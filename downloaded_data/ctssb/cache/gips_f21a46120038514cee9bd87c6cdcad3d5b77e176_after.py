#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    AUTHOR: Matthew Hanson
#    EMAIL:  matt.a.hanson@gmail.com
#
#    Copyright (C) 2014 Applied Geosolutions
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>
################################################################################

import os
import sys
import errno
from osgeo import gdal, ogr
from datetime import datetime, timedelta
import glob
import re
from itertools import groupby
from shapely.wkt import loads
import tarfile
import zipfile
import traceback
import ftplib
import shutil
import commands

import gippy
from gippy.algorithms import CookieCutter
from gips import __version__
from gips.utils import (settings, VerboseOut, RemoveFiles, File2List, List2File, Colors,
        basename, mkdir, open_vector)
from gips import utils
from ..inventory import dbinv, orm

from cookielib import CookieJar
from urllib import urlencode
import urllib2


"""
The data.core classes are the base classes that are used by individual Data modules.
For a new dataset create children of Repository, Asset, and Data
"""


class Repository(object):
    """ Singleton (all classmethods) of file locations and sensor tiling system  """
    # Description of the data source
    description = 'Data source description'
    # Format code of date directories in repository
    _datedir = '%Y%j'
    # attribute holding the tile id
    _tile_attribute = 'tile'
    # valid sub directories in repo
    _subdirs = ['tiles', 'stage', 'quarantine', 'composites']

    @classmethod
    def feature2tile(cls, feature):
        """ Get tile designation from a geospatial feature (i.e. a row) """
        fldindex = feature.GetFieldIndex(cls._tile_attribute)
        return str(feature.GetField(fldindex))


    ##########################################################################
    # Override these functions if not using a tile/date directory structure
    ##########################################################################
    @classmethod
    def data_path(cls, tile='', date=''):
        """ Get absolute data path for this tile and date """
        path = cls.path('tiles')
        if tile != '':
            path = os.path.join(path, tile)
        if date != '':
            path = os.path.join(path, str(date.strftime(cls._datedir)))
        return path

    @classmethod
    def find_tiles(cls):
        """Get list of all available tiles for the current driver."""
        if orm.use_orm():
            return dbinv.list_tiles(cls.name.lower())
        return os.listdir(cls.path('tiles'))

    @classmethod
    def find_dates(cls, tile):
        """ Get list of dates available in repository for a tile """
        if orm.use_orm():
            return dbinv.list_dates(cls.name.lower(), tile)
        tdir = cls.data_path(tile=tile)
        if os.path.exists(tdir):
            return sorted([datetime.strptime(os.path.basename(d), cls._datedir).date() for d in os.listdir(tdir)])
        else:
            return []

    ##########################################################################
    # Child classes should not generally have to override anything below here
    ##########################################################################
    @classmethod
    def get_setting(cls, key):
        """ Get value from repo settings """
        dataclass = cls.__name__[:-10]
        r = settings().REPOS[dataclass]
        if key not in r.keys():
            # not in settings file, use defaults
            exec('import gips.data.%s as clsname' % dataclass)
            driverpath = os.path.dirname(clsname.__file__)
            if key == 'driver':
                return driverpath
            elif key == 'tiles':
                return os.path.join(driverpath, 'tiles.shp')
            else:
                raise Exception('%s is not a valid setting!' % key)
        else:
            return r[key]

    @classmethod
    def managed_request(cls, url, verbosity=1, debuglevel=0):
        """Visit the given http URL and return the response.

        Uses auth settings and cls._manager_url, and also follows custom
        weird redirects (specific to Earthdata servers seemingly).
        Returns urllib2.urlopen(...), or None if errors are encountered.
        debuglevel is ultimately passed in to httplib; if >0, http info,
        such as headers, will be printed on standard out.
        """
        username = cls.get_setting('username')
        password = cls.get_setting('password')
        manager_url = cls._manager_url
        password_manager = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(
            None, manager_url, username, password)
        cookie_jar = CookieJar()
        opener = urllib2.build_opener(
            urllib2.HTTPBasicAuthHandler(password_manager),
            urllib2.HTTPHandler(debuglevel=debuglevel),
            urllib2.HTTPSHandler(debuglevel=debuglevel),
            urllib2.HTTPCookieProcessor(cookie_jar))
        urllib2.install_opener(opener)
        try: # try instead of error handler because the exceptions have funny values to unpack
            request = urllib2.Request(url)
            response = urllib2.urlopen(request)
            redirect_url = response.geturl()
            # some data centers do it differently
            if "redirect" in redirect_url: # TODO is this the right way to detect redirects?
                utils.verbose_out('Redirected to ' + redirect_url, 3)
                redirect_url += "&app_type=401"
                request = urllib2.Request(redirect_url)
                response = urllib2.urlopen(request)
            return response
        except urllib2.URLError as e:
            utils.verbose_out('{} gave bad response: {}'.format(url, e.reason),
                              verbosity, sys.stderr)
            return None
        except urllib2.HTTPError as e:
            utils.verbose_out('{} gave bad response: {} {}'.format(url, e.code, e.reason),
                              verbosity, sys.stderr)
            return None

    @classmethod
    def path(cls, subdir=''):
        """ Paths to repository: valid subdirs (tiles, composites, quarantine, stage) """
        return os.path.join(cls.get_setting('repository'), subdir)


    @classmethod
    def vector2tiles(cls, vector, pcov=0.0, ptile=0.0, tilelist=None):
        """ Return matching tiles and coverage % for provided vector """
        from osgeo import ogr, osr

        # open tiles vector
        v = open_vector(cls.get_setting('tiles'))
        shp = ogr.Open(v.Filename())
        if v.LayerName() == '':
            layer = shp.GetLayer(0)
        else:
            layer = shp.GetLayer(v.LayerName())

        # create and warp site geometry
        ogrgeom = ogr.CreateGeometryFromWkt(vector.WKT())
        srs = osr.SpatialReference(vector.Projection())
        trans = osr.CoordinateTransformation(srs, layer.GetSpatialRef())
        ogrgeom.Transform(trans)
        # convert to shapely
        geom = loads(ogrgeom.ExportToWkt())

        # find overlapping tiles
        tiles = {}
        layer.SetSpatialFilter(ogrgeom)
        layer.ResetReading()
        feat = layer.GetNextFeature()
        while feat is not None:
            tgeom = loads(feat.GetGeometryRef().ExportToWkt())
            if tgeom.intersects(geom):
                area = geom.intersection(tgeom).area
                if area != 0:
                    tile = cls.feature2tile(feat)
                    tiles[tile] = (area / geom.area, area / tgeom.area)
            feat = layer.GetNextFeature()

        # remove any tiles not in tilelist or that do not meet thresholds for % cover
        remove_tiles = []
        if tilelist is None:
            tilelist = tiles.keys()
        for t in tiles:
            if (tiles[t][0] < (pcov / 100.0)) or (tiles[t][1] < (ptile / 100.0)) or t not in tilelist:
                remove_tiles.append(t)
        for t in remove_tiles:
            tiles.pop(t, None)
        return tiles


