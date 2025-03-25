#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2013 Deepin, Inc.
#               2013 Hailong Qiu
#
# Author:     Hailong Qiu <356752238@qq.com>
# Maintainer: Hailong Qiu <356752238@qq.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import gtk
import pangocairo
import cairo
from Xlib import display, error, Xatom, X
import Xlib.protocol.event
from trayicon_plugin_manage import PluginManage
from vtk.statusicon import Element
from vtk.utils import propagate_expose
from vtk.window import TrayIconWin
from vtk.unique_service import UniqueService, is_exists
import dbus
import sys


APP_DBUS_NAME = "com.deepin.trayicon"
APP_OBJECT_NAME = "/com/deepin/trayicon"

TRAY_HEIGHT = 16
plugin_ids = ["date_time", 
              "shutdown", 
              "sound", 
              "network", 
              "mount_media", 
              "power", 
              "bluetooth"
              ]

class TrayIcon(TrayIconWin):
    def __init__(self):
        TrayIconWin.__init__(self)
        if is_exists(APP_DBUS_NAME, APP_OBJECT_NAME): 
            sys.exit()
        app_bus_name = dbus.service.BusName(APP_DBUS_NAME, bus=dbus.SessionBus())
        UniqueService(app_bus_name, APP_DBUS_NAME, APP_OBJECT_NAME)
        self.__save_trayicon = None
        self.__find_tray_dock_check = True
        self.__find_tray_dock_num   = 3
        self.metry = None
        self.__save_width = 0
        self.tray_icon_to_screen_width=10
        root = self.get_root_window()
        self.menu_screen = root.get_screen()
        #
        self.plugin_manage = PluginManage()
        self.tray_window   = None
        self.dock_selection = None
        self.atom_names = [
                None, 
                "MANAGER", 
                "_NET_SYSTEM_TRAY_OPCODE",
                "_NET_SYSTEM_TRAY_OPIENTATION",
                "_NET_SYSTEM_TRAY_VISUAL"
                ]
        #
        self.display = display.Display() 
        #print "display:", self.display
        self.screen   = self.display.screen()
        # 
        self.__init_tray_window()

    def __init_tray_window(self):
        self.__main_hbox = gtk.HBox()
        # 加载插件.
        for id in plugin_ids:
            print "id:", id
            if self.plugin_manage.key_dict.has_key(id):
                p_class = self.plugin_manage.key_dict[id]
                gtk.timeout_add(20, self.__load_plugin_timeout, p_class)
                #self.__load_plugin_timeout(p_class)
        #
        self.tray_window   = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.tray_window.add_events(gtk.gdk.ALL_EVENTS_MASK)
        self.tray_window.add(self.__main_hbox)
        self.tray_window.connect("expose-event", self.__window_expose_event)
        self.tray_window.set_decorated(False)
        self.tray_window.set_app_paintable(True)
        self.tray_window.set_wmclass("deepintrayicon", "DeepinTrayIcon")
        self.tray_window.connect("unmap", self.__tray_window_unmap_event)
        self.tray_window.set_colormap(gtk.gdk.Screen().get_rgba_colormap())
        self.tray_window.set_skip_pager_hint(True)
        self.tray_window.set_skip_taskbar_hint(True)
        self.tray_window.show_all()

        screen  = self.tray_window.get_screen()
        display = screen.get_display()
        root_win = screen.get_root_window()
        root_win.add_filter(self.__tray_icon_manager_filter)
        #
        self.init_tray()
        self.__tray_find_dock()

    def __tray_window_unmap_event(self, widget):
        self.__find_tray_dock_check = True
        self.__find_tray_dock_num   = 3

    def __load_plugin_timeout(self, p_class):
        _class = p_class()
        widget = Element()
        widget.set_size_request(-1, TRAY_HEIGHT)
        _class.init_values([self, widget])
        widget.set_text("")
        widget.connect('popup-menu-event', self.__tray_icon_popup_menu, _class)
        widget.connect("hide",             self.widget_hide_modify_statusicon_size)
        widget.connect("size-allocate",    self.widget_realize_event)
        #
        self.__main_hbox.pack_end(widget)
        self.__main_hbox.show_all()

    def __tray_icon_popup_menu(self, 
                             statusicon, 
                             geometry,
                             plug
                             ):
        self.init_popup_menu(statusicon, plug)

    def container_remove_all(self, container):
        container.foreach(lambda widget: container.remove(widget))

    def init_popup_menu(self, statusicon, plug):
        self.container_remove_all(self.main_ali)
        widget = plug.plugin_widget()
        self.__save_trayicon = plug
        plug.show_menu()
        self.add_plugin(widget)
        self.metry = statusicon.get_geometry()
        self.show_menu()

    def menu_configure_event(self, widget, event):
        self.resize(1, 1)
        self.move_menu() 

    def show_menu(self):
        '''
        # run plug show menu function.
        if self.save_trayicon:
            self.save_trayicon.show_menu()
        '''
        self.move_menu()
        self.show_all()

    def tray_icon_button_press(self, widget, event):        
        if self.in_window_check(widget, event):
            self.hide_menu()

    def hide_menu(self):
        if self.__save_trayicon:
            self.__save_trayicon.hide_menu()
        self.hide_all()        
        self.grab_remove()

    def move_menu(self):        
        if self.metry:
            metry = self.metry  
            # tray_icon_rect[0]: x tray_icon_rect[1]: y t...t[2]: width t...t[3]: height
            tray_icon_rect = metry[1]        
            # get screen height and width. 
            screen_h = self.menu_screen.get_height()
            screen_w = self.menu_screen.get_width()       
            # get x.
            x = tray_icon_rect[0] + tray_icon_rect[2]/2 - self.get_size_request()[0]/2
            x -= self.set_max_show_menu(x)
            # get y.
            y_padding_to_creen = self.get_size_request()[1]#self.allocation.height
            if self.allocation.height <= 1:
                y_padding_to_creen = self.get_size_request()[1]
            # 
            if (screen_h / 2) <= tray_icon_rect[1] <= screen_h: # bottom trayicon show.
                y = tray_icon_rect[1]
                self.move(x, y - y_padding_to_creen)
            else: # top trayicon show.
                y = tray_icon_rect[1]
                self.move(x, y + tray_icon_rect[3])
            #
            self.offset = (tray_icon_rect[0] - self.get_position()[0] 
                        - (self.arrow_width / 2) + (tray_icon_rect[2]/2))

    def set_max_show_menu(self, x):        
        screen_w = self.menu_screen.get_width()        
        screen_rect_width = x + self.get_size_request()[0]
        if (screen_rect_width) > screen_w:
            return screen_rect_width - screen_w + self.tray_icon_to_screen_width
        else:
            return 0

    def __tray_icon_manager_filter(self, event):
        #print "__tray_icon_manager_filter:", event
        if self.tray_window == None:
            self.__init_tray_window()
        return self.__tray_find_dock()

    def __window_expose_event(self, widget, event):
        cr = widget.window.cairo_create()
        rect = widget.allocation
        x, y, w, h = rect
        #
        cr.rectangle(*rect)
        cr.set_source_rgba(1, 1, 1, 0.0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        #
        cr = widget.window.cairo_create()
        #
        propagate_expose(widget, event) 
        return True

    def init_tray(self):
        #print "init_tray..."
        self.atom_names[0] = "_NET_SYSTEM_TRAY_S%d" % (self.display.get_default_screen())
        #
        for atom_name in self.atom_names:
            #print "atom_name:", atom_name
            self.display.intern_atom(atom_name)
        self.opcode_atom = self.display.intern_atom(self.atom_names[2])
        self.visual_atom = self.display.intern_atom(self.atom_names[4])
        # 
        return True

    def __tray_find_dock(self):
        print "find check:", self.__find_tray_dock_check
        if self.__find_tray_dock_check:
            self.__find_tray_dock_num -= 1
            if self.__find_tray_dock_num == 0:
                self.__find_tray_dock_check = False
            #print "tray_find_dock..."
            self.dock_atom = self.display.intern_atom(self.atom_names[0])
            self.dock_selection  = self.display.get_selection_owner(self.dock_atom)

            if self.dock_selection:
                #print "dock_selection:", self.dock_selection.id
                pass

            if self.dock_selection: # 给 dock selection 发送消息.
                self.tray_win = self.display.create_resource_object("window", self.dock_selection.id)
                self.tray_win.get_full_property(self.visual_atom, Xatom.VISUALID)
                if self.tray_window:
                    if self.tray_window.window:
                        self.tray_widget_wind = self.display.create_resource_object("window", self.tray_window.window.xid)
                    else:
                        self.__init_tray_window()
                        #self.__tray_find_dock()
                self.__tray_send_opcode(
                        self.tray_win,
                        self.opcode_atom,
                        [X.CurrentTime, 0L, self.tray_widget_wind.id, 0L, 0L],
                        X.NoEventMask
                        )
                self.display.flush()
                self.tray_window.show_all()
                return False;
            else: # 如果 dock selection 不存在.
                self.__release_tray_window()

        return True;

    def __tray_send_opcode(self,
                         dock_win,
                         type,
                         data,
                         mask
                         ):
        data = (data + [0] * (5 - len(data)))[:5]
        new_event = Xlib.protocol.event.ClientMessage(
                    window      = dock_win.id,
                    client_type = type,
                    data        = (32, (data)),
                    type        = X.ClientMessage
                    )
        dock_win.send_event(new_event, event_mask=mask)
        

    def __release_tray_window(self):
        if None == self.tray_window:
            return ;
        else:
            self.tray_window.hide_all()
            return True
        self.tray_window.destroy()
        self.tray_window = None

    def widget_realize_event(self, widget, allocation):
        self.statusicon_modify_size()

    def widget_hide_modify_statusicon_size(self, widget):
        self.statusicon_modify_size()

    def statusicon_modify_size(self):
        width = 0
        for child in self.__main_hbox.get_children():
            if child.get_visible():
                width += child.get_size_request()[0]

        if self.__save_width != width:
            self.__save_width = width 
            self.tray_window.set_geometry_hints(None, 
                                           width, 
                                           TRAY_HEIGHT, 
                                           width, 
                                           TRAY_HEIGHT, 
                                           -1, -1, -1, -1, -1, -1)


    #############################################
    def get_tray_position(self):
        return self.tray_window.get_position()

    def get_tray_pointer(self):
        return self.tray_window.get_pointer()

if __name__ == "__main__":
    tray_icon = TrayIcon()
    gtk.main()





