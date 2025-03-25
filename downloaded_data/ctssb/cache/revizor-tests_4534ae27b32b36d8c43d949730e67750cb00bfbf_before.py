__author__ = 'gigimon'

import os
import sys
import time
import logging
import collections

from lettuce import world, step

from revizor2 import consts
from revizor2.conf import CONF
from revizor2.utils import wait_until
from revizor2.helpers.jsonrpc import ServiceError
from revizor2.helpers.parsers import parse_apt_repository, parse_rpm_repository, parser_for_os_family
from revizor2.defaults import DEFAULT_SERVICES_CONFIG, DEFAULT_API_TEMPLATES as templates, \
    DEFAULT_SCALARIZR_DEVEL_REPOS, DEFAULT_SCALARIZR_RELEASE_REPOS
from revizor2.consts import Platform, Dist, SERVICES_PORTS_MAP, BEHAVIORS_ALIASES
from revizor2 import szrapi

try:
    import winrm
except ImportError:
    raise ImportError("Please install WinRM")


LOG = logging.getLogger(__name__)


class VerifyProcessWork(object):

    @staticmethod
    def verify(server, behavior=None, port=None):
        if not behavior:
            behavior = server.role.behaviors[0]
        LOG.info('Verify %s behavior process work in server %s (on port: %s)' % (behavior, server.id, port))
        if hasattr(VerifyProcessWork, '_verify_%s' % behavior):
            return getattr(VerifyProcessWork, '_verify_%s' % behavior)(server, port)
        return True

    @staticmethod
    def _verify_process_running(server, process_name):
        LOG.debug('Check process %s in running state on server %s' % (process_name, server.id))
        node = world.cloud.get_node(server)
        for i in range(3):
            out = node.run("ps -C %s -o pid=" % process_name)
            if not out[0].strip():
                LOG.warning("Process %s don't work in server %s (attempt %s)" % (process_name, server.id, i))
            else:
                LOG.info("Process %s work in server %s" % (process_name, server.id))
                return True
            time.sleep(5)
        return False

    @staticmethod
    def _verify_open_port(server, port):
        for i in range(5):
            opened = world.check_open_port(server, port)
            if opened:
                return True
            time.sleep(15)
        return False

    @staticmethod
    def _verify_app(server, port):
        LOG.info('Verify apache (%s) work in server %s' % (port, server.id))
        node = world.cloud.get_node(server)
        results = [VerifyProcessWork._verify_process_running(server,
                                                             DEFAULT_SERVICES_CONFIG['app'][
                                                                 Dist.get_os_family(node.os[0])]['service_name']),
                   VerifyProcessWork._verify_open_port(server, port)]
        return all(results)

    @staticmethod
    def _verify_www(server, port):
        LOG.info('Verify nginx (%s) work in server %s' % (port, server.id))
        results = [VerifyProcessWork._verify_process_running(server, 'nginx'),
                   VerifyProcessWork._verify_open_port(server, port)]
        return all(results)

    @staticmethod
    def _verify_redis(server, port):
        LOG.info('Verify redis-server (%s) work in server %s' % (port, server.id))
        results = [VerifyProcessWork._verify_process_running(server, 'redis-server'),
                   VerifyProcessWork._verify_open_port(server, port)]
        LOG.debug('Redis-server verifying results: %s' % results)
        return all(results)

    @staticmethod
    def _verify_scalarizr(server, port=8010):
        LOG.info('Verify scalarizr (%s) work in server %s' % (port, server.id))
        if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK:
            port = server.details['scalarizr.ctrl_port']
        results = [VerifyProcessWork._verify_process_running(server, 'scalarizr'),
                   VerifyProcessWork._verify_process_running(server, 'scalr-upd-client'),
                   VerifyProcessWork._verify_open_port(server, port)]
        LOG.debug('Scalarizr verifying results: %s' % results)
        return all(results)


