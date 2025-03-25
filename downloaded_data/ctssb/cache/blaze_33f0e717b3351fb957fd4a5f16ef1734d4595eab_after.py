from __future__ import absolute_import

import operator
from datashape import dshape
from .core import Scalar, BinOp, UnaryOp
from ..core import Expr
from .boolean import *


class NumberInterface(Scalar):
    def __eq__(self, other):
        return Eq(self, other)

    def __ne__(self, other):
        return NE(self, other)

    def __lt__(self, other):
        return LT(self, other)

    def __le__(self, other):
        return LE(self, other)

    def __gt__(self, other):
        return GT(self, other)

    def __ge__(self, other):
        return GE(self, other)

    def __neg__(self):
        return Neg(self)

    def __add__(self, other):
        return Add(self, other)

    def __radd__(self, other):
        return Add(other, self)

    def __mul__(self, other):
        return Mul(self, other)

    def __rmul__(self, other):
        return Mul(other, self)

    def __div__(self, other):
        return Div(self, other)

    def __rdiv__(self, other):
        return Div(other, self)

    def __sub__(self, other):
        return Sub(self, other)

    def __rsub__(self, other):
        return Sub(other, self)

    def __pow__(self, other):
        return Pow(self, other)

    def __rpow__(self, other):
        return Pow(other, self)

    def __mod__(self, other):
        return Mod(self, other)

    def __rmod__(self, other):
        return Mod(other, self)


class Number(NumberInterface):
    __hash__ = Expr.__hash__


class Arithmetic(BinOp, Number):
    @property
    def dshape(self):
        return dshape('real')


class Add(Arithmetic):
    symbol = '+'
    op = operator.add


class Mul(Arithmetic):
    symbol = '*'
    op = operator.mul


class Sub(Arithmetic):
    symbol = '-'
    op = operator.sub


class Div(Arithmetic):
    symbol = '/'
    op = operator.truediv


class Pow(Arithmetic):
    symbol = '**'
    op = operator.pow


class Mod(Arithmetic):
    symbol = '%'
    op = operator.mod


class Neg(UnaryOp, Number):
    op = operator.neg

    def __str__(self):
        return '-%s' % self.parent


class UnaryMath(Number, UnaryOp):
    pass


class sin(UnaryMath): pass
class cos(UnaryMath): pass
class tan(UnaryMath): pass
class exp(UnaryMath): pass
class log(UnaryMath): pass
