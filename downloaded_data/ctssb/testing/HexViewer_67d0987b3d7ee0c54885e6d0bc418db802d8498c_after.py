"""
Hex Viewer.

Licensed under MIT
Copyright (c) 2011-2015 Isaac Muse <isaacmuse@gmail.com>
"""

import sublime
import sublime_plugin
import HexViewer.hex_common as common
from time import time, sleep
import threading
import re

HIGHLIGHT_SCOPE = "string"
HIGHLIGHT_ICON = "dot"
HIGHLIGHT_STYLE = "solid"
MS_HIGHLIGHT_DELAY = 500
MAX_HIGHIGHT = 1000
THROTTLING = False

hh_highlight = None

if 'hh_thread' not in globals():
    hh_thread = None


class HexHighlighter(object):
    """Hex highlighter."""

    def init(self):
        """Initialize."""

        init_status = False
        self.address_done = False
        self.total_bytes = 0
        self.address = []
        self.selected_bytes = []
        self.hex_lower = common.use_hex_lowercase()

        # Get Seetings from settings file
        group_size = self.view.settings().get("hex_viewer_bits", None)
        self.inspector_enabled = common.hv_settings("inspector", False)
        self.throttle = common.hv_settings("highlight_throttle", THROTTLING)
        self.max_highlight = common.hv_settings("highlight_max_bytes", MAX_HIGHIGHT)
        self.bytes_wide = self.view.settings().get("hex_viewer_actual_bytes", None)
        self.highlight_scope = common.hv_settings("highlight_scope", HIGHLIGHT_SCOPE)
        self.highlight_icon = common.hv_settings("highlight_icon", HIGHLIGHT_ICON)
        self.enable_fake_hex = common.hv_settings("enable_fake_hex_file", True)
        style = common.hv_settings("highlight_style", HIGHLIGHT_STYLE)

        if (group_size is None or self.bytes_wide is None) and self.enable_fake_hex:
            m = re.match(r'([\da-z]{8}):[\s]{2}((?:[\da-z]+[\s]{1})*)\s*\:[\w\W]*', self.view.substr(self.view.line(0)))
            if m is not None:
                starting_address = int(m.group(1), 16)
                hex_chars = m.group(2).split(' ')
                group_size = (len(hex_chars[0]) / 2) * 8
                self.bytes_wide = (len(hex_chars[0]) / 2) * (len(hex_chars) - 1)
                self.view.settings().set("hex_viewer_bits", group_size)
                self.view.settings().set("hex_viewer_actual_bytes", self.bytes_wide)
                self.view.settings().set("hex_viewer_fake", True)
                self.view.settings().set("hex_viewer_starting_address", starting_address)
                self.view.set_read_only(True)
                self.view.set_scratch(True)
                if common.hv_settings("inspector", False) and common.hv_settings("inspector_auto_show", False):
                    self.view.window().run_command("hex_show_inspector")

        # No icon?
        if self.highlight_icon == "none":
            self.highlight_icon = ""

        # Process highlight style
        self.highlight_style = 0
        if style == "outline":
            self.highlight_style = sublime.DRAW_OUTLINED
        elif style == "none":
            self.highlight_style = sublime.HIDDEN
        elif style == "underline":
            self.highlight_style = sublime.DRAW_EMPTY_AS_OVERWRITE

        # Process hex grouping
        if group_size is not None and self.bytes_wide is not None:
            self.group_size = group_size / common.BITS_PER_BYTE
            self.hex_char_range = common.get_hex_char_range(self.group_size, self.bytes_wide)
            init_status = True
        return init_status

    def get_address(self, start, num_bytes, line):
        """Get the address."""

        address_offset = self.view.settings().get('hex_viewer_starting_address', 0)
        lines = line
        align_to_address_offset = 2
        add_start = lines * self.bytes_wide + start - align_to_address_offset + address_offset
        add_end = add_start + num_bytes - 1
        length = len(self.address)
        if length == 0:
            # Add first address group
            multi_byte = -1 if add_start == add_end else add_end
            self.address.append(add_start)
            self.address.append(multi_byte)
        elif (
            (self.address[1] == -1 and self.address[0] + 1 == add_start) or
            (self.address[1] != -1 and self.address[1] + 1 == add_start)
        ):
            # Update end address
            self.address[1] = add_end
        else:
            # Stop getting adresses if bytes are not consecutive
            self.address_done = True

    def display_address(self):
        """Display the address."""

        address_string = "0x%08x" if self.hex_lower else "0x%08X"
        count = ''
        if self.total_bytes == 0 or len(self.address) != 2:
            self.view.set_status('hex_address', "Address: None")
            return
        # Display number of bytes whose address is not displayed
        if self.address_done:
            delta = 1 if self.address[1] == -1 else self.address[1] - self.address[0] + 1
            if self.total_bytes == "?":
                count = " [+?]"
            else:
                counted_bytes = self.total_bytes - delta
                if counted_bytes > 0:
                    count = " [+" + str(counted_bytes) + " bytes]"
        # Display adresses
        status = "Address: "
        if self.address[1] == -1:
            status += (address_string % self.address[0]) + count
        else:
            status += (address_string % self.address[0]) + "-" + (address_string % self.address[1]) + count
        self.view.set_status('hex_address', status)

    def display_total_bytes(self):
        """Display total hex bytes."""

        total = self.total_bytes if self.total_bytes == "?" else str(self.total_bytes)
        self.view.set_status('hex_total_bytes', "Total Bytes: " + total)

    def hex_selection(self, start, num_bytes, first_pos):
        """Get hex selection."""

        row, column = self.view.rowcol(first_pos)
        column = common.ascii_to_hex_col(start, self.group_size)
        hex_pos = self.view.text_point(row, column)

        # Log first byte
        if self.first_all == -1:
            self.first_all = hex_pos

        # Traverse row finding the specified bytes
        highlight_start = -1
        byte_count = num_bytes
        while byte_count:
            # Byte rising edge
            if self.view.score_selector(hex_pos, 'raw.nibble.upper'):
                if highlight_start == -1:
                    highlight_start = hex_pos
                hex_pos += 2
                byte_count -= 1
                # End of selection
                if byte_count == 0:
                    self.selected_bytes.append(sublime.Region(highlight_start, hex_pos))
            else:
                # Byte group falling edge
                self.selected_bytes.append(sublime.Region(highlight_start, hex_pos))
                hex_pos += 1
                highlight_start = -1
        # Log address
        if num_bytes and not self.address_done:
            self.get_address(start + 2, num_bytes, row)

    def ascii_to_hex(self, sel):
        """Convert ASCII to hex."""

        view = self.view
        start = sel.begin()
        end = sel.end()
        num_bytes = 0
        ascii_range = view.extract_scope(sel.begin())

        # Determine if selection is within ascii range
        if (
            start >= ascii_range.begin() and
            (
                # Single selection should ignore the end of line selection
                (end == start and end < ascii_range.end() - 1) or
                (end != start and end < ascii_range.end())
            )
        ):
            # Single char selection
            if sel.size() == 0:
                num_bytes = 1
                self.selected_bytes.append(sublime.Region(start, end + 1))
            else:
                # Multi char selection
                num_bytes = end - start
                self.selected_bytes.append(sublime.Region(start, end))
            self.total_bytes += num_bytes
            # Highlight hex values
            self.hex_selection(start - ascii_range.begin(), num_bytes, start)

    def hex_to_ascii(self, sel):
        """Convert hex to ASCII."""

        view = self.view
        start = sel.begin()
        end = sel.end()

        # Get range of hex data
        line = view.line(start)
        range_start = line.begin() + common.ADDRESS_OFFSET
        range_end = range_start + self.hex_char_range
        hex_range = sublime.Region(range_start, range_end)

        # Determine if selection is within hex range
        if start >= hex_range.begin() and end <= hex_range.end():
            # Adjust beginning of selection to begining of first selected byte
            start, end, num_bytes = common.adjust_hex_sel(view, start, end, self.group_size)

            # Highlight hex values and their ascii chars
            if num_bytes != 0:
                self.total_bytes += num_bytes
                # Zero based byte number
                start_byte = common.get_byte_count(hex_range.begin(), start + 2, self.group_size) - 1
                self.hex_selection(start_byte, num_bytes, start)

                # Highlight Ascii
                ascii_start = hex_range.end() + common.ASCII_OFFSET + start_byte
                ascii_end = ascii_start + num_bytes
                self.selected_bytes.append(sublime.Region(ascii_start, ascii_end))

    def get_highlights(self):
        """Get the highlights."""

        self.first_all = -1
        for sel in self.view.sel():
            # Kick out if total bytes exceeds limit
            if self.throttle and self.total_bytes >= self.max_highlight:
                if len(self.address) == 2:
                    self.address[1] = -1
                self.total_bytes = "?"
                return

            if self.view.score_selector(sel.begin(), 'comment'):
                self.ascii_to_hex(sel)
            else:
                self.hex_to_ascii(sel)

    def run(self, window):
        """Run command."""

        if window is None:
            return
        self.window = window
        view = self.window.active_view()
        self.view = view

        if not self.init():
            return

        self.get_highlights()

        # Show inspector panel
        if self.inspector_enabled:
            reset = False if self.total_bytes == 1 else True
            self.window.run_command(
                'hex_inspector',
                {'first_byte': self.first_all, 'reset': reset, 'bytes_wide': self.bytes_wide}
            )

        # Highlight selected regions
        if self.highlight_style == sublime.DRAW_EMPTY_AS_OVERWRITE:
            self.selected_bytes = common.underline(self.selected_bytes)
        view.add_regions(
            "hex_view",
            self.selected_bytes,
            self.highlight_scope,
            self.highlight_icon,
            self.highlight_style
        )
        # Display selected byte addresses and total bytes selected
        self.display_address()
        self.display_total_bytes()