class Asset(object):
    """ Class for a single file asset (usually an original raw file or archive) """
    Repository = Repository

    # Sensors
    _sensors = {
        # Does the data have multiple sensors possible for each asset? If not, a single sensor may be fine
        '': {'description': ''},
    }
    # dictionary of assets
    _assets = {
        '': {
            'pattern': r'.+',
        }
    }

    # TODO - move to be per asset ?
    _defaultresolution = [30.0, 30.0]

    def __init__(self, filename):
        """ Inspect a single file and populate variables. Needs to be extended """
        # full filename to asset
        self.filename = filename
        # the asset code
        self.asset = ''
        # tile designation
        self.tile = ''
        # full date
        self.date = datetime(1858, 4, 6)
        # sensor code (key used in cls.sensors dictionary)
        self.sensor = ''
        # dictionary of existing products in asset {'product name': [filename(s)]}
        self.products = {}

    def updated(self, newasset):
        '''
        Compare the version info for this asset (self) to that of newasset.
        Return true if newasset version is greater.
        '''
        return false

    ##########################################################################
    # Child classes should not generally have to override anything below here
    ##########################################################################
    def parse_asset_fp(self):
        """Parse self.filename using the class's asset patterns.

        On the first successful match, the re lib match object is
        returned. Raises ValueError on failure to parse.
        """
        asset_bn = os.path.basename(self.filename)
        for av in self._assets.values():
            match = re.match(av['pattern'], asset_bn)
            if match is not None:
                return match
        raise ValueError("Unparseable asset file name:  " + self.filename)

    def datafiles(self):
        """Get list of readable datafiles from asset.

        A 'datafile' in this context is a file contained within the
        asset file, such as for tar, zip, and hdf files."""
        path = os.path.dirname(self.filename)
        indexfile = os.path.join(path, self.filename + '.index')
        if os.path.exists(indexfile):
            datafiles = File2List(indexfile)
            if len(datafiles) > 0:
                return datafiles
        with utils.error_handler('Problem accessing asset(s) in ' + self.filename):
            if tarfile.is_tarfile(self.filename):
                tfile = tarfile.open(self.filename)
                tfile = tarfile.open(self.filename)
                datafiles = tfile.getnames()
            elif zipfile.is_zipfile(self.filename):
                zfile = zipfile.ZipFile(self.filename)
                datafiles = zfile.namelist()
            else:
                # Try subdatasets
                fh = gdal.Open(self.filename)
                sds = fh.GetSubDatasets()
                datafiles = [s[0] for s in sds]
            if len(datafiles) > 0:
                List2File(datafiles, indexfile)
                return datafiles
            else:
                return [self.filename]


    def extract(self, filenames=tuple()):
        """Extract given files from asset (if it's a tar or zip).

        Extracted files are placed in the same dir as the asset file.
        """
        if tarfile.is_tarfile(self.filename):
            open_file = tarfile.open(self.filename)
        elif zipfile.is_zipfile(self.filename):
            open_file = zipfile.ZipFile(self.filename)
        else:
            raise Exception('%s is not a valid tar or zip file' % self.filename)
        path = os.path.dirname(self.filename)
        if len(filenames) == 0:
            filenames = self.datafiles()
        extracted_files = []
        for f in filenames:
            fname = os.path.join(path, f)
            if not os.path.exists(fname):
                utils.verbose_out("Extracting " + f, 3)
                open_file.extract(f, path)
                # this ensures we have permissions on extracted files
                if not os.path.isdir(fname):
                    os.chmod(fname, 0664)
            extracted_files.append(fname)
        return extracted_files

    ##########################################################################
    # Class methods
    ##########################################################################


    @classmethod
    def discover(cls, tile, date, asset=None):
        """Factory function returns list of Assets for this tile and date.

        Looks in the inventory for this, either the database or the
        filesystem depending on configuration.

        tile:   A tile string suitable for the current class(cls) ie
                'h03v19' for modis
        date:   datetime.date object to limit search in temporal dimension
        asset:  Asset type string, eg for modis could be 'MCD43A2'
        """
        criteria = {'driver': cls.Repository.name.lower(), 'tile': tile, 'date': date}
        if asset is not None:
            criteria['asset'] = asset
        if orm.use_orm():
            # search for ORM Assets to use for making GIPS Assets
            return [cls(a.name) for a in dbinv.asset_search(**criteria)]

        # The rest of this fn uses the filesystem inventory
        tpath = cls.Repository.data_path(tile, date)
        if not os.path.isdir(tpath):
            return []
        if asset is not None:
            assets = [asset]
        else:
            assets = cls._assets.keys()
        found = []
        for a in assets:
            files = utils.find_files(cls._assets[a]['pattern'], tpath)
            # more than 1 asset??
            if len(files) > 1:
                raise Exception("Duplicate(?) assets found: {}".format(files))
            if len(files) == 1:
                found.append(cls(files[0]))
        return found

    @classmethod
    def start_date(cls, asset):
        """ Get starting date for this asset """
        return cls._assets[asset].get('startdate', None)

    @classmethod
    def end_date(cls, asset):
        """Get ending date for this asset.

        One of 'enddate' or 'latency' must be present in
        cls._assets[asset]. Returns either the enddate, or else a
        computation of the most recently-available data, based on the
        (today's date) - asset's known latency.
        """
        a_info = cls._assets[asset]
        if 'enddate' in a_info:
            return a_info['enddate']
        return datetime.now() - timedelta(a_info['latency'])

    @classmethod
    def available(cls, asset, date):
        # TODO this method never seems to be called?
        """ Check availability of an asset for given date """
        date1 = cls._assets[asset].get(['startdate'], None)
        date2 = cls._assets[asset].get(['enddate'], None)
        if date2 is None:
            date2 = datetime.now() - timedelta(cls._asssets[asset]['latency'])
        if date1 is None or date2 is None:
            return False
        if date < date1 or date > date2:
            return False
        return True

    # TODO - combine this with fetch to get all dates
    @classmethod
    def dates(cls, asset, tile, dates, days):
        """ For a given asset get all dates possible (in repo or not) - used for fetch """
        from dateutil.rrule import rrule, DAILY
        # default assumes daily regardless of asset or tile
        datearr = rrule(DAILY, dtstart=dates[0], until=dates[1])
        dates = [dt for dt in datearr if days[0] <= int(dt.strftime('%j')) <= days[1]]
        return dates

    @classmethod
    def query_provider(cls, asset, tile, date):
        """Query the data provider for files matching the arguments.

        Drivers must override this method or else query_service. Must
        return (filename, url), or (None, None) if nothing found. This
        method has a more convenient return value for drivers that never
        find multiple files for the given (asset, tile, date), and don't
        need to unpack a nested data structure in their fetch methods.
        """
        raise NotImplementedError('query_provider not supported for' + cls.__name__)

    @classmethod
    def query_service(cls, asset, tile, date):
        """Query the data provider for files matching the arguments.

        Drivers must override this method, or else query_provider, to
        contact a data source regarding the given arguments, and report
        on whether anything is available for fetching. Must return a
        list of dicts containing available asset filenames and where to
        find them:  [{'basename': bn, 'url': url}, ...]. When nothing is
        avilable, must return [].
        """
        bn, url = cls.query_provider(asset, tile, date)
        if (bn, url) == (None, None):
            return []
        return [{'basename': bn, 'url': url}]


    @classmethod
    def fetch(cls, asset, tile, date):
        """ Fetch stub """
        raise NotImplementedError("Fetch not supported for this data source")

    @classmethod
    def ftp_connect(cls, working_directory):
        """Connect to an FTP server and chdir according to the args.

        Returns the ftplib connection object."""
        conn = ftplib.FTP(cls._host)
        conn.login('anonymous', settings().EMAIL)
        conn.set_pasv(True)
        conn.cwd(working_directory)
        return conn

    @classmethod
    def fetch_ftp(cls, asset, tile, date):
        """ Fetch via FTP """
        url = cls._assets[asset].get('url', '')
        if url == '':
            raise Exception("%s: URL not defined for asset %s" % (cls.__name__, asset))
        VerboseOut('%s: fetch tile %s for %s' % (asset, tile, date), 3)
        ftpurl = url.split('/')[0]
        ftpdir = url[len(ftpurl):]
        with utils.error_handler("Error downloading from {}".format(ftpurl)):
            ftp = ftplib.FTP(ftpurl)
            ftp.login('anonymous', settings().EMAIL)
            pth = os.path.join(ftpdir, date.strftime('%Y'), date.strftime('%j'))
            ftp.set_pasv(True)
            ftp.cwd(pth)

            for f in ftp.nlst('*'):
                VerboseOut("Downloading %s" % f, 2)
                ftp.retrbinary('RETR %s' % f,
                               open(os.path.join(cls.Repository.path('stage'), f), "wb").write)
            ftp.close()

    @classmethod
    def archive(cls, path='.', recursive=False, keep=False, update=False, **kwargs):
        """Move asset into the archive.

        Pass in a path to a file or a directory.  If a directory, its
        contents are scanned for assets and any found are archived; it
        won't descend into subdirectories unless `recursive`.  Any found
        assets are given hard links in the archive.  The original is
        then removed, unless `keep`. If a found asset would replace an
        extant archived asset, replacement is only performed if
        `update`.  kwargs is unused and likely without purpose.
        """
        start = datetime.now()

        fnames = []
        if not os.path.isdir(path):
            fnames.append(path)
        elif recursive:
            for root, subdirs, files in os.walk(path):
                for a in cls._assets.values():
                    files = utils.find_files(a['pattern'], path)
                    fnames.extend(files)
        else:
            for a in cls._assets.values():
                files = utils.find_files(a['pattern'], path)
                fnames.extend(files)
        numlinks = 0
        numfiles = 0
        assets = []
        for f in fnames:
            archived = cls._archivefile(f, update)
            if archived[1] >= 0:
                if not keep:
                    RemoveFiles([f], ['.index', '.aux.xml'])
            if archived[1] > 0:
                numfiles = numfiles + 1
                numlinks = numlinks + archived[1]
                assets.append(archived[0])

        # Summarize
        if numfiles > 0:
            VerboseOut('%s files (%s links) from %s added to archive in %s' %
                      (numfiles, numlinks, os.path.abspath(path), datetime.now() - start))
        if numfiles != len(fnames):
            VerboseOut('%s files not added to archive' % (len(fnames) - numfiles))
        return assets

    @classmethod
    def _archivefile(cls, filename, update=False):
        """ archive specific file """
        bname = os.path.basename(filename)
        try:
            asset = cls(filename)
        except Exception, e:
            # if problem with inspection, move to quarantine
            utils.report_error(e, 'File error, quarantining ' + filename)
            qname = os.path.join(cls.Repository.path('quarantine'), bname)
            if not os.path.exists(qname):
                os.link(os.path.abspath(filename), qname)
            return (None, 0)

        # make an array out of asset.date if it isn't already
        dates = asset.date
        if not hasattr(dates, '__len__'):
            dates = [dates]
        numlinks = 0
        otherversions = False
        for d in dates:
            tpath = cls.Repository.data_path(asset.tile, d)
            newfilename = os.path.join(tpath, bname)
            if not os.path.exists(newfilename):
                # check if another asset exists
                existing = cls.discover(asset.tile, d, asset.asset)
                if len(existing) > 0 and (not update or not existing[0].updated(asset)):
                    # gatekeeper case:  No action taken because existing assets are in the way
                    VerboseOut('%s: other version(s) already exists:' % bname, 1)
                    for ef in existing:
                        VerboseOut('\t%s' % os.path.basename(ef.filename), 1)
                    otherversions = True
                elif len(existing) > 0 and update:
                    # update case:  Remove existing outdated assets and install the new one
                    VerboseOut('%s: removing other version(s):' % bname, 1)
                    for ef in existing:
                        assert ef.updated(asset), 'Asset is not updated version'
                        VerboseOut('\t%s' % os.path.basename(ef.filename), 1)
                        with utils.error_handler('Unable to remove old version ' + ef.filename):
                            os.remove(ef.filename)
                    files = glob.glob(os.path.join(tpath, '*'))
                    for f in set(files).difference([ef.filename]):
                        msg = 'Unable to remove product {} from {}'.format(f, tpath)
                        with utils.error_handler(msg, continuable=True):
                            os.remove(f)
                    with utils.error_handler('Problem adding {} to archive'.format(filename)):
                        os.link(os.path.abspath(filename), newfilename)
                        asset.archived_filename = newfilename
                        VerboseOut(bname + ' -> ' + newfilename, 2)
                        numlinks = numlinks + 1

                else:
                    # 'normal' case:  Just add the asset to the archive; no other work needed
                    if not os.path.exists(tpath):
                        with utils.error_handler('Unable to make data directory ' + tpath):
                            os.makedirs(tpath)
                    with utils.error_handler('Problem adding {} to archive'.format(filename)):
                        os.link(os.path.abspath(filename), newfilename)
                        asset.archived_filename = newfilename
                        VerboseOut(bname + ' -> ' + newfilename, 2)
                        numlinks = numlinks + 1
            else:
                VerboseOut('%s already in archive' % filename, 2)
        if otherversions and numlinks == 0:
            return (asset, -1)
        else:
            return (asset, numlinks)
        # should return asset instance


