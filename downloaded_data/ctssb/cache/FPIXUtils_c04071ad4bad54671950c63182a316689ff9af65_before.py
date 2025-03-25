#!/usr/bin/env python
import sys
import os
import time
import glob
import smtplib
import curses
from config import moduleNames, goodModuleNames #,shifter ,shifterEmail
from datetime import datetime

tbLine = ["TB:"]
idLine = ["module ID:"]

inputDir = os.path.expanduser('~') + "/allTestResults/"

tbs = []
inputFiles = []
cellLength = 20
for index, module in enumerate(moduleNames):

    if module == "0":
        continue

    tbs.append(index)
    testDirs = glob.glob(inputDir + "/" + module + "_*")
    testDirs.sort(key=lambda x: os.path.getmtime(x))
    testDir = testDirs[-1]
    inputFiles.append(testDir)

for index, module in enumerate(goodModuleNames):
    tbLine.append(str(tbs[index]))
    idLine.append(module)

def moduleCrash(line):
    # following keywords suggest test failure
    isCrashed = False
    if "not programmable; stop" in line or\
        "empty results" in line or\
        "Abort data processing" in line:
        #"Event ID mismatch" in line:
        isCrashed = True
    return isCrashed

def checkEqual(list, str):
    # check if all elements in `list` equal to `str`,
    # blank elements are excluded.
    allEqual = True
    nEmpty = 0
    for element in list:
        if element == "":
            nEmpty += 1
            continue
        if element != str:
            allEqual = False
    if nEmpty != 4:
        return allEqual
    else:
        return False

def str2time(str):
    return datetime.strptime(str,'%H:%M:%S')

def endPrint():
    screen.addstr(9,0,'#'*cellLength*(len(goodModuleNames)+1))
    screen.addstr(10,0, '''\nFull test done!
    An email of summary has been sent to shifter with address provided.\n
    Please wait for a few minutes while results are processing and saving, 
    until you are prompt to hit `ENTER` on console.\n
    [statusReport] This is the end, my friEND.
    ---------Hit any button to exit---------
    ''')

def sendEmail(receiver, content):
    # Using mail.com because of easy registration
    s = smtplib.SMTP('smtp.mail.com', 587)
    s.starttls()
    s.login("cmsfpix@mail.com","PixelUpgrade")
    s.sendmail('cmsfpix@mail.com', [receiver], content)
    s.quit()

def summaryFormat(list):
    line = ""
    for entry in list:
        line += str(entry) + '\t\t'
    return line

screen = curses.initscr()
curses.start_color()
curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)     #DEFAULT
curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)    #WARNING 
curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)       #ERROR
curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK)   #CRITICAL
curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_RED)       #CRASH

for index, x in enumerate(range(0,cellLength*len(goodModuleNames)+1,cellLength)):
    screen.addstr(0, x, tbLine[index])

testStartTime = ['']*4
ivEndTime     = ['']*4
ivDoneFlag    = [0]*4
colorFlag     = [[1 for x in range(len(goodModuleNames)+1)] for y in range(8)] #DEFAULT COLOR

