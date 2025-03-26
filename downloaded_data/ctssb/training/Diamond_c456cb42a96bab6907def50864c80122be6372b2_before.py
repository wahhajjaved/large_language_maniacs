# coding=utf-8

"""
Uses /proc/mounts and os.statvfs() to get disk space usage

#### Dependencies

 * /proc/mounts

#### Examples

    # no exclude filters at all
    exclude_filters =,

    # exclude everything that begins /boot or /mnt
    exclude_filters = ^/boot, ^/mnt

    # exclude everything that includes the letter 'm'
    exclude_filters = m,

"""

import diamond.collector
import diamond.convertor
import os
import re

try:
    import psutil
    psutil  # workaround for pyflakes issue #13
except ImportError:
    psutil = None


class DiskSpaceCollector(diamond.collector.Collector):

    def get_default_config_help(self):
        config_help = super(DiskSpaceCollector, self).get_default_config_help()
        config_help.update({
            'filesystems': "filesystems to examine",
            'exclude_filters': "A list of regex patterns. Any filesystem"
            + " matching any of these patterns will be excluded from disk"
            + " space metrics collection",
        })
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(DiskSpaceCollector, self).get_default_config()
        config.update({
            # Enabled by default
            'enabled': 'True',
            'path': 'diskspace',
            # filesystems to examine
            'filesystems': 'ext2, ext3, ext4, xfs, glusterfs, nfs, ntfs, hfs,'
            + ' fat32, fat16',

            # exclude_filters
            #   A list of regex patterns
            #   A filesystem matching any of these patterns will be excluded
            #   from disk space metrics collection.
            #
            # Examples:
            #       exclude_filters =,
            # no exclude filters at all
            #       exclude_filters = ^/boot, ^/mnt
            # exclude everything that begins /boot or /mnt
            #       exclude_filters = m,
            # exclude everything that includes the letter "m"
            'exclude_filters': '^/export/home',

            # We don't use any derivative data to calculate this value
            # Thus we can use a threaded model
            'method': 'Threaded',

            # Default numeric output
            'byte_unit': ['byte']
        })
        return config

    def get_disk_labels(self):
        """
        Creates a mapping of device nodes to filesystem labels
        """
        path = '/dev/disk/by-label/'
        labels = {}
        if not os.path.isdir(path):
            return labels

        for label in os.listdir(path):
            device = os.path.realpath(path + '/' + label)
            labels[device] = label

        return labels

    def get_file_systems(self):
        """
        Creates a map of mounted filesystems on the machine.

        iostat(1): Each sector has size of 512 bytes.

        Returns:
          (major, minor) -> FileSystem(device, mount_point)
        """
        result = {}
        if os.access('/proc/mounts', os.R_OK):
            file = open('/proc/mounts')
            for line in file:
                try:
                    mount = line.split()
                    device = mount[0]
                    mount_point = mount[1]
                    fs_type = mount[2]
                except (IndexError, ValueError):
                    continue

                if (mount_point.startswith('/dev')
                    or mount_point.startswith('/proc')
                        or mount_point.startswith('/sys')):
                    continue

                if device.startswith('/') and mount_point.startswith('/'):
                    stat = os.stat(mount_point)
                    major = os.major(stat.st_dev)
                    minor = os.minor(stat.st_dev)

                    if (major, minor) in result:
                        continue

                    result[(major, minor)] = {
                        'device': device,
                        'mount_point': mount_point,
                        'fs_type': fs_type
                    }

            file.close()

        elif psutil:
            partitions = psutil.disk_partitions(False)
            for partition in partitions:
                result[(0, len(result))] = {
                    'device': partition.device,
                    'mount_point': partition.mountpoint,
                    'fs_type': partition.fstype
                }
            pass

        return result

    def collect(self):
        exclude_reg = re.compile(self.config['exclude_filters'])

        filesystems = []
        for filesystem in self.config['filesystems'].split(','):
            filesystems.append(filesystem.strip())

        labels = self.get_disk_labels()
        for key, info in self.get_file_systems().iteritems():
        # Skip the filesystem if it is not in the list of valid filesystems
            if info['fs_type'] not in filesystems:
                continue

        # Process the filters
            if exclude_reg.match(info['mount_point']):
                continue

            if info['device'] in labels:
                name = labels[info['device']]
            else:
                name = info['mount_point'].replace('/', '_')
                name = name.replace('.', '_')
                if name == '_':
                    name = 'root'

            data = os.statvfs(info['mount_point'])
            block_size = data.f_bsize

            blocks_total = data.f_blocks
            blocks_free = data.f_bfree
            blocks_avail = data.f_bavail
            inodes_total = data.f_files
            inodes_free = data.f_ffree
            inodes_avail = data.f_favail

            for unit in self.config['byte_unit']:

                metric_name = '%s.%s_used' % (name, unit)
                metric_value = float(block_size) * float(
                    blocks_total - blocks_free)
                metric_value = diamond.convertor.binary.convert(
                    value=metric_value, oldUnit='byte', newUnit=unit)
                self.publish(metric_name, metric_value, 2, 'GAUGE')

                metric_name = '%s.%s_free' % (name, unit)
                metric_value = float(block_size) * float(blocks_free)
                metric_value = diamond.convertor.binary.convert(
                    value=metric_value, oldUnit='byte', newUnit=unit)
                self.publish(metric_name, metric_value, 2, 'GAUGE')

                metric_name = '%s.%s_avail' % (name, unit)
                metric_value = float(block_size) * float(blocks_avail)
                metric_value = diamond.convertor.binary.convert(
                    value=metric_value, oldUnit='byte', newUnit=unit)
                self.publish(metric_name, metric_value, 2, 'GAUGE')

            self.publish('%s.inodes_used' % name, inodes_total - inodes_free,
                         metric_type='GAUGE')
            self.publish('%s.inodes_free' % name, inodes_free,
                         metric_type='GAUGE')
            self.publish('%s.inodes_avail' % name, inodes_avail,
                         metric_type='GAUGE')
