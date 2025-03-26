import sys
#sys.path.append("/home/pi/Github/Adafruit_Python_PCA9685")
import Adafruit_PCA9685
from time import sleep

class MotorController:

    armed = False
    frequency = 50

    def __init__(self, ):
        self.pwm = Adafruit_PCA9685.PCA9685()
        self.pwm.set_pwm_freq(self.frequency)
        self.pulse_per_bit = self.get_ppb(self.frequency)

    def get_ppb(self, freq):
        self.pwm.set_pwm_freq(freq)
        pulse_length = 1000000  # 1,000,000 us per second
        pulse_length //= freq
        print('{0}us per period'.format(pulse_length))
        pulse_length //= 4096  # 12 bits of resolution
        print('{0}us per bit'.format(pulse_length))
        return pulse_length

    def get_bit(self, microsecond):
        bit = int(round(microsecond / self.pulse_per_bit))
        print("MS: " + str(microsecond) + " => bit:" + str(bit))
        return bit

    def set_microseconds(self, channel, microsecond):
        self.pwm.set_pwm(channel, 0, self.get_bit(microsecond))

    def set_all_microseconds(self, microsecond):
        for i in range(0, 6):
            self.pwm.set_pwm(i, 0, self.get_bit(microsecond))

    def arm(self):
        print("Arm")
        self.set_all_microseconds(1500)
        self.armed = True

    def disarm(self):
        print("Disarm")
        self.set_all_microseconds(0)
        self.armed = False

    def write(self, axis, ms0, ms1):
        print("Write")
        if self.armed:
            self.set_microseconds(2 * axis, ms0)
            self.set_microseconds(2 * axis + 1, ms1)