# coding: utf-8
import os
import sys


# Useful for very coarse version differentiation.
PY3 = sys.version_info[0] == 3

if PY3:
    from configparser import ConfigParser
else:
    from ConfigParser import SafeConfigParser as ConfigParser


class UndefinedValueError(Exception):
    pass


class Undefined(object):
    """
    Class to represent undefined type.
    """
    pass


# Reference instance to represent undefined values
undefined = Undefined()


class Config(object):
    """
    Handle .env file format used by Foreman.
    """
    _BOOLEANS = {'1': True, 'yes': True, 'true': True, 'on': True,
                 '0': False, 'no': False, 'false': False, 'off': False}

    def __init__(self, repository):
        self.repository = repository

    def _cast_boolean(self, value):
        """
        Helper to convert config values to boolean as ConfigParser do.
        """
        if value.lower() not in self._BOOLEANS:
            raise ValueError('Not a boolean: %s' % value)

        return self._BOOLEANS[value.lower()]

    def get(self, option, default=undefined, cast=undefined):
        """
        Return the value for option or default if defined.
        """
        if self.repository.has_key(option):
            value = self.repository.get(option)
        else:
            value = default

        if isinstance(value, Undefined):
            raise UndefinedValueError('%s option not found and default value was not defined.' % option)

        if isinstance(cast, Undefined):
            cast = lambda v: v  # nop
        elif cast is bool:
            cast = self._cast_boolean

        return cast(value)

    def __call__(self, *args, **kwargs):
        """
        Convenient shortcut to get.
        """
        return self.get(*args, **kwargs)


class RepositoryBase(object):
    def __init__(self, source):
        raise NotImplemented

    def has_key(self, key):
        raise NotImplemented

    def get(self, key):
        raise NotImplemented


class RepositoryIni(RepositoryBase):
    """
    Retrieves option keys from .ini files.
    """
    SECTION = 'settings'

    def __init__(self, source):
        self.parser = ConfigParser()
        self.parser.readfp(open(source))

    def has_key(self, key):
        return self.parser.has_option(self.SECTION, key)

    def get(self, key):
        return self.parser.get(self.SECTION, key)


class RepositoryEnv(RepositoryBase):
    """
    Retrieves option keys from .env files with fall back to os.env.
    """
    def __init__(self, source):
        self.data = {}

        for line in open(source):
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            v = v.strip("'").strip('"')
            self.data[k] = v

    def has_key(self, key):
        return key in self.data or key in os.environ

    def get(self, key):
        return self.data[key] or os.environ[key]


class RepositoryShell(RepositoryBase):
    """
    Retrieves option keys from os.env.
    """
    def __init__(self, source=None):
        pass

    def has_key(self, key):
        return key in os.env

    def get(self, key):
        return os.env[key]


class AutoConfig(object):
    """
    Autodetects the config file and type.
    """
    SUPPORTED = {
        'settings.ini': ConfigIni,
        '.env': ConfigEnv,
    }

    def __init__(self):
        self.config = None

    def _find_file(self, path):
        # look for all files in the current path
        for filename in self.SUPPORTED:
            file = os.path.join(path, filename)
            if os.path.exists(file):
                return file

        # search the parent
        parent = os.path.dirname(path)
        if parent and parent != os.path.sep:
            return self._find_file(parent)

        # reached root without finding any files.
        return ''

    def _load(self, path):
        # Avoid unintended permission errors
        try:
            file = self._find_file(path)
        except:
            file = ''
        klass = self.SUPPORTED.get(os.path.basename(file))

        if not klass:
            klass = ConfigShell

        self.config = klass(file)

    def _caller_path(self):
        # MAGIC! Get the caller's module path.
        frame = sys._getframe()
        path = os.path.dirname(frame.f_back.f_back.f_code.co_filename)
        return path

    def __call__(self, *args, **kwargs):
        if not self.config:
            self._load(self._caller_path())

        return self.config(*args, **kwargs)


# A pré-instantiated AutoConfig to improve decouple's usability
# now just import config and start using with no configuration.
config = AutoConfig()
