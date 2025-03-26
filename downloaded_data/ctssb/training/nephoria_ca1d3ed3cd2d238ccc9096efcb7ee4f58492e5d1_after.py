# Software License Agreement (BSD License)
#
# Copyright (c) 2009-2011, Eucalyptus Systems, Inc.
# All rights reserved.
#
# Redistribution and use of this software in source and binary forms, with or
# without modification, are permitted provided that the following conditions
# are met:
#
#   Redistributions of source code must retain the above
#   copyright notice, this list of conditions and the
#   following disclaimer.
#
#   Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the
#   following disclaimer in the documentation and/or other
#   materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: vic.iglesias@eucalyptus.com


from eutester import Eutester
import time
import re
import os
import copy
from datetime import datetime
from boto.ec2.image import Image
from boto.ec2.keypair import KeyPair
from boto.ec2.blockdevicemapping import BlockDeviceMapping, BlockDeviceType
from boto.ec2.volume import Volume
from boto.exception import EC2ResponseError
from eutester.euinstance import EuInstance
from eutester.euvolume import EuVolume
from eutester.eusnapshot import EuSnapshot


class EC2ops(Eutester):
    def __init__(self, credpath=None, aws_access_key_id=None, aws_secret_access_key = None, username="root",region=None, ec2_ip=None, s3_ip=None, boto_debug=0):
        Eutester.__init__(self, credpath=credpath, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key,region=region,  s3_ip=s3_ip, ec2_ip=ec2_ip, boto_debug=boto_debug)
        self.poll_count = 48
        self.username = username
        self.test_resources = {}
        self.setup_ec2_resource_trackers()
        self.key_dir = "./"

    def setup_ec2_resource_trackers(self):
        """
        Setup keys in the test_resources hash in order to track artifacts created
        """
        self.test_resources["reservations"] = []
        self.test_resources["volumes"] = []
        self.test_resources["snapshots"] = []
        self.test_resources["keypairs"] = []
        self.test_resources["security-groups"] = []
        self.test_resources["images"] = []
    
    def add_keypair(self,key_name=None):
        """
        Add a keypair with name key_name unless it already exists

        :param key_name:      The name of the keypair to add and download.
        """
        if key_name is None:
            key_name = "keypair-" + str(int(time.time())) 
        self.debug(  "Looking up keypair " + key_name )
        key = []
        try:
            key = self.ec2.get_all_key_pairs(keynames=[key_name])    
        except EC2ResponseError:
            pass
        
        if not key:
            self.debug( 'Creating keypair: %s' % key_name)
            # Create an SSH key to use when logging into instances.
            key = self.ec2.create_key_pair(key_name)
            # AWS will store the public key but the private key is
            # generated and returned and needs to be stored locally.
            # The save method will also chmod the file to protect
            # your private key.
            key.save(self.key_dir)
            #Add the fingerprint header to file
            keyfile = open(self.key_dir+key.name+'.pem','r')
            data = keyfile.read()
            keyfile.close()
            keyfile = open(self.key_dir+key.name+'.pem','w')
            keyfile.write('KEYPAIR '+str(key.name)+' '+str(key.fingerprint)+"\n")
            keyfile.write(data)
            keyfile.close()
            
            self.test_resources["keypairs"].append(key)
            return key
        else:
            self.debug(  "Key " + key_name + " already exists")
            
            
            
    def verify_local_keypath(self,keyname, path=None, exten=".pem"):
        """
        Convenience function to verify if a given ssh key 'keyname' exists on the local server at 'path'

        :returns: the keypath if the key is found.
        >>> instance= self.get_instances(state='running')[0]
        >>> keypath = self.get_local_keypath(instance.key_name)
        """
        if path is None:
            path = os.getcwd()
        keypath = path + "/" + keyname + exten
        try:
            os.stat(keypath)
            self.debug("Found key at path:"+str(keypath))
        except:
            raise Exception("key:"+keyname+"not found at the provided path:"+str(path))
        return keypath
    
    def get_all_current_local_keys(self,path=None, exten=".pem"):
        """
        Convenience function to provide a list of all keys in the local dir at 'path' that exist on the server to help
        avoid producing additional keys in test dev.

        :param path: Filesystem path to search in
        :param exten: extension of private key file
        :return: list of key names
        """
        keylist = []
        keys = self.ec2.get_all_key_pairs()
        keyfile = None
        for k in keys:
            try:
                keypath = self.verify_local_keypath(k.name, path, exten)
                keyfile = open(keypath,'r')
                for line in keyfile.readlines():
                    if re.search('KEYPAIR',line):
                        fingerprint = line.split()[2]
                        break
                keyfile.close()
                if fingerprint == k.fingerprint:
                    self.debug('Found key:'+k.name)
                    keylist.append(k)
            except: pass
            finally:
                if keyfile and not keyfile.closed:
                    keyfile.close()
                
        return keylist

    def delete_keypair(self,keypair):

        """
        Delete the keypair object passed in and check that it no longer shows up

        :param keypair: Keypair object to delete and check
        :return: boolean of whether the operation succeeded
        """
        name = keypair.name
        self.debug(  "Sending delete for keypair: " + name)
        keypair.delete()
        try:
            keypair = self.ec2.get_all_key_pairs(keynames=[name])
        except EC2ResponseError:
            keypair = []
            
        if len(keypair) > 0:
            self.fail("Keypair found after attempt to delete it")
            return False
        return True
    
    def get_windows_instance_password(self, instance, private_key_path=None, key=None, dir=None, exten=".pem", encoded=True):
        """
        Get password for a windows instance.

        :param instance: euinstance object
        :param private_key_path: private key file used to decrypt password
        :param key: name of private key
        :param dir: Path to private key
        :param exten: extension of private key
        :param encoded: boolean of whether string returned from server is Base64 encoded
        :return: decrypted password
        :raise: Exception when private key cannot be found on filesystem
        """
        self.debug("get_windows_instance_password, instance:"+str(instance.id)+", keypath:"+str(private_key_path)+", dir:"+str(dir)+", exten:"+str(exten)+", encoded:"+str(encoded))
        try:
            from M2Crypto import RSA
            import base64
        except ImportError:
            raise ImportError("Unable to load M2Crypto. Please install by using your package manager to install "
                              "python-m2crypto or 'easy_install M2crypto'")
        key = key or self.get_keypair(instance.key_name)
        if private_key_path is None and key is not None:
            private_key_path = str(self.verify_local_keypath( key.name , dir, exten))
        if not private_key_path:
            raise Exception('get_windows_instance_password, keypath not found?')        
        encrypted_string = self.ec2.get_password_data(instance.id)
        user_priv_key = RSA.load_key(private_key_path)
        if encoded:
            string_to_decrypt = base64.b64decode(encrypted_string)
        else:
            string_to_decrypt = encrypted_string
        return user_priv_key.private_decrypt(string_to_decrypt,RSA.pkcs1_padding)

    def add_group(self, group_name=None, fail_if_exists=False ):
        """
        Add a security group to the system with name group_name, if it exists dont create it

        :param group_name: Name of the security group to create
        :param fail_if_exists: IF set, will fail if group already exists, otherwise will return the existing group
        :return: boto group object upon success or None for failure
        """
        if group_name is None:
            group_name = "group-" + str(int(time.time()))
        if self.check_group(group_name):
            if fail_if_exists:
                self.fail(  "Group " + group_name + " already exists")
            else:
                self.debug(  "Group " + group_name + " already exists")
                group = self.ec2.get_all_security_groups(group_name)[0]
            self.test_resources["security-groups"].append(group)
            return group
        else:
            self.debug( 'Creating Security Group: %s' % group_name)
            # Create a security group to control access to instance via SSH.
            group = self.ec2.create_security_group(group_name, group_name)
        return group

    def delete_group(self, group):
        """
        Delete the group object passed in and check that it no longer shows up

        :param group: Group object to delete and check
        :return: bool whether operation succeeded
        """
        name = group.name
        self.debug( "Sending delete for group: " + name )
        group.delete()
        if self.check_group(name):
            self.fail("Group found after attempt to delete it")
            return False
        return True

    def check_group(self, group_name):
        """
        Check if a group with group_name exists in the system

        :param group_name: Group name to check for existence
        :return: bool whether operation succeeded
        """
        self.debug( "Looking up group " + group_name )
        try:
            group = self.ec2.get_all_security_groups(groupnames=[group_name])
        except EC2ResponseError:
            return False
        
        if not group:
            return False
        else:
            return True

    def authorize_group_by_name(self,group_name="default", port=22, protocol="tcp", cidr_ip="0.0.0.0/0"):
        """
        Authorize the group with group_name

        :param group_name: Name of the group to authorize, default="default"
        :param port: Port to open, default=22
        :param protocol: Protocol to authorize, default=tcp
        :param cidr_ip: CIDR subnet to authorize, default="0.0.0.0/0" everything
        :return:

        """
        try:
            self.debug( "Attempting authorization of " + group_name + " on port " + str(port) + " " + protocol )
            self.ec2.authorize_security_group_deprecated(group_name,ip_protocol=protocol, from_port=port, to_port=port, cidr_ip=cidr_ip)
            return True
        except self.ec2.ResponseError, e:
            if e.code == 'InvalidPermission.Duplicate':
                self.debug( 'Security Group: %s already authorized' % group_name )
            else:
                raise


    def authorize_group(self, group, port=22, protocol="tcp", cidr_ip="0.0.0.0/0"):
        """
        Authorize the boto.group object

        :param group: boto.group object
        :param port: Port to open, default=22
        :param protocol: Protocol to authorize, default=tcp
        :param cidr_ip: CIDR subnet to authorize, default="0.0.0.0/0" everything
        :return: True on success
        :raise: Exception if operation fails
        """
        return self.authorize_group_by_name(group.name, port, protocol, cidr_ip)
    
    def terminate_single_instance(self, instance, timeout=300 ):
        """
        Terminate an instance

        :param instance: boto.instance object to terminate
        :param timeout: Time in seconds to wait for terminated state
        :return: True on success
        """
        instance.terminate()
        return self.wait_for_instance(instance, state='terminated', timeout=timeout)

    def wait_for_instance(self,instance, state="running", poll_count = None, timeout=480):
        """
        Wait for the instance to enter the state

        :param instance: Boto instance object to check the state on
        :param state: state that we are looking for
        :param poll_count: Number of 10 second poll intervals to wait before failure (for legacy test script support)
        :param timeout: Time in seconds to wait before failure
        :return: True on success
        :raise: Exception when instance does not enter proper state
        """
        if poll_count is not None:
            timeout = poll_count*10 
        self.debug( "Beginning poll loop for instance " + str(instance) + " to go to " + str(state) )
        instance.update()
        instance_original_state = instance.state
        start = time.time()
        elapsed = 0
        ### If the instance changes state or goes to the desired state before my poll count is complete
        while( elapsed <  timeout ) and (instance.state != state) and (instance.state != 'terminated'):
            #poll_count -= 1
            self.debug( "Instance("+instance.id+") State("+instance.state+"), elapsed:"+str(elapsed)+"/"+str(timeout))
            time.sleep(10)
            instance.update()
            elapsed = int(time.time()- start)
            if instance.state != instance_original_state:
                break
        self.debug("Instance("+instance.id+") State("+instance.state+") time elapsed (" +str(elapsed).split('.')[0]+")")
        #self.debug( "Waited a total o" + str( (self.poll_count - poll_count) * 10 ) + " seconds" )
        if instance.state != state:
            raise Exception( str(instance) + " did not enter "+str(state)+" state after elapsed:"+str(elapsed))

        self.debug( str(instance) + ' is now in ' + instance.state )
        return True

    def wait_for_reservation(self,reservation, state="running",timeout=480):
        """
        Wait for an entire reservation to enter the state

        :param reservation: Boto reservation object to check the state on
        :param state: state that we are looking for
        :param timeout: How long in seconds to wait for state
        :return: True on success
        """
        self.debug( "Beginning poll loop for the " + str(len(reservation.instances))   + " found in " + str(reservation) )
        aggregate_result = True
        for instance in reservation.instances:
            if not self.wait_for_instance(instance, state, timeout=timeout):
                aggregate_result = False
        return aggregate_result
    
    def create_volume(self, azone, size=1, eof=True, snapshot=None, timeout=0, poll_interval=10,timepergig=120):
        """
        Create a new EBS volume then wait for it to go to available state, size or snapshot is mandatory

        :param azone: Availability zone to create the volume in
        :param size: Size of the volume to be created
        :param count: Number of volumes to be created
        :param eof: Boolean, indicates whether to end on first instance of failure
        :param snapshot: Snapshot to create the volume from
        :param timeout: Time to wait before failing. timeout of 0 results in size of volume * timepergig seconds
        :param poll_interval: How often in seconds to poll volume state
        :param timepergig: Time to wait per gigabyte size of volume, used when timeout is set to 0
        :return:
        """
        return self.create_volumes(azone, size=size, count=1, mincount=1, eof=eof, snapshot=snapshot, timeout=timeout, poll_interval=poll_interval,timepergig=timepergig)[0]

    def create_volumes(self, 
                       azone, 
                       size = 1, 
                       count = 1, 
                       mincount = None, 
                       eof = True, 
                       monitor_to_state = 'available',
                       delay = 0, 
                       snapshot = None, 
                       timeout=0, 
                       poll_interval = 10,
                       timepergig = 120 ):
        """
        Definition:
                    Create a multiple new EBS volumes then wait for them to go to available state, 
                    size or snapshot is mandatory

        :param azone: Availability zone to create the volume in
        :param size: Size of the volume to be created
        :param count: Number of volumes to be created
        :param mincount: Minimum number of volumes to be created to be considered a success.Default = 'count'
        :param eof: Boolean, indicates whether to end on first instance of failure
        :param monitor_to_state: String, if not 'None' will monitor created volumes to the provided state
        :param snapshot: Snapshot to create the volume from
        :param timeout: Time to wait before failing. timeout of 0 results in size of volume * timepergig seconds
        :param poll_interval: How often in seconds to poll volume state
        :param timepergig: Time to wait per gigabyte size of volume, used when timeout is set to 0
        :return: list of volumes
        """
        start = time.time()
        elapsed = 0
        volumes = []
        
        mincount = mincount or count
        if mincount > count:
            raise Exception('Mincount can not be greater than count')
        #if timeout is set to 0, use size to create a reasonable timeout for this volume creation
        if timeout == 0:
            if snapshot is not None:
                timeout = timepergig * int(snapshot.volume_size)
            else:
                timeout = timepergig * size
        
        if snapshot and not hasattr(snapshot,'eutest_volumes'):
                snapshot = self.get_snapshot(snapshot.id)
        self.debug( "Sending create volume request, count:"+str(count) )
        for x in xrange(0,count):
            vol = None
            try:
                cmdstart = time.time()
                vol = self.ec2.create_volume(size, azone, snapshot)
                cmdtime =  time.time() - cmdstart 
                if vol:
                    vol = EuVolume.make_euvol_from_vol(vol, cmdstart=cmdstart)
                    vol.eutest_cmdstart = cmdstart
                    vol.eutest_createorder = x
                    vol.eutest_cmdtime = "{0:.2f}".format(cmdtime)
                    vol.size = size
                    volumes.append(vol)
            except Exception, e:
                if eof:
                    #Clean up any volumes from this operation and raise exception
                    for vol in volumes:
                        vol.delete()
                    raise e
                else:
                    self.debug("Caught exception creating volume,eof is False, continuing. Error:"+str(e))
            if delay:
                time.sleep(delay)
        if len(volumes) < mincount:
             #Clean up any volumes from this operation and raise exception
            for vol in volumes:
                vol.delete()
            raise Exception("Created "+str(len(retlist))+"/"+str(count)+' volumes. Less than minimum specified:'+str(mincount))
        self.debug( str(len(volumes))+"/"+str(count)+" requests for volume creation succeeded." )
        
        if volumes:
            self.print_euvolume_list(volumes)
        
        if not monitor_to_state:
            self.test_resources["volumes"].extend(volumes)
            if snapshot:
                snapshot.eutest_volumes.extend(volumes)
            return volumes
        #If we begain the creation of the min volumes, monitor till completion, otherwise cleanup and fail out
        retlist = self.monitor_created_euvolumes_to_state(volumes,eof=eof, mincount=mincount, state=monitor_to_state, poll_interval=poll_interval, timepergig=timepergig)
        self.test_resources["volumes"].extend(retlist)
        if snapshot:
            snapshot.eutest_volumes.extend(retlist)
        return retlist
    

    def monitor_created_euvolumes_to_state(self, volumes, eof=True, mincount=None, state='available', poll_interval=10, deletefailed=True, size=1, timepergig=120):
        '''
        Description:
                    Monitors a list of created volumes until 'state' or failure. Allows for a variety of volumes, using differnt
                     types and creation methods to be monitored by a central method. 
        :param volumes: list of created volumes
        :param eof: boolean, if True will end on first failure
        :param mincount: minimum number of successful volumes, else fail
        :param state: string indicating the expected state to monitor to 
        :param deletefailed: delete all failed volumes, in eof case deletes 'volumes' list. In non-eof, if mincount is met, will delete any failed volumes. 
        :param timepergig: integer, time allowed per gig before failing.
        '''
        
        retlist = []
        failed = []
        
        if not volumes:
            raise Exception("Volumes list empty in monitor_created_volumes_to_state")
        count = len(volumes)
        mincount = mincount or count 
        self.debug("Monitoring "+str(count)+" volumes for at least "+str(mincount)+" to reach state:"+str(state))
        origlist = copy.copy(volumes)
        self.debug("Monitoring "+str(count)+" volumes for at least "+str(mincount)+" to reach state:"+str(state))
        for volume in volumes:
            if not isinstance(volume, EuVolume):
                raise Exception("object not of type EuVolume. Found type:"+str(type(volume)))
        #volume = EuVolume()
        # Wait for the volume to be created.
        self.debug( "Polling "+str(len(volumes))+" volumes for status:\""+str(state)+"\"...")
        start = time.time()
        while volumes:
            for volume in volumes:
                volume.update()
                voltimeout = timepergig * (volume.size or size)
                elapsed = time.time()-start
                self.debug("Volume #"+str(volume.eutest_createorder)+" ("+volume.id+") State("+volume.status+"), seconds elapsed: " + str(int(elapsed))+'/'+str(voltimeout))
                if volume.status == state:
                    #add to return list and remove from volumes list
                    retlist.append(volumes.pop(volumes.index(volume)))
                else:
                    if elapsed > voltimeout:
                        volume.status = 'timed-out'
                    if volume.status == 'failed' or volume.status == 'timed-out':
                        if eof:
                            #Clean up any volumes from this operation and raise exception
                            if deletefailed:
                                for vol in origlist:
                                    self.debug('Failure caught in monitor volumes, attempting to delete all volumes...')
                                    try:
                                        self.delete_volume(vol)
                                    except Exception, e:
                                        self.debug('Could not delete volume:'+str(vol.id)+", err:"+str(e))
                            raise Exception(str(volume) + ", failed to reach state:"+str(state)+", vol status:"+str(volume.eutest_laststatus)+", test status:"+str(vol.status))
                        else:
                            #End on failure is not set, so record this failure and move on
                            msg = str(volume) + " went to: " + volume.status
                            self.debug(msg)
                            volume.eutest_failmsg = msg
                            failed.append(volumes.pop(volumes.index(volume)))
                    #Fail fast if we know we've exceeded our mincount already
                    if (count - len(failed)) < mincount:
                        if deletefailed:
                            for failedvol in failed:
                                retlist.remove(failedvol)
                                buf += str(failedvol.id)+"-state:"+str(failedvol.status)+","
                                self.debug(buf)
                            for vol in origlist:
                                self.debug('Failure caught in monitor volumes, attempting to delete all volumes...')
                                try:
                                    self.delete_volume(vol)
                                except Exception, e:
                                    self.debug('Could not delete volume:'+str(vol.id)+", err:"+str(e))
                        raise Exception("Mincount of volumes did not enter state:"+str(state)+" due to faults")
            self.debug("----Time Elapsed:"+str(int(elapsed))+", Waiting on "+str(len(volumes))+" volumes to enter state:"+str(state)+"-----")
            if volumes:
                time.sleep(poll_interval)
            else:
                break
        #We have at least mincount of volumes, delete any failed volumes
        if failed and deletefailed:
            self.debug( "Deleting volumes that never became available...")
            for volume in failed:
                self.debug('Failure caught in monitor volumes, attempting to delete all volumes...')
                try:
                    self.delete_volume(volume)
                except Exception, e:
                    self.debug('Could not delete volume:'+str(volume.id)+", err:"+str(e))
            buf = str(len(failed))+'/'+str(count)+ " Failed volumes after " +str(elapsed)+" seconds:"
            for failedvol in failed:
                retlist.remove(failedvol)
                buf += str(failedvol.id)+"-state:"+str(failedvol.status)+","
                self.debug(buf)
        self.print_euvolume_list(origlist)
        return retlist
                
    def print_euvolume_list(self,euvolumelist):
        buf=""
        euvolumes = copy.copy(euvolumelist)
        if not euvolumes:
            raise Exception('print_euvolume_list: Euvolume list to print is empty')
        for volume in euvolumes:
            if not isinstance(volume, EuVolume):
                raise Exception("object not of type EuVolume. Found type:"+str(type(volume)))
        volume = euvolumes.pop()
        buf = volume.printself()
        for volume in euvolumes:
            buf += volume.printself(title=False)
        self.debug("\n"+str(buf)+"\n")
        
    def print_eusnapshot_list(self,eusnapshots):
        buf=""
        if not eusnapshots:
            raise Exception('print_eusnapshot_list: EuSnapshot list to print is empty')
        for snapshot in eusnapshots:
            if not isinstance(snapshot, EuSnapshot):
                raise Exception("object not of type EuSnapshot. Found type:"+str(type(snapshot)))
        snapshot = eusnapshots.pop()
        buf = snapshot.printself()
        for snapshot in eusnapshots:
            buf += snapshot.printself(title=False)
        self.debug("\n"+str(buf)+"\n")
        

    def delete_volume(self, volume, poll_interval=10, timeout=120):
        """
        Delete the EBS volume then check that it no longer exists

        :param volume: Volume object to delete
        :return: bool, success of the operation
        """
        self.ec2.delete_volume(volume.id)
        self.debug( "Sent delete for volume: " +  str(volume.id)  )
        start = time.time()
        elapsed = 0
        volume.update()
        while elapsed < timeout:
            self.debug( str(volume) + " in " + volume.status + " sleeping:"+str(poll_interval)+", elapsed:"+str(elapsed))
            time.sleep(poll_interval)
            volume.update()
            elapsed = int(time.time()-start)
            if volume.status == "deleted":
                break

        if volume.status != 'deleted':
            self.fail(str(volume) + " left in " +  volume.status + ',elapsed:'+str(elapsed))
            return False
        return True
    
    def delete_volumes(self, volume_list, poll_interval=10, timeout=120):
        """
        Deletes a list of EBS volumes then checks for proper state transition

        :param volume_list: List of volume objects to be deleted
        :param poll_interval: integer, seconds between polls on volumes' state
        :param timeout: integer time allowed before this method fails
        """
        if volume_list:
            vollist = copy.copy(volume_list)
        else:
            raise Exception("delete_volumes: volume_list was empty")
        for volume in vollist:
            self.ec2.delete_volume(volume.id)
            self.debug( "Sent delete for volume: " +  str(volume.id)  )
        start = time.time()
        elapsed = 0
        while vollist and elapsed < timeout:
            for volume in vollist:
                volume.update()
                self.debug( str(volume) + " in " + volume.status)
                volume.update()
                if volume.status == "deleted":
                    vollist.remove(volume)
                elapsed = int(time.time()-start)
                self.debug("---Sleeping:"+str(poll_interval)+", elapsed:"+str(elapsed)+"---")
                time.sleep(poll_interval)
        if vollist:
            errmsg =""
            for volume in vollist:
                errmsg += "ERROR:"+str(volume) + " left in " +  volume.status + ',elapsed:'+str(elapsed)
            raise Exception(errmsg)
        
        
        
    def delete_all_volumes(self):
        """
        Deletes all volumes on the cloud
        """
        volumes = self.ec2.get_all_volumes()
        for volume in volumes:
            self.delete_volume(volume.id)
        """

        instance
        volume
        device_path
        """
    def attach_volume(self, instance, volume, device_path, pause=10, timeout=120):
        """
        Attach a volume to an instance

        :param instance: instance object to attach volume to
        :param volume: volume object to attach
        :param device_path: device name to request on guest
        :param pause: Time in seconds to wait before checking volume state
        :param timeout: Total time in seconds to wait for volume to reach the attached state
        :return:
        :raise: Exception of failure to reach proper state or enter previous state
        """
        self.debug("Sending attach for " + str(volume) + " to be attached to " + str(instance) + " at requested device  " + device_path)
        volume.attach(instance.id,device_path )
        start = time.time()
        elapsed = 0  
        volume.update()
        status = ""
        laststatus=None
        while elapsed < timeout:
            volume.update()
            astatus=None
            if volume.attach_data is not None:
                if re.search("attached",str(volume.attach_data.status)):
                    self.debug(str(volume) + ", Attached: " +  volume.status+ " - " + str(volume.attach_data.status) + ", elapsed:"+str(elapsed))
                    return True
                else:
                    astatus = volume.attach_data.status
                    if astatus:
                        laststatus = astatus
                    elif laststatus and not astatus:
                        raise Exception('Volume status reverted from '+str(laststatus)+' to None, attach failed')
            self.debug( str(volume) + ", state:" + volume.status+', attached status:'+str(astatus) + ", elapsed:"+str(elapsed)+'/'+str(timeout))
            self.sleep(pause)
            elapsed = int(time.time()-start)


        """

        volume
        """
    
    def detach_volume(self, volume, pause = 10, timeout=60):
        """
        Detach a volume

        :param volume: volume to detach
        :param pause: Time in seconds to wait before checking volume state
        :param timeout: Total time in seconds to wait for volume to reach the attached state
        :return: True on success
        """
        if volume is None:
            raise Exception(str(volume) + " does not exist")
        volume.detach()
        self.debug( "Sent detach for volume: " + volume.id + " which is currently in state: " + volume.status)
        start = time.time()
        elapsed = 0  
        while elapsed < timeout:
            volume.update()
            if volume.status != "in-use":
                self.debug(str(volume) + " left in " +  volume.status)
                return True
            self.debug( str(volume) + " state:" + volume.status + " pause:"+str(pause)+" elapsed:"+str(elapsed))
            self.sleep(pause)
            elapsed = int(time.time() - start)
        raise Exception('Volume status remained at '+str(volume.status)+', attach failed')
    
    def get_volume_time_attached(self,volume):
        '''
        Get the seconds elapsed since the volume was attached.
        
        :type volume: boto volume object
        :param volume: The volume used to calculate the elapsed time since attached. 
        
        :rtype: integer
        :returns: The number of seconds elapsed since this volume was attached. 
        '''
        self.debug("Getting time elapsed since volume attached...")
        volume.update()
        if volume.attach_data is None:
            raise Exception('get_time_since_vol_attached: Volume '+str(volume.id)+" not attached")
        #get timestamp from attach_data
        attached_time = self.get_datetime_from_resource_string(volume.attach_data.attach_time)
        #return the elapsed time in seconds
        return time.mktime(datetime.utcnow().utctimetuple()) - time.mktime(attached_time.utctimetuple())
    
    @classmethod
    def get_volume_time_created(cls,volume):
        '''
        Get the seconds elapsed since the volume was created.
        
        :type volume: boto volume object
        :param volume: The volume used to calculate the elapsed time since created. 
        
        :rtype: integer
        :returns: The number of seconds elapsed since this volume was created. 
        '''
        volume.update()
        #get timestamp from attach_data
        create_time = cls.get_datetime_from_resource_string(volume.create_time)
        #return the elapsed time in seconds
        return time.mktime(datetime.utcnow().utctimetuple()) - time.mktime(create_time.utctimetuple())
    
    @classmethod
    def get_snapshot_time_started(cls,snapshot):
        '''
        Get the seconds elapsed since the snapshot was started.
        
        :type snapshot: boto snapshot object
        :param snapshot: The volume used to calculate the elapsed time since started. 
        
        :rtype: integer
        :returns: The number of seconds elapsed since this snapshot was started. 
        '''
        snapshot.update()
        #get timestamp from attach_data
        start_time = cls.get_datetime_from_resource_string(snapshot.start_time)
        #return the elapsed time in seconds
        return time.mktime(datetime.utcnow().utctimetuple()) - time.mktime(start_time.utctimetuple())
    
    @classmethod
    def get_instance_time_launched(cls,instance):
        '''
        Get the seconds elapsed since the volume was attached.
        
        :type volume: boto volume object
        :param volume: The volume used to calculate the elapsed time since attached. 
        
        :rtype: integer
        :returns: The number of seconds elapsed since this volume was attached. 
        '''
        instance.update()
        #get timestamp from launch data
        launch_time = cls.get_datetime_from_resource_string(instance.launch_time)
        #return the elapsed time in seconds
        return time.mktime(datetime.utcnow().utctimetuple()) - time.mktime(launch_time.utctimetuple())
    
    @classmethod
    def get_datetime_from_resource_string(cls,timestamp):
        '''
        Convert a typical resource timestamp to datetime time_struct.
        
        :type timestamp: string
        :param timestamp: Timestamp held within specific boto resource objects.Example timestamp format: 2012-09-19T21:24:03.864Z
        
        :rtype: time_struct
        :returns: The time_struct representation of the timestamp provided. 
        '''
        t = re.findall('\w+',str(timestamp).replace('T',' '))
        #remove milliseconds from list...
        t.pop()
        #create a time_struct out of our list
        return datetime.strptime(" ".join(t), "%Y %m %d %H %M %S")
    
    def create_snapshot_from_volume(self, volume, wait_on_progress=20, poll_interval=10, timeout=0, description=""):
        """
        Create a new EBS snapshot from an existing volume then wait for it to go to the created state.
        By default will poll for poll_count.  If wait_on_progress is specified than will wait on "wait_on_progress"
        overrides # of poll_interval periods, using wait_on_progress # of periods of poll_interval length in seconds
        w/o progress before failing. If volume.id is passed, euvolume data will not be transfered to snapshot created. 

        :param volume: (mandatory Volume) Volume id of the volume to create snapshot from
        :param wait_on_progress: (optional string) string used to describe the snapshot
        :param poll_interval: (optional integer) # of poll intervals to wait while 0 progress is made before exiting, overrides "poll_count" when used
        :param timeout: (optional integer) time to sleep between polling snapshot status
        :param description: (optional integer) over all time to wait before exiting as failure
        :return: EuSnapshot
        """
        return self.create_snapshots(volume, count=1, mincount=1, eof=True, wait_on_progress=wait_on_progress, poll_interval=poll_interval, timeout=timeout, description=description)[0]
        
    
    def create_snapshot(self, volume_id, wait_on_progress=20, poll_interval=10, timeout=0, description=""):
        """
        Create a new single EBS snapshot from an existing volume id then wait for it to go to the created state.
        By default will poll for poll_count.  If wait_on_progress is specified than will wait on "wait_on_progress"
        overrides # of poll_interval periods, using wait_on_progress # of periods of poll_interval length in seconds
        w/o progress before failing. If volume.id is passed, euvolume data will not be transfered to snapshot created. 

        :param volume: (mandatory string) Volume id of the volume to create snapshot from
        :param wait_on_progress: (optional string) string used to describe the snapshot
        :param poll_interval: (optional integer) # of poll intervals to wait while 0 progress is made before exiting, overrides "poll_count" when used
        :param timeout: (optional integer) time to sleep between polling snapshot status
        :param description: (optional integer) over all time to wait before exiting as failure
        :return: EuSnapshot
        """
        snapshots = self.create_snapshots_from_vol_id(volume_id, count=1, mincount=1, eof=True, wait_on_progress=wait_on_progress, poll_interval=poll_interval, timeout=timeout, description=description)
        if len(snapshots) == 1:
            return snapshots[0]
        else:
            raise Exception("create_snapshot: Expected 1 snapshot, got '"+str(len(snapshots))+"' snapshots")
    
    def create_snapshots_from_vol_id(self,volume_id, count=1, mincount=None, eof=True, delay=0, wait_on_progress=20, poll_interval=10, timeout=0, description=""):
        """
        Create a new EBS snapshot from an existing volume' string then wait for it to go to the created state.
        By default will poll for poll_count.  If wait_on_progress is specified than will wait on "wait_on_progress"
        overrides # of poll_interval periods, using wait_on_progress # of periods of poll_interval length in seconds
        w/o progress before failing

        :param volume_id: (mandatory string) Volume id of the volume to create snapshot from
        :parram count: (optional Integer) Specify how many snapshots to attempt to create
        :param mincount: (optional Integer) Specify the min success count, defaults to 'count'
        :param eof: (optional boolean) End on failure.If true will end on first failure, otherwise will continue to try and fufill mincount
        :param wait_on_progress: (optional string) string used to describe the snapshot
        :param poll_interval: (optional integer) # of poll intervals to wait while 0 progress is made before exiting, overrides "poll_count" when used
        :param timeout: (optional integer) time to sleep between polling snapshot status
        :param description: (optional integer) over all time to wait before exiting as failure
        :return: EuSnapshot list
        """
        if isinstance(volume_id, Volume):
            raise Exception('Expected volume.id got Volume, try create_snapshots or create_snapshot_from_volume methods instead')
        volume = EuVolume.make_euvol_from_vol(self.get_volume(volume_id))
        return self.create_snapshots(volume, count=count, mincount=mincount, eof=eof, delay=delay, wait_on_progress=wait_on_progress, poll_interval=poll_interval, timeout=timeout, description=description)


    def create_snapshots(self, volume, count=1, mincount=None, eof=True, delay=0, wait_on_progress=20, poll_interval=10, timeout=0, description=""):
        """
        Create a new EBS snapshot from an existing volume then wait for it to go to the created state.
        By default will poll for poll_count.  If wait_on_progress is specified than will wait on "wait_on_progress"
        overrides # of poll_interval periods, using wait_on_progress # of periods of poll_interval length in seconds
        w/o progress before failing

        :param volume: (mandatory Volume object) Volume to create snapshot from
        :parram count: (optional Integer) Specify how many snapshots to attempt to create
        :param mincount: (optional Integer) Specify the min success count, defaults to 'count'
        :param eof: (optional boolean) End on failure.If true will end on first failure, otherwise will continue to try and fufill mincount
        :param wait_on_progress: (optional string) string used to describe the snapshot
        :param poll_interval: (optional integer) # of poll intervals to wait while 0 progress is made before exiting, overrides "poll_count" when used
        :param timeout: (optional integer) time to sleep between polling snapshot status
        :param description: (optional integer) over all time to wait before exiting as failure
        :return: EuSnapshot list
        """
        #Fix EuSnapshot for isinstance() use later...
        if not hasattr(volume, 'md5'):
            volume = EuVolume.make_euvol_from_vol(volume)
        volume_id = volume.id
        snapshots = []
        retlist = []
        failed = []
        mincount = mincount or count
        if mincount > count:
            raise Exception('Mincount can not be greater than count')
        if wait_on_progress > 0:
            poll_count = wait_on_progress
        else:
            poll_count = self.poll_count
        last_progress = 0
        elapsed = 0
        polls = 0
        snap_start = time.time()
        self.debug('Create_snapshots count:'+str(count)+", mincount:"+str(mincount)+', wait_on_progress:'+str(wait_on_progress)+",eof:"+str(eof))
        for x in xrange(0,count):
            try:
                start = time.time()
                snapshot = self.ec2.create_snapshot( volume_id )
                cmdtime = time.time()-start
                if snapshot:
                    self.debug("Attempting to create snapshot #"+str(x)+ ", id:"+str(snapshot.id))
                    snapshot = EuSnapshot().make_eusnap_from_snap(snapshot, cmdstart=start)
                    #Append some attributes for tracking snapshot through creation and test lifecycle.
                    snapshot.eutest_polls = 0
                    snapshot.eutest_poll_count = poll_count
                    snapshot.eutest_last_progress = 0
                    snapshot.eutest_failmsg = "FAILED"
                    snapshot.eutest_laststatus = None
                    snapshot.eutest_timeintest = 0
                    snapshot.eutest_createorder = x
                    snapshot.eutest_cmdtime = "{0:.2f}".format(cmdtime)
                    snapshot.eutest_volume_md5 = volume.md5
                    snapshot.eutest_volume_md5len = volume.md5len
                    snapshot.eutest_volume_zone = volume.zone
                    
                    if snapshot:
                        snapshots.append(snapshot)
            except Exception, e:
                if eof:
                    raise e
                else:
                    self.debug("Caught exception creating snapshot,eof is False, continuing. Error:"+str(e)) 
            if delay:
                time.sleep(delay)
              
        self.debug('Waiting for '+str(len(snapshots))+" snapshots to go to completed state...")
        while (timeout == 0 or elapsed <= timeout) and snapshots:
            time.sleep(poll_interval)
            self.debug("Waiting for "+str(len(snapshots))+" snapshots to complete creation")
            for snapshot in snapshots:
                try:
                    snapshot.eutest_polls += 1
                    snapshot.update()
                    snapshot.eutest_laststatus = snapshot.status
                    if snapshot.status == 'failed':
                        raise Exception(str(snapshot) + " failed after Polling("+str(snapshot.eutest_polls)+") ,Waited("+str(elapsed)+" sec), last reported (status:" + snapshot.status+" progress:"+snapshot.progress+")")
                    curr_progress = int(snapshot.progress.replace('%',''))
                    #if progress was made, then reset timer 
                    if (wait_on_progress > 0) and (curr_progress > snapshot.eutest_last_progress):
                        snapshot.eutest_poll_count = wait_on_progress
                    else: 
                        snapshot.eutest_poll_count -= 1
                    snapshot.eutest_last_progress = curr_progress
                    elapsed = int(time.time()-snap_start)
                    if snapshot.eutest_poll_count <= 0:
                        raise Exception("Snapshot did not make progress for "+str(wait_on_progress)+" polls, after "+str(elapsed)+" seconds")
                    self.debug(str(snapshot.id)+", Status:"+snapshot.status+", Progress:"+snapshot.progress+", Polls w/o progress:"+str(wait_on_progress-snapshot.eutest_poll_count)+"/"+str(wait_on_progress)+", Time Elapsed:"+str(elapsed))    
                    if snapshot.status == 'completed':
                        self.debug(str(snapshot.id)+" created after " + str(elapsed) + " seconds. Status:"+snapshot.status+", Progress:"+snapshot.progress)
                        self.test_resources["snapshots"].append(snapshot)
                        snapshot.eutest_timeintest = elapsed
                        snapshot.eutest_failmsg ='SUCCESS'
                        retlist.append(snapshot)
                        snapshots.remove(snapshot)
                except Exception, e:
                    if eof:
                        #If exit on fail, delete all snaps and raise exception
                        for snap in snapshots:
                            snap.delete()
                        raise e
                    else:
                        self.debug("Exception caught in snapshot creation, snapshot:"+str(snapshot.id)+".Err:"+str(e))
                        snapshot.eutest_failmsg = str(e)
                        snapshot.eutest_timeintest = elapsed
                        failed.append(snapshot)
                        snapshots.remove(snapshot)
        elapsed = int(time.time()-snap_start)
        for snap in snapshots:
            snapshot.eutest_failmsg = "Snapshot timed out in creation after "+str(elapsed)+" seconds"
            snapshot.eutest_timeintest = elapsed
            failed.append(snapshot)
            snapshots.remove(snapshot)
            
        for snap in failed:
            try:
                snap.delete()
                self.debug("Removed failed snapshot:"+str(snap.id))
            except: pass
            
        #join the lists again for debug purposes
        snapshots = copy.copy(retlist)
        snapshots.extend(failed)
        #Print the results in a formated table
        self.print_eusnapshot_list(snapshots)
        #Check for failure and failure criteria and return 
        #self.fail(str(snapshot) + " failed after Polling("+str(polls)+") ,Waited("+str(elapsed)+" sec), last reported (status:" + snapshot.status+" progress:"+snapshot.progress+")")
        self.test_resources['snapshots'].extend(snapshots)
        if failed and eof:
            raise(str(len(failed))+' snapshots failed in create, see debug output for more info')
        if len(retlist) < mincount:
            raise('Created '+str(len(retlist))+'/'+str(count)+' snapshots is less than provided mincount, see debug output for more info')
        return retlist
    
    
    def get_snapshot(self,snapid=None):
        snaps = self.get_snapshots(snapid=snapid, maxcount=1)
        if snaps:
            return snaps[0]
        else:
            return None
        
    def get_snapshots(self,snapid=None, volume_id=None, volume_size=None, volume_md5=None, maxcount=None):
        retlist =[]
        snapshots = self.test_resources['snapshots']
        snapshots.extend( self.ec2.get_all_snapshots())
        for snap in snapshots:
            if not hasattr(snap,'eutest_volume_md5'):
                snap = EuSnapshot.make_eusnap_from_snap(snap)
            self.debug("Checking snap:"+str(snap.id)+" for match...")
            if snapid and snap.id != snapid:
                continue
            if volume_id and snap.volume_id != volume_id:
                continue
            if volume_size and snap.volume_size != volume_size:
                continue
            if volume_md5 and snap.eutest_volume_md5 != volume_md5:
                continue
            retlist.append(snap)
            if maxcount and (len(retlist) >= maxcount):
                return retlist
        self.debug("Found "+str(len(retlist))+" snapshots matching criteria")
        return retlist
    
        
    
    def delete_snapshot(self,snapshot,timeout=60):
        """
        Delete the snapshot object

        :param snapshot: boto.ec2.snapshot object to delete
        :param timeout: Time in seconds to wait for deletion
        """
        snapshot.delete()
        self.debug( "Sent snapshot delete request for snapshot: " + snapshot.id)
        start = time.time()
        elapsed = 0
        while ( len(self.ec2.get_all_snapshots(snapshot_ids=[snapshot.id])) > 0) and (elapsed < timeout):
            self.sleep(10)
            elapsed = int(time.time()-start)
            self.debug(str(snapshot) + " status " +  snapshot.status + " with " + str(snapshot.progress) + "% progress. Elapsed:"+str(elapsed))
        if len(self.ec2.get_all_snapshots(snapshot_ids=[snapshot.id])) > 0:
            raise Exception(str(snapshot) + " left in" +  snapshot.status + " with " + str(snapshot.progress) + "% progress. Elapsed:"+str(elapsed))
    
    def register_snapshot(self, snapshot, rdn="/dev/sda1", description="bfebs", windows=False, bdmdev=None, name=None, ramdisk=None, kernel=None, dot=True):
        """Convience function for passing a snapshot instead of its id. See register_snapshot_by_id"""
        return self.register_snapshot_by_id( snapshot.id, rdn, description, windows, bdmdev, name, ramdisk, kernel, dot )
    """

    snap_id
    name
    description    (optional string)
    bdmdev         (optional string)
    rdn            (optional string)
    dot            (optional boolean)
    windows        (optional boolean)
    kernel         (optional string)
    """
    def register_snapshot_by_id( self, snap_id, rdn="/dev/sda1", description="bfebs", windows=False, bdmdev=None, name=None, ramdisk=None, kernel=None, dot=True ):
        """
        Register an image snapshot

        :param snap_id: snapshot id
        :param rdn: root-device-name for image
        :param description: description of image to be registered
        :param windows: Is windows image boolean
        :param bdmdev: block-device-mapping device for image
        :param name: name of image to be registered
        :param ramdisk: ramdisk id
        :param kernel: kernel id (note for windows this name should be "windows")
        :param dot: Delete On Terminate boolean
        :return: emi id of registered image
        """
        if bdmdev is None:
            bdmdev=rdn
        if name is None:
            name="bfebs_"+ snap_id
        if ( windows is True ) and ( kernel is not None):
            kernel="windows"     
            
        bdmap = BlockDeviceMapping()
        block_dev_type = BlockDeviceType()
        block_dev_type.snapshot_id = snap_id
        block_dev_type.delete_on_termination = dot
        bdmap[bdmdev] = block_dev_type
            
        self.debug("Register image with: snap_id:"+str(snap_id)+", rdn:"+str(rdn)+", desc:"+str(description)+", windows:"+str(windows)+", bdname:"+str(bdmdev)+", name:"+str(name)+", ramdisk:"+str(ramdisk)+", kernel:"+str(kernel))
        image_id = self.ec2.register_image(name=name, description=description, kernel_id=kernel, ramdisk_id=ramdisk, block_device_map=bdmap, root_device_name=rdn)
        self.debug("Image now registered as " + image_id)
        return image_id

    def register_image( self, image_location, rdn=None, description=None, bdmdev=None, name=None, ramdisk=None, kernel=None ):
        """
        Register an image based on the s3 stored manifest location

        :param image_location:
        :param rdn: root-device-name for image
        :param description: description of image to be registered
        :param bdmdev: block-device-mapping object for image
        :param name: name of image to be registered
        :param ramdisk: ramdisk id
        :param kernel: kernel id (note for windows this name should be "windows")
        :return: image id string
        """
        image_id = self.ec2.register_image(name=name, description=description, kernel_id=kernel, image_location=image_location, ramdisk_id=ramdisk, block_device_map=bdmdev, root_device_name=rdn)
        self.test_resources["images"].append(image_id)
        return image_id

    def deregister_image(self, image, clear=False):
        """
        Deregister an image.

        :param image: boto image object to deregister
        """
        self.ec2.deregister_image(image.id)
        image = self.get_emi(image.id)
        if image.state is not "deregistered":
            raise Exception("Image " + image.id +  " did not enter deregistered state after deregistration was sent to server")
        else:
            if clear:
                self.ec2.deregister_image(image.id)

    def get_emi(self, emi=None, root_device_type=None, root_device_name=None, location=None, state="available", arch=None, owner_id=None, not_location=None):
        """
        Get an emi with name emi, or just grab any emi in the system. Additional 'optional' match criteria can be defined.

        :param emi: Partial ID of the emi to return, defaults to the 'emi-" prefix to grab any
        :param root_device_type: example: 'instance-store' or 'ebs'
        :param root_device_name: example: '/dev/sdb'
        :param location: partial on location match example: 'centos'
        :param state: example: 'available'
        :param arch: example: 'x86_64'
        :param owner_id: owners numeric id
        :param not_location: skip if location string matches this string. Example: not_location='windows'
        :return: image id
        :raise: Exception if image is not found
        """
        if emi is None:
            emi = "mi-"
        self.debug("Looking for image prefix: " + str(emi) )
            
        images = self.ec2.get_all_images()
        for image in images:
            
            if not re.search(emi, image.id):      
                continue  
            if (root_device_type is not None) and (image.root_device_type != root_device_type):
                continue            
            if (root_device_name is not None) and (image.root_device_name != root_device_name):
                continue       
            if (state is not None) and (image.state != state):
                continue            
            if (location is not None) and (not re.search( location, image.location)):
                continue           
            if (arch is not None) and (image.architecture != arch):
                continue                
            if (owner_id is not None) and (image.owner_id != owner_id):
                continue
            if (not_location is not None) and (re.search( not_location, image.location)):
                continue
            self.debug("Returning image:"+str(image.id))
            return image
        raise Exception("Unable to find an EMI")
        return None
    
    def get_all_allocated_addresses(self,account_id=None):
        """
        Return all allocated addresses for a given account_id as boto.ec2.address objects

        :param account_id: account number to filter on
        :return: list of boto.ec2.address objects
        """
        self.debug("get_all_allocated_addresses...")
        account_id = account_id or self.get_account_id()
        ret = []
        if account_id:
            account_id = str(account_id)
            addrs = self.ec2.get_all_addresses()
            for addr in addrs:
                if addr.instance_id and re.search(account_id, str(addr.instance_id)):
                    ret.append(addr)
        return ret
    
    def get_available_addresses(self):
        """
        Get all available addresses

        :return: a list of all available boto.ec2.address
        """
        self.debug("get_available_addresses...")
        ret = []
        addrs = self.ec2.get_all_addresses()
        for addr in addrs:
            if addr.instance_id and re.search(r"(available|nobody)", addr.instance_id):
                ret.append(addr)
        return ret
    
    
    def allocate_address(self):
        """
        Allocate an address for the current user

        :return: boto.ec2.address object allocated
        """
        try:
            self.debug("Allocating an address")
            address = self.ec2.allocate_address()
        except Exception, e:
            self.critical("Unable to allocate address")
            return False
        self.debug("Allocated " + str(address))
        return address

    def associate_address(self,instance, address, timeout=75):
        """
        Associate an address object with an instance

        :param instance: instance object to associate ip with
        :param address: address to associate to instance
        :param timeout: Time in seconds to wait for operation to complete
        :raise: Exception in case of association failure
        """
        ip =  str(address.public_ip)
        self.debug("Attemtping to associate " + str(ip) + " with " + str(instance.id))
        try:
            address.associate(instance.id)
        except Exception, e:
            self.critical("Unable to associate address "+str(ip)+" with instance:"+str(instance.id)+"\n")
            raise e
        
        start = time.time()
        elapsed = 0
        address = self.ec2.get_all_addresses(addresses=[ip])[0] 
        ### Ensure address object holds correct instance value
        while not address.instance_id:
            if elapsed > timeout:
                raise Exception('Address ' + str(ip) + ' never associated with instance')
            self.debug('Address {0} not attached to {1} but rather {2}'.format(str(address), instance.id, address.instance_id) )
            self.sleep(5)
            address = self.ec2.get_all_addresses(addresses=[ip])[0]
            elapsed = int(time.time()-start)

        poll_count = 15
        ### Ensure instance gets correct address
        while instance.ip_address not in address.public_ip:
            if elapsed > timeout:
                raise Exception('Address ' + str(address) + ' did not associate with instance after:'+str(elapsed)+" seconds")
            self.debug('Instance {0} has IP {1} attached instead of {2}'.format(instance.id, instance.public_dns_name, address.public_ip) )
            self.sleep(5)
            instance.update()
            elapsed = int(time.time()-start)
        self.debug("Associated IP successfully")

    def disassociate_address_from_instance(self, instance, timeout=75):
        """
        Disassociate address from instance and ensure that it no longer holds the IP

        :param instance: An instance that has an IP allocated
        :param timeout: Time in seconds to wait for address to disassociate
        :raise:
        """
        self.debug("disassociate_address_from_instance: instance.public_dns_name:" + str(instance.public_dns_name) + " instance:" + str(instance))
        ip=str(instance.public_dns_name)
        address = self.ec2.get_all_addresses(addresses=[instance.public_dns_name])[0]
        
        
        start = time.time()
        elapsed = 0
      
        address = self.ec2.get_all_addresses(addresses=[address.public_ip])[0]
        ### Ensure address object hold correct instance value
        while address.instance_id and not re.match(instance.id, str(address.instance_id)):
            self.debug('Address {0} not attached to Instance "{1}" but rather Instance "{2}" after {3} seconds'.format(str(address), instance.id, address.instance_id, str(elapsed)) )
            if elapsed > timeout:
                raise Exception('Address ' + str(address) + ' never associated with instance after '+str(elapsed)+' seconds')
            address = self.ec2.get_all_addresses(addresses=[address.public_ip])[0]
            self.sleep(5)
            elapsed = int(time.time()-start)
            
        
        self.debug("Attemtping to disassociate " + str(address) + " from " + str(instance.id))
        address.disassociate()
        
        start = time.time()
        ### Ensure instance gets correct address
        while re.search( instance.ip_address,address.public_ip):
            self.debug('Instance {0} has IP "{1}" still using address "{2}" after {3} seconds'.format(instance.id, instance.public_dns_name, address.public_ip, str(elapsed)) )
            if elapsed > timeout:
                raise Exception('Address ' + str(address) + ' never disassociated with instance after '+str(elapsed)+' seconds')
            instance.update()
            self.sleep(5)
            elapsed = int(time.time()-start)
            address = self.ec2.get_all_addresses(addresses=[address.public_ip])[0]
        self.debug("Disassociated IP successfully")    

    def release_address(self, address):
        """
        Release all addresses or a particular IP

        :param address: Address object to release
        :raise: Exception when the address does not release
        """
        try:
            self.debug("Releasing address: " + str(address))
            address.release()
        except Exception, e:
            raise Exception("Failed to release the address: " + str(address) + ": " +  str(e))


    def check_device(self, device_path):
        """
        Used with instance connections. Checks if a device at a certain path exists

        :param device_path: Path to check
        :return: bool, if device was found
        """
        return self.found("ls -1 " + device_path, device_path)

    def get_volumes(self, 
                    volume_id="vol-", 
                    status=None, 
                    attached_instance=None, 
                    attached_dev=None, 
                    snapid=None, 
                    zone=None, 
                    minsize=1, 
                    maxsize=None,
                    md5=None, 
                    eof=False):
        """
        Return list of volumes that matches the criteria. Criteria options to be matched:

        :param volume_id: string present within volume id
        :param status: examples: 'in-use', 'creating', 'available'
        :param attached_instance: instance id example 'i-1234abcd'
        :param attached_dev: example '/dev/sdf'
        :param snapid: snapshot volume was created from example 'snap-1234abcd'
        :param zone: zone of volume example 'PARTI00'
        :param minsize: minimum size of volume to be matched
        :param maxsize: maximum size of volume to be matched
        :param eof: exception on failure to find volume, else returns empty list
        :return: List of volumes matching the filters provided
        :raise:
        """
        retlist = []
        if (attached_instance is not None) or (attached_dev is not None):
            status='in-use'
        volumes = self.test_resources['volumes']
        volumes.extend(self.ec2.get_all_volumes())             
        for volume in volumes:
            if not hasattr(volume,'md5'):
                volume = EuVolume.make_euvol_from_vol(volume)
            if not re.match(volume_id, volume.id):
                continue
            if (snapid is not None) and (volume.snapshot_id != snapid):
                continue
            if (zone is not None) and (volume.zone != zone):
                continue
            if (status is not None) and (volume.status != status):
                continue
            if (md5 is not None) and (volume.md5 != md5):
                continue
            if volume.attach_data is not None:
                if (attached_instance is not None) and ( volume.attach_data.instance_id != attached_instance):
                    continue
                if (attached_dev is not None) and (volume.attach_data.device != attached_dev):
                    continue
            if not (volume.size >= minsize) and (maxsize is None or volume.size <= maxsize):
                continue
            retlist.append(volume)
        if eof and retlist == []:
            raise Exception("Unable to find matching volume")
        else:
            return retlist

    def get_volume(self, volume_id="vol-", status=None, attached_instance=None, attached_dev=None, snapid=None, zone=None, minsize=1, maxsize=None, eof=True):
        """
        Return first volume that matches the criteria.

        :param volume_id: string present within volume id
        :param status: examples: 'in-use', 'creating', 'available'
        :param attached_instance: instance id example 'i-1234abcd'
        :param attached_dev: example '/dev/sdf'
        :param snapid: snapshot volume was created from example 'snap-1234abcd'
        :param zone: zone of volume example 'PARTI00'
        :param minsize: minimum size of volume to be matched
        :param maxsize: maximum size of volume to be matched
        :param eof: exception on failure to find volume, else returns None
        :return: List of volumes matching the filters provided
        :raise:
        """
        vol = None
        try:
            vol = self.get_volumes(volume_id=volume_id, status=status, attached_instance=attached_instance, attached_dev=attached_dev, snapid=snapid, zone=zone, minsize=minsize, maxsize=maxsize, eof=eof)[0]
        except Exception, e:
            if eof:
                raise e
        return vol

    def run_instance(self, image=None, keypair=None, group="default", type=None, zone=None, min=1, max=1, user_data=None,private_addressing=False, username="root", password=None, is_reachable=True, timeout=480):
        """
        Run instance/s and wait for them to go to the running state

        :param image: Image object to use, default is pick the first emi found in the system
        :param keypair: Keypair name to use for the instances, defaults to none
        :param group: Security group name to apply to this set of instnaces, defaults to none
        :param type: VM type to use for these instances, defaults to m1.small
        :param zone: Availability zone to run these instances
        :param min: Minimum instnaces to launch, default 1
        :param max: Maxiumum instances to launch, default 1
        :param user_data: User-data string to pass to instance
        :param private_addressing: Runs an instance with only private IP address
        :param username: username to use when connecting via ssh
        :param password: password to use when connecting via ssh
        :param is_reachable: Instance can be reached on its public IP (Default=True)
        :param timeout: Time in seconds for instance to enter running state
        :return: Reservation object
        :raise:
        """
        if image is None:
            images = self.ec2.get_all_images()
            for emi in images:
                if re.match("emi",emi.id):
                    image = emi      
        if not isinstance(image, Image):
            image = self.get_emi(emi=str(image))
        if image is None:
            raise Exception("emi is None. run_instance could not auto find an emi?")   
        if private_addressing is True:
            addressing_type = "private"
            is_reachable= False
        else:
            addressing_type = None
        #In the case a keypair object was passed instead of the keypair name
        if keypair:
            if isinstance(keypair, KeyPair):
                keypair = keypair.name
        
        start = time.time()
            
        self.debug( "Attempting to run "+ str(image.root_device_type)  +" image " + str(image) + " in group " + str(group))
        reservation = image.run(key_name=keypair,security_groups=[group],instance_type=type, placement=zone, min_count=min, max_count=max, user_data=user_data, addressing_type=addressing_type)
        self.test_resources["reservations"].append(reservation)
        
        if (len(reservation.instances) < min) or (len(reservation.instances) > max):
            self.fail("Reservation:"+str(reservation.id)+" returned "+str(len(reservation.instances))+" instances, not within min("+str(min)+") and max("+str(max)+" ")
        
        try:
            self.wait_for_reservation(reservation,timeout=timeout)
        except Exception, e:
            self.critical("An instance did not enter proper running state in " + str(reservation) )
            self.critical("Terminatng instances in " + str(reservation))
            self.terminate_instances(reservation)
            raise Exception("Instances in " + str(reservation) + " did not enter proper state")
        
        for instance in reservation.instances:
            if instance.state != "running":
                self.critical("Instance " + instance.id + " now in " + instance.state  + " state  in zone: "  + instance.placement )
            else:
                self.debug( "Instance " + instance.id + " now in " + instance.state  + " state  in zone: "  + instance.placement )
        #    
        # check to see if public and private DNS names and IP addresses are the same
        #
            if (instance.ip_address is instance.private_ip_address) and (instance.public_dns_name is instance.private_dns_name) and ( private_addressing is False ):
                self.debug(str(instance) + " got Public IP: " + str(instance.ip_address)  + " Private IP: " + str(instance.private_ip_address) + " Public DNS Name: " + str(instance.public_dns_name) + " Private DNS Name: " + str(instance.private_dns_name))
                self.critical("Instance " + instance.id + " has he same public and private IPs of " + str(instance.ip_address))
            else:
                self.debug(str(instance) + " got Public IP: " + str(instance.ip_address)  + " Private IP: " + str(instance.private_ip_address) + " Public DNS Name: " + str(instance.public_dns_name) + " Private DNS Name: " + str(instance.private_dns_name))

            try:
                self.wait_for_valid_ip(instance)
            except Exception:
                self.terminate_instances(reservation)
                raise Exception("Reservation " +  str(reservation) + " has been terminated because instance " + str(instance) + " did not receive a valid IP")

            if is_reachable:
                self.ping(instance.public_dns_name, 20)
                
        #calculate remaining time to wait for establishing an ssh session/euinstance     
        timeout -= int(time.time() - start)
        #if we can establish an SSH session convert the instances to the test class euinstance for access to instance specific test methods
        if is_reachable:
            self.debug("Converting " + str(reservation) + " into euinstances")
            return self.convert_reservation_to_euinstance(reservation, username=username, password=password, keyname=keypair, timeout=timeout)
        else:
            return reservation

    def wait_for_valid_ip(self, instance, timeout = 60):
        """
        Wait for instance public DNS name to clear from 0.0.0.0

        :param instance: instance object to check
        :param timeout: Time in seconds to wait for IP to change
        :return: True on success
        :raise: Exception if IP stays at 0.0.0.0
        """
        elapsed = 0
        zeros = re.compile("0.0.0.0")
        while elapsed <= timeout:
            if zeros.search(instance.public_dns_name):
                self.sleep(1)
                instance.update()
                elapsed += 1
            else:
                return True
        raise Exception("Timed out waiting for a valid IP (ie anything other than 0.0.0.0.)")
                
            

    def convert_reservation_to_euinstance(self, reservation, username="root", password=None, keyname=None, timeout=120):
        """
        Convert all instances in an entire reservation into eutester.euinstance.Euinstance objects.

        :param reservation: reservation object to use in conversion
        :param username: SSH user name of instance
        :param password: SSH password
        :param keyname: Private key file to use when connecting to the instance
        :param timeout: Time in seconds to wait for successful SSH connection
        :return:
        """
        euinstance_list = []
        keypair = None
        if keyname is not None:
                keypair = self.get_keypair(keyname)
        for instance in reservation.instances:
            if keypair is not None or (password is not None and username is not None):
                try:
                    euinstance_list.append( EuInstance.make_euinstance_from_instance( instance, self, keypair=keypair, username = username, password=password, timeout=timeout ))
                except Exception, e:
                    euinstance_list.append(instance)
                    self.fail("Unable to create Euinstance from " + str(instance)+str(e))
            else:
                euinstance_list.append(instance)
        reservation.instances = euinstance_list
        return reservation
   
    def get_keypair(self, name):
        """
        Retrieve a boto.ec2.keypair object by its name

        :param name:  Name of keypair on the cloud
        :return: boto.ec2.keypair object
        :raise: Exception on failure to find keypair
        """
        try:
            return self.ec2.get_all_key_pairs([name])[0]
        except IndexError, e:
            raise Exception("Keypair: " + name + " not found")
        
    def get_zones(self):
        """
        Return a list of availability zone names.

        :return: list of zone names
        """
        zone_objects = self.ec2.get_all_zones()
        zone_names = []
        for zone in zone_objects:
            zone_names.append(zone.name)
        return zone_names
 
    def get_instances(self, state=None, idstring=None, reservation=None, rootdevtype=None, zone=None, key=None,
                      pubip=None, privip=None, ramdisk=None, kernel=None, image_id=None ):
        """
        Return a list of instances matching the filters provided.

        :param state: str of desired state
        :param idstring: instance-id string
        :param reservation:  reservation-id
        :param rootdevtype: 'instance-store' or 'ebs'
        :param zone: Availablity zone
        :param key: Keypair the instance was launched with
        :param pubip: Instance public IP
        :param privip: Instance private IP
        :param ramdisk: Ramdisk ID string
        :param kernel: Kernel ID string
        :param image_id: Image ID string
        :return: list of instances
        """
        ilist = []
        reservations = self.ec2.get_all_instances()
        for res in reservations:
            if ( reservation is None ) or (re.search(reservation, res.id)):
                for i in res.instances:
                    if (idstring is not None) and (not re.search(idstring, i.id)) :
                        continue
                    if (state is not None) and (i.state != state):
                        continue
                    if (rootdevtype is not None) and (i.root_device_type != rootdevtype):
                        continue
                    if (zone is not None) and (i.placement != zone ):
                        continue
                    if (key is not None) and (i.key_name != key):
                        continue
                    if (pubip is not None) and (i.ip_address != pubip):
                        continue
                    if (privip is not None) and (i.private_ip_address != privip):
                        continue
                    if (ramdisk is not None) and (i.ramdisk != ramdisk):
                        continue
                    if (kernel is not None) and (i.kernel != kernel):
                        continue
                    if (image_id is not None) and (i.image_id != image_id):
                        continue
                    ilist.append(i)
        return ilist

        """

        """
    def get_connectable_euinstances(self,path=None,username='root', password=None, connect=True):
        """
        Convenience method, returns a list of all running instances, for the current creduser
        for which there are local keys at 'path'

        :param path: Path to look for private keys
        :param username: username to use if path is not passed
        :param password: password to use if path is not passed
        :param connect: bool, Whether to create an ssh connection to the instances
        :return:
        """
        try:
            euinstances = []
            keys = self.get_all_current_local_keys(path=path)
            if keys:
                for keypair in keys:
                    self.debug('looking for instances using keypair:'+keypair.name)
                    instances = self.get_instances(state='running',key=keypair.name)
                    if instances:
                        for instance in instances:
                            if not connect:
                                keypair=None
                                euinstances.append(instance)
                            else:
                                euinstances.append(EuInstance.make_euinstance_from_instance( instance, self, username=username,password=password,keypair=keypair))
                      
            return euinstances
        except Exception, e:
            self.debug("Failed to find a pre-existing isntance we can connect to:"+str(e))
            pass
    
    
    def get_all_attributes(self, obj, verbose=True):
        """
        Get a formatted list of all the key pair values pertaining to the object 'obj'

        :param obj: Object to extract information from
        :param verbose: Print key value pairs
        :return: Buffer of key value pairs
        """
        buf=""
        list = sorted(obj.__dict__)
        for item in list:
            if verbose:
                print str(item)+" = "+str(obj.__dict__[item])
            buf += str(item)+" = "+str(obj.__dict__[item])+"\n"
        return buf

    def terminate_instances(self, reservation=None, timeout=480):
        """
        Terminate instances in the system

        :param reservation: Reservation object to terminate all instances in, default is to terminate all instances
        :raise: Exception when instance does not reach terminated state
        """
        ### If a reservation is not passed then kill all instances
        aggregate_result = True
        if reservation is None:
            reservations = self.ec2.get_all_instances()
            for res in reservations:
                for instance in res.instances:
                    self.debug( "Sending terminate for " + str(instance) )
                    instance.terminate()
                if self.wait_for_reservation(res, state="terminated", timeout=timeout) is False:
                    aggregate_result = False
        ### Otherwise just kill this reservation
        else:
            for instance in reservation.instances:
                    self.debug( "Sending terminate for " + str(instance) )
                    instance.terminate()
            if self.wait_for_reservation(reservation, state="terminated", timeout=timeout) is False:
                aggregate_result = False
        return aggregate_result
    
    def stop_instances(self,reservation, timeout=480):
        """
        Stop all instances in a reservation

        :param reservation: boto.ec2.reservation object
        :raise: Exception when instance does not reach stopped state
        """
        for instance in reservation.instances:
            self.debug( "Sending stop for " + str(instance) )
            instance.stop()
        if self.wait_for_reservation(reservation, state="stopped", timeout=timeout) is False:
            return False
        return True
    
    def start_instances(self,reservation, timeout=480):
        """
        Start all instances in a reservation

        :param reservation: boto.ec2.reservation object
        :raise: Exception when instance does not reach running state
        """
        for instance in reservation.instances:
            self.debug( "Sending start for " + str(instance) )
            instance.start()
        if self.wait_for_reservation(reservation, state="running", timeout=timeout) is False:
            return False
        return True
    
