__author__ = 'gigimon'

import time
import copy
import logging
from datetime import datetime

from lettuce import world, step

from revizor2.api import Script
from revizor2.utils import wait_until
from revizor2.consts import ServerStatus


LOG = logging.getLogger(__name__)


@step('I expect server bootstrapping as ([\w\d]+)(?: in (.+) role)?$')
def expect_server_bootstraping_for_role(step, serv_as, role_type, timeout=2000):
    """Expect server bootstrapping to 'Running' and check every 10 seconds scalarizr log for ERRORs and Traceback"""
    role = world.get_role(role_type) if role_type else None
    LOG.info('Expect server bootstrapping as %s for %s role' % (serv_as, role_type))
    server = world.wait_server_bootstrapping(role, ServerStatus.RUNNING, timeout=timeout)
    setattr(world, serv_as, server)


@step('I wait server ([\w\d]+) in ([ \w]+) state')
def wait_server_state(step, serv_as, state):
    """
    Wait old server in selected state
    """
    server = getattr(world, serv_as)
    LOG.info('Wait server %s in state %s' % (server.id, state))
    world.wait_server_bootstrapping(status=ServerStatus.from_code(state), server=server)


@step(r'I( force)? terminate(?: server)? ([\w\d]+)( with decrease)?$')
def terminate_server_decrease(step, force, serv_as, decrease=False):
    """Terminate server (no force) with/without decrease"""
    server = getattr(world, serv_as)
    decrease = bool(decrease)
    force = bool(force)
    LOG.info('Terminate server %s, decrease %s' % (server.id, decrease))
    server.terminate(force=force, decrease=decrease)


@step('I (reboot|suspend|resume)(?: (soft|hard))? server ([\w\d]+)$')
def server_state_action(step, action, reboot_type, serv_as):
    server = getattr(world, serv_as)
    LOG.info('%s server %s' % (action.capitalize(), server.id))
    args = {'method': reboot_type.strip() if reboot_type else 'soft'}
    meth = getattr(server, action)
    if not meth(**args if action == 'reboot' else None):
        raise AssertionError('Server %s was not properly %s' % (server.id, action))
    LOG.info('Server %s was %sed' % (server.id, action))


@step('Scalr ([^ .]+) ([^ .]+) (?:to|from) ([^ .]+)')
def assert_server_message(step, msgtype, msg, serv_as, timeout=1500):
    """Check scalr in/out message delivering"""
    LOG.info('Check message %s %s server %s' % (msg, msgtype, serv_as))
    if serv_as == 'all':
        world.farm.servers.reload()
        server = [serv for serv in world.farm.servers if serv.status == ServerStatus.RUNNING]
        world.wait_server_message(server, msg.strip(), msgtype, find_in_all=True, timeout=timeout)
    else:
        try:
            LOG.info('Try get server %s in world' % serv_as)
            server = getattr(world, serv_as)
        except AttributeError, e:
            LOG.debug('Error in server found message: %s' % e)
            world.farm.servers.reload()
            server = [serv for serv in world.farm.servers if serv.status == ServerStatus.RUNNING]
        LOG.info('Wait message %s / %s in servers: %s' % (msgtype, msg.strip(), server))
        s = world.wait_server_message(server, msg.strip(), msgtype, timeout=timeout)
        setattr(world, serv_as, s)


@step("I execute script '(.+)' (.+) on (.+)")
def execute_script(step, script_name, exec_type, serv_as):
    synchronous = 1 if exec_type.strip() == 'synchronous' else 0
    server = getattr(world, serv_as)
    script = Script.get_id(script_name)
    LOG.info('Execute script id: %s, name: %s' % (script['id'], script_name))
    server.scriptlogs.reload()
    setattr(world, '_server_%s_last_scripts' % server.id, copy.deepcopy(server.scriptlogs))
    LOG.debug('Count of complete scriptlogs: %s' % len(server.scriptlogs))
    Script.script_execute(world.farm.id, server.farm_role_id, server.id, script['id'], synchronous, script['version'])
    LOG.info('Script executed success')


@step('wait all servers are terminated$')
def wait_all_terminated(step):
    """Wait termination of all servers"""
    wait_until(world.wait_farm_terminated, timeout=1800, error_text='Servers in farm not terminated too long')


@step('hostname in ([\w\d]+) is valid$')
def verify_hostname_is_valid(step, serv_as):
    server = getattr(world, serv_as)
    hostname = world.get_hostname(server).strip()
    valid_hostname = '%s-%s-%s'.lower().strip() % (world.farm.name.replace(' ', ''), server.role.name, server.index)
    if not hostname == valid_hostname:
        raise AssertionError('Hostname in server %s is not valid: %s (%s)' % (server.id, valid_hostname, hostname))


@step('not ERROR in ([\w]+) scalarizr log$')
def check_scalarizr_log(step, serv_as):
    """Check scalarizr log for errors"""
    node = world.cloud.get_node(getattr(world, serv_as))
    world.verify_scalarizr_log(node)


@step('scalarizr process is (.+) in (.+)$')
def check_processes(step, count, serv_as):
    time.sleep(60)
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    list_proc = node.run("pgrep -l scalarizr | awk {print'$1'}")[0]
    LOG.info('Scalarizr count of processes %s' % len(list_proc.strip().splitlines()))
    world.assert_not_equal(len(list_proc.strip().splitlines()), int(count),
                    'Scalarizr processes is: %s but processes \n%s' % (len(list_proc.strip().splitlines()), list_proc))


@step("file '(.+)' not contain '(.+)' in ([\w\d]+)")
def verify_string_in_file(step, file_path, value, serv_as):
    server = getattr(world, serv_as)
    LOG.info('Verify file "%s" in %s not contain "%s"' % (file_path, server.id, value))
    node = world.cloud.get_node(server)
    out = node.run('cat %s | grep %s' % (file_path, value))
    if out[0].strip():
        raise AssertionError('File %s contain: %s. Result of grep: %s' % (file_path, value, out[0]))
