#!/usr/bin/python3

import os
import codecs
import sys
import gi
import tempfile
import threading
import time
import gettext
import fnmatch
import urllib.request
import re
import proxygsettings
import subprocess
import lsb_release
import pycurl
import datetime
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0') # Needed to get xid
from gi.repository import Gtk, Gdk, GdkPixbuf, GdkX11, Gio, Pango

try:
    numMintUpdate = subprocess.check_output("ps -A | grep mintUpdate | wc -l", shell = True)
    if (numMintUpdate != "0"):
        os.system("killall mintUpdate")
except Exception as e:
    print (e)
    print(sys.exc_info()[0])

newname = b"mintUpdate"
from ctypes import cdll, byref, create_string_buffer
libc = cdll.LoadLibrary('libc.so.6')
buff = create_string_buffer(len(newname)+1)
buff.value = newname
libc.prctl(15, byref(buff), 0, 0, 0)

# i18n
gettext.install("mintupdate", "/usr/share/linuxmint/locale")

KERNEL_INFO_DIR = "/usr/share/mint-kernel-info"

(TAB_UPDATES, TAB_UPTODATE, TAB_ERROR) = range(3)

package_short_descriptions = {}
package_descriptions = {}

(UPDATE_CHECKED, UPDATE_ALIAS, UPDATE_LEVEL_PIX, UPDATE_OLD_VERSION, UPDATE_NEW_VERSION, UPDATE_LEVEL_STR, UPDATE_SIZE, UPDATE_SIZE_STR, UPDATE_TYPE_PIX, UPDATE_TYPE, UPDATE_TOOLTIP, UPDATE_SORT_STR, UPDATE_OBJ) = range(13)

def size_to_string(size):
    strSize = str(size) + _("B")
    if (size >= 1024):
        strSize = str(size // 1024) + _("KB")
    if (size >= (1024 * 1024)):
        strSize = str(size // (1024 * 1024)) + _("MB")
    if (size >= (1024 * 1024 * 1024)):
        strSize = str(size // (1024 * 1024 * 1024)) + _("GB")
    return strSize

class Alias():
    def __init__(self, name, short_description, description):

        name = name.strip()
        short_description = short_description.strip()
        description = description.strip()

        if (name.startswith('_("') and name.endswith('")')):
            name = _(name[3:-2])
        if (short_description.startswith('_("') and short_description.endswith('")')):
            short_description = _(short_description[3:-2])
        if (description.startswith('_("') and description.endswith('")')):
            description = _(description[3:-2])

        self.name = name
        self.short_description = short_description
        self.description = description

class PackageUpdate():
    def __init__(self, source_package_name, level, oldVersion, newVersion, extraInfo, warning, update_type, origin, tooltip):
        self.name = source_package_name
        self.description = ""
        self.short_description = ""
        self.main_package = None # This is the package within the update which is used for the descriptions
        self.level = level
        self.oldVersion = oldVersion
        self.newVersion = newVersion
        self.size = 0
        self.extraInfo = extraInfo
        self.warning = warning
        self.type = update_type
        self.origin = origin
        self.tooltip = tooltip
        self.packages = []
        self.alias = source_package_name

    def add_package(self, package, size, short_description, description):
        self.packages.append(package)
        self.size += size
        overwrite_main_package = False
        if self.main_package is None or package == self.name:
            overwrite_main_package = True
        else:
            if self.main_package == self.name:
                overwrite_main_package = False
            else:
                # Overwrite dev, dbg, common, arch packages
                for suffix in ["-dev", "-dbg", "-common", "-core", "-data", "-doc", ":i386", ":amd64"]:
                    if (self.main_package.endswith(suffix) and not package.endswith(suffix)):
                        overwrite_main_package = True
                        break
                # Overwrite lib packages
                for prefix in ["lib", "gir1.2"]:
                    if (self.main_package.startswith(suffix) and not package.startswith(suffix)):
                        overwrite_main_package = True
                        break
                for keyword in ["-locale-", "-l10n-", "-help-"]:
                    if (self.main_package.startswith(suffix) and not package.startswith(suffix)):
                        overwrite_main_package = True
                        break
        if overwrite_main_package:
            self.description = description
            self.short_description = short_description
            self.main_package  = package

class ChangelogRetriever(threading.Thread):
    def __init__(self, package_update, application):
        threading.Thread.__init__(self)
        self.source_package = package_update.name
        self.level = package_update.level
        self.version = package_update.newVersion
        self.origin = package_update.origin
        self.application = application
        # get the proxy settings from gsettings
        self.ps = proxygsettings.get_proxy_settings()


        # Remove the epoch if present in the version
        if ":" in self.version:
            self.version = self.version.split(":")[-1]

    def run(self):
        Gdk.threads_enter()
        self.application.builder.get_object("textview_changes").get_buffer().set_text(_("Downloading changelog..."))
        Gdk.threads_leave()

        changelog_sources = []
        if self.origin == "linuxmint":
            changelog_sources.append("http://packages.linuxmint.com/dev/" + self.source_package + "_" + self.version + "_amd64.changes")
            changelog_sources.append("http://packages.linuxmint.com/dev/" + self.source_package + "_" + self.version + "_i386.changes")
        elif self.origin == "ubuntu":
            if (self.source_package.startswith("lib")):
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/main/%s/%s/%s_%s/changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/multiverse/%s/%s/%s_%s/changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/universe/%s/%s/%s_%s/changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/restricted/%s/%s/%s_%s/changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
            else:
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/main/%s/%s/%s_%s/changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/multiverse/%s/%s/%s_%s/changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/universe/%s/%s/%s_%s/changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://changelogs.ubuntu.com/changelogs/pool/restricted/%s/%s/%s_%s/changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
        elif self.origin == "debian":
            if (self.source_package.startswith("lib")):
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/main/%s/%s/%s_%s_changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/contrib/%s/%s/%s_%s_changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/non-free/%s/%s/%s_%s_changelog" % (self.source_package[0:4], self.source_package, self.source_package, self.version))
            else:
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/main/%s/%s/%s_%s_changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/contrib/%s/%s/%s_%s_changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))
                changelog_sources.append("http://metadata.ftp-master.debian.org/changelogs/non-free/%s/%s/%s_%s_changelog" % (self.source_package[0], self.source_package, self.source_package, self.version))

        changelog = [_("No changelog available")]

        if self.ps == {}:
            # use default urllib.request proxy mechanisms (possibly *_proxy environment vars)
            proxy = urllib.request.ProxyHandler()
        else:
            # use proxy settings retrieved from gsettings
            proxy = urllib.request.ProxyHandler(self.ps)

        opener = urllib.request.build_opener(proxy)
        urllib.request.install_opener(opener)

        for changelog_source in changelog_sources:
            try:
                print("Trying to fetch the changelog from: %s" % changelog_source)
                url = urllib.request.urlopen(changelog_source, None, 10)
                source = url.read().decode("utf-8")
                url.close()

                changelog = ""
                if "linuxmint.com" in changelog_source:
                    changes = source.split("\n")
                    for change in changes:
                        stripped_change = change.strip()
                        if stripped_change == ".":
                            change = ""
                        if change == "" or stripped_change.startswith("*") or stripped_change.startswith("["):
                            changelog = changelog + change + "\n"
                else:
                    changelog = source
                changelog = changelog.split("\n")
                break
            except:
                pass

        Gdk.threads_enter()
        self.application.builder.get_object("textview_changes").get_buffer().set_text("")
        for change in changelog:
            self.application.builder.get_object("textview_changes").get_buffer().insert(self.application.builder.get_object("textview_changes").get_buffer().get_end_iter(), change)
            self.application.builder.get_object("textview_changes").get_buffer().insert(self.application.builder.get_object("textview_changes").get_buffer().get_end_iter(), "\n")
        Gdk.threads_leave()

class AutomaticRefreshThread(threading.Thread):
    def __init__(self, application):
        threading.Thread.__init__(self)
        self.application = application

    def run(self):
        # Initial refresh (with APT cache refresh)
        try:
            timer = (self.application.settings.get_int("refresh-minutes") * 60) + (self.application.settings.get_int("refresh-hours") * 60 * 60) + (self.application.settings.get_int("refresh-days") * 24 * 60 * 60)
            self.application.logger.write("Initial refresh will happen in " + str(self.application.settings.get_int("refresh-minutes")) + " minutes, " + str(self.application.settings.get_int("refresh-hours")) + " hours and " + str(self.application.settings.get_int("refresh-days")) + " days")
            timetosleep = int(timer)
            if (timetosleep == 0):
                time.sleep(60) # sleep 1 minute, don't mind the config we don't want an infinite loop to go nuts :)
            else:
                time.sleep(timetosleep)
                if (self.application.app_hidden == True):
                    self.application.logger.write("MintUpdate is in tray mode, performing initial refresh")
                    refresh = RefreshThread(self.application, root_mode=True)
                    refresh.start()
                else:
                    self.application.logger.write("The mintUpdate window is open, skipping initial refresh")
        except Exception as e:
            print (e)
            self.application.logger.write_error("Exception occured during the initial refresh: " + str(sys.exc_info()[0]))

        # Autorefresh (also with APT cache refresh)
        try:
            while(True):
                timer = (self.application.settings.get_int("autorefresh-minutes") * 60) + (self.application.settings.get_int("autorefresh-hours") * 60 * 60) + (self.application.settings.get_int("autorefresh-days") * 24 * 60 * 60)
                self.application.logger.write("Auto-refresh will happen in " + str(self.application.settings.get_int("autorefresh-minutes")) + " minutes, " + str(self.application.settings.get_int("autorefresh-hours")) + " hours and " + str(self.application.settings.get_int("autorefresh-days")) + " days")
                timetosleep = int(timer)
                if (timetosleep == 0):
                    time.sleep(60) # sleep 1 minute, don't mind the config we don't want an infinite loop to go nuts :)
                else:
                    time.sleep(timetosleep)
                    if (self.application.app_hidden == True):
                        self.application.logger.write("MintUpdate is in tray mode, performing auto-refresh")
                        refresh = RefreshThread(self.application, root_mode=True)
                        refresh.start()
                    else:
                        self.application.logger.write("The mintUpdate window is open, skipping auto-refresh")
        except Exception as e:
            print (e)
            self.application.logger.write_error("Exception occured in the auto-refresh thread.. so it's probably dead now: " + str(sys.exc_info()[0]))

class InstallKernelThread(threading.Thread):

    def __init__(self, version, application, builder, remove=False):
        threading.Thread.__init__(self)
        self.version = version
        self.builder = builder
        self.remove = remove
        self.application = application

    def run(self):
        cmd = ["pkexec", "/usr/sbin/synaptic", "--hide-main-window",  \
                "--non-interactive", "--parent-window-id", "%s" % self.builder.get_object("window5").get_window().get_xid()]
        cmd.append("-o")
        cmd.append("Synaptic::closeZvt=true")
        cmd.append("--progress-str")
        cmd.append("\"" + _("Please wait, this can take some time") + "\"")
        cmd.append("--finish-str")
        if self.remove:
            cmd.append("\"" + _("The %s kernel was removed") % self.version + "\"")
        else:
            cmd.append("\"" + _("The %s kernel was installed") % self.version + "\"")
        f = tempfile.NamedTemporaryFile()

        for pkg in ['linux-headers-%s' % self.version, 'linux-headers-%s-generic' % self.version, 'linux-image-%s-generic' % self.version, 'linux-image-extra-%s-generic' % self.version]:
            if self.remove:
                pkg_line = "%s\tdeinstall\n" % pkg
            else:
                pkg_line = "%s\tinstall\n" % pkg
            f.write(pkg_line.encode("utf-8"))
        cmd.append("--set-selections-file")
        cmd.append("%s" % f.name)
        f.flush()
        comnd = subprocess.Popen(' '.join(cmd), stdout=self.application.logger.log, stderr=self.application.logger.log, shell=True)
        returnCode = comnd.wait()
        f.close()

class InstallThread(threading.Thread):

    def __init__(self, application):
        threading.Thread.__init__(self)
        self.application = application
        self.application.window.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))
        self.application.window.set_sensitive(False)

    def run(self):
        try:
            self.application.logger.write("Install requested by user")
            Gdk.threads_enter()
            installNeeded = False
            packages = []
            model = self.application.treeview.get_model()
            Gdk.threads_leave()

            iter = model.get_iter_first()
            while (iter != None):
                checked = model.get_value(iter, UPDATE_CHECKED)
                if (checked == "true"):
                    installNeeded = True
                    package_update = model.get_value(iter, UPDATE_OBJ)
                    for package in package_update.packages:
                        packages.append(package)
                        self.application.logger.write("Will install " + str(package))
                iter = model.iter_next(iter)

            if (installNeeded == True):

                proceed = True
                try:
                    pkgs = ' '.join(str(pkg) for pkg in packages)
                    warnings = subprocess.check_output("/usr/lib/linuxmint/mintUpdate/checkWarnings.py %s" % pkgs, shell = True).decode("utf-8")
                    #print ("/usr/lib/linuxmint/mintUpdate/checkWarnings.py %s" % pkgs)
                    warnings = warnings.split("###")
                    if len(warnings) == 2:
                        installations = warnings[0].split()
                        removals = warnings[1].split()
                        if len(installations) > 0 or len(removals) > 0:
                            Gdk.threads_enter()
                            try:
                                dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL, None)
                                dialog.set_title("")
                                dialog.set_markup("<b>" + _("This upgrade will trigger additional changes") + "</b>")
                                #dialog.format_secondary_markup("<i>" + _("All available upgrades for this package will be ignored.") + "</i>")
                                dialog.set_icon_name("mintupdate")
                                dialog.set_default_size(320, 400)
                                dialog.set_resizable(True)

                                if len(removals) > 0:
                                    # Removals
                                    label = Gtk.Label()
                                    if len(removals) == 1:
                                        label.set_text(_("The following package will be removed:"))
                                    else:
                                        label.set_text(_("The following %d packages will be removed:") % len(removals))
                                    label.set_alignment(0, 0.5)
                                    scrolledWindow = Gtk.ScrolledWindow()
                                    scrolledWindow.set_shadow_type(Gtk.ShadowType.IN)
                                    scrolledWindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
                                    treeview = Gtk.TreeView()
                                    column1 = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
                                    column1.set_sort_column_id(0)
                                    column1.set_resizable(True)
                                    treeview.append_column(column1)
                                    treeview.set_headers_clickable(False)
                                    treeview.set_reorderable(False)
                                    treeview.set_headers_visible(False)
                                    model = Gtk.TreeStore(str)
                                    removals.sort()
                                    for pkg in removals:
                                        iter = model.insert_before(None, None)
                                        model.set_value(iter, 0, pkg)
                                    treeview.set_model(model)
                                    treeview.show()
                                    scrolledWindow.add(treeview)
                                    dialog.vbox.pack_start(label, False, False, 0)
                                    dialog.vbox.pack_start(scrolledWindow, True, True, 0)
                                    dialog.vbox.set_border_width(6)

                                if len(installations) > 0:
                                    # Installations
                                    label = Gtk.Label()
                                    if len(installations) == 1:
                                        label.set_text(_("The following package will be installed:"))
                                    else:
                                        label.set_text(_("The following %d packages will be installed:") % len(installations))
                                    label.set_alignment(0, 0.5)
                                    scrolledWindow = Gtk.ScrolledWindow()
                                    scrolledWindow.set_shadow_type(Gtk.ShadowType.IN)
                                    scrolledWindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
                                    treeview = Gtk.TreeView()
                                    column1 = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
                                    column1.set_sort_column_id(0)
                                    column1.set_resizable(True)
                                    treeview.append_column(column1)
                                    treeview.set_headers_clickable(False)
                                    treeview.set_reorderable(False)
                                    treeview.set_headers_visible(False)
                                    model = Gtk.TreeStore(str)
                                    installations.sort()
                                    for pkg in installations:
                                        iter = model.insert_before(None, None)
                                        model.set_value(iter, 0, pkg)
                                    treeview.set_model(model)
                                    treeview.show()
                                    scrolledWindow.add(treeview)
                                    dialog.vbox.pack_start(label, False, False, 0)
                                    dialog.vbox.pack_start(scrolledWindow, True, True, 0)

                                dialog.show_all()
                                if dialog.run() == Gtk.ResponseType.OK:
                                    proceed = True
                                else:
                                    proceed = False
                                dialog.destroy()
                            except Exception as e:
                                print (e)
                                print(sys.exc_info()[0])
                            Gdk.threads_leave()
                        else:
                            proceed = True
                except Exception as e:
                    print (e)
                    print(sys.exc_info()[0])

                if proceed:
                    Gdk.threads_enter()
                    self.application.set_status(_("Installing updates"), _("Installing updates"), "mintupdate-installing", True)
                    Gdk.threads_leave()
                    self.application.logger.write("Ready to launch synaptic")
                    cmd = ["pkexec", "/usr/sbin/synaptic", "--hide-main-window",  \
                            "--non-interactive", "--parent-window-id", "%s" % self.application.window.get_window().get_xid()]
                    cmd.append("-o")
                    cmd.append("Synaptic::closeZvt=true")
                    cmd.append("--progress-str")
                    cmd.append("\"" + _("Please wait, this can take some time") + "\"")
                    cmd.append("--finish-str")
                    cmd.append("\"" + _("Update is complete") + "\"")
                    f = tempfile.NamedTemporaryFile()

                    for pkg in packages:
                        pkg_line = "%s\tinstall\n" % pkg
                        f.write(pkg_line.encode("utf-8"))

                    cmd.append("--set-selections-file")
                    cmd.append("%s" % f.name)
                    f.flush()
                    comnd = subprocess.Popen(' '.join(cmd), stdout=self.application.logger.log, stderr=self.application.logger.log, shell=True)
                    returnCode = comnd.wait()
                    self.application.logger.write("Return code:" + str(returnCode))
                    f.close()
                    self.application.logger.write("Install finished")

                    if self.application.settings.get_boolean("hide-window-after-update"):
                        Gdk.threads_enter()
                        self.application.app_hidden = True
                        self.application.window.hide()
                        Gdk.threads_leave()

                    if "mintupdate" in packages or "mint-upgrade-info" in packages:
                        # Restart
                        try:
                            self.application.logger.write("Mintupdate was updated, restarting it...")
                            self.application.logger.close()
                        except:
                            pass #cause we might have closed it already

                        command = "/usr/lib/linuxmint/mintUpdate/mintUpdate.py show &"
                        os.system(command)

                    else:
                        # Refresh
                        Gdk.threads_enter()
                        self.application.set_status(_("Checking for updates"), _("Checking for updates"), "mintupdate-checking", not self.application.settings.get_boolean("hide-systray"))
                        self.application.window.get_window().set_cursor(None)
                        self.application.window.set_sensitive(True)
                        Gdk.threads_leave()
                        refresh = RefreshThread(self.application)
                        refresh.start()
                else:
                    # Stop the blinking but don't refresh
                    Gdk.threads_enter()
                    self.application.window.get_window().set_cursor(None)
                    self.application.window.set_sensitive(True)
                    Gdk.threads_leave()
            else:
                # Stop the blinking but don't refresh
                Gdk.threads_enter()
                self.application.window.get_window().set_cursor(None)
                self.application.window.set_sensitive(True)
                Gdk.threads_leave()

        except Exception as e:
            print (e)
            self.application.logger.write_error("Exception occured in the install thread: " + str(sys.exc_info()[0]))
            Gdk.threads_enter()
            self.application.set_status(_("Could not install the security updates"), _("Could not install the security updates"), "mintupdate-error", True)
            self.application.logger.write_error("Could not install security updates")
            self.application.window.get_window().set_cursor(None)
            self.application.window.set_sensitive(True)
            Gdk.threads_leave()

