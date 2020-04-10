import base64
import os
import time
import unittest

import requests

PREFIX = os.getenv('CLKHASH_SERVICE_PREFIX', 'http://0.0.0.0:8000')

PROJECT_ID = 'test-data'
KEY = b'correct horse staple battery'
SCHEMA = {
    'version': 1,
    'clkConfig': {
        'l': 1024,
        'k': 20,
        'hash': {
          'type': 'doubleHash'
        },
        'kdf': {
          'type': 'HKDF',
          'hash': 'SHA256',
          'salt': 'SCbL2zHNnmsckfzchsNkZY9XoHk96P/G5nUBrM7ybymlEFsMV6PA'
                  'eDZCNp3rfNUPCtLDMOGQHG4pCQpfhiHCyA==',
          'info': 'c2NoZW1hX2V4YW1wbGU=',
          'keySize': 64
        }
    },
    'features': [
        {
            'identifier': 'NAME freetext',
            'format': {
                'type': 'string',
                'encoding': 'utf-8',
                'case': 'mixed',
                'minLength': 3
            },
            'hashing': {
                'ngram': 2,
                'weight': 0.5
            }
        },
        {
            'identifier': 'DOB YYYY/MM/DD',
            'format': {
                'type': 'string',
                'encoding': 'ascii',
                'description': 'Numbers separated by slashes, in the '
                               'year, month, day order',
                'pattern': '\\d\\d\\d\\d/\\d\\d/\\d\\d'
            },
            'hashing': {
                'ngram': 1,
                'positional': True
            }
        },
        {
            'identifier': 'GENDER M or F',
            'format': {
                'type': 'enum',
                'values': ['M', 'F']
            },
            'hashing': {
                'ngram': 1,
                'weight': 2
            }
        }  
    ]
}


class TestProjects(unittest.TestCase):
    def setUp(self):
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))

    def test_projects(self):
        # At this stage the project doesn't exist, so we cannot get it
        # or delete it.
        r = requests.get(PREFIX + '/projects')
        self.assertEqual(r.status_code, 200,
                         msg='Expected GET /projects to succeed.')
        self.assertNotIn(PROJECT_ID, r.json()['projects'],
                         msg='Unexpected output from GET /projects.')

        r = requests.get(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{} to fail.'.format(PROJECT_ID))

        r = requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{} to fail.'.format(PROJECT_ID))

        # Try making the project with an invalid schema.
        r = requests.post(
            PREFIX + '/projects/'.format(
                project_id=PROJECT_ID),
            params=dict(
                project_id=PROJECT_ID,
                secret_key=base64.b64encode(KEY)),
            json=["Oh no this won't work."])
        self.assertEqual(
            r.status_code, 422,
            msg='Expected POST /projects/{} to fail.'.format(
                PROJECT_ID))

        # Actually make the project.
        r = requests.post(
            PREFIX + '/projects/'.format(
                project_id=PROJECT_ID),
            params=dict(
                project_id=PROJECT_ID,
                secret_key=base64.b64encode(KEY)),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 201,
            msg='Expected POST /projects/{} to succeed.'.format(
                PROJECT_ID))
        
        # This should fail as the `project_id` already exists.
        r = requests.post(
            PREFIX + '/projects/'.format(
                project_id=PROJECT_ID),
            params=dict(
                project_id=PROJECT_ID,
                secret_key=base64.b64encode(KEY)),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 409,
            msg='Expected POST /projects/{} to fail.'.format(
                PROJECT_ID))

        # We can get the project and the project list.
        r = requests.get(PREFIX + '/projects')
        self.assertEqual(r.status_code, 200,
                         msg='Expected GET /projects to succeed.')
        self.assertIn(PROJECT_ID, r.json()['projects'],
                         msg='Unexpected output from GET /projects.')

        r = requests.get(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{} to succeed.'.format(PROJECT_ID))
        self.assertEqual(
            r.json(), {'projectId': PROJECT_ID, 'schema': SCHEMA},
            msg='Unexpected output from GET /project/{}.'.format(PROJECT_ID))

        # Delete the project
        r = requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 204,
            msg='Expected DELETE /projects/{} to succeed.'.format(PROJECT_ID))

        # Check if it's actually been deleted.
        r = requests.get(PREFIX + '/projects')
        self.assertEqual(r.status_code, 200,
                         msg='Expected GET /projects to succeed.')
        self.assertNotIn(PROJECT_ID, r.json()['projects'],
                         msg='Unexpected output from GET /projects.')

        r = requests.get(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{} to fail.'.format(PROJECT_ID))

        r = requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{} to fail.'.format(PROJECT_ID))
    
    def tearDown(self):
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))



