from Plugins.Plugin import PluginDescriptor
from Screens.PluginBrowser import *
from Screens.Ipkg import Ipkg
from Components.SelectionList import SelectionList
from Screens.NetworkSetup import *
from enigma import *
from Screens.Standby import *
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap, NumberActionMap, HelpableActionMap 
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Tools.BoundFunction import boundFunction
from Tools.LoadPixmap import LoadPixmap
from Components.MenuList import MenuList
from Components.FileList import FileList
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.Pixmap import Pixmap
from Components.config import ConfigSubsection, ConfigInteger, ConfigText, getConfigListEntry, ConfigSelection,  ConfigIP, ConfigYesNo, ConfigSequence, ConfigNumber, NoSave, ConfigEnableDisable
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText 
from Components.Sources.Progress import Progress
from Components.Button import Button
from Components.ActionMap import ActionMap
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest
from __init__ import _

import os
import sys
import re
font = "Regular;16"
import ServiceReference
import time
import datetime
inAAFPanel = None

config.plugins.aafpanel_redpanel = ConfigSubsection()
config.plugins.aafpanel_redpanel.enabled = ConfigYesNo(default=True)
config.plugins.aafpanel_redpanel.enabledlong = ConfigYesNo(default=False)
config.plugins.showaafpanelextensions = ConfigYesNo(default=False)

	
if os.path.isfile("/usr/lib/enigma2/python/Plugins/Extensions/MultiQuickButton/plugin.pyo") is True:
	try:
		from Plugins.Extensions.MultiQuickButton.plugin import *
	except:
		pass

if os.path.isfile("/usr/lib/enigma2/python/Plugins/SystemPlugins/choiceRC/plugin.pyo") is True:
	try:
		from Plugins.SystemPlugins.choiceRC.plugin import *
	except:
		pass		


from Plugins.Extensions.Aafpanel.CronManager import *
from Plugins.Extensions.Aafpanel.About import *
from Plugins.Extensions.Aafpanel.ScriptRunner import *
from Plugins.Extensions.Aafpanel.HddSetup import *
from Plugins.Extensions.Aafpanel.SoftcamPanel import *
from Plugins.Extensions.Aafpanel.CamStart import *
from Plugins.Extensions.Aafpanel.sundtek import *

def Check_Softcam():
	found = False
	for x in os.listdir('/etc'):
		if x.find('.emu') > -1:
			found = True
			break;
	return found

# Hide Softcam-Panel Setup when no softcams installed
if not Check_Softcam() and config.plugins.showaafpanelextensions.value:
	config.plugins.showaafpanelextensions.value = False
	config.plugins.aafpanel_redpanel.enabledlong.value = False
	config.plugins.showaafpanelextensions.save()
	config.plugins.aafpanel_redpanel.save()

# Hide Keymap selection when no other keymaps installed.
if config.usage.keymap.value != eEnv.resolve("${datadir}/enigma2/keymap.xml"):
	if not os.path.isfile(eEnv.resolve("${datadir}/enigma2/keymap.usr")) and config.usage.keymap.value == eEnv.resolve("${datadir}/enigma2/keymap.usr"):
		setDefaultKeymap()
	if not os.path.isfile(eEnv.resolve("${datadir}/enigma2/keymap.ntr")) and config.usage.keymap.value == eEnv.resolve("${datadir}/enigma2/keymap.ntr"):
		setDefaultKeymap()
		
def setDefaultKeymap():
	print "[Aaf-Panel] Set Keymap to Default"
	config.usage.keymap.value = eEnv.resolve("${datadir}/enigma2/keymap.xml")
	config.save()

# edit bb , touch commands.getouput with this def #
def command(comandline, strip=1):
  comandline = comandline + " >/tmp/command.txt"
  os.system(comandline)
  text = ""
  if os.path.exists("/tmp/command.txt") is True:
    file = open("/tmp/command.txt", "r")
    if strip == 1:
      for line in file:
        text = text + line.strip() + '\n'
    else:
      for line in file:
        text = text + line
        if text[-1:] != '\n': text = text + "\n"
    file.close
  # if one or last line then remove linefeed
  if text[-1:] == '\n': text = text[:-1]
  comandline = text
  os.system("rm /tmp/command.txt")
  return comandline

