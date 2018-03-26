import os
import time
import unittest

import requests

PREFIX = os.environ['CLKHASH_SERVICE_PREFIX']

PROJECT_ID = 'test-data'
KEY1, KEY2 = 'correct', 'horse'
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
        self.assertEqual(r.json(), {'projects': []},
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
            PREFIX + '/projects/{project_id}'.format(
                project_id=PROJECT_ID),
            params=dict(
                key1=KEY1,
                key2=KEY2),
            json=["Oh no this won't work."])
        self.assertEqual(
            r.status_code, 422,
            msg='Expected POST /projects/{} to fail.'.format(
                PROJECT_ID))

        # Actually make the project.
        r = requests.post(
            PREFIX + '/projects/{project_id}'.format(
                project_id=PROJECT_ID),
            params=dict(
                key1=KEY1,
                key2=KEY2),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 201,
            msg='Expected POST /projects/{} to succeed.'.format(
                PROJECT_ID))
        
        # This should fail as the `project_id` already exists.
        r = requests.post(
            PREFIX + '/projects/{project_id}'.format(
                project_id=PROJECT_ID),
            params=dict(
                key1=KEY1,
                key2=KEY2),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 409,
            msg='Expected POST /projects/{} to fail.'.format(
                PROJECT_ID))

        # We can get the project and the project list.
        r = requests.get(PREFIX + '/projects')
        self.assertEqual(r.status_code, 200,
                         msg='Expected GET /projects to succeed.')
        self.assertEqual(r.json(), {'projects': ['test-data']},
                         msg='Unexpected output from GET /projects.')

        r = requests.get(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{} to succeed.'.format(PROJECT_ID))
        self.assertEqual(
            r.json(), {'project_id': PROJECT_ID, 'schema': SCHEMA},
            msg='Unexpected output from GET /project/{}.'.format(PROJECT_ID))

        # Delete the project
        r = requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
        self.assertIn(
            r.status_code, {202, 204},
            msg='Expected DELETE /projects/{} to succeed.'.format(PROJECT_ID))

        # Check if it's actually been deleted.
        r = requests.get(PREFIX + '/projects')
        self.assertEqual(r.status_code, 200,
                         msg='Expected GET /projects to succeed.')
        self.assertEqual(r.json(), {'projects': []},
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
        r = requests.get(PREFIX + '/projects/{}/clks'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks to fail.'.format(PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks/0/2'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks/0/2 to fail.'.format(
                PROJECT_ID))

        r = requests.delete(
            PREFIX + '/projects/{}/clks/0/2'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{}/clks/0/2 to fail.'.format(
                PROJECT_ID))

        # Make the project.
        r = requests.post(
            PREFIX + '/projects/{project_id}'.format(
                project_id=PROJECT_ID),
            params=dict(
                key1=KEY1,
                key2=KEY2),
            json=SCHEMA)
        self.assertEqual(
            r.status_code, 201,
            msg='Expected POST /projects/{} to succeed.'.format(
                PROJECT_ID))

        # There are no clks so the status will be empty.
        r = requests.get(
            PREFIX + '/projects/{project_id}/clks'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks_status': []},
            msg='Unexpected output from GET /projects/{}/clks'.format(
                PROJECT_ID))

        # These clks don't exist so we'll get an empty list when we
        # access them.
        r = requests.get(
            PREFIX + '/projects/{project_id}/clks/0/2'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/0/2 to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks': []},
            msg='Unexpected output from GET /projects/{}/clks/0/2'.format(
                PROJECT_ID))

        # Post clks.
        r = requests.post(
            PREFIX + '/projects/{project_id}/clks/'.format(
                project_id=PROJECT_ID),
            params=dict(
                header=True),
            data='NAME freetext,DOB YYYY/MM/DD,GENDER M or F\n'
                 'Jane Doe,1968/05/19,F\n'
                 'Peter Griffin,1998/12/20,M\n')
        self.assertEqual(
            r.status_code, 202,
            msg='Expected POST /projects/{}/clks to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clk_number': 2, 'clk_start_index': 0},
            msg='Unexpected output from POST /projects/{}/clks'.format(
                PROJECT_ID))

        # The status should be nonempty.
        r = requests.get(
            PREFIX + '/projects/{project_id}/clks'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks to succeed.'.format(
                PROJECT_ID))
        self.assertIn(
            len(r.json()['clks_status']), {1, 2},
            msg='Unexpected output from GET /projects/{}/clks'.format(
                PROJECT_ID))

        # Wait a second for clks to get processed
        time.sleep(1)

        # We can get these clks.
        r = requests.get(
            PREFIX + '/projects/{project_id}/clks/0/2'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/0/2 to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            len(r.json()['clks']), 2,
            msg='Unexpected output from GET /projects/{}/clks/0/2'.format(
                PROJECT_ID))

        # Delete the clks.
        r = requests.delete(
            PREFIX + '/projects/{project_id}/clks/0/2'.format(
                project_id=PROJECT_ID))
        self.assertEqual(r.status_code, 204,
            msg='Expected DELETE /projects/{}/clks/0/2 to succeed.'.format(
                PROJECT_ID))

        # They no longer exist.
        r = requests.get(
            PREFIX + '/projects/{project_id}/clks'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks_status': []},
            msg='Unexpected output from GET /projects/{}/clks'.format(
                PROJECT_ID))

        r = requests.get(
            PREFIX + '/projects/{project_id}/clks/0/2'.format(
                project_id=PROJECT_ID))
        self.assertEqual(
            r.status_code, 200,
            msg='Expected GET /projects/{}/clks/0/2 to succeed.'.format(
                PROJECT_ID))
        self.assertEqual(
            r.json(), {'clks': []},
            msg='Unexpected output from GET /projects/{}/clks/0/2'.format(
                PROJECT_ID))

        # Delete the project and check that the clks aren't there.
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks to fail.'.format(PROJECT_ID))

        r = requests.get(PREFIX + '/projects/{}/clks/0/2'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected GET /projects/{}/clks/0/2 to fail.'.format(
                PROJECT_ID))

        r = requests.delete(
            PREFIX + '/projects/{}/clks/0/2'.format(PROJECT_ID))
        self.assertEqual(
            r.status_code, 404,
            msg='Expected DELETE /projects/{}/clks/0/2 to fail.'.format(
                PROJECT_ID))

    
    def tearDown(self):
        requests.delete(PREFIX + '/projects/{}'.format(PROJECT_ID))
