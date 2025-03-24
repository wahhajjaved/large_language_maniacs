#!/usr/bin/python
# TODO: Support changes to root and sstuser passwords

import sys
import json
import os
import socket

from charmhelpers.core.hookenv import (
    Hooks, UnregisteredHookError,
    is_relation_made,
    log,
    relation_get,
    relation_set,
    relation_ids,
    related_units,
    unit_get,
    config,
    remote_unit,
    relation_type,
    INFO
)
from charmhelpers.core.host import (
    service_restart,
    file_hash,
    write_file,
    lsb_release
)
from charmhelpers.fetch import (
    apt_update,
    apt_install,
    add_source,
)
from charmhelpers.contrib.peerstorage import (
    peer_echo,
    peer_store_and_set,
    peer_retrieve_by_prefix
)
from percona_utils import (
    PACKAGES,
    MY_CNF,
    setup_percona_repo,
    render_template,
    get_host_ip,
    get_cluster_hosts,
    configure_sstuser,
    seeded, mark_seeded,
    configure_mysql_root_password,
    relation_clear,
    assert_charm_supports_ipv6,
    unit_sorted
)
from mysql import (
    get_allowed_units,
    get_mysql_password,
    parse_config,
)
from charmhelpers.contrib.hahelpers.cluster import (
    peer_units,
    oldest_peer,
    eligible_leader,
    is_clustered,
    is_leader
)
from mysql import configure_db
from charmhelpers.payload.execd import execd_preinstall
from charmhelpers.contrib.network.ip import (
    is_address_in_network,
    get_address_in_network,
    get_netmask_for_address,
    get_ipv6_addr
)

hooks = Hooks()

LEADER_RES = 'grp_percona_cluster'


@hooks.hook('install')
def install():
    execd_preinstall()
    if config('source') is None and \
            lsb_release()['DISTRIB_CODENAME'] < 'trusty':
        setup_percona_repo()
    elif config('source') is not None:
        add_source(config('source'))

    configure_mysql_root_password(config('root-password'))
    render_config()  # Render base configuation (no cluster)
    apt_update(fatal=True)
    apt_install(PACKAGES, fatal=True)
    configure_sstuser(config('sst-password'))


def render_config(clustered=False, hosts=[]):
    if not os.path.exists(os.path.dirname(MY_CNF)):
        os.makedirs(os.path.dirname(MY_CNF))
    context = {
        'cluster_name': 'juju_cluster',
        'private_address': get_host_ip(),
        'clustered': clustered,
        'cluster_hosts': ",".join(hosts),
        'sst_meethod' : 'xtrabackup',
        'sst_password': get_mysql_password(username='sstuser',
                                           password=config('sst-password'))
    }

    if config('prefer-ipv6'):
        # NOTE(hopem): this is a kludge to get percona working with ipv6.
        # See lp 1380747 for more info. This is intended as a stop gap until
        # percona package is fixed to support ipv6.
        context['bind_address'] = '::'
        context['wsrep_provider_options'] = 'gmcast.listen_addr=tcp://:::4567;'
        context['ipv6'] = True
    else:
        context['ipv6'] = False

    context.update(parse_config())
    write_file(path=MY_CNF,
               content=render_template(os.path.basename(MY_CNF), context),
               perms=0o444)


@hooks.hook('upgrade-charm')
@hooks.hook('config-changed')
def config_changed():
    if config('prefer-ipv6'):
        assert_charm_supports_ipv6()

    hosts = get_cluster_hosts()
    clustered = len(hosts) > 1
    pre_hash = file_hash(MY_CNF)
    render_config(clustered, hosts)
    if file_hash(MY_CNF) != pre_hash:
        oldest = oldest_peer(peer_units())
        if clustered and not oldest and not seeded():
            # Bootstrap node into seeded cluster
            service_restart('mysql')
            mark_seeded()
        elif not clustered:
            # Restart with new configuration
            service_restart('mysql')
    # Notify any changes to the access network
    for r_id in relation_ids('shared-db'):
        for unit in related_units(r_id):
            shared_db_changed(r_id, unit)


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    if config('prefer-ipv6'):
        addr = get_ipv6_addr(exc_list=[config('vip')])[0]
        relation_settings = {'private-address': addr,
                             'hostname': socket.gethostname()}
        log("Setting cluster relation: '%s'" % (relation_settings),
            level=INFO)
        relation_set(relation_id=relation_id,
                     relation_settings=relation_settings)


