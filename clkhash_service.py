import base64
import csv
import functools
import io
import os
import urllib.parse

from flask import abort, Response
import clkhash
import connexion
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.sql

import clkhash_worker
from database import Clk, db_session, ClkStatus, Project


CHUNK_SIZE = 1000

connexion_app = connexion.App(__name__)
flask_app = connexion_app.app

_POST_SUCCESS_RESPONSE = Response(status=201)
del _POST_SUCCESS_RESPONSE.headers['Content-Type']

_DELETE_SUCCESS_RESPONSE = Response(status=204)
del _DELETE_SUCCESS_RESPONSE.headers['Content-Type']


def _apply(function, *iterables):
    """Apply function and discard result."""
    for args in zip(*iterables):
        function(*args)


# TODO: make this return JSON
def _abort_with_msg(msg, status):
    abort(Response(response=msg,
                   status=status,
                   content_type='text/plain'))


def _abort_project_id_not_found(project_id):
    _abort_with_msg("No such project '{}'.".format(project_id), 404)


def _does_project_exist(project_id):
    return db_session.query(
            sqlalchemy.sql.exists().where(Project.id == project_id)
        ).scalar()


def _str_to_status_or_abort(status_str):
    try:
        status_enum = ClkStatus(status_str)
    except ValueError:
        _abort_with_msg("'{}' is not a valid status".format(status_str), 400)
    return status_enum


def _abort_if_project_not_found(function):
    @functools.wraps(function)
    def retval(project_id, *args, **kwargs):
        if not _does_project_exist(project_id):
            _abort_project_id_not_found(project_id)
        else:
            return function(project_id, *args, **kwargs)

    return retval


def _query_statuses_to_enum_or_abort(query_statuses):
    if query_statuses is None:
        return None
    status_strs = query_statuses.split(',')
    status_enums = frozenset(map(_str_to_status_or_abort, status_strs))
    return status_enums


def _make_clk_query(project_id, index_range_start, index_range_end, status):
    query = db_session.query(Clk).filter(Clk.project_id == project_id)
    if index_range_start is not None:
        query = query.filter(Clk.index >= index_range_start)
    if index_range_end is not None:
        query = query.filter(Clk.index < index_range_end)
    if status is not None:
        query = query.filter(Clk.status.in_(status))
    return query


def get_projects():
    project_ids = db_session.query(Project.id)
    return {
        'projects': [id_ for id_, in project_ids]
    }


def post_project(schema, project_id, keys):
    # Check that the schema is valid.
    try:
        clkhash.schema.validate_schema_dict(schema)
    except clkhash.schema.SchemaError as e:
        msg, *_ = e.args
        _abort_with_msg('invalid schema\n\n{}'.format(msg), 422)

    # Store keys as array of base64 strings
    b64_keys = list(map(urllib.parse.unquote, keys.split(',')))

    # Validate the base64:
    for b64_key in b64_keys:
        try:
            base64.b64decode(b64_key, validate=True)
        except ValueError:
            msg = "'{}' is not a valid base64 string".format(b64_key)
            _abort_with_msg(msg, 422)

    project = Project(
        id=project_id,
        schema=schema,
        keys=b64_keys)
    db_session.add(project)

    try:
        db_session.flush()
    except sqlalchemy.exc.IntegrityError:
        db_session.rollback()
        _abort_with_msg("Project '{}' already exists.".format(project_id), 409)
    db_session.commit()

    return _POST_SUCCESS_RESPONSE


def get_project(project_id):
    project = db_session.query(Project).options(
            sqlalchemy.orm.load_only(Project.schema)
        ).filter(
            Project.id == project_id
        ).one_or_none()

    if project is None:
        _abort_project_id_not_found(project_id)

    # We're purposefully not exposing the keys.
    return {
            'projectId': project_id,
            'schema': project.schema
        }


def delete_project(project_id):
    delete_count = db_session.query(Project).filter(
            Project.id == project_id
        ).delete()

    if delete_count == 0:
        _abort_project_id_not_found(project_id)
    elif delete_count == 1:
        # Delete clks also.
        # TODO: abort Celery jobs
        db_session.query(Clk).filter(Clk.project_id == project_id).delete()
        db_session.commit()

        return _DELETE_SUCCESS_RESPONSE
    else:
        # This should not happen.
        raise ValueError(
            'delete count is {}, when it is expected to be 0 or 1'
            .format(delete_count))


@_abort_if_project_not_found
def get_clks_status(project_id):
    clks = db_session.query(Clk).filter(
            Clk.project_id == project_id
        ).options(
            sqlalchemy.orm.load_only(Clk.index, Clk.status)
        ).order_by(Clk.index)

    clks_iter = iter(clks)  # Resume iteration from where we stopped.
    try:
        group_start = next(clks_iter)
    except StopIteration:
        # No clks.
        return {'clksStatus': []}

    # TODO: use itertools.groupby
    groups = []
    count = 1
    for clk in clks_iter:
        if (clk.index == group_start.index + count
                and clk.status == group_start.status):
            count += 1
        else:
            groups.append(dict(
                status=group_start.status.value,
                rangeStart=group_start.index,
                rangeEnd=group_start.index + count))
            group_start = clk
            count = 1
    groups.append(dict(
        status=group_start.status.value,
        rangeStart=group_start.index,
        rangeEnd=group_start.index + count))

    return {'clksStatus': groups}


