# -*- coding: utf-8 -*-

"""
psub.core
~~~~~~~~~~~~~~~~~~~~~

This module implements the psub basic methods.

"""


import re

from .logger import logger
from .providers import napisy24


class Core(object):
    def __init__(self, debug=False):
        logger(save=debug)  # init root logger
        self.logger = logger(__name__)
        # self.provider = napisy24.Provider()

    def _parseFilename(self, filename):
        """Parse filename. Returns {title, year, group}."""
        print('Filename: ' + filename)  # DEBUG
        filename = filename.lower()
        data = {}
        rc = re.match('(.+?)\.+s([0-9]{2})e([0-9]{2})\..+\-(.+?)\..{2,4}', filename)
        if rc:  # tvshow
            data['category'] = 'tvshow'
            data['season'] = rc.group(2)
            data['episode'] = rc.group(3)
            data['group'] = rc.group(4)
        else:  # movie
            rc = re.match('(.+?)\.([0-9]{4})\..+\-(.+?)\..{2,4}', filename)
            data['category'] = 'movie'
            data['year'] = rc.group(2)
            data['group'] = rc.group(3)
        data['title'] = rc.group(1)
        print('Parsed: ')  # DEBUG
        print(data)  # DEBUG
        return data

    def download(self, filename, provider='napisy24', username=None, passwd=None):
        """Downloads subtitles."""
        # TODO: use provider, username, password
        # TODO: destination
        # TODO: language
        # TODO: format
        # TODO: encoding
        # TODO: encoding conversion
        # TODO: imdb_id
        self.provider = napisy24.Provider(username=username, passwd=passwd)
        data = self._parseFilename(filename)
        fc = self.provider.download(category=data['category'], title=data['title'], year=data.get('year'), season=data.get('season'), episode=data.get('episode'), group=data['group'])
        open(filename.replace('.mkv', '.srt'), 'wb').write(fc)
