# -*- coding: utf-8 -*-
# Copyright 2007-2011 The Hyperspy developers
#
# This file is part of  Hyperspy.
#
#  Hyperspy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  Hyperspy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  Hyperspy.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import division
import sys
import os
import types

import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
try:
    import mdp
    mdp_installed = True
except:
    mdp_installed = False
try:
    import sklearn.decomposition
    sklearn_installed = True
except:
    sklearn_installed = False

from hyperspy.misc import utils
from hyperspy.learn.svd_pca import svd_pca
from hyperspy.learn.mlpca import mlpca
from hyperspy.defaults_parser import preferences
from hyperspy import messages
from hyperspy.decorators import auto_replot, do_not_replot
from scipy import linalg


def centering_and_whitening(X):
    X = X.T
    # Centering the columns (ie the variables)
    X = X - X.mean(axis=-1)[:, np.newaxis]
    # Whitening and preprocessing by PCA
    u, d, _ = linalg.svd(X, full_matrices=False)
    del _
    K = (u / (d/np.sqrt(X.shape[1]))).T
    del u, d
    X1 = np.dot(K, X)
    return X1.T, K
    
class MVA():
    """
    Multivariate analysis capabilities for the Spectrum class.

    """

    def __init__(self):
        if not hasattr(self,'learning_results'):
            self.learning_results = LearningResults()

    @do_not_replot
    def decomposition(self, normalize_poissonian_noise=False,
    algorithm = 'svd', output_dimension=None, centre = None,
    auto_transpose = True, navigation_mask=None, signal_mask=None,
    var_array=None, var_func=None, polyfit=None, reproject=None, **kwargs):
        """Decomposition with a choice of algorithms

        The results are stored in self.learning_results

        Parameters
        ----------
        normalize_poissonian_noise : bool
            If True, scale the SI to normalize Poissonian noise
            
        algorithm : 'svd' | 'fast_svd' | 'mlpca' | 'fast_mlpca' | 'nmf' |
            'sparse_pca' | 'mini_batch_sparse_pca'
        
        output_dimension : None or int
            number of components to keep/calculate
            
        centre : None | 'variables' | 'trials'
            If None no centring is applied. If 'variable' the centring will be
            performed in the variable axis. If 'trials', the centring will be 
            performed in the 'trials' axis. It only has effect when using the 
            svd or fast_svd algorithms
        
        auto_transpose : bool
            If True, automatically transposes the data to boost performance.
            Only has effect when using the svd of fast_svd algorithms.
            
        navigation_mask : boolean numpy array
        
        signal_mask : boolean numpy array
            
        var_array : numpy array
            Array of variance for the maximum likelihood PCA algorithm
            
        var_func : function or numpy array
            If function, it will apply it to the dataset to obtain the
            var_array. Alternatively, it can a an array with the coefficients
            of a polynomial.
            
        polyfit :
        
        reproject : None | signal | navigation | both
            If not None, the results of the decomposition will be projected in 
            the selected masked area.


        See also
        --------
        plot_decomposition_factors, plot_decomposition_loadings, plot_lev

        """
        # Check if it is the wrong data type
        if self.data.dtype.char not in ['e', 'f', 'd']: # If not float
            messages.warning(
                'To perform a decomposition the data must be of the float type.'
                ' You can change the type using the change_dtype method'
                ' e.g. s.change_dtype(\'float64\')\n'
                'Nothing done.')
            return
        # backup the original data
        self._data_before_treatments = self.data.copy()

        if algorithm == 'mlpca':
            if normalize_poissonian_noise is True:
                messages.warning(
                "It makes no sense to do normalize_poissonian_noise with "
                "the MLPCA algorithm. Therefore, "
                "normalize_poissonian_noise is set to False")
                normalize_poissonian_noise = False
            if output_dimension is None:
                messages.warning_exit("With the mlpca algorithm the "
                "output_dimension must be expecified")


        # Apply pre-treatments
        # Transform the data in a line spectrum
        self._unfolded4decomposition = self.unfold_if_multidim()
        if hasattr(navigation_mask, 'ravel'):
            navigation_mask = navigation_mask.ravel()

        if hasattr(signal_mask, 'ravel'):
            signal_mask = signal_mask.ravel()

        # Normalize the poissonian noise
        # TODO this function can change the masks and this can cause
        # problems when reprojecting
        if normalize_poissonian_noise is True:
            if reproject is None:
                navigation_mask, signal_mask = \
                    self.normalize_poissonian_noise(
                                            navigation_mask=navigation_mask,
                                            signal_mask=signal_mask,
                                            return_masks = True)
            elif reproject == 'both':
                _, _ = \
                    self.normalize_poissonian_noise(return_masks = True)  
            elif reproject == 'navigation':
                _, signal_mask = \
                    self.normalize_poissonian_noise(return_masks = True,
                                                    signal_mask=signal_mask,) 
            elif reproject == 'signal':
                navigation_mask, _ = \
                    self.normalize_poissonian_noise(return_masks = True,
                                            navigation_mask=navigation_mask,)         
            
        messages.information('Performing decomposition analysis')

        dc = self.data
            
        #set the output target (peak results or not?)
        target = self.learning_results
        
        # Transform the None masks in slices to get the right behaviour
        if navigation_mask is None:
            navigation_mask = slice(None)
        if signal_mask is None:
            signal_mask = slice(None)
        
        # Reset the explained_variance which is not set by all the algorithms
        explained_variance = None
        explained_variance_ratio = None
        mean = None
        
        if algorithm == 'svd':
            factors, loadings, explained_variance, mean = svd_pca(
                dc[:,signal_mask][navigation_mask,:], centre = centre,
                auto_transpose = auto_transpose)

        elif algorithm == 'fast_svd':
            factors, loadings, explained_variance, mean = svd_pca(
                dc[:,signal_mask][navigation_mask,:],
            fast = True, output_dimension = output_dimension, centre = centre,
                auto_transpose = auto_transpose)

        elif algorithm == 'sklearn_pca':
            if sklearn_installed is False:
                raise ImportError(
                'sklearn is not installed. Nothing done')
            sk = sklearn.decomposition.PCA(**kwargs)
            sk.n_components = output_dimension
            loadings = sk.fit_transform((dc[:,signal_mask][navigation_mask,:]))
            factors = sk.components_.T
            explained_variance = sk.explained_variance_
            mean = sk.mean_
            centre = 'trials'   

        elif algorithm == 'nmf':
            if sklearn_installed is False:
                raise ImportError(
                'sklearn is not installed. Nothing done')
            sk = sklearn.decomposition.NMF(**kwargs)
            sk.n_components = output_dimension
            loadings = sk.fit_transform((dc[:,signal_mask][navigation_mask,:]))
            factors = sk.components_.T
            
        elif algorithm == 'sparse_pca':
            if sklearn_installed is False:
                raise ImportError(
                'sklearn is not installed. Nothing done')
            sk = sklearn.decomposition.SparsePCA(output_dimension, **kwargs)
            loadings = sk.fit_transform(dc[:,signal_mask][navigation_mask,:])
            factors = sk.components_.T
            
        elif algorithm == 'mini_batch_sparse_pca':
            if sklearn_installed is False:
                raise ImportError(
                'sklearn is not installed. Nothing done')
            sk = sklearn.decomposition.MiniBatchSparsePCA(output_dimension,
                                                            **kwargs)
            loadings = sk.fit_transform(dc[:,signal_mask][navigation_mask,:])
            factors = sk.components_.T

        elif algorithm == 'mlpca' or algorithm == 'fast_mlpca':
            print "Performing the MLPCA training"
            if output_dimension is None:
                messages.warning_exit(
                "For MLPCA it is mandatory to define the output_dimension")
            if var_array is None and var_func is None:
                messages.information('No variance array provided.'
                'Supposing poissonian data')
                var_array = dc[:,signal_mask][navigation_mask,:]

            if var_array is not None and var_func is not None:
                messages.warning_exit(
                "You have defined both the var_func and var_array keywords"
                "Please, define just one of them")
            if var_func is not None:
                if hasattr(var_func, '__call__'):
                    var_array = var_func(dc[signal_mask,...][:,navigation_mask])
                else:
                    try:
                        var_array = np.polyval(polyfit,dc[signal_mask,
                        navigation_mask])
                    except:
                        messages.warning_exit(
                        'var_func must be either a function or an array'
                        'defining the coefficients of a polynom')
            if algorithm == 'mlpca':
                fast = False
            else:
                fast = True
            U,S,V,Sobj, ErrFlag = mlpca(
                dc[:,signal_mask][navigation_mask,:],
                var_array, output_dimension, fast = fast)
            loadings = U * S
            factors = V
            explained_variance_ratio = S ** 2 / Sobj
            explained_variance = S ** 2 / len(factors)
        else:
            raise ValueError('Algorithm not recognised. '
                                 'Nothing done')

        # We must calculate the ratio here because otherwise the sum information
        # can be lost if the user call crop_decomposition_dimension
        if explained_variance is not None and explained_variance_ratio is None:
            explained_variance_ratio = \
                explained_variance / explained_variance.sum()
                
        # Store the results in learning_results
        target.factors = factors
        target.loadings = loadings
        target.explained_variance = explained_variance
        target.explained_variance_ratio = explained_variance_ratio
        target.decomposition_algorithm = algorithm
        target.poissonian_noise_normalized = \
            normalize_poissonian_noise
        target.output_dimension = output_dimension
        target.unfolded = self._unfolded4decomposition
        target.centre = centre
        target.mean = mean
        

        if output_dimension and factors.shape[1] != output_dimension:
            target.crop_decomposition_dimension(output_dimension)
        
        # Delete the unmixing information, because it'll refer to a previous
        # decompositions
        target.unmixing_matrix = None
        target.bss_algorithm = None

        if self._unfolded4decomposition is True:
            target.original_shape = self._shape_before_unfolding

        # Reproject
        if mean is None:
            mean = 0
        if reproject in ('navigation', 'both'):
            if algorithm not in ('nmf', 'sparse_pca', 'mini_batch_sparse_pca'):
                loadings_ = np.dot(dc[:,signal_mask] - mean, factors)
            else:
                loadings_ = sk.transform(dc[:,signal_mask])
            target.loadings = loadings_
        if reproject in ('signal', 'both'):
            if algorithm not in ('nmf', 'sparse_pca', 'mini_batch_sparse_pca'):
                factors = np.dot(np.linalg.pinv(loadings), 
                                 dc[navigation_mask,:] - mean).T
                target.factors = factors
            else:
                messages.information("Reprojecting the signal is not yet "
                                     "supported for this algorithm")
                if reproject == 'both':
                    reproject = 'signal'
                else:
                    reproject = None
        
        # Rescale the results if the noise was normalized
        if normalize_poissonian_noise is True:
            target.factors[:] *= self._root_bH.T
            target.loadings[:] *= self._root_aG
            
        # Set the pixels that were not processed to nan
        if not isinstance(signal_mask, slice):
            target.signal_mask = signal_mask
            if reproject not in ('both', 'signal'):
                factors = np.zeros((dc.shape[-1], target.factors.shape[1]))
                factors[signal_mask == True,:] = target.factors
                factors[signal_mask == False,:] = np.nan
                target.factors = factors
        if not isinstance(navigation_mask, slice):
            target.navigation_mask = navigation_mask
            if reproject not in ('both', 'navigation'):
                loadings = np.zeros((dc.shape[0], target.loadings.shape[1]))
                loadings[navigation_mask == True,:] = target.loadings
                loadings[navigation_mask == False,:] = np.nan
                target.loadings = loadings

        #undo any pre-treatments
        self.undo_treatments()
        
        if self._unfolded4decomposition is True:
            self.fold()
            self._unfolded4decomposition is False
    
    def get_factors_as_spectrum(self):
        from hyperspy.signals.spectrum import Spectrum
        return Spectrum({'data' : self.learning_results.factors.T})
    
    def blind_source_separation(
        self, number_of_components=None, algorithm='CuBICA', diff_order=1,
        factors=None, comp_list=None, mask=None, 
        on_loadings=False,pretreatment = None, **kwargs):
        """Blind source separation (BSS) on the result on the decomposition.

        Available algorithms: FastICA, JADE, CuBICA, and TDSEP

        Parameters
        ----------
        number_of_components : int
            number of principal components to pass to the BSS algorithm
        algorithm : {FastICA, JADE, CuBICA, TDSEP}
        diff_order : int
        factors : numpy array
            externally provided components
        comp_list : boolen numpy array
            choose the components to use by the boolean list. It permits to
            choose non contiguous components.
        mask : numpy boolean array with the same dimension as the PC
            If not None, only the selected channels will be used by the
            algorithm.
        pretreatment: dict
        
        Any extra parameter is passed to the ICA algorithm
        """
        target=self.learning_results

        if not hasattr(target, 'factors') or target.factors==None:
            self.decomposition()

        else:
            if factors is None:
                if on_loadings:
                    factors = target.loadings
                else:
                    factors = target.factors
            bool_index = np.zeros((factors.shape[0]), dtype = 'bool')
            if number_of_components is not None:
                bool_index[:number_of_components] = True
            else:
                if target.output_dimension is not None:
                    number_of_components = target.output_dimension
                    bool_index[:number_of_components] = True

            if comp_list is not None:
                for ifactors in comp_list:
                    bool_index[ifactors] = True
                number_of_components = len(comp_list)
            factors = factors[:,bool_index]
            if diff_order > 0 and pretreatment is None:
                factors = np.diff(factors, diff_order, axis = 0)
            if pretreatment is not None:
                from hyperspy.signals.spectrum import Spectrum
                sfactors = Spectrum({'data' : factors.T})
                if pretreatment['algorithm'] == 'savitzky_golay':
                    sfactors.smooth_savitzky_golay(
                        number_of_points = pretreatment['number_of_points'],
                        polynomial_order = pretreatment['polynomial_order'],
                        differential_order = diff_order)
                if pretreatment['algorithm'] == 'tv':
                    sfactors.smooth_tv(
                        smoothing_parameter= pretreatment[
                            'smoothing_parameter'],
                        differential_order = diff_order)
                factors = sfactors.data.T
                if pretreatment['algorithm'] == 'butter':
                    b, a = sp.signal.butter(pretreatment['order'],
                        pretreatment['cutoff'], pretreatment['type'])
                    for i in range(factors.shape[1]):
                        factors[:,i] = sp.signal.filtfilt(b, a, factors[:,i])
            
            if mask is not None:
                factors = factors[mask.ravel(), :]

            # first centers and scales data
            factors,invsqcovmat = centering_and_whitening(factors)
            if algorithm == 'orthomax':
                _, unmixing_matrix = utils.orthomax(factors, **kwargs)
                unmixing_matrix = unmixing_matrix.T
            
            elif algorithm == 'sklearn_fastica':
                if sklearn_installed is False:
                    raise ImportError(
                    'sklearn is not installed. Nothing done')
                target.bss_node = sklearn.decomposition.FastICA(**kwargs)
                target.bss_node.whiten = False
                target.bss_node.fit(factors)
                unmixing_matrix = target.bss_node.unmixing_matrix_
            
            else:
                if mdp_installed is False:
                    raise ImportError(
                    'MDP is not installed. Nothing done')
                to_exec = 'target.bss_node=mdp.nodes.%sNode(' % algorithm
                for key, value in kwargs.iteritems():
                    to_exec += '%s=%s,' % (key, value)
                to_exec += ')'
                exec(to_exec)
                target.bss_node.train(factors)
                unmixing_matrix = target.bss_node.get_recmatrix()

            target.unmixing_matrix = np.dot(unmixing_matrix, invsqcovmat)
            self._unmix_factors(target)
            self._unmix_loadings(target)
            self._auto_reverse_bss_component(target)
            target.bss_algorithm = algorithm
            
    def normalize_factors(self, which='bss',by='area', sort=True):
        """Normalises the factors and modifies the loadings 
        accordingly
        
        Parameters
        ----------
        which : 'bss' | 'decomposition'
        by : 'max' | 'area'
        sort : bool
        
        """
        if which == 'bss':
            factors = self.learning_results.bss_factors
            loadings = self.learning_results.bss_loadings
            if factors is None:
                raise UserWarning("This method can only be used after a "
                    "blind source separation operation")
        elif which == 'decomposition':
            factors = self.learning_results.factors
            loadings = self.learning_results.loadings
            if factors is None:
                raise UserWarning("This method can only be used after a "
                    "decomposition operation")
        else:
            raise ValueError("what must be bss or decomposition")
        
        if by == 'max':
            by = np.max
        elif by == 'area':
            by = np.sum
        else:
            raise ValueError("by must be max or mean")
            
        factors /= by(factors,0)
        loadings *= by(factors,0)
        sorting_indexes = np.argsort(loadings.max(0))
        factors[:] = factors[:,sorting_indexes]
        loadings[:] = loadings[:,sorting_indexes]
        loadings[:] = loadings[:,sorting_indexes]

    def reverse_bss_component(self, component_number):
        """Reverse the independent component

        Parameters
        ----------
        component_number : list or int
            component index/es

        Examples
        -------
        >>> s = load('some_file')
        >>> s.decomposition(True) # perform PCA
        >>> s.blind_source_separation(3)  # perform ICA on 3 PCs
        >>> s.reverse_bss_component(1) # reverse IC 1
        >>> s.reverse_bss_component((0, 2)) # reverse ICs 0 and 2
        """

        target=self.learning_results

        for i in [component_number,]:
            target.bss_factors[:,i] *= -1
            target.bss_loadings[:,i] *= -1
            target.unmixing_matrix[i,:] *= -1

    def _unmix_factors(self,target):
        w = target.unmixing_matrix
        n = len(w)
        if target.explained_variance is not None:
            # The output of ICA is not sorted in any way what makes it difficult
            # to compare results from different unmixings. The following code
            # is an experimental attempt to sort them in a more predictable way
            sorting_indexes = np.argsort(np.dot(target.explained_variance[:n],
                np.abs(w.T)))[::-1]
            w[:] = w[sorting_indexes,:]
        target.bss_factors = np.dot(target.factors[:,:n], w.T)
    
    def _auto_reverse_bss_component(self, target):
        n_components = target.bss_factors.shape[1]
        for i in xrange(n_components):
            minimum = np.nanmin(target.bss_loadings[:,i])
            maximum = np.nanmax(target.bss_loadings[:,i])
            if minimum < 0 and -minimum > maximum:
                self.reverse_bss_component(i)
                print("IC %i reversed" % i)

    def _unmix_loadings(self,target):
        """
        Returns the ICA score matrix (formerly known as the recmatrix)
        """
        W = target.loadings.T[:target.bss_factors.shape[1],:]
        Q = np.linalg.inv(target.unmixing_matrix.T)
        target.bss_loadings = np.dot(Q,W).T

    @do_not_replot
    def _calculate_recmatrix(self, components = None, mva_type=None,):
        """
        Rebuilds SIs from selected components

        Parameters
        ------------
        target : target or self.peak_learning_results
        components : None, int, or list of ints
             if None, rebuilds SI from all components
             if int, rebuilds SI from components in range 0-given int
             if list of ints, rebuilds SI from only components in given list
        mva_type : string, currently either 'decomposition' or 'bss'
             (not case sensitive)

        Returns
        -------
        Signal instance
        """

        target=self.learning_results

        if mva_type.lower() == 'decomposition':
            factors = target.factors
            loadings = target.loadings.T
        elif mva_type.lower() == 'bss':
            factors = target.bss_factors
            loadings = target.bss_loadings.T
        if components is None:
            a = np.dot(factors,loadings)
            signal_name = 'model from %s with %i components' % (
            mva_type,factors.shape[1])
        elif hasattr(components, '__iter__'):
            tfactors = np.zeros((factors.shape[0],len(components)))
            tloadings = np.zeros((len(components),loadings.shape[1]))
            for i in xrange(len(components)):
                tfactors[:,i] = factors[:,components[i]]
                tloadings[i,:] = loadings[components[i],:]
            a = np.dot(tfactors, tloadings)
            signal_name = 'model from %s with components %s' % (
            mva_type,components)
        else:
            a = np.dot(factors[:,:components],
                                     loadings[:components,:])
            signal_name = 'model from %s with %i components' % (
            mva_type,components)

        self._unfolded4decomposition = self.unfold_if_multidim()

        sc = self.deepcopy()

        import hyperspy.signals.spectrum
        #if self.mapped_parameters.record_by==spectrum:
        sc.data = a.T.squeeze()
        #else:
        #    sc.data = a.squeeze()
        sc.mapped_parameters.title += signal_name
        if target.mean is not None:
            sc.data += target.mean
        if self._unfolded4decomposition is True:
            self.fold()
            sc.history = ['unfolded']
            sc.fold()
        return sc

    def get_decomposition_model(self, components=None):
        """Return the spectrum generated with the selected number of principal
        components

        Parameters
        ------------
        components : None, int, or list of ints
             if None, rebuilds SI from all components
             if int, rebuilds SI from components in range 0-given int
             if list of ints, rebuilds SI from only components in given list

        Returns
        -------
        Signal instance
        """
        rec=self._calculate_recmatrix(components=components,
                                      mva_type='decomposition')
        rec.residual=rec.copy()
        rec.residual.data=self.data-rec.data
        return rec

    def get_bss_model(self,components = None):
        """Return the spectrum generated with the selected number of
        independent components

        Parameters
        ------------
        components : None, int, or list of ints
             if None, rebuilds SI from all components
             if int, rebuilds SI from components in range 0-given int
             if list of ints, rebuilds SI from only components in given list

        Returns
        -------
        Signal instance
        """
        rec=self._calculate_recmatrix(components=components, mva_type='bss',)
        rec.residual=rec.copy()
        rec.residual.data=self.data-rec.data
        return rec
        

    def plot_explained_variance_ratio(self, n=50, log = True,
                                      ax = None, label = None):
        """Plot the decomposition explained variance ratio vs index number

        Parameters
        ----------
        n : int
            Number of components
        log : bool
            If True, the y axis uses a log scale
        ax : matplotlib.axes instance
            The axes where to plot the figures. If None, a new figure will be
            created
        label: str
            An optional label for the legend
        """
        target = self.learning_results
        if target.explained_variance_ratio is None:
            messages.information(
                'No explained variance ratio information available')
            return 0
        if n > target.explained_variance_ratio.shape[0]:
            n = target.explained_variance_ratio.shape[0]
        if ax is None:
            fig = plt.figure()
            ax = fig.add_subplot(111)
        ax.plot(range(n), target.explained_variance_ratio[:n], 'o', label=label)
        if log is True:
            ax.semilogy()
        ax.set_ylabel('Explained variance ratio')
        ax.set_xlabel('Principal component index')
        plt.legend()
        plt.show()
        return ax

    def plot_cumulative_explained_variance_ratio(self,n=50):
        """Plot the principal components explained variance up to the given
        number

        Parameters
        ----------
        n : int
        """
        target = self.learning_results
        if n > target.explained_variance.shape[0]:
            n=target.explained_variance.shape[0]
        cumu = np.cumsum(target.explained_variance) / np.sum(
                                                     target.explained_variance)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.scatter(range(n), cumu[:n])
        ax.set_xlabel('Principal component')
        ax.set_ylabel('Cumulative explained variance ratio')
        plt.draw()
        plt.show()
        return ax

    def normalize_poissonian_noise(self, navigation_mask = None,
                                   signal_mask = None, return_masks = False):
        """
        Scales the SI following Surf. Interface Anal. 2004; 36: 203–212 to
        "normalize" the poissonian data for decomposition analysis

        Parameters
        ----------
        navigation_mask : boolen numpy array
        signal_mask  : boolen numpy array
        """
        messages.information(
            "Scaling the data to normalize the (presumably) Poissonian noise")
        refold = self.unfold_if_multidim()
        dc = self.data
        if navigation_mask is None:
            navigation_mask = slice(None)
        else:
            navigation_mask = navigation_mask.ravel()
        if signal_mask is None:
            signal_mask = slice(None)
        # Rescale the data to gaussianize the poissonian noise
        aG = dc[:,signal_mask][navigation_mask,:].sum(1).squeeze()
        bH = dc[:,signal_mask][navigation_mask,:].sum(0).squeeze()
        # Checks if any is negative
        if (aG < 0).any() or (bH < 0).any():
            messages.warning_exit(
            "Data error: negative values\n"
            "Are you sure that the data follow a poissonian distribution?")
        # Update the spatial and energy masks so it does not include rows
        # or colums that sum zero.
        aG0 = (aG == 0)
        bH0 = (bH == 0)
        if aG0.any():
            if isinstance(navigation_mask, slice):
                # Convert the slice into a mask before setting its values
                navigation_mask = np.ones((self.data.shape[0]),dtype = 'bool')
            # Set colums summing zero as masked
            navigation_mask[aG0] = False
            aG = aG[aG0 == False]
        if bH0.any():
            if isinstance(signal_mask, slice):
                # Convert the slice into a mask before setting its values
                signal_mask = np.ones((self.data.shape[1]), dtype = 'bool')
            # Set rows summing zero as masked
            signal_mask[bH0] = False
            bH = bH[bH0 == False]
        self._root_aG = np.sqrt(aG)[:, np.newaxis]
        self._root_bH = np.sqrt(bH)[np.newaxis, :]
        dc[:,signal_mask][navigation_mask,:] = \
            (dc[:,signal_mask][navigation_mask,:] /
                (self._root_aG * self._root_bH))
        if refold is True:
            print "Automatically refolding the SI after scaling"
            self.fold()
        if return_masks is True:
            if isinstance(navigation_mask, slice):
                navigation_mask = None
            if isinstance(signal_mask, slice):
                signal_mask = None
            return navigation_mask, signal_mask

    def undo_treatments(self):
        """Undo normalize_poissonian_noise"""
        print "Undoing data pre-treatments"
        self.data=self._data_before_treatments
        del self._data_before_treatments

