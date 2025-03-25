# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2015 Intel Corporation.
# Copyright 2015 Isaku Yamahata <isaku.yamahata at intel com>
#                               <isaku.yamahata at gmail com>
# All Rights Reserved.
#
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
#
# @author: Isaku Yamahata, Intel Corporation.
# shamelessly many codes are stolen from gbp simplechain_driver.py

import sys
import time
import yaml

from heatclient import client as heat_client
from heatclient import exc as heatException
from keystoneclient.v2_0 import client as ks_client
from oslo_config import cfg

from tacker.common import log
from tacker.extensions import vnfm
from tacker.openstack.common import jsonutils
from tacker.openstack.common import log as logging
from tacker.vm.drivers import abstract_driver


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
OPTS = [
    cfg.StrOpt('heat_uri',
               default='http://localhost:8004/v1',
               help=_("Heat server address to create services "
                      "specified in the service chain.")),
    cfg.IntOpt('stack_retries',
               default=10,
               help=_("Number of attempts to retry for stack deletion")),
    cfg.IntOpt('stack_retry_wait',
               default=5,
               help=_("Wait time between two successive stack delete "
                      "retries")),
]
CONF.register_opts(OPTS, group='servicevm_heat')
STACK_RETRIES = cfg.CONF.servicevm_heat.stack_retries
STACK_RETRY_WAIT = cfg.CONF.servicevm_heat.stack_retry_wait

HEAT_TEMPLATE_BASE = """
heat_template_version: 2013-05-23
"""


