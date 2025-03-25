# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2010 Citrix Systems, Inc.
# Copyright 2011 Piston Cloud Computing, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Helper methods for operations related to the management of VM records and
their attributes like VDIs, VIFs, as well as their lookup functions.
"""

import contextlib
import cPickle as pickle
import decimal
import os
import re
import time
import urllib
import urlparse
import uuid
from xml.dom import minidom
from xml.parsers import expat

from eventlet import greenthread

from nova.compute import instance_types
from nova.compute import power_state
from nova import db
from nova import exception
from nova import flags
from nova.image import glance
from nova.openstack.common import cfg
from nova.openstack.common import excutils
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova import utils
from nova.virt.disk import api as disk
from nova.virt import xenapi
from nova.virt.xenapi import volume_utils


LOG = logging.getLogger(__name__)

xenapi_vm_utils_opts = [
    cfg.StrOpt('default_os_type',
               default='linux',
               help='Default OS type'),
    cfg.IntOpt('block_device_creation_timeout',
               default=10,
               help='Time to wait for a block device to be created'),
    cfg.IntOpt('max_kernel_ramdisk_size',
               default=16 * 1024 * 1024,
               help='Maximum size in bytes of kernel or ramdisk images'),
    cfg.StrOpt('sr_matching_filter',
               default='other-config:i18n-key=local-storage',
               help='Filter for finding the SR to be used to install guest '
                    'instances on. The default value is the Local Storage in '
                    'default XenServer/XCP installations. To select an SR '
                    'with a different matching criteria, you could set it to '
                    'other-config:my_favorite_sr=true. On the other hand, to '
                    'fall back on the Default SR, as displayed by XenCenter, '
                    'set this flag to: default-sr:true'),
    cfg.BoolOpt('xenapi_sparse_copy',
                default=True,
                help='Whether to use sparse_copy for copying data on a '
                     'resize down (False will use standard dd). This speeds '
                     'up resizes down considerably since large runs of zeros '
                     'won\'t have to be rsynced'),
    cfg.IntOpt('xenapi_num_vbd_unplug_retries',
               default=10,
               help='Maximum number of retries to unplug VBD'),
    ]

FLAGS = flags.FLAGS
FLAGS.register_opts(xenapi_vm_utils_opts)

XENAPI_POWER_STATE = {
    'Halted': power_state.SHUTDOWN,
    'Running': power_state.RUNNING,
    'Paused': power_state.PAUSED,
    'Suspended': power_state.SUSPENDED,
    'Crashed': power_state.CRASHED}


SECTOR_SIZE = 512
MBR_SIZE_SECTORS = 63
MBR_SIZE_BYTES = MBR_SIZE_SECTORS * SECTOR_SIZE
KERNEL_DIR = '/boot/guest'


class ImageType(object):
    """Enumeration class for distinguishing different image types

    | 0 - kernel image (goes on dom0's filesystem)
    | 1 - ramdisk image (goes on dom0's filesystem)
    | 2 - disk image (local SR, partitioned by objectstore plugin)
    | 3 - raw disk image (local SR, NOT partitioned by plugin)
    | 4 - vhd disk image (local SR, NOT inspected by XS, PV assumed for
    |     linux, HVM assumed for Windows)
    | 5 - ISO disk image (local SR, NOT partitioned by plugin)
    """

    KERNEL = 0
    RAMDISK = 1
    DISK = 2
    DISK_RAW = 3
    DISK_VHD = 4
    DISK_ISO = 5
    _ids = (KERNEL, RAMDISK, DISK, DISK_RAW, DISK_VHD, DISK_ISO)

    KERNEL_STR = "kernel"
    RAMDISK_STR = "ramdisk"
    DISK_STR = "root"
    DISK_RAW_STR = "os_raw"
    DISK_VHD_STR = "vhd"
    DISK_ISO_STR = "iso"
    _strs = (KERNEL_STR, RAMDISK_STR, DISK_STR, DISK_RAW_STR, DISK_VHD_STR,
                DISK_ISO_STR)

    @classmethod
    def to_string(cls, image_type):
        return dict(zip(ImageType._ids, ImageType._strs)).get(image_type)

    @classmethod
    def from_string(cls, image_type_str):
        return dict(zip(ImageType._strs, ImageType._ids)).get(image_type_str)


def create_vm(session, instance, kernel, ramdisk, use_pv_kernel=False):
    """Create a VM record.  Returns new VM reference.
    the use_pv_kernel flag indicates whether the guest is HVM or PV

    There are 3 scenarios:

        1. Using paravirtualization, kernel passed in

        2. Using paravirtualization, kernel within the image

        3. Using hardware virtualization
    """
    inst_type_id = instance.instance_type_id
    instance_type = instance_types.get_instance_type(inst_type_id)
    mem = str(long(instance_type['memory_mb']) * 1024 * 1024)
    vcpus = str(instance_type['vcpus'])

    rec = {
        'actions_after_crash': 'destroy',
        'actions_after_reboot': 'restart',
        'actions_after_shutdown': 'destroy',
        'affinity': '',
        'blocked_operations': {},
        'ha_always_run': False,
        'ha_restart_priority': '',
        'HVM_boot_params': {},
        'HVM_boot_policy': '',
        'is_a_template': False,
        'memory_dynamic_min': mem,
        'memory_dynamic_max': mem,
        'memory_static_min': '0',
        'memory_static_max': mem,
        'memory_target': mem,
        'name_description': '',
        'name_label': instance.name,
        'other_config': {'allowvssprovider': str(False),
                         'nova_uuid': str(instance.uuid)},
        'PCI_bus': '',
        'platform': {'acpi': 'true', 'apic': 'true', 'pae': 'true',
                     'viridian': 'true', 'timeoffset': '0'},
        'PV_args': '',
        'PV_bootloader': '',
        'PV_bootloader_args': '',
        'PV_kernel': '',
        'PV_legacy_args': '',
        'PV_ramdisk': '',
        'recommendations': '',
        'tags': [],
        'user_version': '0',
        'VCPUs_at_startup': vcpus,
        'VCPUs_max': vcpus,
        'VCPUs_params': {},
        'xenstore_data': {}}

    # Complete VM configuration record according to the image type
    # non-raw/raw with PV kernel/raw in HVM mode
    if use_pv_kernel:
        rec['platform']['nx'] = 'false'
        if instance.kernel_id:
            # 1. Kernel explicitly passed in, use that
            rec['PV_args'] = 'root=/dev/xvda1'
            rec['PV_kernel'] = kernel
            rec['PV_ramdisk'] = ramdisk
        else:
            # 2. Use kernel within the image
            rec['PV_bootloader'] = 'pygrub'
    else:
        # 3. Using hardware virtualization
        rec['platform']['nx'] = 'true'
        rec['HVM_boot_params'] = {'order': 'dc'}
        rec['HVM_boot_policy'] = 'BIOS order'

    vm_ref = session.call_xenapi('VM.create', rec)
    LOG.debug(_('Created VM'), instance=instance)
    return vm_ref


def ensure_free_mem(session, instance):
    inst_type_id = instance.instance_type_id
    instance_type = instance_types.get_instance_type(inst_type_id)
    mem = long(instance_type['memory_mb']) * 1024 * 1024
    #get free memory from host
    host = session.get_xenapi_host()
    host_free_mem = long(session.call_xenapi("host.compute_free_memory",
                                             host))
    return host_free_mem >= mem


def find_vbd_by_number(session, vm_ref, number):
    """Get the VBD reference from the device number"""
    vbd_refs = session.call_xenapi("VM.get_VBDs", vm_ref)
    if vbd_refs:
        for vbd_ref in vbd_refs:
            try:
                vbd_rec = session.call_xenapi("VBD.get_record", vbd_ref)
                if vbd_rec['userdevice'] == str(number):
                    return vbd_ref
            except session.XenAPI.Failure, exc:
                LOG.exception(exc)
    raise volume_utils.StorageError(
            _('VBD not found in instance %s') % vm_ref)


def unplug_vbd(session, vbd_ref):
    """Unplug VBD from VM"""
    # Call VBD.unplug on the given VBD, with a retry if we get
    # DEVICE_DETACH_REJECTED.  For reasons which we don't understand,
    # we're seeing the device still in use, even when all processes
    # using the device should be dead.
    max_attempts = FLAGS.xenapi_num_vbd_unplug_retries + 1
    for num_attempt in xrange(1, max_attempts + 1):
        try:
            session.call_xenapi('VBD.unplug', vbd_ref)
            return
        except session.XenAPI.Failure, exc:
            err = len(exc.details) > 0 and exc.details[0]
            if err == 'DEVICE_ALREADY_DETACHED':
                LOG.info(_('VBD %s already detached'), vbd_ref)
                return
            elif err == 'DEVICE_DETACH_REJECTED':
                LOG.info(_('VBD %(vbd_ref)s detach rejected, attempt'
                           ' %(num_attempt)d/%(max_attempts)d'), locals())
            else:
                LOG.exception(exc)
                raise volume_utils.StorageError(
                        _('Unable to unplug VBD %s') % vbd_ref)

        greenthread.sleep(1)

    raise volume_utils.StorageError(
            _('Reached maximum number of retries trying to unplug VBD %s')
            % vbd_ref)


def destroy_vbd(session, vbd_ref):
    """Destroy VBD from host database"""
    try:
        session.call_xenapi('VBD.destroy', vbd_ref)
    except session.XenAPI.Failure, exc:
        LOG.exception(exc)
        raise volume_utils.StorageError(
                _('Unable to destroy VBD %s') % vbd_ref)


def create_vbd(session, vm_ref, vdi_ref, userdevice, vbd_type='disk',
               read_only=False, bootable=False):
    """Create a VBD record and returns its reference."""
    vbd_rec = {}
    vbd_rec['VM'] = vm_ref
    vbd_rec['VDI'] = vdi_ref
    vbd_rec['userdevice'] = str(userdevice)
    vbd_rec['bootable'] = bootable
    vbd_rec['mode'] = read_only and 'RO' or 'RW'
    vbd_rec['type'] = vbd_type
    vbd_rec['unpluggable'] = True
    vbd_rec['empty'] = False
    vbd_rec['other_config'] = {}
    vbd_rec['qos_algorithm_type'] = ''
    vbd_rec['qos_algorithm_params'] = {}
    vbd_rec['qos_supported_algorithms'] = []
    LOG.debug(_('Creating %(vbd_type)s-type VBD for VM %(vm_ref)s,'
                ' VDI %(vdi_ref)s ... '), locals())
    vbd_ref = session.call_xenapi('VBD.create', vbd_rec)
    LOG.debug(_('Created VBD %(vbd_ref)s for VM %(vm_ref)s,'
                ' VDI %(vdi_ref)s.'), locals())
    return vbd_ref


def destroy_vdi(session, vdi_ref):
    try:
        session.call_xenapi('VDI.destroy', vdi_ref)
    except session.XenAPI.Failure, exc:
        LOG.exception(exc)
        raise volume_utils.StorageError(
                _('Unable to destroy VDI %s') % vdi_ref)


def create_vdi(session, sr_ref, info, disk_type, virtual_size,
               read_only=False):
    """Create a VDI record and returns its reference."""
    # create_vdi may be called simply while creating a volume
    # hence information about instance may or may not be present
    otherconf = {}
    if not isinstance(info, basestring):
        name_label = info['name']
        otherconf = {'nova_instance_uuid': info['uuid'],
                     'nova_disk_type': disk_type}
    else:
        name_label = info
    vdi_ref = session.call_xenapi("VDI.create",
         {'name_label': name_label,
          'name_description': disk_type,
          'SR': sr_ref,
          'virtual_size': str(virtual_size),
          'type': 'User',
          'sharable': False,
          'read_only': read_only,
          'xenstore_data': {},
          'other_config': otherconf,
          'sm_config': {},
          'tags': []})
    LOG.debug(_('Created VDI %(vdi_ref)s (%(name_label)s,'
                ' %(virtual_size)s, %(read_only)s) on %(sr_ref)s.'),
              locals())
    return vdi_ref


def copy_vdi(session, sr_ref, vdi_to_copy_ref):
    """Copy a VDI and return the new VDIs reference."""
    vdi_ref = session.call_xenapi('VDI.copy', vdi_to_copy_ref, sr_ref)
    LOG.debug(_('Copied VDI %(vdi_ref)s from VDI '
                '%(vdi_to_copy_ref)s on %(sr_ref)s.') % locals())
    return vdi_ref


def clone_vdi(session, vdi_to_clone_ref):
    """Clones a VDI and return the new VDIs reference."""
    vdi_ref = session.call_xenapi('VDI.clone', vdi_to_clone_ref)
    LOG.debug(_('Cloned VDI %(vdi_ref)s from VDI '
                '%(vdi_to_clone_ref)s') % locals())
    return vdi_ref


def set_vdi_name(session, vdi_uuid, label, description, vdi_ref=None):
    vdi_ref = vdi_ref or session.call_xenapi('VDI.get_by_uuid', vdi_uuid)
    session.call_xenapi('VDI.set_name_label', vdi_ref, label)
    session.call_xenapi('VDI.set_name_description', vdi_ref, description)


def get_vdi_for_vm_safely(session, vm_ref):
    """Retrieves the primary VDI for a VM"""
    vbd_refs = session.call_xenapi("VM.get_VBDs", vm_ref)
    for vbd in vbd_refs:
        vbd_rec = session.call_xenapi("VBD.get_record", vbd)
        # Convention dictates the primary VDI will be userdevice 0
        if vbd_rec['userdevice'] == '0':
            vdi_rec = session.call_xenapi("VDI.get_record", vbd_rec['VDI'])
            return vbd_rec['VDI'], vdi_rec
    raise exception.NovaException(_("No primary VDI found for %(vm_ref)s")
                                  % locals())


def create_snapshot(session, instance, vm_ref, label):
    """Creates Snapshot (Template) VM, Snapshot VBD, Snapshot VDI,
    Snapshot VHD"""
    LOG.debug(_("Snapshotting with label '%(label)s'"), locals(),
              instance=instance)

    vm_vdi_ref, vm_vdi_rec = get_vdi_for_vm_safely(session, vm_ref)
    sr_ref = vm_vdi_rec["SR"]

    original_parent_uuid = get_vhd_parent_uuid(session, vm_vdi_ref)

    template_vm_ref = session.call_xenapi('VM.snapshot', vm_ref, label)
    template_vdi_rec = get_vdi_for_vm_safely(session, template_vm_ref)[1]
    template_vdi_uuid = template_vdi_rec["uuid"]

    LOG.debug(_('Created snapshot %(template_vm_ref)s'), locals(),
              instance=instance)

    parent_uuid, base_uuid = _wait_for_vhd_coalesce(
            session, instance, sr_ref, vm_vdi_ref, original_parent_uuid)

    template_vdi_uuids = {'base': base_uuid,
                          'image': parent_uuid,
                          'snap': template_vdi_uuid}
    return template_vm_ref, template_vdi_uuids


def get_sr_path(session):
    """Return the path to our storage repository

    This is used when we're dealing with VHDs directly, either by taking
    snapshots or by restoring an image in the DISK_VHD format.
    """
    sr_ref = safe_find_sr(session)
    sr_rec = session.call_xenapi("SR.get_record", sr_ref)
    sr_uuid = sr_rec["uuid"]
    return os.path.join(FLAGS.xenapi_sr_base_path, sr_uuid)


def find_cached_image(session, image_id, sr_ref):
    """Returns the vdi-ref of the cached image."""
    for vdi_ref, vdi_rec in _get_all_vdis_in_sr(session, sr_ref):
        other_config = vdi_rec['other_config']

        try:
            image_id_match = other_config['image-id'] == image_id
        except KeyError:
            image_id_match = False

        # NOTE(sirp): `VDI.copy` stores the partially-completed file in the SR.
        # In order to avoid these half-baked files, we compare its current size
        # to the expected size pulled from the original cache file.
        try:
            size_match = (other_config['expected_physical_utilisation'] ==
                          vdi_rec['physical_utilisation'])
        except KeyError:
            size_match = False

        if image_id_match and size_match:
            return vdi_ref

    return None


def upload_image(context, session, instance, vdi_uuids, image_id):
    """Requests that the Glance plugin bundle the specified VDIs and
    push them into Glance using the specified human-friendly name.
    """
    # NOTE(sirp): Currently we only support uploading images as VHD, there
    # is no RAW equivalent (yet)
    LOG.debug(_("Asking xapi to upload %(vdi_uuids)s as"
                " ID %(image_id)s"), locals(), instance=instance)

    glance_host, glance_port = glance.pick_glance_api_server()

    sys_meta = db.instance_system_metadata_get(context, instance['uuid'])
    properties = {}
    prefix = 'image_'
    for key, value in sys_meta.iteritems():
        if key.startswith(prefix):
            key = key[len(prefix):]
        properties[key] = value
    properties['auto_disk_config'] = instance.auto_disk_config
    properties['os_type'] = instance.os_type or FLAGS.default_os_type

    params = {'vdi_uuids': vdi_uuids,
              'image_id': image_id,
              'glance_host': glance_host,
              'glance_port': glance_port,
              'sr_path': get_sr_path(session),
              'auth_token': getattr(context, 'auth_token', None),
              'properties': properties}

    kwargs = {'params': pickle.dumps(params)}
    session.call_plugin('glance', 'upload_vhd', kwargs)


def resize_disk(session, instance, vdi_ref, instance_type):
    # Copy VDI over to something we can resize
    # NOTE(jerdfelt): Would be nice to just set vdi_ref to read/write
    sr_ref = safe_find_sr(session)
    copy_ref = session.call_xenapi('VDI.copy', vdi_ref, sr_ref)

    try:
        # Resize partition and filesystem down
        auto_configure_disk(session, copy_ref, instance_type['root_gb'])

        # Create new VDI
        vdi_size = instance_type['root_gb'] * 1024 * 1024 * 1024
        new_ref = create_vdi(session, sr_ref, instance, 'root', vdi_size)

        new_uuid = session.call_xenapi('VDI.get_uuid', new_ref)

        # Manually copy contents over
        virtual_size = instance_type['root_gb'] * 1024 * 1024 * 1024
        _copy_partition(session, copy_ref, new_ref, 1, virtual_size)

        return new_ref, new_uuid
    finally:
        destroy_vdi(session, copy_ref)


def auto_configure_disk(session, vdi_ref, new_gb):
    """Partition and resize FS to match the size specified by
    instance_types.root_gb.

    This is a fail-safe to prevent accidentally destroying data on a disk
    erroneously marked as auto_disk_config=True.

    The criteria for allowing resize are:

        1. 'auto_disk_config' must be true for the instance (and image).
           (If we've made it here, then auto_disk_config=True.)

        2. The disk must have only one partition.

        3. The file-system on the one partition must be ext3 or ext4.
    """
    with vdi_attached_here(session, vdi_ref, read_only=False) as dev:
        partitions = _get_partitions(dev)

        if len(partitions) != 1:
            return

        _num, start, old_sectors, ptype = partitions[0]
        if ptype in ('ext3', 'ext4'):
            new_sectors = new_gb * 1024 * 1024 * 1024 / SECTOR_SIZE
            _resize_part_and_fs(dev, start, old_sectors, new_sectors)


def _generate_disk(session, instance, vm_ref, userdevice, name, size_mb,
                   fs_type):
    """
    Steps to programmatically generate a disk:

        1. Create VDI of desired size

        2. Attach VDI to compute worker

        3. Create partition

        4. Create VBD between instance VM and VDI
    """
    # 1. Create VDI
    sr_ref = safe_find_sr(session)
    ONE_MEG = 1024 * 1024
    virtual_size = size_mb * ONE_MEG
    vdi_ref = create_vdi(session, sr_ref, instance, name, virtual_size)

    try:
        # 2. Attach VDI to compute worker (VBD hotplug)
        with vdi_attached_here(session, vdi_ref, read_only=False) as dev:
            # 3. Create partition
            dev_path = utils.make_dev_path(dev)
            utils.execute('parted', '--script', dev_path,
                          'mklabel', 'msdos', run_as_root=True)

            partition_start = 0
            partition_end = size_mb
            utils.execute('parted', '--script', dev_path,
                          'mkpart', 'primary',
                          str(partition_start),
                          str(partition_end),
                          run_as_root=True)

            partition_path = utils.make_dev_path(dev, partition=1)

            if fs_type == 'linux-swap':
                utils.execute('mkswap', partition_path, run_as_root=True)
            elif fs_type is not None:
                utils.execute('mkfs', '-t', fs_type, partition_path,
                              run_as_root=True)

        # 4. Create VBD between instance VM and swap VDI
        create_vbd(session, vm_ref, vdi_ref, userdevice, bootable=False)
    except Exception:
        with excutils.save_and_reraise_exception():
            destroy_vdi(session, vdi_ref)


def generate_swap(session, instance, vm_ref, userdevice, swap_mb):
    # NOTE(jk0): We use a FAT32 filesystem for the Windows swap
    # partition because that is what parted supports.
    is_windows = instance.os_type == "windows"
    fs_type = "vfat" if is_windows else "linux-swap"

    _generate_disk(session, instance, vm_ref, userdevice, 'swap', swap_mb,
                   fs_type)


def generate_ephemeral(session, instance, vm_ref, userdevice, size_gb):
    _generate_disk(session, instance, vm_ref, userdevice, 'ephemeral',
                   size_gb * 1024, FLAGS.default_ephemeral_format)


def create_kernel_image(context, session, instance, image_id, user_id,
                        project_id, image_type):
    """Creates kernel/ramdisk file from the image stored in the cache.
    If the image is not present in the cache, it streams it from glance.

    Returns: A list of dictionaries that describe VDIs
    """
    filename = ""
    if FLAGS.cache_images:
        args = {}
        args['cached-image'] = image_id
        args['new-image-uuid'] = str(uuid.uuid4())
        filename = session.call_plugin(
                'kernel', 'create_kernel_ramdisk', args)

    if filename == "":
        return _fetch_image(context, session, instance, image_id, image_type)
    else:
        vdi_type = ImageType.to_string(image_type)
        return {vdi_type: dict(uuid=None, file=filename)}


def destroy_kernel_ramdisk(session, kernel, ramdisk):
    args = {}
    if kernel:
        args['kernel-file'] = kernel
    if ramdisk:
        args['ramdisk-file'] = ramdisk
    session.call_plugin('kernel', 'remove_kernel_ramdisk', args)


def _create_cached_image(context, session, instance, image_id, image_type):
    sr_ref = safe_find_sr(session)
    sr_type = session.call_xenapi('SR.get_record', sr_ref)["type"]
    vdis = {}

    if FLAGS.use_cow_images and sr_type != "ext":
        LOG.warning(_("Fast cloning is only supported on default local SR "
                      "of type ext. SR on this system was found to be of "
                      "type %(sr_type)s. Ignoring the cow flag.")
                      % locals())

    root_vdi_ref = find_cached_image(session, image_id, sr_ref)
    if root_vdi_ref is None:
        vdis = _fetch_image(context, session, instance, image_id,
                                   image_type)
        root_vdi = vdis['root']
        root_vdi_ref = session.call_xenapi('VDI.get_by_uuid',
                                           root_vdi['uuid'])
        set_vdi_name(session, root_vdi['uuid'], 'Glance Image %s' % image_id,
                     'root', vdi_ref=root_vdi_ref)
        session.call_xenapi('VDI.add_to_other_config',
                            root_vdi_ref, 'image-id', str(image_id))

        for vdi_type, vdi in vdis.iteritems():
            vdi_ref = session.call_xenapi('VDI.get_by_uuid',
                                          vdi['uuid'])

            vdi_rec = session.call_xenapi('VDI.get_record', vdi_ref)
            session.call_xenapi('VDI.add_to_other_config',
                                vdi_ref, 'expected_physical_utilisation',
                                vdi_rec['physical_utilisation'])

            if vdi_type == 'swap':
                session.call_xenapi('VDI.add_to_other_config',
                                    root_vdi_ref, 'swap-disk',
                                    str(vdi['uuid']))

    if FLAGS.use_cow_images and sr_type == 'ext':
        new_vdi_ref = clone_vdi(session, root_vdi_ref)
    else:
        new_vdi_ref = copy_vdi(session, sr_ref, root_vdi_ref)

    # Set the name label for the image we just created and remove image id
    # field from other-config.
    session.call_xenapi('VDI.remove_from_other_config',
                        new_vdi_ref, 'image-id')

    vdi_type = ("root" if image_type == ImageType.DISK_VHD
                else ImageType.to_string(image_type))
    vdi_uuid = session.call_xenapi('VDI.get_uuid', new_vdi_ref)
    vdis[vdi_type] = dict(uuid=vdi_uuid, file=None)

    # Create a swap disk if the glance image had one associated with it.
    vdi_rec = session.call_xenapi('VDI.get_record', root_vdi_ref)
    if 'swap-disk' in vdi_rec['other_config']:
        swap_disk_uuid = vdi_rec['other_config']['swap-disk']
        swap_vdi_ref = session.call_xenapi('VDI.get_by_uuid',
                                           swap_disk_uuid)
        new_swap_vdi_ref = copy_vdi(session, sr_ref, swap_vdi_ref)
        new_swap_vdi_uuid = session.call_xenapi('VDI.get_uuid',
                                                new_swap_vdi_ref)
        vdis['swap'] = dict(uuid=new_swap_vdi_uuid, file=None)

    return vdis


def create_image(context, session, instance, image_id, image_type):
    """Creates VDI from the image stored in the local cache. If the image
    is not present in the cache, it streams it from glance.

    Returns: A list of dictionaries that describe VDIs
    """
    cache_images = FLAGS.cache_images.lower()

    # Deterimine if the image is cacheable
    if image_type == ImageType.DISK_ISO:
        cache = False
    elif cache_images == 'all':
        cache = True
    elif cache_images == 'some':
        # FIXME(sirp): This should be eager loaded like instance metadata
        sys_meta = db.instance_system_metadata_get(context,
                instance['uuid'])
        try:
            cache = utils.bool_from_str(sys_meta['image_cache_in_nova'])
        except KeyError:
            cache = False
    elif cache_images == 'none':
        cache = False
    else:
        LOG.warning(_("Unrecognized cache_images value '%s', defaulting to"
                      " True"), FLAGS.cache_images)
        cache = True

    # Fetch (and cache) the image
    if cache:
        vdis = _create_cached_image(
                context, session, instance, image_id, image_type)
    else:
        vdis = _fetch_image(
                context, session, instance, image_id, image_type)

    # Set the name label and description to easily identify what
    # instance and disk it's for
    for vdi_type, vdi in vdis.iteritems():
        set_vdi_name(session, vdi['uuid'], instance.name, vdi_type)

    return vdis


def _fetch_image(context, session, instance, image_id, image_type):
    """Fetch image from glance based on image type.

    Returns: A single filename if image_type is KERNEL or RAMDISK
             A list of dictionaries that describe VDIs, otherwise
    """
    if image_type == ImageType.DISK_VHD:
        vdis = _fetch_vhd_image(context, session, instance, image_id)
    else:
        vdis = _fetch_disk_image(context, session, instance, image_id,
                                 image_type)

    for vdi_type, vdi in vdis.iteritems():
        vdi_uuid = vdi['uuid']
        LOG.debug(_("Fetched VDIs of type '%(vdi_type)s' with UUID"
                    "  '%(vdi_uuid)s'"),
                  locals(), instance=instance)

    return vdis


def _fetch_using_dom0_plugin_with_retry(context, session, image_id,
                                        plugin_name, params, callback=None):
    max_attempts = FLAGS.glance_num_retries + 1
    sleep_time = 0.5
    for attempt_num in xrange(1, max_attempts + 1):
        LOG.info(_('download_vhd %(image_id)s, '
                   'attempt %(attempt_num)d/%(max_attempts)d, '
                   'params: %(params)s') % locals())

        try:
            if callback:
                callback(params)
            kwargs = {'params': pickle.dumps(params)}
            result = session.call_plugin(plugin_name, 'download_vhd', kwargs)
            return jsonutils.loads(result)
        except session.XenAPI.Failure as exc:
            _type, _method, error = exc.details[:3]
            if error == 'RetryableError':
                LOG.error(_('download_vhd failed: %r') %
                          (exc.details[3:],))
            else:
                raise

        time.sleep(sleep_time)
        sleep_time = min(2 * sleep_time, 15)

    raise exception.CouldNotFetchImage(image_id=image_id)


def _fetch_vhd_image(context, session, instance, image_id):
    """Tell glance to download an image and put the VHDs into the SR

    Returns: A list of dictionaries that describe VDIs
    """
    LOG.debug(_("Asking xapi to fetch vhd image %(image_id)s"), locals(),
              instance=instance)

    # NOTE(sirp): The XenAPI plugins run under Python 2.4
    # which does not have the `uuid` module. To work around this,
    # we generate the uuids here (under Python 2.6+) and
    # pass them as arguments
    params = {'image_id': image_id,
              'uuid_stack': [str(uuid.uuid4()) for i in xrange(3)],
              'sr_path': get_sr_path(session),
              'auth_token': getattr(context, 'auth_token', None)}

    def pick_glance(params):
        glance_host, glance_port = glance.pick_glance_api_server()
        params['glance_host'] = glance_host
        params['glance_port'] = glance_port

    plugin_name = 'glance'
    vdis = _fetch_using_dom0_plugin_with_retry(
            context, session, image_id, plugin_name, params,
            callback=pick_glance)

    sr_ref = safe_find_sr(session)
    scan_sr(session, sr_ref)

    # Pull out the UUID of the root VDI
    root_vdi_uuid = vdis['root']['uuid']

    # Set the name-label to ease debugging
    set_vdi_name(session, root_vdi_uuid, instance.name, 'root')

    _check_vdi_size(context, session, instance, root_vdi_uuid)
    return vdis


def _get_vdi_chain_size(session, vdi_uuid):
    """Compute the total size of a VDI chain, starting with the specified
    VDI UUID.

    This will walk the VDI chain to the root, add the size of each VDI into
    the total.
    """
    size_bytes = 0
    for vdi_rec in walk_vdi_chain(session, vdi_uuid):
        cur_vdi_uuid = vdi_rec['uuid']
        vdi_size_bytes = int(vdi_rec['physical_utilisation'])
        LOG.debug(_('vdi_uuid=%(cur_vdi_uuid)s vdi_size_bytes='
                    '%(vdi_size_bytes)d'), locals())
        size_bytes += vdi_size_bytes
    return size_bytes


def _check_vdi_size(context, session, instance, vdi_uuid):
    size_bytes = _get_vdi_chain_size(session, vdi_uuid)

    # FIXME(jk0): this was copied directly from compute.manager.py, let's
    # refactor this to a common area
    instance_type_id = instance['instance_type_id']
    instance_type = instance_types.get_instance_type(instance_type_id)
    allowed_size_gb = instance_type['root_gb']
    allowed_size_bytes = allowed_size_gb * 1024 * 1024 * 1024

    LOG.debug(_("image_size_bytes=%(size_bytes)d, allowed_size_bytes="
                "%(allowed_size_bytes)d"), locals(), instance=instance)

    if size_bytes > allowed_size_bytes:
        LOG.info(_("Image size %(size_bytes)d exceeded instance_type "
                   "allowed size %(allowed_size_bytes)d"),
                 locals(), instance=instance)
        raise exception.ImageTooLarge()


def _fetch_disk_image(context, session, instance, image_id, image_type):
    """Fetch the image from Glance

    NOTE:
    Unlike _fetch_vhd_image, this method does not use the Glance
    plugin; instead, it streams the disks through domU to the VDI
    directly.

    Returns: A single filename if image_type is KERNEL_RAMDISK
             A list of dictionaries that describe VDIs, otherwise
    """
    # FIXME(sirp): Since the Glance plugin seems to be required for the
    # VHD disk, it may be worth using the plugin for both VHD and RAW and
    # DISK restores
    image_type_str = ImageType.to_string(image_type)
    LOG.debug(_("Fetching image %(image_id)s, type %(image_type_str)s"),
              locals(), instance=instance)

    if image_type == ImageType.DISK_ISO:
        sr_ref = safe_find_iso_sr(session)
    else:
        sr_ref = safe_find_sr(session)

    image_service, image_id = glance.get_remote_image_service(
            context, image_id)
    meta = image_service.show(context, image_id)
    virtual_size = int(meta['size'])
    vdi_size = virtual_size
    LOG.debug(_("Size for image %(image_id)s: %(virtual_size)d"), locals(),
              instance=instance)
    if image_type == ImageType.DISK:
        # Make room for MBR.
        vdi_size += MBR_SIZE_BYTES
    elif (image_type in (ImageType.KERNEL, ImageType.RAMDISK) and
          vdi_size > FLAGS.max_kernel_ramdisk_size):
        max_size = FLAGS.max_kernel_ramdisk_size
        raise exception.NovaException(
            _("Kernel/Ramdisk image is too large: %(vdi_size)d bytes, "
              "max %(max_size)d bytes") % locals())

    vdi_ref = create_vdi(session, sr_ref, instance, image_type_str, vdi_size)
    # From this point we have a VDI on Xen host;
    # If anything goes wrong, we need to remember its uuid.
    try:
        filename = None
        vdi_uuid = session.call_xenapi("VDI.get_uuid", vdi_ref)

        with vdi_attached_here(session, vdi_ref, read_only=False) as dev:
            stream_func = lambda f: image_service.download(
                    context, image_id, f)
            _stream_disk(stream_func, image_type, virtual_size, dev)

        if image_type in (ImageType.KERNEL, ImageType.RAMDISK):
            # We need to invoke a plugin for copying the
            # content of the VDI into the proper path.
            LOG.debug(_("Copying VDI %s to /boot/guest on dom0"),
                      vdi_ref, instance=instance)

            args = {}
            args['vdi-ref'] = vdi_ref

            # Let the plugin copy the correct number of bytes.
            args['image-size'] = str(vdi_size)
            if FLAGS.cache_images:
                args['cached-image'] = image_id
            filename = session.call_plugin('kernel', 'copy_vdi', args)

            # Remove the VDI as it is not needed anymore.
            destroy_vdi(session, vdi_ref)
            LOG.debug(_("Kernel/Ramdisk VDI %s destroyed"), vdi_ref,
                      instance=instance)
            vdi_type = ImageType.to_string(image_type)
            return {vdi_type: dict(uuid=None, file=filename)}
        else:
            vdi_type = ImageType.to_string(image_type)
            return {vdi_type: dict(uuid=vdi_uuid, file=None)}
    except (session.XenAPI.Failure, IOError, OSError) as e:
        # We look for XenAPI and OS failures.
        LOG.exception(_("Failed to fetch glance image"),
                      instance=instance)
        e.args = e.args + ([dict(type=ImageType.to_string(image_type),
                                 uuid=vdi_uuid,
                                 file=filename)],)
        raise e


def determine_disk_image_type(image_meta):
    """Disk Image Types are used to determine where the kernel will reside
    within an image. To figure out which type we're dealing with, we use
    the following rules:

    1. If we're using Glance, we can use the image_type field to
       determine the image_type

    2. If we're not using Glance, then we need to deduce this based on
       whether a kernel_id is specified.
    """
    disk_format = image_meta['disk_format']

    disk_format_map = {
        'ami': 'DISK',
        'aki': 'KERNEL',
        'ari': 'RAMDISK',
        'raw': 'DISK_RAW',
        'vhd': 'DISK_VHD',
        'iso': 'DISK_ISO',
    }

    try:
        image_type_str = disk_format_map[disk_format]
    except KeyError:
        raise exception.InvalidDiskFormat(disk_format=disk_format)

    image_type = getattr(ImageType, image_type_str)

    image_ref = image_meta['id']
    msg = _("Detected %(image_type_str)s format for image %(image_ref)s")
    LOG.debug(msg % locals())

    return image_type


def determine_is_pv(session, vdi_ref, disk_image_type, os_type):
    """
    Determine whether the VM will use a paravirtualized kernel or if it
    will use hardware virtualization.

        1. Glance (VHD): then we use `os_type`, raise if not set

        2. Glance (DISK_RAW): use Pygrub to figure out if pv kernel is
           available

        3. Glance (DISK): pv is assumed

        4. Glance (DISK_ISO): no pv is assumed
    """

    LOG.debug(_("Looking up vdi %s for PV kernel"), vdi_ref)
    if disk_image_type == ImageType.DISK_VHD:
        # 1. VHD
        if os_type == 'windows':
            is_pv = False
        else:
            is_pv = True
    elif disk_image_type == ImageType.DISK_RAW:
        # 2. RAW
        with vdi_attached_here(session, vdi_ref, read_only=True) as dev:
            is_pv = _is_vdi_pv(dev)
    elif disk_image_type == ImageType.DISK:
        # 3. Disk
        is_pv = True
    elif disk_image_type == ImageType.DISK_ISO:
        # 4. ISO
        is_pv = False
    else:
        msg = _("Unknown image format %(disk_image_type)s") % locals()
        raise exception.NovaException(msg)

    return is_pv


def set_vm_name_label(session, vm_ref, name_label):
    session.call_xenapi("VM.set_name_label", vm_ref, name_label)


def list_vms(session):
    for vm_ref, vm_rec in session.get_all_refs_and_recs('VM'):
        if (vm_rec["resident_on"] != session.get_xenapi_host() or
            vm_rec["is_a_template"] or vm_rec["is_control_domain"]):
            continue
        else:
            yield vm_ref, vm_rec


def lookup(session, name_label):
    """Look the instance up and return it if available"""
    vm_refs = session.call_xenapi("VM.get_by_name_label", name_label)
    n = len(vm_refs)
    if n == 0:
        return None
    elif n > 1:
        raise exception.InstanceExists(name=name_label)
    else:
        return vm_refs[0]


def lookup_vm_vdis(session, vm_ref):
    """Look for the VDIs that are attached to the VM"""
    # Firstly we get the VBDs, then the VDIs.
    # TODO(Armando): do we leave the read-only devices?
    vbd_refs = session.call_xenapi("VM.get_VBDs", vm_ref)
    vdi_refs = []
    if vbd_refs:
        for vbd_ref in vbd_refs:
            try:
                vdi_ref = session.call_xenapi("VBD.get_VDI", vbd_ref)
                # Test valid VDI
                record = session.call_xenapi("VDI.get_record", vdi_ref)
                LOG.debug(_('VDI %s is still available'), record['uuid'])
            except session.XenAPI.Failure, exc:
                LOG.exception(exc)
            else:
                vdi_refs.append(vdi_ref)
    return vdi_refs


def preconfigure_instance(session, instance, vdi_ref, network_info):
    """Makes alterations to the image before launching as part of spawn.
    """

    # As mounting the image VDI is expensive, we only want do do it once,
    # if at all, so determine whether it's required first, and then do
    # everything
    mount_required = False
    key, net, metadata = _prepare_injectables(instance, network_info)
    mount_required = key or net or metadata
    if not mount_required:
        return

    with vdi_attached_here(session, vdi_ref, read_only=False) as dev:
        _mounted_processing(dev, key, net, metadata)


def lookup_kernel_ramdisk(session, vm):
    vm_rec = session.call_xenapi("VM.get_record", vm)
    if 'PV_kernel' in vm_rec and 'PV_ramdisk' in vm_rec:
        return (vm_rec['PV_kernel'], vm_rec['PV_ramdisk'])
    else:
        return (None, None)


def is_snapshot(session, vm):
    vm_rec = session.call_xenapi("VM.get_record", vm)
    if 'is_a_template' in vm_rec and 'is_a_snapshot' in vm_rec:
        return vm_rec['is_a_template'] and vm_rec['is_a_snapshot']
    else:
        return False


def compile_info(record):
    """Fill record with VM status information"""
    return {'state': XENAPI_POWER_STATE[record['power_state']],
            'max_mem': long(record['memory_static_max']) >> 10,
            'mem': long(record['memory_dynamic_max']) >> 10,
            'num_cpu': record['VCPUs_max'],
            'cpu_time': 0}


def compile_diagnostics(record):
    """Compile VM diagnostics data"""
    try:
        keys = []
        diags = {}
        vm_uuid = record["uuid"]
        xml = get_rrd(get_rrd_server(), vm_uuid)
        if xml:
            rrd = minidom.parseString(xml)
            for i, node in enumerate(rrd.firstChild.childNodes):
                # Provide the last update of the information
                if node.localName == 'lastupdate':
                    diags['last_update'] = node.firstChild.data

                # Create a list of the diagnostic keys (in their order)
                if node.localName == 'ds':
                    ref = node.childNodes
                    # Name and Value
                    if len(ref) > 6:
                        keys.append(ref[0].firstChild.data)

                # Read the last row of the first RRA to get the latest info
                if node.localName == 'rra':
                    rows = node.childNodes[4].childNodes
                    last_row = rows[rows.length - 1].childNodes
                    for j, value in enumerate(last_row):
                        diags[keys[j]] = value.firstChild.data
                    break

        return diags
    except expat.ExpatError as e:
        LOG.exception(_('Unable to parse rrd of %(vm_uuid)s') % locals())
        return {"Unable to retrieve diagnostics": e}


def compile_metrics(start_time, stop_time=None):
    """Compile bandwidth usage, cpu, and disk metrics for all VMs on
       this host"""
    start_time = int(start_time)

    xml = get_rrd_updates(get_rrd_server(), start_time)
    if xml:
        doc = minidom.parseString(xml)
        return parse_rrd_update(doc, start_time, stop_time)

    raise exception.CouldNotFetchMetrics()


def scan_sr(session, sr_ref=None):
    """Scans the SR specified by sr_ref"""
    if sr_ref:
        LOG.debug(_("Re-scanning SR %s"), sr_ref)
        session.call_xenapi('SR.scan', sr_ref)


def scan_default_sr(session):
    """Looks for the system default SR and triggers a re-scan"""
    scan_sr(session, find_sr(session))


def safe_find_sr(session):
    """Same as find_sr except raises a NotFound exception if SR cannot be
    determined
    """
    sr_ref = find_sr(session)
    if sr_ref is None:
        raise exception.StorageRepositoryNotFound()
    return sr_ref


def find_sr(session):
    """Return the storage repository to hold VM images"""
    host = session.get_xenapi_host()
    try:
        tokens = FLAGS.sr_matching_filter.split(':')
        filter_criteria = tokens[0]
        filter_pattern = tokens[1]
    except IndexError:
        # oops, flag is invalid
        LOG.warning(_("Flag sr_matching_filter '%s' does not respect "
                      "formatting convention"), FLAGS.sr_matching_filter)
        return None

    if filter_criteria == 'other-config':
        key, value = filter_pattern.split('=', 1)
        for sr_ref, sr_rec in session.get_all_refs_and_recs('SR'):
            if not (key in sr_rec['other_config'] and
                    sr_rec['other_config'][key] == value):
                continue
            for pbd_ref in sr_rec['PBDs']:
                pbd_rec = session.get_rec('PBD', pbd_ref)
                if pbd_rec and pbd_rec['host'] == host:
                    return sr_ref
    elif filter_criteria == 'default-sr' and filter_pattern == 'true':
        pool_ref = session.call_xenapi('pool.get_all')[0]
        return session.call_xenapi('pool.get_default_SR', pool_ref)
    # No SR found!
    LOG.warning(_("XenAPI is unable to find a Storage Repository to "
                  "install guest instances on. Please check your "
                  "configuration and/or configure the flag "
                  "'sr_matching_filter'"))
    return None


def safe_find_iso_sr(session):
    """Same as find_iso_sr except raises a NotFound exception if SR
    cannot be determined
    """
    sr_ref = find_iso_sr(session)
    if sr_ref is None:
        raise exception.NotFound(_('Cannot find SR of content-type ISO'))
    return sr_ref


def find_iso_sr(session):
    """Return the storage repository to hold ISO images"""
    host = session.get_xenapi_host()
    for sr_ref, sr_rec in session.get_all_refs_and_recs('SR'):
        LOG.debug(_("ISO: looking at SR %(sr_rec)s") % locals())
        if not sr_rec['content_type'] == 'iso':
            LOG.debug(_("ISO: not iso content"))
            continue
        if not 'i18n-key' in sr_rec['other_config']:
            LOG.debug(_("ISO: iso content_type, no 'i18n-key' key"))
            continue
        if not sr_rec['other_config']['i18n-key'] == 'local-storage-iso':
            LOG.debug(_("ISO: iso content_type, i18n-key value not "
                        "'local-storage-iso'"))
            continue

        LOG.debug(_("ISO: SR MATCHing our criteria"))
        for pbd_ref in sr_rec['PBDs']:
            LOG.debug(_("ISO: ISO, looking to see if it is host local"))
            pbd_rec = session.get_rec('PBD', pbd_ref)
            if not pbd_rec:
                LOG.debug(_("ISO: PBD %(pbd_ref)s disappeared") % locals())
                continue
            pbd_rec_host = pbd_rec['host']
            LOG.debug(_("ISO: PBD matching, want %(pbd_rec)s, "
                        "have %(host)s") % locals())
            if pbd_rec_host == host:
                LOG.debug(_("ISO: SR with local PBD"))
                return sr_ref
    return None


def get_rrd_server():
    """Return server's scheme and address to use for retrieving RRD XMLs."""
    xs_url = urlparse.urlparse(FLAGS.xenapi_connection_url)
    return [xs_url.scheme, xs_url.netloc]


def get_rrd(server, vm_uuid):
    """Return the VM RRD XML as a string"""
    try:
        xml = urllib.urlopen("%s://%s:%s@%s/vm_rrd?uuid=%s" % (
            server[0],
            FLAGS.xenapi_connection_username,
            FLAGS.xenapi_connection_password,
            server[1],
            vm_uuid))
        return xml.read()
    except IOError:
        LOG.exception(_('Unable to obtain RRD XML for VM %(vm_uuid)s with '
                        'server details: %(server)s.') % locals())
        return None


def get_rrd_updates(server, start_time):
    """Return the RRD updates XML as a string"""
    try:
        xml = urllib.urlopen("%s://%s:%s@%s/rrd_updates?start=%s" % (
            server[0],
            FLAGS.xenapi_connection_username,
            FLAGS.xenapi_connection_password,
            server[1],
            start_time))
        return xml.read()
    except IOError:
        LOG.exception(_('Unable to obtain RRD XML updates with '
                        'server details: %(server)s.') % locals())
        return None


def parse_rrd_meta(doc):
    data = {}
    meta = doc.getElementsByTagName('meta')[0]
    for tag in ('start', 'end', 'step'):
        data[tag] = int(meta.getElementsByTagName(tag)[0].firstChild.data)
    legend = meta.getElementsByTagName('legend')[0]
    data['legend'] = [child.firstChild.data for child in legend.childNodes]
    return data


def parse_rrd_data(doc):
    dnode = doc.getElementsByTagName('data')[0]
    return [dict(
            time=int(child.getElementsByTagName('t')[0].firstChild.data),
            values=[decimal.Decimal(valnode.firstChild.data)
                  for valnode in child.getElementsByTagName('v')])
            for child in dnode.childNodes]


def parse_rrd_update(doc, start, until=None):
    sum_data = {}
    meta = parse_rrd_meta(doc)
    data = parse_rrd_data(doc)
    for col, collabel in enumerate(meta['legend']):
        _datatype, _objtype, uuid, name = collabel.split(':')
        vm_data = sum_data.get(uuid, dict())
        if name.startswith('vif'):
            vm_data[name] = integrate_series(data, col, start, until)
        else:
            vm_data[name] = average_series(data, col, until)
        sum_data[uuid] = vm_data
    return sum_data


def average_series(data, col, until=None):
    vals = [row['values'][col] for row in data
            if (not until or (row['time'] <= until)) and
                row['values'][col].is_finite()]
    if vals:
        try:
            return (sum(vals) / len(vals)).quantize(decimal.Decimal('1.0000'))
        except decimal.InvalidOperation:
            # (mdragon) Xenserver occasionally returns odd values in
            # data that will throw an error on averaging (see bug 918490)
            # These are hard to find, since, whatever those values are,
            # Decimal seems to think they are a valid number, sortof.
            # We *think* we've got the the cases covered, but just in
            # case, log and return NaN, so we don't break reporting of
            # other statistics.
            LOG.error(_("Invalid statistics data from Xenserver: %s")
                      % str(vals))
            return decimal.Decimal('NaN')
    else:
        return decimal.Decimal('0.0000')


def integrate_series(data, col, start, until=None):
    total = decimal.Decimal('0.0000')
    prev_time = int(start)
    prev_val = None
    for row in reversed(data):
        if not until or (row['time'] <= until):
            time = row['time']
            val = row['values'][col]
            if val.is_nan():
                val = decimal.Decimal('0.0000')
            if prev_val is None:
                prev_val = val
            if prev_val >= val:
                total += ((val * (time - prev_time)) +
                          (decimal.Decimal('0.5000') * (prev_val - val) *
                          (time - prev_time)))
            else:
                total += ((prev_val * (time - prev_time)) +
                          (decimal.Decimal('0.5000') * (val - prev_val) *
                          (time - prev_time)))
            prev_time = time
            prev_val = val
    return total.quantize(decimal.Decimal('1.0000'))


def _get_all_vdis_in_sr(session, sr_ref):
    for vdi_ref in session.call_xenapi('SR.get_VDIs', sr_ref):
        try:
            vdi_rec = session.call_xenapi('VDI.get_record', vdi_ref)
            yield vdi_ref, vdi_rec
        except session.XenAPI.Failure:
            continue


#TODO(sirp): This code comes from XS5.6 pluginlib.py, we should refactor to
# use that implmenetation
def get_vhd_parent(session, vdi_rec):
    """
    Returns the VHD parent of the given VDI record, as a (ref, rec) pair.
    Returns None if we're at the root of the tree.
    """
    if 'vhd-parent' in vdi_rec['sm_config']:
        parent_uuid = vdi_rec['sm_config']['vhd-parent']
        parent_ref = session.call_xenapi("VDI.get_by_uuid", parent_uuid)
        parent_rec = session.call_xenapi("VDI.get_record", parent_ref)
        vdi_uuid = vdi_rec['uuid']
        LOG.debug(_("VHD %(vdi_uuid)s has parent %(parent_ref)s") % locals())
        return parent_ref, parent_rec
    else:
        return None


def get_vhd_parent_uuid(session, vdi_ref):
    vdi_rec = session.call_xenapi("VDI.get_record", vdi_ref)
    ret = get_vhd_parent(session, vdi_rec)
    if ret:
        _parent_ref, parent_rec = ret
        return parent_rec["uuid"]
    else:
        return None


def walk_vdi_chain(session, vdi_uuid):
    """Yield vdi_recs for each element in a VDI chain"""
    # TODO(jk0): perhaps make get_vhd_parent use this
    while True:
        vdi_ref = session.call_xenapi("VDI.get_by_uuid", vdi_uuid)
        vdi_rec = session.call_xenapi("VDI.get_record", vdi_ref)
        yield vdi_rec

        parent_uuid = vdi_rec['sm_config'].get('vhd-parent')
        if parent_uuid:
            vdi_uuid = parent_uuid
        else:
            break


def _wait_for_vhd_coalesce(session, instance, sr_ref, vdi_ref,
                           original_parent_uuid):
    """Spin until the parent VHD is coalesced into its parent VHD

    Before coalesce:
        * original_parent_vhd
            * parent_vhd
                snapshot

    After coalesce:
        * parent_vhd
            snapshot
    """
    def _another_child_vhd():
        if not original_parent_uuid:
            return False

        # Search for any other vdi which parents to original parent and is not
        # in the active vm/instance vdi chain.
        vdi_uuid = session.call_xenapi('VDI.get_record', vdi_ref)['uuid']
        parent_vdi_uuid = get_vhd_parent_uuid(session, vdi_ref)
        for _ref, rec in _get_all_vdis_in_sr(session, sr_ref):
            if ((rec['uuid'] != vdi_uuid) and
               (rec['uuid'] != parent_vdi_uuid) and
               (rec['sm_config'].get('vhd-parent') == original_parent_uuid)):
                # Found another vhd which too parents to original parent.
                return True
        # Found no other vdi with the same parent.
        return False

    # Check if original parent has any other child. If so, coalesce will
    # not take place.
    if _another_child_vhd():
        parent_uuid = get_vhd_parent_uuid(session, vdi_ref)
        parent_ref = session.call_xenapi("VDI.get_by_uuid", parent_uuid)
        base_uuid = get_vhd_parent_uuid(session, parent_ref)
        return parent_uuid, base_uuid

    max_attempts = FLAGS.xenapi_vhd_coalesce_max_attempts
    for i in xrange(max_attempts):
        scan_sr(session, sr_ref)
        parent_uuid = get_vhd_parent_uuid(session, vdi_ref)
        if original_parent_uuid and (parent_uuid != original_parent_uuid):
            LOG.debug(_("Parent %(parent_uuid)s doesn't match original parent"
                        " %(original_parent_uuid)s, waiting for coalesce..."),
                      locals(), instance=instance)
        else:
            parent_ref = session.call_xenapi("VDI.get_by_uuid", parent_uuid)
            base_uuid = get_vhd_parent_uuid(session, parent_ref)
            return parent_uuid, base_uuid

        greenthread.sleep(FLAGS.xenapi_vhd_coalesce_poll_interval)

    msg = (_("VHD coalesce attempts exceeded (%(max_attempts)d)"
             ", giving up...") % locals())
    raise exception.NovaException(msg)


def remap_vbd_dev(dev):
    """Return the appropriate location for a plugged-in VBD device

    Ubuntu Maverick moved xvd? -> sd?. This is considered a bug and will be
    fixed in future versions:
        https://bugs.launchpad.net/ubuntu/+source/linux/+bug/684875

    For now, we work around it by just doing a string replace.
    """
    # NOTE(sirp): This hack can go away when we pull support for Maverick
    should_remap = FLAGS.xenapi_remap_vbd_dev
    if not should_remap:
        return dev

    old_prefix = 'xvd'
    new_prefix = FLAGS.xenapi_remap_vbd_dev_prefix
    remapped_dev = dev.replace(old_prefix, new_prefix)

    return remapped_dev


def _wait_for_device(dev):
    """Wait for device node to appear"""
    for i in xrange(0, FLAGS.block_device_creation_timeout):
        dev_path = utils.make_dev_path(dev)
        if os.path.exists(dev_path):
            return
        time.sleep(1)

    raise volume_utils.StorageError(
        _('Timeout waiting for device %s to be created') % dev)


def cleanup_attached_vdis(session):
    """Unplug any instance VDIs left after an unclean restart"""
    this_vm_ref = get_this_vm_ref(session)

    vbd_refs = session.call_xenapi('VM.get_VBDs', this_vm_ref)
    for vbd_ref in vbd_refs:
        try:
            vbd_rec = session.call_xenapi('VBD.get_record', vbd_ref)
            vdi_rec = session.call_xenapi('VDI.get_record', vbd_rec['VDI'])
        except session.XenAPI.Failure, e:
            if e.details[0] != 'HANDLE_INVALID':
                raise
            continue

        if 'nova_instance_uuid' in vdi_rec['other_config']:
            # Belongs to an instance and probably left over after an
            # unclean restart
            LOG.info(_('Disconnecting stale VDI %s from compute domU'),
                     vdi_rec['uuid'])
            unplug_vbd(session, vbd_ref)
            destroy_vbd(session, vbd_ref)


@contextlib.contextmanager
def vdi_attached_here(session, vdi_ref, read_only=False):
    this_vm_ref = get_this_vm_ref(session)

    vbd_ref = create_vbd(session, this_vm_ref, vdi_ref, 'autodetect',
                         read_only=read_only, bootable=False)
    try:
        LOG.debug(_('Plugging VBD %s ... '), vbd_ref)
        session.call_xenapi("VBD.plug", vbd_ref)
        try:
            LOG.debug(_('Plugging VBD %s done.'), vbd_ref)
            orig_dev = session.call_xenapi("VBD.get_device", vbd_ref)
            LOG.debug(_('VBD %(vbd_ref)s plugged as %(orig_dev)s') % locals())
            dev = remap_vbd_dev(orig_dev)
            if dev != orig_dev:
                LOG.debug(_('VBD %(vbd_ref)s plugged into wrong dev, '
                            'remapping to %(dev)s') % locals())
            _wait_for_device(dev)
            yield dev
        finally:
            LOG.debug(_('Destroying VBD for VDI %s ... '), vdi_ref)
            unplug_vbd(session, vbd_ref)
    finally:
        try:
            destroy_vbd(session, vbd_ref)
        except volume_utils.StorageError:
            # destroy_vbd() will log error
            pass
        LOG.debug(_('Destroying VBD for VDI %s done.'), vdi_ref)


def get_this_vm_uuid():
    with file('/sys/hypervisor/uuid') as f:
        return f.readline().strip()


def get_this_vm_ref(session):
    return session.call_xenapi("VM.get_by_uuid", get_this_vm_uuid())


def _is_vdi_pv(dev):
    LOG.debug(_("Running pygrub against %s"), dev)
    dev_path = utils.make_dev_path(dev)
    output = os.popen('pygrub -qn %s' % dev_path)
    for line in output.readlines():
        #try to find kernel string
        m = re.search('(?<=kernel:)/.*(?:>)', line)
        if m and m.group(0).find('xen') != -1:
            LOG.debug(_("Found Xen kernel %s") % m.group(0))
            return True
    LOG.debug(_("No Xen kernel found.  Booting HVM."))
    return False


def _get_partitions(dev):
    """Return partition information (num, size, type) for a device."""
    dev_path = utils.make_dev_path(dev)
    out, _err = utils.execute('parted', '--script', '--machine',
                             dev_path, 'unit s', 'print',
                             run_as_root=True)
    lines = [line for line in out.split('\n') if line]
    partitions = []

    LOG.debug(_("Partitions:"))
    for line in lines[2:]:
        num, start, end, size, ptype = line.split(':')[:5]
        start = int(start.rstrip('s'))
        end = int(end.rstrip('s'))
        size = int(size.rstrip('s'))
        LOG.debug(_("  %(num)s: %(ptype)s %(size)d sectors") % locals())
        partitions.append((num, start, size, ptype))

    return partitions


def _stream_disk(image_service_func, image_type, virtual_size, dev):
    offset = 0
    if image_type == ImageType.DISK:
        offset = MBR_SIZE_BYTES
        _write_partition(virtual_size, dev)

    dev_path = utils.make_dev_path(dev)

    with utils.temporary_chown(dev_path):
        with open(dev_path, 'wb') as f:
            f.seek(offset)
            image_service_func(f)


def _write_partition(virtual_size, dev):
    dev_path = utils.make_dev_path(dev)
    primary_first = MBR_SIZE_SECTORS
    primary_last = MBR_SIZE_SECTORS + (virtual_size / SECTOR_SIZE) - 1

    LOG.debug(_('Writing partition table %(primary_first)d %(primary_last)d'
                ' to %(dev_path)s...'), locals())

    def execute(*cmd, **kwargs):
        return utils.execute(*cmd, **kwargs)

    execute('parted', '--script', dev_path, 'mklabel', 'msdos',
            run_as_root=True)
    execute('parted', '--script', dev_path, 'mkpart', 'primary',
            '%ds' % primary_first,
            '%ds' % primary_last,
            run_as_root=True)

    LOG.debug(_('Writing partition table %s done.'), dev_path)


def _resize_part_and_fs(dev, start, old_sectors, new_sectors):
    """Resize partition and fileystem.

    This assumes we are dealing with a single primary partition and using
    ext3 or ext4.
    """
    size = new_sectors - start
    end = new_sectors - 1

    dev_path = utils.make_dev_path(dev)
    partition_path = utils.make_dev_path(dev, partition=1)

    # Replay journal if FS wasn't cleanly unmounted
    # Exit Code 1 = File system errors corrected
    #           2 = File system errors corrected, system needs a reboot
    utils.execute('e2fsck', '-f', '-y', partition_path, run_as_root=True,
                  check_exit_code=[0, 1, 2])

    # Remove ext3 journal (making it ext2)
    utils.execute('tune2fs', '-O ^has_journal', partition_path,
                  run_as_root=True)

    if new_sectors < old_sectors:
        # Resizing down, resize filesystem before partition resize
        utils.execute('resize2fs', partition_path, '%ds' % size,
                      run_as_root=True)

    utils.execute('parted', '--script', dev_path, 'rm', '1',
                  run_as_root=True)
    utils.execute('parted', '--script', dev_path, 'mkpart',
                  'primary',
                  '%ds' % start,
                  '%ds' % end,
                  run_as_root=True)

    if new_sectors > old_sectors:
        # Resizing up, resize filesystem after partition resize
        utils.execute('resize2fs', partition_path, run_as_root=True)

    # Add back journal
    utils.execute('tune2fs', '-j', partition_path, run_as_root=True)


def _sparse_copy(src_path, dst_path, virtual_size, block_size=4096):
    """Copy data, skipping long runs of zeros to create a sparse file."""
    start_time = time.time()
    EMPTY_BLOCK = '\0' * block_size
    bytes_read = 0
    skipped_bytes = 0
    left = virtual_size

    LOG.debug(_("Starting sparse_copy src=%(src_path)s dst=%(dst_path)s "
                "virtual_size=%(virtual_size)d block_size=%(block_size)d"),
              locals())

    # NOTE(sirp): we need read/write access to the devices; since we don't have
    # the luxury of shelling out to a sudo'd command, we temporarily take
    # ownership of the devices.
    with utils.temporary_chown(src_path):
        with utils.temporary_chown(dst_path):
            with open(src_path, "r") as src:
                with open(dst_path, "w") as dst:
                    data = src.read(min(block_size, left))
                    while data:
                        if data == EMPTY_BLOCK:
                            dst.seek(block_size, os.SEEK_CUR)
                            left -= block_size
                            bytes_read += block_size
                            skipped_bytes += block_size
                        else:
                            dst.write(data)
                            data_len = len(data)
                            left -= data_len
                            bytes_read += data_len

                        if left <= 0:
                            break

                        data = src.read(min(block_size, left))

    duration = time.time() - start_time
    compression_pct = float(skipped_bytes) / bytes_read * 100

    LOG.debug(_("Finished sparse_copy in %(duration).2f secs, "
                "%(compression_pct).2f%% reduction in size"), locals())


def _copy_partition(session, src_ref, dst_ref, partition, virtual_size):
    # Part of disk taken up by MBR
    virtual_size -= MBR_SIZE_BYTES

    with vdi_attached_here(session, src_ref, read_only=True) as src:
        src_path = utils.make_dev_path(src, partition=partition)

        with vdi_attached_here(session, dst_ref, read_only=False) as dst:
            dst_path = utils.make_dev_path(dst, partition=partition)

            _write_partition(virtual_size, dst)

            if FLAGS.xenapi_sparse_copy:
                _sparse_copy(src_path, dst_path, virtual_size)
            else:
                num_blocks = virtual_size / SECTOR_SIZE
                utils.execute('dd',
                              'if=%s' % src_path,
                              'of=%s' % dst_path,
                              'count=%d' % num_blocks,
                              run_as_root=True)


def _mount_filesystem(dev_path, dir):
    """mounts the device specified by dev_path in dir"""
    try:
        _out, err = utils.execute('mount',
                                 '-t', 'ext2,ext3,ext4,reiserfs',
                                 dev_path, dir, run_as_root=True)
    except exception.ProcessExecutionError as e:
        err = str(e)
    return err


def _find_guest_agent(base_dir, agent_rel_path):
    """
    tries to locate a guest agent at the path
    specificed by agent_rel_path
    """
    agent_path = os.path.join(base_dir, agent_rel_path)
    if os.path.isfile(agent_path):
        # The presence of the guest agent
        # file indicates that this instance can
        # reconfigure the network from xenstore data,
        # so manipulation of files in /etc is not
        # required
        LOG.info(_('XenServer tools installed in this '
                   'image are capable of network injection.  '
                   'Networking files will not be'
                   'manipulated'))
        return True
    xe_daemon_filename = os.path.join(base_dir,
        'usr', 'sbin', 'xe-daemon')
    if os.path.isfile(xe_daemon_filename):
        LOG.info(_('XenServer tools are present '
                   'in this image but are not capable '
                   'of network injection'))
    else:
        LOG.info(_('XenServer tools are not '
                   'installed in this image'))
    return False


def _mounted_processing(device, key, net, metadata):
    """Callback which runs with the image VDI attached"""
    # NB: Partition 1 hardcoded
    dev_path = utils.make_dev_path(device, partition=1)
    with utils.tempdir() as tmpdir:
        # Mount only Linux filesystems, to avoid disturbing NTFS images
        err = _mount_filesystem(dev_path, tmpdir)
        if not err:
            try:
                # This try block ensures that the umount occurs
                if not _find_guest_agent(tmpdir, FLAGS.xenapi_agent_path):
                    LOG.info(_('Manipulating interface files directly'))
                    # for xenapi, we don't 'inject' admin_password here,
                    # it's handled at instance startup time
                    disk.inject_data_into_fs(tmpdir,
                                             key, net, None, metadata,
                                             utils.execute)
            finally:
                utils.execute('umount', dev_path, run_as_root=True)
        else:
            LOG.info(_('Failed to mount filesystem (expected for '
                       'non-linux instances): %s') % err)


def _prepare_injectables(inst, network_info):
    """
    prepares the ssh key and the network configuration file to be
    injected into the disk image
    """
    #do the import here - Cheetah.Template will be loaded
    #only if injection is performed
    from Cheetah import Template as t
    template = t.Template
    template_data = open(FLAGS.injected_network_template).read()

    metadata = inst['metadata']
    key = str(inst['key_data'])
    net = None
    if network_info:
        ifc_num = -1
        interfaces_info = []
        for vif in network_info:
            ifc_num += 1
            try:
                if not vif['network'].get_meta('injected'):
                    # network is not specified injected
                    continue
            except KeyError:
                # vif network is None
                continue

            # NOTE(tr3buchet): using all subnets in case dns is stored in a
            #                  subnet that isn't chosen as first v4 or v6
            #                  subnet in the case where there is more than one
            # dns = list of address of each dns entry from each vif subnet
            dns = [ip['address'] for subnet in vif['network']['subnets']
                                 for ip in subnet['dns']]
            dns = ' '.join(dns).strip()

            interface_info = {'name': 'eth%d' % ifc_num,
                              'address': '',
                              'netmask': '',
                              'gateway': '',
                              'broadcast': '',
                              'dns': dns or '',
                              'address_v6': '',
                              'netmask_v6': '',
                              'gateway_v6': '',
                              'use_ipv6': FLAGS.use_ipv6}

            # NOTE(tr3buchet): the original code used the old network_info
            #                  which only supported a single ipv4 subnet
            #                  (and optionally, a single ipv6 subnet).
            #                  I modified it to use the new network info model,
            #                  which adds support for multiple v4 or v6
            #                  subnets. I chose to ignore any additional
            #                  subnets, just as the original code ignored
            #                  additional IP information

            # populate v4 info if v4 subnet and ip exist
            try:
                # grab the first v4 subnet (or it raises)
                subnet = [s for s in vif['network']['subnets']
                            if s['version'] == 4][0]
                # get the subnet's first ip (or it raises)
                ip = subnet['ips'][0]

                # populate interface_info
                subnet_netaddr = subnet.as_netaddr()
                interface_info['address'] = ip['address']
                interface_info['netmask'] = subnet_netaddr.netmask
                interface_info['gateway'] = subnet['gateway']['address']
                interface_info['broadcast'] = subnet_netaddr.broadcast
            except IndexError:
                # there isn't a v4 subnet or there are no ips
                pass

            # populate v6 info if v6 subnet and ip exist
            try:
                # grab the first v6 subnet (or it raises)
                subnet = [s for s in vif['network']['subnets']
                            if s['version'] == 6][0]
                # get the subnet's first ip (or it raises)
                ip = subnet['ips'][0]

                # populate interface_info
                interface_info['address_v6'] = ip['address']
                interface_info['netmask_v6'] = subnet.as_netaddr().netmask
                interface_info['gateway_v6'] = subnet['gateway']['address']
            except IndexError:
                # there isn't a v6 subnet or there are no ips
                pass

            interfaces_info.append(interface_info)

        if interfaces_info:
            net = str(template(template_data,
                                searchList=[{'interfaces': interfaces_info,
                                            'use_ipv6': FLAGS.use_ipv6}]))
    return key, net, metadata


def ensure_correct_host(session):
    """Ensure we're connected to the host we're running on. This is the
    required configuration for anything that uses vdi_attached_here."""
    this_vm_uuid = get_this_vm_uuid()

    try:
        session.call_xenapi('VM.get_by_uuid', this_vm_uuid)
    except session.XenAPI.Failure as exc:
        if exc.details[0] != 'UUID_INVALID':
            raise
        raise Exception(_('This domU must be running on the host '
                          'specified by xenapi_connection_url'))
