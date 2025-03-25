"""Aqobjectquerylist module."""

import unittest
from pineboolib.loader.main import init_testing, finish_testing


class TestAQObjectQueryList(unittest.TestCase):
    """TestAQObjectQueryList Class."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure pineboo is initialized for testing."""
        init_testing()

    def test_aqobject_query_list(self) -> None:
        """Test AQObjectQueryList function."""
        from pineboolib import application
        from pineboolib.qsa import qsa
        from pineboolib.plugins.mainform.eneboo import eneboo

        main_form_class = getattr(eneboo, "MainForm", None)
        self.assertTrue(main_form_class)
        application.PROJECT.main_window = main_form_class()
        self.assertTrue(application.PROJECT.main_window)
        if application.PROJECT.main_window is not None:
            application.PROJECT.main_window.initScript()
            application.PROJECT.main_window.show()

            list_ = qsa.AQObjectQueryList(
                application.PROJECT.main_window, "QAction", None, False, True
            )
            self.assertTrue(len(list_) in [89, 96, 101], "El tamaño devuelto es %s" % len(list_))

    @classmethod
    def tearDownClass(cls) -> None:
        """Ensure test clear all data."""
        finish_testing()
