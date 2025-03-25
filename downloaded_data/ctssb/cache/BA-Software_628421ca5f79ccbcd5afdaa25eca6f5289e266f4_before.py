# -*- coding: utf-8 -*-
"""
System Related Intricacies
"""

### INCLUDES ###
import os
import time
import copy
import pkgutil
import logging

import bottle

from py_knife import platforms, file_system
from py_knife.ordered_dict import OrderedDict

from gate import __version__
from gate import configure
from gate.database import DatabaseDict
from gate.common import OPTIONS_PARSER, IMG_FOLDER, SYSTEM_FOLDER, MWD
from gate.conversions import get_net_addresses, get_ip_scheme


### CONSTANTS ###
GATE_VERSION = 'GATE_' + __version__

## System Defaults ##
SYSTEM_DEFAULTS = {
    'ip_scheme': 'dynamic',
    'ip_address': '192.168.0.111',
    'subnet_mask': '255.255.255.0',
    'modbus_byte_order': True,          # False == little_endian, True == big_endian
    'modbus_register_order': False,
    'time_offset': 0.0,
    'timezone': time.timezone,
    'log_limit': 100,
    'time_diff': None,                  # Used strictly to perform base timing changes
    'warnings_pop_up_enable': True,
    'warnings_sound_enable': False,
    'user_bypass': False
}

## Default System Data Generator ##
DEFAULT_SYSTEM_DATA = dict()
for importer, module_name, is_package in pkgutil.iter_modules([SYSTEM_FOLDER]):
    if not is_package:
        system_name = module_name.split('.')[-1]
        if not system_name.startswith('_'):
            handler_module = importer.find_module(module_name).load_module(module_name)
            DEFAULT_SYSTEM_DATA[system_name] = handler_module.SYSTEM_DATA

## Timezones List ##
TIMEZONE_DICT = OrderedDict()
TIMEZONE_DICT['UTC-12:00'] = 12*60*60
TIMEZONE_DICT['UTC-11:00'] = 11*60*60
TIMEZONE_DICT['UTC-10:00'] = 10*60*60
TIMEZONE_DICT['UTC-09:30'] = 9.5*60*60
TIMEZONE_DICT['UTC-09:00'] = 9*60*60
TIMEZONE_DICT['UTC-08:00'] = 8*60*60
TIMEZONE_DICT['UTC-07:00'] = 7*60*60
TIMEZONE_DICT['UTC-06:00'] = 6*60*60
TIMEZONE_DICT['UTC-05:00'] = 5*60*60
TIMEZONE_DICT['UTC-04:00'] = 4*60*60
TIMEZONE_DICT['UTC-03:30'] = 3.5*60*60
TIMEZONE_DICT['UTC-03:00'] = 3*60*60
TIMEZONE_DICT['UTC-02:00'] = 2*60*60
TIMEZONE_DICT['UTC-01:00'] = 1*60*60
TIMEZONE_DICT['UTC±00:00'] = 0*60*60
TIMEZONE_DICT['UTC+01:00'] = -1*60*60
TIMEZONE_DICT['UTC+02:00'] = -2*60*60
TIMEZONE_DICT['UTC+03:00'] = -3*60*60
TIMEZONE_DICT['UTC+03:30'] = -3.5*60*60
TIMEZONE_DICT['UTC+04:00'] = -4*60*60
TIMEZONE_DICT['UTC+04:30'] = -4.5*60*60
TIMEZONE_DICT['UTC+05:00'] = -5*60*60
TIMEZONE_DICT['UTC+05:30'] = -5.5*60*60
TIMEZONE_DICT['UTC+05:45'] = -5.75*60*60
TIMEZONE_DICT['UTC+06:00'] = -6*60*60
TIMEZONE_DICT['UTC+06:30'] = -6.5*60*60
TIMEZONE_DICT['UTC+07:00'] = -7*60*60
TIMEZONE_DICT['UTC+08:00'] = -8*60*60
TIMEZONE_DICT['UTC+08:30'] = -8.5*60*60
TIMEZONE_DICT['UTC+08:45'] = -8.75*60*60
TIMEZONE_DICT['UTC+09:00'] = -9*60*60
TIMEZONE_DICT['UTC+09:30'] = -9.5*60*60
TIMEZONE_DICT['UTC+10:00'] = -10*60*60
TIMEZONE_DICT['UTC+10:30'] = -10.5*60*60
TIMEZONE_DICT['UTC+11:00'] = -11*60*60
TIMEZONE_DICT['UTC+12:00'] = -12*60*60
TIMEZONE_DICT['UTC+12:45'] = -12.75*60*60
TIMEZONE_DICT['UTC+13:00'] = -13*60*60
TIMEZONE_DICT['UTC+14:00'] = -14*60*60

