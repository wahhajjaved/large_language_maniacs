#
# platform.py:  Architecture-specific information
#
# Copyright (C) 2009
# Red Hat, Inc.  All rights reserved.
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
#
# Authors: Chris Lumens <clumens@redhat.com>
#

import iutil
import parted
import storage
from storage.errors import *

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)
N_ = lambda x: x

class Platform(object):
    """Platform

       A class containing platform-specific information and methods for use
       during installation.  The intent is to eventually encapsulate all the
       architecture quirks in one place to avoid lots of platform checks
       throughout anaconda."""
    _bootFSType = "ext3"
    _bootloaderPackage = None
    _diskType = parted.diskType["msdos"]
    _minimumSector = 0
    _supportsMdRaidBoot = False

    def __init__(self, anaconda):
        """Creates a new Platform object.  This is basically an abstract class.
           You should instead use one of the platform-specific classes as
           returned by getPlatform below.  Not all subclasses need to provide
           all the methods in this class."""
        self.anaconda = anaconda

    def _mntDict(self):
        """Return a dictionary mapping mount points to devices."""
        ret = {}
        for device in [d for d in self.anaconda.id.storage.devices if d.format.mountable]:
            ret[device.format.mountpoint] = device

        return ret

    def bootDevice(self):
        """Return the device where /boot is mounted."""
        if self.__class__ is Platform:
            raise NotImplementedError("bootDevice not implemented for this platform")

        mntDict = self._mntDict()
        return mntDict.get("/boot", mntDict.get("/"))

    @property
    def bootFSType(self):
        """Return the default filesystem type for the boot partition."""
        return self._bootFSType

    def bootloaderChoices(self, bl):
        """Return the default list of places to install the bootloader.
           This is returned as a dictionary of locations to (device, identifier)
           tuples.  If there is no boot device, an empty dictionary is
           returned."""
        if self.__class__ is Platform:
            raise NotImplementedError("bootloaderChoices not implemented for this platform")

        bootDev = self.bootDevice()
        ret = {}

        if not bootDev:
            return ret

        if bootDev.type == "mdarray":
            ret["boot"] = (bootDev.name, N_("RAID Device"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))
        else:
            ret["boot"] = (bootDev.name, N_("First sector of boot partition"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))

        return ret

    @property
    def bootloaderPackage(self):
        return self._bootloaderPackage

    def checkBootRequest(self, req, diskset):
        """Perform an architecture-specific check on the boot device.  Not all
           platforms may need to do any checks.  Raises an exception if there
           is a problem, or returns True otherwise."""
        return

    @property
    def diskType(self):
        """Return the disk label type as a parted.DiskType."""
        return self._diskType

    @diskType.setter
    def diskType(self, value):
        """Sets the disk label type."""
        self._diskType = value

    @property
    def minimumSector(self, disk):
        """Return the minimum starting sector for the provided disk."""
        return self._minimumSector

    def setDefaultPartitioning(self):
        """Return the default platform-specific partitioning information."""
        return [("/boot", self.bootFSType, 200, None, 0, 0)]

    @property
    def supportsMdRaidBoot(self):
        """Does the platform support /boot on MD RAID?"""
        return self._supportsMdRaidBoot

class EFI(Platform):
    _diskType = parted.diskType["gpt"]

    def bootDevice(self):
        mntDict = self._mntDict()
        return mntDict.get("/boot/efi")

    def bootloaderChoices(self, bl):
        bootDev = self.bootDevice()
        ret = {}

        if not bootDev:
            return ret

        ret["boot"] = (bootDev.name, N_("EFI System Partition"))
        return ret

    def checkBootRequest(self, req, diskset):
        if not req.device or not hasattr(req, "drive"):
            return

        bootPart = None
        for drive in req.drive:
            bootPart = diskset.disks[drive].getPartitionByPath("/dev/%s" % req.device)
            if bootPart:
                break

        if not bootPart:
            return

        if req.mountpoint == "/boot":
            if not bootPart.fileSystem.type.startswith("ext"):
                raise FSError("/boot is not ext2")
            elif req.mountpoint == "/boot/efi":
                if not bootPart.fileSystem.type.startswith("fat"):
                    raise FSError("/boot/efi is not vfat")

    def setDefaultPartitioning(self):
        ret = Platform.setDefaultPartitioning(self)

        # Only add the EFI partition to the default set if there's not already
        # one on the system.
        if len(filter(lambda dev: dev.format.type == "efi" and dev.size < 256 and dev.bootable,
                      self.anaconda.id.storage.partitions)) == 0:
            ret.append(("/boot/efi", "efi", 50, 200, 1, 0))

        return ret

class Alpha(Platform):
    _diskType = parted.diskType["bsd"]

    def checkBootRequest(self, req, diskset):
        if not req.device or not hasattr(req, "drive"):
            return

        bootPart = None
        for drive in req.drive:
            bootPart = diskset.disks[drive].getPartitionByPath("/dev/%s" % req.device)
            if bootPart:
                break

        if not bootPart:
            return

        disk = bootPart.disk

        # Check that we're a BSD disk label
        if not disk.type == self.diskType:
            raise DeviceError("Disk label is not %s" % self.diskType)

        # The first free space should start at the beginning of the drive and
        # span for a megabyte or more.
        free = disk.getFirstPartition()
        while free:
            if free.type & parted.PARTITION_FREESPACE:
                break

            free = free.nextPartition()

        if not free or free.geoemtry.start != 1L or free.getSize(unit="MB") < 1:
            raise DeviceError("Disk does not have enough free space at the beginning")

        return

