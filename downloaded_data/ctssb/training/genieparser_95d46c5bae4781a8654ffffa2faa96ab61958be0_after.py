"""show_bgp.py

NXOS parsers for the following show commands:
    * 'show bgp process vrf all'
    * 'show bgp process vrf all | xml'
    * 'show bgp peer-session <WORD>'
    * 'show bgp peer-policy <WORD>'
    * 'show bgp peer-template <WORD>'
    * 'show bgp vrf all all'
    * 'show bgp vrf all all neighbors'
    * 'show bgp vrf all all nexthop-database'
    * 'show bgp vrf <WORD> all summary'
    * 'show bgp vrf <WORD> all summary | xml'
    * 'show bgp vrf <WROD> all dampening parameters'
    * 'show bgp vrf <WROD> all dampening parameters | xml'
    * 'show bgp vrf all all neighbors <WORD> advertised-routes'
    * 'show bgp vrf all all neighbors <WORD> routes'
    * 'show bgp vrf all all neighbors <WORD> received-routes'
    * 'show bgp all dampening flap-statistics'
    * 'show bgp all dampening flap-statistics | xml'
    * 'show bgp all nexthop-database'
    * 'show bgp all nexthop-database | xml'
    * 'show bgp peer-template'
    * 'show bgp peer-template | xml'
    * 'show bgp vrf <vrf> <address_family>  policy statistics redistribute'
    * 'show bgp vrf <vrf> <address_family>  policy statistics redistribute | xml'
    * 'show bgp vrf <vrf> <address_family>  policy statistics dampening'
    * 'show bgp vrf <vrf> <address_family>  policy statistics dampening | xml'
    * 'show bgp vrf <vrf> <address_family>  policy statistics neighbor <neighbor>'
    * 'show bgp vrf <vrf> <address_family>  policy statistics neighbor <neighbor> | xml'
    * 'show bgp <address_family>  policy statistics redistribute'
    * 'show bgp <address_family>  policy statistics redistribute | xml'
    * 'show bgp <address_family>  policy statistics dampening'
    * 'show bgp <address_family>  policy statistics dampening | xml'
    * 'show bgp <address_family>  policy statistics neighbor <neighbor>'
    * 'show bgp <address_family>  policy statistics neighbor <neighbor> | xml'
    * 'show bgp sessions'
    * 'show bgp sessions | xml'
    * 'show bgp sessions vrf <WORD>'
    * 'show bgp sessions vrf <WORD> | xml'
    * 'show bgp <address_family>  labels vrf <WORD>'
    * 'show bgp <address_family>  labels vrf <WORD> | xml'
    * 'show bgp <address_family>  labels'
    * 'show bgp <address_family>  labels | xml'
"""

# Python
import re
from copy import deepcopy
import xml.etree.ElementTree as ET

# Metaparser
from metaparser import MetaParser
from metaparser.util.schemaengine import Schema, Any, Optional, Or, And,\
                                         Default, Use

# Parser
from parser.yang.bgp_openconfig_yang import BgpOpenconfigYang

# import parser utils
from parser.utils.common import Common


# =====================================
# Schema for 'show bgp process vrf all'
# =====================================
class ShowBgpProcessVrfAllSchema(MetaParser):
    """Schema for show bgp process vrf all"""

    schema = {
        'bgp_pid': int,
        'bgp_protocol_started_reason': str,
        Optional('bgp_performance_mode'): str,
        'bgp_tag': str,
        'bgp_protocol_state': str,
        Optional('bgp_isolate_mode'): str,
        Optional('bgp_mmode'): str,
        'bgp_memory_state': str,
        Optional('bgp_asformat'): str,
        Optional('segment_routing_global_block'): str,
        'num_attr_entries': int,
        'hwm_attr_entries': int,
        'bytes_used': int,
        'entries_pending_delete': int,
        'hwm_entries_pending_delete': int,
        'bgp_paths_per_hwm_attr': int,
        'bgp_as_path_entries': int,
        'bytes_used_as_path_entries': int,
        Optional('vrf'): 
            {Any(): 
                {'vrf_id': str,
                 'vrf_state': str,
                 Optional('router_id'): str,
                 Optional('conf_router_id'): str,
                 Optional('confed_id'): int,
                 Optional('cluster_id'): str,
                 'num_conf_peers': int,
                 'num_pending_conf_peers': int,
                 'num_established_peers': int,
                 Optional('vrf_rd'): str,
                 Optional('graceful_restart'): bool,
                 Optional('graceful_restart_helper_only'): bool,
                 Optional('graceful_restart_restart_time'): int,
                 Optional('graceful_restart_stalepath_time'): int,
                 Optional('address_family'): 
                    {Any(): 
                        {Optional('table_id'): str,
                         Optional('table_state'): str,
                         Optional('enabled'): bool,
                         Optional('graceful_restart'): bool,
                         Optional('advertise_inactive_routes'): bool,
                         Optional('ebgp_max_paths'): int,
                         Optional('ibgp_max_paths'): int,
                         Optional('total_paths'): int,
                         Optional('total_prefixes'): int,
                         Optional('peers'): 
                            {Any(): 
                                {'active_peers': int,
                                 'routes': int,
                                 'paths': int,
                                 'networks': int,
                                 'aggregates': int,
                                },
                            },
                         Optional('redistribution'): 
                            {Any(): 
                                {Optional('route_map'): str,
                                },
                            },
                         Optional('export_rt_list'): str,
                         Optional('import_rt_list'): str,
                         Optional('label_mode'): str,
                         Optional('aggregate_label'): str,
                         Optional('route_reflector'): bool,
                         Optional('next_hop_trigger_delay'):
                            {'critical': int,
                             'non_critical': int,
                            },
                        Optional('import_default_map'): str,
                        Optional('import_default_prefix_limit'): int,
                        Optional('import_default_prefix_count'): int,
                        Optional('export_default_map'): str,
                        Optional('export_default_prefix_limit'): int,
                        Optional('export_default_prefix_count'): int,
                        },
                    },
                },
            },
        }

# =====================================
# Parser for 'show bgp process vrf all'
# =====================================
class ShowBgpProcessVrfAll(ShowBgpProcessVrfAllSchema):
    """Parser for:
        show bgp process vrf all
        parser class - implements detail parsing mechanisms for cli,xml and yang output.
    """

    def cli(self):
        out = self.device.execute('show bgp process vrf all')
        
        # Init vars
        parsed_dict = {}

        for line in out.splitlines():
            line = line.replace('\t', '    ')
            line = line.rstrip()

            # BGP Process ID                 : 29474
            p1 = re.compile(r'^\s*BGP +Process +ID *: +(?P<bgp_pid>[0-9]+)$')
            m = p1.match(line)
            if m:
                parsed_dict['bgp_pid'] = int(m.groupdict()['bgp_pid'])
                continue

            # BGP Protocol Started, reason:  : configuration
            p2 = re.compile(r'^\s*BGP Protocol Started, +reason: *:'
                             ' +(?P<reason>[a-zA-Z\s]+)$')
            m = p2.match(line)
            if m:
                parsed_dict['bgp_protocol_started_reason'] = \
                    str(m.groupdict()['reason']).lower()
                continue

            # BGP Performance Mode:          : No
            p2_1 = re.compile(r'^\s*BGP +Performance +Mode: *:'
                               ' +(?P<performance_mode>[a-zA-Z\s]+)$')
            m = p2_1.match(line)
            if m:
                parsed_dict['bgp_performance_mode'] = \
                    str(m.groupdict()['performance_mode'])
                continue

            # BGP Protocol Tag               : 100
            p3 = re.compile(r'^\s*BGP +Protocol +Tag *:'
                             ' +(?P<bgp_tag>[a-zA-Z0-9]+)$')
            m = p3.match(line)
            if m:
                parsed_dict['bgp_tag'] = str(m.groupdict()['bgp_tag']).lower()
                continue

            # BGP Protocol State             : Running
            p4 = re.compile(r'^\s*BGP +Protocol +State *:'
                             ' +(?P<protocol_state>[a-zA-Z\(\)\s]+)$')
            m = p4.match(line)
            if m:
                parsed_dict['bgp_protocol_state'] = \
                    str(m.groupdict()['protocol_state']).lower()
                continue

            # BGP Isolate Mode               : No
            p4_1 = re.compile(r'^\s*BGP +Isolate +Mode *:'
                               ' +(?P<isolate_mode>[a-zA-Z\s]+)$')
            m = p4_1.match(line)
            if m:
                parsed_dict['bgp_isolate_mode'] = \
                    str(m.groupdict()['isolate_mode'])
                continue

            # BGP MMODE                      : Initialized
            p4_3 = re.compile(r'^\s*BGP +MMODE *:'
                               ' +(?P<mmode>[a-zA-Z\s]+)$')
            m = p4_3.match(line)
            if m:
                parsed_dict['bgp_mmode'] = str(m.groupdict()['mmode'])
                continue

            # BGP Memory State               : OK
            # BGP Memory State               : Severe Alert
            p5 = re.compile(r'^\s*BGP +Memory +State *:'
                             ' +(?P<memory_state>[\w\s]+)$')
            m = p5.match(line)
            if m:
                parsed_dict['bgp_memory_state'] = \
                    str(m.groupdict()['memory_state']).lower()
                continue

            # BGP asformat                   : asplain
            p5_1 = re.compile(r'^\s*BGP +asformat *:'
                               ' +(?P<asformat>[a-zA-Z\s]+)$')
            m = p5_1.match(line)
            if m:
                parsed_dict['bgp_asformat'] = str(m.groupdict()['asformat'])
                continue

            # Segment Routing Global Block   : 10000-25000
            p5_2 = re.compile(r'^\s*Segment +Routing +Global +Block *:'
                               ' +(?P<segment>[0-9\-]+)$')
            m = p5_2.match(line)
            if m:
                parsed_dict['segment_routing_global_block'] = \
                    str(m.groupdict()['segment'])
                continue

            # BGP attributes information
            # Number of attribute entries    : 4
            p6 = re.compile(r'^\s*Number +of +attribute +entries *:'
                             ' +(?P<num_attr_entries>[0-9]+)$')
            m = p6.match(line)
            if m:
                parsed_dict['num_attr_entries'] = \
                    int(m.groupdict()['num_attr_entries'])
                continue

            # HWM of attribute entries       : 5
            p7 = re.compile(r'^\s*HWM +of +attribute +entries *:'
                             ' +(?P<hwm_attr_entries>[0-9]+)$')
            m = p7.match(line)
            if m:
                parsed_dict['hwm_attr_entries'] = \
                    int(m.groupdict()['hwm_attr_entries'])
                continue

            # Bytes used by entries          : 368
            p8 = re.compile(r'^\s*Bytes +used +by +entries *:'
                             ' +(?P<bytes_used>[0-9]+)$')
            m = p8.match(line)
            if m:
                parsed_dict['bytes_used'] = int(m.groupdict()['bytes_used'])
                continue

            # Entries pending delete         : 0
            p9 = re.compile(r'^\s*Entries +pending +delete *:'
                             ' +(?P<entries_pending_delete>[0-9]+)$')
            m = p9.match(line)
            if m:
                parsed_dict['entries_pending_delete'] = \
                    int(m.groupdict()['entries_pending_delete'])
                continue

            # HWM of entries pending delete  : 0
            p10 = re.compile(r'^\s*HWM +of +entries +pending +delete *:'
                              ' +(?P<hwm_entries_pending_delete>[0-9]+)$')
            m = p10.match(line)
            if m:
                parsed_dict['hwm_entries_pending_delete'] = \
                    int(m.groupdict()['hwm_entries_pending_delete'])
                continue

            # BGP paths per attribute HWM    : 1
            p11 = re.compile(r'^\s*BGP +paths +per +attribute +HWM *:'
                              ' +(?P<bgp_paths_per_hwm_attr>[0-9]+)$')
            m = p11.match(line)
            if m:
                parsed_dict['bgp_paths_per_hwm_attr'] = \
                    int(m.groupdict()['bgp_paths_per_hwm_attr'])
                continue

            # BGP AS path entries            : 0
            p12 = re.compile(r'^\s*BGP +AS +path +entries *:'
                              ' +(?P<bgp_as_path_entries>[0-9]+)$')
            m = p12.match(line)
            if m:
                parsed_dict['bgp_as_path_entries'] = \
                    int(m.groupdict()['bgp_as_path_entries'])
                continue

            # Bytes used by AS path entries  : 0
            p13 = re.compile(r'^\s*Bytes +used +by +AS +path +entries *:'
                              ' +(?P<bytes_used_as_path_entries>[0-9]+)$')
            m = p13.match(line)
            if m:
                parsed_dict['bytes_used_as_path_entries'] = \
                    int(m.groupdict()['bytes_used_as_path_entries'])
                continue

            # BGP Information for VRF VRF1
            p14 = re.compile(r'^\s*BGP +Information +for +VRF'
                              ' +(?P<vrf_name>[a-zA-Z0-9]+)$')
            m = p14.match(line)
            if m:
                if 'vrf' not in parsed_dict:
                    parsed_dict['vrf'] = {}
                vrf_name = str(m.groupdict()['vrf_name'])
                if vrf_name not in parsed_dict['vrf']:
                    parsed_dict['vrf'][vrf_name] = {}
                    continue

            # VRF Id                         : 3
            p15 = re.compile(r'^\s*VRF +Id *:'
                              ' +(?P<vrf_id>[a-zA-Z0-9]+)$')
            m = p15.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['vrf_id'] = \
                    str(m.groupdict()['vrf_id'])
                continue

            # VRF state                      : UP
            p16 = re.compile(r'^\s*VRF +state *:'
                              ' +(?P<vrf_state>[a-zA-Z]+)$')
            m = p16.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['vrf_state'] = \
                    str(m.groupdict()['vrf_state']).lower()
                continue

            # Router-ID                      : 11.11.11.11
            p17 = re.compile(r'^\s*Router-ID *:'
                              ' +(?P<router_id>[0-9\.]+)$')
            m = p17.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['router_id'] = \
                    str(m.groupdict()['router_id'])
                continue

            # Configured Router-ID           : 0.0.0.0
            p18 = re.compile(r'^\s*Configured +Router-ID *:'
                              ' +(?P<conf_router_id>[0-9\.]+)$')
            m = p18.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['conf_router_id'] = \
                    str(m.groupdict()['conf_router_id'])
                continue

            # Confed-ID                      : 0
            p19 = re.compile(r'^\s*Confed-ID *:'
                              ' +(?P<confed_id>[0-9]+)$')
            m = p19.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['confed_id'] = \
                    int(m.groupdict()['confed_id'])
                continue

            # Cluster-ID                     : 0.0.0.0
            p20 = re.compile(r'^\s*Cluster-ID *:'
                              ' +(?P<cluster_id>[0-9\.]+)$')
            m = p20.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['cluster_id'] = \
                    str(m.groupdict()['cluster_id'])
                continue

            # No. of configured peers        : 1
            p21 = re.compile(r'^\s*No. +of +configured +peers *:'
                              ' +(?P<num_conf_peers>[0-9]+)$')
            m = p21.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['num_conf_peers'] = \
                    int(m.groupdict()['num_conf_peers'])
                continue
            
            # No. of pending config peers    : 0
            p22 = re.compile(r'^\s*No. +of +pending +config +peers *:'
                              ' +(?P<num_pending_conf_peers>[0-9]+)$')
            m = p22.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['num_pending_conf_peers'] = \
                    int(m.groupdict()['num_pending_conf_peers'])
                continue
            
            # No. of established peers       : 0
            p23 = re.compile(r'^\s*No. +of +established +peers *:'
                              ' +(?P<num_established_peers>[0-9]+)$')
            m = p23.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['num_established_peers'] = \
                    int(m.groupdict()['num_established_peers'])
                continue
            
            # VRF RD                         : 100:100
            p24 = re.compile(r'^\s*VRF +RD *:'
                              ' +(?P<vrf_rd>[a-zA-Z0-9\:\s]+)$')
            m = p24.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['vrf_rd'] = \
                    str(m.groupdict()['vrf_rd']).lower()
                continue

            #     Information for address family IPv4 Unicast in VRF VRF1
            p25 = re.compile(r'^\s*Information +for +address +family'
                               ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+)'
                               ' +in +VRF +(?P<vrf>[a-zA-Z0-9]+)$')
            m = p25.match(line)
            if m:
                if 'address_family' not in parsed_dict['vrf'][vrf_name]:
                    parsed_dict['vrf'][vrf_name]['address_family'] = {}

                address_family = str(m.groupdict()['address_family']).lower()
                
                vrf = str(m.groupdict()['vrf'])

                if address_family not in parsed_dict['vrf'][vrf_name]\
                    ['address_family'] and vrf == vrf_name:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family] = {}
                    # Init export/import RT variables
                    export_rt_found = False ; export_rt_values = ''
                    import_rt_found = False ; import_rt_values = ''
                    continue

            #     Table Id                   : 10
            #     Table Id                   : 0x80000001
            p26 = re.compile(r'^\s*Table +Id *: +(?P<table_id>(\S+))$')
            m = p26.match(line)
            if m:
                table_id = str(m.groupdict()['table_id'])
                if '0x' in table_id:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['table_id'] = table_id
                else:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['table_id'] = '0x' + table_id
                continue
            
            #     Table state                : UP
            p27 = re.compile(r'^\s*Table +state *: +(?P<table_state>[a-zA-Z]+)$')
            m = p27.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['table_state'] = str(m.groupdict()['table_state']).lower()
                continue

            #     Peers      Active-peers    Routes     Paths      Networks   Aggregates
            #     1          0               5          5          1          2      
            p28 = re.compile(r'^\s*(?P<peers>[0-9]+) +(?P<active_peers>[0-9]+)'
                              ' +(?P<routes>[0-9]+) +(?P<paths>[0-9]+)'
                              ' +(?P<networks>[0-9]+) +(?P<aggregates>[0-9]+)$')
            m = p28.match(line)
            if m:
                if 'peers' not in parsed_dict['vrf'][vrf_name]\
                    ['address_family'][address_family]:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'] = {}

                peers = int(m.groupdict()['peers'])

                if peers not in parsed_dict['vrf'][vrf_name]['address_family']\
                    [address_family]['peers']:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers] = {}
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers]['active_peers'] = \
                            int(m.groupdict()['active_peers'])
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers]['routes'] = \
                            int(m.groupdict()['routes'])
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers]['paths'] = \
                            int(m.groupdict()['paths'])
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers]['networks'] = \
                            int(m.groupdict()['networks'])
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['peers'][peers]['aggregates'] = \
                            int(m.groupdict()['aggregates'])
                    continue

            #     Redistribution                
            #         direct, route-map genie_redistribution
            #         static, route-map genie_redistribution
            #         eigrp, route-map test-map
            p29 = re.compile(r'^\s*(?P<name>[a-zA-Z]+),'
                              ' +route-map +(?P<route_map>[a-zA-Z0-9\-\_]+)$')
            m = p29.match(line)
            if m:
                if 'redistribution' not in parsed_dict['vrf'][vrf_name]\
                    ['address_family'][address_family]:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['redistribution'] = {}

                name = str(m.groupdict()['name']).lower()

                if name not in parsed_dict['vrf'][vrf_name]['address_family']\
                    [address_family]['redistribution']:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['redistribution'][name] = {}
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['redistribution'][name]\
                            ['route_map'] = str(m.groupdict()['route_map'])
                    continue
            
            #     Export RT list: 100:100
            p30 = re.compile(r'^\s*Export +RT +list *:'
                              '(?: +(?P<export_rt_list>[0-9\:]+))?$')
            m = p30.match(line)
            if m:
                export_rt_found = True
                import_rt_found = False
                if m.groupdict()['export_rt_list'] != None:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['export_rt_list'] = \
                            str(m.groupdict()['export_rt_list'])
                continue

            # Export RT list:
            #   100:1
            #   400:400
            p30_1 = re.compile(r'^\s*(?P<export_rt_list>(\d+)\:(\d+))$')
            m = p30_1.match(line)
            if m and export_rt_found:
                export_rt_values = export_rt_values + ' ' + str(m.groupdict()['export_rt_list'])
                parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['export_rt_list'] = export_rt_values.strip()

            #     Import RT list: 100:100
            p31 = re.compile(r'^\s*Import +RT +list *:'
                              '(?: +(?P<import_rt_list>[0-9\:]+))?$')
            m = p31.match(line)
            if m:
                import_rt_found = True
                export_rt_found = False
                if m.groupdict()['import_rt_list'] != None:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['import_rt_list'] = \
                            str(m.groupdict()['import_rt_list'])
                continue

            # Import RT list:
            #   100:1
            p31_1 = re.compile(r'^\s*(?P<import_rt_list>(\d+)\:(\d+))$')
            m = p31_1.match(line)
            if m and import_rt_found:
                import_rt_values = import_rt_values + ' ' + str(m.groupdict()['import_rt_list'])
                parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['import_rt_list'] = import_rt_values.strip()

            #     Label mode: per-prefix
            p32 = re.compile(r'^\s*Label +mode *: +(?P<label_mode>[a-zA-Z\-]+)$')
            m = p32.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['label_mode'] = str(m.groupdict()['label_mode'])
                continue

            #     Is a Route-reflector
            p32_1 = re.compile(r'^\s*Is +a +Route\-reflector$')
            m = p32_1.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['route_reflector'] = True
                continue

            #     Aggregate label: 492287
            p33 = re.compile(r'^\s*Aggregate +label *:'
                              ' +(?P<aggregate_label>[a-zA-Z0-9\-]+)$')
            m = p33.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['aggregate_label'] = str(m.groupdict()['aggregate_label'])
                continue

            # Import default limit       : 1000
            p34 = re.compile(r'^\s*Import +default +limit *:'
                              ' +(?P<import_default_prefix_limit>[0-9]+)$')
            m = p34.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['import_default_prefix_limit'] = \
                        int(m.groupdict()['import_default_prefix_limit'])
                continue

            # Import default prefix count : 3
            p35 = re.compile(r'^\s*Import +default +prefix +count *:'
                              ' +(?P<import_default_prefix_count>[0-9]+)$')
            m = p35.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['import_default_prefix_count'] = \
                        int(m.groupdict()['import_default_prefix_count'])

            # Import default map         : PERMIT_ALL_RM
            p36 = re.compile(r'^\s*Import +default +map *:'
                              ' +(?P<import_default_map>[a-zA-Z0-9\_\-]+)$')
            m = p36.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['import_default_map'] = \
                        str(m.groupdict()['import_default_map'])

            # Export default limit       : 1000
            p37 = re.compile(r'^\s*Export +default +limit *:'
                              ' +(?P<export_default_prefix_limit>[0-9]+)$')
            m = p37.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['export_default_prefix_limit'] = \
                        int(m.groupdict()['export_default_prefix_limit'])

            # Export default prefix count : 2
            p38 = re.compile(r'^\s*Export +default +prefix +count *:'
                              ' +(?P<export_default_prefix_count>[0-9]+)$')
            m = p38.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['export_default_prefix_count'] = \
                        int(m.groupdict()['export_default_prefix_count'])

            # Export default map         : PERMIT_ALL_RM
            p39 = re.compile(r'^\s*Export +default +map *:'
                              ' +(?P<export_default_map>[a-zA-Z0-9\_\-]+)$')
            m = p39.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family'][address_family]\
                    ['export_default_map'] = \
                        str(m.groupdict()['export_default_map'])

            # Nexthop trigger-delay
            p40 = re.compile(r'^\s*Nexthop +trigger-delay$')
            m = p40.match(line)
            if m:
                if 'next_hop_trigger_delay' not in parsed_dict['vrf'][vrf_name]\
                    ['address_family'][address_family]:
                    parsed_dict['vrf'][vrf_name]['address_family']\
                        [address_family]['next_hop_trigger_delay'] = {}

            # critical 3000 ms
            p41 = re.compile(r'^\s*critical +(?P<critical>[0-9]+) +ms$')
            m = p41.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family']\
                    [address_family]['next_hop_trigger_delay']['critical'] = \
                    int(m.groupdict()['critical'])

            # non-critical 3000 ms
            p42 = re.compile(r'^\s*non-critical +(?P<non_critical>[0-9]+) +ms$')
            m = p42.match(line)
            if m:
                parsed_dict['vrf'][vrf_name]['address_family']\
                    [address_family]['next_hop_trigger_delay']['non_critical'] = \
                        int(m.groupdict()['non_critical'])

        return parsed_dict

    def xml(self):
        out = self.device.execute('show bgp process vrf all | xml')

        etree_dict = {}
        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        output = ET.fromstring(out)

        for item in output:
            for data in item:
                for show in data:
                    for bgp in show:
                        for __XML__OPT_Cmd_show_ip_bgp_session_cmd_vrf in bgp:
                            for process in __XML__OPT_Cmd_show_ip_bgp_session_cmd_vrf:
                                for __XML__OPT_Cmd_show_bgp_process_cmd_vrf in process:
                                    for __XML__OPT_Cmd_show_bgp_process_cmd___readonly__ in __XML__OPT_Cmd_show_bgp_process_cmd_vrf:
                                        for key in __XML__OPT_Cmd_show_bgp_process_cmd___readonly__:
                                            # Get key text
                                            text = key.tag[key.tag.find('}')+1:]
                                            # bgp_pid
                                            if text == 'processid':
                                                etree_dict['bgp_pid'] = int(key.text)
                                            # bgp_protocol_started_reason
                                            if text == 'protocolstartedreason':
                                                etree_dict['bgp_protocol_started_reason'] = key.text
                                            # bgp_tag
                                            if text == 'protocoltag':
                                                etree_dict['bgp_tag'] = key.text
                                            # bgp_protocol_state
                                            if text == 'protocolstate':
                                                etree_dict['bgp_protocol_state'] = str(key.text).lower()
                                            # bgp_isolate_mode
                                            if text == 'isolatemode':
                                                etree_dict['bgp_isolate_mode'] = key.text
                                            # bgp_mmode
                                            if text == 'mmode':
                                                etree_dict['bgp_mmode'] = key.text
                                            # bgp_memory_state
                                            if text == 'memorystate':
                                                etree_dict['bgp_memory_state'] = str(key.text).lower()
                                            # bgp_performance_mode
                                            if text == 'forwardingstatesaved':
                                                if key.text == 'false':
                                                    etree_dict['bgp_performance_mode'] = 'No'
                                                else:
                                                    etree_dict['bgp_performance_mode'] = 'Yes'
                                            # bgp_asformat
                                            if text == 'asformat':
                                                etree_dict['bgp_asformat'] = key.text
                                            if text == 'srgbmin':
                                                srgbin = key.text
                                            if text == 'srgbmax':
                                                srgmax = key.text
                                                try:
                                                    etree_dict['segment_routing_global_block'] = srgbin + '-' + srgmax
                                                except:
                                                    pass
                                            # num_attr_entries
                                            if text == 'attributeentries':
                                                etree_dict['num_attr_entries'] = int(key.text)
                                            # hwm_attr_entries
                                            if text == 'hwmattributeentries':
                                                etree_dict['hwm_attr_entries'] = int(key.text)
                                            # bytes_used
                                            if text == 'bytesused':
                                                etree_dict['bytes_used'] = int(key.text)
                                            # entries_pending_delete
                                            if text == 'entriespendingdelete':
                                                etree_dict['entries_pending_delete'] = int(key.text)
                                            # hwm_entries_pending_delete
                                            if text == 'hwmentriespendingdelete':
                                                etree_dict['hwm_entries_pending_delete'] = int(key.text)
                                            # bgp_paths_per_hwm_attr
                                            if text == 'pathsperattribute':
                                                etree_dict['bgp_paths_per_hwm_attr'] = int(key.text)
                                            # bgp_as_path_entries
                                            if text == 'aspathentries':
                                                etree_dict['bgp_as_path_entries'] = int(key.text)
                                            # bytes_used_as_path_entries
                                            if text == 'aspathbytes':
                                                etree_dict['bytes_used_as_path_entries'] = int(key.text)
                                            
                                            if text == 'TABLE_vrf':
                                                for table_vrf in key:
                                                    for row_vrf in table_vrf:
                                                        vrf_tag = row_vrf.tag[row_vrf.tag.find('}')+1:]

                                                        # vrf
                                                        #   vrf_name
                                                        if vrf_tag == 'vrf-name-out':
                                                            vrf_name = row_vrf.text
                                                            if 'vrf' not in etree_dict:
                                                                etree_dict['vrf'] = {}
                                                            if vrf_name not in etree_dict['vrf']:
                                                                etree_dict['vrf'][vrf_name] = {}
                                                                vrf_dict = etree_dict['vrf'][vrf_name]
                                                        # vrf_id
                                                        if vrf_tag == 'vrf-id':
                                                            vrf_dict['vrf_id'] = row_vrf.text
                                                        # vrf_state
                                                        if vrf_tag == 'vrf-state':
                                                            vrf_dict['vrf_state'] = str(row_vrf.text).lower()
                                                        # router_id
                                                        if vrf_tag == 'vrf-router-id':
                                                            vrf_dict['router_id'] = row_vrf.text
                                                        # conf_router_id
                                                        if vrf_tag == 'vrf-cfgd-id':
                                                            vrf_dict['conf_router_id'] = row_vrf.text
                                                        # confed_id
                                                        if vrf_tag == 'vrf-confed-id':
                                                            vrf_dict['confed_id'] = int(row_vrf.text)
                                                        # cluster_id
                                                        if vrf_tag == 'vrf-cluster-id':
                                                           vrf_dict['cluster_id'] = row_vrf.text
                                                        # num_conf_peers
                                                        if vrf_tag == 'vrf-peers':
                                                            vrf_dict['num_conf_peers'] = int(row_vrf.text)
                                                        # num_pending_conf_peers
                                                        if vrf_tag == 'vrf-pending-peers':
                                                            vrf_dict['num_pending_conf_peers'] = int(row_vrf.text)
                                                        # num_established_peers
                                                        if vrf_tag == 'vrf-est-peers':
                                                            vrf_dict['num_established_peers'] = int(row_vrf.text)
                                                            vrf_dict['vrf_rd'] = 'not configured'
                                                        # vrf_rd
                                                        if vrf_tag == 'vrf-rd':
                                                            vrf_dict['vrf_rd'] = row_vrf.text

                                                        if vrf_tag == 'TABLE_af':
                                                            for table_af in row_vrf:
                                                                for row_af in table_af:
                                                                    af_tag = row_af.tag[row_af.tag.find('}')+1:]

                                                                    # address_family
                                                                    #   address_family_name
                                                                    if af_tag == 'af-name':
                                                                        address_family_name = str(row_af.text).lower()
                                                                        if 'address_family' not in etree_dict['vrf'][vrf_name]:
                                                                            etree_dict['vrf'][vrf_name]['address_family'] = {}
                                                                        if address_family_name not in etree_dict['vrf'][vrf_name]['address_family']:
                                                                            etree_dict['vrf'][vrf_name]['address_family'][address_family_name] = {}
                                                                            af_dict = etree_dict['vrf'][vrf_name]['address_family'][address_family_name]
                                                                        # Initialize empty lists
                                                                        export_rt_list = ''
                                                                        import_rt_list = ''
                                                                    # table_id
                                                                    if af_tag == 'af-table-id':
                                                                        table_id = str(row_af.text)
                                                                        if '0x' in table_id:
                                                                            af_dict['table_id'] = table_id
                                                                        else:
                                                                            af_dict['table_id'] = '0x' + table_id
                                                                    # table_state
                                                                    if af_tag == 'af-state':
                                                                        af_dict['table_state'] = str(row_af.text).lower()
                                                                    # peers
                                                                    if af_tag == 'af-num-peers':
                                                                        peers = int(row_af.text)
                                                                        if 'peers' not in af_dict:
                                                                            af_dict['peers'] = {}
                                                                        if peers not in af_dict['peers']:
                                                                            af_dict['peers'][peers] = {}
                                                                    # active_peers
                                                                    if af_tag == 'af-num-active-peers':
                                                                        af_dict['peers'][peers]['active_peers'] = int(row_af.text)
                                                                    # routes
                                                                    if af_tag == 'af-peer-routes':
                                                                        af_dict['peers'][peers]['routes'] = int(row_af.text)
                                                                    # paths
                                                                    if af_tag == 'af-peer-paths':
                                                                        af_dict['peers'][peers]['paths'] = int(row_af.text)
                                                                    # networks
                                                                    if af_tag == 'af-peer-networks':
                                                                        af_dict['peers'][peers]['networks'] = int(row_af.text)
                                                                    # aggregates
                                                                    if af_tag == 'af-peer-aggregates':
                                                                        af_dict['peers'][peers]['aggregates'] = int(row_af.text)
                                                                    # route_reflector
                                                                    if af_tag == 'af-rr':
                                                                        if row_af.text == 'true':
                                                                            af_dict['route_reflector'] = True
                                                                    # next_hop_trigger_delay
                                                                    #   critical
                                                                    if af_tag == 'nexthop-trigger-delay-critical':
                                                                        if 'next_hop_trigger_delay' not in af_dict:
                                                                            af_dict['next_hop_trigger_delay'] = {}
                                                                        af_dict['next_hop_trigger_delay']['critical'] = int(row_af.text)
                                                                    # next_hop_trigger_delay
                                                                    #   non_critical
                                                                    if af_tag == 'nexthop-trigger-delay-non-critical':
                                                                        af_dict['next_hop_trigger_delay']['non_critical'] = int(row_af.text)
                                                                    # aggregate_label
                                                                    if af_tag == 'af-aggregate-label':
                                                                        af_dict['aggregate_label'] = row_af.text
                                                                    # label_mode
                                                                    if af_tag == 'af-label-mode':
                                                                        af_dict['label_mode'] = row_af.text
                                                                    # import_default_map
                                                                    if af_tag == 'importdefault_map':
                                                                        af_dict['import_default_map'] = row_af.text
                                                                    # import_default_prefix_limit
                                                                    if af_tag == 'importdefault_prefixlimit':
                                                                        af_dict['import_default_prefix_limit'] = int(row_af.text)
                                                                    # import_default_prefix_count
                                                                    if af_tag == 'importdefault_prefixcount':
                                                                        af_dict['import_default_prefix_count'] = int(row_af.text)
                                                                    # export_default_map
                                                                    if af_tag == 'exportdefault_map':
                                                                        af_dict['export_default_map'] = row_af.text
                                                                    # export_default_prefix_limit
                                                                    if af_tag == 'exportdefault_prefixlimit':
                                                                        af_dict['export_default_prefix_limit'] = int(row_af.text)
                                                                    # export_default_prefix_count
                                                                    if af_tag == 'exportdefault_prefixcount':
                                                                        af_dict['export_default_prefix_count'] = int(row_af.text)

                                                                    # TABLE_redist
                                                                    #   ROW_redist
                                                                    if af_tag == 'TABLE_redist':
                                                                        for table_redist in row_af:
                                                                            for row_redist in table_redist:
                                                                                row_redist_tag = row_redist.tag[row_redist.tag.find('}')+1:]
                                                                                # protocol
                                                                                if row_redist_tag == 'protocol':
                                                                                    protocol = row_redist.text
                                                                                    if 'redistribution' not in af_dict:
                                                                                        af_dict['redistribution'] = {}
                                                                                    if protocol not in af_dict['redistribution']:
                                                                                        af_dict['redistribution'][protocol] = {}
                                                                                # route_map
                                                                                if row_redist_tag == 'route-map':
                                                                                    af_dict['redistribution'][protocol]['route_map'] = row_redist.text

                                                                    # TABLE_evpn_export_rt
                                                                    #   ROW_evpn_export_rt
                                                                    if af_tag == 'TABLE_evpn_export_rt':
                                                                        for table_evpn_export in row_af:
                                                                            for row_export in table_evpn_export:
                                                                                row_export_tag = row_export.tag[row_export.tag.find('}')+1:]
                                                                                # export_rt_list
                                                                                if row_export_tag == 'evpn-export-rt':
                                                                                    export_rt_list = str(export_rt_list + ' ' + row_export.text).strip()
                                                                                    af_dict['export_rt_list'] = export_rt_list
                                                                    # TABLE_evpn_import_rt
                                                                    #   ROW_evpn_import_rt
                                                                    if af_tag == 'TABLE_evpn_import_rt':
                                                                        for table_evpn_import in row_af:
                                                                            for row_import in table_evpn_import:
                                                                                row_import_tag = row_import.tag[row_import.tag.find('}')+1:]
                                                                                # export_rt_list
                                                                                if row_import_tag == 'evpn-import-rt':
                                                                                    import_rt_list = str(import_rt_list + ' ' + row_import.text).strip()
                                                                                    af_dict['import_rt_list'] = import_rt_list

                                                                    # parsed all tags
                                                                    continue
                                                                                    
        return etree_dict

    def yang(self):
        # Initialize empty dictionary
        map_dict = {}

        # Execute YANG 'get' operational state RPC and parse the XML
        bgpOC = BgpOpenconfigYang(self.device)
        yang_dict = bgpOC.yang()

        # Map keys from yang_dict to map_dict

        # bgp_pid
        map_dict['bgp_pid'] = yang_dict['bgp_pid']

        # vrf
        for vrf in yang_dict['vrf']:
            if 'vrf' not in map_dict:
                map_dict['vrf'] = {}
            if vrf not in map_dict['vrf']:
                map_dict['vrf'][vrf] = {}
            for vrf_attr_key in yang_dict['vrf'][vrf]:
                # Set router_id
                if vrf_attr_key == 'router_id':
                    map_dict['vrf'][vrf][vrf_attr_key] = yang_dict['vrf'][vrf][vrf_attr_key]
                # Set address_family
                if vrf_attr_key == 'address_family':
                    map_dict['vrf'][vrf][vrf_attr_key] = yang_dict['vrf'][vrf][vrf_attr_key]
                if vrf_attr_key == 'neighbor':
                    for nbr in yang_dict['vrf'][vrf]['neighbor']:
                        for key in yang_dict['vrf'][vrf]['neighbor'][nbr]:
                            # Set cluster_id
                            if key == 'route_reflector_cluster_id':
                                cluster_id = '0.0.0' + str(yang_dict['vrf'][vrf]['neighbor'][nbr]['route_reflector_cluster_id'])
                                map_dict['vrf'][vrf]['cluster_id'] = cluster_id

        # Return to caller
        return map_dict


# =========================================
# Schema for 'show bgp peer-session <WORD>'
# =========================================
class ShowBgpPeerSessionSchema(MetaParser):
    """Schema for show bgp peer-session <peer_session>"""

    schema = {
        'peer_session': 
            {Any(): 
                {Optional('shutdown'): bool,
                 Optional('update_source'): str,
                 Optional('description'): str,
                 Optional('password'): bool,
                 Optional('ebgp_multihop_enable'): bool,
                 Optional('ebgp_multihop_limit'): int,
                 Optional('disable_connectivity_check'): bool,
                 Optional('suppress_capabilities'): bool,
                 Optional('transport_connection_mode'): str,
                 Optional('holdtime'): int,
                 Optional('keepalive'): int,
                 Optional('remote_as'): bool,
                 Optional('local_as'): bool,
                 Optional('bfd'): bool,
                 Optional('inherited_vrf_default'): str,
                },
            },
        }

