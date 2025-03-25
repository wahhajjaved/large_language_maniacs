#!/usr/bin/env python2
"""
Syncthing-GTK - InfoBox

Colorfull, expandlable widget displaying folder/device data
"""
from __future__ import unicode_literals
from gi.repository import Gtk, Gdk, GLib, GObject, Pango
from syncthing_gtk import DEBUG
import os, math
_ = lambda (a) : a

COLOR_CHANGE_TIMER	= 10	# ms
COLOR_CHANGE_STEP	= 0.05
HILIGHT_INTENSITY	= 0.3	# 0.0 to 1.0

class InfoBox(Gtk.Container):
	""" Expandlable widget displaying folder/device data """
	__gtype_name__ = "InfoBox"
	__gsignals__ = {
			# right-click(button, time)
			b"right-click"	: (GObject.SIGNAL_RUN_FIRST, None, (int, int)),
		}
	
	### Initialization
	def __init__(self, app, title, icon):
		# Variables
		self.app = app
		self.child = None
		self.header = None
		self.str_title = None
		self.header_inverted = False
		self.values = {}
		self.value_widgets = {}
		self.hilight = False
		self.hilight_factor = 0.0
		self.timer_enabled = False
		self.icon = icon
		self.color = (1, 0, 1, 1)		# rgba
		self.background = (1, 1, 1, 1)	# rgba
		self.real_color = self.color	# set color + hilight
		self.border_width = 2
		self.children = [self.header, self.child]
		# Initialization
		Gtk.Container.__init__(self)
		self.init_header()
		self.init_grid()
		# Settings
		self.set_title(title)
		self.set_status(_("Disconnected"))
	
	def init_header(self):
		# Create widgets
		eb = Gtk.EventBox()
		self.title = Gtk.Label()
		self.status = Gtk.Label()
		hbox = Gtk.HBox()
		# Set values
		self.title.set_alignment(0.0, 0.5)
		self.status.set_alignment(1.0, 0.5)
		self.title.set_ellipsize(Pango.EllipsizeMode.START)
		hbox.set_spacing(4)
		# Connect signals
		eb.connect("realize", self.set_header_cursor)
		eb.connect("button-release-event", self.on_header_click)
		eb.connect('enter-notify-event', self.on_enter_notify)
		eb.connect('leave-notify-event', self.on_leave_notify)
		# Pack together
		hbox.pack_start(self.icon, False, False, 0)
		hbox.pack_start(self.title, True, True, 0)
		hbox.pack_start(self.status, False, False, 0)
		hbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*self.color))
		eb.add(hbox)
		# Update stuff
		self.header_box = hbox
		self.header = eb
		self.header.set_parent(self)
		self.children = [self.header, self.child]
	
	def init_grid(self):
		# Create widgets
		self.grid = Gtk.Grid()
		self.rev = Gtk.Revealer()
		align = Gtk.Alignment()
		eb = Gtk.EventBox()
		# Set values
		self.grid.set_row_spacing(1)
		self.grid.set_column_spacing(3)
		self.rev.set_reveal_child(False)
		align.set_padding(2, 2, 5, 5)
		eb.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1,1,1,1))
		self.grid.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1,1,1,1))
		# Connect signals
		eb.connect("button-release-event", self.on_grid_click)
		eb.connect('enter-notify-event', self.on_enter_notify)
		eb.connect('leave-notify-event', self.on_leave_notify)
		# Pack together
		align.add(self.grid)
		eb.add(align)
		self.rev.add(eb)
		self.add(self.rev)
	
	### GtkWidget-related stuff
	def do_add(self, widget):
		if not widget is None:
			if self.child is None:
				self.child = widget
				self.children = [self.header, self.child]
				widget.set_parent(self)
 
	def do_remove(self, widget):
		if self.child == widget:
			self.child = None
			self.children = [self.header, self.child]
			widget.unparent()
 
	def do_child_type(self):
		return(Gtk.Widget.get_type())
 
	def do_forall(self, include_internals, callback, *callback_parameters):
		if not callback is None:
			if hasattr(self, 'children'): # No idea why this happens...
				for c in self.children:
					if not c is None:
						callback(c, *callback_parameters)
 
	def do_get_request_mode(self):
		return(Gtk.SizeRequestMode.CONSTANT_SIZE)
 
	def do_get_preferred_height(self):
		mw, nw, mh, nh = self.get_prefered_size()
		return(mh, nh)
 
	def do_get_preferred_width(self):
		mw, nw, mh, nh = self.get_prefered_size()
		return(mw, nw)
	
	def get_prefered_size(self):
		""" Returns (min_width, nat_width, min_height, nat_height) """
		min_width, nat_width = 0, 0
		min_height, nat_height = 0, 0
		# Use max of prefered widths from children;
		# Use sum of predered height from children.
		for c in self.children:
			if not c is None:
				if c != self.rev or self.rev.get_reveal_child():
					mw, nw = c.get_preferred_width()
					mh, nh = c.get_preferred_height()
					min_width = max(min_width, mw)
					nat_width = max(nat_width, nw)
					min_height = min_height + mh
					nat_height = nat_height + nh
		# Add border size
		min_width += self.border_width * 2	# Left + right border
		nat_width += self.border_width * 2
		min_height += self.border_width * 3	# Top + bellow header + bottom
		nat_height += self.border_width * 3
		return(min_width, nat_width, min_height, nat_height)
 
	def do_size_allocate(self, allocation):
		child_allocation = Gdk.Rectangle()
		child_allocation.x = self.border_width
		child_allocation.y = self.border_width
 
		self.set_allocation(allocation)
 
		if self.get_has_window():
			if self.get_realized():
				self.get_window().move_resize(allocation.x, allocation.y, allocation.width, allocation.height)
		
		# Allocate childrens as VBox does, always use all available width
		for c in self.children:
			if not c is None:
				if c.get_visible():
					min_size, nat_size = c.get_preferred_size()
					child_allocation.width = allocation.width - (self.border_width * 2)
					child_allocation.height = min_size.height
					# TODO: Handle child that has window (where whould i get it?)
					c.size_allocate(child_allocation)
					child_allocation.y += child_allocation.height + self.border_width

 
	def do_realize(self):
		allocation = self.get_allocation()
 
		attr = Gdk.WindowAttr()
		attr.window_type = Gdk.WindowType.CHILD
		attr.x = allocation.x
		attr.y = allocation.y
		attr.width = allocation.width
		attr.height = allocation.height
		attr.visual = self.get_visual()
		attr.event_mask = self.get_events() | Gdk.EventMask.EXPOSURE_MASK
 
		WAT = Gdk.WindowAttributesType
		mask = WAT.X | WAT.Y | WAT.VISUAL
 
		window = Gdk.Window(self.get_parent_window(), attr, mask);
		window.set_decorations(0)
		self.set_window(window)
		self.register_window(window)
		self.set_realized(True)
 
	def do_draw(self, cr):
		allocation = self.get_allocation()
		
		if self.background is None:
			# Use default window background
			Gtk.render_background(self.get_style_context(), cr,
					self.border_width,
					self.border_width,
					allocation.width - (2 * self.border_width),
					allocation.height - (2 * self.border_width)
					)
		
		header_al = self.children[0].get_allocation()
		
		# Border
		cr.set_source_rgba(*self.real_color)
		cr.move_to(0, self.border_width / 2.0)
		cr.line_to(0, allocation.height)
		cr.line_to(allocation.width, allocation.height)
		cr.line_to(allocation.width, self.border_width / 2.0)
		cr.set_line_width(self.border_width * 2) # Half of border is rendered outside of widget
		cr.stroke()
		
		# Background
		if not self.background is None:
			# Use set background color
			cr.set_source_rgba(*self.background)
			cr.rectangle(self.border_width,
					self.border_width,
					allocation.width - (2 * self.border_width),
					allocation.height - (2 * self.border_width)
					)
			cr.fill()
		
		# Header
		cr.set_source_rgba(*self.real_color)
		cr.rectangle(self.border_width / 2.0, 0, allocation.width - self.border_width, header_al.height + (2 * self.border_width))
		cr.fill()
		
		for c in self.children:
			if not c is None:
				self.propagate_draw(c, cr)
            
	### InfoBox logic
	def set_header_cursor(self, eb, *a):
		""" Sets cursor over top part of infobox to hand """
		eb.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.HAND1))
	
	def on_header_click(self, eventbox, event):
		"""
		Hides or reveals everything bellow header
		Displays popup menu on right click
		"""
		if event.button == 1:	# left
			self.rev.set_reveal_child(not self.rev.get_reveal_child())
			self.app.cb_open_closed(self)
		elif event.button == 3:	# right
			self.emit('right-click', event.button, event.time)
	
	def on_grid_click(self, eventbox, event):
		""" Displays popup menu on right click """
		if event.button == 3:	# right
			self.emit('right-click', event.button, event.time)
	
	def hilight_timer(self, *a):
		""" Called repeatedly while color is changing """
		if self.hilight and self.hilight_factor < 1.0:
			self.hilight_factor = min(1.0, self.hilight_factor + COLOR_CHANGE_STEP)
		elif not self.hilight and self.hilight_factor > 0.0:
			self.hilight_factor = max(0.0, self.hilight_factor - COLOR_CHANGE_STEP)		
		else:
			self.timer_enabled = False
		self.recolor()
		return self.timer_enabled
	
	def recolor(self, *a):
		"""
		Called to computes actual color every time when self.color or
		self.hilight_factor changes.
		"""
		self.real_color = tuple([ min(1.0, x + HILIGHT_INTENSITY * math.sin(self.hilight_factor)) for x in self.color])
		gdkcol = Gdk.RGBA(*self.real_color)
		self.header.override_background_color(Gtk.StateType.NORMAL, gdkcol)
		try:
			self.header.get_children()[0].override_background_color(Gtk.StateFlags.NORMAL, gdkcol)
		except IndexError:
			# Happens when recolor is called before header widget is created
			pass

		self.queue_draw()
	
	### Translated events
	def on_enter_notify(self, eb, event, *data):
		self.emit("enter-notify-event", None, *data)
	
	def on_leave_notify(self, eb, event, *data):
		self.emit("leave-notify-event", None, *data)
	
	### Methods
	def set_title(self, t):
		self.str_title = t
		if self.header_inverted:
			self.title.set_markup('<span font_weight="bold" font_size="large" color="black">%s</span>' % t)
		else:
			self.title.set_markup('<span font_weight="bold" font_size="large" color="white">%s</span>' % t)
	
	def get_title(self):
		return self.str_title
	
	def set_icon(self, icon):
		self.header_box.remove(self.icon)
		self.header_box.pack_start(icon, False, False, 0)
		self.header_box.reorder_child(icon, 0)
		self.header_box.show_all()
		self.icon = icon
	
	def set_hilight(self, h):
		if self.hilight != h:
			self.hilight = h
			if not self.timer_enabled:
				GLib.timeout_add(COLOR_CHANGE_TIMER, self.hilight_timer)
				self.timer_enabled = True
	
	def invert_header(self, e):
		self.header_inverted = e
		self.set_title(self.str_title)
	
	def set_status(self, t, percentage=0.0):
		if percentage > 0.0 and percentage < 1.0:
			percent = percentage * 100.0
			self.status.set_markup('<span font_weight="bold" font_size="large" color="white">%s (%.f%%)</span>' % (t, percent))
			if DEBUG : print "%s state changed to %s (%s%%)" % (self.str_title, t, percent)
		else:
			self.status.set_markup('<span font_weight="bold" font_size="large" color="white">%s</span>' % t)
			if DEBUG : print "%s state changed to %s" % (self.str_title, t)
	
	def set_color_hex(self, hx):
		""" Expects AABBCC or #AABBCC format """
		hx = hx.lstrip('#')
		l = len(hx)
		color = [ float(int(hx[i:i+l/3], 16)) / 255.0 for i in range(0, l, l/3) ]
		while len(color) < 4:
			color.append(1.0)
		self.set_color(*color)
		
	def set_color(self, r, g, b, a):
		""" Expects floats """
		self.color = (r, g, b, a)
		self.recolor()
	
	def set_border(self, width):
		self.border_width = width
		self.queue_resize()
	
	def set_open(self, b):
		self.rev.set_reveal_child(b)
	
	def is_open(self):
		""" Returns True if box is open """
		return self.rev.get_reveal_child()
	
	def add_value(self, key, icon, title, value, visible=True):
		""" Adds new line with provided properties """
		if "." in icon:
			# Icon is filename
			wIcon = Gtk.Image.new_from_file(os.path.join(self.app.iconpath, icon))
		else:
			# Icon is theme icon name
			wIcon = Gtk.Image.new_from_icon_name(icon, 1)
		wTitle, wValue = Gtk.Label(), Gtk.Label()
		self.value_widgets[key] = (wValue, wIcon, wTitle)
		self.set_value(key, value)
		wTitle.set_text(title)
		wTitle.set_alignment(0.0, 0.5)
		wValue.set_alignment(1.0, 0.5)
		wValue.set_ellipsize(Pango.EllipsizeMode.START)
		wTitle.set_property("expand", True)
		line = len(self.value_widgets)
		self.grid.attach(wIcon, 0, line, 1, 1)
		self.grid.attach_next_to(wTitle, wIcon, Gtk.PositionType.RIGHT, 1, 1)
		self.grid.attach_next_to(wValue, wTitle, Gtk.PositionType.RIGHT, 1, 1)
		if not visible:
			for w in self.value_widgets[key]:
				w.set_no_show_all(True)
	
	def clear_values(self):
		""" Removes all lines from UI, efectively making all values hidden """
		for ch in [ ] + self.grid.get_children():
			self.grid.remove(ch)
		self.value_widgets = {}
	
	def add_hidden_value(self, key, value):
		""" Adds value that is saved, but not shown on UI """
		self.set_value(key, value)
	
	def set_value(self, key, value):
		""" Updates already existing value """
		self.values[key] = value
		if key in self.value_widgets:
			if value is None:
				self.value_widgets[key][0].set_text("?")
			else:
				self.value_widgets[key][0].set_text(value)
	
	def hide_value(self, key):
		""" Hides value added by add_value """
		if key in self.value_widgets:
			for w in self.value_widgets[key]:
				w.set_no_show_all(True)
				w.set_visible(False)
	
	def show_value(self, key):
		""" Shows value added by add_value """
		if key in self.value_widgets:
			for w in self.value_widgets[key]:
				w.set_no_show_all(False)
				w.set_visible(True)
	
	def hide_values(self, *keys):
		""" Same as hide_value, but for multiple keys at once """
		for k in keys: self.hide_value(k)
	
	def show_values(self, *keys):
		""" Same as show_value, but for multiple keys at once """
		for k in keys: self.show_value(k)
	
	def get_value(self, key):
		return self.values[key]
	
	def __getitem__(self, key):
		""" Shortcut to get_value """
		return self.values[key]
	
	def __setitem__(self, key, value):
		""" Shortcut to set_value. Creates new hidden_value if key doesn't exist """
		self.set_value(key, value)
