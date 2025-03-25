#!/usr/bin/env python
# -*- coding: utf-8 -*-

# satprep_prepare_maintenance.py - a script for (un)scheduling
# downtimes for hosts monitored by Nagios/Icinga/Thruk/Shinken
# and creating/removing VM snapshots using libvirt
#
# 2015 By Christian Stankowic
# <info at stankowic hyphen development dot net>
# https://github.com/stdevel
#

import logging
import sys
from optparse import OptionParser, OptionGroup
import csv
from satprep_shared import schedule_downtime, get_credentials, create_snapshot, is_downtime, has_snapshot, schedule_downtime_hostgroup, is_blacklisted
import time
import os



#set logger
LOGGER = logging.getLogger('satprep_prepare_maintenance')

#some global parameters
downtimeHosts=[]
snapshotHosts=[]
blacklist=["hostname","system_monitoring_name","system_virt_vmname","system_monitoring_notes","1","0",""]
myPrefix=""
defaultMonUser=""
defaultMonPass=""
defaultVirtUser=""
defaultVirtPass=""



def verify():
	#verify snapshots and downtimes
	global downtimeHosts
	global snapshotHosts
	global myPrefix
	global defaultMonUser
	global defaultMonPass
	global defaultVirtUser
	global defaultVirtPass
	
        #check whether the output directory/file is writable
        if os.access(os.getcwd(), os.W_OK):
		LOGGER.debug("Output file/directory writable!")
		if os.path.exists(myPrefix+"_satprep.vlog"):
			myLog = open(myPrefix+"_satprep.vlog", "r+")
		else:
			myLog = open(myPrefix+"_satprep.vlog", "w+")
		myFile = myLog.read().splitlines()
		LOGGER.debug("vlog before customization: ***\n" + str(myFile))
	else:
		#directory not writable
		LOGGER.error("Output directory NOT writable!")
		sys.exit(1)
	
	#check downtimes
	if len(downtimeHosts) == 0 or options.skipMonitoring: LOGGER.info("No downtimes to verify.")
	else:
		#check _all_ the downtimes
		for host in downtimeHosts:
			#try to get differing host/credentials
			if "@" in host and ":" in host:
				thisURI = host[host.find("@")+1:host.rfind(":")]
				thisCred = host[host.rfind(":")+1:]
				thisHost = host[:host.find("@")]
				LOGGER.debug("Found differing host/crendials combination for monitored VM '" + thisHost + "' - Monitoring URL: '" + thisURI + "', credentials: '" + thisCred + "'")
			else:
				thisURI = ""
				thisCred = ""
				thisHost = host
			
			if thisURI != "" and thisCred != "":
				#get username and password
				(thisUsername, thisPassword) = get_credentials(thisURI, thisCred)
				result = is_downtime(thisURI, thisUsername, thisPassword, thisHost, options.userAgent, options.noAuth)
			else:
				#get default login if not in cache
				if defaultMonUser == "": (defaultMonUser, defaultMonPass) = get_credentials("Monitoring", options.monAuthfile)
				result = is_downtime(options.URL, defaultMonUser, defaultMonPass, thisHost, options.userAgent, options.noAuth)
			
			if result:
				#host in downtime
				LOGGER.debug("Host '" + thisHost + "' in downtime. :)")
				#correct or append entry
				if "MONCRIT;"+thisHost in myFile and "MONOK;"+thisHost not in myFile: myFile = [h.replace("MONCRIT;"+thisHost, "MONOK;"+thisHost) for h in myFile]
				elif "MONOK;"+thisHost not in myFile: myFile.append("MONOK;"+thisHost)
			else:
				#host NOT in downtime
				LOGGER.error("Host '" + thisHost + "' NOT in downtime. :(")
				#correct or append entry
				if "MONOK;"+thisHost in myFile and "MONCRIT;"+thisHost not in myFile: myFile = [h.replace("MONOK;"+thisHost, "MONCRIT;"+thisHost) for h in myFile]
				elif "MONCRIT;"+thisHost not in myFile: myFile.append("MONCRIT;"+thisHost)
	
	#check snapshots
	if len(snapshotHosts) == 0 or options.skipSnapshot: LOGGER.info("No snapshots to verify.")
	else:
		#check _all_ the snapshots
		for host in snapshotHosts:
			LOGGER.debug("Checking snapshot for host '" + host + "'...")
			#try to get differing host/credentials
			if "@" in host and ":" in host:
				thisURI = host[host.find("@")+1:host.rfind(":")]
				thisCred = host[host.rfind(":")+1:]
				thisHost = host[:host.find("@")]
				LOGGER.debug("Found differing host/crendials combination for VM '" + thisHost + "' - Virtualization URL: '" + thisURI + "', credentials: '" + thisCred + "'")
			else:
				thisURI = ""
				thisCred = ""
				thisHost = host
			
			if thisURI != "" and thisCred != "":
				#get username and password
				(thisUsername, thisPassword) = get_credentials(thisURI, thisCred)
				result = has_snapshot(thisURI, thisUsername, thisPassword, thisHost, myPrefix+"_satprep")
			else:
				#get default login if not in cache
				if defaultVirtUser == "": (defaultVirtUser, derfaultVirtPass) = get_credentials("Virtualization", options.virtAuthfile)
				result = has_snapshot(options.libvirtURI, defaultVirtUser, defaultVirtPass, thisHost, myPrefix+"_satprep")
			
			if result:
				#snapshot exists
				LOGGER.debug("Snapshot for VM '" + thisHost + "' found. :)")
				#correct or append entry
				if "SNAPCRIT;"+thisHost in myFile and "SNAPOK;"+thisHost not in myFile: myFile = [h.replace("SNAPCRIT;"+thisHost, "SNAPOK;"+thisHost) for h in myFile]
				elif "SNAPOK;"+thisHost not in myFile: myFile.append("SNAPOK;"+thisHost)
			else:
				#snapshot non-existent
				LOGGER.error("No snapshot for VM '" + thisHost + "' found. :(")
				#correct or append entry
				if "SNAPOK;"+thisHost in myFile and "SNAPCRIT;"+thisHost not in myFile: myFile = [h.replace("SNAPOK;"+thisHost, "SNAPCRIT;"+thisHost) for h in myFile]
				elif "SNAPCRIT;"+thisHost not in myFile: myFile.append("SNAPCRIT;"+thisHost)
	#write vlog file
	myLog.seek(0)
	LOGGER.debug("File after customization: ***\n" + str(myFile))
	for line in myFile:
		myLog.write(line + "\n")
	myLog.close()



