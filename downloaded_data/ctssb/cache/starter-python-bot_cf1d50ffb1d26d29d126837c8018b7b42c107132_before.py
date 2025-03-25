import os.path
import random

class SassManager(object):
	
    def __init__(self):
        self.sass_file = open('sass.txt', 'r')
        self.sass_cache = list()
        self.cache_loaded = False

    def load_sass_cache(self):
        for line in self.sass_file.read().splitlines():
            self.sass_cache.append(line)

    def get_sass(self, msg):
        return self.format_sass(msg)

    def format_sass(self, msg):
        target = self.get_target(msg)
        sass = self.get_random_sass()
        return "Hey, " + target + "! " + sass

    def get_random_sass(self):
        if not self.cache_loaded:
            slef.load_sass_cache()
            self.cache_loaded = True

    def get_target(self, msg):
        token = msg.split("sass ", 1)[1]
        target = self.format_target(token.lower().encode('ascii','ignore'))

    def format_target(self, target):
        if ' me ' in target:
            return "you"
        elif 'yourself' in target:
            return "Zac Efron"
        else:
            return target
