__author__ = 'gigimon'

import time
import logging
import traceback
from datetime import datetime

import requests
from lettuce import world
from libcloud.compute.types import NodeState
from revizor2.defaults import USE_SYSTEMCTL

try:
    import winrm
except ImportError:
    raise ImportError("Please install WinRM")

from revizor2.api import Server
from revizor2.conf import CONF
from revizor2.fixtures import resources
from revizor2.consts import ServerStatus, MessageStatus, Dist, Platform

from revizor2.exceptions import ScalarizrLogError, ServerTerminated, \
    ServerFailed, TimeoutError, \
    MessageNotFounded, MessageFailed,\
    EventNotFounded, OSFamilyValueFailed

from revizor2.helpers.jsonrpc import SzrApiServiceProxy

LOG = logging.getLogger(__name__)


SCALARIZR_LOG_IGNORE_ERRORS = [
    'boto',
    'p2p_message',
    'Caught exception reading instance data',
    'Expected list, got null. Selector: listvolumesresponse',
    'error was thrown due to the hostname format'
]

# Run powershell script as Administrator
world.PS_RUN_AS = '''powershell -NoProfile -ExecutionPolicy Bypass -Command "{command}"'''


@world.absorb
def get_windows_session(server=None, public_ip=None, password=None, timeout=None):
    time_until = time.time() + timeout if timeout else None
    username = 'Administrator'
    port = 5985
    while True:
        try:
            if server:
                server.reload()
                public_ip = server.public_ip
                password = password or server.windows_password
                if not password:
                    password = 'scalr'
            if CONF.feature.driver.is_platform_gce:
                username = 'scalr'
            elif CONF.feature.driver.is_platform_cloudstack:
                node = world.cloud.get_node(server)
                port = world.cloud.open_port(node, port)
            LOG.info('Used credentials for windows session: %s:%s %s:%s' % (public_ip, port, username, password))
            session = winrm.Session(
                'http://%s:%s/wsman' % (public_ip, port),
                auth=(username, password))
            LOG.debug('WinRm instance: %s' % session)
            return session
        except Exception as e:
            LOG.error('Got windows session error: %s' % e.message)
        if time.time() >= time_until:
            raise TimeoutError
        time.sleep(5)


@world.absorb
def run_cmd_command_until(command, server=None, public_ip=None, password=None, timeout=None):
    time_until = time.time() + timeout if timeout else None
    LOG.debug('Execute powershell command: %s' % command)
    e = None
    while True:
        console = get_windows_session(
            server=server,
            public_ip=public_ip,
            password=password,
            timeout=timeout)
        try:
            res = console.run_cmd(command)
            LOG.debug('std_out: %s. std_err: %s' % (res.std_out, res.std_err))
            return res
        except Exception as e:
            LOG.error('Got an error while try execute command: "%s" ErrorMsg "%s"' % (command, e.message or str(e)))
        if time.time() >= time_until:
            if e:
                LOG.error('Last error on cmd execution: "%s"' % str(e))
            raise TimeoutError('Command: %s execution failed by timeout' % command)
        time.sleep(30)


@world.absorb
def run_cmd_command(server, command):
    console = get_windows_session(server)
    LOG.info('Run command: %s in server %s' % (command, server.id))
    out = console.run_cmd(command)
    LOG.debug('Result of command: %s\n%s' % (out.std_out, out.std_err))
    if not out.status_code == 0:
        raise AssertionError('Command: "%s" exit with status code: %s and stdout: %s\n stderr:%s' % (command, out.status_code, out.std_out, out.std_err))
    return out


