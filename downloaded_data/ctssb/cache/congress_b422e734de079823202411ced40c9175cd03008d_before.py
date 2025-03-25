#!/usr/bin/env python
# Copyright (c) 2013 VMware, Inc. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import httplib
import json
import re
import uuid
import webob
import webob.dec

from oslo.config import cfg

from congress.common import policy
from congress import exception
from congress.openstack.common import log as logging


LOG = logging.getLogger(__name__)


def error_response(status, error_code, description, data=None):
    """Construct and return an error response.

    Args:
        status: The HTTP status code of the response.
        error_code: The application-specific error code.
        description: Friendly G11N-enabled string corresponding ot error_code.
        data: Additional data (not G11N-enabled) for the API consumer.
    """
    raw_body = {
        'error_code': error_code,
        'description': description,
        'error_data': data
    }
    body = '%s\n' % json.dumps(raw_body)
    return webob.Response(body=body, status=status,
                          content_type='application/json')


NOT_SUPPORTED_RESPONSE = error_response(httplib.NOT_IMPLEMENTED,
                                        httplib.NOT_IMPLEMENTED,
                                        "Method not supported")
INTERNAL_ERROR_RESPONSE = error_response(httplib.INTERNAL_SERVER_ERROR,
                                         httplib.INTERNAL_SERVER_ERROR,
                                         "Internal server error")


class DataModelException(Exception):
    """Congress API Data Model Exception

    Custom exception raised by API Data Model methods to communicate errors to
    the API framework.
    """

    def __init__(self, error_code, description, data=None,
                 http_status_code=httplib.BAD_REQUEST):
        super(DataModelException, self).__init__(description)
        self.error_code = error_code
        self.description = description
        self.data = data
        self.http_status_code = http_status_code

    def rest_response(self):
        return error_response(self.http_status_code, self.error_code,
                              self.description, self.data)


class AbstractApiHandler(object):
    """Abstract handler for API requests.

    Attributes:
        path_regex: The regular expression matching paths supported by this
            handler.
    """

    def __init__(self, path_regex):
        if path_regex[-1] != '$':
            path_regex += "$"
        # we only use 'match' so no need to mark the beginning of string
        self.path_regex = path_regex
        self.path_re = re.compile(path_regex)

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.path_re.pattern)

    def _get_context(self, request):
        """Return dict of variables in request path."""
        m = self.path_re.match(request.path)
        # remove all the None values before returning
        return dict([(k, v) for k, v in m.groupdict().items()
                     if v is not None])

    def handles_request(self, request):
        """Return true iff handler supports the request."""
        m = self.path_re.match(request.path)
        return m is not None

    def handle_request(self, request):
        """Handle a REST request.

        Args:
           request: A webob request object.

        Returns:
            A webob response object.
        """
        return NOT_SUPPORTED_RESPONSE