AAF_Panel_Version = 'OpenAAF-Panel V1.0'
boxversion = command('cat /etc/image-version | grep box_type | cut -d = -f2')
print "[Aaf-Panel] boxversion: %s"  % (boxversion)
panel = open("/tmp/aafpanel.ver", "w")
panel.write(AAF_Panel_Version + '\n')
panel.write("Boxversion: %s " % (boxversion)+ '\n')
try:
	panel.write("Keymap: %s " % (config.usage.keymap.value)+ '\n')
except:
	panel.write("Keymap: keymap file not found !!" + '\n')
panel.close()

ExitSave = "[Exit] = " +_("Cancel") +"              [Ok] =" +_("Save")


class ConfigPORT(ConfigSequence):
	def __init__(self, default):
		ConfigSequence.__init__(self, seperator = ".", limits = [(1,65535)], default = default)

def main(session, **kwargs):
		session.open(Aafpanel)

def Apanel(menuid, **kwargs):
	if menuid == "mainmenu":
		return [("OpenAAF Panel", main, "Aafpanel", 11)]
	else:
		return []

def autostart(reason, **kwargs):
	global timerInstance
	try:
		if timerInstance is None:
			timerInstance = CamStart(None)
		#timerInstance.startTimer()
		timerInstance.timerEvent()
	except:
		pass

def Plugins(**kwargs):
	return [

	#// show Aafpanel in Main Menu
	PluginDescriptor(name="OpenAAF Panel", description="OpenAAF panel AAF-GUI 06/11/2011", where = PluginDescriptor.WHERE_MENU, fnc = Apanel),
	#// autostart
	PluginDescriptor(where = [PluginDescriptor.WHERE_SESSIONSTART,PluginDescriptor.WHERE_AUTOSTART],fnc = autostart),
	#// show Aafpanel in EXTENSIONS Menu
	PluginDescriptor(name="OpenAAF Panel", description="OpenAAAF panel AAF-GUI 06/11/2011", where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc = main) ]



#############------- SKINS --------############################

MENU_SKIN = """<screen position="center,center" size="500,370" title="OpenAAF Panel" >
	<widget source="global.CurrentTime" render="Label" position="0, 340" size="500,24" font="Regular;20" foregroundColor="#FFFFFF" halign="right" transparent="1" zPosition="5">
		<convert type="ClockToText">>Format%H:%M:%S</convert>
	</widget>
	<eLabel backgroundColor="#56C856" position="0,330" size="500,1" zPosition="0" />
	<widget name="Mlist" position="10,10" size="480,300" zPosition="1" scrollbarMode="showOnDemand" backgroundColor="#251e1f20" transparent="1" />
	<widget name="label1" position="10,340" size="490,25" font="Regular;20" transparent="1" foregroundColor="#f2e000" halign="left" />
</screen>"""

CONFIG_SKIN = """<screen position="center,center" size="600,440" title="AAF Config" >
	<widget name="config" position="10,10" size="580,377" enableWrapAround="1" scrollbarMode="showOnDemand" />
	<widget name="labelExitsave" position="90,410" size="420,25" halign="center" font="Regular;20" transparent="1" foregroundColor="#f2e000" />
</screen>"""

CONFIG_SKIN_INFO = """<screen position="center,center" size="600,440" title="AAF Config" >
	<widget name="config" position="10,10" size="580,300" enableWrapAround="1" scrollbarMode="showOnDemand" />
	<eLabel backgroundColor="#56C856" position="0,300" size="600,1" zPosition="0" />
	<widget name="labelInfo" position="10,320" size="600,50" halign="center" font="Regular;20" transparent="1" foregroundColor="white" />
	<eLabel backgroundColor="#56C856" position="0,380" size="600,1" zPosition="0" />
	<widget name="labelExitsave" position="90,410" size="420,25" halign="center" font="Regular;20" transparent="1" foregroundColor="#f2e000" />
</screen>"""

