# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import shutil
import sys
import re

from sickbeard import notifiers
from sickbeard import exceptions
from sickbeard import helpers
from sickbeard import notifiers
from sickbeard import sqlite3
from sickbeard import db
from sickbeard import history
from sickbeard import classes

from sickbeard import logger
from sickbeard.common import *

from sickbeard.notifiers import xbmc

from lib.tvdb_api import tvnamer, tvdb_api, tvdb_exceptions

from lib.tvnamer.utils import FileParser
from lib.tvnamer import tvnamer_exceptions
#from tvdb_api.nfogen import createXBMCInfo

sample_ratio = 0.3

def renameFile(curFile, newName):

    filePath = os.path.split(curFile)
    oldFile = os.path.splitext(filePath[1])

    newFilename = os.path.join(filePath[0], helpers.sanitizeFileName(newName) + oldFile[1])
    
    logger.log("Renaming from " + curFile + " to " + newFilename)

    try:
        os.rename(curFile, newFilename.encode('utf-8'))
    except (OSError, IOError), e:
        logger.log("Failed renaming " + curFile + " to " + os.path.basename(newFilename) + ": " + str(e), logger.ERROR)
        return False

    return newFilename


# #########################
# Find the file we're dealing with
# #########################
def findMainFile (show_dir):
    # init vars
    biggest_file = None
    biggest_file_size = 0
    next_biggest_file_size = 0

    # find the biggest file in the folder
    for file in filter(helpers.isMediaFile, os.listdir(show_dir)):
        cur_size = os.path.getsize(os.path.join(show_dir, file))
        if cur_size > biggest_file_size:
            biggest_file = file
            next_biggest_file_size = biggest_file_size
            biggest_file_size = cur_size

    if biggest_file == None:
        return biggest_file

    # it should be by far the biggest file in the folder. If it isn't, we have a problem (multi-show nzb or something, not going to deal with it)
    if float(next_biggest_file_size) / float(biggest_file_size) > sample_ratio:
        logger.log("Multiple files in the folder are comparably large, giving up", logger.ERROR)
        return None

    return os.path.join(show_dir, biggest_file)


def _checkForExistingFile(newFile, oldFile):

    # if the new file exists, return the appropriate code depending on the size
    if os.path.isfile(newFile):
        
        # see if it's bigger than our old file
        if os.path.getsize(newFile) > os.path.getsize(oldFile):
            return 1
        
        else:
            return -1
    
    else:
        return 0
            

def logHelper (logMessage, logLevel=logger.MESSAGE):
    logger.log(logMessage, logLevel)
    return logMessage + "\n"


