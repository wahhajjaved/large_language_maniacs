# -*- coding: utf-8 -*-
#@+leo-ver=4-thin
#@+node:ekr.20050710142719:@thin leoEditCommands.py
#@@first

'''Basic editor commands for Leo.

Modelled after Emacs and Vim commands.'''

#@<< imports >>
#@+node:ekr.20050710151017:<< imports >>
# __pychecker__ = '--no-import'

import leoGlobals as g

import leoFind
import leoKeys
import leoPlugins
import leoTest

import cPickle
import difflib
import os
import re
import string
import sys

try:
    import ctypes
    import ctypes.util
except ImportError:
    ctypes = None

subprocess = g.importExtension('subprocess',pluginName=None,verbose=False)
#@-node:ekr.20050710151017:<< imports >>
#@nl

#@<< define class baseEditCommandsClass >>
#@+node:ekr.20050920084036.1:<< define class baseEditCommandsClass >>
class baseEditCommandsClass:

    '''The base class for all edit command classes'''

    #@    @+others
    #@+node:ekr.20050920084036.2: ctor, finishCreate, init (baseEditCommandsClass)
    def __init__ (self,c):

        self.c = c
        self.k = self.k = None
        self.registers = {} # To keep pychecker happy.
        self.undoData = None

    def finishCreate(self):

        # Class delegators.
        self.k = self.k = self.c.k
        try:
            self.w = self.c.frame.body.bodyCtrl # New in 4.4a4.
        except AttributeError:
            self.w = None

    def init (self):

        '''Called from k.keyboardQuit to init all classes.'''

        pass
    #@nonl
    #@-node:ekr.20050920084036.2: ctor, finishCreate, init (baseEditCommandsClass)
    #@+node:ekr.20051214132256:begin/endCommand (baseEditCommands)
    #@+node:ekr.20051214133130:beginCommand  & beginCommandWithEvent
    def beginCommand (self,undoType='Typing'):

        '''Do the common processing at the start of each command.'''

        return self.beginCommandHelper(ch='',undoType=undoType,w=self.w)

    def beginCommandWithEvent (self,event,undoType='Typing'):

        '''Do the common processing at the start of each command.'''

        return self.beginCommandHelper(ch=event.char,undoType=undoType,w=event.widget)
    #@+node:ekr.20051215102349:beingCommandHelper
    # New in Leo 4.4b4: calling beginCommand is valid for all widgets,
    # but does nothing unless we are in the body pane.

    def beginCommandHelper (self,ch,undoType,w):

        c = self.c ; p = c.currentPosition()
        name = c.widget_name(w)

        if name.startswith('body'):
            oldSel =  w.getSelectionRange()
            oldText = p.bodyString()
            self.undoData = g.Bunch(
                ch=ch,name=name,oldSel=oldSel,oldText=oldText,w=w,undoType=undoType)
        else:
            self.undoData = None

        return w
    #@-node:ekr.20051215102349:beingCommandHelper
    #@-node:ekr.20051214133130:beginCommand  & beginCommandWithEvent
    #@+node:ekr.20051214133130.1:endCommand
    # New in Leo 4.4b4: calling endCommand is valid for all widgets,
    # but handles undo only if we are in body pane.

    def endCommand(self,label=None,changed=True,setLabel=True):

        '''Do the common processing at the end of each command.'''

        c = self.c ; b = self.undoData ; k = self.k

        # g.trace('changed',changed)

        if b and b.name.startswith('body') and changed:
            c.frame.body.onBodyChanged(undoType=b.undoType,
                oldSel=b.oldSel,oldText=b.oldText,oldYview=None)

        self.undoData = None # Bug fix: 1/6/06 (after a5 released).

        k.clearState()

        # Warning: basic editing commands **must not** set the label.
        if setLabel:
            if label:
                k.setLabelGrey(label)
            else:
                k.resetLabel()
    #@-node:ekr.20051214133130.1:endCommand
    #@-node:ekr.20051214132256:begin/endCommand (baseEditCommands)
    #@+node:ekr.20061007105001:editWidget
    def editWidget (self,event,allowMinibuffer=False):

        c = self.c ; w = event and event.widget

        if w and g.app.gui.isTextWidget(w) and (
            allowMinibuffer or
            w != c.frame.miniBufferWidget
        ):
            self.w = w
        else:
            self.w = self.c.frame.body and self.c.frame.body.bodyCtrl

        if self.w:
            c.widgetWantsFocusNow(self.w)

        return self.w
    #@nonl
    #@-node:ekr.20061007105001:editWidget
    #@+node:ekr.20050920084036.5:getPublicCommands & getStateCommands
    def getPublicCommands (self):

        '''Return a dict describing public commands implemented in the subclass.
        Keys are untranslated command names.  Values are methods of the subclass.'''

        return {}
    #@-node:ekr.20050920084036.5:getPublicCommands & getStateCommands
    #@+node:ekr.20050920084036.6:getWSString
    def getWSString (self,s):

        return ''.join([g.choose(ch=='\t',ch,' ') for ch in s])
    #@-node:ekr.20050920084036.6:getWSString
    #@+node:ekr.20050920084036.7:oops
    def oops (self):

        print("baseEditCommandsClass oops:",
            g.callers(),
            "must be overridden in subclass")
    #@-node:ekr.20050920084036.7:oops
    #@+node:ekr.20050929161635:Helpers
    #@+node:ekr.20050920084036.249:_chckSel
    def _chckSel (self,event,warning='no selection'):

        c = self.c ; k = self.k

        w = self.editWidget(event)

        val = w and w.hasSelection()

        if warning and not val:
            k.setLabelGrey(warning)

        return val
    #@-node:ekr.20050920084036.249:_chckSel
    #@+node:ekr.20050920084036.250:_checkIfRectangle
    def _checkIfRectangle (self,event):

        k = self.k ; key = event.keysym.lower()

        val = self.registers.get(key)

        if val and type(val) == type([]):
            k.clearState()
            k.setLabelGrey("Register contains Rectangle, not text")
            return True

        return False
    #@-node:ekr.20050920084036.250:_checkIfRectangle
    #@+node:ekr.20050920084036.233:getRectanglePoints
    def getRectanglePoints (self,w):

        c = self.c
        c.widgetWantsFocusNow(w)

        s = w.getAllText()
        i,j = w.getSelectionRange()
        r1,r2 = g.convertPythonIndexToRowCol(s,i)
        r3,r4 = g.convertPythonIndexToRowCol(s,j)

        return r1+1,r2,r3+1,r4
    #@-node:ekr.20050920084036.233:getRectanglePoints
    #@+node:ekr.20051002090441:keyboardQuit
    def keyboardQuit (self,event):

        '''Clear the state and the minibuffer label.'''

        return self.k.keyboardQuit(event)
    #@-node:ekr.20051002090441:keyboardQuit
    #@-node:ekr.20050929161635:Helpers
    #@-others
#@-node:ekr.20050920084036.1:<< define class baseEditCommandsClass >>
#@nl

#@+others
#@+node:ekr.20050924100713: Module level...
#@+node:ekr.20050920084720:createEditCommanders (leoEditCommands module)
def createEditCommanders (c):

    '''Create edit classes in the commander.'''

    global classesList

    for name, theClass in classesList:
        theInstance = theClass(c)# Create the class.
        setattr(c,name,theInstance)
        # g.trace(name,theInstance)
#@-node:ekr.20050920084720:createEditCommanders (leoEditCommands module)
#@+node:ekr.20050922104731:finishCreateEditCommanders (leoEditCommands module)
def finishCreateEditCommanders (c):

    '''Finish creating edit classes in the commander.

    Return the commands dictionary for all the classes.'''

    global classesList

    d = {}

    for name, theClass in classesList:
        theInstance = getattr(c,name)
        theInstance.finishCreate()
        theInstance.init()
        d2 = theInstance.getPublicCommands()
        if d2:
            d.update(d2)
            if 0:
                keys = d2.keys()
                keys.sort()
                print '----- %s' % name
                for key in keys: print key

    return d
#@-node:ekr.20050922104731:finishCreateEditCommanders (leoEditCommands module)
#@+node:ekr.20050924100713.1:initAllEditCommanders
def initAllEditCommanders (c):

    '''Re-init classes in the commander.'''

    global classesList

    for name, theClass in classesList:
        theInstance = getattr(c,name)
        theInstance.init()
#@-node:ekr.20050924100713.1:initAllEditCommanders
#@-node:ekr.20050924100713: Module level...
#@+node:ekr.20050920084036.13:abbrevCommandsClass (test)
#@+at
# 
# type some text, set its abbreviation with Control-x a i g, type the text for 
# abbreviation expansion
# type Control-x a e ( or Alt-x expand-abbrev ) to expand abbreviation
# type Alt-x abbrev-on to turn on automatic abbreviation expansion
# Alt-x abbrev-on to turn it off
# 
# an example:
# type:
# frogs
# after typing 's' type Control-x a i g.  This will turn the miniBuffer blue, 
# type in your definition. For example: turtles.
# 
# Now in the buffer type:
# frogs
# after typing 's' type Control-x a e.  This will turn the 'frogs' into:
# turtles
#@-at
#@@c

class abbrevCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.14: ctor & finishCreate
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        # Set local ivars.
        self.abbrevs ={}
        self.daRanges = []
        self.event = None
        self.dynaregex = re.compile(
            r'[%s%s\-_]+'%(string.ascii_letters,string.digits))
            # Not a unicode problem.
            # For dynamic abbreviations
        self.globalDynamicAbbrevs = c.config.getBool('globalDynamicAbbrevs')
        self.store ={'rlist':[], 'stext':''} # For dynamic expansion.
        self.w = None

    def finishCreate(self):

        baseEditCommandsClass.finishCreate(self)
    #@-node:ekr.20050920084036.14: ctor & finishCreate
    #@+node:ekr.20050920084036.15: getPublicCommands & getStateCommands
    def getPublicCommands (self):

        return {
            # 'expand-abbrev':              self.expandAbbrev, # Not a command.

            # Dynamic...
            'dabbrev-completion':           self.dynamicCompletion,
            'dabbrev-expands':              self.dynamicExpansion,

            # Static...
            'abbrev-mode':                  self.toggleAbbrevMode,
            'add-global-abbrev':            self.addAbbreviation,
            # 'expand-region-abbrevs':        self.regionalExpandAbbrev,
            'inverse-add-global-abbrev':    self.addInverseAbbreviation,
            'kill-all-abbrevs':             self.killAllAbbrevs,
            'list-abbrevs':                 self.listAbbrevs,
            'read-abbrev-file':             self.readAbbreviations,
            'write-abbrev-file':            self.writeAbbreviations,
        }
    #@-node:ekr.20050920084036.15: getPublicCommands & getStateCommands
    #@+node:ekr.20050920084036.58:dynamic abbreviation...
    #@+node:ekr.20050920084036.60:dynamicCompletion
    def dynamicCompletion (self,event=None):

        '''Insert the common prefix of all dynamic abbrev's matching the present word.
        This corresponds to C-M-/ in Emacs.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return
        if g.app.gui.guiName() != 'tkinter':
            return g.es('command not ready yet',color='blue')

        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getWord(s,ins)
        txt = w.get(i,j)
        rlist = []
        self.getDynamicList(w,txt,rlist)
        if rlist:
            prefix = reduce(g.longestCommonPrefix,rlist)
            if prefix:
                w.delete(i,j)
                w.insert(i,prefix)
    #@-node:ekr.20050920084036.60:dynamicCompletion
    #@+node:ekr.20050920084036.59:dynamicExpansion
    def dynamicExpansion (self,event=None):

        '''Expand the word in the buffer before point as a dynamic abbrev,
        by searching in the buffer for words starting with that abbreviation (dabbrev-expand).
        This corresponds to M-/ in Emacs.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return
        if g.app.gui.guiName() not in ('null','tkinter'):
            return g.es('command not ready yet',color='blue')

        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getWord(s,ins)
        txt = w.get(i,j)
        rlist = []
        self.getDynamicList(w,txt,rlist)
        if not rlist: return
        prefix = reduce(g.longestCommonPrefix,rlist)
        if prefix and prefix != txt:
            w.delete(i,j)
            w.insert(i,prefix)
        else:
            self.dynamicExpandHelper(prefix,rlist,w)
    #@+node:ekr.20070605110441:dynamicExpandHelper
    def dynamicExpandHelper (self,prefix=None,rlist=None,w=None):

        k = self.k ; tag = 'dabbrev-expand'
        state = k.getState(tag)

        if state == 0:
            self.w = w
            names = rlist ; event = None
            prefix2 = 'dabbrev-expand: '
            k.setLabelBlue(prefix2+prefix,protect=True)
            k.getArg(event,tag,1,self.dynamicExpandHelper,prefix=prefix2,tabList=names)
        else:
            k.clearState()
            k.resetLabel()
            if k.arg:
                w = self.w
                s = w.getAllText()
                ins = w.getInsertPoint()
                i,j = g.getWord(s,ins)
                w.delete(i,j)
                w.insert(i,k.arg)

    #@-node:ekr.20070605110441:dynamicExpandHelper
    #@-node:ekr.20050920084036.59:dynamicExpansion
    #@+node:ekr.20050920084036.61:getDynamicList (helper)
    def getDynamicList (self,w,txt,rlist):

        items = []
        if self.globalDynamicAbbrevs:
            for p in self.c.allNodes_iter():
                s = p.bodyString()
                if s:
                    items.extend(self.dynaregex.findall(s))
        else:
            # Make a big list of what we are considering a 'word'
            s = w.getAllText()
            items.append(self.dynaregex.findall(s))

        # g.trace('txt',repr(txt),'len(items)',len(items))

        if items:
            for word in items:
                if not word.startswith(txt) or word == txt:
                    continue
                    # dont need words that dont match or == the pattern
                if word not in rlist:
                    rlist.append(word)
                else:
                    rlist.remove(word)
                    rlist.append(word)

        # g.trace('rlist',rlist)
    #@-node:ekr.20050920084036.61:getDynamicList (helper)
    #@-node:ekr.20050920084036.58:dynamic abbreviation...
    #@+node:ekr.20070531103114:static abbrevs
    #@+node:ekr.20050920084036.25:addAbbreviation
    def addAbbreviation (self,event):

        '''Add an abbreviation:
        The selected text is the abbreviation;
        the minibuffer prompts you for the name of the abbreviation.
        Also sets abbreviations on.'''

        k = self.k ; state = k.getState('add-abbr')

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            k.setLabelBlue('Add Abbreviation: ',protect=True)
            k.getArg(event,'add-abbr',1,self.addAbbreviation)
        else:
            w = self.w
            k.clearState()
            k.resetLabel()
            s = w.getAllText()
            i = w.getInsertPoint()
            i,j = g.getWord(s,i-1)
            word = s[i:j]
            if k.arg.strip():
                self.abbrevs [k.arg] = word
                k.abbrevOn = True
                k.setLabelGrey(
                    "Abbreviations are on.\nAbbreviation: '%s' = '%s'" % (
                    k.arg,word))
    #@-node:ekr.20050920084036.25:addAbbreviation
    #@+node:ekr.20051004080550:addInverseAbbreviation
    def addInverseAbbreviation (self,event):

        '''Add an inverse abbreviation:
        The selected text is the abbreviation name;
        the minibuffer prompts you for the value of the abbreviation.'''

        k = self.k ; state = k.getState('add-inverse-abbr')

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            k.setLabelBlue('Add Inverse Abbreviation: ',protect=True)
            k.getArg(event,'add-inverse-abbr',1,self.addInverseAbbreviation)
        else:
            w = self.w
            k.clearState()
            k.resetLabel()
            s = w.getAllText()
            i = w.getInsertPoint()
            i,j = g.getWord(s,i-1)
            word = s[i:j]
            if word:
                self.abbrevs [word] = k.arg
    #@-node:ekr.20051004080550:addInverseAbbreviation
    #@+node:ekr.20050920084036.27:expandAbbrev
    def expandAbbrev (self,event):

        '''Not a command.  Called from k.masterCommand to expand
        abbreviations in event.widget.'''

        k = self.k ; c = self.c ; ch = event.char.strip()
        w = self.editWidget(event)
        if not w: return

        word = w.get('insert -1c wordstart','insert -1c wordend')
        g.trace('ch',repr(ch),'word',repr(word))
        if ch:
            # We must do this: expandAbbrev is called from Alt-x and Control-x,
            # we get two differnt types of data and w states.
            word = '%s%s'% (word,ch)

        val = self.abbrevs.get(word)
        if val is not None:
            s = w.getAllText()
            i = w.getInsertPoint()
            i,j = g.getWord(s,i-1)
            if i != j: w.delete(i,j)
            w.insert(i,val)
            c.frame.body.onBodyChanged(undoType='Typing')

        return val is not None
    #@-node:ekr.20050920084036.27:expandAbbrev
    #@+node:ekr.20050920084036.18:killAllAbbrevs
    def killAllAbbrevs (self,event):

        '''Delete all abbreviations.'''

        self.abbrevs = {}
    #@-node:ekr.20050920084036.18:killAllAbbrevs
    #@+node:ekr.20050920084036.19:listAbbrevs
    def listAbbrevs (self,event):

        '''List all abbreviations.'''

        k = self.k

        if self.abbrevs:
            for z in self.abbrevs:
                s = self.abbrevs[z]
                g.es('','%s=%s' % (z,s))
    #@-node:ekr.20050920084036.19:listAbbrevs
    #@+node:ekr.20050920084036.20:readAbbreviations
    def readAbbreviations (self,event):

        '''Read abbreviations from a file.'''

        fileName = g.app.gui.runOpenFileDialog(
            title = 'Open Abbreviation File',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return

        try:
            f = open(fileName)
            for x in f:
                a, b = x.split('=')
                b = b [:-1]
                self.abbrevs [a] = b
            f.close()
        except IOError:
            g.es('can not open',fileName)
    #@-node:ekr.20050920084036.20:readAbbreviations
    #@+node:ekr.20050920084036.21:regionalExpandAbbrev (TK code)
    # def regionalExpandAbbrev (self,event):

        # '''Exapand abbreviations throughout a region.'''

        # k = self.k ; w = self.editWidget(event)
        # if not w or not self._chckSel(event): return

        # i1,i2 = w.getSelectionRange()
        # ins = w.getInsertPoint()
        # 
        #@nonl
        #@<< define a new generator searchXR >>
        #@+node:ekr.20050920084036.22:<< define a new generator searchXR >> LATER
        # @ This is a generator (it contains a yield).
        # To make this work we must define a new generator for each call to regionalExpandAbbrev.
        # @c
        # def searchXR (i1,i2,ins,event):
            # k = self.k
            # w = self.editWidget(event)
            # if not w: return

            # w.tag_add('sXR',i1,i2)
            # while i1:
                # tr = w.tag_ranges('sXR')
                # if not tr: break
                # i1 = w.search(r'\w',i1,stopindex=tr[1],regexp=True)
                # if i1:
                    # word = w.get('%s wordstart' % i1,'%s wordend' % i1)
                    # w.tag_delete('found')
                    # w.tag_add('found','%s wordstart' % i1,'%s wordend' % i1)
                    # w.tag_config('found',background='yellow')
                    # if self.abbrevs.has_key(word):
                        # k.setLabel('Replace %s with %s? y/n' % (word,self.abbrevs[word]))
                        # yield None
                        # if k.regXKey == 'y':
                            # ind = w.index('%s wordstart' % i1)
                            # w.delete('%s wordstart' % i1,'%s wordend' % i1)
                            # w.insert(ind,self.abbrevs[word])
                    # i1 = '%s wordend' % i1
            # w.setInsertPoint(ins,ins,insert=ins)
            # w.tag_delete('sXR')
            # w.tag_delete('found')
            # k.setLabelGrey('')
            # self.k.regx = g.bunch(iter=None,key=None)
        #@-node:ekr.20050920084036.22:<< define a new generator searchXR >> LATER
        #@nl

        # # EKR: the 'result' of calling searchXR is a generator object.
        # k.regx.iter = searchXR(i1,i2,ins,event)
        # k.regx.iter.next() # Call it the first time.
    #@nonl
    #@-node:ekr.20050920084036.21:regionalExpandAbbrev (TK code)
    #@+node:ekr.20050920084036.23:toggleAbbrevMode
    def toggleAbbrevMode (self,event):

        '''Toggle abbreviation mode.'''

        k = self.k
        k.abbrevOn = not k.abbrevOn
        k.keyboardQuit(event)
        k.setLabel('Abbreviations are ' + g.choose(k.abbrevOn,'On','Off'))
    #@-node:ekr.20050920084036.23:toggleAbbrevMode
    #@+node:ekr.20050920084036.24:writeAbbreviations
    def writeAbbreviations (self,event):

        '''Write abbreviations to a file.'''

        fileName = g.app.gui.runSaveFileDialog(
            initialfile = None,
            title='Write Abbreviations',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return

        try:
            f = open(fileName,'w')
            for x in self.abbrevs:
                f.write('%s=%s\n' % (x,self.abbrevs[x]))
            f.close()
        except IOError:
            g.es('can not create',fileName)
    #@-node:ekr.20050920084036.24:writeAbbreviations
    #@-node:ekr.20070531103114:static abbrevs
    #@-others
#@-node:ekr.20050920084036.13:abbrevCommandsClass (test)
#@+node:ekr.20050920084036.31:bufferCommandsClass
#@+at 
#@nonl
# An Emacs instance does not have knowledge of what is considered a buffer in 
# the environment.
# 
# The call to setBufferInteractionMethods calls the buffer configuration 
# methods.
#@-at
#@@c

class bufferCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.32: ctor (bufferCommandsClass)
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.fromName = '' # Saved name from getBufferName.
        self.nameList = [] # [n: <headline>]
        self.names = {}
        self.tnodes = {} # Keys are n: <headline>, values are tnodes.

        try:
            self.w = c.frame.body.bodyCtrl
        except AttributeError:
            self.w = None
    #@-node:ekr.20050920084036.32: ctor (bufferCommandsClass)
    #@+node:ekr.20050920084036.33: getPublicCommands
    def getPublicCommands (self):

        return {

            # These do not seem useful.
                # 'copy-to-buffer':               self.copyToBuffer,
                # 'insert-to-buffer':             self.insertToBuffer,

            'append-to-buffer':             self.appendToBuffer,
            'kill-buffer' :                 self.killBuffer,
            'list-buffers' :                self.listBuffers,
            'list-buffers-alphabetically':  self.listBuffersAlphabetically,
            'prepend-to-buffer':            self.prependToBuffer,
            'rename-buffer':                self.renameBuffer,
            'switch-to-buffer':             self.switchToBuffer,
        }
    #@-node:ekr.20050920084036.33: getPublicCommands
    #@+node:ekr.20050920084036.34:Entry points
    #@+node:ekr.20050920084036.35:appendToBuffer
    def appendToBuffer (self,event):

        '''Add the selected body text to the end of the body text of a named buffer (node).'''

        w = self.editWidget(event) # Sets self.w
        if not w: return

        self.k.setLabelBlue('Append to buffer: ')
        self.getBufferName(self.appendToBufferFinisher)

    def appendToBufferFinisher (self,name):

        c = self.c ; k = self.k ; w = self.w
        s = w.getSelectedText()
        p = self.findBuffer(name)
        if s and p:
            c.beginUpdate()
            try:
                w = self.w
                c.selectPosition(p)
                self.beginCommand('append-to-buffer: %s' % p.headString())
                w.insert('end',s)
                w.setInsertPoint('end')
                w.seeInsertPoint()
                self.endCommand()
            finally:
                c.endUpdate()
                c.recolor_now()
    #@nonl
    #@-node:ekr.20050920084036.35:appendToBuffer
    #@+node:ekr.20050920084036.36:copyToBuffer
    def copyToBuffer (self,event):

        '''Add the selected body text to the end of the body text of a named buffer (node).'''

        w = self.editWidget(event) # Sets self.w
        if not w: return

        self.k.setLabelBlue('Copy to buffer: ')
        self.getBufferName(self.copyToBufferFinisher)

    def copyToBufferFinisher (self,event,name):

        c = self.c ; k = self.k ; w = self.w
        s = w.getSelectedText()
        p = self.findBuffer(name)
        if s and p:
            c.beginUpdate()
            try:
                c.selectPosition(p)
                self.beginCommand('copy-to-buffer: %s' % p.headString())
                w.insert('end',s)
                w.setInsertPoint('end')
                self.endCommand()
            finally:
                c.endUpdate()
                c.recolor_now()
    #@-node:ekr.20050920084036.36:copyToBuffer
    #@+node:ekr.20050920084036.37:insertToBuffer
    def insertToBuffer (self,event):

        '''Add the selected body text at the insert point of the body text of a named buffer (node).'''

        w = self.editWidget(event) # Sets self.w
        if not w: return

        self.k.setLabelBlue('Insert to buffer: ')
        self.getBufferName(self.insertToBufferFinisher)

    def insertToBufferFinisher (self,event,name):

        c = self.c ; k = self.k ; w = self.w
        s = w.getSelectedText()
        p = self.findBuffer(name)
        if s and p:
            c.beginUpdate()
            try:
                c.selectPosition(p)
                self.beginCommand('insert-to-buffer: %s' % p.headString())
                i = w.getInsertPoint()
                w.insert(i,s)
                w.seeInsertPoint()
                self.endCommand()
            finally:
                c.endUpdate()
    #@-node:ekr.20050920084036.37:insertToBuffer
    #@+node:ekr.20050920084036.38:killBuffer
    def killBuffer (self,event):

        '''Delete a buffer (node) and all its descendants.'''

        w = self.editWidget(event) # Sets self.w
        if not w: return

        self.k.setLabelBlue('Kill buffer: ')
        self.getBufferName(self.killBufferFinisher)

    def killBufferFinisher (self,name):

        c = self.c ; p = self.findBuffer(name)
        if p:
            h = p.headString()
            current = c.currentPosition()
            c.selectPosition(p)
            c.deleteOutline (op_name='kill-buffer: %s' % h)
            c.selectPosition(current)
            self.k.setLabelBlue('Killed buffer: %s' % h)
    #@-node:ekr.20050920084036.38:killBuffer
    #@+node:ekr.20050920084036.42:listBuffers & listBuffersAlphabetically
    def listBuffers (self,event):

        '''List all buffers (node headlines), in outline order.
        Nodes with the same headline are disambiguated by giving their parent or child index.
        '''

        self.computeData()
        g.es('buffers...')
        for name in self.nameList:
            g.es('',name)

    def listBuffersAlphabetically (self,event):

        '''List all buffers (node headlines), in alphabetical order.
        Nodes with the same headline are disambiguated by giving their parent or child index.'''

        self.computeData()
        names = self.nameList[:] ; names.sort()

        g.es('buffers...')
        for name in names:
            g.es('',name)
    #@-node:ekr.20050920084036.42:listBuffers & listBuffersAlphabetically
    #@+node:ekr.20050920084036.39:prependToBuffer
    def prependToBuffer (self,event):

        '''Add the selected body text to the start of the body text of a named buffer (node).'''

        w = self.editWidget(event) # Sets self.w
        if not w: return

        self.k.setLabelBlue('Prepend to buffer: ')
        self.getBufferName(self.prependToBufferFinisher)

    def prependToBufferFinisher (self,event,name):

        c = self.c ; k = self.k ; w = self.w
        s = w.getSelectedText()
        p = self.findBuffer(name)
        if s and p:
            c.beginUpdate()
            try:
                c.selectPosition(p)
                self.beginCommand('prepend-to-buffer: %s' % p.headString())
                w.insert(0,s)
                w.setInsertPoint(0)
                w.seeInsertPoint()
                self.endCommand()
            finally:
                c.endUpdate()
                c.recolor_now()

    #@-node:ekr.20050920084036.39:prependToBuffer
    #@+node:ekr.20050920084036.43:renameBuffer
    def renameBuffer (self,event):

        '''Rename a buffer, i.e., change a node's headline.'''

        self.k.setLabelBlue('Rename buffer from: ')
        self.getBufferName(self.renameBufferFinisher1)

    def renameBufferFinisher1 (self,name):

        self.fromName = name
        self.k.setLabelBlue('Rename buffer from: %s to: ' % (name))
        self.getBufferName(self.renameBufferFinisher2)

    def renameBufferFinisher2 (self,name):

        c = self.c ; p = self.findBuffer(self.fromName)
        if p:
            c.endEditing()
            c.beginUpdate()
            c.setHeadString(p,name)
            c.endUpdate()
    #@-node:ekr.20050920084036.43:renameBuffer
    #@+node:ekr.20050920084036.40:switchToBuffer
    def switchToBuffer (self,event):

        '''Select a buffer (node) by its name (headline).'''

        self.k.setLabelBlue('Switch to buffer: ')
        self.getBufferName(self.switchToBufferFinisher)

    def switchToBufferFinisher (self,name):

        c = self.c ; p = self.findBuffer(name)
        if p:
            c.beginUpdate()
            try:
                c.selectPosition(p)
            finally:
                c.endUpdate()
    #@-node:ekr.20050920084036.40:switchToBuffer
    #@-node:ekr.20050920084036.34:Entry points
    #@+node:ekr.20050927102133.1:Utils
    #@+node:ekr.20051215121416:computeData
    def computeData (self):

        counts = {} ; self.nameList = []
        self.names = {} ; self.tnodes = {}

        for p in self.c.allNodes_iter():
            h = p.headString().strip()
            t = p.v.t
            n = counts.get(t,0) + 1
            counts[t] = n
            if n == 1: # Only make one entry per set of clones.
                nameList = self.names.get(h,[])
                if nameList:
                    if p.parent():
                        key = '%s, parent: %s' % (h,p.parent().headString())
                    else:
                        key = '%s, child index: %d' % (h,p.childIndex())
                else:
                    key = h
                self.nameList.append(key)
                self.tnodes[key] = t
                nameList.append(key)
                self.names[h] = nameList
    #@-node:ekr.20051215121416:computeData
    #@+node:ekr.20051215164823:findBuffer
    def findBuffer (self,name):

        t = self.tnodes.get(name)

        for p in self.c.allNodes_iter():
            if p.v.t == t:
                return p

        g.trace("Can't happen",name)
        return None
    #@-node:ekr.20051215164823:findBuffer
    #@+node:ekr.20050927093851:getBufferName
    def getBufferName (self,finisher):

        '''Get a buffer name into k.arg and call k.setState(kind,n,handler).'''

        k = self.k ; c = k.c ; state = k.getState('getBufferName')

        if state == 0:
            self.computeData()
            self.getBufferNameFinisher = finisher
            prefix = k.getLabel() ; event = None
            k.getArg(event,'getBufferName',1,self.getBufferName,
                prefix=prefix,tabList=self.nameList)
        else:
            k.resetLabel()
            k.clearState()
            finisher = self.getBufferNameFinisher
            self.getBufferNameFinisher = None
            finisher(k.arg)
    #@-node:ekr.20050927093851:getBufferName
    #@-node:ekr.20050927102133.1:Utils
    #@-others
#@-node:ekr.20050920084036.31:bufferCommandsClass
#@+node:ekr.20070522085324:chapterCommandsClass
class chapterCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20070522085340: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        # c.chapterController does not exist yet.
    #@-node:ekr.20070522085340: ctor
    #@+node:ekr.20070522085429: getPublicCommands (chapterCommandsClass)
    def getPublicCommands (self):

        c = self.c ; cc = c.chapterController

        # g.trace('cc',cc,g.callers())

        if cc:
            return {
                'clone-node-to-chapter':    cc.cloneNodeToChapter,
                'convert-node-to-chapter':  cc.convertNodeToChapter,
                'copy-node-to-chapter':     cc.copyNodeToChapter,
                'create-chapter':           cc.createChapter,
                'create-chapter-from-node': cc.createChapterFromNode,
                'move-node-to-chapter':     cc.moveNodeToChapter,
                'remove-chapter':           cc.removeChapter,
                'rename-chapter':           cc.renameChapter,
                'select-chapter':           cc.selectChapter,
            }
        else:
            return {}
    #@-node:ekr.20070522085429: getPublicCommands (chapterCommandsClass)
    #@-others
#@-node:ekr.20070522085324:chapterCommandsClass
#@+node:ekr.20050920084036.150:controlCommandsClass
class controlCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.151: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.payload = None
    #@-node:ekr.20050920084036.151: ctor
    #@+node:ekr.20050920084036.152: getPublicCommands
    def getPublicCommands (self):

        k = self.c.k

        return {
            'advertised-undo':              self.advertizedUndo,
            'iconify-frame':                self.iconifyFrame, # Same as suspend.
            'keyboard-quit':                k and k.keyboardQuit,
            'save-buffers-kill-leo':        self.saveBuffersKillLeo,
            'set-silent-mode':              self.setSilentMode,
            'print-plugins':                self.printPlugins,
            'print-plugin-handlers':        self.printPluginHandlers,
            'shell-command':                self.shellCommand,
            'shell-command-on-region':      self.shellCommandOnRegion,
            'suspend':                      self.suspend,
        }
    #@-node:ekr.20050920084036.152: getPublicCommands
    #@+node:ekr.20050922110030:advertizedUndo
    def advertizedUndo (self,event):

        '''Undo the previous command.'''

        self.c.undoer.undo()
    #@-node:ekr.20050922110030:advertizedUndo
    #@+node:ekr.20050920084036.160:executeSubprocess
    def executeSubprocess (self,event,command,theInput=None):

        '''Execute a command in a separate process.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        k.setLabelBlue('started  shell-command: %s' % command)
        try:
            ofile = os.tmpfile()
            efile = os.tmpfile()
            process = subprocess.Popen(command,bufsize=-1,
                stdout = ofile.fileno(), stderr = ofile.fileno(),
                stdin = subprocess.PIPE, shell = True)
            if theInput: process.communicate(theInput)
            process.wait()
            efile.seek(0)
            errinfo = efile.read()
            if errinfo: w.insert('insert',errinfo)
            ofile.seek(0)
            okout = ofile.read()
            if okout: w.insert('insert',okout)
        except Exception, x:
            w.insert('insert',x)

        k.setLabelGrey('finished shell-command: %s' % command)
    #@-node:ekr.20050920084036.160:executeSubprocess
    #@+node:ekr.20070429090859:print-plugins & print-handlers
    def printPluginHandlers (self,event=None):

        leoPlugins.printHandlers()

    def printPlugins (self,event=None):

        leoPlugins.printPlugins()

    #@-node:ekr.20070429090859:print-plugins & print-handlers
    #@+node:ekr.20060603161041:setSilentMode
    def setSilentMode (self,event=None):

        '''Set the mode to be run silently, without the minibuffer.
        The only use for this command is to put the following in an @mode node::

            --> set-silent-mode'''

        self.c.k.silentMode = True
    #@-node:ekr.20060603161041:setSilentMode
    #@+node:ekr.20050920084036.158:shellCommand
    def shellCommand (self,event):

        '''Execute a shell command.'''

        if subprocess:
            k = self.k ; state = k.getState('shell-command')

            if state == 0:
                k.setLabelBlue('shell-command: ',protect=True)
                k.getArg(event,'shell-command',1,self.shellCommand)
            else:
                command = k.arg
                k.commandName = 'shell-command: %s' % command
                k.clearState()
                self.executeSubprocess(event,command)
        else:
            k.setLabelGrey('can not execute shell-command: can not import subprocess')
    #@-node:ekr.20050920084036.158:shellCommand
    #@+node:ekr.20050930112126:shellCommandOnRegion
    def shellCommandOnRegion (self,event):

        '''Execute a command taken from the selected text in a separate process.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        if subprocess:
            if w.hasSelection():
                command = w.getSelectedText()
                k.commandName = 'shell-command: %s' % command
                self.executeSubprocess(event,command)
            else:
                k.clearState()
                k.resetLabel()
        else:
            k.setLabelGrey('can not execute shell-command: can not import subprocess')
    #@-node:ekr.20050930112126:shellCommandOnRegion
    #@+node:ekr.20050920084036.155:shutdown, saveBuffersKillEmacs & setShutdownHook
    def shutdown (self,event):

        '''Quit Leo, prompting to save any unsaved files first.'''

        g.app.onQuit()

    saveBuffersKillLeo = shutdown
    #@-node:ekr.20050920084036.155:shutdown, saveBuffersKillEmacs & setShutdownHook
    #@+node:ekr.20050920084036.153:suspend & iconifyFrame
    def suspend (self,event):

        '''Minimize the present Leo window.'''

        w = self.editWidget(event)
        if not w: return
        self.c.frame.top.iconify()

    # Must be a separate function so that k.inverseCommandsDict will be a true inverse.

    def iconifyFrame (self,event):

        '''Minimize the present Leo window.'''

        self.suspend(event)
    #@-node:ekr.20050920084036.153:suspend & iconifyFrame
    #@-others
#@-node:ekr.20050920084036.150:controlCommandsClass
#@+node:ekr.20060127162818.1:debugCommandsClass
class debugCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20060127162921: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.
    #@-node:ekr.20060127162921: ctor
    #@+node:ekr.20060127163325: getPublicCommands
    def getPublicCommands (self):

        return {
            'collect-garbage':              self.collectGarbage,
            'debug':                        self.debug,
            'disable-gc-trace':             self.disableGcTrace,
            'dump-all-objects':             self.dumpAllObjects,
            'dump-new-objects':             self.dumpNewObjects,
            'enable-gc-trace':              self.enableGcTrace,
            'free-tree-widgets':            self.freeTreeWidgets,
            'print-focus':                  self.printFocus,
            'print-stats':                  self.printStats,
            'print-gc-summary':             self.printGcSummary,
            'run-all-unit-tests':           self.runAllUnitTests, # The new way...
            'run-unit-tests':               self.runUnitTests,
            'run-all-unit-tests-locally':   self.runAllUnitTestsLocally, # The old way...
            'run-unit-tests-locally':       self.runUnitTestsLocally,
            'verbose-dump-objects':         self.verboseDumpObjects,
        }
    #@-node:ekr.20060127163325: getPublicCommands
    #@+node:ekr.20060205050659:collectGarbage
    def collectGarbage (self,event=None):

        """Run Python's Gargabe Collector."""

        g.collectGarbage()
    #@-node:ekr.20060205050659:collectGarbage
    #@+node:ekr.20060519003651:debug & helper
    def debug (self,event=None):

        '''Start an external debugger in another process to debug a script.
        The script is the presently selected text or then entire tree's script.'''

        c = self.c ; p = c.currentPosition()
        python = sys.executable
        script = g.getScript(c,p)
        winpdb = self.findDebugger()
        if not winpdb: return

        #check for doctest examples
        try:
            import doctest
            parser = doctest.DocTestParser()
            examples = parser.get_examples(script)

            # if this is doctest, extract the examples as a script
            if len(examples) > 0:
                script = doctest.script_from_examples(script)
        except ImportError:
            pass

        # special case; debug code may include g.es("info string").
        # insert code fragment to make this expression legal outside Leo.
        hide_ges = "class G:\n def es(s,c=None):\n  pass\ng = G()\n"
        script = hide_ges + script

        # Create a temp file from the presently selected node.
        filename = c.writeScriptFile(script)
        if not filename: return

        # Invoke the debugger, retaining the present environment.
        os.chdir(g.app.loadDir)
        if False and subprocess:
            cmdline = '%s %s -t %s' % (python,winpdb,filename)
            subprocess.Popen(cmdline)
        else:
            args = [sys.executable, winpdb, '-t', filename]
            os.spawnv(os.P_NOWAIT, python, args)
    #@+node:ekr.20060521140213:findDebugger
    def findDebugger (self):

        '''Find the debugger using settings.'''

        c = self.c
        pythonDir = g.os_path_dirname(sys.executable)

        debuggers = (
            c.config.getString('debugger_path'),
            g.os_path_join(pythonDir,'Lib','site-packages','winpdb.py'), # winpdb 1.1.2 or newer
            g.os_path_join(pythonDir,'scripts','_winpdb.py'), # oder version.
        )

        for debugger in debuggers:
            if debugger:
                debugger = g.os_path_abspath(debugger)
                if g.os_path_exists(debugger):
                    return debugger
                else:
                    g.es('debugger does not exist:',debugger,color='blue')
        else:
            g.es('no debugger found.')
            return None
    #@-node:ekr.20060521140213:findDebugger
    #@-node:ekr.20060519003651:debug & helper
    #@+node:ekr.20060202160523:dumpAll/New/VerboseObjects
    def dumpAllObjects (self,event=None):

        '''Print a summary of all existing Python objects.'''

        old = g.app.trace_gc
        g.app.trace_gc = True
        g.printGcAll()
        g.app.trace_gc = old

    def dumpNewObjects (self,event=None):

        '''Print a summary of all Python objects created
        since the last time Python's Garbage collector was run.'''

        old = g.app.trace_gc
        g.app.trace_gc = True
        g.printGcObjects()
        g.app.trace_gc = old

    def verboseDumpObjects (self,event=None):

        '''Print a more verbose listing of all existing Python objects.'''

        old = g.app.trace_gc
        g.app.trace_gc = True
        g.printGcVerbose()
        g.app.trace_gc = old
    #@-node:ekr.20060202160523:dumpAll/New/VerboseObjects
    #@+node:ekr.20060127163325.1:enable/disableGcTrace
    def disableGcTrace (self,event=None):

        '''Enable tracing of Python's Garbage Collector.'''

        g.app.trace_gc = False


    def enableGcTrace (self,event=None):

        '''Disable tracing of Python's Garbage Collector.'''

        g.app.trace_gc = True
        g.enable_gc_debug()

        if g.app.trace_gc_verbose:
            g.es('enabled verbose gc stats',color='blue')
        else:
            g.es('enabled brief gc stats',color='blue')
    #@-node:ekr.20060127163325.1:enable/disableGcTrace
    #@+node:ekr.20060202154734:freeTreeWidgets
    def freeTreeWidgets (self,event=None):

        '''Free all widgets used in Leo's outline pane.'''

        c = self.c

        c.frame.tree.destroyWidgets()
        c.redraw_now()
    #@-node:ekr.20060202154734:freeTreeWidgets
    #@+node:ekr.20060210100432:printFocus
    # Doesn't work if the focus isn't in a pane with bindings!

    def printFocus (self,event=None):

        '''Print information about the requested focus (for debugging).'''

        c = self.c

        g.es_print('      hasFocusWidget:',c.widget_name(c.hasFocusWidget))
        g.es_print('requestedFocusWidget:',c.widget_name(c.requestedFocusWidget))
        g.es_print('           get_focus:',c.widget_name(c.get_focus()))
    #@-node:ekr.20060210100432:printFocus
    #@+node:ekr.20060205043324.3:printGcSummary
    def printGcSummary (self,event=None):

        '''Print a brief summary of all Python objects.'''

        g.printGcSummary()
    #@-node:ekr.20060205043324.3:printGcSummary
    #@+node:ekr.20060202133313:printStats
    def printStats (self,event=None):

        '''Print statistics about the objects that Leo is using.'''

        c = self.c
        c.frame.tree.showStats()
        self.dumpAllObjects()
    #@-node:ekr.20060202133313:printStats
    #@+node:ekr.20060328121145:runUnitTest commands
    def runAllUnitTestsLocally (self,event=None):
        '''Run all unit tests contained in the presently selected outline.'''
        c = self.c
        leoTest.doTests(c,all=True)

    def runUnitTestsLocally (self,event=None):
        '''Run all unit tests contained in the presently selected outline.'''
        c = self.c
        leoTest.doTests(c,all=False)

    def runAllUnitTests (self,event=None):
        '''Run all unit tests contained in the entire outline.'''
        c = self.c
        leoTest.runTestsExternally(c,all=True)

    def runUnitTests(self,event=None):
        '''Run all unit tests contained in the presently selected outline.'''
        c = self.c
        leoTest.runTestsExternally(c,all=False)
    #@-node:ekr.20060328121145:runUnitTest commands
    #@-others
#@-node:ekr.20060127162818.1:debugCommandsClass
#@+node:ekr.20050920084036.53:editCommandsClass
class editCommandsClass (baseEditCommandsClass):

    '''Contains editing commands with little or no state.'''

    #@    @+others
    #@+node:ekr.20050929155208: birth
    #@+node:ekr.20050920084036.54: ctor (editCommandsClass)
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.ccolumn = '0'   # For comment column functions.
        self.extendMode = False # True: all cursor move commands extend the selection.
        self.fillPrefix = '' # For fill prefix functions.
        self.fillColumn = 70 # For line centering.
        self.moveSpotNode = None # A tnode.
        self.moveSpot = None # For retaining preferred column when moving up or down.
        self.moveCol = None # For retaining preferred column when moving up or down.
        self.sampleWidget = None # Created later.
        self.swapSpots = []
        self._useRegex = False # For replace-string
        self.w = None # For use by state handlers.

        # Settings...
        self.autocompleteBrackets   = c.config.getBool('autocomplete-brackets')
        self.bracketsFlashBg        = c.config.getColor('flash-brackets-background-color')
        self.bracketsFlashCount     = c.config.getInt('flash-brackets-count')
        self.bracketsFlashDelay     = c.config.getInt('flash-brackets-delay')
        self.bracketsFlashFg        = c.config.getColor('flash-brackets-foreground-color')
        self.flashMatchingBrackets  = c.config.getBool('flash-matching-brackets')
        self.smartAutoIndent        = c.config.getBool('smart_auto_indent')

        self.initBracketMatcher(c)
    #@-node:ekr.20050920084036.54: ctor (editCommandsClass)
    #@+node:ekr.20050920084036.55: getPublicCommands (editCommandsClass)
    def getPublicCommands (self):        

        c = self.c

        return {
            'activate-cmds-menu':                   self.activateCmdsMenu,
            'activate-edit-menu':                   self.activateEditMenu,
            'activate-file-menu':                   self.activateFileMenu,
            'activate-help-menu':                   self.activateHelpMenu,
            'activate-outline-menu':                self.activateOutlineMenu,
            'activate-plugins-menu':                self.activatePluginsMenu,
            'activate-window-menu':                 self.activateWindowMenu,
            'add-editor':                           c.frame.body and c.frame.body.addEditor,
            'add-space-to-lines':                   self.addSpaceToLines,
            'add-tab-to-lines':                     self.addTabToLines, 
            'back-to-indentation':                  self.backToIndentation,
            'back-char':                            self.backCharacter,
            'back-char-extend-selection':           self.backCharacterExtendSelection,
            'back-paragraph':                       self.backwardParagraph,
            'back-paragraph-extend-selection':      self.backwardParagraphExtendSelection,
            'back-sentence':                        self.backSentence,
            'back-sentence-extend-selection':       self.backSentenceExtendSelection,
            'back-word':                            self.backwardWord,
            'back-word-extend-selection':           self.backwardWordExtendSelection,
            'backward-delete-char':                 self.backwardDeleteCharacter,
            'backward-kill-paragraph':              self.backwardKillParagraph,
            'backward-find-character':              self.backwardFindCharacter,
            'backward-find-character-extend-selection': self.backwardFindCharacterExtendSelection,
            'beginning-of-buffer':                  self.beginningOfBuffer,
            'beginning-of-buffer-extend-selection': self.beginningOfBufferExtendSelection,
            'beginning-of-line':                    self.beginningOfLine,
            'beginning-of-line-extend-selection':   self.beginningOfLineExtendSelection,
            'capitalize-word':                      self.capitalizeWord,
            'center-line':                          self.centerLine,
            'center-region':                        self.centerRegion,
            'clean-all-lines':                      self.cleanAllLines,
            'clean-lines':                          self.cleanLines,
            'clear-extend-mode':                    self.clearExtendMode,
            'clear-selected-text':                  self.clearSelectedText,
            'click-click-box':                      self.clickClickBox,
            'click-headline':                       self.clickHeadline,
            'click-icon-box':                       self.clickIconBox,
            'contract-body-pane':                   c.frame.contractBodyPane,
            'contract-log-pane':                    c.frame.contractLogPane,
            'contract-outline-pane':                c.frame.contractOutlinePane,
            'contract-pane':                        c.frame.contractPane,
            'count-region':                         self.countRegion,
            'cycle-focus':                          self.cycleFocus,
            'cycle-all-focus':                      self.cycleAllFocus,
            'cycle-editor-focus':                   c.frame.body.cycleEditorFocus,
            # 'delete-all-icons':                   self.deleteAllIcons,
            'delete-char':                          self.deleteNextChar,
            'delete-editor':                        c.frame.body.deleteEditor,
            'delete-first-icon':                    self.deleteFirstIcon,
            'delete-indentation':                   self.deleteIndentation,
            'delete-last-icon':                     self.deleteLastIcon,
            'delete-node-icons':                    self.deleteNodeIcons,
            'delete-spaces':                        self.deleteSpaces,
            'do-nothing':                           self.doNothing,
            'downcase-region':                      self.downCaseRegion,
            'downcase-word':                        self.downCaseWord,
            'double-click-headline':                self.doubleClickHeadline,
            'double-click-icon-box':                self.doubleClickIconBox,
            'end-of-buffer':                        self.endOfBuffer,
            'end-of-buffer-extend-selection':       self.endOfBufferExtendSelection,
            'end-of-line':                          self.endOfLine,
            'end-of-line-extend-selection':         self.endOfLineExtendSelection,
            'escape':                               self.watchEscape,
            'eval-expression':                      self.evalExpression,
            'exchange-point-mark':                  self.exchangePointMark,
            'expand-body-pane':                     c.frame.expandBodyPane,
            'expand-log-pane':                      c.frame.expandLogPane,
            'expand-outline-pane':                  c.frame.expandOutlinePane,
            'expand-pane':                          c.frame.expandPane,
            'extend-to-line':                       self.extendToLine,
            'extend-to-paragraph':                  self.extendToParagraph,
            'extend-to-sentence':                   self.extendToSentence,
            'extend-to-word':                       self.extendToWord,
            'fill-paragraph':                       self.fillParagraph,
            'fill-region':                          self.fillRegion,
            'fill-region-as-paragraph':             self.fillRegionAsParagraph,
            'find-character':                       self.findCharacter,
            'find-character-extend-selection':      self.findCharacterExtendSelection,
            'find-word':                            self.findWord,
            'find-word-in-line':                    self.findWordInLine,
            'flush-lines':                          self.flushLines,
            'focus-to-body':                        self.focusToBody,
            'focus-to-log':                         self.focusToLog,
            'focus-to-minibuffer':                  self.focusToMinibuffer,
            'focus-to-tree':                        self.focusToTree,
            'forward-char':                         self.forwardCharacter,
            'forward-char-extend-selection':        self.forwardCharacterExtendSelection,
            'forward-paragraph':                    self.forwardParagraph,
            'forward-paragraph-extend-selection':   self.forwardParagraphExtendSelection,
            'forward-sentence':                     self.forwardSentence,
            'forward-sentence-extend-selection':    self.forwardSentenceExtendSelection,
            'forward-end-word':                     self.forwardEndWord, # New in Leo 4.4.2.
            'forward-end-word-extend-selection':    self.forwardEndWordExtendSelection, # New in Leo 4.4.2.
            'forward-word':                         self.forwardWord,
            'forward-word-extend-selection':        self.forwardWordExtendSelection,
            'fully-expand-body-pane':               c.frame.fullyExpandBodyPane,
            'fully-expand-log-pane':                c.frame.fullyExpandLogPane,
            'fully-expand-pane':                    c.frame.fullyExpandPane,
            'fully-expand-outline-pane':            c.frame.fullyExpandOutlinePane,
            'goto-char':                            self.gotoCharacter,
            'goto-global-line':                     self.gotoGlobalLine,
            'goto-line':                            self.gotoLine,
            'hide-body-pane':                       c.frame.hideBodyPane,
            'hide-log-pane':                        c.frame.hideLogPane,
            'hide-pane':                            c.frame.hidePane,
            'hide-outline-pane':                    c.frame.hideOutlinePane,
            'how-many':                             self.howMany,
            # Use indentBody in leoCommands.py
            'indent-relative':                      self.indentRelative,
            'indent-rigidly':                       self.tabIndentRegion,
            'indent-to-comment-column':             self.indentToCommentColumn,
            'insert-icon':                          self.insertIcon,
            'insert-newline':                       self.insertNewline,
            'insert-parentheses':                   self.insertParentheses,
            'keep-lines':                           self.keepLines,
            'kill-paragraph':                       self.killParagraph,
            'line-number':                          self.lineNumber,
            'move-lines-down':                      self.moveLinesDown,
            'move-lines-up':                        self.moveLinesUp,
            'move-past-close':                      self.movePastClose,
            'move-past-close-extend-selection':     self.movePastCloseExtendSelection,
            'newline-and-indent':                   self.insertNewLineAndTab,
            'next-line':                            self.nextLine,
            'next-line-extend-selection':           self.nextLineExtendSelection,
            'previous-line':                        self.prevLine,
            'previous-line-extend-selection':       self.prevLineExtendSelection,
            'remove-blank-lines':                   self.removeBlankLines,
            'remove-space-from-lines':              self.removeSpaceFromLines,
            'remove-tab-from-lines':                self.removeTabFromLines,
            'reverse-region':                       self.reverseRegion,
            'reverse-sort-lines':                   self.reverseSortLines,
            'reverse-sort-lines-ignoring-case':     self.reverseSortLinesIgnoringCase,                 
            'scroll-down':                          self.scrollDown,
            'scroll-down-extend-selection':         self.scrollDownExtendSelection,
            'scroll-outline-down-line':             self.scrollOutlineDownLine,
            'scroll-outline-down-page':             self.scrollOutlineDownPage,
            'scroll-outline-left':                  self.scrollOutlineLeft,
            'scroll-outline-right':                 self.scrollOutlineRight,
            'scroll-outline-up-line':               self.scrollOutlineUpLine,
            'scroll-outline-up-page':               self.scrollOutlineUpPage,
            'scroll-up':                            self.scrollUp,
            'scroll-up-extend-selection':           self.scrollUpExtendSelection,
            'select-all':                           self.selectAllText,
            # Exists, but can not be executed via the minibuffer.
            # 'self-insert-command':                self.selfInsertCommand,
            'set-comment-column':                   self.setCommentColumn,
            'set-extend-mode':                      self.setExtendMode,
            'set-fill-column':                      self.setFillColumn,
            'set-fill-prefix':                      self.setFillPrefix,
            #'set-mark-command':                    self.setRegion,
            'show-colors':                          self.showColors,
            'show-fonts':                           self.showFonts,
            'simulate-begin-drag':                  self.simulateBeginDrag,
            'simulate-end-drag':                    self.simulateEndDrag,
            'sort-columns':                         self.sortColumns,
            'sort-fields':                          self.sortFields,
            'sort-lines':                           self.sortLines,
            'sort-lines-ignoring-case':             self.sortLinesIgnoringCase,
            'split-line':                           self.splitLine,
            'tabify':                               self.tabify,
            'toggle-extend-mode':                   self.toggleExtendMode,
            'transpose-chars':                      self.transposeCharacters,
            'transpose-lines':                      self.transposeLines,
            'transpose-words':                      self.transposeWords,
            'untabify':                             self.untabify,
            'upcase-region':                        self.upCaseRegion,
            'upcase-word':                          self.upCaseWord,
            'view-lossage':                         self.viewLossage,
            'what-line':                            self.whatLine,
        }
    #@-node:ekr.20050920084036.55: getPublicCommands (editCommandsClass)
    #@+node:ekr.20061012113455:doNothing
    def doNothing (self,event):

        '''A placeholder command, useful for testing bindings.'''

        # g.trace()
        pass
    #@nonl
    #@-node:ekr.20061012113455:doNothing
    #@-node:ekr.20050929155208: birth
    #@+node:ekr.20050920084036.57:capitalization & case
    #@+node:ekr.20051015114221:capitalizeWord & up/downCaseWord
    def capitalizeWord (self,event):
        '''Capitalize the word at the cursor.'''
        self.capitalizeHelper(event,'cap','capitalize-word')

    def downCaseWord (self,event):
        '''Convert all characters of the word at the cursor to lower case.'''
        self.capitalizeHelper(event,'low','downcase-word')

    def upCaseWord (self,event):
        '''Convert all characters of the word at the cursor to UPPER CASE.'''
        self.capitalizeHelper(event,'up','upcase-word')
    #@-node:ekr.20051015114221:capitalizeWord & up/downCaseWord
    #@+node:ekr.20050920084036.145:changePreviousWord (not used)
    def changePreviousWord (self,event):

        k = self.k ; stroke = k.stroke
        w = self.editWidget(event)
        if not w: return

        i = w.getInsertPoint()
        self.beginCommand(undoType='change-previous-word')
        self.moveWordHelper(event,extend=False,forward=False)

        if stroke == '<Alt-c>':
            self.capitalizeWord(event)
        elif stroke == '<Alt-u>':
            self.upCaseWord(event)
        elif stroke == '<Alt-l>':
            self.downCaseWord(event)

        w.setInsertPoint(i)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.145:changePreviousWord (not used)
    #@+node:ekr.20051015114221.1:capitalizeHelper
    def capitalizeHelper (self,event,which,undoType):

        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getWord(s,ins)
        word = s[i:j]
        # g.trace('word',repr(word))
        if not word.strip(): return

        self.beginCommand(undoType=undoType)

        if   which == 'cap':  word2 = word.capitalize()
        elif which == 'low':  word2 = word.lower()
        elif which == 'up':   word2 = word.upper()
        else: g.trace('can not happen: which = %s' %s (which))

        changed = word != word2
        # g.trace('changed',changed,'word2',repr(word2))

        if changed:
            w.delete(i,j)
            w.insert(i,word2)
            w.setSelectionRange(ins,ins,insert=ins)

        self.endCommand(changed=changed,setLabel=True)
    #@-node:ekr.20051015114221.1:capitalizeHelper
    #@-node:ekr.20050920084036.57:capitalization & case
    #@+node:ekr.20051022142249:clicks and focus (editCommandsClass)
    #@+node:ekr.20060211100905:activate-x-menu & activateMenu (editCommandsClass)
    def activateCmdsMenu    (self,event=None):
        '''Activate Leo's Cmnds menu.'''
        self.activateMenu('Cmds')

    def activateEditMenu    (self,event=None):
        '''Activate Leo's Edit menu.'''
        self.activateMenu('Edit')

    def activateFileMenu    (self,event=None):
        '''Activate Leo's File menu.'''
        self.activateMenu('File')

    def activateHelpMenu    (self,event=None):
        '''Activate Leo's Help menu.'''
        self.activateMenu('Help')

    def activateOutlineMenu (self,event=None):
        '''Activate Leo's Outline menu.'''
        self.activateMenu('Outline')

    def activatePluginsMenu (self,event=None):
        '''Activate Leo's Plugins menu.'''
        self.activateMenu('Plugins')

    def activateWindowMenu  (self,event=None):
        '''Activate Leo's Window menu.'''
        self.activateMenu('Window')

    def activateMenu (self,menuName):
        c = self.c
        c.frame.menu.activateMenu(menuName)
    #@-node:ekr.20060211100905:activate-x-menu & activateMenu (editCommandsClass)
    #@+node:ekr.20051022144825.1:cycleFocus
    def cycleFocus (self,event):

        '''Cycle the keyboard focus between Leo's outline, body and log panes.'''

        c = self.c ;  w = event.widget


        body = c.frame.body.bodyCtrl
        log  = c.frame.log.logCtrl
        tree = c.frame.tree.canvas
        panes = [body,log,tree]

        if w in panes:
            i = panes.index(w) + 1
            if i >= len(panes): i = 0
            pane = panes[i]
        else:
            pane = body

        # Warning: traces mess up the focus
        # print g.app.gui.widget_name(w),g.app.gui.widget_name(pane)

        # This works from the minibuffer *only* if there is no typing completion.
        c.widgetWantsFocusNow(pane)
        c.k.newMinibufferWidget = pane
    #@nonl
    #@-node:ekr.20051022144825.1:cycleFocus
    #@+node:ekr.20060613090701:cycleAllFocus
    editWidgetCount = 0
    logWidgetCount = 0

    def cycleAllFocus (self,event):

        '''Cycle the keyboard focus between Leo's outline,
        all body editors and all tabs in the log pane.'''

        c = self.c ; k = c.k
        w = event and event.widget # Does **not** require a text widget.

        pane = None ; w_name = g.app.gui.widget_name
        trace = False
        if trace: print (
            '---- w',w_name(w),id(w),
            '#tabs',c.frame.log.numberOfVisibleTabs(),
            'bodyCtrl',w_name(c.frame.body.bodyCtrl),id(c.frame.body.bodyCtrl))

        # w may not be the present body widget, so test its name, not its id.
        if w_name(w).startswith('body'):
            n = c.frame.body.numberOfEditors
            # g.trace(self.editWidgetCount,n)
            if n > 1:
                self.editWidgetCount += 1
                if self.editWidgetCount == 1:
                    pane = c.frame.body.bodyCtrl
                elif self.editWidgetCount > n:
                    self.editWidgetCount = 0 ; self.logWidgetCount = 1
                    c.frame.log.selectTab('Log')
                    pane = c.frame.log.logCtrl
                else:
                    c.frame.body.cycleEditorFocus(event) ; pane = None
            else:
                self.editWidgetCount = 0 ; self.logWidgetCount = 1
                c.frame.log.selectTab('Log')
                pane = c.frame.log.logCtrl
        elif w_name(w).startswith('log'):
            n = c.frame.log.numberOfVisibleTabs()
            if n > 1:
                self.logWidgetCount += 1
                if self.logWidgetCount == 1:
                    c.frame.log.selectTab('Log')
                    pane = c.frame.log.logCtrl
                elif self.logWidgetCount > n:
                    self.logWidgetCount = 0
                    pane = c.frame.tree.canvas
                else:
                    c.frame.log.cycleTabFocus()
                    pane = c.frame.log.logCtrl
            else:
                self.logWidgetCount = 0
                pane = c.frame.tree.canvas
        else:
            pane = c.frame.body.bodyCtrl
            self.editWidgetCount = 1 ; self.logWidgetCount = 0

        if trace: print 'old: %10s new: %10s' % (w_name(w),w_name(pane))

        if pane:
            k.newMinibufferWidget = pane
            c.widgetWantsFocusNow(pane)
    #@nonl
    #@-node:ekr.20060613090701:cycleAllFocus
    #@+node:ekr.20051022144825:focusTo...
    def focusToBody (self,event):
        '''Put the keyboard focus in Leo's body pane.'''
        self.c.bodyWantsFocusNow()

    def focusToLog (self,event):
        '''Put the keyboard focus in Leo's log pane.'''
        self.c.logWantsFocusNow()

    def focusToMinibuffer (self,event):
        '''Put the keyboard focus in Leo's minibuffer.'''
        self.c.minibufferWantsFocusNow()

    def focusToTree (self,event):
        '''Put the keyboard focus in Leo's outline pane.'''
        self.c.treeWantsFocusNow()
    #@-node:ekr.20051022144825:focusTo...
    #@+node:ekr.20060211063744.1:clicks in the headline
    # These call the actual event handlers so as to trigger hooks.

    def clickHeadline (self,event=None):
        '''Simulate a click in the headline of the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.onHeadlineClick(event,p=p)

    def doubleClickHeadline (self,event=None):
        '''Simulate a double click in headline of the presently selected node.'''
        return self.clickHeadline(event)

    def rightClickHeadline (self,event=None):
        '''Simulate a right click in the headline of the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.onHeadlineRightClick(event,p=p)
    #@-node:ekr.20060211063744.1:clicks in the headline
    #@+node:ekr.20060211055455:clicks in the icon box
    # These call the actual event handlers so as to trigger hooks.

    def clickIconBox (self,event=None):
        '''Simulate a click in the icon box of the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.onIconBoxClick(event,p=p)

    def doubleClickIconBox (self,event=None):
        '''Simulate a double-click in the icon box of the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.onIconBoxDoubleClick(event,p=p)

    def rightClickIconBox (self,event=None):

        '''Simulate a right click in the icon box of the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.onIconBoxRightClick(event,p=p)
    #@-node:ekr.20060211055455:clicks in the icon box
    #@+node:ekr.20060211062025:clickClickBox
    # Call the actual event handlers so as to trigger hooks.

    def clickClickBox (self,event=None):

        '''Simulate a click in the click box (+- box) of the presently selected node.'''

        c = self.c ; p = c.currentPosition()
        c.frame.tree.onClickBoxClick(event,p=p)
    #@-node:ekr.20060211062025:clickClickBox
    #@+node:ekr.20060211063744.2:simulate...Drag
    # These call the drag setup methods which in turn trigger hooks.

    def simulateBeginDrag (self,event=None):

        '''Simulate the start of a drag in the presently selected node.'''
        c = self.c ; p = c.currentPosition()
        c.frame.tree.startDrag(event,p=p)

    def simulateEndDrag (self,event=None):

        '''Simulate the end of a drag in the presently selected node.'''
        c = self.c

        # Note: this assumes that tree.startDrag has already been called.
        c.frame.tree.endDrag(event)
    #@-node:ekr.20060211063744.2:simulate...Drag
    #@-node:ekr.20051022142249:clicks and focus (editCommandsClass)
    #@+node:ekr.20051019183105:color & font
    #@+node:ekr.20051019183105.1:show-colors
    def showColors (self,event):

        '''Open a tab in the log pane showing various color pickers.'''

        c = self.c ; log = c.frame.log ; tabName = 'Colors'

        if log.frameDict.get(tabName):
            log.selectTab(tabName)
        else:
            log.selectTab(tabName)
            log.createColorPicker(tabName)
    #@-node:ekr.20051019183105.1:show-colors
    #@+node:ekr.20051019201809:editCommands.show-fonts & helpers
    def showFonts (self,event):

        '''Open a tab in the log pane showing a font picker.'''

        c = self.c ; log = c.frame.log ; tabName = 'Fonts'

        if log.frameDict.get(tabName):
            log.selectTab(tabName)
        else:
            log.selectTab(tabName)
            log.createFontPicker(tabName)
    #@-node:ekr.20051019201809:editCommands.show-fonts & helpers
    #@-node:ekr.20051019183105:color & font
    #@+node:ekr.20050920084036.132:comment column...
    #@+node:ekr.20050920084036.133:setCommentColumn
    def setCommentColumn (self,event):

        '''Set the comment column for the indent-to-comment-column command.'''

        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        ins = w.getInsertPoint()
        row,col = g.convertPythonIndexToRowCol(s,ins)
        self.ccolumn = col
    #@nonl
    #@-node:ekr.20050920084036.133:setCommentColumn
    #@+node:ekr.20050920084036.134:indentToCommentColumn
    def indentToCommentColumn (self,event):

        '''Insert whitespace to indent the line containing the insert point to the comment column.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='indent-to-comment-column')

        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        line = s[i:j]
        c1 = int(self.ccolumn)
        line2 = ' ' * c1 + line.lstrip()
        if line2 != line:
            w.delete(i,j)
            w.insert(i,line2)
        w.setInsertPoint(i+c1)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.134:indentToCommentColumn
    #@-node:ekr.20050920084036.132:comment column...
    #@+node:ekr.20050920084036.62:esc methods for Python evaluation
    #@+node:ekr.20050920084036.63:watchEscape (Revise)
    def watchEscape (self,event):

        k = self.k

        if not k.inState():
            k.setState('escape','start',handler=self.watchEscape)
            k.setLabelBlue('Esc ')
        elif k.getStateKind() == 'escape':
            state = k.getState('escape')
            # hi1 = k.keysymHistory [0]
            # hi2 = k.keysymHistory [1]
            data1 = leoKeys.keyHandlerClass.lossage[0]
            data2 = leoKeys.keyHandlerClass.lossage[1]
            ch1, stroke1 = data1
            ch2, stroke2 = data2

            if state == 'esc esc' and event.keysym == ':':
                self.evalExpression(event)
            elif state == 'evaluate':
                self.escEvaluate(event)
            # elif hi1 == hi2 == 'Escape':
            elif stroke1 == 'Escape' and stroke2 == 'Escape':
                k.setState('escape','esc esc')
                k.setLabel('Esc Esc -')
            elif event.keysym not in ('Shift_L','Shift_R'):
                k.keyboardQuit(event)
    #@-node:ekr.20050920084036.63:watchEscape (Revise)
    #@+node:ekr.20050920084036.64:escEvaluate (Revise)
    def escEvaluate (self,event):

        k = self.k
        w = self.editWidget(event)
        if not w: return

        if k.getLabel() == 'Eval:':
            k.setLabel('')

        if event.keysym == 'Return':
            expression = k.getLabel()
            try:
                ok = False
                result = eval(expression,{},{})
                result = str(result)
                w.insert('insert',result)
                ok = True
            finally:
                k.keyboardQuit(event)
                if not ok:
                    k.setLabel('Error: Invalid Expression')
        else:
            k.updateLabel(event)
    #@-node:ekr.20050920084036.64:escEvaluate (Revise)
    #@-node:ekr.20050920084036.62:esc methods for Python evaluation
    #@+node:ekr.20050920084036.65:evalExpression
    def evalExpression (self,event):

        '''Evaluate a Python Expression entered in the minibuffer.'''

        k = self.k ; state = k.getState('eval-expression')

        if state == 0:
            k.setLabelBlue('Eval: ',protect=True)
            k.getArg(event,'eval-expression',1,self.evalExpression)
        else:
            k.clearState()
            try:
                e = k.arg
                result = str(eval(e,{},{}))
                k.setLabelGrey('Eval: %s -> %s' % (e,result))
            except Exception:
                k.setLabelGrey('Invalid Expression: %s' % e)
    #@-node:ekr.20050920084036.65:evalExpression
    #@+node:ekr.20050920084036.66:fill column and centering
    #@+at
    # These methods are currently just used in tandem to center the line or 
    # region within the fill column.
    # for example, dependent upon the fill column, this text:
    # 
    # cats
    # raaaaaaaaaaaats
    # mats
    # zaaaaaaaaap
    # 
    # may look like
    # 
    #                                  cats
    #                            raaaaaaaaaaaats
    #                                  mats
    #                              zaaaaaaaaap
    # 
    # after an center-region command via Alt-x.
    #@-at
    #@@c

    #@+others
    #@+node:ekr.20050920084036.67:centerLine
    def centerLine (self,event):

        '''Centers line within current fill column'''

        k = self.k ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        i,j = g.getLine(s,w.getInsertPoint())
        line = s [i:j].strip()
        if not line or len(line) >= self.fillColumn: return

        self.beginCommand(undoType='center-line')
        n = (self.fillColumn-len(line)) / 2
        ws = ' ' * n
        k = g.skip_ws(s,i)
        if k > i: w.delete(i,k-i)
        w.insert(i,ws)
        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.67:centerLine
    #@+node:ekr.20050920084036.68:setFillColumn
    def setFillColumn (self,event):

        '''Set the fill column used by the center-line and center-region commands.'''

        k = self.k ; state = k.getState('set-fill-column')

        if state == 0:
            k.setLabelBlue('Set Fill Column: ')
            k.getArg(event,'set-fill-column',1,self.setFillColumn)
        else:
            k.clearState()
            try:
                n = int(k.arg)
                k.setLabelGrey('fill column is: %d' % n)
                k.commandName = 'set-fill-column %d' % n
            except ValueError:
                k.resetLabel()
    #@-node:ekr.20050920084036.68:setFillColumn
    #@+node:ekr.20050920084036.69:centerRegion
    def centerRegion (self,event):

        '''Centers the selected text within the fill column'''

        k = self.k ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        sel_1, sel_2 = w.getSelectionRange()
        ind, junk = g.getLine(s,sel_1)
        junk, end = g.getLine(s,sel_2)

        self.beginCommand(undoType='center-region')

        inserted = 0
        while ind < end:
            s = w.getAllText()
            i, j = g.getLine(s,ind)
            line = s [i:j].strip()
            # g.trace(len(line),repr(line))
            if len(line) >= self.fillColumn:
                ind = j
            else:
                n = (self.fillColumn-len(line)) / 2
                inserted += n
                k = g.skip_ws(s,i)
                if k > i: w.delete(i,k-i)
                w.insert(i,' '*n)
                ind = j + n-(k-i)

        w.setSelectionRange(sel_1,sel_2+inserted)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.69:centerRegion
    #@+node:ekr.20050920084036.70:setFillPrefix
    def setFillPrefix( self, event ):

        '''Make the selected text the fill prefix.'''

        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        i,j = w.getSelectionRange()
        self.fillPrefix = s[i:j]
    #@-node:ekr.20050920084036.70:setFillPrefix
    #@+node:ekr.20050920084036.71:_addPrefix
    def _addPrefix (self,ntxt):

        ntxt = ntxt.split('.')
        ntxt = map(lambda a: self.fillPrefix+a,ntxt)
        ntxt = '.'.join(ntxt)
        return ntxt
    #@-node:ekr.20050920084036.71:_addPrefix
    #@-others
    #@-node:ekr.20050920084036.66:fill column and centering
    #@+node:ekr.20060417194232:find (quick)
    #@+node:ekr.20060925151926:backward/findCharacter & helper
    def backwardFindCharacter (self,event):
        return self.findCharacterHelper(event,backward=True,extend=False)

    def backwardFindCharacterExtendSelection (self,event):
        return self.findCharacterHelper(event,backward=True,extend=True)

    def findCharacter (self,event):
        return self.findCharacterHelper(event,backward=False,extend=False)

    def findCharacterExtendSelection (self,event):
        return self.findCharacterHelper(event,backward=False,extend=True)
    #@nonl
    #@+node:ekr.20060417194232.1:findCharacterHelper
    def findCharacterHelper (self,event,backward,extend):

        '''Put the cursor at the next occurance of a character on a line.'''

        c = self.c ; k = c.k ; tag = 'find-char' ; state = k.getState(tag)

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            self.event = event
            self.backward = backward ; self.extend = extend
            self.insert = w.getInsertPoint()
            s = '%s character%s: ' % (
                g.choose(backward,'Backward find','Find'),
                g.choose(extend,' & extend',''))
            k.setLabelBlue(s,protect=True)
            # Get the arg without touching the focus.
            k.getArg(event,tag,1,self.findCharacter,oneCharacter=True,useMinibuffer=False)
        else:
            event = self.event ; w = self.w
            backward = self.backward ; extend = self.extend
            ch = k.arg ; s = w.getAllText()
            ins = w.toPythonIndex(self.insert)
            i = ins + g.choose(backward,-1,+1) # skip the present character.
            if backward:
                start = s.rfind('\n',0,i)
                if start == -1: start = 0
                j = s.rfind(ch,start,max(start,i)) # Skip the character at the cursor.
                if j > -1: self.moveToHelper(event,j,extend)
            else:
                end = s.find('\n',i)
                if end == -1: end = len(s)
                j = s.find(ch,min(i,end),end) # Skip the character at the cursor.
                if j > -1: self.moveToHelper(event,j,extend)
            k.resetLabel()
            k.clearState()
    #@nonl
    #@-node:ekr.20060417194232.1:findCharacterHelper
    #@-node:ekr.20060925151926:backward/findCharacter & helper
    #@+node:ekr.20060417194232.2:findWord and FindWordOnLine & helper
    def findWord(self,event):

        '''Put the cursor at the next word that starts with a character.'''

        return self.findWordHelper(event,oneLine=True)

    def findWordInLine(self,event):

        '''Put the cursor at the next word (on a line) that starts with a character.'''

        return self.findWordHelper(event,oneLine=True)

    #@+node:ekr.20080408060320.1:findWordHelper
    def findWordHelper (self,event,oneLine):

        k = self.k ; tag = 'find-word' ; state = k.getState(tag)

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            self.oneLineFlag = oneLine
            k.setLabelBlue('Find word %sstarting with: ' % (
                g.choose(oneLine,'in line ','')))
            k.getArg(event,tag,1,self.findWord,oneCharacter=True)
        else:        
            ch = k.arg ; w = self.w ; c = k.c
            if ch:
                i = w.getInsertPoint()
                s = w.getAllText()
                if self.oneLineFlag:
                    end = s.find('\n',i) # Limit searches to this line.
                    if end == -1: end = len(s)
                else:
                    end = len(s)

                while i < end:
                    i = s.find(ch,i+1,end) # Ensure progress and i > 0.
                    if i == -1:
                        break
                    elif not g.isWordChar(s[i-1]):
                        w.setSelectionRange(i,i,insert=i)
                        break

            k.resetLabel()
            k.clearState()
    #@-node:ekr.20080408060320.1:findWordHelper
    #@-node:ekr.20060417194232.2:findWord and FindWordOnLine & helper
    #@-node:ekr.20060417194232:find (quick)
    #@+node:ekr.20050920084036.72:goto...
    #@+node:ekr.20050929115226:gotoCharacter
    def gotoCharacter (self,event):

        '''Put the cursor at the n'th character of the buffer.'''

        k = self.k ; state = k.getState('goto-char')

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            k.setLabelBlue("Goto n'th character: ")
            k.getArg(event,'goto-char',1,self.gotoCharacter)
        else:
            n = k.arg ; w = self.w ; ok = False
            if n.isdigit():
                n = int(n)
                if n >= 0:
                    w.setInsertPoint(n)
                    w.seeInsertPoint()
                    ok = True
            if not ok:
                g.es('goto-char takes non-negative integer argument',color='blue')
            k.resetLabel()
            k.clearState()
    #@-node:ekr.20050929115226:gotoCharacter
    #@+node:ekr.20060417181052:gotoGlobalLine
    def gotoGlobalLine (self,event):

        '''Put the cursor at the n'th line of a file or script.
        This is a minibuffer interface to Leo's legacy Go To Line number command.'''

        k = self.k ; tag = 'goto-global-line' ; state = k.getState(tag)

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            k.setLabelBlue('Goto global line: ')
            k.getArg(event,tag,1,self.gotoGlobalLine)
        else:
            n = k.arg
            k.resetLabel()
            k.clearState()
            if n.isdigit():
                self.c.goToLineNumber (n=int(n))
    #@-node:ekr.20060417181052:gotoGlobalLine
    #@+node:ekr.20050929124234:gotoLine
    def gotoLine (self,event):

        '''Put the cursor at the n'th line of the buffer.'''

        k = self.k ; state = k.getState('goto-line')

        if state == 0:
            w = self.editWidget(event) # Sets self.w
            if not w: return
            k.setLabelBlue('Goto line: ')
            k.getArg(event,'goto-line',1,self.gotoLine)
        else:
            n = k.arg ;  w = self.w
            if n.isdigit():
                s = w.getAllText()
                i = g.convertRowColToPythonIndex(s,n,0)
                w.setInsertPoint(i)
                w.seeInsertPoint()
            k.resetLabel()
            k.clearState()
    #@-node:ekr.20050929124234:gotoLine
    #@-node:ekr.20050920084036.72:goto...
    #@+node:ekr.20071114081313:icons...
    #@+at
    # 
    # To do:
    # 
    # - Define standard icons in a subfolder of Icons folder?
    # - Tree control recomputes height of each line.
    #@-at
    #@+node:ekr.20080108092811: Helpers
    #@+node:ekr.20080108091349:appendImageDictToList
    def appendImageDictToList(self,aList,iconDir,path,xoffset,**kargs):

        c = self.c
        path = g.os_path_abspath(g.os_path_join(iconDir,path))
        relPath = g.makePathRelativeTo(path,iconDir)

        image,image_height = self.getImage(path)
        if not image:
            g.es('can not load image:',path)
            return xoffset

        if image_height is None:
            yoffset = 0
        else:
            yoffset = 0 # (c.frame.tree.line_height-image_height)/2
            # TNB: I suspect this is being done again in the drawing code

        newEntry = {
            'type' : 'file',
            'file' : path,
            'relPath': relPath,
            'where' : 'beforeHeadline',
            'yoffset' : yoffset, 'xoffset' : xoffset, 'xpad' : 1, # -2,
            'on' : 'tnode',
        }
        newEntry.update(kargs)  # may switch 'on' to 'vnode'
        aList.append (newEntry)
        xoffset += 2

        return xoffset
    #@-node:ekr.20080108091349:appendImageDictToList
    #@+node:tbrown.20080119085249:getIconList
    def getIconList(self, p):
        """Return list of icons for position p, call setIconList to apply changes"""

        fromTnode = []
        if hasattr(p.v.t,'unknownAttributes'):
            fromTnode = [dict(i) for i in p.v.t.unknownAttributes.get('icons',[])]
            for i in fromTnode: i['on'] = 'tnode'

        fromVnode = []
        if hasattr(p.v,'unknownAttributes'):
            fromVnode = [dict(i) for i in p.v.unknownAttributes.get('icons',[])]
            for i in fromVnode: i['on'] = 'vnode'

        fromTnode.extend(fromVnode)
        return fromTnode
    #@-node:tbrown.20080119085249:getIconList
    #@+node:tbrown.20080119085249.1:setIconList
    def _setIconListHelper(self, p, subl, uaLoc):
        """icon setting code common between v and t nodes

        p - postion
        subl - list of icons for the v or t node
        uaLoc - the v or t node"""

        # FIXME lineYOffset is expected to be on a tnode in drawing code

        if subl:
            if not hasattr(uaLoc,'unknownAttributes'):
                uaLoc.unknownAttributes = {}
            uaLoc.unknownAttributes['icons'] = list(subl)
            # g.es((p.headString(),uaLoc.unknownAttributes['icons']))
            uaLoc.unknownAttributes["lineYOffset"] = 3
            p.setDirty()
        else:
            if hasattr(uaLoc,'unknownAttributes'):
                if 'icons' in uaLoc.unknownAttributes:
                    del uaLoc.unknownAttributes['icons']
                    uaLoc.unknownAttributes["lineYOffset"] = 0
                    p.setDirty()

    def dHash(self, d):
        """Hash a dictionary"""
        l = d.keys()
        l.sort()
        return ''.join(['%s%s' % (str(k),str(d[k])) for k in l])

    def setIconList(self, p, l):
        """Set list of icons for position p to l"""

        current = self.getIconList(p)
        if not l and not current: return  # nothing to do
        lHash = ''.join([self.dHash(i) for i in l])
        cHash = ''.join([self.dHash(i) for i in current])
        if lHash == cHash:
            # no difference between original and current list of dictionaries
            return


        subl = [i for i in l if i.get('on') != 'vnode']
        self._setIconListHelper(p, subl, p.v.t)

        subl = [i for i in l if i.get('on') == 'vnode']
        self._setIconListHelper(p, subl, p.v)
    #@-node:tbrown.20080119085249.1:setIconList
    #@+node:ekr.20071114083142:getImage
    def getImage (self,path):

        c = self.c

        try:
            from PIL import Image
        except ImportError:
            Image = None
            g.es('can not import Image module from PIL',color='blue')

        try:
            from PIL import ImageTk
        except ImportError:
            try:
                import ImageTk
            except ImportError:
                ImageTk = None
                g.es('can not import ImageTk module',color='blue')

        try:
            if Image and ImageTk:
                image1 = Image.open(path)
                image = ImageTk.PhotoImage(image1)
            else:
                import Tkinter as Tk
                image = Tk.PhotoImage(master=c.frame.tree.canvas,file=path)
            return image,image.height()
        except Exception:
            return None,None
    #@-node:ekr.20071114083142:getImage
    #@-node:ekr.20080108092811: Helpers
    #@+node:ekr.20071114082418.2:deleteAllIcons (no longer used)
    # def deleteAllIcons (self,event=None):

        # c = self.c

        # for p in c.allNodes_iter():

            # if hasattr(p.v.t,"unknownAttributes"):
                # a = p.v.t.unknownAttributes
                # iconsList = a.get("icons")
                # if iconsList:
                    # a["icons"] = []
                    # a["lineYOffset"] = 0
                    # p.setDirty()
                    # c.setChanged(True)

        # c.redraw()
    #@-node:ekr.20071114082418.2:deleteAllIcons (no longer used)
    #@+node:ekr.20071114082418:deleteFirstIcon
    def deleteFirstIcon (self,event=None):

        c = self.c ; p = c.currentPosition()

        aList = self.getIconList(p)

        if aList:
            self.setIconList(p, aList[1:])
            c.setChanged(True)
            c.redraw()
    #@nonl
    #@-node:ekr.20071114082418:deleteFirstIcon
    #@+node:ekr.20071114092622:deleteIconByName
    def deleteIconByName (self,t,name,relPath):
        """for use by the right-click remove icon callback"""
        c = self.c ; p = c.currentPosition()

        aList = self.getIconList(p)
        if not aList: return

        basePath = g.os_path_abspath(g.os_path_normpath(g.os_path_join(g.app.loadDir,"..","Icons")))
        absRelPath = g.os_path_abspath(g.os_path_normpath(g.os_path_join(basePath,relPath)))
        name = g.os_path_abspath(name)

        newList = []
        for d in aList:
            name2 = d.get('file')
            name2 = g.os_path_abspath(name2)
            name2rel = d.get('relPath')
            # g.trace('name',name,'\nrelPath',relPath,'\nabsRelPath',absRelPath,'\nname2',name2,'\nname2rel',name2rel)
            if not (name == name2 or absRelPath == name2 or relPath == name2rel):
                newList.append(d)

        if len(newList) != len(aList):
            self.setIconList(p, newList)       
            c.setChanged(True)
            c.redraw()
        else:
            g.trace('not found',name)



    #@-node:ekr.20071114092622:deleteIconByName
    #@+node:ekr.20071114085054:deleteLastIcon
    def deleteLastIcon (self,event=None):

        c = self.c ;  p = c.currentPosition()

        c = self.c ; p = c.currentPosition()

        aList = self.getIconList(p)

        if aList:
            self.setIconList(p, aList[:-1])
            c.setChanged(True)
            c.redraw()
    #@nonl
    #@-node:ekr.20071114085054:deleteLastIcon
    #@+node:ekr.20071114082418.1:deleteNodeIcons
    def deleteNodeIcons (self,event=None):

        c = self.c ; p = c.currentPosition()

        if hasattr(p.v.t,"unknownAttributes"):
            a = p.v.t.unknownAttributes
            if dict:  # ???
                self.setIconList(p,[])
                a["lineYOffset"] = 0
                p.setDirty()
                c.setChanged(True)
                c.redraw()
    #@-node:ekr.20071114082418.1:deleteNodeIcons
    #@+node:ekr.20071114081313.1:insertIcon
    def insertIcon (self,event=None):

        c = self.c ; p = c.currentPosition()

        iconDir = g.os_path_abspath(g.os_path_normpath(g.os_path_join(g.app.loadDir,"..","Icons")))
        os.chdir(iconDir)

        paths = g.app.gui.runOpenFileDialog(
            title='Get Icons',
            filetypes=[('All files','*'),('Gif','*.gif'), ('Bitmap','*.bmp'),('Icon','*.ico'),],
            defaultextension=None,
            multiple=True)

        if not paths: return

        aList = [] ; xoffset = 2
        for path in paths:
            xoffset = self.appendImageDictToList(aList,iconDir,path,xoffset)

        aList2 = self.getIconList(p)
        aList2.extend(aList)
        self.setIconList(p, aList2)
        c.setChanged(True)
        c.redraw()
    #@-node:ekr.20071114081313.1:insertIcon
    #@+node:ekr.20080108090719:insertIconFromFile
    def insertIconFromFile (self,path,p=None,pos=None,**kargs):

        c = self.c
        if p is None: p = c.currentPosition()

        iconDir = g.os_path_abspath(g.os_path_normpath(g.os_path_join(g.app.loadDir,"..","Icons")))
        os.chdir(iconDir)

        aList = [] ; xoffset = 2
        xoffset = self.appendImageDictToList(aList,iconDir,path,xoffset,**kargs)

        aList2 = self.getIconList(p)
        if pos is None: pos = len(aList2)
        aList2.insert(pos,aList[0])
        self.setIconList(p, aList2)
        c.setChanged(True)
        c.redraw()
    #@-node:ekr.20080108090719:insertIconFromFile
    #@-node:ekr.20071114081313:icons...
    #@+node:ekr.20050920084036.74:indent...
    #@+node:ekr.20050920084036.75:backToIndentation
    def backToIndentation (self,event):

        '''Position the point at the first non-blank character on the line.'''

        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='back-to-indentation')

        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        while i < j and s[i] in (' \t'):
            i += 1
        w.setInsertPoint(i)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.75:backToIndentation
    #@+node:ekr.20050920084036.76:deleteIndentation
    def deleteIndentation (self,event):

        '''Delete indentation in the presently line.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return


        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        line = s[i:j]
        line2 = s[i:j].lstrip()
        delta = len(line) - len(line2)
        if delta:
            self.beginCommand(undoType='delete-indentation')

            w.delete(i,j)
            w.insert(i,line2)
            ins -= delta
            w.setSelectionRange(ins,ins,insert=ins)

            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.76:deleteIndentation
    #@+node:ekr.20050920084036.78:indentRelative
    def indentRelative (self,event):

        '''The indent-relative command indents at the point based on the previous
        line (actually, the last non-empty line.) It inserts whitespace at the
        point, moving point, until it is underneath an indentation point in the
        previous line.

        An indentation point is the end of a sequence of whitespace or the end of
        the line. If the point is farther right than any indentation point in the
        previous line, the whitespace before point is deleted and the first
        indentation point then applicable is used. If no indentation point is
        applicable even then whitespace equivalent to a single tab is inserted.'''

        c = self.c ; undoType = 'indent-relative' ; w = self.editWidget(event)
        if not w: return
        s = w.getAllText()
        ins = w.getInsertPoint()
        oldSel = w.getSelectionRange()
        oldYview = w.getYScrollPosition()
        # Find the previous non-blank line
        i,j = g.getLine(s,ins)
        while 1:
            if i <= 0: return
            i,j = g.getLine(s,i-1)
            line = s[i:j]
            if line.strip(): break
        self.beginCommand(undoType=undoType)
        try:
            k = g.skip_ws(s,i)
            ws = s[i:k]
            i2,j2 = g.getLine(s,ins)
            k = g.skip_ws(s,i2)
            line = ws + s[k:j2]
            w.delete(i2,j2)
            w.insert(i2,line)
            w.setInsertPoint(i2+len(ws))
            c.frame.body.onBodyChanged(undoType,oldSel=oldSel,oldText=s,oldYview=oldYview)
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.78:indentRelative
    #@-node:ekr.20050920084036.74:indent...
    #@+node:ekr.20050920084036.85:insert & delete...
    #@+node:ekr.20060417171125:addSpace/TabToLines & removeSpace/TabFromLines & helper
    def addSpaceToLines (self,event):
        '''Add a space to start of all lines, or all selected lines.'''
        self.addRemoveHelper(event,ch=' ',add=True,undoType='add-space-to-lines')

    def addTabToLines (self,event):
        '''Add a tab to start of all lines, or all selected lines.'''
        self.addRemoveHelper(event,ch='\t',add=True,undoType='add-tab-to-lines')

    def removeSpaceFromLines (self,event):
        '''Remove a space from start of all lines, or all selected lines.'''
        self.addRemoveHelper(event,ch=' ',add=False,undoType='remove-space-from-lines')

    def removeTabFromLines (self,event):
        '''Remove a tab from start of all lines, or all selected lines.'''
        self.addRemoveHelper(event,ch='\t',add=False,undoType='remove-tab-from-lines')
    #@+node:ekr.20060417172056:addRemoveHelper
    def addRemoveHelper(self,event,ch,add,undoType):

        c = self.c ; k = self.k ; w = self.editWidget(event)
        if not w: return

        if w.hasSelection():s = w.getSelectedText()
        else:               s = w.getAllText()
        if not s: return

        # Insert or delete spaces instead of tabs when negative tab width is in effect.
        d = g.scanDirectives(c) ; width = d.get('tabwidth')
        if ch == '\t' and width < 0: ch = ' ' * abs(width)

        self.beginCommand(undoType=undoType)

        lines = g.splitLines(s)

        if add:
            result = [ch + line for line in lines]
        else:
            result = [g.choose(line.startswith(ch),line[len(ch):],line) for line in lines]

        result = ''.join(result)

        # g.trace('add',add,'hasSelection',w.hasSelection(),'result',repr(result))

        if w.hasSelection():
            i,j = w.getSelectionRange()
            w.delete(i,j)
            w.insert(i,result)
            w.setSelectionRange(i,i+len(result))
        else:
            w.setAllText(result)
            w.setSelectionRange(0,len(s))

        self.endCommand(changed=True,setLabel=True)

    #@-node:ekr.20060417172056:addRemoveHelper
    #@-node:ekr.20060417171125:addSpace/TabToLines & removeSpace/TabFromLines & helper
    #@+node:ekr.20051026092433.1:backwardDeleteCharacter
    def backwardDeleteCharacter (self,event=None):

        '''Delete the character to the left of the cursor.'''

        c = self.c ; p = c.currentPosition()
        w = self.editWidget(event,allowMinibuffer=True)
        if not w: return

        wname = c.widget_name(w)
        ins = w.getInsertPoint()
        i,j = w.getSelectionRange()
        # g.trace(wname,i,j,ins)

        if wname.startswith('body'):
            self.beginCommand()
            try:
                d = g.scanDirectives(c,p)
                tab_width = d.get("tabwidth",c.tab_width)
                changed = True
                if i != j:
                    w.delete(i,j)
                    w.setSelectionRange(i,i,insert=i)
                elif i == 0:
                    changed = False
                elif tab_width > 0:
                    w.delete(ins-1)
                    w.setSelectionRange(ins-1,ins-1,insert=ins-1)
                else:
                    #@                << backspace with negative tab_width >>
                    #@+node:ekr.20051026092746:<< backspace with negative tab_width >>
                    s = prev = w.getAllText()
                    ins = w.getInsertPoint()
                    i,j = g.getLine(s,ins)
                    s = prev = s[i:ins]
                    n = len(prev)
                    abs_width = abs(tab_width)

                    # Delete up to this many spaces.
                    n2 = (n % abs_width) or abs_width
                    n2 = min(n,n2) ; count = 0

                    while n2 > 0:
                        n2 -= 1
                        ch = prev[n-count-1]
                        if ch != ' ': break
                        else: count += 1

                    # Make sure we actually delete something.
                    i = ins-(max(1,count))
                    w.delete(i,ins)
                    w.setSelectionRange(i,i,insert=i)
                    #@-node:ekr.20051026092746:<< backspace with negative tab_width >>
                    #@nl
            finally:
                self.endCommand(changed=True,setLabel=False) # Necessary to make text changes stick.
        else:
            # No undo in this widget.
            # Make sure we actually delete something if we can.
            s = w.getAllText()
            if i != j:
                j = max(i,min(j,len(s)))
                w.delete(i,j)
                w.setSelectionRange(i,i,insert=i)
            elif ins != 0:
                # Do nothing at the start of the headline.
                w.delete(ins-1)
                ins = ins-1
                w.setSelectionRange(ins,ins,insert=ins)
    #@-node:ekr.20051026092433.1:backwardDeleteCharacter
    #@+node:ekr.20070325094935:cleanAllLines
    def cleanAllLines (self,event):

        '''Clean all lines in the selected tree.'''

        c = self.c ; current = c.currentPosition()
        w = c.frame.body.bodyCtrl
        if not w: return

        c.beginUpdate()
        try:
            for p in current.self_and_subtree_iter():
                c.selectPosition(p)
                w.setSelectionRange(0,0,insert=0)
                c.editCommands.cleanLines(event)
            c.selectPosition(current)
        finally:
            c.endUpdate(False)
    #@-node:ekr.20070325094935:cleanAllLines
    #@+node:ekr.20060415112257:cleanLines
    def cleanLines (self,event):

        '''Removes leading whitespace from otherwise blanks lines.'''

        k = self.k ; w = self.editWidget(event)
        if not w: return

        if w.hasSelection():
            s = w.getSelectedText()
        else:
            s = w.getAllText()

        lines = [] ; changed = False
        for line in g.splitlines(s):
            if line.strip():
                lines.append(line)
            else:
                if line.endswith('\n'):
                    lines.append('\n')
                changed = changed or '\n' != line

        if changed:
            self.beginCommand(undoType='clean-lines')
            result = ''.join(lines)
            if w.hasSelection():
                i,j = w.getSelectionRange()
                w.delete(i,j)
                w.insert(i,result)
                w.setSelectionRange(i,j+len(result))
            else:
                w.delete(0,'end')
                w.insert(0,result)
            self.endCommand(changed=changed,setLabel=True)
    #@-node:ekr.20060415112257:cleanLines
    #@+node:ekr.20060414085834:clearSelectedText
    def clearSelectedText (self,event):

        '''Delete the selected text.'''

        c = self.c ; w = self.editWidget(event)
        if not w: return

        i,j = w.getSelectionRange()
        if i == j: return

        self.beginCommand(undoType='clear-selected-text')

        w.delete(i,j)
        w.setInsertPoint(i)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20060414085834:clearSelectedText
    #@+node:ekr.20050920084036.87:deleteNextChar
    def deleteNextChar (self,event):

        '''Delete the character to the right of the cursor.'''

        c = self.c ; w = self.editWidget(event,allowMinibuffer=True)
        if not w: return

        s = w.getAllText()
        i,j = w.getSelectionRange()

        self.beginCommand(undoType='delete-char')

        changed = True
        if i != j:
            w.delete(i,j)
            w.setInsertPoint(i)
        elif j < len(s):
            w.delete(i)
            w.setInsertPoint(i)
        else:
            changed = False

        self.endCommand(changed=changed,setLabel=False)
    #@-node:ekr.20050920084036.87:deleteNextChar
    #@+node:ekr.20050920084036.135:deleteSpaces
    def deleteSpaces (self,event,insertspace=False):

        '''Delete all whitespace surrounding the cursor.'''

        c = self.c ; w = self.editWidget(event)
        undoType = g.choose(insertspace,'insert-space','delete-spaces')
        if not w: return
        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        w1 = ins-1
        while w1 >= i and s[w1].isspace():
            w1 -= 1
        w1 += 1
        w2 = ins
        while w2 <= j and s[w2].isspace():
            w2 += 1
        spaces = s[w1:w2]
        if spaces:
            self.beginCommand(undoType=undoType)
            if insertspace: s = s[:w1] + ' ' + s[w2:]
            else:           s = s[:w1] + s[w2:]
            w.setAllText(s)
            w.setInsertPoint(w1)
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.135:deleteSpaces
    #@+node:ekr.20050920084036.138:insertNewLine
    def insertNewLine (self,event):

        '''Insert a newline at the cursor.'''

        w = self.editWidget(event)
        if not w: return
        wname = g.app.gui.widget_name(w)
        if wname.startswith('head'): return

        self.beginCommand(undoType='insert-newline')

        i = w.getInsertPoint()
        w.insert(i,'\n')
        w.setInsertPoint(i+1)

        self.endCommand(changed=True,setLabel=False)

    insertNewline = insertNewLine
    #@-node:ekr.20050920084036.138:insertNewLine
    #@+node:ekr.20050920084036.86:insertNewLineAndTab
    def insertNewLineAndTab (self,event):

        '''Insert a newline and tab at the cursor.'''

        w = self.editWidget(event)
        if not w: return
        wname = g.app.gui.widget_name(w)
        if wname.startswith('head'): return

        self.beginCommand(undoType='insert-newline-and-indent')

        i = w.getInsertPoint()
        w.insert(i,'\n\t')
        w.setInsertPoint(i+2)

        self.endCommand(changed=True,setLabel=False)
    #@-node:ekr.20050920084036.86:insertNewLineAndTab
    #@+node:ekr.20050920084036.139:insertParentheses
    def insertParentheses (self,event):

        '''Insert () at the cursor.'''

        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='insert-parenthesis')

        i = w.getInsertPoint()
        w.insert(i,'()')
        w.setInsertPoint(i+1)

        self.endCommand(changed=True,setLabel=False)
    #@-node:ekr.20050920084036.139:insertParentheses
    #@+node:ekr.20050920084036.141:removeBlankLines
    def removeBlankLines (self,event):

        '''The remove-blank-lines command removes lines containing nothing but
        whitespace. If there is a text selection, only lines within the selected
        text are affected; otherwise all blank lines in the selected node are
        affected.'''

        c = self.c
        head,lines,tail,oldSel,oldYview = c.getBodyLines()

        changed = False ; result = []
        for line in lines:
            if line.strip():
                result.append(line)
            else:
                changed = True
        result = ''.join(result)

        if changed:
            oldSel = None ; undoType = 'remove-blank-lines'
            c.updateBodyPane(head,result,tail,undoType,oldSel,oldYview)
    #@-node:ekr.20050920084036.141:removeBlankLines
    #@+node:ekr.20051125080855:selfInsertCommand, helpers
    def selfInsertCommand(self,event,action='insert'):

        '''Insert a character in the body pane.
        This is the default binding for all keys in the body pane.'''

        w = self.editWidget(event)
        if not w: return 'break'
        #@    << set local vars >>
        #@+node:ekr.20061103114242:<< set local vars >>
        c = self.c
        p = c.currentPosition()
        gui = g.app.gui
        ch = gui.eventChar(event)
        keysym = gui.eventKeysym(event)
        if keysym == 'Return':
            ch = '\n' # This fixes the MacOS return bug.
        if keysym == 'Tab': # Support for wx_alt_gui plugin.
            ch = '\t'
        name = c.widget_name(w)
        oldSel =  name.startswith('body') and w.getSelectionRange() or (None,None)
        oldText = name.startswith('body') and p.bodyString() or ''
        undoType = 'Typing'
        trace = c.config.getBool('trace_masterCommand')
        brackets = self.openBracketsList + self.closeBracketsList
        inBrackets = ch and g.toUnicode(ch,g.app.tkEncoding) in brackets
        if trace: g.trace(name,repr(ch),ch and ch in brackets)
        #@nonl
        #@-node:ekr.20061103114242:<< set local vars >>
        #@nl
        #g.trace('ch',repr(ch))
        if g.doHook("bodykey1",c=c,p=p,v=p,ch=ch,oldSel=oldSel,undoType=undoType):
            return "break" # The hook claims to have handled the event.
        if ch == '\t':
            self.updateTab(p,w)
        elif ch == '\b':
            # This is correct: we only come here if there no bindngs for this key. 
            self.backwardDeleteCharacter(event)
        elif ch in ('\r','\n'):
            ch = '\n'
            self.insertNewlineHelper(w,oldSel,undoType)
        elif inBrackets and self.autocompleteBrackets:
            self.updateAutomatchBracket(p,w,ch,oldSel)
        elif ch: # Null chars must not delete the selection.
            i,j = oldSel
            if i > j: i,j = j,i
            # Use raw insert/delete to retain the coloring.
            if i != j:                  w.delete(i,j)
            elif action == 'overwrite': w.delete(i)
            w.insert(i,ch)
            w.setInsertPoint(i+1)
            if inBrackets and self.flashMatchingBrackets:

                self.flashMatchingBracketsHelper(w,i,ch)               
        else:
            return 'break' # This method *always* returns 'break'

        # Set the column for up and down keys.
        spot = w.getInsertPoint()
        c.editCommands.setMoveCol(w,spot)

        # Update the text and handle undo.
        newText = w.getAllText()
        changed = newText != oldText
        # g.trace('ch',repr(ch),'changed',changed,'newText',repr(newText[-10:]))
        if changed:
            # g.trace('ins',w.getInsertPoint())
            c.frame.body.onBodyChanged(undoType=undoType,
                oldSel=oldSel,oldText=oldText,oldYview=None)

        g.doHook("bodykey2",c=c,p=p,v=p,ch=ch,oldSel=oldSel,undoType=undoType)
        return 'break'
    #@+node:ekr.20051026171121:insertNewlineHelper
    def insertNewlineHelper (self,w,oldSel,undoType):

        c = self.c ; p = c.currentPosition()
        i,j = oldSel ; ch = '\n'

        if i != j:
            # No auto-indent if there is selected text.
            w.delete(i,j)
            w.insert(i,ch)
            w.setInsertPoint(i+1)
        else:
            w.insert(i,ch)
            w.setInsertPoint(i+1)

            allow_in_nocolor = c.config.getBool('autoindent_in_nocolor_mode')
            if (
                (allow_in_nocolor or c.frame.body.colorizer.useSyntaxColoring(p)) and
                undoType != "Change"
            ):
                # No auto-indent if in @nocolor mode or after a Change command.
                self.updateAutoIndent(p,w)

        w.seeInsertPoint()
    #@nonl
    #@-node:ekr.20051026171121:insertNewlineHelper
    #@+node:ekr.20060804095512:initBracketMatcher
    def initBracketMatcher (self,c):

        self.openBracketsList  = c.config.getString('open_flash_brackets')  or '([{'
        self.closeBracketsList = c.config.getString('close_flash_brackets') or ')]}'

        if len(self.openBracketsList) != len(self.closeBracketsList):
            g.es_print('bad open/close_flash_brackets setting: using defaults')
            self.openBracketsList  = '([{'
            self.closeBracketsList = ')]}'

        # g.trace('self.openBrackets',openBrackets)
        # g.trace('self.closeBrackets',closeBrackets)
    #@-node:ekr.20060804095512:initBracketMatcher
    #@+node:ekr.20060627083506:flashMatchingBracketsHelper
    def flashMatchingBracketsHelper (self,w,i,ch):

        d = {}
        if ch in self.openBracketsList:
            for z in xrange(len(self.openBracketsList)):
                d [self.openBracketsList[z]] = self.closeBracketsList[z]
            reverse = False # Search forward
        else:
            for z in xrange(len(self.openBracketsList)):
                d [self.closeBracketsList[z]] = self.openBracketsList[z]
            reverse = True # Search backward

        delim2 = d.get(ch)

        s = w.getAllText()
        j = g.skip_matching_python_delims(s,i,ch,delim2,reverse=reverse)
        if j != -1:
            self.flashCharacter(w,j)
    #@-node:ekr.20060627083506:flashMatchingBracketsHelper
    #@+node:ekr.20060627091557:flashCharacter
    def flashCharacter(self,w,i):

        bg      = self.bracketsFlashBg or 'DodgerBlue1'
        fg      = self.bracketsFlashFg or 'white'
        flashes = self.bracketsFlashCount or 2
        delay   = self.bracketsFlashDelay or 75

        w.flashCharacter(i,bg,fg,flashes,delay)
    #@-node:ekr.20060627091557:flashCharacter
    #@+node:ekr.20051027172949:updateAutomatchBracket
    def updateAutomatchBracket (self,p,w,ch,oldSel):

        # assert ch in ('(',')','[',']','{','}')

        c = self.c ; d = g.scanDirectives(c,p)
        i,j = oldSel
        language = d.get('language')
        s = w.getAllText()

        if ch in ('(','[','{',):
            automatch = language not in ('plain',)
            if automatch:
                ch = ch + {'(':')','[':']','{':'}'}.get(ch)
            if i != j: w.delete(i,j)
            w.insert(i,ch)
            if automatch:
                ins = w.getInsertPoint()
                w.setInsertPoint(ins-1)
        else:
            ins = w.getInsertPoint()
            ch2 = ins<len(s) and s[ins] or ''
            if ch2 in (')',']','}'):
                ins = w.getInsertPoint()
                w.setInsertPoint(ins+1)
            else:
                if i != j: w.delete(i,j)
                w.insert(i,ch)
                w.setInsertPoint(i+1)
    #@-node:ekr.20051027172949:updateAutomatchBracket
    #@+node:ekr.20051026171121.1:udpateAutoIndent
    def updateAutoIndent (self,p,w):

        c = self.c ; d = g.scanDirectives(c,p)
        tab_width = d.get("tabwidth",c.tab_width)
        # Get the previous line.
        s = w.getAllText()
        ins = w.getInsertPoint()
        i = g.skip_to_start_of_line(s,ins)
        i,j = g.getLine(s,i-1)
        s = s[i:j-1]
        # g.trace(i,j,repr(s))

        # Add the leading whitespace to the present line.
        junk, width = g.skip_leading_ws_with_indent(s,0,tab_width)
        # g.trace('width',width,'tab_width',tab_width)

        if s and s [-1] == ':':
            # For Python: increase auto-indent after colons.
            if g.scanColorDirectives(c,p) == 'python':
                width += abs(tab_width)
        if self.smartAutoIndent:
            # Determine if prev line has unclosed parens/brackets/braces
            bracketWidths = [width] ; tabex = 0
            for i in range(0,len(s)):
                if s [i] == '\t':
                    tabex += tab_width-1
                if s [i] in '([{':
                    bracketWidths.append(i+tabex+1)
                elif s [i] in '}])' and len(bracketWidths) > 1:
                    bracketWidths.pop()
            width = bracketWidths.pop()
        ws = g.computeLeadingWhitespace(width,tab_width)
        if ws:
            i = w.getInsertPoint()
            w.insert(i,ws)
            w.setInsertPoint(i+len(ws))
    #@-node:ekr.20051026171121.1:udpateAutoIndent
    #@+node:ekr.20051026092433:updateTab
    def updateTab (self,p,w):

        c = self.c
        d = g.scanDirectives(c,p)
        tab_width = d.get("tabwidth",c.tab_width)
        i,j = w.getSelectionRange()
            # Returns insert point if no selection, with i <= j.

        if i != j:
            w.delete(i,j)

        if tab_width > 0:
            w.insert(i,'\t')
            ins = i+1
        else:
            # Get the preceeding characters.
            s = w.getAllText()
            start = g.skip_to_start_of_line(s,i)
            s2 = s[start:i]

            # Compute n, the number of spaces to insert.
            width = g.computeWidth(s2,tab_width)
            n = abs(tab_width) - (width % abs(tab_width))
            # g.trace('n',n)
            w.insert(i,' ' * n)
            ins = i+n

        w.setSelectionRange(ins,ins,insert=ins)
    #@nonl
    #@-node:ekr.20051026092433:updateTab
    #@-node:ekr.20051125080855:selfInsertCommand, helpers
    #@-node:ekr.20050920084036.85:insert & delete...
    #@+node:ekr.20050920084036.79:info...
    #@+node:ekr.20050920084036.80:howMany
    def howMany (self,event):

        '''Print how many occurances of a regular expression are found
        in the body text of the presently selected node.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        state = k.getState('how-many')
        if state == 0:
            k.setLabelBlue('How many: ',protect = True)
            k.getArg(event,'how-many',1,self.howMany)
        else:
            k.clearState()
            s = w.getAllText()
            reg = re.compile(k.arg)
            i = reg.findall(s)
            k.setLabelGrey('%s occurances of %s' % (len(i),k.arg))
    #@-node:ekr.20050920084036.80:howMany
    #@+node:ekr.20050920084036.81:lineNumber
    def lineNumber (self,event):

        '''Print the line and column number and percentage of insert point.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        i = w.getInsertPoint()
        row,col = g.convertPythonIndexToRowCol(s,i)
        percent = int((i*100)/len(s))

        k.setLabelGrey(
            'char: %s row: %d col: %d pos: %d (%d%% of %d)' % (
                repr(s[i]),row,col,i,percent,len(s)))
    #@-node:ekr.20050920084036.81:lineNumber
    #@+node:ekr.20050920084036.83:viewLossage
    def viewLossage (self,event):

        '''Put the Emacs-lossage in the minibuffer label.'''

        k = self.k

        g.es('lossage...')
        aList = leoKeys.keyHandlerClass.lossage
        aList.reverse()
        for data in aList:
            ch,stroke = data
            d = {' ':'Space','\t':'Tab','\b':'Backspace','\n':'Newline','\r':'Return'}
            g.es('',stroke or d.get(ch) or ch or 'None')
    #@-node:ekr.20050920084036.83:viewLossage
    #@+node:ekr.20050920084036.84:whatLine
    def whatLine (self,event):

        '''Print the line number of the line containing the cursor.'''

        k = self.k ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        i = w.getInsertPoint()
        row,col = g.convertPythonIndexToRowCol(s,i)

        k.keyboardQuit(event)
        k.setLabel("Line %s" % row)
    #@-node:ekr.20050920084036.84:whatLine
    #@-node:ekr.20050920084036.79:info...
    #@+node:ekr.20050920084036.88:line...
    #@+node:ekr.20050920084036.90:flushLines
    def flushLines (self,event):

        '''Delete each line that contains a match for regexp, operating on the text after point.

        In Transient Mark mode, if the region is active, the command operates on the region instead.'''

        k = self.k ; state = k.getState('flush-lines')

        if state == 0:
            k.setLabelBlue('Flush lines regexp: ',protect=True)
            k.getArg(event,'flush-lines',1,self.flushLines)
        else:
            k.clearState()
            k.resetLabel()
            self.linesHelper(event,k.arg,'flush')
            k.commandName = 'flush-lines %s' % k.arg
    #@-node:ekr.20050920084036.90:flushLines
    #@+node:ekr.20051002095724:keepLines
    def keepLines (self,event):

        '''Delete each line that does not contain a match for regexp, operating on the text after point.

        In Transient Mark mode, if the region is active, the command operates on the region instead.'''

        k = self.k ; state = k.getState('keep-lines')

        if state == 0:
            k.setLabelBlue('Keep lines regexp: ',protect=True)
            k.getArg(event,'keep-lines',1,self.keepLines)
        else:
            k.clearState()
            k.resetLabel()
            self.linesHelper(event,k.arg,'keep')
            k.commandName = 'keep-lines %s' % k.arg
    #@-node:ekr.20051002095724:keepLines
    #@+node:ekr.20050920084036.92:linesHelper
    def linesHelper (self,event,pattern,which):

        k = self.k
        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType=which+'-lines')
        if w.hasSelection():
            i,end = w.getSelectionRange()
        else:
            i = w.getInsertPoint()
            end = 'end'
        txt = w.get(i,end)
        tlines = txt.splitlines(True)
        if which == 'flush':    keeplines = list(tlines)
        else:                   keeplines = []

        try:
            regex = re.compile(pattern)
            for n, z in enumerate(tlines):
                f = regex.findall(z)
                if which == 'flush' and f:
                    keeplines [n] = None
                elif f:
                    keeplines.append(z)
        except Exception, x:
            return
        if which == 'flush':
            keeplines = [x for x in keeplines if x != None]
        w.delete(i,end)
        w.insert(i,''.join(keeplines))
        w.setInsertPoint(i)
        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.92:linesHelper
    #@+node:ekr.20050920084036.77:splitLine
    def splitLine (self,event):

        '''Split a line at the cursor position.'''

        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='split-line')

        s = w.getAllText()
        ins = w.getInsertPoint()
        w.setAllText(s[:ins] + '\n' + s[ins:])
        w.setInsertPoint(ins+1)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.77:splitLine
    #@-node:ekr.20050920084036.88:line...
    #@+node:ekr.20050929114218:move cursor... (leoEditCommands)
    #@+node:ekr.20051218170358: helpers
    #@+node:ekr.20060113130510:extendHelper
    def extendHelper (self,w,extend,spot,upOrDown=False):
        '''Handle the details of extending the selection.
        This method is called for all cursor moves.

        extend: Clear the selection unless this is True.
        spot:   The *new* insert point.
        '''
        c = self.c ; p = c.currentPosition()
        extend = extend or self.extendMode

        ins = w.getInsertPoint()
        i,j = w.getSelectionRange()
        # g.trace('extend',extend,'ins',ins,'sel=',i,j,'spot=',spot,'moveSpot',self.moveSpot)

        # Reset the move spot if needed.
        if self.moveSpot is None or p.v.t != self.moveSpotNode:
            # g.trace('no spot')
            self.setMoveCol(w,g.choose(extend,ins,spot)) # sets self.moveSpot.
        elif extend:
            if i == j or self.moveSpot not in (i,j):
                # g.trace('spot not in sel')
                self.setMoveCol(w,ins) # sets self.moveSpot.
        else:
            if upOrDown:
                s = w.getAllText()
                i2,j2 = g.getLine(s,spot)
                line = s[i2:j2]
                row,col = g.convertPythonIndexToRowCol(s,spot)
                if True: #### j2 < len(s)-1:
                    n = min(self.moveCol,max(0,len(line)-1))
                else:
                    n = min(self.moveCol,max(0,len(line))) # A tricky boundary.
                # g.trace('using moveCol',self.moveCol,'line',repr(line),'n',n)
                spot = g.convertRowColToPythonIndex(s,row,n)
            else:  # Plain move forward or back.
                # g.trace('plain forward/back move')
                self.setMoveCol(w,spot) # sets self.moveSpot.

        if extend:
            if spot < self.moveSpot:
                w.setSelectionRange(spot,self.moveSpot,insert=spot)
            else:
                w.setSelectionRange(self.moveSpot,spot,insert=spot)
        else:
            w.setSelectionRange(spot,spot,insert=spot)

        w.seeInsertPoint()
        c.frame.updateStatusLine()
    #@-node:ekr.20060113130510:extendHelper
    #@+node:ekr.20060113105246.1:moveUpOrDownHelper
    def moveUpOrDownHelper (self,event,direction,extend):

        c = self.c ; w = self.editWidget(event)
        if not w: return
        trace = False

        ins = w.getInsertPoint()
        s = w.getAllText()
        w.seeInsertPoint()

        # Find the start of the next/prev line.
        row,col = g.convertPythonIndexToRowCol(s,ins)
        if trace: g.trace('ins',ins,'row',row,'col',col)
        i,j = g.getLine(s,ins)
        if direction == 'down':
            i2,j2 = g.getLine(s,j)
        else:
            i2,j2 = g.getLine(s,i-1)

        # The spot is the start of the line plus the column index.
        n = max(0,j2-i2-1) # The length of the new line.
        col2 = min(col,n)
        spot = i2 + col2
        if trace: g.trace('spot',spot,'n',n,'col',col,'line',repr(s[i2:j2]))

        self.extendHelper(w,extend,spot,upOrDown=True)
    #@nonl
    #@-node:ekr.20060113105246.1:moveUpOrDownHelper
    #@+node:ekr.20051218122116:moveToHelper
    def moveToHelper (self,event,spot,extend,allowMinibuffer=False):

        '''Common helper method for commands the move the cursor
        in a way that can be described by a Tk Text expression.'''

        c = self.c ; k = c.k ; w = self.editWidget(event,allowMinibuffer=allowMinibuffer)
        if not w: return

        c.widgetWantsFocusNow(w)

        # Put the request in the proper range.
        if c.widget_name(w).startswith('mini'):
            i,j = k.getEditableTextRange()
            if   spot < i: spot = i
            elif spot > j: spot = j

        self.extendHelper(w,extend,spot,upOrDown=False)
    #@nonl
    #@-node:ekr.20051218122116:moveToHelper
    #@+node:ekr.20051218171457:movePastCloseHelper
    def movePastCloseHelper (self,event,extend):

        c = self.c ; w = self.editWidget(event)
        if not w: return

        c.widgetWantsFocusNow(w)
        s = w.getAllText()
        ins = w.getInsertPoint()
        # Scan backwards for i,j.
        i = ins
        while i >= 0 and s[i] != '\n':
            if s[i] == '(': break
            i -= 1
        else: return
        j = ins
        while j >= 0 and s[j] != '\n':
            if s[j] == '(': break
            j -= 1
        if i < j: return
        # Scan forward for i2,j2.
        i2 = ins
        while i2 < len(s) and s[i2] != '\n':
            if s[i2] == ')': break
            i2 += 1
        else: return
        j2 = ins
        while j2 < len(s) and s[j2] != '\n':
            if s[j2] == ')': break
            j2 += 1
        if i2 > j2: return

        self.moveToHelper(event,i2+1,extend)
    #@-node:ekr.20051218171457:movePastCloseHelper
    #@+node:ekr.20051218121447:moveWordHelper
    def moveWordHelper (self,event,extend,forward,end=False):

        '''Move the cursor to the next word.
        The cursor is placed at the start of the word unless end=True'''

        c = self.c
        w = self.editWidget(event)
        if not w: return

        c.widgetWantsFocusNow(w)
        s = w.getAllText() ; n = len(s)
        i = w.getInsertPoint()

        if forward:
            # Unlike backward-word moves, there are two options...
            if end:
                while 0 <= i < n and not g.isWordChar(s[i]):
                    i += 1
                while 0 <= i < n and g.isWordChar(s[i]):
                    i += 1
            else:
                while 0 <= i < n and g.isWordChar(s[i]):
                    i += 1
                while 0 <= i < n and not g.isWordChar(s[i]):
                    i += 1
        else:
            i -= 1
            while 0 <= i < n and not g.isWordChar(s[i]):
                i -= 1
            while 0 <= i < n and g.isWordChar(s[i]):
                i -= 1
            i += 1

        self.moveToHelper(event,i,extend)
    #@nonl
    #@-node:ekr.20051218121447:moveWordHelper
    #@+node:ekr.20051213094517:backSentenceHelper
    def backSentenceHelper (self,event,extend):

        c = self.c
        w = self.editWidget(event)
        if not w: return

        c.widgetWantsFocusNow(w)
        s = w.getAllText()
        i = w.getInsertPoint()

        while i >= 0:
            if s[i] == '.': break
            i -= 1
        else: return

        j = i-1
        while j >= 0:
            if s[j] == '.':
                j += 1 ; break
            j -= 1
        else: j = 0

        while j < i and s[j].isspace():
            j += 1

        if j < i:
            self.moveToHelper(event,j,extend)
    #@-node:ekr.20051213094517:backSentenceHelper
    #@+node:ekr.20050920084036.137:forwardSentenceHelper
    def forwardSentenceHelper (self,event,extend):

        c = self.c
        w = self.editWidget(event)
        if not w: return

        c.widgetWantsFocusNow(w)

        s = w.getAllText()
        ins = w.getInsertPoint()
        i = s.find('.',ins) + 1
        i = min(i,len(s))
        self.moveToHelper(event,i,extend)
    #@-node:ekr.20050920084036.137:forwardSentenceHelper
    #@+node:ekr.20051218133207.1:forwardParagraphHelper
    def forwardParagraphHelper (self,event,extend):

        w = self.editWidget(event)
        if not w: return
        s = w.getAllText()
        ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        line = s[i:j]

        if line.strip(): # Skip past the present paragraph.
            self.selectParagraphHelper(w,i)
            i,j = w.getSelectionRange()
            j += 1

        # Skip to the next non-blank line.
        i = j
        while j < len(s):
            i,j = g.getLine(s,j)
            line = s[i:j]
            if line.strip(): break

        w.setInsertPoint(ins) # Restore the original insert point.
        self.moveToHelper(event,i,extend)
    #@-node:ekr.20051218133207.1:forwardParagraphHelper
    #@+node:ekr.20051218133207:backwardParagraphHelper
    def backwardParagraphHelper (self,event,extend):

        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        i,j = w.getSelectionRange()
        # A hack for wx gui: set the insertion point to the end of the selection range.
        if g.app.unitTesting:
            w.setInsertPoint(j)
        i,j = g.getLine(s,j)
        line = s[i:j]

        if line.strip():
            # Find the start of the present paragraph.
            while i > 0:
                i,j = g.getLine(s,i-1)
                line = s[i:j]
                if not line.strip(): break

        # Find the end of the previous paragraph.
        while i > 0:
            i,j = g.getLine(s,i-1)
            line = s[i:j]
            if line.strip():
                i = j-1 ; break

        self.moveToHelper(event,i,extend)
    #@nonl
    #@-node:ekr.20051218133207:backwardParagraphHelper
    #@+node:ekr.20060209095101:setMoveCol
    def setMoveCol (self,w,spot):

        '''Set the column to which an up or down arrow will attempt to move.'''

        c = self.c ; p = c.currentPosition()
        s = w.getAllText()
        i = w.toPythonIndex(spot)
        junk,col = g.convertPythonIndexToRowCol(s,i)
        # g.trace('spot,i,col',spot,i,col)

        self.moveSpot = i
        self.moveCol = col
        self.moveSpotNode = p.v.t
    #@nonl
    #@-node:ekr.20060209095101:setMoveCol
    #@-node:ekr.20051218170358: helpers
    #@+node:ekr.20050920084036.148:buffers
    def beginningOfBuffer (self,event):
        '''Move the cursor to the start of the body text.'''
        self.moveToHelper(event,0,extend=False)

    def beginningOfBufferExtendSelection (self,event):
        '''Extend the text selection by moving the cursor to the start of the body text.'''
        self.moveToHelper(event,0,extend=True)

    def endOfBuffer (self,event):
        '''Move the cursor to the end of the body text.'''
        w = self.editWidget(event)
        s = w.getAllText()
        self.moveToHelper(event,len(s),extend=False)

    def endOfBufferExtendSelection (self,event):
        '''Extend the text selection by moving the cursor to the end of the body text.'''
        w = self.editWidget(event)
        s = w.getAllText()
        self.moveToHelper(event,len(s),extend=True)
    #@-node:ekr.20050920084036.148:buffers
    #@+node:ekr.20051213080533:characters
    def backCharacter (self,event):
        '''Move the cursor back one character, extending the selection if in extend mode.'''
        w = self.editWidget(event,allowMinibuffer=True)
        i = w.getInsertPoint()
        i = max(0,i-1)
        self.moveToHelper(event,i,extend=False,allowMinibuffer=True)

    def backCharacterExtendSelection (self,event):
        '''Extend the selection by moving the cursor back one character.'''
        w = self.editWidget(event,allowMinibuffer=True)
        i = w.getInsertPoint()
        i = max(0,i-1)
        self.moveToHelper(event,i,extend=True,allowMinibuffer=True)

    def forwardCharacter (self,event):
        '''Move the cursor forward one character, extending the selection if in extend mode.'''
        w = self.editWidget(event,allowMinibuffer=True)
        s = w.getAllText()
        i = w.getInsertPoint()
        i = min(i+1,len(s))
        self.moveToHelper(event,i,extend=False,allowMinibuffer=True)

    def forwardCharacterExtendSelection (self,event):
        '''Extend the selection by moving the cursor forward one character.'''
        w = self.editWidget(event,allowMinibuffer=True)
        s = w.getAllText()
        i = w.getInsertPoint()
        i = min(i+1,len(s))
        self.moveToHelper(event,i,extend=True,allowMinibuffer=True)
    #@-node:ekr.20051213080533:characters
    #@+node:ekr.20051218174113:clear/set/ToggleExtendMode
    def clearExtendMode (self,event):
        '''Turn off extend mode: cursor movement commands do not extend the selection.'''
        self.extendModeHelper(event,False)

    def setExtendMode (self,event):
        '''Turn on extend mode: cursor movement commands do extend the selection.'''
        self.extendModeHelper(event,True)

    def toggleExtendMode (self,event):
        '''Toggle extend mode, i.e., toggle whether cursor movement commands extend the selections.'''
        self.extendModeHelper(event,not self.extendMode)

    def extendModeHelper (self,event,val):

        c = self.c
        w = self.editWidget(event)
        if not w: return

        self.extendMode = val
        g.es('extend mode',g.choose(val,'on','off'),color='red')
        c.widgetWantsFocusNow(w)
    #@-node:ekr.20051218174113:clear/set/ToggleExtendMode
    #@+node:ekr.20050920084036.136:exchangePointMark
    def exchangePointMark (self,event):

        '''Exchange the point (insert point) with the mark (the other end of the selected text).'''

        c = self.c
        w = self.editWidget(event)
        if not w: return

        c.widgetWantsFocusNow(w)
        i,j = w.getSelectionRange(sort=False)
        if i == j: return

        ins = w.getInsertPoint()
        ins = g.choose(ins==i,j,i)
        w.setInsertPoint(ins)
        w.setSelectionRange(i,j,insert=None)
    #@-node:ekr.20050920084036.136:exchangePointMark
    #@+node:ekr.20061007082956:extend-to-line
    def extendToLine (self,event):

        '''Select the line at the cursor.'''

        c = self.c ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText() ; n = len(s)
        i = w.getInsertPoint()

        while 0 <= i < n and not s[i] == '\n':
            i -= 1
        i += 1 ; i1 = i
        while 0 <= i < n and not s[i] == '\n':
            i += 1

        w.setSelectionRange(i1,i)
    #@-node:ekr.20061007082956:extend-to-line
    #@+node:ekr.20061007214835.4:extend-to-sentence
    def extendToSentence (self,event):

        '''Select the line at the cursor.'''

        c = self.c
        w = self.editWidget(event)
        if not w: return

        s = w.getAllText() ; n = len(s)
        i = w.getInsertPoint()

        i2 = 1 + s.find('.',i)
        if i2 == -1: i2 = n
        i1 = 1 + s.rfind('.',0,i2-1)

        w.setSelectionRange(i1,i2)
    #@nonl
    #@-node:ekr.20061007214835.4:extend-to-sentence
    #@+node:ekr.20060116074839.2:extend-to-word
    def extendToWord (self,event):

        '''Select the word at the cursor.'''

        c = self.c
        w = self.editWidget(event)
        if not w: return

        s = w.getAllText() ; n = len(s)
        i = w.getInsertPoint()

        while 0 <= i < n and not g.isWordChar(s[i]):
            i -= 1
        while 0 <= i < n and g.isWordChar(s[i]):
            i -= 1
        i += 1

        # Move to the end of the word.
        i1 = i
        while 0 <= i < n and g.isWordChar(s[i]):
            i += 1

        w.setSelectionRange(i1,i)
    #@nonl
    #@-node:ekr.20060116074839.2:extend-to-word
    #@+node:ekr.20051218141237:lines
    def beginningOfLine (self,event):
        '''Move the cursor to the start of the line, extending the selection if in extend mode.'''
        w = self.editWidget(event,allowMinibuffer=True)
        i,junk = g.getLine(w.getAllText(),w.getInsertPoint())
        self.moveToHelper(event,i,extend=False,allowMinibuffer=True)

    def beginningOfLineExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the start of the line.'''
        w = self.editWidget(event,allowMinibuffer=True)
        i,junk = g.getLine(w.getAllText(),w.getInsertPoint())
        self.moveToHelper(event,i,extend=True,allowMinibuffer=True)

    def endOfLine (self,event): # passed
        '''Move the cursor to the end of the line, extending the selection if in extend mode.'''
        w = self.editWidget(event,allowMinibuffer=True)
        s = w.getAllText()
        junk,i = g.getLine(s,w.getInsertPoint())
        if g.match(s,i-1,'\n'): i -= 1
        self.moveToHelper(event,i,extend=False,allowMinibuffer=True)

    def endOfLineExtendSelection (self,event): # passed
        '''Extend the selection by moving the cursor to the end of the line.'''
        w = self.editWidget(event,allowMinibuffer=True)
        s = w.getAllText()
        junk,i = g.getLine(s,w.getInsertPoint())
        if g.match(s,i-1,'\n'): i -= 1
        self.moveToHelper(event,i,extend=True,allowMinibuffer=True)

    def nextLine (self,event):
        '''Move the cursor down, extending the selection if in extend mode.'''
        self.moveUpOrDownHelper(event,'down',extend=False)

    def nextLineExtendSelection (self,event):
        '''Extend the selection by moving the cursor down.'''
        self.moveUpOrDownHelper(event,'down',extend=True)

    def prevLine (self,event):
        '''Move the cursor up, extending the selection if in extend mode.'''
        self.moveUpOrDownHelper(event,'up',extend=False)

    def prevLineExtendSelection (self,event):
        '''Extend the selection by moving the cursor up.'''
        self.moveUpOrDownHelper(event,'up',extend=True)
    #@-node:ekr.20051218141237:lines
    #@+node:ekr.20050920084036.140:movePastClose
    def movePastClose (self,event):
        '''Move the cursor past the closing parenthesis.'''
        self.movePastCloseHelper(event,extend=False)

    def movePastCloseExtendSelection (self,event):
        '''Extend the selection by moving the cursor past the closing parenthesis.'''
        self.movePastCloseHelper(event,extend=True)
    #@-node:ekr.20050920084036.140:movePastClose
    #@+node:ekr.20050920084036.102:paragraphs
    def backwardParagraph (self,event):
        '''Move the cursor to the previous paragraph.'''
        self.backwardParagraphHelper (event,extend=False)

    def backwardParagraphExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the previous paragraph.'''
        self.backwardParagraphHelper (event,extend=True)

    def forwardParagraph (self,event):
        '''Move the cursor to the next paragraph.'''
        self.forwardParagraphHelper(event,extend=False)

    def forwardParagraphExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the next paragraph.'''
        self.forwardParagraphHelper(event,extend=True)
    #@-node:ekr.20050920084036.102:paragraphs
    #@+node:ekr.20050920084036.131:sentences
    def backSentence (self,event):
        '''Move the cursor to the previous sentence.'''
        self.backSentenceHelper(event,extend=False)

    def backSentenceExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the previous sentence.'''
        self.backSentenceHelper(event,extend=True)

    def forwardSentence (self,event):
        '''Move the cursor to the next sentence.'''
        self.forwardSentenceHelper(event,extend=False)

    def forwardSentenceExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the next sentence.'''
        self.forwardSentenceHelper(event,extend=True)
    #@-node:ekr.20050920084036.131:sentences
    #@+node:ekr.20050920084036.149:words
    def backwardWord (self,event):
        '''Move the cursor to the previous word.'''
        self.moveWordHelper(event,extend=False,forward=False)

    def backwardWordExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the next word.'''
        self.moveWordHelper(event,extend=True,forward=False)

    def forwardEndWord (self,event): # New in Leo 4.4.2
        '''Move the cursor to the next word.'''
        self.moveWordHelper(event,extend=False,forward=True,end=True)

    def forwardEndWordExtendSelection (self,event): # New in Leo 4.4.2
        '''Extend the selection by moving the cursor to the previous word.'''
        self.moveWordHelper(event,extend=True,forward=True,end=True)

    def forwardWord (self,event):
        '''Move the cursor to the next word.'''
        self.moveWordHelper(event,extend=False,forward=True)

    def forwardWordExtendSelection (self,event):
        '''Extend the selection by moving the cursor to the previous word.'''
        self.moveWordHelper(event,extend=True,forward=True)
    #@-node:ekr.20050920084036.149:words
    #@-node:ekr.20050929114218:move cursor... (leoEditCommands)
    #@+node:ekr.20050920084036.95:paragraph...
    #@+others
    #@+node:ekr.20050920084036.99:backwardKillParagraph
    def backwardKillParagraph (self,event):

        '''Kill the previous paragraph.'''

        k = self.k ; c = k.c ; w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='backward-kill-paragraph')
        try:
            self.backwardParagraphHelper(event,extend=True)
            i,j = w.getSelectionRange()
            if i > 0: i = min(i+1,j)
            c.killBufferCommands.kill(event,i,j,undoType=None)
            w.setSelectionRange(i,i,insert=i)
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.99:backwardKillParagraph
    #@+node:ekr.20050920084036.100:fillRegion
    def fillRegion (self,event):

        '''Fill all paragraphs in the selected text.'''

        # New in Leo 4.4.4: just use reformat-paragraph logic.

        c = self.c ; p = c.currentPosition() ; undoType = 'fill-region'
        w = self.editWidget(event)
        i,j = w.getSelectionRange()
        c.undoer.beforeChangeGroup(p,undoType)
        while 1:
            self.c.reformatParagraph(event,undoType='reformat-paragraph')
            ins = w.getInsertPoint()
            s = w.getAllText()
            if ins >= j or ins >= len(s):
                break
        c.undoer.afterChangeGroup(p,undoType)
    #@-node:ekr.20050920084036.100:fillRegion
    #@+node:ekr.20050920084036.104:fillRegionAsParagraph
    def fillRegionAsParagraph (self,event):

        '''Fill the selected text.'''

        k = self.k
        w = self.editWidget(event)
        if not w or not self._chckSel(event): return

        self.beginCommand(undoType='fill-region-as-paragraph')

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.104:fillRegionAsParagraph
    #@+node:ekr.20050920084036.103:fillParagraph
    def fillParagraph( self, event ):

        '''Fill the selected paragraph'''

        w = self.editWidget(event)
        if not w: return

        # Clear the selection range.
        i,j = w.getSelectionRange()
        w.setSelectionRange(i,i,insert=i)

        self.c.reformatParagraph(event)
    #@-node:ekr.20050920084036.103:fillParagraph
    #@+node:ekr.20050920084036.98:killParagraph
    def killParagraph (self,event):

        '''Kill the present paragraph.'''

        k = self.k ; c = k.c ; w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='kill-paragraph')
        try:
            self.extendToParagraph(event)
            i,j = w.getSelectionRange()
            c.killBufferCommands.kill(event,i,j,undoType=None)
            w.setSelectionRange(i,i,insert=i)
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.98:killParagraph
    #@+node:ekr.20050920084036.96:extend-to-paragraph & helper
    def extendToParagraph (self,event):

        '''Select the paragraph surrounding the cursor.'''

        w = self.editWidget(event)
        if not w: return
        s = w.getAllText() ; ins = w.getInsertPoint()
        i,j = g.getLine(s,ins)
        line = s[i:j]

        # Find the start of the paragraph.
        if line.strip(): # Search backward.
            while i > 0:
                i2,j2 = g.getLine(s,i-1)
                line = s[i2:j2]
                if line.strip(): i = i2
                else: break # Use the previous line.
        else: # Search forward.
            while j < len(s):
                i,j = g.getLine(s,j)
                line = s[i:j]
                if line.strip(): break
            else: return

        # Select from i to the end of the paragraph.
        self.selectParagraphHelper(w,i)
    #@+node:ekr.20050920084036.97:selectParagraphHelper
    def selectParagraphHelper (self,w,start):

        '''Select from start to the end of the paragraph.'''

        s = w.getAllText()
        i1,j = g.getLine(s,start)
        while j < len(s):
            i,j2 = g.getLine(s,j)
            line = s[i:j2]
            if line.strip(): j = j2
            else: break

        j = max(start,j-1)
        w.setSelectionRange(i1,j,insert=j)
    #@-node:ekr.20050920084036.97:selectParagraphHelper
    #@-node:ekr.20050920084036.96:extend-to-paragraph & helper
    #@-others
    #@-node:ekr.20050920084036.95:paragraph...
    #@+node:ekr.20050920084036.105:region...
    #@+others
    #@+node:ekr.20050920084036.108:tabIndentRegion (indent-rigidly)
    def tabIndentRegion (self,event):

        '''Insert a hard tab at the start of each line of the selected text.'''

        k = self.k
        w = self.editWidget(event)
        if not w or not self._chckSel(event): return

        self.beginCommand(undoType='indent-rigidly')

        s = w.getAllText()
        i1,j1 = w.getSelectionRange()
        i,junk = g.getLine(s,i1)
        junk,j = g.getLine(s,j1)

        lines = g.splitlines(s[i:j])
        n = len(lines)
        lines = g.joinLines(['\t' + line for line in lines])
        s = s[:i] + lines + s[j:]
        w.setAllText(s)

        # Retain original row/col selection.
        w.setSelectionRange(i1,j1+n,insert=j1+n)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.108:tabIndentRegion (indent-rigidly)
    #@+node:ekr.20050920084036.109:countRegion
    def countRegion (self,event):

        '''Print the number of lines and characters in the selected text.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        txt = w.getSelectedText()
        lines = 1 ; chars = 0
        for z in txt:
            if z == '\n': lines += 1
            else:         chars += 1

        k.setLabelGrey('Region has %s lines, %s character%s' % (
            lines,chars,g.choose(chars==1,'','s')))
    #@-node:ekr.20050920084036.109:countRegion
    #@+node:ekr.20060417183606:moveLinesDown
    def moveLinesDown (self,event):

        '''Move all lines containing any selected text down one line,
        moving to the next node if the lines are the last lines of the body.'''

        c = self.c ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        sel_1,sel_2 = w.getSelectionRange()
        i,junk = g.getLine(s,sel_1)
        i2,j   = g.getLine(s,sel_2)
        lines  = s[i:j]
        # Select from start of the first line to the *start* of the last line.
        # This prevents selection creep.
        n = i2-i 
        # g.trace('lines',repr(lines))

        self.beginCommand(undoType='move-lines-down')
        changed = False
        try:
            if j < len(s):
                next_i,next_j = g.getLine(s,j+1)
                next_line = s[next_i:next_j]
                n2 = next_j-next_i
                w.delete(i,next_j)
                w.insert(i,next_line+lines)
                w.setSelectionRange(i+n2,i+n2+n,insert=i+n2+n)
                changed = True
            elif g.app.gui.widget_name(w).startswith('body'):
                p = c.currentPosition()
                if not p.hasThreadNext(): return
                w.delete(i,j)
                c.setBodyString(p,w.getAllText())
                p = p.threadNext()
                c.beginUpdate()
                try:
                    c.selectPosition(p)
                finally:
                    c.endUpdate()
                s = w.getAllText()
                w.insert(0,lines)
                if not lines.endswith('\n'): w.insert(len(lines),'\n')
                s = w.getAllText()
                w.setSelectionRange(0,n,insert=n)
                changed = True
        finally:
            self.endCommand(changed=changed,setLabel=True)
    #@-node:ekr.20060417183606:moveLinesDown
    #@+node:ekr.20060417183606.1:moveLinesUp
    def moveLinesUp (self,event):

        '''Move all lines containing any selected text up one line,
        moving to the previous node as needed.'''

        c = self.c ; w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        sel_1,sel_2 = w.getSelectionRange()
        i,junk = g.getLine(s,sel_1)
        i2,j   = g.getLine(s,sel_2)
        lines  = s[i:j]
        # Select from start of the first line to the *start* of the last line.
        # This prevents selection creep.
        n = i2-i 
        # g.trace('lines',repr(lines))

        self.beginCommand(undoType='move-lines-up')
        changed = False
        try:
            if i > 0:
                prev_i,prev_j = g.getLine(s,i-1)
                prev_line = s[prev_i:prev_j]
                w.delete(prev_i,j)
                w.insert(prev_i,lines+prev_line)
                w.setSelectionRange(prev_i,prev_i+n,insert=prev_i+n)
                changed = True
            elif g.app.gui.widget_name(w).startswith('body'):
                p = c.currentPosition()
                if not p.hasThreadBack(): return
                w.delete(i,j)
                c.setBodyString(p,w.getAllText())
                p = p.threadBack()
                c.beginUpdate()
                try:
                    c.selectPosition(p)
                finally:
                    c.endUpdate()
                s = w.getAllText()
                if not s.endswith('\n'): w.insert('end','\n')
                w.insert('end',lines)
                s = w.getAllText()
                ins = len(s)-len(lines)+n
                w.setSelectionRange(len(s)-len(lines),ins,insert=ins)
                changed = True
        finally:
            self.endCommand(changed=changed,setLabel=True)
    #@-node:ekr.20060417183606.1:moveLinesUp
    #@+node:ekr.20050920084036.110:reverseRegion
    def reverseRegion (self,event):

        '''Reverse the order of lines in the selected text.'''

        k = self.k
        w = self.editWidget(event)
        if not w or not self._chckSel(event): return

        self.beginCommand(undoType='reverse-region')

        s = w.getAllText()
        i1,j1 = w.getSelectionRange()
        i,junk = g.getLine(s,i1)
        junk,j = g.getLine(s,j1)

        txt = s[i:j]
        aList = txt.split('\n')
        aList.reverse()
        txt = '\n'.join(aList) + '\n'

        w.setAllText(s[:i1] + txt + s[j1:])
        ins = i1 + len(txt) - 1
        w.setSelectionRange(ins,ins,insert=ins)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.110:reverseRegion
    #@+node:ekr.20050920084036.111:up/downCaseRegion & helper
    def downCaseRegion (self,event):
        '''Convert all characters in the selected text to lower case.'''
        self.caseHelper(event,'low','downcase-region')

    def upCaseRegion (self,event):
        '''Convert all characters in the selected text to UPPER CASE.'''
        self.caseHelper(event,'up','upcase-region')

    def caseHelper (self,event,way,undoType):

        w = self.editWidget(event)
        if not w or not w.hasSelection(): return

        self.beginCommand(undoType=undoType)

        s = w.getAllText()
        i,j = w.getSelectionRange()
        ins = w.getInsertPoint()
        sel = g.choose(way=='low',s[i:j].lower(),s[i:j].upper())
        s2 = s[:i] + sel + s[j:]
        # g.trace('sel',repr(sel),'s2',repr(s2))
        changed = s2 != s
        if changed:
            w.setAllText(s2)
            w.setSelectionRange(i,j,insert=ins)

        self.endCommand(changed=changed,setLabel=True)
    #@-node:ekr.20050920084036.111:up/downCaseRegion & helper
    #@-others
    #@-node:ekr.20050920084036.105:region...
    #@+node:ekr.20060309060654:scrolling...
    #@+node:ekr.20050920084036.116:scrollUp/Down/extendSelection
    def scrollDown (self,event):
        '''Scroll the presently selected pane down one page.'''
        self.scrollHelper(event,'down',extend=False)

    def scrollDownExtendSelection (self,event):
        '''Extend the text selection by scrolling the body text down one page.'''
        self.scrollHelper(event,'down',extend=True)

    def scrollUp (self,event):
        '''Scroll the presently selected pane up one page.'''
        self.scrollHelper(event,'up',extend=False)

    def scrollUpExtendSelection (self,event):
        '''Extend the text selection by scrolling the body text up one page.'''
        self.scrollHelper(event,'up',extend=True)
    #@+node:ekr.20060113082917:scrollHelper
    def scrollHelper (self,event,direction,extend):

        k = self.k ; c = k.c ; gui = g.app.gui
        w = gui.eventWidget(event)
        if not w: return #  This does **not** require a text widget.

        if gui.isTextWidget(w):
            c.widgetWantsFocusNow(w)
            # Remember the original insert point.  This may become the moveSpot.
            ins1 = w.getInsertPoint()
            s = w.getAllText()
            row,col = g.convertPythonIndexToRowCol(s,ins1)
            # Compute the spot.
            delta = self.measure(w)
            row1 = g.choose(direction=='down',row+delta,row-delta)
            row1 = max(0,row1)
            spot = g.convertRowColToPythonIndex(s,row1,col)
            # g.trace('spot',spot,'row1',row1)
            self.extendHelper(w,extend,spot)
            w.seeInsertPoint()
        elif gui.widget_name(w).startswith('canvas'):
            if direction=='down':
                self.scrollOutlineDownPage()
            else:
                self.scrollOutlineUpPage()
    #@-node:ekr.20060113082917:scrollHelper
    #@+node:ekr.20050920084036.147:measure
    def measure (self,w):

        s = w.getAllText()
        ins = w.getInsertPoint()
        start, junk = g.convertPythonIndexToRowCol(s,ins)
        start += 1 ; delta = 0

        ustart = start - 1
        while ustart >= 1 and w.indexIsVisible('%s.0' % ustart):
            delta += 1 ; ustart -= 1

        ustart = start + 1
        while w.indexIsVisible('%s.0' % ustart):
            delta += 1 ; ustart += 1

        return delta
    #@-node:ekr.20050920084036.147:measure
    #@-node:ekr.20050920084036.116:scrollUp/Down/extendSelection
    #@+node:ekr.20060309060654.1:scrollOutlineUp/Down/Line/Page
    def scrollOutlineDownLine (self,event=None):
        '''Scroll the outline pane down one line.'''
        a,b = self.c.frame.canvas.leo_treeBar.get()
        if b < 1.0:
            self.c.frame.tree.canvas.yview_scroll(1,"unit")

    def scrollOutlineDownPage (self,event=None):
        '''Scroll the outline pane down one page.'''
        a,b = self.c.frame.canvas.leo_treeBar.get()
        if b < 1.0:
            self.c.frame.tree.canvas.yview_scroll(1,"page")

    def scrollOutlineUpLine (self,event=None):
        '''Scroll the outline pane up one line.'''
        a,b = self.c.frame.canvas.leo_treeBar.get()
        if a > 0.0:
            self.c.frame.tree.canvas.yview_scroll(-1,"unit")

    def scrollOutlineUpPage (self,event=None):
        '''Scroll the outline pane up one page.'''
        a,b = self.c.frame.canvas.leo_treeBar.get()
        if a > 0.0:
            self.c.frame.tree.canvas.yview_scroll(-1,"page")
    #@-node:ekr.20060309060654.1:scrollOutlineUp/Down/Line/Page
    #@+node:ekr.20060726154531:scrollOutlineLeftRight
    def scrollOutlineLeft (self,event=None):
        '''Scroll the outline left.'''
        self.c.frame.tree.canvas.xview_scroll(1,"unit")

    def scrollOutlineRight (self,event=None):
        '''Scroll the outline left.'''
        self.c.frame.tree.canvas.xview_scroll(-1,"unit")
    #@-node:ekr.20060726154531:scrollOutlineLeftRight
    #@-node:ekr.20060309060654:scrolling...
    #@+node:ekr.20050920084036.117:sort...
    #@@nocolor
    #@@color
    #@+at
    # XEmacs provides several commands for sorting text in a buffer.  All
    # operate on the contents of the region (the text between point and the
    # mark).  They divide the text of the region into many "sort records",
    # identify a "sort key" for each record, and then reorder the records
    # using the order determined by the sort keys.  The records are ordered so
    # that their keys are in alphabetical order, or, for numerical sorting, in
    # numerical order.  In alphabetical sorting, all upper-case letters `A'
    # through `Z' come before lower-case `a', in accordance with the ASCII
    # character sequence.
    # 
    #    The sort commands differ in how they divide the text into sort
    # records and in which part of each record they use as the sort key.
    # Most of the commands make each line a separate sort record, but some
    # commands use paragraphs or pages as sort records.  Most of the sort
    # commands use each entire sort record as its own sort key, but some use
    # only a portion of the record as the sort key.
    # 
    # `M-x sort-lines'
    #      Divide the region into lines and sort by comparing the entire text
    #      of a line.  A prefix argument means sort in descending order.
    # 
    # `M-x sort-paragraphs'
    #      Divide the region into paragraphs and sort by comparing the entire
    #      text of a paragraph (except for leading blank lines).  A prefix
    #      argument means sort in descending order.
    # 
    # `M-x sort-pages'
    #      Divide the region into pages and sort by comparing the entire text
    #      of a page (except for leading blank lines).  A prefix argument
    #      means sort in descending order.
    # 
    # `M-x sort-fields'
    #      Divide the region into lines and sort by comparing the contents of
    #      one field in each line.  Fields are defined as separated by
    #      whitespace, so the first run of consecutive non-whitespace
    #      characters in a line constitutes field 1, the second such run
    #      constitutes field 2, etc.
    # 
    #      You specify which field to sort by with a numeric argument: 1 to
    #      sort by field 1, etc.  A negative argument means sort in descending
    #      order.  Thus, minus 2 means sort by field 2 in reverse-alphabetical
    #      order.
    # 
    # `M-x sort-numeric-fields'
    #      Like `M-x sort-fields', except the specified field is converted to
    #      a number for each line and the numbers are compared.  `10' comes
    #      before `2' when considered as text, but after it when considered
    #      as a number.
    # 
    # `M-x sort-columns'
    #      Like `M-x sort-fields', except that the text within each line used
    #      for comparison comes from a fixed range of columns.  An explanation
    #      is given below.
    # 
    #    For example, if the buffer contains:
    # 
    #      On systems where clash detection (locking of files being edited) is
    #      implemented, XEmacs also checks the first time you modify a buffer
    #      whether the file has changed on disk since it was last visited or
    #      saved.  If it has, you are asked to confirm that you want to change
    #      the buffer.
    # 
    # then if you apply `M-x sort-lines' to the entire buffer you get:
    # 
    #      On systems where clash detection (locking of files being edited) is
    #      implemented, XEmacs also checks the first time you modify a buffer
    #      saved.  If it has, you are asked to confirm that you want to change
    #      the buffer.
    #      whether the file has changed on disk since it was last visited or
    # 
    # where the upper case `O' comes before all lower case letters.  If you
    # apply instead `C-u 2 M-x sort-fields' you get:
    # 
    #      saved.  If it has, you are asked to confirm that you want to change
    #      implemented, XEmacs also checks the first time you modify a buffer
    #      the buffer.
    #      On systems where clash detection (locking of files being edited) is
    #      whether the file has changed on disk since it was last visited or
    # 
    # where the sort keys were `If', `XEmacs', `buffer', `systems', and `the'.
    # 
    #    `M-x sort-columns' requires more explanation.  You specify the
    # columns by putting point at one of the columns and the mark at the other
    # column.  Because this means you cannot put point or the mark at the
    # beginning of the first line to sort, this command uses an unusual
    # definition of `region': all of the line point is in is considered part
    # of the region, and so is all of the line the mark is in.
    # 
    #    For example, to sort a table by information found in columns 10 to
    # 15, you could put the mark on column 10 in the first line of the table,
    # and point on column 15 in the last line of the table, and then use this
    # command.  Or you could put the mark on column 15 in the first line and
    # point on column 10 in the last line.
    # 
    #    This can be thought of as sorting the rectangle specified by point
    # and the mark, except that the text on each line to the left or right of
    # the rectangle moves along with the text inside the rectangle.  *Note
    # Rectangles::.
    # 
    #@-at
    #@+node:ekr.20050920084036.118:sortLines commands
    def reverseSortLinesIgnoringCase(self,event):
        return self.sortLines(event,ignoreCase=True,reverse=True)

    def reverseSortLines(self,event):
        return self.sortLines(event,reverse=True)

    def sortLinesIgnoringCase(self,event):
        return self.sortLines(event,ignoreCase=True)

    def sortLines (self,event,ignoreCase=False,reverse=False):

        '''Sort lines of the selected text by comparing the entire text of a line.'''

        c = self.c ; k = c.k ; w = self.editWidget(event)
        if not self._chckSel(event): return

        undoType = g.choose(reverse,'reverse-sort-lines','sort-lines')
        self.beginCommand(undoType=undoType)
        try:
            s = w.getAllText()
            sel_1,sel_2 = w.getSelectionRange()
            ins = w.getInsertPoint()
            i,junk = g.getLine(s,sel_1)
            junk,j = g.getLine(s,sel_2)
            s2 = s[i:j]
            if not s2.endswith('\n'): s2 = s2+'\n'
            aList = g.splitLines(s2)
            if ignoreCase:  aList.sort(key=string.lower)
            else:           aList.sort()
            if reverse:     aList.reverse()
            s = g.joinLines(aList)
            w.delete(i,j)
            w.insert(i,s)
            w.setSelectionRange(sel_1,sel_2,insert=ins)
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.118:sortLines commands
    #@+node:ekr.20050920084036.119:sortColumns
    def sortColumns (self,event):

        '''Sort lines of selected text using only lines in the given columns to do the comparison.'''

        k = self.k
        w = self.editWidget(event)
        if not self._chckSel(event): return
        self.beginCommand(undoType='sort-columns')
        try:
            s = w.getAllText()
            ins = w.getInsertPoint()
            sel_1,sel_2 = w.getSelectionRange()
            sint1,sint2 = g.convertPythonIndexToRowCol(s,sel_1)
            sint3,sint4 = g.convertPythonIndexToRowCol(s,sel_2)
            sint1 += 1 ; sint3 += 1
            i,junk = g.getLine(s,sel_1)
            junk,j = g.getLine(s,sel_2)
            txt = s[i:j]
            columns = [w.get('%s.%s' % (z,sint2),'%s.%s' % (z,sint4))
                for z in xrange(sint1,sint3+1)]
            aList = g.splitLines(txt)
            zlist = zip(columns,aList)
            zlist.sort()
            s = g.joinLines([z[1] for z in zlist])
            w.delete(i,j)
            w.insert(i,s)
            w.setSelectionRange(sel_1,sel_1+len(s),insert=sel_1+len(s))
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.119:sortColumns
    #@+node:ekr.20050920084036.120:sortFields
    def sortFields (self,event,which=None):

        '''Divide the selected text into lines and sort by comparing the contents of
         one field in each line. Fields are defined as separated by whitespace, so
         the first run of consecutive non-whitespace characters in a line
         constitutes field 1, the second such run constitutes field 2, etc.

         You specify which field to sort by with a numeric argument: 1 to sort by
         field 1, etc. A negative argument means sort in descending order. Thus,
         minus 2 means sort by field 2 in reverse-alphabetical order.'''

        k = self.k
        w = self.editWidget(event)
        if not w or not self._chckSel(event): return

        self.beginCommand(undoType='sort-fields')

        s = w.getAllText()
        ins = w.getInsertPoint()
        r1,r2,r3,r4 = self.getRectanglePoints(w)
        i,junk = g.getLine(s,r1)
        junk,j = g.getLine(s,r4)
        txt = s[i:j] # bug reported by pychecker.
        txt = txt.split('\n')
        fields = []
        fn = r'\w+'
        frx = re.compile(fn)
        for line in txt:
            f = frx.findall(line)
            if not which:
                fields.append(f[0])
            else:
                i = int(which)
                if len(f) < i: return
                i = i-1
                fields.append(f[i])
        nz = zip(fields,txt)
        nz.sort()
        #w.delete('%s linestart' % is1,'%s lineend' % is2)
        w.delete(i,j)
        #i = is1.split('.')
        #int1 = int(i[0])
        int1 = i
        for z in nz:
            w.insert('%s.0' % int1,'%s\n' % z[1])
            int1 = int1 + 1
        w.setInsertPoint(ins)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.120:sortFields
    #@-node:ekr.20050920084036.117:sort...
    #@+node:ekr.20050920084036.121:swap/transpose...
    #@+node:ekr.20060529184652:swapHelper
    def swapHelper (self,w,find,ftext,lind,ltext):

        w.delete(find,'%s wordend' % find)
        w.insert(find,ltext)
        w.delete(lind,'%s wordend' % lind)
        w.insert(lind,ftext)
        self.swapSpots.pop()
        self.swapSpots.pop()
    #@-node:ekr.20060529184652:swapHelper
    #@+node:ekr.20050920084036.122:transposeLines
    def transposeLines (self,event):

        '''Transpose the line containing the cursor with the preceding line.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        ins = w.getInsertPoint()
        s = w.getAllText()
        if not s.strip(): return

        i,j = g.getLine(s,ins)
        line1 = s[i:j]

        self.beginCommand(undoType='transpose-lines')

        if i == 0: # Transpose the next line.
            i2,j2 = g.getLine(s,j+1)
            line2 = s[i2:j2]
            w.delete(0,j2)
            w.insert(0,line2+line1)
            w.setInsertPoint(j2-1)
        else: # Transpose the previous line.
            i2,j2 = g.getLine(s,i-1)
            line2 = s[i2:j2]
            w.delete(i2,j)
            w.insert(i2,line1+line2)
            w.setInsertPoint(j-1)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.122:transposeLines
    #@+node:ekr.20050920084036.123:swapWords
    def swapWords (self,event,swapspots):

        '''Transpose the word at the cursor with the preceding word.'''

        w = self.editWidget(event)
        if not w: return
        if g.app.gui.guiName() != 'tkinter':
            return g.es('swap-words command not ready yet',color='blue')

        s = w.getAllText()

        txt = w.get('insert wordstart','insert wordend') ###
        if not txt: return

        i = w.index('insert wordstart') ###

        self.beginCommand(undoType='swap-words')

        if len(swapspots):
            if i > swapspots[1]:
                self.swapHelper(w,i,txt,swapspots[1],swapspots[0])
            elif i < swapspots[1]:
                self.swapHelper(w,swapspots[1],swapspots[0],i,txt)
        else:
            swapspots.append(txt)
            swapspots.append(i)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.123:swapWords
    #@+node:ekr.20060529184652.1:transposeWords (doesn't work)
    def transposeWords (self,event):

        '''Transpose the word at the cursor with the preceding word.'''

        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='transpose-words')
        self.swapWords(event,self.swapSpots)
        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20060529184652.1:transposeWords (doesn't work)
    #@+node:ekr.20050920084036.124:swapCharacters & transeposeCharacters
    def swapCharacters (self,event):

        k = self.k
        w = self.editWidget(event)
        if not w: return

        self.beginCommand(undoType='swap-characters')

        s = w.getAllText()
        i = w.getInsertPoint()
        if 0 < i < len(s):
            w.setAllText(s[:i-1] + s[i] + s[i-1] + s[i+1:])
            w.setSelectionRange(i,i,insert=i)

        self.endCommand(changed=True,setLabel=True)

    transposeCharacters = swapCharacters
    #@-node:ekr.20050920084036.124:swapCharacters & transeposeCharacters
    #@-node:ekr.20050920084036.121:swap/transpose...
    #@+node:ekr.20050920084036.126:tabify & untabify
    def tabify (self,event):
        '''Convert 4 spaces to tabs in the selected text.'''
        self.tabifyHelper (event,which='tabify')

    def untabify (self,event):
        '''Convert tabs to 4 spaces in the selected text.'''
        self.tabifyHelper (event,which='untabify')

    def tabifyHelper (self,event,which):

        k = self.k ; w = self.editWidget(event)
        if not w or not w.hasSelection(): return

        self.beginCommand(undoType=which)

        i,end = w.getSelectionRange()
        txt = w.getSelectedText()
        if which == 'tabify':
            pattern = re.compile(' {4,4}') # Huh?
            ntxt = pattern.sub('\t',txt)
        else:
            pattern = re.compile('\t')
            ntxt = pattern.sub('    ',txt)
        w.delete(i,end)
        w.insert(i,ntxt)
        n = i + len(ntxt)
        w.setSelectionRange(n,n,insert=n)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.126:tabify & untabify
    #@+node:ekr.20061111223516:selectAllText (leoEditCommands)
    def selectAllText (self,event):

        c = self.c 
        w = self.editWidget(event,allowMinibuffer=True) or g.app.gui.eventWidget(event) or c.frame.body.bodyCtrl
        if w == c.frame.miniBufferWidget:
            c.k.selectAll()
        else:
            return w.selectAllText()
    #@-node:ekr.20061111223516:selectAllText (leoEditCommands)
    #@-others
#@-node:ekr.20050920084036.53:editCommandsClass
#@+node:ekr.20050920084036.161:editFileCommandsClass
class editFileCommandsClass (baseEditCommandsClass):

    '''A class to load files into buffers and save buffers to files.'''

    #@    @+others
    #@+node:ekr.20050920084036.162: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.
    #@-node:ekr.20050920084036.162: ctor
    #@+node:ekr.20050920084036.163: getPublicCommands (editFileCommandsClass)
    def getPublicCommands (self):

        return {
            'compare-leo-files':    self.compareLeoFiles,
            'delete-file':          self.deleteFile,
            'diff':                 self.diff, 
            'insert-file':          self.insertFile,
            'make-directory':       self.makeDirectory,
            'open-outline-by-name': self.openOutlineByName,
            'remove-directory':     self.removeDirectory,
            'save-file':            self.saveFile
        }
    #@-node:ekr.20050920084036.163: getPublicCommands (editFileCommandsClass)
    #@+node:ekr.20070920104110:compareLeoFiles
    def compareLeoFiles (self,event):

        c = c1 = self.c ; w = c.frame.body.bodyCtrl

        # Prompt for the file to be compared with the present outline.
        filetypes = [("Leo files", "*.leo"),("All files", "*"),]
        fileName = g.app.gui.runOpenFileDialog(
            title="Compare .leo Files",filetypes=filetypes,defaultextension='.leo')
        if not fileName: return

        # Read the file into the hidden commander.
        c2 = self.createHiddenCommander(fileName)
        if not c2: return

        # Compute the inserted, deleted and changed dicts.
        d1 = self.createFileDict(c1)
        d2 = self.createFileDict(c2)  
        inserted, deleted, changed = self.computeChangeDicts(d1,d2)
        self.dumpCompareNodes(fileName,c1.mFileName,inserted,deleted,changed)

        # Create clones of all inserted, deleted and changed dicts.
        self.createAllCompareClones(inserted,deleted,changed)
        c2.frame.destroySelf()
        g.app.gui.set_focus(c,w)


    #@+node:ekr.20070921072608:computeChangeDicts
    def computeChangeDicts (self,d1,d2):

        '''Compute inserted, deleted, changed dictionaries.'''

        inserted = {}
        for key in d2.keys():
            if not d1.get(key):
                inserted[key] = d2.get(key)

        deleted = {}
        for key in d1.keys():
            if not d2.get(key):
                deleted[key] = d1.get(key)

        changed = {}
        for key in d1.keys():
            if d2.get(key):
                p1 = d1.get(key)
                p2 = d2.get(key)
                if p1.headString() != p2.headString() or p1.bodyString() != p2.bodyString():
                    changed[key] = p1

        return inserted, deleted, changed
    #@-node:ekr.20070921072608:computeChangeDicts
    #@+node:ekr.20070921072910:createAllCompareClones & helper
    def createAllCompareClones(self,inserted,deleted,changed):

        c = self.c # Always use the visible commander
        c.beginUpdate()
        try:
            # Create parent node at the start of the outline.
            u = c.undoer ; undoType = 'Compare .leo Files'
            u.beforeChangeGroup(c.currentPosition(),undoType)
            undoData = u.beforeInsertNode(c.currentPosition())
            parent = c.currentPosition().insertAfter()
            c.setHeadString(parent,undoType)
            u.afterInsertNode(parent,undoType,undoData,dirtyVnodeList=[])
            for d,kind in (
                (deleted,'deleted'),(inserted,'inserted'),(changed,'changed')
            ):
                self.createCompareClones(d,kind,parent)
            c.selectPosition(parent)
            u.afterChangeGroup(parent,undoType,reportFlag=True) 
        finally:
            c.endUpdate(False)
        c.redraw_now()
    #@nonl
    #@+node:ekr.20070921074410:createCompareClones
    def createCompareClones (self,d,kind,parent):

        c = self.c # Always use the visible commander.

        if d.keys():
            parent = parent.insertAsLastChild()
            c.setHeadString(parent,kind)

            for key in d.keys():
                p = d.get(key)
                clone = p.clone()
                clone.moveToLastChildOf(parent)
    #@-node:ekr.20070921074410:createCompareClones
    #@-node:ekr.20070921072910:createAllCompareClones & helper
    #@+node:ekr.20070921070101:createHiddenCommander
    def createHiddenCommander(self,fileName):

        # Read the file into a hidden commander (Similar to g.openWithFileName).
        import leoGui
        import leoFrame
        import leoCommands

        nullGui = leoGui.nullGui('nullGui')
        frame = leoFrame.nullFrame('nullFrame',nullGui,useNullUndoer=True)
        c2 = leoCommands.Commands(frame,fileName)
        theFile,c2.isZipped = g.openLeoOrZipFile(fileName)
        if theFile:
            c2.fileCommands.open(theFile,fileName,readAtFileNodesFlag=True,silent=True)
            return c2
        else:
            return None
    #@nonl
    #@-node:ekr.20070921070101:createHiddenCommander
    #@+node:ekr.20070921070101.1:createFileDict
    def createFileDict (self,c):

        '''Create a dictionary of all relevant positions in commander c.'''

        d = {}
        for p in c.allNodes_iter():
            try:
                # fileIndices for pre-4.x versions of .leo files have a different format.
                i,j,k = p.v.t.fileIndex
                d[str(i),str(j),str(k)] = p.copy()
            except Exception:
                pass
        return d
    #@-node:ekr.20070921070101.1:createFileDict
    #@+node:ekr.20070921072608.1:dumpCompareNodes
    def dumpCompareNodes (self,fileName1,fileName2,inserted,deleted,changed):

        for d,kind in (
            (inserted,'inserted (only in %s)' % (fileName1)),
            (deleted, 'deleted  (only in %s)' % (fileName2)),
            (changed, 'changed'),
        ):
            print ; print kind
            for key in d.keys():
                p = d.get(key)
                print '%-32s %s' % (key,g.toEncodedString(p.headString(),'ascii'))
    #@-node:ekr.20070921072608.1:dumpCompareNodes
    #@-node:ekr.20070920104110:compareLeoFiles
    #@+node:ekr.20050920084036.164:deleteFile
    def deleteFile (self,event):

        '''Prompt for the name of a file and delete it.'''

        k = self.k ; state = k.getState('delete_file')

        if state == 0:
            prefix = 'Delete File: '
            k.setLabelBlue('%s%s%s' % (prefix,os.getcwd(),os.sep))
            k.getArg(event,'delete_file',1,self.deleteFile,prefix=prefix)
        else:
            k.keyboardQuit(event)
            k.clearState()
            try:
                os.remove(k.arg)
                k.setLabel('Deleted: %s' % k.arg)
            except Exception:
                k.setLabel('Not Deleted: %s' % k.arg)
    #@-node:ekr.20050920084036.164:deleteFile
    #@+node:ekr.20050920084036.165:diff (revise)
    def diff (self,event):

        '''Creates a node and puts the diff between 2 files into it.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        try:
            f, name = self.getReadableTextFile()
            txt1 = f.read() ; f.close()
            f2, name2 = self.getReadableTextFile()
            txt2 = f2.read() ; f2.close()
        except IOError: return

        ### self.switchToBuffer(event,"*diff* of ( %s , %s )" % (name,name2))
        data = difflib.ndiff(txt1,txt2)
        idata = []
        for z in data:
            idata.append(z)
        w.delete(0,'end')
        w.insert(0,''.join(idata))
    #@-node:ekr.20050920084036.165:diff (revise)
    #@+node:ekr.20050920084036.166:getReadableTextFile
    def getReadableTextFile (self):

        fileName = g.app.gui.runOpenFileDialog(
            title = 'Open Text File',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return None, None

        try:
            f = open(fileName,'rt')
            return f, fileName
        except IOError:
            g.es('can not open',fileName)
            return None,None
    #@-node:ekr.20050920084036.166:getReadableTextFile
    #@+node:ekr.20050920084036.167:insertFile
    def insertFile (self,event):

        '''Prompt for the name of a file and put the selected text into it.'''

        k = self.k ; c = k.c ; w = self.editWidget(event)
        if not w: return

        f, name = self.getReadableTextFile()
        if f:
            txt = f.read()
            f.close()
            w.insert('insert',txt)
            w.seeInsertPoint()
    #@-node:ekr.20050920084036.167:insertFile
    #@+node:ekr.20050920084036.168:makeDirectory
    def makeDirectory (self,event):

        '''Prompt for the name of a directory and create it.'''

        k = self.k ; state = k.getState('make_directory')

        if state == 0:
            prefix = 'Make Directory: '
            k.setLabelBlue('%s%s%s' % (prefix,os.getcwd(),os.sep))
            k.getArg(event,'make_directory',1,self.makeDirectory,prefix=prefix)
        else:
            k.keyboardQuit(event)
            k.clearState()
            try:
                os.mkdir(k.arg)
                k.setLabel("Created: %s" % k.arg)
            except Exception:
                k.setLabel("Not Create: %s" % k.arg)
    #@-node:ekr.20050920084036.168:makeDirectory
    #@+node:ekr.20060419123128:open-outline-by-name
    def openOutlineByName (self,event):

        '''Prompt for the name of a Leo outline and open it.'''

        c = self.c ; k = self.k ; fileName = ''.join(k.givenArgs)

        if fileName:
            g.openWithFileName(fileName,c)
        else:
            k.setLabelBlue('Open Leo Outline: ',protect=True)
            k.getFileName(event,handler=self.openOutlineByNameFinisher)

    def openOutlineByNameFinisher (self,event):

        c = self.c ; k = self.k ; fileName = k.arg

        k.resetLabel()
        if fileName and g.os_path_exists(fileName) and not g.os_path_isdir(fileName):
            g.openWithFileName(fileName,c)
    #@-node:ekr.20060419123128:open-outline-by-name
    #@+node:ekr.20050920084036.169:removeDirectory
    def removeDirectory (self,event):

        '''Prompt for the name of a directory and delete it.'''

        k = self.k ; state = k.getState('remove_directory')

        if state == 0:
            prefix = 'Remove Directory: '
            k.setLabelBlue('%s%s%s' % (prefix,os.getcwd(),os.sep))
            k.getArg(event,'remove_directory',1,self.removeDirectory,prefix=prefix)
        else:
            k.keyboardQuit(event)
            k.clearState()
            try:
                os.rmdir(k.arg)
                k.setLabel('Removed: %s' % k.arg)
            except Exception:
                k.setLabel('Not Remove: %s' % k.arg)
    #@-node:ekr.20050920084036.169:removeDirectory
    #@+node:ekr.20050920084036.170:saveFile
    def saveFile (self,event):

        '''Prompt for the name of a file and put the body text of the selected node into it..'''

        w = self.editWidget(event)
        if not w: return

        fileName = g.app.gui.runSaveFileDialog(
            initialfile = None,
            title='save-file',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return

        try:
            s = w.getAllText()
            f = open(fileName,'w')
            f.write(s)
            f.close()
        except IOError:
            g.es('can not create',fileName)
    #@-node:ekr.20050920084036.170:saveFile
    #@-others
#@-node:ekr.20050920084036.161:editFileCommandsClass
#@+node:ekr.20060205164707:helpCommandsClass
class helpCommandsClass (baseEditCommandsClass):

    '''A class to load files into buffers and save buffers to files.'''

    #@    @+others
    #@+node:ekr.20060205165501:getPublicCommands (helpCommands)
    def getPublicCommands (self):

        return {
            'help-for-minibuffer':      self.helpForMinibuffer,
            'help-for-command':         self.helpForCommand,
            'apropos-autocompletion':   self.aproposAutocompletion,
            'apropos-bindings':         self.aproposBindings,
            'apropos-debugging-commands': self.aproposDebuggingCommands,
            'apropos-find-commands':    self.aproposFindCommands,
            'print-settings':           self.printSettings,
            'python-help':              self.pythonHelp,
        }
    #@-node:ekr.20060205165501:getPublicCommands (helpCommands)
    #@+node:ekr.20051014170754:helpForMinibuffer
    def helpForMinibuffer (self,event=None):

        '''Print a messages telling you how to get started with Leo.'''

        # A bug in Leo: triple quotes puts indentation before each line.
        c = self.c
        s = '''
    The mini-buffer is intended to be like the Emacs buffer:

    full-command: (default shortcut: Alt-x) Puts the focus in the minibuffer. Type a
    full command name, then hit <Return> to execute the command. Tab completion
    works, but not yet for file names.

    quick-command-mode (default shortcut: Alt-x). Like Emacs Control-C. This mode is
    defined in leoSettings.leo. It is useful for commonly-used commands.

    universal-argument (default shortcut: Alt-u). Like Emacs Ctrl-u. Adds a repeat
    count for later command. Ctrl-u 999 a adds 999 a's. Many features remain
    unfinished.

    keyboard-quit (default shortcut: Ctrl-g) Exits any minibuffer mode and puts
    the focus in the body pane.

    Use the help-for-command command to see documentation for a particular command.
    '''

        s = g.adjustTripleString(s,c.tab_width)
            # Remove indentation from indentation of this function.
        # s = s % (shortcuts[0],shortcuts[1],shortcuts[2],shortcuts[3])

        if not g.app.unitTesting:
            g.es_print('',s)
    #@-node:ekr.20051014170754:helpForMinibuffer
    #@+node:ekr.20060417203717:helpForCommand
    def helpForCommand (self,event):

        '''Prompts for a command name and prints the help message for that command.'''

        k = self.k
        k.fullCommand(event,help=True,helpHandler=self.helpForCommandFinisher)

    def helpForCommandFinisher (self,commandName):

        c = self.c
        bindings = self.getBindingsForCommand(commandName)
        func = c.commandsDict.get(commandName)
        if func and func.__doc__:
            s = ''.join([
                g.choose(line.strip(),line.lstrip(),'\n')
                    for line in g.splitLines(func.__doc__)])
        else:
            s = 'no docstring'
        g.es('','%s:%s\n%s\n' % (commandName,bindings,s),color='blue')

    def getBindingsForCommand(self,commandName):

        c = self.c ; k = c.k ; d = k.bindingsDict
        keys = d.keys() ; keys.sort()

        data = [] ; n1 = 4 ; n2 = 20
        for key in keys:
            bunchList = d.get(key,[])
            for b in bunchList:
                if b.commandName == commandName:
                    pane = g.choose(b.pane=='all','',' %s:' % (b.pane))
                    s1 = pane
                    s2 = k.prettyPrintKey(key,brief=True)
                    s3 = b.commandName
                    n1 = max(n1,len(s1))
                    n2 = max(n2,len(s2))
                    data.append((s1,s2,s3),)

        data.sort(lambda x,y: cmp(x[1],y[1]))

        return ','.join(['%s %s' % (s1,s2) for s1,s2,s3 in data])
    #@nonl
    #@-node:ekr.20060417203717:helpForCommand
    #@+node:ekr.20060226131603.1:aproposAutocompletion
    def aproposAutocompletion (self,event=None):

        '''Prints a discussion of autocompletion.'''

        c = self.c ; s = '''
    This documentation describes both autocompletion and calltips.

    Typing a period when @language python is in effect starts autocompletion. Typing
    '(' during autocompletion shows the calltip. Typing Return or Control-g
    (keyboard-quit) exits autocompletion or calltips.

    Autocompletion

    Autocompletion shows what may follow a period in code. For example, after typing
    g. Leo will show a list of all the global functions in leoGlobals.py.
    Autocompletion works much like tab completion in the minibuffer. Unlike the
    minibuffer, the presently selected completion appears directly in the body
    pane.

    A leading period brings up 'Autocomplete Modules'. (The period goes away.) You
    can also get any module by typing its name. If more than 25 items would appear
    in the Autocompleter tab, Leo shows only the valid starting characters. At this
    point, typing an exclamation mark shows the complete list. Thereafter, typing
    further exclamation marks toggles between full and abbreviated modes.

    If x is a list 'x.!' shows all its elements, and if x is a Python dictionary,
    'x.!' shows x.keys(). For example, 'sys.modules.!' Again, further exclamation
    marks toggles between full and abbreviated modes.

    During autocompletion, typing a question mark shows the docstring for the
    object. For example: 'g.app?' shows the docstring for g.app. This doesn't work
    (yet) directly for Python globals, but '__builtin__.f?' does. Example:
    '__builtin__.pow?' shows the docstring for pow.

    Autocompletion works in the Find tab; you can use <Tab> to cycle through the
    choices. The 'Completion' tab appears while you are doing this; the Find tab
    reappears once the completion is finished.

    Calltips

    Calltips appear after you type an open parenthesis in code. Calltips shows the
    expected arguments to a function or method. Calltips work for any Python
    function or method, including Python's global function. Examples:

    a)  'g.toUnicode('  gives 'g.toUnicode(s, encoding, reportErrors=False'
    b) 'c.widgetWantsFocusNow' gives 'c.widgetWantsFocusNow(w'
    c) 'reduce(' gives 'reduce(function, sequence[, initial]) -> value'

    The calltips appear directly in the text and the argument list is highlighted so
    you can just type to replace it. The calltips appear also in the status line for
    reference after you have started to replace the args.

    Options

    Both autocompletion and calltips are initially enabled or disabled by the
    enable_autocompleter_initially and enable_calltips_initially settings in
    leoSettings.leo. You may enable or disable these features at any time with these
    commands: enable-autocompleter, enable-calltips, disable-autocompleter and
    disable-calltips.
    '''

        if not g.app.unitTesting:
            # Remove indentation from indentation of this function.
            s = g.adjustTripleString(s,c.tab_width)
            g.es_print('',s)
    #@+node:ekr.20060226132000:test_aproposAutocompletion
    if g.unitTesting:

        c,p = g.getTestVars() # Optional: prevents pychecker warnings.
        c.helpCommands.aproposAutocompletion()
    #@-node:ekr.20060226132000:test_aproposAutocompletion
    #@-node:ekr.20060226131603.1:aproposAutocompletion
    #@+node:ekr.20060205170335:aproposBindings
    def aproposBindings (self,event=None):

        '''Prints a discussion of keyboard bindings.'''

        c = self.c
        s = '''
    A shortcut specification has the form:

    command-name = shortcutSpecifier

    or

    command-name ! pane = shortcutSpecifier

    The first form creates a binding for all panes except the minibuffer. The second
    form creates a binding for one or more panes. The possible values for 'pane'
    are:

    pane    bound panes
    ----    -----------
    all     body,log,tree
    body    body
    log     log
    mini    minibuffer
    text    body,log
    tree    tree

    You may use None as the specifier. Otherwise, a shortcut specifier consists of a
    head followed by a tail. The head may be empty, or may be a concatenation of the
    following: (All entries in each row are equivalent).

    Shift+ Shift-
    Alt+ or Alt-
    Control+, Control-, Ctrl+ or Ctrl-

    Notes:

    1. The case of plain letters is significant:  a is not A.

    2. The Shift- (or Shift+) prefix can be applied *only* to letters or
    multi-letter tails. Leo will ignore (with a warning) the shift prefix applied to
    other single letters, e.g., Ctrl-Shift-(

    3. The case of letters prefixed by Ctrl-, Alt-, Key- or Shift- is *not*
    significant.

    The following table illustrates these rules.  In each row, the first entry is the key (for k.bindingsDict) and the other entries are equivalents that the user may specify in leoSettings.leo:

    a, Key-a, Key-A
    A, Shift-A
    Alt-a, Alt-A
    Alt-A, Alt-Shift-a, Alt-Shift-A
    Ctrl-a, Ctrl-A
    Ctrl-A, Ctrl-Shift-a, Ctrl-Shift-A
    !, Key-!,Key-exclam,exclam
    '''

        s = g.adjustTripleString(s,c.tab_width)
            # Remove indentation from indentation of this function.

        if not g.app.unitTesting:
            g.es_print('',s)
    #@-node:ekr.20060205170335:aproposBindings
    #@+node:ekr.20070501092655:aproposDebuggingCommands
    def aproposDebuggingCommands (self,event=None):

        '''Prints a discussion of of Leo's debugging commands.'''

        c = self.c

        #@    << define s >>
        #@+node:ekr.20070501092655.1:<< define s >>
        s = '''
        The following commands are useful for debugging:

        collect-garbage:   Invoke the garbage collector.
        debug:             Start an external debugger in another process.
        disable-gc-trace:  Disable tracing of the garbage collector.
        dump-all-objects:  Print a summary of all existing Python objects.
        dump-new-objects:  Print a summary of all newly-created Python objects.
        enable-gc-trace:   Enable tracing of the garbage collector.
        free-tree-widgets: Free all widgets used in Leo's outline pane.
        print-focus:       Print information about the requested focus.
        print-stats:       Print statistics about existing Python objects.
        print-gc-summary:  Print a brief summary of all Python objects.
        run-unit-tests:    Run unit tests in the presently selected tree.
        verbose-dump-objects: Print a more verbose listing of all existing Python objects.

        Leo also has many debugging settings that enable and disable traces.
        For details, see the node: @settings-->Debugging in leoSettings.leo.
        '''
        #@-node:ekr.20070501092655.1:<< define s >>
        #@nl

        # Remove indentation from s: a workaround of a Leo bug.
        s = g.adjustTripleString(s,c.tab_width)

        if not g.app.unitTesting:
            g.es_print('',s)
    #@-node:ekr.20070501092655:aproposDebuggingCommands
    #@+node:ekr.20060205170335.1:aproposFindCommands
    def aproposFindCommands (self, event=None):

        '''Prints a discussion of of Leo's find commands.'''

        c = self.c

        #@    << define s >>
        #@+node:ekr.20060209082023.1:<< define s >>
        s = '''
        Important: all minibuffer search commands, with the exception of the isearch (incremental) commands, simply provide a minibuffer interface to Leo's legacy find commands.  This means that all the powerful features of Leo's legacy commands are available to the minibuffer search commands.

        Note: all bindings shown are the default bindings for these commands.  You may change any of these bindings using @shortcut nodes in leoSettings.leo.

        Settings

        leoSettings.leo now contains several settings related to the Find tab:

        - @bool show_only_find_tab_options = True

        When True (recommended), the Find tab does not show the 'Find', 'Change', 'Change, Then Find', 'Find All' and 'Change All' buttons.

        - @bool minibufferSearchesShowFindTab = True

        When True, Leo shows the Find tab when executing most of the commands discussed below.  It's not necessary for it to be visible, but I think it provides good feedback about what search-with-present-options does.  YMMY.  When True, the sequence Control-F, Control-G is one way to show the Find Tab.

        Basic find commands

        - The open-find-tab command makes the Find tab visible.  The Find tab does **not** need to be visible to execute any search command discussed below.

        - The hide-find-tab commands hides the Find tab, but retains all the present settings.

        - The search-with-present-options command (Control-F) prompts for a search string.  Typing the <Return> key puts the search string in the Find tab and executes a search based on all the settings in the Find tab. This is a recommended default (Control-F) search command.

        - The show-search-options command shows the present search options in the status line.  At present, this command also makes the Find tab visible.

        Search again commands

        - The find-next command (F3) is the same as the search-with-present-options command, except that it uses the search string in the find-tab.  Recommended as the default 'search again' command.

        - Similarly, the find-previous command (F2) repeats the command specified by the Find tab,
          but in reverse.

        - The find-again is the same as the find-next command if a search pattern is not '<find pattern here>'.
          Otherwise, the find-again is the same as the search-with-present-options command.

        Setting find options

        - Several minibuffer commands toggle the checkboxes and radio buttons in the Find tab, and thus affect the operation of the search-with-present-options command. Some may want to bind these commands to keys. Others, will prefer to toggle options in a mode.

        Here are the commands that toggle checkboxes: toggle-find-ignore-case-option, toggle-find-in-body-option, toggle-find-in-headline-option, toggle-find-mark-changes-option, toggle-find-mark-finds-option, toggle-find-regex-option, toggle-find-reverse-option, toggle-find-word-option, and toggle-find-wrap-around-option.

        Here are the commands that set radio buttons: set-find-everywhere, set-find-node-only, and set-find-suboutline-only.

        - The enter-find-options-mode (Ctrl-Shift-F) enters a mode in which you may change all checkboxes and radio buttons in the Find tab with plain keys.  As always, you can use the mode-help (Tab) command to see a list of key bindings in effect for the mode.

        Search commands that set options as a side effect

        The following commands set an option in the Find tab, then work exactly like the search-with-present-options command.

        - The search-backward and search-forward commands set the 'Whole Word' checkbox to False.

        - The word-search-backward and word-search-forward set the 'Whole Word' checkbox to True.

        - The re-search-forward and re-search-backward set the 'Regexp' checkbox to True.

        Find all commands

        - The find-all command prints all matches in the log pane.

        - The clone-find-all command replaces the previous 'Clone Find' checkbox.  It prints all matches in the log pane, and creates a node at the beginning of the outline containing clones of all nodes containing the 'find' string.  Only one clone is made of each node, regardless of how many clones the node has, or of how many matches are found in each node.

        Note: the radio buttons in the Find tab (Entire Outline, Suboutline Only and Node only) control how much of the outline is affected by the find-all and clone-find-all commands.

        Search and replace commands

        The replace-string prompts for a search string.  Type <Return> to end the search string.  The command will then prompt for the replacement string.  Typing a second <Return> key will place both strings in the Find tab and executes a **find** command, that is, the search-with-present-options command.

        So the only difference between the replace-string and search-with-present-options commands is that the replace-string command has the side effect of setting 'change' string in the Find tab.  However, this is an extremely useful side effect, because of the following commands...

        - The change command (Ctrl-=) replaces the selected text with the 'change' text in the Find tab.

        - The change-then-find (Ctrl--) replaces the selected text with the 'change' text in the Find tab, then executes the find command again.

        The find-next, change and change-then-find commands can simulate any kind of query-replace command.  **Important**: Leo presently has separate query-replace and query-replace-regex commands, but they are buggy and 'under-powered'.  Fixing these commands has low priority.

        - The change-all command changes all occurrences of the 'find' text with the 'change' text.  Important: the radio buttons in the Find tab (Entire Outline, Suboutline Only and Node only) control how much of the outline is affected by this command.

        Incremental search commands

        Leo's incremental search commands are completely separate from Leo's legacy search commands.  At present, incremental search commands do not cross node boundaries: they work only in the body text of single node.

        Coming in Leo 4.4b3: the incremental commands will maintain a list of previous matches.  This allows for

        a) support for backspace and
        b) an incremental-search-again command.

        Furthermore, this list makes it easy to detect the end of a wrapped incremental search.

        Here is the list of incremental find commands: isearch-backward, isearch-backward-regexp, isearch-forward and
        isearch-forward-regexp.'''
        #@-node:ekr.20060209082023.1:<< define s >>
        #@nl

        # Remove indentation from s: a workaround of a Leo bug.
        s = g.adjustTripleString(s,c.tab_width)

        if not g.app.unitTesting:
            g.es_print('',s)
    #@-node:ekr.20060205170335.1:aproposFindCommands
    #@+node:ekr.20060602154458:pythonHelp
    def pythonHelp (self,event=None):

        '''Prompt for a arg for Python's help function, and put it to the log pane.'''

        c = self.c ; k = c.k ; tag = 'python-help' ; state = k.getState(tag)

        if state == 0:
            c.frame.minibufferWantsFocus()
            k.setLabelBlue('Python help: ',protect=True)
            k.getArg(event,tag,1,self.pythonHelp)
        else:
            k.clearState()
            k.resetLabel()
            s = k.arg.strip()
            if s:
                g.redirectStderr()
                g.redirectStdout()
                try: help(str(s))
                except Exception: pass
                g.restoreStderr()
                g.restoreStdout()
    #@-node:ekr.20060602154458:pythonHelp
    #@+node:ekr.20070418074444:printSettings
    def printSettings (self,event=None):

        g.app.config.printSettings(self.c)
    #@-node:ekr.20070418074444:printSettings
    #@-others
#@-node:ekr.20060205164707:helpCommandsClass
#@+node:ekr.20050920084036.171:keyHandlerCommandsClass (add docstrings)
class keyHandlerCommandsClass (baseEditCommandsClass):

    '''User commands to access the keyHandler class.'''

    #@    @+others
    #@+node:ekr.20050920084036.172: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.
    #@-node:ekr.20050920084036.172: ctor
    #@+node:ekr.20050920084036.173:getPublicCommands (keyHandler)
    def getPublicCommands (self):

        k = self.k

        if k:
            return {
                'auto-complete':            k.autoCompleter.autoComplete,
                'auto-complete-force':      k.autoCompleter.autoCompleteForce,
                'digit-argument':           k.digitArgument,
                'disable-autocompleter':    k.autoCompleter.disableAutocompleter,
                'disable-calltips':         k.autoCompleter.disableCalltips,
                'enable-autocompleter':     k.autoCompleter.enableAutocompleter,
                'enable-calltips':          k.autoCompleter.enableCalltips,
                'exit-named-mode':          k.exitNamedMode,
                'full-command':             k.fullCommand, # For menu.
                'hide-mini-buffer':         k.hideMinibuffer,
                'mode-help':                k.modeHelp,
                'negative-argument':        k.negativeArgument,
                'number-command':           k.numberCommand,
                'number-command-0':         k.numberCommand0,
                'number-command-1':         k.numberCommand1,
                'number-command-2':         k.numberCommand2,
                'number-command-3':         k.numberCommand3,
                'number-command-4':         k.numberCommand4,
                'number-command-5':         k.numberCommand5,
                'number-command-6':         k.numberCommand6,
                'number-command-7':         k.numberCommand7,
                'number-command-8':         k.numberCommand8,
                'number-command-9':         k.numberCommand9,
                'print-bindings':           k.printBindings,
                'print-commands':           k.printCommands,
                'propagate-key-event':      k.propagateKeyEvent,
                'repeat-complex-command':   k.repeatComplexCommand,
                # 'scan-for-autocompleter':   k.autoCompleter.scan,
                'set-command-state':        k.setCommandState,
                'set-insert-state':         k.setInsertState,
                'set-overwrite-state':      k.setOverwriteState,
                'show-calltips':            k.autoCompleter.showCalltips,
                'show-calltips-force':      k.autoCompleter.showCalltipsForce,
                'show-mini-buffer':         k.showMinibuffer,
                'toggle-autocompleter':     k.autoCompleter.toggleAutocompleter,
                'toggle-calltips':          k.autoCompleter.toggleCalltips,
                'toggle-mini-buffer':       k.toggleMinibuffer,
                'toggle-input-state':       k.toggleInputState,
                'universal-argument':       k.universalArgument,
            }
        else:
            return {}
    #@-node:ekr.20050920084036.173:getPublicCommands (keyHandler)
    #@-others
#@-node:ekr.20050920084036.171:keyHandlerCommandsClass (add docstrings)
#@+node:ekr.20050920084036.174:killBufferCommandsClass
class killBufferCommandsClass (baseEditCommandsClass):

    '''A class to manage the kill buffer.'''

    #@    @+others
    #@+node:ekr.20050920084036.175: ctor & finishCreate
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.addWsToKillRing = c.config.getBool('add-ws-to-kill-ring')
        self.killBuffer = [] # May be changed in finishCreate.
        self.kbiterator = self.iterateKillBuffer()
        self.last_clipboard = None # For interacting with system clipboard.
        self.lastYankP = None # The position of the last item returned by iterateKillBuffer.
        self.reset = None
            # None, or the index of the next item to be returned in killBuffer by iterateKillBuffer.

    def finishCreate (self):

        baseEditCommandsClass.finishCreate(self)
            # Call the base finishCreate.
            # This sets self.k

        if self.k and self.k.useGlobalKillbuffer:
            self.killBuffer = leoKeys.keyHandlerClass.global_killbuffer
    #@-node:ekr.20050920084036.175: ctor & finishCreate
    #@+node:ekr.20050920084036.176: getPublicCommands
    def getPublicCommands (self):

        return {
            'backward-kill-sentence':   self.backwardKillSentence,
            'backward-kill-word':       self.backwardKillWord,
            'clear-kill-ring':          self.clearKillRing,
            'kill-line':                self.killLine,
            'kill-word':                self.killWord,
            'kill-sentence':            self.killSentence,
            'kill-region':              self.killRegion,
            'kill-region-save':         self.killRegionSave,
            'kill-ws':                  self.killWs,
            'yank':                     self.yank,
            'yank-pop':                 self.yankPop,
            'zap-to-character':         self.zapToCharacter,
        }
    #@-node:ekr.20050920084036.176: getPublicCommands
    #@+node:ekr.20050920084036.183:addToKillBuffer
    def addToKillBuffer (self,text):

        '''Insert the text into the kill buffer if force is True or
        the text contains something other than whitespace.'''

        if self.addWsToKillRing or text.strip():
            self.killBuffer = [z for z in self.killBuffer if z != text]
            self.killBuffer.insert(0,text)
    #@-node:ekr.20050920084036.183:addToKillBuffer
    #@+node:ekr.20050920084036.181:backwardKillSentence
    def backwardKillSentence (self,event):

        '''Kill the previous sentence.'''

        w = self.editWidget(event)
        if not w: return

        s = w.getAllText()
        ins = w.getInsertPoint()
        i = s.rfind('.',ins)
        if i == -1: return

        undoType='backward-kill-sentence'

        self.beginCommand(undoType=undoType)

        i2 = s.rfind('.',0,i) + 1
        self.kill(event,i2,i+1,undoType=undoType)
        self.c.frame.body.forceFullRecolor()
        w.setInsertPoint(i2)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.181:backwardKillSentence
    #@+node:ekr.20050920084036.180:backwardKillWord & killWord
    def backwardKillWord (self,event):
        '''Kill the previous word.'''
        c = self.c
        self.beginCommand(undoType='backward-kill-word')
        c.editCommands.backwardWord(event)
        self.killWs(event)
        self.kill(event,'insert wordstart','insert wordend',undoType=None)
        c.frame.body.forceFullRecolor()
        self.endCommand(changed=True,setLabel=True)

    def killWord (self,event):
        '''Kill the word containing the cursor.'''
        c = self.c
        self.beginCommand(undoType='kill-word')
        self.kill(event,'insert wordstart','insert wordend',undoType=None)
        self.killWs(event)
        c.frame.body.forceFullRecolor()
        self.endCommand(changed=True,setLabel=True)

    #@-node:ekr.20050920084036.180:backwardKillWord & killWord
    #@+node:ekr.20051216151811:clearKillRing
    def clearKillRing (self,event=None):

        '''Clear the kill ring.'''

        self.killBuffer = []
    #@-node:ekr.20051216151811:clearKillRing
    #@+node:ekr.20050920084036.185:getClipboard
    def getClipboard (self):

        '''Return the contents of the clipboard.'''

        try:
            ctxt = g.app.gui.getTextFromClipboard()
            if not self.killBuffer or ctxt != self.last_clipboard:
                self.last_clipboard = ctxt
                if not self.killBuffer or self.killBuffer [0] != ctxt:
                    return ctxt
        except Exception:
            g.es_exception()

        return None
    #@-node:ekr.20050920084036.185:getClipboard
    #@+node:ekr.20050920084036.184:iterateKillBuffer
    class killBuffer_iter_class:

        """Returns a list of positions in a subtree, possibly including the root of the subtree."""

        #@    @+others
        #@+node:ekr.20071003160252.1:__init__ & __iter__
        def __init__(self,c):

            # g.trace('iterateKillBuffer.__init')
            self.c = c
            self.index = 0 # The index of the next item to be returned.

        def __iter__(self):

            return self
        #@-node:ekr.20071003160252.1:__init__ & __iter__
        #@+node:ekr.20071003160252.2:next
        def next(self):

            commands = self.c.killBufferCommands
            aList = commands.killBuffer

            # g.trace(g.listToString([repr(z) for z in aList]))

            if not aList:
                self.index = 0
                return None

            if commands.reset is None:
                i = self.index
            else:
                i = commands.reset
                commands.reset = None

            if i < 0 or i >= len(aList): i = 0
            # g.trace(i)
            val = aList[i]
            self.index = i + 1
            return val
        #@-node:ekr.20071003160252.2:next
        #@-others

    def iterateKillBuffer (self):

        return self.killBuffer_iter_class(self.c)
    #@-node:ekr.20050920084036.184:iterateKillBuffer
    #@+node:ekr.20050920084036.178:kill
    def kill (self,event,frm,to,undoType=None):

        '''A helper method for all kill commands.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        s = w.get(frm,to)
        if undoType: self.beginCommand(undoType=undoType)
        self.addToKillBuffer(s)
        g.app.gui.replaceClipboardWith(s)
        w.delete(frm,to)
        w.setInsertPoint(frm)
        if undoType:
            self.c.frame.body.forceFullRecolor()
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.178:kill
    #@+node:ekr.20071003183657:killLine
    def killLine (self,event):
        '''Kill the line containing the cursor.'''
        c = self.c
        w = self.editWidget(event,allowMinibuffer=True)
        if not w: return
        if w == c.frame.miniBufferWidget:
            c.k.killLine()
        else:
            s = w.getAllText()
            ins = w.getInsertPoint()
            i,j = g.getLine(s,ins)
            # g.trace(i,j,ins,len(s),repr(s[i:j]))
            if ins >= len(s) and g.match(s,j-1,'\n'): # Kill the trailing newline.
                i = max(0,len(s)-1)
                j = len(s)
            elif j > i+1 and g.match(s,j-1,'\n'): # Kill the line, but not the newline.
                j -= 1
            else: # Kill the newline.
                pass
            self.kill(event,i,j,undoType='kill-line')
    #@-node:ekr.20071003183657:killLine
    #@+node:ekr.20050920084036.182:killRegion & killRegionSave & helper
    def killRegion (self,event):
        '''Kill the text selection.'''
        self.killRegionHelper(event,deleteFlag=True)

    def killRegionSave (self,event):
        '''Add the selected text to the kill ring, but do not delete it.'''
        self.killRegionHelper(event,deleteFlag=False)

    def killRegionHelper (self,event,deleteFlag):

        w = self.editWidget(event)
        if not w: return
        theRange = w.tag_ranges('sel')
        if not theRange: return

        s = w.get(theRange[0],theRange[-1])
        if deleteFlag:
            self.beginCommand(undoType='kill-region')
            w.delete(theRange[0],theRange[-1])
            self.c.frame.body.forceFullRecolor()
            self.endCommand(changed=True,setLabel=True)
        self.addToKillBuffer(s)
        g.app.gui.replaceClipboardWith(s)
        # self.removeRKeys(w)
    #@-node:ekr.20050920084036.182:killRegion & killRegionSave & helper
    #@+node:ekr.20050930095323.1:killSentence
    def killSentence (self,event):

        '''Kill the sentence containing the cursor.'''

        w = self.editWidget(event)
        if not w: return
        s = w.getAllText()
        ins = w.getInsertPoint()
        i = s.find('.',ins)
        if i == -1: return

        undoType='kill-sentence'

        self.beginCommand(undoType=undoType)

        i2 = s.rfind('.',0,ins) + 1
        self.kill(event,i2,i+1,undoType=undoType)
        self.c.frame.body.forceFullRecolor()
        w.setInsertPoint(i2)

        self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050930095323.1:killSentence
    #@+node:ekr.20050930100733:killWs
    def killWs (self,event,undoType='kill-ws'):

        '''Kill whitespace.'''

        ws = ''
        w = self.editWidget(event)
        if not w: return
        s = w.getAllText()
        i = j = ins = w.getInsertPoint()

        while i >= 0 and s[i] in (' ','\t'):
            i-= 1
        if i < ins: i += 1

        while j < len(s) and s[j] in (' ','\t'):
            j += 1

        if j > i:
            ws = s[i:j]
            # g.trace(i,j,repr(ws))
            w.delete(i,j)
            if undoType: self.beginCommand(undoType=undoType)
            if self.addWsToKillRing:
                self.addToKillBuffer(ws)
            if undoType: self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050930100733:killWs
    #@+node:ekr.20050930091642.1:yank
    def yank (self,event,pop=False):

        '''yank: insert the first entry of the kill ring.
        yank-pop: insert the next entry of the kill ring.
        '''

        c = self.c ; w = self.editWidget(event,allowMinibuffer=True)
        if not w: return
        current = c.currentPosition()
        if not current: return
        text = w.getAllText()
        i, j = w.getSelectionRange()
        clip_text = self.getClipboard()
        if not self.killBuffer and not clip_text: return

        undoType = g.choose(pop,'yank-pop','yank')
        self.beginCommand(undoType=undoType)
        try:
            if not pop or self.lastYankP and self.lastYankP != current:
                self.reset = 0
            s = self.kbiterator.next()
            if s is None: s = clip_text or ''
            if i != j: w.deleteTextSelection()
            if s != s.lstrip(): # s contains leading whitespace.
                i2,j2 = g.getLine(text,i)
                k = g.skip_ws(text,i2)
                if i2 < i <= k:
                    # Replace the line's leading whitespace by s's leading whitespace.
                    w.delete(i2,k)
                    i = i2
            w.insert(i,s)
            w.setSelectionRange(i,i+len(s),insert=i+len(s))
            self.lastYankP = current.copy()
            c.frame.body.forceFullRecolor()
        finally:
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050930091642.1:yank
    #@+node:ekr.20050930091642.2:yankPop
    def yankPop (self,event):

        '''Insert the next entry of the kill ring.'''

        self.yank(event,pop=True)

    #@-node:ekr.20050930091642.2:yankPop
    #@+node:ekr.20050920084036.128:zapToCharacter
    def zapToCharacter (self,event):

        '''Kill characters from the insertion point to a given character.'''

        k = self.k ; w = self.editWidget(event)
        if not w: return

        state = k.getState('zap-to-char')
        if state == 0:
            k.setLabelBlue('Zap To Character: ',protect=True)
            k.setState('zap-to-char',1,handler=self.zapToCharacter)
        else:
            ch = event and event.char or ' '
            k.resetLabel()
            k.clearState()
            if ch.isspace(): return
            s = w.getAllText()
            ins = w.getInsertPoint()
            i = s.find(ch,ins)
            if i == -1: return
            self.beginCommand(undoType='zap-to-char')
            self.addToKillBuffer(s[ins:i])
            w.setAllText(s[:ins] + s[i:])
            w.setInsertPoint(ins)
            self.endCommand(changed=True,setLabel=True)
    #@-node:ekr.20050920084036.128:zapToCharacter
    #@-others
#@-node:ekr.20050920084036.174:killBufferCommandsClass
#@+node:ekr.20050920084036.186:leoCommandsClass (add docstrings)
class leoCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.187: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.
    #@-node:ekr.20050920084036.187: ctor
    #@+node:ekr.20050920084036.188:leoCommands.getPublicCommands
    def getPublicCommands (self):

        '''(leoCommands) Return a dict of the 'legacy' Leo commands.'''

        k = self.k ; d2 = {}

        #@    << define dictionary d of names and Leo commands >>
        #@+node:ekr.20050920084036.189:<< define dictionary d of names and Leo commands >>
        c = self.c ; f = c.frame

        d = {
            'abort-edit-headline':          f.abortEditLabelCommand,
            'about-leo':                    c.about,
            'add-comments':                 c.addComments,     
            'beautify-all':                 c.beautifyAllPythonCode,
            'beautify-tree':                c.beautifyPythonTree,
            'beautify':                     c.beautifyPythonCode,
            'cascade-windows':              f.cascade,
            'check-derived-file':           c.atFileCommands.checkDerivedFile,
            'check-leo-file':               c.fileCommands.checkLeoFile,
            'clear-recent-files':           c.clearRecentFiles,
            'close-window':                 c.close,
            'contract-or-go-left':          c.contractNodeOrGoToParent,
            'check-python-code':            c.checkPythonCode,
            'check-all-python-code':        c.checkAllPythonCode,
            'check-outline':                c.checkOutline,
            'clear-recent-files':           c.clearRecentFiles,
            'clone-node':                   c.clone,
            'contract-node':                c.contractNode,
            'contract-all':                 c.contractAllHeadlines,
            'contract-parent':              c.contractParent,
            'convert-all-blanks':           c.convertAllBlanks,
            'convert-all-tabs':             c.convertAllTabs,
            'convert-blanks':               c.convertBlanks,
            'convert-tabs':                 c.convertTabs,
            'copy-node':                    c.copyOutline,
            'copy-text':                    f.copyText,
            'cut-node':                     c.cutOutline,
            'cut-text':                     f.cutText,
            'de-hoist':                     c.dehoist,
            'delete-comments':              c.deleteComments,
            'delete-node':                  c.deleteOutline,
            'demote':                       c.demote,
            'dump-outline':                 c.dumpOutline,
            'edit-headline':                c.editHeadline,
            'end-edit-headline':            f.endEditLabelCommand,
            'equal-sized-panes':            f.equalSizedPanes,
            'execute-script':               c.executeScript,
            'exit-leo':                     g.app.onQuit,
            'expand-all':                   c.expandAllHeadlines,
            'expand-next-level':            c.expandNextLevel,
            'expand-node':                  c.expandNode,
            'expand-and-go-right':          c.expandNodeAndGoToFirstChild,
            'expand-ancestors-only':        c.expandOnlyAncestorsOfNode,
            'expand-or-go-right':           c.expandNodeOrGoToFirstChild,
            'expand-prev-level':            c.expandPrevLevel,
            'expand-to-level-1':            c.expandLevel1,
            'expand-to-level-2':            c.expandLevel2,
            'expand-to-level-3':            c.expandLevel3,
            'expand-to-level-4':            c.expandLevel4,
            'expand-to-level-5':            c.expandLevel5,
            'expand-to-level-6':            c.expandLevel6,
            'expand-to-level-7':            c.expandLevel7,
            'expand-to-level-8':            c.expandLevel8,
            'expand-to-level-9':            c.expandLevel9,
            'export-headlines':             c.exportHeadlines,
            'extract':                      c.extract,
            'extract-names':                c.extractSectionNames,
            'extract-section':              c.extractSection,
            'find-next-clone':              c.findNextClone,
            'flatten-outline':              c.flattenOutline,
            'go-back':                      c.goPrevVisitedNode,
            'go-forward':                   c.goNextVisitedNode,
            'goto-first-node':              c.goToFirstNode,
            'goto-first-visible-node':      c.goToFirstVisibleNode,
            'goto-first-sibling':           c.goToFirstSibling,
            'goto-last-node':               c.goToLastNode,
            'goto-last-sibling':            c.goToLastSibling,
            'goto-last-visible-node':       c.goToLastVisibleNode,
            'goto-line-number':             c.goToLineNumber,
            'goto-next-changed':            c.goToNextDirtyHeadline,
            'goto-next-clone':              c.goToNextClone,
            'goto-next-marked':             c.goToNextMarkedHeadline,
            'goto-next-node':               c.selectThreadNext,
            'goto-next-sibling':            c.goToNextSibling,
            'goto-next-visible':            c.selectVisNext,
            'goto-parent':                  c.goToParent,
            'goto-prev-node':               c.selectThreadBack,
            'goto-prev-sibling':            c.goToPrevSibling,
            'goto-prev-visible':            c.selectVisBack,
            'hide-invisibles':              c.hideInvisibles,
            'hoist':                        c.hoist,
            'import-at-file':               c.importAtFile,
            'import-at-root':               c.importAtRoot,
            'import-cweb-files':            c.importCWEBFiles,
            'import-derived-file':          c.importDerivedFile,
            'import-flattened-outline':     c.importFlattenedOutline,
            'import-noweb-files':           c.importNowebFiles,
            'indent-region':                c.indentBody,
            'insert-child':                 c.insertChild,
            'insert-node':                  c.insertHeadline,
            'insert-body-time':             c.insertBodyTime,
            'insert-headline-time':         f.insertHeadlineTime,
            'mark':                         c.markHeadline,
            'mark-changed-items':           c.markChangedHeadlines,
            'mark-changed-roots':           c.markChangedRoots,
            'mark-clones':                  c.markClones,
            'mark-subheads':                c.markSubheads,
            'match-brackets':               c.findMatchingBracket,
            'minimize-all':                 f.minimizeAll,
            'move-outline-down':            c.moveOutlineDown,
            'move-outline-left':            c.moveOutlineLeft,
            'move-outline-right':           c.moveOutlineRight,
            'move-outline-up':              c.moveOutlineUp,
            'new':                          c.new,
            'open-compare-window':          c.openCompareWindow,
            'open-find-dialog':             c.showFindPanel, # Deprecated.
            'open-leoDocs-leo':             c.leoDocumentation,
            'open-leoPlugins-leo':          c.openLeoPlugins,
            'open-leoSettings-leo':         c.openLeoSettings,
            'open-scripts-leo':             c.openLeoScripts,
            'open-myLeoSettings-leo':       c.openMyLeoSettings,
            'open-online-home':             c.leoHome,
            'open-online-tutorial':         c.leoTutorial,
            'open-offline-tutorial':        f.leoHelp,
            'open-outline':                 c.open,
            'open-python-window':           c.openPythonWindow,
            # 'open-test-leo':              c.openTest, # Doesn't work.
            'open-users-guide':             c.leoUsersGuide,
            'open-with':                    c.openWith,
            'outline-to-cweb':              c.outlineToCWEB,
            'outline-to-noweb':             c.outlineToNoweb,
            'paste-node':                   c.pasteOutline,
            'paste-retaining-clones':       c.pasteOutlineRetainingClones,
            'paste-text':                   f.pasteText,
            'pretty-print-all-python-code': c.prettyPrintAllPythonCode,
            'pretty-print-python-code':     c.prettyPrintPythonCode,
            'promote':                      c.promote,
            'read-at-auto-nodes':           c.readAtAutoNodes,
            'read-at-file-nodes':           c.readAtFileNodes,
            'read-outline-only':            c.readOutlineOnly,
            'read-file-into-node':          c.readFileIntoNode,
            'redo':                         c.undoer.redo,
            'reformat-paragraph':           c.reformatParagraph,
            'remove-sentinels':             c.removeSentinels,
            'resize-to-screen':             f.resizeToScreen,
            'revert':                       c.revert,
            'save-file':                    c.save,
            'save-file-as':                 c.saveAs,
            'save-file-as-unzipped':        c.saveAsUnzipped,
            'save-file-as-zipped':          c.saveAsZipped,
            'save-file-to':                 c.saveTo,
            'settings':                     c.preferences,
            'set-colors':                   c.colorPanel,
            'set-font':                     c.fontPanel,
            'show-invisibles':              c.showInvisibles,
            'sort-children':                c.sortChildren,
            'sort-siblings':                c.sortSiblings,
            'tangle':                       c.tangle,
            'tangle-all':                   c.tangleAll,
            'tangle-marked':                c.tangleMarked,
            'toggle-active-pane':           f.toggleActivePane,
            'toggle-angle-brackets':        c.toggleAngleBrackets,
            'toggle-invisibles':            c.toggleShowInvisibles,
            'toggle-sparce-move':           c.toggleSparseMove,
            'toggle-split-direction':       f.toggleSplitDirection,
            'undo':                         c.undoer.undo,
            'unindent-region':              c.dedentBody,
            'unmark-all':                   c.unmarkAll,
            'untangle':                     c.untangle,
            'untangle-all':                 c.untangleAll,
            'untangle-marked':              c.untangleMarked,
            'weave':                        c.weave,
            'write-at-auto-nodes':          c.atFileCommands.writeAtAutoNodes,
            'write-at-file-nodes':          c.fileCommands.writeAtFileNodes,
            'write-dirty-at-auto-nodes':    c.atFileCommands.writeDirtyAtAutoNodes,
            'write-dirty-at-file-nodes':    c.fileCommands.writeDirtyAtFileNodes,
            'write-missing-at-file-nodes':  c.fileCommands.writeMissingAtFileNodes,
            'write-outline-only':           c.fileCommands.writeOutlineOnly,
            'write-file-from-node':         c.writeFileFromNode,
        }
        #@-node:ekr.20050920084036.189:<< define dictionary d of names and Leo commands >>
        #@nl

        # Create a callback for each item in d.
        keys = d.keys() ; keys.sort()
        for name in keys:
            f = d.get(name)
            d2 [name] = f
            k.inverseCommandsDict [f.__name__] = name
            # g.trace('leoCommands %24s = %s' % (f.__name__,name))

        return d2
    #@-node:ekr.20050920084036.188:leoCommands.getPublicCommands
    #@-others
#@-node:ekr.20050920084036.186:leoCommandsClass (add docstrings)
#@+node:ekr.20050920084036.190:macroCommandsClass
class macroCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.191: ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.lastMacro = None
        self.macs = []
        self.macro = []
        self.namedMacros = {}

        # Important: we must not interfere with k.state in startKbdMacro!
        self.recordingMacro = False
    #@-node:ekr.20050920084036.191: ctor
    #@+node:ekr.20050920084036.192: getPublicCommands
    def getPublicCommands (self):

        return {
            'call-last-keyboard-macro': self.callLastKeyboardMacro,
            'end-kbd-macro':            self.endKbdMacro,
            'name-last-kbd-macro':      self.nameLastKbdMacro,
            'load-file':                self.loadFile,
            'insert-keyboard-macro' :   self.insertKeyboardMacro,
            'start-kbd-macro':          self.startKbdMacro,
        }
    #@-node:ekr.20050920084036.192: getPublicCommands
    #@+node:ekr.20050920084036.193:Entry points
    #@+node:ekr.20050920084036.194:insertKeyboardMacro
    def insertKeyboardMacro (self,event):

        '''Save all macros to a file.'''

        k = self.k ; state = k.getState('macro-name')
        prompt = 'Macro name: '

        if state == 0:
            k.setLabelBlue(prompt,protect=True)
            k.getArg(event,'macro-name',1,self.insertKeyboardMacro)
        else:
            ch = event.keysym ; s = s = k.getLabel(ignorePrompt=True)
            g.trace(repr(ch),repr(s))
            if ch == 'Return':
                k.clearState()
                self.saveMacros(event,s)
            elif ch == 'Tab':
                k.setLabel('%s%s' % (
                    prompt,self.findFirstMatchFromList(s,self.namedMacros)),
                    prompt=prompt,protect=True)
            else:
                k.updateLabel(event)
    #@+node:ekr.20050920084036.195:findFirstMatchFromList
    def findFirstMatchFromList (self,s,aList=None):

        '''This method finds the first match it can find in a sorted list'''

        k = self.k ; c = k.c

        if aList is not None:
            aList = c.commandsDict.keys()

        pmatches = [item for item in aList if item.startswith(s)]
        pmatches.sort()
        if pmatches:
            mstring = reduce(g.longestCommonPrefix,pmatches)
            return mstring

        return s
    #@-node:ekr.20050920084036.195:findFirstMatchFromList
    #@-node:ekr.20050920084036.194:insertKeyboardMacro
    #@+node:ekr.20050920084036.196:loadFile & helpers
    def loadFile (self,event):

        '''Asks for a macro file name to load.'''

        fileName = g.app.gui.runOpenFileDialog(
            title = 'Open Macro File',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return

        try:
            f = open(fileName)
            self._loadMacros(f)
        except IOError:
            g.es('can not open',fileName)
    #@+node:ekr.20050920084036.197:_loadMacros
    def _loadMacros (self,f):

        '''Loads a macro file into the macros dictionary.'''

        k = self.k
        macros = cPickle.load(f)
        for z in macros:
            k.addToDoAltX(z,macros[z])
    #@-node:ekr.20050920084036.197:_loadMacros
    #@-node:ekr.20050920084036.196:loadFile & helpers
    #@+node:ekr.20050920084036.198:nameLastKbdMacro
    def nameLastKbdMacro (self,event):

        '''Prompt for the name to be given to the last recorded macro.'''

        k = self.k ; state = k.getState('name-macro')

        if state == 0:
            k.setLabelBlue('Name of macro: ',protect=True)
            k.getArg(event,'name-macro',1,self.nameLastKbdMacro)
        else:
            k.clearState()
            name = k.arg
            k.addToDoAltX(name,self.lastMacro)
            k.setLabelGrey('Macro defined: %s' % name)
    #@-node:ekr.20050920084036.198:nameLastKbdMacro
    #@+node:ekr.20050920084036.199:saveMacros & helper
    def saveMacros (self,event,macname):

        '''Asks for a file name and saves it.'''

        fileName = g.app.gui.runSaveFileDialog(
            initialfile = None,
            title='Save Macros',
            filetypes = [("Text","*.txt"), ("All files","*")],
            defaultextension = ".txt")

        if not fileName: return

        try:
            f = file(fileName,'a+')
            f.seek(0)
            if f:
                self._saveMacros(f,macname)
        except IOError:
            g.es('can not create',fileName)

    #@+node:ekr.20050920084036.200:_saveMacros
    def _saveMacros( self, f , name ):
        '''Saves the macros as a pickled dictionary'''

        fname = f.name
        try:
            macs = cPickle.load( f )
        except Exception:
            macs = {}
        f.close()
        if self.namedMacros.has_key( name ):
            macs[ name ] = self.namedMacros[ name ]
            f = file( fname, 'w' )
            cPickle.dump( macs, f )
            f.close()
    #@-node:ekr.20050920084036.200:_saveMacros
    #@-node:ekr.20050920084036.199:saveMacros & helper
    #@+node:ekr.20050920084036.204:startKbdMacro
    def startKbdMacro (self,event):

        '''Start recording a keyboard macro.'''

        k = self.k

        if not self.recordingMacro:
            self.recordingMacro = True
            k.setLabelBlue('Recording keyboard macro...',protect=True)
        else:
            stroke = k.stroke ; keysym = event.keysym
            if stroke == '<Key>' and keysym in ('Control_L','Alt_L','Shift_L'):
                return False
            g.trace('stroke',stroke,'keysym',keysym)
            if stroke == '<Key>' and keysym ==')':
                self.endKbdMacro(event)
                return True
            elif stroke == '<Key>':
                self.macro.append((event.keycode,event.keysym))
                return True
            else:
                self.macro.append((stroke,event.keycode,event.keysym,event.char))
                return True
    #@-node:ekr.20050920084036.204:startKbdMacro
    #@+node:ekr.20050920084036.206:endKbdMacro
    def endKbdMacro (self,event):

        '''Stop recording a keyboard macro.'''

        k = self.k ; self.recordingMacro = False

        if self.macro:
            self.macro = self.macro [: -4]
            self.macs.insert(0,self.macro)
            self.lastMacro = self.macro[:]
            self.macro = []
            k.setLabelGrey('Keyboard macro defined, not named')
        else:
            k.setLabelGrey('Empty keyboard macro')
    #@-node:ekr.20050920084036.206:endKbdMacro
    #@+node:ekr.20050920084036.202:callLastKeyboardMacro & helper (called from universal command)
    def callLastKeyboardMacro (self,event):

        '''Call the last recorded keyboard macro.'''

        w = event and event.widget
        # This does **not** require a text widget.

        if self.lastMacro:
            self._executeMacro(self.lastMacro,w)
    #@+node:ekr.20050920084036.203:_executeMacro (test)
    def _executeMacro (self,macro,w):

        c = self.c ; k = self.k

        for z in macro:
            if len(z) == 2:
                w.event_generate('<Key>',keycode=z[0],keysym=z[1])
            else:
                meth = g.stripBrackets(z[0])
                bunchList = k.bindingsDict.get(meth,[]) ### Probably should not strip < and >
                if bunchList:
                    b = bunchList [0]
                    # ev = Tk.Event()
                    # ev.widget = w
                    # ev.keycode = z [1]
                    # ev.keysym = z [2]
                    # ev.char = z [3]
                    event = g.Bunch(c=c,widget=w,keycode=z[1],keysym=z[2],char=z[3])
                    k.masterCommand(event,b.f,'<%s>' % meth)
    #@-node:ekr.20050920084036.203:_executeMacro (test)
    #@-node:ekr.20050920084036.202:callLastKeyboardMacro & helper (called from universal command)
    #@-node:ekr.20050920084036.193:Entry points
    #@+node:ekr.20051006065746:Common Helpers
    #@+node:ekr.20050920085536.15:addToDoAltX
    # Called from loadFile and nameLastKbdMacro.

    def addToDoAltX (self,name,macro):

        '''Adds macro to Alt-X commands.'''

        k= self ; c = k.c

        if c.commandsDict.has_key(name):
            return False

        def func (event,macro=macro):
            w = event and event.widget
            # This does **not** require a text widget.
            return self._executeMacro(macro,w)

        c.commandsDict [name] = func
        self.namedMacros [name] = macro
        return True
    #@-node:ekr.20050920085536.15:addToDoAltX
    #@-node:ekr.20051006065746:Common Helpers
    #@-others
#@-node:ekr.20050920084036.190:macroCommandsClass
#@+node:ekr.20050920084036.207:queryReplaceCommandsClass (limited to single node)
class queryReplaceCommandsClass (baseEditCommandsClass):

    '''A class to handle query replace commands.'''

    #@    @+others
    #@+node:ekr.20050920084036.208: ctor & init
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.
        self.regexp = False # True: do query-replace-regexp.  Set in stateHandler.

    def init (self):

        self.qQ = None
        self.qR = None
        self.replaced = 0 # The number of replacements.
    #@-node:ekr.20050920084036.208: ctor & init
    #@+node:ekr.20050920084036.209: getPublicCommands
    def getPublicCommands (self):

        return {
            'query-replace':        self.queryReplace,
            'query-replace-regex':  self.queryReplaceRegex,
        }
    #@-node:ekr.20050920084036.209: getPublicCommands
    #@+node:ekr.20050920084036.210:Entry points
    def queryReplace (self,event):

        '''Interactively find and replace text.
        This is not recommended: Leo's other find and change commands are more capable.'''
        self.regexp = False
        self.stateHandler(event)

    def queryReplaceRegex (self,event):
        '''Interactively find and replace text using regular expressions.
        This is not recommended: Leo's other find and change commands are more capable.'''
        self.regexp = True
        self.stateHandler(event)
    #@-node:ekr.20050920084036.210:Entry points
    #@+node:ekr.20051005151838:Helpers
    #@+node:ekr.20050920084036.212:doOneReplace
    def doOneReplace (self,event):

        w = self.editWidget(event)
        if not w: return

        i = w.tag_ranges('qR')
        w.delete(i[0],i[1])
        w.insert('insert',self.qR)
        self.replaced += 1
    #@-node:ekr.20050920084036.212:doOneReplace
    #@+node:ekr.20050920084036.219:findNextMatch (query-replace)
    def findNextMatch (self,event):

        '''Find the next match and select it.
        Return True if a match was found.
        Otherwise, call quitSearch and return False.'''

        k = self.k
        w = self.editWidget(event)
        if not w: return

        if g.app.gui.guiName() != 'tkinter':
            return g.es('command not ready yet',color='blue')

        w.tag_delete('qR')
        if self.regexp:
            #@        << handle regexp >>
            #@+node:ekr.20051005155611:<< handle regexp >>
            try:
                regex = re.compile(self.qQ)
            except Exception:
                self.quitSearch(event,'Illegal regular expression')
                return False

            txt = w.get('insert','end')
            match = regex.search(txt)

            if match:
                start = match.start()
                end = match.end()
                length = end - start
                i = w.getInsertPoint()
                w.setInsertPoint(i+start)
                w.tag_add('qR','insert','insert +%sc' % length)
                w.tag_config('qR',background='lightblue')
                txt = w.get('insert','insert +%sc' % length)
                return True
            else:
                self.quitSearch(event)
                return False
            #@-node:ekr.20051005155611:<< handle regexp >>
            #@nl
        else:
            #@        << handle plain search >>
            #@+node:ekr.20051005160923:<< handle plain search >> (tag_add & tag_config) LATER
            i = w.search(self.qQ,'insert',stopindex='end')

            if i:
                w.setInsertPoint(i)
                w.tag_add('qR','insert','insert +%sc' % len(self.qQ))
                w.tag_config('qR',background='lightblue')
                return True
            else:
                self.quitSearch(event)
                return False
            #@-node:ekr.20051005160923:<< handle plain search >> (tag_add & tag_config) LATER
            #@nl
    #@-node:ekr.20050920084036.219:findNextMatch (query-replace)
    #@+node:ekr.20050920084036.211:getUserResponse
    def getUserResponse (self,event):

        w = self.editWidget(event)
        if not w or not hasattr(event,'keysym'): return

        # g.trace(event.keysym)
        if event.keysym == 'y':
            self.doOneReplace(event)
            if not self.findNextMatch(event):
                self.quitSearch(event)
        elif event.keysym in ('q','Return'):
            self.quitSearch(event)
        elif event.keysym == '!':
            while self.findNextMatch(event):
                self.doOneReplace(event)
        elif event.keysym in ('n','Delete'):
            # Skip over the present match.
            i = w.getInsertPoint()
            w.setInsertPoint(i + len(self.qQ))
            if not self.findNextMatch(event):
                self.quitSearch(event)

        w.seeInsertPoint()
    #@-node:ekr.20050920084036.211:getUserResponse
    #@+node:ekr.20050920084036.220:quitSearch
    def quitSearch (self,event,message=None):

        k = self.k
        w = self.editWidget(event)
        if not w: return

        w.tag_delete('qR')
        k.clearState()
        if message is None:
            message = 'Replaced %d occurences' % self.replaced
        k.setLabelGrey(message)
    #@-node:ekr.20050920084036.220:quitSearch
    #@+node:ekr.20050920084036.215:stateHandler
    def stateHandler (self,event):

        k = self.k ; state = k.getState('query-replace')

        prompt = g.choose(self.regexp,'Query replace regexp','Query replace')

        if state == 0: # Get the first arg.
            self.init()
            k.setLabelBlue(prompt + ': ',protect=True)
            k.getArg(event,'query-replace',1,self.stateHandler)
        elif state == 1: # Get the second arg.
            self.qQ = k.arg
            if len(k.arg) > 0:
                prompt = '%s %s with: ' % (prompt,k.arg)
                k.setLabelBlue(prompt)
                k.getArg(event,'query-replace',2,self.stateHandler)
            else:
                k.resetLabel()
                k.clearState()
        elif state == 2: # Set the prompt and find the first match.
            self.qR = k.arg # Null replacement arg is ok.
            k.setLabelBlue('Query replacing %s with %s\n' % (self.qQ,self.qR) +
                'y: replace, (n or Delete): skip, !: replace all, (q or Return): quit',
                protect=True)
            k.setState('query-replace',3,self.stateHandler)
            self.findNextMatch(event)
        elif state == 3:
            self.getUserResponse(event)
    #@-node:ekr.20050920084036.215:stateHandler
    #@-node:ekr.20051005151838:Helpers
    #@-others
#@-node:ekr.20050920084036.207:queryReplaceCommandsClass (limited to single node)
#@+node:ekr.20050920084036.221:rectangleCommandsClass
class rectangleCommandsClass (baseEditCommandsClass):

    #@    @+others
    #@+node:ekr.20050920084036.222: ctor & finishCreate
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.theKillRectangle = [] # Do not re-init this!
        self.stringRect = None

    def finishCreate(self):

        baseEditCommandsClass.finishCreate(self)

        self.commandsDict = {
            'c': ('clear-rectangle',    self.clearRectangle),
            'd': ('delete-rectangle',   self.deleteRectangle),
            'k': ('kill-rectangle',     self.killRectangle),
            'o': ('open-rectangle',     self.openRectangle),
            'r': ('copy-rectangle-to-register',
                self.c.registerCommands.copyRectangleToRegister),
            't': ('string-rectangle',   self.stringRectangle),
            'y': ('yank-rectangle',     self.yankRectangle),
        }
    #@-node:ekr.20050920084036.222: ctor & finishCreate
    #@+node:ekr.20051004112630:check
    def check (self,event,warning='No rectangle selected'):

        '''Return True if there is a selection.
        Otherwise, return False and issue a warning.'''

        return self._chckSel(event,warning)
    #@-node:ekr.20051004112630:check
    #@+node:ekr.20050920084036.223:getPublicCommands
    def getPublicCommands (self):

        return {
            'clear-rectangle':  self.clearRectangle,
            'close-rectangle':  self.closeRectangle,
            'delete-rectangle': self.deleteRectangle,
            'kill-rectangle':   self.killRectangle,
            'open-rectangle':   self.openRectangle,
            'string-rectangle': self.stringRectangle,
            'yank-rectangle':   self.yankRectangle,
        }
    #@-node:ekr.20050920084036.223:getPublicCommands
    #@+node:ekr.20051215103053:beginCommand & beginCommandWithEvent (rectangle)
    def beginCommand (self,undoType='Typing'):

        w = baseEditCommandsClass.beginCommand(self,undoType)
        r1,r2,r3,r4 = self.getRectanglePoints(w)
        return w,r1,r2,r3,r4


    def beginCommandWithEvent (self,event,undoType='Typing'):

        '''Do the common processing at the start of each command.'''

        w = baseEditCommandsClass.beginCommandWithEvent(self,event,undoType)
        r1,r2,r3,r4 = self.getRectanglePoints(w)
        return w,r1,r2,r3,r4
    #@-node:ekr.20051215103053:beginCommand & beginCommandWithEvent (rectangle)
    #@+node:ekr.20050920084036.224:Entries (rectangleCommandsClass)
    #@+node:ekr.20050920084036.225:clearRectangle
    def clearRectangle (self,event):

        '''Clear the rectangle defined by the start and end of selected text.'''

        w = self.editWidget(event)
        if not w or not self.check(event): return

        w,r1,r2,r3,r4 = self.beginCommand('clear-rectangle')

        # Change the text.
        fill = ' ' *(r4-r2)
        for r in xrange(r1,r3+1):
            w.delete('%s.%s' % (r,r2),'%s.%s' % (r,r4))
            w.insert('%s.%s' % (r,r2),fill)

        w.setSelectionRange('%s.%s'%(r1,r2),'%s.%s'%(r3,r2+len(fill)))

        self.endCommand()
    #@-node:ekr.20050920084036.225:clearRectangle
    #@+node:ekr.20050920084036.226:closeRectangle
    def closeRectangle (self,event):

        '''Delete the rectangle if it contains nothing but whitespace..'''

        w = self.editWidget(event)
        if not w or not self.check(event): return

        w,r1,r2,r3,r4 = self.beginCommand('close-rectangle')

        # Return if any part of the selection contains something other than whitespace.
        for r in xrange(r1,r3+1):
            s = w.get('%s.%s' % (r,r2),'%s.%s' % (r,r4))
            if s.strip(): return

        # Change the text.
        for r in xrange(r1,r3+1):
            w.delete('%s.%s' % (r,r2),'%s.%s' % (r,r4))

        i = '%s.%s' % (r1,r2)
        j = '%s.%s' % (r3,r2)
        w.setSelectionRange(i,j,insert=j)

        self.endCommand()
    #@-node:ekr.20050920084036.226:closeRectangle
    #@+node:ekr.20050920084036.227:deleteRectangle
    def deleteRectangle (self,event):

        '''Delete the rectangle defined by the start and end of selected text.'''

        w = self.editWidget(event)
        if not w or not self.check(event): return

        w,r1,r2,r3,r4 = self.beginCommand('delete-rectangle')

        for r in xrange(r1,r3+1):
            w.delete('%s.%s' % (r,r2),'%s.%s' % (r,r4))

        i = '%s.%s' % (r1,r2)
        j = '%s.%s' % (r3,r2)
        w.setSelectionRange(i,j,insert=j)

        self.endCommand()
    #@-node:ekr.20050920084036.227:deleteRectangle
    #@+node:ekr.20050920084036.228:killRectangle
    def killRectangle (self,event):

        '''Kill the rectangle defined by the start and end of selected text.'''

        w = self.editWidget(event)
        if not w or not self.check(event): return

        w,r1,r2,r3,r4 = self.beginCommand('kill-rectangle')

        self.theKillRectangle = []

        for r in xrange(r1,r3+1):
            s = w.get('%s.%s' % (r,r2),'%s.%s' % (r,r4))
            self.theKillRectangle.append(s)
            w.delete('%s.%s' % (r,r2),'%s.%s' % (r,r4))

        # g.trace('killRect',repr(self.theKillRectangle))

        if self.theKillRectangle:
            ins = '%s.%s' % (r,r2)
            w.setSelectionRange(ins,ins,insert=ins)

        self.endCommand()
    #@-node:ekr.20050920084036.228:killRectangle
    #@+node:ekr.20050920084036.230:openRectangle
    def openRectangle (self,event):

        '''Insert blanks in the rectangle defined by the start and end of selected text.
        This pushes the previous contents of the rectangle rightward.'''

        w = self.editWidget(event)
        if not w or not self.check(event): return

        w,r1,r2,r3,r4 = self.beginCommand('open-rectangle')

        fill = ' ' * (r4-r2)
        for r in xrange(r1,r3+1):
            w.insert('%s.%s' % (r,r2),fill)

        i = '%s.%s' % (r1,r2)
        j = '%s.%s' % (r3,r2+len(fill))
        w.setSelectionRange(i,j,insert=j)

        self.endCommand()
    #@-node:ekr.20050920084036.230:openRectangle
    #@+node:ekr.20050920084036.232:stringRectangle
    def stringRectangle (self,event):

        '''Prompt for a string, then replace the contents of a rectangle with a string on each line.'''

        c = self.c ; k = self.k ; state = k.getState('string-rect')
        if g.app.unitTesting:
            state = 1 ; k.arg = 's...s' # This string is known to the unit test.
            w = self.editWidget(event)
            self.stringRect = self.getRectanglePoints(w)
        if state == 0:
            w = self.editWidget(event) # sets self.w
            if not w or not self.check(event): return
            self.stringRect = self.getRectanglePoints(w)
            k.setLabelBlue('String rectangle: ',protect=True)
            k.getArg(event,'string-rect',1,self.stringRectangle)
        else:
            k.clearState()
            k.resetLabel()
            c.bodyWantsFocus()
            w = self.w
            self.beginCommand('string-rectangle')
            r1, r2, r3, r4 = self.stringRect
            for r in xrange(r1,r3+1):
                w.delete('%s.%s' % (r,r2),'%s.%s' % (r,r4))
                w.insert('%s.%s' % (r,r2),k.arg)
            w.setSelectionRange('%d.%d' % (r1,r2),'%d.%d' % (r3,r2+len(k.arg)))

            self.endCommand()
    #@nonl
    #@-node:ekr.20050920084036.232:stringRectangle
    #@+node:ekr.20050920084036.229:yankRectangle
    def yankRectangle (self,event,killRect=None):

        '''Yank into the rectangle defined by the start and end of selected text.'''

        c = self.c ; k = self.k
        w = self.editWidget(event)
        if not w: return

        killRect = killRect or self.theKillRectangle
        if g.app.unitTesting:
            # This value is used by the unit test.
            killRect = ['Y1Y','Y2Y','Y3Y','Y4Y']
        elif not killRect:
            k.setLabelGrey('No kill rect') ; return

        w,r1,r2,r3,r4 = self.beginCommand('yank-rectangle')

        n = 0
        for r in xrange(r1,r3+1):
            # g.trace(n,r,killRect[n])
            if n >= len(killRect): break
            w.delete('%s.%s' % (r,r2), '%s.%s' % (r,r4))
            w.insert('%s.%s' % (r,r2), killRect[n])
            n += 1

        i = '%s.%s' % (r1,r2)
        j = '%s.%s' % (r3,r2+len(killRect[n-1]))
        w.setSelectionRange(i,j,insert=j)

        self.endCommand()
    #@-node:ekr.20050920084036.229:yankRectangle
    #@-node:ekr.20050920084036.224:Entries (rectangleCommandsClass)
    #@-others
#@-node:ekr.20050920084036.221:rectangleCommandsClass
#@+node:ekr.20050920084036.234:registerCommandsClass
class registerCommandsClass (baseEditCommandsClass):

    '''A class to represent registers a-z and the corresponding Emacs commands.'''

    #@    @+others
    #@+node:ekr.20051004095209:Birth
    #@+node:ekr.20050920084036.235: ctor, finishCreate & init
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.methodDict, self.helpDict = self.addRegisterItems()
        self.init()

    def finishCreate (self):

        baseEditCommandsClass.finishCreate(self) # finish the base class.

        if self.k.useGlobalRegisters:
            self.registers = leoKeys.keyHandlerClass.global_registers
        else:
            self.registers = {}

    def init (self):

        self.method = None 
        self.registerMode = 0 # Must be an int.
    #@-node:ekr.20050920084036.235: ctor, finishCreate & init
    #@+node:ekr.20050920084036.247: getPublicCommands
    def getPublicCommands (self):

        return {
            'append-to-register':           self.appendToRegister,
            'copy-rectangle-to-register':   self.copyRectangleToRegister,
            'copy-to-register':             self.copyToRegister,
            'increment-register':           self.incrementRegister,
            'insert-register':              self.insertRegister,
            'jump-to-register':             self.jumpToRegister,
            # 'number-to-register':           self.numberToRegister,
            'point-to-register':            self.pointToRegister,
            'prepend-to-register':          self.prependToRegister,
            'view-register':                self.viewRegister,
        }
    #@-node:ekr.20050920084036.247: getPublicCommands
    #@+node:ekr.20050920084036.252:addRegisterItems
    def addRegisterItems( self ):

        methodDict = {
            '+':        self.incrementRegister,
            ' ':        self.pointToRegister,
            'a':        self.appendToRegister,
            'i':        self.insertRegister,
            'j':        self.jumpToRegister,
            # 'n':        self.numberToRegister,
            'p':        self.prependToRegister,
            'r':        self.copyRectangleToRegister,
            's':        self.copyToRegister,
            'v' :       self.viewRegister,
        }    

        helpDict = {
            's':    'copy to register',
            'i':    'insert from register',
            '+':    'increment register',
            'n':    'number to register',
            'p':    'prepend to register',
            'a':    'append to register',
            ' ':    'point to register',
            'j':    'jump to register',
            'r':    'rectangle to register',
            'v':    'view register',
        }

        return methodDict, helpDict
    #@-node:ekr.20050920084036.252:addRegisterItems
    #@-node:ekr.20051004095209:Birth
    #@+node:ekr.20051004123217:checkBodySelection
    def checkBodySelection (self,warning='No text selected'):

        return self._chckSel(event=None,warning=warning)
    #@-node:ekr.20051004123217:checkBodySelection
    #@+node:ekr.20050920084036.236:Entries...
    #@+node:ekr.20050920084036.238:appendToRegister
    def appendToRegister (self,event):

        '''Prompt for a register name and append the selected text to the register's contents.'''

        c = self.c ; k = self.k ; state = k.getState('append-to-reg')

        if state == 0:
            k.setLabelBlue('Append to register: ',protect=True)
            k.setState('append-to-reg',1,self.appendToRegister)
        else:
            k.clearState()
            if self.checkBodySelection():
                if event.keysym.isalpha():
                    w = c.frame.body.bodyCtrl
                    c.bodyWantsFocus()
                    key = event.keysym.lower()
                    val = self.registers.get(key,'')
                    try:
                        val = val + w.get('sel.first','sel.last')
                    except Exception:
                        pass
                    self.registers[key] = val
                    k.setLabelGrey('Register %s = %s' % (key,repr(val)))
                else:
                    k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.238:appendToRegister
    #@+node:ekr.20050920084036.237:prependToRegister
    def prependToRegister (self,event):

        '''Prompt for a register name and prepend the selected text to the register's contents.'''

        c = self.c ; k = self.k ; state = k.getState('prepend-to-reg')

        if state == 0:
            k.setLabelBlue('Prepend to register: ',protect=True)
            k.setState('prepend-to-reg',1,self.prependToRegister)
        else:
            k.clearState()
            if self.checkBodySelection():
                if event.keysym.isalpha():
                    w = c.frame.body.bodyCtrl
                    c.bodyWantsFocus()
                    key = event.keysym.lower()
                    val = self.registers.get(key,'')
                    try:
                        val = w.get('sel.first','sel.last') + val
                    except Exception:
                        pass
                    self.registers[key] = val
                    k.setLabelGrey('Register %s = %s' % (key,repr(val)))
                else:
                    k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.237:prependToRegister
    #@+node:ekr.20050920084036.239:copyRectangleToRegister
    def copyRectangleToRegister (self,event):

        '''Prompt for a register name and append the rectangle defined by selected
        text to the register's contents.'''

        c = self.c ; k = self.k ; state = k.getState('copy-rect-to-reg')

        if state == 0:
            w = self.editWidget(event) # sets self.w
            if not w: return
            k.commandName = 'copy-rectangle-to-register'
            k.setLabelBlue('Copy Rectangle To Register: ',protect=True)
            k.setState('copy-rect-to-reg',1,self.copyRectangleToRegister)
        elif self.checkBodySelection('No rectangle selected'):
            k.clearState()
            if event.keysym.isalpha():
                key = event.keysym.lower()
                w = self.w
                c.widgetWantsFocusNow(w)
                r1, r2, r3, r4 = self.getRectanglePoints(w)
                rect = []
                while r1 <= r3:
                    txt = w.get('%s.%s' % (r1,r2),'%s.%s' % (r1,r4))
                    rect.append(txt)
                    r1 = r1 + 1
                self.registers [key] = rect
                k.setLabelGrey('Register %s = %s' % (key,repr(rect)))
            else:
                k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.239:copyRectangleToRegister
    #@+node:ekr.20050920084036.240:copyToRegister
    def copyToRegister (self,event):

        '''Prompt for a register name and append the selected text to the register's contents.'''

        c = self.c ; k = self.k ; state = k.getState('copy-to-reg')

        if state == 0:
            k.commandName = 'copy-to-register'
            k.setLabelBlue('Copy to register: ',protect=True)
            k.setState('copy-to-reg',1,self.copyToRegister)
        else:
            k.clearState()
            if self.checkBodySelection():
                if event.keysym.isalpha():
                    key = event.keysym.lower()
                    w = c.frame.body.bodyCtrl
                    c.bodyWantsFocus()
                    try:
                        val = w.get('sel.first','sel.last')
                    except Exception:
                        g.es_exception()
                        val = ''
                    self.registers[key] = val
                    k.setLabelGrey('Register %s = %s' % (key,repr(val)))
                else:
                    k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.240:copyToRegister
    #@+node:ekr.20050920084036.241:incrementRegister
    def incrementRegister (self,event):

        '''Prompt for a register name and increment its value if it has a numeric value.'''

        c = self.c ; k = self.k ; state = k.getState('increment-reg')

        if state == 0:
            k.setLabelBlue('Increment register: ',protect=True)
            k.setState('increment-reg',1,self.incrementRegister)
        else:
            k.clearState()
            if self._checkIfRectangle(event):
                pass # Error message is in the label.
            elif event.keysym.isalpha():
                key = event.keysym.lower()
                val = self.registers.get(key,0)
                try:
                    val = str(int(val)+1)
                    self.registers[key] = val
                    k.setLabelGrey('Register %s = %s' % (key,repr(val)))
                except ValueError:
                    k.setLabelGrey("Can't increment register %s = %s" % (key,val))
            else:
                k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.241:incrementRegister
    #@+node:ekr.20050920084036.242:insertRegister
    def insertRegister (self,event):

        '''Prompt for a register name and and insert the value of another register into its contents.'''

        c = self.c ; k = self.k ; state = k.getState('insert-reg')

        if state == 0:
            k.commandName = 'insert-register'
            k.setLabelBlue('Insert register: ',protect=True)
            k.setState('insert-reg',1,self.insertRegister)
        else:
            k.clearState()
            if event.keysym.isalpha():
                w = c.frame.body.bodyCtrl
                c.bodyWantsFocus()
                key = event.keysym.lower()
                val = self.registers.get(key)
                if val:
                    if type(val)==type([]):
                        c.rectangleCommands.yankRectangle(val)
                    else:
                        w.insert('insert',val)
                    k.setLabelGrey('Inserted register %s' % key)
                else:
                    k.setLabelGrey('Register %s is empty' % key)
            else:
                k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.242:insertRegister
    #@+node:ekr.20050920084036.243:jumpToRegister
    def jumpToRegister (self,event):

        '''Prompt for a register name and set the insert point to the value in its register.'''

        c = self.c ; k = self.k ; state = k.getState('jump-to-reg')

        if state == 0:
            k.setLabelBlue('Jump to register: ',protect=True)
            k.setState('jump-to-reg',1,self.jumpToRegister)
        else:
            k.clearState()
            if event.keysym.isalpha():
                if self._checkIfRectangle(event): return
                key = event.keysym.lower()
                val = self.registers.get(key)
                w = c.frame.body.bodyCtrl
                c.bodyWantsFocus()
                if val:
                    try:
                        w.setInsertPoint(val)
                        k.setLabelGrey('At %s' % repr(val))
                    except Exception:
                        k.setLabelGrey('Register %s is not a valid location' % key)
                else:
                    k.setLabelGrey('Register %s is empty' % key)
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.243:jumpToRegister
    #@+node:ekr.20050920084036.244:numberToRegister (not used)
    #@+at
    # C-u number C-x r n reg
    #     Store number into register reg (number-to-register).
    # C-u number C-x r + reg
    #     Increment the number in register reg by number (increment-register).
    # C-x r g reg
    #     Insert the number from register reg into the buffer.
    #@-at
    #@@c

    def numberToRegister (self,event):

        k = self.k ; state = k.getState('number-to-reg')

        if state == 0:
            k.commandName = 'number-to-register'
            k.setLabelBlue('Number to register: ',protect=True)
            k.setState('number-to-reg',1,self.numberToRegister)
        else:
            k.clearState()
            if event.keysym.isalpha():
                # self.registers[event.keysym.lower()] = str(0)
                k.setLabelGrey('number-to-register not ready yet.')
            else:
                k.setLabelGrey('Register must be a letter')
    #@-node:ekr.20050920084036.244:numberToRegister (not used)
    #@+node:ekr.20050920084036.245:pointToRegister
    def pointToRegister (self,event):

        '''Prompt for a register name and put a value indicating the insert point in the register.'''

        c = self.c ; k = self.k ; state = k.getState('point-to-reg')

        if state == 0:
            k.commandName = 'point-to-register'
            k.setLabelBlue('Point to register: ',protect=True)
            k.setState('point-to-reg',1,self.pointToRegister)
        else:
            k.clearState()
            if event.keysym.isalpha():
                w = c.frame.body.bodyCtrl
                c.bodyWantsFocus()
                key = event.keysym.lower()
                val = w.getInsertPoint()
                self.registers[key] = val
                k.setLabelGrey('Register %s = %s' % (key,repr(val)))
            else:
                k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.245:pointToRegister
    #@+node:ekr.20050920084036.246:viewRegister
    def viewRegister (self,event):

        '''Prompt for a register name and print its contents.'''

        c = self.c ; k = self.k ; state = k.getState('view-reg')

        if state == 0:
            k.commandName = 'view-register'
            k.setLabelBlue('View register: ',protect=True)
            k.setState('view-reg',1,self.viewRegister)
        else:
            k.clearState()
            if event.keysym.isalpha():
                key = event.keysym.lower()
                val = self.registers.get(key)
                k.setLabelGrey('Register %s = %s' % (key,repr(val)))
            else:
                k.setLabelGrey('Register must be a letter')
        c.bodyWantsFocus()
    #@-node:ekr.20050920084036.246:viewRegister
    #@-node:ekr.20050920084036.236:Entries...
    #@-others
#@-node:ekr.20050920084036.234:registerCommandsClass
#@+node:ekr.20051023094009:Search classes
#@+node:ekr.20060123125256:class minibufferFind( (the findHandler)
class minibufferFind (baseEditCommandsClass):

    '''An adapter class that implements minibuffer find commands using the (hidden) Find Tab.'''

    #@    @+others
    #@+node:ekr.20060123125317.2: ctor (minibufferFind)
    def __init__(self,c,finder):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        # g.trace('minibufferFind: finder',finder)

        self.c = c
        self.k = k = c.k
        self.w = None
        self.finder = finder
        self.findTextList = []
        self.changeTextList = []

        commandName = 'replace-string'
        s = k.getShortcutForCommandName(commandName)
        s = k.prettyPrintKey(s)
        s = k.shortcutFromSetting(s)
        self.replaceStringShortcut = s
    #@-node:ekr.20060123125317.2: ctor (minibufferFind)
    #@+node:ekr.20060124140114: Options (minibufferFind)
    #@+node:ekr.20060124123133:setFindScope
    def setFindScope(self,where):

        '''Set the find-scope radio buttons.

        `where` must be in ('node-only','entire-outline','suboutline-only'). '''

        h = self.finder

        if where in ('node-only','entire-outline','suboutline-only'):
            var = h.svarDict['radio-search-scope'].get()
            if var:
                h.svarDict["radio-search-scope"].set(where)
        else:
            g.trace('oops: bad `where` value: %s' % where)
    #@-node:ekr.20060124123133:setFindScope
    #@+node:ekr.20060124122844:get/set/toggleOption (minibufferFind)
    # This redirection is required to remove gui-dependencies.

    def getOption (self,ivar):          return self.finder.getOption(ivar)
    def setOption (self,ivar,val):      self.finder.setOption(ivar,val)
    def toggleOption (self,ivar):       self.finder.toggleOption(ivar)
    #@-node:ekr.20060124122844:get/set/toggleOption (minibufferFind)
    #@+node:ekr.20060125074939:showFindOptions
    def showFindOptions (self):

        '''Show the present find options in the status line.'''

        frame = self.c.frame ; z = []
        # Set the scope field.
        head  = self.getOption('search_headline')
        body  = self.getOption('search_body')
        scope = self.getOption('radio-search-scope')
        d = {'entire-outline':'all','suboutline-only':'tree','node-only':'node'}
        scope = d.get(scope) or ''
        head = g.choose(head,'head','')
        body = g.choose(body,'body','')
        sep = g.choose(head and body,'+','')

        frame.clearStatusLine()
        s = '%s%s%s %s  ' % (head,sep,body,scope)
        frame.putStatusLine(s,color='blue')

        # Set the type field.
        script = self.getOption('script_search')
        regex  = self.getOption('pattern_match')
        change = self.getOption('script_change')
        if script:
            s1 = '*Script-find'
            s2 = g.choose(change,'-change*','*')
            z.append(s1+s2)
        elif regex: z.append('regex')

        table = (
            ('reverse',         'reverse'),
            ('ignore_case',     'noCase'),
            ('whole_word',      'word'),
            ('wrap',            'wrap'),
            ('mark_changes',    'markChg'),
            ('mark_finds',      'markFnd'),
        )

        for ivar,s in table:
            val = self.getOption(ivar)
            if val: z.append(s)

        frame.putStatusLine(' '.join(z))
    #@-node:ekr.20060125074939:showFindOptions
    #@+node:ekr.20060205105950:setupChangePattern
    def setupChangePattern (self,pattern):

        h = self.finder ; w = h.change_ctrl

        s = g.toUnicode(pattern,g.app.tkEncoding)

        w.delete(0,'end')
        w.insert(0,s)

        h.update_ivars()
    #@-node:ekr.20060205105950:setupChangePattern
    #@+node:ekr.20060125091234:setupSearchPattern
    def setupSearchPattern (self,pattern):

        h = self.finder ; w = h.find_ctrl

        s = g.toUnicode(pattern,g.app.tkEncoding)

        w.delete(0,'end')
        w.insert(0,s)

        h.update_ivars()
    #@-node:ekr.20060125091234:setupSearchPattern
    #@-node:ekr.20060124140114: Options (minibufferFind)
    #@+node:ekr.20060210180352:addChangeStringToLabel
    def addChangeStringToLabel (self,protect=True):

        c = self.c ; k = c.k ; h = self.finder ; w = h.change_ctrl

        c.frame.log.selectTab('Find')
        c.minibufferWantsFocusNow()

        s = w.getAllText()

        while s.endswith('\n') or s.endswith('\r'):
            s = s[:-1]

        k.extendLabel(s,select=True,protect=protect)
    #@-node:ekr.20060210180352:addChangeStringToLabel
    #@+node:ekr.20060210164421:addFindStringToLabel
    def addFindStringToLabel (self,protect=True):

        c = self.c ; k = c.k ; h = self.finder ; w = h.find_ctrl

        c.frame.log.selectTab('Find')
        c.minibufferWantsFocusNow()

        s = w.getAllText()
        while s.endswith('\n') or s.endswith('\r'):
            s = s[:-1]

        k.extendLabel(s,select=True,protect=protect)
    #@-node:ekr.20060210164421:addFindStringToLabel
    #@+node:ekr.20070105123800:changeAll
    def changeAll (self,event):

        k = self.k ; tag = 'change-all' ; state = k.getState(tag)

        if state == 0:
            w = self.editWidget(event) # sets self.w
            if not w: return
            self.setupArgs(forward=True,regexp=False,word=True)
            k.setLabelBlue('Change All From: ',protect=True)
            k.getArg(event,tag,1,self.changeAll)
        elif state == 1:
            self._sString = k.arg
            self.updateFindList(k.arg)
            s = 'Change All: %s With: ' % (self._sString)
            k.setLabelBlue(s,protect=True)
            self.addChangeStringToLabel()
            k.getArg(event,tag,2,self.changeAll,completion=False,prefix=s)
        elif state == 2:
            self.updateChangeList(k.arg)
            self.lastStateHelper()
            self.generalChangeHelper(self._sString,k.arg,changeAll=True)

    #@-node:ekr.20070105123800:changeAll
    #@+node:ekr.20060128080201:cloneFindAll
    def cloneFindAll (self,event):

        c = self.c ; k = self.k ; tag = 'clone-find-all'
        state = k.getState(tag)

        if state == 0:
            w = self.editWidget(event) # sets self.w
            if not w: return
            self.setupArgs(forward=None,regexp=None,word=None)
            k.setLabelBlue('Clone Find All: ',protect=True)
            k.getArg(event,tag,1,self.cloneFindAll)
        else:
            k.clearState()
            k.resetLabel()
            k.showStateAndMode()
            self.generalSearchHelper(k.arg,cloneFindAll=True)
    #@-node:ekr.20060128080201:cloneFindAll
    #@+node:ekr.20060204120158:findAgain
    def findAgain (self,event):

        f = self.finder

        f.p = self.c.currentPosition()
        f.v = self.finder.p.v

        # This handles the reverse option.
        return f.findAgainCommand()
    #@-node:ekr.20060204120158:findAgain
    #@+node:ekr.20060209064140:findAll
    def findAll (self,event):

        k = self.k ; state = k.getState('find-all')
        if state == 0:
            w = self.editWidget(event) # sets self.w
            if not w: return
            self.setupArgs(forward=True,regexp=False,word=True)
            k.setLabelBlue('Find All: ',protect=True)
            k.getArg(event,'find-all',1,self.findAll)
        else:
            k.clearState()
            k.resetLabel()
            k.showStateAndMode()
            self.generalSearchHelper(k.arg,findAll=True)
    #@-node:ekr.20060209064140:findAll
    #@+node:ekr.20060205105950.1:generalChangeHelper
    def generalChangeHelper (self,find_pattern,change_pattern,changeAll=False):

        # g.trace(repr(change_pattern))

        c = self.c

        self.setupSearchPattern(find_pattern)
        self.setupChangePattern(change_pattern)
        c.widgetWantsFocusNow(self.w)

        self.finder.p = self.c.currentPosition()
        self.finder.v = self.finder.p.v

        # Bug fix: 2007-12-14: remove call to self.finder.findNextCommand.
        # This was the cause of replaces not starting in the right place!

        if changeAll:
            self.finder.changeAllCommand()
        else:
            # This handles the reverse option.
            self.finder.findNextCommand()
    #@-node:ekr.20060205105950.1:generalChangeHelper
    #@+node:ekr.20060124181213.4:generalSearchHelper
    def generalSearchHelper (self,pattern,cloneFindAll=False,findAll=False):

        c = self.c

        self.setupSearchPattern(pattern)
        c.widgetWantsFocusNow(self.w)

        self.finder.p = self.c.currentPosition()
        self.finder.v = self.finder.p.v

        if findAll:
            self.finder.findAllCommand()
        elif cloneFindAll:
            self.finder.cloneFindAllCommand()
        else:
            # This handles the reverse option.
            self.finder.findNextCommand()
    #@-node:ekr.20060124181213.4:generalSearchHelper
    #@+node:ekr.20060210174441:lastStateHelper
    def lastStateHelper (self):

        k = self.k
        k.clearState()
        k.resetLabel()
        k.showStateAndMode()
    #@-node:ekr.20060210174441:lastStateHelper
    #@+node:ekr.20050920084036.113:replaceString
    def replaceString (self,event):

        k = self.k ; tag = 'replace-string' ; state = k.getState(tag)
        pattern_match = self.getOption ('pattern_match')
        prompt = 'Replace ' + g.choose(pattern_match,'Regex','String')
        if state == 0:
            self.setupArgs(forward=None,regexp=None,word=None)
            prefix = '%s: ' % prompt
            self.stateZeroHelper(event,tag,prefix,self.replaceString)
        elif state == 1:
            self._sString = k.arg
            self.updateFindList(k.arg)
            s = '%s: %s With: ' % (prompt,self._sString)
            k.setLabelBlue(s,protect=True)
            self.addChangeStringToLabel()
            k.getArg(event,'replace-string',2,self.replaceString,completion=False,prefix=s)
        elif state == 2:
            self.updateChangeList(k.arg)
            self.lastStateHelper()
            self.generalChangeHelper(self._sString,k.arg)
    #@-node:ekr.20050920084036.113:replaceString
    #@+node:ekr.20060124140224.3:reSearchBackward/Forward
    def reSearchBackward (self,event):

        k = self.k ; tag = 're-search-backward' ; state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=False,regexp=True,word=None)
            self.stateZeroHelper(
                event,tag,'Regexp Search Backward:',self.reSearchBackward,
                escapes=[self.replaceStringShortcut])
        elif k.getArgEscape:
            # Switch to the replace command.
            k.setState('replace-string',1,self.replaceString)
            self.replaceString(event=None)
        else:
            self.updateFindList(k.arg)
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)

    def reSearchForward (self,event):

        k = self.k ; tag = 're-search-forward' ; state = k.getState(tag)
        if state == 0:
            self.setupArgs(forward=True,regexp=True,word=None)
            self.stateZeroHelper(
                event,tag,'Regexp Search:',self.reSearchForward,
                escapes=[self.replaceStringShortcut])
        elif k.getArgEscape:
            # Switch to the replace command.
            k.setState('replace-string',1,self.replaceString)
            self.replaceString(event=None)
        else:
            self.updateFindList(k.arg)
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)
    #@-node:ekr.20060124140224.3:reSearchBackward/Forward
    #@+node:ekr.20060124140224.1:seachForward/Backward
    def searchBackward (self,event):

        k = self.k ; tag = 'search-backward' ; state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=False,regexp=False,word=False)
            self.stateZeroHelper(
                event,tag,'Search Backward: ',self.searchBackward,
                escapes=[self.replaceStringShortcut])
        elif k.getArgEscape:
            # Switch to the replace command.
            k.setState('replace-string',1,self.replaceString)
            self.replaceString(event=None)
        else:
            self.updateFindList(k.arg)
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)

    def searchForward (self,event):

        k = self.k ; tag = 'search-forward' ; state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=True,regexp=False,word=False)
            self.stateZeroHelper(
                event,tag,'Search: ',self.searchForward,
                escapes=[self.replaceStringShortcut])
        elif k.getArgEscape:
            # Switch to the replace command.
            k.setState('replace-string',1,self.replaceString)
            self.replaceString(event=None)
        else:
            self.updateFindList(k.arg)
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)
    #@-node:ekr.20060124140224.1:seachForward/Backward
    #@+node:ekr.20060125093807:searchWithPresentOptions
    def searchWithPresentOptions (self,event):

        k = self.k ; tag = 'search-with-present-options'
        state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=None,regexp=None,word=None)
            self.stateZeroHelper(
                event,tag,'Search: ',self.searchWithPresentOptions,
                escapes=[self.replaceStringShortcut])
        elif k.getArgEscape:
            # Switch to the replace command.
            k.setState('replace-string',1,self.replaceString)
            self.replaceString(event=None)
        else:
            self.updateFindList(k.arg)
            k.clearState()
            k.resetLabel()
            k.showStateAndMode()
            self.generalSearchHelper(k.arg)
    #@-node:ekr.20060125093807:searchWithPresentOptions
    #@+node:ekr.20060124134356:setupArgs
    def setupArgs (self,forward=False,regexp=False,word=False):

        h = self.finder ; k = self.k

        if forward is None:
            reverse = None
        else:
            reverse = not forward

        for ivar,val,in (
            ('reverse', reverse),
            ('pattern_match',regexp),
            ('whole_word',word),
        ):
            if val is not None:
                self.setOption(ivar,val)

        h.p = p = self.c.currentPosition()
        h.v = p.v
        h.update_ivars()
        self.showFindOptions()
    #@-node:ekr.20060124134356:setupArgs
    #@+node:ekr.20060210173041:stateZeroHelper
    def stateZeroHelper (self,event,tag,prefix,handler,escapes=None):

        k = self.k
        self.w = self.editWidget(event)
        if not self.w: return

        k.setLabelBlue(prefix,protect=True)
        self.addFindStringToLabel(protect=False)

        # g.trace(escapes,g.callers())
        if escapes is None: escapes = []
        k.getArgEscapes = escapes
        k.getArgEscape = None # k.getArg may set this.
        k.getArg(event,tag,1,handler, # enter state 1
            tabList=self.findTextList,completion=True,prefix=prefix)
    #@-node:ekr.20060210173041:stateZeroHelper
    #@+node:ekr.20060224171851:updateChange/FindList
    def updateChangeList (self,s):

        if s not in self.changeTextList:
            self.changeTextList.append(s)

    def updateFindList (self,s):

        if s not in self.findTextList:
            self.findTextList.append(s)
    #@-node:ekr.20060224171851:updateChange/FindList
    #@+node:ekr.20060124140224.2:wordSearchBackward/Forward
    def wordSearchBackward (self,event):

        k = self.k ; tag = 'word-search-backward' ; state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=False,regexp=False,word=True)
            self.stateZeroHelper(event,tag,'Word Search Backward: ',self.wordSearchBackward)
        else:
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)

    def wordSearchForward (self,event):

        k = self.k ; tag = 'word-search-forward' ; state = k.getState(tag)

        if state == 0:
            self.setupArgs(forward=True,regexp=False,word=True)
            self.stateZeroHelper(event,tag,'Word Search: ',self.wordSearchForward)
        else:
            self.lastStateHelper()
            self.generalSearchHelper(k.arg)
    #@-node:ekr.20060124140224.2:wordSearchBackward/Forward
    #@-others
