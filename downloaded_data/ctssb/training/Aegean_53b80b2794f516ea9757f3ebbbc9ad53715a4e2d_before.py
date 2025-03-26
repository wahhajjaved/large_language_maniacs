#! /usr/bin/env python
from __future__ import print_function

"""
Provide fitting routines and helper fucntions to Aegean
"""

__author__ = "Paul Hancock"

import copy
import math
import numpy as np
from scipy.linalg import eigh, inv
import lmfit
from .angle_tools import gcd, bear

# Other AegeanTools
# from models import OutputSource, IslandSource
from . import flags

# join the Aegean logger
import logging

log = logging.getLogger('Aegean')


# Modelling and fitting functions
def elliptical_gaussian(x, y, amp, xo, yo, sx, sy, theta):
    """
    Generate a model 2d Gaussian with the given parameters.
    Evaluate this model at the given locations x,y.

    :param x,y: locations at which to calculate values
    :param amp: amplitude of Gaussian
    :param xo,yo: position of Gaussian
    :param major,minor: axes (sigmas)
    :param theta: position angle (degrees) CCW from x-axis
    :return: Gaussian function evaluated at x,y locations
    """
    try:
        sint, cost = math.sin(np.radians(theta)), math.cos(np.radians(theta))
    except ValueError as e:
        if 'math domain error' in e.args:
            sint, cost = np.nan, np.nan
    xxo = x - xo
    yyo = y - yo
    exp = (xxo * cost + yyo * sint) ** 2 / sx ** 2 \
          + (xxo * sint - yyo * cost) ** 2 / sy ** 2
    exp *= -1. / 2
    return amp * np.exp(exp)


def Cmatrix(x, y, sx, sy, theta):
    """
    Construct a correlation matrix corresponding to the data.
    The matrix assumes a gaussian correlation function.
    :param x:
    :param y:
    :param sx: \sigma_x for pix beam
    :param sy: \sigma_y for pix beam
    :param theta: \theta for pix beam
    :return:
    """
    C = np.vstack([elliptical_gaussian(x, y, 1, i, j, sx, sy, theta) for i, j in zip(x, y)])
    return C


def Bmatrix(C):
    """
    Calculate a matrix which is effectively the square root of the correlation matrix C
    :param C: A covariance matrix
    :return: A matrix B such the B.dot(B') = inv(C)
    """
    # this version of finding the square root of the inverse matrix
    # suggested by Cath Trott
    L, Q = eigh(C)
    # force very small eigenvalues to have some minimum non-zero value
    minL = 1e-9*L[-1]
    L[L < minL] = minL
    S = np.diag(1 / np.sqrt(L))
    B = Q.dot(S)
    return B


def jacobian(pars, x, y):
    """
    Analytical calculation of the Jacobian for an elliptical gaussian
    Will work for a model that contains multiple Gaussians, and for which
    some components are not being fit (don't vary).
    :param pars: lmfit.Model
    :param x: x-values over which the model is evaluated
    :param y: y-values over which the model is evaluated
    :return:
    """

    matrix = []

    for i in range(pars['components'].value):
        prefix = "c{0}_".format(i)
        amp = pars[prefix + 'amp'].value
        xo = pars[prefix + 'xo'].value
        yo = pars[prefix + 'yo'].value
        sx = pars[prefix + 'sx'].value
        sy = pars[prefix + 'sy'].value
        theta = pars[prefix + 'theta'].value

        # The derivative with respect to component i doesn't depend on any other components
        # thus the model should not contain the other components
        model = elliptical_gaussian(x, y, amp, xo, yo, sx, sy, theta)

        # precompute for speed
        sint = np.sin(np.radians(theta))
        cost = np.cos(np.radians(theta))
        xxo = x - xo
        yyo = y - yo
        xcos, ycos = xxo * cost, yyo * cost
        xsin, ysin = xxo * sint, yyo * sint

        if pars[prefix + 'amp'].vary:
            dmds = model / amp
            matrix.append(dmds)

        if pars[prefix + 'xo'].vary:
            dmdxo = cost * (xcos + ysin) / sx ** 2 + sint * (xsin - ycos) / sy ** 2
            dmdxo *= model
            matrix.append(dmdxo)

        if pars[prefix + 'yo'].vary:
            dmdyo = sint * (xcos + ysin) / sx ** 2 - cost * (xsin - ycos) / sy ** 2
            dmdyo *= model
            matrix.append(dmdyo)

        if pars[prefix + 'sx'].vary:
            dmdsx = model / sx ** 3 * (xcos + ysin) ** 2
            matrix.append(dmdsx)

        if pars[prefix + 'sy'].vary:
            dmdsy = model / sy ** 3 * (xsin - ycos) ** 2
            matrix.append(dmdsy)

        if pars[prefix + 'theta'].vary:
            dmdtheta = model * (sy ** 2 - sx ** 2) * (xsin - ycos) * (xcos + ysin) / sx ** 2 / sy ** 2
            matrix.append(dmdtheta)

    return np.array(matrix)


def emp_jacobian(pars, x, y):
    """
    An empirical calculation of the Jacobian
    Will work for a model that contains multiple Gaussians, and for which
    some components are not being fit (don't vary).
    :param pars: lmfit.Model
    :param x: x-values over which the model is evaluated
    :param y: y-values over which the model is evaluated
    :return:
    """
    eps = 1e-5
    matrix = []
    model = ntwodgaussian_lmfit(pars)(x, y)
    for i in range(pars['components'].value):
        prefix = "c{0}_".format(i)
        for p in ['amp', 'xo', 'yo', 'sx', 'sy', 'theta']:
            if pars[prefix + p].vary:
                pars[prefix + p].value += eps
                dmdp = ntwodgaussian_lmfit(pars)(x, y) - model
                matrix.append(dmdp / eps)
                pars[prefix + p].value -= eps
    matrix = np.array(matrix)
    return matrix


