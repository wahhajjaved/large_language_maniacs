from copy import copy
import logging

logger = logging.getLogger('mopidy.backends.base')

class BaseStoredPlaylistsController(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    :param provider: provider the controller should use
    :type provider: instance of :class:`BaseStoredPlaylistsProvider`
    """

    def __init__(self, backend, provider):
        self.backend = backend
        self.provider = provider

    def destroy(self):
        """Cleanup after component."""
        self.provider.destroy()

    @property
    def playlists(self):
        """
        Currently stored playlists.

        Read/write. List of :class:`mopidy.models.Playlist`.
        """
        return self.provider.playlists

    @playlists.setter
    def playlists(self, playlists):
        self.provider.playlists = playlists

    def create(self, name):
        """
        Create a new playlist.

        :param name: name of the new playlist
        :type name: string
        :rtype: :class:`mopidy.models.Playlist`
        """
        return self.provider.create(name)

    def delete(self, playlist):
        """
        Delete playlist.

        :param playlist: the playlist to delete
        :type playlist: :class:`mopidy.models.Playlist`
        """
        return self.provider.delete(playlist)

    def get(self, **criteria):
        """
        Get playlist by given criterias from the set of stored playlists.

        Raises :exc:`LookupError` if a unique match is not found.

        Examples::

            get(name='a')            # Returns track with name 'a'
            get(uri='xyz')           # Returns track with URI 'xyz'
            get(name='a', uri='xyz') # Returns track with name 'a' and URI
                                     # 'xyz'

        :param criteria: one or more criteria to match by
        :type criteria: dict
        :rtype: :class:`mopidy.models.Playlist`
        """
        matches = self.playlists
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
        return self.provider.lookup(uri)

    def refresh(self):
        """
        Refresh the stored playlists in
        :attr:`mopidy.backends.base.BaseStoredPlaylistsController.playlists`.
        """
        return self.provider.refresh()

    def rename(self, playlist, new_name):
        """
        Rename playlist.

        :param playlist: the playlist
        :type playlist: :class:`mopidy.models.Playlist`
        :param new_name: the new name
        :type new_name: string
        """
        return self.provider.rename(playlist, new_name)

    def save(self, playlist):
        """
        Save the playlist to the set of stored playlists.

        :param playlist: the playlist
        :type playlist: :class:`mopidy.models.Playlist`
        """
        return self.provider.save(playlist)


class BaseStoredPlaylistsProvider(object):
    """
    :param backend: backend the controller is a part of
    :type backend: :class:`BaseBackend`
    """

    def __init__(self, backend):
        self.backend = backend
        self._playlists = []

    def destroy(self):
        """
        Cleanup after component.

        *MAY be implemented by subclass.*
        """
        pass

    @property
    def playlists(self):
        """
        Currently stored playlists.

        Read/write. List of :class:`mopidy.models.Playlist`.
        """
        return copy(self._playlists)

    @playlists.setter
    def playlists(self, playlists):
        self._playlists = playlists

    def create(self, name):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.create`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

    def delete(self, playlist):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.delete`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

    def lookup(self, uri):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.lookup`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

    def refresh(self):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.refresh`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

    def rename(self, playlist, new_name):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.rename`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

    def save(self, playlist):
        """
        See :meth:`mopidy.backends.base.BaseStoredPlaylistsController.save`.

        *MUST be implemented by subclass.*
        """
        raise NotImplementedError

