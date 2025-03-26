# Authors: Olivier Grisel <olivier.grisel@ensta.org>
#          Alexandre Gramfort <alexandre.gramfort@inria.fr>
# License: BSD Style.


import numpy as np
from numpy.testing import *
from nose.tools import *

from ..coordinate_descent import Lasso, LassoPath, lasso_path
from ..coordinate_descent import ElasticNet, ElasticNetPath, enet_path

def test_Lasso_toy():
    """
    Test Lasso on a toy example for various values of alpha.

    When validating this against glmnet notice that glmnet divides it
    against nobs.
    """

    X = [[-1], [0], [1]]
    Y = [-1, 0, 1]       # just a straight line
    T = [[2], [3], [4]]  # test sample

    clf = Lasso(alpha=0)
    clf.fit(X, Y)
    pred = clf.predict(T)
    assert_array_almost_equal(clf.coef_, [1])
    assert_array_almost_equal(pred, [2, 3, 4])
    assert_almost_equal(clf.dual_gap_,  0)

    clf = Lasso(alpha=0.1)
    clf.fit(X, Y)
    pred = clf.predict(T)
    assert_array_almost_equal(clf.coef_, [.85])
    assert_array_almost_equal(pred, [ 1.7 ,  2.55,  3.4 ])
    assert_almost_equal(clf.dual_gap_, 0)

    clf = Lasso(alpha=0.5)
    clf.fit(X, Y)
    pred = clf.predict(T)
    assert_array_almost_equal(clf.coef_, [.25])
    assert_array_almost_equal(pred, [0.5, 0.75, 1.])
    assert_almost_equal(clf.dual_gap_, 0)

    clf = Lasso(alpha=1)
    clf.fit(X, Y)
    pred = clf.predict(T)
    assert_array_almost_equal(clf.coef_, [.0])
    assert_array_almost_equal(pred, [0, 0, 0])
    assert_almost_equal(clf.dual_gap_, 0)


def test_Enet_toy():
    """
    Test ElasticNet for various parameters of alpha and rho.

    Actualy, the parameters alpha = 0 should not be alowed. However,
    we test it as a border case.
    """

    X = [[-1], [0], [1]]
    Y = [-1, 0, 1]       # just a straight line
    T = [[2], [3], [4]]  # test sample

    # this should be the same as lasso
    clf = ElasticNet(alpha=0, rho=1.0)
    clf.fit(X, Y)
    pred = clf.predict(T)
    assert_array_almost_equal(clf.coef_, [1])
    assert_array_almost_equal(pred, [2, 3, 4])
    assert_almost_equal(clf.dual_gap_, 0)

    # clf = ElasticNet(alpha=0.5, rho=0.3)
    # clf.fit(X, Y, maxit=1000)
    # pred = clf.predict(T)
    # assert_array_almost_equal(clf.coef_, [0.531], decimal=3)
    # assert_array_almost_equal(pred, [1.104, 1.656, 2.208], decimal=3)
    # assert_almost_equal(clf.dual_gap_, 0)

    clf = ElasticNet(alpha=0.5, rho=0.5)
    clf.fit(X, Y)
    pred = clf.predict(T)
    # assert_array_almost_equal(clf.coef_, [0.5])
    # assert_array_almost_equal(pred, [1, 1.5, 2.])
    assert_almost_equal(clf.dual_gap_, 0)


def test_lasso_path_early_stopping():

    # build an ill-posed linear regression problem with many noisy features and
    # comparatively few samples
    n_samples, n_features, maxit = 50, 200, 30
    np.random.seed(0)
    w = np.random.randn(n_features)
    w[10:] = 0.0 # only the top 10 features are impacting the model
    X = np.random.randn(n_samples, n_features)
    y = np.dot(X, w)

    clf = LassoPath(n_alphas=100, eps=1e-3).fit(
        X, y, maxit=maxit, store_path=True)
    assert_equal(len(clf.path_), 52)
    assert_almost_equal(clf.alpha, 0.07, 2) # James Bond!

    # sanity check
    assert_almost_equal(clf.path_[-1].alpha, clf.alpha)
    assert_array_almost_equal(clf.path_[-1].coef_, clf.coef_)

    # test set
    X_test = np.random.randn(n_samples, n_features)
    y_test = np.dot(X_test, w)
    rmse = np.sqrt(((y_test - clf.predict(X_test)) ** 2).mean())
    assert_almost_equal(rmse, 0.35, 2)

    # check that storing the path is not mandatory and yields the same results
    clf2 = LassoPath(n_alphas=100, eps=1e-3).fit(
        X, y, maxit=maxit, store_path=False)
    assert_almost_equal(clf2.alpha, clf.alpha)
    assert_array_almost_equal(clf2.coef_, clf.coef_)
    assert_equals(clf2.path_, [])


