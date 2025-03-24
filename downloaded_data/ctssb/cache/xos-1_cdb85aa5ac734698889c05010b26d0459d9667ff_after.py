from plstackapi.planetstack.config import Config
from plstackapi.openstack.client import OpenStackClient

class OpenStackDriver:

    def __init__(self, config = None, client=None): 
        if config:
            self.config = Config(config)
        else:
            self.config = Config() 

        self.admin_client = OpenStackClient()
        self.admin_user = self.admin_client.keystone.users.find(name=self.admin_client.keystone.username)

        if client:
            self.shell = client
        else:
            self.shell = OpenStackClient()

    def create_role(self, name): 
        roles = self.shell.keystone.roles.findall(name=name)
        if not roles:
            role = self.shell.keystone.roles.create(name)
        else:
            role = roles[0] 
        return role

    def delete_role(self, filter):
        roles = self.shell.keystone.roles.findall(**filter)
        for role in roles:
            self.shell.keystone.roles.delete(role)
        return 1

    def create_tenant(self, tenant_name, enabled, description):
        """Create keystone tenant. Suggested fields: name, description, enabled"""  
        tenants = self.shell.keystone.tenants.findall(name=tenant_name)
        if not tenants:
            fields = {'tenant_name': tenant_name, 'enabled': enabled, 
                      'description': description}  
            tenant = self.shell.keystone.tenants.create(**fields)
        else:
            tenant = tenants[0]

        # always give the admin user the admin role to any tenant created 
        # by the driver. 
        self.add_user_role(self.admin_user.id, tenant.id, 'admin')
        return tenant

    def update_tenant(self, id, **kwds):
        return self.shell.keystone.tenants.update(id, **kwds)

    def delete_tenant(self, id):
        tenants = self.shell.keystone.tenants.findall(id=id)
        for tenant in tenants:
            self.shell.keystone.tenants.delete(tenant)
        return 1

    def create_user(self, name, email, password, enabled):
        users = self.shell.keystone.users.findall(email=email)
        if not users:
            fields = {'name': name, 'email': email, 'password': password,
                      'enabled': enabled}
            user = self.shell.keystone.users.create(**fields)
        else: 
            user = users[0]
        return user

    def delete_user(self, id):
        users = self.shell.keystone.users.findall(id=id)
        for user in users:
            self.shell.keystone.users.delete(user)
        return 1 

    def add_user_role(self, user_id, tenant_id, role_name):
        user = self.shell.keystone.users.find(id=user_id)
        tenant = self.shell.keystone.tenants.find(id=tenant_id)
        role = self.shell.keystone.roles.find(name=role_name)

        role_found = False
        user_roles = user.list_roles(tenant.id)
        for user_role in user_roles:
            if user_role.name == role.name:
                role_found = True
        if not role_found:
            tenant.add_user(user, role)

        return 1

    def delete_user_role(self, user_id, tenant_id, role_name):
        user = self.shell.keystone.users.find(id=user_id)
        tenant = self.shell.keystone.tenants.find(id=tenant_id)
        role = self.shell.keystone.roles.find(name=role_name)

        role_found = False
        user_roles = user.list_roles(tenant.id)
        for user_role in user_roles:
            if user_role.name == role.name:
                role_found = True
        if role_found:
            tenant.remove_user(user, role)

        return 1 

    def update_user(self, id, **kwds):
        return self.shell.keystone.users.update(id, **kwds)

    def create_router(self, name, set_gateway=True):
        routers = self.shell.quantum.list_routers(name=name)['routers']
        if routers:
            router = routers[0]
        else:
            router = self.shell.quantum.create_router({'router': {'name': name}})['router']
        # add router to external network
        if set_gateway:
            nets = self.shell.quantum.list_networks()['networks']
            for net in nets:
                if net['router:external'] == True: 
                    self.shell.quantum.add_gateway_router(router['id'],
                                                          {'network_id': net['id']})
        
        return router

    def delete_router(self, id):
        routers = self.shell.quantum.list_routers(id=id)['routers']
        for router in routers:
            self.shell.quantum.delete_router(router['id'])
            # remove router form external network
            #nets = self.shell.quantum.list_networks()['networks']
            #for net in nets:
            #    if net['router:external'] == True:
            #        self.shell.quantum.remove_gateway_router(router['id'])

    def add_router_interface(self, router_id, subnet_id):
        router = self.shell.quantum.show_router(router_id)['router']
        subnet = self.shell.quantum.show_subnet(subnet_id)['subnet']
        if router and subnet:
            self.shell.quantum.add_interface_router(router_id, {'subnet_id': subnet_id})

    def delete_router_interface(self, router_id, subnet_id):
        router = self.shell.quantum.show_router(router_id)
        subnet = self.shell.quantum.show_subnet(subnet_id)
        if router and subnet:
            self.shell.quantum.remove_interface_router(router_id, {'subnet_id': subnet_id})
 
    def create_network(self, name):
        nets = self.shell.quantum.list_networks(name=name)['networks']
        if nets: 
            net = nets[0]
        else:
            net = self.shell.quantum.create_network({'network': {'name': name}})['network']
        return net
 
    def delete_network(self, id):
        nets = self.shell.quantum.list_networks()['networks']
        for net in nets:
            if net['id'] == id:
                # delete_all ports
                self.delete_network_ports(net['id'])
                # delete all subnets:
                for subnet_id in net['subnets']:
                    self.delete_subnet(subnet_id)
                self.shell.quantum.delete_network(net['id'])
        return 1

    def delete_network_ports(self, network_id):
        ports = self.shell.quantum.list_ports()['ports']
        for port in ports:
            if port['network_id'] == network_id:
                self.shell.quantum.delete_port(port['id'])
        return 1         

    def delete_subnet_ports(self, subnet_id):
        ports = self.shell.quantum.list_ports()['ports']
        for port in ports:
            delete = False
            for fixed_ip in port['fixed_ips']:
                if fixed_ip['subnet_id'] == subnet_id:
                    delete=True
                    break
            if delete:
                self.shell.quantum.delete_port(port['id'])
        return 1
 
    def create_subnet(self, name, network_id, cidr_ip, ip_version, start, end):
        #nets = self.shell.quantum.list_networks(name=network_name)['networks']
        #if not nets:
        #    raise Exception, "No such network: %s" % network_name   
        #net = nets[0]

        subnet = None 
        subnets = self.shell.quantum.list_subnets()['subnets']
        for snet in subnets:
            if snet['cidr'] == cidr_ip and snet['network_id'] == network_id:
                subnet = snet
 
        if not subnet:
            allocation_pools = [{'start': start, 'end': end}]
            subnet = {'subnet': {'name': name,
                                 'network_id': network_id,
                                 'ip_version': ip_version,
                                 'cidr': cidr_ip,
                                 'dns_nameservers': ['8.8.8.8', '8.8.4.4'],
                                 'allocation_pools': allocation_pools}}          
            subnet = self.shell.quantum.create_subnet(subnet)['subnet']

        # TODO: Add route to external network
        # e.g. #  route add -net 10.0.3.0/24 dev br-ex gw 10.100.0.5 
        return subnet

    def update_subnet(self, id, fields):
        return self.shell.quantum.update_subnet(id, fields)

    def delete_subnet(self, id):
        #return self.shell.quantum.delete_subnet(id=id)
        # inefficient but fault tolerant
        subnets = self.shell.quantum.list_subnets()['subnets']
        for subnet in subnets:
            if subnet['id'] == id:
                self.delete_subnet_ports(subnet['id'])
                self.shell.quantum.delete_subnet(id)
        return
    
    def create_keypair(self, name, key):
        keys = self.shell.nova.keypairs.findall(name=name)
        if keys:
            key = keys[0]
        else:
            key = self.shell.nova.keypairs.create(name=name, public_key=key)
        return key

    def delete_keypair(self, id):
        keys = self.shell.nova.keypairs.findall(id=id)
        for key in keys:
            self.shell.nova.keypairs.delete(key) 
        return 1 

    def spawn_instance(self, name, key_name=None, hostname=None, image_id=None, security_group=None, pubkeys=[]):
        flavor_name = self.config.nova_default_flavor
        flavor = self.shell.nova.flavors.find(name=flavor_name)
        #if not image:
        #    image = self.config.nova_default_imave
        if not security_group:
            security_group = self.config.nova_default_security_group 

        #authorized_keys = "\n".join(pubkeys)
        #files = {'/root/.ssh/authorized_keys': authorized_keys}
        files = {}
       
        hints = {}
        availability_zone = None
        if hostname:
            availability_zone = 'nova:%s' % hostname
        server = self.shell.nova.servers.create(
                                            name=name,
                                            key_name = key_name,
                                            flavor=flavor.id,
                                            image=image_id,
                                            security_group = security_group,
                                            files=files,
                                            scheduler_hints=hints,
                                            availability_zone=availability_zone)
        return server
          
    def destroy_instance(self, id):
        servers = self.shell.nova.servers.findall(id=id)
        for server in servers:
            self.shell.nova.servers.delete(server)

    def update_instance_metadata(self, id, metadata):
        servers = self.shell.nova.servers.findall(id=id)
        for server in servers:
            self.shell.nova.servers.set_meta(server, metadata)
            # note: set_meta() returns a broken Server() object. Don't try to
            # print it in the shell or it will fail in __repr__.

    def delete_instance_metadata(self, id, metadata):
        # note: metadata is a dict. Only the keys matter, not the values.
        servers = self.shell.nova.servers.findall(id=id)
        for server in servers:
            self.shell.nova.servers.delete_meta(server, metadata)

