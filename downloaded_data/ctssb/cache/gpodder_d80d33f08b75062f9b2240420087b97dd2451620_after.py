# -*- coding: utf-8 -*-
#
# gPodder - A media aggregator and podcast client
# Copyright (c) 2005-2009 Thomas Perl and the gPodder Team
#
# gPodder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# gPodder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


#
#  libpodcasts.py -- data classes for gpodder
#  thomas perl <thp@perli.net>   20051029
#
#  Contains code based on:
#            liblocdbwriter.py (2006-01-09)
#            liblocdbreader.py (2006-01-10)
#

import gtk
import gobject
import pango

import gpodder
from gpodder import util
from gpodder import opml
from gpodder import feedcore
from gpodder import services
from gpodder import draw
from gpodder import dumbshelve
from gpodder import resolver
from gpodder import corestats

from gpodder.liblogger import log
from gpodder.libgpodder import gl
from gpodder.dbsqlite import db

import os.path
import os
import glob
import shutil
import sys
import urllib
import urlparse
import time
import datetime
import rfc822
import hashlib
import xml.dom.minidom
import feedparser

from xml.sax import saxutils

_ = gpodder.gettext

if gpodder.interface == gpodder.MAEMO:
    ICON_AUDIO_FILE = 'gnome-mime-audio-mp3'
    ICON_VIDEO_FILE = 'gnome-mime-video-mp4'
    ICON_GENERIC_FILE = 'text-x-generic'
    ICON_DOWNLOADING = 'qgn_toolb_messagin_moveto'
    ICON_DELETED = 'qgn_toolb_gene_deletebutton'
    ICON_NEW = 'qgn_list_gene_favor'
else:
    ICON_AUDIO_FILE = 'audio-x-generic'
    ICON_VIDEO_FILE = 'video-x-generic'
    ICON_GENERIC_FILE = 'text-x-generic'
    ICON_DOWNLOADING = gtk.STOCK_GO_DOWN
    ICON_DELETED = gtk.STOCK_DELETE
    ICON_NEW = gtk.STOCK_ABOUT


class gPodderFetcher(feedcore.Fetcher):
    """
    This class extends the feedcore Fetcher with the gPodder User-Agent and the
    Proxy handler based on the current settings in gPodder and provides a
    convenience method (fetch_channel) for use by PodcastChannel objects.
    """

    def __init__(self):
        feedcore.Fetcher.__init__(self, gpodder.user_agent)

    def fetch_channel(self, channel):
        etag = channel.etag
        modified = feedparser._parse_date(channel.last_modified)
        # If we have a username or password, rebuild the url with them included
        # Note: using a HTTPBasicAuthHandler would be pain because we need to
        # know the realm. It can be done, but I think this method works, too
        if channel.username or channel.password:
            username = urllib.quote(channel.username)
            password = urllib.quote(channel.password)
            auth_string = ':'.join((username, password))
            url_parts = list(urlparse.urlsplit(channel.url))
            url_parts[1] = '@'.join((auth_string, url_parts[1]))
            url = urlparse.urlunsplit(url_parts)
        else:
            url = channel.url
        self.fetch(url, etag, modified)

    def _resolve_url(self, url):
        return resolver.get_real_channel_url(url)

#    def _get_handlers(self):
#        # Add a ProxyHandler for fetching data via a proxy server
#        proxies = {'http': 'http://proxy.example.org:8080'}
#        return[urllib2.ProxyHandler(proxies))]


class PodcastModelObject(object):
    """
    A generic base class for our podcast model providing common helper
    and utility functions.
    """

    @classmethod
    def create_from_dict(cls, d, *args):
        """
        Create a new object, passing "args" to the constructor
        and then updating the object with the values from "d".
        """
        o = cls(*args)
        o.update_from_dict(d)
        return o

    def update_from_dict(self, d):
        """
        Updates the attributes of this object with values from the
        dictionary "d" by using the keys found in "d".
        """
        for k in d:
            if hasattr(self, k):
                setattr(self, k, d[k])


