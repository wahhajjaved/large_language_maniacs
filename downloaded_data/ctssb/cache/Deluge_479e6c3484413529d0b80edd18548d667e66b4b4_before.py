#
# torrent.py
#
# Copyright (C) 2007, 2008 Andrew Resch ('andar') <andrewresch@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA    02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.

"""Internal Torrent class"""

import os
from urlparse import urlparse

import deluge.libtorrent as lt
import deluge.common
import deluge.component as component
from deluge.configmanager import ConfigManager
from deluge.log import LOG as log
from deluge.core.preferencesmanager import DEFAULT_PREFS
import deluge.xmlrpclib

TORRENT_STATE = deluge.common.TORRENT_STATE

OPTIONS = {
    "max_download_speed": DEFAULT_PREFS["max_download_speed_per_torrent"],
    "max_upload_speed": DEFAULT_PREFS["max_upload_speed_per_torrent"],
    "max_connections": DEFAULT_PREFS["max_connections_per_torrent"],
    "max_upload_slots": DEFAULT_PREFS["max_upload_slots_per_torrent"],
    "prioritize_first_last_pieces": DEFAULT_PREFS["prioritize_first_last_pieces"],
    "auto_managed": DEFAULT_PREFS["auto_managed"],
    "stop_at_ratio": DEFAULT_PREFS["stop_seed_at_ratio"],
    "stop_ratio": DEFAULT_PREFS["stop_seed_ratio"],
    "remove_at_ratio": DEFAULT_PREFS["remove_seed_at_ratio"],
    "move_completed": DEFAULT_PREFS["move_completed"],
    "move_completed_path": DEFAULT_PREFS["move_completed_path"],
    "file_priorities": [],
    "compact_allocation": DEFAULT_PREFS["compact_allocation"],
    "download_location": DEFAULT_PREFS["download_location"],
    "add_paused": DEFAULT_PREFS["add_paused"]
}

