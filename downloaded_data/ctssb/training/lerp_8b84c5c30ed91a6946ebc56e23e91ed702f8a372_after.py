# -*- coding: utf-8 -*-
"""
This module delivers utilities to manipulate data meshes

"""
import os.path
import pickle
from collections import namedtuple
from copy import deepcopy
from functools import singledispatch
from itertools import islice, product
from numbers import Number
import numpy as np
from numpy.core.multiarray import interp as interp2d
from scipy.interpolate import dfitpack, fitpack
from lerp.intern import deprecated, logger, myPlot
import abc

__version__ = "0.1aN"

# Attention, utilisation d'ascii pour les chaînes de caractères
__all__ = ["mesh1d", "mesh2d", "mesh3d", "mesh4d", "mesh5d",
           "polymesh2d", "polymesh3d"]

axis = namedtuple('axis', ['label', 'unit'])

axeConv = {_i: _j for (_i, _j) in enumerate('xyzvw')}

_html_style = {
    'th': 'color: LightGrey;border:0px none;text-align:center;background:none;',
    'none': 'border:0px none;background:none;',
}


class mesh(abc.ABC):
    """
    
    """
    @property
    @abc.abstractmethod
    def d(self):
        """
        :return: 
        """

    def __dir__(self):
        # print([repr(getattr(self, f)) for f in dir(self.__class__)])
        # Remove deprecated methods from dir()
        return sorted([f for f in dir(self.__class__) \
                       if not (f.startswith('_') | \
                               ('deprecated' in repr(getattr(self, f))))],
                      key=lambda x: x.lower())

    def __len__(self):
        return self.d.size

    def shape(self):
        return self.d.shape

    def read_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            os.path.exists(fileName)
            with open(fileName, 'rb') as f:
                # The protocol version used is detected automatically,
                # so we do not have to specify it.
                data = pickle.load(f)
            return data
        except:
            raise
            # raise FileNotFoundError("Please check your path, {} not found".\
            # format(fileName))

    def to_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            with open(fileName, 'wb') as f:
                pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)
        except:
            raise FileNotFoundError("Please check your path, {} not found". \
                                    format(fileName))


def add(*objs):
    print(*objs)


############################################################################
# CLASSE mesh1d
############################################################################
class mesh1d(np.ndarray):
    """
    Defines a basis class for array/unit/label based objects


    Parameters
    ----------
    data : array
           Data in form of a python array or numpy.array

    label : string, optional
            label for plotting utility

    unit : string, optional
           unit for plotting utility

    Examples
    ---------

    .. code-block:: python

        In [1]: from lerp import mesh1d

        In [2]: x = mesh1d(data=[100, 600, -200, 300], label="Current", unit="A")

        In [3]: print("Max : {0} {1.unit}".format(x.max(), x))
        Max : 600 A

        In [4]: print("Before sorting\\n", x)
        Before sorting
         [ 100  600 -200  300]

        In [5]: x.sort()

        In [6]: print("After sorting\\n", x)
        After sorting
         [-200  100  300  600]

        # Element added to x, inplace and sorting
         In [7]: x.push( [250, 400 ], sort=True)
        Out[7]: mesh1d(data=[-200,100,250,300,400,600], label=Current, unit=A)

        # Addition, in place
        In [8]: x += 900

        In [9]: x
        Out[9]: mesh1d(data=[700,1000,1200,1500], label=Current, unit=A)

        # Slicing
        In [10]: x[2]
        Out[10]: 1200

        In [11]: x[1:3]
        Out[11]: mesh1d(data=[1000,1200], label="Current", unit="A")


    """

    def __new__(cls, data=None, label=None, unit=None):
        # We first cast to be our class type
        # np.asfarray([], dtype='float64')
        @singledispatch
        def myArray(o):
            if o is None:
                o = []
            # Will call directly __array_finalize__
            obj = np.asarray(o).flatten().view(cls)
            obj.label = label
            obj.unit = unit
            return obj

        @myArray.register(mesh1d)
        def _(o):
            if label is not None:
                o.label = label
            if unit is not None:
                o.unit = unit
            return o

        return myArray(data)

    # see InfoArray.__array_finalize__ for comments
    def __array_finalize__(self, obj):
        """

        :type obj: object
        """
        self.unit = getattr(obj, 'unit', None)
        self.label = getattr(obj, 'label', None)

    def __repr__(self):
        return '{0}, label="{1.label}", unit="{1.unit}")'. \
            format(np.array_repr(self, precision=2).replace(")", ""). \
                   replace("(", "(data="), self)

    def _repr_html_(self):

        import xml.etree.ElementTree as ET
        root = ET.Element('div')
        pre = ET.SubElement(root, 'p')
        code = ET.SubElement(pre, 'code')
        code.text = self.__class__.__name__
        span = ET.SubElement(pre, 'span').text = ": "
        b = ET.SubElement(pre, 'b')
        b.text = self.label if self.label is not None else "Label"
        span = ET.SubElement(pre, 'span')
        span.text = " [{}]".format(self.unit if self.unit is
                                                not None else "unit")
        ET.SubElement(pre, 'br')

        res = ET.SubElement(pre, 'p')
        if self.size == 1:
            res.text = str(self)
        else:
            table = ET.SubElement(res, 'table', {'style': 'border: 0px none;'})
            tbody = ET.SubElement(table, 'tbody')
            for _i in range(2):
                if _i == 0:
                    tr = ET.SubElement(tbody, 'tr', {'style': 'border: 0px solid'})
                    for _node in islice(np.arange(len(self)), 15):
                        ET.SubElement(tr, 'th',
                                      {'style': _html_style['th']}).text = str(_node)
                    if len(self) > 16:
                        ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = "..."
                        ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self) - 1)
                    elif len(self) > 15:
                        ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self) - 1)
                else:
                    tr = ET.SubElement(tbody, 'tr', {'style': 'border: 0px solid'})
                    for _node in islice(self, 15):
                        ET.SubElement(tr, 'td').text = str(_node)
                    if len(self) > 16:
                        ET.SubElement(tr, 'td').text = "..."
                        ET.SubElement(tr, 'td').text = str(self[-1])
                    elif len(self) > 15:
                        ET.SubElement(tr, 'td').text = str(self[-1])

        return str(ET.tostring(root, encoding='utf-8'), 'utf-8')

    def __eq__(self, other):

        if isinstance(other, self.__class__) and \
                np.all(np.asarray(self) == np.asarray(other)):
            if self.label != other.label:
                print("Labels are differents : {0.label} / {1.label}".format(self, other))
            if self.unit != other.unit:
                print("Units are differents : {0.unit} / {1.unit}".format(self, other))
            return True
        else:
            return False

    def apply(self, f, inplace=False):
        """Apply a function to the complete mesh1d data

        Parameters
        ----------
        f : function
        inplace: boolean
            True if yA.x.pushou want the mesh1d to be modified inplace

        Returns
        -------
        Nothing or mesh1d
            Depends if inplace is set to False or True

        """
        res = self.__class__(np.apply_along_axis(f, 0, np.array(self)),
                             **self.__dict__)
        if inplace is False:
            return res
        else:
            for i, v in enumerate(self):
                self[i] = res[i]

    def copy(self):
        return self.__class__(np.copy(self), **self.__dict__)

    def diff(self, n=1):
        return self.__class__(np.diff(self, n=n), **self.__dict__)

    def insert(self, at, obj, axis=0):
        if self.ndim == 1:
            newArray = np.insert(self, at, obj)
        else:
            newArray = self

        return newArray

    def mean(self, *args, **kwargs):
        """
        mean
        ^^^^^^^^
        
        Returns
        -------
        Object mean
        """
        return np.mean(np.asarray(self), *args, **kwargs)

    def median(self, *args, **kwargs):
        return np.median(np.asarray(self), *args, **kwargs)

    @myPlot
    def plot(self, *args, **kwargs):
        return
        # _plot(y=self)

    def pop(self, axis=0):
        """Pop an element of the array.

        Parameters
        ----------
        obj: class instance
            The other class must have the ``coef`` attribute.
        axis: integer
            Set to True if you want the mesh1d to be sorted (ascending)

        Returns
        -------
        mesh1d
            Please not that the element(s) are not added inplace!

        """
        return self.__class__(self[:-1], **self.__dict__), self[-1]

    def push(self, obj, unique=True, return_index=False):
        """Pushes an element to an array.

        Notes
        -----
        The elements are not added inplace

        Parameters
        ----------
        obj: single numeric, array, numpy.array
        sort: boolean
              True (default) if you want the mesh1d to be ascending sorted.

        Returns
        -------
        New object of the same class with new element

        Notes
        -----
        As instance of numpy array, the elements are not added inplace
        
        """
        # Test if self is not empty array
        try:
            len(self)
        except:
            res = np.array(obj)
        else:
            res = np.append(self, obj)

        if return_index is True:
            _unique = np.unique(res, return_index=True)
            return [self.__class__(_unique[0].flatten(),
                                   **self.__dict__), _unique[1]]

        if unique is True:
            res = np.unique(res)

        return self.__class__(res, **self.__dict__)

    def __contains__(self, item):
        return item in np.asarray(self)


