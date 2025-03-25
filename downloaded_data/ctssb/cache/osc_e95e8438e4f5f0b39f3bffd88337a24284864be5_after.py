# vim: sw=4 et

# Copyright (C) 2006 Novell Inc.  All rights reserved.
# This program is free software; it may be used, copied, modified
# and distributed under the terms of the GNU General Public Licence,
# either version 2, or version 3 (at your option).

__version__ = '0.122'
# __store_version__ is to be incremented when the format of the working copy
# "store" changes in an incompatible way. Please add any needed migration
# functionality to check_store_version().
__store_version__ = '1.0'

import os
import os.path
import sys
import urllib2
from urllib import pathname2url, quote_plus, urlencode, unquote
from urlparse import urlsplit, urlunsplit
from cStringIO import StringIO
import shutil
import oscerr
import conf
import subprocess
import re
import socket
try:
    from xml.etree import cElementTree as ET
except ImportError:
    import cElementTree as ET



DISTURL_RE = re.compile(r"^(?P<bs>.*)://(?P<apiurl>.*?)/(?P<project>.*?)/(?P<repository>.*?)/(?P<revision>.*)-(?P<source>.*)$")
BUFSIZE = 1024*1024
store = '.osc'

# NOTE: do not use this anymore, use conf.exclude_glob instead.
# but this needs to stay to avoid breakage of tools which use osc lib
exclude_stuff = [store, 'CVS', '*~', '#*#', '.*', '_linkerror']

new_project_templ = """\
<project name="%(name)s">

  <title>Short title of NewProject</title>

  <description>This project aims at providing some foo and bar.

It also does some weird stuff.
</description>

  <person role="maintainer" userid="%(user)s" />
  <person role="bugowner" userid="%(user)s" />
<!-- remove this block to publish your packages on the mirrors -->
  <publish>
    <disable />
  </publish>
  <build>
    <enable />
  </build>
  <debuginfo>
    <disable />
  </debuginfo>

<!-- remove this comment to enable one or more build targets

  <repository name="openSUSE_Factory">
    <path project="openSUSE:Factory" repository="standard" />
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="openSUSE_11.1">
    <path project="openSUSE:11.1" repository="standard"/>
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="openSUSE_11.0">
    <path project="openSUSE:11.0" repository="standard"/>
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="openSUSE_10.3">
    <path project="openSUSE:10.3" repository="standard"/>
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="Fedora_11">
    <path project="Fedora:11" repository="standard" />
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="SLE_11">
    <path project="SUSE:SLE-11" repository="standard" />
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
  <repository name="SLE_10">
    <path project="SUSE:SLE-10:SDK" repository="standard" />
    <arch>x86_64</arch>
    <arch>i586</arch>
  </repository>
-->
 
</project>
"""

new_package_templ = """\
<package name="%(name)s">

  <title>Title of New Package</title>

  <description>
LONG DESCRIPTION 
GOES 
HERE
  </description>

  <person role="maintainer" userid="%(user)s"/>
  <person role="bugowner" userid="%(user)s"/>
  <url>PUT_UPSTREAM_URL_HERE</url>

<!-- 
  use one of the examples below to disable building of this package 
  on a certain architecture, in a certain repository, 
  or a combination thereof:
  
  <disable arch="x86_64"/>
  <disable repository="SUSE_SLE-10"/>
  <disable repository="SUSE_SLE-10" arch="x86_64"/>

  Possible sections where you can use the tags above:
  <build>
  </build>
  <debuginfo>
  </debuginfo>
  <publish>
  </publish>
  <useforbuild>
  </useforbuild>
  
  Please have a look at: 
  http://en.opensuse.org/Restricted_Formats
  Packages containing formats listed there are NOT allowed to 
  be packaged in the openSUSE Buildservice and will be deleted!

-->

</package>
"""

new_user_template = """\
<person>
  <login>%(user)s</login>
  <email>PUT_EMAIL_ADDRESS_HERE</email>
  <realname>PUT_REAL_NAME_HERE</realname>
  <watchlist>
    <project name="home:%(user)s"/>
  </watchlist>
</person>
"""

info_templ = """\
Project name: %s
Package name: %s
Path: %s
API URL: %s
Source URL: %s
srcmd5: %s
Revision: %s
Link info: %s
"""

new_pattern_template = """\
<!-- See http://svn.opensuse.org/svn/zypp/trunk/libzypp/zypp/parser/yum/schema/patterns.rng -->

<pattern>
</pattern>
"""

buildstatus_symbols = {'succeeded':       '.',
                       'disabled':        ' ',
                       'expansion error': 'E',
                       'failed':          'F',
                       'broken':          'B',
                       'blocked':         'b',
                       'building':        '%',
                       'finished':        'f',
                       'scheduled':       's',
                       'excluded':        'x',
                       'dispatching':     'd',
}

# os.path.samefile is available only under Unix
def os_path_samefile(path1, path2):
  try:
      return os.path.samefile(path1, path2)
  except:
      return os.path.realpath(path1) == os.path.realpath(path2)

class File:
    """represent a file, including its metadata"""
    def __init__(self, name, md5, size, mtime):
        self.name = name
        self.md5 = md5
        self.size = size
        self.mtime = mtime
    def __str__(self):
        return self.name


class Serviceinfo:
    """Source service content
    """
    def __init__(self):
        """creates an empty serviceinfo instance"""
        self.commands = None

    def read(self, serviceinfo_node):
        """read in the source services <services> element passed as
        elementtree node.
        """
        if serviceinfo_node == None:
            return
        self.commands = []
        services = serviceinfo_node.findall('service')

        for service in services:
            name = service.get('name')
            try:
                for param in service.findall('param'):
                   option = param.get('name', None)
                   value = param.text
                   name += " --" + option + " '" + value + "'"
                self.commands.append(name)
            except:
                msg = 'invalid service format:\n%s' % ET.tostring(root)
                raise oscerr.APIError(msg)

    def execute(self, dir):
        import tempfile

        for call in self.commands:
            temp_dir = tempfile.mkdtemp()
            name = call.split(None, 1)[0]
            if not os.path.exists("/usr/lib/obs/service/"+name):
               msg =  "ERROR: service is not installed !"
               msg += "Can maybe solved with: zypper in obs-server-" + name
               raise oscerr.APIError(msg)
            c = "/usr/lib/obs/service/" + call + " --outdir " + temp_dir
            ret = subprocess.call(c, shell=True)
            if ret != 0:
               print "ERROR: service call failed: " + c

            for file in os.listdir(temp_dir):
               os.rename( os.path.join(temp_dir, file), os.path.join(dir, "_service:"+name+":"+file) )
            os.rmdir(temp_dir)

class Linkinfo:
    """linkinfo metadata (which is part of the xml representing a directory
    """
    def __init__(self):
        """creates an empty linkinfo instance"""
        self.project = None
        self.package = None
        self.xsrcmd5 = None
        self.lsrcmd5 = None
        self.srcmd5 = None
        self.error = None
        self.rev = None

    def read(self, linkinfo_node):
        """read in the linkinfo metadata from the <linkinfo> element passed as
        elementtree node.
        If the passed element is None, the method does nothing.
        """
        if linkinfo_node == None:
            return
        self.project = linkinfo_node.get('project')
        self.package = linkinfo_node.get('package')
        self.xsrcmd5 = linkinfo_node.get('xsrcmd5')
        self.lsrcmd5 = linkinfo_node.get('lsrcmd5')
        self.srcmd5  = linkinfo_node.get('srcmd5')
        self.error   = linkinfo_node.get('error')
        self.rev     = linkinfo_node.get('rev')

    def islink(self):
        """returns True if the linkinfo is not empty, otherwise False"""
        if self.xsrcmd5 or self.lsrcmd5:
            return True
        return False

    def isexpanded(self):
        """returns True if the package is an expanded link"""
        if self.lsrcmd5 and not self.xsrcmd5:
            return True
        return False

    def haserror(self):
        """returns True if the link is in error state (could not be applied)"""
        if self.error:
            return True
        return False

    def __str__(self):
        """return an informatory string representation"""
        if self.islink() and not self.isexpanded():
            return 'project %s, package %s, xsrcmd5 %s, rev %s' \
                    % (self.project, self.package, self.xsrcmd5, self.rev)
        elif self.islink() and self.isexpanded():
            if self.haserror():
                return 'broken link to project %s, package %s, srcmd5 %s, lsrcmd5 %s: %s' \
                        % (self.project, self.package, self.srcmd5, self.lsrcmd5, self.error)
            else:
                return 'expanded link to project %s, package %s, srcmd5 %s, lsrcmd5 %s' \
                        % (self.project, self.package, self.srcmd5, self.lsrcmd5)
        else:
            return 'None'


class Project:
    """represent a project directory, holding packages"""
    def __init__(self, dir, getPackageList=True):
        import fnmatch
        self.dir = dir
        self.absdir = os.path.abspath(dir)

        self.name = store_read_project(self.dir)
        self.apiurl = store_read_apiurl(self.dir)

        if getPackageList:
            self.pacs_available = meta_get_packagelist(self.apiurl, self.name)
        else:
            self.pacs_available = []
        
        if conf.config['do_package_tracking']:
            self.pac_root = self.read_packages().getroot()
            self.pacs_have = [ pac.get('name') for pac in self.pac_root.findall('package') ]
            self.pacs_excluded = [ i for i in os.listdir(self.dir)
                                   for j in conf.config['exclude_glob']
                                   if fnmatch.fnmatch(i, j) ]
            self.pacs_unvers = [ i for i in os.listdir(self.dir) if i not in self.pacs_have and i not in self.pacs_excluded ]
            # store all broken packages (e.g. packages which where removed by a non-osc cmd)
            # in the self.pacs_broken list
            self.pacs_broken = []
            for p in self.pacs_have:
                if not os.path.isdir(os.path.join(self.absdir, p)):
                    # all states will be replaced with the '!'-state
                    # (except it is already marked as deleted ('D'-state))
                    self.pacs_broken.append(p)
        else:
            self.pacs_have = [ i for i in os.listdir(self.dir) if i in self.pacs_available ]

        self.pacs_missing = [ i for i in self.pacs_available if i not in self.pacs_have ]

    def checkout_missing_pacs(self, expand_link=False):
        for pac in self.pacs_missing:

            if conf.config['do_package_tracking'] and pac in self.pacs_unvers:
                # pac is not under version control but a local file/dir exists
                msg = 'can\'t add package \'%s\': Object already exists' % pac
                raise oscerr.PackageExists(self.name, pac, msg)
            else:
                print 'checking out new package %s' % pac
                checkout_package(self.apiurl, self.name, pac, \
                                 pathname=getTransActPath(os.path.join(self.dir, pac)), \
                                 prj_obj=self, prj_dir=self.dir, expand_link=expand_link)

    def set_state(self, pac, state):
        node = self.get_package_node(pac)
        if node == None:
            self.new_package_entry(pac, state)
        else:
            node.attrib['state'] = state

    def get_package_node(self, pac):
        for node in self.pac_root.findall('package'):
            if pac == node.get('name'):
                return node
        return None

    def del_package_node(self, pac):
        for node in self.pac_root.findall('package'):
            if pac == node.get('name'):
                self.pac_root.remove(node)

    def get_state(self, pac):
        node = self.get_package_node(pac)
        if node != None:
            return node.get('state')
        else:
            return None

    def new_package_entry(self, name, state):
        ET.SubElement(self.pac_root, 'package', name=name, state=state)

    def read_packages(self):
        if os.path.isfile(os.path.join(self.absdir, store, '_packages')):
            return ET.parse(os.path.join(self.absdir, store, '_packages'))
        else:
            # scan project for existing packages and migrate them
            cur_pacs = []
            for data in os.listdir(self.dir):
                pac_dir = os.path.join(self.absdir, data)
                # we cannot use self.pacs_available because we cannot guarantee that the package list
                # was fetched from the server
                if data in meta_get_packagelist(self.apiurl, self.name) and is_package_dir(pac_dir) \
                   and Package(pac_dir).name == data:
                    cur_pacs.append(ET.Element('package', name=data, state=' '))
            store_write_initial_packages(self.absdir, self.name, cur_pacs)
            return ET.parse(os.path.join(self.absdir, store, '_packages'))

    def write_packages(self):
        # TODO: should we only modify the existing file instead of overwriting?
        ET.ElementTree(self.pac_root).write(os.path.join(self.absdir, store, '_packages'))

    def addPackage(self, pac):
        import fnmatch
        for i in conf.config['exclude_glob']:
            if fnmatch.fnmatch(pac, i):
                return False
        state = self.get_state(pac)
        if state == None or state == 'D':
            self.new_package_entry(pac, 'A')
            self.write_packages()
            # sometimes the new pac doesn't exist in the list because
            # it would take too much time to update all data structs regularly
            if pac in self.pacs_unvers:
                self.pacs_unvers.remove(pac)
            return True
        else:
            print 'package \'%s\' is already under version control' % pac
            return False

    def delPackage(self, pac, force = False):
        state = self.get_state(pac.name)
        can_delete = True
        if state == ' ' or state == 'D':
            del_files = []
            for file in pac.filenamelist + pac.filenamelist_unvers:
                filestate = pac.status(file)
                if filestate == 'M' or filestate == 'C' or \
                   filestate == 'A' or filestate == '?':
                    can_delete = False
                else:    
                    del_files.append(file)
            if can_delete or force:
                for file in del_files:
                    pac.delete_localfile(file)
                    if pac.status(file) != '?':
                        pac.delete_storefile(file)
                        # this is not really necessary
                        pac.put_on_deletelist(file)
                        print statfrmt('D', getTransActPath(os.path.join(pac.dir, file)))
                print statfrmt('D', getTransActPath(os.path.join(pac.dir, os.pardir, pac.name)))
                pac.write_deletelist()
                self.set_state(pac.name, 'D')
                self.write_packages()
            else:
                print 'package \'%s\' has local modifications (see osc st for details)' % pac.name
        elif state == 'A':
            if force:
                delete_dir(pac.absdir)
                self.del_package_node(pac.name)
                self.write_packages()
                print statfrmt('D', pac.name)
            else:
                print 'package \'%s\' has local modifications (see osc st for details)' % pac.name
        elif state == None:
            print 'package is not under version control'
        else:
            print 'unsupported state'

    def update(self, pacs = (), expand_link=False, unexpand_link=False, service_files=False):
        if len(pacs):
            for pac in pacs:
                Package(os.path.join(self.dir, pac)).update()
        else:
            # we need to make sure that the _packages file will be written (even if an exception
            # occurs)
            try:
                # update complete project
                # packages which no longer exists upstream
                upstream_del = [ pac for pac in self.pacs_have if not pac in self.pacs_available and self.get_state(pac) != 'A']

                for pac in upstream_del:
                    p = Package(os.path.join(self.dir, pac))
                    self.delPackage(p, force = True)
                    delete_storedir(p.storedir)
                    try:
                        os.rmdir(pac)
                    except:
                        pass
                    self.pac_root.remove(self.get_package_node(p.name))
                    self.pacs_have.remove(pac)

                for pac in self.pacs_have:
                    state = self.get_state(pac)
                    if pac in self.pacs_broken:
                        if self.get_state(pac) != 'A':
                            checkout_package(self.apiurl, self.name, pac,
                                             pathname=getTransActPath(os.path.join(self.dir, pac)), prj_obj=self, prj_dir=self.dir, expand_link=expand_link)
                    elif state == ' ':
                        # do a simple update
                        p = Package(os.path.join(self.dir, pac))
                        rev = None
                        if expand_link and p.islink() and not p.isexpanded():
                            rev = p.linkinfo.xsrcmd5
                            print 'Expanding to rev', rev
                        elif unexpand_link and p.islink() and p.isexpanded():
                            rev = p.linkinfo.lsrcmd5
                            print 'Unexpanding to rev', rev
                        elif p.islink() and p.isexpanded():
                            rev = p.latest_rev();
                        print 'Updating %s' % p.name
                        p.update(rev, service_files)
                    elif state == 'D':
                        # TODO: Package::update has to fixed to behave like svn does
                        if pac in self.pacs_broken:
                            checkout_package(self.apiurl, self.name, pac,
                                             pathname=getTransActPath(os.path.join(self.dir, pac)), prj_obj=self, prj_dir=self.dir, expand_link=expand_link)
                        else:
                            Package(os.path.join(self.dir, pac)).update()
                    elif state == 'A' and pac in self.pacs_available:
                        # file/dir called pac already exists and is under version control
                        msg = 'can\'t add package \'%s\': Object already exists' % pac
                        raise oscerr.PackageExists(self.name, pac, msg)
                    elif state == 'A':
                        # do nothing
                        pass
                    else:
                        print 'unexpected state.. package \'%s\'' % pac

                self.checkout_missing_pacs()
            finally:
                self.write_packages()

    def commit(self, pacs = (), msg = '', files = {}):
        if len(pacs):
            try:
                for pac in pacs:
                    todo = []
                    if files.has_key(pac):
                        todo = files[pac]
                    state = self.get_state(pac)
                    if state == 'A':
                        self.commitNewPackage(pac, msg, todo)
                    elif state == 'D':
                        self.commitDelPackage(pac)
                    elif state == ' ':
                        # display the correct dir when sending the changes
                        if os_path_samefile(os.path.join(self.dir, pac), os.getcwd()):
                            p = Package('.')
                        else:
                            p = Package(os.path.join(self.dir, pac))
                        p.todo = todo
                        p.commit(msg)
                    elif pac in self.pacs_unvers and not is_package_dir(os.path.join(self.dir, pac)):
                        print 'osc: \'%s\' is not under version control' % pac
                    elif pac in self.pacs_broken:
                        print 'osc: \'%s\' package not found' % pac
                    elif state == None:
                        self.commitExtPackage(pac, msg, todo)
            finally:
                self.write_packages()
        else:
            # if we have packages marked as '!' we cannot commit
            for pac in self.pacs_broken:
                if self.get_state(pac) != 'D':
                    msg = 'commit failed: package \'%s\' is missing' % pac
                    raise oscerr.PackageMissing(self.name, pac, msg)
            try:
                for pac in self.pacs_have:
                    state = self.get_state(pac)
                    if state == ' ':
                        # do a simple commit
                        Package(os.path.join(self.dir, pac)).commit(msg)
                    elif state == 'D':
                        self.commitDelPackage(pac)
                    elif state == 'A':
                        self.commitNewPackage(pac, msg)
            finally:
                self.write_packages()

    def commitNewPackage(self, pac, msg = '', files = []):
        """creates and commits a new package if it does not exist on the server"""
        if pac in self.pacs_available:
            print 'package \'%s\' already exists' % pac
        else:
            user = conf.get_apiurl_usr(self.apiurl)
            edit_meta(metatype='pkg',
                      path_args=(quote_plus(self.name), quote_plus(pac)),
                      template_args=({
                              'name': pac,
                              'user': user}),
                      apiurl=self.apiurl)
            # display the correct dir when sending the changes
            olddir = os.getcwd()
            if os_path_samefile(os.path.join(self.dir, pac), os.curdir):
                os.chdir(os.pardir)
                p = Package(pac)
            else:
                p = Package(os.path.join(self.dir, pac))
            p.todo = files
            print statfrmt('Sending', os.path.normpath(p.dir))
            p.commit(msg)
            self.set_state(pac, ' ')
            os.chdir(olddir)

    def commitDelPackage(self, pac):
        """deletes a package on the server and in the working copy"""
        try:
            # display the correct dir when sending the changes
            if os_path_samefile(os.path.join(self.dir, pac), os.curdir):
                pac_dir = pac
            else:
                pac_dir = os.path.join(self.dir, pac)
            p = Package(os.path.join(self.dir, pac))
            #print statfrmt('Deleting', os.path.normpath(os.path.join(p.dir, os.pardir, pac)))
            delete_storedir(p.storedir)
            try:
                os.rmdir(p.dir)
            except:
                pass
        except OSError:
            pac_dir = os.path.join(self.dir, pac)
        #print statfrmt('Deleting', getTransActPath(os.path.join(self.dir, pac)))
        print statfrmt('Deleting', getTransActPath(pac_dir))
        delete_package(self.apiurl, self.name, pac)
        self.del_package_node(pac)

    def commitExtPackage(self, pac, msg, files = []):
        """commits a package from an external project"""
        if os_path_samefile(os.path.join(self.dir, pac), os.getcwd()):
            pac_path = '.'
        else:
            pac_path = os.path.join(self.dir, pac)
 
        project = store_read_project(pac_path)
        package = store_read_package(pac_path)
        apiurl = store_read_apiurl(pac_path)
        if meta_exists(metatype='pkg',
                       path_args=(quote_plus(project), quote_plus(package)),
                       template_args=None,
                       create_new=False, apiurl=apiurl):
            p = Package(pac_path)
            p.todo = files
            p.commit(msg)
        else:
            user = conf.get_apiurl_usr(self.apiurl)
            edit_meta(metatype='pkg',
                      path_args=(quote_plus(project), quote_plus(package)),
                      template_args=({
                              'name': pac,
                              'user': user}),
                              apiurl=apiurl)
            p = Package(pac_path)
            p.todo = files
            p.commit(msg)

    def __str__(self):
        r = []
        r.append('*****************************************************')
        r.append('Project %s (dir=%s, absdir=%s)' % (self.name, self.dir, self.absdir))
        r.append('have pacs:\n%s' % ', '.join(self.pacs_have))
        r.append('missing pacs:\n%s' % ', '.join(self.pacs_missing))
        r.append('*****************************************************')
        return '\n'.join(r)



