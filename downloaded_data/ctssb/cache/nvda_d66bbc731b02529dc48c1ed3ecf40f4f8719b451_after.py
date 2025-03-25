from ctypes import *
from ctypes.wintypes import RECT
from comtypes import BSTR
import unicodedata
import math
import colors
import XMLFormatting
import api
import winUser
import NVDAHelper
import textInfos
from textInfos.offsets import OffsetsTextInfo
import watchdog
from logHandler import log

def detectStringDirection(s):
	direction=0
	for b in (unicodedata.bidirectional(ch) for ch in s):
		if b=='L': direction+=1
		if b in ('R','AL'): direction-=1
	return direction

def yieldListRange(l,start,stop):
	for x in xrange(start,stop):
		yield l[x]

def processFieldsAndRectsRangeReadingdirection(commandList,rects,startIndex,startOffset,endIndex,endOffset):
	containsRtl=False # True if any rtl text is found at all
	curFormatField=None 
	overallDirection=0 # The general reading direction calculated based on the amount of rtl vs ltr text there is
	# Detect the direction for fields with an unknown reading direction, and calculate an over all direction for the entire passage
	for index in xrange(startIndex,endIndex):
		item=commandList[index]
		if isinstance(item,textInfos.FieldCommand) and isinstance(item.field,textInfos.FormatField):
			curFormatField=item.field
		elif isinstance(item,basestring):
			direction=curFormatField['direction']
			if direction==0:
				curFormatField['direction']=direction=detectStringDirection(item)
			if direction<0:
				containsRtl=True
			overallDirection+=direction
	if not containsRtl:
		# As no rtl text was ever seen, then there is nothing else to do
		return
	if overallDirection==0: overallDirection=1
	# following the calculated over all reading direction of the passage, correct all weak/neutral fields to have the same reading direction as the field preceeding them 
	lastDirection=overallDirection
	for index in xrange(startIndex,endIndex):
		if overallDirection<0: index=endIndex-index-1
		item=commandList[index]
		if isinstance(item,textInfos.FieldCommand) and isinstance(item.field,textInfos.FormatField):
			direction=item.field['direction']
			if direction==0:
				item.field['direction']=lastDirection
			lastDirection=direction
	# For fields that are rtl, reverse their text, their rects, and the order of consecutive rtl fields 
	lastEndOffset=startOffset
	runDirection=None
	runStartIndex=None
	runStartOffset=None
	if overallDirection<0:
		reorderList=[]
	for index in xrange(startIndex,endIndex+1):
		item=commandList[index] if index<endIndex else None
		if isinstance(item,basestring):
			lastEndOffset+=len(item)
		elif not item or (isinstance(item,textInfos.FieldCommand) and isinstance(item.field,textInfos.FormatField)):
			direction=item.field['direction'] if item else None
			if direction is None or (direction!=runDirection): 
				if runDirection is not None:
					# This is the end of a run of consecutive fields of the same direction
					if runDirection<0:
						#This run is rtl, so reverse its rects, the text within the fields, and the order of fields themselves
						#Reverse rects
						rects[runStartOffset:lastEndOffset]=rects[lastEndOffset-1:runStartOffset-1 if runStartOffset>0 else None:-1]
						for i in xrange(runStartIndex,index,2):
							command=commandList[i]
							text=commandList[i+1]
							commandList[i+1]=command
							commandList[i]="".join(reversed(text))
						#Reverse commandList
						commandList[runStartIndex:index]=commandList[index-1:runStartIndex-1 if runStartIndex>0 else None:-1]
					if overallDirection<0:
						#As the overall reading direction of the passage is rtl, record the location of this run so we can reverse the order of runs later
						reorderList.append((runStartIndex,runStartOffset,index,lastEndOffset))
				if item:
					runStartIndex=index
					runStartOffset=lastEndOffset
					runDirection=direction
	if overallDirection<0:
		# As the overall reading direction of the passage is rtl, build a new command list and rects list with the order of runs reversed
		# The content of each run is already in logical reading order itself
		newCommandList=[]
		newRects=[]
		for si,so,ei,eo in reversed(reorderList):
			newCommandList.extend(yieldListRange(commandList,si,ei))
			newRects.extend(yieldListRange(rects,so,eo))
		# Finally update the original command list and rect list replacing the old content for this passage with the reordered runs
		commandList[startIndex:endIndex]=newCommandList
		rects[startOffset:endOffset]=newRects

_getWindowTextInRect=None
_requestTextChangeNotificationsForWindow=None
#: Objects that have registered for text change notifications.
_textChangeNotificationObjs=[]

