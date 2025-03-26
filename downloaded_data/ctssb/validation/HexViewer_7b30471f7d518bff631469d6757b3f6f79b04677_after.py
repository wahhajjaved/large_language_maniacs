"""
Hex Viewer
Licensed under MIT
Copyright (c) 2011 Isaac Muse <isaacmuse@gmail.com>
"""

import sublime
import sublime_plugin
import struct
import threading
from os.path import basename, exists
from os.path import getsize as get_file_size
from os import remove
from HexViewer.hex_common import *
from fnmatch import fnmatch
import tempfile
import subprocess
from HexViewer.hex_notify import notify, error

DEFAULT_BIT_GROUP = 16
DEFAULT_BYTES_WIDE = 24
DEFAULT_MAX_FILE_SIZE = 50000.0
VALID_BITS = [8, 16, 32, 64, 128]
VALID_BYTES = [8, 10, 16, 24, 32, 48, 64, 128, 256, 512]
AUTO_OPEN = False

active_thread = None


class ReadBin(threading.Thread):
    def __init__(self, file_name, bytes_wide, group_size):
        self.bytes_wide = int(bytes_wide)
        self.group_size = int(group_size)
        self.file_name = file_name
        self.file_size = get_file_size(file_name)
        self.read_count = 0
        self.abort = False
        threading.Thread.__init__(self)

    def iterfile(self, maxblocksize=4096):
        with open(self.file_name, "rb") as bin:
            # Ensure read block is a multiple of groupsize
            bytes_wide = self.bytes_wide
            blocksize = maxblocksize - (maxblocksize % bytes_wide)

            start = 0
            bytearray = bin.read(blocksize)
            while bytearray:
                outbytes = bytearray[start:start + bytes_wide]
                while outbytes:
                    yield outbytes
                    start += bytes_wide
                    outbytes = bytearray[start:start + bytes_wide]
                start = 0
                bytearray = bin.read(blocksize)

    def run(self):
        translate_table = str.maketrans("".join([chr(c) for c in range(0, 256)]), "".join(["."] * 32 + [chr(c) for c in range(32, 127)] + ["."] * 129))
        def_struct = struct.Struct("=" + ("B" * self.bytes_wide))
        def_template = (("%02x" * self.group_size) + " ") * int(self.bytes_wide / self.group_size)

        line = 0
        read_count = 0
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".hex") as f:
            self.hex_name = f.name
            for bytearray in self.iterfile():
                if self.abort:
                    return
                l_buffer = []

                read_count += self.bytes_wide
                self.read_count = read_count if read_count < self.file_size else self.file_size

                # Add line number
                l_buffer.append("%08x:  " % (line * self.bytes_wide))

                try:
                    # Complete line
                    # Convert to decimal value
                    values = def_struct.unpack(bytearray)

                    # Add hex value
                    l_buffer.append(def_template % values)
                except struct.error:
                    # Incomplete line
                    # Convert to decimal value
                    values = struct.unpack("=" + ("B" * len(bytearray)), bytearray)

                    # Add hex value
                    remain_group = int(len(bytearray) / self.group_size)
                    remain_extra = len(bytearray) % self.group_size
                    l_buffer.append(((("%02x" * self.group_size) + " ") * (remain_group) + ("%02x" * remain_extra)) % values)

                    # Append printable chars to incomplete line
                    delta = self.bytes_wide - len(bytearray)
                    group_space = int(delta / self.group_size)
                    extra_space = (1 if delta % self.group_size else 0)

                    l_buffer.append(" " * (group_space + extra_space + delta * 2))

                # Append printable chars
                l_buffer.append(" :" + "".join([chr(translate_table[b]) for b in bytearray]))

                # Add line to buffer
                f.write(("\n" if line > 0 else "") + "".join(l_buffer))

                line += 1


