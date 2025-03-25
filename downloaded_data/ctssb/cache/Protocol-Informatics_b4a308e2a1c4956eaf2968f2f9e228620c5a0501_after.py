import yaml, sys

def loadConfig(filename):
    cf = file(filename, 'r')
    config = yaml.load(cf)
    return Configuration(config)

def loadConfigFromDict(d):
    return Configuration(config)

def saveConfig(configuration, filename):
    cf = file(filename, 'w')
    yaml.dump(vars(configuration), cf)

class Configuration:
    def __init__(self, d = None):
        # Defaults
        self.format = "pcap"
        self.weight = float(1.0)
        self.graph = False
        self.maxMessages = 50
        self.messageDelimiter = None
        self.fieldDelimiter = None
        self.textBased = False
        self.configFile = None
        self.analysis = None
        self.gnuplotFile = None
        self.onlyUniq = False
        self.interactive = True
        self.inputFile = None

        # update from the config dictionary if available
        if d != None:
            self.__dict__.update(d)
            if not self.checkConfig():
                print "FATAL: Could not initialize from configuration."
                sys.exit(-1)


    def checkConfig(self):
        # do sanity checks
        if self.weight < 0.0 or self.weight > 1.0:
            print "FATAL: Weight must be between 0 and 1"
            return False
        return True

    def print_config(self):
        elems = vars(self)
        maxLen = 20
        for i in elems:
            value = getattr(self,i)
            print i,
            for j in range(maxLen - len(i)):
                print "",
            print str(value),
            for j in range(maxLen - len(str(value))):
                print "", 
            print "\t\t" + str(type(value))

