import time
import copy
import logging
from datetime import datetime
from threading import Thread

from lettuce import world, step

from revizor2.conf import CONF
from revizor2.api import Script, IMPL, Server
from revizor2.utils import wait_until
from revizor2.consts import ServerStatus, Platform
from revizor2.exceptions import MessageFailed
from revizor2.helpers import install_behaviors_on_node

LOG = logging.getLogger(__name__)

COOKBOOKS_BEHAVIOR = {
    'app': 'apache2',
    'www': 'nginx',
    'mysql': 'mysql::server',
    'mysql2': 'mysql::server'

}

BEHAVIOR_SETS = {
    'base': ['base'],
    'mbeh1': ['apache2', 'mysql::server', 'redis', 'postgresql', 'haproxy'],
    'mbeh2': ['nginx', 'percona', 'tomcat', 'memcached']
}


@step('I expect (?:new\s)*server bootstrapping as ([\w\d]+)(?: in (.+) role)?$')
def expect_server_bootstraping_for_role(step, serv_as, role_type, timeout=1800):
    """Expect server bootstrapping to 'Running' and check every 10 seconds scalarizr log for ERRORs and Traceback"""
    role = world.get_role(role_type) if role_type else None
    platform = CONF.feature.platform
    if (platform.is_cloudstack or platform.is_openstack or platform.is_azure):
        timeout = 3000
    LOG.info('Expect server bootstrapping as %s for %s role' % (serv_as,
                                                                role_type))
    server = world.wait_server_bootstrapping(role, ServerStatus.RUNNING,
                                             timeout=timeout)
    setattr(world, serv_as, server)


@step('I see (.+) server (.+)$')
def waiting_for_assertion(step, state, serv_as, timeout=1400):
    role = world.get_role()
    server = world.wait_server_bootstrapping(role, state, timeout)
    setattr(world, serv_as, server)
    LOG.info('Server %s (%s) succesfully in %s state' % (server.id, serv_as, state))


@step('I wait and see (?:[\w]+\s)*([\w]+) server ([\w\d]+)$')
def waiting_server(step, state, serv_as, timeout=1400):
    if CONF.feature.dist.is_windows or CONF.feature.platform.is_azure:
        timeout = 2400
    role = world.get_role()
    server = world.wait_server_bootstrapping(role, state, timeout)
    LOG.info('Server succesfully %s' % state)
    setattr(world, serv_as, server)


@step('I wait server ([\w\d]+) in ([ \w]+) state')
def wait_server_state(step, serv_as, state):
    """
    Wait old server in selected state
    """
    server = getattr(world, serv_as, None)
    if not server:
        LOG.info('Wait new server %s in state %s' % (serv_as, state))
        server = world.wait_server_bootstrapping(status=ServerStatus.from_code(state))
        setattr(world, serv_as, server)
    else:
        LOG.info('Wait server %s in state %s' % (server.id, state))
        world.wait_server_bootstrapping(status=ServerStatus.from_code(state),
                                        server=server)


@step(r'server ([\w\d]+) hasn\'t changed its status in (\d+) minutes')
def server_state_not_changed(step, serv_as, minutes):
    server = getattr(world, serv_as)
    server.reload()
    status_before = server.status
    for _ in range(int(minutes)):
        time.sleep(60)
        server.reload()
        if server.status != status_before:
            raise AssertionError("Server %s change status '%s' -> '%s'" % server.id, status_before, server.status)


@step(r'I( force)? terminate(?: server)? ([\w\d]+)( with decrease)?$')
def terminate_server_decrease(step, force, serv_as, decrease=False):
    """Terminate server (no force) with/without decrease"""
    server = getattr(world, serv_as)
    decrease = bool(decrease)
    force = bool(force)
    LOG.info('Terminate server %s, decrease %s' % (server.id, decrease))
    server.terminate(force=force, decrease=decrease)