while 1:
    testOutput     = ["current test:"]
    subtestOutput  = ["current subtest:"]
    timeOutput     = ["time duration:"]
    criticalOutput = ["# Criticals:"]
    errorOutput    = ["# pXar errors:"]
    warningOutput  = ["# Warnings:"]
    for index, moduleDir in enumerate(inputFiles):
        test       = ""
        subtest    = ""
        timePassed = ""
        nErrors    = 0
        nCriticals = 0
        nWarnings  = 0
        fpixTestLog = glob.glob(moduleDir + '/' + "000*/commander_*.log")
        if fpixTestLog:
            with open(fpixTestLog[0]) as data_file:
                for line in data_file:
                    if line[0] != '[':
                        continue

                    ## status counting
                    if "WARNING:" in line:
                        nWarnings += 1
                        colorFlag[7][index+1] = 2
                        if colorFlag[1][index+1] < 2:
                            colorFlag[1][index+1] = 2
                    if "ERROR:" in line:
                        nErrors += 1
                        colorFlag[6][index+1] = 3
                        if colorFlag[1][index+1] < 3:
                            colorFlag[1][index+1] = 3
                    if "CRITICAL:" in line:
                        nCriticals += 1
                        colorFlag[5][index+1] = 4
                        if colorFlag[1][index+1] < 4:
                            colorFlag[1][index+1] = 4
                    
                    ## Get current time & test duration
                    nowTime = datetime.now().time().strftime('%H:%M:%S')
                    if testStartTime[index]:
                        timePassed = str2time(nowTime) - str2time(testStartTime[index])

                    ## Get test names & test start time
                    if not any(s in line for s in ('done','took','end','Factory','init','setParameter')):
                        if "doTest()" in line:
                            test = line.split(" ")[7].split('::')[0].replace("PixTest","")
                            testStartTime[index] = line.split(" ")[0].strip('[]')[:-4]
                            subtest = ''
                        if "PixTest" in line and "::" in line and "doTest()" not in line:
                            for entry in line.split(' '):
                                if '::' in entry:
                                    subtest = entry.split('::')[1].replace("()","")
                                if ',' in subtest:
                                    subtest = subtest[:-1]
                                testStartTime[index] = line.split(" ")[0].strip('[]')[:-4]
                
                    ## crash counting
                    if moduleCrash(line):
                        if colorFlag[1][index+1] < 5:
                            colorFlag[1][index+1] = 5
                        msg = "Module "+idLine[index+1]+" failed test["\
                            + test + "] subtest["+subtest+"]."
                        #sendEmail(shifterEmail, msg)
                        
                    ## Go to IV test
                    if "this is the end" in line:
                        ivTestLog = glob.glob(moduleDir + '/' + "001*/IV.log")
                        if ivTestLog:
                            test = "IVtest"
                            with open(ivTestLog[0]) as data_file1:
                                for line in data_file1:
                                    if "Welcome" in line:
                                        testStartTime[index] = line.split(" ")[0].strip('[]')[:-4]
                                    nowTime = datetime.now().time().strftime('%H:%M:%S')
                                    if not ivDoneFlag[index]:
                                        ivEndTime[index] = nowTime
                                    timePassed = str2time(nowTime)\
                                                 - str2time(testStartTime[index])
                                    if "this is the end" in line:
                                        test = "ALL done"
                                        ivDoneFlag[index] = 1
                    if ivDoneFlag[index]:
                        timePassed = str2time(ivEndTime[index])\
                                        - str2time(testStartTime[index])

        testOutput.append(test+' '*(cellLength-len(test)))
        subtestOutput.append(subtest+' '*(cellLength-len(subtest)))
        timeOutput.append(str(timePassed))
        criticalOutput.append(str(nCriticals))
        errorOutput.append(str(nErrors))
        warningOutput.append(str(nWarnings))
    snapshot = [idLine, testOutput, subtestOutput, timeOutput, criticalOutput,\
                 errorOutput, warningOutput]
    for y in range(1,8):
        for index, x in enumerate(range(0,cellLength*len(goodModuleNames)+1,cellLength)):
            screen.addstr(y, x, snapshot[y-1][index],\
                         curses.color_pair(colorFlag[y][index]))
    screen.refresh()
    time.sleep(30)

    if checkEqual(testOutput[1:], "ALL done"+' '*(cellLength-len("ALL done"))):
        content = "Hello " + "shifter"\
               + ",\n\nYour module tests are finished, summarized as bellow:\n\n"\
               + '\t' + summaryFormat(snapshot[0]) + '\n'\
               + '\t' + summaryFormat(snapshot[4]) + '\n'\
               + '\t' + summaryFormat(snapshot[5]) + '\n'\
               + '\t' + summaryFormat(snapshot[6]) + '\n'\
               + "\n\nThank you!"
        #sendEmail(shifterEmail, content) #shifterEmail imported from config
        endPrint()
        break
screen.getch()
curses.endwin()
os.system("stty sane")