#@-node:ekr.20060123125256:class minibufferFind( (the findHandler)
#@+node:ekr.20050920084036.257:class searchCommandsClass
class searchCommandsClass (baseEditCommandsClass):

    '''Implements many kinds of searches.'''

    #@    @+others
    #@+node:ekr.20050920084036.258: ctor (searchCommandsClass)
    def __init__ (self,c):

        # g.trace('searchCommandsClass')

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.findTabHandler = None
        self.minibufferFindHandler = None
        self.inited = False

        try:
            self.w = c.frame.body.bodyCtrl
        except AttributeError:
            self.w = None

        # For isearch commands.
        self.ifinder = leoFind.leoFind(c,title='ifinder')
        self.isearch_v = None # vnode of last isearch.
        self.isearch_stack = [] # A stack of previous matches: entries are: (sel,insert)
        self.ignoreCase = None
        self.forward = None
        self.regexp = None
    #@-node:ekr.20050920084036.258: ctor (searchCommandsClass)
    #@+node:ekr.20050920084036.259:getPublicCommands (searchCommandsClass)
    def getPublicCommands (self):

        return {
            'clone-find-all':                       self.cloneFindAll,

            'find-all':                             self.findAll,
            'change-all':                           self.changeAll,

            # Thin wrappers on Find tab
            'change':                               self.findTabChange,
            'change-then-find':                     self.findTabChangeThenFind,
            'find-next':                            self.findTabFindNext,
            'find-prev':                            self.findTabFindPrev,

            'hide-find-tab':                        self.hideFindTab,

            'isearch-forward':                      self.isearchForward,
            'isearch-backward':                     self.isearchBackward,
            'isearch-forward-regexp':               self.isearchForwardRegexp,
            'isearch-backward-regexp':              self.isearchBackwardRegexp,
            'isearch-with-present-options':         self.isearchWithPresentOptions,

            'open-find-tab':                        self.openFindTab,

            'replace-string':                       self.replaceString,

            're-search-forward':                    self.reSearchForward,
            're-search-backward':                   self.reSearchBackward,

            'search-again':                         self.findAgain,
            # Uses existing search pattern.

            'search-forward':                       self.searchForward,
            'search-backward':                      self.searchBackward,
            'search-with-present-options':          self.searchWithPresentOptions,
            # Prompts for search pattern.

            'set-find-everywhere':                  self.setFindScopeEveryWhere,
            'set-find-node-only':                   self.setFindScopeNodeOnly,
            'set-find-suboutline-only':             self.setFindScopeSuboutlineOnly,

            'show-find-options':                    self.showFindOptions,

            'toggle-find-collapses_nodes':          self.toggleFindCollapesNodes,

            'toggle-find-ignore-case-option':       self.toggleIgnoreCaseOption,
            'toggle-find-in-body-option':           self.toggleSearchBodyOption,
            'toggle-find-in-headline-option':       self.toggleSearchHeadlineOption,
            'toggle-find-mark-changes-option':      self.toggleMarkChangesOption,
            'toggle-find-mark-finds-option':        self.toggleMarkFindsOption,
            'toggle-find-regex-option':             self.toggleRegexOption,
            'toggle-find-reverse-option':           self.toggleReverseOption,
            'toggle-find-word-option':              self.toggleWholeWordOption,
            'toggle-find-wrap-around-option':       self.toggleWrapSearchOption,

            'word-search-forward':                  self.wordSearchForward,
            'word-search-backward':                 self.wordSearchBackward,
        }
    #@-node:ekr.20050920084036.259:getPublicCommands (searchCommandsClass)
    #@+node:ekr.20060123131421:Top-level methods
    #@+node:ekr.20051020120306:openFindTab
    def openFindTab (self,event=None,show=True):

        '''Open the Find tab in the log pane.'''

        c = self.c ; log = c.frame.log ; tabName = 'Find'

        wasOpen = self.inited

        if self.inited:
            log.selectTab(tabName)
        else:
            self.inited = True
            log.selectTab(tabName,createText=False)
            f = log.frameDict.get(tabName)
            self.findTabHandler = g.app.gui.createFindTab(c,f)

        if show or wasOpen or c.config.getBool('minibufferSearchesShowFindTab'):
            pass # self.findTabHandler.bringToFront()
        else:
            log.hideTab(tabName)
    #@-node:ekr.20051020120306:openFindTab
    #@+node:ekr.20051022212004:Find Tab commands
    # Just open the Find tab if it has never been opened.
    # For minibuffer commands, it would be good to force the Find tab to be visible.
    # However, this leads to unfortunate confusion when executed from a shortcut.

    def findTabChange(self,event=None):
        '''Execute the 'Change' command with the settings shown in the Find tab.'''
        if self.findTabHandler:
            self.findTabHandler.changeCommand()
        else:
            self.openFindTab()

    def findTabChangeThenFind(self,event=None):
        '''Execute the 'Replace, Find' command with the settings shown in the Find tab.'''
        if self.findTabHandler:
            self.findTabHandler.changeThenFindCommand()
        else:
            self.openFindTab()

    def findTabFindAll(self,event=None):
        '''Execute the 'Find All' command with the settings shown in the Find tab.'''
        if self.findTabHandler:
            self.findTabHandler.findAllCommand()
        else:
            self.openFindTab()

    def findTabFindNext (self,event=None):
        '''Execute the 'Find Next' command with the settings shown in the Find tab.'''
        if self.findTabHandler:
            self.findTabHandler.findNextCommand()
        else:
            self.openFindTab()

    def findTabFindPrev (self,event=None):
        '''Execute the 'Find Previous' command with the settings shown in the Find tab.'''
        if self.findTabHandler:
            self.findTabHandler.findPrevCommand()
        else:
            self.openFindTab()

    def hideFindTab (self,event=None):
        '''Hide the Find tab.'''
        if self.findTabHandler:
            self.c.frame.log.selectTab('Log')
    #@-node:ekr.20051022212004:Find Tab commands
    #@+node:ekr.20060124115801:getHandler
    def getHandler(self,show=False):

        '''Return the minibuffer handler, creating it if necessary.'''

        c = self.c

        self.openFindTab(show=show)
            # sets self.findTabHandler,
            # but *not* minibufferFindHandler.

        if not self.minibufferFindHandler:
            self.minibufferFindHandler = minibufferFind(c,self.findTabHandler)

        return self.minibufferFindHandler
    #@-node:ekr.20060124115801:getHandler
    #@+node:ekr.20060123115459:Find options wrappers
    def setFindScopeEveryWhere (self, event):
        '''Set the 'Entire Outline' radio button in the Find tab.'''
        return self.setFindScope('entire-outline')

    def setFindScopeNodeOnly  (self, event):
        '''Set the 'Node Only' radio button in the Find tab.'''
        return self.setFindScope('node-only')

    def setFindScopeSuboutlineOnly (self, event):
        '''Set the 'Suboutline Only' radio button in the Find tab.'''
        return self.setFindScope('suboutline-only')

    def showFindOptions (self,event):
        '''Show all Find options in the minibuffer label area.'''
        self.getHandler().showFindOptions()

    def toggleFindCollapesNodes(self,event):
        '''Toggle the 'Collapse Nodes' checkbox in the find tab.'''
        # return self.toggleOption('collapse_nodes')
        c = self.c ; p = c.currentPosition()
        val = c.config.getBool('collapse_nodes_during_finds')
        c.config.set(p,'collapse_nodes_during_finds',not val)
        g.es('collapse_nodes_during_finds',c.config.getBool('collapse_nodes_during_finds'))

    def toggleIgnoreCaseOption     (self, event):
        '''Toggle the 'Ignore Case' checkbox in the Find tab.'''
        return self.toggleOption('ignore_case')

    def toggleMarkChangesOption (self, event):
        '''Toggle the 'Mark Changes' checkbox in the Find tab.'''
        return self.toggleOption('mark_changes')
    def toggleMarkFindsOption (self, event):
        '''Toggle the 'Mark Finds' checkbox in the Find tab.'''
        return self.toggleOption('mark_finds')
    def toggleRegexOption (self, event):
        '''Toggle the 'Regexp' checkbox in the Find tab.'''
        return self.toggleOption('pattern_match')
    def toggleReverseOption        (self, event):
        '''Toggle the 'Reverse' checkbox in the Find tab.'''
        return self.toggleOption('reverse')

    def toggleSearchBodyOption (self, event):
        '''Set the 'Search Body' checkbox in the Find tab.'''
        return self.toggleOption('search_body')

    def toggleSearchHeadlineOption (self, event):
        '''Toggle the 'Search Headline' checkbox in the Find tab.'''
        return self.toggleOption('search_headline')

    def toggleWholeWordOption (self, event):
        '''Toggle the 'Whole Word' checkbox in the Find tab.'''
        return self.toggleOption('whole_word')

    def toggleWrapSearchOption (self, event):
        '''Toggle the 'Wrap Around' checkbox in the Find tab.'''
        return self.toggleOption('wrap')

    def setFindScope (self, where):  self.getHandler().setFindScope(where)
    def toggleOption (self, ivar):   self.getHandler().toggleOption(ivar)
    #@-node:ekr.20060123115459:Find options wrappers
    #@+node:ekr.20060124093828:Find wrappers
    def changeAll(self,event=None):
        '''Execute the 'Change All' command with the settings shown in the Find tab.'''
        self.getHandler().changeAll(event)

    def cloneFindAll (self,event):
        '''Do search-with-present-options and print all matches in the log pane. It
        also creates a node at the beginning of the outline containing clones of all
        nodes containing the 'find' string. Only one clone is made of each node,
        regardless of how many clones the node has, or of how many matches are found
        in each node.'''
        self.getHandler().cloneFindAll(event)

    def findAll            (self,event):
        '''Do search-with-present-options and print all matches in the log pane.'''
        self.getHandler().findAll(event)

    def replaceString      (self,event):
        '''Prompts for a search string. Type <Return> to end the search string. The
        command will then prompt for the replacement string. Typing a second
        <Return> key will place both strings in the Find tab and executes a **find**
        command, that is, the search-with-present-options command.'''
        self.getHandler().replaceString(event)

    def reSearchBackward   (self,event):
        '''Set the 'Regexp' checkbox to True and the 'Reverse' checkbox to True,
        then do search-with-present-options.'''
        self.getHandler().reSearchBackward(event)

    def reSearchForward    (self,event):
        '''Set the 'Regexp' checkbox to True, then do search-with-present-options.'''
        self.getHandler().reSearchForward(event)

    def searchBackward     (self,event):
        '''Set the 'Word Search' checkbox to False and the 'Reverse' checkbox to True,
        then do search-with-present-options.'''
        self.getHandler().searchBackward(event)

    def searchForward      (self,event):
        '''Set the 'Word Search' checkbox to False, then do search-with-present-options.'''
        self.getHandler().searchForward(event)

    def wordSearchBackward (self,event):
        '''Set the 'Word Search' checkbox to True, then do search-with-present-options.'''
        self.getHandler().wordSearchBackward(event)

    def wordSearchForward  (self,event):
        '''Set the Word Search' checkbox to True and the 'Reverse' checkbox to True,
        then do search-with-present-options.'''
        self.getHandler().wordSearchForward(event)

    def searchWithPresentOptions (self,event):
        '''Prompts for a search string. Typing the <Return> key puts the search
        string in the Find tab and executes a search based on all the settings in
        the Find tab. Recommended as the default search command.'''
        self.getHandler().searchWithPresentOptions(event)
    #@-node:ekr.20060124093828:Find wrappers
    #@+node:ekr.20060204120158.2:findAgain
    def findAgain (self,event):

        '''The find-again command is the same as the find-next command
        if the search pattern in the Find tab is not '<find pattern here>'
        Otherwise, the find-again is the same as the search-with-present-options command.'''

        h = self.getHandler()

        # h.findAgain returns False if there is no search pattern.
        # In that case, we revert to search-with-present-options.
        if not h.findAgain(event):
            h.searchWithPresentOptions(event)
    #@-node:ekr.20060204120158.2:findAgain
    #@-node:ekr.20060123131421:Top-level methods
    #@+node:ekr.20050920084036.261:incremental search...
    def isearchForward (self,event):
        '''Begin a forward incremental search.'''
        self.startIncremental(event,forward=True,ignoreCase=False,regexp=False)

    def isearchBackward (self,event):
        '''Begin a backward incremental search.'''
        self.startIncremental(event,forward=False,ignoreCase=False,regexp=False)

    def isearchForwardRegexp (self,event):
        '''Begin a forward incremental regexp search.'''
        self.startIncremental(event,forward=True,ignoreCase=False,regexp=True)

    def isearchBackwardRegexp (self,event):
        '''Begin a backard incremental regexp search.'''
        self.startIncremental(event,forward=False,ignoreCase=False,regexp=True)

    def isearchWithPresentOptions (self,event):
        '''Begin an incremental regexp search using the regexp and reverse options from the find panel.'''
        self.startIncremental(event,forward=None,ignoreCase=None,regexp=None)
    #@+node:ekr.20060420144640:iSearchBackspace
    def iSearchBackspace (self):

        c = self.c ; k = self.k ; gui = g.app.gui ; w = self.w

        if not self.isearch_stack:
            ins = w.getInsertPoint()
            self.endSearch(ins,ins)
            return 

        gui.set_focus(c,w)
        pattern = k.getLabel(ignorePrompt=True)
        self.scolorizer(event=None,pattern=pattern)

        sel,ins = self.isearch_stack.pop()

        if sel:
            i,j = sel
            w.setSelectionRange(i,j,insert=ins)
        else:
            w.setInsertPoint(ins)

        w.seeInsertPoint()

        if not self.isearch_stack:
            self.endSearch(ins,ins)
    #@-node:ekr.20060420144640:iSearchBackspace
    #@+node:ekr.20050920084036.262:startIncremental
    def startIncremental (self,event,forward,ignoreCase,regexp):

        c = self.c ; k = self.k ; w = self.w

        # None is a signal to get the option from the find tab.
        if forward is None or regexp is None:
            self.openFindTab(show=False)
            if not self.minibufferFindHandler:
                self.minibufferFindHandler = minibufferFind(c,self.findTabHandler)
            getOption = self.minibufferFindHandler.getOption
            # g.trace('reverse',getOption('reverse'))
            # g.trace('pattern',getOption('pattern_match'))
        else:
            getOption = lambda a: False # The value isn't used.

        self.event = event
        self.forward    = g.choose(forward is None,not getOption('reverse'),forward)
        self.ignoreCase = g.choose(ignoreCase is None,getOption('ignore_case'),ignoreCase)
        self.regexp     = g.choose(regexp  is None,getOption('pattern_match'),regexp)
        # Note: the word option can't be used with isearches!

        self.ins1 = ins = w.getInsertPoint()
        sel = w.getSelectionRange() or (ins,ins),
        self.isearch_stack = [(sel,ins),]

        k.setLabelBlue('Isearch%s%s%s: ' % (
                g.choose(self.forward,'',' Backward'),
                g.choose(self.regexp,' Regexp',''),
                g.choose(self.ignoreCase,' NoCase',''),
            ),protect=True)
        k.setState('isearch',1,handler=self.iSearchStateHandler)
        c.minibufferWantsFocusNow()
    #@-node:ekr.20050920084036.262:startIncremental
    #@+node:ekr.20050920084036.264:iSearchStateHandler
    # Called when from the state manager when the state is 'isearch'

    def iSearchStateHandler (self,event):

        c = self.c ; k = self.k ; w = self.w

        if not event:
            g.trace('no event',g.callers())
            return
        keysym = event.keysym
        ch = event.char
        if keysym == 'Control_L': return

        c.bodyWantsFocusNow()
        if keysym == 'Return':
            i,j = w.getSelectionRange()
            if not self.forward: i,j = j,i
            self.endSearch(i,j)
        elif keysym == 'BackSpace':
            k.updateLabel(event)
            self.iSearchBackspace()
        elif ch:
            k.updateLabel(event)
            self.iSearchHelper(event)
            self.scolorizer(event)
    #@-node:ekr.20050920084036.264:iSearchStateHandler
    #@+node:ekr.20050920084036.265:scolorizer LATER
    def scolorizer (self,event,pattern=None):

        '''Colorizer for incremental searches.'''

        pass # not ready yet.   

        # k = self.k ; w = self.w
        # s = pattern or k.getLabel(ignorePrompt=True)
        # # g.trace(repr(s))
        # w.tag_delete('color','color1')
        # if not s: return
        # if g.app.gui.guiName() != 'tkinter':
            # return g.es('command not ready yet',color='blue')

        # ind = 0
        # index = w.getInsertPoint()
        # index2 = index + len(s)
        # # g.trace(index,index2)
        # # Colorize in the forward direction, regardless of the kind of search.
        # while ind:
            # try:
                # ind = w.search(s,ind,stopindex='end',regexp=self.regexp)
            # except Exception: break
            # if ind:
                # i, d = ind.split('.')
                # d = str(int(d)+len(s))
                # # g.trace(ind)
                # if ind in (index,index2):
                    # w.tag_add('color1',ind,'%s.%s' % (i,d))
                # w.tag_add('color',ind,'%s.%s' % (i,d))
                # ind = i + '.' + d

        # w.tag_config('color',foreground='red')
        # w.tag_config('color1',background='lightblue')
    #@-node:ekr.20050920084036.265:scolorizer LATER
    #@+node:ekr.20050920084036.263:iSearchHelper
    def iSearchHelper (self,event):

        '''Move the cursor to position that matches the pattern in the miniBuffer.
        isearches do not cross node boundaries.'''

        c = self.c ; gui = g.app.gui ; k = self.k ; w = self.w
        p = c.currentPosition()
        self.searchString = pattern = k.getLabel(ignorePrompt=True)
        if not pattern: return
        s = w.getAllText()

        if self.isearch_v != p.v:
            self.isearch_v = p.v
            self.isearch_stack = []

        sel = w.getSelectionRange()
        startindex = insert = w.getInsertPoint()

        if self.forward:
            i1 = startindex
            j1 = len(s)
        else:
            i1 = 0
            j1 = min(len(s),startindex + len(pattern))

        i,j = self.ifinder.searchHelper(s,i1,j1,pattern,
            backwards=not self.forward,
            nocase=self.ignoreCase,
            regexp=self.regexp,
            word=False, # Incremental word-matches are not possible!
            swapij=False)

        if i != -1:
            self.isearch_stack.append((sel,insert),)
            # g.trace(i1,j1,i,j,pos,newpos)
            gui.set_focus(c,w)
            w.setSelectionRange(i,j,insert=i)
    #@-node:ekr.20050920084036.263:iSearchHelper
    #@+node:ekr.20060203072636:endSearch
    def endSearch (self,i,j):

        w = self.w
        w.tag_delete('color','color1')

        insert = g.choose(self.forward,'sel.end','sel.start')
        w.setSelectionRange(i,j,insert=insert)

        self.k.keyboardQuit(event=None)
    #@nonl
    #@-node:ekr.20060203072636:endSearch
    #@-node:ekr.20050920084036.261:incremental search...
    #@-others
