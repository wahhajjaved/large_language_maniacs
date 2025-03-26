#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    Copyright (C) 2017 Applied Geosolutions
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

from __future__ import print_function

import math
import os
import shutil
import sys
import datetime
import shlex
import re
import subprocess
import json
import tempfile
import zipfile
import copy
import glob
from itertools import izip_longest
from xml.etree import ElementTree
import StringIO

from backports.functools_lru_cache import lru_cache

import numpy
import pyproj
import requests
from requests.auth import HTTPBasicAuth
from shapely.wkt import loads as wkt_loads

import gippy
import gippy.algorithms

from gips.data.core import Repository, Asset, Data
import gips.data.core
from gips import utils
from gips import atmosphere


"""Steps for adding a product to this driver:

* add the product to the _products dict
* make a $prod_geoimage() method to generate the GeoImage; follow pattern of others.
* add a stanza to the conditional below where $prod_geoimage is called.
* add the product to the dependency dict above.
* if atmo correction is in use:
    * save its metadata (see 'ref' for a pattern)
    * add the product to the conditional for metadata in the file-saving block
* update system tests
"""

_asset_types = ('L1C', 'L1CGS')

class sentinel2Repository(Repository):
    name = 'Sentinel2'
    description = 'Data from the Sentinel 2 satellite(s) from the ESA'
    # when looking at the tiles shapefile, what's the key to fetch a feature's tile ID?
    _tile_attribute = 'Name'

    default_settings = {
        'source': 'esa',
        'asset-preference': _asset_types,
        'extract': False,
    }

    @classmethod
    def validate_setting(cls, key, value):
        if key == 'source' and value not in ('esa', 'gs'):
            raise ValueError("Sentinel-2's 'source' setting is '{}',"
                    " but valid values are 'esa' or 'gs'".format(value))
        if key == 'asset-preference':
            warts = set(value) - set(_asset_types)
            if warts:
                raise ValueError("Valid 'asset-preferences' for Sentinel-2"
                        " are {}; invalid values found:  {}".format(warts))
        return value

    @classmethod
    def tile_lat_lon(cls, tileid):
        """Returns the coordinates of the given tile ID.

        Uses the reference tile vectors provided with the driver.
        Returns (x0, x1, y0, y1), which is
        (west lon, east lon, south lat, north lat) in degrees.
        """
        e = utils.open_vector(cls.get_setting('tiles'), cls._tile_attribute)[tileid].Extent()
        return e.x0(), e.x1(), e.y0(), e.y1()


