#!/usr/bin/env python

import rospy
from geometry_msgs.msg import PoseStamped
from styx_msgs.msg import Lane, Waypoint, TrafficLight
from std_msgs.msg import Int32, UInt8
from copy import deepcopy
from scipy import spatial
import numpy as np
import tf

import math

'''
This node will publish waypoints from the car's current position to some `x` distance ahead.

As mentioned in the doc, you should ideally first implement a version which does not care
about traffic lights or obstacles.

Once you have created dbw_node, you will update this node to use the status of traffic lights too.

Please note that our simulator also provides the exact location of traffic lights and their
current status in `/vehicle/traffic_lights` message. You can use this message to build this node
as well as to verify your TL classifier.

TODO (for Yousuf and Aaron): Stopline location for each traffic light.
'''

LOOKAHEAD_WPS = 100 # Number of waypoints we will publish. You can change this number


class WaypointUpdater(object):
    def __init__(self):
        rospy.init_node('waypoint_updater', log_level=rospy.DEBUG)

        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb, queue_size=1)
        rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb, queue_size=1)

        rospy.Subscriber('/traffic_waypoint', Int32, self.traffic_cb, queue_size=1)
        rospy.Subscriber('/traffic_state', UInt8, self.traffic_state_cb, queue_size=1)
        rospy.Subscriber('/obstacle_waypoint', Lane, self.obstacle_cb, queue_size=1)


        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)
        self.current_waypoint_index = rospy.Publisher('current_waypoint_index', Int32, queue_size=1)

        # get the speed limit in kph from the waypoint_loader node params store in ms-1
        self.speed_limit = (rospy.get_param('/waypoint_loader/velocity', 10)) * (1000.0 / 3600.0)
        # get the light approach speed limit in kph from the waypoint_loader node params store in ms-1
        self.speed_limit_stop = (rospy.get_param('/waypoint_loader/approach_velocity', 10)) * (1000.0 / 3600.0)
        # get the main message loop update rate in Hz from the waypoint_updater node params
        self.update_rate = rospy.get_param('/waypoint_updater/update_rate', 10)
        # empty placeholder for base waypoints
        self.base_waypoints = None
        # empty placeholder for waypoint working copy
        self.waypoints = None
        # empty placeholder for the current pose of the vehicle
        self.current_pose = None
        # empty placeholder for the current nearest waypoint
        self.current_wp = None
        # empty placeholder for the next waypoint we have to stop at
        self.next_stop = -1
        # empty placeholder for the next light state
        self.next_stop_state = TrafficLight.RED
        # extra debug option
        self.extraDebug = False
        # get the maximum detection distance for the lights in m
        self.max_detect_distance = rospy.get_param('/tl_detector/max_detect_distance', 100)
        # spacial tree to store waypoints
        self.tree = None

        self.loop()

    def loop(self):
        # main message loop for waypoint updater
        rate = rospy.Rate(self.update_rate)
        while not rospy.is_shutdown():
            # do we have the base waypoints yet?
            if self.waypoints and self.current_pose and self.tree != None:
                # find out which waypoint we are next nearest to
                wp_closest = self.locateNextWaypoint()

                # build the list of next waypoints
                waypoints = []
                if wp_closest != None:
                    for wp in range(LOOKAHEAD_WPS):
                        wp_index = (wp + wp_closest) % len(self.waypoints)
                        wp_velocity = self.get_waypoint_velocity(self.base_waypoints[wp_index])
                        target_velocity = min(self.speed_limit, wp_velocity)
                        if self.next_stop != -1 and self.next_stop < len(self.waypoints):
                            # work out how far away this waypoint is from the stop
                            wp_distance_to_stop = self.distanceCarToWaypoint(self.waypoints[wp_index].pose.pose,
                                                                             self.waypoints[self.next_stop].pose.pose)
                            if wp_distance_to_stop < self.max_detect_distance:
                                if self.next_stop_state != TrafficLight.GREEN:
                                    if wp_distance_to_stop < 2.0:
                                        target_velocity = 0.0
                                    else:
                                        target_velocity = target_velocity * (wp_distance_to_stop / self.max_detect_distance)
                                    if wp_index == self.next_stop:
                                        rospy.loginfo("WaypointUpdater: Red light ahead reducing waypoint %s velcocity to %.2fkmh", wp_index, target_velocity * 3.6)
                                elif target_velocity > self.speed_limit_stop:
                                    target_velocity = self.speed_limit_stop
                        self.set_waypoint_velocity(self.waypoints, wp_index, target_velocity)
                        waypoints.append(self.waypoints[wp_index])
