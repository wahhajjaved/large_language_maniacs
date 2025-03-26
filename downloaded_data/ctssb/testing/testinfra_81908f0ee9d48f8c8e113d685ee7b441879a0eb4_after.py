# -*- coding: utf8 -*-
# Copyright © 2015 Philippe Pepiot
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import unicode_literals

import locale
import logging
import pipes

logger = logging.getLogger(__file__)


class CommandResult(object):

    def __init__(
        self, backend, exit_status, stdout_bytes, stderr_bytes, command,
    ):
        self.exit_status = exit_status
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes
        self._stdout = None
        self._stderr = None
        self.command = command
        self._backend = backend
        super(CommandResult, self).__init__()

    @property
    def rc(self):
        return self.exit_status

    @property
    def stdout(self):
        if self._stdout is None:
            self._stdout = self._backend.decode(self.stdout_bytes)
        return self._stdout

    @property
    def stderr(self):
        if self._stderr is None:
            self._stderr = self._backend.decode(self.stderr_bytes)
        return self._stderr

    def __repr__(self):
        return (
            "CommandResult(exit_status=%s, stdout=%s, "
            "stderr=%s, command=%s)"
        ) % (
            self.exit_status,
            repr(self.stdout_bytes),
            repr(self.stderr_bytes),
            repr(self.command),
        )


class BaseBackend(object):
    _backend_type = None

    def __init__(self, *args, **kwargs):
        for arg in args:
            logger.warning("Ignored argument: %s", arg)
        for key, value in kwargs.items():
            logger.warning("Ignored argument: %s = %s", key, value)
        self._encoding = None
        super(BaseBackend, self).__init__()

    def quote(self, command, *args):
        if args:
            return command % tuple(pipes.quote(a) for a in args)
        else:
            return command

    @staticmethod
    def parse_hostspec(hostspec):
        host = hostspec
        user = None
        port = None
        if "@" in host:
            user, host = host.split("@", 1)
        if ":" in host:
            host, port = host.split(":", 1)
        return host, user, port

    def run(self, command, *args):
        raise NotImplementedError

    @classmethod
    def get_backend_type(cls):
        if cls._backend_type is None:
            raise RuntimeError("No backend type")
        return cls._backend_type

    def get_encoding(self):
        cmd = self.run(
            "python -c 'import locale;print(locale.getpreferredencoding())'")
        if cmd.rc == 0:
            encoding = cmd.stdout_bytes.splitlines()[0].decode("ascii")
        else:
            # Python is not installed, we hope the encoding to be the same as
            # local machine...
            encoding = locale.getpreferredencoding()
        return encoding

    @property
    def encoding(self):
        if self._encoding is None:
            self._encoding = self.get_encoding()
        return self._encoding

    def decode(self, data):
        try:
            return data.decode("ascii")
        except UnicodeDecodeError:
            return data.decode(self.encoding)

    def encode(self, data):
        try:
            return data.encode("ascii")
        except UnicodeEncodeError:
            return data.encode(self.encoding)
