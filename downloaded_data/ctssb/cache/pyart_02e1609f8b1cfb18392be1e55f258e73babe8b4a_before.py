"""
pyart.io.mdv
============

Utilities for reading of MDV files.

.. autosummary::
    :toctree: generated/
    :template: dev_template.rst

    MdvFile

.. autosummary::
    :toctree: generated/

    read_mdv

"""
# Code is adapted from Nitin Bharadwaj's Matlab code

import struct
import gzip
import zlib
import StringIO
import datetime

import numpy as np
from netCDF4 import date2num

from ..config import FileMetadata, get_fillvalue
from ..core.radar import Radar
from .common import make_time_unit_str
from .common import radar_coords_to_cart
from .lazydict import LazyLoadDict


def read_mdv(filename, field_names=None, additional_metadata=None,
             file_field_names=False, exclude_fields=None,
             delay_field_loading=False):
    """
    Read a MDV file.

    Parameters
    ----------
    filename : str
        Name of MDV file to read or file-like object pointing to the
        beginning of such a file.
    field_names : dict, optional
        Dictionary mapping MDV data type names to radar field names. If a
        data type found in the file does not appear in this dictionary or has
        a value of None it will not be placed in the radar.fields dictionary.
        A value of None, the default, will use the mapping defined in the
        Py-ART configuration file.
    additional_metadata : dict of dicts, optional
        Dictionary of dictionaries to retrieve metadata from during this read.
        This metadata is not used during any successive file reads unless
        explicitly included.  A value of None, the default, will not
        introduct any addition metadata and the file specific or default
        metadata as specified by the Py-ART configuration file will be used.
    file_field_names : bool, optional
        True to use the MDV data type names for the field names. If this
        case the field_names parameter is ignored. The field dictionary will
        likely only have a 'data' key, unless the fields are defined in
        `additional_metadata`.
    exclude_fields : list or None, optional
        List of fields to exclude from the radar object. This is applied
        after the `file_field_names` and `field_names` parameters.
    delay_field_loading : bool
        True to delay loading of field data from the file until the 'data'
        key in a particular field dictionary is accessed.  In this case
        the field attribute of the returned Radar object will contain
        LazyLoadDict objects not dict objects. Not all file types support this
        parameter.

    Returns
    -------
    radar : Radar
        Radar object containing data from MDV file.

    Notes
    -----
    Currently this function can only read polar MDV files with fields
    compressed with gzip or zlib.

    """
    # create metadata retrieval object
    filemetadata = FileMetadata('mdv', field_names, additional_metadata,
                                file_field_names, exclude_fields)

    mdvfile = MdvFile(filename)

    # value attributes
    az_deg, range_km, el_deg = mdvfile._calc_geometry()
    naz = len(az_deg)
    nele = len(el_deg)
    scan_type = mdvfile.projection

    if scan_type not in ['ppi', 'rhi']:
        raise NotImplementedError('No support for scan_type %s.' % scan_type)

    # time
    time = filemetadata('time')
    units = make_time_unit_str(mdvfile.times['time_begin'])
    time['units'] = units
    time_start = date2num(mdvfile.times['time_begin'], units)
    time_end = date2num(mdvfile.times['time_end'], units)
    time['data'] = np.linspace(time_start, time_end, naz * nele)

    # range
    _range = filemetadata('range')
    _range['data'] = np.array(range_km * 1000.0, dtype='float32')
    _range['meters_to_center_of_first_gate'] = _range['data'][0]
    _range['meters_between_gates'] = (_range['data'][1] - _range['data'][0])

    # fields
    fields = {}
    for mdv_field in set(mdvfile.fields):
        field_name = filemetadata.get_field_name(mdv_field)
        if field_name is None:
            continue

        # create and store the field dictionary
        field_dic = filemetadata(field_name)
        field_dic['_FillValue'] = get_fillvalue()
        dataExtractor = _MdvVolumeDataExtractor(
            mdvfile, mdvfile.fields.index(mdv_field), get_fillvalue())
        if delay_field_loading:
            field_dic = LazyLoadDict(field_dic)
            field_dic.set_lazy('data', dataExtractor)
        else:
            field_dic['data'] = dataExtractor()
        fields[field_name] = field_dic

    # metadata
    metadata = filemetadata('metadata')
    for meta_key, mdv_key in MDV_METADATA_MAP.iteritems():
        metadata[meta_key] = mdvfile.master_header[mdv_key]

    # latitude
    latitude = filemetadata('latitude')
    latitude['data'] = np.array([mdvfile.radar_info['latitude_deg']],
                                dtype='float64')
    # longitude
    longitude = filemetadata('longitude')
    longitude['data'] = np.array([mdvfile.radar_info['longitude_deg']],
                                 dtype='float64')
    # altitude
    altitude = filemetadata('altitude')
    altitude['data'] = np.array([mdvfile.radar_info['altitude_km'] * 1000.0],
                                dtype='float64')

    # sweep_number, sweep_mode, fixed_angle, sweep_start_ray_index,
    # sweep_end_ray_index
    sweep_number = filemetadata('sweep_number')
    sweep_mode = filemetadata('sweep_mode')
    fixed_angle = filemetadata('fixed_angle')
    sweep_start_ray_index = filemetadata('sweep_start_ray_index')
    sweep_end_ray_index = filemetadata('sweep_end_ray_index')
    len_time = len(time['data'])

    if scan_type == 'ppi':
        nsweeps = nele
        sweep_number['data'] = np.arange(nsweeps, dtype='int32')
        sweep_mode['data'] = np.array(nsweeps * ['azimuth_surveillance'])
        fixed_angle['data'] = np.array(el_deg, dtype='float32')
        sweep_start_ray_index['data'] = np.arange(0, len_time, naz,
                                                  dtype='int32')
        sweep_end_ray_index['data'] = np.arange(naz - 1, len_time, naz,
                                                dtype='int32')

    elif scan_type == 'rhi':
        nsweeps = naz
        sweep_number['data'] = np.arange(nsweeps, dtype='int32')
        sweep_mode['data'] = np.array(nsweeps * ['rhi'])
        fixed_angle['data'] = np.array(az_deg, dtype='float32')
        sweep_start_ray_index['data'] = np.arange(0, len_time, nele,
                                                  dtype='int32')
        sweep_end_ray_index['data'] = np.arange(nele - 1, len_time, nele,
                                                dtype='int32')

    # azimuth, elevation
    azimuth = filemetadata('azimuth')
    elevation = filemetadata('elevation')

    if scan_type == 'ppi':
        azimuth['data'] = np.tile(az_deg, nele)
        elevation['data'] = np.array(el_deg).repeat(naz)

    elif scan_type == 'rhi':
        azimuth['data'] = np.array(az_deg).repeat(nele)
        elevation['data'] = np.tile(el_deg, naz)

    # instrument parameters
    # we will set 4 parameters in the instrument_parameters dict
    # prt, prt_mode, unambiguous_range, and nyquist_velocity

    # TODO prt mode: Need to fix this.. assumes dual if two prts
    if mdvfile.radar_info['prt2_s'] == 0.0:
        prt_mode_str = 'fixed'
    else:
        prt_mode_str = 'dual'

    prt_mode = filemetadata('prt_mode')
    prt = filemetadata('prt')
    unambiguous_range = filemetadata('unambiguous_range')
    nyquist_velocity = filemetadata('nyquist_velocity')
    beam_width_h = filemetadata('radar_beam_width_h')
    beam_width_v = filemetadata('radar_beam_width_v')

    prt_mode['data'] = np.array([prt_mode_str] * nsweeps)
    prt['data'] = np.array([mdvfile.radar_info['prt_s']] * nele * naz,
                           dtype='float32')

    urange_m = mdvfile.radar_info['unambig_range_km'] * 1000.0
    unambiguous_range['data'] = np.array([urange_m] * naz * nele,
                                         dtype='float32')

    uvel_mps = mdvfile.radar_info['unambig_vel_mps']
    nyquist_velocity['data'] = np.array([uvel_mps] * naz * nele,
                                        dtype='float32')
    beam_width_h['data'] = np.array(
        [mdvfile.radar_info['horiz_beam_width_deg']], dtype='float32')
    beam_width_v['data'] = np.array(
        [mdvfile.radar_info['vert_beam_width_deg']], dtype='float32')

    instrument_parameters = {'prt_mode': prt_mode, 'prt': prt,
                             'unambiguous_range': unambiguous_range,
                             'nyquist_velocity': nyquist_velocity,
                             'radar_beam_width_h': beam_width_h,
                             'radar_beam_width_v': beam_width_v}

    return Radar(
        time, _range, fields, metadata, scan_type,
        latitude, longitude, altitude,
        sweep_number, sweep_mode, fixed_angle, sweep_start_ray_index,
        sweep_end_ray_index,
        azimuth, elevation,
        instrument_parameters=instrument_parameters)


