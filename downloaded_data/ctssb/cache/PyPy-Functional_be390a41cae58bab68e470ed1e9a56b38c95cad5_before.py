"""
The code needed to flow and annotate low-level helpers -- the ll_*() functions
"""

import types
from pypy.tool.sourcetools import valid_identifier
from pypy.annotation import model as annmodel
from pypy.annotation.policy import AnnotatorPolicy
from pypy.rpython.lltypesystem import lltype
from pypy.rpython import extfunctable

def not_const(s_obj): # xxx move it somewhere else
    if s_obj.is_constant():
        new_s_obj = annmodel.SomeObject()
        new_s_obj.__class__ = s_obj.__class__
        new_s_obj.__dict__ = s_obj.__dict__
        del new_s_obj.const
        s_obj = new_s_obj
    return s_obj


class KeyComp(object):
    def __init__(self, val):
        self.val = val
    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.val == other.val
    def __ne__(self, other):
        return not (self == other)
    def __hash__(self):
        return hash(self.val)
    def __str__(self):
        val = self.val
        if isinstance(val, lltype.LowLevelType):
            return val._short_name() + 'LlT'
        s = getattr(val, '__name__', None)
        if s is None:
            compact = getattr(val, 'compact_repr', None)
            if compact is None:
                s = repr(val)
            else:
                s = compact()        
        return s + 'Const'

class LowLevelAnnotatorPolicy(AnnotatorPolicy):
    allow_someobjects = False

    def default_specialize(pol, funcdesc, args_s):
        if hasattr(funcdesc, 'pyobj') and hasattr(funcdesc.pyobj, 'llresult'):
            # XXX bug mwh to write some tests for this stuff
            funcdesc.overridden = True
            return annmodel.lltype_to_annotation(funcdesc.pyobj.llresult)
        key = []
        new_args_s = []
        for s_obj in args_s:
            if isinstance(s_obj, annmodel.SomePBC):
                assert s_obj.is_constant(), "ambiguous low-level helper specialization"
                key.append(KeyComp(s_obj.const))
                new_args_s.append(s_obj)
            else:
                new_args_s.append(not_const(s_obj))
                try:
                    key.append(annmodel.annotation_to_lltype(s_obj))
                except ValueError:
                    # passing non-low-level types to a ll_* function is allowed
                    # for module/ll_*
                    key.append(s_obj.__class__)
        flowgraph = funcdesc.cachedgraph(tuple(key))
        args_s[:] = new_args_s
        return flowgraph

    def override__init_opaque_object(pol, s_opaqueptr, s_value):
        assert isinstance(s_opaqueptr, annmodel.SomePtr)
        assert isinstance(s_opaqueptr.ll_ptrtype.TO, lltype.OpaqueType)
        assert isinstance(s_value, annmodel.SomeExternalObject)
        exttypeinfo = extfunctable.typetable[s_value.knowntype]
        assert s_opaqueptr.ll_ptrtype.TO._exttypeinfo == exttypeinfo
        return annmodel.SomeExternalObject(exttypeinfo.typ)

    def override__from_opaque_object(pol, s_opaqueptr):
        assert isinstance(s_opaqueptr, annmodel.SomePtr)
        assert isinstance(s_opaqueptr.ll_ptrtype.TO, lltype.OpaqueType)
        exttypeinfo = s_opaqueptr.ll_ptrtype.TO._exttypeinfo
        return annmodel.SomeExternalObject(exttypeinfo.typ)

    def override__to_opaque_object(pol, s_value):
        assert isinstance(s_value, annmodel.SomeExternalObject)
        exttypeinfo = extfunctable.typetable[s_value.knowntype]
        return annmodel.SomePtr(lltype.Ptr(exttypeinfo.get_lltype()))


def annotate_lowlevel_helper(annotator, ll_function, args_s):
    return annotator.annotate_helper(ll_function, args_s, policy= LowLevelAnnotatorPolicy())

# ___________________________________________________________________
# Mix-level helpers: combining RPython and ll-level

class MixLevelAnnotatorPolicy(LowLevelAnnotatorPolicy):

    def __init__(pol, rtyper):
        pol.rtyper = rtyper

    def default_specialize(pol, funcdesc, args_s):
        name = funcdesc.name
        if name.startswith('ll_') or name.startswith('_ll_'): # xxx can we do better?
            return LowLevelAnnotatorPolicy.default_specialize(pol, funcdesc, args_s)
        else:
            return funcdesc.cachedgraph(None)

    def specialize__arglltype(pol, funcdesc, args_s, i):
        key = pol.rtyper.getrepr(args_s[i]).lowleveltype
        alt_name = funcdesc.name+"__for_%sLlT" % key._short_name()
        return funcdesc.cachedgraph(key, alt_name=valid_identifier(alt_name))        


class MixLevelHelperAnnotator:

    def __init__(self, rtyper):
        self.rtyper = rtyper
        self.policy = MixLevelAnnotatorPolicy(rtyper)
        self.pending = []     # list of (graph, args_s, s_result)
        self.delayedreprs = []
        self.delayedconsts = [] 

    def getgraph(self, ll_function, args_s, s_result):
        # get the graph of the mix-level helper ll_function and prepare it for
        # being annotated.  Annotation and RTyping should be done in a single shot
        # at the end with finish().
        graph = self.rtyper.annotator.annotate_helper(ll_function, args_s,
                                                      policy = self.policy,
                                                      complete_now = False)
        for v_arg, s_arg in zip(graph.getargs(), args_s):
            self.rtyper.annotator.setbinding(v_arg, s_arg)
        self.rtyper.annotator.setbinding(graph.getreturnvar(), s_result)
        self.pending.append((graph, args_s, s_result))
        return graph

    def getdelayedrepr(self, s_value):
        """Like rtyper.getrepr(), but the resulting repr will not be setup() at
        all before finish() is called.
        """
        r = self.rtyper.getrepr(s_value)
        r.set_setup_delayed(True)
        self.delayedreprs.append(r)
        return r

    def delayedconst(self, repr, obj):
        if repr.is_setup_delayed():
            delayedptr = lltype._ptr(repr.lowleveltype, "delayed!")
            self.delayedconsts.append((delayedptr, repr, obj))
            return delayedptr
        else:
            return repr.convert_const(obj)

    def finish(self):
        # push all the graphs into the annotator's pending blocks dict at once
        rtyper = self.rtyper
        ann = rtyper.annotator
        for graph, args_s, s_result in self.pending:
            # mark the return block as already annotated, because the return var
            # annotation was forced in getgraph() above.  This prevents temporary
            # less general values reaching the return block from crashing the
            # annotator (on the assert-that-new-binding-is-not-less-general).
            ann.annotated[graph.returnblock] = graph
            ann.build_graph_types(graph, args_s, complete_now=False)
        ann.complete_helpers(self.policy)
        for graph, args_s, s_result in self.pending:
            s_real_result = ann.binding(graph.getreturnvar())
            if s_real_result != s_result:
                raise Exception("wrong annotation for the result of %r:\n"
                                "originally specified: %r\n"
                                " found by annotating: %r" %
                                (graph, s_result, s_real_result))
        rtyper.type_system.perform_normalizations(rtyper, insert_stack_checks=False)
        for r in self.delayedreprs:
            r.set_setup_delayed(False)
        for p, repr, obj in self.delayedconsts:
            p._become(repr.convert_const(obj))
        rtyper.specialize_more_blocks()
        del self.pending[:]
        del self.delayedreprs[:]
        del self.delayedconsts[:]