def setDowntimes():
	#set downtimes
	global defaultMonUser
	global defaultMonPass
	
	#stop if no hosts affected
	if len(downtimeHosts) == 0:
		LOGGER.info("No downtimes to schedule, going home!")
		return False
	
	#schedule downtimes for hostgroups if given
	if len(options.downtimeHostgroups) != 0 and options.tidy == False:
		if options.dryrun:
			#simulation
			for thisHostgroup in options.downtimeHostgroups:
				LOGGER.info("I'd like to schedule downtime for hostgroup '" + thisHostgroup + "'...")
		else:
			#schedule _all_ the downtimes
			for thisHostgroup in options.downtimeHostgroups:
				LOGGER.info("Scheduling downtime for hostgroup '" + thisHostgroup + "'...")
				#get default login if not specified
				if defaultMonUser == "": (defaultMonUser, defaultMonPass) = get_credentials("Monitoring", options.monAuthfile)
				result = schedule_downtime_hostgroup(options.URL, defaultMonUser, defaultMonPass, thisHostgroup, options.hours, options.comment, options.userAgent, options.noAuth)
		return True
	
	#set downtime for affected hosts
	for host in downtimeHosts:
		#try to get differing host/credentials
		if "@" in host and ":" in host:
			thisURI = host[host.find("@")+1:host.rfind(":")]
			thisCred = host[host.rfind(":")+1:]
			thisHost = host[:host.find("@")]
			LOGGER.debug("Found differing host/crendials combination for monitored VM '" + thisHost + "' - Monitoring URL: '" + thisURI + "', credentials: '" + thisCred + "'")
		else:
			thisURI = ""
			thisCred = ""
			thisHost = host
		
		output=""
		if options.dryrun:
			#simulation
			if options.tidy and options.skipMonitoring == False:
				output = "I'd like to unschedule downtime for host '" + thisHost
			elif options.tidy == False and options.skipMonitoring == False:
				output =  "I'd like to schedule downtime for host '" + thisHost + "' for " + options.hours + " hours using the comment '" + options.comment
			#add differing host information
			if thisURI != "": output = output + "' (using " + thisURI + " - " + thisCred + ")..."
			else: output = output + "'..."
			LOGGER.info(output)
		else:
			#_(un)schedule_ all the downtimes
			if options.tidy and options.skipMonitoring == False:
				output = "Unscheduling downtime for host '" + thisHost
			elif options.tidy == False and options.skipMonitoring == False:
				output = "Scheduling downtime for host '" + thisHost + "' (hours=" + options.hours + ", comment=" + options.comment
			#add differing host information
			if thisURI != "": output = output + "' (using " + thisURI + " - " + thisCred + ")..."
			else: output = output + "'..."
			LOGGER.info(output)
			
			#(un)schedule downtime
			if thisURI != "" and thisCred != "":
				#get username and password
				(thisUsername, thisPassword) = get_credentials(thisURI, thisCred)
				result = schedule_downtime(thisURI, thisUsername, thisPassword, thisHost, options.hours, options.comment, options.userAgent, options.noAuth, options.tidy)
			else:
				#get default login if not in cache
				if defaultMonUser == "": (defaultMonUser, defaultMonPass) = get_credentials("Monitoring", options.monAuthfile)
				result = schedule_downtime(options.URL, defaultMonUser, defaultMonPass, thisHost, options.hours, options.comment, options.userAgent, options.noAuth, options.tidy)



