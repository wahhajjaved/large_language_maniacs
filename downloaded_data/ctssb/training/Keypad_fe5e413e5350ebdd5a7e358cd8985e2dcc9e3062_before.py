""" module for LED-board """
from time import sleep, time
import RPi.GPIO as gpio

"""
To declare a pin to input: GPIO.setup(pin, GPIO.IN)
To declare a pin to output: GPIO.setup(pin, GPIO.OUT)

To set the voltage of an output pin to high: GPIO.output(outpin, GPIO.HIGH)
To set the voltage of an output pin to low: GPIO.output(outpin, GPIO.LOW)
"""


class LedBoard:
    """ class for LED-board """

    def __init__(self):
        """ initialize LedBoard

            pin_led_states has the key which is the
            number of the LED,
            and value is an array of values for input
            and output pins. -1 is input pin, while 0
            and 1 is output (respectively low and high)
        """

        self.pins = [16, 12, 21]

        self.pin_led_states = [
            [1, 0, -1],
            [0, 1, -1],
            [-1, 0, 1],
            [-1, 1, 0],
            [1, -1, 0],
            [0, -1, 1]
        ]
        self.setup()

    def setup(self):
        """ set the proper mode """
        gpio.setmode(gpio.BCM)

    def set_pin(self, pin_index, pin_state):
        """ set two pins to output and one to input
            to light the correct led """
        # print("i:", pin_index, "s:", pin_state)
        if pin_state == -1:
            gpio.setup(self.pins[pin_index], gpio.IN)
        else:
            gpio.setup(self.pins[pin_index], gpio.OUT)
            gpio.output(self.pins[pin_index], pin_state)

    def set_high(self, led_number):
        """ lights the given led """
        for pin_index, pin_state in enumerate(self.pin_led_states[led_number]):
            self.set_pin(pin_index, pin_state)

    def light_led(self, led_number, sec):
        """ turn on one LED by calling set_high,
            wait 'sec' seconds and turn it off """
        # print("    nr:", led_number, "s:", sec)
        self.set_high(led_number)
        sleep(sec)
        self.turn_off_led()

    def turn_off_leds(self):
        """ turn off all leds manually, by setting
            the pin to -1 (input) """
        self.set_pin(0, -1)
        self.set_pin(1, -1)
        self.set_pin(2, -1)

    def flash_all_leds(self, sec):
        """ flash all LEDs on and off for
            'sec' seconds when password is wrong """
        stop_time = time() + sec
        while time() < stop_time:
            for key in range(len(self.pin_led_states)):
                self.set_high(key)
                sleep(0.01)
            self.turn_off_leds()
            sleep(0.06)
        self.turn_off_leds()

    def twinkle_all_leds(self, sec):
        """ turn all LEDs on and off in sequence
            for 'sec' seconds when password is verified """
        for key in range(len(self.pin_led_states)):
            # print("        key:", key)
            self.light_led(key, sec / 6)
        self.turn_off_leds()

    def power_up(self):
        """ light show on power up """
        stop_time = time() + 2  # 2 = sec
        while time() < stop_time:
            for k in range(4, 6):
                self.set_high(k)
                sleep(0.01)
        self.turn_off_leds()

    def power_down(self):
        """ light show on power down """
        stop_time = time() + 2  # 2 = sec
        while time() < stop_time:
            for k in range(0, 2):
                self.set_high(k)
                sleep(0.01)
        self.turn_off_leds()

    def verify_new_password(self):
        """ light green to verify that a new
            password has been made """
        stop_time = time() + 2  # 2 = sec
        while time() < stop_time:
            for k in range(4, 6):
                self.set_high(k)
                sleep(0.1)
            self.turn_off_leds()
            sleep(0.2)

    def wrong_new_password(self):
        """ light green to verify that a new
            password has been made """
        stop_time = time() + 2  # 2 = sec
        while time() < stop_time:
            for k in range(0, 2):
                self.set_high(k)
                sleep(0.1)
            self.turn_off_leds()
            sleep(0.2)

gpio.cleanup()
