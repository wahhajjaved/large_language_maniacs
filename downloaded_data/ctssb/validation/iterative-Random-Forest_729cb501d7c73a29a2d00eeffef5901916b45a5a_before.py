"""
This module gathers tree-based methods, including decision, regression and
randomized trees.
"""

# Code is originally adapted from MILK: Machine Learning Toolkit
# Copyright (C) 2008-2011, Luis Pedro Coelho <luis@luispedro.org>
# License: MIT. See COPYING.MIT file in the milk distribution

# Authors: Brian Holt, Peter Prettenhofer, Satrajit Ghosh, Gilles Louppe
# License: BSD3

from __future__ import division
import numpy as np

from ..base import BaseEstimator, ClassifierMixin, RegressorMixin
from ..utils import array2d, check_random_state

from . import _tree

__all__ = [
    "DecisionTreeClassifier",
    "DecisionTreeRegressor"
]

DTYPE = _tree.DTYPE

CLASSIFICATION = {
    "gini": _tree.Gini,
    "entropy": _tree.Entropy,
}

REGRESSION = {
    "mse": _tree.MSE,
}

GRAPHVIZ_TREE_TEMPLATE = """\
%(current)s [label="%(current_gv)s"] ;
%(left_child)s [label="%(left_child_gv)s"] ;
%(right_child)s [label="%(right_child_gv)s"] ;
%(current)s -> %(left_child)s ;
%(current)s -> %(right_child)s ;
"""


def export_graphviz(decision_tree, out_file=None, feature_names=None):
    """Export a decision tree in DOT format.

    This function generates a GraphViz representation of the decision tree,
    which is then written into `out_file`. Once exported, graphical renderings
    can be generated using, for example,::

        $ dot -Tps tree.dot -o tree.ps      (PostScript format)
        $ dot -Tpng tree.dot -o tree.png    (PNG format)

    Parameters
    ----------
    decision_tree : decision tree classifier
        The decision tree to be exported to graphviz.

    out : file object or string, optional (default=None)
        Handle or name of the output file.

    feature_names : list of strings, optional (default=None)
        Names of each of the features.

    Returns
    -------
    out_file : file object
        The file object to which the tree was exported.  The user is
        expected to `close()` this object when done with it.

    Examples
    --------
    >>> from sklearn.datasets import load_iris
    >>> from sklearn import tree

    >>> clf = tree.DecisionTreeClassifier()
    >>> iris = load_iris()

    >>> clf = clf.fit(iris.data, iris.target)
    >>> import tempfile
    >>> out_file = export_graphviz(clf, out_file=tempfile.TemporaryFile())
    >>> out_file.close()
    """
    def node_to_str(node):
        if node.is_leaf:
            return "error = %s\\nsamples = %s\\nvalue = %s" \
                % (node.error, node.samples, node.value)
        else:
            if feature_names is not None:
                feature = feature_names[node.feature]
            else:
                feature = "X[%s]" % node.feature

            return "%s <= %s\\nerror = %s\\nsamples = %s\\nvalue = %s" \
                   % (feature, node.threshold,
                      node.error, node.samples, node.value)

    def recurse(node, count):
        node_data = {
            "current": count,
            "current_gv": node_to_str(node),
            "left_child": 2 * count + 1,
            "left_child_gv": node_to_str(node.left),
            "right_child": 2 * count + 2,
            "right_child_gv": node_to_str(node.right),
        }

        out_file.write(GRAPHVIZ_TREE_TEMPLATE % node_data)

        if not node.left.is_leaf:
            recurse(node.left, 2 * count + 1)
        if not node.right.is_leaf:
            recurse(node.right, 2 * count + 2)

    if out_file is None:
        out_file = open("tree.dot", 'w')
    elif isinstance(out_file, basestring):
        out_file = open(out_file, 'w')

    out_file.write("digraph Tree {\n")
    recurse(decision_tree.tree, 0)
    out_file.write("}")

    return out_file


