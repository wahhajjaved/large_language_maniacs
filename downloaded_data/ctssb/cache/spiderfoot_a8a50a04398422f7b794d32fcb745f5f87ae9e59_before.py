#-------------------------------------------------------------------------------
# Name:         sflib
# Purpose:      Common functions used by SpiderFoot modules.
#               Also defines the SpiderFootPlugin abstract class for modules.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     26/03/2012
# Copyright:   (c) Steve Micallef 2012
# Licence:     GPL
#-------------------------------------------------------------------------------

import inspect
import hashlib
import gzip
import re
import os
import random
import socket
import sys
import time
import urllib2
import StringIO

class SpiderFoot:
    dbh = None
    scanGUID = None

    # 'options' is a dictionary of options which changes the behaviour
    # of how certain things are done in this module
    # 'handle' will be supplied if the module is being used within the
    # SpiderFoot GUI, in which case all feedback should be fed back
    def __init__(self, options, handle=None):
        self.handle = handle
        self.opts = options

    # Bit of a hack to support SOCKS because of the loading order of
    # modules. sfscan will call this to update the socket reference
    # to the SOCKS one.
    def updateSocket(self, sock):
        socket = sock
        urllib2.socket = sock

    # Supplied an option value, return the data based on what the
    # value is. If val is a URL, you'll get back the fetched content,
    # if val is a file path it will be loaded and get back the contents,
    # and if a string it will simply be returned back.
    def optValueToData(self, val, fatal=True, splitLines=True):
        if val.startswith('@'):
            fname = val.split('@')[1]
            try:
                self.info("Loading configuration data from: " + fname)
                f = open(fname, "r")
                if splitLines:
                    arr = f.readlines()
                    ret = list()
                    for x in arr:
                        ret.append(x.rstrip('\n'))
                else:
                    ret = f.read()
                return ret
            except BaseException as b:
                if fatal:
                    self.error("Unable to open option file, " + fname + ".")
                else:
                    return None

        if val.lower().startswith('http://') or val.lower().startswith('https://'):
            try:
                self.info("Downloading configuration data from: " + val)
                res = urllib2.urlopen(val)
                data = res.read()
                if splitLines:
                    return data.splitlines()
                else:
                    return data
            except BaseException as e:
                if fatal:
                    self.error("Unable to open option URL, " + val + ".")
                else:
                    return None

        return val

    # Called usually some time after instantiation
    # to set up a database handle and scan GUID, used
    # for logging events to the database about a scan.
    def setDbh(self, handle):
        self.dbh = handle

    def setScanId(self, id):
        self.scanGUID = id

    def _dblog(self, level, message, component=None):
        return self.dbh.scanLogEvent(self.scanGUID, level, message, component)

    def error(self, error, exception=True):
        if self.dbh == None:
            print '[Error] ' + error
        else:
            self._dblog("ERROR", error)
        if exception:
            raise BaseException("Internal Error Encountered: " + error)

    def fatal(self, error):
        if self.dbh == None:
            print '[Fatal] ' + error
        else:
            self._dblog("FATAL", error)
        exit(-1)

    def status(self, message):
        if self.dbh == None:
            print "[Status] " + message
        else:
            self._dblog("STATUS", message)

    def info(self, message):
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])

        if mod == None:
            modName = "Unknown"
        else:
            modName = mod.__name__

        if self.dbh == None:
            print '[' + modName + '] ' + message
        else:
            self._dblog("INFO", message, modName)
        return

    def debug(self, message):
        if self.opts['_debug'] == False:
            return
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])

        if mod == None:
            modName = "Unknown"
        else:
            modName = mod.__name__

        if self.dbh == None:
            print '[' + modName + '] ' + message
        else:
            self._dblog("DEBUG", message, modName)
        return

    def myPath(self):
        # This will get us the program's directory, even if we are frozen using py2exe.

        # Determine whether we've been compiled by py2exe
        if hasattr(sys, "frozen"):
            return os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))

        return os.path.dirname(unicode(__file__, sys.getfilesystemencoding()))

    #
    # Caching
    #

    # Return the cache path
    def cachePath(self):
        path = self.myPath() + '/cache'
        if not os.path.isdir(path):
            os.mkdir(path)
        return path

    # Store data to the cache
    def cachePut(self, label, data):
        pathLabel = hashlib.sha224(label).hexdigest()
        cacheFile = self.cachePath() + "/" + pathLabel
        fp = file(cacheFile, "w")
        if type(data) is list:
            for line in data:
                fp.write(line + '\n')
        else:
            data = data.encode('utf-8')
            fp.write(data)
        fp.close()

    # Retreive data from the cache
    def cacheGet(self, label, timeoutHrs):
        pathLabel = hashlib.sha224(label).hexdigest()
        cacheFile = self.cachePath() + "/" + pathLabel
        try:
            (m, i, d, n, u, g, sz, atime, mtime, ctime) = os.stat(cacheFile)

            if sz == 0:
                return None

            if mtime > time.time() - timeoutHrs*3600 or timeoutHrs == 0:
                fp = file(cacheFile, "r")
                fileContents = fp.read()
                fp.close()
                fileContents = fileContents.decode('utf-8')
                return fileContents
            else:
                return None
        except BaseException as e:
            return None

    #
    # Configuration process
    #

    # Convert a Python dictionary to something storable
    # in the database.
    def configSerialize(self, opts, filterSystem=True):
        storeopts = dict()

        for opt in opts.keys():
            # Filter out system temporary variables like GUID and others
            if opt.startswith('__') and filterSystem:
                continue

            if type(opts[opt]) is int or type(opts[opt]) is str:
                storeopts[opt] = opts[opt]

            if type(opts[opt]) is bool:
                if opts[opt]:
                    storeopts[opt] = 1
                else:
                    storeopts[opt] = 0
            if type(opts[opt]) is list:
                storeopts[opt] = ','.join(opts[opt])

        if not opts.has_key('__modules__'):
            return storeopts

        for mod in opts['__modules__']:
            for opt in opts['__modules__'][mod]['opts']:
                if opt.startswith('_') and filterSystem:
                    continue

                if type(opts['__modules__'][mod]['opts'][opt]) is int or \
                    type(opts['__modules__'][mod]['opts'][opt]) is str:
                    storeopts[mod + ":" + opt] = opts['__modules__'][mod]['opts'][opt]

                if type(opts['__modules__'][mod]['opts'][opt]) is bool:
                    if opts['__modules__'][mod]['opts'][opt]:
                        storeopts[mod + ":" + opt] = 1
                    else:
                        storeopts[mod + ":" + opt] = 0
                if type(opts['__modules__'][mod]['opts'][opt]) is list:
                    storeopts[mod + ":" + opt] = ','.join(str(x) \
                        for x in opts['__modules__'][mod]['opts'][opt])

        return storeopts
    
    # Take strings, etc. from the database or UI and convert them
    # to a dictionary for Python to process.
    # referencePoint is needed to know the actual types the options
    # are supposed to be.
    def configUnserialize(self, opts, referencePoint, filterSystem=True):
        returnOpts = referencePoint

        # Global options
        for opt in referencePoint.keys():
            if opt.startswith('__') and filterSystem:
                # Leave out system variables
                continue
            if opts.has_key(opt):
                if type(referencePoint[opt]) is bool:
                    if opts[opt] == "1":
                        returnOpts[opt] = True
                    else:
                        returnOpts[opt] = False

                if type(referencePoint[opt]) is str:
                    returnOpts[opt] = str(opts[opt])

                if type(referencePoint[opt]) is int:
                    returnOpts[opt] = int(opts[opt])

                if type(referencePoint[opt]) is list:
                    if type(referencePoint[opt][0]) is int:
                        returnOpts[opt] = list()
                        for x in str(opts[opt]).split(","):
                             returnOpts[opt].append(int(x))
                    else:
                        returnOpts[opt] = str(opts[opt]).split(",")

        if not referencePoint.has_key('__modules__'):
            return returnOpts

        # Module options
        # A lot of mess to handle typing..
        for modName in referencePoint['__modules__']:
            for opt in referencePoint['__modules__'][modName]['opts']:
                if opt.startswith('_') and filterSystem:
                    continue
                if opts.has_key(modName + ":" + opt):
                    if type(referencePoint['__modules__'][modName]['opts'][opt]) is bool:
                        if opts[modName + ":" + opt] == "1":
                            returnOpts['__modules__'][modName]['opts'][opt] = True
                        else:
                            returnOpts['__modules__'][modName]['opts'][opt] = False

                    if type(referencePoint['__modules__'][modName]['opts'][opt]) is str:
                        returnOpts['__modules__'][modName]['opts'][opt] = \
                            str(opts[modName + ":" + opt])

                    if type(referencePoint['__modules__'][modName]['opts'][opt]) is int:
                        returnOpts['__modules__'][modName]['opts'][opt] = \
                            int(opts[modName + ":" + opt])

                    if type(referencePoint['__modules__'][modName]['opts'][opt]) is list:
                        if type(referencePoint['__modules__'][modName]['opts'][opt][0]) is int:
                            returnOpts['__modules__'][modName]['opts'][opt] = list()
                            for x in str(opts[modName + ":" + opt]).split(","):
                                returnOpts['__modules__'][modName]['opts'][opt].append(int(x))
                        else:
                            returnOpts['__modules__'][modName]['opts'][opt] = \
                                str(opts[modName + ":" + opt]).split(",")

        return returnOpts

    # Return an array of module names for returning the
    # types specified.
    def modulesProducing(self, events):
        modlist = list()
        for mod in self.opts['__modules__'].keys():
            if self.opts['__modules__'][mod]['provides'] == None:
                continue

            for evtype in self.opts['__modules__'][mod]['provides']:
                if evtype in events and mod not in modlist:
                    modlist.append(mod)

        return modlist

    # Return an array of modules that consume the types
    # specified.
    def modulesConsuming(self, events):
        modlist = list()
        for mod in self.opts['__modules__'].keys():
            if self.opts['__modules__'][mod]['consumes'] == None:
                continue

            for evtype in self.opts['__modules__'][mod]['consumes']:
                if evtype in events and mod not in modlist:
                    modlist.append(mod)

        return modlist

    # Return an array of types that are produced by the list
    # of modules supplied.
    def eventsFromModules(self, modules):
        evtlist = list()
        for mod in modules:
            if mod in self.opts['__modules__'].keys():
                if self.opts['__modules__'][mod]['provides'] != None:
                    for evt in self.opts['__modules__'][mod]['provides']:
                        evtlist.append(evt)

        return evtlist

    # Return an array of types that are consumed by the list
    # of modules supplied.
    def eventsToModules(self, modules):
        evtlist = list()
        for mod in modules:
            if mod in self.opts['__modules__'].keys():
                if self.opts['__modules__'][mod]['consumes'] != None:
                    for evt in self.opts['__modules__'][mod]['consumes']:
                        evtlist.append(evt)

        return evtlist

    #
    # URL parsing functions
    #

    # Turn a relative path into an absolute path
    def urlRelativeToAbsolute(self, url):
        finalBits = list()

        if '..' not in url:
            return url

        bits = url.split('/')

        for chunk in bits:
            if chunk == '..':
                # Don't pop the last item off if we're at the top
                if len(finalBits) <= 1:
                    continue

                # Don't pop the last item off if the first bits are not the path
                if '://' in url and len(finalBits) <= 3:
                    continue

                finalBits.pop()
                continue

            finalBits.append(chunk)

        #self.debug('xfrmed rel to abs path: ' + url + ' to ' + '/'.join(finalBits))
        return '/'.join(finalBits)

    # Extract the top level directory from a URL
    def urlBaseDir(self, url):

        bits = url.split('/')

        # For cases like 'www.somesite.com'
        if len(bits) == 0:
            #self.debug('base dir of ' + url + ' not identified, using URL as base.')
            return url + '/'

        # For cases like 'http://www.blah.com'
        if '://' in url and url.count('/') < 3:
            #self.debug('base dir of ' + url + ' is: ' + url + '/')
            return url + '/'

        base = '/'.join(bits[:-1])
        #self.debug('base dir of ' + url + ' is: ' + base + '/')
        return base + '/'

    # Extract the scheme and domain from a URL
    # Does not return the trailing slash! So you can do .endswith()
    # checks.
    def urlBaseUrl(self, url):
        if '://' in url:
            bits = re.match('(\w+://.[^/:]*)[:/].*', url)
        else:
            bits = re.match('(.[^/:]*)[:/]', url)

        if bits == None:
            return url.lower()

        #self.debug('base url of ' + url + ' is: ' + bits.group(1))
        return bits.group(1).lower()

    # Extract the FQDN from a URL
    def urlFQDN(self, url):
        baseurl = self.urlBaseUrl(url)
        if '://' not in baseurl:
            count = 0
        else:
            count = 2

        # http://abc.com will split to ['http:', '', 'abc.com']
        return baseurl.split('/')[count].lower()

    # Extract the keyword (the domain without the TLD or any subdomains)
    # from a domain.
    def domainKeyword(self, domain, tldList):
        # Strip off the TLD
        tld = '.'.join(self.hostDomain(domain.lower(), tldList).split('.')[1:])
        ret = domain.lower().replace('.'+tld, '')

        # If the user supplied a domain with a sub-domain, return the second part
        if '.' in ret:
            return ret.split('.')[-1]
        else:
            return ret
        
    # Obtain the domain name for a supplied hostname
    # tldList needs to be an array based on the Mozilla public list
    def hostDomain(self, hostname, tldList):
        ps = PublicSuffixList(tldList)
        return ps.get_public_suffix(hostname)

    # Simple way to verify IPs.
    def validIP(self, address):
        parts = address.split(".")
        if parts == None:
            return False

        if len(parts) != 4:
            return False
        for item in parts:
            if not item.isdigit():
                return False
            if not 0 <= int(item) <= 255:
                return False
        return True

    # Converts a dictionary of k -> array to a nested
    # tree that can be digested by d3 for visualizations.
    def dataParentChildToTree(self, data):
        def get_children(needle, haystack):
            #print "called"
            ret = list()

            if needle not in haystack.keys():
                return None

            if haystack[needle] == None:
                return None

            for c in haystack[needle]:
                #print "found child of " + needle + ": " + c
                ret.append({ "name": c, "children": get_children(c, haystack) })
            return ret

        # Find the element with no parents, that's our root.
        root = None
        for k in data.keys():
            if data[k] == None:
                continue

            contender = True
            for ck in data.keys():
                if data[ck] == None:
                    continue

                if k in data[ck]:
                    contender = False

            if contender:
                root = k
                break

        if root == None:
            #print "*BUG*: Invalid structure - needs to go back to one root."
            final = { }
        else:
            final = { "name": root, "children": get_children(root, data) }

        return final

    #
    # General helper functions to automate many common tasks between modules
    #

    # Parse the contents of robots.txt, returns a list of patterns
    # which should not be followed
    def parseRobotsTxt(self, robotsTxtData):
        returnArr = list()

        # We don't check the User-Agent rule yet.. probably should at some stage

        for line in robotsTxtData.splitlines():
            if line.lower().startswith('disallow:'):
                m = re.match('disallow:\s*(.[^ #]*)', line, re.IGNORECASE)
                self.debug('robots.txt parsing found disallow: ' + m.group(1))
                returnArr.append(m.group(1))
                continue

        return returnArr

    # Find all URLs within the supplied content. This does not fetch any URLs!
    # A dictionary will be returned, where each link will have the keys
    # 'source': The URL where the link was obtained from
    # 'original': What the link looked like in the content it was obtained from
    # The key will be the *absolute* URL of the link obtained, so for example if
    # the link '/abc' was obtained from 'http://xyz.com', the key in the dict will
    # be 'http://xyz.com/abc' with the 'original' attribute set to '/abc'
    def parseLinks(self, url, data, domain):
        returnLinks = dict()

        if data == None or len(data) == 0:
            self.debug('parseLinks() called with no data to parse')
            return None

        # Find actual links
        try:
            regRel = re.compile('(href|src|action|url)[:=][ \'\"]*(.[^\'\"<> ]*)',
                re.IGNORECASE)
            urlsRel = regRel.findall(data)
        except Exception as e:
            self.error("Error applying regex to: " + data)
            return None

        # Find potential links that aren't links (text possibly in comments, etc.)
        try:
            # Because we're working with a big blob of text now, don't worry
            # about clobbering proper links by url decoding them.
            data = urllib2.unquote(data)
            regRel = re.compile('(.)([a-zA-Z0-9\-\.]+\.'+domain+')', 
                re.IGNORECASE)
            urlsRel = urlsRel + regRel.findall(data)
        except Exception as e:
            self.error("Error applying regex2 to: " + data)
        try:
            # Some links are sitting inside a tag, e.g. Google's use of <cite>
            regRel = re.compile('(>)('+domain+'/.[^<]+)', re.IGNORECASE)
            urlsRel = urlsRel + regRel.findall(data)
        except Exception as e:
            self.error("Error applying regex3 to: " + data)

        # Loop through all the URLs/links found by the regex
        for linkTuple in urlsRel:
            # Remember the regex will return two vars (two groups captured)
            meta = linkTuple[0]
            link = linkTuple[1]
            absLink = None

            # Don't include stuff likely part of some dynamically built incomplete
            # URL found in Javascript code (character is part of some logic)
            if link[len(link)-1] == '.' or link[0] == '+' or \
                'javascript:' in link.lower() or '();' in link:
                self.debug('unlikely link: ' + link)
                continue

            # Filter in-page links
            if re.match('.*#.[^/]+', link):
                self.debug('in-page link: ' + link)
                continue

            # Ignore mail links
            if 'mailto:' in link.lower():
                self.debug("Ignoring mail link: " + link)
                continue

            # URL decode links
            if '%2f' in link.lower():
                link = urllib2.unquote(link)

            # Capture the absolute link:
            # If the link contains ://, it is already an absolute link
            if '://' in link:
                absLink = link

            # If the link starts with a /, the absolute link is off the base URL
            if link.startswith('/'):
                absLink = self.urlBaseUrl(url) + link

            # Maybe the domain was just mentioned and not a link, so we make it one
            if absLink == None and domain.lower() in link.lower():
                absLink = 'http://' + link

            # Otherwise, it's a flat link within the current directory
            if absLink == None:
                absLink = self.urlBaseDir(url) + link

            # Translate any relative pathing (../)
            absLink = self.urlRelativeToAbsolute(absLink)
            returnLinks[absLink] = {'source': url, 'original': link}

        return returnLinks

    # Fetch a URL, return the response object
    def fetchUrl(self, url, fatal=False, cookies=None, timeout=30, 
        useragent="SpiderFoot", headers=None, dontMangle=False):
        result = {
            'code': None,
            'status': None,
            'content': None,
            'headers': None,
            'realurl': None
        }

        if url == None:
            self.error('Blank URL supplied to be fetched')
            return result

        # Clean the URL
        url = url.encode('ascii', 'ignore')

        try:
            header = dict()
            if type(useragent) is list:
                header['User-Agent'] = random.choice(useragent)
            else:
                header['User-Agent'] = useragent

            # Add custom headers
            if headers != None:
                for k in headers.keys():
                    header[k] = headers[k]

            req = urllib2.Request(url, None, header)
            if cookies != None:
                req.add_header('cookie', cookies)
                self.info("Fetching (incl. cookies): " + url + \
                    " [user-agent: " + header['User-Agent'] + "] [timeout: " + \
                    str(timeout) + "]")
            else:
                self.info("Fetching: " + url + " [user-agent: " + \
                    header['User-Agent'] + "] [timeout: " + str(timeout) + "]")

            result['headers'] = dict()
            opener = urllib2.build_opener(SmartRedirectHandler())
            fullPage = opener.open(req, timeout=timeout)
            content = fullPage.read()

            for k, v in fullPage.info().items():
                result['headers'][k.lower()] = v

            # Content is compressed
            if 'gzip' in result['headers'].get('content-encoding', ''):
                content = gzip.GzipFile(fileobj=StringIO.StringIO(content)).read()

            if dontMangle:
                result['content'] = content
            else:
                result['content'] = unicode(content, 'utf-8', errors='replace')

            #print "FOR: " + url
            #print "HEADERS: " + str(result['headers'])
            result['realurl'] = fullPage.geturl()
            result['code'] = fullPage.getcode()
            result['status'] = 'OK'
        except urllib2.HTTPError as h:
            self.info("HTTP code " + str(h.code) + " encountered for " + url)
            # Capture the HTTP error code
            result['code'] = h.code
            for k, v in h.info().items():
                result['headers'][k.lower()] = v
            if fatal:
                self.fatal('URL could not be fetched (' + h.code + ')')
        except urllib2.URLError as e:
            self.info("Error fetching " + url + "(" + str(e) + ")")
            result['status'] = str(e)
            if fatal:
                self.fatal('URL could not be fetched (' + str(e) + ')')
        except Exception as x:
            self.info("Unexpected exception occurred fetching: " + url + " (" + str(x) + ")")
            result['content'] = None
            result['status'] = str(x)
            if fatal:
                self.fatal('URL could not be fetched (' + str(x) + ')')

        return result

    # Check if wildcard DNS is enabled by looking up two random hostnames
    def checkDnsWildcard(self, target):
        randpool = 'bcdfghjklmnpqrstvwxyz3456789'
        randhost1 = ''.join([random.choice(randpool) for x in range(6)])
        randhost2 = ''.join([random.choice(randpool) for x in range(10)])

        # An exception will be raised if either of the resolutions fail
        try:
            addrs = socket.gethostbyname_ex(randhost1 + "." + target)
            addrs = socket.gethostbyname_ex(randhost2 + "." + target)
            self.debug(target + " has wildcard DNS.")
            return True
        except BaseException as e:
            self.debug(target + " does not have wildcard DNS.")
            return False

    # Scrape Google for content, starting at startUrl and iterating through
    # results based on options supplied. Will return a dictionary of all pages
    # fetched and their contents {page => content}.
    # Options accepted:
    # limit: number of search result pages before returning, default is 10
    # nopause: don't randomly pause between fetches
    # useragent: User-Agent string to use
    # timeout: Fetch timeout
    # cx: Custom Search Engine ID
    def googleIterate(self, searchString, opts=dict(), cx=None):
        limit = 10
        fetches = 0
        returnResults = dict()

        if opts.has_key('limit'):
            limit = opts['limit']

        # We attempt to make the URL look as authentically human as possible
        seedUrl = "http://www.google.com/search?q={0}".format(searchString) + \
            "&ie=utf-8&oe=utf-8&aq=t&rls=org.mozilla:en-US:official&client=firefox-a"

        if cx != None:
            seedUrl = seedUrl + "cx=" + cx

        firstPage = self.fetchUrl(seedUrl, timeout=opts['timeout'],
            useragent=opts['useragent'])
        if firstPage['code'] == 403 or firstPage['code'] == 503:
            self.error("Google doesn't like us right now..", False)
            return None

        if firstPage['content'] == None:
            self.error("Failed to fetch content from Google.", False)
            return None

        if "name=\"captcha\"" in firstPage['content']:
            self.error("Google returned a CAPTCHA.", False)
            return None

        returnResults[seedUrl] = firstPage['content']
        matches = re.findall("(\/search\S+start=\d+.[^\'\"]*sa=N)", 
            firstPage['content'])

        while matches > 0 and fetches < limit:
            nextUrl = None
            fetches += 1
            for match in matches:
                # Google moves in increments of 10
                if "start=" + str(fetches*10) in match:
                    nextUrl = match.replace("&amp;", "&")

            if nextUrl == None:
                self.debug("Nothing left to scan for in Google results.")
                return returnResults
            self.info("Next Google URL: " + nextUrl)

            # Wait for a random number of seconds between fetches
            if not opts.has_key('nopause'):
                pauseSecs = random.randint(4, 15)
                self.info("Pausing for " + str(pauseSecs))
                time.sleep(pauseSecs)

            nextPage = self.fetchUrl('http://www.google.com' + nextUrl,
                timeout=opts['timeout'], useragent=opts['useragent'])
            if nextPage['code'] == 403 or nextPage['code'] == 503:
                self.error("Google doesn't like us right now..", False)
                return returnResults

            if nextPage['content'] == None:
                self.error("Failed to fetch subsequent content from Google.", False)
                return returnResults

            if "name=\"captcha\"" in nextPage['content']:
                self.error("Google returned a CAPTCHA.", False)
                return None

            returnResults[nextUrl] = nextPage['content']
            matches = re.findall("(\/search\S+start=\d+.[^\'\"]*)", 
                nextPage['content'], re.IGNORECASE)

        return returnResults

    # Scrape Bing for content, starting at startUrl and iterating through
    # results based on options supplied. Will return a dictionary of all pages
    # fetched and their contents {page => content}.
    # Options accepted:
    # limit: number of search result pages before returning, default is 10
    # nopause: don't randomly pause between fetches
    # useragent: User-Agent string to use
    # timeout: Fetch timeout
    def bingIterate(self, searchString, opts=dict()):
        limit = 10
        fetches = 0
        returnResults = dict()

        if opts.has_key('limit'):
            limit = opts['limit']

        # We attempt to make the URL look as authentically human as possible
        seedUrl = "http://www.bing.com/search?q={0}".format(searchString) + \
            "&pc=MOZI"
        firstPage = self.fetchUrl(seedUrl, timeout=opts['timeout'],
            useragent=opts['useragent'])
        if firstPage['code'] == 400:
            self.error("Bing doesn't like us right now..", False)
            return None

        if firstPage['content'] == None:
            self.error("Failed to fetch content from Bing.", False)
            return None

        if "/challengepic?" in firstPage['content']:
            self.error("Bing returned a CAPTCHA.", False)
            return None

        returnResults[seedUrl] = firstPage['content']

        matches = re.findall("(\/search\S+first=\d+.[^\'\"]*FORM=\S+)", 
            firstPage['content'])
        while matches > 0 and fetches < limit:
            nextUrl = None
            fetches += 1
            for match in matches:
                # Bing moves in increments of 10
                if "first=" + str((fetches*10)+1) in match:
                    nextUrl = match.replace("&amp;", "&").replace("%3a", ":")

            if nextUrl == None:
                self.debug("Nothing left to scan for in Bing results.")
                return returnResults
            self.info("Next Bing URL: " + nextUrl)

            # Wait for a random number of seconds between fetches
            if not opts.has_key('nopause'):
                pauseSecs = random.randint(4, 15)
                self.info("Pausing for " + str(pauseSecs))
                time.sleep(pauseSecs)

            nextPage = self.fetchUrl('http://www.bing.com' + nextUrl,
                timeout=opts['timeout'], useragent=opts['useragent'])
            if nextPage['code'] == 400:
                self.error("Bing doesn't like us any more..", False)
                return returnResults

            if nextPage['content'] == None:
                self.error("Failed to fetch subsequent content from Bing.", False)
                return returnResults

            if "/challengepic?" in firstPage['content']:
                self.error("Bing returned a CAPTCHA.", False)
                return None

            returnResults[nextUrl] = nextPage['content']
            matches = re.findall("(\/search\S+first=\d+.[^\'\"]*)", 
                nextPage['content'], re.IGNORECASE)

        return returnResults

    # Scrape Yahoo for content, starting at startUrl and iterating through
    # results based on options supplied. Will return a dictionary of all pages
    # fetched and their contents {page => content}.
    # Options accepted:
    # limit: number of search result pages before returning, default is 10
    # nopause: don't randomly pause between fetches
    # useragent: User-Agent string to use
    # timeout: Fetch timeout
    def yahooIterate(self, searchString, opts=dict()):
        limit = 10
        fetches = 0
        returnResults = dict()

        if opts.has_key('limit'):
            limit = opts['limit']

        # We attempt to make the URL look as authentically human as possible
        seedUrl = "https://search.yahoo.com/search?p={0}".format(searchString) + \
            "&toggle=1&cop=mss&ei=UTF-8"
        firstPage = self.fetchUrl(seedUrl, timeout=opts['timeout'],
            useragent=opts['useragent'])
        if firstPage['code'] == 403:
            self.error("Yahoo doesn't like us right now..", False)
            return None

        if firstPage['content'] == None:
            self.error("Failed to fetch content from Yahoo.", False)
            return None

        returnResults[seedUrl] = firstPage['content']

        matches = re.findall("(\/search;\S+b=\d+.[^\'\"]*)", 
            firstPage['content'])
        while matches > 0 and fetches < limit:
            nextUrl = None
            fetches += 1
            for match in matches:
                # Yahoo moves in increments of 10
                if "b=" + str((fetches*10)+1) in match:
                    nextUrl = "https://search.yahoo.com" + match

            if nextUrl == None:
                self.debug("Nothing left to scan for in Yahoo results.")
                return returnResults
            self.info("Next Yahoo URL: " + nextUrl)

            # Wait for a random number of seconds between fetches
            if not opts.has_key('nopause'):
                pauseSecs = random.randint(4, 15)
                self.info("Pausing for " + str(pauseSecs))
                time.sleep(pauseSecs)

            nextPage = self.fetchUrl(nextUrl,
                timeout=opts['timeout'], useragent=opts['useragent'])
            if nextPage['code'] == 403:
                self.error("Yahoo doesn't like us any more..", False)
                return returnResults

            if nextPage['content'] == None:
                self.error("Failed to fetch subsequent content from Yahoo.", False)
                return returnResults

            returnResults[nextUrl] = nextPage['content']
            matches = re.findall("(\/search;\S+b=\d+.[^\'\"]*)",
                nextPage['content'], re.IGNORECASE)

        return returnResults