class ElementHandler(AbstractApiHandler):
    """API handler for REST element resources.

    REST elements represent individual entities in the data model, and often
    support the following operations:
        - Read a representation of the element
        - Update (replace) the entire element with a new version
        - Update (patch) parts of the element with new values
        - Delete the element

    Elements may also exhibit 'controller' semantics for RPC-style method
    invocation, however this is not currently supported.
    """

    def __init__(self, path_regex, model,
                 collection_handler=None, allow_read=True, allow_replace=True,
                 allow_update=True, allow_delete=True):
        """Initialize an element handler.

        Args:
            path_regex: A regular expression that matches the full path
                to the element.  If multiple handlers match a request path,
                the handler with the highhest registration search_index wins.
            model: A resource data model instance
            collection_handler: The collection handler this elemeent
                is a member of or None if the element is not a member of a
                collection.  (Used for named creation of elements)
            allow_read: True if element supports read
            allow_replace: True if element supports replace
            allow_update: True if element supports update
            allow_delete: True if element supports delete

        """
        super(ElementHandler, self).__init__(path_regex)
        self.model = model
        self.collection_handler = collection_handler
        self.allow_read = allow_read
        self.allow_replace = allow_replace
        self.allow_update = allow_update
        self.allow_delete = allow_delete

    def _get_element_id(self, request):
        m = self.path_re.match(request.path)
        if m.groups():
            return m.groups()[-1]  # TODO(pballand): make robust
        return None

    def handle_request(self, request):
        """Handle a REST request.

        Args:
           request: A webob request object.

        Returns:
            A webob response object.
        """
        if request.method == 'GET' and self.allow_read:
            return self.read(request)
        #TODO(pballand): POST for controller semantics
        elif request.method == 'PUT' and self.allow_replace:
            return self.replace(request)
        elif request.method == 'PATCH' and self.allow_update:
            return self.update(request)
        elif request.method == 'DELETE' and self.allow_delete:
            return self.delete(request)
        return NOT_SUPPORTED_RESPONSE

    def read(self, request):
        if not hasattr(self.model, 'get_item'):
            return NOT_SUPPORTED_RESPONSE

        id_ = self._get_element_id(request)
        item = self.model.get_item(id_, request.params,
                                   context=self._get_context(request))
        if item is None:
            return error_response(httplib.NOT_FOUND, 404, 'Not found')
        return webob.Response(body="%s\n" % json.dumps(item),
                              status=httplib.OK,
                              content_type='application/json')

    def replace(self, request):
        if not hasattr(self.model, 'update_item'):
            return NOT_SUPPORTED_RESPONSE

        id_ = self._get_element_id(request)
        try:
            item = json.loads(request.body)
            self.model.update_item(id_, item, request.params,
                                   context=self._get_context(request))
        except KeyError:
            if (self.collection_handler and
                    getattr(self.collection_handler, 'allow_named_create',
                            False)):
                return self.collection_handler.create_member(request, id_=id_)
            return error_response(httplib.NOT_FOUND, 404, 'Not found')
        return webob.Response(body="%s\n" % json.dumps(item),
                              status=httplib.OK,
                              content_type='application/json')

    def update(self, request):
        if not (hasattr(self.model, 'update_item') or
                hasattr(self.model, 'get_item')):
            return NOT_SUPPORTED_RESPONSE

        context = self._get_context(request)
        id_ = self._get_element_id(request)
        item = self.model.get_item(id_, request.params, context=context)
        if item is None:
            return error_response(httplib.NOT_FOUND, 404, 'Not found')

        updates = json.loads(request.body)
        item.update(updates)
        self.model.update_item(id_, item, request.params, context=context)
        return webob.Response(body="%s\n" % json.dumps(item),
                              status=httplib.OK,
                              content_type='application/json')

    def delete(self, request):
        if not hasattr(self.model, 'delete_item'):
            return NOT_SUPPORTED_RESPONSE

        id_ = self._get_element_id(request)
        try:
            item = self.model.delete_item(
                id_, request.params, context=self._get_context(request))
            return webob.Response(body="%s\n" % json.dumps(item),
                                  status=httplib.OK,
                                  content_type='application/json')
        except KeyError:
            return error_response(httplib.NOT_FOUND, 404, 'Not found')


class CollectionHandler(AbstractApiHandler):
    """API handler for REST collection resources.

    REST collections represent collections of entities in the data model, and
    often support the following operations:
        - List elements in the collection
        - Create new element in the collection

    The following less-common collection operations are NOT SUPPORTED:
        - Replace all elements in the collection
        - Delete all elements in the collection
    """

    def __init__(self, path_regex, model,
                 allow_named_create=True, allow_list=True, allow_create=True):
        """Initialize a collection handler.

        Args:
            path_regex: A regular expression matching the collection base path.
            model: A resource data model instance
            allow_named_create: True if caller can specify ID of new items.
            allow_list: True if collection supports listing elements.
            allow_create: True if collection supports creating elements.
        """
        super(CollectionHandler, self).__init__(path_regex)
        self.model = model
        self.allow_named_create = allow_named_create
        self.allow_list = allow_list
        self.allow_create = allow_create

    def handle_request(self, request):
        """Handle a REST request.

        Args:
           request: A webob request object.

        Returns:
            A webob response object.
        """
        # NOTE(arosen): only do policy.json if keystone is used for now.
        if cfg.CONF.auth_strategy == "keystone":
            context = request.environ['congress.context']
            target = {
                'project_id': context.project_id,
                'user_id': context.user_id
            }
            # NOTE(arosen): today congress only enforces API policy on which
            # API calls we allow tenants to make with their given roles.
            action_type = self._get_action_type(request.method)
            # FIXME(arosen): There should be a cleaner way to do this.
            model_name = self.path_regex.split('/')[1]
            action = "%s_%s" % (action_type, model_name)
            # TODO(arosen): we should handle serializing the
            # response in one place
            try:
                policy.enforce(context, action, target)
            except exception.PolicyNotAuthorized as e:
                LOG.info(unicode(e))
                return webob.Response(body=unicode(e), status=e.code,
                                      content_type='application/json')
        if request.method == 'GET' and self.allow_list:
            return self.list_members(request)
        elif request.method == 'POST' and self.allow_create:
            return self.create_member(request)
        return NOT_SUPPORTED_RESPONSE

    def _get_action_type(self, method):
        if method == 'GET':
            return 'get'
        elif method == 'POST':
            return 'create'
        elif method == 'DELETE':
            return 'delete'
        elif method == 'PUT' or method == 'PATCH':
            return 'update'
        else:
            # should never get here but just in case ;)
            # FIXME(arosen) raise NotImplemented instead and
            # make sure we return that as an http code.
            raise TypeError("Invalid HTTP Method")

    def list_members(self, request):
        if not hasattr(self.model, 'get_items'):
            return NOT_SUPPORTED_RESPONSE
        items = self.model.get_items(request.params,
                                     context=self._get_context(request))
        if 'results' not in items:
            raise TypeError("Invalid response from data model")
        body = "%s\n" % json.dumps(items, indent=2)
        return webob.Response(body=body, status=httplib.OK,
                              content_type='application/json')

    def create_member(self, request, id_=None):
        if not hasattr(self.model, 'add_item'):
            return NOT_SUPPORTED_RESPONSE
        item = json.loads(request.body)
        try:
            id_, item = self.model.add_item(
                item, id_, request.params, context=self._get_context(request))
        except KeyError:
            return error_response(httplib.CONFLICT, httplib.CONFLICT,
                                  'Element already exists')
        item['id'] = id_

        return webob.Response(body="%s\n" % json.dumps(item),
                              status=httplib.CREATED,
                              content_type='application/json',
                              location="%s/%s" % (request.path, id_))