def lmfit_jacobian(pars, x, y, errs=None, B=None, emp=False):
    """
    Wrapper around :jacobian: that gives the output in a format
    that is required for lmfit.
    :param pars: lmfit.Model
    :param x: x-values over which the model is evaluated
    :param y: y-values over which the model is evaluated
    :param errs: a vector of 1\sigma errors (optional)
    :param B: a B-matrix (optional) see B_matrix
    :param emp: True = use empirical Jacobian
    :return:
    """
    if emp:
        matrix = emp_jacobian(pars, x, y, errs, B)
    else:
        # calculate in the normal way
        matrix = jacobian(pars, x, y)
    # now munge this to be as expected for lmfit
    matrix = np.vstack(matrix)

    if errs is not None:
        matrix /= errs
        # matrix = matrix.dot(errs)

    if B is not None:
        matrix = matrix.dot(B)

    matrix = np.transpose(matrix)
    return matrix


def hessian(pars, x, y):
    """
    Create a hessian matrix corresponding to the source model 'pars'
    Only parameters that vary will contribute to the hessian.
    Thus there will be a total of nvar x nvar entries, each of which is a
    len(x) x len(y) array.
    :param pars: lmfit.Parameters() object
    :param x: indices
    :param y: indices
    :return: np.array of shape (nvar, nvar, len(x), len(y))
    """
    j = 0  # keeping track of the number of variable parameters
    # total number of variable parameters
    ntvar = np.sum([pars[k].vary for k in pars.keys() if k != 'components'])
    # construct an empty matrix of the correct size
    hmat = np.zeros((ntvar, ntvar, x.shape[0], x.shape[1]))
    npvar = 0

    for i in range(pars['components'].value):
        prefix = "c{0}_".format(i)
        amp = pars[prefix + 'amp'].value
        xo = pars[prefix + 'xo'].value
        yo = pars[prefix + 'yo'].value
        sx = pars[prefix + 'sx'].value
        sy = pars[prefix + 'sy'].value
        theta = pars[prefix + 'theta'].value

        amp_var = pars[prefix + 'amp'].vary
        xo_var = pars[prefix + 'xo'].vary
        yo_var = pars[prefix + 'yo'].vary
        sx_var = pars[prefix + 'sx'].vary
        sy_var = pars[prefix + 'sy'].vary
        theta_var = pars[prefix + 'theta'].vary

        # precomputed for speed
        model = elliptical_gaussian(x, y, amp, xo, yo, sx, sy, theta)
        sint = np.sin(np.radians(theta))
        sin2t = np.sin(np.radians(2*theta))
        cost = np.cos(np.radians(theta))
        cos2t = np.cos(np.radians(2*theta))
        sx2 = sx**2
        sy2 = sy**2
        xxo = x-xo
        yyo = y-yo
        xcos, ycos = xxo*cost, yyo*cost
        xsin, ysin = xxo*sint, yyo*sint

        if amp_var:
            k = npvar  # second round of keeping track of variable params
            # H(amp,amp)/G =  0
            hmat[j][k] = 0
            k += 1

            if xo_var:
                # H(amp,xo)/G =  1.0*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t))/(amp*sx**2*sy**2)
                hmat[j][k] = (xsin - ycos)*sint/sy2 + (xcos + ysin)*cost/sx2
                hmat[j][k] *= model
                k += 1

            if yo_var:
                # H(amp,yo)/G =  1.0*(-sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*cos(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t))/(amp*sx**2*sy**2)
                hmat[j][k] = -(xsin - ycos)*cost/sy2 + (xcos + ysin)*sint/sx2 
                hmat[j][k] *= model/amp
                k += 1

            if sx_var:
                # H(amp,sx)/G =  1.0*((x - xo)*cos(t) + (y - yo)*sin(t))**2/(amp*sx**3)
                hmat[j][k] = (xcos + ysin)**2
                hmat[j][k] *= model/(amp*sx**3)
                k += 1

            if sy_var:
                # H(amp,sy) =  1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))**2/(amp*sy**3)
                hmat[j][k] = (xsin - ycos)**2
                hmat[j][k] *= model/(amp*sy**3)
                k += 1

            if theta_var:
                # H(amp,t) =  (-1.0*sx**2 + sy**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))*((x - xo)*cos(t) + (y - yo)*sin(t))/(amp*sx**2*sy**2)
                hmat[j][k] = (xsin - ycos)*(xcos + ysin)
                hmat[j][k] *= sy2-sx2
                hmat[j][k] *= model/(amp*sx2*sy2)
                # k += 1
            j += 1

        if xo_var:
            k = npvar
            if amp_var:
                # H(xo,amp)/G = H(amp,xo)
                hmat[j][k] = hmat[k][j]
                k += 1

            # if xo_var:
            # H(xo,xo)/G =  1.0*(-sx**2*sy**2*(sx**2*sin(t)**2 + sy**2*cos(t)**2) + (sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t))**2)/(sx**4*sy**4)
            hmat[j][k] = -sx2*sy2*(sx2*sint**2 + sy2*cost**2)
            hmat[j][k] += (sx2*(xsin - ycos)*sint + sy2*(xcos + ysin)*cost)**2
            hmat[j][k] *= model/ (sx2**2*sy2**2)
            k += 1

            if yo_var:
                # H(xo,yo)/G =  1.0*(sx**2*sy**2*(sx**2 - sy**2)*sin(2*t)/2 - (sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*cos(t) - sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t)))/(sx**4*sy**4)
                hmat[j][k] = sx2*sy2*(sx2 - sy2)*sin2t/2
                hmat[j][k] -= (sx2*(xsin - ycos)*sint + sy2*(xcos + ysin)*cost)*(sx2*(xsin -ycos)*cost - sy2*(xcos + ysin)*sint)
                hmat[j][k] *= model / (sx**4*sy**4)
                k += 1

            if sx_var:
                # H(xo,sx) =  ((x - xo)*cos(t) + (y - yo)*sin(t))*(-2.0*sx**2*sy**2*cos(t) + 1.0*((x - xo)*cos(t) + (y - yo)*sin(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t)))/(sx**5*sy**2)
                hmat[j][k] = (xcos + ysin)
                hmat[j][k] *= -2*sx2*sy2*cost + (xcos + ysin)*(sx2*(xsin - ycos)*sint + sy2*(xcos + ysin)*cost)
                hmat[j][k] *= model / (sx**5*sy2)
                k += 1

            if sy_var:
                # H(xo,sy) =  ((x - xo)*sin(t) + (-y + yo)*cos(t))*(-2.0*sx**2*sy**2*sin(t) + 1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t)))/(sx2*sy**5)
                hmat[j][k] = (xsin - ycos)
                hmat[j][k] *= -2*sx2*sy2*sint + (xsin - ycos)*(sx2*(xsin - ycos)*sint + sy2*(xcos + ysin)*cost)
                hmat[j][k] *= model/(sx2*sy**5)
                k += 1

            if theta_var:
                # H(xo,t) =  1.0*(sx**2*sy**2*(sx**2 - sy**2)*(x*sin(2*t) - xo*sin(2*t) - y*cos(2*t) + yo*cos(2*t)) + (-sx**2 + 1.0*sy**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))*((x - xo)*cos(t) + (y - yo)*sin(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*sin(t) + sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*cos(t)))/(sx**4*sy**4)
                # second part
                hmat[j][k] = (sy2-sx2)*(xsin - ycos)*(xcos + ysin)
                hmat[j][k] *= sx2*(xsin -ycos)*sint + sy2*(xcos + ysin)*cost
                # first part
                hmat[j][k] += sx2*sy2*(sx2 - sy2)*(xxo*sin2t -yyo*cos2t)
                hmat[j][k] *= model/(sx**4*sy**4)
                # k += 1
            j += 1

        if yo_var:
            k = npvar
            if amp_var:
                # H(yo,amp)/G = H(amp,yo)
                hmat[j][k] = hmat[0][2]
                k += 1

            if xo_var:
                # H(yo,xo)/G = H(xo,yo)/G
                hmat[j][k] =hmat[1][2]
                k += 1

            # if yo_var:
            # H(yo,yo)/G = 1.0*(-sx**2*sy**2*(sx**2*cos(t)**2 + sy**2*sin(t)**2) + (sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*cos(t) - sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t))**2)/(sx**4*sy**4)
            hmat[j][k] = (sx2*(xsin - ycos)*cost - sy2*(xcos + ysin)*sint)**2 / (sx2**2*sy2**2)
            hmat[j][k] -= cost**2/sy2 + sint**2/sx2
            hmat[j][k] *= model
            k += 1

            if sx_var:
                # H(yo,sx)/G =  -((x - xo)*cos(t) + (y - yo)*sin(t))*(2.0*sx**2*sy**2*sin(t) + 1.0*((x - xo)*cos(t) + (y - yo)*sin(t))*(sx**2*((x - xo)*sin(t) - (y - yo)*cos(t))*cos(t) - sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t)))/(sx**5*sy**2)
                hmat[j][k] = -1*(xcos + ysin)
                hmat[j][k] *= 2*sx2*sy2*sint + (xcos + ysin)*(sx2*(xsin - ycos)*cost - sy2*(xcos + ysin)*sint)
                hmat[j][k] *= model/(sx**5*sy2)
                k += 1

            if sy_var:
                # H(yo,sy)/G =  ((x - xo)*sin(t) + (-y + yo)*cos(t))*(2.0*sx**2*sy**2*cos(t) - 1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*cos(t) - sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t)))/(sx**2*sy**5)
                hmat[j][k] = (xsin -ycos)
                hmat[j][k] *= 2*sx2*sy2*cost - (xsin - ycos)*(sx2*(xsin - ycos)*cost - sy2*(xcos + ysin)*sint)
                hmat[j][k] *= model/(sx2*sy**5)
                k += 1

            if theta_var:
                # H(yo,t)/G =  1.0*(sx**2*sy**2*(sx**2*(-x*cos(2*t) + xo*cos(2*t) - y*sin(2*t) + yo*sin(2*t)) + sy**2*(x*cos(2*t) - xo*cos(2*t) + y*sin(2*t) - yo*sin(2*t))) + (1.0*sx**2 - sy**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))*((x - xo)*cos(t) + (y - yo)*sin(t))*(sx**2*((x - xo)*sin(t) + (-y + yo)*cos(t))*cos(t) - sy**2*((x - xo)*cos(t) + (y - yo)*sin(t))*sin(t)))/(sx**4*sy**4)
                hmat[j][k] = (sx2 - sy2)*(xsin - ycos)*(xcos + ysin)
                hmat[j][k] *= (sx2*(xsin - ycos)*cost - sy2*(xcos + ysin)*sint)
                hmat[j][k] += sx2*sy2*(sx2-sy2)*(-x*cos2t + xo*cos2t - y*sin2t + yo*sin2t)
                hmat[j][k] *= model/(sx**4*sy**4)
                # k += 1
            j += 1

        if sx_var:
            k = npvar
            if amp_var:
                # H(sx,amp)/G = H(amp,sx)/G
                hmat[j][k] = hmat[k][j]
                k += 1

            if xo_var:
                # H(sx,xo)/G = H(xo,sx)/G
                hmat[j][k] = hmat[k][j]
                k += 1

            if yo_var:
                # H(sx,yo)/G = H(yo/sx)/G
                hmat[j][k] = hmat[k][j]
                k += 1

            # if sx_var:
            # H(sx,sx)/G =  (-3.0*sx**2 + 1.0*((x - xo)*cos(t) + (y - yo)*sin(t))**2)*((x - xo)*cos(t) + (y - yo)*sin(t))**2/sx**6
            hmat[j][k] = -3*sx2 + (xcos + ysin)**2
            hmat[j][k] *= (xcos + ysin)**2
            hmat[j][k] *= model/sx**6
            k += 1

            if sy_var:
                # H(sx,sy)/G =  1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))**2*((x - xo)*cos(t) + (y - yo)*sin(t))**2/(sx**3*sy**3)
                hmat[j][k] = (xsin - ycos)**2 * (xcos + ysin)**2
                hmat[j][k] *= model/(sx**3*sy**3)
                k += 1

            if theta_var:
                # H(sx,t)/G =  (-2.0*sx**2*sy**2 + 1.0*(-sx**2 + sy**2)*((x - xo)*cos(t) + (y - yo)*sin(t))**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))*((x - xo)*cos(t) + (y - yo)*sin(t))/(sx**5*sy**2)
                hmat[j][k] = -2*sx2*sy2 + (sy2 - sx2)*(xcos + ysin)**2
                hmat[j][k] *= (xsin -ycos)*(xcos + ysin)
                hmat[j][k] *= model/(sx**5*sy**2)
                # k += 1
            j += 1

        if sy_var:
            k = npvar
            if amp_var:
                # H(sy,amp)/G = H(amp,sy)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if xo_var:
                # H(sy,xo)/G = H(xo,sy)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if yo_var:
                # H(sy,yo)/G = H(yo/sy)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if sx_var:
                # H(sy,sx)/G = H(sx,sy)/G
                hmat[j][k] = hmat[k][j]
                k += 1

            # if sy_var:
            # H(sy,sy)/G =  (-3.0*sy**2 + 1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))**2/sy**6
            hmat[j][k] = -3*sy2 + (xsin - ycos)**2
            hmat[j][k] *= (xsin - ycos)**2
            hmat[j][k] *= model/sy**6
            k += 1

            if theta_var:
                # H(sy,t)/G =  (2.0*sx**2*sy**2 + 1.0*(-sx**2 + sy**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))**2)*((x - xo)*sin(t) + (-y + yo)*cos(t))*((x - xo)*cos(t) + (y - yo)*sin(t))/(sx**2*sy**5)
                hmat[j][k] = 2*sx2*sy2 + (sy2 - sx2)*(xsin - ycos)**2
                hmat[j][k] *= (xsin - ycos)*(xcos + ysin)
                hmat[j][k] *= model/(sx**2*sy**5)
                # k += 1
            j += 1

        if theta_var:
            k = npvar
            if amp_var:
                # H(t,amp)/G = H(amp,t)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if xo_var:
                # H(t,xo)/G = H(xo,t)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if yo_var:
                # H(t,yo)/G = H(yo/t)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if sx_var:
                # H(t,sx)/G = H(sx,t)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            if sy_var:
                # H(t,sy)/G = H(sy,t)/G
                hmat[j][k] = hmat[k][j]
                k += 1
            # if theta_var:
            # H(t,t)/G =  (sx**2*sy**2*(sx**2*(((x - xo)*sin(t) + (-y + yo)*cos(t))**2 - 1.0*((x - xo)*cos(t) + (y - yo)*sin(t))**2) + sy**2*(-1.0*((x - xo)*sin(t) + (-y + yo)*cos(t))**2 + ((x - xo)*cos(t) + (y - yo)*sin(t))**2)) + (sx**2 - 1.0*sy**2)**2*((x - xo)*sin(t) + (-y + yo)*cos(t))**2*((x - xo)*cos(t) + (y - yo)*sin(t))**2)/(sx**4*sy**4)
            hmat[j][k] = sx2*sy2
            hmat[j][k] *= sx2*((xsin - ycos)**2 - (xcos + ysin)**2) + sy2*((xcos + ysin)**2 - (xsin - ycos)**2)
            hmat[j][k] += (sx2 - sy2)**2*(xsin - ycos)**2*(xcos + ysin)**2
            hmat[j][k] *= model/(sx**4*sy**4)
            # j += 1

        # save the number of variables for the next iteration
        # as we need to start our indexing at this number
        npvar = k
    return np.array(hmat)


