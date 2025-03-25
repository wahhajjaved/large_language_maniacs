from maxclient import MaxClient

import argparse
import ConfigParser
import json
import pika
import pymongo
import requests
import os
import re
import sys


class InitAndPurgeRabbitServer(object):  # pragma: no cover

    def __init__(self, options, quiet=False):
        self.quiet = quiet
        self.options = options

        self.config = ConfigParser.ConfigParser()
        self.config.read(self.options.configfile)

        try:
            self.cluster = self.config.get('app:main', 'mongodb.cluster')
            self.standaloneserver = self.config.get('app:main', 'mongodb.url')
            self.clustermembers = self.config.get('app:main', 'mongodb.hosts')
            self.dbname = self.config.get('app:main', 'mongodb.db_name')
            self.replicaset = self.config.get('app:main', 'mongodb.replica_set')
            self.rabbitmq_settings = self.config.get('app:main', 'max.rabbitmq')

        except:
            print('You must provide a valid configuration .ini file.')
            sys.exit()

    def pika_connection_params(self):
        host, port = re.search(r'\s*(\w+):?(\d*)\s*', self.rabbitmq_settings).groups()
        params = {'host': host}
        if port:
            params['port'] = int(port)
        return params

    def run(self):
        # Connect to the database
        if not self.cluster in ['true', 'True', '1', 1]:
            db_uri = self.standaloneserver
            conn = pymongo.MongoClient(db_uri)
        else:
            hosts = self.clustermembers
            replica_set = self.replicaset
            conn = pymongo.MongoReplicaSetClient(hosts, replicaSet=replica_set)

        db = conn[self.dbname]
        pika_params = self.pika_connection_params()
        rabbit_con = pika.BlockingConnection(
            pika.ConnectionParameters(**pika_params)
        )
        channel = rabbit_con.channel()

        current_conversations = set([unicode(conv['_id']) for conv in db.conversations.find({}, {'_id': 1})])
        req = requests.get('http://{}:15672/api/exchanges'.format(pika_params['host']), auth=('victor.fernandez', ''))
        if req.status_code != 200:
            print('Error getting current exchanges from RabbitMQ server.')
        current_exchanges = req.json()
        current_exchanges = set([exchange.get('name') for exchange in current_exchanges])

        to_add = current_conversations - current_exchanges
        to_delete = current_exchanges - current_conversations

        # Exclude the default Rabbit exchange
        to_delete = to_delete - set([u''])

        # Delete orphaned exchanges in RabbitMQ
        for exdel in to_delete:
            if not exdel.startswith('amq') and not exdel.startswith('new'):
                channel.exchange_delete(exdel)
                print("Added exchange {}".format(exdel))

        # Add missing exchanges in RabbitMQ
        for exadd in to_add:
            channel.exchange_declare(exchange=exadd,
                                     durable=True,
                                     type='fanout')
            print("Added exchange {}".format(exadd))

        # Create default exchange if not created yet
        channel.exchange_declare(exchange='new',
                                 durable=True,
                                 type='direct')
        print("Declared 'new' exchange.")

        # Create the default push queue
        channel.queue_declare("push", durable=True)
        print("Declared 'push' queue.")

        # Create twitter exchange if not created yet
        channel.exchange_declare(exchange='twitter',
                                 durable=True,
                                 type='fanout')
        print("Declared 'twitter' exchange.")
        # Create the default twitter queue
        channel.queue_declare("twitter", durable=True)
        print("Declared 'twitter' queue.")
        channel.queue_declare("tweety_restart", durable=True)
        print("Declared 'tweety_restart' queue.")
        channel.queue_bind(exchange="twitter", queue="twitter")
        print("Binded 'twitter' queue to 'twitter' exchange.")

        # Check if the restricted user and token is set
        settings_file = '{}/.max_restricted'.format(self.config.get('app:main', 'config_directory'))
        if os.path.exists(settings_file):
            settings = json.loads(open(settings_file).read())
        else:
            settings = {}

        if 'token' not in settings or 'username' not in settings:
            maxclient = MaxClient(url=self.config.get('app:main', 'max.server'), oauth_server=self.config.get('app:main', 'max.oauth_server'))
            settings['token'] = maxclient.login()
            settings['username'] = maxclient.getActor()

            open(settings_file, 'w').write(json.dumps(settings, indent=4, sort_keys=True))

        print("Initialized and purged RabbitMQ server.")


def main(argv=sys.argv, quiet=False):  # pragma: no cover
    description = "Initialize and purge if needed RabbitMQ development server."
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('-c', '--config',
                      dest='configfile',
                      type=str,
                      required=True,
                      help=("Configuration file (e.g max.ini)"))
    options = parser.parse_args()

    command = InitAndPurgeRabbitServer(options, quiet)
    return command.run()
