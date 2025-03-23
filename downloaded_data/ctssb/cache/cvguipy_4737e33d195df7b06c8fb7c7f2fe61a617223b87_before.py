#!/usr/bin/python
"""Classes and functions for developing interactive GUI utilities based on OpenCV's highgui modules."""

import os, sys, time, argparse, traceback
import random, math
import threading, multiprocessing
import rlcompleter, readline
from collections import OrderedDict
from configobj import ConfigObj
import numpy as np
import shapely.geometry
import cv2
import cvgeom

# check opencv version for compatibility
if cv2.__version__[0] == '2':
    # enums have different names
    cvFONT_HERSHEY_PLAIN = cv2.cv.CV_FONT_HERSHEY_PLAIN
    cvCAP_PROP_FRAME_WIDTH = cv2.cv.CV_CAP_PROP_FRAME_WIDTH
    cvCAP_PROP_FRAME_HEIGHT = cv2.cv.CV_CAP_PROP_FRAME_HEIGHT
    cvCAP_PROP_FRAME_COUNT = cv2.cv.CV_CAP_PROP_FRAME_COUNT
    cvCAP_PROP_FPS = cv2.cv.CV_CAP_PROP_FPS
    cvCAP_PROP_FOURCC = cv2.cv.CV_CAP_PROP_FOURCC
    cvFOURCC = cv2.cv.CV_FOURCC
    cvCAP_PROP_POS_AVI_RATIO = cv2.cv.CV_CAP_PROP_POS_AVI_RATIO
    cvCAP_PROP_POS_FRAMES = cv2.cv.CV_CAP_PROP_POS_FRAMES
    cvCAP_PROP_POS_MSEC = cv2.cv.CV_CAP_PROP_POS_MSEC
    
    # original waitKey function fine in opencv 2
    cvWaitKey = cv2.waitKey
elif cv2.__version__[0] == '3':
    cvFONT_HERSHEY_PLAIN = cv2.FONT_HERSHEY_PLAIN
    cvCAP_PROP_FRAME_WIDTH = cv2.CAP_PROP_FRAME_WIDTH
    cvCAP_PROP_FRAME_HEIGHT = cv2.CAP_PROP_FRAME_HEIGHT
    cvCAP_PROP_FRAME_COUNT = cv2.CAP_PROP_FRAME_COUNT
    cvCAP_PROP_FPS = cv2.CAP_PROP_FPS
    cvCAP_PROP_FOURCC = cv2.CAP_PROP_FOURCC
    cvFOURCC = cv2.VideoWriter_fourcc
    cvCAP_PROP_POS_AVI_RATIO = cv2.CAP_PROP_POS_AVI_RATIO
    cvCAP_PROP_POS_FRAMES = cv2.CAP_PROP_POS_FRAMES
    cvCAP_PROP_POS_MSEC = cv2.CAP_PROP_POS_MSEC
    
    # but was 'fixed' in 3 (gives same results across OS, but modifiers stripped off - we need to use waitKeyEx)
    cvWaitKey = cv2.waitKeyEx

cvColorCodes = {'red': (0,0,255),
                'orange': (0,153,255),
                'yellow': (0,255,255),
                'green': (0,255,0),
                'forest': (0,102,0),
                'cyan': (255,255,0),
                'blue': (255,0,0),
                'indigo': (255,0,102),
                'violet': (204,0,102),
                'pink': (255,0,255),
                'magenta': (153,0,204),
                'brown': (0,51,102),
                'burgundy': (51,51,153),
                'white': (255,255,255),
                'black': (0,0,0)}

def randomColor(whiteOK=True, blackOK=True):
    colors = dict(cvColorCodes)
    if not whiteOK:
        colors.pop('white')
    if not blackOK:
        colors.pop('black')
    return colors.values()[random.randint(0,len(cvColorCodes)-1)]

def getColorCode(color, default='blue', whiteOK=True, blackOK=True):
        if isinstance(color, str):
            if color in cvColorCodes:
                return cvColorCodes[color]
            elif color.lower() == 'random':
                return randomColor(whiteOK, blackOK)
            elif color.lower() == 'default':
                return cvColorCodes[default]
            elif ',' in color:
                try:
                    return tuple(map(int, color.strip('()').split(',')))            # in case we got a string tuple representation
                except:
                    print "Problem loading color {} . Please check your inputs.".format(color)
        elif isinstance(color, tuple) and len(color) == 3:
            try:
                return tuple(map(int, color))           # in case we got a tuple of strings
            except ValueError or TypeError:
                print "Problem loading color {} . Please check your inputs.".format(color)
        else:
            return cvColorCodes[default]

def getUniqueFilename(fname):
    newfname = fname
    if os.path.exists(fname):
        fn, fext = os.path.splitext(fname)
        i = 1
        newfname = "{}_{}".format(fn, i) + fext
        while os.path.exists(newfname):
            i += 1
            newfname = "{}_{}".format(fn, i) + fext
    return newfname

class KeyCode(object):
    """
    An object representing a press of one or more keys, meant to
    correspond to a function (or specifically, a class method).
    
    This class handles the complex key codes from cv2.waitKeyEx,
    which includes the bit flags that correspond to modifiers
    keys. This allows you to set key combinations with simple
    strings like 'ctrl + shift + d'.
    
    Key code strings must include at least one printable ASCII
    character, preceded by 0 or more modifier strings, with the
    key values separated by '+' characters (can be changed with
    the delim argument). Any modifiers following the ASCII key
    are ignored.
    
    A class method is provided to clear the NumLock flag from a
    key code if it is present, since it is generally handled
    correctly by the keyboard driver. Currently this is the
    only modifier that is removed, but if similar unexpected
    behavior is encountered with other lock keys (e.g. function
    lock, which I don't have on a keyboard now), it will likely
    be handled similarly (if it makes sense to do so).
    
    The class also handles characters so the Shift modifier is
    automatically handled (so Ctrl + Shift + A == Ctrl + Shift + a).
    """
    # modifier flags
    MODIFIER_FLAGS = {}
    MODIFIER_FLAGS['SHIFT'] =   0x010000
    MODIFIER_FLAGS['CTRL'] =    0x040000
    MODIFIER_FLAGS['ALT'] =     0x080000
    MODIFIER_FLAGS['SUPER'] =   0x400000
    
    # lock flags to remove
    LOCK_FLAGS = {}
    LOCK_FLAGS['NUMLOCK'] = 0x100000
    LOCK_FLAGS['CAPSLOCK'] = 0x20000
    #LOCK_FLAGS['NUMPAD'] = 0xff80           # NOTE not sure if this is appropriate...
    
    # special keys
    SPECIAL_KEYS = {}
    SPECIAL_KEYS['DEL'] = 0xffff
    SPECIAL_KEYS['BACKSPACE'] = 0x8
    SPECIAL_KEYS['BACKSPACE2'] = 0xff08
    SPECIAL_KEYS['SHIFT'] = 0xffe2
    SPECIAL_KEYS['ENTER'] = 10
    SPECIAL_KEYS['NUMPAD_ENTER'] = 13
    SPECIAL_KEYS['ESC'] = 27
    SPECIAL_KEYS['LEFT'] = 0xff51
    SPECIAL_KEYS['UP'] = 0xff52
    SPECIAL_KEYS['RIGHT'] = 0xff53
    SPECIAL_KEYS['DOWN'] = 0xff54
    SPECIAL_KEYS['F5'] = 0xffc2
       
    def __init__(self, codeString, delim='+'):
        # parse the code string to extract the info we need
        # first split on delim
        keyStrs = codeString.split(delim)
        self.delim = delim.strip()
        
        # loop through the key strings to create our key code
        self.code = 0
        self.codeStrings = []
        self.codeString = None
        key = None
        for ks in keyStrs:
            # check for modifiers (but only add them once)
            if ks.strip().upper() in self.MODIFIER_FLAGS:
                ksu = ks.strip().upper()
                mf = self.MODIFIER_FLAGS[ksu]
                if self.code & mf != mf:
                    # add to the code and to the string list
                    self.code += mf
                    self.codeStrings.append(ksu.capitalize())
            # check for keys (end our loop
            # special keys
            elif ks.strip().upper() in self.SPECIAL_KEYS:
                key = ks.strip().upper()
                break
            # printable ASCII codes (assumed to be first single character)
            elif len(ks.strip()) == 1:
                key = ks.strip()
                break
            elif ks == ' ':
                key = ks
                break
            else:
                # if we got anything else, we can't do anything
                self.code = None
                return
        # if we got a key, use it
        if key is not None:
            if key not in self.SPECIAL_KEYS:
                # take the ord if it's not a special key
                kc = ord(key)
                # make sure it's printable, otherwise we can't do it
                if kc >= 32 and kc < 127:
                    # now check if we got a shift flag, to know if we need to use the upper or lower
                    if self.code & self.MODIFIER_FLAGS['SHIFT'] == self.MODIFIER_FLAGS['SHIFT']:
                        key = key.upper()
                    else:
                        key = key.lower()
                    keycode = ord(key)
            else:
                # otherwise just use the code we have
                keycode = self.SPECIAL_KEYS[key]
            self.codeStrings.append(key)
            # add the keycode to the code and generate the string
            self.code += keycode
            self.codeString = " {} ".format(self.delim).join(self.codeStrings)
        else:
            # if we didn't get a key, we can't do anything
            self.code = None
    
    def __repr__(self):
        return "<KeyCode '{}' = {}>".format(self.codeString, self.code)
    
    def __hash__(self):
        return self.code
    
    def __eq__(self, code):
        """Test if 'code' matches our code."""
        return self.code == code
    
    @classmethod
    def getModifierFlag(cls, modifierName):
        mn = modifierName.upper()
        if mn in cls.MODIFIER_FLAGS:
            return cls.MODIFIER_FLAGS[mn]
    
    @classmethod
    def getSpecialKeyCode(cls, keyName):
        kn = keyName.upper()
        if kn in cls.SPECIAL_KEYS:
            return cls.SPECIAL_KEYS[kn]
    
    @classmethod
    def clearModifier(cls, code, modifierName):
        if modifierName.upper() in cls.MODIFIER_FLAGS:
            m = cls.MODIFIER_FLAGS[modifierName.strip().upper()]
            if code & m == m:
                code -= m
        return code
    
    @classmethod
    def clearShift(cls, code):
        shift = cls.MODIFIER_FLAGS['SHIFT']
        if code & shift == shift:
            key = code - shift
            if key < 127:
                return key
        return code
    
    @classmethod
    def clearLocks(cls, code):
        """Remove any of the LOCK_FLAGS present in the key code."""
        for lf in cls.LOCK_FLAGS.values():
            if code & lf == lf:
                code -= lf
        return code
    
