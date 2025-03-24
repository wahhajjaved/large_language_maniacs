from PyDynamixel import Joint, DxlComm
from pysea import Spring, SEA
from math import pi
from motion import Motion

# Foot ids
RIGHT_FOOT_ROLL, LEFT_FOOT_ROLL, \
RIGHT_FOOT_PITCH, LEFT_FOOT_PITCH = 11,12,13,14

# Lower leg
RIGHT_LOWER_LEG, LEFT_LOWER_LEG = 15,16
#RIGHT_LOWER_SPRING, LEFT_LOWER_SPRING = 101,102
#RIGHT_LOWER_LEG_SEA, LEFT_LOWER_LEG_SEA = 111,112

# Upper leg
RIGHT_UPPER_LEG, LEFT_UPPER_LEG = 21,22
#LEFT_UPPER_SPRING, RIGHT_UPPER_SPRING = 103,104
#LEFT_UPPER_LEG_SEA, RIGHT_UPPER_LEG_SEA = 113,114

# Thigh
RIGHT_LEG_ROLL, LEFT_LEG_ROLL = 23,24
RIGHT_LEG_PITCH, LEFT_LEG_PITCH = 25,26
RIGHT_LEG_YAW, LEFT_LEG_YAW = 27,28

# Arms
RIGHT_ARM_ROLL, LEFT_ARM_ROLL = 31,32
RIGHT_ARM_PITCH, LEFT_ARM_PITCH = 33,34
RIGHT_ARM_YAW, LEFT_ARM_YAW = 35,36
RIGHT_ELBOW, LEFT_ELBOW = 41,42

# Waist
WAIST_ROLL, WAIST_PITCH, WAIST_YAW = 51,52,53

# Head
NECK_PITCH, NECK_YAW = 61,62

