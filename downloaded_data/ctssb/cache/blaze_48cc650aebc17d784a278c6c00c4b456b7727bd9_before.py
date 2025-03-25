from __future__ import absolute_import
# This file defines the Concrete Array --- a leaf node in the expression graph
#
# A concrete array is constructed from a Data Descriptor Object which handles the
#  indexing and basic interpretation of bytes
#

from . import blz
import numpy as np
from .datashape import dshape
from .datadescriptor import (IDataDescriptor,
                NumPyDataDescriptor,
                BLZDataDescriptor)
from ._printing import array2string

# An Array contains:
#   DataDescriptor
#       Sequence of Bytes (where are the bytes)
#       Index Object (how do I get to them)
#       Data Shape Object (what are the bytes? how do I interpret them)
#
#   axis and dimension labels 
#   user-defined meta-data (whatever are needed --- provenance propagation)
class Array(object):

    @property
    def dshape(self):
        return self._data.dshape

    def __iter__(self, iter):
        return self._data.__iter__()

    def __getitem__(self, key):
        return self._data.__getitem__(key)

    def __len__(self):
        return self._data.dshape[0]

    def __str__(self):
        return array2string(self._data)

    def __init__(self, data, axes=None, labels=None, user={}):
        if not isinstance(data, IDataDescriptor):
            raise TypeError(('Constructing a blaze array directly '
                            'requires a data descriptor, not type '
                            '%r') % (type(data)))
        self._data = data
        self.axes = axes or [''] * (len(self._data.dshape) - 1)
        self.labels = labels or [None] * (len(self._data.dshape) - 1)
        self.user = user

        # Need to inject attributes on the Array depending on dshape attributes

"""
These should be functions

    @staticmethod
    def fromfiles(list_of_files, converters):
        raise NotImplementedError

    @staticmethod
    def fromfile(file, converter):
        raise NotImplementedError

    @staticmethod
    def frombuffers(list_of_buffers, converters):
        raise NotImplementedError

    @staticmethod
    def frombuffer(buffer, converter):
        raise NotImplementedError

    @staticmethod
    def fromobjects():
        raise NotImplementedError

    @staticmethod
    def fromiterator(buffer):
        raise NotImplementedError

"""
        