# mapping from MDV name space to CF-Radial name space
MDV_METADATA_MAP = {'instrument_name': 'data_set_source',
                    'source': 'data_set_info'}

# Information about the MDV file structure
MDV_CHUNK_INFO_LEN = 480
MDV_INFO_LEN = 512
MDV_LONG_FIELD_LEN = 64
MDV_MAX_PROJ_PARAMS = 8
MDV_MAX_VLEVELS = 122
MDV_NAME_LEN = 128
MDV_SHORT_FIELD_LEN = 16
MDV_TRANSFORM_LEN = 16
MDV_UNITS_LEN = 16
MDV_N_COORD_LABELS = 3
MDV_COORD_UNITS_LEN = 32

# (x,y) in degrees. Simple latitude-longitude grid.
# Also known as the Simple Cylindrical or Platte Carree projection.
PROJ_LATLON = 0
# (x,y) in km. Lambert Conformal Conic projection.
PROJ_LAMBERT_CONF = 3
# (x,y) in km. Polar Stereographic projection.
PROJ_POLAR_STEREO = 5
# Cartesian, (x,y) in km. This is a simple line-of-sight
# projection used for single radar sites. The formal name is
# Oblique Lambert Azimuthal projection.
PROJ_FLAT = 8
# radar data in native Plan Position Indicator (PPI) coordinates of
# range, azimuth angle and elevation angle. x is radial range (km),
# y is azimuth angle (deg), z is elev angle (deg).
PROJ_POLAR_RADAR = 9
# (x,y) in km. Oblique Stereographic projection.
PROJ_OBLIQUE_STEREO = 12
# radar data in native Range Height Indicator (RHI) coordinates.
# x is radial range (km), y is elev angle (deg), z is az angle (deg).
PROJ_RHI_RADAR = 13
#  ***************** COMPRESSION *******************
COMPRESSION_NONE = 0  # no compression
COMPRESSION_ZLIB = 3  # Lempel-Ziv
COMPRESSION_BZIP = 4  # bzip2
COMPRESSION_GZIP = 5  # Lempel-Ziv in gzip format

#  ***************** COMPRESSION CODE *******************
TA_NOT_COMPRESSED = 791621423
GZIP_COMPRESSED = 4160223223

#  ***************** TRANSFORM *******************
DATA_TRANSFORM_NONE = 0  # None
DATA_TRANSFORM_LOG = 1  # Natural log

#  ***************** BIT ENCODING *******************
ENCODING_INT8 = 1  # unsigned 8 bit integer
ENCODING_INT16 = 2  # unsigned 16 bit integer
ENCODING_FLOAT32 = 5  # 32 bit IEEE floating point

#  ***************** CHUNK HEADER and DATA *******************
CHUNK_DSRADAR_PARAMS = 3
CHUNK_DSRADAR_ELEVATIONS = 10
CHUNK_DSRADAR_CALIB = 7
DS_LABEL_LEN = 40
NCHAR_DS_RADAR_PARAMS = 2 * DS_LABEL_LEN
DS_RADAR_CALIB_NAME_LEN = 16
DS_RADAR_CALIB_MISSING = -9999.0


