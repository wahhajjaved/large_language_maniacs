#!usr/bin/env python2
# -*- coding: utf-8 -*-
# Name:        torrenter
# Author:      Roman Miroshnychenko aka Roman V. M.
# Created on:  13.12.2014
# Licence:     GPL v.3: http://www.gnu.org/copyleft/gpl.html
"""
Torrent client

The module implements a simple torrent client based on python-libtorrent library
and with torrent media streaming capability.
"""

import os
import time
import threading
import datetime
import cPickle as pickle
from collections import deque
from requests import get

try:
    import libtorrent
except ImportError:
    from python_libtorrent import get_libtorrent
    libtorrent = get_libtorrent()

print 'plugin.video.yatp. libtorrent version: {0}'.format(libtorrent.version)


def load_torrent(url):
        return get(url).content


class TorrenterError(Exception):
    """Custom exception"""
    pass


class Torrenter(object):
    """
    Torrenter class

    Implements a simple torrent client.
    """
    def __init__(self, start_port=6881, end_port=6891,
                 dl_speed_limit=0, ul_speed_limit=0, persistent=False, resume_dir=''):
        """
        Class constructor

        If persistent=False, Torrenter does not store any persistend data
        for torrents.
        :param start_port: int
        :param end_port: int
        :param dl_speed_limit: int - download speed limit in KB/s
        :param ul_speed_limit: int - uplpad speed lomit in KB/s
        :param persistent: bool - store persistent data
        :param resume_dir: str - the dir where session and torrents persistent data are stored.
        :return:
        """
        # torrents_pool is used to map torrent handles to their sha1 hexdigests
        # Item format {hexdigest: torr_handle}
        self._torrents_pool = {}
        # Use persistent storage for session and torrents info
        self._persistent = persistent
        # The directory where session and torrent data are stored
        self._resume_dir = os.path.abspath(resume_dir)
        # Worker threads
        self._add_torrent_thread = None
        # Signal events
        self._torrent_added = threading.Event()
        # Inter-thread data buffers.
        # deque containers for 1 items are used because deque.append operation is atomic.
        self._last_added_torrent = deque([None], 1)
        # Initialize session
        self._session = libtorrent.session()
        self._session.listen_on(start_port, end_port)
        if self._persistent:
            try:
                self._load_session_state()
            except TorrenterError:
                self._save_session_state()
        settings = self._session.get_settings()
        settings['cache_size'] = 256
        if dl_speed_limit or ul_speed_limit:
            settings['ignore_limits_on_local_network'] = False
            if dl_speed_limit > 0:
                settings['download_rate_limit'] = dl_speed_limit * 1024
            if ul_speed_limit > 0:
                settings['upload_rate_limit'] = ul_speed_limit * 1024
        self._session.set_settings(settings)
        self._session.add_dht_router('router.bittorrent.com', 6881)
        self._session.add_dht_router('router.utorrent.com', 6881)
        self._session.add_dht_router('router.bitcomet.com', 6881)
        self._session.start_dht()
        if self._persistent:
            self._load_torrents()

    def __del__(self):
        """
        Class destructor

        Always delete the Torrenter instance when
        exiting the main program.
        """
        try:
            self._add_torrent_thread.join()
        except (RuntimeError, AttributeError):
            pass
        if self._persistent:
            self.save_all_resume_data()
        del self._session

    def add_torrent(self, torrent, save_path, zero_priorities=False):
        """
        Add a torrent download

        :param torrent: str
        :param save_path: str
        :param zero_priorities: bool
        :return: dict {'name': str, 'info_hash': str, 'files': list}
        """
        self._torrent_added.clear()
        torr_handle = self._add_torrent(torrent, save_path)
        if self._persistent:
            self._save_torrent_info(torr_handle)
        result = {'name': torr_handle.name().decode('utf-8'), 'info_hash': str(torr_handle.info_hash())}
        torr_info = torr_handle.get_torrent_info()
        files = []
        for file_ in torr_info.files():
            files.append(file_.path.decode('utf-8'))
        result['files'] = files
        if zero_priorities:
            [torr_handle.piece_priority(piece, 0) for piece in xrange(torr_info.num_pieces())]
        self._last_added_torrent.append(result)
        self._torrent_added.set()

    def add_torrent_async(self, torrent, save_path, zero_priorities=False):
        """
        Add a torrent in a non-blocking way.

        This method will add a torrent in a separate thread. After calling the method,
        the caller should periodically check torrent_added flag and, when
        the flag is set, retrieve results from data_buffer.
        :param torrent: str - path to a .torrent file or a magnet link
        :param save_path: str - save path
        :param zero_priorities: bool
        :return:
        """
        self._add_torrent_thread = threading.Thread(target=self.add_torrent, args=(torrent, save_path, zero_priorities))
        self._add_torrent_thread.daemon = True
        self._add_torrent_thread.start()

    def _add_torrent(self, torrent, save_path, resume_data=None):
        """
        Add a torrent to the pool.

        :param torrent: str - the path to a .torrent file or a magnet link
        :param save_path: str - torrent save path
        :param resume_data: str - bencoded torrent resume data
        :return: object - torr_handle
        """
        add_torrent_params = {'save_path': os.path.abspath(save_path),
                              'storage_mode': libtorrent.storage_mode_t.storage_mode_sparse}
        if resume_data is not None:
            add_torrent_params['resume_data'] = resume_data
        if isinstance(torrent, dict):
            add_torrent_params['ti'] = libtorrent.torrent_info(torrent)
        elif torrent[:7] == 'magnet:':
            add_torrent_params['url'] = torrent
        elif torrent[:7] in ('http://', 'https:/'):
            # Here external http/https client is used in case if libtorrent module is compiled without OpenSSL
            add_torrent_params['ti'] = libtorrent.torrent_info(libtorrent.bdecode(load_torrent(torrent)))
        else:
            try:
                add_torrent_params['ti'] = libtorrent.torrent_info(os.path.abspath(torrent))
            except RuntimeError:
                raise TorrenterError('Invalid path to the .torrent file!')
        torr_handle = self._session.add_torrent(add_torrent_params)
        while not torr_handle.has_metadata():  # Wait until torrent metadata are populated
            time.sleep(0.1)
        # torr_handle.auto_managed(False)
        info_hash = str(torr_handle.info_hash())
        self._torrents_pool[info_hash] = torr_handle
        return torr_handle

    @staticmethod
    def check_piece_range(torr_handle, start_piece, end_piece):
        """
        Check if the range of pieces is downloaded

        :param torr_handle:
        :param start_piece:
        :param end_piece:
        :return:
        """
        result = True
        for piece in xrange(start_piece, end_piece + 1):
            if not torr_handle.have_piece(piece):
                result = False
                break
        return result

    def _get_torrent_status(self, info_hash):
        """
        Get torrent status

        :param info_hash: str
        :return: object status
        """
        try:
            torr_handle = self._torrents_pool[info_hash]
        except KeyError:
            raise TorrenterError('Invalid torrent hash!')
        if torr_handle.is_valid():
            torr_status = torr_handle.status()
        else:
            torr_status = None
        return torr_status

    def _get_torrent_info(self, info_hash):
        """
        Get torrent info

        :param info_hash: str
        :return: object torrent_info
        """
        try:
            torr_info = self._torrents_pool[info_hash].get_torrent_info()
        except KeyError:
            raise TorrenterError('Invalid torrent hash!')
        return torr_info

    def remove_torrent(self, info_hash, delete_files=False):
        """
        Remove a torrent from download

        :param info_hash: str
        :return:
        """
        try:
            self._session.remove_torrent(self._torrents_pool[info_hash], delete_files)
            del self._torrents_pool[info_hash]
            if self._persistent:
                os.remove(os.path.join(self._resume_dir, info_hash + '.resume'))
                os.remove(os.path.join(self._resume_dir, info_hash + '.torrent'))
        except (KeyError, OSError):
            raise TorrenterError('Invalid torrent hash or info files not found!')

    def _save_session_state(self):
        """
        Save session state

        :return:
        """
        if self._persistent:
            state_file = open(os.path.join(self._resume_dir, 'session.state'), mode='wb')
            pickle.dump(self._session.save_state(), state_file)
            state_file.close()
        else:
            raise TorrenterError('Trying to save the state of a non-persistent instance!')

    def _load_session_state(self):
        """
        Load session state

        :return:
        """
        try:
            state_file = open(os.path.join(self._resume_dir, 'session.state'), mode='rb')
        except IOError:
            raise TorrenterError('.state file not found!')
        self._session.load_state(pickle.load(state_file))
        state_file.close()

    def pause_torrent(self, info_hash, graceful_pause=1):
        """
        Pause a torrent
        :param info_hash: str
        :return:
        """
        try:
            self._torrents_pool[info_hash].pause(graceful_pause)
        except KeyError:
            raise TorrenterError('Invalid torrent hash!')

    def resume_torrent(self, info_hash):
        """
        Resume a torrent

        :param info_hash: str
        :return:
        """
        try:
            self._torrents_pool[info_hash].resume()
        except KeyError:
            raise TorrenterError('Invalid torrent hash!')

    def _save_resume_data(self, info_hash, force_save=False):
        """
        Save fast-resume data for a torrent.

        :param info_hash: str
        :return:
        """
        if self._persistent:
            torrent_handle = self._torrents_pool[info_hash]
            if torrent_handle.need_save_resume_data() or force_save:
                resume_data = libtorrent.bencode(torrent_handle.write_resume_data())
                meta_file = open(os.path.join(self._resume_dir, info_hash + '.resume'), mode='r+b')
                metadata = pickle.load(meta_file)
                metadata['resume_data'] = resume_data
                meta_file.seek(0)
                pickle.dump(metadata, meta_file)
                meta_file.truncate()
                meta_file.close()
        else:
            raise TorrenterError('Trying to save torrent metadata for a non-persistent instance!')

    def save_all_resume_data(self, force_save=False):
        """
        Save fast-resume data for all torrents

        :return:
        """
        if self._persistent:
            for key in self._torrents_pool.iterkeys():
                self._save_resume_data(key, force_save)
            self._session.save_state()
        else:
            raise TorrenterError('Trying to save torrent metadata for a non-persistent instance!')

    def _save_torrent_info(self, torr_handle):
        """
        Save torrent metatata and a .torrent file for resume.

        :param torr_handle: object - torrent handle
        :return:
        """
        if self._persistent:
            info_hash = str(torr_handle.info_hash())
            torr_filepath = os.path.join(self._resume_dir, info_hash + '.torrent')
            meta_filepath = os.path.join(self._resume_dir, info_hash + '.resume')
            torr_info = torr_handle.get_torrent_info()
            torr_file = libtorrent.create_torrent(torr_info)
            torr_content = torr_file.generate()
            torr_bencoded = libtorrent.bencode(torr_content)
            t_file = open(torr_filepath, 'wb')
            t_file.write(torr_bencoded)
            t_file.close()
            metadata = {'name': torr_handle.name(),
                        'info_hash': info_hash,
                        'save_path': torr_handle.save_path(),
                        'resume_data': None}
            m_file = open(meta_filepath, mode='wb')
            pickle.dump(metadata, m_file)
            m_file.close()
        else:
            raise TorrenterError('Trying to save torrent metadata for a non-persistent instance!')

    def _load_torrent_info(self, filepath):
        """
        Load torrent state from a pickle file and add the torrent to the pool.

        :param filepath: str
        :return:
        """
        m_file = open(filepath, mode='rb')
        metadata = pickle.load(m_file)
        m_file.close()
        torrent = os.path.join(self._resume_dir, metadata['info_hash'] + '.torrent')
        self._add_torrent(torrent, metadata['save_path'], metadata['resume_data'])

    def _load_torrents(self):
        """
        Load all torrents

        :return:
        """
        dir_listing = os.listdir(self._resume_dir)
        for item in dir_listing:
            if item[-7:] == '.resume':
                self._load_torrent_info(os.path.join(self._resume_dir, item))

    def get_torrent_info(self, info_hash):
        """
        Get torrent info in a human-readable format

        The following info is returned:
        name - torrent's name
        size - MB
        state - torrent's current state
        dl_speed - KB/s
        ul_speed - KB/s
        total_download - MB
        total_upload - MB
        progress - int %
        num_peers
        num_seeds
        added_time - timestamp in 'YYYY-MM-DD HH:MM:SS' format
        completed_time - see above
        info_hash - torrent's info_hash hexdigest in lowecase
        :param info_hash: str
        :return: dict - torrent info
        """
        torr_info = self._get_torrent_info(info_hash)
        torr_status = self._get_torrent_status(info_hash)
        completed_time = str(datetime.datetime.fromtimestamp(int(torr_status.completed_time)))
        return {'name': torr_info.name().decode('utf-8'),
                'size': torr_info.total_size() / 1048576,
                'state': str(torr_status.state) if not torr_status.paused else 'paused',
                'progress': int(torr_status.progress * 100),
                'dl_speed': torr_status.download_payload_rate / 1024,
                'ul_speed': torr_status.upload_payload_rate / 1024,
                'total_download': torr_status.total_done / 1048576,
                'total_upload': torr_status.total_payload_upload / 1048576,
                'num_seeds': torr_status.num_seeds,
                'num_peers': torr_status.num_peers,
                 # Timestamp in 'YYYY-MM-DD HH:MM:SS' format
                'added_time': str(datetime.datetime.fromtimestamp(int(torr_status.added_time))),
                'completed_time': completed_time if completed_time[:10] != '1970-01-01' else '-',
                'info_hash': info_hash}

    def get_all_torrents_info(self):
        """
        Get info for all torrents in the session

        Note that the torrents info list will have a random order.
        It is up to the caller to sort the list accordingly.
        :return: list - the list of torrent info dicts
        """
        listing = []
        for info_hash in self._torrents_pool.iterkeys():
            listing.append(self.get_torrent_info(info_hash))
        return listing

    def pause_all(self, graceful_pause=1):
        """
        Pause all torrents

        :return:
        """
        for info_hash in self._torrents_pool.iterkeys():
            self.pause_torrent(info_hash, graceful_pause)

    def resume_all(self):
        """
        Resume all torrents

        :return:
        """
        for info_hash in self._torrents_pool.iterkeys():
            self.resume_torrent(info_hash)

    @property
    def is_torrent_added(self):
        """Torrent added flag"""
        return self._torrent_added.is_set()

    @property
    def last_added_torrent(self):
        """The last added torrent info"""
        return self._last_added_torrent[0]


