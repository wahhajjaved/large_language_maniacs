#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import inspect
import sys

from common import compat

colors = {
    'clear': '\033[0m',
    'black': '\033[30m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'purple': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m'
}

def timestamp():
    return datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

def putColor(strPrint, color=None):
    if color in colors:
        code = colors[color]
        sys.stderr.write("%s%s\033[m\n" % (code,strPrint))
    else:
        sys.stdout.write(strPrint+"\n")

def log(msg, color=None, quiet=False):
    if not quiet:
        strPrint = "[%s] %s" % (timestamp(), compat.toStr(msg))
        putColor(strPrint, color)

def debug(msg, color=None, quiet=False):
    if not quiet:
        s = inspect.stack()[1]
        frame    = s[0]
        filename = s[1]
        line     = s[2]
        name     = s[3]
        code     = s[4]
        if code:
            strPrint = "[%s:%s %s] %s: " % (filename, line, timestamp(), code[0].strip())
        else:
            strPrint = "[%s:%s %s] : " % (filename, line, timestamp())
        strPrint += repr(msg)
        putColor(strPrint, color)

def warn(msg, quiet=False):
    if not quiet:
        strPrint = "[Warning %s] %s" % (timestamp(), str(msg))
        if sys.stderr.isatty():
            putColor(strPrint, color='yellow')
        else:
            putColor(strPrint)

def alert(msg, quit=True, quiet=False):
    if not quiet:
        strPrint = "[Error %s] %s" % (timestamp(), str(msg))
        if sys.stderr.isatty():
            putColor(strPrint, 'red')
        else:
            putColor(strPrint)
    if quit:
        sys.exit(1)

