import re
import time
import logging

import chef

from lettuce import world, step

from revizor2.utils import wait_until


LOG = logging.getLogger(__name__)


@step("([\w]+) script executed scalarizr is in '(.+)' state in (.+)")
def assert_check_script(step, message, state, serv_as):
    serv = getattr(world, serv_as)
    wait_until(world.wait_script_execute, args=(serv, message, state), timeout=600,
               error_text='I\'m not see %s scripts execution for server %s' % (message, serv.id))


@step("script ([\w\d -/\:/\.]+) executed in ([\w\d]+) by user (\w+) with exitcode (\d+)(?: and contain ([\w\d \.!:;=>\"/]+)?)? for ([\w\d]+)")
def assert_check_script_in_log(step, name, event, user, exitcode, contain, serv_as):
    LOG.debug('Check script in log by parameters: \nname: %s\nevent: %s\nuser: %s\nexitcode: %s\ncontain: %s' %
              (name, event, user, exitcode, contain))
    contain = contain.split(';') if contain else []
    time.sleep(5)
    server = getattr(world, serv_as)
    server.scriptlogs.reload()
    # Convert script name, because scalr convert name to:
    # substr(preg_replace("/[^A-Za-z0-9]+/", "_", $script->name), 0, 50)
    # name = re.sub('[^A-Za-z0-9/.]+', '_', name)[:50] if name else name
    name = re.sub('[^A-Za-z0-9/.:]+', '_', name)[:50]
    for log in server.scriptlogs:
        LOG.debug('Check script log:\nname: %s\nevent: %s\nrun as: %s\nexitcode: %s\n' %
                  (log.name, log.event, log.run_as, log.exitcode))
        if log.event and log.event.strip() == event.strip() \
                and log.run_as == user \
                and ((name == 'chef' and log.name.strip().startswith(name))
                     or (name.startswith('http') and log.name.strip().startswith(name))
                     or (name.startswith('local') and log.name.strip().startswith(name))
                     or log.name.strip() == name):

            LOG.debug('We found event \'%s\' run from user %s' % (log.event, log.run_as))
            if log.exitcode == int(exitcode):
                message = log.message
                truncated = False
                LOG.debug('Log message output: %s' % message)
                if 'Log file truncated. See the full log in' in message:
                    full_log_path = re.findall(r'Log file truncated. See the full log in ([.\w\d/-]+)', message)[0]
                    node = world.cloud.get_node(server)
                    message = node.run('cat %s' % full_log_path)
                    truncated = True
                for cond in contain:
                    if not truncated:
                        cond = cond.replace('"', '&quot;').replace('>', '&gt;').strip()
                    if not cond.strip() in message:
                        raise AssertionError('Script on event "%s" (%s) contain: "%s" but lookup: "%s"'
                                             % (event, user, message, cond))
                LOG.debug('This event exitcode: %s' % log.exitcode)
                return True
            else:
                raise AssertionError('Script on event \'%s\' (%s) exit with code: %s but lookup: %s'
                                     % (event, user, log.exitcode, exitcode))
    raise AssertionError('I\'m not see script on event \'%s\' (%s) in script logs for server %s' % (event, user, server.id))


@step("script output contains '(.+)' in (.+)$")
def assert_check_message_in_log(step, message, serv_as):
    server = getattr(world, serv_as)
    last_scripts = getattr(world, '_server_%s_last_scripts' % server.id)
    server.scriptlogs.reload()
    for log in server.scriptlogs:
        LOG.debug('Check script "%s" is old' % log.name)
        if log in last_scripts:
            continue
        LOG.debug('Server %s script name "%s" content: "%s"' % (server.id, log.name, log.message))
        if message.strip() in log.message:
            return True
        else:
            raise AssertionError(
                "Not see message '%s' in scripts logs (message: %s)" % (
                    message, log.message))
    raise AssertionError('Can\'t found script with text: "%s"' % message)


@step(r"script result contains '([\w\W]+)?' on ([\w\d]+)")
def assert_check_message_in_log_table_view(step, script_output, serv_as):
    if script_output:
        for line in script_output.split(';'):
            external_step = "script output contains '{result}' in {server}".format(
                result=line.strip(),
                server=serv_as)
            LOG.debug('Run external step: %s' % external_step)
            step.when(external_step)


@step("([\w\d]+) chef runlist has only recipes \[([\w\d,.]+)\]")
def verify_recipes_in_runlist(step, serv_as, recipes):
    recipes = recipes.split(',')
    server = getattr(world, serv_as)

    host_name = world.get_hostname_by_server_format(server)
    chef_api = chef.autoconfigure()

    run_list = chef.Node(host_name, api=chef_api).run_list
    if len(run_list) != len(recipes):
        raise AssertionError('Count of recipes in node is another that must be: "%s" != "%s" "%s"' %
                             (len(run_list), len(recipes), run_list))
    if not all(recipe in ','.join(run_list) for recipe in recipes):
        raise AssertionError('Recipe "%s" not exist in run list!' % run_list)


@step("chef bootstrap failed in ([\w\d]+)")
def chef_bootstrap_failed(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    out = node.run('tail -n 50 /var/log/scalarizr_debug.log')[0]
    if "001-chef.bootstrap/bin/chef.sh']] exited with code 1" not in out and \
        "Command /usr/bin/chef-client exited with code 1" not in out:
        raise AssertionError("Chef bootstrap markers not found in scalarizr_debug.log")
