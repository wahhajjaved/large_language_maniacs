"""Flformrecord module."""
# -*- coding: utf-8 -*-


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.Qt import QKeySequence  # type: ignore

from pineboolib.core.utils.utils_base import filedir
from pineboolib.core.settings import config
from pineboolib.core import decorators

from pineboolib.application.database import pnsqlcursor

from pineboolib.fllegacy.flformdb import FLFormDB
from pineboolib.fllegacy.flsqlquery import FLSqlQuery
from pineboolib.fllegacy import flapplication

from pineboolib import logging


from typing import cast, Union, Optional, TYPE_CHECKING
import traceback

if TYPE_CHECKING:
    from . import flaction


DEBUG = False


class FLFormRecordDB(FLFormDB):
    """
    FLFormRecordDBInterface Class.

    FLFormDB subclass designed to edit records.

    Basically this class does the same as its class
    FLFormDB base, the only thing you add is two buttons
    Accept and / or Cancel to confirm or cancel
    the changes that are made to the components of
    data it contains.

    This class is suitable for loading forms
    editing records defined in metadata
    (FLTableMetaData).

    @author InfoSiAL S.L.
    """

    logger = logging.getLogger("FLFormRecordDB")
    """
    Boton Aceptar
    """

    pushButtonAccept: Optional[QtWidgets.QToolButton]

    """
    Boton Aceptar y continuar
    """
    pushButtonAcceptContinue: Optional[QtWidgets.QToolButton]

    """
    Boton Primero
    """
    pushButtonFirst: Optional[QtWidgets.QToolButton]

    """
    Boton Anterior
    """
    pushButtonPrevious: Optional[QtWidgets.QToolButton]

    """
    Boton Siguiente
    """
    pushButtonNext: Optional[QtWidgets.QToolButton]

    """
    Boton Ultimo
    """
    pushButtonLast: Optional[QtWidgets.QToolButton]

    """
    Indica si se debe mostrar el botón Aceptar y Continuar
    """
    showAcceptContinue_: bool

    """
    Indica que se está intentando aceptar los cambios
    """
    accepting: bool

    """
    Modo en el que inicialmente está el cursor
    """
    initialModeAccess: int

    """
    Registra el nivel de anidamiento de transacciones en el que se entra al iniciar el formulario
    """
    initTransLevel: int

    def __init__(
        self,
        parent_or_cursor: Union[QtWidgets.QWidget, pnsqlcursor.PNSqlCursor, None],
        action: "flaction.FLAction",
        load: bool = False,
    ) -> None:
        """
        Inicialize.
        """
        self.logger.trace(
            "__init__: parent_or_cursor=%s, action=%s, load=%s", parent_or_cursor, action, load
        )

        cursor: Optional[pnsqlcursor.PNSqlCursor]
        # if isinstance(action, str):
        #    flapplication.aqApp.db().manager().action(action)

        if isinstance(parent_or_cursor, pnsqlcursor.PNSqlCursor):
            parent = flapplication.aqApp.mainWidget()
            cursor = parent_or_cursor
        else:
            parent = parent_or_cursor
            cursor = None

        super().__init__(parent, action, load)

        self.setWindowModality(QtCore.Qt.ApplicationModal)

        if cursor:
            self.setCursor(parent_or_cursor)
        self.logger.trace("__init__: load formRecord")
        self._uiName = action.formRecord()
        self._scriptForm = action.scriptFormRecord() or "emptyscript"

        self.pushButtonAccept = None
        self.pushButtonAcceptContinue = None
        self.pushButtonFirst = None
        self.pushButtonPrevious = None
        self.pushButtonNext = None
        self.pushButtonLast = None

        self.accepting = False
        self.showAcceptContinue_ = True
        self.initialModeAccess = pnsqlcursor.PNSqlCursor.Browse

        if self.cursor_:
            self.initialModeAccess = self.cursor_.modeAccess()

        self.logger.trace("__init__: load form")
        self.load()
        self.logger.trace("__init__: init form")
        self.initForm()
        self.logger.trace("__init__: done")
        self.loop = False

    def setCaptionWidget(self, text: Optional[str] = None) -> None:
        """
        Set the window title.
        """
        if not self.cursor_:
            return

        if not text:
            text = self.cursor_.metadata().alias()

        if self.cursor_.modeAccess() == self.cursor_.Insert:
            self.setWindowTitle("Insertar %s" % text)
        elif self.cursor_.modeAccess() == self.cursor_.Edit:
            self.setWindowTitle("Editar %s" % text)
        elif self.cursor_.modeAccess() == self.cursor_.Browse:
            self.setWindowTitle("Visualizar %s" % text)

    def formClassName(self) -> str:
        """
        Return the class name of the form at runtime.
        """

        return "FormRecordDB"

    def initForm(self) -> None:
        """
        Initialize the form.
        """

        if self.cursor_ and self.cursor_.metadata():
            # caption = None
            if self._action:
                self.cursor().setAction(self._action)
                if self._action.description():
                    self.setWhatsThis(self._action.description())
                self.idMDI_ = self._action.name()

            # self.bindIface()
            # self.setCursor(self.cursor_)

        else:
            self.setCaptionWidget("No hay metadatos")
        # acl = project.acl()
        acl = None  # FIXME: Add ACL later
        if acl:
            acl.process(self)

    def loadControls(self) -> None:
        """Load widgets for this form."""
        if self.pushButtonAcceptContinue:
            self.pushButtonAcceptContinue.hide()

        if self.pushButtonAccept:
            self.pushButtonAccept.hide()

        if self.pushButtonCancel:
            self.pushButtonCancel.hide()

        if self.pushButtonFirst:
            self.pushButtonFirst.hide()

        if self.pushButtonPrevious:
            self.pushButtonPrevious.hide()

        if self.pushButtonNext:
            self.pushButtonNext.hide()

        if self.pushButtonLast:
            self.pushButtonLast.hide()

        if self.bottomToolbar and self.toolButtonClose:
            self.toolButtonClose.hide()

        self.bottomToolbar = QtWidgets.QFrame()

        if self.bottomToolbar:
            self.bottomToolbar.setMinimumSize(self.iconSize)
            self.bottomToolbar.setLayout(QtWidgets.QHBoxLayout())

            self.bottomToolbar.layout().setContentsMargins(0, 0, 0, 0)
            self.bottomToolbar.layout().setSpacing(0)
            self.bottomToolbar.layout().addStretch()
            self.bottomToolbar.setFocusPolicy(QtCore.Qt.NoFocus)
            self.layout_.addWidget(self.bottomToolbar)
        # if self.layout:
        #    self.layout = None
        # Limpiamos la toolbar

        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy(0), QtWidgets.QSizePolicy.Policy(0)
        )
        sizePolicy.setHeightForWidth(True)

        pbSize = self.iconSize

        if config.value("application/isDebuggerMode", False):

            pushButtonExport = QtWidgets.QToolButton()
            pushButtonExport.setObjectName("pushButtonExport")
            pushButtonExport.setSizePolicy(sizePolicy)
            pushButtonExport.setMinimumSize(pbSize)
            pushButtonExport.setMaximumSize(pbSize)
            pushButtonExport.setIcon(
                QtGui.QIcon(filedir("./core/images/icons", "gtk-properties.png"))
            )
            pushButtonExport.setShortcut(QKeySequence(self.tr("F3")))
            pushButtonExport.setWhatsThis("Exportar a XML(F3)")
            pushButtonExport.setToolTip("Exportar a XML(F3)")
            pushButtonExport.setFocusPolicy(QtCore.Qt.NoFocus)
            self.bottomToolbar.layout().addWidget(pushButtonExport)
            pushButtonExport.clicked.connect(self.exportToXml)

            if config.value("ebcomportamiento/show_snaptshop_button", False):
                push_button_snapshot = QtWidgets.QToolButton()
                push_button_snapshot.setObjectName("pushButtonSnapshot")
                push_button_snapshot.setSizePolicy(sizePolicy)
                push_button_snapshot.setMinimumSize(pbSize)
                push_button_snapshot.setMaximumSize(pbSize)
                push_button_snapshot.setIcon(
                    QtGui.QIcon(filedir("./core/images/icons", "gtk-paste.png"))
                )
                push_button_snapshot.setShortcut(QKeySequence(self.tr("F8")))
                push_button_snapshot.setWhatsThis("Capturar pantalla(F8)")
                push_button_snapshot.setToolTip("Capturar pantalla(F8)")
                push_button_snapshot.setFocusPolicy(QtCore.Qt.NoFocus)
                self.bottomToolbar.layout().addWidget(push_button_snapshot)
                push_button_snapshot.clicked.connect(self.saveSnapShot)

            spacer = QtWidgets.QSpacerItem(
                20, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
            )
            self.bottomToolbar.layout().addItem(spacer)

        if self.cursor().modeAccess() in (self.cursor().Edit, self.cursor().Browse):
            if not self.pushButtonFirst:
                self.pushButtonFirst = QtWidgets.QToolButton()
                self.pushButtonFirst.setObjectName("pushButtonFirst")
                self.pushButtonFirst.setIcon(
                    QtGui.QIcon(filedir("./core/images/icons", "gtk-goto-first-ltr.png"))
                )
                self.pushButtonFirst.clicked.connect(self.firstRecord)
                self.pushButtonFirst.setSizePolicy(sizePolicy)
                self.pushButtonFirst.setMaximumSize(pbSize)
                self.pushButtonFirst.setMinimumSize(pbSize)
                self.pushButtonFirst.setShortcut(QKeySequence(self.tr("F5")))
                self.pushButtonFirst.setWhatsThis(
                    "Aceptar los cambios e ir al primer registro (F5)"
                )
                self.pushButtonFirst.setToolTip("Aceptar los cambios e ir al primer registro (F5)")
                self.pushButtonFirst.setFocusPolicy(QtCore.Qt.NoFocus)
                self.bottomToolbar.layout().addWidget(self.pushButtonFirst)
                # self.pushButtonFirst.show()

            if not self.pushButtonPrevious:
                self.pushButtonPrevious = QtWidgets.QToolButton()
                self.pushButtonPrevious.setObjectName("pushButtonPrevious")
                self.pushButtonPrevious.setIcon(
                    QtGui.QIcon(filedir("./core/images/icons", "gtk-go-back-ltr.png"))
                )
                self.pushButtonPrevious.clicked.connect(self.previousRecord)
                self.pushButtonPrevious.setSizePolicy(sizePolicy)
                self.pushButtonPrevious.setMaximumSize(pbSize)
                self.pushButtonPrevious.setMinimumSize(pbSize)
                self.pushButtonPrevious.setShortcut(QKeySequence(self.tr("F6")))
                self.pushButtonPrevious.setWhatsThis(
                    "Aceptar los cambios e ir al registro anterior (F6)"
                )
                self.pushButtonPrevious.setToolTip(
                    "Aceptar los cambios e ir al registro anterior (F6)"
                )
                self.pushButtonPrevious.setFocusPolicy(QtCore.Qt.NoFocus)
                self.bottomToolbar.layout().addWidget(self.pushButtonPrevious)
                # self.pushButtonPrevious.show()

            if not self.pushButtonNext:
                self.pushButtonNext = QtWidgets.QToolButton()
                self.pushButtonNext.setObjectName("pushButtonNext")
                self.pushButtonNext.setIcon(
                    QtGui.QIcon(filedir("./core/images/icons", "gtk-go-back-rtl.png"))
                )
                self.pushButtonNext.clicked.connect(self.nextRecord)
                self.pushButtonNext.setSizePolicy(sizePolicy)
                self.pushButtonNext.setMaximumSize(pbSize)
                self.pushButtonNext.setMinimumSize(pbSize)
                self.pushButtonNext.setShortcut(QKeySequence(self.tr("F7")))
                self.pushButtonNext.setWhatsThis(
                    "Aceptar los cambios e ir al registro siguiente (F7)"
                )
                self.pushButtonNext.setToolTip(
                    "Aceptar los cambios e ir al registro siguiente (F7)"
                )
                self.pushButtonNext.setFocusPolicy(QtCore.Qt.NoFocus)
                self.bottomToolbar.layout().addWidget(self.pushButtonNext)
                # self.pushButtonNext.show()

            if not self.pushButtonLast:
                self.pushButtonLast = QtWidgets.QToolButton()
                self.pushButtonLast.setObjectName("pushButtonLast")
                self.pushButtonLast.setIcon(
                    QtGui.QIcon(filedir("./core/images/icons", "gtk-goto-last-ltr.png"))
                )
                self.pushButtonLast.clicked.connect(self.lastRecord)
                self.pushButtonLast.setSizePolicy(sizePolicy)
                self.pushButtonLast.setMaximumSize(pbSize)
                self.pushButtonLast.setMinimumSize(pbSize)
                self.pushButtonLast.setShortcut(QKeySequence(self.tr("F8")))
                self.pushButtonLast.setWhatsThis("Aceptar los cambios e ir al último registro (F8)")
                self.pushButtonLast.setToolTip("Aceptar los cambios e ir al último registro (F8)")
                self.pushButtonLast.setFocusPolicy(QtCore.Qt.NoFocus)
                self.bottomToolbar.layout().addWidget(self.pushButtonLast)
                # self.pushButtonLast.show()

        if not self.cursor().modeAccess() == self.cursor().Browse:
            self.pushButtonAcceptContinue = QtWidgets.QToolButton()
            self.pushButtonAcceptContinue.setObjectName("pushButtonAcceptContinue")
            self.pushButtonAcceptContinue.clicked.connect(self.acceptContinue)
            self.pushButtonAcceptContinue.setSizePolicy(sizePolicy)
            self.pushButtonAcceptContinue.setMaximumSize(pbSize)
            self.pushButtonAcceptContinue.setMinimumSize(pbSize)
            self.pushButtonAcceptContinue.setIcon(
                QtGui.QIcon(filedir("./core/images/icons", "gtk-refresh.png"))
            )
            self.pushButtonAcceptContinue.setShortcut(QKeySequence(self.tr("F9")))
            self.pushButtonAcceptContinue.setWhatsThis(
                "Aceptar los cambios y continuar con la edición de un nuevo registro (F9)"
            )
            self.pushButtonAcceptContinue.setToolTip(
                "Aceptar los cambios y continuar con la edición de un nuevo registro (F9)"
            )
            self.pushButtonAcceptContinue.setFocusPolicy(QtCore.Qt.NoFocus)
            self.bottomToolbar.layout().addWidget(self.pushButtonAcceptContinue)
            if not self.showAcceptContinue_:
                self.pushButtonAcceptContinue.close()
                # self.pushButtonAcceptContinue.show()

            if not self.pushButtonAccept:
                self.pushButtonAccept = QtWidgets.QToolButton()
                self.pushButtonAccept.setObjectName("pushButtonAccept")
                self.pushButtonAccept.clicked.connect(self.accept)

            self.pushButtonAccept.setSizePolicy(sizePolicy)
            self.pushButtonAccept.setMaximumSize(pbSize)
            self.pushButtonAccept.setMinimumSize(pbSize)
            self.pushButtonAccept.setIcon(
                QtGui.QIcon(filedir("./core/images/icons", "gtk-save.png"))
            )
            self.pushButtonAccept.setShortcut(QKeySequence(self.tr("F10")))
            self.pushButtonAccept.setWhatsThis("Aceptar los cambios y cerrar formulario (F10)")
            self.pushButtonAccept.setToolTip("Aceptar los cambios y cerrar formulario (F10)")
            self.pushButtonAccept.setFocusPolicy(QtCore.Qt.NoFocus)
            self.bottomToolbar.layout().addWidget(self.pushButtonAccept)
            # self.pushButtonAccept.show()

        if not self.pushButtonCancel:
            self.pushButtonCancel = QtWidgets.QToolButton()
            self.pushButtonCancel.setObjectName("pushButtonCancel")
            try:
                self.cursor().autocommit.connect(self.disablePushButtonCancel)
            except Exception:
                pass

            self.pushButtonCancel.clicked.connect(self.reject)

        self.pushButtonCancel.setSizePolicy(sizePolicy)
        self.pushButtonCancel.setMaximumSize(pbSize)
        self.pushButtonCancel.setMinimumSize(pbSize)
        self.pushButtonCancel.setShortcut(QKeySequence(self.tr("Esc")))
        self.pushButtonCancel.setIcon(QtGui.QIcon(filedir("./core/images/icons", "gtk-stop.png")))
        if not self.cursor().modeAccess() == self.cursor().Browse:
            self.pushButtonCancel.setFocusPolicy(QtCore.Qt.NoFocus)
            self.pushButtonCancel.setWhatsThis("Cancelar los cambios y cerrar formulario (Esc)")
            self.pushButtonCancel.setToolTip("Cancelar los cambios y cerrar formulario (Esc)")
        else:
            self.pushButtonCancel.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.pushButtonCancel.setFocus()
            # pushButtonCancel->setAccel(4096); FIXME
            self.pushButtonCancel.setWhatsThis("Aceptar y cerrar formulario (Esc)")
            self.pushButtonCancel.setToolTip("Aceptar y cerrar formulario (Esc)")

        # pushButtonCancel->setDefault(true);
        self.bottomToolbar.layout().addItem(
            QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        )
        self.bottomToolbar.layout().addWidget(self.pushButtonCancel)
        # self.pushButtonAccept.show()

        self.setFocusPolicy(QtCore.Qt.NoFocus)

        # self.toolButtonAccept = QtGui.QToolButton()
        # self.toolButtonAccept.setIcon(QtGui.QIcon(filedir("./core/images/icons","gtk-add.png")))
        # self.toolButtonAccept.clicked.connect(self.validateForm)
        # self.bottomToolbar.layout.addWidget(self.toolButtonAccept)
        self.inicializeControls()

    def formName(self) -> str:
        """
        Return internal form name.
        """

        return "formRecord%s" % self.idMDI_

    def closeEvent(self, e: QtCore.QEvent) -> None:
        """
        Capture event close.
        """
        self.frameGeometry()
        if self.focusWidget():
            fdb = self.focusWidget().parentWidget()
            try:
                if fdb.autoComFrame_.isvisible():
                    fdb.autoComFrame_.hide()
                    return
            except Exception:
                pass

        if self.cursor_:

            try:
                levels = self.cursor_.transactionLevel() - self.initTransLevel
                if levels > 0:
                    self.cursor_.rollbackOpened(
                        levels,
                        "Se han detectado transacciones no finalizadas en la última operación.\n"
                        "Se van a cancelar las transacciones pendientes.\n"
                        "Los últimos datos introducidos no han sido guardados, por favor\n"
                        "revise sus últimas acciones y repita las operaciones que no\n"
                        "se han guardado.\n"
                        "FLFormRecordDB::closeEvent: %s %s" % (levels, self.name()),
                    )
            except Exception:
                print("ERROR: FLFormRecordDB @ closeEvent :: las transacciones aún no funcionan.")

            if self.accepted_:
                if not self.cursor_.commit():
                    return
                self.afterCommitTransaction()
            else:
                if not self.cursor_.rollback():
                    e.ignore()
                    return
                # else:
                #    self.cursor_.select()

            self.closed.emit()
            self.setCursor(None)
        else:
            self.closed.emit()

        super(FLFormRecordDB, self).closeEvent(e)
        self.deleteLater()

    def validateForm(self) -> bool:
        """
        Form validation.

        Call the "validateForm" function of the associated script when the
        form and only continue with the commit commit when that function
        of script returns TRUE.

        If FLTableMetaData :: concurWarn () is true and two or more sessions / users are.
        Modifying the same fields will display a warning notice.

        @return TRUE if the form has been validated correctly.
        """
        if not self.cursor_:
            return True
        mtd = self.cursor_.metadata()
        if not mtd:
            return True

        if self.cursor_.modeAccess() == pnsqlcursor.PNSqlCursor.Edit and mtd.concurWarn():
            colFields = self.cursor_.concurrencyFields()

            if colFields:
                pKN = mtd.primaryKey()
                pKWhere = (
                    self.cursor_.db()
                    .manager()
                    .formatAssignValue(mtd.field(pKN), self.cursor_.valueBuffer(pKN))
                )
                q = FLSqlQuery(None, self.cursor_.db().connectionName())
                q.setTablesList(mtd.name())
                q.setSelect(colFields)
                q.setFrom(mtd.name())
                q.setWhere(pKWhere)
                q.setForwardOnly(True)

                if q.exec_() and q.next():
                    i = 0
                    for field in colFields:
                        # msg = "El campo '%s' con valor '%s' ha sido modificado\npor otro usuario con el valor '%s'" % (
                        #    mtd.fieldNameToAlias(field), self.cursor_.valueBuffer(field), q.value(i))
                        res = QtWidgets.QMessageBox.warning(
                            QtWidgets.QApplication.focusWidget(),
                            "Aviso de concurrencia",
                            "\n\n ¿ Desea realmente modificar este campo ?\n\n"
                            "Sí : Ignora el cambio del otro usuario y utiliza el valor que acaba de introducir\n"
                            "No : Respeta el cambio del otro usuario e ignora el valor que ha introducido\n"
                            "Cancelar : Cancela el guardado del registro y vuelve a la edición del registro\n\n",
                            cast(
                                QtWidgets.QMessageBox,
                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Default,
                            ),
                            cast(
                                QtWidgets.QMessageBox,
                                QtWidgets.QMessageBox.No
                                | QtWidgets.QMessageBox.Cancel
                                | QtWidgets.QMessageBox.Escape,
                            ),
                        )
                        if res == QtWidgets.QMessageBox.Cancel:
                            return False

                        if res == QtWidgets.QMessageBox.No:
                            self.cursor_.setValueBuffer(field, q.value(i))

        if (
            self.iface
            and self.cursor_.modeAccess() == pnsqlcursor.PNSqlCursor.Insert
            or self.cursor_.modeAccess() == pnsqlcursor.PNSqlCursor.Edit
        ):
            ret_ = True
            fun_ = getattr(self.iface, "validateForm", None)
            if fun_ is not None and fun_ != self.validateForm:
                try:
                    ret_ = fun_()
                except Exception:
                    # script_name = self.iface.__module__
                    from pineboolib.core.error_manager import error_manager
                    from pineboolib.application import project

                    flapplication.aqApp.msgBoxWarning(
                        error_manager(traceback.format_exc(limit=-6, chain=False)), project._DGI
                    )

            return ret_ if isinstance(ret_, bool) else False
        return True

    def acceptedForm(self) -> None:
        """
        Accept of form.

        Call the "acceptedForm" function of the script associated with the form, when
        the form is accepted and just before committing the registration.
        """

        if self.iface:
            try:
                self.iface.acceptedForm()
            except Exception:
                pass

    def afterCommitBuffer(self) -> None:
        """
        After setting the changes of the current record buffer.

        Call the "afterCommitBuffer" function of the script associated with the form
        right after committing the registry buffer.
        """
        if self.iface:
            try:
                self.iface.afterCommitBuffer()
            except Exception:
                pass

    def afterCommitTransaction(self) -> None:
        """
        After fixing the transaction.

        Call the "afterCommitTransaction" function of the script associated with the form,
        right after finishing the current transaction accepting.
        """
        if self.iface:
            try:
                self.iface.afterCommitTransaction()
            except Exception:
                pass

    def canceledForm(self) -> None:
        """
        Form Cancellation.

        Call the "canceledForm" function of the script associated with the form, when
        cancel the form.
        """
        if self.iface:
            try:
                self.iface.canceledForm()
            except Exception:
                pass

    @decorators.pyqtSlot()
    def accept(self) -> None:
        """
        Activate pressing the accept button.
        """

        if self.accepting:
            return

        self.accepting = True

        if not self.cursor_:
            self.close()
            self.accepting = False
            return

        if not self.validateForm():
            self.accepting = False
            return

        if self.cursor_.checkIntegrity():
            self.acceptedForm()
            self.cursor_.setActivatedCheckIntegrity(False)
            if not self.cursor_.commitBuffer():
                self.accepting = False
                return
            else:
                self.cursor_.setActivatedCheckIntegrity(True)
        else:
            self.accepting = False
            return

        self.afterCommitBuffer()
        self.accepted_ = True
        self.close()
        self.accepting = False

    @decorators.pyqtSlot()
    def acceptContinue(self) -> None:
        """
        Activate pressing the accept and continue button.
        """
        if self.accepting:
            return

        self.accepting = True
        if not self.cursor_:
            self.close()
            self.accepting = False
            return

        if not self.validateForm():
            self.accepting = False
            return

        if self.cursor_.checkIntegrity():
            self.acceptedForm()
            self.cursor_.setActivatedCheckIntegrity(False)
            if self.cursor_.commitBuffer():
                self.cursor_.setActivatedCheckIntegrity(True)
                self.cursor_.commit()
                self.cursor_.setModeAccess(pnsqlcursor.PNSqlCursor.Insert)
                self.accepted_ = False
                caption = None
                if self._action:
                    caption = self._action.name()
                if not caption:
                    caption = self.cursor_.metadata().alias()
                self.cursor_.transaction()
                self.setCaptionWidget(caption)
                if self.initFocusWidget_:
                    self.initFocusWidget_.setFocus()
                self.cursor_.refreshBuffer()
                self.initScript()

        self.accepting = False

    @decorators.pyqtSlot()
    def reject(self) -> None:
        """
        Activate pressing the cancel button.
        """
        self.accepted_ = False
        self.canceledForm()
        self.close()

    @decorators.pyqtSlot()
    @decorators.NotImplementedWarn
    def script(self) -> None:
        """
        Return the script associated with the form.
        """

        pass

    @decorators.pyqtSlot()
    def firstRecord(self) -> None:
        """
        Go to the first record.
        """
        if self.cursor_ and not self.cursor_.at() == 0:
            if not self.validateForm():
                return

            if self.cursor_.checkIntegrity():
                self.acceptedForm()
                self.cursor_.setActivatedCheckIntegrity(False)
                if self.cursor_.commitBuffer():
                    self.cursor_.setActivatedCheckIntegrity(True)
                    self.cursor_.commit()
                    self.cursor_.setModeAccess(self.initialModeAccess)
                    self.accepted_ = False
                    self.cursor_.transaction()
                    self.cursor_.first()
                    self.setCaptionWidget()
                    self.initScript()

    @decorators.pyqtSlot()
    def previousRecord(self) -> None:
        """
        Go to the previous record.
        """
        if self.cursor_ and self.cursor_.isValid():
            if self.cursor_.at() == 0:
                self.lastRecord()
                return

            if not self.validateForm():
                return

            if self.cursor_.checkIntegrity():
                self.acceptedForm()
                self.cursor_.setActivatedCheckIntegrity(False)
                if self.cursor_.commitBuffer():
                    self.cursor_.setActivatedCheckIntegrity(True)
                    self.cursor_.commit()
                    self.cursor_.setModeAccess(self.initialModeAccess)
                    self.accepted_ = False
                    self.cursor_.transaction()
                    self.cursor_.prev()
                    self.setCaptionWidget()
                    self.initScript()

    @decorators.pyqtSlot()
    def nextRecord(self) -> None:
        """
        Go to the next record.
        """
        if self.cursor_ and self.cursor_.isValid():
            if self.cursor_.at() == (self.cursor_.size() - 1):
                self.firstRecord()
                return

            if not self.validateForm():
                return

            if self.cursor_.checkIntegrity():
                self.acceptedForm()
                self.cursor_.setActivatedCheckIntegrity(False)
                if self.cursor_.commitBuffer():
                    self.cursor_.setActivatedCheckIntegrity(True)
                    self.cursor_.commit()
                    self.cursor_.setModeAccess(self.initialModeAccess)
                    self.accepted_ = False
                    self.cursor_.transaction()
                    self.cursor_.next()
                    self.setCaptionWidget()
                    self.initScript()

    @decorators.pyqtSlot()
    def lastRecord(self) -> None:
        """
        Go to the last record.
        """
        if self.cursor_ and not self.cursor_.at() == (self.cursor_.size() - 1):
            if not self.validateForm():
                return

            if self.cursor_.checkIntegrity():
                self.acceptedForm()
                self.cursor_.setActivatedCheckIntegrity(False)
                if self.cursor_.commitBuffer():
                    self.cursor_.setActivatedCheckIntegrity(True)
                    self.cursor_.commit()
                    self.cursor_.setModeAccess(self.initialModeAccess)
                    self.accepted_ = False
                    self.cursor_.transaction()
                    self.cursor_.last()
                    self.setCaptionWidget()
                    self.initScript()

    @decorators.pyqtSlot()
    def disablePushButtonCancel(self) -> None:
        """
        Turn off the cancel button.
        """

        if self.pushButtonCancel:
            self.pushButtonCancel.setDisabled(True)

    def show(self) -> None:
        """Show this widget."""

        caption = self._action.caption()
        if not caption:
            caption = self.cursor().metadata().alias()

        if not self.cursor().isValid():
            self.cursor().model().refresh()

        if self.cursor().modeAccess() in (
            self.cursor().Insert,
            self.cursor().Edit,
            self.cursor().Browse,
        ):
            self.cursor().transaction()
            self.initTransLevel = self.cursor().transactionLevel()
            self.setCaptionWidget(caption)
            iface = getattr(self.script, "iface", None)
            if iface is not None:
                self.cursor().setContext(iface)
        if self.cursor().modeAccess() == pnsqlcursor.PNSqlCursor.Insert:
            self.showAcceptContinue_ = True
        else:
            self.showAcceptContinue_ = False

        self.loadControls()
        super(FLFormRecordDB, self).show()

    def inicializeControls(self) -> None:
        """Initialize UI controls for this form."""
        from pineboolib.fllegacy.flfielddb import FLFieldDB

        for child_ in self.findChildren(QtWidgets.QWidget):
            if isinstance(child_, FLFieldDB):
                loaded = getattr(child_, "_loaded", None)
                if loaded is False:
                    QtCore.QTimer.singleShot(0, child_.load)

    def show_and_wait(self) -> None:
        """Show this form blocking for exit."""
        if self.loop:
            raise Exception("show_and_wait(): Se ha detectado una llamada recursiva")

        self.loop = True
        self.show()
        if self.eventloop:
            self.eventloop.exec_()

        self.loop = False

    def hide(self) -> None:
        """Hide this form."""
        if self.loop:
            self.eventloop.exit()
