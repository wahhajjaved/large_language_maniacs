"""
High-level python bindings for Zarafa

Copyright 2014 Zarafa and contributors, license AGPLv3 (see LICENSE file for details)

Some goals:

- To be fully object-oriented, pythonic, layer above MAPI
- To be usable for many common system administration tasks
- To provide full access to the underlying MAPI layer if needed
- To return all text as unicode strings
- To return/accept binary identifiers in readable (hex-encoded) form
- To raise well-described exceptions if something goes wrong

Main classes:

:class:`Server`

:class:`Store`

:class:`User`

:class:`Company`

:class:`Store`

:class:`Folder`

:class:`Item`

:class:`Body`

:class:`Attachment`

:class:`Address`

:class:`Outofoffice`

:class:`Quota`

:class:`Config`

:class:`Service`


"""

# Python 2.5 doesn't have with
from __future__ import with_statement

import contextlib
import cPickle as pickle
import csv
import daemon
import errno
import lockfile
import daemon.pidlockfile
import datetime
import grp
try:
    import libcommon # XXX distribute with python-mapi? or rewrite functionality here?
except ImportError:
    pass
import logging.handlers
from multiprocessing import Process, Queue
from Queue import Empty
import optparse
import os.path
import pwd
import socket
import sys
import StringIO
import struct
import threading
import time
import traceback
import mailbox
from email.parser import Parser
import signal
import ssl
import time

from MAPI.Util import *
from MAPI.Util.Generators import *
import MAPI.Util.AddressBook
import MAPI.Tags
import MAPI.Time
import _MAPICore
import inetmapi
import icalmapi

try:
    REV_TYPE
except NameError:
    REV_TYPE = {}
    for K, V in _MAPICore.__dict__.items():
        if K.startswith('PT_'):
            REV_TYPE[V] = K

try:
    REV_TAG
except NameError:
    REV_TAG = {}
    for K, V in MAPI.Tags.__dict__.items():
        if K.startswith('PR_'):
            REV_TAG[V] = K

PS_INTERNET_HEADERS = DEFINE_OLEGUID(0x00020386, 0, 0)
NAMED_PROPS_INTERNET_HEADERS = [MAPINAMEID(PS_INTERNET_HEADERS, MNID_STRING, u'x-original-to'),]

# XXX from common/mapiguidext.h
PSETID_Archive = DEFINE_GUID(0x72e98ebc, 0x57d2, 0x4ab5, 0xb0, 0xaa, 0xd5, 0x0a, 0x7b, 0x53, 0x1c, 0xb9)
PSETID_Appointment = DEFINE_OLEGUID(0x00062002, 0, 0)
PSETID_Task = DEFINE_OLEGUID(0x00062003, 0, 0)
PSETID_Address = DEFINE_OLEGUID(0x00062004, 0, 0)
PSETID_Common = DEFINE_OLEGUID(0x00062008, 0, 0)
PSETID_Log = DEFINE_OLEGUID(0x0006200A, 0, 0)
PSETID_Note = DEFINE_OLEGUID(0x0006200E, 0, 0)

NAMED_PROPS_ARCHIVER = [MAPINAMEID(PSETID_Archive, MNID_STRING, u'store-entryids'), MAPINAMEID(PSETID_Archive, MNID_STRING, u'item-entryids'), MAPINAMEID(PSETID_Archive, MNID_STRING, u'stubbed'),]

GUID_NAMESPACE = {
    PSETID_Archive: 'archive',
    PSETID_Common: 'common',
    PSETID_Appointment: 'appointment',
    PSETID_Task: 'task',
    PSETID_Address: 'address',
    PSETID_Log: 'log',
    PS_INTERNET_HEADERS: 'internet_headers',
}
NAMESPACE_GUID = dict((b,a) for (a,b) in GUID_NAMESPACE.items()) 

# XXX copied from common/ECDefs.h
def OBJECTCLASS(__type, __class):
    return (__type << 16) | (__class & 0xFFFF)

OBJECTTYPE_MAILUSER = 1
ACTIVE_USER = OBJECTCLASS(OBJECTTYPE_MAILUSER, 1)
NONACTIVE_USER = OBJECTCLASS(OBJECTTYPE_MAILUSER, 2)

# XXX copied from zarafa-msr/main.py
MUIDECSAB = DEFINE_GUID(0x50a921ac, 0xd340, 0x48ee, 0xb3, 0x19, 0xfb, 0xa7, 0x53, 0x30, 0x44, 0x25)
def DEFINE_ABEID(type, id):
    return struct.pack("4B16s3I4B", 0, 0, 0, 0, MUIDECSAB, 0, type, id, 0, 0, 0, 0)
EID_EVERYONE = DEFINE_ABEID(MAPI_DISTLIST, 1)

ADDR_PROPS = [ 
    (PR_ADDRTYPE_W, PR_EMAIL_ADDRESS_W, PR_ENTRYID, PR_DISPLAY_NAME_W, PR_SEARCH_KEY),
    (PR_SENDER_ADDRTYPE_W, PR_SENDER_EMAIL_ADDRESS_W, PR_SENDER_ENTRYID, PR_SENDER_NAME_W, PR_SENDER_SEARCH_KEY),
    (PR_RECEIVED_BY_ADDRTYPE_W, PR_RECEIVED_BY_EMAIL_ADDRESS_W, PR_RECEIVED_BY_ENTRYID, PR_RECEIVED_BY_NAME_W, PR_RECEIVED_BY_SEARCH_KEY),
    (PR_ORIGINAL_SENDER_ADDRTYPE_W, PR_ORIGINAL_SENDER_EMAIL_ADDRESS_W, PR_ORIGINAL_SENDER_ENTRYID, PR_ORIGINAL_SENDER_NAME_W, PR_ORIGINAL_SENDER_SEARCH_KEY),
    (PR_ORIGINAL_AUTHOR_ADDRTYPE_W, PR_ORIGINAL_AUTHOR_EMAIL_ADDRESS_W, PR_ORIGINAL_AUTHOR_ENTRYID, PR_ORIGINAL_AUTHOR_NAME_W, PR_ORIGINAL_AUTHOR_SEARCH_KEY),
    (PR_SENT_REPRESENTING_ADDRTYPE_W, PR_SENT_REPRESENTING_EMAIL_ADDRESS_W, PR_SENT_REPRESENTING_ENTRYID, PR_SENT_REPRESENTING_NAME_W, PR_SENT_REPRESENTING_SEARCH_KEY),
    (PR_RCVD_REPRESENTING_ADDRTYPE_W, PR_RCVD_REPRESENTING_EMAIL_ADDRESS_W, PR_RCVD_REPRESENTING_ENTRYID, PR_RCVD_REPRESENTING_NAME_W, PR_RCVD_REPRESENTING_SEARCH_KEY),
]

# Common/RecurrenceState.h
# Defines for recurrence exceptions
ARO_SUBJECT =	0x0001
ARO_MEETINGTYPE = 0x0002
ARO_REMINDERDELTA = 	0x0004
ARO_REMINDERSET	= 0x0008
ARO_LOCATION = 0x0010
ARO_BUSYSTATUS	= 0x0020
ARO_ATTACHMENT = 0x0040
ARO_SUBTYPE = 0x0080
ARO_APPTCOLOR = 0x0100
ARO_EXCEPTIONAL_BODY = 0x0200

# location of entryids in PR_IPM_OL2007_ENTRYIDS
RSF_PID_RSS_SUBSCRIPTION = 0x8001
RSF_PID_SUGGESTED_CONTACTS = 0x8008


def _stream(mapiobj, proptag):
    stream = mapiobj.OpenProperty(proptag, IID_IStream, 0, 0)
    data = []
    while True:
        blup = stream.Read(0xFFFFF) # 1 MB
        if len(blup) == 0:
            break
        data.append(blup)
    data = ''.join(data)
    if PROP_TYPE(proptag) == PT_UNICODE:
        data = data.decode('utf-32le') # under windows them be utf-16le?
    return data

def _prop(self, mapiobj, proptag):
    if isinstance(proptag, (int, long)):
        try:
            sprop = HrGetOneProp(mapiobj, proptag)
        except MAPIErrorNotEnoughMemory:
            data = _stream(mapiobj, proptag)
            sprop = SPropValue(proptag, data)
        return Property(mapiobj, sprop)
    else:
        namespace, name = proptag.split(':') # XXX syntax
        if name.isdigit(): # XXX
            name = int(name)
        for prop in self.props(namespace=namespace): # XXX sloow, streaming
            if prop.name == name:
                return prop
        raise MAPIErrorNotFound

def _props(mapiobj, namespace=None):
    # XXX show and stream large properties
    proptags = mapiobj.GetPropList(MAPI_UNICODE)
    sprops = mapiobj.GetProps(proptags, MAPI_UNICODE)
    props = [Property(mapiobj, sprop) for sprop in sprops]
    for p in sorted(props):
        if not namespace or p.namespace == namespace:
            yield p

def _state(mapiobj, associated=False):
    exporter = mapiobj.OpenProperty(PR_CONTENTS_SYNCHRONIZER, IID_IExchangeExportChanges, 0, 0)
    if associated:
        exporter.Config(None, SYNC_NORMAL | SYNC_ASSOCIATED | SYNC_CATCHUP, None, None, None, None, 0)
    else:
        exporter.Config(None, SYNC_NORMAL | SYNC_CATCHUP, None, None, None, None, 0)
    steps, step = None, 0
    while steps != step:
        steps, step = exporter.Synchronize(step)
    stream = IStream()
    exporter.UpdateState(stream)
    stream.Seek(0, MAPI.STREAM_SEEK_SET)
    return bin2hex(stream.Read(0xFFFFF))

def _sync(server, syncobj, importer, state, log, max_changes, associated=False):
    importer = TrackingContentsImporter(server, importer, log)
    exporter = syncobj.OpenProperty(PR_CONTENTS_SYNCHRONIZER, IID_IExchangeExportChanges, 0, 0)
    stream = IStream()
    stream.Write(state.decode('hex'))
    stream.Seek(0, MAPI.STREAM_SEEK_SET)
    if associated:
        exporter.Config(stream, SYNC_NORMAL | SYNC_ASSOCIATED | SYNC_UNICODE, importer, None, None, None, 0)
    else:
        exporter.Config(stream, SYNC_NORMAL | SYNC_UNICODE, importer, None, None, None, 0)
    step = retry = changes = 0
    while True:
        try:
            try:
                (steps, step) = exporter.Synchronize(step)
            finally:
                importer.skip = False
            changes += 1
            retry = 0
            if (steps == step) or (max_changes and changes >= max_changes):
                break
        except MAPIError, e:
            if log:
                log.warn("Received a MAPI error or timeout (error=0x%x, retry=%d/5)" % (e.hr, retry))
            time.sleep(5)
            if retry < 5:
                retry += 1
            else:
                if log:
                    log.error("Too many retries, skipping change")
                importer.skip = True # in case of a timeout or other issue, try to skip the change after trying several times
                retry = 0
    exporter.UpdateState(stream)
    stream.Seek(0, MAPI.STREAM_SEEK_SET)
    state = bin2hex(stream.Read(0xFFFFF))
    return state

def _openentry_raw(mapistore, entryid, flags): # avoid underwater action for archived items
    try:
        return mapistore.OpenEntry(entryid, IID_IECMessageRaw, flags)
    except MAPIErrorInterfaceNotSupported:
        return mapistore.OpenEntry(entryid, None, flags)

def _bestbody(mapiobj): # XXX we may want to use the swigged version in libcommon, once available
    # apparently standardized method for determining original message type!
    tag = PR_NULL
    props = mapiobj.GetProps([PR_BODY_W, PR_HTML, PR_RTF_COMPRESSED, PR_RTF_IN_SYNC], 0)

    if (props[3].ulPropTag != PR_RTF_IN_SYNC): # XXX why..
        return tag

    # MAPI_E_NOT_ENOUGH_MEMORY indicates the property exists, but has to be streamed
    if((props[0].ulPropTag == PR_BODY_W or (PROP_TYPE(props[0].ulPropTag) == PT_ERROR and props[0].Value == MAPI_E_NOT_ENOUGH_MEMORY)) and
       (PROP_TYPE(props[1].ulPropTag) == PT_ERROR and props[1].Value == MAPI_E_NOT_FOUND) and
       (PROP_TYPE(props[2].ulPropTag) == PT_ERROR and props[2].Value == MAPI_E_NOT_FOUND)):
        tag = PR_BODY_W

    # XXX why not just check MAPI_E_NOT_FOUND..?
    elif((props[1].ulPropTag == PR_HTML or (PROP_TYPE(props[1].ulPropTag) == PT_ERROR and props[1].Value == MAPI_E_NOT_ENOUGH_MEMORY)) and
         (PROP_TYPE(props[0].ulPropTag) == PT_ERROR and props[0].Value == MAPI_E_NOT_ENOUGH_MEMORY) and
         (PROP_TYPE(props[2].ulPropTag) == PT_ERROR and props[2].Value == MAPI_E_NOT_ENOUGH_MEMORY) and
         props[3].Value == False):
        tag = PR_HTML

    elif((props[2].ulPropTag == PR_RTF_COMPRESSED or (PROP_TYPE(props[2].ulPropTag) == PT_ERROR and props[2].Value == MAPI_E_NOT_ENOUGH_MEMORY)) and
         (PROP_TYPE(props[0].ulPropTag) == PT_ERROR and props[0].Value == MAPI_E_NOT_ENOUGH_MEMORY) and
         (PROP_TYPE(props[1].ulPropTag) == PT_ERROR and props[1].Value == MAPI_E_NOT_FOUND) and
         props[3].Value == True):
        tag = PR_RTF_COMPRESSED

    return tag

def _unpack_short(s, pos):
    return struct.unpack_from('<H', s, pos)[0]

def _unpack_long(s, pos):
    return struct.unpack_from('<L', s, pos)[0]

def _unpack_string(s, pos, length):
    return ''.join(struct.unpack_from('<' + 's' * length, s, pos))

def _pack_long(i):
    return struct.pack('<L', i)

def _rectime_to_unixtime(t):
    return (t - 194074560) * 60

def _unixtime_to_rectime(t):
    return int(t/60) + 194074560

def _extract_ipm_ol2007_entryids(blob, offset):
    # Extracts entryid's from PR_IPM_OL2007_ENTRYIDS blob using
    # logic from common/Util.cpp Util::ExtractAdditionalRenEntryID.
    pos = 0
    while True:
        blocktype = _unpack_short(blob, pos)
        if blocktype == 0:
            break
        pos += 2

        totallen = _unpack_short(blob, pos)
        pos += 2

        if blocktype == offset:
            pos += 2 # skip check
            sublen = _unpack_short(blob, pos)
            pos += 2
            return blob[pos:pos+sublen].encode('hex').upper()
        else:
            pos += totallen

class ZarafaException(Exception):
    pass

class ZarafaConfigException(ZarafaException):
    pass

class ZarafaNotFoundException(ZarafaException):
    pass


class SPropDelayedValue(SPropValue):
    def __init__(self, mapiobj, proptag):
        self.mapiobj = mapiobj
        self.ulPropTag = proptag
        self._Value = None

    @property
    def Value(self):
        if self._Value is None:
            try:
                self._Value = _stream(self.mapiobj, self.ulPropTag)
            except MAPIErrorNotFound: # XXX eg normalized subject streaming broken..?
                self._Value = None
        return self._Value


