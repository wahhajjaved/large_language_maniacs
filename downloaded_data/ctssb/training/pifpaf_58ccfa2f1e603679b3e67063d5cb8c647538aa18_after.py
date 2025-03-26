# -*- encoding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import operator
import os
import signal
import subprocess
import sys
import traceback

from cliff import app
from cliff import command
from cliff import commandmanager
from cliff import lister
import daiquiri
import fixtures
import pbr.version
import pkg_resources
import six


LOG = daiquiri.getLogger("pifpaf")


def _format_multiple_exceptions(e, debug=False):
    valid_excs = []
    excs = list(e.args)
    while excs:
        (etype, value, tb) = excs.pop(0)
        if (etype == fixtures.MultipleExceptions):
            excs.extend(value.args)
        elif (etype == fixtures.SetupError):
            continue
        else:
            valid_excs.append((etype, value, tb))

    if len(valid_excs) == 1:
        (etype, value, tb) = valid_excs[0]
        if debug:
            LOG.error("".join(traceback.format_exception(etype, value, tb)))
        else:
            raise value
    else:
        LOG.error("MultipleExceptions raised:")
        for n, (etype, value, tb) in enumerate(valid_excs):
            if debug:
                LOG.error("- exception %d:" % n)
                LOG.error("".join(
                    traceback.format_exception(etype, value, tb)))
            else:
                LOG.error(value)


DAEMONS = list(map(operator.attrgetter("name"),
                   pkg_resources.iter_entry_points("pifpaf.daemons")))


class ListDaemons(lister.Lister):
    """list available daemons"""

    def take_action(self, parsed_args):
        return ("Daemons",), ((n,) for n in DAEMONS)


def create_RunDaemon(daemon):

    class RunDaemon(command.Command):
        def __init__(self, app, app_args, cmd_name=None):
            super(RunDaemon, self).__init__(app, app_args, cmd_name)
            self.plugin = pkg_resources.load_entry_point(
                "pifpaf", "pifpaf.daemons", daemon)

        def get_parser(self, prog_name):
            parser = super(RunDaemon, self).get_parser(prog_name)
            parser = self.plugin.get_parser(parser)
            parser.add_argument("command",
                                nargs='*',
                                help="command to run")
            return parser

        def putenv(self, key, value):
            return os.putenv(self.app.options.env_prefix + "_" + key, value)

        def expand_urls_var(self, url):
            current_urls = os.getenv(self.app.options.global_urls_variable)
            if current_urls:
                return current_urls + ";" + url
            return url

        def take_action(self, parsed_args):
            command = parsed_args.__dict__.pop("command", None)
            driver = self.plugin(env_prefix=self.app.options.env_prefix,
                                 debug=self.app.options.debug,
                                 **parsed_args.__dict__)
            if command:
                try:
                    with driver:
                        self.putenv("PID", str(os.getpid()))
                        self.putenv("DAEMON", daemon)
                        url = os.getenv(driver.env_prefix + "_URL")
                        self.putenv("%s_URL" % daemon.upper(), url)
                        os.putenv(self.app.options.global_urls_variable,
                                  self.expand_urls_var(url))
                        try:
                            c = subprocess.Popen(command)
                        except Exception:
                            raise RuntimeError("Unable to start command: %s"
                                               % " ".join(command))
                        return c.wait()
                except fixtures.MultipleExceptions as e:
                    _format_multiple_exceptions(e, self.app.options.debug)
                    sys.exit(1)
            else:
                try:
                    driver.setUp()
                except fixtures.MultipleExceptions as e:
                    _format_multiple_exceptions(e, self.app.options.debug)
                    sys.exit(1)
                except Exception:
                    LOG.error("Unable to start %s, "
                              "use --debug for more information"
                              % daemon, exc_info=True)
                    sys.exit(1)
                pid = os.fork()
                if pid == 0:
                    os.setsid()
                    devnull = os.open(os.devnull, os.O_RDWR)
                    os.dup2(devnull, 0)
                    os.dup2(devnull, 1)
                    os.dup2(devnull, 2)

                    def _cleanup(signum, frame):
                        driver.cleanUp()
                        sys.exit(0)

                    signal.signal(signal.SIGTERM, _cleanup)
                    signal.signal(signal.SIGHUP, _cleanup)
                    signal.signal(signal.SIGINT, _cleanup)
                    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
                    signal.pause()
                else:
                    url = driver.env['%s_URL' % driver.env_prefix]
                    driver.env.update({
                        "PIFPAF_PID": pid,
                        self.app.options.env_prefix + "_PID": pid,
                        self.app.options.env_prefix + "_DAEMON": daemon,
                        (self.app.options.env_prefix + "_"
                         + daemon.upper() + "_URL"): url,
                        self.app.options.global_urls_variable:
                        self.expand_urls_var(url),
                        "%s_OLD_PS1" % self.app.options.env_prefix:
                        os.getenv("PS1", ""),
                        "PS1":
                        "(pifpaf/" + daemon + ") " + os.getenv("PS1", ""),
                    })
                    for k, v in six.iteritems(driver.env):
                        print("export %s=\"%s\";" % (k, v))
                    print("%(prefix_lower)s_stop () { "
                          "if test -z \"$%(prefix)s_PID\"; then "
                          "echo 'No PID found in $%(prefix)s_PID'; return -1; "
                          "fi; "
                          "if kill $%(prefix)s_PID; then "
                          "_PS1=$%(prefix)s_OLD_PS1; "
                          "unset %(vars)s; "
                          "PS1=$_PS1; unset _PS1; "
                          "unset -f %(prefix_lower)s_stop; "
                          "unalias pifpaf_stop 2>/dev/null || true; "
                          "fi; } ; "
                          "alias pifpaf_stop=%(prefix_lower)s_stop ; "
                          % {"prefix": self.app.options.env_prefix,
                             "prefix_lower":
                             self.app.options.env_prefix.lower(),
                             "vars": " ".join(driver.env)})
        run = take_action

    RunDaemon.__doc__ = "run %s" % daemon
    return RunDaemon


