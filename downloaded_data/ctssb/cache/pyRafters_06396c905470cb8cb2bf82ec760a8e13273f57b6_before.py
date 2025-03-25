# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six
from six.moves import zip
import sys

import numpy as np

from ..tools_base import ToolBase
from ..handler_base import (ImageSource, ImageSink)

import IPython.utils.traitlets as traitlets


def _generic_thresh(img, min_val=None, max_val=None):
    if min_val is None and max_val is None:
        raise ValueError("must give at least one side")

    if min_val is not None:
        tmp_min = img > min_val
    else:
        tmp_min = True

    if max_val is not None:
        tmp_max = img < max_val
    else:
        tmp_max = True

    return np.logical_and(tmp_min, tmp_max)


class BoundedThreshold(ToolBase):
    """
    Select a band of thresholds

    """
    input_file = traitlets.Instance(klass=ImageSource,
                                    tooltip='Image File',
                                    label='input')
    output_file = traitlets.Instance(klass=ImageSink,
                                    tooltip='Image File',
                                    label='output')
    min_val = traitlets.Float(0, tooltip='Minimum Value', label='min_val')
    max_val = traitlets.Float(1, tooltip='Maximum Value', label='max_val')

    def run(self):
        with self.input_file as src:
            # grab the input data
            res = _generic_thresh(src.get_frame(0),
                                  min_val=self.min_val,
                                  max_val=self.max_val)
        self.output_file.set_resolution(self.input_file.resolution,
                                        self.input_file.resolution_units)
        with self.output_file as snk:
            snk.record_frame(res, 0)


class LTThreshold(ToolBase):
    """
    Pixels less than value

    """
    input_file = traitlets.Instance(klass=ImageSource,
                                    tooltip='Image File',
                                    label='input')
    output_file = traitlets.Instance(klass=ImageSink,
                                    tooltip='Image File',
                                    label='output')
    max_val = traitlets.Float(1, tooltip='Maximum Value', label='max_val')

    def run(self):
        with self.input_file as src:
            # grab the input data
            res = _generic_thresh(src.get_frame(0),
                                  min_val=self.min_val)

        self.output_file.set_resolution(self.input_file.resolution,
                                        self.input_file.resolution_units)
        with self.output_file as snk:
            snk.record_frame(res, 0)


class GTThreshold(ToolBase):
    """
    Pixels greater than value


    """
    input_file = traitlets.Instance(klass=ImageSource,
                                    tooltip='Image File',
                                    label='input')
    output_file = traitlets.Instance(klass=ImageSink,
                                    tooltip='Image File',
                                    label='output')
    max_val = traitlets.Float(1, tooltip='Maximum Value', label='max_val')

    def run(self):
        with self.input_file as src:
            # grab the input data
            res = _generic_thresh(src.get_frame(0),
                                  max_val=self.max_val)

        self.output_file.set_resolution(self.input_file.resolution,
                                        self.input_file.resolution_units)
        with self.output_file as snk:
            snk.record_frame(res, 0)


class _base_binary_op(ToolBase):
    """
    A template class for building binary operation tools
    for pyLight usage.  This is for operations that take two
    images (A and B) and no parameters (ex addition).
    """
    A = traitlets.Instance(klass=ImageSource,
                                    tooltip='Image File A',
                                    label='input')
    B = traitlets.Instance(klass=ImageSource,
                                    tooltip='Image File B',
                                    label='input')
    out = traitlets.Instance(klass=ImageSink,
                                    tooltip='Image File',
                                    label='output')

    @classmethod
    def available(cls):
        """
        Make this class non available (so it does not show up in
        the sub-class lists.
        """
        return False


def _gen_binary_op_class(opp, doc, name):
    """
    A function which generates classes around the `_base_binary_op`
    'template' class. This will eventually be generalized and
    moved else where.

    This function should only be used at import time to use this
    with IPython parallel.  This is because the class will be
    pickled to push to the external process so the class must
    be defined correctly on both sides.

    Parameters
    ----------
    opp : function
        a function that takes two numpy arrays and returns an array

    doc : string
         The docstring for the new class

    name : string
        The name of the new class, should be ascii to play nice with
        py2k
    """
    avail = classmethod(lambda cls: True)

    # define the run function (which closes over the
    def run(self):
        # TODO add checks for resolution matching
        # TODO add meta-data pass through
        with self.A as A, self.B as B:
            tmp_out = []
            for a, b in zip(A, B):
                tmp_out.append(opp(a, b))

        self.output_file.set_resolution(self.A.resolution,
                                        self.A.resolution_units)
        with self.out as snk:
            for j, _out_frame in enumerate(tmp_out):
                snk.record_frame(_out_frame, j)
    #
    new_class = type(str(name), (_base_binary_op,), {"run": run,
                                                     "available": avail,
                                                     '__module__': __name__})
    new_class.__doc__ = doc

    return new_class

# list of binary operations to wrap
_bin_op_list = [
    (np.add, 'Add image A and Image B (A + B)', 'AddImages'),
    (np.subtract, 'Subtract image B from Image A (A - B)',
     'SubtractImages'),
    (np.multiply, 'Multiply images A and B element wise(A * B)',
     'MultImages'),
    (np.divide, ('Divide images A and B element wise (A / B)\n' +
                 'Output type depends on input types'),
     'DivideImages'),
    (np.true_divide, ('Divide images A and B element wise (A / B)\n' +
                 'Always returns floats.'),
                 'TrueDivideImages'),
    (np.floor_divide, ('Divide images A and B element wise (A / B)\n' +
                 'Always returns ints (floor of true_division).'),
                 'FloorDivideImages'),
    ]

mod = sys.modules[__name__]
# loop over the operations and shove into the current module
for args in _bin_op_list:
    setattr(mod, args[-1], _gen_binary_op_class(*args))
