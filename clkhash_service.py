import celery
import clkhash
import connexion
from flask import abort, Response
import flask_pymongo
import pymongo


connexion_app = connexion.App(__name__)
flask_app = connexion_app.app
mongo = flask_pymongo.PyMongo(flask_app)


BAD_ID_RESPONSE = Response(response='Error: no such project.',
                           status=404,
                           content_type='text/plain')

POST_SUCCESS_RESPONSE = Response(status=201)
del POST_SUCCESS_RESPONSE.headers['Content-Type']

DELETE_SUCCESS_RESPONSE = Response(status=204)
del DELETE_SUCCESS_RESPONSE.headers['Content-Type']


def get_projects():
    return [p['_id']
            for p in mongo.db.projects.find({}, dict(_id=True))]


def post_project(project_id, schema, key1, key2):
    # Check that the schema is valid.
    try:
        clkhash.schema.Schema.from_json_dict(schema)
    except clkhash.schema.SchemaError:
        # TODO: Provide more detail.
        abort(Response(response='Invalid schema.',
                       status=422,
                       content_type='text/plain'))

    try:
        mongo.db.projects.insert(dict(
            _id=project_id,
            schema=schema,
            key1=key1,
            key2=key2))
    except pymongo.errors.DuplicateKeyError:
        abort(Response(response='Error: non-unique ID.',
                       status=409,
                       content_type='text/plain'))
    else:
        return POST_SUCCESS_RESPONSE


def get_project(project_id):
    project = mongo.db.projects.find_one(dict(_id=project_id))
    if project is None:
        abort(BAD_ID_RESPONSE)

    id_ = project['_id']
    schema = project['schema']

    # Let's not expose the keys.
    return dict(project_id=id_, schema=schema)


def delete_project(project_id):
    delete_result = mongo.db.projects.delete_one(dict(_id=project_id))

    delete_count = delete_result.deleted_count
    if delete_count == 0:
        abort(BAD_ID_RESPONSE)
    elif delete_count == 1:
        return DELETE_SUCCESS_RESPONSE
    else:
        # This should not happen.
        raise ValueError(
            'Delete count is {}, when it is expected to be 0 or 1'
            .format())


def get_clks_status():
    raise NotImplementedError()


def post_pii():
    raise NotImplementedError()


def get_clks():
    raise NotImplementedError()


def delete_clks():
    raise NotImplementedError()


connexion_app.add_api('swagger.yaml')
connexion_app.run(port=8080, debug=True)
