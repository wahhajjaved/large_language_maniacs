# Copyright 2015 Cisco Systems, Inc.  All rights reserved.
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

from oslo_config import cfg
from oslo_utils import uuidutils

from neutron import context
from neutron.extensions import l3

from networking_cisco.plugins.cisco.common import cisco_constants
from networking_cisco.plugins.cisco.db.l3 import ha_db
from networking_cisco.plugins.cisco.extensions import ha
from networking_cisco.plugins.cisco.extensions import routerhostingdevice
from networking_cisco.plugins.cisco.extensions import routerrole
from networking_cisco.plugins.cisco.extensions import routertype
from networking_cisco.plugins.cisco.extensions import routertypeawarescheduler
from networking_cisco.tests.unit.cisco.l3 import (
    test_ha_l3_router_appliance_plugin as cisco_ha_test)
from networking_cisco.tests.unit.cisco.l3 import (
    test_l3_routertype_aware_schedulers as cisco_test_case)


_uuid = uuidutils.generate_uuid

AGENT_TYPE_L3_CFG = cisco_constants.AGENT_TYPE_L3_CFG
ROUTER_ROLE_GLOBAL = cisco_constants.ROUTER_ROLE_GLOBAL
ROUTER_ROLE_LOGICAL_GLOBAL = cisco_constants.ROUTER_ROLE_LOGICAL_GLOBAL
LOGICAL_ROUTER_ROLE_NAME = cisco_constants.LOGICAL_ROUTER_ROLE_NAME
ROUTER_ROLE_ATTR = routerrole.ROUTER_ROLE_ATTR
HOSTING_DEVICE_ATTR = routerhostingdevice.HOSTING_DEVICE_ATTR
AUTO_SCHEDULE_ATTR = routertypeawarescheduler.AUTO_SCHEDULE_ATTR


