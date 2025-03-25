import sys, os
import time
import re
from Utils.Connection.Unix import getConnection

def getMaxJobsFromFile(controlFilename):
    f = open(controlFilename, "rt")
    lines = f.readlines()
    f.close()
    assert len(lines) == 1
    value = int(lines[0])
    if value == 0:
        print >> sys.stderr, "Exit by control file request"
        sys.exit() 
    return value

def getMaxJobs(maxJobs, controlFilename=None):
    if maxJobs == None:
        if controlFilename != None:
            return getMaxJobsSetting(controlFilename)
        else:
            return None
    else:
        return maxJobs

def prepareCommand(template, input=None, jobTag=None, output=None):
    if "%i" in template or "%a" in template or "%b" in template:
        assert input != None
        template = template.replace("%i", input)
        template = template.replace("%a", os.path.abspath(input))
        template = template.replace("%b", os.path.basename(input))
    if "%j" in template:
        assert jobTag != None
        template = template.replace("%j", jobTag)
    if "%o" in template:
        assert output != None
        template = template.replace("%o", output)
    return template

def submitJob(command, input, connection, jobTag=None, output=None, regex=None, dummy=False, rerun=None, hideFinished=False):
    if input != None and input.endswith(".job"):
        if connection.debug:
            print >> sys.stderr, "Skipped job control file", input
        return
    if connection.debug:
        print >> sys.stderr, "Preparing to submit a job for input", input
    if regex != None and regex.match(input) == None:
        if connection.debug:
            print >> sys.stderr, "Regular expression did not match input, no job submitted"
        return
    elif connection.debug and input != None:
        print >> sys.stderr, "Regular expression matched the input"
    
    if input != None:
        # Determine job name and directory from the input file
        jobDir = os.path.abspath(os.path.dirname(input))
        jobName = os.path.basename(input)
        if jobName == "": # input is a directory
            jobName = jobDir.rstrip("/").split("/")[-1] # use directory name as job name
            jobDir = jobDir.rstrip("/").split("/")[0] # save job control file on the same level as the directory
        if jobTag != None:
            jobName += "-" + jobTag
        # A defined output directory means the job file goes there
        if output != None:
            jobDir = output
    else: # inputless job
        assert jobTag != None
        jobName = jobTag
        jobDir = output
    
    print >> sys.stderr, "Processing job", jobName, "for input", input
    jobStatus = connection.getJobStatusByName(jobDir, jobName)
    if jobStatus != None:
        if rerun != None and jobStatus in rerun:
            print >> sys.stderr, "Rerunning job with status", jobStatus
        else:
            if jobStatus == "RUNNING":
                print >> sys.stderr, "Skipping currently running job"
            elif not hideFinished:
                print >> sys.stderr, "Skipping already processed job with status", jobStatus
            return False         
    
    command = prepareCommand(command, input, jobTag, output)
    
    if not dummy:
        connection.submit(command, jobDir, jobName)
    else:
        print >> sys.stderr, "Dummy mode"
        if connection.debug:
            print >> sys.stderr, "------- Job command -------"
            print >> sys.stderr, command
            print >> sys.stderr, "--------------------------"
    return True

def waitForJobs(maxJobs, submitCount, connection, controlFilename=None, sleepTime=15):
    currentJobs = connection.getNumJobs()
    currentMaxJobs = getMaxJobs(maxJobs, controlFilename)
    print >> sys.stderr, "Current jobs", str(currentJobs) + ", max jobs", str(currentMaxJobs) + ", submitted jobs", submitCount
    if currentMaxJobs != None:
        while(currentJobs > currentMaxJobs):
            time.sleep(sleepTime)
            currentJobs = connection.getNumJobs()
            currentMaxJobs = getMaxJobs(maxJobs, controlFilename)
            print >> sys.stderr, "Current jobs", str(currentJobs) + ", max jobs", str(currentMaxJobs) + ", submitted jobs", submitCount

def getOutputDir(currentDir, input, output=None):
    if output == None:
        return None
    else:
        relativeCurrentDir = os.path.abspath(currentDir)[len(os.path.abspath(input)):]
        return os.path.join(output, relativeCurrentDir)

