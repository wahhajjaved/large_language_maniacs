#! /usr/bin/env python
## Copyright (c) 2006 Marco Antonio Islas Cruz
## <markuz@islascruz.org>
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.



import os,gtk,gobject,sys,pango
import gst
from libchristine.libs_christine import lib_library
from libchristine.gui.GtkMisc import GtkMisc, error
from libchristine.Translator import translate
from libchristine.christineConf import christineConf
from libchristine.Share import Share
from libchristine.Tagger import Tagger
from libchristine.LibraryModel import LibraryModel
from libchristine.globalvars import CHRISTINE_VIDEO_EXT
from libchristine.Logger import LoggerManager
from libchristine.ui import interface
from libchristine.Storage.sqlitedb import sqlite3db
from libchristine.Events import christineEvents

(PATH,
NAME,
TYPE,
PIX,
ALBUM,
ARTIST,
TN,
SEARCH,
PLAY_COUNT,
TIME,
GENRE) = range(11)

(VPATH,
VNAME,
VPIX) = range(3)

QUEUE_TARGETS = [
		('MY_TREE_MODEL_ROW',gtk.TARGET_SAME_WIDGET,0),
		('text/plain',0,0),
		('TEXT',0,0),
		('STRING',0,0)
		]


##
## Since library and queue are more or less the same
## thing. I guess we need to use a base class for
## both lists (and other lists)
##

