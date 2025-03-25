# -*- coding: utf-8 -*-
from Components.Converter.Converter import Converter
from Components.config import config
from enigma import iServiceInformation, iPlayableService, iPlayableServicePtr
from Components.Element import cached
from ServiceReference import resolveAlternate

class ServiceName(Converter, object):
	NAME = 0
	PROVIDER = 1
	REFERENCE = 2
	EDITREFERENCE = 3
	SID = 4

	def __init__(self, type):
		Converter.__init__(self, type)
		if type == "Provider":
			self.type = self.PROVIDER
		elif type == "Reference":
			self.type = self.REFERENCE
		elif type == "EditReference":
			self.type = self.EDITREFERENCE
		elif type == "Sid":
			self.type = self.SID
		else:
			self.type = self.NAME

	@cached
	def getText(self):
		service = self.source.service
		if isinstance(service, iPlayableServicePtr):
			info = service and service.info()
			ref = None
		else: # reference
			info = service and self.source.info
			ref = service
		if not info:
			return ""
		if self.type == self.NAME:
			if config.usage.show_infobar_channel_number.getValue():
				name = ref and info.getName(ref)
				numservice = self.source.serviceref
				num = numservice and numservice.getChannelNum() or None
				print 'service.getChannelNum()',numservice.getChannelNum()
				if name is None:
					name = info.getName()
				return str(num) + '   ' + name.replace('\xc2\x86', '').replace('\xc2\x87', '')
			else:
				name = ref and info.getName(ref)
				if name is None:
					name = info.getName()
				return name.replace('\xc2\x86', '').replace('\xc2\x87', '')
		elif self.type == self.PROVIDER:
			return info.getInfoString(iServiceInformation.sProvider)
		elif self.type == self.REFERENCE or self.type == self.EDITREFERENCE and hasattr(self.source, "editmode") and self.source.editmode:
			if not ref:
				return info.getInfoString(iServiceInformation.sServiceref)
			else:
				nref = resolveAlternate(ref)
				if nref:
					ref = nref
				return ref.toString()
		elif self.type == self.SID:
			if ref is None:
				tmpref = info.getInfoString(iServiceInformation.sServiceref)
			else:
				tmpref = ref.toString()

			if tmpref:
				refsplit = tmpref.split(':')
				if len(refsplit) >= 3: 
					return refsplit[3]
				else:
					return tmpref
			else:
				return 'N/A'

	text = property(getText)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in (iPlayableService.evStart,):
			Converter.changed(self, what)
