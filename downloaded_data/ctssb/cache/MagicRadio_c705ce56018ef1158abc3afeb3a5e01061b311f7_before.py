from tinytag import TinyTag
import MRGlobals
import logging
import random
import time
import json
import DJ
import os

"""
    Short description:
        The purpose of this file is to handle the station objects, fetching of track path, and the handling of dj shows. 

    Station Class Stuff:
        Each station contains:
         - Type of station
         - Station Directory
         - List of tracks
         - Dictionary of station durations
        Pick Stations also have:
         - Last played
         - Epoch from last played
        Dynamic Stations also have:
         - lastShow, lastShowEpoch, and a countdown until the next show (in terms of songs)

        Stations operate with these functions:
         - Init (Starts the station, sets up station duration dictionary and list of stations)
         - Update (Passed from parent, handles the logic that occurs each tick)
    
    Each Station type is a child class. This way, the logic for updating is well organized and clear. It also allows
     the parent class to have one unified import/setup.
    
    The update function passes the audio mixer and a boolean representing if it is transferring from another station.
     The transfer variable is used to determine whether to resume playback of the same song.

    Different types of stations:
     - Static: No music. It just stops the playback upon transferring

     - Fixed: Standard audio loop, persistence is maintained by resuming playback with the remainder of the song time 
        and the date established in MRGlobals. In actuality, there should only be one song in the folder of the Fixed
        station. If there are more than one, it just grabs the first one the OS gives it.

     - Pick: Folder containing multiple tracks. To maintain persistence between radio switching, every time a new song
        starts the song name and start time is saved. Each tick, the station checks the elapsed time against the
        duration of the song. If greater, it'll pick a new song from a shuffled list at random with the remaining time from the check.
        On reboot, all progression is lost.
        
     - Dynamic: Pick Station with included DJ shows interjected. Maintains a countdown of songs until DJ begins. Also
        maintains persistance with DJ shows. Simple rule (allows users to hear what station it is), it always starts on a DJ show. It
        only attempts to resume playback on a DJ show if the DJ show hasn't elapsed.
        
"""

def buildStation(stationData):
    # All stations have 'type' as a part of their definition in stations.json
    stationType = stationData["type"]

    # The Bluetooth station's job is to mute static and turn on the audio of the BT script.
    # Of course, I actually need to implement the sound controls for bluetooth first.

    # TODO: Implement Bluetooth
    if(stationType == "bluetooth"):
        logging.warn("Bluetooth is not implemented. Get on this, Thomas, though I understand you are busy with other stuff.")
        return None
    
    # All station types except for bluetooth have a 'dir' attribute. At this point, it should be safe to grab
    stationDir = stationData["dir"]

    # Generate stations based upon type
    if(stationType == "pick"):
        stationObject = PickStation(stationDir)
    elif(stationType == "dynamic"):
        stationObject = DynamicStation(stationDir)
    else:
        # While there is a type for static/fixed stations, this catches everything just in case
        stationObject = Station(stationDir)

    logging.debug("Station %s has been built" % stationDir)

    return stationObject


# This is literally only to stop music, and simplify tuner logic. It does nothing else.
class StaticStation:
    def update(self, mixer, transfer):
        if transfer:
            mixer.music.stop()
            logging.debug("Static Station has halted music playback")

    def __str__(self):
        return "static"


