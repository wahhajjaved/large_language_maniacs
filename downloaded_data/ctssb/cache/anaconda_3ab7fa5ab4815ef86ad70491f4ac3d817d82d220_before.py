#
# yuminstall.py
#
# Copyright (C) 2005, 2006, 2007  Red Hat, Inc.  All rights reserved.
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

from flags import flags

import sys
import os
import os.path
import shutil
import timer
import warnings
import types
import locale
import glob

import rpm
import rpmUtils
import urlgrabber.progress
import urlgrabber.grabber
from urlgrabber.grabber import URLGrabber, URLGrabError
import yum
import rhpl
from yum.constants import *
from yum.Errors import RepoError, YumBaseError, PackageSackError
from yum.yumRepo import YumRepository
from backend import AnacondaBackend
from product import productName, productStamp
from sortedtransaction import SplitMediaTransactionData
from constants import *
from image import *
from rhpl.translate import _

# specspo stuff
rpm.addMacro("_i18ndomains", "redhat-dist")

import logging
log = logging.getLogger("anaconda")

import urlparse
urlparse.uses_fragment.append('media')


import iutil
import isys

import whiteout

def size_string (size):
    def number_format(s):
        return locale.format("%s", s, 1)

    if size > 1024 * 1024:
        size = size / (1024*1024)
        return _("%s MB") %(number_format(size),)
    elif size > 1024:
        size = size / 1024
        return _("%s KB") %(number_format(size),)        
    else:
        if size == 1:
            return _("%s Byte") %(number_format(size),)                    
        else:
            return _("%s Bytes") %(number_format(size),)

class AnacondaCallback:

    def __init__(self, ayum, anaconda, instLog, modeText):
        self.repos = ayum.repos
        self.ts = ayum.ts
        self.ayum = ayum
        
        self.messageWindow = anaconda.intf.messageWindow
        self.waitWindow = anaconda.intf.waitWindow        
        self.progress = anaconda.id.instProgress
        self.progressWindowClass = anaconda.intf.progressWindow
        self.rootPath = anaconda.rootPath

        self.initWindow = None

        self.progressWindow = None
        self.lastprogress = 0
        self.incr = 20

        self.instLog = instLog
        self.modeText = modeText

        self.openfile = None
        self.inProgressPo = None

    def setSizes(self, numpkgs, totalSize, totalFiles):
        self.numpkgs = numpkgs
        self.totalSize = totalSize
        self.totalFiles = totalFiles

        self.donepkgs = 0
        self.doneSize = 0
        self.doneFiles = 0
        

    def callback(self, what, amount, total, h, user):
        # first time here means we should pop the window telling
        # user to wait until we get here
        if self.initWindow is not None:
            self.initWindow.pop()
            self.initWindow = None

        if what == rpm.RPMCALLBACK_TRANS_START:
            # step 6 is the bulk of the ts processing time
            if amount == 6:
                self.progressWindow = \
                    self.progressWindowClass (_("Processing"), 
                                              _("Preparing transaction from installation source..."),
                                              total)
                try:
                    self.incr = total / 10
                except:
                    pass

        if what == rpm.RPMCALLBACK_TRANS_PROGRESS:
            if self.progressWindow and amount > self.lastprogress + self.incr:
                self.progressWindow.set(amount)
                self.lastprogress = amount

        if what == rpm.RPMCALLBACK_TRANS_STOP and self.progressWindow:
            self.progressWindow.pop()

        if what == rpm.RPMCALLBACK_INST_OPEN_FILE:
            (hdr, rpmloc) = h
            # hate hate hate at epochs...
            epoch = hdr['epoch']
            if epoch is not None:
                epoch = str(epoch)
            txmbrs = self.ayum.tsInfo.matchNaevr(hdr['name'], hdr['arch'],
                                                 epoch, hdr['version'],
                                                 hdr['release'])
            if len(txmbrs) == 0:
                raise RuntimeError, "Unable to find package %s-%s-%s.%s" %(hdr['name'], hdr['version'], hdr['release'], hdr['arch'])
            po = txmbrs[0].po

            repo = self.repos.getRepo(po.repoid)

            s = _("<b>Installing %s</b> (%s)\n") %(str(po), size_string(hdr['size']))
            s += (hdr['summary'] or "")
            self.progress.set_label(s)

            nvra = str("%s" %(po,))
            self.instLog.write(self.modeText % (nvra,))

            self.instLog.flush()
            self.openfile = None
            
            if os.path.exists("%s/var/cache/yum/anaconda-upgrade/packages/%s" 
                              %(self.rootPath,os.path.basename(po.localPkg()))):
                try:
                    f = open("%s/var/cache/yum/anaconda-upgrade/packages/%s" %(self.rootPath,os.path.basename(po.localPkg())), 'r')
                    self.openfile = f
                    log.info("using already downloaded package for %s" %(po,))
                except:
                    pass

            while self.openfile is None:
                try:
                    fn = repo.getPackage(po)

                    f = open(fn, 'r')
                    self.openfile = f
                except yum.Errors.NoMoreMirrorsRepoError:
                    self.ayum._handleFailure(po)
                except yum.Errors.RepoError, e:
                    continue
            self.inProgressPo = po

            return self.openfile.fileno()

        elif what == rpm.RPMCALLBACK_INST_CLOSE_FILE:
            (hdr, rpmloc) = h

            fn = self.openfile.name
            self.openfile.close()
            self.openfile = None

            repo = self.repos.getRepo(self.inProgressPo.repoid)
            if (len(filter(lambda u: u.startswith("file:"), repo.baseurl)) == 0 
                or os.path.dirname(fn) == "%s/var/cache/yum/anaconda-upgrade/packages" %(self.rootPath,)):
                try:
                    os.unlink(fn)
                except OSError, e:
                    log.debug("unable to remove file %s" %(e,))
            self.inProgressPo = None

            self.donepkgs += 1
            self.doneSize += hdr['size']/1024.0
            self.doneFiles += len(hdr[rpm.RPMTAG_BASENAMES])

            self.progress.set_label("")
            self.progress.set_text(_("%s of %s packages completed")
                                   %(self.donepkgs, self.numpkgs))
            self.progress.set_fraction(float(self.doneSize / self.totalSize))
            self.progress.processEvents()

        # FIXME: we should probably integrate this into the progress bar
        # and actually show progress on cleanups.....
        elif what in (rpm.RPMCALLBACK_UNINST_START,
                      rpm.RPMCALLBACK_UNINST_STOP):
            if self.initWindow is None:
                self.initWindow = self.waitWindow(_("Finishing upgrade"),
                                                  _("Finishing upgrade process.  This may take a little while..."))
            else:
                self.initWindow.refresh()

        else:
            pass

        self.progress.processEvents()

class AnacondaYumRepo(YumRepository):
    def __init__( self, uri=None, mirrorlist=None,
                  repoid='anaconda%s' % productStamp,
                  root = "/mnt/sysimage/", addon=True):
        YumRepository.__init__(self, repoid)
        conf = yum.config.RepoConf()
        for k, v in conf.iteritems():
            if v or not self.getAttribute(k):
                self.setAttribute(k, v)
        self.gpgcheck = False
        #self.gpgkey = "%s/RPM-GPG-KEY-fedora" % (method, )
        self.keepalive = False
        self.addon = addon

        if type(uri) == types.ListType:
            self.baseurl = uri
        else:
            self.baseurl = [ uri ]

        if mirrorlist:
            self.mirrorlist = mirrorlist

        self.setAttribute('cachedir', '/tmp/cache/')
        self.setAttribute('pkgdir', root)
        self.setAttribute('hdrdir', '/tmp/cache/headers')

    def dirSetup(self):
        YumRepository.dirSetup(self)
        if not os.path.isdir(self.hdrdir):
            os.makedirs(self.hdrdir, mode=0755)

