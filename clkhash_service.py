import base64
import csv
import functools
import io

import celery
import clkhash
import connexion
from flask import abort, Response
import flask_pymongo
import pymongo

import clkhash_worker


CHUNK_SIZE = 1000

CLK_QUEUED = 'queued'
CLK_IN_PROGRESS = 'in progress'
CLK_DONE = 'done'
CLK_INVALID_DATA = 'invalid data'
CLK_ERROR = 'error'

connexion_app = connexion.App(__name__)
flask_app = connexion_app.app

flask_app.config['MONGO_URI'] = 'mongodb://localhost:27017/admin'
mongo = flask_pymongo.PyMongo(flask_app)

BAD_ID_RESPONSE = Response(response='Error: no such project.',
                           status=404,
                           content_type='text/plain')

POST_SUCCESS_RESPONSE = Response(status=201)
del POST_SUCCESS_RESPONSE.headers['Content-Type']

DELETE_SUCCESS_RESPONSE = Response(status=204)
del DELETE_SUCCESS_RESPONSE.headers['Content-Type']


def _does_project_exist(project_id):
    project_found = mongo.db.projects.count(
        dict(_id=project_id),
        limit=1)

    assert project_found in {0, 1}

    return bool(project_found)


def _abort_if_project_not_found(fun):
    @functools.wraps(fun)
    def retval(project_id, *args, **kwargs):
        if not _does_project_exist(project_id):
            abort(BAD_ID_RESPONSE)

        else:
            return fun(project_id, *args, **kwargs)

    return retval


# Done
def get_projects():
    projects = mongo.db.projects.find({}, dict(_id=True))
    return {
        'projects': [p['_id'] for p in projects]
    }


# Done
def post_project(project_id, schema, key1, key2):
    # Check that the schema is valid.
    try:
        clkhash.schema.Schema.from_json_dict(schema)
    except clkhash.schema.SchemaError as e:
        msg, = e
        abort(Response(response='Invalid schema. {}'.format(msg),
                       status=422,
                       content_type='text/plain'))

    try:
        mongo.db.projects.insert(dict(
            _id=project_id,
            schema=schema,
            key1=key1,
            key2=key2,
            clk_number=0))
    except pymongo.errors.DuplicateKeyError:
        abort(Response(response='Error: non-unique ID.',
                       status=409,
                       content_type='text/plain'))
    else:
        return POST_SUCCESS_RESPONSE


# Done
def get_project(project_id):
    project = mongo.db.projects.find_one(
        dict(_id=project_id),
        projection=dict(_id=True, schema=True))
    if project is None:
        abort(BAD_ID_RESPONSE)

    id_ = project['_id']
    schema = project['schema']

    # Note that we're purposefully not exposing the keys.
    return {
            'project_id': id_,
            'schema': schema
        }


# Done
def delete_project(project_id):
    delete_result = mongo.db.projects.delete_one(dict(_id=project_id))

    delete_count = delete_result.deleted_count
    if delete_count == 0:
        abort(BAD_ID_RESPONSE)
    elif delete_count == 1:
        # Delete clks also.
        mongo.db.clks.delete_many({'project_id': project_id})

        return DELETE_SUCCESS_RESPONSE
    else:
        # This should not happen.
        raise ValueError(
            'Delete count is {}, when it is expected to be 0 or 1'
            .format())


# Done
@_abort_if_project_not_found
def get_clks_status(project_id):
    clks = mongo.db.clks.find({'project_id': project_id},
                              {'status': True, 'index':True})

    clks_iter = iter(clks)
    try:
        group_start = next(clks_iter)
    except StopIteration:
        # No clks.
        return {'clks_status': []}

    groups = []
    count = 1
    for clk in clks_iter:
        if (clk['index'] == group_start['index'] + count
                and clk['status'] == group_start['status']):
            count += 1
        else:
            groups.append(dict(
                status=group_start['status'],
                index=group_start['index'],
                count=count))
            group_start = clk
            count = 1
    groups.append(dict(
        status=group_start['status'],
        index=group_start['index'],
        count=count))

    return {'clks_status': groups}


# Done
@_abort_if_project_not_found
def post_pii(project_id, pii_table, header, validate):
    pii_table = pii_table.decode('utf-8')
    pii_table_stream = io.StringIO(pii_table)

    reader = csv.reader(pii_table_stream)
    if header:
        headings = next(reader)
        # TODO: validate headings

    pii_table = list(reader)

    # Atomically increase clk counter to reserve space for pii.
    start_index_result = mongo.db.projects.find_one_and_update(
        dict(_id=project_id),
        {'$inc': dict(clk_number=len(pii_table))},
        dict(_id=False, clk_number=True)
    )
    if start_index_result is None:
        abort(BAD_ID_RESPONSE)

    start_index = start_index_result['clk_number']
    mongo.db.clks.insert([dict(
            project_id=project_id,
            index=i,
            status=CLK_QUEUED,
            err_msg=None,
            pii=row,
            hash=None)
        for i, row in enumerate(pii_table, start=start_index)])

    # Check if project *still* exists to avoid race conditions.
    # (This is where foreign keys would be useful...)
    if not _does_project_exist(project_id):
        # Project deleted while we were inserting. Clean up.
        mongo.db.clks.delete_many({'project_id': project_id})
        abort(BAD_ID_RESPONSE)
        
    clk_indices = range(start_index, start_index + len(pii_table))
    for i in range(0, clk_indices.stop - clk_indices.start, CHUNK_SIZE):
        this_indices = clk_indices[i:i + CHUNK_SIZE]
        clkhash_worker.hash.delay(project_id,
                                  validate,
                                  this_indices.start,
                                  this_indices.stop - this_indices.start)

    return dict(clk_start_index=start_index, clk_number=len(pii_table))


# Done
@_abort_if_project_not_found
def get_clks(project_id, clk_start_index, clk_number):
    clks = mongo.db.clks.find(
        filter={
            'project_id': project_id,
            'index': {
                '$gte': clk_start_index,
                '$lt': clk_start_index + clk_number
            }
        },
        projection=dict(_id=False, index=True, status=True,
                        err_msg=True, hash=True))

    return {
        'clks': [{
            'index': c['index'],
            'status': c['status'],
            'errMsg': c['err_msg'],
            'hash': base64.b64encode(c['hash']).decode('ascii')
                    if c['hash'] is not None
                    else None
        } for c in clks]
    }


# Done
@_abort_if_project_not_found
def delete_clks(project_id, clk_start_index, clk_number):
    project_found = mongo.db.projects.count(
        dict(_id=project_id),
        limit=1)
    if not project_found:
        abort(BAD_ID_RESPONSE)

    mongo.db.clks.delete_many({
            'project_id': project_id,
            'index': {
                '$gte': clk_start_index,
                '$lt': clk_start_index + clk_number
            }
        })
    return DELETE_SUCCESS_RESPONSE


if __name__ == '__main__':
    connexion_app.add_api('swagger.yaml')
    connexion_app.run(port=8080, debug=True)
