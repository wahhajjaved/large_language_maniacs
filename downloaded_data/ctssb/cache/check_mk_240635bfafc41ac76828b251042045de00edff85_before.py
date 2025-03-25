#!/usr/bin/python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2010             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# ails.  You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.

import socket, os, sys, time, re, signal, math

# Python 2.3 does not have 'set' in normal namespace.
# But it can be imported from 'sets'
try:
    set()
except NameError:
    from sets import Set as set


# colored output, if stdout is a tty
if sys.stdout.isatty():
    tty_red       = '\033[31m'
    tty_green     = '\033[32m'
    tty_yellow    = '\033[33m'
    tty_blue      = '\033[34m'
    tty_magenta   = '\033[35m'
    tty_cyan      = '\033[36m'
    tty_white     = '\033[37m'
    tty_bgblue    = '\033[44m'
    tty_bgmagenta = '\033[45m'
    tty_bgwhite   = '\033[47m'
    tty_bold      = '\033[1m'
    tty_underline = '\033[4m'
    tty_normal    = '\033[0m'
    tty_ok        = tty_green + tty_bold + 'OK' + tty_normal
    def tty(fg=-1, bg=-1, attr=-1):
        if attr >= 0:
            return "\033[3%d;4%d;%dm" % (fg, bg, attr)
        elif bg >= 0:
            return "\033[3%d;4%dm" % (fg, bg)
        elif fg >= 0:
            return "\033[3%dm" % fg
        else:
            return tty_normal
else:
    tty_red       = ''
    tty_green     = ''
    tty_yellow    = ''
    tty_blue      = ''
    tty_magenta   = ''
    tty_cyan      = ''
    tty_white     = ''
    tty_bgblue    = ''
    tty_bgmagenta = ''
    tty_bold      = ''
    tty_underline = ''
    tty_normal    = ''
    tty_ok        = 'OK'
    def tty(fg=-1, bg=-1, attr=-1):
        return ''


# global variables used to cache temporary values
g_dns_cache                  = {}
g_infocache                  = {} # In-memory cache of host info.
g_agent_already_contacted    = {} # do we have agent data from this host?
g_counters                   = {} # storing counters of one host
g_hostname                   = "unknown" # Host currently being checked
g_aggregated_service_results = {}   # store results for later submission
compiled_regexes             = {}   # avoid recompiling regexes
nagios_command_pipe          = None # Filedescriptor to open nagios command pipe.
g_single_oid_hostname        = None
g_single_oid_cache           = {}
g_broken_snmp_hosts          = set([])
g_broken_agent_hosts         = set([])


# variables set later by getopt
opt_dont_submit              = False
opt_showplain                = False
opt_showperfdata             = False
opt_use_cachefile            = False
opt_no_tcp                   = False
opt_no_cache                 = False
opt_no_snmp_hosts            = False
opt_use_snmp_walk            = False
opt_cleanup_autochecks       = False
fake_dns                     = False


class MKGeneralException(Exception):
    def __init__(self, reason):
        self.reason = reason
    def __str__(self):
        return self.reason

class MKCounterWrapped(Exception):
    def __init__(self, countername, reason):
        self.name = countername
        self.reason = reason
    def __str__(self):
        return '%s: %s' % (self.name, self.reason)

class MKAgentError(Exception):
    def __init__(self, reason):
        self.reason = reason
    def __str__(self):
        return self.reason

class MKSNMPError(Exception):
    def __init__(self, reason):
        self.reason = reason
    def __str__(self):
        return self.reason

#   +----------------------------------------------------------------------+
#   |         _                                    _   _                   |
#   |        / \   __ _  __ _ _ __ ___  __ _  __ _| |_(_) ___  _ __        |
#   |       / _ \ / _` |/ _` | '__/ _ \/ _` |/ _` | __| |/ _ \| '_ \       |
#   |      / ___ \ (_| | (_| | | |  __/ (_| | (_| | |_| | (_) | | | |      |
#   |     /_/   \_\__, |\__, |_|  \___|\__, |\__,_|\__|_|\___/|_| |_|      |
#   |             |___/ |___/          |___/                               |
#   +----------------------------------------------------------------------+

# Compute the name of a summary host
def summary_hostname(hostname):
    return aggr_summary_hostname % hostname

# Updates the state of an aggregated service check from the output of
# one of the underlying service checks. The status of the aggregated
# service will be updated such that the new status is the maximum
# (crit > unknown > warn > ok) of all underlying status. Appends the output to
# the output list and increases the count by 1.
def store_aggregated_service_result(hostname, detaildesc, aggrdesc, newstatus, newoutput):
    global g_aggregated_service_results
    count, status, outputlist = g_aggregated_service_results.get(aggrdesc, (0, 0, []))
    if status_worse(newstatus, status):
        status = newstatus
    if newstatus > 0 or aggregation_output_format == "multiline":
        outputlist.append( (newstatus, detaildesc, newoutput) )
    g_aggregated_service_results[aggrdesc] = (count + 1, status, outputlist)

