#__init__.py

import os, re
import numpy as np
import pandas as pd

from pysis import isis, CubeFile
from pysis.labels import parse_file_label, parse_label
from pysis.util.file_manipulation import ImageName, write_file_list


GROUP_RE = re.compile(r'(Group.*End_Group)', re.DOTALL)
# content_re = re.compile(r'(Group.*End_Group)', re.DOTALL)

# does this need to go at the top?: change

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
isistools
Module for often used functions while scripting using pysis.
To use: import isistools

import sys
from os import path

# adds the current path to the python path, so python can find
# modules in the directory
sys.path.insert(0, path.dirname(__file__))
"""

# TODO: normalize inputs to functions:
# filename or image, not "name"

def read_regions(filename):
    """
    Args: yaml filename in region format
    Returns: datapath dict, region dict
    """
    places = yaml.load(open(places))
    datapath = places[feature][0]['data']
    region = places[feature][0]['region']

    return datapath, region


# Do I need this function? can't I just glob?
def read_in_list(filename):    
    with open(filename) as f:
        lines = f.read().splitlines()
    return lines

# Maybe this should go in photometry module??
def get_center_lat_lon(minlat, maxlat, minlon, maxlon):
    '''
    Input minimum and maximum latitude and longitude
    Returns center latitude and longitude
    '''
    center_lat = minlat + abs(maxlat - minlat)/2
    center_lon = minlon + abs(maxlon - minlon)/2
    return center_lat, center_lon

# Wrappers for isis functions:

def spice(image, model):
    """
    Args:
        image: image filename
        model: full path to dtm model name
    """
    isis.spiceinit(
        from_      = image,
        spksmithed = True,
        shape      = 'user',
        model      = model
    )

def phocube(image):
    """
    Calls isis phocube. Input file should be projected. 
    Input one band only!
    """
    isis.phocube(from_=str(image.cub)+'+1',
                to=image.phobands.cub,
                phase='true',
                localemission='true',
                localincidence='true',
                SubSolarGroundAzimuth='true',
                latitude='false',
                longitude='false'
    )

def apply_exposure_time(image, exposure_time):
    isis.fx(f1=image.dn.cub, 
            to=image.cal.cub,
            equation=f1/exposure_time
    )
    os.remove(image.dn.cub) # cleanup

# a "frame" gets passed into this function
def calibrate_wac(image, model, units):
    spice(image, model)

    if units=='calibrated_dn':
        isis.lrowaccal(
            from_       = image.cub,
            to          = image.dn.cub,
            RADIOMETRIC = 'FALSE'
        )
        apply_exposure_time(image, get_exposure_time(image))
    elif units=='reflectance':
        isis.lrowaccal(
            from_       = image.cub,
            to          = image.cal.cub,
            RADIOMETRIC = 'TRUE'
        )
    else: print "Improper image units!"


# TODO: fix input and output here
# a frame is passed in here
def project_wac(image, map):
    """
    Args: 
        image: filename
        map: isis maptemplate mapfile
    """
    isis.cam2map(
        from_    = frame.photrim,
        to       = frame.proj,
        map      = map,
        matchmap = True
    )


# a "frame" gets passed into this function
def create_mosaic(images, mosaic):
    """
    Args: 
        images: files to mosaic together
        mosaic: output mosaic filename
    """
    with NamedTemporaryFile() as listfile:
        write_file_list(listfile, [image.proj.cub for image in images])
        listfile.flush()

        isis.automos(
            fromlist = listfile.name,
            mosaic   = mosaic
        )

# gets passed frames
def mosrange(images, map):
    with NamedTemporaryFile() as listfile:
        write_file_list(listfile, [image.photrim.cub for image in images])
        # listfile.flush() makes sure list is in on disk
        listfile.flush()

        isis.mosrange(
            fromlist   = listfile.name,
            to         = map,
            precision  = 2,
            projection = 'sinusoidal',
            londir     = 'positiveeast',
            londom     = 180
        )

def makemap(region, feature, scale, proj):
    '''
    Uses a set of latitude and longitude boundaries, a projection, and
    a scale to create a mapfile.
    '''
    clon = region[2]+abs(region[3]-region[2])/2
    clat = region[0]+abs(region[1]-region[0])/2

    isis.maptemplate(map=feature+'.map', 
                     projection=proj,
                     clat=clat,
                     clon=clon,
                     rngopt='user',
                     resopt='mpp',
                     resolution=scale,
                     minlat=region[0],
                     maxlat=region[1],
                     minlon=region[2],
                     maxlon=region[3]
                     )
    pass


def makemap_freescale(region, feature, proj, listfile):
    '''
    Uses a set of latitude and longitude boundaries, a projection,
    and a list of images to calculate the image scale
    A mapfile is created
    '''
    clon = region[2]+abs(region[3]-region[2])/2
    clat = region[0]+abs(region[1]-region[0])/2

    isis.maptemplate(map=feature+'.map',
                     fromlist=listfile, 
                     projection=proj,
                     clat=clat,
                     clon=clon,
                     rngopt='user',
                     resopt='calc',
                     resolution=scale,
                     minlat=region[0],
                     maxlat=region[1],
                     minlon=region[2],
                     maxlon=region[3]
                     )
    pass

def check_for_nulls(image, maxnulls):
    nulls = number_null_pixels(image.cub)
    if int(nulls) > maxnulls:
        print "Image has too many NULLS: %s", image.cub
        os.remove(str(image)+'*')
        return False
    else:
        return True

# Getting information from labels and images:

def band_means(bands):
    return bands.mean(axis=(1,2))

def band_stds(bands):
    return bands.std(axis=(1,2))

def img_stats(name):
    cube = CubeFile.open(name)
    return band_means(cube.data), band_stds(cube.data)

def number_null_pixels(image):
    output = isis.stats.check_output(from_=image)
    results = parse_label(GROUP_RE.search(output).group(1))['Results']
    return results['NullPixels']

# TODO: write a function that will get the pixel scale no matter
# the file type: projected or unprojected (with spice)
def get_native_pixel_scale(img_name):
    """
    Args: image filename
    Returns: the pixel_scale
    """
    output = isis.campt.check_output(from_=img_name)
    output = GROUP_RE.search(output).group(1) 
    pixel_scale = parse_label(output)['GroundPoint']['SampleResolution']
    
    return pixel_scale

def get_proj_pixel_scale(img_name):
    """
    Args: image filename
    Returns: the pixel_scale
    """
    label = parse_file_label(image)
    mapping = label['IsisCube']['Mapping']
    pixel_scale = mapping['PixelResolution']
    
    return pixel_scale

def get_exposure_time(image):
    """
    Exposure time is in units of milliseconds. Images in calibrated DN and need 
    to be divided by exposure time. Exposure time is the same for UV and VIS 
    observations.
    """
    # Get label info
    label = parse_file_label(image)
    instrument = label['IsisCube']['Instrument']
    
    return instrument['ExposureDuration']

def get_img_center(img_name):
    """
    Args: image filename
    Returns: center latitude and center longitude of image
    """
    output = isis.campt.check_output(from_=img_name)
    output = GROUP_RE.search(output).group(1) 
    clon = parse_label(output)['GroundPoint']['PositiveEast360Longitude']
    clat = parse_label(output)['GroundPoint']['PlanetographicLatitude']

    return clat, clon

# Version from lroc_wac_proc_cal.py
def get_image_info(image):
    """
    GATHER INFORMATION ABOUT SINGLE OBSERVATION
    BASED ON VIS mosaic only
    """
    # Get label info
    label = parse_file_label(image)
    instrument = label['IsisCube']['Instrument']

    # Get campt info
    output = isis.campt.check_output(from_=image)
    gp = parse_label(GROUP_RE.search(output).group(1))['GroundPoint']

    return pd.Series({
        'start_time':              instrument['StartTime'],
        'exp_time':                instrument['ExposureDuration'],
        'fpa_temp':                instrument['MiddleTemperatureFpa'],
        'subsolar_azimuth':        gp['SubSolarAzimuth'],
        'subsolar_ground_azimuth': gp['SubSolarGroundAzimuth'],
        'solar_distance':          gp['SolarDistance']
    })

def get_spectra(name):
    uv_avgs, uv_stds = get_img_stats('{}.uv.mos.crop.cub'.format(name))
    vis_avgs, vis_stds = get_img_stats('{}.vis.mos.crop.cub'.format(name))

    bands = [321, 360, 415, 566, 604, 643, 689]

    avgs = pd.Series(
        data = np.concatenate([uv_avgs, vis_avgs]),
        index = ['avg_{}'.format(band) for band in bands]
    )

    stds = pd.Series(
        data = np.concatenate([uv_stds, vis_stds]),
        index = ['std_{}'.format(band) for band in bands]
    )

    return pd.concat([avgs, stds])


def get_pho_bands(image):
    """
    Calls phocube on both even and odd parts of the wac and creates a
    continuous version using handmos. Uses map-projected cubes.
    Uses 415 nm band as input (band 1 of the vis frames)
    """
    phocube(image.odd.proj.cub)
    phocube(image.even.proj.cub)

    # handmosaic the odd frames into the even frames
    isis.handmos(from_=image.odd.phoband.cub,
                mosaic=image.even.phoband.cub,
                priority='ontop'
    )
    # shutil.copyfile(src, dst)
    shutil.copyfile(image.even.phoband.cub, image.phoband.cub)
    os.remove(image.odd.phoband.cub, image.even.phoband.cub) #cleanup