"""Preferences.py - singleton preferences for CellProfiler

   TO-DO - load the default preferences from somewhere.
           Create a function to save the preferences.
           Create a function to populate a handles structure with preferences.

CellProfiler is distributed under the GNU General Public License.
See the accompanying file LICENSE for details.

Copyright (c) 2003-2009 Massachusetts Institute of Technology
Copyright (c) 2009-2013 Broad Institute
All rights reserved.

Please see the AUTHORS file for credits.

Website: http://www.cellprofiler.org
"""

import logging
import random
import cellprofiler
import multiprocessing
import os
import os.path
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid
import weakref
from cellprofiler.utilities.utf16encode import utf16encode, utf16decode

logger = logging.getLogger(__name__)

from cellprofiler.utilities.get_proper_case_filename import get_proper_case_filename

'''get_absolute_path - mode = output. Assume "." is the default output dir'''
ABSPATH_OUTPUT = 'abspath_output'

'''get_absolute_path - mode = image. Assume "." is the default input dir'''
ABSPATH_IMAGE = 'abspath_image'

__python_root = os.path.split(str(cellprofiler.__path__[0]))[0]
__cp_root = os.path.split(__python_root)[0]

class HeadlessConfig(object):
    def __init__(self):
        self.__preferences = {}
    
    def Read(self, kwd):
        return self.__preferences[kwd]
    
    def ReadInt(self, kwd, default=0):
        return int(self.__preferences.get(kwd, default))
    
    def ReadBool(self, kwd, default=False):
        return bool(self.__preferences.get(kwd, default))
    
    def Write(self, kwd, value):
        self.__preferences[kwd] = value
        
    WriteInt = Write
    WriteBool = Write
    
    def Exists(self, kwd):
        return self.__preferences.has_key(kwd)

__is_headless = False
__headless_config = HeadlessConfig()

def set_headless():
    global __is_headless
    __is_headless = True
    
def get_headless():
    return __is_headless

def get_config():
    global __is_headless,__headless_config
    if __is_headless:
        return __headless_config
    import wx
    try:
        config = wx.Config.Get(False)
    except wx.PyNoAppError:
        app = wx.App(0)
        config = wx.Config.Get(False)
    if not config:
        wx.Config.Set(wx.Config('CellProfiler','BroadInstitute','CellProfilerLocal.cfg','CellProfilerGlobal.cfg',wx.CONFIG_USE_LOCAL_FILE))
        config = wx.Config.Get()
        if not config.Exists(PREFERENCES_VERSION):
            for key in ALL_KEYS:
                if config.Exists(key):
                    v = config.Read(key)
                    config_write(key, v)
            config_write(PREFERENCES_VERSION, str(PREFERENCES_VERSION_NUMBER))
        else:
            try:
                preferences_version_number = int(config_read(PREFERENCES_VERSION))
                if preferences_version_number != PREFERENCES_VERSION_NUMBER:
                    logger.warning(
                        "Preferences version mismatch: expected %d, at %d" %
                        ( PREFERENCES_VERSION_NUMBER, preferences_version_number))
            except:
                logger.warning(
                    "Preferences version was %s, not a number. Resetting to current version" % preferences_version_number)
                config_write(PREFERENCES_VERSION, str(PREFERENCES_VERSION))
            
    return config

def preferences_as_dict():
    return dict((k, config_read(k)) for k in ALL_KEYS)

def set_preferences_from_dict(d):
    '''Set the preferences by faking the configuration cache'''
    global __cached_values
    __cached_values = d.copy()
    #
    # We also have to defeat value-specific caches.
    #
    global __recent_files
    __recent_files = {}
    for cache_var in (
        "__default_colormap", "__default_image_directory",
        "__default_output_directory", "__allow_output_file_overwrite",
        "__current_pipeline_path", "__has_reported_jvm_error",
        "__ij_plugin_directory", "__ij_version", "__output_filename",
        "__plugin_directory", "__show_analysis_complete_dlg",
        "__show_exiting_test_mode_dlg", "__show_report_bad_sizes_dlg",
        "__show_sampling", "__show_workspace_choice_dlg",
        "__use_more_figure_space",
        "__warn_about_old_pipeline", "__write_MAT_files",
        "__workspace_file", "__omero_server", "__omero_port",
        "__omero_user", "__omero_session_id"):
        globals()[cache_var] = None

__cached_values = {}
def config_read(key):
    '''Read the given configuration value
    
    Only read from the registry once. This is both technically efficient
    and keeps parallel running instances of CellProfiler from overwriting
    each other's values for things like the current output directory.
    
    Decode escaped config sequences too.
    '''
    global __cached_values
    if not __is_headless:
        #
        # Keeps popup box from appearing during testing I hope
        #
        import wx
        shutup = wx.LogNull()
    if __cached_values.has_key(key):
        return __cached_values[key]
    if get_config().Exists(key):
        value = get_config().Read(key)
    else:
        value = None
    if value is not None:
        value = utf16decode(value)
    __cached_values[key] = value
    return value

def config_write(key, value):
    '''Write the given configuration value
    
    Encode escaped config sequences.
    '''
    if not __is_headless:
        #
        # Keeps popup box from appearing during testing I hope
        #
        import wx
        shutup = wx.LogNull()
    __cached_values[key] = value
    if value is not None:
        value = utf16encode(value)
    get_config().Write(key, value)
    
def config_exists(key):
    '''Return True if the key is defined in the configuration'''
    global __cached_values
    if key in __cached_values and __cached_values[key] is not None:
        return True
    return get_config().Exists(key) and get_config().Read(key) is not None
    
def cell_profiler_root_directory():
    if __cp_root:
        return __cp_root
    return '..'

def python_root_directory():
    return __python_root