class RefreshThread(threading.Thread):

    def __init__(self, application, root_mode=False):
        threading.Thread.__init__(self)
        self.root_mode = root_mode
        self.application = application

    def clean_l10n_short_description(self, description):
        try:
            # Remove "Description-xx: " prefix
            value = re.sub(r'Description-(\S+): ', r'', description)
            # Only take the first line and trim it
            value = value.split("\n")[0].strip()
            # Capitalize the first letter
            value = value[:1].upper() + value[1:]
            # Add missing punctuation
            if len(value) > 0 and value[-1] not in [".", "!", "?"]:
                value = "%s." % value
            # Replace & signs with &amp; (because we pango it)
            value = value.replace('&', '&amp;')

            return value
        except Exception as e:
            print(e)
            print(sys.exc_info()[0])
            return description

    def clean_l10n_description(self, description):
            try:
                lines = description.split("\n")
                value = ""
                num = 0
                newline = False
                for line in lines:
                    line = line.strip()
                    if len(line) > 0:
                        if line == ".":
                            value = "%s\n" % (value)
                            newline = True
                        else:
                            if (newline):
                                value = "%s%s" % (value, line.capitalize())
                            else:
                                value = "%s %s" % (value, line)
                            newline = False
                        num += 1
                value = value.replace("  ", " ").strip()
                # Capitalize the first letter
                value = value[:1].upper() + value[1:]
                # Add missing punctuation
                if len(value) > 0 and value[-1] not in [".", "!", "?"]:
                    value = "%s." % value
                return value
            except Exception as e:
                print (e)
                print(sys.exc_info()[0])
                return description

    def l10n_descriptions(self, package_update):
        package_name = package_update.name.replace(":i386", "").replace(":amd64", "")
        if package_name in package_descriptions:
            package_update.short_description = package_short_descriptions[package_name]
            package_update.description = package_descriptions[package_name]

    def fetch_l10n_descriptions(self, package_names):
        if os.path.exists("/var/lib/apt/lists"):
            try:
                super_buffer = []
                for file in os.listdir("/var/lib/apt/lists"):
                    if ("i18n_Translation") in file and not file.endswith("Translation-en"):
                        fd = codecs.open(os.path.join("/var/lib/apt/lists", file), "r", "utf-8")
                        super_buffer += fd.readlines()

                i = 0
                while i < len(super_buffer):
                    line = super_buffer[i].strip()
                    if line.startswith("Package: "):
                        try:
                            pkgname = line.replace("Package: ", "")
                            short_description = ""
                            description = ""
                            j = 2 # skip md5 line after package name line
                            while True:
                                if (i+j >= len(super_buffer)):
                                    break
                                line = super_buffer[i+j].strip()
                                if line.startswith("Package: "):
                                    break
                                if j==2:
                                    short_description = line
                                else:
                                    description += "\n" + line
                                j += 1
                            if pkgname in package_names:
                                if not pkgname in package_descriptions:
                                    package_short_descriptions[pkgname] = short_description
                                    package_descriptions[pkgname] = description
                        except Exception as e:
                            print (e)
                            print("a %s" % sys.exc_info()[0])
                    i += 1
                del super_buffer
            except Exception as e:
                print (e)
                print("Could not fetch l10n descriptions..")
                print(sys.exc_info()[0])

    def check_policy(self):
        # Check the presence of the Mint layer
        p1 = subprocess.Popen(['apt-cache', 'policy'], stdout=subprocess.PIPE)
        p = p1.communicate()[0]
        mint_layer_found = False
        output = p.decode("utf-8").split('\n')
        for line in output:
            line = line.strip()
            if line.startswith("700") and line.endswith("Packages") and "/upstream" in line:
                mint_layer_found = True
                break
        return mint_layer_found

    def run(self):
        Gdk.threads_enter()
        vpaned_position = self.application.builder.get_object("vpaned1").get_position()
        for child in self.application.builder.get_object("hbox_infobar").get_children():
            child.destroy()
        Gdk.threads_leave()
        try:
            if (self.root_mode):
                self.application.logger.write("Starting refresh (including refreshing the APT cache)")
            else:
                self.application.logger.write("Starting refresh")
            Gdk.threads_enter()
            self.application.set_status_message(_("Starting refresh..."))
            self.application.builder.get_object("notebook_status").set_current_page(TAB_UPDATES)
            if (not self.application.app_hidden):
                self.application.window.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))
            self.application.window.set_sensitive(False)

            # Starts the blinking
            self.application.statusIcon.set_from_icon_name("mintupdate-checking")
            self.application.statusIcon.set_tooltip_text(_("Checking for updates"))
            self.application.statusIcon.set_visible(not self.application.settings.get_boolean("hide-systray"))
            self.application.builder.get_object("vpaned1").set_position(vpaned_position)
            Gdk.threads_leave()

            model = Gtk.TreeStore(str, str, GdkPixbuf.Pixbuf, str, str, str, int, str, GdkPixbuf.Pixbuf, str, str, str, object)
            # UPDATE_CHECKED, UPDATE_ALIAS, UPDATE_LEVEL_PIX, UPDATE_OLD_VERSION, UPDATE_NEW_VERSION, UPDATE_LEVEL_STR,
            # UPDATE_SIZE, UPDATE_SIZE_STR, UPDATE_TYPE_PIX, UPDATE_TYPE, UPDATE_TOOLTIP, UPDATE_SORT_STR, UPDATE_OBJ

            model.set_sort_column_id( UPDATE_SORT_STR, Gtk.SortType.ASCENDING )

            aliases = {}
            with open("/usr/lib/linuxmint/mintUpdate/aliases") as alias_file:
                for line in alias_file:
                    if not line.startswith('#'):
                        splitted = line.split("#####")
                        if len(splitted) == 4:
                            (alias_packages, alias_name, alias_short_description, alias_description) = splitted
                            alias_object = Alias(alias_name, alias_short_description, alias_description)
                            for alias_package in alias_packages.split(','):
                                alias_package = alias_package.strip()
                                aliases[alias_package] = alias_object

            # Check to see if no other APT process is running
            if self.root_mode:
                p1 = subprocess.Popen(['ps', '-U', 'root', '-o', 'comm'], stdout=subprocess.PIPE)
                p = p1.communicate()[0]
                running = False
                pslist = p.split(b'\n')
                for process in pslist:
                    if process.strip() in ["dpkg", "apt-get","synaptic","update-manager", "adept", "adept-notifier"]:
                        running = True
                        break
                if (running == True):
                    Gdk.threads_enter()
                    self.application.set_status(_("Another application is using APT"), _("Another application is using APT"), "mintupdate-checking", not self.application.settings.get_boolean("hide-systray"))
                    self.application.logger.write_error("Another application is using APT")
                    if (not self.application.app_hidden):
                        self.application.window.get_window().set_cursor(None)
                    self.application.window.set_sensitive(True)
                    Gdk.threads_leave()
                    return False

            Gdk.threads_enter()
            self.application.set_status_message(_("Finding the list of updates..."))
            self.application.builder.get_object("vpaned1").set_position(vpaned_position)
            Gdk.threads_leave()
            if self.application.app_hidden:
                refresh_command = "/usr/lib/linuxmint/mintUpdate/checkAPT.py 2>/dev/null"
            else:
                refresh_command = "/usr/lib/linuxmint/mintUpdate/checkAPT.py --use-synaptic %s 2>/dev/null" % self.application.window.get_window().get_xid()
            if self.root_mode:
                refresh_command = "sudo %s" % refresh_command
            updates =  subprocess.check_output(refresh_command, shell = True).decode("utf-8")

            if len(updates) > 0 and not "CHECK_APT_ERROR" in updates:
                if not self.check_policy():
                    Gdk.threads_enter()
                    label1 = _("Your APT cache is corrupted.")
                    label2 = _("Do not install or update anything, it could break your operating system!")
                    label3 = _("Switch to a different Linux Mint mirror to solve this situation.")
                    infobar = Gtk.InfoBar()
                    infobar.set_message_type(Gtk.MESSAGE_ERROR)
                    info_label = Gtk.Label()
                    infobar_message = "%s\n<small>%s</small>" % (_("Please switch to another Linux Mint mirror"), _("Your APT cache is corrupted."))
                    info_label.set_markup(infobar_message)
                    infobar.get_content_area().pack_start(info_label,False, False,0)
                    infobar.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
                    infobar.connect("response", self._on_infobar_response)
                    self.application.builder.get_object("hbox_infobar").pack_start(infobar, True, True,0)
                    infobar.show_all()
                    self.application.set_status(_("Could not refresh the list of updates"), "%s\n%s\n%s" % (label1, label2, label3), "mintupdate-error", True)
                    self.application.logger.write("Error: The APT policy is incorrect!")
                    self.application.builder.get_object("notebook_status").set_current_page(TAB_ERROR)
                    self.application.builder.get_object("label_error_details").set_markup("<b>%s\n%s\n%s</b>" % (label1, label2, label3))
                    self.application.builder.get_object("label_error_details").show()
                    if (not self.application.app_hidden):
                            self.application.window.get_window().set_cursor(None)
                    self.application.window.set_sensitive(True)
                    Gdk.threads_leave()
                    return False

            # Look for mintupdate
            if ("UPDATE###mintupdate###" in updates or "UPDATE###mint-upgrade-info###" in updates):
                new_mintupdate = True
            else:
                new_mintupdate = False

            updates = updates.split("---EOL---")

            # Look at the updates one by one
            package_updates = {}
            package_names = set()
            num_visible = 0
            num_safe = 0
            download_size = 0
            num_ignored = 0
            ignored_list = self.application.settings.get_strv("blacklisted-packages")

            if (len(updates) == None):
                Gdk.threads_enter()
                self.application.builder.get_object("notebook_status").set_current_page(TAB_UPTODATE)
                self.application.set_status(_("Your system is up to date"), _("Your system is up to date"), "mintupdate-up-to-date", not self.application.settings.get_boolean("hide-systray"))
                self.application.logger.write("System is up to date")
                Gdk.threads_leave()
            else:
                for pkg in updates:
                    if pkg.startswith("CHECK_APT_ERROR"):
                        try:
                            error_msg = updates[1].replace("E:", "\n")
                        except:
                            error_msg = ""
                        Gdk.threads_enter()
                        self.application.set_status(_("Could not refresh the list of updates"), "%s\n\n%s" % (_("Could not refresh the list of updates"), error_msg), "mintupdate-error", True)
                        self.application.logger.write("Error in checkAPT.py, could not refresh the list of updates")
                        self.application.builder.get_object("notebook_status").set_current_page(TAB_ERROR)
                        self.application.builder.get_object("label_error_details").set_markup("<b>%s</b>" % error_msg)
                        self.application.builder.get_object("label_error_details").show()
                        if (not self.application.app_hidden):
                            self.application.window.get_window().set_cursor(None)
                        self.application.window.set_sensitive(True)
                        Gdk.threads_leave()
                        return False

                    values = pkg.split("###")
                    if len(values) == 10:
                        status = values[0]
                        package = values[1]
                        newVersion = values[2]
                        oldVersion = values[3]
                        size = int(values[4])
                        source_package = values[5]
                        update_type = values[6]
                        origin = values[7]
                        short_description = values[8]
                        description = values[9]

                        package_names.add(package.replace(":i386", "").replace(":amd64", ""))

                        if not source_package in package_updates:
                            updateIsBlacklisted = False
                            for blacklist in ignored_list:
                                if fnmatch.fnmatch(source_package, blacklist):
                                    num_ignored = num_ignored + 1
                                    updateIsBlacklisted = True
                                    break

                            if updateIsBlacklisted:
                                continue

                            is_a_mint_package = False
                            if (update_type == "linuxmint"):
                                update_type = "package"
                                is_a_mint_package = True

                            security_update = (update_type == "security")

                            if update_type == "security":
                                tooltip = _("Security update")
                            elif update_type == "backport":
                                tooltip = _("Software backport. Be careful when upgrading. New versions of sofware can introduce regressions.")
                            elif update_type == "unstable":
                                tooltip = _("Unstable software. Only apply this update to help developers beta-test new software.")
                            else:
                                tooltip = _("Software update")

                            extraInfo = ""
                            warning = ""
                            if is_a_mint_package:
                                level = 1 # Level 1 by default
                            else:
                                level = 3 # Level 3 by default
                            rulesFile = open("/usr/lib/linuxmint/mintUpdate/rules","r")
                            rules = rulesFile.readlines()
                            goOn = True
                            foundPackageRule = False # whether we found a rule with the exact package name or not
                            for rule in rules:
                                if (goOn == True):
                                    rule_fields = rule.split("|")
                                    if (len(rule_fields) == 5):
                                        rule_package = rule_fields[0]
                                        rule_version = rule_fields[1]
                                        rule_level = rule_fields[2]
                                        rule_extraInfo = rule_fields[3]
                                        rule_warning = rule_fields[4]
                                        if (rule_package == source_package):
                                            foundPackageRule = True
                                            if (rule_version == newVersion):
                                                level = rule_level
                                                extraInfo = rule_extraInfo
                                                warning = rule_warning
                                                goOn = False # We found a rule with the exact package name and version, no need to look elsewhere
                                            else:
                                                if (rule_version == "*"):
                                                    level = rule_level
                                                    extraInfo = rule_extraInfo
                                                    warning = rule_warning
                                        else:
                                            if (rule_package.startswith("*")):
                                                keyword = rule_package.replace("*", "")
                                                index = source_package.find(keyword)
                                                if (index > -1 and foundPackageRule == False):
                                                    level = rule_level
                                                    extraInfo = rule_extraInfo
                                                    warning = rule_warning
                            rulesFile.close()
                            level = int(level)

                            # Create a new Update
                            update = PackageUpdate(source_package, level, oldVersion, newVersion, extraInfo, warning, update_type, origin, tooltip)
                            update.add_package(package, size, short_description, description)
                            package_updates[source_package] = update
                        else:
                            # Add the package to the Update
                            update = package_updates[source_package]
                            update.add_package(package, size, short_description, description)

                self.fetch_l10n_descriptions(package_names)

                for source_package in package_updates.keys():

                    package_update = package_updates[source_package]

                    if (new_mintupdate and package_update.name != "mintupdate" and package_update.name != "mint-upgrade-info"):
                        continue

                    if source_package in aliases.keys():
                        alias = aliases[source_package]
                        package_update.alias = alias.name
                        package_update.short_description = alias.short_description
                        package_update.description = alias.description

                    else:
                        # l10n descriptions
                        self.l10n_descriptions(package_update)
                        package_update.short_description = self.clean_l10n_short_description(package_update.short_description)
                        package_update.description = self.clean_l10n_description(package_update.description)

                    security_update = (package_update.type == "security")

                    if ((self.application.settings.get_boolean("level" + str(package_update.level) + "-is-visible")) or (security_update and self.application.settings.get_boolean('security-updates-are-visible'))):
                        iter = model.insert_before(None, None)
                        if (security_update and self.application.settings.get_boolean('security-updates-are-safe')):
                            model.set_value(iter, UPDATE_CHECKED, "true")
                            num_safe = num_safe + 1
                            download_size = download_size + package_update.size
                        elif (self.application.settings.get_boolean("level" + str(package_update.level) + "-is-safe")):
                            model.set_value(iter, UPDATE_CHECKED, "true")
                            num_safe = num_safe + 1
                            download_size = download_size + package_update.size
                        else:
                            model.set_value(iter, UPDATE_CHECKED, "false")

                        model.row_changed(model.get_path(iter), iter)

                        shortdesc = package_update.short_description
                        if len(shortdesc) > 100:
                            shortdesc = shortdesc[:100] + "..."
                        if (self.application.settings.get_boolean("show-descriptions")):
                            model.set_value(iter, UPDATE_ALIAS, package_update.alias + "\n<small><span foreground='#5C5C5C'>%s</span></small>" % shortdesc)
                        else:
                            model.set_value(iter, UPDATE_ALIAS, package_update.alias)
                        model.set_value(iter, UPDATE_LEVEL_PIX, GdkPixbuf.Pixbuf.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/level" + str(package_update.level) + ".png"))
                        model.set_value(iter, UPDATE_OLD_VERSION, package_update.oldVersion)
                        model.set_value(iter, UPDATE_NEW_VERSION, package_update.newVersion)
                        model.set_value(iter, UPDATE_LEVEL_STR, str(package_update.level))
                        model.set_value(iter, UPDATE_SIZE, package_update.size)
                        model.set_value(iter, UPDATE_SIZE_STR, size_to_string(package_update.size))
                        model.set_value(iter, UPDATE_TYPE_PIX, GdkPixbuf.Pixbuf.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/update-type-%s.png" % package_update.type))
                        model.set_value(iter, UPDATE_TYPE, package_update.type)
                        model.set_value(iter, UPDATE_TOOLTIP, package_update.tooltip)
                        model.set_value(iter, UPDATE_SORT_STR, "%s%s" % (str(package_update.level), package_update.alias))
                        model.set_value(iter, UPDATE_OBJ, package_update)
                        num_visible = num_visible + 1

                Gdk.threads_enter()
                if (new_mintupdate):
                    self.statusString = _("A new version of the update manager is available")
                    self.application.set_status(self.statusString, self.statusString, "mintupdate-updates-available", True)
                    self.application.logger.write("Found a new version of mintupdate")
                else:
                    if (num_safe > 0):
                        if (num_safe == 1):
                            if (num_ignored == 0):
                                self.statusString = _("1 recommended update available (%(size)s)") % {'size':size_to_string(download_size)}
                            elif (num_ignored == 1):
                                self.statusString = _("1 recommended update available (%(size)s), 1 ignored") % {'size':size_to_string(download_size)}
                            elif (num_ignored > 1):
                                self.statusString = _("1 recommended update available (%(size)s), %(ignored)d ignored") % {'size':size_to_string(download_size), 'ignored':num_ignored}
                        else:
                            if (num_ignored == 0):
                                self.statusString = _("%(recommended)d recommended updates available (%(size)s)") % {'recommended':num_safe, 'size':size_to_string(download_size)}
                            elif (num_ignored == 1):
                                self.statusString = _("%(recommended)d recommended updates available (%(size)s), 1 ignored") % {'recommended':num_safe, 'size':size_to_string(download_size)}
                            elif (num_ignored > 0):
                                self.statusString = _("%(recommended)d recommended updates available (%(size)s), %(ignored)d ignored") % {'recommended':num_safe, 'size':size_to_string(download_size), 'ignored':num_ignored}
                        self.application.set_status(self.statusString, self.statusString, "mintupdate-updates-available", True)
                        self.application.logger.write("Found " + str(num_safe) + " recommended software updates")
                    else:
                        if num_visible == 0:
                            self.application.builder.get_object("notebook_status").set_current_page(TAB_UPTODATE)
                        self.application.set_status(_("Your system is up to date"), _("Your system is up to date"), "mintupdate-up-to-date", not self.application.settings.get_boolean("hide-systray"))
                        self.application.logger.write("System is up to date")

                Gdk.threads_leave()

            Gdk.threads_enter()
            self.application.logger.write("Refresh finished")

            # Stop the blinking
            self.application.builder.get_object("notebook_details").set_current_page(0)
            if (not self.application.app_hidden):
                self.application.window.get_window().set_cursor(None)
            self.application.treeview.set_model(model)
            del model
            self.application.window.set_sensitive(True)
            self.application.builder.get_object("vpaned1").set_position(vpaned_position)

            try:
                sources_path = "/etc/apt/sources.list.d/official-package-repositories.list"
                if os.path.exists("/usr/bin/mintsources") and os.path.exists(sources_path):
                    mirror_url = None
                    infobar_message = None
                    infobar_message_type = Gtk.MessageType.QUESTION
                    codename = lsb_release.get_distro_information()['CODENAME']
                    with open("/etc/apt/sources.list.d/official-package-repositories.list", 'r') as sources_file:
                        for line in sources_file:
                            line = line.strip()
                            if line.startswith("deb ") and "%s main upstream import" % codename in line:
                                mirror_url = line.split()[1]
                                if mirror_url.endswith("/"):
                                    mirror_url = mirror_url[:-1]
                                break
                    if mirror_url is None:
                        # Unable to find the Mint mirror being used..
                        pass
                    elif mirror_url == "http://packages.linuxmint.com":
                        if not self.application.settings.get_boolean("default-repo-is-ok"):
                            infobar_message = "%s\n<small>%s</small>" % (_("Do you want to switch to a local mirror?"), _("Local mirrors are usually faster than packages.linuxmint.com"))
                    elif not self.application.app_hidden:
                        # Only perform up-to-date checks when refreshing from the UI (keep the load lower on servers)
                        mirror_timestamp = self.get_url_last_modified("%s/db/version" % mirror_url)
                        if mirror_timestamp is None:
                            infobar_message = "%s\n<small>%s</small>" % (_("Please switch to another mirror"), _("%s is not up to date") % mirror_url)
                            infobar_message_type = Gtk.MESSAGE_WARNING
                        else:
                            mint_timestamp = self.get_url_last_modified("http://packages.linuxmint.com/db/version")
                            if mint_timestamp is not None:
                                mint_date = datetime.datetime.fromtimestamp(mint_timestamp)
                                now = datetime.datetime.now()
                                mint_age = (now - mint_date).days
                                if (mint_age > 2):
                                    mirror_date = datetime.datetime.fromtimestamp(mirror_timestamp)
                                    mirror_age = (mint_date - mirror_date).days
                                    if (mirror_age > 2):
                                        infobar_message = "%s\n<small>%s</small>" % (_("Please switch to another mirror"), _("The last update on %(mirror)s was %(days)d days ago") % {'mirror': mirror_url, 'days':(now - mirror_date).days})
                                        infobar_message_type = Gtk.MESSAGE_WARNING
                    if infobar_message is not None:
                        infobar = Gtk.InfoBar()
                        infobar.set_message_type(infobar_message_type)
                        info_label = Gtk.Label()
                        info_label.set_markup(infobar_message)
                        infobar.get_content_area().pack_start(info_label,False, False,0)
                        infobar.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
                        infobar.connect("response", self._on_infobar_response)
                        self.application.builder.get_object("hbox_infobar").pack_start(infobar, True, True,0)
                        infobar.show_all()
            except Exception as e:
                print (e)
                # best effort, just print out the error
                print("An exception occurred while checking if the repositories were up to date: %s" % sys.exc_info()[0])

            Gdk.threads_leave()

        except Exception as e:
            print (e)
            print("-- Exception occured in the refresh thread: " + str(sys.exc_info()[0]))
            self.application.logger.write_error("Exception occured in the refresh thread: " + str(sys.exc_info()[0]))
            Gdk.threads_enter()
            self.application.set_status(_("Could not refresh the list of updates"), _("Could not refresh the list of updates"), "mintupdate-error", True)
            if (not self.application.app_hidden):
                self.application.window.get_window().set_cursor(None)
            self.application.window.set_sensitive(True)
            self.application.builder.get_object("vpaned1").set_position(vpaned_position)
            Gdk.threads_leave()

    def _on_infobar_response(self, infobar, response_id):
        infobar.destroy()
        subprocess.Popen(["mintsources"])

    def get_url_last_modified(self, url):
        try:
            c = pycurl.Curl()
            c.setopt(pycurl.URL, url)
            c.setopt(pycurl.CONNECTTIMEOUT, 5)
            c.setopt(pycurl.TIMEOUT, 30)
            c.setopt(pycurl.FOLLOWLOCATION, 1)
            c.setopt(pycurl.NOBODY, 1)
            c.setopt(pycurl.OPT_FILETIME, 1)
            c.perform()
            filetime = c.getinfo(pycurl.INFO_FILETIME)
            if filetime < 0:
                return None
            else:
                return filetime
        except Exception as e:
            print (e)
            return None

    def checkDependencies(self, changes, cache):
        foundSomething = False
        for pkg in changes:
            for dep in pkg.candidateDependencies:
                for o in dep.or_dependencies:
                    try:
                        if cache[o.name].isUpgradable:
                            pkgFound = False
                            for pkg2 in changes:
                                if o.name == pkg2.name:
                                    pkgFound = True
                            if pkgFound == False:
                                newPkg = cache[o.name]
                                changes.append(newPkg)
                                foundSomething = True
                    except Exception as e:
                        print (e)
                        pass # don't know why we get these..
        if (foundSomething):
            changes = self.checkDependencies(changes, cache)
        return changes

class Logger():

    def __init__(self):
        logdir = "/tmp/mintUpdate/"
        if not os.path.exists(logdir):
            os.system("mkdir -p " + logdir)
            os.system("chmod a+rwx " + logdir)
        self.log = tempfile.NamedTemporaryFile(mode = 'w', prefix = logdir, delete=False)
        try:
            os.system("chmod a+rw %s" % self.log.name)
        except Exception as e:
            print (e)
            print(sys.exc_info()[0])

    def write(self, line):
        try:
            self.log.writelines("%s ++ %s \n" % (datetime.datetime.now().strftime('%m.%d@%H:%M'), line))
            self.log.flush()
        except:
            pass # cause it might be closed already

    def write_error(self, line):
        try:
            self.log.writelines("%s -- %s \n" % (datetime.datetime.now().strftime('%m.%d@%H:%M'), line))
            self.log.flush()
        except:
            pass # cause it might be closed already

    def close(self):
        try:
            self.log.close()
        except:
            pass # cause it might be closed already


class MintUpdate():

    def __init__(self):
        Gdk.threads_init()
        self.app_hidden = True
        self.logger = Logger()
        self.logger.write("Launching mintUpdate")
        self.settings = Gio.Settings("com.linuxmint.updates")
        self.statusIcon = Gtk.StatusIcon()
        self.statusIcon.set_from_icon_name("mintupdate-checking")
        self.statusIcon.set_tooltip_text (_("Checking for updates"))
        self.statusIcon.set_visible(not self.settings.get_boolean("hide-systray"))

        #Set the Glade file
        gladefile = "/usr/share/linuxmint/mintupdate/main.ui"
        self.builder = Gtk.Builder()
        self.builder.add_from_file(gladefile)
        self.statusbar = self.builder.get_object("statusbar")
        self.context_id = self.statusbar.get_context_id("mintUpdate")
        self.window = self.builder.get_object("main_window")
        self.treeview = self.builder.get_object("treeview_update")

        try:
            self.window.set_title(_("Update Manager"))
            self.window.set_default_size(self.settings.get_int('window-width'), self.settings.get_int('window-height'))
            self.builder.get_object("vpaned1").set_position(self.settings.get_int('window-pane-position'))

            vbox = self.builder.get_object("vbox_main")
            self.window.set_icon_name("mintupdate")

            accel_group = Gtk.AccelGroup()
            self.window.add_accel_group(accel_group)

            # Get the window socket (needed for synaptic later on)

            if os.getuid() != 0 :
                # If we're not in root mode do that (don't know why it's needed.. very weird)
                socket = Gtk.Socket()
                vbox.pack_start(socket, False, False, 0)
                socket.show()
                window_id = repr(socket.get_id())

            self.buffer = self.builder.get_object("textview_description").get_buffer()
            self.buffer.create_tag("dimmed", scale=0.9, foreground="#5C5C5C", style=Pango.Style.ITALIC)

            # the treeview
            cr = Gtk.CellRendererToggle()
            cr.connect("toggled", self.toggled)
            column1 = Gtk.TreeViewColumn(_("Upgrade"), cr)
            column1.set_cell_data_func(cr, self.celldatafunction_checkbox)
            column1.set_sort_column_id(UPDATE_CHECKED)
            column1.set_resizable(True)

            column2 = Gtk.TreeViewColumn(_("Package"), Gtk.CellRendererText(), markup=UPDATE_ALIAS)
            column2.set_sort_column_id(UPDATE_ALIAS)
            column2.set_resizable(True)

            column3 = Gtk.TreeViewColumn(_("Level"), Gtk.CellRendererPixbuf(), pixbuf=UPDATE_LEVEL_PIX)
            column3.set_sort_column_id(UPDATE_LEVEL_STR)
            column3.set_resizable(True)

            column4 = Gtk.TreeViewColumn(_("Old version"), Gtk.CellRendererText(), text=UPDATE_OLD_VERSION)
            column4.set_sort_column_id(UPDATE_OLD_VERSION)
            column4.set_resizable(True)

            column5 = Gtk.TreeViewColumn(_("New version"), Gtk.CellRendererText(), text=UPDATE_NEW_VERSION)
            column5.set_sort_column_id(UPDATE_NEW_VERSION)
            column5.set_resizable(True)

            column6 = Gtk.TreeViewColumn(_("Size"), Gtk.CellRendererText(), text=UPDATE_SIZE_STR)
            column6.set_sort_column_id(UPDATE_SIZE)
            column6.set_resizable(True)

            column7 = Gtk.TreeViewColumn(_("Type"), Gtk.CellRendererPixbuf(), pixbuf=UPDATE_TYPE_PIX)
            column7.set_sort_column_id(UPDATE_TYPE)
            column7.set_resizable(True)

            self.treeview.set_tooltip_column(UPDATE_TOOLTIP)

            self.treeview.append_column(column7)
            self.treeview.append_column(column3)
            self.treeview.append_column(column1)
            self.treeview.append_column(column2)
            self.treeview.append_column(column4)
            self.treeview.append_column(column5)
            self.treeview.append_column(column6)

            self.treeview.set_headers_clickable(True)
            self.treeview.set_reorderable(False)
            self.treeview.show()

            self.treeview.connect("button-release-event", self.treeview_right_clicked)
            self.treeview.connect("row-activated", self.treeview_row_activated)

            selection = self.treeview.get_selection()
            selection.connect("changed", self.display_selected_package)
            self.builder.get_object("notebook_details").connect("switch-page", self.switch_page)
            self.window.connect("delete_event", self.close_window)
            self.builder.get_object("tool_apply").connect("clicked", self.install)
            self.builder.get_object("tool_clear").connect("clicked", self.clear)
            self.builder.get_object("tool_select_all").connect("clicked", self.select_all)
            self.builder.get_object("tool_refresh").connect("clicked", self.force_refresh)

            menu = Gtk.Menu()
            menuItem3 = Gtk.ImageMenuItem(Gtk.STOCK_REFRESH)
            menuItem3.set_use_stock(True)
            menuItem3.connect('activate', self.force_refresh)
            menu.append(menuItem3)
            menuItem2 = Gtk.ImageMenuItem(Gtk.STOCK_DIALOG_INFO)
            menuItem2.set_use_stock(True)
            menuItem2.connect('activate', self.open_information)
            menu.append(menuItem2)
            menuItem4 = Gtk.ImageMenuItem(Gtk.STOCK_PREFERENCES)
            menuItem4.set_use_stock(True)
            menuItem4.connect('activate', self.open_preferences)
            menu.append(menuItem4)
            menuItem = Gtk.ImageMenuItem(Gtk.STOCK_QUIT)
            menuItem.set_use_stock(True)
            menuItem.connect('activate', self.quit_from_systray)
            menu.append(menuItem)

            self.statusIcon.connect('activate', self.on_statusicon_clicked)
            self.statusIcon.connect('popup-menu', self.show_statusicon_menu, menu)

            # Set text for all visible widgets (because of i18n)
            self.builder.get_object("tool_apply").set_label(_("Install Updates"))
            self.builder.get_object("tool_refresh").set_label(_("Refresh"))
            self.builder.get_object("tool_select_all").set_label(_("Select All"))
            self.builder.get_object("tool_clear").set_label(_("Clear"))
            self.builder.get_object("label9").set_text(_("Description"))
            self.builder.get_object("label8").set_text(_("Changelog"))

            self.builder.get_object("label_success").set_markup("<b>" + _("Your system is up to date") + "</b>")
            self.builder.get_object("label_error").set_markup("<b>" + _("Could not refresh the list of updates") + "</b>")
            self.builder.get_object("image_success_status").set_from_file("/usr/lib/linuxmint/mintUpdate/icons/yes.png")
            self.builder.get_object("image_error_status").set_from_file("/usr/lib/linuxmint/mintUpdate/rel_upgrades/failure.png")

            self.builder.get_object("vpaned1").set_position(self.settings.get_int('window-pane-position'))

            fileMenu = Gtk.MenuItem.new_with_mnemonic(_("_File"))
            fileSubmenu = Gtk.Menu()
            fileMenu.set_submenu(fileSubmenu)
            closeMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_CLOSE)
            closeMenuItem.set_use_stock(True)
            closeMenuItem.set_label(_("Close"))
            closeMenuItem.connect("activate", self.hide_main_window)
            fileSubmenu.append(closeMenuItem)

            editMenu = Gtk.MenuItem.new_with_mnemonic(_("_Edit"))
            editSubmenu = Gtk.Menu()
            editMenu.set_submenu(editSubmenu)
            prefsMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_PREFERENCES)
            prefsMenuItem.set_use_stock(True)
            prefsMenuItem.set_label(_("Preferences"))
            prefsMenuItem.connect("activate", self.open_preferences)
            editSubmenu.append(prefsMenuItem)
            if os.path.exists("/usr/bin/software-sources") or os.path.exists("/usr/bin/software-properties-gtk") or os.path.exists("/usr/bin/software-properties-kde"):
                sourcesMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_PREFERENCES)
                sourcesMenuItem.set_use_stock(True)
                sourcesMenuItem.set_image(Gtk.Image.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/software-properties.png"))
                sourcesMenuItem.set_label(_("Software sources"))
                sourcesMenuItem.connect("activate", self.open_repositories)
                editSubmenu.append(sourcesMenuItem)

            rel_edition = 'unknown'
            rel_codename = 'unknown'
            if os.path.exists("/etc/linuxmint/info"):
                with open("/etc/linuxmint/info", "r") as info:
                    for line in info:
                        line = line.strip()
                        if "EDITION=" in line:
                            rel_edition = line.split('=')[1].replace('"', '').split()[0]
                        if "CODENAME=" in line:
                            rel_codename = line.split('=')[1].replace('"', '').split()[0]

            rel_path = "/usr/share/mint-upgrade-info/%s" % rel_codename
            if os.path.exists(rel_path):
                with open(os.path.join(rel_path, "info")) as f:
                    config = dict([line.strip().split("=") for line in f])
                if rel_edition.lower() in config['editions']:
                    rel_target = config['target_name']
                    relUpgradeMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_PREFERENCES)
                    relUpgradeMenuItem.set_use_stock(True)
                    relUpgradeMenuItem.set_image(Gtk.Image.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/rel_upgrade.png"))
                    relUpgradeMenuItem.set_label(_("Upgrade to %s") % rel_target)
                    relUpgradeMenuItem.connect("activate", self.open_rel_upgrade)
                    editSubmenu.append(relUpgradeMenuItem)

            viewMenu = Gtk.MenuItem.new_with_mnemonic(_("_View"))
            viewSubmenu = Gtk.Menu()
            viewMenu.set_submenu(viewSubmenu)
            historyMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_INDEX)
            historyMenuItem.set_use_stock(True)
            historyMenuItem.set_label(_("History of updates"))
            historyMenuItem.connect("activate", self.open_history)
            kernelMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_EXECUTE)
            kernelMenuItem.set_use_stock(True)
            kernelMenuItem.set_label(_("Linux kernels"))
            kernelMenuItem.connect("activate", self.open_kernels)
            infoMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_DIALOG_INFO)
            infoMenuItem.set_use_stock(True)
            infoMenuItem.set_label(_("Information"))
            infoMenuItem.connect("activate", self.open_information)
            visibleColumnsMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_DIALOG_INFO)
            visibleColumnsMenuItem.set_use_stock(True)
            visibleColumnsMenuItem.set_label(_("Visible columns"))
            visibleColumnsMenu = Gtk.Menu()
            visibleColumnsMenuItem.set_submenu(visibleColumnsMenu)

            typeColumnMenuItem = Gtk.CheckMenuItem(_("Type"))
            typeColumnMenuItem.set_active(self.settings.get_boolean("show-type-column"))
            column7.set_visible(self.settings.get_boolean("show-type-column"))
            typeColumnMenuItem.connect("toggled", self.setVisibleColumn, column7, "show-type-column")
            visibleColumnsMenu.append(typeColumnMenuItem)

            levelColumnMenuItem = Gtk.CheckMenuItem(_("Level"))
            levelColumnMenuItem.set_active(self.settings.get_boolean("show-level-column"))
            column3.set_visible(self.settings.get_boolean("show-level-column"))
            levelColumnMenuItem.connect("toggled", self.setVisibleColumn, column3, "show-level-column")
            visibleColumnsMenu.append(levelColumnMenuItem)

            packageColumnMenuItem = Gtk.CheckMenuItem(_("Package"))
            packageColumnMenuItem.set_active(self.settings.get_boolean("show-package-column"))
            column2.set_visible(self.settings.get_boolean("show-package-column"))
            packageColumnMenuItem.connect("toggled", self.setVisibleColumn, column2, "show-package-column")
            visibleColumnsMenu.append(packageColumnMenuItem)

            oldVersionColumnMenuItem = Gtk.CheckMenuItem(_("Old version"))
            oldVersionColumnMenuItem.set_active(self.settings.get_boolean("show-old-version-column"))
            column4.set_visible(self.settings.get_boolean("show-old-version-column"))
            oldVersionColumnMenuItem.connect("toggled", self.setVisibleColumn, column4, "show-old-version-column")
            visibleColumnsMenu.append(oldVersionColumnMenuItem)

            newVersionColumnMenuItem = Gtk.CheckMenuItem(_("New version"))
            newVersionColumnMenuItem.set_active(self.settings.get_boolean("show-new-version-column"))
            column5.set_visible(self.settings.get_boolean("show-new-version-column"))
            newVersionColumnMenuItem.connect("toggled", self.setVisibleColumn, column5, "show-new-version-column")
            visibleColumnsMenu.append(newVersionColumnMenuItem)

            sizeColumnMenuItem = Gtk.CheckMenuItem(_("Size"))
            sizeColumnMenuItem.set_active(self.settings.get_boolean("show-size-column"))
            column6.set_visible(self.settings.get_boolean("show-size-column"))
            sizeColumnMenuItem.connect("toggled", self.setVisibleColumn, column6, "show-size-column")
            visibleColumnsMenu.append(sizeColumnMenuItem)

            viewSubmenu.append(visibleColumnsMenuItem)

            descriptionsMenuItem = Gtk.CheckMenuItem(_("Show descriptions"))
            descriptionsMenuItem.set_active(self.settings.get_boolean("show-descriptions"))
            descriptionsMenuItem.connect("toggled", self.setVisibleDescriptions)
            viewSubmenu.append(descriptionsMenuItem)

            viewSubmenu.append(historyMenuItem)

            try:
                # Only support kernel selection in Linux Mint (not LMDE)
                if (subprocess.check_output("lsb_release -is", shell = True).strip() == b"LinuxMint" and float(subprocess.check_output("lsb_release -rs", shell = True).strip()) >= 13):
                    viewSubmenu.append(kernelMenuItem)
            except Exception as e:
                print (e)
                print(sys.exc_info()[0])
            viewSubmenu.append(infoMenuItem)

            helpMenu = Gtk.MenuItem.new_with_mnemonic(_("_Help"))
            helpSubmenu = Gtk.Menu()
            helpMenu.set_submenu(helpSubmenu)
            if os.path.exists("/usr/share/help/C/linuxmint"):
                helpMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_HELP)
                helpMenuItem.set_use_stock(True)
                helpMenuItem.set_label(_("Contents"))
                helpMenuItem.connect("activate", self.open_help)
                key, mod = Gtk.accelerator_parse("F1")
                helpMenuItem.add_accelerator("activate", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
                helpSubmenu.append(helpMenuItem)
            aboutMenuItem = Gtk.ImageMenuItem(Gtk.STOCK_ABOUT)
            aboutMenuItem.set_use_stock(True)
            aboutMenuItem.set_label(_("About"))
            aboutMenuItem.connect("activate", self.open_about)
            helpSubmenu.append(aboutMenuItem)

            self.builder.get_object("menubar1").append(fileMenu)
            self.builder.get_object("menubar1").append(editMenu)
            self.builder.get_object("menubar1").append(viewMenu)
            self.builder.get_object("menubar1").append(helpMenu)

            if len(sys.argv) > 1:
                showWindow = sys.argv[1]
                if (showWindow == "show"):
                    self.window.show_all()
                    self.builder.get_object("vpaned1").set_position(self.settings.get_int('window-pane-position'))
                    self.app_hidden = False

            self.builder.get_object("notebook_details").set_current_page(0)

            refresh = RefreshThread(self)
            refresh.start()

            auto_refresh = AutomaticRefreshThread(self)
            auto_refresh.start()

            Gdk.threads_enter()
            Gtk.main()
            Gdk.threads_leave()

        except Exception as e:
            print (e)
            print(sys.exc_info()[0])
            self.logger.write_error("Exception occured in main thread: " + str(sys.exc_info()[0]))
            self.logger.close()

######### UTILITY FUNCTIONS #########
    def hide_window(self, widget, window):
        window.hide()

    def refresh(self):
        refresh = RefreshThread(self)
        refresh.start()

    def set_status_message(self, message):
        self.statusbar.push(self.context_id, message)

    def set_status(self, message, tooltip, icon, visible):
        self.set_status_message(message)
        self.statusIcon.set_from_icon_name(icon)
        self.statusIcon.set_tooltip_text(tooltip)
        self.statusIcon.set_visible(visible)

######### WINDOW/STATUSICON ##########

    def close_window(self, window, event):
        window.hide()
        self.save_window_size()
        self.app_hidden = True
        return True

    def save_window_size(self):
        self.settings.set_int('window-width', self.window.get_size()[0])
        self.settings.set_int('window-height', self.window.get_size()[1])
        self.settings.set_int('window-pane-position', self.builder.get_object("vpaned1").get_position())

######### MENU/TOOLBAR FUNCTIONS ################

    def hide_main_window(self, widget):
        self.window.hide()
        self.app_hidden = True

    def setVisibleColumn(self, checkmenuitem, column, key):
        self.settings.set_boolean(key, checkmenuitem.get_active())
        column.set_visible(checkmenuitem.get_active())

    def setVisibleDescriptions(self, checkmenuitem):
        self.settings.set_boolean("show-descriptions", checkmenuitem.get_active())
        refresh = RefreshThread(self)
        refresh.start()

    def clear(self, widget):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while (iter != None):
            model.set_value(iter, 0, "false")
            iter = model.iter_next(iter)
        self.set_status_message(_("No updates selected"))

    def select_all(self, widget):
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while (iter != None):
            model.set_value(iter, UPDATE_CHECKED, "true")
            iter = model.iter_next(iter)
        iter = model.get_iter_first()
        download_size = 0
        num_selected = 0
        while (iter != None):
            checked = model.get_value(iter, UPDATE_CHECKED)
            if (checked == "true"):
                size = model.get_value(iter, UPDATE_SIZE)
                download_size = download_size + size
                num_selected = num_selected + 1
            iter = model.iter_next(iter)
        if num_selected == 0:
            self.set_status_message(_("No updates selected"))
        elif num_selected == 1:
            self.set_status_message(_("%(selected)d update selected (%(size)s)") % {'selected':num_selected, 'size':size_to_string(download_size)})
        else:
            self.set_status_message(_("%(selected)d updates selected (%(size)s)") % {'selected':num_selected, 'size':size_to_string(download_size)})

    def force_refresh(self, widget):
        refresh = RefreshThread(self, root_mode=True)
        refresh.start()

    def install(self, widget):
        install = InstallThread(self)
        install.start()


######### TREEVIEW/SELECTION FUNCTIONS #######

    def celldatafunction_checkbox(self, column, cell, model, iter, data):
        cell.set_property("activatable", True)
        checked = model.get_value(iter, UPDATE_CHECKED)
        if (checked == "true"):
            cell.set_property("active", True)
        else:
            cell.set_property("active", False)

    def treeview_row_activated(self, treeview, path, view_column):
        self.toggled(None, path)

    def toggled(self, renderer, path):
        model = self.treeview.get_model()
        iter = model.get_iter(path)
        if (iter != None):
            checked = model.get_value(iter, UPDATE_CHECKED)
            if (checked == "true"):
                model.set_value(iter, UPDATE_CHECKED, "false")
            else:
                model.set_value(iter, UPDATE_CHECKED, "true")

        iter = model.get_iter_first()
        download_size = 0
        num_selected = 0
        while (iter != None):
            checked = model.get_value(iter, UPDATE_CHECKED)
            if (checked == "true"):
                size = model.get_value(iter, UPDATE_SIZE)
                download_size = download_size + size
                num_selected = num_selected + 1
            iter = model.iter_next(iter)
        if num_selected == 0:
            self.set_status_message(_("No updates selected"))
        elif num_selected == 1:
            self.set_status_message(_("%(selected)d update selected (%(size)s)") % {'selected':num_selected, 'size':size_to_string(download_size)})
        else:
            self.set_status_message(_("%(selected)d updates selected (%(size)s)") % {'selected':num_selected, 'size':size_to_string(download_size)})

    def display_selected_package(self, selection):
        try:
            self.builder.get_object("textview_description").get_buffer().set_text("")
            self.builder.get_object("textview_changes").get_buffer().set_text("")
            (model, iter) = selection.get_selected()
            if (iter != None):
                package_update = model.get_value(iter, UPDATE_OBJ)
                if self.builder.get_object("notebook_details").get_current_page() == 0:
                    # Description tab
                    description = package_update.description
                    description = description.split("\\n")
                    for line in description:
                        self.buffer.insert(self.buffer.get_end_iter(), line)
                        self.buffer.insert(self.buffer.get_end_iter(), "\n")

                    if (len(package_update.packages) > 1):
                        dimmed_description = "%s %s" % (_("This update contains %d packages: ") % len(package_update.packages), " ".join(sorted(package_update.packages)))
                        self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), dimmed_description, "dimmed")
                    elif (package_update.packages[0] != package_update.alias):
                        dimmed_description = "%s %s" % (_("This update contains 1 package: "), package_update.packages[0])
                        self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), dimmed_description, "dimmed")
                else:
                    # Changelog tab
                    retriever = ChangelogRetriever(package_update, self)
                    retriever.start()
        except Exception as e:
            print (e)
            print(sys.exc_info()[0])

    def treeview_right_clicked(self, widget, event):
        if event.button == 3:
            (model, iter) = widget.get_selection().get_selected()
            if (iter != None):
                package_update = model.get_value(iter, UPDATE_OBJ)
                menu = Gtk.Menu()
                menuItem = Gtk.MenuItem.new_with_mnemonic(_("Ignore updates for this package"))
                menuItem.connect("activate", self.add_to_ignore_list, package_update.name)
                menu.append(menuItem)
                menu.attach_to_widget (widget, None)
                menu.show_all()
                menu.popup(None, None, None, None, event.button, event.time)

    def add_to_ignore_list(self, widget, pkg):
        blacklist = self.settings.get_strv("blacklisted-packages")
        blacklist.append(pkg)
        self.settings.set_strv("blacklisted-packages", blacklist)
        refresh = RefreshThread(self)
        refresh.start()

    def switch_page(self, notebook, page, page_num):
        selection = self.treeview.get_selection()
        (model, iter) = selection.get_selected()
        if (iter != None):
            package_update = model.get_value(iter, UPDATE_OBJ)
            if (page_num == 0):
                # Description tab
                description = package_update.description
                self.buffer.set_text(description)
                if (len(package_update.packages) > 1):
                    dimmed_description = "\n%s %s" % (_("This update contains %d packages: ") % len(package_update.packages), " ".join(sorted(package_update.packages)))
                    self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), dimmed_description, "dimmed")
                elif (package_update.packages[0] != package_update.name):
                    dimmed_description = "\n%s %s" % (_("This update contains 1 package: "), package_update.packages[0])
                    self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), dimmed_description, "dimmed")
            else:
                # Changelog tab
                retriever = ChangelogRetriever(package_update, self)
                retriever.start()