############################################################################
# CLASSE mesh2d
############################################################################
class mesh2d(mesh):
    """
    Fundamental 2D object, strict monotonic

    Instantiation by giving (x, d) parameters or by loading a csv-file.

    Parameters
    ----------
    x : numpy.array or mesh1d
        1D array of x-coordinates of the mesh on which to interpolate

    d : numpy.array or mesh1d
        1D array of d-coordinates of the mesh on result to be interpolated

    fileName : string
        Complete address to csv-file, further

    Notes
    ----------
    Currently supported features:
        * calling the object `cur(x)` return the interpolated value at x.
        * common operations:  +, -, , /
        * standard functions:func:`len()`, :func:`print()`
    """

    def __init__(self, x=None, d=None,
                 x_label=None, x_unit=None,
                 label=None, unit=None,
                 clipboard=False, extrapolate=True,
                 **kwargs):
        """
        """

        if clipboard is True:
            self.read_clipboard()
        else:
            self.x = mesh1d(x, label=x_label, unit=x_unit)
            self._d = mesh1d(d, label=label, unit=unit)

        self.options = {}
        self.options['extrapolate'] = extrapolate
        if 'options' in kwargs:
            self.options = {**kwargs['options'], **self.options}

        self._gradient = None
        self._sort()
        self._steps = deepcopy(self)
        # Warning : monkey patching
        self._steps.__call__ = self.step
        self.label = label
        self.unit = unit
        
    @property
    def d(self):
        return self._d

    @d.setter
    def d(self, obj):
        self._d = obj

    def __add__(self, obj):
        """
        Adds obj to self along d-axis
        
        Parameters
        ----------
        obj : Number or mesh2d like
              object to add to current object
            
            
        Returns
        ----------
        mesh2d
        
        Notes
        ------------
        Pay attention to 'extrapolate' options as it impacts the adding behavior of both arrays.
        
        Exemple
        ---------- 
                
        
        In [1]: A = mesh2d([1, 2, 3], [0.5, 6, 9.0])

        In [2]: A
        Out[2]: 
        x = mesh1d(data=[1, 2, 3], label="None", unit="None")
        d = mesh1d(data=[ 0.5,  6. ,  9. ], label="None", unit="None")
        
        In [3]: A + 10
        Out[3]: 
        x = mesh1d(data=[1, 2, 3], label="None", unit="None")
        d = mesh1d(data=[ 10.5,  16. ,  19. ], label="None", unit="None")
        
        In [4]: B = mesh2d([0.4, 3, 6], [0.5, 6, 9.0])
        
        In [5]: A + B
        Out[5]: 
        x = mesh1d(data=[ 0.4,  1. ,  2. ,  3. ,  6. ], label="None", unit="None")
        d = mesh1d(data=[ -2.3 ,   2.27,   9.88,  15.  ,  27.  ], label="None", unit="None")
        
        In [6]: A.options
        Out[6]: {'extrapolate': True}
        
        In [7]: A.options['extrapolate'] = False
        
        In [8]: A + B
        Out[8]: 
        x = mesh1d(data=[ 0.4,  1. ,  2. ,  3. ,  6. ], label="None", unit="None")
        d = mesh1d(data=[  1.  ,   2.27,   9.88,  15.  ,  18.  ], label="None", unit="None")

        """
        new_args = deepcopy(self.__dict__)
        if isinstance(obj, Number):
            # Casting rule from numpy
            new_args['d'] = np.add(self.d, obj)
            return self.__class__(**new_args)
        elif isinstance(obj, mesh2d):
            new_args['x'] = np.union1d(self.x, obj.x)
            new_args['d'] = [_y1 + _y2 for _y1, _y2 in zip(self(new_args['x']), obj(new_args['x']))]
            return self.__class__(**new_args)
        else:
            logger.warning("Adding {} to {} failed".format(
                obj.__class__.__name__,
                self.__class__.__name__))

    def __sub__(self, obj):
        return self.__add__(-obj)

    def __mul__(self, obj):
        """
        Adds obj to self along d-axis
        
        Parameters
        ----------
        obj : Number or mesh2d like
              object to multiply to current object
            
            
        Returns
        ----------
        mesh2d        
        
        """
        new_args = deepcopy(self.__dict__)
        if isinstance(obj, Number):
            # Casting rule from numpy
            new_args['d'] = np.multiply(self.d, obj)
            return self.__class__(**new_args)
        elif isinstance(obj, mesh2d):
            new_args['x'] = np.union1d(self.x, obj.x)
            new_args['d'] = [self(_x) * obj(_x) for _x in new_args['x']]
            return self.__class__(**new_args)
        else:
            logger.warning("Multiplying {} to {} failed".format(
                obj.__class__.__name__,
                self.__class__.__name__))

    def __truediv__(self, obj):
        """
        """
        new_args = deepcopy(self.__dict__)
        if isinstance(obj, Number):
            # Casting rule from numpy
            new_args['d'] = np.divide(self.d, obj)
            return self.__class__(**new_args)
        elif isinstance(obj, mesh2d):
            new_args['x'] = np.union1d(self.x, obj.x)
            new_args['d'] = [self(_x) / obj(_x) for _x in new_args['x']]
            return self.__class__(**new_args)
        else:
            logger.warning("Multiplyng {} to {} failed".format(
                obj.__class__.__name__,
                self.__class__.__name__))

    def __neg__(self):
        return self.__class__(x=self.x, d=-self.d)

    def __getitem__(self, i=None):
        if isinstance(i, Number):
            return (self.x[i], self.d[i])
        else:
            return self.__class__(x=self.x[i], d=self.d[i])

    def __iter__(self):
        return zip(self.x, self.d)

    def __eq__(self, other):
        if np.all(self._x == other._x) and \
                np.all(self._d == other._d):
            return True
        else:
            return False

        #   Warning :  __next__ and __iter__ is a bad practice
        #   Iterables are not iterators
        #   def __next__(self):

    def __repr__(self):
        return 'x = {}\nd = {}'. \
            format(self.x.__repr__(), self.d.__repr__())

    def _repr_html_(self):

        import xml.etree.ElementTree as ET
        root = ET.Element('div')
        # ET.SubElement(root, 'style').text="table,td,th,tbody{border:0px;}"
        pre = ET.SubElement(root, 'p')
        code = ET.SubElement(pre, 'code')
        code.text = self.__class__.__name__
        ET.SubElement(pre, 'br')

        res = ET.SubElement(pre, 'p')
        table = ET.SubElement(res, 'table', {'style': 'border: 0px none;'})
        tbody = ET.SubElement(table, 'tbody')
        for _i, _v in enumerate('nxd'):
            if _i == 0:
                tr = ET.SubElement(tbody, 'tr', {'style': 'border:0px none;\
                border-bottom:1px solid #C0C0C0;background:none;'})
                ET.SubElement(tr, 'th', {'style': 'border:0px none;\
                background:none;'})
                for _node in islice(np.arange(len(self)), 15):
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(_node)
                if len(self) > 16:
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = "..."
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self) - 1)
                elif len(self) > 15:
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self) - 1)
            else:
                tr = ET.SubElement(tbody, 'tr')
                _e = getattr(self, _v)
                td = ET.SubElement(tr, 'td')
                b = ET.SubElement(td, 'b')
                b.text = _e.label if _e.label is not None else "Label"
                span = ET.SubElement(td, 'span')
                span.text = " [{}]".format(_e.unit if _e.unit is
                                                      not None else "unit")

                for _node in islice(_e, 15):
                    ET.SubElement(tr, 'td').text = str(_node)
                if len(self) > 16:
                    ET.SubElement(tr, 'td').text = "..."
                    ET.SubElement(tr, 'td').text = str(_e[-1])
                elif len(self) > 15:
                    ET.SubElement(tr, 'td').text = str(_e[-1])

        return str(ET.tostring(root, encoding='utf-8'), 'utf-8')

    def __str__(self):
        """
        """
        o = ""
        o += "\t".join(map(str, self.x))
        o += "\n"
        o += "\t".join(map(str, self.d))
        return o

    def _sort(self, reverse=False):
        """Sorts the grid, ascending x values (default)

        Parameters
        ----------
        reverse: boolean
            Descending order values if True
        """
        if self.x is not None:
            o = self.x.argsort()
            self.x, self.d = self.x[o], self.d[o]

    def __call__(self, x, *args, **kwargs):
        """Best results with numpy
        """
        if self.options['extrapolate']:
            return self.extrapolate(x=x, *args, **kwargs)
        else:
            return self.interpolate(x=x, *args, **kwargs)

    def push(self, x=None, d=None):
        """Pushes an element/array to the array

        Notes
        -----
        The element or the array is added and sorted inplace

        Parameters
        ----------
        x: single numeric, array, numpy.array
        d: single numeric, array, numpy.array

        """

        if x is not None and d is not None:
            x = np.ravel(x)
            d = np.ravel(d)
            # Indices des éléments uniquement dans x
            onlyInPushed = np.setdiff1d(x, self.x, assume_unique=True)
            try:
                eltsOrder = np.concatenate([np.where(x == __s)
                                            for __s in onlyInPushed],
                                           axis=1).flatten()
                x = x[eltsOrder]
                d = d[eltsOrder]
                # Unique
                [x, _o] = np.unique(x, return_index=True)
                d = d[_o]
                [self.x, indices] = self.x.push(x, return_index=True)
                self.d = self.d.push(d, unique=False)[indices]
            except:
                print("All elements already in orginal array")

        self._sort()

    def apply(self, f, axis="d", inplace=False):
        """Apply a function along axis

        Parameters
        ----------
        f : function
        axis: string
            "x" or "d"
        inplace: boolean
            True if you want the mesh1d to be modified inplace

        Returns
        -------
        Nothing or mesh1d
            Depends if inplace is set to False or True

        """
        if axis == "d":
            if inplace is True:
                self.d.apply(f, inplace)
            else:
                return mesh2d(self.x, self.d.apply(f))
        elif axis == "x":
            if inplace is True:
                self.x.apply(f, inplace)
            else:
                return mesh2d(self.x.apply(f), self.d)
        else:
            print("apply used on non existing axis")

    def diff(self, n=1):
        """
        Checked
        """
        return self.__class__(self.x[:-n],
                              self.d.diff(n=n))

    def dropnan(self):
        """
        Checked
        """
        return self[~np.isnan(self.x)]

    def min(self, x=False):
        """Returns the min value of the d-axis.
        If x is set to True, returns a tuple containing
        (min(d), x where d is min)

        Parameters
        ----------
        x : boolean
        """
        if x is True:
            _x = self.d.argmin()
            return (self.x[_x], self.d[_x])
        return min(self.d)

    def max(self, x=False):
        """Returns the max value of the d-axis.
        If x is set to True, returns a tuple containing
        (max(d), x where d is max)

        Parameters
        ----------
        x : boolean
        """
        if x is True:
            _x = self.d.argmax()
            return (self.x[_x], self.d[_x])
        else:
            return max(self.d)

    def mean(self, *args, **kwargs):
        return self.d.mean(*args, **kwargs)

    def median(self, *args, **kwargs):
        return self.d.median(*args, **kwargs)

    def interpolate(self, x, assume_sorted=False, *args, **kwargs):
        """Purpose of this method is to return a linear interpolation
        of a d vector for an unknown value x. If the targeted value
        is out of the x range, the returned d-value is the first,
        resp. the last d-value.

        No interpolation is made out of the x definition range. For such
        a functionality, use:py:meth:`extrapolate` instead.

        Parameters
        ----------
        x:: iterable or single element,

        kind: str or int, optional
        Specifies the kind of interpolation as a string ('linear', 'nearest',
        'zero', 'slinear', 'quadratic', 'cubic' where 'slinear', 'quadratic'
        and 'cubic' refer to a spline interpolation of first, second or third
        order) or as an integer specifying the order of the spline
        interpolator to use. Default is 'linear'.

        Returns
        -------
        A single element or a :class:`numpy.array` if the x parameter was
        a :class:`numpy.array` or a list
        """
        # Code from scipy.interpolate.interp1d
        if not assume_sorted:
            self._sort()

        try:
            if isinstance(x, (np.ndarray, list, range)):
                return interp2d(x, self.x, self.d)

            else:
                return interp2d(np.array([x]), self.x, self.d)[0]
        except:
            raise TypeError("{} interpolation not implemented in {}". \
                            format(x.__class__.__name__,
                                   self.__class__.__name__))

    def step(self, x, **kwargs):
        """
        """

        i = np.searchsorted(self.x, x)
        condlist = [np.in1d(x, self.x), i > 1]
        choicelist = [i, i - 1]
        i = np.select(condlist, choicelist)

        return self.d[i]

    @property
    def steps(self):
        return self._steps

    #    @steps.setter
    #    def steps(self, value):
    #        self._steps = deepcopy(self)
    #        self._steps.__call__ = self._steps.step

    def extrapolate(self, x, *args, **kwargs):
        """np.interp function with linear extrapolation
        np.polyfit
        np.poly1d
        """
        if len(args) > 0:
            res = []
            res.append(self._extrapolate(x, **kwargs))
            for elt in args:
                res.append(self._extrapolate(elt, **kwargs))
            res = tuple(res)
        else:
            if isinstance(x, (np.ndarray, list, range)):
                res = []
                for elt in x:
                    res.append(self._extrapolate(elt, **kwargs))
                res = np.array(res)
            else:
                res = self._extrapolate(x, **kwargs)
        return res

    def _extrapolate(self, x, *args, **kwargs):
        """
        """
        if 'step' in kwargs and kwargs['step'] is True:
            return self.step(x, **kwargs)

        if x <= self.x[0]:
            res = self.d[0] + (x - self.x[0]) * \
                              (self.d[1] - self.d[0]) / (self.x[1] - self.x[0])
        elif x >= self.x[-1]:
            res = self.d[-1] + (x - self.x[-1]) * \
                               (self.d[-1] - self.d[-2]) / (self.x[-1] - self.x[-2])
        else:
            res = np.interp(x, self.x, self.d)

        return float(res)

    # Plot CUR with matplotlib
    @myPlot
    def plot(self, *args, **kwargs):
        """
        Permet de tracer un diagramme
        """
        return

    def polyfit(self, degree=2):
        return polymesh2d(p=np.polyfit(self.x, self.d, degree),
                          x_label=self.x.label, x_unit=self.x.unit,
                          y_label=self.d.label, y_unit=self.d.unit)

    def read_clipboard(self):

        def _en_col(s):
            import re
            _res = re.findall(r'[\-\+\d\.]+', s)
            self.x = mesh1d([float(a) for (i, a)
                             in enumerate(_res) if not i % 2],
                            self.x.label, self.x.unit)
            self.d = mesh1d([float(a) for (i, a) in enumerate(_res) if i % 2],
                            self.d.label, self.d.unit)

        def _en_ligne(s):
            # En colonne
            s = s.split('\r\n')
            if len(s) == 2:
                self.x = mesh1d([float(a) for a in s[0].split('\t')],
                                self.x.label, self.x.unit)
                self.d = mesh1d([float(a) for a in s[1].split('\t')],
                                self.d.label, self.d.unit)

        def get_clipboard():
            import win32clipboard
            try:
                win32clipboard.OpenClipboard()
                data = win32clipboard.GetClipboardData()
                win32clipboard.CloseClipboard()
                return data
            except:
                print("No data in the clipboard")

        s = get_clipboard().strip()

        lineBr = '\r\n'
        dataSep = '\t'

        if s.count('.') == 0 and s.count(',') > 0:
            s = s.replace(",", '.')

        # S'il y a des points dans le presse papier,
        # on remplace les virgules par des tabulations
        if s.count(',') > 0 and s.count('.') > 0:
            s = s.replace(",", dataSep)
        elif s.count('\t') == 0 and s.count(' ') > 0:
            s = s.replace(' ', dataSep)
        elif s.count('\t') == 0 and s.count(';') > 0:
            s = s.replace(';', dataSep)

        if 1 <= s.count(lineBr) <= 2:
            _en_ligne(s)
        elif s.count(lineBr) == s.count(dataSep):
            _en_col(s)
        elif (s.count(lineBr) + 1) == s.count(dataSep) \
                and not s.endswith(lineBr):
            _en_col(s)
        else:
            print("Pas importable")

    def resample(self, x):
        return self.__class__(x=mesh1d(x, **self.x.__dict__),
                              d=self.d.__class__(self(x), **self.d.__dict__))

    def to_clipboard(self, transpose=False, decimal=","):
        def set_clipboard(text):
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text.encode('utf-8'),
                                            win32clipboard.CF_TEXT)
            win32clipboard.SetClipboardText(text,
                                            win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()

        set_clipboard('\r\n'.join([str(_x) + '\t' + str(_y) for (_x, _y) in zip(self.x, self.d)]).replace('.', decimal))

    def to_csv(self, fileName=None, nbreDecimales=2):
        """
        Export CUR data into csv

        Parameters
        ----------
        fileName : String
            Complete path + filename where csv data will be wrote.
            Default to \'C:/temp/aze.csv\'

        nbreDecimales : integer
        """
        import csv

        with open(fileName, 'w') as f:
            writer = csv.writer(f, dialect=csv.excel_tab, delimiter=';')
            # writes header

            # writes channel names
            writer.writerow([self.x.label, self.d.label])
            # writes units
            writer.writerow([self.x.unit, self.d.unit])

            buf = np.vstack([self.x.transpose(), np.round(self.d.transpose(),
                                                          nbreDecimales)])

            buf = buf.transpose()
            #   Write all rows
            r, c = buf.shape
            for i in range(r):
                writer.writerow(buf[i, :])

        f.close()

    def _init_gradient(self):
        _d = np.diff(self.x)
        self._gradient = mesh2d(self.x, np.gradient(self.d, np.concatenate((_d, [_d[-1]]))))

    def gradient(self, x=None):
        if self._gradient is None:
            self._init_gradient()
        if x is None:
            return self._gradient
        else:
            return self._gradient(x)

    @property
    def T(self):
        myObj = deepcopy(self)
        myObj.d, myObj.x = myObj.x, myObj.d
        myObj._sort()
        return myObj

    @property
    def difff(self):
        return np.diff(self.d) / np.diff(self.x)


# Define a MAP object<br/>
# @brief The class can be instanced CR.MAP(x, Y, W):
#      - either with a tuple a data (x, Y, W)
#      - either by parsing a label in a file
#
# @param x           x data of the MAP
# @param Y           Y data of the MAP
# @param W            W data of the MAP
#
# The form of the data should look like: <br/>
# @verbatim
#       (y y y ... y)
#  (x)  (W W W ... W)
#  (x)  (W W W ... W)
# (...) (W W W ... W)
#  (x)  (W W W ... W)
#  (x)  (W W W ... W)
# @endverbatim


############################################################################
# CLASSE mesh3d
############################################################################
class mesh3d(mesh):
    """
    Interpolate over a 2-D grid.

    `x`, `y` and `W` are arrays of values used to approximate some function
    f: ``W = f(x, y)``. This class returns a function whose call method uses
    spline interpolation to find the value of new points.

    Parameters
    ----------
    x : array_like

    Y : array_like
        Arrays defining the data point coordinates.

        If the points lie on a regular grid, `x` can specify the column
        coordinates and `Y` the row coordinates

    Examples
    --------
    Construct a 2-D grid and interpolate on it:

    .. code-block:: python

        from scipy import interpolate
        x = np.arange(-5.01, 5.01, 0.25)
        y = np.arange(-5.01, 5.01, 0.25)
        xx, yy = np.meshgrid(x, y)
        z = np.sin(xx**2+yy**2)

    """

    def __add__(self, other):

        if isinstance(other, mesh2d):
            if np.all(self._x == other.x):
                _z = self.d + other.y.reshape(len(other), 1)
            elif np.all(self._y == other.x):
                _z = self.d + other.y.reshape(1, len(other))
            else:
                raise TypeError("Object dimension not homogeneous in __add__.")
            return self.__class__(self._x, self._y, _z,
                                  self.label, self.unit, **self.options)
        if isinstance(other, Number):
            return self.__class__(self._x, self._y, self.d + other,
                                  self.label, self.unit, **self.options)

        X = mesh1d(np.sort(np.unique(np.concatenate((self._x, other._x)))),
                   self.x.label,
                   self.x.unit)
        Y = mesh1d(np.sort(np.unique(np.concatenate((self._y, other._y)))),
                   self._y.label,
                   self._y.unit)

        W = np.zeros((X.size, Y.size))

        for (i, x) in enumerate(X):
            for (j, y) in enumerate(Y):
                W[i][j] = self(x, y) + other(x, y)

        return self.__class__(X, Y, W, self.label, self.unit)

    def __sub__(self, obj):
        return self.__add__(-obj)

    def __mul__(self, obj):
        """
        """
        new_args = deepcopy(self.__dict__)
        if isinstance(obj, Number):
            # Casting rule from numpy
            new_args['d'] = np.multiply(self.d, obj)
            return self.__class__(**new_args)
        else:
            logger.warning("Multiplying {} to {} failed".format(
                obj.__class__.__name__,
                self.__class__.__name__))

    def __truediv__(self, obj):
        """
        """
        new_args = deepcopy(self.__dict__)
        if isinstance(obj, Number):
            # Casting rule from numpy
            new_args['d'] = np.divide(self.d, obj)
            return self.__class__(**new_args)
        else:
            logger.warning("Multiplyng {} to {} failed".format(
                obj.__class__.__name__,
                self.__class__.__name__))

    def __call__(self, x=None, y=None, *args, **kwargs):
        """Interpolate the function.

        Parameters
        ----------
        x : 1D array
            x-coordinates of the mesh on which to interpolate.
        y : 1D array
            y-coordinates of the mesh on which to interpolate.

        Returns
        -------
            2D array with shape (len(x), len(y))
            The interpolated values.

        """
        if self.options['extrapolate']:
            return self.extrapolate(x=x, y=y, *args, **kwargs)
        else:
            return self.interpolate(x=x, y=y, *args, **kwargs)

    def __eq__(self, other):
        if self._x == other._x and \
                        self._y == other._y and \
                np.all(self.d == other.d):
            if self.label != other.label:
                print("Labels are differents : {0.label} / {1.label}".format(self, other))
            if self.unit != other.unit:
                print("Units are differents : {0.unit} / {1.unit}".format(self, other))
            return True
        else:
            return False

    def __iter__(self):
        """

        :return: x[i], y[j], (i,j), w[i, j]
        """
        for (i, j), elem in np.ndenumerate(self.d):
            yield (self.x[i], self.y[j], (i, j), elem)

    def __init__(self, x=None, y=None, w=None,
                 x_label=None, x_unit=None,
                 y_label=None, y_unit=None,
                 label=None, unit=None,
                 extrapolate=True, clipboard=False,
                 sort=True, *pargs, **kwargs):
        """
        x -> row (index 0 of W)
        Y -> column (index 1 of W)
        W -> Z values
        
        Z
          Z
            Z
               Y   Y   Y   Y
              X   
              X
              X
              X
              X
        
        """

        self.label = label
        self.unit = unit

        self.options = {}
        self.options['extrapolate'] = extrapolate

        self._x = mesh1d(x, label=x_label, unit=x_unit) if "_x" not in kwargs \
            else kwargs["_x"]

        self._y = mesh1d(y, label=y_label, unit=y_unit) if "_y" not in kwargs \
            else kwargs["_y"]

        if "d" not in kwargs:
            self.d = np.empty((self.x.size, self.y.size)) if w is None else \
                np.asfarray(w, dtype='float64')
        else:
            self.d = kwargs["d"]

        if clipboard is True:
            self.read_clipboard()

        self.reshape(sort=sort)

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, obj):
        self._x = self._x.__class__(obj, **self._x.__dict__)

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, obj):
        self._y = self._y.__class__(obj, **self._y.__dict__)

    def __neg__(self):
        """
        """
        return self.__class__(x=self._x, y=self._y, w=-self.d,
                              label=self.label, unit=self.unit)

    def _repr_html_(self):
        """
        """
        import xml.etree.ElementTree as ET
        root = ET.Element('div')
        pre = ET.SubElement(root, 'p')
        code = ET.SubElement(pre, 'code')
        code.text = self.__class__.__name__ + ": "
        b = ET.SubElement(pre, 'b')
        b.text = self.label or "Label"
        span = ET.SubElement(pre, 'span')
        span.text = " [{}]".format(self.unit or "unit")
        ET.SubElement(pre, 'br')

        res = ET.SubElement(pre, 'p')
        table = ET.SubElement(res, 'table', {'style': _html_style['none'], 'class': 'mesh3d'})
        tbody = ET.SubElement(table, 'tbody')

        for _a in np.arange(3):
            if _a == 0:
                tr = ET.SubElement(tbody, 'tr', {'style': _html_style['none']})
                ET.SubElement(tr, 'th', {'colspan': '3', 'style': _html_style['none']})
                td = ET.SubElement(tr, 'th', {'colspan': str(len(self._y)),
                                              'style': _html_style['none']})
                ET.SubElement(td, 'b').text = self._y.label or "Label"
                ET.SubElement(td, 'span').text = " [{}]".format(
                    self._y.unit or "Unit")
            elif _a == 1:
                #                ET.SubElement(tr, 'th').text = str(self._x[_i])

                tr = ET.SubElement(tbody, 'tr', {'style': _html_style['none']})
                ET.SubElement(tr, 'th', {'colspan': '3', 'style': _html_style['none']})
                for _node in islice(np.arange(len(self._y)), 15):
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(_node)
                if len(self._y) > 16:
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = "..."
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self._y) - 1)
                elif len(self._y) > 15:
                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(len(self._y) - 1)

                tr = ET.SubElement(tbody, 'tr', {'style': _html_style['none']})
                ET.SubElement(tr, 'th', {'colspan': '3', 'style': _html_style['none']})
                for _node in islice(self._y, 15):
                    ET.SubElement(tr, 'th').text = str(_node)
                if len(self._y) > 16:
                    ET.SubElement(tr, 'th').text = "..."
                    ET.SubElement(tr, 'th').text = str(self._y[-1])
                elif len(self._y) > 15:
                    ET.SubElement(tr, 'th').text = str(self._y[-1])


            else:
                for _i, _v in enumerate(self._x):
                    tr = ET.SubElement(tbody, 'tr', {'style': 'border: 0px solid'})
                    if _i == 0:
                        td = ET.SubElement(tr, 'th', {'rowspan': str(len(self._x)),
                                                      'style': _html_style['none']})
                        ET.SubElement(td, 'b', {'style': _html_style['none']}).text = self._x.label or "Label"
                        ET.SubElement(td, 'span', {'style': _html_style['none']}).text = " [{}]".format(
                            self._x.unit or "Unit")

                    ET.SubElement(tr, 'th', {'style': _html_style['th']}).text = str(_i)
                    ET.SubElement(tr, 'th').text = str(self._x[_i])

                    for _node in islice(self.d[_i], 15):
                        ET.SubElement(tr, 'td').text = str(_node)
                    if len(self._y) > 16:
                        ET.SubElement(tr, 'td').text = "..."
                        ET.SubElement(tr, 'td').text = str(self.d[_i][-1])
                    elif len(self._y) > 15:
                        ET.SubElement(tr, 'td').text = str(self.d[_i][-1])

        return str(ET.tostring(root, encoding='utf-8'), 'utf-8')

    def __getitem__(self, sl):
        """
        """
        global isXslice
        isXslice = False
        global isYslice
        isYslice = False

        def _get_m2d(slx, slw):
            return mesh2d(x=slx, y=mesh1d(slw, self.label, self.unit), extrapolate=self.options['extrapolate'])

        try:
            if len(sl) == 2:
                slx, sly = sl
                if isinstance(slx, slice) or isinstance(slx, list) or isinstance(slx, np.ndarray):
                    isXslice = len(self.x[slx]) > 1 or False
                if isinstance(sly, slice) or isinstance(sly, list) or isinstance(sly, np.ndarray):
                    isYslice = len(self.y[sly]) > 1 or False
        except:
            slx, sly = sl, slice(None, None, None)
            if isinstance(slx, slice):
                isXslice = len(self.x[slx]) > 1 or False
            isYslice = True

        if isXslice and isYslice:
            return self.__class__(x=self._x[slx], y=self._y[sly],
                                  w=self.d[slx, sly], label=self.label,
                                  unit=self.unit, extrapolate=self.options['extrapolate'])
        elif not isXslice and isYslice:
            return _get_m2d(self._y[sly], self.d[slx, sly])
        elif isXslice and not isYslice:
            return _get_m2d(self._x[slx], self.d[slx, sly])
        else:
            return (self._x[slx].flatten()[0], self._y[sly].flatten()[0],
                    self.d[slx, sly].flatten()[0])

    def __str__(self):
        """
        """
        res = "\t"
        res += "\t".join(map(str, self.y))
        if len(self.x):
            res += "\n"
        for index in range(0, len(self.x)):
            res += str(self.x[index])
            res += "\t"
            res += "\t".join(map(str, self.d[index]))
            res += "\n"
        return res

    def apply(self, f, inplace=False):
        if inplace is False:
            X = self.x.copy()
            Y = self.y.copy()
            W = self.d.copy()
        else:
            X = self.x
            Y = self.y
            W = self.d

        for d, v in np.ndenumerate(W):
            W[d] = f(W[d])

        if inplace is False:
            return mesh3d(X, Y, W, self.label, self.unit)

    def pop(self, axis=0):
        axisLenght = np.ma.size(self.d, axis=axis)
        if axisLenght > 1:
            W = self.d.take(-1, axis=axis)
            self.d = self.d.take(np.arange(axisLenght - 1), axis=axis)
            if axis == 0:
                self.x, popped = self.x.pop()
            else:
                self.y, popped = self.y.pop()

            return popped, W
        else:
            print("axis {} to small to pop".format({0: 'x', 1: 'y'}.get(axis)))

    def interpolate(self, x=None, y=None):
        """"""
        isxN = isinstance(x, Number)
        isyN = isinstance(y, Number)

        # x and y are numeric
        if isxN & isyN:
            if x <= self.x[0]:
                return np.interp(y, self.y, self.d[0])
            elif x >= self.x[-1]:
                return np.interp(y, self.y, self.d[-1])
            else:
                iX = np.searchsorted(self.x, x) - 1

            if y <= self.y[0]:
                return np.interp(x, self.x, self.d[:, 0])
            elif y >= self.y[-1]:
                return np.interp(x, self.x, self.d[:, -1])
            else:
                iY = np.searchsorted(self.y, y) - 1

            Z1 = self.d[iX, iY] + (self.d[iX, iY + 1] - self.d[iX, iY]) * \
                                  (y - self.y[iY]) / (self.y[iY + 1] \
                                                      - self.y[iY])
            Z2 = self.d[iX + 1, iY] + \
                 (self.d[iX + 1, iY + 1] - self.d[iX + 1, iY]) * \
                 (y - self.y[iY]) / (self.y[iY + 1] - self.y[iY])

            return Z1 + (Z2 - Z1) * (x - self.x[iX]) / \
                        (self.x[iX + 1] - self.x[iX])
        # x or y are numeric
        elif isxN | isyN:
            if isxN:
                y = self._y if y is None \
                    else self._y.__class__(y, **self._y.__dict__)
                return mesh2d(y, mesh1d([self.interpolate(x, _y) for _y in y],
                                        self.label, self.unit))
            else:
                x = self._x if x is None \
                    else self._x.__class__(x, **self._x.__dict__)
                return mesh2d(x, mesh1d([self.interpolate(_x, y) for _x in x],
                                        self.label, self.unit))
        # Either x nor y are numeric
        else:
            x = self._x if x is None else self._x.__class__(x,
                                                            **self._x.__dict__)
            y = self._y if y is None else self._y.__class__(y,
                                                            **self._y.__dict__)
            _, tx, _, ty, c, _, _ = dfitpack.regrid_smth(self._x, self._y,
                                                         np.ravel(self.d),
                                                         kx=1, ky=1)

            return self.__class__(x=x, y=y,
                                  w=[fitpack.bisplev(_x, _y, (tx, ty, c, 1, 1)) \
                                     for _x, _y in product(x, y)],
                                  label=self.label, unit=self.unit)

    def extrapolate(self, x, y):
        """"""
        isxN = isinstance(x, Number)
        isyN = isinstance(y, Number)

        # x and y are numerics
        if isxN & isyN:
            if x <= self.x[0]:
                iX = 0
            elif x >= self.x[-1]:
                iX = -2
            else:
                iX = np.searchsorted(self.x, x) - 1

            if y <= self.y[0]:
                iY = 0
            elif y >= self.y[-1]:
                iY = -2
            else:
                iY = np.searchsorted(self.y, y) - 1

            Z1 = self.d[iX, iY] + (self.d[iX, iY + 1] - self.d[iX, iY]) * \
                                  (y - self.y[iY]) / (self.y[iY + 1] - self.y[iY])
            Z2 = self.d[iX + 1, iY] + (self.d[iX + 1, iY + 1] - self.d[iX + 1, iY]) * \
                                      (y - self.y[iY]) / (self.y[iY + 1] - self.y[iY])

            return Z1 + (Z2 - Z1) * (x - self.x[iX]) / (self.x[iX + 1] - self.x[iX])
        # x or y is numeric
        elif isxN | isyN:
            # Save extrapolate status in options before setting to True
            extrapolate = self.options['extrapolate']
            self.options['extrapolate']
            if isxN:
                y = self._y if y is None else self._y.__class__(y, **self._y.__dict__)
                res = mesh2d(y, mesh1d([self(x, _y) for _y in y],
                                       self.label, self.unit))
                self.options['extrapolate'] = extrapolate
                return res
            else:
                x = self._x if x is None else self._x.__class__(x, **self._x.__dict__)
                res = mesh2d(x, mesh1d([self(_x, y) for _x in x],
                                       self.label, self.unit))
                self.options['extrapolate'] = extrapolate
                return res
                # Either x nor y is numeric
        else:
            x = self._x if x is None else self._x.__class__(x, **self._x.__dict__)
            y = self._y if y is None else self._y.__class__(y, **self._y.__dict__)

            return self.__class__(x=x, y=y,
                                  w=[self.extrapolate(_x, _y) for _x, _y in product(x, y)],
                                  label=self.label, unit=self.unit)

    def from_pandas(self, obj):
        self.__init__(x=obj.index.astype(float), x_label=self.x.label,
                      x_unit=self.x.unit, y=obj.columns.astype(float),
                      y_label=self.y.label, y_unit=self.y.unit,
                      w=[np.array(obj.loc[_o]) for _o in obj.index],
                      label=self.label, unit=self.unit)

    # Plot MAP as PDF in filename
    def plot(self, xy=False, filename=None, **kwargs):

        import matplotlib.pyplot as plt

        if self.label is None:
            self.label = ""
        if self.unit is None:
            self.unit = ""

        plt.xlabel(self.y.label + ' [' + self.y.unit + ']' if self.y.label is not None else 'Label' + ' [' + ']')
        plt.ylabel(self.label + ' [' + self.unit + ']')

        for _i, _x in enumerate(self.x):
            # print("plot {}".format(_x))
            self[_i].plot('-', linewidth=1,
                          label=u"{} {}".format(_x, self.x.unit), **kwargs)

        plt.legend(loc=2, borderaxespad=0., frameon=0)

        if filename is not None:
            print("Save file as " + filename)
            plt.savefig(filename, bbox_inches='tight')

    # TODO : check dtype
    def push(self, s=None, d=None, axis=0, inplace=False):
        # s: support point ; d = data (np.array de dimension n * 1)

        _axe = self.y if axis == 1 else self.x
        w2add = np.zeros((len(self.x if axis == 1 else self.y)))
        w2add.put(np.arange(len(d)), d)

        if s not in _axe:
            at = np.searchsorted(_axe, s)
            if axis == 1:
                self.y = _axe.insert(at, s)
            else:
                self.x = _axe.insert(at, s)

            if self.d.size > 0:
                self.d = np.insert(self.d, at, w2add, axis=axis)
            else:
                self.d = [np.array(w2add)]
        else:
            print("push: Value already defined at {}".format(s))

        self.reshape()

    def read_clipboard(self):

        import pandas as pd
        s = pd.read_clipboard(index_col=0, decimal=",")
        self.from_pandas(s)

    def reshape(self, sort=True):
        if len(self.x) > 0:
            self.d = np.reshape(self.d, (len(self.x), -1))
        if sort is True:
            self.sort()

    def sort(self):
        # Code from interp2d
        if not np.all(self._x[1:] >= self._x[:-1]):
            j = np.argsort(self._x)
            self._x = self._x[j]
            self.d = self.d[j, :]
        if not np.all(self._y[1:] >= self._y[:-1]):
            j = np.argsort(self._y)
            self._y = self._y[j]
            self.d = self.d[:, j]

    def to_gpt(self, fileName=None):
        for _y in self.y:
            print("#", str(_y))
            for _x in self.x:
                print(_x, self(_x, _y))
            print("e")

    @property
    def T(self):
        return self.__class__(x=self._y, y=self._x, w=self.d.T,
                              label=self.label, unit=self.unit,
                              **self.options)

    # Important : non sort!
    def diff(self, axis=0, n=1):
        return self.__class__(x=np.diff(self._x, n=n) if axis == 0 else self._x,
                              y=np.diff(self._y, n=n) if axis == 1 else self._y,
                              w=np.diff(self.d, axis=axis, n=n),
                              label=self.label, unit=self.unit,
                              sort=False)


