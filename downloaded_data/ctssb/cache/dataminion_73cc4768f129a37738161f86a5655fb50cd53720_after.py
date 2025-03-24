import pika
import time

import logging
import sys

import cStringIO
import csv
import re
from datetime import datetime

class Filter(object):
    def __init__(self, config={}, logger=None, on_filter=None, coordinator=None, **kwargs):
        log = logging.getLogger(__name__)
        self.logger = logger or log
        self._configuration = config
        self._coordinator = coordinator
        self._on_filter = on_filter
        self._mem = {}
        self._initialize()

    def process(self, data):
        if self._on_filter and hasattr(self._on_filter, '__call__'):
            self.logger.debug("Filter has data: %s", data)
            self._on_filter(data)

    def get_memory(self, key):
        if key in self._mem:
            return self._mem[key]
        return None

    def set_memory(self, key, data):
        self.logger.info("Setting %s with data: %s", key, data)
        self._mem[key] = data

    def send_data(self, data):
        if self._on_filter and hasattr(self._on_filter, '__call__'):
            self.logger.debug("Filter has data ready: %s", data)
            self._on_filter(data)

class Harbour(Filter):
    def _initialize(self):
        self._required_fields = ('sourcetype', 'serviceid')
        self.logger.info("Filter initialized")

    def process(self, data):
        for key in self._required_fields:
            if key not in data:
                return None
        if data["sourcetype"] == "graphite":
            document = {}
            document["sourcetype"] = data["sourcetype"]
            document["serviceid"] = data["serviceid"]
            components = data["message"].split(" ")
            metric_composite = components[0]
            value = components[1]
            timestamp = components[2]
            if len(components) > 2:
                for i in range(3, len(components)):
                    (key, val) = components[i].split("=")
                    document[key] = val
            document["@timestamp"] = datetime.utcfromtimestamp(float(timestamp)).strftime('%Y-%m-%dT%H:%M:%S.%f+0000')
            metric_parts = metric_composite.split(".") 
            document["hostname"] = metric_parts[0]
            document["metric_name"] = ".".join(metric_parts[1:])
            try:
                value = float(value)
                document["metric_value"] = value
            except:
                document["metric_string"] = value
            self.send_data(document)
        else:
            self.logger.debug("Discarding data: %s", data)
            return None
        return None
        if self._on_filter and hasattr(self._on_filter, '__call__'):
            self.logger.debug("Filter has data: %s", data)
            self._on_filter(data)
