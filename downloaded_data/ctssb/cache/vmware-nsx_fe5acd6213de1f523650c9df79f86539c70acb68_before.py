# Copyright 2014 VMware, Inc
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

import netaddr
from oslo_config import cfg

from neutron.api.v2 import attributes as attr
from neutron.db import l3_db
from neutron.db import models_v2
from oslo_log import log as logging
from vmware_nsx.neutron.plugins.vmware.common import exceptions as nsx_exc
from vmware_nsx.neutron.plugins.vmware.common import locking
from vmware_nsx.neutron.plugins.vmware.dbexts import nsxv_db
from vmware_nsx.neutron.plugins.vmware.dbexts import nsxv_models
from vmware_nsx.neutron.plugins.vmware.plugins import nsx_v
from vmware_nsx.neutron.plugins.vmware.plugins.nsx_v_drivers import (
    abstract_router_driver as router_driver)
from vmware_nsx.neutron.plugins.vmware.plugins import nsx_v_md_proxy
from vmware_nsx.neutron.plugins.vmware.vshield.common import (
    constants as vcns_const)
from vmware_nsx.neutron.plugins.vmware.vshield import edge_utils

LOG = logging.getLogger(__name__)

NSXV_ROUTER_RECONFIG = "nsxv_router_reconfig"


