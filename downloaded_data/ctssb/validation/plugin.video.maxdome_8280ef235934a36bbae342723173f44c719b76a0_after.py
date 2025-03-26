# coding: utf8
import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import urlparse
import urllib

import maxdome as maxdome

addon_handle = int(sys.argv[1])
plugin_base_url = sys.argv[0]
params = dict(urlparse.parse_qsl(sys.argv[2][1:]))
addon = xbmcaddon.Addon()

package_only = False
if addon.getSetting('packageonly').lower() == 'true':
    package_only = True

poster_width = '214'
poster_height = '306'

root_dir = [
            {'label': 'Filme', 'page': 'movies'},
            {'label': 'Serien', 'page': 'serien'},
            {'label': 'TV-Shows', 'page': 'tvshows'},
            {'label': 'Kinder', 'page': 'kids'},
            {'label': 'Musik', 'page': 'music'},
            {'label': 'Wissen & Doku', 'page': 'doku'},
            {'label': 'Specials', 'page': 'specials'},
            {'label': 'Suche', 'page': 'search'},
            {'label': 'Merkliste', 'page': 'notepad'},
            {'label': 'Gekaufte Videos', 'page': 'purchased'},
            {'label': 'Geliehene Videos', 'page': 'rent'}
            ]

cat_filme = [
            {'Alle Filme': 'spielfilm_genre_all'},
            {'Neu im Programm': 'spielfilm_genre_all,new'},
            {'Beste Bewertung': 'spielfilm_top_bestebewertung'},
            {'Meistgesehen': 'spielfilm_top_top100leihvideos'},
            {'Demnächst': 'spielfilm_top_demnaechst'},
            {'Letzte Chance': 'spielfilm_top_letztechance'},
            {'Action & Abenteuer': 'spielfilm_genre_all,genre~action|abenteuer'},
            {'Drama': 'spielfilm_genre_all,genre~drama'},
            {'Dokumentarfilm': 'spielfilm_genre_all,genre~dokumentarfilm'},
            {'Erotik': 'spielfilm_genre_all,genre~erotik'},
            {'Familie': 'spielfilm_genre_all,genre~family'},
            {'Komödie': 'spielfilm_genre_all,genre~komödie'},
            {'Krimi & Thriller': 'spielfilm_genre_all,genre~kriminalfilm|thriller'},
            {'Romantik & Liebe': 'spielfilm_genre_all,genre~romantik'},
            {'Sci-Fi & Fantasy': 'spielfilm_genre_all,genre~scifi|fantasy'},
            {'Western': 'spielfilm_genre_all,genre~western'}
            ]

cat_serien = [
            {'Alle Serien': 'serie_top_bestebewertung'},
            {'Neu im Programm': 'serie_top_bestebewertung,new'},
            {'Beste Bewertung': 'serie_top_bestebewertung'},
            {'Meistgesehen': 'serie_top_top50leihserien'},
            {'Demnächst': 'serie_top_demnaechst'},
            {'Letzte Chance': 'serie_top_letztechance'},
            {'Action': 'bundles,genre~action'},
            {'Arztserie': 'serie_top_bestebewertung,genre~arztserie'},
            {'Comedy': 'serie_top_bestebewertung,genre~comedyserie|sitcom'},
            {'Drama': 'serie_top_bestebewertung,genre~drama|dramedy'},
            {'Horror': 'serie_top_bestebewertung,genre~horror'},
            {'Krimi & Thriller': 'serie_top_bestebewertung,genre~kriminalfilm|thriller'},
            {'Sci-Fi & Fantasy': 'serie_top_bestebewertung,genre~scifi|fantasy'}
            ]

cat_tvshow = [
            {'Alle TV-Shows': 'bundles,genre~eventshow|reality|gameshow|castingshow|kochshow|wrestling'},
            {'Castingshows': 'bundles,genre~castingshow'},
            {'Eventshows': 'bundles,genre~eventshow'},
            {'Gameshows': 'bundles,genre~gameshow'},
            {'Kochshows': 'bundles,genre~kochshow'},
            {'Reality-TV': 'bundles,genre~reality'},
            {'Wrestling': 'bundles,genre~wrestling'}
            ]

