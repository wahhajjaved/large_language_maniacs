#!/usr/bin/python2
# -*- encoding: utf-8 -*-
# -*- coding: utf-8 -*-

'''
 This program source code file is part of pySearchTree, a text files search application.
 
 Copyright  © 2015 by LordBlick (at) gmail.com
 
 This program is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License
 as published by the Free Software Foundation; either version 2
 of the License, or (at your option) any later version.
 
 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.
 
 You should have received a copy of the GNU General Public License
 along with this program; if not, you may find one here:
 http://www.gnu.org/licenses/old-licenses/gpl-2.0.html
 or you may search the http://www.gnu.org website for the version 2 license,
 or you may write to the Free Software Foundation, Inc.,
 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
'''

from txtViewSrch import searchTextView
from wgts import gtk, pango
import wgts as wg
class massFindUI:
	def __init__(ui):
		ui.fontDesc = pango.FontDescription('Univers,Sans Condensed 7')
		ui.fontSmall = pango.FontDescription('Univers,Sans Condensed 8')
		ui.fontFixedDesc = pango.FontDescription('Terminus,Monospace Bold 7')
		wg.BGcolor = gtk.gdk.Color('#383430')
		wg.FGcolor = gtk.gdk.Color('#FFF')
		wg.BGcolorEntry = gtk.gdk.Color('#201810')
		wg.Height = 22
		ui.uiInit()
		if __name__ == "__main__":
			ui.mainWindow.connect("destroy", lambda w: gtk.main_quit())
			ui.buttonExit.connect("clicked", lambda w: gtk.main_quit())
			ui.logView.insert_end("User Interface Test...\n")
			ui.uiEnter()

	uiEnter = lambda ui: gtk.main()
	uiExit = lambda ui: gtk.main_quit()

	def uiInit(ui):
		from os import path as ph
		rp = ui.runpath = ph.dirname(ph.realpath(__file__))
		import dlgEngine
		ui.dlgEngine = dlgEngine.DialogEngine(ui)
		dlgEngine.debug = __name__ == "__main__"
		global _dbg
		_dbg = dlgEngine
		_dbg("runpath: %s\n" % rp)
		if __name__ == "__main__":
			ui.cfg = {}
		from gobject import TYPE_STRING as goStr, TYPE_INT as goInt, TYPE_PYOBJECT as goPyObj
		ui.title="pySearchTree V.0.8"
		ui.mainWindow = gtk.Window(gtk.WINDOW_TOPLEVEL)
		w, h = ui.wBase, ui.hBase = (510, 350)
		ui.mainWindow.set_geometry_hints(
			min_width=w, min_height=h)
		ui.mainWindow.resize(w, h)
		ui.mainWindow.set_title(ui.title)
		ui.mainWindow.set_border_width(5)
		ui.accGroup = gtk.AccelGroup()
		ui.mainWindow.add_accel_group(ui.accGroup)
		ui.mainWindow.modify_bg(gtk.STATE_NORMAL, wg.BGcolor)
		ui.cfBPixbuf = gtk.gdk.pixbuf_new_from_file(rp+"pic/logview.png")
		gtk.window_set_default_icon_list(ui.cfBPixbuf, )
		
		ui.mainFrame = gtk.Fixed()

		ui.logView = wg.TextView(ui.mainFrame, 5, 5, 0, 0,
			bEditable=False, tabSpace=4, fontDesc = ui.fontFixedDesc)
		ui.stv = searchTextView(ui, ui.mainWindow, ui.logView)

		ui.labFileset = wg.Label("Type:", ui.mainFrame, 0, 0, 32)
		ui.lsFileset = gtk.ListStore(goStr, goStr, goPyObj)
		ui.cbFileset = wg.ComboBox(ui.lsFileset, ui.mainFrame, 0, 0, 130, wrap=2)

		ui.toggRoot = wg.Toggle("Choose dir...\t", ui.mainFrame, 0,  0, 0)

		ui.toggMaskHome = wg.Toggle("~", ui.mainFrame, 0,  0, 25)
		ui.toggMaskHome.set_tooltip_text('Toggle Mask Home')

		ui.toggSrchInfo = wg.Toggle("?", ui.mainFrame, 0,  0, 25)
		ui.toggSrchInfo.set_tooltip_text('Toggle Startup Search Info')

		ui.buttonSearchLog = wg.Butt(None, ui.mainFrame, 0, 0, 25, height=25, stockID=gtk.STOCK_FIND)
		ui.buttonSearchLog.add_accelerator("clicked", ui.accGroup, ord('F'),
			gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE)
		ui.buttonSearchLog.connect("clicked", ui.stv.showDlgSrch)

		ui.labFindPhrase = wg.Label("Phrase:", ui.mainFrame, 0, 0, 37)
		ui.txtFindPhrase = wg.Entry(ui.mainFrame, 0, 0, 190, clearIco=True)

		ui.buttonFind = wg.Butt("Find", ui.mainFrame, 0,  0, 50)

		ui.buttonBreak = wg.Butt("Stop", ui.mainFrame, 0,  0, 50)

		ui.buttonClear = wg.Butt("Clear", ui.mainFrame, 0,  0, 50)
		ui.buttonClear.connect("clicked", lambda x: ui.logView.clear_text())

		ui.buttonExit = wg.Butt("Exit (Ctrl+Q)", ui.mainFrame, 0, 0, 80)
		ui.buttonExit.add_accelerator(
			"clicked",
			ui.accGroup,
			ord('Q'),
			gtk.gdk.CONTROL_MASK,
			gtk.ACCEL_VISIBLE)
		
		ui.mainWindow.add(ui.mainFrame)
		ui.mainWindow.show_all()
		ui.mainWindow.set_keep_above(True)
		ui.lastWinSize = None
		ui.mainWindow.connect("configure-event", ui.uiSize)

	def uiSize(ui, window, event):
		if event.type==gtk.gdk.CONFIGURE:
			w, h = event.width, event.height
			if ui.lastWinSize==(w, h):
				return True
			ui.lastWinSize = w, h
			y = h-70
			ui.logView.set_size_request(w-20, h-80)
			ui.mainFrame.move(ui.labFileset, 5, y)
			ui.mainFrame.move(ui.cbFileset, 40, y-2)
			ui.mainFrame.move(ui.toggRoot, 175, y)
			ui.toggRoot.set_size_request(w-280, wg.Height)
			ui.mainFrame.move(ui.toggMaskHome, w-100, y)
			ui.mainFrame.move(ui.toggSrchInfo,  w-70, y)
			ui.mainFrame.move(ui.buttonSearchLog, w-40, y-1)
			y += 30
			ui.mainFrame.move(ui.labFindPhrase, 5, y)
			ui.mainFrame.move(ui.txtFindPhrase, 45, y-1)
			ui.txtFindPhrase.set_size_request(w-320, 25)
			ui.mainFrame.move(ui.buttonFind, w-265, y)
			ui.mainFrame.move(ui.buttonBreak, w-210, y)
			ui.mainFrame.move(ui.buttonClear, w-155, y)
			ui.mainFrame.move(ui.buttonExit, w-95, y)
			return True

	def restoreGeometry(ui):
		if hasattr(ui, 'stv') and(ui.cfg['dlgSrchPos']):
			ui.stv.dlgSrchPos =  tuple(map(lambda k: int(k), ui.cfg['dlgSrchPos'].split(',')))
		ui.rGeo(ui.mainWindow, 'MainWindowGeometry')

	def storeGeometry(ui):
		if hasattr(ui, 'stv'):
			stv = ui.stv
			stv.hideDlgSrch()
			if stv.dlgSrchPos:
				ui.cfg['dlgSrchPos'] = "%i,%i" % stv.dlgSrchPos
		ui.cfg['MainWindowGeometry'] = ui.sGeo(ui.mainWindow)

# Entry point
if __name__ == "__main__":
	massFindUI()