class Package:
    """represent a package (its directory) and read/keep/write its metadata"""
    def __init__(self, workingdir):
        self.dir = workingdir
        self.absdir = os.path.abspath(self.dir)
        self.storedir = os.path.join(self.absdir, store)

        check_store_version(self.dir)

        self.prjname = store_read_project(self.dir)
        self.name = store_read_package(self.dir)
        self.apiurl = store_read_apiurl(self.dir)

        self.update_datastructs()

        self.todo = []
        self.todo_send = []
        self.todo_delete = []

    def info(self):
        source_url = makeurl(self.apiurl, ['source', self.prjname, self.name]) 
        r = info_templ % (self.prjname, self.name, self.absdir, self.apiurl, source_url, self.srcmd5, self.rev, self.linkinfo)
        return r

    def addfile(self, n):
        st = os.stat(os.path.join(self.dir, n))
        f = File(n, None, st.st_size, st.st_mtime)
        self.filelist.append(f)
        self.filenamelist.append(n)
        self.filenamelist_unvers.remove(n) 
        shutil.copy2(os.path.join(self.dir, n), os.path.join(self.storedir, n))

    def delete_file(self, n, force=False):
        """deletes a file if possible and marks the file as deleted"""
        state = self.status(n)
        if state in ['?', 'A', 'M'] and not force:
            return (False, state)
        self.delete_localfile(n)
        if state != 'A':
            self.put_on_deletelist(n)
            self.write_deletelist()
        else:
            self.delete_storefile(n)
        return (True, state)

    def delete_storefile(self, n):
        try: os.unlink(os.path.join(self.storedir, n))
        except: pass

    def delete_localfile(self, n):
        try: os.unlink(os.path.join(self.dir, n))
        except: pass

    def put_on_deletelist(self, n):
        if n not in self.to_be_deleted:
            self.to_be_deleted.append(n)

    def put_on_conflictlist(self, n):
        if n not in self.in_conflict:
            self.in_conflict.append(n)

    def clear_from_conflictlist(self, n):
        """delete an entry from the file, and remove the file if it would be empty"""
        if n in self.in_conflict:

            filename = os.path.join(self.dir, n)
            storefilename = os.path.join(self.storedir, n)
            myfilename = os.path.join(self.dir, n + '.mine')
            if self.islinkrepair():
                upfilename = os.path.join(self.dir, n + '.new')
            else:
                upfilename = os.path.join(self.dir, n + '.r' + self.rev)

            try:
                os.unlink(myfilename)
                # the working copy may be updated, so the .r* ending may be obsolete...
                # then we don't care
                os.unlink(upfilename)
                if self.islinkrepair():
                    os.unlink(os.path.join(self.dir, n + '.old'))
            except: 
                pass

            self.in_conflict.remove(n)

            self.write_conflictlist()

    def write_deletelist(self):
        if len(self.to_be_deleted) == 0:
            try:
                os.unlink(os.path.join(self.storedir, '_to_be_deleted'))
            except:
                pass
        else:
            fname = os.path.join(self.storedir, '_to_be_deleted')
            f = open(fname, 'w')
            f.write('\n'.join(self.to_be_deleted))
            f.write('\n')
            f.close()

    def delete_source_file(self, n):
        """delete local a source file"""
        self.delete_localfile(n)
        self.delete_storefile(n)

    def delete_remote_source_file(self, n):
        """delete a remote source file (e.g. from the server)"""
        query = 'rev=upload'
        u = makeurl(self.apiurl, ['source', self.prjname, self.name, pathname2url(n)], query=query)
        http_DELETE(u)
 
    def put_source_file(self, n):
        
        # escaping '+' in the URL path (note: not in the URL query string) is 
        # only a workaround for ruby on rails, which swallows it otherwise
        query = 'rev=upload'
        u = makeurl(self.apiurl, ['source', self.prjname, self.name, pathname2url(n)], query=query)
        http_PUT(u, file = os.path.join(self.dir, n))

        shutil.copy2(os.path.join(self.dir, n), os.path.join(self.storedir, n))

    def commit(self, msg=''):
        # commit only if the upstream revision is the same as the working copy's
        upstream_rev = self.latest_rev();
        if self.rev != upstream_rev:
            raise oscerr.WorkingCopyOutdated((self.absdir, self.rev, upstream_rev))

        if not self.todo:
            self.todo = self.filenamelist_unvers + self.filenamelist
      
        pathn = getTransActPath(self.dir)

        have_conflicts = False
        for filename in self.todo:
            if not filename.startswith('_service:') and not filename.startswith('_service_'):
              st = self.status(filename)
              if st == 'A' or st == 'M':
                  self.todo_send.append(filename)
                  print statfrmt('Sending', os.path.join(pathn, filename))
              elif st == 'D':
                  self.todo_delete.append(filename)
                  print statfrmt('Deleting', os.path.join(pathn, filename))
              elif st == 'C':
                  have_conflicts = True

        if have_conflicts:
            print 'Please resolve all conflicts before committing using "osc resolved FILE"!'
            return 1

        if not self.todo_send and not self.todo_delete and not self.rev == "upload" and not self.islinkrepair():
            print 'nothing to do for package %s' % self.name
            return 1

        if self.islink() and self.isexpanded():
            # resolve the link into the upload revision
            # XXX: do this always?
            query = { 'cmd': 'copy', 'rev': 'upload', 'orev': self.rev }
            u = makeurl(self.apiurl, ['source', self.prjname, self.name], query=query)
            f = http_POST(u)

        print 'Transmitting file data ', 
        try:
            for filename in self.todo_delete:
                # do not touch local files on commit --
                # delete remotely instead
                self.delete_remote_source_file(filename)
                self.to_be_deleted.remove(filename)
            for filename in self.todo_send:
                sys.stdout.write('.')
                sys.stdout.flush()
                self.put_source_file(filename)

            # all source files are committed - now comes the log
            query = { 'cmd'    : 'commit',
                      'rev'    : 'upload',
                      'user'   : conf.get_apiurl_usr(self.apiurl),
                      'comment': msg }
            if self.islink() and self.isexpanded():
                query['keeplink'] = '1'
            if self.islinkrepair():
                query['repairlink'] = '1'
            u = makeurl(self.apiurl, ['source', self.prjname, self.name], query=query)
            f = http_POST(u)
        except urllib2.HTTPError, e:
            # delete upload revision
            try:
                query = { 'cmd': 'deleteuploadrev' }
                u = makeurl(self.apiurl, ['source', self.prjname, self.name], query=query)
                f = http_POST(u)
            except:
                pass
            raise e

        root = ET.parse(f).getroot()
        self.rev = int(root.get('rev'))
        print
        print 'Committed revision %s.' % self.rev

        if self.islinkrepair():
            os.unlink(os.path.join(self.storedir, '_linkrepair'))
            self.linkrepair = False
            # XXX: mark package as invalid?
            print 'The source link has been repaired. This directory can now be removed.'
        if self.islink() and self.isexpanded():
            self.update_local_filesmeta(revision=self.latest_rev())
        else:
            self.update_local_filesmeta()
        self.write_deletelist()
        self.update_datastructs()

        if self.filenamelist.count('_service'):
            print 'The package contains a source service.'
            for filename in self.todo: 
              if filename.startswith('_service:') and os.path.exists(filename):
                os.unlink(filename) #remove local files

    def write_conflictlist(self):
        if len(self.in_conflict) == 0:
            try:
                os.unlink(os.path.join(self.storedir, '_in_conflict'))
            except:
                pass
        else:
            fname = os.path.join(self.storedir, '_in_conflict')
            f = open(fname, 'w')
            f.write('\n'.join(self.in_conflict))
            f.write('\n')
            f.close()

    def updatefile(self, n, revision):
        filename = os.path.join(self.dir, n)
        storefilename = os.path.join(self.storedir, n)
        mtime = self.findfilebyname(n).mtime

        get_source_file(self.apiurl, self.prjname, self.name, n, targetfilename=filename, revision=revision)
        os.utime(filename, (-1, mtime))

        shutil.copy2(filename, storefilename)

    def mergefile(self, n):
        filename = os.path.join(self.dir, n)
        storefilename = os.path.join(self.storedir, n)
        myfilename = os.path.join(self.dir, n + '.mine')
        upfilename = os.path.join(self.dir, n + '.r' + self.rev)
        os.rename(filename, myfilename)

        mtime = self.findfilebyname(n).mtime
        get_source_file(self.apiurl, self.prjname, self.name, n, 
                        revision=self.rev, targetfilename=upfilename)
        os.utime(upfilename, (-1, mtime))

        if binary_file(myfilename) or binary_file(upfilename):
                # don't try merging
                shutil.copy2(upfilename, filename)
                shutil.copy2(upfilename, storefilename)
                self.in_conflict.append(n)
                self.write_conflictlist()
                return 'C'
        else:
            # try merging
            # diff3 OPTIONS... MINE OLDER YOURS
            merge_cmd = 'diff3 -m -E %s %s %s > %s' % (myfilename, storefilename, upfilename, filename)
            # we would rather use the subprocess module, but it is not availablebefore 2.4
            ret = subprocess.call(merge_cmd, shell=True)
            
            #   "An exit status of 0 means `diff3' was successful, 1 means some
            #   conflicts were found, and 2 means trouble."
            if ret == 0:
                # merge was successful... clean up
                shutil.copy2(upfilename, storefilename)
                os.unlink(upfilename)
                os.unlink(myfilename)
                return 'G'
            elif ret == 1:
                # unsuccessful merge
                shutil.copy2(upfilename, storefilename)
                self.in_conflict.append(n)
                self.write_conflictlist()
                return 'C'
            else:
                print >>sys.stderr, '\ndiff3 got in trouble... exit code:', ret
                print >>sys.stderr, 'the command line was:'
                print >>sys.stderr, merge_cmd
                sys.exit(1)



    def update_local_filesmeta(self, revision=None):
        """
        Update the local _files file in the store.
        It is replaced with the version pulled from upstream.
        """
        meta = ''.join(show_files_meta(self.apiurl, self.prjname, self.name, revision=revision))
        try:
            f = open(os.path.join(self.storedir, '_files.new'), 'w')
            f.write(meta)
            f.close()
            os.rename(os.path.join(self.storedir, '_files.new'), os.path.join(self.storedir, '_files'))
        except:
            if os.path.exists(os.path.join(self.storedir, '_files.new')):
                os.unlink(os.path.join(self.storedir, '_files.new'))
            raise

    def update_datastructs(self):
        """
        Update the internal data structures if the local _files
        file has changed (e.g. update_local_filesmeta() has been
        called).
        """
        import fnmatch
        files_tree = read_filemeta(self.dir)
        files_tree_root = files_tree.getroot()

        self.rev = files_tree_root.get('rev')
        self.srcmd5 = files_tree_root.get('srcmd5')

        self.linkinfo = Linkinfo()
        self.linkinfo.read(files_tree_root.find('linkinfo'))

        self.filenamelist = []
        self.filelist = []
        for node in files_tree_root.findall('entry'):
            try: 
                f = File(node.get('name'), 
                         node.get('md5'), 
                         int(node.get('size')), 
                         int(node.get('mtime')))
            except: 
                # okay, a very old version of _files, which didn't contain any metadata yet... 
                f = File(node.get('name'), '', 0, 0)
            self.filelist.append(f)
            self.filenamelist.append(f.name)

        self.to_be_deleted = read_tobedeleted(self.dir)
        self.in_conflict = read_inconflict(self.dir)
        self.linkrepair = os.path.isfile(os.path.join(self.storedir, '_linkrepair'))

        # gather unversioned files, but ignore some stuff
        self.excluded = [ i for i in os.listdir(self.dir) 
                          for j in conf.config['exclude_glob']
                          if fnmatch.fnmatch(i, j) ]
        self.filenamelist_unvers = [ i for i in os.listdir(self.dir)
                                     if i not in self.excluded
                                     if i not in self.filenamelist ]

    def islink(self):
        """tells us if the package is a link (has 'linkinfo').  
        A package with linkinfo is a package which links to another package.
        Returns True if the package is a link, otherwise False."""
        return self.linkinfo.islink()

    def isexpanded(self):
        """tells us if the package is a link which is expanded.  
        Returns True if the package is expanded, otherwise False."""
        return self.linkinfo.isexpanded()

    def islinkrepair(self):
        """tells us if we are repairing a broken source link."""
        return self.linkrepair

    def haslinkerror(self):
        """
        Returns True if the link is broken otherwise False.
        If the package is not a link it returns False.
        """
        return self.linkinfo.haserror()

    def linkerror(self):
        """
        Returns an error message if the link is broken otherwise None.
        If the package is not a link it returns None.
        """
        return self.linkinfo.error

    def update_local_pacmeta(self):
        """
        Update the local _meta file in the store.
        It is replaced with the version pulled from upstream.
        """
        meta = ''.join(show_package_meta(self.apiurl, self.prjname, self.name))
        f = open(os.path.join(self.storedir, '_meta'), 'w')
        f.write(meta)
        f.close()

    def findfilebyname(self, n):
        for i in self.filelist:
            if i.name == n:
                return i

    def status(self, n):
        """
        status can be:

         file  storefile  file present  STATUS
        exists  exists      in _files

          x       x            -        'A'
          x       x            x        ' ' if digest differs: 'M'
                                            and if in conflicts file: 'C'
          x       -            -        '?'
          x       -            x        'D' and listed in _to_be_deleted
          -       x            x        '!'
          -       x            -        'D' (when file in working copy is already deleted)
          -       -            x        'F' (new in repo, but not yet in working copy)
          -       -            -        NOT DEFINED

        """

        known_by_meta = False
        exists = False
        exists_in_store = False
        if n in self.filenamelist:
            known_by_meta = True
        if os.path.exists(os.path.join(self.absdir, n)):
            exists = True
        if os.path.exists(os.path.join(self.storedir, n)):
            exists_in_store = True


        if exists and not exists_in_store and known_by_meta:
            state = 'D'
        elif n in self.to_be_deleted:
            state = 'D'
        elif n in self.in_conflict:
            state = 'C'
        elif exists and exists_in_store and known_by_meta:
            #print self.findfilebyname(n)
            if dgst(os.path.join(self.absdir, n)) != self.findfilebyname(n).md5:
                state = 'M'
            else:
                state = ' '
        elif exists and not exists_in_store and not known_by_meta:
            state = '?'
        elif exists and exists_in_store and not known_by_meta:
            state = 'A'
        elif not exists and exists_in_store and known_by_meta:
            state = '!'
        elif not exists and not exists_in_store and known_by_meta:
            state = 'F'
        elif not exists and exists_in_store and not known_by_meta:
            state = 'D'
        elif not exists and not exists_in_store and not known_by_meta:
            # this case shouldn't happen (except there was a typo in the filename etc.)
            raise IOError('osc: \'%s\' is not under version control' % n)
        
        return state

    def comparePac(self, cmp_pac):
        """
        This method compares the local filelist with
        the filelist of the passed package to see which files
        were added, removed and changed.
        """
        
        changed_files = []
        added_files = []
        removed_files = []

        for file in self.filenamelist+self.filenamelist_unvers:
            state = self.status(file)
            if state == 'A' and (not file in cmp_pac.filenamelist):
                added_files.append(file)
            elif file in cmp_pac.filenamelist and state == 'D':
                removed_files.append(file)
            elif state == ' ' and not file in cmp_pac.filenamelist:
                added_files.append(file)
            elif file in cmp_pac.filenamelist and state != 'A' and state != '?':
                if dgst(os.path.join(self.absdir, file)) != cmp_pac.findfilebyname(file).md5:
                    changed_files.append(file)
        for file in cmp_pac.filenamelist:
            if not file in self.filenamelist:
                removed_files.append(file)
        removed_files = set(removed_files)

        return changed_files, added_files, removed_files

    def merge(self, otherpac):
        self.todo += otherpac.todo

    def __str__(self):
        r = """
name: %s
prjname: %s
workingdir: %s
localfilelist: %s
linkinfo: %s
rev: %s
'todo' files: %s
""" % (self.name, 
        self.prjname, 
        self.dir, 
        '\n               '.join(self.filenamelist), 
        self.linkinfo, 
        self.rev, 
        self.todo)

        return r


    def read_meta_from_spec(self, spec = None):
        import glob
        if spec:
            specfile = spec
        else:
            # scan for spec files
            speclist = glob.glob(os.path.join(self.dir, '*.spec'))
            if len(speclist) == 1:
                specfile = speclist[0]
            elif len(speclist) > 1:
                print 'the following specfiles were found:'
                for file in speclist:
                    print file
                print 'please specify one with --specfile'
                sys.exit(1)
            else:
                print 'no specfile was found - please specify one ' \
                      'with --specfile'
                sys.exit(1)     

        data = read_meta_from_spec(specfile, 'Summary', 'Url', '%description')
        self.summary = data['Summary']
        self.url = data['Url']
        self.descr = data['%description']


    def update_package_meta(self, force=False):
        """
        for the updatepacmetafromspec subcommand
            argument force supress the confirm question
        """

        m = ''.join(show_package_meta(self.apiurl, self.prjname, self.name))

        tree = ET.fromstring(m)
        tree.find('title').text = self.summary
        tree.find('description').text = ''.join(self.descr)
        url = tree.find('url')
        if url == None:
            url = ET.SubElement(tree, 'url')
        url.text = self.url
        
        u = makeurl(self.apiurl, ['source', self.prjname, self.name, '_meta'])
        mf = metafile(u, ET.tostring(tree))

        if not force:
            print '*' * 36, 'old', '*' * 36
            print m
            print '*' * 36, 'new', '*' * 36
            print ET.tostring(tree)
            print '*' * 72
            repl = raw_input('Write? (y/N/e) ')
        else:
            repl = 'y'

        if repl == 'y':
            mf.sync()
        elif repl == 'e':
            mf.edit()

        mf.discard()

    def latest_rev(self):
        if self.islinkrepair():
            upstream_rev = show_upstream_xsrcmd5(self.apiurl, self.prjname, self.name, linkrepair=1)
        elif self.islink() and self.isexpanded():
            upstream_rev = show_upstream_xsrcmd5(self.apiurl, self.prjname, self.name)
        else:
            upstream_rev = show_upstream_rev(self.apiurl, self.prjname, self.name)
        return upstream_rev

    def update(self, rev = None, service_files = False):
        # save filelist and (modified) status before replacing the meta file
        saved_filenames = self.filenamelist
        saved_modifiedfiles = [ f for f in self.filenamelist if self.status(f) == 'M' ]

        oldp = self
        self.update_local_filesmeta(rev)
        self = Package(self.dir)

        # which files do no longer exist upstream?
        disappeared = [ f for f in saved_filenames if f not in self.filenamelist ]

        pathn = getTransActPath(self.dir)

        for filename in saved_filenames:
            if not filename.startswith('_service:') and filename in disappeared:
                print statfrmt('D', os.path.join(pathn, filename))
                # keep file if it has local modifications
                if oldp.status(filename) == ' ':
                    self.delete_localfile(filename)
                self.delete_storefile(filename)

        for filename in self.filenamelist:

            state = self.status(filename)
            if not service_files and filename.startswith('_service:'):
                pass
            elif state == 'M' and self.findfilebyname(filename).md5 == oldp.findfilebyname(filename).md5:
                # no merge necessary... local file is changed, but upstream isn't
                pass
            elif state == 'M' and filename in saved_modifiedfiles:
                status_after_merge = self.mergefile(filename)
                print statfrmt(status_after_merge, os.path.join(pathn, filename))
            elif state == 'M':
                self.updatefile(filename, rev)
                print statfrmt('U', os.path.join(pathn, filename))
            elif state == '!':
                self.updatefile(filename, rev)
                print 'Restored \'%s\'' % os.path.join(pathn, filename)
            elif state == 'F':
                self.updatefile(filename, rev)
                print statfrmt('A', os.path.join(pathn, filename))
            elif state == 'D' and self.findfilebyname(filename).md5 != oldp.findfilebyname(filename).md5:
                self.updatefile(filename, rev)
                self.delete_storefile(filename)
                print statfrmt('U', os.path.join(pathn, filename))
            elif state == ' ':
                pass

        self.update_local_pacmeta()

        #print ljust(p.name, 45), 'At revision %s.' % p.rev
        print 'At revision %s.' % self.rev

        if not service_files:
           self.run_source_services()

    def run_source_services(self):
        if self.filenamelist.count('_service'):
           service = ET.parse(os.path.join(self.absdir, '_service')).getroot()
           si = Serviceinfo()
           si.read(service)
           si.execute(self.absdir)

    def prepare_filelist(self):
        """Prepare a list of files, which will be processed by process_filelist
        method. This allows easy modifications of a file list in commit
        phase.
        """
        if not self.todo:
            self.todo = self.filenamelist + self.filenamelist_unvers
        self.todo.sort()

        ret = ""
        for f in (f for f in self.todo if not os.path.isdir(f)):
            action = 'leave'
            status = self.status(f)
            if status == '!':
                action = 'remove'
            ret += "%s %s %s\n" % (action, status, f)

        ret += """
# Edit a filelist for package %s
# Commands:
# l, leave = leave a file as is
# r, remove = remove a file
# a, add   = add a file
#
# If you remove file from a list, it will be unchanged
# If you remove all, commit will be aborted"""

        return ret

    def edit_filelist(self):
        """Opens a package list in editor for eediting. This allows easy
        modifications of it just by simple text editing
        """
        
        import tempfile
        tempdir = '/tmp'
        if sys.platform[:3] == 'win':
            tempdir = os.getenv('TEMP')
        
        (fd, filename) = tempfile.mkstemp(prefix = 'osc-filelist', suffix = '.txt', dir = tempdir)
        f = os.fdopen(fd, 'w')
        f.write(self.prepare_filelist())
        f.close()
        mtime_orig = os.stat(filename).st_mtime

        if sys.platform[:3] != 'win':
            editor = os.getenv('EDITOR', default='vim')
        else:
            editor = os.getenv('EDITOR', default='notepad')
        while 1:
            subprocess.call('%s %s' % (editor, filename), shell=True)
            mtime = os.stat(filename).st_mtime
            if mtime_orig < mtime:
                filelist = open(filename).readlines()
                os.unlink(filename)
                break
            else:
                raise oscerr.UserAbort()

        return self.process_filelist(filelist)

    def process_filelist(self, filelist):
        """Process a filelist - it add/remove or leave files. This depends on
        user input. If no file is processed, it raises an ValueError
        """

        loop = False
        for line in (l.strip() for l in filelist if (l[0] != "#" or l.strip() != '')):

            foo = line.split(' ')
            if len(foo) == 4:
                action, state, name = (foo[0], ' ', foo[3])
            elif len(foo) == 3:
                action, state, name = (foo[0], foo[1], foo[2])
            else:
                break
            action = action.lower()
            loop = True

            if action in ('r', 'remove'):
                if self.status(name) == '?':
                    os.unlink(name)
                    if name in self.todo:
                        self.todo.remove(name)
                else:
                    self.delete_file(name, True)
            elif action in ('a', 'add'):
                if self.status(name) != '?':
                    print "Cannot add file %s with state %s, skipped" % (name, self.status(name))
                else:
                    self.addfile(name)
            elif action in ('l', 'leave'):
                pass
            else:
                raise ValueError("Unknow action `%s'" % action)

        if not loop:
            raise ValueError("Empty filelist")

