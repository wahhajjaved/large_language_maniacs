#!/usr/bin/env python
import argh
import netaddr


def main(cidr, host):
    cidr_mask = cidr.split("/")[-1]
    subnet = netaddr.IPNetwork(cidr)
    ip_address = netaddr.IPAddress(host)

    prefix = '.'.join(map(str, subnet.network.words[0:3]))
    suffix = ip_address.words[-1]
    return '%s.%s/%s'.rstrip('\n') % (prefix, suffix, cidr_mask)

argh.dispatch_command(main)