def resources_root_directory():
    if hasattr(sys, 'frozen'):
        # On Mac, the application runs in CellProfiler2.0.app/Contents/Resources.
        # Not sure where this should be on PC.
        return '.'
    else:
        return __python_root

    
DEFAULT_INPUT_FOLDER_NAME = 'Default Input Folder'
DEFAULT_OUTPUT_FOLDER_NAME = 'Default Output Folder'
ABSOLUTE_FOLDER_NAME = 'Elsewhere...'
DEFAULT_INPUT_SUBFOLDER_NAME = 'Default Input Folder sub-folder'
DEFAULT_OUTPUT_SUBFOLDER_NAME = 'Default Output Folder sub-folder'
URL_FOLDER_NAME = 'URL'
NO_FOLDER_NAME = "None"

'''Please add any new wordings of the above to this dictionary'''
FOLDER_CHOICE_TRANSLATIONS = {
    'Default Input Folder': DEFAULT_INPUT_FOLDER_NAME,
    'Default Output Folder': DEFAULT_OUTPUT_FOLDER_NAME,
    'Absolute path elsewhere': ABSOLUTE_FOLDER_NAME,
    'Default input directory sub-folder': DEFAULT_INPUT_SUBFOLDER_NAME,
    'Default Input Folder sub-folder': DEFAULT_INPUT_SUBFOLDER_NAME,
    'Default output directory sub-folder': DEFAULT_OUTPUT_SUBFOLDER_NAME,
    'Default Output Folder sub-folder': DEFAULT_OUTPUT_SUBFOLDER_NAME,
    'URL': URL_FOLDER_NAME,
    'None': NO_FOLDER_NAME,
    'Elsewhere...': ABSOLUTE_FOLDER_NAME
    }

IO_FOLDER_CHOICE_HELP_TEXT = """
You can choose among the following options which are common to all file input/output 
modules:
<ul>
<li><i>Default Input Folder</i>: Use the default input folder.</li>
<li><i>Default Output Folder:</i> Use from the default output folder.</li>
<li><i>Elsewhere...</i>: Use a particular folder you specify.</li>
<li><i>Default input directory sub-folder</i>: Enter the name of a subfolder of 
the default input folder or a path that starts from the default input folder.</li>
<li><i>Default output directory sub-folder</i>: Enter the name of a subfolder of 
the default output folder or a path that starts from the default output folder.</li>
</ul>
<p><i>Elsewhere</i> and the two sub-folder options all require you to enter an additional 
path name. You can use an <i>absolute path</i> (such as "C:\imagedir\image.tif" on a PC) or a 
<i>relative path</i> to specify the file location relative to a directory):
<ul>
<li>Use one period to represent the current directory. For example, if you choose 
<i>Default Input Folder sub-folder</i>, you can enter "./MyFiles" to look in a 
folder called "MyFiles" that is contained within the Default Input Folder.</li>
<li>Use two periods ".." to move up one folder level. For example, if you choose 
<i>Default Input Folder sub-folder</i>, you can enter "../MyFolder" to look in a 
folder called "MyFolder" at the same level as the Default Input Folder.</li>
</ul></p>
"""

IO_WITH_METADATA_HELP_TEXT = """
For <i>%(ABSOLUTE_FOLDER_NAME)s</i>, <i>%(DEFAULT_INPUT_SUBFOLDER_NAME)s</i> and 
<i>%(DEFAULT_OUTPUT_SUBFOLDER_NAME)s</i>, if you have metadata associated with your 
images via <b>LoadImages</b> or <b>LoadData</b>, you can name the folder using metadata
tags."""%globals()

PREFERENCES_VERSION = 'PreferencesVersion'
PREFERENCES_VERSION_NUMBER = 1
DEFAULT_IMAGE_DIRECTORY = 'DefaultImageDirectory'
DEFAULT_OUTPUT_DIRECTORY = 'DefaultOutputDirectory'
TITLE_FONT_SIZE = 'TitleFontSize'
TITLE_FONT_NAME = 'TitleFontName'
TABLE_FONT_NAME = 'TableFontName'
TABLE_FONT_SIZE = 'TableFontSize'
BACKGROUND_COLOR = 'BackgroundColor'
PIXEL_SIZE = 'PixelSize'
COLORMAP = 'Colormap'
MODULEDIRECTORY = 'ModuleDirectory'
CHECKFORNEWVERSIONS = 'CheckForNewVersions'
SKIPVERSION = 'SkipVersion'
FF_RECENTFILES = 'RecentFile%d'
STARTUPBLURB = 'StartupBlurb'
RECENT_FILE_COUNT = 10
PRIMARY_OUTLINE_COLOR = 'PrimaryOutlineColor'
SECONDARY_OUTLINE_COLOR = 'SecondaryOutlineColor'
TERTIARY_OUTLINE_COLOR = 'TertiaryOutlineColor'
JVM_ERROR = 'JVMError'
ALLOW_OUTPUT_FILE_OVERWRITE = 'AllowOutputFileOverwrite'
PLUGIN_DIRECTORY = 'PluginDirectory'
IJ_PLUGIN_DIRECTORY = 'IJPluginDirectory'
SHOW_ANALYSIS_COMPLETE_DLG = "ShowAnalysisCompleteDlg"
SHOW_EXITING_TEST_MODE_DLG = "ShowExitingTestModeDlg"
SHOW_BAD_SIZES_DLG = "ShowBadSizesDlg"
SHOW_SAMPLING = "ShowSampling"
WRITE_MAT = "WriteMAT"
WARN_ABOUT_OLD_PIPELINE = "WarnAboutOldPipeline"
USE_MORE_FIGURE_SPACE = "UseMoreFigureSpace"
WRITE_HDF5 = "WriteHDF5"
WORKSPACE_FILE = "WorkspaceFile"
OMERO_SERVER = "OmeroServer"
OMERO_PORT = "OmeroPort"
OMERO_USER = "OmeroUser"
OMERO_SESSION_ID = "OmeroSessionId"
MAX_WORKERS = "MaxWorkers"
TEMP_DIR = "TempDir"
WORKSPACE_CHOICE = "WorkspaceChoice"
ERROR_COLOR = "ErrorColor"
INTERPOLATION_MODE = "InterpolationMode"