cat_kids = [
            {'Alle Kidsvideos': 'kids_genreformateaz_genre_all'},
            {'Kleinkinder': 'kids_genreformateaz_genre_kleinkinder&flt'},
            {'Zeichentrickserien': 'bundles,genre~zeichentrickserie'},
            {'Erziehung & Bildung': 'kids_genreformateaz_genre_erziehungbildung&flt'},
            {'Fantasy': 'kids_genreformateaz_genre_fantasy&flt'},
            {'Kinder & Jugendfilme': 'kids,movies'},
            {'Märchen': 'genre~märchen&flt'}
            ]

cat_music = [
            {'Musik A-Z': 'musik_genre_all&flt'},
            {'Neu im Programm': 'musik_top_neubeimaxdome&flt'},
            {'Beste Bewertung': 'musik_top_bestebewertung&flt'},
            {'Meistgesehen': 'musik_top_top100videosimpaket&flt'}
            ]

cat_doku = [
            {'Wissen & Doku A-Z': 'wissendoku_genreformateaz_genre_all&flt'},
            {'Dokumentationen': 'wissendoku_genreformateaz_genre_dokumentarfilme&flt'},
            {'Extremsport': 'wissendoku_genreformateaz_genre_extremsport&flt'},
            {'Fitness': 'wissendoku_genreformateaz_genre_fitness&flt'},
            {'Geschichte': 'wissendoku_genreformateaz_genre_geschichte&flt'},
            {'Gesellschaft & Soziales': 'wissendoku_genreformateaz_genre_gesellschaftsoziales&flt'},
            {'Magazin': 'wissendoku_genreformateaz_genre_magazin&flt'},
            {'Motorsport': 'wissendoku_genreformateaz_genre_motorsport&flt'},
            {'Natur': 'wissendoku_genreformateaz_genre_natur&flt'},
            {'Persönlichkeiten': 'wissendoku_genreformateaz_genre_persoenlichkeiten&flt'},
            {'Reality-TV': 'wissendoku_genreformateaz_genre_realitytv&flt'},
            {'Reise': 'wissendoku_genreformateaz_genre_reise&flt'},
            {'Reportage': 'wissendoku_genreformateaz_genre_reportage&flt'},
            {'Reise': 'wissendoku_genreformateaz_genre_geschichte&flt'},
            {'Wissenschaft & Technik': 'wissendoku_genreformateaz_genre_wissenschafttechnik&flt'},
            {'Zeitgeschichte': 'wissendoku_genreformateaz_genre_zeitgeschichte&flt'}
            ]

