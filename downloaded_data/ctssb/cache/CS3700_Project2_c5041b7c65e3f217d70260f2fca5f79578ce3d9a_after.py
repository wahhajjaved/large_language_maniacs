#!/usr/bin/python -u

import sys
import socket
import select
from Packet import Packet
from BPDU import BPDU, create_BPDU_from_json
from Port import Port
import time

RECEIVE_SIZE = 1500


class Bridge:
    def __init__(self, bridgeID, LAN_list=[]):
        self.id = bridgeID
        self.ports = []
        self.sockets = []
        self.rootID = self.id
        self.rootPort = None
        self.cost = 0

        self._create_ports_for_lans(LAN_list)
        print "Bridge " + self.id + " starting up\n"
        self._start_receiving()

    def _create_ports_for_lans(self, LAN_list):
        iterator = 0
        for x in range(len(LAN_list)):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)

            port = Port(iterator, s)
            s.connect(self._pad(LAN_list[x]))
            self.ports.append(port)
            iterator += 1
            self.sockets.append(s)

    def _start_receiving(self):
        start_time = time.time()

        # Main loop
        while True:

            #-----ORIGINAL CALLS------#
            # ready, ignore, ignore2 = select.select(self.sockets, [], [], 1)
            # Reads from each fo the ready ports
            #for x in ready:
            #    message = x.recv(RECEIVE_SIZE)
            #-------------------------#

            for port in self.ports:
                ready, ignore, ignore2 = select.select([port.socket], [], [], 1)
                if ready:
                    message = ready[0].recv(RECEIVE_SIZE)
                    # create new packet object from the incoming message
                    #packet = Packet(message)
                    bpdu_in = create_BPDU_from_json(message)
                    if bpdu_in:
                        self._assign_new_root(bpdu_in, port.port_id)
                        port.add_BPDU(bpdu_in)

            #is it time to send a BPDU?
            # compare start time to current time, if > 500ms, send BPDU
            if int(round((time.time() - start_time) * 1000)) > 500:
                self._broadcast_BPDU()
                start_time = time.time()
                print "BPDU"




    def _pad(self, name):
        """
        Pads the name with null bytes at the end
        @param name : the name to pad
        """
        result = '\0' + name
        while len(result) < 108:
                result += '\0'
        return result

    def _choose_rootID_from_BPDU(self, BPDU_in):
        """
        Determines the best BPDU .....

        """
        # TODO : NEEDS TO BE FINISHED
        rootID_2 = BPDU_in.rootID
        cost_2 = BPDU_in.cost
        bridgeID_2 = BPDU_in.id

    def _assign_new_root(self, bpdu_in, port_in):
        if self.rootPort:
            if self.port[self.rootPort].BPDU_list[0].is_incoming_BPDU_better(bpdu_in):
                self.root = bpdu_in.root
                self.rootPort = port_in
                self.cost = bpdu_in.cost
                print "New root: " + self.id + "/" + self.rootID
                print "Root port: " + self.id + "/" + self.rootPort


        else:
            if self.rootID > bpdu_in.root:
                self.rootID = bpdu_in.root
                self.rootPort = port_in
                self.cost = bpdu_in.cost
                print "New root: " + self.id + "/" + self.rootID
                print "Root port: " + self.id + "/" + self.rootPort

    def _broadcast_BPDU(self):
        newBPDU = BPDU(self.id, 'ffff', 99, self.rootID, self.cost)
        for sock in self.sockets:
            sock.send(newBPDU.create_json_BPDU())


    # bridge logic:
    # all bridges first assume they are the root
    # for each received BPDU, the switch chooses:
    #     - a new root (smallest known ROOT ID)
    #     - a new root port (the port that points toward that root)
    #     - a new designated bridge (who is the next hop to root)
    # DO THIS BY USING LOGIC:
    #  - if ROOT ID1 < ROOT ID2: use BPDU-1
    #  - else if ROOT ID1 == ROOT ID2 && COST1 < COST2: use BPDU-1
    #  - else if ROOT ID1 == ROOT ID2 && COST1 == COST2 && BRIDGE-ID1 < BRIDGE-ID2: use BPDU-1
    #  - else: use BPDU-2

    # BPDU logic:
    # elect root Bridge
    # locate next hop closest to root, and it's port
    # select ports to be included in spanning trees, disable others
