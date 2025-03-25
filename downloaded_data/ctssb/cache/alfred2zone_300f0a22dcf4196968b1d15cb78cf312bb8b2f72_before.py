from ipaddress import IPv6Address, IPv6Network
from json import loads
from photon import Photon
from photon.util.files import write_file
from re import compile as re_compile
from time import time

hostname_rx = r'^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$'

photon = Photon(
    defaults='defaults.yaml',
    config='config.yaml',
    meta='zone_from_alfred_meta.json',
    verbose=True
)
settings = photon.settings.get

def _rtrv(socket):
    cmd = settings['alfred_cmd'].format(socket=socket)
    if settings.get('alfred_ssh'):
        cmd = 'ssh {ssh} "{cmd}"'.format(cmd=cmd, ssh=settings['alfred_ssh'])
    res = photon.m(
        'asking alfred%s (%s)' %(' over ssh' if settings.get('alfred_ssh') else '', socket),
        cmdd=dict(cmd=cmd)
    )
    if res.get('returncode') == 0:
        return loads(''.join(res.get('stdout')))
    return dict()

def _check(data, prefix):
    res = list()
    if data:
        for mac in data:
            node = data.get(mac)
            hostname = node['hostname']
            if re_compile(hostname_rx).match(hostname):
                for address in [
                    a for a in node['network']['addresses'] if IPv6Address(a) in prefix
                ]:
                    res.append((str.lower(node['hostname']), address))
    return sorted(set(res))

def _write(elems, community):
    soa, ns, zonefile = (
        settings['communities'][community].get('soa'),
        settings['communities'][community].get('ns'),
        settings['communities'][community].get('zonefile'),
    )

    if all([soa, ns, zonefile]):
        return write_file(zonefile,
            settings['zone'].format(
                soa=soa,
                serial=int(time()),
                ns='\n'.join(['    %s    NS' %(n) for n in ns]),
                nodes='\n'.join(['%s    AAAA    %s' %(n, a) for (n, a) in elems]),
            )
        )


def run():
    res = list()
    for community in settings['communities'].keys():
        prefix, socket = (
            settings['communities'][community].get('prefix'),
            settings['communities'][community].get('socket')
        )
        if all([prefix, socket]):
            res.append(_write(
                _check(
                    _rtrv(socket), IPv6Network(prefix)
                ),
                community
            ))
    if any(res) and settings.get('post_cmd'):
        photon.m(
            'running post command',
            cmdd=dict(cmd=settings['post_cmd'])
        )

if __name__ == '__main__':
    run()
