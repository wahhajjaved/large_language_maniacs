#!/usr/bin/python
import sys, os, urlparse, urllib, xbmc, xbmcplugin, hashlib, time, xbmcgui, ctypes
from contextlib import closing
from kodipopcorntime import settings, media
from kodipopcorntime.exceptions import Notify, Error, HTTPError, ProxyError, TorrentError, Abort
from kodipopcorntime.logging import log, LOGLEVEL, log_error
from kodipopcorntime.platform import Platform
from kodipopcorntime.utils import SafeDialogProgress, Dialog, Cache, notify, NOTIFYLEVEL, ListItem, isoToLang, build_magnetFromMeta, shortenBytes
from kodipopcorntime.torrent import TorrentPlayer

__addon__ = sys.modules['__main__'].__addon__

class PopcornTime:
    def __init__(self, **params):
        self(**params)

    def __call__(self, mediaType=None, endpoint=None, **params):
        self.mediaSettings = None
        if mediaType:
            self.mediaSettings = getattr(settings, mediaType)

        if not endpoint:
            endpoint = 'index'
        log("(Main) Calling %s. Params: %s" %(endpoint, str(params)))
        if not hasattr(self, endpoint):
            raise Error("'PopcornTime' class has no method '%s'" %endpoint)
        getattr(self, endpoint)(**params)

    def addItem(self, mediaType, endpoint, params, isFolder=True, **item):
        log("(Main) Adding item '%s'" %item["label"])
        path = "%s?%s" %(settings.addon.base_url, urllib.urlencode(dict([('mediaType', mediaType), ('endpoint', endpoint)], **params)))

        # Ensure fanart
        if not item.setdefault("properties", {}).get("fanart_image"):
            item["properties"]["fanart_image"] = settings.addon.fanart

        xbmcplugin.addDirectoryItem(settings.addon.handle, path, ListItem.from_dict(**item).as_xbmc_listitem(), isFolder)

    def addItems(self, mediaType, items, endpoint=None, isFolder=True):
        for item in items:
            self.addItem(mediaType, endpoint=endpoint, isFolder=isFolder, **item)

    def finish(self, contentType='files', updateListing=False, cacheToDisc=True):
        log("(Main) Finish", LOGLEVEL.INFO)
        xbmcplugin.setContent(settings.addon.handle, contentType)
        xbmcplugin.endOfDirectory(settings.addon.handle, True, updateListing, cacheToDisc)

    """"""
    def getCurPageNum(self):
        return int(xbmc.getInfoLabel("ListItem.Property(pageNum)") or 1)

    def getSelectedItem(self):
        castAndRole = []
        _c = xbmc.getInfoLabel('ListItem.CastAndRole')
        if _c:
            castAndRole = [cr.split(' as ', 1) for cr in _c.replace('\n', ' / ').split(' / ')]

        return {
            "label": xbmc.getInfoLabel('ListItem.Label'),
            "icon": xbmc.getInfoLabel('ListItem.Icon'),
            "thumbnail": xbmc.getInfoLabel('ListItem.Thumb'),
            "info": {
                "title": xbmc.getInfoLabel('ListItem.Title'),
                "year": int(xbmc.getInfoLabel('ListItem.Year') or 0),
                "originaltitle": xbmc.getInfoLabel('ListItem.OriginalTitle'),
                "genre": xbmc.getInfoLabel('ListItem.Genre'),
                'castandrole': castAndRole,
                'director': xbmc.getInfoLabel('ListItem.Director'),
                "plot": xbmc.getInfoLabel('ListItem.Plot'),
                "plotoutline": xbmc.getInfoLabel('ListItem.PlotOutline'),
                "tagline": xbmc.getInfoLabel('ListItem.Tagline'),
                "writer": xbmc.getInfoLabel('ListItem.Writer'),
                "rating": float(xbmc.getInfoLabel('ListItem.Rating') or 0.0),
                "duration": int(xbmc.getInfoLabel('ListItem.Duration') or 0),
                "code": xbmc.getInfoLabel('ListItem.IMDBNumber'),
                "studio": xbmc.getInfoLabel('ListItem.Studio'),
                "votes": xbmc.getInfoLabel('ListItem.Rating') and float(xbmc.getInfoLabel('ListItem.Votes')) or 0.0
            },
            "properties": {
                "fanart_image": xbmc.getInfoLabel("ListItem.Property(fanart_image)")
            },
            "stream_info": {
                "video": {
                    "codec": xbmc.getInfoLabel('ListItem.VideoCodec'),
                    "duration": int(xbmc.getInfoLabel('ListItem.Duration') or 0)*60,
                    "width": int(xbmc.getInfoLabel('ListItem.VideoResolution')),
                    "height": xbmc.getInfoLabel('ListItem.VideoResolution') == '1920' and 1080 or 720
                },
                "audio": {
                    "codec": xbmc.getInfoLabel('ListItem.AudioCodec'),
                    "language": xbmc.getInfoLabel('ListItem.AudioLanguage'),
                    "channels": int(xbmc.getInfoLabel('ListItem.AudioChannels') or 2)
                },
                'subtitle': {
                    'language': xbmc.getInfoLabel('ListItem.SubtitleLanguage')
                }
            }
        }

    def getSearchString(self):
        log("(Main) Getting search string")
        string = xbmc.getInfoLabel("ListItem.Property(searchString)")
        if not string:
            log("(Main) Showing keyboard")
            keyboard = xbmc.Keyboard('', __addon__.getLocalizedString(30001), False)
            keyboard.doModal()
            if not keyboard.isConfirmed() and not keyboard.getText():
                raise Abort()
            string = keyboard.getText()
        log("(Main) Returning search string '%s'" %string)
        return string

    def getMediaItems(self, call, *args, **params):
        log("(Main) Creating progress dialog")
        with closing(SafeDialogProgress()) as dialog:
            dialog.create(settings.addon.name)
            dialog.update(0, __addon__.getLocalizedString(30007), ' ', ' ')

            items = {}
            pages = 0

            _time = time.time()
            # Getting item list
            log("(Main) Getting item list")
            with closing(media.List(self.mediaSettings, call, *args, **params)) as medialist:
                while not medialist.is_done(0.100):
                    if xbmc.abortRequested or dialog.iscanceled():
                        raise Abort()
                res = medialist.get_data()
                if not res:
                    raise Error("Did not receive any data", 30304)
                items = res['items']
                pages = res['pages']

            # Update progress dialog
            dialog.set_mentions(len(items)+2)
            dialog.update(1, __addon__.getLocalizedString(30018), ' ', ' ')

            def on_data(progressValue, oldItem, newItem):
                    label = ["%s %s" %(__addon__.getLocalizedString(30034), oldItem["label"])]
                    if newItem.get("label") and not oldItem["label"] == newItem["label"]:
                        label = label+["%s %s" %(__addon__.getLocalizedString(30035), newItem["label"])]
                    if newItem.get("stream_info", {}).get("subtitle", {}).get("language"):
                        label = label+["%s %s" %(__addon__.getLocalizedString(30012), isoToLang(newItem["stream_info"]["subtitle"]["language"]))]
                    while len(label) < 3:
                        label = label+[' ']
                    dialog.update(progressValue, *label)

            # Getting media cache
            log("(Main) Getting media info")
            with closing(media.MediaCache(self.mediaSettings, on_data)) as mediadata:
                [mediadata.submit(item) for item in items]
                mediadata.start()
                while not mediadata.is_done(0.100):
                    if xbmc.abortRequested or dialog.iscanceled():
                        raise Abort()
                items = mediadata.get_data()
                if not items:
                    raise Error("Did not receive any movies", 30305)
            log("(Main) Work time: %s" %(time.time()-_time))

            # Done
            dialog.update(1, __addon__.getLocalizedString(30017), ' ', ' ')

            return (items, pages)

    def addNextButton(self, **kwargs):
        log("(Main) Adding item 'Show more'")

        item = {
            "label": __addon__.getLocalizedString(30000),
            "icon": os.path.join(settings.addon.resources_path, 'media', self.mediaSettings.mediaType, 'more.png'),
            "thumbnail": os.path.join(settings.addon.resources_path, 'media', self.mediaSettings.mediaType, 'more_thumbnail.png'),
            "properties": {
                "fanart_image": settings.addon.fanart
            }
        }
        item.setdefault('properties',  {}).update(dict((key, str(value)) for key, value in kwargs.items() if value))
        xbmcplugin.addDirectoryItem(settings.addon.handle, "%s?%s" %(settings.addon.base_url, settings.addon.cur_uri), ListItem.from_dict(**item).as_xbmc_listitem(), True)

    def _calculate_free_space(self):
        if Platform.system == 'windows':
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(self.mediaSettings.download_path), None, None, ctypes.pointer(free_bytes))
            return free_bytes.value
        st = os.statvfs(self.mediaSettings.download_path)
        return st.f_bavail * st.f_frsize

    """ Views """
    def index(self, **params):
        if settings.tvshows.provider:
            log("(Main) Creating index view")
            self.addItem('movies', **settings.movies.provider.folders(None)[0])
            self.addItem('tvshows', **settings.tvshows.provider.folders(None)[0])
            self.finish()
        else:
            self('movies', **settings.movies.provider.folders(None)[0]["params"])

    def folders(self, action, **params):
        log("(Main) Creating folders view", LOGLEVEL.INFO)
        self.addItems(self.mediaSettings.mediaType, self.mediaSettings.provider.folders(*(action,), **params))
        self.finish()

    def season(self, action, **params):
        log("(Main) (season) Reading page cache", LOGLEVEL.INFO)
        curPageNum = self.getCurPageNum()

    def browse(self, action, **params):
        log("(Main) Creating browse view", LOGLEVEL.INFO)
        curPageNum = self.getCurPageNum()
        with closing(Cache("%s.browse.%s" %(self.mediaSettings.mediaType, hashlib.md5(str(dict([('action', action)], **params))).hexdigest()), ttl=24 * 3600, last_changed=self.mediaSettings.lastchanged)) as cache:
            # Reset page number if the user have cleaned the cache
            if not cache:
                curPageNum = 1

            if not cache or curPageNum > cache['curNumOfPages']:
                log("(Main) Reading item cache")
                items, totalPages = self.getMediaItems('browse', *(action, curPageNum,), **params)
                log("(Main) Updating view cache")
                cache.extendKey("items", items)
                cache.update({"curNumOfPages": curPageNum, "totalPages": totalPages})
            pageCache = cache.copy()

        log("(Main) Adding items")
        self.addItems(self.mediaSettings.mediaType, pageCache["items"], 'player', False)

        # NOTE:
        # Add show more, but we stop at page 20... yes 20 pages sounds all right...
        # ... each page cache file can be between 2 and 3 mByt with 20 pages and will have an average of 1 mByt...
        # This can become substantial problem with movies and tv-shows pages
        if pageCache['curNumOfPages'] < pageCache['totalPages'] and pageCache['curNumOfPages'] < 21:
            self.addNextButton(**{'pageNum': pageCache['curNumOfPages']+1})

        update_listing = False
        if curPageNum > 1:
            update_listing = True

        self.finish(self.mediaSettings.mediaType, update_listing)

    def search(self, **params):
        log("(Main) Creating search view", LOGLEVEL.INFO)
        searchString = self.getSearchString()

        curPageNum = self.getCurPageNum()
        with closing(Cache("%s.search.query" %self.mediaSettings.mediaType, ttl=24 * 3600, last_changed=self.mediaSettings.lastchanged)) as cache:
            # Reset cache when we have different search string
            if cache and not searchString == cache['searchString']:
                log("(Main) Resetting view cache")
                cache.trunctate()

            # Reset page number if the user have cleaned the cache
            # or we have a different search string
            if not cache:
                curPageNum = 1

            if not cache or curPageNum > cache['curNumOfPages']:
                log("(Main) Reading item cache")
                items, totalPages = self.getMediaItems('search', *(searchString, curPageNum,), **params)
                log("(Main) Updating view cache")
                cache.extendKey("items", items)
                cache.update({"curNumOfPages": curPageNum, "totalPages": totalPages, "searchString": searchString})
            pageCache = cache.copy()

        log("(Main) Adding items")
        self.addItems(self.mediaSettings.mediaType, pageCache["items"], 'player', False)

        # NOTE:
        # Add show more, but we stop at page 20... yes 20 pages sounds all right...
        # ... each page cache file can be between 2 and 3 mByt with 20 pages and will have an average of 1 mByt...
        # This can become substantial problem with movies and tv-shows pages
        if pageCache['curNumOfPages'] < pageCache['totalPages'] and pageCache['curNumOfPages'] < 21:
            self.addNextButton(**{'pageNum': pageCache['curNumOfPages']+1, 'searchString': searchString})

        update_listing = False
        if curPageNum > 1:
            update_listing = True

        self.finish(self.mediaSettings.mediaType, update_listing)

    def player(self, subtitle=None, **params):
        log("(Main) Creating player options")
        if settings.addon.handle > -1:
            xbmcplugin.endOfDirectory(settings.addon.handle, True, False, False)

        quality    = None
        free_space = self._calculate_free_space()
        waring     = []
        for _q in self.mediaSettings.qualities:
            if params.get(_q):
                if params['%ssize' %_q] > free_space:
                    if _q == '3D' and self.mediaSettings.play3d == 1 and not Dialog().yesno(30010, 30011):
                        continue
                    quality = _q
                    break
                waring = waring+[_q.upper()]

        if waring:
            if not quality:
                raise Notify('TThere is not enough free space in %s' %self.mediaSettings.download_path, 30323, level=NOTIFYLEVEL.ERROR)

            if len(waring) > 1:
                notify(message=__addon__.getLocalizedString(30325) %(", ".join(waring), waring.pop()), level=NOTIFYLEVEL.WARNING)
            else:
                notify(message=__addon__.getLocalizedString(30326) %waring[0], level=NOTIFYLEVEL.WARNING)
            log('(Main) There must be a minimum of %s to play. %s available in %s' %(shortenBytes(params['720p']['size']), shortenBytes(free_space), self.mediaSettings.download_path), LOGLEVEL.NOTICE)

        TorrentPlayer().playTorrentFile(self.mediaSettings, build_magnetFromMeta(params[quality], "quality %s" %quality), self.getSelectedItem(), subtitle)

