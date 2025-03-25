"""Test_aqs module."""

import unittest
from pineboolib.loader.main import init_testing, finish_testing


class TestAQSql(unittest.TestCase):
    """TestAQSql Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_delete(self) -> None:
        """Delete test."""
        from pineboolib.application.database import pnsqlcursor
        from pineboolib.fllegacy.aqsobjects import aqsql

        cur_areas = pnsqlcursor.PNSqlCursor("flareas")
        cur_areas.setModeAccess(cur_areas.Insert)
        cur_areas.refreshBuffer()
        cur_areas.setValueBuffer("idarea", "X")
        cur_areas.setValueBuffer("descripcion", "descripcion area x")
        self.assertTrue(cur_areas.commitBuffer())
        self.assertEqual(cur_areas.size(), 1)
        aq_ = aqsql.AQSql()

        self.assertTrue(aq_.del_("flareas", "idarea='X'"))
        self.assertEqual(cur_areas.size(), 0)
        cur_areas.refresh()
        self.assertEqual(cur_areas.size(), 0)

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()
