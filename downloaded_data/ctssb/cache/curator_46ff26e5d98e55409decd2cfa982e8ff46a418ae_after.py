import time
import os
import shutil
import tempfile
import random
import string
from datetime import timedelta, datetime, date

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError

from unittest import SkipTest, TestCase
from mock import Mock

client = None

DATEMAP = {
    'months': '%Y.%m',
    'weeks': '%Y.%W',
    'days': '%Y.%m.%d',
    'hours': '%Y.%m.%d.%H',
}

host, port = os.environ.get('TEST_ES_SERVER', 'localhost:9200').split(':')
port = int(port) if port else 9200

def get_client():
    global client
    if client is not None:
        return client

    client = Elasticsearch([os.environ.get('TEST_ES_SERVER', {})], timeout=300)

    # wait for yellow status
    for _ in range(100):
        time.sleep(.1)
        try:
            client.cluster.health(wait_for_status='yellow')
            return client
        except ConnectionError:
            continue
    else:
        # timeout
        raise SkipTest("Elasticsearch failed to start.")

def setup():
    get_client()

class Args(dict):
    def __getattr__(self, att_name):
        return self.get(att_name, None)

class CuratorTestCase(TestCase):
    def setUp(self):
        super(CuratorTestCase, self).setUp()
        self.client = get_client()

        args = {}
        args['host'], args['port'] = host, port
        args['time_unit'] = 'days'
        args['prefix'] = 'logstash-'
        self.args = args
        dirname = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        # This will create a psuedo-random temporary directory on the machine
        # which runs the unit tests, but NOT on the machine where elasticsearch
        # is running. This means tests may fail if run against remote instances
        # unless you explicitly set `self.args['location']` to a proper spot
        # on the target machine.
        self.args['location'] = tempfile.mkdtemp(suffix=dirname)
        self.args['repository'] = 'TEST_REPOSITORY'
        if not os.path.exists(self.args['location']):
            os.makedirs(self.args['location'])

    def tearDown(self):
        self.delete_repositories()
        self.client.indices.delete(index='*')
        self.client.indices.delete_template(name='*', ignore=404)
        if os.path.exists(self.args['location']):
            shutil.rmtree(self.args['location'])

    def parse_args(self):
        return Args(self.args)

    def create_indices(self, count, unit=None):
        now = datetime.utcnow()
        unit = unit if unit else self.args['time_unit']
        format = DATEMAP[unit]
        if not unit == 'months':
            step = timedelta(**{unit: 1})
            for x in range(count):
                self.create_index(self.args['prefix'] + now.strftime(format), wait_for_yellow=False)
                now -= step
        else: # months
            now = date.today()
            d = date(now.year, now.month, 1)
            self.create_index(self.args['prefix'] + now.strftime(format), wait_for_yellow=False)

            for i in range(1, count):
                if d.month == 1:
                    d = date(d.year-1, 12, 1)
                else:
                    d = date(d.year, d.month-1, 1)
                self.create_index(self.args['prefix'] + datetime(d.year, d.month, 1).strftime(format), wait_for_yellow=False)

        self.client.cluster.health(wait_for_status='yellow')

    def create_index(self, name, shards=1, wait_for_yellow=True):
        self.client.indices.create(
            index=name,
            body={'settings': {'number_of_shards': shards, 'number_of_replicas': 0}}
        )
        if wait_for_yellow:
            self.client.cluster.health(wait_for_status='yellow')

    def create_repository(self):
        body = {'type':'fs', 'settings':{'location':self.args['location']}}
        self.client.snapshot.create_repository(repository=self.args['repository'], body=body)

    def delete_repositories(self):
        result = self.client.snapshot.get_repository(repository='_all')
        for repo in result:
            self.client.snapshot.delete_repository(repository=repo)
