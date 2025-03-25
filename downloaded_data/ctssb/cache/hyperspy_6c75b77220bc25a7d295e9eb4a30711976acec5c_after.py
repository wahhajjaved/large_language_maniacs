#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright © 2007 Francisco Javier de la Peña
# Copyright © 2010 Francisco Javier de la Peña & Stefano Mazzucco
#
# This file is part of EELSLab.
#
# EELSLab is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# EELSLab is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EELSLab; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  
# USA

# Plugin to read the Gatan Digital Micrograph(TM) file format

from __future__ import with_statement #for Python versions < 2.6
from __future__ import division

import os
import mmap
import re
import numpy as np

# relative imports are discouraged (PEP0008)
from ..utils_readfile import *
from ..exceptions import *
from ..utils_varia import overwrite, swapelem
from ..utils_varia import DictBrowser, fsdict

# Plugin characteristics
# ----------------------
format_name = 'Digital Micrograph dm3'
description = 'Read data from Gatan Digital Micrograph (TM) files'
full_suport = False
# Recognised file extension
file_extensions = ('dm3', 'DM3')
default_extension = 0
# Reading features
reads_images = True
reads_spectrum = True
reads_spectrum_image = True
# Writing features
writes_images = False
writes_spectrum = False
writes_spectrum_image = False
# ----------------------

## used in crawl_dm3 ##
tag_group_pattern = re.compile('\.Group[0-9]{1,}$')
tag_data_pattern = re.compile('\.Data[0-9]{1,}$')
image_data_pattern = re.compile('\.Calibrations\.Data$')
micinfo_pattern = re.compile('\.Microscope Info$')
orsay_pattern = re.compile('\.spim$')
# root_pattern = re.compile('^\w{1,}\.')
image_tags_pattern = re.compile('.*ImageTags\.')
####

read_char = read_byte # dm3 uses chars for 1-Byte signed integers

def read_infoarray(f):
    """Read the infoarray from file f and return it.
    """
    infoarray_size = read_long(f, 'big')
    infoarray = [read_long(f, 'big') for index in range(infoarray_size)]
    infoarray = tuple(infoarray)
    return infoarray

def _infoarray_databytes(iarray):
    """Read the info array iarray and return the number of bytes
    of the corresponding TagData.
    """
    if iarray[0] in _complex_type:
        if iarray[0] == 18: # it's a string
            nbytes = iarray[1]
        elif iarray[0] == 15:   # it's a struct
            field_type =  [iarray[i] for i in range(4, len(iarray), 2)]
            field_bytes = [_data_type[i][1] for i in field_type]
            nbytes = reduce(lambda x, y: x +y, field_bytes)
        elif iarray[0] == 20:   # it's an array            
            if iarray[1] != 15:
                nbytes = iarray[-1] * _data_type[iarray[1]][1]
            else:  # it's an array of structs
                subiarray = iarray[1:-1]
                nbytes = _infoarray_databytes(subiarray) * iarray[-1]
    elif iarray[0] in _simple_type:
        nbytes = _data_type[iarray[0]][1]
    else:
        raise DM3DataTypeError(iarray[0])
    return nbytes
 
def read_string(f, iarray, endian):
    """Read a string defined by the infoArray iarray from
     file f with a given endianness (byte order).
    endian can be either 'big' or 'little'.

    If it's a tag name, each char is 1-Byte;
    if it's a tag data, each char is 2-Bytes Unicode,
    UTF-16-BE or UTF-16-LE.
    E.g 43 00 for little-endian files (UTF-16-LE)
    i.e. a char followed by an empty Byte.
    E.g 'hello' becomes 'h.e.l.l.o.' in UTF-16-LE
    """    
    if (endian != 'little') and (endian != 'big'):
        print('File address:', f.tell())
        raise ByteOrderError(endian)
    else:
        if iarray[0] != 18:
            print('File address:', f.tell())
            raise DM3DataTypeError(iarray[0])
        data = ''
        if endian == 'little':
            s = L_char
        elif endian == 'big':
            s = B_char
        for char in range(iarray[1]):
            data += s.unpack(f.read(1))[0]
        if '\x00' in data:      # it's a Unicode string (TagData)
            uenc = 'utf_16_'+endian[0]+'e'
            data = unicode(data, uenc, 'replace')
        return data

