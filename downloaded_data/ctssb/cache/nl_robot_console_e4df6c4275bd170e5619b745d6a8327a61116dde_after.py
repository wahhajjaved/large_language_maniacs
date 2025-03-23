#! /usr/bin/python
import cmd
import sys

from action_server import Client
from ed.srv import SimpleQuery
from nl_robot_console.srv import TextCommandRequest, TextCommandResponse, TextCommand
import rospy

from grammar_parser import cfgparser

from robocup_knowledge import load_knowledge


# ----------------------------------------------------------------------------------------------------

class RobotConnection(Client):
    def __init__(self, robot_name):
        Client.__init__(self, robot_name)

        self.world_model_query = rospy.ServiceProxy(robot_name + "/ed/simple_query", SimpleQuery)

# ----------------------------------------------------------------------------------------------------

def recurse_replace_in_dict(d, mapping):
    """
    Recursively replace values in a dictionary according to some mapping, if the mapping has an entry
    :param d: a python dictionary in which some items must be replaced
    :param mapping: a python dictionary
    :return: the dictionary with some values replaces according to the given mapping

    >>> mapping = {'A': 'apple', 'B':'banana'}
    >>> flat = {'a': 'A', 'b': 'B'}
    >>> recurse_replace_in_dict(flat, mapping)
    {'a': 'apple', 'b': 'banana'}

    >>> flat = {'a': 'A', 'b': {'c':'courgette'}}
    >>> recurse_replace_in_dict(flat, mapping)
    {'a': 'apple', 'b': {'c': 'courgette'}}

    >>> deep_nested = {'a': 'A', 'b': {'c':{'a': 'A', 'b': 'B'}}}
    >>> recurse_replace_in_dict(deep_nested, mapping)
    {'a': 'apple', 'b': {'c': {'a': 'apple', 'b': 'banana'}}}
    """
    for key in d.keys():
        # Looks magic, but the .get-method of a dict checks if the given entry is in the dict and if it is not, use a default.
        # In this case, if there is an entry for d[key], use it but otherwise default to current value of d[key]
        if isinstance(d[key], dict):
            d[key] = recurse_replace_in_dict(d[key], mapping)
        else:
            d[key] = mapping.get(d[key], d[key])
    return d