def createSnapshots():
	#create snapshots
	global defaultVirtUser
	global defaultVirtPass
	
	#stop if no hosts affected
	if len(snapshotHosts) == 0:
		LOGGER.info("No snapshots to create, going home!")
		return False
	
	#set downtime for affected hosts
	for host in snapshotHosts:
		#try to get differing host/credentials
		if "@" in host and ":" in host:
			thisURI = host[host.find("@")+1:host.rfind(":")]
			thisCred = host[host.rfind(":")+1:]
			thisHost = host[:host.find("@")]
			LOGGER.debug("Found differing host/crendials combination for VM '" + thisHost + "' - libvirtURI: '" + thisURI + "', credentials: '" + thisCred + "'")
		else:
			thisURI = ""
			thisCred = ""
			thisHost = host
		
		output = ""
		if options.dryrun:
			#simulation
			if options.tidy and options.skipSnapshot == False:
				output = "I'd like to remove a snapshot ('" + myPrefix+ "_satprep') for VM '" + thisHost
			elif options.tidy == False and options.skipSnapshot == False:
				output = "I'd like to create a snapshot ('" + myPrefix + "_satprep') for VM '" + thisHost
			#add differing host information
			if thisURI != "": output = output + "' (using " + thisURI + " - " + thisCred + ")..."
			else: output = output + "'..."
			LOGGER.info(output)
		else:
			#_create/remove_ all the snapshots
			if options.tidy and options.skipSnapshot == False:
				output = "Removing a snapshot ('" + myPrefix + "_satprep') for VM '" + thisHost 
			elif options.tidy == False and options.skipSnapshot == False:
				output = "Creating a snapshot ('" + myPrefix + "_satprep') for VM '" + thisHost
			#add differing host information 
			if thisURI != "": output = output + "' (using " + thisURI + " - " + thisCred + ")..."
			else: output = output + "'..."
			LOGGER.info(output)
			
			#create/remove snapshot
			if thisURI != "" and thisCred != "":
				#get username and password
				(thisUsername, thisPassword) = get_credentials(thisURI, thisCred)
				result = create_snapshot(thisURI, thisUsername, thisPassword, thisHost, myPrefix+"_satprep", options.comment, options.tidy)
			else:
				#get default login if not in cache
				if defaultVirtUser == "": (defaultVirtUser, defaultVirtPass) = get_credentials("Virtualization", options.virtAuthfile)
				result = create_snapshot(options.libvirtURI, defaultVirtUser, defaultVirtPass, thisHost, myPrefix+"_satprep", options.comment, options.tidy)



