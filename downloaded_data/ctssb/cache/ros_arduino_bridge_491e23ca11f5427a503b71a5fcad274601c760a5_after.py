#!/usr/bin/env python

"""
  gripper_controller - action based controller for grippers.
  Copyright (c) 2011-2014 Vanadium Labs LLC.  All right reserved.
  
  Modified by: Nathaniel Gallinger, www.updroid.com

  Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that the following conditions are met:
      * Redistributions of source code must retain the above copyright
        notice, this list of conditions and the following disclaimer.
      * Redistributions in binary form must reproduce the above copyright
        notice, this list of conditions and the following disclaimer in the
        documentation and/or other materials provided with the distribution.
      * Neither the name of Vanadium Labs LLC nor the names of its 
        contributors may be used to endorse or promote products derived 
        from this software without specific prior written permission.
  
  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
  ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
  DISCLAIMED. IN NO EVENT SHALL VANADIUM LABS BE LIABLE FOR ANY DIRECT, INDIRECT,
  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
  OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
  OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
  ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import rospy, actionlib
import thread

from math import radians
from control_msgs.msg import GripperCommandAction
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64


class ParallelGripperModel:
    """ One servo to open/close parallel jaws, typically via linkage. """

    def __init__(self):
        self.gripper_width_m = rospy.get_param('~gripper_width_m', 0.036)
        self.gripper_width_deg = rospy.get_param('~gripper_width_deg', 135.0)
        self.joint_name = rospy.get_param('~joint_name', 'gripper_joint')

        # publishers
        self.pub = rospy.Publisher(self.joint_name+'/command', Float64, queue_size=5)

    def scaleInput(self, input):
        in_closed = self.gripper_width_m/2
        in_open = 0
        out_closed = -radians(self.gripper_width_deg)/2
        out_open = radians(self.gripper_width_deg)/2
        return ((input - in_closed) * (out_open - out_closed) / (in_open - in_closed) + out_closed)

    def setCommand(self, command):
        self.pub.publish(self.scaleInput(command.position))

    def getPosition(self, joint_states):
        return 0.0

    def getEffort(self, joint_states):
        return 1.0


class GripperActionController:
    """ The actual action callbacks. """
    def __init__(self):
        joint_name = rospy.get_param('~joint_name', 'gripper_joint')
        rospy.init_node(joint_name)

        # setup model
        try:
            model = rospy.get_param('~model')
        except:
            rospy.logerr('no model specified, exiting')
            exit()

        if model == 'parallel':
            self.model = ParallelGripperModel()
        else:
            rospy.logerr('unknown model specified, exiting')
            exit()

        # subscribe to joint_states
        rospy.Subscriber('joint_states', JointState, self.stateCb)

        # subscribe to command and then spin
        self.server = actionlib.SimpleActionServer('~gripper_action', GripperCommandAction, execute_cb=self.actionCb, auto_start=False)
        self.server.start()
        rospy.spin()

    def actionCb(self, goal):
        """ Take an input command of width to open gripper. """
        rospy.loginfo('Gripper controller action goal recieved:%f' % goal.command.position)
        # send command to gripper
        self.model.setCommand(goal.command)
        # publish feedback
        while True:
            if self.server.is_preempt_requested():
                self.server.set_preemtped()
                rospy.loginfo('Gripper Controller: Preempted.')
                return
            # TODO: get joint position, break when we have reached goal
            break
        self.server.set_succeeded()
        rospy.loginfo('Gripper Controller: Succeeded.')

    def stateCb(self, msg):
        self.state = msg

if __name__=='__main__':
    try:
        GripperActionController()
    except rospy.ROSInterruptException:
        rospy.loginfo('Hasta la Vista...')