def test_enet_path_early_stopping():

    # build an ill-posed linear regression problem with many noisy features and
    # comparatively few samples
    n_samples, n_features, maxit = 50, 200, 50
    np.random.seed(0)
    w = np.random.randn(n_features)
    w[10:] = 0.0 # only the top 10 features are impacting the model
    X = np.random.randn(n_samples, n_features)
    y = np.dot(X, w)

    clf = ElasticNetPath(n_alphas=100, eps=1e-3, rho=0.99)
    clf.fit(X, y, maxit=maxit, store_path=True)
    assert_equal(len(clf.path_), 51)
    assert_almost_equal(clf.alpha, 0.08, 2)

    # sanity check
    assert_almost_equal(clf.path_[-1].alpha, clf.alpha)
    assert_array_almost_equal(clf.path_[-1].coef_, clf.coef_)

    # test set
    X_test = np.random.randn(n_samples, n_features)
    y_test = np.dot(X_test, w)
    rmse = np.sqrt(((y_test - clf.predict(X_test)) ** 2).mean())
    assert_almost_equal(rmse, 0.36, 2)

    # check that storing the path is not mandatory and yields the same results
    clf2 = ElasticNetPath(n_alphas=100, eps=1e-3, rho=0.99)
    clf2.fit(X, y, maxit=maxit, store_path=False)
    assert_almost_equal(clf2.alpha, clf.alpha)
    assert_array_almost_equal(clf2.coef_, clf.coef_)
    assert_equals(clf2.path_, [])

# def test_lasso_path():
#     """
#     Test for the complete lasso path.
#
#     As the weigths_lasso array is quite big, we only test at the first
#     & last index.
#     """
#     n_samples, n_features, maxit = 5, 10, 30
#     np.random.seed(0)
#     Y = np.random.randn(n_samples)
#     X = np.random.randn(n_samples, n_features)
#
#     alphas_lasso, weights_lasso = lasso_path(X, Y, n_alphas = 10, tol=1e-3)
#     assert_array_almost_equal(alphas_lasso,
#                               [ 4.498, 4.363, 4.232, 4.105, 3.982,
#                               3.863, 3.747, 3.634, 3.525, 3.420],
#                               decimal=3)
#
#     assert weights_lasso.shape == (10, 10)
#
#     assert_array_almost_equal(weights_lasso[0],
#                               [0, 0, 0, 0, 0 , -0.016, 0, 0, 0, 0],
#                               decimal=3)
#
#     assert_array_almost_equal(weights_lasso[9],
#                               [-0.038, 0, 0, 0, 0, -0.148, 0, -0.095, 0, 0],
#                               decimal=3)
#
#     assert weights_lasso.shape == (10, 10)
#
#     assert_array_almost_equal(weights_lasso[0],
#                               [0, 0, 0, 0, 0 , -0.016, 0, 0, 0, 0],
#                               decimal=3)
#
#     assert_array_almost_equal(weights_lasso[9],
#                               [-0.038, 0, 0, 0, 0, -0.148, 0, -0.095, 0, 0],
#                               decimal=3)
#
# def test_enet_path():
#     n_samples, n_features, maxit = 5, 10, 30
#     np.random.seed(0)
#     Y = np.random.randn(n_samples)
#     X = np.random.randn(n_samples, n_features)
#
#     alphas_enet, weights_enet = enet_path(X, Y, n_alphas = 10, tol=1e-3)
#     assert_array_almost_equal(alphas_enet,
#                               [ 4.498, 4.363, 4.232, 4.105, 3.982,
#                               3.863, 3.747, 3.634, 3.525, 3.420],
#                               decimal=3)
#
#     assert weights_enet.shape == (10, 10)
#
#     assert_array_almost_equal(weights_enet[0],
#                               [0, 0, 0, 0, 0 , -0.016, 0, 0, 0, 0],
#                               decimal=3)
#
#     assert_array_almost_equal(weights_enet[9],
#                               [-0.028, 0, 0, 0, 0, -0.131, 0, -0.081, 0, 0],
#                               decimal=3)