#
# SpiderFoot plug-in module base class
#
class SpiderFootPlugin(object):
    # Will be set to True by the controller if the user aborts scanning
    _stopScanning = False
    # Modules that will be notified when this module produces events
    _listenerModules = list()
    # Current event being processed
    _currentEvent = None
    # Name of this module, set at startup time
    __name__ = "module_name_not_set!"

    # Not really needed in most cases.
    def __init__(self):
        pass

    # Hack to override module's use of socket, replacing it with
    # one that uses the supplied SOCKS server
    def _updateSocket(self, sock):
        socket = sock
        urllib2.socket = sock

    # Used to clear any listener relationships, etc. This is needed because
    # Python seems to cache local variables even between threads.
    def clearListeners(self):
        self._listenerModules = list()
        self._stopScanning = False

    # Will always be overriden by the implementer.
    def setup(self, sf, url, userOpts=dict()):
        pass

    # Listener modules which will get notified once we have data for them to
    # work with.
    def registerListener(self, listener):
        self._listenerModules.append(listener)

    # Call the handleEvent() method of every other plug-in listening for
    # events from this plug-in. Remember that those plug-ins will be called
    # within the same execution context of this thread, not on their own.
    def notifyListeners(self, sfEvent):
        eventName = sfEvent.eventType
        eventData = sfEvent.data
        storeOnly = False # Under some conditions, only store and don't notify

        if eventData == None or (type(eventData) is unicode and len(eventData) == 0):
            #print "No data to send for " + eventName + " to " + listener.__module__
            return None

        # Look back to ensure the original notification for an element
        # is what's linked to children. For instance, sfp_dns may find
        # xyz.abc.com, and then sfp_ripe obtains some raw data for the
        # same, and then sfp_dns finds xyz.abc.com in there, we should
        # suppress the notification of that to other modules, as the
        # original xyz.abc.com notification from sfp_dns will trigger
        # those modules anyway. This also avoids messy iterations that
        # traverse many many levels.

        # storeOnly is used in this case so that the source to dest
        # relationship is made, but no further events are triggered
        # from dest, as we are already operating on dest's original
        # notification from one of the upstream events.

        prevEvent = sfEvent.sourceEvent
        while prevEvent != None:
            if prevEvent.sourceEvent != None:
                if prevEvent.sourceEvent.eventType == sfEvent.eventType and \
                    prevEvent.sourceEvent.data.lower() == sfEvent.data.lower():
                    #print "Skipping notification of " + sfEvent.eventType + " / " + sfEvent.data
                    storeOnly = True
                    break
            prevEvent = prevEvent.sourceEvent

        self._listenerModules.sort()
        for listener in self._listenerModules:
            #print listener.__module__ + ": " + listener.watchedEvents().__str__()
            if eventName not in listener.watchedEvents() and '*' not in listener.watchedEvents():
                #print listener.__module__ + " not listening for " + eventName
                continue

            if storeOnly and "__stor" not in listener.__module__:
                #print "Storing only for " + sfEvent.eventType + " / " + sfEvent.data
                continue

            #print "Notifying " + eventName + " to " + listener.__module__
            listener._currentEvent = sfEvent

            # Check if we've been asked to stop in the meantime, so that
            # notifications stop triggering module activity.
            if self.checkForStop():
                return None

            listener.handleEvent(sfEvent)

    # Called to stop scanning
    def stopScanning(self):
        self._stopScanning = True

    # For modules to use to check for when they should give back control
    def checkForStop(self):
        return self._stopScanning

    # Return a list of the default configuration options for the module.
    def defaultOpts(self):
        return self.opts

    # What events is this module interested in for input. The format is a list
    # of event types that are applied to event types that this module wants to
    # be notified of, or * if it wants everything.
    # Will usually be overriden by the implementer, unless it is interested
    # in all events (default behavior).
    def watchedEvents(self):
        return [ '*' ]

    # What events this module produces
    # This is to support the end user in selecting modules based on events
    # produced.
    def producedEvents(self):
        return None

    # Handle events to this module
    # Will usually be overriden by the implementer, unless it doesn't handle
    # any events.
    def handleEvent(self, sfEvent):
        return None

    # Kick off the work (for some modules nothing will happen here, but instead
    # the work will start from the handleEvent() method.
    # Will usually be overriden by the implementer.
    def start(self):
        return None

