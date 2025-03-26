"""
Wrapper module to launch preprocessor
"""

import logging
import os
import pkg_resources
import yaml
import fnmatch
import xml.etree.ElementTree as ETree
from datetime import datetime
from .attribute_dict import AttributeDict
from .file_list_sar_pre_processing import SARList
import subprocess
from netCDF4 import Dataset
from typing import List


class PreProcessor(object):

    def __init__(self, **kwargs):
        self.config_file = kwargs.get('config', None)
        self.filelist = kwargs.get('filelist', None)
        self._check()
        self._load_config()
        if kwargs.get('input', None) is not None:
            self.config.input_folder = kwargs.get('input', None)
        if kwargs.get('output', None) is not None:
            self.config.output_folder = kwargs.get('output', None)

    def _check(self):

        assert self.config_file is not None, 'ERROR: Configuration file needs to be provided'

    @staticmethod
    def pre_process():
        assert False, 'Routine should be implemented in child class'

    def _load_config(self):
        """
        Load configuration from self.config.bb.pre_process()
           writes to self.config.
        """
        with open(self.config_file, 'r') as cfg:
            self.config = yaml.safe_load(cfg)
            if 'SAR' in self.config:
                self.config = AttributeDict(**self.config['SAR'])
            else:
                self.config = AttributeDict(**self.config)