class Property(object):
    """ 
Wrapper around MAPI properties 

"""

    def __init__(self, parent_mapiobj, mapiobj): # XXX rethink attributes, names.. add guidname..?
        self._parent_mapiobj = parent_mapiobj

        if PROP_TYPE(mapiobj.ulPropTag) == PT_ERROR and mapiobj.Value == MAPI_E_NOT_ENOUGH_MEMORY:
            for proptype in (PT_BINARY, PT_UNICODE): # XXX slow, incomplete?
                proptag = (mapiobj.ulPropTag & 0xffff0000) | proptype
                try:
                    HrGetOneProp(parent_mapiobj, proptag) # XXX: Unicode issue?? calls GetProps([proptag], 0)
                except MAPIErrorNotEnoughMemory:
                    mapiobj = SPropDelayedValue(parent_mapiobj, proptag)
                    break
                except MAPIErrorNotFound:
                    pass

        self.proptag = mapiobj.ulPropTag
        self.id_ = self.proptag >> 16
        self.mapiobj = mapiobj
        self._value = None

        self.idname = REV_TAG.get(self.proptag) # XXX slow, often unused: make into properties?
        self.type_ = PROP_TYPE(self.proptag)
        self.typename = REV_TYPE.get(self.type_)
        self.named = (self.id_ >= 0x8000)
        self.kind = None
        self.kindname = None
        self.guid = None
        self.name = None
        self.namespace = None

        if self.named:
            try:
                lpname = self._parent_mapiobj.GetNamesFromIDs([self.proptag], None, 0)[0]
                self.guid = bin2hex(lpname.guid)
                self.namespace = GUID_NAMESPACE.get(lpname.guid)
                self.name = lpname.id
                self.kind = lpname.kind
                self.kindname = 'MNID_STRING' if lpname.kind == MNID_STRING else 'MNID_ID'
            except MAPIErrorNoSupport: # XXX user.props()?
                pass

    def get_value(self):
        if self._value is None:
            if self.type_ == PT_SYSTIME: # XXX generalize, property?
                #
                # The datetime object is of "naive" type, has local time and
                # no TZ info. :-(
                #
                self._value = datetime.datetime.fromtimestamp(self.mapiobj.Value.unixtime)
                
            else:
                self._value = self.mapiobj.Value
        return self._value

    def set_value(self, value):
        self._value = value
        if self.type_ == PT_SYSTIME:
            # Timezones are handled.
            value = MAPI.Time.unixtime(time.mktime(value.timetuple()))
        self._parent_mapiobj.SetProps([SPropValue(self.proptag, value)])
        self._parent_mapiobj.SaveChanges(KEEP_OPEN_READWRITE)
    value = property(get_value, set_value)

    @property
    def strid(self):
        if self.named:
            return '%s:%s' % (self.namespace, self.name)
        else:
            return self.idname if self.idname else '' # FIXME: should never be None

    @property
    def strval(self):
        def flatten(v):
            if isinstance(v, list):
                return ','.join(flatten(e) for e in v)
            elif isinstance(v, bool):
                return '01'[v]
            elif self.type_ in (PT_BINARY, PT_MV_BINARY):
                return v.encode('hex').upper()
            else:
                return unicode(v).encode('utf-8')
        return flatten(self.value)

    def __lt__(self, prop):
        return self.proptag < prop.proptag

    def __unicode__(self):
        return u'Property(%s)' % self.strid

    # TODO: check if data is binary and convert it to hex
    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Table(object):
    """
    Wrapper around MAPI tables

"""

    def __init__(self, server, mapitable, proptag, restriction=None, order=None, columns=None):
        self.server = server
        self.mapitable = mapitable
        self.proptag = proptag
        if columns:
            mapitable.SetColumns(columns, 0)
        else:
            cols = mapitable.QueryColumns(TBL_ALL_COLUMNS) # some columns are hidden by default XXX result (if at all) depends on table implementation 
            cols = cols or mapitable.QueryColumns(0) # fall-back 
            mapitable.SetColumns(cols, 0)

    @property
    def header(self):
        return [REV_TAG.get(c, hex(c)) for c in self.mapitable.QueryColumns(0)]

    def rows(self):
        try:
            for row in self.mapitable.QueryRows(-1, 0):
                yield [Property(self.server.mapistore, c) for c in row]
        except MAPIErrorNotFound:
            pass

    def dict_rows(self):
        for row in self.mapitable.QueryRows(-1, 0):
            yield dict((c.ulPropTag, c.Value) for c in row)

    def dict_(self, key, value):
        d = {}
        for row in self.mapitable.QueryRows(-1, 0):
            d[PpropFindProp(row, key).Value] = PpropFindProp(row, value).Value
        return d

    def index(self, key):
        d = {}
        for row in self.mapitable.QueryRows(-1, 0):
            d[PpropFindProp(row, key).Value] = dict((c.ulPropTag, c.Value) for c in row)
        return d
 
    def data(self, header=False):
        data = [[p.strval for p in row] for row in self.rows()]
        if header:
            data = [self.header] + data
        return data

    def text(self, borders=False):
        result = []
        data = self.data(header=True)
        colsizes = [max(len(d[i]) for d in data) for i in range(len(data[0]))]
        for d in data:
            line = []
            for size, c in zip(colsizes, d):
                line.append(c.ljust(size))
            result.append(' '.join(line))
        return '\n'.join(result)

    def csv(self, *args, **kwargs):
        csvfile = StringIO.StringIO()
        writer = csv.writer(csvfile, *args, **kwargs)
        writer.writerows(self.data(header=True))
        return csvfile.getvalue()

    def sort(self, tags):
        if not isinstance(tags, tuple):
            tags = (tags,)
        self.mapitable.SortTable(SSortOrderSet([SSort(abs(tag), TABLE_SORT_DESCEND if tag < 0 else TABLE_SORT_ASCEND) for tag in tags], 0, 0), 0)

    def __iter__(self):
        return self.rows()

    def __repr__(self):
        return u'Table(%s)' % REV_TAG.get(self.proptag)

class Server(object):
    """ 
Server class 

By default, tries to connect to a Zarafa server as configured in ``/etc/zarafa/admin.cfg`` or at UNIX socket ``/var/run/zarafa``

Looks at command-line to see if another server address or other related options were given (such as -c, -s, -k, -p)

:param server_socket: similar to 'server_socket' option in config file
:param sslkey_file: similar to 'sslkey_file' option in config file
:param sslkey_pass: similar to 'sslkey_pass' option in config file
:param config: path of configuration file containing common server options, for example ``/etc/zarafa/admin.cfg``
:param auth_user: username to user for user authentication
:param auth_pass: password to use for user authentication
:param log: logger object to receive useful (debug) information
:param options: OptionParser instance to get settings from (see :func:`parser`)

"""

    def __init__(self, options=None, config=None, sslkey_file=None, sslkey_pass=None, server_socket=None, auth_user=None, auth_pass=None, log=None, service=None, mapisession=None):
        self.options = options
        self.config = config
        self.sslkey_file = sslkey_file
        self.sslkey_pass = sslkey_pass
        self.server_socket = server_socket
        self.service = service
        self.log = log
        self.mapisession = mapisession

        if not self.mapisession:
            # get cmd-line options
            if not self.options:
                self.options, args = parser().parse_args()

            # determine config file
            if config:
                pass
            elif getattr(self.options, 'config_file', None):
                config_file = os.path.abspath(self.options.config_file)
                config = globals()['Config'](None, filename=self.options.config_file) # XXX snarf
            else:
                config_file = '/etc/zarafa/admin.cfg'
                try:
                    file(config_file) # check if accessible
                    config = globals()['Config'](None, filename=config_file) # XXX snarf
                except IOError:
                    pass
            self.config = config

            # get defaults
            if os.getenv('ZARAFA_SOCKET'): # env variable used in testset
                self.server_socket = os.getenv('ZARAFA_SOCKET')
            elif config:
                if not (server_socket or getattr(self.options, 'server_socket')): # XXX generalize
                    self.server_socket = config.get('server_socket')
                    self.sslkey_file = config.get('sslkey_file')
                    self.sslkey_pass = config.get('sslkey_pass')
            self.server_socket = self.server_socket or 'file:///var/run/zarafa'

            # override with explicit or command-line args
            self.server_socket = server_socket or getattr(self.options, 'server_socket', None) or self.server_socket
            self.sslkey_file = sslkey_file or getattr(self.options, 'sslkey_file', None) or self.sslkey_file
            self.sslkey_pass = sslkey_pass or getattr(self.options, 'sslkey_pass', None) or self.sslkey_pass

            # make actual connection. in case of service, wait until this succeeds.
            self.auth_user = auth_user or getattr(self.options, 'auth_user', None) or 'SYSTEM' # XXX override with args
            self.auth_pass = auth_pass or getattr(self.options, 'auth_pass', None) or ''
            while True:
                try:
                    self.mapisession = OpenECSession(self.auth_user, self.auth_pass, self.server_socket, sslkey_file=self.sslkey_file, sslkey_pass=self.sslkey_pass) #, providers=['ZARAFA6','ZCONTACTS'])
                    break
                except MAPIErrorNetworkError:
                    if service:
                        service.log.warn("could not connect to server at '%s', retrying in 5 sec" % self.server_socket)
                        time.sleep(5)
                    else:
                        raise ZarafaException("could not connect to server at '%s'" % self.server_socket)

        # start talking dirty
        self.mapistore = GetDefaultStore(self.mapisession)
        self.admin_store = Store(self, self.mapistore)
        self.sa = self.mapistore.QueryInterface(IID_IECServiceAdmin)
        self.ems = self.mapistore.QueryInterface(IID_IExchangeManageStore)
        self.ab = self.mapisession.OpenAddressBook(0, None, 0) # XXX
        entryid = HrGetOneProp(self.mapistore, PR_STORE_ENTRYID).Value
        self.pseudo_url = entryid[entryid.find('pseudo:'):-1] # XXX ECSERVER
        self.name = self.pseudo_url[9:] # XXX get this kind of stuff from pr_ec_statstable_servers..?
        self._archive_sessions = {}

    def nodes(self): # XXX delay mapi sessions until actually needed
        for row in self.table(PR_EC_STATSTABLE_SERVERS).dict_rows():
            yield Server(options=self.options, config=self.config, sslkey_file=self.sslkey_file, sslkey_pass=self.sslkey_pass, server_socket=row[PR_EC_STATS_SERVER_HTTPSURL], log=self.log, service=self.service)

    def table(self, name, restriction=None, order=None, columns=None):
        return Table(self, self.mapistore.OpenProperty(name, IID_IMAPITable, MAPI_UNICODE, 0), name, restriction=restriction, order=order, columns=columns)

    def tables(self):
        for table in (PR_EC_STATSTABLE_SYSTEM, PR_EC_STATSTABLE_SESSIONS, PR_EC_STATSTABLE_USERS, PR_EC_STATSTABLE_COMPANY, PR_EC_STATSTABLE_SERVERS):
            try:
                yield self.table(table)
            except MAPIErrorNotFound:
                pass

    def gab_table(self): # XXX separate addressbook class? useful to add to self.tables?
        gab = self.ab.OpenEntry(self.ab.GetDefaultDir(), None, 0)
        ct = gab.GetContentsTable(MAPI_DEFERRED_ERRORS)
        return Table(self, ct, PR_CONTAINER_CONTENTS)

    def _archive_session(self, host):
        if host not in self._archive_sessions:
            try:
                self._archive_sessions[host] = OpenECSession('SYSTEM', '', 'https://%s:237/zarafa' % host, sslkey_file=self.sslkey_file, sslkey_pass=self.sslkey_pass)
            except: # MAPIErrorLogonFailed, MAPIErrorNetworkError:
                self._archive_sessions[host] = None # XXX avoid subsequent timeouts for now
                raise ZarafaException("could not connect to server at '%s'" % host)
        return self._archive_sessions[host]

    @property
    def guid(self):
        """ Server GUID """

        return bin2hex(HrGetOneProp(self.mapistore, PR_MAPPING_SIGNATURE).Value)

    def user(self, name):
        """ Return :class:`user <User>` with given name; raise exception if not found """

        return User(name, self)

    def get_user(self, name):
        """ Return :class:`user <User>` with given name or *None* if not found """

        try:
            return self.user(name)
        except ZarafaException:
            pass

    def users(self, remote=False, system=False, parse=True):
        """ Return all :class:`users <User>` on server

            :param remote: include users on remote server nodes
            :param system: include system users
        """

        if parse and getattr(self.options, 'users', None):
            for username in self.options.users:
                yield User(username, self)
            return
        try:
            for name in self._companylist():
                for user in Company(self, name).users(): # XXX remote/system check
                    yield user
        except MAPIErrorNoSupport:
            for username in AddressBook.GetUserList(self.mapisession, None, MAPI_UNICODE):
                user = User(username, self)
                if system or username != u'SYSTEM':
                    if remote or user._ecuser.Servername in (self.name, ''):
                        yield user
                    # XXX following two lines not necessary with python-mapi from trunk
                    elif not remote and user.local: # XXX check if GetUserList can filter local/remote users
                        yield user

    def create_user(self, name, email=None, password=None, company=None, fullname=None, create_store=True):
        """ Create a new :class:`user <Users>` on the server

        :param name: the login name of the new user
        :param email: the email address of the user
        :param password: the login password of the user
        :param company: the company of the user
        :param fullname: the full name of the user
        :param create_store: should a store be created for the new user
        :return: :class:`<User>`
        """
        name = unicode(name)
        fullname = unicode(fullname or '')
        if email:
            email = unicode(email)
        else:
            email = u'%s@%s' % (name, socket.gethostname())
        if password:
            password = unicode(password)
        if company:
            company = unicode(company)
        if company and company != u'Default':
            usereid = self.sa.CreateUser(ECUSER(u'%s@%s' % (name, company), password, email, fullname), MAPI_UNICODE)
            user = self.company(company).user(u'%s@%s' % (name, company))
        else:
            usereid = self.sa.CreateUser(ECUSER(name, password, email, fullname), MAPI_UNICODE)
            user = self.user(name)
        if create_store:
            self.sa.CreateStore(ECSTORE_TYPE_PRIVATE, user.userid.decode('hex'))
        return user

    def remove_user(self, name): # XXX delete(object)?
        user = self.user(name)
        self.sa.DeleteUser(user._ecuser.UserID)

    def company(self, name, create=False):
        """ Return :class:`company <Company>` with given name; raise exception if not found """

        try:
            return Company(self, name)
        except ZarafaNotFoundException:
            if create:
                return self.create_company(name)
            else:
                raise

    def get_company(self, name):
        """ Return :class:`company <Company>` with given name or *None* if not found """

        try:
            return self.company(name)
        except ZarafaException:
            pass

    def remove_company(self, name): # XXX delete(object)?
        company = self.company(name)
        self.sa.DeleteCompany(company._eccompany.CompanyID)

    def _companylist(self): # XXX fix self.sa.GetCompanyList(MAPI_UNICODE)? looks like it's not swigged correctly?
        self.sa.GetCompanyList(MAPI_UNICODE) # XXX exception for single-tenant....
        return MAPI.Util.AddressBook.GetCompanyList(self.mapisession, MAPI_UNICODE)

    def companies(self, remote=False, parse=True): # XXX remote?
        """ Return all :class:`companies <Company>` on server

            :param remote: include companies without users on this server node
        """
        if parse and getattr(self.options, 'companies', None):
            for name in self.options.companies:
                yield Company(self, name)
            return
        try:
            for name in self._companylist():
                yield Company(self, name)
        except MAPIErrorNoSupport:
            yield Company(self, u'Default')

    def create_company(self, name):
        name = unicode(name)
        companyeid = self.sa.CreateCompany(ECCOMPANY(name, None), MAPI_UNICODE)
        return self.company(name)

    def _store(self, guid):
        if len(guid) != 32:
            raise ZarafaException("invalid store id: '%s'" % guid)
        try:
            storeid = guid.decode('hex')
        except:
            raise ZarafaException("invalid store id: '%s'" % guid)
        table = self.ems.GetMailboxTable(None, 0) # XXX merge with Store.__init__
        table.SetColumns([PR_ENTRYID], 0)
        table.Restrict(SPropertyRestriction(RELOP_EQ, PR_STORE_RECORD_KEY, SPropValue(PR_STORE_RECORD_KEY, storeid)), TBL_BATCH)
        for row in table.QueryRows(-1, 0):
            return self.mapisession.OpenMsgStore(0, row[0].Value, None, MDB_WRITE)
        raise ZarafaException("no such store: '%s'" % guid)

    def groups(self):
        for name in MAPI.Util.AddressBook.GetGroupList(self.mapisession, None, MAPI_UNICODE):
            yield Group(name, self)

    def group(self, name):
        return Group(name, self)

    def create_group(self, name, fullname='', email='', hidden = False, groupid = None):
        name = unicode(name) # XXX: fullname/email unicode?
        email = unicode(email)
        fullname = unicode(fullname)
        companyeid = self.sa.CreateGroup(ECGROUP(name, fullname, email, int(hidden), groupid), MAPI_UNICODE)

        return self.group(name)

    def remove_group(self, name):
        group = self.group(name)
        self.sa.DeleteGroup(group._ecgroup.GroupID)

    def store(self, guid):
        """ Return :class:`store <Store>` with given GUID; raise exception if not found """

        if guid == 'public':
            return self.public_store
        else:
            return Store(self, self._store(guid))

    def get_store(self, guid):
        """ Return :class:`store <Store>` with given GUID or *None* if not found """

        try:
            return self.store(guid)
        except ZarafaException:
            pass

    def stores(self, system=False, remote=False, parse=True): # XXX implement remote
        """ Return all :class:`stores <Store>` on server node

        :param system: include system stores
        :param remote: include stores on other nodes

        """
    
        if parse and getattr(self.options, 'stores', None):
            for guid in self.options.stores:
                if guid == 'public': # XXX check self.options.companies?
                    yield self.public_store
                else:
                    yield Store(self, self._store(guid))
            return

        table = self.ems.GetMailboxTable(None, 0)
        table.SetColumns([PR_DISPLAY_NAME_W, PR_ENTRYID], 0)
        for row in table.QueryRows(-1, 0):
            store = Store(self, self.mapisession.OpenMsgStore(0, row[1].Value, None, MDB_WRITE))
            if system or store.public or (store.user and store.user.name != 'SYSTEM'):
                yield store

    def create_store(self, public=False):
        if public:
            mapistore = self.sa.CreateStore(ECSTORE_TYPE_PUBLIC, EID_EVERYONE)
            return Store(self, mapistore)
        # XXX

    def unhook_store(self, user):
        store = user.store
        self.sa.UnhookStore(ECSTORE_TYPE_PRIVATE, user.userid.decode('hex'))
        return store

    def hook_store(self, store, user):
        self.sa.HookStore(ECSTORE_TYPE_PRIVATE, user.userid.decode('hex'), store.guid.decode('hex'))
        return store.guid

    def sync_users(self):
        # Flush user cache on the server
        self.sa.SyncUsers(None)

    @property
    def public_store(self):
        """ public :class:`store <Store>` in single-company mode """

        try:
            self.sa.GetCompanyList(MAPI_UNICODE)
            raise ZarafaException('request for server-wide public store in multi-company setup')
        except MAPIErrorNoSupport:
            return self.companies().next().public_store

    @property
    def state(self):
        """ Current server state """

        return _state(self.mapistore)

    def sync(self, importer, state, log=None, max_changes=None):
        """ Perform synchronization against server node

        :param importer: importer instance with callbacks to process changes
        :param state: start from this state (has to be given)
        :log: logger instance to receive important warnings/errors
        """

        importer.store = None
        return _sync(self, self.mapistore, importer, state, log or self.log, max_changes)

    def __unicode__(self):
        return u'Server(%s)' % self.server_socket

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Group(object):
    def __init__(self, name, server=None):
        self.server = server or Server()
        self._name = unicode(name)
        self._ecgroup = self.server.sa.GetGroup(self.server.sa.ResolveGroupName(self._name, MAPI_UNICODE), MAPI_UNICODE)

    def users(self):
        for ecuser in self.server.sa.GetUserListOfGroup(self._ecgroup.GroupID, MAPI_UNICODE):
            if ecuser.Username == 'SYSTEM':
                continue
            try:
                yield User(ecuser.Username, self.server)
            except ZarafaException: # XXX everyone, groups are included as users..
                pass

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._update(name=unicode(value))

    @property
    def email(self):
        return self._ecgroup.Email

    @email.setter
    def email(self, value):
        self._update(email=unicode(value))

    @property
    def fullname(self):
        return self._ecgroup.Fullname

    @fullname.setter
    def fullname(self, value):
        self._update(fullname=unicode(value))

    @property
    def hidden(self):
        return self._ecgroup.IsHidden == True

    @hidden.setter
    def hidden(self, value):
        self._update(hidden=value)

    @property
    def groupid(self):
        return bin2hex(self._ecgroup.GroupID)

    def add_user(self, user):
        self.server.sa.AddGroupUser(self._ecgroup.GroupID, user._ecuser.UserID)

    def remove_user(self, user):
        self.server.sa.DeleteGroupUser(self._ecgroup.GroupID, user._ecuser.UserID)

    def _update(self, **kwargs):
        # XXX: crashes server on certain characters...
        self._name = kwargs.get('name', self.name)
        fullname = kwargs.get('fullname', self.fullname)
        email = kwargs.get('email', self.email)
        hidden = kwargs.get('hidden', self.hidden)
        group = ECGROUP(self._name, fullname, email, int(hidden), self._ecgroup.GroupID)
        self.server.sa.SetGroup(group, MAPI_UNICODE)
        self._ecgroup = self.server.sa.GetGroup(self.server.sa.ResolveGroupName(self._name, MAPI_UNICODE), MAPI_UNICODE)

    def __unicode__(self):
        return u"Group('%s')" % self.name

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')