class RequestState:
    """for objects to represent the "state" of a request"""
    def __init__(self, name=None, who=None, when=None, comment=None):
        self.name = name
        self.who  = who
        self.when = when
        self.comment = comment

class Action:
    """represents an action"""
    def __init__(self, type, src_project, src_package, src_rev, dst_project, dst_package, src_update):
        self.type = type
        self.src_project = src_project
        self.src_package = src_package
        self.src_rev = src_rev
        self.dst_project = dst_project
        self.dst_package = dst_package
        self.src_update = src_update

class Request:
    """represent a request and holds its metadata
       it has methods to read in metadata from xml,
       different views, ..."""
    def __init__(self):
        self.reqid       = None
        self.state       = RequestState()
        self.who         = None
        self.when        = None
        self.last_author = None
        self.descr       = None
        self.actions     = []
        self.statehistory = []

    def read(self, root):
        self.reqid = int(root.get('id'))
        actions = root.findall('action')
        if len(actions) == 0:
            actions = [ root.find('submit') ] # for old style requests

        for action in actions:
            type = action.get('type', 'submit')
            try:
                src_prj = src_pkg = src_rev = dst_prj = dst_pkg = src_update = None
                if action.findall('source'):
                   n = action.find('source')
                   src_prj = n.get('project', None)
                   src_pkg = n.get('package', None)
                   src_rev = n.get('rev', None)
                if action.findall('target'):
                   n = action.find('target')
                   dst_prj = n.get('project', None)
                   dst_pkg = n.get('package', None)
                if action.findall('options'):
                   n = action.find('options')
                   if n.findall('sourceupdate'):
                      src_update = n.find('sourceupdate').text.strip()
                self.add_action(type, src_prj, src_pkg, src_rev, dst_prj, dst_pkg, src_update)
            except:
                msg = 'invalid request format:\n%s' % ET.tostring(root)
                raise oscerr.APIError(msg)

        # read the state
        n = root.find('state')
        self.state.name, self.state.who, self.state.when \
                = n.get('name'), n.get('who'), n.get('when')
        try:
            self.state.comment = n.find('comment').text.strip()
        except:
            self.state.comment = None

        # read the state history
        for h in root.findall('history'):
            s = RequestState()
            s.name = h.get('name')
            s.who  = h.get('who')
            s.when = h.get('when')
            try:
                s.comment = h.find('comment').text.strip()
            except:
                s.comment = None
            self.statehistory.append(s)
        self.statehistory.reverse()

        # read a description, if it exists
        try:
            n = root.find('description').text
            self.descr = n
        except:
            pass

    def add_action(self, type, src_prj, src_pkg, src_rev, dst_prj, dst_pkg, src_update):
        self.actions.append(Action(type, src_prj, src_pkg, src_rev,
                                   dst_prj, dst_pkg, src_update)
                           )

    def list_view(self):
        ret = '%6d  State:%-7s By:%-12s When:%-12s' % (self.reqid, self.state.name, self.state.who, self.state.when)

        for a in self.actions:
           dst = "%s/%s" % (a.dst_project, a.dst_package)
           if a.src_package == a.dst_package:
              dst = a.dst_project

           sr_source=""
           if a.type=="submit":
              sr_source="%s/%s  -> " % (a.src_project, a.src_package)
           if a.type=="change_devel":
              dst = "developed in %s/%s" % (a.src_project, a.src_package)
              sr_source="%s/%s" % (a.dst_project, a.dst_package)

           ret += '\n        %s:       %-50s %-20s   ' % \
            (a.type, sr_source, dst)

        if self.statehistory and self.statehistory[0]:
            who = []
            for h in self.statehistory:
                who.append("%s(%s)" % (h.who,h.name))
            who.reverse()
            ret += "\n        From: %s" % (' -> '.join(who))
        if self.descr:
            ret += "\n        Descr: %s" % (repr(self.descr))
        ret += "\n"

        return ret

    def __cmp__(self, other):
        return cmp(self.reqid, other.reqid)

    def __str__(self):
        action_list=""
        for action in self.actions:
            action_list="  %s:  " % (action.type)
            if action.type=="submit":
               r=""
               if action.src_rev:
                   r="(r%s)" % (action.src_rev)
               m=""
               if action.src_update:
                   m="(%s)" % (action.src_update)
               action_list=action_list+" %s/%s%s%s -> %s" % ( action.src_project, action.src_package, r, m, action.dst_project )
               if action.dst_package:
                   action_list=action_list+"/%s" % ( action.dst_package )
            elif action.type=="delete":
               action_list=action_list+"  %s" % ( action.dst_project )
               if action.dst_package:
                   action_list=action_list+"/%s" % ( action.dst_package )
            elif action.type=="change_devel":
               action_list=action_list+" %s/%s developed in %s/%s" % \
                           ( action.dst_project, action.dst_package, action.src_project, action.src_package )
            action_list=action_list+"\n"

        s = """\
Request #%s: 

%s

Message:
    %s

State:   %-10s   %s %s
Comment: %s
"""          % (self.reqid,
               action_list,
               self.descr,
               self.state.name, self.state.when, self.state.who,
               self.state.comment)

        if len(self.statehistory):
            histitems = [ '%-10s   %s %s' \
                    % (i.name, i.when, i.who) \
                    for i in self.statehistory ]
            s += 'History: ' + '\n         '.join(histitems)

        s += '\n'
        return s


