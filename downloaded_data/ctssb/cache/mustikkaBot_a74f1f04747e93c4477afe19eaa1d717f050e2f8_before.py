import json
import errno
import logging

import tools

class Commands:

    log = logging.getLogger("mustikkabot.commands")
    bot = None

    commands = []
    jsonfile = "commands.json"

    helpMessage = "Usage: !commands list | add <cmd> | remove <cmd> | set <cmd> <text> | regulars <cmd> <value>"
    # Hidden commands: '!commands save' and '!commands load' for managing the JSON

    def init(self, bot):
        self.bot = bot
        self.read_JSON()
        bot.eventmanager.register_message(self)
        self.log.info("Init complete")

    def dispose(self):
        """
        Uninitialize the module when called by the eventmanager. Unregisters the messagelisteners
        when the module gets disabled.
        """
        self.bot.eventmanager.unregister_special(self)
        
    def handle_message(self, data, user, msg):
        msg = tools.strip_prefix(msg)
        args = msg.split()

        if args[0] == "!commands" or args[0] == "!comm":
            self.setup_commands(user, args)
        else:
            self.run_commands(user, args)

    def setup_commands(self, user, args):
        if len(args) > 1:
            if args[1] == "list":
                self.list_commands()

            if args[1] == "add":
                self.add_command(args)

            if args[1] == "set":
                self.set_command(args)

            if args[1] == "regulars":
                self.set_regulars(args)

            if args[1] == "remove":
                self.remove_command(args)

            if args[1] == "load":
                self.read_JSON()

            if args[1] == "save":
                self.write_JSON()
        else:
            self.bot.send_message(self.helpMessage)

    def run_commands(self, user, args):
        for command in self.commands:
            if "!" + command['name'] == args[0]:
                self.run_command(command, args, user)

    def run_command(self, command, args, user):
        if self.bot.accessmanager.is_in_acl(user, "commands.!" + command['name']):
            self.bot.send_message(command['value'])
            self.log.info("Running command " + command['name'] + ": " + command['value'])

    def read_JSON(self):
        jsondata = ""
        try:
            file = open(self.jsonfile, "r")
            jsondata = file.read()
            file.close()
        except IOError as e:
            if e.errno == errno.ENOENT:
                self.log.info("file does not exist, creating")
                self.write_JSON()

        try:
            self.commands = json.loads(jsondata)
        except ValueError:
            self.log.error("commands-file malformed")

    def write_JSON(self):
        file = open(self.jsonfile, "w")
        data = json.dumps(self.commands, sort_keys=True, indent=4, separators=(',', ': '))
        file.write(data)
        file.close()

    def exists_command(self, cmd):
        """
        :param cmd: Name of a command
        :type cmd: str
        :return: does command exist
        :rtype: bool

        Check if a command exists
        """
        for command in self.commands:
            if command['name'] == cmd:
                return True
        return False

    def add_command(self, args):
        cmd = args[2]

        if not self.exists_command(cmd):
            self.commands.append({"name": cmd})
            self.bot.accessmanager.register_acl("commands.!" + cmd)
            self.write_JSON()
            self.bot.send_message("Added command " + cmd)
            self.log.info("Added new command:" + cmd)

            if len(args) > 3:
                self.set_command(cmd, ' '.join(args[3:]))

        else:
            self.bot.send_message("Command " + cmd + " already exists")
            self.log.warning("Tried to create a command " + cmd + " that already exists")

    def set_command(self, args, quiet=False):
        cmd = args[2]
        text = ' '.join(args[3:])

        for command in self.commands:
            if command['name'] == cmd:
                command['value'] = text
                self.write_JSON()
                if not quiet:
                    self.bot.send_message("New message for command " + cmd + ": " + text)
                self.log.info("Modified the value of command " + cmd + " to: " + text)
                return
        if not quiet:
            self.bot.send_message("Command " + cmd + " not found")
        self.log.warning("Tried to change the text of a nonexisting command: " + cmd)

    def remove_command(self, args):
        cmd = args[2]

        if self.exists_command(cmd):
            to_remove = None
            for command in self.commands:
                if command['name'] == cmd:
                    to_remove = command
            self.commands.pop(to_remove)  # Do not modify the loop variable on the go

            self.bot.accessmanager.remove_acl("commands.!" + cmd)
            self.write_JSON()
            self.bot.send_message("Deleted command " + cmd)
            self.log.info("Deleted command:" + cmd)

            if len(args) > 3:
                self.set_command(cmd, ' '.join(args[3:]))

        else:
            self.bot.send_message("Command " + cmd + " does not exist")
            self.log.warning("Tried to delete a command " + cmd + " that does not exist")

    def list_commands(self):
        cmds = ""
        for command in self.commands:
            if cmds is "":
                cmds += command["name"]
            else:
                cmds += ", " + command["name"]

        self.bot.send_message("Available commands: " + cmds)

    def set_regulars(self, args):
        if len(args) < 4:
            self.bot.send_message("Not enough arguments")
            self.log.warning("Not enough arguments given to \"regulars\" command")
            return

        cmd = args[2]
        if not self.exists_command(cmd):
            self.bot.send_message("No such command as: " + cmd)
            self.log.warning("tried to change the \"regulars\"-value on an invalid command")
            return

        value = args[3].lower()
        if not (value == "on" or value == "off"):
            self.bot.send_message("Invalid value for regulars: " + value)
            self.log.warning("Invalid value passed to set-regulars")
            return
        if value == "on":
            self.bot.accessmanager.add_group_to_acl("commands.!" + cmd, "%all%")
        if value == "off":
            self.bot.accessmanager.remove_group_from_acl("commands.!" + cmd, "%all%")