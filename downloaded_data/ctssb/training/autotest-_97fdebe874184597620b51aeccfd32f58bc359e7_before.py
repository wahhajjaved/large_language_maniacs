import os, itertools, shutil, tempfile
import common

from autotest_lib.client.common_lib import utils, error
from autotest_lib.server import autotest


PROFILER_TMPDIR = "/tmp/profilers"


# control file template for running a job that uses profiler 'name'
run_profiler_control = """\
job.profilers.add(%s)
job.run_test("profiler_test")
job.profilers.delete(%r)
"""


def get_unpassable_types(arg):
    """ Given an argument, returns a set of types contained in arg that are
    unpassable. If arg is an atomic type (e.g. int) it either returns an
    empty set (if the type is passable) or a singleton of the type (if the
    type is not passable). """
    if isinstance(arg, (basestring, int, long)):
        return set()
    elif isinstance(arg, (list, tuple, set, frozenset, dict)):
        if isinstance(arg, dict):
            # keys and values must both be passable
            parts = itertools.chain(arg.iterkeys(), arg.itervalues())
        else:
            # for all other containers we just iterate
            parts = iter(arg)
        types = set()
        for part in parts:
            types |= get_unpassable_types(part)
        return types
    else:
        return set([type(arg)])


def validate_args(args):
    """ Validates arguments. Lists and dictionaries are valid argument types,
    so you can pass *args and **dargs in directly, rather than having to
    iterate over them yourself. """
    unpassable_types = get_unpassable_types(args)
    if unpassable_types:
        msg = "arguments of type '%s' cannot be passed to remote profilers"
        msg %= ", ".join(t.__name__ for t in unpassable_types)
        raise TypeError(msg)


def encode_args(profiler, args, dargs):
    parts = [repr(profiler)]
    parts += [repr(arg) for arg in dargs]
    parts += ["%s=%r" % darg for darg in dargs.iteritems()]
    return ", ".join(parts)


def get_profiler_results_dir(autodir):
    """ Given the directory of the autotest client used to run a profiler,
    return the remote path where profiler results will be stored."""
    return os.path.join(PROFILER_TMPDIR, autodir, "results", "default",
                        "profiler_test", "profiling")


class profiler_proxy(object):
    """ This is a server-side class that acts as a proxy to a real client-side
    profiler class."""

    def __init__(self, job, profiler_name):
        self.job = job
        self.name = profiler_name
        self.installed_hosts = {}
        self.current_test = None

        # does the profiler support rebooting?
        profiler_module = common.setup_modules.import_module(
            profiler_name, "autotest_lib.client.profilers.%s" % profiler_name)
        profiler_class = getattr(profiler_module, profiler_name)
        self.supports_reboot = profiler_class.supports_reboot


    def _install(self):
        """ Install autotest on any current job hosts. """
        current_job_hosts = set(host for host in self.job.hosts
                                if not host.get_autodir() or
                                host.get_autodir().startswith(PROFILER_TMPDIR))
        current_profiler_hosts = set(self.installed_hosts.keys())
        # install autotest on any new hosts in job.hosts
        for host in current_job_hosts - current_profiler_hosts:
            tmp_dir = host.get_tmp_dir(parent=PROFILER_TMPDIR)
            at = autotest.Autotest(host)
            at.install(autodir=tmp_dir)
            self.installed_hosts[host] = (at, tmp_dir)
        # drop any installs from hosts no longer in job.hosts
        for host in current_profiler_hosts - current_job_hosts:
            del self.installed_hosts[host]


    def initialize(self, *args, **dargs):
        validate_args(args)
        validate_args(dargs)
        self.args, self.dargs = args, dargs


    def setup(self, *args, **dargs):
        assert self.args == args and self.dargs == dargs
        # the actual setup happens lazily at start()


    def _signal_client(self, host, autodir, command):
        """ Signal to a client that it should execute profilers.command
        by writing a byte into AUTODIR/profilers.command. """
        path = os.path.join(autodir, "profiler.%s" % command)
        host.run("echo A > %s" % path)


    def _wait_on_client(self, host, autodir, command):
        """ Wait for the client to signal that it's finished by writing
        a byte into AUTODIR/profilers.command. Only waits for 30 seconds
        before giving up. """
        path = os.path.join(autodir, "profiler.%s" % command)
        try:
            host.run("cat %s" % path, ignore_status=True, timeout=30)
        except error.AutoservSSHTimeout:
            pass  # even if it times out, just give up and go ahead anyway


    def _get_hosts(self, host=None):
        """ Returns a dictionary of Host->Autotest mappings currently
        supported by this profiler. If 'host' is not None, all entries
        not matching that host object are filtered out of the dictionary."""
        if host is None:
            return self.installed_hosts
        elif host in self.installed_hosts:
            return {host: self.installed_hosts[host]}
        else:
            return {}


    def start(self, test, host=None):
        self._install()
        encoded_args = encode_args(self.name, self.args, self.dargs)
        control_script = run_profiler_control % (encoded_args, self.name)
        for host, (at, autodir) in self._get_hosts(host).iteritems():
            fifo_pattern = os.path.join(autodir, "profiler.*")
            host.run("rm -f %s" % fifo_pattern)
            host.run("mkfifo %s" % os.path.join(autodir, "profiler.ready"))
            at.run(control_script, background=True)
            self._wait_on_client(host, autodir, "ready")
            self._signal_client(host, autodir, "start")
        self.current_test = test


    def stop(self, test, host=None):
        assert self.current_test == test
        for host, (at, autodir) in self._get_hosts(host).iteritems():
            self._signal_client(host, autodir, "stop")


    def report(self, test, host=None, wait_on_client=True):
        assert self.current_test == test
        self.current_test = None

        # signal to all the clients that they should report
        if wait_on_client:
            for host, (at, autodir) in self._get_hosts(host).iteritems():
                self._signal_client(host, autodir, "report")

        # pull back all the results
        for host, (at, autodir) in self._get_hosts(host).iteritems():
            if wait_on_client:
                self._wait_on_client(host, autodir, "finished")
            results_dir = get_profiler_results_dir(autodir) + "/"
            local_dir = os.path.join(test.profdir, host.hostname)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)

            tempdir = tempfile.mkdtemp(dir=self.job.tmpdir)
            try:
                host.get_file(results_dir, tempdir)
            except error.AutoservRunError:
                pass # no files to pull back, nothing we can do
            utils.merge_trees(tempdir, local_dir)
            shutil.rmtree(tempdir, ignore_errors=True)


    def handle_reboot(self, host):
        if self.current_test:
            test = self.current_test
            if not self.supports_reboot:
                msg = "profiler '%s' does not support rebooting during tests"
                msg %= self.name
                self.job.record("WARN", os.path.basename(test.outputdir),
                                None, msg)
            self.report(test, host, wait_on_client=False)
            self.start(test, host)