@hooks.hook('cluster-relation-departed')
@hooks.hook('cluster-relation-changed')
def cluster_changed():
    # Need to make sure hostname is excluded to build inclusion list (paying
    # attention to those excluded by default in peer_echo().
    # TODO(dosaboy): extend peer_echo() to support providing exclusion list as
    #                well as inclusion list.
    rdata = relation_get()
    inc_list = []
    for attr in rdata.iterkeys():
        if attr not in ['hostname', 'private-address', 'public-address']:
            inc_list.append(attr)

    peer_echo(includes=inc_list)

    config_changed()


# TODO: This could be a hook common between mysql and percona-cluster
@hooks.hook('db-relation-changed')
@hooks.hook('db-admin-relation-changed')
def db_changed(relation_id=None, unit=None, admin=None):
    if not eligible_leader(LEADER_RES):
        log('Service is peered, clearing db relation'
            ' as this service unit is not the leader')
        relation_clear(relation_id)
        return

    if is_clustered():
        db_host = config('vip')
    else:
        if config('prefer-ipv6'):
            db_host = get_ipv6_addr(exc_list=[config('vip')])[0]
        else:
            db_host = unit_get('private-address')

    if admin not in [True, False]:
        admin = relation_type() == 'db-admin'
    database_name, _ = remote_unit().split("/")
    username = database_name
    password = configure_db(relation_get('private-address',
                                         unit=unit,
                                         rid=relation_id),
                            database_name,
                            username,
                            admin=admin)

    relation_set(relation_id=relation_id,
                 relation_settings={
                     'user': username,
                     'password': password,
                     'host': db_host,
                     'database': database_name,
                 }
                 )


# TODO: This could be a hook common between mysql and percona-cluster
@hooks.hook('shared-db-relation-changed')
def shared_db_changed(relation_id=None, unit=None):
    if not eligible_leader(LEADER_RES):
        relation_clear(relation_id)
        # Each unit needs to set the db information otherwise if the unit
        # with the info dies the settings die with it Bug# 1355848
        if is_relation_made('cluster'):
            for rel_id in relation_ids('shared-db'):
                peerdb_settings = \
                    peer_retrieve_by_prefix(rel_id, exc_list=['hostname'])
                passwords = [key for key in peerdb_settings.keys()
                             if 'password' in key.lower()]
                if len(passwords) > 0:
                    relation_set(relation_id=rel_id, **peerdb_settings)
        log('Service is peered, clearing shared-db relation'
            ' as this service unit is not the leader')
        return

    settings = relation_get(unit=unit,
                            rid=relation_id)
    if is_clustered():
        db_host = config('vip')
    else:
        if config('prefer-ipv6'):
            db_host = get_ipv6_addr(exc_list=[config('vip')])[0]
        else:
            db_host = unit_get('private-address')

    access_network = config('access-network')

    singleset = set([
        'database',
        'username',
        'hostname'
    ])

    if singleset.issubset(settings):
        # Process a single database configuration

        # Hostname can be json-encoded list of hostnames
        try:
            hostname = json.loads(settings['hostname'])
        except ValueError:
            hostname = settings['hostname']

        if isinstance(hostname, list):
            for host in hostname:
                password = configure_db(host,
                                        settings['database'],
                                        settings['username'])
        else:
            password = configure_db(hostname,
                                    settings['database'],
                                    settings['username'])

        allowed_units = " ".join(unit_sorted(get_allowed_units(
            settings['database'],
            settings['username'])))

        if (access_network is not None and
                is_address_in_network(access_network,
                                      get_host_ip(settings['hostname']))):
            db_host = get_address_in_network(access_network)
        peer_store_and_set(relation_id=relation_id,
                           db_host=db_host,
                           password=password,
                           allowed_units=allowed_units)
    else:
        # Process multiple database setup requests.
        # from incoming relation data:
        #  nova_database=xxx nova_username=xxx nova_hostname=xxx
        #  quantum_database=xxx quantum_username=xxx quantum_hostname=xxx
        # create
        # {
        #   "nova": {
        #        "username": xxx,
        #        "database": xxx,
        #        "hostname": xxx
        #    },
        #    "quantum": {
        #        "username": xxx,
        #        "database": xxx,
        #        "hostname": xxx
        #    }
        # }
        #
        databases = {}
        for k, v in settings.iteritems():
            db = k.split('_')[0]
            x = '_'.join(k.split('_')[1:])
            if db not in databases:
                databases[db] = {}
            databases[db][x] = v

        return_data = {}
        for db in databases:
            if singleset.issubset(databases[db]):
                try:
                    hostname = json.loads(databases[db]['hostname'])
                except ValueError:
                    hostname = databases[db]['hostname']

                if isinstance(hostname, list):
                    for host in hostname:
                        password = configure_db(host,
                                                databases[db]['database'],
                                                databases[db]['username'])
                else:
                    password = configure_db(hostname,
                                            databases[db]['database'],
                                            databases[db]['username'])

                return_data['_'.join([db, 'password'])] = password

                return_data['_'.join([db, 'allowed_units'])] = \
                    " ".join(unit_sorted(get_allowed_units(
                        databases[db]['database'],
                        databases[db]['username'])))

                if (access_network is not None and
                        is_address_in_network(
                            access_network,
                            get_host_ip(databases[db]['hostname']))):
                    db_host = get_address_in_network(access_network)
        if len(return_data) > 0:
            peer_store_and_set(relation_id=relation_id,
                               **return_data)
            peer_store_and_set(relation_id=relation_id,
                               db_host=db_host)
    peer_store_and_set(relation_id=relation_id,
                       relation_settings={'access-network': access_network})