class LearningResults(object):
    # Decomposition
    factors = None
    loadings = None
    explained_variance = None
    explained_variance_ratio = None
    decomposition_algorithm = None
    poissonian_noise_normalized = None
    output_dimension = None
    mean = None
    centre = None
    # Unmixing
    bss_algorithm = None
    unmixing_matrix = None
    bss_factors = None
    bss_loadings = None
    # Shape
    unfolded = None
    original_shape = None
    # Masks
    navigation_mask = None
    signal_mask =  None
    
    def save(self, filename):
        """Save the result of the decomposition and demixing analysis

        Parameters
        ----------
        filename : string
        """
        kwargs = {}
        for attribute in [
            v for v in dir(self) if type(getattr(self,v)) != types.MethodType
                and not v.startswith('_')]:
            kwargs[attribute] = self.__getattribute__(attribute)
        np.savez(filename, **kwargs)


    def load(self, filename):
        """Load the results of a previous decomposition and demixing analysis
        from a file.

        Parameters
        ----------
        filename : string
        """
        decomposition = np.load(filename)
        for key,value in decomposition.iteritems():
            if value.dtype == np.dtype('object'):
                value = None
                
            setattr(self, key, value)
        print "\n%s loaded correctly" %  filename

        # For compatibility with old version ##################

        if hasattr(self, 'algorithm'):
            self.decomposition_algorithm = self.algorithm
            del self.algorithm
        if hasattr(self, 'V'):
            self.explained_variance = self.V
            del self.V
        if hasattr(self, 'w'):
            self.unmixing_matrix = self.w
            del self.w
        if hasattr(self, 'variance2one'):