def read_struct(f, iarray, endian):
    """Read a struct, defined by iarray, from file f
    with a given endianness (byte order).
    Returns a list of 2-tuples in the form
    (fieldAddress, fieldValue).
    endian can be either 'big' or 'little'.
    """
    if (endian != 'little') and (endian != 'big'):
        print('File address:', f.tell())
        raise ByteOrderError(endian)
    else:    
        if iarray[0] != 15:
            print('File address:', f.tell())
            raise DM3DataTypeError(iarray[0])
        # name_length = iarray[1]
        # name_length always 0?
        # n_fields = iarray[2]
        # field_name_length = [iarray[i] for i in range(3, len(iarray), 2)]
        # field_name_length always 0?
        field_type =  [iarray[i] for i in range(4, len(iarray), 2)]
        # field_ctype = [_data_type[iarray[i]][2] for i in range(4, len(iarray), 2)]
        field_addr = []
        # field_bytes = [_data_type[i][1] for i in field_type]
        field_value = []
        for dtype in field_type:
            if dtype in _simple_type:
                field_addr.append(f.tell())
                read_data = _data_type[dtype][0]
                data = read_data(f, endian)
                field_value.append(data)
            else:
                raise DM3DataTypeError(dtype)    
        return zip(field_addr, field_value)
    
def read_array(f, iarray, endian):
    """Read an array, defined by iarray, from file f
    with a given endianness (byte order).
    endian can be either 'big' or 'little'.
    """
    if (endian != 'little') and (endian != 'big'):
        print('File address:', f.tell())
        raise ByteOrderError(endian)
    else:        
        if iarray[0] != 20:
            print('File address:', f.tell())
            raise DM3DataTypeError(iarray[0])
        arraysize = iarray[-1]
        if arraysize == 0:
            return None
        eltype = _data_type[iarray[1]][0] # same for all elements
        if len(iarray) > 3:  # complex type
            subiarray = iarray[1:-1]
            data = [eltype(f, subiarray, endian)
                    for element in range(arraysize)]
        else: # simple type
            data = [eltype(f, endian) for element in range(arraysize)]
            if iarray[1] == 4: # it's actually a string
                # disregard values that are not characters:
                data = [chr(i) for i in data if i in range(256)]
                data = reduce(lambda x, y: x + y, data)
        return data
    
# _data_type dictionary.
# The first element of the InfoArray in the TagType
# will always be one of _data_type keys.
# the tuple reads: ('read bytes function', 'number of bytes', 'type')
_data_type = {
    2 : (read_short, 2, 'h'),
    3 : (read_long, 4, 'l'),
    4 : (read_ushort, 2, 'H'), # dm3 uses ushorts for unicode chars
    5 : (read_ulong, 4, 'L'),
    6 : (read_float, 4, 'f'),
    7 : (read_double, 8, 'd'),
    8 : (read_boolean, 1, 'B'),
    9 : (read_char, 1, 'b'), # dm3 uses chars for 1-Byte signed integers
    10 : (read_byte, 1, 'b'),   # 0x0a
    15 : (read_struct, None, 'struct',), # 0x0f
    18 : (read_string, None, 'c'), # 0x12
    20 : (read_array, None, 'array'),  # 0x14
    }
                          
_complex_type = (10, 15, 18, 20)
_simple_type =  (2, 3, 4, 5, 6, 7, 8, 9, 10)

def parse_tag_group(f, endian='big'):
    """Parse the root TagGroup of the given DM3 file f.
    Returns the tuple (is_sorted, is_open, n_tags).
    endian can be either 'big' or 'little'.
    """
    is_sorted = read_byte(f, endian)
    is_open = read_byte(f, endian)
    n_tags = read_long(f, endian)
    return bool(is_sorted), bool(is_open), n_tags

def parse_tag_entry(f, endian='big'):
    """Parse a tag entry of the given DM3 file f.
    Returns the tuple (tag_id, tag_name_length, tag_name).
    endian can be either 'big' or 'little'.
    """
    tag_id = read_byte(f, endian)
    tag_name_length = read_short(f, endian)
    str_infoarray = (18, tag_name_length)
    tag_name_arr = read_string(f, str_infoarray, endian)
    if len(tag_name_arr):
        tag_name = reduce(lambda x, y: x + y, tag_name_arr)
    else:
        tag_name = ''
    return tag_id, tag_name_length, tag_name

def parse_tag_type(f):
    """Parse a tag type of the given DM3 file f.
    Returns the tuple infoArray.
    """
    str_infoarray = (18, 4)
    delim = read_string(f, str_infoarray, 'big')
    delimiter = reduce(lambda x, y: x + y, delim)
    if delimiter != '%%%%':
        print('Wrong delimiter: "%s".' % str(delimiter))
        print('File address:', f.tell())
        raise DM3TagTypeError(delimiter)
    else:        
        return read_infoarray(f)
       