class Asr1kRouterTypeDriverTestCase(
        cisco_test_case.L3RoutertypeAwareHostingDeviceSchedulerTestCaseBase):

    # Nexus router type for ASR1k driver tests, why?
    #   - Yes(!), it does not matter and there is only one hosting device for
    #  that router type in the test setup which makes scheduling deterministic
    router_type = 'Nexus_ToR_Neutron_router'

    def _verify_created_routers(self, router_ids, hd_id):
        # tenant routers
        q_p = '%s=None' % ROUTER_ROLE_ATTR
        r_ids = {r['id'] for r in self._list(
            'routers', query_params=q_p)['routers']}
        self.assertEqual(len(r_ids), len(router_ids))
        for r_id in r_ids:
            self.assertIn(r_id, router_ids)
        # global router on hosting device
        q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_GLOBAL)
        g_rtrs = self._list('routers', query_params=q_p)['routers']
        self.assertEqual(len(g_rtrs), 1)
        g_rtr = g_rtrs[0]
        self.assertEqual(g_rtr['name'].endswith(
            hd_id[-cisco_constants.ROLE_ID_LEN:]), True)
        # logical global router for global routers HA
        q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_LOGICAL_GLOBAL)
        g_l_rtrs = self._list('routers', query_params=q_p)['routers']
        self.assertEqual(len(g_l_rtrs), 1)
        g_l_rtr = g_l_rtrs[0]
        self.assertEqual(g_l_rtr['name'], LOGICAL_ROUTER_ROLE_NAME)
        self.assertEqual(g_l_rtr[AUTO_SCHEDULE_ATTR], False)
        # ensure first routers_updated notification was for global router
        notifier = self.plugin.agent_notifiers[AGENT_TYPE_L3_CFG]
        notify_call = notifier.method_calls[0]
        self.assertEqual(notify_call[0], 'routers_updated')
        updated_routers = notify_call[1][1]
        self.assertEqual(len(updated_routers), 1)
        self.assertEqual(updated_routers[0]['id'], g_rtr['id'])
        # ensure *no* update notifications where sent for logical global router
        for call in notifier.method_calls:
            self.assertNotIn(call[1][1][0][ROUTER_ROLE_ATTR],
                             [ROUTER_ROLE_LOGICAL_GLOBAL])

    def _test_gw_router_create_adds_global_router(self, set_context=False):
        tenant_id = _uuid()
        with self.network(tenant_id=tenant_id) as n_external:
            res = self._create_subnet(self.fmt, n_external['network']['id'],
                                      cidr='10.0.1.0/24', tenant_id=tenant_id)
            s = self.deserialize(self.fmt, res)
            self._set_net_external(s['subnet']['network_id'])
            ext_gw = {'network_id': s['subnet']['network_id']}
            with self.router(tenant_id=tenant_id, external_gateway_info=ext_gw,
                             set_context=set_context) as router1:
                r1 = router1['router']
                self.plugin._process_backlogged_routers()
                r1_after = self._show('routers', r1['id'])['router']
                hd_id = r1_after[HOSTING_DEVICE_ATTR]
                # should have one global router now
                self._verify_created_routers({r1['id']}, hd_id)
                with self.router(name='router2', tenant_id=tenant_id,
                                 external_gateway_info=ext_gw,
                                 set_context=set_context) as router2:
                    r2 = router2['router']
                    self.plugin._process_backlogged_routers()
                    # should still have only one global router
                    self._verify_created_routers({r1['id'], r2['id']}, hd_id)

    def test_gw_router_create_adds_global_router(self):
        self._test_gw_router_create_adds_global_router()

    def test_gw_router_create_adds_global_router_non_admin(self):
        self._test_gw_router_create_adds_global_router(True)

    def _test_router_create_adds_no_global_router(self, set_context=False):
        with self.router(set_context=set_context) as router:
            r = router['router']
            self.plugin._process_backlogged_routers()
            # tenant routers
            q_p = '%s=None' % ROUTER_ROLE_ATTR
            t_rtrs = self._list('routers', query_params=q_p)['routers']
            self.assertEqual(len(t_rtrs), 1)
            t_rtr = t_rtrs[0]
            self.assertEqual(t_rtr['id'], r['id'])
            # global router
            q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_GLOBAL)
            g_rtrs = self._list('routers', query_params=q_p)['routers']
            self.assertEqual(len(g_rtrs), 0)
            # logical global router for global routers HA
            q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_LOGICAL_GLOBAL)
            g_l_rtrs = self._list('routers', query_params=q_p)['routers']
            self.assertEqual(len(g_l_rtrs), 0)
            #TODO(bobmel): Also check that notification is sent

    def test_router_create_adds_no_global_router(self):
        self._test_router_create_adds_no_global_router()

    def test_router_create_adds_no_global_router_non_admin(self):
        self._test_router_create_adds_no_global_router(False)

    def _verify_updated_routers(self, router_ids, hd_id=None, call_index=1):
        # tenant routers
        q_p = '%s=None' % ROUTER_ROLE_ATTR
        r_ids = {r['id'] for r in self._list(
            'routers', query_params=q_p)['routers']}
        self.assertEqual(len(r_ids), len(router_ids))
        for r_id in r_ids:
            self.assertIn(r_id, router_ids)
        # global routers
        q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_GLOBAL)
        g_rtrs = self._list('routers', query_params=q_p)['routers']
        # logical global router for global routers HA
        q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_LOGICAL_GLOBAL)
        g_l_rtrs = self._list('routers', query_params=q_p)['routers']
        notifier = self.plugin.agent_notifiers[AGENT_TYPE_L3_CFG]
        if hd_id:
            self.assertEqual(len(g_rtrs), 1)
            g_rtr = g_rtrs[0]
            self.assertEqual(
                g_rtr['name'].endswith(hd_id[-cisco_constants.ROLE_ID_LEN:]),
                True)
            self.assertEqual(len(g_l_rtrs), 1)
            g_l_rtr = g_l_rtrs[0]
            self.assertEqual(g_l_rtr['name'], LOGICAL_ROUTER_ROLE_NAME)
            self.assertEqual(g_l_rtr[AUTO_SCHEDULE_ATTR], False)
            # routers_updated notification call_index is for global router
            notify_call = notifier.method_calls[call_index]
            self.assertEqual(notify_call[0], 'routers_updated')
            updated_routers = notify_call[1][1]
            self.assertEqual(len(updated_routers), 1)
            self.assertEqual(updated_routers[0]['id'], g_rtr['id'])
        else:
            self.assertEqual(len(g_rtrs), 0)
            self.assertEqual(len(g_l_rtrs), 0)
        # ensure *no* update notifications where sent for logical global router
        for call in notifier.method_calls:
            if call[0] != 'router_deleted':
                self.assertNotIn(call[1][1][0][ROUTER_ROLE_ATTR],
                                 [ROUTER_ROLE_LOGICAL_GLOBAL])

    def _test_router_update_set_gw_adds_global_router(self, set_context=False):
        tenant_id = _uuid()
        with self.network(tenant_id=tenant_id) as n_external:
            res = self._create_subnet(self.fmt, n_external['network']['id'],
                                      cidr='10.0.1.0/24', tenant_id=tenant_id)
            s = self.deserialize(self.fmt, res)
            self._set_net_external(s['subnet']['network_id'])
            with self.router(tenant_id=tenant_id,
                             set_context=set_context) as router1,\
                    self.router(name='router2', tenant_id=tenant_id,
                                set_context=set_context) as router2:
                r1 = router1['router']
                r2 = router2['router']
                # backlog processing will trigger one routers_updated
                # notification containing r1 and r2
                self.plugin._process_backlogged_routers()
                # should have no global router yet
                r_ids = {r1['id'], r2['id']}
                self._verify_updated_routers(r_ids)
                ext_gw = {'network_id': s['subnet']['network_id']}
                r_spec = {'router': {l3.EXTERNAL_GW_INFO: ext_gw}}
                r1_after = self._update('routers', r1['id'], r_spec)['router']
                hd_id = r1_after[HOSTING_DEVICE_ATTR]
                # should now have one global router
                self._verify_updated_routers(r_ids, hd_id)
                self._update('routers', r2['id'], r_spec)
                # should still have only one global router
                self._verify_updated_routers(r_ids, hd_id)

    def test_router_update_set_gw_adds_global_router(self):
        self._test_router_update_set_gw_adds_global_router()

    def test_router_update_set_gw_adds_global_router_non_admin(self):
        self._test_router_update_set_gw_adds_global_router(True)

    def _test_router_update_unset_gw_keeps_global_router(self,
                                                         set_context=False):
        tenant_id = _uuid()
        with self.network(tenant_id=tenant_id) as n_external:
            res = self._create_subnet(self.fmt, n_external['network']['id'],
                                      cidr='10.0.1.0/24', tenant_id=tenant_id)
            s = self.deserialize(self.fmt, res)
            self._set_net_external(s['subnet']['network_id'])
            ext_gw = {'network_id': s['subnet']['network_id']}
            with self.router(tenant_id=tenant_id,
                             external_gateway_info=ext_gw,
                             set_context=set_context) as router1,\
                    self.router(name='router2', tenant_id=tenant_id,
                                external_gateway_info=ext_gw,
                                set_context=set_context) as router2:
                r1 = router1['router']
                r2 = router2['router']
                # backlog processing will trigger one routers_updated
                # notification containing r1 and r2
                self.plugin._process_backlogged_routers()
                r1_after = self._show('routers', r1['id'])['router']
                hd_id = r1_after[HOSTING_DEVICE_ATTR]
                r_ids = {r1['id'], r2['id']}
                # should have one global router now
                self._verify_updated_routers(r_ids, hd_id, 0)
                r_spec = {'router': {l3.EXTERNAL_GW_INFO: None}}
                self._update('routers', r1['id'], r_spec)
                # should still have one global router
                self._verify_updated_routers(r_ids, hd_id, 0)
                self._update('routers', r2['id'], r_spec)
                # should have no global router now
                self._verify_updated_routers(r_ids)

    def test_router_update_unset_gw_keeps_global_router(self):
        self._test_router_update_unset_gw_keeps_global_router()

    def test_router_update_unset_gw_keeps_global_router_non_admin(self):
        self._test_router_update_unset_gw_keeps_global_router(True)

    def _verify_deleted_routers(self, hd_id=None, id_global_router=None):
        # global routers
        q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_GLOBAL)
        g_rtrs = self._list('routers', query_params=q_p)['routers']
        if hd_id:
            self.assertEqual(len(g_rtrs), 1)
            g_rtr = g_rtrs[0]
            self.assertEqual(g_rtr['name'].endswith(
                hd_id[-cisco_constants.ROLE_ID_LEN:]), True)
            return g_rtrs[0]['id']
        else:
            self.assertEqual(len(g_rtrs), 0)
            notifier = self.plugin.agent_notifiers[AGENT_TYPE_L3_CFG]
            # ensure 2nd last router_deleted notification was for global router
            notify_call = notifier.method_calls[-2]
            self.assertEqual(notify_call[0], 'router_deleted')
            deleted_router = notify_call[1][1]
            self.assertEqual(deleted_router['id'], id_global_router)
            # ensure last router_deleted notification was for logical global
            # router
            notify_call = notifier.method_calls[-1]
            self.assertEqual(notify_call[0], 'router_deleted')
            deleted_router = notify_call[1][1]
            self.assertEqual(deleted_router[ROUTER_ROLE_ATTR],
                             ROUTER_ROLE_LOGICAL_GLOBAL)
            self.assertEqual(deleted_router[AUTO_SCHEDULE_ATTR], False)

    def _test_gw_router_delete_removes_global_router(self, set_context=False):
        tenant_id = _uuid()
        with self.network(tenant_id=tenant_id) as n_external:
            res = self._create_subnet(self.fmt, n_external['network']['id'],
                                      cidr='10.0.1.0/24', tenant_id=tenant_id)
            s = self.deserialize(self.fmt, res)
            self._set_net_external(s['subnet']['network_id'])
            ext_gw = {'network_id': s['subnet']['network_id']}
            with self.router(tenant_id=tenant_id, external_gateway_info=ext_gw,
                             set_context=set_context) as router1,\
                    self.router(name='router2', tenant_id=tenant_id,
                                external_gateway_info=ext_gw,
                                set_context=set_context) as router2:
                r1 = router1['router']
                r2 = router2['router']
                self.plugin._process_backlogged_routers()
                r1_after = self._show('routers', r1['id'])['router']
                hd_id = r1_after[HOSTING_DEVICE_ATTR]
                self._delete('routers', r1['id'])
                # should still have the global router
                id_global_router = self._verify_deleted_routers(hd_id)
                self._delete('routers', r2['id'])
                # should be no global router now
                self._verify_deleted_routers(id_global_router=id_global_router)

    def test_gw_router_delete_removes_global_router(self):
        self._test_gw_router_delete_removes_global_router()

    def test_gw_router_delete_removes_global_router_non_admin(self):
        self._test_gw_router_delete_removes_global_router(True)

    def _test_router_delete_removes_no_global_router(self, set_context=False):
        tenant_id = _uuid()
        with self.network(tenant_id=tenant_id) as n_external:
            res = self._create_subnet(self.fmt, n_external['network']['id'],
                                      cidr='10.0.1.0/24', tenant_id=tenant_id)
            s = self.deserialize(self.fmt, res)
            self._set_net_external(s['subnet']['network_id'])
            ext_gw = {'network_id': s['subnet']['network_id']}
            with self.router(tenant_id=tenant_id,
                             set_context=set_context) as router1,\
                    self.router(name='router2', tenant_id=tenant_id,
                                external_gateway_info=ext_gw,
                                set_context=set_context) as router2:
                r1 = router1['router']
                r2 = router2['router']
                self.plugin._process_backlogged_routers()
                r1_after = self._show('routers', r1['id'])['router']
                hd_id = r1_after[HOSTING_DEVICE_ATTR]
                self._delete('routers', r1['id'])
                # should still have the global router
                id_global_router = self._verify_deleted_routers(hd_id)
                self._delete('routers', r2['id'])
                # should be no global router now
                self._verify_deleted_routers(id_global_router=id_global_router)

    def test_router_delete_removes_no_global_router(self):
        self._test_router_delete_removes_no_global_router()

    def test_gw_router_delete_removes_no_global_router_non_admin(self):
        self._test_router_delete_removes_no_global_router(True)


