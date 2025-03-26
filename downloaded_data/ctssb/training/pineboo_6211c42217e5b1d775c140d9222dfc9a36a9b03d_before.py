# # -*- coding: utf-8 -*-
from PyQt5 import QtWidgets, QtCore, QtGui, Qt, QtXml
from PyQt5.Qt import QMessageBox

from importlib import import_module

from pineboolib.fllegacy.fldatatable import FLDataTable

from pineboolib.plugins.dgi.dgi_schema import dgi_schema
from pineboolib import decorators
import pineboolib

import datetime
import sys
import re
import logging


logger = logging.getLogger(__name__)


def resolveObject(name):
    mod_ = import_module(__name__)
    ret_ = getattr(mod_, name, None)
    return ret_


class dgi_qt(dgi_schema):

    def __init__(self):
        super(dgi_qt, self).__init__()  # desktopEnabled y mlDefault a True
        self._name = "qt"
        self._alias = "Qt5"

    def __getattr__(self, name):
        return resolveObject(name)


class QWidget(Qt.QWidget):

    def child(self, name):
        return self.findChild(QtWidgets.QWidget, name)


class QTreeWidget(QtWidgets.QTreeWidget):
    pass


class QTreeWidgetItem(QtWidgets.QTreeWidgetItem):
    pass


class QTreeWidgetItemIterator(QtWidgets.QTreeWidgetItemIterator):
    pass


class FLDataTable(FLDataTable):
    pass


class FLTextEditOutput(QtWidgets.QPlainTextEdit):
    oldStdout = None
    oldStderr = None

    def __init__(self, parent):
        super(FLTextEditOutput, self).__init__(parent)

        self.oldStdout = sys.stdout
        self.oldStderr = sys.stderr
        sys.stdout = self
        sys.stderr = self

    def write(self, txt):
        self.oldStdout.write(txt)
        self.appendPlainText(str(txt))


class QToolBar(QtWidgets.QToolBar):
    _label = None

    def setLabel(self, l):
        self._label = l

    def getLabel(self):
        return self._label

    label = property(getLabel, setLabel)


class QSignalMapper(QtCore.QSignalMapper):

    def __init__(self, parent, name):
        super(QSignalMapper, self).__init__(parent)
        self.setObjectName(name)


class FLLineEdit(QtWidgets.QLineEdit):
    logger = logging.getLogger(__name__)
    _tipo = None
    partDecimal = 0
    partInteger = 0
    _maxValue = None
    autoSelect = True
    _name = None
    _longitudMax = None
    _parent = None
    _last_text = None
    _formating = False

    lostFocus = QtCore.pyqtSignal()

    def __init__(self, parent, name=None):
        super(FLLineEdit, self).__init__(parent)
        self._name = name
        if isinstance(parent.fieldName_, str):
            self._fieldName = parent.fieldName_
            self._tipo = parent.cursor_.metadata().fieldType(self._fieldName)
            self.partDecimal = 0
            self.autoSelect = True
            self.partInteger = parent.cursor_.metadata().field(self._fieldName).partInteger()
            self._longitudMax = parent.cursor_.metadata().field(self._fieldName).length()
            self._parent = parent

            if self._tipo in ("int", "uint", "double"):
                self.setAlignment(QtCore.Qt.AlignRight)
            
            

    def setText(self, text_, check_focus=True):
        from pineboolib.pncontrolsfactory import aqApp
        text_ = str(text_)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setText" % self._parent.objectName(), text_)
        else:
            if check_focus:
                
                if text_ in ("", None) or self.hasFocus():
                    super(FLLineEdit, self).setText(text_)
                    return
            
            ok = False
            s = text_
            minus = False
            
            if self._tipo == "double":
                if s[0] == "-":
                    minus = True
                    s = s[1:]
                if aqApp.commaSeparator() == ",":
                    s = s.replace(".", ",")
                        
                    
                val, ok = aqApp.localeSystem().toDouble(s)
                if ok:
                    s = aqApp.localeSystem().toString(val,'f',self.partDecimal)
                if minus:
                    s = "-%s" % s
                
            elif self._tipo in ("int"):
                val, ok = aqApp.localeSystem().toInt(s)
                if ok:
                    s = aqApp.localeSystem().toString(val)
            
            elif self._tipo in ("uint"):
                val, ok = aqApp.localeSystem().toUInt(s)
                if ok:
                    s = aqApp.localeSystem().toString(val)
                    
            super(FLLineEdit, self).setText(s)    
                        
        
            
    

    def text(self):
        from pineboolib.pncontrolsfactory import aqApp
        text_ = super(FLLineEdit, self).text()
        if text_ == "":
            return text_
        
        ok = False
        minus = False
        
        if self._tipo == "double":
            if text_[0] == "-":
                minus = True
                text_ = text_[1:]
            
            val, ok = aqApp.localeSystem().toDouble(text_)
            if ok:
                text_ = str(val)
            
                    
            if minus:
                text_ = "-%s" % text_
        
        elif self._tipo == "uint":
            val, ok = aqApp.localeSystem().toUInt(text_)                
            if ok:
                text_ = str(val)
        
        elif self._tipo == "int":
            val, ok = aqApp.localeSystem().toInt(text_)
                
            if ok:
                text_ = str(val)
        
        return text_
    
    def setMaxValue(self, max_value):
        self._maxValue = max_value
    
    
    def focusOutEvent(self, f):
        
        from pineboolib.pncontrolsfactory import aqApp
        if self._tipo in ("double","int","uint"):
            text_ = super(FLLineEdit, self).text()
            
            if self._tipo == "double":
                                    
                val, ok = aqApp.localeSystem().toDouble(text_)
                
                if ok:
                    text_ = aqApp.localeSystem().toString(val,'f',self.partDecimal)
                super(FLLineEdit, self).setText(text_)
            else:
                
                self.setText(text_)
        super(FLLineEdit, self).focusOutEvent(f)
    
    def focusInEvent(self, f):
        if self.isReadOnly():
            return
        
        from pineboolib.pncontrolsfactory import aqApp
        if self._tipo in ("double","int","uint"):
            self.blockSignals(True)
            s= self.text()
            if self._tipo is ("double"):
                s = aqApp.localeSystem().toString(float(s),'f',self.partDecimal)
                if aqApp.commaSeparator() == ",":
                    s = s.replace(".", "")
                else:
                    s = s.replace(",", "")
                    
            v = self.validator()
            if v:
                pos = 0
                v.validate(s, pos)
            
            super(FLLineEdit, self).setText(s)
            self.blockSignals(False)
        
        if self.autoSelect and not self.selectedText() and not self.isReadOnly():
            self.selectAll()
        
        super(FLLineEdit, self).focusInEvent(f)
        

        


