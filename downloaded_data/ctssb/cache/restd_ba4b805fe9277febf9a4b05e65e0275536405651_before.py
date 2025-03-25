# Copyright (C) 2015 Hewlett Packard Enterprise Development LP
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

from tornado.ioloop import IOLoop
from tornado import web, gen, locks
from tornado.log import app_log

import json
import httplib
import re

from opsrest.resource import Resource
from opsrest.parse import parse_url_path
from opsrest.constants import *
from opsrest.utils.utils import *
from opsrest import get, post, delete, put

import userauth
from opsrest.settings import settings


class BaseHandler(web.RequestHandler):

    # pass the application reference to the handlers
    def initialize(self, ref_object):
        self.ref_object = ref_object
        self.schema = self.ref_object.restschema
        self.idl = self.ref_object.manager.idl
        self.request.path = re.sub("/{2,}", "/", self.request.path)

    def set_default_headers(self):
        # CORS
        allow_origin = self.request.protocol + "://"
        # removing port if present
        allow_origin += self.request.host.split(":")[0]
        self.set_header("Cache-control", "no-cache")
        self.set_header("Access-Control-Allow-Origin", allow_origin)
        self.set_header("Access-Control-Allow-Credentials", "true")
        self.set_header("Access-Control-Expose-Headers", "Date")

        # TODO - remove next line before release - needed for testing
        if HTTP_HEADER_ORIGIN in self.request.headers:
            self.set_header("Access-Control-Allow-Origin",
                            self.request.headers[HTTP_HEADER_ORIGIN])


class LoginHandler(BaseHandler):

    # pass the application reference to the handlers
    def initialize(self, ref_object):
        pass

    @gen.coroutine
    def get(self):

        is_authenticated = userauth.is_user_authenticated(self)
        if not is_authenticated:
            self.set_status(httplib.UNAUTHORIZED)
            self.set_header("Link", "/login")
        else:
            self.set_status(httplib.OK)

        self.finish()

    @gen.coroutine
    def post(self):

        login_success = userauth.handle_user_login(self)
        if not login_success:
            self.set_status(httplib.UNAUTHORIZED)
            self.set_header("Link", "/login")
        else:
            self.set_status(httplib.OK)

        self.finish()


