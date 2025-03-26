import os
#os.environ.setdefault("DJANGO_SETTINGS_MODULE", "planetstack.settings")
import string
import random
import hashlib
from datetime import datetime

from netaddr import IPAddress, IPNetwork
from planetstack import settings
from django.core import management
from core.models import * 
from planetstack.config import Config
try:
    from openstack.client import OpenStackClient
    from openstack.driver import OpenStackDriver
    has_openstack = True
except:
    has_openstack = False

manager_enabled = Config().api_nova_enabled


def random_string(size=6):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(size))

def require_enabled(callable):
    def wrapper(*args, **kwds):
        if manager_enabled and has_openstack:
            return callable(*args, **kwds)
        else:
            return None
    return wrapper


class OpenStackManager:

    def __init__(self, auth={}, caller=None):
        self.client = None
        self.driver = None
        self.caller = None
        self.has_openstack = has_openstack       
        self.enabled = manager_enabled

        if has_openstack and manager_enabled:
            if auth:
                try:
                    self.init_user(auth, caller)
                except:
                    # if this fails then it meanse the caller doesn't have a
                    # role at the slice's tenant. if the caller is an admin
                    # just use the admin client/manager.
                    if caller and caller.is_admin: 
                        self.init_admin()
                    else: raise
            else:
                self.init_admin()

    @require_enabled 
    def init_caller(self, caller, tenant):
        auth = {'username': caller.email,
                'password': hashlib.md5(caller.password).hexdigest()[:6],
                'tenant': tenant}
        self.client = OpenStackClient(**auth)
        self.driver = OpenStackDriver(client=self.client)
        self.caller = caller                 
    
    @require_enabled
    def init_admin(self, tenant=None):
        # use the admin credentials 
        self.client = OpenStackClient(tenant=tenant)
        self.driver = OpenStackDriver(client=self.client)
        self.caller = self.driver.admin_user
        self.caller.kuser_id = self.caller.id 

    @require_enabled
    def save_role(self, role):
        if not role.role:
            keystone_role = self.driver.create_role(role.role_type)
            role.role = keystone_role.id

    @require_enabled
    def delete_role(self, role):
        if role.role:
            self.driver.delete_role({'id': role.role})

    @require_enabled
    def save_key(self, key, name):
        key_fields = {'name': name,
                      'public_key': key}
        nova_key = self.driver.create_keypair(**key_fields)

    @require_enabled
    def delete_key(self, key):
        if key.nkey_id:
            self.driver.delete_keypair(key.nkey_id)

    @require_enabled
    def save_user(self, user):
        name = user.email[:user.email.find('@')]
        user_fields = {'name': name,
                       'email': user.email,
                       'password': hashlib.md5(user.password).hexdigest()[:6],
                       'enabled': True}
        if not user.kuser_id:
            keystone_user = self.driver.create_user(**user_fields)
            user.kuser_id = keystone_user.id
        else:
            self.driver.update_user(user.kuser_id, user_fields)     

        if user.site:
            self.driver.add_user_role(user.kuser_id, user.site.tenant_id, 'user')
            if user.is_admin:
                self.driver.add_user_role(user.kuser_id, user.site.tenant_id, 'admin')
            else:
                # may have admin role so attempt to remove it
                self.driver.delete_user_role(user.kuser_id, user.site.tenant_id, 'admin')

        if user.public_key:
            self.init_caller(user, user.site.login_base)
            self.save_key(user.public_key, user.keyname)
            self.init_admin()

        user.save()
        user.enacted = datetime.now()
        user.save(update_fields=['enacted'])
  
    @require_enabled
    def delete_user(self, user):
        if user.kuser_id:
            self.driver.delete_user(user.kuser_id)        
    
    @require_enabled
    def save_site(self, site, add_role=True):
        if not site.tenant_id:
            tenant = self.driver.create_tenant(tenant_name=site.login_base,
                                               description=site.name,
                                               enabled=site.enabled)
            site.tenant_id = tenant.id
            # give caller an admin role at the tenant they've created
            self.driver.add_user_role(self.caller.kuser_id, tenant.id, 'admin')

        # update the record
        if site.id and site.tenant_id:
            self.driver.update_tenant(site.tenant_id,
                                      description=site.name,
                                      enabled=site.enabled)

        # commit the updated record
        site.save()
        site.enacted = datetime.now()
        site.save(update_fields=['enacted']) # enusre enacted > updated  
        

    @require_enabled
    def delete_site(self, site):
        if site.tenant_id:
            self.driver.delete_tenant(site.tenant_id)
               
    @require_enabled
    def save_site_privilege(self, site_priv):
        if site_priv.user.kuser_id and site_priv.site.tenant_id:
            self.driver.add_user_role(site_priv.user.kuser_id,
                                      site_priv.site.tenant_id,
                                      site_priv.role.role_type)
        site_priv.enacted = datetime.now()
        site_priv.save(update_fields=['enacted'])

    
    @require_enabled
    def delete_site_privilege(self, site_priv):
        self.driver.delete_user_role(site_priv.user.kuser_id, 
                                     site_priv.site.tenant_id, 
                                     site_priv.role.role_type)

    @require_enabled
    def save_slice(self, slice):
        if not slice.tenant_id:
            nova_fields = {'tenant_name': slice.name,
                   'description': slice.description,
                   'enabled': slice.enabled}
            tenant = self.driver.create_tenant(**nova_fields)
            slice.tenant_id = tenant.id

            # give caller an admin role at the tenant they've created
            self.driver.add_user_role(self.caller.kuser_id, tenant.id, 'admin')

            # refresh credentials using this tenant
            self.driver.shell.connect(username=self.driver.shell.keystone.username,
                                      password=self.driver.shell.keystone.password,
                                      tenant=tenant.name)

            # create network
            network = self.driver.create_network(slice.name)
            slice.network_id = network['id']

            # create router
            router = self.driver.create_router(slice.name)
            slice.router_id = router['id']

            # create subnet
            next_subnet = self.get_next_subnet()
            cidr = str(next_subnet.cidr)
            ip_version = next_subnet.version
            start = str(next_subnet[2])
            end = str(next_subnet[-2]) 
            subnet = self.driver.create_subnet(name=slice.name,
                                               network_id = network['id'],
                                               cidr_ip = cidr,
                                               ip_version = ip_version,
                                               start = start,
                                               end = end)
            slice.subnet_id = subnet['id']
            # add subnet as interface to slice's router
            self.driver.add_router_interface(router['id'], subnet['id'])
            # add external route
            self.driver.add_external_route(subnet)


        if slice.id and slice.tenant_id:
            self.driver.update_tenant(slice.tenant_id,
                                      description=slice.description,
                                      enabled=slice.enabled)   

        slice.save()
        slice.enacted = datetime.now()
        slice.save(update_fields=['enacted']) 

    @require_enabled
    def delete_slice(self, slice):
        if slice.tenant_id:
            self._delete_slice(slice.tenant_id, slice.network_id, 
                               slice.router_id, slice.subnet_id)
    @require_enabled
    def _delete_slice(self, tenant_id, network_id, router_id, subnet_id):
        self.driver.delete_router_interface(slice.router_id, slice.subnet_id)
        self.driver.delete_subnet(slice.subnet_id)
        self.driver.delete_router(slice.router_id)
        self.driver.delete_network(slice.network_id)
        self.driver.delete_tenant(slice.tenant_id)
        # delete external route
        subnet = None
        subnets = self.driver.shell.quantum.list_subnets()['subnets']
        for snet in subnets:
            if snet['id'] == slice.subnet_id:
                subnet = snet
        if subnet:
            self.driver.delete_external_route(subnet) 

    
    @require_enabled
    def save_slice_membership(self, slice_memb):
        if slice_memb.user.kuser_id and slice_memb.slice.tenant_id:
            self.driver.add_user_role(slice_memb.user.kuser_id,
                                      slice_memb.slice.tenant_id,
                                      slice_memb.role.role_type)
        slice_memb.enacted = datetime.now()
        slice_memb.save(update_fields=['enacted'])


    @require_enabled
    def delete_slice_membership(self, slice_memb):
        self.driver.delete_user_role(slice_memb.user.kuser_id,
                                     slice_memb.slice.tenant_id,
                                     slice_memb.role.role_type)


    @require_enabled
    def get_next_subnet(self):
        # limit ourself to 10.0.x.x for now
        valid_subnet = lambda net: net.startswith('10.0')  
        subnets = self.driver.shell.quantum.list_subnets()['subnets']
        ints = [int(IPNetwork(subnet['cidr']).ip) for subnet in subnets \
                if valid_subnet(subnet['cidr'])] 
        ints.sort()
        last_ip = IPAddress(ints[-1])
        last_network = IPNetwork(str(last_ip) + "/24")
        next_network = IPNetwork(str(IPAddress(last_network) + last_network.size) + "/24")
        return next_network

    @require_enabled
    def save_subnet(self, subnet):    
        if not subnet.subnet_id:
            quantum_subnet = self.driver.create_subnet(name= subnet.slice.name,
                                          network_id=subnet.slice.network_id,
                                          cidr_ip = subnet.cidr,
                                          ip_version=subnet.ip_version,
                                          start = subnet.start,
                                          end = subnet.end)
            subnet.subnet_id = quantum_subnet['id']
            # add subnet as interface to slice's router
            self.driver.add_router_interface(subnet.slice.router_id, subnet.subnet_id)
            #add_route = 'route add -net %s dev br-ex gw 10.100.0.5' % self.cidr
            #commands.getstatusoutput(add_route)

    
    @require_enabled
    def delete_subnet(self, subnet):
        if subnet.subnet_id:
            self.driver.delete_router_interface(subnet.slice.router_id, subnet.subnet_id)
            self.driver.delete_subnet(subnet.subnet_id)
            #del_route = 'route del -net %s' % self.cidr
            #commands.getstatusoutput(del_route)

    @require_enabled
    def save_sliver(self, sliver):
        if not sliver.instance_id:
            slice_memberships = SliceMembership.objects.filter(slice=sliver.slice)
            pubkeys = [sm.user.public_key for sm in slice_memberships if sm.user.public_key != null]
            pubkeys.append(sliver.creator.public_key) 
            instance = self.driver.spawn_instance(name=sliver.name,
                                   key_name = sliver.creator.keyname,
                                   image_id = sliver.image.image_id,
                                   hostname = sliver.node.name,
                                   pubkeys = pubkeys )
            sliver.instance_id = instance.id
            sliver.instance_name = getattr(instance, 'OS-EXT-SRV-ATTR:instance_name')

        if sliver.instance_id and ("numberCores" in sliver.changed_fields):
            self.driver.update_instance_metadata(sliver.instance_id, {"cpu_cores": str(sliver.numberCores)})

        sliver.save()
        sliver.enacted = datetime.now()
        sliver.save(update_fields=['enacted'])

    @require_enabled
    def delete_sliver(self, sliver):
        if sliver.instance_id:
            self.driver.destroy_instance(sliver.instance_id) 
    

    def refresh_nodes(self):
        # collect local nodes
        nodes = Node.objects.all()
        nodes_dict = {}
        for node in nodes:
            if 'viccidev10' not in node.name:
                nodes_dict[node.name] = node 
        
        deployment = Deployment.objects.filter(name='VICCI')[0]
        login_bases = ['princeton', 'stanford', 'gt', 'uw', 'mpisws']
        sites = Site.objects.filter(login_base__in=login_bases)
        # collect nova nodes:
        compute_nodes = self.client.nova.hypervisors.list()

        compute_nodes_dict = {}
        for compute_node in compute_nodes:
            compute_nodes_dict[compute_node.hypervisor_hostname] = compute_node

        # add new nodes:
        new_node_names = set(compute_nodes_dict.keys()).difference(nodes_dict.keys())
        i = 0
        max = len(sites)
        for name in new_node_names:
            if i == max:
                i = 0
            site = sites[i]
            node = Node(name=compute_nodes_dict[name].hypervisor_hostname,
                        site=site,
                        deployment=deployment)
            node.save()
            i+=1

        # remove old nodes
        old_node_names = set(nodes_dict.keys()).difference(compute_nodes_dict.keys())
        Node.objects.filter(name__in=old_node_names).delete()

    def refresh_images(self):
        from core.models.image import Image
        # collect local images
        images = Image.objects.all()
        images_dict = {}    
        for image in images:
            images_dict[image.name] = image

        # collect glance images
        glance_images = self.client.glance.get_images()
        glance_images_dict = {}
        for glance_image in glance_images:
            glance_images_dict[glance_image['name']] = glance_image

        # add new images
        new_image_names = set(glance_images_dict.keys()).difference(images_dict.keys())
        for name in new_image_names:
            image = Image(image_id=glance_images_dict[name]['id'],
                          name=glance_images_dict[name]['name'],
                          disk_format=glance_images_dict[name]['disk_format'],
                          container_format=glance_images_dict[name]['container_format'])
            image.save()

        # remove old images
        old_image_names = set(images_dict.keys()).difference(glance_images_dict.keys())
        Image.objects.filter(name__in=old_image_names).delete()