class QPushButton(QtWidgets.QPushButton):

    def __init__(self, *args, **kwargs):
        super(QPushButton, self).__init__(*args, **kwargs)

    @property
    def pixmap(self):
        return self.icon()

    @property
    def enabled(self):
        return self.getEnabled()

    @enabled.setter
    def enabled(self, s):
        return self.setEnabled(s)

    @pixmap.setter
    def pixmap(self, value):
        return self.setIcon(value)

    def setPixmap(self, value):
        return self.setIcon(value)

    def getToggleButton(self):
        return self.isCheckable()

    def setToggleButton(self, v):
        return self.setCheckable(v)

    def getOn(self):
        return self.isChecked()

    def setOn(self, value):
        self.setChecked(value)

    toggleButton = property(getToggleButton, setToggleButton)
    on = property(getOn, setOn)


class FLPixmapView(QtWidgets.QScrollArea):
    frame_ = None
    scrollView = None
    autoScaled_ = None
    path_ = None
    pixmap_ = None
    pixmapView_ = None
    lay_ = None
    gB_ = None
    _parent = None

    def __init__(self, parent):
        super(FLPixmapView, self).__init__(parent)
        self.autoScaled_ = False
        self.lay_ = QtWidgets.QHBoxLayout(self)
        self.lay_.setContentsMargins(0, 2, 0, 2)
        self.pixmap_ = QtGui.QPixmap()
        self.pixmapView_ = QLabel(self)
        self.lay_.addWidget(self.pixmapView_)
        self.pixmapView_.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignCenter)
        self.pixmapView_.installEventFilter(self)
        self.setStyleSheet("QScrollArea { border: 1px solid darkgray; border-radius: 3px; }")
        self._parent = parent

    def setPixmap(self, pix):
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setPixmap" % self._parent.objectName(
            ), self._parent.cursor_.valueBuffer(self._parent.fieldName_))
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.pixmap_ = pix

        self.pixmapView_.clear()
        self.pixmapView_.setPixmap(self.pixmap_)
        self.repaint()
        QtWidgets.QApplication.restoreOverrideCursor()

    def eventFilter(self, obj, ev):

        if isinstance(obj, QLabel) and isinstance(ev, QtGui.QResizeEvent):
            self.resizeContents()

        return super(FLPixmapView, self).eventFilter(obj, ev)

    def resizeContents(self):

        if self.pixmap_.isNull():
            return

        new_pix = self.pixmap_
        if self.autoScaled_:
            if self.pixmap_.height() > self.pixmapView_.height() or self.pixmap_.width() > self.pixmapView_.width():
                new_pix = self.pixmap_.scaled(self.pixmapView_.size(), QtCore.Qt.KeepAspectRatio)

            elif self.pixmap_.height() < self.pixmapView_.height() or self.pixmap_.width() < self.pixmapView_.width():
                new_pix = self.pixmap_.scaled(self.pixmapView_.size(), QtCore.Qt.KeepAspectRatio)

        self.pixmapView_.clear()
        self.pixmapView_.setPixmap(new_pix)

    def previewUrl(self, url):
        u = QtCore.QUrl(url)
        if u.isLocalFile():
            path = u.path()

        if not path == self.path_:
            self.path_ = path
            img = QtGui.QImage(self.path_)

            if img is None:
                return

            pix = QtGui.QPixmap()
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            pix.convertFromImage(img)
            QtWidgets.QApplication.restoreOverrideCursor()

            if pix is not None:
                self.setPixmap(pix)

    def clear(self):
        self.pixmapView_.clear()

    def pixmap(self):
        return self.pixmap_

    def setAutoScaled(self, autoScaled):
        self.autoScaled_ = autoScaled


