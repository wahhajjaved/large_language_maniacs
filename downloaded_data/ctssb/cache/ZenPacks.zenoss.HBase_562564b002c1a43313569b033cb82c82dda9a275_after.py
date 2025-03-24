######################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is
# installed.
#
######################################################################

from logging import getLogger
log = getLogger('zen.python')

import re
import time
import json
from twisted.web.client import getPage
from twisted.internet import defer

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSourcePlugin
from Products.DataCollector.plugins.DataMaps import ObjectMap

from Products.ZenUtils.Utils import prepId
from ZenPacks.zenoss.HBase import MODULE_NAME, NAME_SPLITTER
from ZenPacks.zenoss.HBase.utils import hbase_rest_url


class HBaseException(Exception):
    pass


class HBaseBasePlugin(PythonDataSourcePlugin):
    """
    Datasource for HBase Device
    and base for components' datasource classes.
    """

    proxy_attributes = (
        'zHBase',
        'zHBaseUsername',
        'zHBasePasword',
        'zHBasePort'
    )

    component = None

    endpoint = '/status/cluster'

    def process(self, result):
        """
        Parses resulting data into datapoints
        """
        data = json.loads(result)

        return {
            'live_servers': (len(data['LiveNodes']), 'N'),
            'dead_servers': (len(data['DeadNodes']), 'N'),
            'requests_per_second': (data['requests'], 'N'),
            'regions': (data['regions'], 'N'),
            'average_load': (data['averageLoad'], 'N'),
        }

    @defer.inlineCallbacks
    def collect(self, config):
        """
        This method return a Twisted deferred. The deferred results will
        be sent to the onResult then either onSuccess or onError callbacks
        below.
        """
        results = self.new_data()
        data = ''
        for ds in config.datasources:
            if ds.zHBase == "false":
                continue

            self.component = ds.component

            url = hbase_rest_url(
                user=ds.zHBaseUsername,
                passwd=ds.zHBasePasword,
                port=ds.zHBasePort,
                host=ds.manageIp,
                endpoint=self.endpoint
            )

            res = yield getPage(url, headers={'Accept': 'application/json'})

            print "==" * 20
            print ds.component
            print res
            if not res:
                raise HBaseException('No monitoring data.')

            results['values'][self.component] = self.process(res)
            print results

            try:
                pass
            except HBaseException, e:
                results['events'].append({
                    'component': ds.component,
                    'summary': str(e),
                    'eventKey': 'hbase_monitoring_error',
                    'eventClass': '/Status',
                    'severity': 5,
                })
        #return results
        defer.returnValue(results)

    def onSuccess(self, result, config):
        """
        This method return a data structure with zero or more events, values
        and maps.  result - is what returned from collect.
        """
        results = {
            'values': result['values'],
            'events': result['events'],
            'maps': []
        }
        for component in result['values'].keys():
            results['events'].append({
                'component': component,
                'summary': 'Monitoring ok',
                'eventKey': 'hbase_monitoring_error',
                'eventClass': '/Status',
                'severity': 0,
            })
        return results

    def onError(self, result, config):
        severity = 4
        data = self.new_data()
        data['events'].append({
            'component': self.component,
            'summary': str(result),
            'eventKey': 'hbase_monitoring_error',
            'eventClass': '/Status',
            'severity': severity,
        })
        return data

class HBaseRegionServerPlugin(HBaseBasePlugin):
    """
    Datasource for HBase Region Server component.
    """

    def process(self, result):
        """
        Parses resulting data into datapoints
        """
        data = json.loads(res)

        for node in data["LiveNodes"]:
            if self.component == prepId(node['name']):
                return {
                    'requests_per_second': (node['requests'], 'N'),
                    'used_heap_mb': (node['heapSizeMB'], 'N'),
                    'max_heap_mb': (node['maxHeapSizeMB'], 'N'),
                    'regions': (len(node['Region']), 'N'),
                }
        return {}
