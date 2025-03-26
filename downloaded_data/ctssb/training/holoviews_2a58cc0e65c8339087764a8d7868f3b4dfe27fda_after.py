"""
NdIndexableMapping and NdMapping objects.
"""
import param
import numpy as np
from collections import OrderedDict


class AttrDict(dict):
    """
    A dictionary type object that supports attribute access (e.g. for IPython
    tab completion).
    """

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class Dimension(param.Parameterized):

    cyclic = param.Boolean(default=False, doc="""
        Whether the range of this feature is cyclic (wraps around at the high
        end).""")

    name = param.String(default="", doc="Name of the Dimension.")

    range = param.NumericTuple(default=(0, 0), doc="""
        Lower and upper values for a Dimension.""")

    type = param.Parameter(default=None, doc="""
        Type associated with Dimension values.""")

    unit = param.String(default=None, doc="Unit string associated with the Dimension.")

    format_string = param.String(default="{name} = {val}{unit}")

    def __init__(self, name, **params):
        """
        Initializes the Dimension object with a name.
        """
        super(Dimension, self).__init__(name=name, **params)


    def __call__(self, name=None, **params):
        settings = dict(self.get_param_values(onlychanged=True), **params)
        if name is not None: settings['name'] = name
        return self.__class__(**settings)


    def pprint_value(self, value, rounding=2):
        """
        Pretty prints the dimension name and value with the format_string
        parameter and if supplied adds the unit string parameter.
        """

        unit = '' if self.unit is None else ' ' + self.unit
        try: # Try formatting numeric types as floats with rounding
            val=round(float(value), rounding)
        except:
            val = value

        return self.format_string.format(name=self.name.capitalize(),
                                         val=val, unit=unit)



