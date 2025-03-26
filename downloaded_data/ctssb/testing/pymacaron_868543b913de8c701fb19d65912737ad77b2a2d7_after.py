import os
import sys
import logging
import json
import subprocess
from time import sleep
import psutil
from klue_unit.testcase import KlueTestCase


log = logging.getLogger(__name__)


tmpdir = '/tmp/test-klue-microservice'
reportpath = os.path.join(tmpdir, "error_report.json")
try:
    os.stat(tmpdir)
except:
    os.mkdir(tmpdir)


class Tests(KlueTestCase):


    def start_server(self):
        path_server = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'testserver.py')
        log.info("Starting test server at %s" % path_server)
        p = subprocess.Popen([path_server])
        self.pid = p.pid
        log.info("Waiting for test server with pid %s to start" % self.pid)
        sleep(2)

        try:
            p = psutil.Process(self.pid)
        except psutil.NoSuchProcess as e:
            assert 0, "Failed to start testserver"


    def kill_server(self):
        log.info("Killing test server with pid %s" % self.pid)
        if self.pid:
            p = psutil.Process(self.pid)
            p.terminate()

        for p in psutil.process_iter():
            cmd = ' '.join(p.cmdline())
            if cmd.endswith('testserver.py'):
                log.info("PROC FOUND: %s" % p.cmdline())
                p.terminate()


    def assertNoErrorReport(self):
        self.assertFalse(os.path.isfile(reportpath))

    def load_report(self):
        with open(reportpath) as f:
            s = f.read()
            log.info("GOT\n%s\n" % s)
            j = json.loads(s)
            log.debug("Report is %s" % json.dumps(j, indent=4))
            title = j['title']
            body = j['body']
            log.info("Loaded error report [%s]" % title)
            return title, body


    def assertBaseReportOk(self, path=None, user_id=None):
        title, body = self.load_report()
        self.assertTrue(title)
        self.assertTrue('/home/erwan/pnt/klue-microservice/test/testserver.py' in body['stack'][0])
        self.assertTrue('call_id' in body)
        self.assertEqual(body['call_path'], 'crash')
        self.assertEqual(body['is_ec2_instance'], False)

        if user_id:
            self.assertEqual(body['user']['is_auth'], 1)
            self.assertEqual(body['user']['id'], user_id)
        else:
            self.assertEqual(body['user']['is_auth'], 0)
            self.assertEqual(body['user']['id'], '')
        self.assertTrue('python-requests' in body['user']['user_agent'])
        self.assertEqual(body['user']['ip'], '127.0.0.1')

        self.assertEqual(body['endpoint']['method'], 'GET')
        self.assertEqual(body['endpoint']['base_url'], 'http://127.0.0.1:8765/%s' % path)
        self.assertEqual(body['endpoint']['url'], 'http://127.0.0.1:8765/%s' % path)
        self.assertEqual(body['endpoint']['path'], '/%s' % path)
        self.assertTrue(body['endpoint']['id'].endswith(' GET /%s' % path), "%s ends with GET /%s" % (body['endpoint']['id'], path))

        self.assertEqual(body['server']['port'], '8765')
        self.assertTrue(body['server']['api_name'] in ['ping', 'crash'])
        self.assertEqual(body['server']['fqdn'], '127.0.0.1')
        self.assertEqual(body['server']['api_version'], '0.0.1')

        return title, body


    def assertServerErrorReportOk(self, path=None, fatal=True, user_id=None):
        title, body = self.assertBaseReportOk(user_id=user_id, path=path)
        self.assertTrue('error_id' in body)

        self.assertEqual(body['is_fatal_error'], fatal)

        self.assertTrue(body['time']['end'] >= body['time']['start'])
        self.assertTrue(body['time']['microsecs'] >= 1000)
        self.assertTrue(body['time']['microsecs'] <= 10000000)

        self.assertEqual(body['call_path'], 'crash')

        return title, body


    def setUp(self):
        super().setUp()
        self.pid = None
        if 'NO_ERROR_REPORTING' in os.environ:
            del os.environ['NO_ERROR_REPORTING']
        os.environ['DO_REPORT_ERROR'] = '1'

        if os.path.isfile(reportpath):
            os.remove(reportpath)

        self.kill_server()
        self.start_server()
        self.port = 8765


    def tearDown(self):
        self.kill_server()

    #
    # And the tests!
    #

    def test_internal_exception(self):
        j = self.assertGetReturnError(
            'crash/internalexception',
            500,
            'UNHANDLED_SERVER_ERROR'
        )
        title, body = self.assertServerErrorReportOk(
            path='crash/internalexception',
        )
        self.assertEqual(title, 'FATAL ERROR %s 500 UNHANDLED_SERVER_ERROR: do_crash_internal_exception(): Raising an internal exception' % body['server']['api_name'])

        self.assertEqual(body['response']['user_message'], '')
        self.assertEqual(body['response']['type'], 'Response')
        self.assertEqual(body['response']['status'], '500')
        self.assertEqual(body['response']['is_error'], 1)
        self.assertEqual(body['response']['error_code'], 'UNHANDLED_SERVER_ERROR')
        self.assertEqual(body['response']['error_description'], 'Raising an internal exception')

        self.assertEqual(body['trace'][0], 'Traceback (most recent call last):\n')

        self.assertEqual(body['request']['params'], '[]')


    def test_report_error(self):
        j = self.assertGetReturnOk(
            'crash/reporterror'
        )
        title, body = self.assertBaseReportOk(
            path='crash/reporterror',
        )
        self.assertEqual(title, 'NON-FATAL ERROR %s do_crash_report_error(): called crash/reporterror to test error reporting' % body['server']['api_name'])

        self.assertTrue('time' not in body)
        self.assertTrue('error_id' not in body)
        self.assertTrue('response' not in body)
        self.assertTrue('trace' not in body)
        self.assertTrue('request' not in body)
        self.assertEqual(body['is_fatal_error'], False)
        self.assertEqual(body['title'], 'called crash/reporterror to test error reporting')


    def test_report_fatal_error_response(self):
        j = self.assertGetReturnError(
            'crash/returnfatalerrorresponse',
            543,
            'FATAL_CUSTOM_ERROR'
        )
        title, body = self.assertServerErrorReportOk(
            path='crash/returnfatalerrorresponse',
            fatal=True,
        )
        self.assertEqual(title, 'FATAL ERROR %s 543 FATAL_CUSTOM_ERROR: do_crash_return_fatal_error_response(): endpoint returns an Error response' % body['server']['api_name'])


    def test_report_non_fatal_error_response(self):
        j = self.assertGetReturnError(
            'crash/returnnonfatalerrorresponse',
            401,
            'NON_FATAL_CUSTOM_ERROR'
        )
        self.assertNoErrorReport()


    def test_report_error_model(self):
        j = self.assertGetReturnError(
            'crash/returnerrormodel',
            543,
            'ANOTHER_CUSTOM_ERROR'
        )
        self.assertEqual(j['error_description'], 'Testing error model')
        self.assertEqual(j['status'], 543)
        self.assertEqual(j['error'], 'ANOTHER_CUSTOM_ERROR')
        title, body = self.assertServerErrorReportOk(
            path='crash/returnerrormodel',
            fatal=True,
        )
        self.assertEqual(title, 'FATAL ERROR %s 543 ANOTHER_CUSTOM_ERROR: do_crash_return_error_model(): Testing error model' % body['server']['api_name'])


    def test_report_error_instance(self):
        j = self.assertGetReturnError(
            'crash/returnerrorinstance',
            543,
            'FATAL_CUSTOM_ERROR'
        )
        title, body = self.assertServerErrorReportOk(
            path='crash/returnerrorinstance',
            fatal=True,
        )
        self.assertEqual(title, 'FATAL ERROR %s 543 FATAL_CUSTOM_ERROR: do_crash_return_error_instance(): endpoint returns an Error instance' % body['server']['api_name'])


    def test_report_slow_call(self):
        j = self.assertGetReturnOk(
            'crash/slowcall'
        )
        title, body = self.assertServerErrorReportOk(
            path='crash/slowcall',
            fatal=False,
        )
        self.assertEqual(title, 'NON-FATAL ERROR %s 200 : do_crash_slow_call() calltime exceeded 5 sec!' % body['server']['api_name'])

        self.assertEqual(body['response']['user_message'], '')
        self.assertEqual(body['response']['type'], 'Response')
        self.assertEqual(body['response']['status'], '200')
        self.assertEqual(body['response']['is_error'], 0)
        self.assertEqual(body['response']['error_code'], '')
        self.assertEqual(body['response']['error_description'], '')

        self.assertTrue('trace' not in body)

        self.assertEqual(body['request']['params'], '[]')

        self.assertEqual(body['title'], 'do_crash_slow_call() calltime exceeded 5 sec!')
