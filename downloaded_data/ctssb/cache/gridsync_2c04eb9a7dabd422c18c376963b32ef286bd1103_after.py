# -*- coding: utf-8 -*-

import logging
import os
import subprocess
import sys
import webbrowser

from atomicwrites import atomic_write
from PyQt5.QtCore import QCoreApplication, QMetaType, QUrl, QVariant
from PyQt5.QtGui import QClipboard, QDesktopServices

if sys.platform == "win32":
    from win32com.client import Dispatch  # pylint: disable=import-error

from gridsync import resource, settings, APP_NAME, autostart_file_path


def _dbus_notify(title, message, duration=5000):
    from PyQt5.QtDBus import (
        QDBus,
        QDBusArgument,
        QDBusConnection,
        QDBusInterface,
    )

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise OSError("Could not connect to DBus")
    interface = QDBusInterface(
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
        bus,
    )
    error = interface.lastError()
    if error.type():
        raise RuntimeError("{}; {}".format(error.name(), error.message()))
    # See https://developer.gnome.org/notification-spec/
    # "This allows clients to effectively modify the notification while
    # it's active. A value of value of 0 means that this notification
    # won't replace any existing notifications."
    replaces_id = QVariant(0)
    replaces_id.convert(QVariant.UInt)
    interface.call(
        QDBus.NoBlock,
        "Notify",
        APP_NAME,
        replaces_id,
        resource(settings["application"]["tray_icon"]),
        title,
        message,
        QDBusArgument([], QMetaType.QStringList),
        {},
        duration,
    )


def notify(systray, title, message, duration=5000):
    logging.debug("Sending desktop notification...")
    if sys.platform.startswith("linux"):
        try:
            _dbus_notify(title, message, duration)
        except (OSError, RuntimeError) as err:
            logging.warning("%s; falling back to showMessage()...", str(err))
            systray.showMessage(title, message, msecs=duration)
    else:
        systray.showMessage(title, message, msecs=duration)


def _desktop_open(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def open_enclosing_folder(path):
    path = os.path.expanduser(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "--reveal", path])
    elif sys.platform == "win32":
        subprocess.Popen('explorer /select,"{}"'.format(path))
    else:
        # TODO: Get file-manager via `xdg-mime query default inode/directory`
        # and, if 'org.gnome.Nautilus.desktop', call `nautilus --select`?
        _desktop_open(os.path.dirname(path))


def open_path(path):
    path = os.path.expanduser(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)
    else:
        _desktop_open(path)


def get_clipboard_modes():
    clipboard = QCoreApplication.instance().clipboard()
    modes = [QClipboard.Clipboard]
    if clipboard.supportsSelection():
        modes.append(QClipboard.Selection)
    if clipboard.supportsFindBuffer():
        modes.append(QClipboard.FindBuffer)
    return modes


def get_clipboard_text(mode=QClipboard.Clipboard):
    return QCoreApplication.instance().clipboard().text(mode)


def set_clipboard_text(text, mode=QClipboard.Clipboard):
    QCoreApplication.instance().clipboard().setText(text, mode)
    logging.debug(
        "Copied %i bytes to clipboard %i", len(text) if text else 0, mode
    )


def _autostart_enable_linux(executable):
    with atomic_write(autostart_file_path, mode="w", overwrite=True) as f:
        f.write(
            """\
[Desktop Entry]
Name={0}
Comment={0}
Type=Application
Exec=env PATH={1} {2}
Terminal=false
""".format(
                APP_NAME, os.environ["PATH"], executable
            )
        )


# pylint: disable=line-too-long
def _autostart_enable_mac(executable):
    with atomic_write(autostart_file_path, mode="w", overwrite=True) as f:
        f.write(
            """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>{}</string>
    </dict>
    <key>Label</key>
    <string>{}</string>
    <key>Program</key>
    <string>{}</string>
    <key>RunAtLoad</key>
    <true/>
  </dict>
</plist>
""".format(
                os.environ["PATH"],
                settings["build"]["mac_bundle_identifier"],
                executable,
            )
        )


def _autostart_enable_windows(executable):
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(autostart_file_path)
    shortcut.Targetpath = executable
    shortcut.WorkingDirectory = os.path.dirname(executable)
    shortcut.save()


def autostart_enable():
    logging.debug("Writing autostart file to '%s'...", autostart_file_path)
    try:
        os.makedirs(os.path.dirname(autostart_file_path))
    except OSError:
        pass
    appimage_path = os.environ.get("APPIMAGE")
    frozen = getattr(sys, "frozen", False)
    if frozen and frozen == "macosx_app":  # py2app
        executable = os.path.join(
            os.path.dirname(os.path.realpath(sys.executable)), APP_NAME
        )
    elif appimage_path:
        executable = appimage_path
    elif frozen:
        executable = os.path.realpath(sys.executable)
    else:
        executable = os.path.realpath(sys.argv[0])
    if sys.platform == "win32":
        _autostart_enable_windows(executable)
    elif sys.platform == "darwin":
        _autostart_enable_mac(executable)
    else:
        _autostart_enable_linux(executable)
    logging.debug("Wrote autostart file to '%s'", autostart_file_path)


def autostart_is_enabled():
    return os.path.exists(autostart_file_path)


def autostart_disable():
    logging.debug("Deleting autostart file '%s'...", autostart_file_path)
    os.remove(autostart_file_path)
    logging.debug("Deleted autostart file '%s'", autostart_file_path)


def get_browser_name() -> str:
    try:
        name = webbrowser.get().name.replace("-", " ").title()
    except (AttributeError, webbrowser.Error):
        return "browser"
    if name.endswith("Default") or not name or name.lower() == "xdg open":
        return "browser"
    return name
