import unittest

from pyramid import testing
from pyramid import request

from pyramid.registry import Registry

from tests.mock import dao

class ViewTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def test_rest_view(self):
        from arguxserver.views import MainViews
        #request = testing.DummyRequest(params={'host':'a','items':'b'},path='/argux/rest/1.0/host/a')
        r = request.Request.blank(path='/argux/rest/1.0/a/b')
        r.registry = Registry()
        r.registry.settings = {}
        r.registry.settings['dao'] = dao
        r.matchdict = {'host':'localhost','item':'NONE','action':'details'}
        v = MainViews(r)
        info = v.item_details()
        #self.assertEqual(info['fqdn'], 'a')
