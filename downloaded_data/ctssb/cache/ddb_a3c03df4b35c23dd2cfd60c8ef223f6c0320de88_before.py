import json
import logging
import threading
import time
import pika

from db.db import session
from db.models import Metric, WeatherStation

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

class AgentManager(object):
    def __init__(self, cfg):
        self.connection = None
        self.channel = None
        self.cfg = cfg

    def connect(self, forever=True):
        while True:
            try:
                parameters = pika.ConnectionParameters(host=str(self.cfg['broker']),
                                                       port=int(self.cfg['port']),
                                                       vrtual_host='/')
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()

                self.add_metric() # Periodic.
                self.fan_out() # Perodic.

            except Exception as e:
                if not forever:
                    raise
                LOGGER.error("Connection failed. Trying again...")
                time.sleep(1)
                continue

    def stop(self):
        if self.connection:
            self.connection.close()

    def _publish(self, msg):
        try:
            published = self.channel.basic_publish(self.cfg['exchange'],
                                       self.cfg['routingKey'], msg,
                                       pika.BasicProperties(
                                           content_type='application/json',
                                           delivery_mode=2),  # Persistent,
                                           mandatory=True
                                      )
            if not published:
                raise
        except Exception as e:
            LOGGER.error('Error %s when sending message.', str(e))
            raise

    def publish_station(self, station):
        msg_dict = {
            "action": "add_station",
            "data": {
                "id": station.id,
                "name": station.name,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "metric_types": [mt.id for mt in station.metric_types],
            }
        }
        msg = json.dumps(msg_dict)
        self._publish(msg)

    def publish_metric(self, metric):
        msg_dict = {
            "action": "add_metric",
            "data": {
                "id": metric.id,
                "value": metric.value,
                "metric_type_id": metric.metric_type_id,
                "weather_station_id": metric.weather_station_id,
            }
        }
        msg = json.dumps(msg_dict)
        self._publish(msg)

    def add_station(self):
        # TODO(mszankin): This will add our station record to the DB.
        LOGGER.debug('Adding station...')

    def add_metric(self, period=5):
        # TODO(mszankin): This will add a new metric to the DB.
        LOGGER.debug('Adding metric...')
        threading.Timer(period, self.add_metric).start()  # Periodic loop.

    def fan_out(self, period=30):
        LOGGER.debug('Fanning out rows...')

        stations = session.query(WeatherStation).filter_by(is_sent=False).all()
        for station in stations:
            session.begin()
            try:
                self.publish_station(station)
                station.is_sent = True
                session.commit()
            except Exception as e:
                LOGGER.error('Error %s when processing station.', str(e))
                session.rollback()
                raise

        metrics = session.query(Metric).filter_by(is_sent=False).all()
        for metric in metrics:
            session.begin()
            try:
                self.publish_metric(metric)
                station.is_sent = True
                session.commit()
            except Exception as e:
                LOGGER.error('Error %s when processing metric.', str(e))
                session.rollback()
                raise

        threading.Timer(period, self.fan_out).start()  # Periodic loop.

    def run(self):
        self.add_station()
        self.connect()

def main():
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

    cfg = json.load(open("config.json"))

    manager = AgentManager(cfg)
    try:
        manager.run()
    except KeyboardInterrupt:
        manager.stop()


if __name__ == '__main__':
    main()
