#!/usr/bin/env python

import os
import sys
import pyrax
import argparse


# Create a function to take care of the dns record creation
def create_dns(cdnsobj, fqdn, ip_address):

    # Add the domain record
    domains = cdnsobj.list()
    for domain in domains:
        if fqdn.endswith(domain.name):
            print "Found a matching domain: " + domain.name + " for fqdn: " \
                + fqdn
            recs = [{'type': 'A', 'name': fqdn, 'data': ip_address,
                    'ttl': 6000}]

            # Check if the record already exists and return it instead
            records = domain.list_records()
            for record in records:
                if record.name == fqdn and record.data == ip_address:
                    print "Record already exists. Skipping"
                    return 0

             # Add record if we made it this far and return from function
            print "Adding record: \n\t" + fqdn + "   IN  A  " + ip_address
            cdnsobj.add_records(domain, recs)
            return 0


# Check for an existing domain
def check_dns(cdnsobj, fqdn):

    # Add the domain record
    domains = cdnsobj.list()
    found_domain = 0
    for domain in domains:
        if fqdn.endswith(domain.name):
            found_domain = 1

    # Bounce if the domain doesn't exist
    if found_domain != 1:
        print "Domain for FQDN of " + fqdn + " doesn't exist for this account."
        sys.exit(1)


# Get the flavor id from the name
def get_flavor_from_id_or_name(csobj, given_flavor_value):

    flavors = csobj.flavors.list()
    flavor_id = ""
    for flavor in flavors:
        if flavor.id == given_flavor_value or \
           flavor.name == given_flavor_value:
            print "Found flavor with name of \"" + flavor.name + "\""
            flavor_id = flavor.id
    if flavor_id == "":
        print "\nFlavor with name or id of " + given_flavor_value + \
              " does not exist. Please use a flavor id or name from \
              the following available values:\n"
        for flavor in flavors:
            print "id: %s  =>  name: \"%s\"" % (flavor.id, flavor.name)
        sys.exit(1)
    return flavor_id


# Get the image id from the name
def get_image_from_id_or_name(csobj, given_image_value):

    images = csobj.images.list()
    image_id = ""
    for image in images:
        if image.id == given_image_value or image.name == given_image_value:
            print "Found image with name of \"" + image.name + "\""
            image_id = image.id
    if image_id == "":
        print "\nImage with name or id of " + given_image_value + \
              " does not exist. Please use a image id or name from \
              the following available values:\n"
        for image in images:
            print "id: %s  =>  name: \"%s\"" % (image.id, image.name)
        sys.exit(1)
    return image_id


# Check the public key file and return the dictionary for server creation
def check_pub_key_file(given_filename):

    if os.path.isfile(given_filename):
        print "Public Key File " + given_filename + " exists."
        try:
            pkfile = open(given_filename, 'r')
            content = pkfile.read()
            retfiles = {"/root/.ssh/authorized_keys": content}
            return retfiles
        except IOError as e:
            print "Sorry, but we had trouble opening file " + \
                given_filename + ". exiting"
            print("({})".format(e))
            sys.exit(1)
    else:
        print "Public key file " + given_filename + \
            " does exist. Please create using a ssh-keygen and run again."


# Create networks
def create_network(cnetobj, label, subnet):
    networks = cnetobj.list()
    for network in networks:
        if network.label == label:
            print "A network with the label %s already exists. \
                    Returning match.\n" % (label)
            return network

    print "Creating network with label %s and subnet \
            %s\n" % (label, subnet)
    newnetwork = cnetobj.create(label, cidr=subnet)
    return newnetwork


# Create the edge device server
def create_device(csrvobj, fqdn, flavor_id, image_id, rhcsnet_id,
                  appnet_id, storagenet_id, cs_files):

    # Get the server list
    servers = csrvobj.servers.list()
    for server in servers:
        if server.name == fqdn:
            print "Server by the name of " + fqdn + \
                " already exists. Returning it."
            return server

    nics_list = [{'net-id': '00000000-0000-0000-0000-000000000000'},
                 {'net-id': '11111111-1111-1111-1111-111111111111'},
                 {'net-id': rhcsnet_id},
                 {'net-id': appnet_id},
                 {'net-id': storagenet_id}]

    server_ret = csrvobj.servers.create(fqdn, image_id, flavor_id,
                                        nics=nics_list, files=cs_files)

    if server_ret.id != "":
        print "Created server " + server_ret.name + " with root pass of " \
            + server_ret.adminPass
        return server_ret