class PodcastChannel(PodcastModelObject):
    """holds data for a complete channel"""
    MAX_FOLDERNAME_LENGTH = 150
    icon_cache = {}

    feed_fetcher = gPodderFetcher()

    @classmethod
    def load(cls, url, create=True, authentication_tokens=None):
        if isinstance(url, unicode):
            url = url.encode('utf-8')

        tmp = db.load_channels(factory=cls.create_from_dict, url=url)
        if len(tmp):
            return tmp[0]
        elif create:
            tmp = PodcastChannel(url)
            if authentication_tokens is not None:
                tmp.username = authentication_tokens[0]
                tmp.password = authentication_tokens[1]

            tmp.update()
            tmp.save()
            db.force_last_new(tmp)
            return tmp

    def episode_factory(self, d):
        """
        This function takes a dictionary containing key-value pairs for
        episodes and returns a new PodcastEpisode object that is connected
        to this PodcastChannel object.

        Returns: A new PodcastEpisode object
        """
        return PodcastEpisode.create_from_dict(d, self)

    def _consume_updated_feed(self, feed):
        # update the cover if it's not there
        self.update_cover()

        self.parse_error = feed.get('bozo_exception', None)

        self.title = feed.feed.get('title', self.url)
        self.link = feed.feed.get('link', self.link)
        self.description = feed.feed.get('subtitle', self.description)
        # Start YouTube-specific title FIX
        YOUTUBE_PREFIX = 'Uploads by '
        if self.title.startswith(YOUTUBE_PREFIX):
            self.title = self.title[len(YOUTUBE_PREFIX):] + ' on YouTube'
        # End YouTube-specific title FIX

        try:
            self.pubDate = rfc822.mktime_tz(feed.feed.get('updated_parsed', None+(0,)))
        except:
            self.pubDate = time.time()

        if hasattr(feed.feed, 'image'):
            if hasattr(feed.feed.image, 'href') and feed.feed.image.href:
                old = self.image
                self.image = feed.feed.image.href
                if old != self.image:
                    self.update_cover(force=True)

        self.save()

        # Load all episodes to update them properly.
        existing = self.get_all_episodes()

        # We can limit the maximum number of entries that gPodder will parse
        # via the "max_episodes_per_feed" configuration option.
        if len(feed.entries) > gl.config.max_episodes_per_feed:
            log('Limiting number of episodes for %s to %d', self.title, gl.config.max_episodes_per_feed)
        for entry in feed.entries[:min(gl.config.max_episodes_per_feed, len(feed.entries))]:
            episode = None

            try:
                episode = PodcastEpisode.from_feedparser_entry(entry, self)
            except Exception, e:
                log('Cannot instantiate episode "%s": %s. Skipping.', entry.get('id', '(no id available)'), e, sender=self, traceback=True)

            if episode:
                self.count_new += 1

                for ex in existing:
                    if ex.guid == episode.guid or episode.is_duplicate(ex):
                        for k in ('title', 'url', 'description', 'link', 'pubDate', 'guid'):
                            setattr(ex, k, getattr(episode, k))
                        self.count_new -= 1
                        episode = ex

                episode.save()

        # This *might* cause episodes to be skipped if there were more than
        # max_episodes_per_feed items added to the feed between updates.
        # The benefit is that it prevents old episodes from apearing as new
        # in certain situations (see bug #340).
        db.purge(gl.config.max_episodes_per_feed, self.id)

    def _update_etag_modified(self, feed):
        self.updated_timestamp = time.time()
        self.calculate_publish_behaviour()
        self.etag = feed.headers.get('etag', self.etag)
        self.last_modified = feed.headers.get('last-modified', self.last_modified)

    def update(self):
        if self.updated_timestamp > time.time() - 60*60*24:
            # If we have updated in the last 24 hours, do some optimizations
            if self.release_expected > time.time():
                hours = (self.release_expected-time.time())/(60*60)
                log('Expecting a release in %.2f hours - skipping %s', hours, self.title, sender=self)
                return

            # If we have updated in the last 10 minutes, skip the update
            if self.updated_timestamp > time.time() - 60*10:
                log('Last update still too recent - skipping %s', self.title, sender=self)
                return

        try:
            self.feed_fetcher.fetch_channel(self)
        except feedcore.UpdatedFeed, updated:
            feed = updated.data
            self._consume_updated_feed(feed)
            self._update_etag_modified(feed)
            self.save()
        except feedcore.NewLocation, updated:
            feed = updated.data
            self.url = feed.href
            self._consume_updated_feed(feed)
            self._update_etag_modified(feed)
            self.save()
        except feedcore.NotModified, updated:
            feed = updated.data
            self._update_etag_modified(feed)
            self.save()
        except Exception, e:
            # "Not really" errors
            #feedcore.AuthenticationRequired
            # Temporary errors
            #feedcore.Offline
            #feedcore.BadRequest
            #feedcore.InternalServerError
            #feedcore.WifiLogin
            # Permanent errors
            #feedcore.Unsubscribe
            #feedcore.NotFound
            #feedcore.InvalidFeed
            #feedcore.UnknownStatusCode
            raise

        db.commit()

    def update_cover(self, force=False):
        if self.cover_file is None or not os.path.exists(self.cover_file) or force:
            if self.image is not None:
                services.cover_downloader.request_cover(self)

    def delete(self):
        db.delete_channel(self)

    def save(self):
        db.save_channel(self)

    def stat(self, state=None, is_played=None, is_locked=None):
        return db.get_channel_stat(self.url, state=state, is_played=is_played, is_locked=is_locked)

    def __init__( self, url = "", title = "", link = "", description = ""):
        self.id = None
        self.url = url
        self.title = title
        self.link = link
        self.description = description
        self.image = None
        self.pubDate = 0
        self.parse_error = None
        self.newest_pubdate_cached = None
        self.iter = None
        self.foldername = None
        self.auto_foldername = 1 # automatically generated foldername

        # should this channel be synced to devices? (ex: iPod)
        self.sync_to_devices = True
        # to which playlist should be synced
        self.device_playlist_name = 'gPodder'
        # if set, this overrides the channel-provided title
        self.override_title = ''
        self.username = ''
        self.password = ''

        self.last_modified = None
        self.etag = None

        self.save_dir_size = 0
        self.__save_dir_size_set = False

        self.count_downloaded = 0
        self.count_new = 0
        self.count_unplayed = 0

        self.channel_is_locked = False

        self.release_expected = time.time()
        self.release_deviation = 0
        self.updated_timestamp = 0

    def calculate_publish_behaviour(self):
        episodes = db.load_episodes(self, factory=self.episode_factory, limit=30)
        if len(episodes) < 3:
            return

        deltas = []
        latest = max(e.pubDate for e in episodes)
        for index in range(len(episodes)-1):
            if episodes[index].pubDate != 0 and episodes[index+1].pubDate != 0:
                deltas.append(episodes[index].pubDate - episodes[index+1].pubDate)

        if len(deltas) > 1:
            stats = corestats.Stats(deltas)
            self.release_expected = min([latest+stats.stdev(), latest+(stats.min()+stats.avg())*.5])
            self.release_deviation = stats.stdev()
        else:
            self.release_expected = latest
            self.release_deviation = 0

    def request_save_dir_size(self):
        if not self.__save_dir_size_set:
            self.update_save_dir_size()
        self.__save_dir_size_set = True

    def update_save_dir_size(self):
        self.save_dir_size = util.calculate_size(self.save_dir)

    def get_title( self):
        if self.override_title:
            return self.override_title
        elif not self.__title.strip():
            return self.url
        else:
            return self.__title

    def set_title( self, value):
        self.__title = value.strip()

    title = property(fget=get_title,
                     fset=set_title)

    def set_custom_title( self, custom_title):
        custom_title = custom_title.strip()

        # make sure self.foldername is initialized
        self.get_save_dir()

        # rename folder if custom_title looks sane
        new_folder_name = self.find_unique_folder_name(custom_title)
        if len(new_folder_name) > 0 and new_folder_name != self.foldername:
            log('Changing foldername based on custom title: %s', custom_title, sender=self)
            new_folder = os.path.join(gl.downloaddir, new_folder_name)
            old_folder = os.path.join(gl.downloaddir, self.foldername)
            if os.path.exists(old_folder):
                if not os.path.exists(new_folder):
                    # Old folder exists, new folder does not -> simply rename
                    log('Renaming %s => %s', old_folder, new_folder, sender=self)
                    os.rename(old_folder, new_folder)
                else:
                    # Both folders exist -> move files and delete old folder
                    log('Moving files from %s to %s', old_folder, new_folder, sender=self)
                    for file in glob.glob(os.path.join(old_folder, '*')):
                        shutil.move(file, new_folder)
                    log('Removing %s', old_folder, sender=self)
                    shutil.rmtree(old_folder, ignore_errors=True)
            self.foldername = new_folder_name
            self.save()

        if custom_title != self.__title:
            self.override_title = custom_title
        else:
            self.override_title = ''

    def get_downloaded_episodes(self):
        return db.load_episodes(self, factory=self.episode_factory, state=db.STATE_DOWNLOADED)
    
    def get_new_episodes(self, downloading=lambda e: False):
        """
        Get a list of new episodes. You can optionally specify
        "downloading" as a callback that takes an episode as
        a parameter and returns True if the episode is currently
        being downloaded or False if not.

        By default, "downloading" is implemented so that it
        reports all episodes as not downloading.
        """
        def check_is_new(episode):
            """
            For a given episode, returns True if it is to
            be considered new or False if it is "not new".
            """
            return episode.state == db.STATE_NORMAL and \
                    not episode.is_played and \
                    not downloading(episode)

        return [episode for episode in db.load_episodes(self, \
                factory=self.episode_factory) if check_is_new(episode)]

    def update_m3u_playlist(self):
        if gl.config.create_m3u_playlists:
            downloaded_episodes = self.get_downloaded_episodes()
            fn = util.sanitize_filename(self.title)
            if len(fn) == 0:
                fn = os.path.basename(self.save_dir)
            m3u_filename = os.path.join(gl.downloaddir, fn+'.m3u')
            log('Writing playlist to %s', m3u_filename, sender=self)
            f = open(m3u_filename, 'w')
            f.write('#EXTM3U\n')

            # Check to see if we need to reverse the playlist order
            if gl.config.reverse_m3u_playlist_order:
                episodes_m3u = reversed(downloaded_episodes)
            else:
                episodes_m3u = downloaded_episodes

            for episode in episodes_m3u:
                if episode.was_downloaded(and_exists=True):
                    filename = episode.local_filename(create=False)
                    assert filename is not None

                    if os.path.dirname(filename).startswith(os.path.dirname(m3u_filename)):
                        filename = filename[len(os.path.dirname(m3u_filename)+os.sep):]
                    f.write('#EXTINF:0,'+self.title+' - '+episode.title+' ('+episode.cute_pubdate()+')\n')
                    f.write(filename+'\n')
            f.close()

    def addDownloadedItem(self, item):
        log('addDownloadedItem(%s)', item.url)

        if not item.was_downloaded():
            item.mark_downloaded(save=True)
            self.update_m3u_playlist()

    def get_all_episodes(self):
        return db.load_episodes(self, factory=self.episode_factory)

    def iter_set_downloading_columns(self, model, iter, episode=None, downloading=None):
        global ICON_AUDIO_FILE, ICON_VIDEO_FILE, ICON_GENERIC_FILE
        global ICON_DOWNLOADING, ICON_DELETED, ICON_NEW
        
        if episode is None:
            url = model.get_value( iter, 0)
            episode = db.load_episode(url, factory=self.episode_factory)
        else:
            url = episode.url

        if gl.config.episode_list_descriptions or gpodder.interface == gpodder.MAEMO:
            icon_size = 32
        else:
            icon_size = 16

        if downloading is not None and downloading(episode):
            status_icon = util.get_tree_icon(ICON_DOWNLOADING, icon_cache=self.icon_cache, icon_size=icon_size)
        else:
            if episode.state == db.STATE_NORMAL:
                if episode.is_played:
                    status_icon = None
                else:
                    status_icon = util.get_tree_icon(ICON_NEW, icon_cache=self.icon_cache, icon_size=icon_size)
            elif episode.was_downloaded():
                missing = not episode.file_exists()

                if missing:
                    log('Episode missing: %s (before drawing an icon)', episode.url, sender=self)

                file_type = util.file_type_by_extension( model.get_value( iter, 9))
                if file_type == 'audio':
                    status_icon = util.get_tree_icon(ICON_AUDIO_FILE, not episode.is_played, episode.is_locked, not episode.file_exists(), self.icon_cache, icon_size)
                elif file_type == 'video':
                    status_icon = util.get_tree_icon(ICON_VIDEO_FILE, not episode.is_played, episode.is_locked, not episode.file_exists(), self.icon_cache, icon_size)
                else:
                    status_icon = util.get_tree_icon(ICON_GENERIC_FILE, not episode.is_played, episode.is_locked, not episode.file_exists(), self.icon_cache, icon_size)
            elif episode.state == db.STATE_DELETED or episode.state == db.STATE_DOWNLOADED:
                status_icon = util.get_tree_icon(ICON_DELETED, not episode.is_played, icon_cache=self.icon_cache, icon_size=icon_size)
            else:
                log('Warning: Cannot determine status icon.', sender=self)
                status_icon = None

        model.set( iter, 4, status_icon)

    def get_tree_model(self, downloading=None):
        """
        Return a gtk.ListStore containing episodes for this channel
        """
        DATA_TYPES = (str, str, str, bool, gtk.gdk.Pixbuf, str, str, str, str, str)

        # TODO: Remove unused columns, make these symbolic names class
        # members and use them everywhere, so we can change/reorder them
        C_URL, C_TITLE, C_FILESIZE_TEXT, C_UNUSED0, C_STATUS_ICON, \
                C_PUBLISHED_TEXT, C_DESCRIPTION, C_DESCRIPTION_STRIPPED, \
                C_UNUSED1, C_EXTENSION = range(len(DATA_TYPES))

        new_model = gtk.ListStore(*DATA_TYPES)

        log('Returning TreeModel for %s', self.url, sender = self)
        urls = []
        for item in self.get_all_episodes():
            description = item.title_and_description

            if item.length > 0:
                filelength = util.format_filesize(item.length, 1)
            else:
                filelength = None

            new_iter = new_model.append((item.url, item.title, filelength, 
                True, None, item.cute_pubdate(), description, util.remove_html_tags(item.description), 
                'XXXXXXXXXXXXXUNUSEDXXXXXXXXXXXXXXXXXXX', item.extension()))
            self.iter_set_downloading_columns( new_model, new_iter, episode=item, downloading=downloading)
            urls.append(item.url)
        
        self.update_save_dir_size()
        return (new_model, urls)
    
    def find_episode( self, url):
        return db.load_episode(url, factory=self.episode_factory)

    @classmethod
    def find_unique_folder_name(cls, foldername):
        current_try = util.sanitize_filename(foldername, cls.MAX_FOLDERNAME_LENGTH)
        next_try_id = 2

        while db.channel_foldername_exists(current_try):
            current_try = '%s (%d)' % (foldername, next_try_id)
            next_try_id += 1

        return current_try

    def get_save_dir(self):
        urldigest = hashlib.md5(self.url).hexdigest()
        sanitizedurl = util.sanitize_filename(self.url, self.MAX_FOLDERNAME_LENGTH)
        if self.foldername is None or (self.auto_foldername and (self.foldername == urldigest or self.foldername.startswith(sanitizedurl))):
            # we must change the folder name, because it has not been set manually
            fn_template = util.sanitize_filename(self.title, self.MAX_FOLDERNAME_LENGTH)

            # if this is an empty string, try the basename
            if len(fn_template) == 0:
                log('That is one ugly feed you have here! (Report this to bugs.gpodder.org: %s)', self.url, sender=self)
                fn_template = util.sanitize_filename(os.path.basename(self.url), self.MAX_FOLDERNAME_LENGTH)

            # If the basename is also empty, use the first 6 md5 hexdigest chars of the URL
            if len(fn_template) == 0:
                log('That is one REALLY ugly feed you have here! (Report this to bugs.gpodder.org: %s)', self.url, sender=self)
                fn_template = urldigest # no need for sanitize_filename here

            # Find a unique folder name for this podcast
            wanted_foldername = self.find_unique_folder_name(fn_template)

            # if the foldername has not been set, check if the (old) md5 filename exists
            if self.foldername is None and os.path.exists(os.path.join(gl.downloaddir, urldigest)):
                log('Found pre-0.15.0 download folder for %s: %s', self.title, urldigest, sender=self)
                self.foldername = urldigest

            # we have a valid, new folder name in "current_try" -> use that!
            if self.foldername is not None and wanted_foldername != self.foldername:
                # there might be an old download folder crawling around - move it!
                new_folder_name = os.path.join(gl.downloaddir, wanted_foldername)
                old_folder_name = os.path.join(gl.downloaddir, self.foldername)
                if os.path.exists(old_folder_name):
                    if not os.path.exists(new_folder_name):
                        # Old folder exists, new folder does not -> simply rename
                        log('Renaming %s => %s', old_folder_name, new_folder_name, sender=self)
                        os.rename(old_folder_name, new_folder_name)
                    else:
                        # Both folders exist -> move files and delete old folder
                        log('Moving files from %s to %s', old_folder_name, new_folder_name, sender=self)
                        for file in glob.glob(os.path.join(old_folder_name, '*')):
                            shutil.move(file, new_folder_name)
                        log('Removing %s', old_folder_name, sender=self)
                        shutil.rmtree(old_folder_name, ignore_errors=True)
            log('Updating foldername of %s to "%s".', self.url, wanted_foldername, sender=self)
            self.foldername = wanted_foldername
            self.save()

        save_dir = os.path.join(gl.downloaddir, self.foldername)

        # Create save_dir if it does not yet exist
        if not util.make_directory( save_dir):
            log( 'Could not create save_dir: %s', save_dir, sender = self)

        return save_dir
    
    save_dir = property(fget=get_save_dir)

    def remove_downloaded( self):
        shutil.rmtree( self.save_dir, True)
    
    def get_index_file(self):
        # gets index xml filename for downloaded channels list
        return os.path.join( self.save_dir, 'index.xml')
    
    index_file = property(fget=get_index_file)
    
    def get_cover_file( self):
        # gets cover filename for cover download cache
        return os.path.join( self.save_dir, 'cover')

    cover_file = property(fget=get_cover_file)

    def delete_episode_by_url(self, url):
        episode = db.load_episode(url, factory=self.episode_factory)

        if episode is not None:
            filename = episode.local_filename(create=False)
            if filename is not None:
                util.delete_file(filename)
            else:
                log('Cannot delete episode: %s (I have no filename!)', episode.title, sender=self)
            episode.set_state(db.STATE_DELETED)

        self.update_m3u_playlist()