@_abort_if_project_not_found
def post_pii(project_id, pii_table, header, validate):
    # TODO: default encoding is actually ISO/IEC 8859-1. Pemit specifying UTF-8 in header.
    pii_table = pii_table.decode('utf-8')
    pii_table_stream = io.StringIO(pii_table)

    reader = csv.reader(pii_table_stream)
    if header:
        try:
            headings = next(reader)
            # TODO: validate headers
        except StopIteration:
            _abort_with_msg('Header expected but not present.', 422)

    pii_table = tuple(reader)
    records_num = len(pii_table)

    # Atomically increase clk counter to reserve space for PII.
    stmt = sqlalchemy.update(Project).where(
            Project.id == project_id
        ).values(
            clk_count=Project.clk_count + records_num
        ).returning(Project.clk_count)
    result = db_session.execute(stmt)
    db_session.commit()
    start_index = result.scalar() - records_num

    if start_index is None:
        _abort_project_id_not_found(project_id)

    # Add PII to db.
    # TODO: Benchmark this and optimise if necessary.
    for i, row in enumerate(pii_table, start=start_index):
        clk = Clk(
                project_id=project_id,
                index=i,
                status=ClkStatus.QUEUED,
                pii=row
            )
        db_session.add(clk)

    try:
        db_session.flush()
    except sqlalchemy.exc.IntegrityError:
        # Project deleted in the meantime. All good, we'll just abort.
        db_session.rollback()
        _abort_project_id_not_found(project_id)

    # Queue up for the worker.
    # TODO: merge jobs from multiple calls?
    end_index = start_index + records_num
    clk_indices = range(start_index, end_index)
    for i in range(0, clk_indices.stop - clk_indices.start, CHUNK_SIZE):
        this_indices = clk_indices[i:i + CHUNK_SIZE]
        clkhash_worker.hash.delay(project_id,
                                  validate,
                                  this_indices.start,
                                  this_indices.stop - this_indices.start)

    # Only commit once we know that the queueing succeeded.
    db_session.commit()

    return {
            'dataIds': {
                'rangeStart': start_index,
                'rangeEnd': end_index
            }
        }, 202


@_abort_if_project_not_found
def get_clks(project_id,
             index_range_start=None,
             index_range_end=None,
             status=None,
             page_limit=None,
             cursor=None):
    # Deal with cursor. Currently, it's just the index of the last
    # returned element. However, its type is str so we can extend it
    # in the future.
    if cursor is not None:
        try:
            last_returned_index = int(cursor)
        except ValueError:
            _abort_with_msg('the cursor is not parseable', 400)

        if ((index_range_start is not None
             and last_returned_index < index_range_start)
            or (index_range_end is not None
                and index_range_end <= last_returned_index)):
            # Impossible that the cursor comes from the last call.
            _abort_with_msg('the cursor does not match the request', 422)
        
        index_range_start = last_returned_index + 1

    status_enums = _query_statuses_to_enum_or_abort(status)
    query = _make_clk_query(project_id,
                            index_range_start, index_range_end,
                            status_enums)
    query = query.order_by(Clk.index)

    if page_limit is not None:
        # Already ordered. # Limit by `page_limit + 1` so we can check
        # if there are leftover elements.
        query = query.limit(page_limit + 1)
    
    # TODO: What happens if this can't fit in memory? Needs handling.
    clks = query.options(
            sqlalchemy.orm.load_only(
                Clk.index, Clk.status, Clk.err_msg, Clk.hash)).all()
    assert page_limit is None or 0 <= len(clks) <= page_limit + 1

    if page_limit is not None and len(clks) > page_limit:
        assert 1 <= page_limit  # Guaranteed by Swagger spec.
        assert len(clks) >= 2  # Follows from above.
        clks = clks[:-1]  # Last row is just to check for termination
        cursor = str(clks[-1].index)
    else:
        cursor = None

    # TODO: stream: https://blog.al4.co.nz/2016/01/streaming-json-with-flask/
    return {
        'clks': [{
            'index': c.index,
            'status': c.status.value,
            'errMsg': c.err_msg,
            'hash': base64.b64encode(c.hash).decode('ascii')
                    if c.hash is not None
                    else None
        } for c in clks],
        'responseMetadata': {
            'nextCursor': cursor
        }
    }



@_abort_if_project_not_found
def delete_clks(project_id,
                index_range_start=None,
                index_range_end=None,
                status=None):
    status_enums = _query_statuses_to_enum_or_abort(status)
    query = _make_clk_query(project_id,
                            index_range_start, index_range_end,
                            status_enums)

    query.delete(synchronize_session=False)
    db_session.commit()

    return _DELETE_SUCCESS_RESPONSE


@flask_app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


if __name__ == '__main__':
    connexion_app.add_api('swagger.yaml')
    connexion_app.run(port=int(os.environ.get('HTTP_PORT', 8080)),
                      debug=True)
