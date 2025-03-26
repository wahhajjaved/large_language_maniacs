#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import os
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
LOOP_DELAY = 0.001

# do not send warning message for the timespan after the door is opened
DOOR_OPEN_TIMEOUT = 20

# PID file path
PID_FILE_PATH = '/tmp/cavedu_house.pid'

# global variables
PREV_DOOR_OPEN = False
PREV_DOOR_CLOSED = True
PREV_VALUE_EMERGENCY = False
PREV_VALUE_TRAIN_FACE = False
PREV_VALUE_RECOGNIZE_FACE = False
PREV_STATE_1 = None
PREV_STATE_2 = None

LAST_SIGNALED_EMERGENCY_TIME = 0
FLAG_EMERGENCY_TRIGGERED = False

LAST_OPENING_TIME = 0
LAST_CLOSING_TIME = 0

FLAG_DOOR_OPENING_TRIGGERED = False
FLAG_DOOR_CLOSING_TRIGGERED = False

STATE_CHANGE_TIME = 0

STATE = constants.STATE_CLOSED

RFID_SERVICE = None
FACE_AUTH_SERVICE = None
GUI_SERVICE = None

# utility functions
def run_in_background(func):
    thread = threading.Thread(target=func)
    thread.start()

def is_door_open():
    return GPIO.input(config.PIN_IN_MAGNET_SWITCH) == 0

def is_door_opening():
    global PREV_DOOR_OPEN
    global LAST_OPENING_TIME
    global FLAG_DOOR_OPENING_TRIGGERED

    value = is_door_open()
    up_edge = (PREV_DOOR_OPEN ^ value) & value
    PREV_DOOR_OPEN = value

    if up_edge:
        FLAG_DOOR_OPENING_TRIGGERED = False
        LAST_OPENING_TIME = time.time()

    result = False
    if value and not FLAG_DOOR_OPENING_TRIGGERED and time.time() - LAST_OPENING_TIME >= 0.02:
        FLAG_DOOR_OPENING_TRIGGERED = True
        result = True

    return result

def is_door_closing():
    global PREV_DOOR_CLOSED
    global LAST_CLOSING_TIME
    global FLAG_DOOR_CLOSING_TRIGGERED

    value = not is_door_open()
    down_edge = (PREV_DOOR_CLOSED ^ value) & value
    PREV_DOOR_CLOSED = value

    if down_edge:
        LAST_CLOSING_TIME = time.time()
        FLAG_DOOR_CLOSING_TRIGGERED = False

    result = False
    if value and not FLAG_DOOR_CLOSING_TRIGGERED and time.time() - LAST_CLOSING_TIME >= 0.02:
        FLAG_DOOR_CLOSING_TRIGGERED = True
        result = True

    return result

def is_authenticated():
    return RFID_SERVICE.is_tag_detected() or FACE_AUTH_SERVICE.is_auth_granted()

def is_signaled_emergency():
    global PREV_VALUE_EMERGENCY
    global LAST_SIGNALED_EMERGENCY_TIME
    global FLAG_EMERGENCY_TRIGGERED

    value = GPIO.input(config.PIN_IN_EMERGENCY) == 1
    is_up_edge = (PREV_VALUE_EMERGENCY ^ value) & value
    PREV_VALUE_EMERGENCY = value

    if is_up_edge:
        LAST_SIGNALED_EMERGENCY_TIME = time.time()
        FLAG_EMERGENCY_TRIGGERED = False

    result = False
    if value and not FLAG_EMERGENCY_TRIGGERED and time.time() - LAST_SIGNALED_EMERGENCY_TIME >= 0.5:
        result = True
        FLAG_EMERGENCY_TRIGGERED = True

    return result

def is_signaled_train_face():
    return GUI_SERVICE.is_signaled_train_face()

def is_signaled_recognize_face():
    return GUI_SERVICE.is_signaled_recognize_face()

def is_signaled_clear_faces():
    return GUI_SERVICE.is_signaled_clear_faces()

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
    GPIO.output(config.PIN_OUT_LOCK, 0)

