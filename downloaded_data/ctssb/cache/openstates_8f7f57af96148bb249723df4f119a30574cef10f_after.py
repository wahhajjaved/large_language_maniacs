from __future__ import with_statement
import os
import time
import logging
import urllib2
import datetime
import contextlib
from optparse import make_option, OptionParser

from fiftystates.scrape.validator import DatetimeValidator

try:
    import json
except ImportError:
    import simplejson as json

from fiftystates import settings

import scrapelib


class ScrapeError(Exception):
    """
    Base class for scrape errors.
    """
    pass


class NoDataForPeriod(ScrapeError):
    """
    Exception to be raised when no data exists for a given period
    """
    def __init__(self, period):
        self.period = period

    def __str__(self):
        return 'No data exists for %s' % self.period


class JSONDateEncoder(json.JSONEncoder):
    """
    JSONEncoder that encodes datetime objects as Unix timestamps.
    """
    def default(self, obj):
        if (isinstance(obj, datetime.datetime) or
            isinstance(obj, datetime.date)):

            return time.mktime(obj.timetuple())

        return json.JSONEncoder.default(self, obj)


class Scraper(scrapelib.Scraper):

    def __init__(self, metadata, no_cache=False, output_dir=None,
                 strict_validation=None, **kwargs):
        """
        Create a new Scraper instance.

        :param metadata: metadata for this state
        :param no_cache: if True, will ignore any cached downloads
        :param output_dir: the Fifty State data directory to use
        :param strict_validation: exit immediately if validation fails
        """

        # configure underlying scrapelib object
        if no_cache:
            kwargs['cache_dir'] = None
        elif 'cache_dir' not in kwargs:
            kwargs['cache_dir'] = getattr(settings, 'FIFTYSTATES_CACHE_DIR',
                                          None)

        if 'error_dir' not in kwargs:
            kwargs['error_dir'] = getattr(settings, 'FIFTYSTATES_ERROR_DIR',
                                          None)

        if 'timeout' not in kwargs:
            kwargs['timeout'] = getattr(settings, 'SCRAPELIB_TIMEOUT',
                                        600)

        if 'requests_per_minute' not in kwargs:
            kwargs['requests_per_minute'] = None

        super(Scraper, self).__init__(**kwargs)

        if not hasattr(self, 'state'):
            raise Exception('Scrapers must have a state attribute')

        self.metadata = metadata
        self.output_dir = output_dir

        # validation
        self.strict_validation = strict_validation
        self.validator = DatetimeValidator()

        self.follow_robots = False

        # logging convenience methods
        self.logger = logging.getLogger("fiftystates")
        self.log = self.logger.info
        self.debug = self.logger.debug
        self.warning = self.logger.warning

    def validate_json(self, obj):
        if not hasattr(self, '_schema'):
            self._schema = self._get_schema()
        try:
            self.validator.validate(obj, self._schema)
        except ValueError, ve:
            self.warning(str(ve))
            if self.strict_validation:
                raise ve

    def all_sessions(self):
        sessions = []
        for t in self.metadata['terms']:
            sessions.extend(t['sessions'])
        return sessions

    def validate_session(self, session):
        for t in self.metadata['terms']:
            if session in t['sessions']:
                return True
        raise NoDataForPeriod(session)

    def validate_term(self, term):
        for t in self.metadata['terms']:
            if term == t['name']:
                return True
        raise NoDataForPeriod(session)


class FiftystatesObject(dict):
    def __init__(self, _type, **kwargs):
        super(FiftystatesObject, self).__init__()
        self['_type'] = _type
        self['sources'] = []
        self.update(kwargs)

    def add_source(self, url, retrieved=None, **kwargs):
        """
        Add a source URL from which data related to this object was scraped.

        :param url: the location of the source
        """
        retrieved = retrieved or datetime.datetime.now()
        self['sources'].append(dict(url=url, retrieved=retrieved, **kwargs))
