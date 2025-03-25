#!/usr/bin/env python

""" customizable cloud scheduler """

import base64
import json
import sys
import traceback
import smtplib
import logging

from email.mime.text import MIMEText

# User Data Directives:
#SCHED acl=xdmod

#Proposed:
#SCHED feature=cheap

configfile="/etc/eucalyptus/bobsleigh_config.json"

def getInt(s):
    """Convert numbers to int"""
    ret = s
    try:
        ret = int(s)
    except:
        pass

    return ret
        

def parse_nc_file( ncfile ):
    """Create a dictionary of the current NC state as passed in by euca"""
    ncdefs={}
    with open(ncfile) as infile:
        for line in infile:
            line = line.strip().rstrip()
            ncinfo = line.split(",")
            tmp = {}
            for field in ncinfo:
                key, value = field.split("=")
                tmp[key]=getInt(value)
            ncdefs[tmp['ip']]={}
            for key,value in tmp.iteritems():
                ncdefs[tmp['ip']][key]=value

    return ncdefs

def parse_data_file( datafile, req ):
    """Parse any user data if it exists"""
    udataraw = None

    with open(datafile) as infile:
        base64data = infile.read()
        udataraw = base64.b64decode(base64data)

    for line in udataraw.split("\n"):
        if "#SCHED " in line:
            splitline = line.split()
            if len(splitline) == 2:
                confpart = splitline[1]
                params = confpart.split("=")
                if len(params) == 2:
                    key = params[0]
                    value = params[1]
                    req[key]=value

def match_reqs( req, nc ):
    """Check if the requirements can be satisfied by this NC"""
    
    want_acl = req.get("acl", None)

    # ACL
    if want_acl == None:
        if nc['acl'][0] != "ALL":
            return False
        else:
            pass
    else:
        if want_acl in nc['acl']:
            pass
        else:
            return False

    # Platform
    ncplatforms = nc.get("platforms", ["linux", "windows"]) 
    if req['platform'] not in ncplatforms:
        return False;

    # Features
    # TODO

    return True

def has_resources( req, nc ):
    """Does the NC has resources available for this request"""

    resv_cpu = nc.get("reserve", {}).get("cpu", 0)
    resv_mem = nc.get("reserve", {}).get("mem", 0)

    if nc["availmem"] - resv_mem < req["mem"]:
        return False
    if nc["availcores"] - resv_cpu < req["cpu"]:
        return False
    if nc["availdisk"] < req["disk"]:
        return False

    return True

def find_candidates( config, ncinfo, req ):
    """Find all the NCs that can satisfy the requirements"""

    candidates={}
    for key, value in ncinfo.iteritems():
        if match_reqs(req, config['nodecontrollers'][key]):
            if has_resources( req, value ):
                candidates[key]=value

    return candidates

def sched_greedy( config, ncinfo, req ):
    """Pack the instances as tightly as possbible"""

    candidates = find_candidates( config, ncinfo, req )

    if len(candidates) == 0:
        return 0

    # Greedy means find the most loaded NC by core count that can satisfy this request
    nodeid=0
    cores=10000

    for key, value in candidates.iteritems():
        if value["availcores"] < cores:
            nodeid = value["idx"]
            cores = value["availcores"]

    return nodeid

def sched_generous( config, ncinfo, req ):
    """Pack the instances as loosly as possible"""

    candidates = find_candidates( config, ncinfo, req )

    if len(candidates) == 0:
        return 0

    # Generous means find the least loaded NC by core count that can satisfy this request
    nodeid=0
    cores=0

    for key, value in candidates:
        if value["availcores"] > cores:
            nodeid = value["idx"]
            cores = value["availcores"]

    return nodeid

def notify_failure(config, ncinfo, req, extra=None):
    """Email somebody if we can't schedule a node"""
    msg_str = ""
    msg_str += "Bobsleigh configuration:\n\n"
    msg_str += json.dumps(config, indent=4)
    msg_str += "\n\n\n\n"
    msg_str += "NC status from CC:\n\n"
    msg_str += json.dumps(ncinfo, indent=4)
    msg_str += "\n\n\n\n"
    msg_str += "User request:\n\n"
    msg_str += json.dumps(req, indent=4)
    msg_str += "\n\n\n\n"

    if extra != None:
        msg_str += extra

    msg = MIMEText(msg_str)
    msg['Subject'] = 'Instance start Failure'
    msg['From'] = "root@localhost"
    msg['To'] = ", ".join(config['mailto'])
    s = smtplib.SMTP('localhost')
    s.sendmail(msg['From'], config['mailto'], msg.as_string())
    s.quit()       

def main(config):
    """ Format is fixed and defined in cluster/handlers.c"""
    if len(sys.argv) != 9:
        exit(0)

    # Log something to /var/log/eucalyptus ??
    # logging.basicConfig(filename='/tmp/bobsleigh.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    # logging.debug('Running bobsleigh')

    cmd = sys.argv[0]
    ncfile = sys.argv[1]
    instfile = sys.argv[2]
    reqmem = sys.argv[3]
    reqdisk = sys.argv[4]
    reqcpu = sys.argv[5]
    instid = sys.argv[6]
    datafile = sys.argv[7]
    platform = sys.argv[8]

    req={}
    req['cpu']=getInt(reqcpu)
    req['mem']=getInt(reqmem)
    req['disk']=getInt(reqdisk)
    req['platform']=platform

    parse_data_file( datafile, req )
    ncinfo = parse_nc_file( ncfile )

    policy = config.get("policy", "GREEDY")

    retnc=0

    if policy == "GREEDY":
        retnc = sched_greedy( config, ncinfo, req )
    elif policy == "GENEROUS":
        retnc = sched_generous( config, ncinfo, req )
    else:
        retnc = sched_greedy( config, ncinfo, req )

    if retnc == 0 and "mailto" in config:
        notify_failure(config, ncinfo, req)

    exit(retnc)

if __name__ == "__main__":
    try:
        with open(configfile) as infile:
            config = json.load(infile)

        main(config)
    except Exception as e:
        # Need to return 0 on error
        ex_str = traceback.format_exc()
        msg = MIMEText(ex_str)
        if "mailto" in config:
            notify_failure(config, {}, {}, msg.as_string())
        exit(0)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 autoindent smarttab
