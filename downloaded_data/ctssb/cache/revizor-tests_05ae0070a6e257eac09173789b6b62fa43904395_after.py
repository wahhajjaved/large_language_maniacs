# coding: utf-8

"""
Created on 09.01.2015
@author: Eugeny Kurkovich
"""
import os
import re
import time
import base64
import github
import logging
try:
    import winrm
except ImportError:
    raise ImportError("Please install WinRM")

from revizor2.api import IMPL
from revizor2.conf import CONF
from lettuce import step, world, after
from urllib2 import URLError

from revizor2.consts import Dist
from distutils.version import LooseVersion
from revizor2.fixtures import tables, resources

LOG = logging.getLogger(__name__)

ORG = 'Scalr'
SCALARIZR_REPO = 'int-scalarizr'
GH = github.GitHub(access_token=CONF.main.github_access_token)


@step(r"I have manually installed scalarizr(?:\s('[\w\W\d]+'))* on ([\w\d]+)")
def havinng_installed_scalarizr(step, version=None, serv_as=None):
    version = (version or '').replace("'", '')
    setattr(world, serv_as, None)
    if version:
        setattr(world, 'default_agent', version.strip())
    step.behave_as("""
        Given I have a clean image
        And I add image to the new role
        When I have a an empty running farm
        Then I add created role to the farm
        And I see pending server {serv_as}
        When I install scalarizr {version} to the server {serv_as}{manually}
        Then I forbid {pkg_type}scalarizr update at startup and run it on {serv_as}
        And I wait and see running server {serv_as}""".format(
            version=version,
            serv_as=serv_as,
            pkg_type='legacy ' if version.strip() == '3.8.5' else 'msi ',
            manually='' if version else ' manually'))


@step(r"I build (new|corrupt) package")
def having_new_package(step, pkg_type):
    if pkg_type == 'new':
        patched = ''
    else:
        patched = ' with patched script'
    step.behave_as("""
        Given I have a copy of the branch{patched}
        Then I wait for new package was built
    """.format(patched=patched))


@step(r"I set branch with (?:corrupt|new) package for role")
def setting_new_devel_branch(step):
   step.given("I change branch to {} for role".format(world.test_branch_copy))


@step(r"I install (?:corrupt|new) package to the server ([\w\d]+)")
def installing_new_package(step, serv_as):
    branch = getattr(world, 'test_branch_copy')
    step.given("I install new scalarizr to the server {} from the branch {}".format(serv_as, branch.strip()))


@step('I have a copy of the(?: (.+))? branch( with patched script)?')
def having_branch_copy(step, branch=None, is_patched=False):
    if branch == 'system':
        # Use environ because CONF.feature replace '/' to '-'
        branch = os.environ.get('RV_BRANCH')
    elif branch == 'new':
        branch = world.test_branch_copy
    elif not branch:
        # Use environ because CONF.feature replace '/' to '-'
        branch = os.environ.get('RV_TO_BRANCH')
    else:
        branch = branch.strip()
    world.test_branch_copy = getattr(world, 'test_branch_copy', 'test-{}'.format(int(time.time())))
    if is_patched:
        fixture_path = 'scripts/scalarizr_app.py'
        script_path = 'src/scalarizr/app.py'
        content = resources(fixture_path).get()
        commit_msg = 'Patch app.py, corrupt windows start'
    else:
        script_path = 'README.md'
        commit_msg = 'Tested build for %s at %s ' % (branch, time.strftime('%-H:%M:%S'))
        content = 'Scalarizr\n=========\n%s' % commit_msg
    LOG.info('Cloning branch: %s to %s' % (branch, world.test_branch_copy))
    git = GH.repos(ORG)(SCALARIZR_REPO).git
    # Get the SHA the current test branch points to
    base_sha = git.refs('heads/%s' % branch).get().object.sha
    # Create a new blob with the content of the file
    blob = git.blobs.post(
        content=base64.b64encode(content),
        encoding='base64')
    # Fetch the tree this base SHA belongs to
    base_commit = git.commits(base_sha).get()
    # Create a new tree object with the new blob, based on the old tree
    tree = git.trees.post(
        base_tree=base_commit.tree.sha,
        tree=[{'path': script_path,
               'mode': '100644',
               'type': 'blob',
               'sha': blob.sha}])
    # Create a new commit object using the new tree and point its parent to the current master
    commit = git.commits.post(
        message=commit_msg,
        parents=[base_sha],
        tree=tree.sha)
    base_sha = commit.sha
    LOG.debug('Scalarizr service was patched. GitHub api res: %s' % commit)
    # Finally update the heads/master reference to point to the new commit
    try:
        res = git.refs.post(ref='refs/heads/%s' % world.test_branch_copy, sha=base_sha)
        LOG.debug('New branch was created. %s' % res)
    except github.ApiError:
        res = git.refs('heads/%s' % world.test_branch_copy).patch(sha=base_sha)
        LOG.debug('New created branch %s was updated.' % res.get('ref'))
    world.build_commit_sha = base_sha


