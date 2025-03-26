# Authors: Rob Crittenden <rcritten@redhat.com>
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

from __future__ import print_function
from __future__ import absolute_import

import logging
import os
import glob
import errno
import shlex
import pipes
import tempfile

from augeas import Augeas
import dbus

from ipalib.install import certmonger
from ipapython import ipaldap
from ipaserver.install import replication
from ipaserver.install import service
from ipaserver.install import certs
from ipaserver.install import installutils
from ipapython import directivesetter
from ipapython import dogtag
from ipapython import ipautil
from ipapython.dn import DN
import ipapython.errors
from ipaserver.install import sysupgrade
from ipalib import api, x509
from ipalib.constants import IPAAPI_USER, MOD_SSL_VERIFY_DEPTH, IPA_CA_RECORD
from ipaplatform.constants import constants
from ipaplatform.tasks import tasks
from ipaplatform.paths import paths
from ipaplatform import services

logger = logging.getLogger(__name__)

HTTPD_USER = constants.HTTPD_USER
KDCPROXY_USER = constants.KDCPROXY_USER

OCSP_DIRECTIVE = 'SSLOCSPEnable'

OCSP_ENABLED = 'ocsp_enabled'


class WebGuiInstance(service.SimpleServiceInstance):
    def __init__(self):
        service.SimpleServiceInstance.__init__(self, "ipa_webgui")


