"""
Copyright (c) 2015-2016 Constantine Belev



Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:



The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.



THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import numpy as np
import scipy as sp

from scipy import linalg, sparse

from scipy.sparse import coo_matrix, csr_matrix, csc_matrix, lil_matrix

from riemannian_optimization.utils.approx_utils import csvd


def orth(a, eps=1e-12):
    return np.linalg.norm(a.T.dot(a) - np.eye(a.shape[1])) < eps * np.sqrt(a.shape[1])


def torth(a):
    return np.allclose(a.dot(a.T), np.eye(a.shape[0]))


# TODO remove this function if it is not nessesary
def indices_unveil(self, indices):
    """

    Parameters
    ----------
    self
    indices

    Returns
    -------

    """
    indices = np.asarray(indices)
    return np.vstack([np.repeat(indices[0], indices[1].size),
                      np.tile(indices[1], indices[0].size)]).T


class ManifoldElement(object):
    """
    ManifoldElement(data, r=None)

    Returns a rank-constrained SVD-based approximation of matrix, given by 2D array, or one of
    two decompositions: $A = UV^*$ or $A =  U\SigmaV^*$, where \Sigma is diagonal

    Parameters
    ----------
    data : array_like or (U, V) or (U, s, V) tuple
        matrix, which approximation we want to find
    r : int
        rank constraint


    Examples
    --------
    a = np.random.random((10, 5))
    approx = ManifoldElement(a, r=4)
    approx_full = approx.full_matrix()
    print(np.linalg.norm(a - approx_full) / np.linalg.norm(a))

    """
    def __init__(self, data, r=None):
        if isinstance(data, ManifoldElement):
            if r is None:
                ManifoldElement.__init__(self, data, data.r)
            elif r <= data.r:
                self.u = data.u[:, :r].copy()
                self.s = data.s[:r].copy()
                self.v = data.v[:r, :].copy()
                self.shape = data.shape
                self.r = r
            else:
                self.u = np.zeros(data.shape[0], r)
                self.s = np.zeros(r)
                self.v = np.zeros(r, data.shape[1])
                self.u[:, data.r] = data.u
                self.s[:data.r] = data.s
                self.v[:data.r, :] = data.v
                self.shape = data.shape
                self.r = r
        elif isinstance(data, np.ndarray):
            self.r = min(data.shape) if r is None else min(min(data.shape), r)
            self.shape = data.shape
            self.u, self.s, self.v = csvd(data, self.r)
        elif isinstance(data, tuple):
            if len(data) == 2:
                # we have u, v matrices
                u, v = data
                if u.shape[1] != v.shape[0]:
                    raise ValueError(
                        'u, v must be composable, but have shapes {}, {}'.format(u.shape, v.shape))
                self.r = u.shape[1] if r is None else min(u.shape[1], r)
                self.shape = (u.shape[0], v.shape[1])
                self.u, self.s, self.v = u, np.ones(self.r), v
                self.balance()
            elif len(data) == 3:
                u, s, v = data
                if len(s.shape) == 2:
                    s = np.diag(s)
                if u.shape[1] != v.shape[0] or u.shape[1] != s.size:
                    raise ValueError('u, s, v must be svd factorization of some matrix')
                self.r = u.shape[1] if r is None else min(r, u.shape[1])
                self.shape = (u.shape[0], v.shape[1])
                self.u, self.s, self.v = data
                if self.r < u.shape[1]:
                    self.u = self.u[:, :self.r].copy()
                    self.s = self.s[:self.r].copy()
                    self.v = self.v[:self.r, :].copy()
                if not np.allclose(self.s.argsort(), np.arange(self.s.size)[::-1]):
                    self.rearrange()        # We lost ordering of s while performing addition
                self.balance()              # We lost orthogonality while performing hadamard
            else:
                raise ValueError("Arguments in tuple are not supported")
        else:
            raise ValueError("Arguments are not supported")

    def rearrange(self):
        """
        rearrange permutes U \Sigma V^* matrix to obtain
        non-increasing property on diagonal \Sigma matrix

        Returns
        -------
        None
        """
        permutation = self.s.argsort()
        self.u = self.u[:, permutation]
        self.v = self.v[permutation, :]
        self.s = self.s[permutation]
        return None

    def _balance_right(self):
        """
        We only have non-orthogonal v factor, so we need to orthogonalize
        it
        Returns
        -------
        None
        """
        u, self.s, self.v = csvd(np.diag(self.s).dot(self.v))
        self.u = self.u.dot(u)
        return None

    def _balance_left(self):
        """
        We only have non-orthogonal u factor, so we need to orthogonalize
        it
        Returns
        -------
        None
        """
        self.u, self.s, v = csvd(self.u.dot(np.diag(self.s)))
        self.v = v.dot(self.v)
        return None

    def _balance(self):
        """
        All factors are non-orthogonal, so we need full orthogonalization
        Returns
        -------
        None
        """
        mid, self.v = sp.linalg.rq(self.v)
        self.u = self.u.dot(np.diag(self.s).dot(mid))
        self.u, self.s, v = csvd(self.u)
        self.v = v.dot(self.v)
        return None

    def balance(self):
        """
        Performs reorthogonalization of factors, if it needs
        Returns
        -------
        None
        """
        left_balanced = orth(self.u)
        right_balanced = orth(self.v.T)
        if left_balanced:
            if right_balanced:
                pass
            else:
                self._balance_right()
        else:
            if right_balanced:
                self._balance_left()
            else:
                self._balance()
        return

    def is_valid(self):
        """
        Performs validness check. This include checks like:
        * is left core (U) orthogonal?
        * is right core (V^*) orthogonal?
        * is singular values (\Sigma) are in non-increasing order?
        Result will be logical and of these checks.

        Returns
        -------
        status : bool
            Validity status of ManifoldElement object
        """
        left_balanced = orth(self.u)
        right_balanced = orth(self.v.T)
        sigma_sorted = \
            np.allclose(self.s.argsort(), np.arange(self.s.size)[::-1])
        return left_balanced and right_balanced and sigma_sorted

    def __add__(self, other):
        if isinstance(other, np.ndarray):
            other = ManifoldElement(other, self.r)
            return self.__add__(other)
        elif isinstance(other, ManifoldElement):
            u = np.hstack((self.u, other.u))
            s = np.concatenate((self.s, other.s))
            v = np.vstack((self.v, other.v))
            u, r = np.linalg.qr(u)
            rt, v = sp.linalg.rq(v, mode='economic')
            middle_factor = r.dot(np.diag(s)).dot(rt)
            u_mid, s, v_mid = np.linalg.svd(middle_factor, full_matrices=False)
            u = u.dot(u_mid)
            v = v_mid.dot(v)

            factorization = (u, s, v)
            return ManifoldElement(factorization)
        else:
            raise ValueError(
                "operation is not supported for ManifoldElement and {}".format(type(other)))

    def __radd__(self, other):
        if not isinstance(other, np.ndarray) or not isinstance(other, ManifoldElement):
            raise ValueError(
                "operation is not supported for ManifoldElement and {}".format(type(other)))
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, np.ndarray):
            other = ManifoldElement(other, self.r)
            return self.__sub__(other)
        elif isinstance(other, ManifoldElement):
            return self + (-other)
        else:
            raise ValueError(
                "operation is not supported for ManifoldElement and {}".format(type(other)))

    def __rsub__(self, other):
        if not isinstance(other, np.ndarray) or not isinstance(other, ManifoldElement):
            raise ValueError(
                "operation is not supported for ManifoldElement and {}".format(type(other)))
        return self.__sub__(other)

    def __neg__(self):
        return ManifoldElement((-self.u, self.s, self.v))

    def __mul__(self, other):
        if np.isscalar(other):
            return ManifoldElement((self.u, self.s * other, self.v))
        if isinstance(other, ManifoldElement):
            if self.shape != other.shape:
                raise ValueError("Shapes {} and {} are not equal.".format(self.shape, other.shape))
            u = np.zeros((self.shape[0], self.r * other.r))
            for i in range(self.shape[0]):
                u[i, :] = np.kron(self.u[i, :], other.u[i, :])
            s = np.kron(self.s, other.s)
            v = np.zeros((self.r * other.r, self.shape[1]))
            for i in range(self.shape[1]):
                v[:, i] = np.kron(self.v[:, i], other.v[:, i])
            return ManifoldElement((u, s, v))
        else:
            raise ValueError("mul supports only scalars and ManifoldElement instances")

    def __rmul__(self, other):
        # TODO do we need this right-side operator?
        # if yes, make it more clever
        if np.isscalar(other):
            return ManifoldElement((self.u, self.s * other, self.v))
        else:
            raise NotImplementedError('rmul operator is not implemented, except for scalars')

    def transpose(self):
        return ManifoldElement((self.v.T, self.s, self.u.T))

    @property
    def T(self):
        return self.transpose()

    def dot(self, other):
        """
        Matrix product.
        Supports np.ndarray, sp.sparse.spmatrix or ManifoldElement left side.

        Parameters
        ----------
        other : sp.sparse.spmatrix, np.ndarray or ManifoldElement
            matrix to perform matrix product

        Returns
        -------
        prod : ManifoldElement
            matrix product
        """
        if self.shape[1] != other.shape[0]:
            raise ValueError("shapes must match!")
        if isinstance(other, ManifoldElement):
            r_mid = np.dot(np.diag(self.s), self.v.dot(other.u)).dot(np.diag(other.s))
            u, s, v = np.linalg.svd(r_mid, full_matrices=False)
            u = self.u.dot(u)
            v = v.dot(other.v)
            return ManifoldElement((u, s, v))
        elif isinstance(other, np.ndarray):
            # TODO there are some ways to optimize (all balance work gone to constructor)
            return ManifoldElement((self.u, self.s, self.v.dot(other)))
        elif sp.sparse.issparse(other):
            return ManifoldElement((self.u, self.s, csc_matrix(other).__rmul__(self.v)))
        else:
            raise ValueError("argument is not supported")

    def rdot(self, other):
        """
        Matrix product where self is right-sided.
        Supports np.ndarray, sp.sparse.spmatrix or ManifoldElement left side.

        Parameters
        ----------
        other : sp.sparse.spmatrix, np.ndarray or ManifoldElement
            matrix to perform matrix product

        Returns
        -------
        prod : ManifoldElement
            matrix product
        """
        if self.shape[0] != other.shape[1]:
            raise ValueError("shapes must match!")
        if isinstance(other, ManifoldElement):
            return other.dot(self)
        elif isinstance(other, np.ndarray):
            return ManifoldElement((other.dot(self.u), self.s, self.v))
        elif sp.sparse.issparse(other):
            return ManifoldElement((csr_matrix(other).dot(self.u), self.s, self.v))
        else:
            raise ValueError("argument is not supported")

    def full_matrix(self):
        """
        Retrieve full matrix from it's decomposition

        Returns
        -------
        a : np.ndarray
            full matrix, given by approximation
        """
        return self.u.dot(np.diag(self.s)).dot(self.v)

    def trace(self):
        """
        Returns trace of a matrix

        Returns
        -------
        out: float
            trace of a matrix
        """
        return np.einsum('ij, ji ->', self.u * self.s, self.v)

    def scalar_product(self, other):
        """
        Returns scalar product of two ManifoldElements

        Parameters
        ----------
        other : ManifoldElement
            element for which scalar product will be computed

        Returns
        -------
        out: float
            scalar product of two ManifoldElements
        """
        if self.shape != other.shape:
            raise ValueError('Shapes mismatch.')
        return self.dot(other.T).trace()

    def frobenius_norm(self):
        """
        Frobenius norm of matrix approximation

        Returns
        -------
        n : float
            norm of the matrix
        """
        return np.linalg.norm(self.s)

    def evaluate(self, sigma_set):
        """
        Retrieve values of full matrix only on a given set of indices

        Parameters
        ----------
        sigma_set : array_like

        Returns
        -------
        out : csr_matrix
            full matrix evaluated at sigma_set
        """
        idx_argsort = sigma_set[0].argsort()
        sigma_set[1][:] = sigma_set[1][idx_argsort]
        sigma_set[0][:] = sigma_set[0][idx_argsort]
        data = np.zeros(len(sigma_set[0]))
        for (val, idx, count) in zip(*np.unique(sigma_set[0],
                                               return_index=True,
                                               return_counts=True)):
            data[idx:idx + count] = np.dot(self.u[val, :] * self.s,
                                           self.v[:, sigma_set[1][idx: idx + count]])
        return csr_matrix(coo_matrix((data, tuple(sigma_set)), shape=self.shape))

    def isclose(self, other, tol=1e-9):
        """
        Check if element is close to another in frobenius norm.

        Parameters
        ----------
        other : ManifoldElement
            element to check closeness
        tol : float
            tolerance for closeness

        Returns
        -------
        status: bool
            flag indicates that to elements are close or not
        """
        if isinstance(other, ManifoldElement):
            raise ValueError("we can measure closeness only between ManifoldElements")
        largest_norm = max(self.frobenius_norm(), other.frobenius_norm())
        if largest_norm == 0:
            return True
        else:
            return (self - other).frobenius_norm() / largest_norm < tol

    @staticmethod
    def rand(shape, r, desired_norm=None):
        """
        Generates ManifoldElement with parameters:
        * U (shape[0], r) with elements picked from N(0, 1)
        * \Sigma with sorted elements picked from N(0, 1), with desired norm, if given
        * V^* (r, shape[1]) with elements picked from N(0, 1)
        where N(0, 1) means standard normal distribution

        Parameters
        ----------
        shape : tuple of ints
            Output shape.
        r : int
            Desired rank
        desired_norm : float, optional
            Desired frobenius norm of matrix

        Returns
        -------
            out : ManifoldElement
                Randomly generated matrix
        """
        m, n = shape

        u = np.linalg.qr(np.random.randn(m, r))[0]
        s = np.sort(np.abs(np.random.randn(r)))[::-1]
        if desired_norm is not None:
            s *= (desired_norm / np.linalg.norm(s))
        v = sp.linalg.rq(np.random.randn(r, n), mode='economic')[1]
        return ManifoldElement((u, s, v))