INFO_SKIN =  """<screen name="AAF-Info"  position="center,center" size="730,400" title="AAF-Info" >
	<widget name="label2" position="0,10" size="730,25" font="Regular;20" transparent="1" halign="center" foregroundColor="#f2e000" />
	<widget name="label1" position="10,45" size="710,350" font="Console;20" zPosition="1" backgroundColor="#251e1f20" transparent="1" />
</screen>"""

INFO_SKIN2 =  """<screen name="AAF-Info2"  position="center,center" size="530,400" title="AAF-Info" backgroundColor="#251e1f20">
	<widget name="label1" position="10,50" size="510,340" font="Regular;15" zPosition="1" backgroundColor="#251e1f20" transparent="1" />
</screen>"""


###################  Max Test ###################
class PanelList(MenuList):
	def __init__(self, list, font0 = 24, font1 = 16, itemHeight = 50, enableWrapAround = True):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", font0))
		self.l.setFont(1, gFont("Regular", font1))
		self.l.setItemHeight(itemHeight)

def MenuEntryItem(entry):
	res = [entry]
	res.append(MultiContentEntryPixmapAlphaTest(pos=(0, 5), size=(100, 40), png=entry[0]))  # png vorn
	res.append(MultiContentEntryText(pos=(110, 10), size=(440, 40), font=0, text=entry[1]))  # menupunkt
	return res
###################  Max Test ###################

#g
from Screens.PiPSetup import PiPSetup
from Screens.InfoBarGenerics import InfoBarPiP
#g

def AafEntryComponent(file):
	png = LoadPixmap("/usr/lib/enigma2/python/Plugins/Extensions/Aafpanel/pics/" + file + ".png")
	if png == None:
		png = LoadPixmap("/usr/lib/enigma2/python/Plugins/Extensions/Aafpanel/pics/default.png")
	res = (png)
	return res

class Aafpanel(Screen, InfoBarPiP):
	servicelist = None
	def __init__(self, session, services = None):
		Screen.__init__(self, session)
		self.session = session
		self.skin = MENU_SKIN
		self.onShown.append(self.setWindowTitle)
		self.service = None
		global pluginlist
		global videomode
		global aafok
		global AAFCONF
		global menu
		AAFCONF = 0
		pluginlist="False"
		try:
			print '[AAF-Panel] SHOW'
			global inAAFPanel
			inAAFPanel = self
		except:
			print '[AAF-Panel] Error Hide'