class TestClks(unittest.TestCase):
    def setUp(self):
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))

    def test_projects(self):
        # At this stage the project doesn't exist, so we cannot get its
        # clks.
        r = requests.get(PREFIX + '/projects/{}/clks/status'.format(
            PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks to fail.'.format(PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks/ to fail.'.format(PROJECT_ID))

        r = requests.delete(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{}/clks/ to fail.'.format(
                PROJECT_ID))

        # Make the project.
        r = requests.post(
            PREFIX + '/projects/',
            params=dict(
                project_id=PROJECT_ID,
                secret_key=base64.b64encode(KEY)),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 201,
            msg='Expected POST /projects/ to succeed.')

        # There are no clks so the status will be empty.
        r = requests.get(PREFIX + '/projects/{}/clks/status'.format(
            PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/status to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clksStatus': []},
            msg='Unexpected output from GET /projects/{}/clks/status'.format(
                PROJECT_ID))

        # These clks don't exist so we'll get an empty list when we
        # access them.
        r = requests.get(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/ to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks': [], 'responseMetadata': {'nextCursor': None}},
            msg='Unexpected output from GET /projects/{}/clks/'.format(
                PROJECT_ID))

        # Post clks.
        r = requests.post(
            PREFIX + '/projects/{}/pii/'.format(PROJECT_ID),
            params=dict(
                header='true'),
            data='NAME freetext,DOB YYYY/MM/DD,GENDER M or F\n'
                 'Jane Doe,1968/05/19,F\n'
                 'Peter Griffin,1998/12/20,M\n')
        self.assertEqual(
            r.status_code, 202,
            msg='Expected POST /projects/{}/pii/ to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'dataIds': {'rangeStart': 0, 'rangeEnd': 2}},
            msg='Unexpected output from POST /projects/{}/pii/'.format(
                PROJECT_ID))

        # The status should be nonempty.
        r = requests.get(
            PREFIX + '/projects/{}/clks/status'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/status to succeed.'.format(
                PROJECT_ID))
        self.assertIn(
            len(r.json()['clksStatus']), {1, 2},
            msg='Unexpected output from GET /projects/{}/clks/status'.format(
                PROJECT_ID))

        # Wait a second for clks to get processed
        time.sleep(0.5)

        # We can get these clks.
        r = requests.get(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/ to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            len(r.json()['clks']), 2,
            msg='Unexpected output from GET /projects/{}/clks/'.format(
                PROJECT_ID))

        # Delete the clks.
        r = requests.delete(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(r.status_code, 204,
            msg='Expected DELETE /projects/{}/clks/ to succeed.'.format(
                PROJECT_ID))

        # They no longer exist.
        r = requests.get(
            PREFIX + '/projects/{}/clks/status'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/status to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clksStatus': []},
            msg='Unexpected output from GET /projects/{}/clks/status'.format(
                PROJECT_ID))

        r = requests.get(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/ to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks': [], 'responseMetadata': {'nextCursor': None}},
            msg='Unexpected output from GET /projects/{}/clks/'.format(
                PROJECT_ID))

        # Delete the project and check that the clks aren't there.
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks/status'.format(
            PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks/status to fail.'.format(
                PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks/ to fail.'.format(PROJECT_ID))

        r = requests.delete(
            PREFIX + '/projects/{}/clks/'.format(PROJECT_ID),
            params=dict(index_range_start=0,
                        index_range_end=2))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{}/clks/ to fail.'.format(
                PROJECT_ID))

    
    def tearDown(self):
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