class Company(object):
    """ Company class """

    def __init__(self, server, name): # XXX Company(name)
        self._name = name = unicode(name)
        self.server = server
        if name != u'Default': # XXX
            try:
                self._eccompany = self.server.sa.GetCompany(self.server.sa.ResolveCompanyName(self._name, MAPI_UNICODE), MAPI_UNICODE)
            except MAPIErrorNotFound:
                raise ZarafaNotFoundException("no such company: '%s'" % name)

    @property
    def name(self):
        """ Company name """

        return self._name

    def store(self, guid):
        if guid == 'public':
            return self.public_store
        else:
            return self.server.store(guid)

    @property
    def public_store(self):
        """ Company public :class:`store <Store>` """

        if self._name == u'Default': # XXX 
            pubstore = GetPublicStore(self.server.mapisession)
            if pubstore is None:
                return None
            return Store(self.server, pubstore)
        publicstoreid = self.server.ems.CreateStoreEntryID(None, self._name, MAPI_UNICODE)
        publicstore = self.server.mapisession.OpenMsgStore(0, publicstoreid, None, MDB_WRITE)
        return Store(self.server, publicstore)

    def create_store(self, public=False):
        if public:
            if self._name == u'Default':
                mapistore = self.server.sa.CreateStore(ECSTORE_TYPE_PUBLIC, EID_EVERYONE)
            else:
                mapistore = self.server.sa.CreateStore(ECSTORE_TYPE_PUBLIC, self._eccompany.CompanyID)
            return Store(self.server, mapistore)
        # XXX

    def user(self, name):
        """ Return :class:`user <User>` with given name; raise exception if not found """

        name = unicode(name)
        for user in self.users():
            if user.name == name:
                return User(name, self.server)

    def get_user(self, name):
        """ Return :class:`user <User>` with given name or *None* if not found """

        try:
            return self.user(name)
        except ZarafaException:
            pass

    def users(self):
        """ Return all :class:`users <User>` within company """

        for username in AddressBook.GetUserList(self.server.mapisession, self._name if self._name != u'Default' else None, MAPI_UNICODE): # XXX serviceadmin?
            if username != 'SYSTEM':
                yield User(username, self.server)

    def create_user(self, name, password=None):
        self.server.create_user(name, password=password, company=self._name)
        return self.user('%s@%s' % (name, self._name))

    def groups(self):
        if self.name == u'Default': # XXX
            for ecgroup in self.server.sa.GetGroupList(None, MAPI_UNICODE):
                yield Group(ecgroup.Groupname, self)
        else:
            for ecgroup in self.server.sa.GetGroupList(self._eccompany.CompanyID, MAPI_UNICODE):
                yield Group(ecgroup.Groupname, self)

    @property
    def quota(self):
        """ Company :class:`Quota` """

        if self._name == u'Default':
            return Quota(self.server, None)
        else:
            return Quota(self.server, self._eccompany.CompanyID)

    def __unicode__(self):
        return u"Company('%s')" % self._name

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Store(object):
    """ 
    Item store
    
    """

    def __init__(self, server, mapiobj=None):
        if isinstance(server, str): # XXX fix args
            guid, server = server, Server()
            mapiobj = server._store(guid)
        self.server = server
        self.mapiobj = mapiobj
        self._root = self.mapiobj.OpenEntry(None, None, 0)

    @property
    def public(self):
        return self.prop(PR_MDB_PROVIDER).mapiobj.Value == ZARAFA_STORE_PUBLIC_GUID

    @property
    def guid(self):
        """ Store GUID """

        return bin2hex(self.prop(PR_STORE_RECORD_KEY).value)

    @property
    def hierarchyid(self):
        return  self.prop(PR_EC_HIERARCHYID).value

    @property
    def root(self):
        """ :class:`Folder` designated as store root """

        return Folder(self, HrGetOneProp(self._root, PR_ENTRYID).Value)

    @property
    def inbox(self):
        """ :class:`Folder` designated as inbox """

        return Folder(self, self.mapiobj.GetReceiveFolder('IPM', 0)[0])

    @property
    def junk(self):
        """ :class:`Folder` designated as junk """

        # PR_ADDITIONAL_REN_ENTRYIDS is a multi-value property, 4th entry is the junk folder
        return Folder(self, HrGetOneProp(self._root, PR_ADDITIONAL_REN_ENTRYIDS).Value[4])

    @property
    def calendar(self):
        """ :class:`Folder` designated as calendar """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_APPOINTMENT_ENTRYID).Value)

    @property
    def outbox(self):
        """ :class:`Folder` designated as outbox """

        return Folder(self, HrGetOneProp(self.mapiobj, PR_IPM_OUTBOX_ENTRYID).Value)

    @property
    def contacts(self):
        """ :class:`Folder` designated as contacts """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_CONTACT_ENTRYID).Value)

    @property
    def drafts(self):
        """ :class:`Folder` designated as drafts """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_DRAFTS_ENTRYID).Value)

    @property
    def wastebasket(self):
        """ :class:`Folder` designated as wastebasket """

        return Folder(self, HrGetOneProp(self.mapiobj, PR_IPM_WASTEBASKET_ENTRYID).Value)

    @property
    def journal(self):
        """ :class:`Folder` designated as journal """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_JOURNAL_ENTRYID).Value)

    @property
    def notes(self):
        """ :class:`Folder` designated as notes """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_NOTE_ENTRYID).Value)

    @property
    def sentmail(self):
        """ :class:`Folder` designated as sentmail """

        return Folder(self, HrGetOneProp(self.mapiobj, PR_IPM_SENTMAIL_ENTRYID).Value)

    @property
    def tasks(self):
        """ :class:`Folder` designated as tasks """

        return Folder(self, HrGetOneProp(self._root, PR_IPM_TASK_ENTRYID).Value)

    @property
    def subtree(self):
        """ :class:`Folder` designated as IPM.Subtree """

        if self.public:
            ipmsubtreeid = HrGetOneProp(self.mapiobj, PR_IPM_PUBLIC_FOLDERS_ENTRYID).Value
        else:
            ipmsubtreeid = HrGetOneProp(self.mapiobj, PR_IPM_SUBTREE_ENTRYID).Value

        return Folder(self, ipmsubtreeid)

    @property
    def suggested_contacts(self):
        """ :class`Folder` designated as Suggested contacts"""

        entryid = _extract_ipm_ol2007_entryids(self.inbox.prop(PR_IPM_OL2007_ENTRYIDS).value, RSF_PID_SUGGESTED_CONTACTS)

        return Folder(self, entryid.decode('hex'))

    @property
    def rss(self):
        """ :class`Folder` designated as RSS items"""

        entryid = _extract_ipm_ol2007_entryids(self.inbox.prop(PR_IPM_OL2007_ENTRYIDS).value, RSF_PID_RSS_SUBSCRIPTION)

        return Folder(self, entryid.decode('hex'))

    @property
    def user(self):
        """ Store :class:`owner <User>` """

        try:
            userid = HrGetOneProp(self.mapiobj, PR_MAILBOX_OWNER_ENTRYID).Value
            return User(self.server.sa.GetUser(userid, MAPI_UNICODE).Username, self.server)
        except MAPIErrorNotFound:
            pass

    def folder(self, key, recurse=True): # XXX sloowowowww
        """ Return :class:`Folder` with given name or entryid; raise exception if not found

            :param key: name or entryid
        """

        if len(key) == 96: # PR_ENTRYID is always 96
            try:
                folder = Folder(self, key.decode('hex'))
                return folder
            except (MAPIErrorInvalidEntryid, MAPIErrorNotFound, TypeError):
                pass

        matches = [f for f in self.folders(system=True, recurse=recurse) if f.entryid == key or f.name == key]
        if len(matches) == 0:
            raise ZarafaNotFoundException("no such folder: '%s'" % key)
        elif len(matches) > 1:
            raise ZarafaNotFoundException("multiple folders with name/entryid '%s'" % key)
        else:
            return matches[0]

    def get_folder(self, key):
        """ Return :class:`folder <Folder>` with given name/entryid or *None* if not found """

        try:
            return self.folder(key)
        except ZarafaException:
            pass

    def folders(self, recurse=True, system=False, mail=False, parse=True): # XXX mail flag semantic difference?
        """ Return all :class:`folders <Folder>` in store

        :param recurse: include all sub-folders
        :param system: include system folders
        :param mail: only include mail folders

        """

        # filter function to determine if we return a folder or not
        filter_names = None
        if parse and getattr(self.server.options, 'folders', None):
            filter_names = self.server.options.folders

        def check_folder(folder):
            if filter_names and folder.name not in filter_names:
                return False
            if mail:
                try:
                    if folder.prop(PR_CONTAINER_CLASS) != 'IPF.Note':
                        return False
                except MAPIErrorNotFound:
                    pass
            return True

        # determine root folder
        if system:
            root = self._root
        else:
            try:
                if self.public:
                    ipmsubtreeid = HrGetOneProp(self.mapiobj, PR_IPM_PUBLIC_FOLDERS_ENTRYID).Value
                else:
                    ipmsubtreeid = HrGetOneProp(self.mapiobj, PR_IPM_SUBTREE_ENTRYID).Value
            except MAPIErrorNotFound: # SYSTEM store
                return
            root = self.mapiobj.OpenEntry(ipmsubtreeid, IID_IMAPIFolder, MAPI_DEFERRED_ERRORS)

        # loop over and filter all subfolders 
        table = root.GetHierarchyTable(0)
        table.SetColumns([PR_ENTRYID], TBL_BATCH)
        table.Restrict(SPropertyRestriction(RELOP_EQ, PR_FOLDER_TYPE, SPropValue(PR_FOLDER_TYPE, FOLDER_GENERIC)), TBL_BATCH)
        for row in table.QueryRows(-1, 0):
            folder = Folder(self, row[0].Value)
            folder.depth = 0
            if check_folder(folder):
                yield folder
            if recurse:
                for subfolder in folder.folders(depth=1):
                    if check_folder(subfolder):
                        yield subfolder

    def item(self, entryid):
        """ Return :class:`Item` with given entryid; raise exception of not found """ # XXX better exception?

        item = Item() # XXX copy-pasting..
        item.store = self
        item.server = self.server
        item.mapiobj = _openentry_raw(self.mapiobj, entryid.decode('hex'), MAPI_MODIFY)
        return item

    @property
    def size(self):
        """ Store size """

        return self.prop(PR_MESSAGE_SIZE_EXTENDED).value

    def config_item(self, name):
        item = Item()
        item.mapiobj = libcommon.GetConfigMessage(self.mapiobj, 'Zarafa.Quota')
        return item

    @property
    def last_logon(self):
        """ Return :datetime Last logon of a user on this store """

        return self.prop(PR_LAST_LOGON_TIME).value or None

    @property
    def last_logoff(self):
        """ Return :datetime of the last logoff of a user on this store """

        return self.prop(PR_LAST_LOGOFF_TIME).value or None

    @property
    def outofoffice(self):
        """ Return :class:`Outofoffice` """

        # FIXME: If store is public store, return None?
        return Outofoffice(self)

    def prop(self, proptag):
        return _prop(self, self.mapiobj, proptag)

    def props(self):
        return _props(self.mapiobj)

    def __unicode__(self):
        return u"Store('%s')" % self.guid

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Folder(object):
    """
    Item Folder

    """

    def __init__(self, store, entryid=None, associated=False, mapiobj=None): # XXX entryid not hex-encoded!?
        self.store = store
        self.server = store.server
        if mapiobj:
            self.mapiobj = mapiobj
            self._entryid = HrGetOneProp(self.mapiobj, PR_ENTRYID).Value
        else:
            self._entryid = entryid
            try:
                self.mapiobj = store.mapiobj.OpenEntry(entryid, IID_IMAPIFolder, MAPI_MODIFY)
            except MAPIErrorNoAccess: # XXX XXX
                self.mapiobj = store.mapiobj.OpenEntry(entryid, IID_IMAPIFolder, 0)
        self.content_flag = MAPI_ASSOCIATED if associated else 0

    @property
    def entryid(self):
        """ Folder entryid """

        return bin2hex(self._entryid)

    @property
    def sourcekey(self):
        return bin2hex(HrGetOneProp(self.mapiobj, PR_SOURCE_KEY).Value)

    @property
    def parent(self):
        """Return :class:`parent <Folder>` or None"""
        # PR_PARENT_ENTRYID for the message store root folder is its own PR_ENTRYID
        try:
            return Folder(self.store, self.prop(PR_PARENT_ENTRYID).value)
        except MAPIErrorNotFound: # XXX: Should not happen
            return None

    @property
    def hierarchyid(self):
        return self.prop(PR_EC_HIERARCHYID).value

    @property
    def folderid(self): # XXX remove?
        return self.hierarchyid

    @property
    def subfolder_count(self):
        ''' Number of direct subfolders '''

        return self.prop(PR_FOLDER_CHILD_COUNT).value

    @property
    def name(self):
        """ Folder name """

        try:
            return self.prop(PR_DISPLAY_NAME_W).value
        except MAPIErrorNotFound:
            if self.entryid == self.store.root.entryid: # Root folder's PR_DISPLAY_NAME_W is never set
                return u'ROOT'
            else:
                return u''

    @name.setter
    def name(self, name):
        self.mapiobj.SetProps([SPropValue(PR_DISPLAY_NAME_W, unicode(name))])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def container_class(self):
        '''
        Property which describes the type of items a folder holds, possible values
        * IPF.Appointment
        * IPF.Contact
        * IPF.Journal
        * IPF.Note
        * IPF.StickyNote
        * IPF.Task

        https://msdn.microsoft.com/en-us/library/aa125193(v=exchg.65).aspx
        '''

        return self.prop(PR_CONTAINER_CLASS).value

    @container_class.setter
    def container_class(self, value):
        self.mapiobj.SetProps([SPropValue(PR_CONTAINER_CLASS, unicode(value))])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def item(self, entryid):
        """ Return :class:`Item` with given entryid; raise exception of not found """ # XXX better exception?

        item = Item() # XXX copy-pasting..
        item.store = self.store
        item.server = self.server
        item.mapiobj = _openentry_raw(self.store.mapiobj, entryid.decode('hex'), MAPI_MODIFY)
        return item

    def items(self):
        """ Return all :class:`items <Item>` in folder, reverse sorted on received date """

        try:
            table = self.mapiobj.GetContentsTable(self.content_flag)
        except MAPIErrorNoSupport:
            return

        table.SortTable(SSortOrderSet([SSort(PR_MESSAGE_DELIVERY_TIME, TABLE_SORT_DESCEND)], 0, 0), 0) # XXX configure
        while True:
            rows = table.QueryRows(50, 0)
            if len(rows) == 0:
                break
            for row in rows:
                item = Item()
                item.store = self.store
                item.server = self.server
                item.mapiobj = _openentry_raw(self.store.mapiobj, PpropFindProp(row, PR_ENTRYID).Value, MAPI_MODIFY)
                yield item

    def create_item(self, eml=None, ics=None, vcf=None, load=None, loads=None, **kwargs): # XXX associated
        item = Item(self, eml=eml, ics=ics, vcf=vcf, load=load, loads=loads, create=True)
        item.server = self.server
        for key, val in kwargs.items():
            setattr(item, key, val)
        return item

    # XXX: always hard delete or but we should also provide 'softdelete' which moves the item to the wastebasket
    def empty(self, recurse=True, associated=False):
        """ Delete folder contents

        :param recurse: delete subfolders
        :param associated: delete associated contents
        """

        if recurse:
            flags = DELETE_HARD_DELETE
            if associated:
                flags |= DEL_ASSOCIATED
            self.mapiobj.EmptyFolder(0, None, flags)
        else:
            self.delete(self.items()) # XXX look at associated flag! probably also quite slow

    @property
    def size(self): # XXX bit slow perhaps? :P
        """ Folder size """

        try:
            table = self.mapiobj.GetContentsTable(self.content_flag)
        except MAPIErrorNoSupport:
            return 0

        table.SetColumns([PR_MESSAGE_SIZE], 0)
        table.SeekRow(BOOKMARK_BEGINNING, 0)
        rows = table.QueryRows(-1, 0)
        size = 0
        for row in rows:
            size += row[0].Value
        return size

    @property
    def count(self, recurse=False): # XXX implement recurse?
        """ Number of items in folder

        :param recurse: include items in sub-folders

        """

        try:
            return self.mapiobj.GetContentsTable(self.content_flag).GetRowCount(0) # XXX PR_CONTENT_COUNT, PR_ASSOCIATED_CONTENT_COUNT
        except MAPIErrorNoSupport:
            return 0


    def _get_entryids(self, items):
        if isinstance(items, (Item, Folder)):
            items = [items]
        else:
            items = list(items)
        item_entryids = [item.entryid.decode('hex') for item in items if isinstance(item, Item)]
        folder_entryids = [item.entryid.decode('hex') for item in items if isinstance(item, Folder)]
        return item_entryids, folder_entryids

    def delete(self, items): # XXX associated
        item_entryids, folder_entryids = self._get_entryids(items)
        if item_entryids:
            self.mapiobj.DeleteMessages(item_entryids, 0, None, DELETE_HARD_DELETE)
        for entryid in folder_entryids:
            self.mapiobj.DeleteFolder(entryid, 0, None, DEL_FOLDERS|DEL_MESSAGES)

    def copy(self, items, folder, _delete=False):
        item_entryids, folder_entryids = self._get_entryids(items)
        if item_entryids:
            self.mapiobj.CopyMessages(item_entryids, IID_IMAPIFolder, folder.mapiobj, 0, None, (MESSAGE_MOVE if _delete else 0))
        for entryid in folder_entryids:
            self.mapiobj.CopyFolder(entryid, IID_IMAPIFolder, folder.mapiobj, None, 0, None, (FOLDER_MOVE if _delete else 0))

    def move(self, items, folder):
        self.copy(items, folder, _delete=True)

    # XXX: almost equal to Store.folder, refactor?
    def folder(self, key, recurse=True, create=False): # XXX sloowowowww, see also Store.folder
        """ Return :class:`Folder` with given name or entryid; raise exception if not found

            :param key: name or entryid
        """

        if len(key) == 96:
            try:
                folder = Folder(self, key.decode('hex')) # XXX: What about creat=True, do we want to check if it is a valid entryid and then create the folder?
                return folder
            except (MAPIErrorInvalidEntryid, MAPIErrorNotFound, TypeError):
                pass
        matches = [f for f in self.folders(recurse=recurse) if f.entryid == key or f.name == key]
        if len(matches) == 0:
            if create:
                return self.create_folder(key) # XXX assuming no entryid..
            else:
                raise ZarafaNotFoundException("no such folder: '%s'" % key)
        elif len(matches) > 1:
            raise ZarafaNotFoundException("multiple folders with name/entryid '%s'" % key)
        else:
            return matches[0]

    def get_folder(self, key):
        """ Return :class:`folder <Folder>` with given name/entryid or *None* if not found """

        try:
            return self.folder(key)
        except ZarafaException:
            pass

    def folders(self, recurse=True, depth=0):
        """ Return all :class:`sub-folders <Folder>` in folder

        :param recurse: include all sub-folders
        """

        if self.mapiobj.GetProps([PR_SUBFOLDERS], MAPI_UNICODE)[0].Value: # XXX no worky?
            try:
                table = self.mapiobj.GetHierarchyTable(MAPI_UNICODE)
            except MAPIErrorNoSupport: # XXX webapp search folder?
                return

            table.SetColumns([PR_ENTRYID], 0)
            rows = table.QueryRows(-1, 0)
            for row in rows:
                subfolder = self.mapiobj.OpenEntry(row[0].Value, None, MAPI_MODIFY)
                entryid = subfolder.GetProps([PR_ENTRYID], MAPI_UNICODE)[0].Value
                folder = Folder(self.store, entryid)
                folder.depth = depth
                yield folder
                if recurse:
                    for subfolder in folder.folders(depth=depth+1):
                        yield subfolder

    def create_folder(self, name, **kwargs):
        mapifolder = self.mapiobj.CreateFolder(FOLDER_GENERIC, unicode(name), u'', None, MAPI_UNICODE)
        folder = Folder(self.store, HrGetOneProp(mapifolder, PR_ENTRYID).Value)
        for key, val in kwargs.items():
            setattr(folder, key, val)
        return folder

    def rules(self):
        rule_table = self.mapiobj.OpenProperty(PR_RULES_TABLE, IID_IExchangeModifyTable, 0, 0)
        table = Table(self.server, rule_table.GetTable(0), PR_RULES_TABLE)
        for row in table.dict_rows():
            yield Rule(row[PR_RULE_NAME], row[PR_RULE_STATE]) # XXX fix args

    def prop(self, proptag):
        return _prop(self, self.mapiobj, proptag)

    def props(self):
        return _props(self.mapiobj)

    def table(self, name, restriction=None, order=None, columns=None): # XXX associated, PR_CONTAINER_CONTENTS?
        return Table(self.server, self.mapiobj.OpenProperty(name, IID_IMAPITable, MAPI_UNICODE, 0), name, restriction=restriction, order=order, columns=columns)

    def tables(self): # XXX associated, rules
        yield self.table(PR_CONTAINER_CONTENTS)
        yield self.table(PR_FOLDER_ASSOCIATED_CONTENTS)
        yield self.table(PR_CONTAINER_HIERARCHY)

    @property
    def state(self):
        """ Current folder state """

        return _state(self.mapiobj, self.content_flag == MAPI_ASSOCIATED)

    def sync(self, importer, state=None, log=None, max_changes=None, associated=False):
        """ Perform synchronization against folder

        :param importer: importer instance with callbacks to process changes
        :param state: start from this state; if not given sync from scratch
        :log: logger instance to receive important warnings/errors
        """

        if state is None:
            state = (8*'\0').encode('hex').upper()
        importer.store = self.store
        return _sync(self.store.server, self.mapiobj, importer, state, log, max_changes, associated)

    def readmbox(self, location):
        for message in mailbox.mbox(location):
            newitem = Item(self, eml=message.__str__(), create=True)

    def mbox(self, location): # FIXME: inconsistent with maildir()
        mboxfile = mailbox.mbox(location)
        mboxfile.lock()
        for item in self.items():
            mboxfile.add(item.eml())
        mboxfile.unlock()

    def maildir(self, location='.'):
        destination = mailbox.MH(location + '/' + self.name)
        destination.lock()
        for item in self.items():
            destination.add(item.eml())
        destination.unlock()

    def read_maildir(self, location):
        for message in mailbox.MH(location):
            newitem = Item(self, eml=message.__str__(), create=True)

    @property
    def associated(self):
        """ Associated folder containing hidden items """

        return Folder(self.store, self._entryid, associated=True)

    def __iter__(self):
        return self.items()

    def __unicode__(self): # XXX associated?
        return u'Folder(%s)' % self.name

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Item(object):
    """ Item """

    def __init__(self, parent=None, eml=None, ics=None, vcf=None, load=None, loads=None, create=False, mapiobj=None):
        # TODO: self.folder fix this!
        self.emlfile = eml
        if isinstance(parent, Folder): 
            self._folder = parent
        # XXX
        self._architem = None

        if mapiobj:
            self.mapiobj = mapiobj
            if isinstance(parent, Store): 
                self.server = parent.server
            # XXX
            
        elif create:
            self.mapiobj = self.folder.mapiobj.CreateMessage(None, 0)
            self.server = server = self.folder.store.server # XXX

            if eml is not None:
                # options for CreateMessage: 0 / MAPI_ASSOCIATED
                dopt = inetmapi.delivery_options()
                inetmapi.IMToMAPI(server.mapisession, self.folder.store.mapiobj, None, self.mapiobj, self.emlfile, dopt)

            elif ics is not None:
                icm = icalmapi.CreateICalToMapi(self.mapiobj, server.ab, False)
                icm.ParseICal(ics, 'utf-8', '', None, 0)
                icm.GetItem(0, 0, self.mapiobj)

            elif vcf is not None:
                import vobject
                v = vobject.readOne(vcf)
                fullname, email = v.fn.value, str(v.email.value)
                self.mapiobj.SetProps([ # XXX fix/remove non-essential props, figure out hardcoded numbers
                    SPropValue(PR_ADDRTYPE, 'SMTP'), SPropValue(PR_BODY, ''),
                    SPropValue(PR_LOCALITY, ''), SPropValue(PR_STATE_OR_PROVINCE, ''),
                    SPropValue(PR_BUSINESS_FAX_NUMBER, ''), SPropValue(PR_COMPANY_NAME, ''),
                    SPropValue(0x8130001E, fullname), SPropValue(0x8132001E, 'SMTP'),
                    SPropValue(0x8133001E, email), SPropValue(0x8134001E, ''),
                    SPropValue(0x81350102, server.ab.CreateOneOff('', 'SMTP', email, 0)), # XXX
                    SPropValue(PR_GIVEN_NAME, ''), SPropValue(PR_MIDDLE_NAME, ''),
                    SPropValue(PR_NORMALIZED_SUBJECT, ''), SPropValue(PR_TITLE, ''),
                    SPropValue(PR_TRANSMITABLE_DISPLAY_NAME, ''),
                    SPropValue(PR_DISPLAY_NAME_W, fullname),
                    SPropValue(0x80D81003, [0]), SPropValue(0x80D90003, 1), 
                    SPropValue(PR_MESSAGE_CLASS, 'IPM.Contact'),
                ])

            elif load is not None:
                self.load(load)
            elif loads is not None:
                self.loads(loads)

            else:
                try:
                    container_class = HrGetOneProp(self.folder.mapiobj, PR_CONTAINER_CLASS).Value
                except MAPIErrorNotFound:
                    self.mapiobj.SetProps([SPropValue(PR_MESSAGE_CLASS, 'IPM.Note')])
                else:
                    if container_class == 'IPF.Contact': # XXX just skip first 4 chars? 
                        self.mapiobj.SetProps([SPropValue(PR_MESSAGE_CLASS, 'IPM.Contact')]) # XXX set default props
                    elif container_class == 'IPF.Appointment':
                        self.mapiobj.SetProps([SPropValue(PR_MESSAGE_CLASS, 'IPM.Appointment')]) # XXX set default props

            self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def _arch_item(self): # make an explicit connection to archive server so we can handle otherwise silenced errors (MAPI errors in mail bodies for example)
        if self._architem is None:
            if self.stubbed:
                ids = self.mapiobj.GetIDsFromNames(NAMED_PROPS_ARCHIVER, 0)
                PROP_STORE_ENTRYIDS = CHANGE_PROP_TYPE(ids[0], PT_MV_BINARY)
                try:
                    # support for multiple archives was a mistake, and is not and _should not_ be used. so we just pick nr 0.
                    arch_storeid = HrGetOneProp(self.mapiobj, PROP_STORE_ENTRYIDS).Value[0]
                    arch_server = arch_storeid[arch_storeid.find('pseudo://')+9:-1]
                    arch_session = self.server._archive_session(arch_server)
                    if arch_session is None: # XXX first connection failed, no need to report about this multiple times
                        self._architem = self.mapiobj
                    else:
                        PROP_ITEM_ENTRYIDS = CHANGE_PROP_TYPE(ids[1], PT_MV_BINARY)
                        item_entryid = HrGetOneProp(self.mapiobj, PROP_ITEM_ENTRYIDS).Value[0]
                        arch_store = arch_session.OpenMsgStore(0, arch_storeid, None, 0)
                        self._architem = arch_store.OpenEntry(item_entryid, None, 0)
                except MAPIErrorNotFound: # XXX fix 'stubbed' definition!!
                    self._architem = self.mapiobj
            else:
                self._architem = self.mapiobj
        return self._architem

    @property
    def entryid(self):
        """ Item entryid """

        return bin2hex(HrGetOneProp(self.mapiobj, PR_ENTRYID).Value)

    @property
    def hierarchyid(self):
        return HrGetOneProp(self.mapiobj, PR_EC_HIERARCHYID).Value

    @property
    def sourcekey(self):
        """ Item sourcekey """

        if not hasattr(self, '_sourcekey'): # XXX more general caching solution
            self._sourcekey = bin2hex(HrGetOneProp(self.mapiobj, PR_SOURCE_KEY).Value)
        return self._sourcekey

    @property
    def subject(self):
        """ Item subject or *None* if no subject """

        try:
            return self.prop(PR_SUBJECT_W).value
        except MAPIErrorNotFound:
            return u''

    @subject.setter
    def subject(self, x):
        self.mapiobj.SetProps([SPropValue(PR_SUBJECT_W, unicode(x))])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def body(self):
        """ Item :class:`body <Body>` """

        return Body(self) # XXX return None if no body..?

    @property
    def size(self):
        """ Item size """

        return self.prop(PR_MESSAGE_SIZE).value

    @property
    def message_class(self):
        return self.prop(PR_MESSAGE_CLASS).value

    @message_class.setter
    def message_class(self, messageclass):
        # FIXME: Add all possible PR_MESSAGE_CLASS values
        '''
        MAPI Message classes:
        * IPM.Note.SMIME.MultipartSigned - smime signed email
        * IMP.Note                       - normal email
        * IPM.Note.SMIME                 - smime encypted email
        * IPM.StickyNote                 - note
        * IPM.Appointment                - appointment
        * IPM.Task                       - task
        '''
        self.mapiobj.SetProps([SPropValue(PR_MESSAGE_CLASS, unicode(messageclass))])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @body.setter
    def body(self, x):
        self.mapiobj.SetProps([SPropValue(PR_BODY_W, unicode(x))])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def received(self):
        """ Datetime instance with item delivery time """

        try:
            return self.prop(PR_MESSAGE_DELIVERY_TIME).value
        except MAPIErrorNotFound:
            pass

    @property
    def last_modified(self):
        try:
            return self.prop(PR_LAST_MODIFICATION_TIME).value
        except MAPIErrorNotFound:
            pass

    @property
    def stubbed(self):
        """ Is item stubbed by archiver? """

        ids = self.mapiobj.GetIDsFromNames(NAMED_PROPS_ARCHIVER, 0) # XXX cache folder.GetIDs..?
        PROP_STUBBED = CHANGE_PROP_TYPE(ids[2], PT_BOOLEAN)
        try:
            return HrGetOneProp(self.mapiobj, PROP_STUBBED).Value # False means destubbed
        except MAPIErrorNotFound:
            return False

    @property
    def read(self):
        """ Return boolean which shows if a message has been read """

        return self.prop(PR_MESSAGE_FLAGS).value & MSGFLAG_READ > 0

    @read.setter
    def read(self, value):
        if value:
            self.mapiobj.SetReadFlag(0)
        else:
            self.mapiobj.SetReadFlag(CLEAR_READ_FLAG)

    @property
    def folder(self):
        """ Parent :class:`Folder` of an item """

        if self._folder:
            return self._folder
        try:
            return Folder(self.store, HrGetOneProp(self.mapiobj, PR_PARENT_ENTRYID).Value)
        except MAPIErrorNotFound:
            pass

    @property
    def importance(self):
        """ Importance """

        # TODO: userfriendly repr of value
        try:
            return self.prop(PR_IMPORTANCE).value
        except MAPIErrorNotFound:
            pass

    @importance.setter
    def importance(self, value):
        ''' Set importance '''

        '''
        PR_IMPORTANCE_LOW
        PR_IMPORTANCE_MEDIUM
        PR_IMPORTANCE_HIGH
        '''

        self.mapiobj.SetProps([SPropValue(PR_IMPORTANCE, value)])
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def prop(self, proptag):
        return _prop(self, self.mapiobj, proptag)

    def props(self, namespace=None):
        return _props(self.mapiobj, namespace)

    def attachments(self, embedded=False):
        """ Return item :class:`attachments <Attachment>`

        :param embedded: include embedded attachments
        """

        mapiitem = self._arch_item
        table = mapiitem.GetAttachmentTable(MAPI_DEFERRED_ERRORS)
        table.SetColumns([PR_ATTACH_NUM, PR_ATTACH_METHOD], TBL_BATCH)
        attachments = []
        while True:
            rows = table.QueryRows(50, 0)
            if len(rows) == 0:
                break
            for row in rows:
                if row[1].Value == ATTACH_BY_VALUE or (embedded and row[1].Value == ATTACH_EMBEDDED_MSG):
                    att = mapiitem.OpenAttach(row[0].Value, IID_IAttachment, 0)
                    attachments.append(Attachment(att))
        return attachments

    def header(self, name):
        """ Return transport message header with given name """

        return self.headers().get(name)

    def headers(self):
        """ Return transport message headers """

        try:
            message_headers = self.prop(PR_TRANSPORT_MESSAGE_HEADERS)
            headers = Parser().parsestr(message_headers.value, headersonly=True)
            return headers
        except MAPIErrorNotFound:
            return {}

    def eml(self):
        """ Return .eml version of item """

        if self.emlfile is None:
            try:
                self.emlfile = _stream(self.mapiobj, PR_EC_IMAP_EMAIL)
            except MAPIErrorNotFound:
                sopt = inetmapi.sending_options()
                sopt.no_recipients_workaround = True
                self.emlfile = inetmapi.IMToINet(self.store.server.mapisession, None, self.mapiobj, sopt)
        return self.emlfile

    def vcf(self): # XXX don't we have this builtin somewhere? very basic for now
        import vobject
        v = vobject.vCard()
        v.add('n')
        v.n.value = vobject.vcard.Name(family='', given='') # XXX
        v.add('fn')
        v.fn.value = ''
        v.add('email')
        v.email.value = ''
        v.email.type_param = 'INTERNET'
        try:
            v.fn.value = HrGetOneProp(self.mapiobj, 0x8130001E).Value
        except MAPIErrorNotFound:
            pass
        try:
            v.email.value = HrGetOneProp(self.mapiobj, 0x8133001E).Value
        except MAPIErrorNotFound:
            pass
        return v.serialize()

    # XXX def ics for ical export?

    def send(self):
        props = []
        props.append(SPropValue(PR_SENTMAIL_ENTRYID, self.folder.store.sentmail.entryid.decode('hex')))
        props.append(SPropValue(PR_DELETE_AFTER_SUBMIT, True))
        self.mapiobj.SetProps(props)
        self.mapiobj.SubmitMessage(0)

    @property
    def sender(self):
        """ Sender :class:`Address` """

        return Address(self.server, *(self.prop(p).value for p in (PR_SENT_REPRESENTING_ADDRTYPE_W, PR_SENT_REPRESENTING_NAME_W, PR_SENT_REPRESENTING_EMAIL_ADDRESS_W, PR_SENT_REPRESENTING_ENTRYID)))

    def table(self, name, restriction=None, order=None, columns=None):
        return Table(self.server, self.mapiobj.OpenProperty(name, IID_IMAPITable, MAPI_UNICODE, 0), name, restriction=restriction, order=order, columns=columns)

    def tables(self):
        yield self.table(PR_MESSAGE_RECIPIENTS)
        yield self.table(PR_MESSAGE_ATTACHMENTS)

    def recipients(self):
        """ Return recipient :class:`addresses <Address>` """

        result = []
        for row in self.table(PR_MESSAGE_RECIPIENTS):
            row = dict([(x.proptag, x) for x in row])
            result.append(Address(self.server, *(row[p].value for p in (PR_ADDRTYPE_W, PR_DISPLAY_NAME_W, PR_EMAIL_ADDRESS_W, PR_ENTRYID))))
        return result

    @property
    def to(self):
        return self.recipients() # XXX filter

    @property 
    def start(self): # XXX optimize, guid
        return self.prop('common:34070').value

    @property 
    def end(self): # XXX optimize, guid
        return self.prop('common:34071').value

    @property
    def recurring(self):
        return item.prop('appointment:33315').value

    @property
    def recurrence(self):
        return Recurrence(self)

    @to.setter
    def to(self, addrs):
        if isinstance(addrs, (str, unicode)):
            addrs2 = []
            for addr in unicode(addrs).split(';'): # XXX use python email module here?
                if '<' in addr:
                    name = addr[:addr.find('<')].strip()
                    email = addr[addr.find('<')+1:addr.find('>')].strip()
                    addrs2.append(Address(name=name, email=email))
                else:
                    addrs2.append(Address(email=addr.strip()))
        names = []
        for addr in addrs2:
            names.append([
                SPropValue(PR_RECIPIENT_TYPE, MAPI_TO), 
                SPropValue(PR_DISPLAY_NAME_W, addr.name or u'nobody'), 
                SPropValue(PR_ADDRTYPE, 'SMTP'), 
                SPropValue(PR_EMAIL_ADDRESS, unicode(addr.email)),
                SPropValue(PR_ENTRYID, self.server.ab.CreateOneOff(addr.name or u'nobody', u'SMTP', unicode(addr.email), MAPI_UNICODE)),
            ])
        self.mapiobj.ModifyRecipients(0, names)
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE) # XXX needed?

    def delete(self, items):
        # XXX attachments
        if isinstance(items, Property):
            proptags = [items.proptag]
        else:
            proptags = [item.proptag for item in items]
        if proptags:
            self.mapiobj.DeleteProps(proptags)
            self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def _convert_to_smtp(self, props, tag_data):
        if not hasattr(self.server, '_smtp_cache'): # XXX gross speed hack for now
            smtp_cache = {}
            for row in self.server.gab_table().dict_rows():
                entryid, smtp = row.get(PR_ENTRYID), row.get(PR_SMTP_ADDRESS)
                if entryid and smtp:
                    smtp_cache[entryid] = unicode(smtp) # XXX unicode
            self.server._smtp_cache = smtp_cache
        for addrtype, email, entryid, name, searchkey in ADDR_PROPS:
            if addrtype not in tag_data or entryid not in tag_data or name not in tag_data: 
                continue
            if tag_data[addrtype][1] in (u'SMTP', u'MAPIDPL'): # XXX MAPIDPL==distlist.. can we just dump this?
                continue
            email_addr = self.server._smtp_cache.get(tag_data[entryid][1])
            if not email_addr: # XXX deleted user, or no email address? or user with multiple entryids..heh?
                continue
            tag_data[addrtype][1] = u'SMTP'
            if email in tag_data:
                tag_data[email][1] = email_addr
            else:
                props.append([email, email_addr, None])
            tag_data[entryid][1] = self.server.ab.CreateOneOff(tag_data[name][1], u'SMTP', email_addr, MAPI_UNICODE)
            key = 'SMTP:'+str(email_addr).upper()
            if searchkey in tag_data: # XXX probably need to create, also email
                tag_data[searchkey][1] = key
            else:
                props.append([searchkey, key, None])

    def _dump(self):
        # props
        props = []
        tag_data = {}
        bestbody = _bestbody(self.mapiobj)
        for prop in self.props():
            if (bestbody != PR_NULL and prop.proptag in (PR_BODY_W, PR_HTML, PR_RTF_COMPRESSED) and prop.proptag != bestbody):
                continue
            if prop.id_ >= 0x8000: # named prop: prop.id_ system dependant..
                data = [prop.proptag, prop.mapiobj.Value, self.mapiobj.GetNamesFromIDs([prop.proptag], None, 0)[0]]
            else:
                data = [prop.proptag, prop.mapiobj.Value, None]
            props.append(data)
            tag_data[prop.proptag] = data
        self._convert_to_smtp(props, tag_data)

        # recipients
        recipients = []
        for row in self.table(PR_MESSAGE_RECIPIENTS):
            rprops = []
            tag_data = {}
            for prop in row:
                data = [prop.proptag, prop.mapiobj.Value, None]
                rprops.append(data)
                tag_data[prop.proptag] = data
            recipients.append(rprops)
            self._convert_to_smtp(rprops, tag_data)

        # attachments
        attachments = []
        # XXX optimize by looking at PR_MESSAGE_FLAGS?
        for row in self.table(PR_MESSAGE_ATTACHMENTS).dict_rows(): # XXX should we use GetAttachmentTable?
            num = row[PR_ATTACH_NUM]
            method = row[PR_ATTACH_METHOD] # XXX default
            att = self.mapiobj.OpenAttach(num, IID_IAttachment, 0)
            if method == ATTACH_EMBEDDED_MSG:
                msg = att.OpenProperty(PR_ATTACH_DATA_OBJ, IID_IMessage, 0, MAPI_MODIFY | MAPI_DEFERRED_ERRORS)
                item = Item(mapiobj=msg)
                item.server = self.server # XXX
                data = item._dump() # recursion
            else:
                data = _stream(att, PR_ATTACH_DATA_BIN)
            attachments.append(([[a, b, None] for a, b in row.items()], data))

        return {
            'props': props,
            'recipients': recipients,
            'attachments': attachments,
        }

    def dump(self, f):
        pickle.dump(self._dump(), f, pickle.HIGHEST_PROTOCOL)

    def dumps(self):
        return pickle.dumps(self._dump(), pickle.HIGHEST_PROTOCOL)

    def _load(self, d):
        # props
        props = []
        for proptag, value, nameid in d['props']:
            if nameid is not None:
                proptag = self.mapiobj.GetIDsFromNames([nameid], MAPI_CREATE)[0] | (proptag & 0xffff)
            props.append(SPropValue(proptag, value))
        self.mapiobj.SetProps(props)

        # recipients
        recipients = [[SPropValue(proptag, value) for (proptag, value, nameid) in row] for row in d['recipients']]
        self.mapiobj.ModifyRecipients(0, recipients)

        # attachments
        for props, data in d['attachments']:
            props = [SPropValue(proptag, value) for (proptag, value, nameid) in props]
            (id_, attach) = self.mapiobj.CreateAttach(None, 0)
            attach.SetProps(props)
            if isinstance(data, dict):
                msg = attach.OpenProperty(PR_ATTACH_DATA_OBJ, IID_IMessage, 0, MAPI_CREATE | MAPI_MODIFY)
                item = Item(mapiobj=msg)
                item._load(data) # recursion
            else:
                stream = attach.OpenProperty(PR_ATTACH_DATA_BIN, IID_IStream, STGM_WRITE|STGM_TRANSACTED, MAPI_MODIFY | MAPI_CREATE)
                stream.Write(data)
                stream.Commit(0)
            attach.SaveChanges(KEEP_OPEN_READWRITE)
        self.mapiobj.SaveChanges(KEEP_OPEN_READWRITE) # XXX needed?

    def load(self, f):
        self._load(pickle.load(f))

    def loads(self, s):
        self._load(pickle.loads(s))

    def __unicode__(self):
        return u'Item(%s)' % self.subject

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Body:
    """ Body """

    def __init__(self, mapiitem):
        self.mapiitem = mapiitem

    @property
    def text(self):
        """ Plaintext representation (possibly from archive server) """

        try:
            mapiitem = self.mapiitem._arch_item # XXX server already goes 'underwater'.. check details
            return _stream(mapiitem, PR_BODY_W) # under windows them be utf-16le?
        except MAPIErrorNotFound:
            return u''

    @property
    def html(self): # XXX decode using PR_INTERNET_CPID
        """ HTML representation (possibly from archive server), in original encoding """

        try:
            mapiitem = self.mapiitem._arch_item
            return _stream(mapiitem, PR_HTML)
        except MAPIErrorNotFound:
            return ''

    @property
    def type_(self):
        """ original body type: 'text', 'html', 'rtf' or None if it cannot be determined """
        tag = _bestbody(self.mapiitem.mapiobj)
        if tag == PR_BODY_W: 
            return 'text'
        elif tag == PR_HTML: 
            return 'html'
        elif tag == PR_RTF_COMPRESSED: 
            return 'rtf'

    def __unicode__(self):
        return u'Body()'

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Recurrence:
    def __init__(self, item): # XXX just readable start/end for now
        from dateutil.rrule import WEEKLY, DAILY, MONTHLY, MO, TU, TH, FR, WE, SA, SU, rrule, rruleset
        # TODO: add check if we actually have a recurrence, otherwise we throw a mapi exception which might not be desirable
        self.item = item
        value = item.prop('appointment:33302').value # recurrencestate
        SHORT, LONG = 2, 4
        pos = 5 * SHORT + 3 * LONG 

        self.recurrence_frequency = _unpack_short(value, 2 * SHORT)
        self.patterntype = _unpack_short(value, 3 * SHORT)
        self.calendar_type = _unpack_short(value, 4 * SHORT)
        self.first_datetime = _unpack_long(value, 5 * SHORT)
        self.period = _unpack_long(value , 5 * SHORT + LONG) # 12 for year, coincedence?

        if self.patterntype == 1: # Weekly recurrence
            self.pattern = _unpack_long(value, pos) # WeekDays
            pos += LONG
        if self.patterntype in (2, 4, 10, 12): # Monthly recurrence
            self.pattern = _unpack_long(value, pos) # Day Of Month
            pos += LONG
        elif self.patterntype in (3, 11): # Yearly recurrence
            weekday = _unpack_long(value, pos)
            pos += LONG 
            weeknumber = _unpack_long(value, pos)
            pos += LONG 

        self.endtype = _unpack_long(value, pos)
        pos += LONG
        self.occurrence_count = _unpack_long(value, pos)
        pos += LONG
        self.first_dow = _unpack_long(value, pos)
        pos += LONG

        # Number of ocurrences which have been removed in a recurrene
        self.delcount = _unpack_long(value, pos)
        pos += LONG
        # XXX: optimize?
        self.del_recurrences = []
        for _ in xrange(0, self.delcount):
            self.del_recurrences.append(datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos))))
            pos += LONG

        self.modcount = _unpack_long(value, pos)
        pos += LONG
        # XXX: optimize?
        self.mod_recurrences = []
        for _ in xrange(0, self.modcount):
            self.mod_recurrences.append(datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos))))
            pos += LONG

        self.start = datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos)))
        pos += LONG
        self.end = datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos)))

        pos += 3 * LONG # ulReaderVersion2, ulReaderWriter2
        self.startime_offset = _unpack_long(value, pos) # XXX: type?
        pos += LONG
        self.endtime_offset = _unpack_long(value, pos) # XXX: type?
        pos += LONG

        
        # Exceptions
        self.exception_count = _unpack_short(value, pos)
        pos += SHORT

        # FIXME: create class instances.
        self.exceptions = []
        for i in xrange(0, self.exception_count):
            exception = {}
            # Blegh helper..
            exception['startdatetime'] = datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos)))
            pos += LONG
            exception['enddatetime'] = datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos)))
            pos += LONG
            exception['originalstartdate'] = datetime.datetime.fromtimestamp(_rectime_to_unixtime(_unpack_long(value, pos)))
            pos += LONG
            exception['overrideflags'] = _unpack_short(value, pos)
            pos += SHORT

            # We have modified the subject
            if exception['overrideflags'] & ARO_SUBJECT:
                subject_length1 = _unpack_short(value, pos) # XXX: unused?
                pos += SHORT
                subject_length2 = _unpack_short(value, pos)
                pos += SHORT
                exception['subject'] = _unpack_string(value, pos, subject_length2)
                pos += subject_length2

            # XXX: Changed the meeting type too???
            if exception['overrideflags'] & ARO_MEETINGTYPE:
                exception['meetingtype'] = _unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_REMINDERDELTA:
                exception['reminderdelta'] = _unpack_long(value, pos) # XXX: datetime?
                pos += LONG

            if exception['overrideflags'] & ARO_REMINDERSET:
                exception['reminderset'] = _unpack_long(value, pos) # XXX: bool?
                pos += LONG

            if exception['overrideflags'] & ARO_LOCATION:
                localation_length1 = _unpack_short(value, pos) # XXX: unused?
                pos += SHORT
                location_length2 = _unpack_short(value, pos)
                pos += SHORT
                exception['location'] = _unpack_string(value, pos, location_length2)
                pos += location_length2

            if exception['overrideflags'] & ARO_BUSYSTATUS:
                exception['busystatus'] = _unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_ATTACHMENT:
                exception['attachment'] = _unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_SUBTYPE:
                exception['subtype'] = _unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_APPTCOLOR:
                exception['color'] = _unpack_long(value, pos)
                pos += LONG

            self.exceptions.append(exception)


        # FIXME: move to class Item?
        self.clipend = item.prop('appointment:33334').value
        self.clipstart = item.prop('appointment:33333').value 
        self.recurrence_pattern = item.prop('appointment:33330').value
        self.invited = item.prop('appointment:33321').value


        # FIXME; doesn't dateutil have a list of this?
        rrule_weekdays = {0: SU, 1: MO, 2: TU, 3: WE, 4: TH, 5: FR, 6: SA} # FIXME: remove above

        # FIXME: add DAILY, patterntype == 0
        # FIXME: merge exception details with normal appointment data to recurrence.occurences() (Class occurence)
        if self.patterntype == 1: # WEEKLY
            byweekday = () # Set
            for index, week in rrule_weekdays.iteritems():
                if (self.pattern >> index ) & 1:
                    byweekday += (week,)
            # Setup our rule
            rule = rruleset()
            rule.rrule(rrule(WEEKLY, dtstart=self.start, until=self.end, byweekday=byweekday))

            # Remove deleted ocurrences
            for del_date in self.del_recurrences:
                # XXX: Somehow rule.rdate does not work in combination with rule.exdate
                if not del_date in self.mod_recurrences:
                    rule.exdate(del_date)

            self.recurrences = rule
            #self.recurrences = rrule(WEEKLY, dtstart=self.start, until=self.end, byweekday=byweekday)
        elif self.patterntype == 2: # MONTHLY
            # X Day of every Y month(s)
            # The Xnd Y (day) of every Z Month(s)
            self.recurrences = rrule(MONTHLY, dtstart=self.start, until=self.end, bymonthday=self.pattern, interval=self.period)
            # self.pattern is either day of month or 
        elif self.patterntype == 3: # MONTHY, YEARLY
            # Yearly, the last XX of YY
            self.recurrences = rrule(MONTHLY, dtstart=self.start, until=self.end, interval=self.period)

    def __unicode__(self):
        return u'Recurrence(start=%s - end=%s)' % (self.start, self.end)

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')


