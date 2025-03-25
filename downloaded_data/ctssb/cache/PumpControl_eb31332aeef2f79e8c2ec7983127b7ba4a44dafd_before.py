#!/usr/bin/env python

#simple program to move syringe pump a set distance when a button is pushed.
import sys
import os
import pygame
from pygame import locals
import time
import RPi.GPIO as gpio
import spidev
import threading
import datetime

config = {}
execfile(sys.path[0]+"/pumpSettings.py", config)

#set up gpio correctly
gpio.setwarnings(False)
gpio.setmode(gpio.BOARD)

#set gpio pin numbers
DIR_PINS = config["direction_pins"]
STEP_PINS = config["step_pins"]

#Standard increment for movement
STD_INC = config["steps"]

#wait time
WAIT = config["delay"]

#mode selection
MODE = config["mode"]

#number of pumps to control
NUM_PUMPS = config["pumps"]


#Function to read SPI data from MCP3008 chip
#channel must be int 0-7
def ReadChannel(channel):
	adc = spi.xfer2([1,(8+channel)<<4,0])
	data = ((adc[1]&3) << 8) + adc[2]
	return data


#pump class for pump control methods
class Pump:
	def __init__(self, steps, dir_pin, step_pin):
		self.steps = steps
		self.dir = dir_pin
		self.step = step_pin

		gpio.setup(self.step, gpio.OUT, initial = gpio.HIGH)
		gpio.setup(self.dir, gpio.OUT, initial = gpio.HIGH)

	#move the pump one standard increment.
	def move(self, direction, num):
		if direction > 0:
			gpio.output(self.dir,  gpio.HIGH) 
		elif direction < 0: 
			gpio.output(self.dir, gpio.LOW)
		
		else: 
			return
	
		try:
			print "moving pump ", num, datetime.datetime.now()
			for x in range(self.steps):
				gpio.output(self.step, gpio.HIGH)
				time.sleep(0.002)

				gpio.output(self.step, gpio.LOW)
				time.sleep(WAIT)
		except (KeyboardInterrupt):
			print "Move stopped by KeyboardInterrupt"
			return


#set up pump objects and gpio controls.
pump_objs = []
for x in range(NUM_PUMPS):
	pump = Pump(STD_INC, DIR_PINS[x], STEP_PINS[x])
	pump_objs.append(pump)


#no movement at 0, pull if < 0, push if > 0
pump_m = [0,0,0,0]
#analog channels
CHANNEL_NUM = config["channels"]

#matrices for storage of movement variables for simultaneous movement.
pump_steps = [0,0,0,0]
pump_waits = [0,0,0,0]

def micro_time():
	time = datetime.datetime.now()

	return (time.day * 24 * 60 * 60 + time.second) + (time.microsecond / 1000000.0)

def simultaneousMove(pump_waits, pump_steps, pump_m):
	#reset the wait time to a known value.
	WAIT = 0

	low_wait = pump_waits[0]

	for x in pump_waits:
		if x < low_wait and x > 0:
			low_wait = x
	
	#init my_threads storage, to keep track of timer threads outside loop.
	my_threads = [None, None, None, None]

	next_call = time.time()
	
	move_steps = []

	for x in range(NUM_PUMPS):
		move_steps.append(pump_steps[x])

	total_elapsed = 0
	#loop while there are steps to do
	while(any(x > 0 for x in pump_steps)):
		total_elapsed += low_wait
		next_call = next_call + low_wait
		time.sleep(next_call - time.time())
		#Timers, to handle waits simultaneously, correspond to pump numbers.
		#Timer threads will sleep for the time given to them as the first arg
		#then execute the function given as their second arg based on the third
		#arg as the args for the called function.
		#The corresponding pump_steps entry is then decremented to reflect change
		for y in range(NUM_PUMPS):
			
			#if pump_steps[y] > 0:
			#	if my_threads[y] == None or my_threads[y].is_alive() == False:
				#	next_calls[y] = next_calls[y] + pump_waits[y]
				#	my_threads[y] = threading.Timer(next_calls[y] - micro_time(), pump_objs[y].move, [pump_m[y], y])
				#	my_threads[y].daemon = True
				#	my_threads[y].start()
				#	move_steps[y] -= 1
			if(pump_steps[y] > 0 and pump_waits[y]%total_elapsed == 0):
				pump_objs[y].move(pump_m[y], y)
				pump_steps[y] -= 1