def parse_tag_data(f, iarray, endian, skip=0):
    """Parse the data of the given DM3 file f
    with the given endianness (byte order).
    The infoArray iarray specifies how to read the data.
    Returns the tuple (file address, data).
    The tag data is stored in the platform's byte order:
    'little' endian for Intel, PC; 'big' endian for Mac, Motorola.
    If skip != 0 the data is actually skipped.
    """
    faddress = f.tell()
    # nbytes = _infoarray_databytes(iarray)
    if not skip:
        read_data = _data_type[iarray[0]][0]
        if iarray[0] in _complex_type:
            data = read_data(f, iarray, endian)
        elif iarray[0] in _simple_type:
            data = read_data(f, endian)
        else:
            raise DM3DataTypeError(iarray[0])
    else:
        data = '__skipped__'        
        # print('Skipping', nbytes, 'Bytes.')
        nbytes = _infoarray_databytes(iarray)
        f.seek(nbytes, 1)
    # return faddress, nbytes, data
    return faddress, data

def parse_image_data(f, iarray):
    """Returns a tuple with the file offset and the number
    of bytes corresponding to the image data:
    (offset, bytes)
    """
    faddress = f.tell()
    nbytes = _infoarray_databytes(iarray)
    f.seek(nbytes, 1)        
    return faddress, nbytes

def parse_header(f, data_dict, endian='big', debug=0):
    """Parse the header (first 12 Bytes) of the given DM3 file f.
    The relevant information is saved in the dictionary data_dict.
    Optionally, a debug level !=0 may be specified.
    endian can be either 'little' or 'big'.
    Returns the boolean is_little_endian (byte order) of the DM3 file.
    """
    iarray = (3, ) # long
    dm_version = parse_tag_data(f, iarray, endian)
    if dm_version[1] != 3:
        print('File address:', dm_version[1])
        raise DM3FileVersionError(dm_version[1])
    data_dict['DM3.Version'] = dm_version

    filesizeB = parse_tag_data(f, iarray, endian)
    filesizeB = list(filesizeB)
    filesizeB[1] = filesizeB[1] + 16
    filesizeB = tuple(filesizeB)
    data_dict['DM3.FileSize'] = filesizeB

    is_little_endian = parse_tag_data(f, iarray, endian)
    data_dict['DM3.isLittleEndian'] = is_little_endian

    if debug > 0:
        filesizeKB = filesizeB[1] / 2.**10
        # filesizeMB = filesizeB[3] / 2.**20
        print('DM version:', dm_version[1])
        print('size %i B (%.2f KB)' % (filesizeB[1], filesizeKB))
        # print 'size: {0} B ({1:.2f} KB)'.format(filesizeB[1] , filesizeKB)
        print('Is file Little endian?', bool(is_little_endian[1]))
    return bool(is_little_endian[1])

