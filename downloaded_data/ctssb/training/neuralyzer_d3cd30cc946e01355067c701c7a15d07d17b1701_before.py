'''
Non-Negative Matrix factorization implementations.

!! EXPERIMENTAL !!

'''

from __future__ import print_function

import numpy as np

try:
    from sklearn.externals.joblib import Parallel, delayed
    N_JOBS = -1
    JOBLIB_TMP_FOLDER = '/tmp'
except:
    print('joblib could not be imported. NO PARALLEL JOB EXECUTION!')
    N_JOBS = None 

from neuralyzer.log import get_logger




TINY_POSITIVE_NUMBER = np.finfo(np.float).tiny 



def nmf_cvxpy(A, k, max_iter=30):
    '''
    An alternating convex optimization Ansatz.

    This implementation is rather slow ..
    '''

    import cvxpy as cvx
    
    m, n = A.shape

    # Initialize Y randomly.
    Y = np.random.rand(m, k)

    # Perform alternating minimization.
    residual = np.zeros(max_iter)
    for iter_num in range(1, 1+max_iter):
        # At the beginning of an iteration, X and Y are NumPy
        # array types, NOT CVXPY variables.

        # For odd iterations, treat Y constant, optimize over X.
        if iter_num % 2 == 1:
            X = cvx.Variable(k, n)
            constraint = [X >= 0]
        # For even iterations, treat X constant, optimize over Y.
        else:
            Y = cvx.Variable(m, k)
            constraint = [Y >= 0]
        
        # Solve the problem.
        obj = cvx.Minimize(cvx.norm(A - Y*X, 'fro'))
        prob = cvx.Problem(obj, constraint)
        prob.solve(solver=cvx.SCS)

        if prob.status != cvx.OPTIMAL:
            raise Exception("Solver did not converge!")
        
        print('Iteration {}, residual norm {}'.format(iter_num, prob.value))
        residual[iter_num-1] = prob.value

        # Convert variable to NumPy array constant for next iteration.
        if iter_num % 2 == 1:
            X = X.value
        else:
            Y = Y.value

    return X, Y



def nmf_lars(V, k, H_init=None, max_iter=30, morph=True,
        log=False, **kwargs):
    '''
    
    V = WH : V, W, H >= 0

    V.shape = (m, n)
    W.shape = (m, k)
    H.shape = (k, n)

    '''

    from sklearn.linear_model import LassoLars 

    logger = get_logger()
    
    m, n = V.shape

    # Initialize W randomly.
    if H_init is not None:
        H = H_init
    else:
        H = np.random.rand(n, k)
    

    # Perform 'alternating' minimization.
    for iter_num in range(max_iter):

        if log:
            logger.info('iteration : %s / %s' % (iter_num+1, max_iter))

        lB = LassoLars(positive=True, max_iter=200, alpha=0.5, normalize=True, **kwargs)
        lB.fit(H, V.T)
        W = lB.coef_

        lA = LassoLars(positive=True, max_iter=200, alpha=0.05, normalize=True, **kwargs)
        lA.fit(W, V)
        H = lA.coef_

        if morph:
            H = _morph_image_components(H)

    return W, H



def _morph_image_components(H, imshape=(128,128)):
    from skimage import morphology
    m, k = H.shape
    for i in range(k):
        H[:, i] = morph_close_component(H[:,i], imshape) 
    return H


def median_filter_component(a, imshape):
    from skimage import filters, morphology
    # FIXME : disk size choice is arbitrary right now ..
    return filters.median(a.reshape(*imshape)/a.max(), morphology.disk(5)).flatten()


def morph_close_component(a, imshape):
    from skimage import morphology
    amorph = morphology.closing(a.reshape(imshape[0], imshape[1]))
    return amorph.flatten()




# -----------------------------------------------------------------------------
# Approximate L0 constrained Non-negative Matrix and Tensor Factorization 
# -----------------------------------------------------------------------------

from sklearn.linear_model import LassoLars


