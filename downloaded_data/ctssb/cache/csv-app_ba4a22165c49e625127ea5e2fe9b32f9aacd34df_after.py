#!/usr/bin/env python
# -*- coding: utf-8 -*-
# (c) Copyright 2013, 2014, 2015 University of Manchester\
#\
# ImportCSV is free software: you can redistribute it and/or modify\
# it under the terms of the GNU General Public License as published by\
# the Free Software Foundation, either version 3 of the License, or\
# (at your option) any later version.\
#\
# ImportCSV is distributed in the hope that it will be useful,\
# but WITHOUT ANY WARRANTY; without even the implied warranty of\
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the\
# GNU General Public License for more details.\
# \
# You should have received a copy of the GNU General Public License\
# along with ImportCSV.  If not, see <http://www.gnu.org/licenses/>\
#
import logging
import os
from datetime import datetime
import json
import numpy as np
import pandas as pd
from HydraLib.HydraException import HydraPluginError

from HydraLib import config, hydra_dateutil
from csv_util import validate_value
import pytz

log = logging.getLogger(__name__)

def create_dataset(value,
                   resource_attr,
                   unit,
                   dimension,
                   resource_name,
                   metadata,
                   restriction_dict,
                   expand_filenames,
                   basepath,
                   file_dict,
                   default_name,
                   timezone,
                  ):

    resourcescenario = dict()

    
    if metadata.get('name'):
        dataset_name = metadata['name']
        del(metadata['name'])
    else:
        dataset_name = 'Import CSV data'


    dataset          = dict(
        id=None,
        type=None,
        unit=None,
        dimension=None,
        name=dataset_name,
        value=None,
        hidden='N',
        metadata=None,
    )

    resourcescenario['attr_id'] = resource_attr['attr_id']
    resourcescenario['resource_attr_id'] = resource_attr['id']

    value = value.strip()
    if unit is not None:
        unit = unit.strip()
        if len(unit) == 0:
            unit = None
    arr_struct = None
    try:
        float(value)
        dataset['type'] = 'scalar'
        scal = create_scalar(value, restriction_dict)
        dataset['value'] = scal
    except ValueError:
        #Check if it's an array or timeseries by first seeing if the value points
        #to a valid file.
        value = value.replace('\\', '/')
        try:
            filedata = []
            if expand_filenames:
                full_file_path = os.path.join(basepath, value)
                if file_dict.get(full_file_path) is None:
                    with open(full_file_path) as f:
                        filedata = []
                        for l in f:
                            l = l.strip().replace('\n', '').replace('\r', '')
                            filedata.append(l)
                        file_dict[full_file_path] = filedata
                else:
                    filedata = file_dict[full_file_path]



                #The name of the resource is how to identify the data for it.
                #Once this the correct line(s) has been identified, remove the
                #name from the start of the line
                data = []
                for l in filedata:
                    #If a seasonal timeseries is specified using XXXX, then convert
                    #it to use '9999' as this allows valid datetime objects to be
                    #constructed
                    seasonal_key = config.get('DEFAULT', 'seasonal_key', '9999')
                    l = l.replace('XXXX', seasonal_key)
                    
                    l_resource_name = l.split(',',1)[0].strip()
                    if l_resource_name == resource_name:
                        data.append(l[l.find(',')+1:])
                if len(data) == 0:
                    log.info('%s: No data found in file %s' %
                                 (resource_name, value))
                    raise HydraPluginError('%s: No data found in file %s' %
                                         (resource_name, value))
                else:
                    if is_timeseries(data):
                        value_header = get_value_header(filedata)
                        
                        ts = create_timeseries( data,
                                                restriction_dict=restriction_dict,
                                                header=value_header,
                                                filename=value,
                                                timezone=timezone)
                       
                        dataset['type'] = 'timeseries' 
                        dataset['value'] = ts
                    else:
                        dataset['type'] = 'array'
                        if len(filedata) > 0:
                            try:
                                dataset['value'] = create_array(data[0], restriction_dict)
                            except Exception, e:
                                log.exception(e)
                                raise HydraPluginError("There is a value "
                                                       "error in %s. "
                                                       "Please check value"
                                                       " %s is correct."%(value, data[0]))
                        else:
                            dataset['value'] = None
            else:
                raise IOError
        except IOError, e:
            dataset['type'] = 'descriptor'
            desc = create_descriptor(value, restriction_dict)
            dataset['value'] = desc
    
    if unit is not None:
        dataset['unit'] = unit
    if dimension is not None:
        dataset['dimension'] = dimension

    dataset['name'] = default_name

    resourcescenario['value'] = dataset

    m = {}

    if metadata:
        m = metadata
    
    if arr_struct:
        m['data_struct'] = arr_struct

    m = json.dumps(m)

    dataset['metadata'] = m

    return resourcescenario

def create_scalar(value, restriction_dict={}):
    """
        Create a scalar (single numerical value) from CSV data
    """
    validate_value(value, restriction_dict)
    scalar = str(value)
    return scalar

