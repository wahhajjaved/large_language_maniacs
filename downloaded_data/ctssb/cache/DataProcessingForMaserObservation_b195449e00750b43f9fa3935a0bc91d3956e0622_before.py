#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
sdr_fs data processing tool
"""
import sys
import os
import argparse
import json
from multiprocessing import Pool
from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget, QGridLayout, \
    QPushButton, QLabel, QLineEdit, QSlider, QLCDNumber, QMessageBox
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5 import QtCore
import h5py
import numpy as np
import pandas as pd
from astropy.convolution import Gaussian1DKernel, convolve
import peakutils
from parsers.configparser_ import ConfigParser
from utils.help import indexies, compute_gauss
from utils.ploting_qt5 import Plot


def parse_arguments():
    """

    :return: dict with passed args to script
    """
    parser = argparse.ArgumentParser(description='''plotting tool. ''', epilog="""PRE PLOTTER.""")
    parser.add_argument("datafile", help="output file", type=str)
    parser.add_argument("line", help="Observed frequency", type=int)
    parser.add_argument("-c", "--config", help="Configuration cfg file",
                        type=str, default="config/config.cfg")
    parser.add_argument("-t", "--calibType", help="Type of calibration", default="SDR")
    parser.add_argument("-tr", "--threshold",
                        help="Set threshold for outlier filter", type=float, default=1.0)
    parser.add_argument("-f", "--filter",
                        help="Set the amount of times to filter data to remove noise spikes, "
                             "higher than 5 makes little difference",
                        type=int, default=0, choices=range(0, 11), metavar="[0-10]")
    parser.add_argument("-v", "--version", action="version", version='%(prog)s - Version 1.0')
    args = parser.parse_args()
    return args


def get_args(key):
    """

    :param key: argument key
    :return: to script passed argument value
    """
    return str(parse_arguments().__dict__[key])


def get_configs(section, key):
    """

    :param section: configuration file section
    :param key: configuration file sections key
    :return: configuration file section key value
    """
    config_file_path = get_args("config")
    config = ConfigParser(config_file_path)
    return config.get_config(section, key)


def get_data(data_file):
    """

    :param data_file: data file name
    :return: values from script sdr_fs.py
    """
    input_data = h5py.File(data_file, 'r')
    amplitude = input_data['amplitude'][()]
    specie = input_data['specie'][()][0][0].decode("ascii")
    input_data.close()
    return amplitude, specie


def is_outlier(points, threshold):
    """

    :param points: points
    :param threshold: threshold
    :return: mask for outliers
    """
    if len(points.shape) == 1:
        points = points[:, None]

    median = np.median(points, axis=0)
    diff = np.sum((points - median) ** 2, axis=-1)
    diff = np.sqrt(diff)
    med_abs_deviation = np.median(diff)
    modified_z_score = 0.6745 * diff / med_abs_deviation

    return modified_z_score < threshold


def replace_bad_points(xdata, ydata, x_bad_point, y_bad_point, data):
    """

    :param xdata: frequencies
    :param ydata: amplitudes
    :param x_bad_point: frequencies bad points
    :param y_bad_point: amplitudes bad points
    :param data: data
    :return: return data arrays where bad points are replaced with polinom values
    """
    tempx = []
    tempy = []
    xlist = xdata.tolist()
    polyfit = np.polyfit(xdata, ydata, 10)
    poly1d = np.poly1d(polyfit)

    for idx, point in enumerate(x_bad_point):
        index = xlist.index(point)
        if y_bad_point[idx] / ydata[index] > 1.10 or y_bad_point[idx] / ydata[index] < 0.90:
            tempx.append(x_bad_point[idx])
            tempy.append(y_bad_point[idx])
            ydata[index] = poly1d(x_bad_point[idx])
        else:
            ydata[index] = data[index, 1]
    return tempx, tempy


def signal_to_noise_ratio(frequency, amplitude, cuts):
    """

    :param frequency: frequency
    :param amplitude: amplitude
    :param cuts: signal region
    :return: signal to noise ratio
    """
    cuts_index = list()
    cuts_index.append(0)
    for cut in cuts:
        cuts_index.append((np.abs(frequency - float(cut[0]))).argmin())
        cuts_index.append((np.abs(frequency - float(cut[1]))).argmin())
    cuts_index.append(-1)
    y_array = list()
    i = 0
    j = 1
    while i != len(cuts_index):
        y_array.append(amplitude[cuts_index[i]: cuts_index[j]])
        i = i + 2
        j = j + 2
    non_signal_amplitude = list()
    for point in y_array:
        for point_one in point:
            non_signal_amplitude.append(point_one)

    non_signal_amplitude = np.array(non_signal_amplitude)
    std = np.std(non_signal_amplitude)
    ston = std * 3
    return ston


class Analyzer(QWidget):
    """
    GUI application
    """

    def __init__(self):
        super(Analyzer, self).__init__()
        self.setWindowIcon(QIcon('viraclogo.png'))
        self.center()
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.grid.setSpacing(10)
        self.change_params_buttons = None
        self.change_params = False
        self.info_set = set()
        self.info_set_2 = set()
        self.change_data_button = None
        self.m_slider = None
        self.n_slider = None
        self.plot_1 = None
        self.plot_2 = None
        self.m_slider = None
        self.n_slider = None
        self.plot_smooth_data_button = None
        self.m_lcd = None
        self.n_lcd = None
        self.mLabel = None
        self.mLabel = None
        self.nLabel = None
        self.plot_poly = None
        self.info_label = None
        self.info_input_field = None
        self.a = None
        self.b = None
        self.plot_poly = None
        self.info_label = None
        self.info_input_field = None
        self.a = None
        self.b = None
        self.previous_m = None
        self.previous_n = None
        self.badplot_2_right = None
        self.x_bad_points_right = []
        self.y_bad_point_right = []
        self.badplot_1_left = None
        self.y_bad_point_left = []
        self.x_bad_points_left = []
        self.plot_10 = None
        self.plot_11 = None
        self.plot_poly_button = None
        self.p_u1 = None
        self.p_u9 = None
        self.plot_5 = None
        self.plot_6 = None
        self.plot_poly = None
        self.plot_poly = None
        self.monitoring_button = None
        self.local_max_array_u1 = None
        self.local_max_array_u9 = None
        self.z1_not_smooht_data = None
        self.z2_not_smooht_data = None
        self.avg_y_not_smoohtData = None
        self.z1_smooht_data = None
        self.z2_smooht_data = None
        self.avg_y_smooht_data = None
        self.z1 = None
        self.z2 = None
        self.polyu1 = None
        self.polyu9 = None
        self.plot_9 = None
        self.plot_8 = None
        self.plot_7 = None
        self.maxU1 = list()
        self.maxU9 = list()
        self.avgMax = list()
        self.maxu1_index = list()
        self.maxu9_index = list()
        self.maxavg_index = list()
        self.avg_y = None
        self.polynomial_order = 3
        self.change_parms = False
        self.source = get_args("datafile").split(".")[0].split("_")[0]
        self.data_file = get_configs("paths", "outputFilePath") + "/" + \
                         get_args("line") + "/" + \
                         self.source + "/" + \
                         get_args("datafile")
        self.data, self.specie = get_data(self.data_file)
        self.xdata = self.data[:, 0]
        self.ydata_left = self.data[:, 1]
        self.ydata_right = self.data[:, 2]
        self.line = get_args("line")
        self.cuts = get_configs('cuts', self.source + "_" + str(self.line)).split(";")
        self.cuts = [c.split(",") for c in self.cuts]

        if int(get_args("filter")) > 0:
            x_bad_point = []
            y_bad_point_left = []
            y_bad_point_right = []

            for _ in range(int(get_args("filter"))):
                outliers_mask = is_outlier(self.data, float(get_args("threshold")))
                bad_point_index = indexies(outliers_mask, False)

                if _ == 0:
                    for idx, point in enumerate(outliers_mask):
                        if not point:
                            x_bad_point.append(self.data[idx, 0])
                            y_bad_point_left.append(self.data[idx, 1])
                            y_bad_point_right.append(self.data[idx, 2])

                df_y_left = pd.DataFrame(data=self.ydata_left)
                df_y_right = pd.DataFrame(data=self.ydata_right)
                mean_y_left = np.nan_to_num(df_y_left.rolling(window=int(
                    get_configs("parameters", "badPointRange")), center=True).mean())
                mean_y_right = np.nan_to_num(df_y_right.rolling(window=int(
                    get_configs("parameters", "badPointRange")), center=True).mean())
                for bad_point in bad_point_index:
                    if mean_y_left[bad_point] != 0:
                        self.ydata_left[bad_point] = mean_y_left[bad_point]
                for bad_point in bad_point_index:
                    if mean_y_right[bad_point] != 0:
                        self.ydata_right[bad_point] = mean_y_right[bad_point]

                if _ == int(get_args("filter")) - 1:
                    pool = Pool(processes=4)

                    async_result1 = pool. \
                        apply_async(replace_bad_points,
                                    (self.xdata, self.ydata_left,
                                     x_bad_point, y_bad_point_left, self.data))
                    async_result2 = pool. \
                        apply_async(replace_bad_points,
                                    (self.xdata, self.ydata_right,
                                     x_bad_point, y_bad_point_right, self.data))

                    x_bad_point, y_bad_point_left = async_result1.get()
                    x_bad_point, y_bad_point_right = async_result2.get()

        self.data_points = len(self.xdata)
        self.m = 0
        self.n = self.data_points
        self.xdata = np.flip(self.xdata, 0)
        self.ydata_left = np.flip(self.ydata_left, 0)
        self.ydata_right = np.flip(self.ydata_right, 0)
        self.plot_short_specter()

    def plot_short_specter(self):
        """

        :return: None
        """
        self.setWindowTitle("Spectrum")
        if self.change_parms:
            self.m = self.m_slider.value()
            self.n = self.n_slider.value()

            self.plot_1.hide()
            self.plot_2.close()
            self.plot_1.hide()
            self.plot_2.close()
            self.grid.removeWidget(self.plot_1)
            self.grid.removeWidget(self.plot_2)
            self.plot_1.removePolt()
            self.plot_2.removePolt()
            del self.plot_1
            del self.plot_2

            self.m_slider.hide()
            self.m_slider.close()
            self.n_slider.hide()
            self.n_slider.close()
            self.grid.removeWidget(self.m_slider)
            self.grid.removeWidget(self.n_slider)
            del self.m_slider
            del self.n_slider

            self.plot_smooth_data_button.hide()
            self.plot_smooth_data_button.close()
            self.grid.removeWidget(self.plot_smooth_data_button)
            del self.plot_smooth_data_button

            self.m_lcd.hide()
            self.n_lcd.hide()
            self.m_lcd.close()
            self.n_lcd.close()
            self.grid.removeWidget(self.m_lcd)
            self.grid.removeWidget(self.n_lcd)
            del self.m_lcd
            del self.n_lcd

            self.mLabel.hide()
            self.mLabel.close()
            self.grid.removeWidget(self.mLabel)
            del self.mLabel

            self.nLabel.hide()
            self.nLabel.close()
            self.grid.removeWidget(self.nLabel)
            del self.nLabel

            while len(self.info_set) != 0:
                info_item = self.info_set.pop()
                info_item.hide()
                info_item.close()
                self.grid.removeWidget(info_item)
                del info_item

            while len(self.info_set_2) != 0:
                info_item = self.info_set_2.pop()
                info_item.hide()
                info_item.close()
                self.grid.removeWidget(info_item)
                del info_item

            del self.info_set
            del self.info_set_2

            self.change_data_button.hide()
            self.change_data_button.close()
            self.grid.removeWidget(self.change_data_button)
            del self.change_data_button

            if self.m < 0:
                self.m = 0
        else:
            self.m = 0
            self.n = self.data_points
            self.change_params_buttons = QPushButton("Change Params", self)
            self.grid.addWidget(self.change_params_buttons, 4, 3)
            self.change_params_buttons.clicked.connect(self.plot_init_data)
            self.change_params_buttons.setStyleSheet("background-color: blue")

        self.xdata = self.xdata[self.m:self.n]
        self.ydata_left = self.ydata_left[self.m:self.n]
        self.ydata_right = self.ydata_right[self.m:self.n]

        # u1 plot
        self.plot_10 = Plot()
        self.plot_10.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                               'Flux density (Jy)', "Left Polarization", (1, 0),
                               "linear")
        self.plot_10.plot(self.xdata, self.ydata_left,
                          'ko', label='Data Points a', markersize=4, picker=5)

        # u9 plot
        self.plot_11 = Plot()
        self.plot_11.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                               'Flux density (Jy)', "Right Polarization", (1, 1),
                               "linear")
        self.plot_11.plot(self.xdata, self.ydata_right,
                          'ko', label='Data Points', markersize=4, picker=5)

        self.badplot_1_left = self.plot_10.plot(self.x_bad_points_left,
                                                self.y_bad_point_left, 'rx', markersize=10)
        self.badplot_2_right = self.plot_11.plot(self.x_bad_points_right,
                                                 self.y_bad_point_right, 'rx', markersize=10)

        self.plot_10.fig.canvas.mpl_connect('pick_event', self.on_left_click)
        self.plot_11.fig.canvas.mpl_connect('pick_event', self.on_right_click)

        self.grid.addWidget(self.plot_10, 0, 0)
        self.grid.addWidget(self.plot_11, 0, 1)

        self.plot_poly_button = QPushButton("Create Polynomial", self)
        self.grid.addWidget(self.plot_poly_button, 3, 3)
        self.plot_poly_button.clicked.connect(self.remove_cuts)
        self.plot_poly_button.setStyleSheet("background-color: green")

    def plot_init_data(self):
        """

        :return: None
        """
        self.setWindowTitle("Change params")
        self.change_parms = True
        self.change_params_buttons.hide()
        self.change_params_buttons.close()
        self.grid.removeWidget(self.change_params_buttons)
        del self.change_params_buttons

        if self.plot_poly:
            self.plot_poly.hide()
            self.plot_poly.close()
            self.grid.removeWidget(self.plot_poly)
            del self.plot_poly

        self.change_data_button = QPushButton("Change Data", self)
        self.change_data_button.clicked.connect(self.change_data)
        self.change_data_button.setStyleSheet("background-color: blue")
        self.grid.addWidget(self.change_data_button, 5, 3)

        self.plot_smooth_data_button = QPushButton("Create Shorter specter", self)
        self.plot_smooth_data_button.clicked.connect(self.plot_short_specter)
        self.plot_smooth_data_button.setStyleSheet("background-color: green")
        self.grid.addWidget(self.plot_smooth_data_button, 5, 4)

        self.plot_1 = Plot()
        self.plot_1.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Left Polarization", (1, 0), "linear")
        self.plot_1.plot(self.xdata, self.ydata_right, 'ko', label='Data Points', markersize=1, picker=5)

        self.plot_2 = Plot()
        self.plot_2.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Right Polarization", (1, 1), "linear")
        self.plot_2.plot(self.xdata, self.ydata_right, 'ko', label='Data Points', markersize=1, picker=5)

        self.plot_1.fig.canvas.mpl_connect('pick_event', self.on_left_click)
        self.plot_2.fig.canvas.mpl_connect('pick_event', self.on_right_click)

        self.grid.addWidget(self.plot_1, 0, 0)
        self.grid.addWidget(self.plot_2, 0, 1)

        info_panel_labels_text = ["Polynomial order"]
        info_panel_entry_text = [{"defaultValue": str(self.polynomial_order), "addEntry": True}]

        for i in range(0, len(info_panel_labels_text)):

            self.info_label = QLabel(info_panel_labels_text[i])
            self.grid.addWidget(self.info_label, i + 3, 3)
            self.info_set.add(self.info_label)

            if info_panel_entry_text[i]["addEntry"]:
                self.info_input_field = QLineEdit()
                self.info_input_field.setText(str(info_panel_entry_text[i]["defaultValue"]))
                self.grid.addWidget(self.info_input_field, i + 3, 4)
                self.info_set_2.add(self.info_input_field)

        self.a = ((np.abs(self.xdata - float(self.cuts[0][0]))).argmin())
        self.b = ((np.abs(self.xdata - float(self.cuts[-1][1]))).argmin())
        self.previous_m = self.m
        self.previous_n = self.n - 1
        self.m_slider = QSlider(Qt.Horizontal, self)
        self.n_slider = QSlider(Qt.Horizontal, self)
        self.m_slider.setFocusPolicy(Qt.NoFocus)
        self.n_slider.setFocusPolicy(Qt.NoFocus)
        self.m_slider.setTickInterval(20)
        self.m_slider.setSingleStep(20)
        self.m_slider.setMinimum(0)
        self.m_slider.setMaximum(self.a - 1)
        self.n_slider.setMinimum(self.b - 1)
        self.n_slider.setMaximum(self.n)
        self.n_slider.setValue(self.n)
        self.m_slider.setMinimumSize(500, 0)
        self.m_slider.setMinimumSize(500, 0)
        self.m_slider.valueChanged[int].connect(self.change_m)
        self.n_slider.valueChanged[int].connect(self.change_n)
        self.m_lcd = QLCDNumber(self)
        self.n_lcd = QLCDNumber(self)
        self.m_lcd.setSegmentStyle(QLCDNumber.Flat)
        self.n_lcd.setSegmentStyle(QLCDNumber.Flat)
        mpalette = self.m_lcd.palette()
        npalette = self.n_lcd.palette()
        mpalette.setColor(mpalette.Dark, QColor(0, 255, 0))
        npalette.setColor(npalette.Dark, QColor(0, 255, 0))
        self.m_lcd.setPalette(mpalette)
        self.n_lcd.setPalette(npalette)
        self.mLabel = QLabel('M', self)
        self.nLabel = QLabel('N', self)
        self.grid.addWidget(self.mLabel, 1, 3)
        self.grid.addWidget(self.nLabel, 2, 3)
        self.grid.addWidget(self.m_slider, 1, 4)
        self.grid.addWidget(self.n_slider, 2, 4)
        self.grid.addWidget(self.m_lcd, 1, 5)
        self.grid.addWidget(self.n_lcd, 2, 5)
        self.m_slider.valueChanged.connect(self.m_lcd.display)
        self.n_slider.valueChanged.connect(self.n_lcd.display)
        self.m = self.m_slider.value()
        self.n = self.n_slider.value()

    def change_data(self):
        """
        :return: None
        """
        new_values = list()

        for value in self.info_set_2:
            new_values.append(value.text())

        self.polynomial_order = float(new_values[0])

        QMessageBox.information(self, "Info", "Data was changed")

    def change_m(self, value):
        """
        :param value:
        :return:
        """
        self.plot_1.plot(self.xdata[int(self.previous_m)],
                         self.ydata_left[int(self.previous_m)], 'ko', markersize=1)
        self.plot_2.plot(self.xdata[int(self.previous_m)],
                         self.ydata_right[int(self.previous_m)], 'ko', markersize=1)

        self.plot_1.annotation(self.xdata[int(self.previous_m)],
                               self.ydata_left[int(self.previous_m)], " ")
        self.plot_2.annotation(self.xdata[int(self.previous_m)],
                               self.ydata_right[int(self.previous_m)], " ")

        self.plot_1.remannotation()
        self.plot_2.remannotation()

        self.plot_1.annotation(self.xdata[int(value)],
                               self.ydata_left[int(value)], "M")
        self.plot_2.annotation(self.xdata[int(value)],
                               self.ydata_right[int(value)], "M")

        self.plot_1.plot(self.xdata[int(value)],
                         self.ydata_left[int(value)], 'ro', markersize=1)
        self.plot_2.plot(self.xdata[int(value)],
                         self.ydata_right[int(value)], 'ro', markersize=1)

        self.plot_1.canvasShow()
        self.plot_2.canvasShow()

        self.previous_m = value

    def change_n(self, value):
        """

        :param value: value
        :return: None
        """
        self.plot_1.plot(self.xdata[int(self.previous_n - 1)],
                         self.ydata_left[int(self.previous_n - 1)], 'ko', markersize=1)
        self.plot_2.plot(self.xdata[int(self.previous_n - 1)],
                         self.ydata_right[int(self.previous_n - 1)], 'ko', markersize=1)

        self.plot_1.annotation(self.xdata[int(self.previous_n - 1)],
                               self.ydata_left[int(self.previous_n - 1)], " ")
        self.plot_2.annotation(self.xdata[int(self.previous_n - 1)],
                               self.ydata_right[int(self.previous_n - 1)], " ")

        self.plot_1.remannotation()
        self.plot_2.remannotation()
        self.plot_1.annotation(self.xdata[int(value - 1)],
                               self.ydata_left[int(value - 1)], "N")
        self.plot_2.annotation(self.xdata[int(value - 1)],
                               self.ydata_right[int(value - 1)], "N")

        self.plot_1.plot(self.xdata[int(value - 1)],
                         self.ydata_left[int(value - 1)], 'ro', markersize=1)
        self.plot_2.plot(self.xdata[int(value - 1)],
                         self.ydata_right[int(value - 1)], 'ro', markersize=1)

        self.plot_1.canvasShow()
        self.plot_2.canvasShow()
        self.previous_n = value

    def on_right_click(self, event):
        """

        :param event: event
        :return: None
        """
        if event.mouseevent.button == 1:
            line = event.artist
            pointx, pointy = line.get_data()
            ind = event.ind

            if pointx[ind].size > 1:
                print("Too many points selected")
            else:
                y_list = self.ydata_right.tolist()
                index = y_list.index(pointy[ind])
                if self.xdata[index] not in self.x_bad_points_right:
                    self.xdata = self.xdata.reshape(self.xdata.shape[0])
                    polyfit = np.polyfit(self.xdata, self.ydata_right[:], 10)
                    poly1d = np.poly1d(polyfit)
                    self.y_bad_point_right.append(self.ydata_right[index])
                    self.x_bad_points_right.append(self.xdata[index])
                    self.badplot_2_right[0]. \
                        set_data(self.x_bad_points_right, self.y_bad_point_right)
                    self.ydata_right[index] = poly1d(self.xdata[index])
                    event.canvas.draw()
                    event.canvas.flush_events()

    def on_left_click(self, event):
        """

        :param event: event
        :return: None
        """
        if event.mouseevent.button == 1:
            line = event.artist
            pointx, pointy = line.get_data()
            ind = event.ind

            if pointx[ind].size > 1:
                print("Too many points selected")
            else:
                y_list = self.ydata_left.tolist()
                index = y_list.index(pointy[ind])
                if self.xdata[index] not in self.x_bad_points_left:
                    self.xdata = self.xdata.reshape(self.xdata.shape[0])
                    polyfit = np.polyfit(self.xdata, self.ydata_left[:], 10)
                    poly1d = np.poly1d(polyfit)
                    self.y_bad_point_left.append(self.ydata_left[index])
                    self.x_bad_points_left.append(self.xdata[index])
                    self.badplot_1_left[0].set_data(self.x_bad_points_left, self.y_bad_point_left)
                    self.ydata_left[index] = poly1d(self.xdata[index])
                    event.canvas.draw()
                    event.canvas.flush_events()

    def remove_cuts(self):
        """

        :return: None
        """
        if not self.change_parms:
            self.change_params_buttons.hide()
            self.change_params_buttons.close()
            self.grid.removeWidget(self.change_params_buttons)
            del self.change_params_buttons

        cuts_index = list()
        cuts_index.append(0)
        for cut in self.cuts:
            cuts_index.append((np.abs(self.xdata - float(cut[0]))).argmin())
            cuts_index.append((np.abs(self.xdata - float(cut[1]))).argmin())

        cuts_index.append(self.n)
        poly_array_x = list()
        poly_array_u1 = list()
        poly_array_u9 = list()
        i = 0
        j = 1

        while i != len(cuts_index):
            poly_array_x.append(self.xdata[cuts_index[i]: cuts_index[j]])
            poly_array_u1.append(self.ydata_left[cuts_index[i]: cuts_index[j]])
            poly_array_u9.append(self.ydata_right[cuts_index[i]: cuts_index[j]])
            i = i + 2
            j = j + 2

        poly_x = list()
        poly_u1 = list()
        poly_u9 = list()

        for p in poly_array_x:
            for p1 in p:
                poly_x.append(p1)

        for p in poly_array_u1:
            for p1 in p:
                poly_u1.append(p1)

        for p in poly_array_u9:
            for p1 in p:
                poly_u9.append(p1)

        polyx = np.array(poly_x)
        self.polyu1 = np.array(poly_u1)
        self.polyu9 = np.array(poly_u9)

        z_u1 = np.polyfit(polyx, self.polyu1, self.polynomial_order)
        self.p_u1 = np.poly1d(z_u1)

        z_u9 = np.polyfit(polyx, self.polyu9, self.polynomial_order)
        self.p_u9 = np.poly1d(z_u9)

        self.plot_10.hide()
        self.plot_11.close()
        self.plot_10.hide()
        self.plot_11.close()
        self.grid.removeWidget(self.plot_10)
        self.grid.removeWidget(self.plot_11)
        self.plot_10.removePolt()
        self.plot_11.removePolt()
        del self.plot_10
        del self.plot_11

        self.plot_poly_button.hide()
        self.plot_poly_button.close()
        self.grid.removeWidget(self.plot_poly_button)
        del self.plot_poly_button

        # u1 plot
        self.plot_5 = Plot()
        self.plot_5.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Left Polarization", (1, 0),
                              "linear")
        self.plot_5.plot(polyx, self.polyu1, 'ko',
                         label='Data Points', markersize=1)
        self.plot_5.plot(self.xdata, self.p_u1(self.xdata),
                         'b', label='Numpy polyfit', markersize=1)

        # u9 plot
        self.plot_6 = Plot()
        self.plot_6.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Right Polarization", (1, 1),
                              "linear")
        self.plot_6.plot(polyx, self.polyu9,
                         'ko', label='Data Points', markersize=1)
        self.plot_6.plot(self.xdata, self.p_u9(self.xdata),
                         'b', label='Numpy polyfit', markersize=1)

        self.grid.addWidget(self.plot_5, 0, 0)
        self.grid.addWidget(self.plot_6, 0, 1)

        self.plot_poly_button = QPushButton("Create local maximums", self)
        self.grid.addWidget(self.plot_poly_button, 3, 3)
        self.plot_poly_button.clicked.connect(self.plot_local_maximum)
        self.plot_poly_button.setStyleSheet("background-color: green")

    def plot_local_maximum(self):
        """

        :return: None
        """
        self.setWindowTitle("Local maximums")

        self.plot_5.hide()
        self.plot_5.close()
        self.plot_6.hide()
        self.plot_6.close()
        self.grid.removeWidget(self.plot_5)
        self.grid.removeWidget(self.plot_6)
        self.plot_5.removePolt()
        self.plot_6.removePolt()
        del self.plot_5
        del self.plot_6

        self.plot_poly_button.hide()
        self.plot_poly_button.close()
        self.grid.removeWidget(self.plot_poly_button)
        del self.plot_poly_button

        self.monitoring_button = QPushButton("Add points to monitoring", self)
        self.grid.addWidget(self.monitoring_button, 3, 3)
        self.monitoring_button.clicked.connect(self.create_result)
        self.monitoring_button.setStyleSheet("background-color: green")
        self.local_max_array_u1 = self.ydata_left - self.p_u1(self.xdata)
        self.local_max_array_u9 = self.ydata_right - self.p_u9(self.xdata)
        self.z1_not_smooht_data = self.local_max_array_u1
        self.z2_not_smooht_data = self.local_max_array_u9
        self.avg_y_not_smoohtData = (self.z1_not_smooht_data + self.z2_not_smooht_data) / 2

        g1 = Gaussian1DKernel(stddev=3, x_size=19, mode='center', factor=100)
        g2 = Gaussian1DKernel(stddev=3, x_size=19, mode='center', factor=100)
        self.z1_smooht_data = convolve(self.local_max_array_u1, g1, boundary='extend')
        self.z2_smooht_data = convolve(self.local_max_array_u9, g2, boundary='extend')
        self.avg_y_smooht_data = (self.z1_smooht_data + self.z2_smooht_data) / 2

        three_sigma_u1 = 3 * np.std(self.polyu1)
        three_sigma_u9 = 3 * np.std(self.polyu9)
        polyu_avg = (self.polyu1 + self.polyu9) / 2
        three_sigma_uavg = 3 * np.std(polyu_avg)

        smart_tres_u1 = 2.5 * three_sigma_u1 / np.max(self.z1_smooht_data)
        smart_tres_u9 = 2.5 * three_sigma_u9 / np.max(self.z2_smooht_data)
        smart_tres_uavg = 2.5 * three_sigma_uavg / np.max(self.avg_y_smooht_data)

        # indexsu apreikinasana
        indexes_for_ceb = peakutils.indexes(self.z1_smooht_data, thres=smart_tres_u1, min_dist=3)
        indexes_for_ceb2 = peakutils.indexes(self.z2_smooht_data, thres=smart_tres_u9, min_dist=3)
        indexes_for_avg = peakutils.indexes(self.avg_y_smooht_data, thres=smart_tres_uavg, min_dist=3)

        # u1
        self.plot_7 = Plot()
        self.plot_7.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Left Polarization", (1, 0), "linear")
        self.plot_7.plot(self.xdata, self.z1_smooht_data,
                         'b', label='Signal - polynomial', markersize=1)
        self.plot_7.plot(self.xdata[indexes_for_ceb],
                         self.z1_smooht_data[indexes_for_ceb],
                         'dr', label="Local Maximums for signal", markersize=2)
        self.plot_7.annotations(self.xdata[indexes_for_ceb],self.z1_smooht_data[indexes_for_ceb])

        # u9
        self.plot_8 = Plot()
        self.plot_8.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Right Polarization", (1, 1), "linear")
        self.plot_8.plot(self.xdata, self.z2_smooht_data,
                         'b', label='Signal - polynomial', markersize=1)
        self.plot_8.plot(self.xdata[indexes_for_ceb2],
                         self.z2_smooht_data[indexes_for_ceb2],
                         'dr', label="Local Maximums for signal", markersize=2)
        self.plot_8.annotations(self.xdata[indexes_for_ceb2], self.z2_smooht_data[indexes_for_ceb2])

        # uAVG
        self.plot_9 = Plot()
        self.plot_9.creatPlot(self.grid, 'Velocity (km sec$^{-1}$)',
                              'Flux density (Jy)', "Average Polarization", (1, 2), "linear")
        self.plot_9.plot(self.xdata, self.avg_y_smooht_data,
                         'b', label='Signal - polynomial', markersize=1)
        self.plot_9.plot(self.xdata[indexes_for_avg],
                         self.avg_y_smooht_data[indexes_for_avg],
                         'dr', label="Local Maximums for signal", markersize=2)
        self.plot_9.annotations(self.xdata[indexes_for_avg], self.avg_y_smooht_data[indexes_for_avg])

        self.grid.addWidget(self.plot_7, 0, 0)
        self.grid.addWidget(self.plot_8, 0, 1)
        self.grid.addWidget(self.plot_9, 0, 2)

    def create_result(self):
        """

        :return: None
        """
        result_file_name = self.source + "_" + self.line + ".json"
        result_file_path = get_configs("paths", "resultFilePath")
        expername = ".".join([self.data_file.split("/")[-1].split(".")[0],
                             self.data_file.split("/")[-1].split(".")[1]])
        source_velocities = get_configs('velocities',
                                        self.source + "_" +
                                        str(self.line)).replace(" ", "").split(",")
        index_range_for_local_maxima = int(get_configs('parameters',
                                                       "index_range_for_local_maxima"))
        mjd = expername.split("_")[1]
        location = expername.split("_")[2]
        iteration_number = expername.split("_")[3]
        gauss_lines = get_configs("gauss_lines",
                                  self.source + "_" + get_args("line")).replace(" ", "").split(",")

        if os.path.isfile(result_file_path + result_file_name):
            pass
        else:
            os.system("touch " + result_file_path + result_file_name)

            result_file = open(result_file_path + result_file_name, "w")
            result_file.write("{ \n" + "\n}")
            result_file.close()

        with open(result_file_path + result_file_name) as result_data:
            result = json.load(result_data)

        if expername not in result:
            result[expername] = dict()
        indexies_for_source_velocities = [0] * len(source_velocities)
        for index in range(0, len(source_velocities)):
            indexies_for_source_velocities[index] = (
                np.abs(self.xdata - float(source_velocities[index]))).argmin()

        max_amplitude_list_u1 = list()
        max_amplitude_list_u9 = list()
        max_amplitude_list_uavg = list()
        for index in indexies_for_source_velocities:
            max_amplitude_list_tmp_u1 = list()
            max_amplitude_list_tmp_u9 = list()
            max_amplitude_list_tmp_uavg = list()
            for i in range(index - index_range_for_local_maxima,
                           index + index_range_for_local_maxima):
                max_amplitude_list_tmp_u1.append(self.z1_not_smooht_data[i])
                max_amplitude_list_tmp_u9.append(self.z2_not_smooht_data[i])
                max_amplitude_list_tmp_uavg.append(self.avg_y_not_smoohtData[i])
            max_amplitude_list_u1.append(max_amplitude_list_tmp_u1)
            max_amplitude_list_u9.append(max_amplitude_list_tmp_u9)
            max_amplitude_list_uavg.append(max_amplitude_list_tmp_uavg)

        max_apmlitudes_u1 = [np.max(value) for value in max_amplitude_list_u1]
        max_apmlitudes_u9 = [np.max(value) for value in max_amplitude_list_u9]
        max_apmlitudes_uavg = [np.max(value) for value in max_amplitude_list_uavg]

        for maximum in range(0, len(max_apmlitudes_u1)):
            max_apmlitudes_u1[maximum] = [source_velocities[maximum], max_apmlitudes_u1[maximum]]
            max_apmlitudes_u9[maximum] = [source_velocities[maximum], max_apmlitudes_u9[maximum]]
            max_apmlitudes_uavg[maximum] = \
                [source_velocities[maximum], max_apmlitudes_uavg[maximum]]

        result[expername]["modifiedJulianDays"] = mjd
        result[expername]["location"] = location
        result[expername]["Iteration_number"] = int(iteration_number)

        result[expername]["polarizationU1"] = max_apmlitudes_u1
        result[expername]["polarizationU9"] = max_apmlitudes_u9
        result[expername]["polarizationAVG"] = max_apmlitudes_uavg
        result[expername]["flag"] = False
        if get_args("calibType") == "SDR":
            result[expername]["type"] = "SDR"
        else:
            result[expername]["type"] = "DBBC"
        gaussian_areas, _, _, _, _, gauss_lines, \
        gaussiana_amplitudes, gaussiana_mean, gaussiana_std = \
            compute_gauss(self.xdata, self.avg_y_not_smoohtData, gauss_lines)

        result[expername]["areas"] = gaussian_areas
        result[expername]["gauss_amp"] = gaussiana_amplitudes
        result[expername]["gauss_mean"] = gaussiana_mean
        result[expername]["gauss_STD"] = gaussiana_std

        result[expername]["AVG_STON_LEFT"] = \
            signal_to_noise_ratio(self.xdata, self.z1_not_smooht_data, self.cuts)
        result[expername]["AVG_STON_RIGHT"] = \
            signal_to_noise_ratio(self.xdata, self.z2_not_smooht_data, self.cuts)
        result[expername]["AVG_STON_AVG"] = \
            signal_to_noise_ratio(self.xdata, self.avg_y_not_smoohtData, self.cuts)

        with open(result_file_path + result_file_name, "w") as output:
            output.write(json.dumps(result, indent=2))

        total_results = np.transpose([self.xdata, self.z1_smooht_data,
                                      self.z2_smooht_data, self.avg_y_smooht_data])
        total_results2 = np.transpose([self.xdata, self.z1_not_smooht_data,
                                       self.z2_not_smooht_data, self.avg_y_not_smoohtData])
        result_file = h5py.File(self.data_file, "a")
        if "amplitude_corrected" in result_file:
            amplitude_corrected = result_file["amplitude_corrected"]
            amplitude_corrected_not_smooht = result_file["amplitude_corrected_not_smooht"]
            amplitude_corrected[...] = total_results
            amplitude_corrected_not_smooht[...] = total_results2
        else:
            result_file.create_dataset("amplitude_corrected", data=total_results)
            result_file.create_dataset("amplitude_corrected_not_smooht", data=total_results2)
        result_file.close()
        self._quit()

    def center(self):
        """

        :return: None
        """
        frame_geometry = self.frameGeometry()
        centre_position = QDesktopWidget().availableGeometry().center()
        frame_geometry.moveCenter(centre_position)
        self.move(frame_geometry.topLeft())

    @QtCore.pyqtSlot()
    def _quit(self):
        """

        :return: None
        """
        for i in reversed(range(self.grid.count())):
            self.grid.itemAt(i).widget().deleteLater()

        self.hide()
        self.close()
        del self


def main():
    """

    :return: None
    """
    q_app = QApplication(sys.argv)
    application = Analyzer()
    application.show()
    application.showMaximized()
    sys.exit(q_app.exec_())


if __name__ == "__main__":
    main()
