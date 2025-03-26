from __future__ import absolute_import

import wx
import os
import webbrowser

from Cura.gui import configBase
from Cura.gui import expertConfig
from Cura.gui import preview3d
from Cura.gui import sliceProgressPanel
from Cura.gui import alterationPanel
from Cura.gui import pluginPanel
from Cura.gui import preferencesDialog
from Cura.gui import configWizard
from Cura.gui import firmwareInstall
from Cura.gui import printWindow
from Cura.gui import simpleMode
from Cura.gui import projectPlanner
from Cura.gui.tools import batchRun
from Cura.gui import flatSlicerWindow
from Cura.gui.util import dropTarget
from Cura.gui.tools import minecraftImport
from Cura.util import validators
from Cura.util import profile
from Cura.util import version
from Cura.util import sliceRun
from Cura.util import meshLoader

class mainWindow(wx.Frame):
	def __init__(self):
		super(mainWindow, self).__init__(None, title='Cura - ' + version.getVersion())

		self.extruderCount = int(profile.getPreference('extruder_amount'))

		wx.EVT_CLOSE(self, self.OnClose)

		self.SetDropTarget(dropTarget.FileDropTarget(self.OnDropFiles, meshLoader.supportedExtensions()))

		self.normalModeOnlyItems = []

		mruFile = os.path.join(profile.getBasePath(), 'mru_filelist.ini')
		self.config = wx.FileConfig(appName="Cura", 
						localFilename=mruFile,
						style=wx.CONFIG_USE_LOCAL_FILE)
						
		self.ID_MRU_MODEL1, self.ID_MRU_MODEL2, self.ID_MRU_MODEL3, self.ID_MRU_MODEL4, self.ID_MRU_MODEL5, self.ID_MRU_MODEL6, self.ID_MRU_MODEL7, self.ID_MRU_MODEL8, self.ID_MRU_MODEL9, self.ID_MRU_MODEL10 = [wx.NewId() for line in xrange(10)]
		self.modelFileHistory = wx.FileHistory(10, self.ID_MRU_MODEL1)
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Load(self.config)

		self.ID_MRU_PROFILE1, self.ID_MRU_PROFILE2, self.ID_MRU_PROFILE3, self.ID_MRU_PROFILE4, self.ID_MRU_PROFILE5, self.ID_MRU_PROFILE6, self.ID_MRU_PROFILE7, self.ID_MRU_PROFILE8, self.ID_MRU_PROFILE9, self.ID_MRU_PROFILE10 = [wx.NewId() for line in xrange(10)]
		self.profileFileHistory = wx.FileHistory(10, self.ID_MRU_PROFILE1)
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Load(self.config)

		self.menubar = wx.MenuBar()
		self.fileMenu = wx.Menu()
		i = self.fileMenu.Append(-1, 'Load model file...\tCTRL+L')
		self.Bind(wx.EVT_MENU, lambda e: self._showModelLoadDialog(1), i)
		i = self.fileMenu.Append(-1, 'Prepare print...\tCTRL+R')
		self.Bind(wx.EVT_MENU, self.OnSlice, i)
		i = self.fileMenu.Append(-1, 'Print...\tCTRL+P')
		self.Bind(wx.EVT_MENU, self.OnPrint, i)

		self.fileMenu.AppendSeparator()
		i = self.fileMenu.Append(-1, 'Open Profile...')
		self.normalModeOnlyItems.append(i)
		self.Bind(wx.EVT_MENU, self.OnLoadProfile, i)
		i = self.fileMenu.Append(-1, 'Save Profile...')
		self.normalModeOnlyItems.append(i)
		self.Bind(wx.EVT_MENU, self.OnSaveProfile, i)
		i = self.fileMenu.Append(-1, 'Load Profile from GCode...')
		self.normalModeOnlyItems.append(i)
		self.Bind(wx.EVT_MENU, self.OnLoadProfileFromGcode, i)
		self.fileMenu.AppendSeparator()
		i = self.fileMenu.Append(-1, 'Reset Profile to default')
		self.normalModeOnlyItems.append(i)
		self.Bind(wx.EVT_MENU, self.OnResetProfile, i)

		self.fileMenu.AppendSeparator()
		i = self.fileMenu.Append(-1, 'Preferences...\tCTRL+,')
		self.Bind(wx.EVT_MENU, self.OnPreferences, i)
		self.fileMenu.AppendSeparator()

		# Model MRU list
		modelHistoryMenu = wx.Menu()
		self.fileMenu.AppendMenu(wx.NewId(), "&Recent Model Files", modelHistoryMenu)
		self.modelFileHistory.UseMenu(modelHistoryMenu)
		self.modelFileHistory.AddFilesToMenu()
		self.Bind(wx.EVT_MENU_RANGE, self.OnModelMRU, id=self.ID_MRU_MODEL1, id2=self.ID_MRU_MODEL10)

		# Profle MRU list
		profileHistoryMenu = wx.Menu()
		self.fileMenu.AppendMenu(wx.NewId(), "&Recent Profile Files", profileHistoryMenu)
		self.profileFileHistory.UseMenu(profileHistoryMenu)
		self.profileFileHistory.AddFilesToMenu()
		self.Bind(wx.EVT_MENU_RANGE, self.OnProfileMRU, id=self.ID_MRU_PROFILE1, id2=self.ID_MRU_PROFILE10)
		
		self.fileMenu.AppendSeparator()
		i = self.fileMenu.Append(wx.ID_EXIT, 'Quit')
		self.Bind(wx.EVT_MENU, self.OnQuit, i)
		self.menubar.Append(self.fileMenu, '&File')

		toolsMenu = wx.Menu()
		i = toolsMenu.Append(-1, 'Switch to quickprint...')
		self.switchToQuickprintMenuItem = i
		self.Bind(wx.EVT_MENU, self.OnSimpleSwitch, i)
		i = toolsMenu.Append(-1, 'Switch to full settings...')
		self.switchToNormalMenuItem = i
		self.Bind(wx.EVT_MENU, self.OnNormalSwitch, i)
		toolsMenu.AppendSeparator()
		i = toolsMenu.Append(-1, 'Project planner...')
		self.Bind(wx.EVT_MENU, self.OnProjectPlanner, i)
		self.normalModeOnlyItems.append(i)
		i = toolsMenu.Append(-1, 'Batch run...')
		self.Bind(wx.EVT_MENU, self.OnBatchRun, i)
		self.normalModeOnlyItems.append(i)
		#		i = toolsMenu.Append(-1, 'Open SVG (2D) slicer...')
		#		self.Bind(wx.EVT_MENU, self.OnSVGSlicerOpen, i)
		if minecraftImport.hasMinecraft():
			i = toolsMenu.Append(-1, 'Minecraft import...')
			self.Bind(wx.EVT_MENU, self.OnMinecraftImport, i)
		self.menubar.Append(toolsMenu, 'Tools')

		expertMenu = wx.Menu()
		i = expertMenu.Append(-1, 'Open expert settings...')
		self.normalModeOnlyItems.append(i)
		self.Bind(wx.EVT_MENU, self.OnExpertOpen, i)
		expertMenu.AppendSeparator()
		if firmwareInstall.getDefaultFirmware() is not None:
			i = expertMenu.Append(-1, 'Install default Marlin firmware')
			self.Bind(wx.EVT_MENU, self.OnDefaultMarlinFirmware, i)
		i = expertMenu.Append(-1, 'Install custom firmware')
		self.Bind(wx.EVT_MENU, self.OnCustomFirmware, i)
		expertMenu.AppendSeparator()
		i = expertMenu.Append(-1, 'Run first run wizard...')
		self.Bind(wx.EVT_MENU, self.OnFirstRunWizard, i)
		i = expertMenu.Append(-1, 'Run bed leveling wizard...')
		self.Bind(wx.EVT_MENU, self.OnBedLevelWizard, i)
		self.menubar.Append(expertMenu, 'Expert')

		helpMenu = wx.Menu()
		i = helpMenu.Append(-1, 'Online documentation...')
		self.Bind(wx.EVT_MENU, lambda e: webbrowser.open('http://daid.github.com/Cura'), i)
		i = helpMenu.Append(-1, 'Report a problem...')
		self.Bind(wx.EVT_MENU, lambda e: webbrowser.open('https://github.com/daid/Cura/issues'), i)
		i = helpMenu.Append(-1, 'Check for update...')
		self.Bind(wx.EVT_MENU, self.OnCheckForUpdate, i)
		self.menubar.Append(helpMenu, 'Help')
		self.SetMenuBar(self.menubar)

		if profile.getPreference('lastFile') != '':
			self.filelist = profile.getPreference('lastFile').split(';')
			self.SetTitle('Cura - %s - %s' % (version.getVersion(), self.filelist[-1]))
		else:
			self.filelist = []
		self.progressPanelList = []

		self.splitter = wx.SplitterWindow(self, style = wx.SP_3D | wx.SP_LIVE_UPDATE)
		self.leftPane = wx.Panel(self.splitter, style=wx.BORDER_NONE)
		self.rightPane = wx.Panel(self.splitter, style=wx.BORDER_NONE)
		self.splitter.Bind(wx.EVT_SPLITTER_DCLICK, lambda evt: evt.Veto())

		##Gui components##
		self.simpleSettingsPanel = simpleMode.simpleModePanel(self.leftPane)
		self.normalSettingsPanel = normalSettingsPanel(self.leftPane)

		self.leftSizer = wx.BoxSizer(wx.VERTICAL)
		self.leftSizer.Add(self.simpleSettingsPanel)
		self.leftSizer.Add(self.normalSettingsPanel, 1, wx.EXPAND)
		self.leftPane.SetSizer(self.leftSizer)
		
		#Preview window
		self.preview3d = preview3d.previewPanel(self.rightPane)

		#Also bind double clicking the 3D preview to load an STL file.
		#self.preview3d.glCanvas.Bind(wx.EVT_LEFT_DCLICK, lambda e: self._showModelLoadDialog(1), self.preview3d.glCanvas)

		#Main sizer, to position the preview window, buttons and tab control
		sizer = wx.BoxSizer()
		self.rightPane.SetSizer(sizer)
		sizer.Add(self.preview3d, 1, flag=wx.EXPAND)

		# Main window sizer
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.SetSizer(sizer)
		sizer.Add(self.splitter, 1, wx.EXPAND)
		sizer.Layout()
		self.sizer = sizer

		if len(self.filelist) > 0:
			self.preview3d.loadModelFiles(self.filelist)

			# Update the Model MRU
			for idx in xrange(0, len(self.filelist)):
				self.addToModelMRU(self.filelist[idx])

		self.updateProfileToControls()

		self.SetBackgroundColour(self.normalSettingsPanel.GetBackgroundColour())

		self.simpleSettingsPanel.Show(False)
		self.normalSettingsPanel.Show(False)

		# Set default window size & position
		self.SetSize((wx.Display().GetClientArea().GetWidth()/2,wx.Display().GetClientArea().GetHeight()/2))
		self.Centre()

		# Restore the window position, size & state from the preferences file
		try:
			if profile.getPreference('window_maximized') == 'True':
				self.Maximize(True)
			else:
				posx = int(profile.getPreference('window_pos_x'))
				posy = int(profile.getPreference('window_pos_y'))
				width = int(profile.getPreference('window_width'))
				height = int(profile.getPreference('window_height'))
			if posx > 0 or posy > 0:
				self.SetPosition((posx,posy))
			if width > 0 and height > 0:
				self.SetSize((width,height))
				
			self.normalSashPos = int(profile.getPreference('window_normal_sash'))
			if self.normalSashPos < self.normalSettingsPanel.printPanel.GetBestSize()[0] + 5:
				self.normalSashPos = self.normalSettingsPanel.printPanel.GetBestSize()[0] + 5
		except:
			self.Maximize(True)

		self.splitter.SplitVertically(self.leftPane, self.rightPane, self.normalSashPos)

		if wx.Display.GetFromPoint(self.GetPosition()) < 0:
			self.Centre()
		if wx.Display.GetFromPoint((self.GetPositionTuple()[0] + self.GetSizeTuple()[1], self.GetPositionTuple()[1] + self.GetSizeTuple()[1])) < 0:
			self.Centre()
		if wx.Display.GetFromPoint(self.GetPosition()) < 0:
			self.SetSize((800,600))
			self.Centre()

		self.updateSliceMode()

		self.Show(True)

	def updateSliceMode(self):
		isSimple = profile.getPreference('startMode') == 'Simple'

		self.normalSettingsPanel.Show(not isSimple)
		self.simpleSettingsPanel.Show(isSimple)
		self.leftPane.Layout()

		for i in self.normalModeOnlyItems:
			i.Enable(not isSimple)
		self.switchToQuickprintMenuItem.Enable(not isSimple)
		self.switchToNormalMenuItem.Enable(isSimple)

		# Set splitter sash position & size
		if isSimple:
			# Save normal mode sash
			self.normalSashPos = self.splitter.GetSashPosition()
			
			# Change location of sash to width of quick mode pane 
			(width, height) = self.simpleSettingsPanel.GetSizer().GetSize() 
			self.splitter.SetSashPosition(width, True)
			
			# Disable sash
			self.splitter.SetSashSize(0)
		else:
			self.splitter.SetSashPosition(self.normalSashPos, True)
			# Enabled sash
			self.splitter.SetSashSize(4)
								
	def OnPreferences(self, e):
		prefDialog = preferencesDialog.preferencesDialog(self)
		prefDialog.Centre()
		prefDialog.Show(True)

	def _showOpenDialog(self, title, wildcard = meshLoader.wildcardFilter()):
		dlg=wx.FileDialog(self, title, os.path.split(profile.getPreference('lastFile'))[0], style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST)
		dlg.SetWildcard(wildcard)
		if dlg.ShowModal() == wx.ID_OK:
			filename = dlg.GetPath()
			dlg.Destroy()
			if not(os.path.exists(filename)):
				return False
			profile.putPreference('lastFile', filename)
			return filename
		dlg.Destroy()
		return False

	def _showModelLoadDialog(self, amount):
		filelist = []
		for i in xrange(0, amount):
			filelist.append(self._showOpenDialog("Open file to print"))
			if filelist[-1] == False:
				return
		self._loadModels(filelist)

	def _loadModels(self, filelist):
		self.filelist = filelist
		self.SetTitle('Cura - %s - %s' % (version.getVersion(), filelist[-1]))
		profile.putPreference('lastFile', ';'.join(self.filelist))
		self.preview3d.loadModelFiles(self.filelist, True)
		self.preview3d.setViewMode("Normal")
		
		# Update the Model MRU
		for idx in xrange(0, len(self.filelist)):
			self.addToModelMRU(self.filelist[idx])

	def OnDropFiles(self, files):
		profile.putProfileSetting('model_matrix', '1,0,0,0,1,0,0,0,1')
		profile.setPluginConfig([])
		self.updateProfileToControls()
		self._loadModels(files)

	def OnLoadModel(self, e):
		self._showModelLoadDialog(1)

	def OnLoadModel2(self, e):
		self._showModelLoadDialog(2)

	def OnLoadModel3(self, e):
		self._showModelLoadDialog(3)

	def OnLoadModel4(self, e):
		self._showModelLoadDialog(4)

	def OnSlice(self, e):
		if len(self.filelist) < 1:
			wx.MessageBox('You need to load a file before you can prepare it.', 'Print error', wx.OK | wx.ICON_INFORMATION)
			return
		isSimple = profile.getPreference('startMode') == 'Simple'
		if isSimple:
			#save the current profile so we can put it back latter
			oldProfile = profile.getGlobalProfileString()
			self.simpleSettingsPanel.setupSlice()
		#Create a progress panel and add it to the window. The progress panel will start the Skein operation.
		spp = sliceProgressPanel.sliceProgressPanel(self, self, self.filelist)
		self.sizer.Add(spp, 0, flag=wx.EXPAND)
		self.sizer.Layout()
		newSize = self.GetSize()
		newSize.IncBy(0, spp.GetSize().GetHeight())
		if newSize.GetWidth() < wx.GetDisplaySize()[0]:
			self.SetSize(newSize)
		self.progressPanelList.append(spp)
		if isSimple:
			profile.loadGlobalProfileFromString(oldProfile)

	def OnPrint(self, e):
		if len(self.filelist) < 1:
			wx.MessageBox('You need to load a file and prepare it before you can print.', 'Print error', wx.OK | wx.ICON_INFORMATION)
			return
		if not os.path.exists(sliceRun.getExportFilename(self.filelist[0])):
			wx.MessageBox('You need to prepare a print before you can run the actual print.', 'Print error', wx.OK | wx.ICON_INFORMATION)
			return
		printWindow.printFile(sliceRun.getExportFilename(self.filelist[0]))

	def OnModelMRU(self, e):
		fileNum = e.GetId() - self.ID_MRU_MODEL1
		path = self.modelFileHistory.GetHistoryFile(fileNum)
		# Update Model MRU
		self.modelFileHistory.AddFileToHistory(path)  # move up the list
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Save(self.config)
		self.config.Flush()
		# Load Model
		filelist = [ path ]
		self._loadModels(filelist)

	def addToModelMRU(self, file):
		self.modelFileHistory.AddFileToHistory(file)
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Save(self.config)
		self.config.Flush()
	
	def OnProfileMRU(self, e):
		fileNum = e.GetId() - self.ID_MRU_PROFILE1
		path = self.profileFileHistory.GetHistoryFile(fileNum)
		# Update Profile MRU
		self.profileFileHistory.AddFileToHistory(path)  # move up the list
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Save(self.config)
		self.config.Flush()
		# Load Profile	
		profile.loadGlobalProfile(path)
		self.updateProfileToControls()

	def addToProfileMRU(self, file):
		self.profileFileHistory.AddFileToHistory(file)
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Save(self.config)
		self.config.Flush()			

	def removeSliceProgress(self, spp):
		self.progressPanelList.remove(spp)
		newSize = self.GetSize()
		newSize.IncBy(0, -spp.GetSize().GetHeight())
		if newSize.GetWidth() < wx.GetDisplaySize()[0]:
			self.SetSize(newSize)
		spp.Show(False)
		self.sizer.Detach(spp)
		self.sizer.Layout()

	def updateProfileToControls(self):
		self.preview3d.updateProfileToControls()
		self.normalSettingsPanel.updateProfileToControls()
		self.simpleSettingsPanel.updateProfileToControls()

	def OnLoadProfile(self, e):
		dlg=wx.FileDialog(self, "Select profile file to load", os.path.split(profile.getPreference('lastFile'))[0], style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST)
		dlg.SetWildcard("ini files (*.ini)|*.ini")
		if dlg.ShowModal() == wx.ID_OK:
			profileFile = dlg.GetPath()
			profile.loadGlobalProfile(profileFile)
			self.updateProfileToControls()

			# Update the Profile MRU
			self.addToProfileMRU(profileFile)
		dlg.Destroy()

	def OnLoadProfileFromGcode(self, e):
		dlg=wx.FileDialog(self, "Select gcode file to load profile from", os.path.split(profile.getPreference('lastFile'))[0], style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST)
		dlg.SetWildcard("gcode files (*.gcode)|*.gcode;*.g")
		if dlg.ShowModal() == wx.ID_OK:
			gcodeFile = dlg.GetPath()
			f = open(gcodeFile, 'r')
			hasProfile = False
			for line in f:
				if line.startswith(';CURA_PROFILE_STRING:'):
					profile.loadGlobalProfileFromString(line[line.find(':')+1:].strip())
					hasProfile = True
			if hasProfile:
				self.updateProfileToControls()
			else:
				wx.MessageBox('No profile found in GCode file.\nThis feature only works with GCode files made by Cura 12.07 or newer.', 'Profile load error', wx.OK | wx.ICON_INFORMATION)
		dlg.Destroy()

	def OnSaveProfile(self, e):
		dlg=wx.FileDialog(self, "Select profile file to save", os.path.split(profile.getPreference('lastFile'))[0], style=wx.FD_SAVE)
		dlg.SetWildcard("ini files (*.ini)|*.ini")
		if dlg.ShowModal() == wx.ID_OK:
			profileFile = dlg.GetPath()
			profile.saveGlobalProfile(profileFile)
		dlg.Destroy()

	def OnResetProfile(self, e):
		dlg = wx.MessageDialog(self, 'This will reset all profile settings to defaults.\nUnless you have saved your current profile, all settings will be lost!\nDo you really want to reset?', 'Profile reset', wx.YES_NO | wx.ICON_QUESTION)
		result = dlg.ShowModal() == wx.ID_YES
		dlg.Destroy()
		if result:
			profile.resetGlobalProfile()
			self.updateProfileToControls()

	def OnBatchRun(self, e):
		br = batchRun.batchRunWindow(self)
		br.Centre()
		br.Show(True)

	def OnSimpleSwitch(self, e):
		profile.putPreference('startMode', 'Simple')
		self.updateSliceMode()

	def OnNormalSwitch(self, e):
		profile.putPreference('startMode', 'Normal')
		self.updateSliceMode()

	def OnDefaultMarlinFirmware(self, e):
		firmwareInstall.InstallFirmware()

	def OnCustomFirmware(self, e):
		if profile.getPreference('machine_type') == 'ultimaker':
			wx.MessageBox('Warning: Installing a custom firmware does not garantee that you machine will function correctly, and could damage your machine.', 'Firmware update', wx.OK | wx.ICON_EXCLAMATION)
		dlg=wx.FileDialog(self, "Open firmware to upload", os.path.split(profile.getPreference('lastFile'))[0], style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST)
		dlg.SetWildcard("HEX file (*.hex)|*.hex;*.HEX")
		if dlg.ShowModal() == wx.ID_OK:
			filename = dlg.GetPath()
			if not(os.path.exists(filename)):
				return
			#For some reason my Ubuntu 10.10 crashes here.
			firmwareInstall.InstallFirmware(filename)

	def OnFirstRunWizard(self, e):
		configWizard.configWizard()
		self.updateProfileToControls()

	def OnBedLevelWizard(self, e):
		configWizard.bedLevelWizard()

	def OnExpertOpen(self, e):
		ecw = expertConfig.expertConfigWindow()
		ecw.Centre()
		ecw.Show(True)

	def OnProjectPlanner(self, e):
		pp = projectPlanner.projectPlanner()
		pp.Centre()
		pp.Show(True)

	def OnMinecraftImport(self, e):
		mi = minecraftImport.minecraftImportWindow(self)
		mi.Centre()
		mi.Show(True)

	def OnSVGSlicerOpen(self, e):
		svgSlicer = flatSlicerWindow.flatSlicerWindow()
		svgSlicer.Centre()
		svgSlicer.Show(True)

	def OnCheckForUpdate(self, e):
		newVersion = version.checkForNewerVersion()
		if newVersion is not None:
			if wx.MessageBox('A new version of Cura is available, would you like to download?', 'New version available', wx.YES_NO | wx.ICON_INFORMATION) == wx.YES:
				webbrowser.open(newVersion)
		else:
			wx.MessageBox('You are running the latest version of Cura!', 'Awesome!', wx.ICON_INFORMATION)

	def OnClose(self, e):
		profile.saveGlobalProfile(profile.getDefaultProfilePath())

		# Save the window position, size & state from the preferences file
		profile.putPreference('window_maximized', self.IsMaximized())
		if not self.IsMaximized() and not self.IsIconized():
			(posx, posy) = self.GetPosition()
			profile.putPreference('window_pos_x', posx)
			profile.putPreference('window_pos_y', posy)
			(width, height) = self.GetSize()
			profile.putPreference('window_width', width)
			profile.putPreference('window_height', height)			
			
			# Save normal sash position.  If in normal mode (!simple mode), get last position of sash before saving it...
			isSimple = profile.getPreference('startMode') == 'Simple'
			if not isSimple:
				self.normalSashPos = self.splitter.GetSashPosition()
			profile.putPreference('window_normal_sash', self.normalSashPos)

		#HACK: Set the paint function of the glCanvas to nothing so it won't keep refreshing. Which keeps wxWidgets from quiting.
		self.preview3d.glCanvas.OnPaint = lambda e : e
		self.Destroy()

	def OnQuit(self, e):
		self.Close()

