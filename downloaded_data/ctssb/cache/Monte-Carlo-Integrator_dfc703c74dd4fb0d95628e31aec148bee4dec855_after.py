from __future__ import print_function
import numpy as np
from scipy.stats import multivariate_normal
import time
import sys

import mcsampler_new


class test:

    def __init__(self):
        self.dim = 1
        self.k = 1
        self.weights = None
        self.means = None
        self.sampler = None
        self.args = None
        self.llim = -10
        self.rlim = 10
        self.gmm_dict = None

        self.tests_per_init = int(sys.argv[3])
        self.dim_max = int(sys.argv[1])
        self.k_max = int(sys.argv[2])
        self.results = np.zeros((self.dim_max, self.k_max))

    def initialize(self):
        # randomly generate integrand
        self.means = np.random.uniform(self.llim, self.rlim, size=(self.k, self.dim))
        self.weights = np.random.uniform(size=self.k)
        self.weights /= np.sum(self.weights)
        # initialize sampler
        self.sampler = mcsampler_new.MCSampler()
        self.args = []
        for index in range(self.dim):
            self.sampler.add_parameter(str(index), left_limit=self.llim-10, right_limit=self.rlim+10)
            self.args.append(str(index))
        self.gmm_dict = {tuple(range(self.dim)) : None}

    def func(self, samples):
        ret = 0
        for index in range(self.k):
            w = self.weights[index]
            mean = self.means[index]
            ret += w * multivariate_normal.pdf(samples, mean)
        return np.rot90([ret], -1)

    def run_tests(self):
        for self.dim in range(1, self.dim_max + 1):
            for self.k in range(1, self.k_max + 1):
                for iteration in range(self.tests_per_init):
                    self.initialize()
                    t1 = time.time()
                    integral, _, _, _ = self.sampler.integrate(self.func, args=self.args, n_comp=self.k, gmm_dict=self.gmm_dict)
                    t = time.time() - t1
                    self.results[self.dim - 1][self.k - 1] += t
        self.results /= self.tests_per_init

if __name__ == '__main__':
    print('Usage: python/python3 timed_test.py [dim_max] [k_max] [iters_per_test]')
    test = test()
    test.run_tests()
    print(test.results)
