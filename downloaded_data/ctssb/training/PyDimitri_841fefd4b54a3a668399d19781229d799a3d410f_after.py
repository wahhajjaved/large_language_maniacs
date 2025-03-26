from PyDynamixel import *

class Spring(Joint):
    ''' This class derives from Joint to
    implement a Spring feedback board. It
    works exactly like joint, except that
    we can't set torques or goal angles.
    We can only read its current angle.'''

    def __init__(self, spring_id, centerValue = 0):
        ''' The constructor takes the board id
        as the argument. Argument centerValue
        can be set to calibrate the zero
        position of the spring (relaxed pos).
        '''

        super(Spring, self).__init__(spring_id, centerValue)

    def setMaxTorque(self, maxTorque):

        ''' Not implemented in this class!
        '''
        pass

    def sendMaxTorque(self, maxTorque = None):

        ''' Not implemented in this class!
        '''
        pass

    def setGoalAngle(self, angle):

        ''' Not implemented in this class!
        '''
        pass

    def sendGoalAngle(self, goalAngle = None):

        ''' Not implemented in this class!
        '''
        pass

    def enableTorque(self):
    
        ''' Not implemented in this class!
        '''
        pass

    def disableTorque(self):
    
        ''' Not implemented in this class!
        '''
        pass

    def receiveAngle(self):

        ''' Reads the current position of this
        servomotor alone. The read position is
        stored and can be accessed via method
        getAngle()
        '''

        self.currValue = dxl.read_word(self.socket, self.servo_id, \
                GOALPOS_ADDR) - self.centerValue
        self.currAngle = pi*float(self.currValue)/4096.0
        return self.currAngle    

class SEA(object):

    ''' This class implements the Series Elastic
    Actuator. It basically combines a Joint and
    a Spring.
    '''

    spring = None # This will store the spring
    joint = None # This will store the servo

    # PID controller gains
    kp = 1.0
    ki = 0.001
    kd = 0.0

    # PID controller variables
    error_before = 0.0
    error_sum = 0.0
    
    # Goal angle of the SEA
    goalAngle = 0.0

    def __init__(self, joint, spring, \
            kp=1.0, ki=0.001, kd=0.0):

        ''' The constructor receives as argument
        the objects joint and spring. Optionally
        the PID gains can also be passed.
        '''

        self.spring = spring
        self.joint = joint
        self.kp = kp
        self.ki = ki
        self.kd = kd

    def update(self):

        ''' This method updates the goalValue of
        the joint servo according to the spring
        displacement
        '''

        # Calculate the actual position, which is
        # the servo position minus the spring
        # position
        # (here we use joint.goalAngle instead
        #  of joint.currAngle to avoid having
        #  to read the actual position of the
        #  servomotor. We assume the servo has
        #  moved to the desired position
        #  immediatelly!)
        angle = self.joint.goalAngle - self.spring.currAngle

        # Calculate the error
        error = self.goalAngle - angle

        # Calculate the accumulated error
        # (integral)
        self.error_sum = self.error_sum + error

        # Calculate the difference between the
        # current error and the error before
        # (derivative)
        error_deriv = error - self.error_before

        # Saves the error for later calculating
        # the diffrerence again
        self.error_before = error

        # Gets the PID control calculated
        p = self.kp*error
        i = self.ki*self.error_sum
        d = self.kd*error_deriv

        # Defines the control signal
        c = p + i + d

        # Transforms into value and
        # sets to the servo goalValue
        self.joint.goalAngle = self.goalAngle + c

    def setGoalAngle(self, goalAngle):

        ''' Sets the goal angle of the SEA
        which is the same as the goal angle
        of the servo (goal value will change)
        '''
        self.goalAngle = goalAngle

