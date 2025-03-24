import time
import logging
import traceback
from datetime import datetime
from distutils.util import strtobool
import re

import requests
from lettuce import world

try:
    import winrm
except ImportError:
    raise ImportError("Please install WinRM")

from revizor2.conf import CONF
from revizor2.api import Server
from revizor2.consts import Platform
from revizor2.fixtures import resources
from revizor2.consts import ServerStatus, MessageStatus, Dist

from revizor2.exceptions import ScalarizrLogError, ServerTerminated, \
    ServerFailed, TimeoutError, \
    MessageNotFounded, MessageFailed,\
    OSFamilyValueFailed

from revizor2.helpers.jsonrpc import SzrApiServiceProxy

LOG = logging.getLogger(__name__)


SCALARIZR_LOG_IGNORE_ERRORS = [
    'boto',
    'p2p_message',
    'Caught exception reading instance data',
    'Expected list, got null. Selector: listvolumesresponse',
    'error was thrown due to the hostname format',
    "HTTPSConnectionPool(host='my.scalr.com', port=443): Max retries exceeded",
    "Error synchronizing server time: Unable to synchronize time, cause ntpdate binary is not found in $PATH"
]

# Run powershell script as Administrator
world.PS_RUN_AS = '''powershell -NoProfile -ExecutionPolicy Bypass -Command "{command}"'''


@world.absorb
def get_windows_session(server=None, public_ip=None, password=None, timeout=None):
    platform = CONF.feature.platform
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
                    password = 'Scalrtest123'
            if platform.is_gce or platform.is_azure:
                username = 'scalr'
            elif platform.is_cloudstack and world.cloud._driver.use_port_forwarding():
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
def run_cmd_command(server, command, raise_exc=True):
    console = get_windows_session(server)
    LOG.info('Run command: %s in server %s' % (command, server.id))
    out = console.run_cmd(command)
    LOG.debug('Result of command: %s\n%s' % (out.std_out, out.std_err))
    if not out.status_code == 0 and raise_exc:
        raise AssertionError('Command: "%s" exit with status code: %s and stdout: %s\n stderr:%s' % (command, out.status_code, out.std_out, out.std_err))
    return out


@world.absorb
def verify_scalarizr_log(node, log_type='debug', windows=False, server=None):
    LOG.info('Verify scalarizr log in server: %s' % node.id)
    if server:
        server.reload()
        if not server.public_ip:
            LOG.debug('Server has no public IP yet')
            return
    else:
        if isinstance(node, Server):
            node = world.cloud.get_node(node)
        if not node.public_ips or not node.public_ips[0]:
            LOG.debug('Node has no public IP yet')
            return
    try:
        if windows:
            log_out = node.run("findstr /n \"ERROR WARNING Traceback\" \"C:\Program Files\Scalarizr\\var\log\scalarizr_%s.log\"" % log_type)
            if 'FINDSTR: Cannot open' in log_out.std_err:
                log_out = node.run("findstr /n \"ERROR WARNING Traceback\" \"C:\opt\scalarizr\\var\log\scalarizr_%s.log\"" % log_type)
            log_out = log_out.std_out
            LOG.debug('Findstr result: %s' % log_out)
        else:
            log_out = (node.run('grep -n "\- ERROR \|\- WARNING \|Traceback" /var/log/scalarizr_%s.log' % log_type)).std_out
            LOG.debug('Grep result: %s' % log_out)
    except BaseException, e:
        LOG.error('Can\'t connect to server: %s' % e)
        LOG.error(traceback.format_exc())
        return

    lines = log_out.splitlines()
    for i, line in enumerate(lines):
        ignore = False
        LOG.debug('Verify line "%s" for errors' % line)
        log_date = None
        log_level = None
        line_number = -1
        now = datetime.now()
        try:
            line_number = int(line.split(':', 1)[0])
            line = line.split(':', 1)[1]
            log_date = datetime.strptime(line.split()[0], '%Y-%m-%d')
            log_level = line.strip().split()[3]
        except (ValueError, IndexError):
            pass

        if log_date:
            if not log_date.year == now.year or \
                    not log_date.month == now.month or \
                    not log_date.day == now.day:
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

        if log_level == 'WARNING' and i < len(lines) - 1:
            if '%s:Traceback' % (line_number + 1) in lines[i+1]:
                LOG.error('Found WARNING with Traceback in scalarizr_%s.log:\n %s' % (log_type, line))
                raise ScalarizrLogError('Error in scalarizr_%s.log on server %s\nErrors: %s' % (log_type, node.id, log_out))