def shorttime(t):
    """format time as Apr 02 18:19
    or                Apr 02  2005
    depending on whether it is in the current year
    """
    import time

    if time.localtime()[0] == time.localtime(t)[0]:
        # same year
        return time.strftime('%b %d %H:%M',time.localtime(t))
    else:
        return time.strftime('%b %d  %Y',time.localtime(t))


def is_project_dir(d):
    return os.path.exists(os.path.join(d, store, '_project')) and not \
           os.path.exists(os.path.join(d, store, '_package'))

        
def is_package_dir(d):
    return os.path.exists(os.path.join(d, store, '_project')) and \
           os.path.exists(os.path.join(d, store, '_package'))

def parse_disturl(disturl):
    """Parse a disturl, returns tuple (apiurl, project, source, repository,
    revision), else raises an oscerr.WrongArgs exception
    """

    m = DISTURL_RE.match(disturl)
    if not m:
        raise oscerr.WrongArgs("`%s' does not look like disturl")

    apiurl = m.group('apiurl')
    if apiurl.split('.')[0] != 'api':
        apiurl = 'https://api.' + ".".join(apiurl.split('.')[1:])
    return (apiurl, m.group('project'), m.group('source'), m.group('repository'), m.group('revision'))

        
def slash_split(l):
    """Split command line arguments like 'foo/bar' into 'foo' 'bar'.
    This is handy to allow copy/paste a project/package combination in this form.

    Trailing slashes are removed before the split, because the split would 
    otherwise give an additional empty string.
    """
    r = []
    for i in l:
        i = i.rstrip('/')
        r += i.split('/')
    return r


def findpacs(files):
    """collect Package objects belonging to the given files
    and make sure each Package is returned only once"""
    pacs = []
    for f in files:
        p = filedir_to_pac(f)
        known = None
        for i in pacs:
            if i.name == p.name:
                known = i
                break
        if known:
            i.merge(p)
        else:
            pacs.append(p)
    return pacs
        

def read_filemeta(dir):
    try:
        r = ET.parse(os.path.join(dir, store, '_files'))
    except SyntaxError, e:
        raise oscerr.NoWorkingCopy('\'%s\' is not a valid working copy.\n'
                                   'When parsing .osc/_files, the following error was encountered:\n'
                                   '%s' % (dir, e))
    return r


def read_tobedeleted(dir):
    r = []
    fname = os.path.join(dir, store, '_to_be_deleted')

    if os.path.exists(fname):
        r = [ line.strip() for line in open(fname) ]

    return r


def read_inconflict(dir):
    r = []
    fname = os.path.join(dir, store, '_in_conflict')

    if os.path.exists(fname):
        r = [ line.strip() for line in open(fname) ]

    return r


def parseargs(list_of_args):
    """Convenience method osc's commandline argument parsing.
    
    If called with an empty tuple (or list), return a list containing the current directory.
    Otherwise, return a list of the arguments."""
    if list_of_args:
        return list(list_of_args)
    else:
        return [os.curdir]


def filedir_to_pac(f):
    """Takes a working copy path, or a path to a file inside a working copy, 
    and returns a Package object instance
    
    If the argument was a filename, add it onto the "todo" list of the Package """

    if os.path.isdir(f):
        wd = f
        p = Package(wd)

    else:
        wd = os.path.dirname(f)
        if wd == '':
            wd = os.curdir
        p = Package(wd)
        p.todo = [ os.path.basename(f) ]

    return p


def statfrmt(statusletter, filename):
    return '%s    %s' % (statusletter, filename)


def pathjoin(a, *p):
    """Join two or more pathname components, inserting '/' as needed. Cut leading ./"""
    path = os.path.join(a, *p)
    if path.startswith('./'):
        path = path[2:]
    return path


def makeurl(baseurl, l, query=[]):
    """Given a list of path compoments, construct a complete URL.

    Optional parameters for a query string can be given as a list, as a
    dictionary, or as an already assembled string.
    In case of a dictionary, the parameters will be urlencoded by this
    function. In case of a list not -- this is to be backwards compatible.
    """

    #print 'makeurl:', baseurl, l, query

    if type(query) == type(list()):
        query = '&'.join(query)
    elif type(query) == type(dict()):
        query = urlencode(query)

    scheme, netloc = urlsplit(baseurl)[0:2]
    return urlunsplit((scheme, netloc, '/'.join(l), query, ''))               


def http_request(method, url, headers={}, data=None, file=None, timeout=100):
    """wrapper around urllib2.urlopen for error handling,
    and to support additional (PUT, DELETE) methods"""

    filefd = None

    if conf.config['http_debug']:
        print 
        print
        print '--', method, url

    if method == 'POST' and not file and not data:
        # adding data to an urllib2 request transforms it into a POST
        data = ''
        
    req = urllib2.Request(url)

    api_host_options=conf.get_apiurl_api_host_options(url)

    for header, value in api_host_options['http_headers']:
        req.add_header(header, value)

    req.get_method = lambda: method

    # POST requests are application/x-www-form-urlencoded per default
    # since we change the request into PUT, we also need to adjust the content type header
    if method == 'PUT' or (method == 'POST' and data):
        req.add_header('Content-Type', 'application/octet-stream')

    if type(headers) == type({}):
        for i in headers.keys():
            print headers[i]
            req.add_header(i, headers[i])

    if file and not data:
        size = os.path.getsize(file)
        if size < 1024*512:
            data = open(file, 'rb').read()
        else:
            import mmap
            filefd = open(file, 'rb')
            try:
                if sys.platform[:3] != 'win':
                    data = mmap.mmap(filefd.fileno(), os.path.getsize(file), mmap.MAP_SHARED, mmap.PROT_READ)
                else:
                    data = mmap.mmap(filefd.fileno(), os.path.getsize(file))
                data = buffer(data)
            except EnvironmentError, e:
                if e.errno == 19:
                    sys.exit('\n\n%s\nThe file \'%s\' could not be memory mapped. It is ' \
                             '\non a filesystem which does not support this.' % (e, file))
                elif hasattr(e, 'winerror') and e.winerror == 5:
                    # falling back to the default io
                    data = open(file, 'rb').read()
                else:
                    raise

    if conf.config['debug']: print method, url

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        fd = urllib2.urlopen(req, data=data)
    finally:
        socket.setdefaulttimeout(old_timeout)
        if hasattr(conf.cookiejar, 'save'):
            conf.cookiejar.save(ignore_discard=True)

    if filefd: filefd.close()

    return fd


def http_GET(*args, **kwargs):    return http_request('GET', *args, **kwargs)
def http_POST(*args, **kwargs):   return http_request('POST', *args, **kwargs)
def http_PUT(*args, **kwargs):    return http_request('PUT', *args, **kwargs)
def http_DELETE(*args, **kwargs): return http_request('DELETE', *args, **kwargs)


def init_project_dir(apiurl, dir, project):
    if not os.path.exists(dir):
        if conf.config['checkout_no_colon']:
            os.makedirs(dir)      # helpful with checkout_no_colon
        else:
            os.mkdir(dir)
    if not os.path.exists(os.path.join(dir, store)):
        os.mkdir(os.path.join(dir, store))

    # print 'project=',project,'  dir=',dir
    store_write_project(dir, project)
    store_write_apiurl(dir, apiurl)
    if conf.config['do_package_tracking']:
        store_write_initial_packages(dir, project, [])

def init_package_dir(apiurl, project, package, dir, revision=None, files=True):
    if not os.path.isdir(store):
        os.mkdir(store)
    os.chdir(store)
    f = open('_project', 'w')
    f.write(project + '\n')
    f.close
    f = open('_package', 'w')
    f.write(package + '\n')
    f.close

    if files:
        f = open('_files', 'w')
        f.write(''.join(show_files_meta(apiurl, project, package, revision=revision)))
        f.close()
    else:
        # create dummy
        ET.ElementTree(element=ET.Element('directory')).write('_files')

    f = open('_osclib_version', 'w')
    f.write(__store_version__ + '\n')
    f.close()

    store_write_apiurl(os.path.pardir, apiurl)

    os.chdir(os.pardir)
    return


def check_store_version(dir):
    versionfile = os.path.join(dir, store, '_osclib_version')
    try:
        v = open(versionfile).read().strip()
    except:
        v = ''

    if v == '':
        msg = 'Error: "%s" is not an osc working copy.' % os.path.abspath(dir)
        if os.path.exists(os.path.join(dir, '.svn')):
            msg = msg + '\nTry svn instead of osc.'
        raise oscerr.NoWorkingCopy(msg)

    if v != __store_version__:
        if v in ['0.2', '0.3', '0.4', '0.5', '0.6', '0.7', '0.8', '0.9', '0.95', '0.96', '0.97', '0.98', '0.99']:
            # version is fine, no migration needed
            f = open(versionfile, 'w')
            f.write(__store_version__ + '\n')
            f.close()
            return 
        msg = 'The osc metadata of your working copy "%s"' % dir
        msg += '\nhas __store_version__ = %s, but it should be %s' % (v, __store_version__)
        msg += '\nPlease do a fresh checkout or update your client. Sorry about the inconvenience.'
        raise oscerr.WorkingCopyWrongVersion, msg
    

def meta_get_packagelist(apiurl, prj):

    u = makeurl(apiurl, ['source', prj])
    f = http_GET(u)
    root = ET.parse(f).getroot()
    return [ node.get('name') for node in root.findall('entry') ]


def meta_get_filelist(apiurl, prj, package, verbose=False, expand=False, revision=None):
    """return a list of file names,
    or a list File() instances if verbose=True"""

    query = {}
    if expand:
        query['expand'] = 1
    if revision:
        query['rev'] = revision
    else:
        query['rev'] = 'latest'

    u = makeurl(apiurl, ['source', prj, package], query=query)
    f = http_GET(u)
    root = ET.parse(f).getroot()

    if not verbose:
        return [ node.get('name') for node in root.findall('entry') ]

    else:
        l = []
        # rev = int(root.get('rev'))    # don't force int. also allow srcmd5 here.
        rev = root.get('rev')
        for node in root.findall('entry'):
            f = File(node.get('name'), 
                     node.get('md5'), 
                     int(node.get('size')), 
                     int(node.get('mtime')))
            f.rev = rev
            l.append(f)
        return l


def meta_get_project_list(apiurl):
    u = makeurl(apiurl, ['source'])
    f = http_GET(u)
    root = ET.parse(f).getroot()
    return sorted([ node.get('name') for node in root ])


def show_project_meta(apiurl, prj):
    url = makeurl(apiurl, ['source', prj, '_meta'])
    f = http_GET(url)
    return f.readlines()


def show_project_conf(apiurl, prj):
    url = makeurl(apiurl, ['source', prj, '_config'])
    f = http_GET(url)
    return f.readlines()


def show_package_meta(apiurl, prj, pac):
    url = makeurl(apiurl, ['source', prj, pac, '_meta'])
    try:
        f = http_GET(url)
        return f.readlines()
    except urllib2.HTTPError, e:
        e.osc_msg = 'Error getting meta for project \'%s\' package \'%s\'' % (prj, pac)
        raise


def show_develproject(apiurl, prj, pac):
    m = show_package_meta(apiurl, prj, pac)
    try:
        return ET.parse(StringIO(''.join(m))).getroot().find('devel').get('project')
    except:
        return None


def show_pattern_metalist(apiurl, prj):
    url = makeurl(apiurl, ['source', prj, '_pattern'])
    try:
        f = http_GET(url)
        tree = ET.parse(f)
    except urllib2.HTTPError, e:
        e.osc_msg = 'show_pattern_metalist: Error getting pattern list for project \'%s\'' % prj
        raise
    r = [ node.get('name') for node in tree.getroot() ]
    r.sort()
    return r


def show_pattern_meta(apiurl, prj, pattern):
    url = makeurl(apiurl, ['source', prj, '_pattern', pattern])
    try:
        f = http_GET(url)
        return f.readlines()
    except urllib2.HTTPError, e:
        e.osc_msg = 'show_pattern_meta: Error getting pattern \'%s\' for project \'%s\'' % (pattern, prj)
        raise


class metafile:
    """metafile that can be manipulated and is stored back after manipulation."""
    def __init__(self, url, input, change_is_required=False, file_ext='.xml'):
        import tempfile

        self.url = url
        self.change_is_required = change_is_required

        tempdir = '/tmp'
        if sys.platform[:3] == 'win':
            tempdir = os.getenv('TEMP')
        (fd, self.filename) = tempfile.mkstemp(prefix = 'osc_metafile.', suffix = file_ext, dir = tempdir)

        f = os.fdopen(fd, 'w')
        f.write(''.join(input))
        f.close()

        self.hash_orig = dgst(self.filename)

    def sync(self):
        hash = dgst(self.filename)
        if self.change_is_required == True and hash == self.hash_orig:
            print 'File unchanged. Not saving.'
            os.unlink(self.filename)
            return True

        print 'Sending meta data...'
        # don't do any exception handling... it's up to the caller what to do in case
        # of an exception
        http_PUT(self.url, file=self.filename)
        os.unlink(self.filename)
        print 'Done.'
        return True

    def edit(self):
        if sys.platform[:3] != 'win':
            editor = os.getenv('EDITOR', default='vim')
        else:
            editor = os.getenv('EDITOR', default='notepad')
        while 1:
            subprocess.call('%s %s' % (editor, self.filename), shell=True)
            if self.change_is_required == True:
                try:
                    self.sync()
                except urllib2.HTTPError, e:
                    error_help = "%d" % e.code
                    if e.headers.get('X-Opensuse-Errorcode'):
                        error_help = "%s (%d)" % (e.headers.get('X-Opensuse-Errorcode'), e.code)

                    print >>sys.stderr, 'BuildService API error:', error_help
                    # examine the error - we can't raise an exception because we might want
                    # to try again
                    data = e.read()
                    if '<summary>' in data:
                        print >>sys.stderr, data.split('<summary>')[1].split('</summary>')[0]
                    input = raw_input('Try again? ([y/N]): ')
                    if input != 'y' and input != 'Y':
                        break
                else:
                    break
            else:
                self.sync()
                break
        self.discard()
        return self

    def discard(self):
        if os.path.exists(self.filename):
            print 'discarding', self.filename
            os.unlink(self.filename)
        return self
    

# different types of metadata
metatypes = { 'prj':     { 'path': 'source/%s/_meta',
                           'template': new_project_templ,
                           'file_ext': '.xml'
                         },
              'pkg':     { 'path'     : 'source/%s/%s/_meta',
                           'template': new_package_templ,
                           'file_ext': '.xml'
                         },
              'prjconf': { 'path': 'source/%s/_config',
                           'template': '',
                           'file_ext': '.txt'
                         },
              'user':    { 'path': 'person/%s',
                           'template': new_user_template,
                           'file_ext': '.xml'
                         },
              'pattern': { 'path': 'source/%s/_pattern/%s',
                           'template': new_pattern_template,
                           'file_ext': '.xml'
                         },
            }

def meta_exists(metatype,
                path_args=None,
                template_args=None,
                create_new=True,
                apiurl=None):

    if not apiurl:
        apiurl = conf.config['apiurl']
    url = make_meta_url(metatype, path_args, apiurl)
    try:
        data = http_GET(url).readlines()
    except urllib2.HTTPError, e:
        if e.code == 404 and create_new:
            data = metatypes[metatype]['template']
            if template_args:
                data = data % template_args
        else:
            raise e
    return data

def make_meta_url(metatype, path_args=None, apiurl=None):
    if not apiurl:
        apiurl = conf.config['apiurl']
    if metatype not in metatypes.keys():
        raise AttributeError('make_meta_url(): Unknown meta type \'%s\'' % metatype)
    path = metatypes[metatype]['path']

    if path_args:
        path = path % path_args

    return makeurl(apiurl, [path])


