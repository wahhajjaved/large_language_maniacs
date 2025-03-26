# Authors: Rob Crittenden <rcritten@redhat.com>
#
# Copyright (C) 2009    Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import io
import pwd
import grp
import re
import tempfile
import shutil
import base64

from cryptography.hazmat.primitives import serialization
import cryptography.x509

from ipapython.dn import DN
from ipapython.ipa_log_manager import root_logger
from ipapython import ipautil
from ipalib import x509     # pylint: disable=ipa-forbidden-import

try:
    # pylint: disable=import-error,ipa-forbidden-import
    from ipaplatform.paths import paths
    # pylint: enable=import-error,ipa-forbidden-import
except ImportError:
    CERTUTIL = '/usr/bin/certutil'
    PK12UTIL = '/usr/bin/pk12util'
    OPENSSL = '/usr/bin/openssl'
else:
    CERTUTIL = paths.CERTUTIL
    PK12UTIL = paths.PK12UTIL
    OPENSSL = paths.OPENSSL


CA_NICKNAME_FMT = "%s IPA CA"

NSS_FILES = ("cert8.db", "key3.db", "secmod.db", "pwdfile.txt")


def get_ca_nickname(realm, format=CA_NICKNAME_FMT):
    return format % realm


def find_cert_from_txt(cert, start=0):
    """
    Given a cert blob (str) which may or may not contian leading and
    trailing text, pull out just the certificate part. This will return
    the FIRST cert in a stream of data.

    Returns a tuple (certificate, last position in cert)
    """
    s = cert.find('-----BEGIN CERTIFICATE-----', start)
    e = cert.find('-----END CERTIFICATE-----', s)
    if e > 0:
        e = e + 25

    if s < 0 or e < 0:
        raise RuntimeError("Unable to find certificate")

    cert = cert[s:e]
    return (cert, e)


