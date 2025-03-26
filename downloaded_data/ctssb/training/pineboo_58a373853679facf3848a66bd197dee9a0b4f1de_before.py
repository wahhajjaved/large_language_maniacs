"""Ebcomportamiento module."""
# -*- coding: utf-8 -*-
from pineboolib.qsa import qsa
from typing import Any, Union
from PyQt5 import QtWidgets, QtCore


class FormInternalObj(qsa.FormDBWidget):
    """FormInternalObj class."""

    def _class_init(self) -> None:
        """Inicialize."""
        pass

    def main(self) -> None:
        """Entry function."""

        app_ = qsa.aqApp
        if app_ is None:
            return
        mng = app_.db().managerModules()
        self.w_ = mng.createUI(u"ebcomportamiento.ui")
        w = self.w_
        botonAceptar = w.findChild(QtWidgets.QWidget, u"pbnAceptar")
        boton_aceptar_tmp = w.findChild(QtWidgets.QWidget, u"pbn_temporales")
        botonCancelar = w.findChild(QtWidgets.QWidget, u"pbnCancelar")
        botonCambiarColor = w.findChild(QtWidgets.QWidget, u"pbnCO")
        self.module_connect(botonAceptar, u"clicked()", self, u"guardar_clicked")
        self.module_connect(botonCancelar, u"clicked()", self, u"cerrar_clicked")
        self.module_connect(botonCambiarColor, u"clicked()", self, u"seleccionarColor_clicked")
        self.module_connect(boton_aceptar_tmp, u"clicked()", self, u"cambiar_temporales_clicked")
        self.cargarConfiguracion()
        self.initEventFilter()
        w.show()

    def cargarConfiguracion(self) -> None:
        """Load configuration."""
        w = self.w_
        w.findChild(QtWidgets.QWidget, u"cbFLTableDC").setChecked(
            self.leerValorLocal("FLTableDoubleClick")
        )
        w.findChild(QtWidgets.QWidget, u"cbFLTableSC").setChecked(
            self.leerValorLocal("FLTableShortCut")
        )
        w.findChild(QtWidgets.QWidget, u"cbFLTableCalc").setChecked(
            self.leerValorLocal("FLTableExport2Calc")
        )
        w.findChild(QtWidgets.QWidget, u"cbDebuggerMode").setChecked(
            self.leerValorLocal("isDebuggerMode")
        )
        w.findChild(QtWidgets.QWidget, u"cbSLConsola").setChecked(self.leerValorLocal("SLConsola"))
        w.findChild(QtWidgets.QWidget, u"cbSLInterface").setChecked(
            self.leerValorLocal("SLInterface")
        )
        w.findChild(QtWidgets.QWidget, u"leCallFunction").setText(
            self.leerValorLocal("ebCallFunction")
        )
        w.findChild(QtWidgets.QWidget, u"leMaxPixImages").setText(
            self.leerValorLocal("maxPixImages")
        )
        w.findChild(QtWidgets.QWidget, u"leNombreVertical").setText(
            self.leerValorGlobal("verticalName")
        )
        w.findChild(QtWidgets.QWidget, u"cbFLLarge").setChecked(
            self.leerValorGlobal("FLLargeMode") == "True"
        )
        w.findChild(QtWidgets.QWidget, u"cbPosInfo").setChecked(
            self.leerValorGlobal("PosInfo") == "True"
        )
        w.findChild(QtWidgets.QWidget, u"cbMobile").setChecked(self.leerValorLocal("mobileMode"))
        w.findChild(QtWidgets.QWidget, u"cbDeleteCache").setChecked(
            self.leerValorLocal("deleteCache")
        )
        w.findChild(QtWidgets.QWidget, u"cbParseProject").setChecked(
            self.leerValorLocal("parseProject")
        )
        w.findChild(QtWidgets.QWidget, u"cbActionsMenuRed").setChecked(
            self.leerValorLocal("ActionsMenuRed")
        )
        w.findChild(QtWidgets.QWidget, u"cbSpacerLegacy").setChecked(
            self.leerValorLocal("spacerLegacy")
        )
        w.findChild(QtWidgets.QWidget, u"cbParseModulesOnLoad").setChecked(
            self.leerValorLocal("parseModulesOnLoad")
        )
        w.findChild(QtWidgets.QWidget, u"cb_traducciones").setChecked(
            self.leerValorLocal("translations_from_qm")
        )
        w.findChild(QtWidgets.QWidget, "le_temporales").setText(self.leerValorLocal("temp_dir"))
        w.findChild(QtWidgets.QWidget, "cb_kut_debug").setChecked(
            self.leerValorLocal("kugar_debug_mode")
        )
        w.findChild(QtWidgets.QWidget, "cb_no_borrar_cache").setChecked(
            self.leerValorLocal("keep_general_cache")
        )
        w.findChild(QtWidgets.QWidget, "cb_snapshot").setChecked(
            self.leerValorLocal("show_snaptshop_button")
        )
        w.findChild(QtWidgets.QWidget, "cb_imagenes").setChecked(
            self.leerValorLocal("no_img_cached")
        )
        w.findChild(QtWidgets.QWidget, "cb_dbadmin").setChecked(
            self.leerValorLocal("dbadmin_enabled")
        )
        w.findChild(QtWidgets.QWidget, "cb_disable_mtdparser").setChecked(
            self.leerValorLocal("orm_parser_disabled")
        )
        w.findChild(QtWidgets.QWidget, "cb_disable_orm_load").setChecked(
            self.leerValorLocal("orm_load_disabled")
        )
        autoComp = self.leerValorLocal("autoComp")
        if not autoComp or autoComp == "OnDemandF4":
            autoComp = "Bajo Demanda (F4)"
        elif autoComp == "NeverAuto":
            autoComp = "Nunca"
        else:
            autoComp = "Siempre"
        w.findChild(QtWidgets.QWidget, u"cbAutoComp").setCurrentText = autoComp

        w.findChild(QtWidgets.QWidget, u"leCO").hide()
        self.colorActual_ = self.leerValorLocal("colorObligatorio")
        if not self.colorActual_:
            self.colorActual_ = "#FFE9AD"

        w.findChild(QtWidgets.QWidget, u"leCO").setStyleSheet(
            "background-color:" + self.colorActual_
        )

        # Actualizaciones.
        from pineboolib.core.utils.utils_base import filedir
        import os

        if os.path.exists(filedir("../.git")):
            w.findChild(QtWidgets.QWidget, "cb_git_activar").setChecked(
                self.leerValorLocal("git_updates_enabled")
            )
            ruta = self.leerValorLocal("git_updates_repo")
            if ruta is False:
                ruta = "https://github.com/Aulla/pineboo.git"
            w.findChild(QtWidgets.QWidget, "le_git_ruta").setText(ruta)
            self.module_connect(
                w.findChild(QtWidgets.QWidget, "pb_git_test"),
                u"clicked()",
                self,
                "search_git_updates",
            )
        else:
            w.findChild(QtWidgets.QWidget, "tbwLocales").setTabEnabled("tab_updates", False)

        w.findChild(QtWidgets.QWidget, u"leCO").show()

    def search_git_updates(self) -> None:
        """Searh for pineboo updates."""
        url = self.w_.findChild(QtWidgets.QWidget, "le_git_ruta").text
        qsa.sys.search_git_updates(url)

    def leerValorGlobal(self, valor_name: str = None) -> Any:
        """Return global value."""
        util = qsa.FLUtil()
        value = util.sqlSelect("flsettings", "valor", "flkey='%s'" % valor_name)

        if value is None:
            value = ""

        return value

    def grabarValorGlobal(self, valor_name: str, value: Union[str, bool]) -> None:
        """Set global value."""
        util = qsa.FLUtil()
        if not util.sqlSelect("flsettings", "flkey", "flkey='%s'" % valor_name):
            util.sqlInsert("flsettings", "flkey,valor", "%s,%s" % (valor_name, value))
        else:
            util.sqlUpdate("flsettings", u"valor", str(value), "flkey = '%s'" % valor_name)

    def leerValorLocal(self, valor_name: str) -> Any:
        """Return local value."""
        from pineboolib.core.settings import config

        if valor_name in ("isDebuggerMode", "dbadmin_enabled"):
            valor = config.value("application/%s" % valor_name, False)
        else:
            if valor_name in (
                "ebCallFunction",
                "maxPixImages",
                "kugarParser",
                "colorObligatorio",
                "temp_dir",
                "git_updates_repo",
            ):
                valor = config.value("ebcomportamiento/%s" % valor_name, "")
                if valor_name == "temp_dir" and valor == "":
                    app_ = qsa.aqApp
                    if app_ is None:
                        return ""

                    valor = app_.tmp_dir()

            else:
                valor = config.value("ebcomportamiento/%s" % valor_name, False)
        return valor

    def grabarValorLocal(self, valor_name: str, value: Union[str, bool]) -> None:
        """Set local value."""
        from pineboolib.core.settings import config

        if valor_name in ("isDebuggerMode", "dbadmin_enabled"):
            config.set_value("application/%s" % valor_name, value)
        else:
            if valor_name == "maxPixImages" and value is None:
                value = 600
            config.set_value("ebcomportamiento/%s" % valor_name, value)

    def initEventFilter(self) -> None:
        """Inicialize event filter."""
        w = self.w_
        w.eventFilterFunction = qsa.ustr(w.objectName(), u".eventFilter")
        w.allowedEvents = qsa.Array([qsa.AQS.Close])
        w.installEventFilter(w)

    def eventFilter(self, o: QtWidgets.QWidget, e: QtCore.QEvent) -> bool:
        """Event filter."""
        if type(e) == qsa.AQS.Close:
            self.cerrar_clicked()

        return True

    def cerrar_clicked(self) -> None:
        """Close the widget."""
        self.w_.close()

    def guardar_clicked(self) -> None:
        """Save actual configuration."""
        w = self.w_
        self.grabarValorGlobal(
            "verticalName", w.findChild(QtWidgets.QWidget, u"leNombreVertical").text()
        )
        self.grabarValorLocal(
            "FLTableDoubleClick", w.findChild(QtWidgets.QWidget, u"cbFLTableDC").isChecked()
        )
        self.grabarValorLocal(
            "FLTableShortCut", w.findChild(QtWidgets.QWidget, u"cbFLTableSC").isChecked()
        )
        self.grabarValorLocal(
            "FLTableExport2Calc", w.findChild(QtWidgets.QWidget, u"cbFLTableCalc").isChecked()
        )
        self.grabarValorLocal(
            "isDebuggerMode", w.findChild(QtWidgets.QWidget, u"cbDebuggerMode").isChecked()
        )
        self.grabarValorLocal(
            "SLConsola", w.findChild(QtWidgets.QWidget, u"cbSLConsola").isChecked()
        )
        self.grabarValorLocal(
            "SLInterface", w.findChild(QtWidgets.QWidget, u"cbSLInterface").isChecked()
        )
        self.grabarValorLocal(
            "ebCallFunction", w.findChild(QtWidgets.QWidget, u"leCallFunction").text()
        )
        self.grabarValorLocal(
            "maxPixImages", w.findChild(QtWidgets.QWidget, u"leMaxPixImages").text()
        )
        self.grabarValorLocal("colorObligatorio", self.colorActual_)
        self.grabarValorLocal(
            "ActionsMenuRed", w.findChild(QtWidgets.QWidget, u"cbActionsMenuRed").isChecked()
        )
        self.grabarValorGlobal(
            "FLLargeMode", w.findChild(QtWidgets.QWidget, u"cbFLLarge").isChecked()
        )
        self.grabarValorGlobal("PosInfo", w.findChild(QtWidgets.QWidget, u"cbPosInfo").isChecked())
        self.grabarValorLocal(
            "deleteCache", w.findChild(QtWidgets.QWidget, u"cbDeleteCache").isChecked()
        )
        self.grabarValorLocal(
            "parseProject", w.findChild(QtWidgets.QWidget, u"cbParseProject").isChecked()
        )
        self.grabarValorLocal("mobileMode", w.findChild(QtWidgets.QWidget, u"cbMobile").isChecked())
        self.grabarValorLocal(
            "spacerLegacy", w.findChild(QtWidgets.QWidget, u"cbSpacerLegacy").isChecked()
        )
        self.grabarValorLocal(
            "parseModulesOnLoad",
            w.findChild(QtWidgets.QWidget, u"cbParseModulesOnLoad").isChecked(),
        )
        self.grabarValorLocal(
            "translations_from_qm", w.findChild(QtWidgets.QWidget, u"cb_traducciones").isChecked()
        )
        self.grabarValorLocal("temp_dir", w.findChild(QtWidgets.QWidget, "le_temporales").text())
        self.grabarValorLocal(
            "kugar_debug_mode", w.findChild(QtWidgets.QWidget, "cb_kut_debug").isChecked()
        )
        self.grabarValorLocal(
            "keep_general_cache", w.findChild(QtWidgets.QWidget, "cb_no_borrar_cache").isChecked()
        )
        self.grabarValorLocal(
            "git_updates_enabled", w.findChild(QtWidgets.QWidget, "cb_git_activar").isChecked()
        )
        self.grabarValorLocal(
            "git_updates_repo", w.findChild(QtWidgets.QWidget, "le_git_ruta").text
        )
        self.grabarValorLocal(
            "show_snaptshop_button", w.findChild(QtWidgets.QWidget, "cb_snapshot").isChecked()
        )
        self.grabarValorLocal(
            "no_img_cached", w.findChild(QtWidgets.QWidget, "cb_imagenes").isChecked()
        )
        self.grabarValorLocal(
            "dbadmin_enabled", w.findChild(QtWidgets.QWidget, "cb_dbadmin").isChecked()
        )
        self.grabarValorLocal(
            "orm_parser_disabled",
            w.findChild(QtWidgets.QWidget, "cb_disable_mtdparser").isChecked(),
        )
        self.grabarValorLocal(
            "orm_load_disabled", w.findChild(QtWidgets.QWidget, "cb_disable_orm_load").isChecked()
        )

        autoComp = w.findChild(QtWidgets.QWidget, u"cbAutoComp").currentText()
        if autoComp == "Nunca":
            autoComp = "NeverAuto"
        elif autoComp == "Bajo Demanda (F4)":
            autoComp = "OnDemandF4"
        else:
            autoComp = "AlwaysAuto"
        self.grabarValorLocal("autoComp", autoComp)
        self.cerrar_clicked()

    def seleccionarColor_clicked(self) -> None:
        """Set mandatory color."""
        self.colorActual_ = qsa.AQS.ColorDialog_getColor(self.colorActual_, self.w_).name()
        self.w_.findChild(QtWidgets.QWidget, u"leCO").setStyleSheet(
            "background-color:" + self.colorActual_
        )

    def fixPath(self, ruta: str) -> str:
        """Return a fixed path."""
        rutaFixed = ""
        if qsa.sys.osName() == u"WIN32":
            barra = u"\\"
            while ruta != rutaFixed:
                rutaFixed = ruta
                ruta = ruta.replace(u"/", barra)
            if not rutaFixed.endswith(barra):
                rutaFixed += u"\\"

        else:
            rutaFixed = ruta

        return rutaFixed

    def cambiar_temporales_clicked(self) -> None:
        """Change temp folder."""
        old_dir = self.w_.findChild(QtWidgets.QWidget, "le_temporales").text()
        old_dir = self.fixPath(old_dir)
        new_dir = qsa.FileDialog.getExistingDirectory(old_dir)
        if new_dir and new_dir is not old_dir:
            self.w_.findChild(QtWidgets.QWidget, "le_temporales").setText(new_dir)
            from pineboolib import application

            application.project.tmpdir = new_dir


form = None