class DeviceHeat(abstract_driver.DeviceAbstractDriver):

    """Heat driver of hosting device."""

    def __init__(self):
        super(DeviceHeat, self).__init__()

    def get_type(self):
        return 'heat'

    def get_name(self):
        return 'heat'

    def get_description(self):
        return 'Heat infra driver'

    @log.log
    def create_device_template_pre(self, plugin, context, device_template):
        device_template_dict = device_template['device_template']
        vnfd_yaml = device_template_dict['attributes'].get('vnfd')
        if vnfd_yaml is None:
            return

        vnfd_dict = yaml.load(vnfd_yaml)
        KEY_LIST = (('name', 'template_name'), ('description', 'description'))

        device_template_dict.update(
            dict((key, vnfd_dict[vnfd_key]) for (key, vnfd_key) in KEY_LIST
                 if ((not key in device_template_dict or
                      device_template_dict[key] == '') and
                     vnfd_key in vnfd_dict and
                     vnfd_dict[vnfd_key] != '')))

        service_types = vnfd_dict.get('service_properties', {}).get('type', [])
        if service_types:
            device_template_dict.setdefault('service_types', []).extend(
                [{'service_type': service_type}
                 for service_type in service_types])
        for vdu in vnfd_dict.get('vdus', {}).values():
            mgmt_driver = vdu.get('mgmt_driver')
            if mgmt_driver:
                device_template_dict['mgmt_driver'] = mgmt_driver
        LOG.debug(_('device_template %s'), device_template)

    @log.log
    def _update_params(self, original, paramvalues, match=False):
        for key, value in original.iteritems():
            if not isinstance(value, dict) or 'get_input' not in str(value):
                pass
            elif isinstance(value, dict):
                if not match:
                    if key in paramvalues and 'param' in paramvalues[key]:
                        self._update_params(value, paramvalues[key]['param'],
                                            True)
                    elif key in paramvalues:
                        self._update_params(value, paramvalues[key], False)
                    else:
                        LOG.debug('Key missing Value: %s', key)
                        raise vnfm.InputValuesMissing()
                elif 'get_input' in value:
                    if value['get_input'] in paramvalues:
                        original[key] = paramvalues[value['get_input']]
                    else:
                        LOG.debug('Key missing Value: %s', key)
                        raise vnfm.InputValuesMissing()
                else:
                    self._update_params(value, paramvalues, True)

    @log.log
    def _process_parameterized_input(self, dev_attrs, vnfd_dict):
        param_vattrs_yaml = dev_attrs.pop('param_values', None)
        if param_vattrs_yaml:
            try:
                param_vattrs_dict = yaml.load(param_vattrs_yaml)
                LOG.debug('param_vattrs_yaml', param_vattrs_dict)
            except Exception as e:
                LOG.debug("Not Well Formed: %s", str(e))
                raise vnfm.ParamYAMLNotWellFormed(
                    error_msg_details=str(e))
            else:
                self._update_params(vnfd_dict, param_vattrs_dict)
        else:
            raise vnfm.ParamYAMLInputMissing()

    @log.log
    def _process_vdu_network_interfaces(self, vdu_id, vdu_dict, properties,
                                        template_dict):
        def make_port_dict():
            port_dict = {
                'type': 'OS::Neutron::Port',
                'properties': {
                    'port_security_enabled': False
                }
            }
            port_dict['properties'].setdefault('fixed_ips', [])
            return port_dict

        def make_mgmt_outputs_dict(port):
            mgmt_ip = 'mgmt_ip-%s' % vdu_id
            outputs_dict[mgmt_ip] = {
                'description': 'management ip address',
                'value': {
                    'get_attr': [port, 'fixed_ips',
                                 0, 'ip_address']
                }
            }

        def handle_port_creation(network_param, ip_list=[],
                                 mgmt_port=False):
            port = '%s-%s-port' % (vdu_id, network_param['network'])
            port_dict = make_port_dict()
            if mgmt_port:
                make_mgmt_outputs_dict(port)
            for ip in ip_list:
                port_dict['properties']['fixed_ips'].append({"ip_address": ip})
            port_dict['properties'].update(network_param)
            template_dict['resources'][port] = port_dict
            return port

        networks_list = []
        outputs_dict = {}
        template_dict['outputs'] = outputs_dict
        properties['networks'] = networks_list
        for network_param in vdu_dict[
                'network_interfaces'].values():
            port = None
            if 'addresses' in network_param:
                ip_list = network_param.pop('addresses', [])
                if not isinstance(ip_list, list):
                    raise vnfm.IPAddrInvalidInput()
                mgmt_flag = network_param.pop('management', False)
                port = handle_port_creation(network_param, ip_list, mgmt_flag)
            if network_param.pop('management', False):
                port = handle_port_creation(network_param, [], True)
            if port is not None:
                network_param = {
                    'port': {'get_resource': port}
                }
            networks_list.append(network_param)

    @log.log
    def create(self, plugin, context, device):
        LOG.debug(_('device %s'), device)
        heatclient_ = HeatClient(context)
        attributes = device['device_template']['attributes'].copy()
        vnfd_yaml = attributes.pop('vnfd', None)
        fields = dict((key, attributes.pop(key)) for key
                      in ('stack_name', 'template_url', 'template')
                      if key in attributes)
        for key in ('files', 'parameters'):
            if key in attributes:
                fields[key] = jsonutils.loads(attributes.pop(key))

        # overwrite parameters with given dev_attrs for device creation
        dev_attrs = device['attributes'].copy()
        config_yaml = dev_attrs.pop('config', None)
        fields.update(dict((key, dev_attrs.pop(key)) for key
                      in ('stack_name', 'template_url', 'template')
                      if key in dev_attrs))
        for key in ('files', 'parameters'):
            if key in dev_attrs:
                fields.setdefault(key, {}).update(
                    jsonutils.loads(dev_attrs.pop(key)))

        LOG.debug('vnfd_yaml %s', vnfd_yaml)
        if vnfd_yaml is not None:
            assert 'template' not in fields
            assert 'template_url' not in fields
            template_dict = yaml.load(HEAT_TEMPLATE_BASE)
            outputs_dict = {}
            template_dict['outputs'] = outputs_dict

            vnfd_dict = yaml.load(vnfd_yaml)
            LOG.debug('vnfd_dict %s', vnfd_dict)

            if 'get_input' in vnfd_yaml:
                self._process_parameterized_input(dev_attrs, vnfd_dict)

            KEY_LIST = (('description', 'description'),
                        )
            for (key, vnfd_key) in KEY_LIST:
                if vnfd_key in vnfd_dict:
                    template_dict[key] = vnfd_dict[vnfd_key]

            for vdu_id, vdu_dict in vnfd_dict.get('vdus', {}).items():
                template_dict.setdefault('resources', {})[vdu_id] = {
                    "type": "OS::Nova::Server"
                }
                resource_dict = template_dict['resources'][vdu_id]
                KEY_LIST = (('image', 'vm_image'),
                            ('flavor', 'instance_type'))
                resource_dict['properties'] = {}
                properties = resource_dict['properties']
                for (key, vdu_key) in KEY_LIST:
                    properties[key] = vdu_dict[vdu_key]
                if 'network_interfaces' in vdu_dict:
                    self._process_vdu_network_interfaces(vdu_id, vdu_dict,
                                                         properties,
                                                         template_dict)
                if 'user_data' in vdu_dict and 'user_data_format' in vdu_dict:
                    properties['user_data_format'] = vdu_dict[
                        'user_data_format']
                    properties['user_data'] = vdu_dict['user_data']
                elif 'user_data' in vdu_dict or 'user_data_format' in vdu_dict:
                    raise vnfm.UserDataFormatNotFound()
                if ('placement_policy' in vdu_dict and
                    'availability_zone' in vdu_dict['placement_policy']):
                    properties['availability_zone'] = vdu_dict[
                        'placement_policy']['availability_zone']
                if 'config' in vdu_dict:
                    properties['config_drive'] = True
                    metadata = properties.setdefault('metadata', {})
                    metadata.update(vdu_dict['config'])
                    for key, value in metadata.items():
                        metadata[key] = value[:255]

                # monitoring_policy = vdu_dict.get('monitoring_policy', None)
                # failure_policy = vdu_dict.get('failure_policy', None)

                # to pass necessary parameters to plugin upwards.
                for key in ('monitoring_policy', 'failure_policy',
                            'service_type'):
                    if key in vdu_dict:
                        device.setdefault(
                            'attributes', {})[key] = vdu_dict[key]

            if config_yaml is not None:
                config_dict = yaml.load(config_yaml)
                resources = template_dict.setdefault('resources', {})
                for vdu_id, vdu_dict in config_dict.get('vdus', {}).items():
                    if vdu_id not in resources:
                        continue
                    config = vdu_dict.get('config', None)
                    if not config:
                        continue
                    properties = resources[vdu_id].setdefault('properties', {})
                    properties['config_drive'] = True
                    metadata = properties.setdefault('metadata', {})
                    metadata.update(config)
                    for key, value in metadata.items():
                        metadata[key] = value[:255]

            heat_template_yaml = yaml.dump(template_dict)
            fields['template'] = heat_template_yaml
            if not device['attributes'].get('heat_template'):
                device['attributes']['heat_template'] = heat_template_yaml

        if 'stack_name' not in fields:
            name = (__name__ + '_' + self.__class__.__name__ + '-' +
                    device['id'])
            if device['attributes'].get('failure_count'):
                name += ('-%s') % str(device['attributes']['failure_count'])
            fields['stack_name'] = name

        # service context is ignored
        LOG.debug(_('service_context: %s'), device.get('service_context', []))

        LOG.debug(_('fields: %s'), fields)
        LOG.debug(_('template: %s'), fields['template'])
        stack = heatclient_.create(fields)
        return stack['stack']['id']

    def create_wait(self, plugin, context, device_dict, device_id):
        heatclient_ = HeatClient(context)

        stack = heatclient_.get(device_id)
        status = stack.stack_status
        stack_retries = STACK_RETRIES
        while status == 'CREATE_IN_PROGRESS' and stack_retries > 0:
            time.sleep(STACK_RETRY_WAIT)
            try:
                stack = heatclient_.get(device_id)
            except Exception:
                LOG.exception(_("Device Instance cleanup may not have "
                                "happened because Heat API request failed "
                                "while waiting for the stack %(stack)s to be "
                                "deleted"), {'stack': device_id})
                break
            status = stack.stack_status
            LOG.debug(_('status: %s'), status)
            stack_retries = stack_retries - 1

        LOG.debug(_('stack status: %(stack)s %(status)s'),
                  {'stack': str(stack), 'status': status})
        if stack_retries == 0:
            LOG.warn(_("Resource creation is"
                       " not completed within %(wait)s seconds as "
                       "creation of Stack %(stack)s is not completed"),
                     {'wait': (STACK_RETRIES * STACK_RETRY_WAIT),
                      'stack': device_id})
        if status != 'CREATE_COMPLETE':
            raise vnfm.DeviceCreateWaitFailed(device_id=device_id)
        outputs = stack.outputs
        LOG.debug(_('outputs %s'), outputs)
        PREFIX = 'mgmt_ip-'
        mgmt_ips = dict((output['output_key'][len(PREFIX):],
                         output['output_value'])
                        for output in outputs
                        if output.get('output_key', '').startswith(PREFIX))
        if mgmt_ips:
            device_dict['mgmt_url'] = jsonutils.dumps(mgmt_ips)

    @log.log
    def update(self, plugin, context, device_id, device_dict, device):
        # checking if the stack exists at the moment
        heatclient_ = HeatClient(context)
        heatclient_.get(device_id)

        # update config attribute
        config_yaml = device_dict.get('attributes', {}).get('config', '')
        update_yaml = device['device'].get('attributes', {}).get('config', '')
        LOG.debug('yaml orig %(orig)s update %(update)s',
                  {'orig': config_yaml, 'update': update_yaml})
        config_dict = yaml.load(config_yaml) or {}
        update_dict = yaml.load(update_yaml)
        if not update_dict:
            return

        @log.log
        def deep_update(orig_dict, new_dict):
            for key, value in new_dict.items():
                if isinstance(value, dict):
                    if key in orig_dict and isinstance(orig_dict[key], dict):
                        deep_update(orig_dict[key], value)
                        continue

                orig_dict[key] = value

        LOG.debug('dict orig %(orig)s update %(update)s',
                  {'orig': config_dict, 'update': update_dict})
        deep_update(config_dict, update_dict)
        LOG.debug('dict new %(new)s update %(update)s',
                  {'new': config_dict, 'update': update_dict})
        new_yaml = yaml.dump(config_dict)
        device_dict.setdefault('attributes', {})['config'] = new_yaml

    def update_wait(self, plugin, context, device_id):
        # do nothing but checking if the stack exists at the moment
        heatclient_ = HeatClient(context)
        heatclient_.get(device_id)

    def delete(self, plugin, context, device_id):
        heatclient_ = HeatClient(context)
        heatclient_.delete(device_id)

    @log.log
    def delete_wait(self, plugin, context, device_id):
        heatclient_ = HeatClient(context)

        stack = heatclient_.get(device_id)
        status = stack.stack_status
        stack_retries = STACK_RETRIES
        while (status == 'DELETE_IN_PROGRESS' and stack_retries > 0):
            time.sleep(STACK_RETRY_WAIT)
            try:
                stack = heatclient_.get(device_id)
            except heatException.HTTPNotFound:
                return
            except Exception:
                LOG.exception(_("Device Instance cleanup may not have "
                                "happened because Heat API request failed "
                                "while waiting for the stack %(stack)s to be "
                                "deleted"), {'stack': device_id})
                break
            status = stack.stack_status
            stack_retries = stack_retries - 1

        if stack_retries == 0:
            LOG.warn(_("Resource cleanup for device is"
                       " not completed within %(wait)s seconds as "
                       "deletion of Stack %(stack)s is not completed"),
                     {'wait': (STACK_RETRIES * STACK_RETRY_WAIT),
                      'stack': device_id})
        if status != 'DELETE_COMPLETE':
            LOG.warn(_("device (%(device_id)d) deletion is not completed. "
                       "%(stack_status)s"),
                     {'device_id': device_id, 'stack_status': status})

    @log.log
    def attach_interface(self, plugin, context, device_id, port_id):
        raise NotImplementedError()

    @log.log
    def dettach_interface(self, plugin, context, device_id, port_id):
        raise NotImplementedError()


