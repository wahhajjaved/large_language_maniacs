# Authors:
#   Rob Crittenden <rcritten@redhat.com>
#
# Copyright (C) 2010  Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Test some simple LDAP requests using the ldap2 backend

# This fetches a certificate from a host principal so we can ensure that the
# schema is working properly. We know this because the schema will tell the
# encoder not to utf-8 encode binary attributes.

# The DM password needs to be set in ~/.ipa/.dmpw

import os
import sys

import pytest
import nose
from nose.tools import assert_raises  # pylint: disable=E0611
import nss.nss as nss
import six

from ipaserver.plugins.ldap2 import ldap2
from ipalib import api, x509, create_api, errors
from ipapython import ipautil
from ipaplatform.paths import paths
from ipapython.dn import DN

if six.PY3:
    unicode = str


@pytest.mark.tier0
class test_ldap(object):
    """
    Test various LDAP client bind methods.
    """

    def setup(self):
        self.conn = None
        self.ldapuri = 'ldap://%s' % ipautil.format_netloc(api.env.host)
        self.ccache = paths.TMP_KRB5CC % os.getuid()
        nss.nss_init_nodb()
        self.dn = DN(('krbprincipalname','ldap/%s@%s' % (api.env.host, api.env.realm)),
                     ('cn','services'),('cn','accounts'),api.env.basedn)

    def teardown(self):
        if self.conn and self.conn.isconnected():
            self.conn.disconnect()

    def test_anonymous(self):
        """
        Test an anonymous LDAP bind using ldap2
        """
        self.conn = ldap2(api, ldap_uri=self.ldapuri)
        self.conn.connect()
        dn = api.env.basedn
        entry_attrs = self.conn.get_entry(dn, ['associateddomain'])
        domain = entry_attrs.single_value['associateddomain']
        assert domain == api.env.domain

    def test_GSSAPI(self):
        """
        Test a GSSAPI LDAP bind using ldap2
        """
        if not ipautil.file_exists(self.ccache):
            raise nose.SkipTest('Missing ccache %s' % self.ccache)
        self.conn = ldap2(api, ldap_uri=self.ldapuri)
        self.conn.connect(ccache='FILE:%s' % self.ccache)
        entry_attrs = self.conn.get_entry(self.dn, ['usercertificate'])
        cert = entry_attrs.get('usercertificate')
        cert = cert[0]
        serial = unicode(x509.get_serial_number(cert, x509.DER))
        assert serial is not None

    def test_simple(self):
        """
        Test a simple LDAP bind using ldap2
        """
        pwfile = api.env.dot_ipa + os.sep + ".dmpw"
        if ipautil.file_exists(pwfile):
            fp = open(pwfile, "r")
            dm_password = fp.read().rstrip()
            fp.close()
        else:
            raise nose.SkipTest("No directory manager password in %s" % pwfile)
        self.conn = ldap2(api, ldap_uri=self.ldapuri)
        self.conn.connect(bind_dn=DN(('cn', 'directory manager')), bind_pw=dm_password)
        entry_attrs = self.conn.get_entry(self.dn, ['usercertificate'])
        cert = entry_attrs.get('usercertificate')
        cert = cert[0]
        serial = unicode(x509.get_serial_number(cert, x509.DER))
        assert serial is not None

    def test_Backend(self):
        """
        Test using the ldap2 Backend directly (ala ipa-server-install)
        """

        # Create our own api because the one generated for the tests is
        # a client-only api. Then we register in the commands and objects
        # we need for the test.
        myapi = create_api(mode=None)
        myapi.bootstrap(context='cli', in_server=True)
        myapi.finalize()

        pwfile = api.env.dot_ipa + os.sep + ".dmpw"
        if ipautil.file_exists(pwfile):
            fp = open(pwfile, "r")
            dm_password = fp.read().rstrip()
            fp.close()
        else:
            raise nose.SkipTest("No directory manager password in %s" % pwfile)
        myapi.Backend.ldap2.connect(bind_dn=DN(('cn', 'Directory Manager')), bind_pw=dm_password)

        result = myapi.Command['service_show']('ldap/%s@%s' %  (api.env.host, api.env.realm,))
        entry_attrs = result['result']
        cert = entry_attrs.get('usercertificate')
        cert = cert[0]
        serial = unicode(x509.get_serial_number(cert, x509.DER))
        assert serial is not None

    def test_autobind(self):
        """
        Test an autobind LDAP bind using ldap2
        """
        ldapuri = 'ldapi://%%2fvar%%2frun%%2fslapd-%s.socket' % api.env.realm.replace('.','-')
        self.conn = ldap2(api, ldap_uri=ldapuri)
        try:
            self.conn.connect(autobind=True)
        except errors.ACIError:
            raise nose.SkipTest("Only executed as root")
        entry_attrs = self.conn.get_entry(self.dn, ['usercertificate'])
        cert = entry_attrs.get('usercertificate')
        cert = cert[0]
        serial = unicode(x509.get_serial_number(cert, x509.DER))
        assert serial is not None


