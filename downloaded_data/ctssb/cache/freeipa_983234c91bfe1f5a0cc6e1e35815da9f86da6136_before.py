# Authors:
#   Petr Viktorin <pviktori@redhat.com>
#
# Copyright (C) 2013  Red Hat
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

import logging
import os
import tempfile
import shutil
import glob
import contextlib
import nose
import pytest
import six

from ipalib import x509
from ipapython import ipautil
from ipaplatform.paths import paths
from ipapython.dn import DN
from ipatests.test_integration.base import IntegrationTest
from ipatests.test_integration import create_caless_pki
from ipatests.test_integration.create_external_ca import ExternalCA
from ipatests.pytest_plugins.integration import tasks
from ipalib.constants import DOMAIN_LEVEL_0

if six.PY3:
    unicode = str

logger = logging.getLogger(__name__)

_DEFAULT = object()

assert_error = tasks.assert_error

NSS_INVALID_FMT = "certutil: certificate is invalid: %s"
CERT_EXPIRED_MSG = NSS_INVALID_FMT % "Peer's Certificate has expired."
BAD_USAGE_MSG = NSS_INVALID_FMT % ("Certificate key usage inadequate for "
                                   "attempted operation.")


def get_install_stdin(cert_passwords=()):
    lines = [
        '',  # Server host name (has default)
    ]
    lines.extend(cert_passwords)  # Enter foo.p12 unlock password
    lines += [
        'yes',  # Continue with these values?
    ]
    return '\n'.join(lines + [''])


def get_replica_prepare_stdin(cert_passwords=()):
    lines = list(cert_passwords)  # Enter foo.p12 unlock password
    return '\n'.join(lines + [''])


def ipa_certs_cleanup(host):
    host.run_command(['certutil', '-d', paths.NSS_DB_DIR, '-D',
                      '-n', 'External CA cert'],
                     raiseonerr=False)
    # A workaround for https://fedorahosted.org/freeipa/ticket/4639
    result = host.run_command(['certutil', '-L', '-d',
                               paths.HTTPD_ALIAS_DIR], raiseonerr=False)
    for rawcert in result.stdout_text.split('\n')[4: -1]:
        cert = rawcert.split('    ')[0]
        host.run_command(['certutil', '-D', '-d', paths.HTTPD_ALIAS_DIR,
                          '-n', cert], raiseonerr=False)


def server_install_teardown(func):
    def wrapped(*args):
        master = args[0].master
        try:
            func(*args)
        finally:
            tasks.uninstall_master(master, clean=False)
            ipa_certs_cleanup(master)
    return wrapped


def replica_install_teardown(func):
    def wrapped(*args):
        try:
            func(*args)
        finally:
            # Uninstall replica
            replica = args[0].replicas[0]
            master = args[0].master
            tasks.kinit_admin(master)
            tasks.uninstall_master(replica, clean=False)
            # Now let's uninstall client for the cases when client promotion
            # was not successful
            tasks.uninstall_client(replica)
            tasks.clean_replication_agreement(master, replica, cleanup=True,
                                              raiseonerr=False)
            master.run_command(['ipa', 'host-del',
                                replica.hostname],
                               raiseonerr=False)
            ipa_certs_cleanup(replica)
    return wrapped