class IA64(EFI):
    _bootloaderPackage = "elilo"

    def __init__(self, anaconda):
        EFI.__init__(self, anaconda)

class PPC(Platform):
    _bootloaderPackage = "yaboot"
    _ppcMachine = iutil.getPPCMachine()
    _supportsMdRaidBoot = True

    @property
    def ppcMachine(self):
        return self._ppcMachine

class IPSeriesPPC(PPC):
    def bootDevice(self):
        bootDev = None

        # We want the first PReP partition.
        for device in storage.partitions:
            if device.partedPartition.getFlag(parted.PARTITION_PREP):
                bootDev = device
                break

        return bootDev

    def bootloaderChoices(self, bl):
        ret = {}

        bootDev = self.bootDevice()
        if not bootDev:
            return ret

        if bootDev.type == "mdarray":
            ret["boot"] = (bootDev.name, N_("RAID Device"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))
        else:
            ret["boot"] = (bootDev.name, N_("PPC PReP Boot"))

        return ret

    def checkBootRequest(self, req, diskset):
        if not req.device or not hasattr(req, "drive"):
            return

        bootPart = None
        for drive in req.drive:
            bootPart = diskset.disks[drive].getPartitionByPath("/dev/%s" % req.device)
            if bootPart and (bootPart.geometry.end * bootPart.geometry.device.sectorSize /
                             (1024.0 * 1024)) > 4096:
                raise DeviceError("Boot partition is located too high")

        return

    def setDefaultPartitioning(self):
        ret = PPC.setDefaultPartitioning(self)
        ret.insert(0, (None, "PPC PReP Boot", 4, None, 0, 0))
        return ret

class NewWorldPPC(PPC):
    _diskType = parted.diskType["mac"]

    def bootDevice(self):
        bootDev = None

        for device in self.anaconda.id.storage.devices.values():
            # XXX do we need to also check the size?
            if device.format.type == "hfs" and device.bootable:
                bootDev = device

        return bootDev

    def bootloaderChoices(self, bl):
        ret = {}

        bootDev = self.bootDevice()
        if not bootDev:
            return ret

        if bootDev.type == "mdarray":
            ret["boot"] = (bootDev.name, N_("RAID Device"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))
        else:
            ret["boot"] = (bootDev.name, N_("Apple Bootstrap"))
            for (n, device) in enumerate(self.anaconda.id.storage.partitions):
                if device.format.type == "hfs" and device.bootable and device.path != bootDev.path:
                    ret["boot%d" % n] = (device.path, N_("Apple Bootstrap"))

        return ret

    def setDefaultPartitioning(self):
        ret = Platform.setDefaultPartitioning(self)
        ret.insert(0, (None, "Apple Bootstrap", 1, 1, 0, 0))
        return ret

class S390(Platform):
    _bootloaderPackage = "s390utils"

    def __init__(self, anaconda):
        Platform.__init__(self, anaconda)

class Sparc(Platform):
    _diskType = parted.diskType["sun"]

    @property
    def minimumSector(self, disk):
        (cylinders, heads, sector) = disk.device.biosGeometry
        start = long(sectors * heads)
        start /= long(1024 / disk.device.sectorSize)
        return start+1

class X86(EFI):
    _bootloaderPackage = "grub"
    _isEfi = iutil.isEfi()
    _supportsMdRaidBoot = True

    def __init__(self, anaconda):
        EFI.__init__(self, anaconda)

        if self.isEfi:
            self.diskType = parted.diskType["gpt"]
        else:
            self.diskType = parted.diskType["msdos"]

    def bootDevice(self):
        if self.isEfi:
            return EFI.bootDevice(self)
        else:
            return Platform.bootDevice(self)

    def bootloaderChoices(self, bl):
        if self.isEfi:
            return EFI.bootloaderChoices(self, bl)

        bootDev = self.bootDevice()
        ret = {}

        if not bootDev:
            return {}

        if bootDev.type == "mdarray":
            ret["boot"] = (bootDev.name, N_("RAID Device"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))
        else:
            ret["boot"] = (bootDev.name, N_("First sector of boot partition"))
            ret["mbr"] = (bl.drivelist[0], N_("Master Boot Record (MBR)"))

        return ret

    @property
    def isEfi(self):
        return self._isEfi

    def setDefaultPartitioning(self):
        if self.isEfi:
            return EFI.setDefaultPartitioning(self)
        else:
            return Platform.setDefaultPartitioning(self)

def getPlatform(anaconda):
    """Check the architecture of the system and return an instance of a
       Platform subclass to match.  If the architecture could not be determined,
       raise an exception."""
    if iutil.isAlpha():
        return Alpha(anaconda)
    elif iutil.isIA64():
        return IA64(anaconda)
    elif iutil.isPPC():
        ppcMachine = iutil.getPPCMachine()

        if ppcMachine == "PMac" and iutil.getPPCMacGen() == "NewWorld":
            return NewWorldPPC(anaconda)
        elif ppcMachine in ["iSeries", "pSeries"]:
            return IPSeriesPPC(anaconda)
        else:
            raise SystemError, "Unsupported PPC machine type"
    elif iutil.isS390():
        return S390(anaconda)
    elif iutil.isSparc():
        return Sparc(anaconda)
    elif iutil.isX86():
        return X86(anaconda)
    else:
        raise SystemError, "Could not determine system architecture."
