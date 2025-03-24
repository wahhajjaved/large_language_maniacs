import ConfigParser
import getopt
import os
import sys
import time
from threading import Thread

import json
import urllib2

import pika
import requests

HELP_MESSAGE = \
    """haproxy-agent [--config-file=<agent.conf path>] [--push | --pull]'
Usage:
--config-file=    The path to the haproxyhq agent.conf location.
                  Default is /etc/haproxyhq/agent.conf
--push
--pull             """

def get_agent_id():
    """
    function to get the id of the haproxy agent using a rest callback
    """

    headers = {
        'content-type': 'application/json',
        'X-Auth-Token': __agent_token
    }

    body = {
        'name': 'cf_sb_haproxy_agent',
        'description': 'HAProxy Agent for generating service keys',
        'ip': '217.26.224.15',
        'authToken': __agent_token
    }

    params = json.dumps(body).encode('utf8')

    req = urllib2.Request(__server_url, data=params, headers=headers)

    response = urllib2.urlopen(req)

    resp_dict = json.loads(response.read().decode('utf8'))

    href = resp_dict['links'][0]['href']

    agent_id = href.split('/')[-1]

    f = open('/etc/haproxyhq/agent.conf', 'r')
    lines = f.readlines()
    for index, line in enumerate(lines):
        if line.startswith('id', 0, 3):
            lines[index] = 'id = %s\n' % agent_id
    f.close()

    f = open('/etc/haproxyhq/agent.conf', 'w')
    f.writelines(lines)
    f.close()

    return agent_id

def callback(channel=None, method=None, properties=None, body=None):
    """
            retrieves the current config from the backend. In case the local
            config is newer than the one retrieved by the backend, the local
            config is pushed to the server.

            params are just dummies, so that this method can be called as an AMQ
            callback
            """
    response_data = requests.get(__server_url, headers={
        'X-Auth-Token': __agent_token
    }).json()
    config_data = response_data['haProxyConfig']
    config_timestamp = response_data['configTimestamp']
    config_string = HAHQConfigurator(
        config_data=config_data).get_config_string()
    if config_timestamp > get_local_config_timestamp():
        if config_data != get_local_config_data():
            with open(__config_file_path, 'w') as config_file:
                config_file.write(config_string)
    else:
        if config_data != get_local_config_data():
            post_config()
    os.system('service haproxy reload')
    if channel.is_open == False:
            print "Channel was closed!"
    channel.basic_publish(
          exchange="",
          routing_key=properties.reply_to,
          body='OK'
      )
   # channel.basic_ack(delivery_tag = method.delivery_tag)

def connect_to_rabbit_mq():
    """
    connects the client and goes into a loop. Be aware, that this is a
    blocking command
    """
    credentials = None

    if __rabbit_mq_username is not None:
        credentials = pika.PlainCredentials(
            username=__rabbit_mq_username,
            password=__rabbit_mq_password,
        )
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=__rabbit_mq_host,
            port=__rabbit_mq_port,
            virtual_host=__rabbit_mq_virtual_host,
            credentials=credentials,
        )
    )
    channel = connection.channel()
    channel.exchange_declare(exchange=__rabbit_mq_exchange,
                             auto_delete=False,
                             exchange_type='direct')
    channel.queue_bind(exchange=__rabbit_mq_exchange,
                       queue=__rabbit_mq_queue,
                       routing_key=__rabbit_mq_exchange)
    channel.basic_qos(prefetch_count=1)
    print "Queue name is: " + __rabbit_mq_queue
    print "Channel is open. Starting to listen for messages"
    print ""
    channel.basic_consume(consumer_callback=callback,
                          queue=__rabbit_mq_queue, no_ack=True)
    channel.start_consuming()


def get_local_config_data():
    """

    :return: The content of the local haproxy.cfg
    """
    config_string = stringify_file(__config_file_path)
    if config_string:
        return HAHQConfigurator(config_string=config_string).get_config_data()
    else:
        return {
            'config': []
        }


def get_local_config_timestamp():
    """

    :return: The timestamp of last modification from the local haproxy.cfg
    """
    return int(os.stat(__config_file_path).st_mtime * 1000)


