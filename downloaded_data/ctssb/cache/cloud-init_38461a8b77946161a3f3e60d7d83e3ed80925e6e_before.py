# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import DataSource

from cloudinit import seeddir, log
import cloudinit.util as util
import socket
import urllib2
import time
import sys
import boto_utils
import os.path
import errno
import urlparse

class DataSourceEc2(DataSource.DataSource):
    api_ver  = '2009-04-04'
    seeddir = seeddir + '/ec2'
    metadata_address = "http://169.254.169.254"

    def __str__(self):
        return("DataSourceEc2")

    def get_data(self):
        seedret={ }
        if util.read_optional_seed(seedret,base=self.seeddir+ "/"):
            self.userdata_raw = seedret['user-data']
            self.metadata = seedret['meta-data']
            log.debug("using seeded ec2 data in %s" % self.seeddir)
            return True
        
        try:
            if not self.wait_for_metadata_service():
                return False
            self.userdata_raw = boto_utils.get_instance_userdata(self.api_ver, None, self.metadata_address)
            self.metadata = boto_utils.get_instance_metadata(self.api_ver, self.metadata_address)
            return True
        except Exception as e:
            print e
            return False

    def get_instance_id(self):
        return(self.metadata['instance-id'])

    def get_availability_zone(self):
        return(self.metadata['placement']['availability-zone'])

    def get_local_mirror(self):
        return(self.get_mirror_from_availability_zone())

    def get_mirror_from_availability_zone(self, availability_zone = None):
        # availability is like 'us-west-1b' or 'eu-west-1a'
        if availability_zone == None:
            availability_zone = self.get_availability_zone()

        fallback = 'http://archive.ubuntu.com/ubuntu/'

        if self.is_vpc():
            return fallback

        try:
            host="%s.ec2.archive.ubuntu.com" % availability_zone[:-1]
            socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
            return 'http://%s/ubuntu/' % host
        except:
            return fallback


    def wait_for_metadata_service(self, sleeps = None):
        mcfg = self.ds_cfg
        if sleeps is None:
            sleeps = 30
            try:
                sleeps = int(mcfg.get("retries",sleeps))
            except Exception as e:
                util.logexc(log)
                log.warn("Failed to get number of sleeps, using %s" % sleeps)

        if sleeps == 0: return False

        timeout=2
        try:
            timeout = int(mcfg.get("timeout",timeout))
        except Exception as e:
            util.logexc(log)
            log.warn("Failed to get timeout, using %s" % timeout)

        sleeptime = 1

        def_mdurls = ["http://169.254.169.254", "http://instance-data:8773"]
        try:
            mdurls = mcfg.get("metadata_urls", def_mdurls)
        except Exception as e:
            mdurls = def_mdurls
            util.logexc(log)
            log.warn("Failed to get metadata URLs, using defaults")

        starttime = time.time()

        # Remove addresses from the list that wont resolve.
        filtered = [x for x in mdurls if try_to_resolve_metadata(x)]

        if set(filtered) != set(mdurls):
            log.debug("removed the following from metadata urls: %s" %
                list((set(mdurls) - set(filtered))))

        if len(filtered):
            mdurls = filtered
        else:
            log.warn("Empty metadata url list! using default list")
            mdurls = def_mdurls

        log.debug("Searching the following metadata urls: %s" % mdurls)

        for x in range(sleeps):
            for url in mdurls:
                iurl="%s/%s/meta-data/instance-id" % (url, self.api_ver)

                # given 100 sleeps, this ends up total sleep time of 1050 sec
                sleeptime=int(x/5)+1

                reason = ""
                try:
                    req = urllib2.Request(url)
                    resp = urllib2.urlopen(req, timeout=timeout)
                    if resp.read() != "":
                        self.metadata_address = url
                        log.debug("Using metadata source: '%s'" % url)
                        return True
                    reason = "empty data [%s]" % resp.getcode()
                except urllib2.HTTPError as e:
                    reason = "http error [%s]" % e.code
                except urllib2.URLError as e:
                    reason = "url error [%s]" % e.reason

                #not needed? Addresses being checked are displayed above
                #if x == 0:
                #    log.warn("waiting for metadata service at %s" % url)

                log.warn("'%s' failed: %s" % (url, reason))
            time.sleep(sleeptime)

        log.critical("giving up on md after %i seconds\n" %
                  int(time.time()-starttime))
        return False

    def device_name_to_device(self, name):
        # consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        if not self.metadata.has_key('block-device-mapping'):
            return(None)

        found = None
        for entname, device in self.metadata['block-device-mapping'].items():
            if entname == name:
                found = device
                break
            # LP: #513842 mapping in Euca has 'ephemeral' not 'ephemeral0'
            if entname == "ephemeral" and name == "ephemeral0":
                found = device
        if found == None:
            log.warn("unable to convert %s to a device" % name)
            return None

        # LP: #611137
        # the metadata service may believe that devices are named 'sda'
        # when the kernel named them 'vda' or 'xvda'
        # we want to return the correct value for what will actually
        # exist in this instance
        mappings = { "sd": ("vd", "xvd") }
        ofound = found
        short = os.path.basename(found)
        
        if not found.startswith("/"):
            found="/dev/%s" % found

        if os.path.exists(found):
            return(found)

        for nfrom, tlist in mappings.items():
            if not short.startswith(nfrom): continue
            for nto in tlist:
                cand = "/dev/%s%s" % (nto, short[len(nfrom):])
                if os.path.exists(cand):
                    log.debug("remapped device name %s => %s" % (found,cand))
                    return(cand)
        return ofound

    def is_vpc(self):
        # per comment in LP: #615545
        ph="public-hostname"; p4="public-ipv4"
        if ((ph not in self.metadata or self.metadata[ph] == "") and
            (p4 not in self.metadata or self.metadata[p4] == "")):
            return True
        return False

def try_to_resolve_metadata(url):
    try:
        addr = urlparse.urlsplit(url).netloc.split(":")[0]
        socket.getaddrinfo(addr, None)
        return True
    except Exception as e:
        return False


datasources = [ 
  ( DataSourceEc2, ( DataSource.DEP_FILESYSTEM , DataSource.DEP_NETWORK ) ),
]

# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))