def getFrameObjectList(objects):
    frameObjects = {}
    for o in objects:
        for i in o.timeInterval:
            if i not in frameObjects:
                frameObjects[i] = []
            frameObjects[i].append(o)
    return frameObjects

# TODO move this and other actions to new file (cvactions.py, or similar)
class action(object):
    """
    A dummy class for representing an action that can be done and undone.
    To make an action for a cvGUI-dependent class, create a class based
    on the action class then:
        + override the constructor (and any other functions) to accept all
        inputs the action will require
        + override the do() method, which must perfor all necessary actions
        to "do" the action
        + (optionally) override the undo() method, which should perform all
        necessary actions to undo an action
    Such an action can then be used by a method in a cvGUI-dependent class
    to implement a function that can be undone and re-done easily.
    """
    def __init__(self, name=None):
        self.name = name
        
    def __repr__(self):
        return "<action: {} -- {}>".format(self.__class__.__name__, self.name)
    
    def do(self):
        print "This action has not implemented to do() method, so it does nothing!"
    
    def undo(self):
        print "This action cannot be undone!"


class ObjectMover(action):
    """
    An action for moving a list of objects. It calls the 'move' method of the objects, which must
    accept a single cvgeom.imagepoint object as an argument, containing the X and Y coordinates to move.
    """
    def __init__(self, objects, d):
        self.objects = dict(objects)                    # make a copy of the dict so they can change the selected objects outside of here
        self.d = d
        self.name = "{}".format(self.objects)          # name is objects being moved (used in __repr__)
        
    def addObjects(self, objects):
        """Add more objects to be moved"""
        for i, o in objects.iteritems():
            self.objects[i] = o
        
    def hasObjects(self):
        return len(self.objects) > 0
        
    def do(self):
        """Move all objects in the list by d.x and d.y."""
        for p in self.objects.values():
            p.move(self.d)
        
    def undo(self):
        """Undo the move by moving all objects in the list by -d.x and -d.y."""
        for p in self.objects.values():
            p.move(-self.d)

class ObjectRenamer(action):
    """An action for renaming an object.."""
    def __init__(self, objects, o, n):
        self.objects = objects
        self.o = o
        self.n = n
        self.i = o.index
        self.name = "{}".format(self.o)          # name is objects being moved (used in __repr__)
        
    def do(self):
        """Rename the object by setting o.name and o.index to n and moving it in the objects dictionary."""
        self.o.name = self.n
        self.o.index = self.n
        if self.i in self.objects:
            self.objects.pop(self.i)
        self.objects[self.n] = self.o
        
    def undo(self):
        """Undo the rename by setting everything back."""
        self.o.name = ''
        self.o.index = self.i
        self.objects.pop(self.n)
        self.objects[self.n] = self.o

class ObjectAttributeChanger(action):
    """An action for changing an attribute of an object with a certain method call."""
    def __init__(self, o, methodName, attName, newValue):
        self.o = o
        self.methodName = methodName
        self.attName = attName
        self.newValue = newValue
        self.method = getattr(self.o, self.methodName)
        self.oldValue = getattr(self.o, self.attName)
        self.name = "{}".format(self.o)          # name is objects being changed (used in __repr__)
        
    def do(self):
        self.oldValue = getattr(self.o, self.attName)
        self.method(self.newValue)
        
    def undo(self):
        """Undo the change by calling method with the old value."""
        self.method(self.oldValue)

class ObjectIndexChanger(action):
    """An action for changing the index of an object."""
    def __init__(self, objects, o, newIndex):
        self.o = o
        self.objects = objects                            # keep the reference to the original list so we can change it
        self.newIndex = newIndex
        self.oldIndex = o.getIndex()                        # keep the old index so we can undo
        self.name = "{}".format(self.o)                      # name is point being added (used in __repr__)
        
    def do(self):
        """Change the index of the object and change the key in the collection."""
        if self.newIndex is not None and self.oldIndex in self.objects:
            self.o.setIndex(self.newIndex)
            self.objects[self.o.getIndex()] = self.objects.pop(self.oldIndex)
        
    def undo(self):
        """Undo the add by reversing the do action."""
        if self.newIndex in self.objects:
            self.o.setIndex(self.oldIndex)
            self.objects[self.o.getIndex()] = self.objects.pop(self.newIndex)

class ObjectAdder(action):
    """An action for adding a single cvgeom.IndexableObject to a dictionary keyed on its index."""
    def __init__(self, objects, o):
        self.objList = [o]
        self.objects = objects                            # keep the reference to the original list so we can change it
        self.name = "{}".format(self.objList)             # name is point being added (used in __repr__)
    
    def addObject(self, o):
        self.objList.append(o)
        self.name = "{}".format(self.objList)             # name is point being added (used in __repr__)
    
    def do(self):
        """Add the object to the dict."""
        for o in self.objList:
            if o.getIndex() not in self.objects:
                self.objects[o.getIndex()] = o
    
    def undo(self):
        """Undo the add by removing the object from the dict (but keeping it in case we need it later)."""
        for o in self.objList:
            if o.getIndex() in self.objects:
                self.objects.pop(o.getIndex())

class PointInserter(action):
    """An action for inserting a single cvgeom.imagepoint to a cvgeom.MultiPointObject."""
    def __init__(self, obj, x, y, index):
        self.obj = obj
        self.x = x
        self.y = y
        self.index = index
        self.name = "{}".format(self.obj)                      # name is point being added (used in __repr__)
        
    def do(self):
        """Insert the point."""
        self.obj.insertPoint(self.x, self.y, self.index)
        
    def undo(self):
        """Undo the insertion by removing the point."""
        self.obj.removePoint(self.index)

class ObjectDeleter(action):
    """An action for deleting a list of objects."""
    def __init__(self, objects, dList):
        self.objectLists = [objects]                            # keep the reference to the original list so we can change it, make it a list so we can do more than one thing at a time
        self.dList = [dict(dList)]                        # copy the selected list though (but similarly putting it in a list)
        self.name = "{}".format(self.dList)                  # name is objects being deleted (used in __repr__)
        
    def addObjects(self, objects, dList):
        """Add more objects to be deleted"""
        self.objectLists.append(objects)
        self.dList.append(dict(dList))
        self.name = "{}".format(self.dList)                  # name is objects being deleted (used in __repr__)
    
    def do(self):
        """Delete the objects from the dict (but keep them in case they want to undo)."""
        for objects, dList in zip(self.objectLists, self.dList):
            for i in dList.keys():
                if i in objects:
                    dList[i] = objects.pop(i)
        
    def undo(self):
        """Undo the deletion by reinserting the objects in the dict."""
        for objects, dList in zip(self.objectLists, self.dList):
            for i, o in dList.iteritems():
                if o is not None:
                    objects[i] = o

class PointGrouper(action):
    """
    An action for grouping a list of points, inserting them into the objects
    list as a cvgeom.MultiPointObject, and removing them from the point list.
    """
    def __init__(self, objects, points, groupPoints):
        self.objects = objects
        self.points = points
        self.groupPoints = cvgeom.ObjectCollection(groupPoints)        # need to keep this list as it is now
        self.name = str(self.groupPoints)
        
        # create the new MultiPointObject
        self.mpIndex = self.objects.getNextIndex()
        self.mpObj = cvgeom.MultiPointObject(self.mpIndex, points=self.groupPoints)
        
        # create an ObjectAdder to add the new object
        self.objAdder = ObjectAdder(self.objects, self.mpObj)
        
        # and an ObjectDeleter to delete the points
        self.objDeleter = ObjectDeleter(self.points, self.groupPoints)
    
    def do(self):
        """Remove the points from the list, and add the new object to the object list."""
        # call do on both of our actions
        self.objAdder.do()
        self.objDeleter.do()
    
    def undo(self):
        """Remove the object from the list, and add the points back into their list."""
        # call undo on both of our actions
        self.objAdder.undo()
        self.objDeleter.undo()

class cvWindow(object):
    """
    A class for holding information about an OpenCV HighGUI window,
    e.g. the name, trackbar objects it owns, etc. By default it opens
    a cv2.WINDOW_NORMAL (resizable) window, but this can be changed by
    setting windowType.
    """
    def __init__(self, name, mouseCallback=None, windowType=cv2.WINDOW_NORMAL):
        self.name = name
        self.mouseCallback = mouseCallback
        self.windowType = windowType
        self.trackbars = {}
        self.openWindow()
    
    def __repr__(self):
        return "<Window {}: {} trackbars ({})>".format(self.name, len(self.trackbars), self.trackbars)
    
    def addTrackbar(self, trackbar):
        self.trackbars[trackbar.name] = trackbar
    
    def openWindow(self):
        cv2.namedWindow(self.name, self.windowType)
        
        # set up to read mouse clicks from main window
        if self.mouseCallback is not None:
            cv2.setMouseCallback(self.name, lambda event, x, y, flags, param: self.mouseCallback(event, x, y, flags, param))
    
class cvTrackbar(object):
    """
    A class for holding information baout a trackbar, i.e. its name,
    current and maximum value, etc.
    """
    def __init__(self, name, windowName, value, maxValue, callbackFunction):
        self.name = name
        self.windowName = windowName
        self.value = value
        self.maxValue = maxValue
        self.callbackFunction = callbackFunction
        self.createTrackbar()
    
    def __repr__(self):
        return "<Trackbar {} of window {}: position {} of max {}, callback -> {}".format(self.name, self.windowName, self.value, self.maxValue, self.callbackFunction)
    
    def createTrackbar(self):
        cv2.createTrackbar(self.name, self.windowName, self.value, self.maxValue, lambda tbPos: self.callbackFunction(tbPos))
    
    def update(self, value):
        self.value = value
        cv2.setTrackbarPos(self.name, self.windowName, self.value)
    
    def getPos(self):
        return cv2.getTrackbarPos(self.name, self.windowName)

