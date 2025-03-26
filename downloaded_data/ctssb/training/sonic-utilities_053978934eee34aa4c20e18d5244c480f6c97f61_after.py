#!/usr/sbin/env python

import click
import ipaddress
import json
import netaddr
import netifaces
import os
import re
import subprocess
import sys
import time

from socket import AF_INET, AF_INET6
from minigraph import parse_device_desc_xml
from portconfig import get_child_ports
from sonic_py_common import device_info, multi_asic
from sonic_py_common.interface import get_interface_table_name, get_port_table_name
from utilities_common import util_base
from swsscommon.swsscommon import SonicV2Connector, ConfigDBConnector, SonicDBConfig
from utilities_common.db import Db
from utilities_common.intf_filter import parse_interface_in_filter
import utilities_common.cli as clicommon
from .utils import log

from . import aaa
from . import chassis_modules
from . import console
from . import feature
from . import kdump
from . import kube
from . import muxcable
from . import nat
from . import vlan
from . import vxlan
from . import plugins
from .config_mgmt import ConfigMgmtDPB

# mock masic APIs for unit test
try:
    if os.environ["UTILITIES_UNIT_TESTING"] == "1" or os.environ["UTILITIES_UNIT_TESTING"] == "2":
        modules_path = os.path.join(os.path.dirname(__file__), "..")
        tests_path = os.path.join(modules_path, "tests")
        sys.path.insert(0, modules_path)
        sys.path.insert(0, tests_path)
        import mock_tables.dbconnector
    if os.environ["UTILITIES_UNIT_TESTING_TOPOLOGY"] == "multi_asic":
        import mock_tables.mock_multi_asic
        mock_tables.dbconnector.load_namespace_config()
except KeyError:
    pass


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help', '-?'])

SONIC_GENERATED_SERVICE_PATH = '/etc/sonic/generated_services.conf'
SONIC_CFGGEN_PATH = '/usr/local/bin/sonic-cfggen'
VLAN_SUB_INTERFACE_SEPARATOR = '.'
ASIC_CONF_FILENAME = 'asic.conf'
DEFAULT_CONFIG_DB_FILE = '/etc/sonic/config_db.json'
NAMESPACE_PREFIX = 'asic'
INTF_KEY = "interfaces"

INIT_CFG_FILE = '/etc/sonic/init_cfg.json'

DEFAULT_NAMESPACE = ''
CFG_LOOPBACK_PREFIX = "Loopback"
CFG_LOOPBACK_PREFIX_LEN = len(CFG_LOOPBACK_PREFIX)
CFG_LOOPBACK_NAME_TOTAL_LEN_MAX = 11
CFG_LOOPBACK_ID_MAX_VAL = 999
CFG_LOOPBACK_NO="<0-999>"

CFG_PORTCHANNEL_PREFIX = "PortChannel"
CFG_PORTCHANNEL_PREFIX_LEN = 11
CFG_PORTCHANNEL_NAME_TOTAL_LEN_MAX = 15
CFG_PORTCHANNEL_MAX_VAL = 9999
CFG_PORTCHANNEL_NO="<0-9999>"

PORT_MTU = "mtu"
PORT_SPEED = "speed"

asic_type = None

#
# Breakout Mode Helper functions
#

# Read given JSON file
def readJsonFile(fileName):
    try:
        with open(fileName) as f:
            result = json.load(f)
    except Exception as e:
        raise Exception(str(e))
    return result

def _get_breakout_options(ctx, args, incomplete):
    """ Provides dynamic mode option as per user argument i.e. interface name """
    all_mode_options = []
    interface_name = args[-1]

    breakout_cfg_file = device_info.get_path_to_port_config_file()

    if not os.path.isfile(breakout_cfg_file) or not breakout_cfg_file.endswith('.json'):
        return []
    else:
        breakout_file_input = readJsonFile(breakout_cfg_file)
        if interface_name in breakout_file_input[INTF_KEY]:
            breakout_mode_options = [mode for i, v in breakout_file_input[INTF_KEY].items() if i == interface_name \
                                          for mode in v["breakout_modes"].keys()]
            all_mode_options = [str(c) for c in breakout_mode_options if incomplete in c]
        return all_mode_options

def shutdown_interfaces(ctx, del_intf_dict):
    """ shut down all the interfaces before deletion """
    for intf in del_intf_dict:
        config_db = ctx.obj['config_db']
        if clicommon.get_interface_naming_mode() == "alias":
            interface_name = interface_alias_to_name(config_db, intf)
            if interface_name is None:
                click.echo("[ERROR] interface name is None!")
                return False

        if interface_name_is_valid(config_db, intf) is False:
            click.echo("[ERROR] Interface name is invalid. Please enter a valid interface name!!")
            return False

        port_dict = config_db.get_table('PORT')
        if not port_dict:
            click.echo("port_dict is None!")
            return False

        if intf in port_dict:
            config_db.mod_entry("PORT", intf, {"admin_status": "down"})
        else:
            click.secho("[ERROR] Could not get the correct interface name, exiting", fg='red')
            return False
    return True

def _validate_interface_mode(ctx, breakout_cfg_file, interface_name, target_brkout_mode, cur_brkout_mode):
    """ Validate Parent interface and user selected mode before starting deletion or addition process """
    breakout_file_input = readJsonFile(breakout_cfg_file)["interfaces"]

    if interface_name not in breakout_file_input:
        click.secho("[ERROR] {} is not a Parent port. So, Breakout Mode is not available on this port".format(interface_name), fg='red')
        return False

    # Check whether target breakout mode is available for the user-selected interface or not
    if target_brkout_mode not in breakout_file_input[interface_name]["breakout_modes"].keys():
        click.secho('[ERROR] Target mode {} is not available for the port {}'. format(target_brkout_mode, interface_name), fg='red')
        return False

    # Get config db context
    config_db = ctx.obj['config_db']
    port_dict = config_db.get_table('PORT')

    # Check whether there is any port in config db.
    if not port_dict:
        click.echo("port_dict is None!")
        return False

    # Check whether the  user-selected interface is part of  'port' table in config db.
    if interface_name not in port_dict:
        click.secho("[ERROR] {} is not in port_dict".format(interface_name))
        return False
    click.echo("\nRunning Breakout Mode : {} \nTarget Breakout Mode : {}".format(cur_brkout_mode, target_brkout_mode))
    if (cur_brkout_mode == target_brkout_mode):
        click.secho("[WARNING] No action will be taken as current and desired Breakout Mode are same.", fg='magenta')
        sys.exit(0)
    return True

def load_ConfigMgmt(verbose):
    """ Load config for the commands which are capable of change in config DB. """
    try:
        cm = ConfigMgmtDPB(debug=verbose)
        return cm
    except Exception as e:
        raise Exception("Failed to load the config. Error: {}".format(str(e)))

def breakout_warnUser_extraTables(cm, final_delPorts, confirm=True):
    """
    Function to warn user about extra tables while Dynamic Port Breakout(DPB).
    confirm: re-confirm from user to proceed.
    Config Tables Without Yang model considered extra tables.
    cm =  instance of config MGMT class.
    """
    try:
        # check if any extra tables exist
        eTables = cm.tablesWithOutYang()
        if len(eTables):
            # find relavent tables in extra tables, i.e. one which can have deleted
            # ports
            tables = cm.configWithKeys(configIn=eTables, keys=final_delPorts)
            click.secho("Below Config can not be verified, It may cause harm "\
                "to the system\n {}".format(json.dumps(tables, indent=2)))
            click.confirm('Do you wish to Continue?', abort=True)
    except Exception as e:
        raise Exception("Failed in breakout_warnUser_extraTables. Error: {}".format(str(e)))
    return

def breakout_Ports(cm, delPorts=list(), portJson=dict(), force=False, \
    loadDefConfig=False, verbose=False):

    deps, ret = cm.breakOutPort(delPorts=delPorts,  portJson=portJson, \
                    force=force, loadDefConfig=loadDefConfig)
    # check if DPB failed
    if ret == False:
        if not force and deps:
            click.echo("Dependecies Exist. No further action will be taken")
            click.echo("*** Printing dependecies ***")
            for dep in deps:
                click.echo(dep)
            sys.exit(0)
        else:
            click.echo("[ERROR] Port breakout Failed!!! Opting Out")
            raise click.Abort()
        return

#
# Helper functions
#


def _get_device_type():
    """
    Get device type

    TODO: move to sonic-py-common
    """

    command = "{} -m -v DEVICE_METADATA.localhost.type".format(SONIC_CFGGEN_PATH)
    proc = subprocess.Popen(command, shell=True, text=True, stdout=subprocess.PIPE)
    device_type, err = proc.communicate()
    if err:
        click.echo("Could not get the device type from minigraph, setting device type to Unknown")
        device_type = 'Unknown'
    else:
        device_type = device_type.strip()

    return device_type

def interface_alias_to_name(config_db, interface_alias):
    """Return default interface name if alias name is given as argument
    """
    vlan_id = ""
    sub_intf_sep_idx = -1
    if interface_alias is not None:
        sub_intf_sep_idx = interface_alias.find(VLAN_SUB_INTERFACE_SEPARATOR)
        if sub_intf_sep_idx != -1:
            vlan_id = interface_alias[sub_intf_sep_idx + 1:]
            # interface_alias holds the parent port name so the subsequent logic still applies
            interface_alias = interface_alias[:sub_intf_sep_idx]

    # If the input parameter config_db is None, derive it from interface.
    # In single ASIC platform, get_port_namespace() returns DEFAULT_NAMESPACE.
    if config_db is None:
        namespace = get_port_namespace(interface_alias)
        if namespace is None:
            return None
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)

    config_db.connect()
    port_dict = config_db.get_table('PORT')

    if interface_alias is not None:
        if not port_dict:
            click.echo("port_dict is None!")
            raise click.Abort()
        for port_name in port_dict:
            if interface_alias == port_dict[port_name]['alias']:
                return port_name if sub_intf_sep_idx == -1 else port_name + VLAN_SUB_INTERFACE_SEPARATOR + vlan_id

    # Interface alias not in port_dict, just return interface_alias, e.g.,
    # portchannel is passed in as argument, which does not have an alias
    return interface_alias if sub_intf_sep_idx == -1 else interface_alias + VLAN_SUB_INTERFACE_SEPARATOR + vlan_id

def interface_name_is_valid(config_db, interface_name):
    """Check if the interface name is valid
    """
    # If the input parameter config_db is None, derive it from interface.
    # In single ASIC platform, get_port_namespace() returns DEFAULT_NAMESPACE.
    if config_db is None:
        namespace = get_port_namespace(interface_name)
        if namespace is None:
            return False
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)

    config_db.connect()
    port_dict = config_db.get_table('PORT')
    port_channel_dict = config_db.get_table('PORTCHANNEL')
    sub_port_intf_dict = config_db.get_table('VLAN_SUB_INTERFACE')

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)

    if interface_name is not None:
        if not port_dict:
            click.echo("port_dict is None!")
            raise click.Abort()
        for port_name in port_dict:
            if interface_name == port_name:
                return True
        if port_channel_dict:
            for port_channel_name in port_channel_dict:
                if interface_name == port_channel_name:
                    return True
        if sub_port_intf_dict:
            for sub_port_intf_name in sub_port_intf_dict:
                if interface_name == sub_port_intf_name:
                    return True
    return False

def interface_name_to_alias(config_db, interface_name):
    """Return alias interface name if default name is given as argument
    """
    # If the input parameter config_db is None, derive it from interface.
    # In single ASIC platform, get_port_namespace() returns DEFAULT_NAMESPACE.
    if config_db is None:
        namespace = get_port_namespace(interface_name)
        if namespace is None:
            return None
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)

    config_db.connect()
    port_dict = config_db.get_table('PORT')

    if interface_name is not None:
        if not port_dict:
            click.echo("port_dict is None!")
            raise click.Abort()
        for port_name in port_dict:
            if interface_name == port_name:
                return port_dict[port_name]['alias']

    return None

def interface_ipaddr_dependent_on_interface(config_db, interface_name):
    """Get table keys including ipaddress
    """
    data = []
    table_name = get_interface_table_name(interface_name)
    if table_name == "":
        return data
    keys = config_db.get_keys(table_name)
    for key in keys:
        if interface_name in key and len(key) == 2:
            data.append(key)
    return data

def is_interface_bind_to_vrf(config_db, interface_name):
    """Get interface if bind to vrf or not
    """
    table_name = get_interface_table_name(interface_name)
    if table_name == "":
        return False
    entry = config_db.get_entry(table_name, interface_name)
    if entry and entry.get("vrf_name"):
        return True
    return False

def is_portchannel_name_valid(portchannel_name):
    """Port channel name validation
    """

    # Return True if Portchannel name is PortChannelXXXX (XXXX can be 0-9999)
    if portchannel_name[:CFG_PORTCHANNEL_PREFIX_LEN] != CFG_PORTCHANNEL_PREFIX :
        return False
    if (portchannel_name[CFG_PORTCHANNEL_PREFIX_LEN:].isdigit() is False or
          int(portchannel_name[CFG_PORTCHANNEL_PREFIX_LEN:]) > CFG_PORTCHANNEL_MAX_VAL) :
        return False
    if len(portchannel_name) > CFG_PORTCHANNEL_NAME_TOTAL_LEN_MAX:
        return False
    return True

def is_portchannel_present_in_db(db, portchannel_name):
    """Check if Portchannel is present in Config DB
    """

    # Return True if Portchannel name exists in the CONFIG_DB
    portchannel_list = db.get_table(CFG_PORTCHANNEL_PREFIX)
    if portchannel_list is None:
        return False
    if portchannel_name in portchannel_list:
        return True
    return False

def is_port_member_of_this_portchannel(db, port_name, portchannel_name):
    """Check if a port is member of given portchannel
    """
    portchannel_list = db.get_table(CFG_PORTCHANNEL_PREFIX)
    if portchannel_list is None:
        return False

    for k,v in db.get_table('PORTCHANNEL_MEMBER'):
        if (k == portchannel_name) and (v == port_name):
            return True

    return False

# Return the namespace where an interface belongs
# The port name input could be in default mode or in alias mode.
def get_port_namespace(port):
    # If it is a non multi-asic platform, or if the interface is management interface
    # return DEFAULT_NAMESPACE
    if not multi_asic.is_multi_asic() or port == 'eth0':
        return DEFAULT_NAMESPACE

    # Get the table to check for interface presence
    table_name = get_port_table_name(port)
    if table_name == "":
        return None

    ns_list = multi_asic.get_all_namespaces()
    namespaces = ns_list['front_ns'] + ns_list['back_ns']
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()

        # If the interface naming mode is alias, search the tables for alias_name.
        if clicommon.get_interface_naming_mode() == "alias":
            port_dict = config_db.get_table(table_name)
            if port_dict:
                for port_name in port_dict:
                    if port == port_dict[port_name]['alias']:
                        return namespace
        else:
            entry = config_db.get_entry(table_name, port)
            if entry:
                return namespace

    return None

def del_interface_bind_to_vrf(config_db, vrf_name):
    """del interface bind to vrf
    """
    tables = ['INTERFACE', 'PORTCHANNEL_INTERFACE', 'VLAN_INTERFACE', 'LOOPBACK_INTERFACE']
    for table_name in tables:
        interface_dict = config_db.get_table(table_name)
        if interface_dict:
            for interface_name in interface_dict:
                if 'vrf_name' in interface_dict[interface_name] and vrf_name == interface_dict[interface_name]['vrf_name']:
                    interface_dependent = interface_ipaddr_dependent_on_interface(config_db, interface_name)
                    for interface_del in interface_dependent:
                        config_db.set_entry(table_name, interface_del, None)
                    config_db.set_entry(table_name, interface_name, None)

def set_interface_naming_mode(mode):
    """Modify SONIC_CLI_IFACE_MODE env variable in user .bashrc
    """
    user = os.getenv('SUDO_USER')
    bashrc_ifacemode_line = "export SONIC_CLI_IFACE_MODE={}".format(mode)

    # In case of multi-asic, we can check for the alias mode support in any of
    # the namespaces as this setting of alias mode should be identical everywhere.
    # Here by default we set the namespaces to be a list just having '' which
    # represents the linux host. In case of multi-asic, we take the first namespace
    # created for the front facing ASIC.

    namespaces = [DEFAULT_NAMESPACE]
    if multi_asic.is_multi_asic():
        namespaces = multi_asic.get_all_namespaces()['front_ns']

    # Ensure all interfaces have an 'alias' key in PORT dict
    config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespaces[0])
    config_db.connect()
    port_dict = config_db.get_table('PORT')

    if not port_dict:
        click.echo("port_dict is None!")
        raise click.Abort()

    for port_name in port_dict:
        try:
            if port_dict[port_name]['alias']:
                pass
        except KeyError:
            click.echo("Platform does not support alias mapping")
            raise click.Abort()

    if not user:
        user = os.getenv('USER')

    if user != "root":
        bashrc = "/home/{}/.bashrc".format(user)
    else:
        click.get_current_context().fail("Cannot set interface naming mode for root user!")

    f = open(bashrc, 'r')
    filedata = f.read()
    f.close()

    if "SONIC_CLI_IFACE_MODE" not in filedata:
        newdata = filedata + bashrc_ifacemode_line
        newdata += "\n"
    else:
        newdata = re.sub(r"export SONIC_CLI_IFACE_MODE=\w+",
                         bashrc_ifacemode_line, filedata)
    f = open(bashrc, 'w')
    f.write(newdata)
    f.close()
    click.echo("Please logout and log back in for changes take effect.")


def _is_neighbor_ipaddress(config_db, ipaddress):
    """Returns True if a neighbor has the IP address <ipaddress>, False if not
    """
    entry = config_db.get_entry('BGP_NEIGHBOR', ipaddress)
    return True if entry else False

def _get_all_neighbor_ipaddresses(config_db):
    """Returns list of strings containing IP addresses of all BGP neighbors
    """
    addrs = []
    bgp_sessions = config_db.get_table('BGP_NEIGHBOR')
    for addr, session in bgp_sessions.items():
        addrs.append(addr)
    return addrs

def _get_neighbor_ipaddress_list_by_hostname(config_db, hostname):
    """Returns list of strings, each containing an IP address of neighbor with
       hostname <hostname>. Returns empty list if <hostname> not a neighbor
    """
    addrs = []
    bgp_sessions = config_db.get_table('BGP_NEIGHBOR')
    for addr, session in bgp_sessions.items():
        if 'name' in session and session['name'] == hostname:
            addrs.append(addr)
    return addrs

def _change_bgp_session_status_by_addr(config_db, ipaddress, status, verbose):
    """Start up or shut down BGP session by IP address
    """
    verb = 'Starting' if status == 'up' else 'Shutting'
    click.echo("{} {} BGP session with neighbor {}...".format(verb, status, ipaddress))

    config_db.mod_entry('bgp_neighbor', ipaddress, {'admin_status': status})

def _change_bgp_session_status(config_db, ipaddr_or_hostname, status, verbose):
    """Start up or shut down BGP session by IP address or hostname
    """
    ip_addrs = []

    # If we were passed an IP address, convert it to lowercase because IPv6 addresses were
    # stored in ConfigDB with all lowercase alphabet characters during minigraph parsing
    if _is_neighbor_ipaddress(config_db, ipaddr_or_hostname.lower()):
        ip_addrs.append(ipaddr_or_hostname.lower())
    else:
        # If <ipaddr_or_hostname> is not the IP address of a neighbor, check to see if it's a hostname
        ip_addrs = _get_neighbor_ipaddress_list_by_hostname(config_db, ipaddr_or_hostname)

    if not ip_addrs:
        return False

    for ip_addr in ip_addrs:
        _change_bgp_session_status_by_addr(config_db, ip_addr, status, verbose)

    return True

