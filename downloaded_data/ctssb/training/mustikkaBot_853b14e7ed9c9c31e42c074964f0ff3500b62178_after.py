import re
import json
import errno

from logging import log, d


class group:
    accessm = None

    name = None

    def __init__(self, accessm, name):
        self.name = name
        self.accessm = accessm

    def getMembers(self):
        return self.accessm.groups[self.name]['members']


class access:
    bot = None

    groups = {}
    acls = {}

    jsonfile = "acls.json"

    def init(self, bot):
        """
        :param bot: Reference to the main bot instance
        :type bot: bot

        Initialize the access-module
        """
        self.bot = bot
        self.readJSON()
        log("[ACCESS] Init complete")

        if len(self.groups) is 0:
            self.addGroup("%owner")
            self.addGroup("%operators")
            self.addGroup("%moderators")
            self.writeJSON()

        self.addToGroup("%owner", "Herramustikka")
        self.addToGroup("%owner", "varesa")

    def readJSON(self):
        """
        Read the access-data from a JSON file
        """
        jsondata = ""
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
        """
        Write the access-data to a JSON file
        """
        jsondata = {"groups": self.groups, "acls": self.acls}
        file = open(self.jsonfile, "w")
        data = json.dumps(jsondata, sort_keys=True, indent=4, separators=(',', ': '))
        file.write(data)
        file.close()

    def addGroup(self, name, members=None):
        """
        :param name: Name of the group to be created
        :type name: str
        :param members: Optional list of members to initialize the group with
        :type members: list(str)

        Create a new group and optionally add members to it
        """
        if members is None:
            members = []
        self.groups[name] = {"members": members}
        self.writeJSON()

    def removeGroup(self, name):
        """
        :param name: Name of the group to be removed
        :type name: str

        Remove a group if it exists
        """
        self.groups.pop(name, None)
        self.writeJSON()

    def existsGroup(self, name):
        """
        :param name: Name of the group to check
        :type name: str
        :return: Does the group exists
        :rtype: bool

        Check if a group exists
        """
        if name in self.groups.keys():
            return True
        else:
            return False

    def getGroup(self, name):
        """
        :param name: Name of the group
        :type name: str
        :return: An instance of the group specified
        :rtype: group

        Return an instance of the :class:group describing the specified group
        """
        if self.existsGroup(name):
            return group(self, name)
        else:
            return None

    def addToGroup(self, group, name):
        """
        :param group: Name of the group
        :type group: str
        :param name: Name of the person
        :type name: str

        Add a person to a group
        """
        members = self.getGroup(group).getMembers()
        if name not in members:
            members.append(name)
            self.writeJSON()

    def removeFromGroup(self, group, name):
        """
        :param group: Name of the group
        :type group: str
        :param name: Name of the person
        :type name: str

        Remove a person from a group
        """
        self.getGroup(group).getMembers().pop(name, None)
        self.writeJSON()

    def createAcl(self, acl):
        """
        :param acl: Name of the acl
        :type acl: str

        Create a new acl
        """
        self.acls[acl] = {"groups":[], "members":[]}
        self.writeJSON()

    def existsAcl(self, acl):
        """
        :param acl: Name of the ACL
        :type acl: str
        :return: does the acl exist?
        :rtype: bool

        Check if the ACL exists
        """
        if acl in self.acls.keys():
            return True
        else:
            return False

    def registerAcl(self, acl, defaultGroups=None,defaultMembers=None):
        """
        :param acl: name of the acl
        :type acl: str
        :param defaultGroups: optional list of groups to add to the acl
        :type defaultGroups: list(str)
        :param defaultMembers: optional list of members to add to the acl
        :type defaultMembers: list(str)

        Register an acl. Create a new one with the defaults if it does not exist
        """
        if not self.existsAcl(acl):
            self.createAcl(acl)
            if defaultGroups is None and defaultMembers is None:
                self.addGroupToAcl(acl, "%owner")
                self.addGroupToAcl(acl, "%operators")
            else:
                if defaultGroups:
                    for group in defaultGroups:
                        self.addGroupToAcl(self,acl, group)
                if defaultMembers:
                    for member in defaultMembers:
                        self.addUserToAcl(acl, member)
            self.writeJSON()

    def addGroupToAcl(self, acl, group):
        """
        :param acl: name of the acl
        :type acl: str
        :param group: name of the group
        :type group: str

        Add a group to the acl
        """
        if not self.existsGroup(group):
            log("[ACCESS] group does not exist")
            return
        if not group in self.acls[acl]['groups']:
            self.acls[acl]['groups'].append(group)
            log("[ACCESS] group is already in acl")
        self.writeJSON()

    def addUserToAcl(self, acl, user):
        """
        :param acl: name of the acl
        :type acl: str
        :param user: name of the user
        :type user; str

        Add a user to the acl
        """
        if not user in self.acls[acl]['members']:
            self.acls[acl]['members'].append(user)
            self.writeJSON()

    def expandGroups(self, groups):
        """
        :param groups: list of the groups
        :type groups: list(str)
        :return: expanded list of groups
        :rtype: list(str)

        Expand a list of groups, so that all groups with higher level of privileges get permissions,
        if a lower group has them
        """
        expanded = []
        expanded += groups

        for group in groups:
            if group is "%operators":
                if "%owner" not in expanded:
                    expanded.append("%owner")
            elif group is "%moderators":
                if "%owner" not in expanded:
                    expanded.append("%owner")
                if "%operators" not in expanded:
                    expanded.append("%operators")
            elif group is not "%owner":
                if "%owner" not in expanded:
                    expanded.append("%owner")
                if "%operators" not in expanded:
                    expanded.append("%operators")
                if "%moderators" not in expanded:
                    expanded.append("%moderators")

        return expanded

    def isInAcl(self, user, acl):
        """
        :param user: name of the user
        :type user: str
        :param acl: name of the acl
        :type acl: str
        :return: has the user permissions
        :rtype: bool

        Check if a user is in an acl, either directly or through a group
        """
        if user in self.acls[acl]['members']:
            return True

        groups = self.expandGroups(self.acls[acl]['groups'])
        for group in groups:
            if user in self.groups[group]['members']:
                return True

        return False