#		global servicelist
		if services is not None:
			self.servicelist = services
		else:
			self.servicelist = None
		self.list = []
		#// get the remote buttons
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"],
			{
				"cancel": self.Exit,
				"upUp": self.up,
				"downUp": self.down,
				"ok": self.ok,
			}, 1)
		
		self["label1"] = Label(AAF_Panel_Version)

		self.Mlist = []
		if Check_Softcam():
			self.Mlist.append(MenuEntryItem((AafEntryComponent('SoftcamPanel'), _("SoftcamPanel"), 'SoftcamPanel')))
		self.Mlist.append(MenuEntryItem((AafEntryComponent('Setup'), _("Setup"), 'Setup')))
		self.Mlist.append(MenuEntryItem((AafEntryComponent('Plugins'), _("Plugins"), 'Plugins')))
		self.Mlist.append(MenuEntryItem((AafEntryComponent('Infos'), _("Infos"), 'Infos')))
		self.Mlist.append(MenuEntryItem((AafEntryComponent('About'), _("About"), 'About')))
		self.onChangedEntry = []
		if (getDesktop(0).size().width() == 1280):
			self["Mlist"] = PanelList([])
		else:
			self["Mlist"] = PanelList([], font0=24, font1=15, itemHeight=50)
		self["Mlist"].l.setList(self.Mlist)
		menu = 0

	def getCurrentEntry(self):
		if self['Mlist'].l.getCurrentSelection():
			selection = self['Mlist'].l.getCurrentSelection()[0]
			if (selection[0] is not None):
				return selection[0]

	def setWindowTitle(self):
		self.setTitle(_("OpenAAF Panel"))

	def up(self):
		#self["Mlist"].up()
		pass

	def down(self):
		#self["Mlist"].down()
		pass

	def left(self):
		pass

	def right(self):
		pass

	def Red(self):
		self.showExtensionSelection1(Parameter="run")
		pass

	def Green(self):
		#// Not used
		pass

	def yellow(self):
		#// Not used
		pass

	def blue(self):
		#// Not used
		pass

	def Exit(self):
		#// Exit Aafpanel when pressing the EXIT button or go back to the MainMenu
		global menu
		if menu == 0:
			try:
				self.service = self.session.nav.getCurrentlyPlayingServiceReference()
				service = self.service.toCompareString()
				servicename = ServiceReference.ServiceReference(service).getServiceName().replace('\xc2\x87', '').replace('\xc2\x86', '').ljust(16)
				print '[AAF-Panel] HIDE'
				global inAAFPanel
				inAAFPanel = None
			except:
				print '[AAF-Panel] Error Hide'
			self.close()
		elif menu == 1:
			self["Mlist"].moveToIndex(0)
			self["Mlist"].l.setList(self.oldmlist)
			menu = 0
			self["label1"].setText(AAF_Panel_Version)
		elif menu == 2:
			self["Mlist"].moveToIndex(0)
			self["Mlist"].l.setList(self.oldmlist1)
			menu = 1
			self["label1"].setText("Infos")
		else:
			pass

	def ok(self):
		#// Menu Selection
