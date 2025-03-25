# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:

import numpy as np
from scipy import stats
import matplotlib.pylab as pl

def jaccard_index(a, b):
    """
    Compute the Jaccard index (also known as the Jaccard similarity coefficient)
    between sets a and b.

    """
    a[a > 0] = 1
    a[a <= 0] = 0
    b[b > 0] = 1
    b[b <= 0] = 0
    pool = a + b
    pool[pool > 0] = 1
    intersection = a * b
    return intersection.sum() / pool.sum()

def dice_coef(a, b):
    """
    Compuet the Dice's coefficient between sets a and b.

    """
    a[a>0] = 1
    b[b>0] = 1
    a[a<=0] = 0
    b[b<=0] = 0
    if not a.sum():
        if not b.sum():
            return 1.0
    return 2 * np.sum(a * b) / (a.sum() + b.sum())

def corr4d(x, y):
    """
    Compute voxel-wise Pearson's correlation between two 4d data (x and y).
    x and y are two numpy array and should have same dimension.

    """
    if not x.shape == y.shape:
        print 'Data shape not match'
        return
    # r = sum((x-mean_x)(y-mean_y))/sqrt(sum((x-mean_x)^2)*sum((y-mean_y)^2))
    x_mean = np.zeros((x.shape[0], x.shape[1], x.shape[2], 1))
    x_mean[..., 0] = np.mean(x, 3)
    x_mean = np.repeat(x_mean, x.shape[3], axis=3)
    x_mask = x_mean.copy()
    x_mask[x_mask != 0] = 1

    y_mean = np.zeros((y.shape[0], y.shape[1], y.shape[2], 1))
    y_mean[..., 0] = np.mean(y, 3)
    y_mean = np.repeat(y_mean, y.shape[3], axis=3)
    y_mask = y_mean.copy()
    y_mask[y_mask != 0] = 1

    mask = x_mask * y_mask
    x_demean = np.ma.array(x - x_mean, mask=1-mask)
    y_demean = np.ma.array(y - y_mean, mask=1-mask)

    numerator = np.sum(x_demean * y_demean, 3)
    denominator = np.sqrt(np.sum(np.square(x_demean), 3)*np.sum(np.square(y_demean), 3))

    r_data = numerator / denominator
    r_data[mask[..., 0]==0] = 0
    return r_data

def corr3d(x, y):
    """
    Compute Pearson's correlation between data from two different nifti
    files.
    data x and y should be two 3-d dataset.

    """
    if not x.shape == y.shape:
        print 'Data shape not match'
        return
    # create a mask containing voxels that have no zeros in both datasets
    x_mask = x.copy()
    y_mask = y.copy()
    x_mask[x_mask!=0] = 1
    y_mask[y_mask!=0] = 1
    mask = x_mask * y_mask
    mask_vector = mask.reshape((mask.shape[0]*mask.shape[1]*mask.shape[2], 1))
    x_vector = x.reshape((x.shape[0]*x.shape[1]*x.shape[2], 1))
    y_vector = y.reshape((y.shape[0]*y.shape[1]*y.shape[2], 1))
    idx = [i for i in range(mask_vector.shape[0]) if mask_vector[i]]
    x_vector = x_vector[idx]
    print np.mean(x_vector)
    y_vector = y_vector[idx]
    print np.mean(y_vector)
    #r = np.corrcoef(x_vector.T, y_vector.T)
    slope, intercept, r_value, p_value, std_err = stats.linregress(y_vector.T, x_vector.T)
    print slope
    print intercept
    print "Pearson's correlation coefficient is "
    print r_value
    fig = pl.figure()
    pl.scatter(x_vector, y_vector, marker='.', 
               edgecolors='none', facecolors='b')
    pl.show()
    x_data = np.ma.array(x, mask=1-mask)
    y_data = np.ma.array(y, mask=1-mask)
    data = x_data - y_data * slope
    return data

def x_divide_y(x, y):
    """
    x and y are two 3d data, and the function would return x/y in a
    element-wise.

    """
    x_mask = x.copy()
    x_mask[x_mask!=0] = 1
    y_mask = y.copy()
    y_mask[y_mask!=0] = 1
    mask = x_mask * y_mask
    x = np.ma.array(x, mask=1-mask)
    y = np.ma.array(y, mask=1-mask)
    ratio = x / y
    return ratio * mask

def f_test(x, dfn, dfd):
    """
    Perform a Fisher's F test, the function would return a cdf array.

    """
    return stats.f.cdf(x, dfn, dfd)

def eig(x):
    """
    Input a data matrix x, and return the eigen value and eigen vector.
    The computation is based on the covariance matrix of x.
    x must be a two dimension matrix, and raw is sample, column is variable.

    """
    x = np.atleast_2d(x)
    n_samples, n_features = x.shape
    x -= np.mean(x, axis=0)
    c = x.T.dot(x)
    eigval, eigvtr = np.linalg.eig(c)
    return eigval, eigvtr

def flip_x(nifti_data):
    """
    Flip a 3d nifti volume about parasagittal plane through x = 0

    """
    return nifti_data[::-1, ...]

def t_test(x_mean, y_mean, x_std, y_std, x_len, y_len):
    """
    example:
    --------
    t_test(x_mean, y_mean, x_std, y_std, x_len, y_len)

    """
    x_xy = (x_len - 1) * np.square(x_std) + (y_len - 1) * np.square(y_std)
    s_xy = np.sqrt(s_xy / (x_len + y_len - 2))
    temp = np.sqrt(1. / x_len + 1. / y_len)
    t = (x_mean - y_mean) / s_xy / temp
    return t

def precision(true_data, predicted_data):
    """
    Get precision of the prediction.

    """
    true_data[true_data>0] = 1
    true_data[true_data<0] = 0
    predicted_data[predicted_data>0] = 1
    predicted_data[predicted_data<0] = 0
    if not predicted_data.sum():
        if not true_data.sum():
            return 1.0
        else:
            return 0
    else:
        return np.sum(true_data * predicted_data) / predicted_data.sum()

def recall(true_data, predicted_data):
    """
    Get recall of the prediction.

    """
    true_data[true_data>0] = 1
    true_data[true_data<0] = 0
    predicted_data[predicted_data>0] = 1
    predicted_data[predicted_data<0] = 0
    if not true_data.sum():
        if not predicted_data.sum():
            return 1.0
        else:
            return 0
    else:
        return np.sum(true_data * predicted_data) / true_data.sum()

