#!/usr/bin/python -u
import sys
import json


class Packet():
    def __init__(self, message):
        self._parse_to_Packet(message)
        self.isBPDU = False

    def _parse_to_Packet(self, message):
        json_message = json.loads(message)
        self.source = json_message['source']
        self.dest = json_message['dest']
        self.type = json_message['type']
        self.message = json_message['message']
        self.id = self.message['id']

        print "Source: ", self.source
        print "Dest: ", self.dest
        print "Type: ", self.type
        print "Message: ", self.message
        print "MessageID: ", self.messageID

        if self.type == 'bpdu':
            self._create_BPDU(self.message)
            self.isBPDU = True

    def _create_BPDU(self, message):
        self.rootID = message['root']
        self.cost = message['cost']
        print "RootID: ", self.rootID
        print "Cost: ", self.cost
