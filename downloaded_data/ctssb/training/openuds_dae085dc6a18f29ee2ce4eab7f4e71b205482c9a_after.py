# -*- coding: utf-8 -*-
#
# Copyright (c) 2012-2019 Virtual Cable S.L.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * Neither the name of Virtual Cable S.L. nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
@author: Adolfo Gómez, dkmaster at dkmon dot com
"""
import typing
import logging

from django.conf import settings
from django.apps import apps
import uds.models.Config
from uds.core.managers.CryptoManager import CryptoManager

logger = logging.getLogger(__name__)

GLOBAL_SECTION: str = 'UDS'
SECURITY_SECTION: str = 'Security'
CLUSTER_SECTION: str = 'Cluster'

# For save when initialized
_saveLater = []
_getLater = []

# For custom params (for choices mainly)
_configParams = {}


class Config:
    """
    Keeps persistence configuration data
    """

    # Fields types, so inputs get more "beautiful"
    TEXT_FIELD: int = 0
    LONGTEXT_FIELD: int = 1
    NUMERIC_FIELD: int = 2
    BOOLEAN_FIELD: int = 3
    CHOICE_FIELD: int = 4  # Choice fields must set its parameters on global "configParams" (better by calling ".setParams" method)
    READ_FIELD: int = 5  # Only can viewed, but not changed (can be changed througn API, it's just read only to avoid "mistakes")
    HIDDEN_FIELD: int = 6  # Not visible on "admin" config edition

    class Value:

        def __init__(self, section: 'Config.Section', key: str, default: str = '', crypt: bool = False, longText: bool = False, **kwargs):
            logger.debug('Var: %s %s KWARGS: %s', section, key, kwargs)
            self._type: int = kwargs.get('type', -1)

            self._section: 'Config.Section' = section
            self._key: str = key
            self._crypt: bool = crypt
            self._longText: bool = longText
            if crypt is False or not default:
                self._default: str = default
            else:
                self._default = CryptoManager.manager().encrypt(default)
            self._data: typing.Optional[str] = None


        def get(self, force: bool = False) -> str:
            # Ensures DB contains configuration values
            # From Django 1.7, DB can only be accessed AFTER all apps are initialized, curious at least.. :)
            if apps.ready is True:
                if not GlobalConfig.isInitialized():
                    logger.debug('Initializing configuration & updating db values')
                    GlobalConfig.initialize()
            else:
                _getLater.append(self)
                return self._default

            try:
                if force or self._data is None:
                    # logger.debug('Accessing db config {0}.{1}'.format(self._section.name(), self._key))
                    readed = uds.models.Config.objects.get(section=self._section.name(), key=self._key)  # @UndefinedVariable
                    self._data = readed.value
                    self._crypt = [self._crypt, True][readed.crypt]  # True has "higher" precedende than False
                    self._longText = readed.long
                    if self._type != -1:  # readed.field_type == -1 and
                        readed.field_type = self._type
                        readed.save()
                    self._type = readed.field_type
            except Exception:
                # Not found
                if self._default != '' and self._crypt:
                    self.set(CryptoManager.manager().decrypt(self._default))
                elif not self._crypt:
                    self.set(self._default)
                self._data = self._default

            if self._crypt is True:
                return CryptoManager.manager().decrypt(typing.cast(str, self._data))
            return typing.cast(str, self._data)

        def setParams(self, params: typing.Any) -> None:
            _configParams[self._section.name() + self._key] = params

        def getInt(self, force: bool = False) -> int:
            try:
                return int(self.get(force))
            except Exception:
                logger.error('Value for %s.%s is invalid (integer expected)', self._section, self._key)
                try:
                    return int(self._default)
                except Exception:
                    logger.error('Default value for %s.%s is also invalid (integer expected)', self._section, self._key)
                    return -1

        def getBool(self, force: bool = False) -> bool:
            if self.get(force) == '0':
                return False
            return True

        def key(self) -> str:
            return self._key

        def section(self) -> str:
            return self._section.name()

        def isCrypted(self) -> bool:
            return self._crypt

        def isLongText(self) -> bool:
            return self._longText

        def getType(self) -> int:
            return self._type

        def getParams(self) -> typing.Any:
            return _configParams.get(self._section.name() + self._key, None)

        def set(self, value: str):
            if GlobalConfig.isInitialized() is False:
                _saveLater.append((self, value))
                return

            if self._crypt is True:
                value = CryptoManager.manager().encrypt(value)

            # Editable here means that this configuration value can be edited by admin directly (generally, that this is a "clean text" value)

            logger.debug('Saving config %s.%s as %s', self._section.name(), self._key, value)
            try:
                obj, _ = uds.models.Config.objects.get_or_create(section=self._section.name(), key=self._key)  # @UndefinedVariable
                obj.value, obj.crypt, obj.long, obj.field_type = value, self._crypt, self._longText, self._type
                obj.save()
            except Exception:
                logger.exception('Exception')
                # Probably a migration issue, just ignore it
                logger.info("Could not save configuration key %s.%s", self._section.name(), self._key)

    class Section:
        def __init__(self, sectionName: str):
            self._sectionName: str = sectionName

        def value(self, key, default='', **kwargs) -> 'Config.Value':
            return Config.value(self, key, default, **kwargs)

        def valueCrypt(self, key, default='', **kwargs) -> 'Config.Value':
            return Config.value(self, key, default, True, **kwargs)

        def valueLong(self, key, default='', **kwargs) -> 'Config.Value':
            return Config.value(self, key, default, False, True, **kwargs)

        def name(self) -> str:
            return self._sectionName

    @staticmethod
    def section(sectionName):
        return Config.Section(sectionName)

    @staticmethod
    def value(section: Section, key: str, default: str, crypt: bool = False, longText: bool = False, **kwargs) -> 'Config.Value':
        return Config.Value(section, key, default, crypt, longText, **kwargs)

    @staticmethod
    def enumerate() -> typing.Iterable['Config.Value']:
        GlobalConfig.initialize()  # Ensures DB contains all values
        for cfg in uds.models.Config.objects.all().order_by('key'):  # @UndefinedVariable
            # Skip sections with name starting with "__" (not to be editted on configuration)
            if cfg.section.startswith('__'):  # Hidden section:
                continue
            logger.debug('%s.%s:%s,%s', cfg.section, cfg.key, cfg.value, cfg.field_type)
            if cfg.crypt is True:
                val = Config.section(cfg.section).valueCrypt(cfg.key)
            else:
                val = Config.section(cfg.section).value(cfg.key)
            yield val

    @staticmethod
    def update(section, key, value, checkType=False) -> bool:
        # If cfg value does not exists, simply ignore request
        try:
            cfg = uds.models.Config.objects.filter(section=section, key=key)[0]  # @UndefinedVariable
            if checkType and cfg.field_type in (Config.READ_FIELD, Config.HIDDEN_FIELD):
                return  False# Skip non writable elements

            if cfg.crypt is True:
                value = CryptoManager.manager().encrypt(value)
            cfg.value = value
            cfg.save()
            logger.debug('Updated value for %s.%s to %s', section, key, value)
            return True
        except Exception:
            return False


class GlobalConfig:
    """
    Simple helper to keep track of global configuration
    """
    SESSION_EXPIRE_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('sessionExpireTime', '24', type=Config.NUMERIC_FIELD)  # Max session duration (in use) after a new publishment has been made
    # Delay between cache checks. reducing this number will increase cache generation speed but also will load service providers
    CACHE_CHECK_DELAY: Config.Value = Config.section(GLOBAL_SECTION).value('cacheCheckDelay', '19', type=Config.NUMERIC_FIELD)
    # Delayed task number of threads PER SERVER, with higher number of threads, deplayed task will complete sooner, but it will give more load to overall system
    DELAYED_TASKS_THREADS: Config.Value = Config.section(GLOBAL_SECTION).value('delayedTasksThreads', '4', type=Config.NUMERIC_FIELD)
    # Number of scheduler threads running PER SERVER, with higher number of threads, deplayed task will complete sooner, but it will give more load to overall system
    SCHEDULER_THREADS: Config.Value = Config.section(GLOBAL_SECTION).value('schedulerThreads', '3', type=Config.NUMERIC_FIELD)
    # Waiting time before removing "errored" and "removed" publications, cache, and user assigned machines. Time is in seconds
    CLEANUP_CHECK: Config.Value = Config.section(GLOBAL_SECTION).value('cleanupCheck', '3607', type=Config.NUMERIC_FIELD)
    # Time to maintaing "info state" items before removing it, in seconds
    KEEP_INFO_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('keepInfoTime', '14401', type=Config.NUMERIC_FIELD)  # Defaults to 2 days 172800?? better 4 hours xd
    # Max number of services to be "preparing" at same time
    MAX_PREPARING_SERVICES: Config.Value = Config.section(GLOBAL_SECTION).value('maxPreparingServices', '15', type=Config.NUMERIC_FIELD)  # Defaults to 15 services at once (per service provider)
    # Max number of service to be at "removal" state at same time
    MAX_REMOVING_SERVICES: Config.Value = Config.section(GLOBAL_SECTION).value('maxRemovingServices', '15', type=Config.NUMERIC_FIELD)  # Defaults to 15 services at once (per service provider)
    # If we ignore limits (max....)
    IGNORE_LIMITS: Config.Value = Config.section(GLOBAL_SECTION).value('ignoreLimits', '0', type=Config.BOOLEAN_FIELD)
    # Number of services to initiate removal per run of CacheCleaner
    USER_SERVICE_CLEAN_NUMBER: Config.Value = Config.section(GLOBAL_SECTION).value('userServiceCleanNumber', '3', type=Config.NUMERIC_FIELD)  # Defaults to 3 per wun
    # Removal Check time for cache, publications and deployed services
    REMOVAL_CHECK: Config.Value = Config.section(GLOBAL_SECTION).value('removalCheck', '31', type=Config.NUMERIC_FIELD)  # Defaults to 30 seconds
    # Login URL
    LOGIN_URL: Config.Value = Config.section(GLOBAL_SECTION).value('loginUrl', '/login', type=Config.TEXT_FIELD)  # Defaults to /login
    # Session duration
    USER_SESSION_LENGTH: Config.Value = Config.section(SECURITY_SECTION).value('userSessionLength', '14400', type=Config.NUMERIC_FIELD)  # Defaults to 4 hours
    # Superuser (do not need to be at database!!!)
    SUPER_USER_LOGIN: Config.Value = Config.section(SECURITY_SECTION).value('superUser', 'root', type=Config.TEXT_FIELD)
    # Superuser password (do not need to be at database!!!)
    SUPER_USER_PASS: Config.Value = Config.section(SECURITY_SECTION).valueCrypt('rootPass', 'udsmam0', type=Config.TEXT_FIELD)
    # Idle time before closing session on admin
    SUPER_USER_ALLOW_WEBACCESS: Config.Value = Config.section(SECURITY_SECTION).value('allowRootWebAccess', '1', type=Config.BOOLEAN_FIELD)
    # Time an admi session can be idle before being "logged out"
    ADMIN_IDLE_TIME: Config.Value = Config.section(SECURITY_SECTION).value('adminIdleTime', '14400', type=Config.NUMERIC_FIELD)  # Defaults to 4 hous
    # Time betwen checks of unused services by os managers
    # Unused services will be invoked for every machine assigned but not in use AND that has been assigned at least this time
    # (only if os manager asks for this characteristic)
    CHECK_UNUSED_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('checkUnusedTime', '631', type=Config.NUMERIC_FIELD)  # Defaults to 10 minutes
    # Default CSS Used
    CSS: Config.Value = Config.section(GLOBAL_SECTION).value('css', settings.STATIC_URL + 'css/uds.css', type=Config.TEXT_FIELD)
    # Max logins before blocking an account
    MAX_LOGIN_TRIES: Config.Value = Config.section(GLOBAL_SECTION).value('maxLoginTries', '3', type=Config.NUMERIC_FIELD)
    # Block time in second for an user that makes too many mistakes, 5 minutes default
    LOGIN_BLOCK: Config.Value = Config.section(GLOBAL_SECTION).value('loginBlockTime', '300', type=Config.NUMERIC_FIELD)
    # Do autorun of service if just one service.
    # 0 = No autorun, 1 = Autorun at login
    # In a future, maybe necessary another value "2" that means that autorun always
    AUTORUN_SERVICE: Config.Value = Config.section(GLOBAL_SECTION).value('autorunService', '0', type=Config.BOOLEAN_FIELD)
    # Redirect HTTP to HTTPS
    REDIRECT_TO_HTTPS: Config.Value = Config.section(GLOBAL_SECTION).value('redirectToHttps', '0', type=Config.BOOLEAN_FIELD)
    # Max time needed to get a service "fully functional" before it's considered "failed" and removed
    # The time is in seconds
    MAX_INITIALIZING_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('maxInitTime', '3601', type=Config.NUMERIC_FIELD)
    # Custom HTML for login page
    CUSTOM_HTML_LOGIN: Config.Value = Config.section(GLOBAL_SECTION).value('customHtmlLogin', '', type=Config.LONGTEXT_FIELD)
    # Maximum logs per user service
    MAX_LOGS_PER_ELEMENT: Config.Value = Config.section(GLOBAL_SECTION).value('maxLogPerElement', '100', type=Config.NUMERIC_FIELD)
    # Time to restrain a deployed service in case it gives some errors at some point
    RESTRAINT_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('restrainTime', '600', type=Config.NUMERIC_FIELD)
    # Number of errors that must occurr in RESTRAIN_TIME to restrain deployed service
    RESTRAINT_COUNT: Config.Value = Config.section(GLOBAL_SECTION).value('restrainCount', '3', type=Config.NUMERIC_FIELD)

    # Statistics duration, in days
    STATS_DURATION: Config.Value = Config.section(GLOBAL_SECTION).value('statsDuration', '365', type=Config.NUMERIC_FIELD)
    # If disallow login using /login url, and must go to an authenticator
    DISALLOW_GLOBAL_LOGIN: Config.Value = Config.section(GLOBAL_SECTION).value('disallowGlobalLogin', '0', type=Config.BOOLEAN_FIELD)

    # Allos preferences access to users
    PREFERENCES_ALLOWED: Config.Value = Config.section(GLOBAL_SECTION).value('allowPreferencesAccess', '1', type=Config.BOOLEAN_FIELD)

    # Allowed "trusted sources" for request
    TRUSTED_SOURCES: Config.Value = Config.section(SECURITY_SECTION).value('Trusted Hosts', '*', type=Config.TEXT_FIELD)

    # Allow clients to notify their own ip (if set), or use always the request extracted IP
    HONOR_CLIENT_IP_NOTIFY: Config.Value = Config.section(SECURITY_SECTION).value('honorClientNotifyIP', '0', type=Config.BOOLEAN_FIELD)

    # If there is a proxy in front of us
    BEHIND_PROXY: Config.Value = Config.section(SECURITY_SECTION).value('Behind a proxy', '0', type=Config.BOOLEAN_FIELD)

    # If we use new logout mechanics
    EXCLUSIVE_LOGOUT: Config.Value = Config.section(SECURITY_SECTION).value('Exclusive Logout', '0', type=Config.BOOLEAN_FIELD)

    # Clusters related vars

    # Maximum desired CPU Load. If cpu is over this value, a migration of a service is "desirable"
    CLUSTER_MIGRATE_CPULOAD: Config.Value = Config.section(CLUSTER_SECTION).value('Migration CPU Load', '80', type=Config.NUMERIC_FIELD)
    # Maximum CPU Load for a node to be elegible for destination of a migration
    CLUSTER_ELEGIBLE_CPULOAD: Config.Value = Config.section(CLUSTER_SECTION).value('Destination CPU Load', '60', type=Config.NUMERIC_FIELD)
    # Minimum desired Memory free for a cluster node. If free memory (in %) is under this percentage,
    # a migration of a service inside this node is "desirable"
    CLUSTER_MIGRATE_MEMORYLOAD: Config.Value = Config.section(CLUSTER_SECTION).value('Migration Free Memory', '20', type=Config.NUMERIC_FIELD)
    # Minimum Free memory for a node to be elegible for a destination of a migration
    CLUSTER_ELEGIBLE_MEMORYLOAD: Config.Value = Config.section(CLUSTER_SECTION).value('Migration Free Memory', '40', type=Config.NUMERIC_FIELD)

    RELOAD_TIME: Config.Value = Config.section(GLOBAL_SECTION).value('Page reload Time', '300', type=Config.NUMERIC_FIELD)

    # Custom message for error when limiting by calendar
    LIMITED_BY_CALENDAR_TEXT: Config.Value = Config.section(GLOBAL_SECTION).value('Calendar access denied text', '', type=Config.TEXT_FIELD)  # Defaults to Nothing

    # This is used so templates can change "styles" from admin interface
    LOWERCASE_USERNAME: Config.Value = Config.section(SECURITY_SECTION).value('Convert username to lowercase', '1', type=Config.BOOLEAN_FIELD)

    # Global UDS ID (common for all servers on the same cluster)
    UDS_ID: Config.Value = Config.section(GLOBAL_SECTION).value('UDS ID', CryptoManager.manager().uuid(), type=Config.READ_FIELD)

    _initDone = False

    @staticmethod
    def isInitialized():
        return GlobalConfig._initDone

    @staticmethod
    def initialize() -> None:
        if GlobalConfig._initDone is False:
            try:
                # Tries to initialize database data for global config so it is stored asap and get cached for use
                GlobalConfig._initDone = True
                for v in GlobalConfig.__dict__.values():
                    if isinstance(v, Config.Value):
                        v.get()

                for c in _getLater:
                    logger.debug('Get later: %s', c)
                    c.get()

                _getLater[:] = []

                for c, v in _saveLater:
                    logger.debug('Saving delayed value: %s', c)
                    c.set(v)
                _saveLater[:] = []

                # Process some global config parameters
                # GlobalConfig.UDS_THEME.setParams(['html5', 'semantic'])

            except Exception:
                logger.debug('Config table do not exists!!!, maybe we are installing? :-)')


# Context processor
# noinspection PyUnusedLocal
def context_processor(request):
    return {'css_path': GlobalConfig.CSS.get()}
