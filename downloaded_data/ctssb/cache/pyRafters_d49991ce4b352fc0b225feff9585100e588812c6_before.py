"""
A set of sources and sinks for handling in-memory nparrays
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import six

import numpy as np

from ..data_base import DistributionSource, DistributionSink


class np_dist_source(DistributionSource):
    """
    A source for reading distribution data out of csv (or tab or what ever)
    separated files.
    """

    # local stuff
    def __init__(self, edges, vals):
        """
        Wrapper for in-memory work

        Parameters
        ----------
        edges : nparray
            The bin edges

        vals : nparray
            The bin values
        """
        # base stuff
        self._active = False
        # np stuff, make local copies
        self._edges = np.array(edges)
        self._vals = np.array(vals)
        # sanity checks
        if self._edges.ndim != 1:
            raise ValueError("edges must be 1D")
        if self._vals.ndim != 1:
            raise ValueError("vals must be 1D")

        # distribution stuff
        if len(edges) == len(vals):
            self._right = False
        elif (len(edges) + 1)  == len(vals):
            self._right = True
        else:
            raise ValueError("the length of `edges` must be equal to " +
                "or one greater than the length of the vals. " +
                "Not len(edges): {el} and len(vals): {vl}".format(
                    el=len(edges), vl=len(vals)))

    # base properties
    @property
    def active(self):
        return self._active

    def activate(self):
        self._active = True

    def deactivate(self):
        self._active = False

    # distribution methods
    def read_values(self):
        if not self.active:
            raise RuntimeError('handler must be active')

        return self._vals

    def read_edges(self, include_right=False):
        if not self.active:
            raise RuntimeError('handler must be active')
        if include_right:
            raise NotImplementedError("don't support right kwarg yet")

        return self._edges

    @property
    def metadata(self):
        return {'edges': self._edges,
                'vals': self._vals}


class np_dist_sink(DistributionSink):
    """
    A sink for writing distribution data to memory
    """
    def __init__(self):
        # base stuff
        self._active = False
        self._vals = None
        self._edges = None

    # base class parts
    @property
    def active(self):
        return self._active

    def activate(self):
        self._active = True

    def deactivate(self):
        self._active = False

    # np parts
    def write_dist(self, edges, vals, right_edge=False):
        self._edges = np.array(edges)
        self._vals = np.array(vals)

    @property
    def metadata(self):
        return {}