IM_NEAREST = "Nearest"
IM_BILINEAR = "Bilinear"
IM_BICUBIC = "Bicubic"

WC_SHOW_WORKSPACE_CHOICE_DIALOG = "ShowWorkspaceChoiceDlg"
WC_OPEN_LAST_WORKSPACE = "OpenLastWorkspace"
WC_CREATE_NEW_WORKSPACE = "CreateNewWorkspace"
WC_OPEN_OLD_WORKSPACE = "OpenOldWorkspace"

'''The preference key for selecting the correct version of ImageJ'''
IJ_VERSION = "ImageJVersion"
'''Use the enhanced version of ImageJ 1.44 with some support for @parameter'''
IJ_1 = "ImageJ 1.x"
'''Use ImageJ 2.0 with Imglib and new framework'''
IJ_2 = "ImageJ 2.0"

def recent_file(index, category=""):
    return (FF_RECENTFILES % (index + 1)) + category

'''All keys saved in the registry'''
ALL_KEYS = ([ALLOW_OUTPUT_FILE_OVERWRITE, BACKGROUND_COLOR, CHECKFORNEWVERSIONS,
             COLORMAP, DEFAULT_IMAGE_DIRECTORY, DEFAULT_OUTPUT_DIRECTORY,
             IJ_PLUGIN_DIRECTORY, MODULEDIRECTORY, PLUGIN_DIRECTORY,
             PRIMARY_OUTLINE_COLOR, SECONDARY_OUTLINE_COLOR,
             SHOW_ANALYSIS_COMPLETE_DLG, SHOW_BAD_SIZES_DLG, 
             SHOW_EXITING_TEST_MODE_DLG, WORKSPACE_CHOICE,
             SHOW_SAMPLING, SKIPVERSION, STARTUPBLURB,
             TABLE_FONT_NAME, TABLE_FONT_SIZE, TERTIARY_OUTLINE_COLOR,
             TITLE_FONT_NAME, TITLE_FONT_SIZE, WARN_ABOUT_OLD_PIPELINE,
             WRITE_MAT, USE_MORE_FIGURE_SPACE, WORKSPACE_FILE,
             OMERO_SERVER, OMERO_PORT, OMERO_USER] + 
            [recent_file(n, category) for n in range(RECENT_FILE_COUNT)
             for category in ("", 
                              DEFAULT_IMAGE_DIRECTORY, 
                              DEFAULT_OUTPUT_DIRECTORY,
                              WORKSPACE_FILE)])

def module_directory():
    if not config_exists(MODULEDIRECTORY):
        return os.path.join(cell_profiler_root_directory(), 'Modules')
    return str(config_read(MODULEDIRECTORY))

def set_module_directory(value):
    config_write(MODULEDIRECTORY, value)

def module_extension():
    return '.m'

__default_image_directory = None
def get_default_image_directory():
    global __default_image_directory
    if __default_image_directory is not None:
        return __default_image_directory
    # I'm not sure what it means for the preference not to exist.  No read-write preferences file?
    if not config_exists(DEFAULT_IMAGE_DIRECTORY):
        return os.path.abspath(os.path.expanduser('~'))
    # Fetch the default.  Note that it might be None
    default_image_directory = config_read(DEFAULT_IMAGE_DIRECTORY) or ''
    try:
        if os.path.isdir(default_image_directory):
            __default_image_directory = get_proper_case_filename(default_image_directory)
            return __default_image_directory
    except:
        logger.error("Unknown failure when retrieving the default image directory", exc_info=True)
    logger.warning("Warning: current path of %s is not a valid directory. Switching to home directory."%(default_image_directory.encode('ascii', 'replace')))
    # If the user's home directory is not ascii, we're not going to go hunting for one that is.
    # Fail ungracefully.
    default_image_directory = os.path.abspath(os.path.expanduser('~'))
    set_default_image_directory(default_image_directory)
    return str(get_proper_case_filename(default_image_directory))

def set_default_image_directory(path):
    global __default_image_directory
    __default_image_directory = path
    config_write(DEFAULT_IMAGE_DIRECTORY,path)
    add_recent_file(path, DEFAULT_IMAGE_DIRECTORY)
    fire_image_directory_changed_event()
    
def fire_image_directory_changed_event():
    '''Notify listeners of a image directory change'''
    global __default_image_directory
    for listener in __image_directory_listeners:
        listener(PreferenceChangedEvent(__default_image_directory))

__image_directory_listeners = []

def add_image_directory_listener(listener):
    """Add a listener that will be notified when the image directory changes
    
    """
    __image_directory_listeners.append(listener)
    
def remove_image_directory_listener(listener):
    """Remove a previously-added image directory listener
    
    """
    if listener in __image_directory_listeners:
        __image_directory_listeners.remove(listener)

class PreferenceChangedEvent:
    def __init__(self, new_value):
        self.new_value = new_value

