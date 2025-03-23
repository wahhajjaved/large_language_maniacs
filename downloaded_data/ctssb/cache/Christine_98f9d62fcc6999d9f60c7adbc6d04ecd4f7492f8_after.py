#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the Christine project
#
# Copyright (c) 2006-2007 Marco Antonio Islas Cruz
#
# Christine is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Christine is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# @category  Multimedia
# @package   Christine
# @author    Marco Antonio Islas Cruz <markuz@islascruz.org>
# @author    Miguel Vazquez Gocobachi <demrit@gnu.org>
# @copyright 2006-2007 Christine Development Group
# @license   http://www.gnu.org/licenses/gpl.txt

import sys
import random
import thread
import time
import gtk
import gtk.gdk
import pygst; pygst.require('0.10')
import gst.interfaces
import gobject
#import dbus
#import dbus.service
from libchristine.Translator import *
from libchristine.GtkMisc import *
from libchristine.Library import *
from libchristine.Queue import *
from libchristine.Preferences import *
from libchristine.About import *
from libchristine.Player import *
from libchristine.Display import *
from libchristine.Plugins import *
from libchristine.Share import *
from libchristine.Preferences import *
from libchristine.Logger import *


#from dbus.mainloop.glib import DBusGMainLoop

#DBusGMainLoop(set_as_default=True)

#SYSTEM_BUS = dbus.SystemBus()
#SYSTEM_BUS = dbus.SessionBus()

try:
	import pynotify
	pynotify.Urgency(pynotify.URGENCY_NORMAL)
	pynotify.init('christine')
	version = pynotify.get_server_info()['version'].split('.')
	
	if (version < [0, 3, 6]):
		raise ImportError("server version is %d.%d.%d, 0.3.6 or major required" % version)

	PYNOTIFY = True
except ImportError:
	print 'no pynotify available'
	PYNOTIFY = False

if (gtk.gtk_version < (2, 10, 0)):
	print translate('Gtk+ 2.10 or better is required')
	sys.exit()

class Christine(GtkMisc):
	def __init__(self):
		"""
		Constructor, this method will init the gtk_misc parent class,
		initialize the gnome ui client, create the XML interface descriptor,
		initialize class variables and create some timeouts calls
		"""
		self.__Logger = ChristineLogger()
		self.__Logger.Log("Starting Christine")
		GtkMisc.__init__(self)
