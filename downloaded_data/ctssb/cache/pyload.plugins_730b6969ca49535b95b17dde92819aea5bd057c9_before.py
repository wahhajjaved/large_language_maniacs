#!/usr/bin/env python
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

import ConfigParser
import gettext
import logging
import logging.handlers
import time
import urllib2
from glob import glob
from os import mkdir
from os import sep
from os.path import basename
from os.path import exists
from sys import exit
from sys import path
from sys import stdout
from time import sleep

from module.Py_Load_File import PyLoadFile
from module.remote.RequestObject import RequestObject
from module.remote.SocketServer import ServerThread
from module.thread_list import Thread_List
from module.file_list import File_List
from module import file_list

class Core(object):
    """ pyLoad main
    """
    def __init__(self):
        self.config = {}
        self.config['plugin_folder'] = "plugins"
        self.plugins_avaible = {}

        self.read_config()

        translation = gettext.translation("pyLoad", "locale", languages=[self.config['language']])
        translation.install(unicode=True)

        self.check_create(self.config['log_folder'], _("folder for logs"))
        self.check_create(self.config['download_folder'], _("folder for downloads"))
        self.check_create(self.config['link_file'], _("file for links"), False)
        self.check_create(self.config['failed_file'], _("file for failed links"), False)

        self.init_logger(logging.DEBUG) # logging level

        #self.check_update()

        self.logger.info(_("Downloadtime: %s") % self.is_dltime()) # debug only

        self.thread_list = Thread_List(self)

        self.file_list = file_list.load()
  
        path.append(self.config['plugin_folder'])
        self.create_plugin_index()

        self.init_server()

    def read_config(self):
        """ read config and sets preferences
        """
        config = ConfigParser.SafeConfigParser()
        config.read('config')

        for section in config.sections():
            for option in config.options(section):
                self.config[option] = config.get(section, option)
                self.config[option] = False if self.config[option].lower() == 'false' else self.config[option]

    def create_plugin_index(self):
        for file_handler in glob(self.config['plugin_folder'] + sep + '*.py') + glob(self.config['plugin_folder'] + sep + 'DLC.pyc'):
            if file_handler != self.config['plugin_folder'] + sep + "Plugin.py":
                plugin_pattern = ""
                plugin_file = basename(file_handler).replace('.pyc', '').replace('.py', '')
                for line in open(file_handler, "r").readlines():
                    if "props['pattern']" in line:
                        plugin_pattern = line.split("r\"")[1].split("\"")[0]
                if plugin_pattern != "":
                    self.plugins_avaible[plugin_file] = plugin_pattern
                    self.logger.debug(plugin_file + _(" added"))
        self.logger.info(_("created index of plugins"))


    def _get_links(self, link_file):
        """ funktion nur zum testen ohne gui bzw. tui
        """
        links = open(link_file, 'r').readlines()
        self.extend_links(links)

    def append_link(self, link):
        if link not in self.thread_list.get_loaded_urls():
            self.__new_py_load_file(link.replace("\n", ""))

    def extend_links(self, links):
        for link in links:
            self.append_link(link)

    #def check_update(self):
        #"""checks newst version
        #"""
        #newst_version = urllib2.urlopen("http://pyload.nady.biz/files/version.txt").readline().strip()
        #if CURRENT_VERSION < newst_version:
            #self.logger.info(_("new update %s on pyload.org") % newst_version) #newer version out
        #elif CURRENT_VERSION == newst_version:
            #self.logger.info(_("newst version %s in use:") % CURRENT_VERSION) #using newst version
        #else:
            #self.logger.info(_("beta version %s in use:") % CURRENT_VERSION) #using beta version

    def check_create(self, check_name, legend, folder=True):
        if not exists(check_name):
            try:
                if folder:
                    mkdir(check_name)
                else:
                    open(check_name, "w")
                print _("%s created") % legend
            except:
                print _("could not create %s") % legend
                exit()

    def __new_py_load_file(self, url):
        new_file = PyLoadFile(self, url)
        new_file.download_folder = self.config['download_folder']
        self.thread_list.append_py_load_file(new_file)
        return True

    def init_logger(self, level):

        file_handler = logging.handlers.RotatingFileHandler(self.config['log_folder'] + sep + 'log.txt', maxBytes=102400, backupCount=int(self.config['log_count'])) #100 kib * 5
        console = logging.StreamHandler(stdout)

        frm = logging.Formatter("%(asctime)s: %(levelname)-8s  %(message)s", "%d.%m.%Y %H:%M:%S")
        file_handler.setFormatter(frm)
        console.setFormatter(frm)

        self.logger = logging.getLogger("log") # settable in config

        if self.config['file_log']:
            self.logger.addHandler(file_handler)

        self.logger.addHandler(console) #if console logging
        self.logger.setLevel(level)


    def is_dltime(self):
        start_h, start_m = self.config['start'].split(":")
        end_h, end_m = self.config['end'].split(":")

        #@todo: little bug, when start and end time in same hour
        hour, minute  = time.localtime()[3:5]

        if hour > int(start_h) and hour < int(end_h):
            return True
        elif hour == int(start_h) and minute >= int(start_m):
            return True
        elif hour == int(end_h) and minute <= int(end_m):
            return True
        else:
            return False

    def get_downloads(self): #only for debuging?!?
        list = []
        for pyfile in self.thread_list.py_downloading:
            download = {}
            download['id'] = pyfile.id
            download['name'] = pyfile.status.filename
            download['speed'] = pyfile.status.get_speed()
            download['eta'] = pyfile.status.get_ETA()
            download['kbleft'] = pyfile.status.kB_left()
            download['size'] = pyfile.status.size()
            download['percent'] = pyfile.status.percent()
            download['status'] = pyfile.status.type
            download['wait_until'] = pyfile.status.waituntil - time.time()
            list.append(download)

        return list

    def format_time(self, seconds):
        seconds = int(seconds)
        if seconds > 60:
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)
            return "%.2i:%.2i:%.2i" % (hours, minutes, seconds)
        return _("%i seconds") % seconds

    def _test_print_status(self):

        if self.thread_list.py_downloading:

            for pyfile in self.thread_list.py_downloading:
                if pyfile.status.type == 'downloading':
                    print pyfile.status.filename + ": speed is", int(pyfile.status.get_speed()), "kb/s"
                    print pyfile.status.filename + ": finished in", self.format_time(pyfile.status.get_ETA())
                elif pyfile.status.type == 'waiting':
                    print pyfile.status.filename + ": wait", self.format_time(pyfile.status.waituntil - time.time())

    def start(self):
        """ starts the machine
        """
        self._get_links(self.config['link_file'])
        while True:
            #self.thread_list.status()
            self._test_print_status()
            self.server_test()
            sleep(2)
            if len(self.thread_list.threads) == 0:
                pass #break

    def server_test(self):
        obj = RequestObject()
        obj.command = "update"
        obj.data = self.get_downloads()

        self.server.push_all(obj)

    def init_server(self):
        print _("Server Mode")
        self.server = ServerThread(self)
        self.server.start()
        

if __name__ == "__main__":
    testLoader = Core()
    testLoader.start()
