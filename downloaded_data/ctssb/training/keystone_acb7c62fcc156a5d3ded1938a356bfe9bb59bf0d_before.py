# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 - 2012 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import hashlib
import json
import os
import subprocess
import time

import passlib.hash

from keystone.common import config
from keystone.common import logging
from keystone import exception


CONF = config.CONF
config.register_int('crypt_strength', default=40000)

LOG = logging.getLogger(__name__)

MAX_PASSWORD_LENGTH = 4096


def read_cached_file(filename, cache_info, reload_func=None):
    """Read from a file if it has been modified.

    :param cache_info: dictionary to hold opaque cache.
    :param reload_func: optional function to be called with data when
                        file is reloaded due to a modification.

    :returns: data from file.

    """
    mtime = os.path.getmtime(filename)
    if not cache_info or mtime != cache_info.get('mtime'):
        with open(filename) as fap:
            cache_info['data'] = fap.read()
        cache_info['mtime'] = mtime
        if reload_func:
            reload_func(cache_info['data'])
    return cache_info['data']


class SmarterEncoder(json.JSONEncoder):
    """Help for JSON encoding dict-like objects."""
    def default(self, obj):
        if not isinstance(obj, dict) and hasattr(obj, 'iteritems'):
            return dict(obj.iteritems())
        return super(SmarterEncoder, self).default(obj)


def trunc_password(password):
    """Truncate passwords to the MAX_PASSWORD_LENGTH."""
    try:
        if len(password) > MAX_PASSWORD_LENGTH:
            return password[:MAX_PASSWORD_LENGTH]
        else:
            return password
    except TypeError:
        raise exception.ValidationError(attribute='string', target='password')


def hash_user_password(user):
    """Hash a user dict's password without modifying the passed-in dict."""
    try:
        password = user['password']
    except KeyError:
        return user
    else:
        return dict(user, password=hash_password(password))


def hash_ldap_user_password(user):
    """Hash a user dict's password without modifying the passed-in dict."""
    try:
        password = user['password']
    except KeyError:
        return user
    else:
        return dict(user, password=ldap_hash_password(password))


def hash_password(password):
    """Hash a password. Hard."""
    password_utf8 = trunc_password(password).encode('utf-8')
    if passlib.hash.sha512_crypt.identify(password_utf8):
        return password_utf8
    h = passlib.hash.sha512_crypt.encrypt(password_utf8,
                                          rounds=CONF.crypt_strength)
    return h


def ldap_hash_password(password):
    """Hash a password. Hard."""
    password_utf8 = trunc_password(password).encode('utf-8')
    h = passlib.hash.ldap_salted_sha1.encrypt(password_utf8)
    return h


def ldap_check_password(password, hashed):
    if password is None:
        return False
    password_utf8 = trunc_password(password).encode('utf-8')
    return passlib.hash.ldap_salted_sha1.verify(password_utf8, hashed)


def check_password(password, hashed):
    """Check that a plaintext password matches hashed.

    hashpw returns the salt value concatenated with the actual hash value.
    It extracts the actual salt if this value is then passed as the salt.

    """
    if password is None:
        return False
    password_utf8 = trunc_password(password).encode('utf-8')
    return passlib.hash.sha512_crypt.verify(password_utf8, hashed)


# From python 2.7
def check_output(*popenargs, **kwargs):
    r"""Run command with arguments and return its output as a byte string.

    If the exit code was non-zero it raises a CalledProcessError.  The
    CalledProcessError object will have the return code in the returncode
    attribute and output in the output attribute.

    The arguments are the same as for the Popen constructor.  Example:

    >>> check_output(['ls', '-l', '/dev/null'])
    'crw-rw-rw- 1 root root 1, 3 Oct 18  2007 /dev/null\n'

    The stdout argument is not allowed as it is used internally.
    To capture standard error in the result, use stderr=STDOUT.

    >>> import sys
    >>> check_output(['/bin/sh', '-c',
    ...               'ls -l non_existent_file ; exit 0'],
    ...              stderr=sys.STDOUT)
    'ls: non_existent_file: No such file or directory\n'
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    LOG.debug(' '.join(popenargs[0]))
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get('args')
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd)
    return output


def git(*args):
    return check_output(['git'] + list(args))


def unixtime(dt_obj):
    """Format datetime object as unix timestamp

    :param dt_obj: datetime.datetime object
    :returns: float

    """
    return time.mktime(dt_obj.utctimetuple())


def auth_str_equal(provided, known):
    """Constant-time string comparison.

    :params provided: the first string
    :params known: the second string

    :return: True if the strings are equal.

    This function takes two strings and compares them.  It is intended to be
    used when doing a comparison for authentication purposes to help guard
    against timing attacks.  When using the function for this purpose, always
    provide the user-provided password as the first argument.  The time this
    function will take is always a factor of the length of this string.
    """
    result = 0
    p_len = len(provided)
    k_len = len(known)
    for i in xrange(p_len):
        a = ord(provided[i]) if i < p_len else 0
        b = ord(known[i]) if i < k_len else 0
        result |= a ^ b
    return (p_len == k_len) & (result == 0)


def hash_signed_token(signed_text):
    hash_ = hashlib.md5()
    hash_.update(signed_text)
    return hash_.hexdigest()


def setup_remote_pydev_debug():
    if CONF.pydev_debug_host and CONF.pydev_debug_port:
        try:
            try:
                from pydevd import pydevd
            except ImportError:
                import pydevd

            pydevd.settrace(CONF.pydev_debug_host,
                            port=CONF.pydev_debug_port,
                            stdoutToServer=True,
                            stderrToServer=True)
            return True
        except Exception:
            LOG.exception(_(
                'Error setting up the debug environment. Verify that the '
                'option --debug-url has the format <host>:<port> and that a '
                'debugger processes is listening on that port.'))
            raise


class LimitingReader(object):
    """Reader to limit the size of an incoming request."""
    def __init__(self, data, limit):
        """Create an iterator on the underlying data.

        :param data: Underlying data object
        :param limit: maximum number of bytes the reader should allow
        """
        self.data = data
        self.limit = limit
        self.bytes_read = 0

    def __iter__(self):
        for chunk in self.data:
            self.bytes_read += len(chunk)
            if self.bytes_read > self.limit:
                raise exception.RequestTooLarge()
            else:
                yield chunk

    def read(self, i=None):
        result = self.data.read(i)
        self.bytes_read += len(result)
        if self.bytes_read > self.limit:
            raise exception.RequestTooLarge()
        return result