def crawl_dm3(f, data_dict, endian, ntags, group_name='root',
             skip=0, debug=0):
    """Recursively scan the ntags TagEntrys in DM3 file f
    with a given endianness (byte order) looking for
    TagTypes (data) or TagGroups (groups).
    endian can be either 'little' or 'big'.
    The dictionary data_dict is filled with tags and data.
    Each key is generated in a file system fashion using
    '.' as separator.
    e.g. key = 'root.dir0.dir1.dir2.value0'
    If skip != 0 the data reading is actually skipped.
    If debug > 0, 3, 5, 10 useful debug information is printed on screen.
    """
    for tag in range(ntags):
        if debug > 3 and debug < 10:
            print('Crawling at address:', f.tell())

        tag_id, tag_name_length, tag_name = parse_tag_entry(f)

        if debug > 5 and debug < 10:
            print('Tag name:', tag_name)
            print('Tag ID:', tag_id)
            
        if tag_id == 21: # it's a TagType (DATA)
            if not tag_name:
                tag_name = 'Data0'

            data_key = group_name + '.' + tag_name

            if debug > 3 and debug < 10:
                print('Crawling at address:', f.tell())

            infoarray = parse_tag_type(f)

            if debug > 5 and debug < 10:
                print('Infoarray:', infoarray)

            # Don't overwrite duplicate keys, just rename them
            while data_dict.has_key(data_key):
                data_search = tag_data_pattern.search(data_key)
                tag_name = data_search.group()
                j = int(tag_name.strip('.Data'))
                data_key = tag_data_pattern.sub('', data_key)
                if debug > 5 and debug < 10:
                    print('key exists... renaming')
                tag_name = '.Data' + str(j+1)
                data_key = data_key + tag_name

            if image_data_pattern.search(data_key):
                # don't read the data now            
                data_dict[data_key] = parse_image_data(f, infoarray)
            else:
                data_dict[data_key] = parse_tag_data(f, infoarray,
                                                       endian, skip)
            if debug > 10:
                try:
                    if not raw_input('(debug) Press "Enter" to continue\n'):
                        print '######################################'
                        print 'TAG:\n', data_key, '\n'
                        print 'ADDRESS:\n', data_dict[data_key][0], '\n'
                        try:
                            if len(data_dict[data_key][1]) > 10:
                                print 'VALUE:'
                                print data_dict[data_key][1][:10], '[...]\n'
                            else:
                                print 'VALUE:\n', data_dict[data_key][1], '\n'
                        except:
                            print 'VALUE:\n', data_dict[data_key][1], '\n'
                        print '######################################\n'
                except KeyboardInterrupt:
                    print '\n\n###################'
                    print 'Operation canceled.'
                    print '###################\n\n'
                    raise       # exit violently

        elif tag_id == 20: # it's a TagGroup (GROUP)
            if not tag_name:
                tag_name = '.Group0'
                # don't duplicate subgroups, just rename them
                group_search = tag_group_pattern.search(group_name)
                if group_search:
                    tag_name = group_search.group()
                    j = int(tag_name.strip('.Group')) 
                    group_name = tag_group_pattern.sub('', group_name)
                    tag_name = '.Group' + str(j+1)
                    group_name = group_name + tag_name
                else:
                    group_name = group_name + tag_name
            else:
                orsay_search = orsay_pattern.search(group_name)
                if orsay_search: # move orsay-specific dir in the ImageTags dir
                    o = 'Orsay' + orsay_search.group()
                    r = image_tags_pattern.search(group_name).group()
                    group_name = r + o
                micinfo_search = micinfo_pattern.search(group_name)
                if micinfo_search: # move Microscope Info in the ImageTags dir
                    m = micinfo_search.group()[1:]
                    r = image_tags_pattern.search(group_name).group()
                    group_name = r + m
                group_name += '.' + tag_name
            if debug > 3 and debug < 10:
                print('Crawling at address:', f.tell())
            ntags = parse_tag_group(f)[2]
            crawl_dm3(f, data_dict, endian, ntags, group_name,
                      skip, debug) # recursion
        else:
            print('File address:', f.tell())
            raise DM3TagIDError(tag_id)

def open_dm3(fname, skip=0, debug=0, log=''):
    """Open a DM3 file given its name and return the dictionary data_dict
    containint the parsed information.
    If skip != 0 the data is actually skipped.
    Optionally, a debug value debug > 0 may be given.
    If log='filename' is specified, the keys, file address and
    (part of) the data parsed in data_dict are written in the log file.

    NOTE:
    All fields, except the TagData are stored using the Big-endian
    byte order. The TagData are stored in the platform's
    byte order (e.g. 'big' for Mac, 'little' for PC).
    """
    with open(fname, 'r+b') as dm3file:
        fmap = mmap.mmap(dm3file.fileno(), 0, access=mmap.ACCESS_READ)
        data_dict = {}
        if parse_header(fmap, data_dict, debug=debug):
            fendian = 'little'
        else:
            fendian = 'big'
        rntags = parse_tag_group(fmap)[2]
        if debug > 3:
            print('Total tags in root group:', rntags)
        rname = 'DM3'
        crawl_dm3(fmap, data_dict, fendian, rntags, group_name=rname,
                  skip=skip, debug=debug)
#         if platform.system() in ('Linux', 'Unix'):
#             try:
#                 fmap.flush()
#             except:
#                 print("Error. Could not write to file", fname)
#         if platform.system() in ('Windows', 'Microsoft'):
#             if fmap.flush() == 0:
#                 print("Error. Could not write to file", fname)
        fmap.close()

        if log:
            exists = overwrite(log)
            if exists:
                with open(log, 'w') as logfile:
                    for key in data_dict:
                        try:
                            line = '%s    %s    %s' % (key, data_dict[key][0],
                                                       data_dict[key][1][:10])
                        except:
                            try:
                                line = '%s    %s    %s' % (key,
                                                           data_dict[key][0],
                                                           data_dict[key][1])
                            except:
                                line = '%s    %s    %s' % (key,
                                                           data_dict[key][0],
                                                           data_dict[key][1])
                        print >> logfile, line, '\n'
                print('Logfile %s saved in current directory' & log)
                
        # Convert data_dict into a file system-like dictionary, datadict_fs
        datadict_fs = {}
        for nodes in data_dict.items():
            fsdict(nodes[0].split('.'), nodes[1], datadict_fs)
        fsbrowser =  DictBrowser(datadict_fs) # browsable dictionary'
        return fsbrowser    
   