class HTTPInstance(service.Service):
    def __init__(self, fstore=None, cert_nickname='Server-Cert',
                 api=api):
        super(HTTPInstance, self).__init__(
            "httpd",
            service_desc="the web interface",
            fstore=fstore,
            api=api,
            service_prefix=u'HTTP',
            service_user=HTTPD_USER,
            keytab=paths.HTTP_KEYTAB)

        self.cacert_nickname = None
        self.cert_nickname = cert_nickname
        self.ca_is_configured = True
        self.keytab_user = constants.GSSPROXY_USER

    subject_base = ipautil.dn_attribute_property('_subject_base')

    def create_instance(self, realm, fqdn, domain_name, dm_password=None,
                        pkcs12_info=None,
                        subject_base=None, auto_redirect=True, ca_file=None,
                        ca_is_configured=None, promote=False,
                        master_fqdn=None):
        self.fqdn = fqdn
        self.realm = realm
        self.domain = domain_name
        self.dm_password = dm_password
        self.suffix = ipautil.realm_to_suffix(self.realm)
        self.pkcs12_info = pkcs12_info
        self.cert = None
        self.subject_base = subject_base
        self.sub_dict = dict(
            REALM=realm,
            FQDN=fqdn,
            DOMAIN=self.domain,
            AUTOREDIR='' if auto_redirect else '#',
            CRL_PUBLISH_PATH=paths.PKI_CA_PUBLISH_DIR,
            FONTS_DIR=paths.FONTS_DIR,
            FONTS_OPENSANS_DIR=paths.FONTS_OPENSANS_DIR,
            FONTS_FONTAWESOME_DIR=paths.FONTS_FONTAWESOME_DIR,
            GSSAPI_SESSION_KEY=paths.GSSAPI_SESSION_KEY,
            IPA_CUSTODIA_SOCKET=paths.IPA_CUSTODIA_SOCKET,
            IPA_CCACHES=paths.IPA_CCACHES,
            WSGI_PREFIX_DIR=paths.WSGI_PREFIX_DIR,
            WSGI_PROCESSES=constants.WSGI_PROCESSES,
        )
        self.ca_file = ca_file
        if ca_is_configured is not None:
            self.ca_is_configured = ca_is_configured
        self.promote = promote
        self.master_fqdn = master_fqdn

        self.step("stopping httpd", self.__stop)
        self.step("backing up ssl.conf", self.backup_ssl_conf)
        self.step("disabling nss.conf", self.disable_nss_conf)
        self.step("configuring mod_ssl certificate paths",
                  self.configure_mod_ssl_certs)
        self.step("setting mod_ssl protocol list",
                  self.set_mod_ssl_protocol)
        self.step("configuring mod_ssl log directory",
                  self.set_mod_ssl_logdir)
        self.step("disabling mod_ssl OCSP", self.disable_mod_ssl_ocsp)
        self.step("adding URL rewriting rules", self.__add_include)
        self.step("configuring httpd", self.__configure_http)
        self.step("setting up httpd keytab", self.request_service_keytab)
        self.step("configuring Gssproxy", self.configure_gssproxy)
        self.step("setting up ssl", self.__setup_ssl)
        if self.ca_is_configured:
            self.step("configure certmonger for renewals",
                      self.configure_certmonger_renewal_guard)
        self.step("publish CA cert", self.__publish_ca_cert)
        self.step("clean up any existing httpd ccaches",
                  self.remove_httpd_ccaches)
        self.step("configuring SELinux for httpd", self.configure_selinux_for_httpd)
        if not self.is_kdcproxy_configured():
            self.step("create KDC proxy config", self.create_kdcproxy_conf)
            self.step("enable KDC proxy", self.enable_kdcproxy)
        self.step("starting httpd", self.start)
        self.step("configuring httpd to start on boot", self.__enable)
        self.step("enabling oddjobd", self.enable_and_start_oddjobd)

        self.start_creation()

    def __stop(self):
        self.backup_state("running", self.is_running())
        self.stop()

    def __enable(self):
        self.backup_state("enabled", self.is_enabled())
        # We do not let the system start IPA components on its own,
        # Instead we reply on the IPA init script to start only enabled
        # components as found in our LDAP configuration tree
        self.ldap_configure('HTTP', self.fqdn, None, self.suffix)

    def configure_selinux_for_httpd(self):
        try:
            tasks.set_selinux_booleans(constants.SELINUX_BOOLEAN_HTTPD,
                                       self.backup_state)
        except ipapython.errors.SetseboolError as e:
            self.print_msg(e.format_service_warning('web interface'))

    def remove_httpd_ccaches(self):
        # Clean up existing ccaches
        # Make sure that empty env is passed to avoid passing KRB5CCNAME from
        # current env
        ipautil.remove_file(paths.HTTP_CCACHE)
        for f in os.listdir(paths.IPA_CCACHES):
            os.remove(os.path.join(paths.IPA_CCACHES, f))

    def __configure_http(self):
        self.update_httpd_service_ipa_conf()
        self.update_httpd_wsgi_conf()

        # create /etc/httpd/alias, see https://pagure.io/freeipa/issue/7529
        session_dir = os.path.dirname(self.sub_dict['GSSAPI_SESSION_KEY'])
        if not os.path.isdir(session_dir):
            os.makedirs(session_dir)
        # Must be world-readable / executable
        os.chmod(session_dir, 0o755)
        # Restore SELinux context of session_dir /etc/httpd/alias, see
        # https://pagure.io/freeipa/issue/7662
        tasks.restore_context(session_dir)

        target_fname = paths.HTTPD_IPA_CONF
        http_txt = ipautil.template_file(
            os.path.join(paths.USR_SHARE_IPA_DIR,
                         "ipa.conf.template"),
            self.sub_dict)
        self.fstore.backup_file(paths.HTTPD_IPA_CONF)
        http_fd = open(target_fname, "w")
        http_fd.write(http_txt)
        http_fd.close()
        os.chmod(target_fname, 0o644)

        target_fname = paths.HTTPD_IPA_REWRITE_CONF
        http_txt = ipautil.template_file(
            os.path.join(paths.USR_SHARE_IPA_DIR,
                         "ipa-rewrite.conf.template"),
            self.sub_dict)
        self.fstore.backup_file(paths.HTTPD_IPA_REWRITE_CONF)
        http_fd = open(target_fname, "w")
        http_fd.write(http_txt)
        http_fd.close()
        os.chmod(target_fname, 0o644)

    def configure_gssproxy(self):
        tasks.configure_http_gssproxy_conf(IPAAPI_USER)
        services.knownservices.gssproxy.restart()

    def get_mod_nss_nickname(self):
        cert = directivesetter.get_directive(paths.HTTPD_NSS_CONF,
                                             'NSSNickname')
        nickname = directivesetter.unquote_directive_value(cert,
                                                           quote_char="'")
        return nickname

    def backup_ssl_conf(self):
        self.fstore.backup_file(paths.HTTPD_SSL_CONF)
        self.fstore.backup_file(paths.HTTPD_SSL_SITE_CONF)

    def disable_nss_conf(self):
        """
        Backs up the original nss.conf file and replace it with the empty one.
        Empty file avoids recreation of nss.conf in case the package is
        reinstalled.

        There is no safe way to co-exist since there is no safe port
        to make mod_nss use, disable it completely.
        """
        if os.path.exists(paths.HTTPD_NSS_CONF):
            # check that we don't have a backup already
            # (mod_nss -> mod_ssl upgrade scenario)
            if not self.fstore.has_file(paths.HTTPD_NSS_CONF):
                self.fstore.backup_file(paths.HTTPD_NSS_CONF)

        open(paths.HTTPD_NSS_CONF, 'w').close()

    def set_mod_ssl_protocol(self):
        tasks.configure_httpd_protocol()

    def set_mod_ssl_logdir(self):
        tasks.setup_httpd_logging()

    def disable_mod_ssl_ocsp(self):
        if sysupgrade.get_upgrade_state('http', OCSP_ENABLED) is None:
            self.__disable_mod_ssl_ocsp()
            sysupgrade.set_upgrade_state('http', OCSP_ENABLED, False)

    def __disable_mod_ssl_ocsp(self):
        aug = Augeas(flags=Augeas.NO_LOAD | Augeas.NO_MODL_AUTOLOAD)

        aug.set('/augeas/load/Httpd/lens', 'Httpd.lns')
        aug.set('/augeas/load/Httpd/incl', paths.HTTPD_SSL_CONF)
        aug.load()

        path = '/files{}/VirtualHost'.format(paths.HTTPD_SSL_CONF)
        ocsp_path = '{}/directive[.="{}"]'.format(path, OCSP_DIRECTIVE)
        ocsp_arg = '{}/arg'.format(ocsp_path)
        ocsp_comment = '{}/#comment[.="{}"]'.format(path, OCSP_DIRECTIVE)

        ocsp_dir = aug.get(ocsp_path)

        # there is SSLOCSPEnable directive in nss.conf file, comment it
        # otherwise just do nothing
        if ocsp_dir is not None:
            ocsp_state = aug.get(ocsp_arg)
            aug.remove(ocsp_arg)
            aug.rename(ocsp_path, '#comment')
            aug.set(ocsp_comment, '{} {}'.format(OCSP_DIRECTIVE, ocsp_state))
            aug.save()

    def __add_include(self):
        """This should run after __set_mod_nss_port so is already backed up"""
        if installutils.update_file(paths.HTTPD_SSL_SITE_CONF,
                                    '</VirtualHost>',
                                    'Include {path}\n'
                                    '</VirtualHost>'.format(
                                        path=paths.HTTPD_IPA_REWRITE_CONF)
                                    ) != 0:
            self.print_msg("Adding Include conf.d/ipa-rewrite to "
                           "%s failed." % paths.HTTPD_SSL_SITE_CONF)

    def configure_certmonger_renewal_guard(self):
        certmonger = services.knownservices.certmonger
        certmonger_stopped = not certmonger.is_running()

        if certmonger_stopped:
            certmonger.start()
        try:
            bus = dbus.SystemBus()
            obj = bus.get_object('org.fedorahosted.certmonger',
                                 '/org/fedorahosted/certmonger')
            iface = dbus.Interface(obj, 'org.fedorahosted.certmonger')
            path = iface.find_ca_by_nickname('IPA')
            if path:
                ca_obj = bus.get_object('org.fedorahosted.certmonger', path)
                ca_iface = dbus.Interface(ca_obj,
                                          'org.freedesktop.DBus.Properties')
                helper = ca_iface.Get('org.fedorahosted.certmonger.ca',
                                      'external-helper')
                if helper:
                    args = shlex.split(helper)
                    if args[0] != paths.IPA_SERVER_GUARD:
                        self.backup_state('certmonger_ipa_helper', helper)
                        args = [paths.IPA_SERVER_GUARD] + args
                        helper = ' '.join(pipes.quote(a) for a in args)
                        ca_iface.Set('org.fedorahosted.certmonger.ca',
                                     'external-helper', helper)
        finally:
            if certmonger_stopped:
                certmonger.stop()

    def __setup_ssl(self):
        key_passwd_file = paths.HTTPD_PASSWD_FILE_FMT.format(host=api.env.host)
        with open(key_passwd_file, 'wb') as f:
            os.fchmod(f.fileno(), 0o600)
            pkey_passwd = ipautil.ipa_generate_password().encode('utf-8')
            f.write(pkey_passwd)

        if self.pkcs12_info:
            p12_certs, p12_priv_keys = certs.pkcs12_to_certkeys(
                *self.pkcs12_info)
            keys_dict = {
                k.public_key().public_numbers(): k
                for k in p12_priv_keys
            }
            certs_keys = [
                (c, keys_dict.get(c.public_key().public_numbers()))
                for c in p12_certs
            ]
            server_certs_keys = [
                (c, k) for c, k in certs_keys if k is not None
            ]

            if not server_certs_keys:
                raise RuntimeError(
                    "Could not find a suitable server cert in import in %s"
                    % self.pkcs12_info[0]
                )

            # We only handle one server cert
            self.cert = server_certs_keys[0][0]
            x509.write_certificate(self.cert, paths.HTTPD_CERT_FILE)
            x509.write_pem_private_key(
                server_certs_keys[0][1],
                paths.HTTPD_KEY_FILE,
                passwd=pkey_passwd
            )

            if self.ca_is_configured:
                self.start_tracking_certificates()

            self.add_cert_to_service()

        else:
            if not self.promote:
                ca_args = [
                    paths.CERTMONGER_DOGTAG_SUBMIT,
                    '--ee-url', 'https://%s:8443/ca/ee/ca' % self.fqdn,
                    '--certfile', paths.RA_AGENT_PEM,
                    '--keyfile', paths.RA_AGENT_KEY,
                    '--cafile', paths.IPA_CA_CRT,
                    '--agent-submit'
                ]
                helper = " ".join(ca_args)
                prev_helper = certmonger.modify_ca_helper('IPA', helper)
            else:
                prev_helper = None
            try:
                certmonger.request_and_wait_for_cert(
                    certpath=(paths.HTTPD_CERT_FILE, paths.HTTPD_KEY_FILE),
                    principal=self.principal,
                    subject=str(DN(('CN', self.fqdn), self.subject_base)),
                    ca='IPA',
                    profile=dogtag.DEFAULT_PROFILE,
                    dns=[self.fqdn, f'{IPA_CA_RECORD}.{api.env.domain}'],
                    post_command='restart_httpd',
                    storage='FILE',
                    passwd_fname=key_passwd_file,
                    resubmit_timeout=api.env.certmonger_wait_timeout
                )
            finally:
                if prev_helper is not None:
                    certmonger.modify_ca_helper('IPA', prev_helper)
            self.cert = x509.load_certificate_from_file(
                paths.HTTPD_CERT_FILE
            )

            if prev_helper is not None:
                self.add_cert_to_service()

            with open(paths.HTTPD_KEY_FILE, 'rb') as f:
                priv_key = x509.load_pem_private_key(
                    f.read(), pkey_passwd, backend=x509.default_backend())

            # Verify we have a valid server cert
            if (priv_key.public_key().public_numbers()
                    != self.cert.public_key().public_numbers()):
                raise RuntimeError(
                    "The public key of the issued HTTPD service certificate "
                    "does not match its private key.")

        sysupgrade.set_upgrade_state('ssl.conf', 'migrated_to_mod_ssl', True)

    def configure_mod_ssl_certs(self):
        """Configure the mod_ssl certificate directives"""
        directivesetter.set_directive(paths.HTTPD_SSL_SITE_CONF,
                                   'SSLCertificateFile',
                                   paths.HTTPD_CERT_FILE, False)
        directivesetter.set_directive(paths.HTTPD_SSL_SITE_CONF,
                                   'SSLCertificateKeyFile',
                                   paths.HTTPD_KEY_FILE, False)
        directivesetter.set_directive(
            paths.HTTPD_SSL_CONF,
            'SSLPassPhraseDialog',
            'exec:{passread}'.format(passread=paths.IPA_HTTPD_PASSWD_READER),
            False)
        directivesetter.set_directive(paths.HTTPD_SSL_SITE_CONF,
                                   'SSLCACertificateFile',
                                   paths.IPA_CA_CRT, False)
        # set SSLVerifyDepth for external CA installations
        directivesetter.set_directive(paths.HTTPD_SSL_CONF,
                                   'SSLVerifyDepth',
                                   MOD_SSL_VERIFY_DEPTH,
                                   quotes=False)

    def __publish_ca_cert(self):
        ca_subject = self.cert.issuer
        certlist = x509.load_certificate_list_from_file(paths.IPA_CA_CRT)
        ca_certs = [c for c in certlist if c.subject == ca_subject]
        if not ca_certs:
            raise RuntimeError("HTTPD cert was issued by an unknown CA.")
        # at this time we can assume any CA cert will be valid since this is
        # only run during installation
        x509.write_certificate_list(certlist, paths.CA_CRT, mode=0o644)

    def is_kdcproxy_configured(self):
        """Check if KDC proxy has already been configured in the past"""
        return os.path.isfile(paths.HTTPD_IPA_KDCPROXY_CONF)

    def enable_kdcproxy(self):
        """Add ipaConfigString=kdcProxyEnabled to cn=KDC"""
        service.set_service_entry_config(
            'KDC', self.fqdn, [u'kdcProxyEnabled'], self.suffix)

    def create_kdcproxy_conf(self):
        """Create ipa-kdc-proxy.conf in /etc/ipa/kdcproxy"""
        target_fname = paths.HTTPD_IPA_KDCPROXY_CONF
        sub_dict = dict(KDCPROXY_CONFIG=paths.KDCPROXY_CONFIG)
        http_txt = ipautil.template_file(
            os.path.join(paths.USR_SHARE_IPA_DIR,
                         "ipa-kdc-proxy.conf.template"),
            sub_dict)
        self.fstore.backup_file(target_fname)
        with open(target_fname, 'w') as f:
            f.write(http_txt)
        os.chmod(target_fname, 0o644)

    def enable_and_start_oddjobd(self):
        oddjobd = services.service('oddjobd', api)
        self.sstore.backup_state('oddjobd', 'running', oddjobd.is_running())
        self.sstore.backup_state('oddjobd', 'enabled', oddjobd.is_enabled())

        try:
            oddjobd.enable()
            oddjobd.start()
        except Exception as e:
            logger.critical("Unable to start oddjobd: %s", str(e))

    def update_httpd_service_ipa_conf(self):
        tasks.configure_httpd_service_ipa_conf()

    def update_httpd_wsgi_conf(self):
        tasks.configure_httpd_wsgi_conf()

    def uninstall(self):
        if self.is_configured():
            self.print_msg("Unconfiguring web server")

        running = self.restore_state("running")
        enabled = self.restore_state("enabled")

        # Restore oddjobd to its original state
        oddjobd = services.service('oddjobd', api)

        if not self.sstore.restore_state('oddjobd', 'running'):
            try:
                oddjobd.stop()
            except Exception:
                pass

        if not self.sstore.restore_state('oddjobd', 'enabled'):
            try:
                oddjobd.disable()
            except Exception:
                pass

        self.stop_tracking_certificates()

        helper = self.restore_state('certmonger_ipa_helper')
        if helper:
            bus = dbus.SystemBus()
            obj = bus.get_object('org.fedorahosted.certmonger',
                                 '/org/fedorahosted/certmonger')
            iface = dbus.Interface(obj, 'org.fedorahosted.certmonger')
            path = iface.find_ca_by_nickname('IPA')
            if path:
                ca_obj = bus.get_object('org.fedorahosted.certmonger', path)
                ca_iface = dbus.Interface(ca_obj,
                                          'org.freedesktop.DBus.Properties')
                ca_iface.Set('org.fedorahosted.certmonger.ca',
                             'external-helper', helper)

        for f in [paths.HTTPD_IPA_CONF, paths.HTTPD_SSL_CONF,
                  paths.HTTPD_SSL_SITE_CONF, paths.HTTPD_NSS_CONF]:
            try:
                self.fstore.restore_file(f)
            except ValueError as error:
                logger.debug("%s", error)

        # Remove the configuration files we create
        ipautil.remove_keytab(self.keytab)
        remove_files = [
            paths.HTTP_CCACHE,
            paths.HTTPD_CERT_FILE,
            paths.HTTPD_KEY_FILE,
            paths.HTTPD_PASSWD_FILE_FMT.format(host=api.env.host),
            paths.HTTPD_IPA_REWRITE_CONF,
            paths.HTTPD_IPA_CONF,
            paths.HTTPD_IPA_PKI_PROXY_CONF,
            paths.HTTPD_IPA_KDCPROXY_CONF_SYMLINK,
            paths.HTTPD_IPA_KDCPROXY_CONF,
            paths.GSSPROXY_CONF,
            paths.GSSAPI_SESSION_KEY,
            paths.HTTPD_PASSWORD_CONF,
            paths.SYSTEMD_SYSTEM_HTTPD_IPA_CONF,
        ]
        # NSS DB backups
        remove_files.extend(
            glob.glob(os.path.join(paths.HTTPD_ALIAS_DIR, '*.ipasave'))
        )
        if paths.HTTPD_IPA_WSGI_MODULES_CONF is not None:
            remove_files.append(paths.HTTPD_IPA_WSGI_MODULES_CONF)

        for filename in remove_files:
            ipautil.remove_file(filename)

        try:
            os.rmdir(paths.SYSTEMD_SYSTEM_HTTPD_D_DIR)
        except OSError as e:
            if e.errno not in {errno.ENOENT, errno.ENOTEMPTY}:
                logger.error(
                    "Failed to remove directory %s",
                    paths.SYSTEMD_SYSTEM_HTTPD_D_DIR
                )

        # Restore SELinux boolean states
        boolean_states = {name: self.restore_state(name)
                          for name in constants.SELINUX_BOOLEAN_HTTPD}
        try:
            tasks.set_selinux_booleans(boolean_states)
        except ipapython.errors.SetseboolError as e:
            self.print_msg('WARNING: ' + str(e))

        if running:
            self.restart()

        # disabled by default, by ldap_configure()
        if enabled:
            self.enable()

    def stop_tracking_certificates(self):
        try:
            certmonger.stop_tracking(certfile=paths.HTTPD_CERT_FILE)
        except RuntimeError as e:
            logger.error("certmonger failed to stop tracking certificate: %s",
                         str(e))

    def start_tracking_certificates(self):
        key_passwd_file = paths.HTTPD_PASSWD_FILE_FMT.format(host=api.env.host)
        cert = x509.load_certificate_from_file(paths.HTTPD_CERT_FILE)
        if certs.is_ipa_issued_cert(api, cert):
            request_id = certmonger.start_tracking(
                certpath=(paths.HTTPD_CERT_FILE, paths.HTTPD_KEY_FILE),
                post_command='restart_httpd', storage='FILE',
                profile=dogtag.DEFAULT_PROFILE,
                pinfile=key_passwd_file,
                dns=[self.fqdn, f'{IPA_CA_RECORD}.{api.env.domain}'],
            )
            subject = str(DN(cert.subject))
            certmonger.add_principal(request_id, self.principal)
            certmonger.add_subject(request_id, subject)
        else:
            logger.debug("Will not track HTTP server cert %s as it is not "
                         "issued by IPA", cert.subject)

    def request_service_keytab(self):
        super(HTTPInstance, self).request_service_keytab()

        if self.master_fqdn is not None:
            service_dn = DN(('krbprincipalname', self.principal),
                            api.env.container_service,
                            self.suffix)

            ldap_uri = ipaldap.get_ldap_uri(self.master_fqdn)
            with ipaldap.LDAPClient(ldap_uri,
                                    start_tls=not self.promote,
                                    cacert=paths.IPA_CA_CRT) as remote_ldap:
                if self.promote:
                    remote_ldap.gssapi_bind()
                else:
                    remote_ldap.simple_bind(ipaldap.DIRMAN_DN,
                                            self.dm_password)
                replication.wait_for_entry(
                    remote_ldap,
                    service_dn,
                    timeout=api.env.replication_wait_timeout
                )

    def migrate_to_mod_ssl(self):
        """For upgrades only, migrate from mod_nss to mod_ssl"""
        db = certs.CertDB(api.env.realm, nssdir=paths.HTTPD_ALIAS_DIR)
        nickname = self.get_mod_nss_nickname()
        with tempfile.NamedTemporaryFile() as temp:
            pk12_password = ipautil.ipa_generate_password()
            pk12_pwdfile = ipautil.write_tmp_file(pk12_password)
            db.export_pkcs12(temp.name, pk12_pwdfile.name, nickname)
            certs.install_pem_from_p12(temp.name,
                                       pk12_password,
                                       paths.HTTPD_CERT_FILE)

            passwd_fname = paths.HTTPD_PASSWD_FILE_FMT.format(
                            host=api.env.host)
            with open(passwd_fname, 'wb') as passwd_file:
                os.fchmod(passwd_file.fileno(), 0o600)
                passwd_file.write(
                    ipautil.ipa_generate_password().encode('utf-8'))

            certs.install_key_from_p12(temp.name,
                                       pk12_password,
                                       paths.HTTPD_KEY_FILE,
                                       out_passwd_fname=passwd_fname)

        self.backup_ssl_conf()
        self.configure_mod_ssl_certs()
        self.set_mod_ssl_protocol()
        self.set_mod_ssl_logdir()
        self.__add_include()

        self.cert = x509.load_certificate_from_file(paths.HTTPD_CERT_FILE)

        if self.ca_is_configured:
            db.untrack_server_cert(nickname)
            self.start_tracking_certificates()

        # remove nickname and CA certs from NSS db

        self.disable_nss_conf()
