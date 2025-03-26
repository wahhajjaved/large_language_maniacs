#! /usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import os
import argparse
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import datetime
import json
import subprocess

from PyQt5.QtWidgets import QWidget, QGridLayout, QApplication, QDesktopWidget, QToolButton, QLabel, QPushButton
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

from ploting_qt5 import  Plot
from parsers._configparser import ConfigParser
from help import *
from monitor.months import Months

matplotlib.use('Qt5Agg')


def parseArguments():
    parser = argparse.ArgumentParser(description='''Monitoring spectre change in time. ''', epilog="""Monitor Spectre.""")
    parser.add_argument("source", help="Source Name", type=str)
    parser.add_argument("line", help="line", type=int)
    parser.add_argument("-c", "--config", help="Configuration cfg file", type=str, default="config/config.cfg")
    parser.add_argument("-v","--version", action="version", version='%(prog)s - Version 1.0')
    parser.add_argument("-i", "--index", help="Configuration cfg file", type=int, default=0)
    args = parser.parse_args()
    return args


def getArgs(key):
    return str(parseArguments().__dict__[key])


def getConfigs(key, value):
    configFilePath = getArgs("config")
    config = ConfigParser.getInstance()
    config.CreateConfig(configFilePath)
    return config.getConfig(key, value)