class HeatClient:
    def __init__(self, context, password=None):
        # context, password are unused
        auth_url = CONF.keystone_authtoken.auth_uri + '/v2.0'
        authtoken = CONF.keystone_authtoken
        kc = ks_client.Client(
            tenant_name=authtoken.project_name,
            username=authtoken.username,
            password=authtoken.password,
            auth_url=auth_url)
        token = kc.service_catalog.get_token()

        api_version = "1"
        endpoint = "%s/%s" % (cfg.CONF.servicevm_heat.heat_uri,
                              token['tenant_id'])
        kwargs = {
            'token': token['id'],
            'tenant_name': authtoken.project_name,
            'username': authtoken.username,
        }
        self.client = heat_client.Client(api_version, endpoint, **kwargs)
        self.stacks = self.client.stacks

    def create(self, fields):
        fields = fields.copy()
        fields.update({
            'timeout_mins': 10,
            'disable_rollback': True})
        if 'password' in fields.get('template', {}):
            fields['password'] = fields['template']['password']

        try:
            return self.stacks.create(**fields)
        except heatException.HTTPException:
            type_, value, tb = sys.exc_info()
            raise vnfm.HeatClientException(msg=value)

    def delete(self, stack_id):
        try:
            self.stacks.delete(stack_id)
        except heatException.HTTPNotFound:
            LOG.warn(_("Stack %(stack)s created by service chain driver is "
                       "not found at cleanup"), {'stack': stack_id})

    def get(self, stack_id):
        return self.stacks.get(stack_id)