@step('I change repo in ([\w\d]+)$')
def change_repo(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    branch = CONF.feature.to_branch
    change_repo_to_branch(node, branch)


@step('I change repo in ([\w\d]+) to system$')
def change_repo(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    change_repo_to_branch(node, CONF.feature.branch)


def change_repo_to_branch(node, branch):
    if 'ubuntu' in node.os[0].lower() or 'debian' in node.os[0].lower():
        LOG.info('Change repo in Ubuntu')
        node.put_file('/etc/apt/sources.list.d/scalr-branch.list',
                      'deb http://buildbot.scalr-labs.com/apt/debian %s/\n' % branch)
    elif 'centos' in node.os[0].lower():
        LOG.info('Change repo in CentOS')
        node.put_file('/etc/yum.repos.d/scalr-stable.repo',
                      '[scalr-branch]\n' +
                      'name=scalr-branch\n' +
                      'baseurl=http://buildbot.scalr-labs.com/rpm/%s/rhel/$releasever/$basearch\n' % branch +
                      'enabled=1\n' +
                      'gpgcheck=0\n' +
                      'protect=1\n')


@step('pin([ \w]+)? repo in ([\w\d]+)$')
def pin_repo(step, repo, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    if repo and repo.strip() == 'system':
        branch = CONF.feature.branch.replace('/', '-').replace('.', '').strip()
    else:
        branch = os.environ.get('RV_TO_BRANCH', 'master').replace('/', '-').replace('.', '').strip()
    if 'ubuntu' in node.os[0].lower():
        LOG.info('Pin repository for branch %s in Ubuntu' % branch)
        node.put_file('/etc/apt/preferences',
                      'Package: *\n' +
                      'Pin: release a=%s\n' % branch +
                      'Pin-Priority: 990\n')
    elif 'centos' in node.os[0].lower():
        LOG.info('Pin repository for branch %s in CentOS' % repo)
        node.run('yum install yum-protectbase -y')


@step('update scalarizr in ([\w\d]+)$')
def update_scalarizr(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    if 'ubuntu' in node.os[0].lower():
        LOG.info('Update scalarizr in Ubuntu')
        node.run('apt-get update')
        node.run('apt-get install scalarizr-base scalarizr-%s -y' % CONF.feature.driver.scalr_cloud)
    elif 'centos' in node.os[0].lower():
        LOG.info('Update scalarizr in CentOS')
        node.run('yum install scalarizr-base scalarizr-%s -y' % CONF.feature.driver.scalr_cloud)


@step('process ([\w-]+) is (not\s)*running in ([\w\d]+)$')
def check_process(step, process, negation, serv_as):
    LOG.info("Check running process %s on server" % process)
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    list_proc = node.run('ps aux | grep %s' % process)[0].split('\n')
    processes = filter(lambda x: 'grep' not in x and x, list_proc)
    msg = "Process {} on server {} not in valid state".format(
        process,
        server.id)
    assert not processes if negation else processes, msg


@step(r'(\d+) port is( not)? listen on ([\w\d]+)')
def verify_port_status(step, port, closed, serv_as):
    server = getattr(world, serv_as)
    if port.isdigit():
        port = int(port)
    else:
        port = SERVICES_PORTS_MAP[port]
        if isinstance(port, collections.Iterable):
            port = port[0]
    closed = True if closed else False
    LOG.info('Verify port %s is %s on server %s' % (
        port, 'closed' if closed else 'open', server.id
    ))
    node = world.cloud.get_node(server)
    if not CONF.feature.dist.startswith('win'):
        world.set_iptables_rule(server, port)
    if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK:
        port = world.cloud.open_port(node, port, ip=server.public_ip)

    results = []
    for attempt in range(3):
        results.append(world.check_open_port(server, port))
        time.sleep(5)

    if closed and results[-1]:
        raise AssertionError('Port %s is open on server %s (attempts: %s)' % (port, server.id, results))
    elif not closed and not results[-1]:
        raise AssertionError('Port %s is closed on server %s (attempts: %s)' % (port, server.id, results))


@step(r'([\w-]+) is( not)? running on (.+)')
def assert_check_service(step, service, closed, serv_as):
    server = getattr(world, serv_as)
    port = SERVICES_PORTS_MAP[service]
    if isinstance(port, collections.Iterable):
        port = port[0]
    closed = True if closed else False
    LOG.info('Verify port %s is %s on server %s' % (
        port, 'closed' if closed else 'open', server.id
    ))
    if service == 'scalarizr' and CONF.feature.dist.startswith('win'):
        try:
            status = server.upd_api.status()['service_status']
        except ServiceError:
            status = server.upd_api_old.status()['service_status']
        if not status == 'running':
            raise AssertionError('Scalarizr is not running in windows, status: %s' % status)
        return
    node = world.cloud.get_node(server)
    if not CONF.feature.dist.startswith('win'):
        world.set_iptables_rule(server, port)
    if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK:
        #TODO: Change login on this behavior
        port = world.cloud.open_port(node, port, ip=server.public_ip)
    if service in BEHAVIORS_ALIASES.values():
        behavior = [x[0] for x in BEHAVIORS_ALIASES.items() if service in x][0]
    else:
        behavior = service
    check_result = VerifyProcessWork.verify(server, behavior, port)
    if closed and check_result:
        raise AssertionError("Service %s must be don't work but it work!" % service)
    if not closed and not check_result:
        raise AssertionError("Service %s must be work but it doesn't work! (results: %s)" % (service, check_result))


@step(r'I (\w+) service ([\w\d]+) in ([\w\d]+)')
def service_control(step, action, service, serv_as):
    LOG.info("%s service %s" % (action.title(), service))
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    node.run('/etc/init.d/%s %s' % (service, action))


@step(r'scalarizr debug log in ([\w\d]+) contains \'(.+)\'')
def find_string_in_debug_log(step, serv_as, string):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    out = node.run('grep "%s" /var/log/scalarizr_debug.log' % string)
    if not string in out[0]:
        raise AssertionError('String "%s" not found in scalarizr_debug.log. Grep result: %s' % (string, out))


@step('scalarizr version from (\w+) repo is last in (.+)$')
@world.passed_by_version_scalarizr('2.5.14')
def assert_scalarizr_version(step, repo, serv_as):
    """
    Argument repo can be system or role.
    System repo - CONF.feature.branch
    Role repo - CONF.feature.to_branch
    """
    if repo == 'system':
        repo = CONF.feature.branch
    elif repo == 'role':
        repo = CONF.feature.to_branch
    server = getattr(world, serv_as)
    if consts.Dist.is_centos_family(server.role.dist):
        repo_data = parse_rpm_repository(repo)
    elif consts.Dist.is_debian_family(server.role.dist):
        repo_data = parse_apt_repository(repo)
    versions = [package['version'] for package in repo_data if package['name'] == 'scalarizr']
    versions.sort()
    LOG.info('Scalarizr versions in repository %s: %s' % (repo, versions))
    try:
        server_info = server.upd_api.status(cached=False)
    except Exception:
        server_info = server.upd_api_old.status()
    LOG.debug('Server %s status: %s' % (server.id, server_info))
    # if not repo == server_info['repository']:
    #     raise AssertionError('Scalarizr installed on server from different repo (%s) must %s'
    #                          % (server_info['repository'], repo))
    if not versions[-1] == server_info['installed']:
        raise AssertionError('Installed scalarizr version is not last! Installed %s, last: %s'
                             % (server_info['installed'], versions[-1]))


@step(r'scalarizr version(?:\sfrom\s([\w\d_]+))* is last in ([\w\d]+)$')
def assert_scalarizr_version(step, branch, serv_as):
    """
    Argument branch can be system or role.
    System branch - CONF.feature.branch
    Role branch - CONF.feature.to_branch
    """
    server = getattr(world, serv_as)
    if branch == 'system' or not branch:
        branch = CONF.feature.branch
    elif branch == 'role':
        branch = CONF.feature.to_branch
    # Get custom repo url
    os_family = Dist.get_os_family(server.role.dist)
    if branch in ['stable', 'latest']:
        default_repo = DEFAULT_SCALARIZR_RELEASE_REPOS[os_family]
    else:
        url = DEFAULT_SCALARIZR_DEVEL_REPOS['url'][CONF.feature.ci_repo]
        path = DEFAULT_SCALARIZR_DEVEL_REPOS['path'][os_family]
        default_repo = url.format(path=path)
    # Get last scalarizr version from custom repo
    index_url = default_repo.format(branch=branch)
    LOG.debug('Check package from index_url: %s' % index_url)
    repo_data = parser_for_os_family(server.role.dist)(index_url=index_url)
    versions = [package['version'] for package in repo_data if package['name'] == 'scalarizr']
    versions.sort(reverse=True)
    LOG.debug('Last scalarizr version %s for branch %s' % (versions[0] , branch))
    # Get installed scalarizr version
    update_status = server.upd_api.status(cached=False)
    LOG.debug('Last scalarizr version from update client status: %s' % update_status['installed'])
    assert update_status['state'] == 'completed', \
        'Update client not in normal state. Status = "%s", Previous state = "%s"' % \
        (update_status['state'], update_status['prev_state'])
    assert versions[0]  == update_status['installed'], \
        'Server not has last build of scalarizr package, candidate: %s' % update_status['installed']


@step('I reboot scalarizr in (.+)$')
def reboot_scalarizr(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    node.run('/etc/init.d/scalarizr restart')
    LOG.info('Scalarizr restart complete')
    time.sleep(15)


@step("see 'Scalarizr terminated' in ([\w]+) log")
def check_log(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Check scalarizr log for  termination')
    wait_until(world.check_text_in_scalarizr_log, timeout=300, args=(node, "Scalarizr terminated"),
               error_text='Not see "Scalarizr terminated" in debug log')


@step('I ([\w\d]+) service ([\w\d]+)(?: and ([\w]+) has been changed)? on ([\w\d]+)(?: by ([\w]+))?')
def change_service_status(step, status_as, behavior, is_change_pid, serv_as, is_api):
    """Change process status on remote host by his name. """
    #Init params
    service = {'node': None}
    server = getattr(world, serv_as)
    is_api = True if is_api else False
    is_change_pid = True if is_change_pid else False
    node = world.cloud.get_node(server)

    #Checking the behavior in the role
    if not behavior in server.role.behaviors and behavior != 'scalarizr':
        raise AssertionError("{0} can not be found in the tested role.".format(behavior))

    #Get behavior configs
    common_config = DEFAULT_SERVICES_CONFIG.get(behavior)
    #Get service name & status
    if common_config:
        status = common_config['api_endpoint']['service_methods'].get(status_as) if is_api else status_as
        service.update({'node': common_config.get('service_name')})
        if not service['node']:
            service.update({'node': common_config.get(consts.Dist.get_os_family(node.os[0])).get('service_name')})
        if is_api:
            service.update({'api': common_config['api_endpoint'].get('name')})
            if not service['api']:
                raise AssertionError("Can't {0} service. "
                                     "The api endpoint name is not found by the bahavior name {1}".format(status_as, behavior))
            if not status:
                raise AssertionError("Can't {0} service. "
                                     "The api call is not found for {1}".format(status_as, service['node']))
    if not service['node']:
        raise AssertionError("Can't {0} service. "
                             "The process name is not found by the bahavior name {1}".format(status_as, behavior))
    LOG.info("Change service status: {0} {1} {2}".format(service['node'], status, 'by api call' if is_api else ''))

    #Change service status, get pids before and after
    res = world.change_service_status(server, service, status, use_api=is_api, change_pid=is_change_pid)

    #Verify change status
    if any(pid in res['pid_before'] for pid in res['pid_after']):
        LOG.error('Service change status info: {0} Service change status error: {1}'.format(res['info'][0], res['info'][1])
        if not is_api
        else 'Status of the process has not changed, pid have not changed. pib before: %s pid after: %s' % (res['pid_before'], res['pid_after']))
        raise AssertionError("Can't {0} service. No such process {1}".format(status_as, service['node']))

    LOG.info('Service change status info: {0}'.format(res['info'][0] if not is_api
        else '%s.%s() complete successfully' % (service['api'], status)))
    LOG.info("Service status was successfully changed : {0} {1} {2}".format(service['node'], status_as,
                                                                            'by api call' if is_api else ''))
    time.sleep(15)


@step('I know ([\w]+) storages$')
def get_ebs_for_instance(step, serv_as):
    """Give EBS storages for server"""
    #TODO: Add support for all platform with persistent disks
    server = getattr(world, serv_as)
    volumes = server.get_volumes()
    LOG.debug('Volumes for server %s is: %s' % (server.id, volumes))
    if CONF.feature.driver.current_cloud == Platform.EC2:
        storages = filter(lambda x: 'sda' not in x.extra['device'], volumes)
    elif CONF.feature.driver.current_cloud in [Platform.IDCF, Platform.CLOUDSTACK]:
        storages = filter(lambda x: x.extra['volume_type'] == 'DATADISK', volumes)
    else:
        return
    LOG.info('Storages for server %s is: %s' % (server.id, storages))
    if not storages:
        raise AssertionError('Server %s not have storages (%s)' % (server.id, storages))
    setattr(world, '%s_storages' % serv_as, storages)


@step('([\w]+) storage is (.+)$')
def check_ebs_status(step, serv_as, status):
    """Check EBS storage status"""
    if CONF.feature.driver.current_cloud == Platform.GCE:
        return
    time.sleep(30)
    server = getattr(world, serv_as)
    wait_until(world.check_server_storage, args=(serv_as, status), timeout=300, error_text='Volume from server %s is not %s' % (server.id, status))


@step('change branch in server ([\w\d]+) in sources to ([\w\d]+)')
def change_branch_in_sources(step, serv_as, branch):
    if 'system' in branch:
        branch = CONF.feature.branch
    elif not branch.strip():
        branch = CONF.feature.to_branch
    else:
        branch = branch.replace('/', '-').replace('.', '').strip()
    server = getattr(world, serv_as)
    LOG.info('Change branches in sources list in server %s to %s' % (server.id, branch))
    if Dist.is_debian_family(server.role.dist):
        LOG.debug('Change in debian')
        node = world.cloud.get_node(server)
        for repo_file in ['/etc/apt/sources.list.d/scalr-stable.list', '/etc/apt/sources.list.d/scalr-latest.list']:
            LOG.info("Change branch in %s to %s" % (repo_file, branch))
            node.run('echo "deb http://buildbot.scalr-labs.com/apt/debian %s/" > %s' % (branch, repo_file))
    elif Dist.is_centos_family(server.role.dist):
        LOG.debug('Change in centos')
        node = world.cloud.get_node(server)
        for repo_file in ['/etc/yum.repos.d/scalr-stable.repo']:
            LOG.info("Change branch in %s to %s" % (repo_file, branch))
            node.run('echo "[scalr-branch]\nname=scalr-branch\nbaseurl=http://buildbot.scalr-labs.com/rpm/%s/rhel/\$releasever/\$basearch\nenabled=1\ngpgcheck=0" > %s' % (branch, repo_file))
        node.run('echo > /etc/yum.repos.d/scalr-latest.repo')
    elif Dist.is_windows_family(server.role.dist):
        # LOG.debug('Change in windows')
        import winrm
        console = winrm.Session('http://%s:5985/wsman' % server.public_ip,
                                auth=("Administrator", server.windows_password))
        for repo_file in ['C:\Program Files\Scalarizr\etc\scalr-latest.winrepo',
                          'C:\Program Files\Scalarizr\etc\scalr-stable.winrepo']:
            # LOG.info("Change branch in %s to %s" % (repo_file, branch))
            console.run_cmd('echo http://buildbot.scalr-labs.com/win/%s/x86_64/ > "%s"' % (branch, repo_file))


# Step used revizor2.szrapi classes functional
@step(r'I run (.+) command (.+) and pid has been changed on (\w+)(?:(.+))?')
def change_service_pid_by_api(step, service_api, command, serv_as, isset_args=None):
    """
        :param service_api: Service Api class name
        :param command: Api command
        :param serv_as: Server name
        :param isset_args: Is api command has extended arguments
    """
    #Get process pid
    def get_pid(pattern):
        if not pattern:
            raise Exception("Can't get service pid, service search condition is empty.")
        if isinstance(pattern, (list, tuple)):
            pattern = [str(element).strip() for element in pattern]
        else:
            pattern = [element.strip() for element in str(pattern).split(',')]
        cmd = "ps aux | grep {pattern} | grep -v grep | awk {{print'$2'}}".format(pattern='\|'.join(pattern))
        return node.run(cmd)[0].rstrip('\n').split('\n')

    # Set attributes
    server = getattr(world, serv_as)
    service_api = service_api.strip().replace('"', '')
    command = command.strip().replace('"', '')
    node = world.cloud.get_node(server)

    # Get service api
    api = getattr(getattr(szrapi, service_api)(server), command)
    LOG.debug('Set %s instance %s for server %s' % (service_api, api, server.id))
    # Get api arguments
    args = {}
    if isset_args:
        LOG.debug('Api method: (%s) extended arguments: %s' % (command, step.hashes))
        for key, value in step.hashes[0].iteritems():
            try:
                if value.isupper():
                    args.update({key: templates[service_api][value.lower()]})
                else:
                    args.update({key: eval(value)})
            except Exception:
                args.update({key: value})
        LOG.debug('Save {0}.{1} extended arguments: {2}'.format(
            service_api,
            command,
            args
        ))

    # Get service search pattern
    pattern = args.get('ports', None)
    if not pattern:
        # Get behavior from role
        behavior = server.role.behaviors[0]
        common_config = DEFAULT_SERVICES_CONFIG.get(behavior)
        pattern = common_config.get('service_name',
                                    common_config.get(consts.Dist.get_os_family(node.os[0])).get('service_name'))
    LOG.debug('Set search condition: (%s) to get service pid.' % pattern)
    # Run api command
    pid_before = get_pid(pattern)
    LOG.debug('Obtained service:%s pid list %s before api call.' % (pattern, pid_before))
    api_result = api(**args) if args else api()
    LOG.debug('Run %s instance method %s.' % (service_api, command))
    # Save api command result to world [command_name]_res
    setattr(world, ''.join((command, '_res')), api_result)
    LOG.debug('Save {0} instance method {1} result: {2}'.format(
        service_api,
        command,
        api_result))
    pid_after = get_pid(pattern)
    LOG.debug('Obtained service:%s pid list %s after api call.' % (pattern, pid_after))
    assertion_message = 'Some pid was not be changed. pid before api call: {0} after: {1}'.format(
        pid_before,
        pid_after)
    assert not any(pid in pid_before for pid in pid_after), assertion_message
