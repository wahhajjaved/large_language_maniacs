# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt


class PerfectInterval():
    """Remove processing time from intervals"""

    def __init__(self, loop):
        self._loop = loop
        self._last_timestamp = 0

    def __call__(self, seconds):
        now = self._loop.time()
        if self._last_timestamp <= 0:
            self._last_timestamp = int(now)
            return seconds
        else:
            expected = self._last_timestamp + seconds
            diff = now - expected
            interval = seconds - diff
            self._last_timestamp += seconds
            return interval


# Borrow Timeout class from aiohttp until asyncio this is solved:
# https://github.com/python/asyncio/issues/392
from aiohttp import Timeout as AsyncIOTimeout
import asyncio
class SleepUneasy():
    """Asynchronous sleep() that can be aborted"""

    def __init__(self, loop):
        self.loop = loop
        self._interrupt = asyncio.Event(loop=self.loop)
        self._perfint = PerfectInterval(self.loop)

    async def sleep(self, seconds):
        """Sleep for `seconds` or until `interrupt` is called"""
        self._interrupt.clear()
        # Remove processing time from seconds
        seconds = self._perfint(seconds)
        try:
            with AsyncIOTimeout(seconds, loop=self.loop):
                await self._interrupt.wait()
        except asyncio.TimeoutError:
            pass  # Interval passed without interrupt
        finally:
            self._interrupt.clear()

    def interrupt(self):
        """Stop sleeping"""
        self._interrupt.set()


from types import SimpleNamespace
class Response(SimpleNamespace):
    """Response to an API call

    All API implementations should use this class to provide return values to
    API calls.

    success: Whether the call was a success
    msgs: Sequence of messages; either strings or ClientError exceptions

    Any other keyword arguments are made available as attributes.
    """
    def __init__(self, success=False, msgs=(), **kwargs):
        super().__init__(success=bool(success), msgs=tuple(msgs), **kwargs)


def lazy_property(after_creation=None):
    """Property that replaces itself with the requested object when accessed

    `after_creation` is called with the instance of the property.
    """
    # https://stackoverflow.com/a/6849299
    class _lazy_property():
        def __init__(self, fget):
            self.fget = fget
            self.func_name = fget.__name__
            self.after_creation = after_creation

        def __get__(self, obj, cls):
            if obj is None:
                return None
            value = self.fget(obj)
            setattr(obj, self.func_name, value)
            if self.after_creation is not None:
                self.after_creation(obj)
            return value

    return _lazy_property


class LazyDict(dict):
    """Dictionary with callables as values that return the actual value on demand"""
    def __getitem__(self, key):
        value = dict.__getitem__(self, key)
        if callable(value):
            value = value()
            dict.__setitem__(self, key, value)
        return value


import re
class URL():
    """Parse URL as lenient as possible (no validation)"""

    ### Pilfered from yurl: https://github.com/homm/yurl
    # This is not validating regexp.
    # It splits url to unambiguous parts according RFC.
    _split_re = re.compile(r'''
        (?:([^:/?#]+):)?            # scheme
        (?://                       # authority
            (?:([^/?\#@]*)@)?       # userinfo
            ([^/?\#]*)              # host:port
        )?
        ([^?\#]*)                   # path
        \??([^\#]*)                 # query
        \#?(.*)                     # fragment
        ''', re.VERBOSE | re.DOTALL).match

    @classmethod
    def _parse_url(cls, url):
        # Default to http scheme so 'host:123' is not interpreted as 'host://123/'
        if '://' not in str(url):
            url = 'http://' + str(url)

        groups = cls._split_re(url).groups('')
        # Order: scheme, user+password, host+port, path, query, fragment
        dct = {}
        dct['scheme']   = groups[0] or None
        dct['path']     = groups[3] or None
        dct['query']    = groups[4] or None
        dct['fragment'] = groups[5] or None

        auth = groups[1]
        user, pw = None, None
        if auth:
            # Password in authentication is optional
            if ':' in auth:
                user, pw = auth.split(':')
            else:
                user, pw = auth, None
        dct['user'] = user or None
        dct['password'] = pw or None

        # Split port from host only if it consists of digits.
        host = groups[2]
        port = None
        port_idx = host.rfind(':')
        if port_idx >= 0:
            port_str = host[port_idx+1:]
            if port_str.isdigit():
                host = host[:port_idx]
                port = int(port_str)
        dct['host'] = host or None
        dct['port'] = port or None

        return dct

    _obj_cache = {}
    def __new__(cls, url):
        if isinstance(url, cls):
            return url

        cache_id = url
        cache = cls._obj_cache
        url_dict = cache.get(cache_id)
        if url_dict is None:
            url_dict = cache[cache_id] = cls._parse_url(url)

        obj = super().__new__(cls)
        for attr in ('scheme', 'host', 'port', 'path', 'user', 'password'):
            setattr(obj, attr, url_dict[attr])
        return obj

    @property
    def has_auth(self):
        """Whether user and password properties are set"""
        return self.user is not None and self.password is not None

    @property
    def domain(self):
        """TLD Domain"""
        if not hasattr(self, '_domain_cached'):
            host = self.host
            if not host:
                self._domain_cached = None
            else:
                if host.count('.') <= 1:
                    self._domain_cached = host
                else:
                    parts = host.rsplit('.', maxsplit=2)
                    self._domain_cached = '.'.join(parts[-2:])
        return self._domain_cached

    def __str__(self):
        if not hasattr(self, '_cached_string'):
            parts = []
            if self.scheme:
                parts.append('%s://' % self.scheme)
            if self.user:
                parts.append('%s' % self.user)
                if self.password:
                    parts.append(':%s' % self.password)
                parts.append('@')
            if self.host:
                parts.append(self.host)
            if self.port:
                parts.append(':%s' % self.port)
            if self.path:
                parts.append('%s' % self.path)
            self._cached_string = ''.join(parts)
        return self._cached_string

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name[0] != '_':
            # Clear caches
            if hasattr(self, '_cached_string'):
                del self._cached_string
            if name == 'host' and hasattr(self, '_domain_cached'):
                del self._domain_cached

    def __repr__(self):
        return '<%s %s>' % (type(self).__name__, str(self))

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return str(self) != str(other)
