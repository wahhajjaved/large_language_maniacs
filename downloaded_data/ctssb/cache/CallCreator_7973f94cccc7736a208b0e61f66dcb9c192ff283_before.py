#!/usr/bin/env python3

__author__ = "Nadim Khoury"
__version__ = "0.2.3"


import platform
import os
import configparser
from CallCreator import *

class cmdInterface:
	beginhour = 17
	endhour = 23
	intervall = 15 # minutes
	SELECTIONMENU = (0, 1, 2, 3 ,4 ,5, 6)
	number_of_cases = 15
	
	def __init__(self):
		CMDIFStore.init()
		settings = CMDIFStore.getSettings()
		self.beginhour = settings["beginhour"] 
		self.endhour = settings["endhour"] 
		self.intervall = settings["intervall"]
		self.number_of_cases = settings["number_of_cases"]
	
	def __getOSType(self):
		return platform.system()
	
	def clearScreen(self):
		if self.__getOSType() == "Linux":
			os.system("clear")
		elif self.__getOSType() == "Windows":
			os.system("cls")
	
	def getKeyboardInput(self, msg):
		return input(msg)
		
	def checkKeyKeyboardInput(self, selection):
		try:
			selection = int(selection)
		except ValueError:
			raise
		if selection in self.SELECTIONMENU:
			return selection
		else:
			raise CMDInputError("Auswahl liegt nicht im Auswahl-Menü-Bereich")

	def printMainMenue(self):
		self.clearScreen()
		print("############CallCreator############")
		print("############v0.2.3#################")
		print("###################################")
		print("\t\t\tBeginn: %i"% (self.beginhour))
		print("\t\t\tEnde: %i"% (self.endhour))
		print("\t\t\tIntervall: %i"% (self.intervall))
		print("\t\t\tAnzahl Cases : %i"% (self.number_of_cases))
		print("\n\nMenue: ")
		print("\t1. Cases erzeugen")
		print("\t2. Ändere Zeit- und Intervalleinstellungen")
		print("\t3. Ausgabe der Case Beschreibungen")
		print("\t4. Eingabe einer neuen Case-Beschreibung")
		print("\t5. Löschen einer vorhandenen Case-Beschreibung")
		print("\n\t0. Ende")
	
	def prepareCaseCreator(self):
		try:
			call_manager_instance = CaseManager.getCaseManagerObject()
		except OSError as e:
			print(e)
			print("Programmabbruch")
			exit(1)
		return call_manager_instance
	
	def printCaseDescriptions(self, call_manager_instance):
		self.clearScreen()
		for description in call_manager_instance.getAllCaseDescriptions():
			print(description)
	
	def deleteCaseDescription(self, call_manager_instance):
		self.clearScreen()
		print("Löschen einer Case Beschreibung.")
		case = input("Bitte geben Sie die Case-Beschreibung exakt ein ein:\n")
		if call_manager_instance.checkIfCaseDescriptionExists(case):
			call_manager_instance.removeCaseDescription(case)
			print("Case Beschreibung wurde gelöscht!")
		else:
			print("\nFehler!!! Case Beschreibung nicht gefunden. Es wurde keine Löschung vorgenommen!!!")
	
	def saveNewCaseDescription(self, call_manager_instance):
		self.clearScreen()
		case = input("Bitte geben Sie eine Case-Beschreibung ein ein:\n")
		if call_manager_instance.checkIfCaseDescriptionExists(case):
			print("Abbruch, Case Beschreibung existiert schon!")
		else:
			call_manager_instance.createCaseDescription(case)
			print("Case Beschreibung wurde gespeichert!")
	
	def createAndPrintCases(self, call_manager_instance):
		self.clearScreen()
		for c in range(0, self.number_of_cases):
			call_manager_instance.createRandomCase(self.beginhour, self.endhour, self.intervall)
		call_manager_instance.sortAllCases()
		for c in call_manager_instance.getAllCases():
			print(c.getStartTime() + " - " + c.getEndTime() + " " + c.getDescription())
		call_manager_instance.deleteCaseQueue()
	
	def changeCaseValues(self):
		self.clearScreen()
		begin = self.getKeyboardInput("Bitte geben Sie die Start-Stunde ein: ")
		try:
			begin = int(begin)
		except ValueError:
			print("Fehler: Eingabe ungültig!")
			return
		
		if not (begin >= 0 and begin <= 24):
			print("Fehler: Eingabe ungültig!")
		else:
			self.beginhour = begin
		
		end = self.getKeyboardInput("Bitte geben Sie die End-Stunde ein: ")
		try:
			end = int(end)
		except ValueError:
			print("Fehler: Eingabe ungültig!")
			return
		
		if not (end  >= 0 and end  <= 24):
			print("Fehler: Eingabe ungültig!")
		else:
			self.endhour = end
		
		intervall = self.getKeyboardInput("Bitte geben Sie die Maxdauer eines Calls an: ")
		try:
			intervall = int(intervall)
		except ValueError:
			print("Fehler: Eingabe ungültig!")
			return
		
		self.intervall = intervall
		
		number_of_cases = self.getKeyboardInput("Bitte geben Sie die Anzahl der zu erzeugenden Calls an: ")
		try:
			number_of_cases = int(number_of_cases)
		except ValueError:
			print("Fehler: Eingabe ungültig!")
			return
		self.number_of_cases = number_of_cases
		
		CMDIFStore.changeSettings(self.beginhour, self.endhour, \
		                        self.intervall, self.number_of_cases)

								
	def main(self):
		call_manager_instance = self.prepareCaseCreator()
		while True:
			self.printMainMenue()
			try:
				result = self.checkKeyKeyboardInput(\
				         self.getKeyboardInput("\nAuswahl: "))
			except ValueError:
				print("Falsche Eingabe, keine Zahl")
				input("Drücke eine Taste um fortzusetzen")
				result = None
			except CMDInputError:
				print("Falsche Eingabe, Auswahl nicht vorhanden")
				input("Drücke eine Taste um fortzusetzen")
				result = None
			if result == 0:
				break
			elif result == 1:
				self.createAndPrintCases(call_manager_instance)
				input("\n\nDrücke eine Taste um fortzusetzen")
			elif result == 2:
				self.changeCaseValues()
				input("\n\nDrücke eine Taste um fortzusetzen")
			elif result == 3:
				self.printCaseDescriptions(call_manager_instance)
				input("\n\nDrücke eine Taste um fortzusetzen")
			elif result == 4:
				self.saveNewCaseDescription(call_manager_instance)
				input("\n\nDrücke eine Taste um fortzusetzen")
			elif result == 5:
				self.deleteCaseDescription(call_manager_instance)
				input("\n\nDrücke eine Taste um fortzusetzen")

