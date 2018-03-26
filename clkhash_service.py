import base64
import csv
import functools
import io
import json
import os

import celery
import clkhash
import connexion
from flask import abort, Response
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.sql

import clkhash_worker
from database import (Clk, ClkStatus, db_session, Project)


CHUNK_SIZE = 1000

connexion_app = connexion.App(__name__)
flask_app = connexion_app.app

BAD_ID_RESPONSE = Response(response='Error: no such project.',
                           status=404,
                           content_type='text/plain')

POST_SUCCESS_RESPONSE = Response(status=201)
del POST_SUCCESS_RESPONSE.headers['Content-Type']

DELETE_SUCCESS_RESPONSE = Response(status=204)
del DELETE_SUCCESS_RESPONSE.headers['Content-Type']


def _does_project_exist(project_id):
    return db_session.query(
            sqlalchemy.sql.exists().where(Project.id == project_id)
        ).scalar()


def _abort_if_project_not_found(fun):
    @functools.wraps(fun)
    def retval(project_id, *args, **kwargs):
        if not _does_project_exist(project_id):
            abort(BAD_ID_RESPONSE)

        else:
            return fun(project_id, *args, **kwargs)

    return retval


def get_projects():
    project_ids = db_session.query(Project.id)
    return {
        'projects': [id_ for id_, in project_ids]
    }


def post_project(project_id, schema, key1, key2):
    # Check that the schema is valid.
    try:
        clkhash.schema.validate_schema_dict(schema)
    except (clkhash.schema.SchemaError,
            json.decoder.JSONDecodeError) as e:
        msg, *_ = e.args
        abort(Response(response='Invalid schema. {}'.format(msg),
                       status=422,
                       content_type='text/plain'))

    project = Project(
        id=project_id,
        schema=schema,
        keys=[key1, key2])
    db_session.add(project)
    
    try:
        db_session.flush()
    except sqlalchemy.exc.IntegrityError:
        abort(Response(response='Error: non-unique ID.',
                       status=409,
                       content_type='text/plain'))
    db_session.commit()
    
    return POST_SUCCESS_RESPONSE


def get_project(project_id):
    project = db_session.query(Project).options(
            sqlalchemy.orm.load_only(Project.schema)
        ).filter(
            Project.id == project_id
        ).one_or_none()

    if project is None:
        abort(BAD_ID_RESPONSE)

    # Note that we're purposefully not exposing the keys.
    return {
            'project_id': project_id,
            'schema': project.schema
        }


def delete_project(project_id):
    delete_count = db_session.query(Project).filter(
            Project.id == project_id
        ).delete()

    if delete_count == 0:
        abort(BAD_ID_RESPONSE)
    elif delete_count == 1:
        # Delete clks also.
        db_session.query(Clk).filter(Clk.project_id == project_id).delete()
        db_session.commit()

        return DELETE_SUCCESS_RESPONSE
    else:
        # This should not happen.
        raise ValueError(
            'Delete count is {}, when it is expected to be 0 or 1'
            .format())


@_abort_if_project_not_found
def get_clks_status(project_id):
    clks = db_session.query(Clk).filter(
            Clk.project_id == project_id
        ).options(
            sqlalchemy.orm.load_only(Clk.index, Clk.status)
        ).order_by(Clk.index)

    clks_iter = iter(clks)
    try:
        group_start = next(clks_iter)
    except StopIteration:
        # No clks.
        return {'clks_status': []}

    groups = []
    count = 1
    for clk in clks_iter:
        if (clk.index == group_start.index + count
                and clk.status == group_start.status):
            count += 1
        else:
            groups.append(dict(
                status=group_start.status.value,
                index=group_start.index,
                count=count))
            group_start = clk
            count = 1
    groups.append(dict(
        status=group_start.status.value,
        index=group_start.index,
        count=count))

    return {'clks_status': groups}


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
    stmt = sqlalchemy.update(Project).where(
            Project.id == project_id
        ).values(
            clk_count=Project.clk_count + len(pii_table)
        ).returning(Project.clk_count)
    result = db_session.execute(stmt)
    db_session.commit()
    start_index = result.scalar() - len(pii_table)

    if start_index is None:
        abort(BAD_ID_RESPONSE)

    # Add PII to db.
    for i, row in enumerate(pii_table, start=start_index):
        clk = Clk(
                project_id=project_id,
                index=i,
                status=ClkStatus.CLK_QUEUED,
                pii=row
            )
        db_session.add(clk)

    try:
        db_session.flush()
    except sqlalchemy.exc.IntegrityError:
        # Project deleted in the meantime. All good, we'll just abort.
        abort(BAD_ID_RESPONSE)
    db_session.commit()

    # Queue up for the worker.
    clk_indices = range(start_index, start_index + len(pii_table))
    for i in range(0, clk_indices.stop - clk_indices.start, CHUNK_SIZE):
        this_indices = clk_indices[i:i + CHUNK_SIZE]
        clkhash_worker.hash.delay(project_id,
                                  validate,
                                  this_indices.start,
                                  this_indices.stop - this_indices.start)

    return dict(clk_start_index=start_index, clk_number=len(pii_table)), 202


@_abort_if_project_not_found
def get_clks(project_id, clk_start_index, clk_number):
    clks = db_session.query(Clk).filter(
            Clk.project_id == project_id,
            Clk.index >= clk_start_index,
            Clk.index < clk_start_index + clk_number
        ).options(
            sqlalchemy.orm.load_only(Clk.index, Clk.status,
                                     Clk.err_msg, Clk.hash)
        )

    return {
        'clks': [{
            'index': c.index,
            'status': c.status.value,
            'errMsg': c.err_msg,
            'hash': base64.b64encode(c.hash).decode('ascii')
                    if c.hash is not None
                    else None
        } for c in clks]
    }


@_abort_if_project_not_found
def delete_clks(project_id, clk_start_index, clk_number):
    db_session.query(Clk).filter(
            Clk.project_id == project_id,
            Clk.index >= clk_start_index,
            Clk.index < clk_start_index + clk_number
        ).delete()
    db_session.commit()

    return DELETE_SUCCESS_RESPONSE


@flask_app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


if __name__ == '__main__':
    connexion_app.add_api('swagger.yaml')
    connexion_app.run(port=int(os.environ.get('PORT', 8080)),
                      debug=True)
