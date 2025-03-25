"""
(c) 2013 LinkedIn Corp. All rights reserved.
Licensed under the Apache License, Version 2.0 (the "License");?you may not use this file except in compliance with the License. You may obtain a copy of the License at  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software?distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
"""
# TODO get flake8 to just ignore the lines I want, dangit
# flake8: noqa

import logging
from ..base.calendar import BaseExchangeCalendarEvent, BaseExchangeCalendarService, ExchangeEventOrganizer, ExchangeEventResponse
from ..base.folder import BaseExchangeFolder, BaseExchangeFolderService
from ..base.soap import ExchangeServiceSOAP
from ..exceptions import FailedExchangeException, ExchangeStaleChangeKeyException, ExchangeItemNotFoundException

from . import soap_request

from lxml import etree

log = logging.getLogger("pyexchange")


class Exchange2010Service(ExchangeServiceSOAP):

  def calendar(self, id="calendar"):
    return Exchange2010CalendarService(service=self, calendar_id=id)

  def mail(self):
    raise NotImplementedError("Sorry - nothin' here. Feel like adding it? :)")

  def contacts(self):
    raise NotImplementedError("Sorry - nothin' here. Feel like adding it? :)")

  def folder(self):
    return Exchange2010FolderService(service=self)

  def _send_soap_request(self, body, headers=None, retries=2, timeout=30, encoding="utf-8"):
    headers = [("Accept", "text/xml"), ("Content-type", "text/xml; charset=%s " % encoding)]
    return super(Exchange2010Service, self)._send_soap_request(body, headers=headers, retries=retries, timeout=timeout, encoding=encoding)

  def _check_for_errors(self, xml_tree):
    super(Exchange2010Service, self)._check_for_errors(xml_tree)
    self._check_for_exchange_fault(xml_tree)

  def _check_for_exchange_fault(self, xml_tree):

    # If the request succeeded, we should see a <m:ResponseCode>NoError</m:ResponseCode>
    # somewhere in the response. if we don't (a) see the tag or (b) it doesn't say "NoError"
    # then flip out

    response_codes = xml_tree.xpath(u'//m:ResponseCode', namespaces=soap_request.NAMESPACES)

    if not response_codes:
      raise FailedExchangeException(u"Exchange server did not return a status response", None)

    # The full (massive) list of possible return responses is here.
    # http://msdn.microsoft.com/en-us/library/aa580757(v=exchg.140).aspx
    for code in response_codes:
      if code.text == u"ErrorChangeKeyRequiredForWriteOperations":
        # change key is missing or stale. we can fix that, so throw a special error
        raise ExchangeStaleChangeKeyException(u"Exchange Fault (%s) from Exchange server" % code.text)
      elif code.text == u"ErrorItemNotFound":
        # exchange_invite_key wasn't found on the server
        raise ExchangeItemNotFoundException(u"Exchange Fault(%s) from Exchange server" % code.text)
      elif code.text != u"NoError":
        raise FailedExchangeException(u"Exchange Fault (%s) from Exchange server" % code.text)


class Exchange2010CalendarService(BaseExchangeCalendarService):

  def event(self, id=None, **kwargs):
    return Exchange2010CalendarEvent(service=self.service, id=id, **kwargs)

  def get_event(self, id):
    return Exchange2010CalendarEvent(service=self.service, id=id)

  def new_event(self, **properties):
    return Exchange2010CalendarEvent(service=self.service, calendar_id=self.calendar_id, **properties)