@world.absorb
def verify_scalarizr_log(node, log_type='debug', windows=False, server=None):
    if isinstance(node, Server):
        node = world.cloud.get_node(node)
    LOG.info('Verify scalarizr log in server: %s' % node.id)
    try:
        if windows:
            log_out = run_cmd_command(server, "findstr /c:\"\- ERROR\" \"C:\Program Files\Scalarizr\\var\log\scalarizr_%s.log\"" % log_type)
            if 'FINDSTR: Cannot open' in log_out.std_err:
                log_out = run_cmd_command(server, "findstr /c:\"\- ERROR\" \"C:\opt\scalarizr\\var\log\scalarizr_%s.log\"" % log_type)
            log_out = log_out.std_out
            LOG.debug('Findstr result: %s' % log_out)
        else:
            log_out = (node.run('grep "\- ERROR" /var/log/scalarizr_%s.log' % log_type))[0]
            LOG.debug('Grep result: %s' % log_out)
    except BaseException, e:
        LOG.error('Can\'t connect to server: %s' % e)
        LOG.error(traceback.format_exc())
        return
    for line in log_out.splitlines():
        ignore = False
        LOG.debug('Verify line "%s" for errors' % line)
        log_date = None
        log_level = None
        now = datetime.now()
        try:
            log_date = datetime.strptime(line.split()[0], '%Y-%m-%d')
            log_level = line.strip().split()[3]
        except (ValueError, IndexError):
            pass

        if log_date:
            if not log_date.year == now.year \
                or not log_date.month == now.month \
                or not log_date.day == now.day:
                continue

        for error in SCALARIZR_LOG_IGNORE_ERRORS:
            LOG.debug('Check ignore error word in error line: %s' % error)
            if error in line:
                LOG.debug('Ignore this error line: %s' % line)
                ignore = True
        if ignore:
            continue

        if log_level == 'ERROR':
            LOG.error('Found ERROR in scalarizr_%s.log:\n %s' % (log_type, line))
            raise ScalarizrLogError('Error in scalarizr_%s.log on server %s\nErrors: %s' % (log_type, node.id, log_out))


