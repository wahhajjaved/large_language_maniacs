"""
Internal global error types
"""

import sys, traceback
from traceback import format_exception

# Add names you want to be imported by 'from errors import *' to this list.
# This must be list not a tuple as we modify it to include all of our
# the Exception classes we define below at the end of this file.
__all__ = ['format_error']


def format_error():
    t, o, tb = sys.exc_info()
    trace = format_exception(t, o, tb)
    # Clear the backtrace to prevent a circular reference
    # in the heap -- as per tutorial
    tb = ''

    return ''.join(trace)


class JobContinue(SystemExit):
    """Allow us to bail out requesting continuance."""
    pass


class JobComplete(SystemExit):
    """Allow us to bail out indicating continuation not required."""
    pass


class AutotestError(Exception):
    """The parent of all errors deliberatly thrown within the client code."""
    pass


class JobError(AutotestError):
    """Indicates an error which terminates and fails the whole job (ABORT)."""
    pass


class UnhandledJobError(JobError):
    """Indicates an unhandled error in a job."""
    def __init__(self, unhandled_exception):
        if isinstance(unhandled_exception, JobError):
            JobError.__init__(self, *unhandled_exception.args)
        else:
            msg = "Unhandled %s: %s"
            msg %= (unhandled_exception.__class__.__name__,
                    unhandled_exception)
            msg += "\n" + traceback.format_exc()
            JobError.__init__(self, msg)


class TestBaseException(AutotestError):
    """The parent of all test exceptions."""
    # Children are required to override this.  Never instantiate directly.
    exit_status="NEVER_RAISE_THIS"


class TestError(TestBaseException):
    """Indicates that something went wrong with the test harness itself."""
    exit_status="ERROR"


class TestNAError(TestBaseException):
    """Indictates that the test is Not Applicable.  Should be thrown
    when various conditions are such that the test is inappropriate."""
    exit_status="TEST_NA"


class TestFail(TestBaseException):
    """Indicates that the test failed, but the job will not continue."""
    exit_status="FAIL"


class TestWarn(TestBaseException):
    """Indicates that bad things (may) have happened, but not an explicit
    failure."""
    exit_status="WARN"


class UnhandledTestError(TestError):
    """Indicates an unhandled error in a test."""
    def __init__(self, unhandled_exception):
        if isinstance(unhandled_exception, TestError):
            TestError.__init__(self, *unhandled_exception.args)
        else:
            msg = "Unhandled %s: %s"
            msg %= (unhandled_exception.__class__.__name__,
                    unhandled_exception)
            msg += "\n" + traceback.format_exc()
            TestError.__init__(self, msg)


class UnhandledTestFail(TestFail):
    """Indicates an unhandled fail in a test."""
    def __init__(self, unhandled_exception):
        if isinstance(unhandled_exception, TestFail):
            TestFail.__init__(self, *unhandled_exception.args)
        else:
            msg = "Unhandled %s: %s"
            msg %= (unhandled_exception.__class__.__name__,
                    unhandled_exception)
            msg += "\n" + traceback.format_exc()
            TestFail.__init__(self, msg)


class CmdError(TestError):
    """\
    Indicates that a command failed, is fatal to the test unless caught.
    """
    def __init__(self, command, result_obj, additional_text=None):
        TestError.__init__(self, command, result_obj, additional_text)
        self.command = command
        self.result_obj = result_obj
        self.additional_text = additional_text


    def __str__(self):
        if self.result_obj.exit_status is None:
            msg = "Command <%s> failed and is not responding to signals"
            msg %= self.command
        else:
            msg = "Command <%s> failed, rc=%d"
            msg %= (self.command, self.result_obj.exit_status)

        if self.additional_text:
            msg += ", " + self.additional_text
        msg += '\n' + repr(self.result_obj)
        return msg


class PackageError(TestError):
    """Indicates an error trying to perform a package operation."""
    pass


class BarrierError(JobError):
    """Indicates an error happened during a barrier operation."""
    pass


class InstallError(JobError):
    """Indicates an installation error which Terminates and fails the job."""
    pass


class AutotestRunError(AutotestError):
    """Indicates a problem running server side control files."""
    pass


class AutotestTimeoutError(AutotestError):
    """This exception is raised when an autotest test exceeds the timeout
    parameter passed to run_timed_test and is killed.
    """


# server-specific errors

class AutoservError(Exception):
    pass


class AutoservSSHTimeout(AutoservError):
    """SSH experienced a connection timeout"""
    pass


class AutoservRunError(AutoservError):
    """\
    Errors raised by one of the run functions.  Should always be
    constructed with a tuple of two args (error description (str),
    run result object).
    """
    def __init__(self, description, result_obj):
        self.description = description
        self.result_obj = result_obj
        AutoservError.__init__(self, description, result_obj)

    def __str__(self):
        return self.description + '\n' + repr(self.result_obj)


class AutoservVirtError(AutoservError):
    """Vitualization related error"""
    pass


class AutoservUnsupportedError(AutoservError):
    """Error raised when you try to use an unsupported optional feature"""
    pass


class AutoservHostError(AutoservError):
    """Error reaching a host"""
    pass


class AutoservRebootError(AutoservError):
    """Error occured while rebooting a machine"""
    pass


class AutoservSubcommandError(AutoservError):
    """Indicates an error while executing a (forked) subcommand"""
    def __init__(self, func, exit_code):
        AutoservError.__init__(self, func, exit_code)
        self.func = func
        self.exit_code = exit_code

    def __str__(self):
        return ("Subcommand %s failed with exit code %d" %
                (self.func, self.exit_code))


# This MUST remain at the end of the file.
# Limit 'from error import *' to only import the exception instances.
for _name, _thing in locals().items():
    try:
        if issubclass(_thing, Exception):
            __all__.append(_name)
    except TypeError:
        pass  # _thing not a class
__all__ = tuple(__all__)
