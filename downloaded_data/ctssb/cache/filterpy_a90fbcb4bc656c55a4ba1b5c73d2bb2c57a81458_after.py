# -*- coding: utf-8 -*-

"""Copyright 2014 Roger R Labbe Jr.

filterpy library.
http://github.com/rlabbe/filterpy

Documentation at:
https://filterpy.readthedocs.org

Supporting book at:
https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python

This is licensed under an MIT license. See the readme.MD file
for more information.
"""

#
from numpy import array, asarray, isscalar, eye, dot
from functools import reduce


def dot3(A,B,C):
    """ Returns the matrix multiplication of A*B*C"""
    return dot(A, dot(B,C))

def dot4(A,B,C,D):
    """ Returns the matrix multiplication of A*B*C*D"""
    return dot(A, dot(B, dot(C,D)))


def dotn(*args):
    """ Returns the matrix multiplication of 2 or more matrices"""
    return reduce(dot, args)


def setter(value, dim_x, dim_y):
    """ Returns a copy of 'value' as an numpy.array with dtype=float. Throws
    exception if the array is not dimensioned correctly. Value may be any
    type which converts to numpy.array (list, np.array, np.matrix, etc)
    """
    v = array(value, dtype=float)
    if v.shape != (dim_x, dim_y):
        raise Exception('must have shape ({},{})'.format(dim_x, dim_y))
    return v

def setter_1d(value, dim_x):
    """ Returns a copy of 'value' as an numpy.array with dtype=float. Throws
    exception if the array is not dimensioned correctly. Value may be any
    type which converts to numpy.array (list, np.array, np.matrix, etc)
    """

    v = array(value, dtype=float)
    shape = v.shape
    if shape[0] != (dim_x) or v.ndim > 2 or (v.ndim==2 and shape[1] != 1):
        raise Exception('must have shape ({},{})'.format(dim_x, 1))
    return v


def setter_scalar(value, dim_x):
    """ Returns a copy of 'value' as an numpy.array with dtype=float. Throws
    exception if the array is not dimensioned correctly. Value may be any
    type which converts to numpy.array (list, np.array, np.matrix, etc),
    or a scalar, in which case we create a diagonal matrix with each
    diagonal element == value.
    """
    if isscalar(value):
        v = eye(dim_x) * value
    else:
        v = asarray(value, dtype=float)

    if v is value:
        v = value.copy()
    if v.shape != (dim_x, dim_x):
        raise Exception('must have shape ({},{})'.format(dim_x, dim_x))
    return v