class NSSDatabase(object):
    """A general-purpose wrapper around a NSS cert database

    For permanent NSS databases, pass the cert DB directory to __init__

    For temporary databases, do not pass nssdir, and call close() when done
    to remove the DB. Alternatively, a NSSDatabase can be used as a
    context manager that calls close() automatically.
    """
    # Traditionally, we used CertDB for our NSS DB operations, but that class
    # got too tied to IPA server details, killing reusability.
    # BaseCertDB is a class that knows nothing about IPA.
    # Generic NSS DB code should be moved here.
    def __init__(self, nssdir=None):
        if nssdir is None:
            self.secdir = tempfile.mkdtemp()
            self._is_temporary = True
        else:
            self.secdir = nssdir
            self._is_temporary = False
        self.pwd_file = os.path.join(self.secdir, 'pwdfile.txt')

    def close(self):
        if self._is_temporary:
            shutil.rmtree(self.secdir)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.close()

    def run_certutil(self, args, stdin=None, **kwargs):
        new_args = [CERTUTIL, "-d", self.secdir]
        new_args = new_args + args
        new_args.extend(['-f', self.pwd_file])
        return ipautil.run(new_args, stdin, **kwargs)

    def create_db(self, user=None, group=None, mode=None, backup=False):
        """Create cert DB

        :param user: User owner the secdir
        :param group: Group owner of the secdir
        :param mode: Mode of the secdir
        :param backup: Backup the sedir files
        """
        dirmode = 0o750
        filemode = 0o640
        pwdfilemode = 0o640
        if mode is not None:
            dirmode = mode
            filemode = mode & 0o666
            pwdfilemode = mode & 0o660

        uid = -1
        gid = -1
        if user is not None:
            uid = pwd.getpwnam(user).pw_uid
        if group is not None:
            gid = grp.getgrnam(group).gr_gid

        if backup:
            for filename in NSS_FILES:
                path = os.path.join(self.secdir, filename)
                ipautil.backup_file(path)

        if not os.path.exists(self.secdir):
            os.makedirs(self.secdir, dirmode)

        if not os.path.exists(self.pwd_file):
            # Create the password file for this db
            with io.open(os.open(self.pwd_file,
                                 os.O_CREAT | os.O_WRONLY,
                                 pwdfilemode), 'w', closefd=True) as f:
                f.write(ipautil.ipa_generate_password())
                f.flush()

        self.run_certutil(["-N", "-f", self.pwd_file])

        # Finally fix up perms
        os.chown(self.secdir, uid, gid)
        os.chmod(self.secdir, dirmode)
        for filename in NSS_FILES:
            path = os.path.join(self.secdir, filename)
            if os.path.exists(path):
                os.chown(path, uid, gid)
                if path == self.pwd_file:
                    new_mode = pwdfilemode
                else:
                    new_mode = filemode
                os.chmod(path, new_mode)

    def restore(self):
        for filename in NSS_FILES:
            path = os.path.join(self.secdir, filename)
            backup_path = path + '.orig'
            save_path = path + '.ipasave'
            try:
                if os.path.exists(path):
                    os.rename(path, save_path)
                if os.path.exists(backup_path):
                    os.rename(backup_path, path)
            except OSError as e:
                root_logger.debug(e)

    def list_certs(self):
        """Return nicknames and cert flags for all certs in the database

        :return: List of (name, trust_flags) tuples
        """
        result = self.run_certutil(["-L"], capture_output=True)
        certs = result.output.splitlines()

        # FIXME, this relies on NSS never changing the formatting of certutil
        certlist = []
        for cert in certs:
            match = re.match(r'^(.+?)\s+(\w*,\w*,\w*)\s*$', cert)
            if match:
                certlist.append(match.groups())

        return tuple(certlist)

    def find_server_certs(self):
        """Return nicknames and cert flags for server certs in the database

        Server certs have an "u" character in the trust flags.

        :return: List of (name, trust_flags) tuples
        """
        server_certs = []
        for name, flags in self.list_certs():
            if 'u' in flags:
                server_certs.append((name, flags))

        return server_certs

    def get_trust_chain(self, nickname):
        """Return names of certs in a given cert's trust chain

        :param nickname: Name of the cert
        :return: List of certificate names
        """
        root_nicknames = []
        result = self.run_certutil(["-O", "-n", nickname], capture_output=True)
        chain = result.output.splitlines()

        for c in chain:
            m = re.match('\s*"(.*)" \[.*', c)
            if m:
                root_nicknames.append(m.groups()[0])

        return root_nicknames

    def export_pkcs12(self, nickname, pkcs12_filename, pkcs12_passwd=None):
        args = [PK12UTIL, "-d", self.secdir,
                "-o", pkcs12_filename,
                "-n", nickname,
                "-k", self.pwd_file]
        pkcs12_password_file = None
        if pkcs12_passwd is not None:
            pkcs12_password_file = ipautil.write_tmp_file(pkcs12_passwd + '\n')
            args = args + ["-w", pkcs12_password_file.name]
        try:
            ipautil.run(args)
        except ipautil.CalledProcessError as e:
            if e.returncode == 17:
                raise RuntimeError("incorrect password for pkcs#12 file %s" %
                                   pkcs12_filename)
            elif e.returncode == 10:
                raise RuntimeError("Failed to open %s" % pkcs12_filename)
            else:
                raise RuntimeError("unknown error exporting pkcs#12 file %s" %
                                   pkcs12_filename)
        finally:
            if pkcs12_password_file is not None:
                pkcs12_password_file.close()

    def import_pkcs12(self, pkcs12_filename, pkcs12_passwd=None):
        args = [PK12UTIL, "-d", self.secdir,
                "-i", pkcs12_filename,
                "-k", self.pwd_file, '-v']
        pkcs12_password_file = None
        if pkcs12_passwd is not None:
            pkcs12_password_file = ipautil.write_tmp_file(pkcs12_passwd + '\n')
            args = args + ["-w", pkcs12_password_file.name]
        try:
            ipautil.run(args)
        except ipautil.CalledProcessError as e:
            if e.returncode == 17:
                raise RuntimeError("incorrect password for pkcs#12 file %s" %
                    pkcs12_filename)
            elif e.returncode == 10:
                raise RuntimeError("Failed to open %s" % pkcs12_filename)
            else:
                raise RuntimeError("unknown error import pkcs#12 file %s" %
                    pkcs12_filename)
        finally:
            if pkcs12_password_file is not None:
                pkcs12_password_file.close()

    def import_files(self, files, import_keys=False, key_password=None,
                     key_nickname=None):
        """
        Import certificates and a single private key from multiple files

        The files may be in PEM and DER certificate, PKCS#7 certificate chain,
        PKCS#8 and raw private key and PKCS#12 formats.

        :param files: Names of files to import
        :param import_keys: Whether to import private keys
        :param key_password: Password to decrypt private keys
        :param key_nickname: Nickname of the private key to import from PKCS#12
            files
        """
        key_file = None
        extracted_key = None
        extracted_certs = []

        for filename in files:
            try:
                with open(filename, 'rb') as f:
                    data = f.read()
            except IOError as e:
                raise RuntimeError(
                    "Failed to open %s: %s" % (filename, e.strerror))

            # Try to parse the file as PEM file
            matches = list(re.finditer(
                r'-----BEGIN (.+?)-----(.*?)-----END \1-----', data, re.DOTALL))
            if matches:
                loaded = False
                for match in matches:
                    body = match.group()
                    label = match.group(1)
                    line = len(data[:match.start() + 1].splitlines())

                    if label in ('CERTIFICATE', 'X509 CERTIFICATE',
                                 'X.509 CERTIFICATE'):
                        try:
                            x509.load_certificate(match.group(2))
                        except ValueError as e:
                            if label != 'CERTIFICATE':
                                root_logger.warning(
                                    "Skipping certificate in %s at line %s: %s",
                                    filename, line, e)
                                continue
                        else:
                            extracted_certs.append(body)
                            loaded = True
                            continue

                    if label in ('PKCS7', 'PKCS #7 SIGNED DATA', 'CERTIFICATE'):
                        try:
                            certs = x509.pkcs7_to_pems(body)
                        except ipautil.CalledProcessError as e:
                            if label == 'CERTIFICATE':
                                root_logger.warning(
                                    "Skipping certificate in %s at line %s: %s",
                                    filename, line, e)
                            else:
                                root_logger.warning(
                                    "Skipping PKCS#7 in %s at line %s: %s",
                                    filename, line, e)
                            continue
                        else:
                            extracted_certs.extend(certs)
                            loaded = True
                            continue

                    if label in ('PRIVATE KEY', 'ENCRYPTED PRIVATE KEY',
                                 'RSA PRIVATE KEY', 'DSA PRIVATE KEY',
                                 'EC PRIVATE KEY'):
                        if not import_keys:
                            continue

                        if key_file:
                            raise RuntimeError(
                                "Can't load private key from both %s and %s" %
                                (key_file, filename))

                        args = [
                            OPENSSL, 'pkcs8',
                            '-topk8',
                            '-passout', 'file:' + self.pwd_file,
                        ]
                        if ((label != 'PRIVATE KEY' and key_password) or
                            label == 'ENCRYPTED PRIVATE KEY'):
                            key_pwdfile = ipautil.write_tmp_file(key_password)
                            args += [
                                '-passin', 'file:' + key_pwdfile.name,
                            ]
                        try:
                            result = ipautil.run(
                                args, stdin=body, capture_output=True)
                        except ipautil.CalledProcessError as e:
                            root_logger.warning(
                                "Skipping private key in %s at line %s: %s",
                                filename, line, e)
                            continue
                        else:
                            extracted_key = result.output
                            key_file = filename
                            loaded = True
                            continue
                if loaded:
                    continue
                raise RuntimeError("Failed to load %s" % filename)

            # Try to load the file as DER certificate
            try:
                x509.load_certificate(data, x509.DER)
            except ValueError:
                pass
            else:
                data = x509.make_pem(base64.b64encode(data))
                extracted_certs.append(data)
                continue

            # Try to import the file as PKCS#12 file
            if import_keys:
                try:
                    self.import_pkcs12(filename, key_password)
                except RuntimeError:
                    pass
                else:
                    if key_file:
                        raise RuntimeError(
                            "Can't load private key from both %s and %s" %
                            (key_file, filename))
                    key_file = filename

                    server_certs = self.find_server_certs()
                    if key_nickname:
                        for nickname, _trust_flags in server_certs:
                            if nickname == key_nickname:
                                break
                        else:
                            raise RuntimeError(
                                "Server certificate \"%s\" not found in %s" %
                                (key_nickname, filename))
                    else:
                        if len(server_certs) > 1:
                            raise RuntimeError(
                                "%s server certificates found in %s, "
                                "expecting only one" %
                                (len(server_certs), filename))

                    continue

            raise RuntimeError("Failed to load %s" % filename)

        if import_keys and not key_file:
            raise RuntimeError(
                "No server certificates found in %s" % (', '.join(files)))

        for cert_pem in extracted_certs:
            cert = x509.load_certificate(cert_pem)
            nickname = str(DN(cert.subject))
            data = cert.public_bytes(serialization.Encoding.DER)
            self.add_cert(data, nickname, ',,')

        if extracted_key:
            in_file = ipautil.write_tmp_file(
                    '\n'.join(extracted_certs) + '\n' + extracted_key)
            out_file = tempfile.NamedTemporaryFile()
            out_password = ipautil.ipa_generate_password()
            out_pwdfile = ipautil.write_tmp_file(out_password)
            args = [
                OPENSSL, 'pkcs12',
                '-export',
                '-in', in_file.name,
                '-out', out_file.name,
                '-passin', 'file:' + self.pwd_file,
                '-passout', 'file:' + out_pwdfile.name,
            ]
            try:
                ipautil.run(args)
            except ipautil.CalledProcessError as e:
                raise RuntimeError(
                    "No matching certificate found for private key from %s" %
                    key_file)

            self.import_pkcs12(out_file.name, out_password)

    def trust_root_cert(self, root_nickname, trust_flags=None):
        if root_nickname[:7] == "Builtin":
            root_logger.debug(
                "No need to add trust for built-in root CAs, skipping %s" %
                root_nickname)
        else:
            if trust_flags is None:
                trust_flags = 'C,,'
            try:
                self.run_certutil(["-M", "-n", root_nickname,
                                   "-t", trust_flags])
            except ipautil.CalledProcessError:
                raise RuntimeError(
                    "Setting trust on %s failed" % root_nickname)

    def get_cert(self, nickname, pem=False):
        args = ['-L', '-n', nickname, '-a']
        try:
            result = self.run_certutil(args, capture_output=True)
        except ipautil.CalledProcessError:
            raise RuntimeError("Failed to get %s" % nickname)
        cert = result.output
        if not pem:
            cert, _start = find_cert_from_txt(cert, start=0)
            cert = x509.strip_header(cert)
            cert = base64.b64decode(cert)
        return cert

    def has_nickname(self, nickname):
        try:
            self.get_cert(nickname)
        except RuntimeError:
            # This might be error other than "nickname not found". Beware.
            return False
        else:
            return True

    def export_pem_cert(self, nickname, location):
        """Export the given cert to PEM file in the given location"""
        cert = self.get_cert(nickname, pem=True)
        with open(location, "w+") as fd:
            fd.write(cert)
        os.chmod(location, 0o444)

    def import_pem_cert(self, nickname, flags, location):
        """Import a cert form the given PEM file.

        The file must contain exactly one certificate.
        """
        try:
            with open(location) as fd:
                certs = fd.read()
        except IOError as e:
            raise RuntimeError(
                "Failed to open %s: %s" % (location, e.strerror)
            )

        cert, st = find_cert_from_txt(certs)
        self.add_cert(cert, nickname, flags, pem=True)

        try:
            find_cert_from_txt(certs, st)
        except RuntimeError:
            pass
        else:
            raise ValueError('%s contains more than one certificate' %
                             location)

    def add_cert(self, cert, nick, flags, pem=False):
        args = ["-A", "-n", nick, "-t", flags]
        if pem:
            args.append("-a")
        self.run_certutil(args, stdin=cert)

    def delete_cert(self, nick):
        self.run_certutil(["-D", "-n", nick])

    def verify_server_cert_validity(self, nickname, hostname):
        """Verify a certificate is valid for a SSL server with given hostname

        Raises a ValueError if the certificate is invalid.
        """
        cert = self.get_cert(nickname)
        cert = x509.load_certificate(cert, x509.DER)

        try:
            self.run_certutil(['-V', '-n', nickname, '-u', 'V'])
        except ipautil.CalledProcessError:
            raise ValueError('invalid for a SSL server')

        try:
            x509.match_hostname(cert, hostname)
        except ValueError:
            raise ValueError('invalid for server %s' % hostname)

    def verify_ca_cert_validity(self, nickname):
        cert = self.get_cert(nickname)
        cert = x509.load_certificate(cert, x509.DER)

        if not cert.subject:
            raise ValueError("has empty subject")

        try:
            bc = cert.extensions.get_extension_for_class(
                    cryptography.x509.BasicConstraints)
        except cryptography.x509.ExtensionNotFound:
            raise ValueError("missing basic constraints")

        if not bc.value.ca:
            raise ValueError("not a CA certificate")

        try:
            self.run_certutil(['-V', '-n', nickname, '-u', 'L'])
        except ipautil.CalledProcessError:
            raise ValueError('invalid for a CA')

    def publish_ca_cert(self, canickname, location):
        args = ["-L", "-n", canickname, "-a"]
        result = self.run_certutil(args, capture_output=True)
        cert = result.output
        fd = open(location, "w+")
        fd.write(cert)
        fd.close()
        os.chmod(location, 0o444)