@world.absorb
def wait_server_bootstrapping(role=None, status=ServerStatus.RUNNING, timeout=2100, server=None):
    """
    Wait a moment when new server starting in the pointed role and wait server will in selected state.
    Moreover this function remember all previous started servers.

    :param class:Role role: Show in which role lookup a new server
    :return class:Server: Return a new Server
    """
    status = ServerStatus.from_code(status)

    LOG.info('Launch process looking for new server in farm %s for role %s, wait status %s' %
             (world.farm.id, role, status))

    previous_servers = getattr(world, '_previous_servers', [])
    if not previous_servers:
        world._previous_servers = previous_servers

    LOG.debug('Previous servers: %s' % previous_servers)

    lookup_server = server or None
    lookup_node = None

    start_time = time.time()

    while time.time() - start_time < timeout:
        if not lookup_server:
            LOG.debug('Reload servers in role')
            if not role:
                world.farm.servers.reload()
                servers = world.farm.servers
            else:
                role.servers.reload()
                servers = role.servers
            for server in servers:
                LOG.debug('Work with server: %s - %s' % (server.id, server.status))
                if not server in previous_servers and server.status in [ServerStatus.PENDING_LAUNCH,
                                                                        ServerStatus.PENDING,
                                                                        ServerStatus.INIT,
                                                                        ServerStatus.RUNNING]:
                    LOG.debug('I found a server: %s' % server.id)
                    lookup_server = server
        if lookup_server:
            LOG.debug('Reload lookup_server')
            previous_state = lookup_server.status
            lookup_server.reload()

            LOG.debug('Check lookup server terminated?')
            if lookup_server.status in [ServerStatus.TERMINATED,
                                        ServerStatus.PENDING_TERMINATE,
                                        ServerStatus.MISSING] \
                and not status in [ServerStatus.TERMINATED,
                                   ServerStatus.PENDING_TERMINATE,
                                   ServerStatus.MISSING]:
                raise ServerTerminated('Server %s change status to %s (was %s)' %
                                       (lookup_server.id, lookup_server.status,
                                        previous_state))

            LOG.debug('Check lookup server launch failed')
            if lookup_server.is_launch_failed:
                failed_message = lookup_server.get_failed_status_message()
                if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK \
                and ('Can not decode json response data' in failed_message
                     or 'Cannot establish connection with CloudStack server. (Server returned nothing )' in failed_message):
                    time.sleep(90)
                    lookup_server = None
                    lookup_node = None
                    continue
                if status == ServerStatus.FAILED:
                    LOG.debug('Return server because we wait a failed state')
                    return lookup_server
                raise ServerFailed('Server %s failed in %s. Reason: %s'
                                   % (lookup_server.id, ServerStatus.PENDING_LAUNCH,
                                      failed_message))

            LOG.debug('Check lookup server init failed')
            if lookup_server.is_init_failed:
                if status == ServerStatus.FAILED:
                    LOG.debug('Return server because we wait a failed state')
                    return lookup_server
                raise ServerFailed('Server %s failed in %s. Failed (Why?): %s' %
                                   (lookup_server.id, ServerStatus.INIT, lookup_server.get_failed_status_message()))

            LOG.debug('Try get node')
            if not lookup_node and lookup_server.status not in [ServerStatus.PENDING_LAUNCH,
                                                                ServerStatus.PENDING_TERMINATE,
                                                                ServerStatus.TERMINATED,
                                                                ServerStatus.PENDING_SUSPEND,
                                                                ServerStatus.SUSPENDED] \
                    and CONF.feature.driver.current_cloud != Platform.AZURE:
                LOG.debug('Try to get node object for lookup server')
                lookup_node = world.cloud.get_node(lookup_server)

            LOG.debug('Verify update log in node')
            if lookup_node and lookup_server.status in ServerStatus.PENDING:
                LOG.debug('Check scalarizr update log in lookup server')
                if not Dist.is_windows_family(lookup_server.role.dist):
                    verify_scalarizr_log(lookup_node, log_type='update')
                else:
                    verify_scalarizr_log(lookup_node, log_type='update', windows=True, server=lookup_server)

            LOG.debug('Verify debug log in node')
            if lookup_node and lookup_server.status not in [ServerStatus.PENDING_LAUNCH,
                                                            ServerStatus.PENDING_TERMINATE,
                                                            ServerStatus.TERMINATED,
                                                            ServerStatus.PENDING_SUSPEND,
                                                            ServerStatus.SUSPENDED]\
                    and not status == ServerStatus.FAILED:
                LOG.debug('Check scalarizr debug log in lookup server')
                if not Dist.is_windows_family(lookup_server.role.dist):
                    verify_scalarizr_log(lookup_node)
                else:
                    verify_scalarizr_log(lookup_node, windows=True, server=lookup_server)

            LOG.debug('If server Running and we wait Initializing, return server')
            if status == ServerStatus.INIT and lookup_server.status == ServerStatus.RUNNING:
                LOG.info('We wait Initializing but server already Running')
                status = ServerStatus.RUNNING
            if status == ServerStatus.RESUMING and lookup_server.status == ServerStatus.RUNNING:
                LOG.info('We wait Resuming but server already Running')
                status = ServerStatus.RUNNING

            LOG.debug('Compare server status')
            if lookup_server.status == status:
                LOG.info('Lookup server in right status now: %s' % lookup_server.status)
                if status == ServerStatus.RUNNING:
                    LOG.debug('Insert server to previous servers')
                    previous_servers.append(lookup_server)
                LOG.debug('Return server %s' % lookup_server)
                return lookup_server
        LOG.debug('Sleep 10 seconds')
        time.sleep(10)
    else:
        if lookup_server:
            raise TimeoutError('Server %s not in state "%s" it has status: "%s"'
                               % (lookup_server.id, status, lookup_server.status))
        raise TimeoutError('New server in role "%s" was not founding' % role)



@world.absorb
def wait_servers_running(role, count):
    role.servers.reload()
    previous_servers = getattr(world, '_previous_servers', [])
    run_count = 0
    for server in role.servers:
        if server.status == ServerStatus.RUNNING:
            LOG.info('Server %s is Running' % server.id)
            if not server in previous_servers:
                previous_servers.append(server)
            run_count += 1
    if int(count) == run_count:
        LOG.info('Servers in running state are %s' % run_count)
        world._previous_servers = previous_servers
        return True
    return False


@world.absorb
def wait_farm_terminated(*args, **kwargs):
    world.farm.servers.reload()
    for server in world.farm.servers:
        if server.status == ServerStatus.TERMINATED:
            continue
        else:
            return False
    return True


