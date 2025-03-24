"""Process level 0100 station data to aggregated level 0200.
Copyright (C) 2011 Thomas Nauss, Tim Appelhans

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Please send any comments, suggestions, criticism, or (for our sake) bug
reports to nausst@googlemail.com
"""

__author__ = "Thomas Nauss <nausst@googlemail.com>, Tim Appelhans"
__version__ = "2012-12-17"
__license__ = "GNU GPL, see http://www.gnu.org/licenses/"

import sys
import csv
import os
import string
import ConfigParser
from julendat.processtools import time_utilities
from julendat.filetools.stations.dkstations.DKStationDataFile import DKStationDataFile
import shutil
import time
import datetime
from julendat.metadatatools.stations.StationDataFilePath import StationDataFilePath
from julendat.metadatatools.stations.StationInventory import StationInventory
from julendat.metadatatools.stations.Level01Standards import Level01Standards


class StationToLevel0200:   
    """Instance for processing station level 0100 to level 0200 data.
    """

    def __init__(self, filepath, config_file,run_mode="auto"):
        """Inits StationToLevel0200. 
        
        Args:
            filepath: Full path and name of the level 0100 file
            config_file: Configuration file.
            run_mode: Running mode (auto, manual)
        """
        self.set_run_mode(run_mode)
        self.configure(config_file)
        self.init_filenames(filepath)
        if self.get_run_flag():
            self.run()
        else:
            raise Exception, "Run flag is false."

    def set_run_mode(self,run_mode):
        """Sets run mode.
        
        Args:
            run_mode: Running mode (default: auto)
        """
        self.run_mode = run_mode

    def get_run_mode(self):
        """Gets run mode.
        
        Returns:
            Running mode
        """
        return self.run_mode

    def configure(self,config_file):
        """Reads configuration settings and configure object.
    
        Args:
            config_file: Full path and name of the configuration file.
        """
        self.config_file = config_file
        config = ConfigParser.ConfigParser()
        config.read(self.config_file)
        self.tl_data_path = config.get('repository', 'toplevel_processing_plots_path')
        self.station_inventory = config.get('inventory','station_inventory')
        self.project_id = config.get('project','project_id')
        self.level0050_standards = config.get('general','level0050_standards')
        self.r_filepath = config.get('general','r_filepath')

    def init_filenames(self, filepath):
        """Initializes D&K station data file.
        
        Args:
            filepath: Full path and name of the level 0 file
        """
        try:
            self.filenames = StationDataFilePath(filepath=filepath, \
                toplevel_path=self.tl_data_path)
            self.run_flag = True
        except:
            raise Exception, "Can not compute station data filepath"
            self.run_flag = False

    def get_run_flag(self):
        """Gets runtime flag information.
        
        Returns:
            Runtime flag.
        """
        return self.run_flag

    def run(self):
        """Executes class functions according to run_mode settings. 
        """
        if self.get_run_mode() == "concatenate":
            self.concatenate()
        elif self.get_run_mode() == "aggregate_0200":
            self.target_level = "0200"
            self.aggregate_0200()
        elif self.get_run_mode() == "aggregate_0400":
            self.target_level = "0400"
            self.aggregate_0400()
        elif self.get_run_mode() == "aggregate_0405":
            self.target_level = "0405"
            self.aggregate_0405()
        elif self.get_run_mode() == "aggregate_0420":
            self.target_level = "0420"
            self.aggregate_0420()
        else:
            pass

    def move_data(self):
        """Moves files.
        """
        shutil.move(self.source,self.destination)

    def concatenate(self):
        """Concatenate level 0100 station files prior to aggregation.
        """
        aggregation_level = "fah01"
        self.filenames.build_filename_dictionary(aggregation_level)
        output_path = self.filenames.get_filename_dictionary()\
                      ["level_0190_ascii-path"]
        if not os.path.isdir(output_path):
            os.makedirs(output_path)
        infile = open(self.filenames.get_filepath(), "r")
        if os.path.isfile(self.filenames.get_filename_dictionary()\
                      ["level_0190_ascii-filepath"]):
            infile.readline()
        infile_content = infile.read()
        infile.close()
        outfile = open(self.filenames.get_filename_dictionary()\
                      ["level_0190_ascii-filepath"], "a")
        outfile.write(infile_content)
        outfile.close()

    def aggregate_0200(self):
        """Aggregate level 0100 station files to level 0200.
        """
        aggregation_level = "fah01"
        self.filenames.build_filename_dictionary(aggregation_level)
        output_path = self.filenames.get_filename_dictionary()\
                      ["level_0200_ascii-path"]
        if not os.path.isdir(output_path):
            os.makedirs(output_path)
        aggregation_level = "1h"
        outputfilepath = self.filenames.get_filename_dictionary()[\
                             'level_0200_ascii-filepath']
        self.process_aggregation(aggregation_level, outputfilepath)
        self.remove_inf()
        
        print "...finished."

    def aggregate_0400(self):
        """Aggregate level 0310 station files to level 0400.
        """
        aggregation_level = "fam01"
        self.filenames.build_filename_dictionary(aggregation_level)
        output_path = self.filenames.get_filename_dictionary()\
                      ["level_0400_ascii-path"]
        if not os.path.isdir(output_path):
            os.makedirs(output_path)
        aggregation_level = "month"
        outputfilepath = self.filenames.get_filename_dictionary()[\
                             'level_0400_ascii-filepath']
        self.process_aggregation(aggregation_level, outputfilepath)
        self.remove_inf()
        
        print "...finished."

    def aggregate_0405(self):
        """Aggregate level 0310 station files to level 0405.
        """
        aggregation_level = "fad01"
        self.filenames.build_filename_dictionary(aggregation_level)
        output_path = self.filenames.get_filename_dictionary()\
                      ["level_0405_ascii-path"]
        if not os.path.isdir(output_path):
            os.makedirs(output_path)
        aggregation_level = "day"
        outputfilepath = self.filenames.get_filename_dictionary()[\
                             'level_0405_ascii-filepath']
        self.process_aggregation(aggregation_level, outputfilepath)
        self.remove_inf()
        
        print "...finished."

    def aggregate_0420(self):
        """Aggregate level 0310 station files to level 0420.
        """
        aggregation_level = "fad01"
        self.filenames.build_filename_dictionary(aggregation_level)
        output_path = self.filenames.get_filename_dictionary()\
                      ["level_0420_ascii-path"]
        if not os.path.isdir(output_path):
            os.makedirs(output_path)
        aggregation_level = "year"
        outputfilepath = self.filenames.get_filename_dictionary()[\
                             'level_0420_ascii-filepath']
        self.process_aggregation(aggregation_level, outputfilepath)
        self.remove_inf()
        
        print "...finished."
        
    def process_aggregation(self, aggregation_level, outputfilepath):
        """Process aggragation.
        
        Args:
            aggregation_level: Aggregation level
            outputfilepath: Output filepath
        """
        act_wd = os.getcwd()
        os.chdir(self.r_filepath)
        r_source = 'source("' + self.r_filepath + os.sep + \
                'write.aggregate.ki.data.R")'
        r_keyword = "write.aggregate.ki.data"
        r_ifp = 'inputfilepath="' + self.filenames.get_filepath() + '"'
        r_ofp = 'outputfilepath="' + outputfilepath + '"'
        r_level = 'level="' + aggregation_level  + '"'
        r_plevel = 'plevel =' + self.target_level
        r_detail = 'detail = FALSE'
        
	if  self.target_level == "0420" :
            r_detail = 'detail = TRUE'
        
	if self.project_id == "be":
            if aggregation_level == "1h":
                r_scolumn = 'start.column = 10'
            else:
                r_scolumn = 'start.column = 9'
        else:
            r_scolumn = 'start.column = 9'
        
        r_cmd = r_source + '\n' + \
                r_keyword + '(\n' + \
                r_ifp + ',\n' + \
                r_ofp + ',\n' + \
                r_level + ',\n' + \
                r_plevel + ',\n' + \
                r_scolumn + ',\n' + \
                r_detail + ')\n'
        r_script = "aggregation.rscript" 
        f = open(r_script,"w")
        f.write(r_cmd)
        f.close()
        r_cmd = 'R CMD BATCH ' + r_script  + ' ' + r_script + '.log'
        os.system(r_cmd)
        os.chdir(act_wd)

    def remove_inf(self):
        """Remove inf and -inf valus in aggregated level 0200 files.
        """
        if self.get_run_mode() == "aggregate_0200":
            file = self.filenames.get_filename_dictionary()[\
                       'level_0200_ascii-filepath'] 
        elif self.get_run_mode() == "aggregate_0400":
            file = self.filenames.get_filename_dictionary()[\
                       'level_0400_ascii-filepath'] 
        elif self.get_run_mode() == "aggregate_0405":
            file = self.filenames.get_filename_dictionary()[\
                       'level_0405_ascii-filepath'] 
        elif self.get_run_mode() == "aggregate_0420":
            file = self.filenames.get_filename_dictionary()[\
                       'level_0420_ascii-filepath'] 
        infile = open(file, "r")        
        infile_content = infile.read()
        infile.close()
        outfile = open(file, "w")
        outfile.write(infile_content.replace("-Inf", "NA").replace("Inf", "NA").replace("-9999", "NA").replace("9999", "NA"))
        outfile.close()
