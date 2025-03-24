'''

@author: Frank

Test Suite XML config file example:

<integrationTest>
    <suite name="TEST SUITE NAME 1" info="Test case could be absolute path." setupCase="/home/test/cases/setupcase.py" teardownCase='/home/test/cases/teardowncase.py' timeout="1000" config="/home/test/cases/test-config.xml">
        <case timeout="1000">/home/test/cases/test1.py</case>
        <case timeout="1000">/home/test/cases/test2.py</case>
    </suite>
    <suite name="TEST SUITE NAME 2" info="Suite will be repeatly executed 30 times. In each round, test1 will be repeatly executed 20 times. Test case path can be relative path compared with config file path" setupCase="cases/setupcase.py" teardownCase='cases/teardowncase.py' timeout="1000" repeat="30" parallel="4">
        <case timeout="1000" repeat="20" >cases/test1.py</case>
        <case timeout="1000">../cases/test2.py</case>
        <case timeout="1000">../../test/cases/test3.py</case>
        <case info="if not providing timeout, the default 1800s will be set as the timeout. It also apply to setup and teardown test case">test4.py</case>
    </suite>
</integrationTest>

'''

import zstacklib.utils.xmlobject as xmlobject
import zstacklib.utils.linux as linux
import zstacklib.utils.shell as shell
import zstacklib.utils.log as log
import zstacklib.utils.debug as debug
import os
import sys
import optparse
import shutil
import time
import subprocess
import copy
import string
import Queue
import threading
import traceback
import signal
import datetime

import zstackwoodpecker.test_case as test_case

test_start_time = time.time()
log.configure_log('/var/log/zstack/zstack-woodpecker.log')
# log shell command
shell.logcmd = True
# Default test folder
DEFAULT_TEST_CONFIG = 'DEFAULT_TEST_CONFIG'
LOCAL_WOODPECKER_FOLDER = os.path.join(os.path.expanduser('~'), '.zstackwoodpecker/integrationtest')
TEST_CONFIG_FILE = 'test-config.xml'
sig_flag = False
USER_PATH = os.path.expanduser('~')
POST_TEST_CASE_SCRIPT = '%s/.zstackwoodpecker/post_test_case_script.sh' % USER_PATH


class TestError(Exception):
    ''' test error '''
    
class TestSuite(object):
    def __init__(self):
        self.id = None
        self.name = None
        self.cases = []
        self.setup_case = None
        self.teardown_case = None
        self.timeout = None
        self.root_path = None
        self.repeat = 1
        self.total_case_num = 0
        self.parallel = 0
        self.test_config = None
        
class TestCase(object):
    SETUP_CASE = 'setup'
    TEARDOWN_CASE = 'teardown'
    TIMEOUT = "timeout"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    def __init__(self):
        self.id = None
        self.name = None
        self.timeout = None 
        self.success = []
        self.log_path = None
        self.path = None
        self.suite = None
        self.repeat = 1
        self.type = None
        #if test case is global safe for parallel execution. Default is True.
        self.parallel = True 

