"""
Folder Manager module
"""
__license__ = 'MIT'
__copyright__ = '2017, Julien Dcurz <juliendcruz at gmail.com>'

import io
import os
from PySide2 import QtCore
from PIL import Image
import PIL.ExifTags
from iptcinfo3 import IPTCInfo
from imagius.db import dbmgr
from imagius.log import LOGGER
from imagius import settings
from imagius.constants import SortMode
import exifread


class MetaFilesManager():
    _thumb_size = (256, 256)

    def __init__(self, meta_path=settings.get_meta_db_path(), settings_path=settings.get_settings_db_path()):
        self._meta_db = dbmgr(meta_path)
        self._settings_db = dbmgr(settings_path)

    def connect(self):
        self._meta_db.connect()

    def disconnect(self):
        self._meta_db.disconnect()

    def commit(self):
        self._meta_db.commit()

    def get_watched_dirs(self):
        query = "SELECT * FROM dir"
        self._settings_db.connect()
        res = self._settings_db.run_select_query(query)
        self._settings_db.disconnect()
        return res

    def get_scan_dirs(self, sort: SortMode = SortMode.Name, reverseSort=True):
        predicate = ""

        if sort == SortMode.Name:
            if reverseSort:
                predicate = "ORDER BY name DESC"
            else:
                predicate = "ORDER BY name ASC"

        query = "SELECT * FROM scan_dir %s" % predicate

        self._meta_db.connect()
        res = self._meta_db.run_select_query(query)
        self._meta_db.disconnect()
        return res

    def search_scan_dirs(self, search_term):
        query = "SELECT * FROM scan_dir WHERE name LIKE ?"
        self._meta_db.connect()
        res = self._meta_db.run_select_query(query, ("%" + search_term + "%",))
        return res

    def get_scan_dir(self, id):
        query = "SELECT * FROM scan_dir WHERE id = ?"
        params = (id,)
        self._meta_db.connect()
        res = self._meta_db.run_select_query(query, params)
        self._meta_db.disconnect()
        if not res:
            return None
        return res[0]

    def get_scan_dir_id(self, abs_path):
        query = "SELECT * FROM scan_dir WHERE abspath = ?"
        params = (abs_path,)
        res = self._meta_db.run_select_query(query, params)
        if not res:
            return None
        return res[0]

    def add_scan_dir(self, parent_id, path, name, integrity_check):
        """
        <TODO>
        """
        query = "INSERT INTO scan_dir (parent_dir_id, abspath, name, integrity_check) VALUES (?, ?, ?, ?)"
        params = (parent_id, path, name, integrity_check)
        sd_id = self._meta_db.run_insert_query(query, params)
        return sd_id

    def remove_scan_dir(self, id):
        """
        <TODO>
        """
        query = "DELETE FROM scan_dir WHERE id = ?"
        params = (id,)
        return self._meta_db.run_query(query, params)

    def update_scan_dir_integrity_check(self, sd_id, ts):
        """
        <TODO>
        """
        query = "UPDATE scan_dir SET integrity_check = ? WHERE id = ?"
        params = (ts, sd_id)
        sd_id = self._meta_db.run_query(query, params)
        return sd_id

    def update_scan_dir_mtime(self, sd_id, mtime):
        """
        <TODO>
        """
        query = "UPDATE scan_dir SET mtime = ? WHERE id = ?"
        params = (mtime, sd_id)
        sd_id = self._meta_db.run_query(query, params)
        return sd_id

    def update_scan_dir_img_count(self, sd_id, count):
        """
        <TODO>
        """
        query = "UPDATE scan_dir SET img_count = ? WHERE id = ?"
        params = (count, sd_id)
        sd_id = self._meta_db.run_query(query, params)
        return sd_id

    def add_image(self, sdid, abs_path, name, int_check, serial):
        thumb_bytes = self._generate_thumb(abs_path, self._thumb_size)
        mtime = os.path.getmtime(abs_path)
        return self._add_image_db(sdid, abs_path, name, thumb_bytes, mtime, int_check, serial)

    def update_image_thumb(self, si_id, abs_path, mtime, int_check):
        thumb_bytes = self._generate_thumb(abs_path, self._thumb_size)
        self._update_image_thumb_db(si_id, thumb_bytes, mtime, int_check)

    def update_image(self, si_id, int_check):
        self._update_image_db(si_id, int_check)

    def _generate_thumb(self, abspath, thumb_size):
        thumb_bytes = io.BytesIO()
        try:
            ext = QtCore.QFileInfo(abspath).suffix()
            if ext == 'png':
                with Image.open(abspath) as image:
                    image.verify()

            with Image.open(abspath) as image:
                image.thumbnail(thumb_size, Image.ANTIALIAS)
                image.save(thumb_bytes, image.format)
        except Exception as err:
            LOGGER.error('Error while generating thumbs: %s' % err)
        return thumb_bytes

    def get_img_exif(self, abspath):
        exif = {}
        try:
            with PIL.Image.open(abspath) as image:
                exif = {
                    PIL.ExifTags.TAGS[k]: v
                    for k, v in image._getexif().items()
                    if k in PIL.ExifTags.TAGS
                }
        except Exception as ex:
            LOGGER.debug("EXIF data for %s could not be loaded." % abspath)
        return exif

    def get_dir_properties(self, sd_id):
        self.connect()
        dr_dir = self.get_scan_dir(sd_id)
        self.disconnect()
        dir_info = QtCore.QFileInfo(dr_dir['abspath'])
        print(dir_info.size())
        properties = {}
        properties['img_count'] = dr_dir['img_count']
        properties['modified'] = dir_info.lastModified()
        properties['size'] = self.format_size(
            self.get_dir_size(dr_dir['abspath']))

        return properties

    def get_img_properties(self, si_id, sd_id):
        if not self._meta_db.is_open:
            self.connect()
        dr_img = self.get_image_from_id(si_id, sd_id)
        exif = self.get_img_exif(dr_img['abspath'])
        # print(exif)

        properties = {}
        properties['abspath'] = dr_img['abspath']
        properties['filename'] = dr_img['name']
        properties['filesize'] = self.format_size(
            QtCore.QFileInfo(dr_img['abspath']).size())
        properties['dimensions'] = ''
        if exif:
            if 'DateTime' in exif:
                properties['DateTime'] = exif['DateTime']
            if 'DateTimeDigitized' in exif:
                properties['DateTimeDigitized'] = exif['DateTimeDigitized']
            if 'ImageWidth' in exif:
                properties['ImageWidth'] = exif['ImageWidth']
            if 'ImageLength' in exif:
                properties['ImageLength'] = exif['ImageLength']
            if 'ExifImageWidth' in exif:
                properties['ExifImageWidth'] = exif['ExifImageWidth']
            if 'ExifImageHeight' in exif:
                properties['ExifImageHeight'] = exif['ExifImageHeight']
            if 'Orientation' in exif:
                properties['Orientation'] = exif['Orientation']
            if 'XPKeywords' in exif:
                properties['XPKeywords'] = exif['XPKeywords'].decode("utf-16")
            if 'ImageUniqueID' in exif:
                properties['ImageUniqueID'] = exif['ImageUniqueID']
            if 'ColorSpace' in exif:
                properties['ColorSpace'] = exif['ColorSpace']
            if 'BitsPerSample' in exif:
                properties['BitsPerSample'] = exif['BitsPerSample']
            if 'PhotometricInterpretation' in exif:
                properties['PhotometricInterpretation'] = exif['PhotometricInterpretation']
            if 'ResolutionUnit' in exif:
                properties['ResolutionUnit'] = exif['ResolutionUnit']
            if 'Software' in exif:
                properties['Software'] = exif['Software']
            if 'SamplesPerPixel' in exif:
                properties['SamplesPerPixel'] = exif['SamplesPerPixel']
            if 'XResolution' in exif:
                properties['XResolution'] = exif['XResolution']
            if 'YResolution' in exif:
                properties['YResolution'] = exif['YResolution']

            if 'ImageWidth' in exif:
                properties['dimensions'] = "%sx%s" % (
                    properties['ImageWidth'], properties['ImageLength'])
            elif 'ExifImageWidth' in exif:
                properties['dimensions'] = "%sx%s" % (
                    properties['ExifImageWidth'], properties['ExifImageHeight'])
        else:
            LOGGER.debug("EXIF data for %s not found." % dr_img['abspath'])

        # TODO: IPTC support
        # iptc_info = IPTCInfo(dr_img['abspath'])
        # if len(iptc_info.data) < 4:
        #     LOGGER.debug("IPTC dat for %s not found." % dr_img['abspath'])
        # else:
        #     print(iptc_info)

        return properties

    def _add_image_db(self, sdid, abspath, name, blob, mtime, int_check, serial):
        query = "INSERT INTO scan_img (sdid, abspath, name, thumb, mtime, integrity_check, serial) VALUES (?, ?, ?, ?, ?, ?, ?)"
        params = (sdid, abspath, name, blob.getvalue(),
                  mtime, int_check, serial)
        si_id = self._meta_db.run_insert_query(query, params, False)
        return si_id

    def _update_image_db(self, si_id, int_check):
        query = "UPDATE scan_img set integrity_check = ? WHERE id = ?"
        params = (int_check, si_id)
        self._meta_db.run_query(query, params, False)

    def _update_image_thumb_db(self, si_id, blob, mtime, int_check):
        query = "UPDATE scan_img set thumb = ?, mtime = ?, integrity_check = ? WHERE id = ?"
        params = (blob.getvalue(), mtime, int_check, si_id)
        self._meta_db.run_query(query, params, False)

    def get_image_id(self, abs_path):
        query = "SELECT id, mtime FROM scan_img WHERE abspath = ?"
        params = (abs_path,)
        res = self._meta_db.run_select_query(query, params)
        if not res:
            return None
        return res[0]

    def get_image_from_id(self, si_id, sd_id):
        query = "SELECT * FROM scan_img WHERE id = ? AND sdid  = ?"
        params = (si_id, sd_id)
        res = self._meta_db.run_select_query(query, params)
        if not res:
            return None
        return res[0]

    def get_scan_dir_image(self, sd_id, serial):
        query = "SELECT * FROM scan_img WHERE sdid = ? AND serial = ?"
        params = (sd_id, serial)
        res = self._meta_db.run_select_query(query, params)
        if not res:
            return None
        return res[0]

    def get_scan_dir_images(self, sd_id):
        query = "SELECT * FROM scan_img WHERE sdid = ?"
        params = (sd_id,)
        self._meta_db.connect()
        res = self._meta_db.run_select_query(query, params)
        self._meta_db.disconnect()
        return res

    def get_unclean_entries(self, int_check):
        query = "SELECT abspath FROM scan_img WHERE integrity_check < ?"
        params = (int_check,)
        res = self._meta_db.run_select_query(query, params)
        return res

    def clean_db(self, int_check):
        query = "DELETE FROM scan_img WHERE integrity_check < ?"
        params = (int_check,)
        return self._meta_db.run_query(query, params, True)

    def get_orphaned_scan_dirs(self, int_check):
        query = "SELECT * FROM scan_dir WHERE integrity_check < ?"
        params = (int_check,)
        return self._meta_db.run_select_query(query, params)

    def prune_scan_dir(self, sd_id):
        query = "DELETE FROM scan_dir WHERE id = ?"
        params = (sd_id,)
        self._meta_db.run_query(query, params)
        query = "DELETE FROM scan_img WHERE sdid = ?"
        params = (sd_id,)
        return self._meta_db.run_query(query, params)

    def prune_scan_img(self, sd_id, int_check):
        query = "DELETE FROM scan_img WHERE sdid = ? AND integrity_check < ?"
        params = (sd_id, int_check)
        return self._meta_db.run_query(query, params, True)

    def get_scan_dir_img_count(self, sd_id):
        query = "select COUNT(id) AS 'img_count' from scan_img WHERE sdid = ?"
        params = (sd_id,)
        res = self._meta_db.run_select_query(query, params)
        return res[0]['img_count']

    def get_scan_dir_img_next_serial(self, sd_id):
        query = "select MAX(serial) AS last_serial FROM scan_img where sdid = ?"
        params = (sd_id,)
        res = self._meta_db.run_select_query(query, params)
        if res[0]['last_serial'] is None:
            return 1
        return (res[0]['last_serial'] + 1)

    def format_size(self, num, suffix='B'):
        for unit in ['', 'Ki', 'Mi']:
            if abs(num) < 1024.0:
                return "%3.1f %s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f %s%s" % (num, 'Gi', suffix)

    def get_dir_size(self, abspath):
        start_path = abspath
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size
