# -*- encoding: utf-8 -*-
# pylint: disable=missing-docstring, too-few-public-methods

__VERSION__ = '0.1.0'

import abc
import json
import urllib2

import blackbird.plugins


class ConcreteJob(blackbird.plugins.base.JobBase):
    def __init__(self, options, queue, logger):
        super(ConcreteJob, self).__init__(options, queue, logger)
        self.jmx_channel_items = JMXChannelItems()
        self.jmx_sink_items = JMXSinkItems()
        self.jmx_source_items = JMXSourceItems()

    def build_items(self):
        self.__build_ping_item()
        self.__build_items(self.jmx_channel_items)
        self.__build_items(self.jmx_sink_items)
        self.__build_items(self.jmx_source_items)

    def build_discovery_items(self):
        self.__build_discovery_items(self.jmx_channel_items)
        self.__build_discovery_items(self.jmx_sink_items)
        self.__build_discovery_items(self.jmx_source_items)

    def __build_ping_item(self):
        self.__enqueue_item('blackbird.flume_jolokia.ping', 1)
        self.__enqueue_item('blackbird.flume_jolokia.version', __VERSION__)

    def __build_items(self, jmx_items):
        request = self.__request_read(
            jmx_items.mbean_pattern(),
            jmx_items.attributes(),
        )
        result = self.__jolokia(request)

        if result:
            for mbean in result['value'].keys():
                for attribute in jmx_items.attributes():
                    key = jmx_items.zabbix_key(mbean, attribute)
                    clock = result['timestamp']
                    value = result['value'][mbean][attribute]

                    self.__enqueue_item(key, value, clock)


    def __build_discovery_items(self, jmx_items):
        discovery_item_dict = {}
        discovery_item_dict['data'] = []

        request = self.__request_search(jmx_items.mbean_pattern())
        result = self.__jolokia(request)

        if result:
            for mbean in result['value']:
                discovery_item = {}

                _, mbean_properties = mbean.split(':', 1)
                discovery_item['{#MBEAN}'] = mbean_properties

                discovery_item_dict['data'].append(discovery_item)

            key = jmx_items.zabbix_discovery_key()
            value = json.dumps(discovery_item_dict)

            self.__enqueue_item(key, value)

    def __jolokia(self, request):
        try:
            result = urllib2.urlopen(
                url=request,
                timeout=self.options['jolokia_timeout'],
            )
            result_dict = json.load(result)

            if result_dict['status'] == '200':
                return result_dict
            else:
                self.logger.warn('Invalid status code returned from Jolokia.')
                return None
        except urllib2.URLError as url_error:
            self.logger.warn(url_error)
            return None
        except urllib2.HTTPError as http_error:
            self.logger.warn(http_error)
            return None

    def __request_read(self, mbean, attributes):
        request = urllib2.Request(self.__jolokia_url())

        query_dict = {}
        query_dict['type'] = 'read'
        query_dict['mbean'] = mbean
        query_dict['attribute'] = attributes
        query_json = json.dumps(query_dict).encode('utf-8')

        request.add_data(query_json)

        return request

    def __request_search(self, mbean):
        request = urllib2.Request(self.__jolokia_url())

        query_dict = {}
        query_dict['type'] = 'search'
        query_dict['mbean'] = mbean
        query_json = json.dumps(query_dict).encode('utf-8')

        request.add_data(query_json)

        return request

    def __jolokia_url(self):
        jolokia_url = 'http://{0}:{1}{2}/'.format(
            self.options['jolokia_host'],
            self.options['jolokia_port'],
            self.options['jolokia_context'],
        )

        return jolokia_url

    def __enqueue_item(self, key, value, clock=None):
        host = self.options['zabbix_hostname']

        item = FlumeItem(host, key, value, clock)

        self.queue.put(item, block=False)
        self.logger.debug(item)


