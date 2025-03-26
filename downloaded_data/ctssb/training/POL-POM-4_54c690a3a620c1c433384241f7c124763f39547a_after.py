#!/usr/bin/python 
# -*- coding:Utf-8 -*- 

# Copyright (C) 2008 Pâris Quentin
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA. 



import wx, os, getopt, sys, urllib, signal, time, string, urlparse, codecs, time, threading

from subprocess import Popen,PIPE
import lib.Variables as Variables
import lib.lng
import lib.DirTreeCtrl as DirTreeCtrl
lib.lng.Lang()

class Download(threading.Thread):
	def __init__(self, url, local):
		threading.Thread.__init__(self)
		self.url = url
		self.local = local
		self.taille_fichier = 0
		self.taille_bloc = 0
		self.nb_blocs = 0
		self.finished = False
		self.start()
		self.failed = False

	def onHook(self, nb_blocs, taille_bloc, taille_fichier):
		self.nb_blocs = nb_blocs
		self.taille_bloc = taille_bloc
		self.taille_fichier = taille_fichier
		
	def download(self):
		try:
			urllib.urlretrieve(self.url, self.local, reporthook = self.onHook)
		except:
			self.failed = True
		self.finished = True
		
	def run(self):
		self.download()
	

class POL_SetupFrame(wx.Frame): #fenêtre principale
	def __init__(self, titre, POL_SetupWindowID, Arg1, Arg2, Arg3, bash_pid):
		wx.Frame.__init__(self, None, -1, title = titre, style = wx.CLOSE_BOX | wx.CAPTION | wx.MINIMIZE_BOX, size = (520, 398+Variables.windows_add_size))

		self.SetIcon(wx.Icon(Variables.playonlinux_env+"/etc/playonlinux.png", wx.BITMAP_TYPE_ANY))
		self.gauge_i = 0
		self.fichier = ""
		self.last_time = int(round(time.time() * 1000))
		self.downloading = False
		self.ProtectedWindow = False
		
		# Le fichier de lecture
		self.file_id=Variables.playonlinux_rep+"/configurations/guis/"+POL_SetupWindowID
		
		if(Arg1 == "None"):
			self.small_image = wx.Bitmap(Variables.playonlinux_env+"/resources/images/setups/default/top.png")
		else:
			self.small_image = wx.Bitmap(Arg1)

		self.small_x = 520 - self.small_image.GetWidth()

		if(Arg2 == "None"):
			if(os.environ["POL_OS"] == "Linux"):
				self.big_image = wx.Bitmap(Variables.playonlinux_env+"/resources/images/setups/default/playonlinux.jpg")
			else:
				self.big_image = wx.Bitmap(Variables.playonlinux_env+"/resources/images/setups/default/playonmac.jpg")	
		else:
			self.big_image = wx.Bitmap(Arg2)

		if(Arg3 == "protect"):
			self.ProtectedWindow = True
		self.oldfichier = ""
		self.bash_pid = bash_pid
		
		self.make_gui()
		
		self.timer = wx.Timer(self, 1)
		

		#self.header.SetBorderColor((0,0,0))
		#self.panel.SetSizer(self.sizer)
  		#self.panel.SetAutoLayout(True)
		self.Bind(wx.EVT_TIMER, self.AutoReload, self.timer)
   		self.timer.Start(10)
		self.AutoReload(self)
		wx.EVT_CLOSE(self, self.Cancel)

	def make_gui(self):
		# Fonts
		if(os.environ["POL_OS"] == "Mac"):
			self.fontTitre = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "", wx.FONTENCODING_DEFAULT)
			self.fontText = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,False, "", wx.FONTENCODING_DEFAULT)
		else :
			self.fontTitre = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "", wx.FONTENCODING_DEFAULT)
			self.fontText = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,False, "", wx.FONTENCODING_DEFAULT)
			
		# GUI elements
		self.panel = wx.Panel(self, -1, pos=(0,0), size=((520, 398+Variables.windows_add_size)))
		self.header = wx.Panel(self.panel, -1, style=Variables.widget_borders, size=(522,65))
		self.header.SetBackgroundColour((255,255,255))
		self.footer = wx.Panel(self.panel, -1, size=(522,45), pos=(-1,358), style=Variables.widget_borders)
	
		# Panels
		self.MainPanel = wx.Panel(self.panel, -1, pos=(150,0), size=(370,356))
		self.MainPanel.SetBackgroundColour((255,255,255))
		
		
		# Images
		self.top_image = wx.StaticBitmap(self.header, -1, self.small_image, (self.small_x,0), wx.DefaultSize)
		self.left_image = wx.StaticBitmap(self.panel, -1, self.big_image, (0,0), wx.DefaultSize)

		
		# Text
		self.titre_header = wx.StaticText(self.header, -1, _('{0} Wizard').format(os.environ["APPLICATION_TITLE"]),pos=(5,5), size=(340,356),style=wx.ST_NO_AUTORESIZE)
		self.titre_header.SetFont(self.fontTitre)
		self.titre_header.SetForegroundColour((0,0,0)) # For dark themes
		
		self.texte = wx.StaticText(self.panel, -1, "",pos=(20,80),size=(480,275),style=wx.ST_NO_AUTORESIZE)
		self.texte_bis = wx.StaticText(self.panel, -1, "",size=(480,30),style=wx.ST_NO_AUTORESIZE)
		self.titre = wx.StaticText(self.header, -1, "",pos=(20,30), size=(340,356),style=wx.ST_NO_AUTORESIZE)
		self.titre.SetForegroundColour((0,0,0)) # For dark themes
		
		self.texteP = wx.StaticText(self.MainPanel, -1, "",pos=(5,50))
		self.texteP.SetForegroundColour((0,0,0)) # For dark themes
		
		self.titreP = wx.StaticText(self.MainPanel, -1,"",pos=(5,5), size=(340,356))
		self.titreP.SetFont(self.fontTitre)
		self.titreP.SetForegroundColour((0,0,0)) # For dark themes
		
		self.txtEstimation = wx.StaticText(self.panel, -1, "",size=(480,30),style=wx.ST_NO_AUTORESIZE)
		self.register_link = ""
		# Buttons
		self.CancelButton = wx.Button(self.footer, wx.ID_CANCEL, _("Cancel"), pos=(430,0),size=(85,37))
		if(self.ProtectedWindow == True):
			self.CancelButton.Enable(False)
			
		self.NextButton = wx.Button(self.footer, wx.ID_FORWARD, _("Next"), pos=(340,0),size=(85,37))
		self.BackButton = wx.Button(self.footer, wx.ID_FORWARD, _("Back"), pos=(250,0),size=(85,37))
		
		self.NoButton = wx.Button(self.footer, wx.ID_NO, _("No"), pos=(430,0),size=(85,37))
		self.YesButton = wx.Button(self.footer, wx.ID_YES, _("Yes"), pos=(340,0), size=(85,37))
		self.browse = wx.Button(self.panel, 103, _("Browse"), size=(130,25))
		#self.FileList = DirTreeCtrl(None, -1)
		
		#DirTreeCtrl(self.FileList)
		#self.register = wx.HyperlinkCtrl(self.footer, 305, _("Having "), "", pos=(20,180))
	
		# D'autres trucs
		self.champ = wx.TextCtrl(self.panel, 400, "",size=(300,22))
		
		self.bigchamp = wx.TextCtrl(self.panel, -1, "",size=wx.Size(460,240), pos=(25,105),style=Variables.widget_borders|wx.TE_MULTILINE)
		self.MCheckBox = wx.CheckBox(self.panel, 302, _("I Agree"), pos=(20,325))
		self.PCheckBox = wx.CheckBox(self.panel, 304, _("Show virtual drives"), pos=(20,325))
		self.Menu = wx.ListBox(self.panel, 103, pos=(25,105),size=(460,220), style=Variables.widget_borders)
		self.MenuList = wx.ComboBox(self.panel, 103, style=wx.CB_READONLY)
		self.scrolled_panel = wx.ScrolledWindow(self.panel, -1, pos=(20,100), size=(460,220), style=Variables.widget_borders|wx.HSCROLL|wx.VSCROLL)
		self.scrolled_panel.SetBackgroundColour((255,255,255))
		self.texte_panel = wx.StaticText(self.scrolled_panel, -1, "",pos=(5,5))

		self.gauge = wx.Gauge(self.panel, -1, 50, size=(375, 20))
		self.pulsebar = wx.Gauge(self.panel, -1, 50, size=(375, 20))
		self.WaitButton = wx.Button(self.panel, 310, "", size=(250,25))
		
		self.images = wx.ImageList(22, 22)
		self.MenuGames = wx.TreeCtrl(self.panel, 111, style=wx.TR_HIDE_ROOT|wx.TR_FULL_ROW_HIGHLIGHT|Variables.widget_borders, pos=(25,105),size=(460,220))
		self.MenuGames.SetImageList(self.images)
		self.MenuGames.SetSpacing(0)
		
		
		# Login
		self.login = wx.StaticText(self.panel, -1, _("Login: "),pos=(20,120),size=(460,20))
		self.password = wx.StaticText(self.panel, -1, _("Password: "),pos=(20,150),size=(460,20))
		self.loginbox =  wx.TextCtrl(self.panel, -1, "",size=(250,22),pos=(200,115))
		self.passbox =  wx.TextCtrl(self.panel, -1, "",size=(250,22),pos=(200,145), style=wx.TE_PASSWORD)
		self.register = wx.HyperlinkCtrl(self.panel, 303, _("Register"), "", pos=(20,180))
		self.register.SetNormalColour(wx.Colour(0,0,0))
		
		# Fixed Events
		wx.EVT_BUTTON(self, wx.ID_YES, self.release_yes)	
		wx.EVT_BUTTON(self, wx.ID_NO, self.release_no)
		wx.EVT_BUTTON(self, wx.ID_CANCEL , self.Cancel)
		wx.EVT_BUTTON(self, 103,  self.Parcourir)
		wx.EVT_CHECKBOX(self, 302, self.agree)
		wx.EVT_CHECKBOX(self, 304, self.switch_menu)
		wx.EVT_HYPERLINK(self, 303, self.POL_register)
		#wx.EVT_HYPERLINK(self, 305, self.Send_Bug)
		
		# Hide all
		self.Destroy_all()

		
	def Destroy_all(self):
		self.header.Hide()
		self.left_image.Hide()
		self.CancelButton.Hide()
		self.MainPanel.Hide()
		self.NextButton.Hide()
		self.BackButton.Hide()
		self.NoButton.Hide()
		self.YesButton.Hide()
		self.browse.Hide()
		self.champ.Hide()
		self.bigchamp.Hide()
		self.texte.Hide()
		self.texte_bis.Hide()
		self.texteP.Hide()
		self.titre.Hide()
		self.Menu.Hide()
		self.MenuGames.Hide()
		self.MenuList.Hide()
		self.scrolled_panel.Hide()
		self.gauge.Hide()
		self.pulsebar.Hide()
		self.txtEstimation.Hide()
		self.texte_panel.Hide()
		self.MCheckBox.Hide()	
		self.PCheckBox.Hide()	
		self.NextButton.Enable(True)
		self.login.Hide()
		self.loginbox.Hide()
		self.password.Hide()
		self.passbox.Hide()
		self.register.Hide()
		self.WaitButton.Hide()
		self.MCheckBox.SetValue(False)
		self.PCheckBox.SetValue(False)
		self.Refresh()
		
		
	def POL_register(self, event):
		if(os.environ["POL_OS"] == "Mac"): 
			os.system("open "+self.register_link)
		else:
			os.system("xdg-open "+self.register_link)
			
	def RunCommand(self, event, command,confirm):
		if(confirm == "0" or wx.YES == wx.MessageBox(confirm.decode("utf-8"), os.environ["APPLICATION_TITLE"], style=wx.YES_NO | wx.ICON_QUESTION)):
			os.system(command+"&");
			
	def DrawImage(self):			
		self.left_image.Show()

	def DrawHeader(self):
		self.header.Show()

	def DrawCancel(self):
		self.CancelButton.Show()

	def DrawNext(self):
		self.NextButton.Show()

	def SendBash(self, var):
		self.fichier_w = open(self.file_id,"w")
		self.fichier_w.write(var+"\nMsgOut\n")
		self.fichier_w.close()

	def SendBashT(self, var):
		self.fichier_w = open(self.file_id+".txt","w")
		self.fichier_w.write(var)
		self.fichier_w.close()
			
	def release(self, event):
		self.SendBash("Ok")
		self.NextButton.Enable(False)

	def release_but_fail(self, event):
		self.SendBash("Fail")
		self.NextButton.Enable(False)
			
	def release_checkboxes(self, event):
		self.i = 0
		self.send = []
		while(self.i < len(self.item_check)):
			if(self.item_check[self.i].IsChecked() == True):
				self.send.append(self.areaList[self.i])
			self.i += 1
		self.SendBash("MSG_VALUE="+string.join(self.send,self.fichier[5].replace("\n","")))
		self.NextButton.Enable(False)

	def release_yes(self, event):
		self.SendBash("MSG_QUESTION=TRUE")
		self.NextButton.Enable(False)

	def release_no(self, event):
		self.SendBash("MSG_QUESTION=FALSE")
		self.NextButton.Enable(False)
	
	def release_login(self, event):
		self.SendBash("LOGIN="+self.loginbox.GetValue().encode("utf-8")+"\nPASS="+self.passbox.GetValue().encode("utf-8"))
		self.NextButton.Enable(False)

	def release_champ(self, event):
		self.SendBash("MSG_VALUE="+self.champ.GetValue().encode("utf-8"))
		self.NextButton.Enable(False)
			
	def release_bigchamp(self, event):
		self.SendBash("MSG_VALUE=Ok")
		self.SendBashT(self.bigchamp.GetValue().encode("utf-8"))
		self.NextButton.Enable(False)
			
	def release_menu(self,event):
		self.SendBash("MSG_VALUE="+self.areaList[self.Menu.GetSelection()])
		self.NextButton.Enable(False)

	def release_menu_list(self,event):
		self.SendBash("MSG_VALUE="+self.MenuList.GetValue().encode("utf-8"))
		self.NextButton.Enable(False)

	def release_menu_num(self,event):
		self.SendBash("MSG_VALUE="+str(self.Menu.GetSelection()))
		self.NextButton.Enable(False)

	def release_icons(self,event):
		if(self.menu.IsChecked()):
			self.SendBash("MSG_MENU=True")
		if(self.desktop.IsChecked()):
			self.SendBash("MSG_DESKTOP=True")
		if(self.desktop.IsChecked() and self.menu.IsChecked()):
			self.SendBash("MSG_DESKTOP=True\nMSG_MENU=True")
		if(self.desktop.IsChecked() == False and self.menu.IsChecked() == False):
			self.SendBash("Ok")
		self.NextButton.Enable(False)

	def release_menugame(self,event):
		self.SendBash("MSG_VALUE="+self.MenuGames.GetItemText(self.MenuGames.GetSelection()).encode("utf-8"))
		self.NextButton.Enable(False)
		
	def release_menuprefixes(self,event):
		if(self.PCheckBox.IsChecked() == False): # Alors il faut renvoyer le prefix
			self.SendBash("MSG_VALUE=1;"+self.MenuGames.GetItemText(self.MenuGames.GetSelection()).encode("utf-8"))
		else:
			self.SendBash("MSG_VALUE=2;"+self.areaList[self.Menu.GetSelection()])
			
		self.NextButton.Enable(False)		

	def Cancel(self, event):
		if(self.ProtectedWindow == False):
			self.Destroy()
			self.SendBash("MSG_RECEIVED=Cancel") #Indiquera à PlayOnLinux bash qu'il faut arreter l'installation
			#if(os.environ["POL_OS"] = "Mac"):
			os.system("kill -9 -"+self.bash_pid+" 2> /dev/null")
			#if(os.environ["POL_OS"] = "Linux"):
			#	os.system("pkill -9 -P"+self.bash_pid+" 2> /dev/null")
			
			#time.sleep(0.3)
			os.system("kill -9 "+self.bash_pid+" 2> /dev/null") # Plus bourrain, mais bien plus efficace
			os.remove(self.file_id) # La on est plutôt pépère pour faire ça
		else:
			wx.MessageBox(_("You cannot close this window").format(os.environ["APPLICATION_TITLE"]),_("Error"))
			
	def CleanExit(self):
		self.Destroy()
		self.SendBash("MSG_RECEIVED=Cancel") #Indiquera à PlayOnLinux bash qu'il faut arreter l'installation
		os.remove(self.file_id) # La on est plutôt pépère pour faire ça
        #self.Destroy()

	def add_games(self):
		self.games = os.listdir(Variables.playonlinux_rep+"/shortcuts/")
		self.games.sort()
		self.images.RemoveAll()
		self.MenuGames.DeleteAllItems()
		self.root = self.MenuGames.AddRoot("")
		self.i = 0
		for game in self.games: 
			self.file = Variables.playonlinux_rep+"/shortcuts/"+game
			if(not os.path.isdir(self.file)):
				fichier = open(self.file,"r").read()

				if("POL_Wine " in fichier):
					if(os.path.exists(Variables.playonlinux_rep+"/icones/32/"+game)):
						self.file_icone = Variables.playonlinux_rep+"/icones/32/"+game
					else:
						self.file_icone = Variables.playonlinux_env+"/etc/playonlinux32.png"
					
					self.bitmap = wx.Image(self.file_icone)
					self.bitmap.Rescale(22,22,wx.IMAGE_QUALITY_HIGH)
					self.bitmap = self.bitmap.ConvertToBitmap()
					self.images.Add(self.bitmap)
					self.MenuGames.AppendItem(self.root, game, self.i)
					self.i = self.i+1


	def add_menu_icons(self):
		self.cut = self.fichier[5].replace("\n","")
		self.games = string.split(self.fichier[4].replace("\n",""),self.cut)
		self.icons = string.split(self.fichier[7].replace("\n",""),self.cut)
		
		#self.games.sort()
		self.images.RemoveAll()
		self.MenuGames.DeleteAllItems()
		self.root = self.MenuGames.AddRoot("")
		self.i = 0
		for game in self.games: 
			current_icon = self.fichier[6].replace("\n","")+"/"+self.icons[self.i]
			if(os.path.exists(current_icon)):
				self.file_icone = current_icon
			else:
				self.file_icone = Variables.playonlinux_env+"/etc/playonlinux32.png"
			
			self.bitmap = wx.Image(self.file_icone)
			self.bitmap.Rescale(22,22,wx.IMAGE_QUALITY_HIGH)
			self.bitmap = self.bitmap.ConvertToBitmap()
			self.images.Add(self.bitmap)
			self.MenuGames.AppendItem(self.root, game, self.i)
			self.i = self.i+1
							
							
	def DemanderPourcent(self, event):
		self.NextButton.Enable(False)
		if self.p.poll() == None:
			self.gauge.Pulse()		
		else:
			#self.gauge.SetValue(50)
			self.Bind(wx.EVT_TIMER, self.AutoReload, self.timer)
			self.timer_attendre.Stop()
			self.timer_attendre.Destroy()
			self.timer.Start(10)
			self.SendBash("Ok")
			#self.NextButton.Enable(True)
			#self.NextButton.Enable(True)
         
	def Parcourir(self, event):
		self.FileDialog = wx.FileDialog(self.panel)
		self.FileDialog.SetDirectory(self.fichier[5].replace("\n",""))
		self.FileDialog.ShowModal() 
		if(self.FileDialog.GetPath() != ""):
			self.champ.SetValue(self.FileDialog.GetPath().encode('utf-8'))
	        self.FileDialog.Destroy()
   
	def DownloadFile(self, url, localB):    #url = url a récupérer, localB le fichier où enregistrer la modification sans nom de fichier
		#self.buttonSuivant.Enable(False)
		self.chemin = urlparse.urlsplit(url)[2] 
		self.nomFichier = self.chemin.split('/')[-1] 
		self.local = localB + self.nomFichier 
		self.downloader = Download(url, self.local)
		self.downloading = True
		
		#urllib.urlretrieve(url, self.local, reporthook = self.onHook)
	
		#print "Fini dans "+local
		#self.release(self)

	def agree(self, event):
		if(self.MCheckBox.IsChecked()):
			self.NextButton.Enable(True)
		else:
			self.NextButton.Enable(False)

	def switch_menu(self, event):
		if(self.PCheckBox.IsChecked()):
			self.Menu.Show()
			self.MenuGames.Hide()
		else:
			self.MenuGames.Show()
			self.Menu.Hide()
		self.Refresh()
					
	def AutoReload(self, event):
		if(self.downloading == True):
			if(self.downloader.taille_bloc != 0):
				self.nb_blocs_max = self.downloader.taille_fichier / self.downloader.taille_bloc
				self.gauge.SetRange(self.nb_blocs_max)
				self.gauge.SetValue(self.downloader.nb_blocs)

				self.tailleFichierB = float(self.downloader.taille_fichier / 1048576.0)
				self.octetsLoadedB = float((self.downloader.nb_blocs * self.downloader.taille_bloc) / 1048576.0)
				self.octetsLoadedN = round(self.octetsLoadedB, 1)
				self.tailleFichierN = round(self.tailleFichierB, 1)

				self.estimation_txt = str(self.octetsLoadedN) + " "+_("of")+" " + str(self.tailleFichierN) + " "+_("MB downloaded")		
				self.txtEstimation.SetLabel(self.estimation_txt)
				if(self.downloader.finished == True):
					if(self.downloader.failed == True):
						self.release_but_fail(self)
						print("FAIL")
					else:
						self.release(self)
					self.downloading = False
				
					
					#self.downloader.Destroy()
			
		if(os.path.exists(self.file_id)):
			self.fichier = open(self.file_id,"r").readlines()
			if(self.downloading != True):
				try :
					if(self.gauge_i < 2):
						self.gauge_i += 1
					else:
						self.gauge.Pulse()
						self.gauge_i = 0
				except :
					pass

			if(self.fichier != self.oldfichier):
				if(len(self.fichier) > 0):
					if(self.fichier[0] == "MsgIn\n"):
						if(len(self.fichier) > 1):
							if(self.fichier[1] != "pulse\n" and self.fichier[1] != "set_text\n"):
								self.Destroy_all()

						if(len(self.fichier) > 1):
							if(self.fichier[1] == "pulse\n"):
								self.pulsebar.SetValue(int(self.fichier[2])/2)

							if(self.fichier[1] == "set_text\n"):
								self.texte_bis.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte_bis.SetPosition((20,135+self.space*16))
								self.texte_bis.Show()

							if(self.fichier[1] == "champ\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								self.space=self.fichier[2].count("\\n")+1
								
								self.champ.SetPosition((20,85+self.space*16))
								self.champ.SetValue(self.fichier[4].replace("\n",""))
								self.champ.Show()
								
								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_champ)	
								wx.EVT_TEXT_ENTER(self, 400, self.release_champ)

							if(self.fichier[1] == "Login\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()

								self.space=self.fichier[2].count("\\n")+1
								self.register_link = self.fichier[4]

								self.login.Show()
								self.loginbox.Show()
								self.password.Show()
								self.passbox.Show()
								self.register.Show()

								self.DrawCancel()
								self.DrawNext()
																
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_login)
									
							if(self.fichier[1] == "bigchamp\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()

								self.space=self.fichier[2].count("\\n")+1

								self.bigchamp.SetPosition((20,85+self.space*16))
								self.bigchamp.SetValue(self.fichier[4].replace("\n",""))
								
								self.bigchamp.Show()

								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_bigchamp)
				
							if(self.fichier[1] == "browse\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								self.space = self.fichier[2].count("\\n")+1
								
								self.browse.SetPosition(((330, 85+self.space*16)))
								self.browse.Show()
								
								self.champ.SetPosition((20,85+self.space*16))
								self.champ.SetValue(self.fichier[4].replace("\n",""))
								self.champ.Show()

								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_champ)	

							if(self.fichier[1] == "menu\n" or self.fichier[1] == "menu_num\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								self.space = self.fichier[2].count("\\n")+1
								self.cut = self.fichier[5].replace("\n","")
								self.areaList = string.split(self.fichier[4].replace("\n",""),self.cut)
							
								self.space=self.fichier[2].count("\\n")+1
								
								self.Menu.SetPosition((20,85+self.space*16))
								
								self.Menu.Clear()
								self.Menu.InsertItems(self.areaList,0)
								self.Menu.Select(0)
								self.Menu.Show()
								
								self.DrawCancel()
								self.DrawNext()
								
								# Good event
								if(self.fichier[1] == "menu\n"):
									wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menu)	
									wx.EVT_LISTBOX_DCLICK(self, 103, self.release_menu)
								if(self.fichier[1] == "menu_num\n"):	
									wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menu_num)	
									wx.EVT_LISTBOX_DCLICK(self, 103, self.release_menu_num)

							if(self.fichier[1] == "menu_list\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()

								self.space = self.fichier[2].count("\\n")+1
								self.cut = self.fichier[5].replace("\n","")
								self.areaList = string.split(self.fichier[4].replace("\n",""),self.cut)

								self.MenuList.SetPosition((20, 85+self.space*16))
								self.MenuList.Clear()
								self.MenuList.AppendItems(self.areaList)
								self.MenuList.Show()
								
								self.DrawCancel()
								self.DrawNext()
																
								if(self.fichier[6] != "\n"):
									self.MenuList.SetValue(self.fichier[6].replace("\n",""))
								else:
									self.MenuList.SetValue(self.areaList[0])
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menu_list)
											
											
							if(self.fichier[1] == "checkbox_list\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								

								self.scrolled_panel.Show()
								self.space=self.fichier[2].count("\\n")+1
								
								self.scrolled_panel.SetPosition((20,85+self.space*16))
								
								self.cut = self.fichier[5].replace("\n","")
								self.areaList = string.split(self.fichier[4].replace("\n",""),self.cut)

								self.i = 0
								try:
									while(self.i <= len(self.item_check)):
										self.item_check[self.i].Destroy()
										self.i+=1
								except:
									pass
								self.item_check = []
								self.i = 0
								while(self.i < len(self.areaList)):							
									self.item_check.append(wx.CheckBox(self.scrolled_panel, -1, pos=(0,(self.i*25)),label=str(self.areaList[self.i])))
									self.i+=1

								self.scrolled_panel.SetVirtualSize((0,self.i*(25)))
								self.scrolled_panel.SetScrollRate(0,25)
								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_checkboxes)	

							if(self.fichier[1] == "attendre_signal\n" or self.fichier[1] == "pulsebar\n" or self.fichier[1] == "attendre_signal_b\n"):
								self.DrawHeader()
								self.timer_attendre = wx.Timer(self, 1)
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								self.space=self.fichier[2].count("\\n")+1
								self.gauge_space = self.space
								if(self.fichier[1] == "attendre_signal\n" or self.fichier[1] == "attendre_signal_b\n"):
									self.gauge.Show()
									self.gauge.SetPosition((70,95+self.space*16))
								else :
									self.pulsebar.Show()
									self.pulsebar.SetPosition((70,95+self.space*16))

								if(self.fichier[1] == "attendre_signal_b\n"):
									self.WaitButton.Show()
									self.WaitButton.SetLabel(self.fichier[4].replace("\n",""))
									self.WaitButton.SetPosition((135,135+self.space*16))
									self.Bind(wx.EVT_BUTTON, lambda event: self.RunCommand(event,self.fichier[5].replace("\n",""),self.fichier[6].replace("\n","")),self.WaitButton)
									
								self.DrawCancel()
								self.DrawNext()
								self.NextButton.Enable(False)

									
							if(self.fichier[1] == "download\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								self.space=self.fichier[2].count("\\n")+1
								self.gauge.Show()
								self.gauge.SetPosition((70,95+self.space*16))
								
								self.txtEstimation.SetPosition((20,135+self.space*16))
								self.txtEstimation.Show()
								#self.titre.SetFont(self.fontText)
								self.DrawCancel()
								self.DrawNext()
								self.NextButton.Enable(False)	
								self.DownloadFile(self.fichier[4].replace("\n",""), self.fichier[5].replace("\n",""))
								#wx.EVT_BUTTON(self, 300, self.release)
						
							if(self.fichier[1] == "get_games\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								

								self.add_games()
								self.MenuGames.Show()
								
								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menugame)	
								wx.EVT_TREE_ITEM_ACTIVATED(self, 111, self.release_menugame)	
							
							if(self.fichier[1] == "menu_icons\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()

								self.add_menu_icons()
								self.MenuGames.Show()

								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menugame)	
								wx.EVT_TREE_ITEM_ACTIVATED(self, 111, self.release_menugame)
									
							if(self.fichier[1] == "get_prefixes\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								

								self.add_games()
								self.MenuGames.Show()
								
								self.space=self.fichier[2].count("\\n")+1
								
								self.Menu.SetPosition((20,85+self.space*16))
								
								self.Menu.Clear()
								self.areaList = os.listdir(Variables.playonlinux_rep+"/wineprefix/")
								self.areaList.sort()
								
								for file in self.areaList:
									if (str(file[0]) == "."):
										self.areaList.remove(file)

								self.Menu.InsertItems(self.areaList,0)
								self.Menu.Select(0)
								self.Menu.Hide()
								
								self.DrawCancel()
								self.DrawNext()
								
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release_menuprefixes)	
								wx.EVT_TREE_ITEM_ACTIVATED(self, 111, self.release_menuprefixes)
								wx.EVT_LISTBOX_DCLICK(self, 103, self.release_menuprefixes)
									
								self.PCheckBox.Show()


							if(self.fichier[1] == "message\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								#self.titre = wx.StaticText(self.header, -1, self.fichier[3],pos=(20,30), size=(340,356))
								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release)	

							if(self.fichier[1] == "licence\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								#self.Mchamp.SetValue(open(self.fichier[4].replace("\n",""),"r").read())
								
								#
								try:
									self.texte_panel.SetLabel(open(self.fichier[4].replace("\n",""),"r").read())
								except:
									self.texte_panel.SetLabel("E. file not found :"+self.fichier[4].replace("\n",""))
									
								self.texte_panel.Wrap(400)
								self.texte_panel.Show()
								
								self.scrolled_panel.Show()
								self.scrolled_panel.SetVirtualSize(self.texte_panel.GetSize())
								self.scrolled_panel.SetScrollRate(0,25)
								
								self.MCheckBox.Show()
								
								self.DrawCancel()
								self.DrawNext()
								self.NextButton.Enable(False)
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release)	

								
							if(self.fichier[1] == "file\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()

								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()

								self.texte_panel.SetLabel(open(self.fichier[4].replace("\n",""),"r").read())
								self.texte_panel.Wrap(400)
								self.texte_panel.Show()

								self.scrolled_panel.Show()
								self.scrolled_panel.SetVirtualSize(self.texte_panel.GetSize())
								self.scrolled_panel.SetScrollRate(0,25)

								self.DrawCancel()
								self.DrawNext()
								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release)
							
							if(self.fichier[1] == "question\n"):
								self.DrawHeader()
								self.texte.SetLabel(self.fichier[2].replace("\\n","\n"))
								self.texte.Show()
								
								self.titre.SetLabel(self.fichier[3])
								self.titre.Show()
								
								#self.titre.SetFont(self.fontText)
								self.YesButton.Show()
								self.NoButton.Show()	
					
							if(self.fichier[1] == "free_presentation\n"):
								self.MainPanel.Show()
								self.titreP.SetLabel(self.fichier[2])
								self.titreP.Wrap(280)
								
								self.texteP.SetLabel(self.fichier[3].replace("\\n","\n").decode("utf8"))
								self.texteP.Wrap(360)
								self.texteP.Show()
								
								self.DrawCancel()
								self.DrawNext()

								wx.EVT_BUTTON(self, wx.ID_FORWARD, self.release)					
								self.DrawImage()

							if(self.fichier[1] == "exit\n"):
								#self.Destroy()
								self.CleanExit()

						self.oldfichier = self.fichier
