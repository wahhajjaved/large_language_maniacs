# -*- coding: utf-8 -*-
from functools import partial


class AbstractOperator(object):
    """
        This is the base class for operators.
    """
    def __init__(self):
        self.n_in = None
        self.n_out = None

    def __call__(self, *args, **kwargs):
        raise NotImplementedError


class PopulationOperator(AbstractOperator):
    def __init__(self, selection, operator, n_out=None):
        super(PopulationOperator, self).__init__()
        self.selection = selection
        check_operator(operator)
        self.operator = operator
        self.n_out = n_out

    def __call__(self, pop, *args, **kwargs):
        new_pop = []
        while len(new_pop) <= (self.n_out or len(pop)):
            candidates = self.selection(pop)
            new_pop.append(self.operator(candidates))

        return new_pop


def build_population_operator(operator, selection_builder=None, n_out=None):
    check_operator(operator)

    if selection_builder is None:
        from gplib.operators.selection import RandomSelection
        selection_builder = partial(RandomSelection, replacement=False)

    selection = selection_builder(k=operator.n_input)

    return PopulationOperator(selection, operator, n_out)


def check_operator(operator):
    if not isinstance(operator, AbstractOperator):
        typ = TypeError
        msg = 'Expected type: {} not {}.'.format(AbstractOperator, type(operator))
    else:
        return

    raise typ(msg)