@world.absorb
def wait_server_message(server, message_name, message_type='out', find_in_all=False, timeout=600):
    """
    Wait message in server list (or one server). If find_in_all is True, wait this message in all
    servers.
    """
    def check_message_in_server(server, message_name, message_type):
        server.messages.reload()
        lookup_messages = getattr(world,
                                  '_server_%s_lookup_messages' % server.id, [])
        for message in reversed(server.messages):
            LOG.debug('Work with message: %s / %s - %s (%s) on server %s ' %
                      (message.type, message.name, message.delivered, message.id, server.id))
            if message.id in lookup_messages:
                LOG.debug('Message %s was already lookuped' % message.id)
                continue
            if message.name == message_name and message.type == message_type:
                LOG.info('This message matching the our pattern')
                if message.delivered:
                    LOG.info('Lookup message delivered')
                    lookup_messages.append(message.id)
                    setattr(world, '_server_%s_lookup_messages' % server.id,
                            lookup_messages)
                    return True
                elif message.status == MessageStatus.FAILED:
                    lookup_messages.append(message.id)
                    setattr(world, '_server_%s_lookup_messages' % server.id,
                            lookup_messages)
                    raise MessageFailed('Message %s / %s (%s) failed' % (message.type, message.name, message.id))
                elif message.status == MessageStatus.UNSUPPORTED:
                    raise MessageFailed('Message %s / %s (%s) unsupported' % (message.type, message.name, message.id))
        return False

    message_type = 'out' if message_type.strip() == 'sends' else 'in'

    if not isinstance(server, (list, tuple)):
        servers = [server]
    else:
        servers = server

    LOG.info('Try found message %s / %s in servers %s' % (message_type, message_name, servers))

    start_time = time.time()

    delivered_servers = []

    while time.time() - start_time < timeout:
        if not find_in_all:
            for serv in servers:
                if check_message_in_server(serv, message_name, message_type):
                    return serv
        else:
            LOG.debug('Delivered servers = %s, servers = %s' % (delivered_servers, servers))
            if delivered_servers == servers:
                LOG.info('All servers (%s) has delivered message: %s / %s' % (servers, message_type, message_name))
                return True
            LOG.debug('Find message in all servers')
            for serv in servers:
                if serv in delivered_servers:
                    continue
                result = check_message_in_server(serv, message_name, message_type)
                if result:
                    LOG.info('Message %s delivered in server %s (in mass delivering mode)' % (message_name, serv.id))
                    delivered_servers.append(serv)
                    LOG.debug('Message delivered to servers: %s' % [s.id for s in delivered_servers])
        time.sleep(5)
    else:
        raise MessageNotFounded('%s / %s was not finding in servers: %s' % (message_type,
                                                                            message_name,
                                                                            [s.id for s in servers]))


@world.absorb
def is_events_fired(server, events_type):
    events_fired = False
    server.events.reload()
    server_events = [e.type.lower() for e in reversed(server.events)]
    LOG.debug('Server %s events list: %s' % (server.id, server_events))
    if all(e.lower() in server_events for e in events_type.split(',')):
        LOG.debug('"%s" events were fired by %s.' % (events_type, server.id))
        events_fired =  True
    return events_fired


@world.absorb
def wait_script_execute(server, message, state):
    #TODO: Rewrite this as expect server bootstrapping
    LOG.info('Find message %s and state %s in scripting logs' % (message, state))
    server.scriptlogs.reload()
    for log in server.scriptlogs:
        if message in log.message and state == log.event:
            return True
    return False


@world.absorb
def get_hostname(server):
    serv = world.cloud.get_node(server)
    for i in range(3):
        out = serv.run('/bin/hostname')
        if out[0].strip():
            return out[0].strip()
        time.sleep(5)
    raise AssertionError('Can\'t get hostname from server: %s' % server.id)


@world.absorb
def get_hostname_by_server_format(server):
    if CONF.feature.dist.startswith('win'):
        return "%s-%s" % (world.farm.name.replace(' ', '-'), server.index)
    else:
        return '%s-%s-%s' % (
            world.farm.name.replace(' ', '-'),
            server.role.name,
            server.index
        )


@world.absorb
def wait_upstream_in_config(node, ip, contain=True):
    out = node.run('cat /etc/nginx/app-servers.include')
    if contain:
        if ip in "".join([str(i) for i in out]):
            return True
        else:
            return False
    else:
        if not ip in "".join([str(i) for i in out]):
            return True
        else:
            return False


