__author__ = 'gigimon'

import os
import time
import logging
import urllib2
import collections
import re
from datetime import datetime

from lettuce import world, step

from libcloud.compute.types import NodeState
from datetime import datetime

from revizor2 import consts
from revizor2.api import IMPL
from revizor2.conf import CONF
from revizor2.utils import wait_until
from revizor2.helpers.jsonrpc import ServiceError
from revizor2.helpers.parsers import parse_apt_repository, parse_rpm_repository, parser_for_os_family
from revizor2.defaults import DEFAULT_SERVICES_CONFIG, DEFAULT_API_TEMPLATES as templates, \
    DEFAULT_SCALARIZR_DEVEL_REPOS, DEFAULT_SCALARIZR_RELEASE_REPOS
from revizor2.consts import Platform, Dist, SERVICES_PORTS_MAP, BEHAVIORS_ALIASES
from revizor2 import szrapi
from revizor2.fixtures import tables

try:
    import winrm
except ImportError:
    raise ImportError("Please install WinRM")


PLATFORM_TERMINATED_STATE = collections.namedtuple('terminated_state', ('gce', 'ec2'))(
    'terminated',
    'stopped')

LOG = logging.getLogger(__name__)

#User data fixtures
#ec2 - (ec2, eucalyptus),  gce-gce, openstack-(openstack, ecs, rackspaceng), cloudstack-(cloudstack, idcf, ucloud)
USER_DATA = {
                Platform.EC2: {
                    "behaviors": "base,chef",
                    "farmid": "16674",
                    "message_format": "json",
                    "owner_email": "stunko@scalr.com",
                    "szr_key": "9gRW4akJmHYvh6W3vd6GzxOPtk/iQHL+8aZRZZ1u",
                    "s3bucket": "",
                    "cloud_server_id": "",
                    "env_id": "3414",
                    "server_index": "1",
                    "platform": "ec2",
                    "role": "base,chef",
                    "hash": "e6f1bfd5bbf612",
                    "custom.scm_branch": "master",
                    "roleid": "36318",
                    "farm_roleid": "60818",
                    "serverid": "96e52104-f5c4-4ce7-a018-c8c2eb571c99",
                    "p2p_producer_endpoint": "https://my.scalr.com/messaging",
                    "realrolename": "base-ubuntu1204-devel",
                    "region": "us-east-1",
                    "httpproto": "https",
                    "queryenv_url": "https://my.scalr.com/query-env",
                    "cloud_storage_path": "s3://"
                },

                Platform.GCE: {
                    "p2p_producer_endpoint": "https://my.scalr.com/messaging",
                    "behaviors": "app",
                    "owner_email": "stunko@scalr.com",
                    "hash": "e6f1bfd5bbf612",
                    "farmid": "16674",
                    "farm_roleid": "60832",
                    "message_format": "json",
                    "realrolename": "apache-ubuntu1204-devel",
                    "region": "x-scalr-custom",
                    "httpproto": "https",
                    "szr_key": "NiR2xOZKVbvdMPgdxuayLjEK2xC7mtLkVTc0vpka",
                    "platform": "gce",
                    "queryenv_url": "https://my.scalr.com/query-env",
                    "role": "app",
                    "cloud_server_id": "",
                    "roleid": "36319",
                    "env_id": "3414",
                    "serverid": "c2bc7273-6618-4702-9ea1-f290dca3b098",
                    "cloud_storage_path": "gcs://",
                    "custom.scm_branch": "master",
                    "server_index": "1"
                },

                Platform.OPENSTACK: {
                    "p2p_producer_endpoint": "https://my.scalr.com/messaging",
                    "behaviors": "base,chef",
                    "owner_email": "stunko@scalr.com",
                    "hash": "e6f1bfd5bbf612",
                    "farmid": "16674",
                    "farm_roleid": "60821",
                    "message_format": "json",
                    "realrolename": "base-ubuntu1204-devel",
                    "region": "ItalyMilano1",
                    "httpproto": "https",
                    "szr_key": "iyLO/+iOGFFcuSIxbr0IJteRwDjaP1t6NQ8kXbX6",
                    "platform": "ecs",
                    "queryenv_url": "https://my.scalr.com/query-env",
                    "role": "base,chef",
                    "roleid": "36318",
                    "env_id": "3414",
                    "serverid": "59ddbdbf-6d69-4c53-a6b7-76ab391a8465",
                    "cloud_storage_path": "swift://",
                    "custom.scm_branch": "master",
                    "server_index": "1"
                },

                Platform.CLOUDSTACK: {
                    "p2p_producer_endpoint": "https://my.scalr.com/messaging",
                    "behaviors": "base,chef",
                    "owner_email": "stunko@scalr.com",
                    "hash": "e6f1bfd5bbf612",
                    "farmid": "16674",
                    "farm_roleid": "60826",
                    "message_format": "json",
                    "realrolename": "base-ubuntu1204-devel",
                    "region": "jp-east-f2v",
                    "httpproto": "https",
                    "szr_key": "cg3uuixg4jTUDz/CexsKpoNn0VZ9u6EluwpV+Mgi",
                    "platform": "idcf",
                    "queryenv_url": "https://my.scalr.com/query-env",
                    "role": "base,chef",
                    "cloud_server_id": "",
                    "roleid": "36318",
                    "env_id": "3414",
                    "serverid": "feab131b-711e-4f4a-a7dc-ba083c28e5fc",
                    "custom.scm_branch": "master",
                    "server_index": "1"
                }
}


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
                                                                 Dist(node.os).family]['service_name']),
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
        if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK and world.cloud._driver.use_port_forwarding():
            port = server.details['scalarizr.ctrl_port']
        results = [VerifyProcessWork._verify_process_running(server, 'scalarizr'),
                   VerifyProcessWork._verify_process_running(server, 'scalr-upd-client'),
                   VerifyProcessWork._verify_open_port(server, port)]
        LOG.debug('Scalarizr verifying results: %s' % results)
        return all(results)

    @staticmethod
    def _verify_memcached(server, port):
        LOG.info('Verify memcached (%s) work in server %s' % (port, server.id))
        results = [VerifyProcessWork._verify_process_running(server, 'memcached'),
                   VerifyProcessWork._verify_open_port(server, port)]
        return all(results)


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
    if not CONF.feature.dist.is_windows:
        world.set_iptables_rule(server, port)
    if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK and world.cloud._driver.use_port_forwarding():
        port = world.cloud.open_port(node, port, ip=server.public_ip)

    results = []
    for attempt in range(3):
        results.append(world.check_open_port(server, port))
        time.sleep(5)

    if closed and results[-1]:
        raise AssertionError('Port %s is open on server %s (attempts: %s)' % (port, server.id, results))
    elif not closed and not results[-1]:
        raise AssertionError('Port %s is closed on server %s (attempts: %s)' % (port, server.id, results))


