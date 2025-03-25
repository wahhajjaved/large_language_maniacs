#! /usr/bin/env python

#
# stats
#
# A collection of statistics utilities
#

def wilson_score(p, n, z=1.):
  '''Calculate the Wilson score interval to estimate the uncertainty on the
  estimate of the frequency of an event with a binomial distribution.

  Inputs:
    p -- The estimated probability
    n -- The number of data points
    z -- The percentile of the standard normal distribution 
          (i.e., the number of sigmas)
  
  Outputs:
    A tuple which contains the lower and upper bounds.
  '''
  from math import sqrt

  discriminant = z * sqrt(p / n * (1 - p) + z**2 / (4 * n**2))

  low_bound = 1 / (1 + z**2 / n) * (p + z**2 / (2 * n) - discriminant)
  up_bound = 1 / (1 + z**2 / n) * (p + z**2 / (2 * n) + discriminant)

  return (low_bound, up_bound)
