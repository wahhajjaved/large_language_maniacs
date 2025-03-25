"""

EC2 SpotPrice Lib, GPL v3 License

Copyright (c) 2018-2019 Blake Huber

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the 'Software'), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""

import os
import sys
import re
import datetime
import inspect
from spotlib import logger


# precompiled regex pattern, datetime
re_dt = re.compile('\d{4}-[01]\d-[0-3]\d[\sT][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?Z?')

# precompiled regex pattern, datetime, no "T" separator
re_dtnot = re.compile('\d{4}-[01]\d-[0-3]\d[\s][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?Z?')

# precompiled regex pattern, date
re_date = re.compile('\d{4}-[01]\d-[0-3]\d')


def format_datetime(datetime_str):
    """
    Helper module function: Formats datetime strings & dates
    (datetime with no time component)

    Returns:
        datetime iso formatted string
    """
    def convert_dt(datetime_str):
        dt = datetime.datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        return dt.isoformat()

    if isinstance(datetime_str, str) and re_dt.match(datetime_str):
        return datetime_str if not re_dtnot.match(datetime_str) else convert_dt(datetime_str)
    return ''.join([datetime_str, 'T00:00:00']) if re_date.match(datetime_str) else datetime_str


class DurationEndpoints():
    """
    Calculates both custom and default endpoints in time which brackets
    the time period for which spot price historical data is retrieved

    Methods:
        :default_endpoints: construct default start, end datetimes;
            i.e. midnight previous day to midnight current day
        :custom_endpoints: construct customised start, end datetimes via endpoints
        :custom_duration: construct customised start, end datetimes via duration only
        :_convert_dt_string: method to reliably transform various datetime inputs into dt strings

    Use:
        from spotlib import DurationEndpoints
        d = DurationEndpoints()
    """
    def __init__(self, duration_days=1, start_dt=None, end_dt=None, debug=False):
        """
        Args:
            :duration_days (int): Number of days between endpoint dates
            :start_dt (datetime): Datetime start of spot price retrieval period
            :end_dt (datetime): Datetime endpoint of spot price retrieval period
            :debug (bool): verbose output flag

        """
        self.d_days = duration_days

        if all(x is None for x in [start_dt, end_dt]):
            self.start, self.end = self.default_endpoints(self.d_days)

        elif any(x is not None for x in [start_dt, end_dt]):
            x, y = self.calculate_duration_endpoints(start_dt, end_dt)
            self.start = x if x is not None else self.default_endpoints()[0]
            self.end = y if y is not None else self.default_endpoints()[1]

    def default_endpoints(self, duration_days=1):
        """
        Supplies the default start and end dates (dt objects) in absence
        of user supplied endpoints which frames time period from which
        to begin and end retrieving spot price data from Amazon APIs.

        Returns:  TYPE: tuple, containing:

            - start (datetime), midnight yesterday
            - end (datetime) midnight, current day

        """
        # end datetime calcs
        dt_date = datetime.datetime.today().date()
        dt_time = datetime.datetime.min.time()
        end = datetime.datetime.combine(dt_date, dt_time)

        # start datetime calcs
        duration = datetime.timedelta(days=duration_days)
        start = end - duration
        return start, end

    def custom_endpoints(self, start_time=None, end_time=None):
        """
        Calculates custom start and end dates when given a variety of
        formats including string or None. If both duration_days and start_time,
        end_time values are provided, start and end times will take precedence.

        Args:
            :duration_days (int): Duration between start and end points in 24h days
            :start_time (datetime | str | None):  midnight on provided custom date
            :end_time (datetime | str | None):  midnight on provided custom date

        Returns:
            start, end: points in time, TYPE:  datetime regardless of input format

        """
        try:
            if all(isinstance(x, datetime.datetime) for x in [start_time, end_time]):
                return start_time, end_time

            elif any(isinstance(x, str) for x in [start_time, end_time]) \
                and (re_dt.match(x) for x in [start_time, end_time]):
                start = self._convert_dt_string(start_time)
                end = self._convert_dt_string(end_time)

            elif any(x is None for x in [start_time, end_time]):
                start, end = self.default_endpoints()
        except Exception as e:
            fx = inspect.stack()[0][3]
            logger.exception(f'{fx}: Unknown exception while calc start & end duration: {e}')
            return self.start, self.end
        return  start, end

    def custom_duration(self, duration_days):
        """
        Returns start and end datetimes when given a custom duration in days
        """
        return self.default_endpoints(duration_days)

    def _convert_dt_string(self, dt_str):
        dt_format = '%Y-%m-%dT%H:%M:%S'
        return datetime.datetime.strptime(format_datetime(dt_str), dt_format)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "{}(start_dt={}, end_dt={})".format(self.__class__, self.start, self.end)
