#!/usr/bin/env python
"""
tool used to do operation on a list of entrys, and these entrys were
defined in a given file

the program will support to process a number of entries in one running
instance, the entries will be poped from the beginning, and put it behind
of the list, and also comment it out

NOTE: the tool do not support shell buildin command, the command should
      exist as a file 
"""

import sys
import re
import subprocess
import os
import shlex
import time

#log_file = "/usr/local/fountain/utils/rmv_program.log"
log_file = "./rmv_program.log"
# command which used to operate on entries, %s was used to be replace by
# entry
#command_file = "/usr/local/fountain/utils/del_files"
command_file = "/home/denny/work/code/tools/python/test/aa"
command_argument = "-h 127.0.0.1 -p 8888 -f"
# following to regular expression are used to capture valid data from
# file, the regular expression should contain only one group, and program
# will only capture the first captured group.
# captureRe = re.compile(r"\/\w+\/(\w+)");
captureRe = re.compile(r"(.+)");

# temp file will be generate for the entry list file, and mark the finished
# entries in the temp file first, and then after the program complete,
# override original file, here just to choose how to name the temp file
tmp_suffix = ".tmp"

# define how many entries will be processed this time, means the current
# running instance just pop a number of entries to be processed. the value
# can be set from the command line, and default to 5
how_many_entry_once = 5

# sleep interval btween each operation
sleep_interval = 2 # seconds

entry_dict = { "TODO":[], "FAIL":[], "COMPLETE":[] }

class entry:
    def __init__(self, initial_input, expression):
        self.initial_data = initial_input
        self.valid_data = captureData(self.initial_data, expression)
        self.status = "NOT_START"
    def getInitialData(self):
        return self.initial_data
    def getValidData(self):
        return self.valid_data
    def setStatus(self, result):
        self.status = result
    
def log(string):
    # sys.stdout.write(string)
    print string

def logFile(text):
    global log_file
    ISOTIMEFORMAT='%Y-%m-%d %X'
    current_time = time.strftime( ISOTIMEFORMAT, time.localtime() )
    os.system("echo \"%s\n%s\" >> %s"%(current_time, text, log_file))

def open_file(file_name, mode="r"):
    """ open file, return None if fail, capture the system exception,
    and handle open file fail by self """
    try:
        fp = open(file_name, mode)
        return fp
    except:
        return None
        
def usage():
    log("***********************************************************\n"
        "script used to do some operation on a given list of entries\n"
        "Usage: %s <file_of_list_entries> [ <number_of_record_to_execute> ]\n"
        "************************************************************"
        %sys.argv[0])

def isCommented(line):
    """ check if the current line is commented out """
    commentRe = re.compile(r'\s*#.*')
    if commentRe.match(line):
        return True
    return False

def isBlank(line):
    """ check if the current line is a blank line """
    blankRe = re.compile(r'\s*[\r|\n]$')
    if blankRe.match(line):
        return True
    return False

def isIgnored(line):
    """ ignore the blank line and comment line """
    return isCommented(line) and isBlank(line)

def validateData(record, expression):
    """ the record should be in a given valid format, which can satisfy
    a given regular expression
    example:
        /media/201212030050010 can satisfy "\/\w+\/(\w+)"
    """
    m = expression.match(record)
    if m:
        return True
    log("validation fail for path %s"%record)
    return False
    
def captureData(line, expression):
    """ parse the input line in the file_X, and return the captured
    data which is considered a valid data for comparation
    the regular expression should contain only one group, and program
    will only capture the first captured group.
      example:
        record    /media/201212030050010
        re        "\/\w+\/(\w+)"
        captured  201212030050010
      Argument:
        line initial data of the record
        re_for_file_X regular expression for file X
      Return:   valid captured data 
    """
    m = expression.match(line)
    if not m:
        return None
    try:
        ret = m.group(1)
    except:
        log("fail to capture data for: %s, check your regular expression"%line)
        exit()
    return ret

