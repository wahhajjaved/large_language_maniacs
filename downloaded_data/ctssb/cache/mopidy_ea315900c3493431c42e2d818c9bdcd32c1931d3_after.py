from copy import copy
import logging
import random
import time

from mopidy import settings
from mopidy.models import Playlist
from mopidy.utils import get_class

logger = logging.getLogger('mopidy.backends.base')

class BaseBackend(object):
    def __init__(self, core_queue=None, mixer=None):
        self.core_queue = core_queue
        if mixer is not None:
            self.mixer = mixer
        else:
            self.mixer = get_class(settings.MIXER)()

    #: A :class:`multiprocessing.Queue` which can be used by e.g. library
    #: callbacks to send messages to the core.
    core_queue = None

    #: The current playlist controller. An instance of
    #: :class:`BaseCurrentPlaylistController`.
    current_playlist = None

    #: The library controller. An instance of :class:`BaseLibraryController`.
    library = None

    #: The sound mixer. An instance of :class:`mopidy.mixers.BaseMixer`.
    mixer = None

    #: The playback controller. An instance of :class:`BasePlaybackController`.
    playback = None

    #: The stored playlists controller. An instance of
    #: :class:`BaseStoredPlaylistsController`.
    stored_playlists = None

    #: List of URI prefixes this backend can handle.
    uri_handlers = []

    def destroy(self):
        if self.current_playlist:
            self.current_playlist.destroy()

        if self.library:
            self.library.destroy()

        if self.mixer:
            self.mixer.destroy()

        if self.playback:
            self.playback.destroy()

        if self.stored_playlists:
            self.stored_playlists.destroy()

