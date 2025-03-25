#!/usr/bin/env python
#
# Copyright 2014 Matthew Wall
# See the file LICENSE.txt for your rights.

"""Driver for ADS WS1 weather stations.

Thanks to Steve (sesykes71) for the testing that made this driver possible.

Thanks to Jay Nugent (WB8TKL) and KRK6 for weather-2.kr6k-V2.1
  http://server1.nuge.com/~weather/
"""

from __future__ import with_statement
import serial
import syslog
import time

import weewx.drivers

DRIVER_NAME = 'WS1'
DRIVER_VERSION = '0.16'


def loader(config_dict, _):
    return WS1Driver(**config_dict[DRIVER_NAME])

def confeditor_loader():
    return WS1ConfEditor()


INHG_PER_MBAR = 0.0295333727
METER_PER_FOOT = 0.3048
MILE_PER_KM = 0.621371

DEFAULT_PORT = '/dev/ttyS0'
DEBUG_READ = 0


def logmsg(level, msg):
    syslog.syslog(level, 'ws1: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)

def _format(buf):
    return ' '.join(["%0.2X" % ord(c) for c in buf])

class WS1Driver(weewx.drivers.AbstractDevice):
    """weewx driver that communicates with an ADS-WS1 station
    
    port - serial port
    [Required. Default is /dev/ttyS0]

    polling_interval - how often to query the serial interface, seconds
    [Optional. Default is 1]

    max_tries - how often to retry serial communication before giving up
    [Optional. Default is 5]

    retry_wait - how long to wait, in seconds, before retrying after a failure
    [Optional. Default is 10]
    """
    def __init__(self, **stn_dict):
        self.port = stn_dict.get('port', DEFAULT_PORT)
        self.polling_interval = float(stn_dict.get('polling_interval', 1))
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 10))
        self.last_rain = None
        loginf('driver version is %s' % DRIVER_VERSION)
        loginf('using serial port %s' % self.port)
        loginf('polling interval is %s' % self.polling_interval)
        global DEBUG_READ
        DEBUG_READ = int(stn_dict.get('debug_read', DEBUG_READ))

    @property
    def hardware_name(self):
        return "WS1"

    def genLoopPackets(self):
        ntries = 0
        while ntries < self.max_tries:
            ntries += 1
            try:
                packet = {'dateTime': int(time.time() + 0.5),
                          'usUnits': weewx.US}
                # open a new connection to the station for each reading
                with Station(self.port) as station:
                    readings = station.get_readings()
                data = Station.parse_readings(readings)
                packet.update(data)
                self._augment_packet(packet)
                ntries = 0
                yield packet
                if self.polling_interval:
                    time.sleep(self.polling_interval)
            except (serial.serialutil.SerialException, weewx.WeeWxIOError), e:
                logerr("Failed attempt %d of %d to get LOOP data: %s" %
                       (ntries, self.max_tries, e))
                time.sleep(self.retry_wait)
        else:
            msg = "Max retries (%d) exceeded for LOOP data" % self.max_tries
            logerr(msg)
            raise weewx.RetriesExceeded(msg)

    def _augment_packet(self, packet):
        # calculate the rain delta from rain total
        if self.last_rain is not None:
            packet['rain'] = packet['long_term_rain'] - self.last_rain
        else:
            packet['rain'] = None
        self.last_rain = packet['long_term_rain']

        # no wind direction when wind speed is zero
        if 'windSpeed' in packet and not packet['windSpeed']:
            packet['windDir'] = None