@step(r'([\w-]+(?!process)) is( not)? running on (.+)')
def assert_check_service(step, service, closed, serv_as): #FIXME: Rewrite this ugly logic
    server = getattr(world, serv_as)
    port = SERVICES_PORTS_MAP[service]
    if isinstance(port, collections.Iterable):
        port = port[0]
    closed = True if closed else False
    LOG.info('Verify port %s is %s on server %s' % (
        port, 'closed' if closed else 'open', server.id
    ))
    if service == 'scalarizr' and CONF.feature.dist.is_windows:
        status = None
        for _ in range(5):
            try:
                status = server.upd_api.status()['service_status']
            except ServiceError:
                status = server.upd_api_old.status()['service_status']
            if status == 'running':
                return
            time.sleep(5)
        else:
            raise AssertionError('Scalarizr is not running in windows, status: %s' % status)
    node = world.cloud.get_node(server)
    if not CONF.feature.dist.is_windows:
        world.set_iptables_rule(server, port)
    if CONF.feature.driver.cloud_family == Platform.CLOUDSTACK and world.cloud._driver.use_port_forwarding():
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
def assert_scalarizr_version_old(step, repo, serv_as):
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
    if consts.Dist(server.role.dist).is_centos:
        repo_data = parse_rpm_repository(repo)
    elif consts.Dist(server.role.dist).is_debian:
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
    #FIXME: Rewrite this ugly code!
    server = getattr(world, serv_as)
    if branch == 'system' or not branch:
        branch = CONF.feature.branch
    elif branch == 'role':
        branch = CONF.feature.to_branch
    # Get custom repo url
    os_family = Dist(server.role.dist).family
    if '.' in branch and branch.replace('.', '').isdigit():
        last_version = branch
    else:
        if branch in ['stable', 'latest']:
            default_repo = DEFAULT_SCALARIZR_RELEASE_REPOS[os_family]
        else:
            url = DEFAULT_SCALARIZR_DEVEL_REPOS['url'][CONF.feature.ci_repo]
            path = DEFAULT_SCALARIZR_DEVEL_REPOS['path'][os_family]
            default_repo = url.format(path=path)
        # Get last scalarizr version from custom repo
        index_url = default_repo.format(branch=branch)
        LOG.debug('Check package from index_url: %s' % index_url)
        repo_data = parser_for_os_family(server.role.dist)(branch=branch, index_url=index_url)
        versions = [package['version'] for package in repo_data if package['name'] == 'scalarizr']
        versions.sort(reverse=True)
        last_version = versions[0]
        if last_version.strip().endswith('-1'):
            last_version = last_version.strip()[:-2]
    LOG.debug('Last scalarizr version %s for branch %s' % (last_version, branch))
    # Get installed scalarizr version
    for _ in range(5):
        try:
            update_status = server.upd_api.status(cached=False)
            installed_version = update_status['installed']
            if installed_version.strip().endswith('-1'):
                installed_version = installed_version.strip()[:-2]
            break
        except urllib2.URLError:
            time.sleep(3)
    else:
        raise AssertionError('Can\'t get access to update client 5 times (15 seconds)')
    LOG.debug('Last scalarizr version from update client status: %s' % update_status['installed'])
    assert update_status['state'] == 'completed', \
        'Update client not in normal state. Status = "%s", Previous state = "%s"' % \
        (update_status['state'], update_status['prev_state'])
    assert last_version == installed_version, \
        'Server not has last build of scalarizr package, installed: %s last_version: %s' % (installed_version, last_version)