@step(r'I wait for new package was built')
def waiting_new_package(step):
    time_until = time.time() + 2400
    err_msg = ''
    LOG.info('Getting build status for: %s' % world.build_commit_sha)
    while time.time() <= time_until:
        # Get build status
        res = GH.repos(ORG)(SCALARIZR_REPO).commits(world.build_commit_sha).status.get()
        if res.statuses:
            status = filter(lambda x: x['context'] == 'continuous-integration/drone', res.statuses)[0]
            LOG.debug('Patch commit build status: %s' % status)
            if status.state == 'success':
                LOG.info('Drone status: %s' % status.description)
                return
            elif status.state == 'failure':
                err_msg = 'Drone status is failed'
                break
        time.sleep(60)
    raise AssertionError(err_msg or 'Timeout or build status failed.')


@step(r'I have a clean image')
def having_clean_image(step):
    if CONF.feature.dist.is_windows:
        table = tables('images-clean')
        search_cond = dict(
            dist=CONF.feature.dist.id,
            platform=CONF.feature.platform)
        image_id = table.filter(search_cond).first().keys()[0].encode('ascii', 'ignore')
        image = filter(lambda x: x.id == str(image_id), world.cloud.list_images())[0]
    else:
        if CONF.feature.driver.is_platform_ec2 and CONF.feature.dist.id in ['ubuntu-16-04', 'centos-7-x']:
            image = world.cloud.find_image(use_hvm=True)
        else:
            image = world.cloud.find_image(use_hvm=CONF.feature.use_vpc)
    LOG.debug('Obtained clean image %s, Id: %s' %(image.name, image.id))
    setattr(world, 'image', image)


@step(r'I add created role to the farm(?: with (manual scaling)*(stable branch)*)*$')
def setting_farm(step, use_manual_scaling=None, use_stable=None):
    farm = world.farm
    branch = CONF.feature.branch
    cloud_location = CONF.platforms[CONF.feature.platform]['location']
    if CONF.feature.driver.is_platform_gce:
        cloud_location = ""
    role_kwargs = dict(
        location=cloud_location,
        options={
            "user-data.scm_branch": branch if not use_stable else "",
            "base.upd.repository": "stable" if use_stable else "",
            "base.devel_repository": CONF.feature.ci_repo if not use_stable else ""
        },
        alias=world.role['name'],
        use_vpc=CONF.feature.use_vpc
    )
    if CONF.feature.driver.is_platform_ec2 \
            and (CONF.feature.dist.is_windows or CONF.feature.dist.id == 'centos-7-x'):
        role_kwargs['options']['instance_type'] = 'm3.medium'
    if use_manual_scaling:
        manual_scaling = {
            "scaling.one_by_one": 0,
            "scaling.enabled": 0}
        role_kwargs['options'].update(manual_scaling)
    LOG.debug('Add created role to farm with options %s' % role_kwargs)
    farm.add_role(world.role['id'], **role_kwargs)
    farm.roles.reload()
    farm_role = farm.roles[0]
    setattr(world, '%s_role' % world.role['name'], farm_role)


@step(r'I trigger scalarizr update by Scalr UI on ([\w\d]+)$')
def updating_scalarizr_by_scalr_ui(step, serv_as):
    server = getattr(world, serv_as)
    for i in range(5):
        try:
            res = IMPL.server.update_scalarizr(server_id=server.id)
            LOG.debug('Scalarizr update was fired: %s ' % res['successMessage'])
            break
        except Exception as e:
            LOG.error('Scalarizr update status: %s ' % e.message)
            if 'errorMessage' in e.message and 'AlreadyInProgressError' in e.message:
                LOG.warning('Scalarizr update process in progress')
                break
            time.sleep(24)
    else:
        raise Exception("Scalarizr update failed with error: %s" % e)


@step(r'scalarizr version (is default|was updated) in ([\w\d]+)$')
def asserting_version(step, version, serv_as):
    server = getattr(world, serv_as)
    default_installed_agent = getattr(world, 'default_agent', None)
    pre_installed_agent = world.pre_installed_agent
    server.reload()
    command = 'scalarizr -v'
    err_msg = 'Scalarizr version not valid %s:%s'
    # Windows handler
    if CONF.feature.dist.is_windows:
        res = world.run_cmd_command_until(command, server=server, timeout=300).std_out
    # Linux handler
    else:
        node = world.cloud.get_node(server)
        res = node.run(command)[0]
    installed_agent = re.findall('(?:Scalarizr\s)([a-z0-9/./-]+)', res)
    assert installed_agent, "Can't get scalarizr version: %s" % res
    installed_agent = installed_agent[0]
    if default_installed_agent:
        assert LooseVersion(default_installed_agent) == LooseVersion(installed_agent), \
            err_msg % (default_installed_agent, installed_agent)
        world.default_agent = None
        return
    assert LooseVersion(pre_installed_agent) != LooseVersion(installed_agent), \
        err_msg % (pre_installed_agent, installed_agent)
    LOG.debug('Scalarizr was updated. Pre: %s, Inst: %s' %
              (pre_installed_agent, installed_agent))