class Navigation:
    def __init__(self, s):
        self.mxd = s

    def buildUrl(self, query):
        return 'plugin://%s?%s' % (addon.getAddonInfo('id'), urllib.urlencode(query))

    def buildAssetUrl(self, asset):
        asset_class = maxdome.getAssetClass(asset['@class'])
        param_action = ''
        param_id = ''
        if asset_class == 'tvshow' or asset_class == 'tvseason' or asset_class == 'theme':
            param_action = 'list'
            param_id = 'parentid~%s' % (asset['id'])
        elif asset_class == 'movie' or asset_class == 'tvepisode':
            param_action = 'play'
            param_id = asset['id']

        return self.buildUrl({'action': param_action, 'id': param_id})

    def getTitle(self, asset):
        asset_class = maxdome.getAssetClass(asset['@class'])
        if asset_class == 'movie' or asset_class == 'tvshow':
            return asset['title']
        elif asset_class == 'tvseason':
            r = 'Staffel %02d' % (int(asset['number']))
            if not 'de' in asset['languageList']:
                r += ' (OV)'
            return r
        elif asset_class == 'tvepisode':
            return 'S%02dE%02d - %s' % (int(asset['seasonNumber']), int(asset['episodeNumber']), asset['episodeTitle'])
        else:
            return asset['title']

    def mainMenu(self):
        for item in root_dir:
            url = self.buildUrl({'action': 'list', 'page': item['page']})
            li = xbmcgui.ListItem(item['label'])
            li.addContextMenuItems(self.contextMenuItemsForPage(), replaceItems=False)
            xbmcplugin.addDirectoryItem(handle=addon_handle, url=url,
                                listitem=li, isFolder=True)

        xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)


    def listPage(self, table, filter_serie=False):
        for item in table:
            use_filter = False
            if '&flt' in item.values()[0]:
                use_filter = True
            url = self.buildUrl({'action': 'list', 'id': item.values()[0].replace('&flt', ''), 'use_filter': use_filter})
            li = xbmcgui.ListItem(item.keys()[0])
            li.addContextMenuItems(self.contextMenuItemsForPage(), replaceItems=False)
            xbmcplugin.addDirectoryItem(handle=addon_handle, url=url,
                                listitem=li, isFolder=True)

        xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=False)

    def getPage(self, page):
        if page == 'movies':
            self.listPage(cat_filme)
        elif page == 'serien':
            self.listPage(cat_serien)
        elif page == 'tvshows':
            self.listPage(cat_tvshow)
        elif page == 'kids':
            self.listPage(cat_kids)
        elif page == 'music':
            self.listPage(cat_music)
        elif page == 'doku':
            self.listPage(cat_doku)
        elif page == 'specials':
            self.listAssets('themespecial')
        elif page == 'search':
            dlg = xbmcgui.Dialog()
            term = dlg.input('Suchbegriff', type=xbmcgui.INPUT_ALPHANUM)
            self.listAssets('search~"' + term + '"', use_filter=2)
        elif page == 'notepad':
            assets = self.mxd.Assets.parseHtmlAssetsBak(path='/mein-account/merkzettel')
            self.getHtmlAssets(assets)
        elif page == 'purchased':
            assets = self.mxd.Assets.parseHtmlAssetsBak(path='/mein-account/historie?history=2', opt_pref='r_', select_set=1)
            self.getHtmlAssets(assets)
        elif page == 'rent':
            assets = self.mxd.Assets.parseHtmlAssetsBak(path='/mein-account/historie?history=1', opt_pref='r_', select_set=0)
            self.getHtmlAssets(assets)

    def getHtmlAssets(self, assets):
        query = 'assetid~'
        for item in assets:
            query += str(item) + '|'
        query = query[0:len(query)-1]
        self.listAssets(query, force=True)

    def contextMenuItemsForPage(self):
        listitems = []
        #ZEIGE PAKET/STORE
        view_str = 'Zeige '
        if package_only:
            view_str += 'alle Inhalte'
        else:
            view_str += 'nur Paketinhalte'
        listitems.append((view_str, 'RunPlugin(' + plugin_base_url + '?switchview=1' + str(sys.argv[2]).replace('?', '&')+')'))
        return listitems

    def contextMenuItemsForAsset(self, asset):
        listitems = []
        #ZAHLUNGSPFLICHTIGE INHALTE
        if not asset['green']:
            asset_class = maxdome.getAssetClass(asset['@class'])
            strTitle = ''
            if asset_class == 'movie':
                strTitle = 'Film '
            elif asset_class == 'tvseason':
                strTitle = 'Staffel '
            elif asset_class == 'tvepisode':
                strTitle = 'Episode '
            if not asset_class == 'tvshow' and not asset_class == 'theme':
                listitems.append((strTitle + 'leihen/kaufen', 'RunPlugin(' + self.buildUrl({'action': 'buy', 'id': str(asset['id'])}) + ')'))
        #MERKLISTE
        mem_param = ''
        mem_str = ''
        if asset['remembered']:
            mem_str = 'Von Merkliste entfernen'
            mem_param = 'del'
        else:
            mem_str = 'Zur Merkliste hinzufügen'
            mem_param = 'add'
        listitems.append((mem_str, 'RunPlugin(' + self.buildUrl({'action': mem_param, 'id': str(asset['id'])}) + ')'))
        #ZEIGE PAKET/STORE
        view_str = 'Zeige '
        if package_only:
            view_str += 'alle Inhalte'
        else:
            view_str += 'nur Paketinhalte'
        listitems.append((view_str, 'RunPlugin(' + plugin_base_url + sys.argv[2] + '&switchview=1)'))
        #EXPORT FOR LIBRARY
        if addon.getSetting('enablelibraryfolder') == 'true' and not asset['@class'].startswith('MultiAssetTheme'):
            listitems.append(('Für Bibliothek exportieren', 'RunPlugin(' + self.buildUrl({'action': 'export', 'id': str(asset['id'])}) + ')'))

        return listitems

    def getInfoItem(self, asset):
        info = {}
        info['plot'] = asset['descriptionShort']
        if 'descriptionLong' in asset:
            info['plot'] = asset['descriptionLong']
        info['userrating'] = asset['userrating']['averageRating']
        if 'duration' in asset:
            info['duration'] = int(asset['duration'])*60
        if 'productionYear' in asset:
            info['year'] = asset['productionYear']
        asset_class = maxdome.getAssetClass(asset['@class'])
        if asset_class == 'movie':
            info['mediatype'] = 'movie'
            info['title'] = asset['title']
            xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_TITLE)
        elif asset_class == 'tvshow':
            info['mediatype'] = 'tvshow'
            info['title'] = asset['title']
            xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_TITLE)
        elif asset_class == 'tvseason':
            info['mediatype'] = 'season'
            info['title'] = asset['title']
            xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
        elif asset_class == 'tvepisode':
            info['mediatype'] = 'episode'
            info['tvshowtitle'] = asset['title']
            info['title'] = asset['episodeTitle']#self.getTitle(asset)
            info['plot'] = asset['descriptionShort']
            info['season'] = int(asset['seasonNumber'])
            info['episode'] = int(asset['episodeNumber'])
            xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_EPISODE)

        if not asset['green'] and not self.mxd.Assets.isPackageContent(asset):
            if 'title' in info:
                info['title'] += ' (p)'

        return info

    def getPoster(self, data):
        img = ''        
        if not 'coverList' in data:
            return img
        for item in data['coverList']:
            img = item['url'].replace('__WIDTH__', poster_width).replace('__HEIGHT__', poster_height)
            if item['usageType'] == 'poster':
                return img

        return img

    def filterSeriesFromSeasons(self, data):
        series_dict = {}
        for item in data:
            if item['@class'].lower() == 'multiassettvseriesseason':
                asset_id = item['parentIdList'][0]
                if not asset_id in series_dict.keys():
                    item['id'] = asset_id
                    item['@class'] = 'MultiAssetBundleTvSeries'
                    series_dict[asset_id] = item
        
        return series_dict.values()

    def filterTvShows(self, data, rem_episodes=False, rem_seasons=False):
        listitems = []
        for item in data['assetList']:
            asset_class = maxdome.getAssetClass(item['@class'])
            if asset_class == 'tvepisode' and rem_episodes:
                continue
            elif asset_class == 'tvseason' and rem_seasons:
                continue

            listitems.append(item)

        return listitems

    def hasMorePages(self, data):
        if not 'pageInfo' in data:
            return False
        if (data['pageInfo']['start']>1 and data['pageInfo']['size']<self.mxd.Assets.page_size):
            return False
        elif (data['pageInfo']['start']*data['pageInfo']['size']<data['pageInfo']['total']):
            return True

        return False

    def listAssets(self, query, use_filter=False, force=False, start=1):
        if package_only and not force:
