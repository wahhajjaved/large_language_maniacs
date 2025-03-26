# -*- coding: utf-8 -*-
'''
    tests.utils.test_main
    ~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 Markus Unterwaditzer & contributors
    :license: MIT, see LICENSE for more details.
'''

import click
from click.testing import CliRunner
import pytest
import requests

import vdirsyncer.utils as utils
from vdirsyncer.utils.vobject import split_collection

from .. import blow_up, normalize_item, SIMPLE_TEMPLATE, BARE_EVENT_TEMPLATE


def test_parse_options():
    o = {
        'foo': 'yes',
        'hah': 'true',
        'bar': '',
        'baz': 'whatever',
        'bam': '123',
        'asd': 'off'
    }

    a = dict(utils.parse_options(o.items()))

    expected = {
        'foo': True,
        'hah': True,
        'bar': '',
        'baz': 'whatever',
        'bam': 123,
        'asd': False
    }

    assert a == expected

    for key in a:
        # Yes, we want a very strong typecheck here, because we actually have
        # to differentiate between bool and int, and in Python 2, bool is a
        # subclass of int.
        assert type(a[key]) is type(expected[key])  # flake8: noqa


def test_get_password_from_netrc(monkeypatch):
    username = 'foouser'
    password = 'foopass'
    resource = 'http://example.com/path/to/whatever/'
    hostname = 'example.com'

    calls = []

    class Netrc(object):
        def authenticators(self, hostname):
            calls.append(hostname)
            return username, 'bogus', password

    monkeypatch.setattr('netrc.netrc', Netrc)
    monkeypatch.setattr('getpass.getpass', blow_up)

    _password = utils.get_password(username, resource)
    assert _password == password
    assert calls == [hostname]


@pytest.mark.parametrize('resources_to_test', range(1, 8))
def test_get_password_from_system_keyring(monkeypatch, resources_to_test):
    username = 'foouser'
    password = 'foopass'
    resource = 'http://example.com/path/to/whatever/'
    hostname = 'example.com'

    class KeyringMock(object):
        def __init__(self):
            p = utils.password_key_prefix
            self.resources = [
                p + 'http://example.com/path/to/whatever/',
                p + 'http://example.com/path/to/whatever',
                p + 'http://example.com/path/to/',
                p + 'http://example.com/path/to',
                p + 'http://example.com/path/',
                p + 'http://example.com/path',
                p + 'http://example.com/',
            ][:resources_to_test]

        def get_password(self, resource, _username):
            assert _username == username
            assert resource == self.resources.pop(0)
            if not self.resources:
                return password

    monkeypatch.setattr(utils, 'keyring', KeyringMock())

    netrc_calls = []

    class Netrc(object):
        def authenticators(self, hostname):
            netrc_calls.append(hostname)
            return None

    monkeypatch.setattr('netrc.netrc', Netrc)
    monkeypatch.setattr('getpass.getpass', blow_up)

    _password = utils.get_password(username, resource)
    assert _password == password
    assert netrc_calls == [hostname]


def test_get_password_from_prompt(monkeypatch):
    getpass_calls = []

    class Netrc(object):
        def authenticators(self, hostname):
            return None

    class Keyring(object):
        def get_password(self, *a, **kw):
            return None

    monkeypatch.setattr('netrc.netrc', Netrc)
    monkeypatch.setattr(utils, 'keyring', Keyring())

    user = 'my_user'
    resource = 'http://example.com'

    @click.command()
    def fake_app():
        x = utils.get_password(user, resource)
        click.echo('Password is {}'.format(x))

    runner = CliRunner()
    result = runner.invoke(fake_app, input='my_password\n\n')
    assert not result.exception
    assert result.output.splitlines() == [
        'Server password for {} at the resource {}: '.format(user, resource),
        'Save this password in the keyring? [y/N]: ',
        'Password is my_password'
    ]



def test_get_class_init_args():
    class Foobar(object):
        def __init__(self, foo, bar, baz=None):
            pass

    all, required = utils.get_class_init_args(Foobar)
    assert all == {'foo', 'bar', 'baz'}
    assert required == {'foo', 'bar'}


def test_get_class_init_args_on_storage():
    from vdirsyncer.storage.memory import MemoryStorage

    all, required = utils.get_class_init_args(MemoryStorage)
    assert all == set(['collection', 'read_only', 'instance_name'])
    assert not required


def test_request_verify_fingerprint(httpsserver):
    httpsserver.serve_content(content='hello', code=200, headers=None)
    with pytest.raises(requests.exceptions.SSLError) as excinfo:
        utils.request('GET', httpsserver.url)
    assert 'certificate verify failed' in str(excinfo.value)
    utils.request('GET', httpsserver.url, verify=False)
    with pytest.raises(requests.exceptions.SSLError) as excinfo:
        utils.request('GET', httpsserver.url, verify=None,
                      verify_fingerprint='ABCD')
