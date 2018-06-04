import os

import celery
import celery.utils
import clkhash
import clkhash.validate_data
import sqlalchemy.exc
import sqlalchemy.orm

from database import Clk, ClkStatus, db_session, Project


try:
    _BROKER_URI = os.environ['CLKHASH_SERVICE_BROKER_URI']
except KeyError as _e:
    _msg = 'Unset environment variable CLKHASH_SERVICE_BROKER_URI.'
    raise KeyError(_msg) from _e


app = celery.Celery(__name__, broker=_BROKER_URI)
logger = celery.utils.log.get_task_logger(__name__)
logger.info("Setting up celery worker...")


def _get_mapping_for_hash(project_id, key_lists,
                          schema, tokenizers, hash_properties,
                          validate,
                          r):
    try:
        if validate:
            clkhash.validate_data.validate_entries(schema.fields,
                                                   [r.pii])
    except (clkhash.validate_data.EntryError,
            clkhash.validate_data.FormatError) as e:
        msg, *_ = e.args
        mapping = dict(
            project_id=project_id, index=r.index,
            err_msg=msg, pii=None, status=ClkStatus.INVALID_DATA)
    else:
        bf, _, _ = clkhash.bloomfilter.crypto_bloom_filter(
            r.pii, tokenizers, schema.fields,
            key_lists, hash_properties)

        mapping = dict(
            project_id=project_id, index=r.index,
            hash=bf.tobytes(), pii=None, status=ClkStatus.DONE)

    return mapping


@app.task
def hash(project_id, validate, start_index, end_index):
    try:
        logger.info('{}-{}: Starting.'.format(start_index, end_index))
        # Mark clks as in process
        db_session.query(Clk).filter(
                Clk.project_id == project_id,
                Clk.index >= start_index,
                Clk.index < end_index
            ).update({
                Clk.status: ClkStatus.IN_PROGRESS
            })
        db_session.commit()

        logger.debug("{}-{}: Marked as 'in-progress'.".format(
            start_index, end_index))

        try:
            project = db_session.query(Project).filter(
                    Project.id == project_id
                ).options(
                    sqlalchemy.orm.load_only(Project.schema, Project.keys)
                ).one()
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info('{}-{}: Project deleted. Exiting early.'.format(
                start_index, end_index))

        schema = clkhash.schema.Schema.from_json_dict(project.schema)
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

        records = db_session.query(Clk).filter(
            Clk.project_id == project_id,
            Clk.index >= start_index,
            Clk.index < end_index)

        mappings = []
        for r in records:
            # Big try/except block, so we can resume hashing on other
            # Clks even if we error.
            mapping = None
            try:
                mapping = _get_mapping_for_hash(
                    project_id, key_lists, schema, tokenizers, hash_properties,
                    validate,
                    r)
            except Exception as e:
                logger.warning('Exception while hashing: {}'.format(e))
                mapping = dict(
                    project_id=project_id, index=r.index,
                    err_msg=str(e), status=ClkStatus.ERROR, pii=None)

            assert mapping is not None
            mappings.append(mapping)

        db_session.bulk_update_mappings(Clk, mappings)
        db_session.commit()

    except BaseException as e:
        logger.error('Fatal error: {}'.format(e))
        db_session.query(Clk).filter(
                Clk.project_id == project_id,
                Clk.index >= start_index,
                Clk.index < end_index
            ).update({
                Clk.hash: None,
                Clk.pii: None,
                Clk.status: ClkStatus.ERROR,
                Clk.err_msg: "Fatal error: {}".format(e)
            })
        db_session.commit()
        raise