class REPL(cmd.Cmd):

    def __init__(self, knowledge_name, debug=False):
        cmd.Cmd.__init__(self)
        self.debug = debug
        self.prompt = "> "
        self.use_rawinput = True
        self.knowledge = load_knowledge(knowledge_name)
        self._load_grammar()

        # Default robot connection
        self.robot_connection = None
        self.robot_to_connection = {}
        self._get_or_create_robot_connection("amigo")

        self._clear_caches()
        
        # TODO #5: add a dictionary to record that "ice_tea" must map back to "ice tea"
        self._underscore_mapping = {}

    def srvTextCommand(self, request):
        response = TextCommandResponse()
        try:
            self.default(request.command, True)
            response.success = True
        except:
            response.success = False

        return response

    def _load_grammar(self):
        self.parser = cfgparser.CFGParser.fromstring(self.knowledge.grammar)
        self.parser.set_function("id", self.enum_id)
        self.parser.set_function("type", self.enum_type)
        self.parser.set_function("number", self.enum_number)
        self.parser.set_function("property", self.enum_property)

    def _clear_caches(self):
        self._entities = []
        self._updated_wm = False

    def _get_or_create_robot_connection(self, robot_name):
        self.prompt = "[%s] > " % robot_name

        if not robot_name in self.robot_to_connection:
            self.robot_connection = RobotConnection(robot_name)
            self.robot_to_connection[robot_name] = self.robot_connection
        else:
            self.robot_connection = self.robot_to_connection[robot_name]

        return self.robot_connection

    def _update_wm(self):
        if self._updated_wm:
            return

        try:
            self._entities = self.robot_connection.cl_wm().entities
        except rospy.service.ServiceException, e:
            print("\n\n    %s\n" % e)

        self._updated_wm = True

    def emptyline(self):
        pass

    def do_help(self, str):
        print """
        Write a command in natural language. You can either prefix the
        command with a robot name, or leave it out and the command will
        be sent to the last robot specified.

        Examples:

            amigo go to the kitchen
            amigo grab the green drink from the table
            go to 2.45 -0.67
            grab the drink with left
            turn right
            turn 45 degrees left

        *Note that tab-completion is available!*

        Some special commands:

            reload - reloads the grammar
            help   - shows this
            exit   - quits
        """

    def do_EOF(self, line):
        'exit the program. Use  Ctrl-D (Ctrl-Z in Windows) as a shortcut'
        return True

    def default(self, command, debug=False):
        debug = debug or self.debug

        if not command:
            return False
        elif command in ["quit", "exit"]:
            return True  # True means interpreter has to stop
        elif command == "reload":
            self._load_grammar()
        else:
            params = self.parser.parse(self.knowledge.grammar_target, command.strip().split(" "), debug=debug)
            if not params:
                print("\n    I do not understand.\n")
                return False

            # TODO #5: Here, map the "ice_tea" back to the original "ice tea"
            # params = recurse_replace_in_dict(params, self._underscore_mapping)
            semantics = str(params)  # To have the edits done on params also performed on the semantics.

            if debug:
                print params

            if "robot" in params:
                robot_name = params["robot"]
                self._get_or_create_robot_connection(robot_name)

            if not self.robot_connection:
                print("\n    Please specify which robot to use.\n")
                return False

            result = self.robot_connection.send_task(semantics=semantics)
            if not result.succeeded or debug:
                print "\n    Result from action server:\n\n        {0}\n".format(result)

        return False

    def postcmd(self, stop, line):
        # After a command is processed, clear the caches (e.g. world model entities)
        self._clear_caches()
        return stop

    def completedefault(self, text, line, begidx, endidx):
        try:
            partial_command = line.split(" ")[:-1]
            words = self.parser.next_word(self.knowledge.grammar_target, partial_command)
        except Exception as e:
            print e

        return [w + " " for w in words if w.startswith(text)]

    # ---------------------------------------

    def enum_id(self, L):
        self._update_wm()

        ids = [e.id for e in self._entities]

        opts = []
        for id in ids:
            if id != "":
                opts += [cfgparser.Option(id, [cfgparser.Conjunct(id)])]

        return opts

    def enum_type(self, L):
        self._update_wm()

        types = set([i for sublist in [e.types for e in self._entities] for i in sublist])

        opts = []
        for t in types:
            if t != "":
                if " " in t:
                    # TODO #5: Here, map the "ice tea" back to the grammar-parseable "ice_tea"
                    t_with_underscore = t.replace(" ", "_")
                    self._underscore_mapping[t_with_underscore] = t
                    t = t_with_underscore
                opts += [cfgparser.Option(t, [cfgparser.Conjunct(t)])]

        return opts

    def enum_property(self, L):
        options = []

        colors = ["red", "green", "blue", "yellow", "brown", "orange", "black", "white", "pink", "purple", "gray"]
        options += [cfgparser.Option("\"color\": \"%s\"" % c, [cfgparser.Conjunct(c)]) for c in colors]

        sizes = ["large", "medium", "small"]
        options += [cfgparser.Option("\"size\": \"%s\"" % s, [cfgparser.Conjunct(s)]) for s in sizes]

        return options

    def enum_number(self, L):
        if not L:
            return [cfgparser.Option("", [cfgparser.Conjunct("<NUMBER>")])]
        try:
            f = float(L[0])
            return [cfgparser.Option(L[0], [cfgparser.Conjunct(L[0])])]
        except ValueError:
            return []

# ----------------------------------------------------------------------------------------------------

def main():

    import sys

    cmd = None
    debug = False
    service = False
    if len(sys.argv) >= 2:
        debug = "--debug" in sys.argv
        if debug:
            sys.argv.remove("--debug")

    if len(sys.argv) >= 2:
        service = "--service" in sys.argv
        if service:
            sys.argv.remove("--service")

    if len(sys.argv) >= 2:
        cmd = sys.argv[1]


    try:
        rospy.init_node("nl_robot_console")
        repl = REPL("challenge_gpsr", debug=debug)

        if cmd:
            repl.default(cmd, debug=debug)
            return 0
        elif service:
            rospy.spin()
        else:
            repl.cmdloop()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    sys.exit(main())