############################################################################
# CLASSE mesh4d
############################################################################
class mesh4d(mesh):
    """
    """

    def __init__(self,
                 x=None, y=None, z=None, d=None,
                 x_label=None, x_unit=None,
                 y_label=None, y_unit=None,
                 z_label=None, z_unit=None,
                 label=None, unit=None,
                 extrapolate=False, dtype='float64'):

        self.label = label
        self.unit = unit

        self.options = {}
        self.options['extrapolate'] = extrapolate

        self._x = mesh1d(x, label=x_label, unit=x_unit)
        self._y = mesh1d(y, label=y_label, unit=y_unit)
        self._z = mesh1d(z, label=z_label, unit=z_unit)
        self.d = np.zeros((self._x.size, self._y.size, self._z.size)) if d is None else \
            np.asfarray(d, dtype=dtype)

        self.reshape()

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, obj):
        self._x = self._x.__class__(obj, **self._x.__dict__)

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, obj):
        self._y = self._y.__class__(obj, **self._y.__dict__)

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, obj):
        self._z = self._z.__class__(obj, **self._z.__dict__)

    @property
    def shape(self):
        return self.d.shape

    def __add__(self, other):
        return self.__class__(x=self._x, y=self._y, z=self._z,
                              d=self.d + other, label=self.label,
                              unit=self.unit, **self.options)

    def __sub__(self, obj):
        return self.__add__(-obj)

    def __neg__(self):
        """
        """
        return self.__class__(x=self._x, y=self._y, z=self._z,
                              d=-self.d, label=self.label,
                              unit=self.unit, **self.options)

    def __eq__(self, other):
        if self._x == other._x and \
                        self._y == other._y and \
                        self._z == other._z and \
                np.all(self.d == other.d):
            if self.label != other.label:
                print("Labels are differents : {0.label} / {1.label}".format(self, other))
            if self.unit != other.unit:
                print("Units are differents : {0.unit} / {1.unit}".format(self, other))
            return True
        else:
            return False

    def __getitem__(self, sl):
        """
        """
        global isXslice
        isXslice = False
        global isYslice
        isYslice = False
        global isZslice
        isZslice = False

        def _get_m2d(slx, slw):
            return mesh2d(x=slx, y=mesh1d(slw, self.label, self.unit),
                          extrapolate=self.options['extrapolate'])

        def _get_m3d(slx, sly, w):
            return mesh3d(x=slx, y=sly, w=w,
                          label=self.label, unit=self.unit,
                          extrapolate=self.options['extrapolate'])

        try:
            if len(sl) == 2:
                slx, sly = sl
                slz = slice(None, None, None)
            elif len(sl) == 3:
                slx, sly, slz = sl

            if isinstance(slx, slice):
                isXslice = len(self.x[slx]) > 1 or False
            if isinstance(sly, slice):
                isYslice = len(self.y[sly]) > 1 or False
            if isinstance(slz, slice):
                isZslice = len(self.z[slz]) > 1 or False

        except:
            slx, sly, slz = sl, slice(None, None, None), slice(None, None, None)
            if isinstance(slx, slice):
                isXslice = len(self.x[slx]) > 1 or False
            isYslice = True
            isZslice = True

        if isXslice and isYslice and isZslice:
            return self.__class__(x=self._x[slx], y=self._y[sly], z=self._z[slz],
                                  d=self.d[slx, sly, slz], label=self.label,
                                  unit=self.unit, extrapolate=self.options['extrapolate'])

        elif isXslice and isYslice and not isZslice:
            return _get_m3d(self._x[slx], self._y[sly], self.d[slx, sly, slz])
        elif isXslice and not isYslice and isZslice:
            return _get_m3d(self._x[slx], self._z[slz], self.d[slx, sly, slz])
        elif not isXslice and isYslice and isZslice:
            return _get_m3d(self._y[sly], self._z[slz], self.d[slx, sly, slz])

        elif isXslice and not isYslice and not isZslice:
            return _get_m2d(self._x[slx], self.d[slx, sly, slz])
        elif not isXslice and isYslice and not isZslice:
            return _get_m2d(self._y[sly], self.d[slx, sly, slz])
        elif not isXslice and not isYslice and isZslice:
            return _get_m2d(self._z[slz], self.d[slx, sly, slz])

        else:
            return self.d[slx, sly, slz]

    def __call__(self, x=None, y=None, z=None, *args, **kwargs):
        """Best results with numpy
        """
        if self.options['extrapolate']:
            logger.warning("Extrapolation not implented in {}".format(self.__class__.__name__))
            return self.interpolate(x=x, y=y, z=z, *args, **kwargs)
        else:
            return self.interpolate(x=x, y=y, z=z, *args, **kwargs)

    def reshape(self):
        if len(self._x) > 0:
            self.d = np.reshape(self.d,
                                (len(self._x), len(self._y), len(self._z)))
        self.sort()

    def sort(self):
        # Code from interp2d
        if not np.all(self._x[1:] >= self._x[:-1]):
            j = np.argsort(self._x)
            self._x = self._x[j]
            self.d = self.d[j, :, :]
        if not np.all(self._y[1:] >= self._y[:-1]):
            j = np.argsort(self._y)
            self._y = self._y[j]
            self.d = self.d[:, j, :]
        if not np.all(self._z[1:] >= self._z[:-1]):
            j = np.argsort(self._z)
            self._z = self._z[j]
            self.d = self.d[:, :, j]

            # s: support point ; d = object curve ou MAP

    def push(self, s=None, d=None, axis=0):
        # TODO : check type

        # From the axis number, get the corresponding
        # attribute x,y or z from self
        wA = axeConv.get(axis)
        _axis = getattr(self, wA)

        # TODO: check that every (x,y) from mesh3d to add are the same as the 
        if len(self.x) == 0:
            self.x = d.x

        if len(self.y) == 0:
            self.y = d.y

        if s not in _axis:
            at = np.searchsorted(_axis, s)
            setattr(self, wA, _axis.insert(at, s))

            if self.d.size > 0:
                if self.d.take(0, axis=axis).shape != d.d.shape:
                    raise TypeError("Shape of d ({}) not compliant with self's \
                    data shape ({})".format(self.d.take(at, axis=axis).shape,
                                            d.shape))
                if at >= np.size(self.d):
                    np.append(self.d, d.d, axis=axis)
                else:
                    self.d = np.insert(self.d, at, d.d, axis=axis)
            else:
                self.d = np.ravel(d.d)
        else:
            print("push: Value already defined at {}".format(s))

        self.reshape()

    def interpolate(self, x=None, y=None, z=None):
        """a
        """

        isxN = isinstance(x, Number)
        isyN = isinstance(y, Number)
        iszN = isinstance(z, Number)

        # x, y and z are numeric
        if isxN & isyN & iszN:
            if x <= self.x[0]:
                return self[0].interpolate(y, z)
            elif x >= self.x[-1]:
                return self[-1].interpolate(y, z)
            else:
                iX = np.searchsorted(self.x, x) - 1

            if y <= self.y[0]:
                return self[:, 0].interpolate(x, z)
            elif y >= self.y[-1]:
                return self[:, -1].interpolate(x, z)
            else:
                iY = np.searchsorted(self.y, y) - 1

            if z <= self.z[0]:
                return self[:, :, 0].interpolate(x, y)
            elif z >= self.z[-1]:
                return self[:, :, -1].interpolate(x, y)
            else:
                iZ = np.searchsorted(self.z, z) - 1

            X1 = self.x[iX]
            X2 = self.x[iX + 1]
            Y1 = self.y[iY]
            Y2 = self.y[iY + 1]
            Z1 = self.z[iZ]
            Z2 = self.z[iZ + 1]
            Z111 = self.d[iX, iY, iZ]
            Z121 = self.d[iX, iY + 1, iZ]
            Z112 = self.d[iX, iY, iZ + 1]
            Z122 = self.d[iX, iY + 1, iZ + 1]
            Z211 = self.d[iX + 1, iY, iZ]
            Z221 = self.d[iX + 1, iY + 1, iZ]
            Z212 = self.d[iX + 1, iY, iZ + 1]
            Z222 = self.d[iX + 1, iY + 1, iZ + 1]

            # Reduction along Z
            Z11 = Z111 + (Z112 - Z111) * (z - Z1) / (Z2 - Z1)
            Z12 = Z121 + (Z122 - Z121) * (z - Z1) / (Z2 - Z1)
            Z21 = Z211 + (Z212 - Z211) * (z - Z1) / (Z2 - Z1)
            Z22 = Z221 + (Z222 - Z221) * (z - Z1) / (Z2 - Z1)

            # reduction along Y
            Z1 = Z11 + (Z12 - Z11) * (y - Y1) / (Y2 - Y1)
            Z2 = Z21 + (Z22 - Z21) * (y - Y1) / (Y2 - Y1)

            return Z1 + (Z2 - Z1) * (x - X1) / (X2 - X1)
        # x or y are numeric
        # TODO : ne marche pas à partir de là !!!!

        x = x if x is not None else self.x
        y = y if y is not None else self.y
        z = z if z is not None else  self.z

        test = {
            (True, True, False): "__import__('lerp').mesh2d(\
                __import__('lerp').mesh1d(z, **self.z.__dict__),\
                __import__('lerp').mesh1d([self(x,y,_z) for _z in z],\
                label=self.label, unit=self.unit), **self.options)",
            (True, False, True): "__import__('lerp').mesh2d(\
                __import__('lerp').mesh1d(y, **self.y.__dict__),\
                __import__('lerp').mesh1d([self(x,_y,z) for _y in y],\
                label=self.label, unit=self.unit), **self.options)",
            (False, True, True): "__import__('lerp').mesh2d(\
                __import__('lerp').mesh1d(x, **self.x.__dict__),\
                __import__('lerp').mesh1d([self(_x,y,z) for _x in x],\
                label=self.label, unit=self.unit), **self.options)",
            (True, False, False): "__import__('lerp').mesh3d(\
                __import__('lerp').mesh1d(y, **self.y.__dict__),\
                __import__('lerp').mesh1d(z, **self.z.__dict__),\
               [self(x,_y,_z) for _y, _z in  __import__('itertools').product(y,z)],\
                label=self.label, unit=self.unit, **self.options)",
            (False, True, False): "__import__('lerp').mesh3d(\
                __import__('lerp').mesh1d(x, **self.x.__dict__),\
                __import__('lerp').mesh1d(z, **self.z.__dict__),\
               [self(_x,y,_z) for _x, _z in  __import__('itertools').product(x,z)],\
                label=self.label, unit=self.unit, **self.options)",
            (False, False, True): "__import__('lerp').mesh3d(\
                __import__('lerp').mesh1d(x, **self.x.__dict__),\
                __import__('lerp').mesh1d(y, **self.y.__dict__),\
               [self(_x,_y,z) for _x, _y in  __import__('itertools').product(x,y)],\
                label=self.label, unit=self.unit, **self.options)",
        }

        return eval(test[(isxN, isyN, iszN)], {'self': self, 'x': x, 'y': y, 'z': z})

    def _repr_html_(self):
        import xml.etree.ElementTree as ET
        root = ET.Element('div')

        pre = ET.SubElement(root, 'p')
        ET.SubElement(pre, 'code').text = self.__class__.__name__ + ": "
        ET.SubElement(pre, 'b').text = self.label or "Label"
        span = ET.SubElement(pre, 'span').text = " [{}]".format(self.unit or "unit")
        ET.SubElement(pre, 'br')

        root.append(ET.fromstring(self.x._repr_html_()))
        root.append(ET.fromstring(self.y._repr_html_()))
        root.append(ET.fromstring(self.z._repr_html_()))

        # return self.x._repr_html_() + self.y._repr_html_() + self.z._repr_html_()
        return str(ET.tostring(root, encoding='utf-8'), 'utf-8')

    def read_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            os.path.exists(fileName)
            with open(fileName, 'rb') as f:
                # The protocol version used is detected automatically,
                # so we do not have to specify it.
                data = pickle.load(f)
            return data
        except:
            raise
            # raise FileNotFoundError("Please check your path, {} not found".\
            # format(fileName))

    def to_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            with open(fileName, 'wb') as f:
                pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)
        except:
            raise FileNotFoundError("Please check your path, {} not found". \
                                    format(fileName))


