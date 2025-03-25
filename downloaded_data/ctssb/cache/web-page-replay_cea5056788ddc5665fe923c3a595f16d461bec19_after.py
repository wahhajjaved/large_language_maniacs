#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

description = """
    This is a script for running automated network tests of chrome.
"""

import cookielib
import getpass
import logging
import optparse
import os
import subprocess
import sys
import tempfile
import time
import urllib
import urllib2
import runner_cfg

if sys.version < '2.6':
    print 'Need Python 2.6 or greater.'
    sys.exit(1)


# Some constants for our program

# The location of the Replay script
replay_path = "../replay.py"

# The name of the application we're using
benchmark_application_name = "perftracker"

# The location of the PerfTracker extension
perftracker_extension_path = "./extension"

# Function to login to the Google AppEngine app.
# This code credit to: http://dalelane.co.uk/blog/?p=303
def DoAppEngineLogin(username, password):
    target_authenticated_url = runner_cfg.benchmark_server_url

    # We use a cookie to authenticate with Google App Engine by registering a
    # cookie handler here, this will automatically store the cookie returned
    # when we use urllib2 to open http://<server>.appspot.com/_ah/login
    cookiejar = cookielib.LWPCookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))
    urllib2.install_opener(opener)

    #
    # get an AuthToken from Google accounts
    #
    try:
        auth_uri = 'https://www.google.com/accounts/ClientLogin'
        authreq_data = urllib.urlencode({ "Email":   username,
                                          "Passwd":  password,
                                          "service": "ah",
                                          "source":  benchmark_application_name,
                                          "accountType": "HOSTED_OR_GOOGLE" })
        auth_req = urllib2.Request(auth_uri, data=authreq_data)
        auth_resp = urllib2.urlopen(auth_req)
        auth_resp_body = auth_resp.read()
        # The auth response includes several fields.  The part  we're
        # interested in is the bit after "Auth=".
        auth_resp_dict = dict(x.split("=")
                              for x in auth_resp_body.split("\n") if x)
        authtoken = auth_resp_dict["Auth"]

        # Get a cookie:
        # The call to request a cookie will also automatically redirect us to
        # the page that we want to go to. The cookie jar will automatically
        # provide the cookie when we reach the redirected location.
        serv_args = {}
        serv_args['continue'] = target_authenticated_url
        serv_args['auth']     = authtoken
        full_serv_uri = runner_cfg.benchmark_server_url + "_ah/login?%s" % (urllib.urlencode(serv_args))

        serv_req = urllib2.Request(full_serv_uri)
        serv_resp = urllib2.urlopen(serv_req)
        print "AppEngineLogin succeeded."
    except Exception, e: 
      logging.critical("DoAppEngineLogin failed: %s", e)
      return None
    return full_serv_uri