def emp_hessian(pars, x, y):
    """
    Calculate the hessian matrix empirically.
    Relies on :emp_jacobian: for the first order derivatives
    :param pars:
    :param x:
    :param y:
    :return:
    """
    eps = 1e-5
    matrix = []
    for i in range(pars['components']):
        model = emp_jacobian(pars, x, y)
        prefix = "c{0}_".format(i)
        for p in ['amp', 'xo', 'yo', 'sx', 'sy', 'theta']:
            if pars[prefix+p].vary:
                pars[prefix+p].value += eps
                dm2didj = emp_jacobian(pars, x, y) - model
                matrix.append(dm2didj/eps)
                pars[prefix+p].value -= eps
    matrix = np.array(matrix)
    return matrix


def nan_acf(noise):
    """
    Calculate the autocorrelation function of the noise
    where the noise is a 2d array that may contain nans
    :param noise:
    :return:
    """
    corr = np.zeros(noise.shape)
    ix,jx = noise.shape
    for i in range(ix):
        si_min = slice(i, None, None)
        si_max = slice(None, ix-i, None)
        for j in range(jx):
            sj_min = slice(j, None, None)
            sj_max = slice(None, jx-j, None)
            if np.all(np.isnan(noise[si_min, sj_min])) or np.all(np.isnan(noise[si_max, sj_max])):
                corr[i, j] = np.nan
            else:
                corr[i, j] = np.nansum(noise[si_min, sj_min] * noise[si_max, sj_max])
    # return the normalised acf
    return corr / np.nanmax(corr)