def readFile(file):
	#get affected hosts from CSV report
	global downtimeHosts
	global snapshotHosts
	global myPrefix
	
	#set timestamp as prefix
	myPrefix = time.strftime("%Y%m%d", time.gmtime(os.path.getctime(args[1])))
	
	#read report header and get column index for hostname ,reboot and monitoring flag (if any)
	rFile = open(args[1], 'r')
	header = rFile.readline()
	headers = header.replace("\n","").replace("\r","").split(";")
	repcols = { "hostname" : 666, "errata_reboot" : 666, "system_prod": 666, "system_monitoring" : 666, "system_monitoring_name" : 666, "system_virt" : 666, "system_virt_snapshot" : 666, "system_virt_vmname" : 666 }
	for name,value in repcols.items():
		try:
			#try to find index
			repcols[name] = headers.index(name)
		except ValueError:
			LOGGER.debug("Unable to find column index for " + name + " so I'm disabling it.")
	#print report column indexes
	LOGGER.debug("Report column indexes: {0}".format(str(repcols)))
	
	#read report and add affected hosts
	with open(file, 'rb') as csvfile:
		filereader = csv.reader(csvfile, delimiter=';', quotechar='|')
		for row in filereader:
			if options.noIntelligence == True:
				#simply add the damned host
				
				#monitoring, add custom name if defined
				if repcols["system_monitoring_name"] < 666 and row[repcols["system_monitoring_name"]] != "":
					this_name=row[repcols["system_monitoring_name"]]
				else: this_name=row[repcols["hostname"]]
				#only add if prod/nonprod modes aren't avoiding it
				if (row[repcols["system_prod"]] == "1" and options.nonprodOnly == False) \
				or (row[repcols["system_prod"]] != "1" and options.prodOnly == False) \
				or (options.prodOnly == False and options.nonprodOnly == False):
					if is_blacklisted(row[repcols["hostname"]], options.exclude) == False: downtimeHosts.append(this_name)
					LOGGER.debug("Downtime will be scheduled for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
				
				#virtualization, add custom name if defined
				if repcols["system_virt_vmname"] < 666 and row[repcols["system_virt_vmname"]] != "":
					this_name=row[repcols["system_virt_vmname"]]
				else: this_name=row[repcols["hostname"]]
				#only add if prod/nonprod modes aren't avoiding it
				if (row[repcols["system_prod"]] == "1" and options.nonprodOnly == False) \
				or (row[repcols["system_prod"]] != "1" and options.prodOnly == False) \
				or (options.prodOnly == False and options.nonprodOnly == False):
					if is_blacklisted(row[repcols["hostname"]], options.exclude) == False: snapshotHosts.append(this_name)
					LOGGER.debug("Snapshot will be created for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
				else:
					LOGGER.debug("Script parameters are avoiding creating snapshot for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
			else:
				#add host to downtimeHosts if reboot required and monitoring flag set, add custom names if defined
				if repcols["errata_reboot"] < 666 and row[repcols["errata_reboot"]] == "1":
					#handle custom name
					if row[repcols["system_monitoring"]] == "1" and row[repcols["system_monitoring_name"]] != "":
						this_name = row[repcols["system_monitoring_name"]]
					elif row[repcols["system_monitoring"]] == "1":
						this_name = row[repcols["hostname"]]
					#only add if prod/nonprod modes aren't avoiding it
					if (row[repcols["system_prod"]] == "1" and options.nonprodOnly == False) \
					or (row[repcols["system_prod"]] != "1" and options.prodOnly == False) \
					or (options.prodOnly == False and options.nonprodOnly == False):
						if is_blacklisted(row[repcols["hostname"]], options.exclude) == False and row[repcols["system_monitoring"]] == "1": downtimeHosts.append(this_name)
						LOGGER.debug("Downtime will be scheduled for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
					else: LOGGER.debug("Script parameters are avoiding scheduling downtime for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
				
				#add host to snapshotHosts if virtual and snapshot flag set
				if repcols["system_virt"] < 666 and row[repcols["system_virt"]] == "1" and repcols["system_virt_snapshot"] < 666 and row[repcols["system_virt_snapshot"]] == "1":
					#handle custom name
					if row[repcols["system_virt_vmname"]] != "":
						this_name = row[repcols["system_virt_vmname"]]
					else: this_name = row[repcols["hostname"]]
					#only add if prod/nonprod modes aren't avoiding it
					if (row[repcols["system_prod"]] == "1" and options.nonprodOnly == False) \
					or (row[repcols["system_prod"]] != "1" and options.prodOnly == False) \
					or (options.prodOnly == False and options.nonprodOnly == False):
						if is_blacklisted(row[repcols["hostname"]], options.exclude) == False: snapshotHosts.append(this_name)
						LOGGER.debug("Snapshot will be created for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
					else:
						LOGGER.debug("Script parameters are avoiding creating snapshot for '" + this_name + "' (P:" + row[repcols["system_prod"]] + ")")
					
	#remove duplicates and blacklisted lines
	downtimeHosts = sorted(set(downtimeHosts))
	snapshotHosts = sorted(set(snapshotHosts))
	for entry in blacklist:
		if entry in downtimeHosts: downtimeHosts.remove(entry)
		if entry in snapshotHosts: snapshotHosts.remove(entry)
	#print affected hosts
	LOGGER.debug("Affected hosts for downtimes: {0}".format(downtimeHosts))
	LOGGER.debug("Affected hosts for snapshots: {0}".format(snapshotHosts))



def main(options):
	#read file and schedule downtimes
	LOGGER.debug("Options: {0}".format(options))
	LOGGER.debug("Args: {0}".format(args))
	
	#read file
	readFile(args[1])
	
	if options.verifyOnly == True:
		#verify only
		verify()
	else:
		#create snapshots and schedule downtimes
		if options.skipSnapshot == False: createSnapshots()
		if options.skipMonitoring == False: setDowntimes()
		#also verify
		if options.dryrun == False:
			LOGGER.info("Verifying preparation...")
			verify()



def parse_options(args=None):
	if args is None:
		args = sys.argv
	
	#define usage, description, version and load parser
	usage = "usage: %prog [options] snapshot.csv"
	desc = '''%prog is used to prepare maintenance for systems managed with Spacewalk, Red Hat Satellite or SUSE Manager. This includes (un)scheduling downtimes in Nagios, Icinga and Shinken and creating/removing snapshots of virtual machines. As this script uses libvirt multiple hypervisors are supported (see GitHub and libvirt documenation). Login credentials are assigned using the following shell variables:
	SATELLITE_LOGIN	username for Satellite
	SATELLITE_PASSWORD	password for Satellite
	LIBVIRT_LOGIN	username for virtualization host
	LIBVIRT_PASSWORD	password for virtualization host
	
	Alternatively you can also use auth files including a valid username (first line) and password (second line) for the monitoring and virtualization host. Make sure to use file permissions 0600 for these files.
	
	Check-out the GitHub documentation (https://github.com/stdevel/satprep) for further information.
	'''
	parser = OptionParser(usage=usage, description=desc, version="%prog version 0.3.6")
	#define option groups
	genOpts = OptionGroup(parser, "Generic Options")
	monOpts = OptionGroup(parser, "Monitoring Options")
	vmOpts = OptionGroup(parser, "VM Options")
	repOpts = OptionGroup(parser, "Report Options")
	parser.add_option_group(genOpts)
	parser.add_option_group(monOpts)
	parser.add_option_group(vmOpts)
	parser.add_option_group(repOpts)
	
	#GENERIC OPTIONS
	#-c / --comment
	genOpts.add_option("-c", "--comment", action="store", dest="comment", default="System maintenance scheduled by satprep", metavar="COMMENT", help="defines a comment for downtimes and snapshots (default: 'System maintenance scheduled by satprep')")
	#-d / --debug
	genOpts.add_option("-d", "--debug", dest="debug", default=False, action="store_true", help="enable debugging outputs")
	#-f / --no-intelligence
	genOpts.add_option("-f", "--no-intelligence", dest="noIntelligence", action="store_true", default=False, help="disables checking for patches requiring reboot, simply schedules downtimes and creates snapshots for all hosts mentioned in the CSV report (default: no)")
	#-n / --dry-run
	genOpts.add_option("-n", "--dry-run", action="store_true", dest="dryrun", default=False, help="only simulates tasks that would be executed (default: no)")
	#-T / --tidy
	genOpts.add_option("-T", "--tidy", dest="tidy", action="store_true", default=False, help="unschedules downtimes and removes previously created snapshots (default: no)")
	#-V / --verify-only
	genOpts.add_option("-V", "--verify-only", dest="verifyOnly", action="store_true", default="False", help="verifies that all required downtimes and snapshots have been created and quits (default: no)")
	
	#REPORT OPTIONS
	#-p / --prod-only
	repOpts.add_option("-p", "--prod-only", dest="prodOnly", action="store_true", default=False, help="only prepares maintenance for productive hosts (default: no)")
	#-D / --nonprod-only
	repOpts.add_option("-D", "--nonprod-only", dest="nonprodOnly", action="store_true", default=False, help="only prepares maintenance for non-productive hosts (default: no)")
	#-e / --exclude
	repOpts.add_option("-e", "--exclude", dest="exclude", action="append", type="string", default=[], help="defines hosts that should be exluded from preparing maintenance")
	
	#MONITORING OPTIONS
	#-k / --skip-monitoring
	monOpts.add_option("-k", "--skip-monitoring", dest="skipMonitoring", action="store_true", default=False, help="skips creating/removing downtimes (default: no)")
	#-a / --mon-authfile
	monOpts.add_option("-a", "--mon-authfile", dest="monAuthfile", metavar="FILE", default="", help="defines an auth file to use for monitoring")
	#-u / --monitoring-url
	monOpts.add_option("-u", "--monitoring-url", dest="URL", metavar="URL", default="http://localhost/icinga", help="defines the default Nagios/Icinga/Thruk/Shinken URL to use, might be overwritten by custom system keys (default: http://localhost/icinga)")
	#-t / --hours
	monOpts.add_option("-t", "--hours", action="store", dest="hours", default="4", metavar="HOURS", help="sets the time period in hours hosts should be scheduled for downtime (default: 4)")
	#-x / --no-auth
	monOpts.add_option("-x", "--no-auth", action="store_true", default=False, dest="noAuth", help="disables HTTP basic auth (default: no)")
	#-A / --user-agent
	monOpts.add_option("-A", "--user-agent", action="store", default="", metavar="AGENT", dest="userAgent", help="sets a custom HTTP user agent")
	#-g / --downtime-hostgroup
	monOpts.add_option("-g", "--downtime-hostgroup", action="append", type="string", default=[], metavar="HOSTGROUP", dest="downtimeHostgroups", help="defines hostgroups which should be scheduled for downtime. NOTE: This disables scheduling downtime for particular hosts.")
	
	#VM OPTIONS
	#-K / --skip-snapshot
	vmOpts.add_option("-K", "--skip-snapshot", dest="skipSnapshot", action="store_true", default=False, help="skips creating/removing snapshots (default: no)")
	#-H / --libvirt-uri
	vmOpts.add_option("-H", "--libvirt-uri", dest="libvirtURI", action="store", default="", metavar="URI", help="defines the default URI used by libvirt, might be overwritten by custom system keys")
	#-C / --virt-authfile
	vmOpts.add_option("-C", "--virt-authfile", dest="virtAuthfile", action="store", metavar="FILE", default="", help="defines an auth file to use for virtualization")
	
	(options, args) = parser.parse_args(args)
	
	#check whether snapshot reported
	if len(args) != 2:
		print "ERROR: you need to specify exactly one snapshot report!"
		exit(1)
	
	#tell user that he's a funny guy
	if (
		(options.skipSnapshot == True and options.skipMonitoring == True)
		or
		(options.prodOnly == True and options.nonprodOnly == True)
		or
		(options.dryrun == True and options.verifyOnly == True)
	):
		print "Haha, you're funny."
		exit(1)
	
	#expand excluded hosts
	if len(options.exclude) == 1: options.exclude = str(options.exclude).strip("[]'").split(",")	
	
	return (options, args)



if __name__ == "__main__":
	(options, args) = parse_options()
	#set logger level
	if options.debug:
		logging.basicConfig(level=logging.DEBUG)
		LOGGER.setLevel(logging.DEBUG)
	else:
		logging.basicConfig()
		LOGGER.setLevel(logging.INFO)
	main(options)
