#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.


import time
import copy
import inspect
import itertools

from cloudify import ctx
from cloudify.manager import get_rest_client
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from novaclient import exceptions as nova_exceptions
from openstack_plugin_common import (
    NeutronClient,
    provider,
    transform_resource_name,
    get_default_resource_id,
    get_openstack_ids_of_connected_nodes_by_openstack_type,
    with_nova_client,
    is_external_resource,
    is_external_resource_by_properties,
    use_external_resource,
    delete_runtime_properties,
    is_external_relationship,
    USE_EXTERNAL_RESOURCE_PROPERTY,
    OPENSTACK_ID_PROPERTY,
    OPENSTACK_TYPE_PROPERTY,
    COMMON_RUNTIME_PROPERTIES_KEYS
)
from neutron_plugin.floatingip import IP_ADDRESS_PROPERTY
from neutron_plugin.network import NETWORK_OPENSTACK_TYPE
from neutron_plugin.port import PORT_OPENSTACK_TYPE

SERVER_OPENSTACK_TYPE = 'server'

# server status constants. Full lists here: http://docs.openstack.org/api/openstack-compute/2/content/List_Servers-d1e2078.html  # NOQA
SERVER_STATUS_ACTIVE = 'ACTIVE'
SERVER_STATUS_BUILD = 'BUILD'
SERVER_STATUS_SHUTOFF = 'SHUTOFF'

MUST_SPECIFY_NETWORK_EXCEPTION_TEXT = 'Multiple possible networks found'
SERVER_DELETE_CHECK_SLEEP = 2

# Runtime properties
NETWORKS_PROPERTY = 'networks'  # all of the server's ips
IP_PROPERTY = 'ip'  # the server's private ip
RUNTIME_PROPERTIES_KEYS = COMMON_RUNTIME_PROPERTIES_KEYS + \
    [NETWORKS_PROPERTY, IP_PROPERTY]


