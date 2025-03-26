#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import PoseStamped, Pose
from styx_msgs.msg import TrafficLightArray, TrafficLight
from styx_msgs.msg import Lane
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from light_classification.tl_classifier import TLClassifier
import tf
import cv2
import yaml
import math
from enum import Enum

STATE_COUNT_THRESHOLD = 1

class TrafficLightColor(Enum):
    RED = 0
    YELLOW = 1
    GREEN = 2
    NAN = 3
    UNKNOWN = 4

class TLDetector(object):
    def __init__(self, use_tl_groundtruth=False, simulator=True):
        rospy.init_node('tl_detector')

        self.pose = None
        self.waypoint = None
        self.camera_image = None
        self.lights = []

        self.waypoints = 0
        self.num_waypoints = 0
        self.stop_line_waypoints = None
        self.traffic_light_waypoints = None
        self.traffic_light_waypoints_ready = False
        self.use_tl_groundtruth = use_tl_groundtruth
        self.state = TrafficLight.UNKNOWN
        self.last_state = TrafficLight.UNKNOWN
        self.last_wp = -1
        self.state_count = 0
        self.light_classifier = None
        self.current_stop_line_wp = None


        sub1 = rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb)
        sub2 = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb)

        '''
        /vehicle/traffic_lights provides you with the location of the traffic light in 3D map space and
        helps you acquire an accurate ground truth data source for the traffic light
        classifier by sending the current color state of all traffic lights in the
        simulator. When testing on the vehicle, the color state will not be available. You'll need to
        rely on the position of the light and the camera image to predict it.
        '''
        sub3 = rospy.Subscriber('/vehicle/traffic_lights', TrafficLightArray, self.traffic_cb)
        sub6 = rospy.Subscriber('/image_color', Image, self.image_cb,
                                queue_size=1)

        config_string = rospy.get_param("/traffic_light_config")
        self.config = yaml.load(config_string)

        self.upcoming_red_light_pub = rospy.Publisher('/traffic_waypoint', Int32, queue_size=1)

        self.bridge = CvBridge()
        self.light_classifier = TLClassifier(simulator)
        self.listener = tf.TransformListener()

        self.loop()

    def loop(self):
        rate = rospy.Rate(1)  # 50Hz
        while not rospy.is_shutdown():

            if self.pose is None or self.camera_image is None:
                continue

            light_wp, state = self.process_traffic_lights()

            '''
            Publish upcoming red lights at camera frequency.
            Each predicted state has to occur `STATE_COUNT_THRESHOLD` number
            of times till we start using it. Otherwise the previous stable state is
            used.
            '''
            if state != TrafficLight.UNKNOWN:
                if self.state != state:
                    self.state_count = 0
                    self.state = state
                elif self.state_count >= STATE_COUNT_THRESHOLD:
                    self.last_state = self.state
                    light_wp = light_wp if state == TrafficLight.RED else -1
                    self.last_wp = light_wp
                    self.upcoming_red_light_pub.publish(Int32(light_wp))
                    # rospy.loginfo("image_cb publishing new %s", int(self.last_wp))
                else:
                    self.upcoming_red_light_pub.publish(Int32(self.last_wp))
                    # rospy.loginfo("image_cb publishing last red tl wp index %s", int(self.last_wp))

                self.state_count += 1

            rate.sleep()

    def pose_cb(self, msg):
        self.pose = msg

    def waypoints_cb(self, waypoints):
        self.waypoints = waypoints
        self.num_waypoints = len(waypoints.waypoints)
        self.calc_stop_line_waypoints()

    def traffic_cb(self, msg):
        self.lights = msg.lights

    def image_cb(self, msg):
        """Identifies red lights in the incoming camera image and publishes the index
            of the waypoint closest to the red light's stop line to /traffic_waypoint

        Args:
            msg (Image): image from car-mounted camera

        """
        self.has_image = True
        self.camera_image = msg


    def get_closest_waypoint(self, pose):
        """Identifies the closest path waypoint to the given position
            https://en.wikipedia.org/wiki/Closest_pair_of_points_problem
        Args:
            pose (Pose): position to match a waypoint to

        Returns:
            int: index of the closest waypoint in self.waypoints

        """
        #TODO implement

        if self.waypoints is None or self.num_waypoints == 0:
            return None

        min_dist = 1e9
        index = None

        for k in xrange(self.num_waypoints):
            delta_x = (self.waypoints.waypoints[k].pose.pose.position.x - pose.position.x)
            delta_y = (self.waypoints.waypoints[k].pose.pose.position.y - pose.position.y)

            # this is actually dist_squared
            # but we can just use it as comparison
            dist = delta_x*delta_x + delta_y*delta_y
            if dist < min_dist:
                #rospy.loginfo("dx: %s, \t dy: %s", delta_x, delta_y)
                index = k
                min_dist = dist

        return index

    def get_light_state(self):
        """Determines the current color of the traffic light

        Args:
            light (TrafficLight): light to classify

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        if(not self.has_image):
            self.prev_light_loc = None
            return TrafficLight.UNKNOWN

        cv_image = self.bridge.imgmsg_to_cv2(self.camera_image, "bgr8")
        height, width, channels = cv_image.shape
        cv_small = cv_image[:, 0: int(height/1.3)]  # take more image for processing
        cv_small = cv2.resize(cv_small, (0, 0), fx=0.5, fy=0.5)

        #Get classification
        if self.light_classifier:
            return self.light_classifier.get_classification(cv_small)
        else:
            return TrafficLight.UNKNOWN

    def calc_stop_line_waypoints(self):
        # List of positions that correspond to the line to stop in front of for a given intersection
        stop_line_positions = self.config['stop_line_positions']

        stop_line_waypoints = []
        for stop_line_pos in stop_line_positions:
            p = Pose()
            p.position.x = stop_line_pos[0]
            p.position.y = stop_line_pos[1]
            idx = self.get_closest_waypoint(p)
            stop_line_waypoints.append((idx, p.position.x, p.position.y))

        # save this list
        self.stop_line_waypoints = stop_line_waypoints

    def calc_traffic_light_waypoints(self):
        traffic_light_waypoints = []
        for light in self.lights:
            idx = self.get_closest_waypoint(light.pose.pose)
            traffic_light_waypoints.append((idx, light.pose.pose.position.x, light.pose.pose.position.y, light.state))

        # save this list
        self.traffic_light_waypoints = traffic_light_waypoints
        self.traffic_light_waypoints_ready = True

    def process_traffic_lights(self):
        """Finds closest visible traffic light, if one exists, and determines its
            location and color

        Returns:
            int: index of waypoint closes to the upcoming stop line for a traffic light (-1 if none exists)
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        car_wp = None
        stop_line_wp = None
        tl_ground_truth_state = TrafficLight.UNKNOWN
        
        if self.pose:
            car_wp = self.get_closest_waypoint(self.pose.pose)
            # str = 'closest way point: %s'%car_position
            # rospy.loginfo(str)

        #TODO find the closest visible traffic light (if one exists)
        # 1. find the closest stop line ahead
        #
        # 1.1. Find all the stop lines' relative way point distance from the car
        stop_line_waypoints_and_deltas = []

        closed_stop_line_idx = None
        closest_delta_idx = 20000000

        if self.stop_line_waypoints is not None and car_wp is not None:

            for i, t in enumerate(self.stop_line_waypoints):
                sl_wp = t[0]
                if sl_wp is not None:
                    delta_idx = sl_wp - car_wp
                    if delta_idx < 0:
                        continue

                    if delta_idx < closest_delta_idx:
                        closed_stop_line_idx = i
                        closest_delta_idx = delta_idx

            POS_THRESHOLD = 50.0
            COLOR_STR = ['RED', 'YELLOW', 'GREEN', 'NAN', 'UNKNOWN']

            # Now we have found all the stop lines' way points and their relative way point distance from the car
            #
            # 1.2. Find the closest stop line ahead of the car
            #
            if closed_stop_line_idx is not None:

                closest_sl_wp = self.stop_line_waypoints[closed_stop_line_idx][0]

                # calculate distance between the car and the first light coming up
                closest_stop_line_x = self.stop_line_waypoints[closed_stop_line_idx][1]
                closest_stop_line_y = self.stop_line_waypoints[closed_stop_line_idx][2]

                car_x = self.pose.pose.position.x
                car_y = self.pose.pose.position.y

                dist_car_and_stop_line = math.sqrt((car_x - closest_stop_line_x)**2 + (car_y - closest_stop_line_y)**2)

                if dist_car_and_stop_line > 300:
                    return closest_sl_wp, TrafficLight.UNKNOWN

                #
                # 2. Find the traffic light that is closest to and ahead of the stop line we found above
                #
                # update traffic light way points
                if len(self.lights) > 0:
                    self.traffic_light_waypoints_ready = False
                    self.calc_traffic_light_waypoints()

                # proceed if successfully updated traffic light waypoints
                if self.traffic_light_waypoints_ready:

                    closest_tl_wp_delta = 20000
                    closest_tl_wp = None
                    for i, tl_wp in enumerate(self.traffic_light_waypoints):

                        if tl_wp is not None:
                            delta_idx_tl_sl = tl_wp[0] - closest_sl_wp  # waypoint index difference between traffic light and stop line
                            if delta_idx_tl_sl < 0:
                                continue

                            if delta_idx_tl_sl < closest_tl_wp_delta:
                                closest_tl_wp_delta = delta_idx_tl_sl
                                closest_tl_wp = tl_wp

                    if closest_tl_wp is not None:
                        tl_ground_truth_state = closest_tl_wp[3]
                        stop_line_wp = closest_sl_wp
                        self.current_stop_line_wp = stop_line_wp
                        #rospy.loginfo("Traffic light in %s m, color is %s", dist_car_and_stop_line, COLOR_STR[light_state_ground_truth])
                        if self.use_tl_groundtruth:
                            return self.current_stop_line_wp, tl_ground_truth_state

        if not self.use_tl_groundtruth:
            tl_state = self.get_light_state()
            tl_color = TrafficLightColor(tl_state).name
            gt_color = TrafficLightColor(tl_ground_truth_state).name
            rospy.loginfo("Traffic light detected %s, gt %s", tl_color,
                          gt_color)
            return self.current_stop_line_wp, tl_state
        #self.waypoints = None
        return -1, TrafficLight.UNKNOWN

if __name__ == '__main__':
    try:
        TLDetector()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start traffic node.')