__default_output_directory = None
def get_default_output_directory():
    global __default_output_directory
    if __default_output_directory is not None:
        return __default_output_directory
    if not config_exists(DEFAULT_OUTPUT_DIRECTORY):
        return os.path.abspath(os.path.expanduser('~'))

    # Fetch the default.  Note that it might be None
    default_output_directory = config_read(DEFAULT_OUTPUT_DIRECTORY) or ''
    try:
        if os.path.isdir(default_output_directory):
            __default_output_directory = get_proper_case_filename(default_output_directory)
            return __default_output_directory
    except:
        logger.error("Unknown failure when retrieving the default output directory", exc_info=True)
    logger.warning("Warning: current path of %s is not a valid directory. Switching to home directory."%(default_output_directory.encode('ascii', 'replace')))
    # If the user's home directory is not ascii, we're not going to go hunting for one that is.
    # Fail ungracefully.
    default_output_directory = os.path.abspath(os.path.expanduser('~'))
    set_default_output_directory(default_output_directory)
    return str(get_proper_case_filename(default_output_directory))

def set_default_output_directory(path):
    global __default_output_directory
    assert os.path.isdir(path),'Default Output Folder, "%s", is not a directory'%(path)
    __default_output_directory = path
    config_write(DEFAULT_OUTPUT_DIRECTORY,path)
    add_recent_file(path, DEFAULT_OUTPUT_DIRECTORY)
    for listener in __output_directory_listeners:
        listener(PreferenceChangedEvent(path))

__output_directory_listeners = []

def add_output_directory_listener(listener):
    """Add a listener that will be notified when the output directory changes
    
    """
    __output_directory_listeners.append(listener)
    
def remove_output_directory_listener(listener):
    """Remove a previously-added image directory listener
    
    """
    if listener in __output_directory_listeners:
        __output_directory_listeners.remove(listener)

def get_title_font_size():
    if not config_exists(TITLE_FONT_SIZE):
        return 12
    title_font_size = config_read(TITLE_FONT_SIZE)
    return float(title_font_size)

def set_title_font_size(title_font_size):
    config_write(TITLE_FONT_SIZE,str(title_font_size))

def get_title_font_name():
    if not config_exists(TITLE_FONT_NAME):
        return "Tahoma"
    return config_read(TITLE_FONT_NAME)

def set_title_font_name(title_font_name):
    config_write(TITLE_FONT_NAME, title_font_name)

def get_table_font_name():
    if not config_exists(TABLE_FONT_NAME):
        return "Tahoma"
    return config_read(TABLE_FONT_NAME)

def set_table_font_name(title_font_name):
    config_write(TABLE_FONT_NAME, title_font_name)
    
def get_table_font_size():
    if not config_exists(TABLE_FONT_SIZE):
        return 9
    table_font_size = config_read(TABLE_FONT_SIZE)
    return float(table_font_size)

def set_table_font_size(table_font_size):
    config_write(TABLE_FONT_SIZE,str(table_font_size))

def tuple_to_color(t, default = (0,0,0)):
    import wx
    try:
        return wx.Colour(red=int(t[0]), green = int(t[1]), blue = int(t[2]))
    except IndexError, ValueError:
        return tuple_to_color(default)

__background_color = None    
def get_background_color():
    '''Get the color to be used for window backgrounds
    
    Return wx.Colour that will be applied as
    the background for all frames and dialogs
    '''
    global __background_color
    if __background_color is not None:
        return __background_color
    default_color = (143, 188, 143) # darkseagreen
    if not config_exists(BACKGROUND_COLOR):
        __background_color = tuple_to_color(default_color)
    else:
        try:
            color = config_read(BACKGROUND_COLOR).split(',')
        except:
            logger.warn("Failed to read background color")
            traceback.print_exc()
            color = default_color
        __background_color = tuple_to_color(tuple(color), default_color)
    return __background_color

def set_background_color(color):
    '''Set the color to be used for window backgrounds
    
    '''
    global __background_color
    config_write(BACKGROUND_COLOR,
                 ','.join([str(x) for x in color.Get()]))
    __background_color = color
    
__error_color = None
def get_error_color():
    '''Get the color to be used for error text'''
    global __error_color
    #
    # Red found here: 
    # http://www.jankoatwarpspeed.com/css-message-boxes-for-different-message-types/
    # but seems to be widely used.
    #
    default_color = (0xD8, 0x00, 0x0C)
    if __error_color is None:
        if not config_exists(ERROR_COLOR):
            __error_color = tuple_to_color(default_color)
        else:
            color_string = config_read(ERROR_COLOR)
            try:
                __error_color = tuple_to_color(color_string.split(','))
            except:
                print "Failed to parse error color string: " + color_string
                traceback.print_exc()
                __error_color = default_color
    return __error_color

def set_error_color(color):
    '''Set the color to be used for error text
    
    color - a WX color or ducktyped
    '''
    global __error_color
    config_write(ERROR_COLOR,
                 ','.join([str(x) for x in color.Get()]))
    __error_color = tuple_to_color(color.Get())
            

def get_pixel_size():
    """The size of a pixel in microns"""
    if not config_exists(PIXEL_SIZE):
        return 1.0
    return float(config_read(PIXEL_SIZE))

def set_pixel_size(pixel_size):
    config_write(PIXEL_SIZE,str(pixel_size))

__output_filename = None
__output_filename_listeners = []
def get_output_file_name():
    global __output_filename
    if __output_filename is None:
        return 'DefaultOUT.mat'
    return __output_filename

def set_output_file_name(filename):
    global __output_filename
    filename=str(filename)
    __output_filename = filename
    for listener in __output_filename_listeners:
        listener(PreferenceChangedEvent(filename))

def add_output_file_name_listener(listener):
    __output_filename_listeners.append(listener)

def remove_output_file_name_listener(listener):
    try:
        __output_filename_listeners.remove(listener)
    except:
        logger.warn("File name listener doubly removed")