def _validate_bgp_neighbor(config_db, neighbor_ip_or_hostname):
    """validates whether the given ip or host name is a BGP neighbor
    """
    ip_addrs = []
    if _is_neighbor_ipaddress(config_db, neighbor_ip_or_hostname.lower()):
        ip_addrs.append(neighbor_ip_or_hostname.lower())
    else:
        ip_addrs = _get_neighbor_ipaddress_list_by_hostname(config_db, neighbor_ip_or_hostname.upper())

    return ip_addrs

def _remove_bgp_neighbor_config(config_db, neighbor_ip_or_hostname):
    """Removes BGP configuration of the given neighbor
    """
    ip_addrs = _validate_bgp_neighbor(config_db, neighbor_ip_or_hostname)

    if not ip_addrs:
        return False

    for ip_addr in ip_addrs:
        config_db.mod_entry('bgp_neighbor', ip_addr, None)
        click.echo("Removed configuration of BGP neighbor {}".format(ip_addr))

    return True

def _change_hostname(hostname):
    current_hostname = os.uname()[1]
    if current_hostname != hostname:
        clicommon.run_command('echo {} > /etc/hostname'.format(hostname), display_cmd=True)
        clicommon.run_command('hostname -F /etc/hostname', display_cmd=True)
        clicommon.run_command(r'sed -i "/\s{}$/d" /etc/hosts'.format(current_hostname), display_cmd=True)
        clicommon.run_command('echo "127.0.0.1 {}" >> /etc/hosts'.format(hostname), display_cmd=True)

def _clear_qos():
    QOS_TABLE_NAMES = [
            'TC_TO_PRIORITY_GROUP_MAP',
            'MAP_PFC_PRIORITY_TO_QUEUE',
            'TC_TO_QUEUE_MAP',
            'DSCP_TO_TC_MAP',
            'SCHEDULER',
            'PFC_PRIORITY_TO_PRIORITY_GROUP_MAP',
            'PORT_QOS_MAP',
            'WRED_PROFILE',
            'QUEUE',
            'CABLE_LENGTH',
            'BUFFER_POOL',
            'BUFFER_PROFILE',
            'BUFFER_PG',
            'BUFFER_QUEUE',
            'DEFAULT_LOSSLESS_BUFFER_PARAMETER',
            'LOSSLESS_TRAFFIC_PATTERN']

    namespace_list = [DEFAULT_NAMESPACE]
    if multi_asic.get_num_asics() > 1:
        namespace_list = multi_asic.get_namespaces_from_linux()

    for ns in namespace_list:
        if ns is DEFAULT_NAMESPACE:
            config_db = ConfigDBConnector()
        else:
            config_db = ConfigDBConnector(
                use_unix_socket_path=True, namespace=ns
            )
        config_db.connect()
        for qos_table in QOS_TABLE_NAMES:
            config_db.delete_table(qos_table)

def _get_sonic_generated_services(num_asic):
    if not os.path.isfile(SONIC_GENERATED_SERVICE_PATH):
        return None
    generated_services_list = []
    generated_multi_instance_services = []
    with open(SONIC_GENERATED_SERVICE_PATH) as generated_service_file:
        for line in generated_service_file:
            if '@' in line:
                line = line.replace('@', '')
                if num_asic > 1:
                    generated_multi_instance_services.append(line.rstrip('\n'))
                else:
                    generated_services_list.append(line.rstrip('\n'))
            else:
                generated_services_list.append(line.rstrip('\n'))
    return generated_services_list, generated_multi_instance_services

# Callback for confirmation prompt. Aborts if user enters "n"
def _abort_if_false(ctx, param, value):
    if not value:
        ctx.abort()


def _get_disabled_services_list(config_db):
    disabled_services_list = []

    feature_table = config_db.get_table('FEATURE')
    if feature_table is not None:
        for feature_name in feature_table:
            if not feature_name:
                log.log_warning("Feature is None")
                continue

            state = feature_table[feature_name]['state']
            if not state:
                log.log_warning("Enable state of feature '{}' is None".format(feature_name))
                continue

            if state == "disabled":
                disabled_services_list.append(feature_name)
    else:
        log.log_warning("Unable to retreive FEATURE table")

    return disabled_services_list


def _stop_services():
    try:
        subprocess.check_call("sudo monit status", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        click.echo("Disabling container monitoring ...")
        clicommon.run_command("sudo monit unmonitor container_checker")
    except subprocess.CalledProcessError as err:
        pass

    click.echo("Stopping SONiC target ...")
    clicommon.run_command("sudo systemctl stop sonic.target")


def _get_sonic_services():
    out = clicommon.run_command("systemctl list-dependencies --plain sonic.target | sed '1d'", return_cmd=True)
    return [unit.strip() for unit in out.splitlines()]


def _reset_failed_services():
    for service in _get_sonic_services():
        click.echo("Resetting failed status on {}".format(service))
        clicommon.run_command("systemctl reset-failed {}".format(service))


def _restart_services():
    click.echo("Restarting SONiC target ...")
    clicommon.run_command("sudo systemctl restart sonic.target")

    try:
        subprocess.check_call("sudo monit status", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        click.echo("Enabling container monitoring ...")
        clicommon.run_command("sudo monit monitor container_checker")
    except subprocess.CalledProcessError as err:
        pass

    # Reload Monit configuration to pick up new hostname in case it changed
    click.echo("Reloading Monit configuration ...")
    clicommon.run_command("sudo monit reload")


def interface_is_in_vlan(vlan_member_table, interface_name):
    """ Check if an interface is in a vlan """
    for _, intf in vlan_member_table:
        if intf == interface_name:
            return True

    return False

def interface_is_in_portchannel(portchannel_member_table, interface_name):
    """ Check if an interface is part of portchannel """
    for _, intf in portchannel_member_table:
        if intf == interface_name:
            return True

    return False

def interface_has_mirror_config(mirror_table, interface_name):
    """ Check if port is already configured with mirror config """
    for _, v in mirror_table.items():
        if 'src_port' in v and v['src_port'] == interface_name:
            return True
        if 'dst_port' in v and v['dst_port'] == interface_name:
            return True

    return False

def validate_mirror_session_config(config_db, session_name, dst_port, src_port, direction):
    """ Check if SPAN mirror-session config is valid """
    if len(config_db.get_entry('MIRROR_SESSION', session_name)) != 0:
        click.echo("Error: {} already exists".format(session_name))
        return False

    vlan_member_table = config_db.get_table('VLAN_MEMBER')
    mirror_table = config_db.get_table('MIRROR_SESSION')
    portchannel_member_table = config_db.get_table('PORTCHANNEL_MEMBER')

    if dst_port:
        if not interface_name_is_valid(config_db, dst_port):
            click.echo("Error: Destination Interface {} is invalid".format(dst_port))
            return False

        if interface_is_in_vlan(vlan_member_table, dst_port):
            click.echo("Error: Destination Interface {} has vlan config".format(dst_port))
            return False

        if interface_has_mirror_config(mirror_table, dst_port):
            click.echo("Error: Destination Interface {} already has mirror config".format(dst_port))
            return False

        if interface_is_in_portchannel(portchannel_member_table, dst_port):
            click.echo("Error: Destination Interface {} has portchannel config".format(dst_port))
            return False

        if clicommon.is_port_router_interface(config_db, dst_port):
            click.echo("Error: Destination Interface {} is a L3 interface".format(dst_port))
            return False

    if src_port:
        for port in src_port.split(","):
            if not interface_name_is_valid(config_db, port):
                click.echo("Error: Source Interface {} is invalid".format(port))
                return False
            if dst_port and dst_port == port:
                click.echo("Error: Destination Interface cant be same as Source Interface")
                return False
            if interface_has_mirror_config(mirror_table, port):
                click.echo("Error: Source Interface {} already has mirror config".format(port))
                return False

    if direction:
        if direction not in ['rx', 'tx', 'both']:
            click.echo("Error: Direction {} is invalid".format(direction))
            return False

    return True

def update_sonic_environment():
    """Prepare sonic environment variable using SONiC environment template file.
    """
    SONIC_ENV_TEMPLATE_FILE = os.path.join('/', "usr", "share", "sonic", "templates", "sonic-environment.j2")
    SONIC_VERSION_YML_FILE = os.path.join('/', "etc", "sonic", "sonic_version.yml")
    SONIC_ENV_FILE = os.path.join('/', "etc", "sonic", "sonic-environment")

    if os.path.isfile(SONIC_ENV_TEMPLATE_FILE) and os.path.isfile(SONIC_VERSION_YML_FILE):
        clicommon.run_command(
            "{} -d -y {} -t {},{}".format(
                SONIC_CFGGEN_PATH,
                SONIC_VERSION_YML_FILE,
                SONIC_ENV_TEMPLATE_FILE,
                SONIC_ENV_FILE
            ),
            display_cmd=True
        )

def cache_arp_entries():
    success = True
    cache_dir = '/host/config-reload'
    click.echo('Caching ARP table to {}'.format(cache_dir))

    if not os.path.exists(cache_dir):
        os.mkdir(cache_dir)

    arp_cache_cmd = '/usr/local/bin/fast-reboot-dump.py -t {}'.format(cache_dir)
    cache_proc = subprocess.Popen(arp_cache_cmd, shell=True, text=True, stdout=subprocess.PIPE)
    _, cache_err = cache_proc.communicate()
    if cache_err:
        click.echo("Could not cache ARP and FDB info prior to reloading")
        success = False

    if not cache_err:
        fdb_cache_file = os.path.join(cache_dir, 'fdb.json')
        arp_cache_file = os.path.join(cache_dir, 'arp.json')
        fdb_filter_cmd = '/usr/local/bin/filter_fdb_entries -f {} -a {} -c /etc/sonic/configdb.json'.format(fdb_cache_file, arp_cache_file)
        filter_proc = subprocess.Popen(fdb_filter_cmd, shell=True, text=True, stdout=subprocess.PIPE)
        _, filter_err = filter_proc.communicate()
        if filter_err:
            click.echo("Could not filter FDB entries prior to reloading")
            success = False
    
    # If we are able to successfully cache ARP table info, signal SWSS to restore from our cache
    # by creating /host/config-reload/needs-restore
    if success:
        restore_flag_file = os.path.join(cache_dir, 'needs-restore')
        open(restore_flag_file, 'w').close()
    return success

# This is our main entrypoint - the main 'config' command
@click.group(cls=clicommon.AbbreviationGroup, context_settings=CONTEXT_SETTINGS)
@click.pass_context
def config(ctx):
    """SONiC command line - 'config' command"""
    #
    # Load asic_type for further use
    #
    global asic_type

    try:
        version_info = device_info.get_sonic_version_info()
        asic_type = version_info['asic_type']
    except (KeyError, TypeError):
        raise click.Abort()

    # Load the global config file database_global.json once.
    num_asic = multi_asic.get_num_asics()
    if num_asic > 1:
        SonicDBConfig.load_sonic_global_db_config()
    else:
        SonicDBConfig.initialize()

    if os.geteuid() != 0:
        exit("Root privileges are required for this operation")

    ctx.obj = Db()


# Add groups from other modules
config.add_command(aaa.aaa)
config.add_command(aaa.tacacs)
config.add_command(chassis_modules.chassis_modules)
config.add_command(console.console)
config.add_command(feature.feature)
config.add_command(kdump.kdump)
config.add_command(kube.kubernetes)
config.add_command(muxcable.muxcable)
config.add_command(nat.nat)
config.add_command(vlan.vlan)
config.add_command(vxlan.vxlan)

@config.command()
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false,
                expose_value=False, prompt='Existing files will be overwritten, continue?')
@click.argument('filename', required=False)
def save(filename):
    """Export current config DB to a file on disk.\n
       <filename> : Names of configuration file(s) to save, separated by comma with no spaces in between
    """
    num_asic = multi_asic.get_num_asics()
    cfg_files = []

    num_cfg_file = 1
    if multi_asic.is_multi_asic():
        num_cfg_file += num_asic

    # If the user give the filename[s], extract the file names.
    if filename is not None:
        cfg_files = filename.split(',')

        if len(cfg_files) != num_cfg_file:
            click.echo("Input {} config file(s) separated by comma for multiple files ".format(num_cfg_file))
            return

    # In case of multi-asic mode we have additional config_db{NS}.json files for
    # various namespaces created per ASIC. {NS} is the namespace index.
    for inst in range(-1, num_cfg_file-1):
        #inst = -1, refers to the linux host where there is no namespace.
        if inst == -1:
            namespace = None
        else:
            namespace = "{}{}".format(NAMESPACE_PREFIX, inst)

        # Get the file from user input, else take the default file /etc/sonic/config_db{NS_id}.json
        if cfg_files:
            file = cfg_files[inst+1]
        else:
            if namespace is None:
                file = DEFAULT_CONFIG_DB_FILE
            else:
                file = "/etc/sonic/config_db{}.json".format(inst)

        if namespace is None:
            command = "{} -d --print-data > {}".format(SONIC_CFGGEN_PATH, file)
        else:
            command = "{} -n {} -d --print-data > {}".format(SONIC_CFGGEN_PATH, namespace, file)

        log.log_info("'save' executing...")
        clicommon.run_command(command, display_cmd=True)

@config.command()
@click.option('-y', '--yes', is_flag=True)
@click.argument('filename', required=False)
def load(filename, yes):
    """Import a previous saved config DB dump file.
       <filename> : Names of configuration file(s) to load, separated by comma with no spaces in between
    """
    if filename is None:
        message = 'Load config from the default config file(s) ?'
    else:
        message = 'Load config from the file(s) {} ?'.format(filename)

    if not yes:
        click.confirm(message, abort=True)

    num_asic = multi_asic.get_num_asics()
    cfg_files = []

    num_cfg_file = 1
    if multi_asic.is_multi_asic():
        num_cfg_file += num_asic

    # If the user give the filename[s], extract the file names.
    if filename is not None:
        cfg_files = filename.split(',')

        if len(cfg_files) != num_cfg_file:
            click.echo("Input {} config file(s) separated by comma for multiple files ".format(num_cfg_file))
            return

    # In case of multi-asic mode we have additional config_db{NS}.json files for
    # various namespaces created per ASIC. {NS} is the namespace index.
    for inst in range(-1, num_cfg_file-1):
        #inst = -1, refers to the linux host where there is no namespace.
        if inst == -1:
            namespace = None
        else:
            namespace = "{}{}".format(NAMESPACE_PREFIX, inst)

        # Get the file from user input, else take the default file /etc/sonic/config_db{NS_id}.json
        if cfg_files:
            file = cfg_files[inst+1]
        else:
            if namespace is None:
                file = DEFAULT_CONFIG_DB_FILE
            else:
                file = "/etc/sonic/config_db{}.json".format(inst)

        # if any of the config files in linux host OR namespace is not present, return
        if not os.path.exists(file):
            click.echo("The config_db file {} doesn't exist".format(file))
            return

        if namespace is None:
            command = "{} -j {} --write-to-db".format(SONIC_CFGGEN_PATH, file)
        else:
            command = "{} -n {} -j {} --write-to-db".format(SONIC_CFGGEN_PATH, namespace, file)

        log.log_info("'load' executing...")
        clicommon.run_command(command, display_cmd=True)


@config.command()
@click.option('-y', '--yes', is_flag=True)
@click.option('-l', '--load-sysinfo', is_flag=True, help='load system default information (mac, portmap etc) first.')
@click.option('-n', '--no_service_restart', default=False, is_flag=True, help='Do not restart docker services')
@click.option('-d', '--disable_arp_cache', default=False, is_flag=True, help='Do not cache ARP table before reloading (applies to dual ToR systems only)')
@click.argument('filename', required=False)
@clicommon.pass_db
def reload(db, filename, yes, load_sysinfo, no_service_restart, disable_arp_cache):
    """Clear current configuration and import a previous saved config DB dump file.
       <filename> : Names of configuration file(s) to load, separated by comma with no spaces in between
    """
    if filename is None:
        message = 'Clear current config and reload config from the default config file(s) ?'
    else:
        message = 'Clear current config and reload config from the file(s) {} ?'.format(filename)

    if not yes:
        click.confirm(message, abort=True)

    log.log_info("'reload' executing...")

    num_asic = multi_asic.get_num_asics()
    cfg_files = []

    num_cfg_file = 1
    if multi_asic.is_multi_asic():
        num_cfg_file += num_asic

    # If the user give the filename[s], extract the file names.
    if filename is not None:
        cfg_files = filename.split(',')

        if len(cfg_files) != num_cfg_file:
            click.echo("Input {} config file(s) separated by comma for multiple files ".format(num_cfg_file))
            return

    if load_sysinfo:
        command = "{} -j {} -v DEVICE_METADATA.localhost.hwsku".format(SONIC_CFGGEN_PATH, filename)
        proc = subprocess.Popen(command, shell=True, text=True, stdout=subprocess.PIPE)
        cfg_hwsku, err = proc.communicate()
        if err:
            click.echo("Could not get the HWSKU from config file, exiting")
            sys.exit(1)
        else:
            cfg_hwsku = cfg_hwsku.strip()

    # For dual ToR devices, cache ARP and FDB info
    localhost_metadata = db.cfgdb.get_table('DEVICE_METADATA')['localhost']
    cache_arp_table = not disable_arp_cache and 'subtype' in localhost_metadata and localhost_metadata['subtype'].lower() == 'dualtor'

    if cache_arp_table:
        cache_arp_entries()

    #Stop services before config push
    if not no_service_restart:
        log.log_info("'reload' stopping services...")
        _stop_services()

    # In Single ASIC platforms we have single DB service. In multi-ASIC platforms we have a global DB
    # service running in the host + DB services running in each ASIC namespace created per ASIC.
    # In the below logic, we get all namespaces in this platform and add an empty namespace ''
    # denoting the current namespace which we are in ( the linux host )
    for inst in range(-1, num_cfg_file-1):
        # Get the namespace name, for linux host it is None
        if inst == -1:
            namespace = None
        else:
            namespace = "{}{}".format(NAMESPACE_PREFIX, inst)

        # Get the file from user input, else take the default file /etc/sonic/config_db{NS_id}.json
        if cfg_files:
            file = cfg_files[inst+1]
        else:
            if namespace is None:
                file = DEFAULT_CONFIG_DB_FILE
            else:
                file = "/etc/sonic/config_db{}.json".format(inst)

        # Check the file exists before proceeding.
        if not os.path.exists(file):
            click.echo("The config_db file {} doesn't exist".format(file))
            continue

        if namespace is None:
            config_db = ConfigDBConnector()
        else:
            config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)

        config_db.connect()
        client = config_db.get_redis_client(config_db.CONFIG_DB)
        client.flushdb()
        if load_sysinfo:
            if namespace is None:
                command = "{} -H -k {} --write-to-db".format(SONIC_CFGGEN_PATH, cfg_hwsku)
            else:
                command = "{} -H -k {} -n {} --write-to-db".format(SONIC_CFGGEN_PATH, cfg_hwsku, namespace)
            clicommon.run_command(command, display_cmd=True)

        # For the database service running in linux host we use the file user gives as input
        # or by default DEFAULT_CONFIG_DB_FILE. In the case of database service running in namespace,
        # the default config_db<namespaceID>.json format is used.
        if namespace is None:
            if os.path.isfile(INIT_CFG_FILE):
                command = "{} -j {} -j {} --write-to-db".format(SONIC_CFGGEN_PATH, INIT_CFG_FILE, file)
            else:
                command = "{} -j {} --write-to-db".format(SONIC_CFGGEN_PATH, file)
        else:
            if os.path.isfile(INIT_CFG_FILE):
                command = "{} -j {} -j {} -n {} --write-to-db".format(SONIC_CFGGEN_PATH, INIT_CFG_FILE, file, namespace)
            else:
                command = "{} -j {} -n {} --write-to-db".format(SONIC_CFGGEN_PATH, file, namespace)

        clicommon.run_command(command, display_cmd=True)
        client.set(config_db.INIT_INDICATOR, 1)

        # Migrate DB contents to latest version
        db_migrator='/usr/local/bin/db_migrator.py'
        if os.path.isfile(db_migrator) and os.access(db_migrator, os.X_OK):
            if namespace is None:
                command = "{} -o migrate".format(db_migrator)
            else:
                command = "{} -o migrate -n {}".format(db_migrator, namespace)
            clicommon.run_command(command, display_cmd=True)

    # We first run "systemctl reset-failed" to remove the "failed"
    # status from all services before we attempt to restart them
    if not no_service_restart:
        _reset_failed_services()
        log.log_info("'reload' restarting services...")
        _restart_services()

