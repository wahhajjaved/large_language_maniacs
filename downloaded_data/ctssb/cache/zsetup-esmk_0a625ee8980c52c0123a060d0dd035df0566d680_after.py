# import modules
import os

import glob
import re

from osgeo import gdal
from osgeo.gdalconst import *
gdal.TermProgress = gdal.TermProgress_nocb


def ParseType(type):
    if type == 'Byte':
        return GDT_Byte
    elif type == 'Int16':
        return GDT_Int16
    elif type == 'UInt16':
        return GDT_UInt16
    elif type == 'Int32':
        return GDT_Int32
    elif type == 'UInt32':
        return GDT_UInt32
    elif type == 'Float32':
        return GDT_Float32
    elif type == 'Float64':
        return GDT_Float64
    elif type == 'CInt16':
        return GDT_CInt16
    elif type == 'CInt32':
        return GDT_CInt32
    elif type == 'CFloat32':
        return GDT_CFloat32
    elif type == 'CFloat64':
        return GDT_CFloat64
    else:
        return GDT_Byte


class ParseError(Exception):
    """ Customized error class caused if name and template parsing fails.

    INPUTS:
    value (str): error message to be delivered.

    METHODS:
    __str__: returns error message for printing.
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value


class ParsedFileName(object):

    def __init__(self, name, template):
        self.__name = os.path.basename(name)
        self.__path = name
        self.__template = template
        self.__tags = {}
        self.__order = []
        self.parse()

    def __str__(self):
        return self.name

    def parse(self):
        # Parse the template
        # Standard regex to find HTML tags
        re_tag = re.compile('(\<(/?[^\>]+)\>)', re.IGNORECASE)
        tags = re_tag.findall(self.template)

        # Get the separators
        re_sep = re.compile('((?<=>))(.(?=<))')
        seps = re_sep.findall(self.template)

        extension = ''
        separator = ''

        if '.' in self.name:
            re_ext = re.compile(r'\.([A-Za-z0-9-]+)')
            extensions = re_ext.findall(self.name)
            assert len(extensions) == 1, 'More than 1 extension found: %s' \
                                         % extensions
            # FIXME: the dot should be part of the regex
            extension = '.' + extensions[0]
            self.set_tag('EXT', extension)

        # Separators*should* be the same, but strictly
        # they don't have to
        if seps:
            separator = seps[0][1]
            name_body = self.name.replace(extension, '')
            components = name_body.split(separator)
        else:
            # No separator provided, template must be followed literally
            raise NotImplementedError("Name templating without separator " +
                                      "not supported.")

        self.set_tag('SEP', separator)

        if len(components) != len(tags):
            raise ParseError("Template %s and name %s don't match" %
                            (self.template, self.name))

        # Fill tag values with current components
        for tag, component in zip(tags, components):
            self.__order.append(tag[1])
            self.set_tag(tag[1], component)

    @property
    def body(self):
        value = []
        for i, item in enumerate(self.__order):
            if 'BODY' in item:
                value.append(self.get_tag(item))

        return self.separator.join(value)

    @property
    def extension(self):
        return self.get_tag('EXT')

    @property
    def name(self):
        return self.__name

    @property
    def path(self):
        return self.__path

    @property
    def separator(self):
        return self.get_tag('SEP')

    @property
    def tags(self):
        return self.__tags

    def get_tag(self, token):
        if type(token) == str or type(token) == unicode:
            if token in self.__tags.keys():
                return self.__tags[token]
            else:
                return None
        elif type(token) == int:
            if token >= 0 and token <= len(self.__order):
                return self.__order[token]
            else:
                return None

    def get_tags(self, tokens):
        if type(tokens) == list or type(tokens) == tuple:
            tags = []
            for token in tokens:
                if type(token) == str or type(token) == unicode:
                    if token in self.__tags.keys():
                        tags.append(self.__tags[token])
                elif type(token) == int:
                    if token >= 0 and token <= len(self.__order):
                        tags.append(self.__order[token])
            return tags
        else:
            raise ValueError("Token must be either a list or a tuple")

    def get_template(self):
        return self.__template

    def set_tag(self, key, value):
        self.__tags[key] = value

    def set_template(self, value):
        self.__template = value

    template = property(get_template, set_template, None,
                        "template's docstring")


def create_output_name(name, prefix='index'):
    extension = name.split('.')[-1]
    name = name.replace('.' + extension, '')
    # HACK!!! This needs to be taken care properly, USE TEMPLATES
    name = '_'.join(name.split('_')[0:4])
    name = prefix + '_' + name + '.' + extension
    return name


def list_rasters(indir, formats, sorted=False):
    #os.chdir(dir)
    files = []
    for format in formats:
        temp_files = glob.glob(os.path.join(indir, '*.' + format))
        for _file in temp_files:
            files.append(os.path.join(indir, _file))
    if sorted:
        files.sort()
    return files
