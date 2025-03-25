# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

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

"""Debugging console."""

import sys
import code

from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QApplication

from qutebrowser.config import config
from qutebrowser.models import cmdhistory
from qutebrowser.utils import utils
from qutebrowser.widgets import misc


class ConsoleLineEdit(misc.CommandLineEdit):

    """A QLineEdit which executes entered code and provides a history.

    Attributes:
        _history: The command history of executed commands.
        _more: A flag which is set when more input is expected.
        _buffer: The buffer for multiline commands.
        _interpreter: The InteractiveInterpreter to execute code with.
    """

    write = pyqtSignal(str)

    def __init__(self, parent):
        if not hasattr(sys, 'ps1'):
            sys.ps1 = '>>> '
        if not hasattr(sys, 'ps2'):
            sys.ps2 = '... '
        super().__init__(parent)
        self.set_prompt(sys.ps1)
        self.update_font()
        config.on_change(self.update_font, 'fonts', 'debug-console')
        self._more = False
        self._buffer = []
        interpreter_locals = {
            '__name__': '__console__',
            '__doc__': None,
            'qApp': QApplication.instance(),
            # We use parent as self here because the user "feels" the whole
            # console, not just the line edit.
            'self': parent,
        }
        self._interpreter = code.InteractiveInterpreter(interpreter_locals)
        self._history = cmdhistory.History()
        self.returnPressed.connect(self.execute)
        self.setText('')

    def _curprompt(self):
        """Get the prompt which is visible currently."""
        return sys.ps2 if self._more else sys.ps1

    @pyqtSlot(str)
    def execute(self):
        """Execute the line of code which was entered."""
        self._history.stop()
        text = self.text()
        if text:
            self._history.append(text)
        self.push(text)
        self.setText('')

    def push(self, line):
        """Push a line to the interpreter."""
        self._buffer.append(line)
        source = '\n'.join(self._buffer)
        self.write.emit(self._curprompt() + line + '\n')
        # We do two special things with the contextmanagers here:
        #   - We replace stdout/stderr to capture output. Even if we could
        #     override InteractiveInterpreter's write method, most things are
        #     printed elsewhere (e.g. by exec). Other Python GUI shells do the
        #     same.
        #   - We disable our exception hook, so exceptions from the console get
        #     printed and don't ooen a crashdialog.
        with utils.fake_io(self.write.emit), utils.disabled_excepthook():
            self._more = self._interpreter.runsource(source, '<console>')
        self.set_prompt(self._curprompt())
        if not self._more:
            self._buffer = []

    def history_prev(self):
        """Go back in the history."""
        try:
            if not self._history.is_browsing():
                item = self._history.start(self.text().strip())
            else:
                item = self._history.previtem()
        except (cmdhistory.HistoryEmptyError,
                cmdhistory.HistoryEndReachedError):
            return
        self.setText(item)

    def history_next(self):
        """Go forward in the history."""
        if not self._history.is_browsing():
            return
        try:
            item = self._history.nextitem()
        except cmdhistory.HistoryEndReachedError:
            return
        self.setText(item)

    def setText(self, text):
        """Override setText to always prepend the prompt."""
        super().setText(self._curprompt() + text)

    def text(self):
        """Override text to strip the prompt."""
        text = super().text()
        return text[len(self._curprompt()):]

    def keyPressEvent(self, e):
        """Override keyPressEvent to handle special keypresses."""
        if e.key() == Qt.Key_Up:
            self.history_prev()
            e.accept()
        elif e.key() == Qt.Key_Down:
            self.history_next()
            e.accept()
        elif e.modifiers() & Qt.ControlModifier and e.key() == Qt.Key_C:
            self.setText('')
            e.accept()
        else:
            super().keyPressEvent(e)

    def update_font(self):
        """Set the correct font."""
        self.setFont(config.get('fonts', 'debug-console'))


class ConsoleTextEdit(QTextEdit):

    """Custom QTextEdit for console output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setReadOnly(True)
        config.on_change(self.update_font, 'fonts', 'debug-console')
        self.update_font()
        self.setFocusPolicy(Qt.ClickFocus)

    def __repr__(self):
        return utils.get_repr(self)

    def update_font(self):
        """Update font when config changed."""
        self.setFont(config.get('fonts', 'debug-console'))


class ConsoleWidget(QWidget):

    """A widget with an interactive Python console.

    Attributes:
        _lineedit: The line edit in the console.
        _output: The output widget in the console.
        _vbox: The layout which contains everything.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lineedit = ConsoleLineEdit(self)
        self._output = ConsoleTextEdit()
        self._lineedit.write.connect(self.insert_text)
        self._vbox = QVBoxLayout()
        self._vbox.setSpacing(0)
        self._vbox.addWidget(self._output)
        self._vbox.addWidget(self._lineedit)
        self.setLayout(self._vbox)
        self._lineedit.setFocus()

    def __repr__(self):
        return utils.get_repr(self, visible=self.isVisible())

    def insert_text(self, text):
        """Insert new text and scroll output to bottom."""
        self._output.insertPlainText(text)
        scrollbar = self._output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