class WoodPecker(object):
    INTEGRATION_TEST_TAG = 'integrationTest'
    SUITE_TAG = 'suite'
    IMPORT_TAG = 'import'
    CASE_TAG = 'case'
    
    def __init__(self, options):
        self.options = options
        self.test_case_list = linux.full_path(options.testCaseList)
        self.test_root_path = os.path.dirname(self.test_case_list)
        self.test_config_file = None
        if options.testConfig != DEFAULT_TEST_CONFIG:
            self.test_config_file = options.testConfig
        self.defaultTestCaseTimeout = options.defaultTestCaseTimeout
        self.noCleanup = ''
        if options.noCleanup:
            self.noCleanup = 'noCleanup'
        self.onlyActionLog = ''
        if options.onlyActionLog:
            self.onlyActionLog = 'onlyActionLog'
        self.verbose = options.verbose
        self.startDebugger = options.startDebugger
        self.suites = {}
        self.all_cases = {}
        self.total_case_num = 0
        self.suite_num = 0
        self.case_name_max_len = 0
        current_time = time.strftime("%y%m%d-%H%M%S", time.localtime())
        self.result_dir = os.path.join(self.test_root_path, 'test-result', current_time)
        self.summary_path = os.path.join(self.result_dir, 'summary')
        self.brief_path = os.path.join(self.result_dir, 'brief')
        self.err_list_path = os.path.join(self.result_dir, 'err_log_list')
        self.log_dir = os.path.join(self.result_dir, 'logs')
        self.action_log_dir = os.path.join(self.result_dir, 'action_logs')
        self.err_log_dir = os.path.join(self.result_dir, 'errlogs')
        latest_log = os.path.join(self.test_root_path, 'test-result', 'latest')
        shell.call('rm -rf %s' % latest_log)
        shell.call('rm -rf %s' % self.result_dir)
        os.makedirs(self.result_dir, 0755)
        shell.call('ln -s %s %s' % (current_time, latest_log))
        os.makedirs(self.log_dir, 0755)
        os.makedirs(self.action_log_dir, 0755)
        os.makedirs(self.err_log_dir, 0755)
        self.current_cmd_string = linux.get_command_by_pid(os.getpid())
        self.stop_when_fail = options.stopWhenFail
        self.stop_when_fail_match = options.stopWhenFailMatch
        self.dry_run = options.dryRun
        self.case_failure = False
        if options.testFailureRetry and options.testFailureRetry.isdigit():
            os.environ['WOODPECKER_TEST_FAILURE_RETRY'] = options.testFailureRetry
    
    def _check_test_config(self, suite_config, test_case_path):
        '''Woodpecker will firstly check if user passes 
        '-c TEST_CONFIG_FILE_PATH'. If not, it will check if suite.xml defines
        'config=TEST_CONFIG_FILE_PATH'. If not, it will check if config file 
        ~/.zstackwoodpecker/integrationtest/xxx/yyy/test-config.xml existence
        (xxx/yyy should be as same as the test target folder name, e.g. 
        'vm/basic'.) At last woodpecker will use source code test-config.xml in
        current test suite folder. '''
        if self.test_config_file:
            return self.test_config_file
        elif suite_config:
            return suite_config
        else:
            if not 'integrationtest/' in test_case_path:
                return

            test_sub_folder = os.path.dirname(test_case_path.split('integrationtest/')[1])
            local_test_config = os.path.join(LOCAL_WOODPECKER_FOLDER, test_sub_folder, TEST_CONFIG_FILE)
            local_test_config = linux.find_file(TEST_CONFIG_FILE, local_test_config, 4)
            if local_test_config and os.path.exists(local_test_config):
                return local_test_config
            else:
                source_test_config = linux.find_file(TEST_CONFIG_FILE, test_case_path, 4)
                return source_test_config

    def info(self, msg):
        sys.stdout.write('%s\n' % msg)
        
    def validate_cases(self):
        def is_case_exists(case):
            if not os.path.exists(case.path):
                raise TestError('unable to find test case[%s] in suite[%s], please note if you are using relative path, the root path is where test configuration file located which is %s in this case' % (case.path, suite.name, case.suite.root_path))
            
        for suite in self.suites.values():
            if suite.setup_case:
                is_case_exists(suite.setup_case)
            if suite.teardown_case:
                is_case_exists(suite.teardown_case)
            for case in suite.cases:
                is_case_exists(case)
                case_config = test_case.get_case_config(case.path)
                if case_config:
                    if case_config.has_key(test_case.TIME_OUT):
                        case.timeout = str(case_config[test_case.TIME_OUT])
                    if case_config.has_key(test_case.NO_PARALLEL) and \
                            case_config[test_case.NO_PARALLEL]:
                        case.parallel = False

    def get_case_log_path(self, case, suite_repeat, case_repeat):
        log_path = os.path.join(self.log_dir, case.suite.name + '.' + str(suite_repeat), case.name + '_id' + str(case.id) + '.' + str(case_repeat) + '.log')
        return log_path

    def get_case_action_log_path(self, case, suite_repeat, case_repeat):
        log_path = os.path.join(self.action_log_dir, case.suite.name + '.' + str(suite_repeat), case.name + '_id' + str(case.id) + '.' + str(case_repeat) + '.log')
        return log_path

    def run_test(self):
        global sig_flag
        def repeat_char(c, num):
            return c * num
        
        def clear_bar(len):
            fmt = '\r%s'
            sys.stdout.write(fmt % ' '.ljust(len))
            sys.stdout.flush()
        
        def print_bar(casename, length, test_time, terminal_width):
            #bar_len = 22
            test_time2 = '[ %s ]' % str(datetime.timedelta(seconds=test_time))
            time_len = len(test_time2)
            blank_len = terminal_width - time_len - length - self.case_name_max_len - 2
            #if length <= bar_len:
            fmt = '\r%s ' + repeat_char('.', length) + repeat_char(' ', blank_len) + test_time2
            s = fmt % casename.ljust(self.case_name_max_len)
            sys.stdout.write(s)
            sys.stdout.flush()
            #else:
            #    fmt = '\r%s ' + repeat_char(' ', length - bar_len) + repeat_char('.', bar_len) + repeat_char(' ', blank_len) + test_time
            #    s = fmt % casename.ljust(self.case_name_max_len)
            #    sys.stdout.write(s)
            #    sys.stdout.flush()
            return len(s)
            
        def run_case(suite, case, suite_repeat, case_repeat, parallel=0):
            global sig_flag
            if self.dry_run:
                return
            case_log_path = self.get_case_log_path(case, suite_repeat, case_repeat)
            case_action_log_path = self.get_case_action_log_path(case, suite_repeat, case_repeat)
            max_case_name_len = self.case_name_max_len
            if case_repeat == 0:
                case_name = case.name
            else:
                case_name = case.name + '.' + str(case_repeat)
                if len(case_name) > self.case_name_max_len:
                    max_case_name_len = len(case_name)

            try:
                logdir = os.path.dirname(case_action_log_path)
                if not os.path.exists(logdir):
                    os.makedirs(logdir, 0755)
            except:
                pass
                #traceback.print_exc(file=sys.stdout)
            try:
                logdir = os.path.dirname(case_log_path)
                if not os.path.exists(logdir):
                    os.makedirs(logdir, 0755)
            except:
                pass
                #traceback.print_exc(file=sys.stdout)

            logfd = open(case_log_path, 'w', 0)

            try:
                if case_name == 'suite_setup':
                    test_env_variables = 'WOODPECKER_TEST_CONFIG_FILE=%s WOODPECKER_CASE_ACTION_LOG_PATH=%s WOODPECKER_NO_ERROR_CLEANUP=%s WOODPECKER_ONLY_ACTION_LOG=%s' % (self._check_test_config(suite.test_config, case.path), case_action_log_path, self.noCleanup, self.onlyActionLog)
                else:
                    test_env_variables = 'WOODPECKER_TEST_CONFIG_FILE=%s WOODPECKER_CASE_ACTION_LOG_PATH=%s WOODPECKER_NO_ERROR_CLEANUP=%s WOODPECKER_ONLY_ACTION_LOG=%s WOODPECKER_START_DEBUGGER=%s' % (self._check_test_config(suite.test_config, case.path), case_action_log_path, self.noCleanup, self.onlyActionLog, self.startDebugger)
                #self.info('\n test environment variables: %s \n' % test_env_variables)
                #cmd = '%s /usr/bin/nosetests -s --exe %s 2>&1' % (test_env_variables, case.path)
                case_dir = os.path.dirname(case.path)
                #case_name = os.path.basename(case.path)[0:-3]
                cmd = '%s python -c "from zstackwoodpecker import test_case;test_case.main(%s)"' % (test_env_variables, [case.path])
                start_time = time.time()
                if self.case_failure and self.stop_when_fail:
                    return
                if self.verbose:
                    process = subprocess.Popen(cmd, executable='/bin/sh', shell=True, cwd=self.test_root_path, universal_newlines=True)
                else:
                    process = subprocess.Popen(cmd, executable='/bin/sh', shell=True, stdout=logfd, stderr=logfd, cwd=self.test_root_path, universal_newlines=True)
                last_size = 1
                dot_len = 1
                clear_bar(last_size)
                if not self.verbose:
                    try:
                        terminal_width = int(os.popen('stty size', 'r').read().split()[1])
                    except:
                        terminal_width = 80
                    # dot width need to minus the length of max case name and the results 
                    dot_width = terminal_width - max_case_name_len - 13

                if not case.timeout:
                    case.timeout = self.defaultTestCaseTimeout

                display_wait = 1
                curr_time = time.time()
                test_time = curr_time - start_time
                while process.poll() is None:
                    curr_time = time.time()
                    test_time = curr_time - start_time
                    if ((case.timeout != None) and \
                            test_time > string.atoi(case.timeout)) or \
                            sig_flag == True:
                        case.success[suite_repeat][case_repeat] = \
                                TestCase.TIMEOUT
                        test_time2 = '%s' % str(datetime.timedelta(seconds=int(test_time)))
                        ret = ' [ \033[93mtimeout %s\033[0m ]' % test_time2
                        process.terminate()
                        break
                    if not self.verbose:
                        #if parallel:
                        #    #give all thread have chance to show execution time
                        #    if display_wait >= 2.5 * parallel:
                        #        clear_bar(last_size)
                        #        last_size = print_bar(case_name, dot_len, \
                        #                int(test_time), terminal_width)
                        #        display_wait = 0
                        #else:
                        if display_wait == 3:
                            clear_bar(last_size)
                            last_size = print_bar(case_name, dot_len, \
                                    int(test_time), terminal_width)
                            display_wait = 0

                        display_wait += 1

                        dot_len += 1
                        dot_len = 1 if dot_len > (dot_width -2) else dot_len
                    time.sleep(0.127)

                test_time2 = '%s' % str(datetime.timedelta(seconds=int(test_time)))
                if case.success[suite_repeat][case_repeat] != TestCase.TIMEOUT:
                    if process.returncode == 0:
                        case.success[suite_repeat][case_repeat] = TestCase.PASS
                        #ret = ' [ \033[92msuccess\033[0m ]'
                        ret = ' [ \033[92msuccess %s\033[0m ]' % test_time2
			result = "PASS"
                    elif process.returncode == 2:
                        case.success[suite_repeat][case_repeat] = TestCase.SKIP
                        #ret = ' [ \033[93mskipped\033[0m ]'
                        ret = ' [ \033[93mskipped 0:00:00\033[0m ]'
			result = "SKIP"
                    else:
                        case.success[suite_repeat][case_repeat] = TestCase.FAIL
                        #ret = ' [ \033[91mfailed\033[0m  ]'
                        ret = ' [ \033[91mfailed %s\033[0m  ]' % test_time2
                        self.case_failure = True
			result = "FAIL"
                else:
			result = "TIMEOUT"

                if case_repeat != 0:
                        brief = "%s %s.%s %s\n" % (suite.name, case.name, case_repeat, result)
                else:
                        brief = "%s %s %s\n" % (suite.name, case.name, result)

                self.write_file_a(self.brief_path, brief)
                if not self.verbose:
                    dot_width = terminal_width - max_case_name_len - 13 - len(test_time2) - 1
                    fmt = '\r%s ' + repeat_char('.', dot_width)

                    msg = fmt % case_name.ljust(max_case_name_len) + ret
                    self.info(msg)

                if os.path.exists(POST_TEST_CASE_SCRIPT):
                    os.system("bash %s" % POST_TEST_CASE_SCRIPT)

                    
            finally:
                logfd.close()

            if self.stop_when_fail_match:
                logfd = open(case_log_path, 'r')
		for line in logfd:
                    if self.stop_when_fail_match in line:
		        self.stop_when_fail = True
			break
		logfd.close()
        
        def run_suite(suite):
            def wait_for_queue(parallel=0):
                while threading.active_count() > parallel + 1:
                    time.sleep(0.5)

            self.info('Test suite: [%s], %s cases, %s execution threads, repeat %s times:' % (suite.name, suite.total_case_num, suite.parallel, suite.repeat))
            for suite_repeat in range(suite.repeat):
                if self.case_failure and self.stop_when_fail:
                    return

                if suite.setup_case:
                    if sig_flag:
                        return
                    if self.case_failure and self.stop_when_fail:
                        return
                    #self.info('running setup case: %s' % suite.setup_case.name)
                    run_case(suite, suite.setup_case, suite_repeat, 0)
                    if suite.setup_case.success[suite_repeat][0] != TestCase.PASS:
                        self.info('setup_case[%s] in suite[%s] failed to execute, skipping test cases in this suite' % (suite.setup_case.name, suite.name + "_r" + str(suite_repeat)))
                        return
    
                if suite.parallel != 0:
                    for case in suite.cases:
                        if self.case_failure and self.stop_when_fail:
                            break
                        if case.type == None:
                            if case.parallel:
                                for case_repeat in range(case.repeat):
                                    if sig_flag:
                                        return

                                    wait_for_queue(suite.parallel - 1)
                                    if self.case_failure \
                                            and self.stop_when_fail:
                                        break
                                    thread = threading.Thread(target=run_case, \
                                            args=(suite, case, suite_repeat, \
                                            case_repeat, suite.parallel, ))
                                    
                                    thread.start()
                            else:
                                if sig_flag:
                                    return
                                if self.case_failure and self.stop_when_fail:
                                    break
                                wait_for_queue()
                                for case_repeat in range(case.repeat):
                                    run_case(suite, case, suite_repeat, case_repeat)
                else:
                    if sig_flag:
                        return
                    #wait for all test cases are finished. 
                    wait_for_queue()
                    for case in suite.cases:
                        if case.type == None:
                            for case_repeat in range(case.repeat):
                                if sig_flag:
                                    return
                                if self.case_failure and self.stop_when_fail:
                                    return
                                run_case(suite, case, suite_repeat, case_repeat)

                #wait for all test cases are finished. 
                wait_for_queue()
                if suite.teardown_case:
                    if sig_flag:
                        return
                    if self.case_failure and self.stop_when_fail:
                        return
                    #self.info('running teardown case: %s' % suite.teardown_case.name)
                    run_case(suite, suite.teardown_case, suite_repeat, 0)
        
        self.info('[Test Begin]\n')
        for suite in self.suites.values():
            if sig_flag or (self.case_failure and self.stop_when_fail):
                break
            run_suite(suite)
                
    def parse_suite(self):
        self.info('\n[Begin suite parsing]\n')
        if not os.path.exists(self.test_case_list):
            raise TestError('unable to find test configuration file at %s' % self.test_case_list)
        
        def recur_parse(test_case_list):
            suiteroot = os.path.dirname(test_case_list)
            
            def full_path(path):
                if not path.startswith('/'):
                    path = os.path.join(suiteroot, path)
                return path

            def initialize_case_result(suite_repeat, case_repeat):
                case_result = []
                result = []
                for i in range(case_repeat):
                    case_result.append(None)
                for i in range(suite_repeat):
                    result.append(list(case_result))
                return result

            def add_cases_to_suite(xmlobject, s, suite):
                if s.setupCase__:
                    setupcase = TestCase()
                    setupcase.path = full_path(s.setupCase__)
                    setupcase.name = setupcase.path.split('/')[-1].split('.')[0]
                    setupcase.suite = suite
                    setupcase.type = TestCase.SETUP_CASE
                    setupcase.success = initialize_case_result(suite.repeat, setupcase.repeat)
                    self.total_case_num += 1
                    suite.setup_case = setupcase
                    setupcase.id = self.total_case_num
                    self.all_cases[setupcase.id] = setupcase
                    suite.cases.append(setupcase)
                    suite.total_case_num += 1
                    if len(setupcase.name) > self.case_name_max_len:
                        self.case_name_max_len = len(setupcase.name)
                if xmlobject.has_element(s, self.CASE_TAG):
                    for c in s.get_child_node_as_list(self.CASE_TAG):
                        case = TestCase()
                        case.name = c.name__
                        case.timeout = c.timeout__
                        case.path = full_path(c.text_)
                        if c.noparallel__ and c.noparallel__ != 'False':
                            case.parallel = False
                        if not case.name:
                            #only keep 1 level folder info for case name
                            case.name = '/'.join(case.path.split('/')[-2:])[:-3]
                        case.suite = suite
                        case_name_len = len(case.name)
                        if (c.repeat__ and c.repeat__.isdigit() and (string.atoi(c.repeat__) > 0)):
                            case.repeat = string.atoi(c.repeat__)
                            if case.repeat > 1:
                                import math
                                # case name will be increased due to add '.num'
                                case_name_len = case_name_len + 1 + int(math.log(case.repeat, 10)) + 1
                        if case_name_len > self.case_name_max_len:
                            self.case_name_max_len = case_name_len

                        self.info('\t\tRun [%s] times for Case: [%s]' % (case.repeat, case.name))
                           # c_repeat = 2
                           # while (c_repeat <= case.repeat):
                           #     r_case = copy.deepcopy(case)
                           #     r_case.name = case.name + '.'+ str(c_repeat)
                           #     c_repeat += 1
                           #     suite.cases.append(r_case)
                           #     self.total_case_num += 1
                           #     r_case.id = self.total_case_num
                           #     if len(r_case.name) > self.case_name_max_len:
                           #         self.case_name_max_len = len(r_case.name)
                           #     self.all_cases[case.id] = r_case
                        case.success = initialize_case_result(suite.repeat, case.repeat)
                        suite.cases.append(case)
                        suite.total_case_num += case.repeat
                        self.total_case_num += 1
                        #Allow same test cases be executed multi times.
                        case.id = self.total_case_num
                        self.all_cases[case.id] = case

                if s.teardownCase__:
                    teardowncase = TestCase()
                    teardowncase.path = full_path(s.teardownCase__)
                    teardowncase.name = teardowncase.path.split('/')[-1].split('.')[0]
                    teardowncase.suite = suite
                    teardowncase.type = TestCase.TEARDOWN_CASE
                    teardowncase.success = initialize_case_result(suite.repeat, teardowncase.repeat)
                    suite.teardown_case = teardowncase
                    self.total_case_num += 1
                    teardowncase.id = self.total_case_num
                    self.all_cases[teardowncase.id] = teardowncase
                    suite.cases.append(teardowncase)
                    suite.total_case_num += 1
                    if len(teardowncase.name) > self.case_name_max_len:
                        self.case_name_max_len = len(teardowncase.name)

                if s.config__:
                    suite.test_config = full_path(s.config__)

            self.info('discovering test cases in %s ...' % test_case_list)
            
            with open(test_case_list, 'r') as fd:
                xmlstr = fd.read()
            
            xo = xmlobject.loads(xmlstr)
            if xo.get_tag() != self.INTEGRATION_TEST_TAG:
                raise TestError('configuration must start with tag <%s>' % self.INTEGRATION_TEST_TAG)
            
            if xmlobject.has_element(xo, self.SUITE_TAG):
                for s in xo.get_child_node_as_list(self.SUITE_TAG):
                    suite = TestSuite()
                    suite.name = s.name_.replace(' ', '_')
                    suite.id = self.suite_num
                    self.suite_num += 1
                    suite.root_path = os.path.dirname(test_case_list)
                    suite.timeout = s.timeout__

                    if (s.parallel__ and s.parallel__.isdigit() \
                            and (string.atoi(s.parallel__) > 1)):
                        suite.parallel = string.atoi(s.parallel__)

                    if (s.repeat__ and s.repeat__.isdigit() \
                            and (string.atoi(s.repeat__) > 1)):
                        suite.repeat = string.atoi(s.repeat__)

                    self.info('\tSuite [%s] will run [%s] times:' \
                            % (suite.name, suite.repeat))
                       # repeat = 2
                       # while (repeat <= suite.repeat):
                       #     r_suite = copy.deepcopy(suite)
                       #     r_suite.name = suite.name + '.' + str(repeat)
                       #     r_suite.id = suite_id
                       #     suite_id += 1
                       #     if (suite.setup_case):
                       #         self.total_case_num += 1
                       #     if (suite.teardown_case):
                       #         self.total_case_num += 1

                       #     repeat += 1
                       #     add_cases_to_suite(xmlobject, s, r_suite)
                       #     self.suites[r_suite.id] = r_suite

                    add_cases_to_suite(xmlobject, s, suite)
                    self.suites[suite.id] = suite

            if xmlobject.has_element(xo, self.IMPORT_TAG):
                for i in xo.get_child_node_as_list(self.IMPORT_TAG):
                    path = full_path(i.path_)
                    if not os.path.exists(path):
                        raise TestError('unable to find test configuration file at %s, imported config[%s]' % (path, i.path_))
                    recur_parse(path)
            
        recur_parse(self.test_case_list)
        self.info('\n[Suite parsing finished]: %s test suites discovered, total %s cases\n' % (len(self.suites), self.total_case_num))

    def write_file_a(self, fileh, msg):
        file_h = open(fileh, 'a')
        file_h.write(msg)
        file_h.close()

    def finalize_result(self):
        skipped = 0
        success = 0
        failure = 0
        timeout = 0

        err_case = []
        report = ['\n']

        equal_sign = '='*80 + '\n'
        minus_sign = '-'*80 + '\n'
        summary = '\nTest Summary:\n'
        summary_title = " Test Case\t\t\t\t\tPass\tFail\tTMO\tSkip   \n" + minus_sign
        summary += equal_sign + summary_title
        for suite in self.suites.values():
