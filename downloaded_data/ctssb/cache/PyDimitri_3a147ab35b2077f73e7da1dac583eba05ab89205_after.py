from PyDynamixel import Joint, DxlComm
from pysea import Spring, SEA
from math import pi

# Foot ids
LEFT_FOOT_ROLL, RIGHT_FOOT_ROLL, \
RIGHT_FOOT_PITCH, LEFT_FOOT_PITCH = 11,12,13,14

# Lower leg
LEFT_LOWER_LEG, RIGHT_LOWER_LEG = 15,16
LEFT_LOWER_SPRING, RIGHT_LOWER_SPRING = 101,102
LEFT_LOWER_LEG_SEA, RIGHT_LOWER_LEG_SEA = 111,112

# Upper leg
LEFT_UPPER_LEG, RIGHT_UPPER_LEG = 21,22
LEFT_UPPER_SPRING, RIGHT_UPPER_SPRING = 103,104
LEFT_UPPER_LEG_SEA, RIGHT_UPPER_LEG_SEA = 113,114

# Thigh
LEFT_LEG_ROLL, RIGHT_LEG_ROLL = 23,24
LEFT_LEG_PITCH, RIGHT_LEG_PITCH = 25,26
LEFT_LEG_YAW, RIGHT_LEG_YAW = 27,28

# Arms
LEFT_ARM_ROLL, RIGHT_ARM_ROLL = 31,32
LEFT_ARM_PITCH, RIGHT_ARM_PITCH = 33,34
LEFT_ARM_YAW, RIGHT_ARM_YAW = 35,36
LEFT_ELBOW, RIGHT_ELBOW = 41,42

# Waist
WAIST_ROLL, WAIST_PITCH, WAIST_YAW = 51,52,53

# Head
NECK_PITCH, NECK_YAW = 61,62

class Dimitri(object):

    trunk = None
    left_leg = None
    right_leg = None
    springs = None
    joints = [None] * 120

    def __init__(self):

        ''' This class implements the low level
        control for the joints of Dimitri robot.
        '''

        # Ports
        self.trunk = DxlComm('/dev/ttyS11', 8)
        self.left_leg = DxlComm('/dev/ttyS4', 8)
        self.right_leg = DxlComm('/dev/ttyS5', 8)
        self.springs = DxlComm('/dev/ttyS6', 8)

        # Feet
        self.joints[LEFT_FOOT_ROLL] = Joint(LEFT_FOOT_ROLL)
        self.joints[RIGHT_FOOT_ROLL] = Joint(RIGHT_FOOT_ROLL)
        self.joints[LEFT_FOOT_PITCH] = Joint(LEFT_FOOT_PITCH)
        self.joints[RIGHT_FOOT_PITCH] = Joint(RIGHT_FOOT_PITCH)

        # Lower leg
        self.joints[LEFT_LOWER_LEG] = Joint(LEFT_LOWER_LEG)
        self.joints[RIGHT_LOWER_LEG] = Joint(RIGHT_LOWER_LEG)
        self.joints[LEFT_LOWER_SPRING] = Spring(LEFT_LOWER_SPRING)
        self.joints[RIGHT_LOWER_SPRING] = Spring(RIGHT_LOWER_SPRING)
    	self.joints[LEFT_LOWER_LEG_SEA] = \
                SEA(self.joints[LEFT_LOWER_LEG], self.joints[LEFT_LOWER_SPRING])
        self.joints[RIGHT_LOWER_LEG_SEA] = \
                SEA(self.joints[RIGHT_LOWER_LEG], self.joints[RIGHT_LOWER_SPRING])

        # Upper leg
        self.joints[LEFT_UPPER_LEG] = Joint(LEFT_UPPER_LEG)
        self.joints[RIGHT_UPPER_LEG] = Joint(RIGHT_UPPER_LEG)
        self.joints[LEFT_UPPER_SPRING] = Spring(LEFT_UPPER_SPRING)
        self.joints[RIGHT_UPPER_SPRING] = Spring(RIGHT_UPPER_SPRING)
        self.joints[LEFT_UPPER_LEG_SEA] = \
                SEA(self.joints[LEFT_UPPER_LEG], self.joints[LEFT_UPPER_SPRING])
        self.joints[RIGHT_UPPER_LEG_SEA] = \
                SEA(self.joints[RIGHT_UPPER_LEG], self.joints[RIGHT_UPPER_SPRING])

        # Thigh
        self.joints[LEFT_LEG_ROLL] = Joint(LEFT_LEG_ROLL)
        self.joints[RIGHT_LEG_ROLL] = Joint(RIGHT_LEG_ROLL)
        self.joints[LEFT_LEG_PITCH] = Joint(LEFT_LEG_PITCH)
        self.joints[RIGHT_LEG_PITCH] = Joint(RIGHT_LEG_PITCH)
        self.joints[LEFT_LEG_YAW] = Joint(LEFT_LEG_YAW)
        self.joints[RIGHT_LEG_YAW] = Joint(RIGHT_LEG_YAW)

        # Arms
        self.joints[LEFT_ARM_ROLL] = Joint(LEFT_ARM_ROLL)
        self.joints[RIGHT_ARM_ROLL] = Joint(RIGHT_ARM_ROLL)
        self.joints[LEFT_ARM_PITCH] = Joint(LEFT_ARM_PITCH)
        self.joints[RIGHT_ARM_PITCH] = Joint(RIGHT_ARM_PITCH)
        self.joints[LEFT_ARM_YAW] = Joint(LEFT_ARM_YAW)
        self.joints[RIGHT_ARM_YAW] = Joint(RIGHT_ARM_YAW)
        self.joints[LEFT_ELBOW] = Joint(LEFT_ELBOW)
        self.joints[RIGHT_ELBOW] = Joint(RIGHT_ELBOW)

        # Waist
        self.joints[WAIST_ROLL] = Joint(WAIST_ROLL)
        self.joints[WAIST_PITCH] = Joint(WAIST_PITCH)
        self.joints[WAIST_YAW] = Joint(WAIST_YAW)

        # Head
        self.joints[NECK_PITCH] = Joint(NECK_PITCH)
        self.joints[NECK_YAW] = Joint(NECK_YAW)

    def sendGoalAngles(self):

        ''' Send the goal angles for all
        servo motors.
        '''
        self.trunk.sendGoalAngles()
        self.left_leg.sendGoalAngles()
        self.right_leg.sendGoalAngles()

    def receiveAngles(self):

        ''' Send the goal angles for all
        servo motors.
        '''
        self.trunk.receiveAngles()
        self.left_leg.receiveAngles()
        self.right_leg.receiveAngles()
        self.spring.receiveAngles()

    def updateSEAs(self):

        ''' Read the spring angles and compute
        the control value for the SEAs.
        '''

        # Read all the springs
        self.springs.receiveAngles()

        # Compute the PID control signal
        self.left_lower_leg_sea.update()
        self.right_lower_leg_sea.update()
        self.left_upper_leg_sea.update()
        self.right_upper_leg_sea.update()

    def update(self):

        ''' Update all robot joint commands
        '''

        self.updateSEAs()
        self.sendGoalAngles()

    def setPose(pose):

        ''' Set a pose to the robot
        '''
        for index in pose.keys():
            self.joints[index].setGoalAngle(pose[index])

    def enableTorques(self):

        ''' Enable torque in all joints
        '''
        self.trunk.enableTorques()
        self.left_leg.enableTorques()
        self.right_leg.enableTorques()

    def disableTorques(self):

        ''' Enable torque in all joints
        '''
        self.trunk.disableTorques()
        self.left_leg.disableTorques()
        self.right_leg.disableTorques()