#            query += ',package~premium_basic'
            query += ',hasPackageContent'
        data = self.mxd.Assets.getAssets(query, page_start=start)
        if use_filter:
            data['assetList'] = self.filterTvShows(data, True, True)
        xbmcplugin.setContent(addon_handle, 'movies')
        for item in data['assetList']:
            url = self.buildAssetUrl(item)
            isPlayable = False
            if 'action=play' in url:
                isPlayable = True
            
            li = xbmcgui.ListItem(self.getTitle(item))
            if 'remembered' in item:
                li.setProperty('remembered', str(item['remembered']))
            if 'id' in item:
                li.addContextMenuItems(self.contextMenuItemsForAsset(item), replaceItems=False)
            li.setProperty('IsPlayable', str(isPlayable))
            li.setInfo('video', self.getInfoItem(item))
            poster = self.getPoster(item)
            if not poster == '':
                li.setArt({'poster': poster})
            xbmcplugin.addDirectoryItem(handle=addon_handle, url=url,
                                listitem=li, isFolder=(not isPlayable))

#        xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_LABEL)
#        xbmcplugin.addSortMethod(addon_handle, xbmcplugin.SORT_METHOD_VIDEO_TITLE)
        xbmcplugin.addSortMethod(addon_handle, 18) #YEAR
        xbmcplugin.addSortMethod(addon_handle, 19) #RATING
        if self.hasMorePages(data):
            li = xbmcgui.ListItem('(Seite ' + str(data['pageInfo']['start']+1) + ')')
            url = self.buildUrl({'action': 'list', 'id': query, 'start': str(data['pageInfo']['start']+1)})
            xbmcplugin.addDirectoryItem(handle=addon_handle, url=url, listitem=li, isFolder=True)
        xbmcplugin.endOfDirectory(addon_handle, cacheToDisc=True)

    def switchPackageView(self):
        if addon.getSetting('packageonly').lower() == 'true':
            package_only = False
            addon.setSetting('packageonly', 'false')
        else: 
            package_only = True
            addon.setSetting('packageonly', 'true')
        xbmc.executebuiltin('Container.Refresh')

    def showSalesOptions(self, asset):
        sales_options = self.mxd.Assets.getSalesOptions(asset)
        asset_class = maxdome.getAssetClass(asset['@class'])
        dlg = xbmcgui.Dialog()
        dlgitems = []
        for item in sales_options:
            dlgitems.append(item['label'])
        dlgtitle = asset['title']
        if asset_class == 'tvseason':
           dlgtitle += ' - Staffel: ' + str(asset['number'])
        elif asset_class == 'tvepisode':
           dlgtitle += ' - Episode: ' + str(asset['episodeTitle'])
        s = dlg.select(dlgtitle, dlgitems)
        if s<0:
            return None

        return sales_options[s]

    def playAsset(self, assetid):
        asset_info = self.mxd.Assets.getAssetInformation(assetid)
        asset_class = maxdome.getAssetClass(asset_info['@class'])
        #ASSET WITHOUT ACTIVE LICENSE - BUY/RENT?
        if not asset_info['green']:
            options = self.showSalesOptions(asset_info)
            if options:
                r = self.mxd.Assets.orderAsset(assetid, orderType=options['orderType'], orderQuality=options['orderQuality'])
                if '@class' in r:
                    if r['@class'] == 'SelectPaymentQuestionStep':
                        dlg = xbmcgui.Dialog()
                        doOrder = dlg.yesno('Maxdome Store', r['title'], r['priceInfo'], 'Zahlungsmethode: ' + self.mxd.payment_type.title())
                        if doOrder:
                            if not self.mxd.Assets.confirmPayment(assetid, options['orderType'], options['orderQuality']):
                                dlg.ok('Fehler', 'Video konnte nicht geliehen/gekauft werden')
                                return False
                            
            else:
                return False

        if asset_class != 'movie' and asset_class != 'tvepisode':
            return False

        if self.mxd.Assets.orderAsset(assetid):
            li = xbmcgui.ListItem(path=self.mxd.video_url)
            info = self.getInfoItem(asset_info)
            li.setInfo('video', info)
            li.setProperty('inputstream.mpd.license_type', 'com.widevine.alpha')
            li.setProperty('inputstream.mpd.license_key', self.mxd.license_url)
            li.setProperty('inputstreamaddon', 'inputstream.mpd')

            xbmcplugin.setResolvedUrl(addon_handle, True, listitem=li)
            return True

        return False