class FlumeItem(blackbird.plugins.base.ItemBase):
    def __init__(self, host, key, value, clock=None):
        super(FlumeItem, self).__init__(key, value, host, clock)
        self.__data = {}
        self.__generate()

    @property
    def data(self):
        return self.__data

    def __generate(self):
        self.__data['host'] = self.host
        self.__data['key'] = self.key
        self.__data['clock'] = int(self.clock)

        if isinstance(self.value, float):
            self.__data['value'] = round(self.value, 6)
        else:
            self.__data['value'] = self.value

    def __str__(self):
        return str(self.__data)

    def __repr__(self):
        return repr(self.__data)


class Validator(blackbird.plugins.base.ValidatorBase):
    def __init__(self):
        self.__spec = (
            '[{0}]'.format(__name__),
            'zabbix_hostname = string(default={0})'.format(
                self.detect_hostname()
            ),
            'jolokia_host = string(default="localhost")',
            'jolokia_port = integer(0, 65535)',
            'jolokia_context = string(default="/jolokia")',
            'jolokia_timeout = integer(default=10)',
        )

    @property
    def spec(self):
        return self.__spec


class JMXItemsBase(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def _mbean_pattern(self):
        return 'Abstract Property.'

    @abc.abstractproperty
    def _attributes(self):
        return 'Abstract Property.'

    @abc.abstractproperty
    def _zabbix_key(self):
        return 'Abstract Property.'

    @abc.abstractproperty
    def _zabbix_discovery_key(self):
        return 'Abstract Property.'

    def __init__(self):
        pass

    def mbean_pattern(self):
        return self._mbean_pattern

    def attributes(self):
        return self._attributes

    def zabbix_key(self, mbean, attribute):
        _, mbean_properties = mbean.split(':', 1)
        return self._zabbix_key.format(mbean_properties, attribute)

    def zabbix_discovery_key(self):
        return self._zabbix_discovery_key


class JMXChannelItems(JMXItemsBase):
    @property
    def _mbean_pattern(self):
        return 'org.apache.flume.channel:*'

    @property
    def _attributes(self):
        return [
            'ChannelCapacity',
            'ChannelFillPercentage',
            'ChannelSize',
            'EventPutAttemptCount',
            'EventPutSuccessCount',
            'EventTakeAttemptCount',
            'EventTakeSuccessCount',
            'StartTime',
            'StopTime',
        ]

    @property
    def _zabbix_key(self):
        return 'flume.channel[{0},{1}]'

    @property
    def _zabbix_discovery_key(self):
        return 'flume.channel.discovery'


class JMXSinkItems(JMXItemsBase):
    @property
    def _mbean_pattern(self):
        return 'org.apache.flume.sink:*'

    @property
    def _attributes(self):
        return [
            'BatchCompleteCount',
            'BatchEmptyCount',
            'BatchUnderflowCount',
            'ConnectionClosedCount',
            'ConnectionCreatedCount',
            'ConnectionFailedCount',
            'EventDrainAttemptCount',
            'EventDrainSuccessCount',
            'StartTime',
            'StopTime',
        ]

    @property
    def _zabbix_key(self):
        return 'flume.sink[{0},{1}]'

    @property
    def _zabbix_discovery_key(self):
        return 'flume.sink.discovery'


class JMXSourceItems(JMXItemsBase):
    @property
    def _mbean_pattern(self):
        return 'org.apache.flume.source:*'

    @property
    def _attributes(self):
        return [
            'AppendAcceptedCount',
            'AppendBatchAcceptedCount',
            'AppendBatchReceivedCount',
            'AppendReceivedCount',
            'EventAcceptedCount',
            'EventReceivedCount',
            'OpenConnectionCount',
            'StartTime',
            'StopTime',
        ]

    @property
    def _zabbix_key(self):
        return 'flume.source[{0},{1}]'

    @property
    def _zabbix_discovery_key(self):
        return 'flume.source.discovery'