class Outofoffice(object):
    """
    Outofoffice class

    Class which contains a :class:`store <Store>` out of office properties and
    can set out-of-office status, message and subject.

    :param store: :class:`store <Store>`
    """
    def __init__(self, store):
        self.store = store

    @property
    def enabled(self):
        """ Out of office enabled status """

        try:
            return self.store.prop(PR_EC_OUTOFOFFICE).value
        except MAPIErrorNotFound:
            return False

    @enabled.setter
    def enabled(self, value):
        self.store.mapiobj.SetProps([SPropValue(PR_EC_OUTOFOFFICE, value)])
        self.store.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def subject(self):
        """ Subject """

        try:
            return self.store.prop(PR_EC_OUTOFOFFICE_SUBJECT).value
        except MAPIErrorNotFound:
            return u''

    @subject.setter
    def subject(self, value):
        self.store.mapiobj.SetProps([SPropValue(PR_EC_OUTOFOFFICE_SUBJECT, value)])
        self.store.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def message(self):
        """ Message """

        try:
            return self.store.prop(PR_EC_OUTOFOFFICE_MSG).value
        except MAPIErrorNotFound:
            return u''

    @message.setter
    def message(self, value):
        self.store.mapiobj.SetProps([SPropValue(PR_EC_OUTOFOFFICE_MSG, value)])
        self.store.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def start(self):
        """ Out-of-office is activated from the particular datetime onwards """
        try:
            return self.store.prop(PR_EC_OUTOFOFFICE_FROM).value
        except MAPIErrorNotFound:
            return None

    @start.setter
    def start(self, value):
        if value is None:
            self.store.mapiobj.DeleteProps([PR_EC_OUTOFOFFICE_FROM])
        else:
            value = MAPI.Time.unixtime(time.mktime(value.timetuple()))
            self.store.mapiobj.SetProps([SPropValue(PR_EC_OUTOFOFFICE_FROM, value)])
        self.store.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    @property
    def end(self):
        """ Out-of-office is activated until the particular datetime """
        try:
            return self.store.prop(PR_EC_OUTOFOFFICE_UNTIL).value
        except MAPIErrorNotFound:
            return None

    @end.setter
    def end(self, value):
        if value is None:
            self.store.mapiobj.DeleteProps([PR_EC_OUTOFOFFICE_UNTIL])
        else:
            value = MAPI.Time.unixtime(time.mktime(value.timetuple()))
            self.store.mapiobj.SetProps([SPropValue(PR_EC_OUTOFOFFICE_UNTIL, value)])
        self.store.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def __unicode__(self):
        return u'Outofoffice(%s)' % self.subject

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

    def update(self, **kwargs):
        """ Update function for outofoffice """

        for key, val in kwargs.items():
            setattr(self, key, val)