class SpectreTime(QWidget):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.source_name = getConfigs("Full_source_name", self.source)
        self.output_path = getConfigs("paths", "notSmoohtFilePath") + "/" + self.source + "/" + getArgs("line") + "/"
        output_files = [file for file in os.listdir(self.output_path) if file.startswith(self.source + "_")]
        self.index = int(getArgs("index"))
        self.months = Months()
        dates = [self.__create_date(file_name) for file_name in output_files]
        dates = sorted(dates)
        self.sorted_file_names = []

        for f in range(0, len(dates)):
            for file_name in output_files:
                if self.__create_date(file_name) == dates[f]:
                    self.sorted_file_names.append(file_name)

        __result_file = getConfigs("paths", "resultFilePath") + "/" + self.source + "_" + getArgs("line") + ".json"

        with open(__result_file) as result_data:
            self.results = json.load(result_data)

        self.setWindowIcon(QIcon('viraclogo.png'))
        self.center()
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        self.setLayout(self.grid)
        self.setWindowTitle(self.source_name)
        self.InformationLb = QLabel("")
        self.__addWidget(self.InformationLb, 0, 2)
        self.previous = QToolButton(arrowType=Qt.LeftArrow)
        self.next = QToolButton(arrowType=Qt.RightArrow)
        self.previous.clicked.connect(self.previous_spectre)
        self.next.clicked.connect(self.next_spectre)
        self.__addWidget(self.previous, 1, 0)
        self.__addWidget(self.next, 1, 2)
        create_movie_button = QPushButton('Create movie', self)
        create_movie_button.clicked.connect(self.create_movie)
        self.__addWidget(create_movie_button, 1, 3)
        self.x_lim = None
        self.y_lim = None
        self.previous_line = None
        self.first_plot = False
        self.spectre_plot = Plot()
        self.spectre_plot.creatPlot(self.grid, "Velocity (km sec$^{-1}$)", "Flux density (Jy)", getConfigs("Full_source_name", self.source), (1, 1), "linear")
        self.spectre_plot.addZoomEvent(self.zoom_callback)
        self.plot()

    def __addWidget(self, widget, row, colomn):
        self.grid.addWidget(widget, row, colomn)

    def center(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def __create_date(self, file_name):
        tmpDate = file_name.split("/")[-1].split("_")
        tmpDate[-4] = self.months.getMonthNumber([tmpDate[-4]][0])
        date = datetime.datetime.strptime(" ".join(tmpDate[1:-2]), "%H %M %S %d %m %Y")
        return date

    def create_movie(self):
        np.random.seed(19680801)
        files = []

        i = 0
        for file_name in self.sorted_file_names:
            data = np.fromfile(self.output_path + file_name, dtype="float64", count=-1, sep=" ").reshape((file_len(self.output_path + file_name), 4))
            plt.cla()
            x = data[:, [0]]
            y = data[:, [3]]
            plt.rc('xtick', labelsize=8)
            plt.rc('ytick', labelsize=8)
            plt.plot(x, y, label=self.__create_date(file_name))
            plt.xlim(self.x_lim)
            plt.ylim(self.y_lim)
            plt.legend(loc=1, prop={'size': 12})
            plt.xlabel("Velocity (km sec$^{-1}$)", fontsize=6)
            plt.ylabel("Flux density (Jy)", fontsize=6)
            plt.grid(True)
            fname = '_tmp%03d.png' % i
            i += 1
            print('Saving frame', fname)
            plt.savefig(fname, dpi=300, quality=100, format="png")
            files.append(fname)


        print('Making movie animation.mpg - this may take a while')
        subprocess.call("mencoder 'mf://_tmp*.png' -mf w=800:h=600:type=png:fps=10 -ovc lavc "
                        "-lavcopts vcodec=mpeg4:mbd=2:trell:autoaspect -oac copy -o " + self.source + "_spectre_movie.mpg", shell=True)

        for fname in files:
            os.remove(fname)

    def next_spectre(self, event):
        if self.index < len(self.sorted_file_names) +1:
            self.index += 1
        else:
            self.index = 0
        self.plot()

    def previous_spectre(self, event):
        if self.index > 0:
            self.index -= 1
        else:
            self.index = len(self.sorted_file_names) -1
        self.plot()
        
    def zoom_callback(self, event):
        if self.first_plot:
            self.x_lim = event.get_xlim()
            self.y_lim = event.get_ylim()

    def plot(self):
        file_name = self.output_path + self.sorted_file_names[self.index]
        data = np.fromfile(file_name, dtype="float64", count=-1, sep=" ").reshape((file_len(file_name), 4))

        date = self.__create_date(file_name)
        date = str(date)
        time = date.split(" ")[1]
        tmp_date = date.split(" ")[0].split("_")[0]
        tmp_date = tmp_date[2] + "_" + tmp_date[1] + "_" + tmp_date[0]
        iteration = file_name.split("/")[-1].split("_")[-1].split(".")[0]

        exper_name = ""
        for exper in self.results:
            experiment = self.results[exper]
            if experiment["time"] == time or experiment["Date"] == tmp_date:
                exper_name = exper

        if len(exper_name) > 0:
            type = self.results[exper_name]["type"]
            modifiedJulianDays = self.results[exper_name]["modifiedJulianDays"]
            flag = self.results[exper_name]["flag"]

        self.InformationLb.setText("Date " + str(date) + "\n" + "Iteration " + str(iteration)+ "\n" + "Modified Julian Days "+ str(modifiedJulianDays) + "\n" + "Type " + type + "\n" + "Flag " + str(flag))

        x = data[:, [0]]
        y = data[:, [3]]

        line = self.spectre_plot.plot(x, y, "-")

        if self.previous_line:
            self.previous_line[0].remove()

        self.previous_line = line

        self.first_plot = True

        if self.x_lim:
            self.spectre_plot.set_xlim(self.x_lim)
        else:
            self.x_lim = self.spectre_plot.get_xlim()

        if self.y_lim:
            self.spectre_plot.set_ylim(self.y_lim)
        else:
            self.y_lim = self.spectre_plot.get_ylim()

        self.__addWidget(self.spectre_plot, 0,1)


class Main():

    def __parse_arguments(self):
        self.source = getArgs("source")

    def __create_app(self):
        qApp = QApplication(sys.argv)
        aw = SpectreTime(self.source)
        aw.show()
        sys.exit(qApp.exec_())
        sys.exit(0)

    @classmethod
    def run(cls):
        Main.__parse_arguments(cls)
        Main.__create_app(cls)


def main():
    Main().run()
    sys.exit(0)


if __name__ == "__main__":
    main()
