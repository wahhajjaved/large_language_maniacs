#gui/__init__.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2006-2007 NVDA Contributors <http://www.nvda-project.org/>
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

import time
import os
import sys
import wx
from wx.lib import newevent
import globalVars
import config
import versionInfo
import speech
import queueHandler
import core
from settingsDialogs import *
import speechDictHandler
import languageHandler
import logViewer

### Constants
appTitle = "NVDA"
NVDA_PATH = os.getcwd()
ICON_PATH=os.path.join(NVDA_PATH, "images", "icon.png")

ExternalCommandEvent, evt_externalCommand = newevent.NewCommandEvent()
id_showGuiCommand=wx.NewId()
id_abortCommand=wx.NewId()
evt_externalExecute = wx.NewEventType()

### Globals
mainFrame = None
#: A list of top level windows excluding L{mainFrame} which are currently instantiated and which should be destroyed on exit.
#: @type: list
topLevelWindows = []

class ExternalExecuteEvent(wx.PyCommandEvent):
	def __init__(self, func, args, kwargs, callback):
		super(ExternalExecuteEvent, self).__init__(evt_externalExecute, wx.ID_ANY)
		self._func = func
		self._args = args
		self._kwargs = kwargs
		self._callback = callback

	def run(self):
		ret = self._func(*self._args, **self._kwargs)
		if self._callback:
			queueHandler.registerGeneratorObject(self._callback_gen(ret))

	def _callback_gen(self, ret):
		for n in xrange(20):
			yield None
		self._callback(ret)

def getDocFilePath(fileName, localized=True):
	if not getDocFilePath.rootPath:
		if hasattr(sys, "frozen"):
			getDocFilePath.rootPath = os.path.join(NVDA_PATH, "documentation")
		else:
			getDocFilePath.rootPath = os.path.abspath(os.path.join("..", "user_docs"))

	if localized:
		lang = languageHandler.getLanguage()
		tryLangs = [lang]
		if "_" in lang:
			# This locale has a sub-locale, but documentation might not exist for the sub-locale, so try stripping it.
			tryLangs.append(lang.split("_")[0])
		# If all else fails, use English.
		tryLangs.append("en")

		fileName, fileExt = os.path.splitext(fileName)
		for tryLang in tryLangs:
			tryDir = os.path.join(getDocFilePath.rootPath, tryLang)
			if not os.path.isdir(tryDir):
				continue

			# Some out of date translations might include .txt files which are now .html files in newer translations.
			# Therefore, ignore the extension and try both .html and .txt.
			for tryExt in ("html", "txt"):
				tryPath = os.path.join(tryDir, "%s.%s" % (fileName, tryExt))
				if os.path.isfile(tryPath):
					return tryPath

	else:
		# Not localized.
		if not hasattr(sys, "frozen") and fileName in ("copying.txt", "contributors.txt"):
			# If running from source, these two files are in the root dir.
			return os.path.join(NVDA_PATH, "..", fileName)
		else:
			return os.path.join(getDocFilePath.rootPath, fileName)
getDocFilePath.rootPath = None