#                rospy.loginfo("WaypointUpdater: waypoints=%s", waypoints)
                self.publish(waypoints, wp_closest)
            rate.sleep()

    def publish(self, waypoints, wp_closest):
        # populate the next_waypoint message
        next_waypoints = Lane()
        next_waypoints.header.frame_id = '/world'
        next_waypoints.header.stamp = rospy.Time.now()
        next_waypoints.waypoints = waypoints
        # publish the waypoints
        self.final_waypoints_pub.publish(next_waypoints)

        # publish the current waypoint index if not None
        if wp_closest != None:
            self.current_waypoint_index.publish(wp_closest)

    def locateNextWaypoint(self):

        #query the nearest point to the vehicle
        distance, wps_closest = self.tree.query(np.array([[self.current_pose.position.x, self.current_pose.position.y, self.current_pose.position.z]]))

        wp_closest = wps_closest[0]
        distance = distance[0]

        #calculate euler angles of current vehicle pose
        euler = tf.transformations.euler_from_quaternion([self.current_pose.orientation.x,self.current_pose.orientation.y,
                                                          self.current_pose.orientation.z,self.current_pose.orientation.w])

        #calculate the heading of the closest waypoint
        heading_to_waypoint = math.atan2(self.waypoints[wp_closest].pose.pose.position.y-self.current_pose.position.y,
                                         self.waypoints[wp_closest].pose.pose.position.x-self.current_pose.position.x) \
                              - euler[2]

        #if the closest waypoint is behind the vehicle, take the next one (probably in front of the vehicle)
        if math.fabs(heading_to_waypoint) > math.pi/2:
            wp_closest = wp_closest+1

        rospy.loginfo("locateNextWaypoints: wp_closest=%s distance=%.2fm", wp_closest, distance)

        return wp_closest

    def distanceCarToWaypoint(self, pose, waypoint):
        dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
        # calculate Pythagorean distance between waypoint and car's pose
        distance = dl(pose.position, waypoint.position)
        return distance

    def pose_cb(self, msg):
        self.current_pose = msg.pose
        pass

    def waypoints_cb(self, waypoints):
        rospy.loginfo("waypoints_cb: received %s base waypoints", len(waypoints.waypoints))
        self.base_waypoints = waypoints.waypoints
        self.waypoints = deepcopy(self.base_waypoints)

        #setup a kd-tree for efficient nearest neighor lookup
        #(see https://docs.scipy.org/doc/scipy-0.19.1/reference/generated/scipy.spatial.KDTree.html)
        #(Paper: https://www.cs.umd.edu/~mount/Papers/iccs01-kflat.pdf)

        x=[]
        y=[]
        z=[]

        for waypoint in waypoints.waypoints:
            x.append(waypoint.pose.pose.position.x)
            y.append(waypoint.pose.pose.position.y)
            z.append(waypoint.pose.pose.position.z)

        data = zip(x,y,z)

        self.tree = spatial.KDTree(data)

    def traffic_cb(self, msg):
        self.next_stop = msg.data

    def traffic_state_cb(self, msg):
        self.next_stop_state = msg.data

    def obstacle_cb(self, msg):
        # TODO: Callback for /obstacle_waypoint message. We will implement it later
        pass

    def get_waypoint_velocity(self, waypoint):
        return waypoint.twist.twist.linear.x

    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
        waypoints[waypoint].twist.twist.linear.x = velocity

    def distance(self, waypoints, wp1, wp2):
        dist = 0
        dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
        for i in range(wp1, wp2+1):
            dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
            wp1 = i
        return dist

if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
