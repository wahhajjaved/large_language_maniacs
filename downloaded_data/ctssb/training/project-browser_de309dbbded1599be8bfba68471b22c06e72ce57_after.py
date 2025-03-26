#!/usr/bin/python

#File:			FileManager.py
#Description:		Ist fuer den Dateizugriff zustaendig
#Author:		Kaleb Tschabold
#Creation Date:		14.4.2011
#
#History: 		--Version--	--Date--	--Activities--
#			0.1		14.4.2011	Grundfunktionalitaeten werden erstellt
#			0.1		23.4.2011	Erste Funktionen um Dateilisten zu laden

#Unsere Klassen
from File import *

#andere Klassen
import os

class FileManager:
	def __init__(self,sys):
		self.sys = sys
		pass
	
	def getFilesFromDir(self,path):
		a = []
		if not os.path.exists(path):
			matched = self.searchMatchDir(path)
			if len(matched) >= 1:
				array = matched
			else:
				return a
			for i in range(len(array)):
				a.append(File(self.getDirName(array[i]),array[i]))
				a[i].setTags(self.sys.db.getTagsToFile(a[i]))
				a[i].setIsDir(self.isDir(array[i]))
		else:
			if path == '':
				path = path + '/'
			if path[-1:] != '/':
				path = path + '/'
			array =  os.listdir(path)
			for i in range(len(array)):
				fullpath = path + array[i]
				if self.isDir(fullpath):
					fullpath = fullpath + '/'
				print('fullpath from getFilesFromDir: '+fullpath)
				print(fullpath)
				a.append(File(array[i],fullpath))
				a[i].setTags(self.sys.db.getTagsToFile(a[i]))
				a[i].setIsDir(self.isDir(fullpath))
		return a

	def getFileName(self,path):
		return os.path.basename(path)

	def getDirName(self,path):
		s = path.split('/')
		return s[len(s)-2]

	def isDir(self,path):
		return os.path.isdir(path)

	def searchMatchDir(self,path):
		match = []
		try:
			ddf = self.divideDirAndFile(path)
			l = os.listdir(ddf[0])
			for i in range(len(l)):
				if (l[i].find(ddf[1]) >= 0 and os.path.isdir(ddf[0] + '/' + l[i])) or (ddf[1] == '' and os.path.isdir(ddf[0] + '/' + l[i])):
					if ddf[0] == '/':
						match.append(ddf[0] + l[i] + '/')
					else:
						match.append(ddf[0] + '/' + l[i] + '/')
		except:
			pass
		return match

	def divideDirAndFile(self,dirandfile):
		dir = ''
		file = ''
		if dirandfile.find('/') >= 0:
			dir = dirandfile[0:dirandfile.rfind('/')]
			if dir.strip() == '':
				dir = '/'
			file = dirandfile[dirandfile.rfind('/')+1:(len(dirandfile))]
		else:
			dir = '/'
			file = dirandfile[1:]
		divided = []
		divided.append(dir)
		divided.append(file)
		return divided


	def openFile(self,path):
		print('fullpath: '+path)
		if self.sys.c.os == 'linux':
			#Funktioniert nur bei Ubuntu
			os.system('/usr/bin/xdg-open '+path.replace(chr(32),'\ '))
		elif self.sys.c.os == 'windows':
			os.system(path)
		else:
			#Da muss noch eine Loesung sein, wenn die Datei nicht gestartet werden kann
			pass

	def openDir(self,path):
		print('fullpath: '+path)
		self.sys.gui.txtEntry.set_text(path)
		self.sys.gui.updateView()
		
