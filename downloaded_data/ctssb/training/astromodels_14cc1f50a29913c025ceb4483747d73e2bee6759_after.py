import exceptions
import math

import astropy.units as astropy_units
import numpy as np
import warnings
from scipy.special import  erfcinv, erf

from astromodels.functions.function import Function1D, FunctionMeta, ModelAssertionViolation



# noinspection PyPep8Naming
class Gaussian(Function1D):
    r"""
    description :

        A Gaussian function

    latex : $ K \frac{1}{\sigma \sqrt{2 \pi}}\exp{\frac{(x-\mu)^2}{2~(\sigma)^2}} $

    parameters :

        F :

            desc : Integral between -inf and +inf. Fix this to 1 to obtain a Normal distribution
            initial value : 1

        mu :

            desc : Central value
            initial value : 0.0

        sigma :

            desc : standard deviation
            initial value : 1.0
            min : 1e-12

    tests :
        - { x : 0.0, function value: 0.3989422804014327, tolerance: 1e-10}
        - { x : -1.0, function value: 0.24197072451914337, tolerance: 1e-9}

    """

    __metaclass__ = FunctionMeta

    # Place this here to avoid recomputing it all the time

    __norm_const = 1.0 / (math.sqrt(2 * np.pi))

    def _set_units(self, x_unit, y_unit):

        # The normalization is the integral from -inf to +inf, i.e., has dimensions of
        # y_unit * x_unit
        self.F.unit = y_unit * x_unit

        # The mu has the same dimensions as the x
        self.mu.unit = x_unit

        # sigma has the same dimensions as x
        self.sigma.unit = x_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, F, mu, sigma):

        norm = self.__norm_const / sigma

        return F * norm * np.exp(-np.power(x - mu, 2.) / (2 * np.power(sigma, 2.)))

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        mu = self.mu.value
        sigma = self.sigma.value

        sqrt_two = 1.414213562

        if x < 1e-16 or (1 - x) < 1e-16:

            res = -1e32

        else:

            res = mu + sigma * sqrt_two * erfcinv(2 * (1 - x))

        return res

class Truncated_gaussian(Function1D):
    r"""
    description :

        A  truncated Gaussian function defined on the interval between the lower_bound (a) and upper_bound (b)

    latex : $\begin{split}f(x;\mu,\sigma,a,b)=\frac{\frac{1}{\sigma} \phi\left( \frac{x-\mu}{\sigma} \right)}{\Phi\left( \frac{b-\mu}{\sigma} \right) - \Phi\left( \frac{a-\mu}{\sigma} \right)}\\\phi\left(z\right)=\frac{1}{\sqrt{2 \pi}}\exp\left(-\frac{1}{2}z^2\right)\\\Phi\left(z\right)=\frac{1}{2}\left(1+erf\left(\frac{z}{\sqrt(2)}\right)\right)\end{split}$

    parameters :

        F :

            desc : Integral between -inf and +inf. Fix this to 1 to obtain a Normal distribution
            initial value : 1

        mu :

            desc : Central value
            initial value : 0.0

        sigma :

            desc : standard deviation
            initial value : 1.0
            min : 1e-12

        lower_bound :

            desc: lower bound of gaussian, setting to -np.inf results in half normal distribution
            initial value : -1.

        upper_bound :

            desc: upper bound of gaussian  setting to np.inf results in half normal distribution
            initial value : 1.


    tests :
        - { x : 0.0, function value: 0.3989422804014327, tolerance: 1e-10}
        - { x : -1.0, function value: 0.24197072451914337, tolerance: 1e-9}

    """

    __metaclass__ = FunctionMeta

    # Place this here to avoid recomputing it all the time

    __norm_const = 1.0 / (math.sqrt(2 * np.pi))

    def _set_units(self, x_unit, y_unit):

        # The normalization is the integral from -inf to +inf, i.e., has dimensions of
        # y_unit * x_unit
        self.F.unit = y_unit * x_unit

        # The mu has the same dimensions as the x
        self.mu.unit = x_unit

        # The lower_bound has the same dimensions as the x
        self.lower_bound.unit = x_unit

        # The upper_bound has the same dimensions as the x
        self.upper_bound.unit = x_unit

        # sigma has the same dimensions as x
        self.sigma.unit = x_unit




    # noinspection PyPep8Naming
    def evaluate(self, x, F, mu, sigma, lower_bound, upper_bound):


        # phi is in unitless, so we need to do this trick
        # to keep the units right

        norm = self.__norm_const / sigma

        phi = np.zeros(x.shape) * F * norm * 0.
        idx = (x >= lower_bound) & (x <= upper_bound)

        sqrt_two = 1.414213562

        # precalculate the arguments to the CDF

        lower_arg = (lower_bound - mu) / sigma
        upper_arg = (upper_bound - mu) / sigma



        # the typical gaussian functions

        phi[idx] = np.exp(-np.power(x[idx] - mu, 2.) / (2 * np.power(sigma, 2.))) * F * norm

        # the denominator is a function of the CDF


        if isinstance(F, astropy_units.Quantity):
            # erf cannot accept units

            upper_arg = upper_arg.value
            lower_arg = lower_arg.value

        theta_lower = 0.5 + 0.5 * erf(lower_arg / sqrt_two)

        theta_upper = 0.5 + 0.5 * erf(upper_arg / sqrt_two)




        return phi / (theta_upper - theta_lower)

    def from_unit_cube(self, x):

        mu = self.mu.value
        sigma = self.sigma.value
        lower_bound = self.lower_bound.value
        upper_bound = self.upper_bound.value

        sqrt_two = 1.414213562

        if x < 1e-16 or (1 - x) < 1e-16:
            res = -1e32

        # precalculate the arguments to the  CDF

        lower_arg = (lower_bound - mu) / sigma
        upper_arg = (upper_bound - mu) / sigma

        theta_lower = 0.5 + 0.5 * erf(lower_arg / sqrt_two)

        theta_upper = 0.5 + 0.5 * erf(upper_arg / sqrt_two)

        # now precalculate the argument to the Inv. CDF

        arg = theta_lower + x * (theta_upper - theta_lower)

        return mu + sigma * sqrt_two * erfcinv(2 * (1 - arg))