@hooks.hook('ha-relation-joined')
def ha_relation_joined():
    vip = config('vip')
    vip_iface = config('vip_iface')
    vip_cidr = config('vip_cidr')
    corosync_bindiface = config('ha-bindiface')
    corosync_mcastport = config('ha-mcastport')

    if None in [vip, vip_cidr, vip_iface]:
        log('Insufficient VIP information to configure cluster')
        sys.exit(1)

    if config('prefer-ipv6'):
        res_mysql_vip = 'ocf:heartbeat:IPv6addr'
        vip_params = 'params ipv6addr="%s" cidr_netmask="%s" nic="%s"' % \
                     (vip, get_netmask_for_address(vip), vip_iface)
    else:
        res_mysql_vip = 'ocf:heartbeat:IPaddr2'
        vip_params = 'params ip="%s" cidr_netmask="%s" nic="%s"' % \
                     (vip, vip_cidr, vip_iface)

    resources = {'res_mysql_vip': res_mysql_vip}
    resource_params = {'res_mysql_vip': vip_params}
    groups = {'grp_percona_cluster': 'res_mysql_vip'}

    for rel_id in relation_ids('ha'):
        relation_set(relation_id=rel_id,
                     corosync_bindiface=corosync_bindiface,
                     corosync_mcastport=corosync_mcastport,
                     resources=resources,
                     resource_params=resource_params,
                     groups=groups)


@hooks.hook('ha-relation-changed')
def ha_relation_changed():
    clustered = relation_get('clustered')
    if (clustered and is_leader(LEADER_RES)):
        log('Cluster configured, notifying other services')
        # Tell all related services to start using the VIP
        for r_id in relation_ids('shared-db'):
            for unit in related_units(r_id):
                shared_db_changed(r_id, unit)
        for r_id in relation_ids('db'):
            for unit in related_units(r_id):
                db_changed(r_id, unit, admin=False)
        for r_id in relation_ids('db-admin'):
            for unit in related_units(r_id):
                db_changed(r_id, unit, admin=True)
    else:
        # Clear any settings data for non-leader units
        log('Cluster configured, not leader, clearing relation data')
        for r_id in relation_ids('shared-db'):
            relation_clear(r_id)
        for r_id in relation_ids('db'):
            relation_clear(r_id)
        for r_id in relation_ids('db-admin'):
            relation_clear(r_id)


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