class L3CfgAgentAsr1kRouterTypeDriverTestCase(
        cisco_test_case.L3RoutertypeAwareHostingDeviceSchedulerTestCaseBase,
        cisco_ha_test.HAL3RouterTestsMixin):

    def setUp(self, core_plugin=None, l3_plugin=None, dm_plugin=None,
              ext_mgr=None):
        if l3_plugin is None:
            l3_plugin = cisco_test_case.HA_L3_PLUGIN_KLASS
        if ext_mgr is None:
            ext_mgr = (cisco_test_case.
                       TestHASchedulingL3RouterApplianceExtensionManager())
        cfg.CONF.set_override('ha_enabled_by_default', True, group='ha')
        cfg.CONF.set_override('default_ha_redundancy_level', 1, group='ha')

        super(L3CfgAgentAsr1kRouterTypeDriverTestCase, self).setUp(
            l3_plugin=l3_plugin, ext_mgr=ext_mgr)
        self.orig_get_sync_data = self.plugin.get_sync_data
        self.plugin.get_sync_data = self.plugin.get_sync_data_ext

    def tearDown(self):
        self.plugin.get_sync_data = self.orig_get_sync_data
        super(L3CfgAgentAsr1kRouterTypeDriverTestCase, self).tearDown()

    def _verify_sync_data(self, context, ids_colocated_routers, g_l_rtr,
                          g_l_rtr_rr_ids, ha_settings):
        routers = self.plugin.get_sync_data_ext(context,
                                                ids_colocated_routers)
        self.assertEqual(len(routers), 2)
        global_router = [r for r in routers if
                         r[ROUTER_ROLE_ATTR] == ROUTER_ROLE_GLOBAL][0]
        # verify that global router has HA information from logical
        # global router, in particular VIP address for the gw port
        # comes from the gw port of the logical global router
        ha_info = global_router['gw_port']['ha_info']
        ha_port_id = ha_info['ha_port']['id']
        vip_address = g_l_rtr[l3.EXTERNAL_GW_INFO][
            'external_fixed_ips'][0]['ip_address']
        self.assertEqual(
            ha_info['ha_port']['fixed_ips'][0]['ip_address'],
            vip_address)
        self.assertEqual(global_router['gw_port_id'] == ha_port_id,
                         False)
        self._verify_ha_settings(global_router, ha_settings)
        rr_info_list = global_router[ha.DETAILS][ha.REDUNDANCY_ROUTERS]
        self.assertEqual(len(rr_info_list), len(g_l_rtr_rr_ids))
        for rr_info in rr_info_list:
            self.assertIn(rr_info['id'], g_l_rtr_rr_ids)

    def test_l3_cfg_agent_query_global_router_info(self):
        with self.subnet(cidr='10.0.1.0/24') as s_ext:
            self._set_net_external(s_ext['subnet']['network_id'])
            ext_gw = {'network_id': s_ext['subnet']['network_id']}
            with self.router(external_gateway_info=ext_gw) as router:
                r = router['router']
                self.plugin._process_backlogged_routers()
                r_after = self._show('routers', r['id'])['router']
                hd_id = r_after[HOSTING_DEVICE_ATTR]
                id_r_ha_backup = r_after[ha.DETAILS][
                    ha.REDUNDANCY_ROUTERS][0]['id']
                r_ha_backup_after = self._show('routers',
                                               id_r_ha_backup)['router']
                ha_backup_hd_id = r_ha_backup_after[HOSTING_DEVICE_ATTR]
                # logical global router for global routers HA
                q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_LOGICAL_GLOBAL)
                g_l_rtrs = self._list('routers', query_params=q_p)['routers']
                # should be only one logical global router
                self.assertEqual(len(g_l_rtrs), 1)
                g_l_rtr = g_l_rtrs[0]
                g_l_rtr_rr_ids = {r_info['id'] for r_info in g_l_rtr[
                    ha.DETAILS][ha.REDUNDANCY_ROUTERS]}
                self.assertEqual(g_l_rtr[ha.ENABLED], True)
                self.assertEqual(g_l_rtr[routertype.TYPE_ATTR],
                                 r[routertype.TYPE_ATTR])
                # no auto-scheduling to ensure logical global router is never
                # instantiated (unless an admin does some bad thing...)
                self.assertEqual(g_l_rtr[AUTO_SCHEDULE_ATTR], False)
                # global router on hosting devices
                q_p = '%s=%s' % (ROUTER_ROLE_ATTR, ROUTER_ROLE_GLOBAL)
                g_rtrs = {g_r[HOSTING_DEVICE_ATTR]: g_r for g_r in self._list(
                    'routers', query_params=q_p)['routers']}
                self.assertEqual(len(g_rtrs), 2)
                for g_r in g_rtrs.values():
                    self.assertEqual(g_r[routertype.TYPE_ATTR],
                                     r[routertype.TYPE_ATTR])
                    # global routers should have HA disabled in db
                    self.assertEqual(g_r[ha.ENABLED], False)
                    # global routers should never be auto-scheduled as that
                    # can result in them being moved to another hosting device
                    self.assertEqual(g_r[AUTO_SCHEDULE_ATTR], False)
                    # global router should be redundancy router of the logical
                    # global router for this router type
                    self.assertIn(g_r['id'], g_l_rtr_rr_ids)
                e_context = context.get_admin_context()
                # global routers should here have HA setup information from
                # the logical global router
                ha_settings = self._get_ha_defaults(
                    ha_type=cfg.CONF.ha.default_ha_mechanism,
                    redundancy_level=2, priority=ha_db.DEFAULT_MASTER_PRIORITY)
                # verify global router co-located with the user visible router
                ids_colocated_routers = [r['id'], g_rtrs[hd_id]['id']]
                self._verify_sync_data(e_context, ids_colocated_routers,
                                       g_l_rtr, g_l_rtr_rr_ids, ha_settings)
                # verify global router co.located with the ha backup
                # router of the user visible router
                ids_colocated_routers = [r_ha_backup_after['id'],
                                         g_rtrs[ha_backup_hd_id]['id']]
                self._verify_sync_data(e_context, ids_colocated_routers,
                                       g_l_rtr, g_l_rtr_rr_ids, ha_settings)
