# Created By: Virgil Dupras
# Created On: 2006/11/13
# $Id$
# Copyright 2009 Hardcoded Software (http://www.hardcoded.net)
# 
# This software is licensed under the "HS" License as described in the "LICENSE" file, 
# which should be included with this package. The terms are also available at 
# http://www.hardcoded.net/licenses/hs_license

import os.path as op
import logging
import plistlib
import re

from Foundation import *
from AppKit import *
from appscript import app, k, CommandError

from hsutil import io
from hsutil.str import get_file_ext
from hsutil.path import Path
from hsutil.cocoa import as_fetch

from dupeguru import fs
from dupeguru import app_cocoa, directories
from . import data
from .cache import string_to_colors, Cache
from .scanner import ScannerPE

mainBundle = NSBundle.mainBundle()
PictureBlocks = mainBundle.classNamed_('PictureBlocks')
assert PictureBlocks is not None

class Photo(fs.File):
    INITIAL_INFO = fs.File.INITIAL_INFO.copy()
    INITIAL_INFO.update({
        'dimensions': (0,0),
    })
    HANDLED_EXTS = set(['png', 'jpg', 'jpeg', 'gif', 'psd', 'bmp', 'tiff', 'tif', 'nef', 'cr2'])
    
    @classmethod
    def can_handle(cls, path):
        return fs.File.can_handle(path) and get_file_ext(path[-1]) in cls.HANDLED_EXTS
    
    def _read_info(self, field):
        fs.File._read_info(self, field)
        if field == 'dimensions':
            size = PictureBlocks.getImageSize_(unicode(self.path))
            self.dimensions = (size.width, size.height)
    
    def get_blocks(self, block_count_per_side):
        try:
            blocks = PictureBlocks.getBlocksFromImagePath_blockCount_(unicode(self.path), block_count_per_side)
        except Exception as e:
            raise IOError('The reading of "%s" failed with "%s"' % (unicode(self.path), unicode(e)))
        if not blocks:
            raise IOError('The picture %s could not be read' % unicode(self.path))
        return string_to_colors(blocks)
    

class IPhoto(Photo):
    @property
    def display_path(self):
        return Path(('iPhoto Library', self.name))
    
def get_iphoto_database_path():
    ud = NSUserDefaults.standardUserDefaults()
    prefs = ud.persistentDomainForName_('com.apple.iApps')
    if prefs is None:
        raise directories.InvalidPathError()
    if 'iPhotoRecentDatabases' not in prefs:
        raise directories.InvalidPathError()
    plisturl = NSURL.URLWithString_(prefs['iPhotoRecentDatabases'][0])
    return Path(plisturl.path())

def get_iphoto_pictures(plistpath):
    if not io.exists(plistpath):
        raise InvalidPath(self)
    s = io.open(plistpath).read()
    # There was a case where a guy had 0x10 chars in his plist, causing expat errors on loading
    s = s.replace('\x10', '')
    # It seems that iPhoto sometimes doesn't properly escape & chars. The regexp below is to find
    # any & char that is not a &-based entity (&amp;, &quot;, etc.). based on TextMate's XML
    # bundle's regexp
    s, count = re.subn(r'&(?![a-zA-Z0-9_-]+|#[0-9]+|#x[0-9a-fA-F]+;)', '', s)
    if count:
        logging.warning("%d invalid XML entities replacement made", count)
    plist = plistlib.readPlistFromString(s)
    result = []
    for photo_data in plist['Master Image List'].values():
        if photo_data['MediaType'] != 'Image':
            continue
        photo_path = Path(photo_data['ImagePath'])
        photo = IPhoto(photo_path)
        result.append(photo)
    return result

