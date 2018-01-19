import requests

server = 'http://localhost:5000'

project = requests.post(f'{server}/projects',
                        json={
                            'keys': ['testkey1', 'testkey2'],
                            'schema': ['ANY freetext', 'ANY freetext']
                        }
                        ).json()
assert project['status'] == 'created'
project_id = project['id']

print(project_id)
pii_data = [
    {'name': 'Brian Thorne', 'states': 'nsw'},
    {'name': 'Brian Rhys Thorne', 'states': 'NSW'},
    {'name': 'Harry Potter', 'states': 'VIC'},
    {'name': 'Arnold', 'states': 'NSW'},
]

status = requests.post(
    f'{server}/projects/{project_id}',
    json={'data': pii_data}).json()

print(status)


status = requests.get(f'{server}/projects/{project_id}/clks',).json()

print(status)


