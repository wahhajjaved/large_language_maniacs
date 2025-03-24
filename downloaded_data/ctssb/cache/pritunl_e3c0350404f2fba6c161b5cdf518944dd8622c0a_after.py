from constants import *
from exceptions import *
from pritunl import app_server
from cache import cache_db, persist_db
from cache_trie import CacheTrie
from config import Config
from log_entry import LogEntry
from event import Event
import uuid
import tarfile
import os
import subprocess
import logging
import hashlib
import base64
import utils
import struct
import hmac
import time
import threading
import json

logger = logging.getLogger(APP_NAME)

class User(Config):
    str_options = {'name', 'email', 'otp_secret', 'type'}
    bool_options = {'disabled'}
    default_options = {
        'name': 'undefined',
        'disabled': False,
    }
    chmod_mode = 0600
    cached = True
    cache_prefix = 'user'

    def __init__(self, org, id=None, name=None, email=None, type=None):
        Config.__init__(self)
        self.org = org

        if id is None:
            if type == CERT_CA:
                self.id = CA_CERT_ID
            elif type is None:
                raise AttributeError('Type must be specified')
            else:
                self.id = uuid.uuid4().hex
            self.name = name
            self.email = email
            self.type = type
        else:
            self.id = id

        if id is None:
            self._initialize()

    def __setattr__(self, name, value):
        if name == 'id':
            self.reqs_path = os.path.join(self.org.path, REQS_DIR,
                '%s.csr' % value)
            self.key_path = os.path.join(self.org.path, KEYS_DIR,
                '%s.key' % value)
            self.cert_path = os.path.join(self.org.path, CERTS_DIR,
                '%s.crt' % value)
            self.temp_key_archive_path = os.path.join(self.org.path,
                TEMP_DIR, '%s_%s.tar' % (value, uuid.uuid4().hex))
            self.set_path(os.path.join(self.org.path, USERS_DIR,
                '%s.conf' % value))

            self.temp_path = os.path.join(self.org.path, TEMP_DIR, value)
            self.ssl_conf_path = os.path.join(self.temp_path, OPENSSL_NAME)
            self.index_path = os.path.join(self.temp_path, INDEX_NAME)
            self.index_attr_path = os.path.join(
                self.temp_path, INDEX_ATTR_NAME)
            self.serial_path = os.path.join(self.temp_path, SERIAL_NAME)
        Config.__setattr__(self, name, value)

    def dict(self):
        return {
            'id': self.id,
            'organization': self.org.id,
            'organization_name': self.org.name,
            'name': self.name,
            'email': self.email,
            'type': self.type,
            'otp_secret': self.otp_secret,
            'disabled': self.disabled,
        }

    def _upgrade_0_10_9(self):
        if not self.type:
            logger.debug('Upgrading user to v0.10.9... %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
            })
            with open(self.cert_path, 'r') as cert_file:
                cert_data = cert_file.read()
                if 'CA:TRUE' in cert_data:
                    self.type = CERT_CA
                elif 'TLS Web Server Authentication' in cert_data:
                    self.type = CERT_SERVER
                else:
                    self.type = CERT_CLIENT
            self.commit()

    def _initialize(self):
        pool_user_id = None
        if self.type == CERT_CLIENT:
            pool_user_id = cache_db.set_pop(
                self.org.get_cache_key('users_client_pool'))
        elif self.type == CERT_SERVER:
            pool_user_id = cache_db.set_pop(
                self.org.get_cache_key('users_server_pool'))

        if pool_user_id:
            cache_db.publish('users_pool', 'update')
            self.id = pool_user_id
            self.commit()
        else:
            self._setup_openssl()
            self._cert_request()
            self._generate_otp_secret()
            self.commit()
            self._cert_create()
            self._clean_openssl()

        if self.type == CERT_CLIENT_POOL:
            cache_db.set_add(
                self.org.get_cache_key('users_client_pool'), self.id)
        elif self.type == CERT_SERVER_POOL:
            cache_db.set_add(
                self.org.get_cache_key('users_server_pool'), self.id)
        elif self.type != CERT_CA:
            cache_db.set_add(self.org.get_cache_key('users'), self.id)
            self._add_cache_trie_key()

            self.org.queue_sort_users_cache(update_ip_pool=True)
            if self.type == CERT_CLIENT:
                LogEntry(message='Created new user "%s".' % self.name)

    def _add_cache_trie_key(self):
        users_trie = CacheTrie(self.org.get_cache_key('users_trie'))
        users_trie.add_key_terms(self.name, '%s-%s-%s' % (
            self.id, self.type, self.name))

    def _remove_cache_trie_key(self):
        users_trie = CacheTrie(self.org.get_cache_key('users_trie'))
        users_trie.remove_key_terms(self.name, '%s-%s-%s' % (
            self.id, self.type, self.name))

    def _setup_openssl(self):
        if not os.path.exists(self.temp_path):
            os.makedirs(self.temp_path)

        with open(self.index_path, 'a'):
            os.utime(self.index_path, None)

        with open(self.index_attr_path, 'a'):
            os.utime(self.index_attr_path, None)

        with open(self.serial_path, 'w') as serial_file:
            serial_file.write('01\n')

        with open(self.ssl_conf_path, 'w') as conf_file:
            conf_file.write(CERT_CONF % (
                self.org.id,
                self.org.path,
                self.temp_path,
                app_server.key_bits,
                self.id,
            ))

    def _clean_openssl(self):
        utils.rmtree(self.temp_path)

    def _cert_request(self):
        try:
            args = [
                'openssl', 'req', '-new', '-batch',
                '-config', self.ssl_conf_path,
                '-out', self.reqs_path,
                '-keyout', self.key_path,
                '-reqexts', '%s_req_ext' % self.type.replace('_pool', ''),
            ]
            subprocess.check_call(args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            logger.exception('Failed to create user cert requests. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
            })
            raise
        os.chmod(self.key_path, 0600)

    def _cert_create(self):
        try:
            args = ['openssl', 'ca', '-batch']
            if self.type == CERT_CA:
                args += ['-selfsign']
            args += [
                '-config', self.ssl_conf_path,
                '-in', self.reqs_path,
                '-out', self.cert_path,
                '-extensions', '%s_ext' % self.type.replace('_pool', ''),
            ]
            subprocess.check_call(args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            logger.exception('Failed to create user cert. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
            })
            raise

    def get_cache_key(self, suffix=None):
        if not self.cache_prefix:
            raise AttributeError('Cached config object requires cache_prefix')
        key = self.cache_prefix + '-' + self.org.id + '_' + self.id
        if suffix:
            key += '-%s' % suffix
        return key

    def load(self, *args, **kwargs):
        Config.load(self, *args, **kwargs)
        if not self.otp_secret:
            logger.debug('User otp secret missing generating new one. %r' % {
                self._generate_otp_secret()
            })

    def _generate_otp_secret(self):
        sha_hash = hashlib.sha512()
        sha_hash.update(os.urandom(8192))
        byte_hash = sha_hash.digest()
        for i in xrange(6):
            sha_hash = hashlib.sha512()
            sha_hash.update(byte_hash)
            byte_hash = sha_hash.digest()
        self.otp_secret = base64.b32encode(byte_hash)[:DEFAULT_OTP_SECRET_LEN]
        self.commit()

    def generate_otp_secret(self):
        self._generate_otp_secret()
        Event(type=USERS_UPDATED, resource_id=self.org.id)

    def verify_otp_code(self, code, remote_ip=None):
        if remote_ip:
            otp_cache = cache_db.get(self.get_cache_key('otp_cache'))
            if otp_cache:
                cur_code, cur_remote_ip = otp_cache.split(',')
                if cur_code == code and cur_remote_ip == remote_ip:
                    cache_db.expire(self.get_cache_key('otp_cache'),
                        OTP_CACHE_TTL)
                    return True
                else:
                    cache_db.remove(self.get_cache_key('otp_cache'))

        otp_secret = self.otp_secret
        padding = 8 - len(otp_secret) % 8
        if padding != 8:
            otp_secret = otp_secret.ljust(len(otp_secret) + padding, '=')
        otp_secret = base64.b32decode(otp_secret.upper())
        valid_codes = []
        epoch = int(time.time() / 30)
        for epoch_offset in range(-1, 2):
            value = struct.pack('>q', epoch + epoch_offset)
            hmac_hash = hmac.new(otp_secret, value, hashlib.sha1).digest()
            offset = ord(hmac_hash[-1]) & 0x0F
            truncated_hash = hmac_hash[offset:offset + 4]
            truncated_hash = struct.unpack('>L', truncated_hash)[0]
            truncated_hash &= 0x7FFFFFFF
            truncated_hash %= 1000000
            valid_codes.append('%06d' % truncated_hash)
        if code not in valid_codes:
            return False

        used_codes = cache_db.dict_get_all(self.get_cache_key('otp'))
        for auth_time, used_code in used_codes.items():
            if int(time.time()) - int(auth_time) > 120:
                cache_db.dict_remove(self.get_cache_key('otp'), auth_time)
            if used_code == code:
                return False

        cache_db.dict_set(self.get_cache_key('otp'),
            str(int(time.time())), code)
        cache_db.expire(self.get_cache_key('otp_cache'), OTP_CACHE_TTL)
        cache_db.set(self.get_cache_key('otp_cache'),
            ','.join((code, remote_ip)))
        return True

    def _get_key_info_str(self, user_name, org_name, server_name):
        return json.dumps({
            'version': CLIENT_CONF_VER,
            'user': user_name,
            'organization': org_name,
            'server': server_name,
        })

    def _build_key_archive(self):
        user_key_arcname = '%s_%s.key' % (self.org.name, self.name)
        user_cert_arcname = '%s_%s.crt' % (self.org.name, self.name)

        tar_file = tarfile.open(self.temp_key_archive_path, 'w')
        try:
            tar_file.add(self.key_path, arcname=user_key_arcname)
            tar_file.add(self.cert_path, arcname=user_cert_arcname)
            for server in self.org.iter_servers():
                server_cert_arcname = '%s_%s_%s.crt' % (
                    self.org.name, self.name, server.name)
                server_conf_path = os.path.join(self.org.path,
                    TEMP_DIR, '%s_%s.ovpn' % (self.id, server.id))
                server_conf_arcname = '%s_%s_%s.ovpn' % (
                    self.org.name, self.name, server.name)
                server.generate_ca_cert()
                tar_file.add(server.ca_cert_path, arcname=server_cert_arcname)

                client_conf = OVPN_CLIENT_CONF % (
                    self._get_key_info_str(
                        self.name, self.org.name, server.name),
                    server.protocol,
                    server.public_address, server.port,
                    server_cert_arcname,
                    user_cert_arcname,
                    user_key_arcname,
                )

                if server.otp_auth:
                    client_conf += 'auth-user-pass\n'

                with open(server_conf_path, 'w') as ovpn_conf:
                    ovpn_conf.write(client_conf)
                tar_file.add(server_conf_path, arcname=server_conf_arcname)
                os.remove(server_conf_path)
        finally:
            tar_file.close()

        return self.temp_key_archive_path

    def _build_inline_key_archive(self):
        tar_file = tarfile.open(self.temp_key_archive_path, 'w')
        try:
            for server in self.org.iter_servers():
                server_conf_path = os.path.join(self.org.path,
                    TEMP_DIR, '%s_%s.ovpn' % (self.id, server.id))
                server_conf_arcname = '%s_%s_%s.ovpn' % (
                    self.org.name, self.name, server.name)
                server.generate_ca_cert()

                client_conf = OVPN_INLINE_CLIENT_CONF % (
                    self._get_key_info_str(
                        self.name, self.org.name, server.name),
                    server.protocol,
                    server.public_address, server.port,
                )

                if server.otp_auth:
                    client_conf += 'auth-user-pass\n'

                client_conf += '<ca>\n%s\n</ca>\n' % utils.get_cert_block(
                    server.ca_cert_path)
                client_conf += '<cert>\n%s\n</cert>\n' % utils.get_cert_block(
                    self.cert_path)
                client_conf += '<key>\n%s\n</key>\n' % open(
                    self.key_path).read().strip()

                with open(server_conf_path, 'w') as ovpn_conf:
                    os.chmod(server_conf_path, 0600)
                    ovpn_conf.write(client_conf)
                tar_file.add(server_conf_path, arcname=server_conf_arcname)
                os.remove(server_conf_path)
        finally:
            tar_file.close()

        return self.temp_key_archive_path

    def build_key_archive(self):
        if app_server.inline_certs:
            return self._build_inline_key_archive()
        else:
            return self._build_key_archive()

    def clean_key_archive(self):
        try:
            os.remove(self.temp_key_archive_path)
        except OSError:
            pass

    def build_key_conf(self, server_id):
        server = self.org.get_server(server_id)
        conf_name = '%s_%s_%s.ovpn' % (self.org.name, self.name, server.name)
        server.generate_ca_cert()

        client_conf = OVPN_INLINE_CLIENT_CONF % (
            self._get_key_info_str(self.name, self.org.name, server.name),
            server.protocol,
            server.public_address, server.port,
        )

        if server.otp_auth:
            client_conf += 'auth-user-pass\n'

        client_conf += '<ca>\n%s\n</ca>\n' % utils.get_cert_block(
            server.ca_cert_path)
        client_conf += '<cert>\n%s\n</cert>\n' % utils.get_cert_block(
            self.cert_path)
        client_conf += '<key>\n%s\n</key>\n' % open(
            self.key_path).read().strip()

        return {
            'name': conf_name,
            'conf': client_conf,
        }

    def send_key_email(self, key_link_domain):
        email_from = persist_db.dict_get('auth', 'email_from')
        email_api_key = persist_db.dict_get('auth', 'email_api_key')

        if not email_from or not email_api_key:
            raise EmailNotConfiguredError('Email not configured', {
                'org_id': self.org.id,
                'user_id': self.id,
            })

        key_link = self.org.create_user_key_link(self.id)
        response = utils.request.post(POSTMARK_SERVER,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Postmark-Server-Token': email_api_key,
            },
            json_data={
                'From': email_from,
                'To': self.email,
                'Subject': 'Pritunl VPN Key',
                'TextBody':  'Your vpn key can be downloaded from the ' +
                    'temporary link below. You may also directly import ' +
                    'your keys in the Pritunl client using the temporary ' +
                    'URI link.\n\n' +
                    'Key Link: ' + key_link_domain + key_link['view_url'] +
                    '\nURI Key Link: ' +
                    key_link_domain.replace('http', 'pt', 1) +
                    key_link['uri_url'],
            },
        )
        response = response.json()
        error_code = response.get('ErrorCode')
        error_msg = response.get('Message')

        if error_code == 0:
            pass
        elif error_code == 10:
            raise EmailApiKeyInvalid('Email api key invalid', {
                'org_id': self.org.id,
                'user_id': self.id,
                'error_code': error_code,
                'error_msg': error_msg,
            })
        elif error_code == 400:
            raise EmailFromInvalid('Email from invalid', {
                'org_id': self.org.id,
                'user_id': self.id,
                'error_code': error_code,
                'error_msg': error_msg,
            })
        else:
            logger.error('Unknown send user email error. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
                'error_code': error_code,
                'error_msg': error_msg,
            })
            raise EmailError('Unknown send user email error.', {
                'org_id': self.org.id,
                'user_id': self.id,
                'error_code': error_code,
                'error_msg': error_msg,
            })

    def clear_cache(self, org_data=True):
        if org_data:
            if self.type == CERT_CLIENT:
                cache_db.decrement(self.org.get_cache_key('user_count'))
            if self.type != CERT_CA:
                cache_db.set_remove(self.org.get_cache_key('users'), self.id)
                cache_db.list_remove(self.org.get_cache_key('users_sorted'),
                    self.id)
        if self.type in (CERT_CLIENT, CERT_SERVER):
            self._remove_cache_trie_key()
        cache_db.remove(self.get_cache_key('otp'))
        cache_db.remove(self.get_cache_key('otp_cache'))
        Config.clear_cache(self)

    def rename(self, name):
        self._remove_cache_trie_key()
        self.name = name
        self.commit()
        self._add_cache_trie_key()
        self.org.queue_sort_users_cache()
        Event(type=USERS_UPDATED, resource_id=self.org.id)

    def remove(self):
        self.clear_cache()
        name = self.name
        type = self.type
        self.org.queue_sort_users_cache(update_ip_pool=(type == CERT_CLIENT))

        try:
            os.remove(self.reqs_path)
        except OSError, error:
            logger.debug('Failed to remove user reqs file. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
                'path': self.reqs_path,
                'error': error,
            })

        try:
            os.remove(self.key_path)
        except OSError, error:
            logger.debug('Failed to remove user key file. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
                'path': self.reqs_path,
                'error': error,
            })

        try:
            os.remove(self.cert_path)
        except OSError, error:
            logger.debug('Failed to remove user cert file. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
                'path': self.reqs_path,
                'error': error,
            })

        try:
            os.remove(self.get_path())
        except OSError, error:
            logger.debug('Failed to remove user conf file. %r' % {
                'org_id': self.org.id,
                'user_id': self.id,
                'path': self.reqs_path,
                'error': error,
            })

        self._clean_openssl()

        Event(type=ORGS_UPDATED)
        Event(type=USERS_UPDATED, resource_id=self.org.id)
        if type == CERT_CLIENT:
            LogEntry(message='Deleted user "%s".' % name)

    @staticmethod
    def get_user(org, id):
        user = User(org, id=id)
        try:
            user.load()
        except IOError as exception:
            # File not found will happen when cached user list update is queued
            if exception.errno != 2:
                logger.exception('Failed to load user conf. %r' % {
                    'org_id': org.id,
                    'user_id': id,
                })
            return
        return user
