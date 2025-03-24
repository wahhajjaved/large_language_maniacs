from pritunl.constants import *
from pritunl.exceptions import *
from pritunl.descriptors import *
import time
import threading
import subprocess

class QueueCom(object):
    def __init__(self):
        self.state = None
        self.state_lock = threading.Lock()
        self.running = threading.Event()
        self.running.set()
        self.last_check = time.time()
        self.processes = []

    def wait_status(self):
        if self.state in (COMPLETE, STOPPED):
            raise QueueStopped('Queue stopped', {
                'queue_state': self.state,
            })
        self.last_check = time.time()
        self.running.wait()

    def popen(self, args):
        while True:
            self.wait_status()

            process = subprocess.Popen(args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            process_data = [process, False]
            self.processes.append(process_data)

            return_code = process.wait()
            self.processes.remove(process_data)

            if return_code:
                if not process_data[1]:
                    raise ValueError('Popen returned ' +
                        'error exit code %r' % return_code)
            else:
                break

    def popen_term_all(self):
        for process in copy.copy(self.processes):
            if not process[1]:
                process[1] = True
                process[0].terminate()

    def popen_kill_all(self):
        for process in copy.copy(self.processes):
            if not process[1]:
                process[1] = True
                process[0].kill()