@config.command("load_mgmt_config")
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false,
                expose_value=False, prompt='Reload mgmt config?')
@click.argument('filename', default='/etc/sonic/device_desc.xml', type=click.Path(exists=True))
def load_mgmt_config(filename):
    """Reconfigure hostname and mgmt interface based on device description file."""
    log.log_info("'load_mgmt_config' executing...")
    command = "{} -M {} --write-to-db".format(SONIC_CFGGEN_PATH, filename)
    clicommon.run_command(command, display_cmd=True)
    #FIXME: After config DB daemon for hostname and mgmt interface is implemented, we'll no longer need to do manual configuration here
    config_data = parse_device_desc_xml(filename)
    hostname = config_data['DEVICE_METADATA']['localhost']['hostname']
    _change_hostname(hostname)
    mgmt_conf = netaddr.IPNetwork(list(config_data['MGMT_INTERFACE'].keys())[0][1])
    gw_addr = list(config_data['MGMT_INTERFACE'].values())[0]['gwaddr']
    command = "ifconfig eth0 {} netmask {}".format(str(mgmt_conf.ip), str(mgmt_conf.netmask))
    clicommon.run_command(command, display_cmd=True)
    command = "ip route add default via {} dev eth0 table default".format(gw_addr)
    clicommon.run_command(command, display_cmd=True, ignore_error=True)
    command = "ip rule add from {} table default".format(str(mgmt_conf.ip))
    clicommon.run_command(command, display_cmd=True, ignore_error=True)
    command = "[ -f /var/run/dhclient.eth0.pid ] && kill `cat /var/run/dhclient.eth0.pid` && rm -f /var/run/dhclient.eth0.pid"
    clicommon.run_command(command, display_cmd=True, ignore_error=True)
    click.echo("Please note loaded setting will be lost after system reboot. To preserve setting, run `config save`.")

@config.command("load_minigraph")
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false,
                expose_value=False, prompt='Reload config from minigraph?')
@click.option('-n', '--no_service_restart', default=False, is_flag=True, help='Do not restart docker services')
@clicommon.pass_db
def load_minigraph(db, no_service_restart):
    """Reconfigure based on minigraph."""
    log.log_info("'load_minigraph' executing...")

    #Stop services before config push
    if not no_service_restart:
        log.log_info("'load_minigraph' stopping services...")
        _stop_services()

    # For Single Asic platform the namespace list has the empty string
    # for mulit Asic platform the empty string to generate the config
    # for host
    namespace_list = [DEFAULT_NAMESPACE]
    num_npus = multi_asic.get_num_asics()
    if num_npus > 1:
        namespace_list += multi_asic.get_namespaces_from_linux()

    for namespace in namespace_list:
        if namespace is DEFAULT_NAMESPACE:
            config_db = ConfigDBConnector()
            cfggen_namespace_option = " "
            ns_cmd_prefix = ""
        else:
            config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
            cfggen_namespace_option = " -n {}".format(namespace)
            ns_cmd_prefix = "sudo ip netns exec {} ".format(namespace)
        config_db.connect()
        client = config_db.get_redis_client(config_db.CONFIG_DB)
        client.flushdb()
        if os.path.isfile('/etc/sonic/init_cfg.json'):
            command = "{} -H -m -j /etc/sonic/init_cfg.json {} --write-to-db".format(SONIC_CFGGEN_PATH, cfggen_namespace_option)
        else:
            command = "{} -H -m --write-to-db {}".format(SONIC_CFGGEN_PATH, cfggen_namespace_option)
        clicommon.run_command(command, display_cmd=True)
        client.set(config_db.INIT_INDICATOR, 1)

    # get the device type
    device_type = _get_device_type()
    if device_type != 'MgmtToRRouter' and device_type != 'EPMS':
        clicommon.run_command("pfcwd start_default", display_cmd=True)

    # Update SONiC environmnet file
    update_sonic_environment()

    if os.path.isfile('/etc/sonic/acl.json'):
        clicommon.run_command("acl-loader update full /etc/sonic/acl.json", display_cmd=True)

    # generate QoS and Buffer configs
    clicommon.run_command("config qos reload --no-dynamic-buffer", display_cmd=True)

    # Write latest db version string into db
    db_migrator='/usr/local/bin/db_migrator.py'
    if os.path.isfile(db_migrator) and os.access(db_migrator, os.X_OK):
        for namespace in namespace_list:
            if namespace is DEFAULT_NAMESPACE:
                cfggen_namespace_option = " "
            else:
                cfggen_namespace_option = " -n {}".format(namespace)
            clicommon.run_command(db_migrator + ' -o set_version' + cfggen_namespace_option)

    # We first run "systemctl reset-failed" to remove the "failed"
    # status from all services before we attempt to restart them
    if not no_service_restart:
        _reset_failed_services()
        #FIXME: After config DB daemon is implemented, we'll no longer need to restart every service.
        log.log_info("'load_minigraph' restarting services...")
        _restart_services()
    click.echo("Please note setting loaded from minigraph will be lost after system reboot. To preserve setting, run `config save`.")


#
# 'hostname' command
#
@config.command('hostname')
@click.argument('new_hostname', metavar='<new_hostname>', required=True)
def hostname(new_hostname):
    """Change device hostname without impacting the traffic."""

    config_db = ConfigDBConnector()
    config_db.connect()
    config_db.mod_entry('DEVICE_METADATA' , 'localhost', {"hostname" : new_hostname})
    try:
        command = "service hostname-config restart"
        clicommon.run_command(command, display_cmd=True)
    except SystemExit as e:
        click.echo("Restarting hostname-config  service failed with error {}".format(e))
        raise

    # Reload Monit configuration to pick up new hostname in case it changed
    click.echo("Reloading Monit configuration ...")
    clicommon.run_command("sudo monit reload")

    click.echo("Please note loaded setting will be lost after system reboot. To preserve setting, run `config save`.")

#
# 'synchronous_mode' command ('config synchronous_mode ...')
#
@config.command('synchronous_mode')
@click.argument('sync_mode', metavar='<enable|disable>', required=True)
def synchronous_mode(sync_mode):
    """ Enable or disable synchronous mode between orchagent and syncd \n
        swss restart required to apply the configuration \n
        Options to restart swss and apply the configuration: \n
            1. config save -y \n
               config reload -y \n
            2. systemctl restart swss
    """

    if sync_mode == 'enable' or sync_mode == 'disable':
        config_db = ConfigDBConnector()
        config_db.connect()
        config_db.mod_entry('DEVICE_METADATA' , 'localhost', {"synchronous_mode" : sync_mode})
        click.echo("""Wrote %s synchronous mode into CONFIG_DB, swss restart required to apply the configuration: \n
    Option 1. config save -y \n
              config reload -y \n
    Option 2. systemctl restart swss""" % sync_mode)
    else:
        raise click.BadParameter("Error: Invalid argument %s, expect either enable or disable" % sync_mode)

#
# 'portchannel' group ('config portchannel ...')
#
@config.group(cls=clicommon.AbbreviationGroup)
# TODO add "hidden=True if this is a single ASIC platform, once we have click 7.0 in all branches.
@click.option('-n', '--namespace', help='Namespace name',
             required=True if multi_asic.is_multi_asic() else False, type=click.Choice(multi_asic.get_namespace_list()))
@click.pass_context
def portchannel(ctx, namespace):
    # Set namespace to default_namespace if it is None.
    if namespace is None:
        namespace = DEFAULT_NAMESPACE

    config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=str(namespace))
    config_db.connect()
    ctx.obj = {'db': config_db, 'namespace': str(namespace)}

@portchannel.command('add')
@click.argument('portchannel_name', metavar='<portchannel_name>', required=True)
@click.option('--min-links', default=0, type=int)
@click.option('--fallback', default='false')
@click.pass_context
def add_portchannel(ctx, portchannel_name, min_links, fallback):
    """Add port channel"""
    if is_portchannel_name_valid(portchannel_name) != True:
        ctx.fail("{} is invalid!, name should have prefix '{}' and suffix '{}'"
                 .format(portchannel_name, CFG_PORTCHANNEL_PREFIX, CFG_PORTCHANNEL_NO))

    db = ctx.obj['db']

    if is_portchannel_present_in_db(db, portchannel_name):
        ctx.fail("{} already exists!".format(portchannel_name))

    fvs = {'admin_status': 'up',
           'mtu': '9100'}
    if min_links != 0:
        fvs['min_links'] = str(min_links)
    if fallback != 'false':
        fvs['fallback'] = 'true'
    db.set_entry('PORTCHANNEL', portchannel_name, fvs)

@portchannel.command('del')
@click.argument('portchannel_name', metavar='<portchannel_name>', required=True)
@click.pass_context
def remove_portchannel(ctx, portchannel_name):
    """Remove port channel"""
    if is_portchannel_name_valid(portchannel_name) != True:
        ctx.fail("{} is invalid!, name should have prefix '{}' and suffix '{}'"
                 .format(portchannel_name, CFG_PORTCHANNEL_PREFIX, CFG_PORTCHANNEL_NO))

    db = ctx.obj['db']

    # Dont proceed if the port channel does not exist
    if is_portchannel_present_in_db(db, portchannel_name) is False:
        ctx.fail("{} is not present.".format(portchannel_name))

    if len([(k, v) for k, v in db.get_table('PORTCHANNEL_MEMBER') if k == portchannel_name]) != 0:
        click.echo("Error: Portchannel {} contains members. Remove members before deleting Portchannel!".format(portchannel_name))
    else:
        db.set_entry('PORTCHANNEL', portchannel_name, None)

@portchannel.group(cls=clicommon.AbbreviationGroup, name='member')
@click.pass_context
def portchannel_member(ctx):
    pass

@portchannel_member.command('add')
@click.argument('portchannel_name', metavar='<portchannel_name>', required=True)
@click.argument('port_name', metavar='<port_name>', required=True)
@click.pass_context
def add_portchannel_member(ctx, portchannel_name, port_name):
    """Add member to port channel"""
    db = ctx.obj['db']
    if clicommon.is_port_mirror_dst_port(db, port_name):
        ctx.fail("{} is configured as mirror destination port".format(port_name))

    # Check if the member interface given by user is valid in the namespace.
    if port_name.startswith("Ethernet") is False or interface_name_is_valid(db, port_name) is False:
        ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    # Dont proceed if the port channel name is not valid
    if is_portchannel_name_valid(portchannel_name) is False:
        ctx.fail("{} is invalid!, name should have prefix '{}' and suffix '{}'"
                 .format(portchannel_name, CFG_PORTCHANNEL_PREFIX, CFG_PORTCHANNEL_NO))

    # Dont proceed if the port channel does not exist
    if is_portchannel_present_in_db(db, portchannel_name) is False:
        ctx.fail("{} is not present.".format(portchannel_name))

    # Dont allow a port to be member of port channel if it is configured with an IP address
    for key in db.get_table('INTERFACE').keys():
        if type(key) != tuple:
            continue
        if key[0] == port_name:
            ctx.fail(" {} has ip address {} configured".format(port_name, key[1]))
            return

    # Dont allow a port to be member of port channel if it is configured as a VLAN member
    for k,v in db.get_table('VLAN_MEMBER'):
        if v == port_name:
            ctx.fail("%s Interface configured as VLAN_MEMBER under vlan : %s" %(port_name,str(k)))
            return

    # Dont allow a port to be member of port channel if it is already member of a port channel
    for k,v in db.get_table('PORTCHANNEL_MEMBER'):
        if v == port_name:
            ctx.fail("{} Interface is already member of {} ".format(v,k))

    # Dont allow a port to be member of port channel if its speed does not match with existing members
    for k,v in db.get_table('PORTCHANNEL_MEMBER'):
        if k == portchannel_name:
            member_port_entry = db.get_entry('PORT', v)
            port_entry = db.get_entry('PORT', port_name)

            if member_port_entry is not None and port_entry is not None:
                member_port_speed = member_port_entry.get(PORT_SPEED)

                port_speed = port_entry.get(PORT_SPEED)
                if member_port_speed != port_speed:
                    ctx.fail("Port speed of {} is different than the other members of the portchannel {}"
                             .format(port_name, portchannel_name))

    # Dont allow a port to be member of port channel if its MTU does not match with portchannel
    portchannel_entry =  db.get_entry('PORTCHANNEL', portchannel_name)
    if portchannel_entry and portchannel_entry.get(PORT_MTU) is not None :
       port_entry = db.get_entry('PORT', port_name)

       if port_entry and port_entry.get(PORT_MTU) is not None:
            port_mtu = port_entry.get(PORT_MTU)

            portchannel_mtu = portchannel_entry.get(PORT_MTU)
            if portchannel_mtu != port_mtu:
                ctx.fail("Port MTU of {} is different than the {} MTU size"
                         .format(port_name, portchannel_name))

    db.set_entry('PORTCHANNEL_MEMBER', (portchannel_name, port_name),
            {'NULL': 'NULL'})

@portchannel_member.command('del')
@click.argument('portchannel_name', metavar='<portchannel_name>', required=True)
@click.argument('port_name', metavar='<port_name>', required=True)
@click.pass_context
def del_portchannel_member(ctx, portchannel_name, port_name):
    """Remove member from portchannel"""
    # Dont proceed if the port channel name is not valid
    if is_portchannel_name_valid(portchannel_name) is False:
        ctx.fail("{} is invalid!, name should have prefix '{}' and suffix '{}'"
                 .format(portchannel_name, CFG_PORTCHANNEL_PREFIX, CFG_PORTCHANNEL_NO))

    db = ctx.obj['db']

    # Check if the member interface given by user is valid in the namespace.
    if interface_name_is_valid(db, port_name) is False:
        ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    # Dont proceed if the port channel does not exist
    if is_portchannel_present_in_db(db, portchannel_name) is False:
        ctx.fail("{} is not present.".format(portchannel_name))

    # Dont proceed if the the port is not an existing member of the port channel
    if not is_port_member_of_this_portchannel(db, port_name, portchannel_name):
        ctx.fail("{} is not a member of portchannel {}".format(port_name, portchannel_name))

    db.set_entry('PORTCHANNEL_MEMBER', (portchannel_name, port_name), None)
    db.set_entry('PORTCHANNEL_MEMBER', portchannel_name + '|' + port_name, None)


#
# 'mirror_session' group ('config mirror_session ...')
#
@config.group(cls=clicommon.AbbreviationGroup, name='mirror_session')
def mirror_session():
    pass

#
# 'add' subgroup ('config mirror_session add ...')
#

@mirror_session.command('add')
@click.argument('session_name', metavar='<session_name>', required=True)
@click.argument('src_ip', metavar='<src_ip>', required=True)
@click.argument('dst_ip', metavar='<dst_ip>', required=True)
@click.argument('dscp', metavar='<dscp>', required=True)
@click.argument('ttl', metavar='<ttl>', required=True)
@click.argument('gre_type', metavar='[gre_type]', required=False)
@click.argument('queue', metavar='[queue]', required=False)
@click.option('--policer')
def add(session_name, src_ip, dst_ip, dscp, ttl, gre_type, queue, policer):
    """ Add ERSPAN mirror session.(Legacy support) """
    add_erspan(session_name, src_ip, dst_ip, dscp, ttl, gre_type, queue, policer)

@mirror_session.group(cls=clicommon.AbbreviationGroup, name='erspan')
@click.pass_context
def erspan(ctx):
    """ ERSPAN mirror_session """
    pass


#
# 'add' subcommand
#

@erspan.command('add')
@click.argument('session_name', metavar='<session_name>', required=True)
@click.argument('src_ip', metavar='<src_ip>', required=True)
@click.argument('dst_ip', metavar='<dst_ip>', required=True)
@click.argument('dscp', metavar='<dscp>', required=True)
@click.argument('ttl', metavar='<ttl>', required=True)
@click.argument('gre_type', metavar='[gre_type]', required=False)
@click.argument('queue', metavar='[queue]', required=False)
@click.argument('src_port', metavar='[src_port]', required=False)
@click.argument('direction', metavar='[direction]', required=False)
@click.option('--policer')
def add(session_name, src_ip, dst_ip, dscp, ttl, gre_type, queue, policer, src_port, direction):
    """ Add ERSPAN mirror session """
    add_erspan(session_name, src_ip, dst_ip, dscp, ttl, gre_type, queue, policer, src_port, direction)

def gather_session_info(session_info, policer, queue, src_port, direction):
    if policer:
        session_info['policer'] = policer

    if queue:
        session_info['queue'] = queue

    if src_port:
        if clicommon.get_interface_naming_mode() == "alias":
            src_port_list = []
            for port in src_port.split(","):
                src_port_list.append(interface_alias_to_name(None, port))
            src_port=",".join(src_port_list)

        session_info['src_port'] = src_port
        if not direction:
            direction = "both"
        session_info['direction'] = direction.upper()

    return session_info

def add_erspan(session_name, src_ip, dst_ip, dscp, ttl, gre_type, queue, policer, src_port=None, direction=None):
    session_info = {
            "type" : "ERSPAN",
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "dscp": dscp,
            "ttl": ttl
            }

    if gre_type:
        session_info['gre_type'] = gre_type

    session_info = gather_session_info(session_info, policer, queue, src_port, direction)

    """
    For multi-npu platforms we need to program all front asic namespaces
    """
    namespaces = multi_asic.get_all_namespaces()
    if not namespaces['front_ns']:
        config_db = ConfigDBConnector()
        config_db.connect()
        if validate_mirror_session_config(config_db, session_name, None, src_port, direction) is False:
            return
        config_db.set_entry("MIRROR_SESSION", session_name, session_info)
    else:
        per_npu_configdb = {}
        for front_asic_namespaces in namespaces['front_ns']:
            per_npu_configdb[front_asic_namespaces] = ConfigDBConnector(use_unix_socket_path=True, namespace=front_asic_namespaces)
            per_npu_configdb[front_asic_namespaces].connect()
            if validate_mirror_session_config(per_npu_configdb[front_asic_namespaces], session_name, None, src_port, direction) is False:
                return
            per_npu_configdb[front_asic_namespaces].set_entry("MIRROR_SESSION", session_name, session_info)

@mirror_session.group(cls=clicommon.AbbreviationGroup, name='span')
@click.pass_context
def span(ctx):
    """ SPAN mirror session """
    pass

@span.command('add')
@click.argument('session_name', metavar='<session_name>', required=True)
@click.argument('dst_port', metavar='<dst_port>', required=True)
@click.argument('src_port', metavar='[src_port]', required=False)
@click.argument('direction', metavar='[direction]', required=False)
@click.argument('queue', metavar='[queue]', required=False)
@click.option('--policer')
def add(session_name, dst_port, src_port, direction, queue, policer):
    """ Add SPAN mirror session """
    add_span(session_name, dst_port, src_port, direction, queue, policer)