@step('I create server snapshot for ([\w]+)$')
def rebundle_server(step, serv_as):
    """Start rebundle for server"""
    server = getattr(world, serv_as)
    name = 'tmp-%s-%s' % (server.role.name, datetime.now().strftime('%m%d%H%M'))
    bundle_id = server.create_snapshot(name)
    if bundle_id:
        world.bundle_id = bundle_id


@step('I (reboot|suspend|resume)(?: (soft|hard))? server ([\w\d]+)$')
def server_state_action(step, action, reboot_type, serv_as):
    server = getattr(world, serv_as)
    LOG.info('%s server %s' % (action.capitalize(), server.id))
    args = {'method': reboot_type.strip() if reboot_type else 'soft'}
    meth = getattr(server, action)
    res = meth(**args) if action == 'reboot' else meth()
    error_message = None
    if isinstance(res, bool) and not res:
        error_message = "% success: %s" % (action, res)
    elif isinstance(res, dict):
        error_message = res.get('errorMessage', None)
    # Workaround for SCALRCORE-1576
    if error_message == [
        u'Unable to perform request to scalarizr: A server error occurred.  Please contact the administrator. (500)']:
        error_message = None
    assert not error_message, error_message
    LOG.info('Server %s was %sed' % (server.id, action))


@step('Scalr ([^ .]+) ([^ .]+) (?:to|from) ([^ .]+)( with fail)?( without saving to the database)?')
def assert_server_message(step, msgtype, msg, serv_as, failed=False, unstored_message=None, timeout=1500):
    """Check scalr in/out message delivering"""
    LOG.info('Check message %s %s server %s' % (msg, msgtype, serv_as))
    find_message = getattr(world, 'wait_unstored_message' if unstored_message else 'wait_server_message')
    if serv_as == 'all':
        world.farm.servers.reload()
        servers = [serv for serv in world.farm.servers if serv.status == ServerStatus.RUNNING]
        find_message(servers, msg.strip(), msgtype, find_in_all=True, timeout=timeout)
    else:
        try:
            LOG.info('Try get server %s in world' % serv_as)
            server = getattr(world, serv_as)
        except AttributeError as e:
            LOG.debug('Error in server found message: %s' % e)
            world.farm.servers.reload()
            server = [serv for serv in world.farm.servers if serv.status == ServerStatus.RUNNING]
        LOG.info('Wait message %s / %s in servers: %s' % (msgtype, msg.strip(), server))
        try:
            s = find_message(server, msg.strip(), msgtype, timeout=timeout)
            setattr(world, serv_as, s)
        except MessageFailed:
            if not failed:
                raise


@step(r'(?:\s)([\w\W]+) event was fired by ([\w\d]+)')
def assert_server_event(step, events_type, serv_as):
    server = getattr(world, serv_as)
    LOG.info('Check "%s" events were fired  by %s' % (events_type, server.id))
    err_msg = '"%s" events were not fired by %s' % (events_type, server.id)
    wait_until(
        world.is_events_fired,
        args=(server, events_type),
        timeout=300,
        logger=LOG,
        error_text=err_msg)


@step(r'(?:[\w]+) ([\w\W]+) events were not fired after ([\w\d]+) resume')
def assert_server_event_again_fired(step, events, serv_as):
    server = getattr(world, serv_as)
    server.events.reload()
    LOG.info('Check "%s" events were not again fired by %s' % (events, server.id))
    server_events = [e.type.lower() for e in reversed(server.events)]
    LOG.debug('Server %s events list: %s' % (server.id, server_events))
    duplicated_server_events = set([e for e in server_events if server_events.count(e) > 1])
    LOG.debug('Server %s duplicated events list: %s' % (server.id, duplicated_server_events))
    assert not any(e.lower() in duplicated_server_events for e in events.split(',')), \
        'Some events from %s were fired by %s more than one time' % (events, server.id)