#@-node:ekr.20050920084036.257:class searchCommandsClass
#@-node:ekr.20051023094009:Search classes
#@+node:ekr.20051025071455:Spell classes
#@+others
#@+node:ekr.20051025071455.1:class spellCommandsClass
class spellCommandsClass (baseEditCommandsClass):

    '''Commands to support the Spell Tab.'''

    #@    @+others
    #@+node:ekr.20051025080056:ctor
    def __init__ (self,c):

        baseEditCommandsClass.__init__(self,c) # init the base class.

        self.handler = None

        # All the work happens when we first open the frame.
    #@-node:ekr.20051025080056:ctor
    #@+node:ekr.20051025080420:getPublicCommands (searchCommandsClass)
    def getPublicCommands (self):

        return {
            'open-spell-tab':           self.openSpellTab,
            'spell-find':               self.find,
            'spell-change':             self.change,
            'spell-change-then-find':   self.changeThenFind,
            'spell-ignore':             self.ignore,
            'hide-spell-tab':           self.hide,
        }
    #@-node:ekr.20051025080420:getPublicCommands (searchCommandsClass)
    #@+node:ekr.20051025080633:openSpellTab
    def openSpellTab (self,event=None):

        '''Open the Spell Checker tab in the log pane.'''

        c = self.c ; log = c.frame.log ; tabName = 'Spell'

        if log.frameDict.get(tabName):
            log.selectTab(tabName)
        elif self.handler:
            if self.handler.loaded:
                self.handler.bringToFront()
        else:
            log.selectTab(tabName)
            self.handler = spellTabHandler(c,tabName)
            if not self.handler.loaded:
                log.deleteTab(tabName,force=True)
    #@+node:ekr.20051025080420.1:commands...
    # Just open the Spell tab if it has never been opened.
    # For minibuffer commands, we must also force the Spell tab to be visible.

    def find (self,event=None):
        '''Simulate pressing the 'Find' button in the Spell tab.'''
        if self.handler:
            self.openSpellTab()
            self.handler.find()
        else:
            self.openSpellTab()

    def change(self,event=None):
        '''Simulate pressing the 'Change' button in the Spell tab.'''
        if self.handler:
            self.openSpellTab()
            self.handler.change()
        else:
            self.openSpellTab()

    def changeAll(self,event=None):

        if self.handler:
            self.openSpellTab()
            self.handler.changeAll()
        else:
            self.openSpellTab()

    def changeThenFind (self,event=None):
        '''Simulate pressing the 'Change, Find' button in the Spell tab.'''
        if self.handler:
            self.openSpellTab()
            self.handler.changeThenFind()
        else:
            self.openSpellTab()

    def hide (self,event=None):
        '''Hide the Spell tab.'''
        if self.handler:
            self.c.frame.log.selectTab('Log')
            self.c.bodyWantsFocus()

    def ignore (self,event=None):
        '''Simulate pressing the 'Ignore' button in the Spell tab.'''
        if self.handler:
            self.openSpellTab()
            self.handler.ignore()
        else:
            self.openSpellTab()
    #@-node:ekr.20051025080420.1:commands...
    #@-node:ekr.20051025080633:openSpellTab
    #@-others
