import sys
import signal
import os
import time

import daemonized
import filelock


class BaseDaemon(daemonized.Daemonize):
    def __init__(self, pidfile, lockfile=None, stdin=None, stdout=None,
                 stderr=None):
        self.pidfile = pidfile
        if not lockfile:
            lockfile = os.path.splitext(pidfile)[0] + '.lock'
        self._lock = filelock.FileLock(lockfile)

        dev_null = getattr(os, 'devnull', '/dev/null')
        self.stdin = stdin or dev_null
        self.stdout = stdout or dev_null
        self.stderr = stderr or dev_null

    def run(self, *args, **kwargs):
        raise NotImplementedError('Override this method')

    def start(self):
        if self.is_running():
            msg = "Already running\n"
            sys.stderr.write(msg)
            sys.exit(1)

        self.make_daemon()

        try:
            self._lock.acquire(timeout=1)

        except filelock.Timeout:
            msg = "Unable to acquire lock on {}\n"
            sys.stderr.write(msg.format(self.lockfile))
            sys.exit(1)

        self.run()

        self._lock.release()
        self.delpid()

    def stop(self):
        if not self.is_running():
            return

        pid = self.getpid()

        if not pid:     # Process is running but we are unable to find its id
            msg = "Can't find process id\n"
            sys.stderr.write(msg)
            sys.exit(1)

        self.kill(pid)
        self.delpid()

    def restart(self):
            """
            Restart the daemon
            """
            self.stop()
            self.start()

    def is_running(self):
        running = False

        try:
            self._lock.acquire(timeout=1)

        except filelock.Timeout:
            running = True

        finally:
            self._lock.release()

        return running

    def getpid(self):
        try:
            with open(self.pidfile, 'r') as f:
                pid = int(f.read().strip())
        except (IOError, ValueError):
            pid = None

        return pid

    def kill(self, pid, sig=signal.SIGHUP):
        # Try killing the daemon process
        try:
            i = 0
            while i < 10:
                os.kill(pid, sig)
                time.sleep(0.1)
                i = i + 1
            os.kill(pid, signal.SIGTERM)
        except OSError as err:
            if err.errno == 3:  # No such process
                pass
            else:
                msg = "Failed to kill process {} : {}".format(pid, str(err))
                sys.stderr.write(msg)
                sys.exit(1)

    def delpid(self):
        try:
            os.remove(self.pidfile)
        except OSError as err:
            if err.errno == 2:        # file not found
                pass
            else:
                sys.stderr.write(
                    "Failed to remove pidfile: {}".format(str(err)))
                sys.exit(1)