class Directories(directories.Directories):
    def __init__(self):
        directories.Directories.__init__(self, fileclasses=[Photo])
        try:
            self.iphoto_libpath = get_iphoto_database_path()
            self.set_state(self.iphoto_libpath[:-1], directories.STATE_EXCLUDED)
        except directories.InvalidPathError:
            self.iphoto_libpath = None
    
    def _get_files(self, from_path):
        if from_path == Path('iPhoto Library'):
            if self.iphoto_libpath is None:
                return []
            is_ref = self.get_state(from_path) == directories.STATE_REFERENCE
            photos = get_iphoto_pictures(self.iphoto_libpath)
            for photo in photos:
                photo.is_ref = is_ref
            return photos
        else:
            return directories.Directories._get_files(self, from_path)
    
    @staticmethod
    def get_subfolders(path):
        if path == Path('iPhoto Library'):
            return []
        else:
            return directories.Directories.get_subfolders(path)
    
    def add_path(self, path):
        if path == Path('iPhoto Library'):
            if path in self:
                raise AlreadyThereError()
            self._dirs.append(path)
        else:
            directories.Directories.add_path(self, path)
    

class DupeGuruPE(app_cocoa.DupeGuru):
    def __init__(self):
        app_cocoa.DupeGuru.__init__(self, data, 'dupeGuru Picture Edition', appid=5)
        self.scanner = ScannerPE()
        self.directories = Directories()
        p = op.join(self.appdata, 'cached_pictures.db')
        self.scanner.cached_blocks = Cache(p)
    
    def _do_delete(self, j):
        def op(dupe):
            j.add_progress()
            return self._do_delete_dupe(dupe)
        
        marked = [dupe for dupe in self.results.dupes if self.results.is_marked(dupe)]
        self.path2iphoto = {}
        if any(isinstance(dupe, IPhoto) for dupe in marked):
            j = j.start_subjob([6, 4], "Probing iPhoto. Don\'t touch it during the operation!")
            try:
                a = app('iPhoto')
                a.activate(timeout=0)
                a.select(a.photo_library_album(timeout=0), timeout=0)
                photos = as_fetch(a.photo_library_album().photos, k.item)
                for photo in j.iter_with_progress(photos):
                    try:
                        self.path2iphoto[unicode(photo.image_path(timeout=0))] = photo
                    except CommandError:
                        pass
            except (CommandError, RuntimeError):
                pass
        j.start_job(self.results.mark_count, "Sending dupes to the Trash")
        self.last_op_error_count = self.results.perform_on_marked(op, True)
        del self.path2iphoto
    
    def _do_delete_dupe(self, dupe):
        if isinstance(dupe, IPhoto):
            if unicode(dupe.path) in self.path2iphoto:
                photo = self.path2iphoto[unicode(dupe.path)]
                try:
                    a = app('iPhoto')
                    a.remove(photo, timeout=0)
                    return True
                except (CommandError, RuntimeError):
                    return False
            else:
                logging.warning(u"Could not find photo %s in iPhoto Library", unicode(dupe.path))
                return False
        else:
            return app_cocoa.DupeGuru._do_delete_dupe(self, dupe)
    
    def _do_load(self, j):
        self.directories.load_from_file(op.join(self.appdata, 'last_directories.xml'))
        self.results.load_from_xml(op.join(self.appdata, 'last_results.xml'), self._get_file, j)
    
    def _get_file(self, str_path):
        p = Path(str_path)
        if (self.directories.iphoto_libpath is not None) and (p in self.directories.iphoto_libpath[:-1]):
            return IPhoto(p)
        return app_cocoa.DupeGuru._get_file(self, str_path)
    
    def copy_or_move(self, dupe, copy, destination, dest_type):
        if isinstance(dupe, IPhoto):
            copy = True
        return app_cocoa.DupeGuru.copy_or_move(self, dupe, copy, destination, dest_type)
    
    def selected_dupe_path(self):
        if not self.selected_dupes:
            return None
        return self.selected_dupes[0].path
    
    def selected_dupe_ref_path(self):
        if not self.selected_dupes:
            return None
        ref = self.results.get_group_of_duplicate(self.selected_dupes[0]).ref
        if ref is self.selected_dupes[0]: # we don't want the same pic to be displayed on both sides
            return None
        return ref.path
    
