
from multipledispatch import dispatch
from blaze.expr.table import *

base = (int, float, str, bool)

@dispatch(base, object)
def compute(a, b):
    return a


@dispatch(TableExpr, dict)
def compute(t, d):
    if t in d:
        return d[t]

    # Pare down d to only nodes in table
    nodes = set(t.traverse())
    d = dict((k, v) for k, v in d.items()
                    if k in nodes)

    # Common case: One relevant value in dict
    #              Switch to standard dispatching scheme
    if len(d) == 1:
        return compute(t, list(d.values())[0])

    if hasattr(t, 'parent'):
        parent = compute(t.parent, d)
        t2 = t.subs({t.parent: TableSymbol(t.parent.schema)})
        return compute(t2, parent)

    raise NotImplementedError("No method found to compute on multiple Tables")


@dispatch(Join, dict)
def compute(t, d):
    lhs = compute(t.lhs, d)
    rhs = compute(t.rhs, d)


    t2 = t.subs({t.lhs: TableSymbol(t.lhs.schema),
                 t.rhs: TableSymbol(t.rhs.schema)})
    return compute(t2, lhs, rhs)


@dispatch(Join, object)
def compute(t, o):
    return compute(t, o, o)
