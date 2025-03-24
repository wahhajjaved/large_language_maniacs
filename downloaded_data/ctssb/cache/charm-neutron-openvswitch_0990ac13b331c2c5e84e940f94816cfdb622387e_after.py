from charmhelpers.contrib.openstack.neutron import neutron_plugin_attribute
from copy import deepcopy

from charmhelpers.contrib.openstack import context, templating
from collections import OrderedDict
from charmhelpers.contrib.openstack.utils import (
    os_release,
)
import neutron_ovs_context
from charmhelpers.contrib.network.ovs import (
    add_bridge,
    add_bridge_port,
)

NOVA_CONF_DIR = "/etc/nova"
NEUTRON_CONF_DIR = "/etc/neutron"
NEUTRON_CONF = '%s/neutron.conf' % NEUTRON_CONF_DIR
NEUTRON_DEFAULT = '/etc/default/neutron-server'
NEUTRON_L3_AGENT_CONF = "/etc/neutron/l3_agent.ini"
NEUTRON_FWAAS_CONF = "/etc/neutron/fwaas_driver.ini"
ML2_CONF = '%s/plugins/ml2/ml2_conf.ini' % NEUTRON_CONF_DIR
EXT_PORT_CONF = '/etc/init/ext-port.conf'
NEUTRON_METADATA_AGENT_CONF = "/etc/neutron/metadata_agent.ini"


BASE_RESOURCE_MAP = OrderedDict([
    (NEUTRON_CONF, {
        'services': ['neutron-plugin-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext(),
                     context.AMQPContext(ssl_dir=NEUTRON_CONF_DIR)],
    }),
    (ML2_CONF, {
        'services': ['neutron-plugin-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
])
DVR_RESOURCE_MAP = OrderedDict([
    (NEUTRON_L3_AGENT_CONF, {
        'services': ['neutron-vpn-agent'],
        'contexts': [neutron_ovs_context.L3AgentContext()],
    }),
    (NEUTRON_FWAAS_CONF, {
        'services': ['neutron-vpn-agent'],
        'contexts': [neutron_ovs_context.L3AgentContext()],
    }),
    (EXT_PORT_CONF, {
        'services': ['neutron-vpn-agent'],
        'contexts': [context.ExternalPortContext()],
    }),
    (NEUTRON_METADATA_AGENT_CONF, {
        'services': ['neutron-metadata-agent'],
        'contexts': [neutron_ovs_context.DVRSharedSecretContext(),
                     neutron_ovs_context.NetworkServiceContext()],
    }),
])
TEMPLATES = 'templates/'
INT_BRIDGE = "br-int"
EXT_BRIDGE = "br-ex"
DATA_BRIDGE = 'br-data'


def determine_dvr_packages():
    pkgs = []
    if neutron_ovs_context.use_dvr():
        pkgs = ['neutron-vpn-agent']
    return pkgs


def determine_packages():
    pkgs = neutron_plugin_attribute('ovs', 'packages', 'neutron')
    pkgs.extend(determine_dvr_packages())
    return pkgs


def register_configs(release=None):
    release = release or os_release('neutron-common', base='icehouse')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    for cfg, rscs in resource_map().iteritems():
        configs.register(cfg, rscs['contexts'])
    return configs


def resource_map():
    '''
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    '''
    resource_map = deepcopy(BASE_RESOURCE_MAP)
    if neutron_ovs_context.use_dvr():
        resource_map.update(DVR_RESOURCE_MAP)
        dvr_services = ['neutron-metadata-agent', 'neutron-vpn-agent']
        resource_map[NEUTRON_CONF]['services'] += dvr_services
    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().iteritems()}


def configure_ovs():
    add_bridge(INT_BRIDGE)
    add_bridge(EXT_BRIDGE)
    ext_port_ctx = context.ExternalPortContext()()
    if ext_port_ctx and ext_port_ctx['ext_port']:
        add_bridge_port(EXT_BRIDGE, ext_port_ctx['ext_port'])

    add_bridge(DATA_BRIDGE)


def get_shared_secret():
    ctxt = neutron_ovs_context.DVRSharedSecretContext()()
    if 'shared_secret' in ctxt:
        return ctxt['shared_secret']