def make_ita(noise, acf=None):
    """
    Create the matrix ita of the noise where the noise may be a masked array
    where ita(x,y) is the correlation between pixel pairs that have the same separation as x and y.
    :param noise: A possibly masked 2d array
    :param acf: the autocorrelation matrix. (None = calculate from data)
    :return: ita
    """
    if acf is None:
        acf = nan_acf(noise)
    # s should be the number of non-masked pixels
    s = np.count_nonzero(np.isfinite(noise))
    # the indices of the non-masked pixels
    xm, ym = np.where(np.isfinite(noise))
    ita = np.zeros((s, s))
    # iterate over the pixels
    for i, (x1, y1) in enumerate(zip(xm, ym)):
        for j, (x2, y2) in enumerate(zip(xm, ym)):
            k = abs(x1-x2)
            l = abs(y1-y2)
            ita[i, j] = acf[k, l]
    return ita


def RB_bias(data, pars, ita=None, acf=None):
    """
    Calculate the expected bias on each of the parameters in the model pars.
    Only parameters that are allowed to vary will have a bias.
    :param data: data that was fit
    :param pars: lmfit.Parameters() of the fitted model
    :param ita: the ita matrix
    :param acf: the (normalized) noise correlation function
    :return:
    """
    log.info("data {0}".format(data.shape))
    nparams = np.sum([pars[k].vary for k in pars.keys() if k != 'components'])
    # masked pixels
    xm, ym = np.where(np.isfinite(data))
    # all pixels
    x, y = np.indices(data.shape)
    # Create the jacobian as an AxN array accounting for the masked pixels
    j = np.array(np.vsplit(lmfit_jacobian(pars, xm, ym).T, nparams)).reshape(nparams, -1)

    h = hessian(pars, x, y)
    # mask the hessian to be AxAxN array
    h = h[:, :, xm, ym]
    Hij = np.einsum('ik,jk', j, j)
    Dij = np.linalg.inv(Hij)
    Bijk = np.einsum('ip,jkp', j, h)
    Eilkm = np.einsum('il,km', Dij, Dij)

    Cimn_1 =    -1 * np.einsum('krj,ir,km,jn', Bijk, Dij, Dij, Dij)
    Cimn_2 = -1./2 * np.einsum('rkj,ir,km,jn', Bijk, Dij, Dij, Dij)
    Cimn = Cimn_1 + Cimn_2

    if ita is None:
        # N is the noise (data-model)
        N = data - ntwodgaussian_lmfit(pars)(x, y)
        if acf is None:
            acf = nan_acf(N)
        ita = make_ita(N, acf=acf)
        log.info('acf.shape {0}'.format(acf.shape))
        log.info('acf[0] {0}'.format(acf[0]))
        log.info('ita.shape {0}'.format(ita.shape))
        log.info('ita[0] {0}'.format(ita[0]))

    # Included for completeness but not required

    # now mask/ravel the noise
    # N = N[np.isfinite(N)].ravel()
    # Pi = np.einsum('ip,p', j, N)
    # Qij = np.einsum('ijp,p', h, N)

    Vij = np.einsum('ip,jq,pq', j, j, ita)
    Uijk = np.einsum('ip,jkq,pq', j, h, ita)

    bias_1 = np.einsum('imn, mn', Cimn, Vij)
    bias_2 = np.einsum('ilkm, mlk', Eilkm, Uijk)
    bias = bias_1 + bias_2
    log.info('bias {0}'.format(bias))
    return bias


