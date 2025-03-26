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

from pywbem.cim_provider2 import CIMProvider2
import pywbem

class DeviceProvider(CIMProvider2):
    """
        CIM Provider which provides CIM StorageExtent or CIM_StoragePool
        of a Anaconda device.
        
        In addition to CIM provider methods, this class and its subclasses
        can convert CIM InstanceName to Anaconda's StorageDevice instance
        and a vice versa.
    """
    def __init__(self, env, storage, config, manager):
        """
            Initialize the provider.
            Store reference to pyanaconda.storage.Storage.
            Store reference to StorageConfiguration.
            Register at given ProviderManager.
        """
        super(DeviceProvider, self).__init__()
        self.storage = storage
        self.config = config
        self.manager = manager
        self.logger = env.get_logger()
        manager.addProvider(self)
        
    def providesName(self, objectName):
        """
            Returns True, if this class is provider for given CIM InstanceName.
        """
        return False

    def providesDevice(self, device):
        """
            Returns True, if this class is provider for given Anaconda
            StorageDevice class.
        """
        return False
    
    def getDeviceForName(self, objectName):
        """
            Returns Anaconda StorageDevice for given CIM InstanceName or
            None if no device is found.
        """
        return None
        
    def getNameForDevice(self, device):
        """
            Returns CIM InstanceName for given Anaconda StorageDevice.
            None if no device is found.
        """
        return None
        
    def getStatus(self, device):
        """
            Returns OperationalStatus for given Anaconda StorageDevice.
            It combines statuses of all parent devices.
            Subclasses should override this method to provide additional
            statuses.
        """
        status = set()
        parents = self.getBaseDevices(device)
        if len(parents) > 0:
            for parent in parents:
                parentStatus = self.getStatus(parent)
                status.update(parentStatus)
        else:
            status.add(self.DeviceProviderValues.OperationalStatus.OK)
        return list(status)

    def getBaseDevices(self, device):
        """
            Return iterable with base devices for given StorageDevice.
            Base devices are StorageDevices, that the given StorageDevice
            depend on, e.g. RAID members of a RAID, physical volumes
            of a Volume Group and Volume Group of Logical Volume.
        """
        return device.parents

    def _getCommonRedundancy(self, a, b):
        """
            Return the combined data redundancy characteristics for
            two devices.
            Linear device is assumed, i.e. the data are either on A or on B.
            Any specific DeviceProviderSubclasses (e.g. RAID) must override
            this method.
        """
        (aFailure, aData, aPackage) = a
        (bFailure, bData, bPackage) = b

        # assume linar device, i.e. a data is either on A or on B
        # hence dataRedundancy is the minimum of both
        cData = min(aData, bData)
        # assume the worst
        cPackage = min(aPackage, bPackage)
        # both NoSinglePointOfFailure must be true to be the result true
        cFailure = aFailure and bFailure
        
        return(cFailure, cData, cPackage)

    def getRedundancy(self, device):
        """
            Returns redundancy characterictics for given Anaconda StorageDevice.
        """
        parents = self.getBaseDevices(device)
        if len(parents) > 0:
            # find all parents and get their redundancy
            redundancies = map(self.getRedundancy, parents)
            # iteratively call self._getCommonRedundancy(r1, r2), ...
            (noSinglePointOfFailure, dataRedundancy, packageRedundancy) = reduce(self._getCommonRedundancy, redundancies)
        else:
            # this device has no parents, assume it is simple disk
            noSinglePointOfFailure = False
            dataRedundancy = 1
            packageRedundancy = 0
        return (noSinglePointOfFailure, dataRedundancy, packageRedundancy)
    
    class DeviceProviderValues(object):
        class OperationalStatus(object):
            Unknown = pywbem.Uint16(0)
            Other = pywbem.Uint16(1)
            OK = pywbem.Uint16(2)
            Degraded = pywbem.Uint16(3)
            Stressed = pywbem.Uint16(4)
            Predictive_Failure = pywbem.Uint16(5)
            Error = pywbem.Uint16(6)
            Non_Recoverable_Error = pywbem.Uint16(7)
            Starting = pywbem.Uint16(8)
            Stopping = pywbem.Uint16(9)
            Stopped = pywbem.Uint16(10)
            In_Service = pywbem.Uint16(11)
            No_Contact = pywbem.Uint16(12)
            Lost_Communication = pywbem.Uint16(13)
            Aborted = pywbem.Uint16(14)
            Dormant = pywbem.Uint16(15)
            Supporting_Entity_in_Error = pywbem.Uint16(16)
            Completed = pywbem.Uint16(17)
            Power_Mode = pywbem.Uint16(18)
            Relocating = pywbem.Uint16(19)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 0x8000..        
