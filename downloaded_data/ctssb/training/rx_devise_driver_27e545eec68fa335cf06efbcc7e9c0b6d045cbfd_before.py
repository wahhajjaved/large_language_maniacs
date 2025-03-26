#! /usr/bin/env python3

import sys
import time
sys.path.append("/home/amigos/ros/src/")
import pymeasure2

import rospy
import std_msgs
from std_msgs.msg import Float64


class ml2437a_driver(object):

    def __init__(self, IP='192.168.100.19', GPIB=1):
        self.IP = IP
        self.GPIB = GPIB
        self.com = pymeasure.gpib_prologix(self.IP, self.GPIB)

    def measure(self, ch=1, resolution=3):
        self.com.open()
        self.com.send('CHUNIT %d, DBM' %(ch))
        self.com.send('CHRES %d, %d' %(ch, resolution))
        self.com.send('o %d' %(ch))
        time.sleep(0.1)
        ret = self.com.readline()
        self.com.close()
        power = float(ret)
        return power
"""
    def set_ave(self, ch=1, mode, ave_num):
        self.com.open()
        self.com.send("AVE A, %s, %d" %(mode, ave_num))
        self.com.close()
        return

    def get_ave(self, ch=1):
        self.com.open()
        self.com.send("AVE? A")
        time.sleep(0.1)
        ret = self.com.readline()
        self.com.close()
        ave = float(ret)
        return ave
"""

def str2list(param):
    return param.strip('[').strip(']').split(',')


if __name__ == '__main__':
    node_name = 'ml2437a'
    rospy.init_node(node_name)

    ch_number = 2
    topic_name_index = 0
    onoff_index = 1
    host = rospy.get_param('~host')
    port = rospy.get_param('~port')
    rate = rospy.get_param('~rate')
    topic_list = [str2list(rospy.get_param('~topic{}'.format(i+1))) for i in range(ch_number)]

    try:
        pm = ml2437a_driver(host, port)
    except OSError as e:
        rospy.logerr("{e.strerror}. host={host}".format(**locals()))
        sys.exit()

    pub_list = [rospy.Publisher(topic[topic_name_index], Float64, queue_size=1) \
                for topic in topic_list if int(topic[onoff_index]) == 1]
    onoff_list = [topic[topic_name_index] for topic in topic_list if int(topic[onoff_index]) == 1]
    msg_list = [Float64() for i in range(ch_number)]

while not rospy.is_shutdown():

    ret_list = [pm.measure(ch=int(onoff[-1])) for onoff in onoff_list]

    for pub, msg, ret, i in zip(pub_list, msg_list, ret_list, range(ch_number)):
        msg.data = ret_list[i]
        pub.publish(msg)
    continue
