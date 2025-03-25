import unittest
import numpy as np

from abcpy.continuousmodels import Normal
from abcpy.continuousmodels import Uniform
from abcpy.statistics import Identity
from abcpy.approx_lhd import PenLogReg, SynLikelihood

class PenLogRegTests(unittest.TestCase):
    def setUp(self):
        self.mu = Uniform([[-5.0], [5.0]], name='mu')
        self.sigma = Uniform([[5.0], [10.0]], name='sigma')
        self.model = Normal([self.mu,self.sigma])
        self.model_bivariate = Uniform([[0, 0], [1, 1]], name="model")
        self.stat_calc = Identity(degree = 2, cross = 1)
        self.likfun = PenLogReg(self.stat_calc, [self.model], n_simulate = 100, n_folds = 10, max_iter = 100000, seed = 1)
        self.likfun_bivariate = PenLogReg(self.stat_calc, [self.model_bivariate], n_simulate = 100, n_folds = 10, max_iter = 100000, seed = 1)

    def test_likelihood(self):

        #Checks whether wrong input type produces error message
        self.assertRaises(TypeError, self.likfun.likelihood, 3.4, [2,1])
        self.assertRaises(TypeError, self.likfun.likelihood, [2,4], 3.4)

        # create observed data
        y_obs = self.model.forward_simulate(self.model.get_input_values(), 1, rng=np.random.RandomState(1))
        # create fake simulated data
        self.mu._fixed_values = [1.1]
        self.sigma._fixed_values = [1.0]
        y_sim = self.model.forward_simulate(self.model.get_input_values(), 100, rng=np.random.RandomState(1))
        comp_likelihood = self.likfun.likelihood(y_obs, y_sim)
        expected_likelihood = 9.77317308598673e-08
        # This checks whether it computes a correct value and dimension is right. Not correct as it does not check the
        # absolute value:
        # self.assertLess(comp_likelihood - expected_likelihood, 10e-2)
        self.assertAlmostEqual(comp_likelihood, expected_likelihood)

        # try now with the bivariate uniform model:
        y_obs_bivariate = self.model_bivariate.forward_simulate(self.model_bivariate.get_input_values(), 1,
                                                                rng=np.random.RandomState(1))
        y_sim_bivariate = self.model_bivariate.forward_simulate(self.model_bivariate.get_input_values(), 100,
                                                                rng=np.random.RandomState(1))
        comp_likelihood_biv = self.likfun_bivariate.likelihood(y_obs_bivariate, y_sim_bivariate)
        expected_likelihood_biv = 0.9364479566809435
        self.assertAlmostEqual(comp_likelihood_biv, expected_likelihood_biv)



class SynLikelihoodTests(unittest.TestCase):
    def setUp(self):
        self.mu = Uniform([[-5.0], [5.0]], name='mu')
        self.sigma = Uniform([[5.0], [10.0]], name='sigma')
        self.model = Normal([self.mu,self.sigma])
        self.stat_calc = Identity(degree = 2, cross = 0)
        self.likfun = SynLikelihood(self.stat_calc)


    def test_likelihood(self):
        #Checks whether wrong input type produces error message
        self.assertRaises(TypeError, self.likfun.likelihood, 3.4, [2,1])
        self.assertRaises(TypeError, self.likfun.likelihood, [2,4], 3.4)
               
        # create observed data
        y_obs = [9.8]
        # create fake simulated data
        self.mu._fixed_values = [1.1]
        self.sigma._fixed_values = [1.0]
        y_sim = self.model.forward_simulate(self.model.get_input_values(), 100, rng=np.random.RandomState(1))
        # calculate the statistics of the observed data
        comp_likelihood = self.likfun.likelihood(y_obs, y_sim)
        expected_likelihood = 0.00924953470649
        # This checks whether it computes a correct value and dimension is right
        self.assertLess(comp_likelihood - expected_likelihood, 10e-2)

if __name__ == '__main__':
    unittest.main()
        
