#/usr/bin/python
import time
import os

def mfile(fname):
    print "    Image: %s" % os.path.split(fname)[1]

def mtimeT(t0, i, fname):
    print "       time: %5.2f  [%s T try %1i]" % (time.time() - t0, os.path.split(fname)[1],i)

def mfailimg(t0, fname):
    print "       time: %5.2f [%s fail]" % (tim.time() - t0, os.path.split(fname)[1])

def mdoneimg(t0, fname):
    print "       time: %5.2f [warp %s]" % (time.time() - t0, os.path.split(fname)[1])
