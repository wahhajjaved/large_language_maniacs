import ephem
import pytz
import copy
from datetime import datetime, timedelta
import numpy as np

import timezone


def is_dst(zonename):
    tz = pytz.timezone(zonename)
    now = pytz.utc.localize(datetime.utcnow())
    return now.astimezone(tz).dst() != timedelta(0)

# set up relevant time zones
utc = pytz.timezone('UTC')
chile = pytz.timezone('America/Santiago')
pacific = pytz.timezone('US/Pacific')
eastern = pytz.timezone('US/Eastern')

favorite_zones = [chile, eastern, pacific]
favorite_labels = ['Chile', 'EDT', 'PDT'] if is_dst('US/Eastern') else ['Chile', 'EST', 'PST']

#set up for ephem calcs:
def _gemini():
    gemini = ephem.Observer()
    gemini.lat='-30:14:26.7'
    gemini.lon='-70:44:12.006'
    gemini.elevation=2722
    gemini.temp=0
    gemini.pressure=726
    gemini.horizon = '-1:45'  # earth's horizon is below local horizontal if you're on a mountain.
    return gemini

gemsouth = _gemini()
gemsouth_twi = _gemini()
gemsouth_twi.horizon='-12'

def delta_to_now(sometime):
    deltat = (sometime - ephem.now()) # in days
    delta_hour = int(np.floor(deltat*24))
    delta_min = int(np.round((deltat-delta_hour/24)*24*60))
    return delta_hour,delta_min


def format_time(dt, tz):
    tmp = dt.astimezone(tz).strftime('%I:%M %p')
    return tmp[1:] if tmp[0]=='0' else tmp # drop leading zeros

def utc_to_multizone(date_utc):
    if date_utc.tzinfo is None: # assume input is UTC if given a naiive datetime
        date_utc = utc.localize(date_utc)
    times = [format_time(date_utc,tz)+" "+label for tz, label in zip(favorite_zones, favorite_labels)]
    return ", ".join(times)


def sunrise_time_response():
    gemsouth.date = ephem.now()
    gemsouth_twi.date = ephem.now()

    risetime = gemsouth.next_rising(ephem.Sun())
    twitime = gemsouth_twi.next_rising(ephem.Sun(), use_center=True)
    return ("Next sunrise at Gemini South is {}, which is {} h {} m from now.".format(utc_to_multizone(risetime.datetime()), *delta_to_now(risetime)) +
            "\nAnd 12 deg twilight is at {}".format(utc_to_multizone(twitime.datetime()) ) )



def sunset_time_response():
    gemsouth.date = ephem.now()
    gemsouth_twi.date = ephem.now()
    settime = gemsouth.next_setting(ephem.Sun())

    twitime = gemsouth_twi.next_setting(ephem.Sun(), use_center=True)
    return ("Next sunset at Gemini South is {}, which is {} h {} m from now.".format(utc_to_multizone(settime.datetime()), *delta_to_now(settime)) +
            "\nAnd 12 deg twilight is at {}".format(utc_to_multizone(twitime.datetime()) ) )


moon_phases = [ ":new_moon:", ":waxing_crescent_moon:", ":first_quarter_moon:", ":waxing_gibbous_moon:", ":full_moon:", ":waning_gibbous_moon:", ":last_quarter_moon:", ":waning_crescent_moon:"]
moon_observer = _gemini()
    
def get_current_moon_phase():
    """
    Get the current moon phase
    """
    # get the dates of the last and next new moon
    moon_observer.date = datetime.now()
    phase_end = ephem.next_new_moon(moon_observer.date)
    phase_start = ephem.previous_new_moon(moon_observer.date)

    
    # based on that figure out what part of the phase we are in. Phase goes from [0,1)
    phase = (moon_observer.date - phase_start) / (phase_end - phase_start)
    # 8 moon phases, so do this for easy indexing
    phase *= 8 
    # round to the nearest phase and wrap aroudn for the 7.5-7.9 range mapping to 0
    phase = round(phase) % 8
    
    return "The current moon phase is {0}".format(moon_phases[int(phase)])
     
    