def status_worse(newstatus, status):
    if status == 2:
        return False # nothing worse then critical
    elif newstatus == 2:
        return True  # nothing worse then critical
    else:
        return newstatus > status # 0 < 1 < 3 are in correct order

# Submit the result of all aggregated services of a host
# to Nagios. Those are stored in g_aggregated_service_results
def submit_aggregated_results(hostname):
    if not host_is_aggregated(hostname):
        return

    if opt_verbose:
        print "\n%s%sAggregates Services:%s" % (tty_bold, tty_blue, tty_normal)
    global g_aggregated_service_results
    items = g_aggregated_service_results.items()
    items.sort()
    aggr_hostname = summary_hostname(hostname)
    for servicedesc, (count, status, outputlist) in items:
        if aggregation_output_format == "multiline":
            longoutput = ""
            statuscounts = [ 0, 0, 0, 0 ]
            for itemstatus, item, output in outputlist:
                longoutput += '\\n%s: %s' % (item, output)
                statuscounts[itemstatus] = statuscounts[itemstatus] + 1
            summarytexts = [ "%d service%s %s" % (x[0], x[0] != 1 and "s" or "", x[1])
                           for x in zip(statuscounts, ["OK", "WARN", "CRIT", "UNKNOWN" ]) if x[0] > 0 ]
            text = ", ".join(summarytexts) + longoutput
        else:
            if status == 0:
                text = "OK - %d services OK" % count
            else:
                text = " *** ".join([ item + " " + output for itemstatus, item, output in outputlist ])

        if not opt_dont_submit and nagios_command_pipe:
            nagios_command_pipe.write("[%d] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%d;%s\n" %
                (int(time.time()), aggr_hostname, servicedesc, status, text))
            nagios_command_pipe.flush()

        if opt_verbose:
            color = { 0: tty_green, 1: tty_yellow, 2: tty_red, 3: tty_magenta }[status]
            lines = text.split('\\n')
            print "%-20s %s%s%-70s%s" % (servicedesc, tty_bold, color, lines[0], tty_normal)
            if len(lines) > 1:
                for line in lines[1:]:
                    print "  %s" % line
                print "-------------------------------------------------------------------------------"



def submit_check_mk_aggregation(hostname, status, output):
    if not host_is_aggregated(hostname):
        return

    if not opt_dont_submit:
        open_command_pipe()
        if nagios_command_pipe:
            nagios_command_pipe.write("[%d] PROCESS_SERVICE_CHECK_RESULT;%s;Check_MK;%d;%s\n" %
                  (int(time.time()), summary_hostname(hostname), status, output))
            nagios_command_pipe.flush()
    if opt_verbose:
        color = { 0: tty_green, 1: tty_yellow, 2: tty_red, 3: tty_magenta }[status]
        print "%-20s %s%s%-70s%s" % ("Check_MK", tty_bold, color, output, tty_normal)


#   +----------------------------------------------------------------------+
#   |                 ____      _         _       _                        |
#   |                / ___| ___| |_    __| | __ _| |_ __ _                 |
#   |               | |  _ / _ \ __|  / _` |/ _` | __/ _` |                |
#   |               | |_| |  __/ |_  | (_| | (_| | || (_| |                |
#   |                \____|\___|\__|  \__,_|\__,_|\__\__,_|                |
#   |                                                                      |
#   +----------------------------------------------------------------------+


# This is the main function for getting information needed by a
# certain check. It is called once for each check type. For SNMP this
# is needed since not all data for all checks is fetched at once. For
# TCP based checks the first call to this function stores the
# retrieved data in a global variable. Later calls to this function
# get their data from there.

# If the host is a cluster, the information is fetched from all its
# nodes an then merged per-check-wise.

# For cluster checks we do not have an ip address from Nagios
# We need to do DNS-lookups in that case :-(. We could avoid that at
# least in case of precompiled checks. On the other hand, cluster checks
# usually use existing cache files, if check_mk is not misconfigured,
# and thus do no network activity at all...