######### SYSTRAY ####################

    def show_statusicon_menu(self, icon, button, time, menu):
        menu.show_all()
        menu.popup(None, None, None, None, button, time)

    def on_statusicon_clicked(self, widget):
        if (self.app_hidden):
            self.window.show_all()
        else:
            self.window.hide()
            self.save_window_size()
        self.app_hidden = not self.app_hidden

    def quit_from_systray(self, widget, data = None):
        if data:
            data.set_visible(False)
        try:
            self.logger.write("Exiting - requested by user")
            self.logger.close()
            self.save_window_size()
        except:
            pass # cause log might already been closed
        # Whatever works best heh :)
        os.system("kill -9 %s &" % os.getpid())

######### INFORMATION SCREEN #########

    def open_information(self, widget):
        gladefile = "/usr/share/linuxmint/mintupdate/information.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        window = builder.get_object("main_window")
        window.set_title(_("Information") + " - " + _("Update Manager"))
        window.set_icon_name("mintupdate")
        builder.get_object("close_button").connect("clicked", self.hide_window, window)
        builder.get_object("label4").set_text(_("Process ID:"))
        builder.get_object("label5").set_text(_("Log file:"))
        builder.get_object("processid_label").set_text(str(os.getpid()))
        builder.get_object("log_filename").set_text(str(self.logger.log.name))
        txtbuffer = Gtk.TextBuffer()
        txtbuffer.set_text(subprocess.check_output("cat " + self.logger.log.name, shell = True).decode("utf-8"))
        builder.get_object("log_textview").set_buffer(txtbuffer)