@world.absorb
def check_index_page(node, proto, revert, domain_name, name):
    #TODO: Rewrite this
    index = resources('html/index_test.php')
    index = index.get() % {'id': name}
    url = '%s://%s/' % (proto, domain_name)
    nodes = node if isinstance(node, (list, tuple)) else [node]
    for n in nodes:
        LOG.debug('Upload index page %s to server %s' % (name, n.id))
        n.run('mkdir -p /var/www/%s' % name)
        n.put_file(path='/var/www/%s/index.php' % name, content=index)
    for i in range(10):
        LOG.info('Try get index from URL: %s, attempt %s ' % (url, i+1))
        try:
            resp = requests.get(url, timeout=30, verify=False)
            break
        except Exception, e:
            LOG.warning("Error in openning page '%s': %s" % (url, e))
            time.sleep(15)
    else:
        raise AssertionError("Can't get index page: %s" % url)
    if ('VHost %s added' % name in resp.text) or (revert and resp.status_code == 200):
        return True
    raise AssertionError('Index page not valid: %s. Status code: %s' % (resp.text, resp.status_code))


@world.absorb
def wait_rabbitmq_cp(*args, **kwargs):
    detail = world.farm.rabbitmq_cp_detail
    if not detail or not 'password' in detail:
        return False
    else:
        return detail


@world.absorb
def wait_rabbitmq_cp_url(*args, **kwargs):
    detail = world.farm.rabbitmq_cp_detail
    if not detail or not 'url' in detail:
        return False
    else:
        return detail


@world.absorb
def check_text_in_scalarizr_log(node, text):
    out = node.run('cat /var/log/scalarizr_debug.log | grep "%s"' % text)[0]
    if text in out:
        return True
    return False


@world.absorb
def set_iptables_rule(server, port):
    """Insert iptables rule in the top of the list (str, str, list||tuple)->"""
    LOG.info('Insert iptables rule to server %s for opening port %s' % (server, port))
    node = world.cloud.get_node(server)
    my_ip = world.get_external_local_ip()
    LOG.info('My IP address: %s' % my_ip)
    if isinstance(port, (tuple, list)):
        if len(port) == 2:
            port = ':'.join(str(x) for x in port)
        else:
            port = ','.join(str(x) for x in port)
    node.run('iptables -I INPUT -p tcp -s %s --dport %s -j ACCEPT' % (my_ip, port))


@world.absorb
def kill_process_by_name(server, process):
    """Kill process on remote host by his name (server(obj),str)->None if success"""
    LOG.info('Kill %s process on remote host %s' % (process, server.public_ip))
    return world.cloud.get_node(server).run("pgrep -l %(process)s | awk {print'$1'} | xargs -i{}  kill {} && sleep 5 && pgrep -l %(process)s | awk {print'$1'}" % {'process': process})[0]


@world.absorb
def change_service_status(server, service, status, use_api=False, change_pid=False):
    """change_service_status(status, service, server) Change process status on remote host by his name
    Return pid before change status, pid after change status, exit code

    :type   status: str
    :param  status: Service status start, stop, restart, etc or api methods service_restart

    :type   service: dict
    :param  service: {node: name, api: name}, Service node name - scalarizr, apache2, etc...,
                     service api endpoint name apache, etc...

    :type   server: obj
    :param  server: Server object

    :type   use_api:   bool
    :param  use_api:   Status is api call or node command

    :type   change_pid:   bool
    :param  change_pid:   Status is changed pid for node service
    """
    #Init params
    node = world.cloud.get_node(server)

    #Change process status by calling api method or service command
    def change_status():
        if use_api:
            api = SzrApiServiceProxy(server.public_ip, str(server.details['scalarizr.key']))
            #Change process status by calling api call
            try:
                return getattr(getattr(api, service['api']), status)()
            except Exception as e:
                error_msg = """An error occurred while trying to execute a command %(command)s.
                               Original error: %(error)s""" % {
                    'error': e,
                    'command': '%s.%s()' % (service['api'], status)
                }
                LOG.error(error_msg)
                raise Exception(error_msg)
        else:
            #Change process status by  calling command service
            if USE_SYSTEMCTL:
                cmd = "systemctl {status} {process} && sleep 3"
            else:
                cmd = "service {process} {status} && sleep 3"
            return node.run(cmd.format(
                process=service['node'],
                status=status))

    #Get process pid
    def get_pid():
        return node.run("pgrep -l %(process)s | awk {print'$1'} && sleep 5" %
                        {'process': service['node']})[0].rstrip('\n').split('\n')

    #Change status and get pid
    return {
        'pid_before': get_pid() if change_pid else [''],
        'info': change_status(),
        'pid_after': get_pid()
    }

