# Copyright (C) 2011  Codethink Limited
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import json
import logging
import os
import shutil
import StringIO
import tarfile
import urlparse

import morphlib


class BinaryBlob(object):

    def __init__(self, morph, repo, ref):
        self.morph = morph
        self.repo = repo
        self.ref = ref
        
        # The following MUST get set by the caller.
        self.builddir = None
        self.destdir = None
        self.staging = None
        self.settings = None
        self.msg = None
        self.cache_prefix = None
        self.tempdir = None
        self.built = None

    def dict_key(self):
        return {}
    
    def needs_built(self):
        return []

    def builds(self):
        raise NotImplemented()
    
    def build(self):
        raise NotImplemented()

    def filename(self, name):
        return '%s.%s.%s' % (self.cache_prefix, self.morph.kind, name)

    def prepare_binary_metadata(self, blob_name, **kwargs):
        '''Add metadata to a binary about to be built.'''

        self.msg('Adding metadata to %s' % blob_name)
        meta = {
            'name': blob_name,
            'kind': self.morph.kind,
            'description': self.morph.description,
        }
        for key, value in kwargs.iteritems():
            meta[key] = value
        
        dirname = os.path.join(self.destdir, 'baserock')
        filename = os.path.join(dirname, '%s.meta' % blob_name)
        if not os.path.exists(dirname):
            os.mkdir(dirname)
        with open(filename, 'w') as f:
            json.dump(meta, f, indent=4)
            f.write('\n')


class Chunk(BinaryBlob):

    build_system = {
        'autotools': {
            'configure-commands': [
                'if [ -e autogen.sh ]; then ./autogen.sh; fi',
                './configure --prefix=/usr',
            ],
            'build-commands': [
                'make',
            ],
            'test-commands': [
            ],
            'install-commands': [
                'make DESTDIR="$DESTDIR" install',
            ],
        },
    }

    @property
    def chunks(self):
        if self.morph.chunks:
            return self.morph.chunks
        else:
            return { self.morph.name: ['.'] }
    
    def builds(self):
        ret = {}
        for chunk_name in self.chunks:
            ret[chunk_name] = self.filename(chunk_name)
        return ret

    def build(self):
        logging.debug('Creating build tree at %s' % self.builddir)

        self.ex = morphlib.execute.Execute(self.builddir, self.msg)
        self.setup_env()

        self.create_source_and_tarball()

        os.mkdir(self.destdir)
        if self.morph.build_system:
            self.build_using_buildsystem()
        else:
            self.build_using_commands()

        return self.create_chunks(self.chunks)
            
    def setup_env(self):
        path = self.ex.env['PATH']
        self.ex.env.clear()
        
        self.ex.env['TERM'] = 'dumb'
        self.ex.env['SHELL'] = '/bin/sh'
        self.ex.env['USER'] = \
            self.ex.env['USERNAME'] = \
            self.ex.env['LOGNAME'] = 'tomjon'
        self.ex.env['LC_ALL'] = 'C'
        self.ex.env['HOME'] = os.path.join(self.tempdir.dirname)

        if self.settings['keep-path']:
            self.ex.env['PATH'] = path
        else:
            bindirs = ['tools/bin', 'bin', 'usr/bin']
            path = ':'.join(os.path.join(self.tempdir.dirname, x) 
                                         for x in bindirs)
            self.ex.env['PATH'] = path

        self.ex.env['WORKAREA'] = self.tempdir.dirname
        self.ex.env['DESTDIR'] = self.destdir + '/'
        self.ex.env['TOOLCHAIN_TARGET'] = \
            '%s-baserock-linux-gnu' % os.uname()[4]

        if self.morph.max_jobs:
            max_jobs = int(self.morph.max_jobs)
        elif self.settings['max-jobs']:
            max_jobs = self.settings['max-jobs']
        else:
            max_jobs = morphlib.util.make_concurrency()
        self.ex.env['MAKEFLAGS'] = '-j%d' % max_jobs

        if not self.settings['no-ccache']:
            self.ex.env['PATH'] = ('/usr/lib/ccache:%s' % 
                                    self.ex.env['PATH'])
            self.ex.env['CCACHE_BASEDIR'] = self.tempdir.dirname

    def create_source_and_tarball(self):
        self.msg('Creating source tree and tarball')
        tarball = self.cache_prefix + '.src.tar.gz'
        morphlib.git.export_sources(self.repo, self.ref, tarball)
        os.mkdir(self.builddir)
        f = tarfile.open(tarball)
        f.extractall(path=self.builddir)
        f.close()

    def build_using_buildsystem(self):
        bs_name = self.morph.build_system
        self.msg('Building using well-known build system %s' % bs_name)
        bs = self.build_system[bs_name]
        self.run_some_commands('configure', bs['configure-commands'])
        self.run_some_commands('build', bs['build-commands'])
        self.run_some_commands('test', bs['test-commands'])
        self.run_install_commands(bs['install-commands'])

    def build_using_commands(self):
        self.msg('Building using explicit commands')
        self.run_some_commands('configure', self.morph.configure_commands)
        self.run_some_commands('build', self.morph.build_commands)
        self.run_some_commands('test', self.morph.test_commands)
        self.run_install_commands(self.morph.install_commands)

    def run_some_commands(self, what, commands):
        self.msg('commands: %s' % what)
        self.ex.run(commands)

    def run_install_commands(self, commands):
        self.msg ('commands: install')
        flags = self.ex.env['MAKEFLAGS']
        self.ex.env['MAKEFLAGS'] = '-j1'
        self.ex.run(commands, as_fakeroot=True)
        self.ex.env['MAKEFLAGS'] = flags

    def create_chunks(self, chunks):
        ret = {}
        for chunk_name in chunks:
            self.msg('Creating chunk %s' % chunk_name)
            self.prepare_binary_metadata(chunk_name)
            patterns = chunks[chunk_name]
            patterns += [r'baserock/%s\.' % chunk_name]
            filename = self.filename(chunk_name)
            self.msg('Creating binary for %s' % chunk_name)
            morphlib.bins.create_chunk(self.destdir, filename, patterns)
            ret[chunk_name] = filename
        files = os.listdir(self.destdir)
        if files:
            raise Exception('DESTDIR %s is not empty: %s' %
                                (self.destdir, files))
        return ret