class PodcastEpisode(PodcastModelObject):
    """holds data for one object in a channel"""
    MAX_FILENAME_LENGTH = 200

    def reload_from_db(self):
        """
        Re-reads all episode details for this object from the
        database and updates this object accordingly. Can be
        used to refresh existing objects when the database has
        been updated (e.g. the filename has been set after a
        download where it was not set before the download)
        """
        d = db.load_episode(self.url)
        if d is not None:
            self.update_from_dict(d)

        return self

    @staticmethod
    def from_feedparser_entry( entry, channel):
        episode = PodcastEpisode( channel)

        episode.title = entry.get( 'title', util.get_first_line( util.remove_html_tags( entry.get( 'summary', ''))))
        episode.link = entry.get( 'link', '')
        episode.description = ''

        # Get the episode description (prefer summary, then subtitle)
        for key in ('summary', 'subtitle', 'link'):
            if key in entry:
                episode.description = entry[key]
            if episode.description:
                break

        episode.guid = entry.get( 'id', '')
        if entry.get( 'updated_parsed', None):
            episode.pubDate = rfc822.mktime_tz(entry.updated_parsed+(0,))

        if episode.title == '':
            log( 'Warning: Episode has no title, adding anyways.. (Feed Is Buggy!)', sender = episode)

        enclosure = None
        if hasattr(entry, 'enclosures') and len(entry.enclosures) > 0:
            enclosure = entry.enclosures[0]
            if len(entry.enclosures) > 1:
                for e in entry.enclosures:
                    if hasattr( e, 'href') and hasattr( e, 'length') and hasattr( e, 'type') and (e.type.startswith('audio/') or e.type.startswith('video/')):
                        if util.normalize_feed_url(e.href) is not None:
                            log( 'Selected enclosure: %s', e.href, sender = episode)
                            enclosure = e
                            break
            episode.url = util.normalize_feed_url( enclosure.get( 'href', ''))
        elif hasattr(entry, 'link'):
            (filename, extension) = util.filename_from_url(entry.link)
            if extension == '' and hasattr( entry, 'type'):
                extension = util.extension_from_mimetype(e.type)
            file_type = util.file_type_by_extension(extension)
            if file_type is not None:
                log('Adding episode with link to file type "%s".', file_type, sender=episode)
                episode.url = entry.link

        # YouTube specific
        if not episode.url and hasattr(entry, 'links') and len(entry.links) and hasattr(entry.links[0], 'href'):
            episode.url = entry.links[0].href

        if not episode.url:
            log('Episode has no URL')
            log('Episode: %s', episode)
            log('Entry: %s', entry)
            # This item in the feed has no downloadable enclosure
            return None

        metainfo = None
        if not episode.pubDate:
            metainfo = util.get_episode_info_from_url(episode.url)
            if 'pubdate' in metainfo:
                try:
                    episode.pubDate = int(float(metainfo['pubdate']))
                except:
                    log('Cannot convert pubDate "%s" in from_feedparser_entry.', str(metainfo['pubdate']), traceback=True)

        if hasattr(enclosure, 'length'):
            try:
                episode.length = int(enclosure.length)
                if episode.length == 0:
                    raise ValueError('Zero-length is not acceptable')
            except ValueError, ve:
                log('Invalid episode length: %s (%s)', enclosure.length, ve.message)
                episode.length = -1

        if hasattr( enclosure, 'type'):
            episode.mimetype = enclosure.type

        if episode.title == '':
            ( filename, extension ) = os.path.splitext( os.path.basename( episode.url))
            episode.title = filename

        return episode


    def __init__( self, channel):
        # Used by Storage for faster saving
        self.id = None
        self.url = ''
        self.title = ''
        self.length = 0
        self.mimetype = 'application/octet-stream'
        self.guid = ''
        self.description = ''
        self.link = ''
        self.channel = channel
        self.pubDate = 0
        self.filename = None
        self.auto_filename = 1 # automatically generated filename

        self.state = db.STATE_NORMAL
        self.is_played = False
        self.is_locked = channel.channel_is_locked

    def save(self):
        if self.state != db.STATE_DOWNLOADED and self.file_exists():
            self.state = db.STATE_DOWNLOADED
        db.save_episode(self)

    def set_state(self, state):
        self.state = state
        db.mark_episode(self.url, state=self.state, is_played=self.is_played, is_locked=self.is_locked)

    def mark(self, state=None, is_played=None, is_locked=None):
        if state is not None:
            self.state = state
        if is_played is not None:
            self.is_played = is_played
        if is_locked is not None:
            self.is_locked = is_locked
        db.mark_episode(self.url, state=state, is_played=is_played, is_locked=is_locked)

    def mark_downloaded(self, save=False):
        self.state = db.STATE_DOWNLOADED
        self.is_played = False
        if save:
            self.save()
            db.commit()

    @property
    def title_and_description(self):
        """
        Returns Pango markup for displaying in a TreeView, and
        disables the description when the config variable
        "episode_list_descriptions" is not set.
        """
        if gl.config.episode_list_descriptions and gpodder.interface != gpodder.MAEMO:
            return '%s\n<small>%s</small>' % (saxutils.escape(self.title), saxutils.escape(self.one_line_description()))
        else:
            return saxutils.escape(self.title)

    def age_in_days(self):
        return util.file_age_in_days(self.local_filename(create=False))

    def is_old(self):
        return self.age_in_days() > gl.config.episode_old_age
    
    def get_age_string(self):
        return util.file_age_to_string(self.age_in_days())

    age_prop = property(fget=get_age_string)

    def one_line_description( self):
        lines = util.remove_html_tags(self.description).strip().splitlines()
        if not lines or lines[0] == '':
            return _('No description available')
        else:
            return ' '.join(lines)

    def delete_from_disk(self):
        try:
            self.channel.delete_episode_by_url(self.url)
        except:
            log('Cannot delete episode from disk: %s', self.title, traceback=True, sender=self)

    @classmethod
    def find_unique_file_name(cls, url, filename, extension):
        current_try = util.sanitize_filename(filename, cls.MAX_FILENAME_LENGTH)+extension
        next_try_id = 2
        lookup_url = None

        while db.episode_filename_exists(current_try):
            if next_try_id == 2:
                # If we arrive here, current_try has a collision, so
                # try to resolve the URL for a better basename
                log('Filename collision: %s - trying to resolve...', current_try)
                url = util.get_real_url(url)
                (episode_filename, extension_UNUSED) = util.filename_from_url(url)
                current_try = util.sanitize_filename(episode_filename, cls.MAX_FILENAME_LENGTH)+extension
                if not db.episode_filename_exists(current_try) and current_try:
                    log('Filename %s is available - collision resolved.', current_try)
                    return current_try
                else:
                    log('Continuing search with %s as basename...', current_try)

            current_try = '%s (%d)%s' % (filename, next_try_id, extension)
            next_try_id += 1

        return current_try

    def local_filename(self, create, force_update=False, check_only=False):
        """Get (and possibly generate) the local saving filename

        Pass create=True if you want this function to generate a
        new filename if none exists. You only want to do this when
        planning to create/download the file after calling this function.

        Normally, you should pass create=False. This will only
        create a filename when the file already exists from a previous
        version of gPodder (where we used md5 filenames). If the file
        does not exist (and the filename also does not exist), this
        function will return None.

        If you pass force_update=True to this function, it will try to
        find a new (better) filename and move the current file if this
        is the case. This is useful if (during the download) you get
        more information about the file, e.g. the mimetype and you want
        to include this information in the file name generation process.

        If check_only=True is passed to this function, it will never try
        to rename the file, even if would be a good idea. Use this if you
        only want to check if a file exists.

        The generated filename is stored in the database for future access.
        """
        ext = self.extension().encode('utf-8', 'ignore')

        # For compatibility with already-downloaded episodes, we
        # have to know md5 filenames if they are downloaded already
        urldigest = hashlib.md5(self.url).hexdigest()

        if not create and self.filename is None:
            urldigest_filename = os.path.join(self.channel.save_dir, urldigest+ext)
            if os.path.exists(urldigest_filename):
                # The file exists, so set it up in our database
                log('Recovering pre-0.15.0 file: %s', urldigest_filename, sender=self)
                self.filename = urldigest+ext
                self.auto_filename = 1
                self.save()
                return urldigest_filename
            return None

        # We only want to check if the file exists, so don't try to
        # rename the file, even if it would be reasonable. See also:
        # http://bugs.gpodder.org/attachment.cgi?id=236
        if check_only:
            if self.filename is None:
                return None
            else:
                return os.path.join(self.channel.save_dir, self.filename)

        if self.filename is None or force_update or (self.auto_filename and self.filename == urldigest+ext):
            # Try to find a new filename for the current file
            (episode_filename, extension_UNUSED) = util.filename_from_url(self.url)
            fn_template = util.sanitize_filename(episode_filename, self.MAX_FILENAME_LENGTH)

            if 'redirect' in fn_template:
                # This looks like a redirection URL - force URL resolving!
                log('Looks like a redirection to me: %s', self.url, sender=self)
                url = util.get_real_url(self.url)
                log('Redirection resolved to: %s', url, sender=self)
                (episode_filename, extension_UNUSED) = util.filename_from_url(url)
                fn_template = util.sanitize_filename(episode_filename, self.MAX_FILENAME_LENGTH)

            # Use the video title for YouTube downloads
            for yt_url in ('http://youtube.com/', 'http://www.youtube.com/'):
                if self.url.startswith(yt_url):
                    fn_template = self.title

            # If the basename is empty, use the md5 hexdigest of the URL
            if len(fn_template) == 0 or fn_template.startswith('redirect.'):
                log('Report to bugs.gpodder.org: Podcast at %s with episode URL: %s', self.channel.url, self.url, sender=self)
                fn_template = urldigest

            # Find a unique filename for this episode
            wanted_filename = self.find_unique_file_name(self.url, fn_template, ext)

            # We populate the filename field the first time - does the old file still exist?
            if self.filename is None and os.path.exists(os.path.join(self.channel.save_dir, urldigest+ext)):
                log('Found pre-0.15.0 downloaded file: %s', urldigest, sender=self)
                self.filename = urldigest+ext

            # The old file exists, but we have decided to want a different filename
            if self.filename is not None and wanted_filename != self.filename:
                # there might be an old download folder crawling around - move it!
                new_file_name = os.path.join(self.channel.save_dir, wanted_filename)
                old_file_name = os.path.join(self.channel.save_dir, self.filename)
                if os.path.exists(old_file_name) and not os.path.exists(new_file_name):
                    log('Renaming %s => %s', old_file_name, new_file_name, sender=self)
                    os.rename(old_file_name, new_file_name)
                elif force_update and not os.path.exists(old_file_name):
                    # When we call force_update, the file might not yet exist when we
                    # call it from the downloading code before saving the file
                    log('Choosing new filename: %s', new_file_name, sender=self)
                else:
                    log('Warning: %s exists or %s does not.', new_file_name, old_file_name, sender=self)
            log('Updating filename of %s to "%s".', self.url, wanted_filename, sender=self)
            self.filename = wanted_filename
            self.save()

        return os.path.join(self.channel.save_dir, self.filename)

    def extension( self):
         ( filename, ext ) = util.filename_from_url(self.url)
         # if we can't detect the extension from the url fallback on the mimetype
         if ext == '' or util.file_type_by_extension(ext) is None:
             ext = util.extension_from_mimetype(self.mimetype)
             #log('Getting extension from mimetype for: %s  (mimetype: %s)' % (self.title, ext), sender=self)
         return ext

    def mark_new(self):
        self.state = db.STATE_NORMAL
        self.is_played = False
        db.mark_episode(self.url, state=self.state, is_played=self.is_played)

    def mark_old(self):
        self.is_played = True
        db.mark_episode(self.url, is_played=True)

    def file_exists(self):
        filename = self.local_filename(create=False, check_only=True)
        if filename is None:
            return False
        else:
            return os.path.exists(filename)

    def was_downloaded(self, and_exists=False):
        if self.state != db.STATE_DOWNLOADED:
            return False
        if and_exists and not self.file_exists():
            return False
        return True

    def sync_filename( self):
        if gl.config.custom_sync_name_enabled:
            if '{channel' in gl.config.custom_sync_name:
                log('Fixing OLD syntax {channel.*} => {podcast.*} in custom_sync_name.', sender=self)
                gl.config.custom_sync_name = gl.config.custom_sync_name.replace('{channel.', '{podcast.')
            return util.object_string_formatter(gl.config.custom_sync_name, episode=self, podcast=self.channel)
        else:
            return self.title

    def file_type( self):
        return util.file_type_by_extension( self.extension() )

    @property
    def basename( self):
        return os.path.splitext( os.path.basename( self.url))[0]
    
    @property
    def published( self):
        """
        Returns published date as YYYYMMDD (or 00000000 if not available)
        """
        try:
            return datetime.datetime.fromtimestamp(self.pubDate).strftime('%Y%m%d')
        except:
            log( 'Cannot format pubDate for "%s".', self.title, sender = self)
            return '00000000'

    @property
    def pubtime(self):
        """
        Returns published time as HHMM (or 0000 if not available)
        """
        try:
            return datetime.datetime.fromtimestamp(self.pubDate).strftime('%H%M')
        except:
            log('Cannot format pubDate (time) for "%s".', self.title, sender=self)
            return '0000'
    
    def cute_pubdate(self):
        result = util.format_date(self.pubDate)
        if result is None:
            return '(%s)' % _('unknown')
        else:
            return result
    
    pubdate_prop = property(fget=cute_pubdate)

    def calculate_filesize( self):
        filename = self.local_filename(create=False)
        if filename is None:
            log('calculate_filesized called, but filename is None!', sender=self)
        try:
            self.length = os.path.getsize(filename)
        except:
            log( 'Could not get filesize for %s.', self.url)

    def get_filesize_string(self):
        return util.format_filesize(self.length)

    filesize_prop = property(fget=get_filesize_string)

    def get_channel_title( self):
        return self.channel.title

    channel_prop = property(fget=get_channel_title)

    def get_played_string( self):
        if not self.is_played:
            return _('Unplayed')
        
        return ''

    played_prop = property(fget=get_played_string)
    
    def is_duplicate( self, episode ):
        if self.title == episode.title and self.pubDate == episode.pubDate:
            log('Possible duplicate detected: %s', self.title)
            return True
        return False