class Data(object):
    """Collection of assets/products for single date and tile.

    If the data isn't given in tiles, then another discrete spatial
    region may be used instead.  In general, only one asset of each
    asset type is permitted (self.assets is a dict keyed by asset type,
    whose values are Asset objects).
    """
    name = 'Data'
    version = '0.0.0'
    Asset = Asset

    _unitless = 'unitless' # standard string for expressing that a product has no units

    _pattern = '*.tif'
    _products = {}
    _productgroups = {}

    def meta(self):
        """ Retrieve metadata for this tile """
        return {}

    def needed_products(self, products, overwrite):
        """ Make sure all products exist and return those that need processing """
        # TODO calling RequestedProducts twice is strange; rework into something clean
        products = self.RequestedProducts(products)
        products = self.RequestedProducts(
                [p for p in products.products if p not in self.products or overwrite])
        # TODO - this doesnt know that some products aren't available for all dates
        return products

    def process(self, products, overwrite=False, **kwargs):
        """ Make sure all products exist and return those that need processing """
        # TODO replace all calls to this method by subclasses with needed_products, then delete.
        return self.needed_products(products, overwrite)

    @classmethod
    def process_composites(cls, inventory, products, **kwargs):
        """ Process composite products using provided inventory """
        pass

    def copy(self, dout, products, site=None, res=None, interpolation=0, crop=False,
             overwrite=False, tree=False):
        """ Copy products to new directory, warp to projection if given site.

        Arguments
        =========
        dout:       output or destination directory; mkdir(dout) is done if needed.
        products:   which products to copy (passed to self.RequestedProducts())


        """
        # TODO - allow hard and soft linking options
        if res is None:
            res = self.Asset._defaultresolution
            #VerboseOut('Using default resolution of %s x %s' % (res[0], res[1]))
        dout = os.path.join(dout, self.id)
        if tree:
            dout = os.path.join(dout, self.date.strftime('%Y%j'))
        mkdir(dout)
        products = self.RequestedProducts(products)
        bname = '%s_%s' % (self.id, self.date.strftime('%Y%j'))
        for p in products.requested:
            if p not in self.sensors:
                # this product is not available for this day
                continue
            sensor = self.sensors[p]
            fin = self.filenames[(sensor, p)]
            fout = os.path.join(dout, "%s_%s_%s.tif" % (bname, sensor, p))
            if not os.path.exists(fout) or overwrite:
                with utils.error_handler('Problem creating ' + fout, continuable=True):
                    if site is not None:
                        # warp just this tile
                        resampler = ['near', 'bilinear', 'cubic']
                        cmd = 'gdalwarp %s %s -t_srs "%s" -tr %s %s -r %s' % \
                               (fin, fout, site.Projection(), res[0], res[1], resampler[interpolation])
                        print cmd
                        #result = commands.getstatusoutput(cmd)
                    else:
                        gippy.GeoImage(fin).Process(fout)
                        #shutil.copyfile(fin, fout)
        procstr = 'copied' if site is None else 'warped'
        VerboseOut('%s tile %s: %s files %s' % (self.date, self.id, len(products.requested), procstr))

    def filter(self, **kwargs):
        """Permit child classes to implement filtering.

        If data.filter() returns False, the Data object will be left out
        of the inventory during DataInventory instantiation.
        """
        return True

    @classmethod
    def meta_dict(cls):
        return {
            'GIPS Version': __version__,
        }

    def find_files(self):
        """Search path for non-asset files, usually product files.

        These must match the shell glob in self._pattern, and must not
        be assets, index files, nor xml files.
        """
        filenames = glob.glob(os.path.join(self.path, self._pattern))
        assetnames = [a.filename for a in self.assets.values()]
        badexts = ['.index', '.xml']
        test = lambda x: x not in assetnames and os.path.splitext(f)[1] not in badexts
        filenames[:] = [f for f in filenames if test(f)]
        return filenames


    @classmethod
    def normalize_tile_string(cls, tile_string):
        """Override this method to provide custom processing of tile names.

        This method should raise an exception if the tile string is
        invalid, but should return a corrected string instead if
        possible.  So for modis, 'H03V01' should return 'h03v01', while
        'H03V' should raise an exception.
        """
        return tile_string


    ##########################################################################
    # Child classes should not generally have to override anything below here
    ##########################################################################
    def __init__(self, tile=None, date=None, path='', search=True):
        """ Find all data and assets for this tile and date.

        Note date should be a datetime.date object. search=False will
        prevent searching for assets via Asset.discover().
        """
        self.id = tile
        self.date = date
        self.path = path      # /full/path/to/{driver}/tiles/{tile}/{date}; overwritten below
        self.basename = ''    # product file name prefix, form is <tile>_<date>
        self.assets = {}      # dict of <asset type string>: <Asset instance>
        self.filenames = {}   # dict of (sensor, product): product filename
        self.sensors = {}     # dict of asset/product: sensor
        if tile is not None and date is not None:
            self.path = self.Repository.data_path(tile, date)
            self.basename = self.id + '_' + self.date.strftime(self.Repository._datedir)
            if search:
                [self.add_asset(a) for a in self.Asset.discover(tile, date)] # Find all assets
                self.ParseAndAddFiles() # Find products

    def add_asset(self, asset):
        """Add an Asset object to self.assets and:

        Look at its products, adding metadata to self accordingly.
        """
        self.assets[asset.asset] = asset
        for p, val in asset.products.items():
            self.filenames[(asset.sensor, p)] = val
            self.sensors[p] = asset.sensor
        self.filenames.update({(asset.sensor, p): val for p, val in asset.products.items()})
        self.sensors[asset.asset] = asset.sensor

    @property
    def Repository(self):
        """ The repository for this class """
        return self.Asset.Repository

    @classmethod
    def RequestedProducts(cls, *args, **kwargs):
        from gips.core import RequestedProducts
        return RequestedProducts(cls, *args, **kwargs)

    def __getitem__(self, key):
        """ Get filename for product key """
        if type(key) == tuple:
            return self.filenames[key]
        else:
            return self.filenames[(self.sensor_set[0], key)]

    def __str__(self):
        """ Text representation """
        return '%s: %s: %s' % (self.name, self.date, ' '.join(self.product_set))

    def __len__(self):
        """ Number of products """
        return len(self.filenames)

    @property
    def valid(self):
        return False if len(self.filenames) == 0 and len(self.assets) == 0 else True

    @property
    def day(self):
        return self.date.strftime('%j')

    @property
    def sensor_set(self):
        """ Return list of sensors used """
        return list(set(sorted(self.sensors.values())))

    @property
    def products(self):
        """ Get list of products """
        return sorted([k[1] for k in self.filenames.keys()])

    @property
    def product_set(self):
        """ Return list of products available """
        return list(set(self.products))

    def ParseAndAddFiles(self, filenames=None):
        """Parse and Add filenames to existing filenames.

        If no filenames are provided, a list from find_files() is used
        instead."""
        if filenames is None:
            filenames = self.find_files() # find *product* files actually
        datedir = self.Repository._datedir
        for f in filenames:
            bname = basename(f)
            parts = bname.split('_')
            if len(parts) < 3 or len(parts) > 4:
                # Skip this file
                VerboseOut('Unrecognizable file: %s' % f, 3)
                continue
            offset = 1 if len(parts) == 4 else 0
            with utils.error_handler('Unrecognizable file ' + f, continuable=True):
                # only admit product files matching a single date
                if self.date is None:
                    # First time through
                    self.date = datetime.strptime(parts[0 + offset], datedir).date()
                else:
                    date = datetime.strptime(parts[0 + offset], datedir).date()
                    if date != self.date:
                        raise Exception('Mismatched dates: %s' % ' '.join(filenames))
                sensor = parts[1 + offset]
                product = parts[2 + offset]
                self.AddFile(sensor, product, f, add_to_db=False)

    def AddFile(self, sensor, product, filename, add_to_db=True):
        """Add named file to this object, taking note of its metadata.

        Optionally, also add a listing for the product file to the
        inventory database.
        """
        self.filenames[(sensor, product)] = filename
        # TODO - currently assumes single sensor for each product
        self.sensors[product] = sensor
        if add_to_db and orm.use_orm(): # update inventory DB if such is requested
            dbinv.update_or_add_product(driver=self.name.lower(), product=product, sensor=sensor,
                                        tile=self.id, date=self.date, name=filename)

    def asset_filenames(self, product):
        assets = self._products[product]['assets']
        filenames = []
        for asset in assets:
            filenames.extend(self.assets[asset].datafiles())
        if len(filenames) == 0:
            VerboseOut('There are no available assets on %s for tile %s' % (str(self.date), str(self.id), ), 3)
            return None
        return filenames

    def open(self, product, sensor=None, update=False):
        """ Open and return a GeoImage """
        if sensor is None:
            sensor = self.sensors[product]
        with utils.error_handler('Error reading product ({}, {})'.format(sensor, product)):
            fname = self.filenames[(sensor, product)]
            return gippy.GeoImage(fname)


    def open_assets(self, product):
        """ Open and return a GeoImage of the assets """
        return gippy.GeoImage(self.asset_filenames(product))

    # TODO - make general product_filter function
    def masks(self, patterns=None):
        """ List all products that are masks """
        if patterns is None:
            patterns = ['acca', 'fmask', 'mask']
        m = []
        for p in self.products:
            if any(pattern in p for pattern in patterns):
                m.append(p)
        return m

    @classmethod
    def pprint_header(cls):
        """ Print product inventory header showing product coverage"""
        header = Colors.BOLD + Colors.UNDER + '{:^12}'.format('DATE')
        for a in sorted(cls._products.keys()):
            header = header + ('{:^10}'.format(a if a != '' else 'Coverage'))
        return header + '{:^10}'.format('Product') + Colors.OFF

    @classmethod
    def pprint_asset_header(cls):
        """ Print header info for asset coverage """
        header = Colors.BOLD + Colors.UNDER + '{:^12}'.format('DATE')
        for a in sorted(cls.Asset._assets.keys()):
            header = header + ('{:^10}'.format(a if a != '' else 'Coverage'))
        header = header + '{:^10}'.format('Product') + Colors.OFF
        print header

    def pprint(self, dformat='%j', colors=None):
        """ Print product inventory for this date """
        sys.stdout.write('{:^12}'.format(self.date.strftime(dformat)))
        if colors is None:
            sys.stdout.write('  '.join(sorted(self.products)))
        else:
            for p in sorted(self.products):
                sys.stdout.write(colors[self.sensors[p]] + p + Colors.OFF + '  ')
        sys.stdout.write('\n')

    ##########################################################################
    # Class methods
    ##########################################################################
    @classmethod
    def discover(cls, path):
        """Find products in path and return Data object for each date.

        Does not interact with inventory DB as only caller is
        ProjectInventory which needs to read form the filesystem."""
        files = []
        datedir = cls.Asset.Repository._datedir
        for root, dirs, filenames in os.walk(path):
            for filename in filenames:
                f = os.path.join(root, filename)
                VerboseOut(f, 4)
                parts = basename(f).split('_')
                if len(parts) == 3 or len(parts) == 4:
                    with utils.error_handler('Error parsing product date', continuable=True):
                        datetime.strptime(parts[len(parts) - 3], datedir)
                        files.append(f)

        datas = []
        if len(files) == 0:
            return datas

        # Group by date
        sind = len(basename(files[0]).split('_')) - 3

        func = lambda x: datetime.strptime(basename(x).split('_')[sind], datedir).date()
        for date, fnames in groupby(sorted(files), func):
            dat = cls(path=path)
            dat.ParseAndAddFiles(list(fnames))
            datas.append(dat)

        return datas

    @classmethod
    def inventory(cls, site=None, key='', where='', tiles=None, pcov=0.0,
                  ptile=0.0, dates=None, days=None, **kwargs):
        """ Return list of inventories (size 1 if not looping through geometries) """
        from gips.inventory import DataInventory
        from gips.core import SpatialExtent, TemporalExtent
        spatial = SpatialExtent.factory(cls, site=site, key=key, where=where, tiles=tiles,
                                        pcov=pcov, ptile=ptile)
        temporal = TemporalExtent(dates, days)
        return DataInventory(cls, spatial[0], temporal, **kwargs)

    @classmethod
    def products2assets(cls, products):
        """ Get list of assets needed for these products """
        assets = []
        for p in products:
            if 'assets' in cls._products[p]:
                assets.extend(cls._products[p]['assets'])
            else:
                assets.append('')
        return set(assets)

    @classmethod
    def fetch(cls, products, tiles, textent, update=False):
        """ Download data for tiles and add to archive. update forces fetch """
        assets = cls.products2assets(products)
        fetched = []
        for a in assets:
            for t in tiles:
                asset_dates = cls.Asset.dates(a, t, textent.datebounds, textent.daybounds)
                for d in asset_dates:
                    # if we don't have it already, or if update (force) flag
                    if not cls.Asset.discover(t, d, a) or update == True:
                        date_str = d.strftime("%y-%m-%d")
                        msg_prefix = 'Problem fetching asset for {}, {}, {}'.format(a, t, date_str)
                        with utils.error_handler(msg_prefix, continuable=True):
                            cls.Asset.fetch(a, t, d)
                            # fetched may contain both fetched things and unfetchable things
                            fetched.append((a, t, d))
        return fetched

    @classmethod
    def product_groups(cls):
        """ Return dict of groups and products in each one """
        groups = cls._productgroups
        groups['Standard'] = []
        grouped_products = [x for sublist in cls._productgroups.values() for x in sublist]
        for p in cls._products:
            if p not in grouped_products:
                groups['Standard'].append(p)
        if len(groups['Standard']) == 0:
            del groups['Standard']
        return groups

    @classmethod
    def products2groups(cls, products):
        """ Convert product list to groupings """
        p2g = {}
        groups = {}
        allgroups = cls.product_groups()
        for g in allgroups:
            groups[g] = {}
            for p in allgroups[g]:
                p2g[p] = g
        for p, val in products.items():
            g = p2g[val[0]]
            groups[g][p] = val
        return groups

    @classmethod
    def print_products(cls):
        print Colors.BOLD + "\n%s Products v%s" % (cls.name, cls.version) + Colors.OFF
        groups = cls.product_groups()
        opts = False
        txt = ""
        for group in groups:
            txt = txt + Colors.BOLD + '\n%s Products\n' % group + Colors.OFF
            for p in sorted(groups[group]):
                h = cls._products[p]['description']
                txt = txt + '   {:<12}{:<40}\n'.format(p, h)
                if 'arguments' in cls._products[p]:
                    opts = True
                    #sys.stdout.write('{:>12}'.format('options'))
                    args = [['', a] for a in cls._products[p]['arguments']]
                    for a in args:
                        txt = txt + '{:>12}     {:<40}\n'.format(a[0], a[1])
        if opts:
            print "  Optional qualifiers listed below each product."
            print "  Specify by appending '-option' to product (e.g., ref-toa)"
        sys.stdout.write(txt)

    def make_temp_proc_dir(self):
        """Make a temporary directory in which to perform gips processing.

        Returns a context manager that governs the newly-made directory,
        which is deleted on exiting the context. It is created in the
        driver's stage directory, and has a random name.
        """
        return utils.make_temp_dir(prefix='proc', dir=self.Repository.path('stage'))

    @staticmethod
    def proc_temp_dir_manager(wrapped_method):
        """Decorator for self.process to use a tempdir consistently.

        Decorate a method with it, and it'll create a temp
        directory for the method's use, then destroy it afterwards.
        """
        def wrapper(self, *args, **kwargs):
            assert not hasattr(self, '_temp_proc_dir')
            with self.make_temp_proc_dir() as temp_dir:
                self._temp_proc_dir = temp_dir
                # keys are temp filenames, vals are tuples:  (sensor, prod-type, archive full path)
                try:
                    return wrapped_method(self, *args, **kwargs)
                finally:
                    del self._temp_proc_dir
        return wrapper

    def archive_temp_path(self, temp_fp):
        """Move the product file from the managed temp dir to the archive.

        The archival full path is returned; an appropriate spot in the
        archive is chosen automatically.
        """
        archive_fp = os.path.join(self.path, os.path.basename(temp_fp))
        os.rename(temp_fp, archive_fp)
        return archive_fp

    def generate_temp_path(self, filename):
        """Return a full path to the filename within the managed temp dir.

        The filename's basename is glued to the end of the temp dir.
        This method should be called from within proc_temp_dir_manager.
        """
        return os.path.join(self._temp_proc_dir, os.path.basename(filename))

    def product_filename(self, sensor, prod_type):
        """Returns a standardized product file name."""
        date_string = self.date.strftime(self.Repository._datedir)
        # reminder: self.id is the tile ID string, eg 'h12v04' or '19TCH'
        return '{}_{}_{}_{}.tif'.format(self.id, date_string, sensor, prod_type)

    def temp_product_filename(self, sensor, prod_type):
        """Generates a product filename within the managed temp dir."""
        return self.generate_temp_path(self.product_filename(sensor, prod_type))
