"""
Thierry Bertin-Mahieux (2010) Columbia University
tb2332@columbia.edu


This code contains a set of routines to create HDF5 files containing
features and metadata of a song.

This is part of the Million Song Dataset project from
LabROSA (Columbia University) and The Echo Nest.


Copyright 2010, Thierry Bertin-Mahieux

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


import os
import sys
import numpy as np
# code relies on pytables, see http://www.pytables.org
import tables
import hdf5_descriptors as DESC
from hdf5_getters import *

ARRAY_DESC_SEGMENTS_START = 'array of start times of segments'
ARRAY_DESC_SEGMENTS_CONFIDENCE = 'array of confidence of segments'
ARRAY_DESC_SEGMENTS_PITCHES = 'array of pitches of segments (chromas)'
ARRAY_DESC_SEGMENTS_TIMBRE = 'array of timbre of segments (MFCC-like)'
ARRAY_DESC_SEGMENTS_LOUDNESS_MAX = 'array of max loudness of segments'
ARRAY_DESC_SEGMENTS_LOUDNESS_MAX_TIME = 'array of max loudness time of segments'
ARRAY_DESC_SEGMENTS_LOUDNESS_START = 'array of loudness of segments at start time'
ARRAY_DESC_SECTIONS_START = 'array of start times of sections'
ARRAY_DESC_SECTIONS_CONFIDENCE = 'array of confidence of sections'
ARRAY_DESC_BEATS_START = 'array of start times of beats'
ARRAY_DESC_BEATS_CONFIDENCE = 'array of confidence of sections'
ARRAY_DESC_BARS_START = 'array of start times of bars'
ARRAY_DESC_BARS_CONFIDENCE = 'array of confidence of bars'
ARRAY_DESC_TATUMS_START = 'array of start times of tatums'
ARRAY_DESC_TATUMS_CONFIDENCE = 'array of confidence of tatums'


def fill_hdf5_from_song(h5,song):
    """
    Fill an open hdf5 using all the content in a song object
    from the Echo Nest python API.
    Usually, fill_hdf5_from_track() will have been called first.
    """
    # get the metadata table, fill it
    metadata = h5.root.metadata.songs
    metadata.cols.artist_familiarity[0] = song.artist_familiarity
    metadata.cols.artist_hotttnesss[0] = song.artist_hotttnesss
    metadata.cols.artist_id[0] = song.artist_id
    metadata.cols.artist_latitude[0] = song.artist_location.latitude
    metadata.cols.artist_location[0] = song.artist_location.location.encode('utf-8') if song.artist_location.location else ''
    metadata.cols.artist_longitude[0] = song.artist_location.longitude
    metadata.cols.artist_name[0] = song.artist_name.encode('utf-8') if song.artist_name else ''
    metadata.cols.song_id[0] = song.id
    metadata.cols.song_hotttnesss[0] = song.song_hotttnesss
    metadata.cols.title[0] = song.title.encode('utf-8') if song.title else ''
    metadata.flush()
    # get the analysis table
    analysis = h5.root.analysis.songs
    analysis.danceability = song.audio_summary.danceability
    analysis.energy = song.audio_summary.energy
    analysis.flush()


def fill_hdf5_from_track(h5,track):
    """
    Fill an open hdf5 using all the content in a track object
    from the Echo Nest python API
    """
    # get the metadata table, fill it
    metadata = h5.root.metadata.songs
    #metadata.cols.analyzer_version[0] = track.analyzer_version
    metadata.cols.artist_name[0] = track.artist.encode('utf-8') if track.artist else ''
    metadata.cols.release[0] = track.release.encode('utf-8') if track.release else ''
    metadata.cols.title[0] = track.title.encode('utf-8') if track.title else ''
    metadata.flush()
    # get the analysis table, fill it
    analysis = h5.root.analysis.songs
    analysis.cols.analysis_sample_rate[0] = track.analysis_sample_rate
    analysis.cols.audio_md5[0] = track.audio_md5
    analysis.cols.duration[0] = track.duration
    analysis.cols.end_of_fade_in[0] = track.end_of_fade_in
    analysis.cols.key[0] = track.key
    analysis.cols.key_confidence[0] = track.key_confidence
    analysis.cols.loudness[0] = track.loudness
    analysis.cols.mode[0] = track.mode
    analysis.cols.mode_confidence[0] = track.mode_confidence
    analysis.cols.start_of_fade_out[0] = track.start_of_fade_out
    analysis.cols.tempo[0] = track.tempo
    analysis.cols.time_signature[0] = track.time_signature
    analysis.cols.time_signature_confidence[0] = track.time_signature_confidence
    analysis.cols.track_id[0] = track.id
    analysis.flush()
    group = h5.root.analysis
    # analysis arrays (segments)
    analysis.cols.idx_segments_start[0] = 0
    group.segments_start.append( np.array(map(lambda x : x['start'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_confidence[0] = 0
    group.segments_confidence.append( np.array(map(lambda x : x['confidence'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_pitches[0] = 0
    group.segments_pitches.append( np.array(map(lambda x : x['pitches'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_timbre[0] = 0
    group.segments_timbre.append( np.array(map(lambda x : x['timbre'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_loudness_max[0] = 0
    group.segments_loudness_max.append( np.array(map(lambda x : x['loudness_max'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_loudness_max_time[0] = 0
    group.segments_loudness_max_time.append( np.array(map(lambda x : x['loudness_max_time'],track.segments),dtype='float64') )
    analysis.cols.idx_segments_loudness_start[0] = 0
    group.segments_loudness_start.append( np.array(map(lambda x : x['loudness_start'],track.segments),dtype='float64') )
    # analysis arrays (sections)
    analysis.cols.idx_sections_start[0] = 0
    group.sections_start.append( np.array(map(lambda x : x['start'],track.sections),dtype='float64') )
    analysis.cols.idx_sections_confidence[0] = 0
    group.sections_confidence.append( np.array(map(lambda x : x['confidence'],track.sections),dtype='float64') )
    # analysis arrays (beats
    analysis.cols.idx_beats_start[0] = 0
    group.beats_start.append( np.array(map(lambda x : x['start'],track.beats),dtype='float64') )
    analysis.cols.idx_beats_confidence[0] = 0
    group.beats_confidence.append( np.array(map(lambda x : x['confidence'],track.beats),dtype='float64') )
    # analysis arrays (bars)
    analysis.cols.idx_bars_start[0] = 0
    group.bars_start.append( np.array(map(lambda x : x['start'],track.bars),dtype='float64') )
    analysis.cols.idx_bars_confidence[0] = 0
    group.bars_confidence.append( np.array(map(lambda x : x['confidence'],track.bars),dtype='float64') )
    # analysis arrays (tatums)
    analysis.cols.idx_tatums_start[0] = 0
    group.tatums_start.append( np.array(map(lambda x : x['start'],track.tatums),dtype='float64') )
    analysis.cols.idx_tatums_confidence[0] = 0
    group.tatums_confidence.append( np.array(map(lambda x : x['confidence'],track.tatums),dtype='float64') )
    analysis.flush()
    # DONE


def fill_hdf5_aggregate_file(h5,h5_filenames):
    """
    Fill an open hdf5 aggregate file using all the content from all the HDF5 files
    listed as filenames. These HDF5 files are supposed to be filled already.
    Usefull to create one big HDF5 file from many, thus improving IO speed.
    For most of the info, we simply use one row per song.
    For the arrays (e.g. segment_start) we need the indecies (e.g. idx_segment_start)
    to know which part of the array belongs to one particular song.
    """
    # counter
    counter = 0
    # iterate over filenames
    for h5idx,h5filename in enumerate(h5_filenames):
        # open h5 file
        h5tocopy = open_h5_file_read(h5filename)
        # get number of songs in new file
        nSongs = get_num_songs(h5tocopy)
        # iterate over songs in one HDF5 (1 if regular file, more if aggregate file)
        for songidx in xrange(nSongs):
            # METADATA
            row = h5.root.metadata.songs.row
            row["artist_familiarity"] = get_artist_familiarity(h5tocopy,songidx)
            row["artist_hotttnesss"] = get_artist_hotttnesss(h5tocopy,songidx)
            row["artist_id"] = get_artist_id(h5tocopy,songidx)
            row["artist_latitude"] = get_artist_latitude(h5tocopy,songidx)
            row["artist_location"] = get_artist_location(h5tocopy,songidx)
            row["artist_longitude"] = get_artist_longitude(h5tocopy,songidx)
            row["artist_name"] = get_artist_name(h5tocopy,songidx)
            row["release"] = get_release(h5tocopy,songidx)
            row["song_id"] = get_song_id(h5tocopy,songidx)
            row["song_hotttnesss"] = get_song_hotttnesss(h5tocopy,songidx)
            row["title"] = get_title(h5tocopy,songidx)
            row.append()
            h5.root.metadata.songs.flush()
            # ANALYSIS
            row = h5.root.analysis.songs.row
            row["analysis_sample_rate"] = get_analysis_sample_rate(h5tocopy,songidx)
            row["audio_md5"] = get_audio_md5(h5tocopy,songidx)
            row["danceability"] = get_danceability(h5tocopy,songidx)
            row["duration"] = get_duration(h5tocopy,songidx)
            row["end_of_fade_in"] = get_end_of_fade_in(h5tocopy,songidx)
            row["energy"] = get_energy(h5tocopy,songidx)
            row["key"] = get_key(h5tocopy,songidx)
            row["key_confidence"] = get_key_confidence(h5tocopy,songidx)
            row["loudness"] = get_loudness(h5tocopy,songidx)
            row["mode"] = get_mode(h5tocopy,songidx)
            row["mode_confidence"] = get_mode_confidence(h5tocopy,songidx)
            row["start_of_fade_out"] = get_start_of_fade_out(h5tocopy,songidx)
            row["tempo"] = get_tempo(h5tocopy,songidx)
            row["time_signature"] = get_time_signature(h5tocopy,songidx)
            row["time_signature_confidence"] = get_time_signature_confidence(h5tocopy,songidx)
            row["track_id"] = get_track_id(h5tocopy,songidx)
            # INDECIES
            if counter == 0 : # we're first row
                row["idx_segments_start"] = 0
                row["idx_segments_confidence"] = 0
                row["idx_segments_pitches"] = 0
                row["idx_segments_timbre"] = 0
                row["idx_segments_loudness_max"] = 0
                row["idx_segments_loudness_max_time"] = 0
                row["idx_segments_loudness_start"] = 0
                row["idx_sections_start"] = 0
                row["idx_sections_confidence"] = 0
                row["idx_beats_start"] = 0
                row["idx_beats_confidence"] = 0
                row["idx_bars_start"] = 0
                row["idx_bars_confidence"] = 0
                row["idx_tatums_start"] = 0
                row["idx_tatums_confidence"] = 0
            else : # check the current shape of the arrays
                row["idx_segments_start"] = h5.root.analysis.segments_start.shape[0]
                row["idx_segments_confidence"] = h5.root.analysis.segments_confidence.shape[0]
                row["idx_segments_pitches"] = h5.root.analysis.segments_pitches.shape[0]
                row["idx_segments_timbre"] = h5.root.analysis.segments_timbre.shape[0]
                row["idx_segments_loudness_max"] = h5.root.analysis.segments_loudness_max.shape[0]
                row["idx_segments_loudness_max_time"] = h5.root.analysis.segments_loudness_max_time.shape[0]
                row["idx_segments_loudness_start"] = h5.root.analysis.segments_loudness_start.shape[0]
                row["idx_sections_start"] = h5.root.analysis.sections_start.shape[0]
                row["idx_sections_confidence"] = h5.root.analysis.sections_confidence.shape[0]
                row["idx_beats_start"] = h5.root.analysis.beats_start.shape[0]
                row["idx_beats_confidence"] = h5.root.analysis.beats_confidence.shape[0]
                row["idx_bars_start"] = h5.root.analysis.bars_start.shape[0]
                row["idx_bars_confidence"] = h5.root.analysis.bars_confidence.shape[0]
                row["idx_tatums_start"] = h5.root.analysis.tatums_start.shape[0]
                row["idx_tatums_confidence"] = h5.root.analysis.tatums_confidence.shape[0]
            row.append()
            h5.root.analysis.songs.flush()
            # ARRAYS
            h5.root.analysis.segments_start.append( get_segments_start(h5tocopy,songidx) )
            h5.root.analysis.segments_confidence.append( get_segments_confidence(h5tocopy,songidx) )
            h5.root.analysis.segments_pitches.append( get_segments_pitches(h5tocopy,songidx) )
            h5.root.analysis.segments_timbre.append( get_segments_timbre(h5tocopy,songidx) )
            h5.root.analysis.segments_loudness_max.append( get_segments_loudness_max(h5tocopy,songidx) )
            h5.root.analysis.segments_loudness_max_time.append( get_segments_loudness_max_time(h5tocopy,songidx) )
            h5.root.analysis.segments_loudness_start.append( get_segments_loudness_start(h5tocopy,songidx) )
            h5.root.analysis.sections_start.append( get_sections_start(h5tocopy,songidx) )
            h5.root.analysis.sections_confidence.append( get_sections_confidence(h5tocopy,songidx) )
            h5.root.analysis.beats_start.append( get_beats_start(h5tocopy,songidx) )
            h5.root.analysis.beats_confidence.append( get_beats_confidence(h5tocopy,songidx) )
            h5.root.analysis.bars_start.append( get_bars_start(h5tocopy,songidx) )
            h5.root.analysis.bars_confidence.append( get_bars_confidence(h5tocopy,songidx) )
            h5.root.analysis.tatums_start.append( get_tatums_start(h5tocopy,songidx) )
            h5.root.analysis.tatums_confidence.append( get_tatums_confidence(h5tocopy,songidx) )
            # counter
            counter += 1
        # close h5 file
        h5tocopy.close()


def create_song_file(h5filename,title='H5 Song File',force=False,complevel=complevel):
    """
    Create a new HDF5 file for a new song.
    If force=False, refuse to overwrite an existing file
    Raise a ValueError if it's the case.
    Other optional param is the H5 file.
    Setups the groups, each containing a table 'songs' with one row:
    - metadata
    - analysis
    DETAIL
    - we set the compression level to 1 by default, it uses the ZLIB library
      to disable compression, set it to 0
    """
    # check if file exists
    if not force:
        if os.path.exists(h5filename):
            raise ValueError('file exists, can not create HDF5 song file')
    # create the H5 file
    h5 = tables.openFile(h5filename, mode='w', title='H5 Song File')
    # set filter level
    h5.filters = tables.Filters(complevel=complevel,complib='zlib')
    # setup the groups and tables
        # group metadata
    group = h5.createGroup("/",'metadata','metadata about the song')
    table = h5.createTable(group,'songs',DESC.SongMetaData,'table of metadata for one song')
    r = table.row
    r.append()
    table.flush()
        # group analysis
    group = h5.createGroup("/",'analysis','Echo Nest analysis of the song')
    table = h5.createTable(group,'songs',DESC.SongAnalysis,'table of Echo Nest analysis for one song')
    r = table.row
    r.append()
    table.flush()
        # create arrays in group analysis
    h5.createEArray(where=group,name='segments_start',atom=tables.Float64Atom(shape=()),shape=(0,),title=ARRAY_DESC_SEGMENTS_START)
    h5.createEArray(group,'segments_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_CONFIDENCE)
    h5.createEArray(group,'segments_pitches',tables.Float64Atom(shape=()),(0,12),ARRAY_DESC_SEGMENTS_PITCHES)
    h5.createEArray(group,'segments_timbre',tables.Float64Atom(shape=()),(0,12),ARRAY_DESC_SEGMENTS_TIMBRE)
    h5.createEArray(group,'segments_loudness_max',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_MAX)
    h5.createEArray(group,'segments_loudness_max_time',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_MAX_TIME)
    h5.createEArray(group,'segments_loudness_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_START)
    h5.createEArray(group,'sections_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SECTIONS_START)
    h5.createEArray(group,'sections_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SECTIONS_CONFIDENCE)
    h5.createEArray(group,'beats_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BEATS_START)
    h5.createEArray(group,'beats_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BEATS_CONFIDENCE)
    h5.createEArray(group,'bars_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BARS_START)
    h5.createEArray(group,'bars_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BARS_CONFIDENCE)
    h5.createEArray(group,'tatums_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_TATUMS_START)
    h5.createEArray(group,'tatums_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_TATUMS_CONFIDENCE)
    # close it, done
    h5.close()


def create_aggregate_file(h5filename,title='H5 Aggregate File',force=False,expectedrows=1000,complevel=1):
    """
    Create a new HDF5 file for all songs.
    It will contains everything that are in regular song files.
    Tables created empty.
    If force=False, refuse to overwrite an existing file
    Raise a ValueError if it's the case.
    Other optional param is the H5 file.
    DETAILS
    - if you create a very large file, try to approximate correctly
      the number of data points (songs), it speeds things up with arrays (by
      setting the chunking correctly).
    - we set the compression level to 1 by default, it uses the ZLIB library
      to disable compression, set it to 0

    Setups the groups, each containing a table 'songs' with one row:
    - metadata
    - analysis
    """
    # check if file exists
    if not force:
        if os.path.exists(h5filename):
            raise ValueError('file exists, can not create HDF5 song file')
    # create the H5 file
    h5 = tables.openFile(h5filename, mode='w', title='H5 Song File')
    # set filter level
    h5.filters = tables.Filters(complevel=complevel,complib='zlib')
    # setup the groups and tables
        # group metadata
    group = h5.createGroup("/",'metadata','metadata about the song')
    table = h5.createTable(group,'songs',DESC.SongMetaData,'table of metadata for one song',
                           expectedrows=expectedrows)
        # group analysis
    group = h5.createGroup("/",'analysis','Echo Nest analysis of the song')
    table = h5.createTable(group,'songs',DESC.SongAnalysis,'table of Echo Nest analysis for one song',
                           expectedrows=expectedrows)
        # group analysis arrays
    h5.createEArray(where=group,name='segments_start',atom=tables.Float64Atom(shape=()),shape=(0,),title=ARRAY_DESC_SEGMENTS_START)
    h5.createEArray(group,'segments_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_CONFIDENCE,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'segments_pitches',tables.Float64Atom(shape=()),(0,12),ARRAY_DESC_SEGMENTS_PITCHES,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'segments_timbre',tables.Float64Atom(shape=()),(0,12),ARRAY_DESC_SEGMENTS_TIMBRE,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'segments_loudness_max',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_MAX,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'segments_loudness_max_time',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_MAX_TIME,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'segments_loudness_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SEGMENTS_LOUDNESS_START,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'sections_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SECTIONS_START,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'sections_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_SECTIONS_CONFIDENCE,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'beats_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BEATS_START,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'beats_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BEATS_CONFIDENCE,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'bars_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BARS_START,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'bars_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_BARS_CONFIDENCE,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'tatums_start',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_TATUMS_START,
                    expectedrows=expectedrows*300)
    h5.createEArray(group,'tatums_confidence',tables.Float64Atom(shape=()),(0,),ARRAY_DESC_TATUMS_CONFIDENCE,
                    expectedrows=expectedrows*300)
    # close it, done
    h5.close()
    

def open_h5_file_read(h5filename):
    """
    Open an existing H5 in read mode.
    """
    return tables.openFile(h5filename, mode='r')

def open_h5_file_append(h5filename):
    """
    Open an existing H5 in append mode.
    """
    return tables.openFile(h5filename, mode='a')


################################################ MAIN #####################################

def die_with_usage():
    """ HELP MENU """
    print 'hdf5_utils.py'
    print 'by T. Bertin-Mahieux (2010) Columbia University'
    print ''
    print 'should be used as a library, contains functions to create'
    print 'HDF5 files for the Million Song Dataset project'
    sys.exit(0)


if __name__ == '__main__':

    # help menu
    die_with_usage()


