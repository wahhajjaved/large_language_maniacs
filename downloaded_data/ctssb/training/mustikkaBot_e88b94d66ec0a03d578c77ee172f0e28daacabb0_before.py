import json
import errno

from logging import log


class access:
    bot = None

    groups = {}
    acls = {}

    jsonfile = "acls.json"

    def init(self, bot):
        self.bot = bot
        self.readJSON()
        log("[ACCESS] Init complete")

    def readJSON(self):
        jsondata = None
        try:
            file = open(self.jsonfile, "r")
            jsondata = file.read()
            file.close()
        except IOError as e:
            if e.errno == errno.ENOENT:
                log("[COMMANDS] file does not exist, creating")
                self.writeJSON()

        try:
            data = json.loads(jsondata)
            self.groups = data['groups']
            self.acls = data['acls']
        except ValueError:
            log("[COMMANDS] commands-file malformed")


    def writeJSON(self):
        jsondata = {"groups": self.groups, "acls": self.acls}
        file = open(self.jsonfile, "w")
        data = json.dumps(jsondata)
        file.write(data)
        file.close()

    def addGroup(self, name, members=[]):
        self.groups[name] = {"members": members}

    def removeGroup(self, name):
        self.groups.pop(name, None)

    def addToGroup(self, group, name):
        self.groups[group]['members'].append(name)

    def removeFromGroup(self, group, name):
        self.groups[group]['members'].pop(name, None)

    def createAcl(self, acl):
        self.acls[acl] = {}

    def registerAcl(self, acl):
        self.createAcl(acl)

    def addGroupToAcl(self, acl, group):
        if not group in self.groups:
            log("[ACCESS] group does not exist")
            return
        self.acls[acl]['groups'].append(group)

    def addUserToAcl(self, acl, user):
        self.acls[acl]['members'].append(user)

    def isInAcl(self, acl, user):
        if user in self.acls[acl].members:
            return True

        for group in self.acls[acl].groups:
            if user in self.groups[group]['members']:
                return True

        return False
    