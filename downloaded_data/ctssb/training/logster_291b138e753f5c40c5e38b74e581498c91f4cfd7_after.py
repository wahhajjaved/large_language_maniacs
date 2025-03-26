###  A sample logster parser file that can be used to count the number
###  of various stats from Digimap.
###
###  This class was copied from SampleLogster.
###
###  For example:
###  sudo ./logster --dry-run --output=ganglia DMWebLogster /var/log/httpd/access_log
###
###
###  Copyright 2011, Etsy, Inc., 2013 University of Edinburgh
###
###  This file is part of Logster.
###
###  Logster is free software: you can redistribute it and/or modify
###  it under the terms of the GNU General Public License as published by
###  the Free Software Foundation, either version 3 of the License, or
###  (at your option) any later version.
###
###  Logster is distributed in the hope that it will be useful,
###  but WITHOUT ANY WARRANTY; without even the implied warranty of
###  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
###  GNU General Public License for more details.
###
###  You should have received a copy of the GNU General Public License
###  along with Logster. If not, see <http://www.gnu.org/licenses/>.
###

import time
import re

from logster.logster_helper import MetricObject, LogsterParser
from logster.logster_helper import LogsterParsingException

class DMWebLogster(LogsterParser):

    def __init__(self, option_string=None):
        '''Initialize any data structures or variables needed for keeping track
        of the tasty bits we find in the log we are parsing.'''
        self.logins = {}
        self.registrations = {}
        self.downloads = {}
        self.mapproxy = {}

        # Regular expression for matching lines we are interested in, and capturing
        # fields from the line.
        self.regLogin = re.compile('.*GET /login.* HTTP/\d.\d" (?P<code>\d+) .*')
        self.regRegister = re.compile('.*POST /registrations/register-user HTTP/\d.\d" (?P<code>\d+) .*')
        self.regDownloads = re.compile('.*POST /datadownload/submitorder.* HTTP/\d.\d" (?P<code>\d+) .*')
        self.regMapproxy = re.compile('.*GET /mapproxy.* HTTP/\d.\d" (?P<code>\d+) .*')


    def parse_line(self, line):
        '''This function should digest the contents of one line at a time, updating
        object's state variables. Takes a single argument, the line to be parsed.'''

        # Apply regular expression to each line and extract interesting bits.
        regLoginMatch = False
        if "MONITOR" not in line and "idp.edina.ac.uk" not in line:
          regLoginMatch = self.regLogin.match(line)
        regRegisterMatch = self.regRegister.match(line)
        regDownloadMatch = self.regDownloads.match(line)
        regMapproxyMatch = self.regMapproxy.match(line)

        # FIXME crappy duplicated code.. will be moving to logstash anyway
        if regLoginMatch:
          linebits = regLoginMatch.groupdict()
          code = linebits['code']
          if code in self.logins:
            self.logins[code] += 1
          else:
            self.logins[code] = 1
        elif regRegisterMatch:
          linebits = regRegisterMatch.groupdict()
          code = linebits['code']
          if code in self.registrations:
            self.registrations[code] += 1
          else:
            self.registrations[code] = 1
        elif regDownloadMatch:
          linebits = regDownloadMatch.groupdict()
          code = linebits['code']
          if code in self.downloads:
            self.downloads[code] += 1
          else:
            self.downloads[code] = 1
        elif regMapproxyMatch:
          linebits = regMapproxyMatch.groupdict()
          code = linebits['code']
          if code in self.mapproxy:
            self.mapproxy[code] += 1
          else:
            self.mapproxy[code] = 1
        # ignore non-matching lines

    def get_state(self, duration):
        '''Run any necessary calculations on the data collected from the logs
        and return a list of metric objects.'''

        metricObjects = []
        for code, count in self.logins.items():
          metricObjects.append( MetricObject( "logins_count." + code, count, "Logins per minute" ) )
        for code, count in self.registrations.items():
          metricObjects.append( MetricObject( "registrations_count." + code, count, "Registrations per minute" ) )
        for code, count in self.downloads.items():
          metricObjects.append( MetricObject( "download_submit_count." + code, count, "Download Submits per minute" ) )
        for code, count in self.mapproxy.items():
          metricObjects.append( MetricObject( "mapproxy_count." + code, count, "Mapproxy tiles per minute" ) )

        return metricObjects