@world.absorb
def wait_server_bootstrapping(role=None, status=ServerStatus.RUNNING, timeout=2100, server=None):
    """
    Wait a moment when new server starting in the pointed role and wait server will in selected state.
    Moreover this function remember all previous started servers.

    :param class:Role role: Show in which role lookup a new server
    :return class:Server: Return a new Server
    """
    platform = CONF.feature.platform
    status = ServerStatus.from_code(status)

    LOG.info('Launch process looking for new server in farm %s for role %s, wait status %s' %
             (world.farm.id, role, status))

    previous_servers = getattr(world, '_previous_servers', [])
    if not previous_servers:
        world._previous_servers = previous_servers

    LOG.debug('Previous servers: %s' % previous_servers)

    lookup_server = server or None
    lookup_node = None
    azure_failed = 0

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
                err_msg = (
                    'Can not decode json response data',
                    'Cannot establish connection with CloudStack server. (Server returned nothing )'
                )
                failed_message = lookup_server.get_failed_status_message()
                if platform.is_cloudstack and any(msg in failed_message for msg in err_msg):
                    time.sleep(90)
                    lookup_server = None
                    lookup_node = None
                    continue
                # if platform.is_azure and azure_failed != 2:
                #     LOG.warning('Server %s in Azure and failed %s attempt with message: "%s"' % (
                #         lookup_server.id,
                #         azure_failed + 1,
                #         lookup_server.get_failed_status_message()))
                #     azure_failed += 1
                #     time.sleep(15)
                #     continue
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
                    and status != ServerStatus.PENDING:
                LOG.debug('Try to get node object for lookup server')
                lookup_node = world.cloud.get_node(lookup_server)

            LOG.debug('Verify update log in node')
            if lookup_node and lookup_server.status == ServerStatus.PENDING and status != ServerStatus.PENDING:
                LOG.debug('Check scalarizr update log in lookup server')
                if not Dist(lookup_server.role.dist).is_windows and not platform.is_azure:
                    verify_scalarizr_log(lookup_node, log_type='update')
                else:
                    if platform != Platform.RACKSPACENGUS:
                        verify_scalarizr_log(lookup_node, log_type='update', windows=True, server=lookup_server)

            LOG.debug('Verify debug log in node')
            if lookup_node and lookup_server.status not in [ServerStatus.PENDING_LAUNCH,
                                                            ServerStatus.PENDING_TERMINATE,
                                                            ServerStatus.TERMINATED,
                                                            ServerStatus.PENDING_SUSPEND,
                                                            ServerStatus.SUSPENDED]\
                    and not status == ServerStatus.FAILED:
                LOG.debug('Check scalarizr debug log in lookup server')
                if not Dist(lookup_server.role.dist).is_windows and not platform.is_azure:
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

            LOG.debug('Compare server status "%s" == "%s"' % (lookup_server.status, status))
            if lookup_server.status == status:
                LOG.info('Lookup server in right status now: %s' % lookup_server.status)
                if status == ServerStatus.RUNNING:
                    lookup_server.messages.reload()
                    if platform.is_azure \
                            and not Dist(lookup_server.role.dist).is_windows \
                            and not ('ResumeComplete' in map(lambda m: m.name, lookup_server.messages)) \
                            and lookup_server.is_scalarized:
                        LOG.debug('Wait update ssh authorized keys on azure %s server' % lookup_server.id)
                        wait_server_message(
                            lookup_server,
                            'UpdateSshAuthorizedKeys',
                            timeout=2400)
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
def farm_servers_state(state):
    world.farm.servers.reload()
    for server in world.farm.servers:
        if server.status == ServerStatus.from_code(state):
            LOG.info('Servers is in %s state' % state)
            continue
        else:
            return False
    return True