class Dimitri(object):

    trunk = None
    left_leg = None
    right_leg = None
    springs = None
    joints = [None] * 200

    def __init__(self):

        ''' This class implements the low level
        control for the joints of Dimitri robot.
        '''

        # Ports
	self.port = DxlComm('/dev/ttyUSB0', 8)
        # self.trunk = DxlComm('/dev/ttyS11', 8)
        # self.left_leg = DxlComm('/dev/ttyS4', 8)
        # self.right_leg = DxlComm('/dev/ttyS5', 8)
        # self.springs = DxlComm('/dev/ttyS6', 8)

        # Feet
        self.joints[RIGHT_FOOT_ROLL] = Joint(RIGHT_FOOT_ROLL, 4096)
        self.joints[LEFT_FOOT_ROLL] = Joint(LEFT_FOOT_ROLL, 6125)
        self.joints[RIGHT_FOOT_PITCH] = Joint(RIGHT_FOOT_PITCH, 4500)
        self.joints[LEFT_FOOT_PITCH] = Joint(LEFT_FOOT_PITCH, 6030)

        # Lower leg
        self.joints[RIGHT_LOWER_LEG] = Joint(RIGHT_LOWER_LEG, 6627)
        self.joints[LEFT_LOWER_LEG] = Joint(LEFT_LOWER_LEG, 5255)
        #self.joints[RIGHT_LOWER_SPRING] = Spring(RIGHT_LOWER_SPRING)
        #self.joints[LEFT_LOWER_SPRING] = Spring(LEFT_LOWER_SPRING)
        #self.joints[RIGHT_LOWER_LEG_SEA] = \
        #        SEA(self.joints[RIGHT_LOWER_LEG], self.joints[RIGHT_LOWER_SPRING])
    	#self.joints[LEFT_LOWER_LEG_SEA] = \
        #        SEA(self.joints[LEFT_LOWER_LEG], self.joints[LEFT_LOWER_SPRING])

        # Upper leg
        self.joints[RIGHT_UPPER_LEG] = Joint(RIGHT_UPPER_LEG, 5005)
        self.joints[LEFT_UPPER_LEG] = Joint(LEFT_UPPER_LEG, 7682)
        #self.joints[RIGHT_UPPER_SPRING] = Spring(RIGHT_UPPER_SPRING)
        #self.joints[LEFT_UPPER_SPRING] = Spring(LEFT_UPPER_SPRING)
        #self.joints[RIGHT_UPPER_LEG_SEA] = \
        #        SEA(self.joints[RIGHT_UPPER_LEG], self.joints[RIGHT_UPPER_SPRING])
        #self.joints[LEFT_UPPER_LEG_SEA] = \
        #        SEA(self.joints[LEFT_UPPER_LEG], self.joints[LEFT_UPPER_SPRING])

        # Thigh
        self.joints[RIGHT_LEG_ROLL] = Joint(RIGHT_LEG_ROLL, 4629)
        self.joints[LEFT_LEG_ROLL] = Joint(LEFT_LEG_ROLL, 6150)
        self.joints[RIGHT_LEG_PITCH] = Joint(RIGHT_LEG_PITCH, 6370)
        self.joints[LEFT_LEG_PITCH] = Joint(LEFT_LEG_PITCH, 6390)
        self.joints[RIGHT_LEG_YAW] = Joint(RIGHT_LEG_YAW, 8044)
        self.joints[LEFT_LEG_YAW] = Joint(LEFT_LEG_YAW, 4220)

        # Arms
        self.joints[RIGHT_ARM_ROLL] = Joint(RIGHT_ARM_ROLL, 4587)
        self.joints[LEFT_ARM_ROLL] = Joint(LEFT_ARM_ROLL, 5930)
        self.joints[RIGHT_ARM_PITCH] = Joint(RIGHT_ARM_PITCH, 7192)
        self.joints[LEFT_ARM_PITCH] = Joint(LEFT_ARM_PITCH, 6890)
        self.joints[RIGHT_ARM_YAW] = Joint(RIGHT_ARM_YAW, 5136)
        self.joints[LEFT_ARM_YAW] = Joint(LEFT_ARM_YAW, 6620)
        self.joints[RIGHT_ELBOW] = Joint(RIGHT_ELBOW, 4547)
        self.joints[LEFT_ELBOW] = Joint(LEFT_ELBOW, 7790)

        # Waist
        self.joints[WAIST_ROLL] = Joint(WAIST_ROLL, 8055)
        self.joints[WAIST_PITCH] = Joint(WAIST_PITCH, 7513)
        self.joints[WAIST_YAW] = Joint(WAIST_YAW, 4584)

        # Head
        self.joints[NECK_PITCH] = Joint(NECK_PITCH, 7174)
        self.joints[NECK_YAW] = Joint(NECK_YAW, 7777)

	# Add the all joints to the port
	for joint in self.joints:
		if joint:
			self.port.attachJoint(joint)

    def sendGoalAngles(self):

        ''' Send the goal angles for all
        servo motors.
        '''
        #self.trunk.sendGoalAngles()
        #self.left_leg.sendGoalAngles()
        #self.right_leg.sendGoalAngles()
        self.port.sendGoalAngles()

    def receiveCurrAngles(self):

        ''' Receive the goal angles for all
        servo motors.
        '''
        #self.trunk.receiveCurrAngles()
        #self.left_leg.receiveCurrAngles()
        #self.right_leg.receiveCurrAngles()
        #self.spring.receiveCurrAngles()
        self.port.receiveCurrAngles()

    def updateSEAs(self):

        ''' Read the spring angles and compute
        the control value for the SEAs.
        '''
	pass

        # Read all the springs
        # self.springs.receiveAngles()

        # Compute the PID control signal
        # self.left_lower_leg_sea.update()
        # self.right_lower_leg_sea.update()
        # self.left_upper_leg_sea.update()
        # self.right_upper_leg_sea.update()

    def update(self):

        ''' Update all robot joint commands
        '''

        #self.updateSEAs()
        self.sendGoalAngles()

    def setPose(self,pose):

        ''' Set a pose to the robot
        '''
        for index in pose.keys():
            if index != 0:
                self.joints[index].setGoalAngle(pose[index])

    def getPose(self):

        ''' Get the current pose
        of the robot
        '''
        self.receiveCurrAngles()
        pose = {}
        for joint in self.joints:
            if joint:
            	pose[joint] = joint.getAngle()
        return pose

    def enableTorques(self):

        ''' Enable torque in all joints
        '''
        #self.trunk.enableTorques()
        #self.left_leg.enableTorques()
        #self.right_leg.enableTorques()
        self.port.enableTorques()

    def disableTorques(self):

        ''' Disable torque in all joints
        '''
        #self.trunk.disableTorques()
        #self.left_leg.disableTorques()
        #self.right_leg.disableTorques()
        self.port.disableTorques()

    def playMotion(self, motion):
        currPose = self.getPose()
        currPose[0] = 1.0
        motion.keyframes.insert(0,currPose)
        motion.generate()
        for frame in motion.allframes:
            self.setPose(frame)
            sleep(frame[0])

    def playMotionFile(self, filename):
        motion = Motion()
        motion.read(filename)
        self.playMotion(motion)

