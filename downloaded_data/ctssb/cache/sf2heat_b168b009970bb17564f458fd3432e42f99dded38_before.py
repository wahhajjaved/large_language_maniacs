import logging
import yaml
import os
import shutil

from hotsyntax.hot_template import HotTemplate
from hotsyntax.hot_resource import HotResource

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger('NSDTranslator')

TEMPLATE_ANSIBLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates/ansible')




class NSDTranslator(object):
    """ Invokes translation methods. """

    def __init__(self, nsd_data, output_dir=None, ansible=None):
        super(NSDTranslator, self).__init__()
        self.nsd_descriptors = nsd_data
        self.output_dir = output_dir
        self.ansbile = ansible
        self.ansbile_vars = {
            "template_path": "/tmp/app_template.yaml",
            "app_name": str(ansible["app_name"]) if "app_name" in ansible else "test_app",
            "cloud_config_name": str(ansible["cloud_config_name"]) if "cloud_config_name" in ansible else "cloud_config_name"
        }
        self.ansbile_configs = []
        self.hot_template = HotTemplate()
        log.debug('Initialized NSDTranslator')

    def translate(self):
        for vnfd_id in self.nsd_descriptors['vnfd']:
            self._translate_vnf(self.nsd_descriptors['vnfd'][vnfd_id])
        if self.output_dir is not None:
            if self.ansbile:
                self._write_ansible_playbook(self.hot_template)
            else:
                dstfile = open(self.output_dir, 'w') if isinstance(self.output_dir, str) else self.output_dir
                self.hot_template.export_yaml(dstfile)
        else:
            print self.hot_template.toYaml()

    def _translate_vnf(self, vnf_data):
        log.debug('_translate_vnf id: ' + vnf_data['vnfdId'])
        for vdu in vnf_data['vdu']:
            self._translate_vdu(vdu, vnf_data)
        for intVl in vnf_data['intVirtualLinkDesc']:
            self._translate_intVl(intVl, vnf_data)

    def _translate_vdu(self, vdu_data, vnf_data):
        log.debug('_translate_vdu id: %s', vdu_data['vduId'])
        resource_type = self._infer_resource_type(vdu_data['vduId'], vnf_data)
        log.debug('Resource type: %s', resource_type)
        resource_properties = self._get_properties_vdu(resource_type, vdu_data, vnf_data)
        log.debug('Resource prop: %s', resource_properties)
        new_hot_resource = HotResource(vdu_data['vduId'], resource_type, resource_properties)
        self.hot_template.add_resource(vdu_data['vduId'], new_hot_resource)

    def _translate_vnfExtCpd(self, extCpd, vnf_data):
        log.debug('_translate_vnfExtCpd id: %s', extCpd['cpdId'])
        resource_type = self._infer_resource_type(extCpd['cpdId'], vnf_data)
        log.debug('Resource type: %s', resource_type)
        new_hot_resource = self._get_neutron_provider_net(extCpd, vnf_data)
        return new_hot_resource

    def _translate_intVl(self, intVl, vnf_data):
        log.debug('_translate_intVl id: %s', intVl['virtualLinkDescId'])
        # find and get properties for subnet
        metadata_list = vnf_data['modifiableAttributes']['metadata']
        for metadata in metadata_list:
            if 'CPIPv4CIDR' in metadata:
                for prop in metadata['CPIPv4CIDR']:
                    if intVl['virtualLinkDescId'] in prop:
                        for k, cidr in enumerate(prop[intVl['virtualLinkDescId']]):
                            subnet_name = 'subnet_' + intVl['virtualLinkDescId'] + '_' + str(k)
                            sub_pro = {'cidr': str(cidr['cidr']), 'network': str(intVl['virtualLinkDescId'])}
                            neutron_subnet = self._get_subnet(subnet_name, sub_pro, vnf_data)
                            self.hot_template.add_resource(subnet_name, neutron_subnet)

    @staticmethod
    def _infer_resource_type(element_id, vnf_data):
        log.debug('_infer_resource_type from: %s', element_id)
        try:
            vnf_metadata = vnf_data['modifiableAttributes']['metadata']
            for meta in vnf_metadata:
                if 'types' in meta:
                    for type in meta['types']:
                        if element_id in type:
                            return type[element_id]
        except Exception as e:
            log.exception('_infer_resource_type exception ' + e)
        return None

    def _get_properties_vdu(self, resource_type, vdu_data, vnf_data):
        log.debug('_get_properties_vdu for %s, from %s', resource_type, vdu_data['vduId'])
        result = {}

        if resource_type == 'OS::Nova::Server':
            vdu_sw_img_dsc = vdu_data['swImageDesc']
            result['image'] = vdu_sw_img_dsc['swImage']
            user_data_ref = self._get_properties_from_vdu_add_prop('user_data', vdu_data)
            if user_data_ref:
                # "config_path": "/tmp/app_config.yaml"
                config_path = "/tmp/" + user_data_ref + ".yaml"
                var_name = 'config_path_' + str(len(self.ansbile_configs))
                self.ansbile_vars[var_name] = str(config_path)
                self.ansbile_configs.append({"name": str(user_data_ref), "var_name": str(var_name)})
                result['user_data'] = {"get_file": str(config_path)}
            result['user_data_format'] = "RAW"
            # OS::Nova::Flavor

            flavor_id = str(vnf_data['deploymentFlavour'][0]['flavourId'])
            flav_to_create = self._get_properties_from_metadata(flavor_id, "createVIMFlavor", vnf_data)
            print flav_to_create
            if 'createVIMFlavor' in flav_to_create and flav_to_create['createVIMFlavor'] is True:
                flavor_name = 'flavor_' + vdu_data['vduId']
                result['flavor'] = {'get_resource': str(flavor_name)}
                flavor_res = self._get_nova_flavor(flavor_name, vdu_data, vnf_data)
                self.hot_template.add_resource(flavor_name, flavor_res)
            else:
                result['flavor'] = flavor_id
            #  OS::Nova::KeyPair
            key_pair_name = 'key_' + vdu_data['vduId']
            result['key_name'] = {'get_resource': str(key_pair_name)}
            key_pair_res = self._get_nova_key_pair(key_pair_name, vdu_data, vnf_data)
            self.hot_template.add_resource(key_pair_name, key_pair_res)
            if 'intCpd' in vdu_data:
                result['networks'] = []
                for intcpd in vdu_data['intCpd']:
                    net = self._get_network_from_cpd(intcpd, vnf_data)
                    result['networks'].append(net)

        elif resource_type == 'OS::Neutron::Router':
            meta_prop = self._get_properties_from_metadata(vdu_data['vduId'], 'properties', vnf_data)
            result.update(meta_prop)
            if 'intCpd' in vdu_data:
                for intcpd in vdu_data['intCpd']:
                    nri = self._get_neutron_router_interface(vdu_data['vduId'], intcpd, vnf_data)
                    self.hot_template.add_resource('interf_' + intcpd['cpdId'], nri)

        return result

    def _get_network_from_cpd(self, intcpd, vnf_data):
        result = {}
        # FIXME generate port resource o full network resource
        neutron_port_name = 'port_' + intcpd['cpdId']
        result['port'] = {'get_resource': str(neutron_port_name)}
        neutron_port_res = self._get_neutron_port(intcpd, vnf_data)
        self.hot_template.add_resource(neutron_port_name, neutron_port_res)
        return result

    def _get_neutron_router_interface(self, router_id, intcpd, vnf_data):
        resource_type = 'OS::Neutron::RouterInterface'
        resource_prop = {'router': {'get_resource': str(router_id)}}
        neutron_port_name = 'port_' + intcpd['cpdId']
        neutron_port_res = self._get_neutron_port(intcpd, vnf_data)
        self.hot_template.add_resource(neutron_port_name, neutron_port_res)
        resource_prop['port'] = {'get_resource': str(neutron_port_name)}
        new_hot_resource = HotResource('interf_' + router_id, resource_type, resource_prop)
        return new_hot_resource

    def _get_neutron_port(self, intcpd, vnf_data):
        resource_type = 'OS::Neutron::Port'
        resource_prop = {}
        name = intcpd['cpdId']
        network_name = intcpd['intVirtualLinkDesc']

        extCpd = self._isIntCpd_conn_extCpd(intcpd, vnf_data)
        if extCpd:
            neutron_elem = self._translate_vnfExtCpd(extCpd, vnf_data)
        else:
            neutron_elem = self._get_neutron_net(network_name, vnf_data)
        self.hot_template.add_resource(network_name, neutron_elem)


        metadata_list = vnf_data['modifiableAttributes']['metadata']
        for metadata in metadata_list:
            if 'CPIPv4FixedIP' in metadata:
                for index, fixed_ip in enumerate(metadata['CPIPv4FixedIP']):

                    if name in fixed_ip:
                        if 'fixed_ips' not in resource_prop:
                            resource_prop['fixed_ips'] = []
                        resource_prop['fixed_ips'].append({'ip_address': str(fixed_ip[name])})
                        # print "SUBNET for cpid:", name, network_name
                        subnet_name = 'subnet_' + name + '_' + str(index)
                        # neutron_subnet = self._get_resource_subnet(subnet_name, intcpd, vnf_data)
                        # self.hot_template.add_resource(subnet_name, neutron_subnet)
            if 'properties' in metadata:
                for prop in metadata['properties']:
                    if name in prop:
                        meta_prop = dict(pair for d in prop[name] for pair in d.items())
                        resource_prop.update(meta_prop)
        if 'addressData' in intcpd:
            for addr in intcpd['addressData']:
                if 'l2AddressData' in addr:
                    resource_prop['mac_address'] = str(addr['l2AddressData'])
                if 'l3AddressData' in addr and addr['l3AddressData']['floatingIpActivated']:
                    if 'association' in addr['l3AddressData'] and addr['l3AddressData']['association']:
                        float_name = name + "_floating_ip_association"
                        neutron_floating_ip = self._get_floating_ip_association(float_name, intcpd, vnf_data)
                        self.hot_template.add_resource(float_name, neutron_floating_ip)
                    else:
                        float_name = name + "_floating_ip"
                        neutron_floating_ip = self._get_floating_ip(float_name, intcpd, vnf_data)
                        self.hot_template.add_resource(float_name, neutron_floating_ip)
        if 'network' in resource_prop:
            resource_prop['network']['get_resource'] = str(network_name)
        else:
            resource_prop['network'] = {'get_resource': str(network_name)}
        new_hot_resource = HotResource(name, resource_type, resource_prop)
        return new_hot_resource

    def _get_floating_ip_association(self, float_name, intcpd, vnf_data):
        resource_type = 'OS::Neutron::FloatingIPAssociation'
        resource_prop = {'port_id': {'get_resource': 'port_' + str(intcpd['cpdId']) }}
        meta_float_ip = self._get_properties_from_metadata(intcpd['cpdId'], 'CPIPv4FloatingIP', vnf_data)
        resource_prop.update({'floatingip_id': str(meta_float_ip['CPIPv4FloatingIP'])})
        meta_prop = self._get_properties_from_metadata(intcpd['cpdId'], 'properties', vnf_data)
        resource_prop.update(meta_prop)
        new_hot_resource = HotResource(float_name, resource_type, resource_prop)
        return new_hot_resource

    def _get_floating_ip(self, float_name, intcpd, vnf_data):
        resource_type = 'OS::Neutron::FloatingIP'
        resource_prop = {'port_id': {'get_resource':  'port_' + str(intcpd['cpdId'])}}
        meta_float_ip = self._get_properties_from_metadata(intcpd['cpdId'], 'CPIPv4FloatingIP', vnf_data)
        resource_prop.update({'floating_ip_address': str(meta_float_ip['CPIPv4FloatingIP'])})
        meta_prop = self._get_properties_from_metadata(float_name, 'properties', vnf_data)
        resource_prop.update(meta_prop)
        new_hot_resource = HotResource(float_name, resource_type, resource_prop)
        return new_hot_resource

    def _get_nova_flavor(self, name, vdu_data, vnf_data):
        resource_type = 'OS::Nova::Flavor'
        resource_prop = {'flavorid': str(vnf_data['deploymentFlavour'][0]['flavourId']), 'name': str(name),
                         'is_public': False}
        # virtualMemory and virtualCpu properties
        if 'virtualComputeDesc' in vdu_data and vdu_data['virtualComputeDesc'] is not None:
            for vcd in vnf_data['virtualComputeDesc']:
                if vcd['virtualComputeDescId'] == vdu_data['virtualComputeDesc']:
                    resource_prop['ram'] = int(vcd['virtualMemory']['virtualMemSize'])
                    resource_prop['vcpus'] = int(vcd['virtualCpu']['numVirtualCpu'])
        # virtualStorageDesc
        if 'virtualStorageDesc' in vdu_data and vdu_data['virtualStorageDesc'] is not None:
            for vsd in vnf_data['virtualStorageDesc']:
                if vsd['id'] == vdu_data['virtualStorageDesc']:
                    resource_prop['disk'] = str(vsd['sizeOfStorage'])
                    resource_prop['swap'] = 0
        new_hot_resource = HotResource(name, resource_type, resource_prop)
        return new_hot_resource

    def _get_nova_key_pair(self, name, vdu_data, vnf_data):
        resource_type = 'OS::Nova::KeyPair'
        resource_prop = {'name': str(name)}
        for prop in vdu_data['configurableProperties']['additionalVnfcConfigurableProperty']:
            if 'SSHPubKey' in prop:
                resource_prop['public_key'] = prop['SSHPubKey']
                break
        new_hot_resource = HotResource(name, resource_type, resource_prop)
        return new_hot_resource

    def _get_subnet(self, subnet_name, prop, vnf_data):
        resource_type = 'OS::Neutron::Subnet'
        resource_prop = {'name': subnet_name, 'network': {'get_resource': str(prop['network'])},
                         'cidr': str(prop['cidr'])}
        new_hot_resource = HotResource(subnet_name, resource_type, resource_prop)
        return new_hot_resource

    def _get_neutron_net(self, name, vnf_data):
        resource_type = 'OS::Neutron::Net'
        resource_prop = {'name': str(name)}
        new_hot_resource = HotResource(name, resource_type, resource_prop)
        return new_hot_resource

    def _get_neutron_provider_net(self, ext_cpd, vnf_data):
        resource_type = 'OS::Neutron::ProviderNet'
        resource_prop = {'name': str(ext_cpd['intVirtualLinkDesc'])}
        meta_pro = self._get_properties_from_metadata(ext_cpd['cpdId'], 'properties', vnf_data)
        resource_prop.update(meta_pro)
        new_hot_resource = HotResource(ext_cpd['intVirtualLinkDesc'], resource_type, resource_prop)
        return new_hot_resource

    @staticmethod
    def _get_properties_from_metadata(element_id, meta_name, vnf_data):
        metadata_list = vnf_data['modifiableAttributes']['metadata']
        for metadata in metadata_list:
            if meta_name in metadata:
                for prop in metadata[meta_name]:
                    if element_id in prop:
                        if isinstance(prop[element_id], list):
                            meta_prop = dict(pair for d in prop[element_id] for pair in d.items())
                            return meta_prop
                        else:
                            return {meta_name: str(prop[element_id])}
        return {}

    @staticmethod
    def _get_properties_from_vdu_add_prop(prop_name, vdu_data):
        for prop in vdu_data['configurableProperties']['additionalVnfcConfigurableProperty']:
            if prop_name in prop:
                return prop[prop_name]
        return

    @staticmethod
    def _isIntCpd_conn_extCpd(intcpd, vnf_data):
        intVirtualLinkDesc = intcpd['intVirtualLinkDesc']
        for extCpd in vnf_data['vnfExtCpd']:
            if extCpd['intVirtualLinkDesc'] == intVirtualLinkDesc:
                return extCpd
        return None

    @staticmethod
    def makedir_p(directory):
        """makedir_p(path)

        Works like mkdirs, except that check if the leaf exist.

        """
        if not os.path.isdir(directory):
            os.makedirs(directory)

    def _write_ansible_playbook(self, hot):
        try:
            # log.debug(os.path.abspath(__file__))
            log.debug(TEMPLATE_ANSIBLE_PATH)
            log.debug('Write Ansible playbook to %s', self.output_dir)
            create_task = [
                {"name": "Copy heat template",
                 "template": {"src": "stack.j2", "dest": "{{ template_path }}"}}
            ]

            # copy playbook dir tree
            shutil.rmtree(self.output_dir, ignore_errors=True)
            #self.makedir_p(self.output_dir)
            shutil.copytree(TEMPLATE_ANSIBLE_PATH, self.output_dir)

            self.makedir_p(os.path.join(self.output_dir, 'roles', 'create_app', 'templates'))

            # dump heat template in create_app/templates
            heat_path = os.path.join(self.output_dir, 'roles', 'create_app', 'templates', 'stack.j2')
            dstfile = open(heat_path, 'w')
            self.hot_template.export_yaml(dstfile)

            # dump each config script
            for conf in self.ansbile_configs:
                conf_path = os.path.join(self.output_dir, 'roles', 'create_app', 'templates', conf['name']+'.j2')
                conf_file = open(conf_path, 'w')
                conf_file.write(self.nsd_descriptors['resource'][conf['name']])
                conf_file.close()
                create_task.append({"name": "Copy config template",
                                    "template": {"src": str(conf['name'])+'.j2',
                                                 "dest": "{{ " + conf['var_name'] + " }}"}})

            # dump variables ansbile_vars
            self.makedir_p(os.path.join(self.output_dir, 'group_vars'))
            vars_path = os.path.join(self.output_dir, 'group_vars', 'all.yml')
            vars_file = open(vars_path, 'w')
            yaml.dump(self.ansbile_vars, vars_file, default_flow_style=False, explicit_start=True, width=float("inf"))

            create_task.append({"name": "Create new stack",
                                "command": "openstack --os-cloud {{ cloud_config_name }} stack create -t {{ template_path }} {{ app_name }}"})

            # dump task create
            create_path = os.path.join(self.output_dir, 'roles', 'create_app', 'tasks', 'main.yml')
            create_file = open(create_path, 'w')

            yaml.dump(create_task, create_file, default_flow_style=False, explicit_start=True, width=float("inf"))
        except Exception as e:
            log.exception(e)

