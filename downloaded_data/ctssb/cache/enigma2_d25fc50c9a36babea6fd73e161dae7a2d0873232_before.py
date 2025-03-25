from ChannelSelection import ChannelSelection, BouquetSelector, SilentBouquetSelector, EPGBouquetSelector

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ActionMap import NumberActionMap
from Components.Harddisk import harddiskmanager
from Components.Input import Input
from Components.Label import Label
from Components.PluginComponent import plugins
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.Boolean import Boolean
from Components.config import config, ConfigBoolean, ConfigClock
from Components.SystemInfo import SystemInfo
from Components.UsageConfig import preferredInstantRecordPath, defaultMoviePath, preferredTimerPath, ConfigSelection
from Components.Task import Task, Job, job_manager as JobManager
from Components.Pixmap import MovingPixmap, MultiPixmap
from Components.Sources.StaticText import StaticText
from Components.ScrollLabel import ScrollLabel
from EpgSelection import EPGSelection
from Plugins.Plugin import PluginDescriptor

from Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.Dish import Dish
from Screens.EventView import EventViewEPGSelect, EventViewSimple
from Screens.InputBox import InputBox
from Screens.MessageBox import MessageBox
from Screens.MinuteInput import MinuteInput
from Screens.TimerSelection import TimerSelection
from Screens.PictureInPicture import PictureInPicture
from Screens.SubtitleDisplay import SubtitleDisplay
from Screens.RdsDisplay import RdsInfoDisplay, RassInteractive
from Screens.Standby import Standby, TryQuitMainloop
from Screens.TimeDateInput import TimeDateInput
from Screens.TimerEdit import TimerEditList
from Screens.UnhandledKey import UnhandledKey
from ServiceReference import ServiceReference
from skin import parseColor

from RecordTimer import RecordTimer, RecordTimerEntry, parseEvent, AFTEREVENT, findSafeRecordPath
from TimerEntry import TimerEntry as TimerEntry_TimerEntry

from timer import TimerEntry

from Tools import Directories, ASCIItranslit, Notifications

from enigma import eBackgroundFileEraser, eTimer, eServiceCenter, eDVBServicePMTHandler, iServiceInformation, iPlayableService, eServiceReference, eServiceCenter, eEPGCache, eActionMap

from time import time, localtime, strftime
from os import stat as os_stat, listdir as os_listdir, link as os_link, path as os_path, system as os_system, statvfs, remove as os_remove
from bisect import insort
from random import randint

# hack alert!
from Menu import MainMenu, Menu, mdom
from Setup import Setup
import Screens.Standby

def isStandardInfoBar(self):
	return ".InfoBar'>" in `self`

def isMoviePlayerInfoBar(self):
	return ".MoviePlayer" in `self`

def setResumePoint(session):
	global resumePointCache, resumePointCacheLast
	service = session.nav.getCurrentService()
	ref = session.nav.getCurrentlyPlayingServiceReference()
	if (service is not None) and (ref is not None): # and (ref.type != 1):
		# ref type 1 has its own memory...
		seek = service.seek()
		if seek:
			pos = seek.getPlayPosition()
			if not pos[0]:
				key = ref.toString()
				lru = int(time())
				l = seek.getLength()
				if l:
					l = l[1]
				else:
					l = None
				resumePointCache[key] = [lru, pos[1], l]
				print '[ResumePionts] length',len(resumePointCache)
				if len(resumePointCache) > 50:
					candidate = key
					for k,v in resumePointCache.items():
						if v[0] < lru:
							candidate = k
					del resumePointCache[candidate]
# 				print '[ResumePionts] test',(lru - resumePointCacheLast)
# 				if lru - resumePointCacheLast > 3600:
				saveResumePoints()

def delResumePoint(ref):
	global resumePointCache, resumePointCacheLast
	try:
		del resumePointCache[ref.toString()]
	except KeyError:
		pass
# 	if int(time()) - resumePointCacheLast > 3600:
		saveResumePoints()

def getResumePoint(session):
	global resumePointCache
	ref = session.nav.getCurrentlyPlayingServiceReference()
	if (ref is not None) and (ref.type != 1):
		try:
			entry = resumePointCache[ref.toString()]
			entry[0] = int(time()) # update LRU timestamp
			return entry[1]
		except KeyError:
			return None

def saveResumePoints():
	print '[ResumePionts] saving'
	global resumePointCache, resumePointCacheLast
	import cPickle
	try:
		f = open('/etc/enigma2/resumepoints.pkl', 'wb')
		cPickle.dump(resumePointCache, f, cPickle.HIGHEST_PROTOCOL)
	except Exception, ex:
		print "[InfoBar] Failed to write resumepoints:", ex
	resumePointCacheLast = int(time())

def loadResumePoints():
	import cPickle
	try:
		return cPickle.load(open('/etc/enigma2/resumepoints.pkl', 'rb'))
	except Exception, ex:
		print "[InfoBar] Failed to load resumepoints:", ex
		return {}

resumePointCache = loadResumePoints()
resumePointCacheLast = int(time())

class InfoBarDish:
	def __init__(self):
		self.dishDialog = self.session.instantiateDialog(Dish)

class InfoBarUnhandledKey:
	def __init__(self):
		self.unhandledKeyDialog = self.session.instantiateDialog(UnhandledKey)
		self.hideUnhandledKeySymbolTimer = eTimer()
		self.hideUnhandledKeySymbolTimer.callback.append(self.unhandledKeyDialog.hide)
		self.checkUnusedTimer = eTimer()
		self.checkUnusedTimer.callback.append(self.checkUnused)
		self.onLayoutFinish.append(self.unhandledKeyDialog.hide)
		eActionMap.getInstance().bindAction('', -0x7FFFFFFF, self.actionA) #highest prio
		eActionMap.getInstance().bindAction('', 0x7FFFFFFF, self.actionB) #lowest prio
		self.flags = (1<<1)
		self.uflags = 0

	#this function is called on every keypress!
	def actionA(self, key, flag):
		self.unhandledKeyDialog.hide()
		if flag != 4:
			if self.flags & (1<<1):
				self.flags = self.uflags = 0
			self.flags |= (1<<flag)
			if flag == 1: # break
				self.checkUnusedTimer.start(0, True)
		return 0

	#this function is only called when no other action has handled this key
	def actionB(self, key, flag):
		if flag != 4:
			self.uflags |= (1<<flag)

	def checkUnused(self):
		if self.flags == self.uflags:
			self.unhandledKeyDialog.show()
			self.hideUnhandledKeySymbolTimer.start(2000, True)

class SecondInfoBar(Screen):
	ADD_TIMER = 0
	REMOVE_TIMER = 1

	def __init__(self, session):
		Screen.__init__(self, session)
		self["epg_description"] = ScrollLabel()
		self["channel"] = Label()
		self["key_red"] = Label()
		self["key_green"] = Label()
		self["key_yellow"] = Label()
		self["key_blue"] = Label()
		self["SecondInfoBar"] = ActionMap(["2ndInfobarActions"],
			{
				"prevPage": self.pageUp,
				"nextPage": self.pageDown,
				"prevEvent": self.prevEvent,
				"nextEvent": self.nextEvent,
				"timerAdd": self.timerAdd,
				"openSimilarList": self.openSimilarList,
			}, -1)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.getEvent
			})

		self.onShow.append(self.__Show)
		self.onHide.append(self.__Hide)

	def pageUp(self):
		self["epg_description"].pageUp()

	def pageDown(self):
		self["epg_description"].pageDown()

	def __Show(self):
		if config.vixsettings.ColouredButtons.value:
			self["key_yellow"].setText(_("Search"))
		self["key_red"].setText(_("Similar"))
		self["key_blue"].setText(_("Extensions"))
		self["SecondInfoBar"].doBind()
		self.getEvent()

	def __Hide(self):
		if self["SecondInfoBar"].bound:
			self["SecondInfoBar"].doUnbind()

	def getEvent(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		self.getNowNext()
		epglist = self.epglist
		if not epglist:
			self.is_now_next = False
			epg = eEPGCache.getInstance()
			ptr = ref and ref.valid() and epg.lookupEventTime(ref, -1)
			if ptr:
				epglist.append(ptr)
				ptr = epg.lookupEventTime(ref, ptr.getBeginTime(), +1)
				if ptr:
					epglist.append(ptr)
		else:
			self.is_now_next = True
		if epglist:
			Event = self.epglist[0]
			Ref = ServiceReference(ref)
			callback = self.eventViewCallback
			self.cbFunc = callback
			self.currentService=Ref
			self.isRecording = (not Ref.ref.flags & eServiceReference.isGroup) and Ref.ref.getPath()
			self.event = Event
			self.key_green_choice = self.ADD_TIMER
			if self.isRecording:
				self["key_green"].setText("")
			else:
				self["key_green"].setText(_("Add timer"))
			self.setEvent(self.event)

	def getNowNext(self):
		epglist = [ ]
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		ptr = info and info.getEvent(0)
		if ptr:
			epglist.append(ptr)
		ptr = info and info.getEvent(1)
		if ptr:
			epglist.append(ptr)
		self.epglist = epglist

	def eventViewCallback(self, setEvent, setService, val): #used for now/next displaying
		epglist = self.epglist
		if len(epglist) > 1:
			tmp = epglist[0]
			epglist[0]=epglist[1]
			epglist[1]=tmp
			setEvent(epglist[0])

	def prevEvent(self):
		if self.cbFunc is not None:
			self.cbFunc(self.setEvent, self.setService, -1)

	def nextEvent(self):
		if self.cbFunc is not None:
			self.cbFunc(self.setEvent, self.setService, +1)

	def removeTimer(self, timer):
		timer.afterEvent = AFTEREVENT.NONE
		self.session.nav.RecordTimer.removeEntry(timer)
		self["key_green"].setText(_("Add timer"))
		self.key_green_choice = self.ADD_TIMER

	def timerAdd(self):
		self.hide()
		self.secondInfoBarWasShown = False
		if self.isRecording:
			return
		event = self.event
		serviceref = self.currentService
		if event is None:
			return
		eventid = event.getEventId()
		refstr = serviceref.ref.toString()
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and timer.service_ref.ref.toString() == refstr:
				cb_func = lambda ret : not ret or self.removeTimer(timer)
				self.session.openWithCallback(cb_func, MessageBox, _("Do you really want to delete %s?") % event.getEventName())
				break
		else:
			newEntry = RecordTimerEntry(self.currentService, checkOldTimers = True, dirname = preferredTimerPath(), *parseEvent(self.event))
			self.session.openWithCallback(self.finishedAdd, TimerEntry_TimerEntry, newEntry)

	def finishedAdd(self, answer):
		print "finished add"
		if answer[0]:
			entry = answer[1]
			simulTimerList = self.session.nav.RecordTimer.record(entry)
			if simulTimerList is not None:
				for x in simulTimerList:
					if x.setAutoincreaseEnd(entry):
						self.session.nav.RecordTimer.timeChanged(x)
				simulTimerList = self.session.nav.RecordTimer.record(entry)
				if simulTimerList is not None:
					self.session.openWithCallback(self.finishSanityCorrection, TimerSanityConflict, simulTimerList)
			self["key_green"].setText(_("Remove timer"))
			self.key_green_choice = self.REMOVE_TIMER
		else:
			self["key_green"].setText(_("Add timer"))
			self.key_green_choice = self.ADD_TIMER
			print "Timeredit aborted"

	def finishSanityCorrection(self, answer):
		self.finishedAdd(answer)

	def setService(self, service):
		self.currentService=service
		if self.isRecording:
			self["channel"].setText(_("Recording"))
		else:
			name = self.currentService.getServiceName()
			if name is not None:
				self["channel"].setText(name)
			else:
				self["channel"].setText(_("unknown service"))

	def sort_func(self,x,y):
		if x[1] < y[1]:
			return -1
		elif x[1] == y[1]:
			return 0
		else:
			return 1

	def setEvent(self, event):
		self.event = event
		if event is None:
			return
		try:
			name = event.getEventName()
			self["channel"].setText(name)
		except:
			pass
		text = ""
		description = event.getShortDescription()
		extended = event.getExtendedDescription()
		if description and extended:
			description += '\n'
		text = description + extended
		self.setTitle(event.getEventName())
		self["epg_description"].setText(text)
		serviceref = self.currentService
		eventid = self.event.getEventId()
		refstr = serviceref.ref.toString()
		isRecordEvent = False
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and timer.service_ref.ref.toString() == refstr:
				isRecordEvent = True
				break
		if isRecordEvent and self.key_green_choice != self.REMOVE_TIMER:
			self["key_green"].setText(_("Remove timer"))
			self.key_green_choice = self.REMOVE_TIMER
		elif not isRecordEvent and self.key_green_choice != self.ADD_TIMER:
			self["key_green"].setText(_("Add timer"))
			self.key_green_choice = self.ADD_TIMER

	def openSimilarList(self):
		id = self.event and self.event.getEventId()
		refstr = str(self.currentService)
		if id is not None:
			self.hide()
			self.secondInfoBarWasShown = False
			self.session.open(EPGSelection, refstr, None, id)

class InfoBarShowHide:
	""" InfoBar show/hide control, accepts toggleShow and hide actions, might start
	fancy animations. """
	STATE_HIDDEN = 0
	STATE_HIDING = 1
	STATE_SHOWING = 2
	STATE_SHOWN = 3

	def __init__(self):
		self["ShowHideActions"] = ActionMap( ["InfobarShowHideActions"] ,
			{
				"toggleShow": self.toggleShow,
				"LongOKPressed": self.LongOKPressed,
				"hide": self.keyHide,
			}, 1) # lower prio to make it possible to override ok and cancel..

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.serviceStarted,
			})

		self.__state = self.STATE_SHOWN
		self.__locked = 0

		self.hideTimer = eTimer()
		self.hideTimer.callback.append(self.doTimerHide)
		self.hideTimer.start(5000, True)

		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)

		self.onShowHideNotifiers = []

		self.standardInfoBar = False
		self.secondInfoBarScreen = ""
		if isStandardInfoBar(self):
			self.secondInfoBarScreen = self.session.instantiateDialog(SecondInfoBar)
			self.secondInfoBarScreen.hide()
			self.standardInfoBar = True
		self.secondInfoBarWasShown = False
		self.EventViewIsShown = False

	def LongOKPressed(self):
		if isinstance(self, InfoBarEPG):
			if config.vixsettings.QuickEPG_mode.value == "1":
				self.openInfoBarEPG()

	def keyHide(self):
		if self.__state == self.STATE_HIDDEN:
			if config.vixsettings.QuickEPG_mode.value == "2":
				self.openInfoBarEPG()
			else:
				self.hide()
				if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
					self.secondInfoBarScreen.hide()
					self.secondInfoBarWasShown = False
			if self.session.pipshown:
				self.showPiP()
		else:
			self.hide()
			if self.pvrStateDialog:
				self.pvrStateDialog.hide()


	def connectShowHideNotifier(self, fnc):
		if not fnc in self.onShowHideNotifiers:
			self.onShowHideNotifiers.append(fnc)

	def disconnectShowHideNotifier(self, fnc):
		if fnc in self.onShowHideNotifiers:
			self.onShowHideNotifiers.remove(fnc)

	def serviceStarted(self):
		if self.execing:
			if config.usage.show_infobar_on_zap.value:
				self.doShow()

	def __onShow(self):
		self.__state = self.STATE_SHOWN
		for x in self.onShowHideNotifiers:
			x(True)
		self.startHideTimer()

	def startHideTimer(self):
		if self.__state == self.STATE_SHOWN and not self.__locked:
			self.hideTimer.stop()
			idx = config.usage.infobar_timeout.index
			if idx:
				self.hideTimer.start(idx*1000, True)
		elif (self.secondInfoBarScreen and self.secondInfoBarScreen.shown) or (not config.usage.show_second_infobar.value and self.EventViewIsShown):
			self.hideTimer.stop()
			idx = config.usage.second_infobar_timeout.index
			if idx:
				self.hideTimer.start(idx*1000, True)

	def __onHide(self):
		self.__state = self.STATE_HIDDEN
		for x in self.onShowHideNotifiers:
			x(False)

	def doShow(self):
		self.show()
		self.startHideTimer()

	def doTimerHide(self):
		self.hideTimer.stop()
		if self.__state == self.STATE_SHOWN:
			self.hide()
			if self.pvrStateDialog:
				self.pvrStateDialog.hide()
		elif self.__state == self.STATE_HIDDEN and self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		elif self.__state == self.STATE_HIDDEN and self.EventViewIsShown:
			try:
				self.eventView.close()
			except:
				pass
			self.EventViewIsShown = False

	def toggleShow(self):
		if self.__state == self.STATE_HIDDEN:
			if not self.secondInfoBarWasShown:
				self.show()
			if self.secondInfoBarScreen:
				self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
			self.EventViewIsShown = False
		elif self.secondInfoBarScreen and config.usage.show_second_infobar.value and not self.secondInfoBarScreen.shown:
			self.hide()
			self.secondInfoBarScreen.show()
			self.secondInfoBarWasShown = True
			self.startHideTimer()
		elif (not config.usage.show_second_infobar.value or isMoviePlayerInfoBar(self)) and not self.EventViewIsShown:
			self.hide()
			self.openEventView()
			self.EventViewIsShown = True
			self.startHideTimer()
		else:
			self.hide()
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
			elif self.EventViewIsShown:
				try:
					self.eventView.close()
				except:
					pass
				self.EventViewIsShown = False

	def lockShow(self):
		self.__locked = self.__locked + 1
		if self.execing:
			self.show()
			self.hideTimer.stop()

	def unlockShow(self):
		self.__locked = self.__locked - 1
		if self.__locked  <0:
			self.__locked = 0
		if self.execing:
			self.startHideTimer()

class NumberZap(Screen):
	def quit(self):
		self.Timer.stop()
		self.close(0)

	def keyOK(self):
		self.Timer.stop()
		self.close(int(self["number"].getText()))

	def handleServiceName(self):
		service, bouquet = self.searchNumber(int(self["number"].getText()))
		self ["servicename"].text = ServiceReference(service).getServiceName()

	def keyNumberGlobal(self, number):
		self.Timer.start(5000, True)		#reset timer
		self.field = self.field + str(number)
		self["number"].setText(self.field)
		self["number_summary"].setText(self.field)

		self.handleServiceName()

		if len(self.field) >= 4:
			self.keyOK()

	def __init__(self, session, number, searchNumberFunction):
		Screen.__init__(self, session)
		self.onChangedEntry = [ ]
		self.field = str(number)
		self.searchNumber = searchNumberFunction

		self["channel"] = Label(_("Channel:"))
		self["channel_summary"] = StaticText(_("Channel:"))

		self["number"] = Label(self.field)
		self["number_summary"] = StaticText(self.field)
		self["servicename"] = Label()

		self.handleServiceName()

		self["actions"] = NumberActionMap( [ "SetupActions" ],
			{
				"cancel": self.quit,
				"ok": self.keyOK,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumberGlobal
			})

		self.Timer = eTimer()
		self.Timer.callback.append(self.keyOK)
		self.Timer.start(5000, True)

class InfoBarNumberZap:
	""" Handles an initial number for NumberZapping """
	def __init__(self):
		self["NumberActions"] = NumberActionMap( [ "NumberActions"],
			{
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumberGlobal,
			})

	def keyNumberGlobal(self, number):
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable() and number == 0:
			InfoBarTimeshiftState._mayShow(self)
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MaxX/2, self.pvrStateDialog["PTSSeekPointer"].position[1])
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.ptsSeekPointerOK()
			return

		if self.pts_blockZap_timer.isActive():
			return

		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self)
			return

#		print "You pressed number " + str(number)
		if number == 0:
			if isinstance(self, InfoBarPiP) and self.pipHandles0Action():
				self.pipDoHandle0Action()
			else:
				if config.usage.panicbutton.value:
					self.servicelist.history = [ ]
					self.servicelist.history_pos = 0
					self.zapToNumber(1)
				else:
					self.servicelist.recallPrevService()
		else:
			if self.has_key("TimeshiftActions") and not self.timeshift_enabled:
				self.session.openWithCallback(self.numberEntered, NumberZap, number, self.searchNumber)
		if number and config.timeshift.enabled.value and self.timeshift_enabled and not self.isSeekable():
			self.session.openWithCallback(self.numberEntered, NumberZap, number)

	def numberEntered(self, retval):
#		print self.servicelist
		if retval > 0:
			self.zapToNumber(retval)

	def searchNumberHelper(self, serviceHandler, num, bouquet):
		servicelist = serviceHandler.list(bouquet)
		if not servicelist is None:
			serviceIterator = servicelist.getNext()
			while serviceIterator.valid():
				if num == serviceIterator.getChannelNum():
					return serviceIterator
				serviceIterator = servicelist.getNext()
		return None

	def searchNumber(self, number):
		bouquet = self.servicelist.getRoot()
		service = None
		serviceHandler = eServiceCenter.getInstance()
		service = self.searchNumberHelper(serviceHandler, number, bouquet)
		if config.usage.multibouquet.value:
			service = self.searchNumberHelper(serviceHandler, number, bouquet) #search the current bouqeut first
			if service is None:
				bouquet = self.servicelist.bouquet_root
				bouquetlist = serviceHandler.list(bouquet)
				if not bouquetlist is None:
					bouquet = bouquetlist.getNext()
					while bouquet.valid():
						if bouquet.flags & eServiceReference.isDirectory:
							service = self.searchNumberHelper(serviceHandler, number, bouquet)
							if service is not None:
								playable = not (service.flags & (eServiceReference.isMarker|eServiceReference.isDirectory)) or (service.flags & eServiceReference.isNumberedMarker)
								if not playable:
									service = None
								break
							if config.usage.alternative_number_mode.value:
								break
						bouquet = bouquetlist.getNext()
		return service, bouquet

	def zapToNumber(self, number):
		service, bouquet = self.searchNumber(number)
		if not service is None:
			if self.servicelist.getRoot() != bouquet: #already in correct bouquet?
				self.servicelist.clearPath()
				if self.servicelist.bouquet_root != bouquet:
					self.servicelist.enterPath(self.servicelist.bouquet_root)
				self.servicelist.enterPath(bouquet)
			self.servicelist.setCurrentSelection(service) #select the service in servicelist
			self.servicelist.zap(enable_pipzap = True)

