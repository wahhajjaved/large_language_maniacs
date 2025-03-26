
from weather import *
from time import sleep
import RPi.GPIO as GPIO
from math import *

# GPIO pins for servo
SERVOPINLEFT = 11
SERVOPINRIGHT = 13
SERVOPINLIFT = 15

# Lift commands
UP = 0
DOWN = 1
WIPE = 2

# Positions for various leves of lifting
LEVELWRITE = 1000
LEVELUP = 2000
LEVELWIPE = 1500

# determines speed of the servo, higher is slower
LIFTSPEED = 1500

# Set pin numbering mode
GPIO.setmode(GPIO.BOARD)

# Set servo pins as output
GPIO.setup(SERVOPINLEFT,GPIO.OUT)
GPIO.setup(SERVOPINRIGHT,GPIO.OUT)
GPIO.setup(SERVOPINLIFT,GPIO.OUT)

# Set up the pins for PWM at 50 HZ (meaning 20 ms periods)
leftServo = GPIO.PWM(SERVOPINLEFT, 50)
rightServo = GPIO.PWM(SERVOPINRIGHT, 50)
liftServo = GPIO.PWM(SERVOPINLIFT, 50)

# keeps track of location of pen
# currentX = TODO
# currentY = TODO

# Keeps track of the lift position of the pen
servoHeight = 500

def wipe():
	"""gets the eraser and then clears the board"""

	lift(WIPE)
	TODO

# given a number as a string (or a decimal point)
def drawNum(num):
	"""Given a digit or . as a string, writes the digit by lifting up the pen,
	going to the appropriate location, putting the pen down, and then writing"""

	if num == '0':
		lift(UP)
	elif num == '1':
		lift(UP)
	elif num == '2':
		lift(UP)
	elif num == '3':
		lift(UP)
	elif num == '4':
		lift(UP)
	elif num == '5':
		lift(UP)
	elif num == '6':
		lift(UP)
	elif num == '7':
		lift(UP)
	elif num == '8':
		lift(UP)
	elif num == '9':
		lift(UP)
	elif num == '.':
		lift(UP)

def getDigits(temp):
	"""Given the temp as a float, returns an array of the characters
	representing the digits (and the decimal point"""

	return list(str(temp))

def lift(level):
	"""Given the level UP, DOWN, or WIPE, raises or lowers the pen
	to the appropriate point based on the current lift position stored
	in servoHeight"""
	global servoHeight
	global UP
	global LIFTSPEED
	global LEVELUP
	global LEVELWRITE
	global LEVELWIPE
	global liftServo
	liftServo.start(servoHeight/200)
	if level == UP:
		if servoHeight >= LEVELUP:
			while servoHeight >= LEVELUP:
				servoHeight -= 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

		else:
			while servoHeight <= LEVELUP: 
				servoHeight += 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

	elif level == DOWN:
		if servoHeight >= LEVELWRITE:
			while servoHeight >= LEVELWRITE:
				servoHeight -= 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

		else:
			while servoHeight <= LEVELWRITE:
				servoHeight += 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

	elif level == WIPE:
		if servoHeight >= WIPE:
			while servoHeight >= LEVELWIPE:
				servoHeight -= 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

		else:
			while servoHeight <= LEVELWIPE:
				servoHeight += 1
				writeMicroseconds(liftServo, servoHeight)
				delayMicroseconds(LIFTSPEED)

	liftServo.stop()
def setDestination(x, y):
	"""Given a destination x,y, calls goToXY in a loop so that a straight
	is drawn between currentX, currentY and the destination"""

	dx = x - currentX
	dy = y - currentY

	# use distance formula
	distance = sqrt(dx*dx + dy*dy)
	# steps = TODO * distance #how many steps per unit?

	# break the 
	for i in range(0,steps):
		goToXY(currentX+dx/steps,currentY+dy/steps)
		currentX += dx/steps
		currentY += dy/steps


def goToXY(x, y):
	"""Given an x,y points, determines the current number of microseconds to
	write to the left servo and the right servo"""

	# TODO
	#How to physics?

def writeMicroseconds(servo, microseconds):
	"""Calculates duty cycle based on desired pulse width"""
	servo.ChangeDutyCycle(microseconds/200)

def delayMicroseconds(microseconds):
	"""Coverts microsecond delay to seconds delay"""
	sleep(microseconds/1000000)

# while (1):
# 	weatherGetter = Weather()
# 	temp = weatherGetter.getWeather()
# 	digits = getDigist(temp)
# 	print(digits)
# 	for i in range(1,len(digits)):
# 		drawNum(digits[i])
# 	break;

for i in range(0,10):
	lift(UP)
	lift(WIPE)
	lift(DOWN)