## Strings ##
UTC_TIME1 = "System UTC   Time: "
UTC_TIME2 = " ("
UTC_TIME3 = ")"
LOCAL_TIME = "System Local Time: "
TIMEZONE = "System Time  Zone: "


## Bottle Templates ##
_TEMPLATE_PATH = os.path.dirname(os.path.realpath(__file__))
bottle.TEMPLATE_PATH.append(_TEMPLATE_PATH)

## Logger ##
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.WARNING)


### CLASSES ###
class SystemSettings(DatabaseDict):
    """ System related class """
    def __init__(self, system_options=None):
        if system_options is None:
            # Get system options from options parser
            (system_options, args) = OPTIONS_PARSER.parse_args()

        self.name = system_options.system_name
        self.language = system_options.language
        self.modbus_enable = system_options.modbus_enable
        self.snmp_enable = system_options.snmp_enable
        self.virgins_enable = system_options.virgins_enable
        self.faq_enable = system_options.faq_enable
        self.manual_log = system_options.manual_log

        if platforms.PLATFORM == platforms.WINDOWS:
            # FIXME: Modbus Server does not work on Windows
            LOGGER.warning('Modbus Server currently is not supported on Windows OS!')
            self.modbus_enable = False

        self._title = None          # Just to fix warning

        if self.name in DEFAULT_SYSTEM_DATA:
            system_data = DEFAULT_SYSTEM_DATA[self.name]
        else:
            system_data = DEFAULT_SYSTEM_DATA['default']

        for sys_key, sys_value in system_data.items():
            setattr(self, sys_key, sys_value)

        default_system = copy.deepcopy(SYSTEM_DEFAULTS)

        super(SystemSettings, self).__init__(
            db_file='system.db',
            defaults=default_system
        )

        self.version = GATE_VERSION

        if system_options is not None:
            # Set system favicon
            favicon_source_path = os.path.join(IMG_FOLDER, self.name, 'favicon.ico')
            favicon_dest_path = os.path.join(MWD, 'favicon.ico')
            file_system.remove_file(favicon_dest_path)
            file_system.copy_file(favicon_source_path, favicon_dest_path, dos2unix=False)

        # Print System Report #
        if system_options is not None:
            # TODO: Make sure all the options are functional...
            print('Version: {}'.format(self.version))
            print('System: {}'.format(self.name))
            print('Language: {}'.format(self.language))
            print('Modbus Enable: {}'.format(self.modbus_enable))
            print('SNMP Enable: {}'.format(self.snmp_enable))
            print('Virgins Enable: {}'.foramt(self.virgins_enable))
            print('FAQ Enable: {}'.format(self.faq_enable))
            print('Manual Log Enable: {}'.format(self.manual_log))
            print(self.time_settings_str())

    ## Title ##
    def title(self):
        """
        Fetches appropriate title
        :return: title
        """
        if 'title' in iter(self):
            return self['title']
        else:
            return self._title

    ## Time Related ##
    def time(self):
        """ Returns current system time """
        return time.time() - self['time_offset']

    def lcl_time(self, epoch_time=None):
        """ Returns local time in seconds """
        if not epoch_time:
            epoch_time = self.time()
        return epoch_time - self['timezone']

    def utc_time(self, epoch_time=None):
        """ Epoch time to UTC time string (Valid MySQL) """
        if not epoch_time:
            epoch_time = self.time()
        # Change format to "<p>hh:mm:ss</p><p>mm/dd/yyyy</p>"?
        return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(epoch_time))
        # Reverse: return time.mktime(time.strptime(str, '%Y-%m-%d %H:%M:%S'))

    def local_time(self, epoch_time=None):
        """ Epoch time to Local time string (Valid MySQL) """
        local_time_sec = self.lcl_time(epoch_time)
        return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(local_time_sec))
        # Reverse: return time.mktime(time.strptime(str, '%Y-%m-%d %H:%M:%S'))

    def create_time_stamp(self, epoch_time=None):
        local_time_sec = self.lcl_time(epoch_time)
        return time.strftime('%Y%m%d_%H%M%S', time.gmtime(local_time_sec))

    def log_time(self, epoch_time=None):
        """ 
        Converts Epoch time to Local time for the Log output
        .. note:: Javascript epoch == Unix epoch but in milliseconds
        """
        if not epoch_time:
            epoch_time = self.time()
        return int(epoch_time - self['timezone']) * 1000

    def set_linux_time(self, epoch_time=None):
        """ Converts Epoch time to UTC time string for the E10 time change """
        if not epoch_time:
            epoch_time = self.time()
        linux_time = time.strftime('%Y.%m.%d-%H:%M:%S', time.localtime(epoch_time))
        set_time_str = "date +%Y.%m.%d-%H:%M:%S -s '" + linux_time + "'"
        return set_time_str

    def log_file_time(self, epoch_time=None):
        """ Converts Epoch time to UTC time string for log filename """
        local_time_sec = self.lcl_time(epoch_time)
        return time.strftime('%Y%m%d-%H%M%S', time.gmtime(local_time_sec))

    def time_settings_str(self):
        """ Returns current time settings as a string """
        output = ""
        output += UTC_TIME1 + self.utc_time() + UTC_TIME2
        output += str(self.time()) + UTC_TIME3 + '\n'
        output += LOCAL_TIME + self.local_time() + '\n'
        # Display in hours
        output += TIMEZONE + str(TIMEZONE_DICT.keys()[TIMEZONE_DICT.values().index(self['timezone'])]) + '\n'

        return output

    ## IP Addressing Related ##
    def change_network_settings(self, ip_scheme, ip_address=SYSTEM_DEFAULTS['ip_address'],
                                subnet_mask=SYSTEM_DEFAULTS['subnet_mask']):
        """
        Updates IP Addressing variables

        :return: False/True depending if ip addressing been changed or not
        """
        output = False
        if platforms.PLATFORM in platforms.EMBEDDED_PLATFORMS:
            _ip_address, _subnet_mask = get_net_addresses()
            _ip_scheme = get_ip_scheme()

            ip_scheme_changed = bool(ip_scheme != _ip_scheme)
            ip_address_changed = bool(ip_address != _ip_address or subnet_mask != _subnet_mask)

            if ip_scheme_changed or (ip_scheme == 'static' and ip_address_changed):
                output = True
                self['ip_scheme'] = ip_scheme
                self['ip_address'] = ip_address
                self['subnet_mask'] = subnet_mask

                # FIXME: Make sure to include proper update_network script!!!
                if platforms.PLATFORM == platforms.RASPBERRY_PI:
                    configure.configure_pi.update_network(self)

                else:
                    configure.configure_e10.update_network(self, template_path='network_daemon')

                self.save()

        return output

    def attr_dict(self):
        """ Returns pickable dictionary of attributes """
        attr_names = [a for a in dir(self) if not a.startswith('_') and not callable(getattr(self, a))]

        attr_dict = dict()
        for attr_name in attr_names:
            attr_dict[attr_name] = getattr(self, attr_name)

        return attr_dict
