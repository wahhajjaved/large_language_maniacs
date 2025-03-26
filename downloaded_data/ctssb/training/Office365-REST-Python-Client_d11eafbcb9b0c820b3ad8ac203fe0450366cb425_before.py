import requests

from office365.runtime.action_type import ActionType
from office365.runtime.client_object_collection import ClientObjectCollection
from office365.runtime.odata.json_light_format import JsonLightFormat
from office365.runtime.utilities.http_method import HttpMethod
from office365.runtime.utilities.request_options import RequestOptions
from requests import HTTPError, RequestException


class ClientRequestException(RequestException):
    def __init__(self, *args, **kwargs):
        super(ClientRequestException, self).__init__(*args, **kwargs)
        self.content = self.response.json()
        args = (self.code, self.message) + args
        self.args = args

    @property
    def code(self):
        error = self.content.get('error')
        if error:
            return error.get('code')

    @property
    def message_lang(self):
        error = self.content.get('error')
        if error:
            message = error.get('message')
            if isinstance(message, dict):
                return message.get('lang')

    @property
    def message(self):
        error = self.content.get('error')
        if error:
            message = error.get('message')
            if isinstance(message, dict):
                return message.get('value')
            return message


class ClientRequest(object):
    """Client request for SharePoint ODATA/REST service"""

    def __init__(self, context):
        self.context = context
        self.__queries = []
        self.__resultObjects = {}

    def clear(self):
        self.__queries = []
        self.__resultObjects = {}

    def execute_query(self):
        """Submit pending request to the server"""
        try:
            for qry in self.__queries:
                request = self.build_request(qry)
                payload = self.execute_query_direct(request)
                self.process_payload_json(qry, payload)
        finally:
            self.clear()

    def process_payload_json(self, query, response):
        if not response.content:
            return

        payload = response.json()
        "verify for any errors"
        try:
            response.raise_for_status()
        except HTTPError as e:
            raise ClientRequestException(*e.args, response=e.response)

        if any(payload) and query in self.__resultObjects:
            result_object = self.__resultObjects[query]
            json_format = self.context.json_format
            if isinstance(json_format, JsonLightFormat):
                if json_format.payload_root_entry:
                    payload = payload[json_format.payload_root_entry]
                if isinstance(result_object, ClientObjectCollection) \
                        and json_format.payload_root_entry_collection:
                    payload = payload[json_format.payload_root_entry_collection]
            else:
                if isinstance(result_object, ClientObjectCollection):
                    payload = payload[json_format.payload_root_entry_collection]
            result_object.from_json(payload)

    def build_request(self, query):
        request = RequestOptions(query.url)
        "set json format headers"
        request.set_headers(self.context.json_format.build_http_headers())
        if isinstance(self.context.json_format, JsonLightFormat):
            "set custom method headers"
            if query.action_type == ActionType.DeleteEntry:
                request.set_header("X-HTTP-Method", "DELETE")
                request.set_header("IF-MATCH", '*')
            elif query.action_type == ActionType.UpdateEntry:
                request.set_header("X-HTTP-Method", "MERGE")
                request.set_header("IF-MATCH", '*')
            "set method"
            if not (query.action_type == ActionType.ReadEntry or query.action_type == ActionType.GetMethod):
                request.method = HttpMethod.Post
        else:
            if query.action_type == ActionType.CreateEntry:
                request.method = HttpMethod.Post
            elif query.action_type == ActionType.UpdateEntry:
                request.method = HttpMethod.Patch
            elif query.action_type == ActionType.DeleteEntry:
                request.method = HttpMethod.Delete
        "set request payload"
        request.data = query.payload
        return request

    def execute_query_direct(self, request_options):
        """Execute client request"""
        self.context.authenticate_request(request_options)
        if request_options.method == HttpMethod.Post:
            from office365.sharepoint.client_context import ClientContext
            if isinstance(self.context, ClientContext):
                self.context.ensure_form_digest(request_options)
            if hasattr(request_options.data, 'decode') and callable(request_options.data.decode):
                result = requests.post(url=request_options.url,
                                       headers=request_options.headers,
                                       data=request_options.data,
                                       auth=request_options.auth)
            else:
                result = requests.post(url=request_options.url,
                                       headers=request_options.headers,
                                       json=request_options.data,
                                       auth=request_options.auth)
        elif request_options.method == HttpMethod.Patch:
            result = requests.patch(url=request_options.url,
                                    headers=request_options.headers,
                                    json=request_options.data,
                                    auth=request_options.auth)
        elif request_options.method == HttpMethod.Delete:
            result = requests.delete(url=request_options.url,
                                     headers=request_options.headers,
                                     auth=request_options.auth)
        else:
            result = requests.get(url=request_options.url,
                                  headers=request_options.headers,
                                  auth=request_options.auth)
        return result

    def add_query(self, query, result_object=None):
        self.__queries.append(query)
        if result_object is not None:
            self.__resultObjects[query] = result_object
