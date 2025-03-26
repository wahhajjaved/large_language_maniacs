#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io, csv, zipfile
import re
from datetime import datetime
from collections import namedtuple

class LocalData():
    TFX_DIR = 'TFX_data/'

    def __init__(self, start_date=None, end_date=None):
        self.test_data = {'start_date':datetime(**start_date) if isinstance(start_date, dict) else datetime.now(),
                          'end_date':datetime(**end_date) if isinstance(end_date, dict) else datetime.now()}

    def _scan_tfx_directory(self):
        database = {}
        for filename in sorted(os.listdir("TFX_data")):
            if re.match(r'[A-Z]{6}-\d{4}-\d{2}.zip', filename):
                instrument, year, month = re.match(r'([A-Z]{6})-(\d{4})-(\d{2}).zip', filename).groups()
                instrument = instrument.upper()
                instrument = (instrument[:3], instrument[-3:])
                starting_date = datetime(int(year), int(month), 1)
                database.setdefault(instrument, {}).setdefault(starting_date, filename)
        return database

    def get_tick_data(self, instrument):
        """
        Read the TFX
        """
        db = self._scan_tfx_directory()
        filenames = [db[instrument][k] for k in sorted(db[instrument]) if self.test_data['end_date'] > k >= self.test_data['start_date']]

        Tick = namedtuple("Tick", "datetime buy sell")

        for filename in filenames:
            with zipfile.ZipFile(self.TFX_DIR + filename) as zip_file:
                csv_file = io.TextIOWrapper(zip_file.open(zip_file.namelist()[0]))
                csv_reader = csv.reader(csv_file, delimiter=',')
                for row in csv_reader:
                    tick_datetime = datetime.strptime(row[1], '%Y%m%d %H:%M:%S.%f')
                    if self.test_data['start_date'] >= tick_datetime > self.test_data['end_date']:
                        next
                    else:
                        yield Tick(tick_datetime, float(row[3]), float(row[2]))

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