def get_host_info(hostname, ipaddress, checkname):
    nodes = nodes_of(hostname)

    if nodes != None:
        info = []
        at_least_one_without_exception = False
        exception_texts = []
        global opt_use_cachefile
        opt_use_cachefile = True
	is_snmp_error = False
        for node in nodes:
            # If an error with the agent occurs, we still can (and must)
            # try the other node.
            try:
                ipaddress = lookup_ipaddress(node)
                info += get_realhost_info(node, ipaddress, checkname, cluster_max_cachefile_age)
                at_least_one_without_exception = True
            except MKAgentError, e:
		if str(e) != "": # only first error contains text
                    exception_texts.append(str(e))
		g_broken_agent_hosts.add(node)
            except MKSNMPError, e:
		if str(e) != "": # only first error contains text
		    exception_texts.append(str(e))
		g_broken_snmp_hosts.add(node)
		is_snmp_error = True
        if not at_least_one_without_exception:
	    if is_snmp_error:
                raise MKSNMPError(", ".join(exception_texts))
            else:
                raise MKAgentError(", ".join(exception_texts))
        return info
    else:
        return get_realhost_info(hostname, ipaddress, checkname, check_max_cachefile_age)

# Gets info from a real host (not a cluster). There are three possible
# ways: TCP, SNMP and external command.  This function raises
# MKAgentError or MKSNMPError, if there could not retrieved any data. It returns [],
# if the agent could be contacted but the data is empty (no items of
# this check type).
#
# What makes the thing a bit tricky is the fact, that data
# might have to be fetched via SNMP *and* TCP for one host
# (even if this is unlikeyly)
#
# This function assumes, that each check type is queried
# only once for each host.
def get_realhost_info(hostname, ipaddress, checkname, max_cache_age):
    info = get_cached_hostinfo(hostname)
    if info and info.has_key(checkname):
        return info[checkname]

    cache_relpath = hostname + "." + checkname

    # Is this an SNMP table check? Then snmp_info specifies the OID to fetch
    oid_info = snmp_info.get(checkname)
    if oid_info:
        content = read_cache_file(cache_relpath, max_cache_age)
        if content:
            return eval(content)
        # Not cached -> need to get info via SNMP

        # Try to contact host only once
	if hostname in g_broken_snmp_hosts:
	    raise MKSNMPError("")

        # New in 1.1.3: oid_info can now be a list: Each element
        # of that list is interpreted as one real oid_info, fetches
        # a separate snmp table. The overall result is then the list
        # of these results.
        if type(oid_info) == list:
            table = [ get_snmp_table(hostname, ipaddress, entry) for entry in oid_info ]
            # if at least one query fails, we discard the hole table
            if None in table:
                table = None
        else:
            table = get_snmp_table(hostname, ipaddress, oid_info)
        store_cached_checkinfo(hostname, checkname, table)
        write_cache_file(cache_relpath, repr(table) + "\n")
        return table

    # now try SNMP explicity values
    try:
        mib, baseoid, suffixes = snmp_info_single[checkname]
    except:
        baseoid = None
    if baseoid:
        content = read_cache_file(cache_relpath, max_cache_age)
        if content:
            return eval(content)
        table = get_snmp_explicit(hostname, ipaddress, mib, baseoid, suffixes)
        store_cached_checkinfo(hostname, checkname, table)
        write_cache_file(cache_relpath, repr(table) + "\n")
        return table

    # No SNMP check. Then we must contact the check_mk_agent. Have we already
    # to get data from the agent? If yes we must not do that again! Even if
    # no cache file is present
    if g_agent_already_contacted.has_key(hostname):
	raise MKAgentError("")

    g_agent_already_contacted[hostname] = True
    store_cached_hostinfo(hostname, []) # leave emtpy info in case of error

    output = get_agent_info(hostname, ipaddress, max_cache_age)
    if len(output) == 0:
        raise MKAgentError("Empty output from agent")
    elif len(output) < 16:
        raise MKAgentError("Too short output from agent: '%s'" % output)

    lines = [ l.strip() for l in output.split('\n') ]
    info = parse_info(lines)
    store_cached_hostinfo(hostname, info)
    return info.get(checkname, []) # return only data for specified check


def read_cache_file(relpath, max_cache_age):
    # Cache file present, caching allowed? -> read from cache
    cachefile = tcp_cache_dir + "/" + relpath
    if os.path.exists(cachefile) and (
        (opt_use_cachefile and ( not opt_no_cache ) )
        or (simulation_mode and not opt_no_cache) ):
        if cachefile_age(cachefile) <= max_cache_age or simulation_mode:
            f = open(cachefile, "r")
            result = f.read(10000000)
            f.close()
            if len(result) > 0:
                if opt_verbose:
                    sys.stderr.write("Using data from cachefile %s.\n" % cachefile)
                return result
        elif opt_verbose:
            sys.stderr.write("Skipping cache file %s: Too old\n" % cachefile)

    if simulation_mode and not opt_no_cache:
        raise MKGeneralException("Simulation mode and no cachefile present.")

    if opt_no_tcp:
        raise MKGeneralException("Cache file '%s' missing or too old. TCP disallowed by you." % cachefile)