class PifpafCommandManager(commandmanager.CommandManager):
    COMMANDS = dict(("run " + k, create_RunDaemon(k)) for k in DAEMONS)
    COMMANDS.update({"list": ListDaemons})

    def load_commands(self, namespace):
        for name, command_class in six.iteritems(self.COMMANDS):
            self.add_command(name, command_class)


class PifpafApp(app.App):
    CONSOLE_MESSAGE_FORMAT = "%(levelname)s: %(name)s: %(message)s"

    def __init__(self):
        super(PifpafApp, self).__init__(
            "Daemon management tool for testing",
            pbr.version.VersionInfo('pifpaf').version_string(),
            command_manager=PifpafCommandManager(None))

    def build_option_parser(self, description, version):
        parser = super(PifpafApp, self).build_option_parser(
            description, version)
        parser.add_argument(
            "--env-prefix", "-e",
            default="PIFPAF",
            help="prefix to use for environment variables (default: PIFPAF)")
        parser.add_argument(
            "--global-urls-variable", "-g",
            default="PIFPAF_URLS",
            help="global variable name to use to append connection URL when  "
            "chaining multiple pifpaf instances (default: PIFPAF_URLS)")

        return parser

    def configure_logging(self):
        formatter = daiquiri.formatter.ColorFormatter(
            fmt="%(color)s%(levelname)s "
            "[%(name)s] %(message)s%(color_stop)s")

        outputs = [
            daiquiri.output.Stream(sys.stderr, formatter=formatter)
        ]

        if self.options.log_file:
            outputs.append(daiquiri.output.File(self.options.log_file,
                                                formatter=formatter))

        if self.options.debug:
            level = logging.DEBUG
        elif self.options.verbose_level == 1:
            level = logging.INFO
        else:
            level = logging.WARNING

        daiquiri.setup(outputs=outputs, level=level)


def main():
    return PifpafApp().run(sys.argv[1:])


if __name__ == '__main__':
    main()
