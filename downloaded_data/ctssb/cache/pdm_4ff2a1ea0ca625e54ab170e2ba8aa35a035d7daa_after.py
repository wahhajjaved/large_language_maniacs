#!/usr/bin/env python
""" Test SiteService client class. """

import mock
import logging
import datetime
import unittest

from pdm.site.SiteClient import SiteClient
from pdm.site.SiteService import SiteService
from pdm.framework.Tokens import TokenService
from pdm.framework.FlaskWrapper import FlaskServer
from pdm.framework.RESTClient import RESTClientTest

class test_SiteClient(unittest.TestCase):

    SITE_INFO = {'site_name': "Test Site",
                 'site_desc': "Lovely Test Site",
                 'user_ca_cert': "---PEM1---",
                 'service_ca_cert': "---PEM2---", 
                 'auth_type': 0,
                 'auth_uri': "localhost:12345",
                 'public': True,
                 'def_path': "~/tmp",
                 'endpoints': [ "localhost1:2", "localhost3:4" ]}

    def set_user_token(self, user_id):
        raw_token = {'id': user_id}
        token_svc = TokenService()
        token = token_svc.issue(raw_token)
        self._service.fake_auth("TOKEN", token)

    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self._service = FlaskServer("pdm.endpoint.SiteService")
        self._service.test_mode(SiteService, {}, with_test=False)
        self.set_user_token(1000)
        self._test = self._service.test_client()
        patcher, inst = RESTClientTest.patch_client(SiteClient,
                                                    self._test,
                                                    '/site/api/v1.0')
        self._patcher = patcher
        self._inst = inst

    def tearDown(self):
        self._patcher.stop()

    def test_service(self):
        """ Check we can get service info.
        """
        service_info = self._inst.get_service_info()
        # Unfortunately we don't have any easy way to get service
        # info loaded into the test service. Make to with the type
        # for now.
        self.assertIsInstance(service_info, dict)

    def test_site(self):
        """ Check we can add, get and delete a site.
        """
        site_id = self._inst.add_site(self.SITE_INFO)
        self.assertIsInstance(site_id, int)
        # Test getting the site by ID
        res = self._inst.get_site(site_id)
        self.assertIsInstance(res, dict)
        self.assertEqual(res['site_name'], "Test Site")
        # Check that the site appears in the list
        res = self._inst.get_sites()
        self.assertIsInstance(res, list)
        site_names = [x['site_name'] for x in res]
        self.assertIn("Test Site", site_names)
        # Check the endpoint function
        eps = self._inst.get_endpoints(site_id)
        self.assertIsInstance(eps, list)
        self.assertEqual(len(eps), 2)
        self.assertIn("localhost3:4", eps)
        # Try the delete function
        self._inst.del_site(site_id)
        self.assertRaises(Exception, self._inst.get_site, site_id)
        # Put the site back and delete it by user id
        site_id = self._inst.add_site(self.SITE_INFO)
        self._inst.del_user(1000)
        self.assertRaises(Exception, self._inst.get_site, site_id)

    @mock.patch("pdm.site.SiteService.X509Utils")
    @mock.patch("pdm.site.SiteService.MyProxyUtils")
    def test_session(self, mp_mock, x509_mock):
        """ Test the session related functions. """
        mp_mock.logon.return_value = "PROXY_DATA"
        x509_mock.get_cert_expiry.return_value = datetime.datetime.utcnow()
        # First create test site
        site_id = self._inst.add_site(self.SITE_INFO)
        # Now test session parts
        res = self._inst.get_session_info(site_id)
        self.assertIsInstance(res, dict)
        self.assertFalse(res['ok'])
        self._inst.logon(site_id, "a", "b", 123, voms="vo1")
        cred = self._inst.get_cred(site_id, 1000)
        self.assertEqual(cred, "PROXY_DATA")
        self._inst.logoff(site_id)
        # Check the cred is gone
        self.assertRaises(Exception, self._inst.get_cred, 2, 1000)