def get_absolute_path(path, abspath_mode = ABSPATH_IMAGE):
    """Convert a path into an absolute path using the path conventions
    
    If a path starts with http:, https: or ftp:, leave it unchanged.
    If a path starts with "./", then make the path relative to the
    Default Output Folder.
    If a path starts with "&/", then make the path relative to the
    Default Input Folder.
    If a "path" has no path component then make the path relative to
    the Default Output Folder.
    """
    if abspath_mode == ABSPATH_OUTPUT:
        osep = '.'
        isep = '&'
    elif abspath_mode == ABSPATH_IMAGE:
        osep = '&'
        isep = '.'
    else:
        raise ValueError("Unknown abspath mode: %s"%abspath_mode)
    if is_url_path(path):
        return path
    if (path.startswith(osep+os.path.sep) or
        ("altsep" in os.path.__all__ and os.path.altsep and
         path.startswith(osep+os.path.altsep))):
        return os.path.join(get_default_output_directory(), path[2:])
    elif (path.startswith(isep+os.path.sep) or
          ("altsep" in os.path.__all__ and os.path.altsep and
           path.startswith(isep+os.path.altsep))):
        return os.path.join(get_default_image_directory(), path[2:])
    elif len(os.path.split(path)[0]) == 0:
        return os.path.join(get_default_output_directory(), path)
    else:
        return str(get_proper_case_filename(os.path.abspath(path)))

def is_url_path(path):
    '''Return True if the path should be treated as a URL'''
    for protocol in ('http','https','ftp'):
        if path.lower().startswith('%s:' % protocol):
            return True
    return False

__default_colormap = None
def get_default_colormap():
    global __default_colormap
    if __default_colormap is None:
        if not config_exists(COLORMAP):
            __default_colormap = 'jet'
        else:
            __default_colormap = config_read(COLORMAP)
    return __default_colormap

def set_default_colormap(colormap):
    global __default_colormap
    __default_colormap = colormap
    config_write(COLORMAP, colormap)

__current_workspace_path = None
def get_current_workspace_path():
    global __current_workspace_path
    return __current_workspace_path

def set_current_workspace_path(path):
    global __current_workspace_path
    __current_workspace_path = path

def get_check_new_versions():
    if not config_exists(CHECKFORNEWVERSIONS):
        # should this check for whether we can actually save preferences?
        return True
    return get_config().ReadBool(CHECKFORNEWVERSIONS)
    
def set_check_new_versions(val):
    old_val = get_check_new_versions()
    get_config().WriteBool(CHECKFORNEWVERSIONS, bool(val))
    # If the user turns on version checking, they probably don't want
    # to skip versions anymore.
    if val and (not old_val):
        set_skip_version(0)
    

def get_skip_version():
    if not config_exists(SKIPVERSION):
        return 0
    return get_config().ReadInt(SKIPVERSION)

def set_skip_version(ver):
    get_config().WriteInt(SKIPVERSION, ver)
    

__show_sampling = None
def get_show_sampling():
    global __show_sampling
    if __show_sampling is not None:
        return __show_sampling
    if not config_exists(SHOW_SAMPLING):
        __show_sampling = False
        return False
    return get_config().ReadBool(SHOW_SAMPLING)

def set_show_sampling(value):
    global __show_sampling
    get_config().WriteBool(SHOW_SAMPLING, bool(value))
    __show_sampling = bool(value)

__recent_files = {}
def get_recent_files(category=""):
    global __recent_files
    if __recent_files.get(category, None) is None:
        __recent_files[category] = []
        for i in range(RECENT_FILE_COUNT):
            key = recent_file(i, category)
            try:
                if config_exists(key):
                    __recent_files[category].append(config_read(key)) 
            except:
                pass
    return __recent_files[category]

def add_recent_file(filename, category=""):
    recent_files = get_recent_files(category)
    filename = os.path.abspath(filename)
    if filename in recent_files:
        recent_files.remove(filename)
    recent_files.insert(0, filename)
    if len(recent_files) > RECENT_FILE_COUNT:
        del recent_files[-1]
    for i, filename in enumerate(recent_files):
        config_write(recent_file(i, category), filename)

__plugin_directory = None
def get_plugin_directory():
    global __plugin_directory
    
    if __plugin_directory is not None:
        return __plugin_directory
    
    if config_exists(PLUGIN_DIRECTORY):
        __plugin_directory = config_read(PLUGIN_DIRECTORY)
    elif get_headless():
        return None
    else:
        import wx
        if wx.GetApp() is not None:
            __plugin_directory = os.path.join(wx.StandardPaths.Get().GetUserDataDir(), 'plugins')
    return __plugin_directory

def set_plugin_directory(value):
    global __plugin_directory
    
    __plugin_directory = value
    config_write(PLUGIN_DIRECTORY, value)

__ij_plugin_directory = None
def get_ij_plugin_directory():
    global __ij_plugin_directory
    
    if __ij_plugin_directory is not None:
        return __ij_plugin_directory
    
    if config_exists(IJ_PLUGIN_DIRECTORY):
        __ij_plugin_directory = config_read(IJ_PLUGIN_DIRECTORY)
    else:
        # The default is the startup directory
        return os.path.abspath(os.path.join(os.curdir, "plugins"))
    return __ij_plugin_directory

def set_ij_plugin_directory(value):
    global __ij_plugin_directory
    
    __ij_plugin_directory = value
    config_write(IJ_PLUGIN_DIRECTORY, value)

__data_file=None

def get_data_file():
    '''Get the path to the LoadData data file specified on the command-line'''
    global __data_file
    return __data_file

def set_data_file(path):
    global __data_file
    __data_file = path

def standardize_default_folder_names(setting_values,slot):
    if setting_values[slot] in FOLDER_CHOICE_TRANSLATIONS.keys():
        replacement = FOLDER_CHOICE_TRANSLATIONS[setting_values[slot]]
    elif (setting_values[slot].startswith("Default Image") or 
          setting_values[slot].startswith("Default image") or 
          setting_values[slot].startswith("Default input")):
        replacement = DEFAULT_INPUT_FOLDER_NAME
    elif setting_values[slot].startswith("Default output"):
        replacement = DEFAULT_OUTPUT_FOLDER_NAME
    else:
        replacement = setting_values[slot]
    setting_values = (setting_values[:slot] +
                        [replacement] +
                        setting_values[slot+1:])
    return setting_values

