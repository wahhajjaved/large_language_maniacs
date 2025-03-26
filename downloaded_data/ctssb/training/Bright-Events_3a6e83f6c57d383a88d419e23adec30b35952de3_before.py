from app import createApp,db
from flask import request, jsonify
from functools import wraps
from app.auth_blueprint import models
import jwt
import re
import unittest
import json
import base64

class UserActivitiesTestcase(unittest.TestCase):
    """This class will be used for user test cases"""

    def setUp(self):
        self.app = createApp(conf_name='testing')
        self.client = self.app.test_client

        # binds the app to the current context
        with self.app.app_context():
            # create all tables
            db.create_all()

        self.user = {
            'email': 'test@kungu.com',
            'username':'test',
            'password':'hardpass'
        }
        self.login_details = {
            'username' : 'test@kungu.com',
            'password' : 'hardpass'
        }
        self.user2 = {                        
            'username':'samuel',
            'password':'hardpass'
        }
        self.user3 = {            
            'email': 'emai@gmail.com',
            'username':'samuel'            
        }
        self.user4 = {            
            'email': 'emai@gmail.com',
            'username':'samuel',
            'password':'easypass'          
        }

        self.user_login_without_email = {
            
            "password":"string1"
        }
        self.new_password = {
                  "password":"1234@"
              }

    
    #helper methods to login and register
    #login
    def auth_login(self):
        return self.open_with_auth('/api/v1/auth/login', 'GET', 'test', 'hardpass')

    #register a user
    def register_users(self):
        user_details = json.dumps(self.user)
        return self.client().post('api/v1/auth/register', data=json.dumps(self.user), content_type='application/json')

     #get the token from logged in user
    def get_verfication_token(self):
        
        #register user 1st
        self.register_users()

        #login the user
        res = self.auth_login()
        #from nose.tools import set_trace; set_trace()
        #get the access token        
        token = json.loads(res.data.decode('utf-8'))['token']        
            
        return token
       
    #test if user can register
    def test_auth_register(self):
        res = self.register_users() 
        self.assertEqual(res.status_code, 201)

    def open_with_auth(self, url, method, username, password):
        return self.app.test_client().open(url,
                   method = method,
                   headers = {
                        'Authorization': 'Basic ' + base64.b64encode(bytes(username + ":" + password, 'ascii')).decode('ascii') }
    )

    #test if user login
    def test_auth_login(self):

        self.test_auth_register()
        res = self.auth_login()
        self.assertEqual(res.status_code, 200)

    #test for logout endpoint
    def test_auth_logout(self):
        #register user
        res = self.register_users()
        self.assertEqual(res.status_code, 201)
        #log in user 1st
        res = self.auth_login()
        res.assertEqual(res.status_code, 200)

        #log out user
        token = self.get_verfication_token()

        res = self.client().get('/api/v1/auth/logout',
                    headers = {'x-access-token' : token },
                    content_type='application/json')
        self.assertIn('User has logged out', str(res.data))
        self.assertEqual(res.status_code, 200)


    #make sure email is not empty
    def test_auth_register_email_notEmpty(self):
        res = self.client().post('/api/v1/auth/register', data=json.dumps(self.user2),content_type='application/json')
        self.assertIn("Email must be included", str(res.data))

    # #make sure password is set
    def test_auth_register_password_notEmpty(self):
        res = self.client().post('/api/v1/auth/register', data=json.dumps(self.user3),content_type='application/json')
        self.assertIn("Password must be included", str(res.data))

    #test reset password api 
    def test_auth_reset_password(self):
        #test if user can register before changing password
        res = self.client().post('/api/v1/auth/register', data=json.dumps(self.user4),content_type='application/json')
        self.assertEqual(res.status_code, 201)
        # test if user can now update password
        res = self.client().put('/api/v1/auth/reset-password/emai@gmail.com',data=json.dumps(self.new_password),content_type='application/json')
        self.assertEqual(res.status_code, 201)


    def tearDown(self):
        """teardown all initialized variables."""
        with self.app.app_context():
            # drop all tables
            db.session.remove()
            db.drop_all()
    
    if __name__ == '__main__':
        unittest.main()