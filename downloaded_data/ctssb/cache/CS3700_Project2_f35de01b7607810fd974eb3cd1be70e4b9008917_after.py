#!/usr/bin/python -u

import sys
import socket
import select
from Packet import Packet

RECEIVE_SIZE = 1500


class Bridge:
    def __init__(self, bridgeID, LAN_list=[]):
        self.id = bridgeID
        #self.LAN_list = LAN
        self.sockets = []
        self.rootID = self.id

        self._create_sockets_for_lans(LAN_list)
        self._start_receiving()

    def _create_sockets_for_lans(self, LAN_list):
        for x in range(len(LAN_list)):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            s.connect(self._pad(LAN_list[x]))
            self.sockets.append(s)

    def _start_receiving(self):
        # Main loop
        while True:
            # Calls select with all the sockets; change the timeout value (1)
            ready, ignore, ignore2 = select.select(self.sockets, [], [], 1)
            # Reads from each fo the ready sockets
            for x in ready:
                message = x.recv(RECEIVE_SIZE)
                # create new packet object from the incoming message
                packet = Packet(message)
                if packet.isBPDU:
                    self._choose_rootID_from_BPDU(packet)

    def _pad(self, name):
        # pads the name with null bytes at the end
        result = '\0' + name
        while len(result) < 108:
                result += '\0'
        return result

    def _choose_rootID_from_BPDU(self, BPDU_in):
        rootID_2 = BPDU_in.rootID
        cost_2 = BPDU_in.cost
        bridgeID_2 = BPDU_in.id

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