@step('I reboot scalarizr in (.+)$')
def reboot_scalarizr(step, serv_as):
    server = getattr(world, serv_as)
    if CONF.feature.dist.is_systemd:
        cmd = "systemctl restart scalarizr"
    else:
        cmd = "/etc/init.d/scalarizr restart"
    node = world.cloud.get_node(server)
    node.run(cmd)
    LOG.info('Scalarizr restart complete')
    time.sleep(15)


@step('see "(.+)" in ([\w]+) log')
def check_log(step, message, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    LOG.info('Check scalarizr log for  termination')
    wait_until(world.check_text_in_scalarizr_log, timeout=300, args=(node, message),
               error_text='Not see %s in debug log' % message)


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
            service.update({'node': common_config.get(consts.Dist(node.os).family).get('service_name')})
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
    if Dist(server.role.dist).is_debian:
        LOG.debug('Change in debian')
        node = world.cloud.get_node(server)
        for repo_file in ['/etc/apt/sources.list.d/scalr-stable.list', '/etc/apt/sources.list.d/scalr-latest.list']:
            LOG.info("Change branch in %s to %s" % (repo_file, branch))
            node.run('echo "deb http://buildbot.scalr-labs.com/apt/debian %s/" > %s' % (branch, repo_file))
    elif Dist(server.role.dist).is_centos:
        LOG.debug('Change in centos')
        node = world.cloud.get_node(server)
        for repo_file in ['/etc/yum.repos.d/scalr-stable.repo']:
            LOG.info("Change branch in %s to %s" % (repo_file, branch))
            node.run('echo "[scalr-branch]\nname=scalr-branch\nbaseurl=http://buildbot.scalr-labs.com/rpm/%s/rhel/\$releasever/\$basearch\nenabled=1\ngpgcheck=0" > %s' % (branch, repo_file))
        node.run('echo > /etc/yum.repos.d/scalr-latest.repo')
    elif Dist(server.role.dist).is_windows:
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
                                    common_config.get(consts.Dist(node.os).family).get('service_name'))
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