def action_close_door():
    GPIO.output(config.PIN_OUT_LOCK, 1)

def action_signal_housebreak():
    GPIO.output(config.PIN_OUT_INVADED, 1)

def action_signal_door_not_closed():
    logging.debug('signal door not closed')
    GPIO.output(config.PIN_OUT_TIMEOUT, 1)

def action_check_door_open_overtime(expected_state_change_time):
    def routine():
        time.sleep(DOOR_OPEN_TIMEOUT)
        if is_door_open() and STATE_CHANGE_TIME == expected_state_change_time:
            action_signal_door_not_closed()
    run_in_background(routine)

def actoin_set_light(light_on):
    GPIO.output(config.PIN_OUT_LIGHT, 0 if light_on else 1)

def action_train_face():
    FACE_AUTH_SERVICE.signal_train_face()

def action_recognize_face():
    FACE_AUTH_SERVICE.signal_recognize_face()

def action_clear_faces():
    FACE_AUTH_SERVICE.signal_clear_faces()

# event handlers
def on_auth():
    logging.debug('event auth')
    global STATE

    if STATE == constants.STATE_OPEN:     # ignore this case
        action_open_door()

    elif STATE in (constants.STATE_CLOSED, constants.STATE_INVADED, constants.STATE_EMERGENCY): # reset to door open state
        GPIO.output(config.PIN_OUT_INVADED, 0)
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
        action_open_door()
        mediatek_cloud.set_house_status('EMERGENCY')
        STATE = constants.STATE_EMERGENCY

def on_door_opening():
    logging.debug('event door_opening')

    if STATE == constants.STATE_CLOSED:
        on_housebreaking()

def on_door_closing():
    global STATE
    logging.debug('event door_closing')

    GPIO.output(config.PIN_OUT_TIMEOUT, 0)
    action_close_door()

    if STATE == constants.STATE_CLOSED:
        logging.warning('event door_closing is triggered in CLOSED state')

    elif STATE == constants.STATE_OPEN:
        mediatek_cloud.set_house_status('DOOR CLOSED')
        STATE = constants.STATE_CLOSED

def on_state_changed():
    global STATE
    global STATE_CHANGE_TIME
    logging.debug('event state_change')

    STATE_CHANGE_TIME += 1
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

            try:
                os.remove(PID_FILE_PATH)
            except OSError:
                pass

            logging.info('Shutting down...')
            exit()

        # check events
        actoin_set_light(FACE_AUTH_SERVICE.flag_require_light_on)

        if is_signaled_emergency():
            on_emergency()

        if is_signaled_train_face():
            action_train_face()

        if is_signaled_clear_faces():
            action_clear_faces()

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
    # try to kill any other instances
    if os.path.exists(PID_FILE_PATH):
        with open(PID_FILE_PATH) as file_pid:
            pid = int(file_pid.read())

        try:
            os.kill(pid, signal.SIGINT)

            os.kill(pid, 0)
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)

            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)

        except OSError:
            pass

    # create PID file
    with open(PID_FILE_PATH, 'w') as file_pid:
        file_pid.write(str(os.getpid()))

    # setup logger and signal handlers
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    signal.signal(signal.SIGINT, signal_handler)

    # setup GPI Opins
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(config.PIN_OUT_INVADED, GPIO.OUT)
    GPIO.setup(config.PIN_OUT_TIMEOUT, GPIO.OUT)
    GPIO.setup(config.PIN_OUT_LOCK, GPIO.OUT)
    GPIO.setup(config.PIN_OUT_LIGHT, GPIO.OUT)
    GPIO.setup(config.PIN_IN_EMERGENCY, GPIO.IN)
    GPIO.setup(config.PIN_IN_MAGNET_SWITCH, GPIO.IN)

    GPIO.output(config.PIN_OUT_INVADED, 0)
    GPIO.output(config.PIN_OUT_TIMEOUT, 0)
    GPIO.output(config.PIN_OUT_LOCK, 1)
    GPIO.output(config.PIN_OUT_LIGHT, 1)

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
