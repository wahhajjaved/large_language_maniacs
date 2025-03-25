# author: Daniel Burkhardt <daniel.burkhardt@yale.edu>
# (C) 2017 Krishnaswamy Lab GPLv2

from __future__ import print_function, division
from sklearn.preprocessing import normalize
import numpy as np
from scipy import sparse
import pandas as pd
import numbers
from .filter import library_size


def library_size_normalize(data, rescale='median'):
    """Performs L1 normalization on input data
    Performs L1 normalization on input data such that the sum of expression
    values for each cell sums to 1
    then returns normalized matrix to the metric space using median UMI count
    per cell effectively scaling all cells as if they were sampled evenly.

    Parameters
    ----------
    data : array-like, shape=[n_samples, n_features]
        Input data
    rescale : {'mean', 'median'}, float or `None`, optional (default: 'median')
        Rescaling strategy. If 'mean' or 'median', normalized cells are scaled
        back up to the mean or median expression value. If a float,
        normalized cells are scaled up to the given value. If `None`, no
        rescaling is done and all cells will have normalized library size of 1.

    Returns
    -------
    data_norm : array-like, shape=[n_samples, n_features]
        Library size normalized output data
    """
    # pandas support
    columns, index = None, None
    if isinstance(data, pd.SparseDataFrame) or \
            pd.api.types.is_sparse(data):
        columns, index = data.columns, data.index
        data = data.to_coo()
    elif isinstance(data, pd.DataFrame):
        columns, index = data.columns, data.index

    if rescale == 'median':
        rescale = np.median(np.array(library_size(data)))
    elif rescale == 'mean':
        rescale = np.mean(np.array(library_size(data)))
    elif isinstance(rescale, numbers.Number):
        pass
    elif rescale is None:
        rescale = 1
    else:
        raise ValueError("Expected rescale in ['median', 'mean'], a number "
                         "or `None`. Got {}".format(rescale))

    if sparse.issparse(data) and data.nnz >= 2**31:
        # check we can access elements by index
        try:
            data[0, 0]
        except TypeError:
            data = sparse.csr_matrix(data)
        # normalize in chunks - sklearn doesn't does with more
        # than 2**31 non-zero elements
        #
        # determine maximum chunk size
        split = 2**30 // (data.nnz // data.shape[0])
        size_ok = False
        while not size_ok:
            for i in range(0, data.shape[0], split):
                if data[i:i + split, :].nnz >= 2**31:
                    split = split // 2
                    break
            size_ok = True
        # normalize
        data_norm = []
        for i in range(0, data.shape[0], split):
            data_norm.append(normalize(data[i:i + split, :], 'l1', axis=1))
        # combine chunks
        data_norm = sparse.vstack(data_norm)
    else:
        data_norm = normalize(data, norm='l1', axis=1)

    # norm = 'l1' computes the L1 norm which computes the
    # axis = 1 independently normalizes each sample

    data_norm = data_norm * rescale
    if columns is not None:
        # pandas dataframe
        if sparse.issparse(data_norm):
            data_norm = pd.SparseDataFrame(data_norm, default_fill_value=0.0)
        else:
            data_norm = pd.DataFrame(data_norm)
        data_norm.columns = columns
        data_norm.index = index
    return data_norm


def batch_mean_center(data, sample_idx=None):
    """Performs batch mean-centering on the data

    The features of the data are all centered such that
    the column means are zero. Each batch is centered separately.

    Parameters
    ----------
    data : array-like, shape=[n_samples, n_features]
        Input data
    sample_idx : list-like, optional
        Batch indices. If `None`, data is assumed to be a single batch

    Returns
    -------
    data : array-like, shape=[n_samples, n_features]
        Batch mean-centered output data.
    """
    if sparse.issparse(data) or isinstance(data, pd.SparseDataFrame):
        raise ValueError("Cannot mean center sparse data. "
                         "Convert to dense matrix first.")
    if sample_idx is None:
        sample_idx = np.ones(len(data))
    for sample in np.unique(sample_idx):
        idx = sample_idx == sample
        if isinstance(data, pd.DataFrame):
            feature_means = data.iloc[idx].mean(axis=0)
            data.iloc[idx] = data.iloc[idx] - feature_means
        else:
            feature_means = np.mean(data[idx], axis=0)
            data[idx] = data[idx] - feature_means[None, :]
    return data
