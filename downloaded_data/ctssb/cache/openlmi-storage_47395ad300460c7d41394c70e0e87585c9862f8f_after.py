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


"""
    This module is the main entry from CIMOM.
    
    All initialization must be done here.
    
    This module instantiates all providers and registers them in CIMOM.
"""

from pyanaconda import anaconda_log
anaconda_log.init()

from StorageConfiguration import StorageConfiguration
from ProviderManager import ProviderManager
from SettingManager import SettingManager

from LMI_StorageExtent import LMI_StorageExtent
from LMI_MDRAIDStorageExtent import LMI_MDRAIDStorageExtent
from LMI_DiskPartition import LMI_DiskPartition
from LMI_GenericDiskPartition import LMI_GenericDiskPartition
from LMI_LVStorageExtent import LMI_LVStorageExtent
from LMI_VGStoragePool import LMI_VGStoragePool
from LMI_PartitionBasedOn import LMI_PartitionBasedOn
from LMI_MDRAIDBasedOn import LMI_MDRAIDBasedOn
from LMI_LVBasedOn import LMI_LVBasedOn
from LMI_LVAllocatedFromStoragePool import LMI_LVAllocatedFromStoragePool
from LMI_VGAssociatedComponentExtent import LMI_VGAssociatedComponentExtent
from LMI_DiskPartitionConfigurationSetting import LMI_DiskPartitionConfigurationSetting
from SettingProvider import ElementSettingDataProvider
from LMI_DiskPartitioningConfigurationService import LMI_DiskPartitionConfigurationService
from LMI_HostedStorageService import LMI_HostedStorageService
from LMI_DiskPartitionConfigurationCapabilities import LMI_DiskPartitionConfigurationCapabilities
from CapabilitiesProvider import ElementCapabilitiesProvider
from LMI_InstalledPartitionTable import LMI_InstalledPartitionTable

import pyanaconda.storage
import pyanaconda.platform
import os

def init_anaconda(env):
    """ Initialize an anaconda instance and return it. """
    logger = env.get_logger()

    logger.log_info("Initializing Anaconda")

    os.system('udevadm control --env=ANACONDA=1')
    os.system('udevadm trigger --subsystem-match block')
    os.system('udevadm settle')

    # hack to insert RAID modules
    for module in ('raid0', 'raid1', 'raid5', 'raid10'):
        os.system('modprobe ' + module)

    # set up storage class instance
    # ugly hack to make it working on both F17 and F18
    try:
        platform = pyanaconda.platform.getPlatform(None)
    except TypeError:
        platform = pyanaconda.platform.getPlatform()  #IGNORE:E1120
    storage = pyanaconda.storage.Storage(platform=platform)

    # identify the system's storage devices
    storage.devicetree.populate()

    return storage

def get_providers(env):
    """
        Called by CIMOM. Initialize OpenLMI and return dictionary of all
        providers we implement.
    """
    config = StorageConfiguration()
    config.load()

    manager = ProviderManager()
    setting_manager = SettingManager(config)
    setting_manager.load()
    storage = init_anaconda(env)

    providers = {}

    # common construction options
    opts = {'env': env,
            'storage': storage,
            'config': config,
            'provider_manager': manager,
            'setting_manager': setting_manager}
    # StorageDevice providers
    provider = LMI_StorageExtent(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_StorageExtent'] = provider

    provider = LMI_MDRAIDStorageExtent(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_MDRAIDStorageExtent'] = provider

    provider = LMI_DiskPartition(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_DiskPartition'] = provider

    provider = LMI_GenericDiskPartition(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_GenericDiskPartition'] = provider

    provider = LMI_LVStorageExtent(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_LVStorageExtent'] = provider

    provider = LMI_VGStoragePool(**opts)    #IGNORE:W0142
    manager.add_device_provider(provider)
    providers['LMI_VGStoragePool'] = provider

    # settings
    setting_provider = LMI_DiskPartitionConfigurationSetting(**opts)    #IGNORE:W0142
    manager.add_setting_provider(setting_provider)
    providers['LMI_DiskPartitionConfigurationSetting'] = setting_provider
    assoc_provider = ElementSettingDataProvider(#IGNORE:W0142
            setting_provider=setting_provider,
            managed_element_classname="CIM_DiskPartition",
            setting_data_classname="LMI_DiskPartitionConfigurationSetting",
            **opts)
    providers['LMI_DiskPartitionElementSettingData'] = assoc_provider


    # services & capabilities
    service_provider = LMI_DiskPartitionConfigurationService(**opts)    #IGNORE:W0142
    manager.add_service_provider(service_provider)
    providers['LMI_DiskPartitionConfigurationService'] = service_provider

    cap_provider = LMI_DiskPartitionConfigurationCapabilities(**opts)   #IGNORE:W0142
    manager.add_capabilities_provider(cap_provider)
    providers['LMI_DiskPartitionConfigurationCapabilities'] = cap_provider

    assoc_provider = ElementCapabilitiesProvider(#IGNORE:W0142
            "LMI_DiskPartitionElementCapabilities",
            cap_provider, service_provider, **opts)
    providers['LMI_DiskPartitionElementCapabilities'] = assoc_provider


    # Associations
    provider = LMI_PartitionBasedOn(**opts)    #IGNORE:W0142
    providers['LMI_PartitionBasedOn'] = provider

    provider = LMI_MDRAIDBasedOn(**opts)    #IGNORE:W0142
    providers['LMI_MDRAIDBasedOn'] = provider

    provider = LMI_LVBasedOn(**opts)    #IGNORE:W0142
    providers['LMI_LVBasedOn'] = provider

    provider = LMI_LVAllocatedFromStoragePool(**opts)    #IGNORE:W0142
    providers['LMI_LVAllocatedFromStoragePool'] = provider

    provider = LMI_VGAssociatedComponentExtent(**opts)    #IGNORE:W0142
    providers['LMI_VGAssociatedComponentExtent'] = provider

    provider = LMI_HostedStorageService(**opts)    #IGNORE:W0142
    providers['LMI_HostedStorageService'] = provider

    provider = LMI_InstalledPartitionTable(**opts)    #IGNORE:W0142
    providers['LMI_InstalledPartitionTable'] = provider

    print "providers:", providers

    return providers

