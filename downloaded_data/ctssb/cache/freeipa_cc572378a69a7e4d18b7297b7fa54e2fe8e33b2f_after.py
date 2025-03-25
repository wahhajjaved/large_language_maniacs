# Authors: Karl MacMillan <kmacmillan@mentalrootkit.com>
#
# Copyright (C) 2007  Red Hat
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
#

import os
import stat
import sys
import tempfile
import shutil
import xml.dom.minidom
import grp
import pwd
import base64
import fcntl
import time
import datetime

import six
from six.moves import configparser

from ipalib.install import certmonger, sysrestore
from ipapython.ipa_log_manager import root_logger
from ipapython import dogtag
from ipapython import ipautil
from ipapython.certdb import EMPTY_TRUST_FLAGS, IPA_CA_TRUST_FLAGS
from ipapython.certdb import get_ca_nickname, find_cert_from_txt, NSSDatabase
from ipapython.dn import DN
from ipalib import pkcs10, x509, api
from ipalib.errors import CertificateOperationError
from ipalib.text import _
from ipaplatform.paths import paths


def get_cert_nickname(cert):
    """
    Using the subject from cert come up with a nickname suitable
    for NSS. The caller can decide whether to use just the RDN
    or the whole subject.

    Returns a tuple of (rdn, subject_dn) when rdn is the string
    representation of the first RDN in the subject and subject_dn
    is a DN object.
    """
    cert_obj = x509.load_certificate(cert)
    dn = DN(cert_obj.subject)

    return (str(dn[0]), dn)


def install_pem_from_p12(p12_fname, p12_passwd, pem_fname):
    pwd = ipautil.write_tmp_file(p12_passwd)
    ipautil.run([paths.OPENSSL, "pkcs12", "-nokeys", "-clcerts",
                 "-in", p12_fname, "-out", pem_fname,
                 "-passin", "file:" + pwd.name])


def install_key_from_p12(p12_fname, p12_passwd, pem_fname):
    pwd = ipautil.write_tmp_file(p12_passwd)
    ipautil.run([paths.OPENSSL, "pkcs12", "-nodes", "-nocerts",
                 "-in", p12_fname, "-out", pem_fname,
                 "-passin", "file:" + pwd.name],
                umask=0o077)


def export_pem_p12(pkcs12_fname, pkcs12_pwd_fname, nickname, pem_fname):
    ipautil.run([paths.OPENSSL, "pkcs12",
                 "-export", "-name", nickname,
                 "-in", pem_fname, "-out", pkcs12_fname,
                 "-passout", "file:" + pkcs12_pwd_fname])


