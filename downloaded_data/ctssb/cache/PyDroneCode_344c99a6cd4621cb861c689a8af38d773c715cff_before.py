#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of PyDroneCode.
# Please check the file LICENSE.MD for information about the license.
#
# @file
# @version 0.1
# @copyright 2016 Desmodul
# @author Markus Riegert <desmodul@drow-land.de>
# _______________________________________________________________________
# Communicates the generated controller commands to the controlled drone.

from LoggerFactory import LogHandler
import socket
import sys


class Transmitter(object):
    """ Establishes a TCP connection to the drone and populates commands. """

    def __init__(self, _networkConfig):
        self.logger = LogHandler.getLogger(__name__)
        self.droneAdressWlan = "192.168.23.199"
        self.droneAdressLan = "192.168.1.199"
        self.droneControlPort = "20050"

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.state = "connecting"
        try:
            self.socket.connect((self.droneAdressWlan, self.droneControlPort))
            self.state = "connected"
        except:
            self.state = "error"
            self.logger.warn("Connection Error!!! E=" + sys.exc_info()[0])
            self.socket.close()
            self.socket = 0

    def sendData(self, _data):
        if self.socket:
            self.socket.sendall(bytes(_data + "\n", "utf-8"))
            print(("Sent:     {}".format(_data)))
            self.state = "sentData"
            return True
        else:
            self.logger.info("Error sending data: Not connected to drone!!!")
            return False

    def connected(self):
        if self.state == "connected" or self.state == "sentData":
            return True
        else:
            return False

    def getState(self):
        return self.state


def create(_networkConfig):
    transmitter = Transmitter(_networkConfig)
    return transmitter
