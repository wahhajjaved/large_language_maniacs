import gevent.monkey
gevent.monkey.patch_all()
from gevent import pool
from gevent import queue
import os
import sys
import urllib3
from keystoneauth1.identity import v3
from keystoneauth1 import session as keystone_session
from keystoneclient.v3 import client as keystone_client
from ironicclient import client as ironic_client
import ironic_inspector_client
import pandas
from novaclient import client as nova_client
import glanceclient
import argparse


# We don't need no security
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

flavor_body = {
              'name': 'general',
              'vcpus': 0,
              'ram': 0,
              'disk': 0,
              'description': 'A baremetal flavor'
              }
flavor_schema = {
    'body': {
        'name': 'general',
        'vcpus': 1,
        'ram': 1,
        'disk': 1
    },
    'details': {
        'cpu_arch': 'x86_64',
        'capabilities:boot_option': 'local',
        'capabilities:disk_label': 'gpt',
        # Resouce limits on baremetal flavors is unimplemented in openstack
        'resources:VCPU': 0,
        'resources:MEMORY_MB': 0,
        'resources:DISK_GB': 0,
    }
}

CLIENTS = {}
IR_KERNEL_IMAGE = None
IR_INITRD_IMAGE = None


def load_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("excel_file", help="Path to the excel file to read.")
    return parser.parse_args()


def load_auth_clients():
    auth_fields = {
        'auth_url': os.environ['OS_AUTH_URL'],
        'username': os.environ['OS_USERNAME'],
        'password': os.environ['OS_PASSWORD'],
        'project_name': os.environ['OS_PROJECT_NAME'],
        'user_domain_name': os.environ['OS_USER_DOMAIN_NAME'],
        'project_domain_name': os.environ['OS_PROJECT_DOMAIN_NAME']
    }

    v3_auth = v3.Password(**auth_fields)
    ks_sess = keystone_session.Session(auth=v3_auth, verify=False)
    ks_client = keystone_client.Client(session=ks_sess)
    CLIENTS['keystone'] = ks_client

    gl_client = glanceclient.Client('2', session=ks_sess)
    CLIENTS['glance'] = gl_client

    nv_client = nova_client.Client(2, session=ks_sess)
    CLIENTS['nova'] = nv_client

    ir_client = ironic_client.get_client(1, insecure=True, **auth_fields)
    CLIENTS['ironic'] = ir_client

    ins_client = ironic_inspector_client.ClientV1(session=ks_sess)
    CLIENTS['ironic-inspector'] = ins_client


def read_excel_file(excel_file):
    ironic_hosts = pandas.read_excel(open(excel_file, 'rb'))

    seen = set()
    nodes = []
    for i in ironic_hosts.index:
        node_name = ironic_hosts['hostname'][i]
        if node_name not in seen:
            seen.add(node_name)
            nodes.append({
                'hostname': ironic_hosts['hostname'][i],
                'ipv4': ironic_hosts['ipmi address'][i],
                'username': ironic_hosts['ipmi username'][i],
                'password': ironic_hosts['ipmi password'][i],
                'mac': ironic_hosts['provisioning mac address'][i],
                'drive': ironic_hosts['managed drive'][i],
                'flavor': ironic_hosts['server hardware type'][i]
            })
        else:
            error_msg = ("Duplicated hostname %s in excel file. ",
                         "Names must be unique. Please remedy and rerun.")
            print(error_msg % (node_name))
            sys.exit(56)
    return nodes


def get_safe_resource_name(flavor_name):
    # According to the rules, resource flavors must be a key that:
    # 1) begin with CUSTOM_
    # 2) have all punctuation replaced with an underline
    # 3) be all upper case
    # 4) has a value of 1 in the hash
    replace_chars = ('.', '-', '/', '`', '\'', '?', ',', '+')
    for i in replace_chars:
        flavor_name = flavor_name.replace(i, '_')
    return "CUSTOM_" + flavor_name.upper()


