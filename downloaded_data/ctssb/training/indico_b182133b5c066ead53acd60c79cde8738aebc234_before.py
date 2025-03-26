# -*- coding: utf-8 -*-
##
##
## This file is part of CDS Indico.
## Copyright (C) 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010 CERN.
##
## CDS Indico is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## CDS Indico is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with CDS Indico; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Main export interface
"""

# python stdlib imports
import fnmatch
import itertools
import pytz
import re
from zope.interface import Interface, implements
from datetime import datetime, timedelta, date, time

# external lib imports
from simplejson import dumps

# indico imports
from indico.util.date_time import nowutc
from indico.util.fossilize import fossilize

from indico.util.metadata import Serializer
from indico.web.http_api.html import HTML4Serializer
from indico.web.http_api.jsonp import JSONPSerializer
from indico.web.http_api.ical import ICalSerializer
from indico.web.http_api.atom import AtomSerializer
from indico.web.http_api.fossils import IConferenceMetadataFossil,\
    IConferenceMetadataWithContribsFossil, IConferenceMetadataWithSubContribsFossil,\
    IConferenceMetadataWithSessionsFossil
from indico.web.http_api.responses import HTTPAPIError
from indico.web.wsgi import webinterface_handler_config as apache

# indico legacy imports
from MaKaC.common.indexes import IndexesHolder
from MaKaC.common.info import HelperMaKaCInfo
from MaKaC.conference import ConferenceHolder
from MaKaC.plugins.base import PluginsHolder

from indico.web.http_api.util import get_query_parameter, remove_lists


class ArgumentParseError(Exception):
    pass


class ArgumentValueError(Exception):
    pass


class LimitExceededException(Exception):
    pass


class Exporter(object):
    EXPORTER_LIST = []
    TYPES = None # abstract
    RE = None # abstract
    DEFAULT_DETAIL = None # abstract
    MAX_RECORDS = None # abstract

    @classmethod
    def parseRequest(cls, path, qdata):
        """Parse a request path and return an exporter and the requested data type."""
        exporters = itertools.chain(cls.EXPORTER_LIST, cls._getPluginExporters())
        for expCls in exporters:
            m = expCls._matchPath(path)
            if m:
                gd = m.groupdict()
                g = m.groups()
                type = g[0]
                format = g[-1]
                if format not in ExportInterface.getAllowedFormats():
                    return None, None
                return expCls(qdata, type, gd), format
        return None, None

    @staticmethod
    def register(cls):
        """Register an exporter that is not part of a plugin.

        To use it, simply decorate the exporter class with this method."""
        assert cls.RE is not None
        Exporter.EXPORTER_LIST.append(cls)
        return cls

    @classmethod
    def _matchPath(cls, path):
        if not hasattr(cls, '_RE'):
            types = '|'.join(cls.TYPES)
            cls._RE = re.compile(r'/export/(' + types + r')/' + cls.RE + r'\.(\w+)$')
        return cls._RE.match(path)

    @classmethod
    def _getPluginExporters(cls):
        for plugin in PluginsHolder().getPluginTypes():
            for expClsName in plugin.getExporterList():
                yield getattr(plugin.getModule().export, expClsName)

    def __init__(self, qdata, type, urlParams):
        self._qdata = qdata
        self._type = type
        self._urlParams = urlParams

    def _getParams(self):
        self._offset = get_query_parameter(self._qdata, ['O', 'offset'], 0, integer=True)
        self._orderBy = get_query_parameter(self._qdata, ['o', 'order'], 'start')
        self._descending = get_query_parameter(self._qdata, ['c', 'descending'], False)
        self._detail = get_query_parameter(self._qdata, ['d', 'detail'], self.DEFAULT_DETAIL)
        tzName = get_query_parameter(self._qdata, ['tz'], None)
        if tzName is None:
            info = HelperMaKaCInfo.getMaKaCInfoInstance()
            tzName = info.getTimezone()
        self._tz = pytz.timezone(tzName)
        max = self.MAX_RECORDS.get(self._detail, 10000)
        self._userLimit = get_query_parameter(self._qdata, ['n', 'limit'], 0, integer=True)
        if self._userLimit > max:
            raise HTTPAPIError("You can only request up to %d records per request with the detail level '%s'" %
                (max, self._detail), apache.HTTP_BAD_REQUEST)
        self._limit = self._userLimit if self._userLimit > 0 else max

    def __call__(self, aw):
        """Perform the actual exporting"""
        self._getParams()
        resultList = []
        complete = True

        func = getattr(self, 'export_' + self._type, None)
        if not func:
            raise NotImplementedError('export_' + self._type)

        try:
            for obj in func(aw):
                resultList.append(obj)
        except LimitExceededException:
            complete = (self._limit == self._userLimit)

        return resultList, complete


class ExportInterface(object):
    _deltas =  {'yesterday': timedelta(-1),
                'tomorrow': timedelta(1)}

    _sortingKeys = {'id': lambda x: x.getId(),
                    'end': lambda x: x.getEndDate(),
                    'title': lambda x: x.getTitle()}

    def __init__(self, aw):
        self._aw = aw

    @classmethod
    def getAllowedFormats(cls):
        return Serializer.getAllFormats()

    @classmethod
    def _parseDateTime(cls, dateTime):
        """
        Accepted formats:
         * ISO 8601 subset - YYYY-MM-DD[THH:MM]
         * 'today', 'yesterday', 'tomorrow' and 'now'
         * days in the future/past: '[+/-]DdHHhMMm'

         'ctx' means that the date will change according to its function
         ('from' or 'to')
        """

        # if it's a an "alias", return immediately
        now = nowutc()
        if dateTime in cls._deltas:
            return ('ctx', now + cls._deltas[dateTime])
        elif dateTime == 'now':
            return ('abs', now)
        elif dateTime == 'today':
            return ('ctx', now)

        m = re.match(r'^(?:(\d{1,3})d)?(?:(\d{1,2})h)?(?:(\d{1,2})m)?$', dateTime)
        if m:
            atoms = list(0 if a == None else int(a) for a in m.groups())

            if atoms[1] > 23  or atoms[2] > 59:
                raise ArgumentParseError("Invalid time!")
            return ('ctx', timedelta(days=atoms[0], hours=atoms[1], minutes=atoms[2]))
        else:
            # iso 8601 subset
            try:
                return ('abs', datetime.strptime(dateTime, "%Y-%m-%dT%H:%M"))
            except ValueError:
                pass
            try:
                return ('ctx', datetime.strptime(dateTime, "%Y-%m-%d"))
            except ValueError:
                raise ArgumentParseError("Impossible to parse '%s'" % dateTime)

    @classmethod
    def _getDateTime(cls, ctx, dateTime, tz, aux=None):

        rel, value = cls._parseDateTime(dateTime)

        if rel == 'abs':
            return tz.localize(value)
        elif rel == 'ctx' and type(value) == timedelta:
            if ctx == 'from':
                raise ArgumentValueError("Only 'to' accepts relative times")
            else:
                value = aux + value

        # from here on, 'value' has to be a datetime
        if ctx == 'from':
            return tz.localize(value.combine(value.date(), time(0, 0, 0)))
        else:
            return tz.localize(value.combine(value.date(), time(23, 59, 59)))

    def _limitIterator(self, iterator, limit):
        counter = 0
        # this set acts as a checklist to know if a record has already been sent
        exclude = set()
        self._intermediateResults = []

        for obj in iterator:
            if counter >= limit:
                raise LimitExceededException()
            if obj not in exclude and (not hasattr(obj, 'canAccess') or obj.canAccess(self._aw)):
                self._intermediateResults.append(obj)
                yield obj
                exclude.add(obj)
                counter += 1

    def _sortedIterator(self, iterator, limit, orderBy, descending):

        exceeded = False
        if (orderBy and orderBy != 'start') or descending:
            sortingKey = self._sortingKeys.get(orderBy)
            try:
                limitedIterable = sorted(self._limitIterator(iterator, limit),
                                         key=sortingKey)
            except LimitExceededException:
                exceeded = True
                limitedIterable = sorted(self._intermediateResults,
                                         key=sortingKey)

            if descending:
                limitedIterable.reverse()
        else:
            limitedIterable = self._limitIterator(iterator, limit)

        # iterate over result
        for obj in limitedIterable:
            yield obj

        # in case the limit was exceeded while sorting the results,
        # raise the exception as if we were truly consuming an iterator
        if orderBy and exceeded:
            raise LimitExceededException()

    @classmethod
    def _getDetailInterface(cls, detail):
        raise HTTPAPIError('Invalid detail level: %s' % detail, apache.HTTP_BAD_REQUEST)

    def _iterateOver(self, iterator, offset, limit, orderBy, descending, filter=None):
        """
        Iterates over a maximum of `limit` elements, starting at the
        element number `offset`. The elements will be ordered according
        to `orderby` and `descending` (slooooow) and filtered by the
        callable `filter`:
        """

        if filter:
            iterator = itertools.ifilter(filter, iterator)
        sortedIterator = self._sortedIterator(iterator, limit, orderBy, descending)
        # Skip offset elements - http://docs.python.org/library/itertools.html#recipes
        next(itertools.islice(sortedIterator, offset, offset), None)
        return sortedIterator


@Exporter.register
class CategoryEventExporter(Exporter):
    TYPES = ('event', 'categ')
    RE = r'(?P<idlist>\w+(?:-\w+)*)'
    DEFAULT_DETAIL = 'events'
    MAX_RECORDS = {
        'events': 10000,
        'contributions': 500,
        'subcontributions': 500,
        'sessions': 100,
    }

    def _getParams(self):
        super(CategoryEventExporter, self)._getParams()
        self._idList = self._urlParams['idlist'].split('-')

    def export_categ(self, aw):
        expInt = CategoryEventExportInterface(aw)
        return expInt.category(self._idList, self._tz, self._offset, self._limit, self._detail, self._orderBy, self._descending, self._qdata)

    def export_event(self, aw):
        expInt = CategoryEventExportInterface(aw)
        return expInt.event(self._idList, self._tz, self._offset, self._limit, self._detail, self._orderBy, self._descending, self._qdata)


class CategoryEventExportInterface(ExportInterface):
    @classmethod
    def _getDetailInterface(cls, detail):
        if detail == 'events':
            return IConferenceMetadataFossil
        elif detail == 'contributions':
            return IConferenceMetadataWithContribsFossil
        elif detail == 'subcontributions':
            return IConferenceMetadataWithSubContribsFossil
        elif detail == 'sessions':
            return IConferenceMetadataWithSessionsFossil
        raise HTTPAPIError('Invalid detail level: %s' % detail, apache.HTTP_BAD_REQUEST)

    def category(self, idlist, tz, offset, limit, detail, orderBy, descending, qdata):
        fromDT = get_query_parameter(qdata, ['f', 'from'])
        toDT = get_query_parameter(qdata, ['t', 'to'])
        location = get_query_parameter(qdata, ['l', 'location'])
        room = get_query_parameter(qdata, ['r', 'room'])

        fromDT = ExportInterface._getDateTime('from', fromDT, tz) if fromDT != None else None
        toDT = ExportInterface._getDateTime('to', toDT, tz, aux=fromDT) if toDT != None else None

        idx = IndexesHolder().getById('categoryDate')

        filter = None
        if room or location:
            def filter(obj):
                if location:
                    name = obj.getLocation() and obj.getLocation().getName()
                    if not name or not fnmatch.fnmatch(name.lower(), location.lower()):
                        return False
                if room:
                    name = obj.getRoom() and obj.getRoom().getName()
                    if not name or not fnmatch.fnmatch(name.lower(), room.lower()):
                        return False
                return True

        for catId in idlist:
            for obj in self._iterateOver(idx.iterateObjectsIn(catId, fromDT, toDT),
                                         offset, limit, orderBy, descending, filter):
                yield fossilize(obj, IConferenceMetadataFossil, tz=tz)

    def event(self, idlist, tz, offset, limit, detail, orderBy, descending, qdata):
        ch = ConferenceHolder()

        def _iterate_objs(objIds):

            for objId in objIds:
                obj = ch.getById(objId)
                yield obj

        iface = ExportInterface._getDetailInterface(detail)

        for event in self._iterateOver(_iterate_objs(idlist), offset, limit, orderBy, descending):
            yield fossilize(event, iface, tz=tz)

Serializer.register('html', HTML4Serializer)
Serializer.register('jsonp', JSONPSerializer)
Serializer.register('ics', ICalSerializer)
Serializer.register('atom', AtomSerializer)
