import numpy as np

from contextlib import contextmanager
import atexit
import sys
import time


def cartesian(arrays, out=None):
    """
    Generate a cartesian product of input arrays.

    From: http://stackoverflow.com/a/1235363/196284

    Parameters
    ----------
    arrays : list of array-like
        1-D arrays to form the cartesian product of.
    out : ndarray
        Array to place the cartesian product in.

    Returns
    -------
    out : ndarray
        2-D array of shape (M, len(arrays)) containing cartesian products
        formed of input arrays.

    Examples
    --------
    >>> cartesian(([1, 2, 3], [4, 5], [6, 7]))
    array([[1, 4, 6],
           [1, 4, 7],
           [1, 5, 6],
           [1, 5, 7],
           [2, 4, 6],
           [2, 4, 7],
           [2, 5, 6],
           [2, 5, 7],
           [3, 4, 6],
           [3, 4, 7],
           [3, 5, 6],
           [3, 5, 7]])

    """

    arrays = [np.asarray(x) for x in arrays]
    dtype = arrays[0].dtype

    n = np.prod([x.size for x in arrays])
    if out is None:
        out = np.zeros([n, len(arrays)], dtype=dtype)

    m = n / arrays[0].size
    out[:, 0] = np.repeat(arrays[0], m)
    if arrays[1:]:
        cartesian(arrays[1:], out=out[0:m, 1:])
        for j in range(1, arrays[0].size):
            out[j*m:(j+1)*m, 1:] = out[0:m, 1:]
    return out


def ascolumn(array):
    """
    Convert an array to a column vector if it is 1D.

    Parameters
    ----------
    array : array-like
        The array to convert.

    Returns
    -------
    colarray : array-like
        The array in column vector form.
    """

    array = np.asarray(array)
    if array.ndim == 1:
        array = np.reshape(array, (array.shape[0], 1))
    return array


def unit(v):
    result = np.array(v)
    normalize(result)
    return result


def normalize(v):
    v = np.asarray(v)
    if v.ndim == 1:
        v[:] = v / np.linalg.norm(v, 2)
        return v
    elif v.ndim == 2:
        v[:] /= ascolumn(np.linalg.norm(v, 2, axis=1))
        return v
    raise ValueError('Unsupported ndim: %d' % v.ndim)


def cross(u, v, dtype=float):
    '''Cross product for homogenous vectors'''
    u = np.asarray(u)
    v = np.asarray(v)
    if not u.shape == (4,) or not v.shape == (4,):
        raise ValueError('incompatible dimension for homogenous vectors')
    x = np.ndarray((4,), dtype=dtype)
    x[:3] = np.cross(u[:3], v[:3])
    x[3] = 1
    return x


@contextmanager
def profile(name):
    global _profile_registered
    if not _profile_registered:
        atexit.register(_profile_print_results)
        _profile_registered = True
    total = _profile_results.get(name, 0.)
    t0 = time.time()
    try:
        yield
    finally:
        _profile_results[name] = total + time.time() - t0
_profile_results = {}
_profile_registered = False


def _profile_print_results():
    for name, value in _profile_results.items():
        sys.stderr.write('{} {}\n'.format(name, value))