@step(r'I create ([\w]+-?[\w]+?\s)?image from deployed server')
def creating_image(step, image_type=None):
    image_type = image_type or 'base'
    cloud_server = getattr(world, 'cloud_server')
    # Create an image
    image_name = 'tmp-{}-{}-{:%d%m%Y-%H%M%S}'.format(
        image_type.strip(),
        CONF.feature.dist.id,
        datetime.now()
    )
    # Set credentials to image creation
    kwargs = dict(
        node=cloud_server,
        name=image_name,
    )
    if CONF.feature.driver.is_platform_ec2:
        kwargs.update({'reboot': False})
    image = world.cloud.create_template(**kwargs)
    assert getattr(image, 'id', False), 'An image from a node object %s was not created' % cloud_server.name
    # Remove cloud server
    LOG.info('An image: %s from a node object: %s was created' % (image.id, cloud_server.name))
    setattr(world, 'image', image)
    LOG.debug('Image attrs: %s' % dir(image))
    LOG.debug('Image Name: %s' % image.name)
    if CONF.feature.driver.is_platform_cloudstack:
        forwarded_port = world.forwarded_port
        ip = world.ip
        assert world.cloud.close_port(cloud_server, forwarded_port, ip=ip), "Can't delete a port forwarding rule."
    LOG.info('Port forwarding rule was successfully removed.')
    if not CONF.feature.driver.is_platform_gce:
        assert cloud_server.destroy(), "Can't destroy node: %s." % cloud_server.id
    LOG.info('Virtual machine %s was successfully destroyed.' % cloud_server.id)
    setattr(world, 'cloud_server', None)


@step(r'I add ([\w]+-?[\w]+?\s)?image to the new roles?(\sas non scalarized)*$')
def creating_role(step, image_type=None, non_scalarized=None):
    image = getattr(world, 'image')
    image_type = (image_type or 'base').strip()
    if CONF.feature.driver.is_platform_gce:
        cloud_location = ""
        image_id = image.extra['selfLink'].split('projects')[-1][1:]
    else:
         cloud_location = CONF.platforms[CONF.feature.platform]['location']
         image_id = image.id
    image_kwargs = dict(
        platform=CONF.feature.driver.scalr_cloud,
        cloud_location=cloud_location,
        image_id=image_id
    )
    name = 'tmp-{}-{}-{:%d%m%Y-%H%M%S}'.format(
            image_type,
            CONF.feature.dist.id,
            datetime.now())
    if image_type != 'base':
        behaviors = getattr(world, 'installed_behaviors', None)
    else:
        behaviors = ['chef']
    # Checking an image
    try:
        LOG.debug('Checking an image {image_id}:{platform}({cloud_location})'.format(**image_kwargs))
        IMPL.image.check(**image_kwargs)
        image_registered = False
    except Exception as e:
        if not ('Image has already been registered' in e.message):
            raise
        image_registered = True
    is_scalarized = False if non_scalarized else True
    has_cloudinit = True if ('cloudinit' in image_type and not is_scalarized) else False
    if not image_registered:
        # Register image to the Scalr
        LOG.debug('Register image %s to the Scalr' % name)
        image_kwargs.update(dict(
            software=behaviors,
            name=name,
            is_scalarized=is_scalarized,
            has_cloudinit=has_cloudinit))
        image = IMPL.image.create(**image_kwargs)
    else:
        image = IMPL.image.get(image_id=image_id)
    # Create new role
    for behavior in behaviors:
        if has_cloudinit:
            role_name = name.replace(image_type, '-'.join((behavior,'cloudinit')))
            role_behaviors = list((behavior, 'chef'))
        else:
            role_name = name
            role_behaviors = behaviors
        role_kwargs = dict(
            name=role_name,
            is_scalarized = int(is_scalarized or has_cloudinit),
            behaviors=role_behaviors,
            images=[dict(
                platform=CONF.feature.driver.scalr_cloud,
                cloudLocation=cloud_location,
                hash=image['hash'])])
        LOG.debug('Create new role {name}. Role options: {behaviors} {images}'.format(**role_kwargs))
        role = IMPL.role.create(**role_kwargs)
        if not has_cloudinit:
            setattr(world, 'role', role['role'])


