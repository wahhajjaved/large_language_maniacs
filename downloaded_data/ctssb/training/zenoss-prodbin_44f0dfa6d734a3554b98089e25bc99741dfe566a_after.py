###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2010, Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################

from zope.interface import implements
from interfaces import IProtobufSerializer
from Products.ZenUtils.guid.interfaces import IGlobalIdentifier, \
    IGloballyIdentifiable
from zenoss.protocols.protobufs import zep_pb2 as eventConstants
from zenoss.protocols.protobufs import model_pb2 as modelConstants
from Products.ZenMessaging.queuemessaging.interfaces import IModelProtobufSerializer
from Products.ZenEvents.events2.proxy import EventProxy 

class ObjectProtobuf(object):
    """
    Base class for common methods on the protobuf populators
    """
    def __init__(self, obj):
        self.obj = obj

    def _getGUID(self, obj):
        return IGlobalIdentifier(obj).create()

    def autoMapFields(self, proto):
        """
        This maps fields that have the same name from the
        adapted object to the protobuf
        """
        if IGloballyIdentifiable.providedBy(self.obj):
            proto.uuid = self._getGUID(self.obj)
        fields = proto.DESCRIPTOR.fields

        # attempt to match the fields that are named the same
        for field in fields:
            # already set
            if field.name == "uuid":
                continue
            value = getattr(self.obj, field.name, None)
            # we want 0's
            if value is None:
                continue
            try:
                setattr(proto, field.name, value)
            except (AttributeError, TypeError):
                # likely a composite field that we will have to set manually
                continue


class DeviceProtobuf(ObjectProtobuf):
    """
    Fills up the properties of a device protobuf.
    """

    implements(IModelProtobufSerializer)

    @property
    def modelType(self):
        return "DEVICE"

    def fill(self, proto):
        self.autoMapFields(proto)
        proto.title = self.obj.titleOrId()
        return proto


class OrganizerProtobuf(ObjectProtobuf):
    """
    Fills up the properties of an organizer protobuf.
    """

    implements(IModelProtobufSerializer)

    @property
    def modelType(self):
        return "ORGANIZER"

    def fill(self, proto):
        self.autoMapFields(proto)
        proto.title = self.obj.titleOrId()
        #get path minus first 3 '', 'zport', 'dmd'
        proto.path = '/'.join(self.obj.getPrimaryPath()[3:])
        return proto

class DeviceComponentProtobuf(ObjectProtobuf):
    """
    Fills up the properties of a Device Component
    """
    implements(IModelProtobufSerializer)

    @property
    def modelType(self):
        return "COMPONENT"

    def fill(self, proto):
        self.autoMapFields(proto)
        proto.title = self.obj.name()
        # use device protobuf to fill out our device property
        device = self.obj.device()
        if device:
            populator = DeviceProtobuf(device)
            populator.fill(proto.device)
        return proto

def _safestr(s):
    """
    Defensive catchall to be sure that any string going into a protobuf can be
    decoded safely with 7-bit ASCII.  If any specialized encoding is desired, it
    is the responsibility of the caller/sender to take care of it.
    """
    if isinstance(s, str):
        try:
            unicode(s, 'ascii')
        except UnicodeDecodeError:
            s = str(s.decode('ascii','ignore'))
    elif not isinstance(s, basestring):
        s = str(s)
    return s

class EventProtobufMapper(object):
    """
    Base class for mapping a Event value (old-style) to a protobuf Event.
    """
    def mapEvent(self, proto, value):
        """
        Maps the event value to the protobuf.
        """
        pass

class EventProtobufStringMapper(EventProtobufMapper):
    """
    Performs a 1-1 mapping of an old event attribute to a corresponding
    field in the Event protobuf.
    """

    def __init__(self, fieldName):
        self._fieldName = fieldName

    def mapEvent(self, proto, value):
        setattr(proto, self._fieldName, _safestr(value))

class EventProtobufDeviceMapper(EventProtobufMapper):
    """
    Maps a 'device' to the corresponding location in the Event.EventActor.
    """

    def mapEvent(self, proto, value):
        proto.actor.element_type_id = modelConstants.DEVICE
        proto.actor.element_identifier = _safestr(value)

class EventProtobufComponentMapper(EventProtobufMapper):
    """
    Maps a 'component' to the corresponding location in the Event.EventActor.
    """

    def mapEvent(self, proto, value):
        if value:
            proto.actor.element_sub_type_id = modelConstants.COMPONENT
            proto.actor.element_sub_identifier = _safestr(value)

class EventProtobufSeverityMapper(EventProtobufMapper):
    """
    Maps an event severity to the EventSeverity enum value.
    """

    SEVERITIES = {
        '': eventConstants.SEVERITY_CLEAR,
        '0': eventConstants.SEVERITY_CLEAR,
        '1': eventConstants.SEVERITY_DEBUG,
        '2': eventConstants.SEVERITY_INFO,
        '3': eventConstants.SEVERITY_WARNING,
        '4': eventConstants.SEVERITY_ERROR,
        '5': eventConstants.SEVERITY_CRITICAL,
        'CLEAR': eventConstants.SEVERITY_CLEAR,
        'DEBUG': eventConstants.SEVERITY_DEBUG,
        'INFO': eventConstants.SEVERITY_INFO,
        'WARNING': eventConstants.SEVERITY_WARNING,
        'ERROR': eventConstants.SEVERITY_ERROR,
        'CRITICAL': eventConstants.SEVERITY_CRITICAL,
    }

    def mapEvent(self, proto, value):
        severity = str(value).upper()
        proto.severity = self.SEVERITIES.get(severity, 
             eventConstants.SEVERITY_INFO)