class HAHQConfigurator(object):
    """
    This class helps converting a config dict to a string which has the format
    of the HAProxy config file.

    Converting works bi-directional.

    SECTION_KEYWORDS is a list of keywords indicating the begin of a section in
    the HAProxy config file
    """

    SECTION_KEYWORDS = [
        'global',
        'defaults',
        'frontend',
        'backend',
        'listen',
        'peers',
        'mailers',
        'userlist',
        'namespace_list',
        'resolvers',
    ]

    def __init__(self, config_data=None, config_string=None):
        """
        a HAHQConfigurator can be initialized either with a dict describing the
        config, or a string formatted like the config file.

        :param config_data: dict with config data
        :param config_string: string in config file format
        """
        self.config_data = config_data if config_data else None
        self.config_string = config_string if config_string else None

    def __str__(self):
        return self.get_config_string()

    def __dir__(self):
        return self.get_config_data()

    def __eq__(self, other):
        if not isinstance(other, HAHQConfigurator) or \
                        self.get_config_data() != other.get_config_data():
            return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def get_config_string(self):
        """
        returns the config as string and converts it to string, in case it's
        only available as a dict

        :return: config string
        """
        if not self.config_string:
            self.__build_config_string()

        return self.config_string

    def get_config_data(self):
        """
        returns the config data as a dict and converts it to dict, in case it's
        only available as a string

        :return: config data
        """
        if not self.config_data:
            self.__build_config_data()

        return self.config_data

    def __build_config_string(self):
        """
        builds the config string from config data
        """
        self.config_string = ''

        if self.config_data:
            for section in self.config_data['sections']:
                self.config_string += section['section']['type'] + ' ' + \
                                      section['section']['name'] + '\n'

                for value in section['values']:
                    self.config_string += '\t' + value + '\n'

                self.config_string += '\n'

    def __build_config_data(self):
        """
        builds the config data from config string
        """
        if self.config_string:
            self.config_data = {
                'sections': []
            }

            section = dict()

            for line in self.config_string.split('\n'):
                words = line.split()

                if len(words) > 0 and words[0][0] != '#':
                    if words[0] in self.SECTION_KEYWORDS:
                        if section:
                            self.config_data['sections'].append(section)

                        section = {
                            'section': {
                                'type': words[0],
                                'name': ' '.join(words[1:]),
                            },
                            'values': [],
                        }
                    else:
                        if bool(section):
                            section['values'].append(' '.join(words))

            if bool(section):
                self.config_data['sections'].append(section)


class HAHQHeartbeatDaemon(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.setDaemon(True)

    def run(self):
	local_timestamp = get_local_config_timestamp()
	while True:
	    if local_timestamp < get_local_config_timestamp():
	        post_config()
	        local_timestamp = get_local_config_timestamp()
	    time.sleep(60)

def post_config():
    """
    sends the converted data to the server

    """
    config_timestamp = get_local_config_timestamp()
    config_data = get_local_config_data()

    request_data = {
        'haProxyConfig': config_data,
        'configTimestamp': config_timestamp,
        'agentHeartbeatTimestamp': int(round(time.time() * 1000)),
    }
    if os.popen('service haproxy status').read() == 'haproxy is running.\n':
        request_data['haproxyHeartbeatTimestamp'] = request_data[
            'agentHeartbeatTimestamp']
    requests.patch(__server_url, json=request_data, headers={
        'X-Auth-Token': __agent_token
    })
    print "Config file was edited locally. Send to server"


def stringify_file(stringable_file):
    """
    this method returns the content of a file as a string

    :param stringable_file: file path
    :return: string
    """
    with open(stringable_file, 'r') as config_file:
        return config_file.read()


def main():
    is_push = False
    is_pull = False
    agent_config_file_path = '/etc/haproxyhq/agent.conf'
    try:
        opts, args = getopt.getopt(
            args=sys.argv[1:],
            shortopts='',
            longopts=['config-file=', 'push', 'pull', 'help'])
    except getopt.GetoptError as exception:
        print(exception.msg)
        print(HELP_MESSAGE)
        sys.exit(2)
    for opt, arg in opts:
        if opt is '--help':
            print(HELP_MESSAGE)
            sys.exit()
        elif opt in '--config-file':
            agent_config_file_path = arg
        elif opt in '--push':
            is_push = True
        elif opt in '--pull':
            is_pull = True

    config = ConfigParser.RawConfigParser(allow_no_value=True)

    config.readfp(file(agent_config_file_path))

    __agent_id = config.get('agent', 'id')
    global __agent_id
    __agent_token = config.get('agent', 'token')
    global __agent_token
    __config_file_path = config.get('haproxy', 'config_file')
    global __config_file_path
    __rabbit_mq_host = config.get('rabbitmq', 'host')
    global __rabbit_mq_host
    __rabbit_mq_port = config.getint('rabbitmq', 'port')
    global __rabbit_mq_port
    __rabbit_mq_virtual_host = config.get('rabbitmq', 'virtualhost')
    global __rabbit_mq_virtual_host
    __rabbit_mq_exchange = config.get('rabbitmq', 'exchange')
    global __rabbit_mq_exchange
    __rabbit_mq_username = config.get('rabbitmq', 'username')
    global __rabbit_mq_username
    __rabbit_mq_password = config.get('rabbitmq', 'password')
    global __rabbit_mq_password
    __rabbit_mq_queue = config.get('rabbitmq', 'queue')
    global __rabbit_mq_queue
    server_protocol = config.get('server', 'protocol')
    server_address = config.get('server', 'address')
    server_port = config.get('server', 'port')
    server_api_endpoint = config.get('server', 'api_endpoint')
    __server_url = \
        server_protocol + '://' + \
        server_address + ':' + \
        server_port + '/' + \
        server_api_endpoint + '/' + __agent_id
    global __server_url

    if not __agent_id:
        __agent_id = get_agent_id()
	__server_url = __server_url + __agent_id
	post_config()

    try:
        if is_push:
            post_config()
        elif is_pull:
            callback()
        else:
            HAHQHeartbeatDaemon().start()
            connect_to_rabbit_mq()
    except KeyboardInterrupt:
        print 'HAProxyHQ/Agent stopped'
        exit(0)


if __name__ == '__main__':
    main()
