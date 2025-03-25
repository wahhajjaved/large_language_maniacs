from pypy.objspace.std.stdtypedef import *
from pypy.objspace.std.inttype import int_typedef


def descr__new__(space, w_booltype, w_obj=None):
    if space.is_true(w_obj):
        return space.w_True
    else:
        return space.w_False

# ____________________________________________________________

bool_typedef = StdTypeDef("bool", [int_typedef],
    __new__ = newmethod(descr__new__),
    )