class Address:
    """ Address """

    def __init__(self, server=None, addrtype=None, name=None, email=None, entryid=None):
        self.server = server
        self.addrtype = addrtype
        self._name = name
        self._email = email
        self.entryid = entryid

    @property
    def name(self):
        """ Full name """

        return self._name

    @property
    def email(self):
        """ Email address """

        if self.addrtype == 'ZARAFA':
            try:
                mailuser = self.server.mapisession.OpenEntry(self.entryid, None, 0)
                return self.server.user(HrGetOneProp(mailuser, PR_ACCOUNT).Value).email # XXX PR_SMTP_ADDRESS_W from mailuser?
            except (ZarafaException, MAPIErrorNotFound): # XXX deleted user
                return None # XXX 'Support Delft'??
        else:
            return self._email

    def __unicode__(self):
        return u'Address(%s)' % (self._name or self.email)

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Attachment(object):
    """ Attachment """

    def __init__(self, att):
        self.att = att
        self._data = None

    @property
    def number(self):
        try:
            return HrGetOneProp(self.att, PR_ATTACH_NUM).Value
        except MAPIErrorNotFound:
            return 0

    @property
    def mimetype(self):
        """ Mime-type or *None* if not found """

        try:
            return HrGetOneProp(self.att, PR_ATTACH_MIME_TAG).Value
        except MAPIErrorNotFound:
            pass

    @property
    def filename(self):
        """ Filename or *None* if not found """

        try:
            return HrGetOneProp(self.att, PR_ATTACH_LONG_FILENAME_W).Value
        except MAPIErrorNotFound:
            pass

    def __len__(self):
        """ Size """

        try:
            return int(HrGetOneProp(self.att, PR_ATTACH_SIZE).Value) # XXX why is this not equal to len(data)??
        except MAPIErrorNotFound:
            pass

    @property
    def data(self):
        """ Binary data """

        if self._data is None:
            try:
                method = HrGetOneProp(self.att, PR_ATTACH_METHOD).Value # XXX is this just here to raise an exception?
                self._data = _stream(self.att, PR_ATTACH_DATA_BIN)
            except MAPIErrorNotFound:
                self._data = ''
        return self._data

    # file-like behaviour
    def read(self):
        return self.data

    @property
    def name(self):
        return self.filename

    def prop(self, proptag):
        return _prop(self, self.att, proptag)

    def props(self):
        return _props(self.att)