@operation
@with_nova_client
def create(nova_client, **kwargs):
    """
    Creates a server. Exposes the parameters mentioned in
    http://docs.openstack.org/developer/python-novaclient/api/novaclient.v1_1
    .servers.html#novaclient.v1_1.servers.ServerManager.create
    Userdata:

    In all cases, note that userdata should not be base64 encoded,
    novaclient expects it raw.
    The 'userdata' argument under nova.instance can be one of
    the following:

    - A string
    - A hash with 'type: http' and 'url: ...'
    """

    network_ids = get_openstack_ids_of_connected_nodes_by_openstack_type(
        ctx, NETWORK_OPENSTACK_TYPE)
    port_ids = get_openstack_ids_of_connected_nodes_by_openstack_type(
        ctx, PORT_OPENSTACK_TYPE)

    external_server = use_external_resource(ctx, nova_client,
                                            SERVER_OPENSTACK_TYPE)
    if external_server:
        try:
            _validate_external_server_nics(network_ids, port_ids)
            _set_network_and_ip_runtime_properties(external_server)
            return
        except Exception:
            delete_runtime_properties(ctx, RUNTIME_PROPERTIES_KEYS)
            raise

    provider_context = provider(ctx)

    def rename(name):
        return transform_resource_name(ctx, name)

    # For possible changes by _maybe_transform_userdata()

    server = {
        'name': get_default_resource_id(ctx, SERVER_OPENSTACK_TYPE),
    }
    server.update(copy.deepcopy(ctx.properties['server']))
    transform_resource_name(ctx, server)

    ctx.logger.debug(
        "server.create() server before transformations: {0}".format(server))

    if 'nics' in server:
        raise NonRecoverableError(
            "Parameter with name 'nics' must not be passed to"
            " openstack provisioner (under host's "
            "properties.nova.instance)")

    _maybe_transform_userdata(server)

    management_network_id = None
    management_network_name = None

    if ('management_network_name' in ctx.properties) and \
            ctx.properties['management_network_name']:
        management_network_name = ctx.properties['management_network_name']
        management_network_name = rename(management_network_name)
        nc = _neutron_client()
        management_network_id = nc.cosmo_get_named(
            'network', management_network_name)['id']
    else:
        int_network = provider_context.int_network
        if int_network:
            management_network_id = int_network['id']
            management_network_name = int_network['name']  # Already transform.
    if management_network_id is not None:
        server['nics'] = [{'net-id': management_network_id}]

    # Sugar
    if 'image_name' in server:
        server['image'] = nova_client.images.find(
            name=server['image_name']).id
        del server['image_name']
    if 'flavor_name' in server:
        server['flavor'] = nova_client.flavors.find(
            name=server['flavor_name']).id
        del server['flavor_name']

    security_groups = map(rename, server.get('security_groups', []))
    if provider_context.agents_security_group:
        asg = provider_context.agents_security_group['name']
        if asg not in security_groups:
            security_groups.append(asg)
    server['security_groups'] = security_groups

    if 'key_name' in server:
        server['key_name'] = rename(server['key_name'])
    else:
        # 'key_name' not in server
        if provider_context.agents_keypair:
            server['key_name'] = provider_context.agents_keypair['name']

    _fail_on_missing_required_parameters(
        server,
        ('name', 'flavor', 'image', 'key_name'),
        'server')

    if management_network_id is None and (network_ids or port_ids):
        # Known limitation
        raise NonRecoverableError(
            "Nova server with multi-NIC requires "
            "'management_network_name' in properties or id "
            "from provider context, which was not supplied")

    # Multi-NIC by networks - start
    nics = [{'net-id': net_id} for net_id in network_ids]
    if nics:
        server['nics'] = server.get('nics', []) + nics
    # Multi-NIC by networks - end

    # Multi-NIC by ports - start
    nics = [{'port-id': port_id} for port_id in port_ids]
    if nics:
        server['nics'] = server.get('nics', []) + nics
    # Multi-NIC by ports - end

    ctx.logger.debug(
        "server.create() server after transformations: {0}".format(server))

    # First parameter is 'self', skipping
    params_names = inspect.getargspec(nova_client.servers.create).args[1:]

    params_default_values = inspect.getargspec(
        nova_client.servers.create).defaults
    params = dict(itertools.izip(params_names, params_default_values))

    # Fail on unsupported parameters
    for k in server:
        if k not in params:
            raise NonRecoverableError(
                "Parameter with name '{0}' must not be passed to"
                " openstack provisioner (under host's "
                "properties.nova.instance)".format(k))

    for k in params:
        if k in server:
            params[k] = server[k]

    if not params['meta']:
        params['meta'] = dict({})
    if management_network_id is not None:
        params['meta']['cloudify_management_network_id'] = \
            management_network_id
    if management_network_name is not None:
        params['meta']['cloudify_management_network_name'] = \
            management_network_name

    ctx.logger.info("Creating VM with parameters: {0}".format(str(params)))
    ctx.logger.debug(
        "Asking Nova to create server. All possible parameters are: {0})"
        .format(','.join(params.keys())))

    try:
        s = nova_client.servers.create(**params)
    except nova_exceptions.BadRequest as e:
        if str(e).startswith(MUST_SPECIFY_NETWORK_EXCEPTION_TEXT):
            raise NonRecoverableError(
                "Can not provision server: management_network_name or id"
                " is not specified but there are several networks that the "
                "server can be connected to."
            )
        raise NonRecoverableError("Nova bad request error: " + str(e))
    except nova_exceptions.ClientException as e:
        raise NonRecoverableError("Nova client error: " + str(e))
    ctx.runtime_properties[OPENSTACK_ID_PROPERTY] = s.id
    ctx.runtime_properties[OPENSTACK_TYPE_PROPERTY] = SERVER_OPENSTACK_TYPE


def _neutron_client():
    return NeutronClient().get(config=ctx.properties.get('neutron_config'))


