__author__ = "dbr/Ben"
__version = "0.1"

class _Ddict(dict):
    """Lazy-dict, automatically creates multidimensional dicts
    by having __getitem__ create sub-dict automatically"""
    def __init__(self, default=None):
        self.default = default
    #end __init__

    def __getitem__(self, key):
        if not self.has_key(key):
            self[key] = self.__class__(self.default) # Create sub-instance
        return dict.__getitem__(self, key)
    #end __getitem__
#end _Ddict

class Cache:
    import os
    import tempfile
    import urllib
    try:
        import sha1 as hasher
    except ImportError:
        import md5 as hasher
    
    def __init__(self,prefix="tvdb_api"):
        self.prefix = prefix
        tmp = self.tempfile.gettempdir()
        tmppath = self.os.path.join(tmp, prefix)
        if not self.os.path.isdir(tmppath):
            self.os.mkdir(tmppath)
        self.tmp = tmppath
    #end __init__
    
    def getCachePath(self,url):
        cache_name = self.hasher.new(url).hexdigest()
        cache_path = self.os.path.join(self.tmp, cache_name)
        return cache_path
    #end getUrl
    
    def checkCache(self,url):
        path = self.getCachePath(url)
        if self.os.path.isfile(path):
            return path
        else:
            return False
    #end checkCache

    def loadUrl(self,url):
        cacheExists = self.checkCache(url)
        if cacheExists:
            f=open(cacheExists)
            dat = f.read()
            f.close()
            return dat
        else:
            path = self.getCachePath(url)
            dat = self.urllib.urlopen(url).read()
            f=open(path,"w+")
            f.write(dat)
            f.close()
            return dat
        #end if cacheExists
    #end getUrl
#end Cache

# Custom exceptions
class tvdb_error(Exception):pass
class tvdb_shownotfound(Exception):pass
class tvdb_userabort(Exception):pass