class Tree(object):

    def __init__(self, k, capacity=3):
        self.node_count = 0

        self.left = np.empty((capacity,), dtype=np.int64)
        self.left.fill(-1)

        self.right = np.empty((capacity,), dtype=np.int64)
        self.right.fill(-1)

        self.feature = np.empty((capacity,), dtype=np.int32)
        self.feature.fill(-1)

        self.threshold = np.empty((capacity,), dtype=np.float64)
        self.value = np.zeros((capacity, k), dtype=np.float64)

        self.best_error = np.empty((capacity,), dtype=np.float64)
        self.init_error = np.empty((capacity,), dtype=np.float64)
        self.n_samples = np.empty((capacity,), dtype=np.int64)

    def resize(self, capacity=None):
        """Resize tree arrays to `capacity`, if `None` double capacity."""
        if capacity is None:
            # double old capacity  FIXME this will break if too large
            capacity = int(self.left.shape[0] * 2.0)

        if capacity == self.left.shape[0]:
            return
        print("Resizing tree to %d" % capacity)

        self.left.resize((capacity,), refcheck=False)
        self.right.resize((capacity,), refcheck=False)
        self.feature.resize((capacity,), refcheck=False)
        self.threshold.resize((capacity,), refcheck=False)
        self.value.resize((capacity, self.value.shape[1]), refcheck=False)
        self.best_error.resize((capacity,), refcheck=False)
        self.init_error.resize((capacity,), refcheck=False)
        self.n_samples.resize((capacity,), refcheck=False)

    def add_split_node(self, parent, left_child, feature, threshold,
                       init_error, n_samples):
        """Add a splitting node to the tree."""
        node_id = self.node_count
        if node_id >= self.left.shape[0]:
            self.resize()

        self.feature[node_id] = feature
        self.threshold[node_id] = threshold

        self.init_error[node_id] = init_error
        self.best_error[node_id] = init_error
        self.n_samples[node_id] = n_samples

        # set as left or right child of parent
        if parent > -1:
            if left_child:
                self.left[parent] = node_id
            else:
                self.right[parent] = node_id

        self.node_count += 1
        return node_id

    def add_leaf(self, parent, left_child, value, n_samples):
        """Add a leaf to the tree."""
        node_id = self.node_count
        if node_id >= self.left.shape[0]:
            self.resize()

        self.value[node_id] = value
        self.n_samples[node_id] = n_samples

        if left_child:
            self.left[parent] = node_id
        else:
            self.right[parent] = node_id

        self.left[node_id] = -1
        self.right[node_id] = -1

        self.node_count += 1

    def predict(self, X):
        out = np.empty((X.shape[0], ), dtype=np.int64)
        _tree.apply_tree(X, self.left, self.right, self.feature,
                         self.threshold, out)
        return self.value.take(out, axis=0)


def _build_tree(X, y, is_classification, criterion, max_depth, min_split,
                min_density, max_features, random_state, n_classes, find_split,
                sample_mask=None, X_argsorted=None):
    """Build a tree by recursively partitioning the data."""

    if max_depth <= 10:
        init_capacity = (2 ** (max_depth + 1)) - 1
    else:
        init_capacity = 2047  # num nodes of tree with depth 10

    tree = Tree(n_classes, init_capacity)

    # Recursively partition X
    def recursive_partition(X, X_argsorted, y, sample_mask, depth,
                            parent, is_left_child):
        # Count samples
        n_node_samples = sample_mask.sum()

        if n_node_samples == 0:
            raise ValueError("Attempting to find a split "
                             "with an empty sample_mask")

        # Split samples
        if depth < max_depth and n_node_samples >= min_split:
            feature, threshold, init_error = find_split(X,
                                                        y,
                                                        X_argsorted,
                                                        sample_mask,
                                                        n_node_samples,
                                                        max_features,
                                                        criterion,
                                                        random_state)

        else:
            feature = -1

        # Value at this node
        current_y = y[sample_mask]

        if is_classification:
            value = np.zeros((n_classes,))
            t = current_y.max() + 1
            value[:t] = np.bincount(current_y.astype(np.int))

        else:
            value = np.asarray(np.mean(current_y))

        # Terminal node
        if feature == -1:
            tree.add_leaf(parent, is_left_child, value, n_node_samples)

        # Internal node
        else:
            # Sample mask is too sparse?
            if n_node_samples / X.shape[0] <= min_density:
                X = X[sample_mask]
                X_argsorted = np.asfortranarray(
                    np.argsort(X.T, axis=1).astype(np.int32).T)
                y = current_y
                sample_mask = np.ones((X.shape[0],), dtype=np.bool)

            # Split and and recurse
            split = X[:, feature] <= threshold

            node_id = tree.add_split_node(parent, is_left_child, feature,
                                          threshold, init_error,
                                          n_node_samples)

            # left child recursion
            recursive_partition(X, X_argsorted, y,
                                split & sample_mask,
                                depth + 1, node_id, True)

            # right child recursion
            recursive_partition(X, X_argsorted, y,
                                ~split & sample_mask,
                                depth + 1, node_id, False)

    # Launch the construction
    if X.dtype != DTYPE or not np.isfortran(X):
        X = np.asanyarray(X, dtype=DTYPE, order="F")

    if y.dtype != DTYPE or not y.flags.contiguous:
        y = np.ascontiguousarray(y, dtype=DTYPE)

    if sample_mask is None:
        sample_mask = np.ones((X.shape[0],), dtype=np.bool)

    if X_argsorted is None:
        X_argsorted = np.asfortranarray(
            np.argsort(X.T, axis=1).astype(np.int32).T)

    recursive_partition(X, X_argsorted, y, sample_mask, 0, -1, False)

    tree.resize(tree.node_count)
    return tree


