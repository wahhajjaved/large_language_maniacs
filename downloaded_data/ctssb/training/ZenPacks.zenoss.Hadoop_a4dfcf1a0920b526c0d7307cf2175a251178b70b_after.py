######################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is
# installed.
#
######################################################################
import logging
log = logging.getLogger('zen.Hadoop')

from zope.event import notify
from zope.component import adapts
from zope.interface import implements

from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.ZenModel.ZenossSecurity import ZEN_CHANGE_DEVICE
from Products.ZenRelations.RelSchema import ToManyCont, ToOne

from Products.Zuul.decorators import info
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.infos.component import ComponentInfo
from Products.Zuul.interfaces.component import IComponentInfo
from Products.Zuul.utils import ZuulMessageFactory as _t

from Products.ZenUtils.IpUtil import getHostByName

from .HadoopComponent import HadoopComponent


class HadoopDataNode(HadoopComponent):
    meta_type = portal_type = "HadoopDataNode"

    health_state = None
    last_contacted = None
    hbase_device_id = None

    _properties = HadoopComponent._properties + (
        {'id': 'health_state', 'type': 'string'},
        {'id': 'last_contacted', 'type': 'string'},
        {'id': 'hbase_device_id', 'type': 'string'},
    )

    _relations = HadoopComponent._relations + (
        ('hadoop_host', ToOne(
            ToManyCont, 'Products.ZenModel.Device.Device', 'hadoop_data_nodes')),
    )

    def device(self):
        return self.hadoop_host()

    def setHBaseAutodiscover(self, node_name):
        """
        One of HadoopDataNode can be occupied by HBase.
        """
        hbase_device = None
        old_hbase_device = None
        dc = self.dmd.getOrganizer(self.zHbaseDeviceClass)

        # Check for IP
        ip = self.device()._sanitizeIPaddress(node_name)
        if not ip:
            try:
                ip = getHostByName(node_name)
            except Exception:
                pass
        if not ip:
            log.warn("Cann't resolve %s into IP address" % node_name)
            return

        # a) Check if HBase changed it's node
        for node in self.hadoop_data_nodes():
            if node.hbase_device_id == ip:
                # Nothing changed
                return

        # b) Lookup for old HBase node
        for node in self.hadoop_data_nodes():
            if node.hbase_device_id:
                old_hbase_device = self.findDeviceByIdOrIp(
                    node.hbase_device_id
                )
                node.hbase_device_id = None
                node.index_object()
                break

        if old_hbase_device:
            # Changing IP to node_name
            hbase_device = old_hbase_device
            if not self.device().manageIp == ip:
                hbase_device.setManageIp(node_name)
                hbase_device.index_object()
                notify(IndexingEvent(hbase_device))
        else:
            hbase_device = self.findDevice(ip)
            if hbase_device:
                log.info("HBase device found in existing devices")
            else:
                # Check if HBase ZenPack is installed
                try:
                    self.dmd.ZenPackManager.packs._getOb(
                        'ZenPacks.zenoss.HBase'
                    )
                except AttributeError:
                    log.warn("HBase ZenPack is requaried")
                    return

                hbase_device = dc.createInstance(ip)
                hbase_device.title = node_name
                hbase_device.setManageIp(ip)
                hbase_device.setPerformanceMonitor(
                    self.getPerformanceServer().id
                )
                hbase_device.index_object()
                hbase_device.setZenProperty(
                    "zCollectorPlugins", list(hbase_device.zCollectorPlugins) +
                    ['HBaseCollector', 'HBaseTableCollector']
                )
                hbase_device.setZenProperty(
                    'zHBasePassword', self.zHBasePassword
                )
                hbase_device.setZenProperty(
                    'zHBaseUsername', self.zHBaseUsername
                )
                hbase_device.setZenProperty(
                    'zHBaseRestPort', self.zHBaseRestPort
                )
                hbase_device.setZenProperty(
                    'zHBaseMasterPort', self.zHBaseMasterPort
                )
                hbase_device.setZenProperty(
                    'zHBaseRegionServerPort', self.zHBaseRegionServerPort
                )
                hbase_device.setZenProperty('zHBaseScheme', self.zHBaseScheme)

                log.info("HBase device created")
                hbase_device.index_object()
                notify(IndexingEvent(hbase_device))

                # Schedule a modeling job for the new device.
                # hbase_device.collectDevice(setlog=False, background=True)

        # Setting HBase device ID as node property for back link from UI
        for node in self.hadoop_data_nodes():
            if str(node.title).split(':')[0] == node_name:
                node.hbase_device_id = hbase_device.manageIp
                node.index_object()

    def getHBaseAutodiscover(self):
        return True


class IHadoopDataNodeInfo(IComponentInfo):
    '''
    API Info interface for HadoopDataNode.
    '''
    device = schema.Entity(title=_t(u'Device'))
    health_state = schema.TextLine(title=_t(u'Health State'))
    last_contacted = schema.TextLine(title=_t(u'Last Contacted'))
    hbase_device = schema.TextLine(title=_t(u'HBase Device'))


class HadoopDataNodeInfo(ComponentInfo):
    '''
    API Info adapter factory for HadoopDataNode.
    '''
    implements(IHadoopDataNodeInfo)
    adapts(HadoopDataNode)

    health_state = ProxyProperty('health_state')
    last_contacted = ProxyProperty('last_contacted')

    @property
    @info
    def hbase_device(self):
        dev_id = self._object.hbase_device_id
        if dev_id:
            obj = self._object.findDeviceByIdOrIp(dev_id)
            if obj:
                return '<a href="{}">{}</a>'.format(
                            obj.getPrimaryUrlPath(),
                            obj.titleOrId()
                        )
        return ''
