import operator

from bitarray import bitarray
from celery import Celery
import clkhash
from clkhash.schema import Schema
from pymongo import MongoClient, UpdateOne

from common import CLK_DONE, CLK_ERROR, MONGO_SERVER_URI, MONGO_DB

app = Celery('clkhash_worker', broker=MONGO_SERVER_URI)


@app.task
def hash(project_id, validate, start_index, count):
    with MongoClient(MONGO_SERVER_URI) as mongo:
        db = getattr(mongo, MONGO_DB)
        try:
            # You might wonder why the database connection is not
            # within this massive try block. If we error without an
            # active database connection, then there's really nothing
            # we can do anyway except die.

            project = db.projects.find_one(
                project_id,
                projection=dict(_id=False, key1=True, key2=True, schema=True))

            if project is None:
                # Project must have been deleted.
                return

            schema = Schema.from_json_dict(project['schema'])

            # Get PII
            lookup_result = db.clks.find(
                filter={
                    'project_id': project_id,
                    'index': {
                        '$gte': start_index,
                        '$lt': start_index + count
                    }
                },
                projection=dict(_id=False, index=True, pii=True))

            clks_to_process = list(lookup_result)
            if not clks_to_process:
                # PII must have been deleted.
                return

            # TODO: Mark as in progress

            pii = map(operator.itemgetter('pii'), clks_to_process)

            keys = clkhash.key_derivation.generate_key_lists(
                (project['key1'], project['key2']),
                len(schema.fields))
            hash_bitarrays = map(
                operator.itemgetter(0),
                clkhash.bloomfilter.stream_bloom_filters(
                    pii,
                    keys,
                    schema))

            hash_bytes = map(bitarray.tobytes, hash_bitarrays)

            db.clks.bulk_write(
                [UpdateOne(
                    {'project_id': project_id,
                     'index': c['index']},
                    {'$set': {'hash': h, 'pii': None, 'status': CLK_DONE}})
                 for c, h in zip(clks_to_process, hash_bytes)])

        except BaseException as e:
            db.clks.update_many(
                {
                    'project_id': project_id,
                    'index': {
                        '$gte': start_index,
                        '$lt': start_index + count
                    }
                },
                {
                    '$set': {
                        'hash': None,
                        'pii': None,
                        'status': CLK_ERROR,
                        'errmsg': str(e)
                    }
                })
