"""Test_systype module."""

import unittest
from pineboolib.loader.main import init_testing, finish_testing
from pineboolib.fllegacy import systype
from . import fixture_path


class TestSysType(unittest.TestCase):
    """TestSysType Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_file_write(self) -> None:
        """Test FileWrite attributes."""

        from pineboolib.application import types
        from pineboolib import application
        import os

        qsa_sys = systype.SysType()
        txt = "avión, cañita"
        path_1 = "%s/test_systype_one_iso_8859-15.txt" % application.PROJECT.tmpdir
        path_2 = "%s/test_systype_one_utf-8.txt" % application.PROJECT.tmpdir

        if os.path.exists(path_1):
            os.remove(path_1)

        if os.path.exists(path_2):
            os.remove(path_2)

        qsa_sys.fileWriteIso(path_1, txt)
        qsa_sys.fileWriteUtf8(path_2, txt)

        file_1 = types.File(path_1, "ISO-8859-15")
        file_2 = types.File(path_2, "UTF-8")

        result_1 = file_1.read()
        result_2 = file_2.read()

        self.assertEqual(result_1, txt)
        self.assertEqual(result_2, txt)

    def test_translation(self) -> None:
        """Test translation function."""
        from pineboolib.qsa import qsa

        qsa_sys = systype.SysType()

        qsa.aqApp.loadTranslationFromModule("sys", "es")
        self.assertEqual(qsa_sys.translate("scripts", "hola python"), "Holaaaaa")
        self.assertEqual(qsa_sys.translate("python", "hola python sin group"), "Hola de nuevo!")

    def test_eneboopkg(self) -> None:
        """Test eneboopkgs load."""
        from pineboolib.qsa import qsa
        import os

        qsa_sys = systype.SysType()
        path = fixture_path("principal.eneboopkg")
        self.assertTrue(os.path.exists(path))
        qsa_sys.loadModules(path, False)
        qsa_sys.registerUpdate(path)

        qry = qsa.FLSqlQuery()
        qry.setTablesList("flfiles")
        qry.setSelect("count(nombre)")
        qry.setFrom("flfiles")
        qry.setWhere("1=1")
        self.assertTrue(qry.exec_())
        self.assertTrue(qry.first())
        self.assertEqual(qry.value(0), 148)

        qry_2 = qsa.FLSqlQuery()
        qry_2.setTablesList("flfiles")
        qry_2.setSelect("nombre")
        qry_2.setFrom("flfiles")
        qry_2.setWhere("nombre='impuestos.py'")
        self.assertTrue(qry_2.exec_())
        self.assertTrue(qry_2.first())
        self.assertEqual(qry_2.value(0), "impuestos.py")

    def test_run_transaction(self) -> None:
        """Test run transaction."""
        from pineboolib.qsa import qsa

        o_param_ = qsa.Object()
        fun_ = "test"
        o_param_.errorMsg = qsa.sys.translate("Error en la función %s" % fun_)
        f_1 = qsa.Function("oParam", "return true;")
        result_1 = qsa.sys.runTransaction(f_1, o_param_)
        self.assertTrue(result_1)
        f_2 = qsa.Function("oParam", 'oParam.errorMsg = "Holaa";return false;')
        result_2 = qsa.sys.runTransaction(f_2, o_param_)
        self.assertFalse(result_2)

    def test_transaction_level(self) -> None:
        from pineboolib.qsa import qsa
        from pineboolib.application.metadata import pnrelationmetadata

        sys_1 = systype.SysType()
        sys_2 = qsa.sys

        self.assertEqual(sys_1.transactionLevel(), 0)
        self.assertEqual(sys_2.transactionLevel(), 0)

        cur_areas = qsa.FLSqlCursor("flareas")

        cursor = qsa.FLSqlCursor("flareas")
        cursor.setModeAccess(cursor.Insert)
        cursor.refreshBuffer()
        cursor.setValueBuffer("bloqueo", True)
        cursor.setValueBuffer("idarea", "H")
        cursor.setValueBuffer("descripcion", "Área de prueba H")
        self.assertTrue(cursor.commitBuffer())
        rel = pnrelationmetadata.PNRelationMetaData(
            "flareas", "idarea", pnrelationmetadata.PNRelationMetaData.RELATION_1M
        )
        rel.setField("idarea")
        cur_areas.select("idarea ='H'")
        cur_areas.first()
        self.assertEqual(cur_areas.valueBuffer("idarea"), "H")
        cur_areas.setModeAccess(cur_areas.Edit)
        cur_areas.refreshBuffer()
        cur_modulos = qsa.FLSqlCursor("flmodules", True, "default", cur_areas, rel)
        cur_modulos.select()
        cur_modulos.refreshBuffer()
        self.assertEqual(sys_1.transactionLevel(), 0)
        self.assertEqual(sys_2.transactionLevel(), 0)

        cur_modulos.setModeAccess(cur_modulos.Insert)
        cur_modulos.transaction()
        self.assertEqual(sys_1.transactionLevel(), 1)
        self.assertEqual(sys_2.transactionLevel(), 1)
        self.assertTrue(cur_modulos.rollback())

    # def test_mod_main_widget(self) -> None:
    #    """Test modMainWidget."""
    #    from pineboolib.qsa import qsa

    #    mw = qsa.sys.modMainWidget("sys")
    #    self.assertTrue(mw)
    def test_translations(self) -> None:
        """Test translations functions."""

        sys = systype.SysType()

        self.assertEqual(sys.translate("MetaData", "123"), "123")

    def test_pixmap(self) -> None:
        """Text str to pixmap function."""
        from pineboolib.application.database import pnsqlcursor
        from PyQt5 import QtCore

        sys = systype.SysType()
        cursor = pnsqlcursor.PNSqlCursor("flmodules")
        cursor.select("1=1")
        cursor.first()
        buffer_ = cursor.buffer()
        self.assertTrue(buffer_)
        if buffer_:
            icono_txt = buffer_.value("icono")
            pixmap = sys.toPixmap(str(icono_txt))
            self.assertTrue(pixmap)
            res_txt = sys.fromPixmap(pixmap)
            self.assertTrue(res_txt.find("22 22 214 2") > -1)
            pixmap_2 = sys.scalePixmap(pixmap, 50, 50, QtCore.Qt.KeepAspectRatio)
            self.assertTrue(pixmap_2)

    def test_project_info(self) -> None:
        """Test information functions."""
        sys = systype.SysType()

        document_ = sys.mvProjectXml()
        self.assertEqual(document_.toString(), "")

        list_modules = sys.mvProjectModules()
        self.assertEqual(list_modules, [])

        list_extensions = sys.mvProjectExtensions()
        self.assertEqual(list_extensions, [])
        self.assertEqual(sys.calculateShaGlobal(), "cfc09ed22ee2b16a0c571bb99f383b7dd4113553")
        changes = sys.localChanges()
        self.assertEqual(changes["size"], 96)
        res_ = sys.xmlFilesDefBd()
        self.assertTrue(res_)

    def test_project_info_2(self) -> None:
        """Test information functions."""
        from pineboolib import application

        sys = systype.SysType()
        res_1 = sys.xmlModule("flfactppal")
        self.assertTrue(res_1)
        path_ = application.PROJECT.tmpdir
        sys.exportModule("flfactppal", path_)
        sys.importModule("%s/flfactppal/flfactppal.mod" % path_)

    def test_project_others(self) -> None:
        """Test basics functions."""
        sys = systype.SysType()
        list_1 = sys.getWidgetList("formRecordclientes", "FLFieldDB")
        list_2 = sys.getWidgetList("formRecordclientes", "FLTableDB")
        list_3 = sys.getWidgetList("formRecordclientes", "Button")
        self.assertTrue(list_3)
        self.assertTrue(list_1)
        self.assertTrue(list_2)

    def test_project_dump(self) -> None:
        """Test dump class."""
        from pineboolib import application

        ad_ = systype.AbanQDbDumper(
            application.PROJECT.conn_manager.useConn("default"), application.PROJECT.tmpdir, False
        )
        ad_.initDump()

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()


if __name__ == "__main__":
    unittest.main()