#		menu = self["Mlist"].getCurrent()
		global AAFCONF
		menu = self['Mlist'].l.getCurrentSelection()[0][2]
		print '[AAF-Panel] MenuItem: ' + menu
		if menu == "Setup":
			self.Setup()
		elif menu == "Networksetup":
			self.session.open(NetworkAdapterSelection)
		elif menu == "Plugins":
			self.Plugins()
		#elif menu == "Pluginbrowser":
		#	self.session.open(PluginBrowser)
		elif menu == "Infos":
			self.Infos()
		elif menu == "OpenAAF":
			self.session.open(Info, "AAF")
		elif menu == "Info":
			self.session.open(Info, "Sytem_info")
		elif menu == "Default":
			self.session.open(Info, "Default")
		elif menu == "FreeSpace":
			self.session.open(Info, "FreeSpace")
		elif menu == "Network":
			self.session.open(Info, "Network")
		elif menu == "Mounts":
			self.session.open(Info, "Mounts")
		elif menu == "Kernel":
			self.session.open(Info, "Kernel")
		elif menu == "Ram":
			self.session.open(Info, "Free")
		elif menu == "Cpu":
			self.session.open(Info, "Cpu")
		elif menu == "Top":
			self.session.open(Info, "Top")
		elif menu == "MemInfo":
			self.session.open(Info, "MemInfo")
		elif menu == "Module":
			self.session.open(Info, "Module")
		elif menu == "Mtd":
			self.session.open(Info, "Mtd")
		elif menu == "Partitions":
			self.session.open(Info, "Partitions")
		elif menu == "Swap":
			self.session.open(Info, "Swap")
		elif menu == "System_Info":
			self.System()
		elif menu == "CronManager":
			self.session.open(CronManager)	
		elif menu == "About":
			self.session.open(AboutTeam)
		elif menu == "JobManager":
			self.session.open(ScriptRunner)
		elif menu == "SoftcamPanel":
			self.session.open(SoftcamPanel)
		elif menu == "MultiQuickButton":
			self.session.open(MultiQuickButton)
		elif menu == "Remote_setup":
			self.session.open(RCSetupScreen)
		elif menu == "Device_Manager":
			self.session.open(HddSetup)
		elif menu == "SundtekControlCenter":
			self.session.open(SundtekControlCenter)
		elif menu == "RedPanel":
			self.session.open(RedPanel)
		elif menu == "Softcam-Panel Setup":
			self.session.open(ShowSoftcamPanelExtensions)
		elif menu == "KeymapSel":
			self.session.open(KeymapSel)
		else:
			pass

	def Setup(self):
		#// Create Setup Menu
		global menu
		menu = 1
		self["label1"].setText("Setup")
		self.tlist = []
		self.oldmlist = []
		self.oldmlist = self.Mlist
		self.tlist.append(MenuEntryItem((AafEntryComponent('Networksetup'), _("Networksetup"), 'Networksetup')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('SundtekControlCenter'), _("SundtekControlCenter"), 'SundtekControlCenter')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('RedPanel'), _("RedPanel"), 'RedPanel')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('KeymapSel'), _("Keymap Selection"), 'KeymapSel')))
		if Check_Softcam():
			self.tlist.append(MenuEntryItem((AafEntryComponent('Softcam-Panel Setup'), _("Softcam-Panel Setup"), 'Softcam-Panel Setup')))
		if os.path.isfile("/usr/lib/enigma2/python/Plugins/Extensions/MultiQuickButton/plugin.pyo") is True:
			self.tlist.append(MenuEntryItem((AafEntryComponent('MultiQuickButton'), _("MultiQuickButton"), 'MultiQuickButton')))	
		if os.path.isfile("/usr/lib/enigma2/python/Plugins/SystemPlugins/choiceRC/plugin.pyo") is True:
			self.tlist.append(MenuEntryItem((AafEntryComponent('Remote_setup'), _("Remote_setup"), 'Remote_setup')))
		self["Mlist"].moveToIndex(0)
		self["Mlist"].l.setList(self.tlist)
		self.oldmlist1 = self.tlist

	def Plugins(self):
		#// Create Plugin Menu
		global menu
		menu = 1
		self["label1"].setText(_("Plugins"))
		self.tlist = []
		self.oldmlist = []
		self.oldmlist = self.Mlist
		self.tlist.append(MenuEntryItem((AafEntryComponent('Device_Manager'), _("Device_Manager"), 'Device_Manager')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('CronManager'), _("CronManager"), 'CronManager')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('JobManager'), _("JobManager"), 'JobManager')))
		self["Mlist"].moveToIndex(0)
		self["Mlist"].l.setList(self.tlist)

	def Infos(self):
		#// Create Infos Menu
		global menu
		menu = 1
		self["label1"].setText(_("Infos"))
		self.tlist = []
		self.oldmlist = []
		self.oldmlist1 = []
		self.oldmlist = self.Mlist
		self.tlist.append(MenuEntryItem((AafEntryComponent('OpenAAF'), _("OpenAAF"), 'OpenAAF')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Default'), _("Default"), 'Default')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('FreeSpace'), _("FreeSpace"), 'FreeSpace')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Kernel'), _("Kernel"), 'Kernel')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Mounts'), _("Mounts"), 'Mounts')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Network'), _("Network"), 'Network')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Ram'), _("Ram"), 'Ram')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('System_Info'), _("System_Info"), 'System_Info')))
		self["Mlist"].moveToIndex(0)
		self["Mlist"].l.setList(self.tlist)
		self.oldmlist1 = self.tlist

	def System(self):
		#// Create System Menu
		global menu
		menu = 2
		self["label1"].setText(_("System Info"))
		self.tlist = []
		self.tlist.append(MenuEntryItem((AafEntryComponent('Cpu'), _("Cpu"), 'Cpu')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('MemInfo'), _("MemInfo"), 'MemInfo')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Mtd'), _("Mtd"), 'Mtd')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Module'), _("Module"), 'Module')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Partitions'), _("Partitions"), 'Partitions')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Swap'), _("Swap"), 'Swap')))
		self.tlist.append(MenuEntryItem((AafEntryComponent('Top'), _("Top"), 'Top')))
		self["Mlist"].moveToIndex(0)
		self["Mlist"].l.setList(self.tlist)

	def System_main(self):
		#// Create System Main Menu
		global menu
		menu = 1
		self["label1"].setText(_("System"))
		self.tlist = []
		self.oldmlist = []
		self.oldmlist = self.Mlist
		self.tlist.append(MenuEntryItem((AafEntryComponent('Info'), _("Info"), 'Info')))
		self["Mlist"].moveToIndex(0)
		self["Mlist"].l.setList(self.tlist)

