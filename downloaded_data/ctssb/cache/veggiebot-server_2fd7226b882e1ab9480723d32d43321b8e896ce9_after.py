from lib.devices import Pin, MoistureSensor
from lib.settings import Settings
from lib.utils import get_kpa, get_volts, get_resistance
import datetime
import os
import random
from time import sleep
import thread
import pytz


def speak(message):

    gender = random.choice(['m','f',])
    variant = random.choice(range(1,7))

    voice = "-ven-us+%s%s" % (gender, variant)

    cmd = "espeak '%s' -s 160 %s" % (message, voice)
    os.system(cmd)


moisture_sensor = MoistureSensor()


def read_values():

    """ Read the moisture level """

    celsius = moisture_sensor.get_temperature()

    fahrenheit = (celsius * 9.0 / 5.0) + 32.0

    moisture_ohms = moisture_sensor.get_moisture()

    moisture_kiloohms = moisture_ohms / 1000.0

    kpa = get_kpa(moisture_kiloohms, celsius)

    """ Field capacity is about -30 kPa, except
        in the case of sandy soils, which is -10 kPa """

    available_water = -30 - -1500

    remaining_available = ((available_water - (kpa * -1)) / available_water) * 100

    return {
        'moistureLevel': remaining_available,
        'moistureReading': 0,
        'moistureVolts': 0,
        'moistureOhms': moisture_ohms,
        'moistureKOhms': moisture_kiloohms,
        'temperature': fahrenheit,
        'moistureKPa': kpa,
    }


def save_data():

    payload = read_values()

    moisture_sensor.save_data(payload)


def trigger_pump(settings):

    status_change = settings.changed.get('pumpStatus', None)

    if status_change == 'on':
        pin = Pin(17)
        print "Turning pump on ..."
        pin.off() #On opens the circuit
        return

    if status_change == 'off':
        pin = Pin(17)
        print "Turning pump off ..."
        pin.on() #Off completes the circuit
        return

    if settings.pumpStatus == 'auto':

        pin = Pin(17)

        values = read_values()

        if values['moistureLevel'] < settings.autoThreshold - 50:
            pin.off()

        elif values['moistureLevel'] > settings.autoThreshold + 50:
            pin.on()


settings = Settings()

while True:

    sleep(1)

    try:
        settings.refresh()
    except:
        print "Couldn't refresh settings."

    trigger_pump(settings)

    since_last_saved = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC) - moisture_sensor.last_saved

    minutes_since_last_saved = float(since_last_saved.seconds / 60.0)

    if minutes_since_last_saved >= settings.dataInterval:
        save_data()