@step("I execute( local)? script '(.+)' (.+) on (.+)")
def execute_script(step, local, script_name, exec_type, serv_as):
    synchronous = 1 if exec_type.strip() == 'synchronous' else 0
    path = None
    server = getattr(world, serv_as)
    if local:
        path = script_name
        script_id = None
    else:
        script_id = Script.get_id(script_name)['id']
    LOG.info('Execute script "%s" with id: %s' % (script_name, script_id))
    server.scriptlogs.reload()
    setattr(world, '_server_%s_last_scripts' % server.id, copy.deepcopy(server.scriptlogs))
    setattr(world, '_server_%s_last_script_name' % server.id, script_name)
    Script.script_execute(world.farm.id, server.farm_role_id, server.id, script_id, synchronous, path=path)
    LOG.info('Script executed success')


@step(r"I execute '([\w\W]+)?' '([\w\W]+)' '([\w]+)' on ([\w\d]+)")
def script_executing(step, script_type, script_name, execute_type, serv_as):
    if script_type:
        script_type = ' %s ' % script_type.strip()
    else:
        script_type = ' '
    external_step = "I execute{script_type}script '{script_name}' {execute_type} on {server}".format(
        script_type=script_type,
        script_name=script_name,
        execute_type=execute_type,
        server=serv_as)
    LOG.debug('Run external step: %s' % external_step)
    step.when(external_step)


@step('I see script result in (.+)')
def assert_check_script_work(step, serv_as):
    server = getattr(world, serv_as)
    script_name = getattr(world, '_server_%s_last_script_name' % server.id)
    world.check_script_executed(name=script_name,
                                serv_as=serv_as,
                                new_only=True,
                                timeout=600)


@step('wait all servers are ([\w]+)$')
def wait_for_servers_state(step, state):
    """Wait for state of all servers"""
    wait_until(world.farm_servers_state, args=(
        state, ), timeout=1800, error_text=('Servers in farm have no status %s' % state))


@step('hostname in ([\w\d]+) is valid$')
def verify_hostname_is_valid(step, serv_as):
    server = getattr(world, serv_as)
    hostname = server.api.system.get_hostname()
    valid_hostname = world.get_hostname_by_server_format(server)
    if not hostname.lower() == valid_hostname.lower():
        raise AssertionError('Hostname in server %s is not valid: %s (%s)' % (server.id, valid_hostname, hostname))


@step('not ERROR in ([\w]+) scalarizr(?: (debug|update))? log$')
def check_scalarizr_log(step, serv_as, log_type=None):
    """Check scalarizr log for errors"""
    log_type = log_type or 'debug'
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    if CONF.feature.dist.is_windows:
        world.verify_scalarizr_log(node, windows=True, server=server, log_type=log_type)
    else:
        world.verify_scalarizr_log(node, log_type=log_type)


@step('scalarizr process is (.+) in (.+)$')
def check_processes(step, count, serv_as):
    time.sleep(60)
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    list_proc = node.run("pgrep -l scalarizr | awk {print'$1'}")[0]
    LOG.info('Scalarizr count of processes %s' % len(list_proc.strip().splitlines()))
    world.assert_not_equal(len(list_proc.strip().splitlines()), int(count),
                           'Scalarizr processes is: %s but processes \n%s' % (
                           len(list_proc.strip().splitlines()), list_proc))


@step("file '(.+)' not contain '(.+)' in ([\w\d]+)")
def verify_string_in_file(step, file_path, value, serv_as):
    server = getattr(world, serv_as)
    LOG.info('Verify file "%s" in %s not contain "%s"' % (file_path, server.id, value))
    node = world.cloud.get_node(server)
    out = node.run('cat %s | grep %s' % (file_path, value))
    if out[0].strip():
        raise AssertionError('File %s contain: %s. Result of grep: %s' % (file_path, value, out[0]))


