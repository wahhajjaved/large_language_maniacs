#! /usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import configparser
import json
import warnings

def parseArguments():
    parser = argparse.ArgumentParser(description='''automatically call frequencyShiftingAnalyzer and totalSpectrumAnalyer. ''', epilog="""Main program.""")
    parser.add_argument("source", help="Source Name", type=str)
    parser.add_argument("-c", "--config", help="Configuration cfg file", type=str, default="config/config.cfg")
    parser.add_argument("-m", "--manual", help="Set manual log data", action='store_true')
    parser.add_argument("-n", "--noGUI", help="Create smoothed and not smothed outputfiles", action='store_true')
    parser.add_argument("-v","--version", action="version", version='%(prog)s - Version 3.0')
    args = parser.parse_args()

    return args

def findLogFile(logList, iteration):
    tmpL = -1
    for l in range(0, len(logList)):
        if logList[l].split("/")[-1].split(".")[0].split("_")[-1] == iteration:
            tmpL = l
            break
    if tmpL == -1:
        warnings.WarningMessage("Warning " + "log for iteration " + iteration + " do not exist log file " + logList[-1] + " will be used instead !")
        
    return tmpL
    
def main():
    # Parse the arguments
    args = parseArguments()
    sourceName = str(args.__dict__["source"])
    configFilePath = str(args.__dict__["config"])
    
    # Creating config parametrs
    config = configparser.RawConfigParser()
    config.read(configFilePath)
    dataFilesPath = config.get('paths', "dataFilePath")
    resultPath = config.get('paths', "resultFilePath")
    logPath = config.get('paths', "logPath")
    
    path = dataFilesPath + sourceName + "/"
    iterations = list()
    
    # Creating iteration list
    for iteration in os.listdir(path):
        iterations.append(iteration)
            
    iterations.sort(key=int, reverse=False)
    
    print ("iterations", iterations)
     
    logfile_list = list()
    
    # Creating log file list 
    for log in os.listdir(logPath):
        if log.startswith(sourceName):
            logfile_list.append(log)
            
    resultFileName = sourceName + ".json"
    
    # Create result file if not exits   
    if os.path.isfile(resultPath + resultFileName):
        pass
    else:
        os.system("touch " + resultPath +  resultFileName)
            
        resultFile = open (resultPath +  resultFileName, "w")
        resultFile.write("{ \n" + "\n}")
        resultFile.close()
    
    # Open result file   
    with open(resultPath + resultFileName) as result_data:    
        result = json.load(result_data)
    
    processed_iteration = list()
    
    # Create processed observation list
    for experiment in result:
        if experiment.split("_")[-1]  in iterations and experiment.split("_")[-1] not in processed_iteration:
            processed_iteration.append(experiment.split("_")[-1])
            
    
    processed_iteration.sort(key=int, reverse=False)        
    print ("processed_iteration", processed_iteration)
    
    #try:
    if args.manual:
        for i in iterations:
            if i not in processed_iteration:
                frequencyShiftingParametr = sourceName + " " + i + " " + str(logfile_list[findLogFile(logfile_list, i)])
                print ("\033[1;32;39mExecute ",  "python3  " + "code/frequencyShiftingAnalyzer_qt5.py " + frequencyShiftingParametr + " -m\033[0;29;39m")
                os.system("python3  " + "code/frequencyShiftingAnalyzer_qt5.py " + frequencyShiftingParametr  + " -m") 
    else:
        for i in iterations:
            if i not in processed_iteration:
                print(findLogFile(logfile_list, i))
                frequencyShiftingParametr = sourceName + " " + i + " " + str(logfile_list[findLogFile(logfile_list, i)])
                print ("\033[1;31;47mExecute ",  "python3  " + "code/frequencyShiftingAnalyzer_qt5.py " + frequencyShiftingParametr +  " \033[0;29;39m")
                os.system("python3  " + "code/frequencyShiftingAnalyzer_qt5.py " + frequencyShiftingParametr)
        
    # Creating data file list
    data_files = list()
    for data in os.listdir(dataFilesPath):
        if data.startswith(sourceName) and data.endswith(".dat"):
            data_files.append(data)
                
    for d in data_files:
        if d.split(".")[0].split("_")[-1] not in processed_iteration:
            if args.noGUI:
                print ("\033[1;31;47mExecute ",  "python3  " + "code/totalSpectrumAnalyer_qt5.py " + d  +  " -n \033[0;29;39m") 
                os.system("python3  " + "code/totalSpectrumAnalyer_qt5.py " + d + " -n")
            else:
                print ("\033[1;31;47mExecute ",  "python3  " + "code/totalSpectrumAnalyer_qt5.py " + d  +  " \033[0;29;39m") 
                os.system("python3  " + "code/totalSpectrumAnalyer_qt5.py " + d)
    
    '''            
    except IOError as e:
        print ("IO Error",  e)
        sys.exit(1)
        
    except IndexError as e:
        print ("Index Error",  e)
        sys.exit(1)
        
    except ValueError as e:
            print ("Cannot crate modified Julian Days", e)
            
    except TypeError as e:
        print ("TypeError",  e)
        #sys.exit(1)
        
    except:
        print("Unexpected error:", sys.exc_info()[0])
        sys.exit(1)
    '''
                    
if __name__=="__main__":
    main()
    sys.exit(0)
    
    