def add_span(session_name, dst_port, src_port, direction, queue, policer):
    if clicommon.get_interface_naming_mode() == "alias":
        dst_port = interface_alias_to_name(None, dst_port)
        if dst_port is None:
            click.echo("Error: Destination Interface {} is invalid".format(dst_port))
            return

    session_info = {
            "type" : "SPAN",
            "dst_port": dst_port,
            }

    session_info = gather_session_info(session_info, policer, queue, src_port, direction)

    """
    For multi-npu platforms we need to program all front asic namespaces
    """
    namespaces = multi_asic.get_all_namespaces()
    if not namespaces['front_ns']:
        config_db = ConfigDBConnector()
        config_db.connect()
        if validate_mirror_session_config(config_db, session_name, dst_port, src_port, direction) is False:
            return
        config_db.set_entry("MIRROR_SESSION", session_name, session_info)
    else:
        per_npu_configdb = {}
        for front_asic_namespaces in namespaces['front_ns']:
            per_npu_configdb[front_asic_namespaces] = ConfigDBConnector(use_unix_socket_path=True, namespace=front_asic_namespaces)
            per_npu_configdb[front_asic_namespaces].connect()
            if validate_mirror_session_config(per_npu_configdb[front_asic_namespaces], session_name, dst_port, src_port, direction) is False:
                return
            per_npu_configdb[front_asic_namespaces].set_entry("MIRROR_SESSION", session_name, session_info)


@mirror_session.command()
@click.argument('session_name', metavar='<session_name>', required=True)
def remove(session_name):
    """ Delete mirror session """

    """
    For multi-npu platforms we need to program all front asic namespaces
    """
    namespaces = multi_asic.get_all_namespaces()
    if not namespaces['front_ns']:
        config_db = ConfigDBConnector()
        config_db.connect()
        config_db.set_entry("MIRROR_SESSION", session_name, None)
    else:
        per_npu_configdb = {}
        for front_asic_namespaces in namespaces['front_ns']:
            per_npu_configdb[front_asic_namespaces] = ConfigDBConnector(use_unix_socket_path=True, namespace=front_asic_namespaces)
            per_npu_configdb[front_asic_namespaces].connect()
            per_npu_configdb[front_asic_namespaces].set_entry("MIRROR_SESSION", session_name, None)

#
# 'pfcwd' group ('config pfcwd ...')
#
@config.group(cls=clicommon.AbbreviationGroup)
def pfcwd():
    """Configure pfc watchdog """
    pass

@pfcwd.command()
@click.option('--action', '-a', type=click.Choice(['drop', 'forward', 'alert']))
@click.option('--restoration-time', '-r', type=click.IntRange(100, 60000))
@click.option('--verbose', is_flag=True, help="Enable verbose output")
@click.argument('ports', nargs=-1)
@click.argument('detection-time', type=click.IntRange(100, 5000))
def start(action, restoration_time, ports, detection_time, verbose):
    """
    Start PFC watchdog on port(s). To config all ports, use all as input.

    Example:
        config pfcwd start --action drop ports all detection-time 400 --restoration-time 400
    """
    cmd = "pfcwd start"

    if action:
        cmd += " --action {}".format(action)

    if ports:
        ports = set(ports) - set(['ports', 'detection-time'])
        cmd += " {}".format(' '.join(ports))

    if detection_time:
        cmd += " {}".format(detection_time)

    if restoration_time:
        cmd += " --restoration-time {}".format(restoration_time)

    clicommon.run_command(cmd, display_cmd=verbose)

@pfcwd.command()
@click.option('--verbose', is_flag=True, help="Enable verbose output")
def stop(verbose):
    """ Stop PFC watchdog """

    cmd = "pfcwd stop"

    clicommon.run_command(cmd, display_cmd=verbose)

@pfcwd.command()
@click.option('--verbose', is_flag=True, help="Enable verbose output")
@click.argument('poll_interval', type=click.IntRange(100, 3000))
def interval(poll_interval, verbose):
    """ Set PFC watchdog counter polling interval (ms) """

    cmd = "pfcwd interval {}".format(poll_interval)

    clicommon.run_command(cmd, display_cmd=verbose)

@pfcwd.command('counter_poll')
@click.option('--verbose', is_flag=True, help="Enable verbose output")
@click.argument('counter_poll', type=click.Choice(['enable', 'disable']))
def counter_poll(counter_poll, verbose):
    """ Enable/disable counter polling """

    cmd = "pfcwd counter_poll {}".format(counter_poll)

    clicommon.run_command(cmd, display_cmd=verbose)

@pfcwd.command('big_red_switch')
@click.option('--verbose', is_flag=True, help="Enable verbose output")
@click.argument('big_red_switch', type=click.Choice(['enable', 'disable']))
def big_red_switch(big_red_switch, verbose):
    """ Enable/disable BIG_RED_SWITCH mode """

    cmd = "pfcwd big_red_switch {}".format(big_red_switch)

    clicommon.run_command(cmd, display_cmd=verbose)

@pfcwd.command('start_default')
@click.option('--verbose', is_flag=True, help="Enable verbose output")
def start_default(verbose):
    """ Start PFC WD by default configurations  """

    cmd = "pfcwd start_default"

    clicommon.run_command(cmd, display_cmd=verbose)

#
# 'qos' group ('config qos ...')
#
@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def qos(ctx):
    """QoS-related configuration tasks"""
    pass

@qos.command('clear')
def clear():
    """Clear QoS configuration"""
    log.log_info("'qos clear' executing...")
    _clear_qos()

def _update_buffer_calculation_model(config_db, model):
    """Update the buffer calculation model into CONFIG_DB"""
    buffer_model_changed = False
    device_metadata = config_db.get_entry('DEVICE_METADATA', 'localhost')
    if device_metadata.get('buffer_model') != model:
        buffer_model_changed = True
        device_metadata['buffer_model'] = model
        config_db.set_entry('DEVICE_METADATA', 'localhost', device_metadata)
    return buffer_model_changed

@qos.command('reload')
@click.pass_context
@click.option('--no-dynamic-buffer', is_flag=True, help="Disable dynamic buffer calculation")
@click.option(
    '--json-data', type=click.STRING,
    help="json string with additional data, valid with --dry-run option"
)
@click.option(
    '--dry_run', type=click.STRING,
    help="Dry run, writes config to the given file"
)
def reload(ctx, no_dynamic_buffer, dry_run, json_data):
    """Reload QoS configuration"""
    log.log_info("'qos reload' executing...")
    _clear_qos()

    _, hwsku_path = device_info.get_paths_to_platform_and_hwsku_dirs()
    sonic_version_file = device_info.get_sonic_version_file()
    from_db = "-d --write-to-db"
    if dry_run:
        from_db = "--additional-data \'{}\'".format(json_data) if json_data else ""

    namespace_list = [DEFAULT_NAMESPACE]
    if multi_asic.get_num_asics() > 1:
        namespace_list = multi_asic.get_namespaces_from_linux()

    buffer_model_updated = False
    vendors_supporting_dynamic_buffer = ["mellanox"]

    for ns in namespace_list:
        if ns is DEFAULT_NAMESPACE:
            asic_id_suffix = ""
            config_db = ConfigDBConnector()
        else:
            asic_id = multi_asic.get_asic_id_from_name(ns)
            if asic_id is None:
                click.secho(
                    "Command 'qos reload' failed with invalid namespace '{}'".
                        format(ns),
                    fg="yellow"
                )
                raise click.Abort()
            asic_id_suffix = str(asic_id)

            config_db = ConfigDBConnector(
                use_unix_socket_path=True, namespace=ns
            )

        config_db.connect()

        if not no_dynamic_buffer and asic_type in vendors_supporting_dynamic_buffer:
            buffer_template_file = os.path.join(hwsku_path, asic_id_suffix, "buffers_dynamic.json.j2")
            buffer_model_updated |= _update_buffer_calculation_model(config_db, "dynamic")
        else:
            buffer_template_file = os.path.join(hwsku_path, asic_id_suffix, "buffers.json.j2")
            if asic_type in vendors_supporting_dynamic_buffer:
                buffer_model_updated |= _update_buffer_calculation_model(config_db, "traditional")

        if os.path.isfile(buffer_template_file):
            qos_template_file = os.path.join(
                hwsku_path, asic_id_suffix, "qos.json.j2"
            )
            if os.path.isfile(qos_template_file):
                cmd_ns = "" if ns is DEFAULT_NAMESPACE else "-n {}".format(ns)
                fname = "{}{}".format(dry_run, asic_id_suffix) if dry_run else "config-db"
                command = "{} {} {} -t {},{} -t {},{} -y {}".format(
                    SONIC_CFGGEN_PATH, cmd_ns, from_db, buffer_template_file,
                    fname, qos_template_file, fname, sonic_version_file
                )
                # Apply the configurations only when both buffer and qos
                # configuration files are present
                clicommon.run_command(command, display_cmd=True)
            else:
                click.secho("QoS definition template not found at {}".format(
                    qos_template_file
                ), fg="yellow")
        else:
            click.secho("Buffer definition template not found at {}".format(
                buffer_template_file
            ), fg="yellow")

    if buffer_model_updated:
        print("Buffer calculation model updated, restarting swss is required to take effect")

def is_dynamic_buffer_enabled(config_db):
    """Return whether the current system supports dynamic buffer calculation"""
    device_metadata = config_db.get_entry('DEVICE_METADATA', 'localhost')
    return 'dynamic' == device_metadata.get('buffer_model')

#
# 'warm_restart' group ('config warm_restart ...')
#
@config.group(cls=clicommon.AbbreviationGroup, name='warm_restart')
@click.pass_context
@click.option('-s', '--redis-unix-socket-path', help='unix socket path for redis connection')
def warm_restart(ctx, redis_unix_socket_path):
    """warm_restart-related configuration tasks"""
    # Note: redis_unix_socket_path is a path string, and the ground truth is now from database_config.json.
    # We only use it as a bool indicator on either unix_socket_path or tcp port
    use_unix_socket_path = bool(redis_unix_socket_path)
    config_db = ConfigDBConnector(use_unix_socket_path=use_unix_socket_path)
    config_db.connect(wait_for_init=False)

    # warm restart enable/disable config is put in stateDB, not persistent across cold reboot, not saved to config_DB.json file
    state_db = SonicV2Connector(use_unix_socket_path=use_unix_socket_path)
    state_db.connect(state_db.STATE_DB, False)
    TABLE_NAME_SEPARATOR = '|'
    prefix = 'WARM_RESTART_ENABLE_TABLE' + TABLE_NAME_SEPARATOR
    ctx.obj = {'db': config_db, 'state_db': state_db, 'prefix': prefix}

@warm_restart.command('enable')
@click.argument('module', metavar='<module>', default='system', required=False, type=click.Choice(["system", "swss", "bgp", "teamd"]))
@click.pass_context
def warm_restart_enable(ctx, module):
    state_db = ctx.obj['state_db']
    prefix = ctx.obj['prefix']
    _hash = '{}{}'.format(prefix, module)
    state_db.set(state_db.STATE_DB, _hash, 'enable', 'true')
    state_db.close(state_db.STATE_DB)

@warm_restart.command('disable')
@click.argument('module', metavar='<module>', default='system', required=False, type=click.Choice(["system", "swss", "bgp", "teamd"]))
@click.pass_context
def warm_restart_enable(ctx, module):
    state_db = ctx.obj['state_db']
    prefix = ctx.obj['prefix']
    _hash = '{}{}'.format(prefix, module)
    state_db.set(state_db.STATE_DB, _hash, 'enable', 'false')
    state_db.close(state_db.STATE_DB)

@warm_restart.command('neighsyncd_timer')
@click.argument('seconds', metavar='<seconds>', required=True, type=int)
@click.pass_context
def warm_restart_neighsyncd_timer(ctx, seconds):
    db = ctx.obj['db']
    if seconds not in range(1, 9999):
        ctx.fail("neighsyncd warm restart timer must be in range 1-9999")
    db.mod_entry('WARM_RESTART', 'swss', {'neighsyncd_timer': seconds})

@warm_restart.command('bgp_timer')
@click.argument('seconds', metavar='<seconds>', required=True, type=int)
@click.pass_context
def warm_restart_bgp_timer(ctx, seconds):
    db = ctx.obj['db']
    if seconds not in range(1, 3600):
        ctx.fail("bgp warm restart timer must be in range 1-3600")
    db.mod_entry('WARM_RESTART', 'bgp', {'bgp_timer': seconds})

@warm_restart.command('teamsyncd_timer')
@click.argument('seconds', metavar='<seconds>', required=True, type=int)
@click.pass_context
def warm_restart_teamsyncd_timer(ctx, seconds):
    db = ctx.obj['db']
    if seconds not in range(1, 3600):
        ctx.fail("teamsyncd warm restart timer must be in range 1-3600")
    db.mod_entry('WARM_RESTART', 'teamd', {'teamsyncd_timer': seconds})

@warm_restart.command('bgp_eoiu')
@click.argument('enable', metavar='<enable>', default='true', required=False, type=click.Choice(["true", "false"]))
@click.pass_context
def warm_restart_bgp_eoiu(ctx, enable):
    db = ctx.obj['db']
    db.mod_entry('WARM_RESTART', 'bgp', {'bgp_eoiu': enable})

def mvrf_restart_services():
    """Restart interfaces-config service and NTP service when mvrf is changed"""
    """
    When mvrf is enabled, eth0 should be moved to mvrf; when it is disabled,
    move it back to default vrf. Restarting the "interfaces-config" service
    will recreate the /etc/network/interfaces file and restart the
    "networking" service that takes care of the eth0 movement.
    NTP service should also be restarted to rerun the NTP service with or
    without "cgexec" accordingly.
    """
    cmd="service ntp stop"
    os.system (cmd)
    cmd="systemctl restart interfaces-config"
    os.system (cmd)
    cmd="service ntp start"
    os.system (cmd)

def vrf_add_management_vrf(config_db):
    """Enable management vrf in config DB"""

    entry = config_db.get_entry('MGMT_VRF_CONFIG', "vrf_global")
    if entry and entry['mgmtVrfEnabled'] == 'true' :
        click.echo("ManagementVRF is already Enabled.")
        return None
    config_db.mod_entry('MGMT_VRF_CONFIG', "vrf_global", {"mgmtVrfEnabled": "true"})
    mvrf_restart_services()
    """
    The regular expression for grep in below cmd is to match eth0 line in /proc/net/route, sample file:
    $ cat /proc/net/route
        Iface   Destination     Gateway         Flags   RefCnt  Use     Metric  Mask            MTU     Window  IRTT
         eth0    00000000        01803B0A        0003    0       0       202     00000000        0       0       0
    """
    cmd = r"cat /proc/net/route | grep -E \"eth0\s+00000000\s+[0-9A-Z]+\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+202\" | wc -l"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    output = proc.communicate()
    if int(output[0]) >= 1:
        cmd="ip -4 route del default dev eth0 metric 202"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        proc.communicate()
        if proc.returncode != 0:
            click.echo("Could not delete eth0 route")

def vrf_delete_management_vrf(config_db):
    """Disable management vrf in config DB"""

    entry = config_db.get_entry('MGMT_VRF_CONFIG', "vrf_global")
    if not entry or entry['mgmtVrfEnabled'] == 'false' :
        click.echo("ManagementVRF is already Disabled.")
        return None
    config_db.mod_entry('MGMT_VRF_CONFIG', "vrf_global", {"mgmtVrfEnabled": "false"})
    mvrf_restart_services()

@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def snmpagentaddress(ctx):
    """SNMP agent listening IP address, port, vrf configuration"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {'db': config_db}

ip_family = {4: AF_INET, 6: AF_INET6}

@snmpagentaddress.command('add')
@click.argument('agentip', metavar='<SNMP AGENT LISTENING IP Address>', required=True)
@click.option('-p', '--port', help="SNMP AGENT LISTENING PORT")
@click.option('-v', '--vrf', help="VRF Name mgmt/DataVrfName/None")
@click.pass_context
def add_snmp_agent_address(ctx, agentip, port, vrf):
    """Add the SNMP agent listening IP:Port%Vrf configuration"""

    #Construct SNMP_AGENT_ADDRESS_CONFIG table key in the format ip|<port>|<vrf>
    if not clicommon.is_ipaddress(agentip):
        click.echo("Invalid IP address")
        return False
    config_db = ctx.obj['db']
    if not vrf:
        entry = config_db.get_entry('MGMT_VRF_CONFIG', "vrf_global")
        if entry and entry['mgmtVrfEnabled'] == 'true' :
            click.echo("ManagementVRF is Enabled. Provide vrf.")
            return False
    found = 0
    ip = ipaddress.ip_address(agentip)
    for intf in netifaces.interfaces():
        ipaddresses = netifaces.ifaddresses(intf)
        if ip_family[ip.version] in ipaddresses:
            for ipaddr in ipaddresses[ip_family[ip.version]]:
                if agentip == ipaddr['addr']:
                    found = 1
                    break;
        if found == 1:
            break;
    else:
        click.echo("IP addfress is not available")
        return

    key = agentip+'|'
    if port:
        key = key+port
    #snmpd does not start if we have two entries with same ip and port.
    key1 = "SNMP_AGENT_ADDRESS_CONFIG|" + key + '*'
    entry = config_db.get_keys(key1)
    if entry:
        ip_port = agentip + ":" + port
        click.echo("entry with {} already exists ".format(ip_port))
        return
    key = key+'|'
    if vrf:
        key = key+vrf
    config_db.set_entry('SNMP_AGENT_ADDRESS_CONFIG', key, {})

    #Restarting the SNMP service will regenerate snmpd.conf and rerun snmpd
    cmd="systemctl restart snmp"
    os.system (cmd)

@snmpagentaddress.command('del')
@click.argument('agentip', metavar='<SNMP AGENT LISTENING IP Address>', required=True)
@click.option('-p', '--port', help="SNMP AGENT LISTENING PORT")
@click.option('-v', '--vrf', help="VRF Name mgmt/DataVrfName/None")
@click.pass_context
def del_snmp_agent_address(ctx, agentip, port, vrf):
    """Delete the SNMP agent listening IP:Port%Vrf configuration"""

    key = agentip+'|'
    if port:
        key = key+port
    key = key+'|'
    if vrf:
        key = key+vrf
    config_db = ctx.obj['db']
    config_db.set_entry('SNMP_AGENT_ADDRESS_CONFIG', key, None)
    cmd="systemctl restart snmp"
    os.system (cmd)

@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def snmptrap(ctx):
    """SNMP Trap server configuration to send traps"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {'db': config_db}

@snmptrap.command('modify')
@click.argument('ver', metavar='<SNMP Version>', type=click.Choice(['1', '2', '3']), required=True)
@click.argument('serverip', metavar='<SNMP TRAP SERVER IP Address>', required=True)
@click.option('-p', '--port', help="SNMP Trap Server port, default 162", default="162")
@click.option('-v', '--vrf', help="VRF Name mgmt/DataVrfName/None", default="None")
@click.option('-c', '--comm', help="Community", default="public")
@click.pass_context
def modify_snmptrap_server(ctx, ver, serverip, port, vrf, comm):
    """Modify the SNMP Trap server configuration"""

    #SNMP_TRAP_CONFIG for each SNMP version
    config_db = ctx.obj['db']
    if ver == "1":
        #By default, v1TrapDest value in snmp.yml is "NotConfigured". Modify it.
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v1TrapDest", {"DestIp": serverip, "DestPort": port, "vrf": vrf, "Community": comm})
    elif ver == "2":
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v2TrapDest", {"DestIp": serverip, "DestPort": port, "vrf": vrf, "Community": comm})
    else:
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v3TrapDest", {"DestIp": serverip, "DestPort": port, "vrf": vrf, "Community": comm})

    cmd="systemctl restart snmp"
    os.system (cmd)

@snmptrap.command('del')
@click.argument('ver', metavar='<SNMP Version>', type=click.Choice(['1', '2', '3']), required=True)
@click.pass_context
def delete_snmptrap_server(ctx, ver):
    """Delete the SNMP Trap server configuration"""

    config_db = ctx.obj['db']
    if ver == "1":
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v1TrapDest", None)
    elif ver == "2":
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v2TrapDest", None)
    else:
        config_db.mod_entry('SNMP_TRAP_CONFIG', "v3TrapDest", None)
    cmd="systemctl restart snmp"
    os.system (cmd)