class sentinel2Asset(Asset, gips.data.core.GoogleStorageMixin):
    Repository = sentinel2Repository

    gs_bucket_name = 'gcp-public-data-sentinel-2'

    _sensors = {
        'S2A': {
            'description': 'Sentinel-2, Satellite A',
            # Note all these lists are aligned with eachother, so that GREEN is band 3, and has
            # bandwidth 0.035.
            # found in the granule filenames
            'band-strings':
                ['01', '02', '03', '04', '05', '06',
                 '07', '08', '8A', '09', '10', '11', '12'],
            # for GIPS' & gippy's use, not inherent to driver
            'colors':
                ["COASTAL",  "BLUE", "GREEN",    "RED", "REDEDGE1", "REDEDGE2",
                 "REDEDGE3", "NIR",  "REDEDGE4", "WV",  "CIRRUS",   "SWIR1",    "SWIR2"],
            # center wavelength of band in micrometers, CF:
            # https://earth.esa.int/web/sentinel/user-guides/sentinel-2-msi/resolutions/radiometric
            'bandlocs':
                [0.443, 0.490, 0.560, 0.665, 0.705, 0.740,
                 0.783, 0.842, 0.865, 0.945, 1.375, 1.610, 2.190],
            # width of band, evenly split in the center by bandloc:
            # https://earth.esa.int/web/sentinel/user-guides/sentinel-2-msi/resolutions/radiometric
            'bandwidths':
                [0.020, 0.065, 0.035, 0.030, 0.015, 0.015,
                 0.020, 0.115, 0.020, 0.020, 0.030, 0.090, 0.180],
            'bandbounds':
                # low and high boundaries of each band; formatted this way to match other lists
                [(0.433, 0.453), (0.4575, 0.5225), (0.5425, 0.5775), (0.65, 0.68),
                    (0.6975, 0.7125), (0.7325, 0.7475),
                 (0.773, 0.793), (0.7845, 0.8995), (0.855, 0.875), (0.935, 0.955), (1.36, 1.39),
                    (1.565, 1.655), (2.1, 2.28)],
            # in meters per https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi/resolutions/spatial
            'spatial-resolutions':
                [60, 10, 10, 10, 20, 20,
                 20, 10, 20, 60, 60, 20, 20],
            # 'E': None  # S.B. Pulled from asset metadata file
            # 'tcap': _tcapcoef,

            # colors needed for computing indices products such as NDVI
            'indices-bands': ['02', '03', '04', '05', '06',
                              '07', '08', '8A', '11', '12'],
            # similar to landsat's "visbands"
            'indices-colors': ['BLUE', 'GREEN', 'RED',
                               'REDEDGE1', 'REDEDGE2', 'REDEDGE3',
                               'NIR', 'REDEDGE4', 'SWIR1', 'SWIR2'],
        },
    }
    _sensors['S2B'] = copy.deepcopy(_sensors['S2A'])
    _sensors['S2B']['description'] = 'Sentinel-2, Satellite B'

    _asset_fn_pat_base = '^.*S2._.*MSIL1C_.*.{8}T.{6}_.*R..._.*'

    # TODO find real start date for S2 data:
    # https://scihub.copernicus.eu/dhus/search?q=filename:S2?*&orderby=ingestiondate%20asc
    # (change to orderby=ingestiondate%20desc if needed)
    _start_date = datetime.date(2015, 1, 1)

    _assets = {
        'L1C': {
            'source': 'esa',
            # 'pattern' is used for searching the repository of locally-managed assets; this pattern
            # is used for both datastrip and single-tile assets.
            'pattern': _asset_fn_pat_base + '\.zip$',
            'startdate': _start_date,
            'latency': 3, # actually seems to be 3,7,3,7..., but this value seems to be unused;
                          # only needed by Asset.end_date and Asset.available, but those are never called?
        },
        'L1CGS': {
            'source': 'gs',
            'startdate': _start_date,
            'latency': 3,
            'pattern': _asset_fn_pat_base + '_gs\.json$',
        }
    }

    ds_style = 'datastrip-style' # can't be downloaded anymore; deprecated
    st_style = 'single-tile-style'
    # first day of new-style assets, UTC
    st_style_start_date = datetime.datetime(2016, 12, 7, 0, 0)

    # regexes for verifying filename correctness & extracting metadata; convention:
    # https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-2-msi/naming-convention
    _tile_re = '(?P<tile>\d\d[A-Z]{3})'
    # example, note that leading tile code is spliced in by Asset.fetch:
    # 19TCH_S2A_OPER_PRD_MSIL1C_PDMC_20170221T213809_R050_V20151123T091302_20151123T091302.zip
    _ds_name_re = (
        '(?P<sensor>S2[AB])_OPER_PRD_MSIL1C_....' # sensor
        '_(?P<pyear>\d{4})(?P<pmon>\d\d)(?P<pday>\d\d)' # processing date
        'T(?P<phour>\d\d)(?P<pmin>\d\d)(?P<psec>\d\d)' # processing time
        '_R(?P<rel_orbit>\d\d\d)' # relative orbit, not sure if want
        # observation datetime:
        '_V(?P<year>\d{4})(?P<mon>\d\d)(?P<day>\d\d)' # year, month, day
        'T(?P<hour>\d\d)(?P<min>\d\d)(?P<sec>\d\d)' # hour, minute, second
        '_\d{8}T\d{6}.zip') # repeated observation datetime for no known reason

    _name_re = (
        '^(?P<sensor>S2[AB])_MSIL1C_' # sensor
        '(?P<year>\d{4})(?P<mon>\d\d)(?P<day>\d\d)' # year, month, day
        'T(?P<hour>\d\d)(?P<min>\d\d)(?P<sec>\d\d)' # hour, minute, second
        '_N\d{4}_R\d\d\d_T' + _tile_re +  # tile
        '_(?P<pyear>\d{4})(?P<pmon>\d\d)(?P<pday>\d\d)' # processing date
        'T(?P<phour>\d\d)(?P<pmin>\d\d)(?P<psec>\d\d)' # processing time
        '\.(SAFE_gs\.json|zip)$'
    )

    _asset_styles = {
        ds_style: {
            # datastrip-style assets can't use the same name for
            # downloading and archiving, because each downloaded file
            # contains multiple tiles of data
            'downloaded-name-re': _ds_name_re,
            'archived-name-re': '^' + _tile_re + '_' + _ds_name_re,
            # raster file pattern
            # TODO '/.*/' can be misleading due to '/' satisfying '.', so rework into '/[^/]*/'
            'raster-re': r'^.*/GRANULE/.*/IMG_DATA/.*_T{tileid}_B(?P<band>\d[\dA]).jp2$',
            ## internal metadata file patterns
            # updated assumption: only XML file in DATASTRIP/ (not including subdirs)
            'datastrip-md-re': '^.*/DATASTRIP/[^/]+/[^/]*.xml$',
            'tile-md-re': '^.*/GRANULE/.*_T{tileid}_.*/.*_T{tileid}.xml$',
            # example asset metadata path:
            # S2A_OPER_PRD_MSIL1C_PDMC_20160904T192336_R126_V20160903T164322_20160903T164911.SAFE/
            #   S2A_OPER_MTD_SAFL1C_PDMC_20160904T192336_R126_V20160903T164322_20160903T164911.xml
            'asset-md-re': r'^[^/]+/S2[AB]_[^/]+\.xml$',
        },
        st_style: {
            'downloaded-name-re': _name_re,
            'archived-name-re': _name_re,
            # raster file pattern
            'raster-re': '^.*/GRANULE/.*/IMG_DATA/.*_B(?P<band>\d[\dA]).jp2$',
            # internal metadata file patterns
            'datastrip-md-re': '^.*/DATASTRIP/.*/MTD_DS.xml$',
            'tile-md-re': '^.*/GRANULE/.*/MTD_TL.xml$',
            'asset-md-re': '^.*/MTD_MSIL1C.xml$',
        },
    }

    # default resultant resolution for resampling during to Data().copy()
    _defaultresolution = (10, 10)

    def __init__(self, filename):
        """Inspect a single file and set some metadata.

        File naming convention:
        https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-2-msi/naming-convention
        """
        super(sentinel2Asset, self).__init__(filename)

        self.basename = os.path.basename(filename)
        # L1CGS assets are a funny mix of the two styles
        for style, style_dict in self._asset_styles.items():
            match = re.match(style_dict['archived-name-re'], self.basename)
            if match is not None:
                break
        if match is None:
            raise IOError("Asset file name is incorrect for"
                          " Sentinel-2: '{}'".format(self.basename))

        self.style = style
        self.asset = 'L1CGS' if filename.endswith('_gs.json') else 'L1C'
        self.sensor = match.group('sensor')
        self.tile = match.group('tile')
        self.date = datetime.date(*[int(i) for i in match.group('year', 'mon', 'day')])
        self.time = datetime.time(*[int(i) for i in match.group('hour', 'min', 'sec')])
        self.style_res = self.get_style_regexes(self.style, self.tile)
        self._version = int(''.join(
            match.group('pyear', 'pmon', 'pday', 'phour', 'pmin', 'psec')
        ))
        self.meta = {} # for caching asset metadata values
        self.tile_meta = None # tile metadata; dict was not good for this
        # sometimes assets are instantiated but no file is present
        #                                      vvv
        if self.asset == 'L1CGS' and os.path.exists(filename):
            with open(filename) as fo:
                self.json_content = json.load(fo)
                self.meta['cloud-cover'] = self.json_content['cloud-cover']

    @classmethod
    def get_style_regexes(cls, style, tile_id, compile=False):
        """Returns regexes for the given style.

        This lets one locate internal metadata.
        """
        sr = copy.deepcopy(cls._asset_styles[style])
        if style == cls.ds_style:
            sr['raster-re']       = sr['raster-re'].format(tileid=tile_id)
            sr['tile-md-re']      = sr['tile-md-re'].format(tileid=tile_id)
            sr['datastrip-md-re'] = sr['datastrip-md-re'].format(
                tileid=tile_id)
        if compile:
            return {k: re.compile(v) for (k, v) in sr.items()}
        return sr

    @classmethod
    def query_scihub(cls, tile, date):
        username = cls.Repository.get_setting('username')
        password = cls.Repository.get_setting('password')

        year, month, day = date.timetuple()[:3]
        # search step:  locate the asset corresponding to (asset, tile, date)
        url_head = 'https://scihub.copernicus.eu/dhus/search?q='
        #                vvvvvvvv--- sort by processing date so always get the newest one
        url_tail = '&orderby=ingestiondate desc&format=json'
        #                                      year mon  day                    tile
        url_search_string = 'filename:S2?_MSIL1C_{}{:02}{:02}T??????_N????_R???_T{}_*.SAFE'
        search_url = url_head + url_search_string.format(year, month, day, tile) + url_tail

        auth = HTTPBasicAuth(username, password)
        r = requests.get(search_url, auth=auth)
        r.raise_for_status()
        return r.json()

    @classmethod
    def query_esa(cls, tile, date, pclouds):
        """Search for a matching asset in the Sentinel-2 servers.

        Uses the given (tile, date) tuple as a search key, and
        returns a dict else None, like for query_service.
        """
        # search for the asset's URL with wget call (using a suprocess call to wget instead of a
        # more conventional call to a lib because available libs are perceived to be inferior).
        with utils.error_handler("Error performing asset search ({}, {})".format(
                tile, date.strftime("%Y%j"))):
            results = cls.query_scihub(tile, date)['feed'] # always top-level key

            result_count = int(results['opensearch:totalResults'])
            if result_count == 0:
                return None # nothing found, a normal occurence for eg date range queries
            # unfortunately the data's structure varies with the result count
            if result_count == 1:
                entry = results['entry']
            else: # result_count > 1
                utils.verbose_out(
                        "Query returned {} results; choosing the newest.".format(result_count))
                entry = results['entry'][0]

            if 'rel' in entry['link'][0]: # sanity check - the right one doesn't have a 'rel' attrib
                raise IOError("Unexpected 'rel' attribute in search link")
            asset_url = entry['link'][0]['href']
            output_file_name = entry['title'] + '.zip'
            assert entry['double']['name'] == 'cloudcoverpercentage'
            cloud_cover = float(entry['double']['content'])

        if pclouds < 100 and cloud_cover > pclouds:
            return None

        return {'basename': output_file_name, 'url': asset_url}

    @classmethod
    def query_gs(cls, tile, date, pclouds):
        """Query google's store of sentinel-2 data for the given scene."""
        tile_prefix = 'tiles/{}/{}/{}/'.format(tile[0:2], tile[2], tile[3:])
        prefix_template = tile_prefix + '{}_MSIL1C_' + date.strftime('%Y%m%d')
        # It might be S2A or S2B, find out which one
        for sensor in cls._sensors.keys():
            search_prefix = prefix_template.format(sensor)
            # only going to be one prefix, if any are found
            prefix = cls.gs_api_search(search_prefix).get(
                'prefixes', [None])[0]
            if prefix is not None:
                break
        if prefix is None:
            return None

        # search for the parts of the asset we need
        # it's not clear if/when google is going to update their sentinel-2
        # data to have reprocessed single-tile assets
        style = cls.ds_style if date < cls.st_style_start_date else cls.st_style
        style_regexes = cls.get_style_regexes(style, tile, compile=True)
        band_regex = style_regexes['raster-re']
        md_regexes = {'datastrip-md': style_regexes['datastrip-md-re'],
                      'tile-md':      style_regexes['tile-md-re'],
                      'asset-md':     style_regexes['asset-md-re']}
        # for sanity checking later
        expected_key_set = set(md_regexes.keys() + ['spectral-bands'])
        expected_band_cnt = len(cls._sensors['S2A']['band-strings'])
        bands = []
        keys = {'spectral-bands': bands}
        for i in cls.gs_api_search(prefix, delimiter=None)['items']:
            k = i['name']
            p = k.replace(tile_prefix, '', 1)
            if len(bands) < expected_band_cnt and band_regex.match(p):
                bands.append(k)
            else:
                for md_key, regex in md_regexes.items():
                    if regex.match(p):
                        utils.verbose_out('query_gs found {}:  {}'.format(md_key, k), 5)
                        keys[md_key] = k
                        del md_regexes[md_key] # don't repeat useless searches
                    elif k.endswith('xml'):
                        utils.verbose_out('query_gs found unmatched XML file: {}'.format(k), 5)

        # sort correctly despite the wart in the band numbering scheme ('8A')
        def band_sort_key(fn):
            band = band_regex.match(fn).group('band')
            return 8.5 if band == '8A' else int(band)
        bands.sort(key=band_sort_key)

        # check for asset completeness
        if expected_band_cnt != len(bands):
            utils.verbose_out("Found GS asset wasn't complete for"
                              " (L1CGS, {}, {}); expected {} bands but got {}.".format(
                tile, date, expected_band_cnt, len(bands)), 2)
            return None
        missing_keys = expected_key_set - set(keys.keys())
        if missing_keys:
            utils.verbose_out("Found GS asset wasn't complete for"
                              " (L1CGS, {}, {}); keys not found: {}".format(
                tile, date, missing_keys), 2)
            return None

        # handle cloud cover
        r = requests.get(cls.gs_object_url_base() + keys['tile-md'])
        r.raise_for_status()
        cc = cls.cloud_cover_from_et(
                ElementTree.parse(StringIO.StringIO(r.text)))
        if cc > pclouds:
            cc_msg = ('C1GS asset found for ({}, {}), but cloud cover'
                      ' percentage ({}%) fails to meet threshold ({}%)')
            utils.verbose_out(cc_msg.format(tile, date, cc, pclouds), 3)
            return None
        # save it in the asset file to reduce network traffic
        keys['cloud-cover'] = cc

        utils.verbose_out('Found complete L1CGS asset for'
                          ' ({}, {})'.format(tile, date), 3)
        return dict(basename=(prefix.split('/')[-2] + '_gs.json'), keys=keys)

    @classmethod
    @lru_cache(maxsize=100) # cache size chosen arbitrarily
    def query_service(cls, asset, tile, date, pclouds=100, **ignored):
        """as superclass, but bifurcate between google and ESA sources."""
        if not cls.available(asset, date):
            return None
        source = cls.get_setting('source')
        if cls._assets[asset]['source'] != source:
            return None
        rv = {'esa': cls.query_esa,
              'gs':  cls.query_gs, }[source](tile, date, pclouds)
        utils.verbose_out(
            'queried ATD {} {} {}, found '.format(asset, tile, date)
            + ('nothing' if rv is None else rv['basename']), 5)
        return rv

    @classmethod
    def fetch_gs(cls, asset, tile, date, pclouds):
        """Fetch from Google Storage, but only if asset type is L1CGS"""
        qs_rv = cls.query_service(asset, tile, date, pclouds)
        if qs_rv is None:
            return []
        keys = qs_rv['keys']
        # keys have been checked in query_gs already, so just take 'em
        a_content = {k: cls.gs_object_url_base() + keys[k]
                     for k in keys if k.endswith('-md')}
        a_content['spectral-bands'] = [
            cls.gs_vsi_prefix() + b for b in keys['spectral-bands']]
        a_content['cloud-cover'] = keys['cloud-cover']
        cls.gs_stage_asset(qs_rv['basename'], a_content)

    @classmethod
    def fetch_esa(cls, asset, tile, date, pclouds):
        """Fetch an asset from ESA if asset type is L1C."""
        qs_rv = cls.query_service(asset, tile, date, pclouds)
        if qs_rv is None:
            return []
        output_file_name, asset_url = (qs_rv['basename'], qs_rv['url'])

        # datastrip-style assets cover many tiles, so there may be
        # duplication of effort; avoid that by aborting if the stage
        # already contains the desired asset
        full_staged_path = os.path.join(cls.Repository.path('stage'),
                                        output_file_name)
        if os.path.exists(full_staged_path):
            utils.verbose_out('Asset `{}` needed but already in stage/,'
                              ' skipping.'.format(output_file_name))
            return []

        username = cls.Repository.get_setting('username')
        password = cls.Repository.get_setting('password')
        # download the asset via the asset URL, putting it in a temp folder, then move to the stage
        # if the download is successful (this is necessary to avoid a race condition between
        # archive actions and fetch actions by concurrent processes)
        fetch_cmd_template = ('wget --no-check-certificate --user="{}" --password="{}" --timeout=30'
                              ' --no-verbose --output-document="{}" "{}"')
        if gippy.Options.Verbose() != 0:
            fetch_cmd_template += ' --show-progress --progress=dot:giga'
        utils.verbose_out("Fetching " + output_file_name)
        with utils.error_handler("Error performing asset download '({})'".format(asset_url)):
            tmp_dir_full_path = tempfile.mkdtemp(dir=cls.Repository.path('stage'))
            try:
                output_full_path = os.path.join(tmp_dir_full_path, output_file_name)
                fetch_cmd = fetch_cmd_template.format(
                        username, password, output_full_path, asset_url)
                args = shlex.split(fetch_cmd)
                p = subprocess.Popen(args)
                p.communicate()
                if p.returncode != 0:
                    raise IOError("Expected wget exit status 0, got {}".format(p.returncode))
                cls.stage_asset(output_full_path, output_file_name)
            finally:
                shutil.rmtree(tmp_dir_full_path) # always remove the dir even if things break
        return [output_full_path]

    @classmethod
    def fetch(cls, asset, tile, date, pclouds=100, **ignored):
        """Fetch an asset."""
        source = cls.get_setting('source')
        return {'esa': cls.fetch_esa,
                'gs':  cls.fetch_gs, }[source](asset, tile, date, pclouds)

    @classmethod
    def archive(cls, path, recursive=False, keep=False, update=False):
        """Archive Sentinel-2 assets.

        Datastrip assets have special archiving needs due to their
        multi-tile nature, so this method archives them specially using
        hard links.
        """
        if recursive:
            raise ValueError('Recursive asset search not supported by Sentinel-2 driver.')

        found_files = {cls.ds_style: [], cls.st_style: []}

        # find all the files that resemble assets in the given spot
        fn_pile = sum([utils.find_files(cls._assets[at]['pattern'], path)
                       for at in _asset_types], [])
        for fn in fn_pile:
            with utils.error_handler('Error archiving asset', continuable=True):
                bn = os.path.basename(fn)
                for style, style_dict in cls._asset_styles.items():
                    match = re.match(style_dict['downloaded-name-re'], bn)
                    if match is not None:
                        found_files[style].append(fn) # save the found path, not the basename
                        break
                if match is None:
                    raise IOError("Asset file name is incorrect for Sentinel-2: '{}'".format(bn))

        assets = []
        overwritten_assets = []
        for fn in found_files[cls.st_style]:
            new_aol, new_overwritten_aol = super(sentinel2Asset, cls).archive(
                    fn, False, keep, update)
            assets += new_aol
            overwritten_assets += new_overwritten_aol

        for fn in found_files[cls.ds_style]:
            tile_list = cls.ds_tile_list(fn)
            # use the stage dir since it's likely not to break anything (ie on same filesystem)
            with utils.make_temp_dir(dir=cls.Repository.path('stage')) as tdname:
                for tile in tile_list:
                    tiled_fp = os.path.join(tdname, tile + '_' + os.path.basename(fn))
                    os.link(fn, tiled_fp)
                orig_aol, orig_overwritten_aol = (
                        super(sentinel2Asset, cls).archive(
                                tdname, False, False, update))
                assets += orig_aol
                overwritten_assets += orig_overwritten_aol
            if not keep:
                utils.RemoveFiles([fn], ['.index', '.aux.xml'])

        return assets, overwritten_assets


    @classmethod
    def stage_asset(cls, asset_full_path, asset_base_name):
        """Copy the given asset to the stage."""
        stage_path = cls.Repository.path('stage')
        stage_full_path = os.path.join(stage_path, asset_base_name)
        os.rename(asset_full_path, stage_full_path) # on POSIX, if it works, it's atomic


    @classmethod
    def ds_tile_list(cls, file_name):
        """Extract a list of tiles from the given datastrip-style asset."""
        tiles = set()
        file_pattern = cls._asset_styles[cls.ds_style]['raster-re'].format(
            tileid=cls._tile_re)
        p = re.compile(file_pattern)
        with zipfile.ZipFile(file_name) as asset_zf:
            for f in asset_zf.namelist():
                m = p.match(f)
                if m:
                    tiles.add(m.group('tile'))
        if len(tiles) == 0:
            raise IOError(file_name + ' contains no raster files')
        return list(tiles)

    @classmethod
    def cloud_cover_from_et(cls, tree):
        """Tree needs to be an ElementTree object."""
        root = tree.getroot()
        nsre = r'^({.+})Level-1C_Tile_ID$'
        ns = None
        for el in root.iter():
            match = re.match(nsre, el.tag)
            if match:
                ns = match.group(1)
                break
        if ns is None:
            raise Exception("Tile metadata xml namespace could not be found")
        cloud_cover_xpath = ("./{}Quality_Indicators_Info/Image_Content_QI"
                             "/CLOUDY_PIXEL_PERCENTAGE")
        cloud_coverage_el = root.findall(cloud_cover_xpath.format(ns))[0]
        return float(cloud_coverage_el.text)

    def cloud_cover(self):
        """Returns cloud cover for the current asset.

        Caches and returns the value found in self.meta['cloud-cover']."""
        if 'cloud-cover' in self.meta:
            return self.meta['cloud-cover']
        if os.path.exists(self.filename):
            with utils.make_temp_dir() as tmpdir:
                metadata_file = next(f for f in self.datafiles()
                    if re.match(self.style_res['tile-md-re'], f))
                self.extract([metadata_file], path=tmpdir)
                tree = ElementTree.parse(tmpdir + '/' + metadata_file)
            self.meta['cloud-cover'] = self.cloud_cover_from_et(tree)
            return self.meta['cloud-cover']

        results = self.query_scihub(
            self.tile,
            datetime.datetime.strptime(self.date.strftime('%Y-%m-%d'),'%Y-%m-%d')
        )
        try:
            entry = results['feed']['entry']
        except:
            raise ValueError(self.filename + " doesn't exist locally and"
                             " remote metadata couldn't be loaded")
        if type(entry) is list: # XML is just the best thing
            entry = entry[0]
        assert entry['double']['name'] == 'cloudcoverpercentage'
        return float(entry['double']['content'])

    def filter(self, pclouds=100, **kwargs):
        if pclouds >= 100:
            return True
        cc = self.cloud_cover()
        asset_passes_filter = cc <= pclouds
        if asset_passes_filter:
            msg = 'Asset cloud cover is {} %, meets pclouds threshold of {} %'
        else:
            msg = ('Asset cloud cover is {} %,'
                   ' fails to meet pclouds threshold of {} %')
        utils.verbose_out(msg.format(cc, pclouds), 3)
        return asset_passes_filter

    def save_tile_md_file(self, path):
        if self.asset == 'L1C':
            tile_md_fn = next(fn for fn in self.datafiles()
                              if re.match(self.style_res['tile-md-re'], fn))
            self.extract((tile_md_fn,), path)
            return os.path.join(path, tile_md_fn)
        # L1CGS case:
        r = requests.get(self.json_content['tile-md'])
        r.raise_for_status()
        fp = os.path.join(path, 'MTD_TL.xml')
        with open(fp, 'wb') as fo:
            fo.write(r.content)
        return fp

    def xml_subtree_esa(self, md_file_type):
        """Loads XML, then returns the etree object for it.

        File to read is specified by type eg 'tile' or 'datastrip'.
        """
        file_pattern = self.style_res[md_file_type + '-md-re']
        metadata_fn = next(fn for fn in self.datafiles() if re.match(file_pattern, fn))
        utils.verbose_out(
            'Found {} metadata file:  {}'.format(md_file_type, metadata_fn), 5)
        with zipfile.ZipFile(self.filename) as asset_zf:
            with asset_zf.open(metadata_fn) as metadata_zf:
                return ElementTree.parse(metadata_zf)

    def xml_subtree_gs(self, md_file_type):
        r = requests.get(self.json_content[md_file_type + '-md'])
        r.raise_for_status()
        return ElementTree.fromstring(r.content)

    def xml_subtree(self, md_file_type, *tags):
        tree = {'L1C': self.xml_subtree_esa,
                'L1CGS': self.xml_subtree_gs,
               }[self.asset](md_file_type)
        try:
            stl = [next(tree.iter(at)) for at in tags]
        except StopIteration:
            err_str = "For Sentinel-2 {} {} {}, couldn't find {} in {}"
            raise IOError(err_str.format(
                self.asset, self.date, self.tile, tags, md_file_type))
        return stl if len(stl) > 1 else stl[0]

    def tile_metadata(self):
        """Read the tile metadata xml file and extract values of interest.

        Return values are in degrees.  Mainly exists to avoid reading
        the file more than once.
        """

        if self.tile_meta is not None:
            return self.tile_meta
        mva_elem, msa_elem = self.xml_subtree(
            'tile', 'Mean_Viewing_Incidence_Angle_List', 'Mean_Sun_Angle')
        # set viewing angle metadata (should only be one list, with 13 elems,
        # each with 2 angles, a zen and an az)
        angles = mva_elem.findall('Mean_Viewing_Incidence_Angle')
        mvza = numpy.mean([float(e.find('ZENITH_ANGLE').text) for e in angles])
        mvaa = numpy.mean([float(e.find('AZIMUTH_ANGLE').text) for e in angles])
        # set solar angle metadata
        msza = float(msa_elem.find('ZENITH_ANGLE').text)
        msaa = float(msa_elem.find('AZIMUTH_ANGLE').text)
        self.tile_meta = mvza, mvaa, msza, msaa
        return self.tile_meta

    @lru_cache(maxsize=1)
    def raster_full_paths(self):
        rfn_re = re.compile(self.style_res['raster-re'])
        fnl = [df for df in self.datafiles() if rfn_re.match(df)]
        # have to sort the list or else gippy will get confused about which band is which
        bs = self.sensor_spec('band-strings')
        # sorting is weird because the bands aren't named consistently
        fnl.sort(key=lambda f: bs.index(f[-6:-4]))
        return fnl

    def solar_irradiances(self):
        """Loads solar irradiances from asset metadata and returns them.

        The order of the list matches the band list above.  Irradiance
        values are in watts/(m^2 * micrometers).  Wikipedia claims it is
        really "spectral flux density" and measures the power flowing onto
        a surface per unit wavelength:
        https://en.wikipedia.org/wiki/Spectral_flux_density
        """
        sil_elem = self.xml_subtree('datastrip', 'Solar_Irradiance_List')
        values_tags = sil_elem.findall('SOLAR_IRRADIANCE')
        # sanity check that the bands are in the right order
        assert range(13) == [int(vt.attrib['bandId']) for vt in values_tags]
        return [float(vt.text) for vt in values_tags]

    #def gridded_zenith_angle(self):
    #    """Loads and returns zenith angle from the asset metadata.
    #
    #    These are stored in MTD_TL.xml, in degrees, at 5km x 5km resolution.
    #    """
    #    asset_contents = self.datafiles()
    #    # python idiom for "first item in list that satisfies a condition"; should only be one
    #    metadata_fn = next(n for n in asset_contents if re.match('^.*/GRANULE/.*/MTD_TL.xml$', n))
    #    with zipfile.ZipFile(self.filename) as asset_zf:
    #        with asset_zf.open(metadata_fn) as metadata_zf:
    #            tree = ElementTree.parse(metadata_zf)
    #            sag_elem = next(tree.iter('Sun_Angles_Grid')) # should only be one
    #            values_tags = sag_elem.find('Zenith').find('Values_List').findall('VALUES')
    #            text_rows = [vt.text for vt in values_tags]
    #            zenith_grid = []
    #            for tr in text_rows:
    #                numerical_row = [float(t) for t in tr.split()]
    #                zenith_grid.append(numerical_row)
    #    return zenith_grid


    def radiance_factors(self):
        """Computes values needed for converting L1C to TOA radiance.

        Sentinel-2's L1C is a TOA reflectance product.  That can be
        reverted to a TOA radiance product by multiplying each data
        point by a constant factor.  The factor is constant for each
        band of a given asset; the ordering in the returned list is the
        same as the order of the bands in _sensors given above.  See:
        https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/level-1c/algorithm
        """
        mza = math.radians(self.tile_metadata()[2])
        solar_irrads = self.solar_irradiances()
        julian_date = utils.julian_date(datetime.datetime.combine(self.date, self.time), 'cnes')
        return [(1 - 0.01673 * math.cos(0.0172 * (julian_date - 2)))**-2 # solar distance term
                * math.cos(mza) / math.pi # solar angle term
                * si # "equivalent extra-terrestrial solar spectrum" term; aka solar irradiance
                / 1000.0 # revert scaling factor so 16-bit ints aren't overflowed
                for si in solar_irrads]


    def generate_atmo_corrector(self):
        """Generate & return a SIXS object appropriate for this asset.

        Re-usees a previously created object if possible.
        """
        if hasattr(self, '_atmo_corrector'):
            utils.verbose_out('Found existing atmospheric correction object, reusing it.', 4)
            return self._atmo_corrector
        utils.verbose_out('Generating atmospheric correction object.', 4)
        sensor_md = self._sensors[self.sensor]
        visbands = sensor_md['indices-colors'] # TODO visbands isn't really the right name
        vb_indices = [sensor_md['colors'].index(vb) for vb in visbands]
        # assemble list of relevant band boundaries
        wvlens = [sensor_md['bandbounds'][i] for i in vb_indices]
        # assemble geometries
        viewing_zn, viewing_az, solar_zn, solar_az = self.tile_metadata()
        (w_lon, e_lon, s_lat, n_lat) = self.Repository.tile_lat_lon(self.tile)
        geo = {
            'zenith': viewing_zn,
            'azimuth': viewing_az,
            'solarzenith': solar_zn,
            'solarazimuth': solar_az,
            'lon': (w_lon + e_lon) / 2.0, # copy landsat - use center of tile
            'lat': (s_lat + n_lat) / 2.0, # copy landsat - use center of tile
        }
        dt = datetime.datetime.combine(self.date, self.time)
        self._atmo_corrector = atmosphere.SIXS(visbands, wvlens, geo, dt, sensor=self.sensor)
        return self._atmo_corrector

    def footprint(self):
        gf_elem = self.xml_subtree('asset', 'Global_Footprint')
        values_tags = gf_elem.find('EXT_POS_LIST')

        # format as valid WKT
        points = values_tags.text.strip().split(" ")
        zipped_points = izip_longest(*[iter(points)]*2)  # fancy way to group list into pairs
        wkt_points = ", ".join([y + " " + x for x, y in list(zipped_points)])
        footprint_wkt = "POLYGON (({}))".format(wkt_points)

        # For datastrip assets, `Global_Footprint` is the entire swath,
        # so intersect it with tile boundary to get actual footprint.
        tile_polygon = wkt_loads(self.get_geometry())
        return tile_polygon.intersection(wkt_loads(footprint_wkt)).wkt