def process_node(node):
    ironic = CLIENTS['ironic']
    ironic_vars = {
        'name': node['hostname'],
        'driver': 'ipmi',
        'driver_info': {
            'ipmi_address': node['ipv4'],
            'ipmi_password': node['password'],
            'ipmi_username': node['username'],
            # TODO: yank those uuids from something
            'deploy_kernel': IR_KERNEL_IMAGE,
            'deploy_ramdisk': IR_INITRD_IMAGE,
            'resource_class': node['flavor'],
            },
        'properties': {
            'capabilities': 'boot_option:local,disk_label:gpt',
            'cpu_arch': 'x86_64'
            }
        }
    ir_node = ironic.node.create(**ironic_vars)
    print(dir(ironic.node))
    print("Created node %s" % (node['hostname']))
    ir_port_vars = {
            "address": node['mac'],
            "node_uuid": ir_node.uuid
            }
    ir_port = ironic.port.create(**ir_port_vars)
    print("Created neutron port %s for node %s" % (ir_port.uuid, ir_node.name))

    ironic.node.wait_for_provision_state(ir_node.uuid, 'available', 300)
    ironic.node.set_provision_state(ir_node.uuid, 'manage')
    ironic.node.wait_for_provision_state(ir_node.uuid, 'manageable', 300)
    print("Managed node %s" % (ir_node.name))
    ironic.node.set_provision_state(ir_node.uuid, 'inspect')
    print("Inspecting node %s" % (ir_node.name))
    ironic.node.wait_for_provision_state(ir_node.uuid, 'manageable', 3600)
    print("Inspection complete for node %s" % (ir_node.name))

    inspector = CLIENTS['ironic-inspector']
    disks = inspector.get_data(ir_node.uuid)['inventory']['disks']
    device_name = '/dev/' + node['drive']
    target_drive = None
    for disk in disks:
        if disk['name'] == device_name:
            target_drive = disk['serial']
            break
    if target_drive is not None:
        props = [{
            'op': 'add',
            'path': '/properties/root_device',
            'value': target_drive
            }]
        ironic.node.update(ir_node.uuid, props)
        print("Setting boot device to %s on %s" % (target_drive, ir_node.name))


def node_worker(work_queue, return_queue):
    try:
        node = work_queue.get(timeout=0)
    except gevent.queue.Empty:
        return
    try:
        process_node(node)
    except Exception as e:
        return_queue.put({'hostname': node['hostname'], 'message': e.message})


def main():
    args = load_args()
    load_auth_clients()
    xl_nodes = read_excel_file(args.excel_file)

    xl_flavors = set([node['flavor'] for node in xl_nodes])

    images = CLIENTS['glance'].images.list()
    for image in images:
        if image.name == 'ironic-deploy.kernel':
            IR_KERNEL_IMAGE = image.id
        if image.name == 'ironic-deploy.initramfs':
            IR_INITRD_IMAGE = image.id

    if None in [IR_KERNEL_IMAGE, IR_INITRD_IMAGE]:
        err_msg = ("An error has occured. Please ensure ironic introspection"
                   " images are loaded into glance. Images must be named "
                   "\"ironic-deploy.kernel\" and \"ironic-deploy.initramfs\".")
        print(err_msg)
        sys.exit(50)

    nova = CLIENTS['nova']
    api_flavors = nova.flavors.list()
    api_flavor_names = [f.name for f in api_flavors]
    for flavor in xl_flavors:
        if flavor not in api_flavor_names:
            body = flavor_schema['body'].copy()
            details = flavor_schema['details'].copy()
            body['name'] = flavor
            safe_name = get_safe_resource_name(body['name'])
            details[safe_name] = 1
            fl = nova.flavors.create(**body)
            fl.set_keys(details)
            print("Created baremetal flavor %s" % (fl.name))

    api_nodes = [node.name for node in CLIENTS['ironic'].node.list()]
    pool_limit = 8
    work_pool = gevent.pool.Pool(pool_limit)
    work_queue = gevent.queue.Queue()
    return_queue = gevent.queue.Queue()
    for node in xl_nodes:
        if node['hostname'] not in api_nodes:
            work_queue.put(node)

    work_pool.spawn(node_worker, work_queue, return_queue)

    while not work_queue.empty() and not work_pool.free_count == pool_limit:
        gevent.sleep(0.1)
        for x in range(0, min(queue.qsize(), work_pool.free_count())):
            work_pool.spawn(node_worker, work_queue, return_queue)

    work_pool.join()

    while not return_queue.empty():
        e = return_queue.get(timeout=0)
        print("Errors Detected!")
        print("%s: %s" % (e['hostname'], e['message']))
