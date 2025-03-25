import cPickle
import numpy as np
import tensorflow as tf

from disc_learning import TFNoiseAwareModel
from scipy.sparse import issparse
from time import time
from utils import LabelBalancer


class LogisticRegression(TFNoiseAwareModel):

    def __init__(self, save_file=None, name='LR'):
        """Noise-aware logistic regression in TensorFlow"""
        self.d          = None
        self.X          = None
        self.lr         = None
        self.l1_penalty = None
        self.l2_penalty = None
        self.nnz        = None
        super(LogisticRegression, self).__init__(save_file=save_file, name=name)

    def _build(self):
        # Define inputs and variables
        self.X = tf.placeholder(tf.float32, (None, self.d))
        self.Y = tf.placeholder(tf.float32, (None, 1))
        w = tf.Variable(tf.random_normal((self.d, 1), mean=0, stddev=0.01))
        b = tf.Variable(tf.random_normal((1, 1), mean=0, stddev=0.01))
        h = tf.add(tf.matmul(self.X, w), b)
        # Build model
        self.loss = tf.reduce_sum(
            tf.nn.sigmoid_cross_entropy_with_logits(h, self.Y)
        )
        self.train_fn = tf.train.ProximalGradientDescentOptimizer(
            learning_rate=tf.cast(self.lr, dtype=tf.float32),
            l1_regularization_strength=tf.cast(self.l1_penalty, tf.float32),
            l2_regularization_strength=tf.cast(self.l2_penalty, tf.float32),
        ).minimize(self.loss)
        self.prediction = tf.nn.sigmoid(h)
        self.save_dict = {'w': w, 'b': b}
        # Get nnz operation
        self.nnz = tf.reduce_sum(tf.cast(
            tf.not_equal(w, tf.constant(0, tf.float32)), tf.int32
        ))

    def _check_input(self, X):
        if issparse(X):
            raise Exception("Sparse input matrix. Use SparseLogisticRegression")
        return X

    def _run_batch(self, X_train, y_train, i, r):
        """Run a single batch update"""
        # Get batch tensors
        sparse  = issparse(X_train)
        x_batch = X_train[i:r, :].todense() if sparse else X_train[i:r, :]
        y_batch = y_train[i:r].reshape((r-i, 1))
        # Run training step and evaluate loss function                  
        return self.session.run([self.loss, self.train_fn, self.nnz], {
            self.X: x_batch, self.Y: y_batch,
        })

    def train(self, X, training_marginals, n_epochs=10, lr=0.01,
        batch_size=100, l1_penalty=0.0, l2_penalty=0.0, print_freq=5,
        rebalance=False):
        """Train elastic net logistic regression model using TensorFlow
            @X: SciPy or NumPy feature matrix
            @training_marginals: array of marginals for examples in X
            @n_epochs: number of training epochs
            @lr: learning rate
            @batch_size: batch size for mini-batch SGD
            @l1_penalty: l1 regularization strength
            @l2_penalty: l2 regularization strength
            @print_freq: number of epochs after which to print status
            @rebalance: bool or fraction of positive examples desired
                        If True, defaults to standard 0.5 class balance.
                        If False, no class balancing.
        """
        # Build model
        X = self._check_input(X)
        verbose = print_freq > 0
        if verbose:
            print("[{0}] lr={1} l1={2} l2={3}".format(
                self.name, lr, l1_penalty, l2_penalty
            ))
            print("[{0}] Building model".format(self.name))
        self.d          = X.shape[1]
        self.lr         = lr
        self.l1_penalty = l1_penalty
        self.l2_penalty = l2_penalty
        self._build()
        # Get training indices
        train_idxs = LabelBalancer(training_marginals).get_train_idxs(rebalance)
        X_train = X[train_idxs, :]
        y_train = np.ravel(training_marginals)[train_idxs]
        # Run mini-batch SGD
        n = X_train.shape[0]
        batch_size = min(batch_size, n)
        if verbose:
            st = time()
            print("[{0}] Training model".format(self.name))
            print("[{0}] #examples={1}  #epochs={2}  batch size={3}".format(
                self.name, n, n_epochs, batch_size
            ))
        self.session.run(tf.global_variables_initializer())
        for t in xrange(n_epochs):
            epoch_loss = 0.0
            for i in range(0, n, batch_size):
                r = min(n-1, i+batch_size)
                loss, _, nnz = self._run_batch(X_train, y_train, i, r)
                epoch_loss += loss
            # Print training stats
            if verbose and (t % print_freq == 0 or t in [0, (n_epochs-1)]):
                msg = "[{0}] Epoch {1} ({2:.2f}s)\tAvg. loss={3:.6f}\tNNZ={4}"
                print(msg.format(self.name, t, time()-st, epoch_loss/n, nnz))
        if verbose:
            print("[{0}] Training done ({1:.2f}s)".format(self.name, time()-st))

    def marginals(self, X_test):
        X_test = self._check_input(X_test)
        return np.ravel(self.session.run([self.prediction], {self.X: X}))

    def save_info(self, model_name):
        with open('{0}.info'.format(model_name), 'wb') as f:
            cPickle.dump((self.d, self.lr, self.l1_penalty, self.l2_penalty), f)

    def load_info(self, model_name):
        with open('{0}.info'.format(model_name), 'rb') as f:
            self.d, self.lr, self.l1_penalty, self.l2_penalty = cPickle.load(f)


