# Copyright (c) 2014 AnsibleWorks, Inc.
# All Rights Reserved.

# Python
import base64
import contextlib
import datetime
import json
import os
import random
import shutil
import sys
import tempfile
import time
from multiprocessing import Process
from subprocess import Popen

# PyYAML
import yaml

# Django
from django.conf import settings, UserSettingsHolder
from django.contrib.auth.models import User
import django.test
from django.test.client import Client
from django.test.utils import override_settings

# AWX
from awx.main.models import *
from awx.main.backend import LDAPSettings
from awx.main.management.commands.run_callback_receiver import CallbackReceiver
from awx.main.management.commands.run_task_system import run_taskmanager
from awx.main.utils import get_ansible_version
from awx.main.task_engine import TaskEngager as LicenseWriter


class BaseTestMixin(object):
    '''
    Mixin with shared code for use by all test cases.
    '''

    def setUp(self):
        super(BaseTestMixin, self).setUp()
        self.object_ctr = 0
        # Save sys.path before tests.
        self._sys_path = [x for x in sys.path]
        # Save os.environ before tests.
        self._environ = dict(os.environ.items())
        # Capture current directory to change back after each test.
        self._cwd = os.getcwd()
        # Capture list of temp files/directories created during tests.
        self._temp_paths = []
        self._current_auth = None
        self._user_passwords = {}
        self.ansible_version = get_ansible_version()
        self.assertNotEqual(self.ansible_version, 'unknown')
        # Wrap settings so we can redefine them within each test.
        self._wrapped = settings._wrapped
        settings._wrapped = UserSettingsHolder(settings._wrapped)
        # Set all AUTH_LDAP_* settings to defaults to avoid using LDAP for
        # tests unless expicitly configured.
        for name, value in LDAPSettings.defaults.items():
            if name == 'SERVER_URI':
                value = ''
            setattr(settings, 'AUTH_LDAP_%s' % name, value)
        # Pass test database settings in environment for use by any management
        # commands that run from tests.
        for opt in ('ENGINE', 'NAME', 'USER', 'PASSWORD', 'HOST', 'PORT'):
            os.environ['AWX_TEST_DATABASE_%s' % opt] = settings.DATABASES['default'][opt]
        # Set flag so that task chain works with unit tests.
        settings.CELERY_UNIT_TEST = True
        settings.SYSTEM_UUID='00000000-0000-0000-0000-000000000000'
        settings.BROKER_URL='redis://localhost:16379/'
        
        # Create unique random consumer and queue ports for zeromq callback.
        if settings.CALLBACK_CONSUMER_PORT:
            callback_port = random.randint(55700, 55799)
            settings.CALLBACK_CONSUMER_PORT = 'tcp://127.0.0.1:%d' % callback_port
            callback_queue_path = '/tmp/callback_receiver_test_%d.ipc' % callback_port
            self._temp_paths.append(callback_queue_path)
            settings.CALLBACK_QUEUE_PORT = 'ipc://%s' % callback_queue_path
            settings.TASK_COMMAND_PORT = 'ipc:///tmp/task_command_receiver_%d.ipc' % callback_port
        # Disable socket notifications for unit tests.
        settings.SOCKETIO_NOTIFICATION_PORT = None
        # Make temp job status directory for unit tests.
        job_status_dir = tempfile.mkdtemp()
        self._temp_paths.append(job_status_dir)
        settings.JOBOUTPUT_ROOT = os.path.abspath(job_status_dir)
        settings.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'unittests'
            }
        }
        self._start_time = time.time()

    def tearDown(self):
        super(BaseTestMixin, self).tearDown()
        # Restore sys.path after tests.
        sys.path = self._sys_path
        # Restore os.environ after tests.
        for k,v in self._environ.items():
            if os.environ.get(k, None) != v:
                os.environ[k] = v
        for k,v in os.environ.items():
            if k not in self._environ.keys():
                del os.environ[k]
        # Restore current directory after each test.
        os.chdir(self._cwd)
        # Cleanup temp files/directories created during tests.
        for project_dir in self._temp_paths:
            if os.path.exists(project_dir):
                if os.path.isdir(project_dir):
                    shutil.rmtree(project_dir, True)
                else:
                    os.remove(project_dir)
        # Restore previous settings after each test.
        settings._wrapped = self._wrapped

    def create_test_license_file(self, instance_count=10000):
        writer = LicenseWriter( 
           company_name='AWX',
           contact_name='AWX Admin',
           contact_email='awx@example.com',
           license_date=int(time.time() + 3600),
           instance_count=instance_count,
        )
        handle, license_path = tempfile.mkstemp(suffix='.json')
        os.close(handle)
        writer.write_file(license_path)
        self._temp_paths.append(license_path)
        os.environ['AWX_LICENSE_FILE'] = license_path

    def assertElapsedLessThan(self, seconds):
        elapsed = time.time() - self._start_time
        self.assertTrue(elapsed < seconds, 'elapsed time of %0.3fs is greater than %0.3fs' % (elapsed, seconds))

    @contextlib.contextmanager
    def current_user(self, user_or_username, password=None):
        try:
            if isinstance(user_or_username, User):
                username = user_or_username.username
            else:
                username = user_or_username
            password = password or self._user_passwords.get(username)
            previous_auth = self._current_auth
            if username is None:
                self._current_auth = None
            else:
                self._current_auth = (username, password)
            yield
        finally:
            self._current_auth = previous_auth

    def make_user(self, username, password=None, super_user=False):
        user = None
        password = password or username
        if super_user:
            user = User.objects.create_superuser(username, "%s@example.com", password)
        else:
            user = User.objects.create_user(username, "%s@example.com", password)
        # New user should have no auth tokens by default.
        self.assertFalse(user.auth_tokens.count())
        self._user_passwords[user.username] = password
        return user

    def make_organizations(self, created_by, count=1):
        results = []
        for x in range(0, count):
            self.object_ctr = self.object_ctr + 1
            results.append(Organization.objects.create(
                name="org%s-%s" % (x, self.object_ctr), description="org%s" % x, created_by=created_by
            ))
        return results

    def make_project(self, name, description='', created_by=None,
                     playbook_content='', role_playbooks=None, unicode_prefix=True):
        if not os.path.exists(settings.PROJECTS_ROOT):
            os.makedirs(settings.PROJECTS_ROOT)
        # Create temp project directory.
        if unicode_prefix:
            tmp_prefix = u'\u2620tmp'
        else:
            tmp_prefix = 'tmp'
        project_dir = tempfile.mkdtemp(prefix=tmp_prefix, dir=settings.PROJECTS_ROOT)
        self._temp_paths.append(project_dir)
        # Create temp playbook in project (if playbook content is given).
        if playbook_content:
            handle, playbook_path = tempfile.mkstemp(suffix=u'\u2620.yml',
                                                     dir=project_dir)
            test_playbook_file = os.fdopen(handle, 'w')
            test_playbook_file.write(playbook_content.encode('utf-8'))
            test_playbook_file.close()
            # Role playbooks are specified as a dict of role name and the
            # content of tasks/main.yml playbook.
            role_playbooks = role_playbooks or {}
            for role_name, role_playbook_content in role_playbooks.items():
                role_tasks_dir = os.path.join(project_dir, 'roles', role_name, 'tasks')
                if not os.path.exists(role_tasks_dir):
                    os.makedirs(role_tasks_dir)
                role_tasks_playbook_path = os.path.join(role_tasks_dir, 'main.yml')
                with open(role_tasks_playbook_path, 'w') as f:
                    f.write(role_playbook_content)
        return Project.objects.create(
            name=name, description=description,
            local_path=os.path.basename(project_dir), created_by=created_by,
            #scm_type='git',  default_playbook='foo.yml',
        )

    def make_projects(self, created_by, count=1, playbook_content='',
                      role_playbooks=None, unicode_prefix=False):
        results = []
        for x in range(0, count):
            self.object_ctr = self.object_ctr + 1
            results.append(self.make_project(
                name="proj%s-%s" % (x, self.object_ctr),
                description=u"proj%s" % x,
                created_by=created_by,
                playbook_content=playbook_content,
                role_playbooks=role_playbooks,
                unicode_prefix=unicode_prefix
            ))
        return results

    def setup_instances(self):
        instance = Instance(uuid=settings.SYSTEM_UUID, primary=True, hostname='127.0.0.1')
        instance.save()

    def setup_users(self, just_super_user=False):
        # Create a user.
        self.super_username  = 'admin'
        self.super_password  = 'admin'
        self.normal_username = 'normal'
        self.normal_password = 'normal'
        self.other_username  = 'other'
        self.other_password  = 'other'
        self.nobody_username = 'nobody'
        self.nobody_password = 'nobody'

        self.super_django_user  = self.make_user(self.super_username,  self.super_password, super_user=True)

        if not just_super_user:
            self.normal_django_user = self.make_user(self.normal_username, self.normal_password, super_user=False)
            self.other_django_user  = self.make_user(self.other_username,  self.other_password, super_user=False)
            self.nobody_django_user  = self.make_user(self.nobody_username,  self.nobody_password, super_user=False)

    def get_super_credentials(self):
        return (self.super_username, self.super_password)

    def get_normal_credentials(self):
        return (self.normal_username, self.normal_password)

    def get_other_credentials(self):
        return (self.other_username, self.other_password)

    def get_nobody_credentials(self):
        # here is a user without any permissions...
        return (self.nobody_username, self.nobody_password)

    def get_invalid_credentials(self):
        return ('random', 'combination')
        
    def _generic_rest(self, url, data=None, expect=204, auth=None, method=None,
                      data_type=None, accept=None, remote_addr=None,
                      return_response_object=False):
        assert method is not None
        method_name = method.lower()
        #if method_name not in ('options', 'head', 'get', 'delete'):
        #    assert data is not None
        client_kwargs = {}
        if accept:
            client_kwargs['HTTP_ACCEPT'] = accept
        if remote_addr is not None:
            client_kwargs['REMOTE_ADDR'] = remote_addr
        auth = auth or self._current_auth
        if auth:
            # Dict is only used to test case when both Authorization and
            # X-Auth-Token headers are passed.
            if isinstance(auth, dict):
                basic = auth.get('basic', ())
                if basic:
                    basic_auth = base64.b64encode('%s:%s' % (basic[0], basic[1]))
                    basic_auth = basic_auth.decode('ascii')
                    client_kwargs['HTTP_AUTHORIZATION'] = 'Basic %s' % basic_auth
                token = auth.get('token', '')
                if token and not basic:
                    client_kwargs['HTTP_AUTHORIZATION'] = 'Token %s' % token
                elif token:
                    client_kwargs['HTTP_X_AUTH_TOKEN'] = 'Token %s' % token
            elif isinstance(auth, (list, tuple)):
                #client.login(username=auth[0], password=auth[1])
                basic_auth = base64.b64encode('%s:%s' % (auth[0], auth[1]))
                basic_auth = basic_auth.decode('ascii')
                client_kwargs['HTTP_AUTHORIZATION'] = 'Basic %s' % basic_auth
            elif isinstance(auth, basestring):
                client_kwargs['HTTP_AUTHORIZATION'] = 'Token %s' % auth
        client = Client(**client_kwargs)
        method = getattr(client, method_name)
        response = None
        if data is not None:
            data_type = data_type or 'json'
            if data_type == 'json':
                response = method(url, json.dumps(data), 'application/json')
            elif data_type == 'yaml':
                response = method(url, yaml.safe_dump(data), 'application/yaml')
            else:
                self.fail('Unsupported data_type %s' % data_type)
        else:
            response = method(url)

        self.assertFalse(response.status_code == 500 and expect != 500,
                         'Failed (500): %s' % response.content)
        if expect is not None:
            assert response.status_code == expect, "expected status %s, got %s for url=%s as auth=%s: %s" % (expect, response.status_code, url, auth, response.content)
        if method_name == 'head':
            self.assertFalse(response.content)
        #if return_response_object:
        #    return response
        if response.status_code not in [ 204, 405 ] and method_name != 'head' and response.content:
            # no JSON responses in these at least for now, 409 should probably return some (FIXME)
            if response['Content-Type'].startswith('application/json'):
                obj = json.loads(response.content)
            elif response['Content-Type'].startswith('application/yaml'):
                obj = yaml.safe_load(response.content)
            else:
                self.fail('Unsupport response content type %s' % response['Content-Type'])
        else:
            obj = {}

        # Create a new subclass of object type and attach the response instance
        # to it (to allow for checking response headers).
        if isinstance(obj, dict):
            return type('DICT', (dict,), {'response': response})(obj.items())
        elif isinstance(obj, (tuple, list)):
            return type('LIST', (list,), {'response': response})(iter(obj))
        else:
            return obj

    def options(self, url, expect=200, auth=None, accept=None,
                remote_addr=None):
        return self._generic_rest(url, data=None, expect=expect, auth=auth,
                                  method='options', accept=accept,
                                  remote_addr=remote_addr)

    def head(self, url, expect=200, auth=None, accept=None, remote_addr=None):
        return self._generic_rest(url, data=None, expect=expect, auth=auth,
                                  method='head', accept=accept,
                                  remote_addr=remote_addr)
 
    def get(self, url, expect=200, auth=None, accept=None, remote_addr=None):
        return self._generic_rest(url, data=None, expect=expect, auth=auth,
                                  method='get', accept=accept,
                                  remote_addr=remote_addr)

    def post(self, url, data, expect=204, auth=None, data_type=None,
             accept=None, remote_addr=None):
        return self._generic_rest(url, data=data, expect=expect, auth=auth,
                                  method='post', data_type=data_type,
                                  accept=accept,
                                  remote_addr=remote_addr)

    def put(self, url, data, expect=200, auth=None, data_type=None,
            accept=None, remote_addr=None):
        return self._generic_rest(url, data=data, expect=expect, auth=auth,
                                  method='put', data_type=data_type,
                                  accept=accept, remote_addr=remote_addr)

    def patch(self, url, data, expect=200, auth=None, data_type=None,
              accept=None, remote_addr=None):
        return self._generic_rest(url, data=data, expect=expect, auth=auth,
                                  method='patch', data_type=data_type,
                                  accept=accept, remote_addr=remote_addr)

    def delete(self, url, expect=201, auth=None, data_type=None, accept=None,
               remote_addr=None):
        return self._generic_rest(url, data=None, expect=expect, auth=auth,
                                  method='delete', accept=accept,
                                  remote_addr=remote_addr)

    def get_urls(self, collection_url, auth=None):
        # TODO: this test helper function doesn't support pagination
        data = self.get(collection_url, expect=200, auth=auth)
        return [item['url'] for item in data['results']]

    def check_invalid_auth(self, url, data=None, methods=None):
        '''
        Check various methods of accessing the given URL with invalid
        authentication credentials.
        '''
        data = data or {}
        methods = methods or ('options', 'head', 'get')
        for auth in [(None,), ('invalid', 'password')]:
            with self.current_user(*auth):
                for method in methods:
                    f = getattr(self, method)
                    if method in ('post', 'put', 'patch'):
                        f(url, data, expect=401)
                    else:
                        f(url, expect=401)

    def check_pagination_and_size(self, data, desired_count, previous=False,
                                  next=False):
        self.assertTrue('results' in data)
        self.assertEqual(data['count'], desired_count)
        if previous:
            self.assertTrue(data['previous'])
        else:
            self.assertFalse(data['previous'])
        if next:
            self.assertTrue(data['next'])
        else:
            self.assertFalse(data['next'])

    def check_list_ids(self, data, queryset, check_order=False):
        data_ids = [x['id'] for x in data['results']]
        qs_ids = queryset.values_list('pk', flat=True)
        if check_order:
            self.assertEqual(tuple(data_ids), tuple(qs_ids))
        else:
            self.assertEqual(set(data_ids), set(qs_ids))

    def check_get_list(self, url, user, qs, fields=None, expect=200,
                       check_order=False, offset=None, limit=None):
        '''
        Check that the given list view URL returns results for the given user
        that match the given queryset.
        '''
        offset = offset or 0
        with self.current_user(user):
            if expect == 400:
                self.options(url, expect=200)
            else:
                self.options(url, expect=expect)
            self.head(url, expect=expect)
            response = self.get(url, expect=expect)
        if expect != 200:
            return
        total = qs.count()
        if limit is not None:
            if limit > 0:
                qs = qs[offset:offset+limit]
            else:
                qs = qs.none()
        self.check_pagination_and_size(response, total, offset > 0,
                                       limit and ((offset + limit) < total))
        self.check_list_ids(response, qs, check_order)
        if fields:
            for obj in response['results']:
                returned_fields = set(obj.keys())
                expected_fields = set(fields)
                msg = ''
                not_expected = returned_fields - expected_fields
                if not_expected:
                    msg += 'fields %s not expected ' % ', '.join(not_expected)
                not_returned = expected_fields - returned_fields
                if not_returned:
                    msg += 'fields %s not returned ' % ', '.join(not_returned)
                self.assertTrue(set(obj.keys()) <= set(fields), msg)

    def start_taskmanager(self, command_port):
        self.start_redis()
        self.taskmanager_process = Process(target=run_taskmanager,
                                           args=(command_port,))
        self.taskmanager_process.start()

    def terminate_taskmanager(self):
        if hasattr(self, 'taskmanager_process'):
            self.taskmanager_process.terminate()
        self.stop_redis()

    def start_queue(self):
        self.start_redis()
        receiver = CallbackReceiver()
        self.queue_process = Process(target=receiver.run_subscriber,
                                     args=(False,))
        self.queue_process.start()

    def terminate_queue(self):
        if hasattr(self, 'queue_process'):
            self.queue_process.terminate()
        self.stop_redis()

    def start_redis(self):
        if not getattr(self, 'redis_process', None):
            self.redis_process = Popen('redis-server --port 16379 > /dev/null',
                                       shell=True, executable='/bin/bash')

    def stop_redis(self):
        if getattr(self, 'redis_process', None):
            self.redis_process.kill()
            self.redis_process = None


class BaseTest(BaseTestMixin, django.test.TestCase):
    '''
    Base class for unit tests.
    '''

class BaseTransactionTest(BaseTestMixin, django.test.TransactionTestCase):
    '''
    Base class for tests requiring transactions (or where the test database
    needs to be accessed by subprocesses).
    '''

class BaseLiveServerTest(BaseTestMixin, django.test.LiveServerTestCase):
    '''
    Base class for tests requiring a live test server.
    '''
