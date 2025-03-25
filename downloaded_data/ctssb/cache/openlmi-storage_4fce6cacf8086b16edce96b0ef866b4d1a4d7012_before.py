#!/usr/bin/python
# -*- Coding:utf-8 -*-
#
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

from test_base import StorageTestBase
import unittest
import pywbem

class TestSetPartitionStyle(StorageTestBase):
    """
        Test LMI_DiskPartitionConfigurationService.SetPartitionStyle
        with different parameters.
    """

    DISK_CLASS = "LMI_StorageExtent"
    MBR_CLASS = "LMI_DiskPartition"
    GPT_CLASS = "LMI_GenericDiskPartition"

    STYLE_EMBR = 4100
    STYLE_MBR = 2
    STYLE_GPT = 3

    def setUp(self):
        """ Find disk partition service. """
        super(TestSetPartitionStyle, self).setUp()
        self.service = self.wbemconnection.EnumerateInstanceNames(
                "LMI_DiskPartitionConfigurationService")[0]

    def _check_name(self, partname, classname):
        """ Check that CIMInstanceName represents a partition. """
        self.assertEqual(partname['SystemName'], self.SYSTEM_NAME)
        self.assertEqual(partname['SystemCreationClassName'], self.SYSTEM_CLASS_NAME)
        self.assertEqual(partname['CreationClassName'], classname)

    def _create_disk_name(self, device_id):
        """ Return CIMInstanceName for given DeviceID."""
        name = pywbem.CIMInstanceName(
                classname=self.DISK_CLASS,
                keybindings={
                        'DeviceID': device_id,
                        'SystemCreationClassName': self.SYSTEM_CLASS_NAME,
                        'SystemName': self.SYSTEM_NAME,
                        'CreationClassName': self.DISK_CLASS})
        return name

    def _check_capabilities_name(self, capabilities_name, partition_style):
        """
            Check that given partition capabilities name represent givent
            partition_style.
        """
        capabilities = self.wbemconnection.GetInstance(capabilities_name)
        self.assertEqual(capabilities[0]['PartitionStyle'], partition_style)


    def _check_partition_table_type(self, diskname, partition_style):
        """
            Check that disk (represented by CIMInstanceName diskname)
            has partition table partition_style.
        """
        capabilities = self.wbemconnection.Associators(
                diskname,
                AssocClass="LMI_InstalledPartitionTable")
        # there must be only one associated Capabilities instance
        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0]['PartitionStyle'], partition_style)

    def _get_capabilities_name(self, style):
        """
            Return CIMInstanceName with partition capabilities representing
            given partition style.
        """
        if style == self.STYLE_EMBR:
            style_name = "EMBR"
        elif style == self.STYLE_MBR:
            style_name = "MBR"
        elif style == self.STYLE_GPT:
            style_name = "GPT"

        return pywbem.CIMInstanceName(
                classname="LMI_DiskPartitionConfigurationCapabilities",
                keybindings={
                        'InstanceID': "LMI:LMI_DiskPartitionConfigurationCapabilities:" + style_name
                })

    def test_no_params(self):
        """ Try SetPartitionStyle with no parameters"""
        # Extent = None -> error
        self.assertRaises(pywbem.CIMError, self.wbemconnection.InvokeMethod,
                "SetPartitionStyle",
                self.service)

    def test_no_partition_style(self):
        """ Test SetPartitionStyle with no PartitionStyle parameter."""
        diskname = self._create_disk_name(self.disks[0])
        # Extent = sda -> success, with default capabilities (GPT)
        (retval, outparams) = self.wbemconnection.InvokeMethod(
                "SetPartitionStyle",
                self.service,
                Extent=diskname)
        self.assertEqual(retval, 0)
        self._check_partition_table_type(diskname, self.STYLE_GPT)
        self.assertDictEqual(outparams, {})

    def test_gpt(self):
        """ Test SetPartitionStyle with GPT capabilities."""
        diskname = self._create_disk_name(self.disks[0])
        part_style = self._get_capabilities_name(self.STYLE_GPT)
        # Extent = sda, partStyle = MBR -> success
        (retval, outparams) = self.wbemconnection.InvokeMethod(
                "SetPartitionStyle",
                self.service,
                Extent=diskname,
                PartitionStyle=part_style)
        self.assertEqual(retval, 0)
        self._check_partition_table_type(diskname, self.STYLE_GPT)
        self.assertDictEqual(outparams, {})

    def test_mbr(self):
        """ Test SetPartitionStyle with GPT capabilities."""
        diskname = self._create_disk_name(self.disks[0])
        part_style = self._get_capabilities_name(self.STYLE_MBR)
        # Extent = sda, partStyle = MBR -> success
        (retval, outparams) = self.wbemconnection.InvokeMethod(
                "SetPartitionStyle",
                self.service,
                Extent=diskname,
                PartitionStyle=part_style)
        self.assertEqual(retval, 0)
        self._check_partition_table_type(diskname, self.STYLE_MBR)
        self.assertDictEqual(outparams, {})

    def test_embr(self):
        """ Test SetPartitionStyle with EMBR capabilities."""
        diskname = self._create_disk_name(self.disks[0])
        part_style = self._get_capabilities_name(self.STYLE_EMBR)
        # Extent = sda, partStyle = MBR -> success
        self.assertRaises(pywbem.CIMError, self.wbemconnection.InvokeMethod,
                "SetPartitionStyle",
                self.service,
                Extent=diskname,
                PartitionStyle=part_style)

    def test_on_partition(self):
        """ Test SetPartitionStyle on a partition."""
        diskname = self._create_disk_name(self.disks[0])
        # create a partition table on disk
        part_style = self._get_capabilities_name(self.STYLE_MBR)
        # Extent = sda, partStyle = MBR -> success
        (retval, outparams) = self.wbemconnection.InvokeMethod(
                "SetPartitionStyle",
                self.service,
                Extent=diskname,
                PartitionStyle=part_style)
        self.assertEqual(retval, 0)
        self._check_partition_table_type(diskname, self.STYLE_MBR)
        self.assertDictEqual(outparams, {})

        # create partition on the disk
        (retval, outparams) = self.wbemconnection.InvokeMethod(
                "CreateOrModifyPartition",
                self.service,
                extent=diskname)
        self.assertEqual(retval, 0)
        partition = outparams['partition']

        # try to create partition table on it
        self.assertRaises(pywbem.CIMError, self.wbemconnection.InvokeMethod,
                "SetPartitionStyle",
                self.service,
                Extent=partition,
                PartitionStyle=part_style)

        # remove the partition
        self.wbemconnection.DeleteInstance(partition)






    #TODO: add SetPartitionStyle on RAID, LVM etc.

if __name__ == '__main__':
    unittest.main()
