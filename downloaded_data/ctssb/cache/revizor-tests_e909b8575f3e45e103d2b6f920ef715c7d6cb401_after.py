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


@step("script ([\w\d -/]+) executed in ([\w\d]+) by user (\w+) with exitcode (\d+) and contain ([\w\d !:;=>\"/]+)? for ([\w\d]+)")
def assert_check_script_in_log(step, name, event, user, exitcode, contain, serv_as):
    LOG.debug('Check script in log by parameters: \nname: %s\nevent: %s\user: %s\nexitcode: %s\ncontain: %s' %
              (name, event, user, exitcode, contain)
    )
    contain = contain.split(';') if contain else []
    time.sleep(5)
    server = getattr(world, serv_as)
    server.scriptlogs.reload()
    # Convert script name, because scalr convert name to:
    # substr(preg_replace("/[^A-Za-z0-9]+/", "_", $script->name), 0, 50)
    name = re.sub('[^A-Za-z0-9/.]+', '_', name)[:50] if name else name
    for log in server.scriptlogs:
        LOG.debug('Check script log:\nname: %s\nevent: %s\nmessage: %s\nrun as: %s\nexitcode: %s\n' %
                  (log.name, log.event, log.message, log.run_as, log.exitcode))

        if log.event.strip() == event.strip() \
                and log.run_as == user \
                and ((name == 'chef' and log.name.strip().startswith(name))
                     or (name == 'local' and log.name.strip().startswith(name))
                     or log.name.strip() == name):

            LOG.debug('We found event \'%s\' run from user %s' % (log.event, log.run_as))
            if log.exitcode == int(exitcode):
                LOG.debug('Log message output: %s' % log.message)
                for cond in contain:
                    cond = cond.replace('"', '&quot;').replace('>', '&gt;').strip()
                    if not cond.strip() in log.message:
                        raise AssertionError('Script on event "%s" (%s) contain: "%s" but lookup: "%s"'
                                             % (event, user, log.message, cond))
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
        if log in last_scripts:
            continue
        LOG.debug('Server %s log content: %s' % (server.id, log.message))
        if message.strip()[1:-1] in log.message:
            return True
    raise AssertionError("Not see message %s in scripts logs (message: %s)" % (message, log.message))


@step("([\w\d]+) chef runlist has only recipes \[([\w\d,.]+)\]")
def verify_recipes_in_runlist(step, serv_as, recipes):
    recipes = recipes.split(',')
    server = getattr(world, serv_as)
    chef_api = chef.autoconfigure()
    run_list = chef.Node(server.details['hostname']).run_list
    if len(run_list) != len(recipes):
        raise AssertionError('Count of recipes in node is another that must be: "%s" != "%s" "%s"' %
                             (len(run_list), len(recipes), run_list))
    for recipe in recipes:
        if not recipe in ','.join(run_list):
            raise AssertionError('Recipe "%s" not exist in run list!' % run_list)
