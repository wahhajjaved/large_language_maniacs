# Created By: Virgil Dupras
# Created On: 2009-04-25
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import sys
import os.path as op

from PyQt5.QtCore import QTimer, QObject, QCoreApplication, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QFileDialog, QDialog, QMessageBox

from hscommon.trans import trget
from hscommon import desktop

from qtlib.about_box import AboutBox
from qtlib.recent import Recent
from qtlib.util import createActions
from qtlib.progress_window import ProgressWindow

from . import platform
from .result_window import ResultWindow
from .directories_dialog import DirectoriesDialog
from .problem_dialog import ProblemDialog
from .ignore_list_dialog import IgnoreListDialog
from .deletion_options import DeletionOptions

tr = trget('ui')

class DupeGuru(QObject):
    MODELCLASS = None
    LOGO_NAME = '<replace this>'
    NAME = '<replace this>'

    DETAILS_DIALOG_CLASS = None
    RESULT_WINDOW_CLASS = ResultWindow
    RESULT_MODEL_CLASS = None
    PREFERENCES_CLASS = None
    PREFERENCES_DIALOG_CLASS = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prefs = self.PREFERENCES_CLASS()
        self.prefs.load()
        self.model = self.MODELCLASS(view=self)
        self._setup()
        self.prefsChanged.emit(self.prefs)

    #--- Private
    def _setup(self):
        self._setupActions()
        self._update_options()
        self.recentResults = Recent(self, 'recentResults')
        self.recentResults.mustOpenItem.connect(self.model.load_from)
        self.directories_dialog = DirectoriesDialog(self)
        self.resultWindow = self.RESULT_WINDOW_CLASS(self.directories_dialog, self)
        self.progress_window = ProgressWindow(self.resultWindow, self.model.progress_window)
        self.details_dialog = self.DETAILS_DIALOG_CLASS(self.resultWindow, self)
        self.problemDialog = ProblemDialog(parent=self.resultWindow, model=self.model.problem_dialog)
        self.ignoreListDialog = IgnoreListDialog(parent=self.resultWindow, model=self.model.ignore_list_dialog)
        self.deletionOptions = DeletionOptions(parent=self.resultWindow, model=self.model.deletion_options)
        self.preferences_dialog = self.PREFERENCES_DIALOG_CLASS(self.resultWindow, self)
        self.about_box = AboutBox(self.resultWindow, self)

        self.directories_dialog.show()
        self.model.load()

        # The timer scheme is because if the nag is not shown before the application is
        # completely initialized, the nag will be shown before the app shows up in the task bar
        # In some circumstances, the nag is hidden by other window, which may make the user think
        # that the application haven't launched.
        QTimer.singleShot(0, self.finishedLaunching)
        QCoreApplication.instance().aboutToQuit.connect(self.application_will_terminate)

    def _setupActions(self):
        # Setup actions that are common to both the directory dialog and the results window.
        # (name, shortcut, icon, desc, func)
        ACTIONS = [
            ('actionQuit', 'Ctrl+Q', '', tr("Quit"), self.quitTriggered),
            ('actionPreferences', 'Ctrl+P', '', tr("Preferences"), self.preferencesTriggered),
            ('actionIgnoreList', '', '', tr("Ignore List"), self.ignoreListTriggered),
            ('actionShowHelp', 'F1', '', tr("dupeGuru Help"), self.showHelpTriggered),
            ('actionAbout', '', '', tr("About dupeGuru"), self.showAboutBoxTriggered),
            ('actionOpenDebugLog', '', '', tr("Open Debug Log"), self.openDebugLogTriggered),
        ]
        createActions(ACTIONS, self)

    def _update_options(self):
        self.model.scanner.mix_file_kind = self.prefs.mix_file_kind
        self.model.options['escape_filter_regexp'] = not self.prefs.use_regexp
        self.model.options['clean_empty_dirs'] = self.prefs.remove_empty_folders
        self.model.options['ignore_hardlink_matches'] = self.prefs.ignore_hardlink_matches
        self.model.options['copymove_dest_type'] = self.prefs.destination_type

    #--- Public
    def add_selected_to_ignore_list(self):
        self.model.add_selected_to_ignore_list()

    def remove_selected(self):
        self.model.remove_selected(self)

    def confirm(self, title, msg, default_button=QMessageBox.Yes):
        active = QApplication.activeWindow()
        buttons = QMessageBox.Yes | QMessageBox.No
        answer = QMessageBox.question(active, title, msg, buttons, default_button)
        return answer == QMessageBox.Yes

    def invokeCustomCommand(self):
        self.model.invoke_custom_command()

    def show_details(self):
        self.details_dialog.show()

    def showResultsWindow(self):
        self.resultWindow.show()

    #--- Signals
    willSavePrefs = pyqtSignal()
    prefsChanged = pyqtSignal(object)

    #--- Events
    def finishedLaunching(self):
        if sys.getfilesystemencoding() == 'ascii':
            # No need to localize this, it's a debugging message.
            msg = "Something is wrong with the way your system locale is set. If the files you're "\
                "scanning have accented letters, you'll probably get a crash. It is advised that "\
                "you set your system locale properly."
            QMessageBox.warning(self.directories_dialog, "Wrong Locale", msg)

    def application_will_terminate(self):
        self.willSavePrefs.emit()
        self.prefs.save()
        self.model.save()

    def ignoreListTriggered(self):
        self.model.ignore_list_dialog.show()

    def openDebugLogTriggered(self):
        debugLogPath = op.join(self.model.appdata, 'debug.log')
        desktop.open_path(debugLogPath)

    def preferencesTriggered(self):
        self.preferences_dialog.load()
        result = self.preferences_dialog.exec()
        if result == QDialog.Accepted:
            self.preferences_dialog.save()
            self.prefs.save()
            self._update_options()
            self.prefsChanged.emit(self.prefs)

    def quitTriggered(self):
        self.directories_dialog.close()

    def showAboutBoxTriggered(self):
        self.about_box.show()

    def showHelpTriggered(self):
        base_path = platform.HELP_PATH
        url = QUrl.fromLocalFile(op.abspath(op.join(base_path, 'index.html')))
        QDesktopServices.openUrl(url)

    #--- model --> view
    def get_default(self, key):
        return self.prefs.get_value(key)

    def set_default(self, key, value):
        self.prefs.set_value(key, value)

    def show_message(self, msg):
        window = QApplication.activeWindow()
        QMessageBox.information(window, '', msg)

    def ask_yes_no(self, prompt):
        return self.confirm('', prompt)

    def show_results_window(self):
        self.showResultsWindow()

    def show_problem_dialog(self):
        self.problemDialog.show()

    def select_dest_folder(self, prompt):
        flags = QFileDialog.ShowDirsOnly
        return QFileDialog.getExistingDirectory(self.resultWindow, prompt, '', flags)

    def select_dest_file(self, prompt, extension):
        files = tr("{} file (*.{})").format(extension.upper(), extension)
        destination, chosen_filter = QFileDialog.getSaveFileName(self.resultWindow, prompt, '', files)
        if not destination.endswith('.{}'.format(extension)):
            destination = '{}.{}'.format(destination, extension)
        return destination
