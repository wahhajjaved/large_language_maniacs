from __future__ import print_function

import sys
import sysconfig
import os
import logging
import errno
import shlex
import subprocess
import itertools
import socket
import xmlrpc.client
import json
import traceback
import concurrent.futures

from collections import namedtuple, deque
from xml.sax.saxutils import escape
from distutils import version

from typing import List, Dict, Any, Optional, Union, Tuple, NamedTuple

import future.moves.urllib.request
from future.moves import urllib

import requests
import pkg_resources

try:
    import docutils.core
except ImportError:
    docutils = None

from AnyQt.QtWidgets import (
    QWidget, QDialog, QLabel, QLineEdit, QTreeView, QHeaderView,
    QTextBrowser, QDialogButtonBox, QProgressDialog,
    QVBoxLayout, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QPushButton, QFormLayout, QHBoxLayout
)

from AnyQt.QtGui import (
    QStandardItemModel, QStandardItem, QPalette, QTextOption
)
from AnyQt.QtCore import (
    QSortFilterProxyModel, QItemSelectionModel,
    Qt, QObject, QMetaObject, QEvent, QSize, QTimer, QThread, Q_ARG,
    QSettings
)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ..gui.utils import message_warning, message_information, \
                        message_critical as message_error
from ..help.manager import get_dist_meta, trim
from ..utils.qtcompat import qunwrap
from .. import config

log = logging.getLogger(__name__)

#: An installable distribution from PyPi
Installable = namedtuple(
    "Installable",
    ["name",
     "version",
     "summary",
     "description",
     "package_url",
     "release_urls"]
)

#: An source/wheel/egg release for a distribution
ReleaseUrl = namedtuple(
    "ReleaseUrl",
    ["filename",
     "url",
     "size",
     "python_version",
     "package_type"
     ]
)

#: An available package
Available = NamedTuple(
    "Available", (
        ("installable", Installable),
    )
)
#: An installed package. Does not need to have a corresponding installable
#: entry (eg. only local or private distribution)
Installed = NamedTuple(
    "Installed", (
        ("installable", Optional[Installable]),
        ("local", pkg_resources.Distribution)
    )
)

#: An installable item/slot
Item = Union[Available, Installed]


def is_updatable(item):
    # type: (Item) -> bool
    if isinstance(item, Available):
        return False
    elif item.installable is None:
        return False
    else:
        inst, dist = item
        try:
            v1 = version.StrictVersion(dist.version)
            v2 = version.StrictVersion(inst.version)
        except ValueError:
            pass
        else:
            return v1 < v2

        return (version.LooseVersion(dist.version) <
                version.LooseVersion(inst.version))


class TristateCheckItemDelegate(QStyledItemDelegate):
    """
    A QStyledItemDelegate which properly toggles Qt.ItemIsTristate check
    state transitions on user interaction.
    """
    def editorEvent(self, event, model, option, index):
        flags = model.flags(index)
        if not flags & Qt.ItemIsUserCheckable or \
                not option.state & QStyle.State_Enabled or \
                not flags & Qt.ItemIsEnabled:
            return False

        checkstate = model.data(index, Qt.CheckStateRole)
        if checkstate is None:
            return False

        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        if event.type() in {QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                            QEvent.MouseButtonDblClick}:
            pos = event.pos()
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            rect = style.subElementRect(
                QStyle.SE_ItemViewItemCheckIndicator, opt, widget)

            if event.button() != Qt.LeftButton or not rect.contains(pos):
                return False

            if event.type() in {QEvent.MouseButtonPress,
                                QEvent.MouseButtonDblClick}:
                return True

        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
        else:
            return False

        if model.flags(index) & Qt.ItemIsTristate:
            checkstate = (checkstate + 1) % 3
        else:
            checkstate = \
                Qt.Unchecked if checkstate == Qt.Checked else Qt.Checked

        return model.setData(index, checkstate, Qt.CheckStateRole)


