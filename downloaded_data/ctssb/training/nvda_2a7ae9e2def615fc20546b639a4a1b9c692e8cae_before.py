#synthDrivers/espeak.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2006-2008 NVDA Contributors <http://www.nvda-project.org/>
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

import _espeak
import Queue
import threading
import languageHandler
import synthDriverHandler

class SynthDriver(synthDriverHandler.SynthDriver):
	name = "espeak"
	description = "eSpeak"

	hasVoice=True
	hasPitch=True
	hasRate=True
	hasVolume=True
	hasVariant=True
	hasInflection=True

	@classmethod
	def check(cls):
		return True

	def _paramToPercent(self, current, min, max):
		return int(round(float(current - min) / (max - min) * 100))

	def _percentToParam(self, percent, min, max):
		return int(round(float(percent) / 100 * (max - min) + min))

	def initialize(self):
		_espeak.initialize()
		lang=languageHandler.getLanguage()
		_espeak.setVoiceByLanguage(lang)
		self._voiceList=_espeak.getVoiceList()
		self._variantDict=_espeak.getVariantDict()
		self.variant="max"
		self.rate=40
		self.pitch=40
		self.inflection=75


	def speakText(self,text,index=None):
		_espeak.speak(text, index=index)

	def cancel(self):
		_espeak.stop()

	def pause(self,switch):
		_espeak.pause(switch)

	def _get_rate(self):
		val=_espeak.getParameter(_espeak.espeakRATE,1)
		return self._paramToPercent(val,_espeak.minRate,_espeak.maxRate)

	def _set_rate(self,rate):
		val=self._percentToParam(rate, _espeak.minRate, _espeak.maxRate)
		_espeak.setParameter(_espeak.espeakRATE,val,0)

	def _get_pitch(self):
		val=_espeak.getParameter(_espeak.espeakPITCH,1)
		return self._paramToPercent(val,_espeak.minPitch,_espeak.maxPitch)

	def _set_pitch(self,pitch):
		val=self._percentToParam(pitch, _espeak.minPitch, _espeak.maxPitch)
		_espeak.setParameter(_espeak.espeakPITCH,val,0)

	def _get_inflection(self):
		val=_espeak.getParameter(_espeak.espeakRANGE,1)
		return self._paramToPercent(val,_espeak.minPitch,_espeak.maxPitch)

	def _set_inflection(self,val):
		val=self._percentToParam(val, _espeak.minPitch, _espeak.maxPitch)
		_espeak.setParameter(_espeak.espeakRANGE,val,0)

	def _get_volume(self):
		return _espeak.getParameter(_espeak.espeakVOLUME,1)

	def _set_volume(self,volume):
		_espeak.setParameter(_espeak.espeakVOLUME,volume,0)

	def _get_voice(self):
		curVoice = _espeak.getCurrentVoice()
		if not curVoice:
			return 0
		for index, voice in enumerate(self._voiceList):
			if voice.identifier.split('+')[0] == curVoice.identifier.split('+')[0]:
				return index + 1
		return 0

	def _set_voice(self, index):
		if index == 0:
			return
		_espeak.setVoiceAndVariant(voice=self._voiceList[index - 1].identifier)

	def _get_voiceCount(self):
		return len(self._voiceList)

	def getVoiceName(self,num):
		num=num-1
		return "%s (%s)"%(self._voiceList[num].name,self._voiceList[num].identifier)

	def _get_lastIndex(self):
		return _espeak.lastIndex

	def terminate(self):
		_espeak.terminate()

	def _get_variant(self):
		return self._variant

	def _set_variant(self,val):
		self._variant = val if val in self._variantDict else "none"
		_espeak.setVoiceAndVariant(variant=val)

	def _get_variantCount(self):
		return len(self._variantDict)

	def getVariantName(self,num):
		return self._variantDict.values()[num]

	def getVariantIdentifier(self,num):
		return self._variantDict.keys()[num]