# The main Station class, handles the file finding for music alongside the duration searching
class Station:

    stationType = "fixed"

    def __init__(self, stationDirectory):
        # Setup self variables
        self.stationDirectory = stationDirectory
        self.fullStationPath = MRGlobals.stationsFolder + self.stationDirectory + "/"
        # Build track list - the stationDir will contain all music at root. DJ stations contain their own info in the "dj" subfolder
        self.tracks = [file for file in os.listdir(self.fullStationPath) if file.endswith(".ogg")]
        if len(self.tracks) <= 0:
            logging.critical("%s has no audio in its folder" % self.stationDirectory)
        # Build duration list
        self.trackDurations = {}
        for track in self.tracks:
            self.trackDurations[track] = float(TinyTag.get(self.fullStationPath + track).duration)

    def __str__(self):
        return "(%s)[%s | %d]" % (self.stationType, self.stationDirectory, len(self.tracks))


    # This will be called each time the audio thread ticks. It takes a PyGame Mixer as an argument, and the Transfer argument is a boolean
    # Transfer is true only the first time the update is called. It's used to transition between different stations.
    # This function's job is to keep track of music persistance. It behaves a lot like the old prototype, and is the default "fixed" station.
    def update(self, mixer, transfer):

        # If we're transferring from another station, we clean up their mess in the mixer and begin our own music.
        if transfer:

            # Begin by setting up new lead variable and stopping the music. Static will continue, so the slight jump shouldn't be noticable
            mixer.music.stop()
            # We shouldn't technically need to stop the music, considering mixer.music.load() stops it AND it should always be stopped on static, 
            #  but just in case.
            lead = 0.0

            # Only getting the first track, since it's a fixed station. Track logic differs per station type
            newTrack = self.tracks[0] 
            
            # We need to load our new music and setup our lead, to make it seem like the radio was still playing.
            mixer.music.load(self.fullStationPath + newTrack)
            newDuration = self.trackDurations[newTrack]
            lead = time.time() - MRGlobals.clockTime
            # If the lead is more than the duration of the song, that's not good, so we're going to get the remainder and use that instead.
            if lead > newDuration:
                lead = lead % newDuration
                logging.debug("Lead was more than newDuration, lead is now %d" % lead)

            # Loop infinitely, as it's a fixed station. 
            mixer.music.play(loops=-1)
            mixer.music.set_pos(lead)
            
            # Only tell the user we're playing after we're actually playing. That way he doesn't get confused if we crash.
            logging.debug("<%s> New Music Playing: %s Lead: %d" % (self, newTrack, lead))
        
        """
            That's it for this simple station. It'll just run through the basics on transfer. It doesn't have to do anything except for that.
             Infinite looping takes care of most of the work. This update method should NEVER manipulate the mixer's audio. That is exclusively
             for the audio thread. Boundaries are important.
        """

"""
    Pick Stations
     On transfer, a pick station will attempt to play back the last played song with the elapsed offest. If the 
     offset is greater than the duration of the song, it'll pick a new song from a selection that excludes the last 
     played song. It then begins this at the remainder offset, updates the lastSong and lastSongEpoch. In absence of
     a last played song, it'll pick one at random and begin its offset with the same system a Station uses, related
     to the MRGlobals epcoh.
"""
class PickStation(Station):
    # No special init logic, just the basic variable setup.
    def __init__(self, stationDirectory):
        Station.__init__(self, stationDirectory)
        # Setup variables used for update
        self.lastTrack = ""
        self.lastTrackEpoch = 0.0
        self.lastTrackDuration = 0.0

        # Establishing ignored track length. By default, it's 4, but if we're a bit close it'll be below that.
        ignoredCount = 4
        trackCount = len(self.tracks)
        if trackCount <= ignoredCount:
            ignoredCount = trackCount - 1
            if ignoredCount <= 1:
                ignoredCount = 1

        self.ignoredTracks = [""] * ignoredCount
        logging.debug(len(self.ignoredTracks))


    stationType = "pick"

    # pickTrack is a simple little guy, just handles all the logic and errors for picking a new track
    #  It attempts to avoid the last four tracks played. 
    def pickTrack(self):
        pickableTracks = list(self.tracks)
        # Trying to prevent the last three songs from playing again.
        for track in self.ignoredTracks:
            try:
                pickableTracks.remove(track)
            except(ValueError):
                pass
        
        # Pick track
        random.shuffle(pickableTracks)
        picked = random.choice(pickableTracks)
        # Moving the picked track into the ignored queue, removing the first in the queue.
        self.ignoredTracks.pop(0)
        self.ignoredTracks.append(picked)
        return picked

    # update() handles all logic, and does not inherit anything from Station
    def update(self, mixer, transfer):
        # Default lead, should be OK for most cases
        lead = time.time() - self.lastTrackEpoch

        # When a station plays for the first time, lastTrackEpoch is 0. We can check for that, then calculate a
        #  different lead based upon that
        if self.lastTrackEpoch == 0:
            lead = time.time() - MRGlobals.clockTime

        if lead >= self.lastTrackDuration:
            # play new track
            nextTrack = self.pickTrack()
            mixer.music.load(self.fullStationPath + nextTrack)
            mixer.music.play()
            if self.lastTrackDuration == 0.0:
                lead = float(lead) % float(self.trackDurations[nextTrack])
            else:
                lead = float(lead) % float(self.lastTrackDuration)
            mixer.music.set_pos(lead)

            # Setup the data for the next loop
            self.lastTrack = nextTrack
            self.lastTrackEpoch = time.time() - lead
            self.lastTrackDuration = self.trackDurations[nextTrack]
            logging.info("<%s> New Music Playing: %s" % (self, self.lastTrack))
        elif transfer: # This only occurs when the lead is less than the last track duration AND it is a transfer update
            # play old track
            mixer.music.load(self.fullStationPath + self.lastTrack)
            mixer.music.play()
            mixer.music.set_pos(lead)
            logging.info("<%s> Resuming %s at %d" % (self, self.lastTrack, lead))
            # In this case, we wouldn't update any variables, since it should still be maintained

