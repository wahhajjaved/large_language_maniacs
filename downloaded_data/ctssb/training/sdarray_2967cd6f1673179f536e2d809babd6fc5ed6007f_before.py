__all__ = ["sel"]

import numpy as np


class SDArraySelector:
    def __init__(self, accessed, *coords):
        self.accessed = accessed
        self.coords = coords

    def __call__(self, evaluator, *values, drop=True):
        selected = self.accessed

        for coord, value in zip(self.coords, values):
            condition = evaluator(selected[coord], value)
            selected = selected.where(condition, drop=drop)

        return selected

    def _to_seq(self, values):
        return (values,) if len(self.coords) == 1 else values

    def _to_unique(self, c, v, sep=","):
        return [u for u in np.unique(c) if np.any(np.isin(v, u.split(sep)))]

    def eq(self, *values, drop=True):
        return self(lambda c, v: c.isin(v), *values, drop=drop)

    def neq(self, *values, drop=True):
        return self(lambda c, v: ~c.isin(v), *values, drop=drop)

    def gt(self, *values, drop=True):
        return self(lambda c, v: c > v, *values, drop=drop)

    def gt_or_eq(self, *values, drop=True):
        return self(lambda c, v: c >= v, *values, drop=drop)

    def lt(self, *values, drop=True):
        return self(lambda c, v: c < v, *values, drop=drop)

    def lt_or_eq(self, *values, drop=True):
        return self(lambda c, v: c <= v, *values, drop=drop)

    def between(self, *values, drop=True):
        return self(lambda c, v: (c >= v[0]) & (c <= v[1]), *values, drop=drop)

    def contains(self, *values, drop=True):
        return self(lambda c, v: c.isin(self._to_unique(c, v)), *values, drop=drop)

    def __eq__(self, values):
        """Helper operator for the `eq` method."""
        return self.eq(*self._to_seq(values))

    def __ne__(self, values):
        """Helper operator for the `neq` method."""
        return self.neq(*self._to_seq(values))

    def __gt__(self, values):
        """Helper operator for the `gt` method."""
        return self.gt(*self._to_seq(values))

    def __ge__(self, values):
        """Helper operator for the `gt_or_eq` method."""
        return self.gt_or_eq(*self._to_seq(values))

    def __lt__(self, values):
        """Helper operator for the `lt` method."""
        return self.lt(*self._to_seq(values))

    def __le__(self, values):
        """Helper operator for the `lt_or_eq` method."""
        return self.lt_or_eq(*self._to_seq(values))

    def __matmul__(self, values):
        """Helper operator for the `between` method."""
        return self.between(*self._to_seq(values))

    def __pow__(self, values):
        """Helper operator for the `contains` method."""
        return self.contains(*self._to_seq(values))


def sel(array, *coords):
    """Make an `SDArraySelector` instance."""
    return SDArraySelector(array, *coords)