def write_cache_file(relpath, output):
    cachefile = tcp_cache_dir + "/" + relpath
    if not os.path.exists(tcp_cache_dir):
        try:
            os.makedirs(tcp_cache_dir)
        except Exception, e:
            raise MKGeneralException("Cannot create directory %s: %s" % (tcp_cache_dir, e))
    try:
        # write retrieved information to cache file - if we are not root.
        # We assume that Nagios never runs as root.
        if not i_am_root():
            f = open(cachefile, "w+")
            f.write(output)
            f.close()
    except Exception, e:
        raise MKGeneralException("Cannot write cache file %s: %s" % (cachefile, e))


# Get information about a real host (not a cluster node) via TCP
# or by executing an external programm. ipaddress may be None.
# In that case it will be looked up if needed. Also caching will
# be handled here
def get_agent_info(hostname, ipaddress, max_cache_age):
    result = read_cache_file(hostname, max_cache_age)
    if result:
        return result

    # Try to contact every host only once
    if hostname in g_broken_agent_hosts:
	raise MKAgentError("")

    # If the host ist listed in datasource_programs the data from
    # that host is retrieved by calling an external program (such
    # as ssh or rsy) instead of a TCP connect.
    commandline = get_datasource_program(hostname, ipaddress)
    if commandline:
        output = get_agent_info_program(commandline)
    else:
        output = get_agent_info_tcp(hostname, ipaddress)

    # Got new data? Write to cache file
    write_cache_file(hostname, output)

    return output

# Get data in case of external programm
def get_agent_info_program(commandline):
    if opt_verbose:
        sys.stderr.write("Calling external programm %s\n" % commandline)
    try:
        sout = os.popen(commandline + " 2>/dev/null")
        output = sout.read()
        exitstatus = sout.close()
    except Exception, e:
        raise MKAgentError("Could not execute '%s': %s" % (commandline, e))

    if exitstatus:
        if exitstatus >> 8 == 127:
            raise MKAgentError("Programm '%s' not found (exit code 127)" % (commandline,))
        else:
            raise MKAgentError("Programm '%s' exited with code %d" % (commandline, exitstatus >> 8))
    return output

# Get data in case of TCP
def get_agent_info_tcp(hostname, ipaddress):
    if not ipaddress:
        raise MKGeneralException("Cannot contact agent: host '%s' has no IP address." % hostname)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(tcp_connect_timeout)
        except:
            pass # some old Python versions lack settimeout(). Better ignore than fail
        s.connect((ipaddress, agent_port))
        try:
            s.setblocking(1)
        except:
            pass
        output = ""
        while True:
            out = s.recv(4096, socket.MSG_WAITALL)
            if out and len(out) > 0:
                output += out
            else:
                break
        s.close()
        return output
    except Exception, e:
        raise MKAgentError("Cannot get data from TCP port %s:%d: %s" %
                           (ipaddress, agent_port, e))


# Gets all information about one host so far cached.
# Returns None if nothing has been stored so far
def get_cached_hostinfo(hostname):
    global g_infocache
    return g_infocache.get(hostname, None)

# store complete information about a host
def store_cached_hostinfo(hostname, info):
    global g_infocache
    oldinfo = get_cached_hostinfo(hostname)
    if oldinfo:
        oldinfo.update(info)
        g_infocache[hostname] = oldinfo
    else:
        g_infocache[hostname] = info

# store information about one check type
def store_cached_checkinfo(hostname, checkname, table):
    global g_infocache
    info = get_cached_hostinfo(hostname)
    if info:
        info[checkname] = table
    else:
        g_infocache[hostname] = { checkname: table }

# Split agent output in chunks, splits lines by whitespaces
def parse_info(lines):
    info = {}
    chunk = []
    chunkoptions = {}
    separator = None
    for line in lines:
        if line[:3] == '<<<' and line[-3:] == '>>>':
            chunkheader = line[3:-3]
            # chunk header has format <<<name:opt1(args):opt2:opt3(args)>>>
            headerparts = chunkheader.split(":")
            chunkname = headerparts[0]
            chunkoptions = {}
            for o in headerparts[1:]:
                opt_parts = o.split("(")
                opt_name = opt_parts[0]
                if len(opt_parts) > 1:
                    opt_args = opt_parts[1][:-1]
                else:
                    opt_args = None
                chunkoptions[opt_name] = opt_args

            chunk = info.get(chunkname, None)
            if chunk == None: # chunk appears in output for the first time
                chunk = []
                info[chunkname] = chunk
            try:
                separator = chr(int(chunkoptions["sep"]))
            except:
                separator = None
        elif line != '':
            chunk.append(line.split(separator))
    return info


