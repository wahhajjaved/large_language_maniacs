# Copyright (C) 2014  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import ansicolor
import cliapp

import logging
import os
import pipes
import sys

import baserockimport


class BaserockImportApplication(cliapp.Application):
    def add_settings(self):
        self.settings.string(['lorries-dir'],
                             "location for Lorry files",
                             metavar="PATH",
                             default=os.path.abspath('./lorries'))
        self.settings.string(['definitions-dir'],
                             "location for morphology files",
                             metavar="PATH",
                             default=os.path.abspath('./definitions'))
        self.settings.string(['checkouts-dir'],
                             "location for Git checkouts",
                             metavar="PATH",
                             default=os.path.abspath('./checkouts'))
        self.settings.string(['lorry-working-dir'],
                             "Lorry working directory",
                             metavar="PATH",
                             default=os.path.abspath('./lorry-working-dir'))

        self.settings.boolean(['force-stratum-generation', 'force-stratum'],
                              "always create a stratum, overwriting any "
                              "existing stratum morphology, and ignoring any "
                              "components where errors occurred during import",
                              default=False)
        self.settings.boolean(['update-existing'],
                              "update all the checked-out Git trees and "
                              "generated definitions",
                              default=False)
        self.settings.boolean(['use-local-sources'],
                              "use file:/// URLs in the stratum 'repo' "
                              "fields, instead of upstream: URLs",
                              default=False)
        self.settings.boolean(['use-master-if-no-tag'],
                              "if the correct tag for a version can't be "
                              "found, use 'master' instead of raising an "
                              "error",
                              default=False)

    def _stream_has_colours(self, stream):
        # http://blog.mathieu-leplatre.info/colored-output-in-console-with-python.html
        if not hasattr(stream, "isatty"):
            return False
        if not stream.isatty():
            return False # auto color only on TTYs
        try:
            import curses
            curses.setupterm()
            return curses.tigetnum("colors") > 2
        except:
            # guess false in case of error
            return False

    def setup(self):
        self.add_subcommand('omnibus', self.import_omnibus,
                            arg_synopsis='REPO PROJECT_NAME SOFTWARE_NAME')
        self.add_subcommand('rubygems', self.import_rubygems,
                            arg_synopsis='GEM_NAME [GEM_VERSION]')
        self.add_subcommand('python', self.import_python,
                            arg_synopsis='PACKAGE_NAME [VERSION]')

        self.stdout_has_colours = self._stream_has_colours(sys.stdout)

    def setup_logging_formatter_for_file(self):
        root_logger = logging.getLogger()
        root_logger.name = 'main'

        # You need recent cliapp for this to work, with commit "Split logging
        # setup into further overrideable methods".
        return logging.Formatter("%(name)s: %(levelname)s: %(message)s")

    def process_args(self, args):
        if len(args) == 0:
            # Cliapp default is to just say "ERROR: must give subcommand" if
            # no args are passed, I prefer this.
            args = ['help']

        super(BaserockImportApplication, self).process_args(args)

    def status(self, msg, *args, **kwargs):
        text = msg % args
        if kwargs.get('error') == True:
            logging.error(text)
            if self.stdout_has_colours:
                sys.stdout.write(ansicolor.red(text))
            else:
                sys.stdout.write(text)
        else:
            logging.info(text)
            sys.stdout.write(text)
        sys.stdout.write('\n')

    def import_omnibus(self, args):
        '''Import a software component from an Omnibus project.

        Omnibus is a tool for generating application bundles for various
        platforms. See <https://github.com/opscode/omnibus> for more
        information.

        '''
        if len(args) != 3:
            raise cliapp.AppException(
                'Please give the location of the Omnibus definitions repo, '
                'and the name of the project and the top-level software '
                'component.')

        def running_inside_bundler():
            return 'BUNDLE_GEMFILE' in os.environ

        def command_to_run_python_in_directory(directory, args):
            # Bundler requires that we run it from the Omnibus project
            # directory. That messes up any relative paths the user may have
            # passed on the commandline, so we do a bit of a hack to change
            # back to the original directory inside the `bundle exec` process.
            return "cd %s; exec python %s" % (
                pipes.quote(directory), ' '.join(map(pipes.quote, args)))

        def reexecute_self_with_bundler(path):
            script = sys.argv[0]

            logging.info('Reexecuting %s within Bundler, so that extensions '
                         'use the correct dependencies for Omnibus and the '
                         'Omnibus project definitions.', script)
            command = command_to_run_python_in_directory(os.getcwd(), sys.argv)

            logging.debug('Running: `bundle exec %s` in dir %s', command, path)
            os.chdir(path)
            os.execvp('bundle', [script, 'exec', command])

        # Omnibus definitions are spread across multiple repos, and there is
        # no stability guarantee for the definition format. The official advice
        # is to use Bundler to execute Omnibus, so let's do that.
        if not running_inside_bundler():
            reexecute_self_with_bundler(args[0])

        definitions_dir = args[0]
        project_name = args[1]

        loop = baserockimport.mainloop.ImportLoop(
            app=self,
            goal_kind='omnibus', goal_name=args[2], goal_version='master')
        loop.enable_importer('omnibus',
                             extra_args=[definitions_dir, project_name])
        loop.enable_importer('rubygems')
        loop.run()

    def import_rubygems(self, args):
        '''Import one or more RubyGems.'''
        if len(args) not in [1, 2]:
            raise cliapp.AppException(
                'Please pass the name and version of a RubyGem on the '
                'commandline.')

        goal_name = args[0]
        goal_version = args[1] if len(args) == 2 else 'master'

        loop = baserockimport.mainloop.ImportLoop(
            app=self,
            goal_kind='rubygems', goal_name=args[0], goal_version='master')
        loop.enable_importer('rubygems', strata=['strata/ruby.morph'])
        loop.run()

    def import_python(self, args):
        '''Import one or more python packages.'''
        if len(args) < 1 or len(args) > 2:
            raise cliapp.AppException(
                'Please pass the name of the python package on the commandline.')

        package_name = args[0]

        package_version = args[1] if len(args) == 2 else 'master'

        loop = baserockimport.mainloop.ImportLoop(app=self,
                                                  goal_kind='python',
                                                  goal_name=package_name,
                                                  goal_version=package_version)
        loop.enable_importer('python', strata=['strata/core.morph'])
        loop.run()
