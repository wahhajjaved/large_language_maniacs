#!/usr/bin/python

import requests
import json
import base64
import ConfigParser
import os
import sys

#taken from the Oracle VM Web Services API Developer's Guide
def check_manager_state(baseUri,s):
    while True:
        r=s.get(baseUri+'/Manager')
        manager=r.json()
        if manager[0]['managerRunState'].upper() == 'RUNNING':
            break

        time.sleep(1)
    return

def main():
    #parse the config file
    config = ConfigParser.ConfigParser()
    config.readfp(open(os.path.join(sys.path[0],'dellstorage-oraclevm.cfg')))
    dellusername = config.get('dell','username')
    dellpassword = config.get('dell','password')
    dellUri = config.get('dell','baseUri')
    ovmusername = config.get('ovm','username')
    ovmpassword = config.get('ovm','password')
    ovmUri = config.get('ovm','baseUri')

    dbg = False
    if config.has_option('general', 'debug'):
        dbg = config.getboolean('general', 'debug')

    #open a session with Dell Storage Manager
    dells=requests.Session()
    dells.headers.update({'Accept': 'application/json', 'Content-Type': 'application/json', 'x-dell-api-version': '2.2'})
    dells.verify=False #disable once we get a real cert
    dellauth = {'Authorization': 'Basic ' + base64.b64encode(dellusername + ':' + dellpassword), 'Content-Type': 'application/json', 'x-dell-api-version': '2.2'}
    r=dells.post(dellUri+'/ApiConnection/Login','{}',headers=dellauth)

    #open a sesion with Oracle VM Manager
    ovms=requests.Session()
    ovms.auth=(ovmusername, ovmpassword)
    ovms.headers.update({'Accept': 'application/json', 'Content-Type': 'application/json'})
    check_manager_state(ovmUri,ovms)

    #get a list of all Volumes from the Dell Storage Manager
    r=dells.get(dellUri+'/StorageCenter/ScVolume')
    delldisks=r.json()
    
    #get a list of all physical disks in Oracle VM Manager
    r=ovms.get(ovmUri+'/StorageElement')
    ovmdisks=r.json()

    #Match up the OVMM Disk with the Compellent Disk and set the name to match in OVMM
    for disk in ovmdisks:
        if disk['vendor'] == 'COMPELNT':
            found = False
            for delldisk in delldisks:
                #Oracle VM puts the Page 83 Type in front of the actual identifier
                #so cut off the first character
                if disk['page83Id'][1:] == delldisk['deviceId']:
                    found = True

                    if disk['name'] == delldisk['name']:
                        if dbg is True:
                            print 'Disk with Page 83 Id ' + delldisk['deviceId']
                            print 'Oracle VM  name is ' + disk['name']
                            print 'Compellent name is ' + delldisk['name']
                            print 'Names match, no change needed.'
                            print
                    else:
                        print 'Disk with Page 83 Id ' + delldisk['deviceId']
                        print 'Oracle VM  name is ' + disk['name']
                        print 'Compellent name is ' + delldisk['name']
                        print 'Names do not match, changing on Oracle VM Manager.'
                        name = disk
                        name.update({'name': delldisk['name']})
                        r=ovms.put(ovmUri+'/StorageElement/'+disk['id']['value'],json.dumps(name))
                        print r
                        if dbg is True:
                            print r.json()
                            print
                        else:
                            print

                    break
                    
            if not found:
                print 'Unable to find match for ' + disk['name']

    #log out of Dell Storage Manager
    r=dells.post(dellUri+'/ApiConnection/Logout','{}')

    return

if __name__ == '__main__': 
    main()
