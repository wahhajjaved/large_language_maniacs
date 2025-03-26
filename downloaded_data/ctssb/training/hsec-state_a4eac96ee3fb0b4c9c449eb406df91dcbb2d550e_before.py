#!/usr/bin/env python3.4
"""
Receive events, decide what to do. Based on zguide.
"""
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import requests             # for webhooks
import configparser         # for reading config
import time
import comms.comms as comms # for getting a channel to the sensor


def main():
    """ main method """

    # get key for ifttt maker recipe
    config = configparser.ConfigParser()
    config.read('hsec-state.cfg')
    key=config['maker.ifttt.com']['Key']

    # create object for communication to sensor system
    trigger_comms = comms.SubChannel("tcp://localhost:5563", ['events','state'])

    # create object for communication to alert system
    alert_comms = comms.PubChannel("tcp://*:5564")


    try:
        while True:
            # Read envelope and address from queue
            rv = trigger_comms.get()
            if rv is not None:
                # there has been an event
                [address, contents] = rv
                print("Event: [%s] %s" % (address, contents))

                alert_comms.send("state",["Initial state"])
                #post = "https://maker.ifttt.com/trigger/front_door_opened/with/key/" + key
                #print("not really..." + post)
                #print(requests.post(post))
            else:
                # no events waiting for processing
                time.sleep(0.1)

            #print("doing stuff")
            #time.sleep(1)
            # trigger an event

    except KeyboardInterrupt:
        pass
        #q.join(timeout=1) # this probably belongs in the comms module

    # clean up zmq connection
    subscriber.close()
    context.term()

if __name__ == "__main__":
    main()
