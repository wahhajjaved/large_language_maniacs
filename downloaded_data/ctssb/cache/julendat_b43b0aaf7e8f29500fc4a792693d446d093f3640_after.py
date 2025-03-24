"""Process data from level 0200 to gap-filled level 0300.
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

import ConfigParser
import datetime
import fnmatch
import os
import shutil
from julendat.processtools.gapcontrol.StationToLevel0300 import \
    StationToLevel0300

def locate(pattern, patternpath, root=os.curdir):
    '''Locate files matching filename pattern recursively
    
    This routine is based on the one from Simon Brunning at
    http://code.activestate.com/recipes/499305/ and extended by the patternpath.
     
    Args:
        pattern: Pattern of the filename
        patternpath: Pattern of the filepath
        root: Root directory for the recursive search
    '''
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for filename in fnmatch.filter(files, pattern):
            # Modified by Thomas Nauss
            if fnmatch.fnmatch(path, patternpath):
                yield os.path.join(path, filename)

def locate_path(patternpath, root=os.curdir):
    '''Locate files matching filename pattern recursively
    
    This routine is based on the one from Simon Brunning at
    http://code.activestate.com/recipes/499305/ and extended by the patternpath.
     
    Args:
        patternpath: Pattern of the filepath
        root: Root directory for the recursive search
    '''
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for dir_name in fnmatch.filter(dirs, patternpath):
                yield os.path.join(path, dir_name)

def configure(config_file):
    """Reads configuration settings and configure object.
    
    Args:
        config_file: Full path and name of the configuration file.
    """
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    toplevel_processing_plots_path = config.get('repository', \
                                          'toplevel_processing_plots_path')
    project_id = config.get('project','project_id')
    return toplevel_processing_plots_path, project_id

    
def main():
    """Main program function
    Process data from level 0000 to level 0050.
    """
    print
    print 'Module: calibration_level0100'
    print 'Version: ' + __version__
    print 'Author: ' + __author__
    print 'License: ' + __license__
    print   
    
    config_file = "ki_config.cnf"
    toplevel_processing_plots_path, project_id = \
        configure(config_file=config_file)
    input_path = toplevel_processing_plots_path + project_id
    
    station_dataset=locate("*rug*.dat", "*qc25_fah01_0290", input_path)
    for dataset in station_dataset:
        print " "
        systemdate = datetime.datetime.now()

        try:
            print " "
            print "Filling gaps in ", dataset
            systemdate = datetime.datetime.now()
            filepath=dataset
            StationToLevel0300(filepath=filepath, config_file=config_file)
        except Exception as inst:
            print "An error occured with the following dataset."
            print "Some details:"
            print "Filename: " + dataset
            print "Exception type: " , type(inst)
            print "Exception args: " , inst.args
            print "Exception content: " , inst        

if __name__ == '__main__':
    main()

