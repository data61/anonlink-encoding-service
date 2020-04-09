import base64
import csv
import functools
import io
import itertools
import json
import os
import urllib.parse

import clkhash
import clkhash.validate_data
import connexion
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.sql
from flask import abort, jsonify, Response, request

import clkhash_worker
from database import Clk, db_session, ClkStatus, Project


CHUNK_SIZE = 1000

connexion_app = connexion.App(__name__)
flask_app = connexion_app.app

_POST_SUCCESS_RESPONSE = Response(status=201)
del _POST_SUCCESS_RESPONSE.headers['Content-Type']

_DELETE_SUCCESS_RESPONSE = Response(status=204)
del _DELETE_SUCCESS_RESPONSE.headers['Content-Type']


def _abort_with_msg(msg, status):
    """Abort with specified message and status code."""
    response = jsonify(errMsg=msg)
    response.status_code = status
    abort(response)


def _abort_project_id_not_found(project_id):
    """Abort with message that the project was not found."""
    _abort_with_msg("no such project '{}'".format(project_id), 404)


def _does_project_exist(project_id):
    """Returns True iff project with ID `project_id` exists."""
    return db_session.query(
            sqlalchemy.sql.exists().where(Project.id == project_id)
        ).scalar()


def _str_to_status_or_abort(status_str):
    """Convert string to ClkStatus; abort if input is unrecognised."""
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


def _intersperse(iterable, item):
    iterator = iter(iterable)  # Remember where we left off
    try:
        yield next(iterator)
    except StopIteration:
        return
    for i in iterator:
        yield item
        yield i


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


def post_project(project_id, keys, body):
    schema = body
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
        db_session.query(Clk).filter(Clk.project_id == project_id).delete()
        db_session.commit()

        return _DELETE_SUCCESS_RESPONSE
    else:
        # This should not happen.
        raise ValueError(
            'delete count is {}, when it is expected to be 0 or 1'
            .format(delete_count))


def _first_last(iterable):
    iterator = iter(iterable)
    try:
        first = last = next(iterator)
    except StopIteration:
        raise ValueError('empty iterable')

    for last in iterator:
        pass

    return first, last


def _group_clks(clks):
    for _, group in itertools.groupby(
            enumerate(clks),
            key=lambda x: (x[1].status,          # Group by status and
                           x[1].index - x[0])):  # by offset from start.
        (_, first_clk), (_, last_clk) = _first_last(group)
        yield {'status': first_clk.status.value,
               'rangeStart': first_clk.index,
               'rangeEnd': last_clk.index + 1}


def _stream_clk_groups(clk_groups):
    yield '{"clksStatus":['
    yield from _intersperse(map(json.dumps, clk_groups), ',')
    yield ']}'


@_abort_if_project_not_found
def get_clks_status(project_id):
    clks = db_session.query(Clk).filter(
            Clk.project_id == project_id
        ).options(
            sqlalchemy.orm.load_only(Clk.index, Clk.status)
        ).order_by(Clk.index)

    clk_groups = _group_clks(clks)
    clk_group_stream = _stream_clk_groups(clk_groups)
    return Response(clk_group_stream, content_type='application/json')


@_abort_if_project_not_found
def post_pii(project_id, body, header, validate):
    pii_table = body
    pii_table = pii_table.decode(request.charset)
    pii_table_stream = io.StringIO(pii_table)

    reader = csv.reader(pii_table_stream)
    if header != 'false':
        try:
            headings = next(reader)
        except StopIteration:
            _abort_with_msg('Header expected but not present.', 422)
        
        if header == 'true':
            project = db_session.query(Project).options(
                sqlalchemy.orm.load_only(Project.schema)
            ).filter(
                Project.id == project_id
            ).one_or_none()

            if project is None:
                # Project deleted in the meantime
                _abort_project_id_not_found(project_id)

            schema = clkhash.schema.from_json_dict(project.schema)
            try:
                clkhash.validate_data.validate_header(schema.fields, headings)
            except clkhash.validate_data.FormatError as e:
                msg, *_ = e.args
                _abort_with_msg(msg, 422)

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
    
    result_scalar = result.scalar()
    if result_scalar is None:
        # Project deleted in the meantime
        _abort_project_id_not_found(project_id)

    start_index = result_scalar - records_num
    clk_mappings = [
        dict(project_id=project_id, index=i, status=ClkStatus.QUEUED, pii=row)
        for i, row in enumerate(pii_table, start=start_index)]
    try:
        db_session.bulk_insert_mappings(Clk, clk_mappings)
    except sqlalchemy.exc.IntegrityError:
        # Project deleted in the meantime. All good, we'll just abort.
        _abort_project_id_not_found(project_id)

    # Queue up for the worker.
    end_index = start_index + records_num
    clk_indices = range(start_index, end_index)
    for i in range(0, clk_indices.stop - clk_indices.start, CHUNK_SIZE):
        this_indices = clk_indices[i:i + CHUNK_SIZE]
        clkhash_worker.hash.delay(project_id,
                                  validate,
                                  this_indices.start,
                                  this_indices.stop)

    # Only commit once we know that the queueing succeeded.
    db_session.commit()

    return {
            'dataIds': {
                'rangeStart': start_index,
                'rangeEnd': end_index
            }
        }, 202


def _clk_to_dict(clk):
    return {
        'index': clk.index,
        'status': clk.status.value,
        'errMsg': clk.err_msg,
        'hash': base64.b64encode(clk.hash).decode('ascii')
                if clk.hash is not None
                else None
    }


def _stream_clks(clks, page_limit):
    clk_iter = iter(clks)  # Remember where we left off
    returned_clks = (clk_iter
                     if page_limit is None
                     else itertools.islice(clk_iter, page_limit))
    yield '{"clks":['
    
    # First clk is a special case since we need to intersperse ","
    try:
        clk = next(returned_clks)
    except StopIteration:
        pass
    else:
        last_index = clk.index
        yield json.dumps(_clk_to_dict(clk))
    
    for clk in returned_clks:
        yield ','
        last_index = clk.index
        yield json.dumps(_clk_to_dict(clk))

    yield '],"responseMetadata":'

    try:  # See if there are clks we haven't returned
        next(clk_iter)
    except StopIteration:
        cursor = None
    else:
        cursor = str(last_index)

    yield json.dumps({'nextCursor': cursor})
    yield '}'


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
        # Already ordered. Limit by `page_limit + 1` so we can check
        # if there are leftover elements.
        query = query.limit(page_limit + 1)

    clks = query.options(
            sqlalchemy.orm.load_only(
                Clk.index, Clk.status, Clk.err_msg, Clk.hash))

    return Response(_stream_clks(clks, page_limit),
                    content_type='application/json')


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


connexion_app.add_api('openapi.yaml')

if __name__ == '__main__':
    connexion_app.run(port=int(os.environ.get('HTTP_PORT', 8080)),
                      debug=True)
