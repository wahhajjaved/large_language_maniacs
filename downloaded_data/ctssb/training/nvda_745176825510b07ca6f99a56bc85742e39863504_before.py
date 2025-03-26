from . import VirtualBuffer, VirtualBufferTextInfo
from virtualBuffer_new_wrapper import *
import controlTypes
import NVDAObjects.IAccessible
import winUser
import speech
import IAccessibleHandler
import globalVars
import api
import textHandler

class IAccessibleTextInfo(VirtualBufferTextInfo):

	def getXMLFieldSpeech(self,attrs,fieldType,extraDetail=False,reason=None):
		hasIAccessible2=int(attrs['iaccessible2'])
		accRole=attrs['iaccessible::role']
		accRole=int(accRole) if accRole.isdigit() else accRole
		role=IAccessibleHandler.IAccessibleRolesToNVDARoles.get(accRole,controlTypes.ROLE_UNKNOWN)
		states=set(IAccessibleHandler.IAccessibleStatesToNVDAStates[x] for x in [1<<y for y in xrange(32)] if int(attrs.get('iaccessible::state_%s'%x,0)) and x in IAccessibleHandler.IAccessibleStatesToNVDAStates)
		if hasIAccessible2:
			states|=set(IAccessibleHandler.IAccessible2StatesToNVDAStates[x] for x in [1<<y for y in xrange(32)] if int(attrs.get('iaccessible2::state_%s'%x,0)) and x in IAccessibleHandler.IAccessible2StatesToNVDAStates)
		newAttrs=attrs.copy()
		newAttrs['role']=role
		newAttrs['states']=states
		return super(IAccessibleTextInfo,self).getXMLFieldSpeech(newAttrs,fieldType,extraDetail=extraDetail,reason=reason)


