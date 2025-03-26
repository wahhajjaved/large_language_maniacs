# Copyright (c) 2015 Matthew Earl
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
#     The above copyright notice and this permission notice shall be included
#     in all copies or substantial portions of the Software.
# 
#     THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#     OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#     MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
#     NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#     DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#     OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
#     USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
WFF module.

Routines for making propositional logic formulae, as well as routines for
converting them to CNF expressions in an efficient manner.

"""

__all__ = (
    'to_cnf',
    'Var',
)

import abc
import enum

import cnf

class _Formula(metaclass=abc.ABCMeta):
    """
    Base class for formula types.

    Provides common methods. Suitable for use as a mixin.

    _Formulas are immutable, and sub-classes should respect this.

    """
    def __invert__(self):
        return _Op(_OpType.NOT, [self])

    def __and__(self, other):
        if not isinstance(other, _Formula):
            raise NotImplemented
        return _Op(_OpType.AND, [self, other])

    def __or__(self, other):
        if not isinstance(other, _Formula):
            raise NotImplemented
        return _Op(_OpType.OR, [self, other])

    def __rshift__(self, other):
        if not isinstance(other, _Formula):
            raise NotImplemented
        return _Op(_OpType.IMPLIES, [self, other])

    def __lshift__(self, other):
        if not isinstance(other, _Formula):
            raise NotImplemented
        return _Op(_OpType.IMPLIES, [other, self])

    def iff(self, other):
        if not isinstance(other, _Formula):
            raise NotImplemented
        return _Op(_OpType.IFF, [self, other])

    @abc.abstractmethod
    def _is_op(self):
        """
        Is this formula an operation?

        """
        raise NotImplemented

    @abc.abstractmethod
    def _eliminate_iff(self):
        """
        Convert iff operations into two implies operations, ANDED

        """
        raise NotImplemented

    @abc.abstractmethod
    def _eliminate_implies(self):
        """
        Convert implies operations (a >> b) into (~a | b).

        """
        raise NotImplemented

    @abc.abstractmethod
    def _move_nots(self):
        """
        Push nots inwards using De Morgan's Law.

        """
        raise NotImplemented

    @abc.abstractmethod
    def _distribute_ors(self):
        """
        Distribute and over ors.

        """
        raise NotImplemented

    def _to_cnf(self):
        """
        Implementation of `to_cnf()`.

        """
        formula = self._eliminate_iff()
        formula = formula._eliminate_implies()
        formula = formula._move_nots()
        formula = formula._distribute_ors()

        return formula

class _OpType(enum.Enum):
    NOT     = 1
    AND     = 2
    OR      = 4
    IMPLIES = 5
    IFF     = 6

class _Op(_Formula):
    """
    A formula consisting of a binary or unary operation on 2 other formulae.

    Attributes:
        op_type: The operation that this formula represents.
        args: Arguments to the operation.

    """

    OP_ARITY = {_OpType.NOT: 1,
                _OpType.AND: 2,
                _OpType.OR: 2,
                _OpType.IMPLIES: 2,
                _OpType.IFF: 2,
               }

    def __init__(self, op_type, args):
        self._op_type = op_type
        self._args = args

        if len(args) != self.OP_ARITY[op_type]:
            raise ValueError

    def __repr__(self):
        op_to_str = {_OpType.AND: "&",
                     _OpType.OR: "|",
                     _OpType.IMPLIES: ">>"}

        if self._op_type == _OpType.NOT:
            return "~{!r}".format(self._args[0])
        elif self._op_type == _OpType.IFF:
            return "({!r}).iff({!r})".format(*self._args)
        else:
            return "({!r} {} {!r})".format(self._args[0],
                                           op_to_str[self._op_type],
                                           self._args[1])

    def _is_op(self):
        return True

    def _eliminate_iff(self):
        new_args = [arg._eliminate_iff() for arg in self._args]
        if self._op_type == _OpType.IFF:
            out = (new_args[0] >> new_args[1]) & (new_args[0] << new_args[1])
        else:
            out = _Op(self._op_type, new_args)
        return out

    def _eliminate_implies(self):
        new_args = [arg._eliminate_implies() for arg in self._args]
        if self._op_type == _OpType.IMPLIES:
            out = (~new_args[0] | new_args[1])
        else:
            out = _Op(self._op_type, new_args)
        return out

    def _move_nots(self):
        if self._op_type == _OpType.NOT and self._args[0]._is_op():
            # Not of an operation. Either move the NOT in through De Morgan's
            # Law (in the case of an OR or an AND), or in the case of a NOT of
            # a NOT eliminate both NOTs. Recursively apply to the result.
            arg = self._args[0]
            if arg._op_type == _OpType.NOT:
                out = arg._args[0]
            elif arg._op_type == _OpType.AND:
                out = ~arg._args[0] | ~arg._args[1]
            elif arg._op_type == _OpType.OR:
                out = ~arg._args[0] & ~arg._args[1]
            else:
                assert False, ("Op of type {} should have been "
                               "eliminated".format(self._op_type))
            out = out._move_nots()
        elif self._op_type == _OpType.NOT and not self._args[0]._is_op():
            # NOT of a var. Nothing to do.
            out = self
        else:
            # Some other operation. Apply the operation to the children.
            new_args = [arg._move_nots() for arg in self._args]
            out = _Op(self._op_type, new_args)
        return out

    def _distribute_ors(self):
        # Precondition: The formula contains only AND, OR and NOT operators,
        #               and vars. The NOT operations only appear applied to
        #               vars.
        # Postcondition: The formula is in CNF.

        new_args = [arg._distribute_ors() for arg in self._args]

        if (self._op_type == _OpType.OR and
            new_args[1]._is_op() and new_args[1]._op_type == _OpType.AND):
            # We have an expression of the form P | (Q & R), so distribute to
            # (P | Q) & (P | R).
            out = ((new_args[0] | new_args[1]._args[0]) &
                   (new_args[0] | new_args[1]._args[1]))

            # The RHS or LHS of `out` ((P | Q) or (P | R)) may still contain
            # ANDs, so run _distribute_ors() on them to bring ANDs up to the
            # top. After this `out` will be in CNF.
            out = (out._args[0]._distribute_ors() &
                   out._args[1]._distribute_ors())
        elif (self._op_type == _OpType.OR and
              new_args[0]._is_op() and new_args[0]._op_type == _OpType.AND):
            # We have an expression of the form (P & Q) | R, so distribute to
            # (P | R) & (Q | R)
            out = ((new_args[0]._args[0] | new_args[1]) &
                   (new_args[0]._args[1] | new_args[1]))

            # Distribute the ORs on the children, as in the previous case.
            out = (out._args[0]._distribute_ors() &
                   out._args[1]._distribute_ors())
        else:
            # We either have a pure tree of ORs, a tree with ANDs at the top, 
            # or just a single term. All of these satisfy the post-condition
            # for this function.
            out = _Op(self._op_type, new_args)

        return out

class Var(cnf.Var, _Formula):
    def __init__(self, name=None):
        super().__init__(name=name)

    def _is_op(self):
        return False

    def __repr__(self):
        return "Var({!r})".format(self.name)

    def _eliminate_iff(self):
        return self

    def _eliminate_implies(self):
        return self

    def _move_nots(self):
        return self

    def _distribute_ors(self):
        return self

def to_cnf(formula):
    """
    Convert the formula to CNF (conjunctive normal form).

    """
    return formula._to_cnf()