class KeymapSel(ConfigListScreen,Screen):
	def __init__(self, session):
		self.service = None
		Screen.__init__(self, session)

		self.skin = CONFIG_SKIN_INFO
		self.onShown.append(self.setWindowTitle)

		self["labelExitsave"] = Label(ExitSave)
		self["labelInfo"] = Label(_("Copy your keymap to\n/usr/share/enigma2/keymap.usr"))

		
		#keySel = [ ('keymap.xml',_("Default  (keymap.xml)")),('keymap.usr',_("User  (keymap.usr)"))]
		keySel = [ ('keymap.xml',_("Default  (keymap.xml)"))]
		if os.path.isfile(eEnv.resolve("${datadir}/enigma2/keymap.usr")):
			keySel.append(('keymap.usr',_("User  (keymap.usr)")))
		else:
			setDefaultKeymap()
		if os.path.isfile(eEnv.resolve("${datadir}/enigma2/keymap.ntr")):
			keySel.append(('keymap.ntr',_("Neutrino  (keymap.ntr)")))
		else:
			setDefaultKeymap()
		self.keyshow = ConfigSelection(keySel)
		self.actkeymap = self.getKeymap(config.usage.keymap.value)
		self.keyshow.value = self.actkeymap

		self.Clist = []
		self.Clist.append(getConfigListEntry(_("Use Keymap"), self.keyshow))
		ConfigListScreen.__init__(self, self.Clist)

		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "SetupActions"],
		{
			"cancel": self.Exit,
			"ok": self.ok,
			"left": self.keyLeft,
			"right": self.keyRight,
		}, -2)

	def setWindowTitle(self):
		self.setTitle(_("Keymap Selection"))

	def Exit(self):
		self.close()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
	
	def keyRight(self):
		ConfigListScreen.keyRight(self)

	def ok(self):
		config.usage.keymap.value = eEnv.resolve("${datadir}/enigma2/" + self.keyshow.value)
		config.save()
		if self.actkeymap != self.keyshow.value:
			self.changedFinished()
		else:
			self.close()
	
	def changedFinished(self):
		self.session.openWithCallback(self.ExecuteRestart, MessageBox, _("Keymap changed, you need to restart the GUI") +"\n"+_("Do you want to restart now?"), MessageBox.TYPE_YESNO)
		self.close()

	def ExecuteRestart(self, result):
		if result:
			quitMainloop(3)
		else:
			self.close()
	def getKeymap(self, file):
		return file[file.rfind('/') +1:]

class RedPanel(ConfigListScreen,Screen):
	def __init__(self, session):
		self.service = None
		Screen.__init__(self, session)

		self.skin = CONFIG_SKIN
		self.onShown.append(self.setWindowTitle)

		self["labelExitsave"] = Label(ExitSave)

		self.Clist = []
		self.Clist.append(getConfigListEntry(_("Show AAF-Panel Red-key"), config.plugins.aafpanel_redpanel.enabled))
		self.Clist.append(getConfigListEntry(_("Show Softcam-Panel Red-key long"), config.plugins.aafpanel_redpanel.enabledlong))
		ConfigListScreen.__init__(self, self.Clist)

		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "SetupActions"],
		{
			"cancel": self.Exit,
			"ok": self.ok,
			"left": self.keyLeft,
			"right": self.keyRight,
		}, -2)

	def setWindowTitle(self):
		self.setTitle(_("RedPanel"))

	def Exit(self):
		self.close()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
	
	def keyRight(self):
		ConfigListScreen.keyRight(self)

	def ok(self):
		config.plugins.aafpanel_redpanel.save()
		self.close()