class YumSorter(yum.YumBase):
    def _transactionDataFactory(self):
        return SplitMediaTransactionData()

class AnacondaYum(YumSorter):
    def __init__(self, anaconda):
        YumSorter.__init__(self)
        self.anaconda = anaconda
        self._loopbackFile = None

        # The loader mounts the first disc for us, so don't remount it.
        self.currentMedia = 1
        self.mediagrabber = self.mediaHandler

        # Only needed for hard drive and nfsiso installs.
        self._discImages = {}

        # Where is the source media mounted?  isodir only matters if we are
        # doing NFS or HD image installs, and points to the directory where
        # the ISO images themselves may be found.  tree always points to the
        # directory where Packages/ is located.
        self.tree = "/mnt/source"

        if os.path.ismount("/mnt/isodir"):
            self.isodir = "/mnt/isodir"
        else:
            self.isodir = None

        self.doConfigSetup(root=anaconda.rootPath)
        self.conf.installonlypkgs = []
        self.macros = {}

        if flags.selinux:
            for directory in ("/tmp/updates", "/mnt/source/RHupdates",
                        "/etc/selinux/targeted/contexts/files",
                        "/etc/security/selinux/src/policy/file_contexts",
                        "/etc/security/selinux"):
                fn = "%s/file_contexts" %(directory,)
                if os.access(fn, os.R_OK):
                    break
            self.macros["__file_context_path"] = fn
        else:
            self.macros["__file_context_path"]  = "%{nil}"

        self.macros["_dependency_whiteout"] = whiteout.whiteout

        self.updates = []
        self.localPackages = []

    def systemMounted(self, fsset, chroot):
        if not os.path.exists("%s/images/stage2.img" %(self.tree,)):
            log.debug("Not copying stage2.img as we can't find it")
            return

        if self.isodir or self.anaconda.mediaDevice:
            self._loopbackFile = "%s%s/rhinstall-stage2.img" % (chroot,
                                 fsset.filesystemSpace(chroot)[0][0])

            try:
                win = self.anaconda.intf.waitWindow (_("Copying File"),
                        _("Transferring install image to hard drive..."))
                shutil.copyfile("%s/images/stage2.img" % (self.tree,),
                                self._loopbackFile)
                win.pop()
            except Exception, e:
                if win:
                    win.pop()

                log.critical("error transferring stage2.img: %s" %(e,))

                if isinstance(e, IOError) and e.errno == 5:
                    msg = _("An error occurred transferring the install image "
                            "to your hard drive.  This is probably due to "
                            "bad media.")
                else:
                    msg = _("An error occurred transferring the install image "
                            "to your hard drive. You are probably out of disk "
                            "space.")

                self.anaconda.intf.messageWindow(_("Error"), msg)
                os.unlink(self._loopbackFile)
                return 1
        else:
            self._loopbackFile = "%s/images/stage2.img" % self.tree

        isys.lochangefd("/dev/loop0", self._loopbackFile)

    def mediaHandler(self, *args, **kwargs):
        mediaid = kwargs["mediaid"]
        discnum = kwargs["discnum"]
        relative = kwargs["relative"]

        # The package exists on media other than what's mounted right now.
        if discnum != self.currentMedia:
            log.info("switching from media #%s to #%s for %s" %
                     (self.currentMedia, discnum, relative))

            # Unmount any currently mounted ISO images and mount the one
            # containing the requested packages.
            if self.isodir:
                umountImage(self.tree, self.currentMedia)
                self.currentMedia = None

                # mountDirectory checks before doing anything, so it's safe to
                # call this repeatedly.
                mountDirectory(self.isodir, self.anaconda.methodstr,
                               self.anaconda.intf.messageWindow)

                discImages = mountImage(self.isodir, self.tree, discnum,
                                        self.anaconda.intf.messageWindow,
                                        discImages=self._discImages)
                self.currentMedia = discnum
            else:
                if os.access("%s/.discinfo" % self.tree, os.R_OK):
                    f = open("%s/.discinfo" % self.tree)
                    timestamp = f.readline().strip()
                    f.close()
                else:
                    timestamp = self.timestamp

                if self.timestamp is None:
                    self.timestamp = timestamp

                # If self.currentMedia is None, then we shouldn't have anything
                # mounted.  double-check by trying to unmount, but we don't want
                # to get into a loop of trying to unmount forever.  If
                # self.currentMedia is set, then it should still be mounted and
                # we want to loop until it unmounts successfully
                if self.currentMedia is None:
                    try:
                        isys.umount(self.tree)
                    except:
                        pass
                else:
                    unmountCD(self.tree, self.anaconda.intf.messageWindow)
                    self.currentMedia = None

                isys.ejectCdrom(self.anaconda.mediaDevice)

                while True:
                    if self.anaconda.intf:
                        self.anaconda.intf.beep()

                    self.anaconda.intf.messageWindow(_("Change Disc"),
                        _("Please insert %s disc %d to continue.") % (productName,
                                                                      discnum))

                    try:
                        if isys.mount(self.anaconda.mediaDevice, self.tree,
                                      fstype = "iso9660", readOnly = 1):
                            time.sleep(3)
                            isys.mount(self.anaconda.mediaDevice, self.tree,
                                       fstype = "iso9660", readOnly = 1)

                        if verifyMedia(self.tree, discnum, self.timestamp):
                            self.currentMedia = discnum
                            break

                        if not done:
                            self.anaconda.intf.messageWindow(_("Wrong Disc"),
                                    _("That's not the correct %s disc.")
                                      % (productName,))
                            isys.umount(self.tree)
                            isys.ejectCdrom(self.anaconda.mediaDevice)
                    except:
                        self.anaconda.intf.messageWindow(_("Error"),
                                _("Unable to access the disc."))

        ug = URLGrabber(checkfunc=kwargs["checkfunc"])
        ug.urlgrab("%s/%s" % (self.tree, kwargs["relative"]), kwargs["local"],
                   text=kwargs["text"], range=kwargs["range"], copy_local=1)
        return kwargs["local"]

    def doConfigSetup(self, fn='/etc/yum.conf', root='/'):
        self.conf = yum.config.YumConf()
        self.conf.installroot = root
        self.conf.reposdir=["/tmp/repos.d"]
        self.conf.logfile="/tmp/yum.log"
        self.conf.obsoletes=True
        self.conf.cache=0
        self.conf.cachedir = '/tmp/cache/'
        self.conf.metadata_expire = 0

        # set up logging to log to our logs
        ylog = logging.getLogger("yum")
        map(lambda x: ylog.addHandler(x), log.handlers)

        # add default repos
        for (name, uri) in self.anaconda.id.instClass.getPackagePaths(self.anaconda.methodstr).items():
            repo = AnacondaYumRepo(uri, addon=False,
                                   repoid="anaconda-%s-%s" %(name,
                                                             productStamp),
                                   root = root)
            repo.cost = 100

            if self.anaconda.mediaDevice or self.isodir:
                repo.mediaid = getMediaId(self.tree)
                log.info("set mediaid of repo to: %s" % repo.mediaid)

            repo.enable()
            self.repos.add(repo)

        extraRepos = []

        # add some additional not enabled by default repos.
        # FIXME: this is a hack and should probably be integrated
        # with the above
        for (name, (uri, mirror)) in self.anaconda.id.instClass.repos.items():
            rid = name.replace(" ", "")
            repo = AnacondaYumRepo(uri=uri, mirrorlist=mirror, repoid=rid,
                                   root=root, addon=False)
            repo.name = name
            repo.disable()
            extraRepos.append(repo)

        if self.anaconda.id.extraModules:
            for d in glob.glob("/tmp/DD-*/rpms"):
                dirname = os.path.basename(os.path.dirname(d))
                rid = "anaconda-%s" % dirname

                repo = AnacondaYumRepo(uri="file:///%s" % d, repoid=rid,
                                       root=root, addon=False)
                repo.name = "Driver Disk %s" % dirname.split("-")[1]
                repo.enable()
                extraRepos.append(repo)

        if self.anaconda.isKickstart:
            for ksrepo in self.anaconda.id.ksdata.repo.repoList:
                repo = AnacondaYumRepo(uri=ksrepo.baseurl,
                                       mirrorlist=ksrepo.mirrorlist,
                                       repoid=ksrepo.name)
                repo.name = ksrepo.name
                repo.enable()
                extraRepos.append(repo)

        for repo in extraRepos:
            try:
                self.repos.add(repo)
                log.info("added repository %s with URL %s" % (repo.name, repo.mirrorlist or repo.baseurl))
            except yum.Errors.DuplicateRepoError, e:
                log.warning("ignoring duplicate repository %s with URL %s" % (repo.name, repo.mirrorlist or repo.baseurl))

        self.doPluginSetup(searchpath=["/usr/lib/yum-plugins",
                                       "/tmp/updates/yum-plugins",
                                       "/mnt/source/RHupdates/yum-plugins"], 
                           confpath=["/etc/yum/pluginconf.d",
                                     "/tmp/updates/pluginconf.d",
                                     "/mnt/source/RHupdates/pluginconf.d"])
        self.plugins.run('init')

        self.repos.setCacheDir('/tmp/cache')

    def downloadHeader(self, po):
        while True:
            # retrying version of download header
            try:
                YumSorter.downloadHeader(self, po)
            except yum.Errors.NoMoreMirrorsRepoError:
                self._handleFailure(po)
            except yum.Errors.RepoError, e:
                continue
            else:
                break

    def _handleFailure(self, package):
        pkgFile = os.path.basename(package.returnSimple('relativepath'))
        rc = self.anaconda.intf.messageWindow(_("Error"),
                   _("The file %s cannot be opened.  This is due to a missing "
                     "file, a corrupt package or corrupt media.  Please "
                     "verify your installation source.\n\n"
                     "If you exit, your system will be left in an inconsistent "
                     "state that will likely require reinstallation.\n\n") %
                                              (pkgFile,),
                                    type="custom", custom_icon="error",
                                    custom_buttons=[_("Re_boot"), _("_Retry")])

        if rc == 0:
            sys.exit(0)

    def mirrorFailureCB (self, obj, *args, **kwargs):
        # This gets called when a mirror fails, but it cannot know whether
        # or not there are other mirrors left to try, since it cannot know
        # which mirror we were on when we started this particular download. 
        # Whenever we have run out of mirrors the grabber's get/open/retrieve
        # method will raise a URLGrabError exception with errno 256.
        grab = self.repos.getRepo(kwargs["repo"]).grab
        log.warning("Failed to get %s from mirror %d/%d, "
                    "or downloaded file is corrupt" % (obj.url, grab._next + 1,
                                                       len(grab.mirrors)))

        if self.currentMedia:
            unmountCD(self.tree, self.anaconda.intf.messageWindow)
            self.currentMedia = None

    def urlgrabberFailureCB (self, obj, *args, **kwargs):
        log.warning("Try %s/%s for %s failed" % (obj.tries, obj.retry, obj.url))

        delay = 0.25*(2**(obj.tries-1))
        if delay > 1:
            w = anaconda.intf.waitWindow(_("Retrying"), _("Retrying package download..."))
            time.sleep(delay)
            w.pop()
        else:
            time.sleep(delay)

    def getDownloadPkgs(self):
        downloadpkgs = []
        totalSize = 0
        totalFiles = 0
        for txmbr in self.tsInfo.getMembers():
            if txmbr.ts_state in ['i', 'u']:
                po = txmbr.po
            else:
                continue

            if po:
                totalSize += int(po.returnSimple("installedsize")) / 1024
                for filetype in po.returnFileTypes():
                    totalFiles += len(po.returnFileEntries(ftype=filetype))
                downloadpkgs.append(po)

        return (downloadpkgs, totalSize, totalFiles)

    def setColor(self):
        if (rpmUtils.arch.canonArch.startswith("ppc64") or
        rpmUtils.arch.canonArch in ("s390x", "sparc64", "x86_64", "ia64")):
            self.ts.ts.setColor(3)

    def run(self, instLog, cb, intf, id):
        def mediasort(a, b):
            # sort so that first CD comes first, etc.  -99 is a magic number
            # to tell us that the cd should be last
            if a == -99:
                return 1
            elif b == -99:
                return -1
            if a < b:
                return -1
            elif a > b:
                return 1
            return 0

        self.initActionTs()
        if id.getUpgrade():
            self.ts.ts.setProbFilter(~rpm.RPMPROB_FILTER_DISKSPACE)
        self.setColor()

        # If we don't have any required media assume single disc
        if self.tsInfo.reqmedia == {}:
            self.tsInfo.reqmedia[0] = None
        mkeys = self.tsInfo.reqmedia.keys()
        mkeys.sort(mediasort)
        for i in mkeys:
            self.tsInfo.curmedia = i
            if i > 0:
                pkgtup = self.tsInfo.reqmedia[i][0]
            self.populateTs(keepold=0)
            self.ts.check()
            self.ts.order()

            if self._run(instLog, cb, intf) == DISPATCH_BACK:
                self.tsInfo.curmedia = None
                return DISPATCH_BACK

    def _run(self, instLog, cb, intf):
        # set log fd.  FIXME: this is ugly.  see changelog entry from 2005-09-13
        self.ts.ts.scriptFd = instLog.fileno()
        rpm.setLogFile(instLog)

        uniqueProbs = {}
        spaceneeded = {}
        spaceprob = ""
        fileConflicts = []
        fileprob = ""

        try:
            self.runTransaction(cb=cb)
        except YumBaseError, probs:
            # FIXME: we need to actually look at these problems...
            probTypes = { rpm.RPMPROB_NEW_FILE_CONFLICT : _('file conflicts'),
                          rpm.RPMPROB_FILE_CONFLICT : _('file conflicts'),
                          rpm.RPMPROB_OLDPACKAGE: _('older package(s)'),
                          rpm.RPMPROB_DISKSPACE: _('insufficient disk space'),
                          rpm.RPMPROB_DISKNODES: _('insufficient disk inodes'),
                          rpm.RPMPROB_CONFLICT: _('package conflicts'),
                          rpm.RPMPROB_PKG_INSTALLED: _('package already installed'),
                          rpm.RPMPROB_REQUIRES: _('required package'),
                          rpm.RPMPROB_BADARCH: _('package for incorrect arch'),
                          rpm.RPMPROB_BADOS: _('package for incorrect os'),
            }

            for (descr, (type, mount, need)) in probs.value: # FIXME: probs.value???
                log.error("%s: %s" %(probTypes[type], descr))
                if not uniqueProbs.has_key(type) and probTypes.has_key(type):
                    uniqueProbs[type] = probTypes[type]

                if type == rpm.RPMPROB_DISKSPACE:
                    spaceneeded[mount] = need
                elif type in [rpm.RPMPROB_NEW_FILE_CONFLICT, rpm.RPMPROB_FILE_CONFLICT]:
                    fileConflicts.append(descr)

            if spaceneeded:
                spaceprob = _("You need more space on the following "
                              "file systems:\n")

                for (mount, need) in spaceneeded.items():
                    log.info("(%s, %s)" %(mount, need))

                    if mount.startswith("/mnt/sysimage/"):
                        mount.replace("/mnt/sysimage", "")
                    elif mount.startswith("/mnt/sysimage"):
                        mount = "/" + mount.replace("/mnt/sysimage", "")

                    spaceprob += "%d M on %s\n" % (need / (1024*1024), mount)
            elif fileConflicts:
                fileprob = _("There were file conflicts when checking the "
                             "packages to be installed:\n%s\n") % ("\n".join(fileConflicts),)

            msg = _("There was an error running your transaction for "
                    "the following reason(s): %s.\n") % ', '.join(uniqueProbs.values())

            if len(self.anaconda.backend.getRequiredMedia()) > 1:
                intf.detailedMessageWindow(_("Error Running Transaction"),
                   msg, spaceprob + "\n" + fileprob, type="custom",
                   custom_icon="error", custom_buttons=[_("_Exit installer")])
                sys.exit(1)
            else:
                rc = intf.detailedMessageWindow(_("Error running transaction"),
                        msg, spaceprob + "\n" + fileprob, type="custom",
                        custom_icon="error",
                        custom_buttons=[_("_Back"), _("_Exit installer")])

            if rc == 1:
                sys.exit(1)
            else:
                self._undoDepInstalls()
                return DISPATCH_BACK

    def doMacros(self):
        for (key, val) in self.macros.items():
            rpm.addMacro(key, val)

    def simpleDBInstalled(self, name, arch=None):
        # FIXME: doing this directly instead of using self.rpmdb.installed()
        # speeds things up by 400%
        mi = self.ts.ts.dbMatch('name', name)
        if mi.count() == 0:
            return False
        if arch is None:
            return True
        if arch in map(lambda h: h['arch'], mi):
            return True
        return False

    def isPackageInstalled(self, name = None, epoch = None, version = None,
                           release = None, arch = None, po = None):
        # FIXME: this sucks.  we should probably suck it into yum proper
        # but it'll need a bit of cleanup first.
        if po is not None:
            (name, epoch, version, release, arch) = po.returnNevraTuple()

        installed = False
        if name and not (epoch or version or release or arch):
            installed = self.simpleDBInstalled(name)
        elif self.rpmdb.installed(name = name, epoch = epoch, ver = version,
                                rel = release, arch = arch):
            installed = True

        lst = self.tsInfo.matchNaevr(name = name, epoch = epoch,
                                     ver = version, rel = release,
                                     arch = arch)
        for txmbr in lst:
            if txmbr.output_state in TS_INSTALL_STATES:
                return True
        if installed and len(lst) > 0:
            # if we get here, then it was installed, but it's in the tsInfo
            # for an erase or obsoleted --> not going to be installed at end
            return False
        return installed

    def isGroupInstalled(self, grp):
        if grp.selected:
            return True
        elif grp.installed and not grp.toremove:
            return True
        return False