class Exchange2010CalendarEvent(BaseExchangeCalendarEvent):

  def _init_from_service(self, id):

    body = soap_request.get_item(exchange_id=id, format=u'AllProperties')
    response_xml = self.service.send(body)
    properties = self._parse_response_for_get_event(response_xml)

    self._update_properties(properties)
    self._id = id

    self._reset_dirty_attributes()

    return self

  def as_json(self):
    raise NotImplementedError

  def create(self):
    """
    Creates an event in Exchange. ::

        event = service.calendar().new_event(
          subject=u"80s Movie Night",
          location = u"My house",
        )
        event.create()

    Invitations to attendees are sent out immediately.

    """
    self.validate()
    body = soap_request.new_event(self)

    response_xml = self.service.send(body)
    self._id, self._change_key = self._parse_id_and_change_key_from_response(response_xml)

    return self

  def resend_invitations(self):
    """
    Resends invites for an event.  ::

        event = service.calendar().get_event(id='KEY HERE')
        event.resend_invitations()

    Anybody who has not declined this meeting will get a new invite.
    """

    if not self.id:
      raise TypeError(u"You can't send invites for an event that hasn't been created yet.")

    # Under the hood, this is just an .update() but with no attributes changed.
    # We're going to enforce that by checking if there are any changed attributes and bail if there are
    if self._dirty_attributes:
      raise ValueError(u"There are unsaved changes to this invite - please update it first: %r" % self._dirty_attributes)

    self.refresh_change_key()
    body = soap_request.update_item(self, [], send_only_to_changed_attendees=False)
    self.service.send(body)

    return self

  def update(self, send_only_to_changed_attendees=False):
    """
    Updates an event in Exchange.  ::

        event = service.calendar().get_event(id='KEY HERE')
        event.location = u'New location'
        event.update()

    If no changes to the event have been made, this method does nothing.

    Notification of the change event is sent to all users. If you wish to just notify people who were
    added, specify ``send_only_to_changed_attendees=True``.
    """
    if not self.id:
      raise TypeError(u"You can't update an event that hasn't been created yet.")

    self.validate()

    if self._dirty_attributes:
      log.debug(u"Updating these attributes: %r" % self._dirty_attributes)
      self.refresh_change_key()

      body = soap_request.update_item(self, self._dirty_attributes, send_only_to_changed_attendees=send_only_to_changed_attendees)
      self.service.send(body)
      self._reset_dirty_attributes()
    else:
      log.info(u"Update was called, but there's nothing to update. Doing nothing.")

    return self

  def cancel(self):
    """
    Cancels an event in Exchange.  ::

        event = service.calendar().get_event(id='KEY HERE')
        event.cancel()

    This will send notifications to anyone who has not declined the meeting.
    """
    if not self.id:
      raise TypeError(u"You can't delete an event that hasn't been created yet.")

    self.refresh_change_key()
    self.service.send(soap_request.delete_event(self))
    # TODO rsanders high - check return status to make sure it was actually sent
    return None

  def refresh_change_key(self):

    body = soap_request.get_item(exchange_id=self._id, format=u"IdOnly")
    response_xml = self.service.send(body)
    self._id, self._change_key = self._parse_id_and_change_key_from_response(response_xml)

    return self

  def _parse_id_and_change_key_from_response(self, response):

    id_elements = response.xpath(u'//m:Items/t:CalendarItem/t:ItemId', namespaces=soap_request.NAMESPACES)

    if id_elements:
      id_element = id_elements[0]
      return id_element.get(u"Id", None), id_element.get(u"ChangeKey", None)
    else:
      return None, None

  def _parse_response_for_get_event(self, response):

    result = self._parse_event_properties(response)

    organizer_properties = self._parse_event_organizer(response)
    result[u'organizer'] = ExchangeEventOrganizer(**organizer_properties)

    attendee_properties = self._parse_event_attendees(response)
    result[u'_attendees'] = self._build_resource_dictionary([ExchangeEventResponse(**attendee) for attendee in attendee_properties])

    resource_properties = self._parse_event_resources(response)
    result[u'_resources'] = self._build_resource_dictionary([ExchangeEventResponse(**resource) for resource in resource_properties])

    return result

  def _parse_event_properties(self, response):

    property_map = {
      u'subject'      : { u'xpath' : u'//m:Items/t:CalendarItem/t:Subject'},  # noqa
      u'location'     : { u'xpath' : u'//m:Items/t:CalendarItem/t:Location'},  # noqa
      u'availability' : { u'xpath' : u'//m:Items/t:CalendarItem/t:LegacyFreeBusyStatus'},  # noqa
      u'start'        : { u'xpath' : u'//m:Items/t:CalendarItem/t:Start', u'cast': u'datetime'},  # noqa
      u'end'          : { u'xpath' : u'//m:Items/t:CalendarItem/t:End', u'cast': u'datetime'},  # noqa
      u'html_body'    : { u'xpath' : u'//m:Items/t:CalendarItem/t:Body[@BodyType="HTML"]'},  # noqa
      u'text_body'    : { u'xpath' : u'//m:Items/t:CalendarItem/t:Body[@BodyType="Text"]'},  # noqa
    }

    return self.service._xpath_to_dict(element=response, property_map=property_map, namespace_map=soap_request.NAMESPACES)

  def _parse_event_organizer(self, response):

    organizer = response.xpath(u'//m:Items/t:CalendarItem/t:Organizer/t:Mailbox', namespaces=soap_request.NAMESPACES)

    property_map = {
      u'name'      : { u'xpath' : u't:Name'},  # noqa
      u'email'     : { u'xpath' : u't:EmailAddress'},  # noqa
    }

    if organizer:
      return self.service._xpath_to_dict(element=organizer[0], property_map=property_map, namespace_map=soap_request.NAMESPACES)
    else:
      return None

  def _parse_event_resources(self, response):
    property_map = {
      u'name'         : { u'xpath' : u't:Mailbox/t:Name'},  # noqa
      u'email'        : { u'xpath' : u't:Mailbox/t:EmailAddress'},  # noqa
      u'response'     : { u'xpath' : u't:ResponseType'},  # noqa
      u'last_response': { u'xpath' : u't:LastResponseTime', u'cast': u'datetime'},  # noqa
    }

    result = []

    resources = response.xpath(u'//m:Items/t:CalendarItem/t:Resources/t:Attendee', namespaces=soap_request.NAMESPACES)

    for attendee in resources:
      attendee_properties = self.service._xpath_to_dict(element=attendee, property_map=property_map, namespace_map=soap_request.NAMESPACES)
      attendee_properties[u'required'] = True

      if u'last_response' not in attendee_properties:
        attendee_properties[u'last_response'] = None

      result.append(attendee_properties)

    return result

  def _parse_event_attendees(self, response):

    property_map = {
      u'name'         : { u'xpath' : u't:Mailbox/t:Name'},  # noqa
      u'email'        : { u'xpath' : u't:Mailbox/t:EmailAddress'},  # noqa
      u'response'     : { u'xpath' : u't:ResponseType'},  # noqa
      u'last_response': { u'xpath' : u't:LastResponseTime', u'cast': u'datetime'},  # noqa
    }

    result = []

    required_attendees = response.xpath(u'//m:Items/t:CalendarItem/t:RequiredAttendees/t:Attendee', namespaces=soap_request.NAMESPACES)
    for attendee in required_attendees:
      attendee_properties = self.service._xpath_to_dict(element=attendee, property_map=property_map, namespace_map=soap_request.NAMESPACES)
      attendee_properties[u'required'] = True

      if u'last_response' not in attendee_properties:
        attendee_properties[u'last_response'] = None

      result.append(attendee_properties)

    optional_attendees = response.xpath(u'//m:Items/t:CalendarItem/t:OptionalAttendees/t:Attendee', namespaces=soap_request.NAMESPACES)

    for attendee in optional_attendees:
      attendee_properties = self.service._xpath_to_dict(element=attendee, property_map=property_map, namespace_map=soap_request.NAMESPACES)
      attendee_properties[u'required'] = False

      if u'last_response' not in attendee_properties:
        attendee_properties[u'last_response'] = None

      result.append(attendee_properties)

    return result


