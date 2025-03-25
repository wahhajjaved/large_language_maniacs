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

"""Manager for questions to be shown in the statusbar."""

import collections

from PyQt5.QtCore import pyqtSlot, QTimer
from PyQt5.QtWidgets import QLineEdit

from qutebrowser.keyinput import modeman
from qutebrowser.commands import cmdutils
from qutebrowser.utils import usertypes, log, qtutils, objreg, utils


PromptContext = collections.namedtuple('PromptContext',
                                       ['question', 'text', 'input_text',
                                        'echo_mode', 'input_visible'])


class Prompter:

    """Manager for questions to be shown in the statusbar.

    The way in which multiple questions are handled deserves some explanation.

    If a question is blocking, we *need* to ask it immediately, and can't wait
    for previous questions to finish. We could theoretically ask a blocking
    question inside of another blocking one, so in ask_question we simply save
    the current prompt state on the stack, let the user answer the *most
    recent* question, and then restore the previous state.

    With a non-blocking question, things are a bit easier. We simply add it to
    self._queue if we're still busy handling another question, since it can be
    answered at any time.

    In either case, as soon as we finished handling a question, we call
    _pop_later() which schedules a _pop to ask the next question in _queue. We
    schedule it rather than doing it immediately because then the order of how
    things happen is clear, e.g. on_mode_left can't happen after we already set
    up the *new* question.

    Attributes:
        _question: A Question object with the question to be asked to the user.
        _loops: A list of local EventLoops to spin in when blocking.
        _queue: A deque of waiting questions.
    """

    def __init__(self):
        self._question = None
        self._loops = []
        self._queue = collections.deque()
        self._busy = False

    def __repr__(self):
        return utils.get_repr(self, loops=len(self._loops),
                              question=self._question, queue=len(self._queue),
                              busy=self._busy)

    def _pop_later(self):
        """Helper to call self._pop as soon as everything else is done."""
        QTimer.singleShot(0, self._pop)

    def _pop(self):
        """Pop a question from the queue and ask it, if there are any."""
        log.statusbar.debug("Popping from queue {}".format(self._queue))
        if self._queue:
            self.ask_question(self._queue.popleft(), blocking=False)

    def _get_ctx(self):
        """Get a PromptContext based on the current state."""
        if not self._busy:
            return None
        prompt = objreg.get('prompt')
        ctx = PromptContext(question=self._question,
                            text=prompt.txt.text(),
                            input_text=prompt.lineedit.text(),
                            echo_mode=prompt.lineedit.echoMode(),
                            input_visible=prompt.lineedit.isVisible())
        return ctx

    def _restore_ctx(self, ctx):
        """Restore state from a PromptContext.

        Args:
            ctx: A PromptContext previously saved by _get_ctx, or None.

        Return: True if a context was restored, False otherwise.
        """
        log.statusbar.debug("Restoring context {}".format(ctx))
        prompt = objreg.get('prompt')
        if ctx is None:
            prompt.hide_prompt.emit()
            self._busy = False
            return False
        self._question = ctx.question
        prompt.txt.setText(ctx.text)
        prompt.lineedit.setText(ctx.input_text)
        prompt.lineedit.setEchoMode(ctx.echo_mode)
        prompt.lineedit.setVisible(ctx.input_visible)
        return True

    def _display_question(self):
        """Display the question saved in self._question.

        Return:
            The mode which should be entered.

        Raise:
            ValueError if the set PromptMode is invalid.
        """
        prompt = objreg.get('prompt')
        if self._question.mode == usertypes.PromptMode.yesno:
            if self._question.default is None:
                suffix = ""
            elif self._question.default:
                suffix = " (yes)"
            else:
                suffix = " (no)"
            prompt.txt.setText(self._question.text + suffix)
            prompt.lineedit.hide()
            mode = usertypes.KeyMode.yesno
        elif self._question.mode == usertypes.PromptMode.text:
            prompt.txt.setText(self._question.text)
            if self._question.default:
                prompt.lineedit.setText(self._question.default)
            prompt.lineedit.show()
            mode = usertypes.KeyMode.prompt
        elif self._question.mode == usertypes.PromptMode.user_pwd:
            prompt.txt.setText(self._question.text)
            if self._question.default:
                prompt.lineedit.setText(self._question.default)
            prompt.lineedit.show()
            mode = usertypes.KeyMode.prompt
        elif self._question.mode == usertypes.PromptMode.alert:
            prompt.txt.setText(self._question.text + ' (ok)')
            prompt.lineedit.hide()
            mode = usertypes.KeyMode.prompt
        else:
            raise ValueError("Invalid prompt mode!")
        prompt.lineedit.setFocus()
        prompt.show_prompt.emit()
        self._busy = True
        return mode

    def shutdown(self):
        """Cancel all blocking questions.

        Quits and removes all running eventloops.

        Return:
            True if loops needed to be aborted,
            False otherwise.
        """
        if self._loops:
            for loop in self._loops:
                loop.quit()
                loop.deleteLater()
            return True
        else:
            return False

    @pyqtSlot(usertypes.KeyMode)
    def on_mode_left(self, mode):
        """Clear and reset input when the mode was left."""
        prompt = objreg.get('prompt')
        if mode in (usertypes.KeyMode.prompt, usertypes.KeyMode.yesno):
            prompt.txt.setText('')
            prompt.lineedit.clear()
            prompt.lineedit.setEchoMode(QLineEdit.Normal)
            prompt.hide_prompt.emit()
            self._busy = False
            if self._question.answer is None and not self._question.is_aborted:
                self._question.cancel()

    @cmdutils.register(instance='prompter', hide=True,
                       modes=[usertypes.KeyMode.prompt,
                              usertypes.KeyMode.yesno])
    def prompt_accept(self):
        """Accept the current prompt.

        //

        This executes the next action depending on the question mode, e.g. asks
        for the password or leaves the mode.
        """
        prompt = objreg.get('prompt')
        if (self._question.mode == usertypes.PromptMode.user_pwd and
                self._question.user is None):
            # User just entered an username
            self._question.user = prompt.lineedit.text()
            prompt.txt.setText("Password:")
            prompt.lineedit.clear()
            prompt.lineedit.setEchoMode(QLineEdit.Password)
        elif self._question.mode == usertypes.PromptMode.user_pwd:
            # User just entered a password
            password = prompt.lineedit.text()
            self._question.answer = (self._question.user, password)
            modeman.leave(usertypes.KeyMode.prompt, 'prompt accept')
            self._question.done()
        elif self._question.mode == usertypes.PromptMode.text:
            # User just entered text.
            self._question.answer = prompt.lineedit.text()
            modeman.leave(usertypes.KeyMode.prompt, 'prompt accept')
            self._question.done()
        elif self._question.mode == usertypes.PromptMode.yesno:
            # User wants to accept the default of a yes/no question.
            self._question.answer = self._question.default
            modeman.leave(usertypes.KeyMode.yesno, 'yesno accept')
            self._question.done()
        elif self._question.mode == usertypes.PromptMode.alert:
            # User acknowledged an alert
            self._question.answer = None
            modeman.leave(usertypes.KeyMode.prompt, 'alert accept')
            self._question.done()
        else:
            raise ValueError("Invalid question mode!")

    @cmdutils.register(instance='prompter', hide=True,
                       modes=[usertypes.KeyMode.yesno])
    def prompt_yes(self):
        """Answer yes to a yes/no prompt."""
        if self._question.mode != usertypes.PromptMode.yesno:
            # We just ignore this if we don't have a yes/no question.
            return
        self._question.answer = True
        modeman.leave(usertypes.KeyMode.yesno, 'yesno accept')
        self._question.done()

    @cmdutils.register(instance='prompter', hide=True,
                       modes=[usertypes.KeyMode.yesno])
    def prompt_no(self):
        """Answer no to a yes/no prompt."""
        if self._question.mode != usertypes.PromptMode.yesno:
            # We just ignore this if we don't have a yes/no question.
            return
        self._question.answer = False
        modeman.leave(usertypes.KeyMode.yesno, 'prompt accept')
        self._question.done()

    @pyqtSlot(usertypes.Question, bool)
    def ask_question(self, question, blocking):
        """Dispkay a question in the statusbar.

        Args:
            question: The Question object to ask.
            blocking: If True, this function blocks and returns the result.

        Return:
            The answer of the user when blocking=True.
            None if blocking=False.
        """
        log.statusbar.debug("Asking question {}, blocking {}, loops {}, queue "
                            "{}".format(question, blocking, self._loops,
                                        self._queue))

        if self._busy and not blocking:
            # We got an async question, but we're already busy with one, so we
            # just queue it up for later.
            log.statusbar.debug("Adding {} to queue.".format(question))
            self._queue.append(question)
            return

        if blocking:
            # If we're blocking we save the old state on the stack, so we can
            # restore it after exec, if exec gets called multiple times.
            context = self._get_ctx()

        self._question = question
        mode = self._display_question()
        question.aborted.connect(lambda: modeman.maybe_leave(mode, 'aborted'))
        mode_manager = objreg.get('mode-manager')
        try:
            modeman.enter(mode, 'question asked')
        except modeman.ModeLockedError:
            if mode_manager.mode() != usertypes.KeyMode.prompt:
                question.abort()
                return None
        mode_manager.locked = True
        if blocking:
            loop = qtutils.EventLoop()
            self._loops.append(loop)
            loop.destroyed.connect(lambda: self._loops.remove(loop))
            question.completed.connect(loop.quit)
            question.completed.connect(loop.deleteLater)
            loop.exec_()
            if not self._restore_ctx(context):
                # Nothing left to restore, so we can go back to popping async
                # questions.
                if self._queue:
                    self._pop_later()
            return self._question.answer
        else:
            question.completed.connect(self._pop_later)