def lookup_ipaddress(hostname):
    if fake_dns:
        return fake_dns

    elif simulation_mode or opt_use_snmp_walk or is_usewalk_host(hostname):
        return "127.0.0.1"
    elif hostname in g_dns_cache:
        return g_dns_cache[hostname]
    else:
        ipa = ipaddresses.get(hostname)
        if ipa:
            return ipa
        else:
            try:
                ipa = socket.gethostbyname(hostname)
            except:
                g_dns_cache[hostname] = None
                raise
            g_dns_cache[hostname] = ipa
            return ipa

def cachefile_age(filename):
    try:
        return time.time() - os.stat(filename)[8]
    except Exception, e:
        raise MKGeneralException("Cannot determine age of cache file %s: %s" \
                                 % (filename, e))
        return -1

#   +----------------------------------------------------------------------+
#   |                ____                  _                               |
#   |               / ___|___  _   _ _ __ | |_ ___ _ __ ___                |
#   |              | |   / _ \| | | | '_ \| __/ _ \ '__/ __|               |
#   |              | |__| (_) | |_| | | | | ||  __/ |  \__ \               |
#   |               \____\___/ \__,_|_| |_|\__\___|_|  |___/               |
#   |                                                                      |
#   +----------------------------------------------------------------------+


# Variable                 time_t    value
# netctr.eth.tx_collisions 112354335 818
def load_counters(hostname):
    global g_counters
    filename = counters_directory + "/" + hostname
    try:
        g_counters = eval(file(filename).read())
    except:
        # Try old syntax
        try:
            lines = file(filename).readlines()
            for line in lines:
                line = line.split()
                g_counters[' '.join(line[0:-2])] = ( int(line[-2]), int(line[-1]) )
        except:
            g_counters = {}

def get_counter(countername, this_time, this_val):
    global g_counters

    # First time we see this counter? Do not return
    # any data!
    if not countername in g_counters:
        g_counters[countername] = (this_time, this_val)
        # Do not suppress this check on check_mk -nv
        if opt_dont_submit:
            return 1.0, 0.0
        raise MKCounterWrapped(countername, 'Counter initialization')

    last_time, last_val = g_counters.get(countername)
    timedif = this_time - last_time
    if timedif <= 0: # do not update counter
        # Do not suppress this check on check_mk -nv
        if opt_dont_submit:
            return 1.0, 0.0
        raise MKCounterWrapped(countername, 'No time difference')

    # update counter for next time
    g_counters[countername] = (this_time, this_val)

    valuedif = this_val - last_val
    if valuedif < 0:
        # Do not try to handle wrapper counters. We do not know
        # wether they are 32 or 64 bit. It also could happen counter
        # reset (reboot, etc.). Better is to leave this value undefined
        # and wait for the next check interval.
        # Do not suppress this check on check_mk -nv
        if opt_dont_submit:
            return 1.0, 0.0
        raise MKCounterWrapped(countername, 'Value overflow')

    per_sec = float(valuedif) / timedif
    return timedif, per_sec


def get_average(itemname, this_time, this_val, backlog):

    # first call: take current value as average
    if not itemname in g_counters:
        g_counters[itemname] = (this_time, this_val)
        return 1.0, this_val

    # Get previous value and time difference
    last_time, last_val = g_counters.get(itemname)
    timedif = this_time - last_time

    # compute weight, but how?
    weight = math.e ** (-timedif / backlog)

    new_val = last_val * weight + this_val * (1 - weight)
    g_counters[itemname] = (this_time, new_val)
    return timedif, new_val


def save_counters(hostname):
    if not opt_dont_submit and not i_am_root(): # never writer counters as root
        global g_counters
        filename = counters_directory + "/" + hostname
        try:
            if not os.path.exists(counters_directory):
                os.makedirs(counters_directory)
            file(filename, "w").write("%r\n" % g_counters)
        except Exception, e:
            raise MKGeneralException("User %s cannot write to %s: %s" % (username(), filename, e))

# writelines([ "%s %d %d\n" % (i[0], i[1][0], i[1][1]) for i in g_counters.items() ])


#   +----------------------------------------------------------------------+
#   |               ____ _               _    _                            |
#   |              / ___| |__   ___  ___| | _(_)_ __   __ _                |
#   |             | |   | '_ \ / _ \/ __| |/ / | '_ \ / _` |               |
#   |             | |___| | | |  __/ (__|   <| | | | | (_| |               |
#   |              \____|_| |_|\___|\___|_|\_\_|_| |_|\__, |               |
#   |                                                 |___/                |
#   |                                                                      |
#   | All about performing the actual checks and send the data to Nagios.  |
#   +----------------------------------------------------------------------+

