
# Author: Mathieu Blondel <mathieu@mblondel.org>
# License: BSD Style.

import numpy as np

from .base import BaseEstimator, ClassifierMixin
from .preprocessing import LabelEncoder
from .utils import check_random_state
from .utils.validation import safe_asarray


class RandomClassifier(BaseEstimator, ClassifierMixin):
    """
    RandomClassifier is a dummy classifier that makes predictions randomly.

    This classifier is useful as a simple baseline to compare with other
    (real) classifiers.

    Parameters
    ----------
    sampling: str
        Strategy to use to generate predictions.
            * "stratified": generates predictions by respecting the training
              set's class distribution.
            * "most_frequent": always predict the most frequent label in the
              training set (useful for binary classification).
            * "uniform": generates predictions uniformly at random.

    random_state: int seed, RandomState instance, or None (default)
        The seed of the pseudo random number generator to use.

    Attributes
    ----------
    `label_encoder_` : LabelEncoder object
        LabelEncoder used internally.

    `class_prior_` : array, shape = [n_classes]
        Probability of each class.

    """

    def __init__(self, sampling="stratified", random_state=None):
        self.sampling = sampling
        self.random_state = random_state

    def fit(self, X, y):
        """Fit the random classifier.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = [n_samples, n_features]
            Training vectors, where n_samples is the number of samples
            and n_features is the number of features.

        y : array-like, shape = [n_samples]
            Target values.

        Returns
        -------
        self : object
            Returns self.
        """
        self.label_encoder_ = LabelEncoder()
        y = self.label_encoder_.fit_transform(y)
        self.class_prior_ = np.bincount(y) / float(y.shape[0])
        return self

    def predict(self, X):
        """
        Perform classification on test vectors X.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape = [n_samples, n_features]
            Input vectors, where n_samples is the number of samples
            and n_features is the number of features.

        Returns
        -------
        y : array, shape = [n_samples]
            Predicted target values for X.
        """
        X = safe_asarray(X)
        n_samples = X.shape[0]
        rs = check_random_state(self.random_state)

        if self.sampling == "most_frequent":
            ret = np.ones(n_samples, dtype=int) * self.class_prior_.argmax()
        elif self.sampling == "stratified":
            ret = rs.multinomial(1, self.class_prior_,
                                 size=n_samples).argmax(axis=1)
        elif self.sampling == "uniform":
            ret = rs.randint(len(self.class_prior_), size=n_samples)
        else:
            raise ValueError("Unknown sampling type.")

        return self.label_encoder_.inverse_transform(ret)