class Cmd:
    def __init__(self, endpoint, **params):
        log("(Main) Calling %s. Params: %s" %(endpoint, str(params)), LOGLEVEL.INFO)
        if not hasattr(self, endpoint):
            raise Error("'Cmd' class has no method '%s'" %endpoint)
        getattr(self, endpoint)(**params)

    def clear_cache(self, **params):
        def _run(path):
            for x in os.listdir(path):
                if x in ['.', '..']:
                    continue
                _path = os.path.join(path, x)
                if os.path.isfile(_path):
                    os.remove(_path)
                elif os.path.isdir(_path):
                    _run(_path)
                    os.rmdir(_path)

        if Dialog().yesno(30033):
            _run(settings.addon.cache_path)
            notify(30301)

    def reset_torrent_settings(self, **params):
        if Dialog().yesno(30013, 30014):
            # Network
            __addon__.setSetting("listen_port", '6881')
            __addon__.setSetting("use_random_port", 'true')
            __addon__.setSetting("encryption", '1')
            __addon__.setSetting("connections_limit", '200')
            # Peers
            __addon__.setSetting("torrent_connect_boost", '50')
            __addon__.setSetting("connection_speed", '50')
            __addon__.setSetting("peer_connect_timeout", '15')
            __addon__.setSetting("min_reconnect_time", '60')
            __addon__.setSetting("max_failcount", '3')
            # Features
            __addon__.setSetting("enable_tcp", 'true')
            __addon__.setSetting("enable_dht", 'true')
            __addon__.setSetting("enable_lsd", 'true')
            __addon__.setSetting("enable_utp", 'true')
            __addon__.setSetting("enable_scrape", 'false')
            __addon__.setSetting("enable_upnp", 'true')
            __addon__.setSetting("enable_natpmp", 'true')
            # Additional
            __addon__.setSetting("trackers", '')
            __addon__.setSetting("dht_routers", '')
            notify(30314)