class IAccessible(VirtualBuffer):

	def __init__(self,rootNVDAObject):
		super(IAccessible,self).__init__(rootNVDAObject,TextInfo=IAccessibleTextInfo)

	def _fillVBufHelper(self,pacc=None,accChildID=0,parentNode=None,previousNode=None):
		if not pacc:
			pacc=self.rootNVDAObject.IAccessibleObject
		if not parentNode:
			parentNode=self.VBufHandle
		attrs={}
		isBlockElement=True
		if isinstance(pacc,IAccessibleHandler.IAccessible2):
			IAccessible2=1
			docHandle=IAccessibleHandler.windowFromAccessibleObject(pacc)
			ID=pacc.uniqueID
			role=pacc.role()
			if not role:
				role=pacc.accRole(accChildID)
			IAccessible2States=pacc.states
			objAttributes=pacc.attributes
			if role!=IAccessibleHandler.ROLE_SYSTEM_CELL and objAttributes.find("formatting:block")<0:
				isBlockElement=False
		else:
			IAccessible2=0
			docHandle=IAccessibleHandler.windowFromAccessibleObject(pacc)
			ID=-hash(pacc)
			role=pacc.accRole(accChildID)
		if role=="embed":
			return
		states=pacc.accState(accChildID)
		keyboardShortcut=pacc.accKeyboardShortcut(accChildID)
		attrs['IAccessible2']=unicode(IAccessible2)
		attrs['IAccessible::role']=unicode(role)
		for bitPos in xrange(32):
			state=1<<bitPos;
			if state&states:
				attrs["IAccessible::state_%d"%state]="1"
			if IAccessible2 and state&IAccessible2States:
					attrs["IAccessible2::state_%d"%state]="1"
		attrs['keyboardShortcut']=keyboardShortcut if keyboardShortcut else ""
		if IAccessible2:
			for attrib in objAttributes.split(';'):
				split=attrib.find(':')
				if split>=0:
					name=attrib[0:split]
					value=attrib[split+1:]
				else:
					name=attrib
					value=""
			attrs['IAccessible2::attribute_%s'%name]=value
		children=[] #will be strings  or pacc,childID tuples
		if not accChildID and isinstance(pacc,IAccessibleHandler.IAccessible2) and role!=IAccessibleHandler.ROLE_SYSTEM_COMBOBOX and (role!=IAccessibleHandler.ROLE_SYSTEM_LIST or IAccessibleHandler.STATE_SYSTEM_READONLY&states):
			try:
				paccText=pacc.QueryInterface(IAccessibleHandler.IAccessibleText)
			except:
				globalVars.log.debug("no IAccessibleText",exc_info=True)
				paccText=None
		else:
			paccText=None
		if paccText:
			try:
				text=paccText.text(0,-1)
			except:
				globalVars.log.debug("error in IAccessibleText::text, role %s"%pacc.role(),exc_info=True)
				text=""
		else:
			text=""
		if paccText and text:
			try:
				paccHypertext=pacc.QueryInterface(IAccessibleHandler.IAccessibleHypertext)
			except:
				globalVars.log.debug("no IAccessibleHypertext",exc_info=True)
				paccHypertext=None
			offset=0
			plainText=u""
			for ch in text:
				if not paccHypertext or ord(ch)!=0xfffc:
					plainText+=ch
				else:
					if plainText:
						children.append(plainText)
					plainText=u""
					try:
						index=paccHypertext.hyperlinkIndex(offset)
						paccHyperlink=paccHypertext.hyperlink(index)
					except:
						paccHyperlink=None
					if paccHyperlink:
						newPacc=IAccessibleHandler.normalizeIAccessible(paccHyperlink)
						children.append((newPacc,0))
				offset+=1
			if plainText:
				children.append(plainText)
		elif role!=IAccessibleHandler.ROLE_SYSTEM_COMBOBOX and (role!=IAccessibleHandler.ROLE_SYSTEM_LIST or IAccessibleHandler.STATE_SYSTEM_READONLY&states) and accChildID==0 and pacc.accChildCount>0:
			children=IAccessibleHandler.accessibleChildren(pacc,0,pacc.accChildCount)
		else:
			name=pacc.accName(accChildID)
			value=pacc.accValue(accChildID)
			description=pacc.accDescription(accChildID)
			if name:
				text=name
			else:
				text=value
			if text and not (role==IAccessibleHandler.ROLE_SYSTEM_CELL and text.isspace()):
				children.append(text)
			elif not text and role in (IAccessibleHandler.ROLE_SYSTEM_RADIOBUTTON,IAccessibleHandler.ROLE_SYSTEM_CHECKBUTTON,IAccessibleHandler.ROLE_SYSTEM_LIST):
				children.append(u" ")
		del pacc
		parentNode=VBufStorage_addTagNodeToBuffer(parentNode,previousNode,docHandle,ID,attrs,isBlockElement)
		previousNode=None
		for child in children:
			if isinstance(child,basestring):
				previousNode=VBufStorage_addTextNodeToBuffer(parentNode,previousNode,docHandle,0,child)
			else:
				previousNode=self._fillVBufHelper(child[0],child[1],parentNode,previousNode)
		return parentNode


	def isNVDAObjectInVirtualBuffer(self,obj):
		root=self.rootNVDAObject
		w=obj.windowHandle
		while w:
			if w==root.windowHandle:
				return True
			w=winUser.getAncestor(w,winUser.GA_PARENT)
		return False

	def isAlive(self):
		root=self.rootNVDAObject
		if root and winUser.isWindow(root.windowHandle):
			return True

	def event_focusEntered(self,obj,nextHandler):
		pass

	def event_gainFocus(self,obj,nextHandler):
		api.setNavigatorObject(obj)
		role=obj.role
		states=obj.states
		if role==controlTypes.ROLE_DOCUMENT:
			if not IAccessibleHandler.STATE_SYSTEM_BUSY in states and obj!=self.rootNVDAObject and (not self.isNVDAObjectInVirtualBuffer(obj) or self.rootNVDAObject.role!=controlTypes.ROLE_DOCUMENT): 
				self.rootNVDAObject=obj
				self.fillVBuf()
			return
		#We only want to update the caret and speak the field if we're not in the same one as before
		oldInfo=self.makeTextInfo(textHandler.POSITION_CARET)
		try:
			oldDocHandle,oldID=VBufStorage_getFieldIdentifierFromBufferOffset(self.VBufHandle,oldInfo._startOffset)
		except:
			oldDocHandle=oldID=0
		docHandle=obj.windowHandle
		ID=obj.IAccessibleObject.uniqueID if isinstance(obj.IAccessibleObject,IAccessibleHandler.IAccessible2) else -hash(obj.IAccessibleObject)
		if (docHandle!=oldDocHandle or ID!=oldID) and ID!=0:
			try:
				start,end=VBufStorage_getBufferOffsetsFromFieldIdentifier(self.VBufHandle,docHandle,ID)
			except:
				return nextHandler()
			newInfo=self.makeTextInfo(textHandler.Bookmark(self.TextInfo,(start,end)))
			startToStart=newInfo.compareEndPoints(oldInfo,"startToStart")
			startToEnd=newInfo.compareEndPoints(oldInfo,"startToEnd")
			endToStart=newInfo.compareEndPoints(oldInfo,"endToStart")
			endToEnd=newInfo.compareEndPoints(oldInfo,"endToEnd")
			if (startToStart<0 and endToEnd>0) or (startToStart>0 and endToEnd<0) or endToStart<0 or startToEnd>0:  
				speech.speakFormattedTextWithXML(newInfo.XMLContext,newInfo.XMLText,self,newInfo.getXMLFieldSpeech,reason=speech.REASON_FOCUS)
				newInfo.collapse()
				newInfo.updateCaret()


	def _caretMovedToField(self,docHandle,ID):
		try:
			pacc,accChildID=IAccessibleHandler.accessibleObjectFromEvent(docHandle,IAccessibleHandler.OBJID_CLIENT,ID)
			if not (pacc==self.rootNVDAObject.IAccessibleObject and accChildID==self.rootNVDAObject.IAccessibleChildID):
				pacc.accSelect(1,accChildID)
		except:
			pass

	def _activateField(self,docHandle,ID):
		try:
			pacc,accChildID=IAccessibleHandler.accessibleObjectFromEvent(docHandle,IAccessiblehandler.OBJID_CLIENT,ID)
			role=pacc.accRole(accChildID)
			if role in (IAccessibleHandler.ROLE_SYSTEM_COMBOBOX,IAccessibleHandler.ROLE_SYSTEM_TEXT,IAccessibleHandler.ROLE_SYSTEM_LIST):
				api.toggleVirtualBufferPassThrough()
			else:
				pacc.accDoDefaultAction(accChildID)
		except:
			pass

	def _searchableAttribsForNodeType(self,nodeType):
		if nodeType=="heading":
			return {"IAccessible::role":["heading","h1","h2","h3","h4","h5","h6",IAccessibleHandler.IA2_ROLE_HEADING]}
		elif nodeType=="link":
			return {"IAccessible::role":["link",IAccessibleHandler.ROLE_SYSTEM_LINK]}
		elif nodeType=="visitedLink":
			return {"IAccessible::role":["link",IAccessibleHandler.ROLE_SYSTEM_LINK],"IAccessible::state_%d"%IAccessibleHandler.STATE_SYSTEM_TRAVERSED:[1]}
		elif nodeType=="unvisitedLink":
			return {"IAccessible::role":["link",IAccessibleHandler.ROLE_SYSTEM_LINK],"IAccessible::state_%d"%IAccessibleHandler.STATE_SYSTEM_TRAVERSED:[None]}
		elif nodeType=="formField":
			return {"IAccessible::role":[IAccessibleHandler.ROLE_SYSTEM_PUSHBUTTON,IAccessibleHandler.ROLE_SYSTEM_RADIOBUTTON,IAccessibleHandler.ROLE_SYSTEM_CHECKBUTTON,IAccessibleHandler.ROLE_SYSTEM_COMBOBOX,IAccessibleHandler.ROLE_SYSTEM_LIST,IAccessibleHandler.ROLE_SYSTEM_OUTLINE,IAccessibleHandler.ROLE_SYSTEM_TEXT],"IAccessible::state_%s"%IAccessibleHandler.STATE_SYSTEM_READONLY:[0]}
		else:
			return None

