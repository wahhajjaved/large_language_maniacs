# -*- coding: utf-8 -*-
import argparse
import sys
import re
import os
import inspect

from clint import args
from clint.textui import colored, puts, min_width, indent


class Error(Exception):
    pass


class Command(object):
    name = None
    namespace = None
    description = 'no description'
    run = None

    def __init__(self, **kwargs):
        for key in kwargs:
            if hasattr(self, key):
                setattr(self, key, kwargs[key])
            else:
                raise Exception('Invalid keyword argument `%s`' % key)

        self.args = []

        if self.name is None:
            self.name = re.sub('(.)([A-Z]{1})', r'\1_\2',
                self.__class__.__name__).lower()

        self.inspect()

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def inspect(self):
        self.arg_names, varargs, keywords, defaults = inspect.getargspec(
            self.run)
        if hasattr(self.run, 'im_self'):
            del self.arg_names[0]  # Removes `self` arg for class method
        if defaults is not None:
            kwargs = dict(zip(*[reversed(l) \
                for l in (self.arg_names, defaults)]))
        else:
            kwargs = []
        for arg_name in self.arg_names:
            arg = Arg(
                arg_name,
                default=kwargs[arg_name] if arg_name in kwargs else None,
                type=type(kwargs[arg_name]) if arg_name in kwargs else None,
                required=not arg_name in kwargs,
            )
            self.add_argument(arg)

    def add_argument(self, arg):
        dest = arg.dest if hasattr(arg, 'dest') else arg.name
        if dest not in self.arg_names:
            raise Exception('Invalid arg %s' % arg.name)
        if self.has_argument(arg.name):
            position = self.arg_names.index(dest)
            self.args[position] = arg
        else:
            self.args.append(arg)

    def has_argument(self, name):
        return name in [arg.name for arg in self.args]

    def run(self, *args, **kwargs):
        raise NotImplementedError

    def parse(self, args):
        parsed_args = self.parser.parse_args(args)
        args, kwargs = [], {}
        position = 0
        for arg_name in self.arg_names:
            arg = self.args[position]
            if arg.required:
                args.append(getattr(parsed_args, arg_name))
            elif hasattr(parsed_args, arg_name):
                kwargs[arg_name] = getattr(parsed_args, arg_name)
            position = position + 1
        try:
            r = self.run(*args, **kwargs)
        except Error as e:
            r = e
        return self.puts(r)

    @property
    def parser(self):
        parser = argparse.ArgumentParser(description=self.description)
        for arg in self.args:
            parser.add_argument(
                arg.name if arg.required else '--%s' % arg.name,
                **arg.kwargs
            )
        return parser

    @property
    def path(self):
        return self.name if self.namespace is None else '%s.%s' % \
            (self.namespace, self.name)

    def puts(self, r):
        stdout = sys.stdout.write
        type_ = type(r)
        if type_ == list:
            [puts(i, stream=stdout) for i in r]
        elif type_ == dict:
            for key in r:
                puts(min_width(colored.blue(key), 25) + r[key])
        elif type_ == Error:
            puts(colored.red(str(r)), stream=stdout)
        else:
            puts(str(r), stream=stdout)


class Manager(object):
    def __init__(self):
        self.commands = {}

    @property
    def Command(self):
        manager = self

        class BoundCommand(Command):
            class __metaclass__(type):
                def __new__(meta, name, bases, dict_):
                    new = type.__new__(meta, name, bases, dict_)
                    if name != 'BoundCommand':
                        manager.add_command(new())
                    return new

        return BoundCommand

    def add_command(self, command):
        self.commands[command.path] = command

    def arg(self, name, **kwargs):
        def wrapper(command):
            def wrapped(**kwargs):
                command.add_argument(Arg(name, **kwargs))
                return command
            return wrapped(**kwargs)

        return wrapper

    def merge(self, manager, namespace=None):
        for command_name in manager.commands:
            command = manager.commands[command_name]
            if namespace is not None:
                command.namespace = namespace
            self.add_command(command)

    def command(self, *args, **kwargs):
        def register(fn):
            def wrapped(**kwargs):
                if not 'name' in kwargs:
                    kwargs['name'] = fn.__name__
                if not 'description' in kwargs and fn.__doc__:
                    kwargs['description'] = fn.__doc__
                command = self.Command(run=fn, **kwargs)
                self.add_command(command)
                return command
            return wrapped(**kwargs)

        if len(args) == 1 and callable(args[0]):
            fn = args[0]
            return register(fn)
        else:
            return register

    def update_env(self):
        path = os.path.join(os.getcwd(), '.env')
        if os.path.isfile(path):
            env = self.parse_env(open(path).read())
            for key in env:
                os.environ[key] = env[key]

    def parse_env(self, content):
        def strip_quotes(string):
            for quote in "'", '"':
                if string.startswith(quote) and string.endswith(quote):
                    return string.strip(quote)
            return string

        regexp = re.compile('^([A-Za-z_0-9]+)=(.*)$', re.MULTILINE)
        founds = re.findall(regexp, content)
        return {key: strip_quotes(value) for key, value in founds}

    @property
    def parser(self):
        parser = argparse.ArgumentParser(
            usage='%(prog)s [<namespace>.]<command> [<args>]')
        parser.add_argument('command', help='the command to run')
        return parser

    def usage(self):
        def format_line(command, w):
            return "%s%s" % (min_width(command.name, w),
                command.description)

        self.parser.print_help()
        if len(self.commands) > 0:
            puts('\navailable commands:')
            with indent(2):
                namespace = None
                for command_path in sorted(self.commands,
                        key=lambda c: '%s%s' % (c.count('.'), c)):
                    command = self.commands[command_path]
                    if command.namespace is not None:
                        if command.namespace != namespace:
                            puts(colored.red('\n[%s]' % command.namespace))
                        with indent(2):
                            puts(format_line(command, 23))
                    else:
                        puts(format_line(command, 25))
                    namespace = command.namespace

    def main(self):
        if len(args) == 0 or args[0] in ('-h', '--help'):
            return self.usage()
        command = args.get(0)
        try:
            command = self.commands[command]
        except KeyError as e:
            puts(colored.red('Invalid command `%s`\n' % command))
            return self.usage()
        self.update_env()
        command.parse(args.all[1:])


class Arg(object):
    defaults = {
        'help': 'no description',
        'required': False,
        'type': None,
    }

    def __init__(self, name, **kwargs):
        self.name = name
        self._kwargs = dict(self.defaults.items() + kwargs.items())

    def __getattr__(self, key):
        return self._kwargs[key]

    @property
    def kwargs(self):
        dict_ = self._kwargs.copy()
        if self.required:
            del dict_['required']
        elif self.type == bool and self.default == False:
            dict_['action'] = 'store_true'
            del dict_['type']
        return dict_
