#!/usr/bin/python
# -*- coding: utf-8 -*-

#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
from ast import literal_eval
from datetime import datetime
import inspect
import gc
import logging
import os

import shutil
import subprocess

from tarfile import TarFile
from urllib2 import urlopen

from config import BOT_DATA_DIR, BOT_LOG_FILE, BOT_PREFIX
from errbot import botcmd
from errbot.backends.base import Backend

from errbot.plugin_manager import get_all_active_plugin_names, deactivate_all_plugins, update_plugin_places, get_all_active_plugin_objects, get_all_plugins, global_restart, get_all_plugin_names, activate_plugin_with_version_check, deactivatePluginByName, get_plugin_obj_by_name, PluginConfigurationException, check_dependencies
from errbot.storage import StoreMixin
from errbot.utils import PLUGINS_SUBDIR, human_name_for_git_url, tail, format_timedelta, which, get_jid_from_message
from errbot.repos import KNOWN_PUBLIC_REPOS
from errbot.version import VERSION

PLUGIN_DIR = BOT_DATA_DIR + os.sep + PLUGINS_SUBDIR

def get_class_that_defined_method(meth):
  for cls in inspect.getmro(meth.im_class):
    if meth.__name__ in cls.__dict__: return cls
  return None

class ErrBot(Backend, StoreMixin):
    """ Commands related to the bot administration """
    MSG_ERROR_OCCURRED = 'Computer says nooo. See logs for details.'
    MSG_UNKNOWN_COMMAND = 'Unknown command: "%(command)s". '
    startup_time = datetime.now()

    def __init__(self, *args, **kwargs):
        self.open_storage(BOT_DATA_DIR + os.sep + 'core.db')
        # be sure we have a configs entry for the plugin configurations
        if not self.has_key('configs'):
            self['configs'] = {}
        super(ErrBot, self).__init__(*args, **kwargs)

    # Repo management
    def get_installed_plugin_repos(self):
        return self.get('repos', {})

    def add_plugin_repo(self, name, url):
        repos = self.get_installed_plugin_repos()
        repos[name] = url
        self['repos'] = repos

    # plugin blacklisting management
    def get_blacklisted_plugin(self):
        return self.get('bl_plugins', [])

    def is_plugin_blacklisted(self, name):
        return name in self.get_blacklisted_plugin()

    def blacklist_plugin(self, name):
        if self.is_plugin_blacklisted(name):
            logging.warning('Plugin %s is already blacklisted' % name)
            return
        self['bl_plugins'] = self.get_blacklisted_plugin() + [name]
        logging.info('Plugin %s is now blacklisted' % name)

    def unblacklist_plugin(self, name):
        if not self.is_plugin_blacklisted(name):
            logging.warning('Plugin %s is not blacklisted' % name)
            return
        l = self.get_blacklisted_plugin()
        l.remove(name)
        self['bl_plugins'] = l
        logging.info('Plugin %s is now unblacklisted' % name)

    # configurations management
    def get_plugin_configuration(self, name):
        configs = self['configs']
        if not configs.has_key(name):
            return None
        return configs[name]

    def set_plugin_configuration(self, name, obj):
        configs = self['configs']
        configs[name] = obj
        self['configs'] = configs

    # this will load the plugins the admin has setup at runtime
    def update_dynamic_plugins(self):
        all_candidates, errors = update_plugin_places([PLUGIN_DIR + os.sep + d for d in self.get('repos', {}).keys()])
        self.all_candidates = all_candidates
        return errors

    def send_message(self, mess):
        super(ErrBot, self).send_message(mess)
        # Act only in the backend tells us that this message is OK to broadcast
        for bot in get_all_active_plugin_objects():
            try:
                bot.callback_botmessage(mess)
            except Exception:
                logging.exception("Crash in a callback_botmessage handler")

    def callback_message(self, conn, mess):
        if super(ErrBot, self).callback_message(conn, mess):
            # Act only in the backend tells us that this message is OK to broadcast
            for bot in get_all_active_plugin_objects():
                try:
                    bot.callback_message(conn, mess)
                except Exception:
                    logging.exception("Crash in a callback_message handler")

    def activate_non_started_plugins(self):
        logging.info('Activating all the plugins...')
        configs = self['configs']
        errors = ''
        for pluginInfo in get_all_plugins():
            try:
                if self.is_plugin_blacklisted(pluginInfo.name):
                    errors += 'Notice: %s is blacklisted, use ' + BOT_PREFIX + 'load %s to unblacklist it\n' % (pluginInfo.name, pluginInfo.name)
                    continue
                if hasattr(pluginInfo, 'is_activated') and not pluginInfo.is_activated:
                    logging.info('Activate plugin: %s' % pluginInfo.name)
                    activate_plugin_with_version_check(pluginInfo.name, configs.get(pluginInfo.name, None))
            except Exception, e:
                logging.exception("Error loading %s" % pluginInfo.name)
                errors += 'Error: %s failed to start : %s\n' % (pluginInfo.name ,e)
        if errors: self.warn_admins(errors)
        return errors

    def signal_connect_to_all_plugins(self):
        for bot in get_all_active_plugin_objects():
            if hasattr(bot, 'callback_connect'):
                try:
                    bot.callback_connect()
                except Exception as e:
                    logging.exception("callback_connect failed for %s" % bot)

    def connect_callback(self):
        logging.info('Activate internal commands')
        loading_errors = self.activate_non_started_plugins()
        logging.info(loading_errors)
        logging.info('Notifying connection to all the plugins...')
        self.signal_connect_to_all_plugins()
        logging.info('Plugin activation done.')
        self.inject_commands_from(self)

    def disconnect_callback(self):
        self.remove_commands_from(self)
        logging.info('Disconnect callback, deactivating all the plugins.')
        deactivate_all_plugins()


    def shutdown(self):
        logging.info('Shutdown.')
        self.close_storage()
        logging.info('Bye.')

    @botcmd(template = 'status')
    def status(self, mess, args):
        """ If I am alive I should be able to respond to this one
        """
        all_blacklisted = self.get_blacklisted_plugin()
        all_loaded = get_all_active_plugin_names()
        all_attempted = sorted([p.name for p in self.all_candidates])
        plugins_statuses = []
        for name in all_attempted:
            if name in all_blacklisted:
                plugins_statuses.append(('B', name))
            elif name in all_loaded:
                plugins_statuses.append(('L', name))
            elif get_plugin_obj_by_name(name) is not None and get_plugin_obj_by_name(name).get_configuration_template() is not None and self.get_plugin_configuration(name) is None:
                plugins_statuses.append(('C', name))
            else:
                plugins_statuses.append(('E', name))

        try:
            from posix import getloadavg
            loads = getloadavg()
        except Exception as e:
            loads = None
        return {'plugins_statuses' : plugins_statuses, 'loads' : loads, 'gc' : gc.get_count()}

    @botcmd
    def echo(self, mess, args):
        return args

    @botcmd
    def uptime(self, mess, args):
        """ Return the uptime of the bot
        """
        return 'I up for %s %s (since %s)' % (args, format_timedelta(datetime.now() - self.startup_time), datetime.strftime(self.startup_time, '%A, %b %d at %H:%M'))

    @botcmd(admin_only = True)
    def export_configs(self, mess, args):
        """ Returns all the configs in form of a string you can backup
        """
        return str(self.get('configs', {}))

    @botcmd(admin_only = True)
    def import_configs(self, mess, args):
        """ Restore the configs from an export from !export configs
        It will merge with preexisting configurations.
        """
        orig = self.get('configs', {})
        added = literal_eval(args)
        if type(added) is not dict:
            raise Exception('Weird, it should be a dictionary')
        self['configs']=dict(orig.items() + added.items())
        return "Import is done correctly, there are %i config entries now." % len(self.internal_shelf['configs'])

    @botcmd(admin_only = True)
    def zap_configs(self, mess, args):
        """ WARNING : Deletes all the configuration of all the plugins
        """
        self['configs']={}
        return "Done"

    @botcmd(admin_only = True)
    def repos_export(self, mess, args):
        """ Returns all the repos in form of a string you can backup
        """
        return str(self.get_installed_plugin_repos())

    @botcmd(admin_only = True)
    def restart(self, mess, args):
        """ restart the bot """
        self.send(mess.getFrom(), "Deactivating all the plugins...")
        deactivate_all_plugins()
        self.send(mess.getFrom(), "Restarting")
        global_restart()
        return "I'm restarting..."

    def activate_plugin(self, name):
        try:
            if name in get_all_active_plugin_names():
                return "Plugin already in active list"
            if name not in get_all_plugin_names():
                return "I don't know this %s plugin" % name
            activate_plugin_with_version_check(name, self.get_plugin_configuration(name))
        except Exception, e:
            logging.exception("Error loading %s" % name)
            return '%s failed to start : %s\n' % (name ,e)
        return "Plugin %s activated" % name

    def deactivate_plugin(self, name):
        if name not in get_all_active_plugin_names():
            return "Plugin %s not in active list" % name
        deactivatePluginByName(name)
        return "Plugin %s deactivated" % name

    @botcmd(admin_only = True)
    def load(self, mess, args):
        """load a plugin"""
        self.unblacklist_plugin(args)
        return self.activate_plugin(args)

    @botcmd(admin_only = True)
    def unload(self, mess, args):
        """unload a plugin"""
        if args not in get_all_active_plugin_names():
            return '%s in not active' % args
        self.blacklist_plugin(args)
        return self.deactivate_plugin(args)

    @botcmd(admin_only = True)
    def reload(self, mess, args):
        """reload a plugin"""
        if self.is_plugin_blacklisted(args):
            self.unblacklist_plugin(args)
        result = "%s / %s" % (self.deactivate_plugin(args), self.activate_plugin(args))
        return result

    @botcmd(admin_only = True)
    def repos_install(self, mess, args):
        """ install a plugin repository from the given source or a known public repo (see !repos to find those).
        for example from a known repo : !install err-codebot
        for example a git url : git@github.com:gbin/plugin.git
        or an url towards a tar.gz archive : http://www.gootz.net/plugin-latest.tar.gz
        """
        if not args.strip():
            return "You should have an urls/git repo argument"
        if args in KNOWN_PUBLIC_REPOS:
            args = KNOWN_PUBLIC_REPOS[args][0] # replace it by the url
        git_path = which('git')

        if not git_path:
            return 'git command not found: You need to have git installed on your system to by able to install git based plugins.'

        if args.endswith('tar.gz'):
            tar = TarFile(fileobj=urlopen(args))
            tar.extractall(path= PLUGIN_DIR)
            human_name = args.split('/')[-1][:-7]
        else:
            human_name = human_name_for_git_url(args)
            p = subprocess.Popen([git_path, 'clone', args, human_name], cwd = PLUGIN_DIR, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            feedback = p.stdout.read()
            error_feedback = p.stderr.read()
            if p.wait():
               return "Could not load this plugin : \n%s\n---\n%s" % (feedback, error_feedback)
        self.add_plugin_repo(human_name, args)
        errors = self.update_dynamic_plugins()
        if errors:
            self.send(mess.getFrom(), 'Some plugins are generating errors:\n' + '\n'.join(errors) , message_type=mess.getType())
        else:
            self.send(mess.getFrom(), "A new plugin repository named %s has been installed correctly from %s. Refreshing the plugins commands..." % (human_name, args), message_type=mess.getType())
        self.activate_non_started_plugins()
        return "Plugin reload done."

    @botcmd(admin_only = True)
    def repos_uninstall(self, mess, args):
        """ uninstall a plugin repository by name.
        """
        if not args.strip():
            return "You should have a repo name as argument"
        repos = self.get('repos', {})
        if not repos.has_key(args):
            return "This repo is not installed check with ' + BOT_PREFIX + 'repos the list of installed ones"

        plugin_path = PLUGIN_DIR + os.sep + args
        for plugin in get_all_plugins():
            if plugin.path.startswith(plugin_path) and hasattr(plugin,'is_activated') and plugin.is_activated:
                self.send(mess.getFrom(), '/me is unloading plugin %s' % plugin.name)
                self.deactivate_plugin(plugin.name)

        shutil.rmtree(plugin_path)
        repos.pop(args)
        self['repos'] = repos

        return 'Plugins unloaded and repo %s removed' % args


    @botcmd(template='repos')
    def repos(self, mess, args):
        """ list the current active plugin repositories
        """
        installed_repos = self.get_installed_plugin_repos()
        all_names = sorted(set([name for name in KNOWN_PUBLIC_REPOS] + [name for name in installed_repos]))
        max_width = max([len(name) for name in all_names])
        return {'repos':[(repo_name in installed_repos, repo_name in KNOWN_PUBLIC_REPOS, repo_name.ljust(max_width), KNOWN_PUBLIC_REPOS[repo_name][1] if repo_name in KNOWN_PUBLIC_REPOS else installed_repos[repo_name]) for repo_name in all_names]}


    def get_doc(self, command):
        """Get command documentation
        """
        if not command.__doc__:
            return '(undocumented)'
        if BOT_PREFIX == '!':
            return command.__doc__
        return command.__doc__.replace('!', BOT_PREFIX)

    @botcmd
    def help(self, mess, args):
        """   Returns a help string listing available options.

        Automatically assigned to the "help" command."""
        if not args:
            description = 'Available commands:'

            clazz_commands = {}
            for (name, command) in self.commands.iteritems():
                clazz = get_class_that_defined_method(command)
                commands = clazz_commands.get(clazz, [])
                commands.append((name, command))
                clazz_commands[clazz] = commands

            usage = ''
            for clazz in sorted(clazz_commands):
                usage += '\n\n%s: %s\n' % (clazz.__name__, clazz.__doc__ or '')
                usage += '\n'.join(sorted([
                '\t' + BOT_PREFIX + '%s: %s' % (name.replace('_', ' ', 1), 
                    (self.get_doc(command).strip()).split('\n', 1)[0])
                for (name, command) in clazz_commands[clazz] if name != 'help' and not command._err_command_hidden
                ]))
            usage += '\n\n'
        else:
            return super(ErrBot, self).help(mess,'_'.join(args.strip().split(' ')))

        top = self.top_of_help_message()
        bottom = self.bottom_of_help_message()
        return ''.join(filter(None, [top, description, usage, bottom]))

    @botcmd
    def about(self, mess, args):
        """   Returns some information about this err instance"""

        result = 'Err version %s \n\n' % VERSION
        result += 'Authors: Mondial Telecom, Guillaume BINET, Tali PETROVER, Ben VAN DAELE, Paul LABEDAN and others.\n\n'
        return result

    @botcmd
    def apropos(self, mess, args):
        """   Returns a help string listing available options.

        Automatically assigned to the "help" command."""
        if not args:
            return 'Usage: ' + BOT_PREFIX + 'apropos search_term'

        description = 'Available commands:\n'

        clazz_commands = {}
        for (name, command) in self.commands.iteritems():
            clazz = get_class_that_defined_method(command)
            commands = clazz_commands.get(clazz, [])
            commands.append((name, command))
            clazz_commands[clazz] = commands

        usage = ''
        for clazz in sorted(clazz_commands):
            usage += '\n'.join(sorted([
            '\t' + BOT_PREFIX + '%s: %s' % (name.replace('_', ' ', 1), (command.__doc__ or
                                '(undocumented)').strip().split('\n', 1)[0])
            for (name, command) in clazz_commands[clazz] if args is not None and command.__doc__ is not None and args.lower() in command.__doc__.lower() and name != 'help' and not command._err_command_hidden
            ]))
        usage += '\n\n'

        top = self.top_of_help_message()
        bottom = self.bottom_of_help_message()
        return ''.join(filter(None, [top, description, usage, bottom])).strip()

    @botcmd(split_args_with = ' ', admin_only = True)
    def repos_update(self, mess, args):
        """ update the bot and/or plugins
        use : !repos update all
        to update everything
        or : !repos update core
        to update only the core
        or : !repos update repo_name repo_name ...
        to update selectively some repos
        """
        git_path = which('git')
        if not git_path:
            return 'git command not found: You need to have git installed on your system to by able to update git based plugins.'

        directories = set()
        repos = self.get('repos', {})
        core_to_update = 'all' in args or 'core' in args
        if core_to_update:
            directories.add(os.path.dirname(__file__))

        if 'all' in args:
            directories.update([PLUGIN_DIR+os.sep+name for name in repos])
        else:
            directories.update([PLUGIN_DIR+os.sep+name for name in set(args).intersection(set(repos))])

        for d in directories:
            self.send(mess.getFrom(), "I am updating %s ..." % d , message_type=mess.getType())
            p = subprocess.Popen([git_path, 'pull'], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            feedback = p.stdout.read() + '\n' + '-'*50 + '\n'
            err = p.stderr.read().strip()
            if err:
                feedback += err + '\n' + '-'*50 + '\n'
            dep_err = check_dependencies(d)
            if dep_err:
                feedback += dep_err + '\n'
            if p.wait():
                self.send(mess.getFrom(), "Update of %s failed...\n\n%s\n\n resuming..." % (d,feedback) , message_type=mess.getType())
            else:
                self.send(mess.getFrom(), "Update of %s succeeded...\n\n%s\n\n" % (d,feedback) , message_type=mess.getType())
                if not core_to_update:
                    for plugin in get_all_plugins():
                        if plugin.path.startswith(d) and hasattr(plugin,'is_activated') and plugin.is_activated:
                            name = plugin.name
                            self.send(mess.getFrom(), '/me is reloading plugin %s' % name)
                            self.deactivate_plugin(plugin.name)                     # calm the plugin down
                            module = __import__(plugin.path.split(os.sep)[-1]) # find back the main module of the plugin
                            reload(module)                                     # reload it
                            class_name = type(plugin.plugin_object).__name__   # find the original name of the class
                            newclass = getattr(module, class_name)             # retreive the corresponding new class
                            plugin.plugin_object.__class__ = newclass          # BAM, declare the instance of the new type
                            self.activate_plugin(plugin.name)                  # wake the plugin up
        if core_to_update:
            self.restart(mess, '')
            return "You have updated the core, I need to restart."
        return "Done."

    @botcmd(split_args_with = ' ', admin_only = True)
    def config(self, mess, args):
        """ configure or get the configuration / configuration template for a specific plugin
        ie.
        !config ExampleBot
        could return a template if it is not configured:
        {'LOGIN': 'example@example.com', 'PASSWORD': 'password', 'DIRECTORY': '/toto'}
        Copy paste, adapt so can configure the plugin :
        !config ExampleBot {'LOGIN': 'my@email.com', 'PASSWORD': 'myrealpassword', 'DIRECTORY': '/tmp'}
        It will then reload the plugin with this config.
        You can at any moment retreive the current values:
        !config ExampleBot
        should return :
        {'LOGIN': 'my@email.com', 'PASSWORD': 'myrealpassword', 'DIRECTORY': '/tmp'}
        """
        plugin_name = args[0]
        if self.is_plugin_blacklisted(plugin_name):
            return 'Load this plugin first with ' + BOT_PREFIX + 'load %s' % plugin_name
        obj = get_plugin_obj_by_name(plugin_name)
        if obj is None:
            return 'Unknown plugin or the plugin could not load %s' % plugin_name
        template_obj = obj.get_configuration_template()
        if template_obj is None:
            return 'This plugin is not configurable.'

        if len(args) == 1:
            current_config = self.get_plugin_configuration(plugin_name)
            if current_config:
                return 'Copy paste and adapt one of the following:\nDefault Config: ' + BOT_PREFIX + 'config %s %s\nCurrent Config: !config %s %s' % (plugin_name, repr(template_obj), plugin_name, repr(current_config))
            return 'Copy paste and adapt of the following:\n' + BOT_PREFIX + 'config %s %s' % (plugin_name, repr(template_obj))

        try:
            real_config_obj = literal_eval(' '.join(args[1:]))
        except Exception as e:
            logging.exception('Invalid expression for the configuration of the plugin')
            return 'Syntax error in the given configuration'
        if type(real_config_obj) != type(template_obj):
            return 'It looks fishy, your config type is not the same as the template !'

        self.set_plugin_configuration(plugin_name, real_config_obj)
        self.deactivate_plugin(plugin_name)
        try:
            self.activate_plugin(plugin_name)
        except PluginConfigurationException, ce:
            logging.debug('Invalid configuration for the plugin, reverting the plugin to unconfigured')
            self.set_plugin_configuration(plugin_name, None)
            return 'Incorrect plugin configuration: %s' % ce
        return 'Plugin configuration done.'

    @botcmd
    def log_tail(self, mess, args):
        """ Display a tail of the log of n lines or 40 by default
        use : !log tail 10
        """
        #admin_only(mess) # uncomment if paranoid.
        n = 40
        if args.isdigit():
            n = int(args)

        if BOT_LOG_FILE:
            with open(BOT_LOG_FILE, 'r') as f:
                return tail(f, n)
        return 'No log is configured, please define BOT_LOG_FILE in config.py'