class Cauchy(Function1D):
    r"""
    description :

        The Cauchy distribution

    latex : $ K \frac{1}{ \gamma \pi} \left[ \frac{\gamma^2}{(x-x_0)^2 + \gamma^2}  \right] $

    parameters :

        K :

            desc : Integral between -inf and +inf. Fix this to 1 to obtain a Cauchy distribution
            initial value : 1

        x0 :

            desc : Central value
            initial value : 0.0

        gamma :

            desc : standard deviation
            initial value : 1.0
            min : 1e-12

    tests :
        - { x : 0.0, function value: 0.3989422804014327, tolerance: 1e-10}
        - { x : -1.0, function value: 0.24197072451914337, tolerance: 1e-9}

    """

    __metaclass__ = FunctionMeta

    # Place this here to avoid recomputing it all the time

    __norm_const = 1.0 / (math.sqrt(2 * np.pi))

    def _set_units(self, x_unit, y_unit):
        # The normalization is the integral from -inf to +inf, i.e., has dimensions of
        # y_unit * x_unit
        self.K.unit = y_unit * x_unit

        # The mu has the same dimensions as the x
        self.x0.unit = x_unit

        # sigma has the same dimensions as x
        self.gamma.unit = x_unit

    # noinspection PyPep8Naming
    def evaluate(self, x, K, x0, gamma):
        norm = 1 / (gamma * np.pi)

        gamma2 = gamma * gamma

        return K * norm * gamma2 / ((x - x0) * (x - x0) + gamma2)

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        x0 = self.x0.value
        gamma = self.gamma.value

        half_pi = 1.57079632679

        res = np.tan(np.pi * x - half_pi) * gamma + x0

        return res


