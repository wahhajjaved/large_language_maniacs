import numpy as np
import nbinom as nb
from scipy.stats import binom, nbinom


# since we are using calculations based off of the minor allele frequency, we
# have to use a truncated binomial instead of the traditional one. In order to
# adjust for this we normalize the data based off of this. The maximum possible
# value in our case will be (0.5 * x) and the minimum possible value is 1
def truncated_binom_pmf(x, n, p):
    if n < 1:
        return 0
    else:
        return binom.pmf(x, n, p) / (binom.cdf(n/2, n, p) - binom.pmf(0, n, p))


# calculates the likelihood of each value in the joint distribution x given an
# underlying negative binomial distribution distribution for reads and a
# conditional truncated binomial distribution for the minor allele
def compound_nb_binom_pmf(x, p, r, p_nb):
    lh_nb = nbinom.pmf(x[:,1], r, p_nb)
    lh_b = np.ones_like(x[:,0])
    for i in range(len(lh_b)):
        lh_b[i] = lh_nb[i] * truncated_binom_pmf(x[i,0], x[i,1], p)
    return lh_nb * lh_b


# calculates a matrix of the binom_mix for a vector of p values
def get_Likelihood(x, p, r, p_nb):
    # likelihood of p
    lh = np.ones((len(p), len(x)))
    for i in range(len(p)):
        lh[i] = compound_nb_binom_pmf(x, p[i], r, p_nb)
    return lh


# uses expectation maximization to get the weights of each subpopulation
# model given a set of fixed distributions. Calculates the weights from
# likelihood data
def get_Weights(lh):
    return np.sum(lh, axis=1) / np.sum(lh)
