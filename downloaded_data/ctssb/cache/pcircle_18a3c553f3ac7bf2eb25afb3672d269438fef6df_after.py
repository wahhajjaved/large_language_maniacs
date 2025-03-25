from __future__ import print_function
import sys
import time
import itertools
import logging
import re
import os.path
import traceback
import datetime
import argparse

from pcircle.globals import G
from pcircle.fdef import FileItem

__author__ = 'Feiyi Wang'


def numeric_level(loglevel):
    level = getattr(logging, loglevel.upper(), None)
    if not isinstance(level, int):
        raise ValueError("Invalid log level: %s" % loglevel)
    return level


def getLogger(name):
    logger = logging.getLogger(name)
    fmt = '%(asctime)s - %(levelname)s - %(rank)s:%(filename)s:%(lineno)d - %(message)s'
    level = numeric_level(G.loglevel)
    logger.setLevel(level)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(fmt))
    logger.addHandler(ch)
    return logger



def current_time():
    ts = time.time()
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def destpath(fitem, dest):
    """
    return the destination file path
    """
    full_dest_path = None

    if G.copytype == "dir2dir":
        # We use original source path as the relative start
        rpath = os.path.relpath(fitem.path, start=G.src[0].path)
        if rpath == ".":
            full_dest_path = dest
        else:
            full_dest_path = dest + "/" + rpath

    elif G.copytype == "file2file":
        full_dest_path = dest
    elif G.copytype == "file2dir":
        if fitem.dirname:
            rpath = os.path.relpath(fitem.path, start=fitem.dirname)
        else:
            rpath = os.path.basename(fitem.path)

        full_dest_path = dest + "/" + rpath

    else:
        raise ValueError("Can't handle copy type: %s" % G.copytype)

    return full_dest_path

def conv_unit(s):
    """ convert a unit to number """
    d = {"B": 1,
         "K": 1024,
         "M": 1024 * 1024,
         "G": 1024 * 1024 * 1024,
         "T": 1024 * 1024 * 1024 * 1024}
    s = s.upper()
    match = re.match(r"(\d+)(\w+)", s, re.I)
    if match:
        items = match.groups()
        v = int(items[0])
        u = items[1]
        return v * d[u]

    raise ValueError("Can't convert %s" % s)


def conv_time(s):
    """ Convert seconds into readable format"""
    one_min = 60
    one_hr = 60 * 60
    one_day = 24 * 60 * 60

    try:
        s = float(s)
    except:
        raise ValueError("Can't convert %s" % s)

    if s < one_min:
        return "%.2fs" % s
    elif s < one_hr:
        mins = int(s) / 60
        secs = int(s % 60)
        return "%sm %ss" % (mins, secs)
    elif s < one_day:
        s = int(s)
        hours = s / one_hr
        mins = (s % one_hr) / 60
        # secs = int(s - (hours * 60 * 60) - (mins * 60))
        return "%sh %sm" % (hours, mins)
    else:
        s = int(s)
        days = s / one_day
        hours = (s % one_day) / one_hr
        mins = ((s % one_day) % one_hr) / one_min
        return "%sd %sh %sm" % (days, hours, mins)


def bytes_fmt(n):
    d = {'1mb': 1048576,
         '1gb': 1073741824,
         '1tb': 1099511627776}
    if n < d['1mb']:
        return "%.2f KiB" % (float(n) / 1024)

    if n < d['1gb']:
        return "%.2f MiB" % (float(n) / d['1mb'])

    if n < d['1tb']:
        return "%.2f GiB" % (float(n) / d['1gb'])

    return "%.2f TiB" % (float(n) / d['1tb'])


def bins_strs(binlist):
    """ each numeric value in the binlist are converted to a string representation
    """
    res = []
    for b in binlist:
        x = bytes_fmt(b).split()
        res.append("Bin_" + "_".join(x))

    last = bytes_fmt(binlist[-1]).split()
    res.append("Bin>" + "_".join(last))
    return res

def spiner():
    # SO: http://stackoverflow.com/questions/13520622/python-script-to-show-progress
    for c in itertools.cycle('|/-\\'):
        sys.stdout.write('\r' + c)
        sys.stdout.flush()
        time.sleep(0.2)