#
# 'bgp' group ('config bgp ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
def bgp():
    """BGP-related configuration tasks"""
    pass

#
# 'shutdown' subgroup ('config bgp shutdown ...')
#

@bgp.group(cls=clicommon.AbbreviationGroup)
def shutdown():
    """Shut down BGP session(s)"""
    pass

# 'all' subcommand
@shutdown.command()
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def all(verbose):
    """Shut down all BGP sessions
       In the case of Multi-Asic platform, we shut only the EBGP sessions with external neighbors.
    """
    log.log_info("'bgp shutdown all' executing...")
    namespaces = [DEFAULT_NAMESPACE]

    if multi_asic.is_multi_asic():
        ns_list = multi_asic.get_all_namespaces()
        namespaces = ns_list['front_ns']

    # Connect to CONFIG_DB in linux host (in case of single ASIC) or CONFIG_DB in all the
    # namespaces (in case of multi ASIC) and do the sepcified "action" on the BGP neighbor(s)
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()
        bgp_neighbor_ip_list = _get_all_neighbor_ipaddresses(config_db)
        for ipaddress in bgp_neighbor_ip_list:
            _change_bgp_session_status_by_addr(config_db, ipaddress, 'down', verbose)

# 'neighbor' subcommand
@shutdown.command()
@click.argument('ipaddr_or_hostname', metavar='<ipaddr_or_hostname>', required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def neighbor(ipaddr_or_hostname, verbose):
    """Shut down BGP session by neighbor IP address or hostname.
       User can specify either internal or external BGP neighbor to shutdown
    """
    log.log_info("'bgp shutdown neighbor {}' executing...".format(ipaddr_or_hostname))
    namespaces = [DEFAULT_NAMESPACE]
    found_neighbor = False

    if multi_asic.is_multi_asic():
        ns_list = multi_asic.get_all_namespaces()
        namespaces = ns_list['front_ns'] + ns_list['back_ns']

    # Connect to CONFIG_DB in linux host (in case of single ASIC) or CONFIG_DB in all the
    # namespaces (in case of multi ASIC) and do the sepcified "action" on the BGP neighbor(s)
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()
        if _change_bgp_session_status(config_db, ipaddr_or_hostname, 'down', verbose):
            found_neighbor = True

    if not found_neighbor:
        click.get_current_context().fail("Could not locate neighbor '{}'".format(ipaddr_or_hostname))

@bgp.group(cls=clicommon.AbbreviationGroup)
def startup():
    """Start up BGP session(s)"""
    pass

# 'all' subcommand
@startup.command()
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def all(verbose):
    """Start up all BGP sessions
       In the case of Multi-Asic platform, we startup only the EBGP sessions with external neighbors.
    """
    log.log_info("'bgp startup all' executing...")
    namespaces = [DEFAULT_NAMESPACE]

    if multi_asic.is_multi_asic():
        ns_list = multi_asic.get_all_namespaces()
        namespaces = ns_list['front_ns']

    # Connect to CONFIG_DB in linux host (in case of single ASIC) or CONFIG_DB in all the
    # namespaces (in case of multi ASIC) and do the sepcified "action" on the BGP neighbor(s)
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()
        bgp_neighbor_ip_list = _get_all_neighbor_ipaddresses(config_db)
        for ipaddress in bgp_neighbor_ip_list:
            _change_bgp_session_status_by_addr(config_db, ipaddress, 'up', verbose)

# 'neighbor' subcommand
@startup.command()
@click.argument('ipaddr_or_hostname', metavar='<ipaddr_or_hostname>', required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def neighbor(ipaddr_or_hostname, verbose):
    log.log_info("'bgp startup neighbor {}' executing...".format(ipaddr_or_hostname))
    """Start up BGP session by neighbor IP address or hostname.
       User can specify either internal or external BGP neighbor to startup
    """
    namespaces = [DEFAULT_NAMESPACE]
    found_neighbor = False

    if multi_asic.is_multi_asic():
        ns_list = multi_asic.get_all_namespaces()
        namespaces = ns_list['front_ns'] + ns_list['back_ns']

    # Connect to CONFIG_DB in linux host (in case of single ASIC) or CONFIG_DB in all the
    # namespaces (in case of multi ASIC) and do the sepcified "action" on the BGP neighbor(s)
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()
        if _change_bgp_session_status(config_db, ipaddr_or_hostname, 'up', verbose):
            found_neighbor = True

    if not found_neighbor:
        click.get_current_context().fail("Could not locate neighbor '{}'".format(ipaddr_or_hostname))

#
# 'remove' subgroup ('config bgp remove ...')
#

@bgp.group(cls=clicommon.AbbreviationGroup)
def remove():
    "Remove BGP neighbor configuration from the device"
    pass

@remove.command('neighbor')
@click.argument('neighbor_ip_or_hostname', metavar='<neighbor_ip_or_hostname>', required=True)
def remove_neighbor(neighbor_ip_or_hostname):
    """Deletes BGP neighbor configuration of given hostname or ip from devices
       User can specify either internal or external BGP neighbor to remove
    """
    namespaces = [DEFAULT_NAMESPACE]
    removed_neighbor = False

    if multi_asic.is_multi_asic():
        ns_list = multi_asic.get_all_namespaces()
        namespaces = ns_list['front_ns'] + ns_list['back_ns']

    # Connect to CONFIG_DB in linux host (in case of single ASIC) or CONFIG_DB in all the
    # namespaces (in case of multi ASIC) and do the sepcified "action" on the BGP neighbor(s)
    for namespace in namespaces:
        config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=namespace)
        config_db.connect()
        if _remove_bgp_neighbor_config(config_db, neighbor_ip_or_hostname):
            removed_neighbor = True

    if not removed_neighbor:
        click.get_current_context().fail("Could not locate neighbor '{}'".format(neighbor_ip_or_hostname))

#
# 'interface' group ('config interface ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
# TODO add "hidden=True if this is a single ASIC platform, once we have click 7.0 in all branches.
@click.option('-n', '--namespace', help='Namespace name',
             required=True if multi_asic.is_multi_asic() else False, type=click.Choice(multi_asic.get_namespace_list()))
@click.pass_context
def interface(ctx, namespace):
    """Interface-related configuration tasks"""
    # Set namespace to default_namespace if it is None.
    if namespace is None:
        namespace = DEFAULT_NAMESPACE
    config_db = ConfigDBConnector(use_unix_socket_path=True, namespace=str(namespace))
    config_db.connect()
    ctx.obj = {'config_db': config_db, 'namespace': str(namespace)}
#
# 'startup' subcommand
#

@interface.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.pass_context
def startup(ctx, interface_name):
    """Start up interface"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    intf_fs = parse_interface_in_filter(interface_name)
    if len(intf_fs) > 1 and multi_asic.is_multi_asic():
         ctx.fail("Interface range not supported in multi-asic platforms !!")

    if len(intf_fs) == 1 and interface_name_is_valid(config_db, interface_name) is False:
         ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    log.log_info("'interface startup {}' executing...".format(interface_name))
    port_dict = config_db.get_table('PORT')
    for port_name in port_dict:
        if port_name in intf_fs:
            config_db.mod_entry("PORT", port_name, {"admin_status": "up"})

    portchannel_list = config_db.get_table("PORTCHANNEL")
    for po_name in portchannel_list:
        if po_name in intf_fs:
            config_db.mod_entry("PORTCHANNEL", po_name, {"admin_status": "up"})

    subport_list = config_db.get_table("VLAN_SUB_INTERFACE")
    for sp_name in subport_list:
        if sp_name in intf_fs:
            config_db.mod_entry("VLAN_SUB_INTERFACE", sp_name, {"admin_status": "up"})

#
# 'shutdown' subcommand
#

@interface.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.pass_context
def shutdown(ctx, interface_name):
    """Shut down interface"""
    log.log_info("'interface shutdown {}' executing...".format(interface_name))
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    intf_fs = parse_interface_in_filter(interface_name)
    if len(intf_fs) > 1 and multi_asic.is_multi_asic():
         ctx.fail("Interface range not supported in multi-asic platforms !!")

    if len(intf_fs) == 1 and interface_name_is_valid(config_db, interface_name) is False:
        ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    port_dict = config_db.get_table('PORT')
    for port_name in port_dict:
        if port_name in intf_fs:
            config_db.mod_entry("PORT", port_name, {"admin_status": "down"})

    portchannel_list = config_db.get_table("PORTCHANNEL")
    for po_name in portchannel_list:
        if po_name in intf_fs:
            config_db.mod_entry("PORTCHANNEL", po_name, {"admin_status": "down"})

    subport_list = config_db.get_table("VLAN_SUB_INTERFACE")
    for sp_name in subport_list:
        if sp_name in intf_fs:
            config_db.mod_entry("VLAN_SUB_INTERFACE", sp_name, {"admin_status": "down"})

#
# 'speed' subcommand
#

@interface.command()
@click.pass_context
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('interface_speed', metavar='<interface_speed>', required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def speed(ctx, interface_name, interface_speed, verbose):
    """Set interface speed"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    log.log_info("'interface speed {} {}' executing...".format(interface_name, interface_speed))

    if ctx.obj['namespace'] is DEFAULT_NAMESPACE:
        command = "portconfig -p {} -s {}".format(interface_name, interface_speed)
    else:
        command = "portconfig -p {} -s {} -n {}".format(interface_name, interface_speed, ctx.obj['namespace'])

    if verbose:
        command += " -vv"
    clicommon.run_command(command, display_cmd=verbose)

#
# 'breakout' subcommand
#

@interface.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('mode', required=True, type=click.STRING, autocompletion=_get_breakout_options)
@click.option('-f', '--force-remove-dependencies', is_flag=True,  help='Clear all dependencies internally first.')
@click.option('-l', '--load-predefined-config', is_flag=True,  help='load predefied user configuration (alias, lanes, speed etc) first.')
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false, expose_value=False, prompt='Do you want to Breakout the port, continue?')
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
@click.pass_context
def breakout(ctx, interface_name, mode, verbose, force_remove_dependencies, load_predefined_config):
    """ Set interface breakout mode """
    breakout_cfg_file = device_info.get_path_to_port_config_file()

    if not os.path.isfile(breakout_cfg_file) or not breakout_cfg_file.endswith('.json'):
        click.secho("[ERROR] Breakout feature is not available without platform.json file", fg='red')
        raise click.Abort()

    # Get the config_db connector
    config_db = ctx.obj['config_db']

    target_brkout_mode = mode

    # Get current breakout mode
    cur_brkout_dict = config_db.get_table('BREAKOUT_CFG')
    if len(cur_brkout_dict) == 0:
        click.secho("[ERROR] BREAKOUT_CFG table is NOT present in CONFIG DB", fg='red')
        raise click.Abort()

    if interface_name not in cur_brkout_dict.keys():
        click.secho("[ERROR] {} interface is NOT present in BREAKOUT_CFG table of CONFIG DB".format(interface_name), fg='red')
        raise click.Abort()

    cur_brkout_mode = cur_brkout_dict[interface_name]["brkout_mode"]

    # Validate Interface and Breakout mode
    if not _validate_interface_mode(ctx, breakout_cfg_file, interface_name, mode, cur_brkout_mode):
        raise click.Abort()

    """ Interface Deletion Logic """
    # Get list of interfaces to be deleted
    del_ports = get_child_ports(interface_name, cur_brkout_mode, breakout_cfg_file)
    del_intf_dict = {intf: del_ports[intf]["speed"] for intf in del_ports}

    if del_intf_dict:
        """ shut down all the interface before deletion """
        ret = shutdown_interfaces(ctx, del_intf_dict)
        if not ret:
            raise click.Abort()
        click.echo("\nPorts to be deleted : \n {}".format(json.dumps(del_intf_dict, indent=4)))

    else:
        click.secho("[ERROR] del_intf_dict is None! No interfaces are there to be deleted", fg='red')
        raise click.Abort()

    """ Interface Addition Logic """
    # Get list of interfaces to be added
    add_ports = get_child_ports(interface_name, target_brkout_mode, breakout_cfg_file)
    add_intf_dict = {intf: add_ports[intf]["speed"] for intf in add_ports}

    if add_intf_dict:
        click.echo("Ports to be added : \n {}".format(json.dumps(add_intf_dict, indent=4)))
    else:
        click.secho("[ERROR] port_dict is None!", fg='red')
        raise click.Abort()

    """ Special Case: Dont delete those ports  where the current mode and speed of the parent port
                      remains unchanged to limit the traffic impact """

    click.secho("\nAfter running Logic to limit the impact", fg="cyan", underline=True)
    matched_items = [intf for intf in del_intf_dict if intf in add_intf_dict and del_intf_dict[intf] == add_intf_dict[intf]]

    # Remove the interface which remains unchanged from both del_intf_dict and add_intf_dict
    for item in matched_items:
        del_intf_dict.pop(item)
        add_intf_dict.pop(item)

    click.secho("\nFinal list of ports to be deleted : \n {} \nFinal list of ports to be added :  \n {}".format(json.dumps(del_intf_dict, indent=4), json.dumps(add_intf_dict, indent=4), fg='green', blink=True))
    if not add_intf_dict:
        click.secho("[ERROR] add_intf_dict is None or empty! No interfaces are there to be added", fg='red')
        raise click.Abort()

    port_dict = {}
    for intf in add_intf_dict:
        if intf in add_ports:
            port_dict[intf] = add_ports[intf]

    # writing JSON object
    with open('new_port_config.json', 'w') as f:
        json.dump(port_dict, f, indent=4)

    # Start Interation with Dy Port BreakOut Config Mgmt
    try:
        """ Load config for the commands which are capable of change in config DB """
        cm = load_ConfigMgmt(verbose)

        """ Delete all ports if forced else print dependencies using ConfigMgmt API """
        final_delPorts = [intf for intf in del_intf_dict]
        """ Warn user if tables without yang models exist and have final_delPorts """
        breakout_warnUser_extraTables(cm, final_delPorts, confirm=True)

        # Create a dictionary containing all the added ports with its capabilities like alias, lanes, speed etc.
        portJson = dict(); portJson['PORT'] = port_dict

        # breakout_Ports will abort operation on failure, So no need to check return
        breakout_Ports(cm, delPorts=final_delPorts, portJson=portJson, force=force_remove_dependencies,
                       loadDefConfig=load_predefined_config, verbose=verbose)

        # Set Current Breakout mode in config DB
        brkout_cfg_keys = config_db.get_keys('BREAKOUT_CFG')
        if interface_name not in  brkout_cfg_keys:
            click.secho("[ERROR] {} is not present in 'BREAKOUT_CFG' Table!".format(interface_name), fg='red')
            raise click.Abort()
        config_db.set_entry("BREAKOUT_CFG", interface_name, {'brkout_mode': target_brkout_mode})
        click.secho("Breakout process got successfully completed."
                    .format(interface_name), fg="cyan", underline=True)
        click.echo("Please note loaded setting will be lost after system reboot. To preserve setting, run `config save`.")

    except Exception as e:
        click.secho("Failed to break out Port. Error: {}".format(str(e)), fg='magenta')

        sys.exit(0)

def _get_all_mgmtinterface_keys():
    """Returns list of strings containing mgmt interface keys
    """
    config_db = ConfigDBConnector()
    config_db.connect()
    return list(config_db.get_table('MGMT_INTERFACE').keys())

def mgmt_ip_restart_services():
    """Restart the required services when mgmt inteface IP address is changed"""
    """
    Whenever the eth0 IP address is changed, restart the "interfaces-config"
    service which regenerates the /etc/network/interfaces file and restarts
    the networking service to make the new/null IP address effective for eth0.
    "ntp-config" service should also be restarted based on the new
    eth0 IP address since the ntp.conf (generated from ntp.conf.j2) is
    made to listen on that particular eth0 IP address or reset it back.
    """
    cmd="systemctl restart interfaces-config"
    os.system (cmd)
    cmd="systemctl restart ntp-config"
    os.system (cmd)

#
# 'mtu' subcommand
#