class HexViewerListenerCommand(sublime_plugin.EventListener):
    open_me = None

    def is_bin_file(self, file_path, encoding):
        match = False
        if not hv_settings("disable_auto_open_hex_encoding", False) and encoding == "Hexadecimal":
            match = True
        else:
            patterns = hv_settings("auto_open_patterns", [])
            for pattern in patterns:
                match |= fnmatch(file_path, pattern)
                if match:
                    break
        return match

    def open_bin_file(self, view=None, window=None):
        open_now = False
        if view is not None and window is not None:
            # Direct open file
            open_now = True
        else:
            # Preview view of file
            window = sublime.active_window()
            if window is not None:
                view = window.active_view()
        # Open bin file in hex viewer
        if window and view and (open_now or view.file_name() == self.open_me):
            is_preview = window and view.file_name() not in [file.file_name() for file in window.views()]
            if is_preview:
                return
            view.settings().set("hex_no_auto_open", True)
            window.run_command('hex_viewer')

    def auto_load(self, view, window, is_preview):
        file_name = view.file_name()
        if file_name is not None and not exists(file_name):
            file_name = None
        encoding = view.encoding()
        # Make sure we have a file name and that we haven't already processed the view
        if file_name is not None and not view.settings().get("hex_no_auto_open", False):
            # Make sure the file is specified in our binary file list
            if self.is_bin_file(file_name, encoding):
                # Handle previw or direct open
                if is_preview:
                    self.open_me = file_name
                    sublime.set_timeout(lambda: self.open_bin_file(), 100)
                else:
                    self.open_me = file_name
                    self.open_bin_file(view, window)

    def on_activated(self, view):
        # Logic for preview windows
        if hv_settings("auto_open", AUTO_OPEN) and not view.settings().get('is_widget'):
            window = view.window()
            is_preview = window and view.file_name() not in [file.file_name() for file in window.views()]
            if view.settings().get("hex_view_postpone_hexview", True) and not view.is_loading():
                self.auto_load(view, window, is_preview)

    def on_load(self, view):
        # Logic for direct open files
        if hv_settings("auto_open", AUTO_OPEN) and not view.settings().get('is_widget'):
            window = view.window()
            is_preview = window and view.file_name() not in [file.file_name() for file in window.views()]
            if window and not is_preview and view.settings().get("hex_view_postpone_hexview", True):
                self.auto_load(view, window, is_preview)

        temp_file = view.settings().get("hex_viewer_temp_file", None)
        if temp_file is not None:
            if exists(temp_file):
                remove(temp_file)

            view.set_name(basename(view.settings().get("hex_viewer_file_name")) + ".hex")

            view.sel().clear()
            # Offset past address to first byte
            view.sel().add(sublime.Region(ADDRESS_OFFSET, ADDRESS_OFFSET))
            if hv_settings("inspector", False) and hv_settings("inspector_auto_show", False):
                window = view.window()
                if window is not None:
                    view.window().run_command("hex_show_inspector")

    def on_pre_save(self, view):
        # We are saving the file so it will now reference itself
        # Instead of the original binary file, so reset settings.
        # Hex output will no longer be able to toggle back
        # To original file, so open original file along side
        # Newly saved hex output
        if view.settings().has("hex_viewer_file_name"):
            view.window().open_file(view.settings().get("hex_viewer_file_name"))
            view.set_scratch(False)
            view.set_read_only(False)
            view.settings().erase("hex_viewer_bits")
            view.settings().erase("hex_viewer_bytes")
            view.settings().erase("hex_viewer_actual_bytes")
            view.settings().erase("hex_viewer_file_name")


