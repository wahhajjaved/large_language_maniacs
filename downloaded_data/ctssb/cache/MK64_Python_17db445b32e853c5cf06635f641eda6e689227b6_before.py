""" Reads the controller input and forward it """
from evdev import InputDevice, categorize, ecodes, KeyEvent
from n64_keymap import N64_KEYS
import asyncio, evdev
from message import createMessage
from serial_controller import send_data
from enum import Enum

class Commands(Enum):
    LEFT = 0
    RIGHT = 1
    STRAIGHT = 2
    ACCELERATE = 3
    THROTTLE = 4
    START = 5
    USE = 6

# TODO: Async Input from diffrent controller

player_devices = []

def init_input_device(port):
    return evdev.InputDevice(port)

async def read_input_events(player):
    async for event in player.device.async_read_loop():  
        if event.type == ecodes.EV_KEY:
            tmp_command = 10
            keyvalue = event.code
            if(keyvalue == N64_KEYS.A.value):
               tmp_command = Commands.ACCELERATE
            elif(keyvalue == N64_KEYS.B.value):
                tmp_command = Commands.THROTTLE
            elif(keyvalue == N64_KEYS.START.value):
                tmp_command = Commands.START
            elif(keyvalue == N64_KEYS.Z.value):
                tmp_command = Commands.USE
            if tmp_command <10:
                send_data(createMessage(tmp_command.value, 0))
        elif event.type == ecodes.EV_ABS:
            if event.code != ecodes.ABS_Z:
                tmp_command = 0
                value = event.value
                keyvalue = event.code
                if keyvalue == 0:
                    if value < 120:  
                        tmp_command = Commands.LEFT
                        send_data(createMessage(tmp_command.value, value))
                    if value > 130:
                        tmp_command = Commands.RIGHT
                        send_data(createMessage(tmp_command.value, value))
            
