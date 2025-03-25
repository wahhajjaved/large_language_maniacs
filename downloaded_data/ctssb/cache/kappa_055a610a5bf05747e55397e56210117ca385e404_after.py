# Copyright (c) 2014, 2015 Mitch Garnaat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import yaml
import time
import os
import shutil

import kappa.function
import kappa.restapi
import kappa.event_source
import kappa.policy
import kappa.role
import kappa.awsclient

import placebo

LOG = logging.getLogger(__name__)

DebugFmtString = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
InfoFmtString = '...%(message)s'


class Context(object):

    def __init__(self, config_file, environment=None,
                 debug=False, recording_path=None):
        if debug:
            self.set_logger('kappa', logging.DEBUG)
        else:
            self.set_logger('kappa', logging.INFO)
        self._load_cache()
        self.config = yaml.load(config_file)
        self.environment = environment
        profile = self.config['environments'][self.environment]['profile']
        region = self.config['environments'][self.environment]['region']
        self.session = kappa.awsclient.create_session(profile, region)
        if recording_path:
            self.pill = placebo.attach(self.session, recording_path)
            self.pill.record()
        self.policy = kappa.policy.Policy(
            self, self.config['environments'][self.environment])
        self.role = kappa.role.Role(
            self, self.config['environments'][self.environment])
        self.function = kappa.function.Function(
            self, self.config['lambda'])
        if 'restapi' in self.config:
            self.restapi = kappa.restapi.RestApi(
                self, self.config['restapi'])
        else:
            self.restapi = None
        self.event_sources = []
        self._create_event_sources()

    def _load_cache(self):
        self.cache = {}
        if os.path.isdir('.kappa'):
            cache_file = os.path.join('.kappa', 'cache')
            if os.path.isfile(cache_file):
                with open(cache_file, 'r') as fp:
                    self.cache = yaml.load(fp)

    def _delete_cache(self):
        if os.path.isdir('.kappa'):
            shutil.rmtree('.kappa')
            self.cache = {}

    def _save_cache(self):
        if not os.path.isdir('.kappa'):
            os.mkdir('.kappa')
        cache_file = os.path.join('.kappa', 'cache')
        with open(cache_file, 'w') as fp:
            yaml.dump(self.cache, fp)

    def get_cache_value(self, key):
        return self.cache.setdefault(self.environment, dict()).get(key)

    def set_cache_value(self, key, value):
        self.cache.setdefault(
            self.environment, dict())[key] = value.encode('utf-8')
        self._save_cache()

    @property
    def name(self):
        return self.config.get('name', os.path.basename(os.getcwd()))

    @property
    def profile(self):
        return self.config['environments'][self.environment]['profile']

    @property
    def region(self):
        return self.config['environments'][self.environment]['region']

    @property
    def record(self):
        return self.config.get('record', False)

    @property
    def lambda_config(self):
        return self.config.get('lambda')

    @property
    def test_dir(self):
        return self.config.get('tests', '_tests')

    @property
    def source_dir(self):
        return self.config.get('source', '_src')

    @property
    def unit_test_runner(self):
        return self.config.get('unit_test_runner',
                               'nosetests . ../{}/unit/'.format(self.test_dir))

    @property
    def exec_role_arn(self):
        return self.role.arn

    def debug(self):
        self.set_logger('kappa', logging.DEBUG)

    def set_logger(self, logger_name, level=logging.INFO):
        """
        Convenience function to quickly configure full debug output
        to go to the console.
        """
        log = logging.getLogger(logger_name)
        log.setLevel(level)

        ch = logging.StreamHandler(None)
        ch.setLevel(level)

        # create formatter
        if level == logging.INFO:
            formatter = logging.Formatter(InfoFmtString)
        else:
            formatter = logging.Formatter(DebugFmtString)

        # add formatter to ch
        ch.setFormatter(formatter)

        # add ch to logger
        log.addHandler(ch)

    def _create_event_sources(self):
        env_cfg = self.config['environments'][self.environment]
        if 'event_sources' in env_cfg:
            for event_source_cfg in env_cfg['event_sources']:
                _, _, svc, _ = event_source_cfg['arn'].split(':', 3)
                if svc == 'kinesis':
                    self.event_sources.append(
                        kappa.event_source.KinesisEventSource(
                            self, event_source_cfg))
                elif svc == 's3':
                    self.event_sources.append(kappa.event_source.S3EventSource(
                        self, event_source_cfg))
                elif svc == 'sns':
                    self.event_sources.append(
                        kappa.event_source.SNSEventSource(
                            self, event_source_cfg))
                elif svc == 'dynamodb':
                    self.event_sources.append(
                        kappa.event_source.DynamoDBStreamEventSource(
                            self, event_source_cfg))
                else:
                    msg = 'Unknown event source: %s' % event_source_cfg['arn']
                    raise ValueError(msg)

    def add_event_sources(self):
        for event_source in self.event_sources:
            event_source.add(self.function)

    def update_event_sources(self):
        for event_source in self.event_sources:
            event_source.update(self.function)

    def list_event_sources(self):
        event_sources = []
        for event_source in self.event_sources:
            event_sources.append({'arn': event_source.arn,
                                  'starting_position': event_source.starting_position,
                                  'batch_size': event_source.batch_size,
                                  'enabled': event_source.enabled})
        return event_sources

    def enable_event_sources(self):
        for event_source in self.event_sources:
            event_source.enable(self.function)

    def disable_event_sources(self):
        for event_source in self.event_sources:
            event_source.disable(self.function)

    def create(self):
        if self.policy:
            self.policy.create()
        if self.role:
            self.role.create()
        # There is a consistency problem here.
        # If you don't wait for a bit, the function.create call
        # will fail because the policy has not been attached to the role.
        LOG.debug('Waiting for policy/role propogation')
        time.sleep(5)
        self.function.create()
        self.add_event_sources()

    def deploy(self):
        if self.policy:
            self.policy.deploy()
        if self.role:
            self.role.create()
        self.function.deploy()
        if self.restapi:
            self.restapi.deploy()

    def invoke(self, data):
        return self.function.invoke(data)

    def unit_tests(self):
        # run any unit tests
        unit_test_path = os.path.join(self.test_dir, 'unit')
        if os.path.exists(unit_test_path):
            os.chdir(self.source_dir)
            print('running unit tests')
            pipe = os.popen(self.unit_test_runner, 'r')
            print(pipe.read())

    def test(self):
        return self.unit_tests()

    def dryrun(self):
        return self.function.dryrun()

    def invoke_async(self):
        return self.function.invoke_async()

    def tail(self):
        return self.function.tail()

    def delete(self):
        for event_source in self.event_sources:
            event_source.remove(self.function)
        self.function.log.delete()
        self.function.delete()
        if self.restapi:
            self.restapi.delete()
        time.sleep(5)
        if self.role:
            self.role.delete()
        time.sleep(5)
        if self.policy:
            self.policy.delete()
        self._delete_cache()

    def status(self):
        status = {}
        if self.policy:
            status['policy'] = self.policy.status()
        else:
            status['policy'] = None
        if self.role:
            status['role'] = self.role.status()
        else:
            status['role'] = None
        status['function'] = self.function.status()
        status['event_sources'] = []
        if self.event_sources:
            for event_source in self.event_sources:
                status['event_sources'].append(
                    event_source.status(self.function))
        return status
