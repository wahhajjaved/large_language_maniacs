"""Test_flsqlite module."""
import unittest
from pineboolib.loader.main import init_testing, finish_testing
from .. import flsqlite


class TestFLSqlite(unittest.TestCase):
    """TestFLSqlite Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_basic_1(self) -> None:
        """Basics test 1."""

        driver = flsqlite.FLSQLITE()

        self.assertEqual(driver.formatValueLike("bool", "true", False), "=0")
        self.assertEqual(driver.formatValueLike("date", "2020-01-27", True), "LIKE '%%27-01-2020'")

        self.assertEqual(driver.formatValue("bool", "false", True), "0")
        self.assertEqual(driver.formatValue("time", "", True), "")

        # self.assertFalse(driver.transaction_rollback())
        # self.assertFalse(driver.save_point(0))
        # self.assertFalse(driver.transaction_commit())
        # self.assertFalse(driver.transaction())
        # self.assertFalse(driver.save_point_release(0))

        self.assertEqual(driver.setType("String", 20), "VARCHAR(20)")
        self.assertEqual(driver.setType("sTring", 0), "VARCHAR")
        self.assertEqual(driver.setType("Double"), "FLOAT")
        self.assertEqual(driver.setType("Bool"), "BOOLEAN")
        self.assertEqual(driver.setType("DATE"), "VARCHAR(20)")
        self.assertEqual(driver.setType("pixmap"), "TEXT")
        self.assertEqual(driver.setType("bytearray"), "CLOB")
        self.assertEqual(driver.setType("timestamp"), "DATETIME")
        self.assertEqual(
            driver.process_booleans("'true' AND false AND 'false'"), "1 AND false AND 0"
        )

    def test_basic_2(self) -> None:
        """Basics test 2."""
        from pineboolib.application.database import pnsqlcursor

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        sql = (
            "CREATE TABLE fltest (id INTEGER PRIMARY KEY,string_field VARCHAR NULL,date_field VARCHAR(20)"
            + " NULL,time_field VARCHAR(20) NULL,double_field FLOAT NULL,bool_field BOOLEAN NULL"
            + ",uint_field INTEGER NULL,bloqueo BOOLEAN NOT NULL);CREATE INDEX fltest_pkey ON fltest (id)"
        )
        sql2 = (
            "CREATE TABLE fltest (id INTEGER PRIMARY KEY,string_field VARCHAR NULL,date_field VARCHAR(20)"
            + " NULL,time_field VARCHAR(20) NULL,double_field FLOAT NULL,bool_field BOOLEAN NULL"
            + ",uint_field INTEGER NULL,bloqueo BOOLEAN NOT NULL);"
        )
        driver = flsqlite.FLSQLITE()

        self.assertEqual(sql, driver.sqlCreateTable(cursor.metadata()))
        self.assertEqual(sql2, driver.sqlCreateTable(cursor.metadata(), False))

    def test_basic_3(self) -> None:
        """Basics test 3."""

        from pineboolib.application.database import pnsqlcursor

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        conn_ = cursor.db()
        ret = conn_.driver().recordInfo2("fltest")
        self.assertEqual(["id", "uint", True, 0, None, None, True], ret[0])
        self.assertTrue(conn_.alterTable(cursor.metadata()))

    def test_mismatched(self) -> None:
        """Test mismatched table."""

        from pineboolib.application.database import pnsqlcursor

        cursor = pnsqlcursor.PNSqlCursor("fltest")
        cursor2 = pnsqlcursor.PNSqlCursor("fltest3")

        metadata = cursor.metadata()
        metadata2 = cursor2.metadata()

        self.assertFalse(cursor.db().driver().mismatchedTable("fltest", metadata))
        self.assertTrue(cursor.db().driver().mismatchedTable("fltest2", metadata))
        self.assertTrue(cursor.db().driver().mismatchedTable("fltest3", metadata))
        metadata.removeFieldMD("date_field")
        self.assertTrue(cursor.db().driver().mismatchedTable("fltest", metadata))
        self.assertTrue(cursor.db().driver().mismatchedTable("fltest", metadata2))
        self.assertFalse(cursor.db().driver().mismatchedTable("fltest3", metadata2))

    def test_invalid_metadata(self) -> None:
        """Test invalid metadata."""
        from pineboolib.application.database import pnsqlcursor

        with self.assertRaises(Exception):
            pnsqlcursor.PNSqlCursor("fltest6").metadata()

        pnsqlcursor.PNSqlCursor("fltest").metadata()

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()
