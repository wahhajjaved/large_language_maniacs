import os
import re
import time
import json
import logging
from itertools import chain

from lettuce import world, step, after

from revizor2.api import IMPL
from revizor2.conf import CONF
from revizor2.consts import ServerStatus, Platform
from revizor2.fixtures import resources
from revizor2.utils import wait_until


LOG = logging.getLogger(__name__)


@step('I see (.+) server (.+)$')
def waiting_for_assertion(step, state, serv_as, timeout=1400):
    role = world.get_role()
    server = world.wait_server_bootstrapping(role, state, timeout)
    setattr(world, serv_as, server)
    LOG.info('Server %s (%s) succesfully in %s state' % (server.id, serv_as, state))


@step('I wait and see (?:[\w]+\s)*([\w]+) server ([\w\d]+)$')
def waiting_server(step, state, serv_as, timeout=1400):
    if CONF.feature.dist.is_windows:
        timeout = 2400
    role = world.get_role()
    server = world.wait_server_bootstrapping(role, state, timeout)
    LOG.info('Server succesfully %s' % state)
    setattr(world, serv_as, server)


@step('scalarizr(\snot)* installed on the ([\w\d]+) server')
def is_server_scalarized(step, negation, serv_as):
    server = getattr(world, serv_as)
    assert (not negation) is server.is_scalarized


@step('I have (.+) server ([\w\d]+)$')
def having_server(step, state, serv_as):
    server = getattr(world, serv_as)
    world.assert_not_equal(server.status, ServerStatus.from_code(state), "Server %s is not in state %s" % (server.id, state))