def edit_meta(metatype, 
              path_args=None, 
              data=None, 
              template_args=None, 
              edit=False,
              change_is_required=False,
              apiurl=None):

    if not apiurl:
        apiurl = conf.config['apiurl']
    if not data:
        data = meta_exists(metatype,
                           path_args,
                           template_args,
                           create_new=True,
                           apiurl=apiurl)

    if edit:
        change_is_required = True

    url = make_meta_url(metatype, path_args, apiurl)
    f=metafile(url, data, change_is_required, metatypes[metatype]['file_ext'])

    if edit:
        f.edit()
    else:
        f.sync()


def show_files_meta(apiurl, prj, pac, revision=None, expand=False, linkrev=None, linkrepair=False):
    query = {}
    if revision:
        query['rev'] = revision
    else:
        query['rev'] = 'latest'
    if linkrev:
        query['linkrev'] = linkrev
    if expand:
        query['expand'] = 1
    if linkrepair:
        query['emptylink'] = 1
    f = http_GET(makeurl(apiurl, ['source', prj, pac], query=query))
    return f.readlines()


def show_upstream_srcmd5(apiurl, prj, pac, expand=False, revision=None):
    m = show_files_meta(apiurl, prj, pac, expand=expand, revision=revision)
    return ET.parse(StringIO(''.join(m))).getroot().get('srcmd5')


def show_upstream_xsrcmd5(apiurl, prj, pac, revision=None, linkrev=None, linkrepair=False):
    m = show_files_meta(apiurl, prj, pac, revision=revision, linkrev=linkrev, linkrepair=linkrepair)
    try:
        # only source link packages have a <linkinfo> element.
        li_node = ET.parse(StringIO(''.join(m))).getroot().find('linkinfo')
    except:
        return None

    li = Linkinfo()
    li.read(li_node)

    if li.haserror():
        raise oscerr.LinkExpandError(prj, pac, li.error)
    return li.xsrcmd5


def show_upstream_rev(apiurl, prj, pac):
    m = show_files_meta(apiurl, prj, pac)
    return ET.parse(StringIO(''.join(m))).getroot().get('rev')


def read_meta_from_spec(specfile, *args):
    import codecs, locale, re
    """
    Read tags and sections from spec file. To read out
    a tag the passed argument mustn't end with a colon. To
    read out a section the passed argument must start with
    a '%'.
    This method returns a dictionary which contains the
    requested data.
    """

    if not os.path.isfile(specfile):
        raise IOError('\'%s\' is not a regular file' % specfile)

    try:
        lines = codecs.open(specfile, 'r', locale.getpreferredencoding()).readlines()
    except UnicodeDecodeError:
        lines = open(specfile).readlines()

    tags = []
    sections = []
    spec_data = {}

    for itm in args:
        if itm.startswith('%'):
            sections.append(itm)
        else:
            tags.append(itm)

    tag_pat = '(?P<tag>^%s)\s*:\s*(?P<val>.*)'
    for tag in tags:
        m = re.compile(tag_pat % tag, re.I | re.M).search(''.join(lines))
        if m and m.group('val'):
            spec_data[tag] = m.group('val').strip()
        else:
            print >>sys.stderr, 'error - tag \'%s\' does not exist' % tag
            sys.exit(1)

    section_pat = '^%s\s*?$'
    for section in sections:
        m = re.compile(section_pat % section, re.I | re.M).search(''.join(lines))
        if m:
            start = lines.index(m.group()+'\n') + 1
        else:
            print >>sys.stderr, 'error - section \'%s\' does not exist' % section
            sys.exit(1)
        data = []
        for line in lines[start:]:
            if line.startswith('%'):
                break
            data.append(line)
        spec_data[section] = data

    return spec_data


def edit_message(footer='', template=''):
    delim = '--This line, and those below, will be ignored--\n\n' + footer
    import tempfile
    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    (fd, filename) = tempfile.mkstemp(prefix = 'osc-commitmsg', suffix = '.diff', dir = tempdir)
    f = os.fdopen(fd, 'w')
    if template != '':
        f.write(template)
    f.write('\n')
    f.write(delim)
    f.close()
    mtime_orig = os.stat(filename).st_mtime

    if sys.platform[:3] != 'win':
        editor = os.getenv('EDITOR', default='vim')
    else:
        editor = os.getenv('EDITOR', default='notepad')
    while 1:
        subprocess.call('%s %s' % (editor, filename), shell=True)
        mtime = os.stat(filename).st_mtime
        
        if mtime_orig < mtime:
            msg = open(filename).read()
            os.unlink(filename)
            return msg.split(delim)[0].rstrip()
        else:
            input = raw_input('Log message unchanged or not specified\n'
                              'a)bort, c)ontinue, e)dit: ')
            if input in 'aA':
                os.unlink(filename)
                raise oscerr.UserAbort
            elif input in 'cC':
                os.unlink(filename)
                return ''
            elif input in 'eE':
                pass


def create_delete_request(apiurl, project, package, message):

    import cgi

    if package:
      package = """package="%s" """ % (package)
    else:
      package = ""

    xml = """\
<request>
    <action type="delete">
        <target project="%s" %s/>
    </action>
    <state name="new"/>
    <description>%s</description>
</request>
""" % (project, package,
       cgi.escape(message or ''))

    u = makeurl(apiurl, ['request'], query='cmd=create')
    f = http_POST(u, data=xml)

    root = ET.parse(f).getroot()
    return root.get('id')


def create_change_devel_request(apiurl, 
                                devel_project, devel_package, 
                                project, package,
                                message):

    import cgi
    xml = """\
<request>
    <action type="change_devel">
        <source project="%s" package="%s" />
        <target project="%s" package="%s" />
    </action>
    <state name="new"/>
    <description>%s</description>
</request>
""" % (devel_project, 
       devel_package,
       project, 
       package,
       cgi.escape(message or ''))

    u = makeurl(apiurl, ['request'], query='cmd=create')
    f = http_POST(u, data=xml)

    root = ET.parse(f).getroot()
    return root.get('id')


def create_submit_request(apiurl, 
                         src_project, src_package, 
                         dst_project, dst_package,
                         message, orev=None, src_update=None):

    import cgi
    options_block=""
    if src_update:
       options_block="""<options><sourceupdate>%s</sourceupdate></options> """ % (src_update)

    # XXX: keep the old template for now in order to work with old obs instances
    xml = """\
<request type="submit">
    <submit>
        <source project="%s" package="%s" rev="%s"/>
        <target project="%s" package="%s" />
        %s
    </submit>
    <state name="new"/>
    <description>%s</description>
</request>
""" % (src_project, 
       src_package,
       orev or show_upstream_rev(apiurl, src_project, src_package),
       dst_project, 
       dst_package,
       options_block,
       cgi.escape(message or ''))

    u = makeurl(apiurl, ['request'], query='cmd=create')
    f = http_POST(u, data=xml)

    root = ET.parse(f).getroot()
    return root.get('id')


def get_request(apiurl, reqid):
    u = makeurl(apiurl, ['request', reqid])
    f = http_GET(u)
    root = ET.parse(f).getroot()

    r = Request()
    r.read(root)
    return r


def change_request_state(apiurl, reqid, newstate, message=''):
    u = makeurl(apiurl, 
                ['request', reqid], 
                query={'cmd': 'changestate', 'newstate': newstate})
    f = http_POST(u, data=message)
    return f.read()


def get_request_list(apiurl, project, package, req_who='', req_state=('new',), req_type=None ):
    requests = []

    matches = []
    match = ''
    m = ''
    if not "all" in req_state:
       for state in req_state:
           if len(m): m += '%20or%20'
           m += 'state/@name=\'%s\'' % quote_plus(state)
       if len(m): match += "(" + m + ")"
    m = ''
    if req_who:
        if len(m): m += '%20and%20'
        m += 'state/@who=\'%s\'' % quote_plus(req_who)
        m += '%20or%20'
        m += 'history/@who=\'%s\'' % quote_plus(req_who)
    if len(m):
        if len(match): match += "%20and%20"
        match += "(" + m + ")"

    # XXX: we cannot use the '|' in the xpath expression because it is not supported
    #      in the backend
    if project or package:
        for what in ['action', 'submit']:
            m = match
            if project:
                if len(m): m += '%20and%20'
                m += '(%s/target/@project=\'%s\'%%20or%%20' % (what, quote_plus(project))
                m +=  '%s/source/@project=\'%s\')' % (what, quote_plus(project))
            if package:
                if len(m): m += '%20and%20'
                m += '(%s/target/@package=\'%s\'%%20or%%20' % (what, quote_plus(package))
                m +=  '%s/source/@package=\'%s\')' % (what, quote_plus(package))
            if req_type:
                if len(m): m += '%20and%20'
                m += '%s/@type=\'%s\'' % (what, quote_plus(req_type))

            matches.append(m)
    else:
        matches.append(match)

    for match in matches:
        if conf.config['verbose'] > 1:
            print "[",match,"]"
        u = makeurl(apiurl, ['search', 'request'], ['match=%s' % match])
        f = http_GET(u)
        collection = ET.parse(f).getroot()

        for root in collection.findall('request'):
            r = Request()
            r.read(root)
            requests.append(r)

    return requests


def get_request_log(apiurl, reqid):
    r = get_request(conf.config['apiurl'], reqid)
    data = []
    frmt = '-' * 76 + '\n%s | %s | %s\n\n%s'
    # the description of the request is used for the initial log entry
    # otherwise its comment attribute would contain None
    if len(r.statehistory) >= 1:
        r.statehistory[-1].comment = r.descr
    else:
        r.state.comment = r.descr
    for state in [ r.state ] + r.statehistory:
        s = frmt % (state.name, state.who, state.when, str(state.comment))
        data.append(s)
    return data


def get_user_meta(apiurl, user):
    u = makeurl(apiurl, ['person', quote_plus(user)])
    try:
        f = http_GET(u)
        return ''.join(f.readlines())
    except urllib2.HTTPError:
        print 'user \'%s\' not found' % user
        return None


def get_user_data(apiurl, user, *tags):
    """get specified tags from the user meta"""
    meta = get_user_meta(apiurl, user)
    data = []
    if meta != None:
        root = ET.fromstring(meta)
        for tag in tags:
            try:
                if root.find(tag).text != None:
                    data.append(root.find(tag).text)
                else:
                    # tag is empty
                    data.append('-')
            except AttributeError:
                # this part is reached if the tags tuple contains an invalid tag
                print 'The xml file for user \'%s\' seems to be broken' % user
                return None
        return data
    else:
        return None


def get_source_file(apiurl, prj, package, filename, targetfilename=None, revision = None):
    query = None
    if revision:
        query = { 'rev': revision }

    o = open(targetfilename or filename, 'wb')
    u = makeurl(apiurl, ['source', prj, package, pathname2url(filename)], query=query)
    for buf in streamfile(u, http_GET, BUFSIZE):
        o.write(buf)
    o.close()


def get_binary_file(apiurl, prj, repo, arch, 
                    filename, 
                    package = None,
                    target_filename = None, 
                    target_mtime = None,
                    progress_meter = False):

    target_filename = target_filename or filename

    where = package or '_repository'
    u = makeurl(apiurl, ['build', prj, repo, arch, where, filename])

    if progress_meter:
        sys.stdout.write("Downloading %s [  0%%]" % filename)
        sys.stdout.flush()

    f = http_GET(u)
    binsize = int(f.headers['content-length'])

    import tempfile
    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    (fd, tmpfilename) = tempfile.mkstemp(prefix = filename + '.', suffix = '.osc', dir = tempdir)
    os.chmod(tmpfilename, 0644)

    try:
        o = os.fdopen(fd, 'wb')

        downloaded = 0
        while 1:
            #buf = f.read(BUFSIZE)
            buf = f.read(16384)
            if not buf: break
            o.write(buf)
            downloaded += len(buf)
            if progress_meter:
                completion = str(int((float(downloaded)/binsize)*100))
                sys.stdout.write('%s%*s%%]' % ('\b'*5, 3, completion))
                sys.stdout.flush()
        o.close()

        if progress_meter:
            sys.stdout.write('\n')

        shutil.move(tmpfilename, target_filename)
        if target_mtime:
            os.utime(target_filename, (-1, target_mtime))

    # make sure that the temp file is cleaned up when we are interrupted 
    finally:
        try: os.unlink(tmpfilename)
        except: pass

def dgst_from_string(str):
    # Python 2.5 depracates the md5 modules
    # Python 2.4 doesn't have hashlib yet
    try:
        import hashlib
        md5_hash = hashlib.md5()
    except ImportError:
        import md5
        md5_hash = md5.new()
    md5_hash.update(str)
    return md5_hash.hexdigest()

def dgst(file):

    #if not os.path.exists(file):
        #return None

    try:
        import hashlib
        md5 = hashlib
    except ImportError:
        import md5
        md5 = md5
    s = md5.md5()
    f = open(file, 'rb')
    while 1:
        buf = f.read(BUFSIZE)
        if not buf: break
        s.update(buf)
    return s.hexdigest()
    f.close()


def binary(s):
    """return true if a string is binary data using diff's heuristic"""
    if s and '\0' in s[:4096]:
        return True
    return False


def binary_file(fn):
    """read 4096 bytes from a file named fn, and call binary() on the data"""
    return binary(open(fn, 'rb').read(4096))


def get_source_file_diff(dir, filename, rev, oldfilename = None, olddir = None, origfilename = None):
    """
    This methods diffs oldfilename against filename (so filename will
    be shown as the new file).
    The variable origfilename is used if filename and oldfilename differ
    in their names (for instance if a tempfile is used for filename etc.)
    """

    import difflib

    if not oldfilename:
        oldfilename = filename

    if not olddir:
        olddir = os.path.join(dir, store)

    if not origfilename:
        origfilename = filename

    file1 = os.path.join(olddir, oldfilename)   # old/stored original
    file2 = os.path.join(dir, filename)         # working copy

    f1 = open(file1, 'rb')
    s1 = f1.read()
    f1.close()

    f2 = open(file2, 'rb')
    s2 = f2.read()
    f2.close()

    if binary(s1) or binary (s2):
        d = ['Binary file %s has changed\n' % origfilename]

    else:
        d = difflib.unified_diff(\
            s1.splitlines(1), \
            s2.splitlines(1), \
            fromfile = '%s     (revision %s)' % (origfilename, rev), \
            tofile = '%s     (working copy)' % origfilename)

        # if file doesn't end with newline, we need to append one in the diff result
        d = list(d)
        for i, line in enumerate(d):
            if not line.endswith('\n'):
                d[i] += '\n\\ No newline at end of file'
                if i+1 != len(d):
                    d[i] += '\n'

    return ''.join(d)

