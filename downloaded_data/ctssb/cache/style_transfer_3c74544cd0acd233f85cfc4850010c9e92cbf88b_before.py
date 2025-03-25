"""Numerical utilities."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
import math

import numpy as np
from PIL import Image
from PIL.Image import NEAREST, BILINEAR, BICUBIC, LANCZOS  # pylint: disable=unused-import
import pywt
from scipy.linalg import blas

# Machine epsilon for float32
EPS = np.finfo(np.float32).eps

POOL = ProcessPoolExecutor()


# pylint: disable=no-member
def dot(x, y):
    """Returns the dot product of two float32 arrays with the same shape."""
    return blas.sdot(x.ravel(), y.ravel())


# pylint: disable=no-member
def axpy(a, x, y):
    """Sets y = a*x + y for float a and float32 arrays x, y and returns y."""
    y_ = blas.saxpy(x.ravel(), y.ravel(), a=a).reshape(y.shape)
    if y is not y_:
        y[:] = y_
    return y


def norm2(arr):
    """Returns 1/2 the L2 norm squared."""
    return np.sum(arr**2) / 2


def p_norm(arr, p=2):
    """Returns the pth power of the p-norm and its gradient."""
    if p == 1:
        return np.sum(abs(arr)), np.sign(arr)
    elif p == 2:
        return np.sum(arr**2), 2 * arr
    return np.sum(abs(arr)**p), p * np.sign(arr) * abs(arr)**(p-1)


def normalize(arr):
    """Normalizes an array in-place to have an L1 norm equal to its size."""
    arr /= np.mean(abs(arr)) + EPS
    return arr


def resize(a, hw, method=LANCZOS):
    """Resamples an image array in CxHxW format to a new HxW size. The interpolation is performed
    in floating point and the result dtype is numpy.float32."""
    def _resize(a, b):
        b[:] = Image.fromarray(a).resize((hw[1], hw[0]), method)

    a = np.float32(a)
    if a.ndim == 2:
        b = np.zeros(hw, np.float32)
        _resize(a, b)
        return b
    ch = a.shape[0]
    b = np.zeros((ch, hw[0], hw[1]), np.float32)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_resize, a[i], b[i]) for i in range(ch)]
        _ = [fut.result() for fut in futs]

    return b


def roll_by_1(arr, shift, axis):
    """Rolls a 3D array in-place by a shift of one element. Axes 1 and 2 only."""
    if axis == 1:
        if shift == -1:
            line = arr[:, 0, :].copy()
            arr[:, :-1, :] = arr[:, 1:, :]
            arr[:, -1, :] = line
        elif shift == 1:
            line = arr[:, -1, :].copy()
            arr[:, 1:, :] = arr[:, :-1, :]
            arr[:, 0, :] = line
    elif axis == 2:
        if shift == -1:
            line = arr[:, :, 0].copy()
            arr[:, :, :-1] = arr[:, :, 1:]
            arr[:, :, -1] = line
        elif shift == 1:
            line = arr[:, :, -1].copy()
            arr[:, :, 1:] = arr[:, :, :-1]
            arr[:, :, 0] = line
    else:
        raise ValueError('Unsupported shift or axis')
    return arr


def roll2(arr, xy):
    """Translates an array in-place by the shift xy, wrapping at the edges."""
    if xy is None or (xy[0] == 0 and xy[1] == 0):
        return arr
    arr[:] = np.roll(np.roll(arr, xy[0], -1), xy[1], -2)
    return arr


def gram_matrix(feat):
    """Computes the Gram matrix corresponding to a feature map."""
    n, mh, mw = feat.shape
    feat = feat.reshape((n, mh * mw))
    return np.dot(feat, feat.T) / np.float32(feat.size)


def tv_norm(x, beta=2):
    """Computes the total variation norm and its gradient. From jcjohnson/cnn-vis and [3]."""
    x_diff = x - roll_by_1(x.copy(), -1, axis=2)
    y_diff = x - roll_by_1(x.copy(), -1, axis=1)
    grad_norm2 = x_diff**2 + y_diff**2 + EPS
    loss = np.sum(grad_norm2**(beta/2))
    dgrad_norm = (beta/2) * grad_norm2**(beta/2 - 1)
    dx_diff = 2 * x_diff * dgrad_norm
    dy_diff = 2 * y_diff * dgrad_norm
    grad = dx_diff + dy_diff
    grad -= roll_by_1(dx_diff, 1, axis=2)
    grad -= roll_by_1(dy_diff, 1, axis=1)
    return loss, grad


class EWMA:
    """An exponentially weighted moving average with initialization bias correction."""
    def __init__(self, beta, shape=(), dtype=np.float32, correct_bias=True):
        self.beta = beta
        self.fac = 0
        if correct_bias:
            self.fac = 1
        self.value = np.zeros(shape, dtype)

    def get(self):
        """Gets the current value of the running average."""
        return self.value / (1 - self.fac)

    def get_est(self, datum):
        """Estimates the next value of the running average given a datum, but does not update
        the average."""
        est_value = self.beta * self.value + (1 - self.beta) * datum
        return est_value / (1 - self.fac * self.beta)

    def update(self, datum):
        """Updates the running average with a new observation."""
        self.fac *= self.beta
        self.value *= self.beta
        self.value += (1 - self.beta) * datum
        return self.get()


def pad_width(shape, divisors):
    """Returns the amount to pad each axis of an array on in order to be divisible by its
    corresponding divisor. It is intended to be used to generate the 'pad_width' parameter for
    numpy.pad()."""
    pw = []
    for length, divisor in zip(shape, divisors):
        to_pad = math.ceil(length / divisor) * divisor - length
        if to_pad % 2 == 0:
            pw.append((to_pad // 2, to_pad // 2))
        else:
            pw.append((to_pad // 2, to_pad // 2 + 1))
    return pw


def swt_norm(*args, **kwargs):
    """Computes the squared 2-norm of the SWT detail coefficients of the input and its gradient."""
        return ex.submit(_swt_norm, *args, **kwargs).result()


def _swt_norm(x, wavelet, level):
    """Computes the squared 2-norm of the SWT detail coefficients of the input and its gradient."""
    div = 2**math.ceil(math.log2(max(x.shape[1:])))
    pw = pad_width(x.shape, (1, div, div))
    x_pad = np.pad(x, pw, 'symmetric')
    inv_ = []
    for ch in x_pad:
        coeffs = pywt.swt2(ch, wavelet, level)
        for a, _ in coeffs:
            a[:] = 0
        inv_.append(pywt.iswt2(coeffs, wavelet)[pw[1][0]:pw[1][0]+x.shape[1],
                                                pw[2][0]:pw[2][0]+x.shape[2]])
    inv = np.stack(inv_)
    return np.sum(inv**2), inv * 2


# def swt_norm(x, wavelet, level):
#     """Computes the squared 2-norm of the SWT detail coefficients of the input and its gradient."""
#     div = 2**math.ceil(math.log2(max(x.shape[1:])))
#     pw = pad_width(x.shape, (1, div, div))
#     x_pad = np.pad(x, pw, 'symmetric')
#     with ProcessPoolExecutor() as ex:
#         channels = list(ex.map(partial(pywt.swt2, wavelet=wavelet, level=level), x_pad))
#         for coeffs in channels:
#             for a, _ in coeffs:
#                 a[:] = 0
#         inv = np.stack(ex.map(partial(pywt.iswt2, wavelet=wavelet), channels))
#     inv = inv[:, pw[1][0]:pw[1][0]+x.shape[1], pw[2][0]:pw[2][0]+x.shape[2]]
#     return np.sum(inv**2), inv * 2


class Normalizer:
    """Normalizes arrays according to a decaying mean of their L1 norm."""
    def __init__(self, beta):
        self.beta = beta
        self.norms = {}

    def __call__(self, key, arr):
        if key not in self.norms:
            self.norms[key] = EWMA(self.beta)
        arr /= self.norms[key].update(np.mean(abs(arr))) + EPS
        return arr
