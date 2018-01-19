import uuid

from flask import Flask, request, json
from jsonschema import validate, ValidationError
from clkhash import clk


app = Flask(__name__)

# Our global state...
projects = {}

# Define REST data types using json-schema
NEW_PROJECT_SCHEMA = {
    'type': "object",
    'properties': {
        'name': {'type': 'string'},
        'schema': {'type': 'object'},
        'keys': {'type': 'array', 'items': {'type': 'string'}, 'maxLength': 2, "uniqueItems": True}
    }
}

PII_UPLOAD_SCHEMA = {
    'type': "object",
    'properties': {
        'data': {
            'type': 'array',
            'items': {
                'type': 'object'
            }
        }
    }
}

# Return types:
PROJCET_INFO_SCHEMA = {
    'type': "object",
    'properties': {
        'status': {'enum': ['hashing', 'created', 'error', 'complete']},
        'uploaded': {'type': 'number'},
        'hashed': {'type': 'number'}
    }
}


class Project:

    def __init__(self, keys, name=None, schema=None):
        self.name = name
        self.schema = schema
        self.keys = keys
        self.status = "created"
        self.pii_data = []
        self.clks = []

    @staticmethod
    def from_json(data):
        p = Project(keys=data['keys'])
        if 'scehma' in data:
            # TODO validate schema
            p.schema = data['schema']
        if 'name' in data:
            p.name = data['name']

        return p

    def to_json(self):
        return {
          "status": self.status,
          "uploaded": len(self.pii_data),
          "hashed": len(self.clks)
        }

    def add_pii_data(self, data):
        self.pii_data = data
        self.status = "hashing"

    def hash(self):
        return clk.hash_and_serialize_chunk(self.pii_data, self.schema, self.keys)


def create_project():
    app.logger.debug('Creating project')
    data = request.json

    try:
        validate(data, NEW_PROJECT_SCHEMA)
    except ValidationError as e:
        return "Invalid project - " + e.message, 400

    new_project_id = uuid.uuid4().hex
    projects[new_project_id] = Project.from_json(data)

    return json.dumps({
        "status": "created",
        "id": new_project_id
    })


def list_projects():
    app.logger.debug('Listing projects')
    return json.dumps([k for k in projects])


@app.route("/projects", methods=['GET', 'POST'])
def project_root():
    if request.method == 'POST':
        return create_project()
    else:
        return list_projects()


@app.route("/projects/<project_id>", methods=['GET'])
def project_description(project_id: str):
    project_data = projects[project_id].to_json()
    validate(project_data, PROJCET_INFO_SCHEMA)
    return json.dumps(project_data)


@app.route("/projects/<project_id>", methods=['POST'])
def pii_upload(project_id: str):
    print('uploading data for {}'.format(project_id))
    if project_id not in projects:
        return "Project not found", 404

    try:
        validate(request.json, PII_UPLOAD_SCHEMA)
    except ValidationError as e:
        return "Invalid data - " + e.message, 400

    projects[project_id].add_pii_data(request.json['data'])

    project_status = projects[project_id].to_json()
    validate(project_status, PROJCET_INFO_SCHEMA)
    return json.dumps(project_status)


@app.route("/projects/<project_id>/clks", methods=['GET'])
def get_clks(project_id: str):
    clk_data = projects[project_id].hash()

    return json.dumps(clk_data)
