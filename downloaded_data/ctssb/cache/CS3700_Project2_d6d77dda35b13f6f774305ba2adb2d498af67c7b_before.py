#!/usr/bin/python -u

import sys
import socket
import select
from Packet import Packet
from BPDU import BPDU, create_BPDU_from_json
from DataMessage import DataMessage, create_DataMessage_from_json
from Port import Port
import time

RECEIVE_SIZE = 1500


# check through all top BPDUs of all ports...
# for those that are the same, close the highest cost ports

class Bridge:
    """
    This is the class for a Bridge, which contains all the information
    for a network bridge
    """
    def __init__(self, bridgeID, LAN_list=[]):
        """
        creates a new Bridge
        @param bridgeID : unique bridge id, set
        @param LAN_list : default to empty list, else, will hold the LANs
        """
        self.id = bridgeID
        self.ports = []
        self.sockets = []
        self.rootID = self.id
        self.rootPort = None
        self.cost = 1

        self._create_ports_for_lans(LAN_list)
        print "Bridge " + self.id + " starting up\n"
        self._start_receiving()

    def _create_ports_for_lans(self, LAN_list):
        """
        Creates a new socket with a respective port for each
        LAN in the LAN_list
        @LAN_list : List of LANs to create sockets for
        """
        iterator = 0
        for x in range(len(LAN_list)):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            port = Port(iterator, s)
            s.connect(self._pad(LAN_list[x]))
            self.ports.append(port)
            self.sockets.append(s)
            iterator += 1

    def _start_receiving(self):
        """
        This function starts by broadcasting a BPDU, then runs the main loop
        for a Bridge that receives and sends messages and BPDUs to specific
        ports, and takes care of broadcasting BPDUs and messages to all ports
        """
        start_time = time.time()

        self._broadcast_BPDU()

        BPDU_buffer = []

        # Main loop
        while True:

            # -----ORIGINAL CALLS------#
            # ready, ignore, ignore2 = select.select(self.sockets, [], [], 1)
            # Reads from each fo the ready ports
            # for x in ready:
            #    message = x.recv(RECEIVE_SIZE)
            # -------------------------#

            for port in self.ports:
                ready, ignore, ignore2 = select.select([port.socket], [], [], 1)
                if ready:
                    message = ready[0].recv(RECEIVE_SIZE)
                    # attempt to create BPDU object from incoming message
                    bpdu_in = create_BPDU_from_json(message)
                    if bpdu_in:
                        self._assign_new_root(bpdu_in, port.port_id)
                        port.add_BPDU(bpdu_in)
                        # add bpdu to buffer
                        BPDU_buffer.append(bpdu_in)

                    ########################################################
                    elif not bpdu_in:
                        data_in = create_DataMessage_from_json(message)
                        if data_in:
                            if port.enabled:
                                print "Received message " + str(data_in.id) + \
                                    " on port " + str(port.port_id) + " from " + \
                                    str(data_in.source) + " to " + str(data_in.dest)

                                # TODO: check forwarding table for data message dest add_address
                                # TODO: if the address exists, send to that port_id
                                # TODO: else... broadcast to all open ports (except received port)

                                print "Broadcasting message " + \
                                    str(data_in.id) + " to all ports"
                                self._broadcast_message(message, port)
                            else:
                                print "Not forwarding message " + str(data_in.id)
                    ########################################################


            # is it time to send a BPDU?
            # compare start time to current time, if > 500ms, send BPDU
            if int(round((time.time() - start_time) * 1000)) > 500:
                if self.id == self.rootID:
                    self._broadcast_BPDU()
                    print "Root BPDU Sent"
                else:
                    # _broadcast_message(best bpdu)
                    # BEFORE BROADCAST, IF TIMEOUT??? POP and send second
                    # also ----- ADD self.cost to BPDU cost
                    if BPDU_buffer[0]:
                        self._broadcast_message(BPDU_buffer[0].create_json_BPDU(), -1)
                        BPDU_buffer.pop(0)  # #########
                        print "SENT MESSAGE: ", message
                start_time = time.time()

    def _pad(self, name):
        """
        Pads the name with null bytes at the end
        @param name : the name to pad
        @return String
        """
        result = '\0' + name
        while len(result) < 108:
                result += '\0'
        return result

    def _assign_new_root(self, bpdu_in, port_in):
        """
        Determines if the incoming BPDU contains a better root information
        than the current root than the better
        @param BPDU_in : the BPDU to be checked if better
        @param port_in : the port that the bpdu_in was received
        """
        oldRootPort = self.rootPort
        if self.rootPort:
            if self.ports[self.rootPort].BPDU_list[0].is_incoming_BPDU_better(bpdu_in):
                self.root = bpdu_in.root
                self.rootPort = port_in
                self.cost = bpdu_in.cost
                print "New root: " + str(self.id) + "/" + str(self.rootID)
                print "Root port: " + str(self.id) + "/" + str(self.rootPort)
                self.ports[self.rootPort].enabled = True
                self.ports[oldRootPort].enabled = False

        else:
            if self.rootID > bpdu_in.root:
                self.rootID = bpdu_in.root
                self.rootPort = port_in
                self.cost = bpdu_in.cost
                print "New root: " + str(self.id) + "/" + str(self.rootID)
                print "Root port: " + str(self.id) + "/" + str(self.rootPort)
                self.ports[self.rootPort].enabled = True
                self.ports[oldRootPort].enabled = False

    def _broadcast_BPDU(self):
        """
        Broadcasts a new BPDU from this bridge to all sockets. This
        will be done if this Bridge is the root
        """
        newBPDU = BPDU(self.id, 'ffff', 99, self.rootID, self.cost)
        for sock in self.sockets:
            sock.send(newBPDU.create_json_BPDU())

    def _broadcast_message(self, message, port_in):
        """
        Broadcasts the given message to all socket connections
        @param message : string
        """
        for port in self.ports:
            if port != port_in:
                port.sock.send(message)

    # bridge logic:
    # all bridges first assume they are the root
    # for each received BPDU, the switch chooses:
    #     - a new root (smallest known ROOT ID)
    #     - a new root port (the port that points toward that root)
    #     - a new designated bridge (who is the next hop to root)
    # DO THIS BY USING LOGIC:
    #  - if ROOT ID1 < ROOT ID2: use BPDU-1
    #  - else if ROOT ID1 == ROOT ID2 && COST1 < COST2: use BPDU-1
    #  - else if ROOT ID1 == ROOT ID2 && COST1 == COST2 ...
    #              ......&& BRIDGE-ID1 < BRIDGE-ID2: use BPDU-1
    #  - else: use BPDU-2

    # BPDU logic:
    # elect root Bridge
    # locate next hop closest to root, and it's port
    # select ports to be included in spanning trees, disable others
