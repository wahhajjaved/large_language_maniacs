#! /usr/bin/env python

import sys
import time
import re
from pysphere import *
from optparse import OptionParser,OptionGroup

# parameters

# host name
hostname=''

# user
user=''

# password
password=''

# verbose
verbose=False

# timeout
timeout = 0

metrics = [
    'cpu.utilization',
    'cpu.wait',
    'cpu.idle',
    'cpu.latency',
    'cpu.swapwait',
    'cpu.usagemhz',
    'cpu.totalCapacity',
    'mem.usage',
    'mem.swapused',
    'mem.active',
    'disk.write',
    'disk.read',
    'disk.usage',
    'disk.totalLatency',
    'datastore.write',
    'datastore.read',
    'datastore.maxTotalLatency',
    'datastore.totalReadLatency',
    'datastore.totalWriteLatency',
    'net.usage',
    'power.power',
    'power.powerCap',
    ]

# ----------------------------------------------------------------------

class bcolors:
    GRAY = '\033[95m'
    WHITE = '\033[37m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[31m'
    ENDC = '\033[0m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''

# ----------------------------------------------------------------------

def getopts() :
  global hostname,user,password,verbose,summary,clean,vc,mr,debug
  usage = "usage: %prog -H hostname -U username -P password [ -v ]\n\n" \
    "example: %prog -H my-shiny-new-vmware-server -U root -P fakepassword \n\n" \
    "or, verbosely:\n\n" \
    "usage: %prog --host=hostname --user=username --pass=password [ --verbose ]\n"

  parser = OptionParser(usage=usage, version="%prog ")
  group1 = OptionGroup(parser, 'Mandatory parameters')
  group2 = OptionGroup(parser, 'Optional parameters')

  group1.add_option("-H", "--host", dest="host", help="report on HOST", metavar="HOST")
  group1.add_option("-U", "--user", dest="user", help="user to connect as", metavar="USER")
  group1.add_option("-P", "--pass", dest="password", \
      help="password, if password matches file:<path>, first line of given file will be used as password", metavar="PASS")

  group2.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, \
      help="print status messages to stdout (default is to be quiet)")
  group2.add_option("-s", "--summary", action="store_true", dest="summary", default=True, \
      help="print summary statistics for monitoring")
  group2.add_option("-c", "--clean", action="store_true", dest="clean", default=False, \
      help="Clean print")
  group2.add_option("-C", "--vc", action="store_true", dest="vc", default=False, \
      help="Host is Vcenter Server")
  group2.add_option("-m", "--metric", dest="mr", default='None', \
      help="Get single metric")
  group2.add_option("-d", "--debug", dest="debug", action="store_true", default=False, \
      help="Use debug mode")

  parser.add_option_group(group1)
  parser.add_option_group(group2)

  # check input arguments
  if len(sys.argv) < 2:
    print "no parameters specified\n"
    parser.print_help()
    sys.exit(-1)

  (options, args) = parser.parse_args()

  # Making sure all mandatory options appeared.
  mandatories = ['host', 'user', 'password']
  for m in mandatories:
    if not options.__dict__[m]:
      print "mandatory parameter '--" + m + "' is missing\n"
      parser.print_help()
      sys.exit(-1)

    hostname=options.host.lower()
    # if user has put "https://" in front of hostname out of habit, do the right thing
    # hosturl will end up as https://hostname
    if re.match('^https://',hostname):
      hosturl = hostname
    else:
      hosturl = 'https://' + hostname

    user=options.user
    password=options.password
    verbose=options.verbose
    summary=options.summary
    clean=options.clean
    vc=options.vc
    mr=options.mr
    debug=options.debug


# ----------------------------------------------------------------------

getopts()

# ----------------------------------------------------------------------

def coloroutput(name, message) :
    if vc:
        msg = name
    else:
        msg = ''
    if not debug:
        for m in message:
            msg += m + ' '
        if clean:
            print msg
        else:
            print bcolors.BLUE + '[*]' + bcolors.ENDC, "%s %s" % (time.strftime("%Y%m%d %H:%M:%S"), msg)
    else:
        print message

# ----------------------------------------------------------------------


s = VIServer()
s.connect(hostname, user, password)
pm = s.get_performance_manager() 

def get_all(host, name):
    print bcolors.RED + '[+]' + bcolors.ENDC + ' host: ', name
    counters = pm.get_entity_counters(VIMor(host, MORTypes.HostSystem))
    for c in counters:
        print bcolors.YELLOW + '    [-] ', bcolors.ENDC, c, counters[c]
        print bcolors.GREEN + '        [--] ', bcolors.ENDC, pm.get_entity_statistic(host, counters[c]), bcolors.ENDC

def get_metrics(host, name):
    counters = pm.get_entity_counters(VIMor(host, MORTypes.HostSystem))
    if mr == None:
        for m in metrics:
            ms = pm.get_entity_statistic(host, counters[m])[0]
            coloroutput(name, [m, ms.value, ms.unit])
    else:
        ms = pm.get_entity_statistic(host, counters[mr])[0]
        if not debug:
            coloroutput(name, [mr, ms.value, ms.unit])
        else:
            coloroutput(name, ms)

for host, name in s.get_hosts().items():
    if verbose:
        get_all(host, name)
    # else:
    #     get_property(host, name)
    if summary:
        get_metrics(host, name)

s.disconnect()