def doIt(downloaderDir, nzbName=None):
    
    returnStr = ""

    downloadDir = ''

    # if they passed us a real dir then assume it's the one we want
    if os.path.isdir(downloaderDir):
        downloadDir = os.path.abspath(downloaderDir)
    
    # if they've got a download dir configured then use it
    elif sickbeard.TV_DOWNLOAD_DIR != '' and os.path.isdir(sickbeard.TV_DOWNLOAD_DIR):
        downloadDir = os.path.join(sickbeard.TV_DOWNLOAD_DIR, os.path.abspath(downloaderDir).split(os.path.sep)[-1])

        returnStr += logHelper("Trying to use folder "+downloadDir, logger.DEBUG)

    # if we didn't find a real dir then quit
    if not os.path.isdir(downloadDir):
        returnStr += logHelper("Unable to figure out what folder to process. If your downloader and Sick Beard aren't on the same PC make sure you fill out your TV download dir in the config.", logger.DEBUG)
        return returnStr

    myDB = db.DBConnection()
    sqlResults = myDB.select("SELECT * FROM tv_shows")
    for sqlShow in sqlResults:
        if downloadDir.startswith(os.path.abspath(sqlShow["location"])+os.sep):
            returnStr += logHelper("You're trying to post process a show that's already been moved to its show dir", logger.ERROR)
            return returnStr

    returnStr += logHelper("Final folder name is " + downloadDir, logger.DEBUG)
    
    # TODO: check if it's failed and deal with it if it is
    if downloadDir.startswith('_FAILED_'):
        returnStr += logHelper("The directory name indicates it failed to extract, cancelling", logger.DEBUG)
        return returnStr
    
    # find the file we're dealing with
    biggest_file = findMainFile(downloadDir)
    if biggest_file == None:
        returnStr += logHelper("Unable to find the biggest file - is this really a TV download?", logger.DEBUG)
        return returnStr
        
    returnStr += logHelper("The biggest file in the dir is: " + biggest_file, logger.DEBUG)
    
    # use file name, folder name, and NZB name (in that order) to try to figure out the episode info
    result = None
    nameList = [downloadDir.split(os.path.sep)[-1], biggest_file]
    if nzbName != None:
        nameList.append(nzbName)
    
    finalNameList = []
    for curName in nameList:
        finalNameList += helpers.sceneToNormalShowNames(curName)

    showResults = None
    
    for curName in set(finalNameList):
    
        try:
            myParser = FileParser(curName)
            result = myParser.parse()
        except tvnamer_exceptions.InvalidFilename:
            returnStr += logHelper("Unable to parse the filename "+curName+" into a valid episode", logger.DEBUG)
            continue

        try:
            t = tvdb_api.Tvdb(custom_ui=classes.ShowListUI,
                              **sickbeard.TVDB_API_PARMS)
            showObj = t[result.seriesname]
            showInfo = (int(showObj["id"]), showObj["seriesname"])
        except (tvdb_exceptions.tvdb_exception, IOError), e:

            returnStr += logHelper("TVDB didn't respond, trying to look up the show in the DB instead: "+str(e), logger.DEBUG)

            showInfo = helpers.searchDBForShow(result.seriesname)
            
        # if we didn't get anything from TVDB or the DB then try the next option
        if showInfo == None:
            continue

        # find the show in the showlist
        try:
            showResults = helpers.findCertainShow(sickbeard.showList, showInfo[0])
        except exceptions.MultipleShowObjectsException:
            raise #TODO: later I'll just log this, for now I want to know about it ASAP
        
        if showResults != None:
            returnStr += logHelper("Found the show in our list, continuing", logger.DEBUG)
            break
    
    # end for
        
    if result == None:
        returnStr += logHelper("Unable to figure out what this episode is, giving up", logger.DEBUG)
        return returnStr

    if showResults == None:
        returnStr += logHelper("The episode doesn't match a show in my list - bad naming?", logger.DEBUG)
        return returnStr

    if not os.path.isdir(showResults._location):
        returnStr += logHelper("The show dir doesn't exist, canceling postprocessing", logger.DEBUG)
        return returnStr

    
    # get or create the episode (should be created probably, but not for sure)
    season = int(result.seasonnumber)

    rootEp = None
    for curEpisode in result.episodenumbers:
        episode = int(curEpisode)
    
        returnStr += logHelper("TVDB thinks the file is " + showInfo[1] + str(season) + "x" + str(episode), logger.DEBUG)
        
        # now that we've figured out which episode this file is just load it manually
        try:        
            curEp = showResults.getEpisode(season, episode)
        except exceptions.EpisodeNotFoundException, e:
            returnStr += logHelper("Unable to create episode: "+str(e), logger.DEBUG)
            return returnStr
        
        if rootEp == None:
            rootEp = curEp
            rootEp.relatedEps = []
        else:
            rootEp.relatedEps.append(curEp)

    # log it to history
    history.logDownload(rootEp, biggest_file)

    # wait for the copy to finish

    notifiers.notify(NOTIFY_DOWNLOAD, rootEp.prettyName(True))


    # figure out the new filename
    biggestFileName = os.path.basename(biggest_file)
    biggestFileExt = os.path.splitext(biggestFileName)[1]

    # if we're supposed to put it in a season folder then figure out what folder to use
    seasonFolder = ''
    if rootEp.show.seasonfolders == True:
        
        # search the show dir for season folders
        for curDir in os.listdir(rootEp.show.location):

            if not os.path.isdir(os.path.join(rootEp.show.location, curDir)):
                continue
            
            # if it's a season folder, check if it's the one we want
            match = re.match("[Ss]eason\s*(\d+)", curDir)
            if match != None:
                # if it's the correct season folder then stop looking
                if int(match.group(1)) == int(rootEp.season):
                    seasonFolder = curDir
                    break 

        # if we couldn't find the right one then just assume "Season X" format is what we want
        if seasonFolder == '':
            seasonFolder = 'Season ' + str(rootEp.season)

    returnStr += logHelper("Seasonfolders were " + str(rootEp.show.seasonfolders) + " which gave " + seasonFolder, logger.DEBUG)

    destDir = os.path.join(rootEp.show.location, seasonFolder)
    
    newFile = os.path.join(destDir, helpers.sanitizeFileName(rootEp.prettyName())+biggestFileExt)
    returnStr += logHelper("The ultimate destination for " + biggest_file + " is " + newFile, logger.DEBUG)

    existingResult = _checkForExistingFile(newFile, biggest_file)
    
    # if there's no file with that exact filename then check for a different episode file (in case we're going to delete it)
    if existingResult == 0:
        existingResult = _checkForExistingFile(rootEp.location, biggest_file)
        if existingResult == -1:
            existingResult = -2
        if existingResult == 1:
            existingResult = 2
    
    # see if the existing file is bigger - if it is, bail (unless it's a proper in which case we're forcing an overwrite)
    if existingResult > 0:
        if rootEp.status == SNATCHED_PROPER:
            returnStr += logHelper("There is already a file that's bigger at "+newFile+" but I'm going to overwrite it with a PROPER", logger.DEBUG)
        else:
            returnStr += logHelper("There is already a file that's bigger at "+newFile+" - not processing this episode.", logger.DEBUG)
            return returnStr
        
    # if the dir doesn't exist (new season folder) then make it
    if not os.path.isdir(destDir):
        returnStr += logHelper("Season folder didn't exist, creating it", logger.DEBUG)
        os.mkdir(destDir)

    returnStr += logHelper("Moving from " + biggest_file + " to " + destDir, logger.DEBUG)
    try:
        # try using rename to move it because shutil.move is bugged in python 2.5
        try:
            os.rename(biggest_file, os.path.join(destDir, os.path.basename(biggest_file)))
        except OSError:
            shutil.move(biggest_file, destDir)
       
        returnStr += logHelper("File was moved successfully", logger.DEBUG)
        
    except IOError, e:
        returnStr += logHelper("Unable to move the file: " + str(e), logger.ERROR)
        return returnStr

    # if the file existed and was smaller then lets delete it
    # OR if the file existed, was bigger, but we want to replace it anyway cause it's a PROPER snatch
    if existingResult < 0 or (existingResult > 0 and rootEp.status == SNATCHED_PROPER):
        # if we're deleting a file with a different name then just go ahead
        if existingResult in (-2, 2):
            existingFile = rootEp.location
            if rootEp.status == SNATCHED_PROPER:
                returnStr += logHelper(existingFile + " already exists and is larger but I'm deleting it to make way for the proper", logger.DEBUG)
            else:
                returnStr += logHelper(existingFile + " already exists but it's smaller than the new file so I'm replacing it", logger.DEBUG)
            os.remove(existingFile)
            #TODO: delete old metadata
            
            

    curFile = os.path.join(destDir, biggestFileName)

    if sickbeard.RENAME_EPISODES:
        try:
            os.rename(curFile, newFile)
            returnStr += logHelper("Renaming the file " + curFile + " to " + newFile, logger.DEBUG)
        except (OSError, IOError), e:
            returnStr += logHelper("Failed renaming " + curFile + " to " + newFile + ": " + str(e), logger.ERROR)
            return returnStr

    else:
        returnStr += logHelper("Renaming is disabled, leaving file as "+curFile, logger.DEBUG)
        newFile = curFile

    for curEp in [rootEp] + rootEp.relatedEps:
        with curEp.lock:
            curEp.location = newFile
            
            # don't mess up the status - if this is a legit download it should be SNATCHED
            if curEp.status != PREDOWNLOADED:
                curEp.status = DOWNLOADED
            curEp.saveToDB()

    
    # generate nfo/tbn
    rootEp.createMetaFiles()
    rootEp.saveToDB()

    # we don't want to put predownloads in the library until we can deal with removing them
    if sickbeard.XBMC_UPDATE_LIBRARY == True and rootEp.status != PREDOWNLOADED:
        notifiers.xbmc.updateLibrary(rootEp.show.location)

    # delete the old folder unless the config wants us not to
    if not sickbeard.KEEP_PROCESSED_DIR:
        returnStr += logHelper("Deleting folder " + downloadDir, logger.DEBUG)
        
        try:
            shutil.rmtree(downloadDir)
        except (OSError, IOError), e:
            returnStr += logHelper("Warning: unable to remove the folder " + downloadDir + ": " + str(e), logger.ERROR)

    return returnStr

if __name__ == "__main__":
    doIt(sys.argv[1])
