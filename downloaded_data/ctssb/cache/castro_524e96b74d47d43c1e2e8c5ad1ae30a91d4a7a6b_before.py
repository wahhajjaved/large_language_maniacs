import os
import tempfile
from sys import stdout 
from time import sleep

from multiprocessing import Process

import lib.messageboard as mb
from lib.pyvnc2swf import vnc2swf

# Get directory for storing files:
DATA_DIR = os.environ.get('CASTRO_DATA_DIR',
                          tempfile.gettempdir()) 

class Castro:
    def __init__(s, 
                 filename = "castro-video.swf",
                 host     = "localhost",
                 display  = 0,
                 framerate = '12',
                 clipping = None,
                 passwd   = os.path.join(os.path.expanduser("~"), ".vnc", "passwd")):
        s.filename = filename
        s.host = host
        s.display = display
        s.framerate = framerate
        s.clipping = clipping
        s.passwd = passwd
        s.init()

    def init(s):
        args=['lib/pyvnc2swf/vnc2swf.py', 
               '-n',
               '-o', os.path.join(DATA_DIR, s.filename),
               '%s:%s' % (s.host, s.display) ]

        # If password file is specified, insert it into args
        if s.passwd:
            args.insert(4, '-P')
            args.insert(5, s.passwd)

        # If framerate is specified, insert it into args
        if s.framerate:
            args.insert(4, '-r')
            args.insert(5, s.framerate)

        # If clipping is specified, insert it into args
        if s.clipping:
            args.insert(4, '-C')
            args.insert(5, s.clipping)

        s.recorder = Process(target= vnc2swf.main, args=[args])

    def start(s):
        s.recorder.start()

    def stop(s):
        mb.recording_should_continue.write(False)
        s.recorder.join()

    def restart(s):
        s.stop()
        s.init()
        s.start()

# To be used with a "with" statement
class video:
    def __init__(s, *args, **kwargs):
        s.recorder = Castro(*args, **kwargs)
    
    def __enter__(s):
        s.recorder.start()
    
    def __exit__(s, type, value, traceback):
        s.recorder.stop()

# Show some output on screen during a test
def countdown_timer():
    stdout.write("\nRecording a 10 second video...\n\n")
    for i in range(10,0,-1):
        stdout.write("%s " % i)
        stdout.flush()
        sleep(1)
    stdout.write("\n")

def test():
    c = Castro()
    c.init()
    c.start()
    countdown_timer()
    c.stop()

if __name__ == '__main__':
    test()
