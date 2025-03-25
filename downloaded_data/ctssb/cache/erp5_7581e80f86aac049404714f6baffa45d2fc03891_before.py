##############################################################################
#
# Copyright (c) 2008-2010 Nexedi SA and Contributors. All Rights Reserved.
#                    Lukasz Nowak <luke@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsibility of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# guarantees and support are strongly advised to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import os
import subprocess
import unittest
from distutils import util

try:
  any([True])
except NameError:
  # there is no any in python2.4
  def any(l):
    for q in l:
      if q:
        return True
    return False

# List of libraries which are acceptable to be linked in globally
ACCEPTABLE_GLOBAL_LIB_LIST = (
  # 32 bit Linux
	'/usr/lib/libstdc++.so',
 	'/lib/libgcc_s.so',
  '/lib/ld-linux.so',
  '/lib/libc.so',
  '/lib/libcrypt.so',
  '/lib/libdl.so',
  '/lib/libm.so',
  '/lib/libnsl.so',
  '/lib/libpthread.so',
  '/lib/libresolv.so',
  '/lib/librt.so',
  '/lib/libutil.so',
  # 64 bit Linux
	'/lib64/libgcc_s.so',
	'/usr/lib64/libstdc++.so',
  '/lib64/ld-linux-x86-64.so',
  '/lib64/libc.so',
  '/lib64/libcrypt.so',
  '/lib64/libdl.so',
  '/lib64/libm.so',
  '/lib64/libnsl.so',
  '/lib64/libpthread.so',
  '/lib64/libresolv.so',
  '/lib64/librt.so',
  '/lib64/libutil.so',
  # Arch independed Linux
  'linux-vdso.so',
)

SKIP_PART_LIST = (
  'parts/boost-lib-download',
  'parts/mysql-5.1__compile__',
  'parts/openoffice-bin',
  'parts/openoffice-bin__unpack__',
)