class MainFrame(wx.Frame):

	def __init__(self):
		style = wx.DEFAULT_FRAME_STYLE ^ wx.MAXIMIZE_BOX ^ wx.MINIMIZE_BOX | wx.FRAME_NO_TASKBAR
		super(MainFrame, self).__init__(None, wx.ID_ANY, appTitle, size=(500,500), style=style)
		self.Bind(evt_externalCommand, self.onAbortCommand, id=id_abortCommand)
		self.Bind(evt_externalCommand, self.onExitCommand, id=wx.ID_EXIT)
		self.Bind(evt_externalCommand, self.onShowGuiCommand, id=id_showGuiCommand)
		wx.EVT_COMMAND(self,wx.ID_ANY,evt_externalExecute,lambda evt: evt.run())
		self.sysTrayIcon = SysTrayIcon(self)
		self.Show(True)
		self.Show(False)

	def Destroy(self):
		global topLevelWindows
		self.sysTrayIcon.Destroy()
		for window in list(topLevelWindows):
			window.Destroy()
		super(MainFrame, self).Destroy()

	def prePopup(self):
		"""Prepare for a popup.
		This should be called before any dialog or menu which should pop up for the user.
		L{postPopup} should be called after the dialog or menu has been shown.
		@postcondition: A dialog or menu may be shown.
		"""
		self.Show()
		self.Raise()

	def postPopup(self):
		"""Clean up after a popup dialog or menu.
		This should be called after a dialog or menu was popped up for the user.
		"""
		self.Show()
		self.Hide()

	def onAbortCommand(self,evt):
		self.Destroy()

	def onShowGuiCommand(self,evt):
		self.prePopup()
		self.sysTrayIcon.onActivate(None)
		self.postPopup()

	def onRevertToSavedConfigurationCommand(self,evt):
		queueHandler.queueFunction(queueHandler.eventQueue,core.resetConfiguration,reportDone=True)

	def onSaveConfigurationCommand(self,evt):
		try:
			config.save()
			queueHandler.queueFunction(queueHandler.eventQueue,speech.speakMessage,_("configuration saved"))
		except:
			speech.speakMessage(_("Could not save configuration - probably read only file system"),wait=True)

	def _popupSettingsDialog(self, dialog, *args, **kwargs):
		self.prePopup()
		dialog(self, *args, **kwargs).Show()
		self.postPopup()

	def onDefaultDictionaryCommand(self,evt):
		self._popupSettingsDialog(DictionaryDialog,_("Default dictionary"),speechDictHandler.dictionaries["default"])

	def onVoiceDictionaryCommand(self,evt):
		self._popupSettingsDialog(DictionaryDialog,_("Voice dictionary (%s)")%speechDictHandler.dictionaries["voice"].fileName,speechDictHandler.dictionaries["voice"])

	def onTemporaryDictionaryCommand(self,evt):
		self._popupSettingsDialog(DictionaryDialog,_("Temporary dictionary"),speechDictHandler.dictionaries["temp"])

	def onExitCommand(self, evt):
		canExit=False
		if config.conf["general"]["askToExit"]:
			self.prePopup()
			d = wx.MessageDialog(self, _("Are you sure you want to quit NVDA?"), _("Exit NVDA"), wx.YES|wx.NO|wx.ICON_WARNING)
			if d.ShowModal() == wx.ID_YES:
				canExit=True
			self.postPopup()
		else:
			canExit=True
		if canExit:
			if config.conf["general"]["saveConfigurationOnExit"]:
				try:
					config.save()
				except:
					globalVars.log.warning("Could not save configuration - probably read only file system", exc_info=True)
			self.Destroy()

	def onGeneralSettingsCommand(self,evt):
		self._popupSettingsDialog(GeneralSettingsDialog)

	def onSynthesizerCommand(self,evt):
		self._popupSettingsDialog(SynthesizerDialog)

	def onVoiceCommand(self,evt):
		self._popupSettingsDialog(VoiceSettingsDialog)

	def onKeyboardSettingsCommand(self,evt):
		self._popupSettingsDialog(KeyboardSettingsDialog)

	def onMouseSettingsCommand(self,evt):
		self._popupSettingsDialog(MouseSettingsDialog)

	def onObjectPresentationCommand(self,evt):
		self._popupSettingsDialog(ObjectPresentationDialog)

	def onVirtualBuffersCommand(self,evt):
		self._popupSettingsDialog(VirtualBuffersDialog)

	def onDocumentFormattingCommand(self,evt):
		self._popupSettingsDialog(DocumentFormattingDialog)

	def onAboutCommand(self,evt):
		try:
			aboutInfo="""%s
%s: %s
%s: %s
%s: %s"""%(versionInfo.longName,_("version"),versionInfo.version,_("url"),versionInfo.url,_("copyright"),versionInfo.copyrightInfo)
			self.prePopup()
			d = wx.MessageDialog(self, aboutInfo, _("About NVDA"), wx.OK)
			d.ShowModal()
			self.postPopup()
		except:
			globalVars.log.error("gui.mainFrame.onAbout", exc_info=True)

	def onViewLogCommand(self, evt):
		logViewer.LogViewer().Show()

	def onPythonConsoleCommand(self, evt):
		import pythonConsole
		if not pythonConsole.consoleUI:
			pythonConsole.initialize()
		pythonConsole.activate()

