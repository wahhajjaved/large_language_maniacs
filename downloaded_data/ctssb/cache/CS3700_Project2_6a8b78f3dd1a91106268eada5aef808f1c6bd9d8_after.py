#!/usr/bin/python -u

import sys
import socket
import select
from Packet import Packet
from BPDU import BPDU
from Port import Port

RECEIVE_SIZE = 1500


class Bridge:
    def __init__(self, bridgeID, LAN_list=[]):
        self.id = bridgeID
        self.ports = []
        self.sockets = []
        self.rootID = self.id

        self._create_ports_for_lans(LAN_list)
        self._start_receiving()

    def _create_ports_for_lans(self, LAN_list):
        # iterator = 0
        for x in range(len(LAN_list)):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)

            #port = Port(iterator)
            s.connect(self._pad(LAN_list[x]))
            # self.ports.append(port)
            #iterator += 1
            self.sockets.append(s)

    def _start_receiving(self):
        # Main loop
        while True:

            #sockets =
            # Calls select with all the ports; change the timeout value (1)

            ready, ignore, ignore2 = select.select(self.sockets, [], [], 1)
            # Reads from each fo the ready ports
            for x in ready:
                message = x.recv(RECEIVE_SIZE)
                # create new packet object from the incoming message
                #packet = Packet(message)
                bpdu_in = create_BPDU_from_json(message)
                #if bpdu_in:
                    # call set root
                    # if incoming bpdu better than this
                #else:
                    #create normal data message
                #if packet.isBPDU:
                    #self._choose_rootID_from_BPDU(packet)

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

    """
    def _create_new_BPDU(self, source, BPDU_id, root, cost):
        BPDU_message = {}
        BPDU_message['source'] = source
        BPDU_message['dest'] = 'ffff'
        BPDU_message['type'] = 'bpdu'
        BPDU_message['message'] = {}
        BPDU_message['message']['id'] = self.id
        BPDU_message['message']['root'] = root
        BPDU_message['message']['cost'] = cost

        return json.dumps(BPDU_message)
    """

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
