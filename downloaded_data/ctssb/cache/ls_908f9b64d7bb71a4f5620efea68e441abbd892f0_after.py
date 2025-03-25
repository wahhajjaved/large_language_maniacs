#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
.. module:: resultlog
    :platform: Linux, Windows
    :synopsis: main module

.. moduleauthor:: Zoltan Siki <siki@agt.bme.hu>
"""
import os
import tempfile
import datetime
import time

class ResultLog(object):
    """ File based logging for Surveying Calculations. Events & calculation results are logged into this file.
    """
    resultlog_message = ""
    
    def __init__(self, logfile, repeat_count=3):
        """ initialize log file if the given file cannot be opened for output then a SurveyingCalculation.log file in the temperary directory will be used

            :param logfile: name of the log file it will be created if neccessary, messages will be appended to the end
            :param repeat_count: retry count on fail accessing log file
        """
        self.repeat_count = repeat_count   # retry count for i/o operations
        for i in range(self.repeat_count * 2):
            try:
                f = open(logfile, "a")
                break
            except(IOError):
                f = None
                if i == self.repeat_count:
                    logfile = os.path.join(tempfile.gettempdir(), "SurveyingCalculation.log")
        f.close()
        self.logfile = logfile

    def reset(self):
        """ Delete content of log file
        """
        for i in range(self.repeat_count):
            try:
                os.remove(self.logfile)
                break
            except(OSError):
                pass

    def write(self, msg = ""):
        """ Write a  simple message to log

            :param msg: message to write
        """
        for i in range(self.repeat_count):
            try:
                f = open(self.logfile, "a")
                for i in range(self.repeat_count):
                    try:
                        f.write( (msg + '\n').encode('utf8') )
                        break
                    except (IOError):
                        pass
                break
            except (IOError):
                pass
        try:
            f.close()
        except (IOError):
            pass

    def write_log(self, msg):
        """ Write log message with date & time

            :param msg: message to write
        """
        d = time.strftime("%Y-%m-%d %H:%M:%S",
            datetime.datetime.now().timetuple())
        self.write(d + " - " + msg)
