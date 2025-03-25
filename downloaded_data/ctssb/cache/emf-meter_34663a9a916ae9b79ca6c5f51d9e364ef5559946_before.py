#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import sys
import csv
import time
import os.path
from datetime import datetime

from Rail350V import Rail350V


class MeterReader(object):

    def __init__(self, channel_prefix, serial_port):
        self.PHASES = Rail350V.PHASE.keys()
        self.ATTRIBUTES = Rail350V.AVAILABLE_ATTRIBUTES
        self.channel_prefix = channel_prefix

        try:
            self.meter = Rail350V(serial_port, 1)
        except OSError:
            raise

    def aquire_data(self):
        aquired_data = {}

        for phase in self.PHASES:
            for attribute in self.ATTRIBUTES:
                channel_name = "{0}.phase-{1}.{2}".format(
                    self.channel_prefix, phase, attribute)
                datum = {
                    'timestamp': datetime.utcnow(),
                    'value': self.meter.read_phase_property(
                        attribute=attribute, phase=phase)
                }
                aquired_data.update({channel_name: datum})

        return aquired_data


class MeterCSVLogger(object):

    def __init(self, csv_file):
        self.CSV_HEADERS = ['channel', 'timestamp', 'value']
        self.file = csv_file
        if not os.path.isfile(self.file):
            with open(self.file, 'wb') as fp:
                writer = csv.writer(fp)
                writer.write(self.CSV_HEADERS)

    def write_meter_data(self, meter_data):
        with open(self.file, 'wb') as fp:
            writer = csv.writer(fp)

            for channel, datum in meter_data.iteritems():
                row = [channel, datum['timestamp'], datum['value']]
                writer.write(row)


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("generator_name", help="name of the generator")
        parser.add_argument("serial_port", help="serial port")
        parser.add_argument("csv_file", help="csv log file location")
        args = parser.parse_args()

        reader = MeterReader(args.generator_name, args.serial_port)
        csv_logger = MeterCSVLogger(args.csv_file)

        while True:
            d = reader.aquire_data()
            print d
            print "**********"
            csv_logger.write_meter_data(d)
            time.sleep(5)

    except KeyboardInterrupt:
        print "Shutdown requested...exiting"
        sys.exit(0)

if __name__ == '__main__':
    main()
