#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2009 Benoit Chesneau <benoitc@e-engura.org>
#
# This software is licensed as described in the file LICENSE, which
# you should have received as part of this distribution.

"""
Script that pushes a file system hierarchy into a CouchDB design document.

Good for pure Couch application development.

A port of couchapp from Ruby (http://github.com/jchris/couchapp)
"""

import logging
import os
import sys
from optparse import OptionParser, OptionGroup

import couchapp
from couchapp.errors import *
from couchapp.ui import UI
from couchapp.app import CouchApp
from couchapp.utils import in_couchapp
from couchapp.vendor import Vendor


class CouchappCli(object):
    
    def __init__(self, verbose=False):
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console.setFormatter(formatter)
        self.ui = UI(verbose=verbose, logging_handler=console)
        self.verbose = verbose
        
    def generate(self, appname):
        appdir = os.path.normpath(os.path.join(os.getcwd(), appname))
        if self.verbose >= 1:
            self.ui.logger.info("Generating a new CouchApp in %s" % appdir)
        cmd = CouchApp(appdir, self.ui)
        try:
            cmd.generate()
        except AppError, e:
            self.ui.logger.critical(str(e))

    def init(self, appdir, dburl):
        if verbose >= 1:
            self.ui.logger.info("Initializing a new CouchApp in %s" % appdir)
        cmd = CouchApp(appdir, self.ui)
        try:
            cmd.initialize(dburl)
        except AppError, e:
            self.ui.logger.critical(str(e))
            
    def push(self, appdir, appname, dbstring, options=None):
        cmd = CouchApp(appdir, self.ui)
        try:
            cmd.push(dbstring, appname)
        except ValueError, e:
            print>>sys.stderr, e
            return
        except (AppError, MacroError), e:
            self.ui.logger.critical(str(e))

    def clone(self, app_uri, appdir):
        cmd = CouchApp(appdir, self.ui)
        try:
            cmd.clone(app_uri)
        except (AppError, MacroError), e:
            self.ui.logger.critical(str(e))
            
    def vendor_update(self, appdir):
        vendor = Vendor(appdir, self.ui)
        try:
            vendor.update()
        except VendorError, e:
            self.ui.logger.critical(str(e))
            
    def vendor_install(self, appdir, url, scm='git'):
        vendor = Vendor(appdir, self.ui)
        try:
            vendor.install(url, scm=scm)
        except VendorError, e:
            self.ui.logger.critical(str(e))
            
def main():
    parser = OptionParser(usage='%prog [options] cmd', version="%prog " + couchapp.__version__)
    parser.add_option('-v', dest='verbose', default=1,  action='store_const', const=2, help='print message to stdout')
    parser.add_option('-q', dest='verbose', action='store_const', const=0, help="don't print any message")
    
    # generate options
    parser.add_option_group(OptionGroup(parser, "Generate a new CouchApp! (start here)",
            "couchapp generate <appname> [appdir]"))
            
    # push options
    group_push = OptionGroup(parser, "Pushes a CouchApp to CouchDB", 
            "couchapp push [options] [appdir] [appname] [dburl]")
    parser.add_option_group(group_push)
    
    # clone options
    parser.add_option_group(OptionGroup(parser, 
        "Clones/Pulls a CouchApp from a url (like http://host/db/_design/CA_name)",
        "couchapp clone/pull <dburl> [dir]"))
            
    # init options
    group_init = OptionGroup(parser, "Initialize CouchApp .couchapprc", "couchapp init [options] <appdir>")
    group_init.add_option("--db", action="store", help="full url of default database")
    parser.add_option_group(group_init)
    
    group_vendor = OptionGroup(parser, "Install a vendor", "couchapp vendor install vendor_url [option][appdir]")
    group_vendor.add_option("--scm", action="store", default='git', 
                                help="scm used to install the vendor, by default git")
    parser.add_option_group(group_vendor)
    
    options, args = parser.parse_args()


    if len(args) < 1:
        return parser.error('incorrect number of arguments')
        
    cli = CouchappCli(options.verbose)

    if args[0] == 'generate':
        if len(args) < 2:
            return parser.error('cmd: "generate appname"'+
                    '\n\nIncorrect number of arguments, appname is'+
                    ' missing')
        appname = args[1]
        cli.generate(appname)
    elif args[0] == 'push':
        appname = ''
        rel_path = '.'
        dbstring = ''
        # generate [dir] [appname] [url] case
        if len(args) == 4:
            # we test if we are in a couchapp here
            # in case it's true, abort
            if in_couchapp():
                return parser.error('Incorrect number of arguments, you\'re in an app.')
            rel_path = args[1]
            appname = args[2]
            dbstring = args[3]
            
        # generate [dir/appname] [url] case
        elif len(args) == 3:
            rel_path = in_couchapp()
            if rel_path:
                if args[1] != '.':
                    appname = args[1]
                dbstring = args[2]
            else:
                rel_path = args[1]
                dbstring = args[2]
        
        # generate [dir/url] case
        elif len(args) == 2:
            rel_path = in_couchapp()
            if rel_path:
                if args[1] != '.':
                    dbstring = args[1]
            else:
                rel_path = args[1]
                
        # just generate
        elif len(args) == 1:
            rel_path = in_couchapp()
            if not rel_path:
                rel_path = '.'

        appdir = os.path.normpath(os.path.join(os.getcwd(), rel_path))
        # Derive appname from the directory name (/home/foo/sofa => sofa)
        if not appname: 
            appname = ''.join(appdir.split('/')[-1:])
        # PUSH IT!
        cli.push(appdir, appname, dbstring, options=options)
      
    elif args[0] == 'clone' or args[0] == 'pull':
        if len(args) < 2:
            return parser.error('Incorrect number of arguments (at least two)')
        # clone/pull <url> [dir] case
        if len(args) == 3:
            app_dir = args[2]
        # clone/pull <url>
        else:
            app_dir = ''
        # CLONE IT!
        cli.clone(args[1], app_dir)
    
    elif args[0] == 'init':
        dburl = options.db or ''
        try:
            appdir = args[1]
        except IndexError:
            appdir = '.'
        cli.init(appdir, dburl)
    elif args[0] == 'vendor':
        if len(args) < 2:
            return parser.error('Incorrect number of arguments (at least two)')
        action = args[1]
        if action == 'update':
            try:
                appdir = args[2]
            except IndexError:
                appdir = '.'
            cli.vendor_update(appdir)
        elif action == 'install':
            if len(args) < 3:
                return parser.error('Incorrect number of arguments')                
            try:
                appdir = args[3]
            except IndexError:
                appdir = '.'
            cli.vendor_install(appdir, args[2], options.scm)
        else:
            print >>sys.stderr, "%s is an unknown vendor action, sorry." % action      
    else:
        print "%s is an unknown command, sorry." % args[0]

if __name__ == '__main__':
    main()