@interface.command()
@click.pass_context
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('interface_mtu', metavar='<interface_mtu>', required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def mtu(ctx, interface_name, interface_mtu, verbose):
    """Set interface mtu"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']
    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    portchannel_member_table = config_db.get_table('PORTCHANNEL_MEMBER')
    if interface_is_in_portchannel(portchannel_member_table, interface_name):
        ctx.fail("'interface_name' is in portchannel!")

    if ctx.obj['namespace'] is DEFAULT_NAMESPACE:
        command = "portconfig -p {} -m {}".format(interface_name, interface_mtu)
    else:
        command = "portconfig -p {} -m {} -n {}".format(interface_name, interface_mtu, ctx.obj['namespace'])

    if verbose:
        command += " -vv"
    clicommon.run_command(command, display_cmd=verbose)

@interface.command()
@click.pass_context
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('interface_fec', metavar='<interface_fec>', required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def fec(ctx, interface_name, interface_fec, verbose):
    """Set interface fec"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if interface_fec not in ["rs", "fc", "none"]:
        ctx.fail("'fec not in ['rs', 'fc', 'none']!")
    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    if ctx.obj['namespace'] is DEFAULT_NAMESPACE:
        command = "portconfig -p {} -f {}".format(interface_name, interface_fec)
    else:
        command = "portconfig -p {} -f {} -n {}".format(interface_name, interface_fec, ctx.obj['namespace'])

    if verbose:
        command += " -vv"
    clicommon.run_command(command, display_cmd=verbose)

#
# 'ip' subgroup ('config interface ip ...')
#

@interface.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def ip(ctx):
    """Add or remove IP address"""
    pass

#
# 'add' subcommand
#

@ip.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument("ip_addr", metavar="<ip_addr>", required=True)
@click.argument('gw', metavar='<default gateway IP address>', required=False)
@click.pass_context
def add(ctx, interface_name, ip_addr, gw):
    """Add an IP address towards the interface"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    # Add a validation to check this interface is not a member in vlan before 
    # changing it to a router port 
    vlan_member_table = config_db.get_table('VLAN_MEMBER')
    if (interface_is_in_vlan(vlan_member_table, interface_name)):
            click.echo("Interface {} is a member of vlan\nAborting!".format(interface_name))
            return

    try:
        net = ipaddress.ip_network(ip_addr, strict=False)
        if '/' not in ip_addr:
            ip_addr = str(net)

        if interface_name == 'eth0':

            # Configuring more than 1 IPv4 or more than 1 IPv6 address fails.
            # Allow only one IPv4 and only one IPv6 address to be configured for IPv6.
            # If a row already exist, overwrite it (by doing delete and add).
            mgmtintf_key_list = _get_all_mgmtinterface_keys()

            for key in mgmtintf_key_list:
                # For loop runs for max 2 rows, once for IPv4 and once for IPv6.
                # No need to capture the exception since the ip_addr is already validated earlier
                ip_input = ipaddress.ip_interface(ip_addr)
                current_ip = ipaddress.ip_interface(key[1])
                if (ip_input.version == current_ip.version):
                    # If user has configured IPv4/v6 address and the already available row is also IPv4/v6, delete it here.
                    config_db.set_entry("MGMT_INTERFACE", ("eth0", key[1]), None)

            # Set the new row with new value
            if not gw:
                config_db.set_entry("MGMT_INTERFACE", (interface_name, ip_addr), {"NULL": "NULL"})
            else:
                config_db.set_entry("MGMT_INTERFACE", (interface_name, ip_addr), {"gwaddr": gw})
            mgmt_ip_restart_services()

            return

        table_name = get_interface_table_name(interface_name)
        if table_name == "":
            ctx.fail("'interface_name' is not valid. Valid names [Ethernet/PortChannel/Vlan/Loopback]")
        interface_entry = config_db.get_entry(table_name, interface_name)
        if len(interface_entry) == 0:
            if table_name == "VLAN_SUB_INTERFACE":
                config_db.set_entry(table_name, interface_name, {"admin_status": "up"})
            else:
                config_db.set_entry(table_name, interface_name, {"NULL": "NULL"})
        config_db.set_entry(table_name, (interface_name, ip_addr), {"NULL": "NULL"})
    except ValueError:
        ctx.fail("'ip_addr' is not valid.")

#
# 'del' subcommand
#

@ip.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument("ip_addr", metavar="<ip_addr>", required=True)
@click.pass_context
def remove(ctx, interface_name, ip_addr):
    """Remove an IP address from the interface"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    try:
        net = ipaddress.ip_network(ip_addr, strict=False)
        if '/' not in ip_addr:
            ip_addr = str(net)

        if interface_name == 'eth0':
            config_db.set_entry("MGMT_INTERFACE", (interface_name, ip_addr), None)
            mgmt_ip_restart_services()
            return

        table_name = get_interface_table_name(interface_name)
        if table_name == "":
            ctx.fail("'interface_name' is not valid. Valid names [Ethernet/PortChannel/Vlan/Loopback]")
        config_db.set_entry(table_name, (interface_name, ip_addr), None)
        interface_dependent = interface_ipaddr_dependent_on_interface(config_db, interface_name)
        if len(interface_dependent) == 0 and is_interface_bind_to_vrf(config_db, interface_name) is False:
            config_db.set_entry(table_name, interface_name, None)

        if multi_asic.is_multi_asic():
            command = "sudo ip netns exec {} ip neigh flush dev {} {}".format(ctx.obj['namespace'], interface_name, ip_addr)
        else:
            command = "ip neigh flush dev {} {}".format(interface_name, ip_addr)
        clicommon.run_command(command)
    except ValueError:
        ctx.fail("'ip_addr' is not valid.")


#
# buffer commands and utilities
#
def pgmaps_check_legality(ctx, interface_name, input_pg, is_new_pg):
    """
    Tool function to check whether input_pg is legal.
    Three checking performed:
    1. Whether the input_pg is legal: pgs are in range [0-7]
    2. Whether the input_pg overlaps an existing pg in the port
    """
    config_db = ctx.obj["config_db"]

    try:
        lower = int(input_pg[0])
        upper = int(input_pg[-1])

        if upper < lower or lower < 0 or upper > 7:
            ctx.fail("PG {} is not valid.".format(input_pg))
    except Exception:
        ctx.fail("PG {} is not valid.".format(input_pg))

    # Check overlapping.
    # To configure a new PG which is overlapping an existing one is not allowed
    # For example, to add '5-6' while '3-5' existing is illegal
    existing_pgs = config_db.get_table("BUFFER_PG")
    if not is_new_pg:
        if not (interface_name, input_pg) in existing_pgs.keys():
            ctx.fail("PG {} doesn't exist".format(input_pg))
        return

    for k, v in existing_pgs.items():
        port, existing_pg = k
        if port == interface_name:
            existing_lower = int(existing_pg[0])
            existing_upper = int(existing_pg[-1])
            if existing_upper < lower or existing_lower > upper:
                # new and existing pgs disjoint, legal
                pass
            else:
                ctx.fail("PG {} overlaps with existing PG {}".format(input_pg, existing_pg))


def update_pg(ctx, interface_name, pg_map, override_profile, add = True):
    config_db = ctx.obj["config_db"]

    # Check whether port is legal
    ports = config_db.get_entry("PORT", interface_name)
    if not ports:
        ctx.fail("Port {} doesn't exist".format(interface_name))

    # Check whether pg_map is legal
    # Check whether there is other lossless profiles configured on the interface
    pgmaps_check_legality(ctx, interface_name, pg_map, add)

    # All checking passed
    if override_profile:
        profile_dict = config_db.get_entry("BUFFER_PROFILE", override_profile)
        if not profile_dict:
            ctx.fail("Profile {} doesn't exist".format(override_profile))
        if not 'xoff' in profile_dict.keys() and 'size' in profile_dict.keys():
            ctx.fail("Profile {} doesn't exist or isn't a lossless profile".format(override_profile))
        profile_full_name = "[BUFFER_PROFILE|{}]".format(override_profile)
        config_db.set_entry("BUFFER_PG", (interface_name, pg_map), {"profile": profile_full_name})
    else:
        config_db.set_entry("BUFFER_PG", (interface_name, pg_map), {"profile": "NULL"})
    adjust_pfc_enable(ctx, interface_name, pg_map, True)


def remove_pg_on_port(ctx, interface_name, pg_map):
    config_db = ctx.obj["config_db"]

    # Check whether port is legal
    ports = config_db.get_entry("PORT", interface_name)
    if not ports:
        ctx.fail("Port {} doesn't exist".format(interface_name))

    # Remvoe all dynamic lossless PGs on the port
    existing_pgs = config_db.get_table("BUFFER_PG")
    removed = False
    for k, v in existing_pgs.items():
        port, existing_pg = k
        if port == interface_name and (not pg_map or pg_map == existing_pg):
            need_to_remove = False
            referenced_profile = v.get('profile')
            if referenced_profile and referenced_profile == '[BUFFER_PROFILE|ingress_lossy_profile]':
                if pg_map:
                    ctx.fail("Lossy PG {} can't be removed".format(pg_map))
                else:
                    continue
            config_db.set_entry("BUFFER_PG", (interface_name, existing_pg), None)
            adjust_pfc_enable(ctx, interface_name, pg_map, False)
            removed = True
    if not removed:
        if pg_map:
            ctx.fail("No specified PG {} found on port {}".format(pg_map, interface_name))
        else:
            ctx.fail("No lossless PG found on port {}".format(interface_name))


def adjust_pfc_enable(ctx, interface_name, pg_map, add):
    config_db = ctx.obj["config_db"]

    # Fetch the original pfc_enable
    qosmap = config_db.get_entry("PORT_QOS_MAP", interface_name)
    pfc_enable = qosmap.get("pfc_enable")

    pfc_set = set()
    if pfc_enable:
        for priority in pfc_enable.split(","):
            pfc_set.add(int(priority))

    if pg_map:
        lower_bound = int(pg_map[0])
        upper_bound = int(pg_map[-1])

        for priority in range(lower_bound, upper_bound + 1):
            if add:
                pfc_set.add(priority)
            elif priority in pfc_set:
                pfc_set.remove(priority)

        empty_set = set()
        pfc_enable = ""
        if not pfc_set.issubset(empty_set):
            for priority in pfc_set:
                pfc_enable += str(priority) + ","
    elif not add:
        # Remove all
        pfc_enable = ""
    else:
        ctx.fail("Try to add empty priorities")

    qosmap["pfc_enable"] = pfc_enable[:-1]
    config_db.set_entry("PORT_QOS_MAP", interface_name, qosmap)


#
# 'buffer' subgroup ('config interface buffer ...')
#
@interface.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def buffer(ctx):
    """Set or clear buffer configuration"""
    config_db = ctx.obj["config_db"]
    if not is_dynamic_buffer_enabled(config_db):
        ctx.fail("This command can only be executed on a system with dynamic buffer enabled")


#
# 'priority_group' subgroup ('config interface buffer priority_group ...')
#
@buffer.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def priority_group(ctx):
    """Set or clear buffer configuration"""
    pass


#
# 'lossless' subgroup ('config interface buffer priority_group lossless ...')
#
@priority_group.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def lossless(ctx):
    """Set or clear lossless PGs"""
    pass


#
# 'add' subcommand
#
@lossless.command('add')
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('pg_map', metavar='<pg_map>', required=True)
@click.argument('override_profile', metavar='<override_profile>', required=False)
@click.pass_context
def add_pg(ctx, interface_name, pg_map, override_profile):
    """Set lossless PGs for the interface"""
    update_pg(ctx, interface_name, pg_map, override_profile)


#
# 'set' subcommand
#
@lossless.command('set')
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('pg_map', metavar='<pg_map>', required=True)
@click.argument('override_profile', metavar='<override_profile>', required=False)
@click.pass_context
def set_pg(ctx, interface_name, pg_map, override_profile):
    """Set lossless PGs for the interface"""
    update_pg(ctx, interface_name, pg_map, override_profile, False)


#
# 'remove' subcommand
#
@lossless.command('remove')
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('pg_map', metavar='<pg_map', required=False)
@click.pass_context
def remove_pg(ctx, interface_name, pg_map):
    """Clear lossless PGs for the interface"""
    remove_pg_on_port(ctx, interface_name, pg_map)


#
# 'cable_length' subcommand
#

@interface.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('length', metavar='<length>', required=True)
@click.pass_context
def cable_length(ctx, interface_name, length):
    """Set lossless PGs for the interface"""
    config_db = ctx.obj["config_db"]

    if not is_dynamic_buffer_enabled(config_db):
        ctx.fail("This command can only be supported on a system with dynamic buffer enabled")

    # Check whether port is legal
    ports = config_db.get_entry("PORT", interface_name)
    if not ports:
        ctx.fail("Port {} doesn't exist".format(interface_name))

    try:
        assert "m" == length[-1]
    except Exception:
        ctx.fail("Invalid cable length. Should be in format <num>m, like 300m".format(cable_length))

    keys = config_db.get_keys("CABLE_LENGTH")

    cable_length_set = {}
    cable_length_set[interface_name] = length
    config_db.mod_entry("CABLE_LENGTH", keys[0], cable_length_set)

#
# 'transceiver' subgroup ('config interface transceiver ...')
#

@interface.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def transceiver(ctx):
    """SFP transceiver configuration"""
    pass

#
# 'lpmode' subcommand ('config interface transceiver lpmode ...')
#

@transceiver.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('state', metavar='(enable|disable)', type=click.Choice(['enable', 'disable']))
@click.pass_context
def lpmode(ctx, interface_name, state):
    """Enable/disable low-power mode for SFP transceiver module"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    if interface_name_is_valid(config_db, interface_name) is False:
        ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    cmd = "sudo sfputil lpmode {} {}".format("on" if state == "enable" else "off", interface_name)
    clicommon.run_command(cmd)

#
# 'reset' subcommand ('config interface reset ...')
#

@transceiver.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.pass_context
def reset(ctx, interface_name):
    """Reset SFP transceiver module"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    if interface_name_is_valid(config_db, interface_name) is False:
        ctx.fail("Interface name is invalid. Please enter a valid interface name!!")

    cmd = "sudo sfputil reset {}".format(interface_name)
    clicommon.run_command(cmd)

#
# 'vrf' subgroup ('config interface vrf ...')
#


@interface.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def vrf(ctx):
    """Bind or unbind VRF"""
    pass

#
# 'bind' subcommand
#
@vrf.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('vrf_name', metavar='<vrf_name>', required=True)
@click.pass_context
def bind(ctx, interface_name, vrf_name):
    """Bind the interface to VRF"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    table_name = get_interface_table_name(interface_name)
    if table_name == "":
        ctx.fail("'interface_name' is not valid. Valid names [Ethernet/PortChannel/Vlan/Loopback]")
    if is_interface_bind_to_vrf(config_db, interface_name) is True and \
        config_db.get_entry(table_name, interface_name).get('vrf_name') == vrf_name:
        return
    # Clean ip addresses if interface configured
    interface_dependent = interface_ipaddr_dependent_on_interface(config_db, interface_name)
    for interface_del in interface_dependent:
        config_db.set_entry(table_name, interface_del, None)
    config_db.set_entry(table_name, interface_name, None)
    # When config_db del entry and then add entry with same key, the DEL will lost.
    if ctx.obj['namespace'] is DEFAULT_NAMESPACE:
        state_db = SonicV2Connector(use_unix_socket_path=True)
    else:
        state_db = SonicV2Connector(use_unix_socket_path=True, namespace=ctx.obj['namespace'])
    state_db.connect(state_db.STATE_DB, False)
    _hash = '{}{}'.format('INTERFACE_TABLE|', interface_name)
    while state_db.exists(state_db.STATE_DB, _hash):
        time.sleep(0.01)
    state_db.close(state_db.STATE_DB)
    config_db.set_entry(table_name, interface_name, {"vrf_name": vrf_name})

#
# 'unbind' subcommand
#

@vrf.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.pass_context
def unbind(ctx, interface_name):
    """Unbind the interface to VRF"""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("interface is None!")

    table_name = get_interface_table_name(interface_name)
    if table_name == "":
        ctx.fail("'interface_name' is not valid. Valid names [Ethernet/PortChannel/Vlan/Loopback]")
    if is_interface_bind_to_vrf(config_db, interface_name) is False:
        return
    interface_dependent = interface_ipaddr_dependent_on_interface(config_db, interface_name)
    for interface_del in interface_dependent:
        config_db.set_entry(table_name, interface_del, None)
    config_db.set_entry(table_name, interface_name, None)


#
# 'vrf' group ('config vrf ...')
#

@config.group(cls=clicommon.AbbreviationGroup, name='vrf')
@click.pass_context
def vrf(ctx):
    """VRF-related configuration tasks"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {}
    ctx.obj['config_db'] = config_db

@vrf.command('add')
@click.argument('vrf_name', metavar='<vrf_name>', required=True)
@click.pass_context
def add_vrf(ctx, vrf_name):
    """Add vrf"""
    config_db = ctx.obj['config_db']
    if not vrf_name.startswith("Vrf") and not (vrf_name == 'mgmt') and not (vrf_name == 'management'):
        ctx.fail("'vrf_name' is not start with Vrf, mgmt or management!")
    if len(vrf_name) > 15:
        ctx.fail("'vrf_name' is too long!")
    if (vrf_name == 'mgmt' or vrf_name == 'management'):
        vrf_add_management_vrf(config_db)
    else:
        config_db.set_entry('VRF', vrf_name, {"NULL": "NULL"})

@vrf.command('del')
@click.argument('vrf_name', metavar='<vrf_name>', required=True)
@click.pass_context
def del_vrf(ctx, vrf_name):
    """Del vrf"""
    config_db = ctx.obj['config_db']
    if not vrf_name.startswith("Vrf") and not (vrf_name == 'mgmt') and not (vrf_name == 'management'):
        ctx.fail("'vrf_name' is not start with Vrf, mgmt or management!")
    if len(vrf_name) > 15:
        ctx.fail("'vrf_name' is too long!")
    if (vrf_name == 'mgmt' or vrf_name == 'management'):
        vrf_delete_management_vrf(config_db)
    else:
        del_interface_bind_to_vrf(config_db, vrf_name)
        config_db.set_entry('VRF', vrf_name, None)


@vrf.command('add_vrf_vni_map')
@click.argument('vrfname', metavar='<vrf-name>', required=True, type=str)
@click.argument('vni', metavar='<vni>', required=True)
@click.pass_context
def add_vrf_vni_map(ctx, vrfname, vni):
    config_db = ctx.obj['config_db']
    found = 0
    if vrfname not in config_db.get_table('VRF').keys():
        ctx.fail("vrf {} doesnt exists".format(vrfname))
    if not vni.isdigit():
        ctx.fail("Invalid VNI {}. Only valid VNI is accepted".format(vni))

    if clicommon.vni_id_is_valid(int(vni)) is False:
        ctx.fail("Invalid VNI {}. Valid range [1 to 16777215].".format(vni))

    vxlan_table = config_db.get_table('VXLAN_TUNNEL_MAP')
    vxlan_keys = vxlan_table.keys()
    if vxlan_keys is not None:
        for key in vxlan_keys:
            if (vxlan_table[key]['vni'] == vni):
                found = 1
                break

    if (found == 0):
        ctx.fail("VLAN VNI not mapped. Please create VLAN VNI map entry first")

    found = 0
    vrf_table = config_db.get_table('VRF')
    vrf_keys = vrf_table.keys()
    if vrf_keys is not None:
        for vrf_key in vrf_keys:
            if ('vni' in vrf_table[vrf_key] and vrf_table[vrf_key]['vni'] == vni):
                found = 1
                break

    if (found == 1):
        ctx.fail("VNI already mapped to vrf {}".format(vrf_key))

    config_db.mod_entry('VRF', vrfname, {"vni": vni})

@vrf.command('del_vrf_vni_map')
@click.argument('vrfname', metavar='<vrf-name>', required=True, type=str)
@click.pass_context
def del_vrf_vni_map(ctx, vrfname):
    config_db = ctx.obj['config_db']
    if vrfname not in config_db.get_table('VRF').keys():
        ctx.fail("vrf {} doesnt exists".format(vrfname))

    config_db.mod_entry('VRF', vrfname, {"vni": 0})

#
# 'route' group ('config route ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def route(ctx):
    """route-related configuration tasks"""
    pass

@route.command('add', context_settings={"ignore_unknown_options":True})
@click.argument('command_str', metavar='prefix [vrf <vrf_name>] <A.B.C.D/M> nexthop <[vrf <vrf_name>] <A.B.C.D>>|<dev <dev_name>>', nargs=-1, type=click.Path())
@click.pass_context
def add_route(ctx, command_str):
    """Add route command"""
    if len(command_str) < 4 or len(command_str) > 9:
        ctx.fail("argument is not in pattern prefix [vrf <vrf_name>] <A.B.C.D/M> nexthop <[vrf <vrf_name>] <A.B.C.D>>|<dev <dev_name>>!")
    if "prefix" not in command_str:
        ctx.fail("argument is incomplete, prefix not found!")
    if "nexthop" not in command_str:
        ctx.fail("argument is incomplete, nexthop not found!")
    for i in range(0, len(command_str)):
        if "nexthop" == command_str[i]:
            prefix_str = command_str[:i]
            nexthop_str = command_str[i:]
    vrf_name = ""
    cmd = 'sudo vtysh -c "configure terminal" -c "ip route'
    if prefix_str:
        if len(prefix_str) == 2:
            prefix_mask = prefix_str[1]
            cmd += ' {}'.format(prefix_mask)
        elif len(prefix_str) == 4:
            vrf_name = prefix_str[2]
            prefix_mask = prefix_str[3]
            cmd += ' {}'.format(prefix_mask)
        else:
            ctx.fail("prefix is not in pattern!")
    if nexthop_str:
        if len(nexthop_str) == 2:
            ip = nexthop_str[1]
            if vrf_name == "":
                cmd += ' {}'.format(ip)
            else:
                cmd += ' {} vrf {}'.format(ip, vrf_name)
        elif len(nexthop_str) == 3:
            dev_name = nexthop_str[2]
            if vrf_name == "":
                cmd += ' {}'.format(dev_name)
            else:
                cmd += ' {} vrf {}'.format(dev_name, vrf_name)
        elif len(nexthop_str) == 4:
            vrf_name_dst = nexthop_str[2]
            ip = nexthop_str[3]
            if vrf_name == "":
                cmd += ' {} nexthop-vrf {}'.format(ip, vrf_name_dst)
            else:
                cmd += ' {} vrf {} nexthop-vrf {}'.format(ip, vrf_name, vrf_name_dst)
        else:
            ctx.fail("nexthop is not in pattern!")
    cmd += '"'
    clicommon.run_command(cmd)

@route.command('del', context_settings={"ignore_unknown_options":True})
@click.argument('command_str', metavar='prefix [vrf <vrf_name>] <A.B.C.D/M> nexthop <[vrf <vrf_name>] <A.B.C.D>>|<dev <dev_name>>', nargs=-1, type=click.Path())
@click.pass_context
def del_route(ctx, command_str):
    """Del route command"""
    if len(command_str) < 4 or len(command_str) > 9:
        ctx.fail("argument is not in pattern prefix [vrf <vrf_name>] <A.B.C.D/M> nexthop <[vrf <vrf_name>] <A.B.C.D>>|<dev <dev_name>>!")
    if "prefix" not in command_str:
        ctx.fail("argument is incomplete, prefix not found!")
    if "nexthop" not in command_str:
        ctx.fail("argument is incomplete, nexthop not found!")
    for i in range(0, len(command_str)):
        if "nexthop" == command_str[i]:
            prefix_str = command_str[:i]
            nexthop_str = command_str[i:]
    vrf_name = ""
    cmd = 'sudo vtysh -c "configure terminal" -c "no ip route'
    if prefix_str:
        if len(prefix_str) == 2:
            prefix_mask = prefix_str[1]
            cmd += ' {}'.format(prefix_mask)
        elif len(prefix_str) == 4:
            vrf_name = prefix_str[2]
            prefix_mask = prefix_str[3]
            cmd += ' {}'.format(prefix_mask)
        else:
            ctx.fail("prefix is not in pattern!")
    if nexthop_str:
        if len(nexthop_str) == 2:
            ip = nexthop_str[1]
            if vrf_name == "":
                cmd += ' {}'.format(ip)
            else:
                cmd += ' {} vrf {}'.format(ip, vrf_name)
        elif len(nexthop_str) == 3:
            dev_name = nexthop_str[2]
            if vrf_name == "":
                cmd += ' {}'.format(dev_name)
            else:
                cmd += ' {} vrf {}'.format(dev_name, vrf_name)
        elif len(nexthop_str) == 4:
            vrf_name_dst = nexthop_str[2]
            ip = nexthop_str[3]
            if vrf_name == "":
                cmd += ' {} nexthop-vrf {}'.format(ip, vrf_name_dst)
            else:
                cmd += ' {} vrf {} nexthop-vrf {}'.format(ip, vrf_name, vrf_name_dst)
        else:
            ctx.fail("nexthop is not in pattern!")
    cmd += '"'
    clicommon.run_command(cmd)

#
# 'acl' group ('config acl ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
def acl():
    """ACL-related configuration tasks"""
    pass

#
# 'add' subgroup ('config acl add ...')
#

@acl.group(cls=clicommon.AbbreviationGroup)
def add():
    """
    Add ACL configuration.
    """
    pass


def get_acl_bound_ports():
    config_db = ConfigDBConnector()
    config_db.connect()

    ports = set()
    portchannel_members = set()

    portchannel_member_dict = config_db.get_table("PORTCHANNEL_MEMBER")
    for key in portchannel_member_dict:
        ports.add(key[0])
        portchannel_members.add(key[1])

    port_dict = config_db.get_table("PORT")
    for key in port_dict:
        if key not in portchannel_members:
            ports.add(key)

    return list(ports)


def expand_vlan_ports(port_name):
    """
    Expands a given VLAN interface into its member ports.

    If the provided interface is a VLAN, then this method will return its member ports.

    If the provided interface is not a VLAN, then this method will return a list with only
    the provided interface in it.
    """
    config_db = ConfigDBConnector()
    config_db.connect()

    if port_name not in config_db.get_keys("VLAN"):
        return [port_name]

    vlan_members = config_db.get_keys("VLAN_MEMBER")

    members = [member for vlan, member in vlan_members if port_name == vlan]

    if not members:
        raise ValueError("Cannot bind empty VLAN {}".format(port_name))

    return members


def parse_acl_table_info(table_name, table_type, description, ports, stage):
    table_info = {"type": table_type}

    if description:
        table_info["policy_desc"] = description
    else:
        table_info["policy_desc"] = table_name

    if not ports and ports != None:
        raise ValueError("Cannot bind empty list of ports")

    port_list = []
    valid_acl_ports = get_acl_bound_ports()
    if ports:
        for port in ports.split(","):
            port_list += expand_vlan_ports(port)
        port_list = set(port_list)
    else:
        port_list = valid_acl_ports

    for port in port_list:
        if port not in valid_acl_ports:
            raise ValueError("Cannot bind ACL to specified port {}".format(port))

    table_info["ports@"] = ",".join(port_list)

    table_info["stage"] = stage

    return table_info

#
# 'table' subcommand ('config acl add table ...')
#

@add.command()
@click.argument("table_name", metavar="<table_name>")
@click.argument("table_type", metavar="<table_type>")
@click.option("-d", "--description")
@click.option("-p", "--ports")
@click.option("-s", "--stage", type=click.Choice(["ingress", "egress"]), default="ingress")
@click.pass_context
def table(ctx, table_name, table_type, description, ports, stage):
    """
    Add ACL table
    """
    config_db = ConfigDBConnector()
    config_db.connect()

    try:
        table_info = parse_acl_table_info(table_name, table_type, description, ports, stage)
    except ValueError as e:
        ctx.fail("Failed to parse ACL table config: exception={}".format(e))

    config_db.set_entry("ACL_TABLE", table_name, table_info)

#
# 'remove' subgroup ('config acl remove ...')
#

@acl.group(cls=clicommon.AbbreviationGroup)
def remove():
    """
    Remove ACL configuration.
    """
    pass

#
# 'table' subcommand ('config acl remove table ...')
#

@remove.command()
@click.argument("table_name", metavar="<table_name>")
def table(table_name):
    """
    Remove ACL table
    """
    config_db = ConfigDBConnector()
    config_db.connect()
    config_db.set_entry("ACL_TABLE", table_name, None)


#
# 'acl update' group
#

@acl.group(cls=clicommon.AbbreviationGroup)
def update():
    """ACL-related configuration tasks"""
    pass


#
# 'full' subcommand
#

@update.command()
@click.argument('file_name', required=True)
def full(file_name):
    """Full update of ACL rules configuration."""
    log.log_info("'acl update full {}' executing...".format(file_name))
    command = "acl-loader update full {}".format(file_name)
    clicommon.run_command(command)


#
# 'incremental' subcommand
#

@update.command()
@click.argument('file_name', required=True)
def incremental(file_name):
    """Incremental update of ACL rule configuration."""
    log.log_info("'acl update incremental {}' executing...".format(file_name))
    command = "acl-loader update incremental {}".format(file_name)
    clicommon.run_command(command)


#
# 'dropcounters' group ('config dropcounters ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
def dropcounters():
    """Drop counter related configuration tasks"""
    pass


#
# 'install' subcommand ('config dropcounters install')
#
@dropcounters.command()
@click.argument("counter_name", type=str, required=True)
@click.argument("counter_type", type=str, required=True)
@click.argument("reasons",      type=str, required=True)
@click.option("-a", "--alias", type=str, help="Alias for this counter")
@click.option("-g", "--group", type=str, help="Group for this counter")
@click.option("-d", "--desc",  type=str, help="Description for this counter")
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def install(counter_name, alias, group, counter_type, desc, reasons, verbose):
    """Install a new drop counter"""
    command = "dropconfig -c install -n '{}' -t '{}' -r '{}'".format(counter_name, counter_type, reasons)
    if alias:
        command += " -a '{}'".format(alias)
    if group:
        command += " -g '{}'".format(group)
    if desc:
        command += " -d '{}'".format(desc)

    clicommon.run_command(command, display_cmd=verbose)


#
# 'delete' subcommand ('config dropcounters delete')
#
@dropcounters.command()
@click.argument("counter_name", type=str, required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def delete(counter_name, verbose):
    """Delete an existing drop counter"""
    command = "dropconfig -c uninstall -n {}".format(counter_name)
    clicommon.run_command(command, display_cmd=verbose)


#
# 'add_reasons' subcommand ('config dropcounters add_reasons')
#
@dropcounters.command('add-reasons')
@click.argument("counter_name", type=str, required=True)
@click.argument("reasons",      type=str, required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def add_reasons(counter_name, reasons, verbose):
    """Add reasons to an existing drop counter"""
    command = "dropconfig -c add -n {} -r {}".format(counter_name, reasons)
    clicommon.run_command(command, display_cmd=verbose)


#
# 'remove_reasons' subcommand ('config dropcounters remove_reasons')
#
@dropcounters.command('remove-reasons')
@click.argument("counter_name", type=str, required=True)
@click.argument("reasons",      type=str, required=True)
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def remove_reasons(counter_name, reasons, verbose):
    """Remove reasons from an existing drop counter"""
    command = "dropconfig -c remove -n {} -r {}".format(counter_name, reasons)
    clicommon.run_command(command, display_cmd=verbose)


#
# 'ecn' command ('config ecn ...')
#
@config.command()
@click.option('-profile', metavar='<profile_name>', type=str, required=True, help="Profile name")
@click.option('-rmax', metavar='<red threshold max>', type=int, help="Set red max threshold")
@click.option('-rmin', metavar='<red threshold min>', type=int, help="Set red min threshold")
@click.option('-ymax', metavar='<yellow threshold max>', type=int, help="Set yellow max threshold")
@click.option('-ymin', metavar='<yellow threshold min>', type=int, help="Set yellow min threshold")
@click.option('-gmax', metavar='<green threshold max>', type=int, help="Set green max threshold")
@click.option('-gmin', metavar='<green threshold min>', type=int, help="Set green min threshold")
@click.option('-rdrop', metavar='<red drop probability>', type=click.IntRange(0, 100), help="Set red drop probability")
@click.option('-ydrop', metavar='<yellow drop probability>', type=click.IntRange(0, 100), help="Set yellow drop probability")
@click.option('-gdrop', metavar='<green drop probability>', type=click.IntRange(0, 100), help="Set green drop probability")
@click.option('-v', '--verbose', is_flag=True, help="Enable verbose output")
def ecn(profile, rmax, rmin, ymax, ymin, gmax, gmin, rdrop, ydrop, gdrop, verbose):
    """ECN-related configuration tasks"""
    log.log_info("'ecn -profile {}' executing...".format(profile))
    command = "ecnconfig -p %s" % profile
    if rmax is not None: command += " -rmax %d" % rmax
    if rmin is not None: command += " -rmin %d" % rmin
    if ymax is not None: command += " -ymax %d" % ymax
    if ymin is not None: command += " -ymin %d" % ymin
    if gmax is not None: command += " -gmax %d" % gmax
    if gmin is not None: command += " -gmin %d" % gmin
    if rdrop is not None: command += " -rdrop %d" % rdrop
    if ydrop is not None: command += " -ydrop %d" % ydrop
    if gdrop is not None: command += " -gdrop %d" % gdrop
    if verbose: command += " -vv"
    clicommon.run_command(command, display_cmd=verbose)


#
# 'pfc' group ('config interface pfc ...')
#

@interface.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def pfc(ctx):
    """Set PFC configuration."""
    pass


#
# 'pfc asymmetric' ('config interface pfc asymmetric ...')
#

@pfc.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('status', type=click.Choice(['on', 'off']))
@click.pass_context
def asymmetric(ctx, interface_name, status):
    """Set asymmetric PFC configuration."""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    clicommon.run_command("pfc config asymmetric {0} {1}".format(status, interface_name))

#
# 'pfc priority' command ('config interface pfc priority ...')
#

@pfc.command()
@click.argument('interface_name', metavar='<interface_name>', required=True)
@click.argument('priority', type=click.Choice([str(x) for x in range(8)]))
@click.argument('status', type=click.Choice(['on', 'off']))
@click.pass_context
def priority(ctx, interface_name, priority, status):
    """Set PFC priority configuration."""
    # Get the config_db connector
    config_db = ctx.obj['config_db']

    if clicommon.get_interface_naming_mode() == "alias":
        interface_name = interface_alias_to_name(config_db, interface_name)
        if interface_name is None:
            ctx.fail("'interface_name' is None!")

    clicommon.run_command("pfc config priority {0} {1} {2}".format(status, interface_name, priority))

#
# 'buffer' group ('config buffer ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def buffer(ctx):
    """Configure buffer_profile"""
    config_db = ConfigDBConnector()
    config_db.connect()

    if not is_dynamic_buffer_enabled(config_db):
        ctx.fail("This command can only be supported on a system with dynamic buffer enabled")


@buffer.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def profile(ctx):
    """Configure buffer profile"""
    pass


@profile.command('add')
@click.argument('profile', metavar='<profile>', required=True)
@click.option('--xon', metavar='<xon>', type=int, help="Set xon threshold")
@click.option('--xoff', metavar='<xoff>', type=int, help="Set xoff threshold")
@click.option('--size', metavar='<size>', type=int, help="Set reserved size size")
@click.option('--dynamic_th', metavar='<dynamic_th>', type=str, help="Set dynamic threshold")
@click.option('--pool', metavar='<pool>', type=str, help="Buffer pool")
@clicommon.pass_db
def add_profile(db, profile, xon, xoff, size, dynamic_th, pool):
    """Add or modify a buffer profile"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    profile_entry = config_db.get_entry('BUFFER_PROFILE', profile)
    if profile_entry:
        ctx.fail("Profile {} already exist".format(profile))

    update_profile(ctx, config_db, profile, xon, xoff, size, dynamic_th, pool)


@profile.command('set')
@click.argument('profile', metavar='<profile>', required=True)
@click.option('--xon', metavar='<xon>', type=int, help="Set xon threshold")
@click.option('--xoff', metavar='<xoff>', type=int, help="Set xoff threshold")
@click.option('--size', metavar='<size>', type=int, help="Set reserved size size")
@click.option('--dynamic_th', metavar='<dynamic_th>', type=str, help="Set dynamic threshold")
@click.option('--pool', metavar='<pool>', type=str, help="Buffer pool")
@clicommon.pass_db
def set_profile(db, profile, xon, xoff, size, dynamic_th, pool):
    """Add or modify a buffer profile"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    profile_entry = config_db.get_entry('BUFFER_PROFILE', profile)
    if not profile_entry:
        ctx.fail("Profile {} doesn't exist".format(profile))

    if not 'xoff' in profile_entry.keys() and xoff:
        ctx.fail("Can't change profile {} from dynamically calculating headroom to non-dynamically one".format(profile))

    update_profile(ctx, config_db, profile, xon, xoff, size, dynamic_th, pool, profile_entry)


def _is_shared_headroom_pool_enabled(ctx, config_db):
    ingress_lossless_pool = config_db.get_entry('BUFFER_POOL', 'ingress_lossless_pool')
    if 'xoff' in ingress_lossless_pool:
        return True

    default_lossless_param_table = config_db.get_table('DEFAULT_LOSSLESS_BUFFER_PARAMETER')
    if not default_lossless_param_table:
        ctx.fail("Dynamic buffer calculation is enabled while no entry found in DEFAULT_LOSSLESS_BUFFER_PARAMETER table")
    default_lossless_param = list(default_lossless_param_table.values())[0]
    over_subscribe_ratio = default_lossless_param.get('over_subscribe_ratio')
    if over_subscribe_ratio and over_subscribe_ratio != '0':
        return True

    return False


def update_profile(ctx, config_db, profile_name, xon, xoff, size, dynamic_th, pool, profile_entry = None):
    params = {}
    if profile_entry:
        params = profile_entry

    shp_enabled = _is_shared_headroom_pool_enabled(ctx, config_db)

    if not pool:
        pool = 'ingress_lossless_pool'
    params['pool'] = '[BUFFER_POOL|' + pool + ']'
    if not config_db.get_entry('BUFFER_POOL', pool):
        ctx.fail("Pool {} doesn't exist".format(pool))

    if xon:
        params['xon'] = xon
    else:
        xon = params.get('xon')

    if xoff:
        params['xoff'] = xoff
    else:
        xoff = params.get('xoff')

    if size:
        params['size'] = size
    else:
        size = params.get('size')

    dynamic_calculate = False if (xon or xoff or size) else True

    if dynamic_calculate:
        params['headroom_type'] = 'dynamic'
        if not dynamic_th:
            ctx.fail("Either size information (xon, xoff, size) or dynamic_th needs to be provided")
        params['dynamic_th'] = dynamic_th
    else:
        if not xon:
            ctx.fail("Xon is mandatory for non-dynamic profile")

        if not xoff:
            if shp_enabled:
                ctx.fail("Shared headroom pool is enabled, xoff is mandatory for non-dynamic profile")
            elif not size:
                ctx.fail("Neither xoff nor size is provided")
            else:
                xoff_number = int(size) - int(xon)
                if xoff_number <= 0:
                    ctx.fail("The xoff must be greater than 0 while we got {} (calculated by: size {} - xon {})".format(xoff_number, size, xon))
                params['xoff'] = str(xoff_number)

        if not size:
            if shp_enabled:
                size = int(xon)
            else:
                size = int(xon) + int(xoff)
            params['size'] = size

        if dynamic_th:
            params['dynamic_th'] = dynamic_th
        elif not params.get('dynamic_th'):
            # Fetch all the keys of default_lossless_buffer_parameter table
            # and then get the default_dynamic_th from that entry (should be only one)
            keys = config_db.get_keys('DEFAULT_LOSSLESS_BUFFER_PARAMETER')
            if len(keys) != 1:
                ctx.fail("Multiple entries are found in DEFAULT_LOSSLESS_BUFFER_PARAMETER while no dynamic_th specified")

            default_lossless_param = config_db.get_entry('DEFAULT_LOSSLESS_BUFFER_PARAMETER', keys[0])
            if 'default_dynamic_th' in default_lossless_param:
                params['dynamic_th'] = default_lossless_param['default_dynamic_th']
            else:
                ctx.fail("No dynamic_th defined in DEFAULT_LOSSLESS_BUFFER_PARAMETER")

    config_db.set_entry("BUFFER_PROFILE", (profile_name), params)

@profile.command('remove')
@click.argument('profile', metavar='<profile>', required=True)
@clicommon.pass_db
def remove_profile(db, profile):
    """Delete a buffer profile"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    full_profile_name = '[BUFFER_PROFILE|{}]'.format(profile)
    existing_pgs = config_db.get_table("BUFFER_PG")
    for k, v in existing_pgs.items():
        port, pg = k
        referenced_profile = v.get('profile')
        if referenced_profile and referenced_profile == full_profile_name:
            ctx.fail("Profile {} is referenced by {}|{} and can't be removed".format(profile, port, pg))

    entry = config_db.get_entry("BUFFER_PROFILE", profile)
    if entry:
        config_db.set_entry("BUFFER_PROFILE", profile, None)
    else:
        ctx.fail("Profile {} doesn't exist".format(profile))

@buffer.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def shared_headroom_pool(ctx):
    """Configure buffer shared headroom pool"""
    pass


@shared_headroom_pool.command()
@click.argument('ratio', metavar='<ratio>', type=int, required=True)
@clicommon.pass_db
def over_subscribe_ratio(db, ratio):
    """Configure over subscribe ratio"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    port_number = len(config_db.get_table('PORT'))
    if ratio < 0 or ratio > port_number:
        ctx.fail("Invalid over-subscribe-ratio value {}. It should be in range [0, {}]".format(ratio, port_number))

    default_lossless_param = config_db.get_table("DEFAULT_LOSSLESS_BUFFER_PARAMETER")
    first_item = True
    for k, v in default_lossless_param.items():
        if not first_item:
            ctx.fail("More than one item in DEFAULT_LOSSLESS_BUFFER_PARAMETER table. Only the first one is updated")
        first_item = False

        if ratio == 0:
            if "over_subscribe_ratio" in v.keys():
                v.pop("over_subscribe_ratio")
        else:
            v["over_subscribe_ratio"] = ratio

        config_db.set_entry("DEFAULT_LOSSLESS_BUFFER_PARAMETER", k, v)


@shared_headroom_pool.command()
@click.argument('size', metavar='<size>', type=int, required=True)
@clicommon.pass_db
def size(db, size):
    """Configure shared headroom pool size"""
    config_db = db.cfgdb
    state_db = db.db
    ctx = click.get_current_context()

    _hash = 'BUFFER_MAX_PARAM_TABLE|global'
    buffer_max_params = state_db.get_all(state_db.STATE_DB, _hash)
    if buffer_max_params:
        mmu_size = buffer_max_params.get('mmu_size')
        if mmu_size and int(mmu_size) < size:
            ctx.fail("Shared headroom pool must be less than mmu size ({})".format(mmu_size))

    ingress_lossless_pool = config_db.get_entry("BUFFER_POOL", "ingress_lossless_pool")

    if size == 0:
        if "xoff" in ingress_lossless_pool:
            ingress_lossless_pool.pop("xoff")
    else:
        ingress_lossless_pool["xoff"] = size

    config_db.set_entry("BUFFER_POOL", "ingress_lossless_pool", ingress_lossless_pool)


#
# 'platform' group ('config platform ...')
#

@config.group(cls=clicommon.AbbreviationGroup)
def platform():
    """Platform-related configuration tasks"""

# 'firmware' subgroup ("config platform firmware ...")
@platform.group(cls=clicommon.AbbreviationGroup)
def firmware():
    """Firmware configuration tasks"""
    pass

# 'install' subcommand ("config platform firmware install")
@firmware.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True
    ),
    add_help_option=False
)
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def install(args):
    """Install platform firmware"""
    cmd = "fwutil install {}".format(" ".join(args))

    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

# 'update' subcommand ("config platform firmware update")
@firmware.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True
    ),
    add_help_option=False
)
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def update(args):
    """Update platform firmware"""
    cmd = "fwutil update {}".format(" ".join(args))

    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

