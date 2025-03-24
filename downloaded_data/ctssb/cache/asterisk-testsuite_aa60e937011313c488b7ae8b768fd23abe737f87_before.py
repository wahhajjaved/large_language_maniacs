#!/usr/bin/env python
'''Asterisk external test suite driver.

Copyright (C) 2010, Digium, Inc.
Russell Bryant <russell@digium.com>

This program is free software, distributed under the terms of
the GNU General Public License Version 2.
'''

import sys
import os
import subprocess
import optparse
import time
import yaml
import socket

sys.path.append("lib/python")

from asterisk.version import AsteriskVersion
from asterisk.asterisk import Asterisk
from asterisk.TestConfig import Dependency, TestConfig
from asterisk import utils

TESTS_CONFIG = "tests.yaml"
TEST_RESULTS = "asterisk-test-suite-report.xml"

class TestRun:
    def __init__(self, test_name, ast_version, options):
        self.can_run = False
        self.did_run = False
        self.time = 0.0
        self.test_name = test_name
        self.ast_version = ast_version
        self.options = options
        self.test_config = TestConfig(test_name)
        self.failure_message = "<failure />"
        self.__check_deps(ast_version)
        self.stdout = ""

    def run(self):
        self.passed = False
        self.did_run = True
        start_time = time.time()
        cmd = [
            "%s/run-test" % self.test_name,
        ]

        if os.path.exists(cmd[0]) and os.access(cmd[0], os.X_OK):
            msg = "Running %s ..." % cmd
            print msg
            self.stdout += msg
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            try:
                for l in p.stdout.readlines():
                    print l,
                    self.stdout += l
            except IOError:
                pass
            p.wait()

            """ Parse out ERROR messages """
            self.__parse_run_output(self.stdout)

            self.passed = (p.returncode == 0 and self.test_config.expectPass) or (p.returncode and not self.test_config.expectPass)
        else:
            print "FAILED TO EXECUTE %s, it must exist and be executable" % cmd
        self.time = time.time() - start_time

    def __check_deps(self, ast_version):
        self.can_run = self.test_config.check_deps(ast_version)

    def __parse_run_output(self, output):
        tokens = output.split('\n')
        failureBody = ""
        for line in tokens:
            if 'ERROR' in line:
                failureBody += line + '\n'
        if failureBody != "":
            """ This is commented out for now until we can investigate bamboos failure to parse complex messages """
            """self.failure_message = '<failure type="ERROR" message="%s" />' % failureBody"""
            self.failure_message = '<failure />'