############################################################################
# CLASSE mesh5d
############################################################################
class mesh5d(mesh):
    """
    """

    def __init__(self,
                 x=None, y=None, z=None, v=None, d=None,
                 x_label=None, x_unit=None,
                 y_label=None, y_unit=None,
                 z_label=None, z_unit=None,
                 v_label=None, v_unit=None,
                 label=None, unit=None,
                 extrapolate=True, dtype='float64'):

        self.label = label
        self.unit = unit

        self.options = {}
        self.options['extrapolate'] = extrapolate

        self._x = mesh1d(x, label=x_label, unit=x_unit)
        self._y = mesh1d(y, label=y_label, unit=y_unit)
        self._z = mesh1d(z, label=z_label, unit=z_unit)
        self._v = mesh1d(v, label=v_label, unit=v_unit)
        self.d = np.zeros((self._x.size, self._y.size, self._z.size, self._v.size)) if d is None else \
            np.asfarray(d, dtype=dtype)

        self.reshape()

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, obj):
        self._x = self._x.__class__(obj, **self._x.__dict__)

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, obj):
        self._y = self._y.__class__(obj, **self._y.__dict__)

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, obj):
        self._z = self._z.__class__(obj, **self._z.__dict__)

    @property
    def v(self):
        return self._v

    @v.setter
    def v(self, obj):
        self._v = self._v.__class__(obj, **self._v.__dict__)

    @property
    def shape(self):
        return self.d.shape

    def __add__(self, other):
        return self.__class__(x=self._x, y=self._y, z=self._z,
                              v=self._v,
                              d=self.d + other, label=self.label,
                              unit=self.unit, **self.options)

    def __sub__(self, obj):
        return self.__add__(-obj)

    def __neg__(self):
        """
        """
        return self.__class__(x=self._x, y=self._y, z=self._z,
                              v=self._v,
                              d=-self.d, label=self.label,
                              unit=self.unit, **self.options)

    def reshape(self):
        if len(self._x) > 0:
            self.d = np.reshape(self.d,
                                (len(self._x), len(self._y),
                                 len(self._z), len(self._v)))
        self.sort()

    def sort(self):
        # Code from interp2d
        if not np.all(self._x[1:] >= self._x[:-1]):
            j = np.argsort(self._x)
            self._x = self._x[j]
            self.d = self.d[j, :, :]
        if not np.all(self._y[1:] >= self._y[:-1]):
            j = np.argsort(self._y)
            self._y = self._y[j]
            self.d = self.d[:, j, :]
        if not np.all(self._z[1:] >= self._z[:-1]):
            j = np.argsort(self._z)
            self._z = self._z[j]
            self.d = self.d[:, :, j]
        if not np.all(self._v[1:] >= self._v[:-1]):
            j = np.argsort(self._v)
            self._v = self._v[j]
            self.d = self.d[:, :, :, j]

    def _repr_html_(self):
        import xml.etree.ElementTree as ET
        root = ET.Element('div')

        pre = ET.SubElement(root, 'p')
        ET.SubElement(pre, 'code').text = self.__class__.__name__ + ": "
        ET.SubElement(pre, 'b').text = self.label or "Label"
        span = ET.SubElement(pre, 'span').text = " [{}]".format(self.unit or "unit")
        ET.SubElement(pre, 'br')

        root.append(ET.fromstring(self.x._repr_html_()))
        root.append(ET.fromstring(self.y._repr_html_()))
        root.append(ET.fromstring(self.z._repr_html_()))
        root.append(ET.fromstring(self.v._repr_html_()))

        return str(ET.tostring(root, encoding='utf-8'), 'utf-8')

    def read_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            os.path.exists(fileName)
            with open(fileName, 'rb') as f:
                # The protocol version used is detected automatically,
                # so we do not have to specify it.
                data = pickle.load(f)
            return data
        except:
            raise
            # raise FileNotFoundError("Please check your path, {} not found".\
            # format(fileName))

    def to_pickle(self, fileName=None):
        try:
            fileName = os.path.normpath(fileName)
            with open(fileName, 'wb') as f:
                pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)
        except:
            raise FileNotFoundError(f"Please check your path, \
            {format(fileName)} not found.")