class cvGUI(object):
    """
    A class for handling interactions with OpenCV's GUI tools.
    Most of this is documented here:
      http://docs.opencv.org/2.4/modules/highgui/doc/user_interface.html
    """
    def __init__(self, filename, configFilename=None, configSection=None, fps=15.0, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, lineThickness=1, textFontSize=4.0, operationTimeout=30, recordFromStart=False, outputVideoFile=None, autosaveInterval=None, maskFilename=None):
        # constants
        self.filename = filename
        self.fileBasename = os.path.basename(filename)
        self.fnameNoExt, self.fext = os.path.splitext(self.fileBasename)
        self.configFilename = getUniqueFilename(os.path.splitext(filename)[0] + '.txt') if configFilename is None else configFilename
        self.configSection = self.fileBasename if configSection is None else configSection
        self.setPlaybackSpeed(fps)
        self.name = filename if name is None else name
        self.printKeys = printKeys
        self.printMouseEvents = printMouseEvents
        self.clickRadius = clickRadius
        self.lineThickness = lineThickness
        self.textFontSize = textFontSize
        self.clickRadius = clickRadius
        self.lineThickness = lineThickness
        self.operationTimeout = operationTimeout            # amount of time to wait for input when performing a blocking action before the operation times out
        self.recordFromStart = recordFromStart
        self.outputVideoFile = outputVideoFile
        self.autosaveInterval = autosaveInterval
        self.maskFilename = maskFilename
        self.windowName = str(self)
        self.mainWindow = None
        
        # important variables and containers
        self.extraWindows = {}                              # list of extra windows {windowName: cvWindow_object,...}
        self.pointConfig = None
        self.lastAutosave = time.time()
        self.alive = multiprocessing.Value('b', True)               # this can cross processes
        self.thread = None
        self.actionBuffer = []              # list of user actions
        self.undoneActions = []             # list of undone actions, which fills as actions are undone
        self.lastKey = None
        self.img, self.image = None, None       # image and a copy
        self.creatingObject = None
        self.isPaused = False
        self.showCoordinates = False
        self.showObjectText = True
        self.saveFrames = False
        self.videoWriter = None
        self.hideTimestamp = False
        self.timestamp = None
        self.isRealtime = False
        self.mask = None
        self.videoFourCC = cvFOURCC('X','V','I','D')      # NOTE - don't try to use H264, it's often broken
        
        # mouse and keyboard functions are registered by defining a function in this class (or one based on it) and inserting it's name into the mouseBindings or keyBindings dictionaries
        self.mouseBindings = OrderedDict()                         # dictionary of {event: methodname} for defining mouse functions
        self.keyBindings = OrderedDict()                           # dictionary of {keyCode: methodname} for defining key bindings
        
        # image-specific properties
        self.imgWidth, self.imgHeight, self.imgDepth = None, None, None
        
        # ImageInput-specific properties
        #self.color = cvColorCodes[color] if color in cvColorCodes else cvColorCodes['blue']
        self.clickDown = cvgeom.imagepoint()
        self.lastClickDown = cvgeom.imagepoint()
        self.clickUp = cvgeom.imagepoint()
        self.mousePos = cvgeom.imagepoint()
        self.lastMousePos = cvgeom.imagepoint()
        self.selectBox = None
        self.clickedOnObject = False
        self.creatingRegion = None
        self.creatingObject = None
        self.userText = None
        #self.selectedPoints = {}
        
        self.points = cvgeom.ObjectCollection()
        self.objects = cvgeom.ObjectCollection()
        self.selectableObjects = ['points','objects']
        
        # key/mouse bindings
        self.addKeyBindings([' '], 'pause')                     # Spacebar - play/pause video
        self.addKeyBindings(['Ctrl + Q'], 'quit')
        self.addKeyBindings(['Ctrl + Z'], 'undo')
        self.addKeyBindings(['Ctrl + Shift + Z', 'Ctrl + Y'], 'redo')
        self.addKeyBindings(['Ctrl + Shift + C'], 'toggleCoordinates')
        self.addKeyBindings(['Ctrl + Shift + N'], 'toggleObjectText')
        self.addKeyBindings(['?'], 'printKeyBindings')
        self.addKeyBindings(['Ctrl + A'], 'selectAll')                      # Ctrl + a - select all
        self.addKeyBindings(['DEL', 'Ctrl + Shift + D'], 'deleteSelected')  # Delete/Ctrl + Shift + d - delete selected points
        self.addKeyBindings(['Ctrl + D'], 'duplicate')                      # Ctrl + D - duplicate object
        self.addKeyBindings(['Ctrl + T'], 'saveConfig')                     # Ctrl + s - save points to file
        self.addKeyBindings(['Ctrl + Shift + R'], 'toggleRecord')           # Ctrl + Shift + R - start/stop recording
        self.addKeyBindings(['Ctrl + Shift + F'], 'saveFrameImageKB')       # Ctrl + Shift + F - output frame to image file
        self.addKeyBindings(['Ctrl + I'], 'printSelectedObjects')           # Ctrl + I - print selected objects to the console
        self.addKeyBindings(['Ctrl + Shift + I'], 'printObjects')           # Ctrl + Shift + I - print all objects to the console
        self.addKeyBindings(['Ctrl + Shift + B'], 'printUndoBuffers')       # Ctrl + Shift + B - print undo/redo buffers to the console
        self.addKeyBindings(['R'], 'createRegion')                          # R - start creating region (closed polygon/linestring)
        self.addKeyBindings(['L'], 'createLine')                            # L - start creating line
        self.addKeyBindings(['D'], 'createDashedLine')                      # D - start creating dashed line
        self.addKeyBindings(['S'], 'createSpline')                          # S - start creating spline
        self.addKeyBindings(['B'], 'createBox')                             # B - start creating box
        self.addKeyBindings(['C'], 'changeSelectedObjectColor')             # C - change the color of the selected object
        self.addKeyBindings(['I'], 'changeSelectedObjectIndex')             # I - change the index of the selected object
        self.addKeyBindings(['N'], 'renameSelectedObject')                  # N - (re)name the selected object
        self.addKeyBindings(['G'], 'groupSelectedPoints')                   # G - group the selected points into a MultiPointObject
        self.addKeyBindings(['H'], 'toggleHideSelected')                    # H - toggle hide/unhide selected cvgeom objects
        self.addKeyBindings(['U'], 'toggleHideAllFromUserText')             # U - toggle hide/unhide selected cvgeom objects in list based on user input
        self.addKeyBindings(['Ctrl + H'], 'hideAll')                        # Ctrl + H - hide all cvgeom objects
        self.addKeyBindings(['Ctrl + U'], 'hideAllFromUserText')            # Ctrl + U - hide all cvgeom objects in list based on user input
        self.addKeyBindings(['Ctrl + Shift + H'], 'unhideAll')              # Ctrl + Shift + H - unhide all cvgeom objects
        self.addKeyBindings(['Ctrl + Shift + U'], 'unhideAllFromUserText')  # Ctrl + Shift + U - unhide all cvgeom objects in list based on user input
        self.addKeyBindings(['ENTER','NUMPAD_ENTER'], 'enterFinish')        # Enter - finish action
        self.addKeyBindings(['ESC'], 'escapeCancel')                        # Escape - cancel action
        self.addKeyBindings(['LEFT'], 'leftOne')                            # Left Arrow - move object left one pixel
        self.addKeyBindings(['UP'], 'upOne')                                # Up Arrow - move object up one pixel
        self.addKeyBindings(['RIGHT'], 'rightOne')                          # Right Arrow - move object right one pixel
        self.addKeyBindings(['DOWN'], 'downOne')                            # Down Arrow - move object up down pixel
        self.addKeyBindings(['Ctrl + F5'], 'update')                        # Ctrl + F5 to update (refresh) image
        
        # we'll need these when we're getting text from the user
        self.keyCodeEnter = KeyCode('ENTER')
        self.keyCodeEnterNP = KeyCode('NUMPAD_ENTER')
        self.keyCodeEscape = KeyCode('ESC')
        self.keyCodeShift = KeyCode.getSpecialKeyCode('SHIFT')
        self.keyCodeBackspace = [KeyCode('BACKSPACE'),KeyCode('BACKSPACE2')]            # flag issues with backspace??
        self.modifierKeys = [cv2.EVENT_FLAG_SHIFTKEY, cv2.EVENT_FLAG_CTRLKEY]
        
        self.addMouseBindings([cv2.EVENT_LBUTTONDOWN], 'leftClickDown')
        self.addMouseBindings([cv2.EVENT_LBUTTONUP], 'leftClickUp')
        self.addMouseBindings([cv2.EVENT_MOUSEMOVE], 'mouseMove')
        self.addMouseBindings([cv2.EVENT_LBUTTONDBLCLK], 'doubleClick')
    
    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.name)
        
    #### Methods for handling keyboard input ###
    def addKeyBindings(self, keyCodeList, funName, warnDuplicate=True):
        """Add a keybinding for each of the key code strings in keyCodeList to trigger method funName."""
        if not isinstance(keyCodeList, list):
            keyList = [keyCodeList]
        for k in keyCodeList:
            # create a KeyCode object from the string and use it as the key
            kc = KeyCode(k)
            if kc in self.keyBindings and warnDuplicate:
                print "Warning! Key binding {} is already used by '{}'. This binding is being overwritten to activate function '{}' !".format(kc, self.keyBindings[kc], funName)
            self.keyBindings[kc] = funName
    
    def printKeyBindings(self, key=None):
        """Print all the known key bindings to stdout."""
        print "Current Key Bindings:"
        print "======================"
        funs = {}
        funStr = 'Function'
        funLen = len(funStr)
        keyStr = 'Key Code(s)'
        keyCodeLen = len(keyStr)
        docStr = 'Description'
        # pull out key bindings
        for kc, fn in self.keyBindings.iteritems():
            if fn not in funs:
                funs[fn] = []
            kcd = kc.codeString if kc.codeString != ' ' else 'Spacebar'
            funs[fn].append(kcd)
            funLen = len(fn) if len(fn) > funLen else funLen
            fks = ', '.join([kcd for kcd in funs[fn]])             # keep track of functions with multiple keybindings so we know how to format the output
            keyCodeLen = len(fks) if len(fks) > keyCodeLen else keyCodeLen
        
        #set maximum line for description
        #get terminal_size
        rows, columns = os.popen('stty size', 'r').read().split()
        docLen = int(columns) - keyCodeLen - funLen - 8
        
        # create string templates for printing
        tStr = '{:' + str(funLen) + '} | {:' + str(keyCodeLen) + '} | {:' + str(docLen) + '} |'           # template string (for formatting output into columns)
        
        # print header string with table formatting
        print tStr.format(funStr, keyStr, docStr)
        print tStr.format(''.join(['-' for i in range(0,funLen)]),''.join(['-' for i in range(0,keyCodeLen)]),''.join(['-' for i in range(0,docLen)]))
        
        # go through all the known keybindings and print their info
        for fn in sorted(funs.keys()):
            ks = ', '.join([kcd for kcd in funs[fn]])
            doc = getattr(self, fn).__doc__
            ds = ' '.join([s for s in map(lambda s: s.strip(), doc.splitlines()) if len(s) > 0]) if doc is not None else ''
            
            # check if the length of description exceed the terminal_width
            if len(ds) > docLen:
                lines=1
                print tStr.format(fn, ks, ds[0:docLen])
                while len(ds) > lines*docLen:
                    print tStr.format("", "", ds[lines*docLen:(lines+1)*docLen-1])
                    lines+=1
            else:
                print tStr.format(fn, ks, ds)
    
    def readKey(self, key):
        """Process a key read with waitKey using the KeyCode class, which handles modifiers."""
        # if less than 0, ignore it NOTE: -1 is what we get when waitKey times out. is there any way to differentiate it from the window's X button??
        self.lastKey = key
        if key >= 0:
            redraw = False
            if self.printKeys:
                print "<Key = {}>".format(key)
            key = KeyCode.clearLocks(key)           # clear any modifier flags from NumLock
            key = KeyCode.clearShift(key)           # clears shift on characters to get the character (i.e. shift + t is the same as T)
            if key in self.keyBindings:
                # if we have a key binding registered, get the method tied to it and call it
                funName = self.keyBindings[key]
                fun = getattr(self, funName)
                try:
                    if fun.func_code.co_argcount == 1:
                        fun()
                    elif fun.im_func.func_code.co_argcount == 2:
                        fun(key)
                    else:
                        print "readKey: Method {} is not implemented correctly! It must take either 1 argument, the key code, or 0 arguments (not including self).".format(funName)
                except:
                    print traceback.format_exc()
                    print "Error encountered in function {} ! See traceback above for more information.".format(funName)
    
    def _isCharValid(self, c, lettersOK=True, numbersOK=True, charsOK=None):
        """Check if character c is valid based on the allowed characters."""
        valid = False
        # make sure charsOK is a list
        if isinstance(charsOK, str):
            charsOK = [charsOK]
        # check the character
        if lettersOK and numbersOK:
            valid = c.isalnum()
        elif lettersOK:
            valid = c.isalpha()
        elif numbersOK:
            valid = c.isdigit()
        if not valid and isinstance(charsOK, list):
            valid = c in charsOK
        return valid
    
    def getUserText(self, dtype=str, lettersOK=True, numbersOK=True,charsOK=None):
        """Read text from the user, drawing it on the screen as it is typed."""
        # call waitKey(0) in a while loop to get user input
        # once userText is a string, a colon will be printed to the screen to let
        # the user know their input is being captured (after we call update)
        self.userText = ''
        self.update()
        
        timeout = False
        key = 0
        tstart = time.time()
        
        # restrict allowed characters if we are reading numbers
        if dtype == int:
            numbersOK = True
            lettersOK = False
            charsOK = None
        elif dtype == float:
            numbersOK = True
            lettersOK = False
            charsOK = ['.']             # decimal point OK for floats
        elif dtype == str and charsOK is None:
            charsOK = [',','.','_']
        while not timeout:
            if (time.time() - tstart) > self.operationTimeout:
                timeout = True
            try:
                key = KeyCode.clearLocks(cv2.waitKey(0))           # clear any modifier flags from NumLock/similar
                if key == self.keyCodeEscape:
                    print "Cancelling..."
                    self.userText = None
                    return
                elif key in self.keyCodeBackspace:
                    self.userText = self.userText[:-1]          # remove the last character typed
                    self.update()
                elif key in [self.keyCodeEnter,self.keyCodeEnterNP]:
                    break
                elif key == self.keyCodeShift:
                    continue        # ignore shift (we only want the character they type)
                else:
                    if self.printKeys:
                        print key
                    key = KeyCode.clearModifier(key, 'SHIFT')      # clear shift so we get capital letters
                    c = chr(key)
                    if self._isCharValid(c, lettersOK=lettersOK, numbersOK=numbersOK, charsOK=charsOK):
                        tstart = time.time()        # restart the timeout counter every time we get input
                        self.userText += c
                        self.update()
            except:
                if self.printKeys:
                    print traceback.format_exc()
        if timeout:
            text = None
        else:
            try:
                text = dtype(self.userText)
            except ValueError:
                print "Error converting text '{}' to {} ! Defaulting to string...".format(self.userText, dtype)
                text = str(self.userText)
        self.userText = None
        return text
    
    def gotModifier(self, flags):
        if flags & cv2.EVENT_FLAG_ALTKEY == cv2.EVENT_FLAG_ALTKEY:
            flags -= cv2.EVENT_FLAG_ALTKEY          # ignore alt key because it overlaps with NumLock for some reason
        for modk in self.modifierKeys:
            if flags & modk == modk:
                return modk
    
    #### Methods for handling mouse input ###
    def addMouseBindings(self, eventList, funName):
        """Add a mouse binding for each of the events in eventList to trigger method funName."""
        if not isinstance(eventList, list):
            eventList = [eventList]
        for k in eventList:
            self.mouseBindings[k] = funName
    
    def readMouse(self, event, x, y, flags, param):
        """Callback function for reading mouse input (moves and clicks)."""
        if isinstance(self.printMouseEvents, list) and (len(self.printMouseEvents) == 0 or event in self.printMouseEvents):
            print "<Mouse Event {} at ({}, {}), flags={} param={}".format(event, x, y, flags, param)
        if event in self.mouseBindings:
            # if we have a function registered to this event, call it
            funName = self.mouseBindings[event]
            fun = getattr(self, funName)
            try:
                fun(event, x, y, flags, param)
            except TypeError:
                ## try it with no arguments
                #try:
                    #fun()
                #except:
                print traceback.format_exc()
                print "readMouse: Method {} not implemented correctly".format(fun)
    
    def setMousePos(self, x, y):
        """Set the current and previous positions of the mouse cursor."""
        self.lastMousePos = self.mousePos
        self.mousePos = cvgeom.imagepoint(x, y)
    
    def mouseMove(self, event, x, y, flags, param):
        """Process mouse movements."""
        self.setMousePos(x, y)
        if flags & cv2.EVENT_FLAG_LBUTTON:
            self.drag(event, x, y, flags, param)
    
    def drag(self, event, x, y, flags, param):
        """Process mouse movements when the left mouse button is held down (i.e. dragging)."""
        if self.isMovingObjects():
            # move the point(s)  each time we get a new move update, then after the button up event add an action to the buffer with the 2-point move so undo/redo jump (like in other things)
            
            # get the distance between the current mouse position and the last position
            d = self.mousePos - self.lastMousePos
            
            # move all of the selected points and regions by d.x and d.y
            self.movePoints(d)
            self.moveObjects(d)
        else:
            # we are drawing a selection rectangle, so we should update it
            self.updateSelection()
        # update the picture
        self.update()
    
    def leftClickDown(self, event, x, y, flags, param):
        """Process left clicks, which select points and start multi-selection."""
        # record where we click down
        self.clickDown = cvgeom.imagepoint(x, y)
        
        # if we are creating a region, add this point right to the selected region
        if isinstance(self.creatingObject, cvgeom.imageregion):
            i = self.addPointToRegion(x, y)
        elif isinstance(self.creatingObject, cvgeom.imagebox):
            if len(self.creatingObject.points) <= 1:
                i = self.addPointToObject(self.creatingObject, x, y)
            if len(self.creatingObject.points) == 2:
                self.creatingObject.finishBox()
                self.finishCreatingObject()
        elif isinstance(self.creatingObject, cvgeom.imageline):         # line or spline, it gets points the same way
            i = self.addPointToObject(self.creatingObject, x, y)
        else:
            # check if the user clicked on a point, object, or object point
            o = self.checkXY(x, y)
            if o is not None:
                self.clickedOnObject = True
            else:
                self.clickedOnObject = False
        self.update()
    
    def leftClickUp(self, event, x, y, flags, param):
        """
        Process left click up events, which finish moves (recording the action
        for an undo/redo), and stops selection box drawing.
        """
        # record where we let off the mouse button
        self.clickUp = cvgeom.imagepoint(x, y)
        
        # if we were moving points
        if self.isMovingObjects():
            # we're done with the move, add the complete move to the action buffer so it can be undone
            d = cvgeom.imagepoint(x,y) - self.clickDown
            selObjs = self.selectedObjects()
            selObjPoints = None
            if len(selObjs) == 0:
                selObjPoints = self.selectedObjectPoints()
            if selObjPoints is not None and len(selObjPoints) > 0:
                a = ObjectMover(selObjPoints, d)
            else:
                a = ObjectMover(self.selectedPoints(), d)
                a.addObjects(selObjs)
            self.did(a)
        # if we weren't moving points, check where we clicked up to see if we need to select something
        o = self.checkXY(x, y)
        cdo = self.checkXY(self.clickDown.x, self.clickDown.y)
        if o is not None and o == cdo:
            # if we clicked up and down within clickRadius of the same object, select it and say we are moving objects
            # clear selected first if no modifiers
            if self.gotModifier(flags) is None:
                self.clearSelected()
                o.select()
                self.clickedOnObject = True
            else:
                # otherwise toggle selected
                o.toggleSelected()
        elif o is None and cdo is None and self.selectBox is None:
            # otherwise reset the clicked state
            self.clearSelected()
            self.clickedOnObject = False
            self.lastClickDown = self.clickDown
            self.clickDown = cvgeom.imagepoint()
        
        # reset the select box
        self.selectBox = None
        
        # refresh the frame
        self.update()
    
    def doubleClick(self, event, x, y, flags, param):
        """Add a new point or insert a new point into an existing object."""
        if self.creatingObject is None:
            # first check where we clicked
            o = self.checkXY(x, y)
            if o is None:
                # if we don't get anything, add a new point
                self.addPoint(x, y)
            elif isinstance(o, cvgeom.MultiPointObject):
                # if we clicked on a MultiPointObject, insert the point
                indx = o.getInsertIndex(x, y, clickRadius=self.clickRadius)
                a = PointInserter(o, x, y, indx)
                self.do(a)
            
        self.update()
    
    #### Methods for running the program ###
    def isAlive(self):
        return self.alive.value
    
    def getAliveSignal(self):
        return self.alive
    
    def run(self):
        """Show the interactive interface."""
        self.alive.value = True
        
        # open the image first if necessary
        if not self.isOpened():
            self.open()
        
        if self.recordFromStart:
            self.saveFrames = True
            self.openVideoWriter()
        
        while self.isAlive():
            # autosave, if turned on
            if self.autosaveInterval is not None and time.time() - self.lastAutosave >= self.autosaveInterval:
                self.saveConfig()
                self.lastAutosave = time.time()
            
            # showing the image and read keys
            if not self.isPaused:
                self.clear()
                self.drawFrame()
                self.showFrame()
            self.readKey(cvWaitKey(self.iFPS))
        
        if self.autosaveInterval is not None:
            # if autosave is turned on, assume we should save before closing
            print "Saving points to file..."
            self.saveConfig()
    
    def runInThread(self, useProcess=True):
        """Run in a separate thread or process."""
        ps = 'thread'
        if useProcess:
            ps = 'process'
            self.thread = multiprocessing.Process(target=self.run)
        else:
            self.thread = threading.Thread(target=self.run)
        print "{} running in separate {}...".format(self, ps)
        self.thread.start()
        
    def cleanup(self):
        """
        User-implementable cleanup function called by quit() after windows
        are destroyed.
        """
        pass
        
    def quit(self, key=None):
        """Quit the application."""
        self.alive.value = False
        cv2.destroyWindow(self.windowName)
        self.cleanup()
    
    def isOpened(self):
        return self.image is not None
        
    def open(self):
        self.openImage()
        self.openMaskImage()
        self.openGUI()
        
    def openGUI(self):
        self.loadConfig()
        self.openWindow()
        
    def close(self):
        self.quit()
    
    def openImage(self):
        """Read the image file into an array."""
        print "Opening image {}".format(self.filename)
        self.image = cv2.imread(self.filename)
        self.imgHeight, self.imgWidth, self.imgDepth = self.image.shape
        self.img = self.image.copy()
    
    def openMaskImage(self):
        """Read the mask image file into an array."""
        if self.maskFilename is not None:
            self.mask = cv2.imread(self.maskFilename, 0)
    
    def openWindow(self, windowName=None, mouseCallback=None, windowType=cv2.WINDOW_NORMAL):
        """Open the video player window."""
        # create the window
        # NOTE: window name is window handle
        if windowName is None:
            # if we didn't get a window name, this is the main window
            self.mainWindow = cvWindow(self.windowName, mouseCallback=self.readMouse, windowType=windowType)
        else:
            # otherwise, record the new window in our list of extra windows
            self.extraWindows[windowName] = cvWindow(windowName, mouseCallback=mouseCallback, windowType=windowType)
    
    def addTrackbar(self, trackbarName, windowName, value, maxValue, callbackFunction):
        trackbar = cvTrackbar(trackbarName, windowName, value, maxValue, callbackFunction)
        if windowName == self.windowName:
            # if main window, add trackbar info to mainWindow
            self.mainWindow.addTrackbar(trackbar)
        else:
            # otherwise find the window object and add it to that
            # this will break if the window hasn't been created (intended, since trackbar with no window cannot happen)
            self.extraWindows[windowName].addTrackbar(trackbar)
        return trackbar
    
    def pause(self, key=None):
        """Toggle play/pause the player."""
        self.isPaused = not self.isPaused
    
    def setPlaybackSpeed(self, newFPS):
        """Change the playback speed to a different framerate."""
        self.fps = float(newFPS) if newFPS > 0 else 1
        self.iFPS = int(round((1/self.fps)*1000))
    
    #### Methods for handling undo/redo events
    def printUndoBuffers(self, key=None):
        """Print the undo/redo buffers (for debugging purposes)."""
        print 'actionBuffer:'
        print self.actionBuffer
        print 'undoneActions:'
        print self.undoneActions
    
    def do(self, a):
        """Do an action and put it in the action buffer so it can be undone."""
        if isinstance(a, action):
            a.do()
        else:
            print "Do: action '{}' is not implemented correctly!!".format(a)
        self.actionBuffer.append(a)
        
        # clear the redo buffer
        self.undoneActions = []
        
        # update to reflect changes
        self.update()
    
    def did(self, a):
        """
        Inform the object that an action has been performed, so it can be added
        to the action buffer. Useful if you want to draw something out as it is done
        in real time, but have undo/redo actions happen instantly.
        """
        self.actionBuffer.append(a)
        self.update()
    
    def undo(self, key=None):
        """Undo actions in the action buffer."""
        if len(self.actionBuffer) > 0:
            a = self.actionBuffer.pop()
            if isinstance(a, action):
                a.undo()
                self.undoneActions.append(a)
            else:
                print "Undo: action '{}' is not implemented correctly!!".format(a)
                self.actionBuffer.append(a)
        
        # update to reflect changes
        self.update()
    
    def redo(self, key=None):
        """Redo actions in the action buffer."""
        if len(self.undoneActions) > 0:
            a = self.undoneActions.pop()
            if isinstance(a, action):
                a.do()
                self.actionBuffer.append(a)
            else:
                print "Redo: action '{}' is not implemented correctly!!".format(a)
                self.undoneActions.append(a)
        
        # update to reflect changes
        self.update()
    
    def forget(self, key=None):
        """Remove a single action from the undo buffer, but forget about it forever."""
        if len(self.undoneActions) > 0:
            self.actionBuffer.pop()
    
    def clearActions(self, key=None):
        """Clear the action buffer and undone actions."""
        self.actionBuffer = []
        self.undoneActions = []
    
    def forgetCreatingObjectPoints(self):
        # before we add the region creation to the action buffer, forget that we added each of the points individually
        for p in self.creatingObject.points.values():
            self.forget()
    
    #### Methods for loading/saving points/objects from/to text config files ###
    def loadConfig(self):
        if self.configFilename is not None:
            self.pointConfig = ConfigObj(self.configFilename)
            if self.configSection not in self.pointConfig:
                firstSection = self.pointConfig.sections[0]
                print("Section {} not in file {}. Using first available section {} ...".format(self.configSection, self.configFilename, firstSection))
                self.configSection = firstSection
            if self.configSection in self.pointConfig:
                print "Loading points and regions from file {} section {}".format(self.configFilename, self.configSection)
                imageDict = self.pointConfig[self.configSection]
                try:
                    self.points, self.objects = self.loadDict(imageDict)
                except:
                    print traceback.format_exc()
                    print "An error was encountered while loading points from file {}. Please check the formatting.".format(self.configFilename)
        
    def saveConfig(self):
        """Save points and objects to the config file."""
        if self.configFilename is not None:
            print "Saving points and regions to file {} section {}".format(self.configFilename, self.configSection)
            imageDict = self.saveDict()
            #print imageDict
            if self.pointConfig is None:
                self.pointConfig = ConfigObj(self.configFilename)
            self.pointConfig[self.configSection] = imageDict
            self.pointConfig.write()
            print "Changes saved!"
        
    @classmethod
    def loadDict(cls, imageDict):
        points = cvgeom.ObjectCollection()
        objects = cvgeom.ObjectCollection()
        if '_points' in imageDict:
            print "Loading {} points...".format(len(imageDict['_points']))
            for i, p in imageDict['_points'].iteritems():
                indx = None
                for typ in [int, float]:
                    try:
                        indx = typ(i)
                        break
                    except ValueError:
                        pass
                    if indx is None:
                        indx = i
                points[indx] = cvgeom.imagepoint(int(p[0]), int(p[1]), index=indx, color='default')
                    
        print "Loading {} objects".format(len(imageDict)-1)
        for objindx, objDict in imageDict.iteritems():
            if objindx == '_points':
                continue
            objname = objDict['name']
            objcolor = objDict['color']
            objtype = objDict['type']
            if hasattr(cvgeom, objtype):
                objconstr = getattr(cvgeom, objtype)
                obj = objconstr(index=objindx, name=objname, color=objcolor)
                obj.loadPointDict(objDict['_points'])
                objects[objindx] = obj
            else:
                print "Cannot construct object '{}' (name: '{}') of type '{}'".format(objindx, objname, objtype)
        return points, objects
        
    def saveDict(self):
        imageDict = {}
        
        # save the points to the _points section
        print "Saving {} points to file {} section {}".format(len(self.points), self.configFilename, self.configSection)
        imageDict['_points'] = {}
        for i, p in self.points.iteritems():
            imageDict['_points'][str(i)] = p.asList()
        
        # then add the objects
        print "Saving {} objects to file {} section {}".format(len(self.objects), self.configFilename, self.configSection)
        for n, o in self.objects.iteritems():
            # add each object to its own section
            imageDict.update(o.getObjectDict())
        return imageDict
    
    def clear(self):
        """Clear everything from the image."""
        if self.img is not None:
            self.img = self.image.copy()
        
    def showFrame(self):
        """Show the image in the player."""
        if self.img is not None:
            # save the frame if we are recording
            if self.saveFrames:
                self.saveFrame()
            # show it in the player
            cv2.imshow(self.windowName, self.img)
    
    def update(self):
        """Update everything in the GUI object to reflect a change."""
        self.clear()
        self.drawFrame()
        self.showFrame()
    
    def toggleCoordinates(self):
        """Toggle the printing of point coordinates on the image."""
        self.showCoordinates = not self.showCoordinates
        onOff = 'on' if self.showCoordinates else 'off'
        print "Turning coordinate printing {}".format(onOff)
        self.update()
    
    def toggleObjectText(self):
        """Toggle the printing of object text (index/name) on the image."""
        self.showObjectText = not self.showObjectText
        onOff = 'on' if self.showObjectText else 'off'
        print "Turning object text printing {}".format(onOff)
        self.update()
    
    #### Methods for manipulating points/objects in the window ###
    def printObjects(self):
        """Print the points and objects lists to the console (for debugging purposes)."""
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            print "{}: {}".format(objListName, len(objList))
            for i, o in objList.iteritems():
                print "{}: {}".format(i,o)
    
    def printSelectedObjects(self):
        """Print the selected points and objects lists to the console (for debugging purposes)."""
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            sobjs = objList.selectedObjects()
            print "Selected {}: {}".format(objListName, len(sobjs))
            for i, o in sobjs.iteritems():
                print "{}: {}".format(i,o)
    
    #   ### object creation ###
    def createRegion(self):
        """Create a region (closed polygon) by clicking vertices."""
        i = self.objects.getNextIndex()
        print "Starting region {}".format(i)
        self.creatingObject = cvgeom.imageregion(index=i)
        self.creatingObject.select()
        self.update()
        
    def createBox(self):
        """Create a rectangle by clicking two corner points."""
        i = self.objects.getNextIndex()
        print "Starting box {}".format(i)
        self.creatingObject = cvgeom.imagebox(index=i)
        self.creatingObject.select()
        self.update()
        
    def createLine(self):
        """Start creating a polyline."""
        i = self.objects.getNextIndex()
        print "Starting line {}".format(i)
        self.creatingObject = cvgeom.imageline(index=i)
        self.creatingObject.select()
        self.update()
        
    def createDashedLine(self):
        """Start creating a dashed line."""
        i = self.objects.getNextIndex()
        print "Starting dashed line {}".format(i)
        self.creatingObject = cvgeom.dashedline(index=i)
        self.creatingObject.select()
        self.update()
        
    def createSpline(self):
        """Start creating a spline."""
        i = self.objects.getNextIndex()
        print "Starting spline {}".format(i)
        self.creatingObject = cvgeom.imagespline(index=i)
        self.creatingObject.select()
        self.update()
    
    def groupSelectedPoints(self, key=None):
        """Group the selected points into a cvgeom.MultiPointObject"""
        self.groupPoints(self.selectedPoints())
    
    def groupPoints(self, pointList):
        """Group the list of points into a cvgeom.MultiPointObject."""
        if len(pointList) > 0:
            i = self.objects.getNextIndex()
            print "Grouping {} points into object {}".format(len(pointList), i)
            a = PointGrouper(self.objects, self.points, pointList)
            self.do(a)
    
    def addPoint(self, x, y):
        i = self.points.getNextIndex()
        p = cvgeom.imagepoint(x, y, index=i, color='default')
        a = ObjectAdder(self.points, p)
        self.do(a)
    
    def addPointToObject(self, obj, x, y):
        if obj is not None:
            i = obj.getNextIndex()
            p = cvgeom.imagepoint(x, y, index=i, color=obj.color)
            a = ObjectAdder(obj.points, p)
            self.do(a)
        
    def addPointToRegion(self, x, y):
        if self.creatingObject is not None:
            # if the region has at least 3 points, check if this click was on the first point
            if len(self.creatingObject.points) >= 3:
                d = self.creatingObject.points[self.creatingObject.getFirstIndex()].distance(cvgeom.imagepoint(x, y))
                if d <= self.clickRadius:
                    # if it was, finish the object
                    self.finishCreatingObject()
            if self.creatingObject is not None:
                self.addPointToObject(self.creatingObject, x, y)
    
    def enterFinish(self, key=None):
        """
        Finish whatever multi-step action currently being performed (e.g.
        creating a polygon, line, etc.).
        """
        if self.creatingObject is not None:
            # if we are creating an object, finish it
            print "Finishing {}".format(self.creatingObject.getObjStr())
            self.finishCreatingObject()
    
    def finishCreatingObject(self):
        self.forgetCreatingObjectPoints()
        self.creatingObject.deselect()              # make sure to deselect the region
        a = ObjectAdder(self.objects, self.creatingObject)
        self.do(a)
        self.creatingObject = None
    
    def escapeCancel(self, key=None):
        """
        Cancel whatever multi-step action currently being performed (e.g.
        creating a polygon, line, etc.).
        """
        if self.creatingObject is not None:
            # if we are creating a polygon, finish it
            print "Cancelling {}".format(self.creatingObject.getObjStr())
            self.forgetCreatingObjectPoints()
            self.creatingObject = None
        self.update()
        
    def duplicate(self):
        """Duplicate the selected PlaneObject(s)."""
        for p in self.selectedPoints().values():
            print "Duplicating point {}".format(p)
            self.addPoint(p.x, p.y)
        for o in self.selectedObjects().values():
            self.duplicateObject(o)
    
    def duplicateObject(self, o):
        """Duplicate the selected MultiPointObject(s)."""
        i = self.objects.getNextIndex()
        print "Duplicating {} {}".format(o.__class__.__name__, o)
        
        # duplicate the object, then change the index and name
        newObj = deepcopy(o)
        newObj.setIndex(i)
        newObj.setName(i)
        
        # move the object a bit so it can be selected independently of the original
        d = cvgeom.imagepoint(10,10)
        newObj.move(d)
        
        # deselect the original object
        o.deselect()
        
        # add the object
        a = ObjectAdder(self.objects, newObj)
        self.do(a)
        self.creatingObject = None
    
    #   ### object selection ###
    def addToSelectPool(self, objListName, objList):
        """
        Add another ObjectCollection to the pool of selectable objects,
        which by default includes points and objects.
        """
        self.selectableObjects.append(objListName)
    
    def checkXY(self, x, y):
        """Returns the point or polygon within clickRadius of (x,y) (if there is one)."""
        cp = cvgeom.imagepoint(x,y)
        
        # allow user to use this point
        self.userCheckXY(x, y)
        
        for objListName in self.selectableObjects:
            # get the object closest to our click point
            objList = getattr(self, objListName)
            i = objList.getClosestObject(cp)
            if i is not None:
                o = objList[i]
                d = o.distance(cp)
                if d is not None and d <= self.clickRadius:
                    # if it is within clickRadius
                    if isinstance(o, cvgeom.MultiPointObject):
                        # if it's a MultiPointObject, check if we clicked on one of its points
                        op = o.clickedOnPoint(cp, self.clickRadius)
                        if op is not None:
                            return op
                    # otherwise just return the object
                    return o
    
    def userCheckXY(self, x, y):
        """
        User-implementable function to check points clicked by the user without
        interfering with normal operation. By default this function does nothing.
        """
        pass
    
    def selectedFromObjList(self, objListName):
        if hasattr(self, objListName):
            objList = getattr(self, objListName)
            if isinstance(objList, cvgeom.ObjectCollection):
                return objList.selectedObjects()
    
    def selectedPoints(self):
        """Get a dict with the selected points."""
        return self.selectedFromObjList('points')
        #return {i: p for i, p in self.points.iteritems() if p.selected}
        
    def selectedObjects(self):
        """Get a dict with the selected objects."""
        return self.selectedFromObjList('objects')
        #return {i: o for i, o in self.objects.iteritems() if o.selected}
        
    def selectedObjectPoints(self):
        """Get a dict with the selected points of all objects."""
        selectedPoints = cvgeom.ObjectCollection()
        for o in self.objects.values():
            selectedPoints = o.selectedPoints()
            if len(selectedPoints) > 0:
                break
        return selectedPoints
        
    def clearSelected(self):
        """Clear all selected points and regions."""
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            for o in objList.values():
                o.deselect()
        self.update()
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        selp = self.selectedPoints()
        a = None
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            if a is None:
                a = ObjectDeleter(objList, objList.selectedObjects())
            else:
                a.addObjects(objList, objList.selectedObjects())
        if a is not None:
            self.do(a)
        
    def selectAll(self):
        """Select all points and regions in the image."""
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            for o in objList.values():
                o.select()
        self.update()
        
    def updateSelection(self):
        """
        Update the list of selected points to include everything inside the rectangle
        made by self.clickDown and self.mousePos.
        """
        self.selectBox = cvgeom.box(self.clickDown, self.mousePos)
        
        # add any objects that are completely selected
        for objListName in self.selectableObjects:
            objList = getattr(self, objListName)
            for o in objList.values():
                so = o.asShapely()
                if so is not None and self.selectBox.contains(so):
                    o.select()
        self.update()
    
    #   ### moving objects ###
    def moveObjects(self, d):
        """Move all selected regions by (d.x,d.y)."""
        o = None
        for o in self.objects.values():
            if o.selected:
                o.move(d)
            else:
                # look at all the points and move any that are selected
                for p in o.points.values():
                    if p.selected:
                        p.move(d)
        if isinstance(o, cvgeom.imagebox):
            o.refreshPoints()
        
    def movePoints(self, d):
        """Move all selected points by (d.x,d.y)."""
        #for p in self.selectedPoints.values():
        for p in self.points.values():
            if p.selected:
                p.move(d)
    
    def isMovingObjects(self):
        """Whether or not we are currently moving objects (points or regions)."""
        if self.clickedOnObject and not self.clickDown.isNone():
            for p in self.points.values():
                if p.selected:
                    return True
            for o in self.objects.values():
                if o.selected:
                    return True
                for p in o.points.values():
                    if p.selected:
                        return True
        return False
        #return len(self.selectedPoints) > 0 and self.clickedOnObject
    
    def moveAll(self, d):
        """Move all selected objects and points by (d.x,d.y)."""
        selObjs = self.selectedObjects()
        selObjPoints = None
        a = None
        if len(selObjs) == 0:
            selObjPoints = self.selectedObjectPoints()
        if selObjPoints is not None and len(selObjPoints) > 0:
            a = ObjectMover(selObjPoints, d)
        else:
            a = ObjectMover(self.selectedPoints(), d)
            a.addObjects(selObjs)
        if a is not None:
            self.do(a)
        
    def leftOne(self):
        """Move the selected objects left by one pixel."""
        d = cvgeom.imagepoint(-1,0)
        self.moveAll(d)
    
    def rightOne(self):
        """Move the selected objects right by one pixel."""
        d = cvgeom.imagepoint(1,0)
        self.moveAll(d)
    
    def upOne(self):
        """Move the selected objects up by one pixel."""
        d = cvgeom.imagepoint(0,-1)
        self.moveAll(d)
        
    def downOne(self):
        """Move the selected objects up by one pixel."""
        d = cvgeom.imagepoint(0,1)
        self.moveAll(d)
    
    #   ### changing object properties ###
    def hideAllFromUserText(self):
        """Hide all objects in the list specified by the user."""
        objListName = self.getUserText()
        if objListName is not None and objListName in self.selectableObjects:
            print "Hiding all cvgeom objects in list {} ...".format(objListName)
            self.hideAllInObjList(getattr(self, objListName))
        else:
            print "List '{}' is not recognized!".format(objListName)
        self.update()
    
    def unhideAllFromUserText(self):
        """Unhide all objects in the list specified by the user."""
        objListName = self.getUserText()
        if objListName is not None and objListName in self.selectableObjects:
            print "Unhiding all cvgeom objects in list {} ...".format(objListName)
            self.unhideAllInObjList(getattr(self, objListName))
        else:
            print "List '{}' is not recognized!".format(objListName)
        self.update()
    
    def toggleHideAllFromUserText(self):
        """Toggle hide on/off for all objects in the list specified by the user."""
        objListName = self.getUserText()
        if objListName is not None and objListName in self.selectableObjects:
            print "Toggling hide on all cvgeom objects in list {} ...".format(objListName)
            self.toggleHideObjList(getattr(self, objListName))
        else:
            print "List '{}' is not recognized!".format(objListName)
        self.update()
    
    def hideAllInObjList(self, objList):
        """Hide all objects in the ObjectCollection provided."""
        for o in objList.values():
            o.hide()
        self.update()
    
    def hideAll(self):
        """Hide all cvgeom objects in the image."""
        print "Hiding all cvgeom objects ..."
        for objListName in self.selectableObjects:
            self.hideAllInObjList(getattr(self, objListName))
        self.update()
    
    def unhideAllInObjList(self, objList):
        """Unhide all objects in the ObjectCollection provided."""
        for o in objList.values():
            o.unhide()
        self.update()
        
    def unhideAll(self):
        """Unhide all cvgeom objects in the image."""
        print "Unhiding all cvgeom objects ..."
        for objListName in self.selectableObjects:
            self.unhideAllInObjList(getattr(self, objListName))
        self.update()
    
    def toggleHideObjList(self, objList, printObjects=False):
        """Toggle hide/unhide all cvgeom objects in the provided ObjectCollection."""
        for o in objList.values():
            if printObjects:
                print "Toggling hide on object {} ...".format(o.getObjStr())
            o.toggleHidden()
        self.update()
        
    def toggleHideSelected(self):
        """Toggle hide/unhide all selected cvgeom objects. Use unhideAll if you lose an object."""
        for objListName in self.selectableObjects:
            self.toggleHideObjList(self.selectedFromObjList(objListName), printObjects=True)
        self.update()
    
    # TODO EDIT THESE TO GO THROUGH selectableObjects like checkXY and others
    def renameObject(self, o, objList):
        print "Renaming {}".format(o.getObjStr())
        name = self.getUserText()
        if name is not None:
            # remove the object under the old key and replace it with the name as the key
            a = ObjectRenamer(objList, o, name)
            self.do(a)
            print "Renamed to {}".format(o.getObjStr())
        else:
            print "Rename cancelled..."
    
    def renameSelectedObject(self, key=None):
        """(Re)name the selected object."""
        for p in self.points.values():
            if p.selected:
                self.renameObject(p, self.points)
                return
        for o in self.objects.values():
            if o.selected:
                self.renameObject(o, self.objects)
                return
        
    def changeObjectColor(self, o):
        """Take input from the user to change an object's color."""
        print "Changing color of {}".format(o.getObjStr())
        color = self.getUserText()
        if color is not None:
            a = ObjectAttributeChanger(o, 'setColor', 'color', color)
            self.do(a)
            print "Changed color of {} to {}".format(o.getObjStr(), color)
        else:
            print "Color change cancelled..."
        
    def changeSelectedObjectColor(self, key=None):
        """Change the color of the selected object."""
        for p in self.points.values():
            if p.selected:
                self.changeObjectColor(p)
                return
        for o in self.objects.values():
            if o.selected:
                self.changeObjectColor(o)
                return
        
    def changeSelectedObjectIndex(self, key=None):
        """Change the index of the selected object."""
        for o in self.objects.values():
            if o.selected:
                self.changeObjectIndex(o)
                return
        
    def changeObjectIndex(self, o):
        """Take input from the user to change an object's color."""
        print "Changing index of {}".format(o.getObjStr())
        newIndex = self.getUserText()
        if newIndex is not None:
            # make sure we're not going to replace another object
            if newIndex in self.objects:
                print "Index {} is already taken! Doing nothing...".format(newIndex)
                return
            
            # perform the action
            a = ObjectIndexChanger(self.objects, o, newIndex)
            self.do(a)
            print "Changed index of {} to {}".format(o.getObjStr(), newIndex)
        else:
            print "Index change cancelled..."
    
    #### Methods for writing frames to a video or image file ###
    def toggleRecord(self, key=None):
        """Toggle recording of frames to video."""
        self.saveFrames = not self.saveFrames
        if self.saveFrames:
            # starting a new recording
            self.openVideoWriter(self.timestamp)
        elif self.videoWriter is not None:
            # stopping recording - close the video writer
            self.videoWriter.release()
            print "Video file '{}' closed. Recording has stopped.".format(self.outputVideoFile)
        
    def openVideoWriter(self, atTime=None):
        """Create a video writer object to record frames."""
        atTime = time.time() if atTime is None else atTime          # just use the current time if no data yet
        if self.outputVideoFile is None:
            outputVideoFile = time.strftime("{}_{}_%d%b%Y~%H%M%S.avi".format(self.__class__.__name__, self.fnameNoExt), time.localtime(atTime))
        else:
            outputVideoFile = getUniqueFilename(self.outputVideoFile)
        frameHeight = self.img.shape[0]
        frameWidth = self.img.shape[1]
        self.videoWriter = cv2.VideoWriter(outputVideoFile, self.videoFourCC, self.fps, (frameWidth, frameHeight))
        if self.videoWriter.isOpened():
            print "Started recording to file '{}' ...".format(outputVideoFile)
        else:
            print "Could not open video file '{}' for writing !".format(outputVideoFile)
            self.saveFrames = False
    
    def saveFrame(self):
        if self.videoWriter is not None and self.videoWriter.isOpened():
            self.videoWriter.write(self.img)
    
    def saveFrameImage(self, outputFile=None, params=None, imgType='png'):
        """
        Save the current frame to an image file. If outputFile is not specified,
        a filename is generated automatically from the player name and current time.
        """
        if self.img is not None:
            outputFile = time.strftime("{}_%d%b%Y~%H%M%S.{}".format(self.fnameNoExt, imgType.strip('.'))) if outputFile is None else outputFile
            print "Saving current frame to image file {} ...".format(outputFile)
            cv2.imwrite(outputFile, self.img, params)
        else:
            print "No image to save! Make sure the image/video has been loaded correctly!"
            
    def saveFrameImageKB(self, key=None):
        """Save the current frame to an image file (keyboard binding)."""
        self.saveFrameImage()
    
    #### Methods for rendering and displaying graphics ###
    def applyMask(self):
        """Apply the mask to the current image, if there is one."""
        if self.mask is not None:
            self.img = cv2.bitwise_and(self.img, self.img, mask=self.mask)
    
    def drawText(self, text, x, y, fontSize=None, color='green', thickness=2, font=None):
        fontSize = self.textFontSize if fontSize is None else fontSize
        font = cvFONT_HERSHEY_PLAIN if font is None else font
        color = getColorCode(color, default='green')
        cv2.putText(self.img, str(text), (x,y), font, fontSize, color, thickness=thickness)
    
    def drawPoint(self, p, circle=True, crosshairs=True, pointIndex=None):
        """Draw the point on the image as a circle with crosshairs."""
        if not p.hidden:
            if circle:
                ct = 4*self.lineThickness if p.selected else self.lineThickness                 # highlight the circle if it is selected
                cv2.circle(self.img, p.asTuple(), self.clickRadius, p.color, thickness=ct)       # draw the circle
            
            if crosshairs:
                # draw the line from p.x-self.clickRadius to p.x+clickRadius
                p1x, p2x = p.x - self.clickRadius, p.x + self.clickRadius
                cv2.line(self.img, (p1x, p.y), (p2x, p.y), p.color, thickness=1)
                
                # draw the line from p.x-self.clickRadius to p.x+clickRadius
                p1y, p2y = p.y - self.clickRadius, p.y + self.clickRadius
                cv2.line(self.img, (p.x, p1y), (p.x, p2y), p.color, thickness=1)
            
            if self.showCoordinates:
                # draw the coordinates
                offset = 0
                if isinstance(p.index, int):            # shuffle text so it doesn't run together
                    offset = (p.index % 2) * 20
                self.drawText(p.asTuple(), p.x, p.y + 30 + offset, fontSize=round(self.textFontSize/2.0), color=p.color, thickness=1)
            
            # add the index of the point to the image
            pointIndex = p.showIndex if pointIndex is None else pointIndex
            if pointIndex:
                self.drawText(p.getIndex(), p.x, p.y, self.textFontSize, color=p.color, thickness=2)
        
    def drawBox(self, box, boxIndex=True):
        """Draw a cvgeom.imagebox instance on the image as a rectangle, and with a thicker
           line and points at the corners if it is selected."""
        dlt = 2*self.lineThickness
        lt = 4*dlt if box.selected else dlt
        pMin, pMax = box.pointsForDrawing()
        if pMin is not None and pMax is not None:
            cv2.rectangle(self.img, (pMin.x, pMin.y), (pMax.x, pMax.y), box.color, thickness=lt)
            if boxIndex and self.showObjectText:
                self.drawText(box.getIndex(), pMax.x, pMin.y, self.textFontSize, color=box.color, thickness=2)
        
        # add the points if selected
        for p in box.points.values():
            if box.selected or p.selected:
                self.drawPoint(p)
    
    def drawObject(self, obj):
        """
        Draw a cvgeom.MultiPointObject on the image as a linestring. If it is selected,
        draw it as a linestring with a thicker line and points drawn as selected points
        (which can be "grabbed").
        """
        if not obj.hidden:
            if isinstance(obj, cvgeom.imagebox):
                self.drawBox(obj)
            else:
                dlt = 2*self.lineThickness
                lt = 4*dlt if obj.selected else dlt
                isClosed = isinstance(obj, cvgeom.imageregion) and obj != self.creatingObject
                
                # draw the lines as polylines if it's a line or region
                drawAsLine = False
                if isinstance(obj, cvgeom.dashedline):
                    # draw line as a line segment between every other point and the next point
                    indxs = sorted(obj.points.keys())
                    for i in range(1,len(indxs)):
                        if i % 2 == 1:
                            p1 = obj.points[i]
                            p2 = obj.points[i+1]
                            cv2.line(self.img, p1.asTuple(), p2.asTuple(), obj.color, thickness=lt)
                elif isinstance(obj, cvgeom.imageline) or isinstance(obj, cvgeom.imageregion):
                    drawAsLine = True
                    points = np.array([obj.pointsForDrawing()], dtype=np.int32)
                    cv2.polylines(self.img, points, isClosed, obj.color, thickness=lt)
                
                # and also draw the points if selected
                for p in obj.points.values():
                    if obj.selected or p.selected or not drawAsLine:
                        self.drawPoint(p)
                    
                # add the index and name at whatever the min point is
                if self.showObjectText and len(obj.points) > 0:
                    p = obj.points[obj.points.getFirstIndex()]
                    cv2.putText(self.img, obj.getNameStr(), p.asTuple(), cvFONT_HERSHEY_PLAIN, 4.0, obj.color, thickness=2)
    
    def drawFrameObjects(self):
        """
        Draw graphics corresponding to user input (e.g. points, objects, select rectangle,
        text being captured, etc.) on the image.
        """
        # and the box (if there is one)
        # draw the points on the frame
        for i, p in self.points.iteritems():
            self.drawPoint(p)
            
        # draw all the objects
        for i, o in self.objects.iteritems():
            self.drawObject(o)
        
        # and the object we're drawing, if it exists
        if self.creatingObject is not None:
            self.drawObject(self.creatingObject)
            
        # add the select box if it exists
        if self.selectBox is not None:
            cv2.rectangle(self.img, self.clickDown.asTuple(), self.mousePos.asTuple(), cvColorCodes['blue'], thickness=1)
        
        # add any user text to the lower left corner of the window as it is typed in
        if self.userText is not None:
            self.drawText(':' + self.userText, 0, self.imgHeight-10)
    
    def calculateDelay(self):
        """
        Used when displaying time-series data. If the 'isRealtime' property is True,
        this method will calculate the time delay based on the current time and the
        time of the most recent data (via the 'timestamp' property).
        """
        if self.timestamp is not None:
            self.delay = time.time() - self.timestamp
        else:
            self.delay = None
    
    def drawTimeInfo(self):
        """
        Add a timestamp to the upper-left corner of the screen displaying either the
        time associated with the data being displayed, or the delay if realtime data
        is being displayed (as set via the isRealtime property). This method is called
        by the drawFrame method and will automatically draw the timestamp or delay
        if the 'timestamp' property is set to an Unix (Epoch) time value (i.e. the kind
        returned by time.time()).
        """
        if self.timestamp is not None and not self.hideTimestamp:
            timeStr = ""
            if self.isRealtime:
                self.calculateDelay()
                delay = 'calculating...' if self.delay is None else (str(round(self.delay, 2)) + 's')
                
                # draw the text on the image
                timeStr = "Delay: {}".format(delay)
            else:
                # if we're playing historical data, show the time of the most recent data
                timeStr = time.strftime("%m/%d/%Y at %H:%M:%S",time.localtime(self.timestamp))
                timeStr += str(round(self.timestamp-int(self.timestamp),3))[1:]
            self.drawText(timeStr, 10, 20, fontSize=2, color='green', thickness=2)
    
    def drawExtra(self):
        """
        Draw any additional graphics on the image/frame. This method is provided for users
        so they can add graphics to the image without having to replicate the functionality
        of our drawFrame method (unless they want to). By default this method does nothing.
        """
        self.hideTimestamp = True
        self.timestamp = time.time()            # this lets us make a filename for recording video but allow children to override it
    
    def drawFrame(self):
        """Apply the mask, draw points, selectedPoints, and the selectBox on the frame."""
        self.applyMask()
        self.drawFrameObjects()
        self.drawExtra()
        self.drawTimeInfo()
    
