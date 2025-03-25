import sys
import os
import datetime
import logging

from threading import Thread
from tcpServer import TcpServer

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from zmq.utils import jsonapi

import settings

utils.setup_logging() 
_log = logging.getLogger(__name__)

def fan_entity(config_path, **kwargs):
    config = utils.load_config(config_path)
    AGENT_ID = config.get("agent_id")

    SPEED_MAPPINGS = {
        'slow': 175,
        'medium': 90,
        'fast': 7
    }

    class FanEntity(Agent):
        def __init__(self, **kwargs):
            super(FanEntity, self).__init__(**kwargs)

            self.speed = 'slow'
            self.tcpServer = TcpServer(config.get('port'), self)
            Thread(target=self.tcpServer.startServer).start()

        def process_data(self, msg):
            components = msg.split('&')
            data = {}
            # Extract individual fields from the message and create to dictionary for publishing
            for component in components:
                if '=' in component:
                    (key, value) = component.split('=')
                    data.update({key: value})
            self.status_push(data)

        @Core.periodic(settings.HEARTBEAT_PERIOD)
        def publish_status(self):
          self.status_push({'speed': self.speed})

        def status_push(self, data):
            prefix = settings.TYPE_PREFIX + '/' + AGENT_ID + '/data'
            headers = {
                headers_mod.FROM: AGENT_ID,
                headers_mod.CONTENT_TYPE: headers_mod.CONTENT_TYPE.JSON,
                headers_mod.DATE: datetime.datetime.today().isoformat(),
                "Location": config.get('location')
            }
            self.publish_all(data, prefix, headers)
            _log.debug("publishing status: %s", str(data))
 
        def publish_all(self, data, prefix, headers):
            for item in data.keys():
                topic = prefix + '/' + item
                self.vip.pubsub.publish('pubsub', topic, headers, jsonapi.dumps(data[item]))

        def set_speed(self, speed):
            self.speed = speed
            if self.tcpServer.isClientConnected():
                self.tcpServer.sendData("speed={value}".format(value=SPEED_MAPPINGS[speed]))

        @PubSub.subscribe('pubsub', settings.TYPE_PREFIX + '/' + AGENT_ID + '/operations/speed')
        def on_set_speed(self, peer, sender, bus, topic, headers, message):
            print 'Fan Entity got\nTopic: {topic}, {headers}, Message: {message}'.format(topic=topic, headers=headers, message=message)
            self.set_speed(jsonapi.loads(message))
  
    return FanEntity(**kwargs)


def main(argv=sys.argv):
    """Main method called by the platform"""
    utils.vip_main(fan_entity)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