def create_descriptor(value, restriction_dict={}):
    """
        Create a scalar (single textual value) from CSV data
    """
    validate_value(value, restriction_dict)
    descriptor = value
    return descriptor

def create_timeseries(data, restriction_dict={}, header=None, filename="", timezone=pytz.utc):
    if len(data) == 0:
        return None
    
    if header is not None:
        header = header.strip(',')
        col_headings = header.split(',')
    else:
        col_headings =[str(idx) for idx in range(len(data[0].split(',')[2:]))]

    date = data[0].split(',', 1)[0].strip()
    timeformat = hydra_dateutil.guess_timefmt(date)
    seasonal = False

    seasonal_key = config.get('DEFAULT', 'seasonal_key', '9999')
    if 'XXXX' in timeformat or seasonal_key in timeformat:
        seasonal = True
    
    ts_values = {}
    for col in col_headings:
        ts_values[col] = {}
    ts_times = [] # to check for duplicae timestamps in a timeseries.
    timedata = data
    for line in timedata:
        
        if line == '' or line[0] == '#':
            continue

        dataset = line.split(',')
        tstime = datetime.strptime(dataset[0].strip(), timeformat)
        tstime = timezone.localize(tstime)

        ts_time = hydra_dateutil.date_to_string(tstime, seasonal=seasonal)

        if ts_time in ts_times:
            raise HydraPluginError("A duplicate time %s has been found "
                                   "in %s where the value = %s)"%( ts_time,
                                                      filename,
                                                     dataset[2:]))
        else:
            ts_times.append(ts_time)

        value_length = len(dataset[2:])
        shape = dataset[1].strip()
        if shape != '':
            array_shape = tuple([int(a) for a in
                                 shape.split(" ")])
        else:
            array_shape = (value_length,)

        ts_val_1d = []
        for i in range(value_length):
            ts_val_1d.append(str(dataset[i + 2].strip()))

        try:
            ts_arr = np.array(ts_val_1d)
            ts_arr = np.reshape(ts_arr, array_shape)
        except:
            raise HydraPluginError("Error converting %s in file %s to an array"%(ts_val_1d, filename))

        ts_value = ts_arr.tolist()

        for i, ts_val in enumerate(ts_value):
            idx = col_headings[i]
            ts_values[idx][ts_time] = ts_val
    


    timeseries = json.dumps(ts_values)

    validate_value(pd.read_json(timeseries), restriction_dict)
    

    return timeseries

def create_array(data, restriction_dict={}):
    """
        Create a (multi-dimensional) array from csv data
    """
    #Split the line into a list
    dataset = data.split(',')
    #First column is always the array dimensions
    arr_shape = dataset[0]
    #The actual data is everything after column 0
    eval_dataset = []
    for d in dataset[1:]:
        try:
            d = eval(d)
        except:
            d = str(d)
        eval_dataset.append(d)
        #dataset = [eval(d) for d in dataset[1:]]

    #If the dimensions are not set, we assume the array is 1D
    if arr_shape != '':
        array_shape = tuple([int(a) for a in arr_shape.strip().split(" ")])
    else:
        array_shape = (len(eval_dataset),)

    #Reshape the array back to its correct dimensions
    arr = np.array(eval_dataset)
    try:
        arr = np.reshape(arr, array_shape)
    except:
        raise HydraPluginError("You have an error with your array data."
                               " Please ensure that the dimension is correct."
                               " (array = %s, dimension = %s)" %(arr, array_shape))

    validate_value(arr.tolist(), restriction_dict)

    arr = json.dumps(arr.tolist())

    return arr

def is_timeseries(data):
    """
    Check whether a piece of data is a timeseries by trying to guess its
    date format. If that fails, it's not a time series.
    """
    try:
        date = data[0].split(',')[0].strip()
        timeformat = hydra_dateutil.guess_timefmt(date)
        if timeformat is None:
            return False
        else:
            return True
    except:
        raise HydraPluginError("Unable to parse timeseries %s"%data)

def get_value_header(filedata):
    """
        Look for column descriptors on the first line of the array and timeseries files
    """
    value_header = filedata[0].replace(' ', '')
    if value_header.startswith('arraydescription,') or value_header.startswith(','):

        arr_struct = filedata[0].strip().replace(' ', '').replace(',,', '')
        
        arr_struct = arr_struct.split(',')
        arr_struct = "|".join(arr_struct)
        #Set the value header back to its original format (with spaces)
        value_header = filedata[0]
        filedata = filedata[1:]
    elif value_header.startswith('timeseriesdescription') or value_header.startswith(','):

        arr_struct = filedata[0].strip().replace(' ', '').replace(',,', '')

        arr_struct = arr_struct.split(',')
        arr_struct = "|".join(arr_struct[3:])
        #Set the value header back to its original format (with spaces)
        value_header = filedata[0]
        filedata = filedata[1:]
    else:
        value_header = None

    return value_header