@world.absorb
def wait_unstored_message(servers, message_name, message_type='out', find_in_all=False, timeout=1000):
    if not isinstance(servers, (list, tuple)):
        servers = [servers]
    delivered_to = []
    message_type = 'in' if message_type.strip() in ('sends', 'out') else 'out'
    start_time = time.time()
    while time.time() - start_time < timeout:
        if delivered_to == servers:
            LOG.info('All servers has message: %s / %s' % (message_type, message_name))
            break
        for server in servers:
            if server in delivered_to:
                continue
            LOG.info('Searching message "%s/%s" on %s node' % (message_type, message_name, server.id))
            node = world.cloud.get_node(server)
            lookup_messages = getattr(world, '_server_%s_lookup_messages' % server.id, [])
            node_messages = reversed(world.get_szr_messages(node, convert=True))
            message = filter(lambda m:
                             m.name == message_name
                             and m.direction == message_type
                             and m.id not in lookup_messages
                             and strtobool(m.handled), node_messages)

            if message:
                LOG.info('Message found: %s' % message[0].id)
                lookup_messages.append(message[0].id)
                setattr(world,
                        '_server_%s_lookup_messages' % server.id,
                        lookup_messages)
                if find_in_all:
                    LOG.info('Message %s delivered to the server %s' % (message_name, server.id))
                    delivered_to.append(server)
                    continue
                return server
        time.sleep(30)
    else:
        raise MessageNotFounded('%s/%s was not finding' % (message_type, message_name))


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

    message_type = 'in' if message_type.strip() not in ('sends', 'out') else 'out'
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
def check_script_executed(serv_as,
                          name=None,
                          event=None,
                          user=None,
                          log_contains=None,
                          std_err=False,
                          exitcode=None,
                          new_only=False,
                          timeout=0):
    """
    Verifies that server scripting log contains info about script execution.
    """
    out_name = 'STDERR' if std_err else 'STDOUT'
    server = getattr(world, serv_as)
    contain = log_contains.split(';') if log_contains else []
    last_scripts = getattr(world, '_server_%s_last_scripts' % server.id) if new_only else []
    # Convert script name, because scalr converts name to:
    # substr(preg_replace("/[^A-Za-z0-9]+/", "_", $script->name), 0, 50)
    name = re.sub('[^A-Za-z0-9/.:]+', '_', name)[:50]
    if not name.startswith('http') and not name.startswith('/'):
        name = name.replace('.', '')
    timeout = timeout // 10
    LOG.debug('Checking scripting %s logs on %s by parameters:\n'
              '  script name:\t"%s"\n'
              '  event:\t\t%s\n'
              '  user:\t\t"%s"\n'
              '  log_contains:\t"%s"\n'
              '  exitcode:\t%s\n'
              '  new_only:\t%s\n'
              '  timeout:\t%s'
              % (out_name,
                 serv_as,
                 name or 'Any',
                 event or 'Any',
                 user or 'Any',
                 log_contains or 'Any',
                 exitcode or 'Any',
                 new_only,
                 timeout))

    for _ in range(timeout + 1):
        server.scriptlogs.reload()
        for log in server.scriptlogs:
            LOG.debug('Checking script log:\n'
                      '  name:\t"%s"\n'
                      '  event:\t"%s"\n'
                      '  run as:\t"%s"\n'
                      '  exitcode:\t"%s"'
                      % (log.name, log.event, log.run_as, log.exitcode))
            if log in last_scripts:
                LOG.debug('Pass this log because it in last scripts')
                continue
            if log.run_as is None:
                log.run_as = 'Administrator' if CONF.feature.dist.is_windows else 'root'
            event_matched = event is None or (log.event and log.event.strip() == event.strip())
            user_matched = user is None or (log.run_as == user)
            name_matched = name is None \
                or (name == 'chef' and log.name.strip().startswith(name)) \
                or (name.startswith('http') and log.name.strip().startswith(name)) \
                or (name.startswith('local') and log.name.strip().startswith(name)) \
                or log.name.strip() == name
            LOG.debug('Script matched parameters: event - %s, user - %s, name - %s' % (
                event_matched, user_matched, name_matched))
            if name_matched and event_matched and user_matched:
                LOG.debug('Script log matched search parameters')
                if exitcode is None or log.exitcode == int(exitcode):
                    # script exitcode is valid, now check that log output contains wanted text
                    message = log.message.split('STDOUT:', 1)[int(not std_err)]
                    ui_message = True
                    LOG.debug('Log message %s output: %s' % (out_name, message))
                    for cond in contain:
                        cond = cond.strip()
                        # FIXME: Remove this than maint/py3 will merged to master
                        if CONF.feature.branch == 'maint-py3' and "sudo: unknown user: revizor2" in cond:
                            cond = "no such user: 'revizor2'"
                        html_cond = cond.replace('"', '&quot;').replace('>', '&gt;').strip()
                        LOG.debug('Check condition "%s" in log' % cond)
                        found = (html_cond in message) if ui_message else (cond in message)
                        if not found and not CONF.feature.dist.is_windows and 'Log file truncated. See the full log in' in message:
                            full_log_path = re.findall(r'Log file truncated. See the full log in ([.\w\d/-]+)', message)[0]
                            node = world.cloud.get_node(server)
                            message = node.run('cat %s' % full_log_path).std_out
                            ui_message = False
                            found = cond in message
                        if not found:
                            raise AssertionError('Script on event "%s" (%s) contain: "%s" but lookup: \'%s\''
                                                  % (event, user, message, cond))
                    LOG.debug('This event exitcode: %s' % log.exitcode)
                    return True
                else:
                    raise AssertionError('Script on event \'%s\' (%s) exit with code: %s but lookup: %s'
                                         % (event, user, log.exitcode, exitcode))
        time.sleep(10)

    raise AssertionError(
        'I\'m not see script on event \'%s\' (%s) in script logs for server %s' % (event, user, server.id))