config.misc.initialchannelselection = ConfigBoolean(default = True)

class InfoBarChannelSelection:
	""" ChannelSelection - handles the channelSelection dialog and the initial
	channelChange actions which open the channelSelection dialog """
	def __init__(self):
		#instantiate forever
		self.servicelist = self.session.instantiateDialog(ChannelSelection)

		self["ChannelSelectActions"] = HelpableActionMap(self, "InfobarChannelSelection",
			{
				"switchChannelUp": (self.switchChannelUp, _("open servicelist(up)")),
				"switchChannelDown": (self.switchChannelDown, _("open servicelist(down)")),
				"LeftPressed": self.LeftPressed,
				"RightPressed": self.RightPressed,
				"ChannelPlusPressed": self.ChannelPlusPressed,
				"ChannelMinusPressed": self.ChannelMinusPressed,
				"zapUp": (self.zapUp, _("previous channel")),
				"zapDown": (self.zapDown, _("next channel")),
				"historyBack": (self.historyBack, _("previous channel in history")),
				"historyNext": (self.historyNext, _("next channel in history")),
				"openServiceList": (self.openServiceList, _("open servicelist")),
				"openSatellites": (self.openSatellites, _("open Satellites")),
			})

	def LeftPressed(self):
		if config.vixsettings.QuickEPG_mode.value == "3":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.openInfoBarEPG()
		else:
			self.zapUp()

	def RightPressed(self):
		if config.vixsettings.QuickEPG_mode.value == "3":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.openInfoBarEPG()
		else:
			self.zapDown()

	def ChannelPlusPressed(self):
		if config.usage.channelbutton_mode.value == "0":
			self.zapDown()
		elif config.usage.channelbutton_mode.value == "1":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.openServiceList()
		elif config.usage.channelbutton_mode.value == "2":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.serviceListType = "Norm"
			self.servicelist.showFavourites()
			self.session.execDialog(self.servicelist)

	def ChannelMinusPressed(self):
		if config.usage.channelbutton_mode.value == "0":
			self.zapUp()
		elif config.usage.channelbutton_mode.value == "1":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.openServiceList()
		elif config.usage.channelbutton_mode.value == "2":
			if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
				self.secondInfoBarScreen.hide()
				self.secondInfoBarWasShown = False
			self.serviceListType = "Norm"
			self.servicelist.showFavourites()
			self.session.execDialog(self.servicelist)

	def showTvChannelList(self, zap=False):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		self.servicelist.setModeTv()
		if zap:
			self.servicelist.zap()
		if config.usage.show_servicelist.value:
			self.session.execDialog(self.servicelist)

	def showRadioChannelList(self, zap=False):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="showRadioChannelList")
		else:
			self.servicelist.setModeRadio()
			if zap:
				self.servicelist.zap()
			if config.usage.show_servicelist.value:
				self.session.execDialog(self.servicelist)

	def historyBack(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			InfoBarTimeshiftState._mayShow(self)
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX, self.pvrStateDialog["PTSSeekPointer"].position[1])
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.ptsSeekPointerOK()
		elif self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="historyBack")
		else:
			self.servicelist.historyBack()

	def historyNext(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			InfoBarTimeshiftState._mayShow(self)
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MaxX, self.pvrStateDialog["PTSSeekPointer"].position[1])
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.ptsSeekPointerOK()
		elif self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="historyNext")
		else:
			self.servicelist.historyNext()

	def switchChannelUp(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="switchChannelUp")
		else:
			if not config.usage.show_bouquetalways.value:
 # 				self.servicelist.moveUp()
				self.session.execDialog(self.servicelist)
			else:
				self.servicelist.showFavourites()
				self.session.execDialog(self.servicelist)

	def switchChannelDown(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="switchChannelDown")
		else:
			if not config.usage.show_bouquetalways.value:
#  				self.servicelist.moveDown()
				self.session.execDialog(self.servicelist)
			else:
				self.servicelist.showFavourites()
				self.session.execDialog(self.servicelist)

	def openServiceList(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="openServiceList")
		else:
			self.session.execDialog(self.servicelist)

	def openSatellites(self):
		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="openSatellites")
		else:
			self.servicelist.showSatellites()
			self.session.execDialog(self.servicelist)

	def openInfoBarEPG(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		self.EPGtype = "infobar"
		self.session.open(EPGSelection, self.servicelist, self.EPGtype)

	def zapUp(self):
		if self.pts_blockZap_timer.isActive():
			return

		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="zapUp")
		else:
			if self.servicelist.inBouquet():
				prev = self.servicelist.getCurrentSelection()
				if prev:
					prev = prev.toString()
					while True:
						if config.usage.quickzap_bouquet_change.value:
							if self.servicelist.atBegin():
								self.servicelist.prevBouquet()
						self.servicelist.moveUp()
						cur = self.servicelist.getCurrentSelection()
						if cur and (cur.toString() == prev or self.isPlayable(cur)):
							break
			else:
				self.servicelist.moveUp()
			self.servicelist.zap(enable_pipzap = True)

	def zapDown(self):
		if self.pts_blockZap_timer.isActive():
			return

		if self.save_current_timeshift and self.timeshift_enabled:
			InfoBarTimeshift.saveTimeshiftActions(self, postaction="zapDown")
		else:
			if self.servicelist.inBouquet():
				prev = self.servicelist.getCurrentSelection()
				if prev:
					prev = prev.toString()
					while True:
						if config.usage.quickzap_bouquet_change.value and self.servicelist.atEnd():
							self.servicelist.nextBouquet()
						else:
							self.servicelist.moveDown()
						cur = self.servicelist.getCurrentSelection()
						if cur and (cur.toString() == prev or self.isPlayable(cur)):
							break
			else:
				self.servicelist.moveDown()
			self.servicelist.zap(enable_pipzap = True)

	def isPlayable(self, ref):
		if not (ref.flags & eServiceReference.isMarker):
			cur_running = self.session.nav.getCurrentlyPlayingServiceReference()
			if not cur_running:
				cur_running = eServiceReference()
			info = eServiceCenter.getInstance().info(ref)
			if info and info.isPlayable(ref, cur_running):
				return True
		return False