class MdvFile:
    """
    A file object for MDV data.

    A `MdvFile` object stores metadata and data from a MDV file.  Metadata is
    stored in dictionaries as attributes of the object, field data is
    stored as NumPy ndarrays as attributes with the field name. By default
    only metadata is read initially and field data must be read using the
    `read_a_field` or `read_all_fields` methods.  This behavior can be changed
    by setting the `read_fields` parameter to True.

    Parameters
    ----------
    filename : str or file-like
        Name of MDV file to read or file-like object pointing to the
        beginning of such a file.
    debug : bool
        True to print out debugging information, False to supress
    read_fields : bool
        True to read all field during initalization, False (default) only
        reads metadata.

    Notes
    -----
    This Object is not stable enough to be considered a general MDV lib, nor is
    that our intention, but with careful use it shall provide full read/write
    capacity.

    """
    # ftm for use in the struct lib
    # mapper are used to convert vector to dics, they are of the following
    # type: (var_name,inicial pos, final pos)
    master_header_fmt = '>28i 8i i 5i 6f 3f 12f 512s 128s 128s i'
    master_header_mapper = [
        ("record_len1", 0, 1),
        ("struct_id", 1, 2),
        ("revision_number", 2, 3),
        ("time_gen", 3, 4),
        ("user_time", 4, 5),
        ("time_begin", 5, 6),
        ("time_end", 6, 7),
        ("time_centroid", 7, 8),
        ("time_expire", 8, 9),
        ("num_data_times", 9, 10),
        ("index_number", 10, 11),
        ("data_dimension", 11, 12),
        ("data_collection_type", 12, 13),
        ("user_data", 13, 14),
        ("native_vlevel_type", 14, 15),
        ("vlevel_type", 15, 16),
        ("vlevel_included", 16, 17),
        ("grid_orientation", 17, 18),
        ("data_ordering", 18, 19),
        ("nfields", 19, 20),
        ("max_nx", 20, 21),
        ("max_ny", 21, 22),
        ("max_nz", 22, 23),
        ("nchunks", 23, 24),
        ("field_hdr_offset", 24, 25),
        ("vlevel_hdr_offset", 25, 26),
        ("chunk_hdr_offset", 26, 27),
        ("field_grids_differ", 27, 28),
        ("user_data_si328", 28, 36),
        ("time_written", 36, 37),
        ("unused_si325", 37, 42),
        ("user_data_fl326", 42, 48),
        ("sensor_lon", 48, 49),
        ("sensor_lat", 49, 50),
        ("sensor_alt", 50, 51),
        ("unused_fl3212", 51, 63),
        ("data_set_info", 63, 64),
        ("data_set_name", 64, 65),
        ("data_set_source", 65, 66),
        ("record_len2", 66, 67)
    ]

    field_header_fmt = '>17i 10i 9i 4i f f 8f 12f 4f 5f 64s 16s 16s 16s 16s i'
    field_header_mapper = [
        ("record_len1", 0, 1),
        ("struct_id", 1, 2),
        ("field_code", 2, 3),
        ("user_time1", 3, 4),
        ("forecast_delta", 4, 5),
        ("user_time2", 5, 6),
        ("user_time3", 6, 7),
        ("forecast_time", 7, 8),
        ("user_time4", 8, 9),
        ("nx", 9, 10),
        ("ny", 10, 11),
        ("nz", 11, 12),
        ("proj_type", 12, 13),
        ("encoding_type", 13, 14),
        ("data_element_nbytes", 14, 15),
        ("field_data_offset", 15, 16),
        ("volume_size", 16, 17),
        ("user_data_si32", 17, 27),
        ("compression_type", 27, 28),
        ("transform_type", 28, 29),
        ("scaling_type", 29, 30),
        ("native_vlevel_type", 30, 31),
        ("vlevel_type", 31, 32),
        ("dz_constant", 32, 33),
        ("data_dimension", 33, 34),
        ("zoom_clipped", 34, 35),
        ("zoom_no_overlap", 35, 36),
        ("unused_si32", 36, 40),
        ("proj_origin_lat", 40, 41),
        ("proj_origin_lon", 41, 42),
        ("proj_param", 42, 50),
        ("vert_reference", 50, 51),
        ("grid_dx", 51, 52),
        ("grid_dy", 52, 53),
        ("grid_dz", 53, 54),
        ("grid_minx", 54, 55),
        ("grid_miny", 55, 56),
        ("grid_minz", 56, 57),
        ("scale", 57, 58),
        ("bias", 58, 59),
        ("bad_data_value", 59, 60),
        ("missing_data_value", 60, 61),
        ("proj_rotation", 61, 62),
        ("user_data_fl32", 62, 66),
        ("min_value", 66, 67),
        ("max_value", 67, 68),
        ("min_value_orig_vol", 68, 69),
        ("max_value_orig_vol", 69, 70),
        ("unused_fl32", 70, 71),
        ("field_name_long", 71, 72),
        ("field_name", 72, 73),
        ("units", 73, 74),
        ("transform", 74, 75),
        ("unused_char", 75, 76),
        ("record_len2", 76, 77)
    ]

    vlevel_header_fmt = '>i i 122i 4i 122f 5f i'
    vlevel_header_mapper = [
        ("record_len1", 0, 1),
        ("struct_id", 1, 2),
        ("type", 2, 124),
        ("unused_si32", 124, 128),
        ("level", 128, 250),
        ("unused_fl32", 250, 255),
        ("record_len2", 255, 256)
    ]

    chunk_header_fmt = '>5i 2i 480s i'
    chunk_header_mapper = [
        ("record_len1", 0, 1),
        ("struct_id", 1, 2),
        ("chunk_id", 2, 3),
        ("chunk_data_offset", 3, 4),
        ("size", 4, 5),
        ("unused_si32", 5, 7),
        ("info", 7, 8),
        ("record_len2", 8, 9)
    ]

    compression_info_fmt = '>I I I I 2I'
    compression_info_mapper = [
        ("magic_cookie", 0, 1),
        ("nbytes_uncompressed", 1, 2),
        ("nbytes_compressed", 2, 3),
        ("nbytes_coded", 3, 4),
        ("spare", 4, 6)
    ]

    radar_info_fmt = '>12i 2i 22f 4f 40s 40s'
    radar_info_mapper = [
        ("radar_id", 0, 1),
        ("radar_type", 1, 2),
        ("nfields", 2, 3),
        ("ngates", 3, 4),
        ("samples_per_beam", 4, 5),
        ("scan_type", 5, 6),
        ("scan_mode", 6, 7),
        ("nfields_current", 7, 8),
        ("field_flag", 8, 9),
        ("polarization", 9, 10),
        ("follow_mode", 10, 11),
        ("prf_mode", 11, 12),
        ("spare_ints", 12, 14),
        ("radar_constant", 14, 15),
        ("altitude_km", 15, 16),
        ("latitude_deg", 16, 17),
        ("longitude_deg", 17, 18),
        ("gate_spacing_km", 18, 19),
        ("start_range_km", 19, 20),
        ("horiz_beam_width_deg", 20, 21),
        ("vert_beam_width_deg", 21, 22),
        ("pulse_width_us", 22, 23),
        ("prf_hz", 23, 24),
        ("wavelength_cm", 24, 25),
        ("xmit_peak_pwr_watts", 25, 26),
        ("receiver_mds_dbm", 26, 27),
        ("receiver_gain_db", 27, 28),
        ("antenna_gain_db", 28, 29),
        ("system_gain_db", 29, 30),
        ("unambig_vel_mps", 30, 31),
        ("unambig_range_km", 31, 32),
        ("measXmitPowerDbmH_dbm", 32, 33),
        ("measXmitPowerDbmV_dbm", 33, 34),
        ("prt_s", 34, 35),
        ("prt2_s", 35, 36),
        ("spare_floats", 36, 40),
        ("radar_name", 40, 41),
        ("scan_type_name", 41, 42)
    ]

    calib_fmt = '>16s 6i 51f 14f'
    calib_mapper = [
        ("radar_name", 0, 1),
        ("year", 1, 2),
        ("month", 2, 3),
        ("day", 3, 4),
        ("hour", 4, 5),
        ("minute", 5, 6),
        ("second", 6, 7),
        ("wavelength_cm", 7, 8),
        ("beamwidth_h_deg", 8, 9),
        ("beamwidth_v_deg", 9, 10),
        ("antenna_gain_h_db", 10, 11),
        ("antenna_gain_v_db", 11, 12),
        ("pulse_width_us", 12, 13),
        ("xmit_power_h_dbm", 13, 14),
        ("xmit_power_v_dbm", 14, 15),
        ("twoway_waveguide_loss_h_db", 15, 16),
        ("twoway_waveguide_loss_v_db", 16, 17),
        ("twoway_radome_loss_h_db", 17, 18),
        ("twoway_radome_loss_v_db", 18, 19),
        ("filter_loss_db", 19, 20),
        ("radar_constant_h_db", 20, 21),
        ("radar_constant_v_db", 21, 22),
        ("noise_h_co_dbm", 22, 23),
        ("noise_h_cx_dbm", 23, 24),
        ("noise_v_co_dbm", 24, 25),
        ("noise_v_cx_dbm", 25, 26),
        ("rx_gain_h_co_dbm", 26, 27),
        ("rx_gain_h_cx_dbm", 27, 28),
        ("rx_gain_v_co_dbm", 28, 29),
        ("rx_gain_v_cx_dbm", 29, 30),
        ("zh1km_co_dbz", 30, 31),
        ("zh1km_cx_dbz", 31, 32),
        ("zv1km_co_dbz", 32, 33),
        ("zv1km_cx_dbz", 33, 34),
        ("sun_h_co_dbm", 34, 35),
        ("sun_h_cx_dbm", 35, 36),
        ("sun_v_co_dbm", 36, 37),
        ("sun_v_cx_dbm", 37, 38),
        ("noise_source_h_dbm", 38, 39),
        ("noise_source_v_dbm", 39, 40),
        ("power_meas_loss_h_db", 40, 41),
        ("power_meas_loss_v_db", 41, 42),
        ("coupler_fwd_loss_h_db", 42, 43),
        ("coupler_fwd_loss_v_db", 43, 44),
        ("zdr_bias_db", 44, 45),
        ("ldr_h_bias_db", 45, 46),
        ("ldr_v_bias_db", 46, 47),
        ("system_phidp_deg", 47, 48),
        ("test_pulse_h_dbm", 48, 49),
        ("test_pulse_v_dbm", 49, 50),
        ("rx_slope_h_co_db", 50, 51),
        ("rx_slope_h_cx_db", 51, 52),
        ("rx_slope_v_co_db", 52, 53),
        ("rx_slope_v_cx_db", 53, 54),
        ("I0_h_co_dbm", 54, 55),
        ("I0_h_cx_dbm", 55, 56),
        ("I0_v_co_dbm", 56, 57),
        ("I0_v_cx_dbm", 57, 58),
        ("spare", 58, 72)
    ]

    def __init__(self, filename, debug=False, read_fields=False):
        """
        initalize MdvFile from filename (str).
        If filename=None create empty object
        """
        if debug:
            print "Opening file for reading: ", filename
        if filename is None:
            # will creat empqty struct, for filling and writing after
            self.fileptr = None
        elif hasattr(filename, 'read'):
            self.fileptr = filename
        else:
            self.fileptr = open(filename, 'rb')

        if debug:
            print "Getting master header"
        self.master_header = self._get_master_header()

        if debug:
            print "getting field headers"
        nfields = self.master_header['nfields']
        self.field_headers = self._get_field_headers(nfields)

        if debug:
            print "getting vlevel headers"
        self.vlevel_headers = self._get_vlevel_headers(nfields)

        if debug:
            print "getting chunk headers"
        nchunks = self.master_header['nchunks']
        self.chunk_headers = self._get_chunk_headers(nchunks)

        if debug:
            print "Getting Chunk Data"
        # will store raw chunk data, use for unkown chunk information
        self.chunk_data = [None] * self.master_header['nchunks']
        self.radar_info, self.elevations, self.calib_info = self._get_chunks(
            debug)

        if self.master_header['nfields'] > 0:
            if self.field_headers[0]['proj_type'] == PROJ_LATLON:
                self.projection = 'latlon'
            elif self.field_headers[0]['proj_type'] == PROJ_LAMBERT_CONF:
                self.projection = 'lambert_conform'
            elif self.field_headers[0]['proj_type'] == PROJ_POLAR_STEREO:
                self.projection = 'polar_stereographic'
            elif self.field_headers[0]['proj_type'] == PROJ_FLAT:
                self.projection = 'flat'
            elif self.field_headers[0]['proj_type'] == PROJ_POLAR_RADAR:
                self.projection = 'ppi'
            elif self.field_headers[0]['proj_type'] == PROJ_OBLIQUE_STEREO:
                self.projection = 'oblique_stereographic'
            elif self.field_headers[0]['proj_type'] == PROJ_RHI_RADAR:
                self.projection = 'rhi'