######### HISTORY SCREEN #########

    def open_history(self, widget):
        gladefile = "/usr/share/linuxmint/mintupdate/history.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        window = builder.get_object("main_window")
        window.set_icon_name("mintupdate")
        window.set_title(_("History of updates") + " - " + _("Update Manager"))

        treeview = builder.get_object("treeview_history")
        column1 = Gtk.TreeViewColumn(_("Date"), Gtk.CellRendererText(), text=1)
        column1.set_sort_column_id(1)
        column1.set_resizable(True)
        column2 = Gtk.TreeViewColumn(_("Package"), Gtk.CellRendererText(), text=0)
        column2.set_sort_column_id(0)
        column2.set_resizable(True)
        column3 = Gtk.TreeViewColumn(_("Old version"), Gtk.CellRendererText(), text=2)
        column3.set_sort_column_id(2)
        column3.set_resizable(True)
        column4 = Gtk.TreeViewColumn(_("New version"), Gtk.CellRendererText(), text=3)
        column4.set_sort_column_id(3)
        column4.set_resizable(True)
        treeview.append_column(column1)
        treeview.append_column(column2)
        treeview.append_column(column3)
        treeview.append_column(column4)
        treeview.set_headers_clickable(True)
        treeview.set_reorderable(False)
        treeview.set_search_column(0)
        treeview.set_enable_search(True)
        treeview.show()

        model = Gtk.TreeStore(str, str, str, str) # (packageName, date, oldVersion, newVersion)
        if (os.path.exists("/var/log/dpkg.log")):
            updates = subprocess.check_output("cat /var/log/dpkg.log /var/log/dpkg.log.? 2>/dev/null | egrep \"upgrade\"", shell = True).decode("utf-8")
            updates = updates.split("\n")
            for pkg in updates:
                values = pkg.split(" ")
                if len(values) == 6:
                    (date, time, action, package, oldVersion, newVersion) = values
                    if action != "upgrade" or oldVersion == newVersion:
                        continue
                    if ":" in package:
                        package = package.split(":")[0]

                    iter = model.insert_before(None, None)
                    model.set_value(iter, 0, package)
                    model.row_changed(model.get_path(iter), iter)
                    model.set_value(iter, 1, "%s - %s" % (date, time))
                    model.set_value(iter, 2, oldVersion)
                    model.set_value(iter, 3, newVersion)

        model.set_sort_column_id( 1, Gtk.SortType.DESCENDING )
        treeview.set_model(model)
        del model
        builder.get_object("button_close").connect("clicked", self.hide_window, window)