class Station(object):
    def __init__(self, port):
        self.port = port
        self.baudrate = 2400
        self.timeout = 3
        self.serial_port = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, _, value, traceback):
        self.close()

    def open(self):
        logdbg("open serial port %s" % self.port)
        self.serial_port = serial.Serial(self.port, self.baudrate,
                                         timeout=self.timeout)

    def close(self):
        if self.serial_port is not None:
            logdbg("close serial port %s" % self.port)
            self.serial_port.close()
            self.serial_port = None

    def read(self, nchar=1):
        buf = self.serial_port.read(nchar)
        n = len(buf)
        if n != nchar:
            if DEBUG_READ and n:
                logdbg("partial buffer: '%s'" % _format(buf))
            raise weewx.WeeWxIOError("Read expected %d chars, got %d" %
                                     (nchar, n))
        return buf

    def get_readings(self):
        b = []
        bad_byte = False
        while True:
            c = self.read(1)
            if c == "\r":
                break
            elif c == '!' and len(b) > 0:
                break
            elif c == '!':
                b = []
            else:
                b.append(c)
        if DEBUG_READ:
            logdbg("bytes: '%s'" % _format(b))
        if len(b) != 48:
            raise weewx.WeeWxIOError("Got %d bytes, expected 48" % len(b))
        return ''.join(b)

    @staticmethod
    def parse_readings(buf):
        """WS1 station emits data in PeetBros format:

        http://www.peetbros.com/shop/custom.aspx?recid=29

        Each line has 51 characters - 2 header bytes, 48 data bytes, and a
        carriage return:

        !!000000BE02EB000027700000023A023A0025005800000000\r
          SSSSXXDDTTTTLLLLPPPPttttHHHHhhhhddddmmmmRRRRWWWW

          SSSS - wind speed (0.1 kph)
          XX   - wind direction calibration
          DD   - wind direction (0-255)
          TTTT - outdoor temperature (0.1 F)
          LLLL - long term rain (0.01 in)
          PPPP - pressure (0.1 mbar)
          tttt - indoor temperature (0.1 F)
          HHHH - outdoor humidity (0.1 %)
          hhhh - indoor humidity (0.1 %)
          dddd - date (day of year)
          mmmm - time (minute of day)
          RRRR - daily rain (0.01 in)
          WWWW - one minute wind average (0.1 kph)
        """
        # FIXME: peetbros could be 40 bytes or 44 bytes, what about ws1?
        # FIXME: peetbros uses two's complement for temp, what about ws1?
        # FIXME: is the pressure reading 'pressure' or 'barometer'?
        data = dict()
        data['windSpeed'] = Station._decode(buf[0:4], 0.1 * MILE_PER_KM) # mph
        data['windDir'] = Station._decode(buf[6:8], 1.411764)  # compass deg
        data['outTemp'] = Station._decode(buf[8:12], 0.1)  # degree_F
        data['long_term_rain'] = Station._decode(buf[12:16], 0.01)  # inch
        data['pressure'] = Station._decode(buf[16:20], 0.1 * INHG_PER_MBAR)  # inHg
        data['inTemp'] = Station._decode(buf[20:24], 0.1)  # degree_F
        data['outHumidity'] = Station._decode(buf[24:28], 0.1)  # percent
        data['inHumidity'] = Station._decode(buf[28:32], 0.1)  # percent
        data['day_of_year'] = Station._decode(buf[32:36])
        data['minute_of_day'] = Station._decode(buf[36:40])
        data['daily_rain'] = Station._decode(buf[40:44], 0.01)  # inch
        data['wind_average'] = Station._decode(buf[44:48], 0.1 * MILE_PER_KM)  # mph
        return data

    @staticmethod
    def _decode(s, multiplier=None, neg=False):
        v = None
        try:
            v = int(s, 16)
            if neg:
                bits = 4 * len(s)
                if v & (1 << (bits - 1)) != 0:
                    v -= (1 << bits)
            if multiplier is not None:
                v *= multiplier
        except ValueError, e:
            if s != '----':
                logdbg("decode failed for '%s': %s" % (s, e))
        return v


class WS1ConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[WS1]
    # This section is for the ADS WS1 series of weather stations.

    # Serial port such as /dev/ttyS0, /dev/ttyUSB0, or /dev/cuaU0
    port = /dev/ttyUSB0

    # The driver to use:
    driver = weewx.drivers.ws1
"""

    def prompt_for_settings(self):
        print "Specify the serial port on which the station is connected, for"
        print "example /dev/ttyUSB0 or /dev/ttyS0."
        port = self._prompt('port', '/dev/ttyUSB0')
        return {'port': port}


# define a main entry point for basic testing of the station without weewx
# engine and service overhead.  invoke this as follows from the weewx root dir:
#
# PYTHONPATH=bin python bin/weewx/drivers/ws1.py

if __name__ == '__main__':
    import optparse

    usage = """%prog [options] [--help]"""

    syslog.openlog('ws1', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='display driver version')
    parser.add_option('--port', dest='port', metavar='PORT',
                      help='serial port to which the station is connected',
                      default=DEFAULT_PORT)
    (options, args) = parser.parse_args()

    if options.version:
        print "ADS WS1 driver version %s" % DRIVER_VERSION
        exit(0)

    with Station(options.port) as s:
        while True:
            print time.time(), s.get_readings()
