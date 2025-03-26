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

"""Backends for version control systems."""

from . import utils as _utils


class VCSBackend (object):
    name = None

    def __init__(self, author_hacks=None, year_hacks=None, aliases=None):
        if author_hacks is None:
            author_hacks = {}
        self._author_hacks = author_hacks
        if year_hacks is None:
            year_hacks = {}
        self._year_hacks = year_hacks
        if aliases is None:
            aliases = {}
        self._aliases = aliases

    def _years(self, filename=None):
        raise NotImplementedError()

    def original_year(self, filename=None):
        years = self._years(filename=filename)
        if filename is None:
            years.update(self._year_hacks.values())
        elif _utils.splitpath(filename) in self._year_hacks:
            years.update(self._year_hacks[_utils.splitpath(filename)])
        years = sorted(years)
        return years[0]

    def _authors(self, filename=None):
        raise NotImplementedError()

    def authors(self, filename=None, with_emails=True):
        authors = self._authors(filename=filename)
        if filename is None:
            for path,authors in self._author_hacks.items():
                authors.update(authors)
        elif _utils.splitpath(filename) in self._author_hacks:
            authors.update(self._author_hacks[_utils.splitpath(filename)])
        return _utils.replace_aliases(
            authors, with_email=with_emails, aliases=self._aliases)

    def is_versioned(self, filename=None):
        raise NotImplementedError()