class AutoHandler(BaseHandler):

    # parse the url and http params.
    def prepare(self):

        app_log.debug("Incoming request from %s: %s",
                      self.request.remote_ip,
                      self.request)

        if settings['auth_enabled'] and self.request.method != "OPTIONS":
            is_authenticated = userauth.is_user_authenticated(self)
        else:
            is_authenticated = True

        if not is_authenticated:
            self.set_status(httplib.UNAUTHORIZED)
            self.set_header("Link", "/login")
            self.finish()
        else:
            self.resource_path = parse_url_path(self.request.path,
                                                self.schema,
                                                self.idl,
                                                self.request.method)

            if self.resource_path is None:
                self.set_status(httplib.NOT_FOUND)
                self.finish()

    def on_finish(self):
        app_log.debug("Finished handling of request from %s",
                      self.request.remote_ip)

    @gen.coroutine
    def options(self):

        resource = self.resource_path
        while resource.next is not None:
            resource = resource.next

        allowed_methods = ', '.join(resource.get_allowed_methods(self.schema))

        self.set_header(HTTP_HEADER_ALLOW, allowed_methods)
        self.set_header(HTTP_HEADER_ACCESS_CONTROL_ALLOW_METHODS,
                        allowed_methods)

        if HTTP_HEADER_ACCESS_CONTROL_REQUEST_HEADERS in self.request.headers:
            header_ = HTTP_HEADER_ACCESS_CONTROL_REQUEST_HEADERS
            self.set_header(HTTP_HEADER_ACCESS_CONTROL_ALLOW_HEADERS,
                            self.request.headers[header_])

        self.set_status(httplib.OK)
        self.finish()

    @gen.coroutine
    def get(self):

        selector = self.get_query_argument(REST_QUERY_PARAM_SELECTOR, None)

        result = get.get_resource(self.idl, self.resource_path,
                                  self.schema, self.request.path,
                                  selector)

        if result is None:
            self.set_status(httplib.NOT_FOUND)
        else:
            self.set_status(httplib.OK)
            self.set_header(HTTP_HEADER_CONTENT_TYPE, HTTP_CONTENT_TYPE_JSON)
            self.write(json.dumps(result))

        self.finish()

    @gen.coroutine
    def post(self):

        if HTTP_HEADER_CONTENT_LENGTH in self.request.headers:
            try:
                # get the POST body
                post_data = json.loads(self.request.body)

                # create a new ovsdb transaction
                self.txn = self.ref_object.manager.get_new_transaction()

                # post_resource performs data verficiation, prepares and
                #commits the ovsdb transaction
                result = post.post_resource(post_data, self.resource_path,
                                            self.schema, self.txn,
                                            self.idl)

                if result == INCOMPLETE:
                    self.ref_object.manager.monitor_transaction(self.txn)
                    # on 'incomplete' state we wait until the transaction
                    #completes with either success or failure
                    yield self.txn.event.wait()
                    result = self.txn.status

                app_log.debug("POST operation result: %s", result)
                if self.successful_transaction(result):
                    self.set_status(httplib.CREATED)

            except ValueError, e:
                self.set_status(httplib.BAD_REQUEST)
                self.set_header(HTTP_HEADER_CONTENT_TYPE,
                                HTTP_CONTENT_TYPE_JSON)
                self.write(to_json_error(e))

            # TODO: Improve exception handler
            except Exception, e:
                app_log.debug("Unexpected exception: %s", e)

                self.txn.abort()
                self.set_status(httplib.INTERNAL_SERVER_ERROR)

        else:
            self.set_status(httplib.LENGTH_REQUIRED)

        self.finish()

    @gen.coroutine
    def put(self):

        if HTTP_HEADER_CONTENT_LENGTH in self.request.headers:
            try:
                # get the PUT body
                update_data = json.loads(self.request.body)

                # create a new ovsdb transaction
                self.txn = self.ref_object.manager.get_new_transaction()

                # put_resource performs data verficiation, prepares and
                #commits the ovsdb transaction
                result = put.put_resource(update_data, self.resource_path,
                                          self.schema, self.txn, self.idl)

                if result == INCOMPLETE:
                    self.ref_object.manager.monitor_transaction(self.txn)
                    # on 'incomplete' state we wait until the transaction
                    # completes with either success or failure
                    yield self.txn.event.wait()
                    result = self.txn.status

                app_log.debug("PUT operation result: %s", result)
                if self.successful_transaction(result):
                    self.set_status(httplib.OK)

            except ValueError, e:
                self.set_status(httplib.BAD_REQUEST)
                self.set_header(HTTP_HEADER_CONTENT_TYPE,
                                HTTP_CONTENT_TYPE_JSON)
                self.write(to_json_error(e))

            # TODO: Improve exception handler
            except Exception, e:
                app_log.debug("Unexpected exception: %s", e)

                self.txn.abort()
                self.set_status(httplib.INTERNAL_SERVER_ERROR)

        else:
            self.set_status(httplib.LENGTH_REQUIRED)

        self.finish()

    @gen.coroutine
    def delete(self):

        try:
            self.txn = self.ref_object.manager.get_new_transaction()

            result = delete.delete_resource(self.resource_path, self.schema,
                                            self.txn, self.idl)

            if result == INCOMPLETE:
                self.ref_object.manager.monitor_transaction(self.txn)
                # on 'incomplete' state we wait until the transaction
                #completes with either success or failure
                yield self.txn.event.wait()
                result = self.txn.status

            app_log.debug("DELETE operation result: %s", result)
            if self.successful_transaction(result):
                app_log.debug("Successful transaction!")
                self.set_status(httplib.NO_CONTENT)

        except Exception, e:
            if isinstance(e.message, dict):
                self.set_status(e.message.get('status',
                                              httplib.INTERNAL_SERVER_ERROR))
            else:
                app_log.debug("Unexpected exception: %s", e.message)
                self.set_status(httplib.INTERNAL_SERVER_ERROR)

            self.txn.abort()

        self.finish()

    def successful_transaction(self, result):

        if result == SUCCESS or result == UNCHANGED:
            return True

        self.txn.abort()

        if result == ERROR:
            self.set_status(httplib.BAD_REQUEST)
            self.set_header(HTTP_HEADER_CONTENT_TYPE, HTTP_CONTENT_TYPE_JSON)
            self.write(to_json_error(self.txn.get_db_error_msg()))

        elif ERROR in result:
            self.set_status(httplib.BAD_REQUEST)
            self.set_header(HTTP_HEADER_CONTENT_TYPE, HTTP_CONTENT_TYPE_JSON)
            self.write(to_json(result))

        else:
            self.set_status(httplib.INTERNAL_SERVER_ERROR)

        return False