class NdIndexableMapping(param.Parameterized):
    """
    An NdIndexableMapping is a type of mapping (like a dictionary or array)
    that uses fixed-length multidimensional keys. The effect is like an
    N-dimensional array, without requiring that the entire multidimensional
    space be populated.

    If the underlying type of data for each (key,value) pair also supports
    indexing (such as a dictionary, array, or list), fully qualified indexing
    can be used from the top level, with the first N dimensions of the index
    selecting a particular piece of data stored in the NdIndexableMapping
    object, and the remaining dimensions used to index into the underlying data.

    For instance, for an NdIndexableMapping x with dimensions "Year" and
    "Month" and an underlying data type that is a 2D floating-point array
    indexed by (r,c), a 2D array can be indexed with x[2000,3] and a single
    floating-point number may be indexed as x[2000,3,1,9].

    In practice, this class is typically only used as an abstract base class,
    because the NdMapping subclass extends it with a range of useful slicing
    methods for selecting subsets of the data. Even so, keeping the slicing
    support separate from the indexing and data storage methods helps make both
    classes easier to understand.
    """

    dimensions = param.List(default=[Dimension("Default")], constant=True)

    data_type = param.Parameter(default=None, constant=True)

    metadata = param.Dict(default=AttrDict(), doc="""
        Additional labels to be associated with the Dataview.""")

    _deep_indexable = True

    def __init__(self, initial_items=None, **kwargs):
        self._data = OrderedDict()

        kwargs, metadata = self.write_metadata(kwargs)

        super(NdIndexableMapping, self).__init__(metadata=metadata, **kwargs)

        self._dimensions = [d if isinstance(d, Dimension) else Dimension(d)
                            for d in self.dimensions]

        self._next_ind = 0
        self._check_key_type = True

        if isinstance(initial_items, tuple):
            self._add_item(initial_items[0], initial_items[1])
        elif initial_items is not None:
            self.update(OrderedDict(initial_items))


    @property
    def dim_dict(self):
        return OrderedDict([(d.name, d) for d in self._dimensions])


    @property
    def dimension_labels(self):
        return [d.name for d in self._dimensions]


    @property
    def _types(self):
        return [d.type for d in self._dimensions]


    @property
    def ndims(self):
        return len(self.dimensions)


    def write_metadata(self, kwargs):
        """
        Acts as a param override, placing any kwargs, which are not parameters
        into the metadata dictionary.
        """
        items = list(kwargs.items())
        if 'metadata' in kwargs:
            items = list(kwargs.pop('metadata').items()) + items
        metadata = AttrDict(self.metadata, **dict([(k, v) for k, v in items
                                                   if k not in self.params()]))
        for key in metadata:
            kwargs.pop(key, None)
        return kwargs, metadata


    def _item_check(self, dim_vals, data):
        """
        Applies checks to individual data elements before they are inserted
        ensuring that they are of a certain type. Can be subclassed to implement
        further element restrictions.
        """
        if self.data_type is not None and not isinstance(data, self.data_type):
            raise TypeError('{slf} does not accept {data} type, data elements have '
                            'to be a {restr}.'.format(slf=type(self).__name__,
                                                      data=type(data).__name__,
                                                      restr=self.data_type.__name__))
        elif not len(dim_vals) == self.ndims:
            raise KeyError('Key has to match number of dimensions.')


    def _resort(self):
        self._data = OrderedDict(sorted(self._data.items()))


    def _add_item(self, dim_vals, data, sort=True):
        """
        Records data indexing it in the specified feature dimensions.
        """
        if not isinstance(dim_vals, tuple):
            dim_vals = (dim_vals,)
        self._item_check(dim_vals, data)
        dim_types = zip(self._types, dim_vals)
        dim_vals = tuple(v if t is None else t(v) for t, v in dim_types)
        self._update_item(dim_vals, data)
        if sort:
            self._resort()


    def _update_item(self, dim_vals, data):
        """
        Subclasses default method to allow updating of nested data structures
        rather than simply overriding them.
        """
        if dim_vals in self._data and hasattr(self._data[dim_vals], 'update'):
            self._data[dim_vals].update(data)
        else:
            self._data[dim_vals] = data


    def update(self, other):
        """
        Updates the NdMapping with another NdMapping or OrderedDict
        instance, checking that they are indexed along the same number
        of dimensions.
        """
        for key, data in other.items():
            self._add_item(key, data, sort=False)
        self._resort()


    def reindex(self, dimension_labels):
        """
        Create a new object with a re-ordered or reduced set of dimension
        labels. Accepts either a single dimension label or a list of chosen
        dimension labels.

        Reducing the number of dimension labels will discard information held in
        the dropped dimensions. All data values are accessible in the newly
        created object as the new labels must be sufficient to address each
        value uniquely.
        """

        indices = [self.dim_index(el) for el in dimension_labels]

        keys = [tuple(k[i] for i in indices) for k in self._data.keys()]
        reindexed_items = OrderedDict(
            (k, v) for (k, v) in zip(keys, self._data.values()))
        reduced_dims = set(self.dimension_labels).difference(dimension_labels)
        dimensions = [self.dim_dict[d] for d in dimension_labels if d not in reduced_dims]

        if len(set(keys)) != len(keys):
            raise Exception("Given dimension labels not sufficient to address all values uniquely")

        return self.clone(reindexed_items, dimensions=dimensions)


    def add_dimension(self, dimension, dim_pos, dim_val, **kwargs):
        """
        Create a new object with an additional dimension along which items are
        indexed. Requires the dimension name, the desired position in the
        dimension labels and a dimension value that applies to all existing
        elements.
        """
        if isinstance(dimension, str):
            dimension = Dimension(dimension)

        if dimension.name in self.dimension_labels:
            raise Exception('{dim} dimension already defined'.format(dim=dimension.name))

        dimensions = self._dimensions[:]
        dimensions.insert(dim_pos, dimension)

        items = OrderedDict()
        for key, val in self._data.items():
            new_key = list(key)
            new_key.insert(dim_pos, dim_val)
            items[tuple(new_key)] = val

        return self.clone(items, dimensions=dimensions, **kwargs)


    def clone(self, items=None, **kwargs):
        """
        Returns a clone with matching parameter values and metadata, containing
        the specified items (empty by default).
        """
        settings = dict(self.get_param_values(), **kwargs)
        return self.__class__(initial_items=items, **settings)

    def copy(self):
        return self.clone(list(self.items()))


    def dframe(self, value_label='data'):
        try:
            import pandas
        except ImportError:
            raise Exception("Cannot build a DataFrame without the pandas library.")
        labels = self.dimension_labels + [value_label]
        return pandas.DataFrame(
            [dict(zip(labels, k + (v,))) for (k, v) in self._data.items()])


    def _apply_key_type(self, keys):
        """
        If a key type is set in the dim_info dictionary, this method applies the
        type to the supplied key.
        """
        typed_key = () 
        for dim, key in zip(self._dimensions, keys):
            key_type = dim.type
            if key_type is None:
                typed_key += (key,)
            elif isinstance(key, slice):
                sl_vals = [key.start, key.stop, key.step]
                typed_key += (slice(*[key_type(el) if el is not None else None
                                      for el in sl_vals]),)
            elif key is Ellipsis:
                typed_key += (key,)
            else:
                typed_key += (key_type(key),)
        return typed_key


    def _split_index(self, key):
        """
        Splits key into map and data indices. If only map indices are supplied
        the data is passed an index of None.
        """
        if not isinstance(key, tuple):
            key = (key,)
        map_slice = key[:self.ndims]
        if self._check_key_type:
            map_slice = self._apply_key_type(map_slice)
        if len(key) == self.ndims:
            return map_slice, ()
        else:
            return map_slice, key[self.ndims:]


    def __getitem__(self, key):
        """
        Allows indexing in the indexed dimensions, passing any additional
        indices to the data elements.
        """
        if key in [Ellipsis, ()]:
            return self
        map_slice, data_slice = self._split_index(key)
        return self._dataslice(self._data[map_slice], data_slice)


    def _dataslice(self, data, indices):
        """
        Returns slice of data element if the item is deep indexable. Warns if
        attempting to slice an object that has not been declared deep indexable.
        """
        if hasattr(data, '_deep_indexable'):
            return data[indices]
        elif len(indices) > 0:
            self.warning('Cannot index into data element, extra data'
                         ' indices ignored.')
        return data


    def __setitem__(self, key, value):
        self._add_item(key, value)


    def __str__(self):
        return repr(self)


    def dim_range(self, dim):
        dim_values = [k[self.dim_index(dim)] for k in self._data.keys()]
        return np.min(dim_values), np.max(dim_values)


    @property
    def last(self):
        """"
        Returns the item highest data item along the map dimensions.
        """
        return list(self._data.values())[-1] if len(self) else None


    @property
    def last_key(self):
        """"
        Returns the last key.
        """
        return list(self.keys())[-1] if len(self) else None


    def dim_index(self, dimension_label):
        """
        Returns the tuple index of the requested dimension.
        """
        return self.dimension_labels.index(dimension_label)


    def dimension_keys(self):
        """
        Returns the list of keys together with the dimension labels.
        """
        return [tuple(zip(self.dimension_labels, [k] if self.ndims == 1 else k))
                for k in self.keys()]


    def keys(self):
        """
        Returns indices for all data elements.
        """
        if self.ndims == 1:
            return [k[0] for k in self._data.keys()]
        else:
            return list(self._data.keys())


    def values(self):
        return list(self._data.values())


    def items(self):
        return list(zip(list(self.keys()), list(self.values())))


    def get(self, key, default=None):
        try:
            if key is None:
                return None
            return self[key]
        except:
            return default


    def pop(self, *args):
        if len(args) > 0 and not isinstance(args[0], tuple):
            args[0] = (args[0],)
        return self._data.pop(*args)


    def __iter__(self):
        return self

    def next(self): # For Python 2 and 3 compatibility
        return self.__next__()

    def __next__(self):
        """
        Implements the iterable interface, returning values unlike a standard
        dictionary.
        """
        if self._next_ind < len(self.keys()):
            val = list(self.values())[self._next_ind]
            self._next_ind += 1
            return val
        else:
            self._next_ind = 0
            raise StopIteration


    def __contains__(self, key):
        if self.ndims == 1:
            return key in self._data.keys()
        else:
            return key in self.keys()


    def __len__(self):
        return len(self._data)



