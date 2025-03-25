import unittest

import json

from app import app, EnvironmentName, databases


class BucketlistTestCases(unittest.TestCase):
    def setUp(self):
        '''
        Initializes postgres database tables and
        creates a token for each test. Also creates a test_Client for each test.
        The test client enables us to send virtual requests to the server.
        '''

        self.app = app.test_client()
        EnvironmentName('TestingConfig')
        databases.create_all()
        paylod = json.dumps({'username': 'Paul', 'password': 'Upendo'})
        self.app.post('/bucketlist/api/v1/auth/register', data=paylod)
        auth_data = self.app.post('/bucketlist/api/v1/auth/login', data=paylod)
        json_rep = json.loads(auth_data.data)
        self.token = json_rep['Token']
        self.payload1 = json.dumps({'name': 'Before I kick the bucket.'})

    def tearDown(self):
        '''
        Drops table data for each test.
        '''

        databases.session.remove()
        databases.drop_all()

    def test_create_bucketlist_with_empty_name(self):
        payload = json.dumps({'name': ''})
        response = self.app.post('bucketlist/api/v1/bucketlist', data=payload,
                                 headers={"Authorization": self.token})
        self.assertIn('Your Bucketlist needs a title to proceed.',
                      response.data.decode('utf-8'))

    def test_create_bucketlist(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        self.assertTrue(response.status_code == 201)
        self.assertIn('Success', response.data.decode('utf-8'))

    def test_get_bucketlist_while_database_empty(self):
        response = self.app.get('/bucketlist/api/v1/bucketlist',
                                headers={"Authorization": self.token})
        self.assertTrue(response.status_code == 404)
        self.assertIn('Ooops! No bucketlists here',
                      response.data.decode('utf-8'))

    def test_get_bucketlist(self):
        response = self.app.post('/bucketlist/api/v1/bucketlist',
                                 data=self.payload1, headers={"Authorization": self.token})
        response = self.app.get('/bucketlist/api/v1/bucketlist',
                                headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 200)

    def test_get_bucketlist_by_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.get('/bucketlist/api/v1/bucketlist/1',
                                headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 200)

    def test_get_bucketlist_with_invalid_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.get('/bucketlist/api/v1/bucketlist/20',
                                headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 404)
        self.assertIn('Ooops! Sorry this bucketlist does not exist.',
                      response.data.decode('utf-8'))

    def test_delete_bucketlist_with_invalid_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.delete('/bucketlist/api/v1/bucketlist/20',
                                   headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 404)
        self.assertIn('Ooops! Sorry this bucketlist does not exist.',
                      response.data.decode('utf-8'))

    def test_delete_bucketlist(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.delete('/bucketlist/api/v1/bucketlist/1',
                                   headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Bucketlist successfully deleted',
                      response.data.decode('utf-8'))

    def test_edit_bucketlist_with_invalid_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.put('/bucketlist/api/v1/bucketlist/2',
                                data=self.payload1, headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 404)
        self.assertIn('Ooops! Sorry this bucketlist does not exist.',
                      response.data.decode('utf-8'))

    def test_edit_bucketlist(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Die before I do.'})
        response = self.app.put('/bucketlist/api/v1/bucketlist/1',
                                data=payload, headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 201)

    def test_add_items(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise.'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 200)

    def test_add_items_with_invalid_bucket_id(self):
        payload = json.dumps({'name': 'Before I kick the bucket.'})
        response = self.app.post('bucketlist/api/v1/bucketlist', data=payload,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise.'})
        response = self.app.post('bucketlist/api/v1/bucketlist/10/items',
                                 data=payload, headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 404)

    def test_add_items_with_invalid_token(self):
        payload = json.dumps({'name': 'Before I kick the bucket.'})
        response = self.app.post('bucketlist/api/v1/bucketlist', data=payload,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise.'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": 'Invalid'})
        self.assertEqual(response.status_code, 401)

    def test_edit_items(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise.'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.put('bucketlist/api/v1/bucketlist/1/items/1',
                                data=payload, headers={"Authorization": self.token})
        self.assertEqual(response.status_code, 200)

    def test_add_items_that_exist(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise.'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        self.assertIn('Ooops! Sorry, this particular item already exists.',
                      response.data.decode('utf-8'))

    def test_edit_items_that_dont_exist(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.put('bucketlist/api/v1/bucketlist/1/items/1',
                                data=payload, headers={"Authorization": self.token})
        self.assertIn('Ooops! The item_id does not exist.', response.data.decode('utf-8'))
        self.assertTrue(response.status_code == 404)

    def test_edit_items_with_invalid_token(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.put('bucketlist/api/v1/bucketlist/1/items/1',
                                data=payload, headers={"Authorization": 'Invalid'})
        self.assertTrue(response.status_code == 401)

    def test_delete_items(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.delete('bucketlist/api/v1/bucketlist/1/items/1',
                                   data=payload, headers={"Authorization": self.token})
        self.assertTrue(response.status_code == 200)

    def test_delete_items_with_invalid_bucketlist_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.delete('bucketlist/api/v1/bucketlist/10/items/1',
                                   data=payload, headers={"Authorization": self.token})
        self.assertTrue(response.status_code == 404)

    def test_delete_items_with_invalid_token(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.delete('bucketlist/api/v1/bucketlist/1/items/1',
                                   data=payload, headers={"Authorization": 'Invalid'})
        self.assertTrue(response.status_code == 401)

    def test_delete_items_with_invalid_items_id(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        payload = json.dumps({'name': 'Go with bae on a cruise. If she agrees to marry me'})
        response = self.app.post('bucketlist/api/v1/bucketlist/1/items',
                                 data=payload, headers={"Authorization": self.token})
        response = self.app.delete('bucketlist/api/v1/bucketlist/1/items/15',
                                   data=payload, headers={"Authorization": self.token})
        self.assertTrue(response.status_code == 404)

    def test_get_bucketlist_with_invalid_token(self):
        response = self.app.post('bucketlist/api/v1/bucketlist', data=self.payload1,
                                 headers={"Authorization": self.token})
        response = self.app.get('/bucketlist/api/v1/bucketlist/1',
                                headers={"Authorization": 'dd'})
        self.assertEqual(response.status_code, 401)