#TODO: Add check hostup message and direction
@step("I save (\w+) configuration in '([\w]+)' message in ([\w\d]+)$")
def save_config_from_message(step, config_group, message, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Get messages from server %s' % server.id)
    messages = world.get_szr_messages(node)
    msg_id = filter(lambda x: x['name'] == message, messages)[0]['id']
    LOG.info('Message id for %s is %s' % (message, msg_id))
    message_details = json.loads(node.run('szradm message-details %s --json' % msg_id)[0])['body']
    LOG.info('Message details is %s' % message_details)
    LOG.info('Save message part %s' % config_group)
    setattr(world, '%s_%s_%s' % (serv_as, message.lower(), config_group), message_details[config_group])


@step("(\w+) configuration in '([\w]+)' message in ([\w\d]+) is old")
def check_message_config(step, config_group, message, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Get messages from server %s' % server.id)
    messages = world.get_szr_messages(node)
    msg_id = filter(lambda x: x['name'] == message, messages)[0]['id']
    LOG.info('Message id for %s is %s' % (message, msg_id))
    message_details = json.loads(node.run('szradm message-details %s --json' % msg_id)[0])['body']
    LOG.info('Message details is %s' % message_details)
    old_details = getattr(world, '%s_%s_%s' % (serv_as, message.lower(), config_group), '')
    if not config_group in message_details or old_details == message_details[config_group]:
        LOG.error('New and old details is not equal: %s\n %s' % (old_details, message_details[config_group]))
        raise AssertionError('New and old details is not equal')


@step("[directory|file] '([\W\w]+)' exist in ([\w\d]+)$")
def check_path(step, path, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    for attempt in range(3):
        out = node.run('/bin/ls %s' % path)
        if not out[0] and not out[1]:
            time.sleep(5)
            continue
        break
    LOG.info('Check directory %s' % path)
    if 'No such file or directory' in out[0] or 'No such file or directory' in out[1] or not out[0]:
        LOG.error('Directory (file) not exist')
        raise AssertionError("'%s' not exist in server %s" % (path, server.id))


@step("I create (\d+) files in '(.+)' in ([\w\d]+)")
def create_files(step, file_count, directory, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Create %s files in directory %s' % (file_count, directory))
    node.run('cd %s && for (( i=0;i<%s;i++ )) do touch "file$i"; done' % (directory, file_count))


@step("count of files in directory '(.+)' is (\d+) in ([\w\d]+)")
def check_file_count(step, directory, file_count, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Check count of files in directory %s' % directory)
    out = node.run('cd %s && ls' % directory)[0].split()
    for i in ['..', '.', '...', 'lost+found']:
        if i in out:
            out.remove(i)
    if not int(file_count) == len(out):
        raise AssertionError('Count of files in directory is not %s, is %s' % (file_count, out))


@step('I define event \'(.+)\'$')
def define_event_to_role(step, event):
    events = IMPL.event.list()
    res = filter(lambda x: x['name'] == event, events)
    if not res:
        LOG.info('Create new Event')
        IMPL.event.change(event, 'Revizor FireEvent')
        events = IMPL.event.list()
    res = filter(lambda x: x['name'] == event, events)[0]
    setattr(world, 'last_event', res)


@step('I attach a script \'(.+)\' on this event')
def attach_script(step, script_name):
    scripts = IMPL.script.list()
    role = world.get_role()
    res = filter(lambda x: x['name'] == script_name, scripts)[0]
    LOG.info('Add script %s to custom event %s' % (res['name'], world.last_event['name']))
    IMPL.farm.edit_role(world.farm.id, role.role.id, scripting=[{
        "script_type": "scalr",
        "script_id": str(res['id']),
        "script": res['name'],
        "event": world.last_event['name'],
        "params": [],
        "target": "instance",
        "version": "-1",
        "timeout": "1200",
        "issync": "1",
        "order_index": "1",
        }]
    )


@step('I execute \'(.+)\' in (.+)$')
def execute_command(step, command, serv_as):
    node = world.cloud.get_node(getattr(world, serv_as))
    LOG.info('Execute command on server: %s' % command)
    node.run(command)


@step('server ([\w\d]+) contain \'(.+)\'')
def check_file(step, serv_as, path):
    node = world.cloud.get_node(getattr(world, serv_as))
    out = node.run('ls %s' % path)
    LOG.info('Check exist path: %s' % path)
    if not out[2] == 0:
        raise AssertionError('File \'%s\' not exist: %s' % (path, out))


@step("I save device for '(.+)' for role")
def save_device_for_additional_storage(step, mount_point):
    device_id = world.get_storage_device_by_mnt_point(mount_point)[0]['storageId']
    LOG.info('Volume Id for mount point "%s" is "%s"' % (mount_point, device_id))
    setattr(world, 'device_%s' % mount_point.replace('/', '_'), device_id)


@step("I delete saved device '(.+)'")
def delete_volume(step, mount_point):
    device_id = getattr(world, 'device_%s' % mount_point.replace('/', '_'))
    LOG.info('Delete volume: %s' % device_id)
    volume = filter(lambda x: x.id == device_id, world.cloud.list_volumes())
    if volume:
        volume = volume[0]
    else:
        raise AssertionError('Can\'t found Volume in cloud with ID: %s' % device_id)

    for i in range(10):
        try:
            world.cloud._driver._conn.destroy_volume(volume)
            break
        except Exception as e:
            if 'attached' in e.message:
                LOG.warning('Volume %s currently attached to server' % device_id)
                time.sleep(60)


@step("saved device for '(.+)' for role is another")
def verify_saved_and_new_volumes(step, mount_point):
    device = world.get_storage_device_by_mnt_point(mount_point)[0]
    if device['storageId'] == getattr(world, 'device_%s' % mount_point.replace('/', '_')):
        raise AssertionError('Old and new Volume Id for mount point "%s" is equally (%s)' % (mount_point, device))


@step("ports \[([\d,]+)\] not in iptables in ([\w\d]+)")
@world.run_only_if(platform='!%s' % Platform.RACKSPACE_US, dist=['!scientific6', '!centos-7-x'])
def verify_ports_in_iptables(step, ports, serv_as):
    LOG.info('Verify ports "%s" in iptables' % ports)
    if CONF.feature.driver.current_cloud in [Platform.IDCF,
                                             Platform.CLOUDSTACK]:
        LOG.info('Not check iptables because CloudStack')
        return
    server = getattr(world, serv_as)
    ports = ports.split(',')
    node = world.cloud.get_node(server)
    rules = node.run('iptables -L')[0]
    LOG.debug('iptables rules:\n%s' % rules)

    for port in ports:
        LOG.debug('Check port "%s" in iptables rules' % port)
        if port in rules:
            raise AssertionError('Port "%s" in iptables rules!' % port)


@step("I save mount table on ([\w\d]+)")
def save_mount_table(step, serv_as):
    server = getattr(world, serv_as)
    LOG.info('Save mount table from server "%s"' % server.id)
    node = world.cloud.get_node(server)
    mount_table = node.run('mount')[0].splitlines()
    mount_table = {x.split()[2]: x.split()[0] for x in mount_table if x}
    LOG.debug('Mount table:\n %s' % mount_table)
    setattr(world, '%s_mount_table' % serv_as, mount_table)


@step("disk from ([\w\d]+) mount points for '([\W\w]+)' exist in fstab on ([\w\d]+)")
def verify_mount_point_in_fstab(step, from_serv_as, mount_point, to_serv_as):
    to_server = getattr(world, to_serv_as)
    LOG.info('Verify disk from mount point "%s" exist in fstab on server "%s"' %
             (mount_point, to_server.id))
    node = world.cloud.get_node(to_server)
    for i in range(3):
        fstab = node.run('cat /etc/fstab')[0]
        if not fstab: #FIXME: on openstack this trouble was, fix this
            LOG.warning('cat /etc/fstab return nothing')
            time.sleep(15)
            continue
        break
    fstab = fstab.splitlines()
    fstab = {x.split()[1]: x.split()[0] for x in fstab if x and x.startswith('/')}
    LOG.debug('Fstab on server "%s" contains:\n %s' % (to_server.id, fstab))
    mount_disks = getattr(world, '%s_mount_table' % from_serv_as)
    if mount_point not in mount_disks:
        raise AssertionError('Mount point "%s" not exist in mount table:\n%s' %
                             (mount_point, mount_disks))
    if mount_point not in fstab:
        raise AssertionError('Mount point "%s" not exist in fstab:\n%s' %
                             (mount_point, fstab))
    check_symlink, stderr, exit_code = node.run('ls -l "%s"' % (mount_disks[mount_point]))
    if check_symlink.startswith('l'):
        path = os.path.realpath(mount_disks[mount_point] + "/.." + fstab[mount_point])
        if not fstab[mount_point] in path:
            raise AssertionError('Disk in fstab: "%s" is not in symlink "%s"' %
                                 (fstab[mount_point], path))
    else:
        assert mount_disks[mount_point] == fstab[mount_point], (
            'Disk from mount != disk in fstab: "%s" != "%s"' % (
                mount_disks[mount_point], fstab[mount_point]))


@step("start time in ([\w\d _-]+) scripts are different for ([\w\d]+)")
def verify_stdout_for_scripts(step, script_name, serv_as):
    server = getattr(world, serv_as)
    script_name = re.sub('[^A-Za-z0-9/.]+', '_', script_name)[:50]
    times = set()
    counter = 0
    server.scriptlogs.reload()
    for script in server.scriptlogs:
        if not script.name == script_name:
            continue
        counter += 1
        times.add(script.message.splitlines()[-1].split()[-2][:-3])
    if not len(times) == counter:
        raise AssertionError('Last reboot times is equals: %s' % list(times))


@step("disk types in role are valid")
def verify_attached_disk_types(step):
    LOG.info('Verify atype of attached disks')
    role = world.get_role()
    storage_config = IMPL.farm.get_role_settings(world.farm.id, role.role.id)['storages']
    volume_ids = {}
    for device in storage_config['configs']:
        volume_ids[device['mountPoint']] = [s['storageId'] for s in storage_config['devices'][device['id']]]
    ids = list(chain.from_iterable(volume_ids.values()))
    volumes = filter(lambda x: x.id in ids, world.cloud.list_volumes())
    for mount_point in volume_ids:
        volume_ids[mount_point] = filter(lambda x: x.id in volume_ids[mount_point], volumes)
    LOG.debug('Volumes in mount points: %s' % volume_ids)
    if CONF.feature.driver.current_cloud == Platform.EC2:
        LOG.warning('In EC2 platform we can\'t get volume type (libcloud limits)')
        return
    elif CONF.feature.driver.current_cloud == Platform.GCE:
        if not volume_ids['/media/diskmount'][0].extra['type'] == 'pd-standard':
            raise AssertionError('Volume attached to /media/diskmount must be "pd-standard" but it: %s' %
                                 volume_ids['/media/diskmount'][0].extra['type'])
        if not volume_ids['/media/raidmount'][0].extra['type'] == 'pd-ssd':
            raise AssertionError(
                'Volume attached to /media/raidmount must be "pd-ssd" but it: %s' %
                volume_ids['/media/diskmount'][0].extra['type'])


@step(r"instance vcpus info not empty for ([\w\d]+)")
def checking_info_instance_vcpus(step, serv_as):
    server = getattr(world, serv_as)
    vcpus = int(server.details['info.instance_vcpus'])
    LOG.info('Server %s vcpus info: %s' % (server.id, vcpus))
    assert vcpus > 0, 'info.instance_vcpus not valid for %s' % server.id


@step(r"I reconfigure device partitions for '([\W\w]+)' on ([\w\d]+)")
def create_partitions_on_volume(step, mnt_point, serv_as):
    script_name = "create_partitions.sh"
    script_src = resources(os.path.join("scripts", script_name)).get()
    path = os.path.join('/tmp', script_name)

    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)

    LOG.info('Creating partitions table for volume on %s' % mnt_point)
    node.put_file(path, script_src % mnt_point)
    out = node.run('source %s' % path)

    partition_table = out[0].strip("\n").splitlines()[-4:]
    LOG.debug('Created partitions table for volume:\n%s' % "\n".join(partition_table))
    assert all(line.startswith('/dev/') for line in partition_table), \
        "Create volume partitions failed: %s" % out[1]
    LOG.info('Partitions table for volume was successfully created')


@step(r"I trigger snapshot creation from volume for '([\W\w]+)' on role")
def create_volume_snapshot(step, mnt_point):
    device = world.get_storage_device_by_mnt_point(mnt_point)[0]
    LOG.info('Launch volume: "%s" snapshot creation' % device['storageId'])
    kwargs = dict(
        cloud_location=CONF.platforms[CONF.feature.platform]['location'],
        volume_id=device['storageId']
    )
    volume_snapshot_id = IMPL.aws_tools.create_volume_snapshot(**kwargs)
    assert volume_snapshot_id, 'Volume snapshot creation failed'
    LOG.info('Volume snapshot create was started. Snapshot: %s' % volume_snapshot_id)
    setattr(world, 'volume_snapshot_id', volume_snapshot_id)


@step(r"Volume snapshot creation become completed")
def wait_voume_snapshot(step):
    def is_snapshot_completed(**kwargs):
        status = IMPL.aws_tools.snapshots_list(**kwargs)[0]['status']
        LOG.info('Wait for volume snapshot completed, actual state is: %s ' % status)
        return status == "completed"

    wait_until(
        is_snapshot_completed,
        kwargs=dict(
            location=CONF.platforms[CONF.feature.platform]['location'],
            snapshot_id=getattr(world, 'volume_snapshot_id')),
        timeout=600,
        logger=LOG)


@step(r"I add new storage from volume snapshot to role")
def add_storage_to_role(step):
    role = world.get_role()
    volume_snapshot_id = getattr(world, 'volume_snapshot_id', None)
    assert volume_snapshot_id, 'No volume snapshot found in world object'
    LOG.info('Add volume from spanshot: %s to role' % volume_snapshot_id)
    storage_settings = {'configs': [
        {
            "id": None,
            "type": "ebs",
            "fs": None,
            "settings": {
                "ebs.size": "1",
                "ebs.type": "standard",
                "ebs.snapshot": None,
                "ebs.snapshot": volume_snapshot_id},
            "mount": False,
            "reUse": False,
            "status": "",
            "rebuild": False
        }
    ]}
    role.edit(storages=storage_settings)