class Streamer(Torrenter):
    """
    Torrent Streamer class

    Implements a torrent client with media streaming capability
    """
    def __init__(self, *args, **kwargs):
        """Class constructor"""
        # Worker threads
        self._buffer_torrent_thread = None
        self._sliding_window_thread = None
        # Signal events
        self._buffering_complete = threading.Event()
        self._abort_buffering = threading.Event()
        self._abort_sliding = threading.Event()
        # Inter-thread data buffers
        self._buffer_percent = deque([0], 1)
        self._streamed_file_data = deque([None], 1)
        self._sliding_window_position = deque([-1], 1)
        super(Streamer, self).__init__(*args, **kwargs)

    def __del__(self):
        """Class destructor"""
        self.abort_buffering()
        super(Streamer, self).__del__()

    def buffer_torrent_async(self, info_hash, file_index, buffer_size=35):
        """
        Force sequential download of file for video playback.

        This method will stream a torrent in a separate thread. The caller should periodically
        check buffering_complete flag. If buffering needs to be terminated,
        the caller should call abort_buffering method.
        :param info_hash: str
        :param file_index: int - the numerical index of the file to be streamed.
        :param buffer_size: int - buffer size in MB
        :return:
        """
        self._buffer_torrent_thread = threading.Thread(target=self.buffer_torrent,
                                                       args=(info_hash, file_index, buffer_size))
        self._buffer_torrent_thread.daemon = True
        self._buffer_torrent_thread.start()

    def buffer_torrent(self, info_hash, file_index, buffer_size=35):
        """
        Force sequential download of file for video playback.

        :param info_hash: str
        :param file_index: int - the numerical index of the file to be streamed.
        :param buffer_size: int - buffer size in MB
        :return:
        """
        # Clear flags
        self._buffering_complete.clear()
        self._abort_buffering.clear()
        self._buffer_percent.append(0)
        torr_handle = self._torrents_pool[info_hash]
        torr_info = torr_handle.get_torrent_info()
        # Pick the file to be streamed from the torrent files
        file_entry = torr_info.files()[file_index]
        peer_req = torr_info.map_file(file_index, 0, 1048576)  # 1048576 (1MB) is a dummy value to avoid C int overflow
        # Start piece of the file
        start_piece = peer_req.piece
        # The number of pieces in the file
        num_pieces = file_entry.size / torr_info.piece_length()
        # The number of pieces at the start of the file
        # to be downloaded before the file can be played
        end_offset = 2097152 / torr_info.piece_length() + 2  # Experimentally tested
        buffer_length = (buffer_size * 1048576) / torr_info.piece_length() - end_offset
        # The index of the end piece in the file
        end_piece = min(start_piece + num_pieces, torr_info.num_pieces() - 1)
        print 'plugin.video.yatp. start_piece={0}, end_piece={1}, piece_length={2}'.format(start_piece, end_piece,
                                                                                           torr_info.piece_length())
        # Check if the torrent has been downloaded earlier
        if not self.check_piece_range(torr_handle, start_piece, end_piece):
            self._streamed_file_data.append({'torr_handle': torr_handle,
                                             'buffer_length': buffer_length,
                                             'start_piece': start_piece,
                                             'end_offset': end_offset,
                                             'end_piece': end_piece,
                                             'piece_length': torr_info.piece_length()})
            # Setup buffer download
            buffer_pool = (range(start_piece, start_piece + buffer_length + 1)
                           + range(end_piece - end_offset, end_piece - 1))
            print 'plugin.video.yatp. buffer_pool: {0}'.format(str(buffer_pool))
            buffer_pool_length = len(buffer_pool)
            [torr_handle.piece_priority(piece, 7) for piece in buffer_pool]
            self.start_sliding_window_async(torr_handle, start_piece, start_piece + buffer_length,
                                            end_piece - end_offset - 1)
            while len(buffer_pool) > 0 and not self._abort_buffering.is_set():
                time.sleep(0.1)
                for index, piece_ in enumerate(buffer_pool):
                    if torr_handle.have_piece(piece_):
                        del buffer_pool[index]
                buffer_ = int(100 * float(buffer_pool_length - len(buffer_pool)) / buffer_pool_length)
                self._buffer_percent.append(buffer_)
            if not self._abort_buffering.is_set():
                torr_handle.flush_cache()
                self._buffering_complete.set()
        else:
            self._buffering_complete.set()

    def start_sliding_window_async(self, torr_handle, window_start, window_end, last_piece):
        """
        Start a sliding window in a separate thread
        """
        self._abort_sliding.set()
        try:
            self._sliding_window_thread.join()
        except (RuntimeError, AttributeError):
            pass
        self._sliding_window_thread = threading.Thread(target=self._sliding_window,
                                                       args=(torr_handle, window_start, window_end, last_piece))
        self._sliding_window_thread.daemon = True
        self._sliding_window_thread.start()

    def _sliding_window(self, torr_handle, window_start, window_end, last_piece):
        """
        Sliding window

        This method implements a sliding window algorithm for sequential download
        of a media file for streaming purposes.
        """
        self._abort_sliding.clear()
        [torr_handle.piece_priority(piece, 1) for piece in xrange(window_start, window_end + 1)]
        while window_start <= last_piece and not self._abort_sliding.is_set():
            print 'plugin.video.yatp. Sliding window position: {0}'.format(window_start)
            self._sliding_window_position.append(window_start)
            torr_handle.piece_priority(window_start, 7)
            if torr_handle.have_piece(window_start):
                window_start += 1
                if window_end < last_piece:
                    window_end += 1
                    torr_handle.piece_priority(window_end, 1)
            time.sleep(0.1)
        if not self._abort_sliding.is_set():
            [torr_handle.piece_priority(piece, 1) for piece in xrange(torr_handle.get_torrent_info().num_pieces())]
        self._sliding_window_position.append(-1)

    def abort_buffering(self):
        """
        Abort buffering

        :return:
        """
        self._abort_buffering.set()
        self._abort_sliding.set()
        try:
            self._buffer_torrent_thread.join()
        except (RuntimeError, AttributeError):
            pass
        try:
            self._sliding_window_thread.join()
        except (RuntimeError, AttributeError):
            pass

    @property
    def is_buffering_complete(self):
        """Buffering complete flag"""
        return self._buffering_complete.is_set()

    @property
    def sliding_window_position(self):
        """Sliding window position"""
        return self._sliding_window_position[0]

    @property
    def buffer_percent(self):
        """Buffer %"""
        return self._buffer_percent[0]

    @property
    def streamed_file_data(self):
        """
        Streamed file data

        :return: tuple - (torr_handle, start_piece, num_pieces)
        """
        return self._streamed_file_data[0]