class User(object):
    """ User class """

    def __init__(self, name, server=None):
        server = server or Server()
        self._name = name = unicode(name)
        self.server = server
        try:
            self._ecuser = self.server.sa.GetUser(self.server.sa.ResolveUserName(self._name, MAPI_UNICODE), MAPI_UNICODE)
        except MAPIErrorNotFound:
            raise ZarafaException("no such user: '%s'" % name)
        self.mapiobj = self.server.mapisession.OpenEntry(self._ecuser.UserID, None, 0)

    @property
    def name(self):
        """ Account name """

        return self._name

    @name.setter
    def name(self, value):
        self._update(username=unicode(value))

    @property
    def fullname(self):
        """ Full name """

        return self._ecuser.FullName

    @fullname.setter
    def fullname(self, value):
        self._update(fullname=unicode(value))

    @property
    def email(self):
        """ Email address """

        return self._ecuser.Email

    @email.setter
    def email(self, value):
        self._update(email=unicode(value))

    @property
    def userid(self):
        """ Userid """

        return bin2hex(self._ecuser.UserID)

    @property
    def company(self):
        """ :class:`Company` the user belongs to """

        return Company(self.server, HrGetOneProp(self.mapiobj, PR_EC_COMPANY_NAME_W).Value or u'Default')

    @property # XXX
    def local(self):
        store = self.store
        return bool(store and (self.server.guid == bin2hex(HrGetOneProp(store.mapiobj, PR_MAPPING_SIGNATURE).Value)))

    @property
    def store(self):
        """ Default :class:`Store` for user or *None* if no store is attached """

        try:
            storeid = self.server.ems.CreateStoreEntryID(None, self._name, MAPI_UNICODE)
            mapistore = self.server.mapisession.OpenMsgStore(0, storeid, IID_IMsgStore, MDB_WRITE|MAPI_DEFERRED_ERRORS)
            return Store(self.server, mapistore)
        except MAPIErrorNotFound:
            pass

    @property
    def archive_store(self):
        """ Archive :class:`Store` for user or *None* if not found """

        mapistore = self.store.mapiobj
        ids = mapistore.GetIDsFromNames(NAMED_PROPS_ARCHIVER, 0) # XXX merge namedprops stuff
        PROP_STORE_ENTRYIDS = CHANGE_PROP_TYPE(ids[0], PT_MV_BINARY)
        try:
            # support for multiple archives was a mistake, and is not and _should not_ be used. so we just pick nr 0.
            arch_storeid = HrGetOneProp(mapistore, PROP_STORE_ENTRYIDS).Value[0]
        except MAPIErrorNotFound:
            return
        arch_server = arch_storeid[arch_storeid.find('pseudo://')+9:-1]
        arch_session = self.server._archive_session(arch_server)
        if arch_session is None:
            return
        arch_store = arch_session.OpenMsgStore(0, arch_storeid, None, MDB_WRITE)
        return Store(self.server, arch_store) # XXX server?

    @property
    def active(self):
        return self._ecuser.Class == ACTIVE_USER

    @active.setter
    def active(self, value):
        if value:
            self._update(user_class=ACTIVE_USER)
        else:
            self._update(user_class=NONACTIVE_USER)

    @property
    def home_server(self):
        return self._ecuser.Servername

    @property
    def archive_server(self):
        try:
            return HrGetOneProp(self.mapiobj, PR_EC_ARCHIVE_SERVERS).Value[0]
        except MAPIErrorNotFound:
            return


    def prop(self, proptag):
        return _prop(self, self.mapiobj, proptag)

    def props(self):
        return _props(self.mapiobj)

    @property
    def quota(self):
        """ User :class:`Quota` """

        return Quota(self.server, self._ecuser.UserID)

    @property
    def outofoffice(self):
        """ User :class:`Outofoffice` """

        return self.store.outofoffice

    def groups(self):
        for g in self.server.sa.GetGroupListOfUser(self._ecuser.UserID, MAPI_UNICODE):
            yield Group(g.Groupname, self.server)


    def rules(self):
        return self.inbox.rules()

    def __unicode__(self):
        return u"User('%s')" % self._name

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

    def _update(self, **kwargs):
        username = kwargs.get('username', self.name)
        password = kwargs.get('password', self._ecuser.Password)
        email = kwargs.get('email', unicode(self._ecuser.Email))
        fullname = kwargs.get('fullname', unicode(self._ecuser.FullName))
        user_class = kwargs.get('user_class', self._ecuser.Class)

        if self.active:
            store = self.server.unhook_store(user=self)
        usereid = self.server.sa.SetUser(ECUSER(Username=username, Password=password, Email=email, FullName=fullname,
                                         Class=user_class, UserID=self._ecuser.UserID), MAPI_UNICODE)
        if self.active:
            storeguid = self.server.hook_store(store=store, user=self)
        self._ecuser = self.server.sa.GetUser(self.server.sa.ResolveUserName(username, MAPI_UNICODE), MAPI_UNICODE)
        if self.name != username:
            self._name = username

        return self

    def __getattr__(self, x):
        return getattr(self.store, x)

