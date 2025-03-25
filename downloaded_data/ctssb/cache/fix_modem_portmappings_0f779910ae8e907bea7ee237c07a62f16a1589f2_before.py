#!/usr/bin/python

import socket
import collections
import mechanize
import BeautifulSoup


PortMapping = collections.namedtuple('PortMapping', 'name ip port')

class PortMappingHandler():
    def __init__(self):
        options = {
            'modem_ip': '192.168.1.1',
            'username': 'user',
            'password': 'user',
        }

        self.base_url = 'http://%s/scvrtsrv.cmd?action=' % options['modem_ip']
        self.view_url = self.base_url + '=view'
        self.append_url = self.base_url + '=add&srvName=%(name)s&srvAddr=%(ip)s&proto=1,&eStart=%(port)s,&eEnd=%(port)s,&iStart=%(port)s,&iEnd=%(port)s'
        self.remove_url = self.base_url + '=remove&rmLst=%(ip_int)s|%(port)s|%(port)s|1|0|0|%(port)s|%(port)s,'

        self.browser = mechanize.Browser()
        self.browser.add_password(self.base_url, options['username'], options['password'])

    def retrieve(self):
        self.browser.open(self.view_url)
        soup = BeautifulSoup.BeautifulSoup(self.browser.response().read())

        # the first table row is a header
        rows = soup.findAll('tr')[1:]
        mappings = []
        for row in rows:
            cells = row.findAll('td')
            mappings.append(PortMapping(
                    name = cells[0].string, 
                    ip = cells[6].string,
                    port = cells[1].string))

        return mappings

    def append(self, mapping):
        print 'adding %s %s %s' % mapping
        return
        self.browser.open(self.append_url % {
                'name': mapping.name,
                'ip': mapping.ip,
                'port': mapping.port,
            })

    def remove(self, mapping):
        print 'removing %s %s %s' % mapping
        return
        self.browser.open(self.remove_url % {
                'ip_int': ip_to_int(mapping.ip),
                'port': mapping.port,
            })

    def ip_to_int(self, ipaddress):
        return int(socket.inet_pton(socket.AF_INET, ipaddress).encode('hex'), 16)


def get_ipaddress():
    return socket.gethostbyname(socket.gethostname())

def main():
    ip = get_ipaddress();

    wanted_mappings = [
        PortMapping(name='ssh', ip=ip, port=22),
        PortMapping(name='http', ip=ip, port=80),
        PortMapping(name='https', ip=ip, port=443),
    ]

    handler = PortMappingHandler()
    existing_mappings = handler.retrieve()

    to_remove = []
    to_add = []

    for wanted in wanted_mappings:
        wanted_found = False

        for existing in existing_mappings:
            if wanted.port == existing.port:
                found = True

            if wanted.port == existing.port and wanted.ip != existing.ip:
                to_remove.append(existing)
                to_add.append(wanted)

        if not wanted_found:
            mappings_to_add.append(wanted)


    for mapping in to_remove:
        handler.remove(mapping)

    for mapping in to_add:
        handler.append(mapping)


if __name__ == '__main__':
    main()
