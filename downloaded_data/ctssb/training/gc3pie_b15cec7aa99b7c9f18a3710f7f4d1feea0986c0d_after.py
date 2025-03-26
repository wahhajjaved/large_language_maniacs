#! /usr/bin/env python
"""
Run applications as local processes.
"""
# Copyright (C) 2009-2013 GC3, University of Zurich. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
__docformat__ = 'reStructuredText'
__version__ = '$Revision: 1165 $'


# stdlib imports
import cPickle as pickle
from getpass import getuser
import os
import os.path
import posixpath
import time

# GC3Pie imports
import gc3libs
import gc3libs.exceptions
from gc3libs import log, Run
from gc3libs.utils import same_docstring_as, samefile, copy_recursively
from gc3libs.utils import Struct, sh_quote_unsafe, defproperty
from gc3libs.backends import LRMS
from gc3libs.quantity import Memory


def _make_remote_and_local_path_pair(transport, job, remote_relpath,
                                     local_root_dir, local_relpath):
    """
    Return list of (remote_path, local_path) pairs corresponding to
    """
    # see https://github.com/fabric/fabric/issues/306 about why it is
    # correct to use `posixpath.join` for remote paths (instead of
    # `os.path.join`)
    remote_path = posixpath.join(job.execution.lrms_execdir, remote_relpath)
    local_path = os.path.join(local_root_dir, local_relpath)
    if transport.isdir(remote_path):
        # recurse, accumulating results
        result = list()
        for entry in transport.listdir(remote_path):
            result += _make_remote_and_local_path_pair(
                transport, job,
                posixpath.join(remote_relpath, entry),
                local_path, entry)
        return result
    else:
        return [(remote_path, local_path)]


