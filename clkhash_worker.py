import os

from celery import Celery
import clkhash
from clkhash.schema import Schema
import sqlalchemy.exc
import sqlalchemy.orm

from database import (Clk, ClkStatus, db_session, Project)


try:
    _BROKER_URI = os.environ['CLKHASH_SERVICE_BROKER_URI']
except KeyError as _e:
    _msg = 'Unset environment variable CLKHASH_SERVICE_BROKER_URI.'
    raise KeyError(_msg) from _e


app = Celery('clkhash_worker', broker=_BROKER_URI)


@app.task
def hash(project_id, validate, start_index, count):
    try:
        try:
            project = db_session.query(Project).filter(
                    Project.id == project_id
                ).options(
                    sqlalchemy.orm.load_only(Project.schema, Project.keys)
                ).one()
        except sqlalchemy.orm.exc.NoResultFound:
            # Project must have been deleted.
            return

        schema = Schema.from_json_dict(project.schema)
        # TODO: cache derived keys in the database
        key_lists = clkhash.key_derivation.generate_key_lists(
            project.keys,
            len(schema.fields),
            key_size=schema.hashing_globals.kdf_key_size,
            salt=schema.hashing_globals.kdf_salt,
            info=schema.hashing_globals.kdf_info,
            kdf=schema.hashing_globals.kdf_type,
            hash_algo=schema.hashing_globals.kdf_hash)

        tokenizers = [clkhash.tokenizer.get_tokenizer(field.hashing_properties)
              for field in schema.fields]
        hash_properties = schema.hashing_globals

        clks = db_session.query(Clk).filter(
            Clk.project_id == project_id,
            Clk.index >= start_index,
            Clk.index < start_index + count)
        # TODO: Mark as in progress

        for c in clks:
            # TODO: Validate
            bf, _, _ = clkhash.bloomfilter.crypto_bloom_filter(
                c.pii, tokenizers, schema.fields, key_lists, hash_properties)
            c.hash = bf.tobytes()
            c.pii = None
            c.status = ClkStatus.DONE
        
        try:
            db_session.flush()
        except sqlalchemy.orm.exc.StaleDataError:
            # TODO: Do not roll all changes back. Only ignore deleted clks.
            # These clks were deleted.
            db_session.rollback()
        else:
            db_session.commit()

    except BaseException as e:
        clks = db_session.query(Clk).filter(
                Clk.project_id == project_id,
                Clk.index >= start_index,
                Clk.index < start_index + count
            ).update({
                Clk.hash: None,
                Clk.pii: None,
                Clk.status: ClkStatus.ERROR,
                Clk.err_msg: str(e)
            })
        db_session.flush()
        db_session.commit()
        raise