class Exchange2010FolderService(BaseExchangeFolderService):

  def folder(self, id=None, **kwargs):
    return Exchange2010Folder(service=self.service, id=id, **kwargs)

  def get_folder(self, id):
    return Exchange2010Folder(service=self.service, id=id)

  def new_folder(self, **properties):
    return Exchange2010Folder(service=self.service, **properties)

  def find_folder(self, parent_id):

    body = soap_request.find_folder(parent_id=parent_id, format=u'AllProperties')
    response_xml = self.service.send(body)
    return self._parse_response_for_find_folder(response_xml)

  def _parse_response_for_find_folder(self, response):

    result = []
    folders = response.xpath(u'//t:Folders/t:*', namespaces=soap_request.NAMESPACES)
    for folder in folders:
      result.append(
        Exchange2010Folder(
          service=self.service,
          xml=etree.fromstring(etree.tostring(folder))  # Might be a better way to do this
        )
      )

    return result


class Exchange2010Folder(BaseExchangeFolder):

  def _init_from_service(self, id):

    body = soap_request.get_folder(folder_id=id, format=u'AllProperties')
    response_xml = self.service.send(body)
    properties = self._parse_response_for_get_folder(response_xml)

    self._update_properties(properties)

    return self

  def _init_from_xml(self, xml):

    properties = self._parse_response_for_get_folder(xml)
    self._update_properties(properties)

    return self

  def create(self):

    self.validate()
    body = soap_request.new_folder(self)

    response_xml = self.service.send(body)
    print etree.tostring(response_xml, pretty_print=True)
    self._id, self._change_key = self._parse_id_and_change_key_from_response(response_xml)

    return self

  def delete(self):
    if not self.id:
      raise TypeError(u"You can't delete a folder that hasn't been created yet.")

    body = soap_request.delete_folder(self)

    response_xml = self.service.send(body)
    self._id = None
    self._change_key = None

    return self

  def _parse_response_for_get_folder(self, response):

    path = response.xpath(u'//t:Folder | //t:CalendarFolder', namespaces=soap_request.NAMESPACES)[0]
    result = self._parse_folder_properties(path)
    return result

  def _parse_folder_properties(self, response):

    property_map = {
      u'display_name'       : { u'xpath' : u't:DisplayName'},
    }

    self._id, self._change_key = self._parse_id_and_change_key_from_response(response)
    self._parent_id = self._parse_parent_id_and_change_key_from_response(response)[0]

    return self.service._xpath_to_dict(element=response, property_map=property_map, namespace_map=soap_request.NAMESPACES)

  def _parse_id_and_change_key_from_response(self, response):

    id_elements = response.xpath(u't:FolderId', namespaces=soap_request.NAMESPACES)

    if id_elements:
      id_element = id_elements[0]
      return id_element.get(u"Id", None), id_element.get(u"ChangeKey", None)
    else:
      return None, None

  def _parse_parent_id_and_change_key_from_response(self, response):

    id_elements = response.xpath(u't:ParentFolderId', namespaces=soap_request.NAMESPACES)

    if id_elements:
      id_element = id_elements[0]
      return id_element.get(u"Id", None), id_element.get(u"ChangeKey", None)
    else:
      return None, None
