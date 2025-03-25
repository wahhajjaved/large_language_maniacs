import threading
from detector import *
from event import *
from gps import GPS

class TestDetector(Detector):
    @on_event
    def wait_input(self):
        text = input("> ")
        print("RECEIVED INPUT")
        return Event(1, GPS.to_tuple("41.559437 -8.403232"), "input", False, time.time(), 10000000, text )

    def run(self):
        while True:
            self.wait_input()
