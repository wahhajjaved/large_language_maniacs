"""Support for HDF5 files."""

from __future__ import absolute_import, division, print_function
from collections import OrderedDict

import numpy as np
import h5py

import dwi.util

DEFAULT_DSETNAME = 'default'


def write_hdf5(filename, array, attrs, dsetname=DEFAULT_DSETNAME):
    """Write an array with attributes into a newly created, compressed HDF5
    file.
    """
    f = h5py.File(filename, 'w')
    dset = f.create_dataset(dsetname, data=array, compression='gzip',
                            shuffle=True, fletcher32=True)
    for k, v in attrs.iteritems():
        # HDF5 doesn't understand None objects, so replace any with nan values.
        if dwi.util.iterable(v) and not isinstance(v, str):
            v = type(v)([(np.nan if x is None else x) for x in v])
        dset.attrs[k] = v
    f.close()


def read_hdf5(filename, dsetname=DEFAULT_DSETNAME):
    """Read an array with attributes from an HDF5 file."""
    try:
        f = h5py.File(filename, 'r')
    except IOError, e:
        if e.filename is None:
            e.filename = filename
        raise
    if dsetname not in f:
        if len(f.keys()) != 1:
            raise ValueError('Ambiguous content: {}'.format(filename))
        dsetname = f.keys()[0]
    dset = f[dsetname]
    array = np.array(dset)
    attrs = OrderedDict(dset.attrs)
    f.close()
    return array, attrs