class DM3ImageFile(object):
    """ Class to handle Gatan Digital Micrograph (TM) files.
    """

    format = 'dm3'
    format_description = 'Gatan Digital Micrograph (TM) Version 3'

    # Image data types (Image Object chapter on DM help)#
    # key = DM data type code
    # value = numpy data type
    imdtype_dict = {
        0 : 'not_implemented', # null
        1 : 'int16',
        2 : 'float32',
        3 : 'complex64',
        4 : 'not_implemented', # obsolete
        5 : 'complex64_packed', # not numpy: 8-Byte packed complex (FFT data)
        6 : 'uint8',
        7 : 'int32',
        8 : 'argb', # not numpy: 4-Byte RGB (alpha, R, G, B)
        9 : 'int8',
        10 : 'uint16',
        11 : 'uint32',
        12 : 'float64',
        13 : 'complex128',
        14 : 'bool',
        23 : 'rgb', # not numpy: 4-Byte RGB (0, R, G, B)
        }
    
    rootdir = ['DM3',]
    endian = rootdir + ['isLittleEndian',]
    version = rootdir + ['Version',]
    micinfodir = rootdir + ['Microscope Info',]
    rootdir = rootdir + ['DocumentObjectList',] # DocumentTags, Group0..
    imlistdir = rootdir + ['DocumentTags', 'Image Behavior', 'ImageList']
    # imlistdir contains ImageSourceList, Group0, Group1, ... Group[N]
    # "GroupX" dirs contain the useful info in subdirs
    # Group0 is always THUMBNAIL (?)
    # imdisplaydir = ['AnnotationGroupList', 'ImageDisplayInfo']
    # clutname = imdisplaydir + ['CLUTName',] # Greyscale, Rainbow or Temperature
    imdatadir = ['ImageData',]
    imtagsdir = imdatadir + ['ImageTags',]
    imname = imtagsdir + ['Name',]
    orsaydir = imtagsdir + ['Orsay', 'spim', 'detectors', 'eels']
    vsm = orsaydir + ['vsm',]
    dwelltime = orsaydir + ['dwell time',]
    orsaymicdir = orsaydir + ['microscope',]
    calibdir = imdatadir + ['Calibrations',] # ['DataType', 'Data',
                                             # 'Dimensions', 'Brightness']
    im = calibdir + ['Data',]     # file addres and size of image
    imdtype = calibdir + ['DataType',] # data type to compare with imdtype_dict
    brightdir = calibdir + ['Brightness',]
    dimdir = calibdir + ['Dimensions',] # contains 'Data[X]' where
                                        # X is the dimension
    pixdepth = dimdir + ['PixelDepth', ]
    dimtagdir = brightdir + ['Dimension',] # contains 'Data[X]' where
                                           # X is the dimension
    units = ['Units',]          # in dimtagdir + 'Data[X]
    origin = ['Origin',]        # in dimtagdir + 'Data[X]
    scale = ['Scale',]          # in dimtagdir + 'Data[X]

    def __init__(self, fname, data_id=1):
        self.filename = fname
        self.info = '' # should be a dictionary with the microscope info
        self.mode = ''
        if data_id < 0:
            raise ImageIDError(data_id)
        else:
            self.data_id = data_id
        self.open()

    def __repr__(self):
        message = 'Instance of ' + repr(self.__class__)
        message += '\n' + self.mode + ' ' + str(self.imsize)
        return message

    def open(self):        
        self.data_dict = open_dm3(self.filename)
        byte_order = self.data_dict.ls(DM3ImageFile.endian)[1][1]
        if byte_order == 1:
            self.byte_order = 'little'
        elif byte_order == 0:
            self.byte_order = 'big'
        else:
            raise ByteOrderError, byte_order
        self.endian = self.byte_order
                    
        self.data_dict.cd(DM3ImageFile.imlistdir) # enter ImageList

        image_id = [im for im in self.data_dict.ls() if ('Group' in im
                                                         and im != 'Group0')]
        #Group0 is THUMBNAIL and GroupX (X !=0) is IMAGE
        image_id.sort()

        if len(image_id) > 1 or self.data_id == 0:
            print 'File "%s" contains %i images:' % (self.filename,
                                                     len(image_id))
            print
            print 'ID  | Name'
            print '    |     '
            for i in image_id:
                imid, imname = (image_id.index(i) + 1,
                        self.data_dict.ls([i,] + DM3ImageFile.imname)[1][1])
                print ' ', imid, '|', imname
            print '_____________'

            if self.data_id == 0:
                print 'Image ID "%i" is not valid.' % self.data_id
                print 'Please specify a valid image ID'
                return None
        try:
            im = image_id[self.data_id - 1]
            name = self.data_dict.ls([im,] + DM3ImageFile.imname)
            if name:
                self.name = self.data_dict.ls([im,] + DM3ImageFile.imname)[1][1]
            else:
                self.name = self.filename
            print 'Loading image "%s" (ID: %i) from file %s'% (self.name,
                                                               self.data_id,
                                                               self.filename)
        except IndexError:
            raise ImageIDError(self.data_id)

        self.data_dict.cd(image_id[self.data_id - 1]) # enter Group[ID]

        try:
            self.exposure =  self.data_dict.ls(DM3ImageFile.dwelltime)[1][1]
        except:
            self.exposure = None
        try:
            self.vsm =  self.data_dict.ls(DM3ImageFile.vsm)[1][1]
        except:
            self.vsm = None

        imdtype =  self.data_dict.ls(DM3ImageFile.imdtype)[1][1]
        self.imdtype = DM3ImageFile.imdtype_dict[imdtype]

        self.byte_offset = self.data_dict.ls(DM3ImageFile.im)[1][0]

        self.imbytes = self.data_dict.ls(DM3ImageFile.im)[1][1]

        self.pixel_depth =  self.data_dict.ls(DM3ImageFile.pixdepth)[1][1]

        sizes = []
        for i in self.data_dict.ls(DM3ImageFile.dimdir):
            if 'Data' in i:
                sizes.append((i,
                              self.data_dict.ls(DM3ImageFile.dimdir
                                                + [i,])))
        sizes.sort()
        swapelem(sizes, 0, 1)

        origins = []
        for i in self.data_dict.ls(DM3ImageFile.dimtagdir):
            if 'Group' in i:
                origins.append((i,
                                self.data_dict.ls(DM3ImageFile.dimtagdir
                                                  + [i,]
                                                  + DM3ImageFile.origin)))
        origins.sort()
        swapelem(origins, 0, 1)
        
        scales = []
        for i in self.data_dict.ls(DM3ImageFile.dimtagdir):
            if 'Group' in i:
                scales.append((i,
                               self.data_dict.ls(DM3ImageFile.dimtagdir
                                                    + [i,]
                                                    + DM3ImageFile.scale)))
        scales.sort()
        swapelem(scales, 0, 1)

        units = []
        for i in self.data_dict.ls(DM3ImageFile.dimtagdir):
            if 'Group' in i:
                units.append((i,
                              self.data_dict.ls(DM3ImageFile.dimtagdir
                                                + [i,]
                                                + DM3ImageFile.units)))
        units.sort()
        swapelem(units, 0, 1)
        
        self.dimensions = [ (sizes[i][1][1][1],
                        origins[i][1][1][1],
                        scales[i][1][1][1],
                        units[i][1][1][1])
                       for i in range(len(sizes))]

        self.imsize = [self.dimensions[i][0]
                       for i in range(len(self.dimensions))]
       
        br_orig = self.data_dict.ls(DM3ImageFile.brightdir
                                    + DM3ImageFile.origin)[1][1]
        br_scale = self.data_dict.ls(DM3ImageFile.brightdir
                                     + DM3ImageFile.scale)[1][1]
        br_units = self.data_dict.ls(DM3ImageFile.brightdir
                                     + DM3ImageFile.units)[1][1]
        self.brightness = (br_orig, br_scale, br_units)

        # self.data = self.read_image_data()
        try:
            self.data = self.read_image_data()

        except AttributeError:
            print('Error. Could not read data.')
            self.data = 'UNAVAILABLE'
            return None

        if 1 in self.data.shape:
            # remove dimensions of lenght 1, they are useless
            for i in range(len(self.data.shape)):
                if self.data.shape[i] == 1:
                    self.dimensions.pop(i)
                    self.imsize.pop(i)
            self.data = self.data.squeeze()

        d = len(self.dimensions)
        if d == 0: # could also implement a dictionary...
            raise ImageModeError(d)
        else:
            self.mode += str(d) + 'D'

    def read_image_data(self):
        if self.imdtype == 'not_implemented':
            raise AttributeError, "image data type: %s" % self.imdtype
        if ('packed' in self.imdtype):
            return  self.read_packed_complex()
        elif ('rgb' in self.imdtype):
            return self.read_rgb()
        else:
            data = read_data_array(self.filename, self.imbytes,
                                   self.byte_offset, self.imdtype)
            if len(self.dimensions) == 3:
                order = 'F'
            else:
                order = 'C'
            data = data.reshape(self.imsize, order=order)
            if len(self.dimensions) == 3:
                # The Bytes in a SI are ordered as
                # X0, Y0, Z0, X1, Y0, Z0, [...], Xn, Ym, Z0, [...]
                # X0, Y0, Z1, [...], Xn, Ym, Zk
                # since X <=> column and Y <=> row
                # the 1st two axes of the ndarray must be transposed
                # because its natural order is
                # row (Y), column (X), E                
                data = data.transpose((1,0,2))
            return data
            
    def read_rgb(self):
        self.imsize = list(self.imsize)
        self.imsize.append(4)
        self.imsize = tuple(self.imsize)
        data = read_data_array(self.filename, self.imbytes,
                               self.byte_offset, mode='r')
        data = data.reshape(self.imsize, order='C') # (B, G, R, A)
        if self.imdtype == 'rgb':
            data = data[:, :, -2::-1] # (R, G, B)
            self.mode += 'rgb_'
            self.imsize = list(self.imsize)
            self.imsize[-1] = self.imsize[-1] - 1
            self.imsize = tuple(self.imsize)
        elif self.imdtype == 'argb':
            data = np.concatenate((data[:, :, -2::-1], data[:, :, -1:]),
                                  axis=2) # (R, G, B, A)
            self.mode += 'rgba_'
        return data

    def read_packed_complex(self):
        if (self.imsize[0] != self.imsize[1]) or (len(self.imsize)>2):
            msg = "Packed complex format works only for a 2Nx2N image"
            msg += " -> width == height"
            print msg
            raise ImageModeError('FFT')
        print "This image is likely a FFT and each pixel is a complex number"
        print "You might want to display its complex norm"
        print "with a logarithmic intensity scale: log(abs(IMAGE))"
        self.mode += 'FFT_'
        N = int(self.imsize[0] / 2)      # think about a 2Nx2N matrix
        # read all the bytes as 1D array of 4-Byte float
        tmpdata = read_data_array(self.filename, self.imbytes,
                                   self.byte_offset, 'float32', mode='r')
        # tmpdata =  np.ndarray( (self.imbytes/4, ), 'float32',
        #                        fmap.read(self.imbytes), order='C')
        
        # create an empty 2Nx2N ndarray of complex
        data = np.zeros(self.imsize, 'complex64', 'C')
        
        # fill in the real values:
        data[N, 0] = tmpdata[0]
        data[0, 0] = tmpdata[1]
        data[N, N] = tmpdata[2*N**2] # Nyquist frequency
        data[0, N] = tmpdata[2*N**2+1] # Nyquist frequency
                
        # fill in the non-redundant complex values:
        # top right quarter, except 1st column
        for i in range(N): # this could be optimized
            start = 2 * i * N + 2
            stop = start + 2 * (N - 1) - 1
            step = 2
            realpart = tmpdata[start:stop:step]
            imagpart = tmpdata[start+1:stop+1:step]
            data[i, N+1:2*N] = realpart + imagpart * 1j
        # 1st column, bottom left quarter
        start = 2 * N
        stop = start + 2 * N * (N - 1) - 1
        step = 2 * N
        realpart = tmpdata[start:stop:step]
        imagpart = tmpdata[start+1:stop+1:step]
        data[N+1:2*N, 0] = realpart + imagpart * 1j
        # 1st row, bottom right quarter
        start = 2 * N**2 + 2
        stop = start + 2 * (N - 1) - 1
        step = 2
        realpart = tmpdata[start:stop:step]
        imagpart = tmpdata[start+1:stop+1:step]
        data[N, N+1:2*N] = realpart + imagpart * 1j
        # bottom right quarter, except 1st row
        start = stop + 1
        stop = start + 2 * N * (N - 1) - 1
        step = 2
        realpart = tmpdata[start:stop:step]
        imagpart = tmpdata[start+1:stop+1:step]
        complexdata = realpart + imagpart * 1j
        data[N+1:2*N, N:2*N] = complexdata.reshape(N-1, N)

        # fill in the empty pixels: A(i)(j) = A(2N-i)(2N-j)*
        # 1st row, top left quarter, except 1st element
        data[0, 1:N] = np.conjugate(data[0, -1:-N:-1])
        # 1st row, bottom left quarter, except 1st element
        data[N, 1:N] = np.conjugate(data[N, -1:-N:-1])
        # 1st column, top left quarter, except 1st element
        data[1:N, 0] = np.conjugate(data[-1:-N:-1, 0])
        # 1st column, top right quarter, except 1st element
        data[1:N, N] = np.conjugate(data[-1:-N:-1, N])
        # top left quarter, except 1st row and 1st column
        data[1:N, 1:N] = np.conjugate(data[-1:-N:-1, -1:-N:-1])
        # bottom left quarter, except 1st row and 1st column
        data[N+1:2*N, 1:N] = np.conjugate(data[-N-1:-2*N:-1, -1:-N:-1])

        return data

