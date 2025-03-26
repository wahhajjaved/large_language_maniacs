# Copyright (C) 2012 Red Hat, Inc.  All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# Authors: Jan Safranek <jsafrane@redhat.com>
# -*- coding: utf-8 -*-

from DeviceProvider import DeviceProvider
import pywbem
import pyanaconda.storage

class ExtentProvider(DeviceProvider):
    """
        Base of all StorageExtent providers.
        It fills common properties in the StorageExtent.
    """
    def __init__(self, classname, *args, **kwargs):
        self.classname = classname
        super(ExtentProvider, self).__init__(*args, **kwargs)

    def _getDevice(self, objectName):
        """
            Get Anaconda StorageDevice for given name, without any checks.
        """
        path = objectName['DeviceID']
        device = self.storage.devicetree.getDeviceByPath(path)
        return device

    def providesName(self, objectName):
        """
            Returns True, if this class is provider for given CIM InstanceName.
        """
        if objectName['SystemName'] != self.config.systemName:
            return False
        
        if objectName['SystemCreationClassName'] != self.config.systemClassName:
            return False

        if objectName['CreationClassName'] != self.classname:
            return False
        
        return True
        
    def getDeviceForName(self, objectName):
        """
            Returns Anaconda StorageDevice for given CIM InstanceName or
            None if no device is found.
        """
        if self.providesName(objectName):
            return self._getDevice(objectName)

    def getNameForDevice(self, device):
        """
            Returns CIM InstanceName for given Anaconda StorageDevice.
            None if no device is found.
        """
        path = device.path
        name = pywbem.CIMInstanceName(self.classname,
                namespace = self.config.namespace,
                keybindings = {
                    'SystemName' : self.config.systemName,
                    'SystemCreationClassName' : self.config.systemClassName,
                    'CreationClassName' : self.classname,
                    'DeviceID': path
                })
        return name
        
    def getElementName(self, device):
        """
            Return ElementName property value for given StorageDevice.
            Device path (/dev/sda) is the default.
        """
        return device.name
    
    def getExtentStatus(self, device):
        """
            Return ExtentStatus property value for given StorageDevice.
            It must be array of int16 values.
        """
        return []

    GPT_TABLE_SIZE = 34*2   # there are two copies
    MBR_TABLE_SIZE = 1
    def getPartitionTableSize(self, format):
        """
            Return size of partition table (in blocks) for given Anaconda
            DiskLabel instance.
        """
        if format.labelType == "gpt":
            return self.GPT_TABLE_SIZE
        if format.labelType == "msdos":
            return self.MBR_TABLE_SIZE
    
    def getSize(self, device):
        """
            Return (BlockSize, NumberOfBlocks, ConsumableBlocks) properties
            for given StorageDevice.
            
            The ConsumableBlocks should be reduced by partition table size.
        """
        if device.partedDevice:
            blockSize = pywbem.Uint64(device.partedDevice.sectorSize)
            totalBlocks = device.partedDevice.length
            consumableBlocks = device.partedDevice.length
            if device.format and isinstance(device.format, pyanaconda.storage.formats.disklabel.DiskLabel):
                # reduce by partition table size
                consumableBlocks -= self.getPartitionTableSize(device.format)
        else:
            blockSize = None
            totalBlocks = None
            consumableBlocks = None
        return (blockSize, totalBlocks, consumableBlocks)
        
    def getPrimordial(self, device):
        """
            Returns True, if given StorageDevice is primordial.
        """
        return False
    
    def getDiscriminator(self, device):
        """
            Returns ExtentDiscriminator property value for given StorageDevice.
            It must return array of strings.
        """
        d = []
        if device.format and isinstance(device.format, pyanaconda.storage.formats.lvmpv.LVMPhysicalVolume):
            d.append(self.ExtentProviderValues.Discriminator.Pool_Component)
        return d

    def get_instance(self, env, model, device = None):
        """
            Provider implementation of GetInstance intrinsic method.
            It fills common StorageExtent properties.
        """
        if not self.providesName(model):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, "Wrong keys.")
        if not device:
            device = self._getDevice(model)
        if not device:
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, "Cannot find the extent.")
        
        model['ElementName'] = self.getElementName(device)
        model['NameNamespace'] = self.ExtentProviderValues.NameNamespace.OS_Device_Namespace
        model['NameFormat'] = self.ExtentProviderValues.NameFormat.OS_Device_Name
        model['Name'] = device.path
        
        extentStatus = self.getExtentStatus(device)
        model['ExtentStatus'] = pywbem.CIMProperty(name='ExtentStatus', value=extentStatus, type='uint16', array_size=len(extentStatus), is_array=True)
        
        operationalStatus = self.getStatus(device)
        model['OperationalStatus'] = pywbem.CIMProperty(name='OperationalStatus', value=operationalStatus, type='uint16', array_size=len(operationalStatus), is_array=True)
        
        (blockSize, totalBlocks, consumableBlocks) = self.getSize(device)
        if blockSize:
            model['BlockSize'] = pywbem.Uint64(blockSize)
        if totalBlocks:
            model['NumberOfBlocks'] = pywbem.Uint64(totalBlocks)
        if consumableBlocks:
            model['ConsumableBlocks'] = pywbem.Uint64(consumableBlocks)
            
        redundancy = self.getRedundancy(device)
        model['NoSinglePointOfFailure'] = redundancy.noSinglePointOfFailure
        model['DataRedundancy'] = pywbem.Uint16(redundancy.dataRedundancy)
        model['PackageRedundancy'] = pywbem.Uint16(redundancy.packageRedundancy)
        model['ExtentStripeLength'] = pywbem.Uint16(redundancy.stripeLength)
            
        # TODO: add DeltaReservation (mandatory in SMI-S)
        
        model['Primordial'] = self.getPrimordial(device)
        
        discriminator = self.getDiscriminator(device)
        model['ExtentDiscriminator'] = pywbem.CIMProperty(name='ExtentDiscriminator', value=discriminator, type='string', array_size=len(discriminator), is_array=True)
        
        return model
        
    def enumerateDevices(self):
        """
            Enumerate all StorageDevices, that this provider provides.
        """
        pass
    

    def enum_instances(self, env, model, keys_only):
        """Enumerate instances.

        The WBEM operations EnumerateInstances and EnumerateInstanceNames
        are both mapped to this method. 
        This method is a python generator

        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        model -- A template of the pywbem.CIMInstances to be generated.  
            The properties of the model are already filtered according to 
            the PropertyList from the request.  Only properties present in 
            the model need to be given values.  If you prefer, you can 
            always set all of the values, and the instance will be filtered 
            for you. 
        keys_only -- A boolean.  True if only the key properties should be
            set on the generated instances.

        Possible Errors:
        CIM_ERR_FAILED (some other unspecified error occurred)

        """
        model.path.update({'CreationClassName': None, 'SystemName': None,
            'DeviceID': None, 'SystemCreationClassName': None})
        
        for device in self.enumerateDevices():
            name = self.getNameForDevice(device)
            model['SystemName'] = name['SystemName']
            model['SystemCreationClassName'] = name['SystemCreationClassName']
            model['CreationClassName'] = name['CreationClassName']
            model['DeviceID'] = name['DeviceID']
            if keys_only:
                yield model
            else:
                yield self.get_instance(env, model, device)

    class ExtentProviderValues(object):
        class NameNamespace(object):
            Unknown = pywbem.Uint16(0)
            Other = pywbem.Uint16(1)
            VPD83Type3 = pywbem.Uint16(2)
            VPD83Type2 = pywbem.Uint16(3)
            VPD83Type1 = pywbem.Uint16(4)
            VPD80 = pywbem.Uint16(5)
            NodeWWN = pywbem.Uint16(6)
            SNVM = pywbem.Uint16(7)
            OS_Device_Namespace = pywbem.Uint16(8)
            
        class NameFormat(object):
            Unknown = pywbem.Uint16(0)
            Other = pywbem.Uint16(1)
            VPD83NAA6 = pywbem.Uint16(2)
            VPD83NAA5 = pywbem.Uint16(3)
            VPD83Type2 = pywbem.Uint16(4)
            VPD83Type1 = pywbem.Uint16(5)
            VPD83Type0 = pywbem.Uint16(6)
            SNVM = pywbem.Uint16(7)
            NodeWWN = pywbem.Uint16(8)
            NAA = pywbem.Uint16(9)
            EUI64 = pywbem.Uint16(10)
            T10VID = pywbem.Uint16(11)
            OS_Device_Name = pywbem.Uint16(12)
            
        class ExtentStatus(object):
            Other = pywbem.Uint16(0)
            Unknown = pywbem.Uint16(1)
            None_Not_Applicable = pywbem.Uint16(2)
            Broken = pywbem.Uint16(3)
            Data_Lost = pywbem.Uint16(4)
            Dynamic_Reconfig = pywbem.Uint16(5)
            Exposed = pywbem.Uint16(6)
            Fractionally_Exposed = pywbem.Uint16(7)
            Partially_Exposed = pywbem.Uint16(8)
            Protection_Disabled = pywbem.Uint16(9)
            Readying = pywbem.Uint16(10)
            Rebuild = pywbem.Uint16(11)
            Recalculate = pywbem.Uint16(12)
            Spare_in_Use = pywbem.Uint16(13)
            Verify_In_Progress = pywbem.Uint16(14)
            In_Band_Access_Granted = pywbem.Uint16(15)
            Imported = pywbem.Uint16(16)
            Exported = pywbem.Uint16(17)
            Relocating = pywbem.Uint16(18)
            # DMTF_Reserved = ..

        class Usage(object):
            Other = pywbem.Uint16(1)
            Unrestricted = pywbem.Uint16(2)
            Reserved_for_ComputerSystem__the_block_server_ = pywbem.Uint16(3)
            Reserved_by_Replication_Services = pywbem.Uint16(4)
            Reserved_by_Migration_Services = pywbem.Uint16(5)
            Local_Replica_Source = pywbem.Uint16(6)
            Remote_Replica_Source = pywbem.Uint16(7)
            Local_Replica_Target = pywbem.Uint16(8)
            Remote_Replica_Target = pywbem.Uint16(9)
            Local_Replica_Source_or_Target = pywbem.Uint16(10)
            Remote_Replica_Source_or_Target = pywbem.Uint16(11)
            Delta_Replica_Target = pywbem.Uint16(12)
            Element_Component = pywbem.Uint16(13)
            Reserved_as_Pool_Contributor = pywbem.Uint16(14)
            Composite_Volume_Member = pywbem.Uint16(15)
            Composite_LogicalDisk_Member = pywbem.Uint16(16)
            Reserved_for_Sparing = pywbem.Uint16(17)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 32768..65535
            
        class Discriminator(object):
            Pool_Component = 'SNIA:PoolComponent'
            Composite = 'SNIA:Composite'
            Imported = 'SNIA:Imported'
            Allocated = 'SNIA:Allocated'
            