class sentinel2Data(Data):
    name = 'Sentinel2'
    version = '0.1.1'
    Asset = sentinel2Asset

    _productgroups = {
        'Index': [
            'ndvi', 'evi', 'lswi', 'ndsi', 'bi', 'satvi', 'msavi2', 'vari',
            'brgt', 'ndti', 'crc', 'crcm', 'isti', 'sti',
        ],
        'ACOLITE': ['rhow', 'oc2chl', 'oc3chl', 'fai',
                    'spm', 'spm2016', 'turbidity', 'acoflags'],
    }

    _products = {
        # standard products
        'rad': {
            'description': 'Surface-leaving radiance',
            'assets': _asset_types,
            'bands': [{'name': band_name, 'units': 'W/m^2/um'} # aka watts/(m^2 * micrometers)
                      for band_name in Asset._sensors['S2A']['indices-colors']],
            # 'startdate' and 'latency' are optional for DH
        },
        'ref': {
            'description': 'Surface reflectance',
            'assets': _asset_types,
            'bands': [{'name': band_name, 'units': Data._unitless}
                      for band_name in Asset._sensors['S2A']['indices-colors']],
        },
        'cfmask': {
            'description': 'Cloud, cloud shadow, and water classification',
            'assets': _asset_types,
            'bands': {'name': 'cfmask', 'units': Data._unitless},
            'toa': True,
        },
        'cloudmask': {
            'description': 'Cloud mask',
            'assets': _asset_types,
            'bands': {'name': 'cloudmask', 'units': Data._unitless},
        },
    }

    # add index products to _products
    _products.update(
        (p, {'description': d,
             'assets': _asset_types,
             'bands': [{'name': p, 'units': Data._unitless}]}
        ) for p, d in [
            # duplicated in modis and landsat; may be worth it to DRY out
            ('ndvi',   'Normalized Difference Vegetation Index'),
            ('evi',    'Enhanced Vegetation Index'),
            ('lswi',   'Land Surface Water Index'),
            ('ndsi',   'Normalized Difference Snow Index'),
            ('bi',     'Brightness Index'),
            ('satvi',  'Soil-Adjusted Total Vegetation Index'),
            ('msavi2', 'Modified Soil-adjusted Vegetation Index'),
            ('vari',   'Visible Atmospherically Resistant Index'),
            ('brgt',   'VIS and NIR reflectance, weighted by solar energy distribution.'),
            # index products related to tillage
            ('ndti',   'Normalized Difference Tillage Index'),
            ('crc',    'Crop Residue Cover (uses BLUE)'),
            ('crcm',   'Crop Residue Cover, Modified (uses GREEN)'),
            ('isti',   'Inverse Standard Tillage Index'),
            ('sti',    'Standard Tillage Index'),
        ]
    )

    # indices not processed by gippy.Indices(); L1CGS not supported:
    _products.update(
        (p, {'description': d, 'assets': ('L1C',),
             'bands': [{'name': p, 'units': Data._unitless}]}
        ) for p, d in [
            ('mtci',    'MERIS Terrestrial Chlorophyll Index'),
            ('s2rep',   'Sentinel-2 Red Edge Position')])

    # acolite doesn't (yet?) support google storage sentinel-2 data
    atmosphere.add_acolite_product_dicts(_products, 'L1C')

    _product_dependencies = {
        'indices':      'ref',
        'indices-toa':  'ref-toa',
        'ref':          'rad-toa',
        'rad':          'rad-toa',
        'rad-toa':      'ref-toa',
        'ref-toa':      None, # has no deps but the asset
        'cfmask':       None,
        'mtci-toa':     'ref-toa',
        's2rep-toa':    'ref-toa',
        'mtci':         'ref',
        's2rep':        'ref',
        'cloudmask':	'cfmask',
    }

    need_fetch_kwargs = True

    def plan_work(self, requested_products, overwrite):
        """Plan processing run using requested products & their dependencies.

        Returns a set of processing steps needed to generate
        requested_products.  For instance, 'rad-toa' depends on
        'ref-toa', so if the user requests 'rad-toa', set(['rad-toa',
        'ref-toa']) is returned.  But if 'ref-toa' is already in the
        inventory, it is omitted, unless overwrite is True.
        requested_products should contain strings matching
        _product_dependencies above.
        """
        surf_indices = self._productgroups['Index']
        toa_indices  = [i + '-toa' for i in self._productgroups['Index']]
        acolite_products = self._productgroups['ACOLITE']
        _pd = self._product_dependencies
        work = set()
        for rp in requested_products:
            # handle indices specially
            if rp in surf_indices:
                prereq = 'indices'
            elif rp in toa_indices:
                prereq = 'indices-toa'
            elif rp in acolite_products:
                prereq = None
            else:
                if rp not in _pd:
                    raise ValueError(
                            'Could not find dependency listing for ' + rp)
                prereq = rp
            # go thru each prereq and add it in if it's not already present, respecting overwrite.
            while prereq in _pd and (overwrite or prereq not in self.products):
                work.add(prereq)
                prereq = _pd[prereq]
        return work

    def current_asset(self):
        return next(self.assets[at]
                    for at in _asset_types if at in self.assets)

    def current_sensor(self):
        return self.current_asset().sensor

    def load_image(self, product):
        """Load a product file into a GeoImage and return it

        The GeoImage is instead fetched from a cache if possible.
        (sensor, product) should match an entry from self.filenames.
        """
        if product in self._product_images:
            return self._product_images[product]
        image = gippy.GeoImage(self.filenames[(self.current_sensor(), product)])
        self._product_images[product] = image
        return image

    def _drop_geoimage_cache(self):
        """GeoImage objects hold a file handle.  Dropping them to avoid
        filesystme complications.
        """
        for k in self._product_images:
            v = self._product_images.pop(k)
            del v

    @classmethod
    def normalize_tile_string(cls, tile_string):
        """Sentinel-2 customized tile-string normalizer.

        Raises an exception if the tile string doesn't match MGRS
        format, and converts the tile string to uppercase.
        """
        if not re.match(r'^\d\d[a-zA-Z]{3}$', tile_string):
            err_msg = "Tile string '{}' doesn't match MGRS format (eg '04QFJ')".format(tile_string)
            raise IOError(err_msg)
        return tile_string.upper()

    @classmethod
    def add_filter_args(cls, parser):
        """Add custom filtering options for sentinel2."""
        help_str = ('cloud percentage threshold; assets with cloud cover'
                    ' percentages higher than this value will be filtered out')
        parser.add_argument('--pclouds', help=help_str,
                            type=cls.natural_percentage, default=100)

    def filter(self, pclouds=100, **kwargs):
        return all([asset.filter(pclouds, **kwargs) for asset in self.assets.values()])

    def prep_meta(self, additional=None):
        meta = super(sentinel2Data, self).prep_meta(
            self.current_asset().filename, additional)
        return meta

    # TODO move to Asset?
    @lru_cache(maxsize=1)
    def raster_paths(self):
        """Return paths to raster files, extracting them if necessary."""
        ao = self.current_asset()
        if ao.asset == 'L1CGS':
            return ao.json_content['spectral-bands']
        with utils.error_handler('Error reading ' + ao.basename):
            fnl = ao.raster_full_paths()
            if self.get_setting('extract'):
                return ao.extract(fnl)
            # Use zipfile directly using GDAL's virtual filesystem
            return [os.path.join('/vsizip/' + ao.filename, f) for f in fnl]

    def _download_gcs_bands(self, output_dir):
        if self.current_asset().asset != 'L1CGS':
            raise

        self._time_report('Start download from GCS')
        band_files = []
        for path in self.raster_paths():
            match = re.match("/[\w_]+/(.+)", path)
            url = match.group(1)
            output_path = os.path.join(
                output_dir, os.path.basename(url)
            )
            if not os.path.exists(output_path):
                self.Asset.gs_backoff_downloader(url, output_path)
            band_files.append(output_path)
        self._time_report('Finished download from GCS ({} bands)'.format(len(band_files)))
        return band_files

    def ref_toa_geoimage(self):
        """Make a proto-product which acts as a basis for several products.

        It is equivalent to ref-toa; it's needed because the asset's
        spatial resolution must be resampled to be equal for all bands
        of interest.
        """
        self._time_report('Start VRT for ref-toa image')
        ao = self.current_asset()
        indices_bands, b_strings, colors = ao.sensor_spec(
            'indices-bands', 'band-strings', 'colors')
        vrt_filename = os.path.join(self._temp_proc_dir,
                                    self.basename + '_ref-toa.vrt')
        cmd_args = ('gdalbuildvrt -tr 20 20 -separate'
                    ' -srcnodata 0 -vrtnodata 0').split(' ')
        if ao.asset == 'L1CGS':
            raster_paths = self._download_gcs_bands(self._temp_proc_dir)
        else:
            raster_paths = self.raster_paths()
        cmd_args += [vrt_filename] + [
            f for f in raster_paths if f[-6:-4] in indices_bands]
        p = subprocess.Popen(cmd_args)
        p.communicate()
        if p.returncode != 0:
            raise IOError("Expected gdalbuildvrt exit status 0,"
                          " got {}".format(p.returncode))

        vrt_img = gippy.GeoImage(vrt_filename)
        vrt_img.SetNoData(0)
        vrt_img.SetGain(0.0001) # 16-bit storage values / 10^4 = refl values
        # eg:   1        '02', which yields color_name 'BLUE'
        for band_num, band_string in enumerate(indices_bands, 1): # starts at 0
            vrt_img.SetBandName(colors[b_strings.index(band_string)], band_num)
        self._product_images['ref-toa'] = vrt_img
        self._time_report('Finished VRT for ref-toa image')

    def rad_toa_geoimage(self):
        """Reverse-engineer TOA ref data back into a TOA radiance product.

        This is used as intermediary data but is congruent to the rad-toa
        product.
        """
        self._time_report('Starting reversion to TOA radiance.')
        reftoa_img = self.load_image('ref-toa')
        asset_instance = self.current_asset()
        colors = asset_instance.sensor_spec('colors')
        radiance_factors = asset_instance.radiance_factors()
        rad_image = gippy.GeoImage(reftoa_img)

        for i in range(len(rad_image)):
            color = rad_image[i].Description()
            rf = radiance_factors[colors.index(color)]
            self._time_report(
                'TOA radiance reversion factor for {} (band {}): {}'.format(color, i + 1, rf))
            rad_image[i] = rad_image[i] * rf
        rad_image.SetNoData(0)
        self._product_images['rad-toa'] = rad_image

    def rad_geoimage(self):
        """Transmute TOA radiance product into a surface radiance product."""
        self._time_report('Setting up for converting radiance from TOA to surface')
        rad_toa_img = self.load_image('rad-toa')
        ca = self.current_asset()
        atm6s = ca.generate_atmo_corrector()

        rad_image = gippy.GeoImage(rad_toa_img)
        # to check the gain & other values set on the object:
        # print('rad_image info:', rad_image.Info()

        # set meta to pass along to indices
        rad_image._aod_source = str(atm6s.aod[0])
        rad_image._aod_value  = str(atm6s.aod[1])

        for c in ca._sensors[self.current_sensor()]['indices-colors']:
            (T, Lu, Ld) = atm6s.results[c] # Ld is unused for this product
            # 6SV1/Py6S/SIXS produces atmo correction values suitable
            # for raw values ("digital numbers") from landsat, but
            # rad_toa_img isn't a raw value; it has a gain.  So, apply
            # that same gain to Lu, apparently the atmosphere's
            # inherent radiance, to get a reasonable difference.
            lu = 0.0001 * Lu
            rad_image[c] = (rad_toa_img[c] - lu) / T
        self._product_images['rad'] = rad_image


    def process_indices(self, mode, sensor, indices):
        """Generate the given indices.

        gippy.algorithms.Indices is called for the given indices, using
        an image appropriate for the given mode ('toa' or not).
        """
        if len(indices) == 0:
            return

        self._time_report('Starting indices processing for: {}'.format(indices.keys()))

        metadata = self.prep_meta()
        if mode != 'toa':
            image = self.load_image('ref')
            # this faff is needed because gippy shares metadata across images behind your back
            metadata['AOD Source'] = getattr(image, '_aod_source', image.Meta('AOD Source'))
            metadata['AOD Value']  = getattr(image, '_aod_value',  image.Meta('AOD Value'))
        else:
            image = self.load_image('ref-toa')

        # reminder - indices' values are the keys, split by hyphen, eg {ndvi-toa': ['ndvi', 'toa']}
        gippy_input = {} # map prod types to temp output filenames for feeding to gippy
        tempfps_to_ptypes = {} # map temp output filenames to prod types, needed for AddFile
        for prod_type, pt_split in indices.items():
            temp_fp = self.temp_product_filename(sensor, prod_type)
            gippy_input[pt_split[0]] = temp_fp
            tempfps_to_ptypes[temp_fp] = prod_type

        prodout = gippy.algorithms.Indices(image, gippy_input, metadata)

        for temp_fp in prodout.values():
            archived_fp = self.archive_temp_path(temp_fp)
            self.AddFile(sensor, tempfps_to_ptypes[temp_fp], archived_fp)

        self._time_report(' -> %s: processed %s' % (self.basename, indices))

    # this function creates a geolocation error
    #def shrunk_bbox(self, tile):
        #w_lon, e_lon, s_lat, n_lat = self.Repository.tile_lat_lon(tile)
        #latlon = pyproj.Proj(init='epsg:4326')
        #utm = pyproj.Proj(init='epsg:326{}'.format(tile[0:2]))

        #w_lon_utm, s_lat_utm = pyproj.transform(latlon, utm, w_lon, s_lat)
        #e_lon_utm, n_lat_utm = pyproj.transform(latlon, utm, e_lon, n_lat)

        #lon_diff = (e_lon_utm - w_lon_utm) / 16
        #lat_diff = (n_lat_utm - s_lat_utm) / 16

        #w_lon_shrunk, s_lat_shrunk = pyproj.transform(utm, latlon, w_lon_utm + lon_diff, s_lat_utm + lat_diff)
        #e_lon_shrunk, n_lat_shrunk = pyproj.transform(utm, latlon, e_lon_utm - lon_diff, n_lat_utm - lat_diff)

        #return w_lon_shrunk, e_lon_shrunk, s_lat_shrunk, n_lat_shrunk


    def process_acolite(self, aco_prods):
        a_obj, sensor = self.current_asset(), self.current_sensor()
        self._time_report("Starting acolite processing")
        # let acolite use a subdirectory in this run's tempdir:
        aco_dn = self.generate_temp_path('acolite')
        os.mkdir(aco_dn)
        # TODO use self.temp_product_filename(sensor, prod_type)
        # then copy into self.path the right way
        p_spec = {p: os.path.join(self.path, self.product_filename(sensor, p))
                  for p in aco_prods}
        layer_02_abs_fn = next(fn for fn in self.raster_paths()
                               if fn.endswith('_B02.jp2'))
        model_image = gippy.GeoImage(layer_02_abs_fn)

        prodout = atmosphere.process_acolite(a_obj, aco_dn, p_spec,
                self.prep_meta(), model_image, "*.SAFE")

        [self.AddFile(sensor, pt, fn) for pt, fn in prodout.items()]
        self._time_report(' -> {}: processed {}'.format(
                self.basename + '_' + sensor, prodout.keys()))

    def ref_geoimage(self):
        """Generate a surface reflectance image.

        Made from a rad-toa image (the reverted ref-toa data sentinel-2 L1C
        provides), put through an atmospheric correction process.  CF landsat.
        """
        ao = self.current_asset()
        self._time_report('Computing atmospheric corrections for surface reflectance')
        atm6s = ao.generate_atmo_corrector()
        scaling_factor = 0.001 # to prevent chunky small ints
        rad_toa_image = self.load_image('rad-toa')
        sr_image = gippy.GeoImage(rad_toa_image)
        # set meta to pass along to indices
        sr_image._aod_source = str(atm6s.aod[0])
        sr_image._aod_value  = str(atm6s.aod[1])
        for c in ao.sensor_spec('indices-colors'):
            (T, Lu, Ld) = atm6s.results[c]
            lu = 0.0001 * Lu # see rad_geoimage for reason for this
            TLdS = T * Ld * scaling_factor
            sr_image[c] = (rad_toa_image[c] - lu) / TLdS
        self._product_images['ref'] = sr_image

    def fmask_geoimage(self):
        """Generate cloud mask.

        Uses python implementation of cfmask. Builds a VRT of all the necessary
        bands in the proper order, an angles image is created using the supplied
        metadata, and then the two are put through the fmask algorithm.
        """
        self._time_report('Generating cloud mask')

        ao = self.current_asset()

        DEVNULL = open(os.devnull, 'w')

        print("ASSET", ao.asset)
        if ao.asset == 'L1CGS':
            band_files = self._download_gcs_bands(self._temp_proc_dir)
        else:
            band_files = self.raster_paths()
        gdalbuildvrt_args = [
            "gdalbuildvrt",
            "-resolution", "user",
            "-tr", "20", "20",
            "-separate",
            "%s/allbands.vrt" % self._temp_proc_dir,
        ] + band_files
        subprocess.check_call(gdalbuildvrt_args, stderr=DEVNULL)

        # set up commands
        angles_cmd_list = [
            "fmask_sentinel2makeAnglesImage.py",
            "-i", ao.save_tile_md_file(self._temp_proc_dir),
            "-o", "%s/angles.img" % self._temp_proc_dir,
        ]
        fmask_cmd_list = [
            "fmask_sentinel2Stacked.py",
            "-a", "%s/allbands.vrt" % self._temp_proc_dir,
            "-z", "%s/angles.img" % self._temp_proc_dir,
            "-o", "%s/cloudmask.tif" % self._temp_proc_dir,
            "--cloudprobthreshold", "5",
            "-v",
        ]
        # Temp dir for intermediaries that pyfmask generates in the current
        # working directory.  The mask is output to self._temp_proc_dir.
        with utils.make_temp_dir(prefix='gips-py-fmask', dir='/tmp') as tdir:
            prev_wd = os.getcwd()
            os.chdir(tdir)
            try:
                self._time_report('running: ' + ' '.join(angles_cmd_list))
                subprocess.check_call(angles_cmd_list)
                self._time_report('running: ' + ' '.join(fmask_cmd_list))
                subprocess.check_call(fmask_cmd_list)
            finally:
                os.chdir(prev_wd)

        DEVNULL.close()
        fmask_image = gippy.GeoImage("%s/cloudmask.tif" % self._temp_proc_dir)
        self._product_images['cfmask'] = fmask_image


    def cloudmask_geoimage(self):
        fmask_image = self.load_image('cfmask')
        npfm = fmask_image.Read()
        # cfmask values:
        # 0 = NoData
        # 1 = Land
        # 2 = Cloud
        # 3 = Cloud Shadow
        # 4 = Snow
        # 5 = Water

        # Set cfmask 2 and 3 to 1's, everything else to 0's
        np_cloudmask = numpy.logical_or( npfm == 2, npfm == 3).astype('uint8')

        # cloudmask.tif is taken by cfmask
        cloudmask_filename = "%s/cloudmask2.tif" % self._temp_proc_dir
        cloudmask_img = gippy.GeoImage(
            cloudmask_filename,
            fmask_image,
            gippy.GDT_Byte,
            1
        )
        cloudmask_img[0].Write(np_cloudmask)
        self._product_images['cloudmask'] = cloudmask_img


    def mtci_geoimage(self, mode):
        """Generate Python implementation of MTCI."""
        # test this with eg:
        # gips_process sentinel2 -t 16TDP -d 2017-10-01 -v5 -p mtci --overwrite
        self._time_report('Generating MTCI')

        # change this to 'ref'
        ref_img = self.load_image('ref-toa' if mode == 'toa' else 'ref')

        b4 = ref_img['RED'].Read()
        b5 = ref_img['REDEDGE1'].Read()
        b6 = ref_img['REDEDGE2'].Read()

        gain = 0.0002
        missing = -32768

        mtci = missing + 0. * b4.copy()
        wg = (b4 > 0.)&(b4 <= 1.)&(b5 > 0.)&(b5 <= 1.)&(b6 > 0.)&(b6 <= 1.)&(b5 - b4 != 0.)
        mtci[wg] = ((b6[wg] - b5[wg]) / (b5[wg] - b4[wg]))
        mtci[(mtci < -6.)|(mtci >= 6.)] = missing
        mtci[mtci != missing] = mtci[mtci != missing]/gain
        mtci = mtci.astype('int16')

        mtci_filename = "%s/mtci.tif" % self._temp_proc_dir
        mtci_img = gippy.GeoImage(mtci_filename, ref_img, gippy.GDT_Int16, 1)

        mtci_img[0].Write(mtci)
        mtci_img[0].SetGain(gain)
        mtci_img[0].SetNoData(missing)

        self._product_images[
                'mtci-toa' if mode == 'toa' else 'mtci'] = mtci_img

    def s2rep_geoimage(self, mode):
        """Generate Python implementation of S2REP."""
        self._time_report('Generating S2REP')

        # change this to 'ref'
        ref_img = self.load_image('ref-toa' if mode == 'toa' else 'ref')

        b4 = ref_img['RED'].Read()
        b5 = ref_img['REDEDGE1'].Read()
        b6 = ref_img['REDEDGE2'].Read()
        b7 = ref_img['REDEDGE3'].Read()

        gain = 0.04
        offset = 400.
        missing = -32768

        s2rep = missing + 0. * b4.copy()
        wg = (b4 > 0.)&(b4 <= 1.)&(b5 > 0.)&(b5 <= 1.)&(b6 > 0.)&(b6 <= 1.)&(b7 > 0.)&(b7 <= 1.)&(b6 - b5 != 0.)
        s2rep[wg] = 705. + 35. * ((((b7[wg] + b4[wg])/2.) - b5[wg])/(b6[wg] - b5[wg]))

        s2rep[(s2rep < 400.)|(s2rep >= 1100.)] = missing
        s2rep[s2rep != missing] = (s2rep[s2rep != missing] - offset)/gain
        s2rep = s2rep.astype('int16')

        s2rep_filename = "%s/s2rep.tif" % self._temp_proc_dir
        s2rep_img = gippy.GeoImage(s2rep_filename, ref_img, gippy.GDT_Int16, 1)

        s2rep_img[0].Write(s2rep)
        s2rep_img[0].SetGain(gain)
        s2rep_img[0].SetOffset(offset)
        s2rep_img[0].SetNoData(missing)

        self._product_images[
                's2rep-toa' if mode == 'toa' else 's2rep'] = s2rep_img

    @Data.proc_temp_dir_manager
    def process(self, products=None, overwrite=False, **kwargs):
        """Produce data products and save them to files.

        If `products` is None, it processes all products.  If
        `overwrite` is True, it will overwrite existing products if they
        are found.  Products are saved to a well-known or else specified
        directory.  kwargs is unused, and is present for compatibility.
        """
        a_obj = self.current_asset()
        self._time_report(
            'Starting processing for Sentinel-2 {} {} {}'.format(
            a_obj.asset, a_obj.tile, a_obj.date))
        products = self.needed_products(products, overwrite)
        if len(products) == 0:
            utils.verbose_out('No new processing required.')
            return
        self._product_images = {}

        work = self.plan_work(products.requested.keys(), overwrite) # see if we can save any work

        if (a_obj.asset == 'L1C' and a_obj.style == a_obj.ds_style and
                work & set(self._productgroups['ACOLITE'])):
            raise NotImplementedError(
                "Datastrip assets aren't compatible with acolite")

        # only do the bits that need doing
        if 'ref-toa' in work:
            self.ref_toa_geoimage()
        if 'rad-toa' in work:
            self.rad_toa_geoimage()
        if 'rad' in work:
            self.rad_geoimage()
        if 'ref' in work:
            self.ref_geoimage()
        if 'cfmask' in work:
            self.fmask_geoimage()
        if 'cloudmask' in work:
            self.cloudmask_geoimage()
        if 'mtci-toa' in work:
            self.mtci_geoimage('toa')
        if 's2rep-toa' in work:
            self.s2rep_geoimage('toa')
        if 'mtci' in work:
            self.mtci_geoimage('surf')
        if 's2rep' in work:
            self.s2rep_geoimage('surf')

        self._time_report('Starting on standard product processing')

        sensor = self.current_sensor()
        # Process standard products
        for prod_type in products.groups()['Standard']:
            err_msg = 'Error creating product {} for {}'.format(
                    prod_type, a_obj.basename)
            with utils.error_handler(err_msg, continuable=True):
                self._time_report('Starting {} processing'.format(prod_type))
                temp_fp = self.temp_product_filename(sensor, prod_type)
                # have to reproduce the whole object because gippy refuses to write metadata when
                # you do image.Process(filename).
                source_image = self._product_images[prod_type]
                output_image = gippy.GeoImage(temp_fp, source_image)
                output_image.SetNoData(0)
                output_image.SetMeta(self.prep_meta())
                if prod_type in ('ref', 'rad'): # atmo-correction metadata
                    output_image.SetMeta('AOD Source', source_image._aod_source)
                    output_image.SetMeta('AOD Value',  source_image._aod_value)
                if prod_type in ('ref-toa', 'rad-toa', 'rad', 'ref'):
                    output_image.SetGain(0.0001)
                if prod_type == 'cfmask':
                    output_image.SetMeta('FMASK_0', 'nodata')
                    output_image.SetMeta('FMASK_1', 'valid')
                    output_image.SetMeta('FMASK_2', 'cloud')
                    output_image.SetMeta('FMASK_3', 'cloud shadow')
                    output_image.SetMeta('FMASK_4', 'snow')
                    output_image.SetMeta('FMASK_5', 'water')
                if prod_type == 'mtci':
                    output_image.SetGain(0.0002)
                    output_image.SetNoData(-32768)
                if prod_type == 's2rep':
                    output_image.SetGain(0.04)
                    output_image.SetOffset(400.0)
                    output_image.SetNoData(-32768)
                for b_num, b_name in enumerate(source_image.BandNames(), 1):
                    output_image.SetBandName(b_name, b_num)
                # process bandwise because gippy had an error doing it all at once
                for i in range(len(source_image)):
                    source_image[i].Process(output_image[i])
                archive_fp = self.archive_temp_path(temp_fp)
                self.AddFile(sensor, prod_type, archive_fp)

            self._time_report('Finished {} processing'.format(prod_type))
            (source_image, output_image) = (None, None) # gc hint due to C++/swig weirdness
        self._time_report('Completed standard product processing')

        # process indices in two groups:  toa and surf
        indices = products.groups()['Index']
        toa_indices  = {k: v for (k, v) in indices.items() if 'toa' in v}
        self.process_indices('toa', sensor, toa_indices)

        surf_indices  = {k: v for (k, v) in indices.items() if 'toa' not in v}
        self.process_indices('surf', sensor, surf_indices)

        if len(products.groups()['ACOLITE']) > 0:
            self.process_acolite(products.groups()['ACOLITE'])

        self._product_images = {} # hint for gc; may be needed due to C++/swig weirdness
        self._time_report('Processing complete for this spatial-temporal unit')

        ## Drop GeoImage cache
        self._drop_geoimage_cache()
