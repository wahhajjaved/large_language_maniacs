# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Initialization of qutebrowser and application-wide things."""

import os
import sys
import subprocess
import faulthandler
import configparser
import signal
import warnings
import bdb
import base64
import functools
import traceback

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import (pyqtSlot, qInstallMessageHandler, QTimer, QUrl,
                          QStandardPaths, QObject)

import qutebrowser
from qutebrowser.commands import cmdutils, runners
from qutebrowser.config import style, config, websettings
from qutebrowser.network import qutescheme, proxy
from qutebrowser.browser import quickmarks, cookies, downloads, cache
from qutebrowser.widgets import mainwindow, console, crash
from qutebrowser.keyinput import modeman
from qutebrowser.utils import (log, version, message, readline, utils, qtutils,
                               urlutils, debug, objreg, usertypes)
# We import utilcmds to run the cmdutils.register decorators.
from qutebrowser.utils import utilcmds  # pylint: disable=unused-import


class Application(QApplication):

    """Main application instance.

    Attributes:
        _args: ArgumentParser instance.
        _shutting_down: True if we're currently shutting down.
        _quit_status: The current quitting status.
        _crashdlg: The crash dialog currently open.
        _crashlogfile: A file handler to the fatal crash logfile.
        _event_filter: The EventFilter for the application.
    """

    def __init__(self, args):
        """Constructor.

        Args:
            Argument namespace from argparse.
        """
        self._quit_status = {
            'crash': True,
            'tabs': False,
            'main': False,
        }
        self._shutting_down = False
        self._crashdlg = None
        self._crashlogfile = None

        if args.debug:
            # We don't enable this earlier because some imports trigger
            # warnings (which are not our fault).
            warnings.simplefilter('default')

        qt_args = qtutils.get_args(args)
        log.init.debug("Qt arguments: {}, based on {}".format(qt_args, args))
        super().__init__(qt_args)
        sys.excepthook = self._exception_hook

        self._args = args
        objreg.register('args', args)
        QTimer.singleShot(0, self._open_pages)

        objreg.register('app', self)

        if self._args.version:
            print(version.version())
            print()
            print()
            print(qutebrowser.__copyright__)
            print()
            print(version.GPL_BOILERPLATE.strip())
            sys.exit(0)

        log.init.debug("Starting init...")
        self.setQuitOnLastWindowClosed(False)
        self.setOrganizationName("qutebrowser")
        self.setApplicationName("qutebrowser")
        self.setApplicationVersion(qutebrowser.__version__)
        utils.actute_warning()
        self._init_modules()

        log.init.debug("Initializing eventfilter...")
        self._event_filter = modeman.EventFilter(self)
        self.installEventFilter(self._event_filter)

        log.init.debug("Connecting signals...")
        self._connect_signals()

        log.init.debug("Applying python hacks...")
        self._python_hacks()

        log.init.debug("Init done!")

        if self._crashdlg is not None:
            self._crashdlg.raise_()

    def __repr__(self):
        return utils.get_repr(self)

    def _init_modules(self):
        """Initialize all 'modules' which need to be initialized."""
        log.init.debug("Initializing readline-bridge...")
        readline_bridge = readline.ReadlineBridge()
        objreg.register('readline-bridge', readline_bridge)

        log.init.debug("Initializing config...")
        config.init(self._args)
        log.init.debug("Initializing crashlog...")
        self._handle_segfault()
        log.init.debug("Initializing websettings...")
        websettings.init()
        log.init.debug("Initializing quickmarks...")
        quickmarks.init()
        log.init.debug("Initializing proxy...")
        proxy.init()
        log.init.debug("Initializing cookies...")
        cookie_jar = cookies.CookieJar(self)
        objreg.register('cookie-jar', cookie_jar)
        log.init.debug("Initializing cache...")
        diskcache = cache.DiskCache(self)
        objreg.register('cache', diskcache)
        log.init.debug("Initializing downloads...")
        download_manager = downloads.DownloadManager(self)
        objreg.register('download-manager', download_manager)
        log.init.debug("Initializing main window...")
        mainwindow.MainWindow.spawn(False if self._args.nowindow else True)
        log.init.debug("Initializing debug console...")
        debug_console = console.ConsoleWidget()
        objreg.register('debug-console', debug_console)

    def _handle_segfault(self):
        """Handle a segfault from a previous run."""
        # FIXME If an empty logfile exists, we log to stdout instead, which is
        # the only way to not break multiple instances.
        # However this also means if the logfile is there for some weird
        # reason, we'll *always* log to stderr, but that's still better than no
        # dialogs at all.
        # probably irrelevant with single instance support
        # https://github.com/The-Compiler/qutebrowser/issues/10
        path = utils.get_standard_dir(QStandardPaths.DataLocation)
        logname = os.path.join(path, 'crash.log')
        # First check if an old logfile exists.
        if os.path.exists(logname):
            with open(logname, 'r', encoding='ascii') as f:
                data = f.read()
            if data:
                # Crashlog exists and has data in it, so something crashed
                # previously.
                try:
                    os.remove(logname)
                except PermissionError:
                    log.init.warning("Could not remove crash log!")
                else:
                    self._init_crashlogfile()
                self._crashdlg = crash.FatalCrashDialog(data)
                self._crashdlg.show()
            else:
                # Crashlog exists but without data.
                # This means another instance is probably still running and
                # didn't remove the file. As we can't write to the same file,
                # we just leave faulthandler as it is and log to stderr.
                log.init.warning("Empty crash log detected. This means either "
                                 "another instance is running (then ignore "
                                 "this warning) or the file is lying here "
                                 "because of some earlier crash (then delete "
                                 "{}).".format(logname))
                self._crashlogfile = None
        else:
            # There's no log file, so we can use this to display crashes to the
            # user on the next start.
            self._init_crashlogfile()

    def _init_crashlogfile(self):
        """Start a new logfile and redirect faulthandler to it."""
        path = utils.get_standard_dir(QStandardPaths.DataLocation)
        logname = os.path.join(path, 'crash.log')
        self._crashlogfile = open(logname, 'w', encoding='ascii')
        faulthandler.enable(self._crashlogfile)
        if (hasattr(faulthandler, 'register') and
                hasattr(signal, 'SIGUSR1')):
            # If available, we also want a traceback on SIGUSR1.
            # pylint: disable=no-member
            faulthandler.register(signal.SIGUSR1)

    def _open_pages(self):
        """Open startpage etc. and process commandline args."""
        self._process_init_args()
        self._open_startpage()
        self._open_quickstart()

    def _process_init_args(self):
        """Process commandline args.

        URLs to open have no prefix, commands to execute begin with a colon.
        """
        win_id = 0
        for cmd in self._args.command:
            if cmd.startswith(':'):
                log.init.debug("Startup cmd {}".format(cmd))
                commandrunner = runners.CommandRunner(win_id)
                commandrunner.run_safely_init(cmd.lstrip(':'))
            elif not cmd:
                log.init.debug("Empty argument")
                win_id = mainwindow.MainWindow.spawn()
            else:
                tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                            window=win_id)
                log.init.debug("Startup URL {}".format(cmd))
                try:
                    url = urlutils.fuzzy_url(cmd)
                except urlutils.FuzzyUrlError as e:
                    message.error(0, "Error in startup argument '{}': "
                                     "{}".format(cmd, e))
                else:
                    tabbed_browser.tabopen(url)

    def _open_startpage(self):
        """Open startpage in windows which are still empty."""
        for win_id in objreg.window_registry:
            tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                        window=win_id)
            if tabbed_browser.count() == 0:
                log.init.debug("Opening startpage")
                for urlstr in config.get('general', 'startpage'):
                    try:
                        url = urlutils.fuzzy_url(urlstr)
                    except urlutils.FuzzyUrlError as e:
                        message.error(0, "Error when opening startpage: "
                                         "{}".format(e))
                        tabbed_browser.tabopen(QUrl('about:blank'))
                    else:
                        tabbed_browser.tabopen(url)

    def _open_quickstart(self):
        """Open quickstart if it's the first start."""
        state_config = objreg.get('state-config')
        try:
            quickstart_done = state_config['general']['quickstart-done'] == '1'
        except KeyError:
            quickstart_done = False
        if not quickstart_done:
            tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                        window='current')
            tabbed_browser.tabopen(
                QUrl('http://www.qutebrowser.org/quickstart.html'))
            try:
                state_config.add_section('general')
            except configparser.DuplicateSectionError:
                pass
            state_config['general']['quickstart-done'] = '1'

    def _python_hacks(self):
        """Get around some PyQt-oddities by evil hacks.

        This sets up the uncaught exception hook, quits with an appropriate
        exit status, and handles Ctrl+C properly by passing control to the
        Python interpreter once all 500ms.
        """
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        timer = usertypes.Timer(self, 'python_hacks')
        timer.start(500)
        timer.timeout.connect(lambda: None)
        objreg.register('python-hack-timer', timer)

    def _connect_signals(self):
        """Connect all signals to their slots."""
        config_obj = objreg.get('config')
        self.lastWindowClosed.connect(self.shutdown)
        config_obj.style_changed.connect(style.get_stylesheet.cache_clear)

    def _get_widgets(self):
        """Get a string list of all widgets."""
        widgets = self.allWidgets()
        widgets.sort(key=lambda e: repr(e))
        return [repr(w) for w in widgets]

    def _get_pyqt_objects(self, lines, obj, depth=0):
        """Recursive method for get_all_objects to get Qt objects."""
        for kid in obj.findChildren(QObject):
            lines.append('    ' * depth + repr(kid))
            self._get_pyqt_objects(lines, kid, depth + 1)

    def get_all_objects(self):
        """Get all children of an object recursively as a string."""
        output = ['']
        widget_lines = self._get_widgets()
        widget_lines = ['    ' + e for e in widget_lines]
        widget_lines.insert(0, "Qt widgets - {} objects".format(
            len(widget_lines)))
        output += widget_lines
        pyqt_lines = []
        self._get_pyqt_objects(pyqt_lines, self)
        pyqt_lines = ['    ' + e for e in pyqt_lines]
        pyqt_lines.insert(0, 'Qt objects - {} objects:'.format(
            len(pyqt_lines)))
        output += pyqt_lines
        output += ['']
        output += objreg.dump_objects()
        return '\n'.join(output)

    def _recover_pages(self, forgiving=False):
        """Try to recover all open pages.

        Called from _exception_hook, so as forgiving as possible.

        Args:
            forgiving: Whether to ignore exceptions.

        Return:
            A list containing a list for each window, which in turn contain the
            opened URLs.
        """
        pages = []
        for win_id in objreg.window_registry:
            win_pages = []
            tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                        window=win_id)
            for tab in tabbed_browser.widgets():
                try:
                    urlstr = tab.cur_url.toString(
                        QUrl.RemovePassword | QUrl.FullyEncoded)
                    if urlstr:
                        win_pages.append(urlstr)
                except Exception:  # pylint: disable=broad-except
                    if forgiving:
                        log.destroy.exception("Error while recovering tab")
                    else:
                        raise
            pages.append(win_pages)
        return pages

    def _save_geometry(self):
        """Save the window geometry to the state config."""
        last_win_id = sorted(objreg.window_registry)[-1]
        main_window = objreg.get('main-window', scope='window',
                                 window=last_win_id)
        state_config = objreg.get('state-config')
        data = bytes(main_window.saveGeometry())
        geom = base64.b64encode(data).decode('ASCII')
        try:
            state_config.add_section('geometry')
        except configparser.DuplicateSectionError:
            pass
        state_config['geometry']['mainwindow'] = geom

    def _destroy_crashlogfile(self):
        """Clean up the crash log file and delete it."""
        if self._crashlogfile is None:
            return
        # We use sys.__stderr__ instead of sys.stderr here so this will still
        # work when sys.stderr got replaced, e.g. by "Python Tools for Visual
        # Studio".
        if sys.__stderr__ is not None:
            faulthandler.enable(sys.__stderr__)
        else:
            faulthandler.disable()
        self._crashlogfile.close()
        try:
            os.remove(self._crashlogfile.name)
        except (PermissionError, FileNotFoundError):
            log.destroy.exception("Could not remove crash log!")

    def _exception_hook(self, exctype, excvalue, tb):
        """Handle uncaught python exceptions.

        It'll try very hard to write all open tabs to a file, and then exit
        gracefully.
        """
        # pylint: disable=broad-except

        if exctype is bdb.BdbQuit or not issubclass(exctype, Exception):
            # pdb exit, KeyboardInterrupt, ...
            try:
                self.shutdown()
                return
            except Exception:
                log.init.exception("Error while shutting down")
                self.quit()
                return

        exc = (exctype, excvalue, tb)
        sys.__excepthook__(*exc)

        self._quit_status['crash'] = False

        try:
            pages = self._recover_pages(forgiving=True)
        except Exception:
            log.destroy.exception("Error while recovering pages")
            pages = []

        try:
            history = objreg.get('command-history')[-5:]
        except Exception:
            log.destroy.exception("Error while getting history: {}")
            history = []

        try:
            objects = self.get_all_objects()
        except Exception:
            log.destroy.exception("Error while getting objects")
            objects = ""

        try:
            self.lastWindowClosed.disconnect(self.shutdown)
        except TypeError:
            log.destroy.exception("Error while preventing shutdown")
        QApplication.closeAllWindows()
        self._crashdlg = crash.ExceptionCrashDialog(pages, history, exc,
                                                    objects)
        ret = self._crashdlg.exec_()
        if ret == QDialog.Accepted:  # restore
            self.restart(shutdown=False, pages=pages)
        # We might risk a segfault here, but that's better than continuing to
        # run in some undefined state, so we only do the most needed shutdown
        # here.
        qInstallMessageHandler(None)
        self._destroy_crashlogfile()
        sys.exit(1)

    @cmdutils.register(instance='app', name=['quit', 'q'])
    def quit(self):
        """Quit qutebrowser."""
        QApplication.closeAllWindows()

    @cmdutils.register(instance='app', ignore_args=True)
    def restart(self, shutdown=True, pages=None):
        """Restart qutebrowser while keeping existing tabs open."""
        if pages is None:
            pages = self._recover_pages()
        log.destroy.debug("sys.executable: {}".format(sys.executable))
        log.destroy.debug("sys.path: {}".format(sys.path))
        log.destroy.debug("sys.argv: {}".format(sys.argv))
        log.destroy.debug("frozen: {}".format(hasattr(sys, 'frozen')))
        if os.path.basename(sys.argv[0]) == 'qutebrowser':
            # Launched via launcher script
            args = [sys.argv[0]]
            cwd = None
        elif hasattr(sys, 'frozen'):
            args = [sys.executable]
            cwd = os.path.abspath(os.path.dirname(sys.executable))
        else:
            args = [sys.executable, '-m', 'qutebrowser']
            cwd = os.path.join(os.path.abspath(os.path.dirname(
                               qutebrowser.__file__)), '..')
        for arg in sys.argv[1:]:
            if arg.startswith('-'):
                # We only want to preserve options on a restart.
                args.append(arg)
        # Add all open pages so they get reopened.
        page_args = []
        for win in pages:
            page_args.extend(win)
            page_args.append('')
        if page_args:
            args.extend(page_args[:-1])
        log.destroy.debug("args: {}".format(args))
        log.destroy.debug("cwd: {}".format(cwd))
        # Open a new process and immediately shutdown the existing one
        if cwd is None:
            subprocess.Popen(args)
        else:
            subprocess.Popen(args, cwd=cwd)
        if shutdown:
            self.shutdown()

    @cmdutils.register(instance='app', split=False, debug=True)
    def debug_pyeval(self, s):
        """Evaluate a python string and display the results as a webpage.

        //

        We have this here rather in utils.debug so the context of eval makes
        more sense and because we don't want to import much stuff in the utils.

        Args:
            s: The string to evaluate.
        """
        try:
            r = eval(s)  # pylint: disable=eval-used
            out = repr(r)
        except Exception:  # pylint: disable=broad-except
            out = traceback.format_exc()
        qutescheme.pyeval_output = out
        tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                    window='current')
        tabbed_browser.openurl(QUrl('qute:pyeval'), newtab=True)

    @cmdutils.register(instance='app')
    def report(self):
        """Report a bug in qutebrowser."""
        pages = self._recover_pages()
        history = objreg.get('command-history')[-5:]
        objects = self.get_all_objects()
        self._crashdlg = crash.ReportDialog(pages, history, objects)
        self._crashdlg.show()

    def interrupt(self, signum, _frame):
        """Handler for signals to gracefully shutdown (SIGINT/SIGTERM).

        This calls self.shutdown and remaps the signal to call
        self.interrupt_forcefully the next time.
        """
        log.destroy.info("SIGINT/SIGTERM received, shutting down!")
        log.destroy.info("Do the same again to forcefully quit.")
        signal.signal(signal.SIGINT, self.interrupt_forcefully)
        signal.signal(signal.SIGTERM, self.interrupt_forcefully)
        # If we call shutdown directly here, we get a segfault.
        QTimer.singleShot(0, functools.partial(self.shutdown, 128 + signum))

    def interrupt_forcefully(self, signum, _frame):
        """Interrupt forcefully on the second SIGINT/SIGTERM request.

        This skips our shutdown routine and calls QApplication:exit instead.
        It then remaps the signals to call self.interrupt_really_forcefully the
        next time.
        """
        log.destroy.info("Forceful quit requested, goodbye cruel world!")
        log.destroy.info("Do the same again to quit with even more force.")
        signal.signal(signal.SIGINT, self.interrupt_really_forcefully)
        signal.signal(signal.SIGTERM, self.interrupt_really_forcefully)
        # This *should* work without a QTimer, but because of the trouble in
        # self.interrupt we're better safe than sorry.
        QTimer.singleShot(0, functools.partial(self.exit, 128 + signum))

    def interrupt_really_forcefully(self, signum, _frame):
        """Interrupt with even more force on the third SIGINT/SIGTERM request.

        This doesn't run *any* Qt cleanup and simply exits via Python.
        It will most likely lead to a segfault.
        """
        log.destroy.info("WHY ARE YOU DOING THIS TO ME? :(")
        sys.exit(128 + signum)

    @pyqtSlot()
    def shutdown(self, status=0):
        """Try to shutdown everything cleanly.

        For some reason lastWindowClosing sometimes seem to get emitted twice,
        so we make sure we only run once here.

        Args:
            status: The status code to exit with.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        log.destroy.debug("Shutting down with status {}...".format(status))
        deferrer = False
        for win_id in objreg.window_registry:
            prompter = objreg.get('prompter', None, scope='window',
                                  window=win_id)
            if prompter is not None and prompter.shutdown():
                deferrer = True
        if deferrer:
            # If shutdown was called while we were asking a question, we're in
            # a still sub-eventloop (which gets quitted now) and not in the
            # main one.
            # This means we need to defer the real shutdown to when we're back
            # in the real main event loop, or we'll get a segfault.
            log.destroy.debug("Deferring real shutdown because question was "
                              "active.")
            QTimer.singleShot(0, functools.partial(self._shutdown, status))
        else:
            # If we have no questions to shut down, we are already in the real
            # event loop, so we can shut down immediately.
            self._shutdown(status)

    def _shutdown(self, status):  # noqa
        """Second stage of shutdown."""
        # pylint: disable=too-many-branches, too-many-statements
        # FIXME refactor this
        # https://github.com/The-Compiler/qutebrowser/issues/113
        log.destroy.debug("Stage 2 of shutting down...")
        # Remove eventfilter
        try:
            log.destroy.debug("Removing eventfilter...")
            self.removeEventFilter(self._event_filter)
        except KeyError:
            pass
        # Close all tabs
        for win_id in objreg.window_registry:
            log.destroy.debug("Closing tabs in window {}...".format(win_id))
            tabbed_browser = objreg.get('tabbed-browser', scope='window',
                                        window=win_id)
            tabbed_browser.shutdown()
        # Save everything
        try:
            config_obj = objreg.get('config')
        except KeyError:
            log.destroy.debug("Config not initialized yet, so not saving "
                              "anything.")
        else:
            to_save = []
            if config.get('general', 'auto-save-config'):
                to_save.append(("config", config_obj.save))
                try:
                    key_config = objreg.get('key-config')
                except KeyError:
                    pass
                else:
                    to_save.append(("keyconfig", key_config.save))
            to_save += [("window geometry", self._save_geometry),
                        ("quickmarks", quickmarks.save)]
            try:
                command_history = objreg.get('command-history')
            except KeyError:
                pass
            else:
                to_save.append(("command history", command_history.save))
            try:
                state_config = objreg.get('state-config')
            except KeyError:
                pass
            else:
                to_save.append(("window geometry", state_config.save))
            try:
                cookie_jar = objreg.get('cookie-jar')
            except KeyError:
                pass
            else:
                to_save.append(("cookies", cookie_jar.save))
            for what, handler in to_save:
                log.destroy.debug("Saving {} (handler: {})".format(
                    what, handler.__qualname__))
                try:
                    handler()
                except AttributeError as e:
                    log.destroy.warning("Could not save {}.".format(what))
                    log.destroy.debug(e)
        # Re-enable faulthandler to stdout, then remove crash log
        log.destroy.debug("Deactiving crash log...")
        self._destroy_crashlogfile()
        # If we don't kill our custom handler here we might get segfaults
        log.destroy.debug("Deactiving message handler...")
        qInstallMessageHandler(None)
        # Now we can hopefully quit without segfaults
        log.destroy.debug("Deferring QApplication::exit...")
        # We use a singleshot timer to exit here to minimize the likelyhood of
        # segfaults.
        QTimer.singleShot(0, functools.partial(self.exit, status))

    def exit(self, status):
        """Extend QApplication::exit to log the event."""
        log.destroy.debug("Now calling QApplication::exit.")
        if self._args.debug_exit:
            print("Now logging late shutdown.", file=sys.stderr)
            debug.trace_lines(True)
        super().exit(status)