class YumBackend(AnacondaBackend):
    def __init__ (self, anaconda):
        AnacondaBackend.__init__(self, anaconda)
        self.supportsPackageSelection = True

    def complete(self, anaconda):
        try:
            isys.umount(self.ayum.tree)
        except Exception:
            pass

        if anaconda.mediaDevice:
            try:
                shutil.copyfile("%s/media.repo" % self.ayum.tree,
                                "%s/etc/yum.repos.d/%s-install-media.repo" %(anaconda.rootPath, productName))
            except Exception, e:
                log.debug("Error copying media.repo: %s" %(e,))

        if self.ayum._loopbackFile and (anaconda.mediaDevice or self.isodir):
            try:
                os.unlink(self.ayum._loopbackFile)
            except SystemError:
                pass

    def doInitialSetup(self, anaconda):
        if anaconda.id.getUpgrade():
           # FIXME: make sure that the rpmdb doesn't have stale locks :/
           self._resetRpmDb(anaconda.rootPath)

        iutil.writeRpmPlatform()
        self.ayum = AnacondaYum(anaconda)

    def doGroupSetup(self):
        # FIXME: this is a pretty ugly hack to make it so that we don't lose
        # groups being selected (#237708)
        sel = filter(lambda g: g.selected, self.ayum.comps.get_groups())
        self.ayum.doGroupSetup()
        # now we'll actually reselect groups..
        map(lambda g: self.selectGroup(g.groupid), sel)

        # FIXME: this is a bad hack to remove support for xen on xen (#179387)
        if os.path.exists("/proc/xen"):
            if self.ayum.comps._groups.has_key("virtualization"):
                del self.ayum.comps._groups["virtualization"]

        # FIXME: and another bad hack since our xen kernel is PAE
        if rpmUtils.arch.getBaseArch() == "i386" and "pae" not in iutil.cpuFeatureFlags():
            if self.ayum.comps._groups.has_key("virtualization"):
                del self.ayum.comps._groups["virtualization"]


    def doRepoSetup(self, anaconda, thisrepo = None, fatalerrors = True):
        # We want to call ayum.doRepoSetup one repo at a time so we have
        # some concept of which repo didn't set up correctly.
        repos = []

        # Don't do this if we're being called as a dispatcher step (instead
        # of being called when a repo is added via the UI) and we're going
        # back.
        if thisrepo is None and anaconda.dir == DISPATCH_BACK:
            return

        if thisrepo is not None:
            repos.append(self.ayum.repos.getRepo(thisrepo))
        else:
            repos.extend(self.ayum.repos.listEnabled())

        if not os.path.exists("/tmp/cache"):
            iutil.mkdirChain("/tmp/cache/headers")

        self.ayum.doMacros()

        longtasks = ( (self.ayum.doRepoSetup, 4),
                      (self.ayum.doSackSetup, 6) )

        tot = 0
        for t in longtasks:
            tot += t[1]

        for repo in repos:
            if repo.name is None:
                txt = _("Retrieving installation information...")
            else:
                txt = _("Retrieving installation information for %s...")%(repo.name)
            while 1:
                waitwin = YumProgress(anaconda.intf, txt, tot)
                self.ayum.repos.callback = waitwin

                try:
                    for (task, incr) in longtasks:
                        waitwin.set_incr(incr)
                        task(thisrepo = repo.id)
                        waitwin.next_task()
                    waitwin.pop()
                except yum.Errors.NoMoreMirrorsRepoError, e:
                    buttons = [_("_Abort"), _("_Retry")]
                except yum.Errors.RepoError, e:
                    buttons = [_("_Abort")]
                else:
                    break # success

                if anaconda.isKickstart:
                    buttons.append(_("_Continue"))

                waitwin.pop()
                if not fatalerrors:
                    raise RepoError, e

                rc = anaconda.intf.messageWindow(_("Error"),
                                   _("Unable to read package metadata. This may be "
                                     "due to a missing repodata directory.  Please "
                                     "ensure that your install tree has been "
                                     "correctly generated.  %s" % e),
                                     type="custom", custom_icon="error",
                                     custom_buttons=buttons)
                if rc == 0:
                    sys.exit(0)
                elif rc == 2:
                    self.ayum.repos.delete(repo.id)
                    break
                else:
                    continue

            # if we're in kickstart the repo may have been deleted just above
            try:
                self.ayum.repos.getRepo(repo.id)
            except RepoError:
                log.debug("repo %s has been removed" % (repo.id,))
                continue

            repo.setFailureObj(self.ayum.urlgrabberFailureCB)
            repo.setMirrorFailureObj((self.ayum.mirrorFailureCB, (),
                                     {"tsInfo":self.ayum.tsInfo, 
                                      "repo": repo.id}))

        while 1:
            try:
                self.doGroupSetup()
            except yum.Errors.NoMoreMirrorsRepoError:
                buttons = [_("Re_boot"), _("_Retry")]
            except (yum.Errors.GroupsError, yum.Errors.RepoError):
                buttons = [_("Re_boot")]
            else:
                break # success

            rc = anaconda.intf.messageWindow(_("Error"),
                                        _("Unable to read group information "
                                          "from repositories.  This is "
                                          "a problem with the generation "
                                          "of your install tree."),
                                        type="custom", custom_icon="error",
                                        custom_buttons = buttons)
            if rc == 0:
                sys.exit(0)
            else:
                self.ayum._setGroups(None)
                continue

        self._catchallCategory()
        self.ayum.repos.callback = None

    def _catchallCategory(self):
        # FIXME: this is a bad hack, but catch groups which aren't in
        # a category yet are supposed to be user-visible somehow.
        # conceivably should be handled by yum
        grps = {}
        for g in self.ayum.comps.groups:
            if g.user_visible:
                grps[g.groupid] = g

        for cat in self.ayum.comps.categories:
            for g in cat.groups:
                if grps.has_key(g):
                    del grps[g]

        if len(grps.keys()) == 0:
            log.info("no groups missing")
            return
        c = yum.comps.Category()
        c.name = _("Uncategorized")
        c._groups = grps
        c.categoryid = "uncategorized"
        self.ayum.comps._categories[c.categoryid] = c

    def getDefaultGroups(self, anaconda):
        langs = anaconda.id.instLanguage.getCurrentLangSearchList()
        rc = map(lambda x: x.groupid,
                 filter(lambda x: x.default, self.ayum.comps.groups))
        for g in self.ayum.comps.groups:
            if g.langonly in langs:
                rc.append(g.groupid)
        return rc

    def selectModulePackages(self, anaconda, kernelPkgName):
        (base, sep, ext) = kernelPkgName.partition("-")

        for (path, name) in anaconda.id.extraModules:
            if ext != "":
                moduleProvides = "kmod-%s-%s" % (name, ext)
            else:
                moduleProvides = "%s-kmod" % name

            pkgs = self.ayum.returnPackagesByDep(moduleProvides)

            if not pkgs:
                log.warning("Didn't find any package providing module %s" % name)

            for pkg in pkgs:
                if ext == "" and pkg.name == "kmod"+name:
                    log.info("selecting package %s for module %s" % (pkg.name, name))
                    self.ayum.install(po=pkg)
                elif ext != "" and pkg.name.find("-"+ext) != -1:
                    log.info("selecting package %s for module %s" % (pkg.name, name))
                    self.ayum.install(po=pkg)
                else:
                    continue

    def selectBestKernel(self, anaconda):
        """Find the best kernel package which is available and select it."""

        def getBestKernelByArch(pkgname, ayum):
            """Convenience func to find the best arch of a kernel by name"""
            pkgs = ayum.pkgSack.returnNewestByName(pkgname)
            if len(pkgs) == 0:
                return None
            pkgs = self.ayum.bestPackagesFromList(pkgs)
            if len(pkgs) == 0:
                return None
            return pkgs[0]

        foundkernel = False
        kpkg = getBestKernelByArch("kernel", self.ayum)

        # FIXME: this is a bit of a hack.  we shouldn't hard-code and
        # instead check by provides.  but alas.
        for k in ("kernel", "kernel-smp", "kernel-xen0", "kernel-xen",
                  "kernel-PAE"):
            if len(self.ayum.tsInfo.matchNaevr(name=k)) > 0:
                self.selectModulePackages(anaconda, k)
                foundkernel = True

        if not foundkernel and os.path.exists("/proc/xen"):
            try:
                kxen = getBestKernelByArch("kernel-xen", self.ayum)
                log.info("selecting kernel-xen package for kernel")
                foundkernel = True
            except PackageSackError:
                kxen = None
                log.debug("no kernel-xen package")
            else:
                self.ayum.install(po = kxen)
                self.selectModulePackages(anaconda, kxen.name)
                if len(self.ayum.tsInfo.matchNaevr(name="gcc")) > 0:
                    log.debug("selecting kernel-xen-devel")
                    self.selectPackage("kernel-xen-devel.%s" % (kxen.arch,))

        if not foundkernel and (isys.smpAvailable() or isys.htavailable()):
            try:
                ksmp = getBestKernelByArch("kernel-smp", self.ayum)
            except PackageSackError:
                ksmp = None
                log.debug("no kernel-smp package")

            if ksmp and ksmp.returnSimple("arch") == kpkg.returnSimple("arch"):
                foundkernel = True
                log.info("selected kernel-smp package for kernel")
                self.ayum.install(po=ksmp)
                self.selectModulePackages(anaconda, ksmp.name)

                if len(self.ayum.tsInfo.matchNaevr(name="gcc")) > 0:
                    log.debug("selecting kernel-smp-devel")
                    self.selectPackage("kernel-smp-devel.%s" % (kpkg.arch,))

        if not foundkernel and isys.isPaeAvailable():
            try:
                kpae = getBestKernelByArch("kernel-PAE", self.ayum)
            except PackageSackError:
                kpae = None
                log.debug("no kernel-PAE package")

            if kpae and kpae.returnSimple("arch") == kpkg.returnSimple("arch"):
                foundkernel = True
                log.info("select kernel-PAE package for kernel")
                self.ayum.install(po=kpae)
                self.selectModulePackages(anaconda, kpae.name)

                if len(self.ayum.tsInfo.matchNaevr(name="gcc")) > 0:
                    log.debug("selecting kernel-PAE-devel")
                    self.selectPackage("kernel-PAE-devel.%s" % (kpkg.arch,))

        if not foundkernel:
            log.info("selected kernel package for kernel")
            self.ayum.install(po=kpkg)
            self.selectModulePackages(anaconda, kpkg.name)

            if len(self.ayum.tsInfo.matchNaevr(name="gcc")) > 0:
                log.debug("selecting kernel-devel")
                self.selectPackage("kernel-devel.%s" % (kpkg.arch,))

    def selectBootloader(self):
        if rhpl.getArch() in ("i386", "x86_64"):
            self.selectPackage("grub")
        elif rhpl.getArch() == "s390":
            self.selectPackage("s390utils")
        elif rhpl.getArch() == "ppc":
            self.selectPackage("yaboot")
        elif rhpl.getArch() == "ia64":
            self.selectPackage("elilo")

    def selectFSPackages(self, fsset, diskset):
        for entry in fsset.entries:
            map(self.selectPackage, entry.fsystem.getNeededPackages())
            if entry.device.crypto:
                self.selectPackage("cryptsetup-luks")

        for disk in diskset.disks.keys():
            if isys.driveIsIscsi(disk):
                log.info("ensuring iscsi is installed")
                self.selectPackage("iscsi-initiator-utils")
                break

        if diskset.__class__.mpList:
            log.info("ensuring device-mapper-multipath is installed")
            self.selectPackage("device-mapper-multipath")
        if diskset.__class__.dmList:
            log.info("ensuring dmraid is installed")
            self.selectPackage("dmraid")


    # anaconda requires several programs on the installed system to complete
    # installation, but we have no guarantees that some of these will be
    # installed (they could have been removed in kickstart).  So we'll force
    # it.
    def selectAnacondaNeeds(self):
        for pkg in ['authconfig', 'chkconfig', 'mkinitrd', 'rhpl',
                    'system-config-firewall-tui']:
            self.selectPackage(pkg)

    def doPostSelection(self, anaconda):
        # Only solve dependencies on the way through the installer, not the way back.
        if anaconda.dir == DISPATCH_BACK:
            return

        dscb = YumDepSolveProgress(anaconda.intf, self.ayum)
        self.ayum.dsCallback = dscb

        # do some sanity checks for kernel and bootloader
        self.selectBestKernel(anaconda)
        self.selectBootloader()
        self.selectFSPackages(anaconda.id.fsset, anaconda.id.diskset)

        self.selectAnacondaNeeds()

        if anaconda.id.getUpgrade():
            from upgrade import upgrade_remove_blacklist
            self.upgradeFindPackages()
            for pkg in upgrade_remove_blacklist:
                pkgarch = None
                pkgnames = None
                if len(pkg) == 1:
                    pkgname = pkg[0]
                elif len(pkg) == 2:
                    pkgname, pkgarch = pkg
                if pkgname is None:
                    continue
                self.ayum.remove(name=pkgname, arch=pkgarch)
            self.ayum.update()

        try:
            while 1:
                try:
                    (code, msgs) = self.ayum.buildTransaction()
                except yum.Errors.NoMoreMirrorsRepoError, e:
                    buttons = [_("Re_boot"), _("_Retry")]
                except RepoError, e:
                    buttons = [_("Re_boot")]
                else:
                    break

                # FIXME: this message isn't ideal, but it'll do for now
                rc = anaconda.intf.messageWindow(_("Error"),
                               _("Unable to read package metadata. This may be "
                                 "due to a missing repodata directory.  Please "
                                 "ensure that your install tree has been "
                                 "correctly generated.  %s" % e),
                                 type="custom", custom_icon="error",
                                 custom_buttons=buttons)
                if rc == 0:
                    sys.exit(0)
                else:
                    continue

            (self.dlpkgs, self.totalSize, self.totalFiles)  = self.ayum.getDownloadPkgs()

            if not anaconda.id.getUpgrade():
                usrPart = anaconda.id.partitions.getRequestByMountPoint("/usr")
                if usrPart is not None:
                    largePart = usrPart
                else:
                    largePart = anaconda.id.partitions.getRequestByMountPoint("/")

                if largePart and \
                   largePart.getActualSize(anaconda.id.partitions, anaconda.id.diskset) < self.totalSize / 1024:
                    rc = anaconda.intf.messageWindow(_("Error"),
                                            _("Your selected packages require %d MB "
                                              "of free space for installation, but "
                                              "you do not have enough available.  "
                                              "You can change your selections or "
                                              "exit the installer." % (self.totalSize / 1024)),
                                            type="custom", custom_icon="error",
                                            custom_buttons=[_("_Back"), _("_Exit installer")])

                    if rc == 1:
                        sys.exit(1)
                    else:
                        self.ayum._undoDepInstalls()
                        return DISPATCH_BACK
        finally:
            dscb.pop()

        if anaconda.mediaDevice and not anaconda.isKickstart:
           rc = presentRequiredMediaMessage(anaconda)
           if rc == 0:
               rc2 = anaconda.intf.messageWindow(_("Reboot?"),
                                       _("The system will be rebooted now."),
                                       type="custom", custom_icon="warning",
                                       custom_buttons=[_("_Back"), _("_Reboot")])
               if rc2 == 1:
                   sys.exit(0)
               else:
                   return DISPATCH_BACK
           elif rc == 1: # they asked to go back
               return DISPATCH_BACK

        self.ayum.dsCallback = None

    def doPreInstall(self, anaconda):
        if anaconda.dir == DISPATCH_BACK:
            for d in ("/selinux", "/dev"):
                try:
                    isys.umount(anaconda.rootPath + d, removeDir = 0)
                except Exception, e:
                    log.error("unable to unmount %s: %s" %(d, e))
            return

            if flags.test:
                return

        # shorthand
        upgrade = anaconda.id.getUpgrade()

        if upgrade:
            # An old mtab can cause confusion (esp if loop devices are
            # in it).  Be extra special careful and delete any mtab first,
            # in case the user has done something funny like make it into
            # a symlink.
            if os.access(anaconda.rootPath + "/etc/mtab", os.F_OK):
                os.remove(anaconda.rootPath + "/etc/mtab")

            f = open(anaconda.rootPath + "/etc/mtab", "w+")
            f.close()

            # we really started writing modprobe.conf out before things were
            # all completely ready.  so now we need to nuke old modprobe.conf's
            # if you're upgrading from a 2.4 dist so that we can get the
            # transition right
            if (os.path.exists(anaconda.rootPath + "/etc/modules.conf") and
                os.path.exists(anaconda.rootPath + "/etc/modprobe.conf") and
                not os.path.exists(anaconda.rootPath + "/etc/modprobe.conf.anacbak")):
                log.info("renaming old modprobe.conf -> modprobe.conf.anacbak")
                os.rename(anaconda.rootPath + "/etc/modprobe.conf",
                          anaconda.rootPath + "/etc/modprobe.conf.anacbak")

        if self.ayum.systemMounted (anaconda.id.fsset, anaconda.rootPath):
            anaconda.id.fsset.umountFilesystems(anaconda.rootPath)
            return DISPATCH_BACK

        dirList = ['/var', '/var/lib', '/var/lib/rpm', '/tmp', '/dev', '/etc',
                   '/etc/sysconfig', '/etc/sysconfig/network-scripts',
                   '/etc/X11', '/root', '/var/tmp', '/etc/rpm', '/var/cache',
                   '/var/cache/yum', '/etc/modprobe.d']

        # If there are any protected partitions we want to mount, create their
        # mount points now.
        protected = anaconda.id.partitions.protectedPartitions()
        if protected:
            for protectedDev in protected:
                request = anaconda.id.partitions.getRequestByDeviceName(protectedDev)
                if request and request.mountpoint:
                    dirList.append(request.mountpoint)

        for i in dirList:
            try:
                os.mkdir(anaconda.rootPath + i)
            except os.error, (errno, msg):
                pass