class SysTrayIcon(wx.TaskBarIcon):

	def __init__(self, frame):
		super(SysTrayIcon, self).__init__()
		icon=wx.Icon(ICON_PATH,wx.BITMAP_TYPE_PNG)
		self.SetIcon(icon, appTitle)

		self.menu=wx.Menu()
		menu_preferences=wx.Menu()
		item = menu_preferences.Append(wx.ID_ANY,_("&General settings..."),_("General settings"))
		self.Bind(wx.EVT_MENU, frame.onGeneralSettingsCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("&Synthesizer..."),_(" the synthesizer to use"))
		self.Bind(wx.EVT_MENU, frame.onSynthesizerCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("&Voice settings..."),_("Choose the voice, rate, pitch and volume  to use"))
		self.Bind(wx.EVT_MENU, frame.onVoiceCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("&Keyboard Settings..."),_("Configure keyboard layout, speaking of typed characters, words or command keys"))
		self.Bind(wx.EVT_MENU, frame.onKeyboardSettingsCommand, item)
		item = menu_preferences.Append(wx.ID_ANY, _("&Mouse settings..."),_("Change reporting of mouse sape, object under mouse"))
		self.Bind(wx.EVT_MENU, frame.onMouseSettingsCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("&Object presentation..."),_("Change reporting of objects")) 
		self.Bind(wx.EVT_MENU, frame.onObjectPresentationCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("Virtual &buffers..."),_("Change virtual buffers specific settings")) 
		self.Bind(wx.EVT_MENU, frame.onVirtualBuffersCommand, item)
		item = menu_preferences.Append(wx.ID_ANY,_("Document &formatting..."),_("Change Settings of document properties")) 
		self.Bind(wx.EVT_MENU, frame.onDocumentFormattingCommand, item)
		subMenu_speechDicts = wx.Menu()
		item = subMenu_speechDicts.Append(wx.ID_ANY,_("&Default dictionary..."),_("dialog where you can set default dictionary by adding dictionary entries to the list"))
		self.Bind(wx.EVT_MENU, frame.onDefaultDictionaryCommand, item)
		item = subMenu_speechDicts.Append(wx.ID_ANY,_("&Voice dictionary..."),_("dialog where you can set voice-specific dictionary by adding dictionary entries to the list"))
		self.Bind(wx.EVT_MENU, frame.onVoiceDictionaryCommand, item)
		item = subMenu_speechDicts.Append(wx.ID_ANY,_("&Temporary dictionary..."),_("dialog where you can set temporary dictionary by adding dictionary entries to the edit box"))
		self.Bind(wx.EVT_MENU, frame.onTemporaryDictionaryCommand, item)
		menu_preferences.AppendMenu(wx.ID_ANY,_("Speech &dictionaries"),subMenu_speechDicts)
		self.menu.AppendMenu(wx.ID_ANY,_("&Preferences"),menu_preferences)

		menu_tools = wx.Menu()
		item = menu_tools.Append(wx.ID_ANY, _("View log"))
		self.Bind(wx.EVT_MENU, frame.onViewLogCommand, item)
		item = menu_tools.Append(wx.ID_ANY, _("Python console"))
		self.Bind(wx.EVT_MENU, frame.onPythonConsoleCommand, item)
		self.menu.AppendMenu(wx.ID_ANY, _("Tools"), menu_tools)

		menu_help = wx.Menu()
		item = menu_help.Append(wx.ID_ANY, _("User guide"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile(getDocFilePath("user guide.html")), item)
		item = menu_help.Append(wx.ID_ANY, _("Key Command Quick Reference"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile(getDocFilePath("key commands.txt")), item)
		item = menu_help.Append(wx.ID_ANY, _("What's &new"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile(getDocFilePath("whats new.txt", False)), item)
		subMenu = wx.Menu()
		item = subMenu.Append(wx.ID_ANY, _("Home page"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile("http://www.nvda-project.org/"), item)
		item = subMenu.Append(wx.ID_ANY, _("Trac (issue tracker)"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile("http://trac.nvda-project.org/"), item)
		menu_help.AppendMenu(wx.ID_ANY, _("Web resources"), subMenu)
		item = menu_help.Append(wx.ID_ANY, _("License"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile(getDocFilePath("copying.txt", False)), item)
		item = menu_help.Append(wx.ID_ANY, _("Contributors"))
		self.Bind(wx.EVT_MENU, lambda evt: os.startfile(getDocFilePath("contributors.txt", False)), item)
		item = menu_help.Append(wx.ID_ABOUT, _("About..."), _("About NVDA"))
		self.Bind(wx.EVT_MENU, frame.onAboutCommand, item)
		self.menu.AppendMenu(wx.ID_ANY,_("&Help"),menu_help)
		self.menu.AppendSeparator()
		item = self.menu.Append(wx.ID_ANY, _("&Revert to saved configuration"),_("Reset all settings to saved state"))
		self.Bind(wx.EVT_MENU, frame.onRevertToSavedConfigurationCommand, item)
		item = self.menu.Append(wx.ID_SAVE, _("&Save configuration"), _("Write the current configuration to nvda.ini"))
		self.Bind(wx.EVT_MENU, frame.onSaveConfigurationCommand, item)
		self.menu.AppendSeparator()
		item = self.menu.Append(wx.ID_EXIT, _("E&xit"),_("Exit NVDA"))
		self.Bind(wx.EVT_MENU, frame.onExitCommand, item)

		self.Bind(wx.EVT_TASKBAR_RIGHT_DOWN, self.onActivate)

	def Destroy(self):
		self.menu.Destroy()
		super(SysTrayIcon, self).Destroy()

	def onActivate(self, evt):
		self.PopupMenu(self.menu)
		# Showing and hiding our main frame seems to cause Windows to switch to the previous foreground window.
		# If we don't do this and no dialog was displayed, the user will be dumped in the invisible system tray window, which is bad.
		# It is even worse than expected because the user can close the system tray window, breaking the system tray icon.
		# Even if a dialog is displayed, this does no harm.
		mainFrame.postPopup()

def initialize(app):
	global mainFrame
	mainFrame = MainFrame()
	app.SetTopWindow(mainFrame)

def showGui():
 	wx.PostEvent(mainFrame, ExternalCommandEvent(id_showGuiCommand))

def quit():
	wx.PostEvent(mainFrame, ExternalCommandEvent(wx.ID_EXIT))

def abort():
	wx.PostEvent(mainFrame, ExternalCommandEvent(id_abortCommand))

def restart():
	globalVars.restart=True
	wx.PostEvent(mainFrame, ExternalCommandEvent(id_abortCommand))

def execute(func, callback=None, *args, **kwargs):
	"""Execute a function in the GUI thread.
	This should be used when scripts need to interact with the user via the GUI.
	For example, a frame or dialog can be created and this function can then be used to execute its Show method.
	@param func: The function to execute.
	@type func: callable
	@param callback: A function to call in the main thread when C{func} returns. The function will be passed the return value as its only argument.
	@type callback: callable
	@param args: Arguments for the function.
	@param kwargs: Keyword arguments for the function.
"""
	wx.PostEvent(mainFrame, ExternalExecuteEvent(func, args, kwargs, callback))
