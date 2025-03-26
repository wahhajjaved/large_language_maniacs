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
import pyanaconda.storage.formats
import util.partitioning

class ExtentProvider(DeviceProvider):
    """
        Base of all StorageExtent providers.
        It fills common properties in the StorageExtent.
    """
    def __init__(self, classname, *args, **kwargs):
        self.classname = classname
        super(ExtentProvider, self).__init__(*args, **kwargs)

    def _get_device(self, object_name):
        """
            Get Anaconda StorageDevice for given name, without any checks.
        """
        path = object_name['DeviceID']
        device = self.storage.devicetree.getDeviceByPath(path)
        return device

    def provides_name(self, object_name):
        """
            Returns True, if this class is provider for given CIM InstanceName.
        """
        if object_name['SystemName'] != self.config.system_name:
            return False

        if object_name['SystemCreationClassName'] != self.config.system_class_name:
            return False

        if object_name['CreationClassName'] != self.classname:
            return False

        return True

    def get_device_for_name(self, object_name):
        """
            Returns Anaconda StorageDevice for given CIM InstanceName or
            None if no device is found.
        """
        if self.provides_name(object_name):
            return self._get_device(object_name)

    def get_name_for_device(self, device):
        """
            Returns CIM InstanceName for given Anaconda StorageDevice.
            None if no device is found.
        """
        path = device.path
        name = pywbem.CIMInstanceName(self.classname,
                namespace=self.config.namespace,
                keybindings={
                    'SystemName' : self.config.system_name,
                    'SystemCreationClassName' : self.config.system_class_name,
                    'CreationClassName' : self.classname,
                    'DeviceID': path
                })
        return name

    def get_element_name(self, device):
        """
            Return ElementName property value for given StorageDevice.
            Device path (/dev/sda) is the default.
        """
        return device.name

    def get_extent_status(self, device):
        """
            Return ExtentStatus property value for given StorageDevice.
            It must be array of int16 values.
        """
        return []

    def get_size(self, device):
        """
            Return (BlockSize, NumberOfBlocks, ConsumableBlocks) properties
            for given StorageDevice.
            
            The ConsumableBlocks should be reduced by partition table size.
        """
        if device.partedDevice:
            block_size = pywbem.Uint64(device.partedDevice.sectorSize)
            total_blocks = device.partedDevice.length
            consumable_blocks = device.partedDevice.length
            if (device.format and isinstance(device.format,
                    pyanaconda.storage.formats.disklabel.DiskLabel)):
                # reduce by partition table size
                consumable_blocks -= util.partitioning.get_partition_table_size(device)
        else:
            block_size = None
            total_blocks = None
            consumable_blocks = None
        return (block_size, total_blocks, consumable_blocks)

    def get_primordial(self, device):
        """
            Returns True, if given StorageDevice is primordial.
        """
        return False

    def get_discriminator(self, device):
        """
            Returns ExtentDiscriminator property value for given StorageDevice.
            It must return array of strings.
        """
        d = []
        if device.format and isinstance(device.format,
                    pyanaconda.storage.formats.lvmpv.LVMPhysicalVolume):
            d.append(self.Values.Discriminator.Pool_Component)
        return d

    def get_instance(self, env, model, device=None):
        """
            Provider implementation of GetInstance intrinsic method.
            It fills common StorageExtent properties.
        """
        if not self.provides_name(model):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, "Wrong keys.")
        if not device:
            device = self._get_device(model)
        if not device:
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND,
                    "Cannot find the extent.")

        model['ElementName'] = self.get_element_name(device)
        model['NameNamespace'] = self.Values.NameNamespace.OS_Device_Namespace
        model['NameFormat'] = self.Values.NameFormat.OS_Device_Name
        model['Name'] = device.path

        extent_status = self.get_extent_status(device)
        model['ExtentStatus'] = pywbem.CIMProperty(
                name='ExtentStatus',
                value=extent_status,
                type='uint16',
                array_size=len(extent_status),
                is_array=True)

        operational_status = self.get_status(device)
        model['OperationalStatus'] = pywbem.CIMProperty(
                name='OperationalStatus',
                value=operational_status,
                type='uint16',
                array_size=len(operational_status),
                is_array=True)

        (block_size, total_blocks, consumable_blocks) = self.get_size(device)
        if block_size:
            model['BlockSize'] = pywbem.Uint64(block_size)
        if total_blocks:
            model['NumberOfBlocks'] = pywbem.Uint64(total_blocks)
        if consumable_blocks:
            model['ConsumableBlocks'] = pywbem.Uint64(consumable_blocks)

        redundancy = self.get_redundancy(device)
        model['NoSinglePointOfFailure'] = redundancy.no_single_point_of_failure
        model['DataRedundancy'] = pywbem.Uint16(redundancy.data_dedundancy)
        model['PackageRedundancy'] = pywbem.Uint16(redundancy.package_redundancy)
        model['ExtentStripeLength'] = pywbem.Uint16(redundancy.stripe_length)
        model['IsComposite'] = (len(device.parents) > 1)

        # TODO: add DeltaReservation (mandatory in SMI-S)

        model['Primordial'] = self.get_primordial(device)

        discriminator = self.get_discriminator(device)
        model['ExtentDiscriminator'] = pywbem.CIMProperty(
                name='ExtentDiscriminator',
                value=discriminator,
                type='string',
                array_size=len(discriminator),
                is_array=True)

        return model

    def enumerate_devices(self):
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

        for device in self.enumerate_devices():
            name = self.get_name_for_device(device)
            model['SystemName'] = name['SystemName']
            model['SystemCreationClassName'] = name['SystemCreationClassName']
            model['CreationClassName'] = name['CreationClassName']
            model['DeviceID'] = name['DeviceID']
            if keys_only:
                yield model
            else:
                yield self.get_instance(env, model, device)

    class Values(DeviceProvider.Values):
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
