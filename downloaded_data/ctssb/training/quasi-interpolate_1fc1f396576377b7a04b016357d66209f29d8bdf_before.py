# This program calculates the quasi interpolate as defined in the book
# MATHEMATICS OF APPROXIMATION by Johan de Villiers

# Copyright (C) 2013  Tjaart van der Walt

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import math
from sage.all import *

# From equation 10.4.31 on page 328
def quasi_interpolate(m, r, t):
  return_value = 0
  # Remember python range function is upper bound exclusive... so we need the extra + 1
  for j in range(-m, r + 1):
    innersum = 0
    for k in range(j, j + m + 1):
      innersum += alpha(m, j, k)*f(k, t)
      
    return_value += innersum * n(m, j, x)
  return return_value

# From equation 10.4.32 on page 329
def alpha(m, j, k, t):
  alpha_sum = 0
  for l in range(0, m + 1):
    # Derive the lagrange l times
    derived_lagrange = lagrange(m, j, k, t)
    for q in range(0, l):
      derived_lagrange = derivative(derived_lagrange)
    
    # Derive g m-l times
    derived_g = g(m, j, t)
    for q in range(0, m - l):
      derived_g = derivative(derived_g)
    
    alpha_sum += ((-1)**l)*derived_lagrange.subs(x=0)*derived_g.subs(x=0)
  return 1.0/math.factorial(m) * alpha_sum

# From equation 10.4.28 on page 328
def lagrange(m, j, k, t):
  x = var('x')
  res = 1
  for l in (remove_value_from_list(k, range(j, (j + m) + 1))):
    res = res * (x - t[l])/(t[k] - t[l])
  return res 

# From equation 10.4.3 on page 322
def g(m, j, t):
  res = 1
  x = var('x')
  for k in range(1, m + 1):
    res = res * (x - t[j + k])
  return res

def f(k, t):
  pass

# The value for the B-spline
# From equation 10.2.32 page 299 
def b_spline(m, j, x, t):
  summation = 0
  for k in range(j, (j + m + 1) + 1):
    prod = 1
    for l in (remove_value_from_list(k, range(j, (j + m + 1) + 1))):
      prod = prod * (t[l] - t[k])
    summation += (1/prod) * truncated_power(x, t[k], m)
  return (t[j + m + 1] - t[j]) * summation

# If the value of the function of form f=(x - tk)^m is positive 
# evaluate the function, otherwise its 0
# From equation 10.1.13 page 289
def truncated_power(x, tk, m):
  if(x - tk >= 0):
    return (x - tk)**m
  else:
    return 0

# Helper function. Removes all occurences of a given value from the given list
def remove_value_from_list(k, rem_list):
  while(k in rem_list):
    ki = rem_list.index(k)
    del rem_list[ki]
  return rem_list
