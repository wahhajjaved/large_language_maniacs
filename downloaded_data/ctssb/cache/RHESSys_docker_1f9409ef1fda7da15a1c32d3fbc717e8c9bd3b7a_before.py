#!/usr/bin/env python

'''
To run:

SRC_VOLUME=/tmp UUID=1345f6b3a46e RID=MYRESOURCE123 RHESSYS_PROJECT=DR5_3m_nonburned_DEM_rain_duration_DEM_float_lctest RHESSYS_PARAMS="-st 2001 1 1 1 -ed 2001 1 2 1 -b -t tecfiles/tec_daily.txt -w worldfiles/world_init -r flow/world_init_res_conn_subsurface.flow flow/world_init_res_conn_surface.flow -s 1.43092108352 3.81468111311 3.04983096856 -sv 2.35626069137 49.1712407611 -gw 0.00353233818322 0.495935816914" RHESSYS_USE_SRC_FROM_DATA=True INPUT_URL=http://127.0.0.1:8081 RESPONSE_URL=http://127.0.0.1:8080 ABORT_URL=http://127.0.0.1:8080 ./run.py
'''

import os
import sys
from subprocess import *
import re
import tempfile
import shutil
import zipfile

import requests


MAKE_PATH = '/usr/bin/make'
BUFFER_SIZE = 10240

def main():
    try:
        # Define variables referenced in exception and finally blocks
        # Create temporary directory for storing model data in
        tmp_dir = tempfile.mkdtemp()
        abort_url = None
        
        # Read environment
        abort_url = os.environ['ABORT_URL']
        src_vol = os.environ['SRC_VOLUME']
        rsrc_id = os.environ['RID']
        run_id = os.environ['UUID']
        input_url = os.environ['INPUT_URL']
        response_url = os.environ['RESPONSE_URL']
        rhessys_project = os.environ['RHESSYS_PROJECT']
        rhessys_params = os.environ['RHESSYS_PARAMS']
        
        bag_dir = os.path.join(tmp_dir, rsrc_id, 'bag')
        os.makedirs(bag_dir)
        tmp_zip = os.path.join(bag_dir, 'input.zip')
        
        # Download input data to temporary directory
        r = requests.get(input_url, stream=True)
        with open(tmp_zip, 'wb') as fd:
            for chunk in r.iter_content(BUFFER_SIZE):
                fd.write(chunk)
        
        # Unpack the bag
        bag_zip = zipfile.ZipFile(tmp_zip, 'r')
        bag_list = bag_zip.namelist()
        bag_top_level = bag_list[0].strip(os.path.sep)
        bag_zip.extractall(bag_dir)

        # Check to make sure that RHESSYS_PROJECT exits in the zipfile before extracting
        data_dir = os.path.join(bag_dir, bag_top_level, 'data', 'contents')
        zip_name = rhessys_project + os.extsep + 'zip'
        zip_path = os.path.join(data_dir, zip_name)
        zip.ZipFile(zip_path, 'r')
        zlist = zip.namelist()
        top_level = zlist[0].strip(os.path.sep)
        if top_level != rhessys_project:
            raise Exception("Expected resource zip file to contain RHESSYS_PROJECT named {0} but found {1} at the top level of the zip file instead".format(rhessys_project, top_level))
        # Unzip input data
        zip.extractall(data_dir)
        
        # Determine which RHESSys source to use, from SRC_VOLUME or from the
        # downloaded resource
        if os.environ.has_key('RHESSYS_USE_SRC_FROM_DATA'):
            use_src_from_data_vol = bool(os.environ['RHESSYS_USE_SRC_FROM_DATA'])
        else:
            use_src_from_data_vol = False
        # Make sure RHESSys params doesn't already contain an output prefix option, 
        # if so strip it
        rhessys_params = re.sub('-pre\s+\S+\s*', '', rhessys_params)
        
        # Build RHESSys from src
        if use_src_from_data_vol:
            # Use RHESSys src from data volume
            build_dir = os.path.join(data_dir, 
                                     rhessys_project, 'rhessys', 'src', 'rhessys')
        else:
            # Use RHESSys src from src volume (i.e. Docker container)
            build_dir = os.path.join(src_vol, 'RHESSys', 'rhessys')
            
        # Make clean
        make_clean = "{0} clobber".format(MAKE_PATH)
        process = Popen(make_clean, shell=True, cwd=build_dir)
        return_code = process.wait()
        if return_code != 0:
            raise Exception("Command failed: {0}".format(make_clean))
        # Make
        process = Popen(MAKE_PATH, shell=True, cwd=build_dir)
        return_code = process.wait()
        if return_code != 0:
            raise Exception("Command failed: {0}".format(MAKE_PATH))
        
        # Find the RHESSys binary
        rhessys_bin_regex = re.compile('^rhessys.+$')
        contents = os.listdir(build_dir)
        rhessys_bin = None
        for entry in contents:
            m = rhessys_bin_regex.match(entry)
            if m:
                rhessys_bin = os.path.join(build_dir, entry)
                break
        if not rhessys_bin:
            raise Exception("Unable to find RHESSys binary in {0}".format(build_dir))
        if not os.access(rhessys_bin, os.X_OK):
            raise Exception("RHESSys binary {0} is not executable".format(rhessys_bin))
    
        # Run RHESSys
        rhessys_dir = os.path.join(data_dir, 
                                   rhessys_project, 'rhessys')
        # Make output directory
        rhessys_out = os.path.join(rhessys_dir, 'output', run_id)
        if os.path.exists(rhessys_out):
            raise Exception("RHESSys output directory {0} already exists, and should not"
                            .format(rhessys_out))
        os.makedirs(rhessys_out, 0755)
        
        rhessys_cmd = "{0} {1} -pre output/{2}/rhessys".format(rhessys_bin, rhessys_params, run_id)
        process = Popen(rhessys_cmd, shell=True, cwd=rhessys_dir)
        return_code = process.wait()
        if return_code != 0:
            raise Exception("Command failed: {0}, cwd: {1}".format(rhessys_cmd, rhessys_dir))
        
        # POST RHESSys output to RESPONSE_URL
        # Find results
        files = {}
        contents = os.listdir(rhessys_out)
        for entry in contents:
            files[entry] = open(os.path.join(rhessys_out, entry), 'rb')
        r = requests.post(response_url, files=files)
        
    except Exception as e:
        # POST error to ABORT_URL
        if abort_url:
            r = requests.post(abort_url, data={"error_text" : e})
        else:
            raise e
    finally:
        # Clean up
        shutil.rmtree(tmp_dir)
    
if __name__ == "__main__":
    main()
    
