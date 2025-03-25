'''
Copyright 2013 Dustin Frisch<fooker@lab.sh>

This file is part of netprov.

netprov is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

netprov is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with netprov. If not, see <http://www.gnu.org/licenses/>.
'''

from netprov.source import Source, Subnet, Entry

import MySQLdb.cursors



class PhpipamSource(Source):
    def __init__(self,
                 host,
                 port,
                 database,
                 username,
                 password,
                 section = None,
                 fields = {}):
        self.__connection = MySQLdb.connect(host = host,
                                            port = port,
                                            user = username,
                                            passwd = password,
                                            db = database,
                                            cursorclass = MySQLdb.cursors.DictCursor)
        self.__section = section

        self.__fields = fields


    @property
    def subnets(self):
        result = {}

        c_subnets = self.__connection.cursor()
        c_entries = self.__connection.cursor()

        c_subnets.execute('''
            SELECT
              subnet.id AS id,
              CAST(subnet.subnet AS UNSIGNED) AS r_network,
              CAST(subnet.mask AS UNSIGNED) AS r_netmask
        ''' + ''.join(', `%s` AS r_%s' % (field, target)
                      for target, field
                      in self.__fields.iteritems()) +
        '''
            FROM subnets AS subnet
            JOIN sections AS section
              ON (section.id = subnet.sectionId AND
                  section.name LIKE %s)
            ORDER BY r_network
        ''', self.__section)
        for r in c_subnets:
            subnet = Subnet(**{k[2:]: v
                               for k, v
                               in r.iteritems()
                               if k.startswith('r_')})

            entries = result[subnet] = []

            c_entries.execute('''
                SELECT
                    dns_name AS name,
                    CAST(ip_addr AS UNSIGNED) AS ipaddr,
                    mac AS hwaddr,
                    CAST(CONCAT("0", state) AS UNSIGNED) AS state
                FROM ipaddresses
                WHERE subnetId = %s
                ORDER BY ipaddr
            ''', r['id'])
            for r in c_entries:
                r_name = r['name']
                r_ipaddr = r['ipaddr']
                r_hwaddr = r['hwaddr']
                r_state = r['state']

                if r_state == 1 or r_state == 0:
                    entry = Entry.fixed(name = r_name,
                                        ipaddr = r_ipaddr)
                elif r_state == 3:
                    if r_hwaddr:
                        entry = Entry.static(name = r_name,
                                             ipaddr = r_ipaddr,
                                             hwaddr = r_hwaddr)
                    else:
                        entry = Entry.dynamic(name = r_name,
                                              ipaddr = r_ipaddr)

                else:
                    continue

                entries.append(entry)


        c_subnets.close()
        c_entries.close()

        return result