class SARPreProcessor(PreProcessor):

    def __init__(self, **kwargs):
        super(SARPreProcessor, self).__init__(**kwargs)

        # Check if output folder is specified
        assert self.config.output_folder is not None, 'ERROR: output folder needs to be specified'

        # Initialise output folder for different preprocessing steps
        # (can be put in the YAML config file if needed)
        self.config.output_folder_step1 = os.path.join(self.config.output_folder, 'step1')
        self.config.output_folder_step2 = os.path.join(self.config.output_folder, 'step2')
        self.config.output_folder_step3 = os.path.join(self.config.output_folder, 'step3')

        # Initialise name of necessary xml-graphs for preprocessing
        # (can be put in the YAML config file if needed)
        self._configure_config_graph('xml_graph_pre_process_step1', 'pre_process_step1.xml')
        self._configure_config_graph('xml_graph_pre_process_step1_border', 'pre_process_step1_border.xml')
        self._configure_config_graph('xml_graph_pre_process_step2', 'pre_process_step2.xml')
        self._configure_config_graph('xml_graph_pre_process_step3', 'pre_process_step3.xml')

        # Initialise name addition for output files
        self.name_addition_step1 = '_GC_RC_No_Su'
        self.name_addition_step2 = '_Co'
        self.name_addition_step3 = '_speckle'

        # Check if path of SNAP's graph-processing-tool is specified
        if not self.config.has_entry('gpt'):
            # test that gpt is available as parameter
            try:
                return_code = subprocess.call("gpt Subset -h")
                if return_code > 0:
                    raise UserWarning('ERROR: path for SNAPs graph-processing-tool is not specified correctly')
            except FileNotFoundError:
                raise UserWarning('ERROR: path for SNAPs graph-processing-tool is not specified correctly')

        # TODO PUT THE GRAPH DIRECTORIES AND NAMES IN A SEPARATE CONFIG !!!
        # todo discuss if input/output specification part of processing or part of initialization of the object itself

    def _configure_config_graph(self, key_name: str, default_name: str):
        if self.config.has_entry(key_name):
            if not os.path.exists(self.config[key_name]):
                if self.config.has_entry('xml_graph_path'):
                    graph_path = os.path.join(self.config.xml_graph_path, self.config[key_name])
                    if not os.path.exists(graph_path):
                        raise UserWarning(f'Could not determine location of {self.config[key_name]}.')
                    self.config.add_entry(key_name, graph_path)
                else:
                    raise UserWarning(f'Could not determine location of {self.config[key_name]}.')
        else:
            default_graph = pkg_resources.resource_stream('sar_pre_processing.default_graphs', default_name)
            self.config.add_entry(key_name, default_graph)

    def set_file_list(self, file_list: List[str]):
        self.file_list = file_list

    @staticmethod
    def _create_file_list(input_folder, expression):
        """
        Create list containing all files in input_folder (without subfolder)
        that contain the provided expression within the filename
        """
        file_list = []
        for root, dirnames, filenames in os.walk(input_folder):
            for filename in fnmatch.filter(filenames, expression):
                file_list.append(os.path.join(root, filename))
            break
        return file_list

    @staticmethod
    def _decompose_filename(file):
        """
        Decomposition of filename including path in
        path, filename, fileshortname and extension
        """
        (filepath, filename) = os.path.split(file)
        (fileshortname, extension) = os.path.splitext(filename)
        return filepath, filename, fileshortname, extension

    @staticmethod
    def _get_area(lat_min, lat_max, lon_min, lon_max):
        """
        Change input coordinates for subset operator"
        """
        assert lat_min <= lat_max, 'ERROR: invalid lat'
        assert lon_min <= lon_max, 'ERROR: invalid lon'
        return '%.14f %.14f,%.14f %.14f,%.14f %.14f,%.14f %.14f,%.14f %.14f' % \
               (lon_min, lat_min, lon_min, lat_max, lon_max, lat_max, lon_max, lat_min, lon_min, lat_min)

    def create_processing_file_list(self):
        # create filelist
        self.file_list = SARList(config=self.config).create_list()

    def pre_process_step1(self):
        """
        Pre-process S1 SLC data with SNAP's GPT

        1) apply precise orbit file
        2) thermal noise removal
        3) calibration
        4) TOPSAR-Deburst
        5) Geometric Terrain Correction
        6) Radiometric Correction (after kellndorfer et al.)
        7) backscatter normalisation on specified angle in config file (based on Lambert's Law)

        """

        # Check if input folder is specified
        assert self.config.input_folder is not None, 'ERROR: input folder not specified'
        assert os.path.exists(self.config.input_folder)

        # Check if output folder for step1 is specified, if not existing create
        # new folder
        assert self.config.output_folder_step1 is not None, 'ERROR: output folder for step1 needs to be specified'
        if not os.path.exists(self.config.output_folder_step1):
            os.makedirs(self.config.output_folder_step1)

        # Check if XML file for pre-processing is specified
        assert self.config.xml_graph_pre_process_step1 is not None, \
            'ERROR: path of XML file for pre-processing step 1 is not not specified'

        area = None
        try:
            lower_right_y = self.config.region['lr']['lat']
            upper_left_y = self.config.region['ul']['lat']
            upper_left_x = self.config.region['ul']['lon']
            lower_right_x = self.config.region['lr']['lon']
            # todo: how is it with coordinates that go across the datum
            # Coordinates for subset area
            area = self._get_area(lower_right_y, upper_left_y, upper_left_x, lower_right_x)
        except AttributeError:
            logging.info('area of interest not specified, whole images will be processed')
        # loop to process all files stored in input directory
        try:
            normalisation_angle = self.config.normalisation_angle
            if normalisation_angle is None:
                normalisation_angle = '35'
                logging.info('normalisation angle not specified, default value of 35 is used for processing')
        except AttributeError:
            normalisation_angle = '35'
            logging.info('normalisation angle not specified, default value of 35 is used for processing')
        for file in self.file_list[0]:
            logging.info('Scene ', self.file_list[0].index(file) + 1, ' of ', len(self.file_list[0]))
            self._gpt_step1(file, area, normalisation_angle)
        for i, file in enumerate(self.file_list[1][::2]):
            file_list2 = self.file_list[1][1::2]
            file2 = file_list2[i]
            self._gpt_step1(file, file2, area, normalisation_angle, self.config.xml_graph_pre_process_step1_border)

    def _gpt_step1(self, file: str, file2: str, area: str, normalisation_angle: str, script_path: str):
        # Divide filename
        filepath, filename, fileshortname, extension = self._decompose_filename(file)
        # Call SNAP routine, xml file
        logging.info('Process ', filename, ' with SNAP.')
        output_file = os.path.join(self.config.output_folder_step1,
                                   fileshortname + self.name_addition_step1 + '.dim')
        area_part = ''
        if area is not None:
            area_part = '-Parea="POLYGON ((' + area + '))" '
        file2_part = ''
        if file2 is not None:
            file2_part = ' -Pinput2="' + file2 + '"'
        call = '"' + self.config.gpt + '" "' + os.path.join(self.config.xml_graph_path, script_path) + \
               '" -Pinput="' + file + '"' + file2_part + ' -Poutput="' + output_file + \
               '" -Pangle="' + normalisation_angle + '" ' + area_part + '-c 2G -x'
        return_code = subprocess.call(call, shell=True)
        logging.info(return_code)

    def pre_process_step2(self):
        """
        pre_process_step1 has to be done first

        Pre-process S1 SLC data with SNAP's GPT

        1) co-register pre-processed data

        !!! all files will get metadata of the master image !!! Problem?

        """
        # Check if XML file for pre-processing step 2 is specified
        assert self.config.xml_graph_pre_process_step2 is not None, \
            'ERROR: path of XML file for pre-processing step 2 is not not specified'
        # Check if output folder of pre_process_step1 exists
        assert os.path.exists(self.config.output_folder_step1), \
            'ERROR: output folder of pre-processing step1 not found'
        # Check if output folder for step2 is specified, if not existing create
        # new folder
        assert self.config.output_folder_step2 is not None, 'ERROR: output folder for step2 needs to be specified'
        if not os.path.exists(self.config.output_folder_step2):
            os.makedirs(self.config.output_folder_step2)

        # Create file_list with all to be processed images
        if self.file_list is None:
            logging.info('no file list specified, therefore all images in output folder step1 will be processed')
            file_list = self._create_file_list(self.config.output_folder_step1, '*.dim')
            file_list.sort()
        else:
            file_list = []
            for list in self.file_list:
                for file in list:
                    filepath, filename, file_short_name, extension = self._decompose_filename(file)
                    new_file_name = os.path.join(
                        self.config.output_folder_step1, file_short_name + self.name_addition_step1 + '.dim')
                    if os.path.exists(new_file_name) is True:
                        file_list.append(new_file_name)
                    else:
                        logging.info('skip processing for %s. File does not exist' % file)
            file_list.sort()
        # Set Master image for co-registration
        master = file_list[0]
        # loop to co-register all found images to master image
        for file in file_list:
            logging.info('Scene', file_list.index(file) + 1, 'of', len(file_list))
            # Divide filename
            filepath, filename, file_short_name, extension = self._decompose_filename(file)
            # Call SNAP routine, xml file
            logging.info('Process ', filename, ' with SNAP.')
            output_file = os.path.join(
                self.config.output_folder_step2, file_short_name + self.name_addition_step2 + '.dim')
            call = '"' + self.config.gpt + '" "' + \
                   os.path.join(self.config.xml_graph_path, self.config.xml_graph_pre_process_step2) + \
                   '" -Pinput="' + master + '" -Pinput2="' + file + '" -Poutput="' + output_file + '"'
            return_code = subprocess.call(call)
            logging.info(return_code)
            logging.info(datetime.now())

    def pre_process_step3(self):
        """
        pre_process_step1 and 2 has to be done first

        Pre-process S1 SLC data with SNAP's GPT

        1) apply multi-temporal speckle filter

        """
        # Check if output folder of pre_process_step1 exists
        assert os.path.exists(self.config.output_folder_step2), 'ERROR: output folder of pre-processing step2 not found'

        # Check if output folder for step3 is specified, if not existing create
        # new folder
        assert self.config.output_folder_step3 is not None, 'ERROR: output folder for step3 needs to be specified'
        if not os.path.exists(self.config.output_folder_step3):
            os.makedirs(self.config.output_folder_step3)

        # list with all dim files found in output-folder of pre_process_step2

        # Create filelist with all to be processed images
        if self.file_list is None:
            logging.info('no file list specified, therefore all images in output folder step2 will be processed')
            file_list = self._create_file_list(self.config.output_folder_step2, '*.dim')
        else:
            file_list = []
            for list in self.file_list:
                for file in list:
                    file_path, filename, file_short_name, extension = self._decompose_filename(file)
                    new_file_name = os.path.join(self.config.output_folder_step2, file_short_name +
                                                 self.name_addition_step1 + self.name_addition_step2 + '.dim')
                    if os.path.exists(new_file_name) is True:
                        file_list.append(new_file_name)
                    else:
                        logging.info('skip processing for %s. File does not exists' % file)
        # Sort file list by date (hard coded position in filename!!!)
        file_path, filename, file_short_name, extension = self._decompose_filename(file_list[0])
        file_list.sort(key=lambda x: x[len(file_path) + 18:len(file_path) + 33])
        file_list_old = file_list
        for sensor in ['S1A', 'S1B']:
            file_list = [k for k in file_list_old if sensor in k]
            if self.config.speckle_filter.multi_temporal.apply == 'yes':
                # Check if XML file for pre-processing step 3 is specified
                assert self.config.xml_graph_pre_process_step3 is not None, \
                    'ERROR: path of XML file for pre-processing step 3 is not not specified'
                # loop to apply multi-temporal filtering
                # right now 15 scenes if possible 7 before and 7 after multi-temporal filtered scene,
                # vv and vh polarisation are separated
                # use the speckle filter algorithm metadata? metadata for date might be wrong!!!
                for i, file in enumerate(file_list):
                    # apply speckle filter on 15 scenes if possible 7 before and 7 after the scene of interest
                    # what happens if there are less then 15 scenes available
                    if i < 2:
                        processing_file_list = file_list[0:5]
                    elif i <= len(file_list) - 3:
                        processing_file_list = file_list[i - 2:i + 3]
                    else:
                        processing_file_list = file_list[i - 2 - (3 - (len(file_list) - i)):len(file_list)]
                    file_path, filename, file_short_name, extension = self._decompose_filename(file)
                    a, a, b, a = self._decompose_filename(self._create_file_list(
                        os.path.join(file_path, file_short_name + '.data'), '*_slv1_*.img')[0])
                    a, a, c, a = self._decompose_filename(self._create_file_list(
                        os.path.join(file_path, file_short_name + '.data'), '*_slv2_*.img')[0])
                    a, a, d, a = self._decompose_filename(self._create_file_list(
                        os.path.join(file_path, file_short_name + '.data'), '*_slv3_*.img')[0])
                    a, a, e, a = self._decompose_filename(self._create_file_list(
                        os.path.join(file_path, file_short_name + '.data'), '*_slv4_*.img')[0])
                    list_bands_single_speckle_filter = ','.join([b, c, d, e])

                    name_change_vv_single = d
                    name_change_vh_single = e
                    name_change_vv_norm_single = b
                    name_change_vh_norm_single = c

                    list_bands_vv_multi = []
                    list_bands_vh_multi = []

                    list_bands_vv_norm_multi = []
                    list_bands_vh_norm_multi = []

                    for processing_file in processing_file_list:
                        file_path, filename, file_short_name, extension = self._decompose_filename(processing_file)
                        # get filename from folder
                        # think about better way !!!!
                        a, a, band_vv_name_multi, a = self._decompose_filename(self._create_file_list(
                            os.path.join(file_path, file_short_name + '.data'), '*_slv3_*.img')[0])
                        a, a, band_vh_name_multi, a = self._decompose_filename(self._create_file_list(
                            os.path.join(file_path, file_short_name + '.data'), '*_slv4_*.img')[0])
                        a, a, band_vv_name_norm_multi, a = self._decompose_filename(self._create_file_list(
                            os.path.join(file_path, file_short_name + '.data'), '*_slv1_*.img')[0])
                        a, a, band_vh_name_norm_multi, a = self._decompose_filename(self._create_file_list(
                            os.path.join(file_path, file_short_name + '.data'), '*_slv2_*.img')[0])

                        list_bands_vv_multi.append(band_vv_name_multi)
                        list_bands_vh_multi.append(band_vh_name_multi)

                        list_bands_vv_norm_multi.append(band_vv_name_norm_multi)
                        list_bands_vh_norm_multi.append(band_vh_name_norm_multi)

                    # Divide filename of file of interest
                    file_path, filename, file_short_name, extension = self._decompose_filename(file)

                    output_file = os.path.join(
                        self.config.output_folder_step3, file_short_name + self.name_addition_step3 + '.nc')

                    date = datetime.strptime(file_short_name[17:25], '%Y%m%d')
                    date = date.strftime('%d%b%Y')

                    theta = 'localIncidenceAngle_slv10_' + date

                    processing_file_list = ','.join(processing_file_list)
                    list_bands_vv_multi = ','.join(list_bands_vv_multi)
                    list_bands_vh_multi = ','.join(list_bands_vh_multi)
                    list_bands_vv_norm_multi = ','.join(list_bands_vv_norm_multi)
                    list_bands_vh_norm_multi = ','.join(list_bands_vh_norm_multi)

                    call = '"' + self.config.gpt + '" "' \
                           + os.path.join(self.config.xml_graph_path, self.config.xml_graph_pre_process_step3) + \
                           '" -Pinput="' + processing_file_list + '" -Pinput2="' + file + \
                           '" -Poutput="' + output_file + '" -Ptheta="' + theta + \
                           '" -Plist_bands_vv_multi="' + list_bands_vv_multi + \
                           '" -Plist_bands_vh_multi="' + list_bands_vh_multi + \
                           '" -Plist_bands_vv_norm_multi="' + list_bands_vv_norm_multi + \
                           '" -Plist_bands_vh_norm_multi="' + list_bands_vh_norm_multi + '" -Pdate="' + date + \
                           '" -Pname_change_vv_single="' + name_change_vv_single + \
                           '" -Pname_change_vh_single="' + name_change_vh_single + \
                           '" -Pname_change_vv_norm_single="' + name_change_vv_norm_single + \
                           '" -Pname_change_vh_norm_single="' + name_change_vh_norm_single + \
                           '" -Plist_bands_single_speckle_filter="' + list_bands_single_speckle_filter + '"'
                    return_code = subprocess.call(call)
                    logging.info(return_code)
                    logging.info(datetime.now())

    def netcdf_information(self):
        # input folder
        input_folder = self.config.output_folder_step3
        expression = '*.nc'
        file_list = self._create_file_list(input_folder, expression)
        # for loop though all measurement points
        for file in file_list:
            # Divide filename
            file_path, filename, file_short_name, extension = self._decompose_filename(file)
            file_path2 = self.config.output_folder_step1
            # extract date from filename
            date = datetime.strptime(file_short_name[17:32], '%Y%m%dT%H%M%S')

            data_set = Dataset(file, 'r+', format="NETCDF4")
            try:
                data_set.delncattr('start_date', str(date))
                data_set.delncattr('stop_date', str(date))
            except RuntimeError:
                logging.warning('A runtime error has occurred')

            data_set.setncattr_string('date', str(date))
            # extract orbit direction from metadata
            metadata = ETree.parse(os.path.join(file_path2, filename[0:79] + '.dim'))
            for i in metadata.findall('Dataset_Sources'):
                for ii in i.findall('MDElem'):
                    for iii in ii.findall('MDElem'):
                        for iiii in iii.findall('MDATTR'):
                            r = iiii.get('name')
                            if r == 'PASS':
                                orbit_dir = iiii.text
                                if orbit_dir == 'ASCENDING':
                                    orbit_dir = 'ASCENDING'
                                elif orbit_dir == 'DESCENDING':
                                    orbit_dir = 'DESCENDING'
                                data_set.setncattr_string('orbitdirection', orbit_dir)
                            continue
            # extract orbit from metadata
            metadata = ETree.parse(os.path.join(file_path2, filename[0:79] + '.dim'))
            for i in metadata.findall('Dataset_Sources'):
                for ii in i.findall('MDElem'):
                    for iii in ii.findall('MDElem'):
                        for iiii in iii.findall('MDATTR'):
                            r = iiii.get('name')
                            if r == 'REL_ORBIT':
                                relorbit = iiii.text
                                data_set.setncattr_string('relativeorbit', relorbit)
            # extract frequency from metadata
            metadata = ETree.parse(os.path.join(file_path2, filename[0:79] + '.dim'))
            for i in metadata.findall('Dataset_Sources'):
                for ii in i.findall('MDElem'):
                    for iii in ii.findall('MDElem'):
                        for iiii in iii.findall('MDATTR'):
                            r = iiii.get('name')
                            if r == 'radar_frequency':
                                frequency = float(iiii.text)/1000.
                                data_set.setncattr_string('frequency', str(frequency))
            # extract satellite name from name tag
            if file_short_name[0:3] == 'S1A':
                data_set.setncattr_string('satellite', 'S1A')
            elif file_short_name[0:3] == 'S1B':
                data_set.setncattr_string('satellite', 'S1B')


"""run script"""


if __name__ == "__main__":
    processing = SARPreProcessor(config='sample_config_file.yml')
    processing.create_processing_file_list()
    # processing.pre_process_step1()
    # processing.pre_process_step2()
    # processing.pre_process_step3()
    # subprocess.call(os.path.join(os.getcwd(),'projection_problem.sh ' + processing.config.output_folder_step3),
    # shell=True)
    # processing.netcdf_information()
    # NetcdfStack(input_folder=processing.config.output_folder_step3,
    # output_path=processing.config.output_folder_step3.rsplit('/', 1)[0] ,
    # output_filename=processing.config.output_folder_step3.rsplit('/', 2)[1])
    logging.info('finished')
