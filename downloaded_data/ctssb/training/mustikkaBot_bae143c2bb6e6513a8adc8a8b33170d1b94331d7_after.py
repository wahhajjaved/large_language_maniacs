import json
import errno

import tools
from logging import log


def getId():
    return "commands"


class commands:
    bot = None

    commands = []
    jsonfile = "commands.json"

    def init(self, bot):
        self.bot = bot
        self.readJSON()
        bot.eventlistener.registerMessage(self)
        log("[COMMANDS] Init complete")

    def handleMessage(self, data, user, msg):
        msg = tools.stripPrefix(msg)
        args = msg.split()

        if args[0] == "!commands":
            self.setupCommands(user, args)
        else:
            self.runCommands(user, args)

    def setupCommands(self, user, args):
        if args[1] == "add":
            self.addCommand(args[2])

        if args[1] == "set":
            self.setCommand(args[2], ' '.join(args[3:]))

    def runCommands(self, user, args):
        for command in self.commands:
            if "!" + command['name'] == args[0]:
                self.runCommand(command, args)

    def runCommand(self, command, args):
        self.bot.sendMessage(command['value'])

    def readJSON(self):
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
            self.commands = json.loads(jsondata)
        except ValueError:
            log("[COMMANDS] commands-file malformed")


    def writeJSON(self):
        file = open(self.jsonfile, "w")
        data = json.dumps(self.commands)
        file.write(data)
        file.close()

    def addCommand(self, cmd):
        self.commands.append({"name": cmd})
        self.writeJSON()

    def setCommand(self, cmd, text):
        for command in self.commands:
            if command['name'] == cmd:
                command['value'] = text
        self.writeJSON()