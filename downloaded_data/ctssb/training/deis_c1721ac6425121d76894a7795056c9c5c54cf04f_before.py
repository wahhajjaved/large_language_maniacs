"""
Unit tests for the Deis api app.

Run the tests with "./manage.py test api"
"""

from __future__ import unicode_literals

import json
import urllib

from django.conf import settings
from django.test import TestCase


class AuthTest(TestCase):

    fixtures = ['test_auth.json']

    """Tests user registration, authentication and authorization"""

    def test_auth(self):
        """
        Test that a user can register using the API, login and logout
        """
        # make sure logging in with an invalid username/password
        # results in a 200 login page
        url = '/api/auth/login/'
        body = {'username': 'fail', 'password': 'this'}
        response = self.client.post(url, data=json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        # test registration workflow
        username, password = 'newuser', 'password'
        first_name, last_name = 'Otto', 'Test'
        email = 'autotest@deis.io'
        submit = {
            'username': username,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            # try to abuse superuser/staff level perms (not the first signup!)
            'is_superuser': True,
            'is_staff': True,
        }
        url = '/api/auth/register'
        response = self.client.post(url, json.dumps(submit), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['username'], username)
        self.assertNotIn('password', response.data)
        self.assertEqual(response.data['email'], email)
        self.assertEqual(response.data['first_name'], first_name)
        self.assertEqual(response.data['last_name'], last_name)
        self.assertTrue(response.data['is_active'])
        self.assertFalse(response.data['is_superuser'])
        self.assertFalse(response.data['is_staff'])
        self.assertTrue(
            self.client.login(username=username, password=password))
        # test for default objects
        url = '/api/providers'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], len(settings.PROVIDER_MODULES))
        url = '/api/flavors'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 20)
        # test logout and login
        url = '/api/auth/logout/'
        response = self.client.post(url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        url = '/api/providers'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        url = '/api/auth/login/'
        payload = urllib.urlencode({'username': username, 'password': password})
        response = self.client.post(url, data=payload,
                                    content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 302)
        url = '/api/providers'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_cancel(self):
        """Test that a registered user can cancel her account."""
        # test registration workflow
        username, password = 'newuser', 'password'
        first_name, last_name = 'Otto', 'Test'
        email = 'autotest@deis.io'
        submit = {
            'username': username,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            # try to abuse superuser/staff level perms
            'is_superuser': True,
            'is_staff': True,
        }
        url = '/api/auth/register'
        response = self.client.post(url, json.dumps(submit), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            self.client.login(username=username, password=password))
        # test for default objects
        url = '/api/providers'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], len(settings.PROVIDER_MODULES))
        # cancel the account
        url = '/api/auth/cancel'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            self.client.login(username=username, password=password))
