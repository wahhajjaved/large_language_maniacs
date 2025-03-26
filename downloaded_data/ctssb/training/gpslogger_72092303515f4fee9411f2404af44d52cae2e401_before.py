#!/usr/bin/env python
################################################################################
# Copyright (c) by George Ruinelli 
# License: 	GPL3
# Modified by Hiroshi Miura, 2013
################################################################################

import sys
from PySide.QtCore import *
from PySide.QtGui import *
from PySide.QtDeclarative import *
from PySide.QtGui import QDesktopServices as QDS

#import math
import platform
import time
import datetime
import os
import string
import ConfigParser
#import gconf

from datetime import tzinfo, timedelta, datetime
import logging

################################################################################
class GPSLogger(QObject):
  rootpath = "/opt/gps-logger/"
  datapath = "/home/user/MyDocs/GPS-Logger"
  version = "??"
  build = "?"
  config = None
  gpx = None

  def __init__(self):
    super(GPSLogger, self).__init__()
    self._setPath()
    self._loadVersion()
    self.config = Configuration()
    self.gpx = GPX()

  #Set needed path
  def _setPath(self):
    if(platform.machine().startswith('arm')):
      pass
    else:
      self.rootpath = "./"
      self.datapath = "./data/"
    try:
      os.makedirs(self.datapath)
    except:
      pass

  #Load version file
  def _loadVersion(self):
    try:
      file = open(self.rootpath + "version", 'r')
      self.version = file.readline()
      self.version=self.version[:-1]
      self.build = file.readline()
      logging.info("Version: "+str(self.version)+ "-"+str(self.build))
    except:
      logging.warning("Version file not found, please check your installation!")

  def does_opt_in(self):
    logging.info("config.opt_in:", self.config.opt_in)
    return self.config.opt_in

  def finished(self):
    self.config.write()
    if(self.gpx.recording == True):
      logging.info("we are still recording, close file properly")
      self.gpx.stop_recording(gpx)
    logging.debug("Closing")

  @Slot(str, int, result=str)
  def start(self, filename, interval):
    return self.gpx.start_recording(self.datapath, filename, interval)

  @Slot()
  def stop(self):
    logging.debug("stop")
    self.gpx.stop_recording()
      
  @Slot(float, float, float, float)
  def add_point(self, lon, lat, alt, speed):
    logging.debug("recording", lon, lat, alt, speed, time)
    self.gpx.add_entry(lon, lat, alt, speed)
    
  @Slot(float, float, float, float, int)
  def add_waypoint(self, lon, lat, alt, speed, waypoint):
    logging.debug("recording", lon, lat, alt, speed, time)
    self.gpx.add_waypoint(lon, lat, alt, speed, waypoint)

  @Slot(result=str)
  def get_version(self):      
    return str(self.version) + "-" + str(self.build)

  @Slot(bool)
  def Opt_In(self, v):      
    self.config.set_opt_in(v)
    if(v == False):
      self.config.write()
      logging.info("We have to quit now, sry")
      quit()

################################################################################
class Configuration():
  configpath = ""
  configfile = "config.conf"
  opt_in = False

  def __init__(self):
    self.configpath = os.path.join(QDS.storageLocation(QDS.DataLocation),
      "GPS-Logger")
    self.configfile = self.configpath + "/" + self.configfile
    self.load()

  def load(self):
    logging.info("Loading configuration from:", self.configfile)
    self.ConfigParser = ConfigParser.SafeConfigParser()
    try:
      self.ConfigParser.read(self.configfile)
    except: #use default config
      logging.warning("Configuration file "+ self.configfile +
        " not existing or not compatible")
    try:
      self.ConfigParser.add_section('main')
    except:
      pass
    try:
      self.opt_in = self.ConfigParser.getboolean("main", "opt_in")
      logging.info("Configuration loaded")
    except:
      logging.warning("Error loading configuration, using default value")

  def write(self):
    logging.info("Write configuration to:", self.configfile)
    self.ConfigParser.set('main', 'opt_in', str(self.opt_in))
    try:
      os.makedirs(self.configpath)
    except:
      pass
    try:
      handle = open(self.configfile, 'w')
      self.ConfigParser.write(handle)
      handle.close()
      logging.info("Configuration saved")
    except:
      logging.warning("Failed to write configuration file!")

  def set_opt_in(self, v):
    self.opt_in = v