#		dbus.service.Object.__init__(self,SYSTEM_BUS,"/org/christine")

		self.__Share   = Share()
		self.__GConf   = Preferences()

		self.__XML = self.__Share.getTemplate('WindowCore')
		self.__XML.signal_autoconnect(self)

		self.__MenuItemSmallView = self.__XML['ViewSmallMenuItem']
		self.__VBoxCore          = self.__XML['VBoxCore']

		# Class variables
		self.__TextToSearch     = ""
		self.__ErrorStreamCount = 0
		self.__TimeTotal        = 0     # Nanosecs for audio/video file
		self.__LocationCount    = 0     # Count ns and jump if the file is not good
		self.__LastPlayed       = []
		self.__IterNatural      = None
		self.__IterCurrentPlaying = None # Temporal store for the current iter playing
		self.__ScaleMoving      = False
		self.__StatePlaying     = False
		self.__IsFullScreen     = False
		self.__ShowButtons      = False
		self.__IsHidden         = False
		self.__LastTags			= []

		# Creating the player and build the GUI interface
		self.__initPlayer()
		self.__buildInterface()

		if (self.__GConf.getBool('ui/show_in_notification_area')):
			self.__buildTrayIcon()

		self.__GConf.notifyAdd('/apps/christine/ui/show_in_notification_area',
				lambda cl,cnx,entry,widget: self.__TrayIcon.set_visible(entry.get_value().get_bool()))

		self.__Plugins = ChristinePlugins(self)
		gobject.timeout_add(500, self.checkTimeOnMedia)
	
	def __windowEvent(self,widget,event):
		'''
		Manage several event.
		@param gtk.Widget widget: The widget where the event happends
		@param gtk.gdk.Event event: The event.
		'''
		if event.type == gtk.gdk.SCROLL:
			value = self.__HScaleVolume.get_value()
			diff = 0.05
			if event.direction == gtk.gdk.SCROLL_DOWN:
				value -= diff
			elif event.direction == gtk.gdk.SCROLL_UP:
				value += diff
			if value < 0:
				value = 0.0
			elif  value >1:
				value = 1.0
			self.__HScaleVolume.set_value(value)
	def __initPlayer(self):
		"""
		Initialize the player and packs it into the HBoxPlayer
		"""
		self.__Player = Player()
		self.__HBoxPlayer = self.__XML['HBoxPlayer']
		self.__HBoxPlayer.pack_start(self.__Player, True, True, 0)
		self.__Player.bus.add_watch(self.__handlerMessage)

	def __buildInterface(self):
		"""
		This method calls most of the common used 
		interface descriptors (widgets) from self.__XML.
		Connects them to a callback (if needed) and 
		call some other methods to show/hide them.
		"""
		# Calling some widget descriptors with no callback connected "by hand"
		# This interface should not be private.
		#===================================================
		# Public Widgets
		self.MenuBar        = self.__XML['MenuBar'] 
		self.HBoxSearch    = self.__XML['HBoxSearch']
		self.EntrySearch    = self.__XML['EntrySearch'] 
		self.VBoxList       = self.__XML['VBoxList'] 
		#Private widgets
		self.__HPanedListsBox = self.__XML['HPanedListsBox']
		self.__VBoxTemporal   = self.__XML['VBoxTemporal']
		self.__ScrolledMusic  = self.__XML["ScrolledMusic"]
		self.__VBoxList       = self.__XML["VBoxList"]
		# Ends the call to widgets descriptors not connected by hadn

		# Gets window widget from glade template
		self.__Window = self.__XML['WindowCore']
		self.__Window.connect("destroy",gtk.main_quit)
		self.__Window.set_icon(self.__Share.getImageFromPix('logo'))
		self.__Window.connect("event",self.__windowEvent)

		# Gets play button and menu play item from glade template
		self.__PlayButton   = self.__XML['ToggleButtonPlay']
		self.__MenuItemPlay = self.__XML['MenuItemPlay']

		self.Menus = {}

		for i in ['media', 'edit', 'control', 'help']:
			self.Menus["%s" % i] = self.__XML["%s_menu" % i].get_submenu()
		
		# cdisplaybox is the display gtk-Box
		self.__HBoxCairoDisplay = self.__XML['HBoxCairoDisplay']
		
		# Create the display and attach it to the main window
		self.__Display = Display()
		self.__Display.connect('value-changed', self.onScaleChanged)
		self.__HBoxCairoDisplay.pack_start(self.__Display, True, True, 0)
		self.__Display.show_all()

		# Create the library by calling to libs_christine.library class
		self.__Library  = library()
		self.TreeView = self.__Library.tv

		# FIXME: check method if exist and change to standarization
		self.TreeView.connect('button-press-event', self.popupMenuHandlerEvent)
		self.TreeView.connect('key-press-event',    self.handlerKeyPress)
		self.TreeView.connect('row-activated',      self.itemActivated)
		self.TreeView.show()

		# Models in the library are assigned to class variables
		self.__LibraryModel       = self.__Library.tv.get_model()
		self.__LibraryFilterModel = self.__LibraryModel.get_model()
		self.__LibraryFilterModel.set_visible_func(self.filter)
		
		self.__LibraryNaturalModel = self.__LibraryFilterModel.get_model()
		self.__LibraryCurrentIter = self.__LibraryModel.get_iter_first()
		
		self.__ScrolledMusic = self.__XML['ScrolledMusic']
		self.__VBoxVideo = self.__XML['VBoxVideo']

		self.__ScrolledMusic.add(self.__Library.tv)
		#self.__VBoxCore.show_all()

		self.Queue         = queue()
		self.__ScrolledQueue = self.__XML['ScrolledQueue']

		self.Queue.treeview.connect('key-press-event', self.QueueHandlerKey)
		self.Queue.treeview.connect('row-activated',   self.itemActivated)

		self.__ScrolledQueue.add(self.Queue.treeview)
		gobject.timeout_add(500, self.__checkQueue)

		self.__ControlButton = self.__XML['control_button']

		self.__MenuItemShuffle = self.__XML['MenuItemShuffle']
		self.__MenuItemShuffle.set_active(self.__GConf.getBool('control/shuffle'))

		self.__MenuItemShuffle.connect('toggled', 
			lambda widget: self.__GConf.setValue('control/shuffle', 
			widget.get_active()))

		self.__GConf.notifyAdd('/apps/christine/control/shuffle', 
			self.__GConf.toggleWidget, 
			self.__MenuItemShuffle)

		self.__ControlRepeat = self.__XML['repeat']
		self.__ControlRepeat.set_active(self.__GConf.getBool('control/repeat'))
		
		self.__ControlRepeat.connect('toggled', 
			lambda widget: self.__GConf.setValue('control/repeat', 
			widget.get_active()))

		self.__GConf.notifyAdd('/apps/christine/control/repeat', 
			self.__GConf.toggleWidget, 
			self.__ControlRepeat)

		self.__BothSr = self.__XML['both_sr']
		self.__NoneSr = self.__XML['none_sr']
		
		self.__MenuItemVisualMode = self.__XML['MenuItemVisualMode']
		self.__MenuItemVisualMode.set_active(self.__GConf.getBool('ui/visualization'))

		self.visualModePlayer()

		self.__MenuItemSmallView.set_active(self.__GConf.getBool('ui/small_view'))
		self.toggleViewSmall(self.__MenuItemSmallView)

		self.__VBoxToolBox          = self.__XML['VBoxToolBox']
		self.__HBoxToolBoxContainer = self.__XML['HBoxToolBoxContainer']
		self.__HScaleVolume         = self.__XML['HScaleVolume']
		self.__HScaleVolume.connect("scroll-event",self.__windowEvent)

		
		volume = self.__GConf.getFloat('control/volume')

		self.__GConf.notifyAdd('/apps/christine/control/volume', self.__changePrefVolume)

		if (volume):
			self.__HScaleVolume.set_value(volume)
		else:
			self.__HScaleVolume.set_value(0.8)

		self.__HBoxToolBoxContainerMini = self.__HBoxToolBoxContainer
		self.jumpToPlaying(path = self.__GConf.getString('backend/last_played'))

		if ('-q' in sys.argv):
			sys.exit()

	def __buildTrayIcon(self):
		"""
		Show the TrayIcon 
		@see __TrayIcon_handlerEvent()
		@see __TrayIcon_activated()
		@return void

		"""
		self.__TrayIcon = gtk.StatusIcon()
		self.__TrayIcon.set_from_pixbuf(self.__Share.getImageFromPix('trayicon'))
		self.__TrayIcon.connect('popup-menu', self.__trayIconHandlerEvent)
		self.__TrayIcon.connect('activate',   self.__trayIconActivated)
		self.__TrayIcon.set_visible(self.__GConf.getBool('ui/show_in_notification_area'))
	
	def __trayIconHandlerEvent(self, widget, event, time):
		"""
		TrayIcon handler events
		@param gtk.Widget widget: the widget that emit the event.
		@param gtk.gdk.Event event: the event
		@param time: The time requested by the gadget.
		"""
		# If the event is a button press event and it was 
		# the third button then show a popup menu
		if (event == 3):
			XML = self.__Share.getTemplate('MenuTrayIcon')
			XML.signal_autoconnect(self)
			
			popup = XML['menu']
			popup.popup(None, None, None, 3, gtk.get_current_event_time())
			popup.show_all()

	def __trayIconActivated(self, status):
		"""
		This hide and then show the window, 
		intended when you want to show the window
		in your current workspace
		@param Bool status: The status of the trayicon
		"""
		if (self.__IsHidden == True):
			self.__Window.show()
		else:
			self.__Window.hide()

		self.__IsHidden = not self.__IsHidden

	def QueueHandlerKey(self, widget, event):
		"""
		Handler the key-press-event in the queue list
		@param  widget widget The widget that will be used
		@param  event  event  The event requested by the widget 
		"""
		if (event.keyval == 65535):
			selection     = self.Queue.treeview.get_selection()
			(model, iter) = selection.get_selected()

			if (iter is not None):
				name = model.get_value(iter, NAME)
				self.Queue.remove(iter)
				self.Queue.save()
	
	def popupMenuHandlerEvent(self, widget, event):
		"""
		handle the button-press-event in the library
		@param  widget  widget The widget that will be used
		@param  event   event  The event requested by the widget

		"""
		if (event.button == 3):
			XML = self.__Share.getTemplate('PopupMenu')
			XML.signal_autoconnect(self)

			popup = XML['menu']
			popup.popup(None, None, None, 3, gtk.get_current_event_time())
			popup.show_all()

	def deleteFileFromDisk(self, widget):
		"""
		Delete file from disk
		@param  widget widget The widget that will be used
		"""
		selection     = self.TreeView.get_selection()
		(model, iter) = selection.get_selected()
		iter          = self.__getIterNatural(iter)

		self.__Library.delete_from_disk(iter)

	def popupAddToQueue(self, widget):
		"""
		Add the selected item to the queue
		@param  widget widget The widget that will be used
		"""
		selection       = self.TreeView.get_selection()
		(model, iter,)  = selection.get_selected()
		file            = model.get_value(iter, PATH)

		self.Queue.add(file)
	
	def handlerKeyPress(self, treeview, event):
		"""
		Handle the key-press-event in the 
		library. 
		Current keys: Enter to activate the row
		and 'q' to send the selected song to the 
		queue
		@param  widget treeview
		@param  event  event

		"""
		if (event.keyval == 65535):
			self.removeFromLibrary()
		elif (event.keyval == 113):
			selection     = treeview.get_selection()
			(model, iter) = selection.get_selected()
			name          = model.get_value(iter, PATH)

			self.Queue.add(name)

	def removeFromLibrary(self, widget = None):
		"""
		Remove file from library
		@param  widget widget The widget that will be used
		"""
		selection     = self.TreeView.get_selection()
		(model, iter) = selection.get_selected()
		name,path     = model.get(iter, NAME, PATH)
		niter         = self.__getIterNatural(iter)
		if self.__GConf.getString("backend/last_played") == path:
			self.__GConf.setValue("backend/last_played","")
		self.__Library.remove(niter)
		self.__Library.save()

	# @return void
	def itemActivated(self,widget, path, iter):
		'''
		Set the selected item to the player location
		@param gtk.Widget widget: widget The widget that will be used
		@param gtk.TreePath path: The path of the selected area.
		@param gtk.TreeIter iter: The iter that refereces to the 
								selected row.
		'''

		model    = widget.get_model()
		iter     = model.get_iter(path)
		filename = model.get_value(iter, PATH)
		self.__FileName = filename

		self.__IterCurrentPlaying = self.__getIterNatural(iter)
		self.setLocation(filename)

		self.__PlayButton.set_active(False)
		self.__PlayButton.set_active(True)

	def setLocation(self, filename):
		"""
		Set the location in the player and
		perform some other required actions

		@param strin filename: Location to be loaded
		"""
		self.__StatePlaying = False
		self.__IterNatural  = None
		# current iter is a temporal variable
		# that will hold a gtk.TreeIter
		# should be setted to None 
		# before using it
		self.__LibraryCurrentIter = None
		
		self.__Player.stop()
		self.__LibraryNaturalModel.foreach(self.__SearchByPath, self.__Player.getLocation())
	
		if (self.__LibraryCurrentIter != None):
			pix = self.__Share.getImageFromPix('blank')
			pix = pix.scale_simple(20, 20, gtk.gdk.INTERP_BILINEAR)
			self.__LibraryNaturalModel.set(self.__LibraryCurrentIter, PIX, pix)
			self.__IterNatural = self.__LibraryCurrentIter
		
		# Search for the item in the library.
		# if it exists then set it in the "backend/last_played"
		# entry in gconf to be able to select it in the next
		# christine start-up (and other functions) and
		if (self.__IterCurrentPlaying != None and os.path.isfile(filename)):
			count = self.__LibraryNaturalModel.get_value(self.__IterCurrentPlaying, PLAY_COUNT)
			self.__LibraryNaturalModel.set(self.__IterCurrentPlaying, PLAY_COUNT, count + 1)
			self.__IterNatural = self.__IterCurrentPlaying

			self.__Library.save()
			self.__LastPlayed.append(filename)
			self.__GConf.setValue('backend/last_played', filename)

		self.__Player.setLocation(filename)
		name = os.path.split(filename)[-1]
		self.__Display.setSong(name)
		# enable the stream-length for the current song.
		# this will be stopped when we get the length
		gobject.timeout_add(300,self.__streamLength)
		# if we can't get the length, in more than 20
		# times in the same song, then, jump to the
		# next song
		if (self.__LocationCount > 10):
			self.goNext()
		else:
			self.__LocationCount +=1
	
	def stop(self, widget=None):
		"""
		Stop the player
		
		@param gtk.Wiget widget = None:
		"""
		self.__Player.stop()
			
	def changeVolume(self, widget):
		"""
		Callback for the volume scale widget
		@param gtk.Widget widget: Reference to the 
			self.__HScaleVolume widget
		"""
		value = widget.get_value()

		self.__Player.setVolume(value)
		self.__GConf.setValue('control/volume', value)
	
	def __changePrefVolume(self, client, cnx_id, entry, widget):
		'''
		Change the volume of the widget to the last updated value
		in the Preferences storage value.
		'''
		self.__HScaleVolume.set_value(entry.get_value().get_float())
	
	def toggleViewSmall(self, widget):
		"""
		Toggle between the small and the large view
		@param gtk.Widget: gtk.MenuItem that launches this 
		method.
		"""
		#
		# The need to use the "self.__Window.get_size()" will be
		# erased in the future, window size will be saved in
		# gconf.
		#
		active = widget.get_active()
		self.__GConf.setValue('ui/small_view', active)

		if (active):
			self.__HPanedListsBox.hide()
			self.HBoxSearch.hide()

			self.__WindowSize = self.__Window.get_size()
			self.__Window.unmaximize()
			self.__Window.resize(10, 10)
			self.__Window.set_resizable(False)
		else:
			try:
				(w, h) = self.__WindowSize
			except:
				(w, h) = (800, 480)

			self.__HPanedListsBox.show()
			self.HBoxSearch.show()
			self.__Window.resize(w, h)
			self.__Window.set_resizable(True)

	def toggleVisualization(self, widget):
		"""
		This show/hide the visualization
		@param widget: The widget that launches this method.
		"""
		self.__GConf.setValue('ui/visualization', widget.get_active())
		self.visualModePlayer()

		# Be shure that we are not in small view mode.
		if ((self.__MenuItemSmallView.get_active()) and (not widget.get_active())):
			self.toggleViewSmall(self.__MenuItemSmallView)

		self.__Player.setVisualization(widget.get_active())
		
	
	def toggleFullScreen(self, widget = None):
		"""
		Set the full Screen mode
		@param widget: The widget that launches this method.
		"""
		# Only if we are not in FullScreen and we are 
		#playing a video.
		# FIXME: We must enable the full screen if christine has
		#        visualization enabled
		if (not self.__IsFullScreen):
			if ((self.__Player.isVideo()) or\
					(self.__GConf.getBool('ui/visualization'))):
				self.__Window.fullscreen()
				self.__ScrolledMusic.set_size_request(0,0)
				self.__VBoxList.set_size_request(0,0)

				self.__IsFullScreen = True
			else:
				self.__Logger.Log('WARNING: Full screen with no visualization')
				self.__Window.fullscreen()
				self.__IsFullScreen = True
		else: 
		# Non-full screen mode.
		# hide if we are not playing a video nor
		# visualization.
			if ((not self.__Player.isVideo()) and\
					(not self.__GConf.getBool('ui/visualization'))):
				self.__Player.hide()
			self.__ScrolledMusic.set_size_request(200,200)
			self.__VBoxList.set_size_request(150,0)

			self.__Window.unfullscreen()
			self.__IsFullScreen = False
	
