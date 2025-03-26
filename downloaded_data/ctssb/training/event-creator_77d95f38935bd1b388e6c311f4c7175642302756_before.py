# -*- coding: utf-8 -*-

import logging

import ui
from PySide import QtCore

from .WildApricotAPI import WaApiClient
from plugins import Plugin

from config import settings
import config

class WildApricotPlugin(Plugin):
	def __init__(self):
		super().__init__('WildApricot')
		
		self.options = [
			{
				'name': 'API Key',
				'type': 'text',
			},{
				'name': 'Level IDs for members',
				'type': 'text',
			},{
				'name': 'Registration URL format',
				'type': 'text',
			},{
				'name': 'Use this as registration URL',
				'type': 'yesno',
			},{
				'name': 'Enable group-based authorizations',
				'type': 'yesno',
			}
		]

		ui.addTarget(self.name, self, self.createEvent)
		ui.addPopulationType('Members')
	
	def createEvent(self, event):
		# if settings.value('timezone') is not None and settings.value('timezone') != '':
		# 	timezoneOffset = settings.value('timezone').split(' UTC')[1]
		# else:
		# 	timezoneOffset = ''

		tags = ["instructor_name:" + event['instructorName'], "instructor_email:"+event['instructorEmail']]
		
		eventData = {
			"Name": event['title'],
			"StartDate": event['startTime'].toString(QtCore.Qt.ISODate),
			"EndDate": event['stopTime'].toString(QtCore.Qt.ISODate),
			"Location": event['location'],
			"RegistrationsLimit": event['registrationLimit'],
			"RegistrationEnabled": True,
			"StartTimeSpecified": True,
			"EndTimeSpecified": True,
			"Details": {
				"DescriptionHtml": event['description'],
				"AccessControl": { "AccessLevel": "Public" },
				"GuestRegistrationSettings": { "CreateContactMode": "CreateContactForAllGuests" },
				"PaymentMethod": "OnlineOnly",
				"SendEmailCopy": False,
				"WaitListBehaviour": "Disabled",
			},
			"Tags":tags
		}
		
		#@TODO: open ticket with WildApricot so that we can have an API endpoint for enabling email reminders
		self.checkForInterruption()

		logging.debug('Connecting to API')
		api = WaApiClient()
		api.authenticate_with_apikey(self.getSetting('API Key'))

		self.checkForInterruption()
		logging.debug('Creating event')
		eventID = api.execute_request('Events', eventData)

		for rsvpType in event['prices']:
			registrationTypeData = {
				"EventId": eventID,
				"Name": rsvpType['name'],
				"BasePrice": rsvpType['price'],
				"Description": rsvpType['description'],
				"IsEnabled": True,
				"GuestRegistrationPolicy": "Disabled",
				"MultipleRegistrationAllowed": False,
				"WaitlistBehaviour": "Disabled",
				"UnavailabilityPolicy": "Show"
			}
			
			for populationType in rsvpType['availability']:
				if populationType == 'Members':
					registrationTypeData['Availability'] = 'MembersOnly'
					registrationTypeData['AvailableForMembershipLevels'] = []
					
					ids = self.getSetting('Level IDs for members').split(',')
					for id in ids:
						registrationTypeData['AvailableForMembershipLevels'].append({'Id': id})
				else:
					registrationTypeData['Availability'] = 'Everyone'
			
			self.checkForInterruption()

			logging.debug('Adding registration type: ' + rsvpType['name'])
			api.execute_request('EventRegistrationTypes', registrationTypeData)
			
		if config.checkBool(self.getSetting('Enable group-based authorizations')):
			auths = event['tags']['Required auth\'s']
			auth_map = {'Woodshop':416232,
				'Metalshop':416231,
				'Forge':420386,
				'LaserCutter':416230,
				'Mig welding':420387, 
				'Tig welding':420388, 
				'Stick welding':420389, 
				'Manual mill':420390,			
				'Plasma':420391, 
				'Metal lathes':420392, 
				'CNC Plasma':420393, 
				'Intro Tormach':420394, 
				'Full Tormach':420395}
			auth_ids=[]
			if len(auths) > 0:
				for auth in auths:
					auth_ids.append(auth_map[auth])

			self.checkForInterruption()

			logging.debug('Adding auth group requirements')
			api.SetEventAccessControl(eventID, restricted=True, any_level=True, any_group=False, group_ids=auth_ids, level_ids=[])
			
		if self.getSetting('Registration URL format', '') == '':
			waEvent = api.execute_request('Events/%s' % eventID)
			registerURL = waEvent['Details']['Url']
		else:
			registerURL = self.getSetting('Registration URL format', '%s') % eventID

		if config.checkBool(self.getSetting('Use this as registration URL')):
			event['registrationURL'] = registerURL
		
		return registerURL

def load():
	return WildApricotPlugin()
