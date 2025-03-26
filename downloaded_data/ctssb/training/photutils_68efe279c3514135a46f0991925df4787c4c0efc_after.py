# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""
This module includes helper functions for array operations. 
"""
import numpy as np
from astropy import log

__all__ = ['extract_array_2D', 'add_array_2D', 'subpixel_indices']


def _get_slices(large_array_shape, small_array_shape, position):
    """
    Get slices for the overlapping part of a small and a large array.
    
    Given a certain position of the center of the small array, with respect to 
    the large array, four slices are computed, which can be used to extract, 
    add or subtract the small array at the given position. This function takes 
    care of the correct behavior at the boundaries, where the small array is cut
    of appropriately.
     
    Parameters
    ----------
    large_array_shape : tuple
        Shape of the large array.
    small_array_shape : tuple
        Shape of the small array.
    position : tuple, (x, y)
        Position of the small array's center, with respect
        to the large array.
    
    Returns
    -------
    s_y : slice
        Slice in y direction for the large array.
    s_x : slice
        Slice in x direction for the large array.
    b_y : slice
        Slice in y direction for the small array.
    b_x : slice
        Slice in x direction for the small array.
    """
    # Get edge coordinates
    y_min = position[1] - small_array_shape[0] // 2
    x_min = position[0] - small_array_shape[1] // 2
    y_max = position[1] + small_array_shape[0] // 2 + 1
    x_max = position[0] + small_array_shape[1] // 2 + 1

    # Set up slices in x direction
    s_x = slice(max(0, x_min), min(large_array_shape[1], x_max))
    b_x = slice(max(0, -x_min), min(large_array_shape[1] - x_min, x_max - x_min))
    
    # Set up slices in y direction
    s_y = slice(max(0, y_min), min(large_array_shape[0], y_max))
    b_y = slice(max(0, -y_min), min(large_array_shape[0] - y_min, y_max - y_min))
    return s_y, s_x, b_y, b_x


def extract_array_2D(array_large, shape, position):
    """
    Extract smaller array of given shape and position out of a larger array.

    Parameters
    ----------
    array_large : ndarray
        Array to extract another array from.
    shape : tuple
        Shape of the extracted array.
    position : tuple, (x, y)
        Position of the small array's center, with respect
        to the large array.
    
   
    Examples
    --------
    We consider a large array of zeros with the shape 21x21 and a small 
    array of ones with a shape of 9x9:
    
    >>> import numpy as np
    >>> from photutils.arrayutils import extract_array_2D
    >>> large_array = np.zeros((21, 21))
    >>> large_array[6:14, 6:14] = np.ones((9, 9))
    >>> extract_array_2D(large_array, (9, 9), (10, 10))
    """
    # Check if larger array is really larger
    if array_large.shape >= shape:
        s_y, s_x, _, _ = _get_slices(array_large.shape, shape, position)
        return array_large[s_y, s_x]
    else:
        raise Exception("Can't extract array. Shape too large.")


def add_array_2D(array_large, array_small, position):
    """
    Add a smaller 2D array at a given position in a larger 2D array.

    Parameters
    ----------
    array_large : ndarray
        Large array.
    array_small : ndarray
        Small array to add.
    position : tuple, (x, y)
        Position of the small array's center, with respect
        to the large array.
    
    Examples
    --------
    We consider a large array of zeros with the shape 21x21 and a small 
    array of ones with a shape of 9x9:
    
    >>> import numpy as np
    >>> from photutils.arrayutils import add_array_2D
    >>> large_array = np.zeros((21, 21))
    >>> small_array = np.ones((9, 9))
    >>> add_array_2D(large_array, small_array, (10, 10))
    """
    # Check if larger array is really larger
    if array_large.shape >= array_small.shape:
        s_y, s_x, b_y, b_x = _get_slices(array_large.shape, array_small.shape, position)
        array_large[s_y, s_x] += array_small[b_y, b_x]
        return array_large
    else:
        raise Exception("Can't add array. Small array too large.")


def subpixel_indices(position, subsampling):
    """
    Convert decimal points to indices, given a subsampling factor.
    
    Parameters
    ----------
    position : tuple (x, y)
        Position in pixels.
    subsampling : int
        Subsampling factor per pixel.
        
    """
    # Get decimal points
    x_frac, y_frac = np.modf(position)[0]
    
    # Convert to int
    x_sub = np.int(x_frac * subsampling)
    y_sub = np.int(y_frac * subsampling)
    return y_sub, x_sub
    