class cvPlayer(cvGUI):
    """
    A class for playing a video using OpenCV's highgui features. Uses the cvGUI class
    to handle keyboard and mouse input to the window. To create a player for a
    particular purpose, create a new class based on the cvPlayer class and override
    any methods you would like to change. Then define any functions you need to handle
    keyboard/mouse input and set a keyboard/mouse binding by adding an entry to the
    keyBindings or mouseBindings dictionaries in the form:
        {<key /mouse event code>: 'functionName'}
    These are inherited from the cvGUI class, which binds the key/mouse codes to
    the appropriate method.
    NOTE:
    + A method for a key event must accept they key code as its only argument.
    + A method for a mouse event must accept 5 arguments: event, x, y, flags, param
    
    The cvPlayer class adds interactive video playing capabilities to the cvGUI
    class, using an OpenCV VideoCapture object to read a video file and play it
    in a window with a trackbar. The position of the video can be changed using
    the trackbar and also Ctrl+Left/Right.
    """
    def __init__(self, videoFilename, **kwargs):
        # construct cvGUI object
        super(cvPlayer, self).__init__(filename=videoFilename, **kwargs)
        
        # video-specific properties
        self.videoFilename = videoFilename
        self.video = None
        self.vidWidth = None
        self.vidHeight = None
        self.nFrames = None
        self.fps = None
        self.iFPS = None
        self.posAviRatio = 0
        self.posFrames = 0
        self.posMsec = 0
        self.frameOK = True
        self.isPaused = False
        self.video = None
        self.lastFrameImage = None
        self.frameTrackbar = None
        self.movingObjects = cvgeom.ObjectCollection()
        self.addToSelectPool('movingObjects', self.movingObjects)
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        
        # default bindings:
        self.addKeyBindings(['f'], 'advanceOne')
        self.addKeyBindings(['Ctrl  + B'], 'beginning')         # Ctrl + B - skip to beginning of video
        self.addKeyBindings(['Ctrl  + G'], 'jumpToFrameKB')     # Ctrl + G - read frame number from user and jump there
        
    def open(self):
        """Open the video."""
        # open a window (which also sets up to read keys and mouse clicks) and the video (which also sets up the trackbar)
        self.openMaskImage()
        self.openGUI()
        self.openVideo()
        
    def isOpened(self):
        if hasattr(self, 'video') and self.video is not None:
            return self.video.isOpened()
        else:
            return False
    
    def openVideo(self):
        try:
            # make sure we can open the file (VideoCapture doesn't give useful errors,
            #  probably because it's a C++ object...
            with open(self.videoFilename, 'rb') as tmpvid:
                pass
            
            # open the video capture object
            self.video = cv2.VideoCapture(self.videoFilename)
            
            # get information about the video
            self.vidWidth = int(self.video.get(cvCAP_PROP_FRAME_WIDTH))
            self.vidHeight = int(self.video.get(cvCAP_PROP_FRAME_HEIGHT))
            self.nFrames = int(self.video.get(cvCAP_PROP_FRAME_COUNT))
            self.fps = float(self.video.get(cvCAP_PROP_FPS))
            self.iFPS = int(round((1/self.fps)*1000))
            
            # set up the frame trackbar, going from 0 to nFrames
            self.frameTrackbar = self.addTrackbar('Frame', self.windowName, self.posFrames, self.nFrames, self.jumpToFrame)
        except:
            print traceback.format_exc()
            print "Error encountered when opening video file '{}' !\n Check that the file exists and that you have the permissions to read it.\n If you continue to experience this error, you may be missing the FFMPEG\n library files, which requires recompiling OpenCV to fix.".format(self.videoFilename)
            sys.exit(1)
        
    def getVideoPosFrames(self):
        """Get the current position in the video in frames."""
        self.updateVideoPos()
        return self.posFrames

    def updateVideoPos(self):
        """Update values containing current position of the video player in %, frame #, and msec."""
        self.posAviRatio = float(self.video.get(cvCAP_PROP_POS_AVI_RATIO))
        self.posFrames = int(self.video.get(cvCAP_PROP_POS_FRAMES))
        self.posMsec = int(self.video.get(cvCAP_PROP_POS_MSEC))
        #print "posFrames: {}, posMsec: {}, posAviRatio: {}".format(self.posFrames, self.posMsec, self.posAviRatio)
        
    def beginning(self):
        self.video.set(cvCAP_PROP_POS_FRAMES, 0)
        self.readFrame()
        self.drawFrame()
    
    def jumpToFrameKB(self, key=None):
        """Jump to a user-specified frame (keyboard binding)."""
        fn = self.getUserText(dtype=int)
        if isinstance(fn, int):
            if fn >= 0 and fn <= self.nFrames:
                print "Jumping to frame {} ...".format(fn)
                self.jumpToFrame(fn)
            else:
                print "Frame number {} is out of range [{},{}] !".format(fn, 0, self.nFrames)
        
    
    def jumpToFrame(self, tbPos):
        """
        Trackbar callback (i.e. video seek) function. Seeks forward or backward in the video
        corresponding to manipulation of the trackbar.
        """
        #if tbPos >= 60:
            #tbPos = tbPos + 12
           
        self.updateVideoPos()
        self.tbPos = tbPos
        if tbPos != self.posFrames:
            #m = tbPos % 30
            #print "posFrames: {}, tbPos: {}".format(self.posFrames, tbPos)
            #self.video.set(cvCAP_PROP_POS_FRAMES, tbPos)
            
            # TODO NOTE - this is a workaround until we can find a better way to deal with the frame skipping bug in OpenCV (see: http://code.opencv.org/issues/4081)
            if tbPos < self.posFrames:
                self.video.set(cvCAP_PROP_POS_FRAMES, 0)
                self.updateVideoPos()
            for i in range(0,self.tbPos-self.posFrames):
                self.frameOK, self.image = self.video.read()
                if self.frameOK:
                    self.img = self.image.copy()
                    
            #frameTime = 1000.0 * tbPos/self.fps
            #self.video.set(cvCAP_PROP_POS_MSEC, frameTime)
            self.readFrame()
            self.drawFrame()
            self.showFrame()
        
    def readFrame(self):
        """Read a frame from the video capture object."""
        if self.video.isOpened():
            if self.image is not None:
                self.lastFrameImage = self.image.copy()             # save the last frame before we replace it
            self.frameOK, self.image = self.video.read()
            if self.frameOK:
                self.img = self.image.copy()
                if self.imgHeight is None:
                    self.imgHeight, self.imgWidth, self.imgDepth = self.image.shape
                self.updateVideoPos()
                self.frameTrackbar.update(self.posFrames)
            return self.frameOK
        return self.video.isOpened()
    
    def advanceOne(self):
        """Move the video ahead a single frame."""
        self.readFrame()
        self.drawFrame()
        self.showFrame()
    
    def drawMovingObjects(self):
        for mo in self.movingObjects.values():
            if isinstance(mo, cvgeom.PlaneObjectTrajectory):
                mo.setiNow(self.posFrames)
                if not mo.hidden:
                    o = mo.getObjectAtInstant(self.posFrames)
                    if o is not None:
                        self.drawObject(o)
    
    def drawFrame(self):
        """Apply the mask and draw points, selectedPoints, and the selectBox on the frame."""
        self.applyMask()
        self.drawFrameObjects()
        self.drawMovingObjects()
        self.drawExtra()
        self.drawTimeInfo()
    
    def run(self):
        """Alternate name for play (to match cvGUI class)."""
        self.play()
        
    def playInThread(self):
        self.runInThread()
        
    def play(self):
        """Play the video."""
        self.alive.value = True
        
        # open the video first if necessary
        if not self.isOpened():
            self.open()
        
        recordingStarted = False
        while self.isAlive():
            # keep showing frames and reading keys
            if not self.isPaused:
                self.frameOK = self.readFrame()
                self.drawFrame()
                self.showFrame()
                
                if self.recordFromStart and not recordingStarted:
                    recordingStarted = True
                    self.saveFrames = True
                    self.openVideoWriter()
                
            self.readKey(cvWaitKey(self.iFPS))
    
    def pause(self, key=None):
        """Toggle play/pause the video."""
        self.isPaused = not self.isPaused
    
    def selectedFromObjList(self, objListName):
        """
        Method to get selected objects. Overridden from cvGUI to check if
        PlaneObjectTrajectory objects exist at the current instant.
        """
        selectedObjects = super(cvPlayer, self).selectedFromObjList(objListName)
        goodObjects = {}
        
        for i, o in selectedObjects.items():
            if isinstance(o, cvgeom.PlaneObjectTrajectory):
                # if PlaneObjectTrajectory, only add if it exists now
                # also don't let hidden objects through
                if o.existsAtInstant(self.posFrames) and not o.hidden:
                    goodObjects[i] = o
                else:
                    # if it doesn't exist, deselect it
                    o.deselect()
            else:
                # other objects just add
                goodObjects[i] = o
        return cvgeom.ObjectCollection(goodObjects)
    