class Torrent:
    """Torrent holds information about torrents added to the libtorrent session.
    """
    def __init__(self, handle, options, state=None, filename=None):
        log.debug("Creating torrent object %s", str(handle.info_hash()))
        # Get the core config
        self.config = ConfigManager("core.conf")

        self.signals = component.get("SignalManager")

        # Set the libtorrent handle
        self.handle = handle
        # Set the torrent_id for this torrent
        self.torrent_id = str(handle.info_hash())

        # Let's us know if we're waiting on a lt alert
        self.waiting_on_resume_data = False
        
        # We store the filename just in case we need to make a copy of the torrentfile
        if not filename:
            # If no filename was provided, then just use the infohash
            filename = self.torrent_id
            
        self.filename = filename

        # Holds status info so that we don't need to keep getting it from lt
        self.status = self.handle.status()

        try:
            self.torrent_info = self.handle.get_torrent_info()
        except RuntimeError:
            self.torrent_info = None
            
        # Files dictionary
        self.files = self.get_files()
        
        # Default total_uploaded to 0, this may be changed by the state
        self.total_uploaded = 0

        # Set the default options
        self.options = OPTIONS.copy()
        self.options.update(options)
        
        # We need to keep track if the torrent is finished in the state to prevent
        # some weird things on state load.
        self.is_finished = False

        # Load values from state if we have it
        if state:
            # This is for saving the total uploaded between sessions
            self.total_uploaded = state.total_uploaded
            # Set the trackers
            self.set_trackers(state.trackers)
            # Set the filename
            self.filename = state.filename
            self.is_finished = state.is_finished
            # Set the per-torrent queue options
            self.options["stop_at_ratio"] = state.stop_at_ratio
            self.options["stop_ratio"] = state.stop_ratio
            self.options["remove_at_ratio"] = state.remove_at_ratio
        else:
            # Tracker list
            self.trackers = []
            # Create a list of trackers
            for value in self.handle.trackers():
                tracker = {}
                tracker["url"] = value.url
                tracker["tier"] = value.tier
                self.trackers.append(tracker)

        # Various torrent options
        self.handle.resolve_countries(True)
        self.set_options(self.options)
        
        # Status message holds error info about the torrent
        self.statusmsg = "OK"

        # The torrents state
        self.update_state()

        # The tracker status
        self.tracker_status = ""

        log.debug("Torrent object created.")

    ## Options methods ##
    def set_options(self, options):
        OPTIONS_FUNCS = {
            # Functions used for setting options
            "max_download_speed": self.set_max_download_speed,
            "max_upload_speed": self.set_max_upload_speed,
            "max_connections": self.handle.set_max_connections,
            "max_upload_slots": self.handle.set_max_uploads,
            "prioritize_first_last_pieces": self.set_prioritize_first_last,
            "auto_managed": self.set_auto_managed,
            "file_priorities": self.set_file_priorities,
            "download_location": self.set_save_path,
        }
        for (key, value) in options.items():
            if OPTIONS_FUNCS.has_key(key):
                OPTIONS_FUNCS[key](value)
        
        self.options.update(options)
    
    def get_options(self):
        return self.options
        
    def set_max_connections(self, max_connections):
        self.options["max_connections"] = int(max_connections)
        self.handle.set_max_connections(max_connections)

    def set_max_upload_slots(self, max_slots):
        self.options["max_upload_slots"] = int(max_slots)
        self.handle.set_max_uploads(max_slots)

    def set_max_upload_speed(self, m_up_speed):
        self.options["max_upload_speed"] = m_up_speed
        if m_up_speed < 0:
            v = -1
        else:
            v = int(m_up_speed * 1024)

        self.handle.set_upload_limit(v)

    def set_max_download_speed(self, m_down_speed):
        self.options["max_download_speed"] = m_down_speed
        if m_down_speed < 0:
            v = -1
        else:
            v = int(m_down_speed * 1024)
        self.handle.set_download_limit(v)

    def set_prioritize_first_last(self, prioritize):
        self.options["prioritize_first_last_pieces"] = prioritize
        if prioritize:
            if self.handle.has_metadata():
                if self.handle.get_torrent_info().num_files() == 1:
                    # We only do this if one file is in the torrent
                    priorities = [1] * self.handle.get_torrent_info().num_pieces()
                    priorities[0] = 7
                    priorities[-1] = 7
                    self.handle.prioritize_pieces(priorities)

    def set_auto_managed(self, auto_managed):
        self.options["auto_managed"] = auto_managed
        if not (self.handle.is_paused() and not self.handle.is_auto_managed()):
            self.handle.auto_managed(auto_managed)
            self.update_state()

    def set_stop_ratio(self, stop_ratio):
        self.options["stop_ratio"] = stop_ratio

    def set_stop_at_ratio(self, stop_at_ratio):
        self.options["stop_at_ratio"] = stop_at_ratio

    def set_remove_at_ratio(self, remove_at_ratio):
        self.options["remove_at_ratio"] = remove_at_ratio

    def set_file_priorities(self, file_priorities):
        log.debug("setting %s's file priorities: %s", self.torrent_id, file_priorities)
        if len(file_priorities) != len(self.files):
            log.debug("file_priorities len != num_files")
            return

        self.handle.prioritize_files(file_priorities)

        if 0 in self.options["file_priorities"]:
            # We have previously marked a file 'Do Not Download'
            # Check to see if we have changed any 0's to >0 and change state accordingly
            for index, priority in enumerate(self.options["file_priorities"]):
                if priority == 0 and file_priorities[index] > 0:
                    # We have a changed 'Do Not Download' to a download priority
                    self.is_finished = False
                    self.update_state()
                    break

        self.options["file_priorities"] = file_priorities

        # Set the first/last priorities if needed
        self.set_prioritize_first_last(self.options["prioritize_first_last_pieces"])
        
    def set_trackers(self, trackers):
        """Sets trackers"""
        if trackers == None:
            trackers = []

        log.debug("Setting trackers for %s: %s", self.torrent_id, trackers)
        tracker_list = []

        for tracker in trackers:
            new_entry = lt.announce_entry(tracker["url"])
            new_entry.tier = tracker["tier"]
            tracker_list.append(new_entry)

        self.handle.replace_trackers(tracker_list)

        # Print out the trackers
        for t in self.handle.trackers():
            log.debug("tier: %s tracker: %s", t.tier, t.url)
        # Set the tracker list in the torrent object
        self.trackers = trackers
        if len(trackers) > 0:
            # Force a reannounce if there is at least 1 tracker
            self.force_reannounce()

    ### End Options methods ###

    def set_save_path(self, save_path):
        self.options["download_location"] = save_path
            
    def set_tracker_status(self, status):
        """Sets the tracker status"""
        self.tracker_status = status

    def update_state(self):
        """Updates the state based on what libtorrent's state for the torrent is"""
        # Set the initial state based on the lt state
        LTSTATE = deluge.common.LT_TORRENT_STATE
        ltstate = int(self.handle.status().state)

        log.debug("set_state_based_on_ltstate: %s", deluge.common.LT_TORRENT_STATE[ltstate])
        log.debug("session.is_paused: %s", component.get("Core").session.is_paused())
        if ltstate == LTSTATE["Queued"] or ltstate == LTSTATE["Checking"]:
            self.state = "Checking"
            return
        elif ltstate == LTSTATE["Downloading"] or ltstate == LTSTATE["Downloading Metadata"]:
            self.state = "Downloading"
        elif ltstate == LTSTATE["Finished"] or ltstate == LTSTATE["Seeding"]:
            self.state = "Seeding"
        elif ltstate == LTSTATE["Allocating"]:
            self.state = "Allocating"

        if self.handle.is_paused() and len(self.handle.status().error) > 0:
            # This is an error'd torrent
            self.state = "Error"
            self.set_status_message(self.handle.status().error)
            self.handle.auto_managed(False)
        elif self.handle.is_paused() and self.handle.is_auto_managed() and not component.get("Core").session.is_paused():
            self.state = "Queued"
        elif component.get("Core").session.is_paused() or (self.handle.is_paused() and not self.handle.is_auto_managed()):
            self.state = "Paused"

    def set_state(self, state):
        """Accepts state strings, ie, "Paused", "Seeding", etc."""
        if state not in TORRENT_STATE:
            log.debug("Trying to set an invalid state %s", state)
            return

        self.state = state
        return

    def set_status_message(self, message):
        self.statusmsg = message

    def get_eta(self):
        """Returns the ETA in seconds for this torrent"""
        if self.status == None:
            status = self.handle.status()
        else:
            status = self.status

        left = status.total_wanted - status.total_done

        if left <= 0 or status.download_payload_rate == 0:
            return 0

        try:
            eta = left / status.download_payload_rate
        except ZeroDivisionError:
            eta = 0

        return eta

    def get_ratio(self):
        """Returns the ratio for this torrent"""
        if self.status == None:
            status = self.handle.status()
        else:
            status = self.status

        up = self.total_uploaded + status.total_payload_upload
        down = status.total_done

        # Convert 'up' and 'down' to floats for proper calculation
        up = float(up)
        down = float(down)

        try:
            ratio = up / down
        except ZeroDivisionError:
            return 0.0

        return ratio

    def get_files(self):
        """Returns a list of files this torrent contains"""
        if self.torrent_info == None and self.handle.has_metadata():
            torrent_info = self.handle.get_torrent_info()
        else:
            torrent_info = self.torrent_info
        
        if not torrent_info:
            return []
            
        ret = []
        files = torrent_info.files()
        for index, file in enumerate(files):
            ret.append({
                'index': index,
                'path': file.path,
                'size': file.size,
                'offset': file.offset
            })
        return ret

    def get_peers(self):
        """Returns a list of peers and various information about them"""
        ret = []
        peers = self.handle.get_peer_info()

        for peer in peers:
            # We do not want to report peers that are half-connected
            if peer.flags & peer.connecting or peer.flags & peer.handshake:
                continue
            try:
                client = str(peer.client).decode("utf-8")
            except UnicodeDecodeError:
                client = str(peer.client).decode("latin-1")

            # Make country a proper string
            country = str()
            for c in peer.country:
                if not c.isalpha():
                    country += " "
                else:
                    country += c

            ret.append({
                "ip": "%s:%s" % (peer.ip[0], peer.ip[1]),
                "up_speed": peer.up_speed,
                "down_speed": peer.down_speed,
                "country": country,
                "client": client,
                "seed": peer.flags & peer.seed,
                "progress": peer.progress
            })

        return ret

    def get_queue_position(self):
        """Returns the torrents queue position"""
        return self.handle.queue_position()

    def get_file_progress(self):
        """Returns the file progress as a list of floats.. 0.0 -> 1.0"""
        if not self.handle.has_metadata():
            return 0.0
            
        file_progress = self.handle.file_progress()
        ret = []
        for i,f in enumerate(self.files):
            try:
                ret.append(float(file_progress[i]) / float(f["size"]))
            except ZeroDivisionError:
                ret.append(0.0)

        return ret

    def get_tracker_host(self):
        """Returns just the hostname of the currently connected tracker
        if no tracker is connected, it uses the 1st tracker."""
        if not self.status:
            self.status = self.handle.status()

        tracker = self.status.current_tracker
        if not tracker and self.trackers:
            tracker = self.trackers[0]["url"]

        if tracker:
            url = urlparse(tracker)
            if hasattr(url, "hostname"):
                host = (url.hostname or 'unknown?')
                parts = host.split(".")
                if len(parts) > 2:
                    host = ".".join(parts[-2:])
                return host
        return ""

    def get_status(self, keys):
        """Returns the status of the torrent based on the keys provided"""
        # Create the full dictionary
        self.status = self.handle.status()
        if self.handle.has_metadata():
            self.torrent_info = self.handle.get_torrent_info()

        # Adjust progress to be 0-100 value
        progress = self.status.progress * 100

        # Adjust status.distributed_copies to return a non-negative value
        distributed_copies = self.status.distributed_copies
        if distributed_copies < 0:
            distributed_copies = 0.0

        #if you add a key here->add it to core.py STATUS_KEYS too.
        full_status = {
            "distributed_copies": distributed_copies,
            "total_done": self.status.total_done,
            "total_uploaded": self.total_uploaded + self.status.total_payload_upload,
            "state": self.state,
            "paused": self.status.paused,
            "progress": progress,
            "next_announce": self.status.next_announce.seconds,
            "total_payload_download": self.status.total_payload_download,
            "total_payload_upload": self.status.total_payload_upload,
            "download_payload_rate": self.status.download_payload_rate,
            "upload_payload_rate": self.status.upload_payload_rate,
            "num_peers": self.status.num_peers - self.status.num_seeds,
            "num_seeds": self.status.num_seeds,
            "total_peers": self.status.num_incomplete,
            "total_seeds":  self.status.num_complete,
            "total_wanted": self.status.total_wanted,
            "tracker": self.status.current_tracker,
            "trackers": self.trackers,
            "tracker_status": self.tracker_status,
            "save_path": self.options["download_location"],
            "files": self.files,
            "file_priorities": self.options["file_priorities"],
            "compact": self.options["compact_allocation"],
            "max_connections": self.options["max_connections"],
            "max_upload_slots": self.options["max_upload_slots"],
            "max_upload_speed": self.options["max_upload_speed"],
            "max_download_speed": self.options["max_download_speed"],
            "prioritize_first_last": self.options["prioritize_first_last_pieces"],
            "message": self.statusmsg,
            "hash": self.torrent_id,
            "active_time": self.status.active_time,
            "seeding_time": self.status.seeding_time,
            "seed_rank": self.status.seed_rank,
            "is_auto_managed": self.options["auto_managed"],
            "stop_ratio": self.options["stop_ratio"],
            "stop_at_ratio": self.options["stop_at_ratio"],
            "remove_at_ratio": self.options["remove_at_ratio"],
            "move_on_completed": self.options["move_completed"],
            "move_on_completed_path": self.options["move_completed_path"]
        }
        
        def ti_name():
            if self.handle.has_metadata():
                return self.torrent_info.name()
            return self.torrent_id
        def ti_priv():
            if self.handle.has_metadata():
                return self.torrent_info.priv()
            return False
        def ti_total_size():
            if self.handle.has_metadata():
                return self.torrent_info.total_size()
            return 0
        def ti_num_files():
            if self.handle.has_metadata():
                return self.torrent_info.num_files()
            return 0
        def ti_num_pieces():
            if self.handle.has_metadata():
                return self.torrent_info.num_pieces()
            return 0
        def ti_piece_length():
            if self.handle.has_metadata():
                return self.torrent_info.piece_length()
            return 0
            
        fns = {
            "name": ti_name,
            "private": ti_priv,
            "total_size": ti_total_size,
            "num_files": ti_num_files,
            "num_pieces": ti_num_pieces,
            "piece_length": ti_piece_length,
            "eta": self.get_eta,
            "ratio": self.get_ratio,
            "file_progress": self.get_file_progress,
            "queue": self.handle.queue_position,
            "is_seed": self.handle.is_seed,
            "peers": self.get_peers,
            "tracker_host": self.get_tracker_host
        }

        # Create the desired status dictionary and return it
        status_dict = {}

        if len(keys) == 0:
            status_dict = full_status
            for key in fns:
                status_dict[key] = fns[key]()
        else:
            for key in keys:
                if key in full_status:
                    status_dict[key] = full_status[key]
                elif key in fns:
                    status_dict[key] = fns[key]()

        self.status = None
        self.torrent_info = None
        
        return status_dict

    def apply_options(self):
        """Applies the per-torrent options that are set."""
        self.handle.set_max_connections(self.max_connections)
        self.handle.set_max_uploads(self.max_upload_slots)
        self.handle.set_upload_limit(int(self.max_upload_speed * 1024))
        self.handle.set_download_limit(int(self.max_download_speed * 1024))
        self.handle.prioritize_files(self.file_priorities)
        self.handle.resolve_countries(True)

    def pause(self):
        """Pause this torrent"""
        # Turn off auto-management so the torrent will not be unpaused by lt queueing
        self.handle.auto_managed(False)
        if self.handle.is_paused():
            # This torrent was probably paused due to being auto managed by lt
            # Since we turned auto_managed off, we should update the state which should
            # show it as 'Paused'.  We need to emit a torrent_paused signal because
            # the torrent_paused alert from libtorrent will not be generated.
            self.update_state()
            self.signals.emit("torrent_paused", self.torrent_id)
        else:
            try:
                self.handle.pause()
            except Exception, e:
                log.debug("Unable to pause torrent: %s", e)
                return False

        return True

    def resume(self):
        """Resumes this torrent"""

        if self.handle.is_paused() and self.handle.is_auto_managed():
            log.debug("Torrent is being auto-managed, cannot resume!")
            return
        else:
            # Reset the status message just in case of resuming an Error'd torrent
            self.set_status_message("OK")

            if self.handle.is_finished():
                # If the torrent has already reached it's 'stop_seed_ratio' then do not do anything
                if self.config["stop_seed_at_ratio"] or self.options["stop_at_ratio"]:
                    if self.options["stop_at_ratio"]:
                        ratio = self.options["stop_ratio"]
                    else:
                        ratio = self.config["stop_seed_ratio"]

                    if self.get_ratio() >= ratio:
                        self.signals.emit("torrent_resume_at_stop_ratio")
                        return

            if self.options["auto_managed"]:
                # This torrent is to be auto-managed by lt queueing
                self.handle.auto_managed(True)

            try:
                self.handle.resume()
            except:
                pass

            return True

    def move_storage(self, dest):
        """Move a torrent's storage location"""
        try:
            self.handle.move_storage(dest)
        except:
            return False

        return True

    def save_resume_data(self):
        """Signals libtorrent to build resume data for this torrent, it gets
        returned in a libtorrent alert"""
        self.handle.save_resume_data()
        self.waiting_on_resume_data = True
        
    def write_resume_data(self, resume_data):
        """Writes the .fastresume file for the torrent"""
        resume_data = lt.bencode(resume_data)
        path = "%s/%s.fastresume" % (
            self.config["state_location"],
            self.torrent_id)
        try:
            self.delete_fastresume()
            log.debug("Saving fastresume file: %s", path)
            fastresume = open(path, "wb")
            fastresume.write(resume_data)
            fastresume.close()
        except IOError:
            log.warning("Error trying to save fastresume file")
        
        self.waiting_on_resume_data = False

    def delete_fastresume(self):
        """Deletes the .fastresume file"""
        path = "%s/%s.fastresume" % (
            self.config["state_location"],
            self.torrent_id)
        log.debug("Deleting fastresume file: %s", path)
        try:
            os.remove(path)
        except Exception, e:
            log.warning("Unable to delete the fastresume file: %s", e)

    def delete_torrentfile(self):
        """Deletes the .torrent file in the state"""
        path = "%s/%s.torrent" % (
            self.config["state_location"],
            self.torrent_id)
        log.debug("Deleting torrent file: %s", path)
        try:
            os.remove(path)
        except Exception, e:
            log.warning("Unable to delete the torrent file: %s", e)

    def force_reannounce(self):
        """Force a tracker reannounce"""
        try:
            self.handle.force_reannounce()
        except Exception, e:
            log.debug("Unable to force reannounce: %s", e)
            return False

        return True

    def scrape_tracker(self):
        """Scrape the tracker"""
        try:
            self.handle.scrape_tracker()
        except Exception, e:
            log.debug("Unable to scrape tracker: %s", e)
            return False

        return True

    def force_recheck(self):
        """Forces a recheck of the torrents pieces"""
        try:
            self.handle.force_recheck()
        except Exception, e:
            log.debug("Unable to force recheck: %s", e)
            return False
        return True