class BaseCurrentPlaylistController(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    """

    #: The current playlist version. Integer which is increased every time the
    #: current playlist is changed. Is not reset before the MPD server is
    #: restarted.
    version = 0

    def __init__(self, backend):
        self.backend = backend
        self.playlist = Playlist()

    @property
    def playlist(self):
        """The currently loaded :class:`mopidy.models.Playlist`."""
        return copy(self._playlist)

    @playlist.setter
    def playlist(self, new_playlist):
        self._playlist = new_playlist
        self.version += 1

    def add(self, track, at_position=None):
        """
        Add the track to the end of, or at the given position in the current
        playlist.

        :param track: track to add
        :type track: :class:`mopidy.models.Track`
        :param at_position: position in current playlist to add track
        :type at_position: int or :class:`None`
        """
        tracks = self.playlist.tracks
        if at_position is not None:
            tracks.insert(at_position, track)
        else:
            tracks.append(track)
        self.playlist = self.playlist.with_(tracks=tracks)

    def clear(self):
        """Clear the current playlist."""
        self.backend.playback.stop()
        self.backend.playback.current_track = None
        self.playlist = Playlist()

    def get(self, **criteria):
        """
        Get track by given criterias from current playlist.

        Raises :exc:`LookupError` if a unique match is not found.

        Examples::

            get(id=1)               # Returns track with ID 1
            get(uri='xyz')          # Returns track with URI 'xyz'
            get(id=1, uri='xyz')    # Returns track with ID 1 and URI 'xyz'

        :param criteria: on or more criteria to match by
        :type criteria: dict
        :rtype: :class:`mopidy.models.Track`
        """
        matches = self._playlist.tracks
        for (key, value) in criteria.iteritems():
            matches = filter(lambda t: getattr(t, key) == value, matches)
        if len(matches) == 1:
            return matches[0]
        criteria_string = ', '.join(
            ['%s=%s' % (k, v) for (k, v) in criteria.iteritems()])
        if len(matches) == 0:
            raise LookupError(u'"%s" match no tracks' % criteria_string)
        else:
            raise LookupError(u'"%s" match multiple tracks' % criteria_string)

    def load(self, playlist):
        """
        Replace the current playlist with the given playlist.

        :param playlist: playlist to load
        :type playlist: :class:`mopidy.models.Playlist`
        """
        self.playlist = playlist
        self.backend.playback.new_playlist_loaded_callback()

    def move(self, start, end, to_position):
        """
        Move the tracks in the slice ``[start:end]`` to ``to_position``.

        :param start: position of first track to move
        :type start: int
        :param end: position after last track to move
        :type end: int
        :param to_position: new position for the tracks
        :type to_position: int
        """
        if start == end:
            end += 1

        tracks = self.playlist.tracks
        new_tracks = tracks[:start] + tracks[end:]
        for track in tracks[start:end]:
            new_tracks.insert(to_position, track)
            to_position += 1
        self.playlist = self.playlist.with_(tracks=new_tracks)

    def remove(self, track):
        """
        Remove the track from the current playlist.

        :param track: track to remove
        :type track: :class:`mopidy.models.Track`
        """
        tracks = self.playlist.tracks

        if track not in tracks:
            return

        position = tracks.index(track)
        del tracks[position]
        self.playlist = self.playlist.with_(tracks=tracks)

    def shuffle(self, start=None, end=None):
        """
        Shuffles the entire playlist. If ``start`` and ``end`` is given only
        shuffles the slice ``[start:end]``.

        :param start: position of first track to shuffle
        :type start: int or :class:`None`
        :param end: position after last track to shuffle
        :type end: int or :class:`None`
        """
        tracks = self.playlist.tracks
        before = tracks[:start or 0]
        shuffled = tracks[start:end]
        after = tracks[end or len(tracks):]
        random.shuffle(shuffled)
        self.playlist = self.playlist.with_(tracks=before+shuffled+after)

    def destroy(self):
        pass


class BaseLibraryController(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    """

    def __init__(self, backend):
        self.backend = backend

    def find_exact(self, type, query):
        """
        Find tracks in the library where ``type`` matches ``query`` exactly.

        :param type: 'track', 'artist', or 'album'
        :type type: string
        :param query: the search query
        :type query: string
        :rtype: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def lookup(self, uri):
        """
        Lookup track with given URI.

        :param uri: track URI
        :type uri: string
        :rtype: :class:`mopidy.models.Track`
        """
        raise NotImplementedError

    def refresh(self, uri=None):
        """
        Refresh library. Limit to URI and below if an URI is given.

        :param uri: directory or track URI
        :type uri: string
        """
        raise NotImplementedError

    def search(self, type, query):
        """
        Search the library for tracks where ``type`` contains ``query``.

        :param type: 'track', 'artist', 'album', 'uri', and 'any'
        :type type: string
        :param query: the search query
        :type query: string
        :rtype: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def destroy(self):
        pass


class BasePlaybackController(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    """

    #: Constant representing the paused state.
    PAUSED = u'paused'

    #: Constant representing the playing state.
    PLAYING = u'playing'

    #: Constant representing the stopped state.
    STOPPED = u'stopped'

    #: :class:`True`
    #:     Tracks are removed from the playlist when they have been played.
    #: :class:`False`
    #:     Tracks are not removed from the playlist.
    consume = False

    #: The currently playing or selected :class:`mopidy.models.Track`.
    current_track = None

    #: :class:`True`
    #:     Tracks are selected at random from the playlist.
    #: :class:`False`
    #:     Tracks are played in the order of the playlist.
    random = False

    #: :class:`True`
    #:     The current track is played repeatedly.
    #: :class:`False`
    #:     The current track is played once.
    repeat = False

    #: :class:`True`
    #:     Playback is stopped after current song, unless in repeat mode.
    #: :class:`False`
    #:     Playback continues after current song.
    single = False

    def __init__(self, backend):
        self.backend = backend
        self._state = self.STOPPED
        self._shuffled = []
        self._first_shuffle = True

    @property
    def next_track(self):
        """
        The next :class:`mopidy.models.Track` in the playlist.

        For normal playback this is the next track in the playlist. If repeat
        is enabled the next track can loop around the playlist. When random is
        enabled this should be a random track, all tracks should be played once
        before the list repeats.
        """
        tracks = self.backend.current_playlist.playlist.tracks

        if not tracks:
            return None

        if self.random and not self._shuffled:
            if self.repeat or self._first_shuffle:
                self._shuffled = tracks
                random.shuffle(self._shuffled)
                self._first_shuffle = False

        if self._shuffled:
            return self._shuffled[0]

        if self.current_track is None:
            return tracks[0]

        if self.repeat:
            return tracks[(self.playlist_position + 1) % len(tracks)]

        try:
            return tracks[self.playlist_position + 1]
        except IndexError:
            return None

    @property
    def playlist_position(self):
        """The position in the current playlist."""
        if self.current_track is None:
            return None
        try:
            return self.backend.current_playlist.playlist.tracks.index(
                self.current_track)
        except ValueError:
            return None

    @property
    def previous_track(self):
        """
        The previous :class:`mopidy.models.Track` in the playlist.

        For normal playback this is the next track in the playlist. If random
        and/or consume is enabled it should return the current track instead.
        """
        if self.repeat or self.consume or self.random:
            return self.current_track

        if self.current_track is None or self.playlist_position == 0:
            return None

        try:
            return self.backend.current_playlist.playlist.tracks[
                self.playlist_position - 1]
        except IndexError:
            return None

    @property
    def state(self):
        """
        The playback state. Must be :attr:`PLAYING`, :attr:`PAUSED`, or
        :attr:`STOPPED`.

        Possible states and transitions:

        .. digraph:: state_transitions

            "STOPPED" -> "PLAYING" [ label="play" ]
            "PLAYING" -> "STOPPED" [ label="stop" ]
            "PLAYING" -> "PAUSED" [ label="pause" ]
            "PLAYING" -> "PLAYING" [ label="play" ]
            "PAUSED" -> "PLAYING" [ label="resume" ]
            "PAUSED" -> "STOPPED" [ label="stop" ]
        """
        return self._state

    @state.setter
    def state(self, new_state):
        (old_state, self._state) = (self.state, new_state)
        logger.debug(u'Changing state: %s -> %s', old_state, new_state)
        # FIXME _play_time stuff assumes backend does not have a better way of
        # handeling this stuff :/
        if (old_state in (self.PLAYING, self.STOPPED)
                and new_state == self.PLAYING):
            self._play_time_start()
        elif old_state == self.PLAYING and new_state == self.PAUSED:
            self._play_time_pause()
        elif old_state == self.PAUSED and new_state == self.PLAYING:
            self._play_time_resume()

    @property
    def time_position(self):
        """Time position in milliseconds."""
        if self.state == self.PLAYING:
            time_since_started = (self._current_wall_time -
                self._play_time_started)
            return self._play_time_accumulated + time_since_started
        elif self.state == self.PAUSED:
            return self._play_time_accumulated
        elif self.state == self.STOPPED:
            return 0

    def _play_time_start(self):
        self._play_time_accumulated = 0
        self._play_time_started = self._current_wall_time

    def _play_time_pause(self):
        time_since_started = self._current_wall_time - self._play_time_started
        self._play_time_accumulated += time_since_started

    def _play_time_resume(self):
        self._play_time_started = self._current_wall_time

    @property
    def _current_wall_time(self):
        return int(time.time() * 1000)

    @property
    def volume(self):
    # FIXME Shouldn't we just be using the backend mixer directly? ie can we
    # remove this?
        """
        The audio volume as an int in the range [0, 100].

        :class:`None` if unknown.
        """
        return self.backend.mixer.volume

    @volume.setter
    def volume(self, volume):
        self.backend.mixer.volume = volume

    def end_of_track_callback(self):
        """Tell the playback controller that end of track is reached."""
        if self.next_track is not None:
            self.next()
        else:
            self.stop()
            self.current_track = None

    def new_playlist_loaded_callback(self):
        """Tell the playback controller that a new playlist has been loaded."""
        self.current_track = None
        self._first_shuffle = True
        self._shuffled = []

        if self.state == self.PLAYING:
            if self.backend.current_playlist.playlist.length > 0:
                self.play()
            else:
                self.stop()
        elif self.state == self.PAUSED:
            self.stop()

    def next(self):
        """Play the next track."""
        original_track = self.current_track

        if self.state == self.STOPPED:
            return
        elif self.next_track is not None and self._next(self.next_track):
            self.current_track = self.next_track
            self.state = self.PLAYING
        elif self.next_track is None:
            self.stop()

        if self.consume:
            self.backend.current_playlist.remove(original_track)

        if self.random and self.current_track in self._shuffled:
            self._shuffled.remove(self.current_track)

    def _next(self, track):
        return self._play(track)

    def pause(self):
        """Pause playback."""
        if self.state == self.PLAYING and self._pause():
            self.state = self.PAUSED

    def _pause(self):
        raise NotImplementedError

    def play(self, track=None):
        """
        Play the given track or the currently active track.

        :param track: track to play
        :type track: :class:`mopidy.models.Track` or :class:`None`
        """

        if not track and not self.current_track:
            track = self.next_track

        if self.state == self.PAUSED and track is None:
            self.resume()
        elif track is not None and self._play(track):
            self.current_track = track
            self.state = self.PLAYING

        if self.random and self.current_track in self._shuffled:
            self._shuffled.remove(self.current_track)

    def _play(self, track):
        raise NotImplementedError

    def previous(self):
        """Play the previous track."""
        if (self.previous_track is not None
                and self.state != self.STOPPED
                and self._previous(self.previous_track)):
            self.current_track = self.previous_track
            self.state = self.PLAYING

    def _previous(self, track):
        return self._play(track)

    def resume(self):
        """If paused, resume playing the current track."""
        if self.state == self.PAUSED and self._resume():
            self.state = self.PLAYING

    def _resume(self):
        raise NotImplementedError

    def seek(self, time_position):
        """
        Seeks to time position given in milliseconds.

        :param time_position: time position in milliseconds
        :type time_position: int
        """
        if self.state == self.STOPPED:
            self.play()
        elif self.state == self.PAUSED:
            self.resume()

        if time_position < 0:
            time_position = 0
        elif self.current_track and time_position > self.current_track.length:
            self.next()
            return

        self._seek(time_position)

    def _seek(self, time_position):
        raise NotImplementedError

    def stop(self):
        """Stop playing."""
        if self.state != self.STOPPED and self._stop():
            self.state = self.STOPPED

    def _stop(self):
        raise NotImplementedError

    def destroy(self):
        pass


class BaseStoredPlaylistsController(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    """

    def __init__(self, backend):
        self.backend = backend
        self._playlists = []

    @property
    def playlists(self):
        """List of :class:`mopidy.models.Playlist`."""
        return copy(self._playlists)

    @playlists.setter
    def playlists(self, playlists):
        self._playlists = playlists

    def create(self, name):
        """
        Create a new playlist.

        :param name: name of the new playlist
        :type name: string
        :rtype: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def delete(self, playlist):
        """
        Delete playlist.

        :param playlist: the playlist to delete
        :type playlist: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def get(self, **criteria):
        """
        Get playlist by given criterias from the set of stored playlists.

        Raises :exc:`LookupError` if a unique match is not found.

        Examples::

            get(name='a')            # Returns track with name 'a'
            get(uri='xyz')           # Returns track with URI 'xyz'
            get(name='a', uri='xyz') # Returns track with name 'a' and URI 'xyz'

        :param criteria: on or more criteria to match by
        :type criteria: dict
        :rtype: :class:`mopidy.models.Playlist`
        """
        matches = self._playlists
        for (key, value) in criteria.iteritems():
            matches = filter(lambda p: getattr(p, key) == value, matches)
        if len(matches) == 1:
            return matches[0]
        criteria_string = ', '.join(
            ['%s=%s' % (k, v) for (k, v) in criteria.iteritems()])
        if len(matches) == 0:
            raise LookupError('"%s" match no playlists' % criteria_string)
        else:
            raise LookupError('"%s" match multiple playlists' % criteria_string)

    def lookup(self, uri):
        """
        Lookup playlist with given URI in both the set of stored playlists and
        in any other playlist sources.

        :param uri: playlist URI
        :type uri: string
        :rtype: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def refresh(self):
        """Refresh stored playlists."""
        raise NotImplementedError

    def rename(self, playlist, new_name):
        """
        Rename playlist.

        :param playlist: the playlist
        :type playlist: :class:`mopidy.models.Playlist`
        :param new_name: the new name
        :type new_name: string
        """
        raise NotImplementedError

    def save(self, playlist):
        """
        Save the playlist to the set of stored playlists.

        :param playlist: the playlist
        :type playlist: :class:`mopidy.models.Playlist`
        """
        raise NotImplementedError

    def search(self, query):
        """
        Search for playlists whose name contains ``query``.

        :param query: query to search for
        :type query: string
        :rtype: list of :class:`mopidy.models.Playlist`
        """
        return filter(lambda p: query in p.name, self._playlists)

    def destroy(self):
        pass
