# Cura Storage Provider
#
# Copyright (C) 2012 Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Python Provider for Cura_DiskPartitionConfigurationService
Instruments the CIM class Cura_DiskPartitionConfigurationService

"""

import pywbem
from pywbem.cim_provider2 import CIMProvider2
import pyanaconda.storage.devices
import parted
from wrapper.common import *
import util.partitioning

class Cura_DiskPartitionConfigurationService(CIMProvider2):
    """Instrument the CIM class Cura_DiskPartitionConfigurationService 

    POC DiskParitionConfigurationService instrumentation. The partitions
    MUST be alligned to
    Cura_DiskPartitionConfigurationCapabilities.Alignment blocks.
    
    """

    def createMBR(self, disk):
        try:
            util.partitioning.createMBR(disk)
        except Exception, err:
            raise pywbem.CIMError(pywbem.CIM_ERR_FAILED, err.__class__.__name__ + ': '  + str(err))
        return self.Values.SetPartitionStyle.Success
        
    def createGPT(self, disk):
        try:
            util.partitioning.createGPT(disk)
        except Exception, err:
            raise pywbem.CIMError(pywbem.CIM_ERR_FAILED, err.__class__.__name__ + ': '  + str(err))            
        return self.Values.SetPartitionStyle.Success

    def createEMBR(self, partition):
        return self.Values.SetPartitionStyle.Not_Supported

    def createPartition(self, disk, logical, fromSector, toSector):
        if logical:
            partType = parted.PARTITION_LOGICAL
        else:
            partType = parted.PARTITION_NORMAL
            
        print "Partitioning: ", fromSector, toSector
        try:
            part = storage.newPartition(disks=[disk], #start=fromSector, end=toSector,
                    size=pyanaconda.storage.partitioning.sectorsToSize(toSector-fromSector, disk.partedDevice.sectorSize),
                    partType=partType, grow=False)
            util.partitioning.createPartition(part)
        except Exception, err:
            raise pywbem.CIMError(pywbem.CIM_ERR_FAILED, err.__class__.__name__ + ': '  + str(err))
        return (self.Values.CreateOrModifyPartition.Success, part)

    
    def __init__ (self, env):
        logger = env.get_logger()
        logger.log_debug('Initializing provider %s from %s' \
                % (self.__class__.__name__, __file__))
        self.name = 'Cura_PartitionService'

    def get_instance(self, env, model):
        """Return an instance.

        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        model -- A template of the pywbem.CIMInstance to be returned.  The 
            key properties are set on this instance to correspond to the 
            instanceName that was requested.  The properties of the model
            are already filtered according to the PropertyList from the 
            request.  Only properties present in the model need to be
            given values.  If you prefer, you can set all of the 
            values, and the instance will be filtered for you. 

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, unrecognized 
            or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the CIM Class does exist, but the requested CIM 
            Instance does not exist in the specified namespace)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """
        
        logger = env.get_logger()
        logger.log_debug('Entering %s.get_instance()' \
                % self.__class__.__name__)
        

        if (model['SystemName'] != CURA_SYSTEM_NAME
                or model['SystemCreationClassName'] != CURA_SYSTEM_CLASS_NAME
                or model['CreationClassName'] != 'Cura_DiskPartitionConfigurationService'
                or model['Name'] != self.name):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Wrong keys.')
        

        #model['AvailableRequestedStates'] = [self.Values.AvailableRequestedStates.<VAL>,] # TODO 
        #model['Caption'] = '' # TODO 
        #model['CommunicationStatus'] = self.Values.CommunicationStatus.<VAL> # TODO 
        #model['Description'] = '' # TODO 
        #model['DetailedStatus'] = self.Values.DetailedStatus.<VAL> # TODO 
        #model['ElementName'] = '' # TODO 
        model['EnabledDefault'] = self.Values.EnabledDefault.Enabled
        #model['EnabledState'] = self.Values.EnabledState.Not_Applicable # TODO 
        #model['Generation'] = pywbem.Uint64() # TODO 
        model['HealthState'] = self.Values.HealthState.OK 
        #model['InstallDate'] = pywbem.CIMDateTime() # TODO 
        #model['InstanceID'] = '' # TODO 
        #model['OperatingStatus'] = self.Values.OperatingStatus.<VAL> # TODO 
        model['OperationalStatus'] = [self.Values.OperationalStatus.OK,] 
        #model['OtherEnabledState'] = '' # TODO 
        model['PartitioningSchemes'] = self.Values.PartitioningSchemes.Volumes_may_be_partitioned_or_treated_as_whole 
        #model['PrimaryOwnerContact'] = '' # TODO 
        #model['PrimaryOwnerName'] = '' # TODO 
        model['PrimaryStatus'] = self.Values.PrimaryStatus.OK
        model['RequestedState'] = self.Values.RequestedState.Not_Applicable
        model['Started'] = bool(True) 
        #model['StartMode'] = self.Values.StartMode.<VAL> # TODO 
        #model['Status'] = self.Values.Status.<VAL> # TODO 
        #model['StatusDescriptions'] = ['',] # TODO 
        #model['TimeOfLastStateChange'] = pywbem.CIMDateTime() # TODO 
        model['TransitioningToState'] = self.Values.TransitioningToState.Not_Applicable
        return model

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

        logger = env.get_logger()
        logger.log_debug('Entering %s.enum_instances()' \
                % self.__class__.__name__)
                
        # Prime model.path with knowledge of the keys, so key values on
        # the CIMInstanceName (model.path) will automatically be set when
        # we set property values on the model. 
        model.path.update({'CreationClassName': None, 'SystemName': None,
            'Name': None, 'SystemCreationClassName': None})
        
        model['SystemName'] = CURA_SYSTEM_NAME
        model['SystemCreationClassName'] = CURA_SYSTEM_CLASS_NAME    
        model['CreationClassName'] = 'Cura_DiskPartitionConfigurationService'    
        model['Name'] = self.name
        if keys_only:
            yield model
        else:
            try:
                yield self.get_instance(env, model)
            except pywbem.CIMError, (num, msg):
                if num not in (pywbem.CIM_ERR_NOT_FOUND, 
                                pywbem.CIM_ERR_ACCESS_DENIED):
                    raise

    def set_instance(self, env, instance, modify_existing):
        """Return a newly created or modified instance.

        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        instance -- The new pywbem.CIMInstance.  If modifying an existing 
            instance, the properties on this instance have been filtered by 
            the PropertyList from the request.
        modify_existing -- True if ModifyInstance, False if CreateInstance

        Return the new instance.  The keys must be set on the new instance. 

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_NOT_SUPPORTED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, unrecognized 
            or otherwise incorrect parameters)
        CIM_ERR_ALREADY_EXISTS (the CIM Instance already exists -- only 
            valid if modify_existing is False, indicating that the operation
            was CreateInstance)
        CIM_ERR_NOT_FOUND (the CIM Instance does not exist -- only valid 
            if modify_existing is True, indicating that the operation
            was ModifyInstance)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.set_instance()' \
                % self.__class__.__name__)
        # TODO create or modify the instance
        raise pywbem.CIMError(pywbem.CIM_ERR_NOT_SUPPORTED) # Remove to implement
        return instance

    def delete_instance(self, env, instance_name):
        """Delete an instance.

        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        instance_name -- A pywbem.CIMInstanceName specifying the instance 
            to delete.

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_NOT_SUPPORTED
        CIM_ERR_INVALID_NAMESPACE
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, unrecognized 
            or otherwise incorrect parameters)
        CIM_ERR_INVALID_CLASS (the CIM Class does not exist in the specified 
            namespace)
        CIM_ERR_NOT_FOUND (the CIM Class does exist, but the requested CIM 
            Instance does not exist in the specified namespace)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """ 

        logger = env.get_logger()
        logger.log_debug('Entering %s.delete_instance()' \
                % self.__class__.__name__)

        # TODO delete the resource
        raise pywbem.CIMError(pywbem.CIM_ERR_NOT_SUPPORTED) # Remove to implement
        
    def cim_method_requeststatechange(self, env, object_name,
                                      param_requestedstate=None,
                                      param_timeoutperiod=None):
        """Implements Cura_DiskPartitionConfigurationService.RequestStateChange()

        Requests that the state of the element be changed to the value
        specified in the RequestedState parameter. When the requested
        state change takes place, the EnabledState and RequestedState of
        the element will be the same. Invoking the RequestStateChange
        method multiple times could result in earlier requests being
        overwritten or lost. \nA return code of 0 shall indicate the state
        change was successfully initiated. \nA return code of 3 shall
        indicate that the state transition cannot complete within the
        interval specified by the TimeoutPeriod parameter. \nA return code
        of 4096 (0x1000) shall indicate the state change was successfully
        initiated, a ConcreteJob has been created, and its reference
        returned in the output parameter Job. Any other return code
        indicates an error condition.
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method RequestStateChange() 
            should be invoked.
        param_requestedstate --  The input parameter RequestedState (type pywbem.Uint16 self.Values.RequestStateChange.RequestedState) 
            The state requested for the element. This information will be
            placed into the RequestedState property of the instance if the
            return code of the RequestStateChange method is 0 (\'Completed
            with No Error\'), or 4096 (0x1000) (\'Job Started\'). Refer to
            the description of the EnabledState and RequestedState
            properties for the detailed explanations of the RequestedState
            values.
            
        param_timeoutperiod --  The input parameter TimeoutPeriod (type pywbem.CIMDateTime) 
            A timeout period that specifies the maximum amount of time that
            the client expects the transition to the new state to take.
            The interval format must be used to specify the TimeoutPeriod.
            A value of 0 or a null parameter indicates that the client has
            no time requirements for the transition. \nIf this property
            does not contain 0 or null and the implementation does not
            support this parameter, a return code of \'Use Of Timeout
            Parameter Not Supported\' shall be returned.
            

        Returns a two-tuple containing the return value (type pywbem.Uint32 self.Values.RequestStateChange)
        and a list of CIMParameter objects representing the output parameters

        Output parameters:
        Job -- (type REF (pywbem.CIMInstanceName(classname='CIM_ConcreteJob', ...)) 
            May contain a reference to the ConcreteJob created to track the
            state transition initiated by the method invocation.
            

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_requeststatechange()' \
                % self.__class__.__name__)

        # TODO do something
        raise pywbem.CIMError(pywbem.CIM_ERR_METHOD_NOT_AVAILABLE) # Remove to implemented
        out_params = []
        #out_params+= [pywbem.CIMParameter('job', type='reference', 
        #                   value=pywbem.CIMInstanceName(classname='CIM_ConcreteJob', ...))] # TODO
        rval = None # TODO (type pywbem.Uint32 self.Values.RequestStateChange)
        return (rval, out_params)
        
    def cim_method_stopservice(self, env, object_name):
        """Implements Cura_DiskPartitionConfigurationService.StopService()

        The StopService method places the Service in the stopped state.
        Note that the function of this method overlaps with the
        RequestedState property. RequestedState was added to the model to
        maintain a record (such as a persisted value) of the last state
        request. Invoking the StopService method should set the
        RequestedState property appropriately. The method returns an
        integer value of 0 if the Service was successfully stopped, 1 if
        the request is not supported, and any other number to indicate an
        error. In a subclass, the set of possible return codes could be
        specified using a ValueMap qualifier on the method. The strings to
        which the ValueMap contents are translated can also be specified
        in the subclass as a Values array qualifier. \n\nNote: The
        semantics of this method overlap with the RequestStateChange
        method that is inherited from EnabledLogicalElement. This method
        is maintained because it has been widely implemented, and its
        simple "stop" semantics are convenient to use.
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method StopService() 
            should be invoked.

        Returns a two-tuple containing the return value (type pywbem.Uint32)
        and a list of CIMParameter objects representing the output parameters

        Output parameters: none

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_stopservice()' \
                % self.__class__.__name__)

        # TODO do something
        raise pywbem.CIMError(pywbem.CIM_ERR_METHOD_NOT_AVAILABLE) # Remove to implemented
        out_params = []
        rval = None # TODO (type pywbem.Uint32)
        return (rval, out_params)
        
    def cim_method_createormodifypartition(self, env, object_name,
                                           param_devicefilename=None,
                                           param_partition=None,
                                           param_extent=None,
                                           param_endingaddress=None,
                                           param_startingaddress=None):
        """Implements Cura_DiskPartitionConfigurationService.CreateOrModifyPartition()

        This method creates a new partition if the Partition parameter is
        null or modifies the partition specified. If the starting and
        ending address parameters are null, the resulting partition will
        occupy the entire underlying extent. If the starting address is
        non-null and the ending address is null, the resulting partition
        will extend to the end of the underlying extent. \n\nIf a
        partition is being created, a LogicalDisk instance is also created
        BasedOn the partition. The NumberOfBlocks and ComsumableBlocks
        properties MUST be the same value and MUST be common to the
        partition and LogicalDisk (since partition metadata is part of the
        partition table, not part of partitions). The StartingAddress of
        the LogicalDisk MUST be 0, the ConsumableBlocks of the LogicalDisk
        and partition MUST be the same, and the difference between the
        StartingAddress and EndingAddress of the partition and LogicalDisk
        must be the same - one less than ConsumableBlocks/NumberOfBlocks.
        \n\nThe underlying extent MUST be associated to a capabilities
        class describing the installed partition style (partition table);
        this association is established using SetPartitionStyle().
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method CreateOrModifyPartition() 
            should be invoked.
        param_devicefilename --  The input parameter DeviceFileName (type unicode) 
            The platform-specific special file name to be assigned to the
            LogicalDisk instance BasedOn the new DiskPartition instance.
            
        param_partition --  The input parameter Partition (type REF (pywbem.CIMInstanceName(classname='CIM_GenericDiskPartition', ...)) 
            A reference an existing partition instance to modify or null to
            request a new partition.
            
        param_extent --  The input parameter extent (type REF (pywbem.CIMInstanceName(classname='CIM_StorageExtent', ...)) 
            A reference to the underlying extent the partition is base on.
            
        param_endingaddress --  The input parameter EndingAddress (type pywbem.Uint64) 
            The ending block number.
            
        param_startingaddress --  The input parameter StartingAddress (type pywbem.Uint64) 
            The starting block number.
            

        Returns a two-tuple containing the return value (type pywbem.Uint32 self.Values.CreateOrModifyPartition)
        and a list of CIMParameter objects representing the output parameters

        Output parameters:
        Partition -- (type REF (pywbem.CIMInstanceName(classname='CIM_GenericDiskPartition', ...)) 
            A reference an existing partition instance to modify or null to
            request a new partition.
            

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_createormodifypartition()' \
                % self.__class__.__name__)

        # check object_name
        if (object_name['SystemName'] != CURA_SYSTEM_NAME
                or object_name['SystemCreationClassName'] != CURA_SYSTEM_CLASS_NAME
                or object_name['CreationClassName'] != 'Cura_DiskPartitionConfigurationService'
                or object_name['Name'] != self.name):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Wrong service keys.')

        # check start/end addresses
        if param_endingaddress is not None:
            if param_startingaddress is None:
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'startingAddress must be specified if endingAddress is set')
            if param_startingaddress > param_endingaddress:
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'startingAddress must be lower than endingAddress')
        
        # check param_extent
        if (param_extent['SystemName'] != CURA_SYSTEM_NAME
                or param_extent['SystemCreationClassName'] != CURA_SYSTEM_CLASS_NAME):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Wrong extent keys.')
        
        extent = storage.devicetree.getDeviceByPath(param_extent['DeviceID'])
        if not extent:
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Cannot find DeviceID')
        
        gpt = False
        logical = False

        if isinstance(extent, pyanaconda.storage.devices.PartitionDevice):
            # creating logical partition
            if param_extent['CreationClassName'] != 'Cura_DiskPartition':
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is Cura_DiskPartition')
            if not extent.isExtended:
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is not an extended partition')

            # calculate start/end if omitted            
            if param_startingaddress is None:
                param_startingaddress = extent.disk.format.format.alignment.grainSize / extent.disk.partedDevice.sectorSize
            if param_endingaddress is None:
                param_endingaddress = extent.partedPartition.geometry.length - 1
            
            # we must recalculate start/end sector from extended-partition based to disk-based
            param_startingaddress += extent.partedPartition.geometry.start 
            param_endingaddress += extent.partedDevice.length - 1
            disk = extent.disk
            logical = True
            
        elif isinstance(extent, pyanaconda.storage.devices.DiskDevice):
            # creating physical partition
            if param_extent['CreationClassName'] != 'Cura_LocalDiskExtent':
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is Cura_LocalDiskExtent')
            if extent.format.labelType == util.partitioning.LABEL_GPT:
                gpt = True
            # calculate start/end if omitted            
            if param_startingaddress is None:
                param_startingaddress = extent.format.alignment.grainSize
            if param_endingaddress is None:
                if gpt:
                    # don't rewrite secondary GPT!
                    param_endingaddress = extent.partedDevice.length - util.partitioning.GPT_SIZE
                else:
                    param_endingaddress = extent.partedDevice.length - 1
            disk = extent
        else:
            raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is not Cura_LocalDiskExtent nor Cura_DiskPartition')
            
        (ret, partition) = self.createPartition(disk, logical, param_startingaddress, param_endingaddress)
        out_params = []
        if gpt:
            classname = 'Cura_GPTDiskPartition'
        else:
            classname = 'Cura_DiskPartition'
        out_params+= [pywbem.CIMParameter('partition', type='reference', 
                value=pywbem.CIMInstanceName(classname = classname,
                        namespace=CURA_NAMESPACE,
                        keybindings={'CreationClassName': classname,
                                 'DeviceID': partition.path,
                                 'SystemCreationClassName': CURA_SYSTEM_CLASS_NAME,
                                 'SystemName': CURA_SYSTEM_NAME
                }))]
        return (ret, out_params)
        
    def cim_method_changeaffectedelementsassignedsequence(self, env, object_name,
                                                          param_managedelements,
                                                          param_assignedsequence):
        """Implements Cura_DiskPartitionConfigurationService.ChangeAffectedElementsAssignedSequence()

        This method is called to change relative sequence in which order
        the ManagedElements associated to the Service through
        CIM_ServiceAffectsElement association are affected. In the case
        when the Service represents an interface for client to execute
        extrinsic methods and when it is used for grouping of the managed
        elements that could be affected, the ordering represents the
        relevant priority of the affected managed elements with respect to
        each other. \nAn ordered array of ManagedElement instances is
        passed to this method, where each ManagedElement instance shall be
        already be associated with this Service instance via
        CIM_ServiceAffectsElement association. If one of the
        ManagedElements is not associated to the Service through
        CIM_ServiceAffectsElement association, the implementation shall
        return a value of 2 ("Error Occured"). \nUpon successful execution
        of this method, if the AssignedSequence parameter is NULL, the
        value of the AssignedSequence property on each instance of
        CIM_ServiceAffectsElement shall be updated such that the values of
        AssignedSequence properties shall be monotonically increasing in
        correlation with the position of the referenced ManagedElement
        instance in the ManagedElements input parameter. That is, the
        first position in the array shall have the lowest value for
        AssignedSequence. The second position shall have the second lowest
        value, and so on. Upon successful execution, if the
        AssignedSequence parameter is not NULL, the value of the
        AssignedSequence property of each instance of
        CIM_ServiceAffectsElement referencing the ManagedElement instance
        in the ManagedElements array shall be assigned the value of the
        corresponding index of the AssignedSequence parameter array. For
        ManagedElements instances which are associated with the Service
        instance via CIM_ServiceAffectsElement and are not present in the
        ManagedElements parameter array, the AssignedSequence property on
        the CIM_ServiceAffects association shall be assigned a value of 0.
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method ChangeAffectedElementsAssignedSequence() 
            should be invoked.
        param_managedelements --  The input parameter ManagedElements (type REF (pywbem.CIMInstanceName(classname='CIM_ManagedElement', ...)) (Required)
            An array of ManagedElements.
            
        param_assignedsequence --  The input parameter AssignedSequence (type [pywbem.Uint16,]) (Required)
            An array of integers representing AssignedSequence for the
            ManagedElement in the corresponding index of the
            ManagedElements parameter.
            

        Returns a two-tuple containing the return value (type pywbem.Uint32 self.Values.ChangeAffectedElementsAssignedSequence)
        and a list of CIMParameter objects representing the output parameters

        Output parameters:
        Job -- (type REF (pywbem.CIMInstanceName(classname='CIM_ConcreteJob', ...)) 
            Reference to the job spawned if the operation continues after
            the method returns. (May be null if the task is completed).
            

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_changeaffectedelementsassignedsequence()' \
                % self.__class__.__name__)

        # TODO do something
        raise pywbem.CIMError(pywbem.CIM_ERR_METHOD_NOT_AVAILABLE) # Remove to implemented
        out_params = []
        #out_params+= [pywbem.CIMParameter('job', type='reference', 
        #                   value=pywbem.CIMInstanceName(classname='CIM_ConcreteJob', ...))] # TODO
        rval = None # TODO (type pywbem.Uint32 self.Values.ChangeAffectedElementsAssignedSequence)
        return (rval, out_params)
        
    def cim_method_setpartitionstyle(self, env, object_name,
                                     param_extent=None,
                                     param_partitionstyle=None):
        """Implements Cura_DiskPartitionConfigurationService.SetPartitionStyle()

        This method installs a partition table on an extent of the
        specified partition style; creating an association between the
        extent and that capabilities instances referenced as method
        parameters. As a side effect, the consumable block size of the
        underlying extent is reduced by the block size of the metadata
        reserved by the partition table and associated metadata. This size
        is in the PartitionTableSize property of the associated
        DiskPartitionConfigurationCapabilities instance.
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method SetPartitionStyle() 
            should be invoked.
        param_extent --  The input parameter Extent (type REF (pywbem.CIMInstanceName(classname='CIM_StorageExtent', ...)) 
            A reference to the extent (volume or partition) where this
            style (partition table) will be installed.
            
        param_partitionstyle --  The input parameter PartitionStyle (type REF (pywbem.CIMInstanceName(classname='CIM_DiskPartitionConfigurationCapabilities', ...)) 
            A reference to the DiskPartitionConfigurationCapabilities
            instance describing the desired partition style.
            

        Returns a two-tuple containing the return value (type pywbem.Uint32 self.Values.SetPartitionStyle)
        and a list of CIMParameter objects representing the output parameters

        Output parameters: none

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_setpartitionstyle()' \
                % self.__class__.__name__)

        ret = self.Values.SetPartitionStyle.Failed
        
        # check object_name
        if (object_name['SystemName'] != CURA_SYSTEM_NAME
                or object_name['SystemCreationClassName'] != CURA_SYSTEM_CLASS_NAME
                or object_name['CreationClassName'] != 'Cura_DiskPartitionConfigurationService'
                or object_name['Name'] != self.name):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Wrong service keys.')
        
        # check param_extent
        if (param_extent['SystemName'] != CURA_SYSTEM_NAME
                or param_extent['SystemCreationClassName'] != CURA_SYSTEM_CLASS_NAME):
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Wrong extent keys.')
        
        extent = storage.devicetree.getDeviceByPath(param_extent['DeviceID'])
        if not extent:
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Cannot find DeviceID')
        
        if (not isinstance(extent, pyanaconda.storage.devices.PartitionDevice)
                and not isinstance(extent, pyanaconda.storage.devices.DiskDevice)):
            raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'Partitions can be created only on Cura_DiskPartition or Cura_LocalDiskExtent')
        
        if (isinstance(extent, pyanaconda.storage.devices.PartitionDevice)
                and param_extent['CreationClassName'] != 'Cura_DiskPartition'):
            raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is Cura_DiskPartition')

        if (isinstance(extent, pyanaconda.storage.devices.DiskDevice) 
                and param_extent['CreationClassName'] != 'Cura_LocalDiskExtent'):
            raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'extent is Cura_LocalDiskExtent')
        
        # check param_partitionstyle and create the partition table
        styleName = param_partitionstyle['InstanceID']
        if styleName == util.partitioning.TYPE_MBR:
            if param_extent['CreationClassName'] != 'Cura_LocalDiskExtent':
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'MBR can be created only on Cura_LocalDiskExtent')
            ret = self.createMBR(extent)
            
        elif styleName == util.partitioning.TYPE_EMBR:
            if param_extent['CreationClassName'] != 'Cura_DiskPartition':
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'EMBR can be created only on Cura_DiskPartition')
            if not extent.isPrimary:
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'EMBR can be created only on primary Cura_DiskPartition')
            ret = self.createEMBR(extent)

        elif styleName == util.partitioning.TYPE_GPT:
            if param_extent['CreationClassName'] != 'Cura_LocalDiskExtent':
                raise pywbem.CIMError(pywbem.CIM_ERR_INVALID_PARAMETER, 'GPT can be created only on Cura_LocalDiskExtent')
            ret = self.createGPT(extent)
        else:
            raise pywbem.CIMError(pywbem.CIM_ERR_NOT_FOUND, 'Unsupported PartitionStyle')

        out_params = []
        return (ret, out_params)
        
    def cim_method_startservice(self, env, object_name):
        """Implements Cura_DiskPartitionConfigurationService.StartService()

        The StartService method places the Service in the started state.
        Note that the function of this method overlaps with the
        RequestedState property. RequestedState was added to the model to
        maintain a record (such as a persisted value) of the last state
        request. Invoking the StartService method should set the
        RequestedState property appropriately. The method returns an
        integer value of 0 if the Service was successfully started, 1 if
        the request is not supported, and any other number to indicate an
        error. In a subclass, the set of possible return codes could be
        specified using a ValueMap qualifier on the method. The strings to
        which the ValueMap contents are translated can also be specified
        in the subclass as a Values array qualifier. \n\nNote: The
        semantics of this method overlap with the RequestStateChange
        method that is inherited from EnabledLogicalElement. This method
        is maintained because it has been widely implemented, and its
        simple "start" semantics are convenient to use.
        
        Keyword arguments:
        env -- Provider Environment (pycimmb.ProviderEnvironment)
        object_name -- A pywbem.CIMInstanceName or pywbem.CIMCLassName 
            specifying the object on which the method StartService() 
            should be invoked.

        Returns a two-tuple containing the return value (type pywbem.Uint32)
        and a list of CIMParameter objects representing the output parameters

        Output parameters: none

        Possible Errors:
        CIM_ERR_ACCESS_DENIED
        CIM_ERR_INVALID_PARAMETER (including missing, duplicate, 
            unrecognized or otherwise incorrect parameters)
        CIM_ERR_NOT_FOUND (the target CIM Class or instance does not 
            exist in the specified namespace)
        CIM_ERR_METHOD_NOT_AVAILABLE (the CIM Server is unable to honor 
            the invocation request)
        CIM_ERR_FAILED (some other unspecified error occurred)

        """

        logger = env.get_logger()
        logger.log_debug('Entering %s.cim_method_startservice()' \
                % self.__class__.__name__)

        # TODO do something
        raise pywbem.CIMError(pywbem.CIM_ERR_METHOD_NOT_AVAILABLE) # Remove to implemented
        out_params = []
        rval = None # TODO (type pywbem.Uint32)
        return (rval, out_params)
        
    class Values(object):
        class DetailedStatus(object):
            Not_Available = pywbem.Uint16(0)
            No_Additional_Information = pywbem.Uint16(1)
            Stressed = pywbem.Uint16(2)
            Predictive_Failure = pywbem.Uint16(3)
            Non_Recoverable_Error = pywbem.Uint16(4)
            Supporting_Entity_in_Error = pywbem.Uint16(5)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 0x8000..

        class RequestedState(object):
            Unknown = pywbem.Uint16(0)
            Enabled = pywbem.Uint16(2)
            Disabled = pywbem.Uint16(3)
            Shut_Down = pywbem.Uint16(4)
            No_Change = pywbem.Uint16(5)
            Offline = pywbem.Uint16(6)
            Test = pywbem.Uint16(7)
            Deferred = pywbem.Uint16(8)
            Quiesce = pywbem.Uint16(9)
            Reboot = pywbem.Uint16(10)
            Reset = pywbem.Uint16(11)
            Not_Applicable = pywbem.Uint16(12)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 32768..65535

        class HealthState(object):
            Unknown = pywbem.Uint16(0)
            OK = pywbem.Uint16(5)
            Degraded_Warning = pywbem.Uint16(10)
            Minor_failure = pywbem.Uint16(15)
            Major_failure = pywbem.Uint16(20)
            Critical_failure = pywbem.Uint16(25)
            Non_recoverable_error = pywbem.Uint16(30)
            # DMTF_Reserved = ..
            # Vendor_Specific = 32768..65535

        class ChangeAffectedElementsAssignedSequence(object):
            Completed_with_No_Error = pywbem.Uint32(0)
            Not_Supported = pywbem.Uint32(1)
            Error_Occured = pywbem.Uint32(2)
            Busy = pywbem.Uint32(3)
            Invalid_Reference = pywbem.Uint32(4)
            Invalid_Parameter = pywbem.Uint32(5)
            Access_Denied = pywbem.Uint32(6)
            # DMTF_Reserved = 7..32767
            # Vendor_Specified = 32768..65535

        class CreateOrModifyPartition(object):
            Success = pywbem.Uint32(0)
            Not_Supported = pywbem.Uint32(1)
            Unknown = pywbem.Uint32(2)
            Timeout = pywbem.Uint32(3)
            Failed = pywbem.Uint32(4)
            Invalid_Parameter = pywbem.Uint32(5)
            # DMTF_Reserved = ..
            # Overlap_Not_Supported = 0x1000
            # No_Available_Partitions = 0x1001
            # Specified_partition_not_on_specified_extent = 0x1002
            # Device_File_Name_not_valid = 0x1003
            # LogicalDisk_with_different_DeviceFileName_exists = 0x1004
            # Method_Reserved = ..
            # Vendor_Specific = 0x8000..

        class TransitioningToState(object):
            Unknown = pywbem.Uint16(0)
            Enabled = pywbem.Uint16(2)
            Disabled = pywbem.Uint16(3)
            Shut_Down = pywbem.Uint16(4)
            No_Change = pywbem.Uint16(5)
            Offline = pywbem.Uint16(6)
            Test = pywbem.Uint16(7)
            Defer = pywbem.Uint16(8)
            Quiesce = pywbem.Uint16(9)
            Reboot = pywbem.Uint16(10)
            Reset = pywbem.Uint16(11)
            Not_Applicable = pywbem.Uint16(12)
            # DMTF_Reserved = ..

        class EnabledDefault(object):
            Enabled = pywbem.Uint16(2)
            Disabled = pywbem.Uint16(3)
            Not_Applicable = pywbem.Uint16(5)
            Enabled_but_Offline = pywbem.Uint16(6)
            No_Default = pywbem.Uint16(7)
            Quiesce = pywbem.Uint16(9)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 32768..65535

        class EnabledState(object):
            Unknown = pywbem.Uint16(0)
            Other = pywbem.Uint16(1)
            Enabled = pywbem.Uint16(2)
            Disabled = pywbem.Uint16(3)
            Shutting_Down = pywbem.Uint16(4)
            Not_Applicable = pywbem.Uint16(5)
            Enabled_but_Offline = pywbem.Uint16(6)
            In_Test = pywbem.Uint16(7)
            Deferred = pywbem.Uint16(8)
            Quiesce = pywbem.Uint16(9)
            Starting = pywbem.Uint16(10)
            # DMTF_Reserved = 11..32767
            # Vendor_Reserved = 32768..65535

        class AvailableRequestedStates(object):
            Enabled = pywbem.Uint16(2)
            Disabled = pywbem.Uint16(3)
            Shut_Down = pywbem.Uint16(4)
            Offline = pywbem.Uint16(6)
            Test = pywbem.Uint16(7)
            Defer = pywbem.Uint16(8)
            Quiesce = pywbem.Uint16(9)
            Reboot = pywbem.Uint16(10)
            Reset = pywbem.Uint16(11)
            # DMTF_Reserved = ..

        class Status(object):
            OK = 'OK'
            Error = 'Error'
            Degraded = 'Degraded'
            Unknown = 'Unknown'
            Pred_Fail = 'Pred Fail'
            Starting = 'Starting'
            Stopping = 'Stopping'
            Service = 'Service'
            Stressed = 'Stressed'
            NonRecover = 'NonRecover'
            No_Contact = 'No Contact'
            Lost_Comm = 'Lost Comm'
            Stopped = 'Stopped'

        class CommunicationStatus(object):
            Unknown = pywbem.Uint16(0)
            Not_Available = pywbem.Uint16(1)
            Communication_OK = pywbem.Uint16(2)
            Lost_Communication = pywbem.Uint16(3)
            No_Contact = pywbem.Uint16(4)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 0x8000..

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

        class OperatingStatus(object):
            Unknown = pywbem.Uint16(0)
            Not_Available = pywbem.Uint16(1)
            Servicing = pywbem.Uint16(2)
            Starting = pywbem.Uint16(3)
            Stopping = pywbem.Uint16(4)
            Stopped = pywbem.Uint16(5)
            Aborted = pywbem.Uint16(6)
            Dormant = pywbem.Uint16(7)
            Completed = pywbem.Uint16(8)
            Migrating = pywbem.Uint16(9)
            Emigrating = pywbem.Uint16(10)
            Immigrating = pywbem.Uint16(11)
            Snapshotting = pywbem.Uint16(12)
            Shutting_Down = pywbem.Uint16(13)
            In_Test = pywbem.Uint16(14)
            Transitioning = pywbem.Uint16(15)
            In_Service = pywbem.Uint16(16)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 0x8000..

        class RequestStateChange(object):
            Completed_with_No_Error = pywbem.Uint32(0)
            Not_Supported = pywbem.Uint32(1)
            Unknown_or_Unspecified_Error = pywbem.Uint32(2)
            Cannot_complete_within_Timeout_Period = pywbem.Uint32(3)
            Failed = pywbem.Uint32(4)
            Invalid_Parameter = pywbem.Uint32(5)
            In_Use = pywbem.Uint32(6)
            # DMTF_Reserved = ..
            Method_Parameters_Checked___Job_Started = pywbem.Uint32(4096)
            Invalid_State_Transition = pywbem.Uint32(4097)
            Use_of_Timeout_Parameter_Not_Supported = pywbem.Uint32(4098)
            Busy = pywbem.Uint32(4099)
            # Method_Reserved = 4100..32767
            # Vendor_Specific = 32768..65535
            class RequestedState(object):
                Enabled = pywbem.Uint16(2)
                Disabled = pywbem.Uint16(3)
                Shut_Down = pywbem.Uint16(4)
                Offline = pywbem.Uint16(6)
                Test = pywbem.Uint16(7)
                Defer = pywbem.Uint16(8)
                Quiesce = pywbem.Uint16(9)
                Reboot = pywbem.Uint16(10)
                Reset = pywbem.Uint16(11)
                # DMTF_Reserved = ..
                # Vendor_Reserved = 32768..65535

        class SetPartitionStyle(object):
            Success = pywbem.Uint32(0)
            Not_Supported = pywbem.Uint32(1)
            Unknown = pywbem.Uint32(2)
            Timeout = pywbem.Uint32(3)
            Failed = pywbem.Uint32(4)
            Invalid_Parameter = pywbem.Uint32(5)
            # DMTF_Reserved = ..
            # Extent_already_has_partition_table = 0x1000
            # Requested_Extent_too_large = 0x1001
            # Style_not_supported_by_Service = 0x1002
            # Method_Reserved = ..
            # Vendor_Specific = 0x8000..

        class PartitioningSchemes(object):
            No_partitions_allowed = pywbem.Uint16(2)
            Volumes_may_be_partitioned_or_treated_as_whole = pywbem.Uint16(3)
            Volumes_must_be_partitioned = pywbem.Uint16(4)

        class StartMode(object):
            Automatic = 'Automatic'
            Manual = 'Manual'

        class PrimaryStatus(object):
            Unknown = pywbem.Uint16(0)
            OK = pywbem.Uint16(1)
            Degraded = pywbem.Uint16(2)
            Error = pywbem.Uint16(3)
            # DMTF_Reserved = ..
            # Vendor_Reserved = 0x8000..

## end of class Cura_DiskPartitionConfigurationServiceProvider
    
## get_providers() for associating CIM Class Name to python provider class name
    
def get_providers(env): 
    initAnaconda(False)
    cura_diskpartitionconfigurationservice_prov = Cura_DiskPartitionConfigurationService(env)  
    return {'Cura_DiskPartitionConfigurationService': cura_diskpartitionconfigurationservice_prov} 
