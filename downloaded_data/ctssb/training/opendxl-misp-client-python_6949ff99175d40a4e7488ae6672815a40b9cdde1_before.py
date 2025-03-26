from __future__ import absolute_import
import copy
import json
import os
import re
import sys
from tempfile import NamedTemporaryFile
import unittest

if sys.version_info[0] > 2:
    import builtins  # pylint: disable=import-error, unused-import
else:
    import __builtin__  # pylint: disable=import-error

    builtins = __builtin__  # pylint: disable=invalid-name

try:
    from configparser import ConfigParser
except ImportError:
    from ConfigParser import ConfigParser

# pylint: disable=wrong-import-position
from mock import patch
import requests_mock
import dxlmispservice


class StringMatches(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def __eq__(self, other):
        return re.match(self.pattern, other, re.DOTALL)


class StringDoesNotMatch(object):
    def __init__(self, pattern):
        self.pattern = pattern

    def __eq__(self, other):
        return not re.match(self.pattern, other)


class Sample(unittest.TestCase):
    _TEST_HOSTNAME = "127.0.0.1"
    _TEST_API_KEY = "myspecialkey"
    _TEST_API_PORT = "443"
    _TEST_API_NAMES = \
        "new_event,search,add_internal_comment,add_named_attribute,tag,sighting"

    def get_api_endpoint(self, path):
        return "https://" + self._TEST_HOSTNAME + ":" + self._TEST_API_PORT + \
               "/" + path

    @staticmethod
    def expected_print_output(title, detail):
        json_string = title + json.dumps(detail, sort_keys=True,
                                         separators=(".*", ": "))
        return re.sub(r"(\.\*)+", ".*",
                      re.sub(r"[{[\]}]", ".*", json_string))

    @staticmethod
    def _run_sample(app, sample_file):
        app.run()
        with open(sample_file) as f, \
                patch.object(builtins, 'print') as mock_print:
            sample_globals = {"__file__": sample_file}
            exec(f.read(), sample_globals)  # pylint: disable=exec-used
        return mock_print

    def run_sample(self, sample_file, add_request_mocks_fn=None):
        with dxlmispservice.MispService("sample") as app:
            config = ConfigParser()
            config.read(app._app_config_path)

            if not config.has_section(
                    dxlmispservice.MispService._GENERAL_CONFIG_SECTION):
                config.add_section(
                    dxlmispservice.MispService._GENERAL_CONFIG_SECTION)

            use_mock_requests = not config.has_option(
                dxlmispservice.MispService._GENERAL_CONFIG_SECTION,
                dxlmispservice.MispService._GENERAL_API_KEY_CONFIG_PROP
            ) or not config.get(
                dxlmispservice.MispService._GENERAL_CONFIG_SECTION,
                dxlmispservice.MispService._GENERAL_API_KEY_CONFIG_PROP
            )

            if use_mock_requests:
                config.set(
                    dxlmispservice.MispService._GENERAL_CONFIG_SECTION,
                    dxlmispservice.MispService._GENERAL_HOST_CONFIG_PROP,
                    self._TEST_HOSTNAME
                )
                config.set(
                    dxlmispservice.MispService._GENERAL_CONFIG_SECTION,
                    dxlmispservice.MispService._GENERAL_API_KEY_CONFIG_PROP,
                    self._TEST_API_KEY
                )

            config.set(
                dxlmispservice.MispService._GENERAL_CONFIG_SECTION,
                dxlmispservice.MispService._GENERAL_API_NAMES_CONFIG_PROP,
                self._TEST_API_NAMES
            )
            with NamedTemporaryFile(mode="w+", delete=False) \
                as temp_config_file:
                config.write(temp_config_file)
            try:
                app._app_config_path = temp_config_file.name

                if use_mock_requests:
                    with requests_mock.mock(case_sensitive=True) as req_mock:
                        req_mock.get(
                            self.get_api_endpoint("servers/getPyMISPVersion.json"),
                            text='{"version":"1.2.3"}')
                        types_result = {
                            "result":
                                {
                                    "categories": [
                                        "Internal reference",
                                        "Other"
                                    ],
                                    "sane_defaults":
                                        {"comment": {
                                            "default_category": "Other",
                                            "to_ids": 0
                                        }},
                                    "types": ["comment"],
                                    "category_type_mappings": {
                                        "Internal reference": ["comment"],
                                        "Other": ["comment"]
                                    }
                                }
                        }
                        req_mock.get(
                            self.get_api_endpoint("attributes/describeTypes.json"),
                            text=json.dumps(types_result))

                        if add_request_mocks_fn:
                            add_request_mocks_fn(req_mock)
                        mock_print = self._run_sample(app, sample_file)
                else:
                    mock_print = self._run_sample(app, sample_file)
                    req_mock = None
            finally:
                os.remove(temp_config_file.name)
        return (mock_print, req_mock)

    def test_basic_new_event_example(self):
        mock_event_id = "123456"
        expected_event_detail = {
            "Event": {
                "distribution": "3",
                "info": "OpenDXL MISP new event example",
                "analysis": "1",
                "published": False,
                "threat_level_id": "3"
            }}

        def add_request_mocks(req_mock):
            event_detail_with_id = copy.deepcopy(expected_event_detail)
            event_detail_with_id["Event"]["id"] = mock_event_id
            req_mock.post(self.get_api_endpoint("events"),
                          text=json.dumps(event_detail_with_id))
            event_response_data = {"response": event_detail_with_id}
            req_mock.post(self.get_api_endpoint("events/restSearch/download"),
                          text=json.dumps(event_response_data))

        mock_print, req_mock = self.run_sample(
            "sample/basic/basic_new_event_example.py",
            add_request_mocks
        )

        if req_mock:
            request_count = len(req_mock.request_history)
            self.assertGreater(request_count, 1)

            new_event_request = req_mock.request_history[request_count - 2]
            self.assertEqual({
                "Event": {
                    "distribution": "3",
                    "info": "OpenDXL MISP new event example",
                    "analysis": "1",
                    "published": False,
                    "threat_level_id": "3"
                }}, new_event_request.json())

            search_request = req_mock.request_history[request_count - 1]
            self.assertEqual(self._TEST_API_KEY,
                             search_request.headers["Authorization"])
            self.assertEqual({"eventid": mock_event_id}, search_request.json())

        mock_print.assert_any_call(
            StringMatches(
                self.expected_print_output(
                    "Response to the new event request:", expected_event_detail)
            )
        )
        mock_print.assert_any_call(
            StringMatches(
                self.expected_print_output(
                    "Response to the search request for the new MISP event:.*",
                    expected_event_detail
                )
            )
        )
        mock_print.assert_any_call(StringDoesNotMatch("Error invoking request"))

    def test_basic_update_event_example(self):
        mock_event_id = "123456"
        expected_event_detail = {
            "Event": {
                "distribution": "3",
                "info": "OpenDXL MISP update event example",
                "analysis": "1",
                "published": False,
                "threat_level_id": "3"
            }}
        mock_attribute_uuid = ["79e88e45-09eb-4f9b-ba46-c2c850b5eb03"]
        expected_attribute_detail = {
            "category": "Internal reference",
            "value": "Added by the OpenDXL MISP update event example",
            "comment": "This is only a test",
            "type": "comment",
            "to_ids": False,
            "disable_correlation": False
        }
        expected_tag_name = "Tagged by the OpenDXL MISP update event example"
        expected_event_after_update = {
            "Event": {
                "Attribute": [
                    {
                        "Sighting": [
                            {
                                "source": "Seen by the OpenDXL MISP update event example",
                                "type": "0"
                            }
                        ],
                        "Tag": [
                            {
                                "name": "Tagged by the OpenDXL MISP update event example"
                            }
                        ]
                    }
                ]
            }
        }

        def add_attribute_callback(request, context):
            context.status_code = 200
            requested_attribute_uuid = request.json()[0].get("uuid", None)
            # PyMISP started generating a client side random uuid for newly
            # created attributes in 2.4.90.1. The logic below allows the client
            # generated uuid to be returned in the mock response only if
            # present. For earlier PyMISP versions, the default test uuid
            # assigned to mock_attribute_uuid[0] will be used.
            if requested_attribute_uuid:
                mock_attribute_uuid[0] = requested_attribute_uuid
            expected_attribute_detail_with_id = expected_attribute_detail.copy()
            expected_attribute_detail_with_id["uuid"] = mock_attribute_uuid[0]
            return json.dumps({"Attribute": expected_attribute_detail_with_id})

        def add_request_mocks(req_mock):
            event_detail_with_id = copy.deepcopy(expected_event_detail)
            event_detail_with_id["Event"]["id"] = mock_event_id
            req_mock.post(self.get_api_endpoint("events"),
                          text=json.dumps(event_detail_with_id))
            req_mock.post(
                self.get_api_endpoint("attributes/add/" + mock_event_id),
                text=add_attribute_callback)
            req_mock.post(self.get_api_endpoint("tags/attachTagToObject"),
                          text='{"name": "Tag ' + expected_tag_name + '"}')
            req_mock.post(self.get_api_endpoint("sightings/add/"),
                          text='{"message": "1 sighting successfuly added"}')
            req_mock.post(self.get_api_endpoint("events/restSearch/download"),
                          text=json.dumps(expected_event_after_update))

        mock_print, req_mock = self.run_sample(
            "sample/basic/basic_update_event_example.py",
            add_request_mocks
        )

        expected_attribute_uuid = mock_attribute_uuid[0]

        if req_mock:
            request_count = len(req_mock.request_history)
            self.assertGreater(request_count, 4)

            attribute_request = req_mock.request_history[request_count - 4]
            attribute_request_json = attribute_request.json()
            # PyMISP started generating a client side random uuid for newly
            # created attributes in 2.4.90.1. The logic below allows the client
            # generated uuid to be ignored if not present, allowing the
            # assertion to pass on earlier PyMISP versions.
            requested_attribute_uuid = attribute_request_json[0].get(
                "uuid", None)
            if requested_attribute_uuid:
                expected_attribute_detail_with_id = \
                    expected_attribute_detail.copy()
                expected_attribute_detail_with_id["uuid"] = \
                    expected_attribute_uuid
                expected_attribute_request_json = \
                    [expected_attribute_detail_with_id]
            else:
                expected_attribute_request_json = [expected_attribute_detail]
            self.assertEqual(expected_attribute_request_json,
                             attribute_request_json)

            tag_request = req_mock.request_history[request_count - 3]
            self.assertEqual({
                "uuid": expected_attribute_uuid,
                "tag": expected_tag_name
            }, tag_request.json())

            sighting_request = req_mock.request_history[request_count - 2]
            self.assertEqual({
                "source": "Seen by the OpenDXL MISP update event example",
                "type": 0,
                "uuid": expected_attribute_uuid
            }, sighting_request.json())

            search_request = req_mock.request_history[request_count - 1]
            self.assertEqual(self._TEST_API_KEY,
                             search_request.headers["Authorization"])
            self.assertEqual({"eventid": mock_event_id}, search_request.json())

        mock_print.assert_any_call(
            StringMatches(
                self.expected_print_output(
                    "Response to the new event request:",
                    expected_event_detail)
            )
        )
        mock_print.assert_any_call(
            StringMatches(
                self.expected_print_output(
                    "Response to the add internal comment request:",
                    {"Attribute": expected_attribute_detail})
            )
        )
        mock_print.assert_any_call(
            StringMatches(
                'Response to the tag request:.*name": "Tag ' + expected_tag_name
            )
        )
        mock_print.assert_any_call(
            StringMatches(
                'Response to the sighting request:.*message": "' +
                "1 sighting successfuly added"
            )
        )
        mock_print.assert_any_call(
            StringMatches(
                self.expected_print_output(
                    "Response to the search request for the new MISP event:",
                    expected_event_after_update)
            )
        )

        mock_print.assert_any_call(StringDoesNotMatch("Error invoking request"))