def run_sysprep(uuid, console):
    cmd = dict(
        gce='gcesysprep',
        ec2=world.PS_RUN_AS.format(
            command='''$doc = [xml](Get-Content 'C:/Program Files/Amazon/Ec2ConfigService/Settings/config.xml'); ''' \
                '''$doc.Ec2ConfigurationSettings.Plugins.Plugin[0].State = 'Enabled'; ''' \
                '''$doc.save('C:/Program Files/Amazon/Ec2ConfigService/Settings/config.xml')"; ''' \
                '''cmd /C "'C:\Program Files\Amazon\Ec2ConfigService\ec2config.exe' -sysprep'''))
    try:
        console.run_cmd(cmd.get(CONF.feature.driver.scalr_cloud))
    except Exception as e:
        LOG.error('Run sysprep exception : %s' % e.message)
    # Check that instance has stopped after sysprep
    end_time = time.time() + 900
    while time.time() <= end_time:
        node = (filter(lambda n: n.uuid == uuid, world.cloud.list_nodes()) or [''])[0]
        LOG.debug('Obtained node after sysprep running: %s' % node)
        LOG.debug('Obtained node status after sysprep running: %s' % node.state)
        if node.state == NodeState.STOPPED:
            break
        time.sleep(10)
    else:
        raise AssertionError('Cloud instance is not in STOPPED status - sysprep failed, it state: %s' % node.state)


def get_user_name():
    if CONF.feature.driver.is_platform_gce:
        user_name = ['scalr']
    elif CONF.feature.dist.dist == 'ubuntu':
        user_name = ['root', 'ubuntu']
    elif CONF.feature.dist.dist == 'amazon' or \
            (CONF.feature.dist.dist == 'redhat' and CONF.feature.driver.is_platform_ec2):
        user_name = ['root', 'ec2-user']
    else:
        user_name = ['root']
    return user_name


def get_repo_type(custom_branch, custom_version=None):
    class RepoTypes(dict):

        def __init__(self, branch, version=None):
            dict.__init__(self)
            ci_repo = CONF.feature.ci_repo.lower()
            version = version or ''
            self.update({
                'release': '{branch}'.format(branch=branch),
                'develop': '{ci}/{branch}'.format(ci=ci_repo, branch=branch),
                'snapshot': 'snapshot/{version}'.format(version=version)})

        def __extend_repo_type(self, value):
            rt = value.split('/')
            rt.insert(1, CONF.feature.driver.scalr_cloud)
            return '/'.join(rt)

        def __getitem__(self, key):
            if self.has_key(key):
                value = dict.__getitem__(self, key)
                if not CONF.feature.dist.is_windows:
                    value = self.__extend_repo_type(value)
                return value
            raise AssertionError('Repo type: "%s" not valid' % key)

        def get(self, key):
            return self.__getitem__(key)

    # Getting repo types for os family
    repo_types = RepoTypes(branch=custom_branch, version=custom_version)
    # Getting repo
    if custom_version:
        repo_type = repo_types.get('snapshot')
    elif custom_branch in ['latest', 'stable']:
        repo_type = repo_types.get('release')
    else:
        repo_type = repo_types.get('develop')
    return repo_type