######### HELP/ABOUT/SOURCES SCREEN #########

    def open_help(self, widget):
        os.system("yelp help:linuxmint/software-updates &")

    def open_rel_upgrade(self, widget):
        os.system("/usr/bin/mint-release-upgrade &")

    def open_about(self, widget):
        dlg = Gtk.AboutDialog()
        dlg.set_title(_("About") + " - " + _("Update Manager"))
        dlg.set_program_name("mintUpdate")
        dlg.set_comments(_("Update Manager"))
        try:
            h = open('/usr/share/common-licenses/GPL','r')
            s = h.readlines()
            gpl = ""
            for line in s:
                gpl += line
            h.close()
            dlg.set_license(gpl)
        except Exception as e:
            print (e)
            print(sys.exc_info()[0])

        dlg.set_icon_name("mintupdate")
        dlg.set_logo_icon_name("mintupdate")
        dlg.set_website("http://www.github.com/linuxmint/mintupdate")
        def close(w, res):
            if res == Gtk.ResponseType.CANCEL or res == Gtk.ResponseType.DELETE_EVENT:
                w.hide()
        dlg.connect("response", close)
        dlg.show()

    def open_repositories(self, widget):
        if os.path.exists("/usr/bin/software-sources"):
            os.system("/usr/bin/software-sources &")
        elif os.path.exists("/usr/bin/software-properties-gtk"):
            os.system("/usr/bin/software-properties-gtk &")
        elif os.path.exists("/usr/bin/software-properties-kde"):
            os.system("/usr/bin/software-properties-kde &")

