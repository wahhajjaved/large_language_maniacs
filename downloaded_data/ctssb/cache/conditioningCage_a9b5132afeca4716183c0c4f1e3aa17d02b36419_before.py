# Controls for the raspberry pi camera
import datetime as dt
import subprocess as sp
import raspividInterface as rpvI
import raspistillInterface as rpsI
import sys, os, socket, pprint
from twisted.internet.task import LoopingCall
from twisted.internet import defer


# Helper functions
def formatLogString(*words):
    logStr = "{} " * len(words)
    logStr = logStr.format(*words)
    return logStr[:(len(logStr) - 1)]

def generateDateString():
    return dt.datetime.now().isoformat(' ')[:19]

def generateTimestamp():
    now = dt.datetime.now()
    return "{:04}{:02}{:02}_{:02}{:02}".format(
        now.year, now.month, now.day, now.hour, now.minute)

def mergeDicts(d1, d2):
    d = d1.copy()
    for key, value in d2.iteritems():
        d[key] = value
    return d

# Logging class - in lieu of a LoggingService
class Logger(object):
    # An object to handle logging
    # Used to write to log files
      
    def __init__(self):
        self.logFile = None
        self.logDir = None
        self.ensureLogPath()
        self.openNewLogFile()

    def ensureLogPath(self):
        self.logDir = os.path.expanduser("~/logs/")
        if not os.path.exists(self.logDir):
            os.mkdir(self.logDir)

    def openNewLogFile(self):
        if self.logFile:
            if not self.logFile.closed:
                logFile.close()
        filename = "cameraLog_" + generateTimestamp() + '.log'
        self.logFile = open(os.path.join(self.logDir, filename), "w")

    def closeLogFile(self):
        self.logFile.close()
        
    # Function to log events
    def writeToLog(self, line):
        if not self.logFile:
            self.openLogFile()
        self.logFile.write('{} {}\n'.format(generateDateString(), line))
        self.logFile.flush()

