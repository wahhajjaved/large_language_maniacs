# Mapping object for holding upper and lower error bars
#
# Author: Zach Sailer
#
# ----------------------------------------------------------
# Local imports
# ----------------------------------------------------------

import numpy as np

from seqspace.base import BaseMap

def upper_transform(mean, bound, logbase):
    """ Log transformation scaling.

        Untransformed data looks as so:

            Yupper = Ymean + bound
            Ylower = Ymean - bound

        We want log(bounds)
            ie.
                log(Yupper) - log(Ymean)
                log(Ylower) + log(Ymean)

        so log(bound) = log(1 + bound/Ymean)
           log(bound) = log(1 - bound/Ymean)
    """
    return abs(logbase((mean + bound) /mean))

def lower_transform(mean, bound, logbase):
    """ Log transformation scaling.

        Untransformed data looks as so:

            Yupper = Ymean + bound
            Ylower = Ymean - bound

        We want log(bounds)
            ie.
                log(Yupper) - log(Ymean)
                log(Ylower) + log(Ymean)

        so log(bound) = log(1 + bound/Ymean)
           log(bound) = log(1 - bound/Ymean)
    """
    return abs(logbase( mean / (mean - bound) ))


class BaseErrorMap(BaseMap):

    def __init__(self, Map):
        """ If a lower bound is given, use it instead of -variances. """
        self._Map = Map

    def wrapper(self, bound, **kwargs):
        """ Wrapper function that changes variances to whatever bound desired. """
        raise Exception(""" Must be implemented in a subclass """)

    @property
    def upper(self):
        """"""
        if self._Map.stdeviations is None:
            return None
        else:
            if self._Map.transformed:
                return upper_transform(self._Map.phenotypes, self.wrapper(self._Map.stdeviations), logbase=self._Map.logbase)
            else:
                return self.wrapper(self._Map.stdeviations)

    @property
    def lower(self):
        """"""
        if self._Map.stdeviations is None:
            return None
        else:
            if self._Map.transformed:
                return lower_transform(self._Map.phenotypes, self.wrapper(self._Map.stdeviations), logbase=self._Map.logbase)
            else:
                return self.wrapper(self._Map.stdeviations)


class StandardDeviationMap(BaseErrorMap):

    def wrapper(self, bounds, **kwargs):
        """ Wrapper function to convert Variances if necessary"""
        return bounds

class StandardErrorMap(BaseErrorMap):

    def wrapper(self, bounds):
        """ Wrapper function to convert Variances if necessary"""
        return bounds/np.sqrt(self._Map.n_replicates)