def make_diff(wc, revision):
    import tempfile
    changed_files = []
    added_files = []
    removed_files = []
    cmp_pac = None
    diff_hdr = 'Index: %s\n'
    diff_hdr += '===================================================================\n'
    diff = []
    olddir = os.getcwd()
    if not revision:
        # normal diff
        if wc.todo:
            for file in wc.todo:
                if file in wc.filenamelist+wc.filenamelist_unvers:
                    state = wc.status(file)
                    if state == 'A':
                        added_files.append(file)
                    elif state == 'D':
                        removed_files.append(file)
                    elif state == 'M' or state == 'C':
                        changed_files.append(file)
                else:
                    diff.append('osc: \'%s\' is not under version control' % file)
        else:
            for file in wc.filenamelist+wc.filenamelist_unvers:
                state = wc.status(file)
                if state == 'M' or state == 'C':
                    changed_files.append(file)
                elif state == 'A':
                    added_files.append(file)
                elif state == 'D':
                    removed_files.append(file)
    else:
        tempdir = '/tmp'
        if sys.platform[:3] == 'win':
            tempdir = os.getenv('TEMP')
        tmpdir  = tempfile.mkdtemp(str(revision), wc.name, dir = tempdir)
        os.chdir(tmpdir)
        init_package_dir(wc.apiurl, wc.prjname, wc.name, tmpdir, revision)
        cmp_pac = Package(tmpdir)
        if wc.todo:
            for file in wc.todo:
                if file in cmp_pac.filenamelist:
                    if file in wc.filenamelist:
                        changed_files.append(file)
                    else:
                        diff.append('osc: \'%s\' is not under version control' % file)
                else:
                    diff.append('osc: unable to find \'%s\' in revision %s' % (file, cmp_pac.rev))
        else:
            changed_files, added_files, removed_files = wc.comparePac(cmp_pac)

    for file in changed_files:
        diff.append(diff_hdr % file)
        if cmp_pac == None:
            diff.append(get_source_file_diff(wc.absdir, file, wc.rev))
        else:
            cmp_pac.updatefile(file, revision)
            diff.append(get_source_file_diff(wc.absdir, file, revision, file,
                                             cmp_pac.absdir, file))
    tempdir = '/tmp'
    if sys.platform[:3] == 'win':
        tempdir = os.getenv('TEMP')
    (fd, tmpfile) = tempfile.mkstemp(dir = tempdir)
    for file in added_files:
        diff.append(diff_hdr % file)
        if cmp_pac == None:
            diff.append(get_source_file_diff(wc.absdir, file, wc.rev, os.path.basename(tmpfile),
                                             os.path.dirname(tmpfile), file))
        else:
            diff.append(get_source_file_diff(wc.absdir, file, revision, os.path.basename(tmpfile),
                                             os.path.dirname(tmpfile), file))

    # FIXME: this is ugly but it cannot be avoided atm
    #        if a file is deleted via "osc rm file" we should keep the storefile.
    tmp_pac = None
    if cmp_pac == None and removed_files:
        tempdir = '/tmp'
        if sys.platform[:3] == 'win':
            tempdir = os.getenv('TEMP')
        tmpdir  = tempfile.mkdtemp( dir = tempdir)
        os.chdir(tmpdir)
        init_package_dir(wc.apiurl, wc.prjname, wc.name, tmpdir, wc.rev)
        tmp_pac = Package(tmpdir)
        os.chdir(olddir)

    for file in removed_files:
        diff.append(diff_hdr % file)
        if cmp_pac == None:
            tmp_pac.updatefile(file, tmp_pac.rev)
            diff.append(get_source_file_diff(os.path.dirname(tmpfile), os.path.basename(tmpfile),
                                             wc.rev, file, tmp_pac.storedir, file))
        else:
            cmp_pac.updatefile(file, revision)
            diff.append(get_source_file_diff(os.path.dirname(tmpfile), os.path.basename(tmpfile),
                                             revision, file, cmp_pac.storedir, file))

    os.chdir(olddir)
    if cmp_pac != None:
        delete_tmpdir(cmp_pac.absdir)
    if tmp_pac != None:
        delete_tmpdir(tmp_pac.absdir)
    return diff


def server_diff(apiurl,
                old_project, old_package, old_revision,
                new_project, new_package, new_revision, unified=False):

    query = {'cmd': 'diff', 'expand': '1'}
    if old_project:
        query['oproject'] = old_project
    if old_package:
        query['opackage'] = old_package
    if old_revision:
        query['orev'] = old_revision
    if new_revision:
        query['rev'] = new_revision
    if unified:
        query['unified'] = 1

    u = makeurl(apiurl, ['source', new_project, new_package], query=query)

    f = http_POST(u)
    return f.read()


def make_dir(apiurl, project, package, pathname=None, prj_dir=None):
    """
    creates the plain directory structure for a package dir.
    The 'apiurl' parameter is needed for the project dir initialization.
    The 'project' and 'package' parameters specify the name of the
    project and the package. The optional 'pathname' parameter is used
    for printing out the message that a new dir was created (default: 'prj_dir/package').
    The optional 'prj_dir' parameter specifies the path to the project dir (default: 'project').
    """
    prj_dir = prj_dir or project

    # FIXME: carefully test each patch component of prj_dir,
    # if we have a .osc/_files entry at that level.
    #   -> if so, we have a package/project clash,
    #      and should rename this path component by appending '.proj'
    #      and give user a warning message, to discourage such clashes

    pathname = pathname or getTransActPath(os.path.join(prj_dir, package))
    if is_package_dir(prj_dir):
        # we want this to become a project directory, 
        # but it already is a package directory.
        raise oscerr.OscIOError(None, 'checkout_package: package/project clash. Moving myself away not implemented')

    if not is_project_dir(prj_dir):
        # this directory could exist as a parent direory for one of our earlier 
        # checked out sub-projects. in this case, we still need to initialize it.
        print statfrmt('A', prj_dir)
        init_project_dir(apiurl, prj_dir, project)

    if is_project_dir(os.path.join(prj_dir, package)):
        # the thing exists, but is a project directory and not a package directory
        # FIXME: this should be a warning message to discourage package/project clashes
        raise oscerr.OscIOError(None, 'checkout_package: package/project clash. Moving project away not implemented')

    if not os.path.exists(os.path.join(prj_dir, package)):
        print statfrmt('A', pathname)
        os.mkdir(os.path.join(prj_dir, package))
        os.mkdir(os.path.join(prj_dir, package, store))

    return(os.path.join(prj_dir, package))


def checkout_package(apiurl, project, package, 
                     revision=None, pathname=None, prj_obj=None,
                     expand_link=False, prj_dir=None, service_files=None):
    try:
        # the project we're in might be deleted.
        # that'll throw an error then.
        olddir = os.getcwd()
    except:
        olddir = os.environ.get("PWD")

    if not prj_dir:
        prj_dir = olddir
    else:
        if sys.platform[:3] == 'win':
            prj_dir = prj_dir[:2] + prj_dir[2:].replace(':', ';')
        else:
            if conf.config['checkout_no_colon']:
                prj_dir = prj_dir.replace(':', '/')
 
    if not pathname:
        pathname = getTransActPath(os.path.join(prj_dir, package))

    # before we create directories and stuff, check if the package actually
    # exists
    show_package_meta(apiurl, project, package)
 
    if expand_link:
        # try to read from the linkinfo
        # if it is a link we use the xsrcmd5 as the revision to be
        # checked out
        x = show_upstream_xsrcmd5(apiurl, project, package, revision=revision)
        if x:
            revision = x
    os.chdir(make_dir(apiurl, project, package, pathname, prj_dir))
    init_package_dir(apiurl, project, package, store, revision)
    os.chdir(os.pardir)
    p = Package(package)

    for filename in p.filenamelist:
        if service_files or not filename.startswith('_service:'):
           p.updatefile(filename, revision)
           #print 'A   ', os.path.join(project, package, filename)
           print statfrmt('A', os.path.join(pathname, filename))
    if conf.config['do_package_tracking']:
        # check if we can re-use an existing project object
        if prj_obj == None:
            prj_obj = Project(os.getcwd())
        prj_obj.set_state(p.name, ' ')
        prj_obj.write_packages()
    os.chdir(olddir)


def replace_pkg_meta(pkgmeta, new_name, new_prj, keep_maintainers = False,
                     dst_userid = None, keep_develproject = False):
    """
    update pkgmeta with new new_name and new_prj and set calling user as the
    only maintainer (unless keep_maintainers is set). Additionally remove the
    develproject entry (<devel />) unless keep_develproject is true.
    """
    root = ET.fromstring(''.join(pkgmeta))
    root.set('name', new_name)
    root.set('project', new_prj)
    if not keep_maintainers:
        for person in root.findall('person'):
            root.remove(person)
    if not keep_develproject:
        for dp in root.findall('devel'):
            root.remove(dp)
    return ET.tostring(root)

def link_pac(src_project, src_package, dst_project, dst_package, force, rev='', cicount=''):
    """
    create a linked package
     - "src" is the original package
     - "dst" is the "link" package that we are creating here
    """

    try: meta_exists(metatype='pkg',
                       path_args=(quote_plus(dst_project), quote_plus(dst_package)),
                       template_args=None,
                       create_new=False, apiurl=conf.config['apiurl'])
    except:
        src_meta = show_package_meta(conf.config['apiurl'], src_project, src_package)
        src_meta = replace_pkg_meta(src_meta, dst_package, dst_project)
     
        edit_meta('pkg',
                  path_args=(dst_project, dst_package), 
                  data=src_meta)

    # create the _link file
    # but first, make sure not to overwrite an existing one
    if '_link' in meta_get_filelist(conf.config['apiurl'], dst_project, dst_package):
        if force:
            print >>sys.stderr, 'forced overwrite of existing _link file'
        else:
            print >>sys.stderr
            print >>sys.stderr, '_link file already exists...! Aborting'
            sys.exit(1)
    
    if rev:
        rev = 'rev="%s"' % rev
    else:
        rev = ''

    if cicount:
        cicount = 'cicount="%s"' % cicount
    else:
        cicount = ''

    print 'Creating _link...',
    link_template = """\
<link project="%s" package="%s" %s %s>
<patches>
  <!-- <apply name="patch" /> apply a patch on the source directory  -->
  <!-- <topadd>%%define build_with_feature_x 1</topadd> add a line on the top (spec file only) -->
  <!-- <add>file.patch</add> add a patch to be applied after %%setup (spec file only) -->
  <!-- <delete>filename</delete> delete a file -->
</patches>
</link>
""" % (src_project, src_package, rev, cicount)

    u = makeurl(conf.config['apiurl'], ['source', dst_project, dst_package, '_link'])
    http_PUT(u, data=link_template)
    print 'Done.'

def aggregate_pac(src_project, src_package, dst_project, dst_package, repo_map = {}):
    """
    aggregate package
     - "src" is the original package
     - "dst" is the "aggregate" package that we are creating here
     - "map" is a dictionary SRC => TARGET repository mappings
    """

    src_meta = show_package_meta(conf.config['apiurl'], src_project, src_package)
    src_meta = replace_pkg_meta(src_meta, dst_package, dst_project)

    edit_meta('pkg',
              path_args=(dst_project, dst_package), 
              data=src_meta)

    # create the _aggregate file
    # but first, make sure not to overwrite an existing one
    if '_aggregate' in meta_get_filelist(conf.config['apiurl'], dst_project, dst_package):
        print >>sys.stderr
        print >>sys.stderr, '_aggregate file already exists...! Aborting'
        sys.exit(1)

    print 'Creating _aggregate...',
    aggregate_template = """\
<aggregatelist>
  <aggregate project="%s">
""" % (src_project)
    for tgt, src in repo_map.iteritems():
        aggregate_template += """\
    <repository target="%s" source="%s" />
""" % (tgt, src)

    aggregate_template += """\
    <package>%s</package>
  </aggregate>
</aggregatelist>
""" % ( src_package)

    u = makeurl(conf.config['apiurl'], ['source', dst_project, dst_package, '_aggregate'])
    http_PUT(u, data=aggregate_template)
    print 'Done.'

def branch_pkg(apiurl, src_project, src_package, nodevelproject=False, rev=None, target_project=None, target_package=None, return_existing=False):
    """
    Branch a package (via API call)
    """
    query = { 'cmd': 'branch' }
    if nodevelproject:
        query['ignoredevel'] = '1'
    if rev:
        query['rev'] = rev
    if target_project:
        query['target_project'] = target_project
    if target_package:
        query['target_package'] = target_package
    u = makeurl(apiurl, ['source', src_project, src_package], query=query)
    try:
        f = http_POST(u)
    except urllib2.HTTPError, e:
        if not return_existing:
            raise
        msg = ''.join(e.readlines())
        msg = msg.split('<summary>')[1]
        msg = msg.split('</summary>')[0]
        m = re.match(r"branch target package already exists: (\S+)/", msg)
        if not m:
            e.msg += '\n' + msg
            raise
        return (None, m.group(1))

    r = f.read()
    r = r.split('targetproject">')[1]
    r = r.split('</data>')[0]
    return r



def copy_pac(src_apiurl, src_project, src_package, 
             dst_apiurl, dst_project, dst_package,
             client_side_copy = False,
             keep_maintainers = False,
             keep_develproject = False,
             expand = False,
             revision = None,
             comment = None):
    """
    Create a copy of a package.

    Copying can be done by downloading the files from one package and commit
    them into the other by uploading them (client-side copy) --
    or by the server, in a single api call.
    """

    src_meta = show_package_meta(src_apiurl, src_project, src_package)
    dst_userid = conf.get_apiurl_usr(dst_apiurl)
    src_meta = replace_pkg_meta(src_meta, dst_package, dst_project, keep_maintainers,
                                dst_userid, keep_develproject)

    print 'Sending meta data...'
    u = makeurl(dst_apiurl, ['source', dst_project, dst_package, '_meta'])
    http_PUT(u, data=src_meta)

    print 'Copying files...'
    if not client_side_copy:
        query = {'cmd': 'copy', 'oproject': src_project, 'opackage': src_package }
        if expand:
            query['expand'] = '1'
        if revision:
            query['orev'] = revision
        if comment:
            query['comment'] = comment
        u = makeurl(dst_apiurl, ['source', dst_project, dst_package], query=query)
        f = http_POST(u)
        return f.read()

    else:
        # copy one file after the other
        import tempfile
        tempdir = '/tmp'
        if sys.platform[:3] == 'win':
            tempdir = os.getenv('TEMP')
        tmpdir = tempfile.mkdtemp(prefix='osc_copypac', dir = tempdir)
        os.chdir(tmpdir)
        query = {'rev': 'upload'}
        for n in meta_get_filelist(src_apiurl, src_project, src_package, expand=expand):
            print '  ', n
            get_source_file(src_apiurl, src_project, src_package, n, targetfilename=n, revision=revision)
            u = makeurl(dst_apiurl, ['source', dst_project, dst_package, pathname2url(n)], query=query)
            http_PUT(u, file = n)
            os.unlink(n)
        if comment:
            query['comment'] = comment
        query['cmd'] = 'commit'
        u = makeurl(dst_apiurl, ['source', dst_project, dst_package], query=query)
        http_POST(u)
        os.rmdir(tmpdir)
        return 'Done.'


def delete_package(apiurl, prj, pac):
    u = makeurl(apiurl, ['source', prj, pac])
    http_DELETE(u)


def delete_project(apiurl, prj):
    u = makeurl(apiurl, ['source', prj])
    http_DELETE(u)

def delete_files(apiurl, prj, pac, files):
    for file in files:
        u = makeurl(apiurl, ['source', prj, pac, file], query={'comment': 'removed %s' % (file, )})
        http_DELETE(u)

# old compat lib call
def get_platforms(apiurl):
    return get_repositories(apiurl)

def get_repositories(apiurl):
    f = http_GET(makeurl(apiurl, ['platform']))
    tree = ET.parse(f)
    r = [ node.get('name') for node in tree.getroot() ]
    r.sort()
    return r


# old compat lib call
def get_platforms_of_project(apiurl, prj):
    return get_repositories_of_project(apiurl, prj)

def get_repositories_of_project(apiurl, prj):
    f = show_project_meta(apiurl, prj)
    tree = ET.parse(StringIO(''.join(f)))

    r = [ node.get('name') for node in tree.findall('repository')]
    return r


def get_repos_of_project(apiurl, prj):
    f = show_project_meta(apiurl, prj)
    tree = ET.parse(StringIO(''.join(f)))

    repo_line_templ = '%-15s %-10s'
    for node in tree.findall('repository'):
        for node2 in node.findall('arch'):
            yield repo_line_templ % (node.get('name'), node2.text)


def get_binarylist(apiurl, prj, repo, arch, package=None, verbose=False):
    what = package or '_repository'
    u = makeurl(apiurl, ['build', prj, repo, arch, what])
    f = http_GET(u)
    tree = ET.parse(f)
    if not verbose:
        return [ node.get('filename') for node in tree.findall('binary')]
    else:
        l = []
        for node in tree.findall('binary'):
            f = File(node.get('filename'), 
                     None, 
                     int(node.get('size')), 
                     int(node.get('mtime')))
            l.append(f)
        return l


def get_binarylist_published(apiurl, prj, repo, arch):
    u = makeurl(apiurl, ['published', prj, repo, arch])
    f = http_GET(u)
    tree = ET.parse(f)
    r = [ node.get('name') for node in tree.findall('entry')]
    return r


def show_results_meta(apiurl, prj, package=None, lastbuild=None, repository=[], arch=[]):
    query = {}
    if package:
        query['package'] = package
    if lastbuild:
        query['lastbuild'] = 1
    u = makeurl(apiurl, ['build', prj, '_result'], query=query)
    for repo in repository:
        u = u + '&repository=%s' % repo
    for a in arch:
        u = u + '&arch=%s' % a
    f = http_GET(u)
    return f.readlines()


def show_prj_results_meta(apiurl, prj):
    u = makeurl(apiurl, ['build', prj, '_result'])
    f = http_GET(u)
    return f.readlines()


