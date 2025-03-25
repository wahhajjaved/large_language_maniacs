#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#       nmap.py
#       Copyright 2010 arpagon <arpagon@gmail.com.co>
#       
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#       
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#       
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

"""Python Library for admin Aastra Phones
Factory Reset
"""
__version__ = "0.0.1"
__license__ = """The GNU General Public License (GPL-2.0)"""
__author__ = "Sebastian Rojo <http://www.sapian.com.co> arpagon@gamil.com"
__contributors__ = []
_debug = 0

import subprocess
from BeautifulSoup import BeautifulSoup
import logging
import os

logging.basicConfig(level=logging.DEBUG)
if not os.path.exists("/var/log/dialbox"):
    os.makedirs("/var/log/dialbox")
LOG_FILENAME = '/var/log/dialbox/nmap.log'
log = logging.getLogger('NMAP')
handler = logging.FileHandler(LOG_FILENAME)
handler.setLevel(logging.DEBUG)
log.addHandler(handler)

NmapFile="/tmp/nmap.xml"

def GenNmapFile(NetworString):
    p = subprocess.Popen(["nmap", "-sP", "-n" , "-oX", NmapFile, NetworString], stdout=subprocess.PIPE)
    output, err = p.communicate()
    if not err:
        return True
    else:
        return False

def GetHost(NmapFile=NmapFile):
    Result=open(NmapFile).read()
    NmapResult=BeautifulSoup(Result)
    HostDict={}
    for Host in NmapResult.findAll("host"):
        if Host.status.attrs[0][1] == "up":
            for Address in Host.findAll("address"):
                if (u'addrtype', u'mac') in Address.attrs:
                    HostDict[Host.address.attrs[0][1]]=Address.attrs[0][1]
    print HostDict
        

def main():
    pass

if __name__=='__main__':
    main()