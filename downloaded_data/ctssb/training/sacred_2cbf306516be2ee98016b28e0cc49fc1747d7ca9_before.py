#!/usr/bin/env python
# coding=utf-8

from __future__ import division, print_function, unicode_literals
from collections import OrderedDict
import inspect
import os.path
import sys
from host_info import fill_missing_versions

from sacred.arg_parser import get_config_updates, get_observers, parse_args
from sacred.captured_function import create_captured_function
from sacred.commands import print_config
from sacred.config_scope import ConfigScope
from sacred.host_info import get_dependencies
from sacred.initialize import create_run
from utils import print_filtered_stacktrace


__sacred__ = True  # marker for filtering stacktraces when run from commandline


class CircularDependencyError(Exception):
    pass


class Ingredient(object):
    def __init__(self, path, ingredients=(), gen_seed=False,
                 caller_globals=None):
        self.path = path
        self.cfgs = []
        self.ingredients = list(ingredients)
        self.gen_seed = gen_seed
        self.captured_functions = []
        self._is_traversing = False
        self.commands = OrderedDict()
        # capture some context information
        caller_globals = caller_globals or inspect.stack()[1][0].f_globals
        self.doc = caller_globals.get('__doc__') or ""
        self.mainfile = caller_globals.get('__file__') or ""
        if self.mainfile:
            self.mainfile = os.path.abspath(self.mainfile)
        self.dependencies = get_dependencies(caller_globals)

    ############################## Decorators ##################################
    def command(self, f):
        captured_f = self.capture(f)
        self.commands[f.__name__] = captured_f
        return captured_f

    def config(self, f):
        self.cfgs.append(ConfigScope(f))
        return self.cfgs[-1]

    def capture(self, f):
        if f in self.captured_functions:
            return f
        captured_function = create_captured_function(f)
        self.captured_functions.append(captured_function)
        return captured_function

    ################### protected helpers ###################################
    def traverse_ingredients(self):
        if self._is_traversing:
            raise CircularDependencyError()
        else:
            self._is_traversing = True
        yield self, 0
        for ingredient in self.ingredients:
            for sr, depth in ingredient.traverse_ingredients():
                yield sr, depth + 1
        self._is_traversing = False

    def run_command(self, command_name, config_updates=None, loglevel=None):
        run = create_run(self, command_name, config_updates, log_level=loglevel)
        run.logger.info("Running command '%s'" % command_name)
        return run()

    def _gather_commands(self):
        for k, v in self.commands.items():
            yield self.path + '.' + k, v

        for ingred in self.ingredients:
            for k, v in ingred._gather_commands():
                yield k, v


class Experiment(Ingredient):
    def __init__(self, name, ingredients=()):
        caller_globals = inspect.stack()[1][0].f_globals
        super(Experiment, self).__init__(path=name,
                                         ingredients=ingredients,
                                         gen_seed=True,
                                         caller_globals=caller_globals)
        self.name = name
        self.default_command = None
        self.logger = None
        self.observers = []
        self.command(print_config)
        self.info = None

    ############################## Decorators ##################################

    def main(self, f):
        """
        Decorator to define the main function of the experiment.

        The main function of an experiment is the default command that is being
        run when no command is specified, or when calling the run() method.
        """
        captured = self.command(f)
        self.default_command = captured.__name__
        return captured

    def automain(self, f):
        """
        Decorator that defines the main function of the experiment and
        automatically runs the experiment commandline when the file is executed.

        The method decorated by this should be last in the file because:

        .. code-block:: python

            @ex.automain
            def my_main():
                pass

        is equivalent to:

        .. code-block:: python

            @ex.main
            def my_main():
                pass

            if __name__ == '__main__':
                ex.run_commandline()
        """
        captured = self.main(f)
        if f.__module__ == '__main__':
            self.run_commandline()
        return captured

    ############################## public interface ############################

    def get_info(self):
        fill_missing_versions(self.dependencies)

        return dict(
            mainfile=self.mainfile,
            dependencies=self.dependencies,
            doc=self.doc)

    def run(self, config_updates=None, loglevel=None):
        """
        Run the main function of the experiment.

        :param config_updates: Changes to the configuration as a nested dictionary
        :type config_updates: dict
        :param loglevel: Changes to the log-level for this run.
        :type loglevel: int | str

        :return: The result of the main function.
        """
        return self.run_command(self.default_command, config_updates, loglevel)

    def run_commandline(self, argv=None):
        if argv is None:
            argv = sys.argv
        all_commands = self._gather_commands()

        args = parse_args(argv,
                          description=self.doc,
                          commands=OrderedDict(all_commands),
                          print_help=True)
        config_updates = get_config_updates(args['UPDATE'])
        loglevel = args.get('--logging')
        for obs in get_observers(args):
            if obs not in self.observers:
                self.observers.append(obs)

        if args['COMMAND']:
            cmd_name = args['COMMAND']
        else:
            cmd_name = self.default_command

        try:
            return self.run_command(cmd_name,
                                    config_updates=config_updates,
                                    loglevel=loglevel)
        except:
            if args['--debug']:
                raise
            else:
                print_filtered_stacktrace()

    ############################## protected interface #########################

    def _gather_commands(self):
        for k, v in self.commands.items():
            yield k, v

        for ingred in self.ingredients:
            for k, v in ingred._gather_commands():
                yield k, v
