"""
Test models which correspond to classic minimization problems from the global
optimization community.
"""

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function

import numpy as np
import mwhutils.random as random
import mwhutils.pretty as pretty

__all__ = ['Sinusoidal', 'Gramacy', 'Branin', 'Bohachevsky', 'Goldstein']


class GOModel(object):
    """
    Base class for "global optimization" models. Every subclass should
    implement a static method `f` which evaluates the function. Note that `f`
    should be amenable to _minimization_, but calls to `get_data` will return
    the negative of `f` so we can maximize the function.
    """
    def __init__(self, sn2=0.0, rng=None, minimize=False):
        self._sigma = np.sqrt(sn2)
        self._rng = random.rstate(rng)
        self._minimize = minimize

    def __repr__(self):
        args = []
        kwargs = {}
        if self._sigma > 0:
            args.append(self._sigma**2)
        if self._minimize:
            kwargs['minimize'] = True
        return pretty.repr_args(self, *args, **kwargs)

    def __call__(self, x):
        return self.get(x)[0]

    def get(self, X):
        y = self.get_f(X)
        if self._sigma > 0:
            y += self._rng.normal(scale=self._sigma, size=len(y))
        return y

    def get_f(self, X):
        X = np.array(X, ndmin=2, dtype=float, copy=False)
        if X.shape != (X.shape[0], self.bounds.shape[0]):
            raise ValueError('function inputs must be {:d}-dimensional'
                             .format(self.ndim))
        f = self._f(X)
        if not self._minimize:
            f *= -1
        return f


def _cleanup(cls):
    """
    Decorator to make sure the bounds/xmax properties are correctly sized.
    """
    cls.bounds = np.array(cls.bounds, ndmin=2, dtype=float)
    cls.xopt = np.array(cls.xopt, ndmin=1, dtype=float)
    cls.ndim = cls.bounds.shape[0]
    assert cls.bounds.ndim == 2
    assert cls.xopt.ndim == 1
    assert cls.bounds.shape[1] == 2
    assert cls.bounds.shape[0] == cls.xopt.shape[0]
    return cls


# NOTE: for 1d function models we don't really need to worry about the
# dimensions for f. Maybe I should add a check for this later.


@_cleanup
class Sinusoidal(GOModel):
    """
    Simple sinusoidal function bounded in [0, 2pi] given by cos(x)+sin(3x).
    """
    bounds = [0, 2*np.pi]
    xopt = 3.61439678

    @staticmethod
    def _f(x):
        return np.ravel(np.cos(x) + np.sin(3*x))


@_cleanup
class Gramacy(GOModel):
    """
    Sinusoidal function in 1d used by Gramacy and Lee in "Cases for the nugget
    in modeling computer experiments".
    """
    bounds = [[0.5, 2.5]]
    xopt = 0.54856343

    @staticmethod
    def _f(x):
        return np.ravel(np.sin(10*np.pi*x) / (2*x) + (x-1)**4)


@_cleanup
class Branin(GOModel):
    """
    The 2d Branin function bounded in [-5,10] to [0,15]. Global optimizers
    exist at [-pi, 12.275], [pi, 2.275], and [9.42478, 2.475] with no local
    optimizers.
    """
    bounds = [[-5, 10], [0, 15]]
    xopt = [np.pi, 2.275]

    @staticmethod
    def _f(x):
        y = (x[:, 1]-(5.1/(4*np.pi**2))*x[:, 0]**2+5*x[:, 0]/np.pi-6)**2
        y += 10*(1-1/(8*np.pi))*np.cos(x[:, 0])+10
        ## NOTE: this rescales branin by 10 to make it more manageable.
        y /= 10.
        return y


@_cleanup
class Bohachevsky(GOModel):
    """
    The Bohachevsky function in 2d, bounded in [-100, 100] for both variables.
    There is only one global optimizer at [0, 0].
    """
    bounds = [[-100, 100], [-100, 100]]
    xopt = [0, 0]

    @staticmethod
    def _f(x):
        y = 0.7 + x[:, 0]**2 + 2.0*x[:, 1]**2
        y -= 0.3*np.cos(3*np.pi*x[:, 0])
        y -= 0.4*np.cos(4*np.pi*x[:, 1])
        return y


@_cleanup
class Goldstein(GOModel):
    """
    The Goldstein & Price function in 2d, bounded in [-2,-2] to [2,2]. There
    are several local optimizers and a single global optimizer at [0,-1].
    """
    bounds = [[-2, 2], [-2, 2]]
    xopt = [0, -1]

    @staticmethod
    def _f(x):
        a = (1 +
             (x[:, 0] + x[:, 1]+1)**2 *
             (19-14*x[:, 0] +
              3*x[:, 0]**2 - 14*x[:, 1] + 6*x[:, 0]*x[:, 1] + 3*x[:, 1]**2))
        b = (30 +
             (2*x[:, 0] - 3*x[:, 1])**2 *
             (18 - 32*x[:, 0] + 12*x[:, 0]**2 + 48*x[:, 1] - 36*x[:, 0]*x[:, 1]
              + 27*x[:, 1]**2))
        return a * b