# =========================================
# Parser for 'show bgp peer-session <WORD>'
# =========================================
class ShowBgpPeerSession(ShowBgpPeerSessionSchema):

    """Parser for:
        show bgp peer-session <peer_session>
        Executing 'show running-config bgp | inc peer-session' to collect
        configured peer-session names.
    """

    def cli(self):
        
        # Execute 'show running' command to collect peer-sessions
        cmd = 'show running-config | inc peer-session'
        out = self.device.execute(cmd)
        
        # Init vars
        peer_sessions = []
        parsed_dict = {}

        for line in out.splitlines():
            line = line.rstrip()

            # template peer-session PEER-SESSION
            p1 = re.compile(r'^\s*template +peer-session '
                             '+(?P<session_name>[a-zA-Z\-\_]+)$')
            m = p1.match(line)
            if m:
                # Create top level key
                if 'peer_session' not in parsed_dict:
                    parsed_dict['peer_session'] = {}
                # Get session name and save it for later
                peer_sessions.append(str(m.groupdict()['session_name']))
                continue

        if peer_sessions:
            
            # Execute bgp show command now
            for session in peer_sessions:
                
                # Create session key
                if session not in parsed_dict['peer_session']:
                    parsed_dict['peer_session'][session] = {}
                    sub_dict = parsed_dict['peer_session'][session]
                
                base_cmd = 'show bgp peer-session ' + session
                cmd = base_cmd
                out = self.device.execute(cmd)

                for line in out.splitlines():
                    line = line.rstrip()

                    # Commands configured in this template:
                    # Shutdown
                    r1 = re.compile(r'^\s*Shutdown$')
                    m = r1.match(line)
                    if m:
                        sub_dict['shutdown'] = True
                        continue
                  
                    # Update Source - interface: loopback0
                    r2 = re.compile(r'^\s*Update +Source +-'
                                     ' +(?P<update_source>[a-zA-Z0-9\:\s]+)$')
                    m = r2.match(line)
                    if m:
                        sub_dict['update_source'] = \
                            str(m.groupdict()['update_source']).lower()
                        continue
                  
                    # Description - description: PEER-SESSION
                    r3 = re.compile(r'^\s*Description +- +description *:'
                                     ' +(?P<desc>[a-zA-Z\-]+)$')
                    m = r3.match(line)
                    if m:
                        sub_dict['description'] = \
                            str(m.groupdict()['desc'])
                        continue
                  
                    # Password
                    r4 = re.compile(r'^\s*Password$')
                    m = r4.match(line)
                    if m:
                        sub_dict['password'] = True
                        continue
                  
                    # EBGP Multihop - hop limit: 255
                    r5 = re.compile(r'^\s*EBGP +Multihop +- +hop +limit *:'
                                     ' +(?P<ebgp_multihop_limit>[0-9]+)$')
                    m = r5.match(line)
                    if m:
                        sub_dict['ebgp_multihop_enable'] = True
                        sub_dict['ebgp_multihop_limit'] = \
                            int(m.groupdict()['ebgp_multihop_limit'])
                        continue
                  
                    # Disable Connectivity Check
                    r6 = re.compile(r'^\s*Disable +Connectivity +Check$')
                    m = r6.match(line)
                    if m:
                        sub_dict['disable_connectivity_check'] = True
                        continue
                    
                    # Suppress Capabilities
                    r7 = re.compile(r'^\s*Suppress +Capabilities$')
                    m = r7.match(line)
                    if m:
                        sub_dict['suppress_capabilities'] = True
                        continue
                  
                    # Passive Only
                    r8 = re.compile(r'^\s*Passive Only$')
                    m = r8.match(line)
                    if m:
                        sub_dict['transport_connection_mode'] = 'Passive'
                        continue
                  
                    # Timers - hold time: 111, keepalive: 222
                    r9 = re.compile(r'^\s*Timers +- +hold +time *:'
                                     ' +(?P<holdtime>[0-9]+), keepalive *:'
                                     ' +(?P<keepalive>[0-9]+)$')
                    m = r9.match(line)
                    if m:
                        sub_dict['holdtime'] = int(m.groupdict()['holdtime'])
                        sub_dict['keepalive'] = int(m.groupdict()['keepalive'])
                        continue
                    
                    # Remote AS
                    r10 = re.compile(r'^\s*Remote AS$')
                    m = r10.match(line)
                    if m:
                        sub_dict['remote_as'] = True
                        continue
                  
                    # Local AS
                    r11 = re.compile(r'^\s*Local AS$')
                    m = r11.match(line)
                    if m:
                        sub_dict['local_as'] = True
                        continue
                  
                    # Enable Bfd
                    r12 = re.compile(r'^\s*Enable Bfd$')
                    m = r12.match(line)
                    if m:
                        sub_dict['bfd'] = True
                        continue
                
                    # Inherited commands:
                    # Inherited by the following peers:
                    # VRF default: 2.2.2.5
                    r13 = re.compile(r'^\s*VRF +default *:'
                                     ' +(?P<vrf_default>[0-9\.]+)$')
                    m = r13.match(line)
                    if m:
                        sub_dict['inherited_vrf_default'] = \
                            str(m.groupdict()['vrf_default'])
                        continue

        # Return parsed output
        return parsed_dict


# ========================================
# Schema for 'show bgp peer-policy <WORD>'
# ========================================
class ShowBgpPeerPolicySchema(MetaParser):
    """Schema for show bgp peer-policy <peer_policy>"""

    schema = {
        'peer_policy': 
            {Any(): 
                {Optional('send_community'): bool,
                 Optional('send_ext_community'): bool,
                 Optional('route_reflector_client'): bool,
                 Optional('route_map_name_in'): str,
                 Optional('route_map_name_out'): str,
                 Optional('maximum_prefix_max_prefix_no'): int,
                 Optional('default_originate'): bool,
                 Optional('default_originate_route_map'): str,
                 Optional('soft_reconfiguration'): bool,
                 Optional('site_of_origin'): bool,
                 Optional('allowas_in'): bool,
                 Optional('as_override'): bool,
                 Optional('inherited_vrf_default'): str,
                 Optional('next_hop_self'): bool,
                },
            },
        }

# ========================================
# Parser for 'show bgp peer-policy <WORD>'
# ========================================
class ShowBgpPeerPolicy(ShowBgpPeerPolicySchema):
    """Parser for:
        show bgp peer-policy <peer_policy>
        Executing 'show running-config bgp | inc peer-policy' to collect
        configured peer-policy names.
    """

    def cli(self):
        
        # Execute 'show running' command to collect peer-sessions
        cmd = 'show running-config | inc peer-policy'
        out = self.device.execute(cmd)
        
        # Init vars
        policy_names = []
        parsed_dict = {}

        for line in out.splitlines():
            line = line.rstrip()

            # template peer-policy PEER-POLICY
            p1 = re.compile(r'^\s*template +peer-policy'
                             ' +(?P<policy_name>[a-zA-Z0-9\-\_]+)$')
            m = p1.match(line)
            if m:
                # Get session name and save it for later
                policy_names.append(str(m.groupdict()['policy_name']))
                
                # Create top level key
                if 'peer_policy' not in parsed_dict:
                    parsed_dict['peer_policy'] = {}
                
                continue

        if policy_names:
            
            # Execute bgp show command now
            for policy_name in policy_names:
                
                # Create policy_name key
                if policy_name not in parsed_dict['peer_policy']:
                    parsed_dict['peer_policy'][policy_name] = {}
                    sub_dict = parsed_dict['peer_policy'][policy_name]
                
                base_cmd = 'show bgp peer-policy ' + policy_name
                cmd = base_cmd
                out = self.device.execute(cmd)

                for line in out.splitlines():
                    line = line.rstrip()

                    # Commands configured in this template:
                    # Send Community
                    r1 = re.compile(r'^\s*Send +Community$')
                    m = r1.match(line)
                    if m:
                        sub_dict['send_community'] = True
                        continue
                  
                    # Send Ext-community
                    r2 = re.compile(r'^\s*Send +Ext-community$')
                    m = r2.match(line)
                    if m:
                        sub_dict['send_ext_community'] = True
                        continue
                  
                    # Route Reflector Client
                    r3 = re.compile(r'^\s*Route +Reflector +Client$')
                    m = r3.match(line)
                    if m:
                        sub_dict['route_reflector_client'] = True
                        continue
                  
                    # Route-map Inbound - policy-name: test-map
                    r4 = re.compile(r'^\s*Route-map +Inbound +- +policy-name *:'
                                     ' +(?P<inbound_name>[a-zA-Z\-]+)$')
                    m = r4.match(line)
                    if m:
                        sub_dict['route_map_name_in'] = \
                            str(m.groupdict()['inbound_name'])
                        continue
                  
                    # Route-map Outbound - policy-name: test-map
                    r5 = re.compile(r'^\s*Route-map +Outbound +- +policy-name *:'
                                     ' +(?P<outbound_name>[a-zA-Z\-]+)$')
                    m = r5.match(line)
                    if m:
                        sub_dict['route_map_name_out'] = \
                            str(m.groupdict()['outbound_name'])
                  
                    # Maximum Prefixes - prefix limit: 300
                    r6 = re.compile(r'^\s*Maximum +Prefixes +- +prefix +limit *:'
                                     ' +(?P<max_prefix_no>[0-9]+)$')
                    m = r6.match(line)
                    if m:
                        sub_dict['maximum_prefix_max_prefix_no'] = \
                            int(m.groupdict()['max_prefix_no'])
                        continue
                    
                    # Default Originate - route-map: test
                    r7 = re.compile(r'^\s*Default +Originate(?: +- +route-map *:'
                                     ' +(?P<route_map>[a-zA-Z]+))?$')
                    m = r7.match(line)
                    if m:
                        sub_dict['default_originate'] =  True
                        sub_dict['default_originate_route_map'] = \
                            str(m.groupdict()['route_map'])
                        continue
                  
                    # Soft-Reconfig
                    r8 = re.compile(r'^\s*Soft-Reconfig$')
                    m = r8.match(line)
                    if m:
                        sub_dict['soft_reconfiguration'] = True
                        continue
                  
                    # Site-of-origin
                    r9 = re.compile(r'^\s*Site-of-origin$')
                    m = r9.match(line)
                    if m:
                        sub_dict['site_of_origin'] = True
                        continue
                    
                    # Allowas-in
                    r10 = re.compile(r'^\s*Allowas-in$')
                    m = r10.match(line)
                    if m:
                        sub_dict['allowas_in'] = True
                        continue
                  
                    # AS-override
                    r11 = re.compile(r'^\s*AS-override$')
                    m = r11.match(line)
                    if m:
                        sub_dict['as_override'] = True
                        continue
                
                    # Inherited commands:
                    # Inherited by the following peers:
                    # VRF default: 2.2.2.5
                    r12 = re.compile(r'^\s*VRF +default *:'
                                     ' +(?P<vrf_default>[0-9\.]+)$')
                    m = r12.match(line)
                    if m:
                        sub_dict['inherited_vrf_default'] = \
                            str(m.groupdict()['vrf_default'])
                        continue

                    # Nexthop Self
                    r13 = re.compile(r'^\s*Nexthop +Self$')
                    m = r13.match(line)
                    if m:
                        sub_dict['next_hop_self'] = True
                        continue

        # Return parsed output
        return parsed_dict


# ===================================================
# Schema for 'show bgp peer-template <peer_template>'
# ===================================================
class ShowBgpPeerTemplateSchema(MetaParser):
    """Schema for show bgp peer-template <peer_template>"""

    schema = {
        'peer_template':
            {Any():
                {Optional('remote_as'): int,
                Optional('inherit_template'): str,
                Optional('description'): str,
                Optional('update_source'): str,
                Optional('disable_connected_check'): bool,
                Optional('bfd_live_detection'): bool,
                Optional('num_hops_bgp_peer'): int,
                Optional('tcp_md5_auth'): str,
                Optional('nbr_transport_connection_mode'): str,
                Optional('nbr_local_as_cmd'): str,
                Optional('private_as_updates'): bool,
                Optional('holdtime'): int,
                Optional('keepalive_interval'): int,
                },
            },
        }

# ===================================================
# Parser for 'show bgp peer-template <peer_template>'
# ===================================================
class ShowBgpPeerTemplate(ShowBgpPeerTemplateSchema):

    '''Parser for show bgp peer-template <peer_template>
       Executing 'show running-config bgp | inc peer' to colllect
       configured peer-template names.
    '''

    def cli(self):
        
        # Execute 'show running' command to collect peer templates
        cmd = 'show running-config | inc peer'
        out = self.device.execute(cmd)
        
        # Init vars
        peer_templates = []
        parsed_dict = {}

        for line in out.splitlines():
            line = line.rstrip()

            # template peer PEER
            p1 = re.compile(r'^\s*template +peer'
                             ' +(?P<peer_template>[a-zA-Z0-9\-\_]+)$')
            m = p1.match(line)
            if m:
                # Get session name and save it for later
                peer_templates.append(str(m.groupdict()['peer_template']))
                
                # Create top level key
                if 'peer_template' not in parsed_dict:
                    parsed_dict['peer_template'] = {}
                continue

        if peer_templates:
            
            # Execute bgp show command now
            for peer_template in peer_templates:
                
                # Create template_names key
                if peer_template not in parsed_dict['peer_template']:
                    parsed_dict['peer_template'][peer_template] = {}
                    sub_dict = parsed_dict['peer_template'][peer_template]
                
                base_cmd = 'show bgp peer-template ' + peer_template
                cmd = base_cmd
                out = self.device.execute(cmd)

                for line in out.splitlines():
                    line = line.rstrip()

                    # BGP peer-template is PEER
                    # Remote AS 500
                    p1 = re.compile(r'^\s*Remote +AS +(?P<remote_as>[0-9]+)$')
                    m = p1.match(line)
                    if m:
                        sub_dict['remote_as'] = int(m.groupdict()['remote_as'])
                        continue

                    # Inherits session configuration from session-template PEER-SESSION
                    p2 = re.compile(r'^\s*Inherits +session +configuration'
                                     ' +from session-template'
                                     ' +(?P<inherit_template>(\S+))$')
                    m = p2.match(line)
                    if m:
                        sub_dict['inherit_template'] = \
                            str(m.groupdict()['inherit_template'])
                        continue

                    # Description: DESC
                    p3 = re.compile(r'^\s*Description *: +(?P<desc>(\S+))$')
                    m = p3.match(line)
                    if m:
                        sub_dict['description'] = str(m.groupdict()['desc'])
                        continue

                    # Using loopback1 as update source for this peer
                    p4 = re.compile(r'^\s*Using +(?P<update_source>(\S+)) +as'
                                     ' +update +source +for +this +peer$')
                    m = p4.match(line)
                    if m:
                        sub_dict['update_source'] = \
                            str(m.groupdict()['update_source'])
                        continue

                    # Connected check is disabled
                    p5 = re.compile(r'^\s*Connected check is disabled$')
                    m = p5.match(line)
                    if m:
                        sub_dict['disable_connected_check'] = True
                        continue

                    # BFD live-detection is configured
                    p6 = re.compile(r'^\s*BFD live-detection +is +configured$')
                    m = p6.match(line)
                    if m:
                        sub_dict['bfd_live_detection'] = True
                        continue

                    # External BGP peer might be upto 255 hops away
                    p7 = re.compile(r'^\s*External +BGP +peer +might +be +upto'
                                     ' +(?P<num_hops_bgp_peer>[0-9]+) +hops'
                                     ' +away$')
                    m = p7.match(line)
                    if m:
                        sub_dict['num_hops_bgp_peer'] = \
                            int(m.groupdict()['num_hops_bgp_peer'])
                        continue

                    # TCP MD5 authentication is enabled
                    p8 = re.compile(r'^\s*TCP +MD5 +authentication +is'
                                     ' +(?P<tcp_md5_auth>(\S+))$')
                    m = p8.match(line)
                    if m:
                        sub_dict['tcp_md5_auth'] = \
                            str(m.groupdict()['tcp_md5_auth'])
                        continue

                    # Only passive connection setup allowed
                    p9 = re.compile(r'^\s*Only +passive +connection +setup'
                                     ' +allowed$')
                    m = p9.match(line)
                    if m:
                        sub_dict['nbr_transport_connection_mode'] = 'Passive'
                        continue

                    # Neighbor local-as command not active
                    p10 = re.compile(r'^\s*Neighbor +local-as +command'
                                      ' +(?P<nbr_local_as_cmd>(\S+))$')
                    m = p10.match(line)
                    if m:
                        sub_dict['nbr_local_as_cmd'] = \
                            str(m.groupdict()['nbr_local_as_cmd'])
                        continue

                    # Private AS numbers removed from updates sent to this neighbor
                    p11 = re.compile(r'^\s*Private +AS +numbers +removed +from'
                                      ' +updates +sent +to +this +neighbor$')
                    m = p11.match(line)
                    if m:
                        sub_dict['private_as_updates'] = False
                        continue

                    # Hold time = 26, keepalive interval is 13 seconds
                    p12 = re.compile(r'^\s*Hold +time += +(?P<holdtime>[0-9]+),'
                                      ' +keepalive +interval +is'
                                      ' +(?P<keepalive_interval>[0-9]+)'
                                      ' +seconds$')
                    m = p12.match(line)
                    if m:
                        sub_dict['holdtime'] = \
                            int(m.groupdict()['holdtime'])
                        sub_dict['keepalive_interval'] = \
                            int(m.groupdict()['keepalive_interval'])
                        continue


        # Return parsed output
        return parsed_dict


