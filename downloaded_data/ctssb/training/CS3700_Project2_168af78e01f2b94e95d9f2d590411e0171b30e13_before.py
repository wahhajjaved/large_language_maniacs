#!/usr/bin/python -u
from BPDU import BPDU
import socket
import time


class Port:
    """
    This is the class for a Port, which contains a portID, enabled status,
    list of BPDU's (sorted by 'bestness'), and a socket (referenced)
    """
    def __init__(self, port_id, socket=None, enabled=True, BPDU_list=[]):
        """
        initializes a new port, with the given sock ID. a socket input is
        defaulted to None, enabled is defaulted to True, and the BPDU_list
        is defaulted to an empty array
        """
        self.port_id = port_id
        self.enabled = enabled
        self.BPDU_list = BPDU_list
        self.socket = socket
        self.designated = True

    def add_BPDU(self, BPDU):
        """
        This function adds the given BPDU into this BPDU_list based on
        'bestness'. It also clears out any expired BPDUs that have timed out
        @param BPDU : the BPDU to add
        """
        iterator = 0
        bpdu_added = False
        BPDU.time = time.time()
        if not self.BPDU_list:
            self.BPDU_list.insert(0, BPDU)
            bpdu_added = True

            # TODO: is this port still designated?

        for bpdu in self.BPDU_list:
            self._remove_timedout_BPDU(bpdu)

            if bpdu.is_incoming_BPDU_better(BPDU) and not bpdu_added:
                bpdu_added = self._add_BPDU_at_position(BPDU, iterator)
            iterator += 1

        # if the BPDU has not been added yet, add it at the end
        if not bpdu_added:
            self.BPDU_list.append(BPDU)

    def _remove_timedout_BPDU(self, BPDU):
        """
        Checks if the given BPDU has timed out. If so, remove it
        from this BPDU list
        @param BPDU : the BPDU to check
        @return boolean : true if removed
        """
        # If the bpdu has timed out, simply remove it
        if int(round((time.time() - BPDU.time) * 1000)) > 750:
            self.BPDU_list.remove(BPDU)
            return True

    def _add_BPDU_at_position(self, BPDU, position):
        """
        Adds the given BPDU at the given position in this BPDU list
        and returns true after it is added
        @param BPDU : the BPDU to add into this BPDU list
        @param position : the position to add the BPDU in the list
        @return True
        """
        self.BPDU_list.insert(position, BPDU)
        bpdu_added = True
        return True
