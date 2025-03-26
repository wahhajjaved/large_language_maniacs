#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Replace values outside a certain range with no data values. """

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import division

import argparse
import logging

from osgeo import gdal
from osgeo import gdal_array

import numpy as np

logger = logging.getLogger(__name__)

DRIVER_MEM = gdal.GetDriverByName(str('mem'))
DRIVER_TIF = gdal.GetDriverByName(str('gtitf'))


def replace(source_path, target_path):
    source_dataset = gdal.Open(source_path)
    source_values = source_dataset.ReadAsArray()
    source_band = source_dataset.GetRasterBand(1)
    source_no_data_value = source_band.GetNoDataValue()

    data_type = source_band.DataType
    dtype = gdal_array.flip_code(data_type)

    target_no_data_value = np.finfo(dtype).max.item()
    condition = np.logical_or.reduce([
        source_values == source_no_data_value,
        source_values < 1000,
        source_values > 1000,
    ])
    target_values = np.where(condition, target_no_data_value, source_values)

    target_dataset = DRIVER_MEM.CreateCopy('', source_dataset)
    target_band = target_dataset.GetRasterBand(1)
    target_band.WriteArray(target_values)
    target_band.SetNoDataValue(target_no_data_value)

    options = ['compress=deflate', 'tiled=yes']
    gdal.GetDriverByName(str('gtiff')).CreateCopy(
        target_path, target_dataset, options=options,
    )


def get_parser():
    """ Return argument parser. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_path', metavar='SOURCE_PATH')
    parser.add_argument('target_path', metavar='TARGET_PATH')
    return parser


def main():
    """ Call replace with args from parser. """
    kwargs = vars(get_parser().parse_args())
    replace(**kwargs)