######### PREFERENCES SCREEN #########

    def open_preferences(self, widget):
        gladefile = "/usr/share/linuxmint/mintupdate/preferences.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        window = builder.get_object("main_window")
        window.set_title(_("Preferences") + " - " + _("Update Manager"))
        window.set_icon_name("mintupdate")
        window.show()

        #l10n
        builder.get_object("label37").set_text(_("Levels"))
        builder.get_object("label36").set_text(_("Auto-Refresh"))
        builder.get_object("label39").set_markup("<b>" + _("Level") + "</b>")
        builder.get_object("label40").set_markup("<b>" + _("Description") + "</b>")
        builder.get_object("label48").set_markup("<b>" + _("Tested?") + "</b>")
        builder.get_object("label54").set_markup("<b>" + _("Origin") + "</b>")
        builder.get_object("label41").set_markup("<b>" + _("Safe?") + "</b>")
        builder.get_object("label42").set_markup("<b>" + _("Visible?") + "</b>")
        builder.get_object("label43").set_text(_("Certified updates. Tested through Romeo or directly maintained by Linux Mint."))
        builder.get_object("label44").set_text(_("Recommended updates. Tested and approved by Linux Mint."))
        builder.get_object("label45").set_text(_("Safe updates. Not tested but believed to be safe."))
        builder.get_object("label46").set_text(_("Unsafe updates. Could potentially affect the stability of the system."))
        builder.get_object("label47").set_text(_("Dangerous updates. Known to affect the stability of the systems depending on certain specs or hardware."))
        builder.get_object("label55").set_text(_("Linux Mint"))
        builder.get_object("label56").set_text(_("Upstream"))
        builder.get_object("label57").set_text(_("Upstream"))
        builder.get_object("label58").set_text(_("Upstream"))
        builder.get_object("label59").set_text(_("Upstream"))
        builder.get_object("label_refresh").set_text(_("First, refresh the list of updates after:"))
        builder.get_object("label_autorefresh").set_text(_("Then, refresh the list of updates every:"))
        builder.get_object("label82").set_text("<i>" + _("Note: The list only gets refreshed while the update manager window is closed (system tray mode).") + "</i>")
        builder.get_object("label82").set_use_markup(True)
        builder.get_object("label83").set_text(_("Options"))
        builder.get_object("checkbutton_dist_upgrade").set_label(_("Include updates which require the installation of new packages or the removal of installed packages"))
        builder.get_object("checkbutton_hide_window_after_update").set_label(_("Hide the update manager after applying updates"))
        builder.get_object("checkbutton_hide_systray").set_label(_("Only show a tray icon when updates are available or in case of errors"))
        builder.get_object("checkbutton_default_repo_is_ok").set_label(_("Don't suggest to switch to a local mirror"))
        builder.get_object("checkbutton_security_visible").set_label(_("Always show security updates"))
        builder.get_object("checkbutton_security_safe").set_label(_("Always select and trust security updates"))
        builder.get_object("label_minutes").set_text(_("minutes"))
        builder.get_object("label_hours").set_text(_("hours"))
        builder.get_object("label_days").set_text(_("days"))

        builder.get_object("visible1").set_active(self.settings.get_boolean("level1-is-visible"))
        builder.get_object("visible2").set_active(self.settings.get_boolean("level2-is-visible"))
        builder.get_object("visible3").set_active(self.settings.get_boolean("level3-is-visible"))
        builder.get_object("visible4").set_active(self.settings.get_boolean("level4-is-visible"))
        builder.get_object("visible5").set_active(self.settings.get_boolean("level5-is-visible"))
        builder.get_object("safe1").set_active(self.settings.get_boolean("level1-is-safe"))
        builder.get_object("safe2").set_active(self.settings.get_boolean("level2-is-safe"))
        builder.get_object("safe3").set_active(self.settings.get_boolean("level3-is-safe"))
        builder.get_object("safe4").set_active(self.settings.get_boolean("level4-is-safe"))
        builder.get_object("safe5").set_active(self.settings.get_boolean("level5-is-safe"))
        builder.get_object("checkbutton_security_visible").set_active(self.settings.get_boolean("security-updates-are-visible"))
        builder.get_object("checkbutton_security_safe").set_active(self.settings.get_boolean("security-updates-are-safe"))
        builder.get_object("checkbutton_dist_upgrade").set_active(self.settings.get_boolean("dist-upgrade"))
        builder.get_object("checkbutton_hide_window_after_update").set_active(self.settings.get_boolean("hide-window-after-update"))
        builder.get_object("checkbutton_hide_systray").set_active(self.settings.get_boolean("hide-systray"))
        builder.get_object("checkbutton_default_repo_is_ok").set_active(self.settings.get_boolean("default-repo-is-ok"))

        builder.get_object("refresh_days").set_range(0, 365)
        builder.get_object("refresh_days").set_increments(1, 10)
        builder.get_object("refresh_days").set_value(self.settings.get_int("refresh-days"))
        builder.get_object("refresh_hours").set_range(0, 59)
        builder.get_object("refresh_hours").set_increments(1, 5)
        builder.get_object("refresh_hours").set_value(self.settings.get_int("refresh-hours"))
        builder.get_object("refresh_minutes").set_range(0, 59)
        builder.get_object("refresh_minutes").set_increments(1, 5)
        builder.get_object("refresh_minutes").set_value(self.settings.get_int("refresh-minutes"))
        builder.get_object("autorefresh_days").set_range(0, 365)
        builder.get_object("autorefresh_days").set_increments(1, 10)
        builder.get_object("autorefresh_days").set_value(self.settings.get_int("autorefresh-days"))
        builder.get_object("autorefresh_hours").set_range(0, 59)
        builder.get_object("autorefresh_hours").set_increments(1, 5)
        builder.get_object("autorefresh_hours").set_value(self.settings.get_int("autorefresh-hours"))
        builder.get_object("autorefresh_minutes").set_range(0, 59)
        builder.get_object("autorefresh_minutes").set_increments(1, 5)
        builder.get_object("autorefresh_minutes").set_value(self.settings.get_int("autorefresh-minutes"))

        treeview_blacklist = builder.get_object("treeview_blacklist")
        column1 = Gtk.TreeViewColumn(_("Ignored updates"), Gtk.CellRendererText(), text=0)
        column1.set_sort_column_id(0)
        column1.set_resizable(True)
        treeview_blacklist.append_column(column1)
        treeview_blacklist.set_headers_clickable(True)
        treeview_blacklist.set_reorderable(False)
        treeview_blacklist.show()
        model = Gtk.TreeStore(str)
        model.set_sort_column_id( 0, Gtk.SortType.ASCENDING )
        treeview_blacklist.set_model(model)
        blacklist = self.settings.get_strv("blacklisted-packages")
        for ignored_pkg in blacklist:
            iter = model.insert_before(None, None)
            model.set_value(iter, 0, ignored_pkg)

        builder.get_object("pref_button_cancel").connect("clicked", self.hide_window, window)
        builder.get_object("pref_button_apply").connect("clicked", self.save_preferences, builder)
        builder.get_object("button_add").connect("clicked", self.add_blacklisted_package, treeview_blacklist)
        builder.get_object("button_remove").connect("clicked", self.remove_blacklisted_package, treeview_blacklist)
        builder.get_object("button_add").set_always_show_image(True)
        builder.get_object("button_remove").set_always_show_image(True)

    def save_preferences(self, widget, builder):
        self.settings.set_boolean('hide-window-after-update', builder.get_object("checkbutton_hide_window_after_update").get_active())
        self.settings.set_boolean('hide-systray', builder.get_object("checkbutton_hide_systray").get_active())
        self.settings.set_boolean('default-repo-is-ok', builder.get_object("checkbutton_default_repo_is_ok").get_active())
        self.settings.set_boolean('level1-is-visible', builder.get_object("visible1").get_active())
        self.settings.set_boolean('level2-is-visible', builder.get_object("visible2").get_active())
        self.settings.set_boolean('level3-is-visible', builder.get_object("visible3").get_active())
        self.settings.set_boolean('level4-is-visible', builder.get_object("visible4").get_active())
        self.settings.set_boolean('level5-is-visible', builder.get_object("visible5").get_active())
        self.settings.set_boolean('level1-is-safe', builder.get_object("safe1").get_active())
        self.settings.set_boolean('level2-is-safe', builder.get_object("safe2").get_active())
        self.settings.set_boolean('level3-is-safe', builder.get_object("safe3").get_active())
        self.settings.set_boolean('level4-is-safe', builder.get_object("safe4").get_active())
        self.settings.set_boolean('level5-is-safe', builder.get_object("safe5").get_active())
        self.settings.set_boolean('security-updates-are-visible', builder.get_object("checkbutton_security_visible").get_active())
        self.settings.set_boolean('security-updates-are-safe', builder.get_object("checkbutton_security_safe").get_active())
        self.settings.set_int('refresh-days', int(builder.get_object("refresh_days").get_value()))
        self.settings.set_int('refresh-hours', int(builder.get_object("refresh_hours").get_value()))
        self.settings.set_int('refresh-minutes', int(builder.get_object("refresh_minutes").get_value()))
        self.settings.set_int('autorefresh-days', int(builder.get_object("autorefresh_days").get_value()))
        self.settings.set_int('autorefresh-hours', int(builder.get_object("autorefresh_hours").get_value()))
        self.settings.set_int('autorefresh-minutes', int(builder.get_object("autorefresh_minutes").get_value()))
        self.settings.set_boolean('dist-upgrade', builder.get_object("checkbutton_dist_upgrade").get_active())
        blacklist = []
        treeview_blacklist = builder.get_object("treeview_blacklist")
        model = treeview_blacklist.get_model()
        iter = model.get_iter_first()
        while iter is not None:
            pkg = model.get_value(iter, UPDATE_CHECKED)
            iter = model.iter_next(iter)
            blacklist.append(pkg)
        self.settings.set_strv("blacklisted-packages", blacklist)
        builder.get_object("main_window").hide()
        self.refresh()

    def add_blacklisted_package(self, widget, treeview_blacklist):
        dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK, None)
        dialog.set_markup("<b>" + _("Please specify the name of the update to ignore:") + "</b>")
        dialog.set_title(_("Ignore an update"))
        dialog.set_icon_name("mintupdate")
        entry = Gtk.Entry()
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label(_("Name:")), False, 5, 5)
        hbox.pack_end(entry, True, True, 0)
        dialog.vbox.pack_end(hbox, True, True, 0)
        dialog.show_all()
        dialog.run()
        name = entry.get_text()
        dialog.destroy()
        pkg = name.strip()
        if pkg != '':
            model = treeview_blacklist.get_model()
            iter = model.insert_before(None, None)
            model.set_value(iter, 0, pkg)

    def remove_blacklisted_package(self, widget, treeview_blacklist):
        selection = treeview_blacklist.get_selection()
        (model, iter) = selection.get_selected()
        if (iter != None):
            pkg = model.get_value(iter, UPDATE_CHECKED)
            model.remove(iter)