class BaseDecisionTree(BaseEstimator):
    """Base class for decision trees.

    Warning: This class should not be used directly. Use derived classes instead.
    """
    def __init__(self, criterion,
                       max_depth,
                       min_split,
                       min_density,
                       max_features,
                       random_state):
        self.criterion = criterion
        self.max_depth = np.inf if max_depth is None else max_depth
        self.min_split = min_split
        self.min_density = min_density
        self.max_features = -1 if max_features is None else max_features
        self.random_state = check_random_state(random_state)

        self.n_features = None
        self.classes = None
        self.n_classes = None
        self.find_split = _tree._find_best_split

        self.tree = None

    def fit(self, X, y):
        """Build a decision tree from the training set (X, y).

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The training input samples.

        y : array-like, shape = [n_samples]
            The target values (integers that correspond to classes in
            classification, real numbers in regression).

        Return
        ------
        self : object
            Returns self.
        """
        # Convert data
        X = np.asarray(X, dtype=DTYPE, order='F')
        n_samples, self.n_features = X.shape

        is_classification = isinstance(self, ClassifierMixin)

        if is_classification:
            self.classes = np.unique(y)
            self.n_classes = self.classes.shape[0]
            criterion = CLASSIFICATION[self.criterion](self.n_classes)
            y = np.searchsorted(self.classes, y)

        else:
            self.classes = None
            self.n_classes = 1
            criterion = REGRESSION[self.criterion]()

        y = np.ascontiguousarray(y, dtype=DTYPE)

        # Check parameters
        if len(y) != n_samples:
            raise ValueError("Number of labels=%d does not match "
                             "number of features=%d" % (len(y), n_samples))
        if self.min_split <= 0:
            raise ValueError("min_split must be greater than zero.")
        if self.max_depth is not None and self.max_depth <= 0:
            raise ValueError("max_depth must be greater than zero. ")
        if self.min_density < 0.0 or self.min_density > 1.0:
            raise ValueError("min_density must be in [0, 1]")
        if self.max_features >= 0 and not (0 < self.max_features <= self.n_features):
            raise ValueError("max_features must be in (0, n_features]")

        # Build tree
        self.tree = _build_tree(X, y, is_classification, criterion,
                                self.max_depth, self.min_split,
                                self.min_density, self.max_features,
                                self.random_state, self.n_classes,
                                self.find_split)

        return self

    def predict(self, X):
        """Predict class or regression target for X.

        For a classification model, the predicted class for each sample in X is
        returned. For a regression model, the predicted value based on X is
        returned.

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The input samples.

        Returns
        -------
        predictions : array of shape = [n_samples]
            The predicted classes, or the predict values.
        """
        X = array2d(X, dtype=DTYPE)
        n_samples, n_features = X.shape

        if self.tree is None:
            raise Exception("Tree not initialized. Perform a fit first")

        if self.n_features != n_features:
            raise ValueError("Number of features of the model must "
                             " match the input. Model n_features is %s and "
                             " input n_features is %s "
                             % (self.n_features, n_features))

        if isinstance(self, ClassifierMixin):
            predictions = self.classes[np.argmax(
                self.tree.predict(X), axis=1)]
        else:
            predictions = self.tree.predict(X).ravel()

        return predictions


