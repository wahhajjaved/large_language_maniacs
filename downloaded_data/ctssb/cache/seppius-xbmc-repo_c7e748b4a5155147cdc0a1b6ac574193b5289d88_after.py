#!/usr/bin/python
# -*- coding: utf-8 -*-
#/*
# *      Copyright (C) 2011 Silen
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# */
import re, os, urllib, urllib2, cookielib, time, json

import xbmc, xbmcgui, xbmcplugin, xbmcaddon
from datetime import datetime, date, time

from threading import Event, Thread


Addon = xbmcaddon.Addon(id='plugin.video.weewza.com')
icon = xbmc.translatePath(os.path.join(Addon.getAddonInfo('path'),'icon.png'))

# load XML library
try:
    sys.path.append(os.path.join(Addon.getAddonInfo('path'), r'resources', r'lib'))
    from BeautifulSoup  import BeautifulSoup
except:
    try:
        sys.path.insert(0, os.path.join(Addon.getAddonInfo('path'), r'resources', r'lib'))
        from BeautifulSoup  import BeautifulSoup
    except:
        sys.path.append(os.path.join(os.getcwd(), r'resources', r'lib'))
        from BeautifulSoup  import BeautifulSoup
        icon = xbmc.translatePath(os.path.join(os.getcwd().replace(';', ''),'icon.png'))

import HTMLParser
hpar = HTMLParser.HTMLParser()

h = int(sys.argv[1])

def showMessage(heading, message, times = 3000):
    xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")'%(heading, message, times, icon))

# -- repeater ------------------------------------------------------------------
class RepeatTimer(Thread):
    def __init__(self, interval, function, iterations=0, args=[], kwargs={}):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.iterations = iterations
        self.args = args
        self.kwargs = kwargs
        self.finished = Event()

    def run(self):
        count = 0
        while not self.finished.is_set() and (self.iterations <= 0 or count < self.iterations):
            self.finished.wait(self.interval)
            if not self.finished.is_set():
                self.function(*self.args, **self.kwargs)
                count += 1

    def cancel(self):
        self.finished.set()

# -- weewza video player -------------------------------------------------------
class Weewza_Player( xbmc.Player ):

    def __init__( self, *args, **kwargs ):
        xbmc.Player.__init__( self )

        # -- initialize parameters
        self.ID         = None                                  # channel ID
        self.Pos        = None                                  # current timedelta
        self.PlayList   = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)    # internal playlist
        self.MinLen     = 3                                     # min number of unplayed items in play list
        self.isSet      = False

    def play(self, ID, Pos):
        # -- initialize parameters
        self.ID         = ID                            # channel ID
        self.Pos        = Pos                           # current timedelta

        self.PlayList.clear()

        # -- fill up playlist
        for i in range(1, self.MinLen+2):
            self.Add_To_Playlist()

        xbmc.log(str(self.PlayList.__len__()))

        # -- start play
        xbmc.Player().play(self.PlayList)
        self.isSet = True

        # -- inialize update playlist by timer
        self.timer  = RepeatTimer( 60, self.Add_To_Playlist )
        self.timer.run()

    def onPlayBackPaused(self):
        xbmc.log( '*** CALLBACK: PAUSE')

    def Add_To_Playlist(self):
        xbmc.log('** call Add_To_Playlist '+str(self.Pos))
        # -- check if playlist could be expanded
        try:
            pl_pos = self.PlayList.getposition()
        except:
            pl_pos = 0

        if self.PlayList.__len__() - pl_pos > self.MinLen:
            return

        # -- get weewvza video url
        url = 'http://weewza.com/json.php?action=getFile&channelId='+self.ID+'&getPos='+str(self.Pos)
        xbmc.log(url)
        post = None
        request = urllib2.Request(url, post)

        request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)')
        request.add_header('Host',	'weewza.com')
        request.add_header('Accept', '*/*')
        request.add_header('Accept-Language', 'ru-RU')
        request.add_header('Referer',	'http://weewza.com')

        try:
            f = urllib2.urlopen(request)
        except IOError, e:
            if hasattr(e, 'reason'):
                xbmc.log('We failed to reach a server. Reason: '+ e.reason)
            elif hasattr(e, 'code'):
                xbmc.log('The server couldn\'t fulfill the request. Error code: '+ e.code)

        epg = json.load(f)

        xbmc.log(str(epg))

        try:
            video = epg["fileUrl"]
        except:
            return

        xbmc.log(video)

        # -- add new video link to playlist
        self.PlayList.add(video)    # add video link
        self.Pos= self.Pos + 5*60   # set pointer to next 5 min interval
        xbmc.log(str(self.Pos))

#---------- get list of TV channels --------------------------------------------
def Get_TV_Channels():
    url = 'http://weewza.com/view.php?channelId=96'
    post = None
    request = urllib2.Request(url, post)

    request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)')
    request.add_header('Host',	'weewza.com')
    request.add_header('Accept', '*/*')
    request.add_header('Accept-Language', 'ru-RU')
    request.add_header('Referer',	'http://weewza.com')

    try:
        f = urllib2.urlopen(request)
    except IOError, e:
        if hasattr(e, 'reason'):
            xbmc.log('We failed to reach a server. Reason: '+ e.reason)
        elif hasattr(e, 'code'):
            xbmc.log('The server couldn\'t fulfill the request. Error code: '+ e.code)

    html = f.read()

    # -- parsing web page ------------------------------------------------------

    soup = BeautifulSoup(html, fromEncoding="windows-1251")

    weewza_nav = soup.find("div", {"id":"wn"}).findAll("a")
    for nav in weewza_nav:
        name = unescape(nav.find('img')["alt"]).encode('utf-8')
        id   = nav["href"][nav["href"].find('channelId=')+10:1000]
        img  = nav.find('img')["src"]
        i = xbmcgui.ListItem(name, iconImage=img, thumbnailImage=img)
        u = sys.argv[0] + '?mode=EPG'
        u += '&name=%s'%urllib.quote_plus(name)
        u += '&id=%s'%urllib.quote_plus(id)
        u += '&img=%s'%urllib.quote_plus(img)
        xbmcplugin.addDirectoryItem(h, u, i, True)

    #xbmcplugin.addSortMethod(h, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(h)