def initialize():
	global _getWindowTextInRect,_requestTextChangeNotificationsForWindow
	_getWindowTextInRect=CFUNCTYPE(c_long,c_long,c_long,c_int,c_int,c_int,c_int,c_int,c_int,POINTER(BSTR),POINTER(BSTR))(('displayModel_getWindowTextInRect',NVDAHelper.localLib),((1,),(1,),(1,),(1,),(1,),(1,),(1,),(1,),(2,),(2,)))
	_requestTextChangeNotificationsForWindow=NVDAHelper.localLib.displayModel_requestTextChangeNotificationsForWindow

def getWindowTextInRect(bindingHandle, windowHandle, left, top, right, bottom,minHorizontalWhitespace,minVerticalWhitespace):
	text, cpBuf = watchdog.cancellableExecute(_getWindowTextInRect, bindingHandle, windowHandle, left, top, right, bottom,minHorizontalWhitespace,minVerticalWhitespace)
	if not text or not cpBuf:
		return u"",[]

	characterLocations = []
	cpBufIt = iter(cpBuf)
	for cp in cpBufIt:
		characterLocations.append((ord(cp), ord(next(cpBufIt)), ord(next(cpBufIt)), ord(next(cpBufIt))))
	return text, characterLocations

def requestTextChangeNotifications(obj, enable):
	"""Request or cancel notifications for when the display text changes in an NVDAObject.
	A textChange event (event_textChange) will be fired on the object when its text changes.
	Note that this event does not provide any information about the changed text itself.
	It is important to request that notifications be cancelled when you no longer require them or when the object is no longer in use,
	as otherwise, resources will not be released.
	@param obj: The NVDAObject for which text change notifications are desired.
	@type obj: NVDAObject
	@param enable: C{True} to enable notifications, C{False} to disable them.
	@type enable: bool
	"""
	if not enable:
		_textChangeNotificationObjs.remove(obj)
	watchdog.cancellableExecute(_requestTextChangeNotificationsForWindow, obj.appModule.helperLocalBindingHandle, obj.windowHandle, enable)
	if enable:
		_textChangeNotificationObjs.append(obj)

def textChangeNotify(windowHandle, left, top, right, bottom):
	for obj in _textChangeNotificationObjs:
		if windowHandle == obj.windowHandle:
			# It is safe to call this event from this RPC thread.
			# This avoids an extra core cycle.
			obj.event_textChange()