class Stratum(BinaryBlob):
    
    def needs_built(self):
        for source in self.morph.sources:
            project_name = source['name']
            morph_name = source['morph'] if 'morph' in source else project_name
            repo = source['repo']
            ref = source['ref']
            chunks = source['chunks'] if 'chunks' in source else [project_name]
            yield repo, ref, morph_name, chunks

    def builds(self):
        filename = self.filename(self.morph.name)
        return { self.morph.name: filename }

    def build(self):
        os.mkdir(self.destdir)
        for chunk_name, filename in self.built:
            self.msg('Unpacking chunk %s' % chunk_name)
            morphlib.bins.unpack_binary(filename, self.destdir)
        self.prepare_binary_metadata(self.morph.name)
        self.msg('Creating binary for %s' % self.morph.name)
        filename = self.filename(self.morph.name)
        morphlib.bins.create_stratum(self.destdir, filename)
        return { self.morph.name: filename }


class System(BinaryBlob):

    def needs_built(self):
        for stratum_name in self.morph.strata:
            yield self.repo, self.ref, stratum_name, [stratum_name]

    def builds(self):
        filename = self.filename(self.morph.name)
        return { self.morph.name: filename }

    def build(self):
        self.ex = morphlib.execute.Execute(self.tempdir.dirname, self.msg)
        
        # Create image.
        image_name = self.tempdir.join('%s.img' % self.morph.name)
        self.ex.runv(['qemu-img', 'create', '-f', 'raw', image_name,
                      self.morph.disk_size])

        # Partition it.
        self.ex.runv(['parted', '-s', image_name, 'mklabel', 'msdos'],
                     as_root=True)
        self.ex.runv(['parted', '-s', image_name, 'mkpart', 'primary', 
                      '0%', '100%'], as_root=True)
        self.ex.runv(['parted', '-s', image_name, 'set', '1', 'boot', 'on'],
                     as_root=True)

        # Install first stage boot loader into MBR.
        self.ex.runv(['install-mbr', image_name], as_root=True)

        # Setup device mapper to access the partition.
        out = self.ex.runv(['kpartx', '-av', image_name], as_root=True)
        devices = [line.split()[2]
                   for line in out.splitlines()
                   if line.startswith('add map ')]
        partition = '/dev/mapper/%s' % devices[0]

        mount_point = None
        try:
            # Create filesystem.
            self.ex.runv(['mkfs', '-t', 'ext3', partition], as_root=True)
            
            # Mount it.
            mount_point = self.tempdir.join('mnt')
            os.mkdir(mount_point)
            self.ex.runv(['mount', partition, mount_point], as_root=True)

            # Unpack all strata into filesystem.
            for name, filename in self.built:
                self.msg('unpack %s from %s' % (name, filename))
                self.ex.runv(['tar', '-C', mount_point, '-xf', filename],
                             as_root=True)

            # Create fstab.
            fstab = self.tempdir.join('mnt/etc/fstab')
            with open(fstab, 'w') as f:
                f.write('proc /proc proc defaults 0 0\n')
                f.write('sysfs /sys sysfs defaults 0 0\n')
                f.write('/dev/sda1 / ext4 errors=remount-ro 0 1\n')

            # Install extlinux bootloader.
            conf = os.path.join(mount_point, 'extlinux.conf')
            logging.debug('configure extlinux %s' % conf)
            f = open(conf, 'w')
            f.write('''
default linux
timeout 1

label linux
kernel /vmlinuz
append root=/dev/sda1 init=/bin/sh quiet rw
''')
            f.close()

            self.ex.runv(['extlinux', '--install', mount_point], as_root=True)
            
            # Weird hack that makes extlinux work. There is a bug somewhere.
            self.ex.runv(['sync'])
            import time; time.sleep(2)

            # Unmount.
            self.ex.runv(['umount', mount_point], as_root=True)
        except BaseException, e:
            # Unmount.
            if mount_point is not None:
                try:
                    self.ex.runv(['umount', mount_point], as_root=True)
                except Exception:
                    pass

            # Undo device mapping.
            try:
                self.ex.runv(['kpartx', '-d', image_name], as_root=True)
            except Exception:
                pass
            raise

        # Undo device mapping.
        self.ex.runv(['kpartx', '-d', image_name], as_root=True)

        # Move image file to cache.
        filename = self.filename(self.morph.name)
        self.ex.runv(['mv', image_name, filename])

        return { self.morph.name: filename }