#            engine_log += "Test Suite: " + suite.name + "\n"
            for suite_repeat in range(suite.repeat):
                if suite.repeat == 1:
                    summary += " " + suite.name + ":\n"
                else:
                    summary += " " + suite.name + "." + str(suite_repeat) + ":\n"
                for case in suite.cases:
                    for case_repeat in range(case.repeat):
                        if len(case.name) > 38:
                            case_show_name = '%s...' % case.name[:35]
                        else:
                            case_show_name = case.name

                        if case.repeat == 1:
                            case_name = case_show_name
                        else:
                            case_name = case_show_name + '.' + str(case_repeat)

                        if case.success[suite_repeat][case_repeat] is None or case.success[suite_repeat][case_repeat] == TestCase.SKIP:
                            summary += "    {0:44}0\t0\t0\t1\n".format(case_name)
                            skipped += 1
                        elif case.success[suite_repeat][case_repeat] == TestCase.PASS:
                            summary += "    {0:44}1\t0\t0\t0\n".format(case_name)
                            success += 1
                        elif case.success[suite_repeat][case_repeat] == TestCase.FAIL:
                            summary += "    {0:44}0\t1\t0\t0\n".format(case_name)
                            failure += 1
                            case_log_path = self.get_case_log_path(case, suite_repeat, case_repeat)
                            err_case.append(case_log_path)
                        elif case.success[suite_repeat][case_repeat] == TestCase.TIMEOUT:
                            summary += "    {0:44}0\t0\t1\t0\n".format(case_name)
                            timeout += 1
                            case_log_path = self.get_case_log_path(case, suite_repeat, case_repeat)
                            err_case.append(case_log_path)

        total = success + failure + timeout + skipped
        if total > 25:
            summary += minus_sign + summary_title
        else:
            summary += minus_sign

        summary += " Total:\t%d\t\t\t\t\t%d\t%d\t%d\t%d\t\n" % (total, success, failure, timeout, skipped)
        summary += equal_sign
        self.write_file_a(self.summary_path, summary)

        if err_case:
            report.append('Logs of error cases:')
            report.append(equal_sign)
            for ec in err_case:
                link = ['ln -s']
                log_name = os.path.basename(ec)
                suite_name = os.path.dirname(ec[len(self.log_dir):]).replace('/', '_')
                link.append(os.path.join("../", ec[len(self.result_dir)+1:]))
                err_log_link = os.path.join(self.err_log_dir, suite_name + '-' + log_name)
                link.append(err_log_link)
                shell.call(' '.join(link))
                report.append(err_log_link)

        self.write_file_a(self.err_list_path, '\n'.join(report))
        if os.path.exists(POST_TEST_CASE_SCRIPT):
            os.system("bash %s" % POST_TEST_CASE_SCRIPT)

        self.info('\n'.join(report))
        print(summary)
        print('The detailed test results are in %s \n' % self.result_dir)

    def main(self):
        self.parse_suite()
        self.validate_cases()
        self.run_test()
        self.finalize_result()