@step(r"I (check|save) current Scalr update client version(?: was changed)? on ([\w\d]+)")
def checking_upd_client_version(step, action, serv_as):
    server = getattr(world, serv_as)
    server.reload()
    upd_client_staus = server.upd_api.status()
    LOG.info('Scalr upd client status: %s' % upd_client_staus)
    if action == 'save':
        world.upd_client_version = upd_client_staus['service_version']
        LOG.info("Current Scalr update client version: %s" % world.upd_client_version)
        return
    upd_client_version = getattr(world, 'upd_client_version')
    upd_client_current_version = upd_client_staus['service_version']
    assert LooseVersion(upd_client_current_version) > LooseVersion(upd_client_version), \
        "Scalr update client version not valid curr: %s prev: %s" % (upd_client_current_version, upd_client_version)


@step(r'I reboot server in the cloud')
def rebooting_server(step): #FIXME: Find usages
    cloud_server = getattr(world, 'cloud_server')
    if cloud_server:
        assert cloud_server.reboot(), "Can't reboot node: %s" % cloud_server.name
        setattr(world, 'cloud_server', None)


@step(r"I forbid ([\w]+\s)?scalarizr update at startup and run it on ([\w\d]+)$")
def executing_scalarizr(step, pkg_type='', serv_as=None):
    # Create ScalrUpd Client status file
    if pkg_type.strip() == 'legacy':
        cwd = 'c:\Program Files\Scalarizr\Python27'
        env = '''$env:PYTHONPATH = """$env:ProgramFiles\Scalarizr\src"""; '''
    else:
        cwd = 'C:\opt\scalarizr\current\embedded'
        env = ''
    set_status = '''{env}cd """{cwd}"""; ''' \
        '''./python -m scalarizr.updclient.app --make-status-file;'''.format(env=env,cwd=cwd)
    # Run scalarizr
    run_scalarizr = '''Set-Service """ScalrUpdClient""" -startuptype manual; ''' \
        '''Set-Service """Scalarizr""" -startuptype auto; ''' \
        '''Start-Service """Scalarizr"""'''
    server = getattr(world, serv_as.strip())
    server.reload()
    kwargs = dict(server=server, timeout=300)
    assert not world.run_cmd_command_until(
        world.PS_RUN_AS.format(command=set_status),
        **kwargs).std_err, 'Scalr UpdClient status file creatoin failed'
    assert not world.run_cmd_command_until(
        world.PS_RUN_AS.format(command=run_scalarizr),
        **kwargs).std_err, 'Scalarizr execution failed'


@step(r'([\w]+) process is(?: (not))? running on ([\w\d]+)')
def checking_service_state(step, service, is_not, serv_as):
    def get_object(obj, args):
        if len(args) == 1:
            return getattr(obj, args[0])
        return get_object(getattr(obj, args[0]), args[1:])
    service_api = dict(scalarizr='api.system.dist', updclient='upd_api.status')
    server = getattr(world, serv_as)
    try:
        res = get_object(server, service_api[service].split('.'))()
    except URLError as e:
        LOG.error('Got an error while try to get %s status. Err: %s' % (service, e.reason))
        res = False
    assert (res and not is_not) or (not res and is_not), '%s service state not valid' % service


@after.each_scenario
def remove_temporary_data_after_each(scenario):
    use_afret_scenario = ['allow_clean_data']
    use_on_fail = ['allow_clean_on_fail']
    if (scenario.matches_tags(use_afret_scenario) and scenario.passed) or \
            (scenario.matches_tags(use_on_fail) and scenario.failed):
        clear_farm()
        remove_temporary_role()
    remove_temporary_branch()


def clear_farm():
    if getattr(world, 'farm', None):
        IMPL.farm.clear_roles(world.farm.id)
        LOG.info('Farm: %s was cleared' % world.farm.id)


def remove_temporary_role():
    if getattr(world, 'role', None):
        IMPL.role.delete(world.role['id'])
        LOG.info('Temporary role : %s was removed' % world.role['name'])
        IMPL.image.delete(world.role['images'][0]['extended']['hash'])
        LOG.info('Temporary image : %s was removed' % world.role['images'][0]['extended']['name'])


def remove_temporary_branch():
    # Delete github reference(cloned branch)
    if getattr(world, 'test_branch_copy', None):
        try:
            GH.repos(ORG)(SCALARIZR_REPO).git.refs('heads/%s' % world.test_branch_copy).delete()
            LOG.debug('Branch %s was deleted.' % world.test_branch_copy)
        except github.ApiError as e:
            LOG.error(e.message)
