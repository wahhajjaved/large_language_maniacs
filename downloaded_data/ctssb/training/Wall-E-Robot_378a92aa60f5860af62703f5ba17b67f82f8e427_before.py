import os
import logging
if(os.name == "posix"):
    #if("raspberrypi" in str(os.system("uname -a"))):
    import RPi.GPIO as GPIO
    #else:
    #    print("Running on Linux System that is not RaspberryPI, things will probably break quickly.")
else:
    print("Running on Windows System not (a) RaspberryPI, things will probably break quickly.")

class WallEHardware:
    def __init__(self):
        #TODO load these from config
        #Load everything from config
        self.logger = logging.getLogger("WallE.hardware")
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(7,GPIO.OUT)
        self.states = ["dummy"] * 24
        GPIO.output(7,False)
        self.states[7] = False

    def go(self):
        if(self.states[7] == True):
            GPIO.output(7,False)
            self.states[7] == False
        if(self.states[7] == False):
            GPIO.output(7,True)
            self.states[7] == False