__cpfigure_position = (-1,-1)
def get_next_cpfigure_position(update_next_position=True):
    global __cpfigure_position
    pos = __cpfigure_position
    if update_next_position:
        update_cpfigure_position()
    return pos

def reset_cpfigure_position():
    global __cpfigure_position
    __cpfigure_position = (-1,-1)
    
def update_cpfigure_position():
    '''Called by get_next_cpfigure_position to update the screen position at 
    which the next figure frame will be drawn.
    '''
    global __cpfigure_position
    import wx
    win_size = (600,400)
    try:
        disp = wx.GetDisplaySize()
    except:
        disp = (800,600)
    if (__cpfigure_position[0] + win_size[0] > disp[0]):
        __cpfigure_position = (-1, __cpfigure_position[1])
    if (__cpfigure_position[1] + win_size[1] > disp[1]):
        __cpfigure_position = (-1, -1)
    else:
        # These offsets could be set in the preferences UI
        __cpfigure_position = (__cpfigure_position[0] + 120,
                               __cpfigure_position[1] + 24)
    
def get_startup_blurb():
    if not config_exists(STARTUPBLURB):
        return True
    return get_config().ReadBool(STARTUPBLURB)

def set_startup_blurb(val):
    get_config().WriteBool(STARTUPBLURB, val)

def get_primary_outline_color():
    default = (0,255,0)
    if not config_exists(PRIMARY_OUTLINE_COLOR):
        return tuple_to_color(default)
    return tuple_to_color(config_read(PRIMARY_OUTLINE_COLOR).split(","))

def set_primary_outline_color(color):
    config_write(PRIMARY_OUTLINE_COLOR,
                       ','.join([str(x) for x in color.Get()]))

def get_secondary_outline_color():
    default = (255,0,255)
    if not config_exists(SECONDARY_OUTLINE_COLOR):
        return tuple_to_color(default)
    return tuple_to_color(config_read(SECONDARY_OUTLINE_COLOR).split(","))

def set_secondary_outline_color(color):
    config_write(SECONDARY_OUTLINE_COLOR,
                       ','.join([str(x) for x in color.Get()]))

def get_tertiary_outline_color():
    default = (255,255,0)
    if not config_exists(TERTIARY_OUTLINE_COLOR):
        return tuple_to_color(default)
    return tuple_to_color(config_read(TERTIARY_OUTLINE_COLOR).split(","))

def set_tertiary_outline_color(color):
    config_write(TERTIARY_OUTLINE_COLOR,
                       ','.join([str(x) for x in color.Get()]))

__has_reported_jvm_error = False

def get_report_jvm_error():
    '''Return true if user still wants to report a JVM error'''
    if __has_reported_jvm_error:
        return False
    if not config_exists(JVM_ERROR):
        return True
    return config_read(JVM_ERROR) == "True"

def set_report_jvm_error(should_report):
    config_write(JVM_ERROR, "True" if should_report else "False")

def set_has_reported_jvm_error():
    '''Call this to remember that we showed the user the JVM error'''
    global __has_reported_jvm_error
    __has_reported_jvm_error = True
    
__allow_output_file_overwrite = None

def get_allow_output_file_overwrite():
    '''Return true if the user wants to allow CP to overwrite the output file
    
    This is the .MAT output file, typically Default_OUT.mat
    '''
    global __allow_output_file_overwrite
    if __allow_output_file_overwrite is not None:
        return __allow_output_file_overwrite
    if not config_exists(ALLOW_OUTPUT_FILE_OVERWRITE):
        return False
    return config_read(ALLOW_OUTPUT_FILE_OVERWRITE) == "True"

def set_allow_output_file_overwrite(value):
    '''Allow overwrite of .MAT file if true, warn user if false'''
    global __allow_output_file_overwrite
    __allow_output_file_overwrite = value
    config_write(ALLOW_OUTPUT_FILE_OVERWRITE, 
                       "True" if value else "False")

# "Analysis complete" preference
__show_analysis_complete_dlg = None

def get_show_analysis_complete_dlg():
    '''Return true if the user wants to see the "analysis complete" dialog'''
    global __show_analysis_complete_dlg
    if __show_analysis_complete_dlg is not None:
        return __show_analysis_complete_dlg
    if not config_exists(SHOW_ANALYSIS_COMPLETE_DLG):
        return True
    return config_read(SHOW_ANALYSIS_COMPLETE_DLG) == "True"

def set_show_analysis_complete_dlg(value):
    '''Set the "show analysis complete" flag'''
    global __show_analysis_complete_dlg
    __show_analysis_complete_dlg = value
    config_write(SHOW_ANALYSIS_COMPLETE_DLG, 
                       "True" if value else "False")

# "Existing test mode" preference
__show_exiting_test_mode_dlg = None

def get_show_exiting_test_mode_dlg():
    '''Return true if the user wants to see the "exiting test mode" dialog'''
    global __show_exiting_test_mode_dlg
    if __show_exiting_test_mode_dlg is not None:
        return __show_exiting_test_mode_dlg
    if not config_exists(SHOW_EXITING_TEST_MODE_DLG):
        return True
    return config_read(SHOW_EXITING_TEST_MODE_DLG) == "True"

def set_show_exiting_test_mode_dlg(value):
    '''Set the "exiting test mode" flag'''
    global __show_exiting_test_mode_dlg
    __show_exiting_test_mode_dlg = value
    config_write(SHOW_EXITING_TEST_MODE_DLG, 
                       "True" if value else "False")