def handleCommentLine(line, expression, complist):
    """ remove the # sign and put the record to complete list """
    line = line.strip()
    e = entry(line.replace('#', ""), expression)
    if not e.getValidData():
        return
    complist.append(e)
    
    
def handleTodoLine(line, expression, todoList):
    """ add entry to the Todo list """
    line = line.strip()
    e = entry(line, expression)
    if not e.getValidData():
        return
    todoList.append(e)

def putRecordToList(file_name, expression, edict):
    """ parse the file path to get the content id, and put it to the list ,
    the comments line means the record has been completed the operation """
    fp = open_file(file_name)
    if not fp:
        log("fail to open file %s"%file_name)
        exit()
    while True:
        line = fp.readline()
        if not line:
            break
        if isBlank(line):
            continue
        if isCommented(line):
            handleCommentLine(line, expression, edict["COMPLETE"])
        else:
            handleTodoLine(line, expression, edict["TODO"])
    fp.close()

def executeCMD(cmd):
    """ execute command, save the output to log file, and return the
    execution result code """
    logFile(cmd)
    # should check whether the command succeed, and if not, append it
    # to the entry list, and wait to re-run next time
    args = shlex.split(cmd)
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    # get the output of the command, and write it to log file
    out, err = p.communicate()
    logFile(out)
    return p.returncode
    
def commandOnEntries(command, edict):
    """ operate the command on each entry, only operate on a number of
    entries on top, and put it behind with commented out """
    global how_many_entry_once, log_file, sleep_interval
    count = fail_count = succ_count = 0
    todoList = edict["TODO"]
    compList = edict["COMPLETE"]
    failList = edict["FAIL"]
    while (count < how_many_entry_once) and (len(todoList) != 0):
        time.sleep(sleep_interval)
        entry = todoList.pop(0) # pop from the first item
        full_command = command + " " + entry.getValidData()
        log("processing [ " + full_command + " ]")
        ret = executeCMD(full_command)
        if ret == 0: # succeed call
            entry.setStatus("COMPLETE")
            compList.append(entry)
            succ_count += 1
        else: # fail call
            entry.setStatus("FAIL")
            failList.append(entry)
            log("fail!!")
            fail_count += 1
        count += 1
    log("total %d entry processed, %d failed, check debuglog %s for detail\n"%
        (count, fail_count, log_file))

def checkCommandFileExist(path):
    if os.path.exists(path):
        return True
    return False

def saveListsToFile(file_name, edict):
    """ save the left, complete, fail entry list to file """
    global tmp_suffix
    todoList = edict["TODO"]
    compList = edict["COMPLETE"]
    failList = edict["FAIL"]
    fp = open_file(file_name+tmp_suffix, "w")
    for e in todoList:
        fp.write(e.getInitialData() + "\n")
    for e in failList:
        fp.write(e.getInitialData() + "\n")
    for e in compList:
        fp.write("#" + e.getInitialData() + "\n")
    fp.close()
    # save tmp file back to original file
    os.system("cp %s %s"%(file_name + tmp_suffix, file_name))
    
def call_rmv(file_name, expression, command_file, argument):
    global entry_dict
    putRecordToList(file_name, expression, entry_dict)
    command = command_file + " " +  argument
    commandOnEntries(command, entry_dict)
    saveListsToFile(file_name, entry_dict)

if __name__ == "__main__":
    if len(sys.argv) > 3:
        usage()
        exit()

    if len(sys.argv) == 3:
        if not sys.argv[2].isdigit():
            log("the second argument should be digit number")
            exit()
        how_many_entry_once = int(sys.argv[2])
            
    if not checkCommandFileExist(command_file):
        log("command file not exist: %s"%command_file)
        exit()
        
    file_of_list_entries = sys.argv[1]
    
    call_rmv(file_of_list_entries,
             captureRe,
             command_file,
             command_argument)