class HexHighlighterCommand(sublime_plugin.WindowCommand):
    """Hex highlighter command."""

    def run(self):
        """Run the command."""

        if hh_thread.ignore_all:
            return
        hh_thread.modified = True

    def is_enabled(self):
        """Check if command is enabled."""

        return common.is_enabled()


class HexHighlighterListenerCommand(sublime_plugin.EventListener):
    """Hex highlighter event listener command."""

    def on_selection_modified(self, view):
        """Determine if a highlight should be triggered."""

        if hh_thread is None or not common.is_enabled(view) or hh_thread.ignore_all:
            return
        now = time()
        if now - hh_thread.time > hh_thread.wait_time:
            sublime.set_timeout(hh_thread.payload, 0)
        else:
            hh_thread.modified = True
            hh_thread.time = now


class HhThread(threading.Thread):
    """Load up defaults."""

    def __init__(self):
        """Setup the thread."""

        self.reset()
        threading.Thread.__init__(self)

    def reset(self):
        """Reset the thread variables."""

        self.wait_time = 0.12
        self.time = time()
        self.modified = False
        self.ignore_all = False
        self.abort = False

    def payload(self):
        """Code to run."""

        self.modified = False
        # Ignore selection and edit events inside the routine
        self.ignore_all = True
        hh_highlight(sublime.active_window())
        self.ignore_all = False
        self.time = time()

    def kill(self):
        """Kill thread."""

        self.abort = True
        while self.is_alive():
            pass
        self.reset()

    def run(self):
        """Thread loop."""

        while not self.abort:
            if self.modified is True and time() - self.time > self.wait_time:
                sublime.set_timeout(self.payload, 0)
            sleep(0.5)


def plugin_loaded():
    """Setup plugin."""

    global hh_highlight
    global hh_thread
    hh_highlight = HexHighlighter().run

    if 'hh_thread' in globals() and hh_thread is not None:
        hh_thread.kill()
    hh_thread = HhThread()
    hh_thread.start()


def plugin_unloaded():
    """Tear down plugin."""

    hh_thread.kill()
