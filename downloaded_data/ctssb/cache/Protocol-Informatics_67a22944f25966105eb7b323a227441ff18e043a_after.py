# vim: set sts=4 sw=4 cindent nowrap expandtab:

import cmd, sys, os

class CommandLineInterface(cmd.Cmd):
    def __init__(self, config = None):
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
        # only enter PI if we have alrady read some sequences ...
        if not 'sequences' in self.env:
            print "Cannot enter PI mode. Please read some sequences before you do this ..."
            return
            
        import picli
        inst = picli.PICommandLineInterface(self.env)
        inst.prompt = self.prompt[:-1]+':PI> '
        inst.cmdloop()

    def do_config(self, string):
        if string == "":
            print "Current configuration: "
            self.config.print_config()
            return

        import common

        try:
            newConfig = common.config.loadConfig(string)
        except Exception as inst:
            print "Error: Could not read configuration file \"%s\": %s" % (string, inst)
            print "Using old config ..."
            return
        self.config = newConfig
        self.env['config'] = self.config

    def applyConfig(self):
        print "Read configuration file. Trying to apply immediate changes"
        if self.config.inputFile != None:
            print "Found input file in configuration. Trying to read it ..."
            readString = self.config.inputFile + " " + self.config.format
            self.do_read(readString)
        
        
    def help_config(self):
        print "Command syntax: configuration <file>"
        print ""
        print "Reads a configuration from <file>. Configuration format"
        print "is yaml. It needs to be in the same format as the configuration"
        print "files presented to the command line switch -c"

        
    def do_read(self, string):
        import common
        words = string.split()
        if len(words) == 1:
            # we only received an input file. try to guess the format
            print "ERROR: Format guessing not yet implemented ... Please specify format. "
            self.help_read()
            return
            print "Trying to read file \"" + words[0] + "\"..."
            print "No format specified. Trying to guess format. Please specify format"
            return 

            sequences = None
            for reader in common.input.__all__[1:-1]:
                print "Trying reader " + reader + "..."
            
        elif len(words) == 2:
            try:
                print "Attempting to read file \"%s\" as \"%s\" file" % (words[0], words[1])
                # we expect a file and a format string
                if words[1] == "pcap":
                    sequences = common.input.Pcap(words[0], self.config.maxMessages, self.config.onlyUniq, self.config.messageDelimiter, self.config.fieldDelimiter)
                elif words[1] == "bro":
                    sequences = common.input.Bro(words[0], self.config.maxMessages, self.config.onlyUniq, self.config.messageDelimiter, self.config.fieldDelimiter)
                elif words[2] == "ascii":
                    sequences = common.input.ASCII(words[0], self.config.maxMessages, self.config.onlyUniq, self.config.messageDelimiter, self.config.fieldDelimiter)
                else:
                    print "Error: Format \"" + words[1] + "\" unknown to reader"
            except Exception as inst:
                print ("FATAL: Error reading input file '%s':\n %s" % (file, inst))
                return
            self.env['sequences'] = sequences
        else:
            # unknown command format
            print "Error in read syntax."
            self.help_read()
            return
        print "Successfully read input file ..."

    def help_read(self):
        print "Command syntax: read <file> [<bro|pcap|ascii>]"
        print ""
        print "Tries to read messages from a file. You need to specify the filename."
        print "The input module will try to guess the input format. If you specify a"
        print "format, of either bro, pcap, or ascii, the appropriate reader will be"
        print "called."
            
    def emptyline(self):
        pass

    def do_set(self, string):
        if string == "":
            self.help_set()
            return

        words = string.split(' ')
        if len(words) != 2:
            print "Invalid command syntax"
            self.help_set()

        # try to set an object in the configuration object
        try:
            setattr(self.config, words[0], words[1])
        except Exception as inst:
            print "Error: Could not set \"%s\" to \"%s\": %s" % (words[0], words[1], inst)

    def help_set(self):
        print "Command synatx: set <variable> <value>"
        print ""
        print "Sets the configuration variable <variable> to value"
        print "<vlaue>. This change is temporary and will be erased"
        print "on the next restart of Protocol Informatics. Use"

    def do_saveconfig(self, string):
        if string == "":
            print "Invalid command syntax."
            self.help_saveconfig()
            return
        try:
            import common
            common.config.saveConfig(self.config, string)
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
            print i + ":\t\t" + str(self.env[i])
            
    def help_env(self):
        print "Command syntax: env"
        print ""
        print "Prints the current environment content."