class TestSuite:
    def __init__(self, ast_version, options):
        self.options = options

        self.tests = []
        self.tests = self._parse_test_yaml("tests", ast_version)

        self.total_time = 0.0
        self.total_count = 0
        self.total_failures = 0

    def _parse_test_yaml(self, test_dir, ast_version):
        tests = []
        try:
            f = open("%s/%s" % (test_dir, TESTS_CONFIG), "r")
        except IOError:
            print "Failed to open %s" % TESTS_CONFIG
            return
        except:
            print "Unexpected error: %s" % sys.exc_info()[0]
            return

        config = yaml.load(f)
        f.close()

        for t in config["tests"]:
            for val in t:
                path = "%s/%s" % (test_dir, t[val])
                if val == "test":
                    # If we specified a subset of tests, there's no point loading the others.
                    if self.options.test and not self.options.test in path:
                        continue

                    tests.append(TestRun(path, ast_version, self.options))
                elif val == "dir":
                    tests += self._parse_test_yaml(path, ast_version)

        return tests

    def list_tests(self):
        print "Configured tests:"
        i = 1
        for t in self.tests:
            print "%.3d) %s" % (i, t.test_config.test_name)
            print "      --> Summary: %s" % t.test_config.summary
            print "      --> Minimum Version: %s (%s)" % \
                         (str(t.test_config.minversion), str(t.test_config.minversion_check))
            if t.test_config.maxversion is not None:
                print "      --> Maximum Version: %s (%s)" % \
                             (str(t.test_config.maxversion), str(t.test_config.maxversion_check))
            for d in t.test_config.deps:
                if d.version:
                    print "      --> Dependency: %s" % (d.name)
                    print "        --> Version: %s -- Met: %s" % (d.version,
                            str(d.met))
                else:
                    print "      --> Dependency: %s -- Met: %s" % (d.name,
                             str(d.met))
            i += 1

    def run(self):
        test_suite_dir = os.getcwd()

        for t in self.tests:
            if t.can_run is False:
                if t.test_config.skip is not None:
                    print "--> %s ... skipped '%s'" % (t.test_name, t.test_config.skip)
                    continue

                print "--> Cannot run test '%s'" % t.test_name
                print "--- --> Minimum Version: %s (%s)" % \
                    (str(t.test_config.minversion), str(t.test_config.minversion_check))
                if t.test_config.maxversion is not None:
                    print "--- --> Maximum Version: %s (%s)" % \
                        (str(t.test_config.maxversion), str(t.test_config.maxversion_check))
                for d in t.deps:
                    print "--- --> Dependency: %s - %s" % (d.name, str(d.met))
                print
                continue

            print "--> Running test '%s' ...\n" % t.test_name

            # Establish Preconditions
            print "Making sure Asterisk isn't running ..."
            os.system("killall -9 asterisk > /dev/null 2>&1")
            # XXX TODO Hard coded path, gross.
            os.system("rm -f /var/run/asterisk/asterisk.ctl")
            os.system("rm -f /var/run/asterisk/asterisk.pid")
            os.chdir(test_suite_dir)

            # Run Test

            t.run()
            self.total_count += 1
            self.total_time += t.time
            if t.passed is False:
                self.total_failures += 1

    def write_results_xml(self, fn, stdout=False):
        testOutput = ""
        try:
            f = open(TEST_RESULTS, "w")
        except IOError:
            print "Failed to open test results output file: %s" % TEST_RESULTS
            return
        except:
            print "Unexpected error: %s" % sys.exc_info()[0]
            return

        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<testsuite errors="0" tests="%d" time="%.2f" failures="%d" '
                'name="AsteriskTestSuite">\n' %
                (self.total_count, self.total_time, self.total_failures))
        for t in self.tests:
            if t.did_run is False:
                continue
            f.write('\t<testcase time="%.2f" name="%s"' % (t.time, t.test_name))
            if t.passed is True:
                f.write('/>\n')
                continue
            f.write(">\n\t\t%s" % t.failure_message)
            f.write("\n\t</testcase>\n")
        f.write('</testsuite>\n')
        f.close()

        if stdout is True:
            try:
                f = open(TEST_RESULTS, "r")
            except IOError:
                print "Failed to open test results output file: %s" % \
                        TEST_RESULTS
            except:
                print "Unexpected error: %s" % sys.exc_info()[0]
            else:
                print f.read()
                f.close()


def main(argv=None):
    if argv is None:
        args = sys.argv

    usage = "Usage: ./runtests.py [options]"

    parser = optparse.OptionParser(usage=usage)
    parser.add_option("-l", "--list-tests", action="store_true",
            dest="list_tests", default=False,
            help="List tests instead of running them.")
    parser.add_option("-t", "--test",
            dest="test",
            help="Run a single specified test instead of all tests.")
    parser.add_option("-v", "--version",
            dest="version", default=None,
            help="Specify the version of Asterisk rather then detecting it.")
    (options, args) = parser.parse_args(argv)

    # Check to see if this has been executed within a sub directory of an
    # Asterisk source tree.  This is required so that we can execute
    # install and uninstall targets of the Asterisk Makefile in between
    # tests.
    if os.path.exists("../main/asterisk.c") is False:
        print "***  ERROR  ***\n" \
              "runtests has not been executed from within a\n" \
              "subdirectory of an Asterisk source tree.  This\n" \
              "is required for being able to uninstall and install\n" \
              "Asterisk in between tests.\n" \
              "***************\n"
        return 1

    ast_version = AsteriskVersion(options.version)

    #remove any trailing '/' from a test specified with the -t option
    if options.test and options.test[-1] == '/':
        options.test = options.test[0:-1]

    test_suite = TestSuite(ast_version, options)

    if options.list_tests is True:
        print "Asterisk Version: %s\n" % str(ast_version)
        test_suite.list_tests()
        return 0

    print "Running tests for Asterisk %s ...\n" % str(ast_version)

    test_suite.run()

    test_suite.write_results_xml(TEST_RESULTS, stdout=True)

    if not options.test:
        print "\n=== TEST RESULTS ===\n"
        print "PATH: %s\n" % os.getenv("PATH")
        for t in test_suite.tests:
            sys.stdout.write("--> %s --- " % t.test_name)
            if t.did_run is False:
                print "SKIPPED"
                for d in t.deps:
                    print "      --> Dependency: %s -- Met: %s" % (d.name,
                                 str(d.met))
                continue
            if t.passed is True:
                print "PASSED"
            else:
                print "FAILED"

    print "\n"


if __name__ == "__main__":
    sys.exit(main() or 0)