class normalSettingsPanel(configBase.configPanelBase):
	"Main user interface window"
	def __init__(self, parent):
		super(normalSettingsPanel, self).__init__(parent)

		#Main tabs
		self.nb = wx.Notebook(self)
		self.SetSizer(wx.BoxSizer(wx.HORIZONTAL))
		self.GetSizer().Add(self.nb, 1, wx.EXPAND)

		(left, right, self.printPanel) = self.CreateDynamicConfigTab(self.nb, 'Basic')

		configBase.TitleRow(left, "Quality")
		c = configBase.SettingRow(left, "Layer height (mm)", 'layer_height', '0.2', 'Layer height in millimeters.\n0.2 is a good value for quick prints.\n0.1 gives high quality prints.')
		validators.validFloat(c, 0.0001)
		validators.warningAbove(c, lambda : (float(profile.getProfileSetting('nozzle_size')) * 80.0 / 100.0), "Thicker layers then %.2fmm (80%% nozzle size) usually give bad results and are not recommended.")
		c = configBase.SettingRow(left, "Wall thickness (mm)", 'wall_thickness', '0.8', 'Thickness of the walls.\nThis is used in combination with the nozzle size to define the number\nof perimeter lines and the thickness of those perimeter lines.')
		validators.validFloat(c, 0.0001)
		validators.wallThicknessValidator(c)
		c = configBase.SettingRow(left, "Enable retraction", 'retraction_enable', False, 'Retract the filament when the nozzle is moving over a none-printed area. Details about the retraction can be configured in the advanced tab.')

		configBase.TitleRow(left, "Fill")
		c = configBase.SettingRow(left, "Bottom/Top thickness (mm)", 'solid_layer_thickness', '0.6', 'This controls the thickness of the bottom and top layers, the amount of solid layers put down is calculated by the layer thickness and this value.\nHaving this value a multiply of the layer thickness makes sense. And keep it near your wall thickness to make an evenly strong part.')
		validators.validFloat(c, 0.0)
		c = configBase.SettingRow(left, "Fill Density (%)", 'fill_density', '20', 'This controls how densily filled the insides of your print will be. For a solid part use 100%, for an empty part use 0%. A value around 20% is usually enough')
		validators.validFloat(c, 0.0, 100.0)

		configBase.TitleRow(right, "Speed && Temperature")
		c = configBase.SettingRow(right, "Print speed (mm/s)", 'print_speed', '50', 'Speed at which printing happens. A well adjusted Ultimaker can reach 150mm/s, but for good quality prints you want to print slower. Printing speed depends on a lot of factors. So you will be experimenting with optimal settings for this.')
		validators.validFloat(c, 1.0)
		validators.warningAbove(c, 150.0, "It is highly unlikely that your machine can achieve a printing speed above 150mm/s")
		validators.printSpeedValidator(c)

		#configBase.TitleRow(right, "Temperature")
		c = configBase.SettingRow(right, "Printing temperature", 'print_temperature', '0', 'Temperature used for printing. Set at 0 to pre-heat yourself')
		validators.validFloat(c, 0.0, 340.0)
		validators.warningAbove(c, 260.0, "Temperatures above 260C could damage your machine, be careful!")
		if int(profile.getPreference('extruder_amount')) > 1:
			c = configBase.SettingRow(right, "2nd nozzle temperature", 'print_temperature2', '0', 'Temperature used for printing with the 2nd nozzle. Set at 0 to use the same temperature as for nozzle 1')
			validators.validFloat(c, 0.0, 340.0)
			validators.warningAbove(c, 260.0, "Temperatures above 260C could damage your machine, be careful!")
		if int(profile.getPreference('extruder_amount')) > 2:
			c = configBase.SettingRow(right, "3th nozzle temperature", 'print_temperature3', '0', 'Temperature used for printing with the 3th nozzle. Set at 0 to use the same temperature as for nozzle 1')
			validators.validFloat(c, 0.0, 340.0)
			validators.warningAbove(c, 260.0, "Temperatures above 260C could damage your machine, be careful!")
		if int(profile.getPreference('extruder_amount')) > 3:
			c = configBase.SettingRow(right, "4th nozzle temperature", 'print_temperature4', '0', 'Temperature used for printing with the 4th nozzle. Set at 0 to use the same temperature as for nozzle 1')
			validators.validFloat(c, 0.0, 340.0)
			validators.warningAbove(c, 260.0, "Temperatures above 260C could damage your machine, be careful!")
		if profile.getPreference('has_heated_bed') == 'True':
			c = configBase.SettingRow(right, "Bed temperature", 'print_bed_temperature', '0', 'Temperature used for the heated printer bed. Set at 0 to pre-heat yourself')
			validators.validFloat(c, 0.0, 340.0)

		configBase.TitleRow(right, "Support structure")
		c = configBase.SettingRow(right, "Support type", 'support', ['None', 'Exterior Only', 'Everywhere'], 'Type of support structure build.\n"Exterior only" is the most commonly used support setting.\n\nNone does not do any support.\nExterior only only creates support where the support structure will touch the build platform.\nEverywhere creates support even on the insides of the model.')
		c = configBase.SettingRow(right, "Add raft", 'enable_raft', False, 'A raft is a few layers of lines below the bottom of the object. It prevents warping. Full raft settings can be found in the expert settings.\nFor PLA this is usually not required. But if you print with ABS it is almost required.')
		if int(profile.getPreference('extruder_amount')) > 1:
			c = configBase.SettingRow(right, "Support dual extrusion", 'support_dual_extrusion', False, 'Print the support material with the 2nd extruder in a dual extrusion setup. The primary extruder will be used for normal material, while the second extruder is used to print support material.')

		configBase.TitleRow(right, "Filament")
		c = configBase.SettingRow(right, "Diameter (mm)", 'filament_diameter', '2.89', 'Diameter of your filament, as accurately as possible.\nIf you cannot measure this value you will have to calibrate it, a higher number means less extrusion, a smaller number generates more extrusion.')
		validators.validFloat(c, 1.0)
		validators.warningAbove(c, 3.5, "Are you sure your filament is that thick? Normal filament is around 3mm or 1.75mm.")
		if int(profile.getPreference('extruder_amount')) > 1:
			c = configBase.SettingRow(right, "Diameter (mm)", 'filament_diameter2', '2.89', 'Diameter of your filament for the 2nd nozzle, as accurately as possible.\nIf you cannot measure this value you will have to calibrate it, a higher number means less extrusion, a smaller number generates more extrusion. Use 0 to use the same diameter as for nozzle 1.')
			validators.validFloat(c, 0.0)
			validators.warningAbove(c, 3.5, "Are you sure your filament is that thick? Normal filament is around 3mm or 1.75mm.")
		if int(profile.getPreference('extruder_amount')) > 2:
			c = configBase.SettingRow(right, "Diameter (mm)", 'filament_diameter3', '2.89', 'Diameter of your filament for the 3th nozzle, as accurately as possible.\nIf you cannot measure this value you will have to calibrate it, a higher number means less extrusion, a smaller number generates more extrusion. Use 0 to use the same diameter as for nozzle 1.')
			validators.validFloat(c, 0.0)
			validators.warningAbove(c, 3.5, "Are you sure your filament is that thick? Normal filament is around 3mm or 1.75mm.")
		if int(profile.getPreference('extruder_amount')) > 3:
			c = configBase.SettingRow(right, "Diameter (mm)", 'filament_diameter4', '2.89', 'Diameter of your filament for the 4th nozzle, as accurately as possible.\nIf you cannot measure this value you will have to calibrate it, a higher number means less extrusion, a smaller number generates more extrusion. Use 0 to use the same diameter as for nozzle 1.')
			validators.validFloat(c, 0.0)
			validators.warningAbove(c, 3.5, "Are you sure your filament is that thick? Normal filament is around 3mm or 1.75mm.")
		c = configBase.SettingRow(right, "Packing Density", 'filament_density', '1.00', 'Packing density of your filament. This should be 1.00 for PLA and 0.85 for ABS')
		validators.validFloat(c, 0.5, 1.5)

		self.SizeLabelWidths(left, right)
		
		(left, right, self.advancedPanel) = self.CreateDynamicConfigTab(self.nb, 'Advanced')
		
		configBase.TitleRow(left, "Machine size")
		c = configBase.SettingRow(left, "Nozzle size (mm)", 'nozzle_size', '0.4', 'The nozzle size is very important, this is used to calculate the line width of the infill, and used to calculate the amount of outside wall lines and thickness for the wall thickness you entered in the print settings.')
		validators.validFloat(c, 0.1, 10.0)

		configBase.TitleRow(left, "Skirt")
		c = configBase.SettingRow(left, "Line count", 'skirt_line_count', '1', 'The skirt is a line drawn around the object at the first layer. This helps to prime your extruder, and to see if the object fits on your platform.\nSetting this to 0 will disable the skirt. Multiple skirt lines can help priming your extruder better for small objects.')
		validators.validInt(c, 0, 10)
		c = configBase.SettingRow(left, "Start distance (mm)", 'skirt_gap', '6.0', 'The distance between the skirt and the first layer.\nThis is the minimal distance, multiple skirt lines will be put outwards from this distance.')
		validators.validFloat(c, 0.0)

		configBase.TitleRow(left, "Retraction")
		c = configBase.SettingRow(left, "Minimum travel (mm)", 'retraction_min_travel', '5.0', 'Minimum amount of travel needed for a retraction to happen at all. To make sure you do not get a lot of retractions in a small area')
		validators.validFloat(c, 0.0)
		c = configBase.SettingRow(left, "Speed (mm/s)", 'retraction_speed', '40.0', 'Speed at which the filament is retracted, a higher retraction speed works better. But a very high retraction speed can lead to filament grinding.')
		validators.validFloat(c, 0.1)
		c = configBase.SettingRow(left, "Distance (mm)", 'retraction_amount', '0.0', 'Amount of retraction, set at 0 for no retraction at all. A value of 2.0mm seems to generate good results.')
		validators.validFloat(c, 0.0)
		c = configBase.SettingRow(left, "Extra length on start (mm)", 'retraction_extra', '0.0', 'Extra extrusion amount when restarting after a retraction, to better "Prime" your extruder after retraction.')
		validators.validFloat(c, 0.0)

		configBase.TitleRow(right, "Speed")
		c = configBase.SettingRow(right, "Travel speed (mm/s)", 'travel_speed', '150', 'Speed at which travel moves are done, a high quality build Ultimaker can reach speeds of 250mm/s. But some machines might miss steps then.')
		validators.validFloat(c, 1.0)
		validators.warningAbove(c, 300.0, "It is highly unlikely that your machine can achieve a travel speed above 300mm/s")
		c = configBase.SettingRow(right, "Max Z speed (mm/s)", 'max_z_speed', '1.0', 'Speed at which Z moves are done. When you Z axis is properly lubercated you can increase this for less Z blob.')
		validators.validFloat(c, 0.5)
		c = configBase.SettingRow(right, "Bottom layer speed (mm/s)", 'bottom_layer_speed', '25', 'Print speed for the bottom layer, you want to print the first layer slower so it sticks better to the printer bed.')
		validators.validFloat(c, 0.0)

		configBase.TitleRow(right, "Cool")
		c = configBase.SettingRow(right, "Minimal layer time (sec)", 'cool_min_layer_time', '10', 'Minimum time spend in a layer, gives the layer time to cool down before the next layer is put on top. If the layer will be placed down too fast the printer will slow down to make sure it has spend atleast this amount of seconds printing this layer.')
		validators.validFloat(c, 0.0)
		c = configBase.SettingRow(right, "Enable cooling fan", 'fan_enabled', True, 'Enable the cooling fan during the print. The extra cooling from the cooling fan is essensial during faster prints.')

		configBase.TitleRow(right, "Quality")
		c = configBase.SettingRow(right, "Initial layer thickness (mm)", 'bottom_thickness', '0.0', 'Layer thickness of the bottom layer. A thicker bottom layer makes sticking to the bed easier. Set to 0.0 to have the bottom layer thickness the same as the other layers.')
		validators.validFloat(c, 0.0)
		validators.warningAbove(c, lambda : (float(profile.getProfileSetting('nozzle_size')) * 3.0 / 4.0), "A bottom layer of more then %.2fmm (3/4 nozzle size) usually give bad results and is not recommended.")
		c = configBase.SettingRow(right, "Cut off object bottom (mm)", 'object_sink', '0.00', 'Sinks the object into the platform, this can be used for objects that do not have a flat bottom and thus create a too small first layer.')
		validators.validFloat(c, 0.0)
		configBase.settingNotify(c, lambda : self.GetParent().GetParent().GetParent().preview3d.Refresh())
		c = configBase.SettingRow(right, "Duplicate outlines", 'enable_skin', False, 'Skin prints the outer lines of the prints twice, each time with half the thickness. This gives the illusion of a higher print quality.')

		self.SizeLabelWidths(left, right)

		#Plugin page
		self.pluginPanel = pluginPanel.pluginPanel(self.nb)
		if len(self.pluginPanel.pluginList) > 0:
			self.nb.AddPage(self.pluginPanel, "Plugins")
		else:
			self.pluginPanel.Show(False)

		#Alteration page
		self.alterationPanel = alterationPanel.alterationPanel(self.nb)
		self.nb.AddPage(self.alterationPanel, "Start/End-GCode")

		self.Bind(wx.EVT_SIZE, self.OnSize)

		self.nb.SetSize(self.GetSize())
		self.UpdateSize(self.printPanel)
		self.UpdateSize(self.advancedPanel)

	def SizeLabelWidths(self, left, right):
		leftWidth = self.getLabelColumnWidth(left)
		rightWidth = self.getLabelColumnWidth(right)
		maxWidth = max(leftWidth, rightWidth)
		self.setLabelColumnWidth(left, maxWidth)
		self.setLabelColumnWidth(right, maxWidth)

	def OnSize(self, e):
		# Make the size of the Notebook control the same size as this control
		self.nb.SetSize(self.GetSize())
		
		# Propegate the OnSize() event (just in case)
		e.Skip()
		
		# Perform out resize magic
		self.UpdateSize(self.printPanel)
		self.UpdateSize(self.advancedPanel)
	
	def UpdateSize(self, configPanel):
		sizer = configPanel.GetSizer()
		
		# Pseudocde
		# if horizontal:
		#     if width(col1) < best_width(col1) || width(col2) < best_width(col2):
		#         switch to vertical
		# else:
		#     if width(col1) > (best_width(col1) + best_width(col1)):
		#         switch to horizontal
		#
				
		col1 = configPanel.leftPanel
		colSize1 = col1.GetSize()
		colBestSize1 = col1.GetBestSize()
		col2 = configPanel.rightPanel
		colSize2 = col2.GetSize()
		colBestSize2 = col2.GetBestSize()

		orientation = sizer.GetOrientation()
		
		if orientation == wx.HORIZONTAL:
			if (colSize1[0] <= colBestSize1[0]) or (colSize2[0] <= colBestSize2[0]):
				configPanel.Freeze()
				sizer = wx.BoxSizer(wx.VERTICAL)
				sizer.Add(configPanel.leftPanel, flag=wx.EXPAND)
				sizer.Add(configPanel.rightPanel, flag=wx.EXPAND)
				configPanel.SetSizer(sizer)
				#sizer.Layout()
				configPanel.Layout()
				self.Layout()
				configPanel.Thaw()
		else:
			if max(colSize1[0], colSize2[0]) > (colBestSize1[0] + colBestSize2[0]):
				configPanel.Freeze()
				sizer = wx.BoxSizer(wx.HORIZONTAL)
				sizer.Add(configPanel.leftPanel, proportion=1, border=35, flag=wx.EXPAND)
				sizer.Add(configPanel.rightPanel, proportion=1, flag=wx.EXPAND)
				configPanel.SetSizer(sizer)
				#sizer.Layout()
				configPanel.Layout()
				self.Layout()
				configPanel.Thaw()

	def updateProfileToControls(self):
		super(normalSettingsPanel, self).updateProfileToControls()
		self.alterationPanel.updateProfileToControls()
		self.pluginPanel.updateProfileToControls()
