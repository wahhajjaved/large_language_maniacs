from gopigo import *
# ###########################################################################################
# Project for an autonomous robot
# ###########################################################################################

import random
import math
import sys
import time

#argument variables (pass in as args to callibrate)
# -- --------------------------
arg_stop_dist = 30              # cm robot stops
arg_rot_fwd = 20                # number of encoder going fwd (roughly 1 per cm)
arg_rot_side = 6                # number of encoder to make a 90 turn
arg_rot_bck = 14                # number of encoder to make a 180 turn
arg_robot_speed = 150           # Speed
arg_decisions = 10              # Number of times we loop through the program before breaking
# -- ---------------------------

#Fixed variables
# -- ---------------------------
full_scan = 180                 # Full Degree range with servo
deg_scan = 160                  # Degree to finish from (due to mounting)
middle_scan = 80                # Degree looking forward (90 is not straight - using 70)
start_scan=0                  # Degree to start from (due to mounting)
increm = 10                     # Degrees to increment via servo
tracker=0                       # Keeps track of number of times we have looped
situation = {}                  # keep track of all the distances
turn_track = 0                  # how many times have we turned & not gone forward
# -- ---------------------------

def servo_int():
    #Run through scan and capture distances
    for servo_pos in xrange(start_scan,deg_scan+10,increm):
        servo(servo_pos)
        time.sleep(.01)
        dist=us_dist(15)			#Find the distance of the object in front
        situation[servo_pos] = dist

def full_straight():
    # Scan forward direction
    fwd_scan = []
    
    # Take middle angle +/- 30 degrees
    for ang in range(middle_scan-30, middle_scan+40, 10):
        fwd_scan.append(situation[ang])
    
    if (min(fwd_scan) < arg_stop_dist):
        return True
    else:
        return False

def full_turn(side):
    side1 = []
    # Test to see if a side angle is the right way to go 
    if (side=="left"):
        for ang in range(deg_scan, deg_scan-30, -10):
            side1.append(situation[ang])
    elif (side=="right"):
        for ang in range(start_scan,start_scan+30, 10):
            side1.append(situation[ang])
     
    print(side + " " + str(min(side1))) 
    if ( min(side1) > arg_stop_dist):
        return True
    else:
        return False
     
def decision():
    
    # Step 1 - Should we go straight?
    if full_straight(): #move forward?
        print("moving forward " + str(situation[middle_scan]) + "cm")
        move_forward()
    # Step 2 - Try Left?
    elif full_turn("left"): #move left?
        print("moving left " + str(situation[deg_scan-increm]) + "cm")
        turn_left()
    # Step 3 - Try Right?
    elif full_turn("right"): #move right?
        print("moving right " + str(situation[start_scan])+"cm")
        turn_right()
    # Step 4 - Turn Around
    else:
        print("turning around")
        turn_around()

def move_forward():
    #GoPiGo moves forward a short distance
    fwd_rot = situation[middle_scan] - arg_stop_dist 
    if (fwd_rot < arg_rot_fwd):
        enc_tgt(1,1,fwd_rot)
    else:
        enc_tgt(1,1,arg_rot_fwd)
    fwd()
    
def turn_around():
    #Turn Around
    enc_tgt(1,1,arg_rot_bck)
    left_rot()
    
def turn_left():
    #Turn Left
    enc_tgt(1,1,arg_rot_side)
    left_rot()
    
def turn_right():
    #Turn Right
    enc_tgt(1,1,arg_rot_side)
    right_rot()

### PASS IN ARGUMENTS ###
#0 - STOP DISTANCE
#1 - FORWARD (ROTATIONS)
#2 - SIDE (ROTATIONS)
#3 - BACK (ROTATIONS)
#4 - SET SPEED
#5 - NUMBER OF DECISION ITERATIONS

args = sys.argv[1:] #Get Arguments
if len(args) == 6:  #Use defaults if arguments don't match
    #Take Arguments
    arg_stop_dist = int(args[0])
    arg_rot_fwd = int(args[1])
    arg_rot_side = int(args[2])
    arg_rot_bck = int(args[3])
    arg_robot_speed = int(args[4])
    arg_decisions = int(args[5])

print "Press ENTER to begin"
raw_input()				#Wait for input to start
set_speed(arg_robot_speed)
enable_servo()

while True:
    servo_int()
    decision()
    time.sleep(1)
    stop()
    tracker = tracker + 1
    if tracker > arg_decisions:
        break
    
disable_servo()