# Print server data
def print_server_data(serverobj, passwd):
    print "\n\n"
    print "###############################"
    print "# New Server Information"
    print "###############################\n"
    print "%s: " % (serverobj.name)
    print "\t%-10s %s " % ('cloud id:', serverobj.id)
    print "\t%-10s %s " % ('ip addr:', serverobj.accessIPv4)
    print "\t%-10s %s \n" % ('root pass:', passwd)


# Create and attach cbs
def create_and_attach_cbs(cbsobj, cbl_label, cbl_size, server):

    # Check for existing cbl
    exists = 0
    cbl_volumes = cbsobj.list()
    for cbl_volume in cbl_volumes:
        if cbl_volume.name == cbl_label:
            print "CBL volume: " + cbl_volume.name + " exists"
            newvol = cbl_volume
            exists = 1

    if exists == 0:
        print "Creating volume " + cbl_label + " of size " + str(cbl_size)
        newvol = cbsobj.create(name=cbl_label, size=cbl_size)

    print "Attaching volume to server " + server.name
    newvol.attach_to_instance(server,mountpoint='')


# Main function.
def main():

    # Parse the command line arguments
    parser = argparse.ArgumentParser(
        description="Create a 2 node RHCS cluster with a luci/iscsi node",
        prog='create_rhcs_cluster.py')
    parser.add_argument(
        '--image', help='image id or name (default: CentOS 6.4)',
        default='CentOS 6.4')
    parser.add_argument(
        '--flavor',
        help='flavor id or name (default: 512MB Standard Instance)',
        default='512MB Standard Instance')
    parser.add_argument(
        '--region', help='Region (default: DFW)', default="DFW")
    parser.add_argument(
        '--rhcs_network_label',
        help='RHCS network label (default: rhcs00)',
        default='rhcs00')
    parser.add_argument(
        '--rhcs_network_subnet',
        help='RHCS network subnet (default: 192.168.55.0/24)',
        default='192.168.55.0/24')
    parser.add_argument(
        '--storage_network_label',
        help='Storage network label (default: iscsi00)',
        default='iscsi00')
    parser.add_argument(
        '--storage_network_subnet',
        help='Storage network subnet (default: 192.168.66.0/24)',
        default='192.168.66.0/24')
    parser.add_argument(
        '--app_network_label',
        help='App network label (default: app00)',
        default='app00')
    parser.add_argument(
        '--app_network_subnet',
        help='App network subnet (default: 192.168.77.0/24)',
        default='192.168.77.0/24')
    parser.add_argument(
        '--nfs_cbl_size',
        help='NFS service disk size (default: 100)',
        default=100)
    parser.add_argument(
        '--nfs_cbl_label',
        help='NFS service disk label (default: nfs_vol00)',
        default='nfs_vol00')
    parser.add_argument(
        '--mysql_cbl_size',
        help='Mysql service disk size (default: 100)',
        default=100)
    parser.add_argument(
        '--mysql_cbl_label',
        help='Mysql service disk label (default: mysql_vol00)',
        default='mysql_vol00')
    parser.add_argument(
        '--domain', help='domain to use to add dns entries to', required=True)
    parser.add_argument(
        '--public_keyfile', help='ssh public key file',
        required=True)
    args = parser.parse_args()

    luci_host = 'luci00'
    ricci1_host = 'ricci00'
    ricci2_host = 'ricci01'

    # Authenticate using a credentials file: "~/.rackspace_cloud_credentials"
    cred_file = "%s/.rackspace_cloud_credentials" % (os.environ['HOME'])
    print "Setting authentication file to %s" % (cred_file)
    pyrax.set_credential_file(cred_file)

    # Instantiate a cloudservers object
    print "Instantiating cloudservers object"
    csobj = pyrax.cloudservers

    # Instantiate a clouddns object
    print "Instantiating cloud_dns object"
    cdnsobj = pyrax.cloud_dns

    # Instantiate a cloud_networks object
    print "Instantiating cloud_networks object"
    cnetobj = pyrax.cloud_networks

    # Instantiate a cloud_blockstorage object
    print "Instantiating cloud_blockstorage object"
    cbsobj = pyrax.cloud_blockstorage

    # Get the flavor id
    flavor_id = get_flavor_from_id_or_name(csobj, args.flavor)

    # Get the image id
    image_id = get_image_from_id_or_name(csobj, args.image)

    # Lets check the domain existance for the fqdn before going on
    luci_fqdn = luci_host + "." + args.domain
    check_dns(cdnsobj, luci_fqdn)
    ricci1_fqdn = ricci1_host + "." + args.domain
    check_dns(cdnsobj, ricci1_fqdn)
    ricci2_fqdn = ricci2_host + "." + args.domain
    check_dns(cdnsobj, ricci2_fqdn)

    # Check public key file
    cs_files = check_pub_key_file(args.public_keyfile)

    # Create networks
    rhcsnet = create_network(cnetobj, args.rhcs_network_label,
                             args.rhcs_network_subnet)
    appnet = create_network(cnetobj, args.app_network_label,
                            args.app_network_subnet)
    storagenet = create_network(cnetobj, args.storage_network_label,
                                args.storage_network_subnet)

    # Create the luci server
    luci_server = create_device(csobj, luci_fqdn, flavor_id, image_id,
                                rhcsnet.id, appnet.id, storagenet.id,
                                cs_files)

    # Create the ricci1 server
    ricci1_server = create_device(csobj, ricci1_fqdn, flavor_id, image_id,
                                  rhcsnet.id, appnet.id, storagenet.id,
                                  cs_files)

    # Create the ricci2 server
    ricci2_server = create_device(csobj, ricci2_fqdn, flavor_id, image_id,
                                  rhcsnet.id, appnet.id, storagenet.id,
                                  cs_files)

    # Call function to wait on ip addresses to be assigned and update
    print "Waiting for server creation to complete"
    luci_server_updated = pyrax.utils.wait_until(luci_server,
                                                 "status",
                                                 ["ACTIVE", "ERROR"],
                                                 attempts=0)
    if luci_server_updated.status == "ACTIVE":
        print "Server creation finished"
    else:
        print "Server creation errored.  Exiting"
        return

    # Call function to wait on ip addresses to be assigned and update
    ricci1_server_updated = pyrax.utils.wait_until(ricci1_server,
                                                   "status",
                                                   ["ACTIVE", "ERROR"],
                                                   attempts=0)
    if ricci1_server_updated.status == "ACTIVE":
        print "Server creation finished"
    else:
        print "Server creation errored.  Exiting"
        return

    # Call function to wait on ip addresses to be assigned and update
    ricci2_server_updated = pyrax.utils.wait_until(ricci2_server,
                                                   "status",
                                                   ["ACTIVE", "ERROR"],
                                                   attempts=0)
    if ricci2_server_updated.status == "ACTIVE":
        print "Server creation finished"
    else:
        print "Server creation errored.  Exiting"
        return

    # Create NFS Vol and attach to the luci server
    create_and_attach_cbs(cbsobj, args.nfs_cbl_label,
                          args.nfs_cbl_size, luci_server_updated)

    # Create Mysql Vol and attach to the luci server
    create_and_attach_cbs(cbsobj, args.mysql_cbl_label,
                          args.mysql_cbl_size, luci_server_updated)

    # Create a DNS entry for the servers
    create_dns(cdnsobj, luci_fqdn, luci_server_updated.accessIPv4)
    create_dns(cdnsobj, ricci1_fqdn, ricci1_server_updated.accessIPv4)
    create_dns(cdnsobj, ricci2_fqdn, ricci2_server_updated.accessIPv4)

    # Print the server data
    print_server_data(luci_server_updated, luci_server.adminPass)
    print_server_data(ricci1_server_updated, ricci1_server.adminPass)
    print_server_data(ricci1_server_updated, ricci1_server.adminPass)


# Called on execution. We are just going to call the main function from here.
if __name__ == "__main__":
    main()