def progress():
    # SO: http://stackoverflow.com/questions/3002085/python-to-print-out-status-bar-and-percentage

    total = 10000000
    point = total / 100
    increment = total / 20
    for i in xrange(total):
        if (i % (5 * point) == 0):
            sys.stdout.write(
                "\r[" + "=" * (i / increment) + " " * ((total - i) / increment) + "]" + str(i / point) + "%")
            sys.stdout.flush()


class bcolors:
    """
    Black       0;30     Dark Gray     1;30
    Blue        0;34     Light Blue    1;34
    Green       0;32     Light Green   1;32
    Cyan        0;36     Light Cyan    1;36
    Red         0;31     Light Red     1;31
    Purple      0;35     Light Purple  1;35
    Brown       0;33     Yellow        1;33
    Light Gray  0;37     White         1;37
    """

    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    INFO = '\033[1;33m'  # yellow
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''


def hprint(msg):
    print(bcolors.INFO + msg + bcolors.ENDC)


def eprint(msg):
    print(bcolors.FAIL + msg + bcolors.ENDC)


def timestamp():
    import time
    return time.strftime("%Y.%m.%d.%H%M%S")


def timestamp2():
    import time
    return time.strftime("%Y-%m-%d-%H%M%S")


def breakline(line, size=60, minsz=10):
    ret = ''
    total = len(line)
    if total <= size:
        return line

    while total > size:
        ret += line[0:size]
        ret += ' \ \n    '
        total -= size
        line = line[size:]

    if total < minsz:
        return ret[:-8] + line[:]
    else:
        return ret + line[:]


def breakline2(linearr, size=60, minsz=10):
    ret = ''
    curline = ''
    for item in linearr[:-1]:
        curline += ' ' + item
        if len(curline) > size:
            ret = ret + curline + "\ \n"
            curline = ''

    if len(linearr[-1]) < minsz:
        return " ".join([ret, linearr[-1]])
    else:
        return " ".join([ret, "\ \n", linearr[-1]])


def emsg(ep):
    """  Exception string: filename, line no, error type, error message """

    top = traceback.extract_stack()[-2]
    return ', '.join([os.path.basename(top[0]), 'Line ' + str(top[1]),
                      type(ep).__name__ + ': ' + str(ep)])


def calc_chunksize(totalsz):

    chunksize = 0
    MB = 1024 * 1024
    TB = 1024 * 1024 * 1024 * 1024
    if totalsz < 10 * TB:
        chunksize = 16 * MB
    elif totalsz < 100 * TB:
        chunksize = 64 * MB
    elif totalsz < 512 * TB:
        chunksize = 128 * MB
    elif totalsz < 1024 * TB:
        chunksize = 256 * MB
    else:
        chunksize = 512 * MB

    return chunksize


def check_src(infiles, mode=os.R_OK):
    """ check validity of infiles iterable, throw ValueException
    """
    ret = []
    for ele in infiles:
        # set up "dirname" for FileItem, so later we know how to construct
        # destination path when in "file2dir" mode
        elepath = os.path.realpath(os.path.expanduser(ele))
        elefi = FileItem(elepath)
        elefi.dirname = os.path.dirname(elepath)

        if os.path.exists(elepath) and os.access(elepath, mode):
            ret.append(elefi)
        else:
            raise ValueError(ele)

    return ret


def check_src2(infiles, mode=os.R_OK):
    """ check validity of infiles iterable, throw ValueException
    """
    ret = []
    for ele in infiles:
        # set up "dirname" for FileItem, so later we know how to construct
        # destination path when in "file2dir" mode
        elepath = os.path.realpath(os.path.expanduser(ele))

        if os.path.exists(elepath) and os.access(elepath, mode):
            ret.append(elepath)
        else:
            raise ValueError(ele)

    return ret


def choplist(alist, num=2):
    """ alist: a list of FileItem(s)
    chop and return a string for proper display
    """
    if len(alist) > num:
        chop = alist[:num]
    else:
        chop = alist

    buf =  ", ".join([fi.path for fi in alist])

    if len(alist) > num:
        buf += " ..."

    return buf