class CertDB(object):
    """An IPA-server-specific wrapper around NSS

    This class knows IPA-specific details such as nssdir location, or the
    CA cert name.

    ``subject_base``
      Realm subject base DN.  This argument is required when creating
      server or object signing certs.
    ``ca_subject``
      IPA CA subject DN.  This argument is required when importing
      CA certificates into the certificate database.

    """
    # TODO: Remove all selfsign code
    def __init__(self, realm, nssdir, fstore=None,
                 host_name=None, subject_base=None, ca_subject=None,
                 user=None, group=None, mode=None, create=False):
        self.nssdb = NSSDatabase(nssdir)

        self.secdir = nssdir
        self.realm = realm

        self.noise_fname = self.secdir + "/noise.txt"
        self.certdb_fname = self.secdir + "/cert8.db"
        self.keydb_fname = self.secdir + "/key3.db"
        self.secmod_fname = self.secdir + "/secmod.db"
        self.pk12_fname = self.secdir + "/cacert.p12"
        self.pin_fname = self.secdir + "/pin.txt"
        self.reqdir = None
        self.certreq_fname = None
        self.certder_fname = None
        self.host_name = host_name
        self.ca_subject = ca_subject
        self.subject_base = subject_base

        try:
            self.cwd = os.path.abspath(os.getcwd())
        except OSError as e:
            raise RuntimeError(
                "Unable to determine the current directory: %s" % str(e))

        self.cacert_name = get_ca_nickname(self.realm)

        self.user = user
        self.group = group
        self.mode = mode
        self.uid = 0
        self.gid = 0

        if not create:
            if os.path.isdir(self.secdir):
                # We are going to set the owner of all of the cert
                # files to the owner of the containing directory
                # instead of that of the process. This works when
                # this is called by root for a daemon that runs as
                # a normal user
                mode = os.stat(self.secdir)
                self.uid = mode[stat.ST_UID]
                self.gid = mode[stat.ST_GID]
        else:
            if user is not None:
                pu = pwd.getpwnam(user)
                self.uid = pu.pw_uid
                self.gid = pu.pw_gid
            if group is not None:
                self.gid = grp.getgrnam(group).gr_gid
            self.create_certdbs()

        if fstore:
            self.fstore = fstore
        else:
            self.fstore = sysrestore.FileStore(paths.SYSRESTORE)

    ca_subject = ipautil.dn_attribute_property('_ca_subject')
    subject_base = ipautil.dn_attribute_property('_subject_base')

    @property
    def passwd_fname(self):
        return self.nssdb.pwd_file

    def exists(self):
        """
        Checks whether all NSS database files + our pwd_file exist
        """
        db_files = (
            self.secdir,
            self.certdb_fname,
            self.keydb_fname,
            self.secmod_fname,
            self.nssdb.pwd_file,
        )

        for f in db_files:
            if not os.path.exists(f):
                return False
        return True

    def __del__(self):
        if self.reqdir is not None:
            shutil.rmtree(self.reqdir, ignore_errors=True)
            self.reqdir = None
        self.nssdb.close()
        try:
            os.chdir(self.cwd)
        except OSError:
            pass

    def setup_cert_request(self):
        """
        Create a temporary directory to store certificate requests and
        certificates. This should be called before requesting certificates.

        This is set outside of __init__ to avoid creating a temporary
        directory every time we open a cert DB.
        """
        if self.reqdir is not None:
            return

        self.reqdir = tempfile.mkdtemp('', 'ipa-', paths.VAR_LIB_IPA)
        self.certreq_fname = self.reqdir + "/tmpcertreq"
        self.certder_fname = self.reqdir + "/tmpcert.der"

        # When certutil makes a request it creates a file in the cwd, make
        # sure we are in a unique place when this happens
        os.chdir(self.reqdir)

    def set_perms(self, fname, write=False):
        perms = stat.S_IRUSR
        if write:
            perms |= stat.S_IWUSR
        if hasattr(fname, 'fileno'):
            os.fchown(fname.fileno(), self.uid, self.gid)
            os.fchmod(fname.fileno(), perms)
        else:
            os.chown(fname, self.uid, self.gid)
            os.chmod(fname, perms)

    def run_certutil(self, args, stdin=None, **kwargs):
        return self.nssdb.run_certutil(args, stdin, **kwargs)

    def run_signtool(self, args, stdin=None):
        with open(self.passwd_fname, "r") as f:
            password = f.readline()
        new_args = [paths.SIGNTOOL, "-d", self.secdir, "-p", password]

        new_args = new_args + args
        ipautil.run(new_args, stdin)

    def create_noise_file(self):
        if ipautil.file_exists(self.noise_fname):
            os.remove(self.noise_fname)
        with open(self.noise_fname, "w") as f:
            self.set_perms(f)
            f.write(ipautil.ipa_generate_password())

    def create_passwd_file(self, passwd=None):
        ipautil.backup_file(self.passwd_fname)
        with open(self.passwd_fname, "w") as f:
            self.set_perms(f)
            if passwd is not None:
                f.write("%s\n" % passwd)
            else:
                f.write(ipautil.ipa_generate_password())

    def create_certdbs(self):
        self.nssdb.create_db(user=self.user, group=self.group, mode=self.mode,
                             backup=True)
        self.set_perms(self.passwd_fname, write=True)

    def restore(self):
        self.nssdb.restore()

    def list_certs(self):
        """
        Return a tuple of tuples containing (nickname, trust)
        """
        return self.nssdb.list_certs()

    def has_nickname(self, nickname):
        """
        Returns True if nickname exists in the certdb, False otherwise.

        This could also be done directly with:
            certutil -L -d -n <nickname> ...
        """

        certs = self.list_certs()

        for cert in certs:
            if nickname == cert[0]:
                return True

        return False

    def export_ca_cert(self, nickname, create_pkcs12=False):
        """create_pkcs12 tells us whether we should create a PKCS#12 file
           of the CA or not. If we are running on a replica then we won't
           have the private key to make a PKCS#12 file so we don't need to
           do that step."""
        cacert_fname = paths.IPA_CA_CRT
        # export the CA cert for use with other apps
        ipautil.backup_file(cacert_fname)
        root_nicknames = self.find_root_cert(nickname)[:-1]
        with open(cacert_fname, "w") as f:
            os.fchmod(f.fileno(), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            for root in root_nicknames:
                result = self.run_certutil(["-L", "-n", root, "-a"],
                                           capture_output=True)
                f.write(result.output)

        if create_pkcs12:
            ipautil.backup_file(self.pk12_fname)
            ipautil.run([paths.PK12UTIL, "-d", self.secdir,
                         "-o", self.pk12_fname,
                         "-n", self.cacert_name,
                         "-w", self.passwd_fname,
                         "-k", self.passwd_fname])
            self.set_perms(self.pk12_fname)

    def load_cacert(self, cacert_fname, trust_flags):
        """
        Load all the certificates from a given file. It is assumed that
        this file creates CA certificates.
        """
        with open(cacert_fname) as f:
            certs = f.read()

        st = 0
        while True:
            try:
                (cert, st) = find_cert_from_txt(certs, st)
                _rdn, subject_dn = get_cert_nickname(cert)
                if subject_dn == self.ca_subject:
                    nick = get_ca_nickname(self.realm)
                else:
                    nick = str(subject_dn)
                self.nssdb.add_cert(cert, nick, trust_flags, pem=True)
            except RuntimeError:
                break

    def get_cert_from_db(self, nickname, pem=True):
        """
        Retrieve a certificate from the current NSS database for nickname.

        pem controls whether the value returned PEM or DER-encoded. The
        default is the data straight from certutil -a.
        """
        try:
            args = ["-L", "-n", nickname, "-a"]
            result = self.run_certutil(args, capture_output=True)
            cert = result.output
            if pem:
                return cert
            else:
                cert, _start = find_cert_from_txt(cert, start=0)
                cert = x509.strip_header(cert)
                dercert = base64.b64decode(cert)
                return dercert
        except ipautil.CalledProcessError:
            return ''

    def track_server_cert(self, nickname, principal, password_file=None, command=None):
        """
        Tell certmonger to track the given certificate nickname.
        """
        try:
            request_id = certmonger.start_tracking(
                self.secdir, nickname=nickname, pinfile=password_file,
                post_command=command)
        except RuntimeError as e:
            root_logger.error("certmonger failed starting to track certificate: %s" % str(e))
            return

        cert = self.get_cert_from_db(nickname)
        cert_obj = x509.load_certificate(cert)
        subject = str(DN(cert_obj.subject))
        certmonger.add_principal(request_id, principal)
        certmonger.add_subject(request_id, subject)

    def untrack_server_cert(self, nickname):
        """
        Tell certmonger to stop tracking the given certificate nickname.
        """
        try:
            certmonger.stop_tracking(self.secdir, nickname=nickname)
        except RuntimeError as e:
            root_logger.error("certmonger failed to stop tracking certificate: %s" % str(e))

    def create_server_cert(self, nickname, hostname, subject=None):
        """
        If we are using a dogtag CA then other_certdb contains the RA agent key
        that will issue our cert.

        You can override the certificate Subject by specifying a subject.

        Returns a certificate in DER format.
        """
        if subject is None:
            subject=DN(('CN', hostname), self.subject_base)
        self.request_cert(subject, san_dnsnames=[hostname])
        try:
            self.issue_server_cert(self.certreq_fname, self.certder_fname)
            self.import_cert(self.certder_fname, nickname)
            with open(self.certder_fname, "r") as f:
                dercert = f.read()
        finally:
            for fname in (self.certreq_fname, self.certder_fname):
                try:
                    os.unlink(fname)
                except OSError:
                    pass

        return dercert

    def request_cert(
            self, subject, certtype="rsa", keysize="2048",
            san_dnsnames=None):
        assert isinstance(subject, DN)
        self.create_noise_file()
        self.setup_cert_request()
        args = ["-R", "-s", str(subject),
                "-o", self.certreq_fname,
                "-k", certtype,
                "-g", keysize,
                "-z", self.noise_fname,
                "-f", self.passwd_fname,
                "-a"]
        if san_dnsnames is not None and len(san_dnsnames) > 0:
            args += ['-8', ','.join(san_dnsnames)]
        result = self.run_certutil(args,
                                   capture_output=True, capture_error=True)
        os.remove(self.noise_fname)
        return (result.output, result.error_output)

    def issue_server_cert(self, certreq_fname, cert_fname):
        self.setup_cert_request()

        if self.host_name is None:
            raise RuntimeError("CA Host is not set.")

        with open(certreq_fname, "r") as f:
            csr = f.read()

        # We just want the CSR bits, make sure there is nothing else
        csr = pkcs10.strip_header(csr)

        params = {'profileId': dogtag.DEFAULT_PROFILE,
                'cert_request_type': 'pkcs10',
                'requestor_name': 'IPA Installer',
                'cert_request': csr,
                'xmlOutput': 'true'}

        # Send the request to the CA
        result = dogtag.https_request(
            self.host_name, 8443,
            url="/ca/ee/ca/profileSubmitSSLClient",
            cafile=api.env.tls_ca_cert,
            client_certfile=paths.RA_AGENT_PEM,
            client_keyfile=paths.RA_AGENT_KEY,
            **params)
        http_status, _http_headers, http_body = result
        root_logger.debug("CA answer: %s", http_body)

        if http_status != 200:
            raise CertificateOperationError(
                error=_('Unable to communicate with CMS (status %d)') % http_status)

        # The result is an XML blob. Pull the certificate out of that
        doc = xml.dom.minidom.parseString(http_body)
        item_node = doc.getElementsByTagName("b64")
        try:
            try:
                cert = item_node[0].childNodes[0].data
            except IndexError:
                raise RuntimeError("Certificate issuance failed")
        finally:
            doc.unlink()

        # base64-decode the result for uniformity
        cert = base64.b64decode(cert)

        # Write the certificate to a file. It will be imported in a later
        # step. This file will be read later to be imported.
        with open(cert_fname, "w") as f:
            f.write(cert)

    def issue_signing_cert(self, certreq_fname, cert_fname):
        self.setup_cert_request()

        if self.host_name is None:
            raise RuntimeError("CA Host is not set.")

        with open(certreq_fname, "r") as f:
            csr = f.read()

        # We just want the CSR bits, make sure there is no thing else
        csr = pkcs10.strip_header(csr)

        params = {'profileId': 'caJarSigningCert',
                'cert_request_type': 'pkcs10',
                'requestor_name': 'IPA Installer',
                'cert_request': csr,
                'xmlOutput': 'true'}

        # Send the request to the CA
        result = dogtag.https_request(
            self.host_name, 8443,
            url="/ca/ee/ca/profileSubmitSSLClient",
            cafile=api.env.tls_ca_cert,
            client_certfile=paths.RA_AGENT_PEM,
            client_keyfile=paths.RA_AGENT_KEY,
            **params)
        http_status, _http_headers, http_body = result
        if http_status != 200:
            raise RuntimeError("Unable to submit cert request")

        # The result is an XML blob. Pull the certificate out of that
        doc = xml.dom.minidom.parseString(http_body)
        item_node = doc.getElementsByTagName("b64")
        cert = item_node[0].childNodes[0].data
        doc.unlink()

        # base64-decode the cert for uniformity
        cert = base64.b64decode(cert)

        # Write the certificate to a file. It will be imported in a later
        # step. This file will be read later to be imported.
        with open(cert_fname, "w") as f:
            f.write(cert)

    def add_cert(self, cert, nick, flags, pem=False):
        self.nssdb.add_cert(cert, nick, flags, pem)

    def import_cert(self, cert_fname, nickname):
        """
        Load a certificate from a PEM file and add minimal trust.
        """
        args = ["-A", "-n", nickname,
                "-t", "u,u,u",
                "-i", cert_fname,
                "-f", self.passwd_fname]
        self.run_certutil(args)

    def delete_cert(self, nickname):
        self.nssdb.delete_cert(nickname)

    def create_pin_file(self):
        """
        This is the format of Directory Server pin files.
        """
        ipautil.backup_file(self.pin_fname)
        with open(self.pin_fname, "w") as pinfile:
            self.set_perms(pinfile)
            pinfile.write("Internal (Software) Token:")
            with open(self.passwd_fname) as pwdfile:
                pinfile.write(pwdfile.read())

    def find_root_cert(self, nickname):
        """
        Given a nickname, return a list of the certificates that make up
        the trust chain.
        """
        root_nicknames = self.nssdb.get_trust_chain(nickname)

        return root_nicknames

    def trust_root_cert(self, root_nickname, trust_flags):
        if root_nickname is None:
            root_logger.debug("Unable to identify root certificate to trust. Continuing but things are likely to fail.")
            return

        try:
            self.nssdb.trust_root_cert(root_nickname, trust_flags)
        except RuntimeError:
            pass

    def find_server_certs(self):
        return self.nssdb.find_server_certs()

    def import_pkcs12(self, pkcs12_fname, pkcs12_passwd=None):
        return self.nssdb.import_pkcs12(pkcs12_fname,
                                        pkcs12_passwd=pkcs12_passwd)

    def export_pkcs12(self, pkcs12_fname, pkcs12_pwd_fname, nickname=None):
        if nickname is None:
            nickname = get_ca_nickname(api.env.realm)

        ipautil.run([paths.PK12UTIL, "-d", self.secdir,
                     "-o", pkcs12_fname,
                     "-n", nickname,
                     "-k", self.passwd_fname,
                     "-w", pkcs12_pwd_fname])

    def create_from_cacert(self):
        cacert_fname = paths.IPA_CA_CRT
        if ipautil.file_exists(self.certdb_fname):
            # We already have a cert db, see if it is for the same CA.
            # If it is we leave things as they are.
            with open(cacert_fname, "r") as f:
                newca = f.read()

            newca, _st = find_cert_from_txt(newca)

            cacert = self.get_cert_from_db(self.cacert_name)
            if cacert != '':
                cacert, _st = find_cert_from_txt(cacert)

            if newca == cacert:
                return

        # The CA certificates are different or something went wrong. Start with
        # a new certificate database.
        self.create_passwd_file()
        self.create_certdbs()
        self.load_cacert(cacert_fname, IPA_CA_TRUST_FLAGS)

    def create_from_pkcs12(self, pkcs12_fname, pkcs12_passwd,
                           ca_file, trust_flags):
        """Create a new NSS database using the certificates in a PKCS#12 file.

           pkcs12_fname: the filename of the PKCS#12 file
           pkcs12_pwd_fname: the file containing the pin for the PKCS#12 file
           nickname: the nickname/friendly-name of the cert we are loading

           The global CA may be added as well in case it wasn't included in the
           PKCS#12 file. Extra certs won't hurt in any case.

           The global CA may be specified in ca_file, as a PEM filename.
        """
        self.create_noise_file()
        self.create_passwd_file()
        self.create_certdbs()
        self.init_from_pkcs12(
            pkcs12_fname,
            pkcs12_passwd,
            ca_file=ca_file,
            trust_flags=trust_flags)

    def init_from_pkcs12(self, pkcs12_fname, pkcs12_passwd,
                         ca_file, trust_flags):
        self.import_pkcs12(pkcs12_fname, pkcs12_passwd)
        server_certs = self.find_server_certs()
        if len(server_certs) == 0:
            raise RuntimeError("Could not find a suitable server cert in import in %s" % pkcs12_fname)

        if ca_file:
            try:
                with open(ca_file) as fd:
                    certs = fd.read()
            except IOError as e:
                raise RuntimeError(
                    "Failed to open %s: %s" % (ca_file, e.strerror))
            st = 0
            num = 1
            while True:
                try:
                    cert, st = find_cert_from_txt(certs, st)
                except RuntimeError:
                    break
                self.add_cert(cert, 'CA %s' % num, EMPTY_TRUST_FLAGS, pem=True)
                num += 1

        # We only handle one server cert
        nickname = server_certs[0][0]

        ca_names = self.find_root_cert(nickname)[:-1]
        if len(ca_names) == 0:
            raise RuntimeError("Could not find a CA cert in %s" % pkcs12_fname)

        self.cacert_name = ca_names[-1]
        self.trust_root_cert(self.cacert_name, trust_flags)

        self.export_ca_cert(nickname, False)

    def export_pem_cert(self, nickname, location):
        return self.nssdb.export_pem_cert(nickname, location)

    def request_service_cert(self, nickname, principal, host):
        certmonger.request_and_wait_for_cert(certpath=self.secdir,
                                             nickname=nickname,
                                             principal=principal,
                                             subject=host,
                                             passwd_fname=self.passwd_fname)


class _CrossProcessLock(object):
    _DATETIME_FORMAT = '%Y%m%d%H%M%S%f'

    def __init__(self, filename):
        self._filename = filename

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def acquire(self, owner=None):
        self._do(self._acquire, owner)

    def release(self, owner=None):
        self._do(self._release, owner)

    def _acquire(self, owner):
        now = datetime.datetime.utcnow()

        if self._locked and now >= self._expire:
            self._locked = False

        if self._locked:
            return False

        self._locked = True
        self._owner = owner
        self._expire = now + datetime.timedelta(hours=1)

        return True

    def _release(self, owner):
        if not self._locked or self._owner != owner:
            raise RuntimeError("lock not acquired by %s" % owner)

        self._locked = False
        self._owner = None
        self._expire = None

        return True

    def _do(self, func, owner):
        if owner is None:
            owner = '%s[%s]' % (os.path.basename(sys.argv[0]), os.getpid())

        while True:
            with open(self._filename, 'a+') as f:
                fcntl.flock(f, fcntl.LOCK_EX)

                f.seek(0)
                self._read(f)

                if func(owner):
                    f.seek(0)
                    f.truncate()
                    self._write(f)
                    return

            time.sleep(10)

    def _read(self, fileobj):
        p = configparser.RawConfigParser()
        if six.PY2:
            p.readfp(fileobj)  # pylint: disable=deprecated-method
        else:
            p.read_file(fileobj)  # pylint: disable=no-member

        try:
            self._locked = p.getboolean('lock', 'locked')

            if self._locked:
                self._owner = p.get('lock', 'owner')

                expire = p.get('lock', 'expire')
                try:
                    self._expire = datetime.datetime.strptime(
                        expire, self._DATETIME_FORMAT)
                except ValueError:
                    raise configparser.Error
        except configparser.Error:
            self._locked = False
            self._owner = None
            self._expire = None

    def _write(self, fileobj):
        p = configparser.RawConfigParser()
        p.add_section('lock')

        locked = '1' if self._locked else '0'
        p.set('lock', 'locked', locked)

        if self._locked:
            expire = self._expire.strftime(self._DATETIME_FORMAT)
            p.set('lock', 'owner', self._owner)
            p.set('lock', 'expire', expire)

        p.write(fileobj)

renewal_lock = _CrossProcessLock(paths.IPA_RENEWAL_LOCK)