@operation
@with_nova_client
def start(nova_client, **kwargs):
    server = get_server_by_context(nova_client)

    if is_external_resource(ctx):
        ctx.logger.info('Validating external server is started')
        if server.status != SERVER_STATUS_ACTIVE:
            raise NonRecoverableError(
                'Expected external resource server {0} to be in '
                '"{1}" status'.format(server.id, SERVER_STATUS_ACTIVE))
        return

    if server.status not in (SERVER_STATUS_ACTIVE, SERVER_STATUS_BUILD):
        server.start()
    else:
        ctx.logger.info('Server is already started')


@operation
@with_nova_client
def stop(nova_client, **kwargs):
    """
    Stop server.

    Depends on OpenStack implementation, server.stop() might not be supported.
    """
    if is_external_resource(ctx):
        ctx.logger.info('Not stopping server since an external server is '
                        'being used')
        return

    server = get_server_by_context(nova_client)

    if server.status != SERVER_STATUS_SHUTOFF:
        nova_client.servers.stop(server)
    else:
        ctx.logger.info('Server is already stopped')


@operation
@with_nova_client
def delete(nova_client, **kwargs):
    if not is_external_resource(ctx):
        ctx.logger.info('Deleting Server')
        server = get_server_by_context(nova_client)
        nova_client.servers.delete(server)
        _wait_for_server_to_be_deleted(nova_client, server)
    else:
        ctx.logger.info('Not deleting server since an external server is '
                        'being used')

    delete_runtime_properties(ctx, RUNTIME_PROPERTIES_KEYS)


def _wait_for_server_to_be_deleted(nova_client,
                                   server,
                                   timeout=120,
                                   sleep_interval=5):
    timeout = time.time() + timeout
    while time.time() < timeout:
        try:
            server = nova_client.servers.get(server)
            ctx.logger.debug('Waiting for server "{}" to be deleted. current'
                             ' status: {}'.format(server.id, server.status))
            time.sleep(sleep_interval)
        except nova_exceptions.NotFound:
            return
    # recoverable error
    raise RuntimeError('Server {} has not been deleted. waited for {} seconds'
                       .format(server.id, timeout))


def get_server_by_context(nova_client):
    return nova_client.servers.get(
        ctx.runtime_properties[OPENSTACK_ID_PROPERTY])


def _set_network_and_ip_runtime_properties(server):
    ips = {}
    _, default_network_ips = server.networks.items()[0]
    manager_network_ip = None
    management_network_name = server.metadata.get(
        'cloudify_management_network_name')
    for network, network_ips in server.networks.items():
        if management_network_name and network == management_network_name:
            manager_network_ip = network_ips[0]
        ips[network] = network_ips
    if manager_network_ip is None:
        manager_network_ip = default_network_ips[0]
    ctx.runtime_properties[NETWORKS_PROPERTY] = ips
    # The ip of this instance in the management network
    ctx.runtime_properties[IP_PROPERTY] = manager_network_ip


@operation
@with_nova_client
def get_state(nova_client, **kwargs):
    server = get_server_by_context(nova_client)
    if server.status == SERVER_STATUS_ACTIVE:
        _set_network_and_ip_runtime_properties(server)
        return True
    return False


@operation
@with_nova_client
def connect_floatingip(nova_client, **kwargs):
    server_id = ctx.runtime_properties[OPENSTACK_ID_PROPERTY]
    floating_ip_id = ctx.related.runtime_properties[OPENSTACK_ID_PROPERTY]
    floating_ip_address = ctx.related.runtime_properties[IP_ADDRESS_PROPERTY]

    if is_external_relationship(ctx):
        ctx.logger.info('Validating external floatingip and server '
                        'are associated')
        nc = _neutron_client()
        port_id = nc.show_floatingip(floating_ip_id)['floatingip']['port_id']
        if port_id and nc.show_port(port_id)['port']['device_id'] != server_id:
            return
        raise NonRecoverableError(
            'Expected external resources server {0} and floating-ip {1} to be '
            'connected'.format(server_id, floating_ip_id))

    server = nova_client.servers.get(server_id)
    server.add_floating_ip(floating_ip_address)