############################################################################
# CLASSE polymesh2d
############################################################################
class polymesh2d(object):
    """
    """

    def __init__(self, p=None, x_label=None, x_unit=None,
                 y_label=None, y_unit=None):

        self.x = axis(label=x_label, unit=x_unit)
        self.y = axis(label=y_label, unit=y_unit)
        self.p = np.poly1d(p)

    def __call__(self, x):
        if isinstance(x, Number):
            return self.p(x)
        else:
            return mesh2d(x=mesh1d(x, self.x.label, self.x.unit),
                          d=mesh1d(self.p(x), self.y.label, self.y.unit))

    def plot(self, *pargs, **kwargs):
        import matplotlib.pyplot as plt

        xlim = kwargs['xlim'] if 'xlim' in kwargs else (0, 100)
        n = kwargs.pop('n') if 'n' in kwargs else 500

        kwargs['dx'] = kwargs['dx'] if 'dx' in kwargs else None
        kwargs['ylim'] = kwargs['ylim'] if 'ylim' in kwargs else None
        kwargs['dy'] = kwargs['dy'] if 'dy' in kwargs else None

        if n < 2:
            logger.warning("More than two points are necessary for linspace")
            return

        if plt.gca().lines:
            x = np.linspace(*plt.xlim(), n)
        else:
            x = np.linspace(*xlim, n)

        data2plot = self(x)
        if kwargs['dx'] is None:
            kwargs['dx'] = np.ptp(x) / 14
        if kwargs['ylim'] is None:
            kwargs['ylim'] = (np.min(data2plot.y), np.max(data2plot.y))
        if kwargs['dy'] is None:
            kwargs['dy'] = np.ptp(data2plot.y) / 12

        self(x).plot(*pargs, **kwargs)

    def _polyprint(self, html=False):
        tr = {48: 8304,
              49: 185,
              50: 178,
              51: 179,
              52: 8308,
              53: 8309,
              54: 8310,
              55: 8311,
              56: 8312,
              57: 8313}
        # joiner[first, negative] = str
        joiner = {
            (True, True): '-',
            (True, False): '',
            (False, True): ' - ',
            (False, False): ' + '
        }

        result = []
        for power, coeff in reversed(list(enumerate(reversed(self.p.coeffs)))):
            j = joiner[not result, coeff < 0]
            coeff = abs(coeff)

            f = {0: '{0}{1}', 1: '{}{}·x'}.get(power, '{}{}·x{}')
            f0 = {0: '{}{}', 1: '{}x'}.get(power, '{0}x{2}')

            if coeff == 1:
                result.append(f0.format(j, coeff,
                                        str(power).translate(tr)
                                        if html is True
                                        else "^{}".format(power)))
            elif coeff != 0:
                result.append(f.format(j, coeff,
                                       str(power).translate(tr)
                                       if html is True
                                       else "^{}".format(power)))

        return ''.join(result) or '0'

    def __repr__(self):
        return self._polyprint()

    def _repr_html_(self):
        return self._polyprint(html=True)

    def resample(self, x):
        return mesh2d(x=mesh1d(x,
                               label=self.x.label, unit=self.x.unit),
                      y=mesh1d(self.p(x),
                               label=self.y.label, unit=self.y.unit))


