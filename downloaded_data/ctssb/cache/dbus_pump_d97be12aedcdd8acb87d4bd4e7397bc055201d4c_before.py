#!/usr/bin/python -u
# -*- coding: utf-8 -*-

# Function
# dbus_pump monitors the dbus for tank sensors
# The monitored tank sensor can be configured through the gui.
# It then monitors SOC, AC loads, battery current and battery voltage,to auto start/stop the pump based
# on the configuration settings. pump can be started manually or periodically setting a tes trun period.
# Time zones function allows to use different values for the conditions along the day depending on time

from dbus.mainloop.glib import DBusGMainLoop
import gobject
import dbus
import dbus.service
import datetime
import calendar
import os
import argparse
import time
import sys
import json
import os

# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService
from vedbus import VeDbusItemImport
from ve_utils import exit_on_error
from dbusmonitor import DbusMonitor
from settingsdevice import SettingsDevice
from logger import setup_logging

softwareversion = '0.4'


class DbusPump:

	def __init__(self, retries=300):
		self._bus = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
		# One second per retry
		self.RETRIES_ON_ERROR = retries
		self._current_retries = 0

		self.TANKSERVICE_DEFAULT = 'default'
		self.TANKSERVICE_NOTANK = 'notanksensor'
		self._dbusservice = None
		self._tankservice = self.TANKSERVICE_NOTANK
		self._valid_tank_level = True
		self._relay_state_import = None

		# DbusMonitor expects these values to be there, even though we don need them. So just
		# add some dummy data. This can go away when DbusMonitor is more generic.
		dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}

		# TODO: possible improvement: don't use the DbusMonitor it all, since we are only monitoring
		# a set of static values which will always be available. DbusMonitor watches for services
		# that come and go, and takes care of automatic signal subscribtions etc. etc: all not necessary
		# in this use case where we have fixed services names (com.victronenergy.settings, and c
		# com.victronenergy.system).
		self._dbusmonitor = DbusMonitor({
			'com.victronenergy.settings': {   # This is not our setting so do it here. not in supportedSettings
				'/Settings/Relay/Function': dummy,
				'/Settings/Relay/Polarity': dummy
			},
			'com.victronenergy.tank': {   # This is not our setting so do it here. not in supportedSettings
				'/Level': dummy,
				'/FluidType': dummy,
				'/ProductName': dummy,
				'/Mgmt/Connection': dummy
			}
		}, self._dbus_value_changed, self._device_added, self._device_removed)

		# Connect to localsettings
		self._settings = SettingsDevice(
			bus=self._bus,
			supportedSettings={
				'tankservice': ['/Settings/Pump0/TankService', self.TANKSERVICE_NOTANK, 0, 1],
				'autostart': ['/Settings/Pump0/AutoStartEnabled', 1, 0, 1],
				'startvalue': ['/Settings/Pump0/StartValue', 50, 0, 100],
				'stopvalue': ['/Settings/Pump0/StopValue', 80, 0, 100],
				'mode': ['/Settings/Pump0/Mode', 0, 0, 100]  # Auto = 0, On = 1, Off = 2
			},
			eventCallback=self._handle_changed_setting)

		# Whenever services come or go, we need to check if it was a service we use. Note that this
		# is a bit double: DbusMonitor does the same thing. But since we don't use DbusMonitor to
		# monitor for com.victronenergy.battery, .vebus, .charger or any other possible source of
		# battery data, it is necessary to monitor for changes in the available dbus services.
		self._bus.add_signal_receiver(self._dbus_name_owner_changed, signal_name='NameOwnerChanged')

		self._evaluate_if_we_are_needed()
		gobject.timeout_add(1000, self._handletimertick)

		self._changed = True

	def _evaluate_if_we_are_needed(self):
		if self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Function') == 3:
			if self._dbusservice is None:
				logger.info('Action! Going on dbus and taking control of the relay.')

				relay_polarity_import = VeDbusItemImport(
					bus=self._bus, serviceName='com.victronenergy.settings',
					path='/Settings/Relay/Polarity',
					eventCallback=None, createsignal=True)

			if not self._relay_state_import:
				logger.info('Getting relay from systemcalc.')
				try:
					self._relay_state_import = VeDbusItemImport(
						bus=self._bus, serviceName='com.victronenergy.system',
						path='/Relay/0/State',
						eventCallback=None, createsignal=True)
				except dbus.exceptions.DBusException:
					logger.info('Systemcalc relay not available.')
					self._relay_state_import = None


				# As is not possible to keep the relay state during the CCGX power cycles,
				# set the relay polarity to normally open.
				if relay_polarity_import.get_value() == 1:
					relay_polarity_import.set_value(0)
					logger.info('Setting relay polarity to normally open.')

				# put ourselves on the dbus
				self._dbusservice = VeDbusService('com.victronenergy.pump.startstop0')
				self._dbusservice.add_mandatory_paths(
					processname=__file__,
					processversion=softwareversion,
					connection='pump',
					deviceinstance=0,
					productid=None,
					productname=None,
					firmwareversion=None,
					hardwareversion=None,
					connected=1)
				# State: None = invalid, 0 = stopped, 1 = running
				self._dbusservice.add_path('/State', value=0)
				self._dbusservice.add_path('/AvailableTankServices', value=None)
				self._dbusservice.add_path('/ActiveTankService', value=None)
				self._update_relay()
				self._handleservicechange()

		else:
			if self._dbusservice is not None:
				self._stop_pump()
				self._dbusservice.__del__()
				self._dbusservice = None
				self._relay_state_import = None

				logger.info('Relay function is no longer set to pump startstop: made sure pump is off and going off dbus')

	def _device_added(self, dbusservicename, instance):
		self._handleservicechange()
		self._evaluate_if_we_are_needed()

	def _device_removed(self, dbusservicename, instance):
		self._handleservicechange()
		# Relay handling depends on systemcalc, if the service disappears restart
		# the relay state import
		if dbusservicename == "com.victronenergy.system":
			self._relay_state_import = None
		self._evaluate_if_we_are_needed()

	def _dbus_value_changed(self, dbusServiceName, dbusPath, options, changes, deviceInstance):

		if dbusPath == '/Settings/Relay/Function':
			self._evaluate_if_we_are_needed()
		self._changed = True
		# Update relay state when polarity changes
		if dbusPath == '/Settings/Relay/Polarity':
			self._update_relay()

	def _handle_changed_setting(self, setting, oldvalue, newvalue):
		self._changed = True
		self._evaluate_if_we_are_needed()
		if setting == "tankservice":
			self._handleservicechange()

		if setting == 'autostart':
				logger.info('Autostart function %s.' % ('enabled' if newvalue == 1 else 'disabled'))

	def _dbus_name_owner_changed(self, name, oldowner, newowner):
		return True

	def _handletimertick(self):
		# try catch, to make sure that we kill ourselves on an error. Without this try-catch, there would
		# be an error written to stdout, and then the timer would not be restarted, resulting in a dead-
		# lock waiting for manual intervention -> not good!
		try:
			if self._dbusservice is not None:
				self._evaluate_startstop_conditions()
			self._changed = False
		except:
			self._stop_pump()
			import traceback
			traceback.print_exc()
			sys.exit(1)
		return True

	def _evaluate_startstop_conditions(self):

		if self._settings['tankservice'] == self.TANKSERVICE_NOTANK:
			self._stop_pump()
			return

		value = self._dbusmonitor.get_value(self._tankservice, "/Level")
		startvalue = self._settings['startvalue']
		stopvalue = self._settings['stopvalue']
		started = self._dbusservice['/State'] == 1
		mode = self._settings['mode']

		# On mode
		if mode == 1:
			if not started:
				self._start_pump()
			self._current_retries = 0
			return

		# Off mode
		if mode == 2:
			if started:
				self._stop_pump()
			self._current_retries = 0
			return

		# Auto mode, in case of an invalid reading start the retrying mechanism
		if started and value is None and mode == 0:

			# Keep the pump running during RETRIES_ON_ERROR(default 300) retries
			if started and self._current_retries < self.RETRIES_ON_ERROR:
				self._current_retries += 1
				logger.info("Unable to get tank level, retrying (%i)" % self._current_retries)
				return
			# Stop the pump after RETRIES_ON_ERROR(default 300) retries
			logger.info("Unable to get tank level after %i retries, stopping pump." % self._current_retries)
			self._stop_pump()
			return

		if self._current_retries > 0 and value is not None:
			logger.info("Tank level successfuly obtained after %i retries." % self._current_retries)
			self._current_retries = 0

		# Tank level not valid, check if is the first invalid reading
		# and print a log message
		if value is None:
			if self._valid_tank_level:
				self._valid_tank_level = False
				logger.info("Unable to get tank level, skipping evaluation.")
			return
		# Valid reading after a previous invalid one
		elif value is not None and not self._valid_tank_level:
			self._valid_tank_level = True
			logger.info("Tank level successfuly obtained, resuming evaluation.")

		start_is_greater = startvalue > stopvalue
		start = started or (value >= startvalue if start_is_greater else value <= startvalue)
		stop = value <= stopvalue if start_is_greater else value >= stopvalue

		if start and not stop:
			self._start_pump()
		else:
			self._stop_pump()

	def _determinetankservice(self):
		s = self._settings['tankservice'].split('/')
		if len(s) != 2:
			logger.error("The tank setting (%s) is invalid!" % self._settings['tankservice'])
		serviceclass = s[0]
		instance = int(s[1]) if len(s) == 2 else None
		services = self._dbusmonitor.get_service_list(classfilter=serviceclass)

		if instance not in services.values():
			# Once chosen tank does not exist. Don't auto change the setting (it might come
			# back). And also don't autoselect another.
			newtankservice = None
		else:
			# According to https://www.python.org/dev/peps/pep-3106/, dict.keys() and dict.values()
			# always have the same order.
			newtankservice = services.keys()[services.values().index(instance)]

		if newtankservice != self._tankservice:
			services = self._dbusmonitor.get_service_list()
			instance = services.get(newtankservice, None)
			if instance is None:
				tank_service = None
			else:
				tank_service = self._get_instance_service_name(newtankservice, instance)
			self._dbusservice['/ActiveTankService'] = newtankservice
			logger.info("Tank service, setting == %s, changed from %s to %s (%s)" %
															(self._settings['tankservice'], self._tankservice, newtankservice, instance))
			self._tankservice = newtankservice

	def _handleservicechange(self):

		services = self._get_connected_service_list('com.victronenergy.tank')
		ul = {self.TANKSERVICE_NOTANK: 'No tank sensor'}
		for servicename, instance in services.items():
			key = self._get_instance_service_name(servicename, instance)
			ul[key] = self._get_readable_service_name(servicename)
		self._dbusservice['/AvailableTankServices'] = dbus.Dictionary(ul, signature='sv')
		self._determinetankservice()

	def _get_readable_service_name(self, servicename):
		fluidTypes = ['Fuel', 'Fresh water', 'Waste water', 'Live well',
															'Oil', 'Black water']

		index = self._dbusmonitor.get_value(servicename, '/FluidType')
		service = self._dbusmonitor.get_value(servicename, '/Mgmt/Connection')
		return ('' if index >= len(fluidTypes) else fluidTypes[index] + ' on ') + service

	def _get_instance_service_name(self, service, instance):
		return '%s/%s' % ('.'.join(service.split('.')[0:3]), instance)

	def _get_connected_service_list(self, classfilter=None):
		services = self._dbusmonitor.get_service_list(classfilter=classfilter)
		return services

	def _start_pump(self):
		if not self._relay_state_import:
			logger.info("Relay import not available, can't start pump by %s condition" % condition)
			return

		systemcalc_relay_state = 0
		state = self._dbusservice['/State']

		try:
			systemcalc_relay_state = self._relay_state_import.get_value()
		except dbus.exceptions.DBusException:
			logger.info('Error getting relay state')

		# This function will start the pump in the case the pump not
		# already running.
		if state == 0 or systemcalc_relay_state != state:
			self._dbusservice['/State'] = 1
			self._update_relay()
			self._starttime = time.time()
			logger.info('Starting pump')

	def _stop_pump(self):
		if not self._relay_state_import:
			logger.info("Relay import not available, can't stop the pump")
			return

		systemcalc_relay_state = 1
		state = self._dbusservice['/State']

		try:
			systemcalc_relay_state = self._relay_state_import.get_value()
		except dbus.exceptions.DBusException:
			logger.info('Error getting relay state')

		if state == 1 or systemcalc_relay_state != state:
			self._dbusservice['/State'] = 0
			logger.info('Stopping pump')
			self._update_relay()

	def _update_relay(self):
		if not self._relay_state_import:
			logger.info("Relay import not available")
			return

		# Relay polarity 0 = NO, 1 = NC
		polarity = bool(self._dbusmonitor.get_value('com.victronenergy.settings', '/Settings/Relay/Polarity'))
		w = int(not polarity) if bool(self._dbusservice['/State']) else int(polarity)

		try:
			self._relay_state_import.set_value(dbus.Int32(w, variant_level=1))
		except dbus.exceptions.DBusException:
			logger.info('Error setting relay state')


if __name__ == '__main__':
	# Argument parsing
	parser = argparse.ArgumentParser(
		description='Start and stop a pump based on selected tank sensor level'
	)

	parser.add_argument('-d', '--debug', help='set logging level to debug',
						action='store_true')
	parser.add_argument('-r', '--retries', help='Retries on error', default=300, type=int)

	args = parser.parse_args()

	print '-------- dbus_pump, v' + softwareversion + ' is starting up --------'
	logger = setup_logging(args.debug)

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	pump = DbusPump(args.retries)
	# Start and run the mainloop
	mainloop = gobject.MainLoop()
	mainloop.run()
