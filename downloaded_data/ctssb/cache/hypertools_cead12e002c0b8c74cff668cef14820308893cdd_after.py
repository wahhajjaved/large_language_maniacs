#!/usr/bin/env python

"""
Implements PCA (wrapper for scikit-learn.decomposition.PCA)

INPUTS:
-numpy array(s)
-list of numpy arrays

OUTPUTS:
-numpy array (or list of arrays) with dimensions reduced
"""

##PACKAGES##
import warnings
import numpy as np
from ppca import PPCA
from sklearn.decomposition import PCA as PCA
from ..util.pandas_to_matrix import pandas_to_matrix
from ..util.normalize import normalize as normalizer
from .._shared.helpers import *

##SUB FUNCTIONS##
def reducePCA(x, ndim):

	# if there are any nans in any of the lists, use ppca
	if np.isnan(np.vstack(x)).any():
		warnings.warn('Missing data: Inexact solution computed with PPCA (see https://github.com/allentran/pca-magic for details)')

		# ppca if missing data
		m = PPCA(np.vstack(x))
		m.fit(d=ndim)
		x_pca = m.transform()

		# if the whole row is missing, return nans
		all_missing = [idx for idx,a in enumerate(np.vstack(x)) if all([type(b)==np.nan for b in a])]
		if len(all_missing)>0:
			for i in all_missing:
				x_pca[i,:]=np.nan

		# get the original lists back
		if len(x)>1:
			x_split = np.cumsum([i.shape[0] for i in x][:-1])
			return list(np.split(x_pca,x_split,axis=0))
		else:
			return [x_pca]

	else:
		m=PCA(n_components=ndim, whiten=True)
		m.fit(np.vstack(x))
		if len(x)>1:
			return [m.transform(i) for i in x]
		else:
			return [m.transform(x[0])]

##MAIN FUNCTION##
def reduce(x, ndims=3, method=reducePCA, normalize=None):

	## CHECK DATA TYPE ##
	data_type = check_data(x)

	## IF DATAFRAME, CONVERT TO ARRAY ##
	if data_type=='df':
	    # convert df to common format
	    x = pandas_to_matrix(x)

	if type(x) is not list:
		x = [x]
	assert all([i.shape[1]>ndims for i in x]), "In order to reduce the data, ndims must be less than the number of dimensions"

	x = normalizer(x, normalize=normalize)

	return method(x,ndims)