class tvdb:
    """
    Create easy-to-use interface to name of season/episode name
    >>> i = tvdb()
    >>> i['showname']['1']['24']['name']
    'Last Episode'
    """
    from BeautifulSoup import BeautifulStoneSoup
    
    def __init__(self,interactive=False,debug=False):
        self.config={}
        self.config['apikey'] = "0629B785CE550C8D"
        # The following url_ configs are based of the http://www.thetvdb.com API documentation
        self.config['url_mirror'] = "http://www.thetvdb.com/api/%s/mirrors.xml" % (self.config['apikey'])
        self.config['url_getSeries'] = "http://www.thetvdb.com/api/GetSeries.php?seriesname=%s"
        self.config['url_epInfo'] = "http://www.thetvdb.com/api/%s/series/%%s/all/" % (self.config['apikey'])
        
        self.config['interactive'] = interactive # prompt for correct series if needed
        
        self.config['debug_enabled'] = debug # show debugging messages
        self.config['debug_tofile'] = False
        self.config['debug_filename'] = "tvdb.log"
        self.config['debug_path'] = '.'
        
        self.cache = Cache("tvdb_api") # Caches retreived URLs in tmp dir
        self.log = self.initLogger() # Setups the logger (self.log.debug() etc)
        self.shows = {} # Holds all show data in shows[show_id] = dict of ep data
        self.corrections = {} # Holds show-name to show_id mapping
        
        # Config setup. Grab TVDB mirrors
        self.mirrors = self._getMirrors() # TODO: Apply random mirror urls (Minor: Currently 1 mirror)
    #end __init__
    
    def initLogger(self):
        import os,logging,sys
        logdir = os.path.expanduser( self.config['debug_path'] )
        logpath = os.path.join(logdir,self.config['debug_filename'])
        
        logger = logging.getLogger("tvdb")
        formatter = logging.Formatter('%(asctime)s) %(levelname)s %(message)s')
        
        if self.config['debug_tofile']:
            hdlr = logging.FileHandler(logpath)
        else:
            hdlr = logging.StreamHandler(sys.stdout)
        #end if debug_tofile
        
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr)
        
        if self.config['debug_enabled']:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        return logger
    #end initLogger
    
    def _getsoupsrc(self,url):
        self.log.debug('Retriving URL %s' % (url.replace(" ","+")))
        
        url=url.replace(" ","+")
        try:
            src=self.cache.loadUrl(url)
        except IOError,errormsg:
            raise tvdb_error("Could not connect to server: %s\n" % (errormsg))
        #end try
        soup=self.BeautifulStoneSoup(src)
        return soup
    #end _getsoupsrc
    
    def _getMirrors(self):
        mirrorSoup=self._getsoupsrc( self.config['url_mirror'] )
        mirrors=[]
        for mirror in mirrorSoup.findAll('mirror'):
            self.log.debug('Found mirror %s' % (mirror))
            
            mirrors.append(
                mirror.find('mirrorpath').contents[0]
            )
        #end for mirror
        self.log.debug('Found total of %s mirrors' % (len(mirrors)))
        return mirrors
    #end _getMirrors

    def _cleanName(self,name):
        name = name.replace("&amp;","and")
        return name
    #end _cleanName
    
    def _getSeries(self,series):
        seriesSoup = self._getsoupsrc( self.config['url_getSeries'] % (series) )
        allSeries=[]
        for series in seriesSoup.findAll('series'):
            cur_name = series.find('seriesname').contents[0]
            cur_name = self._cleanName(cur_name)
            cur_sid = series.find('id').contents[0]
            self.log.debug('Found series %s (id: %s)' % (cur_name,cur_sid))
            allSeries.append( {'sid':cur_sid, 'name':cur_name} )
        #end for series
        
        if len(allSeries) == 0:
            self.log.debug('Series result returned zero')
            raise tvdb_shownotfound("Show-name search returned zero results")
        
        if self.config['interactive']:
            self.log.debug('Interactivily selecting show')
            for i in range(len(allSeries[:6])):
                i_show = i + 1 # Start at more human readable number 1 (not zero)
                self.log.debug( 'Showing allSeries[%s] = %s)' % (i_show,allSeries[i]) )
                print "%s -> %s (tvdb id: %s)" % (i_show,allSeries[i]['name'].encode("UTF-8","ignore"),allSeries[i]['sid'].encode("UTF-8","ignore"))
            print "Enter choice (first number):"
            ans=raw_input()
            self.log.debug( 'Got choice of: %s' % (ans))
            try:
                selected_id = int(ans) - 1 # The human entered 1 as first result, not zero
                self.log.debug( 'Trying to return ID: %d' % (selected_id))
                return allSeries[ selected_id ]
            except ValueError: # Input was not number
                if ans == "q":
                    self.log.debug('Got quit command (q)')
                    raise tvdb_userabort("User aborted")
                else:
                    self.log.debug('Unknown keypress %s' % (ans))
                    raise tvdb_userabort("Invalid keypress") # TODO: Better UI
            #end for k,v
        else:
            self.log.debug('Auto-selecting first search result')
            return allSeries[0]
    #end _getSeries

    def _getEps(self,sid):
        self.log.debug('Getting all episodes of %s' % (sid))
        epsSoup=self._getsoupsrc( self.config['url_epInfo']% (sid) )
        for ep in epsSoup.findAll('episode'):
            ep_no = int( ep.find('episodenumber').contents[0] )
            seas_no = int( ep.find('seasonnumber').contents[0] )
            ep_name = str( ep.find('episodename').contents[0] )
            
            self.shows[sid][seas_no][ep_no] = {'name':ep_name}
        #end for ep
    #end _geEps
    
    def _nameToSid(self,name):
        """
        Takes show name, returns the correct series ID (if the show has
        already been grabbed), or grabs all episodes and returns 
        the correct SID.
        """
        if self.corrections.has_key(name):
            self.log.debug('Correcting %s to %s' % (name,self.corrections[name]) )
            sid = self.corrections[name]
        else:
            self.log.debug('Getting show %s' % (name))
            selected_series = self._getSeries( name )
            sname, sid = selected_series['name'], selected_series['sid']
            self.log.debug( "Got %s, sid %s" % (sname,sid) )
            self.shows[sid] = _Ddict(dict)
            self.shows[sid]['showname'] = sname
            self.corrections[name] = sid
            self._getEps( sid )
        #end if self.corrections.has_key
        return sid
    #end _nameToSid

    def __getitem__(self,key):
        """
        Handles tvdb_instance['showname'] calls.
        The dict index should be the show name
        """
        key=key.lower() # make key lower case
        sid = self._nameToSid(key)
        self.log.debug('Got series id %s' % (sid))
        return dict.__getitem__(self.shows, sid)
    #end __getitem__
    
    def __setitem__(self,key,value):
        self.log.debug('Setting %s = %s' % (key,value))
        self.shows[key] = value
    #end __getitem__
    def __str__(self):
        return str(self.shows) #TODO: Improve this
    #end __str__
#end tvdb

if __name__ == '__main__':
    x=tvdb(interactive=True,debug=True)
    print x['lost'][1][4]
    print x['Lost'][1][4]