#@-node:ekr.20051025071455.1:class spellCommandsClass
#@+node:ekr.20051025071455.18:class spellTabHandler (leoFind.leoFind)
class spellTabHandler (leoFind.leoFind):

    """A class to create and manage Leo's Spell Check dialog."""

    #@    @+others
    #@+node:ekr.20051025071455.19:Birth & death
    #@+node:ekr.20051025071455.20:spellTabHandler.__init__
    def __init__(self,c,tabName):

        """Ctor for the Leo Spelling dialog."""

        leoFind.leoFind.__init__(self,c) # Call the base ctor.

        self.c = c
        self.body = c.frame.body
        self.currentWord = None
        self.suggestions = []
        self.messages = [] # List of message to be displayed when hiding the tab.
        self.outerScrolledFrame = None
        self.workCtrl = g.app.gui.plainTextWidget(c.frame.top)
            # A text widget for scanning.
            # Must have a parent frame even though it is not packed.

        self.loaded = self.init_aspell(c)
        if self.loaded:
            self.tab = g.app.gui.createSpellTab(c,self,tabName)
    #@-node:ekr.20051025071455.20:spellTabHandler.__init__
    #@+node:ekr.20051025094004:init_aspell
    def init_aspell (self,c):

        '''Init aspell and related ivars.  Return True if all went well.'''

        self.local_language_code = c.config.getString('spell_local_language_code') or 'en'

        self.dictionaryFileName = dictionaryFileName = (
            c.config.getString('spell_local_dictionary') or
            os.path.join(g.app.loadDir,"..","plugins",'spellpyx.txt'))

        if not dictionaryFileName or not g.os_path_exists(dictionaryFileName):
            g.es_print('can not open dictionary file:',dictionaryFileName, color='red')
            return False

        self.aspell = AspellClass(c,dictionaryFileName,self.local_language_code)

        if self.aspell.aspell:
            self.dictionary = self.readDictionary(dictionaryFileName)
        else:
            self.dictionary = False
            # g.es_print('can not open Aspell',color='red')

        return self.aspell.aspell
    #@-node:ekr.20051025094004:init_aspell
    #@+node:ekr.20051025071455.16:readDictionary
    def readDictionary (self,fileName):

        """Read the dictionary of words which we use as a local dictionary

        Although Aspell itself has the functionality to handle this kind of things
        we duplicate it here so that we can also use it for the "ignore" functionality
        and so that in future a Python only solution could be developed."""

        d = {}

        try:
            f = open(fileName,"r")
        except IOError:
            g.es("can not open local dictionary",fileName,"using a blank one instead")
            return d

        try:
            # Create the dictionary - there are better ways to do this
            # in later Python's but we stick with this method for compatibility
            for word in f.readlines():
                d [word.strip().lower()] = 0
        finally:
            f.close()

        return d
    #@-node:ekr.20051025071455.16:readDictionary
    #@-node:ekr.20051025071455.19:Birth & death
    #@+node:ekr.20051025071455.36:Commands
    #@+node:ekr.20051025071455.37:add
    def add(self,event=None):
        """Add the selected suggestion to the dictionary."""

        if not self.currentWord: return

        # g.trace(self.currentWord)

        try:
            f = None
            try:
                # Rewrite the dictionary in alphabetical order.
                f = open(self.dictionaryFileName, "r")
                words = f.readlines()
                f.close()
                words = [word.strip() for word in words]
                words.append(self.currentWord)
                words.sort()
                f = open(self.dictionaryFileName, "w")
                for word in words:
                    f.write("%s\n" % word)
                f.flush()
                f.close()
                if 1:
                    s = 'Spell: added %s' % self.currentWord
                    self.messages.append(s)
                else: # Too distracting.
                    g.es("adding ", color= "blue", newline= False) 
                    g.es('','%s' % self.currentWord)
            except IOError:
                g.es("can not add",self.currentWord,"to dictionary",color="red")
        finally:
            if f: f.close()

        self.dictionary[self.currentWord.lower()] = 0
        self.tab.onFindButton()
    #@-node:ekr.20051025071455.37:add
    #@+node:ekr.20051025071455.38:change (spellTab)
    def change(self,event=None):
        """Make the selected change to the text"""

        # __pychecker__ = '--no-override --no-argsused'
             # event param is not used, required, and different from base class.

        c = self.c ; body = self.body ; w = body.bodyCtrl

        selection = self.tab.getSuggestion()
        if selection:
            if hasattr(self.tab,'change_i') and self.tab.change_i is not None:
                start,end = oldSel = self.tab.change_i,self.tab.change_j
                # g.trace('using',start,end)
            else:
                start,end = oldSel = w.getSelectionRange()
            if start:
                if start > end: start,end = end,start
                w.delete(start,end)
                w.insert(start,selection)
                w.setSelectionRange(start,start+len(selection))
                c.frame.body.onBodyChanged("Change",oldSel=oldSel)
                c.invalidateFocus()
                c.bodyWantsFocusNow()
                return True

        # The focus must never leave the body pane.
        c.invalidateFocus()
        c.bodyWantsFocusNow()
        return False
    #@-node:ekr.20051025071455.38:change (spellTab)
    #@+node:ekr.20051025071455.40:find & helpers
    def find (self,event=None):
        """Find the next unknown word."""

        c = self.c ; body = c.frame.body ; w = body.bodyCtrl

        # Reload the work pane from the present node.
        s = w.getAllText().rstrip()
        self.workCtrl.delete(0,"end")
        self.workCtrl.insert("end",s)

        # Reset the insertion point of the work widget.
        ins = w.getInsertPoint()
        self.workCtrl.setInsertPoint(ins)

        alts, word = self.findNextMisspelledWord()
        self.currentWord = word # Need to remember this for 'add' and 'ignore'

        if alts:
            # Save the selection range.
            ins = w.getInsertPoint()
            i,j = w.getSelectionRange()
            self.tab.fillbox(alts,word)
            c.invalidateFocus()
            c.bodyWantsFocusNow()
            # Restore the selection range.
            w.setSelectionRange(i,j,insert=ins)
            w.see(ins)
            ### w.update() ###
        else:
            g.es("no more misspellings")
            self.tab.fillbox([])
            c.invalidateFocus()
            c.bodyWantsFocusNow()
    #@+node:ekr.20051025071455.45:findNextMisspelledWord
    def findNextMisspelledWord(self):
        """Find the next unknown word."""

        c = self.c ; p = c.currentPosition()
        w = c.frame.body.bodyCtrl
        aspell = self.aspell ; alts = None ; word = None
        sparseFind = c.config.getBool('collapse_nodes_while_spelling')
        trace = False
        try:
            while 1:
                i,j,p,word = self.findNextWord(p)
                # g.trace(i,j,p and p.headString() or '<no p>')
                if not p or not word:
                    alts = None
                    break
                #@            << Skip word if ignored or in local dictionary >>
                #@+node:ekr.20051025071455.46:<< Skip word if ignored or in local dictionary >>
                #@+at 
                #@nonl
                # We don't bother to call apell if the word is in our 
                # dictionary. The dictionary contains both locally 'allowed' 
                # words and 'ignored' words. We put the test before aspell 
                # rather than after aspell because the cost of checking aspell 
                # is higher than the cost of checking our local dictionary. 
                # For small local dictionaries this is probably not True and 
                # this code could easily be located after the aspell call
                #@-at
                #@@c

                if self.dictionary.has_key(word.lower()):
                    continue
                #@-node:ekr.20051025071455.46:<< Skip word if ignored or in local dictionary >>
                #@nl
                alts = aspell.processWord(word)
                if trace: g.trace('alts',alts and len(alts) or 0,i,j,word,p and p.headString() or 'None')
                if alts:
                    c.beginUpdate()
                    try:
                        redraw = not p.isVisible(c)
                        # New in Leo 4.4.8: show only the 'sparse' tree when redrawing.
                        if sparseFind and not c.currentPosition().isAncestorOf(p):
                            for p2 in c.currentPosition().self_and_parents_iter():
                                p2.contract()
                                redraw = True
                        for p2 in p.parents_iter():
                            if not p2.isExpanded():
                                p2.expand()
                                redraw = True
                        # c.frame.tree.expandAllAncestors(p)
                        c.selectPosition(p)
                    finally:
                        c.endUpdate(redraw)
                        w.setSelectionRange(i,j,insert=j)
                    break
        except Exception:
            g.es_exception()
        return alts, word
    #@-node:ekr.20051025071455.45:findNextMisspelledWord
    #@+node:ekr.20051025071455.47:findNextWord (tkSpell)
    def findNextWord(self,p):
        """Scan for the next word, leaving the result in the work widget"""

        c = self.c ; p = p.copy() ; trace = False
        while 1:
            s = self.workCtrl.getAllText()
            i = self.workCtrl.getInsertPoint()
            while i < len(s) and not g.isWordChar1(s[i]):
                i += 1
            # g.trace('p',p and p.headString(),'i',i,'len(s)',len(s))
            if i < len(s):
                # A non-empty word has been found.
                j = i
                while j < len(s) and g.isWordChar(s[j]):
                    j += 1
                word = s[i:j]
                # This trace verifies that all words have been checked.
                # g.trace(repr(word))
                for w in (self.workCtrl,c.frame.body.bodyCtrl):
                    c.widgetWantsFocusNow(w)
                    w.setSelectionRange(i,j,insert=j)
                if trace: g.trace(i,j,word,p.headString())
                return i,j,p,word
            else:
                # End of the body text.
                p.moveToThreadNext()
                if not p: break
                self.workCtrl.delete(0,'end')
                self.workCtrl.insert(0,p.bodyString())
                for w in (self.workCtrl,c.frame.body.bodyCtrl):
                    c.widgetWantsFocusNow(w)
                    w.setSelectionRange(0,0,insert=0)
                if trace: g.trace(0,0,'-->',p.headString())

        return None,None,None,None
    #@nonl
    #@-node:ekr.20051025071455.47:findNextWord (tkSpell)
    #@-node:ekr.20051025071455.40:find & helpers
    #@+node:ekr.20051025121408:hide
    def hide (self,event=None):

        self.c.frame.log.selectTab('Log')

        for message in self.messages:
            g.es(message,color='blue')

        self.messages = []
    #@-node:ekr.20051025121408:hide
    #@+node:ekr.20051025071455.41:ignore
    def ignore(self,event=None):

        """Ignore the incorrect word for the duration of this spell check session."""

        if not self.currentWord: return

        if 1: # Somewhat helpful: applies until the tab is destroyed.
            s = 'Spell: ignore %s' % self.currentWord
            self.messages.append(s)

        if 0: # Too distracting
            g.es("ignoring ",color= "blue", newline= False)
            g.es('','%s' % self.currentWord)

        self.dictionary[self.currentWord.lower()] = 0
        self.tab.onFindButton()
    #@-node:ekr.20051025071455.41:ignore
    #@-node:ekr.20051025071455.36:Commands
    #@-others