#
# 'watermark' group ("show watermark telemetry interval")
#

@config.group(cls=clicommon.AbbreviationGroup)
def watermark():
    """Configure watermark """
    pass

@watermark.group(cls=clicommon.AbbreviationGroup)
def telemetry():
    """Configure watermark telemetry"""
    pass

@telemetry.command()
@click.argument('interval', required=True)
def interval(interval):
    """Configure watermark telemetry interval"""
    command = 'watermarkcfg --config-interval ' + interval
    clicommon.run_command(command)


#
# 'interface_naming_mode' subgroup ('config interface_naming_mode ...')
#

@config.group(cls=clicommon.AbbreviationGroup, name='interface_naming_mode')
def interface_naming_mode():
    """Modify interface naming mode for interacting with SONiC CLI"""
    pass

@interface_naming_mode.command('default')
def naming_mode_default():
    """Set CLI interface naming mode to DEFAULT (SONiC port name)"""
    set_interface_naming_mode('default')

@interface_naming_mode.command('alias')
def naming_mode_alias():
    """Set CLI interface naming mode to ALIAS (Vendor port alias)"""
    set_interface_naming_mode('alias')

def is_loopback_name_valid(loopback_name):
    """Loopback name validation
    """

    if loopback_name[:CFG_LOOPBACK_PREFIX_LEN] != CFG_LOOPBACK_PREFIX :
        return False
    if (loopback_name[CFG_LOOPBACK_PREFIX_LEN:].isdigit() is False or
          int(loopback_name[CFG_LOOPBACK_PREFIX_LEN:]) > CFG_LOOPBACK_ID_MAX_VAL) :
        return False
    if len(loopback_name) > CFG_LOOPBACK_NAME_TOTAL_LEN_MAX:
        return False
    return True

