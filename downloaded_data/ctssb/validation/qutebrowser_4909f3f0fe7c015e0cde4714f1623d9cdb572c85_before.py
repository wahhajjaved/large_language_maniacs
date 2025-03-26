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

"""Loggers and utilities related to logging."""

import re
import os
import sys
import logging
from logging import getLogger
from collections import deque

from PyQt5.QtCore import (QtDebugMsg, QtWarningMsg, QtCriticalMsg, QtFatalMsg,
                          qInstallMessageHandler)
# Optional imports
try:
    # pylint: disable=import-error
    from colorlog import ColoredFormatter
except ImportError:
    ColoredFormatter = None
try:
    # pylint: disable=import-error
    import colorama
except ImportError:
    colorama = None

# Log formats to use.
SIMPLE_FMT = '{levelname}: {message}'
EXTENDED_FMT = ('{asctime:8} {levelname:8} {name:10} {module}:{funcName}:'
                '{lineno} {message}')
SIMPLE_FMT_COLORED = '%(log_color)s%(levelname)s%(reset)s: %(message)s'
EXTENDED_FMT_COLORED = ('%(green)s%(asctime)-8s%(reset)s %(log_color)'
                        's%(levelname)-8s%(reset)s %(yellow)s%(name)-10s '
                        '%(module)s:%(funcName)s:%(lineno)s%(reset)s '
                        '%(message)s')
DATEFMT = '%H:%M:%S'


# The different loggers used.

statusbar = getLogger('statusbar')
completion = getLogger('completion')
destroy = getLogger('destroy')
modes = getLogger('modes')
webview = getLogger('webview')
mouse = getLogger('mouse')
misc = getLogger('misc')
url = getLogger('url')
procs = getLogger('procs')
commands = getLogger('commands')
init = getLogger('init')
signals = getLogger('signals')
hints = getLogger('hints')
keyboard = getLogger('keyboard')
downloads = getLogger('downloads')
js = getLogger('js')
qt = getLogger('qt')
style = getLogger('style')
rfc6266 = getLogger('rfc6266')


ram_handler = None


def init_log(args):
    """Init loggers based on the argparse namespace passed."""
    level = 'DEBUG' if args.debug else args.loglevel.upper()
    try:
        numeric_level = getattr(logging, level)
    except AttributeError:
        raise ValueError("Invalid log level: {}".format(args.loglevel))

    console, ram = _init_handlers(numeric_level, args.color, args.loglines)
    root = getLogger()
    if console is not None:
        if args.logfilter is not None and numeric_level <= logging.DEBUG:
            console.addFilter(LogFilter(args.logfilter.split(',')))
            console.addFilter(LeplFilter())
        root.addHandler(console)
    if ram is not None:
        root.addHandler(ram)
        console.addFilter(LeplFilter())
    root.setLevel(logging.NOTSET)
    logging.captureWarnings(True)
    qInstallMessageHandler(qt_message_handler)


def fix_rfc2622():
    """Fix the rfc6266 logger.

    In rfc2622 <= v0.04, a NullHandler class is added as handler, instead of an
    object, which causes an exception later.

    This was fixed in [1], but since v0.05 is not out yet, we work around the
    issue by deleting the wrong handler.

    This should be executed after init_log is done and rfc6266 is imported, but
    before using it.

    [1]: https://github.com/g2p/rfc6266/commit/cad58963ed13f5e1068fcc9e4326123b6b2bdcf8
    """
    rfc6266.removeHandler(logging.NullHandler)


def _init_handlers(level, color, ram_capacity):
    """Init log handlers.

    Args:
        level: The numeric logging level.
        color: Whether to use color if available.
    """
    global ram_handler
    console_formatter, ram_formatter, use_colorama = _init_formatters(
        level, color)

    if sys.stderr is None:
        console_handler = None
    else:
        if use_colorama:
            stream = colorama.AnsiToWin32(sys.stderr)
        else:
            stream = sys.stderr
        console_handler = logging.StreamHandler(stream)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)

    if ram_capacity == 0:
        ram_handler = None
    else:
        ram_handler = RAMHandler(capacity=ram_capacity)
        ram_handler.setLevel(logging.NOTSET)
        ram_handler.setFormatter(ram_formatter)

    return console_handler, ram_handler


