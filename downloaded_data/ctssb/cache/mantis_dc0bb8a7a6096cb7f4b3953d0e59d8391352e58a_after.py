#!/usr/bin/env python3

import pycouchdb
import requests
import sys
import xml.etree.ElementTree as ET

def usage():
    print("usage: ./parser.py <NETXML-FILE>")

class Mantis:
    __db = None

    def __init__(self, *args, **kwargs):
        """Constructor for the Mantis class.

        possible arguments are:
        * sourcefile: path to netxml source file
        * dbname: name of database to use, default is "wifinetworks"
        * host: hostname/IP of database server
        * port: listening port of database server
        * username: username for the database
        * password: password for the database
        If arguments are not set, default values are used.
        """

        # check all given arguments for validity
        validargs = ('sourcefile','dbname','host','port','username','password')
        for arg in kwargs.keys():
            if arg not in validargs:
                raise TypeError("invalid argument")
            
        # assume default config for couchdb
        authstring = "http://"
        if ('username' in kwargs.keys()) and ('password' in kwargs.keys()):
            authstring +=  kwargs['username'] + ":" + kwargs['password']

        if len(authstring) > 8:
            authstring += "@"

        if 'host' in kwargs.keys():
            authstring += kwargs['host']
        else:
            authstring += "localhost"

        if 'port' in kwargs.keys():
            authstring += ":" + kwargs['port']
        else:
            authstring += ":5984"

        server = pycouchdb.Server(authstring)

        try:
            server.info()
        except requests.exceptions.ConnectionError:
            sys.stderr.write("connecting to server failed\n")
            sys.exit(1)

        # assume databasename, if database does not exists, create it
        if 'dbname' in kwargs.keys():
            dbname = kwargs['dbname']
        else:
            dbname = "wifinetworks"

        try:
            db = server.database(dbname)
        except pycouchdb.exceptions.NotFound:
            server.create(dbname)
        self.__db = server.database(dbname)

        if 'sourcefile' in kwargs.keys():
            filename = kwargs['sourcefile']
            self.parse_xml(filename)

    def parse_xml(self,netxmlfile):
        """Parse given netxml file."""
        updatecounter = 0
        tree = ET.ElementTree()
        try:
            tree = ET.parse(netxmlfile)
        except FileNotFoundError:
            sys.stderr.write("opening file failed\n")
        root = tree.getroot()
        for network in tree.findall('wireless-network'):
            networkdata = {}
            # only handle fixed networks, ignore probes etc.
            if "infrastructure" == network.attrib['type']:
                # extract the data
                ssids = network.findall('SSID')
                ssiddata = []
                for ssidnode in ssids:
                    ssiddata.append( self.extract_ssid_data(ssidnode) )
                    networkdata['ssid'] = ssiddata
                    networkdata['bssid'] = network.find('BSSID').text
                    networkdata['snr-info'] = self.extract_snr_info( network.find('snr-info') )
                    networkdata['gps-info'] = self.extract_gps_info( network.find('gps-info') )
                    # push it into couchdb
                doc = self.__db.save(networkdata)
                updatecounter += 1
        return updatecounter

    def extract_ssid_data(self,rawdata):
        """Extract relevant SSID data from given XML-node.

        This data contains per SSID: maximum data rate, encryption modes and
        ESSID.
        """

        if not isinstance(rawdata,ET.Element):
            raise TypeError("given rawdata not an ElementTree-element")

        ssiddata = {}
        maxrate = rawdata.find('max-rate').text
        ssiddata['max-rate'] = float(maxrate)

        encryption_modes = rawdata.findall('encryption')
        enctxt = []
        for enc in encryption_modes:
            enctxt.append(enc.text)
            ssiddata['encryption'] = enctxt

        ssiddata['essid'] = rawdata.find('essid').text

        return ssiddata

    def extract_snr_info(self,rawdata):
        """Extract relevant radio signal data from given XML-node.

        This data contains minimum and maximum levels of the signal and noise.
        """
        if not isinstance(rawdata,ET.Element):
            raise TypeError("given rawdata not an ElementTree-element")

        snrinfo = {}
        data = rawdata.find('min_signal_dbm').text
        snrinfo['min_signal_dbm'] = int(data)
        data = rawdata.find('min_noise_dbm').text
        snrinfo['min_noise_dbm'] = int(data)
        data = rawdata.find('min_signal_rssi').text
        snrinfo['min_signal_rssi'] = int(data)
        data = rawdata.find('min_noise_rssi').text
        snrinfo['min_noise_rssi'] = int(data)

        data = rawdata.find('max_signal_dbm').text
        snrinfo['max_signal_dbm'] = int(data)
        data = rawdata.find('max_noise_dbm').text
        snrinfo['max_noise_dbm'] = int(data)
        data = rawdata.find('max_signal_rssi').text
        snrinfo['max_signal_rssi'] = int(data)
        data = rawdata.find('max_noise_rssi').text
        snrinfo['max_noise_rssi'] = int(data)

        return snrinfo


    def extract_gps_info(self, rawdata):
        """Extract relevant GPS data from given XML-node.

        This data contains the coordinates of the minimum, maximum and peak
        signal level.
        """

        if not isinstance(rawdata,ET.Element):
            raise TypeError("given rawdata not an ElementTree-element")

        gpsinfo = {}
        data = rawdata.find('min-lat').text
        gpsinfo['min-lat'] = float(data)
        data = rawdata.find('min-lon').text
        gpsinfo['min-lon'] = float(data)
        data = rawdata.find('max-lat').text
        gpsinfo['max-lat'] = float(data)
        data = rawdata.find('max-lon').text
        gpsinfo['max-lon'] = float(data)
        data = rawdata.find('peak-lat').text
        gpsinfo['peak-lat'] = float(data)
        data = rawdata.find('peak-lon').text
        gpsinfo['peak-lon'] = float(data)

        return gpsinfo

    def deflate(self):
        """Remove all duplicate entries and compact database. Return number of removed entries."""
        mapfunction = "function(doc) {\
            var bssid, essid, uid;\
            if (doc.ssid && doc.bssid) {\
            uid = [doc.bssid];\
            names = [];\
            for (index in doc.ssid) {\
                names.push(doc.ssid[index]['essid']);\
            }\
            uid.push(names);\
            emit(uid, null);\
        }\
        }"
        result = self.__db.temporary_query(mapfunction)
        # this algorithm deletes entries with same UIDs
        # the current UID could be insufficient
        knownids = []
        killlist = []
        print(list(result).__class__)
        for item in result:
            if item['key'] not in knownids:
                knownids.append(item['key'])
            else:
                killlist.append(item['id'])

        for docid in killlist:
            self.__db.delete(docid)

        self.__db.compact()

        return len(killlist)

    def create_bssid_view(self):
        _doc = {
            "_id": "_design/testing",
            "views": {
                "bssids": {
                    "map": "function(doc) { if(doc.bssid) { emit(doc.bssid); } }"
                    }
                }
            }
        self.__db.save(_doc)

# only call if executed as script
if __name__ == '__main__':
    if 2 != len(sys.argv):
        usage()
        sys.exit(1)

    databucket = Mantis(sourcefile=sys.argv[1])
#    databucket = Mantis()
    databucket.create_bssid_view()
    purges = databucket.deflate()
#    print(purges)