class HexViewerCommand(sublime_plugin.WindowCommand):
    handshake = -1
    file_name = ""
    thread = None

    def set_format(self):
        self.group_size = DEFAULT_BIT_GROUP / BITS_PER_BYTE
        self.bytes_wide = DEFAULT_BYTES_WIDE

        # Set grouping
        if self.bits in VALID_BITS:
            self.group_size = self.bits / BITS_PER_BYTE

        # Set bytes per line
        if self.bytes in hv_settings("valid_bytes_per_line", VALID_BYTES):
            self.bytes_wide = self.bytes

        # Check if grouping and bytes per line do not align
        # Round to nearest bytes
        offset = self.bytes_wide % self.group_size
        if offset == self.bytes_wide:
            self.bytes_wide = self.bits / BITS_PER_BYTE
        elif offset != 0:
            self.bytes_wide -= offset

    def buffer_init(self, bits, bytearray):
        self.view = self.window.active_view()
        file_name = None
        if self.view is not None:
            # Get font settings
            self.font = hv_settings('custom_font', 'None')
            self.font_size = hv_settings('custom_font_size', 0)

            # Get file name
            file_name = self.view.settings().get("hex_viewer_file_name", self.view.file_name())

            # Get current bit and byte settings from view
            # Or try and get them from settings file
            # If none are found, use default
            current_bits = self.view.settings().get(
                'hex_viewer_bits',
                hv_settings('group_bytes_by_bits', DEFAULT_BIT_GROUP)
            )
            current_bytes = self.view.settings().get(
                'hex_viewer_bytes',
                hv_settings('bytes_per_line', DEFAULT_BYTES_WIDE)
            )
            # Use passed in bit and byte settings if available
            self.bits = bits if bits is not None else int(current_bits)
            self.bytes = bytearray if bytearray is not None else int(current_bytes)
            self.set_format()
        return file_name

    def read_bin(self, file_name):
        global active_thread
        self.abort = False
        self.current_view = self.view
        self.thread = ReadBin(file_name, self.bytes_wide, self.group_size)
        file_size = float(self.thread.file_size) * 0.001
        max_file_size = float(hv_settings("max_file_size_kb", DEFAULT_MAX_FILE_SIZE))
        if file_size > max_file_size:
            viewer = hv_settings("external_viewer", {}).get("viewer", "")
            if exists(viewer):
                self.view.run_command("hex_external_viewer")
            else:
                error("File size exceeded HexViewers configured max limit of %s KB" % str(max_file_size))
            self.reset_thread()
        else:
            self.thread.start()
            self.handle_thread()
            active_thread = self.thread

    def load_hex_view(self):
        file_name = self.thread.file_name
        hex_name = self.thread.hex_name
        abort = self.thread.abort
        self.thread = None

        if abort:
            notify("Conversion aborted!")
            if exists(hex_name):
                remove(hex_name)
            return

        # Show binary data
        view = self.window.open_file(hex_name)

        self.window.focus_view(self.view)
        if self.window.active_view().id() == self.view.id():
            self.window.run_command("close_file")
        self.window.focus_view(view)

        # Set font
        if self.font != 'none':
            view.settings().set('font_face', self.font)
        if self.font_size != 0:
            view.settings().set("font_size", self.font_size)

        # Save hex view settings
        view.settings().set("hex_viewer_bits", self.bits)
        view.settings().set("hex_viewer_bytes", self.bytes)
        view.settings().set("hex_viewer_actual_bytes", self.bytes_wide)
        view.settings().set("hex_viewer_file_name", file_name)
        view.settings().set("hex_no_auto_open", True)
        view.settings().set("hex_viewer_fake", False)
        view.settings().set("hex_viewer_temp_file", hex_name)
        # Show hex content in view; make read only
        view.set_scratch(True)
        view.set_read_only(True)

    def read_file(self, file_name):
        if hv_settings("inspector", False):
            self.window.run_command("hex_hide_inspector")
        view = self.window.open_file(file_name)
        view.settings().set("hex_no_auto_open", True)
        self.window.focus_view(self.view)
        self.window.run_command("close_file")
        self.window.focus_view(view)

    def reset_thread(self):
        self.thread = None

    def handle_thread(self):
        if self.abort is True:
            self.thread.abort = True
            notify("Hex View aborted!")
            sublime.set_timeout(lambda: self.reset_thread(), 500)
            return
        ratio = float(self.thread.read_count) / float(self.thread.file_size)
        percent = int(ratio * 10)
        leftover = 10 - percent
        message = "[" + "-" * percent + ">" + "-" * leftover + ("] %3d%%" % int(ratio * 100)) + " converted to hex"
        sublime.status_message(message)
        if not self.thread.is_alive():
            sublime.set_timeout(lambda: self.load_hex_view(), 100)
        else:
            sublime.set_timeout(lambda: self.handle_thread(), 100)

    def abort_hex_load(self):
        self.abort = True

    def discard_changes(self, value):
        if value.strip().lower() == "yes":
            if self.switch_type == "hex":
                view = sublime.active_window().active_view()
                if self.handshake == view.id():
                    view.set_scratch(True)
                    self.read_bin(self.file_name)
                else:
                    error("Target view is no longer in focus!  Hex view aborted.")
            else:
                self.read_file(self.file_name)
        self.reset()

    def discard_panel(self):
        self.window.show_input_panel(
            "Discard Changes? (yes | no):",
            "no",
            self.discard_changes,
            None,
            self.reset
        )

    def reset(self):
        self.handshake = -1
        self.file_name = ""
        self.type = None

    def is_enabled(self):
        view = self.window.active_view()
        return (
            view is not None and
            not view.settings().get("hex_viewer_fake", False) and
            not(active_thread is not None and active_thread.is_alive())
        )

    def run(self, bits=None, bytearray=None):
        global active_thread
        if active_thread is not None and active_thread.is_alive():
            error("HexViewer is already converting a file!\nPlease run the abort command to stop the current conversion.")
            return
        # If thread is active cancel thread
        if self.thread is not None and self.thread.is_alive():
            self.abort_hex_load()
            return

        # Init Buffer
        file_name = self.buffer_init(bits, bytearray)

        # Identify view
        if self.handshake != -1 and self.handshake == self.view.id():
            self.reset()
        self.handshake = self.view.id()

        if file_name is not None and exists(file_name):
            # Decide whether to read in as a binary file or a traditional file
            if self.view.settings().has("hex_viewer_file_name"):
                self.view_type = "hex"
                if is_hex_dirty(self.view):
                    self.file_name = file_name
                    if bits is None and bytearray is None:
                        self.switch_type = "file"
                    else:
                        self.switch_type = "hex"
                    self.discard_panel()
                else:
                    if bits is None and bytearray is None:
                        # Switch back to traditional output
                        self.read_file(file_name)
                    else:
                        # Reload hex with new settings
                        self.read_bin(file_name)
            else:
                # We are going to swap out the current file for hex output
                # So as not to clutter the screen.  Changes need to be saved
                # Or they will be lost
                if self.view.is_dirty():
                    self.file_name = file_name
                    self.switch_type = "hex"
                    self.discard_panel()
                else:
                    # Switch to hex output
                    self.read_bin(file_name)
        else:
            if file_name is None:
                error("View does not exist on disk!")
            else:
                error("%s does not exist on disk!" % basename(file_name))


