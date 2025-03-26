#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module containing windows, widgets etc. to create the QATS application

@author: perl
"""

import logging
import os
from itertools import cycle
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QWidget, QHBoxLayout, \
    QListView, QGroupBox, QLabel, QRadioButton, QCheckBox, QDoubleSpinBox, QVBoxLayout, QPushButton, QAction, \
    QLineEdit, QComboBox, QSplitter, QFrame, QTabBar
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from pkg_resources import resource_filename, get_distribution, DistributionNotFound

from .logger import QLogger
from .threading import Worker
from .models import CustomSortFilterProxyModel
from .widgets import CustomTabWidget
from ..tsdb import TsDB
from ..stats import empirical_cdf
from .funcs import (
    export_to_file,
    import_from_file,
    read_timeseries,
    calculate_trace,
    calculate_psd,
    calculate_rfc,
    calculate_weibull_fit
)


LOGGING_LEVELS = dict(
    debug=logging.DEBUG,
    info=logging.INFO,
    warning=logging.WARNING,
    error=logging.ERROR,
)

# todo: implement multithreading for creating special plots (tools)
# todo: settings on file menu: nperseg= and detrend= for welch psd, Hz, rad/s or s for filters
# todo: add technical guidance and result interpretation to help menu, link docs website
# todo: add 'export' option to file menu: response statistics summary (mean, std, skew, kurt, tz, weibull distributions, gumbel distributions etc.)
# todo: read .csv file and .xlsx files assuming keys in first row and time vector in first column
# todo: read orcaflex time series files


class Qats(QMainWindow):
    """
    Main window for the QATS application.

    Contain widgets for plotting time series, power spectra and statistics.

    Series of data are loaded from a .ts file, and their names are displayed in a checkable list view. The user can
    select the series it wants from the list and plot them on a matplotlib canvas. The prodlinelib python package is
    used for loading time series from file, perform signal processing, calculating power spectra and statistics and
    plotting.
    """

    def __init__(self, parent=None, files_on_init=None, logging_level="info"):
        """
        Initiate main window

        Parameters
        ----------
        parent : QMainWindow, optional
            Parent window
        files_on_init : str|iterable, optional
            File names to be loaded on initiation
        logging_level : str, optional
            Logging level. Valid options: 'debug', 'info' (default), 'warning', 'error'.

        """
        super(Qats, self).__init__(parent)

        assert logging_level in LOGGING_LEVELS, "invalid logging level: '%s'" % logging_level

        # create pool for managing threads
        self.threadpool = QThreadPool()

        # window title and icon (assumed located in 'images' at same level)
        self.setWindowTitle("QATS")
        self.icon = QIcon(resource_filename("qats.app", "qats.ico"))
        self.setWindowIcon(self.icon)

        # create statusbar
        self.db_status = QLabel()
        self.statusBar().addPermanentWidget(self.db_status, stretch=0)

        # enable dropping url objects
        self.setAcceptDrops(True)

        # create frames
        self.main_frame = QFrame()
        self.setCentralWidget(self.main_frame)
        self.upper_left_frame = QFrame()
        self.bottom_left_frame = QFrame()
        self.left_frame = QFrame()
        self.right_frame = QFrame()

        # create tabs
        self.tabs = CustomTabWidget()

        # time domain plot tab
        w = QWidget()
        self.tabs.addTab(w, "Time history")
        self.tabs.setTabToolTip(0, "Plot data versus time for selected time series")
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)     # disable close button
        self.history_fig = Figure()
        self.history_canvas = FigureCanvas(self.history_fig)
        self.history_canvas.setParent(w)
        self.history_axes = self.history_fig.add_subplot(111)
        self.history_mpl_toolbar = NavigationToolbar(self.history_canvas, self.upper_left_frame)
        vbox = QVBoxLayout()
        vbox.addWidget(self.history_canvas)
        vbox.addWidget(self.history_mpl_toolbar)
        w.setLayout(vbox)

        # power spectrum plot tab
        w = QWidget()
        self.tabs.addTab(w, "Power spectrum")
        self.tabs.setTabToolTip(1, "Plot power spectral density versus frequency for selected time series")
        self.tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)  # disable close button
        self.spectrum_fig = Figure()
        self.spectrum_canvas = FigureCanvas(self.spectrum_fig)
        self.spectrum_canvas.setParent(w)
        self.spectrum_axes = self.spectrum_fig.add_subplot(111)
        self.spectrum_mpl_toolbar = NavigationToolbar(self.spectrum_canvas, self.upper_left_frame)
        vbox = QVBoxLayout()
        vbox.addWidget(self.spectrum_canvas)
        vbox.addWidget(self.spectrum_mpl_toolbar)
        w.setLayout(vbox)

        # weibull paper plot tab
        w = QWidget()
        self.tabs.addTab(w, "Maxima/Minima CDF")
        self.tabs.setTabToolTip(2, "Plot fitted Weibull cumulative distribution function to maxima/minima of "
                                   "selected time series")
        self.tabs.tabBar().setTabButton(2, QTabBar.RightSide, None)  # disable close button
        self.weibull_fig = Figure()
        self.weibull_canvas = FigureCanvas(self.weibull_fig)
        self.weibull_canvas.setParent(w)
        self.weibull_axes = self.weibull_fig.add_subplot(111)
        self.weibull_mpl_toolbar = NavigationToolbar(self.weibull_canvas, self.upper_left_frame)
        vbox = QVBoxLayout()
        vbox.addWidget(self.weibull_canvas)
        vbox.addWidget(self.weibull_mpl_toolbar)
        w.setLayout(vbox)

        # cycle distribution plot tab
        w = QWidget()
        self.tabs.addTab(w, "Cycle distribution")
        self.tabs.setTabToolTip(3, "Plot distribution of cycle magnitude versus cycle count for "
                                   "selected time series")
        self.tabs.tabBar().setTabButton(3, QTabBar.RightSide, None)  # disable close button
        self.cycles_fig = Figure()
        self.cycles_canvas = FigureCanvas(self.cycles_fig)
        self.cycles_canvas.setParent(w)
        self.cycles_axes = self.cycles_fig.add_subplot(111)
        self.cycles_mpl_toolbar = NavigationToolbar(self.cycles_canvas, self.upper_left_frame)
        vbox = QVBoxLayout()
        vbox.addWidget(self.cycles_canvas)
        vbox.addWidget(self.cycles_mpl_toolbar)
        w.setLayout(vbox)

        # add layout to main frame (need to go via layout)
        main_hbox = QHBoxLayout()
        main_hbox.addWidget(self.tabs)
        self.upper_left_frame.setLayout(main_hbox)

        # initiate time series data base and checkable model and view with filter
        self.db = TsDB()
        self.db_common_path = ""
        self.db_source_model = QStandardItemModel()
        self.db_proxy_model = CustomSortFilterProxyModel()
        self.db_proxy_model.setDynamicSortFilter(True)
        self.db_proxy_model.setSourceModel(self.db_source_model)
        self.db_view = QListView()
        self.db_view.setModel(self.db_proxy_model)
        self.db_view_filter_casesensitivity = QCheckBox("Case sensitive filter")
        self.db_view_filter_casesensitivity.setChecked(False)
        self.db_view_filter_pattern = QLineEdit()
        self.db_view_filter_pattern.setPlaceholderText("type filter text")
        self.db_view_filter_pattern.setText("")
        self.db_view_filter_syntax = QComboBox()
        self.db_view_filter_syntax.addItem("Wildcard", QRegExp.Wildcard)
        self.db_view_filter_syntax.addItem("Regular expression", QRegExp.RegExp)
        self.db_view_filter_syntax.addItem("Fixed string", QRegExp.FixedString)
        self.db_view_filter_pattern.textChanged.connect(self.model_view_filter_changed)
        self.db_view_filter_syntax.currentIndexChanged.connect(self.model_view_filter_changed)
        self.db_view_filter_casesensitivity.toggled.connect(self.model_view_filter_changed)
        self.model_view_filter_changed()
        # unselect all items
        self.select_button = QPushButton("&Select all")
        self.unselect_button = QPushButton("&Unselect all")
        self.select_button.clicked.connect(self.select_all_items_in_model)
        self.unselect_button.clicked.connect(self.unselect_all_items_in_model)
        view_group = QGroupBox("Select time series")
        view_layout = QVBoxLayout()
        view_filter_hbox = QHBoxLayout()
        view_filter_hbox.addWidget(self.db_view_filter_pattern)
        view_filter_hbox.addWidget(self.db_view_filter_syntax)
        view_layout.addLayout(view_filter_hbox)
        view_layout.addWidget(self.db_view_filter_casesensitivity)
        view_select_hbox = QHBoxLayout()
        view_select_hbox.addWidget(self.select_button)
        view_select_hbox.addWidget(self.unselect_button)
        view_layout.addLayout(view_select_hbox)
        view_layout.addWidget(self.db_view)
        view_group.setLayout(view_layout)

        # time window selection
        time_group = QGroupBox("Set data processing time window")
        time_group.setToolTip("Calculations performed only for data within specified time window")
        self.from_time = QDoubleSpinBox()  # time window
        self.to_time = QDoubleSpinBox()
        self.from_time.setRange(0, 1e12)
        self.to_time.setRange(0, 1e12)
        self.from_time.setEnabled(True)
        self.to_time.setEnabled(True)
        self.from_time.setSingleStep(0.01)
        self.to_time.setSingleStep(0.01)
        self.from_time.setSuffix("s")
        self.to_time.setSuffix("s")
        spins_hbox = QHBoxLayout()
        spins_hbox.addWidget(QLabel('from'))
        spins_hbox.addWidget(self.from_time)
        spins_hbox.addWidget(QLabel('to'))
        spins_hbox.addWidget(self.to_time)
        spins_hbox.addStretch(1)
        time_group.setLayout(spins_hbox)

        # set initial value of time window spin boxes
        self.from_time.setValue(0)
        self.to_time.setValue(1000000000000)

        # mutual exclusive peaks/troughs radio buttons
        minmax_group = QGroupBox("Select statistical quantity")
        minmax_group.setToolTip("Select maxima or minima as basis for the fitted and plotted cumulative"
                                " distribution functions. ")
        self.maxima = QRadioButton("Maxima")
        self.minima = QRadioButton("Minima")
        self.show_minmax = QCheckBox("Show in plot")
        self.maxima.setChecked(True)  # default maxima is checked
        minmax_hbox = QHBoxLayout()
        minmax_hbox.addWidget(self.maxima)
        minmax_hbox.addWidget(self.minima)
        minmax_hbox.addWidget(self.show_minmax)
        minmax_hbox.addStretch(1)
        minmax_group.setLayout(minmax_hbox)

        # filter selection and frequency window
        self.no_filter = QRadioButton("None")
        self.no_filter.setCheckable(False)
        self.no_filter.toggled.connect(self.on_no_filter)
        no_filter_hbox = QHBoxLayout()
        no_filter_hbox.addWidget(self.no_filter)

        self.lowpass = QRadioButton("Low-pass")
        self.lowpass.setCheckable(False)
        self.lowpass.toggled.connect(self.on_lowpass)
        self.lowpass_f = QDoubleSpinBox()
        self.lowpass_f.setEnabled(False)  # default opaque
        lowpass_hbox = QHBoxLayout()
        lowpass_hbox.addWidget(self.lowpass)
        lowpass_hbox.addStretch(1)
        lowpass_hbox.addWidget(QLabel("below"))
        lowpass_hbox.addWidget(self.lowpass_f)

        self.hipass = QRadioButton("High-pass")
        self.hipass.setCheckable(False)
        self.hipass.toggled.connect(self.on_hipass)
        self.hipass_f = QDoubleSpinBox()
        self.hipass_f.setEnabled(False)  # default opaque
        hipass_hbox = QHBoxLayout()
        hipass_hbox.addWidget(self.hipass)
        hipass_hbox.addStretch(1)
        hipass_hbox.addWidget(QLabel("above"))
        hipass_hbox.addWidget(self.hipass_f)

        self.bandpass = QRadioButton("Band-pass")
        self.bandpass.setCheckable(False)
        self.bandpass.toggled.connect(self.on_bandpass)
        self.bandpass_lf = QDoubleSpinBox()
        self.bandpass_hf = QDoubleSpinBox()
        self.bandpass_lf.setEnabled(False)  # default opaque
        self.bandpass_hf.setEnabled(False)  # default opaque
        bandpass_hbox = QHBoxLayout()
        bandpass_hbox.addWidget(self.bandpass)
        bandpass_hbox.addStretch(1)
        bandpass_hbox.addWidget(QLabel("between"))
        bandpass_hbox.addWidget(self.bandpass_lf)
        bandpass_hbox.addWidget(QLabel("and"))
        bandpass_hbox.addWidget(self.bandpass_hf)

        self.bandblock = QRadioButton("Band-block")
        self.bandblock.setCheckable(False)
        self.bandblock.toggled.connect(self.on_bandblock)
        self.bandblock_lf = QDoubleSpinBox()
        self.bandblock_hf = QDoubleSpinBox()
        self.bandblock_lf.setEnabled(False)  # default opaque
        self.bandblock_hf.setEnabled(False)  # default opaque
        bandblock_hbox = QHBoxLayout()
        bandblock_hbox.addWidget(self.bandblock)
        bandblock_hbox.addStretch(1)
        bandblock_hbox.addWidget(QLabel("between"))
        bandblock_hbox.addWidget(self.bandblock_lf)
        bandblock_hbox.addWidget(QLabel("and"))
        bandblock_hbox.addWidget(self.bandblock_hf)

        # set range, decimals and suffix of frequency filter range spin boxes
        for w in [self.lowpass_f, self.hipass_f, self.bandpass_lf, self.bandpass_hf, self.bandblock_lf,
                  self.bandblock_hf]:
            w.setRange(0.0, 50.)
            w.setDecimals(3)
            w.setSuffix("Hz")

        # make filter selection radio buttons checkable
        for w in [self.no_filter, self.lowpass, self.hipass, self.bandpass, self.bandblock]:
            w.setCheckable(True)

        # un-filtered data series by default
        self.no_filter.toggle()

        # stack radio-butttons and spin-boxes vertically
        filter_vbox = QVBoxLayout()
        for hb in [no_filter_hbox, lowpass_hbox, hipass_hbox, bandpass_hbox, bandblock_hbox]:
            filter_vbox.addLayout(hb)

        filter_group = QGroupBox("Apply frequency filter")
        filter_group.setLayout(filter_vbox)

        # show plots / update GUI
        self.display_button = QPushButton("&Display")
        self.display_button.clicked.connect(self.on_display)

        # create right hand vertical box layout and add data series check list,
        # time window spin boxes, show button, legend check box
        right_vbox = QVBoxLayout()
        right_vbox.addWidget(view_group)
        right_vbox.addWidget(time_group)
        right_vbox.addWidget(minmax_group)
        right_vbox.addWidget(filter_group)
        right_vbox.addWidget(self.display_button)

        # add layout to right hand frame
        self.right_frame.setLayout(right_vbox)

        # create logger widget
        self.logger = QLogger(self)
        self.logger.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        logging.getLogger().addHandler(self.logger)
        logging.getLogger().setLevel(LOGGING_LEVELS[logging_level])
        logger_layout = QVBoxLayout()
        logger_layout.addWidget(self.logger.widget)
        self.bottom_left_frame.setLayout(logger_layout)

        # add adjustable splitter to main window
        vertical_splitter = QSplitter(Qt.Vertical)
        vertical_splitter.addWidget(self.upper_left_frame)
        vertical_splitter.addWidget(self.bottom_left_frame)
        vbox = QVBoxLayout()
        vbox.addWidget(vertical_splitter)
        self.left_frame.setLayout(vbox)
        horizontal_splitter = QSplitter(Qt.Horizontal)
        horizontal_splitter.addWidget(self.left_frame)
        horizontal_splitter.addWidget(self.right_frame)
        hbox = QHBoxLayout()
        hbox.addWidget(horizontal_splitter)
        self.main_frame.setLayout(hbox)

        # create menubar, file menu and help menu
        self.menu_bar = self.menuBar()
        file_menu = self.menu_bar.addMenu("&File")
        tool_menu = self.menu_bar.addMenu("&Tools")
        help_menu = self.menu_bar.addMenu("&Help")

        # create File menu and actions
        import_action = QAction("&Import from file", self)
        import_action.setShortcut("Ctrl+I")
        import_action.setStatusTip("Import time series from file")
        import_action.triggered.connect(self.on_import)

        export_action = QAction("&Export to file", self)
        export_action.setShortcut("Ctrl+E")
        export_action.setStatusTip("Export time series to file")
        export_action.triggered.connect(self.on_export)

        clear_action = QAction("&Clear", self)
        clear_action.setShortcut("Ctrl+C")
        clear_action.setStatusTip("Clear all time series from database")
        clear_action.triggered.connect(self.on_clear)

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.setToolTip("Close the application")
        quit_action.triggered.connect(self.close)

        plot_gumbel_action = QAction("Plot extremes CDF", self)
        plot_gumbel_action.setToolTip("Plot fitted Gumbel cumulative distribution function to extremes"
                                      " in selected time series")
        plot_gumbel_action.triggered.connect(self.create_gumbel_plot)

        about_action = QAction("&About", self)
        about_action.setShortcut("F1")
        about_action.setToolTip("About the application")
        about_action.triggered.connect(self.on_about)

        file_menu.addAction(import_action)
        file_menu.addAction(export_action)
        file_menu.addAction(clear_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        tool_menu.addAction(plot_gumbel_action)
        help_menu.addAction(about_action)

        # load files specified on initation
        if files_on_init is not None:
            if isinstance(files_on_init, str):
                self.load_files([files_on_init])
            elif isinstance(files_on_init, tuple) or isinstance(files_on_init, list):
                self.load_files(files_on_init)

        # refresh
        self.reset_axes()
        self.set_status(message="Welcome! Please load a file to get started.")

    @staticmethod
    def log_thread_exception(exc):
        """
        Pipe exceptions from threads other than main thread to logger

        Parameters
        ----------
        exc : tuple
            Exception type, value and traceback

        """
        # choose to pipe only the the exception value, not type nor full traceback
        logging.error("%s - %s" % exc[1:])

    def dragEnterEvent(self, event):
        """
        Event handler for dragging objects over main window. Overrides method in QWidget.
        """
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Event handler for dropping objects over main window. Overrides method in QWidget.
        """
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        self.load_files(files)

    def model_view_filter_changed(self):
        """
        Apply filter changes to db proxy model
        """
        syntax = QRegExp.PatternSyntax(self.db_view_filter_syntax.itemData(self.db_view_filter_syntax.currentIndex()))
        case_sensitivity = (self.db_view_filter_casesensitivity.isChecked() and Qt.CaseSensitive or Qt.CaseInsensitive)
        reg_exp = QRegExp(self.db_view_filter_pattern.text(), case_sensitivity, syntax)
        self.db_proxy_model.setFilterRegExp(reg_exp)

    def set_status(self, message=None, msecs=None):
        """
        Display status of the database and other temporary messages in the status bar

        Parameters
        ----------
        message : str, optional
            Status message
        msecs : int, optional
            Duration of status message. By default the message will stay until overwritten.
        """
        # Update database status (permanent widget right of statusbar)
        self.db_status.setText("%d time series in database" % self.db.n)

        # show temporary message
        if not message:
            message = ""    # statusbar.showMessage() does not accept NoneType
        if not msecs:
            msecs = 0       # statusbar.showMessage() does not accept NoneType

        self.statusBar().showMessage(message, msecs=msecs)

    def load_files(self, files):
        """
        Load files into application

        Parameters
        ----------
        files : list
            list of file names

        """

        if len(files):
            # update statusbar
            self.set_status("Importing %d file(s)...." % len(files))

            # Pass the function to execute, args, kwargs are passed to the run function
            worker = Worker(import_from_file, list(files))

            # pipe exceptions to logger (NB: like this because logging module cannot be used in pyqt QThreads)
            worker.signals.error.connect(self.log_thread_exception)

            # grab results and merge into model
            worker.signals.result.connect(self.update_model)

            # update model and status bar once finished
            worker.signals.finished.connect(self.set_status)

            # Execute
            self.threadpool.start(worker)

    def update_model(self, newdb):
        """
        Fill item model with time series identifiers

        Parameters
        ----------
        newdb : TsDB
            Time series database
        """
        # merge the loaded time series into the database
        self.db.update(newdb)

        # fill item model with time series by unique id (common path is removed)
        names = self.db.list(names="*", relative=True, display=False)
        self.db_source_model.clear()    # clear before re-adding

        for name in names:
            # set each item as unchecked initially
            item = QStandardItem(name)
            item.setCheckState(Qt.Unchecked)
            item.setCheckable(True)
            item.setToolTip(os.path.join(self.db_common_path, name))
            self.db_source_model.appendRow(item)

        # common path of all time series id in db
        self.db_common_path = self.db.common
        self.set_status()

    def get_selected_items_in_model(self):
        """
        Return list of names of checked series in item model
        """
        selected_items = []

        for row_number in range(self.db_proxy_model.rowCount()):
            # get index of item in proxy model and index of the same item in the source model
            proxy_index = self.db_proxy_model.index(row_number, 0)
            source_index = self.db_proxy_model.mapToSource(proxy_index)

            # is this item checked?
            is_selected = self.db_source_model.data(source_index, Qt.CheckStateRole) == QVariant(Qt.Checked)

            if is_selected:
                # item path relative to common path in db
                rpath = self.db_source_model.data(source_index)

                # join with common path and add to list of checked items
                selected_items.append(os.path.join(self.db_common_path, rpath))

        return selected_items

    def select_all_items_in_model(self):
        """
        Check all items in item model
        """
        for row_number in range(self.db_proxy_model.rowCount()):
            proxy_index = self.db_proxy_model.index(row_number, 0)
            source_index = self.db_proxy_model.mapToSource(proxy_index)
            item = self.db_source_model.itemFromIndex(source_index)
            item.setCheckState(Qt.Checked)

    def unselect_all_items_in_model(self):
        """
        Uncheck all items in item model
        """
        for row_number in range(self.db_proxy_model.rowCount()):
            proxy_index = self.db_proxy_model.index(row_number, 0)
            source_index = self.db_proxy_model.mapToSource(proxy_index)
            item = self.db_source_model.itemFromIndex(source_index)
            item.setCheckState(Qt.Unchecked)

    def get_time_window(self):
        """
        Time window from spin boxes
        """
        return self.from_time.value(), self.to_time.value()

    def create_gumbel_plot(self):
        """
        Create new closable tab widget with plot of fitted Gumbel cumulative distribution function to extremes
        of selected time series
        """
        # get ui selections
        checked_series = self.get_selected_items_in_model()
        filterargs = self.get_filter_settings()
        time_window = self.get_time_window()

        if len(checked_series) < 2:
            # no series were selected
            logging.info("Too few time series selected to fit extreme CDF.")
            return
        else:
            # get data series as dictionary of TimeSeries obj
            series = self.db.getm(names=checked_series, store=False)
            sample = []     # initiate empty sample
            names = []

            for name, ts in series.items():
                # path calculation to get relative path for enhanced legend readability
                names.append(os.path.relpath(name, self.db_common_path))

                # get data extreme (largest maxima or smallest minima)
                _, tsdata = ts.get(twin=time_window, filterargs=filterargs)

                if self.maxima.isChecked():
                    sample.append(np.max(tsdata))
                else:
                    sample.append(np.min(tsdata))

            try:
                sample = np.asarray(sample)
                # estimate distribution parameters
                if self.maxima.isChecked():
                    # distribution of largest maximum
                    location, scale = gumbel_pwm(sample)
                    logging.info("Fitted Gumbel distribution to sample of %d maxima."
                                 "Fitted distribution parameters (location, scale) = (%5.3g, %5.3g)"
                                 % (sample.size, location, scale))
                else:
                    # distribution of smallest minimum
                    sample *= -1.   # To model the minimum value, use the negative of the original values
                    location, scale = gumbel_pwm(sample)
                    logging.info("Fitted Gumbel distribution to sample of %d minima."
                                 "Fitted distribution parameters (location, scale) = (%5.3g, %5.3g).\n"
                                 "Note that the distribution parameters are based on the negative of the original "
                                 "sample. Multiply the distribution quantiles by -1 before use."
                                 % (sample.size, location, scale))

                sample = np.sort(sample)
                z_sample = -np.log(-np.log(empirical_cdf(sample.size, kind="median")))
                z_fit = (sample - location) / scale

            except (ValueError, ZeroDivisionError) as err:
                logging.warning(err.__str__)
                return

            # create widget and attach to tab
            w = QWidget()
            fig = Figure()
            canvas = FigureCanvas(fig)
            canvas.setParent(w)
            axes = fig.add_subplot(111)
            toolbar = NavigationToolbar(canvas, self.upper_left_frame)
            vbox = QVBoxLayout()
            vbox.addWidget(canvas)
            vbox.addWidget(toolbar)
            w.setLayout(vbox)
            self.tabs.addTab(w, "Extremes CDF")
            tabindex = self.tabs.indexOf(w)
            self.tabs.setTabToolTip(tabindex, "Plot fitted Gumbel cumulative distribution function "
                                              "to extremes (maxima/minima) of selected time series")

            if self.maxima.isChecked():
                # plot largest maxima
                axes.plot(sample, z_sample, 'ko', label='Data')
                axes.plot(sample, z_fit, '-m', label='Fitted')
            else:
                # plot smallest minima. remember that the negative of the original sample was used when fitting
                # invert the horizontal axis to have the smallest minima (largest in absolute sense) to the right
                axes.invert_xaxis()
                axes.plot(-1.*sample, z_sample, 'ko', label='Data')
                axes.plot(-1.*sample, z_fit, '-m', label='Fitted')

            # plotting positions and plot configurations
            ylabels = np.array([0.1, 0.2, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999])
            yticks = -np.log(-np.log(ylabels))
            axes.set_yticks(yticks)
            axes.set_yticklabels(ylabels)
            axes.legend(loc="upper left")
            axes.grid(True)
            axes.set_xlabel("Data")
            axes.set_ylabel("Cumulative probability (-)")
            canvas.draw()

    def reset_axes(self):
        """
        Clear and reset plot axes
        """
        self.history_axes.clear()
        self.history_axes.grid(True)
        self.history_axes.set_xlabel('Time (s)')
        self.history_canvas.draw()
        self.spectrum_axes.clear()
        self.spectrum_axes.grid(True)
        self.spectrum_axes.set_xlabel('Frequency (Hz)')
        self.spectrum_axes.set_ylabel('Spectral density')
        self.spectrum_canvas.draw()
        self.weibull_axes.clear()
        self.weibull_axes.grid(True)
        self.weibull_axes.set_xlabel('X - location')
        self.weibull_axes.set_ylabel('Cumulative probability (-)')
        self.weibull_canvas.draw()
        self.cycles_axes.clear()
        self.cycles_axes.grid(True)
        self.cycles_axes.set_xlabel('Cycle magnitude')
        self.cycles_axes.set_ylabel('Cycle count (-)')
        self.cycles_canvas.draw()

    def get_filter_settings(self):
        """
        Return filter type and cut off frequencies
        """
        if self.lowpass.isChecked():
            args = ('lp', self.lowpass_f.value())
        elif self.hipass.isChecked():
            args = ('hp', self.hipass_f.value())
        elif self.bandpass.isChecked():
            args = ('bp', self.bandpass_lf.value(), self.bandpass_hf.value())
        elif self.bandblock.isChecked():
            args = ('bb', self.bandblock_lf.value(), self.bandblock_hf.value())
        else:
            args = None

        return args

    def plot_history(self, container):
        """
        Plot time series history and peaks/troughs

        Parameters
        ----------
        container : dict
            Time, data, peak and trough values
        """
        # clear axes
        self.history_axes.clear()
        self.history_axes.grid(True)
        self.history_axes.set_xlabel('Time (s)')

        # draw
        for name, data in container.items():
            # plot timetrace
            self.history_axes.plot(data.get('t'), data.get('x'), '-', label=name)

            # include maxima/minima if requested
            if self.show_minmax.isChecked() and self.maxima.isChecked():
                # maxima
                self.history_axes.plot(data.get('tmax'), data.get('xmax'), 'o')
            elif self.show_minmax.isChecked() and self.minima.isChecked():
                # minima
                self.history_axes.plot(data.get('tmin'), data.get('xmin'), 'o')

            self.history_axes.legend(loc="upper left")
            self.history_canvas.draw()

        self.set_status("History plot updated", msecs=3000)

    def plot_psd(self, container):
        """
        Plot time series power spectral density

        Parameters
        ----------
        container : dict
            Frequency versus power spectral density as tuple
        """
        # clear axes
        self.spectrum_axes.clear()
        self.spectrum_axes.grid(True)
        self.spectrum_axes.set_xlabel('Frequency (Hz)')
        self.spectrum_axes.set_ylabel('Spectral density')

        # draw
        for name, value in container.items():
            f, s = value
            self.spectrum_axes.plot(f, s, '-', label=name)
            self.spectrum_axes.legend(loc="upper left")
            self.spectrum_canvas.draw()

        self.set_status("Power spectral density plot updated", msecs=3000)

    def plot_rfc(self, container):
        """
        Plot time series cycle distribution found using rainflow counting

        Parameters
        ----------
        container : dict
            Frequency versus power spectral density as tuple
        """
        self.cycles_axes.clear()
        self.cycles_axes.grid(True)
        self.cycles_axes.set_xlabel('Cycle magnitude')
        self.cycles_axes.set_ylabel('Cycle count (-)')

        # cycle bar colors
        barcolor = cycle("bgrcmyk")

        # draw
        for name, value in container.items():
            magnitude, count = value    # unpack magnitude and count

            try:
                # width of bars
                width = magnitude[1] - magnitude[0]

            except IndexError:
                # cycles and magnitude lists are empty, no cycles found from rainflow
                logging.warning("No cycles found for time series '%s'. Cannot create cycle histogram." % name)

            except ValueError:
                # probably nans or infs in data
                logging.warning("Invalid values (nan, inf) in time series '%s'. Cannot create cycle histogram." % name)

            else:
                self.cycles_axes.bar(magnitude, count, width, label=name, alpha=0.4, color=next(barcolor))
                self.cycles_axes.legend(loc="upper left")
                self.cycles_canvas.draw()

        self.set_status("Cycle distribution plot updated", msecs=3000)

    def plot_weibull(self, container):
        """
        Plot maxima/minima sample on linearized weibull axes

        Parameters
        ----------
        container : dict
            Sample and fitted weibull parameters
        """
        self.weibull_axes.clear()
        self.weibull_axes.grid(True)
        self.weibull_axes.set_xlabel('X - location')
        self.weibull_axes.set_ylabel('Cumulative probability (-)')

        # labels and tick positions for weibull paper plot
        p_labels = np.array([0.2, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999, 0.9999])
        p_ticks = np.log(np.log(1. / (1. - p_labels)))
        x_lb, x_ub = None, None

        # draw
        for name, value in container.items():
            x = value.get("sample")
            a = value.get("loc")
            b = value.get("scale")
            c = value.get("shape")
            is_minima = value.get("minima")

            # to simplify logging message
            if is_minima:
                txt = "minima"
            else:
                txt = "maxima"

            if x is not None:
                logging.info("Fitted Weibull distribution to sample of %d %s from '%s'. "
                             "(location, scale, shape) = (%5.3g, %5.3g, %5.3g)" % (x.size, txt, name, a, b, c))
            else:
                # skip is sample is NoneType, warning sent by thread
                continue

            # flip sample to be able to plot sample on weibull scales
            if is_minima:
                x *= -1.

            # normalize maxima/minima sample on weibull scales
            x = np.sort(x)  # sort ascending
            mask = (x >= a)  # weibull paper plot will fail for mv-a < 0
            x_norm = np.log(x[mask] - a)
            ecdf_norm = np.log(np.log(1. / (1. - (np.arange(x.size) + 1.) / (x.size + 1.))))
            q_fitted = b * (-np.log(1. - p_labels)) ** (1. / c)  # x-a

            # consider switching to np.any(), not sure what is more correct
            if np.all(q_fitted <= 0.):
                logging.warning("Invalid sample for time series '%s'. Cannot fit Weibull distribution." % name)
                pass
            else:
                # normalized quantiles from fitted distribution (inside if-statement to avoid log(negative_num)
                q_norm_fitted = np.log(q_fitted)

                # calculate data range for xtick/label calculation later
                if not x_lb:
                    # first time
                    x_lb = np.min(q_fitted)
                elif np.min(q_fitted) < x_lb:
                    # lower value
                    x_lb = np.min(q_fitted)

                if not x_ub:
                    x_ub = np.max(q_fitted)
                elif np.max(q_fitted) > x_ub:
                    x_ub = np.max(q_fitted)

                # calculate axes tick and labels
                labels_sample = np.around(np.linspace(x_lb, x_ub, 4), decimals=1)

                ticks_sample = np.log(labels_sample[labels_sample > 0.])

                # and draw weibull paper plot (avoid log(0))
                self.weibull_axes.plot(x_norm, ecdf_norm[mask], 'o', label=name)
                self.weibull_axes.plot(q_norm_fitted, p_ticks, '-')

                self.weibull_axes.set_xticks(ticks_sample)
                if self.maxima.isChecked():
                    self.weibull_axes.set_xticklabels(labels_sample[labels_sample > 0.])
                else:
                    self.weibull_axes.set_xticklabels(-1. * labels_sample[labels_sample > 0.])

                self.weibull_axes.set_ylim((p_labels[0], p_labels[-1]))
                self.weibull_axes.set_yticks(p_ticks)
                self.weibull_axes.set_yticklabels(p_labels)
                self.weibull_axes.legend(loc='upper left')
                self.weibull_canvas.draw()

            self.set_status("Weibull distribution plot updated", msecs=3000)

    def process_timeseries(self, container):
        """
        Process timeseries to calculate cycle distribution, power spectral density and max/min distributions

        Parameters
        ----------
        container : dict
            Container with TimeSeries objects

        Notes
        -----
        Starts new threads for RFC, PSD and Weibull calculations while history plot is created directly.
        """
        self.set_status("Processing...", msecs=3000)

        # ui selections
        twin = self. get_time_window()
        fargs = self.get_filter_settings()

        # start calculation of filtered and windows time series trace
        worker = Worker(calculate_trace, container, twin, fargs)
        worker.signals.error.connect(self.log_thread_exception)
        worker.signals.result.connect(self.plot_history)
        self.threadpool.start(worker)

        # start calculations of psd
        worker = Worker(calculate_psd, container, twin, fargs)
        worker.signals.error.connect(self.log_thread_exception)
        worker.signals.result.connect(self.plot_psd)
        self.threadpool.start(worker)

        # start calculations of weibull
        worker = Worker(calculate_weibull_fit, container, twin, fargs, self.minima.isChecked())
        worker.signals.error.connect(self.log_thread_exception)
        worker.signals.result.connect(self.plot_weibull)
        self.threadpool.start(worker)

        # start calculations of rfc
        worker = Worker(calculate_rfc, container, twin, fargs)
        worker.signals.error.connect(self.log_thread_exception)
        worker.signals.result.connect(self.plot_rfc)
        self.threadpool.start(worker)

    def on_about(self):
        """
        Show information about the application
        """
        # get distribution version
        try:
            # version at runtime from distribution/package info
            version = get_distribution("qats").version
        except DistributionNotFound:
            # package is not installed
            version = ""

        # todo: Insert link to github issue tracker
        msg = "This is a low threshold tool for inspection of time series, power spectra and statistics. " \
              "Its main objective is to ease self-check, quality assurance and reporting.<br><br>" \
              "Import qats Python package and use the API when you need advanced features or want to extend it's " \
              "functionality.<br><br>" \
              "Feature requests, technical queries and bug reports should be directed to the developers on " \
              "<a href='https://github.com/dnvgl/qats/issues'>Github</a>.<br><br>" \
              "ENJOY!"

        msgbox = QMessageBox()
        msgbox.setWindowIcon(self.icon)
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setTextFormat(Qt.RichText)
        msgbox.setText(msg.strip())
        msgbox.setWindowTitle("About QATS - version %s" % version)
        msgbox.exec_()

    def on_clear(self):
        """
        Clear all time series from database
        """
        self.db.clear(names="*", display=False)
        self.db_common_path = ""
        self.db_source_model.clear()
        self.reset_axes()
        logging.info("Cleared all time series from database...")
        self.set_status()

    def on_display(self):
        """
        Plot checked data series when pressing the 'show' button.
        """

        # list of selected series
        selected_series = self.get_selected_items_in_model()

        if len(selected_series) >= 1:
            # update statusbar
            self.set_status("Reading time series...", msecs=10000)  # will probably be erased by new status message

            # Pass the function to execute, args, kwargs are passed to the run function
            # todo: consider if it is necessary to pass copied db to avoid main loop freeze
            worker = Worker(read_timeseries, self.db, selected_series)

            # pipe exceptions to logger (NB: like this because logging module cannot be used in pyqt QThreads)
            worker.signals.error.connect(self.log_thread_exception)

            # grab results start further calculations
            worker.signals.result.connect(self.process_timeseries)

            # Execute
            self.threadpool.start(worker)
        else:
            # inform user to select at least one time series before plotting
            logging.info("Select at least 1 time series before plotting.")

    def on_export(self):
        """
        Export selected time series to file
        """
        # file save dialogue
        dlg = QFileDialog()
        dlg.setWindowIcon(self.icon)
        options = dlg.Options()

        name, _ = dlg.getSaveFileName(dlg, "Export time series to file", "",
                                      "Direct access file (*.ts);;"
                                      "ASCII file with header (*.dat);;"
                                      "All Files (*)", options=options)

        # get list of selected time series
        keys = self.get_selected_items_in_model()

        # get ui settings
        fargs = self.get_filter_settings()
        twin = self.get_time_window()

        if name:    # nullstring if file dialog is cancelled
            # update statusbar
            self.set_status("Exporting....")

            # Pass the function to execute, args, kwargs are passed to the run function
            worker = Worker(export_to_file, name, self.db, keys, twin, fargs)

            # pipe exceptions to logger
            worker.signals.error.connect(self.log_thread_exception)

            # update status bar once finished
            worker.signals.finished.connect(self.set_status)

            # Execute
            self.threadpool.start(worker)

    def on_import(self):
        """
        File open dialogue
        """
        dlg = QFileDialog()
        dlg.setWindowIcon(self.icon)
        options = dlg.Options()
        files, _ = dlg.getOpenFileNames(dlg, "Load time series files", "",
                                        "Direct access files (*.ts);;"
                                        "SIMO S2X direct access files with info array (*.tda);;"
                                        "RIFLEX SIMO binary files (*.bin);;"
                                        "RIFLEX SIMO ASCII files (*.asc);;"
                                        "Matlab files (*.mat);;"
                                        "ASCII file with header (*.dat);;"
                                        "SIMA H5 files (*.h5);;"
                                        "All Files (*)", options=options)

        # load files into db and update application model and view
        self.load_files(files)

    def on_no_filter(self):
        """
        Toggle off all filters and disable spin boxes
        """
        if self.db.n > 0:
            self.lowpass_f.setEnabled(False)
            self.hipass_f.setEnabled(False)
            self.bandpass_lf.setEnabled(False)
            self.bandpass_hf.setEnabled(False)
            self.bandblock_lf.setEnabled(False)
            self.bandblock_hf.setEnabled(False)

    def on_lowpass(self):
        """
        Toggle off filters and disable spin boxes, except low-pass
        """
        if self.db.n > 0:
            self.lowpass_f.setEnabled(True)
            self.hipass_f.setEnabled(False)
            self.bandpass_lf.setEnabled(False)
            self.bandpass_hf.setEnabled(False)
            self.bandblock_lf.setEnabled(False)
            self.bandblock_hf.setEnabled(False)

    def on_hipass(self):
        """
        Toggle off filters and disable spin boxes, except high-pass
        """
        if self.db.n > 0:
            self.lowpass_f.setEnabled(False)
            self.hipass_f.setEnabled(True)
            self.bandpass_lf.setEnabled(False)
            self.bandpass_hf.setEnabled(False)
            self.bandblock_lf.setEnabled(False)
            self.bandblock_hf.setEnabled(False)

    def on_bandpass(self):
        """
        Toggle off filters and disable spin boxes, except band-pass
        """
        if self.db.n > 0:
            self.lowpass_f.setEnabled(False)
            self.hipass_f.setEnabled(False)
            self.bandpass_lf.setEnabled(True)
            self.bandpass_hf.setEnabled(True)
            self.bandblock_lf.setEnabled(False)
            self.bandblock_hf.setEnabled(False)

    def on_bandblock(self):
        """
        Toggle off filters and disable spin boxes, except band-block
        """
        if self.db.n > 0:
            self.lowpass_f.setEnabled(False)
            self.hipass_f.setEnabled(False)
            self.bandpass_lf.setEnabled(False)
            self.bandpass_hf.setEnabled(False)
            self.bandblock_lf.setEnabled(True)
            self.bandblock_hf.setEnabled(True)
