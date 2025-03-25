#!/usr/bin/python
#Copyright (C) 2009 Gabes Jean, naparuba@gmail.com
#
#This file is part of Shinken.
#
#Shinken is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Shinken is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with Shinken.  If not, see <http://www.gnu.org/licenses/>.


#This Class is an example of an Arbiter module
#Here for the configuration phase AND running one


#This text is print at the import
print "Detected module : NSCA module for Arbiter"


import time
import select
import socket
import struct
from ctypes import create_string_buffer
import random

from shinken.external_command import ExternalCommand

properties = {
    'type' : 'nsca_server',
    'external' : True,
    'phases' : ['running'],
    }

def decrypt_xor(data, key):
    keylen = len(key)
    crypted = [chr(ord(data[i]) ^ ord(key[i % keylen])) for i in xrange(len(data))]
    return ''.join(crypted)

#called by the plugin manager to get a broker
def get_instance(plugin):
    print "Get a NSCA arbiter module for plugin %s" % plugin.get_name()

    if hasattr(plugin, 'host'):
        if plugin.host == '*':
            host = ''
        else:
            host = plugin.host
    else:
        host = '127.0.0.1'
    if hasattr(plugin, 'port'):
        port = int(plugin.port)
    else:
        port = 5667
    if hasattr(plugin, 'encryption_method'):
        encryption_method = int(plugin.encryption_method)
    else:
        encryption_method = 0
    if hasattr(plugin, 'password'):
        password = plugin.password
    else:
        password = ""

    instance = NSCA_arbiter(plugin.get_name(), host, port, encryption_method, password)
    return instance


#Just print some stuff
class NSCA_arbiter:
    def __init__(self, name, host, port, encryption_method, password):
        self.name = name
        self.host = host
        self.port = port
        self.encryption_method = encryption_method
        self.password = password
        self.rng = random.Random(password)

    #Called by Arbiter to say 'let's prepare yourself guy'
    def init(self):
        print "Initialisation of the nsca arbiter module"
        self.return_queue = self.properties['from_queue']


    def get_name(self):
        return self.name


    #Ok, main function that is called in the CONFIGURATION phase
    def get_objects(self):
        print "[Dummy] ask me for objects to return"
        r = {'hosts' : []}
        h = {'name' : 'dummy host from dummy arbiter module',
             'register' : '0',
             }

        r['hosts'].append(h)
        print "[Dummy] Returning to Arbiter the hosts:", r
        return r

    def send_init_packet(self, socket):
        '''
        Build an init packet
         00-127  : IV
         128-131 : unix timestamp
        '''
        init_packet=create_string_buffer(132)
        iv = ''.join([chr(self.rng.randrange(256)) for i in xrange(128)])
        init_packet.raw=struct.pack("!128sI",iv,int(time.mktime(time.gmtime())))
        socket.send(init_packet)
        return iv

    def read_check_result(self, data, iv):
        '''
        Read the check result
         00-01 : Version
         02-05 : CRC32
         06-09 : Timestamp
         10-11 : Return code
         12-75 : hostname
         76-203 : service
         204-715 : output of the plugin
         716-720 : padding
        '''
        if len(data) != 720:
            return None

        if self.encryption_method == 1:
            data = decrypt_xor(data,self.password)
            data = decrypt_xor(data,iv)

        (version, pad1, crc32, timestamp, rc, hostname_dirty, service_dirty, output_dirty, pad2) = struct.unpack("!hhIIh64s128s512sh",data)
        hostname, sep, dish =  hostname_dirty.partition("\0")
        service, sep, dish = service_dirty.partition("\0")
        output, sep, dish = output_dirty.partition("\0")
        return (timestamp, rc, hostname, service, output)

    def post_command(self, timestamp, rc, hostname, service, output):
        '''
        Send a check result command to the arbiter
        '''
        if len(service) == 0:
            extcmd = "[%lu] PROCESS_HOST_CHECK_RESULT;%s;%d;%s\n" % (timestamp,hostname,rc,output)
        else:
            extcmd = "[%lu] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%d;%s\n" % (timestamp,hostname,service,rc,output)

        e = ExternalCommand(extcmd)
        self.return_queue.put(e)


    #When you are in "external" mode, that is the main loop of your process
    def main(self):
        backlog = 5
        size = 8192
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(0)
        server.bind((self.host, self.port))
        server.listen(backlog)
        input = [server]
        databuffer = {}
        IVs = {}

        while True:
            inputready,outputready,exceptready = select.select(input,[],[], 0)

            for s in inputready:
                if s == server:
                    # handle the server socket
                    client, address = server.accept()
                    iv = self.send_init_packet(client)
                    IVs[client] = iv
                    input.append(client)
                else:
                    # handle all other sockets
                    data = s.recv(size)
                    if s in databuffer:
                        databuffer[s] += data
                    else:
                        databuffer[s] = data
                    if len(databuffer[s]) == 720:
                        # end-of-transmission or an empty line was received
                        (timestamp, rc, hostname, service, output)=self.read_check_result(databuffer[s],IVs[s])
                        del databuffer[s]
                        del IVs[s]
                        self.post_command(timestamp,rc,hostname,service,output)
                        try:
                            s.shutdown(2)
                        except Exception , exp:
                            print exp
                        s.close()
                        input.remove(s)