"""
    By far the most complicated station, a Dynamic station plays audio from the tracks list with interjected DJ shows, generated by the DJ object.
"""
class DynamicStation(PickStation):

    stationType = "Dynamic"

    def __init__(self, stationDirectory):
        PickStation.__init__(self, stationDirectory)
        
        # We need to find the rules specific to this DJ/station object. We can find these in the .dj file located in the
        #  root of the station folder, bearing the same name as the station folder.
        djFilePath = self.fullStationPath + self.stationDirectory + ".dj"
        djFile = open(djFilePath)
        self.djFileData = None
        try:
            self.djFileData = json.load(djFile)
        except (IOError):
            logging.critical("%s.dj file not found" % self.stationDirectory)
        except (ValueError):
            logging.critical("%s.dj is improper" % self.stationDirectory)
        assert(self.djFileData is not None), ("Error in DJFile Data for %s, shutting down." % self.stationDirectory)

        logging.debug("%s.dj has been found and read properly" % self.stationDirectory)

        # Now that we have the data, we need to build ourselves a DJ.
        self.dj = DJ.DJ(self.fullStationPath, self.djFileData["format"])

        logging.debug("%s.dj has been built properly" % self.stationDirectory)

        # We also need to prep our song ranges
        self.minTracks = int(self.djFileData["minSongs"])
        self.maxTracks = int(self.djFileData["maxSongs"])

        # Finally we need to prep our DJ lastShow stuff
        self.lastShow = []
        self.lastShowEpoch = 0.0
        self.lastShowDuration = 0.0
        self.showIndex = 0

        self.mode = "music"
        self.remainingTracks = -1
    
    # Same logic as a pickstation, but with the addition of a counter to handle the switching between modes
    def pickTrack(self):
        picked = PickStation.pickTrack(self)
        self.remainingTracks -= 1
        return picked

    def update(self, mixer, transfer):
        if self.mode == "music":
            if self.remainingTracks < 0:
                # This throws a tiny gap, about 1/60th of a second between the last track
                # stopping and the show beginning, but that's ok. 
                self.mode = "show"
                return
            # If we're doing music, use all the same logic as the parent.
            PickStation.update(self, mixer, transfer)
        if self.mode == "show":
            # First, decide if it's been too long since the last show. If it has, we 
            #  generate a new show.

            # We do this by determining if the lead (or time since the last show's 
            #  epoch) is greater than the last show's duration
            lead = time.time() - self.lastShowEpoch
            if lead >= self.lastShowDuration:
                #Alright, we need ourselves a new show. We get the DJ to build one for us,
                # then we save all the variables to ourselves, including the total duration
                # of the show.
                self.lastShow = self.dj.generateShow()
                # Summation of time:
                self.lastShowDuration = 3.0
                for track in self.lastShow:
                    trackDuration = track["duration"]
                    self.lastShowDuration += trackDuration
                print("New Show Duration %d" % self.lastShowDuration)
                # Saving of the current epoch
                self.lastShowEpoch = time.time()
                self.showIndex = 0
                self.showSegment = self.lastShow[self.showIndex]
                # Load the first track of the first segment
                mixer.music.load(self.showSegment["track"])
                mixer.music.play()

                self.lastTrack = self.showSegment["track"]
                self.lastTrackEpoch = time.time()
                self.lastTrackDuration = self.showSegment["duration"]
                logging.info("<%s> New show beginnning" % self)
                return
            else:
                # We're still inside the last show, so we need to find out what part of it we are on
                # First, if we need to check if the segment of the show is over
                lead = time.time() - self.lastTrackEpoch
                if lead >= self.lastTrackDuration:
                    # We're in a new segment of the show. Check if we can start the next one  
                    self.showIndex += 1
                    if self.showIndex >= len(self.lastShow):
                        # Show is over, back to music
                        self.mode = "music"
                        self.remainingTracks = random.randint(self.minTracks, self.maxTracks)
                        print(self.remainingTracks)
                        return
                    # If we're at this point, this means we need to start the next segment
                    self.showSegment = self.lastShow[self.showIndex]
                    mixer.music.load(self.showSegment["track"])
                    mixer.music.play()
                    self.lastTrack = self.showSegment["track"]
                    self.lastTrackEpoch = time.time()
                    self.lastTrackDuration = self.showSegment["duration"]
                    logging.info("<%s> Next segment of show beginning" % self)
                    return
                # We're playing a track right now, everything is OK.
                if transfer:
                    # We've been transferred to, and the last segment is still playing
                    mixer.music.load(self.showSegment["track"])
                    mixer.music.play()
                    mixer.music.set_pos(lead)
                    logging.info("<%s> Resuming segment at %d" % (self, lead))
