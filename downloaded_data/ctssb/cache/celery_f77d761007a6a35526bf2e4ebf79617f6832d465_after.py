import os
import sys
import signal


CAN_DETACH = True
try:
    import resource
except ImportError:
    CAN_DETACH = False


def acquire_pidlock(pidfile):
    """Get the :class:`daemon.pidlockfile.PIDLockFile` handler for
    ``pidfile``.

    If the ``pidfile`` already exists, but the process is not running the
    ``pidfile`` will be removed, a ``"stale pidfile"`` message is emitted
    and execution continues as normally. However, if the process is still
    running the program will exit complaning that the program is already
    running in the background somewhere.

    """
    from daemon.pidlockfile import PIDLockFile
    import errno
    pidlock = PIDLockFile(pidfile)
    if not pidlock.is_locked():
        return pidlock
    pid = pidlock.read_pid()
    try:
        os.kill(pid, 0)
    except os.error, exc:
        if exc.errno == errno.ESRCH:
            sys.stderr.write("Stale pidfile exists. Removing it.\n")
            os.unlink(pidfile)
            return PIDLockFile(pidfile)
    except TypeError, exc:
        sys.stderr.write("Broken pidfile found. Removing it.\n")
        os.unlink(pidfile)
        return PIDLockFile(pidfile)
    else:
        raise SystemExit(
                "ERROR: Pidfile (%s) already exists.\n"
                "Seems celeryd is already running? (PID: %d)" % (
                    pidfile, pid))
    return pidlock


def create_daemon_context(logfile=None, pidfile=None, **options):
    if not CAN_DETACH:
        raise RuntimeError(
                "This operating system doesn't support detach.")

    from daemon import DaemonContext

    # Since without stderr any errors will be silently suppressed,
    # we need to know that we have access to the logfile
    if logfile:
        open(logfile, "a").close()

    options["pidlock"] = pidfile and acquire_pidlock(pidfile)

    defaults = {"uid": lambda: os.geteuid(),
                "gid": lambda: os.getegid(),
                "umask": lambda: 0,
                "chroot_directory": lambda: None,
                "working_directory": lambda: os.getcwd()}

    for opt_name, opt_default_gen in defaults.items():
        if opt_name not in options:
            options[opt_name] = opt_default_gen()

    return DaemonContext(chroot_directory=chroot,
                            working_directory=working_directory,
                            umask=umask,
                            pidfile=pidlock,
                            uid=uid,
                            gid=gid)


def reset_signal(signal_name):
    if hasattr(signal, signal_name):
        signal.signal(getattr(signal, signal_name), signal.SIG_DFL)


def install_signal_handler(signal_name, handler):
    """Install a SIGHUP handler."""
    if not hasattr(signal, signal_name):
        return # Platform doesn't support signal.

    signum = getattr(signal, signal_name)
    signal.signal(signum, handler)