class libraryBase(GtkMisc):
	def __init__(self):
		'''
		Constructor, load the
		glade ui description for a simple treeview
		and set some class variables
		'''
		self.iters = {}
		GtkMisc.__init__(self)
		self.share = Share()
		self.interface = interface()
		self.db = sqlite3db()
		self.tagger = Tagger()
		self.Events = christineEvents()
		#self.__row_changed_id = 0
		#self.__appending = False
		#self.__setting = False
		self.__xml = self.share.getTemplate("TreeViewSources","treeview")
		self.__xml.signal_autoconnect(self)
		self.gconf = christineConf()
		self.tv = self.__xml["treeview"]
		self.set_drag_n_drop()
		self.blank_pix = self.share.getImageFromPix("blank")
		self.blank_pix = self.blank_pix.scale_simple(20,20,gtk.gdk.INTERP_BILINEAR)
		self.add_columns()
		self.scroll = gtk.ScrolledWindow()
		self.scroll.set_policy(gtk.POLICY_AUTOMATIC,gtk.POLICY_AUTOMATIC)
		self.scroll.set_shadow_type(gtk.SHADOW_ETCHED_IN)
		self.scroll.add(self.tv)
		
	def loadLibrary(self, library):
		#if self.__row_changed_id:
		#	self.model.disconnect(self.__row_changed_id)
		self.tv.set_model(None)
		#self.__appending = False
		#self.__setting = False
		self.library_lib = lib_library(library)
		self.__music = self.library_lib.get_all()
		self.__iterator = self.__music
		#self.__iterator = self.__music.keys()
		#self.__iterator.sort()
		self.gen_model()
		self.model.createSubmodels()
		self.fillModel()
		self.tv.set_model(self.model.getModel())
		self.CURRENT_ITER = self.model.get_iter_first()

	def __rowChanged(self,model,path,iter):
		'''
		Handle the row changed stuff
		'''
		#The filename is the key in the self.library dictionary
		a = [filename, name,artist,
		album,track_number,path,
		tipo,pc,duration,
		genre] = model.get(iter,PATH,
				    NAME,ARTIST,ALBUM,
					TN,PATH, TYPE,
					PLAY_COUNT,TIME,GENRE)
		if filename == None:
			return False
		a = [k for k in a]
		for i in range(len(a)):
			if a[i] == None:
				if i in [4,8]:
					a[i] = 0
				else:
					a[i] = ""
		self.library_lib[a[0]] = {"title":a[1],
				"type":a[6],"artist":a[2],
				"album":a[3],"track_number":a[4],
				"playcount":a[7],
				"time":a[8],
				"genre":a[9]}
		for i in self.library_lib[filename].keys():
			if self.library_lib[filename][i] == None:
				sys.exit(-1)

	def gen_model(self):
		'''
		Generates the model
		'''
		if not getattr(self, 'model', False):
			i = gobject.TYPE_INT
			self.model = LibraryModel(
					str, #path
					str, #name
					str, #type
					gtk.gdk.Pixbuf, #Pix
					str, #album
					str, #artist
					int, #Track Number
					str, #search
					int, #play count
					str, #time
					str) #Genre
		else:
			self.model.clear()

	def fillModel(self):
		sounds = self.library_lib.get_all()
		pix = self.share.getImageFromPix('blank')
		pix = pix.scale_simple(20, 20, gtk.gdk.INTERP_BILINEAR)
		#self.__appending = True
		keys = sounds.keys()
		keys.sort()
		for path in keys:
			values = sounds[path]
			for key in values.keys():
				if isinstance(values[key],str):
					try:
						values[key] =  u'%s'%values[key].decode('latin-1')
						values[key] =  u'%s'%values[key].encode('latin-1')
					except:
						pass
			track_number = values['track_number']
			iter = self.model.append(PATH,path,
					NAME, values['title'],
					SEARCH,
					''.join((values['title'], values['artist'],values['album'],	values['type'])),
					PIX,pix,
					TYPE,values['type'],
					ARTIST,values['artist'],
					ALBUM ,values['album'],
					TN,values['track_number'],
					PLAY_COUNT ,values['playcount'],
					TIME ,values['time'],
					GENRE ,values['genre'])
			self.iters[path] = iter

	def __set(self):
		#if not self.__setting:
		#	return False
		for i in range(20):
			if len(self.__iterator):
				key = self.__iterator.pop()
			else:
				return False
			data = self.__music[key]
			iter = self.iters[key]
			for i in data.keys():
				try:
					if isinstance(data[i], str):
						data[i] = u'%s'%data[i].encode('latin-1')
				except:
					pass
			self.model.set(iter,
					TYPE,data['type'],
					ARTIST,data['artist'],
					ALBUM ,data['album'],
					TN,data['track_number'],
					PLAY_COUNT ,data['playcount'],
					TIME ,data['time'],
					GENRE ,data['genre'],
					)
		return True

	def add_columns(self):
		render = gtk.CellRendererText()
		render.set_property("ellipsize",pango.ELLIPSIZE_END)
		tv = self.tv
		tvc = gtk.TreeViewColumn

		tn = tvc(translate("T#"),render,text=TN)
		tn.set_sort_column_id(TN)
		tn.set_min_width(30)
		tn.set_resizable(True)
		tn.set_visible(self.gconf.getBool("ui/show_tn"))
		tn.set_visible(True)
		tv.append_column(tn)

		pix = gtk.CellRendererPixbuf()
		name = tvc(translate("Title"))
		name.set_sort_column_id(NAME)
		name.set_resizable(True)
		name.set_fixed_width(250)
		name.pack_start(pix,False)
		rtext = gtk.CellRendererText()
		rtext.set_property("ellipsize",pango.ELLIPSIZE_END)
		name.pack_start(rtext,True)
		name.add_attribute(pix,"pixbuf",PIX)
		name.add_attribute(rtext,"text",NAME)
		tv.append_column(name)


		artist = tvc(translate("Artist"),render,text=ARTIST)
		artist.set_sort_column_id(ARTIST)
		artist.set_resizable(True)
		artist.set_fixed_width(150)
		artist.set_visible(self.gconf.getBool("ui/show_artist"))
		tv.append_column(artist)

		album = tvc(translate("Album"),render,text=ALBUM)
		album.set_sort_column_id(ALBUM)
		album.set_resizable(True)
		album.set_fixed_width(150)
		album.set_visible(self.gconf.getBool("ui/show_album"))
		tv.append_column(album)

		type = tvc(translate("Type"),render,text=TYPE)
		type.set_sort_column_id(TYPE)
		type.set_resizable(True)
		type.set_min_width(250)
		type.set_visible(self.gconf.getBool("ui/show_type"))
		tv.append_column(type)

		play = tvc(translate("Count"),render,text=PLAY_COUNT)
		play.set_sort_column_id(PLAY_COUNT)
		play.set_resizable(True)
		play.set_visible(self.gconf.getBool("ui/show_play_count"))
		play.set_min_width(50)
		tv.append_column(play)

		length = tvc(translate("Lenght"),render,text=TIME)
		length.set_sort_column_id(TIME)
		length.set_resizable(True)
		length.set_visible(self.gconf.getBool("ui/show_length"))
		length.set_min_width(100)
		tv.append_column(length)

		genre = tvc(translate("Genre"),render,text=GENRE)
		genre.set_sort_column_id(GENRE)
		genre.set_resizable(True)
		genre.set_visible(self.gconf.getBool("ui/show_genre"))
		genre.set_min_width(250)
		tv.append_column(genre)
		
		for i in (tn, name, artist, album, type, play, length, genre):
			i.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)


		self.gconf.notifyAdd("ui/show_artist",self.gconf.toggleVisible,artist)
		self.gconf.notifyAdd("ui/show_album",self.gconf.toggleVisible,album)
		self.gconf.notifyAdd("ui/show_type",self.gconf.toggleVisible,type)
		#self.gconf.notifyAdd("ui/show_tn",self.gconf.toggleVisible,tn)
		self.gconf.notifyAdd("ui/show_play_count",self.gconf.toggleVisible,play)
		self.gconf.notifyAdd("ui/show_length",self.gconf.toggleVisible,length)
		self.gconf.notifyAdd("ui/show_genre",self.gconf.toggleVisible,genre)
		self.tv.set_property('fixed-height-mode', True)

	def add(self,file,prepend=False):
		if type(file) == type(()):
			file = file[0]
		if not os.path.isfile(file):
			return False
		name = os.path.split(file)[1]
		if isinstance(name,()):
			name = name[0]
		################################
		vals = self.db.getItemByPath(file)
		if not vals:
			tags = self.tagger.readTags(file)
		else:
			tags = {}
			tags['title'] = vals['title']
			tags['album'] =  vals['album']
			tags['artist'] = vals['artist']
			tags['track'] = vals['track_number']
			tags['genre'] = vals['genre']

		if tags["title"] == "":
			n = os.path.split(file)[1].split(".")
			tags["title"] = ".".join([k for k in n[:-1]])

		if "video-codec" in tags.keys() or \
				os.path.splitext(file)[1][1:] in CHRISTINE_VIDEO_EXT:
			t = "video"
		else:
			t = "audio"
		if type(tags["track"]) !=  type(1):
			tags["track"] = 0
		name	= tags["title"]
		album	= tags["album"]
		artist	= tags["artist"]
		tn		= tags["track"]

		if prepend:
			func = self.model.prepend
		else:
			func = self.model.append
		iter = func(NAME,name,
				PATH,file,
				PIX,self.blank_pix,
				TYPE,t,
				ALBUM,album,
				ARTIST,artist,
				TN,int(tn),
				SEARCH,",".join([tags["title"],tags["album"],tags["artist"]]),
				PLAY_COUNT,0,
				GENRE,tags["genre"]
				)

		self.library_lib[file] = {"title":name,
				"type":t,"artist":artist,
				"album":album,
				"track_number":int(tn),
				"playcount":0,
				"time":'0:00',
				"genre":tags['genre'],}

	def stream_length(self,widget=None,n=1):
		try:
			total = self.interface.Player.query_duration(gst.FORMAT_TIME)[0]
			ts = total/gst.SECOND
			text = "%02d:%02d"%divmod(ts,60)
			self.model.set(self.iters[self.interface.Player.getLocation()],
					TIME,text)
		except gst.QueryError:
			pass
		return True

	def remove(self,iter):
		'''
		Remove the selected iter from the library.
		'''
		key = self.model.getValue(iter,PATH)
		value = self.library_lib.remove(key)
		if value:
			self.model.remove(iter)

	def save(self):
		'''
		Save the current library
		'''
		self.library_lib.save()

	def updateData(self, path, **kwargs):
		'''
		This method updates the data in the main library if it can. And
		in the data base.

		@param path:
		@param title:
		@param album:
		@param artist:
		@param track_number:
		@param search:
		@param genre:
		@param play_count:
		@param time:
		'''
		keys = {'title':NAME,
			 	'album':ALBUM,
			 	'artist':ARTIST,
			 	'track_number':TN,
			 	'search':SEARCH,
			 	'play_count':PLAY_COUNT,
			 	'genre':GENRE,
			 	'time':TIME,
			 	}
		for key in kwargs:
			value = keys[key]
			iter = self.model.basemodel.search_iter_on_column(path, PATH)
			if not iter:
				return None
			self.model.basemodel.set(iter, value, kwargs[key])
		iter = self.model.basemodel.search_iter_on_column(path, PATH)
		(path, title, artist, album, type,
		track_number, playcount,time, genre) = self.model.basemodel.get(iter,
												PATH,
												NAME, ARTIST,ALBUM, TYPE,
												TN,PLAY_COUNT, TIME, GENRE)
		self.library_lib.updateItem(path, title=title, artist=artist,
								album=album, type=type, track_number=track_number,
								playcount=playcount,time=time,
								genre=genre)

	def key_press_handler(self,treeview,event):
		if event.keyval == gtk.gdk.keyval_from_name('Delete'):
			selection = treeview.get_selection()
			model,iter = selection.get_selected()
			name = model.get_value(iter,NAME)
			model.remove(iter)
			self.library_lib.remove(name)
			self.save()

	def Exists(self,filename):
		'''
		Checks if the filename exits in
		the library
		'''
		result = filename in self.library_lib.keys()
		return result

	# Need some help in the next functions
	# They need to be retouched to work fine.

	def set_drag_n_drop(self):
		self.tv.connect("drag_motion",self.check_contexts)
		self.tv.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
				QUEUE_TARGETS,
				gtk.gdk.ACTION_DEFAULT|gtk.gdk.ACTION_MOVE)

		self.tv.connect("drag_data_received",self.add_it)
		self.tv.enable_model_drag_dest(QUEUE_TARGETS,
				gtk.gdk.ACTION_DEFAULT|gtk.gdk.ACTION_COPY)
		self.tv.connect("drag-data-get",self.drag_data_get)

		self.tv.connect("drag_drop", self.dnd_handler)

	def drag_data_get(self,
			treeview,
			context,
			selection,
			info,
			timestamp):
		tsel = treeview.get_selection()
		model,iter = tsel.get_selected()
		text = model.get_value(iter,PATH)
		text = "file://"+text
		selection.set(selection.target,8,text)
		return

	def check_contexts(self,
			treeview,
			context,
			selection,
			info,
			timestamp):
		return True

	def dnd_handler(self,
			treeview,
			context,
			selection,
			info,
			timestamp,
			b=None,
			c=None):
		treeview.emit_stop_by_name("drag_drop")
		tgt = treeview.drag_dest_find_target(context,QUEUE_TARGETS)
		text = treeview.drag_get_data(context,tgt)
		return True

	def add_it(self,treeview,context,x,y,selection,target,timestamp):
		#treeview.emit_stop_by_name("drag_drop")
		treeview.emit_stop_by_name("drag_data_received")
		target = treeview.drag_dest_find_target(context,QUEUE_TARGETS)
		if timestamp != 0:
			text = self.parse_received_data(selection.get_text())
			while len(text) > 0:
				file = text.pop()
				if file[:7] == "file://":
					file = file[7:].replace("%20"," ")
				self.add(file)
		return True

	def delete_from_disk(self,iter):
		dialog = self.share.getTemplate("deleteFileFromDisk")["dialog"]
		response = dialog.run()
		path = self.model.getValue(iter,PATH)
		if response == -5:
			try:
				os.unlink(path)
				self.remove(iter)
				self.save()
			except IOError:
				error("cannot delete file: %s"%path)
		dialog.destroy()

	def clear(self):
		self.model.clear()
		self.library_lib.clear()
		self.save()

	def itemActivated(self,widget, path, iter):
		model    = widget.get_model()
		iter     = model.get_iter(path)
		filename = model.get_value(iter, PATH)
		self.__FileName = filename
		self.interface.coreClass.setLocation(filename)
		self.IterCurrentPlaying = iter
		self.interface.playButton.set_active(False)
		self.interface.playButton.set_active(True)
		
	def set(self, *args):
		'''
		wraper for the self.model.set
		'''
		return self.model.set(*args)
		
	def search(self, *args):
		'''
		wrapper for the self.model.search
		'''
		return self.model.search(*args)
	
	def get_path(self, *args):
		'''
		wrapper for the self.model.get_path
		'''
		return self.model.get_path(*args)
	def iter_next(self, iter):
		return self.model.iter_next(iter)
		
		