@step(r'I have a ([\w\d]+) attached volume as ([\w\d]+)')
@world.run_only_if(storage='persistent', platform=[Platform.EC2])
def save_attached_volume_id(step, serv_as, volume_as):
    server = getattr(world, serv_as)
    attached_volume = None
    node = world.cloud.get_node(server)
    platfrom = CONF.feature.platform
    if platform.is_ec2:
        volumes = server.get_volumes()
        if not volumes:
            raise AssertionError('Server %s doesn\'t has attached volumes!' %
                                 (server.id))
        attached_volume = filter(lambda x:
                                 x.extra['device'] != node.extra['root_device_name'],
                                 volumes)[0]
    elif platform.is_gce:
        volumes = filter(lambda x: x['deviceName'] != 'root',
                         node.extra.get('disks', []))
        if not volumes:
            raise AssertionError('Server %s doesn\'t has attached volumes!' %
                                 server.id)
        elif len(volumes) > 1:
            raise AssertionError('Server %s has a more 1 attached disks!' %
                                 server.id)
        attached_volume = filter(lambda x: x.name == volumes[0]['deviceName'],
                                 world.cloud.list_volumes())[0]
    elif platform.is_cloudstack:
        volumes = server.get_volumes()
        if len(volumes) == 1:
            raise AssertionError('Server %s doesn\'t has attached volumes!' %
                                 (server.id))
        attached_volume = filter(lambda x:
                                 x.extra['volume_type'] != 'ROOT',
                                 volumes)[0]
    setattr(world, '%s_volume' % volume_as, attached_volume)
    LOG.info('Attached volume for server "%s" is "%s"' %
             (server.id, attached_volume.id))


@step(r'attached volume ([\w\d]+) has size (\d+) Gb')
@world.run_only_if(storage='persistent', platform=[Platform.EC2])
def verify_attached_volume_size(step, volume_as, size):
    LOG.info('Verify attached volume has new size "%s"' % size)
    size = int(size)
    volume = getattr(world, '%s_volume' % volume_as)
    volume_size = int(volume.size)
    if CONF.feature.platform.is_cloudstack:
        volume_size = volume_size / 1024 / 1024 / 1024
    if not size == volume_size:
        raise AssertionError('VolumeId "%s" has size "%s" but must be "%s"'
                             % (volume.id, volume.size, size))


@step('connection with scalarizr was established')
def is_scalarizr_connected(step, timeout=1400):
    LOG.info('Establish connection with scalarizr.')
    #Whait outbound request from scalarizr
    res = wait_until(
        IMPL.bundle.check_scalarizr_connection,
        args=(world.server.id, ),
        timeout=timeout,
        error_text="Time out error. Can't establish connection with scalarizr.")
    if res.get('failure_reason'):
        raise AssertionError("Bundle task {id} failed. Error: {msg}".format(
            id=res['id'],
            msg=res['failure_reason']))
    world.bundle_task = res
    if not res['behaviors']:
        world.bundle_task.update({'behaviors': ['base']})
    elif 'base' not in res['behaviors']:
        world.bundle_task.update({'behaviors': ','.join((','.join(res['behaviors']), 'base')).split(',')})
    else:
        world.bundle_task.update({'behaviors': res['behaviors']})
    LOG.info('Connection with scalarizr was established. Received the following behaviors: %s' % world.bundle_task['behaviors'])


@step(r'I initiate the installation (\w+ )?behaviors on the server')
@world.run_only_if(dist=['!coreos'])
def install_behaviors(step, behavior_set=None):
    #Set recipes
    cookbooks = []
    if behavior_set:
        cookbooks = BEHAVIOR_SETS[behavior_set.strip()]
        if CONF.feature.dist.id in ['ubuntu-16-04', 'centos-7-x'] and behavior_set.strip() == 'mbeh1':
            cookbooks.remove('mysql::server')
        elif CONF.feature.dist.id == 'ubuntu-16-04' and behavior_set.strip() == 'mbeh2':
            cookbooks.remove('percona')
        installed_behaviors = []
        for c in cookbooks:
            match = [key for key, value in COOKBOOKS_BEHAVIOR.items() if c == value]
            installed_behaviors.append(match[0]) if match else installed_behaviors.append(c)
        setattr(world, 'installed_behaviors', installed_behaviors)
    else:
        for behavior in CONF.feature.behaviors:
            if behavior in cookbooks:
                continue
            cookbooks.append(COOKBOOKS_BEHAVIOR.get(behavior, behavior))
    LOG.info('Initiate the installation behaviors on the server: %s' %
             world.cloud_server.name)
    install_behaviors_on_node(world.cloud_server, cookbooks,
                              CONF.feature.platform.name,
                              branch=CONF.feature.branch)