# "Report bad sizes" preference
__show_report_bad_sizes_dlg = None

def get_show_report_bad_sizes_dlg():
    '''Return true if the user wants to see the "report bad sizes" dialog'''
    global __show_report_bad_sizes_dlg
    if __show_report_bad_sizes_dlg is not None:
        return __show_report_bad_sizes_dlg
    if not config_exists(SHOW_BAD_SIZES_DLG):
        return True
    return config_read(SHOW_BAD_SIZES_DLG) == "True"

def set_show_report_bad_sizes_dlg(value):
    '''Set the "exiting test mode" flag'''
    global __show_report_bad_sizes_dlg
    __show_report_bad_sizes_dlg = value
    config_write(SHOW_BAD_SIZES_DLG, 
                       "True" if value else "False")

# Write .MAT files on output
__write_MAT_files = None

def get_write_MAT_files():
    '''Determine whether to write measurements in .MAT files, .h5 files or not at all

    returns True to write .MAT, WRITE_HDF5 to write .h5 files, False to not write
    '''
    global __write_MAT_files
    if __write_MAT_files is not None:
        return __write_MAT_files
    if not config_exists(WRITE_MAT):
        return False
    value = config_read(WRITE_MAT)
    if value == "True":
        return True
    if value == WRITE_HDF5:
        return WRITE_HDF5
    return False

def set_write_MAT_files(value):
    '''Set the "Write MAT files" flag'''
    global __write_MAT_files
    __write_MAT_files = value
    config_write(WRITE_MAT,
                 WRITE_HDF5 if value == WRITE_HDF5
                 else "True" if value else "False")

__warn_about_old_pipeline = None
def get_warn_about_old_pipeline():
    '''Return True if CP should warn the user about old SVN revision pipelines'''
    global __warn_about_old_pipeline
    if __warn_about_old_pipeline is not None:
        return __warn_about_old_pipeline
    if not config_exists(WARN_ABOUT_OLD_PIPELINE):
        return True
    return config_read(WARN_ABOUT_OLD_PIPELINE) == "True"

def set_warn_about_old_pipeline(value):
    '''Set the "warn about old pipelines" flag'''
    global __warn_about_old_pipeline
    __warn_about_old_pipeline = value
    config_write(WARN_ABOUT_OLD_PIPELINE,
                       "True" if value else "False")

__use_more_figure_space = None
def get_use_more_figure_space():
    '''Return True if CP should use more of the figure space'''
    global __use_more_figure_space
    if __use_more_figure_space is not None:
        return __use_more_figure_space
    if not config_exists(USE_MORE_FIGURE_SPACE):
        return False
    return config_read(USE_MORE_FIGURE_SPACE) == "True"

def set_use_more_figure_space(value):
    '''Set the "use more figure space" flag'''
    global __use_more_figure_space
    __use_more_figure_space = value
    config_write(USE_MORE_FIGURE_SPACE,
                       "True" if value else "False")

__ij_version = None
def get_ij_version():
    '''Return an indicator of which version of ImageJ to use
    
    returns one of IJ_1 or IJ_2.
    
    This determines whether to use the ImageJ 1.44 version, enhanced
    with the @parameter decoration or to use the new and experimental
    ImageJ 2.0 codebase.
    '''
    global __ij_version
    if __ij_version is not None:
        return __ij_version
    if not config_exists(IJ_VERSION):
        return IJ_1
    result = config_read(IJ_VERSION)
    return IJ_1 if result not in (IJ_1, IJ_2) else result

def set_ij_version(value):
    '''Set the ImageJ version to use
    
    value: one of IJ_1 or IJ_2
    '''
    global __ij_version
    assert value in (IJ_1, IJ_2)
    __ij_version = value
    config_write(IJ_VERSION, value)

__workspace_file = None
def get_workspace_file():
    '''Return the path to the workspace file'''
    global __workspace_file
    if __workspace_file is not None:
        return __workspace_file
    if not config_exists(WORKSPACE_FILE):
        return None
    __workspace_file = config_read(WORKSPACE_FILE)
    return __workspace_file

def set_workspace_file(path, permanently = True):
    '''Set the path to the workspace file

    path - path to the file
    
    permanently - True to write it to the configuration, False if the file
                  should only be set for the running instance (e.g. as a
                  command-line parameter for a scripted run)
    '''
    global __workspace_file
    __workspace_file = path
    if permanently:
        add_recent_file(path, WORKSPACE_FILE)
        config_write(WORKSPACE_FILE, path)

###########################################
#
# OMERO logon credentials
#
###########################################

__omero_server = None
__omero_port = None
__omero_user = None
__omero_session_id = None

def get_omero_server():
    '''Get the DNS name of the Omero server'''
    global __omero_server
    if __omero_server is None:
        if not config_exists(OMERO_SERVER):
            return None
        __omero_server = config_read(OMERO_SERVER)
    return __omero_server

def set_omero_server(omero_server):
    '''Set the DNS name of the Omero server'''
    global __omero_server
    __omero_server = omero_server
    config_write(OMERO_SERVER, omero_server)
    
def get_omero_port():
    '''Get the port used to connect to the Omero server'''
    global __omero_port
    if __omero_port is None:
        if not config_exists(OMERO_PORT):
            return 4064
        try:
            __omero_port = int(config_read(OMERO_PORT))
        except:
            return 4064
    return __omero_port

def set_omero_port(omero_port):
    '''Set the port used to connect to the Omero server'''
    global __omero_port
    __omero_port = omero_port
    config_write(OMERO_PORT, str(omero_port))
    
def get_omero_user():
    '''Get the Omero user name'''
    global __omero_user
    if __omero_user is None:
        if not config_exists(OMERO_USER):
            return None
        __omero_user = config_read(OMERO_USER)
    return __omero_user