class library(libraryBase):
	def __init__(self):
		libraryBase.__init__(self)
		self.__logger = LoggerManager().getLogger('Library')
		self.tv.connect('button-press-event', self.popupMenuHandlerEvent)
		self.tv.connect('key-press-event',    self.handlerKeyPress)
		self.tv.connect('row-activated',      self.itemActivated)
		self.scroll.show_all()
		self.Events.addWatcher('gotTags', self.gotTags)
	
	def gotTags(self, tags):
		title = tags['title']
		artist = tags['artist']
		album = tags['album']
		genre = tags['genre']
		track_number  = tags['track_number']
		type_file = self.interface.Player.getType()
		
		search = '.'.join([title,artist, album, genre, type_file])

		self.updateData(self.interface.Player.getLocation(),
								title=title,
								album= album,
								artist=artist,
								track_number=track_number,
								search=search,
								genre=genre)

	def handlerKeyPress(self, treeview, event):
		"""
		Handle the key-press-event in the
		library.
		Current keys: Enter to activate the row
		and 'q' to send the selected song to the
		queue
		"""

		if (event.keyval == gtk.gdk.keyval_from_name('Delete')):
			self.removeFromLibrary()
		elif (event.keyval == gtk.gdk.keyval_from_name('q')):
			selection     = treeview.get_selection()
			iter = selection.get_selected()[1]
			name          = self.model.getValue(iter, PATH)
			self.interface.Queue.add(name)

	def popupMenuHandlerEvent(self, widget, event):
		"""
		handle the button-press-event in the library
		"""
		if (event.button == 3):
			XML = self.share.getTemplate('PopupMenu')
			XML.signal_autoconnect(self)

			popup = XML['menu']
			popup.popup(None, None, None, 3, gtk.get_current_event_time())
			popup.show_all()

	def popupAddToQueue(self, widget):
		"""
		Add the selected item to the queue
		"""
		selection       = self.tv.get_selection()
		(model, iter,)  = selection.get_selected()
		file            = model.get_value(iter, PATH)

		self.interface.Queue.add(file)