#instant input instant movement 
if (MODE == 0):
	#initialize pygame stuff
	#os.environ["SDL_VIDEODRIVER"] = "dummy"
	pygame.init()
	screen = pygame.display.set_mode((640, 480))
	pygame.display.flip()


	pygame.joystick.init() #pygame joystick device system (for usb gamepad)

	deadZone = 0.6 # make a wide deadzone

	try:
   		j = pygame.joystick.Joystick(0) # create a joystick instance
   		j.init() # init instance
   		print 'Enabled usb joystick: ' + j.get_name()
	except pygame.error:
   		print 'no usb joystick found.'


   	#SPI Joystick setup
	spi = spidev.SpiDev()
	spi.open(0,0)
	
	#infiniloop for input
	while(True):
		#cycle through the possible channels and set the movement integers based on the input from the channels
		for x in range(CHANNEL_NUM):
			joy_value = ReadChannel(x)
			
			print joy_value
			#joystick center is supposed to be 511.5
			if joy_value < 500:
				pump_m[x] = -1 
				print 

			elif joy_value > 530:
				pump_m[x] = 1

			else:
				pump_m[x] = 0

		for e in pygame.event.get(): #iterate over pygame event stack
			if e.type == pygame.KEYDOWN:
				if e.key == pygame.K_w: #forward motion on pump0
					pump_m[0] = 1
			 	elif e.key == pygame.K_s: #backward motion on pump0
					pump_m[0] = -1
				elif e.key == spygame.K_d: #forward motion on pump1
					pump_m[1] = 1
				elif e.key == pygame.K_a: #backward motion on pump1
					pump_m[1] = -1
				elif e.key == pygame.K_UP:
					pump_m[2] = 1
				elif e.key == pygame.K_DOWN:
					pump_m[2] = -1
				elif e.key == pygame.K_RIGHT:
					pump_m[3] = 1
				elif e.key == pygame.K_LEFT:
					pump_m[3] = -1
				elif e.key == pygame.K_ESCAPE:
					gpio.cleanup()
					sys.exit(1)

			elif e.type == pygame.KEYUP:
				if e.key in (pygame.K_w, pygame.K_s, pygame.K_d, pygame.K_a, pygame.K_UP, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_LEFT):
					#Stop pump0
					pump_m[0] = 0

			if e.type == pygame.locals.JOYAXISMOTION:	#read Analog stick motion
				x1, y1 = j.get_axis(0), j.get_axis(1) #Left Stick
				y2, x2 = j.get_axis(2), j.get_axis(3) #Right Stick (not in use)

				print x1
				print y1
				print x2
				print xy

				if x1 < -1 * deadZone:
					print "Left Joystick 1"

				if x1 > deadZone:
					print "Right Joystick 1"

				if y1 <= deadZone and y1 >= -1*deadZone:
					m1 = 0 #no motion

				if y1 < -1 *deadZone:
					print "Up Joystick 1"
					m1 = 1 #push forward

				if y1 > deadZone:
					print "Down Joystick 1"
					m1 = -1 #pull back
	
		
	
		#resolve movement
		for x in range(NUM_PUMPS):
			pump_objs[x].move(pump_m[x])


#single direction mode (keyboard entry)
elif(MODE == 1):
	while(True):
		#get the number of the pump the user wants to set the movement on.
		pump_num = raw_input("Pump to move: (type 'start' or 's' to move them and 'exit' or 'e' to exit): ")
		#if the user tells the program to start, run the simultaneous movement function
		if pump_num == "start" or pump_num == "s":
			simultaneousMove(pump_waits, pump_steps, pump_m)
			
			#reset values for next entries.
			for x in range(NUM_PUMPS):
				pump_m[x] = 0
				pump_waits[x] = 0
				pump_steps[x] = 0
			continue
		#if the user says to exit, do so
		if pump_num == "exit" or pump_num == "e":
			gpio.cleanup()
			sys.exit(0)
		
		#parse the entered pump number to an int
		try:
			pump_num = int(pump_num)
		except ValueError:
			print "Invalid pump number."
			continue

		#get the number of steps the user would like to make the pump do, parse them and then get the direction and absolute value
		num_steps = raw_input("Number of steps to move it in: ")
		
		try:	
			num_steps = int(num_steps)
		except ValueError:
			print "Invalid step number."
			continue

		if (num_steps < 0):
			direction = -1
		else:
			direction = 1
		num_steps = abs(num_steps)

		#get the time these should occur accross and parse it.
		time_in = raw_input("Time to do steps in (seconds): ")
		try:
			time_in = int(time_in)
		except ValueError:
			print "Invalid time."
			continue

		#set corresponding list entries for this pump to the correct variables for movement.
		if pump_num < NUM_PUMPS:
			pump_waits[pump_num] = (time_in/num_steps) - 0.002
			pump_steps[pump_num] = num_steps
			pump_m[pump_num] = direction			
		else:
			print "Invalid pump number"

#alternating direction mode (keyboard entry)
elif(mode == 2):
	while(True):
		#get the number of the pump the user wants to set the movement on.
		pump_num = raw_input("Pump to move: (exit' or 'e' to exit): ")
		if pump_num == "start" or pump_num == "s":
			#ask the user how many times they want to reverse the pumps
			reps_in = raw_input("How many times should the pump switch (each rep has both directions)?")
			try :
				reps_in = int(reps_in)
			except ValueError:
				print "Invalid number of repetitions."
				continue
			reps_in = abs(reps_in)

			#execute the moves.
			for x in range(reps_in):
				simultaneousMove(pump_waits, pump_steps, pump_m)

				for y in range(len(pump_m)):
					pump_m[y] = -1 * pump_m[y]

				simultaneousMove(pump_waits, pump_steps, pump_m)

				for y in range(len(pump_m)):
					pump_m[y] = -1 * pump_m[y]

			#reset values for next entries.
			for x in range(NUM_PUMPS):
				pump_m[x] = 0
				pump_waits[x] = 0
				pump_steps[x] = 0

			repetitions = 0
			continue
		if pump_num == "exit" or pump_num == "e":
			gpio.cleanup()
			sys.exit(0)
		
		#parse the entered pump number to an int
		try:
			pump_num = int(pump_num)
		except ValueError:
			print "Invalid pump number."
			continue

		#get the number of steps the user would like to make the pump do, parse them and then get the direction and absolute value
		num_steps = raw_input("Number of steps to move it in: ")
		
		try:	
			num_steps = int(num_steps)
		except ValueError:
			print "Invalid step number."
			continue

		if (num_steps < 0):
			direction = -1
		else:
			direction = 1
		num_steps = abs(num_steps)

		#get the time these should occur accross and parse it.
		time_in = raw_input("Time to do steps in (seconds): ")
		try:
			time_in = int(time_in)
		except ValueError:
			print "Invalid time."
			continue


		#set corresponding list entries for this pump to the correct variables for movement.
		if pump_num < NUM_PUMPS:
			pump_waits[pump_num] = (time_in/num_steps) - 0.002
			pump_steps[pump_num] = num_steps
			pump_m[pump_num] = direction
		else:
			print "Invalid pump number"