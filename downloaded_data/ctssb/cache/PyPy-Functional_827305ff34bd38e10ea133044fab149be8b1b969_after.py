"""
This file defines utilities for manipulating objects in an
RPython-compliant way.
"""

import sys, new

class Symbolic(object):

    def annotation(self):
        return None

    def lltype(self):
        return None

    def __cmp__(self, other):
        if self is other:
            return 0
        else:
            raise TypeError("Symbolics can not be compared!")

    def __hash__(self):
        raise TypeError("Symbolics are not hashable!")

class ComputedIntSymbolic(Symbolic):

    def __init__(self, compute_fn):
        self.compute_fn = compute_fn

    def annotation(self):
        from pypy.annotation import model
        return model.SomeInteger()

    def lltype(self):
        from pypy.rpython.lltypesystem import lltype
        return lltype.Signed


def instantiate(cls):
    "Create an empty instance of 'cls'."
    if isinstance(cls, type):
        return cls.__new__(cls)
    else:
        return new.instance(cls)

def we_are_translated():
    return False
# annotation -> True

def keepalive_until_here(*values):
    pass

def hint(x, **kwds):
    return x


class FREED_OBJECT(object):
    def __getattribute__(self, attr):
        raise RuntimeError("trying to access freed object")
    def __setattr__(self, attr, value):
        raise RuntimeError("trying to access freed object")


def free_non_gc_object(obj):
    assert not getattr(obj.__class__, "_alloc_flavor_", 'gc').startswith('gc'), "trying to free gc object"
    obj.__dict__ = {}
    obj.__class__ = FREED_OBJECT

def cast_object_to_weakgcaddress(obj):
    from pypy.rpython.lltypesystem.llmemory import fakeweakaddress
    return fakeweakaddress(obj)

def cast_weakgcaddress_to_object(address, expected_result):
    if address.ref is None:  # NULL address
        return None
    obj = address.get()
    assert obj is not None
    assert isinstance(obj, expected_result)
    return obj

from pypy.rpython.extregistry import ExtRegistryEntry

class Entry(ExtRegistryEntry):
    _about_ = cast_object_to_weakgcaddress

    def compute_result_annotation(self, s_obj):
        from pypy.annotation import model as annmodel
        return annmodel.SomeWeakGcAddress()

    def specialize_call(self, hop):
        vlist = hop.inputargs(hop.args_r[0])
        return hop.genop('cast_ptr_to_weakadr', vlist,
                         resulttype=hop.r_result.lowleveltype)

class Entry(ExtRegistryEntry):
    _about_ = cast_weakgcaddress_to_object

    def compute_result_annotation(self, s_int, s_clspbc):
        from pypy.annotation import model as annmodel
        assert len(s_clspbc.descriptions) == 1
        desc = s_clspbc.descriptions.keys()[0]
        cdef = desc.getuniqueclassdef()
        return annmodel.SomeInstance(cdef, can_be_None=True)

    def specialize_call(self, hop):
        from pypy.rpython import raddress
        assert isinstance(hop.args_r[0], raddress.WeakGcAddressRepr)
        vlist = [hop.inputarg(raddress.weakgcaddress_repr, arg=0)]
        return hop.genop('cast_weakadr_to_ptr', vlist,
                         resulttype = hop.r_result.lowleveltype)


   
# __ hlinvoke XXX this doesn't seem completely the right place for this

def hlinvoke(repr, llcallable, *args):
    raise TypeError, "hlinvoke is meant to be rtyped and not called direclty"


class UnboxedValue(object):
    """A mixin class to use for classes that have exactly one field which
    is an integer.  They are represented as a tagged pointer."""
    _mixin_ = True

    def __new__(cls, value):
        assert '__init__' not in cls.__dict__  # won't be called anyway
        assert isinstance(cls.__slots__, str) or len(cls.__slots__) == 1
        return super(UnboxedValue, cls).__new__(cls)

    def __init__(self, value):
        # this funtion is annotated but not included in the translated program
        int_as_pointer = value * 2 + 1   # XXX for now
        if -sys.maxint-1 <= int_as_pointer <= sys.maxint:
            if isinstance(self.__slots__, str):
                setattr(self, self.__slots__, value)
            else:
                setattr(self, self.__slots__[0], value)
        else:
            raise OverflowError("UnboxedValue: argument out of range")

    def __repr__(self):
        return '<unboxed %d>' % (self.getvalue(),)

    def getvalue(self):   # helper, equivalent to reading the custom field
        if isinstance(self.__slots__, str):
            return getattr(self, self.__slots__)
        else:
            return getattr(self, self.__slots__[0])

# ____________________________________________________________


class r_dict(object):
    """An RPython dict-like object.
    Only provides the interface supported by RPython.
    The functions key_eq() and key_hash() are used by the key comparison
    algorithm."""

    def __init__(self, key_eq, key_hash):
        self._dict = {}
        self.key_eq = key_eq
        self.key_hash = key_hash

    def __getitem__(self, key):
        return self._dict[_r_dictkey(self, key)]

    def __setitem__(self, key, value):
        self._dict[_r_dictkey(self, key)] = value

    def __delitem__(self, key):
        del self._dict[_r_dictkey(self, key)]

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        for dk in self._dict:
            yield dk.key

    def __contains__(self, key):
        return _r_dictkey(self, key) in self._dict

    def get(self, key, default):
        return self._dict.get(_r_dictkey(self, key), default)

    def copy(self):
        result = r_dict(self.key_eq, self.key_hash)
        result.update(self)
        return result

    def update(self, other):
        for key, value in other.items():
            self[key] = value

    def keys(self):
        return [dk.key for dk in self._dict]

    def values(self):
        return self._dict.values()

    def items(self):
        return [(dk.key, value) for dk, value in self._dict.items()]

    iterkeys = __iter__

    def itervalues(self):
        return self._dict.itervalues()

    def iteritems(self):
        for dk, value in self._dict.items():
            yield dk.key, value

    def clear(self):
        self._dict.clear()

    def __repr__(self):
        "Representation for debugging purposes."
        return 'r_dict(%r)' % (self._dict,)

    def __hash__(self):
        raise TypeError("cannot hash r_dict instances")


class _r_dictkey(object):
    __slots__ = ['dic', 'key', 'hash']
    def __init__(self, dic, key):
        self.dic = dic
        self.key = key
        self.hash = dic.key_hash(key)
    def __eq__(self, other):
        if not isinstance(other, _r_dictkey):
            return NotImplemented
        return self.dic.key_eq(self.key, other.key)
    def __ne__(self, other):
        if not isinstance(other, _r_dictkey):
            return NotImplemented
        return not self.dic.key_eq(self.key, other.key)
    def __hash__(self):
        return self.hash

    def __repr__(self):
        return repr(self.key)