class DisplayModelTextInfo(OffsetsTextInfo):

	minHorizontalWhitespace=8
	minVerticalWhitespace=32

	def __init__(self, obj, position):
		if isinstance(position, textInfos.Rect):
			self._location = position.left, position.top, position.right, position.bottom
			position = textInfos.POSITION_ALL
		else:
			self._location = None
		super(DisplayModelTextInfo, self).__init__(obj, position)

	_cache__storyFieldsAndRects = True
	def _get__storyFieldsAndRects(self):
		if self._location:
			left, top, right, bottom = self._location
		else:
			try:
				left, top, width, height = self.obj.location
			except TypeError:
				# No location; nothing we can do.
				return [],[],[]
			right = left + width
			bottom = top + height
		bindingHandle=self.obj.appModule.helperLocalBindingHandle
		if not bindingHandle:
			log.debugWarning("AppModule does not have a binding handle")
			return [],[],[]
		text,rects=getWindowTextInRect(bindingHandle, self.obj.windowHandle, left, top, right, bottom, self.minHorizontalWhitespace, self.minVerticalWhitespace)
		if not text:
			return [],[],[]
		text="<control>%s</control>"%text
		commandList=XMLFormatting.XMLTextParser().parse(text)
		curFormatField=None
		lastEndOffset=0
		lineStartOffset=0
		lineStartIndex=0
		lineBaseline=None
		lineEndOffsets=[]
		for index in xrange(len(commandList)):
			item=commandList[index]
			if isinstance(item,basestring):
				lastEndOffset+=len(item)
			elif isinstance(item,textInfos.FieldCommand):
				if isinstance(item.field,textInfos.FormatField):
					curFormatField=item.field
					self._normalizeFormatField(curFormatField)
				else:
					curFormatField=None
				baseline=curFormatField['baseline'] if curFormatField  else None
				if baseline!=lineBaseline:
					if lineBaseline is not None:
						processFieldsAndRectsRangeReadingdirection(commandList,rects,lineStartIndex,lineStartOffset,index,lastEndOffset)
						lineEndOffsets.append(lastEndOffset)
					if baseline is not None:
						lineStartIndex=index
						lineStartOffset=lastEndOffset
						lineBaseline=baseline
		return commandList,rects,lineEndOffsets

	def _getStoryOffsetLocations(self):
		baseline=None
		direction=0
		lastEndOffset=0
		commandList,rects,lineEndOffsets=self._storyFieldsAndRects
		for item in commandList:
			if isinstance(item,textInfos.FieldCommand) and isinstance(item.field,textInfos.FormatField):
				baseline=item.field['baseline']
				direction=item.field['direction']
			elif isinstance(item,basestring):
				endOffset=lastEndOffset+len(item)
				for rect in rects[lastEndOffset:endOffset]:
					yield rect,baseline,direction
				lastEndOffset=endOffset

	def _getFieldsInRange(self,start,end):
		storyFields=self._storyFieldsAndRects[0]
		if not storyFields:
			return []
		#Strip  unwanted commands and text from the start and the end to honour the requested offsets
		lastEndOffset=0
		startIndex=endIndex=relStart=relEnd=None
		for index in xrange(len(storyFields)):
			item=storyFields[index]
			if isinstance(item,basestring):
				endOffset=lastEndOffset+len(item)
				if lastEndOffset<=start<endOffset:
					startIndex=index-1
					relStart=start-lastEndOffset
				if lastEndOffset<end<=endOffset:
					endIndex=index+1
					relEnd=end-lastEndOffset
				lastEndOffset=endOffset
		if startIndex is None:
			return []
		if endIndex is None:
			endIndex=len(storyFields)
		commandList=storyFields[startIndex:endIndex]
		if (endIndex-startIndex)==2 and relStart is not None and relEnd is not None:
			commandList[1]=commandList[1][relStart:relEnd]
		else:
			if relStart is not None:
				commandList[1]=commandList[1][relStart:]
			if relEnd is not None:
				commandList[-1]=commandList[-1][:relEnd]
		return commandList

	def _getStoryText(self):
		return u"".join(x for x in self._storyFieldsAndRects[0] if isinstance(x,basestring))

	def _getStoryLength(self):
		lineEndOffsets=self._storyFieldsAndRects[2]
		if lineEndOffsets:
			return lineEndOffsets[-1]+1
		return 0

	useUniscribe=False

	def _getTextRange(self, start, end):
		return u"".join(x for x in self._getFieldsInRange(start,end) if isinstance(x,basestring))

	def getTextWithFields(self,formatConfig=None):
		start=self._startOffset
		end=self._endOffset
		if start==end:
			return u""
		return self._getFieldsInRange(start,end)

	def _normalizeFormatField(self,field):
		field['bold']=True if field.get('bold')=="true" else False
		field['baseline']=int(field.get('baseline','-1'))
		field['direction']=int(field.get('direction','0'))
		field['italic']=True if field.get('italic')=="true" else False
		field['underline']=True if field.get('underline')=="true" else False
		color=field.get('color')
		if color is not None:
			field['color']=colors.RGB.fromCOLORREF(int(color))
		bkColor=field.get('background-color')
		if bkColor is not None:
			field['background-color']=colors.RGB.fromCOLORREF(int(bkColor))

	def _getPointFromOffset(self, offset):
		rects=self._storyFieldsAndRects[1]
		if not rects or offset>=len(rects):
			raise LookupError
		x,y=rects[offset][:2]
		return textInfos.Point(x, y)

	def _getOffsetFromPoint(self, x, y):
		for charOffset, (charLeft, charTop, charRight, charBottom) in enumerate(self._storyFieldsAndRects[1]):
			if charLeft<=x<charRight and charTop<=y<charBottom:
				return charOffset
		raise LookupError

	def _getClosestOffsetFromPoint(self,x,y):
		#Enumerate the character rectangles
		a=enumerate(self._storyFieldsAndRects[1])
		#Convert calculate center points for all the rectangles
		b=((charOffset,(charLeft+(charRight-charLeft)/2,charTop+(charBottom-charTop)/2)) for charOffset,(charLeft,charTop,charRight,charBottom) in a)
		#Calculate distances from all center points to the given x and y
		#But place the distance before the character offset, to make sorting by distance easier
		c=((math.sqrt(abs(x-cx)**2+abs(y-cy)**2),charOffset) for charOffset,(cx,cy) in b)
		#produce a static list of distances and character offsets, sorted by distance 
		d=sorted(c)
		#Return the lowest offset with the shortest distance
		return d[0][1] if len(d)>0 else 0

	def _getNVDAObjectFromOffset(self,offset):
		try:
			p=self._getPointFromOffset(offset)
		except (NotImplementedError,LookupError):
			return self.obj
		obj=api.getDesktopObject().objectFromPoint(p.x,p.y)
		from NVDAObjects.window import Window
		if not obj or not isinstance(obj,Window) or not winUser.isDescendantWindow(self.obj.windowHandle,obj.windowHandle):
			return self.obj
		return obj

	def _getOffsetsFromNVDAObject(self,obj):
		l=obj.location
		if not l:
			raise RuntimeError
		x=l[0]+(l[2]/2)
		y=l[1]+(l[3]/2)
		offset=self._getClosestOffsetFromPoint(x,y)
		return offset,offset

	def _getLineOffsets(self,offset):
		lineEndOffsets=self._storyFieldsAndRects[2]
		if not lineEndOffsets or offset>=lineEndOffsets[-1]:
			return offset,offset+1
		startOffset=0
		endOffset=0
		for lineEndOffset in lineEndOffsets: 
			startOffset=endOffset
			endOffset=lineEndOffset
			if lineEndOffset>offset:
				break
		return startOffset,endOffset

	def _get_clipboardText(self):
		return super(DisplayModelTextInfo,self).clipboardText.replace('\0',' ')