@world.absorb
def get_hostname(server):
    serv = world.cloud.get_node(server)
    with serv.remote_connection() as conn:
        for i in range(3):
            out = serv.run('/bin/hostname')
            if out.std_out.strip():
                return out.std_out.strip()
            time.sleep(5)
        raise AssertionError('Can\'t get hostname from server: %s' % server.id)


@world.absorb
def get_hostname_by_server_format(server):
    return 'r%s-%s-%s' % (
        world.farm.id,
        server.farm_role_id,
        server.index
    )


@world.absorb
def wait_upstream_in_config(node, ip, contain=True):
    out = node.run('cat /etc/nginx/app-servers.include').std_out
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
        n.run('mkdir -p /var/www/{0} && chmod 777 /var/www/{0}'.format(name))
        n.put_file('/var/www/%s/index.php' % name, index)
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
    out = node.run('cat /var/log/scalarizr_debug.log | grep "%s"' % text).std_out
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
    return world.cloud.get_node(server).run("pgrep -l %(process)s | awk {print'$1'} | xargs -i{}  kill {} && sleep 5 && pgrep -l %(process)s | awk {print'$1'}" % {'process': process}).std_out


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
            if CONF.feature.dist.is_systemd:
                cmd = "systemctl {status} {process} && sleep 3"
            else:
                cmd = "service {process} {status} && sleep 3"
            return node.run(cmd.format(
                process=service['node'],
                status=status))

    # Get process pid
    def get_pid():
        return node.run("pgrep -l %(process)s | awk {print'$1'} && sleep 5" %
                        {'process': service['node']}).std_out.rstrip('\n').split('\n')
    # Change status and get pid
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
    with node.remote_connection() as conn:
        logrotate_conf = conn.run('cat /etc/logrotate.d/%s-logrotate' % process)
        if not logrotate_conf.std_err:
            logrotate_param = {}
            #Get the directory from the first line config file
            logrotate_param['dir'] = '/'.join(logrotate_conf.std_out.split('\n')[0].split('/')[0:-1])
            #Check the archive log files
            logrotate_param['compress'] = 'compress' in logrotate_conf.std_out
            #Get the log file mask from the first line config
            logrotate_param['log_mask'] = logrotate_conf.std_out.split('\n')[0].split('/')[-1].rstrip('.log {')
            #Performing rotation and receive a list of log files
            LOG.info('Performing rotation and receive a list of log files for % remote host %s' % (process, server.public_ip))
            rotated_logs = conn.run('logrotate -f /etc/logrotate.d/%s-logrotate && stat --format="%%n %%U %%G %%a"  %s/%s' %
                                    (process, logrotate_param['dir'], logrotate_param['log_mask']))
            if not rotated_logs.status_code:
                try:
                    log_files = []
                    for str in rotated_logs.std_out.rstrip('\n').split('\n'):
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
                raise AssertionError("Can't logrotate to force the rotation. Error message:%s" % logrotate_conf.std_err)
        else:
            raise AssertionError("Can't get config file:%s-logrotate. Error message:%s" %
                                 (process, logrotate_conf.std_err))
        return True


@world.absorb
def value_for_os_family(debian, centos, server=None, node=None):
    if server:
        # Get node by server
        node = world.cloud.get_node(server)
    elif not node:
        raise AttributeError("Not enough required arguments: server and node both can't be empty")
    # Get os family result
    os_family_res = dict(debian=debian, centos=centos).get(CONF.feature.dist.family) if CONF.feature.dist.id != 'coreos' else 'echo'
    if not os_family_res:
        raise OSFamilyValueFailed('No value for node os: %s' % node.os.id)
    return os_family_res


@world.absorb
def get_service_paths(service_name, server=None, node=None, service_conf=None, service_conf_base_path=None):
    if server:
        node = world.cloud.get_node(server)
    elif not node:
        raise AttributeError("Not enough required arguments: server and node both can't be empty")
    with node.remote_connection() as conn:
        # Get service path
        service_path = conn.run('which %s' % service_name)
        if service_path.status_code:
            raise AssertionError("Can't get %s service path: %s" % (service_name, service_path))
        service_path = dict(bin=service_path.std_out.split()[0], conf='')
        # Get service config path
        if service_conf:
            base_path = service_conf_base_path or '/etc'
            service_conf_path = conn.run('find %s -type f -name "%s" -print' % (base_path, service_conf))
            if service_conf_path.status_code:
                raise AssertionError("Can't find service %s configs : %s" % (service_name, service_conf_path))
            service_path.update({'conf': service_conf_path.std_out.split()[0]})
        return service_path