# Class for SpiderFoot Events
class SpiderFootEvent(object):
    generated = None
    eventType = None
    confidence = None
    visibility = None
    risk = None
    module = None
    data = None
    sourceEvent = None
    sourceEventHash = None
    __id = None
    
    def __init__(self, eventType, data, module, sourceEvent=None,
        confidence=100, visibility=100, risk=0):
        self.eventType = eventType
        self.generated = time.time()
        self.confidence = confidence
        self.visibility = visibility
        self.risk = risk
        self.module = module
        self.data = data
        self.sourceEvent = sourceEvent

        # "ROOT" is a special "hash" reserved for elements with no
        # actual parent (e.g. the first page spidered.)
        if sourceEvent != None:
            self.sourceEventHash = sourceEvent.getHash()
        else:
            self.sourceEventHash = "ROOT"

        self.__id = self.eventType + str(self.generated) + self.module + \
            str(random.randint(0, 99999999))

    # Unique hash of this event
    def getHash(self):
        if self.eventType == "INITIAL_TARGET":
            return "ROOT"

        digestStr = self.__id.encode('raw_unicode_escape')
        return hashlib.sha256(digestStr).hexdigest()

    # Update variables as new information becomes available
    def setConfidence(self, confidence):
        self.confidence = confidence

    def setVisibility(self, visibility):
        self.visibility = visibility

    def setRisk(self, risk):
        self.risk = risk

    def setSourceEventHash(self, srcHash):
        self.sourceEventHash = srcHash