class ShowSoftcamPanelExtensions(ConfigListScreen,Screen):
	def __init__(self, session):
		self.service = None
		Screen.__init__(self, session)

		self.skin = CONFIG_SKIN
		self.onShown.append(self.setWindowTitle)

		self["labelExitsave"] = Label(ExitSave)

		self.Clist = []
		self.Clist.append(getConfigListEntry(_("Show Softcam-Panel in Extensions Menu"), config.plugins.showaafpanelextensions))
		ConfigListScreen.__init__(self, self.Clist)

		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "SetupActions"],
		{
			"cancel": self.Exit,
			"ok": self.ok,
			"left": self.keyLeft,
			"right": self.keyRight,
		}, -2)

	def setWindowTitle(self):
		self.setTitle(_("Softcam-Panel Setup"))

	def Exit(self):
		self.close()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
	
	def keyRight(self):
		ConfigListScreen.keyRight(self)

	def ok(self):
		config.plugins.showaafpanelextensions.save()
		self.close()

class Info(Screen):
	def __init__(self, session, info):
		self.service = None
		Screen.__init__(self, session)

		self.skin = INFO_SKIN

		self["label2"] = Label("AAF")
		self["label1"] =  ScrollLabel()
		if info == "AAF":
			self.AAF()
		if info == "Sytem_info":
			self.Sytem_info()
		elif info == "Default":
			self.Default()
		elif info == "FreeSpace":
			self.FreeSpace()
		elif info == "Mounts":
			self.Mounts()
		elif info == "Network":
			self.Network()
		elif info == "Kernel":
			self.Kernel()
		elif info == "Free":
			self.Free()
		elif info == "Cpu":
			self.Cpu()
		elif info == "Top":
			self.Top()
		elif info == "MemInfo":
			self.MemInfo()
		elif info == "Module":
			self.Module()
		elif info == "Mtd":
			self.Mtd()
		elif info == "Partitions":
			self.Partitions()
		elif info == "Swap":
			self.Swap()

		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"],
		{
			"cancel": self.Exit,
			"ok": self.ok,
			"up": self.Up,
			"down": self.Down,
		}, -1)

	def Exit(self):
		self.close()

	def ok(self):
		self.close()

	def Down(self):
		self["label1"].pageDown()

	def Up(self):
		self["label1"].pageUp()

	def AAF(self):
		try:
			self["label2"].setText("AAF")
			info1 = self.Do_cmd("cat", "/etc/motd", None)
			if info1.find('wElc0me') > -1:
				info1 = info1[info1.find('wElc0me'):len(info1)] + "\n"
				info1 = info1.replace('|','')
			else:
				info1 = info1[info1.find('AAF'):len(info1)] + "\n"
			info2 = self.Do_cmd("cat", "/etc/image-version", None)
			info3 = self.Do_cut(info1 + info2)
			self["label1"].setText(info3)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Sytem_info(self):
		try:
			self["label2"].setText(_("Image Info"))
			info1 = self.Do_cmd("cat", "/etc/version", None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Default(self):

		try:
			self["label2"].setText(_("Default"))
			now = datetime.datetime.now()
			info1 = 'Date = ' + now.strftime("%d-%B-%Y") + "\n"
			info2 = 'Time = ' + now.strftime("%H:%M:%S") + "\n"
			info3 = self.Do_cmd("uptime", None, None)
			tmp = info3.split(",")
			info3 = 'Uptime = ' + tmp[0].lstrip() + "\n"
			info4 = self.Do_cmd("cat", "/etc/image-version", " | head -n 1")
			info4 = info4[9:]
			info4 = 'Boxtype = ' + info4 + "\n"
			info5 = 'Load = ' + self.Do_cmd("cat", "/proc/loadavg", None)
			info6 = self.Do_cut(info1 + info2 + info3 + info4 + info5)
			self["label1"].setText(info6)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def FreeSpace(self):
		try:
			self["label2"].setText(_("FreeSpace"))
			info1 = self.Do_cmd("df", None, "-h")
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Mounts(self):
		try:
			self["label2"].setText(_("Mounts"))
			info1 = self.Do_cmd("mount", None, None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Network(self):
		try:
			self["label2"].setText(_("Network"))
			info1 = self.Do_cmd("ifconfig", None, None) + '\n'
			info2 = self.Do_cmd("route", None, "-n")
			info3 = self.Do_cut(info1 + info2)
			self["label1"].setText(info3)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Kernel(self):
		try:
			self["label2"].setText(_("Kernel"))
			info0 = self.Do_cmd("cat", "/proc/version", None)
			info = info0.split('(')
			info1 = "Name = " + info[0] + "\n"
			info2 =  "Owner = " + info[1].replace(')','') + "\n"
			info3 =  "Mainimage = " + info[2][0:info[2].find(')')] + "\n"
			info4 = "Date = " + info[2][info[2].find('SMP')+8:len(info[2])]
			info5 = self.Do_cut(info1 + info2 + info3 + info4)
			self["label1"].setText(info5)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Free(self):
		try:
			self["label2"].setText(_("Ram"))
			info1 = self.Do_cmd("free", None, None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Cpu(self):
		try:
			self["label2"].setText(_("Cpu"))
			info1 = self.Do_cmd("cat", "/proc/cpuinfo", None, " | sed 's/\t\t/\t/'")
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Top(self):
		try:
			self["label2"].setText(_("Top"))
			info1 = self.Do_cmd("top", None, "-b -n1")
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def MemInfo(self):
		try:
			self["label2"].setText(_("MemInfo"))
			info1 = self.Do_cmd("cat", "/proc/meminfo", None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Module(self):
		try:
			self["label2"].setText(_("Module"))
			info1 = self.Do_cmd("cat", "/proc/modules", None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Mtd(self):
		try:
			self["label2"].setText(_("Mtd"))
			info1 = self.Do_cmd("cat", "/proc/mtd", None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Partitions(self):
		try:
			self["label2"].setText(_("Partitions"))
			info1 = self.Do_cmd("cat", "/proc/partitions", None)
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))

	def Swap(self):
		try:
			self["label2"].setText(_("Swap"))
			info0 = self.Do_cmd("cat", "/proc/swaps", None, " | sed 's/\t/ /g; s/[ ]* / /g'")
			info0 = info0.split("\n");
			info1 = ""
			for l in info0[1:]:
				l1 = l.split(" ")
				info1 = info1 + "Name: " + l1[0] + '\n'
				info1 = info1 + "Type: " + l1[1] + '\n'
				info1 = info1 + "Size: " + l1[2] + '\n'
				info1 = info1 + "Used: " + l1[3] + '\n'
				info1 = info1 + "Prio: " + l1[4] + '\n\n'
			if info1[-1:] == '\n': info1 = info1[:-1]
			if info1[-1:] == '\n': info1 = info1[:-1]
			info1 = self.Do_cut(info1)
			self["label1"].setText(info1)
		except:
			self["label1"].setText(_("an internal error has occur"))


	def Do_find(self, text, search):
		text = text + ' '
		ret = ""
		pos = text.find(search)
		pos1 = text.find(" ", pos)
		if pos > -1:
			ret = text[pos + len(search):pos1]
		return ret

	def Do_cut(self, text):
		text1 = text.split("\n")
		text = ""
		for line in text1:
			text = text + line[:95] + "\n"
		if text[-1:] == '\n': text = text[:-1]
		return text

	def Do_cmd(self, cmd , file, arg , pipe = ""):
		try:
			if file != None:
				if os.path.exists(file) is True:
					o = command(cmd + ' ' + file + pipe, 0)
				else:
					o = "File not found: \n" + file
			else:
				if arg == None:
					o = command(cmd, 0)
				else:
					o = command(cmd + ' ' + arg, 0)
			return o
		except:
			o = ''
			return o

