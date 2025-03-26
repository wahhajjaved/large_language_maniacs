# -*- coding: utf-8 -*-

import zc.buildout
import shutil
import os
from bda.recipe.deployment.common import Config

class Recipe(object):
    
    def __init__(self, buildout, name, options):
        self.name = name
        self.options = options
        self.buildout = buildout
        self.buildout_base = buildout['buildout']['directory']
        distserver = options.get('distserver')
        if not distserver:
            raise zc.buildout.UserError(u'distserver section missing.')
        distserver = [d.strip() for d in distserver.strip().split('\n')]
        if not distserver:
            raise zc.buildout.UserError(u'No dist servers defined.')
        self.distserver = dict()
        for server in distserver:
            key, val = server.split(' ')
            self.distserver[key] = val
        packages = options.get('packages')
        if not packages:
            raise zc.buildout.UserError(u'packages section missing.')
        packages = [p.strip() for p in packages.strip().split('\n')]
        if not packages:
            raise zc.buildout.UserError(u'No packages defined.')
        self.packages = dict()
        for package in packages:
            key, val = package.split(' ')
            self.packages[key] = val
        base_path = buildout['buildout']['directory']
        self.rc = options.get('rc')
        if not self.rc:
            raise zc.buildout.UserError(u'No RC sources config defined.')
        if not self.rc.startswith(base_path):
            rc = os.path.join(base_path, self.rc)
        self.dev = options.get('dev')
        if not self.dev:
            raise zc.buildout.UserError(u'No DEV sources config defined.')
        if not self.dev.startswith(base_path):
            self.dev = os.path.join(base_path, self.dev)
        self.live = options.get('live')
        if not self.live:
            raise zc.buildout.UserError(u'No Live versions config defined.')
        if not self.live.startswith(base_path):
            self.live = os.path.join(base_path, self.live)
        self.register = options.get('register', '')
        self.env = options.get('env')
        if not self.env in ['dev', 'rc', 'all']:
            raise zc.buildout.UserError(u'No or wrong env flavor defined.')
        sources_default = os.path.join(self.buildout['buildout']['directory'],
                                       'src')
        self.sources_dir = self.buildout['buildout'].get('sources-dir', 
                                                         sources_default) 

    def install(self):
        path = os.path.join(self.buildout['buildout']['directory'],
                            '.bda.recipe.deployment.cfg')
        if os.path.exists(path):
            os.remove(path)
        dev_sources =  Config(self.dev)
        sources = dev_sources.as_dict('sources')
        Config(path, self.buildout_base, self.distserver, self.packages,
               sources, self.rc, self.live, self.env, self.sources_dir,
               self.register)()
        
    def update(self):
        return self.install()