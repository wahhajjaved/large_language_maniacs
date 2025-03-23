#!/usr/bin/env python3

import time
import sys
from traceback import format_exc as Trace

# filename for logs (str)
LOG_FILE = "log.txt"

# how to show user time (str)
SHOW_TIME_FORMAT = "%d.%m.%Y %H:%M:%S"


class Parent:
    def __init__(self, **kwargs):
        """
            plugins - dict : key as str => dict {
                  target -> module/class,
                  dependes -> list of key,
                  module -> True if that's module,
                  args -> tuple of args for plugins (optional)
            }
        """
        try:
            defaults = {
                'name': 'KFrame',
                'plugins': {},
                'log_file': LOG_FILE,
            }
            self.cfg = {k: kwargs[k] if k in kwargs else defaults[k] for k in defaults}
            self.name = self.cfg['name']

            # variables
            self.debug = '--debug' in sys.argv[1:]
            self.plugins = {}
            self.modules = {}
            self.RUN_FLAG = True  # U can use this falg as a signal to stop program

            self._argv_p = {}      # keep params and flags
            self._argv_rules = {}  # collected rules from all plugins
            self._params = {}
            self._my_argvs = {
                '-h': {'critical': False, 'description': 'See this message again'},
                '-?': {'critical': False, 'description': 'See this message again'},
                '--help': {'critical': False, 'description': 'See this message again'},
                '--stdout': {'critical': False, 'description': 'Extra print logs to stdout'},
                '--debug': {'critical': False, 'description': 'Verbose log'},
                '--no-log': {'critical': False, 'description': 'Do not save logs'},

            }
            # list of strings
            self._log_storage = []
            # flag; if true -> keep logs in storage
            self._log_store = False
            # predefined log levels
            self.levels = {
                'debug': 'Debug',
                'info': 'Info',
                'warning': 'Warning',
                'error': 'Error',
                'critical': 'Critical',
            }

            self.plugin_t = self.cfg['plugins']

            if any(
                map(
                    lambda pl: any(
                        map(
                            lambda x: x not in pl,
                            {'target', 'module'}
                        )
                    ),
                    self.plugin_t.values()
                )
            ):
                raise ValueError('Plugin does not has important propery "target" or "module"')

            self.FATAL = False
            self.errmsg = []
        except Exception as e:
            e = Trace()
            self.FATAL = True
            self.errmsg = ["Parent init : {}".format(e)]

    def collect_argv(self):
        rules = dict(self._my_argvs)
        rules.update(self._params)
        for i in self.plugins:
            r = self.plugins[i].get_argv_rules()
            for j in r:
                if j not in rules:
                    rules[j] = r[j]
                else:
                    rules[j]['critical'] = rules[j]['critical'] or r[j]['critical']
        self._argv_rules = rules

    def parse_argv(self):
        """
            parse argv according to plugin's rules
        """
        self.collect_argv()
        for arg in sys.argv[1:]:
            if '=' in arg:
                key = arg.split('=')
                value = key[1]
                key = key[0]
            else:
                key = arg
                value = True
            self._argv_p[key] = value
        return self

    def check_critiacal_argv(self):
        """
            check if all critical argv were passed
            set FATAL True if not all passed
        """
        if any(
            map(
                lambda x: self._argv_rules[x]['critical'] and x not in self._argv_p,
                self._argv_rules.keys()
            )
        ):
            self.FATAL = True
            self.errmsg += ["Parent: parse-argv: not all critical params were passed"]
        return self

    def _init_plugins(self):
        """
            initialize plugins and modules
        """
        try:
            d = dict(self.plugin_t)
            az = []
            bz = list(self.plugin_t.keys())
            i = 0
            _len = len(bz)
            while i < _len and len(bz) > 0:
                for j in list(d.keys()):
                    if d[j]['module']:
                        d.pop(j)
                        az.append(j)
                        if j in bz:
                            bz.pop(bz.index(j))
                    else:
                        d[j]['dependes'] = list(filter(lambda x: x not in az and x in d, d[j]['dependes']))
                        if len(d[j]['dependes']) <= 0:
                            d.pop(j)
                            az.append(j)
                            if j in bz:
                                bz.pop(bz.index(j))
                i += 1
            for i in az:
                try:
                    a, b = self.__init_plugin(
                        key=i,
                        plugin_name=i,
                        args=self.plugin_t[i]['args'],
                        kwargs=self.plugin_t[i]['kwargs']
                    )
                    self.FATAL = self.FATAL or not a
                    self.errmsg.append(b)
                except Exception as e:
                    self.FATAL = True
                    self.errmsg.append('-- plugin (%s) init: %s' % (i, e))
        except Exception as e:
            e = Trace()
            self.errmsg.append('Parent: init-plugins: %s' % e)
            self.FATAL = True

    def __init_plugin(self, key, plugin_name, args, kwargs, export=False):
        """
            initialize plugin with plugin_name
            and save it with key
            if export:
              return initilized object (plugin or module)
            else:
              return True on success , extra msg (errmsg)
        """
        if key not in self.plugin_t:
            if export:
                raise ValueError('Plugin %s not added' % key)
            else:
                return False, '%s: Plugin %s not added' % (plugin_name, key)
        try:
            if self.plugin_t[key]['module']:
                obj = self.plugin_t[plugin_name]['target']
                if export:
                    return obj
                self.modules[key] = obj
                setattr(self, key, obj)
                return True, 'loaded successfully - %s' % (plugin_name)
            else:
                obj = self.plugin_t[plugin_name]['target'](self, plugin_name, args, kwargs)
                if export:
                    return obj
                self.plugins[key] = obj
                setattr(self, key, obj)
                return not self.plugins[key].FATAL, self.plugins[key].errmsg
        except Exception as e:
            e = Trace()
            self.log('Parent: init plugin(%s): %s' % (plugin_name, e), _type='error')
            return False, '%s: Exception: %s' % (plugin_name, e)

    def print_errmsg(self):
        """
            print plugins' initializations status
        """
        _type = 'critical' if self.FATAL else 'info'
        if not self.FATAL and any(map(lambda x: x.FATAL, self.plugins.values())):
            _type = 'error'
        for i in self.errmsg:
            self.log('\t' + i, _type=_type)

    def print_help(self):
        """
            print all expected
        """
        def topic(name):
            st = name
            while len(st) < 20:
                st = " %s " % st
            st = '|%s|' % st
            x = '-' if len(st) % 2 else ''
            return "".join([" " for i in range(16)]) + "+-------------------%s-+\n" % x + "".join(
                [" " for i in range(16)]
            ) + st + "\n" + "".join(
                [" " for i in range(16)]
            ) + "+-------------------%s-+\n" % x

        def insert_tabs(txt, tabs):
            return "".join(
                list(
                    map(
                        lambda x: ''.join(
                            ['\t' for i in range(tabs)]
                        ) + x + '\n',
                        txt.split('\n')
                    )
                )
            )
        st = topic(self.name) + 'Flags:\n'
        self.collect_argv()
        for i in self._argv_rules:
            st += '\t{key}\n{desc}{critical}\n\n'.format(
                key=i,
                desc=insert_tabs(
                    self._argv_rules[i]['description'],
                    tabs=2
                ),
                critical='\n\t\tCritical!' if self._argv_rules[i]['critical'] else ''
            )
        print(st)

    def run(self):
        """
            start all plugins
        """
        self.log('PARENT: start plugins', _type='debug')
        for i in filter(
            lambda x: self.plugin_t[x]['autostart'],
            self.plugins,
        ):
            self.plugins[i].start()
        while self.RUN_FLAG:
            try:
                time.sleep(1.0)
            except KeyboardInterrupt:
                self.stop(lite=False)

    def save_log(self, message, raw_msg, time, level, user_prefix):
        """
            save log message to file
        """
        with open(self.cfg['log_file'], 'ab') as f:
            f.write(''.join([message, '\n']).encode('utf-8'))

