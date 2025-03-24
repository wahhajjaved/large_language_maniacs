#! /usr/bin/env python
# net_main.py example program for inventory gathering
# Class 8 in Byers' Applied Python series

from net_system.models import NetworkDevice, Credentials   #removed SnmpCredentials
from remote_connection.ssh_connection import SSHConnection
import django
import time

def gather_inventory():

    # Main program dispatch for working each device,
    # connecting appropriately based on class and
    # looking through config
    
    DEBUG = True
    
    net_devices = NetworkDevice.objects.all()
    
    for a_device in net_devices:
        
        if 'ssh' in a_device.device_class:
            if DEBUG: print "SSH inventory call: {} {}".format(a_device.device_name, a_device.device_class)
            ssh_connect = SSHConnection(a_device)
            ssh_connect.establish_connection()
        elif 'onepk' in a_device.device_class:
            if DEBUG: print "onePK inventory call: {} {}".format(a_device.device_name, a_device.device_class)
            pass
        elif 'eapi' in a_device.device_class:
            if DEBUG: print "eAPI inventory call: {} {}".format(a_device.device_name, a_device.device_class)
            pass
        else:    #invalid conditions handler
            pass
            

# START MAIN LOOP

if __name__ == "__main__":
    
    django.setup()
    
    LOOP_DELAY = 300  # 5-minute pause between loops
    VERBOSE = True
    
    time.sleep(5)
    print
    
    while True:
        
        if VERBOSE: print "Gather inventory from devices"
        gather_inventory()
            
        if VERBOSE: print "Sleeping for {} seconds".format(LOOP_DELAY)
        time.sleep(LOOP_DELAY)
                
