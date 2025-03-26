#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import time
import logging
import signal
import threading

import RPi.GPIO as GPIO

import config
import constants
import rfid
import gui
import face_auth
import mediatek_cloud

# the delay time (ms) after each loop
LOOP_DELAY = 0.05

# the timespan that the GPIO pin is set to 1
OUTPUT_PIN_TIMESPAN = 0.03

# do not send warning message for the timespan after the door is opened
DOOR_OPEN_TIMESPAN = 5

# global variables
PREV_DOOR_OPEN = False
PREV_DOOR_CLOSED = True
PREV_VALUE_EMERGENCY = False
PREV_VALUE_TRAIN_FACE = False
PREV_VALUE_RECOGNIZE_FACE = False
PREV_STATE_1 = None
PREV_STATE_2 = None

STATE_CHANGE_TIME = 0

STATE = constants.STATE_CLOSED

RFID_SERVICE = None
FACE_AUTH_SERVICE = None
GUI_SERVICE = None

# utility functions
def run_in_background(func):
    thread = threading.Thread(target=func)
    thread.start()
    # asyncio.get_event_loop().run_in_executor(None, func)

def is_door_open():
    return GPIO.input(config.PIN_IN_MAGNET_SWITCH) == 0

def is_door_opening():
    global PREV_DOOR_OPEN
    value = is_door_open()
    result = (PREV_DOOR_OPEN ^ value) & value
    PREV_DOOR_OPEN = value
    return result

def is_door_closing():
    global PREV_DOOR_CLOSED
    value = not is_door_open()
    result = (PREV_DOOR_CLOSED ^ value) & value
    PREV_DOOR_CLOSED = value
    return result

def is_authenticated():
    return rfid.read_tag() is not None or FACE_AUTH_SERVICE.is_auth_granted()

def is_signaled_emergency():
    global PREV_VALUE_EMERGENCY
    value = GPIO.input(config.PIN_IN_EMERGENCY) == 1
    result = (PREV_VALUE_EMERGENCY ^ value) & value
    PREV_VALUE_EMERGENCY = value
    return result

def is_signaled_train_face():
    return GUI_SERVICE.is_signaled_train_face()

def is_signaled_recognize_face():
    return GUI_SERVICE.is_signaled_recognize_face()

def is_state_changed():
    global PREV_STATE_1
    result = PREV_STATE_1 != STATE
    PREV_STATE_1 = STATE
    return result

def is_state_unchanged():
    global PREV_STATE_2
    result = PREV_STATE_2 == STATE
    PREV_STATE_2 = STATE
    return result

def action_open_door():
    def routine():
        GPIO.output(config.PIN_OUT_LOCK, 1)
        time.sleep(0.5)
        GPIO.output(config.PIN_OUT_LOCK, 0)
    run_in_background(routine)

def action_signal_housebreak():
    def routine():
        GPIO.output(config.PIN_OUT_INVADED, 1)
        time.sleep(0.5)
        GPIO.output(config.PIN_OUT_INVADED, 0)
    run_in_background(routine)

def action_signal_door_not_closed():
    def routine():
        GPIO.output(config.PIN_OUT_TIMEOUT, 1)
        time.sleep(0.5)
        GPIO.output(config.PIN_OUT_TIMEOUT, 0)
    run_in_background(routine)

def action_check_door_open_overtime(expected_state_change_time):
    def routine():
        time.sleep(DOOR_OPEN_TIMESPAN)
        if is_door_open() and STATE_CHANGE_TIME == expected_state_change_time:
            action_signal_door_not_closed()
    run_in_background(routine)

def action_train_face():
    FACE_AUTH_SERVICE.signal_train_face()

def action_recognize_face():
    FACE_AUTH_SERVICE.signal_recognize_face()

# event handlers
def on_auth():
    logging.debug('event auth')
    global STATE

    if STATE == constants.STATE_OPEN:     # ignore this case
        return

    elif STATE in (constants.STATE_CLOSED, constants.STATE_INVADED, constants.STATE_EMERGENCY): # reset to door open state
        action_open_door()
        mediatek_cloud.set_house_status('DOOR OPEN')
        STATE = constants.STATE_OPEN