def bias_correct(params, data, acf=None):
    """
    Apply a bias correction to the given fit parameters
    :param params:
    :param data:
    :param C:
    :return:
    """
    bias = RB_bias(data, params, acf=acf)
    i = 0
    for p in params:
        if 'theta' in p:
            continue
        if params[p].vary:
            params[p].value -= bias[i]
            i += 1
    return


def CRB_errs(jac, C, B=None):
    """
    Calculate minimum errors given by the Cramer-Rao bound
    :param jac: the jacobian
    :param C: the correlation matrix
    :param B: B.dot(B') should = inv(C), ie B ~ sqrt(inv(C))
    :return: array of errors for the model parameters
    """
    if B is not None:
        fim_inv = inv(np.transpose(jac).dot(B).dot(np.transpose(B)).dot(jac))
    else:
        fim = np.transpose(jac).dot(inv(C)).dot(jac)
        fim_inv = inv(fim)
    errs = np.sqrt(np.diag(fim_inv))
    return errs


def condon_errors(source, theta_n, psf=None):
    """
    Calculate the parameter errors for a fitted source
    using the description of Condon'97
    All parameters are assigned errors, assuming that all params were fit.
    If some params were held fixed then these errors are overestimated.
    :param source: Source for which errors need to be calculated
    :param theta_n: The angular size of an image pixel
    :return: The same source but with errors assigned.
    """

    # indices for the calculation or rho
    alphas = {'amp': (3. / 2, 3. / 2),
              'major': (5. / 2, 1. / 2),
              'xo': (5. / 2, 1. / 2),
              'minor': (1. / 2, 5. / 2),
              'yo': (1. / 2, 5. / 2),
              'pa': (1. / 2, 5. / 2)}

    major = source.a / 3600.  # degrees
    minor = source.b / 3600.  # degrees
    phi = np.radians(source.pa)  # radians
    if psf is not None:
        beam = psf.get_beam(source.ra, source.dec)
        if beam is not None:
            theta_n = np.hypot(beam.a, beam.b)
            print(beam, theta_n)

    if theta_n is None:
        source.err_a = source.err_b = source.err_peak_flux = source.err_pa = source.err_int_flux = 0
        return

    smoothing = major * minor / (theta_n ** 2)
    factor1 = (1 + (major / theta_n))
    factor2 = (1 + (minor / theta_n))
    snr = source.peak_flux / source.local_rms
    # calculation of rho2 depends on the parameter being used so we lambda this into a function
    rho2 = lambda x: smoothing / 4 * factor1 ** alphas[x][0] * factor2 ** alphas[x][1] * snr ** 2

    source.err_peak_flux = source.peak_flux * np.sqrt(2 / rho2('amp'))
    source.err_a = major * np.sqrt(2 / rho2('major')) * 3600.  # arcsec
    source.err_b = minor * np.sqrt(2 / rho2('minor')) * 3600.  # arcsec

    err_xo2 = 2. / rho2('xo') * major ** 2 / (8 * np.log(2))  # Condon'97 eq 21
    err_yo2 = 2. / rho2('yo') * minor ** 2 / (8 * np.log(2))
    source.err_ra = np.sqrt(err_xo2 * np.sin(phi)**2 + err_yo2 * np.cos(phi)**2)
    source.err_dec = np.sqrt(err_xo2 * np.cos(phi)**2 + err_yo2 * np.sin(phi)**2)

    if (major == 0) or (minor == 0):
        source.err_pa = -1
    # if major/minor are very similar then we should not be able to figure out what pa is.
    elif abs(2 * (major-minor) / (major+minor)) < 0.01:
        source.err_pa = -1
    else:
        source.err_pa = np.degrees(np.sqrt(4 / rho2('pa')) * (major * minor / (major ** 2 - minor ** 2)))

    # integrated flux error
    err2 = (source.err_peak_flux / source.peak_flux) ** 2
    err2 += (theta_n ** 2 / (major * minor)) * ((source.err_a / source.a) ** 2 + (source.err_b / source.b) ** 2)
    source.err_int_flux = source.int_flux * np.sqrt(err2)
    return


