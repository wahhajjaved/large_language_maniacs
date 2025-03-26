import imp
import os
import re


class modulemanager:
    modules = {}
    bot = None

    def init(self, bot):
        self.bot = bot
        self.setupModules()
        self.initModules()

    def importModule(self, file):
        fpath = os.path.normpath(os.path.join(os.path.dirname(__file__), file))
        dir, fname = os.path.split(fpath)
        mname, ext = os.path.splitext(fname)

        (file, filename, data) = imp.find_module(mname, [dir])
        return imp.load_module(mname, file, filename, data)

    def setupModules(self):
        files = os.listdir("modules/")
        for file in files:
            result = re.search(r'\.py$', file)
            if result is not None:
                module = self.importModule("modules/" + file)
                id = module.getId()
                self.modules[id] = getattr(module, id)()

    def addModule(self, name):
        file = "modules/" + name + ".py"
        if os.path.exists(file):
            module = self.importModule(file)
            id = module.getId()
            self.modules[id] = getattr(module, id)()

    def removeModule(self, id):
        self.modules.pop(id, None)

    def initModules(self):
        for name, module in self.modules.iteritems():
            module.init(self.bot)

    def getModule(self, name):
        return self.modules[name]

    def getModules(self):
        return self.modules