#
# 'loopback' group ('config loopback ...')
#
@config.group()
@click.pass_context
@click.option('-s', '--redis-unix-socket-path', help='unix socket path for redis connection')
def loopback(ctx, redis_unix_socket_path):
    """Loopback-related configuration tasks"""
    kwargs = {}
    if redis_unix_socket_path:
        kwargs['unix_socket_path'] = redis_unix_socket_path
    config_db = ConfigDBConnector(**kwargs)
    config_db.connect(wait_for_init=False)
    ctx.obj = {'db': config_db}

@loopback.command('add')
@click.argument('loopback_name', metavar='<loopback_name>', required=True)
@click.pass_context
def add_loopback(ctx, loopback_name):
    config_db = ctx.obj['db']
    if is_loopback_name_valid(loopback_name) is False:
        ctx.fail("{} is invalid, name should have prefix '{}' and suffix '{}' "
                .format(loopback_name, CFG_LOOPBACK_PREFIX, CFG_LOOPBACK_NO))

    lo_intfs = [k for k, v in config_db.get_table('LOOPBACK_INTERFACE').items() if type(k) != tuple]
    if loopback_name in lo_intfs:
        ctx.fail("{} already exists".format(loopback_name))

    config_db.set_entry('LOOPBACK_INTERFACE', loopback_name, {"NULL" : "NULL"})

@loopback.command('del')
@click.argument('loopback_name', metavar='<loopback_name>', required=True)
@click.pass_context
def del_loopback(ctx, loopback_name):
    config_db = ctx.obj['db']
    if is_loopback_name_valid(loopback_name) is False:
        ctx.fail("{} is invalid, name should have prefix '{}' and suffix '{}' "
                .format(loopback_name, CFG_LOOPBACK_PREFIX, CFG_LOOPBACK_NO))

    lo_config_db = config_db.get_table('LOOPBACK_INTERFACE')
    lo_intfs = [k for k, v in lo_config_db.items() if type(k) != tuple]
    if loopback_name not in lo_intfs:
        ctx.fail("{} does not exists".format(loopback_name))

    ips = [ k[1] for k in lo_config_db if type(k) == tuple and k[0] == loopback_name ]
    for ip in ips:
        config_db.set_entry('LOOPBACK_INTERFACE', (loopback_name, ip), None)

    config_db.set_entry('LOOPBACK_INTERFACE', loopback_name, None)


@config.group(cls=clicommon.AbbreviationGroup)
def ztp():
    """ Configure Zero Touch Provisioning """
    if os.path.isfile('/usr/bin/ztp') is False:
        exit("ZTP feature unavailable in this image version")

    if os.geteuid() != 0:
        exit("Root privileges are required for this operation")

@ztp.command()
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false,
                expose_value=False, prompt='ZTP will be restarted. You may lose switch data and connectivity, continue?')
@click.argument('run', required=False, type=click.Choice(["run"]))
def run(run):
    """Restart ZTP of the device."""
    command = "ztp run -y"
    clicommon.run_command(command, display_cmd=True)

@ztp.command()
@click.option('-y', '--yes', is_flag=True, callback=_abort_if_false,
                expose_value=False, prompt='Active ZTP session will be stopped and disabled, continue?')
@click.argument('disable', required=False, type=click.Choice(["disable"]))
def disable(disable):
    """Administratively Disable ZTP."""
    command = "ztp disable -y"
    clicommon.run_command(command, display_cmd=True)

@ztp.command()
@click.argument('enable', required=False, type=click.Choice(["enable"]))
def enable(enable):
    """Administratively Enable ZTP."""
    command = "ztp enable"
    clicommon.run_command(command, display_cmd=True)

#
# 'syslog' group ('config syslog ...')
#
@config.group(cls=clicommon.AbbreviationGroup, name='syslog')
@click.pass_context
def syslog_group(ctx):
    """Syslog server configuration tasks"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {'db': config_db}

@syslog_group.command('add')
@click.argument('syslog_ip_address', metavar='<syslog_ip_address>', required=True)
@click.pass_context
def add_syslog_server(ctx, syslog_ip_address):
    """ Add syslog server IP """
    if not clicommon.is_ipaddress(syslog_ip_address):
        ctx.fail('Invalid ip address')
    db = ctx.obj['db']
    syslog_servers = db.get_table("SYSLOG_SERVER")
    if syslog_ip_address in syslog_servers:
        click.echo("Syslog server {} is already configured".format(syslog_ip_address))
        return
    else:
        db.set_entry('SYSLOG_SERVER', syslog_ip_address, {'NULL': 'NULL'})
        click.echo("Syslog server {} added to configuration".format(syslog_ip_address))
        try:
            click.echo("Restarting rsyslog-config service...")
            clicommon.run_command("systemctl restart rsyslog-config", display_cmd=False)
        except SystemExit as e:
            ctx.fail("Restart service rsyslog-config failed with error {}".format(e))

@syslog_group.command('del')
@click.argument('syslog_ip_address', metavar='<syslog_ip_address>', required=True)
@click.pass_context
def del_syslog_server(ctx, syslog_ip_address):
    """ Delete syslog server IP """
    if not clicommon.is_ipaddress(syslog_ip_address):
        ctx.fail('Invalid IP address')
    db = ctx.obj['db']
    syslog_servers = db.get_table("SYSLOG_SERVER")
    if syslog_ip_address in syslog_servers:
        db.set_entry('SYSLOG_SERVER', '{}'.format(syslog_ip_address), None)
        click.echo("Syslog server {} removed from configuration".format(syslog_ip_address))
    else:
        ctx.fail("Syslog server {} is not configured.".format(syslog_ip_address))
    try:
        click.echo("Restarting rsyslog-config service...")
        clicommon.run_command("systemctl restart rsyslog-config", display_cmd=False)
    except SystemExit as e:
        ctx.fail("Restart service rsyslog-config failed with error {}".format(e))

#
# 'ntp' group ('config ntp ...')
#
@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def ntp(ctx):
    """NTP server configuration tasks"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {'db': config_db}

@ntp.command('add')
@click.argument('ntp_ip_address', metavar='<ntp_ip_address>', required=True)
@click.pass_context
def add_ntp_server(ctx, ntp_ip_address):
    """ Add NTP server IP """
    if not clicommon.is_ipaddress(ntp_ip_address):
        ctx.fail('Invalid ip address')
    db = ctx.obj['db']
    ntp_servers = db.get_table("NTP_SERVER")
    if ntp_ip_address in ntp_servers:
        click.echo("NTP server {} is already configured".format(ntp_ip_address))
        return
    else:
        db.set_entry('NTP_SERVER', ntp_ip_address, {'NULL': 'NULL'})
        click.echo("NTP server {} added to configuration".format(ntp_ip_address))
        try:
            click.echo("Restarting ntp-config service...")
            clicommon.run_command("systemctl restart ntp-config", display_cmd=False)
        except SystemExit as e:
            ctx.fail("Restart service ntp-config failed with error {}".format(e))

@ntp.command('del')
@click.argument('ntp_ip_address', metavar='<ntp_ip_address>', required=True)
@click.pass_context
def del_ntp_server(ctx, ntp_ip_address):
    """ Delete NTP server IP """
    if not clicommon.is_ipaddress(ntp_ip_address):
        ctx.fail('Invalid IP address')
    db = ctx.obj['db']
    ntp_servers = db.get_table("NTP_SERVER")
    if ntp_ip_address in ntp_servers:
        db.set_entry('NTP_SERVER', '{}'.format(ntp_ip_address), None)
        click.echo("NTP server {} removed from configuration".format(ntp_ip_address))
    else:
        ctx.fail("NTP server {} is not configured.".format(ntp_ip_address))
    try:
        click.echo("Restarting ntp-config service...")
        clicommon.run_command("systemctl restart ntp-config", display_cmd=False)
    except SystemExit as e:
        ctx.fail("Restart service ntp-config failed with error {}".format(e))

#
# 'sflow' group ('config sflow ...')
#
@config.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def sflow(ctx):
    """sFlow-related configuration tasks"""
    config_db = ConfigDBConnector()
    config_db.connect()
    ctx.obj = {'db': config_db}

#
# 'sflow' command ('config sflow enable')
#
@sflow.command()
@click.pass_context
def enable(ctx):
    """Enable sFlow"""
    config_db = ctx.obj['db']
    sflow_tbl = config_db.get_table('SFLOW')

    if not sflow_tbl:
        sflow_tbl = {'global': {'admin_state': 'up'}}
    else:
        sflow_tbl['global']['admin_state'] = 'up'

    config_db.mod_entry('SFLOW', 'global', sflow_tbl['global'])

    try:
        proc = subprocess.Popen("systemctl is-active sflow", shell=True, text=True, stdout=subprocess.PIPE)
        (out, err) = proc.communicate()
    except SystemExit as e:
        ctx.fail("Unable to check sflow status {}".format(e))

    if out != "active":
        log.log_info("sflow service is not enabled. Starting sflow docker...")
        clicommon.run_command("sudo systemctl enable sflow")
        clicommon.run_command("sudo systemctl start sflow")

#
# 'sflow' command ('config sflow disable')
#
@sflow.command()
@click.pass_context
def disable(ctx):
    """Disable sFlow"""
    config_db = ctx.obj['db']
    sflow_tbl = config_db.get_table('SFLOW')

    if not sflow_tbl:
        sflow_tbl = {'global': {'admin_state': 'down'}}
    else:
        sflow_tbl['global']['admin_state'] = 'down'

    config_db.mod_entry('SFLOW', 'global', sflow_tbl['global'])

#
# 'sflow' command ('config sflow polling-interval ...')
#
@sflow.command('polling-interval')
@click.argument('interval',  metavar='<polling_interval>', required=True,
                type=int)
@click.pass_context
def polling_int(ctx, interval):
    """Set polling-interval for counter-sampling (0 to disable)"""
    if interval not in range(5, 301) and interval != 0:
        click.echo("Polling interval must be between 5-300 (0 to disable)")

    config_db = ctx.obj['db']
    sflow_tbl = config_db.get_table('SFLOW')

    if not sflow_tbl:
        sflow_tbl = {'global': {'admin_state': 'down'}}

    sflow_tbl['global']['polling_interval'] = interval
    config_db.mod_entry('SFLOW', 'global', sflow_tbl['global'])

def is_valid_sample_rate(rate):
    return rate in range(256, 8388608 + 1)


#
# 'sflow interface' group
#
@sflow.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def interface(ctx):
    """Configure sFlow settings for an interface"""
    pass

#
# 'sflow' command ('config sflow interface enable  ...')
#
@interface.command()
@click.argument('ifname', metavar='<interface_name>', required=True, type=str)
@click.pass_context
def enable(ctx, ifname):
    config_db = ctx.obj['db']
    if not interface_name_is_valid(config_db, ifname) and ifname != 'all':
        click.echo("Invalid interface name")
        return

    intf_dict = config_db.get_table('SFLOW_SESSION')

    if intf_dict and ifname in intf_dict:
        intf_dict[ifname]['admin_state'] = 'up'
        config_db.mod_entry('SFLOW_SESSION', ifname, intf_dict[ifname])
    else:
        config_db.mod_entry('SFLOW_SESSION', ifname, {'admin_state': 'up'})

#
# 'sflow' command ('config sflow interface disable  ...')
#
@interface.command()
@click.argument('ifname', metavar='<interface_name>', required=True, type=str)
@click.pass_context
def disable(ctx, ifname):
    config_db = ctx.obj['db']
    if not interface_name_is_valid(config_db, ifname) and ifname != 'all':
        click.echo("Invalid interface name")
        return

    intf_dict = config_db.get_table('SFLOW_SESSION')

    if intf_dict and ifname in intf_dict:
        intf_dict[ifname]['admin_state'] = 'down'
        config_db.mod_entry('SFLOW_SESSION', ifname, intf_dict[ifname])
    else:
        config_db.mod_entry('SFLOW_SESSION', ifname,
                            {'admin_state': 'down'})

#
# 'sflow' command ('config sflow interface sample-rate  ...')
#
@interface.command('sample-rate')
@click.argument('ifname', metavar='<interface_name>', required=True, type=str)
@click.argument('rate', metavar='<sample_rate>', required=True, type=int)
@click.pass_context
def sample_rate(ctx, ifname, rate):
    config_db = ctx.obj['db']
    if not interface_name_is_valid(config_db, ifname) and ifname != 'all':
        click.echo('Invalid interface name')
        return
    if not is_valid_sample_rate(rate):
        click.echo('Error: Sample rate must be between 256 and 8388608')
        return

    sess_dict = config_db.get_table('SFLOW_SESSION')

    if sess_dict and ifname in sess_dict:
        sess_dict[ifname]['sample_rate'] = rate
        config_db.mod_entry('SFLOW_SESSION', ifname, sess_dict[ifname])
    else:
        config_db.mod_entry('SFLOW_SESSION', ifname, {'sample_rate': rate})


#
# 'sflow collector' group
#
@sflow.group(cls=clicommon.AbbreviationGroup)
@click.pass_context
def collector(ctx):
    """Add/Delete a sFlow collector"""
    pass

def is_valid_collector_info(name, ip, port, vrf_name):
    if len(name) > 16:
        click.echo("Collector name must not exceed 16 characters")
        return False

    if port not in range(0, 65535 + 1):
        click.echo("Collector port number must be between 0 and 65535")
        return False

    if not clicommon.is_ipaddress(ip):
        click.echo("Invalid IP address")
        return False

    if vrf_name != 'default' and vrf_name != 'mgmt':
        click.echo("Only 'default' and 'mgmt' VRF are supported")
        return False

    return True

#
# 'sflow' command ('config sflow collector add ...')
#
@collector.command()
@click.option('--port', required=False, type=int, default=6343,
              help='Collector port number')
@click.option('--vrf', required=False, type=str, default='default',
              help='Collector VRF')
@click.argument('name', metavar='<collector_name>', required=True)
@click.argument('ipaddr', metavar='<IPv4/v6_address>', required=True)
@click.pass_context
def add(ctx, name, ipaddr, port, vrf):
    """Add a sFlow collector"""
    ipaddr = ipaddr.lower()

    if not is_valid_collector_info(name, ipaddr, port, vrf):
        return

    config_db = ctx.obj['db']
    collector_tbl = config_db.get_table('SFLOW_COLLECTOR')

    if (collector_tbl and name not in collector_tbl and len(collector_tbl) == 2):
        click.echo("Only 2 collectors can be configured, please delete one")
        return

    config_db.mod_entry('SFLOW_COLLECTOR', name,
                        {"collector_ip": ipaddr,  "collector_port": port,
                         "collector_vrf": vrf})
    return

#
# 'sflow' command ('config sflow collector del ...')
#
@collector.command('del')
@click.argument('name', metavar='<collector_name>', required=True)
@click.pass_context
def del_collector(ctx, name):
    """Delete a sFlow collector"""
    config_db = ctx.obj['db']
    collector_tbl = config_db.get_table('SFLOW_COLLECTOR')

    if name not in collector_tbl:
        click.echo("Collector: {} not configured".format(name))
        return

    config_db.mod_entry('SFLOW_COLLECTOR', name, None)

#
# 'sflow agent-id' group
#
@sflow.group(cls=clicommon.AbbreviationGroup, name='agent-id')
@click.pass_context
def agent_id(ctx):
    """Add/Delete a sFlow agent"""
    pass

#
# 'sflow' command ('config sflow agent-id add ...')
#
@agent_id.command()
@click.argument('ifname', metavar='<interface_name>', required=True)
@click.pass_context
def add(ctx, ifname):
    """Add sFlow agent information"""
    if ifname not in netifaces.interfaces():
        click.echo("Invalid interface name")
        return

    config_db = ctx.obj['db']
    sflow_tbl = config_db.get_table('SFLOW')

    if not sflow_tbl:
        sflow_tbl = {'global': {'admin_state': 'down'}}

    if 'agent_id' in sflow_tbl['global']:
        click.echo("Agent already configured. Please delete it first.")
        return

    sflow_tbl['global']['agent_id'] = ifname
    config_db.mod_entry('SFLOW', 'global', sflow_tbl['global'])

#
# 'sflow' command ('config sflow agent-id del')
#
@agent_id.command('del')
@click.pass_context
def delete(ctx):
    """Delete sFlow agent information"""
    config_db = ctx.obj['db']
    sflow_tbl = config_db.get_table('SFLOW')

    if not sflow_tbl:
        sflow_tbl = {'global': {'admin_state': 'down'}}

    if 'agent_id' not in sflow_tbl['global']:
        click.echo("sFlow agent not configured.")
        return

    sflow_tbl['global'].pop('agent_id')
    config_db.set_entry('SFLOW', 'global', sflow_tbl['global'])


# Load plugins and register them
helper = util_base.UtilHelper()
for plugin in helper.load_plugins(plugins):
    helper.register_plugin(plugin, config)


if __name__ == '__main__':
    config()
