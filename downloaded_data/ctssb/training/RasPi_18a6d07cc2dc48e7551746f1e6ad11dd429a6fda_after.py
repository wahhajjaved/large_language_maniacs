#!/usr/bin/python

#
# test script for ...
# playing around with motion detection (PIR and the camera)
#

import sys
import os
import time
import threading
# from datetime import datetime
import datetime
# from signal import pause

# import core classes for Raspberry Pi
from gpiozero import MotionSensor, LED
from picamera import PiCamera


# add classes directory of current project to the search path in order
# to find custom classes used in this script
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + '/classes')

# import custom classes
import debuguh

# create objects from gpiozero classes
used_sensor_01 = MotionSensor(4)  # PIR connected to pin x
sensor_01_aktiv = True
led_01 = LED(16)  # LED connected to pin x

# create objects from other tool classes
camera = PiCamera()


def current_time(val_a, val_b):
    local_time = time.localtime()
    jahr, monat, tag = local_time[0:3]
    stunde, minute, sekunde = local_time[3:6]
    system_time = str(stunde).zfill(2) + ":" + str(minute).zfill(2) + ":" + str(sekunde).zfill(2)
    system_date = str(tag).zfill(2) + "." + str(monat).zfill(2) + "." + str(jahr)
    determined_time = ""

    if val_a == "time" and val_b == "date":
        determined_time = system_time + " " + system_date
    elif val_a == "date" and val_b == "time":
        determined_time = system_date + " " + system_time
    elif val_a == "time" and val_b == "":
        determined_time = system_time
    elif val_a == "date" and val_b == "":
        determined_time = system_date
    else:
        determined_time = local_time

    return determined_time


def capture():
    time_stamp = datetime.datetime.now().isoformat()
    camera.capture('/home/pi/%s.jpg' % time_stamp)


def sensoren_abfrage():
    global used_sensor_01, sensor_01_aktiv, led_01, camera

    print("Thread zur Sensorenabfrage gestartet.")

    while sensor_01_aktiv:
        used_sensor_01.wait_for_motion()
        led_01.on()
        capture()
        print("Motion detected at " + current_time("time", "date"))
        time.sleep(1)
        led_01.off()

# a few debug tests first
#  script global setting of debugging and create the object to the debug class
debug = 1
duh = debuguh.debuguh_out()  # create the object

# show some debugging info depending on the value of the parameter
duh.show_info(debug)

#
#
# now "the real thing" (TM)
#
#

# Abfrage des PIR Sensors in eigenem Thread starten
sensorenAbfrageThread = threading.Thread(target=sensoren_abfrage)
sensorenAbfrageThread.start()
# time.sleep(5)  # damit alle Sensorwerte zum Start eingelesen sind

# Hauptroutine
# TODO: Hauptroutine edited by UH finishes after z loops
z = 0

while z < 5:
    displayTime = current_time("time", "date")  # bei Abfrage "date","time" ändert die Reihenfolge der Ausgabe
    print(displayTime)

    time.sleep(5)
    z = z + 1