class AddonManagerWidget(QWidget):

    statechanged = Signal()

    def __init__(self, parent=None, **kwargs):
        super(AddonManagerWidget, self).__init__(parent, **kwargs)

        #: list of Available | Installed
        self.__items = []
        self.setLayout(QVBoxLayout())

        self.__header = QLabel(
            wordWrap=True,
            textFormat=Qt.RichText
        )
        self.__search = QLineEdit(
            placeholderText=self.tr("Filter")
        )
        self.tophlayout = topline = QHBoxLayout()
        topline.addWidget(self.__search)
        self.layout().addLayout(topline)

        self.__view = view = QTreeView(
            rootIsDecorated=False,
            editTriggers=QTreeView.NoEditTriggers,
            selectionMode=QTreeView.SingleSelection,
            alternatingRowColors=True
        )
        self.__view.setItemDelegateForColumn(0, TristateCheckItemDelegate())
        self.layout().addWidget(view)

        self.__model = model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["", "Name", "Version", "Action"])
        model.dataChanged.connect(self.__data_changed)
        proxy = QSortFilterProxyModel(
            filterKeyColumn=1,
            filterCaseSensitivity=Qt.CaseInsensitive
        )
        proxy.setSourceModel(model)
        self.__search.textChanged.connect(proxy.setFilterFixedString)

        view.setModel(proxy)
        view.selectionModel().selectionChanged.connect(
            self.__update_details
        )
        header = self.__view.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.__details = QTextBrowser(
            frameShape=QTextBrowser.NoFrame,
            readOnly=True,
            lineWrapMode=QTextBrowser.WidgetWidth,
            openExternalLinks=True,
        )

        self.__details.setWordWrapMode(QTextOption.WordWrap)
        palette = QPalette(self.palette())
        palette.setColor(QPalette.Base, Qt.transparent)
        self.__details.setPalette(palette)
        self.layout().addWidget(self.__details)

    def setItems(self, items):
        # type: (List[Item]) -> None
        self.__items = items
        model = self.__model
        model.setRowCount(0)

        for item in items:
            if isinstance(item, Installed):
                installed = True
                ins, dist = item
                name = dist.project_name
                summary = get_dist_meta(dist).get("Summary", "")
                version = ins.version if ins is not None else dist.version
            else:
                installed = False
                (ins,) = item
                dist = None
                name = ins.name
                summary = ins.summary
                version = ins.version

            updatable = is_updatable(item)

            item1 = QStandardItem()
            item1.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                           Qt.ItemIsUserCheckable |
                           (Qt.ItemIsTristate if updatable else 0))

            if installed and updatable:
                item1.setCheckState(Qt.PartiallyChecked)
            elif installed:
                item1.setCheckState(Qt.Checked)
            else:
                item1.setCheckState(Qt.Unchecked)
            item1.setData(item, Qt.UserRole)

            item2 = QStandardItem(name)
            item2.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item2.setToolTip(summary)
            item2.setData(item, Qt.UserRole)

            if updatable:
                version = "{} < {}".format(dist.version, ins.version)

            item3 = QStandardItem(version)
            item3.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            item4 = QStandardItem()
            item4.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            model.appendRow([item1, item2, item3, item4])

        model.sort(1)

        self.__view.resizeColumnToContents(0)
        self.__view.setColumnWidth(
            1, max(150, self.__view.sizeHintForColumn(1)))
        self.__view.setColumnWidth(
            2, max(150, self.__view.sizeHintForColumn(2)))

        if self.__items:
            self.__view.selectionModel().select(
                self.__view.model().index(0, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )

    def items(self):
        # type: () -> List[Item]
        return list(self.__items)

    def itemState(self):
        # type: () -> List['Action']
        steps = []
        for i in range(self.__model.rowCount()):
            modelitem = self.__model.item(i, 0)
            item = modelitem.data(Qt.UserRole)
            state = modelitem.checkState()
            if modelitem.flags() & Qt.ItemIsTristate and state == Qt.Checked:
                steps.append((Upgrade, item))
            elif isinstance(item, Available) and state == Qt.Checked:
                steps.append((Install, item))
            elif isinstance(item, Installed) and state == Qt.Unchecked:
                steps.append((Uninstall, item))

        return steps

    def setItemState(self, steps):
        # type: (List['Action']) -> None
        model = self.__model
        if model.rowCount() == 0:
            return

        for row in range(model.rowCount()):
            modelitem = model.item(row, 0)  # type: QStandardItem
            item = modelitem.data(Qt.UserRole)  # type: Item
            # Find the action command in the steps list for the item
            cmd = -1
            for cmd_, item_ in steps:
                if item == item_:
                    cmd = cmd_
                    break
            if isinstance(item, Available):
                modelitem.setCheckState(
                    Qt.Checked if cmd == Install else Qt.Unchecked
                )
            elif isinstance(item, Installed):
                if cmd == Upgrade:
                    modelitem.setCheckState(Qt.Checked)
                elif cmd == Uninstall:
                    modelitem.setCheckState(Qt.Unchecked)
                elif is_updatable(item):
                    modelitem.setCheckState(Qt.PartiallyChecked)
                else:
                    modelitem.setCheckState(Qt.Checked)
            else:
                assert False

    def __selected_row(self):
        indices = self.__view.selectedIndexes()
        if indices:
            proxy = self.__view.model()
            indices = [proxy.mapToSource(index) for index in indices]
            return indices[0].row()
        else:
            return -1

    def __data_changed(self, topleft, bottomright):
        rows = range(topleft.row(), bottomright.row() + 1)
        for i in rows:
            modelitem = self.__model.item(i, 0)
            actionitem = self.__model.item(i, 3)
            item = modelitem.data(Qt.UserRole)

            state = modelitem.checkState()
            flags = modelitem.flags()

            if flags & Qt.ItemIsTristate and state == Qt.Checked:
                actionitem.setText("Update")
            elif isinstance(item, Available) and state == Qt.Checked:
                actionitem.setText("Install")
            elif isinstance(item, Installed) and state == Qt.Unchecked:
                actionitem.setText("Uninstall")
            else:
                actionitem.setText("")
        self.statechanged.emit()

    def __update_details(self):
        index = self.__selected_row()
        if index == -1:
            self.__details.setText("")
        else:
            item = self.__model.item(index, 1)
            item = qunwrap(item.data(Qt.UserRole))
            assert isinstance(item, (Installed, Available))
            text = self._detailed_text(item)
            self.__details.setText(text)

    def _detailed_text(self, item):
        if isinstance(item, Installed):
            remote, dist = item
            if remote is None:
                description = get_dist_meta(dist).get("Description")
                description = description
            else:
                description = remote.description
        else:
            description = item[0].description

        if docutils is not None:
            try:
                html = docutils.core.publish_string(
                    trim(description),
                    writer_name="html",
                    settings_overrides={
                        "output-encoding": "utf-8",
#                         "embed-stylesheet": False,
#                         "stylesheet": [],
#                         "stylesheet_path": []
                    }
                ).decode("utf-8")

            except docutils.utils.SystemMessage:
                html = "<pre>{}<pre>".format(escape(description))
            except Exception:
                html = "<pre>{}<pre>".format(escape(description))
        else:
            html = "<pre>{}<pre>".format(escape(description))
        return html

    def sizeHint(self):
        return QSize(480, 420)


def method_queued(method, sig, conntype=Qt.QueuedConnection):
    name = method.__name__
    obj = method.__self__
    assert isinstance(obj, QObject)

    def call(*args):
        args = [Q_ARG(atype, arg) for atype, arg in zip(sig, args)]
        return QMetaObject.invokeMethod(obj, name, conntype, *args)

    return call


class AddonManagerDialog(QDialog):
    def __init__(self, parent=None, **kwargs):
        super(AddonManagerDialog, self).__init__(parent, **kwargs)
        self.setLayout(QVBoxLayout())

        self.addonwidget = AddonManagerWidget()
        self.addonwidget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.addonwidget)
        buttons = QDialogButtonBox(
            orientation=Qt.Horizontal,
            standardButtons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel,

        )
        addmore = QPushButton(
            "Add more...", toolTip="Add an add-on not listed below",
            autoDefault=False
        )
        self.addonwidget.tophlayout.addWidget(addmore)
        addmore.clicked.connect(self.__run_add_package_dialog)

        buttons.accepted.connect(self.__accepted)
        buttons.rejected.connect(self.reject)

        self.layout().addWidget(buttons)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        self.__progress = None  # type: QProgressDialog

        # The installer thread
        self.__thread = None
        # The installer object
        self.__installer = None

    @Slot(object)
    def setItems(self, items):
        # type: (List[Item]) -> None
        self.addonwidget.setItems(items)

    @Slot(object)
    def addInstallable(self, installable):
        # type: (Installable) -> None
        items = self.addonwidget.items()
        if installable.name in {item.installable.name for item in items
                                if item.installable is not None}:
            return
        new = installable_items([installable], list_installed_addons())
        state = self.addonwidget.itemState()
        self.addonwidget.setItems(items + new)
        self.addonwidget.setItemState(state)  # restore state

    def __run_add_package_dialog(self):
        dlg = QDialog(self, windowTitle="Add add-on by name")
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        vlayout = QVBoxLayout()
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        nameentry = QLineEdit(
            placeholderText="Package name",
            toolTip="Enter a package name as displayed on "
                    "PyPI (capitalization is not important)")
        nameentry.setMinimumWidth(250)
        form.addRow("Name:", nameentry)
        vlayout.addLayout(form)
        buttons = QDialogButtonBox(
            standardButtons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        okb = buttons.button(QDialogButtonBox.Ok)
        okb.setEnabled(False)
        okb.setText("Add")

        def changed(name):
            okb.setEnabled(bool(name))
        nameentry.textChanged.connect(changed)
        vlayout.addWidget(buttons)
        vlayout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        dlg.setLayout(vlayout)
        f = None

        def query():
            nonlocal f
            name = nameentry.text()
            f = self._executor.submit(pypi_json_query_project_meta, [name])
            okb.setDisabled(True)

            def ondone(f):
                error_text = ""
                error_details = ""
                try:
                    pkgs = f.result()
                except Exception:
                    log.error("Query error:", exc_info=True)
                    error_text = "Failed to query package index"
                    error_details = traceback.format_exc()
                    pkg = None
                else:
                    pkg = pkgs[0]
                    if pkg is None:
                        error_text = "'{}' not was not found".format(name)
                if pkg:
                    pkg = installable_from_json_response(pkg)
                    method_queued(self.addInstallable, (object,))(pkg)
                    method_queued(dlg.accept, ())()
                else:
                    method_queued(self.__show_error_for_query, (str, str)) \
                        (error_text, error_details)
                    method_queued(dlg.reject, ())()

            f.add_done_callback(ondone)

        buttons.accepted.connect(query)
        buttons.rejected.connect(dlg.reject)
        dlg.exec_()

    @Slot(str, str)
    def __show_error_for_query(self, text, error_details):
        message_error(text, title="Error", details=error_details)

    def progressDialog(self):
        if self.__progress is None:
            self.__progress = QProgressDialog(
                self,
                minimum=0, maximum=0,
                labelText=self.tr("Retrieving package list"),
                sizeGripEnabled=False,
                windowTitle="Progress"
            )
            self.__progress.setWindowModality(Qt.WindowModal)
            self.__progress.hide()
            self.__progress.canceled.connect(self.reject)

        return self.__progress

    def done(self, retcode):
        super(AddonManagerDialog, self).done(retcode)
        if self.__thread is not None:
            self.__thread.quit()
            self.__thread.wait(1000)

    def closeEvent(self, event):
        super(AddonManagerDialog, self).closeEvent(event)
        if self.__thread is not None:
            self.__thread.quit()
            self.__thread.wait(1000)

    def __accepted(self):
        steps = self.addonwidget.itemState()

        if steps:
            # Move all uninstall steps to the front
            steps = sorted(
                steps, key=lambda step: 0 if step[0] == Uninstall else 1
            )
            self.__installer = Installer(steps=steps)
            self.__thread = QThread(self)
            self.__thread.start()

            self.__installer.moveToThread(self.__thread)
            self.__installer.finished.connect(self.__on_installer_finished)
            self.__installer.error.connect(self.__on_installer_error)

            progress = self.progressDialog()

            self.__installer.installStatusChanged.connect(progress.setLabelText)
            progress.show()
            progress.setLabelText("Installing")

            self.__installer.start()

        else:
            self.accept()

    def __on_installer_error(self, command, pkg, retcode, output):
        message_error(
            "An error occurred while running a subprocess", title="Error",
            informative_text="{} exited with non zero status.".format(command),
            details="".join(output),
            parent=self
        )
        self.reject()

    def __on_installer_finished(self):
        message_information(
            "Please restart the application for changes to take effect.",
            parent=self)
        self.accept()


class SafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, use_datetime=0, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        super(SafeTransport, self).__init__(use_datetime)
        self._timeout = timeout

    def make_connection(self, *args, **kwargs):
        conn = super(SafeTransport, self).make_connection(*args, **kwargs)
        conn.timeout = self._timeout
        return conn


PYPI_API_JSON = "https://pypi.org/pypi/{name}/json"
PYPI_API_XMLRPC = "https://pypi.org/pypi"


def pypi_search(spec, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
    """
    Search package distributions available on PyPi using PyPiXMLRPC.
    """
    pypi = xmlrpc.client.ServerProxy(
        PYPI_API_XMLRPC,
        transport=SafeTransport(timeout=timeout)
    )
    # pypi search
    spec = {key: [v] if isinstance(v, str) else v
            for key, v in spec.items()}
    _spec = {}
    for key, values in spec.items():
        if isinstance(values, str):
            _spec[key] = values
        elif key == "keywords" and len(values) > 1:
            _spec[key] = [values[0]]
        else:
            _spec[key] = values
    addons = pypi.search(_spec, 'and')
    addons = [item["name"] for item in addons if "name" in item]
    metas_ = pypi_json_query_project_meta(addons)

    # post filter on multiple keywords
    def matches(meta, spec):
        # type: (Dict[str, Any], Dict[str, List[str]]) -> bool
        def match_list(meta, query):
            # type: (List[str], List[str]) -> bool
            meta = {s.casefold() for s in meta}
            return all(q.casefold() in meta for q in query)

        def match_string(meta, query):
            # type: (str, List[str]) -> bool
            meta = meta.casefold()
            return all(q.casefold() in meta for q in query)

        for key, query in spec.items():
            value = meta.get(key, None)
            if isinstance(value, str) and not match_string(value, query):
                return False
            elif isinstance(value, list) and not match_list(value, query):
                return False
        return True

    metas = []
    for meta in metas_:
        if meta is not None:
            if matches(meta["info"], spec):
                metas.append(meta)
    return [installable_from_json_response(m) for m in metas]


def pypi_json_query_project_meta(projects, session=None):
    # type: (List[str], Optional[requests.Session]) -> List[Optional[dict]]
    """
    Parameters
    ----------
    projects : List[str]
        List of project names to query
    session : Optional[requests.Session]
    """
    if session is None:
        session = requests.Session()

    rval = []
    for name in projects:
        r = session.get(PYPI_API_JSON.format(name=name))
        if r.status_code != 200:
            rval.append(None)
        else:
            try:
                meta = r.json()
            except json.JSONDecodeError:
                rval.append(None)
            else:
                try:
                    # sanity check
                    installable_from_json_response(meta)
                except (TypeError, KeyError):
                    rval.append(None)
                else:
                    rval.append(meta)
    return rval


def installable_from_json_response(meta):
    # type: (dict) -> Installable
    """
    Extract relevant project meta data from a PyPiJSONRPC response

    Parameters
    ----------
    meta : dict
        JSON response decoded into python native dict.

    Returns
    -------
    installable : Installable
    """
    info = meta["info"]
    name = info["name"]
    version = info.get("version", "0")
    summary = info.get("summary", "")
    description = info.get("description", "")
    package_url = info.get("package_url", "")

    return Installable(name, version, summary, description, package_url, [])


def list_pypi_addons():
    """
    List add-ons available on pypi.
    """
    return pypi_search(config.default.addon_pypi_search_spec(), timeout=20)


def list_installed_addons():
    return [ep.dist for ep in config.default.addon_entry_points()]


def installable_items(pypipackages, installed=[]):
    """
    Return a list of installable items.

    Parameters
    ----------
    pypipackages : list of Installable
    installed : list of pkg_resources.Distribution
    """

    dists = {dist.project_name: dist for dist in installed}
    packages = {pkg.name: pkg for pkg in pypipackages}

    # For every pypi available distribution not listed by
    # `installed`, check if it is actually already installed.
    ws = pkg_resources.WorkingSet()
    for pkg_name in set(packages.keys()).difference(set(dists.keys())):
        try:
            d = ws.find(pkg_resources.Requirement.parse(pkg_name))
        except pkg_resources.VersionConflict:
            pass
        except ValueError:
            # Requirements.parse error ?
            pass
        else:
            if d is not None:
                dists[d.project_name] = d

    project_names = unique(
        itertools.chain(packages.keys(), dists.keys())
    )

    items = []
    for name in project_names:
        if name in dists and name in packages:
            item = Installed(packages[name], dists[name])
        elif name in dists:
            item = Installed(None, dists[name])
        elif name in packages:
            item = Available(packages[name])
        else:
            assert False
        items.append(item)
    return items


def unique(iterable):
    seen = set()

    def observed(el):
        observed = el in seen
        seen.add(el)
        return observed

    return (el for el in iterable if not observed(el))


def have_install_permissions():
    """Check if we can create a file in the site-packages folder.
    This works on a Win7 miniconda install, where os.access did not. """
    try:
        fn = os.path.join(sysconfig.get_path("purelib"), "test_write_" + str(os.getpid()))
        with open(fn, "w"):
            pass
        os.remove(fn)
        return True
    except PermissionError:
        return False


def _env_with_proxies():
    """
    Return system environment with proxies obtained from urllib so that
    they can be used with pip.
    """
    proxies = urllib.request.getproxies()
    env = dict(os.environ)
    if "http" in proxies:
        env["HTTP_PROXY"] = proxies["http"]
    if "https" in proxies:
        env["HTTPS_PROXY"] = proxies["https"]
    return env


Install, Upgrade, Uninstall = 1, 2, 3

Action = Tuple[int, Item]


class CommandFailed(Exception):
    def __init__(self, cmd, retcode, output):
        if not isinstance(cmd, str):
            cmd = " ".join(map(shlex.quote, cmd))
        self.cmd = cmd
        self.retcode = retcode
        self.output = output


class Installer(QObject):
    installStatusChanged = Signal(str)
    started = Signal()
    finished = Signal()
    error = Signal(str, object, int, list)

    def __init__(self, parent=None, steps=[]):
        QObject.__init__(self, parent)
        self.__interupt = False
        self.__queue = deque(steps)
        self.__statusMessage = ""
        self.pip = PipInstaller()
        self.conda = CondaInstaller()

    def start(self):
        QTimer.singleShot(0, self._next)

    def interupt(self):
        self.__interupt = True

    def setStatusMessage(self, message):
        if self.__statusMessage != message:
            self.__statusMessage = message
            self.installStatusChanged.emit(message)

    @Slot()
    def _next(self):
        command, pkg = self.__queue.popleft()

        try:
            if command == Install:
                self.setStatusMessage(
                    "Installing {}".format(pkg.installable.name))
                if self.conda:
                    self.conda.install(pkg.installable, raise_on_fail=False)
                self.pip.install(pkg.installable)
            elif command == Upgrade:
                self.setStatusMessage(
                    "Upgrading {}".format(pkg.installable.name))
                if self.conda:
                    self.conda.upgrade(pkg.installable, raise_on_fail=False)
                self.pip.upgrade(pkg.installable)
            elif command == Uninstall:
                self.setStatusMessage(
                    "Uninstalling {}".format(pkg.local.project_name))
                if self.conda:
                    try:
                        self.conda.uninstall(pkg.local, raise_on_fail=True)
                    except CommandFailed:
                        self.pip.uninstall(pkg.local)
                else:
                    self.pip.uninstall(pkg.local)
        except CommandFailed as ex:
            self.error.emit(
                "Command failed: python {}".format(ex.cmd),
                pkg, ex.retcode, ex.output
            )
            return

        if self.__queue:
            QTimer.singleShot(0, self._next)
        else:
            self.finished.emit()


class PipInstaller:

    def __init__(self):
        arguments = QSettings().value('add-ons/pip-install-arguments', '', type=str)
        self.arguments = shlex.split(arguments)

    def install(self, pkg):
        cmd = ["python", "-m", "pip", "install"]
        cmd.extend(self.arguments)
        if pkg.package_url.startswith("http://"):
            cmd.append(pkg.name)
        else:
            # Package url is path to the (local) wheel
            cmd.append(pkg.package_url)

        run_command(cmd)

    def upgrade(self, package):
        # This is done in two steps to avoid upgrading
        # all of the dependencies - faster
        self.upgrade_no_deps(package)
        self.install(package)

    def upgrade_no_deps(self, package):
        cmd = ["python", "-m", "pip", "install", "--upgrade", "--no-deps"]
        cmd.extend(self.arguments)
        cmd.append(package.name)

        run_command(cmd)

    def uninstall(self, dist):
        cmd = ["python", "-m", "pip", "uninstall", "--yes", dist.project_name]
        run_command(cmd)


class CondaInstaller:
    def __init__(self):
        enabled = QSettings().value('add-ons/allow-conda-experimental',
                                    False, type=bool)
        if enabled:
            self.conda = self._find_conda()
        else:
            self.conda = None

    def _find_conda(self):
        executable = sys.executable
        bin = os.path.dirname(executable)

        # posix
        conda = os.path.join(bin, "conda")
        if os.path.exists(conda):
            return conda

        # windows
        conda = os.path.join(bin, "Scripts", "conda.bat")
        if os.path.exists(conda):
            # "activate" conda environment orange is running in
            os.environ["CONDA_PREFIX"] = bin
            os.environ["CONDA_DEFAULT_ENV"] = bin
            return conda

    def install(self, pkg, raise_on_fail=False):
        cmd = [self.conda, "install", "--yes", "--quiet",
               self._normalize(pkg.name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def upgrade(self, pkg, raise_on_fail=False):
        cmd = [self.conda, "upgrade", "--yes", "--quiet",
               self._normalize(pkg.name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def uninstall(self, dist, raise_on_fail=False):
        cmd = [self.conda, "uninstall", "--yes",
               self._normalize(dist.project_name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def _normalize(self, name):
        # Conda 4.3.30 is inconsistent, upgrade command is case sensitive
        # while install and uninstall are not. We assume that all conda
        # package names are lowercase which fixes the problems (for now)
        return name.lower()

    def __bool__(self):
        return bool(self.conda)


def run_command(command, raise_on_fail=True):
    """Run command in a subprocess.

    Return `process` return code and output once it completes.
    """
    log.info("Running %s", " ".join(command))

    if command[0] == "python":
        process = python_process(command[1:])
    else:
        process = create_process(command)

    output = []
    while process.poll() is None:
        try:
            line = process.stdout.readline()
        except IOError as ex:
            if ex.errno != errno.EINTR:
                raise
        else:
            output.append(line)
            print(line, end="")
    # Read remaining output if any
    line = process.stdout.read()
    if line:
        output.append(line)
        print(line, end="")

    if process.returncode != 0:
        log.info("Command %s failed with %s",
                 " ".join(command), process.returncode)
        log.debug("Output:\n%s", "\n".join(output))
        if raise_on_fail:
            raise CommandFailed(command, process.returncode, output)

    return process.returncode, output


def python_process(args, script_name=None, **kwargs):
    """
    Run a `sys.executable` in a subprocess with `args`.
    """
    executable = sys.executable
    if os.name == "nt" and os.path.basename(executable) == "pythonw.exe":
        # Don't run the script with a 'gui' (detached) process.
        dirname = os.path.dirname(executable)
        executable = os.path.join(dirname, "python.exe")

    if script_name is not None:
        script = script_name
    else:
        script = executable

    return create_process(
        [script] + args,
        executable=executable
    )


def create_process(cmd, executable=None, **kwargs):
    if hasattr(subprocess, "STARTUPINFO"):
        # do not open a new console window for command on windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo

    return subprocess.Popen(
        cmd,
        executable=executable,
        cwd=None,
        env=_env_with_proxies(),
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        bufsize=-1,
        universal_newlines=True,
        **kwargs
    )
