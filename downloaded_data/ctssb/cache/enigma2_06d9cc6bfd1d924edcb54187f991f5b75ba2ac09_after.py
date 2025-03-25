from Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.ActionMap import ActionMap, NumberActionMap, HelpableActionMap
from Components.Button import Button
from Components.config import config, configfile, ConfigClock, getConfigListEntry
from Components.ConfigList import ConfigListScreen
from Components.EpgList import EPGList, TimelineText, getPiconName, EPG_TYPE_SINGLE, EPG_TYPE_SIMILAR, EPG_TYPE_MULTI, EPG_TYPE_ENHANCED, EPG_TYPE_INFOBAR, EPG_TYPE_GRAPH, MAX_TIMELINES, days, dayslong
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.Event import Event
from Components.Sources.StaticText import StaticText
from Components.Sources.Boolean import Boolean
from Components.UsageConfig import preferredTimerPath
from Screens.TimerEdit import TimerSanityConflict
from Screens.EventView import EventViewSimple
from Screens.MessageBox import MessageBox
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
# from Tools.LoadPixmap import LoadPixmap
from TimeDateInput import TimeDateInput
from enigma import eServiceReference, eTimer, eServiceCenter
from RecordTimer import RecordTimerEntry, parseEvent, AFTEREVENT
from TimerEntry import TimerEntry
from ServiceReference import ServiceReference
from time import time, localtime, mktime

mepg_config_initialized = False
try:
	from Plugins.Extensions.AutoTimer.AutoTimerEditor import addAutotimerFromEvent
	BlueText = _("Add AutoTimer")
except:
	BlueText = _("Toggle Sort")

