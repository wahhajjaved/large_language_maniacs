from vumi_http_proxy.servicemaker import (
    Options, ProxyWorkerServiceMaker, client)
from vumi_http_proxy import http_proxy
from twisted.trial import unittest
from vumi_http_proxy.test import helpers


class TestOptions(unittest.TestCase):
    def test_defaults(self):
        options = Options()
        options.parseOptions([])
        self.assertEqual(options["port"], 8080)
        self.assertEqual(str(options["interface"]), "0.0.0.0")
        self.assertEqual(str(options["blacklist"]), "./docs/proxy_blacklist.yml")

    def test_override(self):
        options = Options()
        options.parseOptions(["--port", 8000])
        options.parseOptions(["--interface", '127.0.0.1'])
        options.parseOptions(["--blacklist", "fake_blacklist.yml"])
        self.assertEqual(options["port"], "8000")
        self.assertEqual(str(options["interface"]), "127.0.0.1")
        self.assertEqual(str(options["blacklist"]), "fake_blacklist.yml")


class TestProxyWorkerServiceMaker(unittest.TestCase):
    def test_makeService(self):
        options = Options()
        options.parseOptions([])
        self.patch(client, 'createResolver', lambda: helpers.TestResolver())
        servicemaker = ProxyWorkerServiceMaker()
        service = servicemaker.makeService(options)
        self.assertTrue(isinstance(service.factory, http_proxy.ProxyFactory))
        self.assertEqual(service.endpoint._interface, '0.0.0.0')
        self.assertEqual(service.endpoint._port, 8080)