class HexViewerOptionsCommand(sublime_plugin.WindowCommand):
    def set_bits(self, value):
        if value != -1:
            self.window.run_command('hex_viewer', {"bits": VALID_BITS[value]})

    def set_bytes(self, value):
        if value != -1:
            self.window.run_command('hex_viewer', {"bytearray": self.valid_bytes[value]})

    def is_enabled(self):
        view = self.window.active_view()
        return is_enabled() and view is not None and not view.settings().get("hex_viewer_fake", False)

    def run(self, option):
        self.view = self.window.active_view()
        file_name = self.view.settings().get("hex_viewer_file_name", self.view.file_name())
        self.valid_bytes = hv_settings("valid_bytes_per_line", VALID_BYTES)
        if file_name is not None:
            if self.view.settings().has("hex_viewer_file_name"):
                option_list = []
                if option == "bits":
                    for bits in VALID_BITS:
                        option_list.append(str(bits) + " bits")
                    self.window.show_quick_panel(option_list, self.set_bits)
                elif option == "bytes":
                    for bytearray in self.valid_bytes:
                        option_list.append(str(bytearray) + " bytes")
                    self.window.show_quick_panel(option_list, self.set_bytes)


class HexExternalViewerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        viewer = hv_settings("external_viewer", {}).get("viewer", "")
        if not exists(viewer):
            error("Can't find the external hex viewer!")
            return

        file_name = self.view.file_name()
        if file_name is not None and exists(file_name):
            cmd = [viewer] + hv_settings("external_viewer", {}).get("args", [])

            for x in range(0, len(cmd)):
                cmd[x] = cmd[x].replace("${FILE}", file_name)

            subprocess.Popen(cmd)

    def is_enabled(self):
        viewer = hv_settings("external_viewer", {}).get("viewer", "")
        return exists(viewer) and self.view.file_name() is not None


class HexViewerAbortCommand(sublime_plugin.WindowCommand):
    def run(self):
        global active_thread
        if active_thread is not None and active_thread.is_alive():
            active_thread.abort = True

    def is_enabled(self):
        global active_thread
        return active_thread is not None and active_thread.is_alive()