#        if debug:
#            print "Calculating Radar coordinates"
#        az_deg, range_km, el_deg = self._calc_geometry()
#        self.az_deg = np.array(az_deg, dtype='float32')
#        self.range_km = np.array(range_km, dtype='float32')
#        self.el_deg = np.array(el_deg, dtype='float32')

        if debug:
            print "Making usable time objects"
        self.times = self._make_time_dict()

#        if debug:
#            print "Calculating cartesian coordinates"
#        self.carts = self._make_carts_dict()

        if debug:
            print "indexing fields"
        self.fields = self._make_fields_list()

        self.fields_data = [None] * self.master_header["nfields"]

        if read_fields:
            if debug:
                print "Reading all fields"
            self.read_all_fields()
        return

    ##################
    # public methods #
    ##################
    def write(self, filename, debug=False):
        """ Write a MdvFile to filename (stg) """
        if debug:
            print "Opening file for writing:", filename
        if hasattr(filename, 'write'):
            self.fileptr = filename
        else:
            self.fileptr = open(filename, 'wb')
        file_start = self.fileptr.tell()

        # first write fields so one can calculate the offsets
        # put zero in headers

        headers_size = (1024 + (416 + 1024) * self.master_header["nfields"] +
                        512 * self.master_header["nchunks"])
        self.fileptr.write("\x00" * headers_size)

        if debug:
            print "Writing Fields Data"
        for ifield in range(self.master_header["nfields"]):
            self.write_a_field(ifield)

        # write chunks
        if debug:
            print "Writing Chunk Data"
        self._write_chunks(debug)
        # calculate offsets
        self._calc_file_offsets()
        self.fileptr.seek(file_start)
        # write headers
        if debug:
            print "Writing master header"
        self._write_master_header()

        if debug:
            print "Writing field headers"
        self._write_field_headers(self.master_header["nfields"])

        if debug:
            print "Writing vlevel headers"
        self._write_vlevel_headers(self.master_header["nfields"])

        if debug:
            print "Writing chunk headers"
        self._write_chunk_headers(self.master_header["nchunks"])
        # close file
        # XXX should I really do that? what if it's a file-like struct?
        if debug:
            print "Closing file"
        self.fileptr.close()

    def read_a_field(self, fnum, debug=False):
        """
        Read a field from the MDV file.

        Parameters
        ----------
        fnum : int
            Field number to read.
        debug : bool
            True to print debugging information, False to supress.

        Returns
        -------
        field_data : array
            Field data.  This data is also stored as a object attribute under
            the field name.

        See Also
        --------
        read_all_fields : Read all fields in the MDV file.

        """

        field_header = self.field_headers[fnum]
        # if the field has already been read, return it
        if self.fields_data[fnum] is not None:
            if debug:
                print "Getting data from the object."
            return self.fields_data[fnum]

        # field has not yet been read, populate the object and return
        if debug:
            print "No data found in object, populating"

        nz = field_header['nz']
        ny = field_header['ny']
        nx = field_header['nx']

        # read the header
        field_data = np.zeros([nz, ny, nx], dtype='float32')
        self.fileptr.seek(field_header['field_data_offset'])
        self._get_levels_info(nz)  # dict not used, but need to seek.

        for sw in xrange(nz):
            if debug:
                print "doing levels ", sw

            # get the compressed level data
            compr_info = self._get_compression_info()
            compr_data = self.fileptr.read(compr_info['nbytes_coded'])
            encoding_type = field_header['encoding_type']
            if encoding_type == ENCODING_INT8:
                fmt = '>%iB' % (nx * ny)
                np_form = '>B'
            elif encoding_type == ENCODING_INT16:
                fmt = '>%iH' % (nx * ny)
                np_form = '>H'
            elif encoding_type == ENCODING_FLOAT32:
                fmt = '>%if' % (nx * ny)
                np_form = '>f'
            else:
                raise ValueError('unknown encoding: ', encoding_type)

            # decompress the level data
            if compr_info['magic_cookie'] == 0xf7f7f7f7:
                cd_fobj = StringIO.StringIO(compr_data)
                gzip_file_handle = gzip.GzipFile(fileobj=cd_fobj)
                decompr_data = gzip_file_handle.read(struct.calcsize(fmt))
                gzip_file_handle.close()
            elif compr_info['magic_cookie'] == 0xf5f5f5f5:
                decompr_data = zlib.decompress(compr_data)
            else:
                raise NotImplementedError('unsupported compression mode')
                # With sample data it should be possible to write
                # decompressor for other modes, the compression magic
                # cookies for these modes are:
                # 0x2f2f2f2f : TA_NOT_COMPRESSED
                # 0xf8f8f8f8 : GZIP_NOT_COMPRSSED
                # 0xf3f3f3f3 : BZIP_COMPRESSED
                # 0xf4f4f4f4 : BZIP_NOT_COMPRESSED
                # 0xf6f6f6f6 : ZLIB_NOT_COMPRESSED

            # read the decompressed data, reshape and mask
            sw_data = np.fromstring(decompr_data, np_form).astype('float32')
            sw_data.shape = (ny, nx)
            mask = sw_data == field_header['bad_data_value']
            np.putmask(sw_data, mask, [np.NaN])

            # scale and offset the data, store in field_data
            scale = field_header['scale']
            bias = field_header['bias']
            field_data[sw, :, :] = sw_data * scale + bias

        # store data as object attribute and return
        self.fields_data[fnum] = field_data
        return field_data

    def write_a_field(self, fnum, debug=False):
        """ write field number 'fnum' to mdv file """
        # the file pointer must be set at the correct location prior to call
        field_header = self.field_headers[fnum]
        if field_header['compression_type'] != 3:
            import warnings
            warnings.warn(
                "compression_type not implemented, converting to zlib")
            field_header['compression_type'] = 3

        field_data = self.fields_data[fnum]
        nz = field_header['nz']
        # save file posicion
        field_start = self.fileptr.tell()
        # write zeros to vlevel_offsets and vlevel_nbytes
        self.fileptr.write("\x00" * 4 * 2 * nz)
        field_size = 0
        vlevel_offsets = [0] * nz
        vlevel_nbytes = [0] * nz
        for sw in xrange(nz):
            vlevel_offsets[sw] = field_size
            scale = field_header['scale']
            bias = field_header['bias']
            sw_data = np.round((field_data[sw, :, :] - bias) / scale)
            if hasattr(sw_data, 'mask'):
                sw_data = np.where(
                    sw_data.mask, field_header['bad_data_value'], sw_data)

            encoding_type = field_header['encoding_type']
            if encoding_type == ENCODING_INT8:
                np_form = '>B'
            elif encoding_type == ENCODING_INT16:
                np_form = '>H'
            elif encoding_type == ENCODING_FLOAT32:
                np_form = '>f'
            else:
                raise ValueError('unknown encoding: ', encoding_type)
            uncompr_data = np.array(sw_data, dtype=np_form).tostring()
            compr_data = zlib.compress(uncompr_data)
            if len(compr_data) > len(uncompr_data):
                magic = 0xf6f6f6f6
                compr_data = uncompr_data
            else:
                magic = 0xf5f5f5f5
            compr_info = {
                'magic_cookie': magic,
                'nbytes_uncompressed': len(uncompr_data),
                'nbytes_compressed': len(compr_data) + 24,
                'nbytes_coded': len(compr_data),
                'spare': [0, 0],
            }

            self._write_compression_info(compr_info)
            self.fileptr.write(compr_data)
            field_size = field_size + len(compr_data) + 24
            vlevel_nbytes[sw] = len(compr_data) + 24
        # go back and rewrite vlevel_offsets and vlevel_nbytes
        field_end = self.fileptr.tell()
        self.fileptr.seek(field_start)
        fmt = '>%iI %iI' % (nz, nz)
        string = struct.pack(fmt, *(vlevel_offsets + vlevel_nbytes))
        self.fileptr.write(string)
        self.fileptr.seek(field_end)
        field_header["volume_size"] = field_size + 2 * 4 * nz

    def read_all_fields(self):
        """ Read all fields, storing data to field name attributes. """
        for i in xrange(self.master_header['nfields']):
            self.read_a_field(i)

    def close(self):
        """ Close the MDV file. """
        self.fileptr.close()

    ###################
    # private methods #
    ###################

    # get_ methods for reading headers

    def _get_master_header(self):
        """ Read the MDV master header, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.master_header_mapper[-1][2]
            l[0] = 1016
            l[1] = 14142
            l[2] = 1
            l[9] = 1
            l[16] = 1
            l[17] = 1
            l[63] = ""
            l[64] = ""
            l[65] = ""
            l[66] = 1016
        else:
            l = struct.unpack(
                self.master_header_fmt,
                self.fileptr.read(struct.calcsize(self.master_header_fmt)))
        d = {}
        for item in self.master_header_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_master_header(self):
        """ Write the MDV master header. """
        # the file pointer must be set at the correct location prior to call
        d = self.master_header
        l = [0] * self.master_header_mapper[-1][2]
        for item in self.master_header_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.master_header_fmt, *l)
        self.fileptr.write(string)

    def _get_field_headers(self, nfields):
        """ Read nfields field headers, return a list of dicts. """
        # the file pointer must be set at the correct location prior to call
        return [self._get_field_header() for i in range(nfields)]

    def _write_field_headers(self, nfields):
        """ Write nfields field headers. """
        # the file pointer must be set at the correct location prior to call
        for i in range(nfields):
            self._write_field_header(self.field_headers[i])

    def _get_field_header(self):
        """ Read a single field header, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.field_header_mapper[-1][2]
            l[0] = 408
            l[1] = 14143
            l[57] = 1  # scale
            l[71] = ""
            l[72] = ""
            l[73] = ""
            l[74] = ""
            l[75] = ""
            l[76] = 408
        else:
            l = struct.unpack(
                self.field_header_fmt,
                self.fileptr.read(struct.calcsize(self.field_header_fmt)))
        d = {}
        for item in self.field_header_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_field_header(self, d):
        """ Write the a single field header. """
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.field_header_mapper[-1][2]
        for item in self.field_header_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.field_header_fmt, *l)
        self.fileptr.write(string)

    def _get_vlevel_headers(self, nfields):
        """ Read nfields vlevel headers, return a list of dicts. """
        # the file pointer must be set at the correct location prior to call
        return [self._get_vlevel_header() for i in range(nfields)]

    def _write_vlevel_headers(self, nfields):
        """ Write nfields vlevel headers"""
        # the file pointer must be set at the correct location prior to call
        for i in range(nfields):
            self._write_vlevel_header(self.vlevel_headers[i])

    def _get_vlevel_header(self):
        """ Read a single vlevel header, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.vlevel_header_mapper[-1][2]
            l[0] = 1016
            l[1] = 14144
            l[255] = 1016
        else:
            l = struct.unpack(
                self.vlevel_header_fmt,
                self.fileptr.read(struct.calcsize(self.vlevel_header_fmt)))
        d = {}
        for item in self.vlevel_header_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_vlevel_header(self, d):
        """  Write the a single vfield header. """
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.vlevel_header_mapper[-1][2]
        for item in self.vlevel_header_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.vlevel_header_fmt, *l)
        self.fileptr.write(string)

    def _get_chunk_headers(self, nchunks):
        """ Get nchunk chunk headers, return a list of dicts. """
        # the file pointer must be set at the correct location prior to call
        return [self._get_chunk_header() for i in range(nchunks)]

    def _write_chunk_headers(self, nchunks):
        """ Write nchunk chunk headers. """
        # the file pointer must be set at the correct location prior to call
        for i in range(nchunks):
            self._write_chunk_header(self.chunk_headers[i])

    def _get_chunk_header(self):
        """ Get a single chunk header, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.chunk_header_mapper[-1][2]
            l[0] = 504
            l[1] = 14145
            l[7] = ""
            l[8] = 504
        else:
            l = struct.unpack(
                self.chunk_header_fmt,
                self.fileptr.read(struct.calcsize(self.chunk_header_fmt)))
        d = {}
        for item in self.chunk_header_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_chunk_header(self, d):
        """  Write the a single chunk header. """
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.chunk_header_mapper[-1][2]
        for item in self.chunk_header_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.chunk_header_fmt, *l)
        self.fileptr.write(string)

    def _get_chunks(self, debug=False):
        """ Get data in chunks, return radar_info, elevations, calib_info. """
        # the file pointer must be set at the correct location prior to call
        radar_info, elevations, calib_info = None, [], None
        for cnum, curr_chunk_header in enumerate(self.chunk_headers):

            chunk_id = curr_chunk_header['chunk_id']
            self.fileptr.seek(curr_chunk_header['chunk_data_offset'])

            if chunk_id == CHUNK_DSRADAR_PARAMS:
                if debug:
                    print 'Getting radar info'
                radar_info = self._get_radar_info()

            elif chunk_id == CHUNK_DSRADAR_CALIB:
                if debug:
                    print 'getting elevations'
                elevations = self._get_elevs(curr_chunk_header['size'])

            elif chunk_id == CHUNK_DSRADAR_ELEVATIONS:
                if debug:
                    print 'getting cal'
                calib_info = self._get_calib()

            else:
                if debug:
                    print 'getting unknown chunk %i' % chunk_id
                self.chunk_data[cnum] = self._get_unknown_chunk(cnum)

        return radar_info, elevations, calib_info

    def _write_chunks(self, debug=False):
        """ write chunks data """
        # the file pointer must be set at the correct location prior to call
        for cnum, curr_chunk_header in enumerate(self.chunk_headers):
            chunk_id = curr_chunk_header['chunk_id']

            if chunk_id == CHUNK_DSRADAR_PARAMS:
                if debug:
                    print 'writing radar info'
                self._write_radar_info(self.radar_info)

            elif chunk_id == CHUNK_DSRADAR_ELEVATIONS:
                if debug:
                    print 'writing elevations'
                self._write_elevs(self.elevations)

            elif chunk_id == CHUNK_DSRADAR_CALIB:
                if debug:
                    print 'writing cal'
                self._write_calib(self.calib_info)

            else:
                if debug:
                    print 'writing unknown chunk %i' % chunk_id
                self._write_unknown_chunk(self, self.chunk_data[cnum])

    def _get_radar_info(self):
        """ Get the radar information, return dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.radar_info_mapper[-1][2]
            l[40] = ""
            l[41] = ""
        else:
            l = struct.unpack(
                self.radar_info_fmt,
                self.fileptr.read(struct.calcsize(self.radar_info_fmt)))
        d = {}
        for item in self.radar_info_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_radar_info(self, d):
        """  Write radar information. """
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.radar_info_mapper[-1][2]
        for item in self.radar_info_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.radar_info_fmt, *l)
        self.fileptr.write(string)

    def _get_elevs(self, nbytes):
        """ Return an array of elevation read from current file position. """
        # the file pointer must be set at the correct location prior to call
        SIZE_FLOAT = 4.0
        nelevations = np.floor(nbytes / SIZE_FLOAT)
        fmt = '>%df' % (nelevations)
        l = struct.unpack(fmt, self.fileptr.read(struct.calcsize(fmt)))
        return np.array(l)

    def _write_elevs(self, l):
        """ Write an array of elevation. """
        # the file pointer must be set at the correct location prior to call
        fmt = '>%df' % (len(l))
        string = struct.pack(fmt, *l)
        self.fileptr.write(string)

    def _get_calib(self):
        """ Get the calibration information, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.calib_mapper[-1][2]
            l[0] = ""
        else:
            l = struct.unpack(
                self.calib_fmt,
                self.fileptr.read(struct.calcsize(self.calib_fmt)))
        d = {}
        for item in self.calib_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_calib(self, d):
        """  Write calibration information. """
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.calib_mapper[-1][2]
        for item in self.calib_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.calib_fmt, *l)
        self.fileptr.write(string)

    def _get_compression_info(self):
        """ Get compression infomation, return a dict. """
        # the file pointer must be set at the correct location prior to call
        if self.fileptr is None:
            l = [0] * self.compression_info_mapper[-1][2]
        else:
            l = struct.unpack(
                self.compression_info_fmt,
                self.fileptr.read(struct.calcsize(self.compression_info_fmt)))
        d = {}
        for item in self.compression_info_mapper:
            if item[2] == item[1] + 1:
                d[item[0]] = l[item[1]]
            else:
                d[item[0]] = l[item[1]:item[2]]
            if isinstance(d[item[0]], basestring):
                d[item[0]] = d[item[0]].split('\x00', 1)[0]
        return d

    def _write_compression_info(self, d):
        """ Write compression infomation"""
        # the file pointer must be set at the correct location prior to call
        l = [0] * self.compression_info_mapper[-1][2]
        for item in self.compression_info_mapper:
            if item[2] == item[1] + 1:
                l[item[1]] = d[item[0]]
            else:
                l[item[1]:item[2]] = d[item[0]]
        string = struct.pack(self.compression_info_fmt, *l)
        self.fileptr.write(string)

    def _get_unknown_chunk(self, cnum):
        """ Get raw data from chunk """
        # the file pointer must be set at the correct location prior to call
        size = self.chunk_headers[cnum]['size']
        return self.fileptr.read(size)

    def _write_unknown_chunk(self, data):
        """ Write raw data from chunk """
        # the file pointer must be set at the correct location prior to call
        self.fileptr.write(data)

    def _get_levels_info(self, nlevels):
        """ Get nlevel information, return a dict. """
        # the file pointer must be set at the correct location prior to call
        fmt = '>%iI %iI' % (nlevels, nlevels)
        if self.fileptr:
            l = struct.unpack(fmt, self.fileptr.read(struct.calcsize(fmt)))
        else:
            l = [0] * 2 * nlevels
        d = {}
        d['vlevel_offsets'] = l[:nlevels]
        d['vlevel_nbytes'] = l[nlevels: 2 * nlevels]
        return d

    def _write_levels_info(self, nlevels, d):
        """ write levels information, return a dict. """
        # the file pointer must be set at the correct location prior to call
        fmt = '%iI %iI' % (nlevels, nlevels)
        l = d['vlevel_offsets'] + d['vlevel_nbytes']
        string = struct.pack(fmt, *l)
        self.fileptr.write(string)

    def _calc_file_offsets(self):
        self.master_header["field_hdr_offset"] = 1024
        self.master_header["vlevel_hdr_offset"] = (
            1024 + 416 * self.master_header["nfields"])
        self.master_header["chunk_hdr_offset"] = (
            1024 + (416 + 1024) * self.master_header["nfields"])

        file_pos = (self.master_header["chunk_hdr_offset"] +
                    512 * self.master_header["nchunks"])
        for i in range(self.master_header["nfields"]):
            self.field_headers[i]["field_data_offset"] = file_pos
            file_pos = file_pos + self.field_headers[i]["volume_size"]

        for i in range(self.master_header["nchunks"]):
            self.chunk_headers[i]["chunk_data_offset"] = file_pos
            file_pos = file_pos + self.chunk_headers[i]["size"]

    def _make_time_dict(self):
        """ Return a time dictionary. """
        t_base = datetime.datetime(1970, 1, 1, 00, 00)
        tb = datetime.timedelta(seconds=self.master_header['time_begin'])
        te = datetime.timedelta(seconds=self.master_header['time_end'])
        tc = datetime.timedelta(seconds=self.master_header['time_centroid'])
        return {'time_begin': t_base + tb, 'time_end': t_base + te,
                'time_centroid': t_base + tc}

    def _time_dict_into_header(self):
        """ Complete time information in master_header from the time dict """
        t_base = datetime.datetime(1970, 1, 1, 00, 00)
        self.master_header['time_begin'] = (
            self.times['time_begin'] - t_base).total_seconds()
        self.master_header['time_end'] = (
            self.times['time_end'] - t_base).total_seconds()
        self.master_header['time_centroid'] = (
            self.times['time_centroid'] - t_base).total_seconds()

    # misc. methods
    # XXX move some where else, there are not general mdv operations
    def _calc_geometry(self):
        """ Calculate geometry, return az_deg, range_km, el_deg. """
        nsweeps = self.master_header['max_nz']
        nrays = self.master_header['max_ny']
        ngates = self.master_header['max_nx']
        grid_minx = self.field_headers[0]['grid_minx']
        grid_miny = self.field_headers[0]['grid_miny']
        grid_dx = self.field_headers[0]['grid_dx']
        grid_dy = self.field_headers[0]['grid_dy']

        range_km = grid_minx + np.arange(ngates) * grid_dx

        if self.field_headers[0]['proj_type'] == PROJ_RHI_RADAR:
            el_deg = grid_miny + np.arange(nrays) * grid_dy
            az_deg = self.vlevel_headers[0]['level'][0:nsweeps]

        if self.field_headers[0]['proj_type'] == PROJ_POLAR_RADAR:
            az_deg = grid_miny + np.arange(nrays) * grid_dy
            el_deg = self.vlevel_headers[0]['level'][0:nsweeps]

        return az_deg, range_km, el_deg

    def _make_carts_dict(self):
        """ Return a carts dictionary, distances in meters. """
        az_deg, range_km, el_deg = self._calc_geometry()
        # simple calculation involving 4/3 earth radius
        nsweeps = self.master_header['max_nz']
        nrays = self.master_header['max_ny']
        ngates = self.master_header['max_nx']
        xx = np.empty([nsweeps, nrays, ngates], dtype=np.float32)
        yy = np.empty([nsweeps, nrays, ngates], dtype=np.float32)
        zz = np.empty([nsweeps, nrays, ngates], dtype=np.float32)

        if self.projection == 'rhi':
            rg, ele = np.meshgrid(range_km, el_deg)
            rg = np.array(rg, dtype=np.float64)
            ele = np.array(ele, dtype=np.float64)
            for aznum in xrange(nsweeps):
                azg = np.ones(rg.shape, dtype=np.float64) * az_deg[aznum]
                x, y, z = radar_coords_to_cart(rg, azg, ele)
                zz[aznum, :, :] = z
                xx[aznum, :, :] = x
                yy[aznum, :, :] = y

        elif self.projection == 'ppi':
            rg, azg = np.meshgrid(range_km, az_deg)
            rg = np.array(rg, dtype=np.float64)
            azg = np.array(azg, dtype=np.float64)
            for elnum in xrange(nsweeps):
                ele = np.ones(rg.shape, dtype=np.float64) * el_deg[elnum]
                x, y, z = radar_coords_to_cart(rg, azg, ele)
                zz[elnum, :, :] = z
                xx[elnum, :, :] = x
                yy[elnum, :, :] = y

        return {'x': xx, 'y': yy, 'z': zz}

    def _make_fields_list(self):
        """ Return a list of fields. """
        fh = self.field_headers
        return [fh[i]['field_name'] for i in range(len(fh))]


class _MdvVolumeDataExtractor(object):
    """
    Class facilitating on demand extraction of data from a MDV file.

    Parameters
    ----------
    mdvfile : MdvFile
        Open MdvFile object to extract data from.
    field_num : int
        Field number of data to be extracted.
    fillvalue : int
        Value used to fill masked values in the returned array.
    """

    def __init__(self, mdvfile, field_num, fillvalue):
        """ initialize the object. """
        self.mdvfile = mdvfile
        self.field_num = field_num
        self.fillvalue = fillvalue

    def __call__(self):
        """ Return an array containing data from the referenced volume. """
        # grab data from MDV object, mask and reshape
        data = self.mdvfile.read_a_field(self.field_num)
        data[np.where(np.isnan(data))] = self.fillvalue
        data[np.where(data == 131072)] = self.fillvalue
        data = np.ma.masked_equal(data, self.fillvalue)
        data.shape = (data.shape[0] * data.shape[1], data.shape[2])
        return data