###### KERNEL FEATURES #####################################

    def install_kernel(self, widget, selection, builder, window):
        (model, iter) = selection.get_selected()
        if (iter != None):
            (status, version, pkg_version, installed, used, recommended, installable) = model.get_value(iter, 7)
            installed = (installed == "1")
            used = (used == "1")
            installable = (installable == "1")
            if (installed):
                message = _("Are you sure you want to remove the %s kernel?") % version
            else:
                message = _("Are you sure you want to install the %s kernel?") % version
            image = Gtk.Image()
            image.set_from_file("/usr/lib/linuxmint/mintUpdate/icons/warning.png")
            d = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.YES_NO, message)
            image.show()
            d.set_image(image)
            d.set_default_response(Gtk.ResponseType.NO)
            r = d.run()
            d.hide()
            d.destroy()
            if r == Gtk.ResponseType.YES:
                thread = InstallKernelThread(version, self, builder, installed)
                thread.start()
                window.hide()

    def open_kernels(self, widget):
        gladefile = "/usr/share/linuxmint/mintupdate/kernels.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        window = builder.get_object("window5")
        window.set_title(_("Linux kernels") + " - " + _("Update Manager"))
        window.set_icon_name("mintupdate")
        builder.get_object("close_button").connect("clicked", self.hide_window, window)

        builder.get_object("title_warning").set_markup("<span foreground='black' font_weight='bold' size='large'>%s</span>" % _("Warning!"))
        builder.get_object("label_warning").set_markup(_("The Linux kernel is a critical part of the system. Regressions can lead to lack of networking, lack of sound, lack of graphical environment or even the inability to boot the computer. Only install or remove kernels if you're experienced with kernels, drivers, dkms and you know how to recover a non-booting computer."))
        builder.get_object("label_available").set_markup("%s" % _("The following kernels are available:"))
        builder.get_object("label_more_info").set_text(_("More info..."))
        builder.get_object("label_more_info_1").set_markup("<small>%s</small>" % _("Fixes can represent bug fixes, improvements in hardware support or security fixes."))
        builder.get_object("label_more_info_2").set_markup("<small>%s</small>" % _("Security fixes are important when local users represent a potential threat (in companies, libraries, schools or public places for instance) or when the computer can be threatened by remote attacks (servers for instance)."))
        builder.get_object("label_more_info_3").set_markup("<small>%s</small>" % _("Bug fixes and hardware improvements are important if one of your devices isn't working as expected and the newer kernel addresses that problem."))
        builder.get_object("label_more_info_4").set_markup("<small>%s</small>" % _("Regressions represent something which worked well and no longer works after an update. It is common in software development that a code change or even a bug fix introduces side effects and breaks something else. Because of regressions it is recommended to be selective when installing updates or newer kernels."))
        builder.get_object("label_known_fixes").set_text(_("Fixes"))
        builder.get_object("label_known_regressions").set_text(_("Regressions"))
        builder.get_object("label_contact").set_markup("<span foreground='#3c3c3c' font_weight='bold' size='small'>%s</span>" % _("Note: Only known fixes and regressions are mentioned. If you are aware of additional fixes or regressions, please contact the development team."))

        (COL_VERSION, COL_LABEL, COL_PIC_LOADED, COL_PIC_RECOMMENDED, COL_PIC_INSTALLED, COL_PIC_FIXES, COL_PIC_REGRESSIONS, COL_VALUES, COL_LOADED, COL_RECOMMENDED, COL_INSTALLED, COL_FIXES, COL_REGRESSIONS) = range(13)
        model = Gtk.TreeStore(str, str, GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf, object, bool, bool, bool, bool, bool)

        # the treeview
        treeview_kernels = builder.get_object("treeview_kernels")
        column1 = Gtk.TreeViewColumn(_("Version"), Gtk.CellRendererText(), markup=COL_LABEL)
        column1.set_sort_column_id(COL_LABEL)
        column1.set_resizable(True)
        column1.set_expand(True)
        column2 = Gtk.TreeViewColumn(_("Loaded"), Gtk.CellRendererPixbuf(), pixbuf=COL_PIC_LOADED)
        column2.set_sort_column_id(COL_LOADED)
        column2.set_resizable(True)
        column2.set_expand(False)
        column3 = Gtk.TreeViewColumn(_("Recommended"), Gtk.CellRendererPixbuf(), pixbuf=COL_PIC_RECOMMENDED)
        column3.set_sort_column_id(COL_RECOMMENDED)
        column3.set_resizable(True)
        column3.set_expand(False)
        column4 = Gtk.TreeViewColumn(_("Installed"), Gtk.CellRendererPixbuf(), pixbuf=COL_PIC_INSTALLED)
        column4.set_sort_column_id(COL_INSTALLED)
        column4.set_resizable(True)
        column4.set_expand(False)
        column5 = Gtk.TreeViewColumn(_("Fixes"), Gtk.CellRendererPixbuf(), pixbuf=COL_PIC_FIXES)
        column5.set_sort_column_id(COL_FIXES)
        column5.set_resizable(True)
        column5.set_expand(False)
        column6 = Gtk.TreeViewColumn(_("Regressions"), Gtk.CellRendererPixbuf(), pixbuf=COL_PIC_REGRESSIONS)
        column6.set_sort_column_id(COL_REGRESSIONS)
        column6.set_resizable(True)
        column6.set_expand(False)

        treeview_kernels.append_column(column1)
        treeview_kernels.append_column(column2)
        treeview_kernels.append_column(column3)
        treeview_kernels.append_column(column4)
        treeview_kernels.append_column(column5)
        treeview_kernels.append_column(column6)

        treeview_kernels.set_headers_clickable(True)
        treeview_kernels.set_reorderable(False)
        treeview_kernels.set_search_column(1)
        treeview_kernels.set_enable_search(True)
        treeview_kernels.show()

        kernels = subprocess.check_output("/usr/lib/linuxmint/mintUpdate/checkKernels.py | grep \"###\"", shell = True).decode("utf-8")
        kernels = kernels.split("\n")
        for kernel in kernels:
            values = kernel.split("###")
            if len(values) == 7:
                status = values[0]
                if status != "KERNEL":
                    continue
                (status, version, pkg_version, installed, used, recommended, installable) = values
                installed = (installed == "1")
                used = (used == "1")
                recommended = (recommended == "1")
                installable = (installable == "1")
                label = version

                tick = GdkPixbuf.Pixbuf.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/tick.png")
                pix_fixes = GdkPixbuf.Pixbuf.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/fixes.png")
                pix_bugs = GdkPixbuf.Pixbuf.new_from_file("/usr/lib/linuxmint/mintUpdate/icons/regressions.png")

                iter = model.insert_before(None, None)

                fixes = False
                regressions = False
                if os.path.exists(os.path.join(KERNEL_INFO_DIR, version)):
                    kernel_file = open(os.path.join(KERNEL_INFO_DIR, version))
                    lines = kernel_file.readlines()
                    num_fixes = 0
                    num_bugs = 0
                    for line in lines:
                        elements = line.split("---")
                        if len(elements) == 4:
                            (prefix, title, url, description) = elements
                            if prefix == "fix":
                                num_fixes += 1
                            elif prefix == "bug":
                                num_bugs += 1
                    if num_fixes > 0:
                        fixes = True
                        model.set_value(iter, COL_PIC_FIXES, pix_fixes)
                    if num_bugs > 0:
                        regressions = True
                        model.set_value(iter, COL_PIC_REGRESSIONS, pix_bugs)

                if os.path.exists(os.path.join(KERNEL_INFO_DIR, "versions")):
                    kernel_file = open(os.path.join(KERNEL_INFO_DIR, "versions"))
                    lines = kernel_file.readlines()
                    for line in lines:
                        elements = line.split("\t")
                        if len(elements) == 3:
                            (versions_version, versions_tag, versions_upstream) = elements
                            if version in versions_version:
                                label = "%s (%s)" % (version, versions_upstream.strip())

                if installable and not installed:
                    button = Gtk.Button(_("Install"))
                    button.connect("clicked", self.install_kernel, version, window, builder, False)

                elif installed and not used:
                    button = Gtk.Button(_("Remove"))
                    button.connect("clicked", self.install_kernel, version, window, builder, True)

                if used:
                    model.set_value(iter, COL_PIC_LOADED, tick)
                    label = "<b>%s</b>" % label
                if recommended:
                    model.set_value(iter, COL_PIC_RECOMMENDED, tick)
                if installed:
                    model.set_value(iter, COL_PIC_INSTALLED, tick)

                model.set_value(iter, COL_VERSION, version)
                model.set_value(iter, COL_LABEL, label)
                model.set_value(iter, COL_VALUES, values)
                # Use "not", these are used to sort and we want to see positives when clicking the columns
                model.set_value(iter, COL_LOADED, not used)
                model.set_value(iter, COL_RECOMMENDED, not recommended)
                model.set_value(iter, COL_INSTALLED, not installed)
                model.set_value(iter, COL_FIXES, not fixes)
                model.set_value(iter, COL_REGRESSIONS, not regressions)

                model.row_changed(model.get_path(iter), iter)

        treeview_kernels.set_model(model)
        del model

        selection = treeview_kernels.get_selection()
        selection.connect("changed", self.display_selected_kernel, builder)

        button_install = builder.get_object("button_install")
        button_install.connect('clicked', self.install_kernel, selection, builder, window)

        window.show_all()

    def label_size_allocate(self, widget, rect):
        widget.set_size_request(rect.width, -1)

    def display_selected_kernel(self, selection, builder):
        button_install = builder.get_object("button_install")
        button_install.set_sensitive(False)
        button_install.set_tooltip_text("")
        try:
            scrolled_fixes = builder.get_object("scrolled_fixes")
            scrolled_regressions = builder.get_object("scrolled_regressions")
            for child in scrolled_fixes.get_children():
                scrolled_fixes.remove(child)
            for child in scrolled_regressions.get_children():
                scrolled_regressions.remove(child)
            (model, iter) = selection.get_selected()
            if (iter != None):
                (status, version, pkg_version, installed, used, recommended, installable) = model.get_value(iter, 7)
                installed = (installed == "1")
                used = (used == "1")
                installable = (installable == "1")
                if installed:
                    button_install.set_label(_("Remove the %s kernel") % version)
                    if used:
                        button_install.set_tooltip_text(_("This kernel cannot be removed because it is currently in use."))
                    else:
                        button_install.set_sensitive(True)
                else:
                    button_install.set_label(_("Install the %s kernel") % version)
                    if not installable:
                        button_install.set_tooltip_text(_("This kernel is not installable."))
                    else:
                        button_install.set_sensitive(True)
                if os.path.exists(os.path.join(KERNEL_INFO_DIR, version)):
                    kernel_file = open(os.path.join(KERNEL_INFO_DIR, version))
                    lines = kernel_file.readlines()
                    fixes_box = Gtk.Table()
                    fixes_box.set_row_spacings(3)
                    bugs_box = Gtk.Table()
                    bugs_box.set_row_spacings(3)
                    num_fixes = 0
                    num_bugs = 0
                    for line in lines:
                        elements = line.split("---")
                        if len(elements) == 4:
                            (prefix, title, url, description) = elements
                            link = Gtk.Label()
                            link.set_markup("<a href='%s'>%s</a>" % (url.strip(), title.strip()))
                            link.set_alignment(0, 0.5);
                            description_label = Gtk.Label()
                            description = description.strip()
                            description = re.sub(r'CVE-(\d+)-(\d+)', r'<a href="http://cve.mitre.org/cgi-bin/cvename.cgi?name=\g<0>">\g<0></a>', description)
                            description_label.set_markup("%s" % description.strip())
                            description_label.set_alignment(0, 0.5);
                            if prefix == "fix":
                                fixes_box.attach(link, 0, 1, num_fixes, num_fixes+1, xoptions=Gtk.AttachOptions.FILL, yoptions=Gtk.AttachOptions.FILL, xpadding=3, ypadding=0)
                                fixes_box.attach(description_label, 1, 2, num_fixes, num_fixes+1, xoptions=Gtk.AttachOptions.FILL, yoptions=Gtk.AttachOptions.FILL, xpadding=0, ypadding=0)
                                num_fixes += 1
                            elif prefix == "bug":
                                bugs_box.attach(link, 0, 1, num_bugs, num_bugs+1, xoptions=Gtk.AttachOptions.FILL, yoptions=Gtk.AttachOptions.FILL, xpadding=3, ypadding=0)
                                bugs_box.attach(description_label, 1, 2, num_bugs, num_bugs+1, xoptions=Gtk.AttachOptions.FILL, yoptions=Gtk.AttachOptions.FILL, xpadding=0, ypadding=0)
                                num_bugs += 1
                    scrolled_fixes.add_with_viewport(fixes_box)
                    scrolled_regressions.add_with_viewport(bugs_box)
                    fixes_box.show_all()
                    bugs_box.show_all()
        except Exception as e:
            print(e)
            print(sys.exc_info()[0])


if __name__ == "__main__":
    MintUpdate()