def errors(source, model, wcshelper):
    """
    Convert pixel based errors into sky coord errors
    :param source: Source object
    :param wcshelper: WCSHelper object
    :return:
    """

    # if the source wasn't fit then all errors are -1
    if source.flags & (flags.NOTFIT | flags.FITERR):
        source.err_peak_flux = source.err_a = source.err_b = source.err_pa = -1
        source.err_ra = source.err_dec = source.err_int_flux = -1
        return source
    # copy the errors from the model
    prefix = "c{0}_".format(source.source)
    err_amp = model[prefix + 'amp'].stderr
    xo, yo = model[prefix + 'xo'].value, model[prefix + 'yo'].value
    err_xo = model[prefix + 'xo'].stderr
    err_yo = model[prefix + 'yo'].stderr

    sx, sy = model[prefix + 'sx'].value, model[prefix + 'sy'].value
    err_sx = model[prefix + 'sx'].stderr
    err_sy = model[prefix + 'sy'].stderr

    theta = model[prefix + 'theta'].value
    err_theta = model[prefix + 'theta'].stderr

    source.err_peak_flux = err_amp
    pix_errs = [err_xo, err_yo, err_sx, err_sy, err_theta]

    log.debug("Pix errs: {0}".format(pix_errs))

    ref = wcshelper.pix2sky([xo, yo])
    # check to see if the reference position has a valid WCS coordinate
    # It is possible for this to fail, even if the ra/dec conversion works elsewhere
    if not all(np.isfinite(ref)):
        source.flags |= flags.WCSERR
        source.err_peak_flux = source.err_a = source.err_b = source.err_pa = -1
        source.err_ra = source.err_dec = source.err_int_flux = -1
        return source

    # position errors
    if model[prefix + 'xo'].vary and model[prefix + 'yo'].vary \
            and all(np.isfinite([err_xo, err_yo])):
        offset = wcshelper.pix2sky([xo + err_xo, yo + err_yo])
        source.err_ra = gcd(ref[0], ref[1], offset[0], ref[1])
        source.err_dec = gcd(ref[0], ref[1], ref[0], offset[1])
    else:
        source.err_ra = source.err_dec = -1

    if model[prefix + 'theta'].vary and np.isfinite(err_theta):
        # pa error
        off1 = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        off2 = wcshelper.pix2sky(
            [xo + sx * np.cos(np.radians(theta + err_theta)), yo + sy * np.sin(np.radians(theta + err_theta))])
        source.err_pa = abs(bear(ref[0], ref[1], off1[0], off1[1]) - bear(ref[0], ref[1], off2[0], off2[1]))
    else:
        source.err_pa = -1

    if model[prefix + 'sx'].vary and model[prefix + 'sy'].vary \
            and all(np.isfinite([err_sx, err_sy])):
        # major axis error
        ref = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        offset = wcshelper.pix2sky(
            [xo + (sx + err_sx) * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        source.err_a = gcd(ref[0], ref[1], offset[0], offset[1]) * 3600

        # minor axis error
        ref = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta + 90)), yo + sy * np.sin(np.radians(theta + 90))])
        offset = wcshelper.pix2sky(
            [xo + sx * np.cos(np.radians(theta + 90)), yo + (sy + err_sy) * np.sin(np.radians(theta + 90))])
        source.err_b = gcd(ref[0], ref[1], offset[0], offset[1]) * 3600
    else:
        source.err_a = source.err_b = -1

    sqerr = 0
    sqerr += (source.err_peak_flux / source.peak_flux) ** 2 if source.err_peak_flux > 0 else 0
    sqerr += (source.err_a / source.a) ** 2 if source.err_a > 0 else 0
    sqerr += (source.err_b / source.b) ** 2 if source.err_b > 0 else 0
    if sqerr == 0:
        source.err_int_flux = -1
    else:
        source.err_int_flux = abs(source.int_flux * np.sqrt(sqerr))

    return source


def new_errors(source, model, wcshelper):  # pragma: no cover
    """
    Convert pixel based errors into sky coord errors
    Uses covariance matrix for ra/dec errors
    and calculus approach to a/b/pa errors
    :param source: Source object
    :param wcshelper: WCSHelper object
    :return:
    """

    # if the source wasn't fit then all errors are -1
    if source.flags & (flags.NOTFIT | flags.FITERR):
        source.err_peak_flux = source.err_a = source.err_b = source.err_pa = -1
        source.err_ra = source.err_dec = source.err_int_flux = -1
        return source
    # copy the errors/values from the model
    prefix = "c{0}_".format(source.source)
    err_amp = model[prefix + 'amp'].stderr
    xo, yo = model[prefix + 'xo'].value, model[prefix + 'yo'].value
    err_xo = model[prefix + 'xo'].stderr
    err_yo = model[prefix + 'yo'].stderr

    sx, sy = model[prefix + 'sx'].value, model[prefix + 'sy'].value
    err_sx = model[prefix + 'sx'].stderr
    err_sy = model[prefix + 'sy'].stderr

    theta = model[prefix + 'theta'].value
    err_theta = model[prefix + 'theta'].stderr

    # the peak flux error doesn't need to be converted, just copied
    source.err_peak_flux = err_amp

    pix_errs = [err_xo, err_yo, err_sx, err_sy, err_theta]

    # check for inf/nan errors -> these sources have poor fits.
    if not all(a is not None and np.isfinite(a) for a in pix_errs):
        source.flags |= flags.FITERR
        source.err_peak_flux = source.err_a = source.err_b = source.err_pa = -1
        source.err_ra = source.err_dec = source.err_int_flux = -1
        return source

    # calculate the reference coordinate
    ref = wcshelper.pix2sky([xo, yo])
    # check to see if the reference position has a valid WCS coordinate
    # It is possible for this to fail, even if the ra/dec conversion works elsewhere
    if not all(np.isfinite(ref)):
        source.flags |= flags.WCSERR
        source.err_peak_flux = source.err_a = source.err_b = source.err_pa = -1
        source.err_ra = source.err_dec = source.err_int_flux = -1
        return source

    # calculate position errors by transforming the error ellipse
    if model[prefix + 'xo'].vary and model[prefix + 'yo'].vary:
        # determine the error ellipse from the Jacobian
        mat = model.covar[1:3, 1:3]
        if not(np.all(np.isfinite(mat))):
            source.err_ra = source.err_dec = -1
        else:
            (a, b), e = np.linalg.eig(mat)
            pa = np.degrees(np.arctan2(*e[0]))
            # transform this ellipse into sky coordinates
            ra, dec, major, minor, pa = wcshelper.pix2sky_ellipse([xo, yo], a, b, pa)

            # now determine the radius of the ellipse along the ra/dec directions.
            source.err_ra = major*minor / np.hypot(major*np.sin(np.radians(pa)), minor*np.cos(np.radians(pa)))
            source.err_dec = major*minor / np.hypot(major*np.cos(np.radians(pa)), minor*np.sin(np.radians(pa)))
    else:
        source.err_ra = source.err_dec = -1

    if model[prefix + 'theta'].vary:
        # pa error
        off1 = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        # offset by 1 degree
        off2 = wcshelper.pix2sky(
            [xo + sx * np.cos(np.radians(theta + 1)), yo + sy * np.sin(np.radians(theta + 1))])
        # scale the initial theta error by this amount
        source.err_pa = abs(bear(ref[0], ref[1], off1[0], off1[1]) - bear(ref[0], ref[1], off2[0], off2[1])) * err_theta
    else:
        source.err_pa = -1

    if model[prefix + 'sx'].vary and model[prefix + 'sy'].vary:
        # major axis error
        ref = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        # offset by 0.1 pixels
        offset = wcshelper.pix2sky(
            [xo + (sx + 0.1) * np.cos(np.radians(theta)), yo + sy * np.sin(np.radians(theta))])
        source.err_a = gcd(ref[0], ref[1], offset[0], offset[1])/0.1 * err_sx * 3600

        # minor axis error
        ref = wcshelper.pix2sky([xo + sx * np.cos(np.radians(theta + 90)), yo + sy * np.sin(np.radians(theta + 90))])
        # offset by 0.1 pixels
        offset = wcshelper.pix2sky(
            [xo + sx * np.cos(np.radians(theta + 90)), yo + (sy + 0.1) * np.sin(np.radians(theta + 90))])
        source.err_b = gcd(ref[0], ref[1], offset[0], offset[1])/0.1*err_sy * 3600
    else:
        source.err_a = source.err_b = -1

    sqerr = 0
    sqerr += (source.err_peak_flux / source.peak_flux) ** 2 if source.err_peak_flux > 0 else 0
    sqerr += (source.err_a / source.a) ** 2 if source.err_a > 0 else 0
    sqerr += (source.err_b / source.b) ** 2 if source.err_b > 0 else 0
    source.err_int_flux = abs(source.int_flux * np.sqrt(sqerr))

    return source


