#
# A helper for hypnotoad plugins to enable fault tolerant filesystem
# operations.
#

import datetime
import time
import errno
import logging
import os
import subprocess
import signal

LOG = logging.getLogger('root')

class hypnofs(object):

    def __init__(self):
        self.dry_run_mode = True

    def timeout_command(self, command, timeout=10):
        """
        Call a shell command and either return its output or kill it. Continue
        if the process doesn't get killed cleanly (for D-state).
        """
        start = datetime.datetime.now()
        process = subprocess.Popen( \
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while process.poll() is None:
            time.sleep(0.1)
            now = datetime.datetime.now()

            if (now - start).seconds > timeout:
                os.kill(process.pid, signal.SIGKILL)
                os.waitpid(-1, os.WNOHANG)
                raise IOError(errno.EWOULDBLOCK)

        return process.stdout.readlines()

    def callback_wrap(self, args, timeout, fail_cb, fail_obj, throw_exc=False):
        """
        Wraps a command with the potential for timeout to provide a
        callback on failure feature.
        """
        result = None
        failed = False

        try:
            result = self.timeout_command(args, timeout)
        except IOError, exc:
            if exc.args[0] == errno.EWOULDBLOCK:
                if fail_cb:
                    fail_cb(fail_obj)
                failed = True
            if throw_exc:
                raise

        return result, failed

    def makedirs(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.makedirs()"""

        LOG.debug("Creating directory with path of '" + path + "'.")

        if not self.dry_run_mode:
            result, failed = self.callback_wrap( \
                ['mkdir', '-p', path], timeout, fail_cb, fail_obj)
            return result, failed
        else:
            return (None,False)

    def chmod(self, path, perms, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.chmod()"""

        LOG.debug("Changing permissions of '" + path + "' to '" + perms + "'.")

        if not self.dry_run_mode:
            result, failed = self.callback_wrap( \
                ['chmod', perms, path], timeout, fail_cb, fail_obj)
            return result, failed
        else:
            return (None,False)

    def chown(self, path, owner='-1', group='-1', timeout=10, \
        fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.chown()."""

        LOG.debug("Changing ownership of '" + \
            path + "' to '" + owner + ":" + group + "'.")

        if not self.dry_run_mode:
            result, failed = self.callback_wrap( \
                ['chown', owner + ':' + group, path], timeout, fail_cb, fail_obj)
            return result, failed
        else:
            return (None,False)

    def symlink(self, src, dest, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.symlink()"""

        LOG.debug("Creating a symlink from '" + src + "' to '" + dest + "'.")

        if not self.dry_run_mode:
            result, failed = self.callback_wrap( \
                ['ln', '-s', '-n', '-f', src, dest], timeout, fail_cb, fail_obj)
            return result, failed
        else:
            return (None,False)

    def isdir(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.path.isdir()"""

        cmd_output, failed = self.callback_wrap( \
            ['file', '-b', path], timeout, fail_cb, fail_obj)

        if "directory" in cmd_output[0]:
            return True, failed
        else:
            return False, failed

    def isfile(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.path.isfile()"""

        cmd_output, failed = self.callback_wrap( \
            ['file', '-b', path], timeout, fail_cb, fail_obj)

        if len(cmd_output) < 1:
            return False, failed
        elif "directory" in cmd_output[0]:
            return False, failed
        elif "ERROR" in cmd_output[0]:
            return False, failed
        else:
            return True, failed

    def islink(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.path.islink()"""

        cmd_output, failed = self.callback_wrap( \
            ['file', '-b', path], timeout, fail_cb, fail_obj)

        if "symbolic link" in cmd_output[0]:
            return True, failed
        else:
            return False, failed

    def path_exists(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.path.exists()"""

        cmd_output, failed = self.callback_wrap( \
            ['file', '-b', path], timeout, fail_cb, fail_obj)

        if "ERROR" in cmd_output[0]:
            return False, failed
        else:
            return True, failed

    def listdir(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.listdir()"""

        cmd_output, failed = self.callback_wrap( \
            ['find', path, '-maxdepth', '1', '-printf', '%f\\n'], \
            timeout, fail_cb, fail_obj)

        if failed:
            return None, failed
        return [i.strip() for i in cmd_output], failed

    def ismount(self, path, timeout=10, fail_cb=None, fail_obj=None):
        """A fault tolerant version of os.path.ismount()"""

        cmd_output, failed = self.callback_wrap( \
            ['mountpoint', path], timeout, fail_cb, fail_obj)

        if "is a mountpoint" in cmd_output[0]:
            return True, failed
        else:
            return False, failed

# EOF
