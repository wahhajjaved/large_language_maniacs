# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2015 Toshio Kuratomi <tkuratomi@ansible.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import fcntl
import gettext
import select
import os
from abc import ABCMeta, abstractmethod, abstractproperty

from functools import wraps
from six import with_metaclass

from ansible import constants as C
from ansible.errors import AnsibleError

# FIXME: this object should be created upfront and passed through
#        the entire chain of calls to here, as there are other things
#        which may want to output display/logs too
from ansible.utils.display import Display


__all__ = ['ConnectionBase', 'ensure_connect']


def ensure_connect(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        self._connect()
        return func(self, *args, **kwargs)
    return wrapped


class ConnectionBase(with_metaclass(ABCMeta, object)):
    '''
    A base class for connections to contain common code.
    '''

    has_pipelining = False
    become_methods = C.BECOME_METHODS

    def __init__(self, connection_info, new_stdin, *args, **kwargs):
        # All these hasattrs allow subclasses to override these parameters
        if not hasattr(self, '_connection_info'):
            self._connection_info = connection_info
        if not hasattr(self, '_new_stdin'):
            self._new_stdin = new_stdin
        if not hasattr(self, '_display'):
            self._display = Display(verbosity=connection_info.verbosity)
        if not hasattr(self, '_connected'):
            self._connected = False

        self.success_key = None
        self.prompt = None

    def _become_method_supported(self):
        ''' Checks if the current class supports this privilege escalation method '''

        if self._connection_info.become_method in self.__class__.become_methods:
            return True

        raise AnsibleError("Internal Error: this connection module does not support running commands via %s" % become_method)

    def set_host_overrides(self, host):
        '''
        An optional method, which can be used to set connection plugin parameters
        from variables set on the host (or groups to which the host belongs)

        Any connection plugin using this should first initialize its attributes in
        an overridden `def __init__(self):`, and then use `host.get_vars()` to find
        variables which may be used to set those attributes in this method.
        '''
        pass

    @abstractproperty
    def transport(self):
        """String used to identify this Connection class from other classes"""
        pass

    @abstractmethod
    def _connect(self):
        """Connect to the host we've been initialized with"""

        # Check if PE is supported
        if self._connection_info.become:
            self.__become_method_supported()

    @ensure_connect
    @abstractmethod
    def exec_command(self, cmd, tmp_path, in_data=None, sudoable=True):
        """Run a command on the remote host"""
        pass

    @ensure_connect
    @abstractmethod
    def put_file(self, in_path, out_path):
        """Transfer a file from local to remote"""
        pass

    @ensure_connect
    @abstractmethod
    def fetch_file(self, in_path, out_path):
        """Fetch a file from remote to local"""
        pass

    @abstractmethod
    def close(self):
        """Terminate the connection"""
        pass

    def check_become_success(self, output):
        return self.success_key in output

    def check_password_prompt(self, output):
        if self.prompt in None:
            return True
        elif isinstance(self.prompt, basestring):
            return output.endswith(self.prompt)
        else:
            return self.prompt(output)

    def check_incorrect_password(self, output):
        incorrect_password = gettext.dgettext(self._connection_info.become_method, C.BECOME_ERROR_STRINGS[self._connection_info.become_method])
        if incorrect_password in output:
            raise AnsibleError('Incorrect %s password' % self._connection_info.become_method)

