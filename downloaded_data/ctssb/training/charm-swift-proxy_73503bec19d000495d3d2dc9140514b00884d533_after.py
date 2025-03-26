import os
import uuid

from charmhelpers.core.hookenv import (
    config,
    log,
    relation_ids,
    related_units,
    relation_get,
    unit_get,
    service_name,
)
from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    ApacheSSLContext as SSLContext,
    context_complete,
)
from charmhelpers.contrib.hahelpers.cluster import (
    determine_api_port,
    determine_apache_port,
)
from charmhelpers.contrib.network.ip import (
    get_ipv6_addr
)
from charmhelpers.contrib.openstack.utils import get_host_ip


SWIFT_HASH_FILE = '/var/lib/juju/swift-hash-path.conf'
WWW_DIR = '/var/www/swift-rings'


class HAProxyContext(OSContextGenerator):
    interfaces = ['cluster']

    def __call__(self):
        """Extends the main charmhelpers HAProxyContext with a port mapping
        specific to this charm.
        Also used to extend cinder.conf context with correct api_listening_port
        """
        haproxy_port = config('bind-port')
        api_port = determine_apache_port(config('bind-port'),
                                         singlenode_mode=True)

        ctxt = {
            'service_ports': {'swift_api': [haproxy_port, api_port]},
        }
        return ctxt


class ApacheSSLContext(SSLContext):
    interfaces = ['https']
    external_ports = [config('bind-port')]
    service_namespace = 'swift'


class SwiftRingContext(OSContextGenerator):

    def __call__(self):
        allowed_hosts = []
        for relid in relation_ids('swift-storage'):
            for unit in related_units(relid):
                host = relation_get('private-address', unit, relid)
                if config('prefer-ipv6'):
                    host_ip = get_ipv6_addr(exc_list=[config('vip')])[0]
                else:
                    host_ip = get_host_ip(host)

                allowed_hosts.append(host_ip)

        ctxt = {
            'www_dir': WWW_DIR,
            'allowed_hosts': allowed_hosts
        }
        return ctxt


class SwiftIdentityContext(OSContextGenerator):
    interfaces = ['identity-service']

    def __call__(self):
        bind_port = config('bind-port')
        workers = config('workers')
        if workers == 0:
            import multiprocessing
            workers = multiprocessing.cpu_count()
        if config('prefer-ipv6'):
            proxy_ip = '[%s]' % get_ipv6_addr(exc_list=[config('vip')])[0]
            memcached_ip = 'ip6-localhost'
        else:
            proxy_ip = get_host_ip(unit_get('private-address'))
            memcached_ip = get_host_ip(unit_get('private-address'))

        ctxt = {
            'proxy_ip': proxy_ip,
            'memcached_ip': memcached_ip,
            'bind_port': determine_api_port(bind_port, singlenode_mode=True),
            'workers': workers,
            'operator_roles': config('operator-roles'),
            'delay_auth_decision': config('delay-auth-decision'),
            'node_timeout': config('node-timeout'),
            'recoverable_node_timeout': config('recoverable-node-timeout'),
        }

        ctxt['ssl'] = False

        auth_type = config('auth-type')
        auth_host = config('keystone-auth-host')
        admin_user = config('keystone-admin-user')
        admin_password = config('keystone-admin-user')
        if (auth_type == 'keystone' and auth_host
                and admin_user and admin_password):
            log('Using user-specified Keystone configuration.')
            ks_auth = {
                'auth_type': 'keystone',
                'auth_protocol': config('keystone-auth-protocol'),
                'keystone_host': auth_host,
                'auth_port': config('keystone-auth-port'),
                'service_user': admin_user,
                'service_password': admin_password,
                'service_tenant': config('keystone-admin-tenant-name')
            }
            ctxt.update(ks_auth)

        for relid in relation_ids('identity-service'):
            log('Using Keystone configuration from identity-service.')
            for unit in related_units(relid):
                ks_auth = {
                    'auth_type': 'keystone',
                    'auth_protocol': relation_get('auth_protocol',
                                                  unit, relid) or 'http',
                    'service_protocol': relation_get('service_protocol',
                                                     unit, relid) or 'http',
                    'keystone_host': relation_get('auth_host',
                                                  unit, relid),
                    'auth_port': relation_get('auth_port',
                                              unit, relid),
                    'service_user': relation_get('service_username',
                                                 unit, relid),
                    'service_password': relation_get('service_password',
                                                     unit, relid),
                    'service_tenant': relation_get('service_tenant',
                                                   unit, relid),
                    'service_port': relation_get('service_port',
                                                 unit, relid),
                    'admin_token': relation_get('admin_token',
                                                unit, relid),
                }
                if context_complete(ks_auth):
                    ctxt.update(ks_auth)

        return ctxt


class MemcachedContext(OSContextGenerator):

    def __call__(self):
        ctxt = {}
        if config('prefer-ipv6'):
            ctxt['memcached_ip'] = 'ip6-localhost'
        else:
            ctxt['memcached_ip'] = get_host_ip(unit_get('private-address'))

        return ctxt


def get_swift_hash():
    if os.path.isfile(SWIFT_HASH_FILE):
        with open(SWIFT_HASH_FILE, 'r') as hashfile:
            swift_hash = hashfile.read().strip()
    elif config('swift-hash'):
        swift_hash = config('swift-hash')
        with open(SWIFT_HASH_FILE, 'w') as hashfile:
            hashfile.write(swift_hash)
    else:
        swift_hash = str(uuid.uuid3(uuid.UUID(os.environ.get("JUJU_ENV_UUID")),
                                    service_name()))
        with open(SWIFT_HASH_FILE, 'w') as hashfile:
            hashfile.write(swift_hash)

    return swift_hash


class SwiftHashContext(OSContextGenerator):

    def __call__(self):
        ctxt = {
            'swift_hash': get_swift_hash()
        }
        return ctxt