#            log.error("Error making directory %s: %s" % (i, msg))

        self.initLog(anaconda.id, anaconda.rootPath)

        if flags.setupFilesystems:
            # setup /etc/rpm/platform for the post-install environment
            iutil.writeRpmPlatform(anaconda.rootPath)
            
            try:
                # FIXME: making the /var/lib/rpm symlink here is a hack to
                # workaround db->close() errors from rpm
                iutil.mkdirChain("/var/lib")
                for path in ("/var/tmp", "/var/lib/rpm"):
                    if os.path.exists(path) and not os.path.islink(path):
                        shutil.rmtree(path)
                    if not os.path.islink(path):
                        os.symlink("%s/%s" %(anaconda.rootPath, path), "%s" %(path,))
                    else:
                        log.warning("%s already exists as a symlink to %s" %(path, os.readlink(path),))
            except Exception, e:
                # how this could happen isn't entirely clear; log it in case
                # it does and causes problems later
                log.error("error creating symlink, continuing anyway: %s" %(e,))

            # SELinux hackery (#121369)
            if flags.selinux:
                try:
                    os.mkdir(anaconda.rootPath + "/selinux")
                except Exception, e:
                    pass
                try:
                    isys.mount("/selinux", anaconda.rootPath + "/selinux", "selinuxfs")
                except Exception, e:
                    log.error("error mounting selinuxfs: %s" %(e,))

            # we need to have a /dev during install and now that udev is
            # handling /dev, it gets to be more fun.  so just bind mount the
            # installer /dev
            log.warning("no dev package, going to bind mount /dev")
            isys.mount("/dev", "%s/dev" %(anaconda.rootPath,), bindMount = 1)
            if not upgrade:
                anaconda.id.fsset.mkDevRoot(anaconda.rootPath)

        # write out the fstab
        if not upgrade:
            anaconda.id.fsset.write(anaconda.rootPath)
            # rootpath mode doesn't have this file around
            if os.access("/etc/modprobe.d/anaconda", os.R_OK):
                shutil.copyfile("/etc/modprobe.d/anaconda", 
                                anaconda.rootPath + "/etc/modprobe.d/anaconda")
            anaconda.id.network.write(anaconda.rootPath)
            anaconda.id.iscsi.write(anaconda.rootPath)
            anaconda.id.zfcp.write(anaconda.rootPath)

        # make a /etc/mtab so mkinitrd can handle certain hw (usb) correctly
        f = open(anaconda.rootPath + "/etc/mtab", "w+")
        f.write(anaconda.id.fsset.mtab())
        f.close()

    def checkSupportedUpgrade(self, anaconda):
        if anaconda.dir == DISPATCH_BACK:
            return
        self._checkUpgradeVersion(anaconda)
        self._checkUpgradeArch(anaconda)

    def _resetRpmDb(self, rootPath):
        for rpmfile in ("__db.000", "__db.001", "__db.002", "__db.003"):
            try:
                os.unlink("%s/var/lib/rpm/%s" %(rootPath, rpmfile))
            except Exception, e:
                log.debug("error %s removing file: /var/lib/rpm/%s" %(e,rpmfile))

    def _checkUpgradeVersion(self, anaconda):
        # Figure out current version for upgrade nag and for determining weird
        # upgrade cases
        supportedUpgradeVersion = -1
        for pkgtup in self.ayum.rpmdb.whatProvides('redhat-release', None, None):
            n, a, e, v, r = pkgtup
            if supportedUpgradeVersion <= 0:
                val = rpmUtils.miscutils.compareEVR((None, '3', '1'),
                                                    (e, v,r))
                if val > 0:
                    supportedUpgradeVersion = 0
                else:
                    supportedUpgradeVersion = 1
                    break

        if productName.find("Red Hat Enterprise Linux") == -1:
            supportedUpgradeVersion = 1

        if supportedUpgradeVersion == 0:
            rc = anaconda.intf.messageWindow(_("Warning"),
                                    _("You appear to be upgrading from a system "
                                      "which is too old to upgrade to this "
                                      "version of %s.  Are you sure you wish to "
                                      "continue the upgrade "
                                      "process?") %(productName,),
                                    type = "yesno")
            if rc == 0:
                self._resetRpmDb(anaconda.rootPath)
                sys.exit(0)

    def _checkUpgradeArch(self, anaconda):
        # get the arch of the initscripts package
        pkgs = self.ayum.pkgSack.returnNewestByName('initscripts')
        if len(pkgs) == 0:
            log.info("no packages named initscripts")
            return
        pkgs = self.ayum.bestPackagesFromList(pkgs)
        if len(pkgs) == 0:
            log.info("no best package")
            return
        myarch = pkgs[0].arch

        log.info("initscripts is arch: %s" %(myarch,))
        for po in self.ayum.rpmdb.getProvides('initscripts'):
            log.info("po.arch is arch: %s" %(po.arch,))
            if po.arch != myarch:
                rc = anaconda.intf.messageWindow(_("Warning"),
                                        _("The arch of the release of %s you "
                                          "are upgrading to appears to be %s "
                                          "which does not match your previously "
                                          "installed arch of %s.  This is likely "
                                          "to not succeed.  Are you sure you "
                                          "wish to continue the upgrade process?")
                                        %(productName, myarch, po.arch),
                                        type="yesno")
                if rc == 0:
                    self._resetRpmDb(anaconda.rootPath)
                    sys.exit(0)
                else:
                    log.warning("upgrade between possibly incompatible "
                                "arches %s -> %s" %(po.arch, myarch))
                    break

    def doInstall(self, anaconda):
        log.info("Preparing to install packages")
        if flags.test:
            log.info("Test mode - not performing install")
            return

        if not anaconda.id.upgrade:
            rpm.addMacro("__dbi_htconfig",
                         "hash nofsync %{__dbi_other} %{__dbi_perms}")

        if anaconda.isKickstart and anaconda.id.ksdata.packages.excludeDocs:
            rpm.addMacro("_excludedocs", "1")

        cb = AnacondaCallback(self.ayum, anaconda,
                              self.instLog, self.modeText)
        cb.setSizes(len(self.dlpkgs), self.totalSize, self.totalFiles)

        cb.initWindow = anaconda.intf.waitWindow(_("Install Starting"),
                                        _("Starting install process.  This may take several minutes..."))

        rc = self.ayum.run(self.instLog, cb, anaconda.intf, anaconda.id)

        if cb.initWindow is not None:
            cb.initWindow.pop()

        self.instLog.close ()

        anaconda.id.instProgress = None

        if rc == DISPATCH_BACK:
            return DISPATCH_BACK

    def doPostInstall(self, anaconda):
        if flags.test:
            return

        if anaconda.id.getUpgrade():
            w = anaconda.intf.waitWindow(_("Post Upgrade"),
                                    _("Performing post upgrade configuration..."))
        else:
            w = anaconda.intf.waitWindow(_("Post Install"),
                                    _("Performing post install configuration..."))

        for tsmbr in self.ayum.tsInfo.matchNaevr(name='rhgb'):
            anaconda.id.bootloader.args.append("rhgb quiet")
            break

        for tsmbr in self.ayum.tsInfo.matchNaevr(name='gdm') + self.ayum.tsInfo.matchNaevr(name='kdm'):
            if anaconda.id.displayMode == 'g' and not flags.usevnc:
                anaconda.id.desktop.setDefaultRunLevel(5)
                break

        # XXX: write proper lvm config

        AnacondaBackend.doPostInstall(self, anaconda)
        w.pop()

    def kernelVersionList(self, rootPath="/"):
        kernelVersions = []
        
        # nick is used to generate the lilo name
        for (ktag, nick) in [ ('kernel-smp', 'smp'),
                              ('kernel-xen0', 'xen0'),
                              ('kernel-xenU', 'xenU'),
                              ('kernel-xen', 'xen'),
                              ('kernel-PAE', 'pae') ]:
            tag = ktag.rsplit('-', 1)[1]
            for tsmbr in filter(lambda p: p.output_state in TS_INSTALL_STATES, 
                                self.ayum.tsInfo.matchNaevr(name=ktag)):
                version = ( tsmbr.version + '-' + tsmbr.release + tag)
                kernelVersions.append((version, tsmbr.arch, nick))

        for tsmbr in filter(lambda p: p.output_state in TS_INSTALL_STATES,
                            self.ayum.tsInfo.matchNaevr(name='kernel')):
            version = ( tsmbr.version + '-' + tsmbr.release)
            kernelVersions.append((version, tsmbr.arch, 'base'))

        return kernelVersions

    def __getGroupId(self, group):
        """Get the groupid for the given name (english or translated)."""
        for g in self.ayum.comps.groups:
            if group == g.name:
                return g.groupid
            for trans in g.translated_name.values():
                if group == trans:
                    return g.groupid

    def isGroupSelected(self, group):
        try:
            grp = self.ayum.comps.return_group(group)
            if grp.selected: return True
        except yum.Errors.GroupsError, e:
            pass
        return False

    def _selectDefaultOptGroup(self, grpid, default, optional):
        retval = 0
        grp = self.ayum.comps.return_group(grpid)

        if not default:
            for pkg in grp.default_packages.keys():
                self.deselectPackage(pkg)
                retval -= 1

        if optional:
            for pkg in grp.optional_packages.keys():
                self.selectPackage(pkg)
                retval += 1

        return retval

    def selectGroup(self, group, *args):
        if args:
            default = args[0][0]
            optional = args[0][1]
        else:
            default = True
            optional = False

        try:
            mbrs = self.ayum.selectGroup(group)
            if len(mbrs) == 0 and self.isGroupSelected(group):
                return 1

            extras = self._selectDefaultOptGroup(group, default, optional)

            return len(mbrs) + extras
        except yum.Errors.GroupsError, e:
            # try to find out if it's the name or translated name
            gid = self.__getGroupId(group)
            if gid is not None:
                mbrs = self.ayum.selectGroup(gid)
                if len(mbrs) == 0 and self.isGroupSelected(gid):
                    return 1

                extras = self._selectDefaultOptGroup(group, default, optional)

                return len(mbrs) + extras
            else:
                log.debug("no such group %s" %(group,))
                return 0

    def deselectGroup(self, group, *args):
        try:
            self.ayum.deselectGroup(group)
        except yum.Errors.GroupsError, e:
            # try to find out if it's the name or translated name
            gid = self.__getGroupId(group)
            if gid is not None:
                self.ayum.deselectGroup(gid)
            else:
                log.debug("no such group %s" %(group,))

    def selectPackage(self, pkg, *args):
        try:
            mbrs = self.ayum.install(pattern=pkg)
            return len(mbrs)
        except yum.Errors.InstallError:
            log.debug("no package matching %s" %(pkg,))
            return 0
        
    def deselectPackage(self, pkg, *args):
        sp = pkg.rsplit(".", 2)
        txmbrs = []
        if len(sp) == 2:
            txmbrs = self.ayum.tsInfo.matchNaevr(name=sp[0], arch=sp[1])

        if len(txmbrs) == 0:
            txmbrs = self.ayum.tsInfo.matchNaevr(name=pkg)

        if len(txmbrs) > 0:
            map(lambda x: self.ayum.tsInfo.remove(x.pkgtup), txmbrs)
        else:
            log.debug("no such package %s" %(pkg,))

    def upgradeFindPackages(self):
        # check the installed system to see if the packages just
        # are not newer in this release.
        # Dictionary of newer package to tuple of old packages
        packageMap = { "firefox": ("mozilla", "netscape-navigator", "netscape-communicator") }

        for new, oldtup in packageMap.iteritems():
            if self.ayum.isPackageInstalled(new):
                continue
            found = 0
            for p in oldtup:
                if self.ayum.rpmdb.installed(name=p):
                    found = 1
                    break
            if found > 0:
                self.selectPackage(new)

    def writeKS(self, f):
        # Only write out lines for repositories that weren't added
        # automatically by anaconda.
        for repo in filter(lambda r: r.addon, self.ayum.repos.listEnabled()):
            line = "repo --name=%s " % (repo.name or repo.repoid)

            if repo.baseurl:
                line += " --baseurl=%s\n" % repo.baseurl[0]
            else:
                line += " --mirrorlist=%s\n" % repo.mirrorlist

            f.write(line)

    def writePackagesKS(self, f, anaconda):
        if anaconda.isKickstart:
            f.write(anaconda.id.ksdata.packages.__str__())
            return

        groups = []
        installed = []
        removed = []

        # Faster to grab all the package names up front rather than call
        # searchNevra in the loop below.
        allPkgNames = map(lambda pkg: pkg.name, self.ayum.pkgSack.returnPackages())
        allPkgNames.sort()

        # On CD/DVD installs, we have one transaction per CD and will end up
        # checking allPkgNames against a very short list of packages.  So we
        # have to reset to media #0, which is an all packages transaction.
        old = self.ayum.tsInfo.curmedia
        self.ayum.tsInfo.curmedia = 0

        self.ayum.tsInfo.makelists()
        txmbrNames = map (lambda x: x.name, self.ayum.tsInfo.getMembers())

        self.ayum.tsInfo.curmedia = old

        if len(self.ayum.tsInfo.instgroups) == 0 and len(txmbrNames) == 0:
            return

        f.write("\n%packages\n")

        for grp in filter(lambda x: x.selected, self.ayum.comps.groups):
            groups.append(grp.groupid)

            defaults = grp.default_packages.keys() + grp.mandatory_packages.keys()
            optionals = grp.optional_packages.keys()

            for pkg in filter(lambda x: x in defaults and (not x in txmbrNames and x in allPkgNames), grp.packages):
                removed.append(pkg)

            for pkg in filter(lambda x: x in txmbrNames, optionals):
                installed.append(pkg)

        for grp in groups:
            f.write("@%s\n" % grp)

        for pkg in installed:
            f.write("%s\n" % pkg)

        for pkg in removed:
            f.write("-%s\n" % pkg)

    def writeConfiguration(self):
        return

    def getRequiredMedia(self):
        return self.ayum.tsInfo.reqmedia.keys()