class Quota(object):
    """
    Quota class

    Quota limits are stored in bytes.

    """

    def __init__(self, server, userid):
        self.server = server
        self.userid = userid
        self._warning_limit = self._soft_limit = self._hard_limit = 0 # XXX quota for 'default' company?
        if userid:
            quota = server.sa.GetQuota(userid, False)
            self._warning_limit = quota.llWarnSize
            self._soft_limit = quota.llSoftSize
            self._hard_limit = quota.llHardSize
            # XXX: logical name for variable
            # Use default quota set in /etc/zarafa/server.cfg
            self._use_default_quota = quota.bUseDefaultQuota
            # XXX: is this for multitendancy?
            self._isuser_default_quota = quota.bIsUserDefaultQuota

    @property
    def warning_limit(self):
        """ Warning limit """

        return self._warning_limit

    @warning_limit.setter
    def warning_limit(self, value):
        self.update(warning_limit=value)

    @property
    def soft_limit(self):
        """ Soft limit """

        return self._soft_limit

    @soft_limit.setter
    def soft_limit(self, value):
        self.update(soft_limit=value)

    @property
    def hard_limit(self):
        """ Hard limit """

        return self._hard_limit

    @hard_limit.setter
    def hard_limit(self, value):
        self.update(hard_limit=value)

    def update(self, **kwargs):
        """
        Update function for Quota limits, currently supports the
        following kwargs: `warning_limit`, `soft_limit` and `hard_limit`.

        TODO: support defaultQuota and IsuserDefaultQuota
        """

        self._warning_limit = kwargs.get('warning_limit', self._warning_limit)
        self._soft_limit = kwargs.get('soft_limit', self._soft_limit)
        self._hard_limit = kwargs.get('hard_limit', self._hard_limit)
        # TODO: implement setting defaultQuota, userdefaultQuota
        # (self, bUseDefaultQuota, bIsUserDefaultQuota, llWarnSize, llSoftSize, llHardSize)
        quota = ECQUOTA(False, False, self._warning_limit, self._soft_limit, self._hard_limit)
        self.server.sa.SetQuota(self.userid, quota)

    @property
    def recipients(self):
        if self.userid:
            return [self.server.user(ecuser.Username) for ecuser in self.server.sa.GetQuotaRecipients(self.userid, 0)]
        else:
            return []

    def __unicode__(self):
        return u'Quota(warning=%s, soft=%s, hard=%s)' % (_bytes_to_human(self.warning_limit), _bytes_to_human(self.soft_limit), _bytes_to_human(self.hard_limit))

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')

class Rule:
    def __init__(self, name, state): # XXX fix args
        self.name = unicode(name)
        self.active = bool(state & ST_ENABLED)

    def __unicode__(self):
        return u"Rule('%s')" % self.name

    def __repr__(self):
        return unicode(self).encode(sys.stdout.encoding or 'utf8')


class TrackingContentsImporter(ECImportContentsChanges):
    def __init__(self, server, importer, log):
        ECImportContentsChanges.__init__(self, [IID_IExchangeImportContentsChanges, IID_IECImportContentsChanges])
        self.server = server
        self.importer = importer
        self.log = log
        self.skip = False

    def ImportMessageChangeAsAStream(self, props, flags):
        self.ImportMessageChange(props, flags)

    def ImportMessageChange(self, props, flags):
        if self.skip:
            raise MAPIError(SYNC_E_IGNORE)
        try:
            entryid = PpropFindProp(props, PR_ENTRYID)
            if self.importer.store:
                mapistore = self.importer.store.mapiobj
            else:
                store_entryid = PpropFindProp(props, PR_STORE_ENTRYID).Value
                store_entryid = WrapStoreEntryID(0, 'zarafa6client.dll', store_entryid[:-4])+self.server.pseudo_url+'\x00'
                mapistore = self.server.mapisession.OpenMsgStore(0, store_entryid, None, 0)
            item = Item()
            item.server = self.server
            item.store = Store(self.server, mapistore)
            try:
                item.mapiobj = _openentry_raw(mapistore, entryid.Value, 0)
                item.folderid = PpropFindProp(props, PR_EC_PARENT_HIERARCHYID).Value
                props = item.mapiobj.GetProps([PR_EC_HIERARCHYID, PR_EC_PARENT_HIERARCHYID, PR_STORE_RECORD_KEY], 0) # XXX properties don't exist?
                item.docid = props[0].Value
                # item.folderid = props[1].Value # XXX 
                item.storeid = bin2hex(props[2].Value)
                if hasattr(self.importer, 'update'):
                    self.importer.update(item, flags)
            except (MAPIErrorNotFound, MAPIErrorNoAccess): # XXX, mail already deleted, can we do this in a cleaner way?
                if self.log:
                    self.log.debug('received change for entryid %s, but it could not be opened' % bin2hex(entryid.Value))
        except Exception, e:
            if self.log:
                self.log.error('could not process change for entryid %s (%r):' % (bin2hex(entryid.Value), props))
                self.log.error(traceback.format_exc(e))
            else:
                traceback.print_exc(e)
        raise MAPIError(SYNC_E_IGNORE)

    def ImportMessageDeletion(self, flags, entries):
        if self.skip:
            return
        try:
            for entry in entries:
                item = Item()
                item.server = self.server
                item._sourcekey = bin2hex(entry)
                if hasattr(self.importer, 'delete'):
                    self.importer.delete(item, flags)
        except Exception, e:
            if self.log:
                self.log.error('could not process delete for entries: %s' % [bin2hex(entry) for entry in entries])
                self.log.error(traceback.format_exc(e))
            else:
                traceback.print_exc(e)

    def ImportPerUserReadStateChange(self, states):
        pass

    def UpdateState(self, stream):
        pass

def daemon_helper(func, service, log):
    try:
        if not service or isinstance(service, Service):
            if isinstance(service, Service): # XXX
                service.log_queue = Queue()
                service.ql = QueueListener(service.log_queue, *service.log.handlers)
                service.ql.start()
            func()
        else:
            func(service)
    finally:
        if isinstance(service, Service):
            service.ql.stop()
        if log and service:
            log.info('stopping %s', service.name)

def daemonize(func, options=None, foreground=False, args=[], log=None, config=None, service=None):
    if log and service:
        log.info('starting %s', service.logname or service.name)
    if foreground or (options and options.foreground):
        try:
            if isinstance(service, Service): # XXX
                service.log_queue = Queue()
                service.ql = QueueListener(service.log_queue, *service.log.handlers)
                service.ql.start()
            func(*args)
        finally:
            if log and service:
                log.info('stopping %s', service.logname or service.name)
    else:
        uid = gid = None
        working_directory = '/'
        pidfile = None
        if args:
            pidfile = '/var/run/zarafa-%s.pid' % args[0].name
        if config:
            working_directory = config.get('running_path')
            pidfile = config.get('pid_file')
            if config.get('run_as_user'):
                uid = pwd.getpwnam(config.get('run_as_user')).pw_uid
            if config.get('run_as_group'):
                gid = grp.getgrnam(config.get('run_as_group')).gr_gid
        if pidfile: # following checks copied from zarafa-ws
            pidfile = daemon.pidlockfile.TimeoutPIDLockFile(pidfile, 10)
            oldpid = pidfile.read_pid()
            if oldpid is None:
                # there was no pidfile, remove the lock if it's there
                pidfile.break_lock()
            elif oldpid:
                try:
                    cmdline = open('/proc/%u/cmdline' % oldpid).read().split('\0')
                except IOError, error:
                    if error.errno != errno.ENOENT:
                        raise
                    # errno.ENOENT indicates that no process with pid=oldpid exists, which is ok
                    pidfile.break_lock()
#                else: # XXX can we do this in general? are there libraries to avoid having to deal with this? daemonrunner? 
#                    # A process exists with pid=oldpid, check if it's a zarafa-ws instance.
#                    # sys.argv[0] contains the script name, which matches cmdline[1]. But once compiled
#                    # sys.argv[0] is probably the executable name, which will match cmdline[0].
#                    if not sys.argv[0] in cmdline[:2]:
#                        # break the lock if it's another process
#                        pidfile.break_lock()
        if uid is not None and gid is not None:
            for h in log.handlers:
                if isinstance(h, logging.handlers.WatchedFileHandler):
                    os.chown(h.baseFilename, uid, gid)
        with daemon.DaemonContext(
                pidfile=pidfile,
                uid=uid,
                gid=gid,
                working_directory=working_directory,
                files_preserve=[h.stream for h in log.handlers if isinstance(h, logging.handlers.WatchedFileHandler)] if log else None,
                prevent_core=False,
            ):
            daemon_helper(func, service, log)

def _loglevel(options, config):
    if options and getattr(options, 'loglevel', None):
        log_level = options.loglevel
    elif config:
        log_level = config.get('log_level')
    else:
        log_level = 'debug'
    return { # XXX NONE?
        '0': logging.NOTSET,
        '1': logging.CRITICAL,
        '2': logging.ERROR,
        '3': logging.WARNING,
        '4': logging.INFO,
        '5': logging.INFO,
        '6': logging.DEBUG,
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL,
    }[log_level]

def logger(service, options=None, stdout=False, config=None, name=''):
    logger = logging.getLogger(name or service)
    if logger.handlers:
        return logger
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_method = 'file'
    log_file = '/var/log/zarafa/%s.log' % service
    if config:
        log_method = config.get('log_method') or log_method
        log_file = config.get('log_file') or log_file
    log_level = _loglevel(options, config)
    if name:
        log_file = log_file.replace(service, name) # XXX
    fh = None
    if log_method == 'file' and log_file != '-':
        fh = logging.handlers.WatchedFileHandler(log_file)
    elif log_method == 'syslog':
        fh = logging.handlers.SysLogHandler(address='/dev/log')
    if fh:
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    ch = logging.StreamHandler() # XXX via options?
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    if stdout or (options and options.foreground):
        logger.addHandler(ch)
    logger.setLevel(log_level)
    return logger

def _parse_date(option, opt_str, value, parser):
    setattr(parser.values, option.dest, datetime.datetime.strptime(value, '%Y-%m-%d'))