def get_results(apiurl, prj, package, lastbuild=None, repository=[], arch=[]):
    r = []
    result_line_templ = '%(rep)-15s %(arch)-10s %(status)s'

    f = show_results_meta(apiurl, prj, package, lastbuild, repository, arch)
    tree = ET.parse(StringIO(''.join(f)))
    root = tree.getroot()

    for node in root.findall('result'):
        rmap = {}
        rmap['prj'] = prj
        rmap['pac'] = package
        rmap['rep'] = node.get('repository')
        rmap['arch'] = node.get('arch')

        statusnode =  node.find('status')
        try:
            rmap['status'] = statusnode.get('code')
        except:
            # code can be missing when package is too new:
            return {}

        if rmap['status'] in ['expansion error', 'broken', 'blocked']:
            rmap['status'] += ': ' + statusnode.find('details').text

        if rmap['status'] == 'failed':
            rmap['status'] += ': %s' % apiurl + \
                '/build/%(prj)s/%(rep)s/%(arch)s/%(pac)s/_log' % rmap

        r.append(result_line_templ % rmap)
    return r

def get_prj_results(apiurl, prj, hide_legend=False, csv=False, status_filter=None, name_filter=None):
    #print '----------------------------------------'

    r = []
    #result_line_templ = '%(prj)-15s %(pac)-15s %(rep)-15s %(arch)-10s %(status)s'
    result_line_templ = '%(rep)-15s %(arch)-10s %(status)s'

    f = show_prj_results_meta(apiurl, prj)
    tree = ET.parse(StringIO(''.join(f)))
    root = tree.getroot()

    pacs = []
    # sequence of (repo,arch) tuples
    targets = []
    # {package: {(repo,arch): status}}
    status = {}
    if not root.find('result'):
        return []
    for node in root.find('result'):
        pacs.append(node.get('package'))
    pacs.sort()
    for node in root.findall('result'):
        tg = (node.get('repository'), node.get('arch'))
        targets.append(tg)
        for pacnode in node.findall('status'):
            pac = pacnode.get('package')
            if pac not in status:
                status[pac] = {}
            status[pac][tg] = pacnode.get('code')
    targets.sort()

    # filter option
    if status_filter or name_filter:

        pacs_to_show = []
        targets_to_show = []

        #filtering for Package Status 
        if status_filter:
            if status_filter in buildstatus_symbols.values():
                for txt, sym in buildstatus_symbols.items():
                    if sym == status_filter:
                        filt_txt = txt
                for pkg in status.keys():
                    for repo in status[pkg].keys():
                        if status[pkg][repo] == filt_txt:
                            if not name_filter:
                                pacs_to_show.append(pkg)
                                targets_to_show.append(repo)
                            elif name_filter in pkg:
                                pacs_to_show.append(pkg)

        #filtering for Package Name 
        elif name_filter:
            for pkg in pacs:
                if name_filter in pkg:
                    pacs_to_show.append(pkg)

        pacs = [ i for i in pacs if i in pacs_to_show ]
        if len(targets_to_show):
            targets = [ i for i in targets if i in targets_to_show ]

    # csv output
    if csv:
        # TODO: option to disable the table header
        row = ['_'] + ['/'.join(tg) for tg in targets]
        r.append(';'.join(row))
        for pac in pacs:
            row = [pac] + [status[pac][tg] for tg in targets]
            r.append(';'.join(row))
        return r

    # human readable output
    max_pacs = 40
    for startpac in range(0, len(pacs), max_pacs):
        offset = 0
        for pac in pacs[startpac:startpac+max_pacs]:
            r.append(' |' * offset + ' ' + pac)
            offset += 1

        for tg in targets:
            line = []
            line.append(' ')
            for pac in pacs[startpac:startpac+max_pacs]:
                st = ''
                if not status.has_key(pac) or not status[pac].has_key(tg):
                    # for newly added packages, status may be missing
                    st = '?'
                else:
                    try:
                        st = buildstatus_symbols[status[pac][tg]]
                    except:
                        print 'osc: warn: unknown status \'%s\'...' % status[pac][tg]
                        print 'please edit osc/core.py, and extend the buildstatus_symbols dictionary.'
                        st = '?'
                        buildstatus_symbols[status[pac][tg]] = '?'
                line.append(st)
                line.append(' ')
            line.append(' %s %s' % tg)
            line = ''.join(line)

            r.append(line)

        r.append('')

    if not hide_legend and len(pacs):
        r.append(' Legend:')
        for i, j in buildstatus_symbols.items():
            r.append('  %s %s' % (j, i))

    return r


def streamfile(url, http_meth = http_GET, bufsize=8192):
    """
    performs http_meth on url and read bufsize bytes from the response
    until EOF is reached. After each read bufsize bytes are yielded to the
    caller.
    """
    f = http_meth.__call__(url)
    data = f.read(bufsize)
    while len(data):
        yield data
        data = f.read(bufsize)
    f.close()


def print_buildlog(apiurl, prj, package, repository, arch, offset = 0):
    """prints out the buildlog on stdout"""
    query = {'nostream' : '1', 'start' : '%s' % offset}
    while True:
        query['start'] = offset
        start_offset = offset
        u = makeurl(apiurl, ['build', prj, repository, arch, package, '_log'], query=query)
        for data in streamfile(u):
            offset += len(data)
            sys.stdout.write(data)
        if start_offset == offset:
            break

def get_buildinfo(apiurl, prj, package, repository, arch, specfile=None, addlist=None):
    query = []
    if addlist:
        for i in addlist:
            query.append('add=%s' % quote_plus(i))

    u = makeurl(apiurl, ['build', prj, repository, arch, package, '_buildinfo'], query=query)

    if specfile:
        f = http_POST(u, data=specfile)
    else:
        f = http_GET(u)
    return f.read()


def get_buildconfig(apiurl, prj, package, repository, arch):
    u = makeurl(apiurl, ['build', prj, repository, '_buildconfig'])
    f = http_GET(u)
    return f.read()


def get_buildhistory(apiurl, prj, package, repository, arch, format = 'text'):
    import time
    u = makeurl(apiurl, ['build', prj, repository, arch, package, '_history'])
    f = http_GET(u)
    root = ET.parse(f).getroot()

    r = []
    for node in root.findall('entry'):
        rev = int(node.get('rev'))
        srcmd5 = node.get('srcmd5') 
        versrel = node.get('versrel') 
        bcnt = int(node.get('bcnt'))
        t = time.localtime(int(node.get('time')))
        t = time.strftime('%Y-%m-%d %H:%M:%S', t)

        if format == 'csv':
            r.append('%s|%s|%d|%s.%d' % (t, srcmd5, rev, versrel, bcnt))
        else:
            r.append('%s   %s %6d    %s.%d' % (t, srcmd5, rev, versrel, bcnt))

    if format == 'text':
        r.insert(0, 'time                  srcmd5                              rev   vers-rel.bcnt')

    return r

def print_jobhistory(apiurl, prj, current_package, repository, arch, format = 'text'):
    import time
    if current_package:
        u = makeurl(apiurl, ['build', prj, repository, arch, '_jobhistory'], "package=%s" % (current_package))
    else:
        u = makeurl(apiurl, ['build', prj, repository, arch, '_jobhistory'])
    f = http_GET(u)
    root = ET.parse(f).getroot()

    if format == 'text':
        print "time                 package                                            reason           code              build time"
    for node in root.findall('jobhist'):
        package = node.get('package')
        reason = node.get('reason')
        if not reason:
            reason = "unknown"
        bcnt = node.get('bcnt')
        code = node.get('code')
        rev = int(node.get('rev'))
        srcmd5 = node.get('srcmd5') 
        rt = int(node.get('readytime'))
        readyt = time.localtime(rt)
        readyt = time.strftime('%Y-%m-%d %H:%M:%S', readyt)
        st = int(node.get('starttime'))
        et = int(node.get('endtime'))
        endtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(et))
        waitstart = time.strftime('%H:%M:%S', time.gmtime(st-rt))
        waittm = time.gmtime(et-st)
        if waittm.tm_hour:
            waitbuild = "%2dh %2dm %2ds" % (waittm.tm_hour, waittm.tm_min, waittm.tm_sec)
        else:
            waitbuild = "    %2dm %2ds" % (waittm.tm_min, waittm.tm_sec)
        
        if format == 'csv':
            print '%s|%s|%s|%s|%s' % (endtime, package, reason, code, waitbuild)
        else:
            print '%s  %-50s %-16s %-16s %s' % (endtime, package[0:49], reason[0:15], code[0:15], waitbuild)


def get_commitlog(apiurl, prj, package, revision, format = 'text'):
    import time, locale
    u = makeurl(apiurl, ['source', prj, package, '_history'])
    f = http_GET(u)
    root = ET.parse(f).getroot()

    r = []
    if format == 'xml':
        r.append('<?xml version="1.0"?>')
        r.append('<log>')
    revisions = root.findall('revision')
    revisions.reverse()
    for node in revisions:
        srcmd5 = node.find('srcmd5').text
        try:
            rev = int(node.get('rev'))
            #vrev = int(node.get('vrev')) # what is the meaning of vrev?
            try:
                if revision and rev != int(revision):
                    continue
            except ValueError:
                if revision != srcmd5:
                    continue
        except ValueError:
            # this part should _never_ be reached but...
            return [ 'an unexpected error occured - please file a bug' ]
        version = node.find('version').text
        user = node.find('user').text
        try:
            comment = node.find('comment').text.encode(locale.getpreferredencoding(), 'replace')
        except:
            comment = '<no message>'
        try:
            requestid = node.find('requestid').text.encode(locale.getpreferredencoding(), 'replace')
        except:
            requestid = ""
        t = time.localtime(int(node.find('time').text))
        t = time.strftime('%Y-%m-%d %H:%M:%S', t)

        if format == 'csv':
            s = '%s|%s|%s|%s|%s|%s|%s' % (rev, user, t, srcmd5, version, 
                comment.replace('\\', '\\\\').replace('\n', '\\n').replace('|', '\\|'), requestid)
            r.append(s)
        elif format == 'xml':
            r.append('<logentry')
            r.append('   revision="%s" srcmd5="%s">' % (rev, srcmd5))
            r.append('<author>%s</author>' % user)
            r.append('<date>%s</date>' % t)
            r.append('<requestid>%s</requestid>' % requestid)
            r.append('<msg>%s</msg>' % 
                comment.replace('&', '&amp;').replace('<', '&gt;').replace('>', '&lt;'))
            r.append('</logentry>')
        else:
            s = '-' * 76 + \
                '\nr%s | %s | %s | %s | %s | sr%s\n' % (rev, user, t, srcmd5, version, requestid) + \
                '\n' + comment
            r.append(s)

    if format not in ['csv', 'xml']:
        r.append('-' * 76)
    if format == 'xml':
        r.append('</log>')
    return r


def rebuild(apiurl, prj, package, repo, arch, code=None):
    query = { 'cmd': 'rebuild' }
    if package:
        query['package'] = package
    if repo:
        query['repository'] = repo
    if arch:
        query['arch'] = arch
    if code:
        query['code'] = code

    u = makeurl(apiurl, ['build', prj], query=query)
    try:
        f = http_POST(u)
    except urllib2.HTTPError, e:
        e.osc_msg = 'could not trigger rebuild for project \'%s\' package \'%s\'' % (prj, package)
        raise

    root = ET.parse(f).getroot()
    return root.get('code')


def store_read_project(dir):
    try:
        p = open(os.path.join(dir, store, '_project')).readlines()[0].strip()
    except IOError:
        msg = 'Error: \'%s\' is not an osc project dir or working copy' % os.path.abspath(dir)
        if os.path.exists(os.path.join(dir, '.svn')):
            msg += '\nTry svn instead of osc.'
        raise oscerr.NoWorkingCopy(msg)
    return p


def store_read_package(dir):
    try:
        p = open(os.path.join(dir, store, '_package')).readlines()[0].strip()
    except IOError:
        msg = 'Error: \'%s\' is not an osc working copy' % os.path.abspath(dir)
        if os.path.exists(os.path.join(dir, '.svn')):
            msg += '\nTry svn instead of osc.'
        raise oscerr.NoWorkingCopy(msg)
    return p

def store_read_apiurl(dir):
    fname = os.path.join(dir, store, '_apiurl')
    try:
        url = open(fname).readlines()[0].strip()
        # this is needed to get a proper apiurl
        # (former osc versions may stored an apiurl with a trailing slash etc.)
        apiurl = conf.urljoin(*conf.parse_apisrv_url(None, url))
    except:
        apiurl = conf.config['apiurl']
    return apiurl

def store_write_string(dir, file, string):
    fname = os.path.join(dir, store, file)
    open(fname, 'w').write(string)

def store_write_project(dir, project):
    fname = os.path.join(dir, store, '_project')
    open(fname, 'w').write(project + '\n')

def store_write_apiurl(dir, apiurl):
    fname = os.path.join(dir, store, '_apiurl')
    open(fname, 'w').write(apiurl + '\n')

def store_write_initial_packages(dir, project, subelements):
    fname = os.path.join(dir, store, '_packages')
    root = ET.Element('project', name=project)
    for elem in subelements:
        root.append(elem)
    ET.ElementTree(root).write(fname)

def get_osc_version():
    return __version__


def abortbuild(apiurl, project, package=None, arch=None, repo=None):
    query = { 'cmd': 'abortbuild' }
    if package:
        query['package'] = package
    if arch:
        query['arch'] = arch
    if repo:
        query['repository'] = repo
    u = makeurl(apiurl, ['build', project], query)
    try:
        f = http_POST(u)
    except urllib2.HTTPError, e:
        e.osc_msg = 'abortion failed for project %s' % project
        if package:
            e.osc_msg += ' package %s' % package
        if arch:
            e.osc_msg += ' arch %s' % arch
        if repo:
            e.osc_msg += ' repo %s' % repo
        raise

    root = ET.parse(f).getroot()
    return root.get('code')


def wipebinaries(apiurl, project, package=None, arch=None, repo=None, code=None):
    query = { 'cmd': 'wipe' }
    if package:
        query['package'] = package
    if arch:
        query['arch'] = arch
    if repo:
        query['repository'] = repo
    if code:
        query['code'] = code

    u = makeurl(apiurl, ['build', project], query)
    try:
        f = http_POST(u)
    except urllib2.HTTPError, e:
        e.osc_msg = 'wipe binary rpms failed for project %s' % project
        if package:
            e.osc_msg += ' package %s' % package
        if arch:
            e.osc_msg += ' arch %s' % arch
        if repo:
            e.osc_msg += ' repository %s' % repo
        if code:
            e.osc_msg += ' code=%s' % code
        raise

    root = ET.parse(f).getroot()
    return root.get('code')


def parseRevisionOption(string):
    """
    returns a tuple which contains the revisions
    """

    if string:
        if ':' in string:
            splitted_rev = string.split(':')
            try:
                for i in splitted_rev:
                    int(i)
                return splitted_rev
            except ValueError:
                print >>sys.stderr, 'your revision \'%s\' will be ignored' % string
                return None, None
        else:
            if string.isdigit():
                return string, None
            elif string.isalnum() and len(string) == 32:
                # could be an md5sum
                return string, None
            else:
                print >>sys.stderr, 'your revision \'%s\' will be ignored' % string
                return None, None
    else:
        return None, None

def checkRevision(prj, pac, revision, apiurl=None):
    """
    check if revision is valid revision, i.e. it is not 
    larger than the upstream revision id
    """
    if len(revision) == 32:
        # there isn't a way to check this kind of revision for validity
        return True
    if not apiurl:
        apiurl = conf.config['apiurl']
    try:
        if int(revision) > int(show_upstream_rev(apiurl, prj, pac)) \
           or int(revision) <= 0:
            return False
        else:
            return True
    except (ValueError, TypeError):
        return False

def build_xpath_predicate(search_list, search_term, exact_matches):
    """
    Builds and returns a xpath predicate
    """

    predicate = ['[']
    for i, elem in enumerate(search_list):
        if i > 0 and i < len(search_list):
            predicate.append(' or ')
        if exact_matches:
            predicate.append('%s=\'%s\'' % (elem, search_term))
        else:
            predicate.append('contains(%s, \'%s\')' % (elem, search_term))
    predicate.append(']')
    return predicate

def build_table(col_num, data = [], headline = [], width=1, csv = False):
    """
    This method builds a simple table.
    Example1: build_table(2, ['foo', 'bar', 'suse', 'osc'], ['col1', 'col2'], 2)
        col1  col2
        foo   bar
        suse  osc
    """

    longest_col = []
    for i in range(col_num):
        longest_col.append(0)
    if headline and not csv:
        data[0:0] = headline
    # find longest entry in each column
    i = 0
    for itm in data:
        if longest_col[i] < len(itm):
            longest_col[i] = len(itm)
        if i == col_num - 1:
            i = 0
        else:
            i += 1
    # calculate length for each column
    for i, row in enumerate(longest_col):
        longest_col[i] = row + width
    # build rows   
    row = []
    table = []
    i = 0
    for itm in data:
        if i % col_num == 0:
            i = 0
            row = []
            table.append(row)
        # there is no need to justify the entries of the last column
        # or when generating csv
        if i == col_num -1 or csv:
            row.append(itm)
        else:
            row.append(itm.ljust(longest_col[i]))
        i += 1
    if csv:
        separator = '|'
    else:
        separator = ''
    return [separator.join(row) for row in table]

