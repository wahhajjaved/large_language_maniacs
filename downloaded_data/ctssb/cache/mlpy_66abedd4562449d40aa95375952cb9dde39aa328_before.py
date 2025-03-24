# SYSTEM IMPORTS
import numpy
import os
import sys


_cd_ = os.path.abspath(os.path.dirname(__file__))
_net_dir_ = os.path.join(_cd_, "..")
# _src_dir_ = os.path.join(_cd_, "..", "..")
for _dir_ in [_cd_, _net_dir_]: # , _src_dir_]:
    if _dir_ not in sys.path:
        sys.path.append(_dir_)
# del _src_dir_
del _net_dir_
del _cd_


# PYTHON PROJECT IMPORTS
import activations as af
import ann


class skipgram(ann.ann):
    def __init__(self, vocab_size, context_size, num_embedding_dims, learning_rate=1.0):
        super(skipgram, self).__init__([vocab_size, num_embedding_dims, vocab_size],
                                       afuncs=[af.linear, af.softmax],
                                       afunc_primes=[af.linear_prime, af.softmax_prime],
                                       learning_rate=learning_rate, weight_decay_coeff=0.0)
        self.context_size = context_size
        self.vocab_size = vocab_size
        self.biases = [numpy.zeros(b.shape) for b in self.biases]

    def sum_context(self, X):
        return numpy.sum([X[:, i*self.vocab_size:(i+1)*self.vocab_size]
                         for i in range(self.context_size)], axis=0)

    def expand_context(self, y):
        return numpy.tile(y, self.context_size)

    def cost_function(self, X, y):
        _, as_ = self.complete_feed_forward(X)
        return -numpy.sum(numpy.log(numpy.sum(numpy.where(y==1, as_[-1], 0), axis=1)))

    def feed_forward(self, X):
        y = super(skipgram, self).feed_forward(X)
        return self.expand_context(y)

    def complete_feed_forward(self, X):
        zs = list()
        as_ = list([X])
        a = X
        z = None
        for afunc, weight in zip(self.afuncs, self.weights):
            z = numpy.dot(a, weight)
            zs.append(z)
            a = afunc(z)
            as_.append(a)

        as_[-1] = self.expand_context(as_[-1])
        return zs, as_

    def compute_error(self, Y_hat, Y):
        # skipgram predicts the context words, which means that out output has different
        # dimensions than the weights, and different shapes than the error vector

        # Y_hat and Y have shape (num_examples, self.vocab_size * self.context_size)
        # while the error vector needs to have shape (num_examples, self.vocab_size)

        # so, we will compute the difference between the error vectors, and sum them together
        return self.sum_context(Y_hat - Y)

    def _predict_example(self, x):
        return self.weights[0][x == 1]