class CALessBase(IntegrationTest):
    @classmethod
    def install(cls, mh):
        cls.cert_dir = tempfile.mkdtemp(prefix="ipatest-")
        cls.pem_filename = os.path.join(cls.cert_dir, 'root.pem')
        cls.cert_password = cls.master.config.admin_password
        cls.crl_path = os.path.join(cls.master.config.test_dir, 'crl')

        if cls.replicas:
            replica_hostname = cls.replicas[0].hostname
        else:
            replica_hostname = 'unused-replica.test'
        if cls.clients:
            client_hostname = cls.clients[0].hostname
        else:
            client_hostname = 'unused-client.test'

        create_caless_pki.domain = unicode(cls.master.domain.name)
        create_caless_pki.realm = unicode(cls.master.domain.name.upper())
        create_caless_pki.server1 = unicode(cls.master.hostname)
        create_caless_pki.server2 = unicode(replica_hostname)
        create_caless_pki.client = unicode(client_hostname)
        create_caless_pki.password = unicode(cls.master.config.dirman_password)
        create_caless_pki.cert_dir = unicode(cls.cert_dir)

        # here we generate our certificates (not yet converted to .p12)
        logger.info('Generating certificates to %s', cls.cert_dir)
        create_caless_pki.create_pki()

        for host in cls.get_all_hosts():
            tasks.apply_common_fixes(host)

            # Copy CRLs over
            host.transport.mkdir_recursive(cls.crl_path)
            for source in glob.glob(os.path.join(cls.cert_dir, '*.crl')):
                dest = os.path.join(cls.crl_path, os.path.basename(source))
                host.transport.put_file(source, dest)

    @classmethod
    def uninstall(cls, mh):
        # Remove the NSS database
        shutil.rmtree(cls.cert_dir)
        for host in cls.get_all_hosts():
            tasks.uninstall_master(host)
        super(CALessBase, cls).uninstall(mh)

    @classmethod
    def install_server(cls, host=None,
                       http_pkcs12='server.p12', dirsrv_pkcs12='server.p12',
                       http_pkcs12_exists=True, dirsrv_pkcs12_exists=True,
                       http_pin=_DEFAULT, dirsrv_pin=_DEFAULT, pkinit_pin=None,
                       root_ca_file='root.pem', pkinit_pkcs12_exists=False,
                       pkinit_pkcs12='server-kdc.p12', unattended=True,
                       stdin_text=None):
        """Install a CA-less server

        Return value is the remote ipa-server-install command
        """
        if host is None:
            host = cls.master

        extra_args = ['--http-cert-file', http_pkcs12,
                      '--dirsrv-cert-file', dirsrv_pkcs12,
                      '--ca-cert-file', root_ca_file,
                      '--ip-address', host.ip]

        if http_pin is _DEFAULT:
            http_pin = cls.cert_password
        if dirsrv_pin is _DEFAULT:
            dirsrv_pin = cls.cert_password
        if pkinit_pin is _DEFAULT:
            pkinit_pin = cls.cert_password
        tasks.prepare_host(host)
        files_to_copy = ['root.pem']
        if http_pkcs12_exists:
            files_to_copy.append(http_pkcs12)
        if dirsrv_pkcs12_exists:
            files_to_copy.append(dirsrv_pkcs12)
        if pkinit_pkcs12_exists:
            files_to_copy.append(pkinit_pkcs12)
            extra_args.extend(['--pkinit-cert-file', pkinit_pkcs12])
        else:
            extra_args.append('--no-pkinit')
        for filename in set(files_to_copy):
            cls.copy_cert(host, filename)

        # Remove existing ca certs from default database to avoid conflicts
        args = [paths.CERTUTIL, "-D", "-d", "/etc/httpd/alias", "-n"]
        host.run_command(args + ["ca1"], raiseonerr=False)
        host.run_command(args + ["ca1/server"], raiseonerr=False)

        if http_pin is not None:
            extra_args.extend(['--http-pin', http_pin])
        if dirsrv_pin is not None:
            extra_args.extend(['--dirsrv-pin', dirsrv_pin])
        if pkinit_pin is not None:
            extra_args.extend(['--pkinit-pin', dirsrv_pin])
        return tasks.install_master(host, extra_args=extra_args,
                                    unattended=unattended,
                                    stdin_text=stdin_text,
                                    raiseonerr=False)

    @classmethod
    def copy_cert(cls, host, filename):
        host.transport.put_file(os.path.join(cls.cert_dir, filename),
                                os.path.join(host.config.test_dir, filename))

    def prepare_replica(self, _replica_number=0, replica=None, master=None,
                        http_pkcs12='replica.p12', dirsrv_pkcs12='replica.p12',
                        http_pkcs12_exists=True, dirsrv_pkcs12_exists=True,
                        http_pin=_DEFAULT, dirsrv_pin=_DEFAULT,
                        pkinit_pin=None, root_ca_file='root.pem',
                        pkinit_pkcs12_exists=False,
                        pkinit_pkcs12='replica-kdc.p12', unattended=True,
                        stdin_text=None, domain_level=None):
        """Prepare a CA-less replica

        Puts the bundle file into test_dir on the replica if successful,
        otherwise ensures it is missing.

        Return value is the remote ipa-replica-prepare command
        """
        if replica is None:
            replica = self.replicas[_replica_number]
        if master is None:
            master = self.master
        if http_pin is _DEFAULT:
            http_pin = self.cert_password
        if dirsrv_pin is _DEFAULT:
            dirsrv_pin = self.cert_password
        if pkinit_pin is _DEFAULT:
            pkinit_pin = self.cert_password

        if domain_level is None:
            domain_level = tasks.domainlevel(master)
        files_to_copy = ['root.pem']
        if http_pkcs12_exists:
            files_to_copy.append(http_pkcs12)
        if dirsrv_pkcs12_exists:
            files_to_copy.append(dirsrv_pkcs12)
        if pkinit_pkcs12_exists:
            files_to_copy.append(pkinit_pkcs12)
        if domain_level == DOMAIN_LEVEL_0:
            destination_host = master
        else:
            destination_host = replica
        # Both master and replica lack ipatests folder by this time, so we need
        # to re-create it
        tasks.prepare_host(master)
        tasks.prepare_host(replica)
        for filename in set(files_to_copy):
            try:
                destination_host.transport.put_file(
                    os.path.join(self.cert_dir, filename),
                    os.path.join(destination_host.config.test_dir, filename))
            except OSError:
                pass
        extra_args = []
        if http_pkcs12_exists:
            extra_args.extend(['--http-cert-file', http_pkcs12])
        if dirsrv_pkcs12_exists:
            extra_args.extend(['--dirsrv-cert-file', dirsrv_pkcs12])
        if pkinit_pkcs12_exists and domain_level != DOMAIN_LEVEL_0:
            extra_args.extend(['--pkinit-cert-file', pkinit_pkcs12])
        else:
            extra_args.append('--no-pkinit')

        if http_pin is not None:
            extra_args.extend(['--http-pin', http_pin])
        if dirsrv_pin is not None:
            extra_args.extend(['--dirsrv-pin', dirsrv_pin])
        if pkinit_pin is not None:
            extra_args.extend(['--pkinit-pin', dirsrv_pin])

        if domain_level == DOMAIN_LEVEL_0:
            result = tasks.replica_prepare(master, replica,
                                           extra_args=extra_args,
                                           raiseonerr=False,
                                           stdin_text=stdin_text)
        else:
            result = tasks.install_replica(master, replica, setup_ca=False,
                                           extra_args=extra_args,
                                           unattended=unattended,
                                           stdin_text=stdin_text,
                                           raiseonerr=False)
        return result

    def get_replica_filename(self, replica):
        return os.path.join(replica.config.test_dir,
                            'replica-info.gpg')

    @classmethod
    def create_pkcs12(cls, nickname, filename='server.p12', password=None):
        """Create a cert chain and generate pkcs12 cert"""
        if password is None:
            password = cls.cert_password

        fname_chain = []

        key_fname = '{}.key'.format(os.path.join(cls.cert_dir, nickname))
        certchain_fname = '{}.pem'.format(os.path.join(cls.cert_dir, nickname))

        nick_chain = nickname.split('/')

        # to construct whole chain e.g "ca1 - ca1/sub - ca1/sub/server"
        for index, _value in enumerate(nick_chain):
            cert_nick = '/'.join(nick_chain[:index+1])
            cert_path = '{}.crt'.format(os.path.join(cls.cert_dir, cert_nick))
            if os.path.isfile(cert_path):
                fname_chain.append(cert_path)

        # create the chain file
        with open(certchain_fname, 'w') as chain:
            for cert_fname in fname_chain:
                with open(cert_fname) as cert:
                    chain.write(cert.read())

        ipautil.run(["openssl", "pkcs12", "-export", "-out", filename,
                     "-inkey", key_fname, "-in", certchain_fname, "-passin",
                     "pass:"+cls.cert_password, "-passout", "pass:"+password,
                     "-name", nickname], cwd=cls.cert_dir)

    @classmethod
    def prepare_cacert(cls, nickname):
        """ Prepare pem file for root_ca_file/ca-cert-file option """
        # create_caless_pki saves certificates with ".crt" extension by default
        fname_from_nick = '{}.crt'.format(os.path.join(cls.cert_dir, nickname))
        shutil.copy(fname_from_nick, cls.pem_filename)

    @classmethod
    def get_pem(cls, nickname):
        """ Return PEM cert as base64 encoded ascii for TestIPACommands """
        cacert_fname = '{}.crt'.format(os.path.join(cls.cert_dir, nickname))
        with open(cacert_fname, 'r') as f:
            return f.read()

    def verify_installation(self):
        """Verify CA cert PEM file and LDAP entry created by install

        Called from every positive server install test
        """
        with open(self.pem_filename, 'rb') as f:
            expected_cacrt = f.read()
        logger.debug('Expected /etc/ipa/ca.crt contents:\n%s',
                     expected_cacrt.decode('utf-8'))
        expected_cacrt = x509.load_unknown_x509_certificate(expected_cacrt)
        logger.debug('Expected CA cert:\n%r',
                     expected_cacrt.public_bytes(x509.Encoding.PEM))
        for host in [self.master] + self.replicas:
            # Check the LDAP entry
            ldap = host.ldap_connect()

            entry = ldap.get_entry(DN(('cn', 'CACert'), ('cn', 'ipa'),
                                      ('cn', 'etc'), host.domain.basedn))
            cert_from_ldap = entry.single_value['cACertificate']
            logger.debug('CA cert from LDAP on %s:\n%r',
                         host, cert_from_ldap.public_bytes(x509.Encoding.PEM))
            assert cert_from_ldap == expected_cacrt

            # Verify certmonger was not started
            result = host.run_command(['getcert', 'list'], raiseonerr=False)
            assert result.returncode == 0

        for host in self.get_all_hosts():
            # Check the cert PEM file
            remote_cacrt = host.get_file_contents(paths.IPA_CA_CRT)
            logger.debug('%s:/etc/ipa/ca.crt contents:\n%s',
                         host, remote_cacrt)
            cacrt = x509.load_unknown_x509_certificate(remote_cacrt)
            logger.debug('%s: Decoded /etc/ipa/ca.crt:\n%r',
                         host, cacrt.public_bytes(x509.Encoding.PEM))
            assert expected_cacrt == cacrt