def ntwodgaussian_lmfit(params):
    """
    theta is in degrees
    :param params: model parameters (can be multiple)
    :return: a function that maps (x,y) -> model
    """

    def rfunc(x, y):
        result = None
        for i in range(params['components'].value):
            prefix = "c{0}_".format(i)
            # I hope this doesn't kill our run time
            amp = np.nan_to_num(params[prefix + 'amp'].value)
            xo = params[prefix + 'xo'].value
            yo = params[prefix + 'yo'].value
            sx = params[prefix + 'sx'].value
            sy = params[prefix + 'sy'].value
            theta = params[prefix + 'theta'].value
            if result is not None:
                result += elliptical_gaussian(x, y, amp, xo, yo, sx, sy, theta)
            else:
                result = elliptical_gaussian(x, y, amp, xo, yo, sx, sy, theta)
        return result

    return rfunc


def do_lmfit(data, params, B=None, errs=None, dojac=True):
    """
    Fit the model to the data
    data may contain 'flagged' or 'masked' data with the value of np.NaN
    input: data - pixel information
           params - and lmfit.Model instance
    return: fit results, modified model
    """
    # copy the params so as not to change the initial conditions
    # in case we want to use them elsewhere
    params = copy.deepcopy(params)
    data = np.array(data)
    mask = np.where(np.isfinite(data))

    def residual(params, **kwargs):
        f = ntwodgaussian_lmfit(params)  # A function describing the model
        model = f(*mask)  # The actual model
        if B is None:
            return model - data[mask]
        else:
            return (model - data[mask]).dot(B)

    if dojac:
        result = lmfit.minimize(residual, params, kws={'x': mask[0], 'y': mask[1], 'B': B, 'errs': errs}, Dfun=lmfit_jacobian)
    else:
        result = lmfit.minimize(residual, params, kws={'x': mask[0], 'y': mask[1], 'B': B, 'errs': errs})

    # Remake the residual so that it is once again (model - data)
    if B is not None:
        result.residual = result.residual.dot(inv(B))
    return result, params


def covar_errors(params, data, errs, B, C=None):
    """
    Take a set of parameters that were fit with lmfit, and replace the errors
    with the 1\sigma errors calculated using the covariance matrix.
    :param params: lmfit.Model
    :param data: data over which the model was fit
    :param errs: a matrix of 1\sigma errors
    :param B: B matrix (see Bmatrix)
    :param C: C matrix (optional, will obviate the need for Bmatrix)
    :return:
    """

    mask = np.where(np.isfinite(data))

    # calculate the proper parameter errors and copy them across.
    if C is not None:
        try:
            J = lmfit_jacobian(params, mask[0], mask[1], errs=errs)
            covar = np.transpose(J).dot(inv(C)).dot(J)
            onesigma = np.sqrt(np.diag(inv(covar)))
        except (np.linalg.linalg.LinAlgError, ValueError) as e:
            C = None

    if C is None:
        try:
            J = lmfit_jacobian(params, mask[0], mask[1], B=B, errs=errs)
            covar = np.transpose(J).dot(J)
            onesigma = np.sqrt(np.diag(inv(covar)))
        except (np.linalg.linalg.LinAlgError, ValueError) as e:
            onesigma = [-2] * len(mask[0])

    for i in range(params['components'].value):
        prefix = "c{0}_".format(i)
        j = 0
        for p in ['amp', 'xo', 'yo', 'sx', 'sy', 'theta']:
            if params[prefix + p].vary:
                params[prefix + p].stderr = onesigma[j]
                j += 1

    return params


