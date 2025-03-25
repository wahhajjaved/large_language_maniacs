import os
import sys

from datetime import datetime as dt
from datetime import timedelta as tdelta

from panoptes.utils import config, database

from ..utils import has_logger

@has_logger
class WeatherStation(object):
    """P
    This object is used to determine the weather safe/unsafe condition.
    """

    def __init__(self, *args, **kwargs):
        '''
        '''
        self._is_safe = False
        self.sensors = None
        self._translator = {True: 'safe', False: 'unsafe'}

    def is_safe(self):
        """ Determines whether current conditions are safe or not

        Args:
            stale(int): If reading is older than `stale` seconds, return False. Default 180 (seconds).

        Returns:
            bool:       Conditions are safe (True) or unsafe (False)
        """
        return self._is_safe

    def check_conditions(self, stale=180):
        """ Determines whether current conditions are safe or not

        Args:
            stale(int): If reading is older than `stale` seconds, return False. Default 180 (seconds).

        Note:
            `stale` not implemented in the base class.

        Returns:
            str:       String describing state::

                { True: 'safe', False: 'unsafe' }

        """

        return self._translator.get(self.is_safe(), 'unsafe')


class WeatherStationMongo(WeatherStation):
    """
    This object is used to determine the weather safe/unsafe condition.

    Queries a mongodb collection for most recent values.
    """

    def __init__(self, *args, **kwargs):
        ''' Initialize the weather station with a mongodb connection. '''
        super().__init__(*args, **kwargs)

        self.sensors = database.PanMongo().sensors

    def is_safe(self, stale=180):
        ''' Determines whether current conditions are safe or not

        Args:
            stale(int): If reading is older than `stale` seconds, return False. Default 180 (seconds).

        Returns:
            bool:       Conditions are safe (True) or unsafe (False)
        '''
        assert self._sensors is not None, self.logger.warning("No connection to sensors.")
        is_safe = super().__init__()

        now = dt.utcnow()
        try:
            is_safe = self.sensors.find_one({'type': 'weather', 'status': 'current'})['data']['Safe']
            timestamp = self.sensors.find_one({'type': 'weather', 'status': 'current'})['date']
            age = (now - timestamp).total_seconds()
        except:
            self.logger.warning("Weather not safe or no record found in Mongo DB")
            is_safe = False
        else:
            if age > stale:
                is_safe = False

        self._is_safe = is_safe
        return self._is_safe

class WeatherStationSimulator(WeatherStation):
    """
    This object simulates safe/unsafe conditions.

    Args:
        simulator(path):    Set this to a file path to manually control safe/unsafe conditions.
            If the file exists, the weather is unsafe.  If the file does not exist, then conditions
            are safe.

    Returns:

    """

    def __init__(self, *args, **kwargs):
        ''' Simulator initializer  '''
        super().__init__(*args, **kwargs)

        if kwargs.get('simulator', None) is not None:
            if os.path.exists(simulator):
                self._is_safe = False
            else:
                self._is_safe = True


    def set_safe(self):
        """ Sets the simulator to safe weather """
        self._is_safe = True

    def set_unsafe(self):
        """ Sets the simulator to unsafe weather """
        self._is_safe = False

    def is_safe(self, stale=180):
        ''' Simulator simply returns the `self._is_safe` param '''
        return self._is_safe


if __name__ == '__main__':
    weather = WeatherStationMongo()
    safe = weather.check_conditions()
    translator = {True: 'safe', False: 'unsafe'}
    print('Conditions are {}'.format(translator[safe]))