class TestServerInstall(CALessBase):
    num_replicas = 0

    @server_install_teardown
    def test_nonexistent_ca_pem_file(self):
        "IPA server install with non-existent CA PEM file "

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca2')

        result = self.install_server(root_ca_file='does_not_exist')
        assert_error(result,
                     'Failed to open does_not_exist: No such file '
                     'or directory')

    @server_install_teardown
    def test_unknown_ca(self):
        "IPA server install with CA PEM file with unknown CA certificate"

        self.create_pkcs12('ca3/server')
        self.prepare_cacert('ca2')

        result = self.install_server()
        assert_error(result,
                     'The full certificate chain is not present in server.p12')

    @server_install_teardown
    def test_ca_server_cert(self):
        "IPA server install with CA PEM file with server certificate"

        self.create_pkcs12('noca')
        self.prepare_cacert('noca')

        result = self.install_server()
        assert_error(result,
                     'The full certificate chain is not present in server.p12')

    @pytest.mark.xfail(reason='Ticket N 6289')
    @server_install_teardown
    def test_ca_2_certs(self):
        "IPA server install with CA PEM file with 2 certificates"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')
        self.prepare_cacert('ca2')

        result = self.install_server()
        assert_error(result, 'root.pem contains more than one certificate')

    @server_install_teardown
    def test_nonexistent_http_pkcs12_file(self):
        "IPA server install with non-existent HTTP PKCS#12 file"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='does_not_exist',
                                     http_pkcs12_exists=False)
        assert_error(result, 'Failed to open does_not_exist')

    @server_install_teardown
    def test_nonexistent_ds_pkcs12_file(self):
        "IPA server install with non-existent DS PKCS#12 file"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca2')

        result = self.install_server(dirsrv_pkcs12='does_not_exist',
                                     dirsrv_pkcs12_exists=False)
        assert_error(result, 'Failed to open does_not_exist')

    @server_install_teardown
    def test_missing_http_password(self):
        "IPA server install with missing HTTP PKCS#12 password (unattended)"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pin=None)
        assert_error(result,
                     'ipa-server-install: error: You must specify --http-pin '
                     'with --http-cert-file')

    @server_install_teardown
    def test_missing_ds_password(self):
        "IPA server install with missing DS PKCS#12 password (unattended)"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server(dirsrv_pin=None)
        assert_error(result,
                     'ipa-server-install: error: You must specify '
                     '--dirsrv-pin with --dirsrv-cert-file')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    @server_install_teardown
    def test_incorect_http_pin(self):
        "IPA server install with incorrect HTTP PKCS#12 password"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pin='bad<pin>')
        assert_error(result, 'incorrect password for pkcs#12 file server.p12')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    @server_install_teardown
    def test_incorect_ds_pin(self):
        "IPA server install with incorrect DS PKCS#12 password"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server(dirsrv_pin='bad<pin>')
        assert_error(result, 'incorrect password for pkcs#12 file server.p12')

    @server_install_teardown
    def test_invalid_http_cn(self):
        "IPA server install with HTTP certificate with invalid CN"

        self.create_pkcs12('ca1/server-badname', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: '
                     'invalid for server %s' % self.master.hostname)

    @server_install_teardown
    def test_invalid_ds_cn(self):
        "IPA server install with DS certificate with invalid CN"

        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in dirsrv.p12 is not valid: '
                     'invalid for server %s' % self.master.hostname)

    @server_install_teardown
    def test_expired_http(self):
        "IPA server install with expired HTTP certificate"

        self.create_pkcs12('ca1/server-expired', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    @server_install_teardown
    def test_expired_ds(self):
        "IPA server install with expired DS certificate"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/server-expired', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in dirsrv.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    @server_install_teardown
    def test_http_bad_usage(self):
        "IPA server install with HTTP certificate with invalid key usage"

        self.create_pkcs12('ca1/server-badusage', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    @server_install_teardown
    def test_ds_bad_usage(self):
        "IPA server install with DS certificate with invalid key usage"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/server-badusage', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in dirsrv.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    @server_install_teardown
    def test_revoked_http(self):
        "IPA server install with revoked HTTP certificate"

        self.create_pkcs12('ca1/server-revoked', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    @server_install_teardown
    def test_revoked_ds(self):
        "IPA server install with revoked DS certificate"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/server-revoked', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    @server_install_teardown
    def test_http_intermediate_ca(self):
        "IPA server install with HTTP certificate issued by intermediate CA"

        self.create_pkcs12('ca1/subca/server', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result, 'Apache Server SSL certificate and'
                             ' Directory Server SSL certificate are not'
                             ' signed by the same CA certificate')

    @server_install_teardown
    def test_ds_intermediate_ca(self):
        "IPA server install with DS certificate issued by intermediate CA"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/subca/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'Apache Server SSL certificate and Directory Server SSL'
                     ' certificate are not signed by the same CA certificate')

    @server_install_teardown
    def test_ca_self_signed(self):
        "IPA server install with self-signed certificate"

        self.create_pkcs12('server-selfsign')
        self.prepare_cacert('server-selfsign')

        result = self.install_server()
        assert result.returncode > 0

    @server_install_teardown
    def test_valid_certs(self):
        "IPA server install with valid certificates"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server()
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_wildcard_http(self):
        "IPA server install with wildcard HTTP certificate"

        self.create_pkcs12('ca1/wildcard', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_wildcard_ds(self):
        "IPA server install with wildcard DS certificate"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/wildcard', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_http_san(self):
        "IPA server install with HTTP certificate with SAN"

        self.create_pkcs12('ca1/server-altname', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_ds_san(self):
        "IPA server install with DS certificate with SAN"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/server-altname', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_interactive_missing_http_pkcs_password(self):
        "IPA server install with prompt for HTTP PKCS#12 password"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        stdin_text = get_install_stdin(cert_passwords=[self.cert_password])

        result = self.install_server(http_pin=None, unattended=False,
                                     stdin_text=stdin_text)
        assert result.returncode == 0
        self.verify_installation()
        assert ('Enter Apache Server private key unlock password'
                in result.stdout_text), result.stdout_text

    @server_install_teardown
    def test_interactive_missing_ds_pkcs_password(self):
        "IPA server install with prompt for DS PKCS#12 password"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        stdin_text = get_install_stdin(cert_passwords=[self.cert_password])

        result = self.install_server(dirsrv_pin=None, unattended=False,
                                     stdin_text=stdin_text)
        assert result.returncode == 0
        self.verify_installation()
        assert ('Enter Directory Server private key unlock password'
                in result.stdout_text), result.stdout_text

    @server_install_teardown
    def test_no_http_password(self):
        "IPA server install with empty HTTP password"

        self.create_pkcs12('ca1/server', filename='http.p12', password='')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12',
                                     http_pin='')
        assert result.returncode == 0
        self.verify_installation()

    @server_install_teardown
    def test_no_ds_password(self):
        "IPA server install with empty DS password"

        self.create_pkcs12('ca1/server', filename='http.p12')
        self.create_pkcs12('ca1/server', filename='dirsrv.p12', password='')
        self.prepare_cacert('ca1')

        result = self.install_server(http_pkcs12='http.p12',
                                     dirsrv_pkcs12='dirsrv.p12',
                                     dirsrv_pin='')
        assert result.returncode == 0
        self.verify_installation()


class TestReplicaInstall(CALessBase):
    num_replicas = 1

    @classmethod
    def install(cls, mh):
        super(TestReplicaInstall, cls).install(mh)
        cls.create_pkcs12('ca1/server')
        cls.prepare_cacert('ca1')
        result = cls.install_server()
        assert result.returncode == 0

    @replica_install_teardown
    def test_no_certs(self):
        "IPA replica install without certificates"
        result = self.prepare_replica(http_pkcs12_exists=False,
                                      dirsrv_pkcs12_exists=False)
        assert_error(result, "Cannot issue certificates: a CA is not "
                             "installed. Use the --http-cert-file, "
                             "--dirsrv-cert-file options to provide "
                             "custom certificates.")

    @replica_install_teardown
    def test_nonexistent_http_pkcs12_file(self):
        "IPA replica install with non-existent DS PKCS#12 file"

        self.create_pkcs12('ca1/replica', filename='http.p12')

        result = self.prepare_replica(dirsrv_pkcs12='does_not_exist',
                                      http_pkcs12='http.p12')
        assert_error(result, 'Failed to open does_not_exist')

    @replica_install_teardown
    def test_nonexistent_ds_pkcs12_file(self):
        "IPA replica install with non-existent HTTP PKCS#12 file"

        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='does_not_exist',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result, 'Failed to open does_not_exist')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    @replica_install_teardown
    def test_incorect_http_pin(self):
        "IPA replica install with incorrect HTTP PKCS#12 password"

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        result = self.prepare_replica(http_pin='bad<pin>')
        assert result.returncode > 0
        assert_error(result, 'incorrect password for pkcs#12 file replica.p12')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    @replica_install_teardown
    def test_incorect_ds_pin(self):
        "IPA replica install with incorrect DS PKCS#12 password"

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        result = self.prepare_replica(dirsrv_pin='bad<pin>')
        assert_error(result, 'incorrect password for pkcs#12 file replica.p12')

    @replica_install_teardown
    def test_http_unknown_ca(self):
        "IPA replica install with HTTP certificate issued by unknown CA"

        self.create_pkcs12('ca2/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result, 'Apache Server SSL certificate and'
                             ' Directory Server SSL certificate are not'
                             ' signed by the same CA certificate')

    @replica_install_teardown
    def test_ds_unknown_ca(self):
        "IPA replica install with DS certificate issued by unknown CA"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca2/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'Apache Server SSL certificate and Directory Server SSL'
                     ' certificate are not signed by the same CA certificate')

    @replica_install_teardown
    def test_invalid_http_cn(self):
        "IPA replica install with HTTP certificate with invalid CN"

        self.create_pkcs12('ca1/replica-badname', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: '
                     'invalid for server %s' % self.replicas[0].hostname)

    @replica_install_teardown
    def test_invalid_ds_cn(self):
        "IPA replica install with DS certificate with invalid CN"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica-badname', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in dirsrv.p12 is not valid: '
                     'invalid for server %s' % self.replicas[0].hostname)

    @replica_install_teardown
    def test_expired_http(self):
        "IPA replica install with expired HTTP certificate"

        self.create_pkcs12('ca1/replica-expired', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    @replica_install_teardown
    def test_expired_ds(self):
        "IPA replica install with expired DS certificate"

        self.create_pkcs12('ca1/replica-expired', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    @replica_install_teardown
    def test_http_bad_usage(self):
        "IPA replica install with HTTP certificate with invalid key usage"

        self.create_pkcs12('ca1/replica-badusage', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in http.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    @replica_install_teardown
    def test_ds_bad_usage(self):
        "IPA replica install with DS certificate with invalid key usage"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica-badusage', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'The server certificate in dirsrv.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    @replica_install_teardown
    def test_revoked_http(self):
        "IPA replica install with revoked HTTP certificate"

        self.create_pkcs12('ca1/replica-revoked', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    @replica_install_teardown
    def test_revoked_ds(self):
        "IPA replica install with revoked DS certificate"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica-revoked', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    @replica_install_teardown
    def test_http_intermediate_ca(self):
        "IPA replica install with HTTP certificate issued by intermediate CA"

        self.create_pkcs12('ca1/subca/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result,
                     'Apache Server SSL certificate and Directory Server SSL'
                     ' certificate are not signed by the same CA certificate')

    @replica_install_teardown
    def test_ds_intermediate_ca(self):
        "IPA replica install with DS certificate issued by intermediate CA"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/subca/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert_error(result, 'Apache Server SSL certificate and'
                             ' Directory Server SSL certificate are not'
                             ' signed by the same CA certificate')

    @replica_install_teardown
    def test_valid_certs(self):
        "IPA replica install with valid certificates"

        self.create_pkcs12('ca1/replica', filename='server.p12')

        result = self.prepare_replica(http_pkcs12='server.p12',
                                      dirsrv_pkcs12='server.p12')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_wildcard_http(self):
        "IPA replica install with wildcard HTTP certificate"

        self.create_pkcs12('ca1/wildcard', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_wildcard_ds(self):
        "IPA replica install with wildcard DS certificate"

        self.create_pkcs12('ca1/wildcard', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_http_san(self):
        "IPA replica install with HTTP certificate with SAN"

        self.create_pkcs12('ca1/replica-altname', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_ds_san(self):
        "IPA replica install with DS certificate with SAN"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica-altname', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_interactive_missing_http_pkcs_password(self):
        "IPA replica install with missing HTTP PKCS#12 password"

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        stdin_text = get_replica_prepare_stdin(
            cert_passwords=[self.cert_password])

        result = self.prepare_replica(http_pin=None, unattended=False,
                                      stdin_text=stdin_text)
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_interactive_missing_ds_pkcs_password(self):
        "IPA replica install with missing DS PKCS#12 password"

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        stdin_text = get_replica_prepare_stdin(
            cert_passwords=[self.cert_password])

        result = self.prepare_replica(dirsrv_pin=None, unattended=False,
                                      stdin_text=stdin_text)
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_no_http_password(self):
        "IPA replica install with empty HTTP password"

        self.create_pkcs12('ca1/replica', filename='http.p12', password='')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12',
                                      http_pin='')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()

    @replica_install_teardown
    def test_no_ds_password(self):
        "IPA replica install with empty DS password"

        self.create_pkcs12('ca1/replica', filename='http.p12')
        self.create_pkcs12('ca1/replica', filename='dirsrv.p12', password='')

        result = self.prepare_replica(http_pkcs12='http.p12',
                                      dirsrv_pkcs12='dirsrv.p12',
                                      dirsrv_pin='')
        assert result.returncode == 0
        if self.domain_level > DOMAIN_LEVEL_0:
            self.verify_installation()


class TestClientInstall(CALessBase):
    num_clients = 1

    def test_client_install(self):
        "IPA client install"

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        result = self.install_server()
        assert result.returncode == 0

        self.clients[0].run_command(['ipa-client-install',
                                     '--domain', self.master.domain.name,
                                     '--server', self.master.hostname,
                                     '-p', self.master.config.admin_name,
                                     '-w', self.master.config.admin_password,
                                     '-U'])

        self.verify_installation()


class TestIPACommands(CALessBase):
    @classmethod
    def install(cls, mh):
        super(TestIPACommands, cls).install(mh)

        cls.create_pkcs12('ca1/server')
        cls.prepare_cacert('ca1')

        result = cls.install_server()
        assert result.returncode == 0

        tasks.kinit_admin(cls.master)

        cls.client_pem = ''.join(cls.get_pem('ca1/client').splitlines()[1:-1])
        logger.debug('Client PEM:\n%r', cls.client_pem)
        cls.test_hostname = 'testhost.%s' % cls.master.domain.name
        cls.test_service = 'test/%s' % cls.test_hostname

    def check_ipa_command_not_available(self, command):
        "Verify that the given IPA subcommand is not available"

        result = self.master.run_command(['ipa', command], raiseonerr=False)
        assert_error(result, "ipa: ERROR: unknown command '%s'" % command)

    @contextlib.contextmanager
    def host(self):
        "Context manager that adds and removes a host entry with a certificate"
        self.master.run_command(['ipa', 'host-add', self.test_hostname,
                                 '--force',
                                 '--certificate', self.client_pem])
        self.master.run_command(['ipa-getkeytab', '-s', self.master.hostname,
                                 '-p' "host/%s" % self.test_hostname,
                                 '-k', paths.HTTP_KEYTAB])
        try:
            yield
        finally:
            self.master.run_command(['ipa', 'host-del', self.test_hostname],
                                    raiseonerr=False)

    @contextlib.contextmanager
    def service(self):
        "Context manager that adds and removes host & service entries"
        with self.host():
            self.master.run_command(['ipa', 'service-add', self.test_service,
                                     '--force',
                                     '--certificate', self.client_pem])
            self.master.run_command(['ipa-getkeytab', '-s',
                                     self.master.hostname,
                                     '-p', self.test_service,
                                     '-k', paths.HTTP_KEYTAB])
            yield

    def test_service_mod_doesnt_revoke(self):
        "Verify that service-mod does not attempt to revoke certificate"
        with self.service():
            self.master.run_command(['ipa', 'service-mod', self.test_service,
                                     '--certificate='])

    def test_service_disable_doesnt_revoke(self):
        "Verify that service-disable does not attempt to revoke certificate"
        with self.service():
            result = self.master.run_command(['ipa', 'service-disable',
                                              self.test_service],
                                             raiseonerr=False)
            assert(result.returncode == 0), (
                "Failed to disable ipa-service: %s" % result.stderr_text)

    def test_service_del_doesnt_revoke(self):
        "Verify that service-del does not attempt to revoke certificate"
        with self.service():
            self.master.run_command(['ipa', 'service-del', self.test_service])

    def test_host_mod_doesnt_revoke(self):
        "Verify that host-mod does not attempt to revoke host's certificate"
        with self.host():
            self.master.run_command(['ipa', 'host-mod', self.test_hostname,
                                     '--certificate='])

    def test_host_disable_doesnt_revoke(self):
        "Verify that host-disable does not attempt to revoke host certificate"
        with self.host():
            self.master.run_command(['ipa', 'host-disable',
                                     self.test_hostname])

    def test_host_del_doesnt_revoke(self):
        "Verify that host-del does not attempt to revoke host's certificate"
        with self.host():
            self.master.run_command(['ipa', 'host-del', self.test_hostname])


class TestCertInstall(CALessBase):
    @classmethod
    def install(cls, mh):
        super(TestCertInstall, cls).install(mh)

        cls.create_pkcs12('ca1/server')
        cls.prepare_cacert('ca1')

        result = cls.install_server()
        assert result.returncode == 0

        tasks.kinit_admin(cls.master)

    def certinstall(self, mode, cert_nick=None, cert_exists=True,
                    filename='server.p12', pin=_DEFAULT, stdin_text=None,
                    p12_pin=None, args=None):
        if cert_nick:
            self.create_pkcs12(cert_nick, password=p12_pin)
        if pin is _DEFAULT:
            pin = self.cert_password
        if cert_exists:
            self.copy_cert(self.master, filename)
        if not args:
            args = ['ipa-server-certinstall',
                    '-p', self.master.config.dirman_password,
                    '-%s' % mode, filename]
            if pin is not None:
                args += ['--pin', pin]
        return self.master.run_command(args,
                                       raiseonerr=False,
                                       stdin_text=stdin_text)

    def test_nonexistent_http_pkcs12_file(self):
        "Install new HTTP certificate from non-existent PKCS#12 file"

        result = self.certinstall('w', filename='does_not_exist', pin='none',
                                  cert_exists=False)
        assert_error(result, 'Failed to open does_not_exist')

    def test_nonexistent_ds_pkcs12_file(self):
        "Install new DS certificate from non-existent PKCS#12 file"

        result = self.certinstall('d', filename='does_not_exist', pin='none',
                                  cert_exists=False)
        assert_error(result, 'Failed to open does_not_exist')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    def test_incorect_http_pin(self):
        "Install new HTTP certificate with incorrect PKCS#12 password"

        result = self.certinstall('w', 'ca1/server', pin='bad<pin>')
        assert_error(result,
                     'incorrect password for pkcs#12 file server.p12')

    @pytest.mark.xfail(reason='freeipa ticket 5378')
    def test_incorect_dirsrv_pin(self):
        "Install new DS certificate with incorrect PKCS#12 password"

        result = self.certinstall('d', 'ca1/server', pin='bad<pin>')
        assert_error(result,
                     'incorrect password for pkcs#12 file server.p12')

    def test_invalid_http_cn(self):
        "Install new HTTP certificate with invalid CN "

        result = self.certinstall('w', 'ca1/server-badname')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: '
                     'invalid for server %s' % self.master.hostname)

    def test_invalid_ds_cn(self):
        "Install new DS certificate with invalid CN "

        result = self.certinstall('d', 'ca1/server-badname')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: '
                     'invalid for server %s' % self.master.hostname)

    def test_expired_http(self):
        "Install new expired HTTP certificate"

        result = self.certinstall('w', 'ca1/server-expired')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    def test_expired_ds(self):
        "Install new expired DS certificate"

        result = self.certinstall('d', 'ca1/server-expired')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: {err}'
                     .format(err=CERT_EXPIRED_MSG))

    def test_http_bad_usage(self):
        "Install new HTTP certificate with invalid key usage"

        result = self.certinstall('w', 'ca1/server-badusage')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    def test_ds_bad_usage(self):
        "Install new DS certificate with invalid key usage"

        result = self.certinstall('d', 'ca1/server-badusage')
        assert_error(result,
                     'The server certificate in server.p12 is not valid: {err}'
                     .format(err=BAD_USAGE_MSG))

    def test_revoked_http(self):
        "Install new revoked HTTP certificate"

        result = self.certinstall('w', 'ca1/server-revoked')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    def test_revoked_ds(self):
        "Install new revoked DS certificate"

        result = self.certinstall('d', 'ca1/server-revoked')

        if result.returncode == 0:
            raise nose.SkipTest(
                "Known CA-less installation defect, see "
                "https://fedorahosted.org/freeipa/ticket/4270")

        assert result.returncode > 0

    @pytest.mark.xfail(reason='freeipa ticket 6959')
    def test_http_intermediate_ca(self):
        "Install new HTTP certificate issued by intermediate CA"

        result = self.certinstall('w', 'ca1/subca/server')
        assert result.returncode == 0, result.stderr_text

    @pytest.mark.xfail(reason='freeipa ticket 6959')
    def test_ds_intermediate_ca(self):
        "Install new DS certificate issued by intermediate CA"

        result = self.certinstall('d', 'ca1/subca/server')
        assert result.returncode == 0, result.stderr_text

    def test_self_signed(self):
        "Install new self-signed certificate"

        result = self.certinstall('w', 'server-selfsign')
        assert_error(result,
                     'The full certificate chain is not present in server.p12')

    def test_valid_http(self):
        "Install new valid HTTP certificate"

        result = self.certinstall('w', 'ca1/server')
        assert result.returncode == 0

    def test_valid_ds(self):
        "Install new valid DS certificate"

        result = self.certinstall('d', 'ca1/server')
        assert result.returncode == 0

    def test_wildcard_http(self):
        "Install new wildcard HTTP certificate"

        result = self.certinstall('w', 'ca1/wildcard')
        assert result.returncode == 0

    def test_wildcard_ds(self):
        "Install new wildcard DS certificate"

        result = self.certinstall('d', 'ca1/wildcard')
        assert result.returncode == 0

    def test_http_san(self):
        "Install new HTTP certificate with SAN"

        result = self.certinstall('w', 'ca1/server-altname')
        assert result.returncode == 0

    def test_ds_san(self):
        "Install new DS certificate with SAN"

        result = self.certinstall('d', 'ca1/server-altname')
        assert result.returncode == 0

    def test_interactive_missing_http_pkcs_password(self):
        "Install new HTTP certificate with missing PKCS#12 password"

        result = self.certinstall('w', 'ca1/server',
                                  pin=None,
                                  stdin_text=self.cert_password + '\n')
        assert result.returncode == 0

    def test_interactive_missing_ds_pkcs_password(self):
        "Install new DS certificate with missing PKCS#12 password"

        result = self.certinstall('d', 'ca1/server',
                                  pin=None,
                                  stdin_text=self.cert_password + '\n')
        assert result.returncode == 0

    def test_no_http_password(self):
        "Install new HTTP certificate with no PKCS#12 password"

        result = self.certinstall('w', 'ca1/server', pin='', p12_pin='')
        assert result.returncode == 0

    def test_no_ds_password(self):
        "Install new DS certificate with no PKCS#12 password"

        result = self.certinstall('d', 'ca1/server', pin='', p12_pin='')
        assert result.returncode == 0

    def test_http_old_options(self):
        "Install new valid DS certificate using pre-v3.3 CLI options"
        # http://www.freeipa.org/page/V3/ipa-server-certinstall_CLI_cleanup

        args = ['ipa-server-certinstall',
                '-w', 'server.p12',
                '--http-pin', self.cert_password]

        result = self.certinstall('w', 'ca1/server', args=args)
        assert_error(result, "no such option: --http-pin")

    def test_ds_old_options(self):
        "Install new valid DS certificate using pre-v3.3 CLI options"
        # http://www.freeipa.org/page/V3/ipa-server-certinstall_CLI_cleanup

        args = ['ipa-server-certinstall',
                '-d', 'server.p12',
                '--dirsrv-pin', self.cert_password]
        stdin_text = self.master.config.dirman_password + '\n'

        result = self.certinstall('d', 'ca1/server',
                                  args=args, stdin_text=stdin_text)
        assert_error(result, "no such option: --dirsrv-pin")


class TestPKINIT(CALessBase):
    """Install master and replica with PKINIT"""
    num_replicas = 1

    @classmethod
    def install(cls, mh):
        super(TestPKINIT, cls).install(mh)
        cls.create_pkcs12('ca1/server')
        cls.create_pkcs12('ca1/server-kdc', filename='server-kdc.p12')
        cls.prepare_cacert('ca1')
        result = cls.install_server(pkinit_pkcs12_exists=True,
                                    pkinit_pin=_DEFAULT)
        assert result.returncode == 0

    @replica_install_teardown
    def test_server_replica_install_pkinit(self):
        self.create_pkcs12('ca1/replica', filename='replica.p12')
        self.create_pkcs12('ca1/replica-kdc', filename='replica-kdc.p12')
        result = self.prepare_replica(pkinit_pkcs12_exists=True,
                                      pkinit_pin=_DEFAULT)
        assert result.returncode == 0
        self.verify_installation()


class TestServerReplicaCALessToCAFull(CALessBase):
    """
    Test server and replica caless to cafull scenario:
    Master (caless) / replica (caless) >> master (ca) / replica (ca)
    """
    num_replicas = 1

    def test_install_caless_server_replica(self):
        """Install CA-less master and replica"""

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        master = self.install_server()
        assert master.returncode == 0

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        replica = self.prepare_replica()
        assert replica.returncode == 0

    def test_server_ipa_ca_install(self):
        """Install CA on master"""

        ca_master = tasks.install_ca(self.master)
        assert ca_master.returncode == 0
        cert_update_master = self.master.run_command(['ipa-certupdate'])
        assert cert_update_master.returncode == 0
        cert_update_replica = self.replicas[0].run_command(['ipa-certupdate'])
        assert cert_update_replica.returncode == 0

    def test_replica_ipa_ca_install(self):
        """Install CA on replica"""

        ca_replica = tasks.install_ca(self.replicas[0])
        assert ca_replica.returncode == 0


class TestReplicaCALessToCAFull(CALessBase):
    """
    Test replica caless to cafull when master stays caless scenario:
    Master (caless) / replica (caless) >> replica (ca)
    """
    num_replicas = 1

    def test_install_caless_server_replica(self):
        """Install CA-less master and replica"""

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        master = self.install_server()
        assert master.returncode == 0

        self.create_pkcs12('ca1/replica', filename='replica.p12')

        replica = self.prepare_replica()
        assert replica.returncode == 0

    def test_replica_ipa_ca_install(self):
        """Install CA on replica (master caless)"""

        ca_replica = tasks.install_ca(self.replicas[0])
        assert ca_replica.returncode == 0


class TestServerCALessToExternalCA(CALessBase):
    """Test server caless to extarnal CA scenario"""

    def test_install_caless_server(self):
        """Install CA-less master"""

        self.create_pkcs12('ca1/server')
        self.prepare_cacert('ca1')

        master = self.install_server()
        assert master.returncode == 0

    def test_server_ipa_ca_install_external(self):
        """Install external CA on master"""

        # First step of ipa-ca-install (get CSR)
        ca_master_pre = tasks.install_ca(self.master, external_ca=True)
        assert ca_master_pre.returncode == 0

        # Create external CA
        external_ca = ExternalCA()
        root_ca = external_ca.create_ca()

        # Get IPA CSR as string
        ipa_csr = self.master.get_file_contents('/root/ipa.csr')
        # Have CSR signed by the external CA
        ipa_ca = external_ca.sign_csr(ipa_csr)

        test_dir = self.master.config.test_dir

        root_ca_fname = os.path.join(test_dir, 'root_ca.crt')
        ipa_ca_fname = os.path.join(test_dir, 'ipa_ca.crt')

        # Transport certificates (string > file) to master
        self.master.put_file_contents(root_ca_fname, root_ca)
        self.master.put_file_contents(ipa_ca_fname, ipa_ca)

        cert_files = [root_ca_fname, ipa_ca_fname]

        # Continue with ipa-ca-install
        ca_master_post = tasks.install_ca(self.master, cert_files=cert_files)
        assert ca_master_post.returncode == 0