#####
##### Handler for the events in the window
#####
##### @access public
##### @param  widget
##### @return void
####def onWindowCoreEvent(self, player, event):
####	"""
####	Handler for the events in the window
####	@param 
####	"""
####	if (event.type == gtk.gdk.KEY_PRESS):
####		if (event.keyval == 103):
####			self.viewPlayButtons()
####		elif (event.keyval == 65366):
####			if (self.__IsFullScreen):
####				self.goNext()
####		elif (event.keyval == 65365):
####			if (self.__IsFullScreen):
####				self.goPrev()
####				return True
####		elif (event.keyval == 102):
####			if (self.__IsFullScreen):
####				self.toggleFullScreen()
	
	def viewPlayButtons(self, widget = None):
		"""
		This show/hide the player buttons. Suppossed to work only on 
		fullscreen mode
		
		@param gtk.Widget widget = None: 
		"""
		if (not self.__IsFullScreen):
			return True

		if (self.__ShowButtons):
			self.__HBoxToolBoxContainerMini.show()
			self.MenuBar.show()
			self.__ShowButtons = False
		else:
			self.__HBoxToolBoxContainerMini.hide()
			self.MenuBar.hide()
			self.__ShowButtons = True

	###########################################
	#           search stuff begins           #
	###########################################
	
	def onFindActivate(self, widget):
		"""
		Set the focus on the Search entry
		@param widget: Gtk.Widget that lauhces this method
		"""
		self.EntrySearch.grab_focus()

	def search(self, widget = None):
		"""
		Perform the actions to make a search
		@param Widget widget= None:
		"""

		# Store the text that is in search box into 
		# the self.__TextToSearch variable
		self.__TextToSearch = self.EntrySearch.get_text().lower()

		if (self.__TextToSearch == ''):
			self.jumpToPlaying()

		# Since we are using a filter model (in the library) we 
		# can use
		# the refilter method in the filter model to show only
		# the rows that we need.
		self.__LibraryFilterModel.refilter()
	
	def clearEntrySearch(self, widget):
		"""
		Entry search cleaning
		@param widget: gtk.Widget
		"""
		self.EntrySearch.set_text('')

	def filter(self, model, iter):
		'''
		#
		# This method is called by the library.refilter filtered 
		# model method.
		# This code should be as simple as we can, we must do 
		# everything
		# as fast as we can
		#
		# @access public
		# @param  widget
		# @param  ?       iter
		'''

		if (self.__TextToSearch == ''):
			return True

		value = model.get(iter, SEARCH)[0]

		try:
			value = value.lower()
		except:
			value = ""
			
		if (value.find(self.__TextToSearch) >= 0):
			return True
		else: 
			return False

	###################################################
	#                  Play stuff                     #
	###################################################
	
	def switchPlay(self, widget):
		"""
		This metod enable/disable the playing. Works for the 
		menuitem and for the play button.
		# @param  widget
		"""
		#
		# is really needed two controls? 
		#
		active = widget.get_active()

		if (not active):
			self.__Player.pause()
			self.__StatePlaying = False
		else:
			self.play()
			self.__StatePlaying = True
			self.jumpToPlaying()

		# Sync the two controls
		self.__MenuItemPlay.set_active(active)
		self.__PlayButton.set_active(active)
			
	def play(self, widget = None):
		"""
		Play!!, but only if the state is not already playing

		# @param  widget
		"""
		if not self.__StatePlaying:
			location = self.__Player.getLocation()
			# and only if location is not None, 
			# if it is the case then
			# go for one file to play
			if (location == None):
				self.goNext()
			self.__Player.playIt()

	def trayIconPlay(self,widget = None):
		"""
		Play from trayicon menu

		# @param  widget
		"""
		self.__PlayButton.set_active(True)

	def pause(self, widget = None):
		"""
		Pause method

		@param  widget
		"""
		self.__PlayButton.set_active(False)
		
	def __getIterNatural(self, iter):
		"""
		This returns a natural iter, the iter in the 
		low level model gtk.ListStore in library
		
		@param gtk.TreeIter: Current iter
		"""
		#Didn't you hate the long names?
		method = self.__LibraryModel.convert_iter_to_child_iter
		fiter = method(None, iter)
		method =self.__LibraryFilterModel.convert_iter_to_child_iter
		return method(fiter)

	def goPrev(self, widget = None):
		"""
		Go to play the previous song. 
		If no previous song was played in the 
		current session, then plays the previous 
		song in the library

		# @param  widget
		"""
		if (len(self.__LastPlayed) > 1):
			# remove the last played since it's the 
			# same that we are playing.
			self.__LastPlayed.pop()
			self.setLocation(self.__LastPlayed.pop())
			self.__PlayButton.set_active(False)
			self.__PlayButton.set_active(True)
		else:
			self.__LibraryCurrentIter = None
			self.__LibraryModel.foreach(self.__SearchByPath, 
				self.__GConf.getString('backend/last_played'))

			if self.__LibraryCurrentIter != None:
				path = self.__LibraryModel.get_path(self.__LibraryCurrentIter)
				if (path > 0):
					path = (path[0] -1,)

				if (path[0] > -1):
					iter     = self.__LibraryModel.get_iter(path)
					location = self.__LibraryModel.get_value(iter, PATH)
					self.setLocation(location)

					# This avoid the return to the last played song
					# wich is the next in the list.
					self.__LastPlayed.pop()
					self.__PlayButton.set_active(False)
					self.__PlayButton.set_active(True)
	

	def goNext(self, widget = None):
		"""
		Find a new file to play. in some cases 
		relay on self.__getNextInList

		# @param  widget
		"""
		# resetting the self.__LocationCount to 0 as we have a new file :-)
		self.__LocationCount = 0

		# Look for a file in the queue. Iter should not be None in the case
		# there where something in the queue
		model = self.Queue.treeview.get_model()
		iter  = model.get_iter_first()

		if (type(iter) == gtk.TreeIter):
			self.setLocation(model.get_value(iter, PATH))
			self.__LibraryCurrentIter == None
			self.jumpToPlaying()
			self.Queue.remove(iter)
			self.Queue.save()
			self.__PlayButton.set_active(False)
			self.__PlayButton.set_active(True)
		else:
			# FIXME: I got to fix this when I know what to do with the 
			# play behavior.
			if (self.__MenuItemShuffle.get_active()):
				self.__Elements = 0
				self.__Elements = len (self.__LibraryModel) - 1
				if self.__Elements < 1:
					return True
				# r will represent a gtk.TreePath. a printable version
				# of the gtk.TreePath is like this (0,), we just
				# need to substitute that zero for the random value
				# we want.
				r = ((self.__Elements * random.random()),)
				iter     = self.__LibraryModel.get_iter(r)
				filename = self.__LibraryModel.get_value(iter, PATH)
				self.__IterCurrentPlaying = self.__getIterNatural(iter)
				if ((not filename in self.__LastPlayed) or \
						(self.__GConf.getBool('control/repeat'))):
						self.setLocation(filename)
						self.__PlayButton.set_active(False)
						self.__PlayButton.set_active(True)
				else:
					self.__getNextInList()
					self.__PlayButton.set_active(False)
					self.__PlayButton.set_active(True)
			else:
				self.__getNextInList()

	def	__checkQueue(self):
		'''

		# Check queue
		#
		# @access public
		# @param  widget
		# @return boolean

		'''
		if not self.__GConf.getBool("ui/QueueAutohide"):
			return True
		model = self.Queue.treeview.get_model()

		if (model != None):
			b = model.get_iter_first()

			if (type(b) != gtk.TreeIter):
				self.__ScrolledQueue.hide()
			else:
				self.__ScrolledQueue.show()

		return True
			
	def __getNextInList(self):
		"""
		Gets the next item in list
		"""
		path = self.__GConf.getString('backend/last_played')

		if (path == None):
			filename = self.__GConf.getString('backend/last_played')
			self.__LibraryCurrentIter = None
			self.__LibraryModel.foreach(self.__SearchByPath, filename)

			if (self.__LibraryCurrentIter == None):
				iter     = self.__LibraryModel.get_iter_first()
				filename = self.__LibraryModel.get_value(iter, PATH)
				self.__IterCurrentPlaying = self.__getIterNatural(iter)

			self.setLocation(filename)
		else:
			self.__LibraryCurrentIter = None
			self.__LibraryModel.foreach(self.__SearchByPath, path)

			if (self.__LibraryCurrentIter != None):
				iter = self.__LibraryModel.iter_next(self.__LibraryCurrentIter)
			else:
				iter = self.__LibraryModel.get_iter_first()

			self.__IterCurrentPlaying = self.__getIterNatural(iter)
			try:
				self.setLocation(self.__LibraryModel.get_value(iter, PATH))
				niter = self.__getIterNatural(iter)
				self.__PlayButton.set_active(False)
				self.__PlayButton.set_active(True)
			except:
				self.setScale('', '', b = 0)
				self.setLocation(path)
				self.__PlayButton.set_active(False)
	
	def __SearchByPath(self, model, path, iter, location):
		"""
		search location in the model, if it found it then it will
		store the iter where it was found in 
		self.__LibraryCurrentIter

		@param gtk.Model model,
		@param gtk.TreePath path,
		@param gtk.TreeIter iter,
		@param string location: The strin to search for.
		"""
		iter      = model.get_iter(path)
		mlocation = model.get_value(iter, PATH)

		if mlocation == location:
			self.__LibraryCurrentIter = iter
			return True
	
	def onScaleChanged(self, scale, a, value = None):
		"""
		Callback on the value changed signal on position scale

		@access public
		"""
		value = int(self.__Display.value * self.__TimeTotal) 
		value = value / gst.SECOND
		total = self.__TimeTotal*gst.SECOND

		self.__ScaleMoving = False

		if (value < 0):
			value = 0

		self.__Player.seekTo(value)
	
	#
	# Sets scale value
	#
	# @access public
	# @return void
	def setScale(self, scale, a, b):
		"""
		This method changes the scale value
		"""
		self.__ScaleMoving = True
		self.__ScaleValue  = b
		self.__ScaleMoving = False
	
	#
	# Jump to playing
	#
	# @access public
	# @return void
	def jumpToPlaying(self, widget = None, path = None):
		"""
		This method jumps and select the file
		specified in the path.
		If path is not specified then try to
		select the playing one
		"""
		if (path == None):
			location = self.__Player.getLocation()
		else:
			location = path

		self.__LibraryCurrentIter = None
		self.__LibraryModel.foreach(self.__SearchByPath, location)

		if (self.__LibraryCurrentIter != None):
			state = self.__StatePlaying

			if (self.__StatePlaying):
				iter = self.__getIterNatural(self.__LibraryCurrentIter)
				pix  = self.__Share.getImageFromPix('sound')
				pix  = pix.scale_simple(20, 20, gtk.gdk.INTERP_BILINEAR)
				self.__LibraryNaturalModel.set(iter, PIX, pix)

			path = self.__LibraryModel.get_path(self.__LibraryCurrentIter)

			if (path != None):
				self.TreeView.scroll_to_cell(path, None, True, 0.5, 0.5)
				self.TreeView.set_cursor(path)

	#
	# Jump to creates dialog
	#
	# @access public
	# @param  widget
	# @return boolean
	def jumpTo(self, widget):
		"""
		Creates a gtk.Dialog box where
		the user specify the minute and second
		where to the song/video should be.
		"""
		# if self.__TimeTotal is not defined then
		# there is no media in player, so
		# there is no way to "jump to" any place.
		if (self.__TimeTotal == 0):
			return False

		XML    = self.__Share.getTemplate('jumpTo')
		dialog = XML['dialog']
		dialog.set_icon(self.__Share.getImageFromPix('logo'))

		(mins, seconds) = divmod((self.__TimeTotal / gst.SECOND), 60)

		#Current minute and current second
		(cmins, cseconds) = divmod(self.__Display.getValue(), 60)
		(cmins, cseconds) = (int(cmins), int(cseconds))

		mins_adj = gtk.Adjustment(value = 0, lower = 0, upper = mins, step_incr = 1)
		secs_adj = gtk.Adjustment(value = 0, lower = 0, upper = 59, step_incr = 1)

		ok_button = XML['okbutton']

		mins_scale = XML['mins']
		secs_scale = XML['secs']

		mins_scale.connect('key-press-event', self.jumpToOkClicked, ok_button)
		secs_scale.connect('key-press-event', self.jumpToOkClicked, ok_button)

		mins_scale.set_adjustment(mins_adj)
		mins_scale.set_value(cmins)

		secs_scale.set_adjustment(secs_adj)
		secs_scale.set_value(cseconds)

		response = dialog.run()
		dialog.destroy()

		if (response == gtk.RESPONSE_OK):
			time = ((mins_scale.get_value() * 60) + secs_scale.get_value())

			if (time > self.__TimeTotal):
				time = self.__TimeTotal

			self.__Player.seekTo(time)

	#
	# Jump to accept button
	#
	# @access public
	# @param  widget
	# @param  event
	# @param  widget
	# @return void			
	def jumpToOkClicked(self, widget, event, button):
		"""
		Jumpo to Accept button
		"""
		if (event.keyval == 65293):
			button.emit('clicked')

	#
	# Decrease volume
	#
	# @access public
	# @param  widget
	# @return void
	def decreaseVolume(self, widget = None):
		"""
		Decrease the volume
		"""
		volume = (self.__HScaleVolume.get_value() - 0.1)

		if (volume < 0):
			volume = 0

		self.__HScaleVolume.set_value(volume)
	
	#
	# Increase volume
	#
	# @access public
	# @param  widget
	# @return void
	def increaseVolume(self, widget = None):
		"""
		Increase the volume
		"""
		volume = (self.__HScaleVolume.get_value() + 0.1)

		if (volume > 1.0):
			volume = 1.0

		self.__HScaleVolume.set_value(volume)
	
	#
	# Mute volume
	#
	# @access public
	# @param  widget
	# @return void
	def mute(self, widget):
		"""
		Set mute
		"""
		if (widget.get_active()):
			self.__Volume = self.__HScaleVolume.get_value()
			self.__HScaleVolume.set_value(0.0)
		else:
			self.__HScaleVolume.set_value(self.__Volume)

	####################################################
	#               libraty stuff begins               #
	####################################################
	
	#
	# Import a file or files
	#
	# @access public
	# @param  widget
	# @return void
	def importFile(self, widget, queue = False):
		"""
		Import a file or files
		first argument is a widget, second argument
		is an optional  boolean value that defines
		if the files are going to queue or not
		"""
		XML = self.__Share.getTemplate('FileSelector')
		fs  = XML['fs']
		uri = self.__GConf.getString("ui/LastFolder")
		if uri:
			fs.set_uri(uri)
		fs.set_icon(self.__Share.getImageFromPix('logo'))

		response = fs.run()
		files    = fs.get_filenames()

		fs.destroy()

		if (response == gtk.RESPONSE_OK):
			self.addFiles(files = files, queue = queue)
			path = os.path.join(os.path.split(files[0])[:-1])[0]
			self.__GConf.setValue("ui/LastFolder",path)

			# What I told, if queue is true
			# send it to queue
			if (queue):
				self.Queue.save()
			else:
				self.__Library.save()
	
	#
	# Import folder
	#
	# @access public
	# @param  widget
	# @return void
	def importFolder(self, widget):
		"""
		This is the 'simple' way to import folders
		Creates and rund a filechooser dialog to 
		select the dir. 
		A Checkbox let you set if the import will be
		recursive.
		"""
		XML  = self.__Share.getTemplate('directorySelector')
		ds   = XML['ds']
		walk = XML['walk']
		uri = self.__GConf.getString("ui/LastFolder")
		if uri:
			ds.set_uri(uri)

		ds.set_icon(self.__Share.getImageFromPix('logo'))

		response  = ds.run()
		filenames = ds.get_filenames()


		if (response == gtk.RESPONSE_OK):
			self.__GConf.setValue("ui/LastFolder",filenames[0])
			ds.destroy()
			for i in filenames:
				if (walk.get_active()):
					self.addDirectories(i)
				else:
					files = [os.path.join(i, k) \
					for k in os.listdir(i) if os.path.isfile(os.path.join(i, k))]
					if (len(files) > 0):
						self.addFiles(files = files)

			self.__Library.save()
			return True
		ds.destroy()

	#
	# This add a single directory, is simplier that addDirectories
	# because there is no need to dig
	#
	# @access public
	# @param  string dir
	# @return void
	def addDirectory(self, dir):
		"""
		This add a single directory, is simplier that addDirectories
		because there is no need to dig
		"""
		files = os.listdir(dir)
		f     = []
		self.f = []

		for i in files:
			ext = i.split('.').pop()
			exists = False

			if (os.path.join(i[0], path) in self.f):
				exists = True

			# Again, only files with the right
			# extension will be imported
			if (ext in self.__GConf.getString('backend/allowed_files').split(',')):
				f.append(i)

		files = f
		self.addFiles(files)
	
	#
	# Recursive import, first and only argument
	# is the dir where to digg
	#
	# @access public
	# @param  string dir
	# @return void
	def addDirectories(self, dir):
		"""
		Recursive import, first and only argument
		is the dir where to digg
		"""
		# dig looking for files
		a         = os.walk(dir)
		b         = True
		f         = []
		filenames = []

		while (b):
			try: 
				(dirpath, dirnames, files) = a.next()
				filenames.append([dirpath, files])
			except:
				b = False

		self.f = []

		# create a temporal list with the path of
		# the files already stored in the library
		# to avoid duplicates
		self.__LibraryModel.foreach(lambda model,path,iter: self.f.append(model.get_value(iter,PATH)))
		for i in filenames:
			for path in i[1]:
				ext    = path.split('.').pop().lower()
				exists = False

				if (os.path.join(i[0], path) in self.f):
					exists = True

				# FIXME: at the moment only files with the right
				# extension will be imported, 
				# this extensions are defined in 
				# libs_christine/libs_christine.py
				# We need to know what files are supported by 
				# gstreamer
				if ext in self.__GConf.getString('backend/allowed_files').split(',') and not exists:
					f.append(os.path.join(i[0],path))
		# Once we have the files to add, then use the addFiles
		# wrapper method to add them.
		if (len(f) > 0):
			self.addFiles(files = f)
		else:
			pass
	
	#
	# Add a single file, to the library or queue.
	# the files are taken from the self.__FilesToAdd
	# list. the only one argument is queue, wich defines
	# if the importing is to the queue
	#
	# @access private
	# @return boolean
	def __addFile(self, list = None, data = None,queue = False):
		"""
		Add a single file, to the library or queue.
		the files are taken from the self.__FilesToAdd
		list. the only one argument is queue, wich defines
		if the importing is to the queue
		"""
		if (type(queue) != type(True)):
			queue = False

		# This method is the "hard" one in the importing files
		# (or directories) We must be carefull in the code
		# and everything must run as fast as we can
		if queue:
			library = self.Queue
		else:
			library = self.__Library
		counter = 0
		while len(self.__FilesToAdd) > 0:
			counter +=1
			new_file = self.__FilesToAdd.pop()
			library.add(new_file)
			if counter == 500:
				library.save()
				counter = 0
			self.__updateAddProgressBar(new_file)
		library.save()

	def __updateAddProgressBar(self,file):
		length = len(self.__FilesToAdd)
		if (length > 0):
			self.__Percentage = (1 - (length / float(self.__TimeTotalNFiles)))
		else:
			self.__Percentage = 1
		if (self.__Percentage > 1.0):
			self.__Percentage = 1.0
		# Setting the value and text in the progressbar
		self.__AddProgress.set_fraction(self.__Percentage)
		rest = (self.__TimeTotalNFiles - length)
		text = "%02d/%02d" % (rest, self.__TimeTotalNFiles)
		self.__AddProgress.set_text(text)
		self.__AddFileLabel.set_text(os.path.split(file)[1])
		while gtk.events_pending():
			gtk.main_iteration(False)


	#
	# Add files to the library or to the queue
	#
	# @access public
	# @return void
	def addFiles(self, widget = None, files = None, queue = False):
		"""
		Add files to the library or to the queue
		"""
		XML = self.__Share.getTemplate('addFiles')
		XML.signal_autoconnect(self)
		
		self.__AddWindow       = XML['WindowCore']
		self.__AddProgress     = XML['progressbar']
		self.__AddCloseButton  = XML['close']
		self.__AddFileLabel    = XML['file_label']
		self.__AddFileLabel.set_text('None')
		self.__AddCloseButton.connect("clicked",self.importCancel)

		self.__AddCloseButton.grab_add()
		# Be sure that we are working with a list of files
		if (type(files) != type([])):
			raise TypeError, "files must be List, got %s" % type(files)

		files.reverse()

		# Global variable to save temporal files and paths
		self.__FilesToAdd = []
		self.__Paths      = []

		self.__LibraryNaturalModel.foreach(self.getPaths)

		for i in files:
			ext    = i.split('.').pop().lower()
			if (not i in self.__Paths) and \
					(ext in self.__GConf.getString('backend/allowed_files').split(',')):
				self.__FilesToAdd.append(i)

		self.__Percentage      = 0
		self.__TimeTotalNFiles = len(self.__FilesToAdd)

		self.__addFile(queue=queue)
		self.__AddWindow.destroy()

	#
	# Gets path from
	#
	# @access public
	# @return void
	def getPaths(self, model, path, iter):
		"""
		Gets path from
		"""
		self.__Paths.append(model.get_value(iter, PATH))

	#
	# Cancel de import stuff
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def importCancel(self, widget):
		"""
		Cancel de import stuff
		"""
		self.__AddCloseButton.grab_remove()
		self.__FilesToAdd = []
		self.__AddWindow.destroy()

	#
	# Import file to queue
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def importToQueue(self, widget):
		"""
		Import file to queue
		"""
		self.importFile('', True)
	
	########################################
	#          PLayer section              #
	########################################

	#
	# Handle the messages from self.__Player
	#
	# @access public
	# @params ?        a
	# @params ?        b
	# @params ?        c
	# @params ?        d
	# @return boolean
	def __handlerMessage(self, a, b, c = None, d = None):
		"""
		Handle the messages from self.__Player
		"""
		type_file = b.type

		if (type_file == gst.MESSAGE_ERROR):
			error(b.parse_error()[1])

		if (type_file == gst.MESSAGE_EOS):
			self.goNext()
		elif (type_file == gst.MESSAGE_TAG):
			self.__Player.foundTagCallback(b.parse_tag())
			self.setTags()
		elif (type_file == gst.MESSAGE_BUFFERING):
			percent = 0
			percent = b.structure['buffer-percent']
			self.__Display.setText("%d" % percent)
			self.__Display.setValue((percent / 100))
		elif (type_file == gst.MESSAGE_ELEMENT):
			self.__Player.emitExpose()
			return True

		return True

	#
	# Update the time showed in the player 
	# it in the  player
	#
	# @access public
	# @return boolean
	def checkTimeOnMedia(self):
		"""
		Update the time showed in the player
		"""
		try:
			nanos      = self.__Player.query_position(gst.FORMAT_TIME)[0]
			ts         = (nanos / gst.SECOND)
			time       = "%02d:%02d" % divmod(ts, 60)
			time_total = "%02d:%02d" % divmod((self.__TimeTotal / gst.SECOND), 60)

			if (ts < 0):
				ts = long(0)

			if ((nanos > 0) and (self.__TimeTotal > 0)):
				currenttime = (nanos / float(self.__TimeTotal))
				self.__Display.setText("%s/%s" % (time, time_total))

				if ((currenttime >= 0) and (currenttime <= 1)):
					self.__Display.setScale(currenttime)
		# Taking care only in gst.QueryError
		# other errors are raised
		except gst.QueryError:
			pass

		return True
	
	#
	# Catches the lenght of the media and update 
	# it in the  player
	#
	# @access private
	# @return boolean
	def __streamLength(self):
		"""
		Catches the lenght of the media and update it in the 
		player
		"""
		if (self.__Player.getLocation().split(':')[0] == 'http'):
			return True

		try:
			self.__TimeTotal = self.__Player.query_duration(gst.FORMAT_TIME)[0]
			ts               = (self.__TimeTotal / gst.SECOND)
			text             = "%02d:%02d" % divmod(ts, 60)

			self.__ErrorStreamCount = 0

			if (self.__IterNatural is not None):
				time= self.__LibraryNaturalModel.get(self.__IterNatural, TIME)

				if (time != text):
					self.__LibraryNaturalModel.set(self.__IterNatural, TIME, text)
					self.__Library.save()
			return False
		except gst.QueryError:
			self.__ErrorStreamCount += 1

			if (self.__ErrorStreamCount > 10):
				self.setLocation(self.__Player.getLocation())
				self.__PlayButton.set_active(False)
				self.__PlayButton.set_active(True)

			return True
	
	#
	# Update the current media tags in the library
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @param  ?      b      ?
	# @return void
	def setTags(self, widget = "", b = ""):
		"""
		Update the current media tags in the library
		"""
		title     = self.__Player.getTag('title').replace('_', ' ')
		artist    = self.__Player.getTag('artist')
		album     = self.__Player.getTag('album')
		genre     = self.__Player.getTag('genre')
		type_file = self.__Player.getType()

		tags = [title,artist,album,genre]

		if tags == self.__LastTags:
			return True
		else:
			self.__LastTags = tags

		if (type(genre) == type([])):
			genre = ','.join(genre)
		elif type(genre) != type(""):
			genre = ""

		track_number = self.__Player.getTag('track-number')
		if type(track_number) == type(""):
			if track_number.isdigit():
				track_number = int(track_number)
			else:
				track_number = 0


		if (title == ''):
			title = os.path.split(self.__Player.getLocation())[1]
			title = '.'.join(title.split('.')[:-1])

		# stript_XML_entities is a method inherited from gtk_misc
		tooltext = title
		title    = self.stripXmlEntities(title)

		# Sets window title, which it will be our current song :-)
		self.__Window.set_title("%s - Christine" % title)
		
		notify_text = "<big>%s</big>\n" % title

		# Show or hide deppending if there are something
		# to show or hide
		if (artist != ''):
			notify_text += " by <big>%s</big>\n" % artist
			tooltext    += "\nby %s" % artist

		if (album != ''):
			notify_text += " from <big>%s</big>" % album
			tooltext    += "\nfrom %s" % album

		# Updating the info in library, only if it is available.
		if (self.__IterNatural is not None):
			if title != '':
				self.__LibraryNaturalModel.set(self.__IterNatural,
						NAME,   title,
						ALBUM,  album,
						ARTIST, artist,
						TN,     track_number,
						SEARCH, '.'.join([title, artist, album, genre, type_file]),
						GENRE,  genre)

			(title1, artist1, album1, tc) = self.__LibraryNaturalModel.get(self.__IterNatural, 
			NAME, ARTIST, ALBUM, TN)

			if title != title1 \
				or artist != artist1 \
				or album != album \
				or track_number != tc:
				gobject.timeout_add(500, self.__Library.save)

		if ((PYNOTIFY) and (self.__GConf.getBool('ui/show_pynotify'))):
			try:
				self.__Notify.close()
			except:
				pass
			pixmap = self.__Share.getImage('trayicon')
			self.__Notify = pynotify.Notification('christine', '',pixmap)

			if (self.__GConf.getBool('ui/show_in_notification_area')):
				try:
					self.__Notify.attach_to_status_icon(self.__TrayIcon)
				except:
					pass
				self.__TrayIcon.set_tooltip(tooltext)

			self.__Notify.set_timeout(3000)

			self.__Notify.set_property('body', notify_text)
			self.__Notify.show()

		self.__Display.setSong(tooltext.replace('\n', ' '))
		self.visualModePlayer()
	
	########################################
	#             Gtk modes                #
	########################################
	
	#
	# Simple or complete visualization
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def visualModePlayer(self, widget = None):
		"""
		Simple or complete visualization
		"""
		isPlaying = False
		state = self.__Player.getState()[1]
		if gst.State(gst.STATE_PLAYING) is state:
			isPlaying = True

		if (self.__Player.isVideo()):
			self.__HBoxPlayer.show_all()
		else:
			if (self.__GConf.getBool('ui/visualization') and isPlaying):
				self.__HBoxPlayer.show_all()
			else:
				self.__HBoxPlayer.hide()

	
	#
	# Open a dialog to select a remote location
	#
	# @see    openRemote.glade
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def openRemote(self, widget):
		"""
		Open a dialog to select a remote location
		"""
		# Need be hacked to use mp3u playlist and radio features
		XML    = self.__Share.getTemplate('openRemote')
		entry  = XML['entry']
		dialog = XML['dialog']
		button  = XML['okbutton']
		entry.connect("key-press-event", self.__oRButtonClick,button)

		dialog.set_icon(self.__Share.getImageFromPix('logo'))

		response = dialog.run()

		if (response == gtk.RESPONSE_OK):
			location = entry.get_text()
			if location == "":
				return False
			extension = location.split(".").pop()
			if location.split(":")[0] == "file":
				file = ":".join(location.split(":")[1:])[2:]
				urldesc = open(file)
			else:
				import urllib
				gate = urllib.FancyURLopener()
				urldesc = gate.open(location)
			if extension == "pls":
				for i in urldesc.readlines():
					if i.lower().find("file") > -1:
						location = i.split("=").pop().strip()
				self.setLocation(location)
				self.__PlayButton.set_active(False)
				self.__PlayButton.set_active(True)
			elif extension == "m3u":
				lines = urldesc.readlines()
				if lines[0].lower() != "#extm3u":
					self.goNext()

				sites = []
				for i in range(len(lines)):
					if lines[i].split(":")[0].lower() == "#extinf":
						sites.append(lines[i+1])
					else:
						print lines[i].split(":")[0].lower()
				print sites
				for i in sites:
					i = i.strip("\r")
					i = i.strip("\n")
					i = i.strip()
					self.Queue.add(i)
				self.goNext()
			urldesc.close()
		dialog.destroy()
	
	def __oRButtonClick(self,widget,event,button):
		'''
		Clicks the okbutton on ENTER key pressed
		'''
		if widget.get_text() == "":
			return False
		if event.keyval == 65293:
			button.clicked()
	#
	# Raise a dialog that asks for confirmation
	# To remove all files in the list
	# @regturn void
	def cleanLibrary(self,widget):
		xml = self.__Share.getTemplate("deleteQuestion")
		dialog = xml["dialog"]
		response = dialog.run()
		if response == -5:
			self.__Library.clear()
		dialog.destroy()



	#
	# Show the about dialog
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def showGtkAbout(self, widget):
		"""
		Show the about dialog
		"""
		guiAbout()
	
	#
	# Show the preferences dialog
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def showGtkPreferences(self, widget):
		"""
		Show the preferences dialog
		"""
		guiPreferences()
	
	#
	# GTK application exit
	#
	# @access public
	# @param  widget widget The widget that will be used
	# @return void
	def quitGtk(self, widget = None):
		self.__Player.stop()
		gtk.main_quit()
	
	#
	# GTK application run
	#
	# @access public
	# @return void
	def runGtk(self):
		"""
		GTK application running
		"""
		gtk.main()


# This is useful when we want to launch christine 
# directiy from python
if __name__ == "__main__":
	a = Christine()
	a.runGtk()
