import os
import re
import logging
import json
from datetime import datetime

from lettuce import world, after, before

from lxml import etree

from revizor2.conf import CONF
from revizor2.backend import IMPL
from revizor2.cloud import Cloud
from revizor2.cloud.node import ExtendedNode
from revizor2.consts import ServerStatus, Dist, Platform
from revizor2.fixtures import manifests


LOG = logging.getLogger(__name__)

OUTLINE_ITERATOR = {}


def get_all_logs_and_info(scenario, outline='', outline_failed=None):
    if CONF.feature.driver.current_cloud == Platform.AZURE:
        return
    # Get Farm
    LOG.warning('Get scalarizr logs after scenario %s' % scenario.name)
    farm = getattr(world, 'farm', None)
    if not farm:
        LOG.error("Farm does not exists. Can't get logs. Exit from step.")
        return
    farm.servers.reload()
    # Get servers
    servers = farm.servers
    # Get test
    test_name = scenario.described_at.file.split('/')[-1].split('.')[0]
    LOG.debug('Test name: %s' % test_name)
    # Get path
    start_time = world.test_start_time
    path = os.path.realpath(os.path.join(CONF.main.log_path, 'scalarizr',
                                         test_name,
                                         start_time.strftime('%m%d-%H:%M'),
                                         scenario.name.replace('/', '-'),
                                         outline))
    LOG.debug('Path to save log: %s' % path)
    if not os.path.exists(path):
        os.makedirs(path, 0755)
    # Get logs && configs
    for server in servers:
        logs = [
            # debug log
            {'file': os.path.join(path, '_'.join((server.id, 'scalarizr_debug.log'))),
             'log_type': 'debug',
             'compress': True},
            # update log
            {'file': os.path.join(path, '_'.join((server.id, 'scalarizr_update.log'))),
             'log_type': 'update',
             'compress': True}]
        if server.status in [ServerStatus.PENDING, ServerStatus.INIT, ServerStatus.RUNNING]:
            try:
                #Get log from remote host
                for log in logs:
                    server.get_log_by_api(**log)
                    LOG.info('Save {log_type} log from server {} to {file}'.format(server.id, **log))
                    #Get configs and role behavior from remote host only for linux family
                    if not Dist.is_windows_family(server.role.dist):
                        file = os.path.join(path, '_'.join((server.id, 'scalr_configs.tar.gz')))
                        server.get_configs(file, compress=True)
                        LOG.info('Download archive with scalr directory and behavior to: {}'.format(file))
            except BaseException, e:
                LOG.error('Error in downloading configs: %s' % e)
                continue
        if server.status == ServerStatus.RUNNING and not CONF.feature.dist.startswith('win'):
            node = world.cloud.get_node(server)
            out = node.run("ps aux | grep 'bin/scal'")[0]
            for line in out.splitlines():
                ram = line.split()[5]
                if len(ram) > 3:
                    ram = '%sMB' % ram[:-3]
                if 'bin/scalr-upd-client' in line:
                    LOG.info('Server %s use %s RAM for update-client' % (server.id, ram))
                    world.wrt(etree.Element('meta', name='szrupdateram', value=ram, serverid=server.id))
                elif 'bin/scalarizr' in line:
                    LOG.info('Server %s use %s RAM for scalarizr' % (server.id, ram))
                    world.wrt(etree.Element('meta', name='szrram', value=ram, serverid=server.id))
    # Save farm, domains and messages info if scenario has failed
    if scenario.failed or outline_failed:
        domains = None
        try:
            domains = IMPL.domain.list(farm_id=farm.id)
        except Exception as e:
            if not 'You do not have permission to view this component' in str(e):
                raise
        LOG.warning("Get farm settings after test failure")
        farm_settings = IMPL.farm.get_settings(farm_id=farm.id)
        if servers:
            LOG.warning("Get scalarizr messages for every server after test failure")
            try:
                for server in servers:
                    server.messages.reload()
                    server_messages = []
                    for msg in server.messages:
                        server_messages.append({msg.name: {'message': msg.message,
                            'date': str(msg.date),
                            'delivered': msg.delivered,
                            'status': msg.status,
                            'type': msg.type,
                            'id': msg.id}})
                    # Save server messages
                    with open(os.path.join(path, '%s_messages.json' % server.id), "w+") as f:
                        f.write(json.dumps(server_messages, indent=2))
            except:
                pass
        # Save farm settings
        with open(os.path.join(path, 'farm_settings.json'), "w+") as f:
            f.write(json.dumps(farm_settings, indent=2))
        # Save domains list
        if domains:
            with open(os.path.join(path, 'domains.json'), "w+") as f:
                f.write(json.dumps(domains, indent=2))


@before.all
def initialize_world():
    setattr(world, 'test_start_time', datetime.now())
    c = Cloud()
    setattr(world, 'cloud', c)