#            self.variance_normalized = self.variance2one
            del self.variance2one
        if hasattr(self, 'centered'):
            del self.centered
            
        if hasattr(self, 'pca_algorithm'):
            self.decomposition_algorithm = self.pca_algorithm
            del self.pca_algorithm
            
        if hasattr(self, 'ica_algorithm'):
            self.bss_algorithm = self.ica_algorithm
            del self.ica_algorithm
            
        if hasattr(self, 'v'):
            self.loadings = self.v
            del self.v

        if hasattr(self, 'scores'):
            self.loadings = self.scores
            del self.scores
            
        if hasattr(self, 'pc'):
            self.loadings = self.pc
            del self.pc
            
        if hasattr(self, 'ica_scores'):
            self.bss_loadings = self.ica_scores
            del self.ica_scores
            
        if hasattr(self, 'ica_factors'):
            self.bss_factors = self.ica_factors
            del self.ica_factors

        #######################################################
        
        # Output_dimension is an array after loading, convert it to int            
        if hasattr(self, 'output_dimension') and self.output_dimension \
                                                is not None:
            self.output_dimension = int(self.output_dimension)
        self.summary()

    def summary(self):
        """Prints a summary of the decomposition and demixing parameters to the 
        stdout
        """
        print
        print "Decomposition parameters:"
        print "-------------------------"
        print "Decomposition algorithm : ", self.decomposition_algorithm
        print "Poissonian noise normalization : %s" % \
        self.poissonian_noise_normalized
        print "Output dimension : %s" % self.output_dimension
        print "Centre : %s" % self.centre
        
        if self.bss_algorithm is not None:
            print
            print "Demixing parameters:"
            print "---------------------"
            print "BSS algorithm : %s" % self.bss_algorithm
            print "Number of components : %i" % len(self.unmixing_matrix)


    def crop_decomposition_dimension(self, n):
        """
        Crop the score matrix up to the given number.

        It is mainly useful to save memory and reduce the storage size
        """
        print "trimming to %i dimensions" % n
        self.loadings = self.loadings[:,:n]
        if self.explained_variance is not None:
            self.explained_variance = self.explained_variance[:n]
        self.factors = self.factors[:,:n]
        
    def _transpose_results(self):
        self.factors, self.loadings, self.bss_factors, self.bss_loadings = \
        self.loadings, self.factors, self.bss_loadings, self.bss_factors
        