def update_channel_model_by_iter( model, iter, channel,
        cover_cache=None, max_width=0, max_height=0, initialize_all=False):

    count_downloaded = channel.stat(state=db.STATE_DOWNLOADED)
    count_new = channel.stat(state=db.STATE_NORMAL, is_played=False)
    count_unplayed = channel.stat(state=db.STATE_DOWNLOADED, is_played=False)

    channel.iter = iter
    if initialize_all:
        model.set(iter, 0, channel.url)

    model.set(iter, 1, channel.title)
    title_markup = saxutils.escape(channel.title)
    description_markup = saxutils.escape(util.get_first_line(channel.description) or _('No description available'))
    d = []
    if count_new:
        d.append('<span weight="bold">')
    d.append(title_markup)
    if count_new:
        d.append('</span>')

    description = ''.join(d+['\n', '<small>', description_markup, '</small>'])
    model.set(iter, 2, description)

    if channel.parse_error:
        model.set(iter, 6, str(channel.parse_error))
    else:
        model.set(iter, 6, None)

    if count_unplayed > 0 or count_downloaded > 0:
        model.set(iter, 3, draw.draw_pill_pixbuf(str(count_unplayed), str(count_downloaded)))
        model.set(iter, 7, True)
    else:
        model.set(iter, 7, False)

    if initialize_all:
        # Load the cover if we have it, but don't download
        # it if it's not available (to avoid blocking here)
        pixbuf = services.cover_downloader.get_cover(channel, avoid_downloading=True)
        new_pixbuf = None
        if pixbuf is not None:
            new_pixbuf = util.resize_pixbuf_keep_ratio(pixbuf, max_width, max_height, channel.url, cover_cache)
        model.set(iter, 5, new_pixbuf or pixbuf)