############################################################################
# CLASSE polymesh3d
############################################################################
class polymesh3d(object):
    """
    """

    def __init__(self, x_label=None, x_unit=None,
                 y_label=None, y_unit=None,
                 label=None, unit=None):

        self._x = axis(label=x_label, unit=x_unit)
        self._y = axis(label=y_label, unit=y_unit)
        self.z = axis(label=label, unit=unit)

        self._dtype = np.dtype([('x', 'f8'), ('p', object)])

    @property
    def x(self):
        return mesh1d(self.p.x,
                      label=self._x.label,
                      unit=self._x.unit)

    @property
    def y(self):
        """
        Describe the highest coefficent
        """
        return mesh1d(np.arange((max([len(_p.p.p.coeffs) for _p in self.p]))),
                      label=self._y.label,
                      unit=self._y.unit)

    def push(self, y, p):
        newElement = np.rec.array([(y, polymesh2d(p))], dtype=self._dtype)
        try:
            self.p = np.rec.array(np.append(newElement, self.p))
        except:
            self.p = newElement

        # sort
        self.p = np.rec.array(self.p[self.p.x.argsort()])

        # This will be some pre-determined size
        shape = (len(self.x), len(self.y))
        self._w = np.zeros(shape, dtype=np.float64)

        for _x, _P in enumerate(self.p):
            self._w[_x, -len(_P.p.p) - 1:] = np.array(_P.p.p.coeffs)

        self._m3d = mesh3d(x=self.x, y=self.y, w=self._w,
                           label=self.z.label,
                           unit=self.z.label)

    def __call__(self, x=None, y=None):

        myPoly = polymesh2d(self._m3d(x=x).y,
                            x_label=self.y.label, x_unit=self.y.unit,
                            y_label=self.z.label, y_unit=self.z.unit)
        if y is None:
            return myPoly
        else:
            return myPoly(y)

    def plot(self, *pargs, **kwargs):
        import matplotlib.pyplot as plt
        for i, x in enumerate(self.p.x):
            self.p.p[i].plot(label="{} {}".format(str(x), self.x.unit),
                             *pargs, **kwargs)
        plt.legend(loc=2)

    def resample(self, y):
        res = mesh3d(x=mesh1d(**self.x.__dict__),
                     y=mesh1d(y, **self.y.__dict__),
                     label=self.z.label, unit=self.z.unit)
        for x, p in self.p:
            res.push(x, p(y).y)
        return res