#@-node:ekr.20051025071455.18:class spellTabHandler (leoFind.leoFind)
#@+node:ekr.20051025071455.6:class AspellClass
class AspellClass:

    """A wrapper class for Aspell spell checker"""

    #@    @+others
    #@+node:ekr.20051025071455.7:Birth & death
    #@+node:ekr.20051025071455.8:__init__
    def __init__ (self,c,local_dictionary_file,local_language_code):

        """Ctor for the Aspell class."""

        self.c = c

        self.aspell_dir = g.os_path_abspath(c.config.getString('aspell_dir'))
        self.aspell_bin_dir = g.os_path_abspath(c.config.getString('aspell_bin_dir'))
        self.diagnose = c.config.getBool('diagnose-aspell-installation')

        self.local_language_code = local_language_code or 'en'
        self.local_dictionary_file = g.os_path_abspath(local_dictionary_file)
        self.local_dictionary = "%s.wl" % os.path.splitext(self.local_dictionary_file) [0]

        # g.trace('code',self.local_language_code,'dict',self.local_dictionary_file)
        # g.trace('dir',self.aspell_dir,'bin_dir',self.aspell_bin_dir)

        self.aspell = self.sc = None

        if ctypes:
            self.getAspellWithCtypes()
        else:
            self.getAspell()
    #@-node:ekr.20051025071455.8:__init__
    #@+node:ekr.20061017125710:getAspell
    def getAspell (self):

        if sys.platform.startswith('linux'):
            self.report('You must be using Python 2.5 or above to use aspell on Linux')
            return

        try:
            import aspell
        except ImportError:
            # Specify the path to the top-level Aspell directory.
            theDir = g.choose(sys.platform=='darwin',self.aspell_dir,self.aspell_bin_dir)
            aspell = g.importFromPath('aspell',theDir,pluginName=None,verbose=False)

        if not aspell:
            self.report('can not import aspell')

        self.aspell = aspell
        self.sc = aspell and aspell.spell_checker(prefix=self.aspell_dir,lang=self.local_language_code)
    #@-node:ekr.20061017125710:getAspell
    #@+node:ekr.20061018111331:getAspellWithCtypes
    def getAspellWithCtypes (self):

        try:
            c_int, c_char_p = ctypes.c_int, ctypes.c_char_p

            if sys.platform.startswith('win'):
                path = g.os_path_join(self.aspell_bin_dir, "aspell-15.dll")
                self.aspell = aspell = ctypes.CDLL(path)
            else:
                path = 'aspell'
                libname = ctypes.util.find_library(path)
                assert(libname)
                self.aspell = aspell = ctypes.CDLL(libname)
        except Exception:
            self.report('Can not load %s' % (path))
            self.aspell = self.check = self.sc = None
            return

        try:
            #@        << define and configure aspell entry points >>
            #@+node:ekr.20061018111933:<< define and configure aspell entry points >>
            # new_aspell_config
            new_aspell_config = aspell.new_aspell_config 
            new_aspell_config.restype = c_int

            # aspell_config_replace
            aspell_config_replace = aspell.aspell_config_replace 
            aspell_config_replace.argtypes = [c_int, c_char_p, c_char_p] 

            # aspell_config_retrieve
            aspell_config_retrieve = aspell.aspell_config_retrieve 
            aspell_config_retrieve.restype = c_char_p  
            aspell_config_retrieve.argtypes = [c_int, c_char_p] 

            # aspell_error_message
            aspell_error_message = aspell.aspell_error_message 
            aspell_error_message.restype = c_char_p  

            sc = new_aspell_config()
            if 0:
                print sc 
                print aspell_config_replace(sc, "prefix", self.aspell_dir) #1/0 
                print 'prefix', self.aspell_dir, repr(aspell_config_retrieve(sc, "prefix"))
                print aspell_config_retrieve(sc, "lang")
                print aspell_config_replace(sc, "lang",self.local_language_code)
                print aspell_config_retrieve(sc, "lang")

            possible_err = aspell.new_aspell_speller(sc)
            aspell.delete_aspell_config(c_int(sc))

            # Rudimentary error checking, needs more.  
            if aspell.aspell_error_number(possible_err) != 0:
                self.report(aspell_error_message(possible_err))
                spell_checker = None
            else: 
                spell_checker = aspell.to_aspell_speller(possible_err)

            if not spell_checker:
                raise Exception('aspell checker not enabled')

            word_list_size = aspell.aspell_word_list_size
            word_list_size.restype = c_int
            word_list_size.argtypes = [c_int,]

            # word_list_elements
            word_list_elements = aspell.aspell_word_list_elements
            word_list_elements.restype = c_int
            word_list_elements.argtypes = [c_int,]

            # string_enumeration_next
            string_enumeration_next = aspell.aspell_string_enumeration_next
            string_enumeration_next.restype = c_char_p
            string_enumeration_next.argtypes = [c_int,]

            # check
            check = aspell.aspell_speller_check
            check.restype = c_int 
            check.argtypes = [c_int, c_char_p, c_int]

            # suggest
            suggest = aspell.aspell_speller_suggest
            suggest.restype = c_int 
            suggest.argtypes = [c_int, c_char_p, c_int]
            #@nonl
            #@-node:ekr.20061018111933:<< define and configure aspell entry points >>
            #@nl
        except Exception:
            self.report('aspell checker not enabled')
            self.aspell = self.check = self.sc = None
            return

        # Remember these functions (bound methods).
        # No other ctypes data is known outside this method.
        self.check = check
        self.spell_checker = spell_checker
        self.string_enumeration_next = string_enumeration_next
        self.suggest = suggest
        self.word_list_elements = word_list_elements
        self.word_list_size = word_list_size
    #@-node:ekr.20061018111331:getAspellWithCtypes
    #@+node:ekr.20071111153009:report
    def report (self,message):

        if self.diagnose:
            g.es_print(message,color='blue')
    #@-node:ekr.20071111153009:report
    #@-node:ekr.20051025071455.7:Birth & death
    #@+node:ekr.20051025071455.10:processWord
    def processWord(self, word):
        """Pass a word to aspell and return the list of alternatives.
        OK: 
        * 
        Suggestions: 
        & «original» «count» «offset»: «miss», «miss», ... 
        None: 
        # «original» «offset» 
        simplifyed to not create the string then make a list from it
        """

        # g.trace('word',word)

        if not self.aspell:
            g.trace('aspell not installed')
            return None
        elif ctypes:
            if self.check(self.spell_checker,word,len(word)):
                return None
            else:
                return self.suggestions(word)
        else:
            if self.sc.check(word):
                return None
            else:
                return self.sc.suggest(word)
    #@-node:ekr.20051025071455.10:processWord
    #@+node:ekr.20061018101455.4:suggestions
    def suggestions(self,word):

        "return list of words found"

        aList = []
        sw = self.suggest(self.spell_checker, word, len(word))

        if self.word_list_size(sw):
            ewords = self.word_list_elements(sw)
            while 1: 
                x = self.string_enumeration_next(ewords)
                if x is None: break
                aList.append(x)
        return aList
    #@nonl
    #@-node:ekr.20061018101455.4:suggestions
    #@+node:ekr.20051025071455.11:updateDictionary
    def updateDictionary(self):

        """Update the aspell dictionary from a list of words.

        Return True if the dictionary was updated correctly."""

        try:
            # Create master list
            basename = os.path.splitext(self.local_dictionary)[0]
            cmd = (
                "%s --lang=%s create master %s.wl < %s.txt" %
                (self.aspell_bin_dir, self.local_language_code, basename,basename))
            os.popen(cmd)
            return True

        except Exception, err:
            print "unable to update local aspell dictionary:",err
            return False
    #@-node:ekr.20051025071455.11:updateDictionary
    #@-others
