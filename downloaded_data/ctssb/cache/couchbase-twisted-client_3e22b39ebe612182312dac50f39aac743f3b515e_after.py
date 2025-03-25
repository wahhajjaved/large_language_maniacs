#
# Copyright 2013, Couchbase, Inc.
# All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from couchbase.admin import Admin
from couchbase.libcouchbase import HttpResult
from couchbase.exceptions import (
    BadHandleError, ArgumentError, AuthError, ConnectError)

from tests.base import CouchbaseTestCase

class AdminSimpleSet(CouchbaseTestCase):
    def setUp(self):
        super(AdminSimpleSet, self).setUp()
        self.admin = self.make_admin_connection()

    def test_http_request(self):
        htres = self.admin.http_request('pools/')
        self.assertIsInstance(htres, HttpResult)
        self.assertIsInstance(htres.value, dict)
        self.assertEqual(htres.http_status, 200)
        self.assertEqual(htres.url, 'pools/')
        self.assertTrue(htres.success)

    def test_bad_request(self):
        htres = self.admin.http_request('/badpath')
        self.assertIsInstance(htres, HttpResult)
        self.assertFalse(htres.success)

    def test_bad_args(self):
        self.assertRaises(ArgumentError,
                          self.admin.http_request,
                          None)

        self.assertRaises(ArgumentError,
                          self.admin.http_request,
                          '/',
                          method='blahblah')

    def test_bad_auth(self):
        self.assertRaises(AuthError, Admin,
                          'baduser', 'badpass', host=self.host)

    def test_bad_host(self):
        self.assertRaises(ConnectError, Admin,
                          'user', 'pass', host='127.0.0.1', port=1)

    def test_bad_handle(self):
        self.assertRaises(BadHandleError, self.admin.set, "foo", "bar")
        self.assertRaises(BadHandleError, self.admin.get, "foo")
        self.assertRaises(BadHandleError, self.admin.append, "foo", "bar")
        self.assertRaises(BadHandleError, self.admin.delete, "foo")
        self.assertRaises(BadHandleError, self.admin.unlock, "foo", 1)