if __name__ == "__main__":


    def plot_jacobian():
        """
        Plot the Jacobian for a test model
        :return:
        """
        nx = 15
        ny = 12
        x, y = np.where(np.ones((nx, ny)) == 1)

        # smoothing = 1.27 # 3pix/beam
        # smoothing = 2.12 # 5pix/beam
        smoothing = 1.5  # ~4.2pix/beam

        # The model parameters
        params = lmfit.Parameters()
        params.add('c0_amp', value=1, min=0.5, max=2)
        params.add('c0_xo', value=1. * nx / 2, min=nx / 2. - smoothing / 2., max=nx / 2. + smoothing / 2)
        params.add('c0_yo', value=1. * ny / 2, min=ny / 2. - smoothing / 2., max=ny / 2. + smoothing / 2.)
        params.add('c0_sx', value=2 * smoothing, min=0.8 * smoothing)
        params.add('c0_sy', value=smoothing, min=0.8 * smoothing)
        params.add('c0_theta', value=45)  #, min=-2*np.pi, max=2*np.pi)
        params.add('components', value=1, vary=False)

        def rmlabels(ax):
            ax.set_xticks([])
            ax.set_yticks([])

        from matplotlib import pyplot

        fig = pyplot.figure(1)
        # This sets all nan pixels to be a nasty yellow colour
        cmap = pyplot.cm.cubehelix
        cmap.set_bad('y', 1.)
        #kwargs = {'interpolation':'nearest','cmap':cmap,'vmin':-0.1,'vmax':1, 'origin':'lower'}
        kwargs = {'interpolation': 'nearest', 'cmap': cmap, 'origin': 'lower'}
        for i, jac in enumerate([emp_jacobian, lmfit_jacobian]):
            fig = pyplot.figure(i + 1, figsize=(4, 6))
            jdata = jac(params, x, y)
            fig.suptitle(str(jac))
            for k, p in enumerate(['amp', 'xo', 'yo', 'sx', 'sy', 'theta']):
                ax = fig.add_subplot(3, 2, k + 1)
                ax.imshow(jdata[:, k].reshape(nx, ny), **kwargs)
                ax.set_title(p)
                rmlabels(ax)

        pyplot.show()

    def clx(ax):
        """
        Remove the x/y ticks from a given axis
        :param ax:
        :return: None
        """
        ax.set_xticks([])
        ax.set_yticks([])
        return


    def test_hessian_plots():
        """
        Plot the empirical and analytical hessian to check for agreement.
        :return: None
        """
        from matplotlib import pyplot
        model = lmfit.Parameters()
        model.add('c0_amp', 1, vary=True)
        model.add('c0_xo', 20, vary=True)
        model.add('c0_yo', 20, vary=True)
        model.add('c0_sx', 5, vary=True)
        model.add('c0_sy', 4, vary=True)
        model.add('c0_theta', 37, vary=True)
        model.add('components', 1, vary=False)
        x, y = np.indices((40, 40))
        # Empirical Hessian
        kwargs = {"interpolation": "nearest", 'aspect': 1, 'vmin': -1, 'vmax': 1}
        fig, ax = pyplot.subplots(6, 6, squeeze=True, sharex=True, sharey=True, figsize=(5, 6))
        Hemp = emp_hessian(model, x, y)
        vars = ['amp', 'xo', 'yo', 'sx', 'sy', 'theta']
        for i, row in enumerate(ax):
            for j, ax in enumerate(row):
                im = Hemp[i, j, :, :]
                # im[np.where(abs(im) < 1e-5)] = 0
                # print vars[i],vars[j], np.amax(im)
                im /= np.amax(im)
                ax.imshow(im, **kwargs)
                if j == 0:
                    ax.set_ylabel(vars[i])
                if i == 5:
                    ax.set_xlabel(vars[j])
                clx(ax)
        fig.suptitle('Empirical Hessian')

        # Analytical Hessian
        fig, ax = pyplot.subplots(6, 6, squeeze=True, sharex=True, sharey=True, figsize=(5, 6))
        Hana = hessian(model, x, y)
        for i, row in enumerate(ax):
            for j, ax in enumerate(row):
                im = Hana[i, j, :, :]
                # im[np.where(abs(im) < 1e-5)] = 0
                # print vars[i],vars[j], np.amax(im)
                im /= np.amax(im)
                ax.imshow(im, **kwargs)
                if j == 0:
                    ax.set_ylabel(vars[i])
                if i == 5:
                    ax.set_xlabel(vars[j])
                clx(ax)
        fig.suptitle('Analytical Hessian')

        # Difference
        fig, ax = pyplot.subplots(6, 6, squeeze=True, sharex=True, sharey=True, figsize=(5, 6))
        Hana = hessian(model, x, y)
        for i, row in enumerate(ax):
            for j, ax in enumerate(row):
                im1 = Hana[i, j, :, :]
                im1 /= np.amax(im1)
                im2 = Hemp[i, j, :, :]
                im2 /= np.amax(im2)
                ax.imshow(im1-im2, **kwargs)
                if j == 0:
                    ax.set_ylabel(vars[i])
                if i == 5:
                    ax.set_xlabel(vars[j])
                clx(ax)
        fig.suptitle('Difference')
        pyplot.show()


    def test_jacobian_plot():
        """

        :return:
        """
        from matplotlib import pyplot
        model = lmfit.Parameters()
        model.add('c0_amp', 1, vary=True)
        model.add('c0_xo', 20, vary=True)
        model.add('c0_yo', 20, vary=True)
        model.add('c0_sx', 5, vary=True)
        model.add('c0_sy', 4, vary=True)
        model.add('c0_theta', 37, vary=True)
        model.add('components', 1, vary=False)
        x, y = np.indices((40, 40))

        kwargs = {"interpolation": "nearest", 'aspect': 1, 'vmin': -1, 'vmax': 1}
        vars = ['amp', 'xo', 'yo', 'sx', 'sy', 'theta']

        fig, ax = pyplot.subplots(6, 3, sharex=True, sharey=True, figsize=(3, 6))

        Jemp = emp_jacobian(model, x, y)
        Jana = jacobian(model, x, y)

        for i, row in enumerate(ax):
            im1 = Jemp[i, :, :]
            im1 /= np.amax(im1)
            im2 = Jana[i, :, :]
            im2 /= np.amax(im2)
            row[0].imshow(im1, **kwargs)
            row[0].set_ylabel(vars[i])
            row[1].imshow(im2, **kwargs)
            row[2].imshow(im1-im2, **kwargs)
            clx(row[0])
            clx(row[1])
        ax[0][0].set_title("Emp")
        ax[0][1].set_title("Ana")
        ax[0][2].set_title("Diff")
        fig.suptitle('Jacobian Comparison')
        pyplot.show()
        return

    test_hessian_plots()
    test_jacobian_plot()