def search(apiurl, search_list, kind, search_term, verbose = False, exact_matches = False, repos_baseurl = False, role_filter = None):
    """
    Perform a search for 'search_term'. A list which contains the
    results will be returned on success otherwise 'None'. If 'verbose' is true
    and the title-tag-text (<title>TEXT</title>) is longer than 60 chars it'll we
    truncated.
    """

    if role_filter:
        role_filter = role_filter.split(':')

    predicate = build_xpath_predicate(search_list, search_term, exact_matches)
    u = makeurl(apiurl, ['search', kind], ['match=%s' % quote_plus(''.join(predicate))])
    if conf.config['verbose']: print '>>', unquote(u), '<<'
    f = http_GET(u)
    root = ET.parse(f).getroot()
    result = []
    for node in root.findall(kind):
        if role_filter:
            skip = 1
            for p in node.findall('person'):
                if p.get('userid') == role_filter[0] and p.get('role') == role_filter[1]:
                    skip = 0
            if skip:
                continue

        # TODO: clarify if we need to check if node.get() returns 'None'.
        #       If it returns 'None' something is broken anyway...
        if kind == 'package':
            project = node.get('project')
            package = node.get('name')
            result.append(package)
        else:
            project = node.get('name')
        result.append(project)
        if verbose:
            title = node.findtext('title').strip()
            if len(title) > 60:
                title = title[:61] + '...'
            result.append(title)
        if repos_baseurl:
            # FIXME: no hardcoded URL of instance
            result.append('http://download.opensuse.org/repositories/%s/' % project.replace(':', ':/'))
    if result:
        return result
    else:
        return None


def set_link_rev(apiurl, project, package, revision = None):
    url = makeurl(apiurl, ['source', project, package, '_link'])
    try:
       f = http_GET(url)
       root = ET.parse(f).getroot()
    except urllib2.HTTPError, e:
       e.osc_msg = 'Unable to get _link file in package \'%s\' for project \'%s\'' % (package, project)
       raise

    # set revision element
    if not revision:
       src_project = root.attrib['project']
       src_package = root.attrib['package']
       root.attrib['rev'] = show_upstream_rev(apiurl, src_project, src_package);
    elif revision == -1:
       del root.attrib['rev']
    else:
       root.attrib['rev'] = revision

    l = ET.tostring(root)
    # upload _link file again
    http_PUT(url, data=l)


def delete_dir(dir):
    # small security checks
    if os.path.islink(dir):
        return False
    elif os.path.abspath(dir) == '/':
        return False
    elif not os.path.isdir(dir):
        return False

    for dirpath, dirnames, filenames in os.walk(dir, topdown=False):
        for file in filenames:
            try:
                os.unlink(os.path.join(dirpath, file))
            except:
                return False
        for dirname in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, dirname))
            except:
                return False
    try:
        os.rmdir(dir)
    except:
        return False
    return True

def delete_tmpdir(tmpdir):
    """
    This method deletes a tempdir. This tempdir
    must be located under /tmp/$DIR. If "tmpdir" is not
    a valid tempdir it'll return False. If os.unlink() / os.rmdir()
    throws an exception we will return False too - otherwise
    True.
    """

    head, tail = os.path.split(tmpdir)
    if sys.platform == 'win32':
        if head.upper().startswith(os.getenv('TEMP').upper) and tail:
            try:
                os.rmdir(tmpdir)
            except:
                return False
    else:
        if head.startswith('/tmp') and tail:
            return delete_dir(tmpdir)
    return False

def delete_storedir(store_dir):
    """
    This method deletes a store dir.
    """
    head, tail = os.path.split(store_dir)
    if tail == '.osc':
        return delete_dir(store_dir)
    else:
        return False

def unpack_srcrpm(srpm, dir, *files):
    """
    This method unpacks the passed srpm into the
    passed dir. If arguments are passed to the \'files\' tuple
    only this files will be unpacked.
    """
    if not is_srcrpm(srpm):
        print >>sys.stderr, 'error - \'%s\' is not a source rpm.' % srpm
        sys.exit(1)
    curdir = os.getcwd()
    if not os.path.isdir(dir):
        dir = curdir
    else:
        os.chdir(dir)
    cmd = 'rpm2cpio %s | cpio -i %s &> /dev/null' % (srpm, ' '.join(files))
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print >>sys.stderr, 'error \'%s\' - cannot extract \'%s\'' % (ret, srpm)
        sys.exit(1)
    os.chdir(curdir)

def is_rpm(f):
    """check if the named file is an RPM package"""
    try:                                                                                                                                
        h = open(f, 'rb').read(4)
    except:
        return False

    if h == '\xed\xab\xee\xdb':
        return True
    else:
        return False

def is_srcrpm(f):
    """check if the named file is a source RPM"""

    if not is_rpm(f):
        return False

    try:
        h = open(f, 'rb').read(8)
    except:
        return False

    if h[7] == '\x01':
        return True
    else:
        return False   

def addMaintainer(apiurl, prj, pac, user):
    # for backward compatibility only
    addPerson(apiurl, prj, pac, user)

def addPerson(apiurl, prj, pac, user, role="maintainer"):
    """ add a new person to a package or project """
    path = quote_plus(prj),
    kind = 'prj'
    if pac:
        path = path + (quote_plus(pac),)
        kind = 'pkg'
    data = meta_exists(metatype=kind,
                       path_args=path,
                       template_args=None,
                       create_new=False)
                       
    if data and get_user_meta(apiurl, user) != None:
        tree = ET.fromstring(''.join(data))
        found = False
        for person in tree.getiterator('person'):
            if person.get('userid') == user and person.get('role') == role:
                found = True
                print "user already exists"
                break
        if not found:
            # the xml has a fixed structure
            tree.insert(2, ET.Element('person', role=role, userid=user))
            print 'user \'%s\' added to \'%s\'' % (user, pac or prj)
            edit_meta(metatype=kind,
                      path_args=path,
                      data=ET.tostring(tree))
    else:
        print "osc: an error occured"

def delMaintainer(apiurl, prj, pac, user):
    # for backward compatibility only
    delPerson(apiurl, prj, pac, user)

def delPerson(apiurl, prj, pac, user, role="maintainer"):
    """ delete a person from a package or project """
    path = quote_plus(prj), 
    kind = 'prj'
    if pac:
        path = path + (quote_plus(pac), )
        kind = 'pkg'
    data = meta_exists(metatype=kind,
                       path_args=path,
                       template_args=None,
                       create_new=False)
    if data:
        tree = ET.fromstring(''.join(data))
        found = False
        for person in tree.getiterator('person'):
            if person.get('userid') == user and person.get('role') == role:
                tree.remove(person)
                found = True
                print "user \'%s\' removed" % user
        if found:
            edit_meta(metatype=kind,
                      path_args=path,
                      data=ET.tostring(tree))
        else:
            print "user \'%s\' not found in \'%s\'" % (user, pac or prj)
    else:
        print "an error occured"

def setDevelProject(apiurl, prj, pac, dprj, dpkg=None):
    """ set the <devel project="..."> element to package metadata"""
    path = (quote_plus(prj),) + (quote_plus(pac),)
    data = meta_exists(metatype='pkg',
                       path_args=path,
                       template_args=None,
                       create_new=False)
                       
    if data and show_project_meta(apiurl, dprj) != None:
        tree = ET.fromstring(''.join(data))
        if not tree.find('devel') != None:
            ET.SubElement(tree, 'devel')
        elem = tree.find('devel')
        if dprj:
           elem.attrib['project'] = dprj
        else:
           if elem.attrib.has_key('project'):
              del elem.attrib['project']
        if dpkg:
           elem.attrib['package'] = dpkg
        else:
           if elem.attrib.has_key('package'):
              del elem.attrib['package']
        edit_meta(metatype='pkg',
                  path_args=path,
                  data=ET.tostring(tree))
    else:
        print "osc: an error occured"

def createPackageDir(pathname, prj_obj=None):
    """
    create and initialize a new package dir in the given project.
    prj_obj can be a Project() instance.
    """
    prj_dir, pac_dir = getPrjPacPaths(pathname)
    if is_project_dir(prj_dir):
        if not os.path.exists(pac_dir):
            prj = prj_obj or Project(prj_dir, False)
            if prj.addPackage(pac_dir):
                os.mkdir(pathname)
                os.chdir(pathname)
                init_package_dir(prj.apiurl,
                                 prj.name,
                                 pac_dir, pac_dir, files=False)
                os.chdir(prj.absdir)
                print statfrmt('A', os.path.normpath(pathname))
                return True
            else:
                return False
        else:
            print '\'%s\' already exists' % pathname
            return False
    else:
        print '\'%s\' is not a working copy' % prj_dir
        if os.path.exists(os.path.join(prj_dir, '.svn')):
            print 'try svn instead of osc.'
        return False


def addFiles(filenames, prj_obj = None):
    for filename in filenames:
        if not os.path.exists(filename):
            print >>sys.stderr, "file '%s' does not exist" % filename
            return 1

    # init a package dir if we have a normal dir in the "filenames"-list
    # so that it will be find by findpacs() later
    for filename in filenames:

        prj_dir, pac_dir = getPrjPacPaths(filename)

        if not is_package_dir(filename) and os.path.isdir(filename) and is_project_dir(prj_dir) \
           and conf.config['do_package_tracking']:
            old_dir = os.getcwd()
            prj_name = store_read_project(prj_dir)
            prj_apiurl = store_read_apiurl(prj_dir)
            os.chdir(filename)
            init_package_dir(prj_apiurl, prj_name, pac_dir, pac_dir, files=False)
            os.chdir(old_dir)
        elif is_package_dir(filename) and conf.config['do_package_tracking']:
            print >>sys.stderr, 'osc: warning: \'%s\' is already under version control' % filename
            return 1
        elif os.path.isdir(filename) and is_project_dir(prj_dir):
            print >>sys.stderr, 'osc: cannot add a directory to a project unless ' \
                                '\'do_package_tracking\' is enabled in the configuration file'
            return 1

    pacs = findpacs(filenames)

    for pac in pacs:
        if conf.config['do_package_tracking'] and not pac.todo:
            prj = prj_obj or Project(os.path.dirname(pac.absdir))
            if pac.name in prj.pacs_unvers:
                if not prj.addPackage(pac.name):
                    sys.exit(1)
                print statfrmt('A', getTransActPath(os.path.join(pac.dir, os.pardir, pac.name)))
                for filename in pac.filenamelist_unvers:
                    pac.todo.append(filename)
            elif pac.name in prj.pacs_have:
                print 'osc: warning: \'%s\' is already under version control' % pac.name
        for filename in pac.todo:
            if filename in pac.excluded:
                print >>sys.stderr, 'osc: warning: \'%s\' is excluded from a working copy' % filename
                continue
            if filename in pac.filenamelist:
                print >>sys.stderr, 'osc: warning: \'%s\' is already under version control' % filename
                continue
            if pac.dir != '.':
                pathname = os.path.join(pac.dir, filename)
            else:
                pathname = filename
            print statfrmt('A', pathname)
            pac.addfile(filename)

def getPrjPacPaths(path):
    """
    returns the path for a project and a package
    from path. This is needed if you try to add
    or delete packages:
    Examples:
        osc add pac1/: prj_dir = CWD;
                       pac_dir = pac1
        osc add /path/to/pac1:
                       prj_dir = path/to;
                       pac_dir = pac1
        osc add /path/to/pac1/file
                       => this would be an invalid path
                          the caller has to validate the returned
                          path!
    """
    # make sure we hddave a dir: osc add bar vs. osc add bar/; osc add /path/to/prj_dir/new_pack
    # filename = os.path.join(tail, '')
    prj_dir, pac_dir = os.path.split(os.path.normpath(path))
    if prj_dir == '':
        prj_dir = os.getcwd()
    return (prj_dir, pac_dir)

def getTransActPath(pac_dir):
    """
    returns the path for the commit and update operations/transactions.
    Normally the "dir" attribute of a Package() object will be passed to
    this method.
    """
    if pac_dir != '.':
        pathn = os.path.normpath(pac_dir)
    else:
        pathn = ''
    return pathn

def getStatus(pacs, prj_obj=None, verbose=False, quiet=False):
    """
    calculates the status of certain packages. pacs is a list of Package()
    objects and prj_obj is a Project() object. If prj_obj is specified all
    Package() objects in the pacs list have to belong to this project.
    """
    lines = []
    if prj_obj:
        if conf.config['do_package_tracking']:
            for data in prj_obj.pacs_unvers:
                lines.append(statfrmt('?', os.path.normpath(os.path.join(prj_obj.dir, data))))
            for data in prj_obj.pacs_broken:
                if prj_obj.get_state(data) == 'D':
                    lines.append(statfrmt('D', os.path.normpath(os.path.join(prj_obj.dir, data))))
                else:
                    lines.append(statfrmt('!', os.path.normpath(os.path.join(prj_obj.dir, data))))

    for p in pacs:
        # no files given as argument? Take all files in current dir
        if not p.todo:
            p.todo = p.filenamelist + p.filenamelist_unvers
        p.todo.sort()

        if prj_obj and conf.config['do_package_tracking']:
            state = prj_obj.get_state(p.name)
            if state != None and (state != ' ' or verbose):
               lines.append(statfrmt(state, os.path.normpath(os.path.join(prj_obj.dir, p.name))))

        for filename in p.todo:
            if filename in p.excluded:
                continue
            s = p.status(filename)
            if s == 'F':
                lines.append(statfrmt('!', pathjoin(p.dir, filename)))
            elif s != ' ' or (s == ' ' and verbose):
                lines.append(statfrmt(s, pathjoin(p.dir, filename)))

    if quiet:
        lines = [line for line in lines if line[0] != '?']
    else:
        # arrange the lines in order: unknown files first
        # filenames are already sorted
        lines = [line for line in lines if line[0] == '?'] \
              + [line for line in lines if line[0] != '?']
    return lines

def get_commit_message_template(pac):
    """
    Read the difference in .changes file(s) and put them as a template to commit message.
    """
    diff = ""
    template = []
    date_re = re.compile(r'\+(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([A-Z][a-z]{2}) ( ?[0-9]|[0-3][0-9]) .*')
    if pac.todo:
        files = filter(lambda file: '.changes' in file and pac.status(file) in ('A', 'M'), pac.todo)
        if not files:
            return template
        
        for file in files:
            if pac.status(file) == 'M':
                diff += get_source_file_diff(pac.absdir, file, pac.rev)
            elif pac.status(file) == 'A':
                f = open(file, 'r')
                for line in f:
                    diff += '+' + line
                f.close()
    
    if diff:
        index = 0
        diff = diff.split('\n')

        # The first four lines contains a header of diff
        for line in diff[3:]:
            # this condition is magical, but it removes all unwanted lines from commit message
            if not(line) or (line and line[0] != '+') or \
            date_re.match(line) or \
            line == '+' or line[0:3] == '+++':
                continue

            if line == '+-------------------------------------------------------------------':
                template.append('')
            else:
                template.append(line[1:])
    
    return template

def check_filelist_before_commit(pacs):

    # warn if any of files has a ? status (usually a patch, or new source was not added to meta)
    for p in pacs:
        # no files given as argument? Take all files in current dir
        if not p.todo:
            p.todo = p.filenamelist + p.filenamelist_unvers
        p.todo.sort()
        for f in (f for f in p.todo if not os.path.isdir(f)):
            if p.status(f) in ('?', '!'):
                resp = raw_input("File `%s' is not in package meta. Would you like skip/remove/edit file lists/commit/abort? (s/r/e/c/A) "% (f, ))
                if resp in ('s', 'S'):
                    continue
                elif resp in ('r', 'R'):
                    p.process_filelist(['r ? %s' % (f, ), ])
                elif resp in ('e', 'E'):
                    try:
                        p.edit_filelist()
                    except ValueError:
                        print >>sys.stderr, "Error during processiong of file list."
                        raise oscerr.UserAbort()
                elif resp in ('c', 'C'):
                    break
                else:
                    raise oscerr.UserAbort()