class CMDIFStore:
	__settings_file = "cmdIFsettings.ini"
	__settings = { "beginhour" : 17, \
	             "endhour" : 23, \
	             "intervall" : 15, \
	             "number_of_cases" : 15 }
	
	@classmethod
	def init(cls):
		cls.config = configparser.ConfigParser()
		if os.path.isfile(cls.__settings_file):
			cls.config.read(cls.__settings_file)
			cls.__settings["beginhour"] = int(cls.config.get("CaseSettings",\
			                              "beginhour"))
			cls.__settings["endhour"] = int(cls.config.get("CaseSettings",\
			                            "endhour"))
			cls.__settings["intervall"] = int(cls.config.get("CaseSettings",\
			                              "intervall"))
			cls.__settings["number_of_cases"] = int(cls.config.get("CaseSettings",\
			                                    "number_of_cases"))
		else:
			cls.config["CaseSettings"] = cls.__settings
			cls.saveSettings()
	
	@classmethod
	def getSettings(cls):
		return cls.__settings
	
	@classmethod
	def changeSettings(cls, beginhour, endhour, intervall, 
	                   number_of_cases):
		cls.__settings["beginhour"] = beginhour
		cls.__settings["endhour"] = endhour
		cls.__settings["intervall"] = intervall
		cls.__settings["number_of_cases"] = number_of_cases
		cls.config['CaseSettings'] = cls.__settings
		cls.__saveSettingsToFile()
	
	@classmethod
	def __saveSettingsToFile(cls):
		with open(cls.__settings_file, 'w') as configfile:
			cls.config.write(configfile)
			

class CMDInputError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return rpr(self.value)

if __name__ == "__main__":
	cmd = cmdInterface()
	cmd.main()
	
