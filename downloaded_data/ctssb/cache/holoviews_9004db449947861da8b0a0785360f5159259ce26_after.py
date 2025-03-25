from __future__ import absolute_import
import sys
import types

import numpy as np
import xarray as xr

from .. import util
from ..dimension import Dimension
from ..ndmapping import NdMapping, item_check, sorted_context
from ..element import Element
from .grid import GridInterface
from .interface import Interface


class XArrayInterface(GridInterface):

    types = (xr.Dataset if xr else None,)

    datatype = 'xarray'

    @classmethod
    def dimension_type(cls, dataset, dim):
        name = dataset.get_dimension(dim).name
        idx = list(dataset.data.keys()).index(name)
        return dataset.data[name].dtype.type


    @classmethod
    def dtype(cls, dataset, dim):
        name = dataset.get_dimension(dim).name
        idx = list(dataset.data.keys()).index(name)
        return dataset.data[name].dtype


    @classmethod
    def init(cls, eltype, data, kdims, vdims):
        element_params = eltype.params()
        kdim_param = element_params['kdims']
        vdim_param = element_params['vdims']

        if kdims:
            kdim_names = [kd.name if isinstance(kd, Dimension)
                          else kd for kd in kdims]
        else:
            kdim_names = [kd.name for kd in eltype.kdims]

        if not isinstance(data, xr.Dataset):
            kdims = [kd if isinstance(kd, Dimension) else Dimension(kd)
                     for kd in kdims]
            vdims = [d if isinstance(vd, Dimension) else Dimension(vd)
                     for vd in vdims]
            if isinstance(data, tuple):
                data = {d.name: vals for d, vals in zip(kdims + vdims, data)}
            if not isinstance(data, dict):
                raise TypeError('XArrayInterface could not interpret data type')
            coords = [(kd.name, data[kd.name]) for kd in kdims][::-1]
            arrays = {}
            for vdim in vdims:
                arr = data[vdim.name]
                if not isinstance(arr, xr.DataArray):
                    arr = xr.DataArray(arr, coords=coords)
                arrays[vdim.name] = arr
            try:
                data = xr.Dataset(arrays)
            except:
                pass
        else:
            if vdims is None:
                vdims = list(data.data_vars.keys())
            if kdims is None:
                kdims = [name for name in data.dims
                         if isinstance(data[name].data, np.ndarray)]

        if not isinstance(data, xr.Dataset):
            raise TypeError('Data must be be an xarray Dataset type.')
        return data, {'kdims': kdims, 'vdims': vdims}, {}


    @classmethod
    def range(cls, dataset, dimension):
        dim = dataset.get_dimension(dimension).name
        if dim in dataset.data:
            data = dataset.data[dim]
            return data.min().item(), data.max().item()
        else:
            return np.NaN, np.NaN


    @classmethod
    def groupby(cls, dataset, dimensions, container_type, group_type, **kwargs):
        index_dims = [dataset.get_dimension(d) for d in dimensions]
        element_dims = [kdim for kdim in dataset.kdims
                        if kdim not in index_dims]

        group_kwargs = {}
        if group_type != 'raw' and issubclass(group_type, Element):
            group_kwargs = dict(util.get_param_values(dataset),
                                kdims=element_dims)
        group_kwargs.update(kwargs)

        # XArray 0.7.2 does not support multi-dimensional groupby
        # Replace custom implementation when 
        # https://github.com/pydata/xarray/pull/818 is merged.
        if len(dimensions) == 1:
            data = [(k, group_type(v, **group_kwargs)) for k, v in
                    dataset.data.groupby(dimensions[0])]
        else:
            unique_iters = [cls.values(dataset, d, False) for d in dimensions]
            indexes = zip(*[vals.flat for vals in util.cartesian_product(unique_iters)])
            data = [(k, group_type(dataset.data.sel(**dict(zip(dimensions, k))),
                                   **group_kwargs))
                    for k in indexes]

        if issubclass(container_type, NdMapping):
            with item_check(False), sorted_context(False):
                return container_type(data, kdims=index_dims)
        else:
            return container_type(data)


    @classmethod
    def get_coords(cls, dataset, dim):
        return dataset.data[dim].data


    @classmethod
    def values(cls, dataset, dim, expanded=True, flat=True):
        data = dataset.data[dim].data
        if dim in dataset.vdims:
            inversions = cls.invert(dataset)
            if inversions and not (flat and data.ndim > 1):
                data = data.__getitem__(inversions[::-1])
            dims = [name for name in dataset.data[dim].dims
                    if isinstance(dataset.data[name].data, np.ndarray) and
                    name in dataset.data.dims]
            inds = [dims.index(kd.name) for kd in dataset.kdims]
            transposed = data.transpose(inds[::-1])
            return transposed.T.flatten() if flat else transposed
        elif not expanded:
            return data if np.all(data[1:] >= data[:-1]) else data[::-1]
        else:
            arrays = [dataset.data[d.name].data for d in dataset.kdims]
            product = util.cartesian_product(arrays)[dataset.get_dimension_index(dim)]
            inversions = cls.invert(dataset)
            if inversions:
                product = product.__getitem__(inversions)
            return product.flatten() if flat else product


    @classmethod
    def aggregate(cls, dataset, dimensions, function, **kwargs):
        if len(dimensions) > 1:
            raise NotImplementedError('Multi-dimensional aggregation not '
                                      'supported as of xarray <=0.7.2.')
        elif not dimensions:
            return dataset.data.apply(function)
        else:
            return dataset.data.groupby(dimensions[0]).apply(function)


    @classmethod
    def unpack_scalar(cls, dataset, data):
        """
        Given a dataset object and data in the appropriate format for
        the interface, return a simple scalar.
        """
        if (len(data.data_vars) == 1 and
            len(data[dataset.vdims[0].name].shape) == 0):
            return data[dataset.vdims[0].name].item()
        return data


    @classmethod
    def concat(cls, dataset_objs):
        #cast_objs = cls.cast(dataset_objs)
        # Reimplement concat to automatically add dimensions
        # once multi-dimensional concat has been added to xarray.
        return xr.concat([col.data for col in dataset_objs], dim='concat_dim')

    @classmethod
    def redim(cls, dataset, dimensions):
        renames = {k: v.name for k, v in dimensions.items()}
        return dataset.data.rename(renames)

    @classmethod
    def reindex(cls, dataset, kdims=None, vdims=None):
        return dataset.data

    @classmethod
    def sort(cls, dataset, by=[]):
        return dataset

    @classmethod
    def select(cls, dataset, selection_mask=None, **selection):
        validated = {}
        for k, v in selection.items():
            if isinstance(v, slice):
                v = (v.start, v.stop)
            if isinstance(v, set):
                validated[k] = list(v)
            elif isinstance(v, tuple):
                validated[k] = slice(v[0], v[1]-sys.float_info.epsilon*10)
            elif isinstance(v, types.FunctionType):
                validated[k] = v(dataset[k])
            else:
                validated[k] = v
        data = dataset.data.sel(**validated)
        indexed = cls.indexed(dataset, selection)
        if (indexed and len(data.data_vars) == 1 and
            len(data[dataset.vdims[0].name].shape) == 0):
            return data[dataset.vdims[0].name].item()
        return data

    @classmethod
    def length(cls, dataset):
        return np.product(dataset[dataset.vdims[0].name].shape)
    
    @classmethod
    def dframe(cls, dataset, dimensions):
        if dimensions:
            return dataset.reindex(columns=dimensions)
        else:
            return dataset.data.to_dataframe().reset_index(dimensions)

    @classmethod
    def sample(cls, columns, samples=[]):
        raise NotImplementedError

    @classmethod
    def add_dimension(cls, columns, dimension, dim_pos, values, vdim):
        if not vdim:
            raise Exception("Cannot add key dimension to a dense representation.")
        dim = dimension.name if isinstance(dimension, Dimension) else dimension
        return dataset.assign(**{dim: values})


Interface.register(XArrayInterface)