# This is the main check function - the central entry point to all and
# everything
def do_check(hostname, ipaddress):
    if opt_verbose:
        sys.stderr.write("Check_mk version %s\n" % check_mk_version)

    start_time = time.time()

    try:
        load_counters(hostname)
        agent_version, num_success, num_errors, problems = do_all_checks_on_host(hostname, ipaddress)
        save_counters(hostname)
        if problems:
	    output = "CRIT - %s" % problems
            status = 2
        elif num_errors > 0 and num_success > 0:
            output = "WARNING - Got only %d out of %d infos" % (num_success, num_success + num_errors)
            status = 1
        elif num_errors > 0:
            output = "CRIT - Got no information from host"
            status = 2
        elif agent_min_version and agent_version < agent_min_version:
            output = "WARNING - old plugin version %s (should be at least %s)" % (agent_version, agent_min_version)
            status = 1
        else:
            output = "OK - Agent version %s" % (agent_version, num_success)
            status = 0

    except MKGeneralException, e:
        if opt_debug:
            raise
        output = "UNKNOWN - %s" % e
        status = 3

    if aggregate_check_mk:
        try:
            submit_check_mk_aggregation(hostname, status, output)
        except:
            if opt_debug:
                raise

    run_time = time.time() - start_time
    output += ", execution time %.1f sec|execution_time=%.3f\n" % (run_time, run_time)
    sys.stdout.write(output)
    sys.exit(status)

def check_unimplemented(checkname, params, info):
    return (3, 'UNKNOWN - Check not implemented')

# Loops over all checks for a host, gets the data, calls the check
# function that examines that data and sends the result to Nagios
def do_all_checks_on_host(hostname, ipaddress):
    global g_aggregated_service_results
    g_aggregated_service_results = {}
    global g_hostname
    g_hostname = hostname
    num_success = 0
    num_errors = 0
    check_table = get_sorted_check_table(hostname)
    problems = []
    for checkname, item, params, description, info in check_table:
        # In case of a precompiled check table info is the aggrated
        # service name. In the non-precompiled version there are the dependencies
        if type(info) == str:
            aggrname = info
        else:
            aggrname = aggregated_service_name(hostname, description)

        infotype = checkname.split('.')[0]
        try:
	    info = get_host_info(hostname, ipaddress, infotype)
        except MKSNMPError, e:
	    if str(e):
	        problems.append(str(e))
            num_errors += 1
	    g_broken_snmp_hosts.add(hostname)
	    continue

        except MKAgentError, e:
	    if str(e):
                problems.append(str(e))
            num_errors += 1
	    g_broken_agent_hosts.add(hostname)
	    continue

        if info or info == []:
            num_success += 1
            try:
                check_funktion = check_info[checkname][0]
            except:
                check_funktion = check_unimplemented

            try:
                dont_submit = False
                result = check_funktion(item, params, info)
            # handle check implementations that do not yet support the
            # handling of wrapped counters via exception. Do not submit
            # any check result in that case:
            except MKCounterWrapped, e:
                if opt_verbose:
                    print "Counter wrapped, not handled by check, ignoring this check result: %s" % e
                dont_submit = True
            except Exception, e:
                result = (3, "UNKNOWN - invalid output from agent, invalid check parameters or error in implementation of check %s. Please set <tt>debug_log</tt> to a filename in <tt>main.mk</tt> for enabling exception logging." % checkname)
                if debug_log:
                    try:
                        import traceback, pprint
                        l = file(debug_log, "a")
                        l.write(("Invalid output from plugin or error in check:\n"
                                "  Check_MK Version: %s\n"
                                "  Date:             %s\n"
                                "  Host:             %s\n"
                                "  Service:          %s\n"
                                "  Check type:       %s\n"
                                "  Item:             %r\n"
                                "  Parameters:       %s\n"
                                "  %s\n"
                                "  Agent info:       %s\n\n") % (
                                check_mk_version,
                                time.strftime("%Y-%d-%m %H:%M:%S"),
                                hostname, description, checkname, item, pprint.pformat(params),
                                traceback.format_exc().replace('\n', '\n      '),
                                pprint.pformat(info)))
                    except:
                        pass

                if opt_debug:
                    raise
            if not dont_submit:
                submit_check_result(hostname, description, result, aggrname)
        else:
            num_errors += 1

    submit_aggregated_results(hostname)

    try:
        if not is_snmp_host(hostname):
            version_info = get_host_info(hostname, ipaddress, 'check_mk')
            # TODO: remove this later, when all agents have been converted
            if not version_info:
                version_info = get_host_info(hostname, ipaddress, 'mknagios')
            agent_version = version_info[0][1]
        else:
            agent_version = "(unknown)"
    except MKAgentError, e:
	g_broken_agent_hosts.add(hostname)
        agent_version = "(unknown)"
    except:
        agent_version = "(unknown)"
    return agent_version, num_success, num_errors, ", ".join(problems)