def batch(command, input=None, connection=None, jobTag=None, output=None, regex=None, regexDir=None, dummy=False, rerun=None, 
          hideFinished=False, controlFilename=None, sleepTime=15, debug=False, limit=None, loop=False):
    connection = getConnection(connection)
    connection.debug = debug
    if input == None: # an inputless batch job:
        waitForJobs(limit, 0, connection, controlFilename, sleepTime)
        submitJob(command, input, connection, jobTag, output, regex, dummy, rerun, hideFinished)
    elif os.path.exists(input) and os.path.isfile(input): # single file
        waitForJobs(limit, 0, connection, controlFilename, sleepTime)
        submitJob(command, input, connection, jobTag, output, regex, dummy, rerun, hideFinished)
    else: # walk directory tree
        firstLoop = True
        submitCount = 0
        while firstLoop or loop:
            waitForJobs(limit, submitCount, connection, controlFilename, sleepTime)
            for triple in os.walk(input):
                if regexDir != None and regexDir.match(os.path.join(triple[0])) == None:
                    print >> sys.stderr, "Skipping directory", triple[0]
                    continue
                else:
                    print >> sys.stderr, "Processing directory", triple[0]
                for item in sorted(triple[1]) + sorted(triple[2]): # process both directories and files
                    #print item, triple, os.path.join(triple[0], item)
                    if submitJob(command, os.path.join(triple[0], item), connection, jobTag, getOutputDir(triple[0], input, output), regex, dummy, rerun, hideFinished):
                        submitCount += 1
                        # number of submitted jobs has increased, so check if we need to wait
                        waitForJobs(limit, submitCount, connection, controlFilename, sleepTime)
            firstLoop = False

if __name__=="__main__":
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
        print >> sys.stderr, "Found Psyco, using"
    except ImportError:
        print >> sys.stderr, "Psyco not installed"

    from optparse import OptionParser
    optparser = OptionParser()
    optparser.add_option("-c", "--command", default=None, dest="command", help="")
    optparser.add_option("-i", "--input", default=None, dest="input", help="Input file or directory. A directory will be processed recursively")
    optparser.add_option("-n", "--connection", default=None, dest="connection", help="")
    optparser.add_option("-r", "--regex", default=None, dest="regex", help="")
    optparser.add_option("-d", "--regexDir", default=None, dest="regexDir", help="")
    optparser.add_option("-j", "--job", default=None, dest="job", help="job name")
    optparser.add_option("-o", "--output", default=None, dest="output", help="")
    optparser.add_option("-l", "--limit", default=None, dest="limit", help="")
    optparser.add_option("--debug", default=False, action="store_true", dest="debug", help="Print jobs on screen")
    optparser.add_option("--controlFile", default=None, dest="controlFile", help="")
    optparser.add_option("--sleepTime", default=None, dest="sleepTime", help="")
    optparser.add_option("--dummy", default=False, action="store_true", dest="dummy", help="Don't submit jobs")
    optparser.add_option("--rerun", default=None, dest="rerun", help="Rerun jobs which have one of these states (comma-separated list)")
    optparser.add_option("--maxJobs", default=None, type="int", dest="maxJobs", help="Maximum number of jobs in queue/running")
    optparser.add_option("--hideFinished", default=False, action="store_true", dest="hideFinished", help="")
    optparser.add_option("--loop", default=False, action="store_true", dest="loop", help="Continuously loop through the input directory")
    (options, args) = optparser.parse_args()
    
    assert options.command != None
    if options.limit != None: options.limit = int(options.limit)
    if options.rerun != None: options.rerun = options.rerun.split(",")
    if options.sleepTime != None: options.sleepTime = int(options.sleepTime)
    if options.regex != None: options.regex = re.compile(options.regex)
    if options.regexDir != None: options.regexDir = re.compile(options.regexDir)
    batch(command=options.command, input=options.input, connection=options.connection, jobTag=options.job,
          output=options.output, 
          regex=options.regex, regexDir=options.regexDir, dummy=options.dummy, rerun=options.rerun, 
          hideFinished=options.hideFinished, controlFilename=options.controlFile, sleepTime=options.sleepTime, 
          debug=options.debug, limit=options.limit, loop=options.loop)