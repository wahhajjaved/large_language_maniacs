#!/usr/bin/env python

# Copyright (c) 2013 CNRS
# Author: Florent Lamiraux
#
# This file is part of hpp-ros.
# hpp-ros is free software: you can redistribute it
# and/or modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either version
# 3 of the License, or (at your option) any later version.
#
# hpp-ros is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Lesser Public License for more details.  You should have
# received a copy of the GNU Lesser General Public License along with
# hpp-ros.  If not, see
# <http://www.gnu.org/licenses/>.

from math import sqrt, atan2
import numpy as np
import rospy
import time
from sensor_msgs.msg import JointState
from geometry_msgs.msg import TransformStamped
from visualization_msgs.msg import Marker
from visualization_msgs.msg import MarkerArray
from geometry_msgs.msg import Point
from tf import TransformBroadcaster
from hpp import Quaternion

import hpp

class Obstacle (object):
    def __init__ (self, name, frameId):
        self.name = name
        self.frameId = frameId
        self.position = (0,0,0,1,0,0,0)

class Transform (object):
    def __init__ (self, quat, trans):
        self.quat = quat
        self.trans = trans

    def __mul__ (self, other):
        if not isinstance (other, Transform):
            raise TypeError ("expecting Transform type object")
        trans = self.trans + (self.quat * Quaternion (0, other.trans) *
                              self.quat.conjugate ()).array [1:]
        quat = self.quat * other.quat
        return Transform (quat, trans)
    def __str__ (self):
        return \
            """
Transform
  Quaternion:  %s
  Translation: %s """%(self.quat, self.trans)