def nagios_pipe_open_timeout(signum, stackframe):
    raise IOError("Timeout while opening pipe")

def open_command_pipe():
    global nagios_command_pipe
    if nagios_command_pipe == None:
        if not os.path.exists(nagios_command_pipe_path):
            nagios_command_pipe = False # False means: tried but failed to open
            raise MKGeneralException("Missing Nagios command pipe '%s'" % nagios_command_pipe_path)
        else:
            try:
                signal.signal(signal.SIGALRM, nagios_pipe_open_timeout)
                signal.alarm(3) # three seconds to open pipe
                nagios_command_pipe =  file(nagios_command_pipe_path, 'w')
                signal.alarm(0) # cancel alarm
            except Exception, e:
                nagios_command_pipe = False
                raise MKGeneralException("Error writing to command pipe: %s" % e)



def none_to_empty(x):
    if x == None:
        return ""
    else:
        return x

def submit_check_result(host, servicedesc, result, sa):
    global nagios_command_pipe
    # [<timestamp>] PROCESS_SERVICE_CHECK_RESULT;<host_name>;<svc_description>;<return_code>;<plugin_output>

    # Aggregated service -> store for later
    if sa != "":
        store_aggregated_service_result(host, servicedesc, sa, result[0], result[1])

    # performance data - if any - is stored in the third part of the result
    perftexts = [];
    perftext = ""

    if len(result) > 2:
        perfdata = result[2]
        # Check may append the name of the check command to the
        # list of perfdata. It is of type string. And it might be
        # needed by the graphing tool in order to choose the correct
        # template. Currently this is used only by mrpe.
        if len(perfdata) > 0 and type(perfdata[-1]) == str:
            check_command = perfdata[-1]
            del perfdata[-1]
        else:
            check_command = None

        for p in perfdata:
            # replace None with "" and fill up to 6 values
            p = (map(none_to_empty, p) + ['','','',''])[0:6]
            perftexts.append("%s=%s;%s;%s;%s;%s" %  tuple(p) )
        if perftexts != [] and not direct_rrd_update(host, servicedesc, perfdata):
            if check_command and perfdata_format == "pnp":
                perftexts.append("[%s]" % check_command)
            perftext = "|" + (" ".join(perftexts))

    if not opt_dont_submit:
        open_command_pipe()
        if nagios_command_pipe:
            nagios_command_pipe.write("[%d] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%d;%s\n" %
                                   (int(time.time()), host, servicedesc, result[0], result[1] + perftext)  )
            # Important: Nagios needs the complete command in one single write() block!
            # Python buffers and sends chunks of 4096 bytes, if we do not flush.
            nagios_command_pipe.flush()

    if opt_verbose:
        if opt_showperfdata:
            p = ' (%s)' % (" ".join(perftexts))
        else:
            p = ''
        color = { 0: tty_green, 1: tty_yellow, 2: tty_red, 3: tty_magenta }[result[0]]
        print "%-20s %s%s%-56s%s%s" % (servicedesc, tty_bold, color, result[1], tty_normal, p)

