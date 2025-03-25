import socket

from pulsar import get_actor
from pulsar.apps import http
from pulsar.apps.test import unittest
from pulsar.apps.http import URLError

from .client import TestHttpClientBase


class ExternalBase(TestHttpClientBase):
    with_httpbin = False

    def after_response(self, response):
        pass

    def test_http_get(self):
        client = self.client()
        response = yield client.get('http://www.amazon.co.uk/').on_finished
        self.assertEqual(response.status_code, 200)

    def test_get_https(self):
        client = self.client()
        response = yield client.get('https://github.com/trending').on_finished
        self.assertEqual(response.status_code, 200)

    def test_get_httpbin(self):
        client = self.client()
        response = yield client.get('http://httpbin.org/get').on_finished
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.after_response(response)

    def test_bad_host(self):
        client = self.client()
        response = client.get('http://xxxyyyxxxxyyy/blafoo')
        try:
            yield response.on_finished
        except socket.error:
            self.assertFalse(response.status_code)
            self.assertTrue(response.is_error)
            self.assertRaises(URLError, response.raise_for_status)
        else:
            self.assertTrue(response.request.proxy)
            self.assertTrue(response.status_code >= 400)

    def test_send_files(self):
        client = self.client()
        files = {'test': 'simple file'}
        response = yield client.post('http://httpbin.org/post', files=files
                                     ).on_finished
        self.assertEqual(response.status_code, 200)
        ct = response.request.headers['content-type']
        self.assertTrue(ct.startswith('multipart/form-data; boundary='))
        data = response.json()
        self.assertEqual(data['files'], files)

    def test_http_get_timeit(self):
        client = self.client()
        response = yield client.timeit(10, 'get', 'http://www.amazon.co.uk/'
                                       ).on_finished
        self.assertTrue(response.total_time)


class ProxyExternal(ExternalBase):

    def after_response(self, response):
        self.assertTrue(response.request.proxy)

    def test_get_https(self):
        client = self.client()
        response = client.get('https://github.com/trending')
        r1 = yield response.on_headers
        self.assertEqual(r1.status_code, 200)
        headers1 = r1.headers
        r2 = yield response.on_finished
        self.assertEqual(r2.status_code, 200)
        headers2 = r2.headers
        self.assertNotEqual(len(headers1), len(headers2))


@unittest.skipUnless(get_actor().cfg.http_proxy=='',
                    'Requires no external proxy')
class Test_HttpClient_NoProxy_External(ExternalBase, unittest.TestCase):
    '''Test external URI when no global proxy server is present.
    '''


@unittest.skipUnless(get_actor().cfg.http_proxy=='',
                     'Requires no external proxy')
class Test_HttpClient_Proxy_External(ProxyExternal, unittest.TestCase):
    with_proxy = True


@unittest.skipUnless(get_actor().cfg.http_proxy, 'Requires external proxy')
class Test_HttpClient_ExternalProxy_External(ProxyExternal,
                                             unittest.TestCase):
    pass