# =================================
# Schema for 'show bgp vrf all all'
# =================================
class ShowBgpVrfAllAllSchema(MetaParser):
    """Schema for show bgp vrf all all"""

    schema = {
        'vrf': 
            {Any(): 
                {'address_family': 
                    {Any(): 
                        {'bgp_table_version': int,
                         'local_router_id': str,
                         Optional('route_distinguisher'): str,
                         Optional('default_vrf'): str,
                         Optional('aggregate_address_ipv4_address'): str,
                         Optional('aggregate_address_ipv4_mask'): str,
                         Optional('aggregate_address_as_set'): bool,
                         Optional('aggregate_address_summary_only'): bool,
                         Optional('v6_aggregate_address_ipv6_address'): str,
                         Optional('v6_aggregate_address_as_set'): bool,
                         Optional('v6_aggregate_address_summary_only'): bool,
                         Optional('prefixes'):
                            {Any(): 
                                {'index': 
                                    {Any(): 
                                        {'next_hop': str,
                                         Optional('status_codes'): str,
                                         Optional('path_type'): str,
                                         Optional('metric'): int,
                                         Optional('localprf'): int,
                                         Optional('weight'): int,
                                         Optional('path'): str,
                                         Optional('origin_codes'): str,
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

# =================================
# Parser for 'show bgp vrf all all'
# =================================
class ShowBgpVrfAllAll(ShowBgpVrfAllAllSchema):
    """Parser for show bgp vrf all all"""

    def cli(self):
        cmd = 'show bgp vrf all all'
        out = self.device.execute(cmd)
        
        # Init dictionary
        parsed_dict = {}
        af_dict = {}

        # Init vars
        index = 1
        data_on_nextline = False
        bgp_table_version = local_router_id = ''

        for line in out.splitlines():
            line = line.rstrip()

            # BGP routing table information for VRF VRF1, address family IPv4 Unicast
            p1 = re.compile(r'^\s*BGP +routing +table +information +for +VRF'
                             ' +(?P<vrf_name>[a-zA-Z0-9\-]+), +address +family'
                             ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+)$')
            m = p1.match(line)
            if m:
                # Get values
                vrf = str(m.groupdict()['vrf_name'])
                address_family = str(m.groupdict()['address_family']).lower()
                original_address_family = address_family
                if 'vrf' not in parsed_dict:
                    parsed_dict['vrf'] = {}
                if vrf not in parsed_dict['vrf']:
                    parsed_dict['vrf'][vrf] = {}
                if 'address_family' not in parsed_dict['vrf'][vrf]:
                    parsed_dict['vrf'][vrf]['address_family'] = {}
                if address_family not in parsed_dict['vrf'][vrf]\
                    ['address_family']:
                    parsed_dict['vrf'][vrf]['address_family'][address_family] = {}

                # Set af_dict
                af_dict = parsed_dict['vrf'][vrf]['address_family'][address_family]
                continue

            # BGP table version is 35, local router ID is 11.11.11.11
            # BGP table version is 381, Local Router ID is 1.1.1.2
            p2 = re.compile(r'^\s*BGP +table +version +is'
                             ' +(?P<bgp_table_version>[0-9]+), +(L|l)ocal'
                             ' +(R|r)outer +ID +is +(?P<local_router_id>[0-9\.]+)$')
            m = p2.match(line)
            if m:
                bgp_table_version = int(m.groupdict()['bgp_table_version'])
                local_router_id = str(m.groupdict()['local_router_id'])
                af_dict['bgp_table_version'] = bgp_table_version
                af_dict['local_router_id'] = local_router_id
                continue

            # Status: s-suppressed, x-deleted, S-stale, d-dampened, h-history, *-valid, >-best
            # Path type: i-internal, e-external, c-confed, l-local, a-aggregate, r-redist
            # Origin codes: i - IGP, e - EGP, ? - incomplete, | - multipath
            # Network            Next Hop         Metric   LocPrf   Weight Path

            # *>i[2]:[77][7,0][9.9.9.9,1,151587081][29.1.1.1,22][19.0.101.1,29.0.1.30]/616
            # *>iaaaa:1::/113       ::ffff:19.0.101.1
            p3_1 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)?'
                             '(?P<path_type>(i|e|c|l|a|r|I))?'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             '(?: *(?P<next_hop>[a-zA-Z0-9\.\:\/\[\]\,]+))?$')
            m = p3_1.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                data_on_nextline = True

                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])

                # Init dict
                if 'prefixes' not in af_dict:
                    af_dict['prefixes'] = {}
                if prefix not in af_dict['prefixes']:
                    af_dict['prefixes'][prefix] = {}
                if 'index' not in af_dict['prefixes'][prefix]:
                    af_dict['prefixes'][prefix]['index'] = {}
                if index not in af_dict['prefixes'][prefix]['index']:
                    af_dict['prefixes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['prefixes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['prefixes'][prefix]['index'][index]['path_type'] = path_type
                if m.groupdict()['next_hop']:
                    af_dict['prefixes'][prefix]['index'][index]['next_hop'] = str(m.groupdict()['next_hop'])
                
                # Check if aggregate_address_ipv4_address
                if 'a' in path_type:
                    address, mask = prefix.split("/")
                    if ':' in prefix:
                        af_dict['v6_aggregate_address_ipv6_address'] = prefix
                        af_dict['v6_aggregate_address_as_set'] = True
                        af_dict['v6_aggregate_address_summary_only'] = True
                        continue
                    else:
                        af_dict['aggregate_address_ipv4_address'] = address
                        af_dict['aggregate_address_ipv4_mask'] = mask
                        af_dict['aggregate_address_as_set'] = True
                        af_dict['aggregate_address_summary_only'] = True
                        continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # *>a11.0.0.0/8       0.0.0.0                  100      32768 i
            # *>i33.33.33.33/32   3.3.3.3         0        100          0 ?
            # l34.34.34.0/24      0.0.0.0                  100      32768 i
            # *>i2001::33/128     ::ffff:3.3.3.3  0        100          0 ?
            # *>l[2]:[0]:[0]:[48]:[0000.1986.6d99]:[0]:[0.0.0.0]/216
            # *>i                 21.0.0.2        0        100          0 ?
            # *>l1.1.1.0/24        0.0.0.0                            100      32768 i
            # *>r1.3.1.0/24        0.0.0.0                4444        100      32768 ?
            # *>r1.3.2.0/24        0.0.0.0                4444        100      32768 ?
            # *>i1.6.0.0/16     19.0.101.1                            100          0 10 20 30 40 50 60 70 80 90 i
            # *>i1.1.2.0/24     19.0.102.4                            100          0 {62112 33492 4872 41787 13166 50081 21461 58376 29755 1135} i
            p3_2 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)'
                             '(?P<path_type>(i|e|c|l|a|r|I))'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             ' +(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             ' +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+)'
                             ' +(?P<origin_codes>(i|e|\?|\&|\|))$')
            m = p3_2.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                
                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                # Init dict
                if 'prefixes' not in af_dict:
                    af_dict['prefixes'] = {}
                if prefix not in af_dict['prefixes']:
                    af_dict['prefixes'][prefix] = {}
                if 'index' not in af_dict['prefixes'][prefix]:
                    af_dict['prefixes'][prefix]['index'] = {}
                if index not in af_dict['prefixes'][prefix]['index']:
                    af_dict['prefixes'][prefix]['index'][index] = {}
                if index not in af_dict['prefixes'][prefix]['index']:
                    af_dict['prefixes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['prefixes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['prefixes'][prefix]['index'][index]['path_type'] = path_type
                af_dict['prefixes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['prefixes'][prefix]['index'][index]['origin_codes'] = origin_codes

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['prefixes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['prefixes'][prefix]['index'][index]['localprf'] = int(m1.groupdict()['localprf'])
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['prefixes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                elif m2:
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['prefixes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['prefixes'][prefix]['index'][index]['localprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['prefixes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                elif m3:
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['prefixes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()

                # Check if aggregate_address_ipv4_address
                if 'a' in path_type:
                    address, mask = prefix.split("/")
                    if ':' in prefix:
                        af_dict['v6_aggregate_address_ipv6_address'] = prefix
                        af_dict['v6_aggregate_address_as_set'] = True
                        af_dict['v6_aggregate_address_summary_only'] = True
                        continue
                    else:
                        af_dict['aggregate_address_ipv4_address'] = address
                        af_dict['aggregate_address_ipv4_mask'] = mask
                        af_dict['aggregate_address_as_set'] = True
                        af_dict['aggregate_address_summary_only'] = True
                        continue

            #                     0.0.0.0               100      32768 i
            #                     19.0.101.1            4444       100 0 3 10 20 30 40 50 60 70 80 90 i
            # *>i                 19.0.102.4                        100          0 {62112 33492 4872 41787 13166 50081 21461 58376 29755 1135} i
            p3_3 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)?'
                             '(?P<path_type>(i|e|c|l|a|r|I))?'
                             ' *(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             '(?: +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+))?'
                             ' +(?P<origin_codes>(i|e|\?|\|))$')
            m = p3_3.match(line)
            if m:
                # Get keys
                if m.groupdict()['status_codes']:
                    status_codes = str(m.groupdict()['status_codes'])
                if m.groupdict()['path_type']:
                    path_type = str(m.groupdict()['path_type'])
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                if data_on_nextline:
                    data_on_nextline =  False
                else:
                    index += 1

                # Init dict
                if 'prefixes' not in af_dict:
                    af_dict['prefixes'] = {}
                if prefix not in af_dict['prefixes']:
                    af_dict['prefixes'][prefix] = {}
                if 'index' not in af_dict['prefixes'][prefix]:
                    af_dict['prefixes'][prefix]['index'] = {}
                if index not in af_dict['prefixes'][prefix]['index']:
                    af_dict['prefixes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['prefixes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['prefixes'][prefix]['index'][index]['origin_codes'] = origin_codes

                try:
                    # Set values of status_codes and path_type from prefix line
                    af_dict['prefixes'][prefix]['index'][index]['status_codes'] = status_codes
                    af_dict['prefixes'][prefix]['index'][index]['path_type'] = path_type
                except:
                    pass

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['prefixes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['prefixes'][prefix]['index'][index]['localprf'] = int(m1.groupdict()['localprf'])
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['prefixes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['prefixes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['prefixes'][prefix]['index'][index]['localprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['prefixes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['prefixes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['prefixes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # Route Distinguisher: 100:100     (VRF VRF1)
            # Route Distinguisher: 2:100    (VRF vpn2)
            p4 = re.compile(r'^\s*Route +Distinguisher *:'
                             ' +(?P<route_distinguisher>(\S+))'
                             '(?: +\(VRF +(?P<default_vrf>(\S+))\))?$')
            m = p4.match(line)
            if m:
                route_distinguisher = str(m.groupdict()['route_distinguisher'])
                new_address_family = original_address_family + ' RD ' + route_distinguisher
                
                # Init dict
                if 'address_family' not in parsed_dict['vrf'][vrf]:
                    parsed_dict['vrf'][vrf]['address_family'] = {}
                if new_address_family not in parsed_dict['vrf'][vrf]['address_family']:
                    parsed_dict['vrf'][vrf]['address_family'][new_address_family] = {}
                
                # Set keys
                parsed_dict['vrf'][vrf]['address_family'][new_address_family]['bgp_table_version'] = bgp_table_version
                parsed_dict['vrf'][vrf]['address_family'][new_address_family]['local_router_id'] = local_router_id
                parsed_dict['vrf'][vrf]['address_family'][new_address_family]['route_distinguisher'] = route_distinguisher
                if m.groupdict()['default_vrf']:
                    parsed_dict['vrf'][vrf]['address_family']\
                        [new_address_family]['default_vrf'] = \
                            str(m.groupdict()['default_vrf'])

                # Reset address_family key and af_dict for use in other regex
                address_family = new_address_family
                af_dict = parsed_dict['vrf'][vrf]['address_family'][address_family]
                continue

        # order the af prefixes index
        # return dict when parsed dictionary is empty
        if 'vrf' not in parsed_dict:
            return parsed_dict

        for vrf in parsed_dict['vrf']:
            if 'address_family' not in parsed_dict['vrf'][vrf]:
                continue
            for af in parsed_dict['vrf'][vrf]['address_family']:
                af_dict = parsed_dict['vrf'][vrf]['address_family'][af]
                if 'prefixes' in af_dict:
                    for prefixes in af_dict['prefixes']:
                        if len(af_dict['prefixes'][prefixes]['index'].keys()) > 1:                            
                            ind = 1
                            nexthop_dict = {}
                            for i, j in sorted(af_dict['prefixes'][prefixes]['index'].items(),
                                               key = lambda x:x[1]['next_hop']):
                                nexthop_dict[ind] = af_dict['prefixes'][prefixes]['index'][i]
                                ind += 1
                            del(af_dict['prefixes'][prefixes]['index'])
                            af_dict['prefixes'][prefixes]['index'] = nexthop_dict

        return parsed_dict


# ==============================================
# Schema for 'show bgp vrf <vrf> all neighbors'
# ==============================================
class ShowBgpVrfAllNeighborsSchema(MetaParser):
    """Schema for show bgp vrf <vrf> all neighbors"""

    schema = {
        'neighbor':
            {Any(): 
                {'remote_as': int,
                 Optional('local_as'): str,
                 Optional('link'): str,
                 Optional('peer_index'): int,
                 Optional('description'): str,
                 Optional('bgp_version'): int,
                 Optional('router_id'): str,
                 Optional('session_state'): str,
                 Optional('shutdown'): bool,
                 Optional('up_time'): str,
                 Optional('peer_group'): str,
                 Optional('suppress_four_byte_as_capability'): bool,
                 Optional('retry_time'): str,
                 Optional('update_source'): str,
                 Optional('bfd_live_detection'): bool,
                 Optional('bfd_enabled'): bool,
                 Optional('bfd_state'): str,
                 Optional('nbr_local_as_cmd'): str,
                 Optional('last_read'): str,
                 Optional('holdtime'): int,
                 Optional('keepalive_interval'): int,
                 Optional('bgp_negotiated_keepalive_timers'): 
                    {Optional('last_read'): str,
                     Optional('keepalive_interval'): int,
                     Optional('hold_time'): int,
                     Optional('last_written'): str,
                     Optional('keepalive_timer'): str,
                    },
                 Optional('minimum_advertisement_interval'): int,
                 Optional('disable_connected_check'): bool,
                 Optional('inherit_peer_session'): str,
                 Optional('ebgp_multihop_max_hop'): int,
                 Optional('ebgp_multihop'): bool,
                 Optional('tcp_md5_auth'): str,
                 Optional('tcp_md5_auth_config'): str,
                 Optional('received_messages'): int,
                 Optional('received_notifications'): int,
                 Optional('received_bytes_queue'): int,
                 Optional('sent_messages'): int,
                 Optional('sent_notifications'): int,
                 Optional('sent_bytes_queue'): int,
                 Optional('enabled'): bool,
                 Optional('remove_private_as'): bool,
                 Optional('nbr_ebgp_multihop'): bool,
                 Optional('nbr_ebgp_multihop_max_hop'): int,
                 Optional('route_reflector_cluster_id'): int,
                 Optional('graceful_restart'): bool,
                 Optional('graceful_restart_helper_only'): bool,
                 Optional('graceful_restart_restart_time'): int,
                 Optional('graceful_restart_stalepath_time'): int,
                 Optional('allow_own_as'): int,
                 Optional('send_community'): str,
                 Optional('route_reflector_client'): bool,
                 Optional('bgp_session_transport'):
                    {Optional('connection'): 
                        {Optional('mode'): str,
                         Optional('last_reset'): str,
                         Optional('reset_reason'): str,
                         Optional('reset_by'): str,
                         Optional('attempts'): int,
                         Optional('established'): int,
                         Optional('dropped'): int,
                        },
                     Optional('transport'):
                        {Optional('local_port'): str,
                         Optional('local_host'): str,
                         Optional('foreign_port'): str,
                         Optional('foreign_host'): str,
                         Optional('fd'): str,
                         Optional('passive_mode'): str,
                        },
                    },
                 Optional('bgp_neighbor_counters'):
                    {Optional('messages'):
                        {Optional('sent'): 
                            {Any(): int,
                            },
                         Optional('received'):
                            {Any(): int,
                            },
                        },
                    },
                 Optional('bgp_negotiated_capabilities'): 
                    {Optional('route_refresh'): str,
                     Optional('route_refresh_old'): str,
                     Optional('vpnv4_unicast'): str,
                     Optional('vpnv6_unicast'): str,
                     Optional('graceful_restart'): str,
                     Optional('enhanced_refresh'): str,
                     Optional('multisession'): str,
                     Optional('stateful_switchover'): str,
                     Optional('dynamic_capability'): str,
                     Optional('dynamic_capability_old'): str,
                    },
                 Optional('graceful_restart_paramters'): 
                    {Optional('address_families_advertised_to_peer'): str,
                     Optional('address_families_advertised_from_peer'): str,
                     Optional('restart_time_advertised_to_peer_seconds'): int,
                     Optional('restart_time_advertised_by_peer_seconds'): int,
                     Optional('stale_time_advertised_by_peer_seconds'): int,
                    },
                 Optional('address_family'): 
                    {Any(): 
                        {Optional('bgp_table_version'): int,
                         Optional('neighbor_version'): int,
                         Optional('send_community'): str,
                         Optional('soo'): str,
                         Optional('soft_configuration'): bool,
                         Optional('next_hop_self'): bool,
                         Optional('third_party_nexthop'): bool,
                         Optional('as_override_count'): int,
                         Optional('as_override'): bool,
                         Optional('maximum_prefix_max_prefix_no'): int,
                         Optional('route_map_name_in'): str,
                         Optional('route_map_name_out'): str,
                         Optional('default_originate'): bool,
                         Optional('default_originate_route_map'): str,
                         Optional('route_reflector_client'): bool,
                         Optional('enabled'): bool,
                         Optional('graceful_restart'): bool,
                         Optional('ipv4_unicast_send_default_route'): bool,
                         Optional('ipv6_unicast_send_default_route'): bool,
                         Optional('path'): 
                            {Optional('total_entries'): int,
                             Optional('memory_usage'): int,
                             Optional('accepted_paths'): int,
                            },
                         Optional('inherit_peer_policy'):
                            {Any():
                                {Optional('inherit_peer_seq'): int,
                                },
                            },
                        },
                    },
                },
            },
        }

# ==============================================
# Parser for 'show bgp vrf <vrf> all neighbors'
# ==============================================
class ShowBgpVrfAllNeighbors(ShowBgpVrfAllNeighborsSchema):
    """Parser for:
        show bgp vrf <vrf> all neighbors
        parser class - implements detail parsing mechanisms for cli and yang output.
        """

    def cli(self, vrf):
        cmd  = 'show bgp vrf {vrf} all neighbors'.format(vrf=vrf)
        out = self.device.execute(cmd)
        
        # Init vars
        parsed_dict = {}
        standard_send_community = False

        for line in out.splitlines():
            line = line.rstrip()

            # BGP neighbor is 2.2.2.2,  remote AS 100, ibgp link,  Peer index 1
            # BGP neighbor is 2.2.2.5,  remote AS 200, local AS 333, ebgp link,  Peer index 2
            p1 = re.compile(r'^\s*BGP +neighbor +is +(?P<neighbor_id>[a-zA-Z0-9\.\:]+),'
                             ' +remote +AS +(?P<remote_as>[0-9]+),'
                             '(?: +local +AS +(?P<local_as>[0-9]+),)?'
                             ' +(?P<link>[a-zA-Z]+) +link, +Peer +index'
                             ' +(?P<peer_index>[0-9]+)$')
            m = p1.match(line)
            if m:
                standard_send_community = False
                if 'neighbor' not in parsed_dict:
                    parsed_dict['neighbor'] = {}
                neighbor_id = str(m.groupdict()['neighbor_id'])
                if neighbor_id not in parsed_dict['neighbor']:
                    parsed_dict['neighbor'][neighbor_id] = {}
                    remote_as = m.groupdict()['remote_as']
                    if remote_as != None:
                        parsed_dict['neighbor'][neighbor_id]['remote_as'] = \
                            int(m.groupdict()['remote_as'])
                    parsed_dict['neighbor'][neighbor_id]['local_as'] = \
                        str(m.groupdict()['local_as'])
                    parsed_dict['neighbor'][neighbor_id]['link'] = \
                        str(m.groupdict()['link'])
                    parsed_dict['neighbor'][neighbor_id]['peer_index'] = \
                        int(m.groupdict()['peer_index'])
                    continue

            # Description: nei_desc
            p2 = re.compile(r'^\s*Description *: +(?P<description>(\S+))$')
            m = p2.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['description'] = \
                        str(m.groupdict()['description'])
                continue

            # BGP version 4, remote router ID 2.2.2.2
            p3 = re.compile(r'^\s*BGP +version +(?P<bgp_version>[0-9]+),'
                             ' +remote +router +ID +(?P<router_id>[0-9\.]+)$')
            m = p3.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['bgp_version'] = \
                        int(m.groupdict()['bgp_version'])
                parsed_dict['neighbor'][neighbor_id]['router_id'] = \
                        str(m.groupdict()['router_id'])
                continue

            # BGP state = Established, up for 5w0d
            # BGP state = Idle, down for 4w6d, retry in 0.000000
            # BGP state = Shut (Admin), down for 5w0d
            p4 = re.compile(r'^\s*BGP +state +='
                             ' +(?P<session_state>[a-zA-Z\(\)\s]+), +(up|down)'
                             ' +for +(?P<up_time>[a-zA-Z0-9\:\.]+)'
                             '(?: *, +retry +in +(?P<retry_time>[0-9\.\:]+))?$')
            m = p4.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['session_state'] = \
                        str(m.groupdict()['session_state']).lower()
                parsed_dict['neighbor'][neighbor_id]['up_time'] = \
                        str(m.groupdict()['up_time'])
                parsed_dict['neighbor'][neighbor_id]['retry_time'] = \
                        str(m.groupdict()['retry_time'])
                session_state = str(m.groupdict()['session_state'])
                if 'Shut' in session_state or 'shut' in session_state:
                    parsed_dict['neighbor'][neighbor_id]['shutdown'] = True
                else:
                    parsed_dict['neighbor'][neighbor_id]['shutdown'] = False
                    continue

            # Using loopback0 as update source for this peer
            p5 = re.compile(r'^\s*Using +(?P<update_source>[a-zA-Z0-9]+)'
                             ' +as +update +source +for +this +peer$')
            m = p5.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['update_source'] = \
                        str(m.groupdict()['update_source'])
                continue

            # BFD live-detection is configured
            # BFD live-detection is configured and enabled, state is Up
            p6 = re.compile(r'^\s*BFD live-detection is configured'
                             '( *and (?P<bfd_enabled>\w+), state *is *'
                             '(?P<bfd_state>\w+))?$')
            m = p6.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['bfd_live_detection'] = \
                    True
                if m.groupdict()['bfd_enabled'] and \
                   m.groupdict()['bfd_enabled'].lower() == 'enabled':
                    parsed_dict['neighbor'][neighbor_id]['bfd_enabled'] = True
                if m.groupdict()['bfd_state']:
                    parsed_dict['neighbor'][neighbor_id]['bfd_state'] = \
                        m.groupdict()['bfd_state'].lower()
                continue

            # Neighbor local-as command not active
            p7 = re.compile(r'^\s*Neighbor +local-as +command'
                             ' +(?P<nbr_local_as_cmd>[a-zA-Z\s]+)$')
            m = p7.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['nbr_local_as_cmd'] = \
                        str(m.groupdict()['nbr_local_as_cmd'])
                continue

            # Last read 00:00:24, hold time = 99, keepalive interval is 33 seconds
            # Last read never, hold time = 180, keepalive interval is 60 seconds
            # Last read never, hold time = 45, keepalive interval is 15 seconds
            p8 = re.compile(r'^\s*Last +read +(?P<last_read>[a-zA-Z0-9\:]+),'
                             ' +hold +time += +(?P<holdtime>[0-9]+), +keepalive'
                             ' +interval +is +(?P<keepalive_interval>[0-9]+)'
                             ' +seconds$')
            m = p8.match(line)
            if m:
                if 'bgp_negotiated_keepalive_timers' not in \
                    parsed_dict['neighbor'][neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_negotiated_keepalive_timers'] = {}
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_keepalive_timers']['last_read'] = \
                        str(m.groupdict()['last_read'])
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_keepalive_timers']['keepalive_interval'] = \
                        int(m.groupdict()['keepalive_interval'])
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_keepalive_timers']['hold_time'] = \
                        int(m.groupdict()['holdtime'])
                continue

            # Last written 00:00:02, keepalive timer expiry due 00:00:30
            # Last written never, keepalive timer not running
            p9 = re.compile(r'^\s*Last +written'
                             ' +(?P<last_written>[a-zA-Z0-9\:]+), +keepalive'
                             ' +timer +(?P<keepalive_timer>[a-zA-Z0-9\:\s]+)$')
            m = p9.match(line)
            if m:
                if 'bgp_negotiated_keepalive_timers' not in \
                    parsed_dict['neighbor'][neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_negotiated_keepalive_timers'] = {}
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_keepalive_timers']['last_written'] = \
                        str(m.groupdict()['last_written'])
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_keepalive_timers']['keepalive_timer'] = \
                        str(m.groupdict()['keepalive_timer'])
                continue

            # Inherits session configuration from session-template PEER-SESSION
            p10 = re.compile(r'^\s*Inherits +session +configuration +from'
                            ' +session-template +(?P<template>[a-zA-Z\-\_]+)$')
            m = p10.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['inherit_peer_session'] = \
                    str(m.groupdict()['template'])
                continue

            # Connected check is disabled
            p11 = re.compile(r'^\s*Connected check is disabled$')
            m = p11.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['disable_connected_check'] = True
                continue

            # Private AS numbers removed from updates sent to this neighbor
            p11_2 = re.compile(r'^\s*Private +AS +numbers +removed +from +updates +sent +to +this +neighbor$')
            m = p11_2.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['remove_private_as'] = True
                continue

            # External BGP peer might be upto 255 hops away
            p12_1 = re.compile(r'^\s*External +BGP +peer +might +be +upto'
                             ' +(?P<ebgp_multihop_max_hop>[0-9]+) +hops +away$')
            m = p12_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['ebgp_multihop'] = True
                parsed_dict['neighbor'][neighbor_id]['ebgp_multihop_max_hop'] =\
                    int(m.groupdict()['ebgp_multihop_max_hop'])
                continue

            # External BGP peer might be up to 5 hops away
            p12_2 = re.compile(r'^\s*External +BGP +peer +might +be +up to'
                             ' +(?P<ebgp_multihop_max_hop>[0-9]+) +hops +away$')
            m = p12_2.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['ebgp_multihop'] = True
                parsed_dict['neighbor'][neighbor_id]['ebgp_multihop_max_hop'] =\
                    int(m.groupdict()['ebgp_multihop_max_hop'])
                continue

            # TCP MD5 authentication is enabled
            # TCP MD5 authentication is set (disabled)
            p13 = re.compile(r'^\s*TCP +MD5 +authentication +is'
                              ' +(?P<tcp_md5_auth>[a-zA-Z\(\)\s]+)$')
            m = p13.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['tcp_md5_auth'] = \
                    str(m.groupdict()['tcp_md5_auth'])
                parsed_dict['neighbor'][neighbor_id]['tcp_md5_auth_config'] = \
                    str(line).strip()
                continue
            
            # Only passive connection setup allowed
            p14 = re.compile(r'^\s*Only +passive +connection +setup +allowed$')
            m = p14.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'connection' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['connection'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['mode'] = 'passive'
                continue

            # Received 92717 messages, 3 notifications, 0 bytes in queue
            p15 = re.compile(r'^\s*Received +(?P<received_messages>[0-9]+)'
                              ' +messages, +(?P<received_notifications>[0-9]+)'
                              ' +notifications, +(?P<received_bytes>[0-9]+)'
                              ' +bytes +in +queue$')
            m = p15.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['received_messages'] = \
                    int(m.groupdict()['received_messages'])
                parsed_dict['neighbor'][neighbor_id]['received_notifications'] = \
                    int(m.groupdict()['received_notifications'])
                parsed_dict['neighbor'][neighbor_id]['received_bytes_queue'] = \
                    int(m.groupdict()['received_bytes'])
                continue

            # Sent 92730 messages, 5 notifications, 0 bytes in queue
            p16 = re.compile(r'^\s*Sent +(?P<sent_messages>[0-9]+)'
                              ' +messages, +(?P<sent_notifications>[0-9]+)'
                              ' +notifications, +(?P<sent_bytes_queue>[0-9]+)'
                              ' +bytes +in +queue$')
            m = p16.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['sent_messages'] = \
                    int(m.groupdict()['sent_messages'])
                parsed_dict['neighbor'][neighbor_id]['sent_notifications'] = \
                    int(m.groupdict()['sent_notifications'])
                parsed_dict['neighbor'][neighbor_id]['sent_bytes_queue'] = \
                    int(m.groupdict()['sent_bytes_queue'])
                continue

            # Connections established 9, dropped 8
            p17 = re.compile(r'^\s*Connections +established'
                              ' +(?P<esablished>[0-9]+), +dropped'
                              ' +(?P<dropped>[0-9]+)$')
            m = p17.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'connection' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['connection'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['established'] = \
                        int(m.groupdict()['esablished'])
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['dropped'] = int(m.groupdict()['dropped'])
                continue

            # Connections attempts 0
            p17_1 = re.compile(r'^\s*Connections +attempts'
                                ' +(?P<attemps>[0-9]+)$')
            m = p17.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'connection' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['connection'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['attemps'] = int(m.groupdict()['attemps'])
                continue

            # Last reset by us 5w0d, due to session cleared
            # Last reset by peer 5w0d, due to session cleared
            # Last reset by us never, due to No error
            p18 = re.compile(r'^\s*Last +reset +by (?P<reset_by>[a-zA-Z]+)'
                              ' +(?P<last_reset>[a-zA-Z0-9\:\s]+), +due +to'
                              ' +(?P<reset_reason>[a-zA-Z\-\s]+)$')
            m = p18.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'connection' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['connection'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['last_reset'] = \
                        str(m.groupdict()['last_reset']).lower()
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['reset_reason'] = \
                        str(m.groupdict()['reset_reason']).lower()
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['connection']['reset_by'] = \
                        str(m.groupdict()['reset_by']).lower()
                continue

            # Neighbor capabilities:
            p19 = re.compile(r'^\s*Neighbor +capabilities *:$')
            m = p19.match(line)
            if m:
                if 'bgp_negotiated_capabilities' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_negotiated_capabilities'] = {}
                continue

            # Dynamic capability: advertised (mp, refresh, gr) received (mp, refresh, gr)
            p20_1 = re.compile(r'^\s*Dynamic +capability *:'
                              ' +(?P<dynamic_capability>[a-zA-Z\,\(\)\s]+)$')
            m = p20_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['dynamic_capability'] = \
                        str(m.groupdict()['dynamic_capability'])
                continue

            # Dynamic capability (old): advertised received
            p20_2 = re.compile(r'^\s*Dynamic +capability +\(old\) *:'
                              ' +(?P<dynamic_capability_old>[a-zA-Z\s]+)$')
            m = p20_2.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['dynamic_capability_old'] = \
                        str(m.groupdict()['dynamic_capability_old'])
                continue

            # Route refresh capability (new): advertised received
            p21_1 = re.compile(r'^\s*Route +refresh +capability +\(new\) *:'
                                ' +(?P<route_refresh>[a-zA-Z\s]+)$')
            m = p21_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['route_refresh'] = \
                        str(m.groupdict()['route_refresh'])
                continue

            # Route refresh capability (old): advertised received 
            p21_1 = re.compile(r'^\s*Route +refresh +capability +\(old\) *:'
                                ' +(?P<route_refresh_old>[a-zA-Z\s]+)$')
            m = p21_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['route_refresh_old'] = \
                        str(m.groupdict()['route_refresh_old'])
                continue

            # 4-Byte AS capability: disabled
            # 4-Byte AS capability: disabled received
            p22 = re.compile(r'^\s*4-Byte AS capability: +(?P<capability>[\w\s]+)$')
            m = p22.match(line)
            if m:
                if 'disabled' in m.groupdict()['capability']:
                    parsed_dict['neighbor'][neighbor_id]['suppress_four_byte_as_capability'] = True
                continue

            # Address family VPNv4 Unicast: advertised received
            p23 = re.compile(r'^\s*Address +family +VPNv4 +Unicast *:'
                              ' +(?P<vpnv4_unicast>[a-zA-Z\s]+)$')
            m = p23.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['vpnv4_unicast'] = \
                        str(m.groupdict()['vpnv4_unicast'])
                continue

            # Address family VPNv6 Unicast: advertised received 
            p24 = re.compile(r'^\s*Address +family +VPNv6 +Unicast *:'
                              ' +(?P<vpnv6_unicast>[a-zA-Z\s]+)$')
            m = p24.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['vpnv6_unicast'] = \
                        str(m.groupdict()['vpnv6_unicast'])
                continue


            # Graceful Restart capability: advertised received
            p25 = re.compile(r'^\s*Graceful +Restart +capability *:'
                              ' +(?P<graceful_restart>[a-zA-Z\s]+)$')
            m = p25.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_negotiated_capabilities']['graceful_restart'] = \
                        str(m.groupdict()['graceful_restart'])
                continue

            # Graceful Restart Parameters:
            p26 = re.compile(r'^\s*Graceful +Restart +Parameters *:$')
            m = p26.match(line)
            if m:
                if 'graceful_restart_paramters' not in \
                    parsed_dict['neighbor'][neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['graceful_restart_paramters'] = {}
                    continue

            # Address families advertised to peer:
            # VPNv4 Unicast  VPNv6 Unicast 
            p27_1 = re.compile(r'^\s*$')
            m = p27_1.match(line)
            if m:
                continue

            # Address families received from peer:
            # VPNv4 Unicast  VPNv6 Unicast  
            p27_2 = re.compile(r'^\s*$')
            m = p27_2.match(line)
            if m:
                continue

            # Forwarding state preserved by peer for:
            # Restart time advertised to peer: 240 seconds
            p28_1 = re.compile(r'^\s*Restart +time +advertised +to +peer *:'
                                ' +(?P<time>[0-9]+) +seconds$')
            m = p28_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['graceful_restart_paramters']\
                        ['restart_time_advertised_to_peer_seconds'] = \
                            int(m.groupdict()['time'])
                continue

            # Restart time advertised by peer: 120 seconds
            p28_2 = re.compile(r'^\s*Restart +time +advertised +by +peer *:'
                                ' +(?P<time>[0-9]+) +seconds$')
            m = p28_2.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['graceful_restart_paramters']\
                        ['restart_time_advertised_by_peer_seconds'] = \
                            int(m.groupdict()['time'])
                continue

            # Stale time for routes advertised by peer: 600 seconds
            p28_1 = re.compile(r'^\s*Stale +time +for +routes +advertised +by'
                                ' +peer *: +(?P<time>[0-9]+) +seconds$')
            m = p28_1.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]\
                    ['graceful_restart_paramters']\
                        ['stale_time_advertised_by_peer_seconds'] = \
                            int(m.groupdict()['time'])
                continue

            # Message statistics:
            #                         Sent               Rcvd
            # Opens:                         9                  9  
            # Notifications:                 5                  3  
            # Updates:                      50                 38  
            # Keepalives:                92663              92661  
            # Route Refresh:                 2                  5  
            # Capability:                    1                  1  
            # Total:                     92730              92717  
            # Total bytes:             1763812            1763099  
            # Bytes in queue:                0                  0
            p30 = re.compile(r'^\s*(?P<message_stat>[a-zA-Z\s]+) *:'
                              ' +(?P<sent>[0-9]+) +(?P<received>[0-9]+)$')
            m = p30.match(line)
            if m:
                if 'bgp_neighbor_counters' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters'] = {}
                if 'messages' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_neighbor_counters']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters']['messages'] = {}
                if 'sent' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_neighbor_counters']['messages']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters']['messages']['sent'] = {}
                if 'received' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_neighbor_counters']['messages']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters']['messages']['received'] = {}
                message_stat = str(m.groupdict()['message_stat']).lower()
                message_stat = message_stat.replace(" ", "_")
                sent = int(m.groupdict()['sent'])
                received = int(m.groupdict()['received'])
                if message_stat not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_neighbor_counters']['messages']['sent']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters']['messages']['sent']\
                        [message_stat] = sent
                if message_stat not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_neighbor_counters']['messages']['received']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_neighbor_counters']['messages']['received']\
                        [message_stat] = received
                continue

            # For address family: VPNv4 Unicast
            p31 = re.compile(r'^\s*For +address +family *:'
                              ' +(?P<af>[a-zA-Z0-9\s]+)$')
            m = p31.match(line)
            if m:
                if 'address_family' not in  parsed_dict['neighbor'][neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]['address_family'] = {}
                address_family = str(m.groupdict()['af']).lower()
                
                if address_family not in parsed_dict['neighbor'][neighbor_id]\
                    ['address_family']:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family] = {}
                    continue

            # BGP table version 48, neighbor version 48
            p32 = re.compile(r'^\s*BGP +table +version'
                              ' +(?P<af_bgp_table_version>[0-9]+), +neighbor'
                              ' +version +(?P<nbr_version>[0-9]+)$')
            m = p32.match(line)
            if m:
                standard_send_community = False
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['bgp_table_version'] = \
                        int(m.groupdict()['af_bgp_table_version'])
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['neighbor_version'] = \
                        int(m.groupdict()['nbr_version'])
                continue

            # 1 accepted paths consume 48 bytes of memory
            p33 = re.compile(r'^\s*(?P<accepted_paths>[0-9]+) +accepted'
                              ' +paths +consume +(?P<bytes_consumed>[0-9]+)'
                              ' +bytes +of +memory$')
            m = p33.match(line)
            if m:
                if 'path' not in parsed_dict['neighbor'][neighbor_id]\
                    ['address_family'][address_family]:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['path'] = {}
                accepted_paths = int(m.groupdict()['accepted_paths'])
                memory_usage = int(m.groupdict()['bytes_consumed'])
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['path']['accepted_paths'] = accepted_paths
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['path']['memory_usage'] = memory_usage
                continue

            # 2 sent paths
            p34 = re.compile(r'^\s*(?P<num_sent_paths>[0-9]+) +sent +paths$')
            m = p34.match(line)
            if m:
                if 'path' not in parsed_dict['neighbor'][neighbor_id]\
                    ['address_family'][address_family]:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['path'] = {}
                total_entries = int(m.groupdict()['num_sent_paths'])
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['path']['total_entries'] = total_entries
                continue
            
            # Community attribute sent to this neighbor
            p35 = re.compile(r'^\s*Community +attribute +sent +to +this'
                              ' +neighbor$')
            m = p35.match(line)
            if m:
                standard_send_community = True
                parsed_dict['neighbor'][neighbor_id]['address_family'] \
                    [address_family]['send_community'] = 'standard'
                continue

            # Extended community attribute sent to this neighbor
            p36 = re.compile(r'^\s*Extended +community +attribute +sent +to'
                              ' +this +neighbor$')
            m = p36.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family'] \
                    [address_family]['send_community'] = 'extended'

                if standard_send_community:
                    parsed_dict['neighbor'][neighbor_id]['address_family'] \
                        [address_family]['send_community'] = 'both'
                continue

            # Maximum prefixes allowed 300000
            p37 = re.compile(r'^\s*Maximum +prefixes +allowed +(?P<num>[0-9]+)$')
            m = p37.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['maximum_prefix_max_prefix_no'] = \
                        int(m.groupdict()['num'])
                continue

            # Inbound route-map configured is genie_redistribution, handle obtained
            p38 = re.compile(r'^\s*Inbound +route-map +configured +is'
                              ' +(?P<route_map_name_in>(\S+)), +handle'
                              ' +obtained$')
            m = p38.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['route_map_name_in'] = \
                        str(m.groupdict()['route_map_name_in'])
                continue

            # Outbound route-map configured is genie_redistribution, handle obtained
            p39 = re.compile(r'^\s*Outbound +route-map +configured +is'
                              ' +(?P<route_map_name_out>(\S+)), +handle'
                              ' +obtained$')
            m = p39.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['route_map_name_out'] = \
                        str(m.groupdict()['route_map_name_out'])
                continue

            # Third-party Nexthop will not be computed.
            p40 = re.compile(r'^\s*Third-party +Nexthop +will +not +be'
                              ' +computed.$')
            m = p40.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['third_party_nexthop'] = True
                continue
            
            # SOO Extcommunity: SOO:100:100
            p41 = re.compile(r'^\s*SOO +Extcommunity *:'
                              ' +(?P<soo>[a-zA-Z0-9\:]+)$')
            m = p41.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['soo'] = str(m.groupdict()['soo'])
                continue

            # Inbound soft reconfiguration allowed
            p42 = re.compile(r'^\s*Inbound +soft +reconfiguration +allowed$')
            m = p42.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['soft_configuration'] = True
                continue

            # Nexthop always set to local peering address, 0.0.0.0
            p43 = re.compile(r'^\s*Nexthop +always +set +to +local +peering'
                              ' +address, +(?P<ip>[\w\.\:]+)$')
            m = p43.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['next_hop_self'] = True
                continue

            # Allow my ASN 9 times
            p44 = re.compile(r'^\s*Allow +my +ASN +(?P<num>[0-9]+) +times$')
            m = p44.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['as_override_count'] = \
                        int(m.groupdict()['num'])
                continue

            # ASN override is enabled
            p45 = re.compile(r'^\s*ASN override is enabled$')
            m = p45.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['as_override'] = True
                continue

            # Default information originate, default not sent
            # Default information originate, default sent
            # Default information originate, route-map SOMENAME, default not sent
            p46 = re.compile(r'^\s*Default +information +originate,'
                              '(?: +route-map +(?P<route_map>(\S+)),)?'
                              ' +default(?: +not)? +sent$')
            m = p46.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['default_originate'] = True
                if m.groupdict()['route_map']:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['default_originate_route_map'] = \
                            m.groupdict()['route_map']
                continue

            # Inherited policy-templates:
            # Preference    Name
            #         10    PEER-POLICY                                                 
            #         20    PEER-POLICY2
            p48 = re.compile(r'^\s*(?P<inherit_peer_seq>[0-9]+)'
                              ' +(?P<policy_name>[a-zA-Z0-9\-\_]+)$')
            m = p48.match(line)
            if m:
                policy_name = str(m.groupdict()['policy_name'])
                inherit_peer_seq = int(m.groupdict()['inherit_peer_seq'])
                if 'inherit_peer_policy' not in parsed_dict['neighbor']\
                    [neighbor_id]['address_family'][address_family]:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['inherit_peer_policy'] = {}
                if policy_name not in parsed_dict['neighbor'][neighbor_id]\
                    ['address_family'][address_family]\
                        ['inherit_peer_policy']:
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['inherit_peer_policy']\
                        [policy_name] = {}
                    parsed_dict['neighbor'][neighbor_id]['address_family']\
                        [address_family]['inherit_peer_policy']\
                        [policy_name]['inherit_peer_seq'] = inherit_peer_seq
                    continue

            # Local host: 1.1.1.1, Local port: 179
            p49 = re.compile(r'^\s*Local +host *: +(?P<local_host>[0-9\.\:]+),'
                              ' +Local +port *: +(?P<local_port>[0-9]+)$')
            m = p49.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'transport' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['transport'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['transport']['local_host'] = \
                        str(m.groupdict()['local_host'])
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['transport']['local_port'] = \
                        str(m.groupdict()['local_port'])
                continue

            # Foreign host: 2.2.2.2, Foreign port: 4466
            p50 = re.compile(r'^\s*Foreign +host *:'
                              ' +(?P<foreign_host>[0-9\.\:]+), +Foreign'
                              ' +port *: +(?P<foreign_port>[0-9]+)$')
            m = p50.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'transport' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['transport'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['transport']['foreign_host'] = \
                        str(m.groupdict()['foreign_host'])
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['transport']['foreign_port'] = \
                        str(m.groupdict()['foreign_port'])
                continue
            
            # fd = 44
            p51 = re.compile(r'^\s*fd += +(?P<fd>[0-9]+)$')
            m = p51.match(line)
            if m:
                if 'bgp_session_transport' not in parsed_dict['neighbor']\
                    [neighbor_id]:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport'] = {}
                if 'transport' not in parsed_dict['neighbor'][neighbor_id]\
                    ['bgp_session_transport']:
                    parsed_dict['neighbor'][neighbor_id]\
                        ['bgp_session_transport']['transport'] = {}
                parsed_dict['neighbor'][neighbor_id]['bgp_session_transport']\
                    ['transport']['fd'] = str(m.groupdict()['fd'])
                continue

            # Route reflector client
            p52 = re.compile(r'^\s*Route reflector client$')
            m = p52.match(line)
            if m:
                parsed_dict['neighbor'][neighbor_id]['address_family']\
                    [address_family]['route_reflector_client'] = True
                continue

        return parsed_dict

    def yang(self, vrf):
        # Initialize empty dictionary
        map_dict = {}

        # Execute YANG 'get' operational state RPC and parse the XML
        bgpOC = BgpOpenconfigYang(self.device)
        yang_dict = bgpOC.yang()

        if 'vrf' in yang_dict:
            for vrf_name in yang_dict['vrf']:
                if vrf_name == vrf:
                    if 'neighbor' in yang_dict['vrf'][vrf_name]:
                        for neighbor in yang_dict['vrf'][vrf_name]['neighbor']:
                            if 'neighbor' not in map_dict:
                                map_dict['neighbor'] = {}
                            if neighbor not in map_dict['neighbor']:
                                map_dict['neighbor'][neighbor] = {}
                            for key in yang_dict['vrf'][vrf_name]['neighbor'][neighbor]:
                                if key == 'ebgp_multihop':
                                    map_dict['neighbor'][neighbor]['link'] = 'ebgp'
                                map_dict['neighbor'][neighbor][key] = \
                                    yang_dict['vrf'][vrf_name]['neighbor'][neighbor][key]
                                continue

        # Return to caller
        return map_dict


# ==================================================
# Schema for 'show bgp vrf all all nexthop-database'
# ==================================================
class ShowBgpVrfAllAllNextHopDatabaseSchema(MetaParser):
    """Schema for show bgp vrf all all nexthop-database"""

    schema = {
        'vrf': 
            {Any():
                {'address_family':
                    {Any():
                        {'af_nexthop_trigger_enable': bool,
                         'nexthop_trigger_delay_critical': int,
                         'nexthop_trigger_delay_non_critical': int,
                         Optional('next_hop'): {
                            Any(): {                                
                                 Optional('refcount'): int,
                                 Optional('flags'): str,
                                 Optional('igp_cost'): int,
                                 Optional('igp_route_type'): int,
                                 Optional('igp_preference'): int,
                                 Optional('attached'): bool,
                                 Optional('local'): bool,
                                 Optional('reachable'): bool,
                                 Optional('labeled'): bool,
                                 Optional('filtered'): bool,
                                 Optional('pending_update'): bool,
                                 Optional('resolve_time'): str,
                                 Optional('rib_route'): str,
                                 Optional('metric_next_advertise'): str,
                                 Optional('rnh_epoch'): int,
                                 Optional('attached_nexthop'): {
                                    Any(): {
                                        'attached_nexthop_interface': str,
                                        },
                                    },
                                },
                            }
                         }
                        },
                    },
                },
            }

# ==================================================
# Parser for 'show bgp vrf all all nexthop-database'
# ==================================================
class ShowBgpVrfAllAllNextHopDatabase(ShowBgpVrfAllAllNextHopDatabaseSchema):
    """Parser for show bgp vrf all all nexthop-database"""

    def cli(self, cmd='show bgp vrf all all nexthop-database'):
        out = self.device.execute(cmd)
        
        # Init vars
        nh_dict = {}

        for line in out.splitlines():
            line = line.rstrip()

            # Next Hop table for VRF VRF1, address family IPv4 Unicast:
            p1 = re.compile(r'^\s*Next +Hop +table +for +VRF'
                             ' +(?P<vrf_name>[a-zA-Z0-9]+), +address +family'
                             ' +(?P<af>[a-zA-Z0-9\s\-]+) *:$')
            m = p1.match(line)
            if m:
                if 'vrf' not in nh_dict:
                    nh_dict['vrf'] = {}
                vrf = str(m.groupdict()['vrf_name'])
                if vrf not in nh_dict['vrf']:
                    nh_dict['vrf'][vrf] = {}
                if 'address_family' not in nh_dict['vrf'][vrf]:
                    nh_dict['vrf'][vrf]['address_family'] = {}
                af = str(m.groupdict()['af']).lower()

                if af not in nh_dict['vrf'][vrf]['address_family']:
                    nh_dict['vrf'][vrf]['address_family'][af] = {}
                    af_dict = nh_dict['vrf'][vrf]['address_family'][af]
                    af_dict['af_nexthop_trigger_enable'] = True
                    continue

            # Next-hop trigger-delay(miliseconds)
            # Critical: 2222 Non-critical: 3333
            p2 = re.compile(r'^\s*Critical *:'
                             ' +(?P<nexthop_trigger_delay_critical>[0-9]+)'
                             ' +Non-critical *:'
                             ' +(?P<nexthop_trigger_delay_non_critical>[0-9]+)$')
            m = p2.match(line)
            if m:
                af_dict['nexthop_trigger_delay_critical'] = \
                    int(m.groupdict()['nexthop_trigger_delay_critical'])
                af_dict['nexthop_trigger_delay_non_critical'] = \
                    int(m.groupdict()['nexthop_trigger_delay_non_critical'])
                continue

            # Nexthop: 0.0.0.0, Refcount: 4, IGP cost: 0
            # Nexthop: 200.0.3.1, Flags: 0x41, Refcount: 1, IGP cost: 3
            p3 = re.compile(r'^\s*Nexthop *: +(?P<nh>[a-zA-Z0-9\.\:]+),'
                             '( +Flags *: +(?P<flags>\w+),)?'
                             ' +Refcount *: +(?P<refcount>[0-9]+), +IGP'
                             ' +cost *: +(?P<igp_cost>[0-9\-]+)$')
            m = p3.match(line)
            if m:
                nexthop = m.groupdict()['nh']
                if 'next_hop' not in af_dict:
                    af_dict['next_hop'] = {}
                if nexthop not in af_dict['next_hop']:
                    af_dict['next_hop'][nexthop] = {}

                af_dict['next_hop'][nexthop]['refcount'] = int(m.groupdict()['refcount'])
                af_dict['next_hop'][nexthop]['igp_cost'] = int(m.groupdict()['igp_cost'])
                if m.groupdict()['flags']:
                    af_dict['next_hop'][nexthop]['flags'] = m.groupdict()['flags']
                continue

            # IGP Route type: 0, IGP preference: 0
            p4 = re.compile(r'^\s*IGP +Route +type *:'
                             ' +(?P<igp_route_type>[0-9]+), +IGP +preference *:'
                             ' +(?P<igp_preference>[0-9]+)$')
            m = p4.match(line)
            if m:
                af_dict['next_hop'][nexthop]['igp_route_type'] = int(m.groupdict()['igp_route_type'])
                af_dict['next_hop'][nexthop]['igp_preference'] = int(m.groupdict()['igp_preference'])
                continue

            # Nexthop is not-attached local unreachable not-labeled
            # Nexthop is not-attached not-local reachable labeled
            p5 = re.compile(r'^\s*Nexthop +is +(?P<attached>[\w\-]+) +'
                             '(?P<local>[\w\-]+) +(?P<reachable>[\w\-]+) +'
                             '(?P<labeled>[\w\-]+)$')
            m = p5.match(line)
            if m:
                if m.groupdict()['attached'] == 'not-attached':
                    af_dict['next_hop'][nexthop]['attached'] = False
                else:
                    af_dict['next_hop'][nexthop]['attached'] = True

                if m.groupdict()['local'] == 'not-local':
                    af_dict['next_hop'][nexthop]['local'] = False
                else:
                    af_dict['next_hop'][nexthop]['local'] = True

                if m.groupdict()['reachable'] == 'unreachable':
                    af_dict['next_hop'][nexthop]['reachable'] = False
                else:
                    af_dict['next_hop'][nexthop]['reachable'] = True

                if m.groupdict()['labeled'] == 'not-labeled':
                    af_dict['next_hop'][nexthop]['labeled'] = False
                else:
                    af_dict['next_hop'][nexthop]['labeled'] = True

                af_dict['next_hop'][nexthop]['filtered'] = False
                af_dict['next_hop'][nexthop]['pending_update'] = False

                continue

            # Nexthop last resolved: never, using 0.0.0.0/0
            p6 = re.compile(r'^\s*Nexthop +last +resolved *:'
                             ' +(?P<nexthop_last_resolved>[a-zA-Z0-9\:]+),'
                             ' +using +(?P<nexthop_resolved_using>[\w\:\-\.\/]+)$')
            m = p6.match(line)
            if m:
                af_dict['next_hop'][nexthop]['resolve_time'] = \
                    str(m.groupdict()['nexthop_last_resolved'])
                af_dict['next_hop'][nexthop]['rib_route'] = \
                    str(m.groupdict()['nexthop_resolved_using'])
                continue

            # Metric next advertise: Never
            p7 = re.compile(r'^\s*Metric +next +advertise *:'
                             ' +(?P<metric_next_advertise>[a-zA-Z0-9]+)$')
            m = p7.match(line)
            if m:
                af_dict['next_hop'][nexthop]['metric_next_advertise'] = \
                    str(m.groupdict()['metric_next_advertise']).lower()
                continue

            # RNH epoch: 0
            p8 = re.compile(r'^\s*RNH +epoch *: +(?P<rnh_epoch>[0-9]+)$')
            m = p8.match(line)
            if m:
                af_dict['next_hop'][nexthop]['rnh_epoch'] = int(m.groupdict()['rnh_epoch'])
                continue

            # Attached nexthop: 10.1.3.3, Interface: Ethernet4/2
            p8 = re.compile(r'^\s*Attached +nexthop *:'
                             ' +(?P<attached_nexthop>[\w\.\:]+), +Interface *:'
                             ' +(?P<attached_nexthop_interface>[\w\-\.\/]+)$')
            m = p8.match(line)
            if m:
                if 'attached_nexthop' not in af_dict['next_hop'][nexthop]:
                    af_dict['next_hop'][nexthop]['attached_nexthop'] = {}

                at_nexthop = m.groupdict()['attached_nexthop']

                if at_nexthop not in af_dict['next_hop'][nexthop]['attached_nexthop']:
                    af_dict['next_hop'][nexthop]['attached_nexthop'][at_nexthop] = {}
                af_dict['next_hop'][nexthop]['attached_nexthop'][at_nexthop]\
                    ['attached_nexthop_interface'] = \
                        m.groupdict()['attached_nexthop_interface']
                continue

        return nh_dict


# =========================================
# Schema for 'show bgp vrf <WORD> all summary'
# =========================================
class ShowBgpVrfAllAllSummarySchema(MetaParser):
    """Schema for show bgp vrf <WORD> all summary"""

    schema = {
        'vrf':
            {Any():
                {Optional('neighbor'):
                    {Any():
                        {'address_family':
                            {Any():
                                {'neighbor_table_version': int,
                                'as': int,
                                'msg_rcvd': int,
                                'msg_sent': int,
                                'tbl_ver': int,
                                'inq': int,
                                'outq': int,
                                'up_down': str,
                                'state_pfxrcd': str,
                                'state': str,
                                Optional('prefix_received'): str,
                                Optional('route_identifier'): str,
                                Optional('local_as'): int,
                                Optional('bgp_table_version'): int,
                                Optional('config_peers'): int,
                                Optional('capable_peers'): int,
                                Optional('prefixes'):
                                    {'total_entries': int,
                                    'memory_usage': int,
                                },
                                Optional('path'):
                                    {'total_entries': int,
                                    'memory_usage': int,
                                },
                                Optional('attribute_entries'): str,
                                Optional('as_path_entries'): str,
                                Optional('community_entries'): str,
                                Optional('clusterlist_entries'): str,
                                Optional('dampening'): bool,
                                Optional('history_paths'): int,
                                Optional('dampened_paths'): int,
                                Optional('soft_reconfig_recvd_paths'): int,
                                Optional('soft_reconfig_identical_paths'): int,
                                Optional('soft_reconfig_combo_paths'): int,
                                Optional('soft_reconfig_filtered_recvd'): int,
                                Optional('soft_reconfig_bytes'): int
                                },
                            },
                        },
                    },
                },
            },
        }

# =========================================
# Parser for 'show bgp vrf <WORD> all summary'
# =========================================
class ShowBgpVrfAllAllSummary(ShowBgpVrfAllAllSummarySchema):
    """Parser for show bgp vrf <WORD> all summary"""

    def cli(self, vrf='all'):
        cmd = 'show bgp vrf {} all summary'.format(vrf)
        out = self.device.execute(cmd)
        
        # Init vars
        sum_dict = {}
        data_on_nextline = False

        for line in out.splitlines():
            line = line.rstrip()

            # BGP summary information for VRF VRF1, address family IPv4 Unicast
            p1 = re.compile(r'^\s*BGP +summary +information +for +VRF'
                             ' +(?P<vrf_name>[a-zA-Z0-9]+), +address +family'
                             ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+)$')
            m = p1.match(line)
            if m:
                # Save variables for use later
                address_family = str(m.groupdict()['address_family']).lower()
                vrf = str(m.groupdict()['vrf_name'])
                # Delete variables in preparation for next neighbor
                try:
                    del route_identifier; del local_as; del bgp_table_version;
                    del config_peers; del capable_peers; del attribute_entries;
                    del as_path_entries; del community_entries;
                    del clusterlist_entries; del dampening; del history_paths;
                    del dampened_paths; del soft_reconfig_recvd_paths;
                    del soft_reconfig_identical_paths; del soft_reconfig_combo_paths;
                    del soft_reconfig_filtered_recvd; del soft_reconfig_bytes
                except:
                    pass

                continue

            # BGP router identifier 4.4.4.4, local AS number 100
            p2 = re.compile(r'^\s*BGP +router +identifier'
                             ' +(?P<route_identifier>[0-9\.\:]+), +local +AS'
                             ' +number +(?P<local_as>[0-9]+)$')
            m = p2.match(line)
            if m:
                route_identifier = str(m.groupdict()['route_identifier'])
                local_as = int(m.groupdict()['local_as'])
                if 'vrf' not in sum_dict:
                    sum_dict['vrf'] = {}
                if vrf not in sum_dict['vrf']:
                    sum_dict['vrf'][vrf] = {}
                continue

            # BGP table version is 40, IPv4 Unicast config peers 1, capable peers 0
            p3 = re.compile(r'^\s*BGP +table +version +is'
                             ' +(?P<bgp_table_version>[0-9]+),'
                             ' +(?P<address_family>[a-zA-Z0-9\-\s]+) +config'
                             ' +peers +(?P<config_peers>[0-9]+), +capable'
                             ' +peers +(?P<capable_peers>[0-9]+)$')
            m = p3.match(line)
            if m:
                bgp_table_version = int(m.groupdict()['bgp_table_version'])
                config_peers = int(m.groupdict()['config_peers'])
                capable_peers = int(m.groupdict()['capable_peers'])
                continue

            # 5 network entries and 5 paths using 620 bytes of memory
            p4 = re.compile(r'^\s*(?P<networks>[0-9]+) +network +entries +and'
                             ' +(?P<paths>[0-9]+) +paths +using'
                             ' +(?P<bytes>[0-9]+) +bytes +of +memory$')
            m = p4.match(line)
            if m:
                num_prefix_entries = int(m.groupdict()['networks'])
                memory_usage = int(m.groupdict()['bytes'])
                num_path_entries = int(m.groupdict()['paths'])
                continue

            # BGP attribute entries [3/384], BGP AS path entries [0/0]
            p5 = re.compile(r'^\s*BGP +attribute +entries'
                             ' +(?P<attribute_entries>(\S+)), +BGP +AS +path'
                             ' +entries +(?P<as_path_entries>(\S+))$')
            m = p5.match(line)
            if m:
                attribute_entries = str(m.groupdict()['attribute_entries'])
                as_path_entries = str(m.groupdict()['as_path_entries'])
                continue

            # BGP community entries [0/0], BGP clusterlist entries [1/4]
            p6 = re.compile(r'^\s*BGP +community +entries'
                             ' +(?P<community_entries>(\S+)), +BGP +clusterlist'
                             ' +entries +(?P<clusterlist_entries>(\S+))$')
            m = p6.match(line)
            if m:
                community_entries = str(m.groupdict()['community_entries'])
                clusterlist_entries = str(m.groupdict()['clusterlist_entries'])
                continue

            # Dampening configured, 0 history paths, 0 dampened paths
            p7 = re.compile(r'^\s*Dampening +configured,'
                             ' +(?P<history_paths>[0-9]+) +history +paths,'
                             ' +(?P<dampened_paths>[0-9]+) +dampened +paths$')
            m = p7.match(line)
            if m:
                dampening = True
                history_paths = int(m.groupdict()['history_paths'])
                dampened_paths = int(m.groupdict()['dampened_paths'])
                continue

            # 10 received paths for inbound soft reconfiguration
            p9 = re.compile(r'^\s*(?P<val>[0-9]+) +received +paths +for +inbound +soft +reconfiguration$')
            m = p9.match(line)
            if m:
                soft_reconfig_recvd_paths = int(m.groupdict()['val'])
                continue

            # 10 identical, 0 modified, 0 filtered received paths using 0 bytes
            p10 = re.compile(r'^\s*(?P<val1>[0-9]+) +identical, +'
                              '(?P<val2>[0-9]+) +modified, +'
                              '(?P<val3>[0-9]+) +filtered +received +paths +'
                              'using +(?P<val4>[0-9]+) +bytes$')
            m = p10.match(line)
            if m:
                soft_reconfig_identical_paths = int(m.groupdict()['val1'])
                soft_reconfig_combo_paths = int(m.groupdict()['val2'])
                soft_reconfig_filtered_recvd = int(m.groupdict()['val3'])
                soft_reconfig_bytes = int(m.groupdict()['val4'])
                continue

            # Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
            # 2.2.2.10        4     0       0       0        0    0    0     5w6d Idle 
            p8 = re.compile(r'^\s*(?P<neighbor>[a-zA-Z0-9\.\:]+) +(?P<v>[0-9]+)'
                             ' +(?P<as>[0-9]+) +(?P<msg_rcvd>[0-9]+)'
                             ' +(?P<msg_sent>[0-9]+) +(?P<tbl_ver>[0-9]+)'
                             ' +(?P<inq>[0-9]+) +(?P<outq>[0-9]+)'
                             ' +(?P<up_down>[a-zA-Z0-9\:]+)'
                             ' +(?P<state_pfxrcd>(?P<state>[a-zA-Z\s\(\)]+)?'
                             '(?P<prx_rcd>\d+)?([\w\(\)\s]+)?)$')
            m = p8.match(line)
            if m:
                # Add neighbor to dictionary
                neighbor = str(m.groupdict()['neighbor'])
                if 'neighbor' not in sum_dict['vrf'][vrf]:
                    sum_dict['vrf'][vrf]['neighbor'] = {}
                if neighbor not in sum_dict['vrf'][vrf]['neighbor']:
                    sum_dict['vrf'][vrf]['neighbor'][neighbor] = {}
                nbr_dict = sum_dict['vrf'][vrf]['neighbor'][neighbor]

                # Add address family to this neighbor
                if 'address_family' not in nbr_dict:
                    nbr_dict['address_family'] = {}
                if address_family not in nbr_dict['address_family']:
                    nbr_dict['address_family'][address_family] = {}
                nbr_af_dict = nbr_dict['address_family'][address_family]

                # Add keys for this address_family
                nbr_af_dict['neighbor_table_version'] = int(m.groupdict()['v'])
                nbr_af_dict['as'] = int(m.groupdict()['as'])
                nbr_af_dict['msg_rcvd'] = int(m.groupdict()['msg_rcvd'])
                nbr_af_dict['msg_sent'] = int(m.groupdict()['msg_sent'])
                nbr_af_dict['tbl_ver'] = int(m.groupdict()['tbl_ver'])
                nbr_af_dict['inq'] = int(m.groupdict()['inq'])
                nbr_af_dict['outq'] = int(m.groupdict()['outq'])
                nbr_af_dict['up_down'] = str(m.groupdict()['up_down'])
                nbr_af_dict['state_pfxrcd'] = str(m.groupdict()['state_pfxrcd']).lower().strip()
                if m.groupdict()['state']:
                    nbr_af_dict['state'] = m.groupdict()['state_pfxrcd'].lower()
                if m.groupdict()['prx_rcd']:
                    nbr_af_dict['prefix_received'] = m.groupdict()['prx_rcd']
                    nbr_af_dict['state'] = 'established'
                try:
                    # Assign variables
                    nbr_af_dict['route_identifier'] = route_identifier
                    nbr_af_dict['local_as'] = local_as
                    nbr_af_dict['bgp_table_version'] = bgp_table_version
                    nbr_af_dict['config_peers'] = config_peers
                    nbr_af_dict['capable_peers'] = capable_peers
                    nbr_af_dict['attribute_entries'] = attribute_entries
                    nbr_af_dict['as_path_entries'] = as_path_entries
                    nbr_af_dict['community_entries'] = community_entries
                    nbr_af_dict['clusterlist_entries'] = clusterlist_entries
                    nbr_af_dict['dampening'] = dampening
                    nbr_af_dict['history_paths'] = history_paths
                    nbr_af_dict['dampened_paths'] = dampened_paths
                except:
                    pass
                try:
                    nbr_af_dict['soft_reconfig_recvd_paths'] = soft_reconfig_recvd_paths
                    nbr_af_dict['soft_reconfig_identical_paths'] = soft_reconfig_identical_paths
                    nbr_af_dict['soft_reconfig_combo_paths'] = soft_reconfig_combo_paths
                    nbr_af_dict['soft_reconfig_filtered_recvd'] = soft_reconfig_filtered_recvd
                    nbr_af_dict['soft_reconfig_bytes'] = soft_reconfig_bytes
                except:
                    pass

                if num_prefix_entries or num_prefix_entries == 0:
                    nbr_af_dict['prefixes'] = {}
                    nbr_af_dict['prefixes']['total_entries'] = num_prefix_entries
                    nbr_af_dict['prefixes']['memory_usage'] = memory_usage
                if num_path_entries or num_path_entries == 0:
                    nbr_af_dict['path'] = {}
                    nbr_af_dict['path']['total_entries'] = num_path_entries
                    nbr_af_dict['path']['memory_usage'] = memory_usage
                    continue

            # Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
            # 2.2.2.10
            p8_1 = re.compile(r'^\s*(?P<neighbor>[a-zA-Z0-9\.\:]+)$')
            m = p8_1.match(line)
            if m:
                data_on_nextline = True
                # Add neighbor to dictionary
                neighbor = str(m.groupdict()['neighbor'])
                if 'neighbor' not in sum_dict['vrf'][vrf]:
                    sum_dict['vrf'][vrf]['neighbor'] = {}
                if neighbor not in sum_dict['vrf'][vrf]['neighbor']:
                    sum_dict['vrf'][vrf]['neighbor'][neighbor] = {}
                nbr_dict = sum_dict['vrf'][vrf]['neighbor'][neighbor]
                continue

            # Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
            #                 4     0       0       0        0    0    0     5w6d Idle 
            p8_2 = re.compile(r'^\s*(?P<v>[0-9]+) +(?P<as>[0-9]+)'
                             ' +(?P<msg_rcvd>[0-9]+) +(?P<msg_sent>[0-9]+)'
                             ' +(?P<tbl_ver>[0-9]+) +(?P<inq>[0-9]+)'
                             ' +(?P<outq>[0-9]+) +(?P<up_down>[a-zA-Z0-9\:]+)'
                             ' +(?P<state_pfxrcd>(?P<state>[a-zA-Z\s\(\)]+)?(?P<prx_rcd>\d+)?([\w\(\)\s]+)?)$')
            m = p8_2.match(line)
            if m and data_on_nextline:
                data_on_nextline = False
                # Add address family to this neighbor
                if 'address_family' not in nbr_dict:
                    nbr_dict['address_family'] = {}
                if address_family not in nbr_dict['address_family']:
                    nbr_dict['address_family'][address_family] = {}
                nbr_af_dict = nbr_dict['address_family'][address_family]

                # Add keys for this address_family
                nbr_af_dict['neighbor_table_version'] = int(m.groupdict()['v'])
                nbr_af_dict['as'] = int(m.groupdict()['as'])
                nbr_af_dict['msg_rcvd'] = int(m.groupdict()['msg_rcvd'])
                nbr_af_dict['msg_sent'] = int(m.groupdict()['msg_sent'])
                nbr_af_dict['tbl_ver'] = int(m.groupdict()['tbl_ver'])
                nbr_af_dict['inq'] = int(m.groupdict()['inq'])
                nbr_af_dict['outq'] = int(m.groupdict()['outq'])
                nbr_af_dict['up_down'] = str(m.groupdict()['up_down'])
                nbr_af_dict['state_pfxrcd'] = str(m.groupdict()['state_pfxrcd']).lower().strip()
                if m.groupdict()['state']:
                    nbr_af_dict['state'] = m.groupdict()['state_pfxrcd'].lower()
                if m.groupdict()['prx_rcd']:
                    nbr_af_dict['prefix_received'] = m.groupdict()['prx_rcd']
                    nbr_af_dict['state'] = 'established'

                try:
                    # Assign variables
                    nbr_af_dict['route_identifier'] = route_identifier
                    nbr_af_dict['local_as'] = local_as
                    nbr_af_dict['bgp_table_version'] = bgp_table_version
                    nbr_af_dict['config_peers'] = config_peers
                    nbr_af_dict['capable_peers'] = capable_peers
                    nbr_af_dict['attribute_entries'] = attribute_entries
                    nbr_af_dict['as_path_entries'] = as_path_entries
                    nbr_af_dict['community_entries'] = community_entries
                    nbr_af_dict['clusterlist_entries'] = clusterlist_entries
                    nbr_af_dict['dampening'] = dampening
                    nbr_af_dict['history_paths'] = history_paths
                    nbr_af_dict['dampened_paths'] = dampened_paths
                except:
                    pass
                try:
                    nbr_af_dict['soft_reconfig_recvd_paths'] = soft_reconfig_recvd_paths
                    nbr_af_dict['soft_reconfig_identical_paths'] = soft_reconfig_identical_paths
                    nbr_af_dict['soft_reconfig_combo_paths'] = soft_reconfig_combo_paths
                    nbr_af_dict['soft_reconfig_filtered_recvd'] = soft_reconfig_filtered_recvd
                    nbr_af_dict['soft_reconfig_bytes'] = soft_reconfig_bytes
                except:
                    pass

                if num_prefix_entries or num_prefix_entries == 0:
                    nbr_af_dict['prefixes'] = {}
                    nbr_af_dict['prefixes']['total_entries'] = num_prefix_entries
                    nbr_af_dict['prefixes']['memory_usage'] = memory_usage
                if num_path_entries or num_path_entries == 0:
                    nbr_af_dict['path'] = {}
                    nbr_af_dict['path']['total_entries'] = num_path_entries
                    nbr_af_dict['path']['memory_usage'] = memory_usage
                    continue

        return sum_dict

    def xml(self, vrf='all'):

        cmd = 'show bgp vrf {} all summary'.format(vrf)

        out = self.device.execute(cmd + ' | xml')

        etree_dict = {}

        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                       expect_command=cmd)

        # find Vrf root
        root = Common.retrieve_xml_child(root=root, key='TABLE_vrf')

        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-out'.format(namespace)).text
            except:
                break

            # <vrf-router-id>19.0.0.6</vrf-router-id>
            try:
                route_identifier = vrf_tree.find('{}vrf-router-id'.format(namespace)).text
            except:
                route_identifier = None

            # <vrf-local-as>333</vrf-local-as>
            try:
                local_as = vrf_tree.find('{}vrf-local-as'.format(namespace)).text
            except:
                local_as = None

            # Address family table
            af_tree = vrf_tree.find('{}TABLE_af'.format(namespace))
            if not af_tree:
                continue
            for af_root in af_tree.findall('{}ROW_af'.format(namespace)):
                # Address family table
                saf_tree = af_root.find('{}TABLE_saf'.format(namespace))
                if not saf_tree:
                    continue
                # -----   loop address_family  -----
                for saf_root in saf_tree.findall('{}ROW_saf'.format(namespace)):
                    # neighbor
                    try:
                        af = saf_root.find('{}af-name'.format(namespace)).text
                        af = af.lower()
                        # initial af dictionary
                        af_dict = {}
                        if route_identifier:
                            af_dict['route_identifier'] = route_identifier
                        if local_as:
                            af_dict['local_as'] = int(local_as)
                    except:
                        continue

                    # <tableversion>7</tableversion>
                    try:
                        af_dict['bgp_table_version'] = int(
                            saf_root.find('{}tableversion'.format(namespace)).text)
                    except:
                        # for valide entry, table version should be there
                        continue

                    # <configuredpeers>3</configuredpeers>
                    af_dict['config_peers'] = \
                        int(saf_root.find('{}configuredpeers'.format(namespace)).text)
                        
                    # <capablepeers>2</capablepeers>
                    af_dict['capable_peers'] = \
                        int(saf_root.find('{}capablepeers'.format(namespace)).text)

                    # <totalnetworks>5</totalnetworks>
                    try:
                        total_prefix_entries = \
                            int(saf_root.find('{}totalnetworks'.format(namespace)).text)
                        if 'prefixes' not in af_dict:
                            af_dict['prefixes'] = {}
                        af_dict['prefixes']['total_entries'] = total_prefix_entries
                    except:
                        pass
                        
                    # <totalpaths>10</totalpaths>
                    try:
                        total_path_entries = \
                            int(saf_root.find('{}totalpaths'.format(namespace)).text)
                        if 'path' not in af_dict:
                            af_dict['path'] = {}
                        af_dict['path']['total_entries'] = total_path_entries
                    except:
                        pass
                        
                    # <memoryused>1820</memoryused>
                    try:
                        memory_usage = \
                            int(saf_root.find('{}memoryused'.format(namespace)).text)
                        af_dict['path']['memory_usage'] = memory_usage
                        af_dict['prefixes']['memory_usage'] = memory_usage
                    except:
                        pass

                    try:
                        # <numberattrs>1</numberattrs>
                        entries_1 = \
                            saf_root.find('{}numberattrs'.format(namespace)).text
                            
                        # <bytesattrs>160</bytesattrs>
                        entries_2 = \
                            saf_root.find('{}bytesattrs'.format(namespace)).text

                        af_dict['attribute_entries'] = '[{0}/{1}]'.format(entries_1, entries_2)
                    except:
                        pass
                        
                    try:
                        # <numberpaths>1</numberpaths>
                        entries_1 = \
                            saf_root.find('{}numberpaths'.format(namespace)).text

                        # <bytespaths>34</bytespaths>
                        entries_2 = \
                            saf_root.find('{}bytespaths'.format(namespace)).text

                        af_dict['as_path_entries'] = '[{0}/{1}]'.format(entries_1, entries_2)
                    except:
                        pass
                        
                    try:
                        # <numbercommunities>0</numbercommunities>
                        entries_1 = \
                            saf_root.find('{}numbercommunities'.format(namespace)).text

                        # <bytescommunities>0</bytescommunities>
                        entries_2 = \
                            saf_root.find('{}bytescommunities'.format(namespace)).text

                        af_dict['community_entries'] = '[{0}/{1}]'.format(entries_1, entries_2)
                    except:
                        pass
                        
                    try:
                        # <numberclusterlist>0</numberclusterlist>
                        entries_1 = \
                            saf_root.find('{}numberclusterlist'.format(namespace)).text

                        # <bytesclusterlist>0</bytesclusterlist>
                        entries_2 = \
                            saf_root.find('{}bytesclusterlist'.format(namespace)).text

                        af_dict['clusterlist_entries'] = '[{0}/{1}]'.format(entries_1, entries_2)
                    except:
                        pass

                    # <dampening>Enabled</dampening>
                    dampening = saf_root.find('{}dampening'.format(namespace)).text.lower()
                    if 'enabled' in dampening or 'true' in dampening:
                        af_dict['dampening'] = True

                    # <historypaths>0</historypaths>
                    try:
                        af_dict['history_paths'] = int(saf_root.find('{}historypaths'.format(namespace)).text)
                    except:
                        pass

                    # <dampenedpaths>0</dampenedpaths>
                    try:
                        af_dict['dampened_paths'] = int(saf_root.find('{}dampenedpaths'.format(namespace)).text)
                    except:
                        pass

                    # <softreconfigrecvdpaths>10</softreconfigrecvdpaths>
                    try:
                        af_dict['soft_reconfig_recvd_paths'] = int(
                                saf_root.find('{}softreconfigrecvdpaths'.format(namespace)).text)
                    except:
                        pass
                        
                    # <softreconfigidenticalpaths>10</softreconfigidenticalpaths>
                    try:
                        af_dict['soft_reconfig_identical_paths'] = int(
                                saf_root.find('{}softreconfigidenticalpaths'.format(namespace)).text)
                    except:
                        pass

                    # <softreconfigcombopaths>0</softreconfigcombopaths>
                    try:
                        af_dict['soft_reconfig_combo_paths'] = int(
                                saf_root.find('{}softreconfigcombopaths'.format(namespace)).text)
                    except:
                        pass

                    # <softreconfigfilteredrecvd>0</softreconfigfilteredrecvd>
                    try:
                        af_dict['soft_reconfig_filtered_recvd'] = int(
                                saf_root.find('{}softreconfigfilteredrecvd'.format(namespace)).text)
                    except:
                        pass
                        
                    # <softreconfigbytes>0</softreconfigbytes>
                    try:
                        af_dict['soft_reconfig_bytes'] = int(
                                saf_root.find('{}softreconfigbytes'.format(namespace)).text)
                    except:
                        pass
                        
                     # Neighbor table
                    nei_tree = saf_root.find('{}TABLE_neighbor'.format(namespace))
                    if not nei_tree:
                        continue

                    # -----   loop neighbors  -----
                    for nei_root in nei_tree.findall('{}ROW_neighbor'.format(namespace)):
                        # neighbor
                        try:
                            nei = nei_root.find('{}neighborid'.format(namespace)).text
                        except:
                            continue

                        if 'vrf' not in etree_dict:
                            etree_dict['vrf'] = {}
                        if vrf not in etree_dict['vrf']:
                            etree_dict['vrf'][vrf] = {}

                        if 'neighbor' not in etree_dict['vrf'][vrf]:
                            etree_dict['vrf'][vrf]['neighbor'] = {}
                        if nei not in etree_dict['vrf'][vrf]['neighbor']:
                            etree_dict['vrf'][vrf]['neighbor'][nei] = {}

                        if 'address_family' not in etree_dict['vrf'][vrf]['neighbor'][nei]:
                            etree_dict['vrf'][vrf]['neighbor'][nei]['address_family'] = {}

                        if af not in etree_dict['vrf'][vrf]['neighbor'][nei]['address_family']:
                            etree_dict['vrf'][vrf]['neighbor'][nei]['address_family'][af] = {}
                    
                        sub_dict = etree_dict['vrf'][vrf]['neighbor'][nei]['address_family'][af]

                        #  ---   AF attributes -------
                        update_dict = deepcopy(af_dict)
                        sub_dict.update(update_dict)

                        #  ---   Neighbors attributes -------
                        # <neighborversion>4</neighborversion>
                        sub_dict['neighbor_table_version'] = int(
                            nei_root.find('{}neighborversion'.format(namespace)).text)

                        # <msgrecvd>5471</msgrecvd>
                        sub_dict['msg_rcvd'] = int(
                            nei_root.find('{}msgrecvd'.format(namespace)).text)
                        
                        # <msgsent>5459</msgsent>
                        sub_dict['msg_sent'] = int(
                            nei_root.find('{}msgsent'.format(namespace)).text)
                        
                        # <neighbortableversion>7</neighbortableversion>
                        sub_dict['tbl_ver'] = int(
                            nei_root.find('{}neighbortableversion'.format(namespace)).text)
                        
                        # <inq>0</inq>
                        sub_dict['inq'] = int(
                            nei_root.find('{}inq'.format(namespace)).text)
                        
                        # <outq>0</outq>
                        sub_dict['outq'] = int(
                            nei_root.find('{}outq'.format(namespace)).text)
                        
                        # <neighboras>333</neighboras>
                        sub_dict['as'] = int(
                            nei_root.find('{}neighboras'.format(namespace)).text)
                        
                        # <time>3d18h</time>
                        sub_dict['up_down'] = \
                            nei_root.find('{}time'.format(namespace)).text
                        
                        # <state>Established</state>
                        state = nei_root.find('{}state'.format(namespace)).text.lower()

                        # <prefixreceived>5</prefixreceived>
                        prefix_received = \
                            nei_root.find('{}prefixreceived'.format(namespace)).text

                        if 'established' in state:
                            sub_dict['state'] = state
                            sub_dict['prefix_received'] = prefix_received
                            sub_dict['state_pfxrcd'] = prefix_received
                        else:
                            sub_dict['state'] = state
                            sub_dict['state_pfxrcd'] = state
                
        return etree_dict

# ==================================================
# Schema for 'show bgp vrf <WROD> all dampening parameters'
# ==================================================
class ShowBgpVrfAllAllDampeningParametersSchema(MetaParser):
    """Schema for 'show bgp vrf <WROD> all dampening parameters"""
    
    schema = {
        'vrf':
            {Any():
                {'address_family':
                    {Any():
                        {Optional('dampening'): str,
                        Optional('dampening_route_map'): str,
                        Optional('dampening_half_life_time'): str,
                        Optional('dampening_reuse_time'): str,
                        Optional('dampening_suppress_time'): str,
                        Optional('dampening_max_suppress_time'): str,
                        Optional('dampening_max_suppress_penalty'): str,
                        Optional('route_distinguisher'):
                            {Optional(Any()): {
                                Optional('rd_vrf'): str,
                                Optional('rd_vni_id'): str,
                                Optional('dampening_route_map'): str,
                                Optional('dampening_half_life_time'): str,
                                Optional('dampening_reuse_time'): str,
                                Optional('dampening_suppress_time'): str,
                                Optional('dampening_max_suppress_time'): str,
                                Optional('dampening_max_suppress_penalty'): str,
                                },
                            },
                        },
                    },
                },
            },
        }

# ==================================================
# Parser for 'show bgp vrf <WROD> all dampening parameters'
# ==================================================
class ShowBgpVrfAllAllDampeningParameters(ShowBgpVrfAllAllDampeningParametersSchema):
    """Parser for 'show bgp vrf <WROD> all dampening parameters"""
    
    def cli(self, vrf ='all'):
        cmd = 'show bgp vrf {} all dampening parameters'.format(vrf)
        out = self.device.execute(cmd)
        bgp_dict = {}
        sub_dict = {}

        for line in out.splitlines():
            line = line.strip()
            p1 = re.compile(r'^Route +(?P<route>\w+) +Dampening +Parameters '
                             '+for +VRF +(?P<vrf>\w+) +Address +family '
                             '+(?P<af_name>[a-zA-Z0-9 ]+):$')
            m = p1.match(line)
            if m:
                if 'vrf' not in bgp_dict:
                    bgp_dict['vrf'] = {}

                vrf = m.groupdict()['vrf']
                if vrf not in bgp_dict['vrf']:
                    bgp_dict['vrf'][vrf] = {}
                    bgp_dict['vrf'][vrf]['address_family'] = {}

                af_name = m.groupdict()['af_name'].lower()
                if af_name not in bgp_dict['vrf'][vrf]['address_family']:
                    bgp_dict['vrf'][vrf]['address_family'][af_name] = {}
                    # trim the coding lines for adopting pep8
                    sub_dict = bgp_dict['vrf'][vrf]['address_family'][af_name]
                    sub_dict['dampening'] = 'True'
                continue

            p9 = re.compile(r'^Route +Distinguisher: +(?P<rd>[0-9\.:]+) +'
                             '\(VRF +(?P<rd_vrf>\w+)\)$')
            m = p9.match(line)
            if m:
                if 'route_distinguisher' not in \
                  bgp_dict['vrf'][vrf]['address_family'][af_name]:
                   bgp_dict['vrf'][vrf]['address_family']\
                     [af_name]['route_distinguisher'] = {}
                rd = m.groupdict()['rd']
                if rd and rd not in bgp_dict['vrf'][vrf]['address_family']\
                  [af_name]['route_distinguisher']:
                    sub_dict = bgp_dict['vrf'][vrf]['address_family']\
                      [af_name]['route_distinguisher'][rd] = {}

                rd_vrf = m.groupdict()['rd_vrf']
                if rd_vrf:
                    sub_dict['rd_vrf'] = rd_vrf
                continue

            # Route Distinguisher: 500:1    (L3VNI 2)
            # rd_vrf = L3, vni = 2
            p10 = re.compile(r'^Route +Distinguisher: +(?P<rd>[0-9\.:]+) +'
                             '\((?P<rd_vrf>\w+)( *VNI +(?P<vni>\w+))\)')
            m = p10.match(line)
            if m:
                if 'route_distinguisher' not in \
                  bgp_dict['vrf'][vrf]['address_family'][af_name]:
                   bgp_dict['vrf'][vrf]['address_family']\
                     [af_name]['route_distinguisher'] = {}
                rd = m.groupdict()['rd']
                vni = m.groupdict()['vni']
                if rd and rd not in bgp_dict['vrf'][vrf]['address_family']\
                  [af_name]['route_distinguisher']:
                    sub_dict = bgp_dict['vrf'][vrf]['address_family']\
                      [af_name]['route_distinguisher'][rd] = {}

                rd_vrf = m.groupdict()['rd_vrf']
                if rd_vrf:
                    sub_dict['rd_vrf'] = rd_vrf
                if vni:
                    sub_dict['rd_vni_id'] = vni
                continue


            p2 = re.compile(r'^Dampening +policy +configured: '
                             '+(?P<route_map>\w+)$')
            m = p2.match(line)
            if m:
                sub_dict['dampening_route_map'] = m.groupdict()['route_map']
                continue

            p3 = re.compile(r'^Half-life +time +: +'
                             '(?P<half_time>\d+)( *(?P<unit>\w+))?$')
            m = p3.match(line)
            if m:
                sub_dict['dampening_half_life_time'] =\
                   m.groupdict()['half_time']
                continue

            p4 = re.compile(r'^Suppress +penalty +: +'
                             '(?P<suppress_pen>\d+)( *(?P<unit>\w+))?$')
            m = p4.match(line)
            if m:
                sub_dict['dampening_suppress_time'] =\
                  m.groupdict()['suppress_pen']
                continue

            p5 = re.compile(r'^Reuse +penalty +: +'
                             '(?P<reuse_pen>\d+)( *(?P<unit>\w+))?$')
            m = p5.match(line)
            if m:
                sub_dict['dampening_reuse_time'] =\
                  m.groupdict()['reuse_pen']
                continue

            p6 = re.compile(r'^Max +suppress +time +: +'
                             '(?P<max_sup_time>\d+)( *(?P<unit>\w+))?$')
            m = p6.match(line)
            if m:
                sub_dict['dampening_max_suppress_time'] =\
                  m.groupdict()['max_sup_time']
                continue

            p7 = re.compile(r'^Max +suppress +penalty +: '
                             '+(?P<max_sup_pen>\d+)( *(?P<unit>\w+))?$')
            m = p7.match(line)
            if m:
                sub_dict['dampening_max_suppress_penalty'] =\
                  m.groupdict()['max_sup_pen']
                continue
        return bgp_dict

    def xml(self, vrf='all'):
        cmd = 'show bgp vrf {} all dampening parameters'.format(vrf)

        out = self.device.execute(cmd + ' | xml')

        etree_dict = {}

        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                       expect_command=cmd)

        root = Common.retrieve_xml_child(
                root=root,
                key='TABLE_vrf')

        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-out'.format(namespace)).text
            except:
                break

            # Address family table
            af_tree = vrf_tree.find('{}TABLE_afi'.format(namespace))
            if not af_tree:
                continue
            for af_root in af_tree.findall('{}ROW_afi'.format(namespace)):
                # Address family table
                saf_tree = af_root.find('{}TABLE_safi'.format(namespace))
                if not saf_tree:
                    continue
                # -----   loop address_family  -----
                for saf_root in saf_tree.findall('{}ROW_safi'.format(namespace)):
                    # neighbor
                    try:
                        af = saf_root.find('{}af-name'.format(namespace)).text
                        af = af.lower()
                    except:
                        continue

                     # RD table
                    rd_tree = saf_root.find('{}TABLE_rd'.format(namespace))
                    if not rd_tree:
                        continue

                    # -----   loop rd  -----
                    for rd_root in rd_tree.findall('{}ROW_rd'.format(namespace)):
                        # neighbor
                        try:
                            rd = rd_root.find('{}rd_val'.format(namespace)).text
                        except:
                            rd = None

                        if 'vrf' not in etree_dict:
                            etree_dict['vrf'] = {}
                        if vrf not in etree_dict['vrf']:
                            etree_dict['vrf'][vrf] = {}

                        if 'address_family' not in etree_dict['vrf'][vrf]:
                            etree_dict['vrf'][vrf]['address_family'] = {}

                        if af not in etree_dict['vrf'][vrf]['address_family']:
                            etree_dict['vrf'][vrf]['address_family'][af] = {}

                        # dampening
                        etree_dict['vrf'][vrf]['address_family'][af]['dampening'] = 'True'

                        if rd:
                            if 'route_distinguisher' not in etree_dict['vrf'][vrf]:
                                etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'] = {}

                            if rd not in etree_dict['vrf'][vrf]['address_family']:
                                etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'][rd] = {}
                            sub_dict = etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'][rd]
                        else:
                            sub_dict = etree_dict['vrf'][vrf]['address_family'][af]
                                    

                        # <dampconfigured>Configured</dampconfigured>
                        # cli does not have this key

                        # <rpmname>test</rpmname>
                        try:
                            sub_dict['dampening_route_map'] = \
                                rd_root.find('{}rpmname'.format(namespace)).text
                        except:
                            pass

                        # <rd_vrf>vpn2</rd_vrf>
                        try:
                            sub_dict['rd_vrf'] = \
                                rd_root.find('{}rd_vrf'.format(namespace)).text
                        except:
                            pass

                        # <rd_vniid>2</rd_vniid>
                        try:
                            sub_dict['rd_vni_id'] = \
                                rd_root.find('{}rd_vniid'.format(namespace)).text
                        except:
                            pass

                        # <damphalflife>1</damphalflife>
                        try:
                            sub_dict['dampening_half_life_time'] = \
                                rd_root.find('{}damphalflife'.format(namespace)).text
                        except:
                            pass

                        # <dampsuppress>30</dampsuppress>
                        try:
                            sub_dict['dampening_suppress_time'] = \
                                rd_root.find('{}dampsuppress'.format(namespace)).text
                        except:
                            pass

                        # <dampreuse>10</dampreuse>
                        try:
                            sub_dict['dampening_reuse_time'] = \
                                rd_root.find('{}dampreuse'.format(namespace)).text
                        except:
                            pass

                        # <dampsuppresstime>2</dampsuppresstime>
                        try:
                            sub_dict['dampening_max_suppress_time'] = \
                                rd_root.find('{}dampsuppresstime'.format(namespace)).text
                        except:
                            pass

                        # <dampmaxpenalty>40</dampmaxpenalty>
                        try:
                            sub_dict['dampening_max_suppress_penalty'] = \
                                rd_root.find('{}dampmaxpenalty'.format(namespace)).text
                        except:
                            pass

        return etree_dict

# ==========================================================================
# Schema for 'show bgp vrf <vrf> all neighbors <neighbor> advertised-routes'
# ==========================================================================
class ShowBgpVrfAllNeighborsAdvertisedRoutesSchema(MetaParser):
    """Schema for show bgp vrf <vrf> all neighbors <neighbor> advertised-routes"""

    schema = {
        'vrf':
            {Any():
                {'neighbor':
                    {Any():
                        {'address_family':
                            {Any():
                                {Optional('bgp_table_version'): int,
                                 Optional('local_router_id'): str,
                                 Optional('route_distinguisher'): str,
                                 Optional('default_vrf'): str,
                                 Optional('advertised'): 
                                    {Optional(Any()):
                                        {Optional('index'):
                                            {Optional(Any()):
                                                {Optional('next_hop'): str,
                                                 Optional('status_codes'): str,
                                                 Optional('path_type'): str,
                                                 Optional('metric'): int,
                                                 Optional('locprf'): int,
                                                 Optional('weight'): int,
                                                 Optional('path'): str,
                                                 Optional('origin_codes'): str,
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

# ==========================================================================
# Parser for 'show bgp vrf <vrf> all neighbors <neighbor> advertised-routes'
# ==========================================================================
class ShowBgpVrfAllNeighborsAdvertisedRoutes(ShowBgpVrfAllNeighborsAdvertisedRoutesSchema):
    """Parser for show bgp vrf <vrf> all neighbors <neighbor> advertised-routes"""

    def cli(self, vrf, neighbor):
        cmd  = 'show bgp vrf {vrf} all neighbors {neighbor} advertised-routes'.format(vrf=vrf, neighbor=neighbor)
        out = self.device.execute(cmd)
        
        # Init dictionary
        route_dict = {}
        af_dict = {}

        # Init vars
        data_on_nextline =  False
        index = 1
        bgp_table_version = local_router_id = ''

        for line in out.splitlines():
            line = line.rstrip()

            # Peer 21.0.0.2 routes for address family IPv4 Unicast:
            p1 = re.compile(r'^\s*Peer +(?P<neighbor_id>(\S+)) +routes +for'
                             ' +address +family'
                             ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+) *:$')
            m = p1.match(line)
            if m:
                neighbor_id = str(m.groupdict()['neighbor_id'])
                address_family = str(m.groupdict()['address_family']).lower()
                original_address_family = address_family
                continue

            # BGP table version is 25, Local Router ID is 21.0.101.1
            p2 = re.compile(r'^\s*BGP +table +version +is'
                             ' +(?P<bgp_table_version>[0-9]+), +[Ll]ocal +[Rr]outer'
                             ' +ID +is +(?P<local_router_id>(\S+))$')
            m = p2.match(line)
            if m:
                bgp_table_version = int(m.groupdict()['bgp_table_version'])
                local_router_id = str(m.groupdict()['local_router_id'])

                # Init dict
                if 'vrf' not in route_dict:
                    route_dict['vrf'] = {}
                if vrf not in route_dict['vrf']:
                    route_dict['vrf'][vrf] = {}
                if 'neighbor' not in route_dict['vrf'][vrf]:
                    route_dict['vrf'][vrf]['neighbor'] = {}
                if neighbor_id not in route_dict['vrf'][vrf]['neighbor']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id] = {}
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][address_family] = {}

                # Set af_dict
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]

                # Init advertised dict
                if 'advertised' not in af_dict:
                    af_dict['advertised'] = {}

                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['bgp_table_version'] = \
                        bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['local_router_id'] = \
                        local_router_id
                continue

            # Status: s-suppressed, x-deleted, S-stale, d-dampened, h-history, *-valid, >-best
            # Path type: i-internal, e-external, c-confed, l-local, a-aggregate, r-redist, I-injected
            # Origin codes: i - IGP, e - EGP, ? - incomplete, | - multipath, & - backup

            # *>i[2]:[77][7,0][9.9.9.9,1,151587081][29.1.1.1,22][19.0.101.1,29.0.1.30]/616
            # *>iaaaa:1::/113       ::ffff:19.0.101.1
            p3_1 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)?'
                             '(?P<path_type>(i|e|c|l|a|r|I))?'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             '(?: *(?P<next_hop>[a-zA-Z0-9\.\:\/\[\]\,]+))?$')
            m = p3_1.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                data_on_nextline = True

                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])

                # Init dict
                if 'advertised' not in af_dict:
                    af_dict['advertised'] = {}
                if prefix not in af_dict['advertised']:
                    af_dict['advertised'][prefix] = {}
                if 'index' not in af_dict['advertised'][prefix]:
                    af_dict['advertised'][prefix]['index'] = {}
                if index not in af_dict['advertised'][prefix]['index']:
                    af_dict['advertised'][prefix]['index'][index] = {}

                # Set keys
                af_dict['advertised'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['advertised'][prefix]['index'][index]['path_type'] = path_type
                if m.groupdict()['next_hop']:
                    af_dict['advertised'][prefix]['index'][index]['next_hop'] = str(m.groupdict()['next_hop'])
                continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # *>l1.1.1.0/24         0.0.0.0                           100      32768 i
            # *>r1.3.1.0/24         0.0.0.0               4444        100      32768 ?
            # *>r1.3.2.0/24         0.0.0.0               4444        100      32768 ?
            # *>i1.6.0.0/16         19.0.101.1                        100          0 10 20 30 40 50 60 70 80 90 i
            # *>i1.1.2.0/24         19.0.102.4                        100          0 {62112 33492 4872 41787 13166 50081 21461 58376 29755 1135} i
            p3_2 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)'
                             '(?P<path_type>(i|e|c|l|a|r|I))'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             ' +(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             ' +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+)'
                             ' +(?P<origin_codes>(i|e|\?|\&|\|))$')
            m = p3_2.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                
                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                # Init dict
                if 'advertised' not in af_dict:
                    af_dict['advertised'] = {}
                if prefix not in af_dict['advertised']:
                    af_dict['advertised'][prefix] = {}
                if 'index' not in af_dict['advertised'][prefix]:
                    af_dict['advertised'][prefix]['index'] = {}
                if index not in af_dict['advertised'][prefix]['index']:
                    af_dict['advertised'][prefix]['index'][index] = {}
                if index not in af_dict['advertised'][prefix]['index']:
                    af_dict['advertised'][prefix]['index'][index] = {}

                # Set keys
                af_dict['advertised'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['advertised'][prefix]['index'][index]['path_type'] = path_type
                af_dict['advertised'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['advertised'][prefix]['index'][index]['origin_codes'] = origin_codes

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['advertised'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['advertised'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['advertised'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['advertised'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['advertised'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['advertised'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['advertised'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            #                     0.0.0.0               100      32768 i
            #                     19.0.101.1            4444       100 0 3 10 20 30 40 50 60 70 80 90 i
            p3_3 = re.compile(r'^\s*(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             '(?: +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+))?'
                             ' +(?P<origin_codes>(i|e|\?|\|))$')
            m = p3_3.match(line)
            if m:
                # Get keys
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                if data_on_nextline:
                    data_on_nextline =  False
                else:
                    index += 1

                # Init dict
                if 'advertised' not in af_dict:
                    af_dict['advertised'] = {}
                if prefix not in af_dict['advertised']:
                    af_dict['advertised'][prefix] = {}
                if 'index' not in af_dict['advertised'][prefix]:
                    af_dict['advertised'][prefix]['index'] = {}
                if index not in af_dict['advertised'][prefix]['index']:
                    af_dict['advertised'][prefix]['index'][index] = {}

                # Set keys
                af_dict['advertised'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['advertised'][prefix]['index'][index]['origin_codes'] = origin_codes
                try:
                    # Set values of status_codes and path_type from prefix line
                    af_dict['advertised'][prefix]['index'][index]['status_codes'] = status_codes
                    af_dict['advertised'][prefix]['index'][index]['path_type'] = path_type
                except:
                    pass

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['advertised'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['advertised'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['advertised'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['advertised'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['advertised'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['advertised'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['advertised'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['advertised'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # Route Distinguisher: 100:100     (VRF VRF1)
            # Route Distinguisher: 2:100    (VRF vpn2)
            p4 = re.compile(r'^\s*Route +Distinguisher *:'
                             ' +(?P<route_distinguisher>(\S+))'
                             '(?: +\(VRF +(?P<default_vrf>(\S+))\))?$')
            m = p4.match(line)
            if m:
                route_distinguisher = str(m.groupdict()['route_distinguisher'])
                new_address_family = original_address_family + ' RD ' + route_distinguisher
                
                # Init dict
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                        [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if new_address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family] = {}
                
                # Set keys
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['bgp_table_version'] = bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['local_router_id'] = local_router_id
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['route_distinguisher'] = route_distinguisher
                if m.groupdict()['default_vrf']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family]['default_vrf'] = \
                            str(m.groupdict()['default_vrf'])

                # Reset address_family key and af_dict for use in other regex
                address_family = new_address_family
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]

                # Init advertised dict
                if 'advertised' not in af_dict:
                    af_dict['advertised'] = {}
                    continue

        return route_dict


# ===============================================================
# Schema for 'show bgp vrf <vrf> all neighbors <neighbor> routes'
# ===============================================================
class ShowBgpVrfAllNeighborsRoutesSchema(MetaParser):
    """Schema for show bgp vrf <vrf> all neighbors <neighbor> routes"""

    schema = {
        'vrf':
            {Any():
                {'neighbor':
                    {Any():
                        {'address_family':
                            {Any():
                                {Optional('bgp_table_version'): int,
                                 Optional('local_router_id'): str,
                                 Optional('route_distinguisher'): str,
                                 Optional('default_vrf'): str,
                                 Optional('routes'): 
                                    {Optional(Any()):
                                        {Optional('index'):
                                            {Optional(Any()):
                                                {Optional('next_hop'): str,
                                                 Optional('status_codes'): str,
                                                 Optional('path_type'): str,
                                                 Optional('metric'): int,
                                                 Optional('locprf'): int,
                                                 Optional('weight'): int,
                                                 Optional('path'): str,
                                                 Optional('origin_codes'): str,
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

# ===============================================================
# Parser for 'show bgp vrf <vrf> all neighbors <neighbor> routes'
# ===============================================================
class ShowBgpVrfAllNeighborsRoutes(ShowBgpVrfAllNeighborsRoutesSchema):
    """Parser for show bgp vrf <vrf> all neighbors <neighbor> routes"""

    def cli(self, vrf, neighbor):
        cmd  = 'show bgp vrf {vrf} all neighbors {neighbor} routes'.format(vrf=vrf, neighbor=neighbor)
        out = self.device.execute(cmd)
        
        # Init dictionary
        route_dict = {}
        af_dict = {}

        # Init vars
        data_on_nextline =  False
        index = 1
        bgp_table_version = local_router_id = ''

        for line in out.splitlines():
            line = line.rstrip()

            # Peer 21.0.0.2 routes for address family IPv4 Unicast:
            p1 = re.compile(r'^\s*Peer +(?P<neighbor_id>(\S+)) +routes +for'
                             ' +address +family'
                             ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+) *:$')
            m = p1.match(line)
            if m:
                neighbor_id = str(m.groupdict()['neighbor_id'])
                address_family = str(m.groupdict()['address_family']).lower()
                original_address_family = address_family
                continue

            # BGP table version is 25, Local Router ID is 21.0.101.1
            p2 = re.compile(r'^\s*BGP +table +version +is'
                             ' +(?P<bgp_table_version>[0-9]+), +[Ll]ocal +[Rr]outer'
                             ' +ID +is +(?P<local_router_id>(\S+))$')
            m = p2.match(line)
            if m:
                bgp_table_version = int(m.groupdict()['bgp_table_version'])
                local_router_id = str(m.groupdict()['local_router_id'])
                
                # Init dict
                if 'vrf' not in route_dict:
                    route_dict['vrf'] = {}
                if vrf not in route_dict['vrf']:
                    route_dict['vrf'][vrf] = {}
                if 'neighbor' not in route_dict['vrf'][vrf]:
                    route_dict['vrf'][vrf]['neighbor'] = {}
                if neighbor_id not in route_dict['vrf'][vrf]['neighbor']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id] = {}
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][address_family] = {}

                # Set af_dict
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]
                
                # Init routes dict
                if 'routes' not in af_dict:
                    af_dict['routes'] = {}

                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['bgp_table_version'] = \
                        bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['local_router_id'] = \
                        local_router_id
                continue

            # Status: s-suppressed, x-deleted, S-stale, d-dampened, h-history, *-valid, >-best
            # Path type: i-internal, e-external, c-confed, l-local, a-aggregate, r-redist, I-injected
            # Origin codes: i - IGP, e - EGP, ? - incomplete, | - multipath, & - backup

            # *>i[2]:[77][7,0][9.9.9.9,1,151587081][29.1.1.1,22][19.0.101.1,29.0.1.30]/616
            # *>iaaaa:1::/113       ::ffff:19.0.101.1
            p3_1 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)?'
                             '(?P<path_type>(i|e|c|l|a|r|I))?'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             '(?: *(?P<next_hop>[a-zA-Z0-9\.\:\/\[\]\,]+))?$')
            m = p3_1.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                data_on_nextline = True

                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])

                # Init dict
                if 'routes' not in af_dict:
                    af_dict['routes'] = {}
                if prefix not in af_dict['routes']:
                    af_dict['routes'][prefix] = {}
                if 'index' not in af_dict['routes'][prefix]:
                    af_dict['routes'][prefix]['index'] = {}
                if index not in af_dict['routes'][prefix]['index']:
                    af_dict['routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['routes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['routes'][prefix]['index'][index]['path_type'] = path_type
                if m.groupdict()['next_hop']:
                    af_dict['routes'][prefix]['index'][index]['next_hop'] = str(m.groupdict()['next_hop'])
                continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # *>l1.1.1.0/24         0.0.0.0                           100      32768 i
            # *>r1.3.1.0/24         0.0.0.0               4444        100      32768 ?
            # *>r1.3.2.0/24         0.0.0.0               4444        100      32768 ?
            # *>i1.6.0.0/16         19.0.101.1                        100          0 10 20 30 40 50 60 70 80 90 i
            # *>i1.1.2.0/24         19.0.102.4                        100          0 {62112 33492 4872 41787 13166 50081 21461 58376 29755 1135} i
            p3_2 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)'
                             '(?P<path_type>(i|e|c|l|a|r|I))'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             ' +(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             ' +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+)'
                             ' +(?P<origin_codes>(i|e|\?|\&|\|))$')
            m = p3_2.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                
                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                # Init dict
                if 'routes' not in af_dict:
                    af_dict['routes'] = {}
                if prefix not in af_dict['routes']:
                    af_dict['routes'][prefix] = {}
                if 'index' not in af_dict['routes'][prefix]:
                    af_dict['routes'][prefix]['index'] = {}
                if index not in af_dict['routes'][prefix]['index']:
                    af_dict['routes'][prefix]['index'][index] = {}
                if index not in af_dict['routes'][prefix]['index']:
                    af_dict['routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['routes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['routes'][prefix]['index'][index]['path_type'] = path_type
                af_dict['routes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['routes'][prefix]['index'][index]['origin_codes'] = origin_codes

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['routes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['routes'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['routes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['routes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['routes'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['routes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['routes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            #                     0.0.0.0               100      32768 i
            #                     19.0.101.1            4444       100 0 3 10 20 30 40 50 60 70 80 90 i
            p3_3 = re.compile(r'^\s*(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             '(?: +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+))?'
                             ' +(?P<origin_codes>(i|e|\?|\|))$')
            m = p3_3.match(line)
            if m:
                # Get keys
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                if data_on_nextline:
                    data_on_nextline =  False
                else:
                    index += 1

                # Init dict
                if 'routes' not in af_dict:
                    af_dict['routes'] = {}
                if prefix not in af_dict['routes']:
                    af_dict['routes'][prefix] = {}
                if 'index' not in af_dict['routes'][prefix]:
                    af_dict['routes'][prefix]['index'] = {}
                if index not in af_dict['routes'][prefix]['index']:
                    af_dict['routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['routes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['routes'][prefix]['index'][index]['origin_codes'] = origin_codes
                try:
                    # Set values of status_codes and path_type from prefix line
                    af_dict['routes'][prefix]['index'][index]['status_codes'] = status_codes
                    af_dict['routes'][prefix]['index'][index]['path_type'] = path_type
                except:
                    pass

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['routes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['routes'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['routes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['routes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['routes'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['routes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['routes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['routes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # Route Distinguisher: 100:100     (VRF VRF1)
            # Route Distinguisher: 2:100    (VRF vpn2)
            p4 = re.compile(r'^\s*Route +Distinguisher *:'
                             ' +(?P<route_distinguisher>(\S+))'
                             '(?: +\(VRF +(?P<default_vrf>(\S+))\))?$')
            m = p4.match(line)
            if m:
                route_distinguisher = str(m.groupdict()['route_distinguisher'])
                new_address_family = original_address_family + ' RD ' + route_distinguisher
                
                # Init dict
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                        [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if new_address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family] = {}
                
                # Set keys
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['bgp_table_version'] = bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['local_router_id'] = local_router_id
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['route_distinguisher'] = route_distinguisher
                if m.groupdict()['default_vrf']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family]['default_vrf'] = \
                            str(m.groupdict()['default_vrf'])

                # Reset address_family key and af_dict for use in other regex
                address_family = new_address_family
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]
                
                # Init routes dict
                if 'routes' not in af_dict:
                    af_dict['routes'] = {}
                    continue

        return route_dict


# =====================================================================
# Schema for 'show bgp vrf <WORD> all neighbors <WORD> received-routes'
# =====================================================================
class ShowBgpVrfAllNeighborsReceivedRoutesSchema(MetaParser):
    """Schema for show bgp vrf <vrf> all neighbors <neighbor> received-routes"""

    schema = {
        'vrf':
            {Any():
                {'neighbor':
                    {Any():
                        {'address_family':
                            {Any():
                                {Optional('bgp_table_version'): int,
                                 Optional('local_router_id'): str,
                                 Optional('route_distinguisher'): str,
                                 Optional('default_vrf'): str,
                                 Optional('received_routes'): 
                                    {Optional(Any()):
                                        {Optional('index'):
                                            {Optional(Any()):
                                                {Optional('next_hop'): str,
                                                 Optional('status_codes'): str,
                                                 Optional('path_type'): str,
                                                 Optional('metric'): int,
                                                 Optional('locprf'): int,
                                                 Optional('weight'): int,
                                                 Optional('path'): str,
                                                 Optional('origin_codes'): str,
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

# =====================================================================
# Parser for 'show bgp vrf <WORD> all neighbors <WORD> received-routes'
# =====================================================================
class ShowBgpVrfAllNeighborsReceivedRoutes(ShowBgpVrfAllNeighborsReceivedRoutesSchema):
    """Parser for show bgp vrf <vrf> all neighbors <neighbor> received-routes"""

    def cli(self, vrf, neighbor):
        cmd  = 'show bgp vrf {vrf} all neighbors {neighbor} received-routes'.format(vrf=vrf, neighbor=neighbor)
        out = self.device.execute(cmd)
        
        # Init dictionary
        route_dict = {}
        af_dict = {}

        # Init vars
        data_on_nextline =  False
        index = 1
        bgp_table_version = local_router_id = ''

        for line in out.splitlines():
            line = line.rstrip()

            # Peer 21.0.0.2 routes for address family IPv4 Unicast:
            p1 = re.compile(r'^\s*Peer +(?P<neighbor_id>(\S+)) +routes +for'
                             ' +address +family'
                             ' +(?P<address_family>[a-zA-Z0-9\s\-\_]+) *:$')
            m = p1.match(line)
            if m:
                neighbor_id = str(m.groupdict()['neighbor_id'])
                address_family = str(m.groupdict()['address_family']).lower()
                original_address_family = address_family
                continue

            # BGP table version is 25, Local Router ID is 21.0.101.1
            p2 = re.compile(r'^\s*BGP +table +version +is'
                             ' +(?P<bgp_table_version>[0-9]+), +[Ll]ocal +[Rr]outer'
                             ' +ID +is +(?P<local_router_id>(\S+))$')
            m = p2.match(line)
            if m:
                bgp_table_version = int(m.groupdict()['bgp_table_version'])
                local_router_id = str(m.groupdict()['local_router_id'])

                # Init dict
                if 'vrf' not in route_dict:
                    route_dict['vrf'] = {}
                if vrf not in route_dict['vrf']:
                    route_dict['vrf'][vrf] = {}
                if 'neighbor' not in route_dict['vrf'][vrf]:
                    route_dict['vrf'][vrf]['neighbor'] = {}
                if neighbor_id not in route_dict['vrf'][vrf]['neighbor']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id] = {}
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][address_family] = {}

                # Set af_dict
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]
                
                # Init received_routes dict
                if 'received_routes' not in af_dict:
                    af_dict['received_routes'] = {}
                    
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['bgp_table_version'] = \
                        bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]['local_router_id'] = \
                        local_router_id
                continue

            # Status: s-suppressed, x-deleted, S-stale, d-dampened, h-history, *-valid, >-best
            # Path type: i-internal, e-external, c-confed, l-local, a-aggregate, r-redist, I-injected
            # Origin codes: i - IGP, e - EGP, ? - incomplete, | - multipath, & - backup

            # *>i[2]:[77][7,0][9.9.9.9,1,151587081][29.1.1.1,22][19.0.101.1,29.0.1.30]/616
            # *>iaaaa:1::/113       ::ffff:19.0.101.1
            p3_1 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)?'
                             '(?P<path_type>(i|e|c|l|a|r|I))?'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             '(?: *(?P<next_hop>[a-zA-Z0-9\.\:\/\[\]\,]+))?$')
            m = p3_1.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                data_on_nextline = True

                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])

                # Init dict
                if 'received_routes' not in af_dict:
                    af_dict['received_routes'] = {}
                if prefix not in af_dict['received_routes']:
                    af_dict['received_routes'][prefix] = {}
                if 'index' not in af_dict['received_routes'][prefix]:
                    af_dict['received_routes'][prefix]['index'] = {}
                if index not in af_dict['received_routes'][prefix]['index']:
                    af_dict['received_routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['received_routes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['received_routes'][prefix]['index'][index]['path_type'] = path_type
                if m.groupdict()['next_hop']:
                    af_dict['received_routes'][prefix]['index'][index]['next_hop'] = str(m.groupdict()['next_hop'])
                continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # *>l1.1.1.0/24         0.0.0.0                           100      32768 i
            # *>r1.3.1.0/24         0.0.0.0               4444        100      32768 ?
            # *>r1.3.2.0/24         0.0.0.0               4444        100      32768 ?
            # *>i1.6.0.0/16         19.0.101.1                        100          0 10 20 30 40 50 60 70 80 90 i
            # *>i1.1.2.0/24         19.0.102.4                        100          0 {62112 33492 4872 41787 13166 50081 21461 58376 29755 1135} i
            p3_2 = re.compile(r'^\s*(?P<status_codes>(s|x|S|d|h|\*|\>|\s)+)'
                             '(?P<path_type>(i|e|c|l|a|r|I))'
                             '(?P<prefix>[a-zA-Z0-9\.\:\/\[\]\,]+)'
                             ' +(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             ' +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+)'
                             ' +(?P<origin_codes>(i|e|\?|\&|\|))$')
            m = p3_2.match(line)
            if m:
                # New prefix, reset index count
                index = 1
                
                # Get keys
                status_codes = str(m.groupdict()['status_codes'])
                path_type = str(m.groupdict()['path_type'])
                prefix = str(m.groupdict()['prefix'])
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                # Init dict
                if 'received_routes' not in af_dict:
                    af_dict['received_routes'] = {}
                if prefix not in af_dict['received_routes']:
                    af_dict['received_routes'][prefix] = {}
                if 'index' not in af_dict['received_routes'][prefix]:
                    af_dict['received_routes'][prefix]['index'] = {}
                if index not in af_dict['received_routes'][prefix]['index']:
                    af_dict['received_routes'][prefix]['index'][index] = {}
                if index not in af_dict['received_routes'][prefix]['index']:
                    af_dict['received_routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['received_routes'][prefix]['index'][index]['status_codes'] = status_codes
                af_dict['received_routes'][prefix]['index'][index]['path_type'] = path_type
                af_dict['received_routes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['received_routes'][prefix]['index'][index]['origin_codes'] = origin_codes

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['received_routes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['received_routes'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['received_routes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['received_routes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['received_routes'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['received_routes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['received_routes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            #                     0.0.0.0               100      32768 i
            #                     19.0.101.1            4444       100 0 3 10 20 30 40 50 60 70 80 90 i
            p3_3 = re.compile(r'^\s*(?P<next_hop>[a-zA-Z0-9\.\:]+)'
                             '(?: +(?P<numbers>[a-zA-Z0-9\s\(\)\{\}]+))?'
                             ' +(?P<origin_codes>(i|e|\?|\|))$')
            m = p3_3.match(line)
            if m:
                # Get keys
                next_hop = str(m.groupdict()['next_hop'])
                origin_codes = str(m.groupdict()['origin_codes'])

                if data_on_nextline:
                    data_on_nextline =  False
                else:
                    index += 1

                # Init dict
                if 'received_routes' not in af_dict:
                    af_dict['received_routes'] = {}
                if prefix not in af_dict['received_routes']:
                    af_dict['received_routes'][prefix] = {}
                if 'index' not in af_dict['received_routes'][prefix]:
                    af_dict['received_routes'][prefix]['index'] = {}
                if index not in af_dict['received_routes'][prefix]['index']:
                    af_dict['received_routes'][prefix]['index'][index] = {}

                # Set keys
                af_dict['received_routes'][prefix]['index'][index]['next_hop'] = next_hop
                af_dict['received_routes'][prefix]['index'][index]['origin_codes'] = origin_codes
                try:
                    # Set values of status_codes and path_type from prefix line
                    af_dict['received_routes'][prefix]['index'][index]['status_codes'] = status_codes
                    af_dict['received_routes'][prefix]['index'][index]['path_type'] = path_type
                except:
                    pass

                # Parse numbers
                numbers = m.groupdict()['numbers']
                
                # Metric     LocPrf     Weight Path
                #    4444       100          0  10 3 10 20 30 40 50 60 70 80 90
                m1 = re.compile(r'^(?P<metric>[0-9]+)'
                                 '(?P<space1>\s{5,10})'
                                 '(?P<localprf>[0-9]+)'
                                 '(?P<space2>\s{5,10})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    100        ---          0 10 20 30 40 50 60 70 80 90
                #    ---        100          0 10 20 30 40 50 60 70 80 90
                #    100        ---      32788 ---
                #    ---        100      32788 --- 
                m2 = re.compile(r'^(?P<value>[0-9]+)'
                                 '(?P<space>\s{2,21})'
                                 '(?P<weight>[0-9]+)'
                                 '(?: *(?P<path>[0-9\{\}\s]+))?$').match(numbers)

                #    ---        ---      32788 200 33299 51178 47751 {27016}
                m3 = re.compile(r'^(?P<weight>[0-9]+)'
                                 ' +(?P<path>[0-9\{\}\s]+)$').match(numbers)

                if m1:
                    af_dict['received_routes'][prefix]['index'][index]['metric'] = int(m1.groupdict()['metric'])
                    af_dict['received_routes'][prefix]['index'][index]['locprf'] = int(m1.groupdict()['localprf'])
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m1.groupdict()['weight'])
                    # Set path
                    if m1.groupdict()['path']:
                        af_dict['received_routes'][prefix]['index'][index]['path'] = m1.groupdict()['path'].strip()
                        continue
                elif m2:
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m2.groupdict()['weight'])
                    # Set metric or localprf
                    if len(m2.groupdict()['space']) > 10:
                        af_dict['received_routes'][prefix]['index'][index]['metric'] = int(m2.groupdict()['value'])
                    else:
                        af_dict['received_routes'][prefix]['index'][index]['locprf'] = int(m2.groupdict()['value'])
                    # Set path
                    if m2.groupdict()['path']:
                        af_dict['received_routes'][prefix]['index'][index]['path'] = m2.groupdict()['path'].strip()
                        continue
                elif m3:
                    af_dict['received_routes'][prefix]['index'][index]['weight'] = int(m3.groupdict()['weight'])
                    af_dict['received_routes'][prefix]['index'][index]['path'] = m3.groupdict()['path'].strip()
                    continue

            # Network            Next Hop            Metric     LocPrf     Weight Path
            # Route Distinguisher: 100:100     (VRF VRF1)
            # Route Distinguisher: 2:100    (VRF vpn2)
            p4 = re.compile(r'^\s*Route +Distinguisher *:'
                             ' +(?P<route_distinguisher>(\S+))'
                             '(?: +\(VRF +(?P<default_vrf>(\S+))\))?$')
            m = p4.match(line)
            if m:
                route_distinguisher = str(m.groupdict()['route_distinguisher'])
                new_address_family = original_address_family + ' RD ' + route_distinguisher
                
                # Init dict
                if 'address_family' not in route_dict['vrf'][vrf]['neighbor']\
                        [neighbor_id]:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'] = {}
                if new_address_family not in route_dict['vrf'][vrf]['neighbor']\
                    [neighbor_id]['address_family']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family] = {}
                
                # Set keys
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['bgp_table_version'] = bgp_table_version
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['local_router_id'] = local_router_id
                route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][new_address_family]['route_distinguisher'] = route_distinguisher
                if m.groupdict()['default_vrf']:
                    route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                        ['address_family'][new_address_family]['default_vrf'] = \
                            str(m.groupdict()['default_vrf'])

                # Reset address_family key and af_dict for use in other regex
                address_family = new_address_family
                af_dict = route_dict['vrf'][vrf]['neighbor'][neighbor_id]\
                    ['address_family'][address_family]
                
                # Init received_routes dict
                if 'received_routes' not in af_dict:
                    af_dict['received_routes'] = {}
                    continue

        return route_dict


# ====================================
# Schema for 'show running-config bgp'
# ====================================
class ShowRunningConfigBgpSchema(MetaParser):
    """Schema for show running-config bgp"""

    schema = {
        'bgp':
            {'instance':
                {'default':
                    {'bgp_id': int,
                    'protocol_shutdown': bool,
                    Optional('ps_name'):
                        {Any():
                            {'ps_fall_over_bfd': bool,
                            'ps_suppress_four_byte_as_capability': bool,
                            Optional('ps_description'): str,
                            'ps_disable_connected_check': bool,
                            'ps_ebgp_multihop': bool,
                            Optional('ps_ebgp_multihop_max_hop'): int,
                            Optional('ps_local_as_as_no'): int,
                            'ps_local_as_no_prepend': bool,
                            'ps_local_as_dual_as': bool,
                            'ps_local_as_replace_as': bool,
                            Optional('ps_password_text'): str,
                            Optional('ps_remote_as'): int,
                            'ps_shutdown': bool,
                            Optional('ps_keepalive_interval'): int,
                            Optional('ps_hodltime'): int,
                            Optional('ps_transport_connection_mode'): str,
                            Optional('ps_update_source'): str}},
                    Optional('pp_name'):
                        {Any():
                            {Optional('pp_allowas_in'): bool,
                             'pp_allowas_in_as_number': int,
                             'pp_as_override': bool,
                             'pp_default_originate': bool,
                             Optional('pp_default_originate_route_map'): str,
                             Optional('pp_route_map_name_in'): str,
                             Optional('pp_route_map_name_out'): str,
                             Optional('pp_maximum_prefix_max_prefix_no'): int,
                             Optional('pp_maximum_prefix_threshold'): int,
                             Optional('pp_maximum_prefix_restart'): int,
                             Optional('pp_maximum_prefix_warning_only'): bool,
                             'pp_next_hop_self': bool,
                             'pp_route_reflector_client': bool,
                             Optional('pp_send_community'): str,
                             'pp_soft_reconfiguration': bool,
                             Optional('pp_soo'): str}},
                    'vrf':
                        {Any():
                            {Optional('always_compare_med'): bool,
                            Optional('bestpath_compare_routerid'): bool,
                            Optional('bestpath_cost_community_ignore'): bool,
                            Optional('bestpath_med_missing_at_worst'): bool,
                            Optional('cluster_id'): str,
                            Optional('confederation_identifier'): int,
                            Optional('confederation_peers_as'): str,
                            'graceful_restart': bool,
                            Optional('graceful_restart_restart_time'): int,
                            Optional('graceful_restart_stalepath_time'): int,
                            'log_neighbor_changes': bool,
                            Optional('router_id'): str,
                            Optional('keepalive_interval'): int,
                            Optional('holdtime'): int,
                            'enforce_first_as': bool,
                            'fast_external_fallover': bool,
                            Optional('default_choice_ipv4_unicast'): str,
                            Optional('dynamic_med_interval'): int,
                            Optional('shutdown'): str,
                            'flush_routes': bool,
                            'isolate': bool,
                            Optional('disable_policy_batching_ipv4'): str,
                            Optional('disable_policy_batching_ipv6'): str,
                            Optional('af_name'):
                                {Any():
                                    {Optional('af_dampening'): bool,
                                    Optional('af_dampening_route_map'): str,
                                    Optional('af_dampening_half_life_time'): int,
                                    Optional('af_dampening_reuse_time'): int,
                                    Optional('af_dampening_suppress_time'): int,
                                    Optional('af_dampening_max_suppress_time'): int,
                                    Optional('af_nexthop_route_map'): str,
                                    Optional('af_nexthop_trigger_enable'): bool,
                                    Optional('af_nexthop_trigger_delay_critical'): int,
                                    Optional('af_nexthop_trigger_delay_non_critical'): int,
                                    Optional('af_client_to_client_reflection'): bool,
                                    Optional('af_distance_extern_as'): int,
                                    Optional('af_distance_internal_as'): int,
                                    Optional('af_distance_local'): int,
                                    Optional('af_maximum_paths_ebgp'): int,
                                    Optional('af_maximum_paths_ibgp'): int,
                                    Optional('af_maximum_paths_eibgp'): int,
                                    Optional('af_aggregate_address_ipv4_address'): str,
                                    Optional('af_aggregate_address_ipv4_mask'): int,
                                    Optional('af_aggregate_address_as_set'): bool,
                                    Optional('af_aggregate_address_summary_only'): bool,
                                    Optional('af_network_number'): str,
                                    Optional('af_network_mask'): int,
                                    Optional('af_network_route_map'): str,
                                    Optional('af_redist_isis'): str,
                                    Optional('af_redist_isis_metric'): str,
                                    Optional('af_redist_isis_route_policy'): str,
                                    Optional('af_redist_ospf'): str,
                                    Optional('af_redist_ospf_metric'): str,
                                    Optional('af_redist_ospf_route_policy'): str,
                                    Optional('af_redist_rip'): str,
                                    Optional('af_redist_rip_metric'): str,
                                    Optional('af_redist_rip_route_policy'): str,
                                    Optional('af_redist_static'): bool,
                                    Optional('af_redist_static_metric'): str,
                                    Optional('af_redist_static_route_policy'): str,
                                    Optional('af_redist_connected'): bool,
                                    Optional('af_redist_connected_metric'): str,
                                    Optional('af_redist_connected_route_policy'): str,
                                    Optional('af_v6_aggregate_address_ipv6_address'): str,
                                    Optional('af_v6_aggregate_address_as_set'): bool,
                                    Optional('af_v6_aggregate_address_summary_only'): bool,
                                    Optional('af_v6_network_number'): str,
                                    Optional('af_v6_network_route_map'): str,
                                    Optional('af_v6_allocate_label_all'): bool,
                                    Optional('af_retain_rt_all'): bool,
                                    Optional('af_label_allocation_mode'): str}},
                            Optional('neighbor_id'):
                                {Any():
                                    {Optional('nbr_fall_over_bfd'): bool,
                                     Optional('nbr_suppress_four_byte_as_capability'): bool,
                                     Optional('nbr_description'): str,
                                     Optional('nbr_disable_connected_check'): bool,
                                     Optional('nbr_ebgp_multihop'): bool,
                                     Optional('nbr_ebgp_multihop_max_hop'): int,
                                     Optional('nbr_inherit_peer_session'): str,
                                     Optional('nbr_local_as_as_no'): int,
                                     Optional('nbr_local_as_no_prepend'): bool,
                                     Optional('nbr_local_as_replace_as'): bool,
                                     Optional('nbr_local_as_dual_as'): bool,
                                     Optional('nbr_remote_as'): int,
                                     Optional('nbr_remove_private_as'): bool,
                                     Optional('nbr_shutdown'): bool,
                                     Optional('nbr_keepalive_interval'): int,
                                     Optional('nbr_holdtime'): int,
                                     Optional('nbr_update_source'): str,
                                     Optional('nbr_password_text'): str,
                                     Optional('nbr_transport_connection_mode'): str,
                                     Optional('nbr_af_name'):
                                        {Any():
                                            {Optional('nbr_af_allowas_in'): bool,
                                            Optional('nbr_af_allowas_in_as_number'): int,
                                            Optional('nbr_af_inherit_peer_policy'): str,
                                            Optional('nbr_af_inherit_peer_seq'): int,
                                            Optional('nbr_af_maximum_prefix_max_prefix_no'): int,
                                            Optional('nbr_af_maximum_prefix_threshold'): int,
                                            Optional('nbr_af_maximum_prefix_restart'): int,
                                            Optional('nbr_af_maximum_prefix_warning_only'): bool,
                                            Optional('nbr_af_route_map_name_in'): str,
                                            Optional('nbr_af_route_map_name_out'): str,
                                            Optional('nbr_af_route_reflector_client'): bool,
                                            Optional('nbr_af_send_community'): str,
                                            Optional('nbr_af_soft_reconfiguration'): bool,
                                            Optional('nbr_af_next_hop_self'): bool,
                                            Optional('nbr_af_as_override'): bool,
                                            Optional('nbr_af_default_originate'): bool,
                                            Optional('nbr_af_default_originate_route_map'): str,
                                            Optional('nbr_af_soo'): str},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            }

# ====================================
# Parser for 'show running-config bgp'
# ====================================
class ShowRunningConfigBgp(ShowRunningConfigBgpSchema):
    """Parser for show running-config bgp"""

    def cli(self):
        cmd  = 'show running-config bgp'
        out = self.device.execute(cmd)

        # Init vars
        bgp_dict = {}
        bgp_id = ''
        protocol_shutdown = False
        send_community_standard_match = 'False'
        peer_policy_send_community_standard_match = 'False'
        neighbor_id = ''
        af_name = ''
        nbr_af_name = ''
        ps_name = ''
        pp_name = ''

        for line in out.splitlines():
            line = line.rstrip()
            # router bgp 333
            p1 = re.compile(r'^\s*router +bgp +(?P<bgp_id>[0-9]+)$')
            m = p1.match(line)
            if m:
                bgp_id = int(m.groupdict()['bgp_id'])
                if 'bgp' not in bgp_dict:
                    bgp_dict['bgp'] = {}
                if 'instance' not in bgp_dict['bgp']:
                    bgp_dict['bgp']['instance'] = {}
                if 'default' not in bgp_dict['bgp']['instance']:
                    bgp_dict['bgp']['instance']['default'] = {}
                bgp_dict['bgp']['instance']['default']['bgp_id'] = bgp_id
                bgp_dict['bgp']['instance']['default']['protocol_shutdown'] = \
                    protocol_shutdown
                vrf = 'default'
                if 'vrf' not in bgp_dict['bgp']['instance']['default']:
                    bgp_dict['bgp']['instance']['default']['vrf'] = {}
                if vrf not in bgp_dict['bgp']['instance']['default']['vrf']:
                    bgp_dict['bgp']['instance']['default']['vrf'][vrf] = {}
                continue

            if bgp_id:
                #   shutdown
                p2 = re.compile(r'^\s*shutdown$')
                m = p2.match(line)
                if m:
                    bgp_dict['bgp']['instance']['default']['protocol_shutdown'] = True
                    continue

                #   vrf vpn1
                p3 = re.compile(r'^\s*vrf +(?P<vrf>[a-z0-9]+)$')
                m = p3.match(line)
                if m:
                    # Get keys
                    vrf = str(m.groupdict()['vrf'])
                    af_name = ''
                    neighbor_id = ''
                    nbr_af_name = ''
                    if 'vrf' not in bgp_dict['bgp']['instance']['default']:
                        bgp_dict['bgp']['instance']['default']['vrf'] = {}
                    if vrf not in bgp_dict['bgp']['instance']['default']['vrf']:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf] = {}
                    continue

                if vrf:
                    #   bestpath cost-community ignore
                    #   bestpath compare-routerid
                    #   bestpath med missing-as-worst
                    #   bestpath always-compare-med
                    p4 = re.compile(r'^\s*bestpath +(?P<best_path>[a-z\-\s]+)$')
                    m = p4.match(line)
                    if m:
                        # Get keys
                        best_path = str(m.groupdict()['best_path'])
                        # Initialize variables
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['always_compare_med'] = \
                            False
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_compare_routerid'] = \
                            False
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_cost_community_ignore'] = \
                            False
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_med_missing_at_worst'] = \
                            False
                        if best_path == 'cost-community ignore':
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_cost_community_ignore'] = True
                        elif best_path == 'compare-routerid':
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_compare_routerid'] = True
                        elif best_path == 'med missing-as-worst':
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['bestpath_med_missing_at_worst'] = True
                        elif best_path == 'always-compare-med':
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['always_compare_med'] = True
                        continue

                    #   cluster-id <cluster_id>
                    p5 = re.compile(r'^\s*cluster-id +(?P<cluster_id>[0-9\.]+)$')
                    m = p5.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['cluster_id'] = \
                            str(m.groupdict()['cluster_id'])
                        continue

                    #   confederation identifier <confederation_identifier>
                    p6 = re.compile(r'^\s*confederation +identifier +(?P<confederation_identifier>[0-9]+)$')
                    m = p6.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['confederation_identifier'] = \
                            int(m.groupdict()['confederation_identifier'])
                        continue

                    #   confederation peers <confederation_peers_as>
                    p7 = re.compile(r'^\s*confederation +peers +(?P<confederation_peers_as>[0-9]+)$')
                    m = p7.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['confederation_peers_as'] = \
                            str(m.groupdict()['confederation_peers_as'])
                        continue

                    #   no graceful-restart
                    p8 = re.compile(r'^\s*no graceful-restart$')
                    m = p8.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['graceful_restart'] = False
                        continue
                    elif 'graceful_restart' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['graceful_restart'] = True

                    #   graceful-restart restart-time 121
                    #   graceful-restart stalepath-time 301
                    p9 = re.compile(r'^\s*graceful-restart'
                                     ' +(?P<graceful_restart_type>[a-z\-]+)'
                                     ' +(?P<time>[0-9]+)$')
                    m = p9.match(line)
                    if m:
                        graceful_restart_type = \
                            str(m.groupdict()['graceful_restart_type'])
                        if graceful_restart_type == 'restart-time':
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf][
                                'graceful_restart_restart_time'] = \
                                    int(m.groupdict()['time'])
                        else:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf][
                                'graceful_restart_stalepath_time'] = \
                                    int(m.groupdict()['time'])
                        continue

                    #   log-neighbor-changes
                    p10 = re.compile(r'^\s*log-neighbor-changes$')
                    m = p10.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['log_neighbor_changes'] = True
                        continue
                    elif 'log_neighbor_changes' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['log_neighbor_changes'] = False

                    #   router-id <router-id>
                    p11 = re.compile(r'^\s*router-id +(?P<router_id>[0-9\.]+)$')
                    m = p11.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['router_id'] = \
                            str(m.groupdict()['router_id'])
                        continue

                    #   timers bgp <keepalive-interval> <holdtime>
                    p12 = re.compile(r'^\s*timers +bgp +(?P<keepalive_interval>[0-9]+)'
                                      ' +(?P<holdtime>[0-9]+)$')
                    m = p12.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['keepalive_interval'] = \
                            int(m.groupdict()['keepalive_interval'])
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['holdtime'] = \
                            int(m.groupdict()['holdtime'])
                        continue

                    #   no enforce-first-as
                    p13 = re.compile(r'^\s*no enforce-first-as$')
                    m = p13.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['enforce_first_as'] = False
                        continue
                    elif 'enforce_first_as' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['enforce_first_as'] = True

                    #   no fast-external-fallover
                    p14 = re.compile(r'^\s*no fast-external-fallover$')
                    m = p14.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['fast_external_fallover'] = False
                        continue
                    elif 'fast_external_fallover' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['fast_external_fallover'] = True

                    #   dynamic-med-interval 70
                    p15 = re.compile(r'^\s*dynamic-med-interval +(?P<dynamic_med_interval>[0-9]+)$')
                    m = p15.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['dynamic_med_interval'] = \
                            int(m.groupdict()['dynamic_med_interval'])
                        continue

                    #   flush-routes
                    p16 = re.compile(r'^\s*flush-routes$')
                    m = p16.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['flush_routes'] = True
                        continue
                    elif 'flush_routes' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['flush_routes'] = False

                    #   isolate
                    p17 = re.compile(r'^\s*isolate$')
                    m = p17.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['isolate'] = True
                        continue
                    elif 'isolate' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['isolate'] = False

                    #   disable-policy-batching ipv4 prefix-list <WORD>
                    p18 = re.compile(r'^\s*disable-policy-batching ipv4 prefix-list +(?P<disable_policy_batching_ipv4>[a-zA-Z0-9]+)$')
                    m = p18.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['disable_policy_batching_ipv4'] = \
                            str(m.groupdict()['disable_policy_batching_ipv4'])
                        continue

                    #   disable-policy-batching ipv4 prefix-list <WORD>
                    p19 = re.compile(r'^\s*disable-policy-batching ipv6 prefix-list +(?P<disable_policy_batching_ipv6>[a-zA-Z0-9]+)$')
                    m = p19.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['disable_policy_batching_ipv6'] = \
                            str(m.groupdict()['disable_policy_batching_ipv6'])
                        continue

                    if neighbor_id == '':
                        #   address-family ipv4 multicast
                        p20 = re.compile(r'^\s*address-family +(?P<af_name>[a-z0-9\-\s]+)$')
                        m = p20.match(line)
                        if m:
                            # Get keys
                            af_name = str(m.groupdict()['af_name'])
                            if 'af_name' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'] = {}
                            if af_name not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name']:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name] = {}
                            continue

                    if af_name:
                        #    dampening [ { <af_dampening_half_life_time>
                        #    <af_dampening_resuse_time> <af_dampening_suppress_time>
                        #    <af_dampening_max_suppress_time> } |
                        #    { route-map <af_dampening_route_map> } ]
                        p21 = re.compile(r'^\s*dampening '
                                          '+(?P<af_dampening_half_life_time>[0-9]+) '
                                          '+(?P<af_dampening_reuse_time>[0-9]+) '
                                          '+(?P<af_dampening_suppress_time>[0-9]+) '
                                          '+(?P<af_dampening_max_suppress_time>[0-9]+)$')
                        m = p21.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening'] = \
                                True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening_half_life_time'] = \
                                int(m.groupdict()['af_dampening_half_life_time'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening_reuse_time'] = \
                                int(m.groupdict()['af_dampening_reuse_time'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening_suppress_time'] = \
                                int(m.groupdict()['af_dampening_suppress_time'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening_max_suppress_time'] = \
                                int(m.groupdict()['af_dampening_max_suppress_time'])
                            continue

                        #    dampening [ { route-map <af_dampening_route_map> } ]
                        p22 = re.compile(r'^\s*dampening +route-map +(?P<af_dampening_route_map>[A-Z0-9\-\_]+)$')
                        m = p22.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening'] = \
                                True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_dampening_route_map'] = \
                                str(m.groupdict()['af_dampening_route_map'])
                            continue

                        #    nexthop route-map <af_nexthop_route_map>
                        p23 = re.compile(r'^\s*nexthop +route-map +(?P<af_nexthop_route_map>[A-Za-z0-9\-\_]+)$')
                        m = p23.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_nexthop_route_map'] = \
                                str(m.groupdict()['af_nexthop_route_map'])
                            continue

                        #     { nexthop trigger-delay critical
                        #     <af_nexthop_trigger_delay_critical> non-critical
                        #     <af_nexthop_trigger_delay_non_critical> } |
                        #     { no nexthop trigger-delay }
                        p24 = re.compile(r'^\s*nexthop +trigger-delay +critical +(?P<af_nexthop_trigger_delay_critical>[0-9]+) +non-critical +(?P<af_nexthop_trigger_delay_non_critical>[0-9]+)$')
                        m = p24.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_nexthop_trigger_enable'] = \
                                True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_nexthop_trigger_delay_critical'] = \
                                int(m.groupdict()['af_nexthop_trigger_delay_critical'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_nexthop_trigger_delay_non_critical'] = \
                                int(m.groupdict()['af_nexthop_trigger_delay_non_critical'])
                            continue

                        #     {no nexthop trigger-delay }
                        p25 = re.compile(r'^\s*no nexthop trigger-delay$')
                        m = p25.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_nexthop_trigger_enable'] = \
                                False
                            continue

                        #     {no client-to-client reflection }
                        p26 = re.compile(r'^\s*no client-to-client reflection$')
                        m = p26.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_client_to_client_reflection'] = \
                                False
                            continue
                        elif 'af_client_to_client_reflection' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_client_to_client_reflection'] = \
                                True

                        #    distance <af_distance_extern_as> <af_distance_internal_as> <af_distance_local> | no distance [ <af_distance_extern_as> <af_distance_internal_as> <af_distance_local> ]
                        p27 = re.compile(r'^\s*distance +(?P<af_distance_extern_as>[0-9]+) +(?P<af_distance_internal_as>[0-9]+) +(?P<af_distance_local>[0-9]+)$')
                        m = p27.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_distance_extern_as'] = \
                                int(m.groupdict()['af_distance_extern_as'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_distance_internal_as'] = \
                                int(m.groupdict()['af_distance_internal_as'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_distance_local'] = \
                                int(m.groupdict()['af_distance_local'])
                            continue

                        #    maximum-paths <af_maximum_paths_ebgp>
                        #    maximum-paths ibgp <af_maximum_paths_ibgp>
                        p28 = re.compile(r'^\s*maximum-paths( +(?P<af_maximum_paths_type>[a-z]+))? +(?P<af_maximum_paths_value>[0-9]+)$')
                        m = p28.match(line)
                        if m:
                            if m.groupdict()['af_maximum_paths_type']:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_maximum_paths_ibgp'] = \
                                    int(m.groupdict()['af_maximum_paths_value'])
                            else:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_maximum_paths_ebgp'] = \
                                    int(m.groupdict()['af_maximum_paths_value'])
                            continue

                        #    maximum-paths eibgp <af_maximum_paths_eibgp>
                        p29 = re.compile(r'^\s*maximum-paths +eibgp +(?P<af_maximum_paths_eibgp>[0-9]+)$')
                        m = p29.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_maximum_paths_eibgp'] = \
                                int(m.groupdict()['af_maximum_paths_eibgp'])
                            continue

                        #    aggregate-address <af_aggregate_address_ipv4_address>/<af_aggregate_address_ipv4_mask> [ as-set | summary-only ] +
                        #    aggregate-address <af_v6_aggregate_address_ipv6_address> [ as-set | summary-only ] +
                        p30 = re.compile(r'^\s*aggregate-address +(?P<af_aggregate_address_address>[a-z0-9\.\:]+)(\/(?P<af_aggregate_address_ipv4_mask>[0-9]+))?( +(?P<extra_line>[a-z\-\s]+))?$')
                        m = p30.match(line)
                        if m:
                            ip_address = str(m.groupdict()['af_aggregate_address_address'])
                            if '::' not in ip_address:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_ipv4_address'] = \
                                    ip_address
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_ipv4_mask'] = \
                                    int(m.groupdict()['af_aggregate_address_ipv4_mask'])
                                if m.groupdict()['extra_line']:
                                    if m.groupdict()['extra_line'] == 'as-set':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_as_set'] = \
                                            True
                                    elif m.groupdict()['extra_line'] == 'summary-only':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_summary_only'] = \
                                            True
                                    elif m.groupdict()['extra_line'] == 'as-set summary-only':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_as_set'] = \
                                            True
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_aggregate_address_summary_only'] = \
                                            True
                            else:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_aggregate_address_ipv6_address'] = \
                                    ip_address
                                if m.groupdict()['extra_line']:
                                    if m.groupdict()['extra_line'] == 'as-set':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_aggregate_address_as_set'] = \
                                            True
                                    elif m.groupdict()['extra_line'] == 'summary-only':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_aggregate_address_summary_only'] = \
                                            True
                                    elif m.groupdict()['extra_line'] == 'as-set summary-only':
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_aggregate_address_as_set'] = \
                                            True
                                        bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_aggregate_address_summary_only'] = \
                                            True
                            continue

                        #    network { <af_network_number> mask <af_network_mask> } [ route-map <rmap-name> ] +
                        #    network <af_v6_network_number> [ route-map <af_v6_network_route_map> ] +
                        p31 = re.compile(r'^\s*network +(?P<af_network_number>[0-9\.\:\/]+)( +mask +(?P<af_network_mask>[0-9\.]+))?( +route-map +(?P<af_network_route_map>[A-Za-z0-9\-\_]+))?$')
                        m = p31.match(line)
                        if m:
                            if m.groupdict()['af_network_mask']:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_number'] = \
                                    str(m.groupdict()['af_network_number'])
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_mask'] = \
                                    str(m.groupdict()['af_network_mask'])
                                if m.groupdict()['af_network_route_map']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_route_map'] = \
                                        str(m.groupdict()['af_network_route_map'])
                            else:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_network_number'] = \
                                    str(m.groupdict()['af_network_number'])
                                if m.groupdict()['af_network_route_map']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_network_route_map'] = \
                                        str(m.groupdict()['af_network_route_map'])
                            continue

                        #    network { <af_network_number>/<ip-prefix> } [ route-map <rmap-name> ] +
                        p32 = re.compile(r'^\s*network +(?P<af_network_number>[0-9\.]+)\/(?P<af_network_mask>[0-9]+)( +route-map +(?P<af_network_route_map>[A-Za-z0-9\-\_]+))?$')
                        m = p32.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_number'] = \
                                str(m.groupdict()['af_network_number'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_mask'] = \
                                str(m.groupdict()['af_network_mask'])
                            if m.groupdict()['af_network_route_map']:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_network_route_map'] = \
                                    str(m.groupdict()['af_network_route_map'])
                            continue

                        #    redistribute isis <Isis.pid> route-map <route_policy>
                        p33 = re.compile(r'^\s*redistribute +isis +(?P<af_redist_isis>[0-9]+) +route-map+(?P<af_redist_isis_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p33.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_isis'] = \
                                str(m.groupdict()['af_redist_isis'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_isis_route_policy'] = \
                                str(m.groupdict()['af_redist_isis_route_policy'])
                            continue

                        #    redistribute isis <Isis.pid> route-map <route_policy>
                        p34 = re.compile(r'^\s*redistribute +isis +(?P<af_redist_isis>[0-9]+) +route-map+(?P<af_redist_isis_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p34.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_isis'] = \
                                str(m.groupdict()['af_redist_isis'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_isis_route_policy'] = \
                                str(m.groupdict()['af_redist_isis_route_policy'])
                            continue

                        #    redistribute ospf <Ospf.pid> route-map <route_policy>
                        p35 = re.compile(r'^\s*redistribute +ospf +(?P<af_redist_ospf>[0-9]+) +route-map+(?P<af_redist_ospf_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p35.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_ospf'] = \
                                str(m.groupdict()['af_redist_ospf'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_ospf_route_policy'] = \
                                str(m.groupdict()['af_redist_ospf_route_policy'])
                            continue

                        #    Redistribute rip <Rip.pid> route-map <route_policy>
                        p36 = re.compile(r'^\s*redistribute +rip +(?P<af_redist_rip>[0-9]+) +route-map +(?P<af_redist_rip_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p36.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_rip'] = \
                                str(m.groupdict()['af_redist_rip'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_rip_route_policy'] = \
                                str(m.groupdict()['af_redist_rip_route_policy'])
                            continue

                        #    redistribute static route-map <route_policy>
                        p37 = re.compile(r'^\s*redistribute +static +route-map +(?P<af_redist_static_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p37.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_static'] = True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_static_route_policy'] = \
                                str(m.groupdict()['af_redist_static_route_policy'])
                            continue

                        #    redistribute direct route-map <route_policy>
                        p38 = re.compile(r'^\s*redistribute +direct +route-map +(?P<af_redist_connected_route_policy>[A-Za-z0-9\-\_]+)$')
                        m = p38.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_connected'] = True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_redist_connected_route_policy'] = \
                                str(m.groupdict()['af_redist_connected_route_policy'])
                            continue

                        #    allocate-label all
                        p39 = re.compile(r'^\s*allocate-label all$')
                        m = p39.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_v6_allocate_label_all'] = True
                            continue

                        #    retain route-target all
                        p40 = re.compile(r'^\s*retain route-target all$')
                        m = p40.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_retain_rt_all'] = True
                            continue

                        #    label-allocation-mode per-vrf
                        p41 = re.compile(r'^\s*label-allocation-mode +(?P<per_vrf>[A-Za-z0-9]+)$')
                        m = p41.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['af_name'][af_name]['af_label_allocation_mode'] = \
                                str(m.groupdict()['per_vrf'])
                            continue

                    #   neighbor <neighbor_id>
                    p42 = re.compile(r'^\s*neighbor +(?P<neighbor_id>[a-z0-9\.\:]+)$')
                    m = p42.match(line)
                    if m:
                        # Get keys
                        neighbor_id = str(m.groupdict()['neighbor_id'])
                        if 'neighbor_id' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'] = {}
                        if neighbor_id not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id']:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id] = {}
                        continue

                    #   Same line of configuration can be configured under the peer session section
                    if neighbor_id:
                        #   bfd
                        p43 = re.compile(r'^\s*bfd$')
                        m = p43.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_fall_over_bfd'] = \
                                True
                            continue
                        elif 'nbr_fall_over_bfd' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_fall_over_bfd'] = \
                                False

                        #   capability suppress 4-byte-as
                        p44 = re.compile(r'^\s*capability suppress 4-byte-as$')
                        m = p44.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_suppress_four_byte_as_capability'] = \
                                True
                            continue
                        elif 'nbr_suppress_four_byte_as_capability' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_suppress_four_byte_as_capability'] = \
                                False

                        #   description <nbr_description>
                        p45 = re.compile(r'^\s*description +(?P<nbr_description>[A-Za-z0-9]+)$')
                        m = p45.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_description'] = \
                                str(m.groupdict()['nbr_description'])
                            continue

                        #   disable-connected-check
                        p46 = re.compile(r'^\s*disable-connected-check$')
                        m = p46.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_disable_connected_check'] = \
                                True
                            continue
                        elif 'nbr_disable_connected_check' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_disable_connected_check'] = \
                                False

                        #   ebgp-multihop <nbr_ebgp_multihop_max_hop>
                        p47 = re.compile(r'^\s*ebgp-multihop +(?P<nbr_ebgp_multihop_max_hop>[0-9]+)$')
                        m = p47.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_ebgp_multihop'] = \
                                True
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_ebgp_multihop_max_hop'] = \
                                int(m.groupdict()['nbr_ebgp_multihop_max_hop'])
                            continue
                        elif 'nbr_ebgp_multihop' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_ebgp_multihop'] = \
                                False

                        #   inherit peer-session <nbr_inherit_peer_session>
                        p48 = re.compile(r'^\s*inherit peer-session +(?P<nbr_inherit_peer_session>[A-Za-z0-9\-]+)$')
                        m = p48.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_inherit_peer_session'] = \
                                str(m.groupdict()['nbr_inherit_peer_session'])
                            continue

                        #    { local-as <nbr_local_as_as_no> [ no-prepend [ replace-as [ dual-as ] ] ] }
                        p49 = re.compile(r'^\s*local-as +(?P<nbr_local_as_as_no>[0-9\.]+)( +(?P<no_prepend>no-prepend)( +(?P<replace_as>replace-as)( +(?P<dual_as>dual-as))?)?)?$')
                        m = p49.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_as_no'] = \
                                int(m.groupdict()['nbr_local_as_as_no'])
                            if 'nbr_local_as_no_prepend' in m.groupdict():
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_no_prepend'] = \
                                    True
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_replace_as'] = \
                                    True
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_dual_as'] = \
                                    True
                            continue
                        elif 'nbr_local_as_no_prepend' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_no_prepend'] = \
                                False
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_replace_as'] = \
                                False
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_local_as_dual_as'] = \
                                False

                        #   { remote-as <nbr_remote_as> }
                        p50 = re.compile(r'^\s*remote-as +(?P<nbr_remote_as>[0-9]+)$')
                        m = p50.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_remote_as'] = \
                                int(m.groupdict()['nbr_remote_as'])
                            continue

                        #   remove-private-as
                        p51 = re.compile(r'^\s*remove-private-as$')
                        m = p51.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_remove_private_as'] = \
                                True
                            continue
                        elif 'nbr_remove_private_as' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_remove_private_as'] = \
                                False

                        #   shutdown
                        p52 = re.compile(r'^\s*shutdown$')
                        m = p52.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_shutdown'] = \
                                True
                            continue
                        elif 'nbr_shutdown' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_shutdown'] = \
                                False

                        #   timers <nbr_keepalive_interval> <nbr_holdtime>
                        p53 = re.compile(r'^\s*timers +(?P<nbr_keepalive_interval>[0-9]+) +(?P<nbr_holdtime>[0-9]+)$')
                        m = p53.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_keepalive_interval'] = \
                                int(m.groupdict()['nbr_keepalive_interval'])
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_holdtime'] = \
                                int(m.groupdict()['nbr_holdtime'])
                            continue

                        #   update-source <nbr_update_source>
                        p54 = re.compile(r'^\s*update-source +(?P<nbr_update_source>[A-Za-z0-9\/\.]+)$')
                        m = p54.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_update_source'] = \
                                str(m.groupdict()['nbr_update_source'])
                            continue

                        #   password <nbr_password_text>
                        p55 = re.compile(r'^\s*password +(?P<nbr_password_text>.*)$')
                        m = p55.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_password_text'] = \
                                str(m.groupdict()['nbr_password_text'])
                            continue

                        #   transport connection-mode <nbr_transport_connection_mode>
                        p56 = re.compile(r'^\s*transport connection-mode +(?P<nbr_transport_connection_mode>[a-z]+)$')
                        m = p56.match(line)
                        if m:
                            bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_transport_connection_mode'] = \
                                str(m.groupdict()['nbr_transport_connection_mode'])
                            continue

                        #   address-family <nbr_af_name>
                        p57 = re.compile(r'^\s*address-family +(?P<nbr_af_name>[A-Za-z0-9\s\-]+)$')
                        m = p57.match(line)
                        if m:
                            nbr_af_name = str(m.groupdict()['nbr_af_name'])
                            if 'nbr_af_name' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'] = {}
                            if nbr_af_name not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name']:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name] = {}
                            continue

                        if nbr_af_name:
                            #   allowas-in [ <allowas-in-cnt> ]
                            p58 = re.compile(r'^\s*allowas-in( +(?P<nbr_af_allowas_in_as_number>[0-9]+))?$')
                            m = p58.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_allowas_in'] = \
                                    True
                                if m.groupdict()['nbr_af_allowas_in_as_number']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_allowas_in_as_number'] = \
                                        int(m.groupdict()['nbr_af_allowas_in_as_number'])
                                continue
                            elif 'nbr_af_allowas_in' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_allowas_in'] = \
                                    False

                            #   inherit peer-policy <nbr_af_inherit_peer_policy> <nbr_af_inherit_peer_seq>
                            p59 = re.compile(r'^\s*inherit peer-policy +(?P<nbr_af_inherit_peer_policy>[A-Za-z0-9\-]+) +(?P<nbr_af_inherit_peer_seq>[0-9]+)$')
                            m = p59.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_inherit_peer_policy'] = \
                                    str(m.groupdict()['nbr_af_inherit_peer_policy'])
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_inherit_peer_seq'] = \
                                    int(m.groupdict()['nbr_af_inherit_peer_seq'])
                                continue

                            #   maximum-prefix <nbr_af_maximum_prefix_max_prefix_no> [ <nbr_af_maximum_prefix_threshold> ] [ restart <nbr_af_maximum_prefix_restart> ]
                            p60 = re.compile(r'^\s*maximum-prefix +(?P<nbr_af_maximum_prefix_max_prefix_no>[0-9]+)( +(?P<nbr_af_maximum_prefix_threshold>[0-9]+))?( +restart +(?P<nbr_af_maximum_prefix_restart>[0-9]+))?$')
                            m = p60.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_max_prefix_no'] = \
                                    int(m.groupdict()['nbr_af_maximum_prefix_max_prefix_no'])
                                if m.groupdict()['nbr_af_maximum_prefix_threshold']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_threshold'] = \
                                        int(m.groupdict()['nbr_af_maximum_prefix_threshold'])
                                if m.groupdict()['nbr_af_maximum_prefix_restart']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_restart'] = \
                                        int(m.groupdict()['nbr_af_maximum_prefix_restart'])
                                continue

                            #   maximum-prefix <nbr_af_maximum_prefix_max_prefix_no> [ <nbr_af_maximum_prefix_threshold> ] [ warning-only ]
                            p61 = re.compile(r'^\s*maximum-prefix +(?P<nbr_af_maximum_prefix_max_prefix_no>[0-9]+)( +(?P<nbr_af_maximum_prefix_threshold>[0-9]+))?( +(?P<nbr_af_maximum_prefix_warning_only>warning-only))?$')
                            m = p61.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_max_prefix_no'] = \
                                    int(m.groupdict()['nbr_af_maximum_prefix_max_prefix_no'])
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_threshold'] = \
                                    int(m.groupdict()['nbr_af_maximum_prefix_threshold'])
                                if m.groupdict()['nbr_af_maximum_prefix_warning_only']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_warning_only'] = \
                                        True
                                else:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_maximum_prefix_warning_only'] = \
                                        False
                                continue

                            #   route-map <nbr_af_route_map_name_in> in
                            p62 = re.compile(r'^\s*route-map +(?P<nbr_af_route_map_name_in>.*) in$')
                            m = p62.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_route_map_name_in'] = \
                                    str(m.groupdict()['nbr_af_route_map_name_in'])
                                continue

                            #   route-map <nbr_af_route_map_name_out> out
                            p63 = re.compile(r'^\s*route-map +(?P<nbr_af_route_map_name_out>.*) out$')
                            m = p63.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_route_map_name_out'] = \
                                    str(m.groupdict()['nbr_af_route_map_name_out'])
                                continue

                            #   route-reflector-client
                            p64 = re.compile(r'^\s*route-reflector-client$')
                            m = p64.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_route_reflector_client'] = \
                                    True
                                continue
                            elif 'nbr_af_route_reflector_client' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_route_reflector_client'] = \
                                    False

                            #   send-community
                            p65 = re.compile(r'^\s*send-community$')
                            m = p65.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_send_community'] = \
                                    'standard'
                                send_community_standard_match = 'True'
                                continue

                            #   send-community extended
                            p66 = re.compile(r'^\s*send-community +extended$')
                            m = p66.match(line)
                            if m:
                                if send_community_standard_match:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_send_community'] = \
                                        'both'
                                else:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_send_community'] = \
                                        'extended'
                                continue

                            #   route-reflector-client
                            p67 = re.compile(r'^\s*soft-reconfiguration inbound( +(?P<nbr_af_soft_reconfiguration_extra>.*))?$')
                            m = p67.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_soft_reconfiguration'] = \
                                    True
                                continue
                            elif 'nbr_af_soft_reconfiguration' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_soft_reconfiguration'] = \
                                    False

                            #   next-hop-self
                            p68 = re.compile(r'^\s*next-hop-self$')
                            m = p68.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_next_hop_self'] = \
                                    True
                                continue
                            elif 'nbr_af_next_hop_self' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_next_hop_self'] = \
                                    False

                            #   as-override
                            p69 = re.compile(r'^\s*as-override$')
                            m = p69.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_as_override'] = \
                                    True
                                continue
                            elif 'nbr_af_as_override' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_as_override'] = \
                                    False

                            #   default-originate [ route-map <nbr_af_default_originate_route_map> ]
                            p70 = re.compile(r'^\s*default-originate( +route-map +(?P<nbr_af_default_originate_route_map>.*))?$')
                            m = p70.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_default_originate'] = \
                                    True
                                if m.groupdict()['nbr_af_default_originate_route_map']:
                                    bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_default_originate_route_map'] = \
                                        str(m.groupdict()['nbr_af_default_originate_route_map'])
                                continue
                            elif 'nbr_af_default_originate' not in bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_default_originate'] = \
                                    False

                            #   soo <nbr_af_soo>
                            p71 = re.compile(r'^\s*soo +(?P<nbr_af_soo>.*)$')
                            m = p71.match(line)
                            if m:
                                bgp_dict['bgp']['instance']['default']['vrf'][vrf]['neighbor_id'][neighbor_id]['nbr_af_name'][nbr_af_name]['nbr_af_soo'] = \
                                    str(m.groupdict()['nbr_af_soo'])
                                continue

                #   template peer-session PEER-SESSION
                p72 = re.compile(r'^\s*template peer-session +(?P<ps_name>.*)$')
                m = p72.match(line)
                if m:
                    # Get keys
                    ps_name = str(m.groupdict()['ps_name'])
                    if 'ps_name' not in bgp_dict['bgp']:
                        bgp_dict['bgp']['instance']['default']['ps_name'] = {}
                    if ps_name not in bgp_dict['bgp']['instance']['default']['ps_name']:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name] = {}
                    continue

                if ps_name:
                    #   bfd
                    p73 = re.compile(r'^\s*bfd$')
                    m = p73.match(line)
                    if m:
                        # Get keys
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_fall_over_bfd'] = True
                        continue
                    elif 'ps_fall_over_bfd' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_fall_over_bfd'] = False

                    #   capability suppress 4-byte-as
                    p74 = re.compile(r'^\s*bfd$')
                    m = p74.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_suppress_four_byte_as_capability'] = True
                        continue
                    elif 'ps_suppress_four_byte_as_capability' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_suppress_four_byte_as_capability'] = False

                    #   description <ps_description>
                    p75 = re.compile(r'^\s*description +(?P<ps_description>.*)$')
                    m = p75.match(line)
                    if m:
                        # Get keys
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_description'] = \
                            str(m.groupdict()['ps_description'])
                        continue

                    #   disable-connected-check
                    p76 = re.compile(r'^\s*disable-connected-check$')
                    m = p76.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_disable_connected_check'] = True
                        continue
                    elif 'ps_disable_connected_check' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_disable_connected_check'] = False

                    #   ebgp-multihop <ps_ebgp_multihop_max_hop>
                    p77 = re.compile(r'^\s*ebgp-multihop +(?P<ps_ebgp_multihop_max_hop>[0-9]+)$$')
                    m = p77.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_ebgp_multihop'] = True
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_ebgp_multihop_max_hop'] = \
                            int(m.groupdict()['ps_ebgp_multihop_max_hop'])
                        continue
                    elif 'ps_ebgp_multihop' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_ebgp_multihop'] = False

                    #    { local-as <ps_local_as_as_no> [ no-prepend [ replace-as [ dual-as ] ] ] }
                    p78 = re.compile(r'^\s*local-as +(?P<ps_local_as_as_no>[0-9\.]+)( +no-prepend( +replace-as( +dual-as)?)?)?$')
                    m = p78.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_as_no'] = \
                            str(m.groupdict()['ps_local_as_as_no'])
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_no_prepend'] = \
                            True
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_replace_as'] = \
                            True
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_dual_as'] = \
                            True
                        continue
                    elif 'ps_local_as_no_prepend' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_no_prepend'] = \
                            False
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_replace_as'] = \
                            False
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_local_as_dual_as'] = \
                            False

                    #   password <ps_password_text>
                    p79 = re.compile(r'^\s*password +(?P<ps_password_text>.*)$')
                    m = p79.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_password_text'] = \
                            str(m.groupdict()['ps_password_text'])
                        continue

                    #   { remote-as <ps_remote_as> }
                    p80 = re.compile(r'^\s*remote-as +(?P<ps_remote_as>[0-9]+)$')
                    m = p80.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_remote_as'] = \
                            int(m.groupdict()['ps_remote_as'])
                        continue

                    #   shutdown
                    p81 = re.compile(r'^\s*shutdown$')
                    m = p81.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_shutdown'] = \
                            True
                        continue
                    elif 'ps_shutdown' not in bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_shutdown'] = \
                            False

                    #   timers <ps_keepalive_interval> <ps_hodltime>
                    p82 = re.compile(r'^\s*timers +(?P<ps_keepalive_interval>[0-9]+) +(?P<ps_hodltime>[0-9]+)$')
                    m = p82.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_keepalive_interval'] = \
                            int(m.groupdict()['ps_keepalive_interval'])
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_hodltime'] = \
                            int(m.groupdict()['ps_hodltime'])
                        continue

                    #   transport connection-mode <ps_transport_connection_mode>
                    p83 = re.compile(r'^\s*transport connection-mode +(?P<ps_transport_connection_mode>[a-z]+)$')
                    m = p83.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_transport_connection_mode'] = \
                            str(m.groupdict()['ps_transport_connection_mode'])
                        continue

                    #   update-source <ps_update_source>
                    p84 = re.compile(r'^\s*update-source +(?P<ps_update_source>[A-Za-z0-9\/\.]+)$')
                    m = p54.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['ps_name'][ps_name]['ps_update_source'] = \
                            str(m.groupdict()['ps_update_source'])
                        continue

                #   template peer-policy <pp_name>
                p85 = re.compile(r'^\s*template peer-session +(?P<pp_name>.*)$')
                m = p85.match(line)
                if m:
                    # Get keys
                    pp_name = str(m.groupdict()['pp_name'])
                    if 'pp_name' not in bgp_dict['bgp']['instance']['default']:
                        bgp_dict['bgp']['instance']['default']['pp_name'] = {}
                    if pp_name not in bgp_dict['bgp']['instance']['default']['pp_name']:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name] = {}
                    continue

                if pp_name:
                    #   allowas-in [ <allowas-in-cnt> ]
                    p86 = re.compile(r'^\s*allowas-in( +(?P<pp_allowas_in_as_number>[0-9]+))?$')
                    m = p86.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_allowas_in'] = \
                            True
                        if m.groupdict()['pp_allowas_in_as_number']:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_allowas_in_as_number'] = \
                                int(m.groupdict()['pp_allowas_in_as_number'])
                        continue
                    elif 'pp_allowas_in' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_allowas_in'] = \
                            False

                    #   as-override
                    p87 = re.compile(r'^\s*as-override$')
                    m = p87.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_as_override'] = \
                            True
                        continue
                    elif 'pp_as_override' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_as_override'] = \
                            False

                    #   default-originate [ route-map <pp_default_originate_route_map> ]
                    p88 = re.compile(r'^\s*default-originate( +route-map +(?P<pp_default_originate_route_map>.*))?$')
                    m = p88.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_default_originate'] = \
                            True
                        if m.groupdict()['pp_default_originate_route_map']:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_default_originate_route_map'] = \
                                str(m.groupdict()['pp_default_originate_route_map'])
                        continue
                    elif 'pp_default_originate' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_default_originate'] = \
                            False

                    #   route-map <pp_route_map_name_in> in
                    p89 = re.compile(r'^\s*route-map +(?P<pp_route_map_name_in>.*) in$')
                    m = p89.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_route_map_name_in'] = \
                            str(m.groupdict()['pp_route_map_name_in'])
                        continue

                    #   route-map <nbr_af_route_map_name_out> out
                    p90 = re.compile(r'^\s*route-map +(?P<pp_route_map_name_out>.*) out$')
                    m = p90.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_route_map_name_out'] = \
                            str(m.groupdict()['pp_route_map_name_out'])
                        continue

                    #    maximum-prefix <pp_maximum_prefix_max_prefix_no> [ <pp_maximum_prefix_threshold> ] [ restart <pp_maximum_prefix_restart> ]
                    p91 = re.compile(r'^\s*maximum-prefix +(?P<pp_maximum_prefix_max_prefix_no>[0-9]+)( +(?P<nbr_af_maximum_prefix_threshold>[0-9]+))?(restart +(?P<nbr_af_maximum_prefix_restart>[0-9]+))?$')
                    m = p91.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_max_prefix_no'] = \
                            int(m.groupdict()['pp_maximum_prefix_max_prefix_no'])
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_threshold'] = \
                            int(m.groupdict()['pp_maximum_prefix_threshold'])
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_restart'] = \
                            int(m.groupdict()['pp_maximum_prefix_restart'])
                        continue

                    #   maximum-prefix <pp_maximum_prefix_max_prefix_no> [ <pp_maximum_prefix_threshold> ] [ warning-only ]
                    p92 = re.compile(r'^\s*maximum-prefix +(?P<pp_maximum_prefix_max_prefix_no>[0-9]+)( +(?P<pp_maximum_prefix_threshold>[0-9]+))?( +(?P<pp_maximum_prefix_warning_only>warning-only))?$')
                    m = p92.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_max_prefix_no'] = \
                            int(m.groupdict()['pp_maximum_prefix_max_prefix_no'])
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_threshold'] = \
                            int(m.groupdict()['pp_maximum_prefix_threshold'])
                        if m.groupdict()['pp_maximum_prefix_warning_only']:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_warning_only'] = \
                                True
                        else:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_maximum_prefix_warning_only'] = \
                                False
                        continue

                    #   next-hop-self
                    p93 = re.compile(r'^\s*next-hop-self$')
                    m = p93.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_next_hop_self'] = \
                            True
                        continue
                    elif 'pp_next_hop_self' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_next_hop_self'] = \
                            False

                    #   route-reflector-client
                    p94 = re.compile(r'^\s*route-reflector-client$')
                    m = p94.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_route_reflector_client'] = \
                            True
                        continue
                    elif 'pp_route_reflector_client' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_route_reflector_client'] = \
                            False

                    #   send-community
                    p95 = re.compile(r'^\s*send-community$')
                    m = p95.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_send_community'] = \
                            'standard'
                        peer_policy_send_community_standard_match = 'True'
                        continue

                    #   send-community extended
                    p96 = re.compile(r'^\s*send-community +extended$')
                    m = p96.match(line)
                    if m:
                        if peer_policy_send_community_standard_match:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_send_community'] = \
                                'both'
                        else:
                            bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_send_community'] = \
                                'extended'
                        continue

                    #   route-reflector-client
                    p97 = re.compile(r'^\s*soft-reconfiguration inbound( +(?P<nbr_af_soft_reconfiguration_extra>.*))?$')
                    m = p97.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_soft_reconfiguration'] = \
                            True
                        continue
                    elif 'pp_soft_reconfiguration' not in bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_soft_reconfiguration'] = \
                            False

                    #   soo <pp_soo>
                    p98 = re.compile(r'^\s*soo +(?P<pp_soo>.*)$')
                    m = p98.match(line)
                    if m:
                        bgp_dict['bgp']['instance']['default']['pp_name'][pp_name]['pp_soo'] = \
                            str(m.groupdict()['pp_soo'])
                        continue

        return bgp_dict


# ===================================================
# Schema for 'show bgp all dampening flap-statistics'
# ===================================================
class ShowBgpAllDampeningFlapStatisticsSchema(MetaParser):
    """Schema for show bgp all dampening flap-statistics"""

    schema = {
        'vrf': {
            Any(): {
                'address_family': {
                    Any(): {
                        Optional('network'): {
                            Any(): {
                                'peer': str,
                                'flaps': int,
                                'duration': str,
                                'current_penalty': int,
                                'suppress_limit': int,
                                'reuse_limit': int,
                                'best': bool,
                                Optional('status'): str,
                                Optional('reuse_time'): str,
                                Optional('pathtype'): str,
                            },
                        },
                        Optional('history_paths'): int,
                        Optional('dampened_paths'): int,
                        Optional('dampening_enabled'): bool,
                        Optional('route_identifier'): {
                            Any(): {
                                Optional('network'): {
                                    Any(): {
                                        'peer': str,
                                        'flaps': int,
                                        'duration': str,
                                        Optional('reuse_time'): str,
                                        'current_penalty': int,
                                        'suppress_limit': int,
                                        'reuse_limit': int,
                                        'best': bool,
                                        Optional('status'): str,
                                        Optional('pathtype'): str,
                                    },
                                },
                                'history_paths': int,
                                'dampened_paths': int,
                                'dampening_enabled': bool,
                            },
                        }
                    },                            
                },
            },
        }
    }

# ===================================================
# Parser for 'show bgp all dampening flap-statistics'
# ===================================================
class ShowBgpAllDampeningFlapStatistics(ShowBgpAllDampeningFlapStatisticsSchema):
    """Parser for:
        show bgp all dampening flap-statistics
        parser class implements detail parsing mechanisms for cli,xml output."""

    def cli(self):
        cmd = 'show bgp all dampening flap-statistics'
        out = self.device.execute(cmd)
        
        # Init vars
        ret_dict = {}
        sub_dict = {}
        history_paths = None
        dampened_paths = None

        for line in out.splitlines():
            line = line.strip()

            # build keys for dampened_paths and history_paths
            if isinstance(dampened_paths, int):
                sub_dict['dampened_paths'] = dampened_paths
                sub_dict['dampening_enabled'] = True
                
            if isinstance(history_paths, int):
                sub_dict['history_paths'] = history_paths

            # Flap Statistics for VRF default, address family IPv4 Unicast:
            p1 = re.compile(r'^Flap +Statistics +for +VRF +'
                             '(?P<vrf_name>[\w\-]+), +address +family +'
                             '(?P<address_family>[\w\s\-]+):$')
            m = p1.match(line)
            if m:
                address_family = m.groupdict()['address_family'].lower()
                vrf = m.groupdict()['vrf_name']

                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}

                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}

                if 'address_family' not in ret_dict['vrf'][vrf]:
                    ret_dict['vrf'][vrf]['address_family'] = {}

                if address_family not in ret_dict['vrf'][vrf]['address_family']:
                    ret_dict['vrf'][vrf]['address_family'][address_family] = {}
                    sub_dict = ret_dict['vrf'][vrf]['address_family'][address_family]
                        
                # reset variable
                dampened_paths = None
                history_paths = None
                continue

            # Dampening configured, 0 history paths, 2 dampened paths
            p2 = re.compile(r'^Dampening +configured, +'
                             '(?P<history_paths>\d+) +history +paths, +'
                             '(?P<dampened_paths>\d+) +dampened +paths$')
            m = p2.match(line)
            if m:
                history_paths = int(m.groupdict()['history_paths'])
                dampened_paths = int(m.groupdict()['dampened_paths'])
                continue

            # Route Distinguisher: 0:0
            p3 = re.compile(r'^Route +Distinguisher: +'
                             '(?P<route_identifier>[\w\.\:]+)$')
            m = p3.match(line)
            if m:
                route_identifier = m.groupdict()['route_identifier']
                if 'route_identifier' not in ret_dict['vrf'][vrf]\
                    ['address_family'][address_family]:
                    ret_dict['vrf'][vrf]['address_family'][address_family]\
                        ['route_identifier'] = {}

                if route_identifier not in ret_dict['vrf'][vrf]\
                    ['address_family'][address_family]['route_identifier']:
                    ret_dict['vrf'][vrf]['address_family'][address_family]\
                        ['route_identifier'][route_identifier] = {}

                    sub_dict = ret_dict['vrf'][vrf]['address_family'][address_family]\
                        ['route_identifier'][route_identifier]
                continue

            # d e 2.3.1.0/24       19.0.102.3                38   00:09:36 00:01:40 35/30/10
            p4 = re.compile(r'^(?P<best>[\*])?(?P<status>\w+)'
                             ' +(?P<pathtype>[e|i])'
                             ' +(?P<network>\S+)'
                             ' +(?P<peer>[\w\/\.\:]+)'
                             ' +(?P<flaps>\d+)'
                             ' +(?P<duration>[\w\:\.]+)'
                             '( +(?P<reuse_time>[\w\:\.]+))?'
                             ' +(?P<current_penalty>\d+)\/'
                             '(?P<suppress_limit>\d+)\/(?P<reuse_limit>\d+)$')
            m = p4.match(line)

            # d e [2]:[77][7,0][39.39.39.39,2,656877351][39.1.1.1,22][19.0.102.3,39.0.1.31]/61619.0.102.3                38   00:09:36 00:01:40 34/30/10
            p4_1 = re.compile(r'^(?P<best>[\*])?(?P<status>\w+)'
                             ' +(?P<pathtype>[e|i])'
                             ' +(?P<network>\S+\/\d{1,3})'
                             '(?P<peer>[1|2][\d\.\:]+)'
                             ' +(?P<flaps>\d+)'
                             ' +(?P<duration>[\w\:\.]+)'
                             '( +(?P<reuse_time>[\w\:\.]+))?'
                             ' +(?P<current_penalty>\d+)\/'
                             '(?P<suppress_limit>\d+)\/(?P<reuse_limit>\d+)$')
            m1 = p4_1.match(line)
            m = m if m else m1
            if m:
                network = m.groupdict()['network']
                if 'network' not in sub_dict:
                    sub_dict['network'] = {}
                if network not in sub_dict['network']:
                    sub_dict['network'][network] = {}

                if m.groupdict()['best']:
                    sub_dict['network'][network]['best'] = True
                else:
                    sub_dict['network'][network]['best'] = False
                sub_dict['network'][network]['status'] = m.groupdict()['status']
                sub_dict['network'][network]['pathtype'] = m.groupdict()['pathtype']
                sub_dict['network'][network]['peer'] = m.groupdict()['peer']
                sub_dict['network'][network]['flaps'] = int(m.groupdict()['flaps'])
                sub_dict['network'][network]['duration'] = m.groupdict()['duration']
                if m.groupdict()['reuse_time']:
                    sub_dict['network'][network]['reuse_time'] = m.groupdict()['reuse_time']
                sub_dict['network'][network]['current_penalty'] = \
                    int(m.groupdict()['current_penalty'])
                sub_dict['network'][network]['suppress_limit'] = \
                    int(m.groupdict()['suppress_limit'])
                sub_dict['network'][network]['reuse_limit'] = \
                    int(m.groupdict()['reuse_limit'])
                continue
        return ret_dict


    def xml(self):
        out = self.device.execute('show bgp all dampening flap-statistics | xml')

        etree_dict = {}
        sub_dict = {}
        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                expect_command='show bgp all dampening flap-statistics')

        # top table root
        vrf_root = Common.retrieve_xml_child(root=root, key='TABLE_vrf')
        if not vrf_root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in vrf_root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-out'.format(namespace)).text
            except:
                break

            # address_family table
            afi = vrf_tree.find('{}TABLE_afi'.format(namespace))

            # -----   loop address_family  -----
            for af_root in afi.findall('{}ROW_afi'.format(namespace)):

                # address_family
                row_safi = af_root.find('{}TABLE_safi'.format(namespace))
                row_safi = row_safi.find('{}ROW_safi'.format(namespace))

                try:
                    af = row_safi.find('{}af-name'.format(namespace)).text.lower()
                except:
                    continue

                # rd table
                rd = row_safi.find('{}TABLE_rd'.format(namespace))
                if not rd:
                    continue
                else:
                    if 'vrf' not in etree_dict:
                        etree_dict['vrf'] = {}
                    if vrf not in etree_dict['vrf']:
                        etree_dict['vrf'][vrf] = {}

                    if 'address_family' not in etree_dict['vrf'][vrf]:
                        etree_dict['vrf'][vrf]['address_family'] = {}
                    if af not in etree_dict['vrf'][vrf]['address_family']:
                        etree_dict['vrf'][vrf]['address_family'][af] = {}

                # -----   loop rd  -----
                for rd_root in rd.findall('{}ROW_rd'.format(namespace)):
                    # rd
                    try:
                        rd = rd_root.find('{}rd_val'.format(namespace)).text
                    except:
                        rd = None

                    # <dampeningenabled>true</dampeningenabled>
                    try:
                        dampeningenabled = rd_root.find('{}dampeningenabled'
                                                        .format(namespace)).text
                    except:
                        # <dampening>true</dampening>
                        try:
                            dampeningenabled = rd_root.find('{}dampening'
                                                            .format(namespace)).text
                        except:
                            pass
                            
                    # <historypaths>0</historypaths>
                    historypaths = int(rd_root.find('{}historypaths'
                                                    .format(namespace)).text)
                    # <dampenedpaths>2</dampenedpaths>
                    dampenedpaths = int(rd_root.find('{}dampenedpaths'
                                                     .format(namespace)).text)

                    if rd:
                        # set default attributes under address family 
                        # <dampeningenabled>true</dampeningenabled>
                        if dampeningenabled == 'true':
                            etree_dict['vrf'][vrf]['address_family'][af]['dampening_enabled'] = True

                        # <historypaths>0</historypaths>
                        etree_dict['vrf'][vrf]['address_family'][af]['history_paths'] = historypaths
                        
                        # <dampenedpaths>2</dampenedpaths>
                        etree_dict['vrf'][vrf]['address_family'][af]['dampened_paths'] = dampenedpaths

                        if 'route_identifier' not in etree_dict['vrf'][vrf]\
                            ['address_family'][af]:
                            etree_dict['vrf'][vrf]['address_family'][af]\
                                ['route_identifier'] = {}

                        if rd not in etree_dict['vrf'][vrf]\
                            ['address_family'][af]['route_identifier']:
                            etree_dict['vrf'][vrf]['address_family'][af]\
                                ['route_identifier'][rd] = {}

                        sub_dict = etree_dict['vrf'][vrf]['address_family'][af]\
                            ['route_identifier'][rd]
                    else:
                        sub_dict = etree_dict['vrf'][vrf]['address_family'][af]

                    # <dampeningenabled>true</dampeningenabled>
                    if dampeningenabled == 'true':
                        sub_dict['dampening_enabled'] = True

                    # <historypaths>0</historypaths>
                    sub_dict['history_paths'] = historypaths

                    # <dampenedpaths>2</dampenedpaths>
                    sub_dict['dampened_paths'] = dampenedpaths

                    # prefix table
                    prefix = rd_root.find('{}TABLE_prefix'.format(namespace))
                    if not prefix:
                        continue

                    # -----   loop prefix  -----
                    for prefix_root in prefix.findall('{}ROW_prefix'.format(namespace)):

                        # <ipprefix>2.3.1.0/24</ipprefix>
                        try:
                            network = prefix_root.find('{}ipprefix'.format(namespace)).text
                        except:
                            pass

                        # ipv6prefix>2001::/112</ipv6prefix>
                        try:
                            network = prefix_root.find('{}ipv6prefix'.format(namespace)).text
                        except:
                            pass

                        # <nonipprefix>[2]:[0]:[0]:[48]:[0201.0201.0201]:[32]:[2.7.1.1]/248</nonipprefix>
                        try:
                            network = prefix_root.find('{}nonipprefix'.format(namespace)).text
                        except:
                            pass
                           
                        if 'network' not in sub_dict:
                            sub_dict['network'] = {}

                        if network not in sub_dict['network']:
                            sub_dict['network'][network] = {}

                        # <status>d</status>
                        sub_dict['network'][network]['status'] = \
                            prefix_root.find('{}status'.format(namespace)).text

                        # <pathtype>e</pathtype>
                        sub_dict['network'][network]['pathtype'] = \
                            prefix_root.find('{}pathtype'.format(namespace)).text

                        # <peer>19.0.102.3</peer>
                        try:
                            sub_dict['network'][network]['peer'] = \
                                prefix_root.find('{}peer'.format(namespace)).text
                        except:
                            pass

                        # <ipv6peer>fec0::2002</ipv6peer>
                        try:
                            sub_dict['network'][network]['peer'] = \
                                prefix_root.find('{}ipv6peer'.format(namespace)).text
                        except:
                            pass

                        # <flapcount>39</flapcount>
                        sub_dict['network'][network]['flaps'] = \
                            int(prefix_root.find('{}flapcount'.format(namespace)).text)
                            
                        # <duration>00:09:53</duration>
                        sub_dict['network'][network]['duration'] = \
                            prefix_root.find('{}duration'.format(namespace)).text
                            
                        # <reuse>00:01:40</reuse>
                        reuse = prefix_root.find('{}reuse'.format(namespace)).text
                        if reuse:
                            sub_dict['network'][network]['reuse_time'] = reuse
                            
                            
                        # <penalty>34</penalty>
                        penalty = prefix_root.find('{}penalty'.format(namespace)).text
                        if penalty:
                            sub_dict['network'][network]['current_penalty'] = int(penalty)
                            
                        # <suppresslimit>30</suppresslimit>
                        sub_dict['network'][network]['suppress_limit'] = \
                            int(prefix_root.find('{}suppresslimit'.format(namespace)).text)

                       # <reuselimit>10</reuselimit>
                        sub_dict['network'][network]['reuse_limit'] = \
                            int(prefix_root.find('{}reuselimit'.format(namespace)).text)

                       # <best>false</best>
                        if prefix_root.find('{}best'.format(namespace)).text == 'false':
                            sub_dict['network'][network]['best'] = False
                        else:
                            sub_dict['network'][network]['best'] = True                                                                                    
        return etree_dict


# ==========================================
# Parser for 'show bgp all nexthop-database'
# ==========================================
class ShowBgpAllNexthopDatabase(ShowBgpVrfAllAllNextHopDatabase):
    """Parser for:
        show bgp all nexthop-database
        parser class implements detail parsing mechanisms for cli,xml output."""

    def cli(self):
        cmd = 'show bgp all nexthop-database'
        return super().cli(cmd)


    def xml(self):
        out = self.device.execute('show bgp all nexthop-database | xml')

        etree_dict = {}
        sub_dict = {}
        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                expect_command='show bgp all nexthop-database')

        # top table root
        vrf_root = Common.retrieve_xml_child(root=root, key='TABLE_nhvrf')
        if not vrf_root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in vrf_root.findall('{}ROW_nhvrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}nhvrf-name-out'.format(namespace)).text
            except:
                break

            if 'vrf' not in etree_dict:
                etree_dict['vrf'] = {}
            if vrf not in etree_dict['vrf']:
                etree_dict['vrf'][vrf] = {}

            # address_family table
            afi = vrf_tree.find('{}TABLE_nhafi'.format(namespace))

            # -----   loop address_family  -----
            for af_root in afi.findall('{}ROW_nhafi'.format(namespace)):

                # address_family
                row_safi = af_root.find('{}TABLE_nhsafi'.format(namespace))
                af_root = row_safi.find('{}ROW_nhsafi'.format(namespace))
                try:
                    af = af_root.find('{}af-name'.format(namespace)).text.lower()
                except:
                    continue

                if 'address_family' not in etree_dict['vrf'][vrf]:
                    etree_dict['vrf'][vrf]['address_family'] = {}
                if af not in etree_dict['vrf'][vrf]['address_family']:
                    etree_dict['vrf'][vrf]['address_family'][af] = {}

                # af_nexthop_trigger_enable
                etree_dict['vrf'][vrf]['address_family'][af]\
                    ['af_nexthop_trigger_enable'] = True

                # <nhnoncriticaldelay>10000</nhnoncriticaldelay>
                etree_dict['vrf'][vrf]['address_family'][af]\
                    ['nexthop_trigger_delay_non_critical'] = int(af_root.find('{}nhnoncriticaldelay'
                                                             .format(namespace)).text)
                # <nhcriticaldelay>3000</nhcriticaldelay>
                etree_dict['vrf'][vrf]['address_family'][af]\
                    ['nexthop_trigger_delay_critical'] = int(af_root.find('{}nhcriticaldelay'
                                                             .format(namespace)).text)

                # nexthop table
                next_hop = af_root.find('{}TABLE_nexthop'.format(namespace))
                if not next_hop:
                    continue

                # -----   loop nexthop  -----
                for nexthop_root in next_hop.findall('{}ROW_nexthop'.format(namespace)):
                    # nexthop
                    # <ipnexthop-out>200.0.3.1</ipnexthop-out>
                    try:
                        nexthop = nexthop_root.find('{}ipnexthop-out'.format(namespace)).text
                    except:
                        pass

                    # <ipv6nexthop-out>2000::3:1</ipv6nexthop-out>
                    try:
                        nexthop = nexthop_root.find('{}ipv6nexthop-out'.format(namespace)).text
                    except:
                        pass

                    if 'next_hop' not in etree_dict['vrf'][vrf]\
                        ['address_family'][af]:
                        etree_dict['vrf'][vrf]['address_family'][af]\
                            ['next_hop'] = {}

                    if nexthop not in etree_dict['vrf'][vrf]\
                        ['address_family'][af]['next_hop']:
                        etree_dict['vrf'][vrf]['address_family'][af]\
                            ['next_hop'][nexthop] = {}

                    sub_dict = etree_dict['vrf'][vrf]['address_family'][af]\
                        ['next_hop'][nexthop]

                    # <refcount>1</refcount>
                    sub_dict['refcount'] = int(nexthop_root.find(
                                                '{}refcount'.format(namespace)).text)

                    # <igpmetric>3</igpmetric>
                    sub_dict['igp_cost'] = \
                        int(nexthop_root.find('{}igpmetric'.format(namespace)).text)

                    # <igptype>0</igptype>
                    sub_dict['igp_route_type'] = \
                        int(nexthop_root.find('{}igptype'.format(namespace)).text)

                    # <igppref>110</igppref>
                    sub_dict['igp_preference'] = \
                        int(nexthop_root.find('{}igppref'.format(namespace)).text)

                    # <attached>false</attached>
                    if nexthop_root.find('{}attached'.format(namespace)).text == 'false':
                        sub_dict['attached'] = False
                    else:
                        sub_dict['attached'] = True


                    # <local>false</local>
                    if nexthop_root.find('{}local'.format(namespace)).text == 'false':
                        sub_dict['local'] = False
                    else:
                        sub_dict['local'] = True

                    # <reachable>true</reachable>
                    if nexthop_root.find('{}reachable'.format(namespace)).text == 'false':
                        sub_dict['reachable'] = False
                    else:
                        sub_dict['reachable'] = True

                    # <labeled>true</labeled>
                    if nexthop_root.find('{}labeled'.format(namespace)).text == 'false':
                        sub_dict['labeled'] = False
                    else:
                        sub_dict['labeled'] = True

                    # <filtered>false</filtered>
                    if nexthop_root.find('{}filtered'.format(namespace)).text == 'false':
                        sub_dict['filtered'] = False
                    else:
                        sub_dict['filtered'] = True

                    # <pendingupdate>false</pendingupdate>
                    if nexthop_root.find('{}pendingupdate'.format(namespace)).text == 'false':
                        sub_dict['pending_update'] = False
                    else:
                        sub_dict['pending_update'] = True

                    # <resolvetime>18:38:21</resolvetime>
                    sub_dict['resolve_time'] = \
                        nexthop_root.find('{}resolvetime'.format(namespace)).text

                    # <ribroute>200.0.3.1/32</ribroute>
                    try:
                        sub_dict['rib_route'] = \
                            nexthop_root.find('{}ribroute'.format(namespace)).text
                    except:
                        pass                    

                    # <ipv6ribroute>0::/0</ipv6ribroute>
                    try:
                        sub_dict['rib_route'] = \
                            nexthop_root.find('{}ipv6ribroute'.format(namespace)).text
                    except:
                        pass

                    # <nextadvertise>Never</nextadvertise>
                    sub_dict['metric_next_advertise'] = \
                        nexthop_root.find('{}nextadvertise'.format(namespace)).text.lower()

                    # <rnhepoch>1</rnhepoch>
                    sub_dict['rnh_epoch'] = \
                        int(nexthop_root.find('{}rnhepoch'.format(namespace)).text)


                    # attachedhops table
                    attached = nexthop_root.find('{}TABLE_attachedhops'.format(namespace))
                    if not attached:
                        continue

                    # -----   loop attachedhops  -----
                    for attach_root in attached.findall('{}ROW_attachedhops'.format(namespace)):

                        # <attachedhop>201.7.23.2</attachedhop>
                        try:
                            att_hop = attach_root.find('{}attachedhop'.format(namespace)).text
                        except:
                            pass

                        # <ipv6attachedhop>fe80::6e9c:edff:fe4d:ff41</ipv6attachedhop>
                        try:
                            att_hop = attach_root.find('{}ipv6attachedhop'.format(namespace)).text
                        except:
                            pass
                           
                        if 'attached_nexthop' not in sub_dict:
                            sub_dict['attached_nexthop'] = {}

                        if att_hop not in sub_dict['attached_nexthop']:
                            sub_dict['attached_nexthop'][att_hop] = {}

                        # <interface>port-channel2.100</interface>
                        sub_dict['attached_nexthop'][att_hop]['attached_nexthop_interface'] = \
                            attach_root.find('{}interface'.format(namespace)).text                                                                                                          
        return etree_dict


# ===================================
# Schema for 'show bgp peer-template'
# ===================================
class ShowBgpPeerTemplateCmdSchema(MetaParser):
    """Schema for show bgp peer-template"""

    schema = {
        'template': {
            Any(): {
                Optional('source_interface'): str,
                Optional('low_mem_exempt'): bool,
                Optional('logging_neighbor_events'): bool,
                Optional('external_bgp_peer_hops_limit'): int,
                Optional('passive_only'): bool,
                Optional('local_as_inactive'): bool,
                Optional('remove_private_as'): bool,
                Optional('vrf'): {
                    Any(): {
                        'inheriting_peer': {
                            Any(): {
                                'inheriting_peer': str,
                            },
                        }
                    },
                },
                'address_family': {
                    Any(): {
                        Optional('condition_map'): str,
                        Optional('advertise_map'): str,
                        Optional('advertise_map_status'): str,
                        Optional('in_soft_reconfig_allowed'): bool,
                        Optional('send_community'): bool,
                        Optional('send_ext_community'): bool,
                        Optional('local_nexthop'): str,
                        Optional('third_party_nexthop'): bool,
                        Optional('max_pfx'): int,
                        Optional('soo'): str,
                        Optional('weight'): int,
                        Optional('allow_as_in'): int,
                        Optional('as_override'): bool,
                        Optional('peer_as_check_disabled'): bool,
                        Optional('rr_configured'): bool,
                        Optional('default_originate'): bool,
                        Optional('default_originate_route_map'): str,
                        Optional('unsuppress_map'): str,
                        Optional('in_policy'): {
                            Any(): {
                                'type': str,
                                'name': str,
                            },
                        },
                        Optional('out_policy'): {
                            Any(): {
                                'type': str,
                                'name': str,
                            },
                        },                        
                    },                            
                },
            },
        }
    }

# ===================================
# Parser for 'show bgp peer-template'
# ===================================
class ShowBgpPeerTemplateCmd(ShowBgpPeerTemplateCmdSchema):
    """Parser for:
        show bgp peer-template
    parser class implements detail parsing mechanisms for cli,xml output."""

    def cli(self):
        cmd = 'show bgp peer-template'
        out = self.device.execute(cmd)
        
        # Init vars
        ret_dict = {}
        sub_dict = {}
        tem_peer = None

        for line in out.splitlines():
            line = line.strip()

            # BGP peer-template is PEER2
            p1 = re.compile(r'^BGP +peer\-template +is +'
                             '(?P<template>[\w\-]+)$')
            m = p1.match(line)
            if m:
                template = m.groupdict()['template']

                if 'template' not in ret_dict:
                    ret_dict['template'] = {}

                if template not in ret_dict['template']:
                    ret_dict['template'][template] = {}

                # will enable regext when there is output
                # initial the flag due to comparison with xml version
                ret_dict['template'][template]['local_as_inactive'] = False
                ret_dict['template'][template]['remove_private_as'] = False
                ret_dict['template'][template]['logging_neighbor_events'] = False
                ret_dict['template'][template]['passive_only'] = False
                continue

            # Using loopback1 as update source for this peer
            p2 = re.compile(r'^Using +(?P<intf>[\w\-\/\.]+) +as'
                             ' +update +source +for +this +peer$')
            m = p2.match(line)
            if m:
                ret_dict['template'][template]['source_interface'] = \
                    m.groupdict()['intf']
                continue

            # Peer is low-memory exempt
            p3 = re.compile(r'^Peer +is +low\-memory +exempt$')
            m = p3.match(line)
            if m:
                ret_dict['template'][template]['low_mem_exempt'] = True
                continue

            # Disable logging neighbor events
            p4 = re.compile(r'^Disable +logging +neighbor +events$')
            m = p4.match(line)
            if m:
                ret_dict['template'][template]['logging_neighbor_events'] = False
                continue

            # External BGP peer might be up to 100 hops away
            p5 = re.compile(r'^External +BGP +peer +might +be +up +to'
                             ' +(?P<hops>\d+) +hops +away$')
            m = p5.match(line)
            if m:
                ret_dict['template'][template]['external_bgp_peer_hops_limit'] = \
                    int(m.groupdict()['hops'])
                continue

            # Only passive connection setup allowed
            p6 = re.compile(r'^Only +passive +connection +setup +allowed$')
            m = p6.match(line)
            if m:
                ret_dict['template'][template]['passive_only'] = True
                continue

            # Neighbor local-as command not active
            p23 = re.compile(r'^Neighbor +local\-as +command +not +active$')
            m = p23.match(line)
            if m:
                ret_dict['template'][template]['local_as_inactive'] = True
                continue

            # For address family: IPv4 Unicast
            p7 = re.compile(r'^For +address +family: +(?P<af>[\w\s\-]+)$')
            m = p7.match(line)
            if m:
                af = m.groupdict()['af'].lower()

                if 'address_family' not in ret_dict['template'][template]:
                    ret_dict['template'][template]['address_family'] = {}

                if af not in ret_dict['template'][template]['address_family']:
                    ret_dict['template'][template]['address_family'][af] = {}

                sub_dict = ret_dict['template'][template]['address_family'][af]

                # will enable regext when there is output
                # initial the flag due to comparison with xml version
                sub_dict['in_soft_reconfig_allowed'] = False
                sub_dict['rr_configured'] = False
                sub_dict['peer_as_check_disabled'] = False
                sub_dict['as_override'] = False
                sub_dict['default_originate'] = False
                continue

            # Condition-map DENY_ALL_RM, Advertise-map BLOCK-ALL, Status Advertise
            p8 = re.compile(r'^Condition\-map +(?P<con_map>[\w\-]+), +'
                             'Advertise\-map +(?P<adv_map>[\w\-]+), +'
                             'Status +(?P<status>[\w\-]+)$')
            m = p8.match(line)
            if m:
                sub_dict['condition_map'] = m.groupdict()['con_map']
                sub_dict['advertise_map'] = m.groupdict()['adv_map']
                sub_dict['advertise_map_status'] = m.groupdict()['status'].lower()
                continue

            # Inbound soft reconfiguration allowed(always)
            p25 = re.compile(r'^Inbound +soft +reconfiguration +allowed\(always\)$')
            m = p25.match(line)
            if m:
                sub_dict['in_soft_reconfig_allowed'] = True
                continue

            # Community attribute sent to this neighbor
            p9 = re.compile(r'^Community +attribute +sent +to +this +neighbor$')
            m = p9.match(line)
            if m:
                sub_dict['send_community'] = True
                continue

            # Extended community attribute sent to this neighbor
            p10 = re.compile(r'^Extended +community +attribute +sent +'
                              'to +this +neighbor$')
            m = p10.match(line)
            if m:
                sub_dict['send_ext_community'] = True
                continue

            # Nexthop always set to local peering address, 0.0.0.0
            p11 = re.compile(r'^Nexthop +always +set +to +local +'
                              'peering +address, +(?P<local_nexthop>[\w\.\:]+)$')
            m = p11.match(line)
            if m:
                sub_dict['local_nexthop'] = m.groupdict()['local_nexthop']
                continue

            # Third-party Nexthop will not be computed.
            # will enhance this when output for third_party_nexthop is enabled
            p12 = re.compile(r'^Third\-party +Nexthop +will +not +be +computed.$')
            m = p12.match(line)
            if m:
                sub_dict['third_party_nexthop'] = False
                continue

            # Maximum prefixes allowed 888888888
            p13 = re.compile(r'^Maximum +prefixes +allowed +(?P<max_pfx>\d+)$')
            m = p13.match(line)
            if m:
                sub_dict['max_pfx'] = int(m.groupdict()['max_pfx'])
                continue

            # SOO Extcommunity: SOO:1.1.1.1:100
            p14 = re.compile(r'^SOO +Extcommunity: +(?P<soo>[\w\:\.]+)$')
            m = p14.match(line)
            if m:
                sub_dict['soo'] = m.groupdict()['soo']
                continue

            # Weight: 9999
            p15 = re.compile(r'^Weight: +(?P<weight>\d+)$')
            m = p15.match(line)
            if m:
                sub_dict['weight'] = int(m.groupdict()['weight'])
                continue

            # Allow my ASN 10 times
            p16 = re.compile(r'^Allow +my +ASN +(?P<asn>\d+) +times$')
            m = p16.match(line)
            if m:
                sub_dict['allow_as_in'] = int(m.groupdict()['asn'])
                continue

            # ASN override is enabled
            p17 = re.compile(r'^ASN +override +is +(?P<status>\w+)$')
            m = p17.match(line)
            if m:
                if m.groupdict()['status'] == 'enabled':
                    sub_dict['as_override'] = True
                else:
                    sub_dict['as_override'] = False
                continue

            # Peer ASN check is disabled
            p24 = re.compile(r'^Peer +ASN +check +is +disabled$')
            m = p24.match(line)
            if m:
                sub_dict['peer_as_check_disabled'] = True
                continue

            # Inbound ip prefix-list configured is LIST123
            # Inbound route-map configured is PERMIT_ROUTE_IPV4_RM
            p18 = re.compile(r'^Inbound +(?P<type>[\w\-\s]+) +configured'
                              ' +is +(?P<name>[\w\-]+)$')
            m = p18.match(line)
            if m:
                name = m.groupdict()['name']
                policy_type = m.groupdict()['type']

                if 'in_policy' not in sub_dict:
                    sub_dict['in_policy'] = {}

                if name not in sub_dict['in_policy']:
                    sub_dict['in_policy'][name] = {}

                sub_dict['in_policy'][name]['name'] = name
                sub_dict['in_policy'][name]['type'] = policy_type
                continue

            # Outbound ip prefix-list configured is LIST456
            # Outbound route-map configured is PERMIT_IPV6_RM
            p19 = re.compile(r'^Outbound +(?P<type>[\w\-\s]+) +configured'
                              ' +is +(?P<name>[\w\-]+)$')
            m = p19.match(line)
            if m:
                name = m.groupdict()['name']
                policy_type = m.groupdict()['type']

                if 'out_policy' not in sub_dict:
                    sub_dict['out_policy'] = {}

                if name not in sub_dict['out_policy']:
                    sub_dict['out_policy'][name] = {}

                sub_dict['out_policy'][name]['name'] = name
                sub_dict['out_policy'][name]['type'] = policy_type
                continue

            # Default information originate, route-map PASS-ALL  Last End-of-RIB sent 0.000000 after session start
            # Default information originate  Last End-of-RIB sent 0.000000 after session start
            p20 = re.compile(r'^Default +information +originate(, +'
                              'route-map +(?P<map>[\w\-]+))? +(?P<dummy>.*)$')
            m = p20.match(line)
            if m:
                sub_dict['default_originate'] = True
                if m.groupdict()['map']:
                    sub_dict['default_originate_route_map'] = m.groupdict()['map']
                continue

            # First convergence 0.000000 after session start with 0 routes sent

            # Unsuppress-map ORIGINATE_IPV6 configured
            p21 = re.compile(r'^Unsuppress\-map +(?P<map>[\w\-]+) +configured$')
            m = p21.match(line)
            if m:
                sub_dict['unsuppress_map'] = m.groupdict()['map']
                continue

            # Members of peer-template PEER1:
            # default: 21.0.201.1
            p22 = re.compile(r'^Members +of +peer\-template +(?P<peer>[\w\-]+):$')
            m = p22.match(line)
            if m:
                tem_peer = m.groupdict()['peer']
                continue

            p22_1 = re.compile(r'^(?P<vrf>[\w\-]+): +(?P<neighbor>[\w\:\.]+)$')
            m = p22_1.match(line)
            if m and tem_peer:
                if 'vrf' not in ret_dict['template'][tem_peer]:
                    ret_dict['template'][tem_peer]['vrf'] = {}

                vrf = m.groupdict()['vrf']

                if vrf not in ret_dict['template'][tem_peer]['vrf']:
                    ret_dict['template'][tem_peer]['vrf'][vrf] = {}

                if 'inheriting_peer' not in ret_dict['template'][tem_peer]['vrf'][vrf]:
                    ret_dict['template'][tem_peer]['vrf'][vrf]['inheriting_peer'] = {}

                nei = m.groupdict()['neighbor']

                if nei not in ret_dict['template'][tem_peer]['vrf'][vrf]['inheriting_peer']:
                    ret_dict['template'][tem_peer]['vrf'][vrf]['inheriting_peer'][nei] = {}

                ret_dict['template'][tem_peer]['vrf'][vrf]['inheriting_peer'][nei]\
                    ['inheriting_peer'] = nei
                    

                # reset tem_peer
                tem_peer = None
                continue

        return ret_dict


    def xml(self):
        out = self.device.execute('show bgp peer-template | xml')

        etree_dict = {}
        sub_dict = {}
        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                expect_command='show bgp peer-template')

        # top table root
        root = Common.retrieve_xml_child(root=root, key='TABLE_neighbor')
        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for peer_tree in root.findall('{}ROW_neighbor'.format(namespace)):
            # vrf
            try:
                template = peer_tree.find('{}templatepeer'.format(namespace)).text
            except:
                break

            if 'template' not in etree_dict:
                etree_dict['template'] = {}
            if template not in etree_dict['template']:
                etree_dict['template'][template] = {}

            # <sourceif>loopback1</sourceif>
            try:
                etree_dict['template'][template]['source_interface'] = \
                    peer_tree.find('{}sourceif'.format(namespace)).text
            except:
                pass

            # <lowmemexempt>true</lowmemexempt>
            try:
                if peer_tree.find('{}lowmemexempt'.format(namespace)).text == 'true':
                    etree_dict['template'][template]['low_mem_exempt'] = True
                else:
                    etree_dict['template'][template]['low_mem_exempt'] = False
            except:
                pass

            # <ttlsecurity>false</ttlsecurity>
            if peer_tree.find('{}ttlsecurity'.format(namespace)).text == 'true':
                etree_dict['template'][template]['logging_neighbor_events'] = True
            else:
                etree_dict['template'][template]['logging_neighbor_events'] = False

            # <passiveonly>true</passiveonly>
            if peer_tree.find('{}passiveonly'.format(namespace)).text == 'true':
                etree_dict['template'][template]['passive_only'] = True
            else:
                etree_dict['template'][template]['passive_only'] = False

            # <localas-inactive>false</localas-inactive>
            if peer_tree.find('{}localas-inactive'.format(namespace)).text == 'true':
                etree_dict['template'][template]['local_as_inactive'] = True
            else:
                etree_dict['template'][template]['local_as_inactive'] = False

            # <remove-privateas>false</remove-privateas>
            if peer_tree.find('{}remove-privateas'.format(namespace)).text == 'true':
                etree_dict['template'][template]['remove_private_as'] = True
            else:
                etree_dict['template'][template]['remove_private_as'] = False

            # <ttllimit>100</ttllimit>
            try:
                etree_dict['template'][template]['external_bgp_peer_hops_limit'] = \
                    int(peer_tree.find('{}ttllimit'.format(namespace)).text)
            except:
                pass

             # vrf table
            vrf_tree = peer_tree.find('{}TABLE_vrf'.format(namespace))
            if vrf_tree:
                # -----   loop vrf  -----
                for vrf_root in vrf_tree.findall('{}ROW_vrf'.format(namespace)):
                    # <vrf-name>default</vrf-name>
                    try:
                        vrf = vrf_root.find('{}vrf-name'.format(namespace)).text.lower()
                    except:
                        continue

                    # inheritingpeer table
                    inherit_tree = vrf_root.find('{}TABLE_inheritingpeer'.format(namespace))
                    if not inherit_tree:
                        continue

                    # -----   loop inheritingpeer  -----
                    for inherit_root in inherit_tree.findall('{}ROW_inheritingpeer'
                                                             .format(namespace)):

                        # <inheritingpeer>21.0.201.1</inheritingpeer>
                        try:
                            inherit_peer = inherit_root.find('{}inheritingpeer'
                                                             .format(namespace)).text.lower()
                        except:
                            continue
                        if 'vrf' not in etree_dict['template'][template]:
                            etree_dict['template'][template]['vrf'] = {}
                        if vrf not in etree_dict['template'][template]['vrf']:
                            etree_dict['template'][template]['vrf'][vrf] = {}

                        if 'inheriting_peer' not in etree_dict['template']\
                            [template]['vrf'][vrf]:
                            etree_dict['template'][template]['vrf'][vrf]\
                                ['inheriting_peer'] = {}
                            
                        if inherit_peer not in etree_dict['template']\
                            [template]['vrf'][vrf]['inheriting_peer']:
                            etree_dict['template'][template]['vrf'][vrf]\
                                ['inheriting_peer'][inherit_peer] = {}

                        etree_dict['template'][template]['vrf'][vrf]\
                                ['inheriting_peer'][inherit_peer]['inheriting_peer'] = inherit_peer


            # address_family table
            afi = peer_tree.find('{}TABLE_peraf'.format(namespace))

            # -----   loop address_family  -----
            for af_root in afi.findall('{}ROW_peraf'.format(namespace)):

                try:
                    # address_family
                    row_safi = af_root.find('{}TABLE_persaf'.format(namespace))
                    af_root = row_safi.find('{}ROW_persaf'.format(namespace))
                    af = af_root.find('{}per-af-name'.format(namespace)).text.lower()
                except:
                    continue

                if 'address_family' not in etree_dict['template'][template]:
                    etree_dict['template'][template]['address_family'] = {}
                if af not in etree_dict['template'][template]['address_family']:
                    etree_dict['template'][template]['address_family'][af] = {}

                sub_dict = etree_dict['template'][template]['address_family'][af]

                # <conditionmap>DENY_ALL_RM</conditionmap>
                try:
                    sub_dict['condition_map'] = \
                        af_root.find('{}conditionmap'.format(namespace)).text
                except:
                    pass

                # <advertisemap>BLOCK-ALL</advertisemap>
                try:
                    sub_dict['advertise_map'] = \
                        af_root.find('{}advertisemap'.format(namespace)).text
                except:
                    pass

                # <advertisemapstatus>Advertise</advertisemapstatus>
                try:
                    sub_dict['advertise_map_status'] = \
                        af_root.find('{}advertisemapstatus'.format(namespace)).text.lower()
                except:
                    pass

                try:
                    # <insoftreconfigallowed>false</insoftreconfigallowed>
                    if af_root.find('{}insoftreconfigallowed'.format(namespace)).text == 'true':
                        sub_dict['in_soft_reconfig_allowed'] = True
                    else:
                        sub_dict['in_soft_reconfig_allowed'] = False
                except:
                    pass

                # <sendcommunity>true</sendcommunity>
                if af_root.find('{}sendcommunity'.format(namespace)).text == 'true':
                    sub_dict['send_community'] = True
                else:
                    sub_dict['send_community'] = False

                # <sendextcommunity>true</sendextcommunity>
                if af_root.find('{}sendextcommunity'.format(namespace)).text == 'true':
                    sub_dict['send_ext_community'] = True
                else:
                    sub_dict['send_ext_community'] = False

                # <thirdpartynexthop>false</thirdpartynexthop>
                if af_root.find('{}thirdpartynexthop'.format(namespace)).text == 'true':
                    sub_dict['third_party_nexthop'] = True
                else:
                    sub_dict['third_party_nexthop'] = False

                    # <asoverride>true</asoverride>
                if af_root.find('{}asoverride'.format(namespace)).text == 'true':
                    sub_dict['as_override'] = True
                else:
                    sub_dict['as_override'] = False

                # <peerascheckdisabled>false</peerascheckdisabled>
                if af_root.find('{}peerascheckdisabled'.format(namespace)).text == 'true':
                    sub_dict['peer_as_check_disabled'] = True
                else:
                    sub_dict['peer_as_check_disabled'] = False

                # <rrconfigured>false</rrconfigured>
                if af_root.find('{}rrconfigured'.format(namespace)).text == 'true':
                    sub_dict['rr_configured'] = True
                else:
                    sub_dict['rr_configured'] = False

                # <localnexthop>0.0.0.0</localnexthop>
                try:
                    sub_dict['local_nexthop'] = \
                        af_root.find('{}localnexthop'.format(namespace)).text
                except:
                    pass

                # <maxpfx>888888888</maxpfx>
                try:
                    sub_dict['max_pfx'] = \
                        int(af_root.find('{}maxpfx'.format(namespace)).text)
                except:
                    pass

                # <soo>SOO:1.1.1.1:100</soo>
                try:
                    sub_dict['soo'] = \
                        af_root.find('{}soo'.format(namespace)).text
                except:
                    pass

                # <weight>9999</weight>
                try:
                    sub_dict['weight'] = \
                        int(af_root.find('{}weight'.format(namespace)).text)
                except:
                    pass

                # <allowasin>10</allowasin>
                try:
                    sub_dict['allow_as_in'] = \
                        int(af_root.find('{}allowasin'.format(namespace)).text)
                except:
                    pass

                # <defaultoriginate>true</defaultoriginate>
                try:
                    if af_root.find('{}defaultoriginate'.format(namespace)).text == 'true':
                        sub_dict['default_originate'] = True
                    else:
                        sub_dict['default_originate'] = False
                except:
                    pass

                # <defaultoriginatermap>PASS-ALL</defaultoriginatermap>
                try:
                    sub_dict['default_originate_route_map'] = \
                        af_root.find('{}defaultoriginatermap'.format(namespace)).text
                except:
                    pass

                # <unsuppress-map>ORIGINATE_IPV6</unsuppress-map>
                try:
                    sub_dict['unsuppress_map'] = \
                        af_root.find('{}unsuppress-map'.format(namespace)).text
                except:
                    pass
                

                # TABLE_inpolicy table
                policy = af_root.find('{}TABLE_inpolicy'.format(namespace))

                if policy:
                    # -----   loop in policy  -----
                    for policy_root in policy.findall('{}ROW_inpolicy'.format(namespace)):
                        try:
                            policy = policy_root.find('{}inpolicyname'.format(namespace)).text
                        except:
                            continue

                        if 'in_policy' not in sub_dict:
                            sub_dict['in_policy'] = {}
                        if policy not in sub_dict['in_policy']:
                            sub_dict['in_policy'][policy] = {}

                        sub_dict['in_policy'][policy]['name'] = policy

                        # <inpolicytype>route-map</inpolicytype>
                        sub_dict['in_policy'][policy]['type'] = \
                            policy_root.find('{}inpolicytype'.format(namespace)).text

                # TABLE_outpolicy table
                policy = af_root.find('{}TABLE_outpolicy'.format(namespace))

                if policy:
                    # -----   loop in policy  -----
                    for policy_root in policy.findall('{}ROW_outpolicy'.format(namespace)):
                        try:
                            policy = policy_root.find('{}outpolicyname'.format(namespace)).text
                        except:
                            continue
                        if 'out_policy' not in sub_dict:
                            sub_dict['out_policy'] = {}
                        if policy not in sub_dict['out_policy']:
                            sub_dict['out_policy'][policy] = {}

                        sub_dict['out_policy'][policy]['name'] = policy

                        # <outpolicytype>route-map</outpolicytype>
                        sub_dict['out_policy'][policy]['type'] = \
                            policy_root.find('{}outpolicytype'.format(namespace)).text

                                                                                                                         
        return etree_dict


# ==============================================================================
# Schema for:
# * 'show bgp vrf <vrf> <address_family>  policy statistics redistribute
# * 'show bgp vrf <vrf> <address_family>  policy statistics dampening'
# * 'show bgp vrf <vrf> <address_family>  policy statistics neighbor <neighbor>'
# ==============================================================================
class ShowBgpPolicyStatisticsSchema(MetaParser):
    """Schema for:
       show bgp [vrf <vrf>] <address_family>  policy statistics redistribute
       show bgp [vrf <vrf>] <address_family>  policy statistics dampening
       show bgp [vrf <vrf>] <address_family>  policy statistics neighbor <neighbor>
    """

    schema = {
        'vrf': {
            Any(): {
                Optional('rpm_handle_count'): int,
                Optional('route_map'): {
                    Any():{
                        Any(): {
                            'action': str,
                            'seq_num': int,
                            'total_accept_count': int,
                            'total_reject_count': int,
                            Optional('command'): {
                                'compare_count': int,
                                'match_count': int,
                                'command': str
                            }
                        },
                    },
                }
            },
        }
    }

# ==============================================================================
# Parser for:
# * 'show bgp vrf <vrf> <address_family>  policy statistics redistribute'
# * 'show bgp vrf <vrf> <address_family>  policy statistics dampening''
# * 'show bgp vrf <vrf> <address_family>  policy statistics neighbor <neighbor>'
# ==============================================================================
class ShowBgpPolicyStatistics(ShowBgpPolicyStatisticsSchema):
    """Parser for:
        show bgp [vrf <vrf>] <address_family>  policy statistics redistribute
        show bgp [vrf <vrf>] <address_family>  policy statistics dampening
        show bgp [vrf <vrf>] <address_family>  policy statistics neighbor <neighbor>
        parser class implements detail parsing mechanisms for cli,xml output"""
    
    def cli(self, cmd):

        out = self.device.execute(cmd)
        
        # Init vars
        ret_dict = {}
        index = 1

        # extract vrf info if specified,
        # if not, vrf is default
        m = re.compile(r'^show +bgp +vrf +(?P<vrf>\S+)').match(cmd)
        if m:
            vrf = m.groupdict()['vrf']
            if vrf == 'all':
                vrf = ''
        else:
            vrf = 'default'

        for line in out.splitlines():
            line = line.strip()

            # Details for VRF default
            p1 = re.compile(r'^Details +for +VRF +'
                             '(?P<vrf>[\w\-]+)$')
            m = p1.match(line)
            if m:
                vrf = m.groupdict()['vrf']
                nei_flag = True
                continue

            # No such neighbor
            if re.compile(r'No +such +neighbor$').match(line):
                nei_flag = False

            # Total count for redistribute rpm handles: 1
            # Total count for neighbor rpm handles: 1
            # Total count for dampening rpm handles: 1
            p2 = re.compile(r'^Total +count +for +(?P<type>\w+) +rpm +handles: +'
                             '(?P<handles>\d+)$')
            m = p2.match(line)

            # BGP policy statistics not available
            p3 = re.compile(r'^BGP +policy +statistics +not +available$')
            m1 = p3.match(line)

            if m or m1:
                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}

                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}

                ret_dict['vrf'][vrf]['rpm_handle_count'] = \
                    int(m.groupdict()['handles']) if m else 0
                continue

            # C: No. of comparisions, M: No. of matches

            # route-map Filter-pip deny 10
            # route-map ADD_RT_400_400 permit 10
            # route-map RMAP_DIRECT->BGP_IPV4 permit 10
            p4 = re.compile(r'^route\-map +(?P<name>\S+) +'
                             '(?P<action>\w+) +(?P<seqnum>\d+)$')
            m = p4.match(line)
            if m:
                name = m.groupdict()['name']

                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}

                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}

                if 'route_map' not in ret_dict['vrf'][vrf]:
                    ret_dict['vrf'][vrf]['route_map'] = {}

                if name not in ret_dict['vrf'][vrf]['route_map']:
                    ret_dict['vrf'][vrf]['route_map'][name] = {}
                    index = 1
                else:
                    index += 1

                if index not in ret_dict['vrf'][vrf]['route_map'][name]:
                    ret_dict['vrf'][vrf]['route_map'][name][index] = {}

                ret_dict['vrf'][vrf]['route_map'][name][index]['action'] = \
                    m.groupdict()['action']

                ret_dict['vrf'][vrf]['route_map'][name][index]['seq_num'] = \
                    int(m.groupdict()['seqnum'])
                continue

            #   match ip address prefix-list pip-prefix                    C: 0      M: 0 
            #   match ip address prefix-list DIRECT->BGP_IPV4              C: 16     M: 0 
            p5 = re.compile(r'^(?P<command>[\w\s\-\>]+) +'
                             'C: +(?P<compare_count>\d+) +'
                             'M: +(?P<match_count>\d+)$')
            m = p5.match(line)
            if m:
                command = m.groupdict()['command'].strip()

                if 'command' not in ret_dict['vrf'][vrf]['route_map'][name][index]:
                    ret_dict['vrf'][vrf]['route_map'][name][index]['command'] = {}

                ret_dict['vrf'][vrf]['route_map'][name][index]['command']\
                    ['compare_count'] = int(m.groupdict()['compare_count'])

                ret_dict['vrf'][vrf]['route_map'][name][index]['command']\
                    ['match_count'] = int(m.groupdict()['match_count'])

                ret_dict['vrf'][vrf]['route_map'][name][index]['command']\
                    ['command'] = command
                continue

            # Total accept count for policy: 0
            p6 = re.compile(r'^Total +accept +count +for +policy: +'
                             '(?P<total_accept_count>\d+)$')
            m = p6.match(line)
            if m:
                ret_dict['vrf'][vrf]['route_map'][name][index]['total_accept_count'] = \
                    int(m.groupdict()['total_accept_count'])
                continue

            # Total reject count for policy: 0
            p7 = re.compile(r'^Total +reject +count +for +policy: +'
                             '(?P<total_reject_count>\d+)$')
            m = p7.match(line)
            if m:
                ret_dict['vrf'][vrf]['route_map'][name][index]['total_reject_count'] = \
                    int(m.groupdict()['total_reject_count'])
                continue

        return ret_dict


    def xml(self, cmd):
        out = self.device.execute('{} | xml'.format(cmd))

        etree_dict = {}
        neighbor = None
        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                       expect_command=cmd)

        # get neighbor
        nei = Common.retrieve_xml_child(root=root, key='__XML__PARAM__neighbor-id')

        if hasattr(nei, 'tag'):
            for item in nei.getchildren():
                if '__XML__value' in item.tag:
                    neighbor = item.text
                    continue

                # cover the senario that __readonly__ may be mssing when
                # there are values in the output
                if '__readonly__' in item.tag:
                    root = item.getchildren()[0]
                else:
                    root = item
        else:
            # top table rootl
            root = Common.retrieve_xml_child(root=root, key='TABLE_vrf')

        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-polstats'.format(namespace)).text
            except:
                break

            if 'vrf' not in etree_dict:
                etree_dict['vrf'] = {}
            if vrf not in etree_dict['vrf']:
                etree_dict['vrf'][vrf] = {}

            # <rpm-handle-count>1</rpm-handle-count>
            etree_dict['vrf'][vrf]['rpm_handle_count'] = \
                int(vrf_tree.find('{}rpm-handle-count'.format(namespace)).text)

             # route_map table
            rpm_tree = vrf_tree.find('{}TABLE_rmap'.format(namespace))
            if not rpm_tree:
                continue

            # -----   loop route_map  -----
            for rmp_root in rpm_tree.findall('{}ROW_rmap'.format(namespace)):
                # route map
                try:
                    name = rmp_root.find('{}name'.format(namespace)).text
                    name = name.replace('&gt;', '>')
                except:
                    continue

                if 'route_map' not in etree_dict['vrf'][vrf]:
                    etree_dict['vrf'][vrf]['route_map'] = {}

                if name not in etree_dict['vrf'][vrf]['route_map']:
                    etree_dict['vrf'][vrf]['route_map'][name] = {}
                    # initial index
                    index = 1
                else:
                    index += 1
                    
                if index not in etree_dict['vrf'][vrf]['route_map'][name]:
                    etree_dict['vrf'][vrf]['route_map'][name][index] = {}


                # <action>deny</action>
                try:
                    etree_dict['vrf'][vrf]['route_map'][name][index]['action'] = \
                        rmp_root.find('{}action'.format(namespace)).text
                except:
                    pass

                # <seqnum>10</seqnum>
                try:
                    etree_dict['vrf'][vrf]['route_map'][name][index]['seq_num'] = \
                        int(rmp_root.find('{}seqnum'.format(namespace)).text)
                except:
                    pass

                # <totalacceptcount>0</totalacceptcount>
                try:
                    etree_dict['vrf'][vrf]['route_map'][name][index]['total_accept_count'] = \
                        int(rmp_root.find('{}totalacceptcount'.format(namespace)).text)
                except:
                    pass

                # <totalrejectcount>2</totalrejectcount>
                try:
                    etree_dict['vrf'][vrf]['route_map'][name][index]['total_reject_count'] = \
                        int(rmp_root.find('{}totalrejectcount'.format(namespace)).text)
                except:
                    pass


                # TABLE_cmd table
                command = rmp_root.find('{}TABLE_cmd'.format(namespace))

                if not command:
                    continue

                # -----   loop command  -----
                for command_root in command.findall('{}ROW_cmd'.format(namespace)):
                    try:
                        cmd_str = command_root.find('{}command'.format(namespace)).text.strip()
                        cmd_str = cmd_str.replace('&gt;', '>')
                    except:
                        continue

                    if 'command' not in etree_dict['vrf'][vrf]['route_map'][name][index]:
                        etree_dict['vrf'][vrf]['route_map'][name][index]['command'] = {}

                    # command
                    etree_dict['vrf'][vrf]['route_map'][name][index]\
                        ['command']['command'] = cmd_str

                    # <comparecount>2</comparecount>
                    try:
                        etree_dict['vrf'][vrf]['route_map'][name][index]\
                            ['command']['compare_count'] = \
                                int(command_root.find('{}comparecount'.format(namespace)).text)
                    except:
                        pass
                    
                    # <matchcount>0</matchcount>
                    try:
                        etree_dict['vrf'][vrf]['route_map'][name][index]\
                            ['command']['match_count'] = \
                                int(command_root.find('{}matchcount'.format(namespace)).text)
                    except:
                        pass
        return etree_dict

# ===============================================================================
# Parser for 'show bgp vrf <vrf> <address_family> policy statistics redistribute'
# ===============================================================================
class ShowBgpPolicyStatisticsRedistribute(ShowBgpPolicyStatistics):
    """Parser for:
        show bgp [vrf <vrf>] <address_family> policy statistics redistribute
        parser class implements detail parsing mechanisms for cli,xml output"""

    def cli(self, address_family, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics redistribute'\
                  .format(vrf=vrf, af=address_family)
        else:
            cmd = 'show bgp {af} policy statistics redistribute'\
                  .format(af=address_family)
        return super().cli(cmd)

    def xml(self, address_family, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics redistribute'\
                  .format(vrf=vrf, af=address_family)
        else:
            cmd = 'show bgp {af} policy statistics redistribute'\
                  .format(af=address_family)
        return super().xml(cmd)

# ==================================================================================
# Parser for 'show bgp vrf <vrf> <address_family> policy statistics neighbor <WORD>'
# ==================================================================================
class ShowBgpPolicyStatisticsNeighbor(ShowBgpPolicyStatistics):
    """Parser for:
        show bgp [vrf <vrf>] <address_family> policy statistics neighbor <neighbor>
        parser class implements detail parsing mechanisms for cli,xml output"""
    
    def cli(self, address_family, neighbor, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics neighbor {nei}'\
                  .format(vrf=vrf, af=address_family, nei=neighbor)
        else:
            cmd = 'show bgp {af} policy statistics neighbor {nei}'\
                  .format(af=address_family, nei=neighbor)
        return super().cli(cmd)

    def xml(self, address_family, neighbor, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics neighbor {nei}'\
                  .format(vrf=vrf, af=address_family, nei=neighbor)
        else:
            cmd = 'show bgp {af} policy statistics neighbor {nei}'\
                  .format(af=address_family, nei=neighbor)
        return super().xml(cmd)

# ============================================================================
# Parser for 'show bgp vrf <vrf> <address_family> policy statistics dampening'
# ============================================================================
class ShowBgpPolicyStatisticsDampening(ShowBgpPolicyStatistics):
    """Parser for:
        show bgp [vrf <vrf>] <address_family> policy statistics dampening
        parser class implements detail parsing mechanisms for cli,xml output"""
    
    def cli(self, address_family, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics dampening'\
                  .format(vrf=vrf, af=address_family)
        else:
            cmd = 'show bgp {af} policy statistics dampening'\
                  .format(af=address_family)
        return super().cli(cmd)

    def xml(self, address_family, vrf=''):
        if vrf:
            cmd = 'show bgp vrf {vrf} {af} policy statistics dampening'\
                  .format(vrf=vrf, af=address_family)
        else:
            cmd = 'show bgp {af} policy statistics dampening'\
                  .format(af=address_family)
        return super().xml(cmd)


# ==============================================================================
# Schema for:
# * 'show bgp sessions [vrf <WORD>]'
# ==============================================================================
class ShowBgpSessionsSchema(MetaParser):
    """Schema for:
       show bgp sessions
       show bgp sessions vrf <WROD>
    """

    schema = {
        'total_peers': int,
        'total_established_peers': int,
        'local_as': int,
        'vrf': {
            Any(): {
                'local_as': int,
                'vrf_peers': int,
                'vrf_established_peers': int,
                'router_id': str,
                Optional('neighbor'): {
                    Any(): {
                        'connections_dropped': int,
                        'remote_as': int,
                        'last_flap': str,
                        'last_read': str,
                        'last_write': str,
                        'state': str,
                        'local_port': int,
                        'remote_port': int,
                        'notifications_sent': int,
                        'notifications_received': int,
                    },
                }
            },
        }
    }

# ==============================================================================
# Parser for:
# * 'show bgp sessions'
# ==============================================================================
class ShowBgpSessions(ShowBgpSessionsSchema):
    """Parser for:
        show bgp sessions"""
    
    def cli(self, vrf=''):

        cmd = 'show bgp sessions' if not vrf else \
              'show bgp sessions vrf {}'.format(vrf)

        out = self.device.execute(cmd)
        
        # Init vars
        ret_dict = {}
        status_map = {'I': 'idle',
                      'A': 'active',
                      'O': 'open',
                      'E': 'established',
                      'C': 'closing',
                      'S': 'shutdown'}

        for line in out.splitlines():
            line = line.strip()

            # Total peers 4, established peers 3
            p1 = re.compile(r'^Total +peers +(?P<total>\d+), +'
                             'established +peers +(?P<established>\d+)$')
            m = p1.match(line)
            if m:
                ret_dict['total_peers'] = int(m.groupdict()['total'])
                ret_dict['total_established_peers'] = \
                    int(m.groupdict()['established'])
                continue

            # ASN 100
            p2 = re.compile(r'^ASN +(?P<asn>\d+)$')
            m = p2.match(line)
            if m:
                ret_dict['local_as'] = int(m.groupdict()['asn'])
                continue


            # VRF default, local ASN 100
            p3 = re.compile(r'^VRF +(?P<vrf>\S+), +'
                             'local +ASN +(?P<asn>\d+)$')
            m = p3.match(line)
            if m:
                vrf = m.groupdict()['vrf']
                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}
                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}
                ret_dict['vrf'][vrf]['local_as'] = \
                    int(m.groupdict()['asn'])
                continue

            # peers 4, established peers 3, local router-id 100.1.1.1
            p4 = re.compile(r'^peers +(?P<peer>\d+), +'
                             'established +peers +(?P<established>\d+), +'
                             'local +router\-id +(?P<id>[\w\.\:]+)$')
            m = p4.match(line)
            if m:
                ret_dict['vrf'][vrf]['vrf_peers'] = \
                    int(m.groupdict()['peer'])

                ret_dict['vrf'][vrf]['vrf_established_peers'] = \
                    int(m.groupdict()['established'])
                    
                ret_dict['vrf'][vrf]['router_id'] = \
                    m.groupdict()['id']
                continue

            # 50.1.1.101        300 2     00:30:01|never   |never    I   0/0          2/0
            p5 = re.compile(r'^(?P<nei>[\w\.\:]+) +'
                             '(?P<asn>\d+) +'
                             '(?P<dropped>\d+) +'
                             '(?P<last_flap>[\w\.\:]+) *\|'
                             '(?P<last_read>[\w\.\:]+) *\|'
                             '(?P<last_write>[\w\.\:]+) +'
                             '(?P<state>[a-zA-Z]) +'
                             '(?P<local_port>\d+)\/'
                             '(?P<remote_port>\d+) +'
                             '(?P<notifications_sent>\d+)\/'
                             '(?P<notifications_received>\d+)$')
            m = p5.match(line)
            if m:
                nei = m.groupdict()['nei']
                if 'neighbor' not in ret_dict['vrf'][vrf]:
                    ret_dict['vrf'][vrf]['neighbor'] = {}
                if nei not in ret_dict['vrf'][vrf]['neighbor']:
                    ret_dict['vrf'][vrf]['neighbor'][nei] = {}

                ret_dict['vrf'][vrf]['neighbor'][nei]['remote_as'] = \
                    int(m.groupdict()['asn'])

                ret_dict['vrf'][vrf]['neighbor'][nei]['connections_dropped'] = \
                    int(m.groupdict()['dropped'])

                ret_dict['vrf'][vrf]['neighbor'][nei]['last_flap'] = \
                    m.groupdict()['last_flap']

                ret_dict['vrf'][vrf]['neighbor'][nei]['last_read'] = \
                    m.groupdict()['last_read']

                ret_dict['vrf'][vrf]['neighbor'][nei]['last_write'] = \
                    m.groupdict()['last_write']

                ret_dict['vrf'][vrf]['neighbor'][nei]['state'] = \
                    status_map[m.groupdict()['state']]

                ret_dict['vrf'][vrf]['neighbor'][nei]['local_port'] = \
                    int(m.groupdict()['local_port'])

                ret_dict['vrf'][vrf]['neighbor'][nei]['remote_port'] = \
                    int(m.groupdict()['remote_port'])

                ret_dict['vrf'][vrf]['neighbor'][nei]['notifications_sent'] = \
                    int(m.groupdict()['notifications_sent'])

                ret_dict['vrf'][vrf]['neighbor'][nei]['notifications_received'] = \
                    int(m.groupdict()['notifications_received'])
                continue

        return ret_dict

    def xml(self, vrf=''):

        cmd = 'show bgp sessions' if not vrf else \
              'show bgp sessions vrf {}'.format(vrf)

        out = self.device.execute(cmd + ' | xml')

        etree_dict = {}

        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                       expect_command=cmd)

        ret = Common.retrieve_xml_child(
                root=root,
                key='__readonly__')

        if hasattr(ret, 'tag'):
            # get total_peers                
            try:
                total_peers = ret.find('{}totalpeers'.format(namespace)).text
                etree_dict['total_peers'] = int(total_peers)
            except:
                pass

            # get total_established_peers            
            try:
                total_established_peers = ret.find(
                    '{}totalestablishedpeers'.format(namespace)).text
                etree_dict['total_established_peers'] = int(total_established_peers)
            except:
                pass

            # get local_as               
            try:
                local_as = ret.find('{}localas'.format(namespace)).text
                etree_dict['local_as'] = int(local_as)
            except:
                pass

        else:
            # output is empty
            return etree_dict

        # find Vrf root
        root = ret.find('{}TABLE_vrf'.format(namespace))

        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-out'.format(namespace)).text
            except:
                break

            if 'vrf' not in etree_dict:
                etree_dict['vrf'] = {}
            if vrf not in etree_dict['vrf']:
                etree_dict['vrf'][vrf] = {}

            # <local-as>333</local-as>
            etree_dict['vrf'][vrf]['local_as'] = \
                int(vrf_tree.find('{}local-as'.format(namespace)).text)

            # <vrfpeers>3</vrfpeers>
            etree_dict['vrf'][vrf]['vrf_peers'] = \
                int(vrf_tree.find('{}vrfpeers'.format(namespace)).text)

            # <vrfestablishedpeers>2</vrfestablishedpeers>
            etree_dict['vrf'][vrf]['vrf_established_peers'] = \
                int(vrf_tree.find('{}vrfestablishedpeers'.format(namespace)).text)
                
            # <router-id>19.0.0.6</router-id>
            etree_dict['vrf'][vrf]['router_id'] = \
                vrf_tree.find('{}router-id'.format(namespace)).text
                
             # Neighbor table
            nei_tree = vrf_tree.find('{}TABLE_neighbor'.format(namespace))
            if not nei_tree:
                continue

            # -----   loop neighbors  -----
            for nei_root in nei_tree.findall('{}ROW_neighbor'.format(namespace)):
                # neighbor
                try:
                    nei = nei_root.find('{}neighbor-id'.format(namespace)).text
                except:
                    continue

                if 'neighbor' not in etree_dict['vrf'][vrf]:
                    etree_dict['vrf'][vrf]['neighbor'] = {}

                if nei not in etree_dict['vrf'][vrf]['neighbor']:
                    etree_dict['vrf'][vrf]['neighbor'][nei] = {}

                # <connectionsdropped>0</connectionsdropped>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['connections_dropped'] = \
                        int(nei_root.find('{}connectionsdropped'.format(namespace)).text)
                except:
                    pass

                # <remoteas>333</remoteas>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['remote_as'] = \
                        int(nei_root.find('{}remoteas'.format(namespace)).text)
                except:
                    pass

                # <lastflap>PT1H4M41S</lastflap>
                try:
                    ret = nei_root.find('{}lastflap'.format(namespace)).text
                    ret = Common.convert_xml_time(ret)
                    etree_dict['vrf'][vrf]['neighbor'][nei]['last_flap'] = \
                        'never' if 'P' in ret else ret
                except:
                    pass
                    
                # <lastread>PT47S</lastread>
                try:
                    ret = nei_root.find('{}lastread'.format(namespace)).text
                    ret = Common.convert_xml_time(ret)
                    etree_dict['vrf'][vrf]['neighbor'][nei]['last_read'] = \
                        'never' if 'P' in ret else ret
                except:
                    pass
                    
                # <lastwrite>PT15S</lastwrite>
                try:
                    ret = nei_root.find('{}lastwrite'.format(namespace)).text
                    ret = Common.convert_xml_time(ret)
                    etree_dict['vrf'][vrf]['neighbor'][nei]['last_write'] = \
                        'never' if 'P' in ret else ret
                except:
                    pass
                    
                # <state>Established</state>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['state'] = \
                        nei_root.find('{}state'.format(namespace)).text.lower()
                except:
                    pass
                    
                # <localport>179</localport>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['local_port'] = \
                        int(nei_root.find('{}localport'.format(namespace)).text)
                except:
                    pass
                    
                # <remoteport>48392</remoteport>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['remote_port'] = \
                        int(nei_root.find('{}remoteport'.format(namespace)).text)
                except:
                    pass
                    
                # <notificationssent>0</notificationssent>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['notifications_sent'] = \
                        int(nei_root.find('{}notificationssent'.format(namespace)).text)
                except:
                    pass
                    
                # <notificationsreceived>0</notificationsreceived>
                try:
                    etree_dict['vrf'][vrf]['neighbor'][nei]['notifications_received'] = \
                        int(nei_root.find('{}notificationsreceived'.format(namespace)).text)
                except:
                    pass                    

        return etree_dict


# ==============================================================================
# Schema for:
# * 'show bgp <address_family> labels [vrf <WROD>]'
# ==============================================================================
class ShowBgpSessionsSchema(MetaParser):
    """Schema for:
       show bgp <address_family> labels
       show bgp <address_family> labels vrf <WROD>
    """

    schema = {
        'vrf': {
            Any(): {
                'address_family': {
                    Any(): {
                        'table_version': int,
                        'router_id': str,
                        Optional('prefix'): {
                            Any(): {
                                'index': {
                                    Any(): {
                                        'status': str,
                                        'best_path': bool,
                                        'type': str,
                                        'status_code': str,
                                        Optional('best_code'): str,
                                        'type_code': str,
                                        'nexthop': str,
                                        'in_label': str,
                                        'out_label': str,
                                        Optional('vpn'): str,
                                        Optional('hold_down'): str,
                                    },
                                }
                            },
                        },
                        Optional('route_distinguisher'): {
                            Any(): {
                                Optional('rd_vrf'): str,
                                'prefix': {
                                    Any(): {
                                        'index': {
                                            Any(): {
                                                'status': str,
                                                'best_path': bool,
                                                'type': str,
                                                'status_code': str,
                                                Optional('best_code'): str,
                                                'type_code': str,
                                                'nexthop': str,
                                                'in_label': str,
                                                'out_label': str,
                                                Optional('vpn'): str,
                                                Optional('hold_down'): str,
                                            },
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }
    }

# ==============================================================================
# Parser for:
# * 'show bgp <address_family> labels [vrf <WROD>]'
# ==============================================================================
class ShowBgpLabels(ShowBgpSessionsSchema):
    """Parser for:
        show bgp <address_family> labels [vrf <WROD>]"""
    
    def cli(self, address_family, vrf=''):
        assert address_family in ['ipv4 unicast', 'ipv4 multicast',
                                  'ipv6 unicast', 'ipv6 multicast',
                                  'vpnv4 unicast', 'vpnv6 unicast']

        cmd = 'show bgp {} labels'.format(address_family) if not vrf else \
              'show bgp {af} labels vrf {vrf}'.format(af=address_family, vrf=vrf)

        out = self.device.execute(cmd)
        
        # Init vars
        ret_dict = {}
        status_map = {'*': 'valid',
                      's': 'suppressed,',
                      'x': 'deleted',
                      'S': 'stale',
                      'd': 'dampened',
                      'h': 'history',
                      '>': 'best'}
        path_type_map = {'i': 'internal',
                         'e': 'external',
                         'c': 'confed',
                         'l': 'local',
                         'r': 'redist',
                         'a': 'aggregate',
                         'I': 'injected'}

        for line in out.splitlines():
            line = line.strip()

            # BGP routing table information for VRF default, address family IPv4 Unicast
            p1 = re.compile(r'^BGP +routing +table +information +for +VRF +(?P<vrf>\S+), +'
                             'address +family +(?P<af>[\w\s]+)$')
            m = p1.match(line)
            if m:
                vrf = m.groupdict()['vrf']
                address_family = m.groupdict()['af'].lower()
                continue

            # BGP table version is 7, Local Router ID is 19.0.0.6
            # BGP table version is 3, local router ID is 92.1.1.0
            p2 = re.compile(r'^BGP +table +version +is +(?P<ver>\d+), +'
                             '(L|l)ocal +(R|r)outer +ID +is +(?P<router_id>[\w\.\:]+)$')
            m = p2.match(line)
            if m:
                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}
                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}
                if 'address_family' not in ret_dict['vrf'][vrf]:
                    ret_dict['vrf'][vrf]['address_family'] = {}
                if address_family not in ret_dict['vrf'][vrf]['address_family']:
                    ret_dict['vrf'][vrf]['address_family'][address_family] = {}

                sub_dict = ret_dict['vrf'][vrf]['address_family'][address_family]

                sub_dict['table_version'] = int(m.groupdict()['ver'])
                sub_dict['router_id'] = m.groupdict()['router_id']
                continue

            # Route Distinguisher: 92.1.1.0:3    (VRF vrf-9100)
            p4 = re.compile(r'^Route +Distinguisher: +(?P<rd>[\w\.\:]+) +'
                             '\(VRF +(?P<vrf>\S+)\)$')
            m = p4.match(line)
            if m:
                rd = m.groupdict()['rd']
                if 'vrf' not in ret_dict:
                    ret_dict['vrf'] = {}
                if vrf not in ret_dict['vrf']:
                    ret_dict['vrf'][vrf] = {}
                if 'address_family' not in ret_dict['vrf'][vrf]:
                    ret_dict['vrf'][vrf]['address_family'] = {}
                if address_family not in ret_dict['vrf'][vrf]['address_family']:
                    ret_dict['vrf'][vrf]['address_family'][address_family] = {}
                if 'route_distinguisher' not in ret_dict['vrf'][vrf]\
                    ['address_family'][address_family]:
                    ret_dict['vrf'][vrf]['address_family'][address_family]\
                        ['route_distinguisher'] = {}
                if rd not in ret_dict['vrf'][vrf]\
                    ['address_family'][address_family]['route_distinguisher']:
                    ret_dict['vrf'][vrf]['address_family'][address_family]\
                        ['route_distinguisher'][rd] = {}

                sub_dict = ret_dict['vrf'][vrf]['address_family']\
                    [address_family]['route_distinguisher'][rd]

                sub_dict['rd_vrf'] = m.groupdict()['vrf']
                continue


            # *>i1.5.210.0/24       19.0.101.1          nolabel/nolabel
            # * i0.0.0.0/0          95.1.1.0            nolabel/9100
            p3 = re.compile(r'^(?P<status>s|S|x|d|h|\*)'
                             '(?P<best>\>)? *'
                             '(?P<type_code>i|e|c|l|a|r|I)'
                             '(?P<prefix>[\w\/\.\:]+)? +'
                             '(?P<next_hop>[\w\/\.\:]+) +'
                             '(?P<in_label>\w+)\/'
                             '(?P<out_label>\w+)$')
            m = p3.match(line)
            if m:
                prefix_cur = m.groupdict()['prefix']
                if prefix_cur:
                    index = 0
                    prefix = prefix_cur
                else:
                    index += 1

                status_code = m.groupdict()['status']
                best_code = m.groupdict()['best']
                type_code = m.groupdict()['type_code']
                next_hop = m.groupdict()['next_hop']
                in_label = m.groupdict()['in_label']
                out_label = m.groupdict()['out_label']


                if 'prefix' not in sub_dict:
                    sub_dict['prefix'] = {}
                if prefix not in sub_dict['prefix']:
                    sub_dict['prefix'][prefix] = {}
                if 'index' not in sub_dict['prefix'][prefix]:
                    sub_dict['prefix'][prefix]['index'] = {}
                if index not in sub_dict['prefix'][prefix]['index']:
                    sub_dict['prefix'][prefix]['index'][index] = {}

                sub_dict['prefix'][prefix]['index'][index]['status'] = \
                    status_map[status_code]
                sub_dict['prefix'][prefix]['index'][index]['status_code'] = status_code

                if best_code:
                    sub_dict['prefix'][prefix]['index'][index]['best_code'] = best_code
                sub_dict['prefix'][prefix]['index'][index]['best_path'] = \
                    True if best_code else False

                sub_dict['prefix'][prefix]['index'][index]['type'] = \
                    path_type_map[type_code]
                sub_dict['prefix'][prefix]['index'][index]['type_code'] = type_code

                sub_dict['prefix'][prefix]['index'][index]['nexthop'] = next_hop
                    
                sub_dict['prefix'][prefix]['index'][index]['in_label'] = in_label
                    
                sub_dict['prefix'][prefix]['index'][index]['out_label'] = in_label
                continue

        return ret_dict

    def xml(self, address_family, vrf=''):
        assert address_family in ['ipv4 unicast', 'ipv4 multicast',
                                  'ipv6 unicast', 'ipv6 multicast',
                                  'vpnv4 unicast', 'vpnv6 unicast']

        cmd = 'show bgp {} labels'.format(address_family) if not vrf else \
              'show bgp {af} labels vrf {vrf}'.format(af=address_family, vrf=vrf)

        out = self.device.execute(cmd + ' | xml')

        etree_dict = {}

        # Remove junk characters returned by the device
        out = out.replace("]]>]]>", "")
        root = ET.fromstring(out)

        # top table root
        show_root = Common.retrieve_xml_child(root=root, key='show')
        # get xml namespace
        # {http://www.cisco.com/nxos:7.0.3.I7.1.:bgp}
        try:
            m = re.compile(r'(?P<name>\{[\S]+\})').match(show_root.tag)
            namespace = m.groupdict()['name']
        except:
            return etree_dict

        # compare cli command
        Common.compose_compare_command(root=root, namespace=namespace,
                                       expect_command=cmd)

        # find Vrf root
        root = Common.retrieve_xml_child(root=root, key='TABLE_vrf')

        if not root:
            return etree_dict

        # -----   loop vrf  -----
        for vrf_tree in root.findall('{}ROW_vrf'.format(namespace)):
            # vrf
            try:
                vrf = vrf_tree.find('{}vrf-name-out'.format(namespace)).text
            except:
                break

            # Address family table
            af_tree = vrf_tree.find('{}TABLE_afi'.format(namespace))
            if not af_tree:
                continue
            for af_root in af_tree.findall('{}ROW_afi'.format(namespace)):
                # Address family table
                saf_tree = af_root.find('{}TABLE_safi'.format(namespace))
                if not saf_tree:
                    continue
                # -----   loop address_family  -----
                for saf_root in saf_tree.findall('{}ROW_safi'.format(namespace)):
                    # neighbor
                    try:
                        af = saf_root.find('{}af-name'.format(namespace)).text
                        af = af.lower()
                    except:
                        continue

                    # <table-version>7</table-version>
                    try:
                        table_version = \
                            int(saf_root.find('{}table-version'.format(namespace)).text)
                    except:
                        table_version = None

                    # <router-id>19.0.0.6</router-id>
                    try:
                        router_id = \
                            saf_root.find('{}router-id'.format(namespace)).text
                    except:
                        router_id = None

                    if table_version or router_id:
                        if 'vrf' not in etree_dict:
                            etree_dict['vrf'] = {}
                        if vrf not in etree_dict['vrf']:
                            etree_dict['vrf'][vrf] = {}

                        if 'address_family' not in etree_dict['vrf'][vrf]:
                            etree_dict['vrf'][vrf]['address_family'] = {}

                        if af not in etree_dict['vrf'][vrf]['address_family']:
                            etree_dict['vrf'][vrf]['address_family'][af] = {}
                        if table_version:
                            etree_dict['vrf'][vrf]['address_family'][af]['table_version'] = table_version
                        if router_id:
                            etree_dict['vrf'][vrf]['address_family'][af]['router_id'] = router_id

                     # RD table
                    rd_tree = saf_root.find('{}TABLE_rd'.format(namespace))
                    if not rd_tree:
                        continue

                    # -----   loop rd  -----
                    for rd_root in rd_tree.findall('{}ROW_rd'.format(namespace)):
                        # neighbor
                        try:
                            rd = rd_root.find('{}rd_val'.format(namespace)).text
                        except:
                            rd = None

                        if rd:
                            if 'route_distinguisher' not in etree_dict['vrf'][vrf]:
                                etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'] = {}

                            if rd not in etree_dict['vrf'][vrf]['address_family']:
                                etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'][rd] = {}
                            sub_dict = etree_dict['vrf'][vrf]['address_family'][af]\
                                    ['route_distinguisher'][rd]
                        else:
                            sub_dict = etree_dict['vrf'][vrf]['address_family'][af]

                        # <rd_vrf>vrf-9100</rd_vrf>
                        try:
                            sub_dict['rd_vrf'] = rd_root.find('{}rd_vrf'.format(namespace)).text
                        except:
                            pass

                         # prefix table
                        prefix_tree = rd_root.find('{}TABLE_prefix'.format(namespace))
                        if not prefix_tree:
                            continue

                        # -----   loop prefix  -----
                        for prefix_root in prefix_tree.findall('{}ROW_prefix'.format(namespace)):
                            # <ipprefix>10.1.1.1</ipprefix>
                            try:
                                prefix = prefix_root.find('{}ipprefix'.format(namespace)).text
                            except:
                                # <ipv6prefix>83::/112</ipv6prefix>
                                try:
                                    prefix = prefix_root.find('{}ipv6prefix'.format(namespace)).text
                                except:
                                    continue 

                            if 'prefix' not in sub_dict:
                                sub_dict['prefix'] = {}

                            if prefix not in sub_dict['prefix']:
                                sub_dict['prefix'][prefix] = {}

                             # path table
                            index_tree = prefix_root.find('{}TABLE_path'.format(namespace))
                            if not index_tree:
                                continue

                            # -----   loop path  -----
                            for index_root in index_tree.findall('{}ROW_path'.format(namespace)):
                                # neighbor
                                try:
                                    index = int(index_root.find('{}pathnr'.format(namespace)).text)
                                except:
                                    continue

                                if 'index' not in sub_dict['prefix'][prefix]:
                                    sub_dict['prefix'][prefix]['index'] = {}

                                if index not in sub_dict['prefix'][prefix]['index']:
                                    sub_dict['prefix'][prefix]['index'][index] = {}

                                # <status>valid</status>
                                sub_dict['prefix'][prefix]['index'][index]['status'] = \
                                    index_root.find('{}status'.format(namespace)).text

                                # <best>bestpath</best>
                                sub_dict['prefix'][prefix]['index'][index]['best_path'] = \
                                    False if 'none' in index_root.find('{}best'.format(namespace)).text \
                                    else True

                                # <type>internal</type>
                                sub_dict['prefix'][prefix]['index'][index]['type'] = \
                                    index_root.find('{}type'.format(namespace)).text

                                try:
                                    # <statuscode>*</statuscode>
                                    sub_dict['prefix'][prefix]['index'][index]['status_code'] = \
                                        index_root.find('{}statuscode'.format(namespace)).text

                                    # <bestcode>&gt;</bestcode>
                                    best_code = index_root.find('{}bestcode'.format(namespace)).text
                                    best_code = '>' if '&gt;' in best_code else best_code.strip()
                                    if best_code:
                                        sub_dict['prefix'][prefix]['index'][index]['best_code'] = best_code
                                       
                                    # <typecode>i</typecode>
                                    sub_dict['prefix'][prefix]['index'][index]['type_code'] = \
                                        index_root.find('{}typecode'.format(namespace)).text
                                except:
                                    pass

                                # <ipnexthop>19.0.101.1</ipnexthop>
                                try:
                                    sub_dict['prefix'][prefix]['index'][index]['nexthop'] = \
                                        index_root.find('{}ipnexthop'.format(namespace)).text
                                except:
                                    # <ipv6nexthop>50:1::1:101</ipv6nexthop>
                                    try:
                                        sub_dict['prefix'][prefix]['index'][index]['nexthop'] = \
                                            index_root.find('{}ipv6nexthop'.format(namespace)).text
                                    except:
                                        pass

                                # <inlabel>nolabel</inlabel>
                                sub_dict['prefix'][prefix]['index'][index]['in_label'] = \
                                    index_root.find('{}inlabel'.format(namespace)).text

                                # <outlabel>nolabel</outlabel>
                                sub_dict['prefix'][prefix]['index'][index]['out_label'] = \
                                    index_root.find('{}outlabel'.format(namespace)).text

                                # <vpn></vpn>
                                vpn = index_root.find('{}vpn'.format(namespace)).text
                                if vpn:
                                    sub_dict['prefix'][prefix]['index'][index]['vpn'] = vpn
                                    

                                # <hold_down></hold_down>
                                hold_down = index_root.find('{}hold_down'.format(namespace)).text
                                if hold_down:
                                    sub_dict['prefix'][prefix]['index'][index]['hold_down'] = hold_down


        return etree_dict