def sigint_handler(signum, frame):
    global sig_flag
    print 'receive ctrl-c signal, will stop current woodpecker running'
    sig_flag = True

def main():
    parser = optparse.OptionParser()
    parser.add_option("-f", "--test-case", dest="testCaseList", default=None, help="[Required] Define what test cases will run.")
    parser.add_option("-c", "--test-config", dest="testConfig", default=DEFAULT_TEST_CONFIG, help="[Optional] Integration test config file. Default config file will be test-config.xml under test cases folder.")
    parser.add_option("-v", "--verbose", action='store_true', dest="verbose", help="[Optional] print output to console")
    parser.add_option("-u", "--dry-run", action='store_true', dest="dryRun", help="[Optional] Dry run test case")
    parser.add_option("-n", "--no-cleanup", action='store_true', dest="noCleanup", default=False, help="[Optional] do not execute error_cleanup(), when test case fails")
    parser.add_option("-s", "--stop-failure", action='store_true', dest="stopWhenFail", default=False, help="[Optional] Stop testing, when there is test case failure. Used to work with -n option")
    parser.add_option("-m", "--stop-failure-match", action='store', dest="stopWhenFailMatch", default=None, help="[Optional] Stop testing, when there is test case failure and test log match given string. Used to work with -n option")
    parser.add_option("-a", "--action-log", action='store_true', dest="onlyActionLog", default=False, help="[Optional] only save 'Action' log by test_util.action_logger(). test_util.test_logger() will not be saved in test case's action.log file.")
    parser.add_option("-d", "--start-debugger", action='store_true', dest="startDebugger", default=False, help="[Optional] start remote debugger with rpdb (default port 4444) at the time of exception.")
    parser.add_option("-t", "--case-timeout", action='store', dest="defaultTestCaseTimeout", default='1800', help="[Optional] test case timeout, if test case doesn't set one. The default timeout is 1800s.")
    parser.add_option("-r", "--test-failure-retry", action='store', dest="testFailureRetry", default=None, help="[Optional] Set the max retry times, when test checker is failed. ")
    (options, arg) = parser.parse_args()
    if not options.testCaseList:
        parser.print_help()
        sys.exit(1)

    signal.signal(signal.SIGINT, sigint_handler)

    w = WoodPecker(options)
    w.main()
    test_end_time = time.time()
    test_time = test_end_time - test_start_time
    test_time_list = str(test_time).split('.')
    print "Total test time: %s.%s (%s)\n" % (time.strftime('%H:%M:%S', time.gmtime(int(test_time_list[0]))), test_time_list[1][:3], test_time)
    sys.exit(0)

if __name__ == '__main__':
    debug.install_runtime_tracedumper()
    main()