@world.absorb
def is_log_rotate(server, process, rights, group=None):
    """Checks for logrotate config file and rotates the log. Returns the status of the operation."""
    if not group:
        group = ['nogroup', process]
    elif isinstance(group, str):
        group = [group, process]
    LOG.info('Loking for config file:  %s-logrotate on remote host %s' % (process, server.public_ip))
    node = world.cloud.get_node(server)
    logrotate_conf = node.run('cat /etc/logrotate.d/%s-logrotate' % process)
    if not logrotate_conf[1]:
        logrotate_param = {}
        #Get the directory from the first line config file
        logrotate_param['dir'] = '/'.join(logrotate_conf[0].split('\n')[0].split('/')[0:-1])
        #Check the archive log files
        logrotate_param['compress'] = 'compress' in logrotate_conf[0]
        #Get the log file mask from the first line config
        logrotate_param['log_mask'] = logrotate_conf[0].split('\n')[0].split('/')[-1].rstrip('.log {')
        #Performing rotation and receive a list of log files
        LOG.info('Performing rotation and receive a list of log files for % remote host %s' % (process, server.public_ip))
        rotated_logs = node.run('logrotate -f /etc/logrotate.d/%s-logrotate && stat --format="%%n %%U %%G %%a"  %s/%s' %
                                (process, logrotate_param['dir'], logrotate_param['log_mask']))
        if not rotated_logs[2]:
            try:
                log_files = []
                for str in rotated_logs[0].rstrip('\n').split('\n'):
                    tmp_str = str.split()
                    log_files.append(dict([['rights', tmp_str[3]], ['user', tmp_str[1]], ['group', tmp_str[2]],  ['file', tmp_str[0]]]))
                    has_gz = False
                for log_file_atr in log_files:
                    if log_file_atr['file'].split('.')[-1] == 'gz' and not has_gz:
                        has_gz = True
                    if not (log_file_atr['rights'] == rights and
                                    log_file_atr['user'] == process and
                                    log_file_atr['group'] in group):
                        raise AssertionError("%(file)s file attributes are not correct. Wrong attributes %(atr)s: " %
                                             {'file': log_file_atr['file'], 'atr': (log_file_atr['rights'],
                                                                                    log_file_atr['user'],
                                                                                    log_file_atr['group'])})
                if logrotate_param['compress'] and not has_gz:
                    raise AssertionError('Logrotate config file has attribute "compress", but not gz find.')
            except IndexError, e:
                raise Exception('Error occurred at get list of log files: %s' % e)
        else:
            raise AssertionError("Can't logrotate to force the rotation. Error message:%s" % logrotate_conf[1])
    else:
        raise AssertionError("Can't get config file:%s-logrotate. Error message:%s" %
                             (process, logrotate_conf[1]))
    return True

@world.absorb
def value_for_os_family(debian, centos, server=None, node=None):
    if server:
        # Get node by server
        node = world.cloud.get_node(server)
    elif not node:
        raise AttributeError("Not enough required arguments: server and node both can't be empty")
    # Get node os name
    node_os = getattr(node, 'os', [''])[0]
    # Get os family result
    os_family_res =  dict(debian=debian, centos=centos).get(Dist.get_os_family(node_os))
    if not os_family_res:
        raise OSFamilyValueFailed('No value for node os: %s' % node_os)
    return os_family_res

@world.absorb
def get_service_paths(service_name, server=None, node=None, service_conf=None, service_conf_base_path=None):
    if server:
        node = world.cloud.get_node(server)
    elif not node:
        raise AttributeError("Not enough required arguments: server and node both can't be empty")
    # Get service path
    service_path = node.run('which %s' % service_name)
    if service_path[2]:
        raise AssertionError("Can't get %s service path: %s" % (service_name, service_path))
    service_path = dict(bin=service_path[0].split()[0], conf='')
    # Get service config path
    if service_conf:
        base_path = service_conf_base_path or '/etc'
        service_conf_path = node.run('find %s -type f -name "%s" -print' % (base_path, service_conf))
        if service_conf_path[2]:
            raise AssertionError("Can't find service %s configs : %s" % (service_name, service_conf_path))
        service_path.update({'conf': service_conf_path[0].split()[0]})
    return service_path