@before.each_feature
def exclude_scenarios_by_version(feature):
    """
    This hook remove some scenarios in depends from role version.
    You can set in .manifest file EXCLUDE_SCENARIOS variable with version software
    and scenarios which You want exclude from test in this role version.

    >>> EXCLUDE_SCENARIOS= {
    >>>    "default": ["Bootstrapping role"],
    >>>    "26": ["Bundling data", "Modifying data"]
    >>> }
    """
    #TODO: Implement version operator > < => =<
    version = 'default'
    if CONF.feature.role_id:
        role = IMPL.role.get(CONF.feature.role_id)
        version = re.findall('(\d+)', role['name'].split('-')[0])
        version = int(version[0]) if version else 'default'

    manifest = os.path.realpath(
        os.path.join(os.path.dirname(feature.scenarios[0].with_file.split('.')[0]),
                     'manifests',
                     feature.described_at.file.split('.')[0].split('/')[-1] + '.manifest')
    )
    if not os.path.isfile(manifest):
        LOG.warning("Manifest file %s doesn't exist")
        return
    manifest = manifests(manifest)
    if 'EXCLUDED_SCENARIOS' in manifest:
        excluded_scenarios_name = manifest['EXCLUDED_SCENARIOS'].get(version, [])
        LOG.info('Exclude the following scenarios %s from test because role version: %s' %
                 (excluded_scenarios_name, version))
        new_scenarios_list = []
        for scenario in feature.scenarios:
            if not scenario.name in excluded_scenarios_name:
                new_scenarios_list.append(scenario)
        if new_scenarios_list:
            feature.scenarios = new_scenarios_list


@before.each_feature
def exclude_steps_by_options(feature):
    """
    Exclude steps from feature for @world.run_only_if
    """
    for scenario in feature.scenarios:
        steps_to_remove = set()
        for step in scenario.steps:
            func = step._get_match(None)[1].function
            if hasattr(func, '_exclude'):
                steps_to_remove.add(step)
        for step in steps_to_remove:
            scenario.steps.remove(step)
        if len(scenario.steps) == 0:
            feature.scenarios.remove(scenario)


@after.outline
def get_logs_and_info_after_outline(*args, **kwargs):
    """Collect logs and additional info if outline failed"""
    scenario = args[0]
    outline_error = args[3]
    if scenario.name in OUTLINE_ITERATOR:
        OUTLINE_ITERATOR[scenario.name] += 1
    else:
        OUTLINE_ITERATOR[scenario.name] = 1
    if outline_error:
        get_all_logs_and_info(scenario, outline=str(OUTLINE_ITERATOR[scenario.name]), outline_failed=outline_error)


@after.each_scenario
def get_logs_and_info_after_scenario(scenario):
    """Give scalarizr_debug.log logs from servers"""
    get_all_logs_and_info(scenario)


@after.all
def cleanup_all(total):
    """If not have problem - stop farm and delete roles, vhosts, domains"""
    LOG.info('Failed steps: %s' % total.steps_failed)
    LOG.debug('Results %s' % total.scenario_results)
    LOG.debug('Passed %s' % total.scenarios_passed)
    if (not total.steps_failed and CONF.feature.stop_farm) or (CONF.feature.stop_farm and CONF.main.te_id):
        LOG.info('Clear and stop farm...')
        farm = getattr(world, 'farm', None)
        if not farm:
            return
        IMPL.farm.clear_roles(world.farm.id)
        bundled_role_id = getattr(world, 'bundled_role_id', None)
        if bundled_role_id:
            LOG.info('Delete bundled role: %s' % bundled_role_id)
            try:
                IMPL.role.delete(bundled_role_id)
            except BaseException, e:
                LOG.exception('Error on deletion role %s' % bundled_role_id)
        cloud_node = getattr(world, 'cloud_server', None)
        if cloud_node:
            LOG.info('Destroy node in cloud')
            try:
                cloud_node.destroy()
            except BaseException, e:
                LOG.exception('Node %s can\'t be destroyed' % cloud_node.id)
        world.farm.terminate()

        world.farm.vhosts.reload()
        if hasattr(world, 'vhosts_list'):
            for vhost in world.vhosts_list:
                LOG.info('Delete vhost: %s' % vhost.name)
                vhost.delete()

        try:
            world.farm.domains.reload()
            for domain in world.farm.domains:
                LOG.info('Delete domain: %s' % domain.name)
                domain.delete()
        except Exception as e:
            if 'You do not have permission to view this component' in e:
                LOG.warning('DNS disabled in Scalr config!')

    else:
        farm = getattr(world, 'farm', None)
        if not farm:
            return
        world.farm.roles.reload()
        for r in world.farm.roles:
            IMPL.farm.edit_role(world.farm.id, r.role_id, options={"system.timeouts.reboot": 999999,
                                                                   "system.timeouts.launch": 999999})
    for v in dir(world):
        if isinstance(getattr(world, v), ExtendedNode):
            world.__delattr__(v)