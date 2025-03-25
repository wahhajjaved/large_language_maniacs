"""Helper functions related to the creation and destruction of virtual machines and instances
"""

from cfme.cloud.provider import get_from_config as get_cloud_from_config
from cfme.exceptions import UnknownProviderType
from cfme.infrastructure.provider import get_from_config as get_infra_from_config
from utils.log import logger
from utils.mgmt_system import RHEVMSystem, VMWareSystem, EC2System, OpenstackSystem


def deploy_template(provider_key, vm_name, template_name=None, timeout=900, **deploy_args):
    try:
        provider_crud = get_infra_from_config(provider_key)
    except UnknownProviderType:
        provider_crud = get_cloud_from_config(provider_key)
    mgmt = provider_crud.get_mgmt_system()
    data = provider_crud.get_yaml_data()

    deploy_args.update(vm_name=vm_name)
    if isinstance(mgmt, RHEVMSystem):
        if 'default_cluster' not in deploy_args:
            deploy_args.update(cluster_name=data['default_cluster'])
    elif isinstance(mgmt, VMWareSystem):
        pass
    elif isinstance(mgmt, EC2System):
        pass
    elif isinstance(mgmt, OpenstackSystem):
        if ('network_name' not in deploy_args) and data.get('network'):
            deploy_args.update(network_name=data['network'])
    else:
        raise Exception("Unsupported provider type: %s" % mgmt.__class__.__name__)

    if template_name is None:
        template_name = data['small_template']

    logger.info("Getting ready to deploy VM/instance %s from template %s on provider %s" %
        (vm_name, template_name, data['name']))
    try:
        logger.debug("Deploy args: " + str(deploy_args))
        vm_name = mgmt.deploy_template(template_name, timeout=timeout, **deploy_args)
        logger.info("Provisioned VM/instance %s" % vm_name)  # instance ID in case of EC2
    except Exception as e:
        logger.error('Could not provisioning VM/instance %s (%s)', vm_name, e)
        logger.info('Attempting cleanup on VM/instance %s', vm_name)
        try:
            if mgmt.does_vm_exist(vm_name):
                # Stop the vm first
                logger.warning('Destroying VM/instance %s', vm_name)
                if mgmt.delete_vm(vm_name):
                    logger.info('VM/instance %s destroyed', vm_name)
                else:
                    logger.error('Error destroying VM/instance %s', vm_name)
        except Exception as f:
            logger.error('Could not destroy VM/instance %s (%s)', vm_name, f)
        finally:
            raise e

    return vm_name
