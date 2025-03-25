import json
import logging
import os
import datetime

import tools
import exceptions


class Commands:
    """
    Module to manage custom commands
    """

    def __init__(self):
        # Logger instance for this module
        self.log = logging.getLogger("mustikkabot.commands")
        # Handle to the root instance
        self.bot = None

        # Array of the commands loaded
        self.commands = []

        # Message to show when called without arguments
        self.helpMessage = "Usage: !commands list | add <cmd> | remove <cmd> | set <cmd> <text> | " \
                           "regulars <cmd> <value> | setrepeat <cmd> <time> [<lines>]"
        # Hidden commands: '!commands save' and '!commands load' for managing the JSON

    def init(self, bot):
        self.bot = bot

        # Name of the JSON file
        self.jsonpath = os.path.join(self.bot.datadir, "commands.json")

        self.read_JSON()

        for command in self.commands:
            bot.accessmanager.register_acl("commands.!" + command['name'])

        bot.eventmanager.register_message(self)
        bot.timemanager.register_interval(self.check_repeats, datetime.timedelta(seconds=20), datetime.timedelta(seconds=10))

        self.log.info("Init complete")

    def dispose(self):
        """
        Uninitialize the module when called by the eventmanager. Unregisters the messagelisteners
        when the module gets disabled.
        """
        self.bot.eventmanager.unregister_message(self)

    def check_repeats(self):
        for command in self.commands:
            if 'repeat' in command.keys() and command['repeat']:
                if not 'lastshown' in command.keys():
                    self.bot.send_message(command['value'])
                    self.log.info("Showed message for command " + command['name'] + " on repeat")
                    command['lastshown'] = datetime.datetime.now()
                    return # Send only one command/cycle to prevent spam
                else:
                    if (datetime.datetime.now() - command['lastshown']) > datetime.timedelta(minutes=command['repeattime']):
                        self.bot.send_message(command['value'])
                        self.log.info("Showed message for command " + command['name'] + " on repeat")
                        command['lastshown'] = datetime.datetime.now()
                        return # Send only one command/cycle to prevent spam
        
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

    # noinspection PyPep8Naming
    def read_JSON(self):
        """
        Read the JSON datafile from disk that contains all saved commands
        :return: None
        """

        if not os.path.isfile(self.jsonpath):
            if os.path.isfile(os.path.join(self.bot.basepath, "src", "commands.json")):
                self.log.info("Commands-datafile found at old location, moving")
                if not os.path.isdir(self.bot.datadir):
                    os.mkdir(self.bot.datadir)
                os.rename(os.path.join(self.bot.basepath, "src", "commands.json"),
                          self.jsonpath)
            else:
                self.log.info("Commands-datafile does not exist, creating")
                self.write_JSON()

        jsondata = ""
        try:
            with open(self.jsonpath, "r") as file:
                jsondata = file.read()
        except:
            self.log.error("Could not open " + self.jsonpath)
            raise exceptions.FatalException("Could not open " + self.jsonpath)

        try:
            self.commands = json.loads(jsondata)
        except ValueError:
            self.log.error("commands-file malformed")

    # noinspection PyPep8Naming
    def write_JSON(self):
        """
        Write the loaded commands to disk in JSON format
        :return: None
        """
        file = open(self.jsonpath, "w")
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

    """
    " User commands
    """

    def add_command(self, args):
        cmd = args[2]

        if not self.exists_command(cmd):
            if len(args) > 3:
                text = ' '.join(args[3:])
            else:
                text = ""

            self.commands.append({"name": cmd, "value": text})

            self.bot.accessmanager.register_acl("commands.!" + cmd)
            self.write_JSON()
            self.bot.send_message("Added command " + cmd)
            self.log.info("Added new command:" + cmd)
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
            self.commands.remove(to_remove)  # Do not modify the loop variable on the go

            self.bot.accessmanager.remove_acl("commands.!" + cmd)
            self.write_JSON()
            self.bot.send_message("Deleted command " + cmd)
            self.log.info("Deleted command:" + cmd)
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

    def set_repeat(self, args):
        #args: !commands setrepeat cmd time lines
        if len(args) < 4:
            self.bot.send_message("Not enough arguments. Please use '!commands setrepeat <cmd> <time> [<lines>]'. Zero "
                                  "<time> or <lines> means that the condition is ignored. Zeroing both removes repeat.")
            return

        try:
            cmd = int(args[2])
            time = int(args[3])
            if len(args) < 5:
                lines = 0
            else:
                lines = int(args[4])

            if time < 0 or lines < 0:
                raise ValueError
        except ValueError:
            self.bot.send_message("Invalid arguments, <time> and <lines> must be numbers 0 or bigger")
            self.log.warning("Invalid non-integer arguments given to setrepeat")

        if not self.exists_command(cmd):
            self.bot.send_message("Invalid command name " + cmd)
            self.log.warning("Tried to modify repeat setting for invalid command " + cmd)

        if time == 0 and lines == 0:
            self.commands[cmd]['repeat'] = False
            self.bot.send_message("Repetition disabled for command " + cmd)
        else:
            self.commands[cmd]['repeat'] = True
            self.commands[cmd]['repeattime'] = time
            self.commands[cmd]['repeatlines'] = lines

            msg = "Repetition enabled for command " + cmd + " every "
            if time:
                msg += str(time) + " minutes"
            if time and lines:
                msg += " and "
            if lines:
                msg += str(lines) + " lines"

            self.bot.send_message(msg)
            self.log.info(msg)