def run():
    try:
        log("(Main) Starting - Platform: %s %s" %(Platform.system, Platform.arch), LOGLEVEL.INFO)

        log("(Main) Platform: %s" %sys.platform)
        if hasattr(os, 'uname'):
            log("(Main) Uname: %s" %str(os.uname()))
        log("(Main) Environ: %s" %str(os.environ))

        if not Platform.system:
            raise Error("Unsupported OS", 30302)

        def _empty_dir(path):
            if os.path.isdir(path):
                for x in os.listdir(path):
                    if x in ['.', '..', 'movies', 'tvshows']:
                        continue
                    _path = os.path.join(path, x)
                    if os.path.isfile(_path):
                        os.remove(_path)
                    elif os.path.isdir(_path):
                        _empty_dir(_path)
                        os.rmdir(_path)

        # Clear cache after update
        if not settings.addon.version+"~1" == settings.addon.last_update_id:
            _empty_dir(settings.addon.cache_path)
            __addon__.setSetting("last_update_id", settings.addon.version+"~1")
        else:
            # Clean debris from the cache dir
            try:
                for mediaType in ['movies', 'tvshows']:
                    if getattr(settings, mediaType).delete_files:
                        _empty_dir(os.path.join(settings.addon.cache_path, mediaType))
            except:
                log_error()
                sys.exc_clear()

        params = dict(urlparse.parse_qsl(settings.addon.cur_uri))
        if not params.pop('cmd', None):
            PopcornTime(**params)
        else:
            Cmd(**params)

    except (Error, HTTPError, ProxyError, TorrentError) as e:
        notify(e.messageID, level=NOTIFYLEVEL.ERROR)
        log_error()
    except Notify as e:
        notify(e.messageID, e.message, level=e.level)
        log("(Main) Notify: %s" %str(e), LOGLEVEL.NOTICE)
        sys.exc_clear()
    except Abort:
        log("(Main) Abort", LOGLEVEL.INFO)
        sys.exc_clear()
    except:
        notify(30308, level=NOTIFYLEVEL.ERROR)
        log_error()
