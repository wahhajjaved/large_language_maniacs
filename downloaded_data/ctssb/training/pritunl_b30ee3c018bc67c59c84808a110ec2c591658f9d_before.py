from pritunl.server.output import ServerOutput
from pritunl.server.output_link import ServerOutputLink
from pritunl.server.bandwidth import ServerBandwidth
from pritunl.server.ip_pool import ServerIpPool

from pritunl.constants import *
from pritunl.exceptions import *
from pritunl.descriptors import *
from pritunl import settings
from pritunl import ipaddress
from pritunl import logger
from pritunl import host
from pritunl import utils
from pritunl import mongo
from pritunl import queue
from pritunl import transaction
from pritunl import event
from pritunl import messenger
from pritunl import organization
from pritunl import listener

import os
import signal
import time
import datetime
import subprocess
import threading
import traceback
import re
import bson
import pymongo
import random
import collections

_resource_lock = collections.defaultdict(threading.Lock)

class Server(mongo.MongoObject):
    fields = {
        'name',
        'network',
        'network_lock',
        'port',
        'protocol',
        'dh_param_bits',
        'mode',
        'local_networks',
        'dns_servers',
        'search_domain',
        'otp_auth',
        'lzo_compression',
        'debug',
        'organizations',
        'hosts',
        'primary_organization',
        'primary_user',
        'ca_certificate',
        'dh_params',
        'status',
        'start_timestamp',
        'replica_count',
        'instances',
        'instances_count',
    }
    fields_default = {
        'dns_servers': [],
        'otp_auth': False,
        'lzo_compression': False,
        'debug': False,
        'organizations': [],
        'hosts': [],
        'status': False,
        'replica_count': 1,
        'instances': [],
        'instances_count': 0,
    }
    cache_prefix = 'server'

    def __init__(self, name=None, network=None, port=None, protocol=None,
            dh_param_bits=None, mode=None, local_networks=None,
            dns_servers=None, search_domain=None, otp_auth=None,
            lzo_compression=None, debug=None, **kwargs):
        mongo.MongoObject.__init__(self, **kwargs)

        self._cur_event = None
        self._last_event = 0
        self._orig_network = self.network
        self._orgs_changed = False
        self._clients = None
        self._client_count = 0
        self._temp_path = utils.get_temp_path()
        self._instance_id = str(bson.ObjectId())
        self.ip_pool = ServerIpPool(self)

        if name is not None:
            self.name = name
        if network is not None:
            self.network = network
        if port is not None:
            self.port = port
        if protocol is not None:
            self.protocol = protocol
        if dh_param_bits is not None:
            self.dh_param_bits = dh_param_bits
        if mode is not None:
            self.mode = mode
        if local_networks is not None:
            self.local_networks = local_networks
        if dns_servers is not None:
            self.dns_servers = dns_servers
        if search_domain is not None:
            self.search_domain = search_domain
        if otp_auth is not None:
            self.otp_auth = otp_auth
        if lzo_compression is not None:
            self.lzo_compression = lzo_compression
        if debug is not None:
            self.debug = debug

    @cached_static_property
    def collection(cls):
        return mongo.get_collection('servers')

    @cached_static_property
    def user_collection(cls):
        return mongo.get_collection('users')

    @cached_static_property
    def host_collection(cls):
        return mongo.get_collection('hosts')

    def dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'uptime': self.uptime,
            'users_online': self.users_online,
            'user_count': self.user_count,
            'network': self.network,
            'port': self.port,
            'protocol': self.protocol,
            'dh_param_bits': self.dh_param_bits,
            'mode': self.mode,
            'local_networks': self.local_networks,
            'dns_servers': self.dns_servers,
            'search_domain': self.search_domain,
            'otp_auth': True if self.otp_auth else False,
            'lzo_compression': self.lzo_compression,
            'debug': True if self.debug else False,
        }

    @property
    def uptime(self):
        if not self.start_timestamp:
            return
        return max((utils.now() - self.start_timestamp).seconds, 1)

    @cached_property
    def users_online(self):
        clients = set()
        for instance in self.instances:
            clients = clients |set(instance['clients'])
        return len(clients)

    @cached_property
    def user_count(self):
        return organization.get_user_count_multi(org_ids=self.organizations)

    @cached_property
    def bandwidth(self):
        return ServerBandwidth(self.id)

    @cached_property
    def output(self):
        return ServerOutput(self.id)

    @cached_property
    def output_link(self):
        return ServerOutputLink(self.id)

    def initialize(self):
        self.generate_dh_param()

    def queue_dh_params(self, block=False):
        queue.start('dh_params', block=block, server_id=self.id,
            dh_param_bits=self.dh_param_bits, priority=HIGH)
        self.dh_params = None

        if block:
            self.load()

    def get_cache_key(self, suffix=None):
        if not self.cache_prefix:
            raise AttributeError('Cached config object requires cache_prefix')
        key = self.cache_prefix + '-' + self.id
        if suffix:
            key += '-%s' % suffix
        return key

    def get_ip_set(self, org_id, user_id):
        return self.ip_pool.get_ip_addr(org_id, user_id)

    def assign_ip_addr(self, org_id, user_id):
        if not self.network_lock:
            self.ip_pool.assign_ip_addr(org_id, user_id)
        else:
            queue.start('assign_ip_addr', server_id=self.id, org_id=org_id,
                user_id=user_id)

    def unassign_ip_addr(self, org_id, user_id):
        if not self.network_lock:
            self.ip_pool.unassign_ip_addr(org_id, user_id)
        else:
            queue.start('unassign_ip_addr', server_id=self.id, org_id=org_id,
                user_id=user_id)

    def get_key_remotes(self):
        remotes = []
        spec = {
            '_id': {'$in': self.hosts},
        }
        project = {
            '_id': False,
            'public_address': True,
        }

        for doc in self.host_collection.find(spec, project):
            remotes.append('remote %s %s' % (
                doc['public_address'], server.port))

        random.shuffle(remotes)

        return '\n'.join(remotes)

    def commit(self, *args, **kwargs):
        tran = None

        if self.network != self._orig_network:
            tran = transaction.Transaction()
            if self.network_lock:
                raise ServerNetworkLocked('Server network is locked', {
                    'server_id': self.id,
                    'lock_id': self.network_lock,
                })
            else:
                queue_ip_pool = queue.start('assign_ip_pool',
                    transaction=tran,
                    server_id=self.id,
                    network=self.network,
                    old_network=self._orig_network,
                )
                self.network_lock = queue_ip_pool.id
        elif self._orgs_changed:
            # TODO update ip pool
            pass

        mongo.MongoObject.commit(self, transaction=tran,
            *args, **kwargs)

        if tran:
            messenger.publish('queue', 'queue_updated',
                transaction=tran)
            tran.commit()

    def remove(self):
        self.remove_primary_user()
        mongo.MongoObject.remove(self)

    def create_primary_user(self):
        logger.debug('Creating primary user. %r' % {
            'server_id': self.id,
        })

        try:
            org = self.iter_orgs().next()
        except StopIteration:
            raise ServerMissingOrg('Primary user cannot be created ' + \
                'without any organizations', {
                    'server_id': self.id,
                })

        user = org.new_user(name=SERVER_USER_PREFIX + self.id,
            type=CERT_SERVER, resource_id=self.id)

        self.primary_organization = org.id
        self.primary_user = user.id
        self.commit(('primary_organization', 'primary_user'))

    def remove_primary_user(self):
        logger.debug('Removing primary user. %r' % {
            'server_id': self.id,
        })

        self.user_collection.remove({
            'resource_id': self.id,
        })

        self.primary_organization = None
        self.primary_user = None

    def add_org(self, org_id):
        if not isinstance(org_id, basestring):
            org_id = org_id.id
        logger.debug('Adding organization to server. %r' % {
            'server_id': self.id,
            'org_id': org_id,
        })
        if org_id in self.organizations:
            logger.debug('Organization already on server, skipping. %r' % {
                'server_id': self.id,
                'org_id': org_id,
            })
            return
        self.organizations.append(org_id)
        self.changed.add('organizations')
        self.generate_ca_cert()
        self._orgs_changed = True

    def remove_org(self, org_id):
        if not isinstance(org_id, basestring):
            org_id = org_id.id
        if org_id not in self.organizations:
            return
        logger.debug('Removing organization from server. %r' % {
            'server_id': self.id,
            'org_id': org_id,
        })
        if self.primary_organization == org_id:
            self.remove_primary_user()
        try:
            self.organizations.remove(org_id)
        except ValueError:
            pass
        self.changed.add('organizations')
        self.generate_ca_cert()
        self._orgs_changed = True

    def iter_orgs(self):
        for org_id in self.organizations:
            org = organization.get_org(id=org_id)
            if org:
                yield org
            else:
                logger.error('Removing non-existent organization ' +
                    'from server. %r' % {
                        'server_id': self.id,
                        'org_id': org_id,
                    })
                self.remove_org(org_id)
                self.commit('organizations')
                event.Event(type=SERVER_ORGS_UPDATED, resource_id=self.id)

    def get_org(self, org_id):
        if org_id in self.organizations:
            return organization.get_org(id=org_id)

    def add_host(self, host_id):
        if not isinstance(host_id, basestring):
            host_id = host_id.id
        logger.debug('Adding host to server. %r' % {
            'server_id': self.id,
            'host_id': host_id,
        })
        if host_id in self.hosts:
            logger.debug('Host already on server, skipping. %r' % {
                'server_id': self.id,
                'host_id': host_id,
            })
            return
        self.hosts.append(host_id)
        self.changed.add('hosts')

    def remove_host(self, host_id):
        if not isinstance(host_id, basestring):
            host_id = host_id.id
        if host_id not in self.hosts:
            return
        logger.debug('Removing host from server. %r' % {
            'server_id': self.id,
            'host_id': host_id,
        })
        try:
            self.hosts.remove(host_id)
        except ValueError:
            pass
        self.changed.add('hosts')

    def iter_hosts(self):
        for host_id in self.hosts:
            hst = host.get_host(id=host_id)
            if hst:
                yield hst
            else:
                logger.error('Removing non-existent host ' +
                    'from server. %r' % {
                        'server_id': self.id,
                        'host_id': host_id,
                    })
                self.remove_host(host_id)
                self.commit('hosts')
                event.Event(type=SERVER_HOSTS_UPDATED, resource_id=self.id)

    def get_host(self, host_id):
        if host_id in self.hosts:
            return host.get_host(id=host_id)

    def generate_dh_param(self):
        reserved = queue.reserve('pooled_dh_params', svr=self)
        if not reserved:
            reserved = queue.reserve('queued_dh_params', svr=self)

        if reserved:
            queue.start('dh_params', dh_param_bits=self.dh_param_bits,
                priority=LOW)
            return

        self.queue_dh_params()

    def generate_ca_cert(self):
        ca_certificate = ''
        for org in self.iter_orgs():
            ca_certificate += org.ca_certificate
        self.ca_certificate = ca_certificate

    def get_cursor_id(self):
        return messenger.get_cursor_id('servers')

    def publish(self, message, transaction=None, extra=None):
        extra = extra or {}
        extra.update({
            'server_id': self.id,
        })
        messenger.publish('servers', message,
            extra=extra, transaction=transaction)

    def subscribe(self, cursor_id=None, timeout=None):
        for msg in messenger.subscribe('servers', cursor_id=cursor_id,
                timeout=timeout):
            if msg.get('server_id') == self.id:
                yield msg

    def start(self, timeout=VPN_OP_TIMEOUT):
        cursor_id = self.get_cursor_id()

        if self.status:
            return

        if not self.organizations:
            raise ServerMissingOrg('Server cannot be started ' + \
                'without any organizations', {
                    'server_id': self.id,
                })

        start_timestamp = utils.now()
        response = self.collection.update({
            '_id': bson.ObjectId(self.id),
            'status': False,
            'instances_count': 0,
        }, {'$set': {
            'status': True,
            'start_timestamp': start_timestamp,
        }})

        if not response['updatedExisting']:
            raise ServerInstanceSet('Server instances already running. %r', {
                    'server_id': self.id,
                })
        self.status = True
        self.start_timestamp = start_timestamp

        started = False
        stopped_count = 0
        try:
            prefered_host = random.choice(self.hosts)
            self.publish('start', extra={
                'prefered_host': prefered_host,
            })

            for msg in self.subscribe(cursor_id=cursor_id, timeout=timeout):
                message = msg['message']
                if message == 'started':
                    started = True
                    break
                elif message == 'stopped':
                    stopped_count += 1
                    if stopped_count >= self.replica_count:
                        break

            if not started:
                if stopped_count:
                    raise ServerStartError('Server failed to start', {
                        'server_id': self.id,
                    })
                else:
                    raise ServerStartError('Server start timed out', {
                            'server_id': self.id,
                        })
            self.instances_count = started
        except:
            self.publish('force_stop')
            self.collection.update({
                '_id': bson.ObjectId(self.id),
            }, {'$set': {
                'status': False,
                'instances': [],
                'instances_count': 0,
            }})
            self.status = False
            self.instances = []
            self.instances_count = 0
            raise

    def stop(self, timeout=VPN_OP_TIMEOUT, force=False):
        cursor_id = self.get_cursor_id()

        logger.debug('Stopping server. %r' % {
            'server_id': self.id,
        })

        if not self.status:
            return

        response = self.collection.update({
            '_id': bson.ObjectId(self.id),
            'status': True,
        }, {'$set': {
            'status': False,
            'start_timestamp': None,
            'instances': [],
            'instances_count': 0,
        }})

        if not response['updatedExisting']:
            raise ServerStopError('Server not running', {
                    'server_id': self.id,
                })
        self.status = False

        if force:
            self.publish('force_stop')
        else:
            self.publish('stop')

    def force_stop(self, timeout=VPN_OP_TIMEOUT):
        self.stop(timeout=timeout, force=True)

    def restart(self):
        if not self.status:
            self.start()
            return
        logger.debug('Restarting server. %r' % {
            'server_id': self.id,
        })
        self.stop()
        self.start()