# The main event
class Camera(object):

    defaultTLParams = {
            'interval': 10*1000,
            'duration': 5*24*60*60*1000,
            'cageName': socket.gethostname(),
            'width': 854,
            'height': 480,
            'dateTime': generateTimestamp(),
            'jpegQuality': 50
    }

    defaultVideoParams = {
            'cageName': socket.gethostname(),
            'duration': 0,
            'stream': False,
            'streamTo': '10.117.33.13',
            'streamPort': 5001,
            'width': 1280,
            'height': 740,
            'fps': 30,
            'bitrate': 3000000,
            'dateTime': generateTimestamp(),
            'outputPath': None
    }

    def __init__(self, logger=None):
        self.activeTimelapse = None
        self.activeVideo = None
        # Set logger object
        if logger is not None:
            self.logger = logger
        else:
            self.logger = Logger()

    def startVideo(self, params={}, fireToResumeTL=None):
        vidParams = self.overwriteVideoDefaults(params)
        # Stop active videos
        if self.activeVideo is not None:
            # Try to start the new video again, using the same params, once the active video has stopped
            self.activeVideo.firedOnRaspicamRelease.addBoth(self.callback_startVideo, params=vidParams)
            self.stopVideo()
            return
        # Videos supercede timelapses
        if self.activeTimelapse is not None:
            atl = self.activeTimelapse # A race condition is created here.  Reference the active timelapse beforehand to prevent madness
            fireToResumeTL = self.suspendActiveTimelapse() # None if no active timelapse
            # Try to start the video again after the active timelapse has released the raspicam
            atl.firedOnRaspicamRelease.addBoth(self.callback_startVideo, params=vidParams, susTl=fireToResumeTL)
            return
        # Log the video command
        self.logger.writeToLog(formatLogString('startVid', 'timestamp', vidParams['dateTime']))
        # Handle video creation
        self._initiateVideo(vidParams, susTl=fireToResumeTL)

    def stopVideo(self):
        if self.activeVideo is not None:
            self._terminateActiveVideo()
        self.logger.writeToLog('stopVid')

    def suspendActiveTimelapse(self):
        if self.activeTimelapse is not None:
            tl, self.activeTimelapse = self.activeTimelapse, None
            tl.stop()
            d = defer.Deferred()
            d.addCallback(self.callback_resumeTimelapse, tl)
            return d
        else:
            return None

    def startTimelapse(self, params={}):
        tlParams = self.overwriteTimelapseDefaults(params)
        # If a video is playing, start timelapse when the video ends
        if self.activeVideo is not None:
            self.activeVideo.firedOnRaspicamRelease.addBoth(self.callback_startTimelapse, tlParams)
            return
        # If a timelapse is active, stop it
        if self.activeTimelapse is not None:
            self._terminateActiveTimelapse()
        # Log the timelapse start
        self.logger.writeToLog(formatLogString('startTL','intervalLen',tlParams['interval'],'timestamp',tlParams['dateTime']))
        self._initiateTimelapse(tlParams)

    def stopTimelapse(self):
        self._terminateActiveTimelapse()
        self.logger.writeToLog('stopTL')

    def overwriteVideoDefaults(self, params):
        return mergeDicts(self.defaultVideoParams, params)

    def overwriteTimelapseDefaults(self, params):
        return mergeDicts(self.defaultTLParams, params)

    def _initiateTimelapse(self, params):
        tl = Timelapse(params)
        tl.start()
        tl.firedOnRaspicamRelease.addBoth(self._derefActiveTimelapse)
        self.activeTimelapse = tl

    def _terminateActiveTimelapse(self):
        if self.activeTimelapse is not None:
            tl, self.activeTimelapse = self.activeTimelapse, None
            tl.stop()

    def _initiateVideo(self, params, susTl=None):
        if params['stream']:
            v = Stream(params)
        else:
            v = Video(params)
        v.start()
        # Set active Video to None when raspivid is reaped
        v.firedOnRaspicamRelease.addCallback(self)
        if susTl is not None:
            v.firedOnRaspicamRelease.chainDeferred(susTl)
        self.activeVideo = v

    def _terminateActiveVideo(self, *args):
        self.activeVideo.stop()
        # Not all videos are stopped in this fashion, so dereferencing should
        #  be handled elsewhere

    def _derefActiveVideo(self, *args):
        print 'Dereferencing active video...'
        if self.activeVideo is not None:
            self.activeVideo = None

    def _derefActiveTimelapse(self, *args):
        print 'Dereferencing active timelapse...'
        if self.activeTimelapse is not None:
            self.activeTimelapse = None

    def callback_startVideo(self, result, params={}, susTl=None):
        self.startVideo(params, susTl)

    def callback_startTimelapse(self, result, params={}):
        self.startTimelapse(params)

    def callback_resumeTimelapse(self, result, tl):
        tl.start()
        tl.firedOnRaspicamRelease.addBoth(self._derefActiveTimelapse)
        self.activeTimelapse = tl


class CameraState(dict):
    firedOnRaspicamRelease = None

    def secondsRemaining(self):
        d = dt.timedelta(milliseconds=self['duration'])
        e = self['startTime'] + d
        r = e - dt.datetime.now()
        return r.total_seconds()

class Video(CameraState):
    rpvProtocol = None

    def start(self, *args):
        self.rpvProtocol = rpvI.RaspiVidProtocol(vidParams=self)
        d = self.rpvProtocol.startRecording()
        self.firedOnRaspicamRelease = d

    def stop(self, *args):
        self.rpvProtocol.stopRecording()


class Stream(Video):
    # Same factory for each Stream
    streamingFactory = rpvI.VideoStreamingFactory()

    def start(self, *args):
        d = self.streamingFactory.initiateStreaming(self.copy()) #eww.. the streamingFactory references this arg.  Shouldn't pass self.
        self.firedOnRaspicamRelease = d

    def stop(self, *args):
        self.streamingFactory.stopStreaming()

class Timelapse(CameraState):
    rpsProtocol = None
    
    def start(self, *args):
        if self.rpsProtocol is None:
            self.rpsProtocol = rpsI.RaspiStillTimelapseProtocol(tlParams=self)
        d = self.rpsProtocol.startTimelapse()
        self.firedOnRaspicamRelease = d

    def stop(self, *args):
        self.rpsProtocol.stopTimelapse()