class SparseLogisticRegression(LogisticRegression):

    def __init__(self, save_file=None, name='SparseLR'):
        """Sparse noise-aware logistic regression in TensorFlow"""
        self.indices = None
        self.shape   = None
        self.ids     = None
        self.weights = None
        super(SparseLogisticRegression, self).__init__(
            save_file=save_file, name=name
        )

    def _build(self):
        # Define input placeholders
        self.indices = tf.placeholder(tf.int64) 
        self.shape   = tf.placeholder(tf.int64, (2,))
        self.ids     = tf.placeholder(tf.int64)
        self.weights = tf.placeholder(tf.float32)
        self.Y       = tf.placeholder(tf.float32, (None, 1))
        # Define training variables
        sparse_ids = tf.SparseTensor(self.indices, self.ids, self.shape)
        sparse_vals = tf.SparseTensor(self.indices, self.weights, self.shape)
        w = tf.Variable(tf.random_normal((self.d, 1), mean=0, stddev=0.01))
        b = tf.Variable(tf.random_normal((1, 1), mean=0, stddev=0.01))
        z = tf.nn.embedding_lookup_sparse(
            params=w, sp_ids=sparse_ids, sp_weights=sparse_vals, combiner='sum'
        )
        h = tf.add(z, b)
        # Build model
        self.loss = tf.reduce_sum(
            tf.nn.sigmoid_cross_entropy_with_logits(h, self.Y)
        )
        self.train_fn = tf.train.ProximalGradientDescentOptimizer(
            learning_rate=tf.cast(self.lr, dtype=tf.float32),
            l1_regularization_strength=tf.cast(self.l1_penalty, tf.float32),
            l2_regularization_strength=tf.cast(self.l2_penalty, tf.float32),
        ).minimize(self.loss)
        self.prediction = tf.nn.sigmoid(h)
        self.save_dict = {'w': w, 'b': b}
        # Get nnz operation
        self.nnz = tf.reduce_sum(tf.cast(
            tf.not_equal(w, tf.constant(0, tf.float32)), tf.int32
        ))

    def _check_input(self, X):
        if not issparse(X):
            msg = "Dense input matrix. Cast to sparse or use LogisticRegression"
            raise Exception(msg)
        return X.tocsr()

    def _batch_sparse_data(self, X):
        """Convert sparse batch matrix to sparse inputs for embedding lookup"""
        if not issparse(X):
            raise Exception("Matrix X must be scipy.sparse type")
        X_lil = X.tolil()
        indices, ids, weights = [], [], []
        max_len = 0
        for i, (row, data) in enumerate(zip(X_lil.rows, X_lil.data)):
            max_len = max(max_len, len(row))
            indices.extend((i, t) for t in xrange(len(row)))
            ids.extend(row)
            weights.extend(data)
        shape = (len(X_lil.rows), max_len)
        return indices, shape, ids, weights

    def _run_batch(self, X_train, y_train, i, r):
        """Run a single batch update"""
        # Get batch sparse tensor data
        indices, shape, ids, weights = self._batch_sparse_data(X_train[i:r, :])
        y_batch = y_train[i:r].reshape((r-i, 1))
        # Run training step and evaluate loss function                  
        return self.session.run([self.loss, self.train_fn, self.nnz], {
            self.indices: indices,
            self.shape:   shape,
            self.ids:     ids,
            self.weights: weights,
            self.Y:       y_batch,
        })

    def marginals(self, X_test):
        X_test = self._check_input(X_test)
        if X_test.shape[0] == 0:
            return np.ravel([])
        indices, shape, ids, weights = self._batch_sparse_data(X_test)
        return np.ravel(self.session.run([self.prediction], {
            self.indices: indices,
            self.shape:   shape,
            self.ids:     ids,
            self.weights: weights,
        }))
