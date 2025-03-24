#!/usr/bin/env python

import datetime
import os, sys, re
from time import sleep

from pypinsobj.pypinsobj import *



class Relay(object):




    def __init__(self, config_file):
	self.p = Pins(mode=BCM, from_file=config_file)


    def turn_on(self, channel_name):
	self.p.turn_on(channel_name)


    def turn_off(self, channel_name):
	self.p.turn_off(channel_name)
    