def parser(options='cskpUPufmvCSlbe'):
    """
Return OptionParser instance from the standard ``optparse`` module, containing common zarafa command-line options

:param options: string containing a char for each desired option, default "cskpUPufmvV"

Available options:

-c, --config: Path to configuration file

-s, --server-socket: Zarafa server socket address

-k, --sslkey-file: SSL key file

-p, --sslkey-password: SSL key password

-U, --auth-user: Login as user

-P, --auth-pass: Login with password

-C, --company: Run program for specific company

-u, --user: Run program for specific user

-S, --store: Run program for specific store

-f, --folder: Run program for specific folder

-b, --period-begin: Run program for specific period

-e, --period-end: Run program for specific period

-F, --foreground: Run service in foreground

-m, --modify: Enable database modification (python-zarafa does not check this!)

-l, --log-level: Set log level (debug, info, warning, error, critical)

-I, --input-dir: Specify input directory

-O, --output-dir: Specify output directory

-v, --verbose: Enable verbose output (python-zarafa does not check this!)

-V, --version: Show program version and exit
"""

    parser = optparse.OptionParser()

    if 'c' in options: parser.add_option('-c', '--config', dest='config_file', help='Load settings from FILE', metavar='FILE')

    if 's' in options: parser.add_option('-s', '--server-socket', dest='server_socket', help='Connect to server SOCKET', metavar='SOCKET')
    if 'k' in options: parser.add_option('-k', '--ssl-key', dest='sslkey_file', help='SSL key file', metavar='FILE')
    if 'p' in options: parser.add_option('-p', '--ssl-pass', dest='sslkey_pass', help='SSL key password', metavar='PASS')
    if 'U' in options: parser.add_option('-U', '--auth-user', dest='auth_user', help='Login as user', metavar='NAME')
    if 'P' in options: parser.add_option('-P', '--auth-pass', dest='auth_pass', help='Login with password', metavar='PASS')

    if 'C' in options: parser.add_option('-C', '--company', dest='companies', action='append', default=[], help='Run program for specific company', metavar='NAME')
    if 'u' in options: parser.add_option('-u', '--user', dest='users', action='append', default=[], help='Run program for specific user', metavar='NAME')
    if 'S' in options: parser.add_option('-S', '--store', dest='stores', action='append', default=[], help='Run program for specific store', metavar='GUID')
    if 'f' in options: parser.add_option('-f', '--folder', dest='folders', action='append', default=[], help='Run program for specific folder', metavar='NAME')

    if 'b' in options: parser.add_option('-b', '--period-begin', dest='period_begin', action='callback', help='Run program for specific period', callback=_parse_date, metavar='DATE', type='str')
    if 'e' in options: parser.add_option('-e', '--period-end', dest='period_end', action='callback', help='Run program for specific period', callback=_parse_date, metavar='DATE', type='str')

    if 'F' in options: parser.add_option('-F', '--foreground', dest='foreground', action='store_true', help='Run program in foreground')

    if 'm' in options: parser.add_option('-m', '--modify', dest='modify', action='store_true', help='Enable database modification')
    if 'l' in options: parser.add_option('-l', '--log-level', dest='loglevel', action='store', help='Set log level', metavar='NAME')
    if 'v' in options: parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Enable verbose output')
    if 'V' in options: parser.add_option('-V', '--version', dest='version', action='store_true', help='Show program version')

    if 'w' in options: parser.add_option('-w', '--worker-processes', dest='worker_processes', help='Number of parallel worker processes', metavar='N', type='int')

    if 'I' in options: parser.add_option('-I', '--input-dir', dest='input_dir', help='Specify input directory', metavar='PATH')
    if 'O' in options: parser.add_option('-O', '--output-dir', dest='output_dir', help='Specify output directory', metavar='PATH')

    return parser

@contextlib.contextmanager # it logs errors, that's all you need to know :-)
def log_exc(log):
    """
Context-manager to log any exception in sub-block to given logger instance

:param log: logger instance

Example usage::

    with log_exc(log):
        .. # any exception will be logged when exiting sub-block

"""
    try: yield
    except Exception, e: log.error(traceback.format_exc(e))

def _bytes_to_human(b):
    suffixes = ['b', 'kb', 'mb', 'gb', 'tb', 'pb']
    if b == 0: return '0 b'
    i = 0
    len_suffixes = len(suffixes)-1
    while b >= 1024 and i < len_suffixes:
        b /= 1024
        i += 1
    f = ('%.2f' % b).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

def _human_to_bytes(s):
    '''
    Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
    License: MIT
    '''
    s = s.lower()
    init = s
    num = ""
    while s and s[0:1].isdigit() or s[0:1] == '.':
        num += s[0]
        s = s[1:]
    num = float(num)
    letter = s.strip()
    for sset in [('b', 'k', 'm', 'g', 't', 'p', 'e', 'z', 'y'),
                 ('b', 'kb', 'mb', 'gb', 'tb', 'pb', 'eb', 'zb', 'yb'),
                 ('b', 'kib', 'mib', 'gib', 'tib', 'pib', 'eib', 'zib', 'yib')]:
        if letter in sset:
            break
    else:
        raise ValueError("can't interpret %r" % init)
    prefix = {sset[0]:1}
    for i, s in enumerate(sset[1:]):
        prefix[s] = 1 << (i+1)*10
    return int(num * prefix[letter])

class ConfigOption:
    def __init__(self, type_, **kwargs):
        self.type_ = type_
        self.kwargs = kwargs

    def parse(self, key, value):
        return getattr(self, 'parse_'+self.type_)(key, value)

    def parse_string(self, key, value):
        if self.kwargs.get('multiple') == True:
            values = value.split()
        else:
            values = [value]
        for value in values:
            if self.kwargs.get('check_path') is True and not os.path.exists(value): # XXX moved to parse_path
                raise ZarafaConfigException("%s: path '%s' does not exist" % (key, value))
            if self.kwargs.get('options') is not None and value not in self.kwargs.get('options'):
                raise ZarafaConfigException("%s: '%s' is not a legal value" % (key, value))
        if self.kwargs.get('multiple') == True:
            return values
        else:
            return values[0]

    def parse_path(self, key, value):
        if self.kwargs.get('check', True) and not os.path.exists(value):
            raise ZarafaConfigException("%s: path '%s' does not exist" % (key, value))
        return value

    def parse_integer(self, key, value):
        if self.kwargs.get('options') is not None and int(value) not in self.kwargs.get('options'):
            raise ZarafaConfigException("%s: '%s' is not a legal value" % (key, value))
        if self.kwargs.get('multiple') == True:
            return [int(x, base=self.kwargs.get('base', 10)) for x in value.split()]
        return int(value, base=self.kwargs.get('base', 10))

    def parse_boolean(self, key, value):
        return {'no': False, 'yes': True, '0': False, '1': True, 'false': False, 'true': True}[value]

    def parse_size(self, key, value):
        return _human_to_bytes(value)

class Config:
    """
Configuration class

:param config: dictionary describing configuration options. TODO describe available options

Example::

    config = Config({
        'some_str': Config.String(default='blah'),
        'number': Config.Integer(),
        'filesize': Config.size(), # understands '5MB' etc
    })

"""
    def __init__(self, config, service=None, options=None, filename=None, log=None):
        self.config = config
        self.service = service
        self.warnings = []
        self.errors = []
        if filename:
            pass
        elif options and getattr(options, 'config_file', None):
            filename = options.config_file
        elif service:
            filename = '/etc/zarafa/%s.cfg' % service
        self.data = {}
        if self.config is not None:
            for key, val in self.config.items():
                if 'default' in val.kwargs:
                    self.data[key] = val.kwargs.get('default')
        for line in file(filename):
            line = line.strip().decode('utf-8')
            if not line.startswith('#'):
                pos = line.find('=')
                if pos != -1:
                    key = line[:pos].strip()
                    value = line[pos+1:].strip()
                    if self.config is None:
                        self.data[key] = value
                    elif key in self.config:
                        if self.config[key].type_ == 'ignore':
                            self.data[key] = None
                            self.warnings.append('%s: config option ignored' % key)
                        else:
                            try:
                                self.data[key] = self.config[key].parse(key, value)
                            except ZarafaConfigException, e:
                                if service:
                                    self.errors.append(e.message)
                                else:
                                    raise
                    else:
                        msg = "%s: unknown config option" % key
                        if service:
                            self.warnings.append(msg)
                        else:
                            raise ZarafaConfigException(msg)
        if self.config is not None:
            for key, val in self.config.items():
                if key not in self.data and val.type_ != 'ignore':
                    msg = "%s: missing in config file" % key
                    if service: # XXX merge
                        self.errors.append(msg)
                    else:
                        raise ZarafaConfigException(msg)

    @staticmethod
    def string(**kwargs):
        return ConfigOption(type_='string', **kwargs)

    @staticmethod
    def path(**kwargs):
        return ConfigOption(type_='path', **kwargs)

    @staticmethod
    def boolean(**kwargs):
        return ConfigOption(type_='boolean', **kwargs)

    @staticmethod
    def integer(**kwargs):
        return ConfigOption(type_='integer', **kwargs)

    @staticmethod
    def size(**kwargs):
        return ConfigOption(type_='size', **kwargs)

    @staticmethod
    def ignore(**kwargs):
        return ConfigOption(type_='ignore', **kwargs)

    def get(self, x, default=None):
        return self.data.get(x, default)

    def __getitem__(self, x):
        return self.data[x]

CONFIG = {
    'log_method': Config.string(options=['file', 'syslog'], default='file'),
    'log_level': Config.string(options=map(str, range(7))+['info', 'debug', 'warning', 'error', 'critical'], default='info'),
    'log_file': Config.string(default=None),
    'log_timestamp': Config.integer(options=[0,1], default=1),
    'pid_file': Config.string(default=None),
    'run_as_user': Config.string(default=None),
    'run_as_group': Config.string(default=None),
    'running_path': Config.string(check_path=True, default='/'),
    'server_socket': Config.string(default=None),
    'sslkey_file': Config.string(default=None),
    'sslkey_pass': Config.string(default=None),
    'worker_processes': Config.integer(default=1),
}

# log-to-queue handler copied from Vinay Sajip
class QueueHandler(logging.Handler):
    def __init__(self, queue):
        logging.Handler.__init__(self)
        self.queue = queue

    def enqueue(self, record):
        self.queue.put_nowait(record)

    def prepare(self, record):
        self.format(record)
        record.msg, record.args, record.exc_info = record.message, None, None
        return record

    def emit(self, record):
        try:
            self.enqueue(self.prepare(record))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

# log-to-queue listener copied from Vinay Sajip
class QueueListener(object):
    _sentinel = None

    def __init__(self, queue, *handlers):
        self.queue = queue
        self.handlers = handlers
        self._stop = threading.Event()
        self._thread = None

    def dequeue(self, block):
        return self.queue.get(block)

    def start(self):
        self._thread = t = threading.Thread(target=self._monitor)
        t.setDaemon(True)
        t.start()

    def prepare(self, record):
        return record

    def handle(self, record):
        record = self.prepare(record)
        for handler in self.handlers:
            handler.handle(record)

    def _monitor(self):
        q = self.queue
        has_task_done = hasattr(q, 'task_done')
        while not self._stop.isSet():
            try:
                record = self.dequeue(True)
                if record is self._sentinel:
                    break
                self.handle(record)
                if has_task_done:
                    q.task_done()
            except Empty:
                pass
        # There might still be records in the queue.
        while True:
            try:
                record = self.dequeue(False)
                if record is self._sentinel:
                    break
                self.handle(record)
                if has_task_done:
                    q.task_done()
            except Empty:
                break

    def stop(self):
        self._stop.set()
        self.queue.put_nowait(self._sentinel)
        self._thread.join()
        self._thread = None

class Service:
    """
Encapsulates everything to create a simple Zarafa service, such as:

- Locating and parsing a configuration file
- Performing logging, as specifified in the configuration file
- Handling common command-line options (-c, -F)
- Daemonization (if no -F specified)

:param name: name of the service; if for example 'search', the configuration file should be called ``/etc/zarafa/search.cfg`` or passed with -c
:param config: :class:`Configuration <Config>` to use
:param options: OptionParser instance to get settings from (see :func:`parser`)

"""

    def __init__(self, name, config=None, options=None, args=None, logname=None, **kwargs):
        self.name = name
        self.__dict__.update(kwargs)
        if not options:
            options, args = parser('cskpUPufmvVFw').parse_args() # XXX store args?
        self.options, self.args = options, args
        self.name = name
        self.logname = logname
        config2 = CONFIG.copy()
        if config:
            config2.update(config)
        if getattr(options, 'config_file', None):
            options.config_file = os.path.abspath(options.config_file) # XXX useful during testing. could be generalized with optparse callback?
        self.config = Config(config2, service=name, options=options)
        self.config.data['server_socket'] = os.getenv('ZARAFA_SOCKET') or self.config.data['server_socket']
        if getattr(options, 'worker_processes', None):
            self.config.data['worker_processes'] = options.worker_processes
        self.log = logger(self.logname or self.name, options=self.options, config=self.config) # check that this works here or daemon may die silently XXX check run_as_user..?
        for msg in self.config.warnings:
            self.log.warn(msg)
        if self.config.errors:
            for msg in self.config.errors:
                self.log.error(msg)
            sys.exit(1)

    @property
    def server(self):
        return Server(options=self.options, config=self.config.data, log=self.log, service=self)

    def start(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *args: sys.exit(-sig))
        with log_exc(self.log):
            daemonize(self.main, options=self.options, args=[], log=self.log, config=self.config, service=self)

class Worker(Process):
    def __init__(self, service, name, **kwargs):
        Process.__init__(self)
        self.daemon = True
        self.name = name
        self.service = service
        self.__dict__.update(kwargs)
        self.log = logging.getLogger(name=self.name)
        if not self.log.handlers:
            loglevel = _loglevel(service.options, service.config)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            qh = QueueHandler(service.log_queue)
            qh.setFormatter(formatter)
            qh.setLevel(loglevel)
            self.log.addHandler(qh)
            self.log.setLevel(loglevel)

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        with log_exc(self.log):
            self.main()

class _ZSocket: # XXX megh, double wrapper
    def __init__(self, addr, ssl_key, ssl_cert):
        self.ssl_key = ssl_key
        self.ssl_cert = ssl_cert
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind(addr)
        self.s.listen(5)

    def accept(self):
        newsocket, fromaddr = self.s.accept()
        connstream = ssl.wrap_socket(newsocket, server_side=True, keyfile=self.ssl_key, certfile=self.ssl_cert)
        return connstream, fromaddr


def server_socket(addr, ssl_key=None, ssl_cert=None, log=None): # XXX https, merge code with client_socket
    if addr.startswith('file://'):
        addr2 = addr.replace('file://', '')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        os.system('rm -f %s' % addr2)
        s.bind(addr2)
        s.listen(5)
    elif addr.startswith('https://'):
        addr2 = addr.replace('https://', '').split(':')
        addr2 = (addr2[0], int(addr2[1]))
        s = _ZSocket(addr2, ssl_key=ssl_key, ssl_cert=ssl_cert)
    else:
        addr2 = addr.replace('http://', '').split(':')
        addr2 = (addr2[0], int(addr2[1]))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(addr2)
        s.listen(5)
    if log:
        log.info('listening on socket %s', addr)
    return s

def client_socket(addr, ssl_cert=None, log=None):
    if addr.startswith('file://'):
        addr2 = addr.replace('file://', '')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    elif addr.startswith('https://'):
        addr2 = addr.replace('https://', '').split(':')
        addr2 = (addr2[0], int(addr2[1]))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s = ssl.wrap_socket(s, ca_certs=ssl_cert, cert_reqs=ssl.CERT_REQUIRED)
    else:
        addr2 = addr.replace('http://', '').split(':')
        addr2 = (addr2[0], int(addr2[1]))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(addr2)
    return s
