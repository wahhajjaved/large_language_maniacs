#-*- coding: utf-8 -*-
#
#  IEDWorkflow.py
#  AutoDMG
#
#  Created by Per Olofsson on 2013-10-24.
#  Copyright (c) 2013 Per Olofsson, University of Gothenburg. All rights reserved.
#

from Foundation import *
import os.path
import platform
import glob
import grp
import traceback

from IEDLog import *
from IEDSocketListener import *
from IEDDMGHelper import *


VERSIONPLIST_PATH = u"System/Library/CoreServices/SystemVersion.plist"


class IEDWorkflow(NSObject):
    """The workflow contains the logic needed to setup, execute, and report
    the result of the build.
    """
    
    def init(self):
        self = super(IEDWorkflow, self).init()
        if self is None:
            return None
        
        # Helper class for managing disk images.
        self.dmgHelper = IEDDMGHelper.alloc().initWithDelegate_(self)
        
        # Socket for communicating with helper processes.
        self.listener = IEDSocketListener.alloc().init()
        self.listenerPath = self.listener.listenOnSocket_withDelegate_(u"/tmp/se.gu.it.IEDSocketListener", self)
        
        # State for the workflow.
        self._outputPath = None
        self.installerMountPoint = None
        self.additionalPackages = list()
        self.attachedPackageDMGs = dict()
        
        return self
    
    def initWithDelegate_(self, delegate):
        self = self.init()
        if self is None:
            return None
        
        self.delegate = delegate
        
        return self
    
    # Helper methods.
    
    def cleanup(self):
        LogDebug(u"cleanup")
        self.listener.stopListening()
        self.dmgHelper.detachAll_(None)
    
    def handleDetachResult_(self, result):
        if result[u"success"] == True:
            try:
                del self.attachedPackageDMGs[result[u"dmg-path"]]
            except KeyError:
                pass
        else:
            self.delegate.detachFailed_details_(result[u"dmg-path"], result[u"error-message"])
    
    def detachInstallerDMGs(self):
        LogDebug(u"Detaching installer DMGs")
        for dmgPath, mountPoint in self.attachedPackageDMGs.iteritems():
            self.dmgHelper.detach_selector_(dmgPath, self.handleDetachResult_)
    
    
    
    # External state of controller.
    
    def hasSource(self):
        return self.installerMountPoint is not None
    
    
    
    # Common delegate methods:
    #
    #     - (void)displayAlert:(NSString *)message text:(NSString *)text
    #     - (void)detachFailed:(NSString *)message details:(NSString *)details
    
    
    
    # Set a new installer source.
    #
    # Delegate methods:
    #
    #     - (void)ejectingSource
    #     - (void)examiningSource:(NSString *)path
    #     - (void)sourceSucceeded:(NSDictionary *)info
    #     - (void)sourceFailed:(NSString *)message text:(NSString *)text
    
    def setSource_(self, path):
        LogDebug(u"setSource:%@", path)
        
        self.newSourcePath = path
        if self.installerMountPoint:
            self.delegate.ejectingSource()
            self.dmgHelper.detachAll_(self.continueSetSource_)
        else:
            self.continueSetSource_({})
    
    def continueSetSource_(self, failedUnmounts):
        LogDebug(u"continueSetSource:%@", failedUnmounts)
        
        if failedUnmounts:
            text = u"\n".join(u"%s: %s" % (dmg, error) for dmg, error in failedUnmounts.iteritems())
            self.delegate.displayAlert_text_(u"Failed to eject dmgs", text)
        
        self.delegate.examiningSource_(self.newSourcePath)
        
        self.installerMountPoint = None
        self.baseSystemMountedFromPath = None
        self.installESDPath = os.path.join(self.newSourcePath, u"Contents/SharedSupport/InstallESD.dmg")
        self.dmgHelper.attach_selector_(self.installESDPath, self.handleSourceMountResult_)
    
    # handleSourceMountResult: may be called twice, once for InstallESD.dmg
    # and once for BaseSystem.dmg.
    def handleSourceMountResult_(self, result):
        LogDebug(u"handleSourceMountResult:%@", result)
        
        if result[u"success"] == False:
            self.delegate.sourceFailed_text_(u"Failed to mount %s" % result[u"dmg-path"],
                                             result[u"error-message"])
            return
        
        mountPoint = result[u"mount-point"]
        
        # Don't set this again since 10.9 mounts BaseSystem.dmg after InstallESD.dmg.
        if self.installerMountPoint is None:
            self.installerMountPoint = mountPoint
        
        baseSystemPath = os.path.join(mountPoint, u"BaseSystem.dmg")
        
        if os.path.exists(os.path.join(mountPoint, VERSIONPLIST_PATH)):
            # FIXME: check Packages/OSInstall.mpkg
            self.checkVersion_(mountPoint)
        elif os.path.exists(baseSystemPath):
            self.baseSystemMountedFromPath = baseSystemPath
            self.dmgHelper.attach_selector_(baseSystemPath, self.handleSourceMountResult_)
        else:
            self.sourceFailed_text_(u"Invalid installer",
                                    u"Couldn't find system version in InstallESD.")
    
    def checkVersion_(self, mountPoint):
        LogDebug(u"checkVersion:%@", mountPoint)
        
        # InstallESD.dmg for 10.7/10.8, BaseSystem.dmg for 10.9.
        plist = NSDictionary.dictionaryWithContentsOfFile_(os.path.join(mountPoint, VERSIONPLIST_PATH))
        if self.baseSystemMountedFromPath:
            self.dmgHelper.detach_selector_(self.baseSystemMountedFromPath, self.handleDetachResult_)
        name = plist[u"ProductName"]
        version = plist[u"ProductUserVisibleVersion"]
        build = plist[u"ProductBuildVersion"]
        installerVersion = tuple(int(x) for x in version.split(u"."))
        runningVersion = tuple(int(x) for x in platform.mac_ver()[0].split(u"."))
        if installerVersion[:2] == runningVersion[:2]:
            LogNotice(u"Accepted source %@: %@ %@ %@", self.newSourcePath, name, version, build)
            self.installerName = name
            self.installerVersion = version
            self.installerBuild = build
            info = {
                u"name": name,
                u"version": version,
                u"build": build,
            }
            self.delegate.sourceSucceeded_(info)
        else:
            self.delegate.ejectingSource()
            self.dmgHelper.detachAll_(self.rejectSource_)
    
    def rejectSource_(self, failedUnmounts):
        self.delegate.sourceFailed_text_(u"Version mismatch",
                                         u"The major version of the installer and the current OS must match.")
        if failedUnmounts:
            text = u"\n".join(u"%s: %s" % (dmg, error) for dmg, error in failedUnmounts.iteritems())
            self.delegate.displayAlert_text_(u"Failed to eject dmgs", text)
    
    
    
    # Set a list of packages to install after the OS.
    
    def setPackagesToInstall_(self, packages):
        self.additionalPackages = packages
    
    # Path to generated disk image.
    
    def outputPath(self):
        return self._outputPath
    def setOutputPath_(self, path):
        self._outputPath = path
    
    
    
    # Start the workflow.
    #
    # Delegate methods:
    #
    #     - (void)buildStartingWithOutput:(NSString *)outputPath
    #     - (void)buildSetTotalWeight:(double)totalWeight
    #     - (void)buildSetPhase:(NSString *)phase
    #     - (void)buildSetProgress:(double)progress
    #     - (void)buildSetProgressMessage:(NSString *)message
    #     - (void)buildSucceeded
    #     - (void)buildFailed:(NSString *)message details:(NSString *)details
    #     - (void)buildStopped
    
    def start(self):
        LogNotice(u"Starting build")
        LogNotice(u"Using installer: %@ %@ %@", self.installerName, self.installerVersion, self.installerBuild)
        LogNotice(u"Using output path: %@", self.outputPath())
        self.delegate.buildStartingWithOutput_(self.outputPath())
        
        # The workflow is split into tasks, and each task has one or more
        # phases. Each phase of the installation is given a weight for the
        # progress bar, calculated from the size of the installer package.
        # Phases that don't install packages get an estimated weight.
        
        self.tasks = list()
        
        # Prepare for install.
        self.tasks.append({
            u"method": self.taskPrepare,
            u"phases": [
                {u"title": u"Preparing", u"weight": 1 * 1024 * 1024},
            ],
        })
        
        # Perform installation.
        installerPhases = [
            {u"title": u"Starting install", u"weight": 1 * 1024 * 1024},
            {u"title": u"Creating disk image", u"weight": 100 * 1024 * 1024},
            {u"title": u"Installing OS", u"weight": 4 * 1024 * 1024 * 1024},
        ]
        for package in self.additionalPackages:
            installerPhases.append({
                u"title": u"Installing %s" % package.name(),
                # Add 100 MB to the weight to account for overhead.
                u"weight": package.size() + 100 * 1024 * 1024,
            })
        installerPhases.extend([
            # hdiutil convert.
            {u"title": u"Finalizing disk image", u"weight": 500 * 1024 * 1024},
        ])
        self.tasks.append({
            u"method": self.taskInstall,
            u"phases": installerPhases,
        })
        
        # Finalize image.
        self.tasks.append({
            u"method": self.taskFinalize,
            u"phases": [
                {u"title": u"Finalizing disk image", u"weight": 100 * 1024 * 1024},
            ],
        })
        
        # Calculate total weight of all phases.
        self.totalWeight = 0
        for task in self.tasks:
            LogInfo(u"Task %@ with %d phases:", task[u"method"], len(task[u"phases"]))
            for phase in task[u"phases"]:
                LogInfo(u"    Phase '%@' with weight %.1f", phase[u"title"], phase[u"weight"] / 1048576.0)
                self.totalWeight += phase[u"weight"]
        self.delegate.buildSetTotalWeight_(self.totalWeight)
        
        # Start the first task.
        self.progress = 0
        self.currentTask = None
        self.currentPhase = None
        self.nextTask()
    
    
    
    # Task and phase logic.
    
    def nextTask(self):
        LogDebug(u"nextTask")
        
        if self.currentTask:
            if self.currentTask[u"phases"]:
                details = NSString.stringWithFormat_(u"Phases remaining: %@", self.currentTask[u"phases"])
                self.fail_details_(u"Task finished prematurely", details)
                return
        if self.tasks:
            self.currentTask = self.tasks.pop(0)
            LogNotice(u"Starting task with %d phases", len(self.currentTask[u"phases"]))
            self.nextPhase()
            self.currentTask[u"method"]()
        else:
            LogNotice(u"Build finished successfully, image saved to %@", self.outputPath())
            self.delegate.buildSucceeded()
            self.stop()
    
    def nextPhase(self):
        LogDebug(u"nextPhase")
        
        if self.currentPhase:
            self.progress += self.currentPhase[u"weight"]
        try:
            self.currentPhase = self.currentTask[u"phases"].pop(0)
        except IndexError:
            self.fail_details_(u"No phase left in task", traceback.format_stack())
            return
        LogNotice(u"Starting phase: %@", self.currentPhase[u"title"])
        self.delegate.buildSetPhase_(self.currentPhase[u"title"])
        self.delegate.buildSetProgress_(self.progress)
    
    def fail_details_(self, message, text):
        LogError(u"Workflow failed: %@ (%@)", message, text)
        self.delegate.buildFailed_details_(message, text)
        self.stop()
    
    # Stop is called at the end of a workflow, regardless of if it succeeded
    # or failed.
    def stop(self):
        LogDebug(u"Workflow stopping")
        self.detachInstallerDMGs()
        self.delegate.buildStopped()
    
    
    
    # Task: Prepare.
    #
    #    1. Go through the list of packages to install and if they're
    #       contained in disk images, mount them.
    #    2. Generate a list of paths to the packages for the install task.
    
    def taskPrepare(self):
        LogDebug(u"taskPrepare")
        
        # Attach any disk images containing update packages.
        self.attachedPackageDMGs = dict()
        self.numberOfDMGsToAttach = 0
        for package in self.additionalPackages:
            if package.path().endswith(u".dmg"):
                self.numberOfDMGsToAttach += 1
                LogInfo(u"Attaching %@", package.path())
                self.dmgHelper.attach_selector_(package.path(), self.attachPackageDMG_)
        if self.numberOfDMGsToAttach == 0:
            self.continuePrepare()
    
    # This will be called once for each disk image.
    def attachPackageDMG_(self, result):
        LogDebug(u"attachPackageDMG:%@", result)
        
        if result[u"success"] == False:
            self.fail_details_(u"Failed to attach %s" % result[u"dmg-path"],
                               result[u"error-message"])
            return
        # Save result in a dictionary of dmg paths and their mount points.
        self.attachedPackageDMGs[result[u"dmg-path"]] = result[u"mount-point"]
        # If this was the last image we were waiting for, continue preparing
        # for install.
        if len(self.attachedPackageDMGs) == self.numberOfDMGsToAttach:
            self.continuePrepare()
    
    def continuePrepare(self):
        LogDebug(u"continuePrepare")
        
        # Generate a list of packages to install, starting with the OS.
        self.packagesToInstall = [
            os.path.join(self.installerMountPoint, u"Packages/OSInstall.mpkg"),
        ]
        for package in self.additionalPackages:
            if package.path().endswith(u".dmg"):
                mountPoint = self.attachedPackageDMGs[package.path()]
                packagePaths = glob.glob(os.path.join(mountPoint, "*.mpkg"))
                packagePaths += glob.glob(os.path.join(mountPoint, "*.pkg"))
                if len(packagePaths) == 0:
                    self.fail_details_(u"No installer found",
                                       u"No package found in %s" % package.name())
                    return
                elif len(packagePaths) > 1:
                    LogWarning(u"Multiple packages found in disk image of %s, using %s" % (update[u"name"], packagePaths[0]))
                self.packagesToInstall.append(packagePaths[0])
            else:
                self.packagesToInstall.append(package.path())
        
        LogInfo(u"%d packages to install:", len(self.packagesToInstall))
        for path in self.packagesToInstall:
            LogInfo(u"    %@", path)
        
        # Task done.
        self.nextTask()
    
    
    
    # Task: Install.
    #
    #    1. Run the installesdtodmg.sh script with administrator privileges.
    #       Progress is sent back via notifications to the socket, which keeps
    #       the phases in sync with the script.
    
    def taskInstall(self):
        LogNotice(u"Install task running")
        
        # The script is wrapped with progresswatcher.py which parses script
        # output and sends it back as notifications to IEDSocketListener.
        args = [
            NSBundle.mainBundle().pathForResource_ofType_(u"progresswatcher", u"py"),
            u"--cd", NSBundle.mainBundle().resourcePath(),
            u"--socket", self.listenerPath,
            u"installesdtodmg",
            u"--user", NSUserName(),
            u"--group", grp.getgrgid(os.getgid()).gr_name,
            u"--output", self.outputPath(),
        ] + self.packagesToInstall
        LogInfo(u"Launching install with arguments:")
        for arg in args:
            LogInfo(u"    '%@'", arg)
        self.performSelectorInBackground_withObject_(self.launchScript_, args)
    
    def launchScript_(self, args):
        LogDebug(u"launchScript:")
        
        # Generate an AppleScript snippet to launch a shell command with
        # administrator privileges.
        shellscript = u' & " " & '.join(u"quoted form of arg%d" % i for i in range(len(args)))
        def escape(s):
            return s.replace(u"\\", u"\\\\").replace(u'"', u'\\"')
        applescript = u"\n".join([u'set arg%d to "%s"' % (i, escape(arg)) for i, arg in enumerate(args)] + \
                                 [u'do shell script %s with administrator privileges' % shellscript])
        trampoline = NSAppleScript.alloc().initWithSource_(applescript)
        evt, error = trampoline.executeAndReturnError_(None)
        if evt is None:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(self.handleLaunchScriptError_, error, False)
    
    def handleLaunchScriptError_(self, error):
        if error[NSAppleScriptErrorNumber] == -128:
            self.stop()
        else:
            self.fail_details_(u"Build failed", error[NSAppleScriptErrorMessage])
    
    
    
    # Task: Finalize.
    #
    #    1. Scan the image for restore.
    
    def taskFinalize(self):
        LogNotice(u"Finalize task running")
        
        self.delegate.buildSetProgressMessage_(u"Scanning disk image for restore")
        # The script is wrapped with progresswatcher.py which parses script
        # output and sends it back as notifications to IEDSocketListener.
        args = [
            NSBundle.mainBundle().pathForResource_ofType_(u"progresswatcher", u"py"),
            u"--socket", self.listenerPath,
            u"imagescan",
            self.outputPath(),
        ]
        LogInfo(u"Launching finalize with arguments:")
        for arg in args:
            LogInfo(u"    '%@'", arg)
        subprocess.Popen(args)
    
    
    
    # SocketListener delegate methods.
    
    def socketReceivedMessage_(self, msg):
        # The message is a dictionary with "action" as the only required key.
        action = msg[u"action"]
        
        if action == u"update_progress":
            percent = msg[u"percent"]
            currentProgress = self.progress + self.currentPhase[u"weight"] * percent / 100.0
            self.delegate.buildSetProgress_(currentProgress)
        
        elif action == u"update_message":
            LogMessage(IEDLogLevelInfo, msg[u"message"])
            self.delegate.buildSetProgressMessage_(msg[u"message"])
        
        elif action == u"select_phase":
            LogNotice(u"Script phase: %@", msg[u"phase"])
            self.nextPhase()
        
        elif action == u"log_message":
            LogMessage(msg[u"log_level"], msg[u"message"])
        
        elif action == u"notify_failure":
            self.fail_details_(u"Build failed", msg[u"message"])
        
        elif action == u"task_done":
            status = msg[u"termination_status"]
            if status == 0:
                self.nextTask()
            else:
                details = NSString.stringWithFormat_(u"Task exited with status %@", msg[u"termination_status"])
                LogError(u"%@", details)
                # Status codes 100-199 are from installesdtodmg.sh, and have
                # been preceeded by a "notify_failure" message.
                if (status < 100) or (status > 199):
                    self.fail_details_(u"Build failed", details)
        
        else:
            self.fail_details_(u"Unknown progress notification", u"Message: %@", msg)