#@-node:ekr.20051025071455.6:class AspellClass
#@-others
#@-node:ekr.20051025071455:Spell classes
#@-others

#@<< define classesList >>
#@+node:ekr.20050922104213:<< define classesList >>
classesList = [
    ('abbrevCommands',      abbrevCommandsClass),
    ('bufferCommands',      bufferCommandsClass),
    ('editCommands',        editCommandsClass),
    ('chapterCommands',     chapterCommandsClass),
    ('controlCommands',     controlCommandsClass),
    ('debugCommands',       debugCommandsClass),
    ('editFileCommands',    editFileCommandsClass),
    ('helpCommands',        helpCommandsClass),
    ('keyHandlerCommands',  keyHandlerCommandsClass),
    ('killBufferCommands',  killBufferCommandsClass),
    ('leoCommands',         leoCommandsClass),
    ('macroCommands',       macroCommandsClass),
    ('queryReplaceCommands',queryReplaceCommandsClass),
    ('rectangleCommands',   rectangleCommandsClass),
    ('registerCommands',    registerCommandsClass),
    ('searchCommands',      searchCommandsClass),
    ('spellCommands',       spellCommandsClass),
]
#@-node:ekr.20050922104213:<< define classesList >>
#@nl
#@-node:ekr.20050710142719:@thin leoEditCommands.py
#@-leo