class SimpleDataModel(object):
    """A container providing access to a single type of data.
    """

    def __init__(self, model_name):
        self.model_name = model_name
        self.items = {}

    @staticmethod
    def _context_str(context):
        context = context or {}
        return ".".join(
            ["%s:%s" % (k, context[k]) for k in sorted(context.keys())])

    def get_items(self, params, context=None):
        """Get items in model.

        Args:
            params: A dict-like object containing parameters
                    from the request query string and body.
            context: Key-values providing frame of reference of request

        Returns: A dict containing at least a 'results' key whose value is
                 a list of items in the model.  Additional keys set in the
                 dict will also be rendered for the user.
        """
        cstr = self._context_str(context)
        results = self.items.setdefault(cstr, {}).values()
        return {'results': results}

    def add_item(self, item, params, id_=None, context=None):
        """Add item to model.

        Args:
            item: The item to add to the model
            params: A dict-like object containing parameters
                    from the request query string and body.
            id_: The ID of the item, or None if an ID should be generated
            context: Key-values providing frame of reference of request

        Returns:
             Tuple of (ID, newly_created_item)

        Raises:
            KeyError: ID already exists.
        """
        cstr = self._context_str(context)
        if id_ is None:
            id_ = str(uuid.uuid4())
        if id_ in self.items.setdefault(cstr, {}):
            raise KeyError("Cannot create item with ID '%s': "
                           "ID already exists")
        self.items[cstr][id_] = item
        return (id_, item)

    def get_item(self, id_, params, context=None):
        """Retrieve item with id id_ from model.

        Args:
            id_: The ID of the item to retrieve
            params: A dict-like object containing parameters
                    from the request query string and body.
            context: Key-values providing frame of reference of request

        Returns:
             The matching item or None if item with id_ does not exist.
        """
        cstr = self._context_str(context)
        return self.items.setdefault(cstr, {}).get(id_)

    def update_item(self, id_, item, params, context=None):
        """Update item with id_ with new data.

        Args:
            id_: The ID of the item to be updated
            item: The new item
            params: A dict-like object containing parameters
                    from the request query string and body.
            context: Key-values providing frame of reference of request

        Returns:
             The updated item.

        Raises:
            KeyError: Item with specified id_ not present.
        """
        cstr = self._context_str(context)
        if id_ not in self.items.setdefault(cstr, {}):
            raise KeyError("Cannot update item with ID '%s': "
                           "ID does not exist" % id_)
        self.items.setdefault(cstr, {})[id_] = item
        return item

    def delete_item(self, id_, params, context=None):
        """Remove item from model.

        Args:
            id_: The ID of the item to be removed
            params: A dict-like object containing parameters
                    from the request query string and body.
            context: Key-values providing frame of reference of request

        Returns:
             The removed item.

        Raises:
            KeyError: Item with specified id_ not present.
        """
        cstr = self._context_str(context)
        ret = self.items.setdefault(cstr, {})[id_]
        del self.items[cstr][id_]
        return ret
