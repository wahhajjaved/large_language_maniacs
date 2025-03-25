from twisted.internet import protocol, error, defer
import datetime as dt
import os, socket

def generateTimestamp():
    now = dt.datetime.now()
    return "{:04}{:02}{:02}_{:02}{:02}".format(
        now.year, now.month, now.day, now.hour, now.minute)

def mergeDicts(d1, d2):
    d = d1.copy()
    for key, value in d2.iteritems():
        d[key] = value
    return d    

defaults = {
    'interval': 10*1000,
    'duration': 5*24*60*60*1000,
    'cageName': socket.gethostname(),
    'width': 854,
    'height': 480,
    'dateTime': generateTimestamp(),
    'jpegQuality': 50
}

start_of_image = soi = '\xff\xd8\xff\xe1'

class RaspiStillTimelapseProtocol(protocol.ProcessProtocol):
    _currImageNumber = 0
    _currImageFile = None

    def __init__(self, tlParams={}):
        tlParams = mergeDicts(defaults, tlParams)
        # Set the arguments to call raspistill with
        self._setTlArgs(tlParams)
        self.tlParams = tlParams
        # Empty list for deffereds fired on raspistill reaping
        self.fireWhenProcessEnds = []

    def outReceived(self, data):
        # Decide where to write the data
        self._handleData(data)

    def errReceived(self, data):
        print '[err] raspistill:'
        print data

    def processEnded(self, status):
        # Fire off deferreds and close the last image file
        self.fireFireWhenProcessEndsDeferreds()
        self._closeCurrImageFile()

    def fireFireWhenProcessEndsDeferreds(self):
        # Fire all deferreds in fireWhenProcessEnds
        while self.fireWhenProcessEnds:
            d = self.fireWhenProcessEnds.pop()
            try:
                d.callback(None)
            # This will eventually be called when
            #  the parent factory's currProcessDeferred 
            #  is cancelled
            except defer.AlreadyCalledError:
                pass

    def deferUntilProcessEnds(self):
        d = defer.Deferred()
        self.fireWhenProcessEnds.append(d)
        return d

    def startTimelapse(self):
        from twisted.internet import reactor
        reactor.spawnProcess(self, '/usr/bin/raspistill', args=self.tlArgs, env=os.environ)
        return self.deferUntilProcessEnds()

    # Call with maybeDeferred
    def stopTimelapse(self):
        try:
            self.transport.signalProcess('KILL')
        except error.ProcessExitedAlready:
            return
        return self.deferUntilProcessEnds()

    def _setTlArgs(self, params):
        tlArgString = 'raspistill --timelapse {interval} -t {duration} -w {width} -h {height} -q {jpegQuality} -o -'.format(**params)
        self.tlArgs = tlArgString.split()

    def _handleData(self, data):
        # Check incoming data for a jpeg start of file
        containsSOI, ind = self._detectSOI(data)
        if containsSOI:
            # Write data before soi to the current file,
            #  and data after soi to the next file
            self._writeToCurrImageFile(data[:ind])
            self._writeToNextImageFile(data[ind:])
        else:
            self._writeToCurrImageFile(data)

    def _detectSOI(self, data):
        ind = data.find(soi)
        return ind >= 0 , ind
        
    def _openNextImageFile(self):
        if self._currImageFile is not None:
            self._closeCurrImageFile
        f = open(self._generateNextImageFileName(), 'w')
        self._currImageFile = f

    def _writeToNextImageFile(self, data):
        f = self._openNextImageFile()
        self._writeToCurrImageFile(data)

    def _writeToCurrImageFile(self, data):
        if self._currImageFile is not None:
            self._currImageFile.write(data)

    def _closeCurrImageFile(self):
        f, self._currImageFile = self._currImageFile, None
        f.close()

    def _generateNextImageFileName(self):
        filename = "~/timelapse/{cageName}_{dateTime}_%05d.jpg" % self._getNextImageNumber()
        filename = filename.format(**self.tlParams)
        print 'writing to %s' % filename
        return os.path.expanduser(filename)

    def _getNextImageNumber(self):
        self._currImageNumber += 1
        return self._currImageNumber


def main():
    from twisted.internet import reactor
    tlProc = RaspiStillTimelapseProtocol(p)
    reactor.callWhenRunning(tlProc.startTimelapse)
    reactor.callWhenRunning(reactor.callLater, 25, tlProc.stopTimelapse)
    reactor.run()

if __name__ == '__main__':
    main()