class EditableTextDisplayModelTextInfo(DisplayModelTextInfo):

	minHorizontalWhitespace=1
	minVerticalWhitespace=4

	def _findCaretOffsetFromLocation(self,caretRect,validateBaseline=True,validateDirection=True):
		for charOffset, ((charLeft, charTop, charRight, charBottom),charBaseline,charDirection) in enumerate(self._getStoryOffsetLocations()):
			# Skip any character that does not overlap the caret vertically
			if (caretRect.bottom<=charTop or caretRect.top>=charBottom):
				continue
			# Skip any character that does not overlap the caret horizontally
			if (caretRect.right<=charLeft or caretRect.left>=charRight):
				continue
			# skip over any character that does not have a baseline or who's baseline the caret does not go through
			if validateBaseline and (charBaseline<0 or not (caretRect.top<charBaseline<=caretRect.bottom)):
				continue
			# Does the caret hang off the right side of the character more than the left?
			if validateDirection:
				direction=max(0,charLeft-caretRect.left)-max(0,caretRect.right-charRight)
				# Skip any character who's reading direction disagrees with the caret's direction
				if (charDirection<0 and direction>0) or (not charDirection<0 and direction<0):
					continue
			return charOffset
		raise LookupError

	def _getCaretOffset(self):
		caretRect = winUser.getGUIThreadInfo(self.obj.windowThreadID).rcCaret
		objLocation=self.obj.location
		objRect=RECT(objLocation[0],objLocation[1],objLocation[0]+objLocation[2],objLocation[1]+objLocation[3])
		tempPoint = winUser.POINT()
		tempPoint.x=caretRect.left
		tempPoint.y=caretRect.top
		winUser.user32.ClientToScreen(self.obj.windowHandle, byref(tempPoint))
		caretRect.left=max(objRect.left,tempPoint.x)
		caretRect.top=max(objRect.top,tempPoint.y)
		tempPoint.x=caretRect.right
		tempPoint.y=caretRect.bottom
		winUser.user32.ClientToScreen(self.obj.windowHandle, byref(tempPoint))
		caretRect.right=min(objRect.right,tempPoint.x)
		caretRect.bottom=min(objRect.bottom,tempPoint.y)
		# Find a character offset where the caret overlaps vertically, overlaps horizontally, overlaps the baseline and is totally within or on the correct side for the reading order
		try:
			return self._findCaretOffsetFromLocation(caretRect,validateBaseline=True,validateDirection=True)
		except LookupError:
			pass
		# Find a character offset where the caret overlaps vertically, overlaps horizontally, overlaps the baseline, but does not care about reading order (probably whitespace at beginning or end of a line)
		try:
			return self._findCaretOffsetFromLocation(caretRect,validateBaseline=True,validateDirection=False)
		except LookupError:
			pass
		# Find a character offset where the caret overlaps vertically, overlaps horizontally, but does not care about baseline or reading order (probably vertical whitespace -- blank lines)
		return self._findCaretOffsetFromLocation(caretRect,validateBaseline=False,validateDirection=False)

	def _setCaretOffset(self,offset):
		rects=self._storyFieldsAndRects[1]
		if offset>=len(rects):
			raise RuntimeError("offset %d out of range")
		left,top,right,bottom=rects[offset]
		x=left #+(right-left)/2
		y=top+(bottom-top)/2
		oldX,oldY=winUser.getCursorPos()
		winUser.setCursorPos(x,y)
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN,0,0,None,None)
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP,0,0,None,None)
		winUser.setCursorPos(oldX,oldY)

	def _getSelectionOffsets(self):
		offset=self._getCaretOffset()
		return offset,offset

	def _setSelectionOffsets(self,start,end):
		if start!=end:
			raise TypeError("Expanded selections not supported")
		self._setCaretOffset(start)
