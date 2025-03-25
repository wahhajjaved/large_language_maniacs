from pritunl.constants import *
from pritunl.helpers import *
from pritunl import utils
from pritunl import mongo
from pritunl import sso
from pritunl import limiter
from pritunl import logger
from pritunl import ipaddress
from pritunl import settings
from pritunl import event
from pritunl import docdb

import datetime
import collections
import bson
import hashlib
import threading
import uuid

_limiter = limiter.Limiter('vpn', 'peer_limit', 'peer_limit_timeout')

class Clients(object):
    def __init__(self, server, instance, instance_com):
        self.server = server
        self.instance = instance
        self.instance_com = instance_com
        self.iroutes = {}
        self.iroutes_thread = {}
        self.iroutes_lock = threading.RLock()
        self.iroutes_index = collections.defaultdict(set)

        self.clients = docdb.DocDb(
            'user_id',
            'mac_addr',
            'virt_address',
        )
        self.clients_queue = collections.deque()

        self.ip_pool = []
        self.ip_network = ipaddress.IPv4Network(self.server.network)
        for ip_addr in self.ip_network.iterhosts():
            self.ip_pool.append(ip_addr)

    @cached_static_property
    def collection(cls):
        return mongo.get_collection('clients')

    def generate_client_conf(self, client_id, virt_address, user, reauth):
        from pritunl.server.utils import get_by_id

        client_conf = ''

        if user.link_server_id:
            link_usr_svr = get_by_id(user.link_server_id,
                fields=('_id', 'network', 'network_start',
                'network_end', 'local_networks'))

            client_conf += 'iroute %s %s\n' % utils.parse_network(
                link_usr_svr.network)
            for local_network in link_usr_svr.local_networks:
                if ':' in local_network:
                    client_conf += 'iroute-ipv6 %s\n' % local_network
                else:
                    client_conf += 'iroute %s %s\n' % utils.parse_network(
                        local_network)
        else:
            if self.server.mode == ALL_TRAFFIC:
                client_conf += 'push "redirect-gateway def1"\n'
                if self.server.ipv6:
                    client_conf += 'push "redirect-gateway-ipv6 def1"\n'
                    client_conf += 'push "route-ipv6 2000::/3"\n'

            if self.server.dns_mapping:
                client_conf += 'push "dhcp-option DNS %s"\n' % (
                    utils.get_network_gateway(self.server.network))

            for dns_server in self.server.dns_servers:
                client_conf += 'push "dhcp-option DNS %s"\n' % dns_server
            if self.server.search_domain:
                client_conf += 'push "dhcp-option DOMAIN %s"\n' % (
                    self.server.search_domain)

            client_conf += 'push "ip-win32 dynamic 0 3600"\n'

            network_links = user.get_network_links()
            for network_link in network_links:
                if self.reserve_iroute(client_id, network_link, True):
                    if ':' in network_link:
                        client_conf += 'iroute-ipv6 %s\n' % network_link
                    else:
                        client_conf += 'iroute %s %s\n' % utils.parse_network(
                            network_link)

            if network_links and not reauth:
                thread = threading.Thread(target=self.iroute_ping_thread,
                    args=(client_id, virt_address.split('/')[0]))
                thread.daemon = True
                thread.start()

            for network_link in self.server.network_links:
                if ':' in network_link:
                    client_conf += 'push "route-ipv6 %s"\n' % network_link
                else:
                    client_conf += 'push "route %s %s"\n' % (
                        utils.parse_network(network_link))

            for link_svr in self.server.iter_links(fields=(
                    '_id', 'network', 'local_networks', 'network_start',
                    'network_end')):
                client_conf += 'push "route %s %s"\n' % utils.parse_network(
                    link_svr.network)

                for local_network in link_svr.local_networks:
                    if ':' in local_network:
                        client_conf += 'push "route-ipv6 %s"\n' % (
                            local_network)
                    else:
                        client_conf += 'push "route %s %s"\n' % (
                            utils.parse_network(local_network))

        return client_conf

    def reserve_iroute(self, client_id, network, primary):
        reserved = False

        self.iroutes_lock.acquire()
        try:
            self.iroutes_index[client_id].add(network)
            iroute = self.iroutes.get(network)
            reconnect = None

            if iroute and self.clients.count_id(iroute['master']):
                if iroute['master'] == client_id:
                    reserved = True
                elif not primary or iroute['primary']:
                    if primary:
                        iroute['primary_slaves'].add(client_id)
                    else:
                        iroute['secondary_slaves'].add(client_id)
                else:
                    reconnect = iroute['master']
                    iroute['master'] = client_id
                    iroute['primary'] = primary
                    reserved = True
            else:
                self.iroutes[network] = {
                    'master': client_id,
                    'primary': primary,
                    'primary_slaves': set(),
                    'secondary_slaves': set(),
                }
                reserved = True
        finally:
            self.iroutes_lock.release()

        if reconnect:
            self.instance_com.push_output('Primary link available ' +
                'over secondary, relinking %s' % network)
            self.instance_com.client_kill(reconnect)

        return reserved

    def remove_iroutes(self, client_id):
        primary_reconnect = set()
        secondary_reconnect = set()

        self.iroutes_lock.acquire()
        try:
            if client_id not in self.iroutes_index:
                return

            networks = self.iroutes_index.pop(client_id)
            for network in networks:
                iroute = self.iroutes.get(network)
                if not iroute:
                    continue
                if iroute['master'] == client_id:
                    primary_reconnect |= iroute['primary_slaves']
                    secondary_reconnect |= iroute['secondary_slaves']
                    self.iroutes.pop(network)
                else:
                    if client_id in iroute['primary_slaves']:
                        iroute['primary_slaves'].remove(client_id)
                    if client_id in iroute['secondary_slaves']:
                        iroute['secondary_slaves'].remove(client_id)
        finally:
            self.iroutes_lock.release()

        for client_id in primary_reconnect:
            self.instance_com.client_kill(client_id)

        if primary_reconnect:
            time.sleep(5)

        for client_id in secondary_reconnect:
            self.instance_com.client_kill(client_id)

        if primary_reconnect or secondary_reconnect:
            self.instance_com.push_output('Gateway link ' +
                'changed, relinking gateways')

    def has_failover_iroute(self, client_id):
        self.iroutes_lock.acquire()

        try:
            if client_id in self.iroutes_index:
                for network in self.iroutes_index[client_id]:
                    iroute = self.iroutes.get(network)

                    if iroute['primary_slaves'] or iroute['primary_slaves']:
                        return True
            else:
                return True
        finally:
            self.iroutes_lock.release()

        return False

    def allow_client(self, client, org, user, reauth=False):
        client_id = client['client_id']
        key_id = client['key_id']
        org_id = client['org_id']
        user_id = client['user_id']
        device_id = client.get('device_id')
        device_name = client.get('device_name')
        platform = client.get('platform')
        mac_addr = client.get('mac_addr')
        remote_ip = client.get('remote_ip')
        address_dynamic = False

        if reauth:
            doc = self.clients.find_id(client_id)
            if not doc:
                self.instance_com.send_client_deny(client_id, key_id,
                    'Client connection info timed out')
                return
            virt_address = doc['virt_address']
            virt_address6 = doc['virt_address6']
        else:
            virt_address = self.server.get_ip_addr(org_id, user_id)
            if not self.server.multi_device:
                for client in self.clients.find({'user_id': user_id}):
                    self.instance_com.client_kill(client['id'])
            elif virt_address:
                if mac_addr:
                    for client in self.clients.find({'mac_addr': mac_addr}):
                        self.instance_com.client_kill(client['id'])

                if self.clients.find({'virt_address': virt_address}):
                    virt_address = None

            if not virt_address:
                while True:
                    try:
                        ip_addr = self.ip_pool.pop()
                    except IndexError:
                        break
                    ip_addr = '%s/%s' % (ip_addr, self.ip_network.prefixlen)

                    if not self.clients.find({'virt_address': ip_addr}):
                        virt_address = ip_addr
                        address_dynamic = True
                        break

            if not virt_address:
                self.instance_com.send_client_deny(client_id, key_id,
                    'Unable to assign ip address')
                return

            virt_address6 = self.server.ip4to6(virt_address)

            self.clients.insert({
                'id': client_id,
                'org_id': org_id,
                'org_name': org.name,
                'user_id': user_id,
                'user_name': user.name,
                'user_type': user.type,
                'device_id': device_id,
                'device_name': device_name,
                'platform': platform,
                'mac_addr': mac_addr,
                'otp_code': None,
                'virt_address': virt_address,
                'virt_address6': virt_address6,
                'real_address': remote_ip,
                'address_dynamic': address_dynamic,
            })

        client_conf = self.generate_client_conf(client_id,
            virt_address, user, reauth)

        client_conf += 'ifconfig-push %s %s\n' % utils.parse_network(
            virt_address)

        if self.server.ipv6:
            client_conf += 'ifconfig-ipv6-push %s\n' % virt_address6

        if self.server.debug:
            self.instance_com.push_output('Client conf %s:' % user_id)
            for conf_line in client_conf.split('\n'):
                if conf_line:
                    self.instance_com.push_output('  ' + conf_line)

        self.instance_com.send_client_auth(client_id, key_id, client_conf)

    def auth_push(self, type, client, org, user, reauth):
        client_id = client['client_id']
        key_id = client['key_id']
        remote_ip = client.get('remote_ip')
        platform = client.get('platform')
        device_name = client.get('device_name')

        def auth_thread():
            info={
                'Server': self.server.name,
            }

            platform_name = None
            if platform == 'linux':
                platform_name = 'Linux'
            elif platform == 'mac':
                platform_name = 'Apple'
            elif platform == 'win':
                platform_name = 'Windows'
            elif platform == 'chrome':
                platform_name = 'Chrome OS'

            if device_name:
                info['Device'] = '%s (%s)' % (device_name, platform_name)

            allow = False
            try:
                if type == DUO_AUTH:
                    allow, _ = sso.auth_duo(
                        user.name,
                        ipaddr=remote_ip,
                        type='Connection',
                        info=info,
                    )
                elif type == SAML_OKTA_AUTH:
                    allow = sso.auth_okta(
                        user.name,
                        ipaddr=remote_ip,
                        type='Connection',
                        info=info,
                    )
                else:
                    raise ValueError('Unkown push auth type')
            except:
                logger.exception('Push auth server error', 'server',
                    client_id=client_id,
                    user_id=user.id,
                    username=user.name,
                    server_id=self.server.id,
                )
                self.instance_com.push_output(
                    'ERROR Push auth server error client_id=%s' % client_id)
            try:
                if allow:
                    self.allow_client(client, org, user, reauth)
                else:
                    logger.LogEntry(message='User failed push ' +
                        'authentication "%s".' % user.name)
                    self.instance_com.send_client_deny(
                        client_id,
                        key_id,
                        'User failed push authentication',
                    )
            except:
                logger.exception('Push auth error', 'server',
                    client_id=client_id,
                    user_id=user.id,
                    server_id=self.server.id,
                )
                self.instance_com.push_output(
                    'ERROR Push auth error client_id=%s' % client_id)

        thread = threading.Thread(target=auth_thread)
        thread.daemon = True
        thread.start()

    def connect(self, client, reauth=False):
        client_id = None
        key_id = None
        try:
            client_id = client['client_id']
            key_id = client['key_id']
            org_id = client['org_id']
            user_id = client['user_id']
            otp_code = client.get('otp_code')
            remote_ip = client.get('remote_ip')

            if not _limiter.validate(remote_ip):
                self.instance_com.send_client_deny(client_id, key_id,
                    'Too many connect requests')
                return

            org = self.server.get_org(org_id, fields=['_id', 'name'])
            if not org:
                self.instance_com.send_client_deny(client_id, key_id,
                    'Organization is not valid')
                return

            user = org.get_user(user_id, fields=('_id', 'name', 'email',
                'type', 'auth_type', 'disabled', 'otp_secret',
                'link_server_id', 'bypass_secondary'))
            if not user:
                self.instance_com.send_client_deny(client_id, key_id,
                    'User is not valid')
                return

            if user.disabled:
                logger.LogEntry(message='User failed authentication, ' +
                    'disabled user "%s".' % (user.name))
                self.instance_com.send_client_deny(client_id, key_id,
                    'User is disabled')
                return

            if not user.bypass_secondary:
                if not user.auth_check():
                    logger.LogEntry(message='User failed authentication, ' +
                        'sso provider denied "%s".' % (user.name))
                    self.instance_com.send_client_deny(client_id, key_id,
                        'User failed authentication')
                    return

                if self.server.otp_auth and user.type == CERT_CLIENT and \
                        not user.verify_otp_code(otp_code, remote_ip):
                    logger.LogEntry(message='User failed two-step ' +
                        'authentication "%s".' % user.name)
                    self.instance_com.send_client_deny(client_id, key_id,
                        'Invalid OTP code')
                    return

                if settings.app.sso and DUO_AUTH in user.auth_type and \
                        DUO_AUTH in settings.app.sso:
                    self.auth_push(DUO_AUTH, client, org, user, reauth)
                    return
                elif settings.app.sso and \
                        user.auth_type == SAML_OKTA_AUTH and \
                        settings.app.sso == SAML_OKTA_AUTH:
                    self.auth_push(SAML_OKTA_AUTH, client, org, user, reauth)
                    return

            self.allow_client(client, org, user, reauth)
        except:
            logger.exception('Error parsing client connect', 'server',
                server_id=self.server.id,
            )
            if client_id and key_id:
                self.instance_com.send_client_deny(client_id, key_id,
                    'Error parsing client connect')

    def connected(self, client_id):
        client = self.clients.find_id(client_id)
        if not client:
            self.instance_com.push_output(
                'ERROR Unknown client connected client_id=%s' % client_id)
            self.instance_com.client_kill(client_id)
            return

        timestamp = utils.now()
        doc = {
            'user_id': client['user_id'],
            'server_id': self.server.id,
            'host_id': settings.local.host_id,
            'timestamp': timestamp,
            'platform': client['platform'],
            'type': client['user_type'],
            'device_name': client['device_name'],
            'mac_addr': client['mac_addr'],
            'network': self.server.network,
            'real_address': client['real_address'],
            'virt_address': client['virt_address'],
            'virt_address6': client['virt_address6'],
            'connected_since': int(timestamp.strftime('%s')),
        }

        if settings.local.sub_active and \
                settings.local.sub_plan == 'enterprise':
            domain_hash = hashlib.md5()
            domain_hash.update(
                client['user_name'].split('@')[0] + '.' + client['org_name'])
            domain_hash = bson.binary.Binary(domain_hash.digest(),
                subtype=bson.binary.MD5_SUBTYPE)
            doc['domain'] = domain_hash

        try:
            doc_id = self.collection.insert(doc)
        except:
            logger.exception('Error adding client', 'server',
                server_id=self.server.id,
            )
            self.instance_com.client_kill(client_id)
            return

        self.clients.update_id(client_id, {
            'doc_id': doc_id,
            'timestamp': datetime.datetime.now(),
        })

        self.clients_queue.append(client_id)

        self.instance_com.push_output(
            'User connected user_id=%s' % client['user_id'])
        self.send_event()

    def disconnected(self, client_id):
        client = self.clients.find_id(client_id)
        if not client:
            return
        self.clients.remove_id(client_id)
        self.remove_iroutes(client_id)

        virt_address = client['virt_address']
        if client['address_dynamic']:
            updated = self.clients.update({
                'id': client_id,
                'virt_address': virt_address,
            }, {
                'virt_address': None,
            })
            if updated:
                self.ip_pool.append(virt_address.split('/')[0])

        doc_id = client.get('doc_id')
        if doc_id:
            try:
                self.collection.remove({
                    '_id': doc_id,
                })
            except:
                logger.exception('Error removing client', 'server',
                    server_id=self.server.id,
                )

        self.instance_com.push_output(
            'User disconnected user_id=%s' % client['user_id'])
        self.send_event()

    def disconnect_user(self, user_id):
        for client in self.clients.find({'user_id': user_id}):
            self.instance_com.client_kill(client['id'])

    def send_event(self):
        for org_id in self.server.organizations:
            event.Event(type=USERS_UPDATED, resource_id=org_id)
        event.Event(type=HOSTS_UPDATED, resource_id=settings.local.host_id)
        event.Event(type=SERVERS_UPDATED)

    def interrupter_sleep(self, length):
        if check_global_interrupt() or self.instance.sock_interrupt:
            return True
        while True:
            sleep = min(0.5, length)
            time.sleep(sleep)
            length -= sleep
            if check_global_interrupt() or self.instance.sock_interrupt:
                return True
            elif length <= 0:
                return False

    @interrupter
    def iroute_ping_thread(self, client_id, virt_address):
        thread_id = uuid.uuid4().hex
        self.iroutes_thread[client_id] = thread_id

        yield interrupter_sleep(6)

        while True:
            yield interrupter_sleep(self.server.link_ping_interval)

            if client_id not in self.iroutes_index or \
                    self.iroutes_thread.get(client_id) != thread_id:
                break

            if not self.has_failover_iroute(client_id):
                continue

            latency = utils.ping(virt_address,
                timeout=self.server.link_ping_timeout)
            if latency is None and self.has_failover_iroute(client_id):
                self.instance_com.push_output(
                    'Gateway link timeout on %s' % virt_address)
                self.instance_com.client_kill(client_id)
                break

    @interrupter
    def ping_thread(self):
        try:
            while True:
                try:
                    try:
                        client_id = self.clients_queue.popleft()
                    except IndexError:
                        if self.interrupter_sleep(
                                settings.vpn.client_ttl - 60):
                            return
                        continue

                    client = self.clients.find_id(client_id)
                    if not client:
                        continue

                    diff = datetime.timedelta(
                        seconds=settings.vpn.client_ttl - 60) - \
                           (datetime.datetime.now() - client['timestamp'])

                    if diff.seconds > settings.vpn.client_ttl:
                        logger.error('Client ping time diff out of range',
                            'server',
                            time_diff=diff.seconds,
                            server_id=self.server.id,
                            instance_id=self.instance.id,
                        )
                        if self.interrupter_sleep(10):
                            return
                    elif diff.seconds > 1:
                        if self.interrupter_sleep(diff.seconds):
                            return

                    if self.instance.sock_interrupt:
                        return

                    try:
                        updated = self.clients.update_id(client_id, {
                            'timestamp': datetime.datetime.now(),
                        })
                        if not updated:
                            continue

                        response = self.collection.update({
                            '_id': client['doc_id'],
                        }, {
                            '$set': {
                                'timestamp': utils.now(),
                            },
                        })
                        if not response['updatedExisting']:
                            logger.error('Client lost unexpectedly', 'server',
                                server_id=self.server.id,
                                instance_id=self.instance.id,
                            )
                            self.instance_com.client_kill(client_id)
                            continue
                    except:
                        self.clients_queue.append(client_id)
                        logger.exception('Failed to update client', 'server',
                            server_id=self.server.id,
                            instance_id=self.instance.id,
                        )
                        yield interrupter_sleep(1)
                        continue

                    self.clients_queue.append(client_id)

                    yield
                    if self.instance.sock_interrupt:
                        return
                except GeneratorExit:
                    raise
                except:
                    logger.exception('Error in client thread', 'server',
                        server_id=self.server.id,
                        instance_id=self.instance.id,
                    )
                    yield interrupter_sleep(3)
                    if self.instance.sock_interrupt:
                        return
        finally:
            doc_ids = []
            for client in self.clients.find_all():
                doc_id = client.get('doc_id')
                if doc_id:
                    doc_ids.append(doc_id)

            try:
                self.collection.remove({
                    '_id': {'$in': doc_ids},
                })
            except:
                logger.exception('Error removing client', 'server',
                    server_id=self.server.id,
                )