class InfoBarMenu:
	""" Handles a menu action, to open the (main) menu """
	def __init__(self):
		self["MenuActions"] = HelpableActionMap(self, "InfobarMenuActions",
			{
				"mainMenu": (self.mainMenu, _("Enter main menu...")),
				"showNetworkSetup": (self.showNetworkMounts, _("Show network mounts ...")),
				"showRFmod": (self.showRFSetup, _("Show RFmod setup...")),
				"toggleAspectRatio": (self.toggleAspectRatio, _("Toggle aspect ratio...")),
			})
		self.session.infobar = None

	def mainMenu(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		print "loading mainmenu XML..."
		menu = mdom.getroot()
		assert menu.tag == "menu", "root element in menu must be 'menu'!"

		self.session.infobar = self
		# so we can access the currently active infobar from screens opened from within the mainmenu
		# at the moment used from the SubserviceSelection

		self.session.openWithCallback(self.mainMenuClosed, MainMenu, menu)

	def toggleAspectRatio(self):
		ASPECT = [ "auto", "16_9", "4_3" ]
		ASPECT_MSG = { "auto":"Auto", "16_9":"16:9", "4_3":"4:3" }
		if config.av.aspect.value in ASPECT:
			index = ASPECT.index(config.av.aspect.value)
			config.av.aspect.value = ASPECT[(index+1)%3]
		else:
			config.av.aspect.value = "auto"
		config.av.aspect.save()
		self.session.open(MessageBox, _("AV aspect is %s." % ASPECT_MSG[config.av.aspect.value]), MessageBox.TYPE_INFO, timeout=5)

	def showNetworkMounts(self):
		menulist = mdom.getroot().findall('menu')
		for item in menulist:
			if item.attrib['entryID'] == 'setup_selection':
				menulist = item.findall('menu')
				for item in menulist:
					if item.attrib['entryID'] == 'system_selection':
						menulist = item.findall('menu')
						for item in menulist:
							if item.attrib['entryID'] == 'network_menu':
								menu = item
		assert menu.tag == "menu", "root element in menu must be 'menu'!"
		self.session.openWithCallback(self.mainMenuClosed, Menu, menu)

	def showRFSetup(self):
		self.session.openWithCallback(self.mainMenuClosed, Setup, 'RFmod')

	def mainMenuClosed(self, *val):
		self.session.infobar = None

class InfoBarSimpleEventView:
	""" Opens the Eventview for now/next """
	def __init__(self):
		self["EPGActions"] = HelpableActionMap(self, "InfobarEPGActions",
			{
				"InfoPressed": (self.InfoPressed, _("show program information...")),
				"EPGPressed":  (self.showDefaultEPG, _("show EPG...")),
				"showInfobarOrEpgWhenInfobarAlreadyVisible": self.showEventInfoWhenNotVisible,
			})

	def showEventInfoWhenNotVisible(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.shown:
			self.openEventView()
		else:
			self.toggleShow()
			return 1


class InfoBarEPG:
	""" EPG - Opens an EPG list when the showEPGList action fires """
	def __init__(self):
		self.is_now_next = False
		self.dlg_stack = [ ]
		self.bouquetSel = None
		self.eventView = None
		self.epglist = []
		self.defaultEPGType = self.getDefaultEPGtype()
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.__evEventInfoChanged,
			})

		self["EPGActions"] = HelpableActionMap(self, "InfobarEPGActions",
			{
				"InfoPressed": (self.InfoPressed, _("show program information...")),
				"showEventInfoPlugin": (self.showEventInfoPlugins, _("list of EPG views...")),
				"EPGPressed":  (self.showDefaultEPG, _("show EPG...")),
				"showInfobarOrEpgWhenInfobarAlreadyVisible": self.showEventInfoWhenNotVisible,
			})

	def getEPGPluginList(self):
		pluginlist = [(p.name, boundFunction(self.runPlugin, p)) for p in plugins.getPlugins(where = PluginDescriptor.WHERE_EVENTINFO)]
		if pluginlist:
			pluginlist.append((_("Event Info..."), self.openEventView))
			pluginlist.append((_("Graphical EPG..."), self.openGraphEPG))
			pluginlist.append((_("Infobar EPG..."), self.openInfoBarEPG))
			pluginlist.append((_("Multi EPG..."), self.openMultiServiceEPG))
			pluginlist.append((_("Single EPG..."), self.openSingleServiceEPG))
		return pluginlist

	def getDefaultEPGtype(self):
		pluginlist = self.getEPGPluginList()
		config.usage.defaultEPGType=ConfigSelection(default = "None", choices = pluginlist)
		for plugin in pluginlist:
			if plugin[0] == config.usage.defaultEPGType.value:
				return plugin[1]
		return None

	def InfoPressed(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if config.misc.boxtype.getValue().startswith('et') or config.misc.boxtype.getValue().startswith('odin') or config.misc.boxtype.getValue().startswith('venton') or config.misc.boxtype.getValue().startswith('tm') or config.misc.boxtype.getValue().startswith('gb'):
			self.openEventView()
		else:
			self.showDefaultEPG()

	def EPGPressed(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		self.openGraphEPG()

	def showEventInfoWhenNotVisible(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if self.shown:
			self.openEventView()
		else:
			self.toggleShow()
			return 1

	def zapToService(self, service, bouquet=None):
		if service is not None:
			if bouquet:
				self.epg_bouquet = bouquet
			if self.servicelist.getRoot() != self.epg_bouquet: #already in correct bouquet?
				self.servicelist.clearPath()
				if self.servicelist.bouquet_root != self.epg_bouquet:
					self.servicelist.enterPath(self.servicelist.bouquet_root)
				self.servicelist.enterPath(self.epg_bouquet)
			self.servicelist.setCurrentSelection(service) #select the service in servicelist
			self.servicelist.zap(enable_pipzap = True)

	def getBouquetServices(self, bouquet):
		services = [ ]
		servicelist = eServiceCenter.getInstance().list(bouquet)
		if not servicelist is None:
			while True:
				service = servicelist.getNext()
				if not service.valid(): #check if end of list
					break
				if service.flags & (eServiceReference.isDirectory | eServiceReference.isMarker): #ignore non playable services
					continue
				services.append(ServiceReference(service))
		return services

	def openBouquetEPG(self, bouquet, withCallback=True):
		services = self.getBouquetServices(bouquet)
		if services:
			self.epg_bouquet = bouquet
			if withCallback:
				self.dlg_stack.append(self.session.openWithCallback(self.closed, EPGSelection, services, self.zapToService, None, self.changeBouquetCB, self.EPGtype, self.StartBouquet))
			else:
				self.session.open(EPGSelection, services, self.zapToService, None, self.changeBouquetCB, self.EPGtype, self.StartBouquet)

	def changeBouquetCB(self, epgcall):
		bouquets = self.servicelist.getBouquetList()
		self.epg = epgcall
		self.session.openWithCallback(self.onBouquetSelectorClose, EPGBouquetSelector, self.bouquets, self.epg_bouquet)

	def onBouquetSelectorClose(self, bouquet):
		if bouquet:
			services = self.getBouquetServices(bouquet)
			if len(services):
				self.epg_bouquet = bouquet
				self.epg.setServices(services)
				self.epg.setTitle(ServiceReference(self.epg_bouquet).getServiceName())

	def closed(self, ret=False):
		closedScreen = self.dlg_stack.pop()
		if self.bouquetSel and closedScreen == self.bouquetSel:
			self.bouquetSel = None
		elif self.eventView and closedScreen == self.eventView:
			self.eventView = None
		if ret:
			dlgs=len(self.dlg_stack)
			if dlgs > 0:
				self.dlg_stack[dlgs-1].close(dlgs > 1)

	def openMultiServiceEPG(self, withCallback=True):
		self.EPGtype = "multi"
		Servicelist = self.servicelist
		self.StartBouquet = Servicelist
		if config.epgselection.showbouquet_multi.value:
			self.bouquets = self.servicelist.getBouquetList()
			if self.bouquets is None:
				cnt = 0
			else:
				cnt = len(self.bouquets)
			if cnt > 1: # show bouquet list
				if withCallback:
					self.bouquetSel = self.session.openWithCallback(self.closed, BouquetSelector, self.bouquets, self.openBouquetEPG, enableWrapAround=True)
					self.dlg_stack.append(self.bouquetSel)
				else:
					self.bouquetSel = self.session.open(BouquetSelector, self.bouquets, self.openBouquetEPG, enableWrapAround=True)
			elif cnt == 1:
				self.openBouquetEPG(self.bouquets[0][1], withCallback, self.StartBouquet)
		else:
			self.bouquets = Servicelist and self.servicelist.getBouquetList()
			self.epg_bouquet = Servicelist and Servicelist.getRoot()
			if self.epg_bouquet is not None:
				if len(self.bouquets) > 1 :
					cb = self.changeBouquetCB
				else:
					cb = None
				services = self.getBouquetServices(self.epg_bouquet)
				self.session.openWithCallback(self.GraphEPG_cleanup, EPGSelection, services, self.zapToService, None, cb, self.EPGtype, self.StartBouquet)

	def changeServiceCB(self, direction, epg):
		if self.serviceSel:
			if direction > 0:
				self.serviceSel.nextService()
			else:
				self.serviceSel.prevService()
			epg.setService(self.serviceSel.currentService())

	def SingleServiceEPGClosed(self, ret=False):
		self.serviceSel = None

	def openSingleServiceEPG(self):
		self.session.openWithCallback(self.reopen,EPGSelection, self.servicelist)

	def openInfoBarEPG(self):
		self.EPGtype = "infobar"
		self.session.open(EPGSelection, self.servicelist, self.EPGtype)

	def openGraphEPG(self, withCallback=True):
		self.EPGtype = "graph"
		Servicelist = self.servicelist
		self.StartBouquet = Servicelist
		if config.epgselection.showbouquet_vixepg.value:
			self.bouquets = self.servicelist.getBouquetList()
			if self.bouquets is None:
				cnt = 0
			else:
				cnt = len(self.bouquets)
			if cnt > 1: # show bouquet list
				if withCallback:
					self.bouquetSel = self.session.openWithCallback(self.reopen, BouquetSelector, self.bouquets, self.openBouquetEPG, enableWrapAround=True)
					self.dlg_stack.append(self.bouquetSel)
				else:
					self.bouquetSel = self.session.open(BouquetSelector, self.bouquets, self.openBouquetEPG, enableWrapAround=True)
			elif cnt == 1:
				self.openBouquetEPG(self.bouquets[0][1], withCallback)
		else:
			self.bouquets = Servicelist and self.servicelist.getBouquetList()
			self.epg_bouquet = Servicelist and Servicelist.getRoot()
			if self.epg_bouquet is not None:
				if len(self.bouquets) > 1 :
					cb = self.changeBouquetCB
				else:
					cb = None
				services = self.getBouquetServices(self.epg_bouquet)
				self.session.openWithCallback(self.closeGraphEPG, EPGSelection, services, self.zapToService, None, cb, self.EPGtype, self.StartBouquet)

	def closeGraphEPG(self, ret=False):
		self.GraphEPG_cleanup()
		self.reopen(ret)

	def GraphEPG_cleanup(self, ret=False):
		global epg
		epg = None

	def reopen(self, answer):
		if answer == 'reopen':
			self.openGraphEPG()
		elif answer == 'close' and isMoviePlayerInfoBar(self):
			self.lastservice = self.session.nav.getCurrentlyPlayingServiceReference()
			self.close()

	def showCoolTVGuide(self):
		if Directories.fileExists("/usr/lib/enigma2/python/Plugins/Extensions/CoolTVGuide/plugin.pyo"):
			for plugin in plugins.getPlugins([PluginDescriptor.WHERE_EXTENSIONSMENU, PluginDescriptor.WHERE_EVENTINFO]):
				if plugin.name == _("Cool TV Guide"):
					self.runPlugin(plugin)
					break
		else:
			self.session.open(MessageBox, _("The Cool TV Guide plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

	def showEventInfoPlugins(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False

		pluginlist = self.getEPGPluginList()
		if pluginlist:
			pluginlist.append((_("Select default EPG type..."), self.SelectDefaultInfoPlugin))
			self.session.openWithCallback(self.EventInfoPluginChosen, ChoiceBox, title=_("Please choose an extension..."), list = pluginlist, skin_name = "EPGExtensionsList")
		else:
			self.openSingleServiceEPG()

	def runPlugin(self, plugin):
		plugin(session = self.session, servicelist = self.servicelist)

	def EventInfoPluginChosen(self, answer):
		if answer is not None:
			answer[1]()

	def SelectDefaultInfoPlugin(self):
		self.session.openWithCallback(self.DefaultInfoPluginChosen, ChoiceBox, title=_("Please select a default EPG type..."), list = self.getEPGPluginList(), skin_name = "EPGExtensionsList")

	def DefaultInfoPluginChosen(self, answer):
		if answer is not None:
			self.defaultEPGType = answer[1]
			config.usage.defaultEPGType.value = answer[0]
			config.usage.defaultEPGType.save()

	def openSimilarList(self, eventid, refstr):
		self.session.open(EPGSelection, refstr, None, eventid)

	def getNowNext(self):
		epglist = [ ]
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		ptr = info and info.getEvent(0)
		if ptr:
			epglist.append(ptr)
		ptr = info and info.getEvent(1)
		if ptr:
			epglist.append(ptr)
		self.epglist = epglist

	def __evEventInfoChanged(self):
		if self.is_now_next and len(self.dlg_stack) == 1:
			self.getNowNext()
			if self.eventView and self.epglist:
				self.eventView.setEvent(self.epglist[0])

	def showDefaultEPG(self):
		if self.defaultEPGType is not None:
			self.defaultEPGType()
			return
		self.EPGPressed()

	def openEventView(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		self.getNowNext()
		epglist = self.epglist
		if not epglist:
			self.is_now_next = False
			epg = eEPGCache.getInstance()
			ptr = ref and ref.valid() and epg.lookupEventTime(ref, -1)
			if ptr:
				epglist.append(ptr)
				ptr = epg.lookupEventTime(ref, ptr.getBeginTime(), +1)
				if ptr:
					epglist.append(ptr)
		else:
			self.is_now_next = True
		if epglist:
			self.eventView = self.session.openWithCallback(self.closed, EventViewEPGSelect, epglist[0], ServiceReference(ref), self.eventViewCallback, self.openSingleServiceEPG, self.openMultiServiceEPG, self.openSimilarList)
			self.dlg_stack.append(self.eventView)

	def eventViewCallback(self, setEvent, setService, val): #used for now/next displaying
		epglist = self.epglist
		if len(epglist) > 1:
			tmp = epglist[0]
			epglist[0]=epglist[1]
			epglist[1]=tmp
			setEvent(epglist[0])

class InfoBarRdsDecoder:
	"""provides RDS and Rass support/display"""
	def __init__(self):
		self.rds_display = self.session.instantiateDialog(RdsInfoDisplay)
		self.session.instantiateSummaryDialog(self.rds_display)
		self.rass_interactive = None

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.__serviceStopped,
				iPlayableService.evUpdatedRassSlidePic: self.RassSlidePicChanged
			})

		self["RdsActions"] = ActionMap(["InfobarRdsActions"],
		{
			"startRassInteractive": self.startRassInteractive
		},-1)

		self["RdsActions"].setEnabled(False)

		self.onLayoutFinish.append(self.rds_display.show)
		self.rds_display.onRassInteractivePossibilityChanged.append(self.RassInteractivePossibilityChanged)

	def RassInteractivePossibilityChanged(self, state):
		self["RdsActions"].setEnabled(state)

	def RassSlidePicChanged(self):
		if not self.rass_interactive:
			service = self.session.nav.getCurrentService()
			decoder = service and service.rdsDecoder()
			if decoder:
				decoder.showRassSlidePicture()

	def __serviceStopped(self):
		if self.rass_interactive is not None:
			rass_interactive = self.rass_interactive
			self.rass_interactive = None
			rass_interactive.close()

	def startRassInteractive(self):
		self.rds_display.hide()
		self.rass_interactive = self.session.openWithCallback(self.RassInteractiveClosed, RassInteractive)

	def RassInteractiveClosed(self, *val):
		if self.rass_interactive is not None:
			self.rass_interactive = None
			self.RassSlidePicChanged()
		self.rds_display.show()

class Seekbar(Screen):
	skin = """
	<screen position="center,40" size="560,55" title="%s" flags="wfNoBorder">
		<widget name="cursor" position="0,15" size="8,18" pixmap="skin_default/position_arrow.png" alphatest="on" />
		<widget source="session.CurrentService" render="PositionGauge" position="145,30" size="270,10" zPosition="2" pointer="skin_default/position_pointer.png:540,0" transparent="1" foregroundColor="#20224f">
			<convert type="ServicePosition">Gauge</convert>
		</widget>
		<widget name="time" position="50,25" size="100,20" font="Regular;20" halign="left" backgroundColor="#4e5a74" transparent="1" />
		<widget source="session.CurrentService" render="Label" position="420,25" size="90,24" font="Regular;20" halign="right" backgroundColor="#4e5a74" transparent="1">
			<convert type="ServicePosition">Length</convert>
		</widget>
	</screen>""" % _("Seek")

	def __init__(self, session, fwd):
		Screen.__init__(self, session)
		self.session = session
		self.fwd = fwd
		self.percent = 0.0
		self.length = None
		service = session.nav.getCurrentService()
		if service:
			self.seek = service.seek()
			if self.seek:
				self.length = self.seek.getLength()
				position = self.seek.getPlayPosition()
				if self.length and position:
					if int(position[1]) > 0:
						self.percent = float(position[1]) * 100.0 / float(self.length[1])

		self["cursor"] = MovingPixmap()
		self["time"] = Label()

		self["actions"] = ActionMap(["WizardActions", "DirectionActions"], {"back": self.exit, "ok": self.keyOK, "left": self.keyLeft, "right": self.keyRight}, -1)

		self.cursorTimer = eTimer()
		self.cursorTimer.callback.append(self.updateCursor)
		self.cursorTimer.start(200, False)

	def updateCursor(self):
		if self.length:
			x = 145 + int(2.7 * self.percent)
			self["cursor"].moveTo(x, 15, 1)
			self["cursor"].startMoving()
			pts = int(float(self.length[1]) / 100.0 * self.percent)
			self["time"].setText("%d:%02d" % ((pts/60/90000), ((pts/90000)%60)))

	def exit(self):
		self.cursorTimer.stop()
		self.close()

	def keyOK(self):
		if self.length:
			self.seek.seekTo(int(float(self.length[1]) / 100.0 * self.percent))
			self.exit()

	def keyLeft(self):
		self.percent -= float(config.seek.sensibility.value) / 10.0
		if self.percent < 0.0:
			self.percent = 0.0

	def keyRight(self):
		self.percent += float(config.seek.sensibility.value) / 10.0
		if self.percent > 100.0:
			self.percent = 100.0

	def keyNumberGlobal(self, number):
		sel = self["config"].getCurrent()[1]
		if sel == self.positionEntry:
			self.percent = float(number) * 10.0
		else:
			ConfigListScreen.keyNumberGlobal(self, number)

class InfoBarSeek:
	"""handles actions like seeking, pause"""

	SEEK_STATE_PLAY = (0, 0, 0, ">")
	SEEK_STATE_PAUSE = (1, 0, 0, "||")
	SEEK_STATE_EOF = (1, 0, 0, "END")

	def __init__(self, actionmap = "InfobarSeekActions"):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
				iPlayableService.evStart: self.__serviceStarted,

				iPlayableService.evEOF: self.__evEOF,
				iPlayableService.evSOF: self.__evSOF,
			})
		self.fast_winding_hint_message_showed = False

		class InfoBarSeekActionMap(HelpableActionMap):
			def __init__(self, screen, *args, **kwargs):
				HelpableActionMap.__init__(self, screen, *args, **kwargs)
				self.screen = screen

			def action(self, contexts, action):
				print "action:", action
				if action[:5] == "seek:":
					time = int(action[5:])
					self.screen.doSeekRelative(time * 90000)
					return 1
				elif action[:8] == "seekdef:":
					key = int(action[8:])
					time = (-config.seek.selfdefined_13.value, False, config.seek.selfdefined_13.value,
						-config.seek.selfdefined_46.value, False, config.seek.selfdefined_46.value,
						-config.seek.selfdefined_79.value, False, config.seek.selfdefined_79.value)[key-1]
					self.screen.doSeekRelative(time * 90000)
					return 1
				else:
					return HelpableActionMap.action(self, contexts, action)

		self["SeekActions"] = InfoBarSeekActionMap(self, actionmap,
			{
				"playpauseService": self.playpauseService,
				"pauseService": (self.pauseService, _("pause")),
				"unPauseService": (self.unPauseService, _("continue")),

				"seekFwd": (self.seekFwd, _("skip forward")),
				"seekFwdManual": (self.seekFwdManual, _("skip forward (enter time)")),
				"seekBack": (self.seekBack, _("skip backward")),
				"seekBackManual": (self.seekBackManual, _("skip backward (enter time)")),

				"SeekbarFwd": self.seekFwdSeekbar,
				"SeekbarBack": self.seekBackSeekbar
			}, prio=-1)
			# give them a little more priority to win over color buttons
		self["SeekActionsPTS"] = InfoBarSeekActionMap(self, "InfobarSeekActionsPTS",
			{
				"playpauseService": self.playpauseService,
				"pauseService": (self.pauseService, _("pause")),
				"unPauseService": (self.unPauseService, _("continue")),

				"seekFwd": (self.seekFwd, _("skip forward")),
				"seekFwdManual": (self.seekFwdManual, _("skip forward (enter time)")),
				"seekBack": (self.seekBack, _("skip backward")),
				"seekBackManual": (self.seekBackManual, _("skip backward (enter time)")),

				"SeekbarFwd": self.seekFwdSeekbar,
				"SeekbarBack": self.seekBackSeekbar
			}, prio=-1)
			# give them a little more priority to win over color buttons

		self["SeekActions"].setEnabled(False)
		self["SeekActionsPTS"].setEnabled(False)

		self.activity = 0
		self.activityTimer = eTimer()
		self.activityTimer.callback.append(self.doActivityTimer)
		self.seekstate = self.SEEK_STATE_PLAY
		self.lastseekstate = self.SEEK_STATE_PLAY

		self.onPlayStateChanged = [ ]

		self.lockedBecauseOfSkipping = False

		self.__seekableStatusChanged()

	def makeStateForward(self, n):
		return (0, n, 0, ">> %dx" % n)

	def makeStateBackward(self, n):
		return (0, -n, 0, "<< %dx" % n)

	def makeStateSlowMotion(self, n):
		return (0, 0, n, "/%d" % n)

	def isStateForward(self, state):
		return state[1] > 1

	def isStateBackward(self, state):
		return state[1] < 0

	def isStateSlowMotion(self, state):
		return state[1] == 0 and state[2] > 1

	def getHigher(self, n, lst):
		for x in lst:
			if x > n:
				return x
		return False

	def getLower(self, n, lst):
		lst = lst[:]
		lst.reverse()
		for x in lst:
			if x < n:
				return x
		return False

	def showAfterSeek(self):
		if isinstance(self, InfoBarShowHide):
			self.doShow()

	def up(self):
		pass

	def down(self):
		pass

	def getSeek(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None

		seek = service.seek()

		if seek is None or not seek.isCurrentlySeekable():
			return None

		return seek

	def isSeekable(self):
		if self.getSeek() is None or (isStandardInfoBar(self) and not self.timeshift_enabled):
			return False
		return True

	def __seekableStatusChanged(self):
#		print "seekable status changed!"
		if not self.isSeekable():
# 			print "not seekable, return to play"
			self["SeekActions"].setEnabled(False)
			self.setSeekState(self.SEEK_STATE_PLAY)
		else:
#			print "seekable"
			self["SeekActions"].setEnabled(True)
			self.activityTimer.start(200, False)
			for c in self.onPlayStateChanged:
				c(self.seekstate)

	def doActivityTimer(self):
		if self.isSeekable():
			self.activity += 16
			hdd = 1
			if self.activity >= 100:
				self.activity = 0
		else:
 			self.activityTimer.stop()
 			self.activity = 0
 			hdd = 0
		if os_path.exists("/proc/stb/lcd/symbol_hdd"):
			file = open("/proc/stb/lcd/symbol_hdd", "w")
			file.write('%d' % int(hdd))
			file.close()
		if os_path.exists("/proc/stb/lcd/symbol_hddprogress"):
			file = open("/proc/stb/lcd/symbol_hddprogress", "w")
			file.write('%d' % int(self.activity))
			file.close()

	def __serviceStarted(self):
		self.fast_winding_hint_message_showed = False
		self.seekstate = self.SEEK_STATE_PLAY
		self.__seekableStatusChanged()

	def setSeekState(self, state):
		service = self.session.nav.getCurrentService()

		if service is None:
			return False

		if not self.isSeekable():
			if state not in (self.SEEK_STATE_PLAY, self.SEEK_STATE_PAUSE):
				state = self.SEEK_STATE_PLAY

		pauseable = service.pause()

		if pauseable is None:
# 			print "not pauseable."
			state = self.SEEK_STATE_PLAY

		self.seekstate = state

		if pauseable is not None:
			if self.seekstate[0] and self.seekstate[3] == '||':
# 				print "resolved to PAUSE"
				self.activityTimer.stop()
				pauseable.pause()
			elif self.seekstate[0] and self.seekstate[3] == 'END':
# 				print "resolved to STOP"
				self.activityTimer.stop()
				service.stop()
			elif self.seekstate[1]:
# 				print "resolved to FAST FORWARD"
				pauseable.setFastForward(self.seekstate[1])
			elif self.seekstate[2]:
# 				print "resolved to SLOW MOTION"
				pauseable.setSlowMotion(self.seekstate[2])
			else:
# 				print "resolved to PLAY"
				self.activityTimer.start(200, False)
				pauseable.unpause()

		for c in self.onPlayStateChanged:
			c(self.seekstate)

		self.checkSkipShowHideLock()

		return True

	def playpauseService(self):
		if self.seekstate == self.SEEK_STATE_PLAY:
			self.pauseService()
		else:
			if self.seekstate == self.SEEK_STATE_PAUSE:
				if config.seek.on_pause.value == "play":
					self.unPauseService()
				elif config.seek.on_pause.value == "step":
					self.doSeekRelative(1)
				elif config.seek.on_pause.value == "last":
					self.setSeekState(self.lastseekstate)
					self.lastseekstate = self.SEEK_STATE_PLAY
			else:
				self.unPauseService()

	def pauseService(self):
		if self.seekstate != self.SEEK_STATE_EOF:
			self.lastseekstate = self.seekstate
		self.setSeekState(self.SEEK_STATE_PAUSE);

	def unPauseService(self):
		if self.seekstate == self.SEEK_STATE_PLAY:
			return 0
		self.setSeekState(self.SEEK_STATE_PLAY)

	def doSeek(self, pts):
		seekable = self.getSeek()
		if seekable is None:
			return
		seekable.seekTo(pts)

	def doSeekRelative(self, pts):
		seekable = self.getSeek()
		if seekable is None:
			return
		prevstate = self.seekstate

		if self.seekstate == self.SEEK_STATE_EOF:
			if prevstate == self.SEEK_STATE_PAUSE:
				self.setSeekState(self.SEEK_STATE_PAUSE)
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		seekable.seekRelative(pts<0 and -1 or 1, abs(pts))
		if abs(pts) > 100 and config.usage.show_infobar_on_skip.value:
			self.showAfterSeek()

	def seekFwd(self):
		seek = self.getSeek()
		if seek and not (seek.isCurrentlySeekable() & 2):
			if not self.fast_winding_hint_message_showed and (seek.isCurrentlySeekable() & 1):
				self.session.open(MessageBox, _("No fast winding possible yet.. but you can use the number buttons to skip forward/backward!"), MessageBox.TYPE_INFO, timeout=10)
				self.fast_winding_hint_message_showed = True
				return
			return 0 # trade as unhandled action
		if self.seekstate == self.SEEK_STATE_PLAY:
			self.setSeekState(self.makeStateForward(int(config.seek.enter_forward.value)))
		elif self.seekstate == self.SEEK_STATE_PAUSE:
			if len(config.seek.speeds_slowmotion.value):
				self.setSeekState(self.makeStateSlowMotion(config.seek.speeds_slowmotion.value[-1]))
			else:
				self.setSeekState(self.makeStateForward(int(config.seek.enter_forward.value)))
		elif self.seekstate == self.SEEK_STATE_EOF:
			pass
		elif self.isStateForward(self.seekstate):
			speed = self.seekstate[1]
			if self.seekstate[2]:
				speed /= self.seekstate[2]
			speed = self.getHigher(speed, config.seek.speeds_forward.value) or config.seek.speeds_forward.value[-1]
			self.setSeekState(self.makeStateForward(speed))
		elif self.isStateBackward(self.seekstate):
			speed = -self.seekstate[1]
			if self.seekstate[2]:
				speed /= self.seekstate[2]
			speed = self.getLower(speed, config.seek.speeds_backward.value)
			if speed:
				self.setSeekState(self.makeStateBackward(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		elif self.isStateSlowMotion(self.seekstate):
			speed = self.getLower(self.seekstate[2], config.seek.speeds_slowmotion.value) or config.seek.speeds_slowmotion.value[0]
			self.setSeekState(self.makeStateSlowMotion(speed))

	def seekBack(self):
		seek = self.getSeek()
		if seek and not (seek.isCurrentlySeekable() & 2):
			if not self.fast_winding_hint_message_showed and (seek.isCurrentlySeekable() & 1):
				self.session.open(MessageBox, _("No fast winding possible yet.. but you can use the number buttons to skip forward/backward!"), MessageBox.TYPE_INFO, timeout=10)
				self.fast_winding_hint_message_showed = True
				return
			return 0 # trade as unhandled action
		seekstate = self.seekstate
		if seekstate == self.SEEK_STATE_PLAY:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
		elif seekstate == self.SEEK_STATE_EOF:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
			self.doSeekRelative(-6)
		elif seekstate == self.SEEK_STATE_PAUSE:
			self.doSeekRelative(-1)
		elif self.isStateForward(seekstate):
			speed = seekstate[1]
			if seekstate[2]:
				speed /= seekstate[2]
			speed = self.getLower(speed, config.seek.speeds_forward.value)
			if speed:
				self.setSeekState(self.makeStateForward(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		elif self.isStateBackward(seekstate):
			speed = -seekstate[1]
			if seekstate[2]:
				speed /= seekstate[2]
			speed = self.getHigher(speed, config.seek.speeds_backward.value) or config.seek.speeds_backward.value[-1]
			self.setSeekState(self.makeStateBackward(speed))
		elif self.isStateSlowMotion(seekstate):
			speed = self.getHigher(seekstate[2], config.seek.speeds_slowmotion.value)
			if speed:
				self.setSeekState(self.makeStateSlowMotion(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PAUSE)
		self.pts_lastseekspeed = self.seekstate[1]

	def seekFwdManual(self, fwd=True):
		if config.seek.baractivation.value == "leftright":
			self.session.open(Seekbar, fwd)
		else:
			self.session.openWithCallback(self.fwdSeekTo, MinuteInput)

	def seekBackManual(self, fwd=False):
		if config.seek.baractivation.value == "leftright":
			self.session.open(Seekbar, fwd)
		else:
			self.session.openWithCallback(self.rwdSeekTo, MinuteInput)

	def seekFwdSeekbar(self, fwd=True):
		if not config.seek.baractivation.value == "leftright":
			self.session.open(Seekbar, fwd)
		else:
			self.session.openWithCallback(self.fwdSeekTo, MinuteInput)

	def fwdSeekTo(self, minutes):
		self.doSeekRelative(minutes * 60 * 90000)

	def seekBackSeekbar(self, fwd=False):
		if not config.seek.baractivation.value == "leftright":
			self.session.open(Seekbar, fwd)
		else:
			self.session.openWithCallback(self.rwdSeekTo, MinuteInput)

	def rwdSeekTo(self, minutes):
# 		print "rwdSeekTo"
		self.doSeekRelative(-minutes * 60 * 90000)

	def checkSkipShowHideLock(self):
		if self.seekstate == self.SEEK_STATE_PLAY or self.seekstate == self.SEEK_STATE_EOF:
			self.lockedBecauseOfSkipping = False
 			self.unlockShow()
		else:
			wantlock = self.seekstate != self.SEEK_STATE_PLAY
			if config.usage.show_infobar_on_skip.value:
				if self.lockedBecauseOfSkipping and not wantlock:
					self.unlockShow()
					self.lockedBecauseOfSkipping = False

				if wantlock and not self.lockedBecauseOfSkipping:
					self.lockShow()
					self.lockedBecauseOfSkipping = True

	def calcRemainingTime(self):
		seekable = self.getSeek()
		if seekable is not None:
			len = seekable.getLength()
			try:
				tmp = self.cueGetEndCutPosition()
				if tmp:
					len = (False, tmp)
			except:
				pass
			pos = seekable.getPlayPosition()
			speednom = self.seekstate[1] or 1
			speedden = self.seekstate[2] or 1
			if not len[0] and not pos[0]:
				if len[1] <= pos[1]:
					return 0
				time = (len[1] - pos[1])*speedden/(90*speednom)
				return time
		return False

	def __evEOF(self):
		if self.seekstate == self.SEEK_STATE_EOF:
			return

		# if we are seeking forward, we try to end up ~1s before the end, and pause there.
		seekstate = self.seekstate
		if self.seekstate != self.SEEK_STATE_PAUSE:
			self.setSeekState(self.SEEK_STATE_EOF)

		if seekstate not in (self.SEEK_STATE_PLAY, self.SEEK_STATE_PAUSE): # if we are seeking
			seekable = self.getSeek()
			if seekable is not None:
				seekable.seekTo(-1)
				self.doEofInternal(True)
		if seekstate == self.SEEK_STATE_PLAY: # regular EOF
			self.doEofInternal(True)
		else:
			self.doEofInternal(False)

	def doEofInternal(self, playing):
		pass		# Defined in subclasses

	def __evSOF(self):
		self.setSeekState(self.SEEK_STATE_PLAY)
		self.doSeek(0)

from Screens.PVRState import PVRState, TimeshiftState, PTSTimeshiftState
class InfoBarPVRState:
	def __init__(self, screen=PVRState, force_show = False):
		self.onChangedEntry = [ ]
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.pvrStateDialog = self.session.instantiateDialog(screen)
		self.onShow.append(self._mayShow)
		self.onHide.append(self.pvrStateDialog.hide)
		self.force_show = force_show

	def createSummary(self):
		return InfoBarMoviePlayerSummary

	def _mayShow(self):
		if "MoviePlayer'>" in str(self) and not config.usage.movieplayer_pvrstate.value:
			self["state"].setText("")
			self["statusicon"].setPixmapNum(6)
			self["speed"].setText("")
		if self.execing and self.seekstate != self.SEEK_STATE_EOF and not config.usage.movieplayer_pvrstate.value:
			self.pvrStateDialog.show()

	def __playStateChanged(self, state):
		playstateString = state[3]
		state_summary = playstateString
		self.pvrStateDialog["state"].setText(playstateString)
		if playstateString == '>':
			self.pvrStateDialog["statusicon"].setPixmapNum(0)
			self.pvrStateDialog["speed"].setText("")
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 0
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(0)
				self["speed"].setText("")
		elif playstateString == '||':
			self.pvrStateDialog["statusicon"].setPixmapNum(1)
			self.pvrStateDialog["speed"].setText("")
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 1
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(1)
				self["speed"].setText("")
		elif playstateString == 'END':
			self.pvrStateDialog["statusicon"].setPixmapNum(2)
			self.pvrStateDialog["speed"].setText("")
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 2
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(2)
				self["speed"].setText("")
		elif playstateString.startswith('>>'):
			speed = state[3].split()
			self.pvrStateDialog["statusicon"].setPixmapNum(3)
			self.pvrStateDialog["speed"].setText(speed[1])
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 3
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(3)
				self["speed"].setText(speed[1])
		elif playstateString.startswith('<<'):
			speed = state[3].split()
			self.pvrStateDialog["statusicon"].setPixmapNum(4)
			self.pvrStateDialog["speed"].setText(speed[1])
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 4
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(4)
				self["speed"].setText(speed[1])
		elif playstateString.startswith('/'):
			self.pvrStateDialog["statusicon"].setPixmapNum(5)
			self.pvrStateDialog["speed"].setText(playstateString)
			speed_summary = self.pvrStateDialog["speed"].text
			statusicon_summary = 5
			if "MoviePlayer'>" in str(self) and config.usage.movieplayer_pvrstate.value:
 				self["state"].setText(playstateString)
				self["statusicon"].setPixmapNum(5)
				self["speed"].setText(playstateString)

		for cb in self.onChangedEntry:
			cb(state_summary, speed_summary, statusicon_summary)

		# if we return into "PLAY" state, ensure that the dialog gets hidden if there will be no infobar displayed
		if not config.usage.show_infobar_on_skip.value and self.seekstate == self.SEEK_STATE_PLAY and not self.force_show:
			self.pvrStateDialog.hide()
		else:
			self._mayShow()

class InfoBarTimeshiftState(InfoBarPVRState):
	def __init__(self):
		InfoBarPVRState.__init__(self, screen=TimeshiftState, force_show = True)
		self.onHide.append(self.__hideTimeshiftState)

	def _mayShow(self):
		if config.timeshift.enabled.value:
			self["TimeshiftActivateActions"].setEnabled(True)
			self["TimeshiftActions"].setEnabled(False)
		else:
			self["TimeshiftActivateActions"].setEnabled(False)
			self["TimeshiftActions"].setEnabled(True)
		if self.execing and self.timeshift_enabled and self.isSeekable():
			if config.timeshift.enabled.value:
				self["TimeshiftActivateActions"].setEnabled(False)
				self["TimeshiftActions"].setEnabled(True)
				self["SeekActions"].setEnabled(True)
				InfoBarTimeshift.ptsSeekPointerSetCurrentPos(self)
				self["SeekActions"].setEnabled(False)
				self["SeekActionsPTS"].setEnabled(True)
				if config.timeshift.showinfobar.value:
					self["TimeshiftSeekPointerActions"].setEnabled(True)
			else:
				self["SeekActions"].setEnabled(True)
			self.pvrStateDialog.show()

		elif self.execing and self.timeshift_enabled and not self.isSeekable():
			if config.timeshift.enabled.value:
				self["SeekActions"].setEnabled(False)
				self["SeekActionsPTS"].setEnabled(False)
				self["TimeshiftSeekPointerActions"].setEnabled(False)
			else:
				self["TimeshiftActivateActions"].setEnabled(True)
				self["SeekActions"].setEnabled(False)
			self.pvrStateDialog.hide()

	def __hideTimeshiftState(self):
		if config.timeshift.enabled.value:
			self["TimeshiftActivateActions"].setEnabled(True)
			self["TimeshiftActions"].setEnabled(False)
			self["SeekActionsPTS"].setEnabled(False)
			self["TimeshiftSeekPointerActions"].setEnabled(False)
			if self.timeshift_enabled and self.isSeekable():
				self["TimeshiftActivateActions"].setEnabled(False)
				self["TimeshiftActions"].setEnabled(True)
				self["SeekActions"].setEnabled(True)
			elif self.timeshift_enabled and not self.isSeekable():
				self["SeekActions"].setEnabled(False)
		else:
			self["TimeshiftActivateActions"].setEnabled(False)
			self["TimeshiftActions"].setEnabled(True)
			if self.timeshift_enabled and self.isSeekable():
				self["SeekActions"].setEnabled(True)
			elif self.timeshift_enabled and not self.isSeekable():
				self["TimeshiftActivateActions"].setEnabled(True)
				self["SeekActions"].setEnabled(False)
		self.pvrStateDialog.hide()

class InfoBarShowMovies:

	# i don't really like this class.
	# it calls a not further specified "movie list" on up/down/movieList,
	# so this is not more than an action map
	def __init__(self):
		self["MovieListActions"] = HelpableActionMap(self, "InfobarMovieListActions",
			{
				"movieList": (self.showMovies, _("movie list")),
				"up": (self.up, _("movie list")),
				"down": (self.down, _("movie list"))
			})

# InfoBarTimeshift requires InfoBarSeek, instantiated BEFORE!

# Hrmf.
#
# Timeshift works the following way:
#                                         demux0   demux1                    "TimeshiftActions" "TimeshiftActivateActions" "SeekActions"
# - normal playback                       TUNER    unused      PLAY               enable                disable              disable
# - user presses "yellow" button.         FILE     record      PAUSE              enable                disable              enable
# - user presess pause again              FILE     record      PLAY               enable                disable              enable
# - user fast forwards                    FILE     record      FF                 enable                disable              enable
# - end of timeshift buffer reached       TUNER    record      PLAY               enable                enable               disable
# - user backwards                        FILE     record      BACK  # !!         enable                disable              enable
#

# in other words:
# - when a service is playing, pressing the "timeshiftStart" button ("yellow") enables recording ("enables timeshift"),
# freezes the picture (to indicate timeshift), sets timeshiftMode ("activates timeshift")
# now, the service becomes seekable, so "SeekActions" are enabled, "TimeshiftEnableActions" are disabled.
# - the user can now PVR around
# - if it hits the end, the service goes into live mode ("deactivates timeshift", it's of course still "enabled")
# the service looses it's "seekable" state. It can still be paused, but just to activate timeshift right
# after!
# the seek actions will be disabled, but the timeshiftActivateActions will be enabled
# - if the user rewinds, or press pause, timeshift will be activated again

# note that a timeshift can be enabled ("recording") and
# activated (currently time-shifting).

class InfoBarTimeshift:
	def __init__(self):
		self["TimeshiftActions"] = HelpableActionMap(self, "InfobarTimeshiftActions",
			{
				"timeshiftStart": (self.startTimeshift, _("start timeshift")),  # the "yellow key"
				"timeshiftStop": (self.stopTimeshift, _("stop timeshift")),      # currently undefined :), probably 'TV'
				"instantRecord": self.instantRecord,
				"restartTimeshift": self.restartTimeshift
			}, prio=1)
		self["TimeshiftActivateActions"] = ActionMap(["InfobarTimeshiftActivateActions"],
			{
				"timeshiftActivateEnd": self.activateTimeshiftEnd, # something like "rewind key"
				"timeshiftActivateEndAndPause": self.activateTimeshiftEndAndPause  # something like "pause key"
			}, prio=-1) # priority over record

		self["TimeshiftSeekPointerActions"] = ActionMap(["InfobarTimeshiftSeekPointerActions"],
			{
				"SeekPointerOK": self.ptsSeekPointerOK,
				"SeekPointerLeft": self.ptsSeekPointerLeft,
				"SeekPointerRight": self.ptsSeekPointerRight
			},-2)
		self["TimeshiftActions"].setEnabled(False)
		self["TimeshiftActivateActions"].setEnabled(False)
		self["TimeshiftSeekPointerActions"].setEnabled(False)
		self.timeshift_enabled = 0
		self.timeshift_state = 0
		self.ts_rewind_timer = eTimer()
		self.ts_rewind_timer.callback.append(self.rewindService)

		self.__event_tracker = ServiceEventTracker(screen = self, eventmap =
			{
				iPlayableService.evStart: self.__evStart,
				iPlayableService.evEnd: self.__evEnd,
				iPlayableService.evSOF: self.__evSOF,
				iPlayableService.evUpdatedInfo: self.__evInfoChanged,
				iPlayableService.evUpdatedEventInfo: self.__evEventInfoChanged,
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
				iPlayableService.evUser+1: self.ptsTimeshiftFileChanged
			})

		self.pts_begintime = 0
		self.pts_pathchecked = False
		self.pts_pvrStateDialog = "TimeshiftState"
		self.pts_seektoprevfile = False
		self.pts_switchtolive = False
		self.pts_currplaying = 1
		self.pts_lastseekspeed = 0
		self.pts_service_changed = False
		self.pts_record_running = self.session.nav.RecordTimer.isRecording()
		self.save_current_timeshift = False
		self.save_timeshift_postaction = None
		self.save_timeshift_filename = None
		self.service_changed = 0

		# Init Global Variables
		self.session.ptsmainloopvalue = 0
		config.timeshift.isRecording.value = False

		# Init eBackgroundFileEraser
		self.BgFileEraser = eBackgroundFileEraser.getInstance()

		# Init PTS Delay-Timer
		self.pts_delay_timer = eTimer()
		self.pts_delay_timer.callback.append(self.activatePermanentTimeshift)

		# Init PTS LengthCheck-Timer
		self.pts_LengthCheck_timer = eTimer()
		self.pts_LengthCheck_timer.callback.append(self.ptsLengthCheck)

		# Init PTS MergeRecords-Timer
		self.pts_mergeRecords_timer = eTimer()
		self.pts_mergeRecords_timer.callback.append(self.ptsMergeRecords)

		# Init PTS Merge Cleanup-Timer
		self.pts_mergeCleanUp_timer = eTimer()
		self.pts_mergeCleanUp_timer.callback.append(self.ptsMergePostCleanUp)

		# Init PTS QuitMainloop-Timer
		self.pts_QuitMainloop_timer = eTimer()
		self.pts_QuitMainloop_timer.callback.append(self.ptsTryQuitMainloop)

		# Init PTS CleanUp-Timer
		self.pts_cleanUp_timer = eTimer()
		self.pts_cleanUp_timer.callback.append(self.ptsCleanTimeshiftFolder)
		self.pts_cleanUp_timer.start(30000, True)

		# Init PTS SeekBack-Timer
		self.pts_SeekBack_timer = eTimer()
		self.pts_SeekBack_timer.callback.append(self.ptsSeekBackTimer)

		# Init Block-Zap Timer
		self.pts_blockZap_timer = eTimer()

		# Record Event Tracker
		self.session.nav.RecordTimer.on_state_change.append(self.ptsTimerEntryStateChange)

		# Keep Current Event Info for recordings
		self.pts_eventcount = 1
		self.pts_curevent_begin = int(time())
		self.pts_curevent_end = 0
		self.pts_curevent_name = _("Timeshift")
		self.pts_curevent_description = ""
		self.pts_curevent_servicerefname = ""
		self.pts_curevent_station = ""
		self.pts_curevent_eventid = None

		# Init PTS Infobar
		self.pts_seekpointer_MinX = 8
		self.pts_seekpointer_MaxX = 396 # make sure you can divide this through 2

	def __evStart(self):
		self.service_changed = 1
		self.pts_delay_timer.stop()
		self.pts_service_changed = True

	def __evEnd(self):
		self.service_changed = 0
		if not config.timeshift.isRecording.value:
			self.timeshift_enabled = 0
			self.__seekableStatusChanged()

	def __evSOF(self):
		if not config.timeshift.enabled.value or not self.timeshift_enabled:
			return

		if self.pts_currplaying == 1:
			preptsfile = config.timeshift.maxevents.value
		else:
			preptsfile = self.pts_currplaying-1

		# Switch to previous TS file by seeking forward to next one
		if Directories.fileExists("%spts_livebuffer.%s" % (config.usage.timeshift_path.value, preptsfile), 'r') and preptsfile != self.pts_eventcount:
			self.pts_seektoprevfile = True
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (preptsfile))

			self.setSeekState(self.SEEK_STATE_PAUSE)
			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)
			self.doSeek(-1)
			self.seekFwd()

	def __evInfoChanged(self):
		if self.service_changed:
			self.service_changed = 0

			# We zapped away before saving the file, save it now!
			if self.save_current_timeshift:
				self.SaveTimeshift("pts_livebuffer.%s" % (self.pts_eventcount))

			# Delete Timeshift Records on zap
			self.pts_eventcount = 0
			self.pts_cleanUp_timer.start(3000, True)

	def __evEventInfoChanged(self):
		if not config.timeshift.enabled.value:
			return

		# Get Current Event Info
		service = self.session.nav.getCurrentService()
		old_begin_time = self.pts_begintime
		info = service and service.info()
		ptr = info and info.getEvent(0)
		self.pts_begintime = ptr and ptr.getBeginTime() or 0

		# Save current TimeShift permanently now ...
		if info.getInfo(iServiceInformation.sVideoPID) != -1:

			# Take care of Record Margin Time ...
			if self.save_current_timeshift and self.timeshift_enabled:
				if config.recording.margin_after.value > 0 and len(self.recording) == 0:
					self.SaveTimeshift(mergelater=True)
					recording = RecordTimerEntry(ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()), time(), time()+(config.recording.margin_after.value*60), self.pts_curevent_name, self.pts_curevent_description, self.pts_curevent_eventid, dirname = config.usage.default_path.value)
					recording.dontSave = True
					self.session.nav.RecordTimer.record(recording)
					self.recording.append(recording)
				else:
					self.SaveTimeshift()

			# Restarting active timers after zap ...
			if self.pts_delay_timer.isActive() and not self.timeshift_enabled:
				self.pts_delay_timer.start(config.timeshift.startdelay.value*1000, True)
			if self.pts_cleanUp_timer.isActive() and not self.timeshift_enabled:
				self.pts_cleanUp_timer.start(3000, True)

			# (Re)Start TimeShift
			if not self.pts_delay_timer.isActive():
				if not self.timeshift_enabled or old_begin_time != self.pts_begintime or old_begin_time == 0:
					if self.pts_service_changed:
						self.pts_service_changed = False
						self.pts_delay_timer.start(config.timeshift.startdelay.value*1000, True)
					else:
						self.pts_delay_timer.start(1000, True)

	def __seekableStatusChanged(self):
		self["SeekActionsPTS"].setEnabled(False)
		self["TimeshiftSeekPointerActions"].setEnabled(False)
		if config.timeshift.enabled.value:
			self["TimeshiftActivateActions"].setEnabled(True)
			self["TimeshiftActions"].setEnabled(False)
			if self.timeshift_enabled and self.isSeekable():
				self["TimeshiftActivateActions"].setEnabled(False)
				self["TimeshiftActions"].setEnabled(True)
				self["SeekActions"].setEnabled(True)
			elif self.timeshift_enabled and not self.isSeekable():
				self["SeekActions"].setEnabled(False)
		else:
			self["TimeshiftActivateActions"].setEnabled(False)
			self["TimeshiftActions"].setEnabled(True)
			if self.timeshift_enabled and self.isSeekable():
				self["SeekActions"].setEnabled(True)
			elif self.timeshift_enabled and not self.isSeekable():
				self["TimeshiftActivateActions"].setEnabled(True)
				self["SeekActions"].setEnabled(False)

		# Reset Seek Pointer And Eventname in InfoBar
		if config.timeshift.enabled.value and self.timeshift_enabled and not self.isSeekable():
			if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState":
				self.pvrStateDialog["eventname"].setText("")
			self.ptsSeekPointerReset()

		# setNextPlaybackFile() when switching back to live tv
		if config.timeshift.enabled.value and self.timeshift_enabled and not self.isSeekable():
			if self.pts_starttime <= (time()-5):
				self.pts_blockZap_timer.start(3000, True)
			self.pts_currplaying = self.pts_eventcount
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (self.pts_eventcount))

	def eraseTimeshiftFile(self):
		for filename in os_listdir(config.usage.timeshift_path.value):
			if filename.startswith("timeshift.") and not filename.endswith(".del") and not filename.endswith(".copy"):
				self.BgFileEraser.erase("%s%s" % (config.usage.timeshift_path.value,filename))

	def activatePermanentTimeshift(self):
		if self.ptsCheckTimeshiftPath() is False or self.session.screen["Standby"].boolean is True or self.ptsLiveTVStatus() is False or (config.timeshift.stopwhilerecording.value and self.pts_record_running):
			return

		# Replace PVR Timeshift State Icon
		if self.pts_pvrStateDialog != "Screens.PVRState.PTSTimeshiftState":
			self.pts_pvrStateDialog = "Screens.PVRState.PTSTimeshiftState"
			self.pvrStateDialog = self.session.instantiateDialog(Screens.PVRState.PTSTimeshiftState)

		# Set next-file on event change only when watching latest timeshift ...
		if self.isSeekable() and self.pts_eventcount == self.pts_currplaying:
			pts_setnextfile = True
		else:
			pts_setnextfile = False

		# Update internal Event Counter
		if self.pts_eventcount >= config.timeshift.maxevents.value:
			self.pts_eventcount = 0

		self.pts_eventcount += 1

		# Do not switch back to LiveTV while timeshifting
		if self.isSeekable():
			switchToLive = False
		else:
			switchToLive = True

		# setNextPlaybackFile() on event change while timeshifting
		if self.pts_eventcount > 1 and self.isSeekable() and pts_setnextfile:
			self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (self.pts_eventcount))

		# (Re)start Timeshift now
		self.stopTimeshiftConfirmed(True, switchToLive)
		ts = self.getTimeshift()
		if ts and not ts.startTimeshift():
			if (config.misc.boxtype.value == 'vuuno' or config.misc.boxtype.value == 'vuduo') and os_path.exists("/proc/stb/lcd/symbol_timeshift"):
				if self.session.nav.RecordTimer.isRecording():
					open("/proc/stb/lcd/symbol_timeshift", "w").write("0")
			self.pts_starttime = time()
			self.pts_LengthCheck_timer.start(120000)
			self.timeshift_enabled = 1
			self.save_timeshift_postaction = None
			self.ptsGetEventInfo()
			self.ptsCreateHardlink()
			self.__seekableStatusChanged()
		else:
			self.session.open(MessageBox, _("Timeshift not possible!"), MessageBox.TYPE_ERROR)
			self.pts_eventcount = 0

	def startTimeshift(self):
		if config.timeshift.enabled.value:
			self.pts_delay_timer.stop()
			self.activatePermanentTimeshift()
			self.activateTimeshiftEndAndPause()
		else:
# 			print "enable timeshift"
			ts = self.getTimeshift()
			if ts is None:
				self.session.open(MessageBox, _("Timeshift not possible!"), MessageBox.TYPE_ERROR)
# 				print "no ts interface"
				return 0

			if self.timeshift_enabled:
				print "hu, timeshift already enabled?"
			else:
				if not ts.startTimeshift():
					self.timeshift_enabled = 1

					# we remove the "relative time" for now.
					#self.pvrStateDialog["timeshift"].setRelative(time.time())

					# PAUSE.
					#self.setSeekState(self.SEEK_STATE_PAUSE)
					self.activateTimeshiftEnd(False)

					# enable the "TimeshiftEnableActions", which will override
					# the startTimeshift actions
					self.__seekableStatusChanged()
				else:
					print "timeshift failed"

	def stopTimeshift(self):
		if not self.timeshift_enabled:
			return 0

		# Jump Back to Live TV
		if config.timeshift.enabled.value and self.timeshift_enabled:
			if self.isSeekable():
				self.pts_switchtolive = True
				self.ptsSetNextPlaybackFile("")
				self.setSeekState(self.SEEK_STATE_PAUSE)
				if self.seekstate != self.SEEK_STATE_PLAY:
					self.setSeekState(self.SEEK_STATE_PLAY)
				self.doSeek(-1) # seek 1 gop before end
				self.seekFwd() # seekFwd to switch to live TV
				return 1
			return 0

		if not self.timeshift_enabled:
			return 0
# 		print "disable timeshift"
		ts = self.getTimeshift()
		if ts is None:
			return 0
		self.session.openWithCallback(self.stopTimeshiftConfirmed, MessageBox, _("Stop Timeshift?"), MessageBox.TYPE_YESNO)

	def stopTimeshiftConfirmed(self, confirmed, switchToLive=True):
		was_enabled = self.timeshift_enabled

		if not confirmed:
			return
		ts = self.getTimeshift()
		if ts is None:
			return

		# Get rid of old timeshift file before E2 truncates its filesize
		self.eraseTimeshiftFile()

		# Stop Timeshift now
		try:
			ts.stopTimeshift(switchToLive)
		except:
			ts.stopTimeshift()

		self.timeshift_enabled = 0
		self.__seekableStatusChanged()

		if was_enabled and not self.timeshift_enabled:
			self.timeshift_enabled = 0
			self.pts_LengthCheck_timer.stop()

	def restartTimeshift(self):
		self.activatePermanentTimeshift()
		Notifications.AddNotification(MessageBox, _("[TimeShift] Restarting Timeshift!"), MessageBox.TYPE_INFO, timeout=5)

	def saveTimeshiftPopup(self):
		self.session.openWithCallback(self.saveTimeshiftPopupCallback, ChoiceBox, \
			title=_("The Timeshift record was not saved yet!\nWhat do you want to do now with the timeshift file?"), \
			list=((_("Save Timeshift as Movie and stop recording"), "savetimeshift"), \
			(_("Save Timeshift as Movie and continue recording"), "savetimeshiftandrecord"), \
			(_("Don't save Timeshift as Movie"), "noSave")))

	def saveTimeshiftPopupCallback(self, answer):
		if answer is None:
			return

		if answer[1] == "savetimeshift":
			self.saveTimeshiftActions("savetimeshift", self.save_timeshift_postaction)
		elif answer[1] == "savetimeshiftandrecord":
			self.saveTimeshiftActions("savetimeshiftandrecord", self.save_timeshift_postaction)
		elif answer[1] == "noSave":
			self.save_current_timeshift = False
			self.saveTimeshiftActions("noSave", self.save_timeshift_postaction)

	def saveTimeshiftEventPopup(self):
		filecount = 0
		entrylist = []
		entrylist.append((_("Current Event:")+" %s" % (self.pts_curevent_name), "savetimeshift"))

		filelist = os_listdir(config.usage.timeshift_path.value)

		if filelist is not None:
			filelist.sort()

		for filename in filelist:
			if (filename.startswith("pts_livebuffer.") is True) and (filename.endswith(".del") is False and filename.endswith(".meta") is False and filename.endswith(".eit") is False and filename.endswith(".copy") is False):
				statinfo = os_stat("%s%s" % (config.usage.timeshift_path.value,filename))
				if statinfo.st_mtime < (time()-5.0):
					# Get Event Info from meta file
					readmetafile = open("%s%s.meta" % (config.usage.timeshift_path.value,filename), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					description = readmetafile.readline()[0:-1]
					begintime = readmetafile.readline()[0:-1]
					readmetafile.close()

					# Add Event to list
					filecount += 1
					entrylist.append((_("Record") + " #%s (%s): %s" % (filecount,strftime("%H:%M",localtime(int(begintime))),eventname), "%s" % filename))

		self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, title=_("Which event do you want to save permanently?"), list=entrylist)

	def saveTimeshiftActions(self, action=None, postaction=None):
		self.save_timeshift_postaction = postaction

		if action is None:
			if config.timeshift.favoriteSaveAction.value == "askuser":
				self.saveTimeshiftPopup()
				return
			elif config.timeshift.favoriteSaveAction.value == "savetimeshift":
				self.SaveTimeshift()
			elif config.timeshift.favoriteSaveAction.value == "savetimeshiftandrecord":
				if self.pts_curevent_end > time():
					self.SaveTimeshift(mergelater=True)
					self.ptsRecordCurrentEvent()
				else:
					self.SaveTimeshift()
			elif config.timeshift.favoriteSaveAction.value == "noSave":
				config.timeshift.isRecording.value = False
				self.save_current_timeshift = False
		elif action == "savetimeshift":
			self.SaveTimeshift()
		elif action == "savetimeshiftandrecord":
			if self.pts_curevent_end > time():
				self.SaveTimeshift(mergelater=True)
				self.ptsRecordCurrentEvent()
			else:
				self.SaveTimeshift()
		elif action == "noSave":
			config.timeshift.isRecording.value = False
			self.save_current_timeshift = False

		# Get rid of old timeshift file before E2 truncates its filesize
		if self.save_timeshift_postaction is not None:
			self.eraseTimeshiftFile()

		# Post PTS Actions like ZAP or whatever the user requested
		if self.save_timeshift_postaction == "zapUp":
			InfoBarChannelSelection.zapUp(self)
		elif self.save_timeshift_postaction == "zapDown":
			InfoBarChannelSelection.zapDown(self)
		elif self.save_timeshift_postaction == "historyBack":
			InfoBarChannelSelection.historyBack(self)
		elif self.save_timeshift_postaction == "historyNext":
			InfoBarChannelSelection.historyNext(self)
		elif self.save_timeshift_postaction == "switchChannelUp":
			InfoBarChannelSelection.switchChannelUp(self)
		elif self.save_timeshift_postaction == "switchChannelDown":
			InfoBarChannelSelection.switchChannelDown(self)
		elif self.save_timeshift_postaction == "openServiceList":
			InfoBarChannelSelection.openServiceList(self)
		elif self.save_timeshift_postaction == "showRadioChannelList":
			InfoBarChannelSelection.showRadioChannelList(self, zap=True)
		elif self.save_timeshift_postaction == "standby":
			Notifications.AddNotification(Screens.Standby.Standby2)

	def SaveTimeshift(self, timeshiftfile=None, mergelater=False):
		self.save_current_timeshift = False
		savefilename = None
		if timeshiftfile is not None:
			savefilename = timeshiftfile

		if savefilename is None:
			for filename in os_listdir(config.usage.timeshift_path.value):
				if filename.startswith("timeshift.") and not filename.endswith(".del") and not filename.endswith(".copy"):
					try:
						statinfo = os_stat("%s%s" % (config.usage.timeshift_path.value,filename))
						if statinfo.st_mtime > (time()-5.0):
							savefilename=filename
					except Exception, errormsg:
						Notifications.AddNotification(MessageBox, _("PTS Plugin Error: %s" % (errormsg)), MessageBox.TYPE_ERROR)

		if savefilename is None:
			Notifications.AddNotification(MessageBox, _("No Timeshift found to save as recording!"), MessageBox.TYPE_ERROR)
		else:
			timeshift_saved = True
			timeshift_saveerror1 = ""
			timeshift_saveerror2 = ""
			metamergestring = ""

			config.timeshift.isRecording.value = True

			if mergelater:
				self.pts_mergeRecords_timer.start(120000, True)
				metamergestring = "pts_merge\n"

			try:
				if timeshiftfile is None:
					# Save Current Event by creating hardlink to ts file
					if self.pts_starttime >= (time()-60):
						self.pts_starttime -= 60

					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name)
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "long" and self.pts_curevent_name != pts_curevent_description:
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name,self.pts_curevent_description)
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d",localtime(self.pts_starttime)),self.pts_curevent_name)
					except Exception, errormsg:
						print "[TimeShift] Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					fullname = Directories.getRecordingFilename(ptsfilename,config.usage.default_path.value)
					os_link("%s%s" % (config.usage.timeshift_path.value,savefilename), "%s.ts" % (fullname))
					metafile = open("%s.ts.meta" % (fullname), "w")
					metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime),metamergestring))
					metafile.close()
					self.ptsCreateEITFile(fullname)
				elif timeshiftfile.startswith("pts_livebuffer"):
					# Save stored timeshift by creating hardlink to ts file
					readmetafile = open("%s%s.meta" % (config.usage.timeshift_path.value,timeshiftfile), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					description = readmetafile.readline()[0:-1]
					begintime = readmetafile.readline()[0:-1]
					readmetafile.close()

					ptsfilename = "%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(int(begintime))),self.pts_curevent_station,eventname)
					try:
						if config.usage.setup_level.index >= 2:
							if config.recording.filename_composition.value == "long" and eventname != description:
								ptsfilename = "%s - %s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(int(begintime))),self.pts_curevent_station,eventname,description)
							elif config.recording.filename_composition.value == "short":
								ptsfilename = "%s - %s" % (strftime("%Y%m%d",localtime(int(begintime))),eventname)
					except Exception, errormsg:
						print "[TimeShift] Using default filename"

					if config.recording.ascii_filenames.value:
						ptsfilename = ASCIItranslit.legacyEncode(ptsfilename)

					fullname=Directories.getRecordingFilename(ptsfilename,config.usage.default_path.value)
					os_link("%s%s" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts" % (fullname))
					os_link("%s%s.meta" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts.meta" % (fullname))
					if os_path.exists("%s%s.eit" % (config.usage.timeshift_path.value,timeshiftfile)):
						os_link("%s%s.eit" % (config.usage.timeshift_path.value,timeshiftfile),"%s.eit" % (fullname))

					# Add merge-tag to metafile
					if mergelater:
						metafile = open("%s.ts.meta" % (fullname), "a")
						metafile.write("%s\n" % (metamergestring))
						metafile.close()

				# Create AP and SC Files when not merging
				if not mergelater:
					self.ptsCreateAPSCFiles(fullname+".ts")

			except Exception, errormsg:
				timeshift_saved = False
				timeshift_saveerror1 = errormsg

			# Hmpppf! Saving Timeshift via Hardlink-Method failed. Probably other device?
			# Let's try to copy the file in background now! This might take a while ...
			if not timeshift_saved:
				try:
					stat = statvfs(config.usage.default_path.value)
					freespace = stat.f_bfree / 1000 * stat.f_bsize / 1000
					randomint = randint(1, 999)

					if timeshiftfile is None:
						# Get Filesize for Free Space Check
						filesize = int(os_path.getsize("%s%s" % (config.usage.timeshift_path.value,savefilename)) / (1024*1024))

						# Save Current Event by copying it to the other device
						if filesize <= freespace:
							os_link("%s%s" % (config.usage.timeshift_path.value,savefilename), "%s%s.%s.copy" % (config.usage.timeshift_path.value,savefilename,randomint))
							copy_file = savefilename
							metafile = open("%s.ts.meta" % (fullname), "w")
							metafile.write("%s\n%s\n%s\n%i\n%s" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime),metamergestring))
							metafile.close()
							self.ptsCreateEITFile(fullname)
					elif timeshiftfile.startswith("pts_livebuffer"):
						# Get Filesize for Free Space Check
						filesize = int(os_path.getsize("%s%s" % (config.usage.timeshift_path.value, timeshiftfile)) / (1024*1024))

						# Save stored timeshift by copying it to the other device
						if filesize <= freespace:
							os_link("%s%s" % (config.usage.timeshift_path.value,timeshiftfile), "%s%s.%s.copy" % (config.usage.timeshift_path.value,timeshiftfile,randomint))
							Directories.copyfile("%s%s.meta" % (config.usage.timeshift_path.value,timeshiftfile),"%s.ts.meta" % (fullname))
							if os_path.exists("%s%s.eit" % (config.usage.timeshift_path.value,timeshiftfile)):
								Directories.copyfile("%s%s.eit" % (config.usage.timeshift_path.value,timeshiftfile),"%s.eit" % (fullname))
							copy_file = timeshiftfile

						# Add merge-tag to metafile
						if mergelater:
							metafile = open("%s.ts.meta" % (fullname), "a")
							metafile.write("%s\n" % (metamergestring))
							metafile.close()

					# Only copy file when enough disk-space available!
					if filesize <= freespace:
						timeshift_saved = True
						copy_file = copy_file+"."+str(randomint)

						# Get Event Info from meta file
						if os_path.exists("%s.ts.meta" % (fullname)):
							readmetafile = open("%s.ts.meta" % (fullname), "r")
							servicerefname = readmetafile.readline()[0:-1]
							eventname = readmetafile.readline()[0:-1]
						else:
							eventname = "";

						JobManager.AddJob(CopyTimeshiftJob(self, "mv \"%s%s.copy\" \"%s.ts\"" % (config.usage.timeshift_path.value,copy_file,fullname), copy_file, fullname, eventname))
						if not Screens.Standby.inTryQuitMainloop and not Screens.Standby.inStandby and not mergelater and self.save_timeshift_postaction != "standby":
							Notifications.AddNotification(MessageBox, _("Saving timeshift as movie now. This might take a while!"), MessageBox.TYPE_INFO, timeout=5)
					else:
						timeshift_saved = False
						timeshift_saveerror1 = ""
						timeshift_saveerror2 = _("Not enough free Diskspace!\n\nFilesize: %sMB\nFree Space: %sMB\nPath: %s" % (filesize,freespace,config.usage.default_path.value))

				except Exception, errormsg:
					timeshift_saved = False
					timeshift_saveerror2 = errormsg

			if not timeshift_saved:
				config.timeshift.isRecording.value = False
				self.save_timeshift_postaction = None
				errormessage = str(timeshift_saveerror1) + "\n" + str(timeshift_saveerror2)
				Notifications.AddNotification(MessageBox, _("Timeshift save failed!")+"\n\n%s" % errormessage, MessageBox.TYPE_ERROR)

	def ptsCleanTimeshiftFolder(self):
		if not config.timeshift.enabled.value or self.ptsCheckTimeshiftPath() is False or self.session.screen["Standby"].boolean is True:
			return

		try:
			for filename in os_listdir(config.usage.timeshift_path.value):
				if (filename.startswith("timeshift.") or filename.startswith("pts_livebuffer.")) and (filename.endswith(".del") is False and filename.endswith(".copy") is False and filename.endswith(".meta") is False and filename.endswith(".eit") is False):

					statinfo = os_stat("%s%s" % (config.usage.timeshift_path.value,filename))
					# if no write for 5 sec = stranded timeshift
					if statinfo.st_mtime < (time()-5.0):
						print "[TimeShift] Erasing stranded timeshift %s" % filename
						self.BgFileEraser.erase("%s%s" % (config.usage.timeshift_path.value,filename))

						# Delete Meta and EIT File too
						if filename.startswith("pts_livebuffer.") is True:
							os_remove("%s%s.meta" % (config.usage.timeshift_path.value,filename))
							os_remove("%s%s.eit" % (config.usage.timeshift_path.value,filename))
		except:
			print "PTS: IO-Error while cleaning Timeshift Folder ..."

	def ptsGetEventInfo(self):
		event = None
		try:
			serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
			serviceHandler = eServiceCenter.getInstance()
			info = serviceHandler.info(serviceref)

			self.pts_curevent_servicerefname = serviceref.toString()
			self.pts_curevent_station = info.getName(serviceref)

			service = self.session.nav.getCurrentService()
			info = service and service.info()
			event = info and info.getEvent(0)
		except Exception, errormsg:
			Notifications.AddNotification(MessageBox, _("Getting Event Info failed!")+"\n\n%s" % errormsg, MessageBox.TYPE_ERROR, timeout=10)

		if event is not None:
			curEvent = parseEvent(event)
			self.pts_curevent_begin = int(curEvent[0])
			self.pts_curevent_end = int(curEvent[1])
			self.pts_curevent_name = curEvent[2]
			self.pts_curevent_description = curEvent[3]
			self.pts_curevent_eventid = curEvent[4]

	def ptsFrontpanelActions(self, action=None):
		if self.session.nav.RecordTimer.isRecording() or SystemInfo.get("NumFrontpanelLEDs", 0) == 0:
			return

		try:
			if action == "start":
				if os_path.exists("/proc/stb/fp/led_set_pattern"):
					open("/proc/stb/fp/led_set_pattern", "w").write("0xa7fccf7a")
				elif os_path.exists("/proc/stb/fp/led0_pattern"):
					open("/proc/stb/fp/led0_pattern", "w").write("0x55555555")
				if os_path.exists("/proc/stb/fp/led_pattern_speed"):
					open("/proc/stb/fp/led_pattern_speed", "w").write("20")
				elif os_path.exists("/proc/stb/fp/led_set_speed"):
					open("/proc/stb/fp/led_set_speed", "w").write("20")
			elif action == "stop":
				if os_path.exists("/proc/stb/fp/led_set_pattern"):
					open("/proc/stb/fp/led_set_pattern", "w").write("0")
				elif os_path.exists("/proc/stb/fp/led0_pattern"):
					open("/proc/stb/fp/led0_pattern", "w").write("0")
		except Exception, errormsg:
			print "[Timeshift] %s" % (errormsg)

	def ptsCreateHardlink(self):
		timeshiftlist = []
		for filename in os_listdir(config.usage.timeshift_path.value):
			if filename.startswith("timeshift.") and not filename.endswith(".del") and not filename.endswith(".copy"):
				try:
					statinfo = os_stat("%s%s" % (config.usage.timeshift_path.value,filename))
					if statinfo.st_size < 10:
						try:
							if os_path.exists("%spts_livebuffer.%s.eit" % (config.usage.timeshift_path.value,self.pts_eventcount)):
								self.BgFileEraser.erase("%spts_livebuffer.%s.eit" % (config.usage.timeshift_path.value,self.pts_eventcount))
							if os_path.exists("%spts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_eventcount)):
								self.BgFileEraser.erase("%spts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_eventcount))
							if os_path.exists("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount)):
								self.BgFileEraser.erase("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))
						except Exception, errormsg:
							Notifications.AddNotification(MessageBox, _("Failed to remove old files.")+"\n\n%s" % errormsg, MessageBox.TYPE_ERROR)
							print "[Timeshift] %s" % (errormsg)

						try:
							# Create link to pts_livebuffer file
							os_link("%s%s" % (config.usage.timeshift_path.value,filename), "%spts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))

							# Create a Meta File
							metafile = open("%spts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_eventcount), "w")
							metafile.write("%s\n%s\n%s\n%i\n" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime)))
							metafile.close()
						except Exception, errormsg:
							Notifications.AddNotification(MessageBox, _("Creating Hardlink to Timeshift file failed!")+"\n"+_("The Filesystem on your Timeshift-Device does not support hardlinks.\nMake sure it is formatted in EXT2 or EXT3!")+"\n\n%s" % errormsg, MessageBox.TYPE_ERROR)

						# Create EIT File
						self.ptsCreateEITFile("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_eventcount))

						# Permanent Recording Hack
						if config.timeshift.permanentrecording.value:
							try:
								fullname = Directories.getRecordingFilename("%s - %s - %s" % (strftime("%Y%m%d %H%M",localtime(self.pts_starttime)),self.pts_curevent_station,self.pts_curevent_name),config.usage.default_path.value)
								os_link("%s%s" % (config.usage.timeshift_path.value,filename), "%s.ts" % (fullname))
								# Create a Meta File
								metafile = open("%s.ts.meta" % (fullname), "w")
								metafile.write("%s\n%s\n%s\n%i\nautosaved\n" % (self.pts_curevent_servicerefname,self.pts_curevent_name.replace("\n", ""),self.pts_curevent_description.replace("\n", ""),int(self.pts_starttime)))
								metafile.close()
							except Exception, errormsg:
								print "[Timeshift] %s" % (errormsg)
				except Exception, errormsg:
					errormsg = str(errormsg)
					if errormsg.find('Input/output error') != -1:
						errormsg += _("\nAn Input/output error usually indicates a corrupted filesystem! Please check the filesystem of your timeshift-device!")
					Notifications.AddNotification(MessageBox, _("Creating Hardlink to Timeshift file failed!")+"\n%s" % (errormsg), MessageBox.TYPE_ERROR)

	def ptsRecordCurrentEvent(self):
			recording = RecordTimerEntry(ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()), time(), self.pts_curevent_end, self.pts_curevent_name, self.pts_curevent_description, self.pts_curevent_eventid, dirname = config.usage.default_path.value)
			recording.dontSave = True
			self.session.nav.RecordTimer.record(recording)
			self.recording.append(recording)

	def ptsMergeRecords(self):
		if self.session.nav.RecordTimer.isRecording():
			self.pts_mergeRecords_timer.start(120000, True)
			return

		ptsmergeSRC = ""
		ptsmergeDEST = ""
		ptsmergeeventname = ""
		ptsgetnextfile = False
		ptsfilemerged = False

		filelist = os_listdir(config.usage.default_path.value)

		if filelist is not None:
			filelist.sort()

		for filename in filelist:
			if filename.endswith(".meta"):
				# Get Event Info from meta file
				readmetafile = open("%s%s" % (config.usage.default_path.value,filename), "r")
				servicerefname = readmetafile.readline()[0:-1]
				eventname = readmetafile.readline()[0:-1]
				eventtitle = readmetafile.readline()[0:-1]
				eventtime = readmetafile.readline()[0:-1]
				eventtag = readmetafile.readline()[0:-1]
				readmetafile.close()

				if ptsgetnextfile:
					ptsgetnextfile = False
					ptsmergeSRC = filename[0:-5]

					if ASCIItranslit.legacyEncode(eventname) == ASCIItranslit.legacyEncode(ptsmergeeventname):
						# Copy EIT File
						if Directories.fileExists("%s%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3])):
							Directories.copyfile("%s%s.eit" % (config.usage.default_path.value, ptsmergeSRC[0:-3]),"%s%s.eit" % (config.usage.default_path.value, ptsmergeDEST[0:-3]))

						# Delete AP and SC Files
						if os_path.exists("%s%s.ap" % (config.usage.default_path.value, ptsmergeDEST)):
							self.BgFileEraser.erase("%s%s.ap" % (config.usage.default_path.value, ptsmergeDEST))
						if os_path.exists("%s%s.sc" % (config.usage.default_path.value, ptsmergeDEST)):
							self.BgFileEraser.erase("%s%s.sc" % (config.usage.default_path.value, ptsmergeDEST))

						# Add Merge Job to JobManager
						JobManager.AddJob(MergeTimeshiftJob(self, "cat \"%s%s\" >> \"%s%s\"" % (config.usage.default_path.value,ptsmergeSRC,config.usage.default_path.value,ptsmergeDEST), ptsmergeSRC, ptsmergeDEST, eventname))
						config.timeshift.isRecording.value = True
						ptsfilemerged = True
					else:
						ptsgetnextfile = True

				if eventtag == "pts_merge" and not ptsgetnextfile:
					ptsgetnextfile = True
					ptsmergeDEST = filename[0:-5]
					ptsmergeeventname = eventname
					ptsfilemerged = False

					# If still recording or transfering, try again later ...
					if Directories.fileExists("%s%s" % (config.usage.default_path.value,ptsmergeDEST)):
						statinfo = os_stat("%s%s" % (config.usage.default_path.value,ptsmergeDEST))
						if statinfo.st_mtime > (time()-10.0):
							self.pts_mergeRecords_timer.start(120000, True)
							return

					# Rewrite Meta File to get rid of pts_merge tag
					metafile = open("%s%s.meta" % (config.usage.default_path.value,ptsmergeDEST), "w")
					metafile.write("%s\n%s\n%s\n%i\n" % (servicerefname,eventname.replace("\n", ""),eventtitle.replace("\n", ""),int(eventtime)))
					metafile.close()

		# Merging failed :(
		if not ptsfilemerged and ptsgetnextfile:
			Notifications.AddNotification(MessageBox,_("[Timeshift] Merging records failed!"), MessageBox.TYPE_ERROR)

	def ptsCreateAPSCFiles(self, filename):
		if Directories.fileExists(filename, 'r'):
			if Directories.fileExists(filename+".meta", 'r'):
				# Get Event Info from meta file
				readmetafile = open(filename+".meta", "r")
				servicerefname = readmetafile.readline()[0:-1]
				eventname = readmetafile.readline()[0:-1]
			else:
				eventname = ""
			JobManager.AddJob(CreateAPSCFilesJob(self, "/usr/lib/enigma2/python/Components/createapscfiles \"%s\"" % (filename), eventname))
		else:
			self.ptsSaveTimeshiftFinished()

	def ptsCreateEITFile(self, filename):
		if self.pts_curevent_eventid is not None:
			try:
				import Components.eitsave
				serviceref = ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference()).ref.toString()
				Components.eitsave.SaveEIT(serviceref, filename+".eit", self.pts_curevent_eventid, -1, -1)
			except Exception, errormsg:
				print "[Timeshift] %s" % (errormsg)

	def ptsCopyFilefinished(self, srcfile, destfile):
		# Erase Source File
		if Directories.fileExists(srcfile):
			self.BgFileEraser.erase(srcfile)

		# Restart Merge Timer
		if self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)
		else:
			# Create AP and SC Files
			self.ptsCreateAPSCFiles(destfile)

	def ptsMergeFilefinished(self, srcfile, destfile):
		if self.session.nav.RecordTimer.isRecording() or len(JobManager.getPendingJobs()) >= 1:
			# Rename files and delete them later ...
			self.pts_mergeCleanUp_timer.start(120000, True)
			os_system("echo \"\" > \"%s.pts.del\"" % (srcfile[0:-3]))
		else:
			# Delete Instant Record permanently now ... R.I.P.
			self.BgFileEraser.erase("%s" % (srcfile))
			self.BgFileEraser.erase("%s.ap" % (srcfile))
			self.BgFileEraser.erase("%s.sc" % (srcfile))
			self.BgFileEraser.erase("%s.meta" % (srcfile))
			self.BgFileEraser.erase("%s.cuts" % (srcfile))
			self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))

		# Create AP and SC Files
		self.ptsCreateAPSCFiles(destfile)

		# Run Merge-Process one more time to check if there are more records to merge
		self.pts_mergeRecords_timer.start(10000, True)

	def ptsSaveTimeshiftFinished(self):
		if not self.pts_mergeCleanUp_timer.isActive():
			self.ptsFrontpanelActions("stop")
			config.timeshift.isRecording.value = False

		if Screens.Standby.inTryQuitMainloop:
			self.pts_QuitMainloop_timer.start(30000, True)
		else:
			Notifications.AddNotification(MessageBox, _("Timeshift saved to your harddisk!"), MessageBox.TYPE_INFO, timeout = 5)

	def ptsMergePostCleanUp(self):
		if self.session.nav.RecordTimer.isRecording() or len(JobManager.getPendingJobs()) >= 1:
			config.timeshift.isRecording.value = True
			self.pts_mergeCleanUp_timer.start(120000, True)
			return

		self.ptsFrontpanelActions("stop")
		config.timeshift.isRecording.value = False

		filelist = os_listdir(config.usage.default_path.value)
		for filename in filelist:
			if filename.endswith(".pts.del"):
				srcfile = config.usage.default_path.value + "/" + filename[0:-8] + ".ts"
				self.BgFileEraser.erase("%s" % (srcfile))
				self.BgFileEraser.erase("%s.ap" % (srcfile))
				self.BgFileEraser.erase("%s.sc" % (srcfile))
				self.BgFileEraser.erase("%s.meta" % (srcfile))
				self.BgFileEraser.erase("%s.cuts" % (srcfile))
				self.BgFileEraser.erase("%s.eit" % (srcfile[0:-3]))
				self.BgFileEraser.erase("%s.pts.del" % (srcfile[0:-3]))

				# Restart QuitMainloop Timer to give BgFileEraser enough time
				if Screens.Standby.inTryQuitMainloop and self.pts_QuitMainloop_timer.isActive():
					self.pts_QuitMainloop_timer.start(60000, True)

	def ptsTryQuitMainloop(self):
		if Screens.Standby.inTryQuitMainloop and (len(JobManager.getPendingJobs()) >= 1 or self.pts_mergeCleanUp_timer.isActive()):
			self.pts_QuitMainloop_timer.start(60000, True)
			return

		if Screens.Standby.inTryQuitMainloop and self.session.ptsmainloopvalue:
			self.session.dialog_stack = []
			self.session.summary_stack = [None]
			self.session.open(TryQuitMainloop, self.session.ptsmainloopvalue)

	def ptsGetSeekInfo(self):
		s = self.session.nav.getCurrentService()
		return s and s.seek()

	def ptsGetPosition(self):
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		pos = seek.getPlayPosition()
		if pos[0]:
			return 0
		return pos[1]

	def ptsGetLength(self):
		seek = self.ptsGetSeekInfo()
		if seek is None:
			return None
		length = seek.getLength()
		if length[0]:
			return 0
		return length[1]

	def ptsGetSaveTimeshiftStatus(self):
		return self.save_current_timeshift

	def ptsSeekPointerOK(self):
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			if not self.pvrStateDialog.shown:
				if self.seekstate != self.SEEK_STATE_PLAY or self.seekstate == self.SEEK_STATE_PAUSE:
					self.setSeekState(self.SEEK_STATE_PLAY)
				self.doShow()
				return

			length = self.ptsGetLength()
			position = self.ptsGetPosition()

			if length is None or position is None:
				return

			cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
			jumptox = int(cur_pos[0]) - int(self.pts_seekpointer_MinX)
			jumptoperc = round((jumptox / 400.0) * 100, 0)
			jumptotime = int((length / 100) * jumptoperc)
			jumptodiff = position - jumptotime

			self.doSeekRelative(-jumptodiff)
		else:
			return

	def ptsSeekPointerLeft(self):
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			self.ptsMoveSeekPointer(direction="left")
		else:
			return

	def ptsSeekPointerRight(self):
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled and self.isSeekable():
			self.ptsMoveSeekPointer(direction="right")
		else:
			return

	def ptsSeekPointerReset(self):
		if self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" and self.timeshift_enabled:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX,self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsSeekPointerSetCurrentPos(self):
		if not self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState" or not self.timeshift_enabled or not self.isSeekable():
			return

		position = self.ptsGetPosition()
		length = self.ptsGetLength()

		if length >= 1:
			tpixels = int((float(int((position*100)/length))/100)*400)
			self.pvrStateDialog["PTSSeekPointer"].setPosition(self.pts_seekpointer_MinX+tpixels, self.pvrStateDialog["PTSSeekPointer"].position[1])

	def ptsMoveSeekPointer(self, direction=None):
		if direction is None or self.pts_pvrStateDialog != "Screens.PVRState.PTSTimeshiftState":
			return

		isvalidjump = False
		cur_pos = self.pvrStateDialog["PTSSeekPointer"].position
		self.doShow()

		if direction == "left":
			minmaxval = self.pts_seekpointer_MinX
			movepixels = -15
			if cur_pos[0]+movepixels > minmaxval:
				isvalidjump = True
		elif direction == "right":
			minmaxval = self.pts_seekpointer_MaxX
			movepixels = 15
			if cur_pos[0]+movepixels < minmaxval:
				isvalidjump = True
		else:
			return 0

		if isvalidjump:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(cur_pos[0]+movepixels,cur_pos[1])
		else:
			self.pvrStateDialog["PTSSeekPointer"].setPosition(minmaxval,cur_pos[1])

	def ptsTimeshiftFileChanged(self):
		# Reset Seek Pointer
		if config.timeshift.enabled.value:
			self.ptsSeekPointerReset()

		if self.pts_switchtolive:
			self.pts_switchtolive = False
			return

		if self.pts_seektoprevfile:
			if self.pts_currplaying == 1:
				self.pts_currplaying = config.timeshift.maxevents.value
			else:
				self.pts_currplaying -= 1
		else:
			if self.pts_currplaying == config.timeshift.maxevents.value:
				self.pts_currplaying = 1
			else:
				self.pts_currplaying += 1

		if not Directories.fileExists("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,self.pts_currplaying), 'r'):
			self.pts_currplaying = self.pts_eventcount

		# Set Eventname in PTS InfoBar
		if config.timeshift.enabled.value and self.pts_pvrStateDialog == "Screens.PVRState.PTSTimeshiftState":
			try:
				if self.pts_eventcount != self.pts_currplaying:
					readmetafile = open("%spts_livebuffer.%s.meta" % (config.usage.timeshift_path.value,self.pts_currplaying), "r")
					servicerefname = readmetafile.readline()[0:-1]
					eventname = readmetafile.readline()[0:-1]
					readmetafile.close()
					self.pvrStateDialog["eventname"].setText(eventname)
				else:
					self.pvrStateDialog["eventname"].setText("")
			except Exception, errormsg:
				self.pvrStateDialog["eventname"].setText("")

		# Get next pts file ...
		if self.pts_currplaying+1 > config.timeshift.maxevents.value:
			nextptsfile = 1
		else:
			nextptsfile = self.pts_currplaying+1

		# Seek to previous file
		if self.pts_seektoprevfile:
			self.pts_seektoprevfile = False

			if Directories.fileExists("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,nextptsfile), 'r'):
				self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (nextptsfile))

			self.ptsSeekBackHack()
		else:
			if Directories.fileExists("%spts_livebuffer.%s" % (config.usage.timeshift_path.value,nextptsfile), 'r') and nextptsfile <= self.pts_eventcount:
				self.ptsSetNextPlaybackFile("pts_livebuffer.%s" % (nextptsfile))
			if nextptsfile == self.pts_currplaying:
				self.pts_switchtolive = True
				self.ptsSetNextPlaybackFile("")

	def ptsSetNextPlaybackFile(self, nexttsfile):
		ts = self.getTimeshift()
		if ts is None:
			return

		try:
			ts.setNextPlaybackFile("%s%s" % (config.usage.timeshift_path.value,nexttsfile))
		except:
			print "[TimeShift] setNextPlaybackFile() not supported by OE. Enigma2 too old !?"

	def ptsSeekBackHack(self):
		if not config.timeshift.enabled.value or not self.timeshift_enabled:
			return

		self.setSeekState(self.SEEK_STATE_PAUSE)
		self.doSeek(-90000*4) # seek ~4s before end
		self.pts_SeekBack_timer.start(1000, True)

	def ptsSeekBackTimer(self):
		if self.pts_lastseekspeed == 0:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
		else:
			self.setSeekState(self.makeStateBackward(int(-self.pts_lastseekspeed)))

	def ptsCheckTimeshiftPath(self):
		if self.pts_pathchecked:
			return True
		else:
			if Directories.fileExists(config.usage.timeshift_path.value, 'w'):
				self.pts_pathchecked = True
				return True
			else:
				Notifications.AddNotification(MessageBox, _("Could not activate Permanent-Timeshift!\nTimeshift-Path does not exist"), MessageBox.TYPE_ERROR, timeout=15)
				if self.pts_delay_timer.isActive():
					self.pts_delay_timer.stop()
				if self.pts_cleanUp_timer.isActive():
					self.pts_cleanUp_timer.stop()
				return False

	def ptsTimerEntryStateChange(self, timer):
		if not config.timeshift.enabled.value or not config.timeshift.stopwhilerecording.value:
			return

		self.pts_record_running = self.session.nav.RecordTimer.isRecording()

		# Abort here when box is in standby mode
		if self.session.screen["Standby"].boolean is True:
			return

		# Stop Timeshift when Record started ...
		if timer.state == TimerEntry.StateRunning and self.timeshift_enabled and self.pts_record_running:
			if self.ptsLiveTVStatus() is False:
				self.timeshift_enabled = 0
				self.pts_LengthCheck_timer.stop()
				return

			if self.seekstate != self.SEEK_STATE_PLAY:
				self.setSeekState(self.SEEK_STATE_PLAY)

			if self.isSeekable():
				Notifications.AddNotification(MessageBox,_("Record started! Stopping timeshift now ..."), MessageBox.TYPE_INFO, timeout=5)

			self.stopTimeshiftConfirmed(True, False)

		# Restart Timeshift when all records stopped
		if timer.state == TimerEntry.StateEnded and not self.timeshift_enabled and not self.pts_record_running:
			self.activatePermanentTimeshift()

		# Restart Merge-Timer when all records stopped
		if timer.state == TimerEntry.StateEnded and self.pts_mergeRecords_timer.isActive():
			self.pts_mergeRecords_timer.stop()
			self.pts_mergeRecords_timer.start(15000, True)

		# Restart FrontPanel LED when still copying or merging files
		# ToDo: Only do this on PTS Events and not events from other jobs
		if timer.state == TimerEntry.StateEnded and (len(JobManager.getPendingJobs()) >= 1 or self.pts_mergeRecords_timer.isActive()):
			self.ptsFrontpanelActions("start")
			config.timeshift.isRecording.value = True

	def ptsLiveTVStatus(self):
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		sTSID = info and info.getInfo(iServiceInformation.sTSID) or -1

		if sTSID is None or sTSID == -1:
			return False
		else:
			return True

	def ptsLengthCheck(self):
		# Check if we are in TV Mode ...
		if self.ptsLiveTVStatus() is False:
			self.timeshift_enabled = 0
			self.pts_LengthCheck_timer.stop()
			return

		if config.timeshift.stopwhilerecording.value and self.pts_record_running:
			return

		# Length Check
		if config.timeshift.enabled.value and self.session.screen["Standby"].boolean is not True and self.timeshift_enabled and (time() - self.pts_starttime) >= (config.timeshift.maxlength.value * 60):
			if self.save_current_timeshift:
				self.saveTimeshiftActions("savetimeshift")
				self.activatePermanentTimeshift()
				self.save_current_timeshift = True
			else:
				self.activatePermanentTimeshift()
			Notifications.AddNotification(MessageBox,_("Maximum Timeshift length per Event reached!\nRestarting Timeshift now ..."), MessageBox.TYPE_INFO, timeout=5)

	def getTimeshift(self):
		service = self.session.nav.getCurrentService()
		return service and service.timeshift()

	# activates timeshift, and seeks to (almost) the end
	def activateTimeshiftEnd(self, back = True):
		ts = self.getTimeshift()
# 		print "activateTimeshiftEnd"

		if ts is None:
			return

		if ts.isTimeshiftActive():
# 			print "!! activate timeshift called - but shouldn't this be a normal pause?"
			self.pauseService()
		else:
# 			print "play, ..."
			ts.activateTimeshift() # activate timeshift will automatically pause
			self.setSeekState(self.SEEK_STATE_PAUSE)
			seekable = self.getSeek()
			if seekable is not None:
				seekable.seekTo(-90000) # seek approx. 1 sec before end
		if back:
			if config.misc.boxtype.value.startswith('et'):
					self.ts_rewind_timer.start(1000, 1)
			else:
					self.ts_rewind_timer.start(100, 1)

	def rewindService(self):
		self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))

	# same as activateTimeshiftEnd, but pauses afterwards.
	def activateTimeshiftEndAndPause(self):
# 		print "activateTimeshiftEndAndPause"
		#state = self.seekstate
		self.activateTimeshiftEnd(False)

from Screens.PiPSetup import PiPSetup

class InfoBarExtensions:
	EXTENSION_SINGLE = 0
	EXTENSION_LIST = 1

	def __init__(self):
		self.list = []

		if config.vixsettings.ColouredButtons.value:
			self["InstantExtensionsActions"] = HelpableActionMap(self, "InfobarExtensions",
				{
					"extensions": (self.showExtensionSelection, _("view extensions...")),
					"RedPressed": (self.RedPressed, _("Show epg")),
					"showPluginBrowser": (self.showPluginBrowser, _("Show the plugin browser..")),
					"showEventInfo": (self.openEventView, _("Show the infomation on current event.")),
					"openTimerList": (self.showTimerList, _("Show the tv player...")),
					"openAutoTimerList": (self.showAutoTimerList, _("Show the tv player...")),
					"openEPGSearch": (self.showEPGSearch, _("Show the tv player...")),
					"openIMDB": (self.showIMDB, _("Show the tv player...")),
					"showMediaPlayer": (self.showMediaPlayer, _("Show the media player...")),
				}, 1) # lower priority
		else:
			self["InstantExtensionsActions"] = HelpableActionMap(self, "InfobarExtensions",
				{
					"extensions": (self.showExtensionSelection, _("view extensions...")),
					"showPluginBrowser": (self.showPluginBrowser, _("Show the plugin browser..")),
					"showEventInfo": (self.openEventView, _("Show the infomation on current event.")),
					"showMediaPlayer": (self.showMediaPlayer, _("Show the media player...")),
				}, 1) # lower priority

		self.addExtension(extension = self.getLogManager, type = InfoBarExtensions.EXTENSION_LIST)
		self.addExtension(extension = self.getOsd3DSetup, type = InfoBarExtensions.EXTENSION_LIST)
		self.addExtension(extension = self.getCCcamInfo, type = InfoBarExtensions.EXTENSION_LIST)
		self.addExtension(extension = self.getOScamInfo, type = InfoBarExtensions.EXTENSION_LIST)

	def getLMname(self):
		return _("Log Manager")

	def getLogManager(self):
		if config.logmanager.showinextensions.value:
			return [((boundFunction(self.getLMname), boundFunction(self.openLogManager), lambda: True), None)]
		else:
			return []

	def get3DSetupname(self):
		return _("OSD 3D Setup")

	def getOsd3DSetup(self):
		if config.osd.show3dextensions .value:
			return [((boundFunction(self.get3DSetupname), boundFunction(self.openOSD3DSetup), lambda: True), None)]
		else:
			return []

	def getCCname(self):
		return _("CCcam Info")

	def getCCcamInfo(self):
		if Directories.pathExists('/usr/softcams/'):
			softcams = os_listdir('/usr/softcams/')
		for softcam in softcams:
			if softcam.lower().startswith('cccam') and config.cccaminfo.showInExtensions.value:
				return [((boundFunction(self.getCCname), boundFunction(self.openCCcamInfo), lambda: True), None)] or []
		else:
			return []

	def getOSname(self):
		return _("OScam Info")

	def getOScamInfo(self):
		if Directories.pathExists('/usr/softcams/'):
			softcams = os_listdir('/usr/softcams/')
		for softcam in softcams:
			if softcam.lower().startswith('oscam') and config.oscaminfo.showInExtensions.value:
				return [((boundFunction(self.getOSname), boundFunction(self.openOScamInfo), lambda: True), None)] or []
		else:
			return []

	def RedPressed(self):
		if isinstance(self, InfoBarEPG):
			if config.usage.defaultEPGType.value == "Graphical EPG..." or config.usage.defaultEPGType.value == "None":
				self.openSingleServiceEPG()
			else:
				self.openGraphEPG()
		else:
			self.openEventView()

	def addExtension(self, extension, key = None, type = EXTENSION_SINGLE):
		self.list.append((type, extension, key))

	def updateExtension(self, extension, key = None):
		self.extensionsList.append(extension)
		if key is not None:
			if self.extensionKeys.has_key(key):
				key = None

		if key is None:
			for x in self.availableKeys:
				if not self.extensionKeys.has_key(x):
					key = x
					break

		if key is not None:
			self.extensionKeys[key] = len(self.extensionsList) - 1

	def updateExtensions(self):
		self.extensionsList = []
		self.availableKeys = [ "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "red", "green", "yellow", "blue" ]
		self.extensionKeys = {}
		for x in self.list:
			if x[0] == self.EXTENSION_SINGLE:
				self.updateExtension(x[1], x[2])
			else:
				for y in x[1]():
					self.updateExtension(y[0], y[1])


	def showExtensionSelection(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		self.updateExtensions()
		extensionsList = self.extensionsList[:]
		keys = []
		list = []
		for x in self.availableKeys:
			if self.extensionKeys.has_key(x):
				entry = self.extensionKeys[x]
				extension = self.extensionsList[entry]
				if extension[2]():
					name = str(extension[0]())
					list.append((extension[0](), extension))
					keys.append(x)
					extensionsList.remove(extension)
				else:
					extensionsList.remove(extension)
		list.extend([(x[0](), x) for x in extensionsList])

		keys += [""] * len(extensionsList)
		self.session.openWithCallback(self.extensionCallback, ChoiceBox, title=_("Please choose an extension..."), list = list, keys = keys, skin_name = "ExtensionsList")

	def extensionCallback(self, answer):
		if answer is not None:
			answer[1][1]()

	def showPluginBrowser(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		from Screens.PluginBrowser import PluginBrowser
		self.session.open(PluginBrowser)

	def openCCcamInfo(self):
		from Screens.CCcamInfo import CCcamInfoMain
		self.session.open(CCcamInfoMain)

	def openOScamInfo(self):
		from Screens.OScamInfo import OscamInfoMenu
		self.session.open(OscamInfoMenu)

	def showTimerList(self):
		self.session.open(TimerEditList)

	def openLogManager(self):
		from Screens.LogManager import LogManager
		self.session.open(LogManager)

	def openOSD3DSetup(self):
		from Screens.OSD import OSD3DSetupScreen
		self.session.open(OSD3DSetupScreen)

	def showAutoTimerList(self):
		if os_path.exists("/usr/lib/enigma2/python/Plugins/Extensions/AutoTimer/plugin.pyo"):
			from Plugins.Extensions.AutoTimer.plugin import main, autostart
			from Plugins.Extensions.AutoTimer.AutoTimer import AutoTimer
			from Plugins.Extensions.AutoTimer.AutoPoller import AutoPoller
			autopoller = AutoPoller()
			autotimer = AutoTimer()
			global autotimer
			global autopoller
			try:
				autotimer.readXml()
			except SyntaxError as se:
				self.session.open(
					MessageBox,
					_("Your config file is not well-formed:\n%s") % (str(se)),
					type = MessageBox.TYPE_ERROR,
					timeout = 10
				)
				return

			# Do not run in background while editing, this might screw things up
			if autopoller is not None:
				autopoller.stop()

			from Plugins.Extensions.AutoTimer.AutoTimerOverview import AutoTimerOverview
			self.session.openWithCallback(
				self.editCallback,
				AutoTimerOverview,
				autotimer
			)
		else:
			self.session.open(MessageBox, _("The AutoTimer plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

	def editCallback(self, session):
		global autotimer
		global autopoller
		# XXX: canceling of GUI (Overview) won't affect config values which might have been changed - is this intended?
		# Don't parse EPG if editing was canceled
		if session is not None:
			# Save xml
			autotimer.writeXml()
			# Poll EPGCache
			autotimer.parseEPG()

		# Start autopoller again if wanted
		if config.plugins.autotimer.autopoll.value:
			if autopoller is None:
				from Plugins.Extensions.AutoTimer.AutoPoller import AutoPoller
				autopoller = AutoPoller()
			autopoller.start()
		# Remove instance if not running in background
		else:
			autopoller = None
			autotimer = None

	def showEPGSearch(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		from Plugins.Extensions.EPGSearch.EPGSearch import EPGSearch
		s = self.session.nav.getCurrentService()
		if s:
			info = s.info()
			event = info.getEvent(0) # 0 = now, 1 = next
			if event:
				name = event and event.getEventName() or ''
			else:
				name = self.session.nav.getCurrentlyPlayingServiceReference().toString()
				name = name.split('/')
				name = name[-1]
				name = name.replace('.',' ')
				name = name.split('-')
				name = name[0]
				if name.endswith(' '):
					name = name[:-1]
		if name:
			self.session.open(EPGSearch, name, False)
		else:
			self.session.open(EPGSearch)

	def showIMDB(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if os_path.exists("/usr/lib/enigma2/python/Plugins/Extensions/IMDb/plugin.pyo"):
			from Plugins.Extensions.IMDb.plugin import IMDB
			s = self.session.nav.getCurrentService()
			if s:
				info = s.info()
				event = info.getEvent(0) # 0 = now, 1 = next
				name = event and event.getEventName() or ''
				self.session.open(IMDB, name)
		else:
			self.session.open(MessageBox, _("The IMDb plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

	def showMediaPlayer(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if isinstance(self, InfoBarExtensions):
			if isinstance(self, InfoBar):
				try: # falls es nicht installiert ist
					from Plugins.Extensions.MediaPlayer.plugin import MediaPlayer
					self.session.open(MediaPlayer)
					no_plugin = False
				except Exception, e:
					self.session.open(MessageBox, _("The MediaPlayer plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

from Tools.BoundFunction import boundFunction
import inspect

# depends on InfoBarExtensions

class InfoBarPlugins:
	def __init__(self):
		self.addExtension(extension = self.getPluginList, type = InfoBarExtensions.EXTENSION_LIST)

	def getPluginName(self, name):
		return name

	def getPluginList(self):
		l = []
		for p in plugins.getPlugins(where = PluginDescriptor.WHERE_EXTENSIONSMENU):
			args = inspect.getargspec(p.__call__)[0]
			if len(args) == 1 or len(args) == 2 and isinstance(self, InfoBarChannelSelection):
				l.append(((boundFunction(self.getPluginName, p.name), boundFunction(self.runPlugin, p), lambda: True), None, p.name))
		l.sort(key = lambda e: e[2]) # sort by name
		return l

	def runPlugin(self, plugin):
		if isinstance(self, InfoBarChannelSelection):
			plugin(session = self.session, servicelist = self.servicelist)
		else:
			plugin(session = self.session)

from Components.Task import job_manager
class InfoBarJobman:
	def __init__(self):
		self.addExtension(extension = self.getJobList, type = InfoBarExtensions.EXTENSION_LIST)

	def getJobList(self):
		if config.usage.jobtaksextensions.getValue():
			return [((boundFunction(self.getJobName, job), boundFunction(self.showJobView, job), lambda: True), None) for job in job_manager.getPendingJobs()]
		else:
			return []

	def getJobName(self, job):
		return "%s: %s (%d%%)" % (job.getStatustext(), job.name, int(100*job.progress/float(job.end)))

	def showJobView(self, job):
		from Screens.TaskView import JobView
		job_manager.in_background = False
		self.session.openWithCallback(self.JobViewCB, JobView, job)

	def JobViewCB(self, in_background):
		job_manager.in_background = in_background

# depends on InfoBarExtensions
class InfoBarPiP:
	def __init__(self):
		try:
			self.session.pipshown
		except:
			self.session.pipshown = False
		if SystemInfo.get("NumVideoDecoders", 1) > 1 and isinstance(self, InfoBarEPG):
			self["PiPActions"] = HelpableActionMap(self, "InfobarPiPActions",
				{
					"activatePiP": (self.showPiP, _("activate PiP")),
				})
			if (self.allowPiP):
				self.addExtension((self.getShowHideName, self.showPiP, lambda: True), "blue")
				self.addExtension((self.getMoveName, self.movePiP, self.pipShown), "green")
				self.addExtension((self.getSwapName, self.swapPiP, self.pipShown), "yellow")
				self.addExtension((self.getTogglePipzapName, self.togglePipzap, self.pipShown), "red")
			else:
				self.addExtension((self.getShowHideName, self.showPiP, self.pipShown), "blue")
				self.addExtension((self.getMoveName, self.movePiP, self.pipShown), "green")

	def pipShown(self):
		return self.session.pipshown

	def pipHandles0Action(self):
		return self.pipShown() and config.usage.pip_zero_button.value != "standard"

	def getShowHideName(self):
		if self.session.pipshown:
			return _("Disable Picture in Picture")
		else:
			return _("Activate Picture in Picture")

	def getSwapName(self):
		return _("Swap Services")

	def getMoveName(self):
		return _("Move Picture in Picture")

	def getTogglePipzapName(self):
		slist = self.servicelist
		if slist and slist.dopipzap:
			return _("Zap focus to main screen")
		return _("Zap focus to Picture in Picture")

	def togglePipzap(self):
		if not self.session.pipshown:
			self.showPiP()
		slist = self.servicelist
		if slist:
			slist.togglePipzap()

	def showPiP(self):
		if self.session.pipshown:
			slist = self.servicelist
			if slist and slist.dopipzap:
				slist.togglePipzap()
			del self.session.pip
			self.session.pipshown = False
		else:
			self.session.pip = self.session.instantiateDialog(PictureInPicture)
			self.session.pip.show()
			newservice = self.servicelist.servicelist.getCurrent()
			if self.session.pip.playService(newservice):
				self.session.pipshown = True
				self.session.pip.servicePath = self.servicelist.getCurrentServicePath()
			else:
				self.session.pipshown = False
				del self.session.pip

	def swapPiP(self):
		swapservice = self.session.nav.getCurrentlyPlayingServiceReference()
		pipref = self.session.pip.getCurrentService()
		if swapservice and pipref and pipref.toString() != swapservice.toString():
			currentServicePath = self.servicelist.getCurrentServicePath()
			self.servicelist.setCurrentServicePath(self.session.pip.servicePath)
			self.session.pip.playService(swapservice)
			self.session.nav.stopService() # stop portal
			self.session.nav.playService(pipref) # start subservice
			self.session.pip.servicePath = currentServicePath

	def movePiP(self):
		self.session.open(PiPSetup, pip = self.session.pip)

	def pipDoHandle0Action(self):
		use = config.usage.pip_zero_button.value
		if "swap" == use:
			self.swapPiP()
		elif "swapstop" == use:
			self.swapPiP()
			self.showPiP()
		elif "stop" == use:
			self.showPiP()

from RecordTimer import parseEvent, RecordTimerEntry

class InfoBarInstantRecord:
	"""Instant Record - handles the instantRecord action in order to
	start/stop instant records"""
	def __init__(self):
		self["InstantRecordActions"] = HelpableActionMap(self, "InfobarInstantRecord",
			{
				"instantRecord": (self.instantRecord, _("Instant Record...")),
			})
		self.recording = []

	def stopCurrentRecording(self, entry = -1):
		if entry is not None and entry != -1:
			self.session.nav.RecordTimer.removeEntry(self.recording[entry])
			self.recording.remove(self.recording[entry])

	def startInstantRecording(self, limitEvent = False):
		serviceref = self.session.nav.getCurrentlyPlayingServiceReference()

		# try to get event info
		event = None
		try:
			service = self.session.nav.getCurrentService()
			epg = eEPGCache.getInstance()
			event = epg.lookupEventTime(serviceref, -1, 0)
			if event is None:
				info = service.info()
				ev = info.getEvent(0)
				event = ev
		except:
			pass

		begin = int(time())
		end = begin + 3600	# dummy
		name = "instant record"
		description = ""
		eventid = None

		if event is not None:
			curEvent = parseEvent(event)
			name = curEvent[2]
			description = curEvent[3]
			eventid = curEvent[4]
			if limitEvent:
				end = curEvent[1]
		else:
			if limitEvent:
				self.session.open(MessageBox, _("No event info found, recording indefinitely."), MessageBox.TYPE_INFO)

		if isinstance(serviceref, eServiceReference):
			serviceref = ServiceReference(serviceref)

		recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname = preferredInstantRecordPath())
		recording.dontSave = True

		if event is None or limitEvent == False:
			recording.autoincrease = True
			recording.setAutoincreaseEnd()

		simulTimerList = self.session.nav.RecordTimer.record(recording)

		if simulTimerList is None:	# no conflict
			self.recording.append(recording)
		else:
			if len(simulTimerList) > 1: # with other recording
				name = simulTimerList[1].name
				name_date = ' '.join((name, strftime('%F %T', localtime(simulTimerList[1].begin))))
				print "[TIMER] conflicts with", name_date
				recording.autoincrease = True	# start with max available length, then increment
				if recording.setAutoincreaseEnd():
					self.session.nav.RecordTimer.record(recording)
					self.recording.append(recording)
					self.session.open(MessageBox, _("Record time limited due to conflicting timer %s") % name_date, MessageBox.TYPE_INFO)
				else:
					self.session.open(MessageBox, _("Couldn't record due to conflicting timer %s") % name, MessageBox.TYPE_INFO)
			else:
				self.session.open(MessageBox, _("Couldn't record due to invalid service %s") % serviceref, MessageBox.TYPE_INFO)
			recording.autoincrease = False

	def isInstantRecordRunning(self):
# 		print "self.recording:", self.recording
		if self.recording:
			for x in self.recording:
				if x.isRunning():
					return True
		return False

	def recordQuestionCallback(self, answer):
# 		print "pre:\n", self.recording

		if answer is None or answer[1] == "no":
			return
		list = []
		recording = self.recording[:]
		for x in recording:
			if not x in self.session.nav.RecordTimer.timer_list:
				self.recording.remove(x)
			elif x.dontSave and x.isRunning():
				list.append((x, False))

		if answer[1] == "changeduration":
			if len(self.recording) == 1:
				self.changeDuration(0)
			else:
				self.session.openWithCallback(self.changeDuration, TimerSelection, list)
		elif answer[1] == "changeendtime":
			if len(self.recording) == 1:
				self.setEndtime(0)
			else:
				self.session.openWithCallback(self.setEndtime, TimerSelection, list)
		elif answer[1] == "stop":
			self.session.openWithCallback(self.stopCurrentRecording, TimerSelection, list)
		elif answer[1] in ( "indefinitely" , "manualduration", "manualendtime", "event"):
			self.startInstantRecording(limitEvent = answer[1] in ("event", "manualendtime") or False)
			if answer[1] == "manualduration":
				self.changeDuration(len(self.recording)-1)
			elif answer[1] == "manualendtime":
				self.setEndtime(len(self.recording)-1)
# 		print "after:\n", self.recording

		if config.timeshift.enabled.value:
			if answer is not None and answer[1] == "savetimeshift":
				if InfoBarSeek.isSeekable(self) and self.pts_eventcount != self.pts_currplaying:
					InfoBarTimeshift.SaveTimeshift(self, timeshiftfile="pts_livebuffer.%s" % self.pts_currplaying)
					#InfoBarTimeshift.saveTimeshiftEventPopup(self)
				else:
					Notifications.AddNotification(MessageBox,_("Timeshift will get saved at end of event!"), MessageBox.TYPE_INFO, timeout=5)
					self.save_current_timeshift = True
					config.timeshift.isRecording.value = True
			if answer is not None and answer[1] == "savetimeshiftEvent":
				InfoBarTimeshift.saveTimeshiftEventPopup(self)

			if answer is not None and answer[1].startswith("pts_livebuffer") is True:
				InfoBarTimeshift.SaveTimeshift(self, timeshiftfile=answer[1])

	def setEndtime(self, entry):
		if entry is not None and entry >= 0:
			self.selectedEntry = entry
			self.endtime=ConfigClock(default = self.recording[self.selectedEntry].end)
			dlg = self.session.openWithCallback(self.TimeDateInputClosed, TimeDateInput, self.endtime)
			dlg.setTitle(_("Please change recording endtime"))

	def TimeDateInputClosed(self, ret):
		if len(ret) > 1:
			if ret[0]:
# 				print "stopping recording at", strftime("%F %T", localtime(ret[1]))
				if self.recording[self.selectedEntry].end != ret[1]:
					self.recording[self.selectedEntry].autoincrease = False
				self.recording[self.selectedEntry].end = ret[1]
		else:
			if self.recording[self.selectedEntry].end != int(time()):
				self.recording[self.selectedEntry].autoincrease = False
			self.recording[self.selectedEntry].end = int(time())
		self.session.nav.RecordTimer.timeChanged(self.recording[self.selectedEntry])

	def changeDuration(self, entry):
		if entry is not None and entry >= 0:
			self.selectedEntry = entry
			self.session.openWithCallback(self.inputCallback, InputBox, title=_("How many minutes do you want to record?"), text="5", maxSize=False, type=Input.NUMBER)

	def inputCallback(self, value):
# 		print "stopping recording after", int(value), "minutes."
		entry = self.recording[self.selectedEntry]
		if value is not None:
			if int(value) != 0:
				entry.autoincrease = False
			entry.end = int(time()) + 60 * int(value)
		else:
			if entry.end != int(time()):
				entry.autoincrease = False
			entry.end = int(time())
		self.session.nav.RecordTimer.timeChanged(entry)

	def instantRecord(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		pirr = preferredInstantRecordPath()
		if not config.timeshift.enabled.value or not self.timeshift_enabled:
			if not findSafeRecordPath(pirr) and not findSafeRecordPath(defaultMoviePath()):
				if not pirr:
					pirr = ""
				self.session.open(MessageBox, _("Missing ") + "\n" + pirr +
							 "\n" + _("No HDD found or HDD not initialized!"), MessageBox.TYPE_ERROR)
				return

			if self.isInstantRecordRunning():
				self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
					title=_("A recording is currently running.\nWhat do you want to do?"), \
					list=((_("stop recording"), "stop"), \
					(_("add recording (stop after current event)"), "event"), \
					(_("add recording (indefinitely)"), "indefinitely"), \
					(_("add recording (enter recording duration)"), "manualduration"), \
					(_("add recording (enter recording endtime)"), "manualendtime"), \
					(_("change recording (duration)"), "changeduration"), \
					(_("change recording (endtime)"), "changeendtime"), \
					(_("do nothing"), "no")))
			else:
				self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
					title=_("Start recording?"), \
					list=((_("add recording (stop after current event)"), "event"), \
					(_("add recording (indefinitely)"), "indefinitely"), \
					(_("add recording (enter recording duration)"), "manualduration"), \
					(_("add recording (enter recording endtime)"), "manualendtime"), \
					(_("don't record"), "no")))
			return
		else:
			dir = preferredInstantRecordPath()
			if not dir or not Directories.fileExists(dir, 'w'):
				dir = defaultMoviePath()
			try:
				stat = os_stat(dir)
			except:
				# XXX: this message is a little odd as we might be recording to a remote device
				self.session.open(MessageBox, _("No HDD found or HDD not initialized!"), MessageBox.TYPE_ERROR)
				return

			#if self.session.nav.RecordTimer.isRecording():
			if self.isInstantRecordRunning():
				self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
					title=_("A recording is currently running.\nWhat do you want to do?"), \
					list=((_("stop recording"), "stop"), \
					(_("add recording (stop after current event)"), "event"), \
					(_("add recording (indefinitely)"), "indefinitely"), \
					(_("add recording (enter recording duration)"), "manualduration"), \
					(_("add recording (enter recording endtime)"), "manualendtime"), \
					(_("change recording (duration)"), "changeduration"), \
					(_("change recording (endtime)"), "changeendtime"), \
					(_("Timeshift")+" "+_("save recording (stop after current event)"), "savetimeshift"), \
					(_("Timeshift")+" "+_("save recording (Select event)"), "savetimeshiftEvent"), \
					(_("do nothing"), "no")))
			else:
				self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
					title=_("Start recording?"), \
					list=((_("add recording (stop after current event)"), "event"), \
					(_("add recording (indefinitely)"), "indefinitely"), \
					(_("add recording (enter recording duration)"), "manualduration"), \
					(_("add recording (enter recording endtime)"), "manualendtime"), \
					(_("Timeshift")+" "+_("save recording (stop after current event)"), "savetimeshift"), \
					(_("Timeshift")+" "+_("save recording (Select event)"), "savetimeshiftEvent"), \
					(_("don't record"), "no")))

from Tools.ISO639 import LanguageCodes

class InfoBarAudioSelection:
	def __init__(self):
		self["AudioSelectionAction"] = HelpableActionMap(self, "InfobarAudioSelectionActions",
			{
				"audioSelection": (self.audioSelection, _("Audio Options...")),
			})

	def audioSelection(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		from Screens.AudioSelection import AudioSelection
		self.session.openWithCallback(self.audioSelected, AudioSelection, infobar=self)

	def audioSelected(self, ret=None):
		print "[infobar::audioSelected]", ret

class InfoBarSubserviceSelection:
	def __init__(self):
		self["SubserviceSelectionAction"] = HelpableActionMap(self, "InfobarSubserviceSelectionActions",
			{
				"GreenPressed": (self.GreenPressed),
			})

		self["SubserviceQuickzapAction"] = HelpableActionMap(self, "InfobarSubserviceQuickzapActions",
			{
				"nextSubservice": (self.nextSubservice, _("Switch to next subservice")),
				"prevSubservice": (self.prevSubservice, _("Switch to previous subservice"))
			}, -1)
		self["SubserviceQuickzapAction"].setEnabled(False)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.checkSubservicesAvail
			})
		self.onClose.append(self.__removeNotifications)

		self.bsel = None

	def GreenPressed(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		if not config.vixsettings.Subservice.value:
			self.openTimerList()
		else:
			self.subserviceSelection()

	def __removeNotifications(self):
		self.session.nav.event.remove(self.checkSubservicesAvail)

	def checkSubservicesAvail(self):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		if not subservices or subservices.getNumberOfSubservices() == 0:
			self["SubserviceQuickzapAction"].setEnabled(False)

	def nextSubservice(self):
		self.changeSubservice(+1)

	def prevSubservice(self):
		self.changeSubservice(-1)

	def changeSubservice(self, direction):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		n = subservices and subservices.getNumberOfSubservices()
		if n and n > 0:
			selection = -1
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			idx = 0
			while idx < n:
				if subservices.getSubservice(idx).toString() == ref.toString():
					selection = idx
					break
				idx += 1
			if selection != -1:
				selection += direction
				if selection >= n:
					selection=0
				elif selection < 0:
					selection=n-1
				newservice = subservices.getSubservice(selection)
				if newservice.valid():
					del subservices
					del service
					self.session.nav.playService(newservice, False)

	def subserviceSelection(self):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		self.bouquets = self.servicelist.getBouquetList()
		n = subservices and subservices.getNumberOfSubservices()
		selection = 0
		if n and n > 0:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			tlist = []
			idx = 0
			while idx < n:
				i = subservices.getSubservice(idx)
				if i.toString() == ref.toString():
					selection = idx
				tlist.append((i.getName(), i))
				idx += 1

			if self.bouquets and len(self.bouquets):
				keys = ["red", "blue", "",  "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" ] + [""] * n
				if config.usage.multibouquet.value:
					tlist = [(_("Quickzap"), "quickzap", service.subServices()), (_("Add to bouquet"), "CALLFUNC", self.addSubserviceToBouquetCallback), ("--", "")] + tlist
				else:
					tlist = [(_("Quickzap"), "quickzap", service.subServices()), (_("Add to favourites"), "CALLFUNC", self.addSubserviceToBouquetCallback), ("--", "")] + tlist
				selection += 3
			else:
				tlist = [(_("Quickzap"), "quickzap", service.subServices()), ("--", "")] + tlist
				keys = ["red", "",  "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" ] + [""] * n
				selection += 2

			self.session.openWithCallback(self.subserviceSelected, ChoiceBox, title=_("Please select a subservice..."), list = tlist, selection = selection, keys = keys, skin_name = "SubserviceSelection")

	def subserviceSelected(self, service):
		del self.bouquets
		if not service is None:
			if isinstance(service[1], str):
				if service[1] == "quickzap":
					from Screens.SubservicesQuickzap import SubservicesQuickzap
					self.session.open(SubservicesQuickzap, service[2])
			else:
				self["SubserviceQuickzapAction"].setEnabled(True)
				self.session.nav.playService(service[1], False)

	def addSubserviceToBouquetCallback(self, service):
		if len(service) > 1 and isinstance(service[1], eServiceReference):
			self.selectedSubservice = service
			if self.bouquets is None:
				cnt = 0
			else:
				cnt = len(self.bouquets)
			if cnt > 1: # show bouquet list
				self.bsel = self.session.openWithCallback(self.bouquetSelClosed, BouquetSelector, self.bouquets, self.addSubserviceToBouquet)
			elif cnt == 1: # add to only one existing bouquet
				self.addSubserviceToBouquet(self.bouquets[0][1])
				self.session.open(MessageBox, _("Service has been added to the favourites."), MessageBox.TYPE_INFO)

	def bouquetSelClosed(self, confirmed):
		self.bsel = None
		del self.selectedSubservice
		if confirmed:
			self.session.open(MessageBox, _("Service has been added to the selected bouquet."), MessageBox.TYPE_INFO)

	def addSubserviceToBouquet(self, dest):
		self.servicelist.addServiceToBouquet(dest, self.selectedSubservice[1])
		if self.bsel:
			self.bsel.close(True)
		else:
			del self.selectedSubservice

	def openTimerList(self):
		self.session.open(TimerEditList)

class InfoBarRedButton:
	def __init__(self):
		self["RedButtonActions"] = HelpableActionMap(self, "InfobarRedButtonActions",
			{
				"activateRedButton": (self.activateRedButton, _("Red button...")),
			})
		self.onHBBTVActivation = [ ]
		self.onRedButtonActivation = [ ]

	def activateRedButton(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info and info.getInfoString(iServiceInformation.sHBBTVUrl) != "":
			for x in self.onHBBTVActivation:
				x()
		elif False: # TODO: other red button services
			for x in self.onRedButtonActivation:
				x()

class InfoBarAdditionalInfo:
	def __init__(self):
		self["RecordingPossible"] = Boolean(fixed=harddiskmanager.HDDCount() > 0)
		self["TimeshiftPossible"] = self["RecordingPossible"]
		self["ExtensionsAvailable"] = Boolean(fixed=1)
		# TODO: these properties should be queried from the input device keymap
		self["ShowTimeshiftOnYellow"] = Boolean(fixed=0)
		self["ShowAudioOnYellow"] = Boolean(fixed=0)
		self["ShowRecordOnRed"] = Boolean(fixed=0)

class InfoBarNotifications:
	def __init__(self):
		self.onExecBegin.append(self.checkNotifications)
		Notifications.notificationAdded.append(self.checkNotificationsIfExecing)
		self.onClose.append(self.__removeNotification)

	def __removeNotification(self):
		Notifications.notificationAdded.remove(self.checkNotificationsIfExecing)

	def checkNotificationsIfExecing(self):
		if self.execing:
			self.checkNotifications()

	def checkNotifications(self):
		notifications = Notifications.notifications
		if notifications:
			n = notifications[0]

			del notifications[0]
			cb = n[0]

			if n[3].has_key("onSessionOpenCallback"):
				n[3]["onSessionOpenCallback"]()
				del n[3]["onSessionOpenCallback"]

			if cb is not None:
				dlg = self.session.openWithCallback(cb, n[1], *n[2], **n[3])
			else:
				dlg = self.session.open(n[1], *n[2], **n[3])

			# remember that this notification is currently active
			d = (n[4], dlg)
			Notifications.current_notifications.append(d)
			dlg.onClose.append(boundFunction(self.__notificationClosed, d))

	def __notificationClosed(self, d):
		Notifications.current_notifications.remove(d)

class InfoBarServiceNotifications:
	def __init__(self):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.serviceHasEnded
			})

	def serviceHasEnded(self):
# 		print "service end!"
		try:
			self.setSeekState(self.SEEK_STATE_PLAY)
		except:
			pass

class InfoBarCueSheetSupport:
	CUT_TYPE_IN = 0
	CUT_TYPE_OUT = 1
	CUT_TYPE_MARK = 2
	CUT_TYPE_LAST = 3

	ENABLE_RESUME_SUPPORT = False

	def __init__(self, actionmap = "InfobarCueSheetActions"):
		self["CueSheetActions"] = HelpableActionMap(self, actionmap,
			{
				"jumpPreviousMark": (self.jumpPreviousMark, _("jump to previous marked position")),
				"jumpNextMark": (self.jumpNextMark, _("jump to next marked position")),
				"toggleMark": (self.toggleMark, _("toggle a cut mark at the current position"))
			}, prio=1)

		self.cut_list = [ ]
		self.is_closing = False
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__serviceStarted,
			})

	def __serviceStarted(self):
		if self.is_closing:
			return
# 		print "new service started! trying to download cuts!"
		self.downloadCuesheet()

		if self.ENABLE_RESUME_SUPPORT:
			for (pts, what) in self.cut_list:
				if what == self.CUT_TYPE_LAST:
					last = pts
					break
			else:
				last = getResumePoint(self.session)
			if last is None:
				return
			# only resume if at least 10 seconds ahead, or <10 seconds before the end.
			seekable = self.__getSeekable()
			if seekable is None:
				return # Should not happen?
			length = seekable.getLength() or (None,0)
# 			print "seekable.getLength() returns:", length
			# Hmm, this implies we don't resume if the length is unknown...
			if (last > 900000) and (not length[1]  or (last < length[1] - 900000)):
				self.resume_point = last
				l = last / 90000
				if config.usage.on_movie_start.value == "ask" or not length[1]:
					Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Do you want to resume this playback?") + "\n" + (_("Resume position at %s") % ("%d:%02d:%02d" % (l/3600, l%3600/60, l%60))), timeout=10)
				elif config.usage.on_movie_start.value == "resume":
# TRANSLATORS: The string "Resuming playback" flashes for a moment
# TRANSLATORS: at the start of a movie, when the user has selected
# TRANSLATORS: "Resume from last position" as start behavior.
# TRANSLATORS: The purpose is to notify the user that the movie starts
# TRANSLATORS: in the middle somewhere and not from the beginning.
# TRANSLATORS: (Some translators seem to have interpreted it as a
# TRANSLATORS: question or a choice, but it is a statement.)
					Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Resuming playback"), timeout=2, type=MessageBox.TYPE_INFO)

	def playLastCB(self, answer):
		if answer == True:
			self.doSeek(self.resume_point)
		self.hideAfterResume()

	def hideAfterResume(self):
		if isinstance(self, InfoBarShowHide):
			self.hide()

	def __getSeekable(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None
		return service.seek()

	def cueGetCurrentPosition(self):
		seek = self.__getSeekable()
		if seek is None:
			return None
		r = seek.getPlayPosition()
		if r[0]:
			return None
		return long(r[1])

	def cueGetEndCutPosition(self):
		ret = False
		isin = True
		for cp in self.cut_list:
			if cp[1] == self.CUT_TYPE_OUT:
				if isin:
					isin = False
					ret = cp[0]
			elif cp[1] == self.CUT_TYPE_IN:
				isin = True
		return ret

	def jumpPreviousNextMark(self, cmp, start=False):
		current_pos = self.cueGetCurrentPosition()
		if current_pos is None:
			return False
		mark = self.getNearestCutPoint(current_pos, cmp=cmp, start=start)
		if mark is not None:
			pts = mark[0]
		else:
			return False

		self.doSeek(pts)
		return True

	def jumpPreviousMark(self):
		# we add 5 seconds, so if the play position is <5s after
		# the mark, the mark before will be used
		self.jumpPreviousNextMark(lambda x: -x-5*90000, start=True)

	def jumpNextMark(self):
		if not self.jumpPreviousNextMark(lambda x: x-90000):
			self.doSeek(-1)

	def getNearestCutPoint(self, pts, cmp=abs, start=False):
		# can be optimized
		beforecut = True
		nearest = None
		bestdiff = -1
		instate = True
		if start:
			bestdiff = cmp(0 - pts)
			if bestdiff >= 0:
				nearest = [0, False]
		for cp in self.cut_list:
			if beforecut and cp[1] in (self.CUT_TYPE_IN, self.CUT_TYPE_OUT):
				beforecut = False
				if cp[1] == self.CUT_TYPE_IN:  # Start is here, disregard previous marks
					diff = cmp(cp[0] - pts)
					if start and diff >= 0:
						nearest = cp
						bestdiff = diff
					else:
						nearest = None
						bestdiff = -1
			if cp[1] == self.CUT_TYPE_IN:
				instate = True
			elif cp[1] == self.CUT_TYPE_OUT:
				instate = False
			elif cp[1] in (self.CUT_TYPE_MARK, self.CUT_TYPE_LAST):
				diff = cmp(cp[0] - pts)
				if instate and diff >= 0 and (nearest is None or bestdiff > diff):
					nearest = cp
					bestdiff = diff
		return nearest

	def toggleMark(self, onlyremove=False, onlyadd=False, tolerance=5*90000, onlyreturn=False):
		current_pos = self.cueGetCurrentPosition()
		if current_pos is None:
# 			print "not seekable"
			return

		nearest_cutpoint = self.getNearestCutPoint(current_pos)

		if nearest_cutpoint is not None and abs(nearest_cutpoint[0] - current_pos) < tolerance:
			if onlyreturn:
				return nearest_cutpoint
			if not onlyadd:
				self.removeMark(nearest_cutpoint)
		elif not onlyremove and not onlyreturn:
			self.addMark((current_pos, self.CUT_TYPE_MARK))

		if onlyreturn:
			return None

	def addMark(self, point):
		insort(self.cut_list, point)
		self.uploadCuesheet()
		self.showAfterCuesheetOperation()

	def removeMark(self, point):
		self.cut_list.remove(point)
		self.uploadCuesheet()
		self.showAfterCuesheetOperation()

	def showAfterCuesheetOperation(self):
		if isinstance(self, InfoBarShowHide):
			self.doShow()

	def __getCuesheet(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None
		return service.cueSheet()

	def uploadCuesheet(self):
		cue = self.__getCuesheet()

		if cue is None:
# 			print "upload failed, no cuesheet interface"
			return
		cue.setCutList(self.cut_list)

	def downloadCuesheet(self):
		cue = self.__getCuesheet()

		if cue is None:
# 			print "download failed, no cuesheet interface"
			self.cut_list = [ ]
		else:
			self.cut_list = cue.getCutList()

class InfoBarSummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="62,46" size="82,18" font="Regular;16" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
		<widget source="session.RecordState" render="FixedLabel" text=" " position="62,46" size="82,18" zPosition="1" >
			<convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
			<convert type="ConditionalShowHide">Blink</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="6,4" size="120,42" font="Regular;18" >
			<convert type="ServiceName">Name</convert>
		</widget>
		<widget source="session.Event_Now" render="Progress" position="6,46" size="46,18" borderWidth="1" >
			<convert type="EventTime">Progress</convert>
		</widget>
	</screen>"""

# for picon:  (path="piconlcd" will use LCD picons)
#		<widget source="session.CurrentService" render="Picon" position="6,0" size="120,64" path="piconlcd" >
#			<convert type="ServiceName">Reference</convert>
#		</widget>

class InfoBarSummarySupport:
	def __init__(self):
		pass

	def createSummary(self):
		return InfoBarSummary

class InfoBarMoviePlayerSummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="62,46" size="64,18" font="Regular;16" halign="right" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
		<widget source="session.RecordState" render="FixedLabel" text=" " position="62,46" size="64,18" zPosition="1" >
			<convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
			<convert type="ConditionalShowHide">Blink</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="6,4" size="120,42" font="Regular;18" >
			<convert type="ServiceName">Name</convert>
		</widget>
		<widget source="session.CurrentService" render="Progress" position="6,46" size="56,18" borderWidth="1" >
			<convert type="ServicePosition">Position</convert>
		</widget>
	</screen>"""
	def __init__(self, session, parent):
		Screen.__init__(self, session, parent = parent)
		self["state_summary"] = StaticText("")
		self["speed_summary"] = StaticText("")
 		self["statusicon_summary"] = MultiPixmap()
		self.onShow.append(self.addWatcher)
		self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		self.parent.onChangedEntry.append(self.selectionChanged)

	def removeWatcher(self):
		self.parent.onChangedEntry.remove(self.selectionChanged)

	def selectionChanged(self, state_summary, speed_summary, statusicon_summary):
		self["state_summary"].setText(state_summary)
		self["speed_summary"].setText(speed_summary)
		self["statusicon_summary"].setPixmapNum(int(statusicon_summary))

class InfoBarMoviePlayerSummarySupport:
	def __init__(self):
		pass

	def createSummary(self):
		return InfoBarMoviePlayerSummary

class InfoBarTeletextPlugin:
	def __init__(self):
		self.teletext_plugin = None
		for p in plugins.getPlugins(PluginDescriptor.WHERE_TELETEXT):
			self.teletext_plugin = p

		if self.teletext_plugin is not None:
			self["TeletextActions"] = HelpableActionMap(self, "InfobarTeletextActions",
				{
					"startTeletext": (self.startTeletext, _("View teletext..."))
				})
		else:
			print "no teletext plugin found!"

	def startTeletext(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		self.teletext_plugin(session=self.session, service=self.session.nav.getCurrentService())

class InfoBarSubtitleSupport(object):
	def __init__(self):
		object.__init__(self)
		self["SubtitleSelectionAction"] = HelpableActionMap(self, "InfobarSubtitleSelectionActions",
			{
				"subtitleSelection": (self.subtitleSelection, _("Subtitle selection...")),
			})

		self.subtitle_window = self.session.instantiateDialog(SubtitleDisplay)
		self.__subtitles_enabled = False

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.__serviceStopped,
				iPlayableService.evUpdatedInfo: self.__updatedInfo
			})
		self.__selected_subtitle = None

	def subtitleSelection(self):
		if self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.secondInfoBarWasShown = False
		service = self.session.nav.getCurrentService()
		subtitle = service and service.subtitle()
		subtitlelist = subtitle and subtitle.getSubtitleList()
		if self.__subtitles_enabled or subtitlelist and len(subtitlelist)>0:
			from Screens.AudioSelection import SubtitleSelection
			self.session.open(SubtitleSelection, self)

	def __serviceStopped(self):
		if self.__subtitles_enabled:
			self.subtitle_window.hide()
			self.__subtitles_enabled = False
			self.__selected_subtitle = None

	def __updatedInfo(self):
		subtitle = self.getCurrentServiceSubtitle()
		cachedsubtitle = subtitle.getCachedSubtitle()
		if subtitle and cachedsubtitle:
			if self.__selected_subtitle and self.__subtitles_enabled and cachedsubtitle != self.__selected_subtitle:
				subtitle.disableSubtitles(self.subtitle_window.instance)
				self.subtitle_window.hide()
				self.__subtitles_enabled = False
			self.setSelectedSubtitle(cachedsubtitle)
			self.setSubtitlesEnable(True)

	def getCurrentServiceSubtitle(self):
		service = self.session.nav.getCurrentService()
		return service and service.subtitle()

	def setSubtitlesEnable(self, enable=True):
		subtitle = self.getCurrentServiceSubtitle()
		if enable:
			if self.__selected_subtitle:
				if subtitle and not self.__subtitles_enabled:
					subtitle.enableSubtitles(self.subtitle_window.instance, self.selected_subtitle)
					self.subtitle_window.show()
					self.__subtitles_enabled = True
		else:
			if subtitle and self.__subtitles_enabled:
				subtitle.disableSubtitles(self.subtitle_window.instance)
			self.__selected_subtitle = False
			self.__subtitles_enabled = False
			self.subtitle_window.hide()

	def setSelectedSubtitle(self, subtitle):
		self.__selected_subtitle = subtitle

	subtitles_enabled = property(lambda self: self.__subtitles_enabled, setSubtitlesEnable)
	selected_subtitle = property(lambda self: self.__selected_subtitle, setSelectedSubtitle)

class InfoBarServiceErrorPopupSupport:
	def __init__(self):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evTuneFailed: self.__tuneFailed,
				iPlayableService.evStart: self.__serviceStarted
			})
		self.__serviceStarted()

	def __serviceStarted(self):
		self.last_error = None
		Notifications.RemovePopup(id = "ZapError")

	def __tuneFailed(self):
		if not config.usage.hide_zap_errors.value:
			service = self.session.nav.getCurrentService()
			info = service and service.info()
			error = info and info.getInfo(iServiceInformation.sDVBState)

			if error == self.last_error:
				error = None
			else:
				self.last_error = error

			error = {
				eDVBServicePMTHandler.eventNoResources: _("No free tuner!"),
				eDVBServicePMTHandler.eventTuneFailed: _("Tune failed!"),
				eDVBServicePMTHandler.eventNoPAT: _("No data on transponder!\n(Timeout reading PAT)"),
				eDVBServicePMTHandler.eventNoPATEntry: _("Service not found!\n(SID not found in PAT)"),
				eDVBServicePMTHandler.eventNoPMT: _("Service invalid!\n(Timeout reading PMT)"),
				eDVBServicePMTHandler.eventNewProgramInfo: None,
				eDVBServicePMTHandler.eventTuned: None,
				eDVBServicePMTHandler.eventSOF: None,
				eDVBServicePMTHandler.eventEOF: None,
				eDVBServicePMTHandler.eventMisconfiguration: _("Service unavailable!\nCheck tuner configuration!"),
			}.get(error) #this returns None when the key not exist in the dict

			if error is not None:
				Notifications.AddPopup(text = error, type = MessageBox.TYPE_ERROR, timeout = 5, id = "ZapError")
			else:
				Notifications.RemovePopup(id = "ZapError")

class InfoBarZoom:
	def __init__(self):
		self.zoomrate=0
		self.zoomin=1

		self["ZoomActions"] = HelpableActionMap(self, "InfobarZoomActions",
			{
				"ZoomInOut":(self.ZoomInOut, _("Zoom In/Out TV...")),
				"ZoomOff":(self.ZoomOff, _("Zoom Off...")),
			}, prio=2)

	def ZoomInOut(self):
		zoomval=0
		if self.zoomrate > 3:
			self.zoomin = 0
		elif self.zoomrate < -9:
			self.zoomin = 1

		if self.zoomin == 1:
			self.zoomrate += 1
		else:
			self.zoomrate -= 1

		if self.zoomrate < 0:
		    zoomval=abs(self.zoomrate)+10
		else:
		    zoomval=self.zoomrate
		print "zoomRate:", self.zoomrate
		print "zoomval:", zoomval
		file = open("/proc/stb/vmpeg/0/zoomrate", "w")
		file.write('%d' % int(zoomval))
		file.close()

	def ZoomOff(self):
		self.zoomrate = 0
		self.zoomin = 1
		open("/proc/stb/vmpeg/0/zoomrate", "w").write(str(0))



###################################
###   PTS CopyTimeshift Task    ###
###################################

class CopyTimeshiftJob(Job):
	def __init__(self, toolbox, cmdline, srcfile, destfile, eventname):
		Job.__init__(self, _("Saving Timeshift files"))
		self.toolbox = toolbox
		AddCopyTimeshiftTask(self, cmdline, srcfile, destfile, eventname)

class AddCopyTimeshiftTask(Task):
	def __init__(self, job, cmdline, srcfile, destfile, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)
		self.srcfile = config.usage.timeshift_path.value + srcfile + ".copy"
		self.destfile = destfile + ".ts"

		self.ProgressTimer = eTimer()
		self.ProgressTimer.callback.append(self.ProgressUpdate)

	def ProgressUpdate(self):
		if self.srcsize <= 0 or not Directories.fileExists(self.destfile, 'r'):
			return

		self.setProgress(int((os_path.getsize(self.destfile)/float(self.srcsize))*100))
		self.ProgressTimer.start(15000, True)

	def prepare(self):
		if Directories.fileExists(self.srcfile, 'r'):
			self.srcsize = os_path.getsize(self.srcfile)
			self.ProgressTimer.start(15000, True)

		self.toolbox.ptsFrontpanelActions("start")

	def afterRun(self):
		self.setProgress(100)
		self.ProgressTimer.stop()
		self.toolbox.ptsCopyFilefinished(self.srcfile, self.destfile)
		config.timeshift.isRecording.value = True

###################################
###   PTS MergeTimeshift Task   ###
###################################

class MergeTimeshiftJob(Job):
	def __init__(self, toolbox, cmdline, srcfile, destfile, eventname):
		Job.__init__(self, _("Merging Timeshift files"))
		self.toolbox = toolbox
		AddMergeTimeshiftTask(self, cmdline, srcfile, destfile, eventname)

class AddMergeTimeshiftTask(Task):
	def __init__(self, job, cmdline, srcfile, destfile, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)
		self.srcfile = config.usage.default_path.value + srcfile
		self.destfile = config.usage.default_path.value + destfile

		self.ProgressTimer = eTimer()
		self.ProgressTimer.callback.append(self.ProgressUpdate)

	def ProgressUpdate(self):
		if self.srcsize <= 0 or not Directories.fileExists(self.destfile, 'r'):
			return

		self.setProgress(int((os_path.getsize(self.destfile)/float(self.srcsize))*100))
		self.ProgressTimer.start(7500, True)

	def prepare(self):
		if Directories.fileExists(self.srcfile, 'r') and Directories.fileExists(self.destfile, 'r'):
			fsize1 = os_path.getsize(self.srcfile)
			fsize2 = os_path.getsize(self.destfile)
			self.srcsize = fsize1 + fsize2
			self.ProgressTimer.start(7500, True)

		self.toolbox.ptsFrontpanelActions("start")

	def afterRun(self):
		self.setProgress(100)
		self.ProgressTimer.stop()
		config.timeshift.isRecording.value = True
		self.toolbox.ptsMergeFilefinished(self.srcfile, self.destfile)

##################################
###   Create APSC Files Task   ###
##################################

class CreateAPSCFilesJob(Job):
	def __init__(self, toolbox, cmdline, eventname):
		Job.__init__(self, _("Creating AP and SC Files"))
		self.toolbox = toolbox
		CreateAPSCFilesTask(self, cmdline, eventname)

class CreateAPSCFilesTask(Task):
	def __init__(self, job, cmdline, eventname):
		Task.__init__(self, job, eventname)
		self.toolbox = job.toolbox
		self.setCmdline(cmdline)

	def prepare(self):
		self.toolbox.ptsFrontpanelActions("start")
		config.timeshift.isRecording.value = True

	def afterRun(self):
		self.setProgress(100)
		self.toolbox.ptsSaveTimeshiftFinished()