def on_housebreaking():
    global STATE
    if STATE != constants.STATE_INVADED:
        logging.debug('event housebreaking')
        STATE = constants.STATE_INVADED
        mediatek_cloud.set_house_status('INVADED')
        action_signal_housebreak()

def on_emergency():
    global STATE
    if STATE != constants.STATE_EMERGENCY:
        logging.debug('event emergency')
        mediatek_cloud.set_house_status('EMERGENCY')
        STATE = constants.STATE_EMERGENCY

def on_door_opening():
    logging.debug('event door_opening')

    if STATE == constants.STATE_CLOSED:
        on_housebreaking()

def on_door_closing():
    global STATE
    logging.debug('event door_closing')

    if STATE == constants.STATE_CLOSED:
        logging.warning('event door_closing is triggered in CLOSED state')

    elif STATE == constants.STATE_OPEN:
        mediatek_cloud.set_house_status('DOOR CLOSED')
        STATE = constants.STATE_CLOSED

def on_state_changed():
    global STATE
    global STATE_CHANGE_TIME

    STATE_CHANGE_TIME = time.time()
    GUI_SERVICE.set_house_state(STATE)

    if STATE == constants.STATE_OPEN:
        action_check_door_open_overtime(STATE_CHANGE_TIME)

def on_state_unchanged():
    pass

def main():
    global STATE
    global PREV_STATE_1
    global PREV_STATE_2
    global PREV_DOOR_OPEN
    global PREV_DOOR_CLOSED

    # initialize
    if is_door_open():
        STATE = PREV_STATE_1 = PREV_STATE_2 = constants.STATE_OPEN
        PREV_DOOR_OPEN = True
        PREV_DOOR_CLOSED = False

    else:
        STATE = PREV_STATE_1 = PREV_STATE_2 = constants.STATE_CLOSED
        PREV_DOOR_OPEN = False
        PREV_DOOR_CLOSED = True

    # monitor the events by polling
    while True:
        if constants.SHUTDOWN_FLAG:
            RFID_SERVICE.stop()
            GUI_SERVICE.stop()
            FACE_AUTH_SERVICE.stop()
            logging.info('Shutting down...')
            exit()

        # check events
        if is_signaled_emergency():
            on_emergency()

        if is_signaled_train_face():
            action_train_face()

        if is_signaled_recognize_face():
            action_recognize_face()

        if is_authenticated():
            on_auth()

        if is_door_opening():
            on_door_opening()

        if is_door_closing():
            on_door_closing()


        if is_state_changed():
            on_state_changed()

        else:
            on_state_unchanged()

        time.sleep(LOOP_DELAY)

def signal_handler(signum, frame):
    constants.SHUTDOWN_FLAG = True

if __name__ == '__main__':
    # setup logger and signal handlers
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    signal.signal(signal.SIGINT, signal_handler)

    # setup GPI Opins
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(config.PIN_OUT_INVADED, GPIO.OUT)
    GPIO.setup(config.PIN_OUT_TIMEOUT, GPIO.OUT)
    GPIO.setup(config.PIN_OUT_LOCK, GPIO.OUT)
    GPIO.setup(config.PIN_IN_EMERGENCY, GPIO.IN)
    GPIO.setup(config.PIN_IN_MAGNET_SWITCH, GPIO.IN)

    GPIO.output(config.PIN_OUT_INVADED, 0)
    GPIO.output(config.PIN_OUT_TIMEOUT, 0)

    # setup RFID service
    RFID_SERVICE = rfid.RfidService()
    RFID_SERVICE.start()

    # setup gui service
    GUI_SERVICE = gui.GuiServie()
    GUI_SERVICE.start()

    # setup face authentication service
    FACE_AUTH_SERVICE = face_auth.FaceAuthServie(config.FACES_DATABASE_PATH, GUI_SERVICE)
    FACE_AUTH_SERVICE.start()

    # run the main procedure
    logging.info('Access control system started')
    main()
