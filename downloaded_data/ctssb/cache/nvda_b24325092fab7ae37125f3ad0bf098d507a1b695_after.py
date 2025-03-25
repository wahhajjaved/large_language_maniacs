#appModules/_default.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2006-2007 NVDA Contributors <http://www.nvda-project.org/>
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

import gc
import comtypes.client
import datetime
import time
import tones
from keyUtils import key
import keyboardHandler
import IAccessibleHandler
import controlTypes
import api
import textHandler
import speech
import sayAllHandler
from NVDAObjects import NVDAObject, NVDAObjectTextInfo
import globalVars
from logHandler import log
from synthDriverHandler import *
import gui
import wx
import core
import config
import winUser
import appModuleHandler
import winKernel
import ctypes
from gui import mainFrame
import virtualBufferHandler
import scriptHandler

class appModule(appModuleHandler.AppModule):

	def event_switchStart(self,obj,nextHandler):
		speech.cancelSpeech()

	def event_switchEnd(self,obj,nextHandler):
		oldFocus = api.getFocusObject()
		api.processPendingEvents()
		if oldFocus != api.getFocusObject():
			return
		# Task switcher is gone, but no foreground or focus event was fired.
		# We must therefore find and restore the correct focus.
		speech.cancelSpeech()
		IAccessibleHandler.processFocusNVDAEvent(api.findObjectWithFocus())

	def script_keyboardHelp(self,keyPress):
		if not globalVars.keyboardHelp:
 			state=_("on")
			globalVars.keyboardHelp=True
		else:
			state=_("off")
			globalVars.keyboardHelp=False
		speech.speakMessage(_("keyboard help %s")%state)
	script_keyboardHelp.__doc__=_("Turns keyboard help on and off. When on, pressing a key on the keyboard will tell you what script is associated with it, if any.")

	def script_reportCurrentLine(self,keyPress):
		obj=api.getFocusObject()
		virtualBuffer=obj.virtualBuffer
		if hasattr(virtualBuffer,'TextInfo') and not virtualBuffer.passThrough:
			obj=virtualBuffer
		info=obj.makeTextInfo(textHandler.POSITION_CARET)
		info.expand(textHandler.UNIT_LINE)
		if scriptHandler.getLastScriptRepeateCount()==0:
			speech.speakTextInfo(info,reason=speech.REASON_CARET)
		else:
			speech.speakSpelling(info.text)
	script_reportCurrentLine.__doc__=_("Reports the current line under the application cursor. Pressing this key twice will spell the current line")

	def script_leftMouseClick(self,keyPress):
		speech.speakMessage(_("left click"))
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN,0,0,None,None)
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP,0,0,None,None)
	script_leftMouseClick.__doc__=_("Clicks the left mouse button once at the current mouse position")

	def script_rightMouseClick(self,keyPress):
		speech.speakMessage(_("right click"))
		winUser.mouse_event(winUser.MOUSEEVENTF_RIGHTDOWN,0,0,None,None)
		winUser.mouse_event(winUser.MOUSEEVENTF_RIGHTUP,0,0,None,None)
	script_rightMouseClick.__doc__=_("Clicks the right mouse button once at the current mouse position")

	def script_reportCurrentSelection(self,keyPress):
		obj=api.getFocusObject()
		virtualBuffer=obj.virtualBuffer
		if hasattr(virtualBuffer,'TextInfo') and not virtualBuffer.passThrough:
			obj=virtualBuffer
		info=obj.makeTextInfo(textHandler.POSITION_SELECTION)
		if info.isCollapsed:
			speech.speakMessage(_("no selection"))
		else:
			speech.speakMessage(_("selected %s")%info.text)
	script_reportCurrentSelection.__doc__=_("Announces the current selection in edit controls and documents. If there is no selection it says so.")

	def script_dateTime(self,keyPress):
		if scriptHandler.getLastScriptRepeateCount()==0:
			text=winKernel.GetTimeFormat(winKernel.getThreadLocale(), winKernel.TIME_NOSECONDS, None, None)
		else:
			text=winKernel.GetDateFormat(winKernel.getThreadLocale(), winKernel.DATE_LONGDATE, None, None)
		speech.speakMessage(text)
	script_dateTime.__doc__=_("If pressed once, reports the current time. If pressed twice, reports the current date")

	def script_increaseSynthSetting(self,keyPress):
		speech.speakMessage("%s %s" % (globalVars.settingsRing.currentSettingName, globalVars.settingsRing.increase()))
	script_increaseSynthSetting.__doc__=_("Increases the currently active setting in the synth settings ring")

	def script_decreaseSynthSetting(self,keyPress):
		speech.speakMessage("%s %s" % (globalVars.settingsRing.currentSettingName, globalVars.settingsRing.decrease()))
	script_decreaseSynthSetting.__doc__=_("Decreases the currently active setting in the synth settings ring")

	def script_nextSynthSetting(self,keyPress):
		speech.speakMessage("%s %s"%(globalVars.settingsRing.next(), globalVars.settingsRing._get_currentSettingValue()))
	script_nextSynthSetting.__doc__=_("Moves to the next available setting in the synth settings ring")

	def script_previousSynthSetting(self,keyPress):
		speech.speakMessage("%s %s"%(globalVars.settingsRing.previous(), globalVars.settingsRing._get_currentSettingValue()))
	script_previousSynthSetting.__doc__=_("Moves to the previous available setting in the synth settings ring")

	def script_toggleSpeakTypedCharacters(self,keyPress):
		if config.conf["keyboard"]["speakTypedCharacters"]:
			onOff=_("off")
			config.conf["keyboard"]["speakTypedCharacters"]=False
		else:
			onOff=_("on")
			config.conf["keyboard"]["speakTypedCharacters"]=True
		speech.speakMessage(_("speak typed characters")+" "+onOff)
	script_toggleSpeakTypedCharacters.__doc__=_("Toggles on and off the speaking of typed characters")

	def script_toggleSpeakTypedWords(self,keyPress):
		if config.conf["keyboard"]["speakTypedWords"]:
			onOff=_("off")
			config.conf["keyboard"]["speakTypedWords"]=False
		else:
			onOff=_("on")
			config.conf["keyboard"]["speakTypedWords"]=True
		speech.speakMessage(_("speak typed words")+" "+onOff)
	script_toggleSpeakTypedWords.__doc__=_("Toggles on and off the speaking of typed words")

	def script_toggleSpeakCommandKeys(self,keyPress):
		if config.conf["keyboard"]["speakCommandKeys"]:
			onOff=_("off")
			config.conf["keyboard"]["speakCommandKeys"]=False
		else:
			onOff=_("on")
			config.conf["keyboard"]["speakCommandKeys"]=True
		speech.speakMessage(_("speak command keys")+" "+onOff)
	script_toggleSpeakCommandKeys.__doc__=_("Toggles on and off the speaking of typed keys, that are not specifically characters")

	def script_toggleSpeakPunctuation(self,keyPress):
		if config.conf["speech"]["speakPunctuation"]:
			onOff=_("off")
			config.conf["speech"]["speakPunctuation"]=False
		else:
			onOff=_("on")
			config.conf["speech"]["speakPunctuation"]=True
		speech.speakMessage(_("speak punctuation")+" "+onOff)
	script_toggleSpeakPunctuation.__doc__=_("Toggles on and off the speaking of punctuation. When on NVDA will say the names of punctuation symbols, when off it will be up to the synthesizer as to how it speaks punctuation")

	def script_moveMouseToNavigatorObject(self,keyPress):
		speech.speakMessage(_("Move mouse to navigator"))
		obj=api.getNavigatorObject() 
		try:
			p=api.getReviewPosition().pointAtStart
		except NotImplementedError:
			p=None
		if p:
			winUser.setCursorPos(p.x,p.y)
		else:
			try:
				(left,top,width,height)=obj.location
			except:
				speech.speakMessage(_("object has no location"))
				return
			winUser.setCursorPos(left+(width/2),top+(height/2))
	script_moveMouseToNavigatorObject.__doc__=_("Moves the mouse pointer to the current navigator object")

	def script_moveNavigatorObjectToMouse(self,keyPress):
		speech.speakMessage(_("Move navigator object to mouse"))
		obj=api.getMouseObject()
		api.setNavigatorObject(obj)
		speech.speakObject(obj)
	script_moveNavigatorObjectToMouse.__doc__=_("Sets the navigator object to the current object under the mouse pointer and speaks it")

	def script_navigatorObject_current(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		if scriptHandler.getLastScriptRepeateCount()>=1:
			textList=[]
			if isinstance(curObject.name,basestring) and len(curObject.name)>0 and not curObject.name.isspace():
				textList.append(curObject.name)
			if isinstance(curObject.value,basestring) and len(curObject.value)>0 and not curObject.value.isspace():
				textList.append(curObject.value)
			if curObject.TextInfo!=NVDAObjectTextInfo:
				info=curObject.makeTextInfo(textHandler.POSITION_SELECTION)
				if info.text and not info.isCollapsed:
					textList.append(info.text)
				else:
					info.expand(textHandler.UNIT_READINGCHUNK)
					if info.text:
						textList.append(info.text)
			text=" ".join(textList)
			if len(text)>0 and not text.isspace():
				if scriptHandler.getLastScriptRepeateCount()==1:
					speech.speakSpelling(text)
				else:
					if api.copyToClip(text):
						speech.speakMessage(_("%s copied to clipboard")%text)
		else:
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		return False
	script_navigatorObject_current.__doc__=_("Reports the current navigator object or, if pressed three times, Copies name and value of current navigator object to the clipboard")

	def script_navigatorObject_currentDimensions(self,keyPress):
		obj=api.getNavigatorObject()
		if not obj:
			speech.speakMessage(_("no navigator object"))
		location=obj.location
		if not location:
			speech.speakMessage(_("No location information for navigator object"))
		(left,top,width,height)=location
		(deskLeft,deskTop,deskWidth,deskHeight)=api.getDesktopObject().location
		speech.speakMessage(_("Object edges positioned %.1f per cent right from left of screen, %.1f per cent down from top of screen, %.1f per cent left from right of screen, %.1f up from bottom of screen")%((float(left)/deskWidth)*100,(float(top)/deskHeight)*100,100-((float(width+left)/deskWidth)*100),100-(float(height+top)/deskHeight)*100))
	script_navigatorObject_currentDimensions.__doc__=_("Reports the hight, width and position of the current navigator object")

	def script_navigatorObject_toFocus(self,keyPress):
		obj=api.getFocusObject()
		if not isinstance(obj,NVDAObject):
			speech.speakMessage(_("no focus"))
		api.setNavigatorObject(obj)
		speech.speakMessage(_("move to focus"))
		speech.speakObject(obj,reason=speech.REASON_QUERY)
	script_navigatorObject_toFocus.__doc__=_("Sets the navigator object to the current focus")

	def script_navigatorObject_parent(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		curObject=curObject.parent
		if curObject is not None:
			api.setNavigatorObject(curObject)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("No parents"))
	script_navigatorObject_parent.__doc__=_("Sets the navigator object to the parent of the object it is currently on and speaks it")

	def script_navigatorObject_next(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		curObject=curObject.next
		if curObject is not None:
			api.setNavigatorObject(curObject)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("No next"))
	script_navigatorObject_next.__doc__=_("Sets the navigator object to the object next to the one it is currently on and speaks it")

	def script_navigatorObject_previous(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		curObject=curObject.previous
		if curObject is not None:
			api.setNavigatorObject(curObject)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("No previous"))
	script_navigatorObject_previous.__doc__=_("Sets the navigator object to the object previous to the one it is currently on and speaks it")

	def script_navigatorObject_firstChild(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		curObject=curObject.firstChild
		if curObject is not None:
			api.setNavigatorObject(curObject)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("No children"))
	script_navigatorObject_firstChild.__doc__=_("Sets the navigator object to the first child object of the one it is currently on and speaks it")

	def script_navigatorObject_nextInFlow(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		up=[]
		down=[]
		curObject=curObject.getNextInFlow(up=up,down=down)
		if curObject is not None:
			api.setNavigatorObject(curObject)
			if len(up)>0:
				for count in range(len(up)+1):
					tones.beep(880*(1.25**count),50)
					time.sleep(0.025)
			if len(down)>0:
				for count in range(len(down)+1):
					tones.beep(880/(1.25**count),50)
					time.sleep(0.025)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("end of flow"))
	script_navigatorObject_nextInFlow.__doc__=_("Sets the navigator object to the object this object flows to and speaks it")

	def script_navigatorObject_previousInFlow(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		up=[]
		down=[]
		curObject=curObject.getPreviousInFlow(up=up,down=down)
		if curObject is not None:
			api.setNavigatorObject(curObject)
			if len(up)>0:
				for count in range(len(up)+1):
					tones.beep(880*(1.25**count),50)
					time.sleep(0.025)
			if len(down)>0:
				for count in range(len(down)+1):
					tones.beep(880/(1.25**count),50)
					time.sleep(0.025)
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
		else:
			speech.speakMessage(_("Beginning of flow"))
	script_navigatorObject_previousInFlow.__doc__=_("Sets the navigator object to the object this object flows from and speaks it")

	def script_navigatorObject_doDefaultAction(self,keyPress):
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		curObject.doDefaultAction()
	script_navigatorObject_doDefaultAction.__doc__=_("Performs the default action on the current navigator object (example: presses it if it is a button).")

	def script_navigatorObject_where(self,keyPress):
		"""Reports where the current navigator object is by reporting each of its ancestors""" 
		curObject=api.getNavigatorObject()
		if not isinstance(curObject,NVDAObject):
			speech.speakMessage(_("no navigator object"))
			return
		speech.speakObject(curObject,reason=speech.REASON_QUERY)
		curObject=curObject.parent
		while curObject is not None:
			speech.speakMessage(_("inside"))
			speech.speakObject(curObject,reason=speech.REASON_QUERY)
			curObject=curObject.parent
	script_navigatorObject_where.__doc__=_("Reports where the current navigator object is by reporting each of its ancestors")

	def script_review_top(self,keyPress):
		info=api.getReviewPosition().obj.makeTextInfo(textHandler.POSITION_FIRST)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_LINE)
		speech.speakMessage(_("top"))
		speech.speakTextInfo(info)
	script_review_top.__doc__=_("Moves the review cursor to the top line of the current navigator object and speaks it")

	def script_review_previousLine(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		info.collapse()
		res=info.move(textHandler.UNIT_LINE,-1)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_LINE)
		if res==0:
			speech.speakMessage(_("top"))
		speech.speakTextInfo(info)
	script_review_previousLine.__doc__=_("Moves the review cursor to the previous line of the current navigator object and speaks it")

	def script_review_currentLine(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		if scriptHandler.getLastScriptRepeateCount()==0:
			speech.speakTextInfo(info)
		else:
			speech.speakSpelling(info._get_text())
	script_review_currentLine.__doc__=_("Reports the line of the current navigator object where the review cursor is situated. If this key is pressed twice, the current line will be spelled")

	def script_review_nextLine(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		info.collapse()
		res=info.move(textHandler.UNIT_LINE,1)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_LINE)
		if res==0:
			speech.speakMessage(_("bottom"))
		speech.speakTextInfo(info)
	script_review_nextLine.__doc__=_("Moves the review cursor to the next line of the current navigator object and speaks it")

	def script_review_bottom(self,keyPress):
		info=api.getReviewPosition().obj.makeTextInfo(textHandler.POSITION_LAST)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_LINE)
		speech.speakMessage(_("bottom"))
		speech.speakTextInfo(info)
	script_review_bottom.__doc__=_("Moves the review cursor to the bottom line of the current navigator object and speaks it")

	def script_review_previousWord(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_WORD)
		info.collapse()
		res=info.move(textHandler.UNIT_WORD,-1)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_WORD)
		if res==0:
			speech.speakMessage(_("top"))
		speech.speakTextInfo(info)
	script_review_previousWord.__doc__=_("Moves the review cursor to the previous word of the current navigator object and speaks it")

	def script_review_currentWord(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_WORD)
		if scriptHandler.getLastScriptRepeateCount()==0:
			speech.speakTextInfo(info)
		else:
			speech.speakSpelling(info._get_text())
	script_review_currentWord.__doc__=_("Speaks the word of the current navigator object where the review cursor is situated. If this key is pressed twice, the word will be spelled")

	def script_review_nextWord(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_WORD)
		info.collapse()
		res=info.move(textHandler.UNIT_WORD,1)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_WORD)
		if res==0:
			speech.speakMessage(_("bottom"))
		speech.speakTextInfo(info)
	script_review_nextWord.__doc__=_("Moves the review cursor to the next word of the current navigator object and speaks it")

	def script_review_startOfLine(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		info.collapse()
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_CHARACTER)
		speech.speakMessage(_("left"))
		speech.speakTextInfo(info,handleSymbols=True)
	script_review_startOfLine.__doc__=_("Moves the review cursor to the first character of the line where it is situated in the current navigator object and speaks it")

	def script_review_previousCharacter(self,keyPress):
		lineInfo=api.getReviewPosition().copy()
		lineInfo.expand(textHandler.UNIT_LINE)
		charInfo=api.getReviewPosition().copy()
		charInfo.expand(textHandler.UNIT_CHARACTER)
		charInfo.collapse()
		res=charInfo.move(textHandler.UNIT_CHARACTER,-1)
		if res==0 or charInfo.compareEndPoints(lineInfo,"startToStart")<0:
			speech.speakMessage(_("left"))
			reviewInfo=api.getReviewPosition().copy()
			reviewInfo.expand(textHandler.UNIT_CHARACTER)
			speech.speakSpelling(reviewInfo.text)
		else:
			api.setReviewPosition(charInfo.copy())
			charInfo.expand(textHandler.UNIT_CHARACTER)
			speech.speakTextInfo(charInfo,handleSymbols=True)
	script_review_previousCharacter.__doc__=_("Moves the review cursor to the previous character of the current navigator object and speaks it")

	def script_review_currentCharacter(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_CHARACTER)
		if scriptHandler.getLastScriptRepeateCount()==0:
			speech.speakTextInfo(info,handleSymbols=True)
		else:
			try:
				c = ord(info._get_text())
				speech.speakMessage("%d," % c)
				speech.speakSpelling(hex(c))
			except:
				speech.speakTextInfo(info,handleSymbols=True)
	script_review_currentCharacter.__doc__=_("Reports the character of the current navigator object where the review cursor is situated. If this key is pressed twice, ascii and hexadecimal values are spoken for the character")

	def script_review_nextCharacter(self,keyPress):
		lineInfo=api.getReviewPosition().copy()
		lineInfo.expand(textHandler.UNIT_LINE)
		charInfo=api.getReviewPosition().copy()
		charInfo.expand(textHandler.UNIT_CHARACTER)
		charInfo.collapse()
		res=charInfo.move(textHandler.UNIT_CHARACTER,1)
		if res==0 or charInfo.compareEndPoints(lineInfo,"endToEnd")>=0:
			speech.speakMessage(_("right"))
			reviewInfo=api.getReviewPosition().copy()
			reviewInfo.expand(textHandler.UNIT_CHARACTER)
			speech.speakSpelling(reviewInfo.text)
		else:
			api.setReviewPosition(charInfo.copy())
			charInfo.expand(textHandler.UNIT_CHARACTER)
			speech.speakTextInfo(charInfo,handleSymbols=True)
	script_review_nextCharacter.__doc__=_("Moves the review cursor to the next character of the current navigator object and speaks it")

	def script_review_endOfLine(self,keyPress):
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		info.collapse(end=True)
		info.move(textHandler.UNIT_CHARACTER,-1)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_CHARACTER)
		speech.speakMessage(_("right"))
		speech.speakTextInfo(info,handleSymbols=True)
	script_review_endOfLine.__doc__=_("Moves the review cursor to the last character of the line where it is situated in the current navigator object and speaks it")

	def script_review_moveToCaret(self,keyPress):
		info=api.getReviewPosition().obj.makeTextInfo(textHandler.POSITION_CARET)
		api.setReviewPosition(info.copy())
		info.expand(textHandler.UNIT_LINE)
		speech.speakTextInfo(info)
	script_review_moveToCaret.__doc__=_("Moves the review cursor to the position of the system caret, in the current navigator object")

	def script_review_moveCaretHere(self,keyPress):
		api.getReviewPosition().updateCaret()
		info=api.getReviewPosition().copy()
		info.expand(textHandler.UNIT_LINE)
		speech.speakTextInfo(info)
	script_review_moveCaretHere.__doc__=_("Moves the system caret to the position of the review cursor , in the current navigator object")

	def script_speechMode(self,keyPress):
		curMode=speech.speechMode
		speech.speechMode=speech.speechMode_talk
		newMode=(curMode+1)%3
		if newMode==speech.speechMode_off:
			name=_("off")
		elif newMode==speech.speechMode_beeps:
			name=_("beeps")
		elif newMode==speech.speechMode_talk:
			name=_("talk")
		speech.cancelSpeech()
		speech.speakMessage(_("speech mode %s")%name)
		speech.speechMode=newMode
	script_speechMode.__doc__=_("Toggles between the speech modes of off, beep and talk. When set to off NVDA will not speak anything. If beeps then NVDA will simply beep each time it its supposed to speak something. If talk then NVDA wil just speak normally.")

	def script_toggleVirtualBufferPassThrough(self,keyPress):
		vbuf = api.getFocusObject().virtualBuffer
		if not vbuf:
			return
		vbuf.passThrough = not vbuf.passThrough
		virtualBufferHandler.reportPassThrough(vbuf)
	script_toggleVirtualBufferPassThrough.__doc__=_("Toggles virtualBuffer pass-through mode on and off. When on, keys will pass straight through the current virtualBuffer, allowing you to interact with a control without the virtualBuffer doing something else with the key.")

	def script_quit(self,keyPress):
		gui.quit()
	script_quit.__doc__=_("Quits NVDA!")

	def script_showGui(self,keyPress):
		gui.showGui()
	script_showGui.__doc__=_("Shows the NVDA menu")

	def script_review_sayAll(self,keyPress):
		info=api.getReviewPosition().copy()
		sayAllHandler.readText(info,sayAllHandler.CURSOR_REVIEW)
	script_review_sayAll.__doc__ = _("reads from the review cursor  up to end of current text, moving the review cursor as it goes")

	def script_navigatorObject_sayAll(self,keyPress):
		obj=api.getNavigatorObject()
		sayAllHandler.readObjects(obj)
	script_navigatorObject_sayAll.__doc__ = _("reads from the navigator object ")

	def script_sayAll(self,keyPress):
		o=api.getFocusObject()
		v=o.virtualBuffer
		if v and not hasattr(v,'TextInfo') and not v.passThrough:
			sayAllHandler.sayAll(v.text_reviewPosition,v.text_characterCount,v.text_getNextLineOffsets,v.text_getText,v.text_reportNewPresentation,v._set_text_reviewPosition)
		else:
			if hasattr(v,'TextInfo') and not v.passThrough:
				o=v
			info=o.makeTextInfo(textHandler.POSITION_CARET)
			sayAllHandler.readText(info,sayAllHandler.CURSOR_CARET)
	script_sayAll.__doc__ = _("reads from the system caret up to the end of the text, moving the caret as it goes")

	def script_reportFormatting(self,keyPress):
		formatConfig={
			"reportFontName":True,"reportFontSize":True,"reportFontAttributes":True,
			"reportStyle":True,"reportAlignment":True,"reportSpellingErrors":True,
			"reportPage":False,"reportLineNumber":False,"reportTables":False,
			"reportLinks":False,"reportHeadings":False,"reportLists":False,
			"reportBlockQuotes":False,
		}
		o=api.getFocusObject()
		info=o.makeTextInfo(textHandler.POSITION_CARET)
		info.expand(textHandler.UNIT_CHARACTER)
		formatField=textHandler.FormatField()
		for field in info.getInitialFields(formatConfig):
			if isinstance(field,textHandler.FormatField):
				formatField.update(field)
		speechText=speech.getFormatFieldSpeech(formatField,formatConfig=formatConfig)
		speech.speakMessage(speechText)

	def script_reportCurrentFocus(self,keyPress):
		focusObject=api.findObjectWithFocus() #getFocusObject()
		if isinstance(focusObject,NVDAObject):
			if scriptHandler.getLastScriptRepeateCount()==0:
				speech.speakObject(focusObject, reason=speech.REASON_QUERY)
			else:
				speech.speakSpelling(focusObject.name)
		else:
			speech.speakMessage(_("no focus"))
	script_reportCurrentFocus.__doc__ = _("reports the object with focus")

	def script_reportStatusLine(self,keyPress):
		obj = api.getStatusBar()
		if not obj:
			speech.speakMessage(_("no status bar found"))
			return
		text = api.getStatusBarText(obj)

		if scriptHandler.getLastScriptRepeateCount()==0:
			speech.speakMessage(text)
		else:
			speech.speakSpelling(text)
		api.setNavigatorObject(obj)
	script_reportStatusLine.__doc__ = _("reads the current application status bar and moves the navigator to it")

	def script_toggleMouseTracking(self,keyPress):
		if config.conf["mouse"]["enableMouseTracking"]:
			onOff=_("off")
			config.conf["mouse"]["enableMouseTracking"]=False
		else:
			onOff=_("on")
			config.conf["mouse"]["enableMouseTracking"]=True
		speech.speakMessage(_("Mouse tracking")+" "+onOff)
	script_toggleMouseTracking.__doc__=_("Toggles the reporting of information as the mouse moves")

	def script_title(self,keyPress):
		obj=api.getForegroundObject()
		if obj:
			speech.speakObject(obj,reason=speech.REASON_QUERY)
	script_title.__doc__=_("Reports the title of the current application or foreground window")

	def script_speakForeground(self,keyPress):
		obj=api.getForegroundObject()
		if obj:
			speech.speakObject(obj,reason=speech.REASON_QUERY)
			obj.speakDescendantObjects()
	script_speakForeground.__doc__ = _("speaks the current foreground object")

	def script_test_navigatorWindowInfo(self,keyPress):
		obj=api.getNavigatorObject()
		import ctypes
		import winUser
		w=ctypes.windll.user32.GetAncestor(obj.windowHandle,3)
		w=ctypes.windll.user32.GetAncestor(w,3)
		className=winUser.getClassName(w)
		speech.speakMessage("%s, %s"%(w,className))
		if not isinstance(obj,NVDAObject): 
			speech.speakMessage(_("no navigator object"))
			return
		if scriptHandler.getLastScriptRepeateCount()>=1:
			if api.copyToClip("Control ID: %s\r\nClass: %s\r\ninternal text: %s"%(winUser.getControlID(obj.windowHandle),obj.windowClassName,winUser.getWindowText(obj.windowHandle))):
				speech.speakMessage(_("copied to clipboard"))
		else:
			log.info("%s %s"%(obj.role,obj.windowHandle))
			speech.speakMessage("%s"%obj)
			speech.speakMessage(_("Control ID: %s")%winUser.getControlID(obj.windowHandle))
			speech.speakMessage(_("Class: %s")%obj.windowClassName)
			speech.speakSpelling(obj.windowClassName)
			speech.speakMessage(_("internal text: %s")%winUser.getWindowText(obj.windowHandle))
			speech.speakMessage(_("text: %s")%obj.windowText)
			speech.speakMessage("is unicode: %s"%ctypes.windll.user32.IsWindowUnicode(obj.windowHandle))
	script_test_navigatorWindowInfo.__doc__ = _("reports some information about the current navigator object, mainly useful for developers. When pressed 2 times it copies control id, class and internal text to the windows clipboard")

	def script_toggleBeepOnProgressBarUpdates(self,keyPress):
		progressLabels = (
			("off", _("off")),
			("visible", _("Beep for visible")),
			("all", _("Beep for all")),
			("speak", _("Speak each 10 percent"))
		)

		for index, (setting, name) in enumerate(progressLabels):
			if setting == config.conf["presentation"]["reportProgressBarUpdates"]:
				new=(index+1)%4
				break
		config.conf["presentation"]["reportProgressBarUpdates"]=progressLabels[new][0]
		speech.cancelSpeech()
		speech.speakMessage(progressLabels[new][1])
	script_toggleBeepOnProgressBarUpdates.__doc__=_("Toggles how NVDA reports progress bar updates. It can beep for all the progress bars or just for the progressbars in the foreground. Additionally it is possible to have current value spoken each 10 percent or it is possible to completely disable this reporting.")

	def script_toggleReportDynamicContentChanges(self,keyPress):
		if globalVars.reportDynamicContentChanges:
			onOff=_("off")
			globalVars.reportDynamicContentChanges=False
		else:
			onOff=_("on")
			globalVars.reportDynamicContentChanges=True
		speech.speakMessage(_("report dynamic content changes")+" "+onOff)
	script_toggleReportDynamicContentChanges.__doc__=_("Toggles on and off the reporting of dynamic content changes, such as new text in dos console windows")

	def script_toggleCaretMovesReviewCursor(self,keyPress):
		if globalVars.caretMovesReviewCursor:
			onOff=_("off")
			globalVars.caretMovesReviewCursor=False
		else:
			onOff=_("on")
			globalVars.caretMovesReviewCursor=True
		speech.speakMessage(_("caret moves review cursor")+" "+onOff)
	script_toggleCaretMovesReviewCursor.__doc__=_("Toggles on and off the movement of the review cursor due to the caret moving.")

	def script_toggleFocusMovesNavigatorObject(self,keyPress):
		if globalVars.focusMovesNavigatorObject:
			onOff=_("off")
			globalVars.focusMovesNavigatorObject=False
		else:
			onOff=_("on")
			globalVars.focusMovesNavigatorObject=True
		speech.speakMessage(_("focus moves navigator object")+" "+onOff)
	script_toggleFocusMovesNavigatorObject.__doc__=_("Toggles on and off the movement of the navigator object due to focus changes") 

	#added by Rui Batista<ruiandrebatista@gmail.com> to implement a battery status script
	def script_say_battery_status(self,keyPress):
		UNKNOWN_BATTERY_STATUS = 0xFF
		AC_ONLINE = 0X1
		NO_SYSTEM_BATTERY = 0X80
		sps = winKernel.SYSTEM_POWER_STATUS()
		if not winKernel.GetSystemPowerStatus(sps) or sps.BatteryFlag is UNKNOWN_BATTERY_STATUS:
			log.error("error accessing system power status")
			return
		if sps.BatteryFlag & NO_SYSTEM_BATTERY:
			speech.speakMessage(_("no system battery"))
			return
		text = _("%d percent") % sps.BatteryLifePercent + " "
		if sps.ACLineStatus & AC_ONLINE: text += _("AC power on")
		elif sps.BatteryLifeTime!=0xffffffff: 
			text += _("%d hours and %d minutes remaining") % (sps.BatteryLifeTime / 3600, (sps.BatteryLifeTime % 3600) / 60)
		speech.speakMessage(text)
	script_say_battery_status.__doc__ = _("reports battery status and time remaining if AC is not plugged in")

	def script_passNextKeyThrough(self,keyPress):
		keyboardHandler.passNextKeyThrough()
		speech.speakMessage(_("Pass next key through"))
 	script_passNextKeyThrough.__doc__=_("The next key that is pressed will not be handled at all by NVDA, it will be passed directly through to Windows.")

	def script_speakApplicationName(self,keyPress):
		s=appModuleHandler.getAppName(api.getForegroundObject().windowHandle,True)
		speech.speakMessage(_("Currently running application is %s.")%s)
		speech.speakSpelling(s)
		if appModuleHandler.moduleExists(appModuleHandler.activeModule.appName):
			mod = appModuleHandler.activeModule.appName
		else:
			mod = _("default module")
		speech.speakMessage(_("and currently loaded module is %s") % mod)
	script_speakApplicationName.__doc__ = _("Speaks filename of the active application along with name of the currently loaded appmodule")

	def script_activateGeneralSettingsDialog(self,keyPress):
		mainFrame.onGeneralSettingsCommand(None)
	script_activateGeneralSettingsDialog.__doc__ = _("Shows the NVDA general settings dialog")

	def script_activateSynthesizerDialog(self,keyPress):
		mainFrame.onSynthesizerCommand(None)
	script_activateSynthesizerDialog.__doc__ = _("Shows the NVDA synthesizer dialog")

	def script_activateVoiceDialog(self,keyPress):
		mainFrame.onVoiceCommand(None)
	script_activateVoiceDialog.__doc__ = _("Shows the NVDA voice settings dialog")

	def script_activateKeyboardSettingsDialog(self,keyPress):
		mainFrame.onKeyboardSettingsCommand(None)
	script_activateKeyboardSettingsDialog.__doc__ = _("Shows the NVDA keyboard settings dialog")

	def script_activateMouseSettingsDialog(self,keyPress):
		mainFrame.onMouseSettingsCommand(None)
	script_activateMouseSettingsDialog.__doc__ = _("Shows the NVDA mouse settings dialog")

	def script_activateObjectPresentationDialog(self,keyPress):
		mainFrame. onObjectPresentationCommand(None)
	script_activateObjectPresentationDialog.__doc__ = _("Shows the NVDA object presentation settings dialog")

	def script_activateVirtualBuffersDialog(self,keyPress):
		mainFrame.onVirtualBuffersCommand(None)
	script_activateVirtualBuffersDialog.__doc__ = _("Shows the NVDA virtual buffers settings dialog")

	def script_activateDocumentFormattingDialog(self,keyPress):
		mainFrame.onDocumentFormattingCommand(None)
	script_activateDocumentFormattingDialog.__doc__ = _("Shows the NVDA document formatting settings dialog")

	def script_saveConfiguration(self,keyPress):
		wx.CallAfter(mainFrame.onSaveConfigurationCommand, None)
	script_saveConfiguration.__doc__ = _("Saves the current NVDA configuration")

	def script_revertToSavedConfiguration(self,keyPress):
		mainFrame.onRevertToSavedConfigurationCommand(None)
	script_revertToSavedConfiguration.__doc__ = _("loads the saved NVDA configuration, overriding current changes")

	def script_activatePythonConsole(self,keyPress):
		import pythonConsole
		if not pythonConsole.consoleUI:
			pythonConsole.initialize()
		pythonConsole.consoleUI.updateNamespaceSnapshotVars()
		pythonConsole.activate()
	script_activatePythonConsole.__doc__ = _("Activates the NVDA Python Console, primarily useful for development")