def set_omero_user(omero_user):
    '''Set the Omero user name'''
    global __omero_user
    __omero_user = omero_user
    config_write(OMERO_USER, omero_user)
    
def get_omero_session_id():
    '''Get the session ID to use to communicate to Omero'''
    global __omero_session_id
    if __omero_session_id is None:
        if not config_exists(OMERO_SESSION_ID):
            return None
        __omero_session_id = config_read(OMERO_SESSION_ID)
    return __omero_session_id

def set_omero_session_id(omero_session_id):
    '''Set the Omero session ID'''
    global __omero_session_id
    __omero_session_id = omero_session_id
    config_write(OMERO_SESSION_ID, omero_session_id)

def default_max_workers():
    try:
        return multiprocessing.cpu_count()
    except:
        return 4
    
__max_workers = None
def get_max_workers():
    '''Get the maximum number of worker processes allowed during analysis'''
    global __max_workers
    if __max_workers is not None:
        return __max_workers
    default = default_max_workers()
    if config_exists(MAX_WORKERS):
        __max_workers = get_config().ReadInt(MAX_WORKERS, default)
        return __max_workers
    return default

def set_max_workers(value):
    '''Set the maximum number of worker processes allowed during analysis'''
    global __max_workers
    get_config().WriteInt(MAX_WORKERS, value)
    __max_workers = value

__temp_dir = None
def get_temporary_directory():
    '''Get the directory to be used for temporary files
    
    The default is whatever is returned by tempfile.gettempdir()
    (see http://docs.python.org/2/library/tempfile.html#tempfile.gettempdir)
    '''
    global __temp_dir
    if __temp_dir is not None:
        pass
    elif config_exists(TEMP_DIR):
        __temp_dir = config_read(TEMP_DIR)
    else:
        __temp_dir = tempfile.gettempdir()
    return __temp_dir

def set_temporary_directory(tempdir):
    '''Set the directory to be used for temporary files
    
    tempdir - pathname of the directory
    '''
    global __temp_dir
    config_write(TEMP_DIR, tempdir)
    __temp_dir = tempdir

__progress_data = threading.local()
__progress_data.last_report = time.time()
__progress_data.callbacks = None
__interpolation_mode = None
def get_interpolation_mode():
    '''Get the interpolation mode for matplotlib
    
    Returns one of IM_NEAREST, IM_BILINEAR or IM_BICUBIC
    '''
    global __interpolation_mode
    if __interpolation_mode is not None:
        return __interpolation_mode
    if config_exists(INTERPOLATION_MODE):
        __interpolation_mode = config_read(INTERPOLATION_MODE)
    else:
        __interpolation_mode = IM_NEAREST
    return __interpolation_mode

def set_interpolation_mode(value):
    global __interpolation_mode
    __interpolation_mode = value
    config_write(INTERPOLATION_MODE, value)
    
def add_progress_callback(callback):
    '''Add a callback function that listens to progress calls
    
    The progress indicator is designed to monitor progress of operations
    on the user interface thread. The model is that operations are nested
    so that both an operation and sub-operation can report their progress.
    An operation reports its initial progress and is pushed onto the
    stack at that point. When it reports 100% progress, it's popped from
    the stack.
    
    callback - callback function with signature of 
               fn(operation_id, progress, message)
               where operation_id names the instance of the operation being
               performed (e.g. a UUID), progress is a number between 0 and 1
               where 1 indicates that the operation has completed and
               message is the message to show.
               
               Call the callback with operation_id = None to pop the operation
               stack after an exception.
               
    Note that the callback must remain in-scope. For example:
    
    class Foo():
       def callback(operation_id, progress, message):
          ...
          
    works but
    
    class Bar():
        def __init__(self):
            def callback(operation_id, progress, message):
                ...
            
    does not work because the reference is lost when __init__ returns.
    '''
    global __progress_data
    if __progress_data.callbacks is None:
        __progress_data.callbacks = weakref.WeakSet()
    __progress_data.callbacks.add(callback)
    
def remove_progress_callback(callback):
    global __progress_data
    if (__progress_data.callbacks is not None and 
        callback in __progress_data.callbacks):
        __progress_data.callbacks.remove(callback)
    
def report_progress(operation_id, progress, message):
    '''Report progress to all callbacks registered on the caller's thread
    
    operation_id - ID of operation being performed
    
    progress - a number between 0 and 1 indicating the extent of progress.
               None indicates indeterminate operation duration. 0 should be
               reported at the outset and 1 at the end.
               
    message - an informative message.
    '''
    global __progress_data
    if __progress_data.callbacks is None:
        return
    t = time.time()
    if progress in (None, 0, 1) or t - __progress_data.last_report > 1:
        for callback in __progress_data.callbacks:
            callback(operation_id, progress, message)
        __progress_data.last_report = time.time()
        
def map_report_progress(fn_map, fn_report, sequence, freq=None):
    '''Apply a mapping function to a sequence, reporting progress
    
    fn_map - function that maps members of the sequence to members of the output
    
    fn_report - function that takes a sequence member and generates an
                informative string
                
    freq - report on mapping every N items. Default is to report 100 or less
           times.
    '''
    n_items = len(sequence)
    if n_items == 0:
        return []
    if freq == None:
        if n_items < 100:
            freq = 1
        else:
            freq = (n_items + 99) / 100
    output = []
    uid = uuid.uuid4()
    for i in range(0, n_items, freq):
        report_progress(uuid, float(i) / n_items, fn_report(sequence[i]))
        output += map(fn_map, sequence[i:i+freq])
    report_progress(uuid, 1, "Done")
    return output
        
def cancel_progress():
    '''Cancel all progress indicators
    
    for instance, after an exception is thrown that bubbles to the top.
    '''
    report_progress(None, None, None)