# ========================================================================
#                                USER API
# ========================================================================

    def fast_init(self, target, export=True, *args, **kwargs):
        """
            add, init and export plugin
            same as P.add_plugin().init_plugin()
        """
        if 'key' in kwargs:
            key = kwargs.pop('key')
        else:
            key = target.name
        if key not in self.plugin_t:
            self.add_plugin(key=key, target=target, autostart=False)
        return self.init_plugin(key=key, export=export, *args, **kwargs)

    def add_plugin(self, target, **kw):
        """
            Add new plugin/module
            kwargs:
            -- must be --
              target (class/module) - smth that'll be kept here and maybe called (if that's plugin)
            -- optional --
              key (str) - how u wanna call it (default: target.name)
              autostart (bool) - initialize plugin when call Parent.init() (default: True)
              module (bool) - True if target is module ; otherwise target is plugin (default: False)
              dependes (list of str) - list of other plugins/modules that must be initialized before this one
                  ignored if kwagrs[module] == True
                  Default: empty list
              args (tuple) - tuple of arg that will be passed to init() as *args (plugins only)
              kwargs (dict) - dict of arg that will be passed to init() as **kwargs (plugins only)
        """
        from kframe.base.plugin import Plugin
        if issubclass(target, Plugin):
            raise ValueError('target ({}) bust be isinstance of kframe.Plugin'.format(str(target)))
        self.plugin_t[kw.get('key', target.name)] = {
            'target': target,
            'autostart': kw['autostart'] if 'autostart' in kw else True,
            'module': kw['module'] if 'module' in kw else False,
            'args': kw['args'] if 'args' in kw else (),
            'kwargs': kw['kwargs'] if 'kwargs' in kw else {},
            'dependes': kw['dependes'] if 'dependes' in kw else [],
        }
        return self

    def add_module(self, target, key=None):
        """
            Add new module
        """
        if key is None:
            key = target.name
        self.plugin_t[key] = {
            'target': target,
            'module': True,
            'autostart': True,
            'args': (),
            'kwargs': {},
            'dependes': [],
        }
        self.init_plugin(
            key=key,
            export=False,
        )
        return self

    def init(self):
        """
            just for easier use
        """
        self.parse_argv()
        self.log('---------------------------------------------')
        self.init_plugins()
        return self

    def init_plugins(self):
        """
            initialize plugins and modules
            return True in case of success
            or False if not
        """
        if self.FATAL:
            self.print_errmsg()
            return False
        self._init_plugins()
        return not self.FATAL

    def init_plugin(self, key, export=True, *args, **kwargs):
        """
            initialize plugin/module and return it
            returned object doesn't saved in this class
            if args and kwargs not passed => use ones passed in Parent.add_plugin() or Parent.add_module()
            return initialized object
        """
        return self.__init_plugin(
            key=key,
            plugin_name=key,
            args=self.plugin_t[key]['args'] if len(args) <= 0 else args,
            kwargs=self.plugin_t[key]['kwargs'] if len(kwargs) <= 0 else kwargs,
            export=export
        )

    def get_plugin(self, key):
        """
            return already initialized plugin or module
            or return None
        """
        if key in self.plugins:
            return self.plugins[key]
        elif key in self.modules:
            return self.modules[key]
        raise AttributeError('no plugin/module "%s"' % (key))

    def __getitem__(self, key):
        """
            operator overload
            return already initialized plugin or module
            or return None
        """
        return self.get_plugin(key)

    def __contains__(self, key):
        """
            operator overload
            return True if plugin or module exists
            or False if not
        """
        return key in self.plugins or key in self.modules

    def get_class(self, key):
        """
            return Class/Module for the key
            NOT the initialized object!
            or None in case of nothing was found
        """
        return self.plugin_t[key]['target'] if key in self.plugin_t else None

    def get_param(self, key, default=None):
        """
            return param's value if param was passed
            return True as bool if that's was flag
            else return None if nothing was passed
        """
        return self._argv_p[key] if key in self._argv_p else default

    def get_params(self):
        """
            return dict with all parsed sys.argv
        """
        return dict(self._argv_p)

    def expect_argv(self, key, critical=False, description=""):
        """
            add expected key to storage
            flag as bool - True if we expect flag or False if param
            critical as bool - True if this param/flag is critical (default: False)
            description as str - some descrition for human (default: "")
        """
        self._params[key] = {
            'critical': critical,
            'description': description,
        }
        return self

    def log(self, st, _type='info', force=False, plugin_name=None):
        """
            log function
            st - message to save
             _type    |   level
            'debug'   |   Debug
            'info'    |   Info - default
            'warning' |   Warning
            'error'   |   Error
            'critical'|   Critical
        """
        _type = _type if _type in self.levels else 'error'
        prefix = self.levels[_type]
        _time = time.localtime()
        msg = '{_time} -:- {prefix} : {raw_msg}'.format(
            _time=time.strftime(SHOW_TIME_FORMAT, _time),
            prefix=prefix,
            raw_msg=st,
        )
        if _type == 'debug' and not ('--debug' in self._argv_p or force):
            return self
        if '--stdout' in self._argv_p:
            print(msg)
        if self._log_store:
            self._log_storage.append(msg)
        if '--no-log' not in self._argv_p:
            self.save_log(message=msg, raw_msg=st, time=_time, level=_type, user_prefix=prefix)
        return self

    def add_log_level(self, key, user_prefix):
        """
            add new level of logging
        """
        self.levels[key] = user_prefix

    @property
    def log_store(self):
        """
            return log_store flag as bool
        """
        return self._log_store

    def log_store_set(self, value):
        """
            set log_store flag as bool
        """
        if not isinstance(value, bool):
            raise ValueError(
                'log_store must be bool; not "{}"'.format(
                    type(
                        value
                    )
                )
            )
        self._log_store = value

    def log_storage(self):
        """
            return stored list of str and clean buffer
        """
        res = list(self._log_storage)
        self._log_storage.clear()
        return res

    def start(self, wait=True):
        """
            start program
        """
        self.parse_argv()
        if '-h' in sys.argv[1:] or '-?' in sys.argv[1:] or '--help' in sys.argv[1:]:
            self.print_help()
            return self
        self.print_errmsg()
        self.check_critiacal_argv()
        if self.FATAL or any(map(lambda x: x.FATAL, self.plugins.values())):
            for i in self.plugins:
                if self.plugins[i].FATAL:
                    self.log('error in initialize: {}'.format(i), _type='error')
            return self
        else:
            try:
                self.RUN_FLAG = wait
                self.run()
            except Exception as e:
                e = Trace()
                self.log('Parent: start: %s' % (e), _type='error')
        return self

    def stop(self, lite=True):
        """
            stop all plugins
        """
        self.RUN_FLAG = False
        for i in self.plugins:
            self.plugins[i].stop(wait=False)
        if not lite:
            for i in self.plugins:
                self.plugins[i].stop(wait=True)
        return self