class QLayoutWidget(QtWidgets.QWidget):
    pass


class QGroupBox(QtWidgets.QGroupBox):

    def __init__(self, *args, **kwargs):
        super(QGroupBox, self).__init__(*args, **kwargs)

    def setLineWidth(self, width):
        self.setContentsMargins(width, width, width, width)

    @property
    def selectedId(self):
        return 0

    @decorators.NotImplementedWarn
    def setShown(self, b):
        pass

    def __setattr__(self, name, value):
        if name == "title":
            self.setTitle(str(value))
        else:
            super(QGroupBox, self).__setattr__(name, value)


class QAction(QtWidgets.QAction):

    activated = QtCore.pyqtSignal()
    _menuText = None
    _objectName = None

    def __init__(self, parent=None):
        super(QAction, self).__init__(parent)
        self.triggered.connect(self.send_activated)
        self._name = None
        self._menuText = None

    def send_activated(self, b=None):
        self.activated.emit()

    def getName(self):
        return self.objectName()

    def setName(self, n):
        self.setObjectName(n)

    def getMenuText(self):
        return self._menuText

    def setMenuText(self, t):
        self._menuText = t

    name = property(getName, setName)
    menuText = property(getMenuText, setMenuText)


class ProgressDialog(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(ProgressDialog, self).__init__(*args, **kwargs)
        self.title = "Untitled"
        self.step = 0
        self.steps = 100

    def __getattr__(self, name):
        return DefFun(self, name)

    def setup(self, title, steps):
        self.title = title
        self.step = 0
        self.steps = steps
        self.setWindowTitle("%s - %d/%d" % (self.title, self.step, self.steps))
        self.setWindowModality(QtCore.Qt.ApplicationModal)

    def setProgress(self, step):
        self.step = step
        self.setWindowTitle("%s - %d/%d" % (self.title, self.step, self.steps))
        if step > 0:
            self.show()
        self.update()
        QtCore.QCoreApplication.processEvents(
            QtCore.QEventLoop.ExcludeUserInputEvents)


class QLabel(QtWidgets.QLabel):

    @QtCore.pyqtProperty(str)
    def text(self):
        return self.text()

    @text.setter
    def text(self, v):
        if not isinstance(v, str):
            v = str(v)
        self.setText(v)

    def setText(self, text):
        if not isinstance(text, str):
            text = str(text)
        super(QLabel, self).setText(text)

    def setPixmap(self, pix):

        if isinstance(pix, QIcon):
            pix = pix.pixmap(32, 32)
        super(QLabel, self).setPixmap(pix)

    @QtCore.pyqtSlot(bool)
    def setShown(self, b):
        self.setVisible(b)
    
    def getAlign(self):
        return self.alignment()
    
    def setAlign(self, alignment_):
        self.setAlignment(alignment_)
        
    alignment = property(getAlign, setAlign)


class QListWidgetItem(QtWidgets.QListWidgetItem):
    pass


class QListViewWidget(QtWidgets.QListWidget):
    pass


class QListView(QtWidgets.QListView):

    _model = None

    def __init__(self, *args, **kwargs):
        super(QListView, self).__init__(*args, **kwargs)

        self._model = QtGui.QStandardItemModel(self)

    def addItem(self, item):
        it = QtGui.QStandardItem(item)
        self._model.appendRow(it)
        self.setModel(self._model)

    @decorators.Deprecated
    def setItemMargin(self, margin):
        pass

    @decorators.NotImplementedWarn
    def setClickable(self, c):
        pass

    @decorators.NotImplementedWarn
    def setResizable(self, r):
        pass

    @decorators.NotImplementedWarn
    def setHeaderLabel(self, l):
        pass

    def clear(self):
        self._model = None
        self._model = QtGui.QStandardItemModel(self)


"""
class QActionGroup(Qt.QActionGroup):

    _name = None
    _text = None
    _menuText = None
    activated = QtCore.pyqtSignal()

    def __init__(self, parent, name=None):
        super(QActionGroup, self).__init__(parent)
        self.triggered.connect(self.send_activated)
        self._name = name

    def addTo(self, menu):
        for ac in self.actions():
            action_ = menu.addAction(ac.icon(), ac.menuText, ac.trigger)

    def addSeparator(self):
        ac_ = QAction()
        ac_.setSeparator(True)
        self.addAction(ac_)

    def getName(self):
        return self._name

    def setName(self, n):
        self._name = n

    def getText(self):
        return self._text

    def setText(self, t):
        self._text = t

    def getMenuText(self):
        return self._menuText

    def setMenuText(self, t):
        self._menuText = t

    def send_activated(self, b=None):
        self.activated.emit()

    name = property(getName, setName)
    text = property(getText, setText)
    menuText = property(getMenuText, setMenuText)
"""
QActionGroup = QtWidgets.QActionGroup


class QDomDocument(QtXml.QDomDocument):
    pass


class QDateEdit(QtWidgets.QDateEdit):

    _parent = None
    _date = None
    separator_ = None

    def __init__(self, parent, name=None):
        super(QDateEdit, self).__init__(parent)
        super(QDateEdit, self).setDisplayFormat("dd-MM-yyyy")
        if name:
            self.setObjectName(name)
        self.setSeparator("-")
        self._parent = parent
        self.date_ = super(QDateEdit, self).date().toString(QtCore.Qt.ISODate)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_CreateWidget" % self._parent.objectName(), "QDateEdit")

    def getDate(self):
        ret = super(QDateEdit, self).date().toString(QtCore.Qt.ISODate)
        if ret != "2000-01-01":
            return ret
        else:
            return None

    def setDate(self, v):
        if not isinstance(v, str):
            if hasattr(v, "toString"):
                v = v.toString("yyyy%sMM%sdd" % (self.separator(), self.separator()))
            else:
                v = str(v)

        date = QtCore.QDate.fromString(v[:10], "yyyy-MM-dd")
        super(QDateEdit, self).setDate(date)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setDate" % self._parent.objectName(), "QDateEdit")

    date = property(getDate, setDate)

    @decorators.NotImplementedWarn
    def setAutoAdvance(self, b):
        pass

    def setSeparator(self, c):
        self.separator_ = c
        self.setDisplayFormat("dd%sMM%syyyy" % (self.separator(), self.separator()))

    def separator(self):
        return self.separator_

    def __getattr__(self, name):
        if name == "date":
            return super(QDateEdit, self).date().toString(QtCore.Qt.ISODate)


class FLDateEdit(QDateEdit):

    valueChanged = QtCore.pyqtSignal()
    DMY = "dd-MM-yyyy"
    _parent = None

    def __init__(self, parent, name):
        super(FLDateEdit, self).__init__(parent, name)
        self.setMinimumWidth(90)
        self.setMaximumWidth(90)
        self._parent = parent

    def setOrder(self, order):
        self.setDisplayFormat(order)

    def getDate(self):
        return super(FLDateEdit, self).date

    def setDate(self, d=None):

        from pineboolib.utils import convert_to_qdate

        if d in (None, "NAN"):
            date = QtCore.QDate.fromString(str("01-01-2000"), "dd-MM-yyyy")
        else:
            date = convert_to_qdate(d)

        super(FLDateEdit, self).setDate(date)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setDate" % self._parent.objectName(), date.toString())
        else:
            self.setStyleSheet('color: black')

    date = property(getDate, setDate)


class QTabWidget(QtWidgets.QTabWidget):

    def setTabEnabled(self, tab, enabled):

        idx = self.indexByName(tab)
        if idx is None:
            return

        if pineboolib.project._DGI.localDesktop():
            return QtWidgets.QTabWidget.setTabEnabled(self, idx, enabled)
        else:
            pineboolib.project._DGI._par.addQueque("%s_setTabEnabled" % self.objectName(), [idx, enabled])

            # try:
            #     for idx in range(self.count()):
            #         if self.widget(idx).objectName() == tab.lower():
            #             if not pineboolib.project._DGI.localDesktop():
            #                 pineboolib.project._DGI._par.addQueque("%s_setTabEnabled" % self.objectName(), [idx, enabled])
            #             return QtWidgets.QTabWidget.setTabEnabled(self, idx, enabled)

            # except ValueError:
            #     print("ERROR: Tab not found:: QTabWidget::setTabEnabled %r : %r" % (tab, enabled))
            #     return False
        # print("ERROR: Unknown type for 1st arg:: QTabWidget::setTabEnabled %r : %r" % (tab, enabled))

    def showPage(self, tab):

        idx = self.indexByName(tab)
        if idx is None:
            return

        if pineboolib.project._DGI.localDesktop():
            return QtWidgets.QTabWidget.setCurrentIndex(self, idx)
        else:
            pass
            # pineboolib.project._DGI._par.addQueque("%s_setTabEnabled" % self.objectName(), [idx, enabled])

    def indexByName(self, tab):

        idx = None
        if isinstance(tab, int):
            return tab
        elif not isinstance(tab, str):
            logger.error("ERROR: Unknown type tab name or index:: QTabWidget %r", tab)
            return None

        try:
            for idx in range(self.count()):
                if self.widget(idx).objectName() == tab.lower():
                    return idx
        except ValueError:
            logger.error("ERROR: Tab not found:: QTabWidget, tab name = %r", tab)
        return None

    def removePage(self, idx):
        if isinstance(idx, int):
            self.removeTab(idx)


class FLCheckBox(QtWidgets.QCheckBox):

    def __init__(self, parent=None, num_rows=None):
        super(FLCheckBox, self).__init__(parent)


class QTable(QtWidgets.QTableWidget):

    lineaActual = None
    currentChanged = QtCore.pyqtSignal(int, int)
    doubleClicked = QtCore.pyqtSignal(int, int)
    read_only_cols = None
    read_only_rows = None
    cols_list = None

    def __init__(self, parent=None):
        super(QTable, self).__init__(parent)
        if not parent:
            self.setParent(self.parentWidget())

        self.cols_list = []
        self.lineaActual = -1
        self.currentCellChanged.connect(self.currentChanged_)
        self.cellDoubleClicked.connect(self.doubleClicked_)
        self.read_only_cols = []
        self.read_only_rows = []

    @decorators.needRevision
    def currentChanged_(self, currentRow, currentColumn, previousRow, previousColumn):
        # FIXME: esto produce un TypeError: native Qt signal is not callable
        self.currentChanged.emit(currentRow, currentColumn)

    def doubleClicked_(self, f, c):
        self.doubleClicked.emit(f, c)

    def numRows(self):
        return self.rowCount()

    def numCols(self):
        return self.columnCount()

    def setNumCols(self, n):
        self.setColumnCount(n)
        self.setColumnLabels(",", ",".join(self.cols_list))

    def setNumRows(self, n):
        self.setRowCount(n)

    def setReadOnly(self, b):
        if b:
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        else:
            self.setEditTriggers(QtWidgets.QAbstractItemView.EditTriggers)

    def selectionMode(self):
        return super(QTable, self).selectionMode()

    def setFocusStyle(self, m):
        self.setStyleSheet(m)

    def setColumnLabels(self, separador, lista):
        array_ = lista.split(separador)
        labels_ = []
        for i in range(self.columnCount()):
            if len(array_) > i:
                labels_.append(array_[i])
        self.setHorizontalHeaderLabels(labels_)

    def setColumnStrechable(self, col, b):
        if b:
            self.horizontalHeader().setSectionResizeMode(col, Qt.QHeaderView.Stretch)
        else:
            self.horizontalHeader().setSectionResizeMode(col, Qt.QHeaderView.AdjustToContents)

    def setHeaderLabel(self, l):
        self.cols_list.append(l)
        self.setColumnLabels(",", ",".join(self.cols_list))

    def insertRows(self, numero):
        self.insertRow(numero)

    def text(self, row, col):
        return self.item(row, col).text() if self.item(row, col) else None

    def setText(self, row, col, value):
        # self.setItem(self.numRows() - 1, col, QtWidgets.QTableWidgetItem(str(value)))
        self.setItem(row, col, QtWidgets.QTableWidgetItem(str(value)))
        if row in self.read_only_rows:
            self.setRowReadOnly(row, True)

        if col in self.read_only_cols:
            self.setColumnReadOnly(col, True)

    def adjustColumn(self, k):
        self.horizontalHeader().setSectionResizeMode(k, QtWidgets.QHeaderView.ResizeToContents)

    def setRowReadOnly(self, row, b):
        if b:
            self.read_only_rows.append(row)
        else:
            for r in self.read_only_rows:
                if r == row:
                    del r
                    break

        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                if b:
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                else:
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

    def setColumnReadOnly(self, col, b):
        if b:
            self.read_only_cols.append(col)
        else:
            for c in self.read_only_cols:
                if c == col:
                    del c
                    break

        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item:
                if b:
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                else:
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

    @decorators.NotImplementedWarn
    def setLeftMargin(self, n):
        pass

        # setItemDelegateForColumn(c, new NotEditableDelegate(view))

    # def __getattr__(self, name):
        # return DefFun(self, name)


class FLTable(QTable):
    AlwaysOff = None

    @decorators.NotImplementedWarn
    def setColumnMovingEnabled(self, b):
        pass

    @decorators.NotImplementedWarn
    def setVScrollBarMode(self, mode):
        pass

    @decorators.NotImplementedWarn
    def setHScrollBarMode(self, mode):
        pass


@decorators.NotImplementedWarn
class QDataView(QtWidgets.QWidget):

    pass


class FLTimeEdit(QtWidgets.QTimeEdit):

    def __init__(self, parent):
        super(FLTimeEdit, self).__init__(parent)
        self.setDisplayFormat("hh:mm:ss")
        self.setMinimumWidth(90)
        self.setMaximumWidth(90)

    def setTime(self, v):
        if isinstance(v, str):
            v = v.split(':')
            time = QtCore.QTime(int(v[0]), int(v[1]), int(v[2]))
        else:
            time = v

        super(FLTimeEdit, self).setTime(time)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setTime" % self._parent.objectName(), date.toString())
    
    def getTime(self):
        return super(FLTimeEdit).time
    
    time = property(getTime, setTime)


class FLSpinBox(QtWidgets.QSpinBox):

    def __init__(self, parent=None):
        super(FLSpinBox, self).__init__(parent)
        # editor()setAlignment(Qt::AlignRight);

    def setMaxValue(self, v):
        self.setMaximum(v)


class QComboBox(QtWidgets.QComboBox):

    _parent = None

    def __init__(self, parent=None):
        self._parent = parent
        super(QComboBox, self).__init__(parent)

    # def __getattr__(self, name):
    #    return DefFun(self, name)

    @QtCore.pyqtProperty(str)
    def currentItem(self):
        return self.currentIndex

    @currentItem.setter
    def currentItem(self, i):
        if i:
            if not pineboolib.project._DGI.localDesktop():
                pineboolib.project._DGI._par.addQueque("%s_setCurrentIndex" % self.objectName(), n)
            self.setCurrentIndex(i)

    def insertStringList(self, strl):
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_insertStringList" % self.objectName(), strl)
        self.insertItems(len(strl), strl)


class QLineEdit(QtWidgets.QLineEdit):

    _parent = None

    def __init__(self, parent=None):
        super(QLineEdit, self).__init__(parent=None)
        self._parent = parent
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_CreateWidget" % self._parent.objectName(), "QLineEdit")

    def getText(self):
        return super(QLineEdit, self).text()

    def setText(self, v):
        if not isinstance(v, str):
            v = str(v)
        super(QLineEdit, self).setText(v)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setText" % self._parent.objectName(), v)

    text = property(getText, setText)


class QTextEdit(QtWidgets.QTextEdit):
    LogText = 0

    def __init__(self, parent = None):
        super(QTextEdit, self).__init__(parent)
        self.LogText = 0

    def setText(self, text):
        super(QTextEdit, self).setText(text)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setText" % self._parent.objectName(), text)

    def getText(self):
        return super(QTextEdit, self).toPlainText()

    @decorators.NotImplementedWarn
    def textFormat(self):
        return

    @decorators.Incomplete
    def setTextFormat(self, value):
        if value == 0:  # LogText
            self.setReadOnly(True)

    @decorators.NotImplementedWarn
    def setShown(self, value):
        pass

    def setAutoFormatting(self, value):
        if value == 0:
            value = QtWidgets.QTextEdit.AutoAll
        super(QTextEdit, self).setAutoFormatting(value)

    text = property(getText, setText)


class QCheckBox(QtWidgets.QCheckBox):

    _parent = None

    def __init__(self, parent):
        self._parent = parent
        super(QCheckBox, self).__init__(parent)

    @QtCore.pyqtProperty(int)
    def checked(self):
        return self.isChecked()

    @checked.setter
    def checked(self, b):
        if isinstance(b, str):
            b = (b == "true")
        super(QCheckBox, self).setChecked(b)
        if not pineboolib.project._DGI.localDesktop():
            pineboolib.project._DGI._par.addQueque("%s_setChecked" % self._parent.objectName(), b)


class QToolButton(QtWidgets.QToolButton):

    groupId = None

    def __init__(self, parent):
        super(QToolButton, self).__init__(parent)
        self.groupId = None

    def setToggleButton(self, value):
        self.setDown(value)

    @decorators.Deprecated
    def setUsesBigPixmap(self, value):
        pass

    def toggleButton(self):
        return self.isDown()

    def getOn(self):
        return self.isChecked()

    def setOn(self, value):
        self.setChecked(value)

    on = property(getOn, setOn)

    @decorators.Deprecated
    def setUsesTextLabel(self, value):
        pass

    def buttonGroupId(self):
        return self.groupId

    def setButtonGroupId(self, id):
        self.groupId = id


class QButtonGroup(QGroupBox):

    def __init__(self, *args):
        super(QButtonGroup, self).__init__(*args)

    @decorators.NotImplementedWarn
    def setLineWidth(self, w):
        pass


class CheckBox(QWidget):
    _label = None
    _cb = None

    def __init__(self):
        super(CheckBox, self).__init__()

        self._label = QtWidgets.QLabel(self)
        self._cb = QtWidgets.QCheckBox(self)
        spacer = QtWidgets.QSpacerItem(
            1, 1, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        _lay = QtWidgets.QHBoxLayout()
        _lay.addWidget(self._cb)
        _lay.addWidget(self._label)
        _lay.addSpacerItem(spacer)
        self.setLayout(_lay)

    def __setattr__(self, name, value):
        if name == "text":
            self._label.setText(str(value))
        elif name == "checked":
            self._cb.setChecked(value)
        else:
            super(CheckBox, self).__setattr__(name, value)

    def __getattr__(self, name):
        if name == "checked":
            return self._cb.isChecked()
        else:
            return super(CheckBox, self).__getattr__(name)


class LineEdit(QWidget):
    _label = None
    _line = None

    def __init__(self):
        super(LineEdit, self).__init__()

        self._label = QtWidgets.QLabel(self)
        self._line = QtWidgets.QLineEdit(self)
        _lay = QtWidgets.QHBoxLayout()
        _lay.addWidget(self._label)
        _lay.addWidget(self._line)
        self.setLayout(_lay)

    def __setattr__(self, name, value):
        if name == "label":
            self._label.setText(str(value))
        elif name == "text":
            self._line.setText(str(value))
        else:
            super(LineEdit, self).__setattr__(name, value)

    def __getattr__(self, name):
        if name == "text":
            return self._line.text()
        else:
            return super(LineEdit, self).__getattr__(name)


FLDomDocument = QDomDocument
FLListViewItem = QtWidgets.QListView


class FileDialog(QtWidgets.QFileDialog):

    def getOpenFileName(*args):
        obj = None
        parent = QtWidgets.QApplication.activeModalWidget()
        if len(args) == 1:
            obj = QtWidgets.QFileDialog.getOpenFileName(parent, str(args[0]))
        elif len(args) == 2:
            obj = QtWidgets.QFileDialog.getOpenFileName(parent, str(args[0]), str(args[1]))
        elif len(args) == 3:
            obj = QtWidgets.QFileDialog.getOpenFileName(parent, str(args[0]), str(args[1]), str(args[2]))
        elif len(args) == 4:
            obj = QtWidgets.QFileDialog.getOpenFileName(parent, str(args[0]), str(args[1]), str(args[2]), str(args[3]))

        if obj is None:
            return None

        return obj[0]

    def getExistingDirectory(basedir=None, caption=None):
        if not basedir:
            from pineboolib.utils import filedir
            basedir = filedir("..")

        import pineboolib
        if pineboolib.project._DGI.localDesktop():
            parent = pineboolib.project.main_window.ui_
            ret = QtWidgets.QFileDialog.getExistingDirectory(
                parent, caption, basedir, QtWidgets.QFileDialog.ShowDirsOnly)
            if ret:
                ret = ret + "/"

            return ret


class MessageBox(QMessageBox):
    @classmethod
    def msgbox(cls, typename, text, button0, button1=None, button2=None, title=None, form=None):
        if form:
            logger.warn("MessageBox: Se intentó usar form, y no está implementado.")
        icon = QMessageBox.NoIcon
        if not title:
            title = "Pineboo"
        if typename == "question":
            icon = QMessageBox.Question
            if not title:
                title = "Question"
        elif typename == "information":
            icon = QMessageBox.Information
            if not title:
                title = "Information"
        elif typename == "warning":
            icon = QMessageBox.Warning
            if not title:
                title = "Warning"
        elif typename == "critical":
            icon = QMessageBox.Critical
            if not title:
                title = "Critical"
        # title = unicode(title,"UTF-8")
        # text = unicode(text,"UTF-8")
        msg = QMessageBox(icon, title, text)
        msg.addButton(button0)
        if button1:
            msg.addButton(button1)
        if button2:
            msg.addButton(button2)
        return msg.exec_()

    @classmethod
    def question(cls, *args):
        return cls.msgbox("question", *args)

    @classmethod
    def information(cls, *args):
        return cls.msgbox("question", *args)

    @classmethod
    def warning(cls, *args):
        return cls.msgbox("warning", *args)

    @classmethod
    def critical(cls, *args):
        return cls.msgbox("critical", *args)


QColor = QtGui.QColor


class RadioButton(QtWidgets.QRadioButton):

    def __ini__(self):
        super(RadioButton, self).__init__()
        self.setChecked(False)

    def __setattr__(self, name, value):
        if name == "text":
            self.setText(value)
        elif name == "checked":
            self.setChecked(value)
        else:
            super(RadioButton, self).__setattr__(name, value)

    def __getattr__(self, name):
        if name == "checked":
            return self.isChecked()

class Process(QtCore.QProcess):

    stderr = None
    stdout = None

    def __init__(self, *args):
        super(Process, self).__init__()
        self.readyReadStandardOutput.connect(self.stdoutReady)
        self.readyReadStandardError.connect(self.stderrReady)
        self.stderr = None
        self.normalExit = self.NormalExit
        self.crashExit = self.CrashExit
        
        if args:
            self.setProgram(args[0])
            argumentos = args[1:]
            self.setArguments(argumentos)

    def start(self):
        super(Process, self).start()

    def stop(self):
        super(Process, self).stop()

    def writeToStdin(self, stdin_):
        import sys
        encoding = sys.getfilesystemencoding()
        stdin_as_bytes = stdin_.encode(encoding)
        self.writeData(stdin_as_bytes)
        # self.closeWriteChannel()

    def stdoutReady(self):
        self.stdout = str(self.readAllStandardOutput())

    def stderrReady(self):
        self.stderr = str(self.readAllStandardError())

    def readStderr(self):
        return self.stderr

    def getWorkingDirectory(self):
        return super(Process, self).workingDirectory()

    def setWorkingDirectory(self, wd):
        super(Process, self).setWorkingDirectory(wd)

    def getIsRunning(self):
        return self.state() in (self.Running, self.Starting)
    
    def exitcode(self):
        return self.exitCode()

    def execute(comando):
        import sys
        encoding = sys.getfilesystemencoding()
        pro = QtCore.QProcess()
        if isinstance(comando, str):
            comando = comando.split(" ")

        programa = comando[0]
        argumentos = comando[1:]
        pro.setProgram(programa)
        pro.setArguments(argumentos)
        pro.start()
        pro.waitForFinished(30000)
        Process.stdout = pro.readAllStandardOutput().data().decode(encoding)
        Process.stderr = pro.readAllStandardError().data().decode(encoding)

    running = property(getIsRunning)
    workingDirectory = property(getWorkingDirectory, setWorkingDirectory)
    
    


QProcess = Process

class QDialog(QtWidgets.QDialog):
    
    def getTitle(self):
        return self.windowTitle()
    
    def setTitle(self, title):
        self.setWindowTitle(title)
    
    def getEnabled(self):
        return self.isEnabled()
    
    def setEnable_(self, enable_):
        self.setEnabled(enable_)

    caption = property(getTitle, setTitle)
    enable = property(getEnabled, setEnable_)
    
class Dialog(QDialog):
    _layout = None
    buttonBox = None
    okButtonText = None
    cancelButtonText = None
    okButton = None
    cancelButton = None
    _tab = None

    def __init__(self, title=None, f=None, desc=None):
        # FIXME: f no lo uso , es qt.windowsflg
        super(Dialog, self).__init__()
        if title:
            self.setWindowTitle(str(title))

        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self._layout = QtWidgets.QVBoxLayout()
        self.setLayout(self._layout)
        self.buttonBox = QtWidgets.QDialogButtonBox()
        self.okButton = QtWidgets.QPushButton("&Aceptar")
        self.cancelButton = QtWidgets.QPushButton("&Cancelar")
        self.buttonBox.addButton(
            self.okButton, QtWidgets.QDialogButtonBox.AcceptRole)
        self.buttonBox.addButton(
            self.cancelButton, QtWidgets.QDialogButtonBox.RejectRole)
        self.okButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)
        from PyQt5.Qt import QTabWidget
        self._tab = QTabWidget()
        self._tab.hide()
        self._layout.addWidget(self._tab)
        self.oKButtonText = None
        self.cancelButtonText = None

    def add(self, _object):
        self._layout.addWidget(_object)

    def exec_(self):
        if self.okButtonText:
            self.okButton.setText(str(self.okButtonText))
        if (self.cancelButtonText):
            self.cancelButton.setText(str(self.cancelButtonText))
        self._layout.addWidget(self.buttonBox)

        return super(Dialog, self).exec_()

    def newTab(self, name):
        if self._tab.isHidden():
            self._tab.show()
        self._tab.addTab(QtWidgets.QWidget(), str(name))

    def __getattr__(self, name):
        if name == "caption":
            name = self.setWindowTitle

        return getattr(super(Dialog, self), name)


class GroupBox(QGroupBox):
    def __init__(self, *args):
        super(GroupBox, self).__init__(*args)
        self._layout = QtWidgets.QVBoxLayout()
        self.setLayout(self._layout)

    def add(self, _object):
        self._layout.addWidget(_object)





class QVBoxLayout(QtWidgets.QVBoxLayout):
    pass


class QHBoxLayout(QtWidgets.QHBoxLayout):
    pass


class QFrame(QtWidgets.QFrame):
    pass


class QMainWindow(QtWidgets.QMainWindow):

    def child(self, n, c=None):
        ret = None

        if c is None:
            c = QtCore.QObject
        ret = self.findChild(c, n)
        return ret


class QMenu(Qt.QMenu):
    pass


QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QIcon = QtGui.QIcon
"""
class QPixmap(QtGui.QPixmap):

    def convertToImage(self):
        return QImage(self.toImage())


class QImage(QtGui.QImage):

    def smoothScale(self, w, h):
        self = self.scaled(w, h)


class QIconSet(object):

    def __init__(self, icon):
        self = icon
"""


class QDoubleValidator(QtGui.QDoubleValidator):
    pass