I4 = np.matrix ([[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
def getRootJointPosition (robot):
    pos = robot.getRootJointPosition ()
    return Transform (Quaternion (pos [3:7]), np.array (pos [0:3]))

def computeRobotPositionAnchor (self, config):
    pos = self.rootJointPosition
    self.transform.transform.rotation = (pos.quat.array [1],
                                          pos.quat.array [2],
                                          pos.quat.array [3],
                                          pos.quat.array [0])
    self.transform.transform.translation = (pos.trans [0],
                                             pos.trans [1],
                                             pos.trans [2])
    self.js.position = []
    for (rank, convert) in self.jointConversion:
        self.js.position.append (convert (config [rank:]))

def computeRobotPositionFreeflyer (self, config):
    ff_rot = config [self.cfgBegin+3:self.cfgBegin+7]
    ff_pos = config [self.cfgBegin+0:self.cfgBegin+3]
    jointMotion = Transform (Quaternion (ff_rot), ff_pos)
    pos = self.rootJointPosition * jointMotion
    self.transform.transform.rotation = (pos.quat.array [1],
                                          pos.quat.array [2],
                                          pos.quat.array [3],
                                          pos.quat.array [0])
    self.transform.transform.translation = (pos.trans [0],
                                             pos.trans [1],
                                             pos.trans [2])
    self.js.position = []
    for (rank, convert) in self.jointConversion:
        self.js.position.append (convert (config [rank:]))

def computeRobotPositionPlanar (self, config):
    c = config [self.cfgBegin + 2]
    s = config [self.cfgBegin + 3]
    if -1e-6 < s and s < 1e-6:
        sinth2 = 0; costh2 = 1
    else:
        costh2 = sqrt ((c+1)/2.); sinth2 = s / (2*costh2)
    jointMotion = Transform (Quaternion (costh2, 0 , 0, sinth2),
                             np.array ([config [self.cfgBegin + 0], config [self.cfgBegin + 1], 0]))
    pos = self.rootJointPosition * jointMotion
    self.transform.transform.rotation = (pos.quat.array [1],
                                          pos.quat.array [2],
                                          pos.quat.array [3],
                                          pos.quat.array [0])
    self.transform.transform.translation = (pos.trans [0],
                                             pos.trans [1],
                                             pos.trans [2])
    self.js.position = []
    for (rank, convert) in self.jointConversion:
        self.js.position.append (convert (config [rank:]))

## Display of robot and obstacle configurations in Rviz
#
#  This class implements
#  \li a tranform broadcaster that broadcasts the position of the robot root
#      link with respect to the global frame "map",
#  \li a joint state publisher that publishes the joint positions. These joint
#      positions are read by a node of type "robot_state_publisher" that
#      computes the relative positions of all links of the robot. Rviz then
#      displays the positions of the links.
class ScenePublisher (object):
    def __init__ (self, robot, tf_root = None, prefix = None, jointNames = None, cfgBegin = None):
        if prefix is None:
            self.rootJointType = robot.rootJointType
            if self.rootJointType == "freeflyer":
                jointNames = robot.jointNames[2:]
                self.computeRobotPosition = computeRobotPositionFreeflyer
            elif self.rootJointType == "planar":
                jointNames = robot.jointNames[2:]
                self.computeRobotPosition = computeRobotPositionPlanar
            elif self.rootJointType == "anchor":
                jointNames = robot.jointNames[:]
                self.computeRobotPosition = computeRobotPositionAnchor
            else:
              raise RuntimeError ("Unknow root joint type: " + self.rootJointType)
            try:
                rootJointPosition = getRootJointPosition (robot)
            except hpp.Error:
                rootJointPosition = Transform (Quaternion ([1,0,0,0]),
                                                np.array ([0,0,0]))
            cfgBegin = 0
            self.build (robot, robot.tf_root, rootJointPosition, "", jointNames, cfgBegin)
        else:
            self.rootJointType = robot.rootJointType[prefix]
            if self.rootJointType == "freeflyer":
                shift = 2
                self.computeRobotPosition = computeRobotPositionFreeflyer
            elif self.rootJointType == "planar":
                shift = 2
                self.computeRobotPosition = computeRobotPositionPlanar
            elif self.rootJointType == "anchor":
                shift = 0
                self.computeRobotPosition = computeRobotPositionAnchor
            else:
              raise RuntimeError ("Unknow root joint type: " + self.rootJointType)
            try:
              pos = robot.client.manipulation.robot.getRootJointPosition (prefix)
              rootJointPosition = Transform (Quaternion (pos [3:7]), np.array (pos [0:3]))
            except:
              rootJointPosition = Transform (Quaternion ([1,0,0,0]), np.array ([0,0,0]))
            self.build (robot, tf_root, rootJointPosition, prefix + "/", jointNames[shift:], cfgBegin)

    def build (self, robot, tf_root, rootJointPosition, prefix, jointNames, cfgBegin):
        """
        jointNames contains all the actuated joints of the specified robot
        """
        if prefix is "" or prefix is None:
          self.tf_root = tf_root
        else:
          self.tf_root = "/" + prefix + tf_root
        self.rootJointPosition = rootJointPosition
        self.referenceFrame = "map"

        self.cfgBegin = cfgBegin
        self.pubRobots = dict ()
        self.pubRobots ['marker'] = rospy.Publisher ('/visualization_marker_array', MarkerArray)
        self.js = JointState ()
        if len(jointNames) is 0:
            self.pubRobots ['robot'] = None
            self.jointConversion = list ()
        else:
            self.pubRobots ['robot'] = rospy.Publisher ("/" + prefix + 'joint_states', JointState)
            self.js.name = jointNames
            self.initJointConversion (robot, prefix, jointNames)
        self.broadcaster = TransformBroadcaster ()
        rospy.init_node ('hpp', log_level=rospy.FATAL )
        # Create constant transformation between the map frame and the robot
        # base link frame.
        self.transform = TransformStamped ()
        self.transform.header.frame_id = self.referenceFrame;
        self.transform.child_frame_id = self.tf_root
        # Create constant transformation between the map frame and the obstacle
        # frame.
        # Here, the obstacle can move in the map frame (see __call__, with the
        # move q_obs) but is without any joint.
        self.trans_map_obstacle = TransformStamped ()
        self.trans_map_obstacle.header.frame_id = "map";
        self.trans_map_obstacle.child_frame_id = "obstacle_base"
        self.objects = dict ()
        self.markerArray = MarkerArray()
        self.oid = 0

    ## Initialize map to build rviz configuration
    #  In hpp, unbouded rotation joint have 2 configuration variables, this
    #  makes the mapping of configurations between ROS and hpp non trivial
    def initJointConversion (self, robot, prefix, jointNames):
        self.jointConversion = []
        rank = 0
        for n in robot.getJointNames ():
            size = robot.getJointConfigSize (n)
            if not n.startswith (prefix) or n [len(prefix):] not in jointNames:
                rank += size
                continue
            if size == 1:
                self.jointConversion.append ((rank, lambda x: x[0]))
            elif size == 2:
                self.jointConversion.append ((rank, lambda x: atan2
                                              (x[1], x[0])))
            else:
                raise RuntimeError ("Unknow joint of size " + str (size))
            rank += size

    def addObject (self, name, frameId):
        """
        Add an object with given name and attached to given frame
        """
        self.objects [name] = Obstacle (name, frameId)

    def addPolygonFilled(self, points):
        oid = self.oid+1
        name = "/polygonFilled"+str(self.oid)
        marker = Marker()
        marker.id = self.oid
        marker.ns = "/polygonFilled"
        marker.header.frame_id = name
        marker.type = marker.TRIANGLE_LIST
        marker.action = marker.ADD
        marker.scale.x = 1
        marker.scale.y = 1
        marker.scale.z = 1
        marker.color.r = 1.0
        marker.color.g = 1.0
        marker.color.b = 1.0
        marker.color.a = 1.0
        marker.pose.orientation.w = 1.0
        marker.pose.position.x = 0
        marker.pose.position.y = 0
        marker.pose.position.z = 0
        marker.points = []
        for i in range(0,len(points)-2,1):
                pt = Point(points[0][0], points[0][1], points[0][2])
                marker.points.append(pt)
                pt = Point(points[i+1][0], points[i+1][1], points[i+1][2])
                marker.points.append(pt)
                pt = Point(points[i+2][0], points[i+2][1], points[i+2][2])
                marker.points.append(pt)
        self.markerArray.markers.append(marker)

    def addPolygon(self, points, linewidth=0.02):
        self.oid = self.oid+1
        self.name = "/polygon"+str(self.oid)
        self.marker = Marker()
        self.marker.id = self.oid
        self.marker.ns = "/polygon"
        self.marker.header.frame_id = self.name
        self.marker.type = self.marker.LINE_STRIP
        self.marker.action = self.marker.ADD
        self.marker.scale.x = linewidth
        self.marker.scale.y = 1
        self.marker.scale.z = 1
        self.marker.color.r = 1.0
        self.marker.color.g = 0.0
        self.marker.color.b = 0.0
        self.marker.color.a = 1.0
        self.marker.pose.orientation.w = 1.0
        self.marker.pose.position.x = 0
        self.marker.pose.position.y = 0
        self.marker.pose.position.z = 0
        self.marker.points = []
        for p in points:
                pt = Point()
                pt.x = p[0]; pt.y = p[1]; pt.z = p[2]
                self.marker.points.append(pt)
        #connect last marker to first marker
        pt = Point()
        pt.x = points[0][0]; pt.y = points[0][1]; pt.z = points[0][2]
        self.marker.points.append(pt)

        self.markerArray.markers.append(self.marker)

    def addSphere(self, x, y, z):
        self.addSphere(x, y, z, 0.05, 0.05, 0.05)

    def addSphere(self, x, y, z, sx, sy, sz):
        self.oid = self.oid+1
        self.name = "/sphere"+str(self.oid)
        self.marker = Marker()
        self.marker.id = self.oid
        self.marker.ns = "/shapes"
        self.marker.header.frame_id = self.name
        self.marker.type = self.marker.SPHERE
        self.marker.action = self.marker.ADD
        self.marker.scale.x = sx
        self.marker.scale.y = sy
        self.marker.scale.z = sz
        self.marker.color.r = 1.0
        self.marker.color.g = 0.0
        self.marker.color.b = 1.0
        self.marker.color.a = 1.0
        self.marker.pose.orientation.w = 1.0
        self.marker.pose.position.x = x
        self.marker.pose.position.y = y
        self.marker.pose.position.z = z
        self.markerArray.markers.append(self.marker)

    def publishObjects (self):
        if not rospy.is_shutdown ():
            now = rospy.Time.now ()
            r = rospy.Rate(10)
            for n, obj in self.objects.iteritems ():
                self.broadcaster.sendTransform \
                    (obj.position [0:3], (obj.position [4],
                                          obj.position [5],
                                          obj.position [6],
                                          obj.position [3]), now,
                     obj.frameId, "map")
            for m in self.markerArray.markers:
                    #pos = (m.pose.position.x, m.pose.position.y, m.pose.position.z)
                    pos = (0,0,0)
                    ori = ( m.pose.orientation.x,  \
                            m.pose.orientation.y, \
                            m.pose.orientation.z, \
                            m.pose.orientation.w)
                    self.broadcaster.sendTransform \
                        (pos, ori, now, m.header.frame_id, "/"+self.referenceFrame)

            self.pubRobots ['marker'].publish (self.markerArray)

    def moveObject (self, name, position):
        self.objects [name].position = position

    def publish (self):
        self.publishObjects ()
        self.publishRobots ()


    def publishRobots (self):
        if not rospy.is_shutdown ():
            config = self.robotConfig
            now = rospy.Time.now ()
            self.computeRobotPosition (self, config)
            self.transform.header.stamp.secs = now.secs
            self.transform.header.stamp.nsecs = now.nsecs
            self.transform.header.seq = self.js.header.seq
            if self.pubRobots ['robot'] is not None:
                self.js.header.stamp.secs = now.secs
                self.js.header.stamp.nsecs = now.nsecs
                self.js.header.seq += 1
                self.js.velocity = len (self.js.position)*[0.,]
                self.js.effort = len (self.js.position)*[0.,]
                rospy.loginfo (self.js)

            rospy.loginfo (self.transform)
            self.broadcaster.sendTransform \
                (self.transform.transform.translation,
                 self.transform.transform.rotation,
                 now, self.tf_root, self.referenceFrame)
            if self.pubRobots ['robot'] is not None:
                self.pubRobots ['robot'].publish (self.js)

    def __call__ (self, args):
        self.robotConfig = args
        self.publish ()
