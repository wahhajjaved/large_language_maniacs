# Copyright (C) 2012 W. Trevor King
#
# This file is part of update-copyright.
#
# update-copyright is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# update-copyright is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with update-copyright.  If not, see
# <http://www.gnu.org/licenses/>.

from . import VCSBackend as _VCSBackend
from . import utils as _utils


class GitBackend (_VCSBackend):
    name = 'Git'

    def __init__(self, **kwargs):
        super(GitBackend, self).__init__(**kwargs)
        self._version = self._git_cmd('--version').split(' ')[-1]
        if self._version.startswith('1.5.'):
            # Author name <author email>
            self._author_format = '--pretty=format:%an <%ae>'
            self._year_format = ['--pretty=format:%ai']  # Author date
            # YYYY-MM-DD HH:MM:SS Z
            # Earlier versions of Git don't seem to recognize --date=short
        else:
            self._author_format = '--pretty=format:%aN <%aE>'
            self._year_format = ['--pretty=format:%ad',  # Author date
                                 '--date=short']         # YYYY-MM-DD

    def _git_cmd(self, *args):
        status,stdout,stderr = _utils.invoke(
            ['git'] + list(args), cwd=self._root, unicode_output=True)
        return stdout.rstrip('\n')

    def _dates(self, filename=None):
        args = ['log'] + self._year_format
        if filename is not None:
            args.extend(['--follow'] + [filename])
        output = self._git_cmd(*args)
        if self._version.startswith('1.5.'):
            output = '\n'.join([x.split()[0] for x in output.splitlines()])
        return output.splitlines()

    def _years(self, filename=None):
        dates = self._dates(filename=filename)
        years = set(int(date.split('-', 1)[0]) for date in dates)
        return years

    def _authors(self, filename=None):
        args = ['log', self._author_format]
        if filename is not None:
            args.extend(['--follow', filename])
        output = self._git_cmd(*args)
        authors = set(output.splitlines())
        return authors

    def is_versioned(self, filename):
        output = self._git_cmd('log', '--follow', filename)
        if len(output) == 0:
            return False
        return True
