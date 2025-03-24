#!/usr/bin/python
# -*- coding: utf-8 -*- 
# 
#Copyright (C) 2009 sp00b, sebnapi, RaNaN
#
#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation; either version 3 of the License,
#or (at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#See the GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.
#
###
CURRENT_VERSION = '0.1'

#python imports
import ConfigParser
from glob import glob
from string import find, split
from os import sep, chdir, mkdir, curdir, name, system, remove
from os.path import exists, abspath, dirname, basename
from sys import path, exit, stdout
import urllib2
import re
from time import sleep, time
import logging
import logging.handlers

#my imports
from module.download_thread import Download_Thread
from module.thread_list import Thread_List
from module.Py_Load_File import PyLoadFile

class Core(object):
    """ pyLoad main 
    """
    def __init__(self):
        self.check_update()

        self.download_folder = ""
        self.log_folder = ""
        self.plugins_folder = "Plugins"
        self.link_file = "links.txt"
        self.plugins_avaible = {}
        self.search_updates = False
        
        self.read_config()
        
        self.thread_list = Thread_List(self)
        
        self.check_create(self.download_folder, "Ordner für Downloads", True)
        self.check_create(self.log_folder, "Ordner für Logs", True)
        self.check_create(self.link_file, "Datei für Links", False)

        self.init_logger(logging.DEBUG) # logging level

        path.append(self.plugins_folder)
        self.create_plugin_index()
        
    def read_config(self):
        """ sets self.download_folder, self.applicationPath, self.search_updates and self.plugins_folder
        """
        config = ConfigParser.ConfigParser()
        config.read('config')
        self.download_folder = config.get('general', 'downloadFolder')
        self.link_file = config.get('general', 'linkFile')
        self.search_updates = config.get('updates', 'searchUpdates')
        self.log_folder = config.get('log', 'logFolder')

    def create_plugin_index(self):
        for file_handler in glob(self.plugins_folder + sep + '*.py'):
            if file_handler != self.plugins_folder + sep + "Plugin.py":
                plugin_pattern = ""
                plugin_file = basename(file_handler).replace('.py', '')
                for line in open(file_handler, "r").readlines():
                    try:
                        plugin_pattern = re.search(r"self.plugin_pattern = r\"(.*)\"", line).group(1)
                        break
                        print line
                    except:
                        pass
                if plugin_pattern != "":
                    self.plugins_avaible[plugin_file] = plugin_pattern
                    self.logger.debug(plugin_file + " hinzugefuegt")
        print "Index der Plugins erstellt"

##    def check_needed_plugins(self):
##        links = open(self.link_file, 'r').readlines()
##        plugins_indexed = pickle.load(open(self.plugin_index, "r"))
##        for link in links:
##            link = link.replace("\n", "")
##            for plugin_file in plugins_indexed.keys():
##                if re.search(plugins_indexed[plugin_file], link) != None:
##                    self.plugins_needed[plugin_file] = plugins_indexed[plugin_file]
##        print "Benoetigte Plugins: " + str(self.plugins_needed.keys())
##
##    def import_needed_plugins(self):
##        for needed_plugin in self.plugins_needed.keys():
##            self.import_plugin(needed_plugin)
##
##    def import_plugin(self, needed_plugin):
##        try:
##            new_plugin = __import__(needed_plugin)
##            self.plugins_dict[new_plugin] = self.plugins_needed[needed_plugin]
##            #if new_plugin.plugin_type in "hoster" or new_plugin.plugin_type in "container":
##            #   print "Plugin geladen: " + new_plugin.plugin_name
##            #plugins[plugin_file] = __import__(plugin_file)
##        except:
##            print "Fehlerhaftes Plugin: " + needed_plugin
##

    def _get_links(self, link_file):
        """ funktion nur zum testen ohne gui bzw. tui
        """
        links = open(link_file, 'r').readlines()
        self.extend_links(links)               

    def append_link(self, link):
        if link not in self.thread_list.get_loaded_urls():
            self.__new_py_load_file(link)
                
    def extend_links(self, links):
        for link in links:
            self.append_link(link)

    def check_update(self):
        """checks newst version
        """
        newst_version = urllib2.urlopen("http://pyload.nady.biz/files/version.txt").readline().strip()
        if CURRENT_VERSION < newst_version:
            print "Neues Update " + newst_version + " auf pyload.de.rw" #newer version out
        elif CURRENT_VERSION == newst_version:
            print "Neuste Version " + CURRENT_VERSION + " in benutzung" #using newst version
        else:
            print "Beta Version " + CURRENT_VERSION + " in benutzung" #using beta version

    def check_create(self, check_name, legend, folder):
        if not exists(check_name):
            try:
                if folder:
                    mkdir(check_name)
                else:
                    open(check_name, "w")
                print legend, "erstellt"
            except:
                print "Konnte", legend, "nicht erstellen"
                exit()
    
    #def addLinks(self, newLinks, atTheBeginning):
        #pass
        
#    def get_hoster(self, url):
#        """ searches the right plugin for an url
#        """
#        for plugin, plugin_pattern in self.plugins_avaible.items():
#            if re.match(plugin_pattern, url) != None: #guckt ob übergebende url auf muster des plugins passt
#                return plugin
#        #logger: kein plugin gefunden
#        return None
            
            
    def __new_py_load_file(self, url):
        new_file = PyLoadFile(self, url)
        new_file.download_folder = self.download_folder
        self.thread_list.append_py_load_file(new_file)
        return True
    
    def init_logger(self, level):
        handler = logging.handlers.RotatingFileHandler('Logs/log.txt', maxBytes = 12800 , backupCount = 10) #100 kb
        console = logging.StreamHandler(stdout) 
        #handler = logging.FileHandler('Logs/log.txt') 
        frm = logging.Formatter("%(asctime)s: %(levelname)-8s  %(message)s", 
                              "%d.%m.%Y %H:%M:%S") 
        handler.setFormatter(frm)
        console.setFormatter(frm)

        self.logger = logging.getLogger() # settable in config
        self.logger.addHandler(handler)
        self.logger.addHandler(console) #if console logging
        self.logger.setLevel(level)
    
    def _test_print_status(self):
        if self.thread_list.py_downloading:
                
            for pyfile in self.thread_list.py_downloading:
                if pyfile.status.type == 'downloading':
                    print pyfile.status.filename + ": speed is" ,int(pyfile.status.get_speed()) ,"kb/s"
                    print pyfile.status.filename + ": arraives in" ,pyfile.status.get_ETA() ,"seconds"

                    #try:
                    #    fn = pyfile.status.filename
                    #    p = round(float(pyfile.status.downloaded_kb)/pyfile.status.total_kb, 2)
                    #    s = round(pyfile.status.rate, 2)
                    #    del pyfile.status  #?!?
                    #    pyfile.status = None
                    #    print fn + ": " + str(p) + " @ " + str(s) + "kB/s"
                    #except:
                    #    print pyfile.status.filename, "downloading"
                        
                if pyfile.status.type == 'waiting':
                    print pyfile.status.filename + ": wait", int(pyfile.status.waituntil -time()) , "seconds"
    
    def start(self):
        """ starts the machine
        """
        self._get_links(self.link_file)
        while True:
            #self.thread_list.status()
            self._test_print_status()
            sleep(1)
            if len(self.thread_list.threads) == 0:
                break

testLoader = Core()
testLoader.start()