def _init_formatters(level, color):
    """Init log formatters.

    Args:
        level: The numeric logging level.
        color: Whether to use color if available.

    Return:
        A (console_formatter, ram_formatter, use_colorama) tuple.
        console_formatter/ram_formatter: logging.Formatter instances.
        use_colorama: Whether to use colorama.
    """
    if level <= logging.DEBUG:
        console_fmt = EXTENDED_FMT
        console_fmt_colored = EXTENDED_FMT_COLORED
    else:
        console_fmt = SIMPLE_FMT
        console_fmt_colored = SIMPLE_FMT_COLORED
    ram_formatter = logging.Formatter(EXTENDED_FMT, DATEFMT, '{')
    if sys.stderr is None:
        return None, ram_formatter, False
    use_colorama = False
    if (ColoredFormatter is not None and (os.name == 'posix' or colorama) and
            sys.stderr.isatty() and color):
        console_formatter = ColoredFormatter(
            console_fmt_colored, DATEFMT, log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red',
            }
        )
        if colorama:
            colorama.init()
            use_colorama = True
    else:
        console_formatter = logging.Formatter(console_fmt, DATEFMT, '{')
    return console_formatter, ram_formatter, use_colorama


def qt_message_handler(msg_type, context, msg):
    """Qt message handler to redirect qWarning etc. to the logging system.

    Args:
        QtMsgType msg_type: The level of the message.
        QMessageLogContext context: The source code location of the message.
        msg: The message text.
    """
    # Mapping from Qt logging levels to the matching logging module levels.
    # Note we map critical to ERROR as it's actually "just" an error, and fatal
    # to critical.
    qt_to_logging = {
        QtDebugMsg: logging.DEBUG,
        QtWarningMsg: logging.WARNING,
        QtCriticalMsg: logging.ERROR,
        QtFatalMsg: logging.CRITICAL,
    }
    # Change levels of some well-known messages to debug so they don't get
    # shown to the user.
    # suppressed_msgs is a list of regexes matching the message texts to hide.
    suppressed_msgs = ("libpng warning: iCCP: Not recognizing known sRGB "
                       "profile that has been edited",
                       "OpenType support missing for script [0-9]*")
    if any(re.match(pattern, msg.strip()) for pattern in suppressed_msgs):
        level = logging.DEBUG
    else:
        level = qt_to_logging[msg_type]
    # We get something like "void qt_png_warning(png_structp, png_const_charp)"
    # from Qt, but only want "qt_png_warning".
    match = re.match(r'.*( |::)(\w*)\(.*\)', context.function)
    if match is not None:
        func = match.group(2)
    else:
        func = context.function
    name = 'qt' if context.category == 'default' else 'qt-' + context.category
    if msg.splitlines()[0] == ('This application failed to start because it '
                               'could not find or load the Qt platform plugin '
                               '"xcb".'):
        # Handle this message specially.
        msg += ("\n\nOn Archlinux, this should fix the problem:\n"
                "    pacman -S libxkbcommon-x11")
        try:
            import faulthandler
        except ImportError:
            pass
        else:
            faulthandler.disable()
    record = qt.makeRecord(name, level, context.file, context.line, msg, None,
                           None, func)
    qt.handle(record)


class LogFilter(logging.Filter):

    """Filter to filter log records based on the commandline argument.

    The default Filter only supports one name to show - we support a
    comma-separated list instead.

    Attributes:
        names: A list of names that should be logged.
    """

    def __init__(self, names):
        super().__init__()
        self.names = names

    def filter(self, record):
        """Determine if the specified record is to be logged."""
        if self.names is None:
            return True
        if record.levelno > logging.DEBUG:
            # More important than DEBUG, so we won't filter at all
            return True
        for name in self.names:
            if record.name == name:
                return True
            elif not record.name.startswith(name):
                continue
            elif record.name[len(name)] == '.':
                return True
        return False


class LeplFilter(logging.Filter):

    """Filter to filter debug log records by the lepl library."""

    def filter(self, record):
        """Determine if the specified record is to be logged."""
        if (record.levelno == logging.INFO and
                record.name == 'lepl.lexer.rewriters.AddLexer'):
            # Special useless info message triggered by rfc6266
            return False
        if record.levelno > logging.DEBUG:
            # More important than DEBUG, so we won't filter at all
            return True
        return not record.name.startswith('lepl.')


class RAMHandler(logging.Handler):

    """Logging handler which keeps the messages in a deque in RAM.

    Loosly based on logging.BufferingHandler which is unsuitable because it
    uses a simple list rather than a deque.

    Attributes:
        data: A deque containing the logging records.
    """

    def __init__(self, capacity):
        super().__init__()
        if capacity != -1:
            self.data = deque(maxlen=capacity)
        else:
            self.data = deque()

    def emit(self, record):
        self.data.append(record)

    def dump_log(self):
        """Dump the complete formatted log data as as string."""
        lines = []
        for record in self.data:
            lines.append(self.format(record))
        return '\n'.join(lines)