def readElfAsDict(f):
  """Reads ELF information from file"""
  popen = subprocess.Popen(['readelf', '-d', os.path.join(*f.split('/'))],
      stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  result = popen.communicate()[0]
  if popen.returncode != 0:
    raise AssertionError(result)
  library_list = []
  rpath_list = []
  runpath_list = []
  for l in result.split('\n'):
    if '(NEEDED)' in l:
      library_list.append(l.split(':')[1].strip(' []').split('.so')[0])
    elif '(RPATH)' in l:
      rpath_list = [q.rstrip('/') for q in l.split(':',1)[1].strip(' []').split(':')]
    elif '(RUNPATH)' in l:
      runpath_list = [q.rstrip('/') for q in l.split(':',1)[1].strip(' []').split(':')]
  if len(runpath_list) == 0:
    runpath_list = rpath_list
  elif len(rpath_list) != 0 and runpath_list != rpath_list:
    raise ValueError('RPATH and RUNPATH are different.')
  return dict(
    library_list=sorted(library_list),
    runpath_list=sorted(runpath_list)
  )

def readLddInfoList(f):
  popen = subprocess.Popen(['ldd', f], stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT)
  link_list = []
  a = link_list.append
  result = popen.communicate()[0]
  if 'not a dynamic executable' in result:
    return link_list
  for line in result.split('\n'):
    line = line.strip()
    if '=>' in line:
      lib, path = line.split('=>')
      lib = lib.strip()
      path = path.strip()
      if lib in path:
        # libpthread.so.0 => /lib64/libpthread.so.0 (0x00007f77fcebf000)
        a(path.split()[0])
      else:
        # linux-vdso.so.1 =>  (0x00007fffa7fff000)
        a(lib)
    elif 'warning: you do not have execution permission for' in line:
      pass
    elif 'No such file or directory' in line:
      # ignore broken links
      pass
    elif line:
      # /lib64/ld-linux-x86-64.so.2 (0x00007f77fd400000)
      a(line.split()[0])
  return link_list

class AssertSoftwareMixin(unittest.TestCase):
  def assertEqual(self, first, second, msg=None):
    try:
      return unittest.TestCase.assertEqual(self, first, second, msg=msg)
    except unittest.TestCase.failureException:
      if isinstance(first, list) and \
          isinstance(second, list):
        err = ''
        for elt in first:
          if elt not in second:
            err += '- %s\n' % elt
        for elt in second:
          if elt not in first:
            err += '+ %s\n' % elt
        if err == '':
          raise
        else:
          if msg:
            msg = '%s: Lists are different:\n%s' % (msg, err)
          else:
            msg = 'Lists are different:\n%s' % err
          raise unittest.TestCase.failureException, msg
      else:
        raise

  def assertLibraryList(self, path, library_list=None, software_list=None,
                        additional_runpath_list=None):
    elf_dict = readElfAsDict(path)
    if library_list is not None:
      self.assertEqual(sorted(library_list), elf_dict['library_list'], path)
    if software_list is not None:
      soft_dir = os.path.join(os.path.abspath(os.curdir), 'parts')
      runpath_list = [os.path.join(soft_dir, software, 'lib') for
        software in software_list]
      if additional_runpath_list is not None:
        runpath_list.extend(additional_runpath_list)
      self.assertEqual(sorted(runpath_list), elf_dict['runpath_list'], path)

  def assertSoftwareDictEmpty(self, first, msg=None):
    try:
      return unittest.TestCase.assertEqual(self, first, {}, msg)
    except unittest.TestCase.failureException:
      if msg is None:
        msg = ''
        for path, wrong_link_list in first.iteritems():
          msg += '%s:\n' % path
          msg += '\n'.join(['\t' + q for q in sorted(wrong_link_list)]) + '\n'
        msg = 'Bad linked software:\n%s' % msg
        raise unittest.TestCase.failureException, msg
      else:
        raise

class AssertSoftwareRunable(AssertSoftwareMixin):
  def test_HaProxy(self):
    stdout, stderr = subprocess.Popen(["parts/haproxy/sbin/haproxy", "-v"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertTrue(stdout.startswith('HA-Proxy'))

  def test_Apache(self):
    stdout, stderr = subprocess.Popen(["parts/apache/bin/httpd", "-v"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertTrue(stdout.startswith('Server version: Apache'))

  def test_Varnish(self):
    stdout, stderr = subprocess.Popen(["parts/varnish/sbin/varnishd", "-V"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stdout, '')
    self.assertTrue(stderr.startswith('varnishd ('))

  def test_TokyoCabinet(self):
    stdout, stderr = subprocess.Popen(["parts/tokyocabinet/bin/tcamgr",
      "version"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertTrue(stdout.startswith('Tokyo Cabinet'))

  def test_Flare(self):
    stdout, stderr = subprocess.Popen(["parts/flare/bin/flarei", "-v"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertTrue(stdout.startswith('flare'))

  def test_rdiff_backup(self):
    stdout, stderr = subprocess.Popen(["bin/rdiff-backup", "-V"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertEqual(stdout.strip(), 'rdiff-backup 1.0.5')

  def test_imagemagick(self):
    binary_list = [ 'animate', 'composite', 'convert', 'identify', 'mogrify',
        'stream', 'compare', 'conjure', 'display', 'import', 'montage']
    base = os.path.join('parts', 'imagemagick', 'bin')
    error_list = []
    for binary in binary_list:
      stdout, stderr = subprocess.Popen([os.path.join(base, binary), "-version"],
          stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
      if 'Version: ImageMagick' not in stdout:
        error_list.append(binary)
    self.assertEqual([], error_list)

  def test_w3m(self):
    stdout, stderr = subprocess.Popen(["parts/w3m/bin/w3m", "-V"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    self.assertEqual(stderr, '')
    self.assertTrue(stdout.startswith('w3m version w3m/0.5.2'))

class AssertMysql50Tritonn(AssertSoftwareMixin):
  def test_ld_mysqld(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/libexec/mysqld', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libdl',
      'libgcc_s',
      'libm',
      'libnsl',
      'libpthread',
      'librt',
      'libsenna',
      'libssl',
      'libstdc++',
      'libz',
      ], [
      'ncurses',
      'openssl',
      'readline',
      'senna',
      'zlib',
      ])

  def test_ld_mysqlmanager(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/libexec/mysqlmanager', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libgcc_s',
      'libm',
      'libnsl',
      'libpthread',
      'libssl',
      'libstdc++',
      'libz',
      ], [
      'ncurses',
      'zlib',
      'readline',
      'openssl',
      ])

  def test_ld_libmysqlclient_r(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/lib/mysql/libmysqlclient_r.so', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libm',
      'libnsl',
      'libpthread',
      'libssl',
      'libz',
      ], [
      'ncurses',
      'openssl',
      'readline',
      'zlib',
      ])

  def test_ld_libmysqlclient(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/lib/mysql/libmysqlclient.so', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libm',
      'libnsl',
      'libssl',
      'libz',
      ], [
      'ncurses',
      'openssl',
      'readline',
      'zlib',
      ])

  def test_ld_sphinx(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/lib/mysql/sphinx.so', [
      'libc',
      'libcrypt',
      'libgcc_s',
      'libm',
      'libnsl',
      'libpthread',
      'libstdc++',
      ], [
      'ncurses',
      'openssl',
      'readline',
      'zlib',
      ])

  def test_ld_mysql(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/bin/mysql', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libgcc_s',
      'libm',
      'libmysqlclient',
      'libncurses',
      'libnsl',
      'libreadline',
      'libssl',
      'libstdc++',
      'libz',
      ], [
      'ncurses',
      'zlib',
      'readline',
      'openssl',
      ], [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-tritonn-5.0', 'lib', 'mysql')])

  def test_ld_mysqladmin(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/bin/mysqladmin', [
      'libc',
      'libcrypt',
      'libcrypto',
      'libgcc_s',
      'libm',
      'libmysqlclient',
      'libnsl',
      'libssl',
      'libstdc++',
      'libz',
      ], [
      'ncurses',
      'openssl',
      'readline',
      'zlib',
      ], [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-tritonn-5.0', 'lib', 'mysql')])

  def test_ld_mysqldump(self):
    self.assertLibraryList('parts/mysql-tritonn-5.0/bin/mysqldump', ['libc', 'libcrypt', 'libcrypto', 'libm',
      'libmysqlclient', 'libnsl', 'libssl', 'libz'], ['ncurses', 'zlib', 'readline', 'openssl'], [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-tritonn-5.0', 'lib', 'mysql')])

class AssertMysql51(AssertSoftwareMixin):
  def test_ld_mysqld(self):
    self.assertLibraryList('parts/mysql-5.1/libexec/mysqld', ['libc', 'libcrypt', 'libdl', 'libgcc_s', 'libm', 'libnsl',
      'libpthread', 'libstdc++', 'libz'], ['ncurses', 'zlib', 'readline'])

  def test_ld_mysqlmanager(self):
    self.assertLibraryList('parts/mysql-5.1/libexec/mysqlmanager', ['libc', 'libcrypt', 'libgcc_s', 'libm', 'libnsl',
      'libpthread', 'libstdc++', 'libz'], ['ncurses', 'zlib', 'readline'])

  def test_ld_libmysqlclient_r(self):
    self.assertLibraryList('parts/mysql-5.1/lib/mysql/libmysqlclient_r.so', ['libc', 'libz', 'libcrypt', 'libm', 'libnsl', 'libpthread'], ['ncurses', 'zlib', 'readline'])

  def test_ld_libmysqlclient(self):
    self.assertLibraryList('parts/mysql-5.1/lib/mysql/libmysqlclient.so', ['libc', 'libz', 'libcrypt', 'libm', 'libnsl', 'libpthread'], ['ncurses', 'readline', 'zlib'])

  def test_ld_mysql(self):
    self.assertLibraryList('parts/mysql-5.1/bin/mysql', ['libc', 'libz', 'libcrypt', 'libgcc_s', 'libm',
      'libmysqlclient', 'libncurses', 'libnsl', 'libpthread', 'libreadline',
      'libstdc++'], ['ncurses', 'zlib', 'readline'],
                           [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-5.1', 'lib', 'mysql')])

  def test_ld_mysqladmin(self):
    self.assertLibraryList('parts/mysql-5.1/bin/mysqladmin', ['libc', 'libz', 'libcrypt', 'libgcc_s', 'libm',
      'libmysqlclient', 'libnsl', 'libpthread', 'libstdc++'], ['ncurses', 'zlib', 'readline'],
                           [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-5.1', 'lib', 'mysql')])

  def test_ld_mysqldump(self):
    self.assertLibraryList('parts/mysql-5.1/bin/mysqldump', ['libc', 'libz', 'libcrypt', 'libm', 'libmysqlclient',
      'libnsl', 'libpthread'], ['ncurses', 'zlib', 'readline'],
                           [os.path.join(os.path.abspath(os.curdir),
      'parts', 'mysql-5.1', 'lib', 'mysql')])

class AssertSqlite3(AssertSoftwareMixin):
  """Tests for built memcached"""

  def test_ld_bin_sqlite3(self):
    self.assertLibraryList('parts/sqlite3/bin/sqlite3', ['libpthread', 'libc', 'libdl', 'libsqlite3'], ['sqlite3'])

  def test_ld_libsqlite3(self):
    self.assertLibraryList('parts/sqlite3/lib/libsqlite3.so', ['libpthread', 'libc', 'libdl'], [])

class AssertMemcached(AssertSoftwareMixin):
  """Tests for built memcached"""

  def test_ld_memcached(self):
    """Checks proper linking to libevent from memcached"""
    self.assertLibraryList('parts/memcached/bin/memcached', ['libpthread', 'libevent-1.4', 'libc'], ['libevent'])

class AssertSubversion(AssertSoftwareMixin):
  """Tests for built subversion"""
  def test_ld_svn(self):
    self.assertLibraryList('parts/subversion/bin/svn', ['libsvn_client-1', 'libsvn_wc-1', 'libsvn_ra-1',
      'libsvn_diff-1', 'libsvn_ra_local-1', 'libsvn_repos-1', 'libsvn_fs-1',
      'libsvn_fs_fs-1', 'libsvn_fs_util-1', 'libsvn_ra_svn-1',
      'libsvn_delta-1', 'libsvn_subr-1', 'libsqlite3', 'libxml2',
      'libaprutil-1', 'libapr-1', 'libuuid', 'librt', 'libexpat',
      'libz', 'libssl', 'libcrypto', 'libsvn_ra_neon-1',
      'libc', 'libcrypt', 'libdl', 'libm',
      'libpthread', 'libneon'
      ], ['apache', 'libexpat', 'openssl', 'neon', 'libxml2',
                     'sqlite3', 'subversion', 'zlib', 'libuuid'])

  def test_ld_svnadmin(self):
    self.assertLibraryList('parts/subversion/bin/svnadmin', ['libsvn_repos-1', 'libsvn_fs-1',
      'libsvn_fs_fs-1', 'libsvn_fs_util-1', 'libsvn_delta-1', 'libsvn_subr-1',
      'libsqlite3', 'libaprutil-1', 'libapr-1', 'libuuid', 'librt',
      'libexpat', 'libz', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_svndumpfilter(self):
    self.assertLibraryList('parts/subversion/bin/svndumpfilter', ['libsvn_repos-1', 'libsvn_fs-1',
      'libsvn_fs_fs-1', 'libsvn_fs_util-1', 'libsvn_delta-1', 'libsvn_subr-1',
      'libsqlite3', 'libaprutil-1', 'libapr-1', 'libuuid', 'librt',
      'libexpat', 'libz', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_svnlook(self):
    self.assertLibraryList('parts/subversion/bin/svnlook', ['libsvn_repos-1', 'libsvn_fs-1', 'libsvn_diff-1',
      'libsvn_fs_fs-1', 'libsvn_fs_util-1', 'libsvn_delta-1', 'libsvn_subr-1',
      'libsqlite3', 'libaprutil-1', 'libapr-1', 'libuuid', 'librt',
      'libexpat', 'libz', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_svnserve(self):
    self.assertLibraryList('parts/subversion/bin/svnserve', ['libsvn_repos-1', 'libsvn_fs-1', 'libsvn_ra_svn-1',
      'libsvn_fs_fs-1', 'libsvn_fs_util-1', 'libsvn_delta-1', 'libsvn_subr-1',
      'libsqlite3', 'libaprutil-1', 'libapr-1', 'libuuid', 'librt',
      'libexpat', 'libz', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_svnsync(self):
    self.assertLibraryList('parts/subversion/bin/svnsync', [
      'libapr-1',
      'libaprutil-1',
      'libc',
      'libcrypt',
      'libcrypto',
      'libdl',
      'libexpat',
      'libm',
      'libneon',
      'libpthread',
      'librt',
      'libsqlite3',
      'libssl',
      'libsvn_delta-1',
      'libsvn_fs-1',
      'libsvn_fs_fs-1',
      'libsvn_fs_util-1',
      'libsvn_ra-1',
      'libsvn_ra_local-1',
      'libsvn_ra_neon-1',
      'libsvn_ra_svn-1',
      'libsvn_repos-1',
      'libsvn_subr-1',
      'libuuid',
      'libxml2',
      'libz',
      ], [
      'apache',
      'libexpat',
      'libuuid',
      'libxml2',
      'neon',
      'openssl',
      'sqlite3',
      'subversion',
      'zlib',
      ])

  def test_ld_svnversion(self):
    self.assertLibraryList('parts/subversion/bin/svnversion', ['libsvn_diff-1', 'libsvn_wc-1',
      'libsvn_delta-1', 'libsvn_subr-1', 'libsqlite3',
      'libaprutil-1', 'libapr-1', 'libuuid', 'librt', 'libexpat',
      'libz', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_client(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_client-1.so', ['libsvn_diff-1', 'libsvn_wc-1',
      'libsvn_delta-1', 'libsvn_subr-1', 'libsvn_ra-1',
      'libaprutil-1', 'libapr-1', 'libuuid', 'librt', 'libexpat',
      'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'sqlite3', 'subversion', 'zlib',
      'libuuid', 'neon'])

  def test_ld_libsvn_delta(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_delta-1.so', [
      'libsvn_subr-1', 'libz',
      'libaprutil-1', 'libapr-1', 'libuuid', 'librt', 'libexpat',
      'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'sqlite3', 'subversion', 'zlib',
      'libuuid', 'neon'])

  def test_ld_libsvn_diff(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_diff-1.so', [
      'libsvn_subr-1', 'libaprutil-1', 'libapr-1', 'libuuid', 'librt',
      'libexpat', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'sqlite3', 'subversion', 'zlib',
      'libuuid', 'neon'])

  def test_ld_libsvn_fs(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_fs-1.so', [
      'libapr-1',
      'libc',
      'libcrypt',
      'libdl',
      'libpthread',
      'librt',
      'libsvn_delta-1',
      'libsvn_fs_fs-1',
      'libsvn_fs_util-1',
      'libsvn_subr-1',
      'libuuid',
      ], [
      'apache',
      'libuuid',
      'neon',
      'sqlite3',
      'subversion',
      'zlib',
      ])

  def test_ld_libsvn_fs_fs(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_fs_fs-1.so', ['libsvn_delta-1', 'libaprutil-1', 'libexpat',
      'libsvn_fs_util-1', 'libsvn_subr-1', 'libapr-1', 'libuuid', 'librt',
      'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'sqlite3', 'subversion', 'zlib',
      'libuuid', 'neon'])

  def test_ld_libsvn_fs_util(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_fs_util-1.so', ['libaprutil-1', 'libexpat',
      'libsvn_subr-1', 'libapr-1', 'libuuid', 'librt',
      'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'sqlite3', 'subversion', 'zlib',
      'libuuid', 'neon'])

  def test_ld_libsvn_ra(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_ra-1.so', ['libaprutil-1', 'libsvn_delta-1', 'libsvn_fs-1',
      'libsvn_ra_local-1', 'libsvn_ra_neon-1', 'libsvn_ra_svn-1',
      'libsvn_repos-1', 'libexpat', 'libsvn_subr-1', 'libapr-1', 'libuuid',
      'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_ra_local(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_ra_local-1.so', ['libaprutil-1', 'libsvn_delta-1', 'libsvn_fs-1',
      'libsvn_repos-1', 'libexpat', 'libsvn_subr-1', 'libapr-1', 'libuuid',
      'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_ra_neon(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_ra_neon-1.so', [
      'libapr-1',
      'libaprutil-1',
      'libc',
      'libcrypt',
      'libcrypto',
      'libdl',
      'libexpat',
      'libm',
      'libneon',
      'libpthread',
      'librt',
      'libssl',
      'libsvn_delta-1',
      'libsvn_subr-1',
      'libuuid',
      'libxml2',
      'libz',
      ], [
      'apache',
      'libexpat',
      'libuuid',
      'libxml2',
      'neon',
      'openssl',
      'sqlite3',
      'subversion',
      'zlib',
      ])

  def test_ld_libsvn_ra_svn(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_ra_svn-1.so', ['libaprutil-1', 'libsvn_delta-1',
      'libexpat', 'libsvn_subr-1', 'libapr-1', 'libuuid',
      'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_repos(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_repos-1.so', ['libaprutil-1', 'libsvn_delta-1',
      'libexpat', 'libsvn_subr-1', 'libapr-1', 'libuuid', 'libsvn_fs-1',
      'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat',
                     'sqlite3', 'subversion', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_subr(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_subr-1.so', ['libaprutil-1', 'libexpat', 'libapr-1',
      'libuuid', 'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      'libsqlite3', 'libz',
      ], ['apache', 'libexpat',
                     'sqlite3', 'zlib', 'libuuid', 'neon'])

  def test_ld_libsvn_wc(self):
    self.assertLibraryList('parts/subversion/lib/libsvn_wc-1.so', ['libaprutil-1', 'libexpat', 'libapr-1',
      'libsvn_delta-1', 'libsvn_diff-1', 'libsvn_subr-1',
      'libuuid', 'librt', 'libc', 'libcrypt', 'libdl', 'libpthread',
      ], ['apache', 'libexpat', 'subversion',
                     'sqlite3', 'zlib', 'libuuid', 'neon'])

class AssertNeon(AssertSoftwareMixin):
  """Tests for built neon"""
  def test_ld_libneon(self):
    self.assertLibraryList('parts/neon/lib/libneon.so', [
      'libc',
      'libcrypto',
      'libdl',
      'libm',
      'libssl',
      'libxml2',
      'libz',
      ], [
      'libxml2',
      'openssl',
      'zlib',
      ])

  def test_neonconfig(self):
    popen = subprocess.Popen([os.path.join('parts', 'neon', 'bin', 'neon-config'),
      '--libs'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = popen.communicate()[0]
    self.assertEqual(0, popen.returncode, result)
    result_left = []
    for l in result.split():
      # let's remove acceptable parameters
      if l in (
      '-Wl,-rpath',
      '-lcrypto',
      '-ldl',
      '-lm',
      '-lneon',
      '-lpthread',
      '-lssl',
      '-lxml2',
      '-lz',
          ):
        continue
      if 'parts/neon/lib' in l:
        continue
      if 'parts/zlib/lib' in l:
        continue
      if 'parts/libxml2/lib' in l:
        continue
      if 'parts/openssl/lib' in l:
        continue
      result_left.append(l)
    # whatever left is wrong
    self.assertEqual([], result_left)

class AssertPythonMysql(AssertSoftwareMixin):
  def test_ld_mysqlso(self):
    for d in os.listdir('develop-eggs'):
      if d.startswith('MySQL_python'):
        path = os.path.join('develop-eggs', d, '_mysql.so')
        elf_dict = readElfAsDict(path)
        self.assertEqual(sorted(['libc', 'libcrypt', 'libcrypto', 'libm',
      'libmysqlclient_r', 'libnsl', 'libpthread', 'libssl', 'libz']),
          elf_dict['library_list'])
        soft_dir = os.path.join(os.path.abspath(os.curdir), 'parts')
        expected_rpath_list = [os.path.join(soft_dir, software, 'lib') for
            software in ['zlib', 'openssl']]
        expected_rpath_list.append(os.path.join(os.path.abspath(os.curdir), 'parts', 'mysql-tritonn-5.0', 'lib', 'mysql'))
        self.assertEqual(sorted(expected_rpath_list), elf_dict['runpath_list'])

class AssertApache(AssertSoftwareMixin):
  """Tests for built apache"""

  def test_ld_libaprutil1(self):
    """Checks proper linking of libaprutil-1.so"""
    self.assertLibraryList('parts/apache/lib/libaprutil-1.so', ['libexpat', 'libapr-1', 'librt', 'libcrypt',
      'libpthread', 'libdl', 'libc', 'libuuid'], ['apache', 'zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_libapr1(self):
    """Checks proper linking of libapr-1.so"""
    self.assertLibraryList('parts/apache/lib/libapr-1.so', ['librt', 'libcrypt', 'libuuid',
      'libpthread', 'libdl', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_modules(self):
    required_module_list = sorted([q.strip() for q in """
      actions_module
      alias_module
      asis_module
      auth_basic_module
      auth_digest_module
      authn_alias_module
      authn_anon_module
      authn_dbd_module
      authn_dbm_module
      authn_default_module
      authn_file_module
      authz_dbm_module
      authz_default_module
      authz_groupfile_module
      authz_host_module
      authz_owner_module
      authz_svn_module
      authz_user_module
      autoindex_module
      bucketeer_module
      cache_module
      case_filter_in_module
      case_filter_module
      cern_meta_module
      cgi_module
      cgid_module
      charset_lite_module
      core_module
      dav_fs_module
      dav_module
      dav_svn_module
      dbd_module
      deflate_module
      dir_module
      disk_cache_module
      dumpio_module
      echo_module
      env_module
      expires_module
      ext_filter_module
      filter_module
      headers_module
      http_module
      ident_module
      imagemap_module
      include_module
      info_module
      log_config_module
      log_forensic_module
      logio_module
      mime_magic_module
      mime_module
      mpm_prefork_module
      negotiation_module
      optional_fn_export_module
      optional_fn_import_module
      optional_hook_export_module
      optional_hook_import_module
      proxy_ajp_module
      proxy_balancer_module
      proxy_connect_module
      proxy_ftp_module
      proxy_http_module
      proxy_module
      proxy_scgi_module
      reqtimeout_module
      rewrite_module
      setenvif_module
      so_module
      speling_module
      ssl_module
      status_module
      substitute_module
      unique_id_module
      userdir_module
      usertrack_module
      version_module
      vhost_alias_module
    """.split() if len(q.strip()) > 0])
    popen = subprocess.Popen(['parts/apache/bin/httpd', '-M'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = popen.communicate()[0]
    loaded_module_list = sorted([module_name for module_name in result.split()
                          if module_name.endswith('module')])
    self.assertEqual(loaded_module_list, required_module_list)

  def test_ld_module_mod_actions(self):
    self.assertLibraryList('parts/apache/modules/mod_actions.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_alias(self):
    self.assertLibraryList('parts/apache/modules/mod_alias.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_asis(self):
    self.assertLibraryList('parts/apache/modules/mod_asis.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_auth_basic(self):
    self.assertLibraryList('parts/apache/modules/mod_auth_basic.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_auth_digest(self):
    self.assertLibraryList('parts/apache/modules/mod_auth_digest.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_alias(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_alias.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_anon(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_anon.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_dbd(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_dbd.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_dbm(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_dbm.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_default(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_default.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authn_file(self):
    self.assertLibraryList('parts/apache/modules/mod_authn_file.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_dbm(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_dbm.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_default(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_default.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_groupfile(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_groupfile.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_host(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_host.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_owner(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_owner.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_authz_user(self):
    self.assertLibraryList('parts/apache/modules/mod_authz_user.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_autoindex(self):
    self.assertLibraryList('parts/apache/modules/mod_autoindex.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_bucketeer(self):
    self.assertLibraryList('parts/apache/modules/mod_bucketeer.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_cache(self):
    self.assertLibraryList('parts/apache/modules/mod_cache.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_case_filter(self):
    self.assertLibraryList('parts/apache/modules/mod_case_filter.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_case_filter_in(self):
    self.assertLibraryList('parts/apache/modules/mod_case_filter_in.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_cern_meta(self):
    self.assertLibraryList('parts/apache/modules/mod_cern_meta.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_cgi(self):
    self.assertLibraryList('parts/apache/modules/mod_cgi.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_cgid(self):
    self.assertLibraryList('parts/apache/modules/mod_cgid.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_charset_lite(self):
    self.assertLibraryList('parts/apache/modules/mod_charset_lite.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_dav(self):
    self.assertLibraryList('parts/apache/modules/mod_dav.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_dav_fs(self):
    self.assertLibraryList('parts/apache/modules/mod_dav_fs.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_dbd(self):
    self.assertLibraryList('parts/apache/modules/mod_dbd.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_deflate(self):
    self.assertLibraryList('parts/apache/modules/mod_deflate.so', ['libpthread', 'libc', 'libz'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_dir(self):
    self.assertLibraryList('parts/apache/modules/mod_dir.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_disk_cache(self):
    self.assertLibraryList('parts/apache/modules/mod_disk_cache.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_dumpio(self):
    self.assertLibraryList('parts/apache/modules/mod_dumpio.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_echo(self):
    self.assertLibraryList('parts/apache/modules/mod_echo.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_env(self):
    self.assertLibraryList('parts/apache/modules/mod_env.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_expires(self):
    self.assertLibraryList('parts/apache/modules/mod_expires.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_ext_filter(self):
    self.assertLibraryList('parts/apache/modules/mod_ext_filter.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_filter(self):
    self.assertLibraryList('parts/apache/modules/mod_filter.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_headers(self):
    self.assertLibraryList('parts/apache/modules/mod_headers.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_ident(self):
    self.assertLibraryList('parts/apache/modules/mod_ident.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_imagemap(self):
    self.assertLibraryList('parts/apache/modules/mod_imagemap.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_include(self):
    self.assertLibraryList('parts/apache/modules/mod_include.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_info(self):
    self.assertLibraryList('parts/apache/modules/mod_info.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_log_config(self):
    self.assertLibraryList('parts/apache/modules/mod_log_config.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_log_forensic(self):
    self.assertLibraryList('parts/apache/modules/mod_log_forensic.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_logio(self):
    self.assertLibraryList('parts/apache/modules/mod_logio.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_mime(self):
    self.assertLibraryList('parts/apache/modules/mod_mime.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_mime_magic(self):
    self.assertLibraryList('parts/apache/modules/mod_mime_magic.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_negotiation(self):
    self.assertLibraryList('parts/apache/modules/mod_negotiation.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_optional_fn_export(self):
    self.assertLibraryList('parts/apache/modules/mod_optional_fn_export.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_optional_fn_import(self):
    self.assertLibraryList('parts/apache/modules/mod_optional_fn_import.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_optional_hook_export(self):
    self.assertLibraryList('parts/apache/modules/mod_optional_hook_export.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_optional_hook_import(self):
    self.assertLibraryList('parts/apache/modules/mod_optional_hook_import.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_ajp(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_ajp.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_balancer(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_balancer.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_connect(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_connect.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_ftp(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_ftp.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_http(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_http.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_proxy_scgi(self):
    self.assertLibraryList('parts/apache/modules/mod_proxy_scgi.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_reqtimeout(self):
    self.assertLibraryList('parts/apache/modules/mod_reqtimeout.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_rewrite(self):
    self.assertLibraryList('parts/apache/modules/mod_rewrite.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_setenvif(self):
    self.assertLibraryList('parts/apache/modules/mod_setenvif.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_speling(self):
    self.assertLibraryList('parts/apache/modules/mod_speling.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_ssl(self):
    self.assertLibraryList('parts/apache/modules/mod_ssl.so', ['libpthread', 'libc', 'libcrypto', 'libdl',
      'libssl', 'libz'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_status(self):
    self.assertLibraryList('parts/apache/modules/mod_status.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_substitute(self):
    self.assertLibraryList('parts/apache/modules/mod_substitute.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_unique_id(self):
    self.assertLibraryList('parts/apache/modules/mod_unique_id.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_userdir(self):
    self.assertLibraryList('parts/apache/modules/mod_userdir.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_usertrack(self):
    self.assertLibraryList('parts/apache/modules/mod_usertrack.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_version(self):
    self.assertLibraryList('parts/apache/modules/mod_version.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

  def test_ld_module_mod_vhost_alias(self):
    self.assertLibraryList('parts/apache/modules/mod_vhost_alias.so', ['libpthread', 'libc'], ['zlib', 'openssl', 'libuuid', 'libexpat', 'pcre'])

class AssertItools(AssertSoftwareMixin):
  def test_ld_parserso(self):
    self.assertLibraryList('parts/itools/lib/itools/xml/parser.so', ['libc', 'libglib-2.0', 'libpthread'], ['glib'])

class AssertOpenssl(AssertSoftwareMixin):
  def test_ld_openssl(self):
    self.assertLibraryList('parts/openssl/bin/openssl', ['libc', 'libcrypto', 'libdl', 'libssl'], ['openssl'])

class AssertCyrusSasl(AssertSoftwareMixin):
  def test_ld_pluginviewer(self):
    self.assertLibraryList('parts/cyrus-sasl/sbin/pluginviewer', [
      'libc',
      'libdl',
      'libresolv',
      'libsasl2',
      ], [
      'cyrus-sasl',
      'zlib',
      ])

  def test_ld_libsasl2(self):
    self.assertLibraryList('parts/cyrus-sasl/lib/libsasl2.so', [
      'libc',
      'libdl',
      'libresolv',
      ], [
      ])

  def test_ld_sasl2_libanonymous(self):
    self.assertLibraryList('parts/cyrus-sasl/lib/sasl2/libanonymous.so', [
      'libc',
      'libresolv',
      ], [
      ])

  def test_ld_sasl2_libcrammd5(self):
    self.assertLibraryList('parts/cyrus-sasl/lib/sasl2/libcrammd5.so', [
      'libc',
      'libresolv',
      ], [
      ])

  def test_ld_sasl2_libplain(self):
    self.assertLibraryList('parts/cyrus-sasl/lib/sasl2/libplain.so', [
      'libc',
      'libcrypt',
      'libresolv',
      ], [
      ])

class AssertPython26(AssertSoftwareMixin):
  def test_ld_dyn_locale(self):
    self.assertLibraryList('parts/python2.6/lib/python2.6/lib-dynload/_locale.so', [
      'libc',
      'libintl',
      'libpthread',
      ], [
      'bzip2',
      'gdbm',
      'gettext',
      'libdb',
      'ncurses',
      'openssl',
      'readline',
      'sqlite3',
      'zlib',
      ])

class AssertGettext(AssertSoftwareMixin):
  def test_ld_libintl(self):
    self.assertLibraryList('parts/gettext/lib/libintl.so', [
      'libc',
      ], [
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_libasprintf(self):
    self.assertLibraryList('parts/gettext/lib/libasprintf.so', [
      'libc',
      'libgcc_s',
      'libm',
      'libstdc++',
      ], [
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_libgettextlib(self):
    self.assertLibraryList('parts/gettext/lib/libgettextlib.so', [
      'libc',
      'libdl',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_libgettextpo(self):
    self.assertLibraryList('parts/gettext/lib/libgettextpo.so', [
      'libc',
      'libintl',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_libgettextsrc(self):
    self.assertLibraryList('parts/gettext/lib/libgettextsrc.so', [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def _test_ld_gettext_bin(self, bin):
    self.assertLibraryList(bin, [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libgettextsrc-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_envsubst(self):
    self.assertLibraryList('parts/gettext/bin/envsubst', [
      'libc',
      'libintl',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_gettext(self):
    self.assertLibraryList('parts/gettext/bin/gettext', [
      'libc',
      'libintl',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_msgattrib(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgattrib')

  def test_ld_msgcat(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgcat')

  def test_ld_msgcmp(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgcmp')

  def test_ld_msgcomm(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgcomm')

  def test_ld_msgconv(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgconv')

  def test_ld_msgen(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgen')

  def test_ld_msgexec(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgexec')

  def test_ld_msgfilter(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgfilter')

  def test_ld_msgfmt(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgfmt')

  def test_ld_msggrep(self):
    self.assertLibraryList('parts/gettext/bin/msggrep', [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libgettextsrc-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_msginit(self):
    self.assertLibraryList('parts/gettext/bin/msginit', [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libgettextsrc-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_msgmerge(self):
    self.assertLibraryList('parts/gettext/bin/msgmerge', [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libgettextsrc-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_msgunfmt(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msgunfmt')

  def test_ld_msguniq(self):
    self._test_ld_gettext_bin('parts/gettext/bin/msguniq')

  def test_ld_ngettext(self):
    self.assertLibraryList('parts/gettext/bin/ngettext', [
      'libc',
      'libintl',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_recode_sr_latin(self):
    self.assertLibraryList('parts/gettext/bin/recode-sr-latin', [
      'libc',
      'libdl',
      'libgettextlib-0.18.1',
      'libintl',
      'libm',
      'libncurses',
      'libxml2',
      'libz',
      ], [
      'gettext',
      'libxml2',
      'ncurses',
      'zlib',
      ])

  def test_ld_xgettext(self):
    self._test_ld_gettext_bin('parts/gettext/bin/xgettext')

class AssertLibxslt(AssertSoftwareMixin):
  def test_ld_xsltproc(self):
    self.assertLibraryList('parts/libxslt/bin/xsltproc', [
      'libc',
      'libdl',
      'libexslt',
      'libm',
      'libxml2',
      'libxslt',
      'libz',
      ], [
      'libxml2',
      'libxslt',
      'zlib',
      ])

class AssertW3m(AssertSoftwareMixin):
  def test_ld_w3m(self):
    self.assertLibraryList('parts/w3m/bin/w3m', [
      'libc',
      'libdl',
      'libcrypto',
      'libgc',
      'libm',
      'libncurses',
      'libnsl',
      'libpthread',
      'libssl',
      ], [
      'garbage-collector',
      'ncurses',
      'openssl',
      'zlib',
      ])

class AssertVarnish(AssertSoftwareMixin):
  def test_ld_varnishd(self):
    self.assertLibraryList('parts/varnish-2.1/sbin/varnishd', [
      'libc',
      'libdl',
      'libm',
      'libnsl',
      'libpthread',
      'libvarnish',
      'libvarnishcompat',
      'libvcl',
      ], [
      'ncurses',
      'varnish-2.1',
      ])

  def test_ld_varnishtop(self):
    self.assertLibraryList('parts/varnish-2.1/bin/varnishtop', [
      'libc',
      'libncurses',
      'libpthread',
      'libvarnish',
      'libvarnishapi',
      'libvarnishcompat',
      ], [
      'ncurses',
      'varnish-2.1',
      ])

class AssertLibrsync(AssertSoftwareMixin):
  def test_ld_rdiff(self):
    self.assertLibraryList('parts/librsync/bin/rdiff', [
      'libbz2',
      'libc',
      'libpopt',
      'librsync',
      'libz',
      ], [
      'bzip2',
      'librsync',
      'popt',
      'zlib',
      ])

  def test_ld_librsync(self):
    self.assertLibraryList('parts/librsync/lib/librsync.so', [
      'libbz2',
      'libc',
      'libpopt',
      'libz',
      ], [
      'bzip2',
      'popt',
      'zlib',
      ])

class AssertPopt(AssertSoftwareMixin):
  def test_ld_libpopt(self):
    self.assertLibraryList('parts/popt/lib/libpopt.so', [
      'libc',
      ], [
      ])

class AssertBzip2(AssertSoftwareMixin):
  def test_ld_bzip2(self):
    self.assertLibraryList('parts/bzip2/bin/bzip2', [
      'libc',
      ], [
      ])

  def test_ld_libbz2(self):
    self.assertLibraryList('parts/bzip2/lib/libbz2.so', [
      'libc',
      ], [
      ])

class AssertPysvn(AssertSoftwareMixin):
  def test_ld_pysvn(self):
    python_version_major, python_version_minor = util.sys.version_info[0:2]
    self.assertLibraryList('develop-eggs/pysvn-1.7.4-py%s.%s-%s.egg/pysvn/_pysvn_%s_%s.so' % (
      python_version_major, python_version_minor, util.get_platform(),
      python_version_major, python_version_minor), [
      'libc',
      'libcom_err',
      'libexpat',
      'libgcc_s',
      'libm',
      'libneon',
      'libresolv',
      'libssl',
      'libstdc++',
      'libsvn_client-1',
      'libsvn_diff-1',
      'libsvn_repos-1',
      ], [
      'libexpat',
      'neon',
      'openssl',
      'subversion'
      ])

class AssertElfLinkedInternally(AssertSoftwareMixin):
  def _xxtest(self):
    result_dict = {}
    root = os.path.join(os.path.abspath(os.curdir), 'parts')
    for dirpath, dirlist, filelist in os.walk(root):
      for filename in filelist:
        # skip some not needed places
        if any([q in dirpath for q in SKIP_PART_LIST]):
          continue
        filename = os.path.join(dirpath, filename)
        link_list = readLddInfoList(filename)
        bad_link_list = [q for q in link_list if not q.startswith(root) \
                          and not any([q.startswith(k) for k in ACCEPTABLE_GLOBAL_LIB_LIST])]
        if len(bad_link_list):
          result_dict[filename] = bad_link_list
    self.assertSoftwareDictEmpty(result_dict)


if __name__ == '__main__':
  unittest.main()
