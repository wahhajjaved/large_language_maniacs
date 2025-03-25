# Richard Darst, May 2009
# David M. Creswick, Sept 2009

import math
import numpy as np

def cartesianproduct(*args):
    """Cartesian product of iteratables given as arguments.

    This implementation thanks to MrGreen.
    """
    if len(args) == 0:
        yield ()
    else:
        for x in args[0]:
            for xs in cartesianproduct(*args[1:]):
                yield (x,) + xs

def chooseNEnumerate(objs, number=1):
    """Iterator over all posibilities of choosing `number` of `objs`

    This *exhaustively lists* all options, not providing overall
    statistics.
    """
    # by Richard Darst
    if number == 0:
        yield ()
        return

    for i, obj in enumerate(objs):
        otherobjs = objs[:i] + objs[i+1:]
        #print " current", obj, otherobjs
        for conditional_selections in chooseNEnumerate(otherobjs, number-1):
            #print " others", conditional_selections
            yield ( obj, ) + conditional_selections



class Averager(object):
    """Numerically Stable Averager

    Calculate averages and standard deviations in a numerically stable way.

    From the 'On-Line Algorithm' from
    http://en.wikipedia.org/wiki/Algorithms_for_calculating_variance
    """
    def __init__(self):
        self.n       = 0
        self._mean    = 0.   # mean
        self._M2     = 0.   # variance accumulator
        #self._var_n  = 0.
        #self._var_n1 = 0.
    def add(self, value):
        """Add a new number to the dataset.
        """
        n = self.n + 1
        delta = value - self._mean
        mean = self._mean + delta/n
        M2 = self._M2 + delta*(value - mean)
        self.n = n
        self._mean = mean
        self._M2 = M2

    @property
    def mean(self):
        """Mean"""
        return self._mean
    @property
    def std(self):
        """Population Variance"""
        if self.n == 0: return float('nan')
        return math.sqrt(self._M2 / self.n)
    @property
    def stdsample(self):
        """Sample Variance"""
        if self.n <= 1: return float('nan')
        return math.sqrt(self._M2 / (self.n-1))
    @property
    def var(self):
        """Population Standard Deviation"""
        if self.n == 0: return float('nan')
        return self._M2 / self.n
    @property
    def varsample(self):
        """Sample Standard Deviation"""
        if self.n <= 1: return float('nan')
        return self._M2 / (self.n-1)

def extended_euclidean_algorithm(a, b):
    """given integers a and b , I return the tuple (x, y, gcd(a,b))
    such that x*a + y*b = gcd(a,b)

    Generally speaking, the algorithm should work over any principal
    ideal domain, so you can probably pass any pair of python object
    that act like members of a principal ideal domain.


    Proof of correctness:
    The division algorithm asserts existence of integers q and r so
    that 0 <= r < b and
    
    (1)  a = q*b + r.
    
    If r == 0, then b divides a exactly, thus b is the gcd of a and
    b. Obviously x=0 and y=1. This handles the base case for the
    induction argument. So now assume r != 0 and run the extended
    euclidean algorithm on b and r to find integers x' and y' such
    that

    (2) x'*b + y'*r = gcd(b,r).

    The recursive application of the euclidean algorithm will
    eventually terminate becase 0 <= r < b, so at every iteration it
    is being applied to a pair of numbers that are strictly smaller
    than before.  Multiply eqn (1) by y' and substitute into (2) for
    y'*r to get

    y'*a + (x' - y'*q)*b = gcd(b,r).

    Due to eqn (1), gcd(b,r) = gcd(a,b). So the coefficients are
    x = y' and y = x' - y'*q.

    """
    q, r = divmod(a,b)
    if r == 0:
        return 0, 1, b
    else:
        x, y, gcd = extended_euclidean_algorithm(b, r)
        return y, (x-y*q), gcd

def gcd(a, b):
    '''finds greatest common denominator of a and b
    '''
    _, _, gcd = extended_euclidean_algorithm(a,b)
    return gcd

def product(seq):
    it = iter(seq)
    x = it.next()
    for y in it:
        x *= y
    return x

def chinese_remainder_algorithm(congruences):
    """Chinese remainder algorithm

    Given a list of (n_i, a_i) tuples where the n_i are all pairwise
    coprime, this function finds an integer x such that x mod n_i =
    a_i for all n_i, a_i in the list of congruences.

    eg, chinese_remainder_algorithm([(3,2),(4,3),(5,1)]) returns 11
    because 11 mod 3 is 2, 11 mod 4 is 3, and 11 mod 5 is 1

    Proof of correctness:
    If you have a collection of integers e_i that have the property that
    e_i mod n_j = 0 for i != j and e_i mod n_j = 1 for i = j, then
    (a_1*e_1 + a_2*e_2 + ... + a_k*e_k) mod n_i = a_i for all i.
    So the mystery number x is (a_1*e_1 + a_2*e_2 + ... + a_k*e_k).
    Now we just have to construct e_i that have those properties.
    Define N = n_1*n_2*...*n_k. Then N is divisible by n_i and N/n_i
    is relatively prime to n_i (because remember n_i is relatively
    prime to n_j for all i != j). The Euclidean algorithm can be
    used to find integers x and y so that x*n_i + y*N/n_i = 1. From
    this equation, you can tell that (y*N/n_i) mod n_i = 1. Since N/n_i
    has every n_j as a factor except n_i, (y*N/n_i) mod n_j = 0 for j != 1.
    We have found the e_i we needed, specifically, e_i = y*N/n_i.

    """
    N = product([n for n,_ in congruences])
    c = 0
    for n,a in congruences:
        _, y, gcd = extended_euclidean_algorithm(n, N/n)
        assert gcd == 1
        e = y*N/n
        c += a*e
    return c % N


def fact(x):
    """return the factorial of x"""
    return (1 if x==0 else x * fact(x-1))


def perm(l):
    """Generate all permuations of a list"""
    sz = len(l)
    if sz <= 1:
        return [l]
    return [p[:i]+[l[0]]+p[i:] for i in xrange(sz) for p in perm(l[1:])]


def geometric_dist(lower, upper, n):
    """Return 'n' numbers distributed geometrically between
    lower and upper.
    """
    const = 1.0/float(n-1.0)*np.log(float(upper)/float(lower))
    temps = np.zeros(n,dtype=float)
    for i in xrange(n): temps[i] = lower*np.exp(i*const)

    return temps


def nball_random_surface_point(ndims, radius=1.):
    """
    Uniformly randomly generate a point on the surface of the
    n-ball.

    """
    x = np.random.randn(ndims)
    r = np.sqrt((x**2.).sum())
    s = 1./r * x

    return radius * s