class EventProtobufIntMapper(EventProtobufMapper):
    """
    Maps an event to an integer value in the protobuf.
    """

    def __init__(self, fieldName):
        self._fieldName = fieldName

    def mapEvent(self, proto, value):
        try:
            setattr(proto, self._fieldName, int(value))
        except ValueError:
            pass

class EventProtobufSyslogPriorityMapper(EventProtobufMapper):
    """
    Maps a syslog priority value to the corresponding SyslogPriority.*.
    """

    SYSLOG_PRIORITIES = {
        0: eventConstants.SYSLOG_PRIORITY_EMERG,
        1: eventConstants.SYSLOG_PRIORITY_ALERT,
        2: eventConstants.SYSLOG_PRIORITY_CRIT,
        3: eventConstants.SYSLOG_PRIORITY_ERR,
        4: eventConstants.SYSLOG_PRIORITY_WARNING,
        5: eventConstants.SYSLOG_PRIORITY_NOTICE,
        6: eventConstants.SYSLOG_PRIORITY_INFO,
        7: eventConstants.SYSLOG_PRIORITY_DEBUG,
    }

    def mapEvent(self, proto, value):
        try:
            proto.syslog_priority = self.SYSLOG_PRIORITIES[int(value)]
        except (KeyError, ValueError):
            pass

class EventProtobufDateMapper(EventProtobufMapper):
    """
    Maps a time.time() floating point value to the time in
    milliseconds as used by Event.
    """

    def __init__(self, fieldName):
        self._fieldName = fieldName

    def mapEvent(self, proto, value):
        setattr(proto, self._fieldName, int(value * 1000))

class EventProtobufDetailMapper(EventProtobufMapper):
    """
    Map's an event property to a new name in details.
    """

    def __init__(self, detailName):
        self._detailName = detailName

    def mapEvent(self, proto, value):
        proto.details.add(name=self._detailName, value=[value])

class EventProtobuf(ObjectProtobuf):
    """
    Fills up the properties of an event
    """

    implements(IProtobufSerializer)

    # event property, protobuf property
    _FIELD_MAPPERS = {
        'dedupid': EventProtobufStringMapper('fingerprint'),
        'evid' : EventProtobufStringMapper('uuid'),
        'device': EventProtobufDeviceMapper(),
        'component': EventProtobufComponentMapper(),
        'eventClass': EventProtobufStringMapper('event_class'),
        'eventKey': EventProtobufStringMapper('event_key'),
        'summary': EventProtobufStringMapper('summary'),
        'message': EventProtobufStringMapper('message'),
        'severity': EventProtobufSeverityMapper(),
        'eventState': EventProtobufIntMapper('status'),
        'eventClassKey': EventProtobufStringMapper('event_class_key'),
        'eventGroup': EventProtobufStringMapper('event_group'),
        # stateChange -> Managed by ZEP
        # firstTime -> Managed by ZEP
        'lastTime': EventProtobufDateMapper('created_time'),
        # count -> Managed by ZEP
        # prodState -> Added by zeneventd
        # suppid -> Added as a detail (deprecated)
        # manager -> Added as a detail (deprecated)
        'agent': EventProtobufStringMapper('agent'),
        # DeviceClass -> Added by zeneventd
        # Location -> Added by zeneventd
        # Systems -> Added by zeneventd
        # DeviceGroups -> Added by zeneventd
        'ipAddress': EventProtobufDetailMapper(EventProxy.DEVICE_IP_ADDRESS_DETAIL_KEY),
        'facility': EventProtobufIntMapper('syslog_facility'),
        'priority': EventProtobufSyslogPriorityMapper(),
        'ntevid': EventProtobufIntMapper('nt_event_code'),
        # ownerid -> Managed by ZEP
        # clearid -> Managed by ZEP
        # DevicePriority -> Added by zeneventd
        # eventClassMapping -> Added by zeneventd
        'monitor': EventProtobufStringMapper('monitor'),
    }

    # If these attributes are found on the Event they are not mapped and are not
    # placed into event details.
    _IGNORED_ATTRS = set(['_action','_clearClasses','_fields','stateChange','firstTime',
                          'count','prodState','DeviceClass','Location','Systems',
                          'DeviceGroups','ownerid','clearid','DevicePriority','eventClassMapping'])

    def __init__(self, obj):
        ObjectProtobuf.__init__(self, obj)

    def addDetail(self, proto, name, value):
        isIterable = lambda x : hasattr(x, '__iter__')
        detail = proto.details.add()
        detail.name = name
        if isIterable(value):
            for v in value:
                detail.value.append(_safestr(v))
        else:
            detail.value.append(_safestr(value))

    def fill(self, proto):
        event = self.obj

        for key, value in event.__dict__.iteritems():
            if key in self._IGNORED_ATTRS or value is None:
                continue
            mapper = self._FIELD_MAPPERS.get(key)
            if mapper:
                mapper.mapEvent(proto, value)
            else:
                self.addDetail(proto, key, value)

        return proto

