# vim: set sts=4 sw=4 cindent nowrap expandtab:

import cmd, sys, os, signal, time

lastEOF = 0

def sig_int_handler(signum, frame):
    global lastEOF
    if lastEOF == 0 or lastEOF < int(time.time()):
        print "Received Sigint. Please use quit, EOF or exit to exit the program. Or quickly tap a second time ..."
        lastEOF = int(time.time())
        return
    print "Hard shutdown ..."
    sys.exit(0)
    
class CommandLineInterface(cmd.Cmd):
    def __init__(self, config = None):
        signal.signal(signal.SIGINT, sig_int_handler)

        cmd.Cmd.__init__(self)
        self.prompt = "inf> "
        sys.path.append("../")
        
        self.env = dict()

        import common
        if config != None:
            self.config = config
            self.applyConfig()
        else:
            self.config = common.config.Configuration()

    def cmdloop(self):
        try:
            cmd.Cmd.cmdloop(self)
        except Exception as inst:
            print "Whoa. Caught an exception: %s" % (inst)
            import traceback
            traceback.print_exc(file=sys.stdout)

    def do_EOF(self, string):
        print string
        sys.exit(0)

    def do_quit(self, string):
        sys.exit(0)

    def do_exit(self, string):
        sys.exit(0)

    def help_quit(self):
        print "Quit the program."
    
    def help_EOF(self):
        self.help_quit()

    def help_exit(self):
        self.help_quit()

    def do_restart(self, string):
        print "Trying to restart Protocol Informatics..."
        executable = sys.executable
        args = sys.argv[:]
        args.insert(0, sys.executable)
        os.execvp(executable, args)

    def do_PI(self, string):            
        import picli
        inst = picli.PICommandLineInterface(self.env, self.config)
        inst.prompt = self.prompt[:-1]+':PI> '
        inst.cmdloop()
        print "Finishing PI mode ..."
        self.config = inst.config
        self.env = inst.env

    def do_seqs(self, string):
        import seqcli
        inst = seqcli.SequencesCommandLineInterface(self.env, self.config)
        inst.prompt = self.prompt[:-1]+':Seqs> '
        inst.cmdloop()
        print "Finishing sequence modify mode ..."
        self.config = inst.config
        self.env = inst.env
        

    def do_config(self, string):
        if string == "":
            print "Current configuration: "
            self.config.print_config()
            return

        # try to find a command like "config <variable> <value>
        words = string.split()
        if len(words) != 2:
            # ok, we didn't find it yet. lets trye for format 
            # "config <variable>=<value>
            words = string.split('=')
            if len(words) != 2:
                # ok, we have no idea what this should be ..."
                print "Invalid command syntax"
                self.help_config()
                return

        # try to set an object in the configuration object
        try:
            targetClassType = type(getattr(self.config, words[0]))
            import types
            if targetClassType == types.NoneType or words[0] == "None":
                newVal = None
            elif targetClassType == types.BooleanType:
                if words[1] == "True":
                    newVal = True
                elif words[1] == "False":
                    newVal = False
            else:
                newVal = targetClassType(words[1])
            setattr(self.config, words[0], newVal)
        except Exception as inst:
            print "Error: Could not set \"%s\" to \"%s\": %s" % (words[0], words[1], inst)


    def applyConfig(self):
        print "Read configuration file. Trying to apply immediate changes"
        if self.config.inputFile != None:
            print "Found input file in configuration. Trying to read it ..."
            if self.config.format != None and self.config.inputFile != None and self.config.inputFile != "":
                readString = self.config.format+ " " + self.config.inputFile
                self.do_read(readString)
            
        
    def help_config(self):
        print "Command synatx: config [<variable> <value>|<variable>=<value]"
        print ""
        print "If no argument is given to the config command, the current "
        print "configuration set is printed."
        print "Otherwise, this command Sets the configuration variable <variable>"
        print "to value <vlaue>. This change is temporary and will be erased"
        print "on the next restart of Protocol Informatics. Use"


    def do_read(self, string):
        import common
        words = string.split()
        if len(words) != 2:
            self.help_read()
            return

        formatType = words[0]
        filename = words[1]

        sequences = None
        try:
            print "Attempting to read file \"%s\" as \"%s\" file" % (filename, formatType)
            # we expect a file and a format string
            if formatType == "pcap":
                sequences = common.input.Pcap(filename, self.config.maxMessages, self.config.ethOffsetoutout).getConnections()
            elif formatType == "bro":
                sequences = common.input.Bro(filename, self.config.maxMessages).getConnections()
            elif formatType == "ascii":
                sequences = common.input.ASCII(filename, self.config.maxMessages).getConnections()
            elif formatType == "config":
                try:
                    newConfig = common.config.loadConfig(filename)
                except Exception as inst:
                    print "Error: Could not read configuration file \"%s\": %s" % (filename, inst)
                    print "Using old config ..."
                    return
                self.config = newConfig
                self.applyConfig()
            else:
                print "Error: Format \"" + format + "\" unknown to reader"
                return
        except Exception as inst:
            print ("FATAL: Error reading input file '%s':\n %s" % (filename, inst))
            return

        if sequences != None:
            self.env['sequences'] = sequences

        print "Successfully read input file ..."

    def help_read(self):
        print "Command syntax: read [<bro|pcap|ascii|config>] <file>"
        print ""
        print "Tries to read file <file> in the specified format. If format"
        print "equals \"config\", a new configuration file is read from <file>."
        print "In all other cases, input data for the protocol inferences are "
        print "read in the specified format (bro, pcap, ascii)"
            
    def emptyline(self):
        pass

    def do_saveconfig(self, string):
        import common
        if string == "":
            if self.config.configFile == None:
                print "No filename associated with config file. Please specify a filename"
                return
        else:
            self.config.configFile = string

        try:
            common.config.saveConfig(self.config, self.config.configFile)
        except Exception as inst:
            print "Error: Could not save config file: %s" % (inst)

    def help_saveconfig(self):
        print "Command syntax: saveconfig <filename>"
        print ""
        print "Save a yml configuration file to <filename>, which"
        print "can be used as a command line argument or as input"
        print "for config <filename>"

    def do_env(self, string):
        print "Currently contained in env:"
        for i in self.env:
            self.show_type(self.env[i], i)
            
    def help_env(self):
        print "Command syntax: env"
        print ""
        print "Prints the current environment content."

    def do_show(self, string):
        if string == "":
            self.do_env("")
            return

        if not string in self.env:
            print "\"%s\" not in env!" % (string)
            return

        self.show_type(self.env[string], string)

    def help_show(self, string):
        print "Command syntax: show <variable>"
        print ""
        print "Show the contents of the environment variable"
        print "<variable>."

    def show_type(self, obj, objIdentifier = ""):
        if type(obj) == type(dict()):
            print "Found dictionary \"%s\" with content:" % (objIdentifier)
            for i in obj:
                print i + "\t\t" + str(obj[i])
        else:
            print objIdentifier + ":\t\t" + str(obj)