class EPGSelection(Screen, HelpableScreen):
	data = resolveFilename(SCOPE_CURRENT_SKIN,"skin.xml")
	data = data.replace('/ skin.xml','/skin.xml')
	data = file(resolveFilename(SCOPE_CURRENT_SKIN,"skin.xml")).read()
	if data.find('xres="1280"') >= 0:
		QuickEPG = """
			<screen name="QuickEPG" position="0,505" size="1280,215" backgroundColor="transparent" flags="wfNoBorder">
				<ePixmap alphatest="off" pixmap="DMConcinnity-HD/infobar-hd.png" position="0,0" size="1280,220" zPosition="0"/>
				<widget source="Service" render="Picon" position="60,75" size="100,60" transparent="1" zPosition="2" alphatest="blend">
					<convert type="ServiceName">Reference</convert>
				</widget>
				<widget source="Service" render="Label" position="0,42" size="1280,36" font="Regular;26" valign="top" halign="center" noWrap="1" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" zPosition="2" >
					<convert type="ServiceName">Name</convert>
				</widget>
				<widget name="list" position="340,80" size="640,54" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" itemHeight="27" zPosition="2"/>
				<ePixmap pixmap="DMConcinnity-HD/buttons/red.png" position="260,160" size="25,25" alphatest="blend" />
				<widget name="key_red" position="300,164" zPosition="1" size="130,20" font="Regular; 20" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/green.png" position="450,160" size="25,25" alphatest="blend" />
				<widget name="key_green" position="490,164" zPosition="1" size="130,20" font="Regular; 20" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/yellow.png" position="640,160" size="25,25" alphatest="blend" />
				<widget name="key_yellow" position="680,164" zPosition="1" size="130,20" font="Regular; 20" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/blue.png" position="830,160" size="25,25" alphatest="blend" />
				<widget name="key_blue" position="870,164" zPosition="1" size="150,20" font="Regular; 20" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" />
			</screen>"""
		GraphEPG = """
			<screen name="GraphicalEPG" position="center,center" size="1280,720" backgroundColor="#000000" >
				<eLabel text="Programme Guide" position="460,20" size="480,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="center" transparent="1" />
				<widget source="global.CurrentTime" render="Label" position="283, 20" size="90,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget source="global.CurrentTime" render="Label" position="1070, 20" size="160,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Format:%d.%m.%Y</convert>
				</widget>
				<widget name="lab1" position="0,90" size="1280,480" font="Regular;24" halign="center" valign="center" backgroundColor="#000000" transparent="0" zPosition="2" />
				<widget name="timeline_text" position="9, 60" size="1230,30" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1"/>
				<widget name="list" position="40,90" size="1200, 480" scrollbarMode="showNever" transparent="1" />
				<widget name="timeline0" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />
				<widget name="timeline1" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />
				<widget name="timeline2" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />
				<widget name="timeline3" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />
				<widget name="timeline4" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />
				<widget name="timeline5" position="0,90" zPosition="2" size="2,480" pixmap="skin_default/timeline.png" />

				<widget name="timeline_now" position="0, 90" zPosition="2" size="19, 480" pixmap="/usr/share/enigma2/skin_default/GraphEPG/timeline-now.png" alphatest="on" />
				<widget source="Event" render="Label" position="5, 575" size="100, 30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="EventTime">StartTime</convert>
					<convert type="ClockToText" />
				</widget>
				<widget source="Event" render="Label" position="113, 575" size="100, 30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="left" transparent="1">
					<convert type="EventTime">EndTime</convert>
					<convert type="ClockToText">Format:- %H:%M</convert>
				</widget>
				<widget source="Event" render="Label" position="230,575" size="1010,30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" halign="left">
					<convert type="EventName">Name</convert>
				</widget>
				<widget source="Event" render="Label" position="40, 605" zPosition="1" size="1200, 73" font="Regular;20" foregroundColor="#00dddddd" backgroundColor="#000000" shadowColor="#000000" transparent="1">
					<convert type="EventName">ExtendedDescription</convert>
				</widget>
					<ePixmap pixmap="skin_default/buttons/red.png" position="270, 675" size="25,25" alphatest="blend" />
				<widget name="key_red" position="305, 679" size="150, 24" font="Regular;20" foregroundColor="#9F1313" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
					<ePixmap pixmap="skin_default/buttons/green.png" position="460, 675" size="25,25" alphatest="blend" />
				<widget name="key_green" position="495, 679" size="150, 24" font="Regular;20" foregroundColor="#00389416" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
					<ePixmap pixmap="skin_default/buttons/yellow.png" position="670, 675" size="25,25" alphatest="blend" />
				<widget name="key_yellow" position="705, 679" size="150, 24" font="Regular;20" foregroundColor="#B59E01" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
					<ePixmap pixmap="skin_default/buttons/blue.png" position="860, 675" size="25,25" alphatest="blend" />
				<widget name="key_blue" position="895, 679" size="150, 24" font="Regular;20" foregroundColor="#1E28B6" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
			</screen>"""
		GraphEPGPIG = """
			<screen name="GraphicalEPGPIG" position="center,center" size="1280,720" backgroundColor="#000000" flags="wfNoBorder">
				<eLabel text="Programme Guide" position="460,20" size="480,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="center" transparent="1" />
				<widget source="global.CurrentTime" render="Label" position="283, 20" size="90,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget source="global.CurrentTime" render="Label" position="1070, 20" size="160,30" font="Regular;26" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Format:%d.%m.%Y</convert>
				</widget>
				<eLabel position="858,60" size="382,215" zPosition="2" backgroundColor="#000000" foregroundColor="#000000" />
				<widget source="session.VideoPicture" render="Pig" position="860,62" size="378,211" zPosition="3" backgroundColor="#ff000000" />
				<widget source="Event" render="Label" position="5,60" size="100, 30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="EventTime">StartTime</convert>
					<convert type="ClockToText" />
				</widget>
				<widget source="Event" render="Label" position="113,60" size="100, 30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="left" transparent="1">
					<convert type="EventTime">EndTime</convert>
					<convert type="ClockToText">Format:- %H:%M</convert>
				</widget>
				<widget source="Event" render="Label" position="230,60" size="600,30" font="Regular;26" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" halign="left">
					<convert type="EventName">Name</convert>
				</widget>
				<widget source="Event" render="Label" position="40,90" zPosition="1" size="790,185" font="Regular;20" foregroundColor="#00dddddd" backgroundColor="#000000" shadowColor="#000000" transparent="1" valign="top">
					<convert type="EventName">ExtendedDescription</convert>
				</widget>
				<widget name="lab1" position="40,320" size="1200,350" font="Regular;24" halign="center" valign="center" backgroundColor="#000000" transparent="0" zPosition="2" />
				<widget name="timeline_text" position="9,290" size="1230,30" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" />
				<widget name="list" position="40,320" size="1200,350" scrollbarMode="showNever" transparent="1" />
				<widget name="timeline0" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline1" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline2" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline3" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline4" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline5" position="0,320" zPosition="1" size="2,350" pixmap="skin_default/timeline.png" />
				<widget name="timeline_now" position="0,320" zPosition="2" size="19,350" pixmap="/usr/share/enigma2/skin_default/GraphEPG/timeline-now.png" alphatest="on" />
				<ePixmap pixmap="skin_default/buttons/red.png" position="270, 675" size="25,25" alphatest="blend" />
				<widget name="key_red" position="305, 679" size="150, 24" font="Regular;20" foregroundColor="#9F1313" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/green.png" position="460, 675" size="25,25" alphatest="blend" />
				<widget name="key_green" position="495, 679" size="150, 24" font="Regular;20" foregroundColor="#00389416" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/yellow.png" position="670, 675" size="25,25" alphatest="blend" />
				<widget name="key_yellow" position="705, 679" size="150, 24" font="Regular;20" foregroundColor="#B59E01" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/blue.png" position="860, 675" size="25,25" alphatest="blend" />
				<widget name="key_blue" position="895, 679" size="150, 24" font="Regular;20" foregroundColor="#1E28B6" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
			</screen>"""

	else:
		QuickEPG = """
			<screen name="QuickEPG" position="0,325" size="720,276" backgroundColor="transparent" flags="wfNoBorder" >
				<ePixmap alphatest="off" pixmap="DMConcinnity-HD/infobar.png" position="0,0" size="720,156" zPosition="1"/>
				<eLabel backgroundColor="#41080808" position="0,156" size="720,110" zPosition="2"/>
				<widget borderColor="#0f0f0f" borderWidth="1" backgroundColor="#16000000" font="Enigma;24" foregroundColor="#00f0f0f0" halign="left" noWrap="1" position="88,120" render="Label" size="68,28" source="global.CurrentTime" transparent="1" zPosition="3">
					<convert type="ClockToText">Default</convert>
				</widget>		
				<widget borderColor="#0f0f0f" borderWidth="1" backgroundColor="#16000000" font="Enigma;16" noWrap="1" position="54,100" render="Label" size="220,22" source="global.CurrentTime" transparent="1" valign="bottom" zPosition="3">
					<convert type="ClockToText">Date</convert>
				</widget>
				<widget source="Service" render="Picon" position="50,150" size="100,60" transparent="1" zPosition="4" alphatest="blend">
					<convert type="ServiceName">Reference</convert>
				</widget>
				<widget source="Service" render="Label" borderColor="#0f0f0f" borderWidth="1" backgroundColor="#16000000" font="Enigma;24" foregroundColor="#00f0f0f0" halign="center" position="160,120" size="400,28" transparent="1" valign="bottom" zPosition="3" >
					<convert type="ServiceName">Name</convert>
				</widget>
				<widget name="list" position="160,160" size="500,45" backgroundColor="#41080808" foregroundColor="#cccccc" transparent="1" itemHeight="22" zPosition="4"/>
				<ePixmap pixmap="DMConcinnity-HD/buttons/red.png" position="80,210" size="25,25" alphatest="blend" zPosition="4" />
				<widget name="key_red" position="110,213" size="100,20" font="Regular; 17" halign="left" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" zPosition="4" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/green.png" position="210,210" size="25,25" alphatest="blend" zPosition="4" />
				<widget name="key_green" position="240,213" size="100,20" font="Regular; 17" halign="left" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" zPosition="4" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/yellow.png" position="340,210" size="25,25" alphatest="blend" zPosition="4" />
				<widget name="key_yellow" position="370,213" size="100,20" font="Regular; 17" halign="left" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" zPosition="4" />
				<ePixmap pixmap="DMConcinnity-HD/buttons/blue.png" position="470,210" size="25,25" alphatest="blend" zPosition="4" />
				<widget name="key_blue" position="500,213" size="150,20" font="Regular; 17" halign="left" backgroundColor="#101214" foregroundColor="#cccccc" transparent="1" zPosition="4" />
			</screen>"""
		GraphEPG = """
			<screen name="GraphicalEPG" position="center,center" size="720,576" backgroundColor="#000000" >
				<widget source="Title" render="Label" position="200,18" size="380,28" font="Regular;22" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="center" transparent="1" />
				<widget source="global.CurrentTime" render="Label" position="140, 18" size="90,24" font="Regular;20" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
						<convert type="ClockToText">Default</convert>
				</widget>
				<widget source="global.CurrentTime" render="Label" position="525, 18" size="160,24" font="Regular;20" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Format:%d.%m.%Y</convert>
				</widget>
				<widget name="timeline_text" position="10, 40" size="690,25" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1"/>
				<widget name="lab1" position="25,65" size="665,378" font="Regular;24" halign="center" valign="center" backgroundColor="#000000" transparent="0" zPosition="2" />
				<widget name="list" position="25,65" size="665,378" scrollbarMode="showNever" transparent="1" />
				<widget name="timeline0" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline1" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline2" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline3" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline4" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline5" position="0,140" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline_now" position="10, 65" zPosition="2" size="19, 378" pixmap="/usr/share/enigma2/skin_default/GraphEPG/timeline-now.png" alphatest="on" />
				<widget source="Event" render="Label" position="10,445" size="70,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="EventTime">StartTime</convert>
					<convert type="ClockToText" />
				</widget>
				<widget source="Event" render="Label" position="88,445" size="80,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="left" transparent="1">
					<convert type="EventTime">EndTime</convert>
					<convert type="ClockToText">Format:- %H:%M</convert>
				</widget>
				<widget source="Event" render="Label" position="165,445" size="535,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" halign="left">
					<convert type="EventName">Name</convert>
				</widget>
				<widget source="Event" render="Label" position="30, 465" zPosition="1" size="667, 75" font="Regular;18" foregroundColor="#00dddddd" backgroundColor="#000000" shadowColor="#000000" transparent="1">
					<convert type="EventName">ExtendedDescription</convert>
				</widget>
				<ePixmap pixmap="skin_default/buttons/red.png" position="70, 537" size="18,18" alphatest="blend" />
				<widget name="key_red" position="95, 539" size="125, 26" font="Regular;18" foregroundColor="#9F1313" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/green.png" position="220, 537" size="18,18" alphatest="blend" />
				<widget name="key_green" position="245, 539" size="125, 26" font="Regular;18" foregroundColor="#00389416" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/yellow.png" position="370, 537" size="18,18" alphatest="blend" />
				<widget name="key_yellow" position="395, 539" size="125, 26" font="Regular;18" foregroundColor="#B59E01" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/blue.png" position="520, 537" size="18,18" alphatest="blend" />
				<widget name="key_blue" position="545, 539" size="125, 26" font="Regular;18" foregroundColor="#1E28B6" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
			</screen>
			"""
		GraphEPGPIG = """
			<screen name="GraphicalEPG" position="center,center" size="720,576" backgroundColor="#000000" flags="wfNoBorder">
				<widget source="Title" render="Label" position="200,18" size="380,28" font="Regular;22" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="center" transparent="1" />
				<widget source="global.CurrentTime" render="Label" position="140, 18" size="90,24" font="Regular;20" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget source="global.CurrentTime" render="Label" position="525, 18" size="160,24" font="Regular;20" foregroundColor="#FFFFFF" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="ClockToText">Format:%d.%m.%Y</convert>
				</widget>
				<widget source="Event" render="Label" position="10,47" size="70,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="right" transparent="1">
					<convert type="EventTime">StartTime</convert>
					<convert type="ClockToText" />
				</widget>
				<widget source="Event" render="Label" position="88,47" size="80,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" shadowColor="#000000" halign="left" transparent="1">
					<convert type="EventTime">EndTime</convert>
					<convert type="ClockToText">Format:- %H:%M</convert>
				</widget>
				<widget source="Event" render="Label" position="165,47" size="535,26" font="Regular;22" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" halign="left">
					<convert type="EventName">Name</convert>
				</widget>
				<widget source="Event" render="Label" position="30,73" zPosition="1" size="375,125" font="Regular;18" foregroundColor="#00dddddd" backgroundColor="#000000" shadowColor="#000000" transparent="1" valign="top">
					<convert type="EventName">ExtendedDescription</convert>
				</widget>
				<eLabel position="413,45" size="273,154" zPosition="2" backgroundColor="#000000" foregroundColor="#000000" />
				<widget name="lab1" position="25,235" size="665,278" font="Regular;24" halign="center" valign="center" backgroundColor="#000000" transparent="0" zPosition="2" />
				<widget source="session.VideoPicture" render="Pig" position="415,47" size="269,150" zPosition="3" backgroundColor="#ff000000" />
				<widget name="timeline_text" position="10,210" size="690,25" foregroundColor="#00e5b243" backgroundColor="#000000" transparent="1" />
				<widget name="list" position="25,235" size="665,278" scrollbarMode="showNever" transparent="1" />
				<widget name="timeline0" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline1" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline2" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline3" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline4" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline5" position="0,235" zPosition="1" size="0,0" pixmap="skin_default/timeline.png" />
				<widget name="timeline_now" position="10,235" zPosition="2" size="19,278" pixmap="/usr/share/enigma2/skin_default/GraphEPG/timeline-now.png" alphatest="on" />
				<ePixmap pixmap="skin_default/buttons/red.png" position="70, 537" size="18,18" alphatest="blend" />
				<widget name="key_red" position="95, 539" size="125, 26" font="Regular;18" foregroundColor="#9F1313" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/green.png" position="220, 537" size="18,18" alphatest="blend" />
				<widget name="key_green" position="245, 539" size="125, 26" font="Regular;18" foregroundColor="#00389416" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/yellow.png" position="370, 537" size="18,18" alphatest="blend" />
				<widget name="key_yellow" position="395, 539" size="125, 26" font="Regular;18" foregroundColor="#B59E01" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
				<ePixmap pixmap="skin_default/buttons/blue.png" position="520, 537" size="18,18" alphatest="blend" />
				<widget name="key_blue" position="545, 539" size="125, 26" font="Regular;18" foregroundColor="#1E28B6" backgroundColor="#000000" shadowColor="#000000" halign="left" valign="top" transparent="1" />
			</screen>"""
	EMPTY = 0
	ADD_TIMER = 1
	REMOVE_TIMER = 2
	
	ZAP = 1

	def __init__(self, session, service, zapFunc=None, eventid=None, bouquetChangeCB=None, serviceChangeCB=None, EPGtype = None,  bouquetname=""):
		Screen.__init__(self, session)
		if EPGtype:
			self.StartBouquet = EPGtype
			EPGtype = None
		if zapFunc == 'infobar':
			self.InfobarEPG = True
			zapFunc = None
		else:
			self.InfobarEPG = False
		if serviceChangeCB == 'graph':
			self.GraphicalEPG = True
			serviceChangeCB = None
		else:
			self.GraphicalEPG = False
		self.bouquetChangeCB = bouquetChangeCB
		self.serviceChangeCB = serviceChangeCB
		self.ask_time = -1 #now
		self.closeRecursive = False
		self["Service"] = ServiceEvent()
		self["Event"] = Event()
		Screen.setTitle(self, _("Programme Guide"))
		self.key_red_choice = self.EMPTY
		self.key_green_choice = self.EMPTY
		self["key_red"] = Button(_("IMDb Search"))
		self["key_green"] = Button(_("Add Timer"))
		self["key_yellow"] = Button(_("EPG Search"))
		self["key_blue"] = Button(BlueText)
		if isinstance(service, str) and eventid != None:
			self.type = EPG_TYPE_SIMILAR
			self.currentService=service
			self.eventid = eventid
			self.zapFunc = None
		elif isinstance(service, list):
			if self.GraphicalEPG:
				self.type = EPG_TYPE_GRAPH
				if not config.epgselction.pictureingraphics.value:
					self.skin = self.GraphEPG
					self.skinName = "GraphicalEPG"
				else:
					self.skin = self.GraphEPGPIG
					self.skinName = "GraphicalEPGPIG"
				now = time() - int(config.epg.histminutes.getValue()) * 60
				self.ask_time = self.ask_time = now - now % (int(config.epgselction.roundTo.getValue()) * 60)
				self.closeRecursive = False
				self['lab1'] = Label(_('Wait please while gathering data...'))
				self["timeline_text"] = TimelineText()
				self["Event"] = Event()
				self.time_lines = [ ]
				for x in range(0, MAX_TIMELINES):
					pm = Pixmap()
					self.time_lines.append(pm)
					self["timeline%d"%(x)] = pm
				self["timeline_now"] = Pixmap()
				self.services = service
				self.zapFunc = zapFunc
			else:
				self.type = EPG_TYPE_MULTI
				self.skinName = "EPGSelectionMulti"
				self["now_button"] = Pixmap()
				self["next_button"] = Pixmap()
				self["more_button"] = Pixmap()
				self["now_button_sel"] = Pixmap()
				self["next_button_sel"] = Pixmap()
				self["more_button_sel"] = Pixmap()
				self["now_text"] = Label()
				self["next_text"] = Label()
				self["more_text"] = Label()
				self["date"] = Label()
				self.services = service
				self.zapFunc = zapFunc

		elif isinstance(service, eServiceReference) or isinstance(service, str):
			self.type = EPG_TYPE_SINGLE
			self.currentService=ServiceReference(service)
			self.zapFunc = None
		else:
			if self.InfobarEPG:
				self.type = EPG_TYPE_INFOBAR
				self.skin = self.QuickEPG
				self.skinName = "QuickEPG"
			else:
				self.type = EPG_TYPE_ENHANCED
			self.list = []
			self.servicelist = service
			self.currentService=self.session.nav.getCurrentlyPlayingServiceReference()
			self.zapFunc = None

		self["list"] = EPGList(type = self.type, selChangedCB = self.onSelectionChanged, timer = session.nav.RecordTimer, time_epoch = config.epgselction.prev_time_period.getValue(), overjump_empty = config.epgselction.overjump.value)

		HelpableScreen.__init__(self)
		self["okactions"] = HelpableActionMap(self, "OkCancelActions",
			{
				"cancel": (self.closing, _("Exit EPG")),
				"OK":     (self.OK, _("Zap to channel (setup in menu)")),
				"OKLong": (self.OKLong, _("Zap to channel and close (setup in menu)")),
			}, -1)
		self["okactions"].csel = self

		self["colouractions"] = HelpableActionMap(self, "ColorActions",
			{
				"red":				(self.redButtonPressed, _("IMDB serach for current event")),
				"greenlong":		(self.showTimerList, _("Show Timer List")),
				"yellow":			(self.yellowButtonPressed, _("Search for similar events")),
				"blue":				(self.blueButtonPressed, _("Add a auto timer for current event")),
				"bluelong":			(self.showAutoTimerList, _("Show AutoTimer List")),
			},-1)
		self["colouractions"].csel = self

		self["addtimer"] = HelpableActionMap(self, "EPGSelectActions",
			{
				"timerAdd":			(self.timerAdd, _("Add/Remove timer for current event")),
			},-1)
		self["addtimer"].csel = self

		self["recordingactions"] = HelpableActionMap(self, "InfobarInstantRecord",
			{
				"ShortRecord":		(self.doRecordTimer, _("Add a record timer for current event")),
				"LongRecord":		(self.doZapTimer, _("Add a zap timer for current event")),
			},-1)
		self["recordingactions"].csel = self

		if  self.type == EPG_TYPE_INFOBAR:
			self["epgactions"] = HelpableActionMap(self, "EPGSelectActions",
				{
					"nextBouquet":		(self.nextBouquet, _("Goto next bouquet")),
					"prevBouquet":		(self.prevBouquet, _("Goto previous bouquet")),
					"nextService":		(self.nextPage, _("Move down a page")),
					"prevService":		(self.prevPage, _("Move up a page")),
					"input_date_time":	(self.enterDateTime, _("Goto specific data/time")),
					"Info":				(self.Info, _("Show detailed event info")),
					"InfoLong":			(self.InfoLong, _("Show single epg for current channel")),
					"Menu":				(self.createSetup, _("Setup menu")),
				},-1)
			self["epgactions"].csel = self

			self["cursoractions"] = HelpableActionMap(self, "DirectionActions",
				{
					"left":		(self.prevService, _("Goto previous channel")),
					"right":	(self.nextService, _("Goto next channel")),
					"up":		(self.moveUp, _("Goto previous channel")),
					"down":		(self.moveDown, _("Goto next channel")),
				},-1)
			self["cursoractions"].csel = self

			self["inputactions"] = NumberActionMap(["NumberActions"],
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
			}, -1)
			self["inputactions"].csel = self

		elif self.type == EPG_TYPE_ENHANCED:
			self["epgactions"] = HelpableActionMap(self, "EPGSelectActions",
				{
					"nextBouquet":		(self.nextBouquet, _("Goto next bouquet")),
					"prevBouquet":		(self.prevBouquet, _("Goto previous bouquet")),
					"nextService":		(self.nextService, _("Goto next channel")),
					"prevService": 		(self.prevService, _("Goto previous channel")),
					"input_date_time":	(self.enterDateTime, _("Goto specific data/time")),
					"Info":				(self.Info, _("Show detailed event info")),
					"InfoLong":			(self.InfoLong, _("Show single epg for current channel")),
					"Menu":				(self.createSetup, _("Setup menu")),
				},-1)
			self["epgactions"].csel = self

			self["cursoractions"] = HelpableActionMap(self, "DirectionActions",
				{
					"left":		(self.prevPage, _("Move up a page")),
					"right":	(self.nextPage, _("Move down a page")),
					"up":		(self.moveUp, _("Goto previous channel")),
					"down":		(self.moveDown, _("Goto next channel")),
				},-1)
			self["cursoractions"].csel = self
			self["inputactions"] = NumberActionMap(["NumberActions"],
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
			}, -1)
			self["inputactions"].csel = self

		elif self.type == EPG_TYPE_GRAPH:
			self["epgactions"] = HelpableActionMap(self, "EPGSelectActions",
				{
					"nextBouquet":		(self.nextService, _("Jump forward 24 hours")),
					"prevBouquet":		(self.prevService, _("Jump back 24 hours")),
					"prevService":		(self.Bouquetlist, _("Show bouquet selection menu")),
					"nextService": 		(self.Bouquetlist, _("Show bouquet selection menu")),
					"input_date_time":	(self.enterDateTime, _("Goto specific data/time")),
					"Info":				(self.Info, _("Show detailed event info")),
					"InfoLong":			(self.InfoLong, _("Show single epg for current channel")),
					"Menu":				(self.createSetup, _("Setup menu")),
				},-1)
			self["epgactions"].csel = self
			self["cursoractions"] = HelpableActionMap(self, "DirectionActions",
				{
					"left": 	(self.leftPressed, _("Goto previous event")),
					"right":	(self.rightPressed, _("Goto next event")),
					"up":		(self.moveUp, _("Goto previous channel")),
					"down":		(self.moveDown, _("Goto next channel")),
				},-1)
			self["cursoractions"].csel = self
			self["input_actions"] = HelpableActionMap(self, "NumberActions",
				{
					"1":		(self.key1, _("Reduce time scale")),
					"2":		(self.key2, _("Page up")),
					"3":		(self.key3, _("Increase time scale")),
					"4":		(self.key4, _("page left")),
					"5":		(self.key5, _("Jump to current time")),
					"6":		(self.key6, _("Page right")),
					"7":		(self.key7, _("No of items switch (increase or reduced)")),
					"8":		(self.key8, _("Page down")),
					"9":		(self.key9, _("Jump to prime time")),
					"0":		(self.key0, _("Move to home of list")),
				},-1)
			self["input_actions"].csel = self

		elif self.type == EPG_TYPE_MULTI:
			self["epgactions"] = HelpableActionMap(self, "EPGSelectActions",
				{
					"nextBouquet":		(self.Bouquetlist, _("Show bouquet selection menu")),
					"prevBouquet":		(self.Bouquetlist, _("Show bouquet selection menu")),
					"nextService":		(self.nextPage, _("Move down a page")),
					"prevService":		(self.prevPage, _("Move up a page")),
					"input_date_time":	(self.enterDateTime, _("Goto specific data/time")),
					"Info":				(self.Info, _("Show detailed event info")),
					"InfoLong":			(self.InfoLong, _("Show single epg for current channel")),
					"Menu":				(self.createSetup, _("Setup menu")),
				},-1)
			self["epgactions"].csel = self

			self["cursoractions"] = HelpableActionMap(self, "DirectionActions",
				{
					"left":		(self.leftPressed, _("Move up a page")),
					"right":	(self.rightPressed, _("Move down a page")),
					"up":		(self.moveUp, _("Goto previous channel")),
					"down":		(self.moveDown, _("Goto next channel")),
				},-1)
			self["cursoractions"].csel = self

		if self.type == EPG_TYPE_GRAPH:
			self.curBouquet = bouquetChangeCB
			self.updateTimelineTimer = eTimer()
			self.updateTimelineTimer.callback.append(self.moveTimeLines)
			self.updateTimelineTimer.start(60*1000)
			self.activityTimer = eTimer()
			self.activityTimer.timeout.get().append(self.onStartup)
			self.updateList()
		elif self.type == EPG_TYPE_MULTI:
			self.curBouquet = bouquetChangeCB
			self.onLayoutFinish.append(self.onStartup)
		else:
			self.onLayoutFinish.append(self.onStartup)

	def createSetup(self):
		self.session.openWithCallback(self.onSetupClose, EPGSelectionSetup, self.type)

	def onSetupClose(self):
		if self.type == EPG_TYPE_GRAPH:
			l = self["list"]
			l.setItemsPerPage()
			l.setEventFontsize()
			l.setServiceFontsize()
			self["timeline_text"].setTimeLineFontsize()
			l.setEpoch(config.epgselction.prev_time_period.getValue())
			l.setOverjump_Empty(config.epgselction.overjump.value)
			l.setShowPicon(config.epgselction.showpicon.value)
			l.setShowServiceTitle(config.epgselction.showservicetitle.value)
			now = time() - int(config.epg.histminutes.getValue()) * 60
			self.ask_time = now - now % (int(config.epgselction.roundTo.getValue()) * 60)
			l.fillGraphEPG(None, self.ask_time)
			self.moveTimeLines()
		else:
			if config.epgselction.sort.value == "Time":
				self.sort_type = 0
			else:
				self.sort_type = 1
			l = self["list"]
			l.setItemsPerPage()
			l.setEventFontsize()
			l.recalcEntrySize()
			l.sortSingleEPG(self.sort_type)

	def updateList(self):
		self.activityTimer.start(10)

	def onStartup(self):
		self.onCreate()
		if self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR:
			self.StartBouquet = self.servicelist.getRoot()
		self.StartRef = self.session.nav.getCurrentlyPlayingServiceReference()
		if self.type == EPG_TYPE_GRAPH:
			self['lab1'].hide()

	def onCreate(self):
		serviceref = self.session.nav.getCurrentlyPlayingServiceReference()
		l = self["list"]
		l.recalcEntrySize()
		if self.type == EPG_TYPE_GRAPH:
			self.activityTimer.stop()
			self.services = self.generateList(self.services)
			l.fillGraphEPG(self.services, self.ask_time)
			l.moveToService(serviceref)
			l.setCurrentlyPlaying(serviceref)
			l.setShowPicon(config.epgselction.showpicon.value)
			l.setShowServiceTitle(config.epgselction.showservicetitle.value)
			self.moveTimeLines()
			if config.epgselction.channel1.value:
				l.instance.moveSelectionTo(0)
			self.setTitle(ServiceReference(self.StartBouquet).getServiceName())
		elif self.type == EPG_TYPE_MULTI:
			l.fillMultiEPG(self.services, self.ask_time)
			l.moveToService(serviceref)
			l.setCurrentlyPlaying(serviceref)
			self.setTitle(ServiceReference(self.StartBouquet).getServiceName())
		elif self.type == EPG_TYPE_SINGLE:
			service = self.currentService
			self["Service"].newService(service.ref)
			title = service.getServiceName()
			self.setTitle(title)
			l.fillSingleEPG(service)
		elif self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR:
			service = ServiceReference(self.servicelist.getCurrentSelection())
			self["Service"].newService(service.ref)
			title = service.getServiceName()
			self.setTitle(title)
			l.fillSingleEPG(service)
		else:
			l.fillSimilarList(self.currentService, self.eventid)
		if self.type == EPG_TYPE_SINGLE or self.type == EPG_TYPE_ENHANCED:
			if config.epgselction.sort.value == "Time":
				self.sort_type = 0
			else:
				self.sort_type = 1
			l.sortSingleEPG(self.sort_type)

	def nextPage(self):
		self["list"].instance.moveSelection(self["list"].instance.pageDown)

	def prevPage(self):
		self["list"].instance.moveSelection(self["list"].instance.pageUp)

	def leftPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self["list"].updateMultiEPG(-1)
		else:
			self.updEvent(-1)

	def rightPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self["list"].updateMultiEPG(1)
		else:
			self.updEvent(+1)
		
	def nextBouquet(self):
		if (self.type == EPG_TYPE_MULTI or self.type == EPG_TYPE_GRAPH) and self.bouquetChangeCB:
			self.bouquetChangeCB(self)
		elif (self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR) and config.usage.multibouquet.value:
			self.servicelist.nextBouquet()
			self.onCreate()

	def prevBouquet(self):
		if (self.type == EPG_TYPE_MULTI or self.type == EPG_TYPE_GRAPH) and self.bouquetChangeCB:
			self.bouquetChangeCB(self)
		elif (self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR) and config.usage.multibouquet.value:
			self.servicelist.prevBouquet()
			self.onCreate()

	def Bouquetlist(self):
		if self.bouquetChangeCB:
			self.bouquetChangeCB(self)

	def nextService(self):
		if self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR:
			self["list"].instance.moveSelectionTo(0)
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
						if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
							break
			else:
				self.servicelist.moveDown()
			if self.isPlayable():
				self.onCreate()
				if not self["list"].getCurrent()[1] and config.epgselction.overjump.value:
					self.nextService()
			else:
				self.nextService()
		elif self.type == EPG_TYPE_GRAPH:
			coolhilf = config.epgselction.prev_time_period.getValue()
			if coolhilf == 60:
				for i in range(24):
					self.updEvent(+2)
			if coolhilf == 120:
				for i in range(12):
					self.updEvent(+2)
			if coolhilf == 180:
				for i in range(8):
					self.updEvent(+2)
			if coolhilf == 240:
				for i in range(6):
					self.updEvent(+2)
			if coolhilf == 300:
				for i in range(4):
					self.updEvent(+2)
		else:
			if self.serviceChangeCB:
				self.serviceChangeCB(1, self)

	def prevService(self):
		if self.type == EPG_TYPE_ENHANCED or self.type == EPG_TYPE_INFOBAR:
			self["list"].instance.moveSelectionTo(0)
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
						if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
							break
			else:
				self.servicelist.moveUp()
			if self.isPlayable():
				self.onCreate()
				if not self["list"].getCurrent()[1] and config.epgselction.overjump.value:
					self.prevService()
			else:
				self.prevService()
		elif self.type == EPG_TYPE_GRAPH:
			coolhilf = config.epgselction.prev_time_period.getValue()
			if coolhilf == 60:
				for i in range(24):
					self.updEvent(-2)
			if coolhilf == 120:
				for i in range(12):
					self.updEvent(-2)
			if coolhilf == 180:
				for i in range(8):
					self.updEvent(-2)
			if coolhilf == 240:
				for i in range(6):
					self.updEvent(-2)
			if coolhilf == 300:
				for i in range(4):
					self.updEvent(-2)
		else:
			if self.serviceChangeCB:
				self.serviceChangeCB(-1, self)

	def enterDateTime(self):
		if self.type == EPG_TYPE_MULTI:
			global mepg_config_initialized
			if not mepg_config_initialized:
				config.misc.prev_mepg_time=ConfigClock(default = time())
				mepg_config_initialized = True
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.epgselction.prev_time )
		elif self.type == EPG_TYPE_GRAPH:
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.epgselction.prev_time)

	def onDateTimeInputClosed(self, ret):
		if len(ret) > 1:
			if ret[0]:
				if self.type == EPG_TYPE_MULTI:
					self.ask_time=ret[1]
					self["list"].fillMultiEPG(self.services, ret[1])
				elif self.type == EPG_TYPE_GRAPH:
					now = time() - int(config.epg.histminutes.getValue()) * 60
					self.ask_time = self.ask_time - self.ask_time % (int(config.epgselction.roundTo.getValue()) * 60)
					l = self["list"]
					l.resetOffset()
					l.fillGraphEPG(None, self.ask_time)
					self.moveTimeLines(True)

	def closing(self):
		if (self.type == 5 and config.epgselction.preview_mode_pliepg.value) or (self.type == 4 and config.epgselction.preview_mode_infobar.value) or (self.type == 3 and config.epgselction.preview_mode_enhanced.value) or (self.type != 5 and self.type != 4 and self.type != 3 and config.epgselction.preview_mode.value):
			if self.type != EPG_TYPE_GRAPH and self.type != EPG_TYPE_MULTI:
				self.session.nav.playService(self.StartRef)
			else:
				self.zapFunc(self.StartRef, self.StartBouquet)
		if self.type != EPG_TYPE_GRAPH and self.type != EPG_TYPE_MULTI and self.type != EPG_TYPE_SINGLE:
			self.setServicelistSelection(self.StartBouquet, self.StartRef)
		self.close(self.closeRecursive)

	def GraphEPGClose(self):
		self.closeRecursive = True
		ref = self["list"].getCurrent()[1]
		if ref:
			self.closeScreen()		

	def closeScreen(self):
		if self.type == EPG_TYPE_GRAPH:
			config.epgselction.save()
		self.close(self.closeRecursive)

	def infoKeyPressed(self):
		cur = self["list"].getCurrent()
		event = cur[0]
		service = cur[1]
		if event is not None:
			if self.type != EPG_TYPE_SIMILAR:
				self.session.open(EventViewSimple, event, service, self.eventViewCallback, self.openSimilarList)
			else:
				self.session.open(EventViewSimple, event, service, self.eventViewCallback)

	def openSimilarList(self, eventid, refstr):
		self.session.open(EPGSelection, refstr, None, eventid)

	def setServices(self, services):
		self.services = services
		self.onCreate()

	def setService(self, service):
		self.currentService = service
		self.onCreate()

	def eventViewCallback(self, setEvent, setService, val):
		l = self["list"]
		old = l.getCurrent()
		if self.type == EPG_TYPE_GRAPH:
			self.updEvent(val, False)
		else:
			if val == -1:
				self.moveUp()
			elif val == +1:
				self.moveDown()
		cur = l.getCurrent()
		if (self.type == EPG_TYPE_MULTI or self.type == EPG_TYPE_GRAPH) and cur[0] is None and cur[1].ref != old[1].ref:
			self.eventViewCallback(setEvent, setService, val)
		else:
			setService(cur[1])
			setEvent(cur[0])

	def eventSelected(self):
		self.infoKeyPressed()

	def setSortDescription(self):
		if config.epgselction.sort.value == "Time":
			self.sort_type = 1
		else:
			self.sort_type = 0
		self["list"].sortSingleEPG(self.sort_type)

	def OpenSingleEPG(self):
		cur = self["list"].getCurrent()
		event = cur[0]
		serviceref = cur[1]
		refstr = serviceref.ref.toString()
		if event is not None:
			self.session.open(SingleEPG, refstr)		

	def redButtonPressed(self):
		try:
			from Plugins.Extensions.IMDb.plugin import IMDB, IMDBEPGSelection
			try:
				cur = self["list"].getCurrent()
				event = cur[0]
				name = event.getEventName()
			except:
				name = ''
			self.session.open(IMDB, name, False)
		except ImportError:
			self.session.open(MessageBox, _("The IMDb plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

	def yellowButtonPressed(self):
		try:
			from Plugins.Extensions.EPGSearch.EPGSearch import EPGSearch
			try:
				cur = self["list"].getCurrent()
				event = cur[0]
				name = event.getEventName()
			except:
				name = ''
			self.session.open(EPGSearch, name, False)
		except ImportError:
			self.session.open(MessageBox, _("The EPGSearch plugin is not installed!\nPlease install it."), type = MessageBox.TYPE_INFO,timeout = 10 )

	def blueButtonPressed(self):
		try:
			from Plugins.Extensions.AutoTimer.AutoTimerEditor import addAutotimerFromEvent
			cur = self["list"].getCurrent()
			event = cur[0]
			if not event: return
			serviceref = cur[1]
			addAutotimerFromEvent(self.session, evt = event, service = serviceref)
		except ImportError:
			if self.type == EPG_TYPE_SINGLE or self.type == EPG_TYPE_ENHANCED:
				if self.sort_type == 0:
					self.sort_type = 1
				else: 
					self.sort_type = 0
				self["list"].sortSingleEPG(self.sort_type)

	def showTimerList(self):
		from Screens.TimerEdit import TimerEditList
		self.session.open(TimerEditList)

	def showAutoTimerList(self):
		try:
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
		except ImportError:
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
	
	def removeTimer(self, timer):
		timer.afterEvent = AFTEREVENT.NONE
		self.session.nav.RecordTimer.removeEntry(timer)
		self["key_green"].setText(_("Add Timer"))
		self.key_green_choice = self.ADD_TIMER

	def timerAdd(self):
		cur = self["list"].getCurrent()
		event = cur[0]
		serviceref = cur[1]
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
			newEntry = RecordTimerEntry(serviceref, checkOldTimers = True, dirname = preferredTimerPath(), *parseEvent(event))
			self.session.openWithCallback(self.finishedAdd, TimerEntry, newEntry)

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
			self["key_green"].setText(_("Add Timer"))
			self.key_green_choice = self.ADD_TIMER
			print "Timeredit aborted"
	
	def finishSanityCorrection(self, answer):
		self.finishedAdd(answer)

	def doRecordTimer(self):
		zap = False
		cur = self["list"].getCurrent()
		event = cur[0]
		serviceref = cur[1]
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
			newEntry = RecordTimerEntry(serviceref, checkOldTimers = True, *parseEvent(event))
			self.session.openWithCallback(self.finishedAdd, RecordSetup, newEntry, zap)

	def doZapTimer(self):
		zap = True
		cur = self["list"].getCurrent()
		event = cur[0]
		serviceref = cur[1]
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
			newEntry = RecordTimerEntry(serviceref, checkOldTimers = True, *parseEvent(event))
			self.session.openWithCallback(self.finishedAdd, RecordSetup, newEntry, zap)

	def moveUp(self):
		self["list"].moveUp()
		if self.type == EPG_TYPE_GRAPH:
			self.moveTimeLines()

	def moveDown(self):
		self["list"].moveDown()
		if self.type == EPG_TYPE_GRAPH:
			self.moveTimeLines()

			
	def updEvent(self, dir, visible=True):
		ret = self["list"].selEntry(dir, visible)
		if ret:
			self.moveTimeLines(True)		

	def key1(self):
		hilf = config.epgselction.prev_time_period.getValue()	
		if hilf > 60:
			hilf = hilf - 60
			self["list"].setEpoch(hilf)
			config.epgselction.prev_time_period.setValue(hilf)
			self.moveTimeLines()

	def key2(self):
		self["list"].instance.moveSelection(self["list"].instance.pageUp)
		self.moveTimeLines()

	def key3(self):
		hilf = config.epgselction.prev_time_period.getValue()	
		if hilf < 300:
			hilf = hilf + 60
			self["list"].setEpoch(hilf)
			config.epgselction.prev_time_period.setValue(hilf)
			self.moveTimeLines()

	def key4(self):
		self.updEvent(-2)

	def key5(self):
		now = time() - int(config.epg.histminutes.getValue()) * 60
		self.ask_time = now - now % (int(config.epgselction.roundTo.getValue()) * 60)
		self["list"].resetOffset()
		self["list"].fillGraphEPG(None, self.ask_time)
		self.moveTimeLines(True)

	def key6(self):
		self.updEvent(+2)

	def key7(self):
		if config.epgselction.heightswitch.value:
			config.epgselction.heightswitch.setValue(False)
		else:
			config.epgselction.heightswitch.setValue(True)
		self["list"].setItemsPerPage()
		self["list"].fillGraphEPG(None)
		self.moveTimeLines()

	def key8(self):
		self["list"].instance.moveSelection(self["list"].instance.pageDown)
		self.moveTimeLines()

	def key9(self):
		cooltime = localtime(self["list"].getTimeBase())
		hilf = (cooltime[0], cooltime[1], cooltime[2], int(config.epgselction.primetimehour.getValue()), int(config.epgselction.primetimemins.getValue()),0, cooltime[6], cooltime[7], cooltime[8])
		cooltime = mktime(hilf)
		self["list"].resetOffset()
		self["list"].fillGraphEPG(None, cooltime)
		self.moveTimeLines(True)		

	def key0(self):
		self["list"].instance.moveSelectionTo(0)	
		now = time() - int(config.epg.histminutes.getValue()) * 60
		self.ask_time = now - now % (int(config.epgselction.roundTo.getValue()) * 60)
		self["list"].resetOffset()
		self["list"].fillGraphEPG(None, self.ask_time)
		self.moveTimeLines()

	def OK(self):
		if config.epgselction.OK_pliepg.value == "EventView" or config.epgselction.OK_enhanced.value == "EventView" or config.epgselction.OK_infobar.value == "EventView":
			self.infoKeyPressed()
		elif config.epgselction.OK_pliepg.value == "Zap" or config.epgselction.OK_enhanced.value == "Zap" or config.epgselction.OK_infobar.value == "Zap":
			self.ZapTo()
		elif config.epgselction.OK_pliepg.value == "Zap + Exit" or config.epgselction.OK_enhanced.value == "Zap + Exit" or config.epgselction.OK_infobar.value == "Zap + Exit":
			self.zap()

	def OKLong(self):
		if config.epgselction.OKLong_pliepg.value == "Zap" or config.epgselction.OKLong_enhanced.value == "Zap" or config.epgselction.OKLong_infobar.value == "Zap":
			self.ZapTo()
		if config.epgselction.OKLong_pliepg.value == "Zap + Exit" or config.epgselction.OKLong_enhanced.value == "Zap + Exit" or config.epgselction.OKLong_infobar.value == "Zap + Exit":
			self.zap()

	def Info(self):
		if config.epgselction.Info.value == "Channel Info":
			self.infoKeyPressed()
		if config.epgselction.Info.value == "Single EPG":
			self.OpenSingleEPG()

	def InfoLong(self):
		if config.epgselction.InfoLong.value == "Channel Info":
			self.infoKeyPressed()
		if config.epgselction.InfoLong.value == "Single EPG":
			self.OpenSingleEPG()

	def applyButtonState(self, state):
		if state == 0:
			self["now_button"].hide()
			self["now_button_sel"].hide()
			self["next_button"].hide()
			self["next_button_sel"].hide()
			self["more_button"].hide()
			self["more_button_sel"].hide()
			self["now_text"].hide()
			self["next_text"].hide()
			self["more_text"].hide()
			self["key_red"].setText("")
		else:
			if state == 1:
				self["now_button_sel"].show()
				self["now_button"].hide()
			else:
				self["now_button"].show()
				self["now_button_sel"].hide()

			if state == 2:
				self["next_button_sel"].show()
				self["next_button"].hide()
			else:
				self["next_button"].show()
				self["next_button_sel"].hide()

			if state == 3:
				self["more_button_sel"].show()
				self["more_button"].hide()
			else:
				self["more_button"].show()
				self["more_button_sel"].hide()

	def onSelectionChanged(self):
		cur = self["list"].getCurrent()
		if cur is None:
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			if self.key_red_choice != self.EMPTY:
				self["key_red"].setText("")
				self.key_red_choice = self.EMPTY
			return
		event = cur[0]
		self["Event"].newEvent(event)
		if self.type == EPG_TYPE_MULTI or self.type == EPG_TYPE_GRAPH:
			count = self["list"].getCurrentChangeCount()
			if self.type == EPG_TYPE_MULTI:
				if self.ask_time != -1:
					self.applyButtonState(0)
				elif count > 1:
					self.applyButtonState(3)
				elif count > 0:
					self.applyButtonState(2)
				else:
					self.applyButtonState(1)
				datestr = ""
				if event is not None:
					now = time()
					beg = event.getBeginTime()
					nowTime = localtime(now)
					begTime = localtime(beg)
					if nowTime[2] != begTime[2]:
							datestr = '%s'%(dayslong[begTime[6]])
					else:
							datestr = '%s'%(_("Today"))
				self["date"].setText(datestr)

			if cur[1] is None:
				self["Service"].newService(None)
			else:
				self["Service"].newService(cur[1].ref)

		if cur[1] is None or cur[1].getServiceName() == "":
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			if self.key_red_choice != self.EMPTY:
				self["key_red"].setText("")
				self.key_red_choice = self.EMPTY
			return

		if event is None:
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			return

		serviceref = cur[1]
		eventid = event.getEventId()
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
			self["key_green"].setText(_("Add Timer"))
			self.key_green_choice = self.ADD_TIMER

	def moveTimeLines(self, force=False):
		self.updateTimelineTimer.start((60 - (int(time()) % 60)) * 1000)        #keep syncronised
		self["timeline_text"].setEntries(self["list"], self["timeline_now"], self.time_lines)
		self["list"].l.invalidate() # not needed when the zPosition in the skin is correct! ?????
	
	def generateList(self, services):
		res = [ ]
		for service in services:
			res.append( (service, getPiconName(service.ref.toString())) )
		return res

	def isPlayable(self):
		# check if service is playable
		current = ServiceReference(self.servicelist.getCurrentSelection())
		return not (current.ref.flags & (eServiceReference.isMarker|eServiceReference.isDirectory))

	def setServicelistSelection(self, bouquet, service):
		# we need to select the old service with bouquet
		if self.servicelist.getRoot() != bouquet: #already in correct bouquet?
			self.servicelist.clearPath()
			self.servicelist.enterPath(self.servicelist.bouquet_root)
			self.servicelist.enterPath(bouquet)
		self.servicelist.setCurrentSelection(service) #select the service in servicelist

	def zap(self):
		if self.type == EPG_TYPE_GRAPH or self.type == EPG_TYPE_MULTI:
			if self.zapFunc :
				self.closeRecursive = True
				ref = self["list"].getCurrent()[1]
				if ref:
					self.zapFunc(ref.ref)
					self["list"].setCurrentlyPlaying(ref.ref)
					self["list"].l.invalidate()
					self.closeScreen()
				else:
					self.closeScreen()
		else:
			try:
				currch = self.session.nav.getCurrentlyPlayingServiceReference()
				currch = currch.toString()
				switchto = ServiceReference(self.servicelist.getCurrentSelection())
				switchto = str(switchto)
				if not switchto == currch:
					self.servicelist.zap()
					self.close()
				else:
					self.close()
			except:
				self.close()

	def ZapTo(self):
		if self.type == EPG_TYPE_GRAPH or self.type == EPG_TYPE_MULTI:
			if self.zapFunc:
				currch = self.session.nav.getCurrentlyPlayingServiceReference()
				currch = currch.toString()
				ref = self["list"].getCurrent()[1]
				if self.type == EPG_TYPE_GRAPH:
					self["list"].curr_refcool = ref.ref
					self["list"].fillGraphEPG(None)
				switchto = ServiceReference(ref.ref)
				switchto = str(switchto)
				if not switchto == currch:
					if ref and switchto.find('alternatives') != -1:
						self.zapFunc(ref.ref)
						self.close(True)
					else:
						self.zapFunc(ref.ref)
				else:
					self.close(True)
		else:
			try:
				currch = self.session.nav.getCurrentlyPlayingServiceReference()
				currch = currch.toString()
				switchto = ServiceReference(self.servicelist.getCurrentSelection())
				switchto = str(switchto)
				if not switchto == currch:
					self.servicelist.zap()
				else:
					self.close()
			except:
				self.close()

	def keyNumberGlobal(self, number):
		from Screens.InfoBarGenerics import NumberZap
		self.session.openWithCallback(self.numberEntered, NumberZap, number)

	def numberEntered(self, retval):
		if retval > 0:
			self.zapToNumber(retval)

	def searchNumberHelper(self, serviceHandler, num, bouquet):
		servicelist = serviceHandler.list(bouquet)
		if not servicelist is None:
			while num:
				serviceIterator = servicelist.getNext()
				if not serviceIterator.valid(): #check end of list
					break
				playable = not (serviceIterator.flags & (eServiceReference.isMarker|eServiceReference.isDirectory))
				if playable:
					num -= 1;
			if not num: #found service with searched number ?
				return serviceIterator, 0
		return None, num

	def zapToNumber(self, number):
		bouquet = self.servicelist.bouquet_root
		service = None
		serviceHandler = eServiceCenter.getInstance()
		bouquetlist = serviceHandler.list(bouquet)
		if not bouquetlist is None:
			while number:
				bouquet = bouquetlist.getNext()
				if not bouquet.valid(): #check end of list
					break
				if bouquet.flags & eServiceReference.isDirectory:
					service, number = self.searchNumberHelper(serviceHandler, number, bouquet)
		if not service is None:
			self.setServicelistSelection(bouquet, service)
		self.onCreate()

	# ChannelSelection Support
# 	def prepareChannelSelectionDisplay(self):
# 		# save current ref and bouquet ( for cancel )
# 		self.curSelectedRef = eServiceReference(self.servicelist.getCurrentSelection().toString())
# 		self.curSelectedBouquet = self.servicelist.getRoot()
# 
# 	def cancelChannelSelection(self):
# 		# select service and bouquet selected before started ChannelSelection
# 		if self.servicelist.revertMode is None:
# 			ref = self.curSelectedRef
# 			bouquet = self.curSelectedBouquet
# 			if ref.valid() and bouquet.valid():
# 				# select bouquet and ref in servicelist
# 				self.setServicelistSelection(bouquet, ref)
# 		# close ChannelSelection
# 		self.servicelist.revertMode = None
# 		self.servicelist.asciiOff()
# 		self.servicelist.close(None)
# 
# 		# clean up
# 		self.curSelectedRef = None
# 		self.curSelectedBouquet = None
# 		# display VZ data
# 		self.servicelist_overwrite_zap()

	#def switchChannelDown(self):
		#self.prepareChannelSelectionDisplay()
		#self.servicelist.moveDown()
		## show ChannelSelection
		#self.session.execDialog(self.servicelist)

	#def switchChannelUp(self):
		#self.prepareChannelSelectionDisplay()
		#self.servicelist.moveUp()
		## show ChannelSelection
		#self.session.execDialog(self.servicelist)

# 	def showFavourites(self):
# 		self.prepareChannelSelectionDisplay()
# 		self.servicelist.showFavourites()
# 		# show ChannelSelection
# 		self.session.execDialog(self.servicelist)

# 	def openServiceList(self):
# 		self.prepareChannelSelectionDisplay()
# 		# show ChannelSelection
# 		self.session.execDialog(self.servicelist)

# 	def servicelist_overwrite_zap(self):
# 		# we do not really want to zap to the service, just display data for VZ
# 		self.currentPiP = ""
# 		if self.isPlayable():
# 			self.onCreate()

# 	def __onClose(self):
# 		# reverse changes of ChannelSelection 
# 		self.servicelist.zap = self.servicelist_orig_zap
# 		self.servicelist["actions"] = ActionMap(["OkCancelActions", "TvRadioActions"],
# 			{
# 				"cancel": self.servicelist.cancel,
# 				"ok": self.servicelist.channelSelected,
# 				"keyRadio": self.servicelist.setModeRadio,
# 				"keyTV": self.servicelist.setModeTv,
# 			})

class RecordSetup(TimerEntry):
	def __init__(self, session, timer, zap):
		Screen.__init__(self, session)
		self.timer = timer
		self.timer.justplay = zap
		self.entryDate = None
		self.entryService = None
		self.keyGo()

	def keyGo(self, result = None):
		if self.timer.justplay:
			self.timer.begin += (config.recording.margin_before.value * 60)
			self.timer.end = self.timer.begin
		self.timer.resetRepeated()
		self.saveTimer()
		self.close((True, self.timer))

	def saveTimer(self):
		self.session.nav.RecordTimer.saveTimer()
				
class SingleEPG(EPGSelection):
	def __init__(self, session, service, zapFunc=None, bouquetChangeCB=None, serviceChangeCB=None):
		EPGSelection.__init__(self, session, service, zapFunc, bouquetChangeCB, serviceChangeCB)
		self.skinName = "EPGSelection"

class EPGSelectionSetup(Screen, ConfigListScreen):	
	def __init__(self, session, type):
		Screen.__init__(self, session)
		self.type=type
		Screen.setTitle(self, _("EPG Setup"))
		self["satus"] = StaticText()
		self['footnote'] = Label(_("* = Close EPG Required"))
		self["HelpWindow"] = Pixmap()
		self["HelpWindow"].hide()
		self["VKeyIcon"] = Boolean(False)
		self.onChangedEntry = [ ]
		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session, on_change = self.changedEntry)
		self.createSetup()
		self.skinName = "Setup"
		
		if self.type == 5:
			self["actions"] = ActionMap(["SetupActions", 'ColorActions', "HelpActions"],
			{
				"ok": self.keySave,
				"save": self.keySave,
				"cancel": self.keyCancel,
				"red": self.keyCancel,
				"green": self.keySave,
			}, -1)
		else:
			self["actions"] = ActionMap(["SetupActions", 'ColorActions'],
			{
				"ok": self.keySave,
				"save": self.keySave,
				"cancel": self.keyCancel,
				"red": self.keyCancel,
				"green": self.keySave,
			}, -1)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		if not self.selectionChanged in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.selectionChanged)
		self.selectionChanged()

	def createSetup(self):
		self.editListEntry = None
		self.list = [ ]
		if self.type == 5:
			self.list.append(getConfigListEntry(_("Channel preview mode"), config.epgselction.preview_mode_pliepg))
			self.list.append(getConfigListEntry(_("Show bouquet on launch"), config.epgselction.showbouquet_pliepg))
			self.list.append(getConfigListEntry(_("Picture In Graphics*"), config.epgselction.pictureingraphics))
			self.list.append(getConfigListEntry(_("Show Picons"), config.epgselction.showpicon))
			self.list.append(getConfigListEntry(_("Show Service names "), config.epgselction.showservicetitle))
			self.list.append(getConfigListEntry(_("Info Button"), config.epgselction.Info))
			self.list.append(getConfigListEntry(_("Long Info Button"), config.epgselction.InfoLong))
			self.list.append(getConfigListEntry(_("OK Button"), config.epgselction.OK_pliepg))
			self.list.append(getConfigListEntry(_("LongOK Button"), config.epgselction.OKLong_pliepg))
			self.list.append(getConfigListEntry(_("Channel 1 at Start"), config.epgselction.channel1))
			self.list.append(getConfigListEntry(_("Skip Empty Services"), config.epgselction.overjump))
			self.list.append(getConfigListEntry(_("Base Time"), config.epgselction.roundTo))
			self.list.append(getConfigListEntry(_("Primetime hour"), config.epgselction.primetimehour))
			self.list.append(getConfigListEntry(_("Primetime minute"), config.epgselction.primetimemins))
			self.list.append(getConfigListEntry(_("Items per Page"), config.epgselction.itemsperpage_vixepg))
			self.list.append(getConfigListEntry(_("Event Fontsize (relative to skin size)"), config.epgselction.ev_fontsize_pliepg))
			self.list.append(getConfigListEntry(_("Service Fontsize (relative to skin size)"), config.epgselction.serv_fontsize_pliepg))
			self.list.append(getConfigListEntry(_("Service width"), config.epgselction.servicewidth))
			self.list.append(getConfigListEntry(_("Timeline Fontsize"), config.epgselction.tl_fontsize_pliepg))
			self.list.append(getConfigListEntry(_("Time Scale"), config.epgselction.prev_time_period))
		elif self.type == 4:
			self.list.append(getConfigListEntry(_("Channel preview mode"), config.epgselction.preview_mode_infobar))
			self.list.append(getConfigListEntry(_("Skip Empty Services"), config.epgselction.overjump))
			self.list.append(getConfigListEntry(_("Sort List by"), config.epgselction.sort))
			self.list.append(getConfigListEntry(_("OK Button"), config.epgselction.OK_infobar))
			self.list.append(getConfigListEntry(_("LongOK Button"), config.epgselction.OKLong_infobar))
			self.list.append(getConfigListEntry(_("Items per Page"), config.epgselction.itemsperpage_infobar))
			self.list.append(getConfigListEntry(_("Event Fontsize (relative to skin size)"), config.epgselction.ev_fontsize_infobar))
		elif self.type == 3:
			self.list.append(getConfigListEntry(_("Channel preview mode"), config.epgselction.preview_mode_enhanced))
			self.list.append(getConfigListEntry(_("Skip Empty Services"), config.epgselction.overjump))
			self.list.append(getConfigListEntry(_("Sort List by"), config.epgselction.sort))
			self.list.append(getConfigListEntry(_("OK Button"), config.epgselction.OK_enhanced))
			self.list.append(getConfigListEntry(_("LongOK Button"), config.epgselction.OKLong_enhanced))
			self.list.append(getConfigListEntry(_("Items per Page"), config.epgselction.itemsperpage_enhanced))
			self.list.append(getConfigListEntry(_("Event Fontsize (relative to skin size)"), config.epgselction.ev_fontsize_enhanced))
		elif self.type == 1:
			self.list.append(getConfigListEntry(_("Channel preview mode"), config.epgselction.preview_mode))
			self.list.append(getConfigListEntry(_("Show bouquet on launch"), config.epgselction.showbouquet_multi))
			self.list.append(getConfigListEntry(_("Skip Empty Services"), config.epgselction.overjump))
			self.list.append(getConfigListEntry(_("Sort List by"), config.epgselction.sort))
			self.list.append(getConfigListEntry(_("OK Button"), config.epgselction.OK))
			self.list.append(getConfigListEntry(_("LongOK Button"), config.epgselction.OKLong))
			self.list.append(getConfigListEntry(_("Items per Page"), config.epgselction.itemsperpage_multi))
			self.list.append(getConfigListEntry(_("Event Fontsize (relative to skin size)"), config.epgselction.ev_fontsize_multi))
		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def selectionChanged(self):
		self["satus"].setText(_("Current value: ") + self.getCurrentValue())

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()
		self.selectionChanged()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def saveAll(self):
		for x in self["config"].list:
			x[1].save()
		configfile.save()

	# keySave and keyCancel are just provided in case you need them.
	# you have to call them by yourself.
	def keySave(self):
		self.saveAll()
		self.close()
	
	def cancelConfirm(self, result):
		if not result:
			return
		for x in self["config"].list:
			x[1].cancel()
		self.close()

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
		else:
			self.close()