@operation
@with_nova_client
def disconnect_floatingip(nova_client, **kwargs):
    if is_external_relationship(ctx):
        ctx.logger.info('Not associating floatingip and server since '
                        'external floatingip and server are being used')
        return

    server_id = ctx.runtime_properties[OPENSTACK_ID_PROPERTY]
    server = nova_client.servers.get(server_id)
    server.remove_floating_ip(ctx.related.runtime_properties[
        IP_ADDRESS_PROPERTY])


def _fail_on_missing_required_parameters(obj, required_parameters, hint_where):
    for k in required_parameters:
        if k not in obj:
            raise NonRecoverableError(
                "Required parameter '{0}' is missing (under host's "
                "properties.{1}). Required parameters are: {2}"
                .format(k, hint_where, required_parameters))


def _validate_external_server_nics(network_ids, port_ids):
    new_nic_nodes = \
        [node_instance_id for node_instance_id, runtime_props in
         ctx.capabilities.get_all().iteritems() if runtime_props.get(
             OPENSTACK_TYPE_PROPERTY) in (PORT_OPENSTACK_TYPE,
                                          NETWORK_OPENSTACK_TYPE)
         and not is_external_resource_by_properties(
         _get_properties_by_node_instance_id(node_instance_id))]  # NOQA
    if new_nic_nodes:
        raise NonRecoverableError(
            "Can't connect new port and/or network nodes to a server node "
            "with '{0}'=True".format(USE_EXTERNAL_RESOURCE_PROPERTY))

    nc = _neutron_client()
    server_id = ctx.runtime_properties[OPENSTACK_ID_PROPERTY]
    connected_ports = nc.list_ports(device_id=server_id)['ports']

    # not counting networks connected by a connected port since allegedly
    # the connection should be on a separate port
    connected_ports_networks = {port['network_id'] for port in
                                connected_ports if port['id'] not in port_ids}
    connected_ports_ids = {port['id'] for port in
                           connected_ports}
    disconnected_networks = [network_id for network_id in network_ids if
                             network_id not in connected_ports_networks]
    disconnected_ports = [port_id for port_id in port_ids if port_id not
                          in connected_ports_ids]
    if disconnected_networks or disconnected_ports:
        raise NonRecoverableError(
            'Expected external resources to be connected to external server {'
            '0}: Networks - {1}; Ports - {2}'.format(server_id,
                                                     disconnected_networks,
                                                     disconnected_ports))


def _get_properties_by_node_instance_id(node_instance_id):
    client = get_rest_client()
    node_instance = client.node_instances.get(node_instance_id)
    node = client.nodes.get(ctx.deployment_id, node_instance.node_id)
    return node.properties


# *** userdata handling - start ***
userdata_handlers = {}


def userdata_handler(type_):
    def f(x):
        userdata_handlers[type_] = x
        return x
    return f


def _maybe_transform_userdata(nova_config_instance):
    """Allows userdata to be read from a file, etc, not just be a string"""
    if 'userdata' not in nova_config_instance:
        return
    if not isinstance(nova_config_instance['userdata'], dict):
        return
    ud = nova_config_instance['userdata']

    _fail_on_missing_required_parameters(
        ud,
        ('type',),
        'server.userdata')

    if ud['type'] not in userdata_handlers:
        raise NonRecoverableError(
            "Invalid type '{0}' (under host's "
            "properties.nova_config.instance.userdata)"
            .format(ud['type']))

    nova_config_instance['userdata'] = userdata_handlers[ud['type']](ud)


@userdata_handler('http')
def ud_http(params):
    """ Fetches userdata using HTTP """
    import requests
    _fail_on_missing_required_parameters(
        params,
        ('url',),
        "server.userdata when using type 'http'")
    return requests.get(params['url']).text
# *** userdata handling - end ***