class ShellcmdLrms(LRMS):
    """
    Execute an `Application`:class: instance as a local process.

    Construction of an instance of `ShellcmdLrms` takes the following
    optional parameters (in addition to any parameters taken by the
    base class `LRMS`:class:):

    :param str time_cmd:
      Path to the GNU ``time`` command.  Default is
      `/usr/bin/time`:file: which is correct on all known Linux
      distributions.

      This backend uses many of the
      extended features of GNU ``time``, so the shell-builtins or the
      BSD ``time`` will not work.

    :param str spooldir:
      Path to a filesystem location where to create
      temporary working directories for processes executed through
      this backend. The default value `None` means to use ``$TMPDIR``
      or `/tmp`:file: (see `tempfile.mkftemp` for details).
    """

    # this matches what the ARC grid-manager does
    TIMEFMT = """WallTime=%es
KernelTime=%Ss
UserTime=%Us
CPUUsage=%P
MaxResidentMemory=%MkB
AverageResidentMemory=%tkB
AverageTotalMemory=%KkB
AverageUnsharedMemory=%DkB
AverageUnsharedStack=%pkB
AverageSharedMemory=%XkB
PageSize=%ZB
MajorPageFaults=%F
MinorPageFaults=%R
Swaps=%W
ForcedSwitches=%c
WaitSwitches=%w
Inputs=%I
Outputs=%O
SocketReceived=%r
SocketSent=%s
Signals=%k
ReturnCode=%x"""
    WRAPPER_DIR = '.gc3pie_shellcmd'
    WRAPPER_SCRIPT = 'wrapper_script.sh'
    WRAPPER_OUTPUT_FILENAME = 'resource_usage.txt'
    WRAPPER_PID = 'wrapper.pid'

    RESOURCE_RCDIR = '$HOME/.gc3'
    RESOURCE_FILENAME = 'shellcmd_jobs.pickle'

    def __init__(self, name,
                 # these parameters are inherited from the `LRMS` class
                 architecture, max_cores, max_cores_per_job,
                 max_memory_per_core, max_walltime,
                 auth=None,
                 # these are specific to `ShellcmdLrms`
                 # ignored if `transport` is 'local'
                 frontend='localhost', transport='local',
                 time_cmd='/usr/bin/time',
                 spooldir=None,
                 **extra_args):

        # init base class
        LRMS.__init__(
            self, name,
            architecture, max_cores, max_cores_per_job,
            max_memory_per_core, max_walltime, auth, **extra_args)

        # GNU time is needed
        self.time_cmd = time_cmd

        # default is to use $TMPDIR or '/tmp' (see `tempfile.mkftemp`)
        self.spooldir = spooldir
        if not spooldir:
            self.spooldir = os.getenv('TMPDIR', default='/tmp')

        # Configure transport
        self.frontend = frontend
        if transport == 'local':
            self.transport = gc3libs.backends.transport.LocalTransport()
            self._username = getuser()
        elif transport == 'ssh':
            auth = self._auth_fn()
            self._username = auth.username
            self.transport = gc3libs.backends.transport.SshTransport(
                frontend, username=self._username)
        else:
            raise gc3libs.exceptions.TransportError(
                "Unknown transport '%s'" % transport)

        # use `max_cores` as the max number of processes to allow
        self.user_queued = 0
        self.queued = 0
        self.jobs = {}
        self.total_memory = max_memory_per_core
        self.available_memory = self.total_memory

    @defproperty
    def user_run():
        def fget(self):
            jobs = [job for job in self.jobs.values() if not job['terminated']]
            return len(jobs)
        return locals()

    @defproperty
    def free_slots():
        """Returns the number of cores free"""
        def fget(self):
            """
            Sums the number of corse requested by jobs not in TERM*
            state and returns the difference from the number of cores
            of the resource.
            """
            def filter_cores(job):
                if job['terminated']:
                    return 0
                else:
                    return job['requested_cores']

            return self.max_cores - sum(map(filter_cores, self.jobs.values()))
        return locals()

    @same_docstring_as(LRMS.cancel_job)
    def cancel_job(self, app):
        try:
            pid = int(app.execution.lrms_jobid)
        except ValueError, ex:
            raise gc3libs.exceptions.InvalidArgument(
                "Invalid field `lrms_jobid` in Job '%s':"
                " expected a number, got '%s' (%s) instead"
                % (app, app.execution.lrms_jobid,
                   type(app.execution.lrms_jobid)))

        self.transport.connect()
        exit_code, stdout, stderr = self.transport.execute_command(
            'kill %d' % pid)
        # XXX: should we check that the process actually died?
        if exit_code != 0:
            # Error killing the process. It may not exists or we don't
            # have permission to kill it.
            exit_code, stdout, stderr = self.transport.execute_command(
                "ps ax | grep -E '^ *%d '" % pid)
            if exit_code == 0:
                # The PID refers to an existing process, but we
                # couldn't kill it.
                gc3libs.log.error(
                    "Failed while killing Job '%s': %s" % (pid, stderr))
            else:
                # The PID refers to a non-existing process.
                gc3libs.log.error(
                    "Failed while killing Job '%s'. It refers to non-existent"
                    " local process %s." % (app, app.execution.lrms_jobid))
        self.update_job_resource_usage(pid, terminated=True)

    @same_docstring_as(LRMS.close)
    def close(self):
        # XXX: free any resources in use?
        pass

    def free(self, app):
        """
        Delete the temporary directory where a child process has run.
        The temporary directory is removed with all its content,
        recursively.

        If the deletion is successful, the `lrms_execdir` attribute in
        `app.execution` is reset to `None`; subsequent invocations of
        this method on the same applications do nothing.

        """
        try:
            if app.execution.lrms_execdir is not None:
                self.transport.connect()
                self.transport.remove_tree(app.execution.lrms_execdir)
                app.execution.lrms_execdir = None
        except Exception, ex:
            log.warning("Failed removing folder '%s': %s: %s",
                        app.execution.lrms_execdir, ex.__class__.__name__, ex)
        pid = app.execution.lrms_jobid
        if pid in self.jobs:
            del self.jobs[pid]
            self._update_resource_usage_file()

    def _gather_machine_specs(self):
        """
        Gather information about this machine. Try to be compatible
        with as many *nix OSs as possible.
        """
        self.transport.connect()
        exit_code, stdout, stderr = self.transport.execute_command('uname -m')
        arch = gc3libs.config._parse_architecture(stdout)
        if arch != self.architecture:
            raise gc3libs.exceptions.ConfigurationError(
                "Invalid architecture: configuration file says `%s` but "
                "it actually is `%s`" % (str.join(', ', self.architecture),
                                         str.join(', ', arch)))

        exit_code, stdout, stderr = self.transport.execute_command('uname -s')
        self.running_kernel = stdout.strip()

        if self.running_kernel == 'Linux':
            exit_code, stdout, stderr = self.transport.execute_command('nproc')
            max_cores = int(stdout)

            fd = self.transport.open('/proc/meminfo', 'r')
            # Get the amount of total memory from /proc/meminfo
            self.total_memory = self.max_memory_per_core
            for line in fd:
                if line.startswith('MemTotal'):
                    self.total_memory = int(line.split()[1]) * Memory.KiB
                    break

        elif self.running_kernel == 'Darwin':
            exit_code, stdout, stderr = self.transport.execute_command(
                'sysctl hw.ncpu')
            max_cores = int(stdout.split(':')[-1])

            exit_code, stdout, stderr = self.transport.execute_command(
                'sysctl hw.memsize')
            self.total_memory = int(stdout.split(':')[1]) * Memory.B

        if max_cores != self.max_cores:
            log.warning(
                "`max_cores` value on resource %s mismatch: configuration"
                "file says `%d` while it's actually `%d`. Updating current "
                "value.", self.name, self.max_cores, max_cores)
            self.max_cores = max_cores

        if self.total_memory != self.max_memory_per_core:
            log.warning(
                "`max_memory_per_core` value on resource %s mismatch: "
                "configuration file says `%s` while it's actually `%s`. "
                "Updating current value.", self.name, self.max_memory_per_core,
                self.total_memory)
            self.max_memory_per_core = self.total_memory

        self.available_memory = self.total_memory

        # This is supposed to spit out the ful path on the remote end
        exit_code, stdout, stderr = self.transport.execute_command(
            "echo %s" % sh_quote_unsafe(ShellcmdLrms.RESOURCE_RCDIR))

        resource_home = stdout.strip()
        self.resource_filename = os.path.join(resource_home, ShellcmdLrms.RESOURCE_FILENAME)
        
        # XXX: it is actually necessary to create the folder 
        # as a separate step
        log.info('creating resource file folder: %s ...' % self.resource_filename)
        try:
            self.transport.makedirs(resource_home)
        except Exception, ex:
            gc3libs.log.error("Failed while creating resource file: %s. Error type: %s. Message: %s" % (resource_home, type(ex),str(ex)))
            # cannot continue
            raise

    def _get_resource_usage_from_file(self):
        """
        Get information on total resources from the
        RESOURCE_FILENAME.
        """
        self.transport.connect()
        try:
            fp = self.transport.open(self.resource_filename, 'r')
            self.jobs = pickle.load(fp)
            # Remove job which are in terminated state.
            for pid, job in self.jobs.items():
                if job['terminated']:
                    del self.jobs[job]
            fp.close()
        except:
            self.jobs = {}

    def _update_resource_usage_file(self):
        """
        Update resource usage information on the remote file.
        """
        self.transport.connect()
        # XXX: should create file if necessaty ?
        fp = self.transport.open(self.resource_filename, 'w+')
        pickle.dump(self.jobs, fp, -1)
        fp.close()

    def update_job_resource_usage(self, pid, **kwargs):
        """
        Update information on the resources requested by the job
        identified by `pid` and write these information on the
        resource file too.
        """
        self.jobs[pid].update(kwargs)
        self._update_resource_usage_file()

    @same_docstring_as(LRMS.get_resource_status)
    def get_resource_status(self):
        # if we have been doing our own book-keeping well, then
        # there's no resource status to update
        if not self.updated:
            self._gather_machine_specs()
            self._get_resource_usage_from_file()
            self.updated = True

        def filter_memory(x):
            if x['requested_memory'] is not None:
                return x['requested_memory'].amount(unit=Memory.B)
            else:
                return 0

        used_memory = Memory.B * sum(map(filter_memory, self.jobs.values()))
        if not isinstance(used_memory, Memory):
            used_memory = Memory.B * used_memory
        self.available_memory = self.total_memory - used_memory
        log.debug("Recovering resource information from file %s: "
                  "Available memory: %s, used memory: %s",
                  self.resource_filename, self.available_memory, used_memory)
        return self

    @same_docstring_as(LRMS.get_results)
    def get_results(self, app, download_dir, overwrite=False):
        if app.output_base_url is not None:
            raise gc3libs.exceptions.DataStagingError(
                "Retrieval of output files to non-local destinations"
                " is not supported in the Shellcmd backend.")
        try:
            self.transport.connect()
            # Make list of files to copy, in the form of (remote_path,
            # local_path) pairs.  This entails walking the
            # `Application.outputs` list to expand wildcards and
            # directory references.
            stageout = list()
            for remote_relpath, local_url in app.outputs.iteritems():
                local_relpath = local_url.path
                if remote_relpath == gc3libs.ANY_OUTPUT:
                    remote_relpath = ''
                    local_relpath = ''
                stageout += _make_remote_and_local_path_pair(
                    self.transport, app, remote_relpath,
                    download_dir, local_relpath)

            # copy back all files, renaming them to adhere to the
            # ArcLRMS convention
            log.debug("Downloading job output into '%s' ...", download_dir)
            for remote_path, local_path in stageout:
                log.debug("Downloading remote file '%s' to local file '%s'",
                          remote_path, local_path)
                if (overwrite
                        or not os.path.exists(local_path)
                        or os.path.isdir(local_path)):
                    log.debug("Copying remote '%s' to local '%s'"
                              % (remote_path, local_path))
                    # ignore missing files (this is what ARC does too)
                    self.transport.get(remote_path, local_path,
                                       ignore_nonexisting=True)
                else:
                    log.info("Local file '%s' already exists;"
                             " will not be overwritten!",
                             local_path)

            return  # XXX: should we return list of downloaded files?

        except:
            raise

    def update_job_state(self, app):
        """
        Query the running status of the local process whose PID is
        stored into `app.execution.lrms_jobid`, and map the POSIX
        process status to GC3Libs `Run.State`.
        """
        self.transport.connect()
        pid = app.execution.lrms_jobid
        exit_code, stdout, stderr = self.transport.execute_command(
            "ps ax | grep -E '^ *%d '" % pid)
        if exit_code == 0:
            # Process exists. Check the status
            status = stdout.split()[2]
            if status[0] == 'T':
                # Job stopped
                app.execution.state = Run.State.STOPPED
            elif status[0] in ['R', 'I', 'U', 'S', 'D', 'W']:
                # Job is running. Check manpage of ps both on linux
                # and BSD to know the meaning of these statuses.
                app.execution.state = Run.State.RUNNING
        else:
            # pid does not exists in process table. Check wrapper file
            # contents
            app.execution.state = Run.State.TERMINATING
            if app.requested_memory:
                self.available_memory += app.requested_memory
            wrapper_filename = posixpath.join(
                app.execution.lrms_execdir,
                ShellcmdLrms.WRAPPER_DIR,
                ShellcmdLrms.WRAPPER_OUTPUT_FILENAME)
            try:
                wrapper_file = self.transport.open(wrapper_filename, 'r')
                self.update_job_resource_usage(pid, terminated=True)
            except:
                del self.jobs[pid]
                self._update_resource_usage_file()
                raise gc3libs.exceptions.InvalidArgument(
                    "Job '%s' refers to process wrapper %s which"
                    " ended unexpectedly"
                    % (app, app.execution.lrms_jobid))
            try:
                outcoming = self._parse_wrapper_output(wrapper_file)
                app.execution.returncode = int(outcoming.ReturnCode)
            except:
                wrapper_file.close()

        return app.execution.state

    def submit_job(self, app):
        """
        Run an `Application` instance as a local process.

        :see: `LRMS.submit_job`
        """
        if not self.updated:
            self.get_resource_status()
        if self.free_slots == 0:
            raise gc3libs.exceptions.LRMSSubmitError(
                "Resource %s already running maximum allowed number of jobs"
                " (increase 'max_cores' to raise)." % self.name)

        if app.requested_memory and \
                self.available_memory < app.requested_memory:
            raise gc3libs.exceptions.LRMSSubmitError(
                "Resource %s does not have enough available memory: %s < %s."
                % (self.name, self.available_memory, app.requested_memory))

        gc3libs.log.debug("Executing local command '%s' ..."
                          % (str.join(" ", app.arguments)))

        ## determine execution directory
        self.transport.connect()
        exit_code, stdout, stderr = self.transport.execute_command(
            "mktemp -d %s " % posixpath.join(
                self.spooldir, 'gc3libs.XXXXXX.tmp.d'))
        if exit_code != 0:
            gc3libs.log.error(
                "Error creating temporary directory on host %s: %s"
                % (self.frontend, stderr))

        execdir = stdout.strip()

        # Copy input files to remote dir

        # FIXME: this code is took from
        # gc3libs.backends.batch.BatchSystem.submit_job
        for local_path, remote_path in app.inputs.items():
            remote_path = posixpath.join(execdir, remote_path)
            remote_parent = os.path.dirname(remote_path)
            try:
                if remote_parent not in ['', '.']:
                    log.debug("Making remote directory '%s'" % remote_parent)
                    self.transport.makedirs(remote_parent)
                log.debug("Transferring file '%s' to '%s'" % (local_path.path,
                                                              remote_path))
                self.transport.put(local_path.path, remote_path,
                                   recursive=True)
                # preserve execute permission on input files
                if os.access(local_path.path, os.X_OK):
                    self.transport.chmod(remote_path, 0755)
            except:
                log.critical(
                    "Copying input file '%s' to remote host '%s' failed",
                    local_path.path, self.frontend)
                raise

        app.execution.lrms_execdir = execdir
        app.execution.state = Run.State.RUNNING

        # try to ensure that a local executable really has
        # execute permissions, but ignore failures (might be a
        # link to a file we do not own)
        if app.arguments[0].startswith('./'):
            try:
                os.chmod(app.arguments[0], 0755)
            except OSError:
                pass

        ## set up redirection
        redirection_arguments = ''
        if app.stdin is not None:
            stdin = open(app.stdin, 'r')
            redirection_arguments += " < %s" % app.stdin

        if app.stdout is not None:
            redirection_arguments += " > %s" % app.stdout

        if app.join:
            redirection_arguments += " 2>&1"
        else:
            if app.stderr is not None:
                redirection_arguments += " 2> %s" % app.stderr

        ## set up environment
        env_arguments = ''
        for k, v in app.environment.iteritems():
            env_arguments += "%s=%s; " % (k, v)
        arguments = str.join(' ', (sh_quote_unsafe(i) for i in app.arguments))

        # Create the directory in which pid, output and wrapper script
        # files will be stored
        wrapper_dir = posixpath.join(
            execdir,
            ShellcmdLrms.WRAPPER_DIR)

        if not self.transport.isdir(wrapper_dir):
            self.transport.makedirs(wrapper_dir)

        # Build
        pidfilename = posixpath.join(wrapper_dir,
                                     ShellcmdLrms.WRAPPER_PID)
        wrapper_output_filename = posixpath.join(
            wrapper_dir,
            ShellcmdLrms.WRAPPER_OUTPUT_FILENAME)
        wrapper_script_fname = posixpath.join(
            wrapper_dir,
            ShellcmdLrms.WRAPPER_SCRIPT)

        # Create the wrapper script
        wrapper_script = self.transport.open(
            wrapper_script_fname, 'w')
        wrapper_script.write("""#!/bin/sh
echo $$ > %s
cd %s
exec %s -o %s -f '%s' /bin/sh %s -c '%s %s'
""" % (pidfilename, execdir, self.time_cmd,
       wrapper_output_filename,
       ShellcmdLrms.TIMEFMT, redirection_arguments,
       env_arguments, arguments))
        wrapper_script.close()

        self.transport.chmod(wrapper_script_fname, 0755)

        # Execute the script in background
        self.transport.execute_command(wrapper_script_fname, detach=True)

        # Just after the script has been started the pidfile should be
        # filled in with the correct pid.
        #
        # However, the script can have not been able to write the
        # pidfile yet, so we have to wait a little bit for it...
        pidfile = None
        for retry in gc3libs.utils.ExponentialBackoff():
            try:
                pidfile = self.transport.open(pidfilename, 'r')
                break
            except gc3libs.exceptions.TransportError, ex:
                if '[Errno 2]' in str(ex):  # no such file or directory
                    time.sleep(retry)
                    continue
                else:
                    raise
        if pidfile is None:
            raise gc3libs.exceptions.LRMSSubmitError(
                "Unable to get PID file of submitted process from"
                " execution directory `%s`: %s"
                % (execdir, pidfilename))
        pid = pidfile.read().strip()
        try:
            pid = int(pid)
        except ValueError:
            pidfile.close()
            raise gc3libs.exceptions.LRMSSubmitError(
                "Invalid pid `%s` in pidfile %s." % (pid, pidfilename))
        pidfile.close()

        # Update application and current resources
        app.execution.lrms_jobid = pid
        if app.requested_memory:
            self.available_memory -= app.requested_memory
        self.jobs[pid] = {
            'requested_cores': app.requested_cores,
            'requested_memory': app.requested_memory,
            'execution_dir': execdir,
            'terminated': False, }
        self._update_resource_usage_file()
        return app

    @same_docstring_as(LRMS.peek)
    def peek(self, app, remote_filename, local_file, offset=0, size=None):
        rfh = open(remote_filename, 'r')
        rfh.seek(offset)
        data = rfh.read(size)
        rfh.close()

        try:
            local_file.write(data)
        except (TypeError, AttributeError):
            output_file = open(local_file, 'w+b')
            output_file.write(data)
            output_file.close()

    def validate_data(self, data_file_list=[]):
        """
        Return `False` if any of the URLs in `data_file_list` cannot
        be handled by this backend.

        The `shellcmd`:mod: backend can only handle ``file`` URLs.
        """
        for url in data_file_list:
            if not url.scheme in ['file']:
                return False
        return True

    def _parse_wrapper_output(self, wrapper_file):
        """
        Parse the file saved by the wrapper in
        `ShellcmdLrms.WRAPPER_OUTPUT_FILENAME` inside the WRAPPER_DIR
        in the job's execution directory and return a `Struct`:class:
        containing the values found on the file.

        `wrapper_file` is an opened file. This method will rewind the
        file before reading.
        """
        wrapper_file.seek(0)
        wrapper_output = Struct()
        for line in wrapper_file:
            if '=' not in line:
                continue
            k, v = line.strip().split('=', 1)
            wrapper_output[k] = v

        return wrapper_output

## main: run tests

if "__main__" == __name__:
    import doctest
    doctest.testmod(name="__init__",
                    optionflags=doctest.NORMALIZE_WHITESPACE)