#-------------------------------------------------------------------------------

#---------- get EPG for selected channel ---------------------------------------
def Get_EPG(params):
    # -- parameters
    id  = urllib.unquote_plus(params['id'])
    img = urllib.unquote_plus(params['img'])

    url = 'http://weewza.com/json.php?action=getFullEPG&channelId='+id

    post = None
    request = urllib2.Request(url, post)

    request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)')
    request.add_header('Host',	'weewza.com')
    request.add_header('Accept', '*/*')
    request.add_header('Accept-Language', 'ru-RU')
    request.add_header('Referer',	'http://weewza.com')

    try:
        f = urllib2.urlopen(request)
    except IOError, e:
        if hasattr(e, 'reason'):
            xbmc.log('We failed to reach a server. Reason: '+ e.reason)
        elif hasattr(e, 'code'):
            xbmc.log('The server couldn\'t fulfill the request. Error code: '+ e.code)

    epg = json.load(f)

    for js in epg["FullEPG"]:
        name  = unescape(js["start"][0:16]+"   "+js["name"]).encode('utf-8')
        type  = unescape(js["type"]).encode('utf-8')
        if type == 'future':
            name = '[COLOR FFFF0000]'+name+'[/COLOR]'
        start = unescape(js["start"])
        i = xbmcgui.ListItem(name, iconImage=img, thumbnailImage=img)
        u = sys.argv[0] + '?mode=PLAY'
        u += '&name=%s'%urllib.quote_plus(name)
        u += '&id=%s'%urllib.quote_plus(id)
        u += '&start=%s'%urllib.quote_plus(start)
        u += '&type=%s'%urllib.quote_plus(type)
        xbmcplugin.addDirectoryItem(h, u, i, False)

    xbmcplugin.endOfDirectory(h)
#-------------------------------------------------------------------------------


#-------------------------------------------------------------------------------

def PLAY(params):
    # -- parameters
    start      = urllib.unquote_plus(params['start'])
    id         = urllib.unquote_plus(params['id'])

    xbmc.log('*** start PLAY: '+id+'  '+start)

    # -- check if video available

    url = 'http://weewza.com/json.php?action=getFullEPG&channelId='+id

    post = None
    request = urllib2.Request(url, post)

    request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)')
    request.add_header('Host',	'weewza.com')
    request.add_header('Accept', '*/*')
    request.add_header('Accept-Language', 'ru-RU')
    request.add_header('Referer',	'http://weewza.com')

    try:
        f = urllib2.urlopen(request)
    except IOError, e:
        if hasattr(e, 'reason'):
            xbmc.log('We failed to reach a server. Reason: '+ e.reason)
        elif hasattr(e, 'code'):
            xbmc.log('The server couldn\'t fulfill the request. Error code: '+ e.code)

    epg = json.load(f)

    for js in epg["FullEPG"]:
        if unescape(js["start"]) == start:
            if unescape(js["type"]).encode('utf-8') == 'future':
                xbmc.log(unescape(js["start"][0:16]+"   "+js["name"]).encode('utf-8'))
                return False

    # -- calculate timedelta
    getPos = get_Weewza_getPos(start)

    # -- play video
    Weewza.play(id, getPos)

#-------------------------------------------------------------------------------

def get_Weewza_getPos(str):
    #2011-10-26 22:30:00
    yr = int(str[0:4])
    mn = int(str[5:7])
    dn = int(str[8:10])
    hh = int(str[11:13])
    mi = int(str[14:16])

    d1 = datetime(yr, mn, dn, hh, mi, 0)
    d2 = datetime(1970, 1, 1)

    d = d1-d2

    return d.days*86400+d.seconds-4*60*60

def unescape(text):
    try:
        text = hpar.unescape(text)
    except:
        text = hpar.unescape(text.decode('utf8'))

    try:
        text = unicode(text, 'utf-8')
    except:
        text = text

    return text

def get_url(url):
    return "http:"+urllib.quote(url.replace('http:', ''))

#-------------------------------------------------------------------------------
def get_params(paramstring):
	param=[]
	if len(paramstring)>=2:
		params=paramstring
		cleanedparams=params.replace('?','')
		if (params[len(params)-1]=='/'):
			params=params[0:len(params)-2]
		pairsofparams=cleanedparams.split('&')
		param={}
		for i in range(len(pairsofparams)):
			splitparams={}
			splitparams=pairsofparams[i].split('=')
			if (len(splitparams))==2:
				param[splitparams[0]]=splitparams[1]
	return param
#-------------------------------------------------------------------------------
params=get_params(sys.argv[2])

Weewza = Weewza_Player() # initialize player

mode = None

try:
	mode = urllib.unquote_plus(params['mode'])
except:
	Get_TV_Channels()

if mode == 'EPG':
	Get_EPG(params)
elif mode == 'PLAY':
	PLAY(params)

try:
    if Weewza.isSet:
        Weewza.timer.cancel()
except:
    mode = None