def file_reader(filename, data_type=None, data_id=1, old = True):
    """Reads a DM3 file and loads the data into the appropriate class.
    data_id can be specified to load a given image within a DM3 file that
    contains more than one dataset.

    If 'old' is True, will use the old DM3 reader from digital_micrograph.py
    module. Hopefully, this option will be removed soon.
    """
    if old:
        import digital_micrograph as dm_old
        return dm_old.file_reader(filename, data_type=data_type)  
        
    dm3 = DM3ImageFile(filename, data_id)

    calibration_dict = {}
    acquisition_dict = {}

    if '2D' in dm3.mode:
        # gotta find a better way to do this
        if 'm' in dm3.units:
            data_type = 'Image'
        else:
            data_type = 'SI'
    elif '3D' in dm3.mode:
        data_type = 'SI'
    elif '1D' in dm3.mode:
        data_type = 'SI'
    else:
        raise IOError, 'data type "%s" not recognized' % dm3.mode

    calibration_dict['dimensions'] = dm3.dimensions
    calibration_dict['mode'] = dm3.mode

    if dm3.name:
        calibration_dict['title'] = dm3.name
    else:
        calibration_dict['title'] =  os.path.splitext(filename)[0]

    data_cube = dm3.data

    # Determine the dimensions
    units = [dm3.dimensions[i][3] for i in range(len(dm3.dimensions))]
    origins = np.asarray([dm3.dimensions[i][1]
                          for i in range(len(dm3.dimensions))],
                         dtype=np.float)
    scales =np.asarray([dm3.dimensions[i][2]
                        for i in range(len(dm3.dimensions))],
                       dtype=np.float)    
    # Scale the origins
    origins = origins * scales
    
    if data_type == 'SI': 
        print("Treating the data as an SI")

        # only Orsay Spim is supported for now
        # does anyone have other kinds of SIs for testing?
        if dm3.exposure:
            acquisition_dict['exposure'] = dm3.exposure            
        if dm3.vsm:
            calibration_dict['vsm'] = float(dm3.vsm)

        # In EELSLab1 the first index must be the energy
        # (this will change in EELSLab2)
        if 'eV' in units: # could use regular expressions or compare to a 'energy units' dictionary/list
            energy_index = units.index('eV')
        elif 'keV' in units:
            energy_index = units.index('keV')
        else:
            energy_index = -1

        # In DM the origin is negative. Change it to positive
        origins[energy_index] *= -1
        
        # Rearrange the data_cube and parameters to have the energy first
        # THIS MAY NOT WORK WITH SPLIs/ChronoSPLIS
        data_cube = np.rollaxis(data_cube, energy_index, 0)
        origins = np.roll(origins, 1)
        scales = np.roll(scales, 1)
        units = np.roll(units, 1)

        # Store the calibration in the calibration dict
        origins_keys = ['energyorigin', 'yorigin', 'xorigin']
        scales_keys = ['energyscale', 'yscale', 'xscale']
        units_keys = ['energyunits', 'yunits', 'xunits']

        for value in origins:
            calibration_dict.__setitem__(origins_keys.pop(0), value)

        for value in scales:
            calibration_dict.__setitem__(scales_keys.pop(0), value)

        for value in units:
            calibration_dict.__setitem__(units_keys.pop(0), value)

    elif data_type == 'Image':
        print("Treating the data as an image")
        
        origins_keys = ['xorigin', 'yorigin', 'zorigin']
        scales_keys = ['xscale', 'yscale', 'zscale']
        units_keys = ['xunits', 'yunits', 'zunits']

        for value in origins:
            calibration_dict.__setitem__(origins_keys.pop(0), value)

        for value in scales:
            calibration_dict.__setitem__(scales_keys.pop(0), value)

        for value in units:
            calibration_dict.__setitem__(units_keys.pop(0), value)
    else:
        raise TypeError, "could not identify the file data_type"

    calibration_dict['data_cube'] = data_cube

    dictionary = {
        'data_type' : data_type, 
        'calibration' : calibration_dict, 
        'acquisition' : acquisition_dict,
        'imported_parameters' : calibration_dict}
    
    return [dictionary, ]