class queue (libraryBase):
	def __init__(self):
		libraryBase.__init__(self)
		self.__logger = LoggerManager().getLogger('Library')
		self.loadLibrary('queue')
		self.tv.connect('key-press-event', self.QueueHandlerKey)
		gobject.timeout_add(500, self.checkQueue)
		self.scroll.set_size_request(100,150)
		self.interface.Queue = self
		self.tv.set_property('fixed-height-mode', False)


	def add_columns(self):
		render = gtk.CellRendererText()
		tv = self.tv
		pix = gtk.CellRendererPixbuf()
		icon = gtk.TreeViewColumn("",pix,pixbuf=PIX)
		icon.set_sort_column_id(TYPE)
		name = gtk.TreeViewColumn(translate("Queue"),render,markup=NAME)
		name.set_sort_column_id(NAME)
		tv.append_column(name)
		#name.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		tv.set_headers_visible(False)

	def add(self,file,prepend=False):
		if type(file) == type(()):
			file = file[0]
		if not os.path.isfile(file):
			return False
		name = os.path.split(file)[1]
		if isinstance(name,()):
			name = name[0]
		################################
		tags = self.tagger.readTags(file)

		if tags["title"] == "":
			n = os.path.split(file)[1].split(".")
			tags["title"] = ".".join([k for k in n[:-1]])

		if "video-codec" in tags.keys() or \
				os.path.splitext(file)[1][1:] in CHRISTINE_VIDEO_EXT:
			t = "video"
		else:
			t = "audio"

		if type(tags["track"]) !=  type(1):
			tags["track"] = 0

		name	= tags["title"]
		album	= tags["album"]
		artist	= tags["artist"]
		tn		= tags["track"]
		if file.split(":")[0] == "file" or \
				os.path.isfile(file) or \
				os.path.isfile(file.replace('%2C',',')):
			try:
				tags = self.tagger.readTags(file)
			except:
				self.emit_signal("tags-found!")
				return True
			name	= self.strip_XML_entities(tags["title"])
			album	= self.strip_XML_entities(tags["album"])
			artist	= self.strip_XML_entities(tags["artist"])
			if name == "":
				n = os.path.split(file)[1].split(".")
				name = ".".join([k for k in n[:-1]])
			name = "<b><i>%s</i></b>"%name
			name = self.strip_XML_entities(name)
			if album !="":
				name += "\n from <i>%s</i>"%album
			if artist != "":
				name += "\n by <i>%s</i>"%artist
		if prepend:
			func = self.model.prepend
		else:
			func = self.model.append
		iter = func(NAME,name,
				PATH,file,
				PIX,self.blank_pix,
				TYPE,t,
				ALBUM,album,
				ARTIST,artist,
				TN,int(tn),
				SEARCH,",".join([tags["title"],tags["album"],tags["artist"]]),
				PLAY_COUNT,0,
				GENRE,tags["genre"]
				)

		self.library_lib[file] = {"title":name,
				"type":t,"artist":artist,
				"album":album,"track_number":int(tn),
				"playcount":0,
				"time":'0:00',
				"genre":tags['genre']}
		self.save()

	def QueueHandlerKey(self, widget, event): 
		"""
		Handler the key-press-event in the queue list
		"""
		if (event.keyval == gtk.gdk.keyval_from_name('Delete')):
			selection     = self.tv.get_selection()
			(model, iter) = selection.get_selected()

			if (iter is not None):
				name = model.get_value(iter, NAME)
				self.remove(iter)
				
	def	checkQueue(self):
		model = self.tv.get_model()
		if (model != None):
			b = model.get_iter_first()
			if b == None:
				self.scroll.hide()
			else:
				self.scroll.show()
		return True
	
	def itemActivated(self,widget, path, iter):
		libraryBase.itemActivated(self, widget, path, iter)
		model    = widget.get_model()
		model.remove(iter)
