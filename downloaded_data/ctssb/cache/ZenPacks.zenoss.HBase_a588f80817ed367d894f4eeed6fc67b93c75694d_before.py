######################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is
# installed.
#
######################################################################

import json

from logging import getLogger

from twisted.web.client import getPage
from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap
from Products.ZenEvents import ZenEventClasses
from Products.ZenUtils.Utils import prepId, convToUnits
from ZenPacks.zenoss.HBase import MODULE_NAME, NAME_SPLITTER
from ZenPacks.zenoss.HBase.dsplugins.base_plugin import (
    HBaseBasePlugin, sum_perf_metrics
)
from ZenPacks.zenoss.HBase.utils import (
    hbase_rest_url, hbase_headers, dead_node_name, version_diff,
    ConfWrapper, HBaseException, check_error
)

log = getLogger('zen.HBasePlugins')


class HBaseRegionServerPlugin(HBaseBasePlugin):
    """
    Datasource plugin for HBase Region Server component.
    """

    def process(self, result):
        """
        Parses resulting data into datapoints.
        """
        data = json.loads(result)

        for node in version_diff(data["LiveNodes"]):
            if self.component == prepId(node['name']):
                res = {
                    'requests_per_second': (node['requests'], 'N'),
                    'used_heap_mb': (node['heapSizeMB'], 'N'),
                    'max_heap_mb': (node['maxHeapSizeMB'], 'N'),
                    'regions': (len(node['Region']), 'N'),
                    'read_requests': (0, 'N'),
                    'write_requests': (0, 'N'),
                    'number_of_stores': (0, 'N'),
                    'number_of_store_files': (0, 'N'),
                    'store_file_size_mb': (0, 'N'),
                    'store_file_index_size_mb': (0, 'N'),
                    'memstore_size_mb': (0, 'N'),
                    'current_compacted_kv': (0, 'N'),
                    'total_compacting_kv': (0, 'N'),
                }
                for region in node["Region"]:
                    res = sum_perf_metrics(res, region)
                return res
        return {}

    def get_events(self, result, ds):
        """
        Return a list of event dictionaries informing about the health
        of the region server.
        """
        data = json.loads(result)
        # Check for dead servers.
        dead_nodes = [prepId(dead_node_name(node)[0]) for node
                      in version_diff(data["DeadNodes"])]
        # Send error or clear event.
        severity = ((self.component in dead_nodes) and ZenEventClasses.Error
                    or ZenEventClasses.Clear)
        return [{
            'component': self.component,
            'summary': "Region server '{0}' is dead".format(
                self.component.replace('_', ':')),
            'eventKey': 'hbase_regionserver_monitoring_error',
            'eventClass': '/Status',
            'severity': severity
        }]


class HBaseRegionServerConfPlugin(HBaseBasePlugin):
    """
    Datasource plugin for Region Server and Region
    components' config properties remodeling.
    """

    proxy_attributes = HBaseBasePlugin.proxy_attributes + (
        'region_ids',
        'title',
        'zHBaseRegionServerPort',
    )

    @defer.inlineCallbacks
    def collect(self, config):
        """
        This method overrides the HBaseBasePlugin.collect method.
        """
        results = self.new_data()
        for ds in config.datasources:
            self.component = ds.component
            headers = hbase_headers(
                accept='application/json',
                username=ds.zHBaseUsername,
                passwd=ds.zHBasePassword
            )
            url = hbase_rest_url(
                scheme=ds.zHBaseScheme,
                port=ds.zHBaseRegionServerPort,
                host=get_host(ds),
                endpoint='/dump'
            )
            try:
                res = yield getPage(url, headers=headers)
                if not res:
                    raise HBaseException('No monitoring data')
                results['maps'].extend(self.add_maps(res, ds))
            except (Exception, HBaseException), e:
                e = check_error(e, ds.device) or e
                log.error("No access to page '{}': {}".format(url, e))
        defer.returnValue(results)

    def add_maps(self, result, ds):
        """
        Return a list of ObjectMaps with config properties updates
        for this regionserver and all it's regions.
        """
        oms = []
        conf = ConfWrapper(result)
        oms.append(ObjectMap({
            "compname": "hbase_servers/{}".format(self.component),
            "modname": "Region Server conf",
            'handler_count': conf.handler_count,
            'memstore_upper_limit': conf.memstore_upper_limit,
            'memstore_lower_limit': conf.memstore_lower_limit,
            'logflush_interval': conf.logflush_interval
        }))
        # All the regions within the region server will have the same
        # configuration as set in the region server's conf file.
        for region in ds.region_ids:
            oms.append(ObjectMap({
                "compname": "hbase_servers/{}/regions/{}{}{}".format(
                    ds.component, ds.component, NAME_SPLITTER, prepId(region)),
                "modname": "Region conf",
                'memstore_flush_size': convToUnits(conf.memestore_flush_size),
                'max_file_size': convToUnits(conf.max_file_size)
            }))
        return oms


class RegionServerStatisticsJMXPlugin(HBaseBasePlugin):
    """
    Datasource plugin for HBase Region Server component.
    """

    proxy_attributes = HBaseBasePlugin.proxy_attributes + (
        'region_ids',
        'title',
        'zHBaseRegionServerPort',
    )

    @defer.inlineCallbacks
    def collect(self, config):
        """
        This method overrides the HBaseBasePlugin.collect method.
        """
        results = self.new_data()
        for ds in config.datasources:
            self.component = ds.component
            headers = hbase_headers(
                accept='application/json',
                username=ds.zHBaseUsername,
                passwd=ds.zHBasePassword
            )
            url = hbase_rest_url(
                scheme=ds.zHBaseScheme,
                port=ds.zHBaseRegionServerPort,
                host=get_host(ds),
                endpoint='/jmx'
            )
            try:
                res = yield getPage(url, headers=headers)
                if not res:
                    raise HBaseException('No monitoring data.')
                results['values'][ds.component] = self.form_values(res, ds)
            except (Exception, HBaseException), e:
                e = check_error(e, ds.device) or e
                msg = "No access to page '{}': {}".format(url, e)
                results['events'].append({
                    'component': self.component,
                    'summary': str(e),
                    'message': msg,
                    'eventKey': 'hbase_monitoring_error',
                    'eventClass': '/Status',
                    'severity': ZenEventClasses.Info,
                })
                log.error(msg)
        defer.returnValue(results)

    def form_values(self, result, ds):
        """
        Parse the results of the HBase datasource.
        """
        # data points for different versions of HBase
        points = {
            'blockCacheEvictedCount': 'blockCacheEvictionCount',
            'blockCacheHitCachingRatio': 'blockCacheExpressHitPercent',
            'blockCacheHitRatio': 'blockCountHitPercent',
            'callQueueLen': 'numCallsInGeneralQueue',
            'compactionQueueSize': 'compactionQueueLength',
            'flushQueueSize': 'flushQueueLength',
        }
        try:
            data = json.loads(result)
        except Exception:
            raise HBaseException('Error parsing collected data.')

        result = {}
        for point in ds.points:
            for value in data.get('beans'):
                if value.get(point.id) is not None:
                    result[point.id] = (value[point.id], 'N')
                elif value.get(points.get(point.id)) is not None:
                    result[point.id] = (value[points[point.id]], 'N')
        return result


def get_host(ds):
    '''
    Check if component title contains 'localhost', if so,
    change it to device IP and return correct host for regionserver
    '''
    # TODO: it's a workaround, try to find another way.
    return ds.manageIp if 'localhost' in ds.title else ds.title