class Builder(object):

    '''Build binary objects for Baserock.
    
    The objects may be chunks or strata.'''
    
    def __init__(self, tempdir, msg, settings):
        self.tempdir = tempdir
        self.real_msg = msg
        self.settings = settings
        self.cachedir = morphlib.cachedir.CacheDir(settings['cachedir'])
        self.indent = 0

    def msg(self, text):
        spaces = '  ' * self.indent
        self.real_msg('%s%s' % (spaces, text))

    def indent_more(self):
        self.indent += 1
    
    def indent_less(self):
        self.indent -= 1

    def build(self, repo, ref, filename):
        '''Build a binary based on a morphology.'''

        self.indent_more()
        self.msg('build %s|%s|%s' % (repo, ref, filename))
        repo = urlparse.urljoin(self.settings['git-base-url'], repo)
        morph = self.get_morph_from_git(repo, ref, filename)

        if morph.kind == 'chunk':
            blob = Chunk(morph, repo, ref)
        elif morph.kind == 'stratum':
            blob = Stratum(morph, repo, ref)
        elif morph.kind == 'system':
            blob = System(morph, repo, ref)
        else:
            raise Exception('Unknown kind of morphology: %s' % morph.kind)

        dict_key = blob.dict_key()
        self.complete_dict_key(dict_key, morph.name, repo, ref)
        logging.debug('completed dict_key:\n%s' % repr(dict_key))

        blob.builddir = self.tempdir.join('%s.build' % morph.name)
        blob.destdir = self.tempdir.join('%s.inst' % morph.name)
        blob.staging = self.tempdir.join('staging')
        blob.settings = self.settings
        blob.msg = self.msg
        blob.cache_prefix = self.cachedir.name(dict_key)
        blob.tempdir = self.tempdir
        
        builds = blob.builds()
        if all(os.path.exists(builds[x]) for x in builds):
            for x in builds:
                self.msg('using cached %s %s at %s' % 
                            (morph.kind, x, builds[x]))
            return builds

        if not os.path.exists(blob.staging):
            os.mkdir(blob.staging)
        self.build_needed(blob)

        self.msg('Building %s %s' % (morph.kind, morph.name))
        self.indent_more()
        built = blob.build()
        self.indent_less()
        for x in built:
            self.msg('%s %s cached at %s' % (morph.kind, x, built[x]))
        self.indent_less()
        return built

    def build_needed(self, blob):
        blob.built = []
        for repo, ref, morph_name, blob_names in blob.needs_built():
            morph_filename = '%s.morph' % morph_name
            cached = self.build(repo, ref, morph_filename)
            for blob_name in blob_names:
                blob.built.append((blob_name, cached[blob_name]))
            for blob_name in cached:
                morphlib.bins.unpack_binary(cached[blob_name], blob.staging)
            
    def complete_dict_key(self, dict_key, name, repo, ref):
        '''Fill in default fields of a cache's dict key.'''

        if repo and ref:
            abs_ref = morphlib.git.get_commit_id(repo, ref)
        else:
            abs_ref = ''

        dict_key['name'] = name
        dict_key['arch'] = morphlib.util.arch()
        dict_key['repo'] = repo
        dict_key['ref'] = abs_ref

    def get_morph_from_git(self, repo, ref, filename):
        morph_text = morphlib.git.get_morph_text(repo, ref, filename)
        f = StringIO.StringIO(morph_text)
        f.name = filename
        morph = morphlib.morphology.Morphology(f, 
                                               self.settings['git-base-url'])
        return morph