class NdMapping(NdIndexableMapping):
    """
    NdMapping supports the same indexing semantics as NdIndexableMapping but
    also supports filtering of items using slicing ranges.
    """

    def __getitem__(self, indexslice):
        """
        Allows slicing operations along the map and data dimensions. If no data
        slice is supplied it will return all data elements, otherwise it will
        return the requested slice of the data.
        """
        if indexslice in [Ellipsis, ()]:
            return self

        map_slice, data_slice = self._split_index(indexslice)
        map_slice = self._transform_indices(map_slice)
        conditions = self._generate_conditions(map_slice)

        if all(not isinstance(el, slice) for el in map_slice):
            return self._dataslice(self._data[map_slice], data_slice)
        else:
            items = [(k, self._dataslice(v, data_slice)) for k, v
                     in self._data.items() if self._conjunction(k, conditions)]
            if self.ndims == 1:
                items = [(k[0], v) for (k, v) in items]
            return self.clone(items)


    def _transform_indices(self, indices):
        """
        Identity function here but subclasses can implement transforms of the
        dimension indices from one coordinate system to another.
        """
        return indices


    def _generate_conditions(self, map_slice):
        """
        Generates filter conditions used for slicing the data structure.
        """
        conditions = []
        for dim in map_slice:
            if isinstance(dim, slice):
                if dim == slice(None):
                    conditions.append(self._all_condition())
                elif dim.start is None:
                    conditions.append(self._upto_condition(dim))
                elif dim.stop is None:
                    conditions.append(self._from_condition(dim))
                else:
                    conditions.append(self._range_condition(dim))
            elif dim is Ellipsis:
                conditions.append(self._all_condition())
            else:
                conditions.append(self._value_condition(dim))
        return conditions


    def _value_condition(self, value):
        return lambda x: x == value


    def _range_condition(self, slice):
        if slice.step is None:
            lmbd = lambda x: slice.start <= x < slice.stop
        else:
            lmbd = lambda x: slice.start <= x < slice.stop and not (
                (x-slice.start) % slice.step)
        return lmbd


    def _upto_condition(self, slice):
        if slice.step is None:
            lmbd = lambda x: x < slice.stop
        else:
            lmbd = lambda x: x < slice.stop and not (x % slice.step)
        return lmbd


    def _from_condition(self, slice):
        if slice.step is None:
            lmbd = lambda x: x > slice.start
        else:
            lmbd = lambda x: x > slice.start and ((x-slice.start) % slice.step)
        return lmbd

    def _all_condition(self):
        return lambda x: True


    def _conjunction(self, key, conditions):
        conds = []
        for i, cond in enumerate(conditions):
            conds.append(cond(key[i]))
        return all(conds)

        
__all__ = ["NdIndexableMapping",
           "NdMapping",
           "AttrDict",
           "Dimension"]