class DecisionTreeClassifier(BaseDecisionTree, ClassifierMixin):
    """A decision tree classifier.

    Parameters
    ----------
    criterion : string, optional (default="gini")
        The function to measure the quality of a split. Supported criteria are
        "gini" for the Gini impurity and "entropy" for the information gain.

    max_depth : integer or None, optional (default=10)
        The maximum depth of the tree. If None, then nodes are expanded until
        all leaves are pure or until all leaves contain less than min_split
        samples.

    min_split : integer, optional (default=1)
        The minimum number of samples required to split an internal node.

    min_density : float, optional (default=0.1)
        The minimum density of the `sample_mask` (i.e. the fraction of samples
        in the mask). If the density falls below this threshold the mask is
        recomputed and the input data is packed which results in data copying.
        If `min_density` equals to one, the partitions are always represented
        as copies of the original data. Otherwise, partitions are represented
        as bit masks (aka sample masks).

    max_features : int or None, optional (default=None)
        The number of features to consider when looking for the best split.
        If None, all features are considered, otherwise max_features are chosen
        at random.

    random_state : int, RandomState instance or None, optional (default=None)
        If int, random_state is the seed used by the random number generator;
        If RandomState instance, random_state is the random number generator;
        If None, the random number generator is the RandomState instance used
        by `np.random`.

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Decision_tree_learning

    .. [2] L. Breiman, J. Friedman, R. Olshen, and C. Stone, "Classification
           and Regression Trees", Wadsworth, Belmont, CA, 1984.

    .. [3] T. Hastie, R. Tibshirani and J. Friedman. "Elements of Statistical
           Learning", Springer, 2009.

    See also
    --------
    DecisionTreeRegressor

    Examples
    --------
    >>> from sklearn.datasets import load_iris
    >>> from sklearn.cross_validation import cross_val_score
    >>> from sklearn.tree import DecisionTreeClassifier

    >>> clf = DecisionTreeClassifier(random_state=0)
    >>> iris = load_iris()

    >>> cross_val_score(clf, iris.data, iris.target, cv=10)
    ...                             # doctest: +SKIP
    ...
    array([ 1.     ,  0.93...,  0.86...,  0.93...,  0.93...,
            0.93...,  0.93...,  1.     ,  0.93...,  1.      ])
    """
    def __init__(self, criterion="gini",
                       max_depth=10,
                       min_split=1,
                       min_density=0.1,
                       max_features=None,
                       random_state=None):
        super(DecisionTreeClassifier, self).__init__(criterion,
                                                     max_depth,
                                                     min_split,
                                                     min_density,
                                                     max_features,
                                                     random_state)

    def predict_proba(self, X):
        """Predict class probabilities of the input samples X.

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The input samples.

        Returns
        -------
        p : array of shape = [n_samples, n_classes]
            The class probabilities of the input samples. Classes are ordered
            by arithmetical order.
        """
        X = array2d(X, dtype=DTYPE)
        n_samples, n_features = X.shape

        if self.tree is None:
            raise Exception("Tree not initialized. Perform a fit first.")

        if self.n_features != n_features:
            raise ValueError("Number of features of the model must "
                             " match the input. Model n_features is %s and "
                             " input n_features is %s "
                             % (self.n_features, n_features))

        P = self.tree(X)
        P /= P.sum(axis=1)[:, np.newaxis]
        return P

    def predict_log_proba(self, X):
        """Predict class log-probabilities of the input samples X.

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The input samples.

        Returns
        -------
        p : array of shape = [n_samples, n_classes]
            The class log-probabilities of the input samples. Classes are
            ordered by arithmetical order.
        """
        return np.log(self.predict_proba(X))


class DecisionTreeRegressor(BaseDecisionTree, RegressorMixin):
    """A tree regressor.

    Parameters
    ----------
    criterion : string, optional (default="mse")
        The function to measure the quality of a split. The only supported
        criterion is "mse" for the mean squared error.

    max_depth : integer or None, optional (default=10)
        The maximum depth of the tree. If None, then nodes are expanded until
        all leaves are pure or until all leaves contain less than min_split
        samples.

    min_split : integer, optional (default=1)
        The minimum number of samples required to split an internal node.

    min_density : float, optional (default=0.1)
        The minimum density of the `sample_mask` (i.e. the fraction of samples
        in the mask). If the density falls below this threshold the mask is
        recomputed and the input data is packed which results in data copying.
        If `min_density` equals to one, the partitions are always represented
        as copies of the original data. Otherwise, partitions are represented
        as bit masks (aka sample masks).

    max_features : int or None, optional (default=None)
        The number of features to consider when looking for the best split.
        If None, all features are considered, otherwise max_features are chosen
        at random.

    random_state : int, RandomState instance or None, optional (default=None)
        If int, random_state is the seed used by the random number generator;
        If RandomState instance, random_state is the random number generator;
        If None, the random number generator is the RandomState instance used
        by `np.random`.

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Decision_tree_learning

    .. [2] L. Breiman, J. Friedman, R. Olshen, and C. Stone, "Classification
           and Regression Trees", Wadsworth, Belmont, CA, 1984.

    .. [3] T. Hastie, R. Tibshirani and J. Friedman. "Elements of Statistical
           Learning", Springer, 2009.

    See also
    --------
    DecisionTreeClassifier

    Examples
    --------
    >>> from sklearn.datasets import load_boston
    >>> from sklearn.cross_validation import cross_val_score
    >>> from sklearn.tree import DecisionTreeRegressor

    >>> boston = load_boston()
    >>> regressor = DecisionTreeRegressor(random_state=0)

    R2 scores (a.k.a. coefficient of determination) over 10-folds CV:

    >>> cross_val_score(regressor, boston.data, boston.target, cv=10)
    ...                    # doctest: +SKIP
    ...
    array([ 0.61..., 0.57..., -0.34..., 0.41..., 0.75...,
            0.07..., 0.29..., 0.33..., -1.42..., -1.77...])
    """
    def __init__(self, criterion="mse",
                       max_depth=10,
                       min_split=1,
                       min_density=0.1,
                       max_features=None,
                       random_state=None):
        super(DecisionTreeRegressor, self).__init__(criterion,
                                                    max_depth,
                                                    min_split,
                                                    min_density,
                                                    max_features,
                                                    random_state)