# Clobber a tmp directory.  Be careful!
def ClobberTmpDirectory(tmpdir):
    # Do sanity checking so we don't clobber the wrong thing
    if len(tmpdir) == 0 or not tmpdir.startswith("/tmp/"):
        return

    for root, dirs, files in os.walk(tmpdir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(tmpdir)


class TestInstance:
    def __init__(self, config, log_level):
        self.config = config
        self.log_level = log_level
        self.proxy_process = None

    def GenerateConfigFile(self, notes):
        # The PerfTracker extension requires this name in order to kick off.
        ext_suffix = "startbenchmark.html"
        self.filename = tempfile.mktemp(suffix=ext_suffix, prefix="")
        f = open(self.filename, "w+")
        def writeln(f, line):
          f.write(line + "\n")
        
        f.write("""
<body>
<textarea id=json></textarea>
<script>
var benchmark = {};
benchmark.user = "";  // XXXMB - fix me.
""")
        if not notes:
            notes = "";

        cmdline = "";    # TODO(mbelshe):  How to plumb this?

        writeln(f, "benchmark.notes = \"" + notes + "\";");
        writeln(f, "benchmark.cmdline = \"" + cmdline + "\";");
        writeln(f, "benchmark.server_url = \"" + runner_cfg.benchmark_server_url + "\";")
        writeln(f, "benchmark.server_login = \"" + options.login_url + "\";")
        writeln(f, "benchmark.iterations = " + str(self.config["iterations"]) + ";")
        writeln(f, "benchmark.download_bandwidth_kbps = " + str(self.config["download_bandwidth_kbps"]) + ";")
        writeln(f, "benchmark.upload_bandwidth_kbps = " + str(self.config["upload_bandwidth_kbps"]) + ";")
        writeln(f, "benchmark.round_trip_time_ms = " + str(self.config["round_trip_time_ms"]) + ";")
        writeln(f, "benchmark.packet_loss_rate = " + str(self.config["packet_loss_rate"]) + ";")
        if self.config["use_spdy"]:
            writeln(f, "benchmark.use_spdy = true;")
        else:
            writeln(f, "benchmark.use_spdy = false;")

        writeln(f, "benchmark.urls = [")
        for url in runner_cfg.configurations["urls"]:
            writeln(f, "  \"" + url + "\",")
 
        writeln(f, "];");
        f.write("""
var raw_json = JSON.stringify(benchmark);
document.getElementById("json").innerHTML = raw_json;
</script>
</body>
""")

        f.close()
        return

    def StartProxy(self):
        logging.debug("Starting Web-Page-Replay")
        log_level = "info"
        if self.log_level:
            log_level = self.log_level
        cmdline = [
          replay_path,
          "-x",  # Disables DNS intercepting
          "-d", str(self.config["download_bandwidth_kbps"]) + "KBit/s",
          "-u", str(self.config["upload_bandwidth_kbps"]) + "KBit/s",
          "-m", str(self.config["round_trip_time_ms"]),
          "-p", str(self.config["packet_loss_rate"] / 100.0),
          "-l", log_level,
          runner_cfg.replay_data_archive
        ]
        logging.debug("Starting replay proxy: %s", str(cmdline))
        self.proxy_process = subprocess.Popen(cmdline)

        # We just changed the system resolv.conf.  If we go too fast here
	# it may still be pointing at the old version...  linux sux
        time.sleep(5)

    def StopProxy(self):
        if self.proxy_process:
            logging.debug("Stopping Web-Page-Replay")
            self.proxy_process.send_signal(2)  # SIGINT
            self.proxy_process.wait()

    def RunChrome(self, chrome_cmdline):
        start_file_url = "file://" + self.filename

        profile_dir = tempfile.mkdtemp(prefix="chrome.profile.");

        try:
            cmdline = [
              runner_cfg.chrome_path,
              "--host-resolver-rules=MAP * 127.0.0.1,EXCLUDE " + runner_cfg.benchmark_server, 
              "--disable-background-networking",
              "--enable-benchmarking",
              "--enable-logging",
              "--load-extension=" + perftracker_extension_path,
              "--log-level=0",
              "--no-first-run",
              "--no-js-randomization",
              "--user-data-dir=" + profile_dir,
            ]
            if chrome_cmdline:
              cmdline.extend(chrome_cmdline.split(" "))
            cmdline.append(start_file_url)
  
            logging.debug("Starting chrome: %s", str(cmdline))
            chrome = subprocess.Popen(cmdline)
            chrome.wait();
        finally:
            ClobberTmpDirectory(profile_dir)

    def RunTest(self, notes, chrome_cmdline):
        try:
            self.GenerateConfigFile(notes)
            self.StartProxy()
            self.RunChrome(chrome_cmdline)
        finally:
            logging.debug("Cleaning up test")
            self.StopProxy()
            self.Cleanup()

    def Cleanup(self):
        os.remove(self.filename)

def main(options):
    iterations = runner_cfg.configurations["iterations"]
    for plr in runner_cfg.configurations["packet_loss_rates"]:
        for network in runner_cfg.configurations["networks"]:
            for rtt in runner_cfg.configurations["round_trip_times"]:
                config = {
                    "iterations"             : iterations,
                    "download_bandwidth_kbps": network["download_bandwidth_kbps"],
                    "upload_bandwidth_kbps"  : network["upload_bandwidth_kbps"],
                    "round_trip_time_ms"     : rtt,
                    "packet_loss_rate"       : plr,
                    "use_spdy"               : False,
                }
                logging.debug("Running test configuration: %s", str(config))
                test = TestInstance(config, options.log_level)
                test.RunTest(options.notes, options.chrome_cmdline)

if __name__ == '__main__':
    log_levels = ('debug', 'info', 'warning', 'error', 'critical')

    class PlainHelpFormatter(optparse.IndentedHelpFormatter):
        def format_description(self, description):
            if description:
                return description + '\n'
            else:
                return ''

    option_parser = optparse.OptionParser(
            usage='%prog -u user',
            formatter=PlainHelpFormatter(),
            description=description,
            epilog='')

    option_parser.add_option('-l', '--log_level', default='info',
            action='store',
            type='choice',
            choices=log_levels,
            help='Minimum verbosity level to log')
    option_parser.add_option('-f', '--log_file', default=None,
            action='store',
            type='string',
            help='Log file to use in addition to writting logs to stderr.')
    option_parser.add_option('-c', '--chrome_cmdline', default=None,
            action='store',
            type='string',
            help='Command line options to pass to chrome.')
    option_parser.add_option('-n', '--notes', default=None,
            action='store',
            type='string',
            help='Notes to record with this test run.')
    option_parser.add_option('-u', '--user', default=None,
            action='store',
            type='string',
            help='Username for logging into appengine.')

    options, args = option_parser.parse_args()

    # Collect login credentials and verify
    if not options.user:
      option_parser.error('Must specify an appengine user for login')
    options.password = getpass.getpass(options.user + " password: ");
    options.login_url = DoAppEngineLogin(options.user, options.password)
    if not options.login_url:
      exit(-1)

    log_level = logging.__dict__[options.log_level.upper()]
    logging.basicConfig(level=log_level)
    if options.log_file:
        fh = logging.FileHandler(options.log_file)
        fh.setLevel(log_level)
        logging.getLogger('').addHandler(fh)

    sys.exit(main(options))