class NMF_L0(object):
    ''' An implementation of non-negative matrix factorization according to [1]

    Solves the equation     V = WH 
    for                     V, W, H >= 0
    with                    [V] = N x M, [W] = N x k, [H] = k x M 

    .. in an iterative, multiplicatve approach under Lars Lasso regularization
    of the number of active elements in H.

    References:
    [1] M. Morup, K. H. Madsen, L. K. Hansen, Approximate L0 constrained
    Non-negative Matrix and Tensor Factorization, IEEE 2008


    !!! WARNING !!!
    requires tweaked scikit-learn LassoLars implementation that allows
    non-negativity constraint on H.


    '''

    def __init__(self, spl0=0.3, iterations=100, logger=get_logger()):
        self._spl0 = spl0
        # TODO: iterations will have to be replaced by a stop criterion,
        # based on a the residual and max_iterations!
        self.iterations = iterations 
        self.logger=logger

    @property
    def spl0(self):
        return self._spl0


    def fit(self, V, H_init=None, W_init=None, k=None, njobs=N_JOBS):
        self.v_shape = V.shape
        if W_init is None:
            self._W = np.random.rand(self.v_shape[0], k)
        else:
            self._W = W_init
        if H_init is None:
            self._H = np.random.rand(k, self.v_shape[1])
        else:
            self._H = H_init

        for i in range(self.iterations):
            try:
                self._W = NMF_L0.update_W(V, self._H, self._W
                        ).clip( TINY_POSITIVE_NUMBER, np.inf)
                self._H = NMF_L0.update_H(V, self._W, spl0=self.spl0, njobs=njobs,
                        ).clip( TINY_POSITIVE_NUMBER, np.inf)
            # py3 cleanup TODO
            except:
                self.logger.exception('CANNOT UPDATE at iteration %s' % i)                
                break 


    @staticmethod
    def update_H(V, W, spl0=0.8, njobs=N_JOBS, joblib_tmp_folder=JOBLIB_TMP_FOLDER):
        '''
        !!! WARNING : requires tweaked scikit-learn LassoLars implementation
        that allows non-negativity, ie positivity, constraint on H.
        '''

        hs = []
        alphas = []

        if njobs is None:
            for n in range(V.shape[1]):

                ll = LARS(positive=True)
                ll.fit(W, V[:,n])
                alphas.append(ll.alphas_)
                hs.append(ll.coef_path_)

        else:
            # TODO : what about the temp folder now?
            #pout = Parallel(n_jobs=njobs, temp_folder=joblib_tmp_folder)(
            pout = Parallel(n_jobs=njobs)(
                    delayed(do_lars_fit)(W, V[:,pidx], return_path=True)
                    for pidx in range(V.shape[1])
                    )
            for ll in pout:
                alphas.append(ll[0])
                hs.append(ll[1])


        # SORT OUT H here according to sparseness criterion
        alphs = np.concatenate(alphas)
        # approximate l0 cut off
        # TODO : this is problematic because coefficients can be dropped ..
        numcomps = (1.-spl0)*V.shape[0]*V.shape[1]
        cutoff = -np.percentile(-alphs, (1.-spl0)*100) 
        H = []
        for n in range(len(hs)):
            H.append(hs[n][:, np.where((alphas[n] - cutoff) <= 0)[0][0]])

        H = np.array(H).T
        return H


    @staticmethod
    def update_W(V, H, W):
        n, m = V.shape
        n, k = W.shape
        W = np.multiply(W,
                np.multiply(
                    np.dot(V, H.T) + 
                        np.dot(W,
                            np.diag(
                                np.dot(
                                    np.ones((1, n)),
                                    np.multiply(np.dot(W, np.dot(H, H.T)), W)
                                ).flatten()
                            )
                        ),
                    1./(np.dot(W, np.dot(H, H.T)) + 
                        np.dot(
                            W, 
                            np.diag(
                                np.dot(np.ones((1, n)),
                                    np.multiply(np.dot(V, H.T), W)
                                    ).flatten()
                            )
                        )
                       )
                )
            )
        return W




# LARS
# -----------------------------------------------------------------------------
# slim implementation of the sklearns LassoLars algorithm with a couple of
# adaptations

from sklearn.linear_model.least_angle import lars_path


class LARS(object):

    def __init__(self, positive=True, eps=np.finfo(np.float).eps,
            copy_X=True, max_iter=500,):

        self.method = 'lasso'
        self.positive = positive 
        self.eps = eps
        self.copy_X = copy_X
        self.max_iter = max_iter


    def fit(self, X, y, Xy=None, return_path=True, alpha_min=0.):

        self._alpha_min = alpha_min

        ### maybe do some checks on the inputs here

        ### set up
        if self.copy_X:
            X = X.copy()
        n_features = X.shape[1]

        if y.ndim == 1:
            y = y[:, np.newaxis]
        n_targets = y.shape[1]

        self.alphas_ = []
        self.n_iter_ = []

        self.coef_ = []
        self.active_ = []
        self.coef_path_ = []

        for k in xrange(n_targets):
            this_Xy = None if Xy is None else Xy[:, k]
            alphas, active, coef_path, n_iter_ = lars_path(
                X, y[:, k], Gram=None, Xy=this_Xy, copy_X=self.copy_X,
                copy_Gram=True, alpha_min=self._alpha_min, method=self.method,
                max_iter=self.max_iter, eps=self.eps, return_path=return_path,
                return_n_iter=True, positive=self.positive)
            self.alphas_.append(alphas)
            self.active_.append(active)
            self.n_iter_.append(n_iter_)
            if return_path:
                self.coef_path_.append(coef_path)
                self.coef_.append(coef_path[:, -1])
            else:
                self.coef_.append(coef_path)

        if n_targets == 1:
            self.n_iter_ = self.n_iter_[0]
            if return_path:
                self.alphas_, self.active_, self.coef_path_, self.coef_ = [
                    a[0] for a in (self.alphas_, self.active_, self.coef_path_,
                                   self.coef_)]
            else:
                self.alphas_, self.active_, self.coef_ = [
                    a[0] for a in (self.alphas_, self.active_, self.coef_)]

        return self


def do_lars_fit(X, y, alpha=0., return_path=False):
    ll = LARS(positive=True)
    ll.fit(X, y, alpha_min=alpha, return_path=return_path)
    if return_path:
        return ll.alphas_, ll.coef_path_
    else:
        return ll.coef_
