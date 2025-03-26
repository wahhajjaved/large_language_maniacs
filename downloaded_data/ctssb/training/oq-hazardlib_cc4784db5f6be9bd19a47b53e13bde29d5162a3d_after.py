# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (C) 2015-2016 GEM Foundation

# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.

import ast
import pydoc
import collections
import numpy
import h5py


class Hdf5Dataset(object):
    """
    Little wrapper around an (extendable) HDF5 dataset. Extendable datasets
    are useful for logging information incrementally into an HDF5 file.
    """
    @classmethod
    def create(cls, hdf5, name, dtype, shape=None, compression=None):
        """
        :param hdf5: a h5py.File object
        :param name: an hdf5 key string
        :param dtype: dtype of the dataset (usually composite)
        :param shape: shape of the dataset (if None, the dataset is extendable)
        :param compression: None or 'gzip' are recommended
        """
        if shape is None:  # extendable dataset
            dset = hdf5.create_dataset(
                name, (0,), dtype, chunks=True, maxshape=(None,))
        else:  # fixed-shape dataset
            dset = hdf5.create_dataset(name, shape, dtype)
        return cls(dset)

    def __init__(self, dset):
        self.dset = dset
        self.file = dset.file
        self.name = dset.name
        self.dtype = dset.dtype
        self.attrs = dset.attrs
        self.length = len(dset)

    def extend(self, array):
        """
        Extend the dataset with the given array, which must have
        the expected dtype. This method will give an error if used
        with a fixed-shape dataset.
        """
        newlength = self.length + len(array)
        self.dset.resize((newlength,))
        self.dset[self.length:newlength] = array
        self.length = newlength

    def append(self, tup):
        """
        Append a compatible tuple of data to the underlying dataset
        """
        self.extend(numpy.array([tup], self.dtype))


def extend(dset, array):
    """
    Extend an extensible dataset with an array of a compatible dtype
    """
    length = len(dset)
    newlength = length + len(array)
    dset.resize((newlength,))
    dset[length:newlength] = array


class LiteralAttrs(object):
    """
    A class to serialize attributes to HDF5. The goal is to store simple
    parameters as an HDF5 table in a readable way. The attributes are
    expected to be short, i.e. the names must be under 50 chars and
    and the length of their string representation under 200 chars.
    This is customizable by overriding the class variables KEYLEN
    and VALUELEN respectively.
    The implementation treats specially dictionary attributes, by
    storing them as `attrname.keyname` strings, see the example below:

    >>> class Ser(LiteralAttrs):
    ...     def __init__(self, a, b):
    ...         self.a = a
    ...         self.b = b
    >>> ser = Ser(1, dict(x='xxx', y='yyy'))
    >>> arr, attrs = ser.__toh5__()
    >>> for k, v in arr:
    ...     print('%s=%s' % (k.decode('utf8'), v.decode('utf8')))
    a=1
    b.x='xxx'
    b.y='yyy'
    >>> s = object.__new__(Ser)
    >>> s.__fromh5__(arr, attrs)
    >>> s.a
    1
    >>> s.b['x']
    'xxx'

    The implementation is not recursive, i.e. there will be at most
    one dot in the serialized names (in the example here `a`, `b.x`, `b.y`).
    """
    KEYLEN = 50
    VALUELEN = 200

    def _check_len(self, key, value):
        """
        Check the lengths of `key` and `value` and raise a ValueError if they
        are too long. Otherwise, returns the pair (key, value).
        """
        if len(key) > self.KEYLEN:
            raise ValueError(
                'An instance of Serializable cannot have '
                'public attributes longer than %d chars; '
                '%r has %d chars' % (self.KEYLEN, key, len(key)))
        rep = repr(value)
        if len(rep) > self.VALUELEN:
            raise ValueError(
                'Attribute %s=%s too long: %d > %d' %
                (key, rep, len(rep), self.VALUELEN))
        return key, rep

    def __toh5__(self):
        info_dt = numpy.dtype([('key', (bytes, self.KEYLEN)),
                               ('value', (bytes, self.VALUELEN))])
        attrnames = sorted(a for a in vars(self) if not a.startswith('_'))
        lst = []
        for attr in attrnames:
            value = getattr(self, attr)
            if isinstance(value, dict):
                for k, v in sorted(value.items()):
                    key = '%s.%s' % (attr, k)
                    lst.append(self._check_len(key, v))
            else:
                lst.append(self._check_len(attr, value))
        return numpy.array(lst, info_dt), {}

    def __fromh5__(self, array, attrs):
        dd = collections.defaultdict(dict)
        for (name, literal) in array:
            name = name.decode('utf8')
            if '.' in name:
                k1, k2 = name.split('.', 1)
                dd[k1][k2] = ast.literal_eval(literal.decode('utf8'))
            else:
                dd[name] = ast.literal_eval(literal.decode('utf8'))
        vars(self).update(dd)


class File(h5py.File):
    """
    Subclass of :class:`h5py.File` able to store and retrieve objects
    conforming to the HDF5 protocol used by the OpenQuake software.
    It works recursively also for dictionaries of the form name->obj.

    >>> f = File('/tmp/x.h5', 'w')
    >>> f['dic'] = dict(a=dict(x=1, y=2), b=3)
    >>> dic = f['dic']
    >>> dic['a']['x'].value
    1
    >>> dic['b'].value
    3
    >>> f.close()
    """
    def __setitem__(self, path, obj):
        cls = obj.__class__
        if hasattr(obj, '__toh5__'):
            obj, attrs = obj.__toh5__()
            pyclass = '%s.%s' % (cls.__module__, cls.__name__)
        else:
            pyclass = ''
        if isinstance(obj, dict):
            for k, v in sorted(obj.items()):
                key = '%s/%s' % (path, k)
                self[key] = v
        else:
            super(File, self).__setitem__(path, obj)
        a = super(File, self).__getitem__(path).attrs
        if pyclass:
            a['__pyclass__'] = pyclass
            for k, v in sorted(attrs.items()):
                a[k] = v

    def __getitem__(self, path):
        h5obj = super(File, self).__getitem__(path)
        h5attrs = h5obj.attrs
        if '__pyclass__' in h5attrs:
            cls = pydoc.locate(h5attrs['__pyclass__'])
            obj = cls.__new__(cls)
            if not hasattr(h5obj, 'shape'):  # is group
                h5obj = {k: self['%s/%s' % (path, k)]
                         for k, v in h5obj.items()}
            obj.__fromh5__(h5obj, h5attrs)
            return obj
        else:
            return h5obj

    def __delitem__(self, key):
        if (h5py.version.version <= '2.0.1' and not
                hasattr(super(File, self).__getitem__(key), 'shape')):
            # avoid bug when deleting groups that produces a segmentation fault
            return
        super(File, self).__delitem__(key)
