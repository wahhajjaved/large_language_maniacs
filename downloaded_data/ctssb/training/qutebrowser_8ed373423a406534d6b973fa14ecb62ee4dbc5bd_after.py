# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""The main tabbed browser widget."""

import os
import logging
import subprocess
from tempfile import mkstemp
from functools import partial

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QObject, QProcess, QPoint
from PyQt5.QtGui import QClipboard
from PyQt5.QtPrintSupport import QPrintDialog, QPrintPreviewDialog

import qutebrowser.commands.utils as cmdutils
import qutebrowser.config.config as config
import qutebrowser.browser.hints as hints
import qutebrowser.utils.url as urlutils
import qutebrowser.utils.message as message
import qutebrowser.utils.webelem as webelem
from qutebrowser.utils.misc import check_overflow
from qutebrowser.utils.misc import shell_escape
from qutebrowser.commands.exceptions import CommandError


class CommandDispatcher(QObject):

    """Command dispatcher for TabbedBrowser.

    Contains all commands which are related to the current tab.

    We can't simply add these commands to BrowserTab directly and use
    currentWidget() for TabbedBrowser.cmd because at the time
    cmdutils.register() decorators are run, currentWidget() will return None.

    Attributes:
        _tabs: The TabbedBrowser object.
    """

    def __init__(self, parent):
        """Constructor.

        Args:
            parent: The TabbedBrowser for this dispatcher.
        """
        super().__init__(parent)
        self._tabs = parent

    def _scroll_percent(self, perc=None, count=None, orientation=None):
        """Inner logic for scroll_percent_(x|y).

        Args:
            perc: How many percent to scroll, or None
            count: How many percent to scroll, or None
            orientation: Qt.Horizontal or Qt.Vertical
        """
        if perc is None and count is None:
            perc = 100
        elif perc is None:
            perc = int(count)
        else:
            perc = float(perc)
        perc = check_overflow(perc, 'int', fatal=False)
        frame = self._tabs.currentWidget().page_.currentFrame()
        if orientation == Qt.Horizontal:
            right = frame.contentsSize().width()
            viewsize = frame.geometry().width()
            x = (right - viewsize) * perc / 100
            y = frame.scrollPosition().y()
        elif orientation == Qt.Vertical:
            bottom = frame.contentsSize().height()
            viewsize = frame.geometry().height()
            x = frame.scrollPosition().x()
            y = (bottom - viewsize) * perc / 100
        else:
            raise ValueError("Invalid orientation {}".format(orientation))
        frame.setScrollPosition(QPoint(x, y))

    def _prevnext(self, prev, newtab):
        """Inner logic for {tab,}{prev,next}page."""
        widget = self._tabs.currentWidget()
        frame = widget.page_.currentFrame()
        if frame is None:
            raise CommandError("No frame focused!")
        widget.hintmanager.follow_prevnext(frame, widget.url(), prev, newtab)

    def _tab_move_absolute(self, idx):
        """Get an index for moving a tab absolutely.

        Args:
            idx: The index to get, as passed as count.
        """
        if idx is None:
            return 0
        elif idx == 0:
            return self._tabs.count() - 1
        else:
            return idx - 1

    def _tab_move_relative(self, direction, delta):
        """Get an index for moving a tab relatively.

        Args:
            direction: + or - for relative moving, None for absolute.
            delta: Delta to the current tab.
        """
        if delta is None:
            raise ValueError
        if direction == '-':
            return self._tabs.currentIndex() - delta
        elif direction == '+':
            return self._tabs.currentIndex() + delta

    def _editor_cleanup(self, oshandle, filename):
        """Clean up temporary file when the editor was closed."""
        os.close(oshandle)
        try:
            os.remove(filename)
        except PermissionError:
            raise CommandError("Failed to delete tempfile...")

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_close(self, count=None):
        """Close the current/[count]th tab.

        Args:
            count: The tab index to close, or None

        Emit:
            quit: If last tab was closed and last-close in config is set to
                  quit.
        """
        tab = self._tabs.cntwidget(count)
        if tab is None:
            return
        self._tabs.close_tab(tab)

    @cmdutils.register(instance='mainwindow.tabs.cmd', name='open',
                       split=False)
    def openurl(self, url, count=None):
        """Open a URL in the current/[count]th tab.

        Args:
            url: The URL to open.
            count: The tab index to open the URL in, or None.
        """
        tab = self._tabs.cntwidget(count)
        if tab is None:
            if count is None:
                # We want to open a URL in the current tab, but none exists
                # yet.
                self._tabs.tabopen(url)
            else:
                # Explicit count with a tab that doesn't exist.
                return
        else:
            tab.openurl(url)

    @cmdutils.register(instance='mainwindow.tabs.cmd', name='reload')
    def reloadpage(self, count=None):
        """Reload the current/[count]th tab.

        Args:
            count: The tab index to reload, or None.
        """
        tab = self._tabs.cntwidget(count)
        if tab is not None:
            tab.reload()

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def stop(self, count=None):
        """Stop loading in the current/[count]th tab.

        Args:
            count: The tab index to stop, or None.
        """
        tab = self._tabs.cntwidget(count)
        if tab is not None:
            tab.stop()

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def print_preview(self, count=None):
        """Preview printing of the current/[count]th tab.

        Args:
            count: The tab index to print, or None.
        """
        tab = self._tabs.cntwidget(count)
        if tab is not None:
            preview = QPrintPreviewDialog()
            preview.paintRequested.connect(tab.print)
            preview.exec_()

    @cmdutils.register(instance='mainwindow.tabs.cmd', name='print')
    def printpage(self, count=None):
        """Print the current/[count]th tab.

        Args:
            count: The tab index to print, or None.
        """
        # QTBUG: We only get blank pages.
        # https://bugreports.qt-project.org/browse/QTBUG-19571
        # If this isn't fixed in Qt 5.3, bug should be reopened.
        tab = self._tabs.cntwidget(count)
        if tab is not None:
            printdiag = QPrintDialog()
            printdiag.open(lambda: tab.print(printdiag.printer()))

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def back(self, count=1):
        """Go back in the history of the current tab.

        Args:
            count: How many pages to go back.
        """
        for _ in range(count):
            self._tabs.currentWidget().go_back()

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def forward(self, count=1):
        """Go forward in the history of the current tab.

        Args:
            count: How many pages to go forward.
        """
        for _ in range(count):
            self._tabs.currentWidget().go_forward()

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def hint(self, groupstr='all', targetstr='normal'):
        """Start hinting.

        Args:
            groupstr: The hinting mode to use.
            targetstr: Where to open the links.
        """
        widget = self._tabs.currentWidget()
        frame = widget.page_.mainFrame()
        if frame is None:
            raise CommandError("No frame focused!")
        try:
            group = getattr(webelem.Group, groupstr.replace('-', '_'))
        except AttributeError:
            raise CommandError("Unknown hinting group {}!".format(groupstr))
        try:
            target = getattr(hints.Target, targetstr.replace('-', '_'))
        except AttributeError:
            raise CommandError("Unknown hinting target {}!".format(targetstr))
        widget.hintmanager.start(frame, widget.url(), group, target)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def follow_hint(self):
        """Follow the currently selected hint."""
        self._tabs.currentWidget().hintmanager.follow_hint()

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def prev_page(self):
        """Open a "previous" link."""
        self._prevnext(prev=True, newtab=False)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def next_page(self):
        """Open a "next" link."""
        self._prevnext(prev=False, newtab=False)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def prev_page_tab(self):
        """Open a "previous" link in a new tab."""
        self._prevnext(prev=True, newtab=True)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def next_page_tab(self):
        """Open a "next" link in a new tab."""
        self._prevnext(prev=False, newtab=True)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def scroll(self, dx, dy, count=1):
        """Scroll the current tab by count * dx/dy.

        Args:
            dx: How much to scroll in x-direction.
            dy: How much to scroll in x-direction.
            count: multiplier
        """
        dx = int(int(count) * float(dx))
        dy = int(int(count) * float(dy))
        cmdutils.check_overflow(dx, 'int')
        cmdutils.check_overflow(dy, 'int')
        self._tabs.currentWidget().page_.currentFrame().scroll(dx, dy)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def scroll_perc_x(self, perc=None, count=None):
        """Scroll the current tab to a specific percent of the page (horiz).

        Args:
            perc: Percentage to scroll.
            count: Percentage to scroll.
        """
        self._scroll_percent(perc, count, Qt.Horizontal)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def scroll_perc_y(self, perc=None, count=None):
        """Scroll the current tab to a specific percent of the page (vert).

        Args:
            perc: Percentage to scroll.
            count: Percentage to scroll.
        """
        self._scroll_percent(perc, count, Qt.Vertical)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def scroll_page(self, mx, my, count=1):
        """Scroll the frame page-wise.

        Args:
            mx: How many pages to scroll to the right.
            my: How many pages to scroll down.
            count: multiplier
        """
        frame = self._tabs.currentWidget().page_.currentFrame()
        size = frame.geometry()
        dx = int(count) * float(mx) * size.width()
        dy = int(count) * float(my) * size.height()
        cmdutils.check_overflow(dx, 'int')
        cmdutils.check_overflow(dy, 'int')
        frame.scroll(dx, dy)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def yank(self, sel=False):
        """Yank the current URL to the clipboard or primary selection.

        Args:
            sel: True to use primary selection, False to use clipboard
        """
        clip = QApplication.clipboard()
        url = urlutils.urlstring(self._tabs.currentWidget().url())
        mode = QClipboard.Selection if sel else QClipboard.Clipboard
        clip.setText(url, mode)
        message.info("URL yanked to {}".format("primary selection" if sel
                                               else "clipboard"))

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def yank_title(self, sel=False):
        """Yank the current title to the clipboard or primary selection.

        Args:
            sel: True to use primary selection, False to use clipboard
        """
        clip = QApplication.clipboard()
        title = self._tabs.tabText(self._tabs.currentIndex())
        mode = QClipboard.Selection if sel else QClipboard.Clipboard
        clip.setText(title, mode)
        message.info("Title yanked to {}".format("primary selection" if sel
                                                 else "clipboard"))

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def zoom_in(self, count=1):
        """Increase the zoom level for the current tab.

        Args:
            count: How many steps to take.
        """
        tab = self._tabs.currentWidget()
        tab.zoom(count)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def zoom_out(self, count=1):
        """Decrease the zoom level for the current tab.

        Args:
            count: How many steps to take.
        """
        tab = self._tabs.currentWidget()
        tab.zoom(-count)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def zoom(self, zoom=None, count=None):
        """Set the zoom level for the current tab to [count] or 100 percent.

        Args:
            count: How many steps to take.
        """
        try:
            level = cmdutils.arg_or_count(zoom, count, default=100)
        except ValueError as e:
            raise CommandError(e)
        tab = self._tabs.currentWidget()
        tab.zoom_perc(level)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_only(self):
        """Close all tabs except for the current one."""
        for tab in self._tabs.widgets:
            if tab is self._tabs.currentWidget():
                continue
            self._tabs.close_tab(tab)

    @cmdutils.register(instance='mainwindow.tabs.cmd', split=False)
    def open_tab(self, url):
        """Open a new tab with a given url."""
        self._tabs.tabopen(url, background=False)

    @cmdutils.register(instance='mainwindow.tabs.cmd', split=False)
    def open_tab_bg(self, url):
        """Open a new tab in background."""
        self._tabs.tabopen(url, background=True)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def open_tab_cur(self):
        """Set the statusbar to :tabopen and the current URL."""
        url = urlutils.urlstring(self._tabs.currentWidget().url())
        message.set_cmd_text(':open-tab ' + url)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def open_cur(self):
        """Set the statusbar to :open and the current URL."""
        url = urlutils.urlstring(self._tabs.currentWidget().url())
        message.set_cmd_text(':open ' + url)

    @cmdutils.register(instance='mainwindow.tabs.cmd', hide=True)
    def open_tab_bg_cur(self):
        """Set the statusbar to :tabopen-bg and the current URL."""
        url = urlutils.urlstring(self._tabs.currentWidget().url())
        message.set_cmd_text(':open-tab-bg ' + url)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def undo(self):
        """Re-open a closed tab (optionally skipping [count] tabs)."""
        if self._tabs.url_stack:
            self._tabs.tabopen(self._tabs.url_stack.pop())
        else:
            raise CommandError("Nothing to undo!")

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_prev(self, count=1):
        """Switch to the previous tab, or skip [count] tabs.

        Args:
            count: How many tabs to switch back.
        """
        newidx = self._tabs.currentIndex() - count
        if newidx >= 0:
            self._tabs.setCurrentIndex(newidx)
        elif config.get('tabbar', 'wrap'):
            self._tabs.setCurrentIndex(newidx % self._tabs.count())
        else:
            raise CommandError("First tab")

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_next(self, count=1):
        """Switch to the next tab, or skip [count] tabs.

        Args:
            count: How many tabs to switch forward.
        """
        newidx = self._tabs.currentIndex() + count
        if newidx < self._tabs.count():
            self._tabs.setCurrentIndex(newidx)
        elif config.get('tabbar', 'wrap'):
            self._tabs.setCurrentIndex(newidx % self._tabs.count())
        else:
            raise CommandError("Last tab")

    @cmdutils.register(instance='mainwindow.tabs.cmd', nargs=(0, 1))
    def paste(self, sel=False, tab=False):
        """Open a page from the clipboard.

        Args:
            sel: True to use primary selection, False to use clipboard
            tab: True to open in a new tab.
        """
        clip = QApplication.clipboard()
        mode = QClipboard.Selection if sel else QClipboard.Clipboard
        url = clip.text(mode)
        if not url:
            raise CommandError("Clipboard is empty.")
        logging.debug("Clipboard contained: '{}'".format(url))
        if tab:
            self._tabs.tabopen(url)
        else:
            self.openurl(url)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def paste_tab(self, sel=False):
        """Open a page from the clipboard in a new tab.

        Args:
            sel: True to use primary selection, False to use clipboard
        """
        self._tabs.paste(sel, True)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_focus(self, index=None, count=None):
        """Select the tab given as argument/[count].

        Args:
            index: The tab index to focus, starting with 1.
        """
        try:
            idx = cmdutils.arg_or_count(index, count, default=1,
                                        countzero=self._tabs.count())
        except ValueError as e:
            raise CommandError(e)
        cmdutils.check_overflow(idx + 1, 'int')
        if 1 <= idx <= self._tabs.count():
            self._tabs.setCurrentIndex(idx - 1)
        else:
            raise CommandError("There's no tab with index {}!".format(idx))

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_move(self, direction=None, count=None):
        """Move the current tab.

        Args:
            direction: + or - for relative moving, None for absolute.
            count: If moving absolutely: New position (or first).
                   If moving relatively: Offset.
        """
        if direction is None:
            new_idx = self._tab_move_absolute(count)
        elif direction in '+-':
            try:
                new_idx = self._tab_move_relative(direction, count)
            except ValueError:
                raise CommandError("Count must be given for relative moving!")
        else:
            raise CommandError("Invalid direction '{}'!".format(direction))
        if not 0 <= new_idx < self._tabs.count():
            raise CommandError("Can't move tab to position {}!".format(
                new_idx))
        tab = self._tabs.currentWidget()
        cur_idx = self._tabs.currentIndex()
        icon = self._tabs.tabIcon(cur_idx)
        label = self._tabs.tabText(cur_idx)
        cmdutils.check_overflow(cur_idx, 'int')
        cmdutils.check_overflow(new_idx, 'int')
        self._tabs.removeTab(cur_idx)
        self._tabs.insertTab(new_idx, tab, icon, label)
        self._tabs.setCurrentIndex(new_idx)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def tab_focus_last(self):
        """Select the tab which was last focused."""
        idx = self._tabs.indexOf(self._tabs.last_focused)
        if idx == -1:
            raise CommandError("Last focused tab vanished!")
        self._tabs.setCurrentIndex(idx)

    @cmdutils.register(instance='mainwindow.tabs.cmd', split=False)
    def spawn(self, cmd):
        """Spawn a command in a shell. {} gets replaced by the current URL.

        The URL will already be quoted correctly, so there's no need to do
        that.

        The command will be run in a shell, so you can use shell features like
        redirections.

        We use subprocess rather than Qt's QProcess here because of it's
        shell=True argument and because we really don't care about the process
        anymore as soon as it's spawned.

        Args:
            cmd: The command to execute.
        """
        url = urlutils.urlstring(self._tabs.currentWidget().url())
        cmd = cmd.replace('{}', shell_escape(url))
        logging.debug("Executing: {}".format(cmd))
        subprocess.Popen(cmd, shell=True)

    @cmdutils.register(instance='mainwindow.tabs.cmd')
    def home(self):
        """Open main startpage in current tab."""
        self.openurl(config.get('general', 'startpage')[0])

    @cmdutils.register(instance='mainwindow.tabs.cmd', modes=['insert'],
                       hide=True)
    def open_editor(self):
        """Open an external editor with the current form field.

        We use QProcess rather than subprocess here because it makes it a lot
        easier to execute some code as soon as the process has been finished
        and do everything async.
        """
        frame = self._tabs.currentWidget().page_.currentFrame()
        elem = frame.findFirstElement(webelem.SELECTORS[
            webelem.Group.editable_focused])
        if elem.isNull():
            raise CommandError("No editable element focused!")
        oshandle, filename = mkstemp(text=True)
        text = elem.evaluateJavaScript('this.value')
        if text:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text)
        proc = QProcess(self)
        proc.finished.connect(partial(self.on_editor_closed, elem, oshandle,
                                      filename))
        proc.error.connect(partial(self.on_editor_error, oshandle, filename))
        editor = config.get('general', 'editor')
        executable = editor[0]
        args = [arg.replace('{}', filename) for arg in editor[1:]]
        logging.debug("Calling '{}' with args {}".format(executable, args))
        proc.start(executable, args)

    def on_editor_closed(self, elem, oshandle, filename, exitcode,
                         exitstatus):
        """Write the editor text into the form field and clean up tempfile.

        Callback for QProcess when the editor was closed.
        """
        logging.debug("Editor closed")
        if exitcode != 0:
            raise CommandError("Editor did quit abnormally (status "
                               "{})!".format(exitcode))
        if exitstatus != QProcess.NormalExit:
            # No error here, since we already handle this in on_editor_error
            return
        if elem.isNull():
            raise CommandError("Element vanished while editing!")
        with open(filename, 'r', encoding='utf-8') as f:
            text = ''.join(f.readlines())
            text = webelem.javascript_escape(text)
        logging.debug("Read back: {}".format(text))
        elem.evaluateJavaScript("this.value='{}'".format(text))
        self._editor_cleanup(oshandle, filename)

    def on_editor_error(self, oshandle, filename, error):
        """Display an error message and clean up when editor crashed."""
        messages = {
            QProcess.FailedToStart: "The process failed to start.",
            QProcess.Crashed: "The process crashed.",
            QProcess.Timedout: "The last waitFor...() function timed out.",
            QProcess.WriteError: ("An error occurred when attempting to write "
                                  "to the process."),
            QProcess.ReadError: ("An error occurred when attempting to read "
                                 "from the process."),
            QProcess.UnknownError: "An unknown error occurred.",
        }
        self._editor_cleanup(oshandle, filename)
        raise CommandError("Error while calling editor: {}".format(
            messages[error]))