def channels_to_model(channels, cover_cache=None, max_width=0, max_height=0):
    new_model = gtk.ListStore( str, str, str, gtk.gdk.Pixbuf, int,
        gtk.gdk.Pixbuf, str, bool, str )

    urls = []
    for channel in channels:
        update_channel_model_by_iter(new_model, new_model.append(), channel,
            cover_cache, max_width, max_height, True)
        urls.append(channel.url)

    return (new_model, urls)


def load_channels():
    return db.load_channels(factory=PodcastChannel.create_from_dict)

def update_channels(callback_proc=None, callback_error=None, is_cancelled_cb=None):
    log('Updating channels....')

    channels = load_channels()
    count = 0

    for channel in channels:
        if is_cancelled_cb is not None and is_cancelled_cb():
            return channels
        callback_proc and callback_proc(count, len(channels))
        channel.update()
        count += 1

    return channels

def save_channels( channels):
    exporter = opml.Exporter(gl.channel_opml_file)
    return exporter.write(channels)

def can_restore_from_opml():
    try:
        if len(opml.Importer(gl.channel_opml_file).items):
            return gl.channel_opml_file
    except:
        return None



class LocalDBReader( object):
    """
    DEPRECATED - Only used for migration to SQLite
    """
    def __init__( self, url):
        self.url = url

    def get_text( self, nodelist):
        return ''.join( [ node.data for node in nodelist if node.nodeType == node.TEXT_NODE ])

    def get_text_by_first_node( self, element, name):
        return self.get_text( element.getElementsByTagName( name)[0].childNodes)
    
    def get_episode_from_element( self, channel, element):
        episode = PodcastEpisode(channel)
        episode.title = self.get_text_by_first_node( element, 'title')
        episode.description = self.get_text_by_first_node( element, 'description')
        episode.url = self.get_text_by_first_node( element, 'url')
        episode.link = self.get_text_by_first_node( element, 'link')
        episode.guid = self.get_text_by_first_node( element, 'guid')

        if not episode.guid:
            for k in ('url', 'link'):
                if getattr(episode, k) is not None:
                    episode.guid = getattr(episode, k)
                    log('Notice: episode has no guid, using %s', episode.guid)
                    break
        try:
            episode.pubDate = float(self.get_text_by_first_node(element, 'pubDate'))
        except:
            log('Looks like you have an old pubDate in your LocalDB -> converting it')
            episode.pubDate = self.get_text_by_first_node(element, 'pubDate')
            log('FYI: pubDate value is: "%s"', episode.pubDate, sender=self)
            pubdate = feedparser._parse_date(episode.pubDate)
            if pubdate is None:
                log('Error converting the old pubDate - sorry!', sender=self)
                episode.pubDate = 0
            else:
                log('PubDate converted successfully - yay!', sender=self)
                episode.pubDate = time.mktime(pubdate)
        try:
            episode.mimetype = self.get_text_by_first_node( element, 'mimetype')
        except:
            log('No mimetype info for %s', episode.url, sender=self)
        episode.calculate_filesize()
        return episode

    def load_and_clean( self, filename):
        """
        Clean-up a LocalDB XML file that could potentially contain
        "unbound prefix" XML elements (generated by the old print-based
        LocalDB code). The code removes those lines to make the new 
        DOM parser happy.

        This should be removed in a future version.
        """
        lines = []
        for line in open(filename).read().split('\n'):
            if not line.startswith('<gpodder:info'):
                lines.append( line)

        return '\n'.join( lines)
    
    def read( self, filename):
        doc = xml.dom.minidom.parseString( self.load_and_clean( filename))
        rss = doc.getElementsByTagName('rss')[0]
        
        channel_element = rss.getElementsByTagName('channel')[0]

        channel = PodcastChannel(url=self.url)
        channel.title = self.get_text_by_first_node( channel_element, 'title')
        channel.description = self.get_text_by_first_node( channel_element, 'description')
        channel.link = self.get_text_by_first_node( channel_element, 'link')

        episodes = []
        for episode_element in rss.getElementsByTagName('item'):
            episode = self.get_episode_from_element( channel, episode_element)
            episodes.append(episode)

        return episodes

