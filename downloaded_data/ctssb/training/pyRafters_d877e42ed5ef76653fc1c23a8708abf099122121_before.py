from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six

from collections import namedtuple, MutableMapping
import h5py

md_value = namedtuple("md_value", ['value', 'units'])


def _hdf_write_helper(group, md, overwrite=False):
    """
    recursive helper function for writing meta-data into DataExchange files

    Parameters
    ----------
    group : `~h5py.Group`
        a valid and open group to put the meta-data in

    md : dict
       All values in the dict must be either a `dict` or
       a `md_value` named tuple

    overwrite : bool, optional [False]
       If true, silently overwrite values when a given meta-data entry
       exists, if False raise an exception.  This can result in data being
       partially written.
    """
    for k, v in six.iteritems(md):
        # we have hit a leaf
        if isinstance(v, md_value):
            if overwrite and k in group:
                del group[k]
            ds = group.create_dataset(k, data=v.value)
            if v.units is not None:
                ds.attrs['units'] = v.units
        # else keep recursing down the tree
        else:
            # TODO re-use existing groups
            ng = group.require_group(k)
            _hdf_write_helper(ng, v._dict)


def _hdf_read_helper(group, md_dict):
    """
    A recursive reader function to extract meta-data from a DateExchange group.

    This operates on the input _in place_.

    Parameters
    ----------
    group : `h5py.Group`
        a valid and open group to extract md from

    md_dict : `MD_dict`
       the `MD_dict` to load the data into
    """
    for k in group.keys():
        print(k)
        obj = group[k]
        if isinstance(obj, h5py.Dataset):
            if 'units' in obj.attrs:
                units = obj.attrs['units']
            else:
                units = None
            md_dict[k] = md_value(obj[...], units)
        elif isinstance(obj, h5py.Group):
            md_dict._dict[k] = MD_dict()
            _hdf_read_helper(obj, md_dict[k])
        # else: all objects in an hdf file should be groups or data sets


def _iter_helper(path_list, split, md_dict):
    """
    Recursively walk the tree and return the names of the leaves
    """
    for k, v in six.iteritems(md_dict):
        if isinstance(v, md_value):
            yield split.join(path_list + [k])
        else:
            for inner_v in _iter_helper(path_list + [k], split, v):
                yield inner_v


class MD_dict(MutableMapping):
    """
    A class to make dealing with the meta-data scheme for DateExchange easier

    Examples
    --------
    Getting and setting data by path is possible

    >>> tt = MD_dict()
    >>> tt['name'] = 'test'
    >>> tt['nested.a'] = 2
    >>> tt['nested.b'] = (5, 'm')
    >>> tt['nested.a'].value
    2
    >>> tt['nested.a'].units is None
    True
    >>> tt['name'].value
    'test'
    >>> tt['nested.b'].units
    'm'

    These objects can be put into an hdf group:

    >>> F = h5py.File('exampl.h5', driver='core')  # creates file in memory
    >>> g = F.require_group('meta_data')
    >>> tt.write_hdf(g)

    and loaded back

    >>> tt2 = MD_dict.read_hdf_group(F['meta_data'])
    >>> tt['name'] == tt2['name']
    True
    """
    def __init__(self, md_dict=None):
        # TODO properly walk the input on upgrade dicts -> MD_dict
        if md_dict is None:
            md_dict = dict()

        self._dict = md_dict
        self._split = '.'

    def __repr__(self):
        return self._dict.__repr__()

    # overload __setitem__ so dotted paths work
    def __setitem__(self, key, val):

        key_split = key.split(self._split)
        tmp = self._dict
        for k in key_split[:-1]:
            try:
                tmp = tmp[k]._dict
            except:
                tmp[k] = type(self)()
                tmp = tmp[k]._dict
            if isinstance(tmp, md_value):
                # TODO make message better
                raise KeyError("trying to use a leaf node as a branch")
        # TODO sixify
        # catch the case of a bare string
        if isinstance(val, str):
            # a value with out units
            tmp[key_split[-1]] = md_value(val, 'text')
            return
        try:
            # if the second element is a string or None, cast to named tuple
            if isinstance(val[1], str) or val[1] is None:
                tmp[key_split[-1]] = md_value(*val)
            # else, assume whole thing is the value with no units
            else:
                tmp[key_split[-1]] = md_value(val, None)
        # catch any type errors from trying to index into non-indexable things
        # or from trying to use iterables longer than 2
        except TypeError:
            tmp[key_split[-1]] = md_value(val, None)

    def __getitem__(self, key):
        key_split = key.split(self._split)
        tmp = self._dict
        for k in key_split[:-1]:
            try:
                tmp = tmp[k]._dict
            except:
                tmp[k] = type(self)()
                tmp = tmp[k]._dict

            if isinstance(tmp, md_value):
                # TODO make message better
                raise KeyError("trying to use a leaf node as a branch")

        return tmp.get(key_split[-1], None)

    def __delitem__(self, key):
        # pass one delete the entry
        # TODO make robust to non-keys
        key_split = key.split(self._split)
        tmp = self._dict
        for k in key_split[:-1]:
            # make sure we are grabbing the internal dict
            tmp = tmp[k]._dict
        del tmp[key_split[-1]]
        # TODO pass 2 remove empty branches

    def __len__(self):
        return len(list(iter(self)))

    def __iter__(self):
        return _iter_helper([], self._split, self._dict)

    def write_hdf(self, group):
        """
        Writes out this MD structure to a hdf file.

        Parameters
        ----------
        group : `~h5py.Group`
           Open group to write meta-data into
        """
        _hdf_write_helper(group, self._dict)

    @classmethod
    def read_hdf_group(cls, group):
        """
        Contruct a MD_dict by reading a group in an hdf file

        Parameters
        ----------
        group : `h5py.Group`
            An open and valid group
        """
        self = cls()
        _hdf_read_helper(group, self)
        return self