@step('I trigger the Create role')
def create_role(step):
    kwargs = dict(
        server_id=world.server.id,
        bundle_task_id=world.bundle_task['id'],
        os_id=world.bundle_task['os'][0]['id']
    )
    if CONF.feature.dist.is_windows:
        kwargs.update({'behaviors': 'chef'})
    elif all(behavior in world.bundle_task['behaviors'] for behavior in CONF.feature.behaviors):
        kwargs.update({'behaviors': ','.join(CONF.feature.behaviors)})
    else:
        raise AssertionError(
            'Transmitted behavior: %s, not in the list received from the server' % CONF.feature.behaviors)

    if not IMPL.bundle.create_role(**kwargs):
        raise AssertionError('Create role initi`alization is failed.')


@step('I trigger the Start building and run scalarizr')
def start_building(step):
    platform = CONF.feature.platform
    LOG.info('Initiate Start building')
    time.sleep(180)
    #Emulation pressing the 'Start building' key on the form 'Create role from
    #Get CloudServerId, Command to run scalarizr
    if platform.is_gce:
        server_id = world.cloud_server.name
    else:
        server_id = world.cloud_server.id
    res = IMPL.bundle.import_start(platform=platform.name,
                                   location=platform.location,
                                   cloud_id=server_id,
                                   name='test-import-%s' % datetime.now().strftime('%m%d-%H%M'))
    if not res:
        raise AssertionError("The import process was not started. Scalarizr run command was not received.")
    LOG.info('Start scalarizr on remote host. ServerId is: %s' % res['server_id'])
    LOG.info('Scalarizr run command is: %s' % res['scalarizr_run_command'])
    world.server = Server(**{'id': res['server_id']})

    #Run screen om remote host in "detached" mode (-d -m This creates a new session but doesn't  attach  to  it)
    #and then run scalari4zr on new screen
    if CONF.feature.dist.is_windows:
        password = 'Scalrtest123'
        console = world.get_windows_session(public_ip=world.cloud_server.public_ips[0], password=password)
        def call_in_background(command):
            try:
                console.run_cmd(command)
            except:
                pass
        t1 = Thread(target=call_in_background, args=(res['scalarizr_run_command'],))
        t1.start()
    else:
        world.cloud_server.run('screen -d -m %s &' % res['scalarizr_run_command'])

@step(r'I install Chef on server')
@world.run_only_if(dist=['!coreos'])
def install_chef(step):
    node = getattr(world, 'cloud_server', None)
    if CONF.feature.dist.is_windows:
        password = 'Scalrtest123'
        console = world.get_windows_session(public_ip=node.public_ips[0], password=password)
        #TODO: Change to installation via Fatmouse task
        # command = "msiexec /i https://opscode-omnibus-packages.s3.amazonaws.com/windows/2008r2/i386/chef-client-12.5.1-1-x86.msi /passive"
        command = ". { iwr -useb https://omnitruck.chef.io/install.ps1 } | iex; install -version 12.19.36"
        console.run_ps(command)
        chef_version = console.run_cmd("chef-client --version")
        assert chef_version.std_out, "Chef was not installed"
    else:
        node.run('rm -rf /tmp/chef-solo/cookbooks/*')
        command = "curl -L https://omnitruck.chef.io/install.sh | sudo bash -s -- -v 12.19.36 \
            && git clone https://github.com/Scalr/cookbooks.git /tmp/chef-solo/cookbooks"
        node.run(command)
        chef_version = node.run("chef-client --version")
        assert chef_version[2] == 0, "Chef was not installed"