@pytest.mark.tier0
class test_LDAPEntry(object):
    """
    Test the LDAPEntry class
    """
    cn1 = [u'test1']
    cn2 = [u'test2']
    dn1 = DN(('cn', cn1[0]))
    dn2 = DN(('cn', cn2[0]))

    def setup(self):
        self.ldapuri = 'ldap://%s' % ipautil.format_netloc(api.env.host)
        self.conn = ldap2(api, ldap_uri=self.ldapuri)
        self.conn.connect()

        self.entry = self.conn.make_entry(self.dn1, cn=self.cn1)

    def teardown(self):
        if self.conn and self.conn.isconnected():
            self.conn.disconnect()

    def test_entry(self):
        e = self.entry
        assert e.dn is self.dn1
        assert u'cn' in e
        assert u'cn' in e.keys()
        assert 'CN' in e
        if six.PY2:
            assert 'CN' not in e.keys()
        else:
            assert 'CN' in e.keys()
        assert 'commonName' in e
        if six.PY2:
            assert 'commonName' not in e.keys()
        else:
            assert 'commonName' in e.keys()
        assert e['CN'] is self.cn1
        assert e['CN'] is e[u'cn']

        e.dn = self.dn2
        assert e.dn is self.dn2

    def test_set_attr(self):
        e = self.entry
        e['commonName'] = self.cn2
        assert u'cn' in e
        assert u'cn' in e.keys()
        assert 'CN' in e
        if six.PY2:
            assert 'CN' not in e.keys()
        else:
            assert 'CN' in e.keys()
        assert 'commonName' in e
        if six.PY2:
            assert 'commonName' not in e.keys()
        else:
            assert 'commonName' in e.keys()
        assert e['CN'] is self.cn2
        assert e['CN'] is e[u'cn']

    def test_del_attr(self):
        e = self.entry
        del e['CN']
        assert 'CN' not in e
        assert 'CN' not in e.keys()
        assert u'cn' not in e
        assert u'cn' not in e.keys()
        assert 'commonName' not in e
        assert 'commonName' not in e.keys()

    def test_popitem(self):
        e = self.entry
        assert e.popitem() == ('cn', self.cn1)
        assert list(e) == []

    def test_setdefault(self):
        e = self.entry
        assert e.setdefault('cn', self.cn2) == self.cn1
        assert e['cn'] == self.cn1
        assert e.setdefault('xyz', self.cn2) == self.cn2
        assert e['xyz'] == self.cn2

    def test_update(self):
        e = self.entry
        e.update({'cn': self.cn2}, xyz=self.cn2)
        assert e['cn'] == self.cn2
        assert e['xyz'] == self.cn2

    def test_pop(self):
        e = self.entry
        assert e.pop('cn') == self.cn1
        assert 'cn' not in e
        assert e.pop('cn', 'default') is 'default'
        with assert_raises(KeyError):
            e.pop('cn')

    def test_clear(self):
        e = self.entry
        e.clear()
        assert not e
        assert 'cn' not in e

    @pytest.mark.skipif(sys.version_info >= (3, 0), reason="Python 2 only")
    def test_has_key(self):
        e = self.entry
        assert not e.has_key('xyz')
        assert e.has_key('cn')
        assert e.has_key('COMMONNAME')

    def test_in(self):
        e = self.entry
        assert 'xyz' not in e
        assert 'cn' in e
        assert 'COMMONNAME' in e

    def test_get(self):
        e = self.entry
        assert e.get('cn') == self.cn1
        assert e.get('commonname') == self.cn1
        assert e.get('COMMONNAME', 'default') == self.cn1
        assert e.get('bad key', 'default') == 'default'

    def test_single_value(self):
        e = self.entry
        assert e.single_value['cn'] == self.cn1[0]
        assert e.single_value['commonname'] == self.cn1[0]
        assert e.single_value.get('COMMONNAME', 'default') == self.cn1[0]
        assert e.single_value.get('bad key', 'default') == 'default'

    def test_sync(self):
        e = self.entry

        nice = e['test'] = [1, 2, 3]
        assert e['test'] is nice

        raw = e.raw['test']
        assert raw == [b'1', b'2', b'3']

        nice.remove(1)
        assert e.raw['test'] is raw
        assert raw == [b'2', b'3']

        raw.append(b'4')
        assert e['test'] is nice
        assert nice == [2, 3, u'4']

        nice.remove(2)
        raw.append(b'5')
        assert nice == [3, u'4']
        assert raw == [b'2', b'3', b'4', b'5']
        assert e['test'] is nice
        assert e.raw['test'] is raw
        assert nice == [3, u'4', u'5']
        assert raw == [b'3', b'4', b'5']

        nice.insert(0, 2)
        raw.remove(b'4')
        assert nice == [2, 3, u'4', u'5']
        assert raw == [b'3', b'5']
        assert e.raw['test'] is raw
        assert e['test'] is nice
        assert nice == [2, 3, u'5']
        assert raw == [b'3', b'5', b'2']

        raw = [b'a', b'b']
        e.raw['test'] = raw
        assert e['test'] is not nice
        assert e['test'] == [u'a', u'b']

        nice = 'not list'
        e['test'] = nice
        assert e['test'] is nice
        assert e.raw['test'] == [b'not list']

        e.raw['test'].append(b'second')
        assert e['test'] == ['not list', u'second']