################################################################################
class GPX():
  filehandle = None
  recording = False
  waypoints = ""

  def start_recording(self, datapath, filename, interval):
    if(filename == ""):
      filename = "track"
    
    suffix = 1
    filename2 = filename + ".gpx" #try first without a suffix
    full_filename = datapath + "/" + filename2

    if(os.path.exists(full_filename)):
      while(os.path.exists(full_filename)):
        filename2 = filename + "_" + str(suffix) + ".gpx"
        full_filename = datapath + "/" + filename2
        suffix = suffix + 1
    logging.info("Start recording", full_filename, interval)
    try:
      self.filehandle = open(full_filename, 'w')
      self.recording = True
      self.filehandle.write(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"no\" ?>\n")
      txt = '''\
<gpx xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     creator="N9 GPS Logger"  version="1.1"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">\n'''
      self.filehandle.write(txt)
      txt = '''\
  <metadata>
    <link href="http://www.ruinelli.ch">
	    <text>N9 GPS Logger</text>
    </link>
  </metadata>
  '''
      self.filehandle.write(txt)
      txt = "<trk>\n" + \
        "<name>" + str(filename) + "</name>\n" + \
        "		<trkseg>\n"
      self.filehandle.write(txt)
      self.waypoints = ""
      return filename2
    except:
      logging.warning("failed to open file:", full_filename)
      return ""

  def _get_iso_datetime(self):
    tt = datetime.utcnow().timetuple() #time in UTC

    #add leading zeros
    if(int(tt[1])<10):
      mm = "0" + str(tt[1])
    else:
      mm = str(tt[1])
    if(int(tt[2])<10):
      d = "0" + str(tt[2])
    else:
      d = str(tt[2])
    if(int(tt[3])<10):
      h = "0" + str(tt[3])
    else:
      h = str(tt[3])
    if(int(tt[4])<10):
      m = "0" + str(tt[4])
    else:
      m = str(tt[4])
    if(int(tt[5])<10):
      s = "0" + str(tt[5])
    else:
      s = str(tt[5])

    return str(tt[0]) + "-" + str(mm) + "-" + str(d) + "T" + str(h) + ":" + \
        str(m) + ":" + str(s) + "Z" #2012-07-31T20:44:36Z

  def add_entry(self, lon, lat, alt, speed):
    if(self.recording == True):
      logging.debug("adding entry")
      try:
        alt = str(int(alt))
      except:
        alt ="0"
      t = self._get_iso_datetime();
      s = speed * 3.6
      logging.debug("trk:%s,%f,%f,%f,%f", t, lat, lon, alt, s)
      txt = "		<trkpt lat=\"" + str(lat) + "\" lon=\"" + str(lon) + "\">\n" + \
        "			<ele>" + str(int(alt)) + "</ele>\n" + \
        "			<time>" + t + "</time>\n" + \
        "			<desc>Lat.=" + str(lat) + ", Long.=" + str(lon) + ", Alt.=" + \
              str(alt) + "m, Speed=" + str(s) + "Km/h</desc>\n" + \
        "		</trkpt>\n"
      self.filehandle.write(txt)
    else:
      logging.warning("file closed, can not add entry")

  def add_waypoint(self, lon, lat, alt, speed, waypoint):
    if(self.recording == True):
      loging.debug("adding waypoint")
      t = self._get_iso_datetime()
      txt = "  <wpt lat=\"" + str(lat) + "\" lon=\"" + str(lon) + "\">\n" + \
        "    <ele>" + str(int(alt)) + "</ele>\n" + \
        "    <time>" + str(t) + "</time>\n" + \
        "    <name>" + str(waypoint) + "</name>\n" + \
        "  </wpt>\n"
      self.waypoints += txt
    else:
      logging.warning("file closed, can not add entry")

  def stop_recording(self):
    logging.debug("Stop recording")
    if(self.recording == True):
      txt = '''\
    </trkseg>
  </trk>
'''
      self.filehandle.write(txt)
      self.filehandle.write(self.waypoints)
      self.filehandle.write("\n</gpx>")
    try:
      self.filehandle.close()
      self.recording = False
    except:
      pass

################################################################################

if __name__ == '__main__':
  app = QApplication(sys.argv)
  logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

  gpslogger = GPSLogger()

  # create view
  view = QDeclarativeView()
  view.setSource(QUrl.fromLocalFile(gpslogger.rootpath + 'qml/main.qml'))

  # expose the object to QML
  context = view.rootContext()
  context.setContextProperty("gpslogger", gpslogger)

  if(platform.machine().startswith('arm')):
    view.showFullScreen()
    view.show()
    if(gpslogger.does_opt_in() == False):
      root = view.rootObject()
      root.show_Opt_In()

  app.exec_()
  gpslogger.finished()

