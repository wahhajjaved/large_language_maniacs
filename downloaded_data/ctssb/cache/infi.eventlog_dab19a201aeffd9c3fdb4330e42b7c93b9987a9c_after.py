
from infi.pyutils.contexts import contextmanager
from infi.exceptools import InfiException
from logging import getLogger

logger = getLogger(__name__)

EvtQueryChannelPath           = 0x1
EvtQueryFilePath              = 0x2
EvtQueryForwardDirection      = 0x100
EvtQueryReverseDirection      = 0x200
EvtQueryTolerateQueryErrors   = 0x1000 
EvtOpenChannelPath   = 0x1
EvtOpenFilePath      = 0x2 

def get_c_api_module():
    from brownie.importing import import_string
    from os import name
    from mock import Mock
    is_windows = name == "nt"
    return import_string("infi.eventlog.c_api" if is_windows else "infi.eventlog.c_api.mock")

c_api = get_c_api_module()

class EventLogException(InfiException):
    pass

class Session(object):
    @contextmanager
    def open_context(self):
        raise NotImplementedError()

class LocalSession(Session):
    @contextmanager
    def open_context(self):
        yield None
        
class RemoteSession(Session):
    def __init__(self, computername, username, password, domain):
        raise NotImplementedError()

class EventLog(object):    
    def __init__(self, session):
        super(EventLog, self).__init__()
        self._session =  session
        self._flags = 0

    @contextmanager
    def open_channel_context(self, channel_name):
        channel_name = unicode(channel_name)
        channels = list(self.get_available_channels())
        flags = 0
        flags |= EvtOpenChannelPath if channel_name in channels else EvtOpenFilePath
        
        with self._session.open_context() as session_handle:
            evt_handle = c_api.EvtOpenLog(session_handle, channel_name, falgs)
        try:
            yield evt_handle
        finally:
            c_api.EvtClose(evt_handle)

    def get_available_channels(self):
        with self._session.open_context() as session_handle:
            evt_handle = c_api.EvtOpenChannelEnum(session_handle, 0)
            while True:
                try:
                    buffer = c_api.ctypes.create_unicode_buffer(c_api.MAX_LENGTH)
                    buffer_used = c_api.DWORD()
                    c_api.EvtNextChannelPath(evt_handle, c_api.MAX_LENGTH, buffer, 
                                             c_api.ctypes.byref(buffer_used))
                    yield buffer.value
                except c_api.WindowsException, error:
                    if error.winerror != c_api.ERROR_NO_MORE_ITEMS:
                        raise
                    break

    @contextmanager
    def query_context(self, channel_name, query, flags):
        channel_name = unicode(channel_name)
        with self._session.open_context() as session_handle:
            evt_handle = c_api.EvtQuery(session_handle, channel_name, query, flags)
            try:
                yield evt_handle
            finally:
                c_api.EvtClose(evt_handle)

    def event_query(self, channel_name, query="*", reversed=False):
        """:returns: a generator for events, from oldest to newest.
        Use reserved=True to get events in reversed order (newest to oldest)
        """
        channel_name = unicode(channel_name)
        channels = list(self.get_available_channels())
        flags = 0
        flags |= EvtQueryChannelPath if channel_name in channels else EvtQueryFilePath
        flags |= EvtQueryReverseDirection if reversed else EvtQueryForwardDirection
        with self.query_context(channel_name, query, flags):
            pass

class LocalEventLog(EventLog):
    def __init__(self):
        super(LocalEventLog, self).__init__(LocalSession())