# Override the default redirectors to re-use cookies
class SmartRedirectHandler(urllib2.HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):
        if headers.has_key("Set-Cookie"):
            req.add_header('cookie', headers['Set-Cookie'])
        result = urllib2.HTTPRedirectHandler.http_error_301(
            self, req, fp, code, msg, headers)
        return result

    def http_error_302(self, req, fp, code, msg, headers):
        if headers.has_key("Set-Cookie"):
            req.add_header('cookie', headers['Set-Cookie'])
        result = urllib2.HTTPRedirectHandler.http_error_302(
            self, req, fp, code, msg, headers)
        return result


"""
Public Suffix List module for Python.
See LICENSE.tp for applicable license.
"""

class PublicSuffixList(object):
	def __init__(self, input_data):
		"""Reads and parses public suffix list.
		
		input_file is a file object or another iterable that returns
		lines of a public suffix list file. If input_file is None, an
		UTF-8 encoded file named "publicsuffix.txt" in the same
		directory as this Python module is used.
		
		The file format is described at http://publicsuffix.org/list/
		"""

		#if input_file is None:
			#input_path = os.path.join(os.path.dirname(__file__), 'publicsuffix.txt')
			#input_file = codecs.open(input_path, "r", "utf8")

		root = self._build_structure(input_data)
		self.root = self._simplify(root)

	def _find_node(self, parent, parts):
		if not parts:
			return parent

		if len(parent) == 1:
			parent.append({})

		assert len(parent) == 2
		negate, children = parent

		child = parts.pop()

		child_node = children.get(child, None)

		if not child_node:
			children[child] = child_node = [0]

		return self._find_node(child_node, parts)

	def _add_rule(self, root, rule):
		if rule.startswith('!'):
			negate = 1
			rule = rule[1:]
		else:
			negate = 0

		parts = rule.split('.')
		self._find_node(root, parts)[0] = negate

	def _simplify(self, node):
		if len(node) == 1:
			return node[0]

		return (node[0], dict((k, self._simplify(v)) for (k, v) in node[1].items()))

	def _build_structure(self, fp):
		root = [0]

		for line in fp:
			line = line.strip()
			if line.startswith('//') or not line:
				continue

			self._add_rule(root, line.split()[0].lstrip('.'))

		return root

	def _lookup_node(self, matches, depth, parent, parts):
		if parent in (0, 1):
			negate = parent
			children = None
		else:
			negate, children = parent

		matches[-depth] = negate

		if depth < len(parts) and children:
			for name in ('*', parts[-depth]):
				child = children.get(name, None)
				if child is not None:
					self._lookup_node(matches, depth+1, child, parts)

	def get_public_suffix(self, domain):
		"""get_public_suffix("www.example.com") -> "example.com"

		Calling this function with a DNS name will return the
		public suffix for that name.

		Note that for internationalized domains the list at
		http://publicsuffix.org uses decoded names, so it is
		up to the caller to decode any Punycode-encoded names.
		"""

		parts = domain.lower().lstrip('.').split('.')
		hits = [None] * len(parts)

		self._lookup_node(hits, 1, self.root, parts)

		for i, what in enumerate(hits):
			if what is not None and what == 0:
				return '.'.join(parts[i:])