class RouterSharedDriver(router_driver.RouterBaseDriver):

    def get_type(self):
        return "shared"

    def create_router(self, context, lrouter, allow_metadata=True):
        pass

    def update_router(self, context, router_id, router):
        r = router['router']
        is_routes_update = True if 'routes' in r else False
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        if not edge_id:
            return super(nsx_v.NsxVPluginV2, self.plugin).update_router(
                context, router_id, router)
        else:
            with locking.LockManager.get_lock(
                    str(edge_id), lock_file_prefix=NSXV_ROUTER_RECONFIG,
                    external=True):
                gw_info = self.plugin._extract_external_gw(
                    context, router, is_extract=True)
                super(nsx_v.NsxVPluginV2, self.plugin).update_router(
                    context, router_id, router)
                self.update_routes(context, router_id, None)
            # here is used to handle routes which tenant updates.
            if gw_info != attr.ATTR_NOT_SPECIFIED:
                self._update_router_gw_info(context, router_id, gw_info,
                                            is_routes_update)
            if 'admin_state_up' in r:
                # If router was deployed on a different edge then
                # admin-state-up is already updated on the new edge.
                current_edge_id = (
                    edge_utils.get_router_edge_id(context, router_id))
                if current_edge_id == edge_id:
                    self.plugin._update_router_admin_state(context, router_id,
                                                           self.get_type(),
                                                           r['admin_state_up'])
            return self.plugin.get_router(context, router_id)

    def delete_router(self, context, router_id):
        pass

    def _update_routes_on_routers(self, context, target_router_id, router_ids):
        nexthop = None
        all_routes = []
        for router_id in router_ids:
            routes = self.plugin._get_extra_routes_by_router_id(
                context, router_id)
            filters = {'device_id': [router_id]}
            ports = self.plugin.get_ports(context.elevated(), filters)
            self.plugin._add_network_info_for_routes(context, routes, ports)
            all_routes.extend(routes)
            if not nexthop:
                router_qry = context.session.query(l3_db.Router)
                router_db = router_qry.filter_by(id=router_id).one()
                router_nexthop = self.plugin._get_external_attachment_info(
                    context, router_db)[2]
                if router_nexthop:
                    nexthop = router_nexthop
        # TODO(berlin) do rollback op.
        edge_utils.update_routes(self.nsx_v, context, target_router_id,
                                 all_routes, nexthop)

    def _update_nat_rules_on_routers(self, context,
                                     target_router_id, router_ids):
        snats = []
        dnats = []
        for router_id in router_ids:
            router_qry = context.session.query(l3_db.Router)
            router = router_qry.filter_by(id=router_id).one()
            if router.gw_port:
                snat, dnat = self.plugin._get_nat_rules(context, router)
                snats.extend(snat)
                dnats.extend(dnat)
        edge_utils.update_nat_rules(
            self.nsx_v, context, target_router_id, snats, dnats)

    def _update_external_interface_on_routers(self, context,
                                              target_router_id, router_ids):
        ext_net_ids = self._get_ext_net_ids(context, router_ids)
        if len(ext_net_ids) > 1:
            msg = _("Can't configure external interface on multiple external "
                    "networks")
            raise nsx_exc.NsxPluginException(err_msg=msg)
        gateway_primary_addr = None
        gateway_mask = None
        gateway_nexthop = None
        secondary = []
        if not ext_net_ids:
            ext_net_id = None
        else:
            ext_net_id = ext_net_ids[0]
        for router_id in router_ids:
            router_qry = context.session.query(l3_db.Router)
            router = router_qry.filter_by(id=router_id).one()
            addr, mask, nexthop = self.plugin._get_external_attachment_info(
                context, router)
            if addr:
                if not gateway_primary_addr:
                    gateway_primary_addr = addr
                else:
                    secondary.append(addr)
            if mask and not gateway_mask:
                gateway_mask = mask
            if nexthop and not gateway_nexthop:
                gateway_nexthop = nexthop
            secondary.extend(self.plugin._get_floatingips_by_router(
                context, router_id))
        LOG.debug('Configure ext interface as following, ext_net: %s, '
                  'primaryAddress: %s, netmask: %s, nexthop: %s, secondary: '
                  '%s.', ext_net_id, gateway_primary_addr, gateway_mask,
                  gateway_nexthop, secondary)
        edge_utils.update_external_interface(
            self.nsx_v, context, target_router_id, ext_net_id,
            gateway_primary_addr, gateway_mask, secondary)

    def _update_subnets_and_dnat_firewall_on_routers(self, context,
                                                     target_router_id,
                                                     router_ids,
                                                     allow_external=True):
        fake_fw_rules = []
        for router_id in router_ids:
            router_qry = context.session.query(l3_db.Router)
            router = router_qry.filter_by(id=router_id).one()
            subnet_cidrs = self.plugin._find_router_subnets_cidrs(
                context, router['id'])
            routes = self.plugin._get_extra_routes_by_router_id(
                context, router['id'])
            subnet_cidrs.extend([route['destination'] for route in routes])
            if subnet_cidrs:
                # Fake fw rule to open subnets firewall flows and static routes
                # relative flows
                fake_subnet_fw_rule = {
                    'action': 'allow',
                    'enabled': True,
                    'source_ip_address': subnet_cidrs,
                    'destination_ip_address': subnet_cidrs}
                fake_fw_rules.append(fake_subnet_fw_rule)
            _, dnat_rules = self.plugin._get_nat_rules(context, router)
            dnat_cidrs = [rule['dst'] for rule in dnat_rules]
            if dnat_cidrs:
                # Fake fw rule to open dnat firewall flows
                fake_dnat_fw_rule = {
                    'action': 'allow',
                    'enabled': True,
                    'destination_ip_address': dnat_cidrs}
                fake_fw_rules.append(fake_dnat_fw_rule)
            nosnat_fw_rules = self.plugin._get_nosnat_subnets_fw_rules(
                context, router)
            fake_fw_rules.extend(nosnat_fw_rules)

        # If metadata service is enabled, block access to inter-edge network
        if self.plugin.metadata_proxy_handler:
            fake_fw_rules += (
                nsx_v_md_proxy.get_router_fw_rules())

        # TODO(berlin): Add fw rules if fw service is supported
        fake_fw = {'firewall_rule_list': fake_fw_rules}
        edge_utils.update_firewall(self.nsx_v, context, target_router_id,
                                   fake_fw, allow_external=allow_external)

    def update_routes(self, context, router_id, nexthop):
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        if edge_id:
            router_db = self.plugin._get_router(context, router_id)
            available_router_ids, conflict_router_ids = (
                self._get_available_and_conflicting_ids(context, router_id))
            is_conflict = self.edge_manager.is_router_conflict_on_edge(
                context, router_id, conflict_router_ids, [], 0)
            if is_conflict:
                self._remove_router_services_on_edge(context, router_id)
                self._unbind_router_on_edge(context, router_id)
                self._bind_router_on_available_edge(
                    context, router_id, router_db.admin_state_up)
                new_edge_id = edge_utils.get_router_edge_id(context,
                                                            router_id)
                with locking.LockManager.get_lock(
                        str(new_edge_id),
                        lock_file_prefix=NSXV_ROUTER_RECONFIG, external=True):
                    self._add_router_services_on_available_edge(context,
                                                                router_id)
            else:
                router_ids = self.edge_manager.get_routers_on_same_edge(
                    context, router_id)
                if router_ids:
                    self._update_routes_on_routers(
                        context, router_id, router_ids)

    def _get_ext_net_ids(self, context, router_ids):
        ext_net_ids = []
        for router_id in router_ids:
            router_qry = context.session.query(l3_db.Router)
            router_db = router_qry.filter_by(id=router_id).one()
            ext_net_id = router_db.gw_port_id and router_db.gw_port.network_id
            if ext_net_id and ext_net_id not in ext_net_ids:
                ext_net_ids.append(ext_net_id)
        return ext_net_ids

    def _get_shared_routers(self, context):
        shared_routers = []
        routers_qry = context.session.query(l3_db.Router).all()
        for r in routers_qry:
            nsx_attr = (context.session.query(
                nsxv_models.NsxvRouterExtAttributes).filter_by(
                    router_id=r['id']).first())
            if nsx_attr['router_type'] == 'shared':
                shared_routers.append(r)
        return shared_routers

    def _get_available_and_conflicting_ids(self, context, router_id):
        """Query all conflicting router ids with existing router id.
        The router with static routes will be conflict with all other routers.
        The routers with different gateway will be conflict.
        The routers with overlapping interface will be conflict.
        """
        # 1. Check gateway
        # 2. Check subnet interface
        # 3. Check static routes
        router_list = []
        src_router_dict = {}
        ports_qry = context.session.query(models_v2.Port)
        intf_ports = ports_qry.filter_by(
            device_owner=l3_db.DEVICE_OWNER_ROUTER_INTF).all()
        gw_ports = ports_qry.filter_by(
            device_owner=l3_db.DEVICE_OWNER_ROUTER_GW).all()
        shared_routers = self._get_shared_routers(context)
        for r in shared_routers:
            router_dict = {}
            router_dict['id'] = r['id']
            router_dict['gateway'] = None
            for gwp in gw_ports:
                if gwp['id'] == r['gw_port_id']:
                    router_dict['gateway'] = (
                        gwp['fixed_ips'][0]['subnet_id'])
            subnet_ids = [p['fixed_ips'][0]['subnet_id'] for p in
                          intf_ports if p['device_id'] == r['id']]
            router_dict['subnet_ids'] = subnet_ids
            extra_routes = self.plugin._get_extra_routes_by_router_id(
                context, r['id'])
            destinations = [routes['destination'] for routes in extra_routes]
            router_dict['destinations'] = destinations

            LOG.debug('The router configuration is %s for router %s',
                      router_dict, router_dict['id'])
            if router_id != r['id']:
                router_list.append(router_dict)
            else:
                src_router_dict = router_dict

        # Router with static routes is conflict with other routers
        available_routers = []
        conflict_routers = []
        if src_router_dict['destinations'] != []:
            conflict_routers = [r['id'] for r in router_list]
            return (available_routers, conflict_routers)

        subnets_qry = context.session.query(models_v2.Subnet).all()
        conflict_cidr_set = []
        for subnet in subnets_qry:
            if subnet['id'] in src_router_dict['subnet_ids']:
                conflict_cidr_set.append(subnet['cidr'])
            if (src_router_dict['gateway'] is not None and
                subnet['id'] == src_router_dict['gateway']):
                conflict_cidr_set.append(subnet['cidr'])
        conflict_ip_set = netaddr.IPSet(conflict_cidr_set)
        # Check conflict router ids with gateway and interface
        for r in router_list:
            if r['destinations'] != []:
                conflict_routers.append(r['id'])
            else:
                cidr_set = []
                for subnet in subnets_qry:
                    if subnet['id'] in r['subnet_ids']:
                        cidr_set.append(subnet['cidr'])
                ip_set = netaddr.IPSet(cidr_set)
                if (src_router_dict['gateway'] is None or
                    r['gateway'] is None or
                    src_router_dict['gateway'] == r['gateway']):
                    if (conflict_ip_set & ip_set):
                        conflict_routers.append(r['id'])
                    else:
                        available_routers.append(r['id'])
                else:
                    conflict_routers.append(r['id'])

        return (available_routers, conflict_routers)

    def _get_conflict_network_and_router_ids_by_intf(self, context, router_id):
        """Collect conflicting networks and routers based on interface ports.
        Collect conflicting networks which has overlapping subnet attached
        to another router.
        Collect conflict routers which has overlap network attached to it.
        Returns:
        conflict_network_ids: networks which has overlapping ips
        conflict_router_ids: routers which has overlapping interfaces
        intf_num: interfaces number attached on the router
        """
        conflict_network_ids = []
        conflict_router_ids = []
        ports_qry = context.session.query(models_v2.Port)
        intf_ports = ports_qry.filter_by(
            device_owner=l3_db.DEVICE_OWNER_ROUTER_INTF).all()

        router_net_ids = list(
            set([port['network_id'] for port in intf_ports
                 if port['device_id'] == router_id]))
        if cfg.CONF.allow_overlapping_ips:
            router_intf_ports = [port for port in intf_ports
                                 if port['device_id'] == router_id]
            subnet_ids = []
            for port in router_intf_ports:
                subnet_ids.append(port['fixed_ips'][0]['subnet_id'])
            subnets_qry = context.session.query(models_v2.Subnet).all()
            subnets = [subnet for subnet in subnets_qry
                       if subnet['id'] in subnet_ids]
            conflict_network_ids.extend(
                self.plugin._get_conflict_network_ids_by_overlapping(
                    context, subnets))

        other_router_ports = [port for port in intf_ports
                              if port['device_id'] != router_id]

        for port in other_router_ports:
            if port['network_id'] in router_net_ids:
                conflict_router_ids.append(port['device_id'])

        conflict_router_ids = list(set(conflict_router_ids))
        conflict_network_ids = list(set(conflict_network_ids))
        intf_num = len(router_net_ids)
        return (conflict_network_ids, conflict_router_ids, intf_num)

    def _get_external_network_id_by_router(self, context, router_id):
        """Get router's external network id if it has."""
        router = self.plugin.get_router(context, router_id)
        ports_qry = context.session.query(models_v2.Port)
        gw_ports = ports_qry.filter_by(
            device_id=router_id,
            device_owner=l3_db.DEVICE_OWNER_ROUTER_GW,
            id=router['gw_port_id']).all()

        if gw_ports:
            return gw_ports[0]['network_id']

    def _get_conflict_network_ids_by_ext_net(self, context, router_id):
        """Collect conflicting networks based on external network.
        Collect conflicting networks which has overlapping subnet with the
        router's external network
        """
        conflict_network_ids = []
        ext_net_id = self._get_external_network_id_by_router(context,
                                                             router_id)
        if ext_net_id:
            ext_net = self.plugin._get_network(context, ext_net_id)
            if ext_net.subnets:
                ext_subnet = ext_net.subnets[0]
                if ext_subnet:
                    conflict_network_ids.extend(
                        self.plugin._get_conflict_network_ids_by_overlapping(
                            context, [ext_subnet]))
        return conflict_network_ids

    def _get_conflict_router_ids_by_ext_net(self, context,
                                            conflict_network_ids):
        """Collect conflict routers based on its external network.
        Collect conflict router if it has external network and the external
        network is in conflict_network_ids
        """
        ext_net_filters = {'router:external': [True]}
        ext_nets = self.plugin.get_networks(
            context.elevated(), filters=ext_net_filters)
        ext_net_ids = [ext_net.get('id') for ext_net in ext_nets]
        conflict_ext_net_ids = list(set(ext_net_ids) &
                                    set(conflict_network_ids))
        gw_ports_filter = {'network_id': conflict_ext_net_ids,
                           'device_owner': [l3_db.DEVICE_OWNER_ROUTER_GW]}
        ports_qry = context.session.query(models_v2.Port)
        gw_ports = self.plugin._apply_filters_to_query(
            ports_qry, models_v2.Port, gw_ports_filter).all()
        return list(set([gw_port['device_id'] for gw_port in gw_ports]))

    def _get_optional_and_conflict_router_ids_by_gw(self, context, router_id):
        """Collect conflict routers and optional routers based on GW port.
        Collect conflict router if it has different external network,
        else, collect optional router if it is not distributed and exclusive
        Returns:
        optional_router_ids: routers we can use its edge for the shared router.
        conflict_router_ids: conflict routers which has different gateway
        """
        ext_net_id = self._get_external_network_id_by_router(context,
                                                             router_id)
        routers = context.session.query(l3_db.Router).all()
        optional_router_ids = []
        conflict_router_ids = []

        if ext_net_id:
            ports_qry = context.session.query(models_v2.Port)
            all_gw_ports = ports_qry.filter_by(
                device_owner=l3_db.DEVICE_OWNER_ROUTER_GW).all()
            metadata_nets = nsxv_db.get_nsxv_internal_network(
                context.session,
                vcns_const.InternalEdgePurposes.INTER_EDGE_PURPOSE)
            metadata_net_ids = [metadata_net['network_id']
                                for metadata_net in metadata_nets]
            # filter out metadata gw_ports
            all_gw_ports = [gw_port for gw_port in all_gw_ports
                            if gw_port['network_id'] not in metadata_net_ids]
            for gw_port in all_gw_ports:
                if gw_port and gw_port['network_id'] != ext_net_id:
                    conflict_router_ids.append(gw_port['device_id'])

        for router in routers:
            router_res = {}
            self.plugin._extend_nsx_router_dict(router_res, router)
            if (router['id'] not in conflict_router_ids
                and router_res.get('router_type') == 'shared'):
                optional_router_ids.append(router['id'])
        return optional_router_ids, conflict_router_ids

    def _bind_router_on_available_edge(self, context, router_id, admin_state):
        with locking.LockManager.get_lock("router", lock_file_prefix="bind-",
                                          external=True):
            conflict_network_ids, conflict_router_ids, intf_num = (
                self._get_conflict_network_and_router_ids_by_intf(context,
                                                                  router_id))
            conflict_network_ids_by_ext_net = (
                self._get_conflict_network_ids_by_ext_net(context, router_id))
            conflict_network_ids.extend(conflict_network_ids_by_ext_net)
            optional_router_ids, new_conflict_router_ids = (
                self._get_available_and_conflicting_ids(context, router_id))
            conflict_router_ids.extend(new_conflict_router_ids)
            conflict_router_ids = list(set(conflict_router_ids))

            new = self.edge_manager.bind_router_on_available_edge(
                context, router_id, optional_router_ids,
                conflict_router_ids, conflict_network_ids, intf_num)
            # configure metadata service on the router.
            metadata_proxy_handler = self.plugin.metadata_proxy_handler
            if metadata_proxy_handler and new:
                metadata_proxy_handler.configure_router_edge(router_id)
            edge_id = edge_utils.get_router_edge_id(context, router_id)
            with locking.LockManager.get_lock(
                    str(edge_id),
                    lock_file_prefix=NSXV_ROUTER_RECONFIG,
                    external=True):
                # add all internal interfaces of the router on edge
                intf_net_ids = (
                    self.plugin._get_internal_network_ids_by_router(context,
                                                                    router_id))
                for network_id in intf_net_ids:
                    address_groups = self.plugin._get_address_groups(
                        context, router_id, network_id)
                    edge_utils.update_internal_interface(
                        self.nsx_v, context, router_id, network_id,
                        address_groups, admin_state)

    def _unbind_router_on_edge(self, context, router_id):
        self.edge_manager.unbind_router_on_edge(context, router_id)
        metadata_proxy_handler = self.plugin.metadata_proxy_handler
        if metadata_proxy_handler:
            metadata_proxy_handler.cleanup_router_edge(router_id)

    def _add_router_services_on_available_edge(self, context, router_id):
        router_ids = self.edge_manager.get_routers_on_same_edge(
            context, router_id)
        self._update_external_interface_on_routers(
            context, router_id, router_ids)
        self._update_routes_on_routers(context, router_id, router_ids)
        self._update_nat_rules_on_routers(context, router_id, router_ids)
        self._update_subnets_and_dnat_firewall_on_routers(
            context, router_id, router_ids, allow_external=True)

    def _remove_router_services_on_edge(self, context, router_id,
                                        intf_net_id=None):
        router_ids = self.edge_manager.get_routers_on_same_edge(
            context, router_id)
        router_ids.remove(router_id)
        # Refresh firewall, nats, ext_vnic as well as static routes
        self._update_routes_on_routers(context, router_id, router_ids)
        self._update_subnets_and_dnat_firewall_on_routers(
            context, router_id, router_ids, allow_external=True)
        self._update_nat_rules_on_routers(context, router_id, router_ids)
        self._update_external_interface_on_routers(
            context, router_id, router_ids)
        intf_net_ids = (
            self.plugin._get_internal_network_ids_by_router(context,
                                                            router_id))
        if intf_net_id:
            intf_net_ids.remove(intf_net_id)
        for net_id in intf_net_ids:
            edge_utils.delete_interface(self.nsx_v, context, router_id, net_id,
                                        is_wait=False)

    def _update_router_gw_info(self, context, router_id, info,
                               is_routes_update=False):
        router = self.plugin._get_router(context, router_id)
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        if not edge_id:
            super(nsx_v.NsxVPluginV2, self.plugin)._update_router_gw_info(
                context, router_id, info, router=router)
        # UPDATE gw info only if the router has been attached to an edge
        else:
            is_migrated = False
            with locking.LockManager.get_lock(
                    str(edge_id),
                    lock_file_prefix=NSXV_ROUTER_RECONFIG,
                    external=True):
                router_ids = self.edge_manager.get_routers_on_same_edge(
                    context, router_id)
                org_ext_net_id = (router.gw_port_id and
                                  router.gw_port.network_id)
                org_enable_snat = router.enable_snat
                orgaddr, orgmask, orgnexthop = (
                    self.plugin._get_external_attachment_info(
                        context, router))
                super(nsx_v.NsxVPluginV2, self.plugin)._update_router_gw_info(
                    context, router_id, info, router=router)
                new_ext_net_id = (router.gw_port_id and
                                  router.gw_port.network_id)
                new_enable_snat = router.enable_snat
                newaddr, newmask, newnexthop = (
                    self.plugin._get_external_attachment_info(
                        context, router))
                if new_ext_net_id and new_ext_net_id != org_ext_net_id:
                    # Check whether the gw address has overlapping
                    # with networks attached to the same edge
                    conflict_network_ids = (
                        self._get_conflict_network_ids_by_ext_net(
                            context, router_id))
                    is_migrated = self.edge_manager.is_router_conflict_on_edge(
                        context, router_id, [], conflict_network_ids)
                    if is_migrated:
                        self._remove_router_services_on_edge(context,
                                                             router_id)
                        self._unbind_router_on_edge(context, router_id)

                if not is_migrated:
                    ext_net_ids = self._get_ext_net_ids(context, router_ids)
                    if len(ext_net_ids) > 1:
                        # move all routing service of the router from existing
                        # edge to a new available edge if new_ext_net_id is
                        # changed.
                        self._remove_router_services_on_edge(context,
                                                             router_id)
                        self._unbind_router_on_edge(context, router_id)
                        is_migrated = True
                    else:
                        # Clear gateway info if all routers has no gw conf
                        if (orgnexthop and
                            (org_ext_net_id != new_ext_net_id or
                             len(ext_net_ids) == 0)):
                            LOG.debug("Delete default gateway %s", orgnexthop)
                            edge_utils.clear_gateway(self.nsx_v, context,
                                                     router_id)

                        # Update external vnic if addr or mask is changed
                        if orgaddr != newaddr or orgmask != newmask:
                            self._update_external_interface_on_routers(
                                context, router_id, router_ids)

                        # Update SNAT rules if ext net changed
                        # or ext net not changed but snat is changed.
                        if ((new_ext_net_id != org_ext_net_id) or
                            (new_ext_net_id == org_ext_net_id and
                             new_enable_snat != org_enable_snat)):
                            self._update_nat_rules_on_routers(context,
                                                              router_id,
                                                              router_ids)

                        if (new_ext_net_id != org_ext_net_id or
                            new_enable_snat != org_enable_snat or
                            is_routes_update):
                            self._update_subnets_and_dnat_firewall_on_routers(
                                context, router_id, router_ids,
                                allow_external=True)

                        # Update static routes in all.
                        self._update_routes_on_routers(
                            context, router_id, router_ids)
            if is_migrated:
                self._bind_router_on_available_edge(
                    context, router_id, router.admin_state_up)
                edge_id = edge_utils.get_router_edge_id(context, router_id)
                with locking.LockManager.get_lock(
                        str(edge_id),
                        lock_file_prefix=NSXV_ROUTER_RECONFIG,
                        external=True):
                    self._add_router_services_on_available_edge(context,
                                                                router_id)

    def add_router_interface(self, context, router_id, interface_info):
        self.plugin._check_intf_number_of_router(context, router_id)
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        router_db = self.plugin._get_router(context, router_id)
        if edge_id:
            is_migrated = False
            with locking.LockManager.get_lock(
                    str(edge_id),
                    lock_file_prefix=NSXV_ROUTER_RECONFIG,
                    external=True):
                router_ids = self.edge_manager.get_routers_on_same_edge(
                    context, router_id)
                info = super(nsx_v.NsxVPluginV2,
                       self.plugin).add_router_interface(
                    context, router_id, interface_info)
                subnet = self.plugin.get_subnet(context, info['subnet_id'])
                network_id = subnet['network_id']
                # Collect all conflict networks whose cidr are overlapped
                # with networks attached to the router and conflct routers
                # which has same network with the router's.
                conflict_network_ids, conflict_router_ids, _ = (
                    self._get_conflict_network_and_router_ids_by_intf(
                        context, router_id))

                _, new_conflict_router_ids = (
                    self._get_available_and_conflicting_ids(context,
                                                            router_id))
                conflict_router_ids.extend(new_conflict_router_ids)
                conflict_router_ids = list(set(conflict_router_ids))

                interface_ports = (
                    self.plugin._get_router_interface_ports_by_network(
                        context, router_id, network_id))
                # Consider whether another subnet of the same network
                # has been attached to the router.
                if len(interface_ports) > 1:
                    is_conflict = self.edge_manager.is_router_conflict_on_edge(
                        context, router_id, conflict_router_ids,
                        conflict_network_ids, 0)
                else:
                    is_conflict = self.edge_manager.is_router_conflict_on_edge(
                        context, router_id, conflict_router_ids,
                        conflict_network_ids, 1)
                if is_conflict:
                    if len(interface_ports) > 1:
                        self._remove_router_services_on_edge(
                            context, router_id)
                    else:
                        self._remove_router_services_on_edge(
                            context, router_id, network_id)
                    self._unbind_router_on_edge(context, router_id)
                    is_migrated = True
                else:
                    address_groups = self.plugin._get_address_groups(
                        context, router_id, network_id)
                    edge_utils.update_internal_interface(
                        self.nsx_v, context, router_id,
                        network_id, address_groups, router_db.admin_state_up)
                    if router_db.gw_port and router_db.enable_snat:
                        self._update_nat_rules_on_routers(
                            context, router_id, router_ids)
                    self._update_subnets_and_dnat_firewall_on_routers(
                        context, router_id, router_ids, allow_external=True)
            if is_migrated:
                self._bind_router_on_available_edge(
                    context, router_id, router_db.admin_state_up)
                edge_id = edge_utils.get_router_edge_id(context, router_id)
                with locking.LockManager.get_lock(
                        str(edge_id),
                        lock_file_prefix=NSXV_ROUTER_RECONFIG,
                        external=True):
                    self._add_router_services_on_available_edge(context,
                                                                router_id)
        else:
            info = super(nsx_v.NsxVPluginV2, self.plugin).add_router_interface(
                context, router_id, interface_info)
            # bind and configure routing servie on an availab edge
            self._bind_router_on_available_edge(
                context, router_id, router_db.admin_state_up)
            edge_id = edge_utils.get_router_edge_id(context, router_id)
            with locking.LockManager.get_lock(
                    str(edge_id),
                    lock_file_prefix=NSXV_ROUTER_RECONFIG,
                    external=True):
                self._add_router_services_on_available_edge(context,
                                                            router_id)
        return info

    def remove_router_interface(self, context, router_id, interface_info):
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        with locking.LockManager.get_lock(
                str(edge_id),
                lock_file_prefix=NSXV_ROUTER_RECONFIG,
                external=True):
            info = super(
                nsx_v.NsxVPluginV2, self.plugin).remove_router_interface(
                    context, router_id, interface_info)
            subnet = self.plugin.get_subnet(context, info['subnet_id'])
            network_id = subnet['network_id']
            router_ids = self.edge_manager.get_routers_on_same_edge(
                context, router_id)
            self._update_nat_rules_on_routers(context, router_id, router_ids)
            self._update_subnets_and_dnat_firewall_on_routers(
                context, router_id, router_ids, allow_external=True)
            ports = self.plugin._get_router_interface_ports_by_network(
                context, router_id, network_id)
            if not ports:
                edge_utils.delete_interface(self.nsx_v, context,
                                            router_id, network_id)
                # unbind all services if no interfaces attached to the router
                if not self.plugin._get_internal_network_ids_by_router(
                        context, router_id):
                    self._remove_router_services_on_edge(context, router_id)
                    self._unbind_router_on_edge(context, router_id)
            else:
                address_groups = self.plugin._get_address_groups(
                    context, router_id, network_id)
                edge_utils.update_internal_interface(
                    self.nsx_v, context, router_id, network_id, address_groups)
        return info

    def _update_edge_router(self, context, router_id):
        edge_id = edge_utils.get_router_edge_id(context, router_id)
        with locking.LockManager.get_lock(
                str(edge_id),
                lock_file_prefix=NSXV_ROUTER_RECONFIG,
                external=True):
            router_ids = self.edge_manager.get_routers_on_same_edge(
                context, router_id)
            if router_ids:
                self._update_external_interface_on_routers(
                    context, router_id, router_ids)
                self._update_nat_rules_on_routers(
                    context, router_id, router_ids)
                self._update_subnets_and_dnat_firewall_on_routers(
                    context, router_id, router_ids, allow_external=True)
