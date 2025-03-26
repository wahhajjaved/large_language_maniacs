import psutil
import os
import stat
import sys
import time
import traceback
from tempfile import NamedTemporaryFile
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from .streaming_log import StreamingLog
from shortuuid import ShortUUID
import atexit
from threading import Thread
from .config import Config
import logging
import socket
import click
from wandb import __stage_dir__, Error
from wandb import util
from .run import Run
logger = logging.getLogger(__name__)


def editor(content='', marker='# Before we start this run, enter a brief description. (to skip, direct stdin to dev/null: `python train.py < /dev/null`)\n'):
    message = click.edit(content + '\n\n' + marker)
    if message is not None:
        return message.split(marker, 1)[0].rstrip('\n')


class Echo(object):
    def __init__(self, log):
        self.terminal = sys.stdout
        self.log = log
        self.thread = None

    def write(self, message):
        self.terminal.write(message)
        #TODO: ThreadPool
        self.thread = Thread(target=self.log.write, args=(message,))
        self.thread.start()

    def flush(self):
        self.terminal.flush()

    def close(self, failed=False):
        if self.thread:
            self.thread.join()
        if failed:
            # TODO: unfortunate line_buffer access
            self.log.push([[self.log.line_buffer.line_number +
                            1, "ERROR: %s\n" % failed, "error"]])
            sys.stderr.write("ERROR: %s\n" % failed)
            failed = True
        self.log.heartbeat(complete=True, failed=failed)


class ExitHooks(object):
    def __init__(self):
        self.exit_code = None
        self.exception = None

    def hook(self):
        self._orig_exit = sys.exit
        self._orig_excepthook = sys.excepthook
        sys.exit = self.exit
        sys.excepthook = self.excepthook

    def exit(self, code=0):
        self.exit_code = code
        self._orig_exit(code)

    def excepthook(self, exc_type, exc, *args):
        self.exception = exc
        self._orig_excepthook(exc_type, exc, *args)


class Sync(object):
    """Watches for files to change and automatically pushes them
    """

    def __init__(self, api, run=None, project=None, tags=[], datasets=[], config={}, description=None, dir=None):
        # 1.6 million 6 character combinations
        runGen = ShortUUID(alphabet=list(
            "0123456789abcdefghijklmnopqrstuvwxyz"))
        self.run_id = run or runGen.random(6)
        self._project = project or api.settings("project")
        self._entity = api.settings("entity")
        logger.debug("Initialized sync for %s/%s", self._project, self.run_id)
        self._dpath = os.path.join(__stage_dir__, 'description.md')
        self._description = description or (os.path.exists(self._dpath) and open(
            self._dpath).read()) or os.getenv('WANDB_DESCRIPTION')
        try:
            self.tty = sys.stdin.isatty() and os.getpgrp() == os.tcgetpgrp(sys.stdout.fileno())
        except OSError:
            self.tty = False
        if not os.getenv('DEBUG') and not self._description and self.tty:
            self._description = editor()
        self._config = Config(config)
        self._proc = psutil.Process(os.getpid())
        self._api = api
        self._tags = tags
        self._handler = PatternMatchingEventHandler()
        self._handler.on_created = self.add
        self._handler.on_modified = self.push
        self.url = "{base}/{entity}/{project}/runs/{run}".format(
            project=self._project,
            entity=self._entity,
            run=self.run_id,
            base="https://app.wandb.ai"
        )
        self.log = StreamingLog(self.run_id)
        self._hooks = ExitHooks()
        self._hooks.hook()
        self._observer = Observer()
        if dir is None:
            self._watch_dir = os.path.join(__stage_dir__, 'run-%s' % self.run_id)
            util.mkdir_exists_ok(self._watch_dir)
        else:
            self._watch_dir = os.path.abspath(dir)

        self._observer.schedule(self._handler, self._watch_dir, recursive=True)

        self.run = Run(self._watch_dir, self._config)

    def watch(self, files):
        try:
            # TODO: better failure handling
            self._api.upsert_run(name=self.run_id, project=self._project, entity=self._entity,
                                 config=self._config.__dict__, description=self._description, host=socket.gethostname())
            self._handler._patterns = [
                os.path.join(self._watch_dir, os.path.normpath(f)) for f in files]
            # Ignore hidden files/folders
            self._handler._ignore_patterns = ['*/.*']
            if os.path.exists(__stage_dir__ + "diff.patch"):
                self._api.push("{project}/{run}".format(
                    project=self._project,
                    run=self.run_id
                ), {"diff.patch": open(__stage_dir__ + "diff.patch", "rb")})
            self._observer.start()
            print("Syncing %s" % self.url)
            # TODO: put the sub process run logic here?
            if self.source_proc:
                self.log.write(" ".join(self.source_proc.cmdline()) + "\n\n")
                line = sys.stdin.readline()
                while line:
                    sys.stdout.write(line)
                    self.log.write(line)
                    # TODO: push log every few minutes...
                    line = sys.stdin.readline()
                self.stop()
            else:
                self.log.write(" ".join(psutil.Process(
                    os.getpid()).cmdline()) + "\n\n")
                # let's hijack stdout
                self._echo = Echo(self.log)
                sys.stdout = self._echo
                logger.debug("Swapped stdout")
                #TODO: stderr
                atexit.register(self.stop)
        except KeyboardInterrupt:
            self.stop()
        except Error:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print("!!! Fatal W&B Error: %s" % exc_value)
            lines = traceback.format_exception(
                exc_type, exc_value, exc_traceback)
            logger.error('\n'.join(lines))

    def stop(self):
        # This is a a heuristic delay to catch files that were written just before
        # the end of the script. This is unverified, but theoretically the file
        # change notification process used by watchdog (maybe inotify?) is
        # asynchronous. It's possible we could miss files if 10s isn't long enough.
        # TODO: Guarantee that all files will be saved.
        print("Script ended, waiting for final file modifications.")
        time.sleep(10.0)
        self.log.tempfile.flush()
        print("Pushing log")
        slug = "{project}/{run}".format(
            project=self._project,
            run=self.run_id
        )
        self._api.push(
            slug, {"training.log": open(self.log.tempfile.name, "rb")})
        os.path.exists(self._dpath) and os.remove(self._dpath)
        print("Synced %s" % self.url)
        self._echo.close(failed=self._hooks.exception)
        self.log.close()
        try:
            self._observer.stop()
            self._observer.join()
        # TODO: py2 TypeError: PyCObject_AsVoidPtr called with null pointer
        except TypeError:
            pass
        # TODO: py3 SystemError: <built-in function stop> returned a result with an error set
        except SystemError:
            pass

    # TODO: limit / throttle the number of adds / pushes
    def add(self, event):
        self.push(event)

    # TODO: is this blocking the main thread?
    def push(self, event):
        if os.stat(event.src_path).st_size == 0 or os.path.isdir(event.src_path):
            return None
        file_name = os.path.relpath(event.src_path, self._watch_dir)
        if logger.parent.handlers[0]:
            debugLog = logger.parent.handlers[0].stream
        else:
            debugLog = None
        print("Pushing %s" % file_name)
        with open(event.src_path, 'rb') as f:
            self._api.push(self._project, {file_name: f}, bucket=self.run_id,
                        description=self._description, progress=debugLog)

    @property
    def source_proc(self):
        mode = os.fstat(0).st_mode
        if not stat.S_ISFIFO(mode):
            # stdin is not a pipe
            return None
        else:
            source = self._proc.parent().children()[0]
            return None if source == self._proc else source

    def echo(self):
        print(sys.stdin.read())