@step(r"I install(?: new)? scalarizr(?: ([\w\d\.\'\-]+))?(?: (with sysprep))? to the server(?: ([\w][\d]))?(?: (manually))?(?: from the branch ([\w\d\W]+))?")
def installing_scalarizr(step, custom_version=None, use_sysprep=None, serv_as=None, use_rv_to_branch=None, custom_branch=None):
    node = getattr(world, 'cloud_server', None)
    resave_node = True if node else False
    rv_branch = CONF.feature.branch
    rv_to_branch = CONF.feature.to_branch
    server = getattr(world, (serv_as or '').strip(), None)
    if server:
        server.reload()
    # Get scalarizr repo type
    if use_rv_to_branch:
        branch = rv_to_branch
    elif custom_branch:
        branch = custom_branch
    else:
        branch = rv_branch
    repo_type = get_repo_type(branch, custom_version)
    LOG.info('Installing scalarizr from repo_type: %s' % repo_type)
    # Windows handler
    if CONF.feature.dist.is_windows:
        password = 'Scalrtest123'
        if node:
            console_kwargs = dict(
                public_ip=node.public_ips[0],
                password=password)
        else:
            console_kwargs = dict(server=server)
            if CONF.feature.driver.is_platform_ec2:
                console_kwargs.update({'password': password})
            LOG.debug('Cloud server not found get node from server')
            node = wait_until(world.cloud.get_node, args=(server,), timeout=300, logger=LOG)
            LOG.debug('Node get successfully: %s' % node)  # Wait ssh
        console_kwargs.update({'timeout': 1200})
        # Install scalarizr
        url = 'https://my.scalr.net/public/windows/{repo_type}'.format(repo_type=repo_type)
        cmd = "iex ((new-object net.webclient).DownloadString('{url}/install_scalarizr.ps1'))".format(url=url)
        assert not world.run_cmd_command_until(
            world.PS_RUN_AS.format(command=cmd),
            **console_kwargs).std_err, "Scalarizr installation failed"
        out = world.run_cmd_command_until('scalarizr -v', **console_kwargs).std_out
        LOG.debug('Installed scalarizr version: %s' % out)
        version = re.findall('(?:Scalarizr\s)([a-z0-9/./-]+)', out)
        assert version, 'installed scalarizr version not valid. Regexp found: "%s", out from server: "%s"' % (version, out)
        if use_sysprep:
            run_sysprep(node.uuid, world.get_windows_session(**console_kwargs))
    # Linux handler
    else:
        # Wait cloud server
        if not node:
            LOG.debug('Cloud server not found get node from server')
            node = wait_until(world.cloud.get_node, args=(server, ), timeout=300, logger=LOG)
            LOG.debug('Node get successfully: %s' % node)
        # Wait ssh
        start_time = time.time()
        while (time.time() - start_time) < 300:
            try:
                if node.get_ssh():
                    break
            except AssertionError:
                LOG.warning('Can\'t get ssh for server %s' % node.id)
                time.sleep(10)
        url = 'https://my.scalr.net/public/linux/{repo_type}'.format(repo_type=repo_type)
        cmd = '{curl_install} && ' \
            'curl -L {url}/install_scalarizr.sh | bash && ' \
            'sync && scalarizr -v'.format(
                curl_install=world.value_for_os_family(
                    debian="apt-get update && apt-get install curl -y",
                    centos="yum clean all && yum install curl -y",
                    server=server,
                    node=node
                ),
                url=url)
        LOG.debug('Install script body: %s' % cmd)
        res = node.run(cmd)[0]
        version = re.findall('(?:Scalarizr\s)([a-z0-9/./-]+)', res)
        assert version, 'Scalarizr version is invalid. Command returned: %s' % res
        cv2_init = 'touch /etc/scalr/private.d/scalr_labs_corev2'
        LOG.info('Init scalarizr corev2. Run command %s' % cv2_init)
        node.run(cv2_init)
    setattr(world, 'pre_installed_agent', version[0])
    if resave_node:
        setattr(world, 'cloud_server', node)
    LOG.debug('Scalarizr %s was successfully installed' % world.pre_installed_agent)


@step('I have a server([\w ]+)? running in cloud$')
def given_server_in_cloud(step, user_data):
    #TODO: Add install behaviors
    LOG.info('Create node in cloud. User_data:%s' % user_data)
    #Convert dict to formatted str
    if user_data:
        dict_to_str = lambda d: ';'.join(['='.join([key, value]) if value else key for key, value in d.iteritems()])
        user_data = dict_to_str(USER_DATA[CONF.feature.driver.cloud_family])
        if CONF.feature.driver.current_cloud == Platform.GCE:
            user_data = {'scalr': user_data}
    else:
        user_data = None
    #Create node
    image = None
    if CONF.feature.dist.is_windows:
        table = tables('images-clean')
        search_cond = dict(
            dist=CONF.feature.dist.id,
            platform=CONF.feature.platform)
        image = table.filter(search_cond).first().keys()[0].encode('ascii', 'ignore')
    node = world.cloud.create_node(userdata=user_data, use_hvm=CONF.feature.use_vpc, image=image)
    setattr(world, 'cloud_server', node)
    LOG.info('Cloud server was set successfully node name: %s' % node.name)
    if CONF.feature.driver.current_cloud in [Platform.CLOUDSTACK, Platform.IDCF, Platform.KTUCLOUD]:
        #Run command
        out = node.run('wget -qO- ifconfig.me/ip')
        if not out[1]:
            ip_address = out[0].rstrip("\n")
            LOG.info('Received external ip address of the node. IP:%s' % ip_address)
            setattr(world, 'ip', ip_address)
        else:
            raise AssertionError("Can't get node external ip address. Original error: %s" % out[1])
        #Open port, set firewall rule
        new_port = world.cloud.open_port(node, 8013, ip=ip_address)
        setattr(world, 'forwarded_port', new_port)
        if not new_port == 8013:
            raise AssertionError('Import will failed, because opened port is not 8013, '
                                 'an installed port is: %s' % new_port)