def direct_rrd_update(host, servicedesc, perfdata):
    if do_rrd_update:
        path = rrd_path + "/" + host.replace(":", "_") + "/" + servicedesc.replace("/", "_").replace(" ", "_")
        # check existance and age of xml file
        try:
            xml_age = os.stat(path + ".xml").st_mtime
            if time.time() - xml_age > (3600 + os.getpid() % 1800):
                return False # XML file too old
            numbers = [ str(p[1]).rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_ ") for p in perfdata ]
            # sys.stderr.write("Schreibe rrdtool.update(" + path + ".rrd" + ", N:" + ":".join(numbers))
            rrdtool.update(path + ".rrd", "N:" + ":".join(numbers))
        except:
            return False # Update not successfull or XML file missing or too old
        return True
    return False


#   +----------------------------------------------------------------------+
#   |                  _   _      _                                        |
#   |                 | | | | ___| |_ __   ___ _ __ ___                    |
#   |                 | |_| |/ _ \ | '_ \ / _ \ '__/ __|                   |
#   |                 |  _  |  __/ | |_) |  __/ |  \__ \                   |
#   |                 |_| |_|\___|_| .__/ \___|_|  |___/                   |
#   |                              |_|                                     |
#   +----------------------------------------------------------------------+

# determine the name of the current user. This involves
# a lookup of /etc/passwd. Because this function is needed
# only in general error cases, the pwd module is imported
# here - not globally
def username():
    import pwd
    return pwd.getpwuid(os.getuid())[0]

def i_am_root():
    return os.getuid() == 0

# Returns the nodes of a cluster, or None if hostname is
# not a cluster
def nodes_of(hostname):
    for tagged_hostname, nodes in clusters.items():
        if hostname == tagged_hostname.split("|")[0]:
            return nodes
    return None

# needed by df, df_netapp and vms_df and maybe others in future:
# compute warning and critical levels. Takes into account the size of
# the filesystem and the magic number. Since the size is only known at
# check time this function's result cannot be precompiled.
def get_filesystem_levels(host, mountpoint, size_gb, params):
    # If no magic factor is given, we use the neutral factor 1.0
    if len(params) < 3:
        params = (params[0], params[1], 1.0)
        lowest_warning_level = 0
        lowest_critical_level = 0
    else:
        lowest_warning_level = df_lowest_warning_level
        lowest_critical_level = df_lowest_critical_level

    (warn, crit, magicfactor) = params    # warn and crit are in percent

    hgb_size = size_gb / float(df_magicnumber_normsize)
    felt_size = hgb_size ** magicfactor
    scale = felt_size / hgb_size
    warn_scaled = 100 - (( 100 - warn ) * scale)
    crit_scaled = 100 - (( 100 - crit ) * scale)

    # Make sure, levels do never get too low due to magic factor
    if warn_scaled < lowest_warning_level:
        warn_scaled = lowest_warning_level
    if crit_scaled < lowest_critical_level:
        crit_scaled = lowest_critical_level

    size_mb     = size_gb * 1024
    warn_mb     = int(size_mb * warn_scaled / 100)
    crit_mb     = int(size_mb * crit_scaled / 100)
    levelstext  = "(levels at %.1f/%.1f%%)" % (warn_scaled, crit_scaled)

    return warn_mb, crit_mb, levelstext


#   +----------------------------------------------------------------------+
#   |     ____ _               _      _          _                         |
#   |    / ___| |__   ___  ___| | __ | |__   ___| |_ __   ___ _ __ ___     |
#   |   | |   | '_ \ / _ \/ __| |/ / | '_ \ / _ \ | '_ \ / _ \ '__/ __|    |
#   |   | |___| | | |  __/ (__|   <  | | | |  __/ | |_) |  __/ |  \__ \    |
#   |    \____|_| |_|\___|\___|_|\_\ |_| |_|\___|_| .__/ \___|_|  |___/    |
#   |                                             |_|                      |
#   |                                                                      |
#   | These functions are used in some of the checks.                      |
#   +----------------------------------------------------------------------+


# check range, values might be negative!
# returns True, if value is inside the interval
def within_range(value, minv, maxv):
    if value >= 0: return value >= minv and value <= maxv
    else: return value <= minv and value >= maxv

# compile regex or look it up in already compiled regexes
# (compiling is a CPU consuming process. We cache compiled
# regexes).
def get_regex(pattern):
    reg = compiled_regexes.get(pattern)
    if not reg:
        reg = re.compile(pattern)
        compiled_regexes[pattern] = reg
    return reg

# Names of texts usually output by checks
nagios_state_names = ["OK", "WARN", "CRIT", "UNKNOWN"]

# int() function that return 0 for empty strings
def saveint(i):
    if i == '':
        return 0
    else:
        return int(i)

def savefloat(f):
    try:
        return float(f)
    except:
        return 0.0

# Takes bytes as integer and returns a string which represents the bytes in a
# more human readable form scaled to GB/MB/KB
def get_bytes_human_readable(b, base=1024.0):
    # Handle negative bytes correctly
    prefix = ''
    if b < 0:
        prefix = '-'
        b *= -1

    if b > base * base * base:
        return '%s%.2fGB' % (prefix, b / base / base / base)
    if b > base * base:
        return '%s%.2fMB' % (prefix, b / base / base)
    elif b > base:
        return '%s%.2fKB' % (prefix, b / base)
    else:
        return '%s%.2fB' % (prefix, b)

def get_nic_speed_human_readable(speed):
    try: 
        speedi = int(speed)
        if speedi == 10000000:
            speed = "10MBit/s"
        elif speedi == 100000000:
            speed = "100MBit/s"
        elif speedi == 1000000000:
            speed = "1GBit/s"
        elif speed < 1500000000:
            speed = "%dMBit/s" % (speedi / 1000000)
        else:
            speed = "%dGBit/s" % (speedi / 1000000000)
    except:
        pass
    return speed