class YumProgress:
    def __init__(self, intf, text, total):
        window = intf.progressWindow(_("Installation Progress"), text,
                                     total, 0.01)
        self.window = window
        self.current = 0
        self.incr = 1
        self.total = total
        self.popped = False

    def set_incr(self, incr):
        self.incr = incr

    def progressbar(self, current, total, name=None):
        if not self.popped:
            self.window.set(float(current)/total * self.incr + self.current)
        else:
            warnings.warn("YumProgress.progressbar called when popped",
                          RuntimeWarning, stacklevel=2) 

    def pop(self):
        self.window.pop()
        self.popped = True

    def next_task(self, current = None):
        if current:
            self.current = current
        else:
            self.current += self.incr
        if not self.popped:
            self.window.set(self.current)
        else:
            warnings.warn("YumProgress.set called when popped",
                          RuntimeWarning, stacklevel=2)             

class YumDepSolveProgress:
    def __init__(self, intf, ayum = None):
        window = intf.progressWindow(_("Dependency Check"),
        _("Checking dependencies in packages selected for installation..."),
                                     1.0, 0.01)
        self.window = window

        self.numpkgs = None
        self.loopstart = None
        self.incr = None
        self.ayum = ayum

        self.restartLoop = self.downloadHeader = self.transactionPopulation = self.refresh
        self.procReq = self.procConflict = self.unresolved = self.noop

    def tscheck(self, num = None):
        self.refresh()
        if num is None and self.ayum is not None and self.ayum.tsInfo is not None:
            num = len(self.ayum.tsInfo.getMembers())

        if num:
            self.numpkgs = num
            self.loopstart = self.current
            self.incr = (1.0 / num) * ((1.0 - self.loopstart) / 2)

    def pkgAdded(self, *args):
        if self.numpkgs:
            self.set(self.current + self.incr)

    def noop(self, *args, **kwargs):
        pass

    def refresh(self, *args):
        self.window.refresh()

    def set(self, value):
        self.current = value
        self.window.set(self.current)

    def start(self):
        self.set(0.0)
        self.refresh()

    def end(self):
        self.window.set(1.0)
        self.window.refresh()

    def pop(self):
        self.window.pop()
