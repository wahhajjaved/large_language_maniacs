#!/usr/bin/env python3

# source: https://nikolak.com/pyqt-qt-designer-getting-started/

import sys

from PyQt5.QtCore import pyqtSlot

from PyQt5 import QtWidgets, QtCore, QtGui
from terminal_advisor.gui.qt import main_window
from terminal_advisor.gui.threads import Refresh, Run, Search
from terminal_advisor.gui import settings


class GUIApp(QtWidgets.QMainWindow, main_window.Ui_MainWindow):

    def __init__(self, advisor, config):
        super(self.__class__, self).__init__()
        self.advisor = advisor
        self.config = config
        self.setupUi(self)
        self.settings_form = None
        self.run_thread = None
        self.refresh_thread = None
        self.search_thread = None
        self.update_window()

        # connections
        self.button_refresh.clicked.connect(self.refresh)
        self.button_run.clicked.connect(self.run)

        self.line_edit_advisee.editingFinished.connect(self.advisee_search)

        self.action_settings.triggered.connect(self.menu_settings)
        self.button_settings.clicked.connect(self.menu_settings)

        self.list_advisees.currentItemChanged.connect(self.update_window)

    @pyqtSlot()
    def update_window(self):
        # status bar
        status = 'Logged out' if self.advisor.logged_in else 'Logged in as %s' % self.advisor.username
        self.status_bar.showMessage(status)

        # button refresh
        enabled = self.advisor.logged_in
        self.button_refresh.setEnabled(enabled)

        # button run
        enabled = self.list_advisees.currentItem() is not None
        self.button_run.setEnabled(enabled)

    @staticmethod
    def show_busy(title, message):
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setInformativeText(message)
        msg.setStandardButtons(QtWidgets.QMessageBox.Cancel)
        msg.setWindowTitle(title)
        msg.exec_()


    @pyqtSlot()
    def menu_settings(self):
        self.settings_form = settings.GUIApp(self.advisor, self.config)
        self.settings_form.login_change.connect(self.update_window)
        self.settings_form.settings_close.connect(self.show)
        self.settings_form.show()
        self.hide()

    @pyqtSlot()
    def advisee_search(self):
        search_term = self.line_edit_advisee.text()
        self.search_thread = Search(self.advisor, search_term)
        self.search_thread.done.connect(self.refresh_update)
        self.search_thread.start()

    @pyqtSlot()
    def refresh(self):
        self.refresh_thread = Refresh(self.advisor)
        self.refresh_thread.done.connect(self.refresh_update)
        self.refresh_thread.start()
        self.show_busy('Refreshing', 'Refreshing...')

    @pyqtSlot(list)
    def refresh_update(self, advisees):
        self.list_advisees.clear()
        self.list_advisees.addItems(advisees)


    @pyqtSlot()
    def run(self):
        action = str(self.combo_action.currentText())
        advisee = self.list_advisees.currentItem().text()
        self.run_thread = Run(self.advisor, action, advisee)
        self.run_thread.done.connect(self.run_done)
        self.run_thread.start()

    @pyqtSlot(str)
    def run_done(self, msg):
        pass


def main(advisor, no_login, config):
    if advisor.login_ready() and not no_login:
        advisor.login()
    app = QtWidgets.QApplication(sys.argv)
    form = GUIApp(advisor, config)
    form.show()
    sys.exit(app.exec_())