class Log_normal(Function1D):
    r"""
       description :

           A log normal function

       latex : $ K \frac{1}{ x \sigma \sqrt{2 \pi}}\exp{\frac{(\log x-\mu)^2}{2~(\sigma)^2}} $

       parameters :

           F :

               desc : Integral between 0and +inf. Fix this to 1 to obtain a log Normal distribution
               initial value : 1

           mu :

               desc : Central value
               initial value : 0.0

           sigma :

               desc : standard deviation
               initial value : 1.0
               min : 1e-12

       tests :
           - { x : 0.0, function value: 0.3989422804014327, tolerance: 1e-10}
           - { x : -1.0, function value: 0.24197072451914337, tolerance: 1e-9}

       """

    __metaclass__ = FunctionMeta


    # Place this here to avoid recomputing it all the time

    __norm_const = 1.0 / (math.sqrt(2 * np.pi))


    def _set_units(self, x_unit, y_unit):

        # The normalization is the integral from -inf to +inf, i.e., has dimensions of
        # y_unit * x_unit
        self.F.unit = y_unit

        # The mu has the same dimensions as the x
        self.mu.unit = astropy_units.dimensionless_unscaled

        # sigma has the same dimensions as x
        self.sigma.unit = astropy_units.dimensionless_unscaled

    # noinspection PyPep8Naming
    def evaluate(self, x, F, mu, sigma):

        if isinstance(F, astropy_units.Quantity):

            x_ = x.value

        else:

            x_ = x

        norm = self.__norm_const / (sigma * x_)

        return F * norm * np.exp(-np.power(np.log(x_) - mu, 2.) / (2 * np.power(sigma, 2.)))

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        mu = self.mu.value
        sigma = self.sigma.value

        sqrt_two = 1.414213562

        if x < 1e-16 or (1 - x) < 1e-16:

            res = -1e32

        else:

            res = mu + sigma * sqrt_two * erfcinv(2 * (1 - x))

        return np.exp(res)


class Uniform_prior(Function1D):
    r"""
    description :

        A function which is constant on the interval lower_bound - upper_bound and 0 outside the interval. The
        extremes of the interval are counted as part of the interval.

    latex : $ f(x)=\begin{cases}0 & x < \text{lower_bound} \\\text{value} & \text{lower_bound} \le x \le \text{upper_bound} \\ 0 & x > \text{upper_bound} \end{cases}$

    parameters :

        lower_bound :

            desc : Lower bound for the interval
            initial value : 0
            min : -np.inf
            max : np.inf

        upper_bound :

            desc : Upper bound for the interval
            initial value : 1
            min : -np.inf
            max : np.inf

        value :

            desc : Value in the interval
            initial value : 1.0

    tests :
        - { x : 0.5, function value: 1.0, tolerance: 1e-20}
        - { x : -0.5, function value: 0, tolerance: 1e-20}

    """

    __metaclass__ = FunctionMeta

    def _set_units(self, x_unit, y_unit):
        # Lower and upper bound has the same unit as x
        self.lower_bound.unit = x_unit
        self.upper_bound.unit = x_unit

        # value has the same unit as y
        self.value.unit = y_unit

    def evaluate(self, x, lower_bound, upper_bound, value):
        # The value * 0 is to keep the units right

        result = np.zeros(x.shape) * value * 0

        idx = (x >= lower_bound) & (x <= upper_bound)
        result[idx] = value

        return result


    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        lower_bound = self.lower_bound.value
        upper_bound = self.upper_bound.value

        low = lower_bound
        spread = float(upper_bound - lower_bound)

        par = x * spread + low

        return par

class Log_uniform_prior(Function1D):
    r"""
    description :

        A function which is K/x on the interval lower_bound - upper_bound and 0 outside the interval. The
        extremes of the interval are NOT counted as part of the interval. Lower_bound must be >= 0.

    latex : $ f(x)=K~\begin{cases}0 & x \le \text{lower_bound} \\\frac{1}{x} & \text{lower_bound} < x < \text{upper_bound} \\ 0 & x \ge \text{upper_bound} \end{cases}$

    parameters :

        lower_bound :

            desc : Lower bound for the interval
            initial value : 1e-20
            min : 1e-30
            max : np.inf

        upper_bound :

            desc : Upper bound for the interval
            initial value : 100
            min : 1e-30
            max : np.inf

        K :

            desc : Normalization
            initial value : 1
            fix : yes

    """

    __metaclass__ = FunctionMeta

    def _setup(self):
        self._handle_units = False

    def _set_units(self, x_unit, y_unit):
        # Lower and upper bound has the same unit as x
        self.lower_bound.unit = x_unit
        self.upper_bound.unit = x_unit
        self.K.unit = y_unit * x_unit

    def evaluate(self, x, lower_bound, upper_bound, K):
        # This makes the prior proper because it is the integral between lower_bound and upper_bound

        res = np.where((x > lower_bound) & (x < upper_bound), K / x, 0)

        if isinstance(x, astropy_units.Quantity):

            return res * self.y_unit

        else:

            return res

    def from_unit_cube(self, x):
        """
        Used by multinest

        :param x: 0 < x < 1
        :param lower_bound:
        :param upper_bound:
        :return:
        """

        low = math.log10(self.lower_bound.value)
        up = math.log10(self.upper_bound.value)

        spread = up - low
        par = 10 ** (x * spread + low)

        return par
