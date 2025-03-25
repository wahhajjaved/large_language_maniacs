""" module for LED-board """
from time import sleep
import RPi.GPIO as gpio
# from gpiozero import LED

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

        self.pins = [16, 20, 21]

        self.pin_led_states = [
            [1, 0, -1],
            [0, 1, -1],
            [1, -1, 0],
            [0, -1, 1],
            [-1, 1, 0],
            [-1, 0, 1]
        ]
        # run self.setup() here?

    def setup(self):
        """ set the proper mode """
        gpio.setmode(gpio.BCM)

    def set_pin(self, pin_index, pin_state):
        """ set two pins to output and one to input
            to light the correct led """
        print("i:", pin_index, "s:", pin_state)
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
        print("    nr:", led_number, "s:", sec)
        self.set_high(led_number)
        sleep(sec)
        # self.turn_off_led(led_number)

    def turn_off_led(self, led_number):
        self.set_pin(led_number, 0)

    def flash_all_leds(self, sec):
        """ flash all LEDs on and off for
            'sec' seconds when password is wrong """
        # time_flashed is the duration the LEDs have flashed
        time_flashed = 0
        # last_state remembers the last state of the LED (1 = high, 0 = low)
        last_state = 0

        while time_flashed < sec:
            for key in range(len(self.pin_led_states) - 1):
                if last_state == 0:
                    self.set_pin(key, 1)
                else:
                    self.set_pin(key, 0)

            if key == 5:
                last_state = (last_state + 1) % 2

            sleep(0.2)
            time_flashed += 0.2

    def twinkle_all_leds(self, sec):
        """ turn all LEDs on and off in sequence
            for 'sec' seconds when password is verified """
        for key in range(len(self.pin_led_states) - 1):
            print("        key:", key)
            self.light_led(key, sec / 6)

    def power_up(self):
        """ light show on power up """
        gpio.output(self.pins[1], gpio.HIGH)
        gpio.output(self.pins[3], gpio.HIGH)
        gpio.output(self.pins[5], gpio.HIGH)
        sleep(0.5)

        gpio.output(self.pins[1], gpio.LOW)
        gpio.output(self.pins[3], gpio.LOW)
        gpio.output(self.pins[5], gpio.LOW)
        gpio.output(self.pins[2], gpio.HIGH)
        gpio.output(self.pins[4], gpio.HIGH)
        gpio.output(self.pins[6], gpio.HIGH)
        sleep(0.5)

        gpio.output(self.pins[2], gpio.LOW)
        gpio.output(self.pins[4], gpio.LOW)
        gpio.output(self.pins[6], gpio.LOW)

        gpio.output(self.pins[1], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[1], gpio.LOW)
        gpio.output(self.pins[2], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[2], gpio.LOW)
        gpio.output(self.pins[3], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[3], gpio.LOW)
        gpio.output(self.pins[4], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[4], gpio.LOW)
        gpio.output(self.pins[5], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[5], gpio.LOW)
        gpio.output(self.pins[6], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[6], gpio.LOW)

    def power_down(self):
        """ light show on power down """
        gpio.output(self.pins[2], gpio.HIGH)
        gpio.output(self.pins[4], gpio.HIGH)
        gpio.output(self.pins[6], gpio.HIGH)
        sleep(0.5)

        gpio.output(self.pins[2], gpio.LOW)
        gpio.output(self.pins[4], gpio.LOW)
        gpio.output(self.pins[6], gpio.LOW)
        gpio.output(self.pins[1], gpio.HIGH)
        gpio.output(self.pins[3], gpio.HIGH)
        gpio.output(self.pins[5], gpio.HIGH)
        sleep(0.5)

        gpio.output(self.pins[1], gpio.LOW)
        gpio.output(self.pins[3], gpio.LOW)
        gpio.output(self.pins[5], gpio.LOW)

        gpio.output(self.pins[6], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[6], gpio.LOW)
        gpio.output(self.pins[5], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[5], gpio.LOW)
        gpio.output(self.pins[4], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[4], gpio.LOW)
        gpio.output(self.pins[3], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[3], gpio.LOW)
        gpio.output(self.pins[2], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[2], gpio.LOW)
        gpio.output(self.pins[1], gpio.HIGH)
        sleep(0.1)

        gpio.output(self.pins[1], gpio.LOW)

    def verify_new_password(self):
        """ light green to verify that a new
            password has been made """

    def wrong_new_password(self):
        """ light green to verify that a new
            password has been made """


LB = LedBoard()
LB.setup()


def test_leds():
    LB.light_led(0, 2)
#    LB.light_led(1, 0.5)
#    LB.light_led(2, 0.5)
#    LB.light_led(3, 0.5)
#    LB.light_led(4, 0.5)
#    LB.light_led(5, 0.5)


def test_twinkle():
    LB.twinkle_all_leds(6)


def test_flash():
    LB.flash_all_leds(6)


test_leds()

gpio.cleanup()
