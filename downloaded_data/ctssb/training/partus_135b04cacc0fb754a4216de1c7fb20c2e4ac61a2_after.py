#! /usr/bin/env python
# -*- coding: utf-8 -*-

###
### AST extensions.
###

import ast
import symtable
import marshal
import sys

import cl

from cl         import t, nil, typep, null, integerp, floatp, sequencep, stringp, mapcar, mapc,\
                       remove_if, sort, car, identity, every, find, with_output_to_string, error, reduce,\
                       symbol_value, progv
from cl         import _ast_rw as ast_rw, _ast_alias as ast_alias, _ast_string as ast_string, _ast_name as ast_name, _ast_attribute as ast_attribute, _ast_index as ast_index
from cl         import _ast_funcall as ast_funcall, _ast_maybe_normalise_string as ast_maybe_normalise_string
from cl         import _ast_Expr as ast_Expr, _ast_list as ast_list, _ast_tuple as ast_tuple, _ast_set as ast_set
from cl         import _ast_return as ast_return, _ast_assign as ast_assign, _ast_import as ast_import
from cl         import _ast_module as ast_module
from cl         import _not_implemented as not_implemented
from pergamum   import astp, bytesp, emptyp, ascend_tree, multiset, multiset_appendf, tuplep, fprintf
from neutrality import py3p


def extract_ast(source, filename='<virtualitty>'):
    return compile(source, filename, 'exec', flags=ast.PyCF_ONLY_AST)

def extract_symtable(source, filename):
    return symtable.symtable(source, filename, 'exec')


###
### Pyzzle-specific AST
###
def ast_strtuple(x, writep = False):
    assert(tuplep(x))
    return ast.Tuple(elts = mapcar(ast_string, x), ctx = ast_rw(writep))

def ast_marshal(x):
    return ast_funcall(ast_attribute(ast_name("marshal"), "loads"), (ast_bytes if py3p() else ast_string)(marshal.dumps(x)))

def module_ast_function_p(x):
    return x.body and every(lambda x: ast_def_p(x) or ast_import_maybe_from_p(x), x.body)


# predicates
def ast_string_p(x):            return typep(x, ast.Str)
def ast_dict_p(x):              return typep(x, ast.Dict)
def ast_list_p(x):              return typep(x, ast.List)
def ast_tuple_p(x):             return typep(x, ast.Tuple)
def ast_num_p(x):               return typep(x, ast.Num)
def ast_name_p(x):              return typep(x, ast.Name)
def ast_string_equalp(x, s):    return ast_string_p(x) and x.s == s
def ast_assign_p(x, to):        return typep(x, ast.Assign) and to in x.targets
def ast_pass_p(x):              return typep(x, ast.Pass)
def ast_module_p(x):            return typep(x, ast.Module)
def ast_def_p(x):               return typep(x, ast.FunctionDef)
def ast_import_p(x):            return typep(x, ast.Import)
def ast_import_from_p(x):       return typep(x, ast.ImportFrom)
def ast_import_maybe_from_p(x): return ast_import_p(x) or ast_import_from_p(x)
def ast_call_p(x):              return typep(x, ast.Call)
def ast_subscript_p(x):         return typep(x, ast.Subscript)
def ast_attribute_p(x):         return typep(x, ast.Attribute)
def ast_keyword_p(x):           return typep(x, ast.keyword)
def ast_slice_p(x):             return typep(x, ast.Slice)
def ast_extslice_p(x):          return typep(x, ast.ExtSlice)
def ast_index_p(x):             return typep(x, ast.Index)

def ast_mod_p(x):               return typep(x, ast.mod)
def ast_stmt_p(x):              return typep(x, ast.stmt)
def ast_expr_p(x):              return typep(x, ast.expr)

def ast_Expr_p(x):              return typep(x, ast.Expr)

# top-levels
def ast_expression(expr):
    assert astp(expr)
    return ast.Expression(body = expr, lineno = 0)

def ast_def(name, args, *body):
    filtered_body = remove_if(null, body)
    assert stringp(name) and all(mapcar(astp, filtered_body))
    ast_args = ast.arguments(
                             args=args,
                             defaults=[],
                             kwonlyargs=[],
                             kw_defaults=[],
                             vararg=None,
                             varargannotation=None,
                             kwarg=None,
                             kwargannotation=None,
                            )
    return ast.FunctionDef(name=name, decorator_list=[], args=ast_args, body=filtered_body, returns=None)


## expressions
def ast_bytes(bs):                  return ast.Bytes(s = the(bytes, bs))
def ast_arg(name):                  return ast.Name(arg = the(str, name), ctx = ast.Param())

def ast_dict(keys, values):
    return ast.Dict(keys = keys, values = values)

def ast_func_name(x):
    if typep(x, ast.Name):
        return x.id
    elif ast_subscript_p(x):
        return ast_func_name(x.value) + '[' + ast_func_name(x.slice.value) + ']'
    elif typep(x, ast.Attribute):
        return ast_func_name(x.value) + '.' + x.attr
    else:
        return '<unhandled>'

## statements
def astlist_prog(*body):
    "WARNING: not an actual node, returns a list!"
    return remove_if(null, body) or [ast.Pass()]

def ast_expression(node): return ast.Expression(body = the(ast.AST, node))

def ast_import_all_from(name):
    return ast.ImportFrom(module = the(str, name), names=[ast.alias(name='*', asname=None)])

def ast_assign_var(name, value):
    assert stringp(name) and (integerp(value) or stringp(value) or astp(value))
    return ast.Assign(value=value, targets=[ast_name(name, True)])

def ast_append_var(name, value):
    assert stringp(name) and (stringp(value) or astp(value))
    return ast.AugAssign(value=value, target=ast_name(name, True), op=ast.Add())

def ast_when(test, *body):
    return ast.If(test=test, body=remove_if(null, body), orelse=[])

def ast_unless(test, *body):
    return ast.If(test=test, body=[], orelse=remove_if(null, body))

def ast_try_except(body, except_handlers, *else_body):
    return ast.TryExcept(body=remove_if(null, body),
                         handlers=[ast.ExceptHandler(name=xname,
                                                     type=ast_name(xtype),
                                                     body=remove_if(null, xhandler_body)) for (xtype, xname, xhandler_body) in except_handlers],
                         orelse=remove_if(null, else_body))

def ast_print(*strings):
    return ast_expr(ast_funcall('print', *strings))


## validation
def ast_invalid_p(x, checks):
    """Perform a series of AST CHECKS on X.  If all is well, return None, otherwise, return an explanation."""

    for check in checks:
        result = check[0](x)
        if not result:
            return check[1] % check[2:]

def ast_fqn_p(x):
    if typep(x, ast.Name):
        return (x.id, )
    elif typep(x, ast.Attribute):
        rec = ast_fqn_p(x.value)
        return (rec + (x.attr, ) if rec else False)
    else:
        return False

def ast_children(x, ast_only = None, lineno_only = None):

        def passes(x):
                return (((not lineno_only) or
                         hasattr(x, "lineno")) and
                        ((not ast_only) or
                         isinstance(x, ast.AST)))
        for slot in x._fields:
                slotval = getattr(x, slot)
                if isinstance(slotval, list):
                        for elt in slotval:
                                if passes(elt):
                                        yield elt
                else:
                        if passes(slotval):
                                yield slotval

def ast_last_lineno(form):
        return max([form.lineno] +
                   [ ast_last_lineno(x)
                     for x in ast_children(form, lineno_only = True)])

def ast_first_subnode_at_lineno(form, lineno):
        """The implied condition is that LINENO definitely points at
some subform of FORM."""
        assert(lineno >= form.lineno)
        def rec(form):
                return if_let(find_if(lambda form: lineno >= form.lineno,
                                             sorted(ast_children(form, lineno_only = t),
                                                    key = slotting("lineno")),
                                             from_end = t),
                              rec,
                              lambda: form)
        return rec(form)

def pp_ast(o, stream = sys.stdout):
    """Pretty-print AST O."""

    def do_pp_ast_rec(x, name, pspec):
        lstr = ['']

        def lmesg(msg):
            lstr[0] += msg
            if msg[-1] == '\n'[0]:
                fprintf(stream, (lstr[0]))
                lstr[0] = ''

        def pp_prefix(spec):
            for i in spec:
                lmesg((' |  ' if i else '    '))

        pp_prefix(pspec)
        if name:
            lmesg('<' + name + '>: ')
        if x is None:
            lmesg('<None>\n')
        elif stringp(x):
            lmesg("'" + x + "'\n")
        elif bytesp(x) or integerp(x) or floatp(x) or isinstance(x, bool):
            lmesg(str(x) + '\n')
        elif sequencep(x) and emptyp(x):
            lmesg('[]\n')
        else:
            child_slot_names = type(x)._fields
            child_slots = [(k, getattr(x, k)) for k in child_slot_names]
            lmesg(type(x).__name__ + '  ')

            for (k, v) in child_slots:
                if stringp(v):
                    lmesg("<%s>: '%s', "%(k, v))

            lmesg('\n')
            child_list_slots = list(reversed(sort([(k, v) for (k, v) in child_slots if isinstance(v, list)], key=car)))
            child_list_slots_nr = len(child_list_slots)

            for (k, v) in child_slots:
                if not isinstance(v, list) and not stringp(v):
                    do_pp_ast_rec(v, k, pspec + (([True] if child_list_slots_nr > 0 else [False])))

            for ((k, v), i) in zip(child_list_slots, range(0, child_list_slots_nr)):
                pp_prefix(pspec)
                lmesg(' ^[' + k + ']\n')
                subprefix = pspec + (([True] if i < child_list_slots_nr - 1 else [False]))
                for sub in v:
                    do_pp_ast_rec(sub, '', subprefix)

    do_pp_ast_rec(o, '', [])
    return o

class NotImplemented(Exception):
        def __init__(self, action, x):
                self.action, self.x = action, x
        def __str__(self):
                return "%s %s is not implemented." % (action.capitalize(), x)

cl._string_set("*AST-PP-DEPTH*", 0, force_toplevel = t)
def pp_ast_as_code(x, tab = " " * 8):
        def indent():
                return tab * symbol_value("*AST-PP-DEPTH*")
        def iterate(xs):
                return mapcar(rec, xs)
        def rec(x):
                def pp_call(x):
                        return "%s(%s%s%s%s)" % (pp_ast_as_code(x.func),
                                                 ", ".join(iterate(x.args)),
                                                 ", ".join(iterate(x.keywords)),
                                                 (", *%s" % pp_ast_as_code(x.starargs)) if x.starargs else "",
                                                 (", **%s" % pp_ast_as_code(x.kwargs)) if x.kwargs else "")
                def pp_generatorexp(x):
                        return "%s%s" % (rec(x.elt), "".join(" " + rec(c) for c in x.generators))
                def pp_comprehension(x):
                        return "for %s in %s%s" % (rec(x.target), rec(x.iter),
                                                   "".join(" if %s" % rec(x) for x in x.ifs))
                def pp_attribute(x):
                        return "%s.%s" % (pp_ast_as_code(x.value), x.attr)
                def pp_name(x):
                        return x.id
                def pp_arg(x):
                        return x.arg + ((": " + str(x.annotation)) if x.annotation else "")
                def pp_alias(x):
                        return x.name + ((" as " + x.asname) if x.asname else "")
                def pp_keyword(x):
                        return "%s = %s" % (x.arg, pp_ast_as_code(x.value))
                def pp_subscript(x):
                        return "%s[%s]" % (pp_ast_as_code(x.value),
                                           pp_ast_as_code(x.slice))
                def pp_index(x):
                        return "%s" % pp_ast_as_code(x.value)
                def pp_slice(x):
                        l, u, s = x.lower or "", x.upper or "", x.step
                        if x.step:
                                return "%s:%s:%s" % tuple(iterate((l, u, s)))
                        else:
                                return "%s:%s" % tuple(iterate((l, u)))
                def pp_iterable(x):
                        l, r = { ast.List: ("[", "]"), ast.Tuple: ("(", ")"), ast.Set: ("{", "}"), ast.Dict: ("{", "}"), } [type(x)]
                        return "%s%s%s%s" % (l,
                                             ", ".join(iterate(x.elts)
                                                       if not ast_dict_p(x) else
                                                       mapcar(lambda k, v: "%s: %s" % (k, v),
                                                              x.keys,
                                                              x.values)),
                                             "," if (ast_tuple_p(x) and len(x.elts) == 1) else "",
                                             r)
                def pp_string(x):
                        q = "'''" if find("\n", x.s) else "'"
                        val = with_output_to_string(lambda s: print(x.s, file = s, end = ""))
                        return q + val + q
                def pp_num(x):     return str(x.n)
                op_print_map = dict(# binary
                                    Add = "+", Sub = "-", Mult = "*", Div = "/",
                                    Mod = "%", Pow = "**", LShift = "<<", RShift = ">>",
                                    BitOr = "|", BitXor = "^", BitAnd = "&",
                                    FloorDiv = "//",
                                    # unary
                                    Invert = "~", Not = "not", UAdd = "+", USub = "-",
                                    # bool
                                    And = "and", Or = "or",
                                    # cmpop
                                    Eq = "eq", NotEq = "not eq",
                                    Lt = "<", LtE = "<=", Gt = ">", GtE = ">=",
                                    Is = "is", IsNot = "is not",
                                    In = "in", NotIn = "not in")
                def pp_binop(x):
                        return (pp_ast_as_code(x.left) +
                                (" %s " % (op_print_map[type(x.op).__name__])) +
                                pp_ast_as_code(x.right))
                def pp_unop(x):
                        return (("%s " % (op_print_map[type(x.op).__name__])) +
                                pp_ast_as_code(x.operand))
                def pp_boolop(x):
                        return ((" %s " % (op_print_map[type(x.op).__name__])).join(iterate(x.values)))
                def pp_compare(x):
                        return rec(x.left) + "".join(" %s %s" % (op_print_map[type(op).__name__], rec(comp)) for op, comp in zip(x.ops, x.comparators))
                def pp_ifexp(x):
                        return (rec(x.body) + " if " +
                                rec(x.test) + " else " +
                                rec(x.orelse))
                def pp_module(x):
                        return "\n".join(iterate(x.body))
                def pp_args(args):
                        (args, vararg,
                         kwonlyargs, kwarg,
                         defaults,
                         kw_defaults) = mapcar(lambda a: getattr(args, a),
                                               ["args", "vararg", "kwonlyargs", "kwarg",
                                                "defaults", "kw_defaults"])
                        fixs = len(args) - len(defaults)
                        return ", ".join(mapcar(rec, args[:fixs]) +
                                         mapcar(lambda var, val: rec(var) + " = " + val,
                                                args[fixs:], iterate(defaults)) +
                                         ([("*" + vararg)] if vararg else []) +
                                         mapcar(lambda var, val: rec(var) + " = " + val,
                                                kwonlyargs, iterate(kw_defaults)) +
                                         ([("**" + rec(kwarg))] if kwarg else []))
                def pp_lambda(x):
                        args = rec(x.args)
                        return "lambda%s: %s" % (" " + args if args else "", rec(x.body))
                def pp_subprogn(body):
                        with progv({"*AST-PP-DEPTH*": symbol_value("*AST-PP-DEPTH*") + 1}):
                                return "\n".join(iterate(body)) + "\n"
                def pp_functiondef(x):
                        "XXX: ignores __annotations__"
                        return ("\n".join(indent() + "@" + rec(d) for d in x.decorator_list) +
                                ("\n" if x.decorator_list else "") +
                                indent() + "def " + x.name + "(" + rec(x.args) + "):\n" +
                                pp_subprogn(x.body))
                def pp_for(x):
                        return (indent() + "for " + rec(x.target) + " in " + rec(x.iterator) + ":\n" +
                                pp_subprogn(x.body) +
                                (indent() + "else:\n" + pp_subprogn(x.orelse)) if x.orelse else "")
                def pp_if(x):
                        def ifrec(x, firstp):
                                chainp = len(x.orelse) is 1 and typep(x.orelse[0], ast.If)
                                return (indent() + ("" if firstp else "el") + "if " + rec(x.test) + ":\n" +
                                        pp_subprogn(x.body) +
                                        ("" if not x.orelse else
                                         (ifrec(x.orelse[0], False) if chainp else
                                          (indent() + "else:\n" +
                                           pp_subprogn(x.orelse)))))
                        return ifrec(x, True)
                def pp_Expr(x):
                        return indent() + rec(x.value)
                def pp_assign(x):
                        return indent() + "%s = %s" % (", ".join(iterate(x.targets)),
                                                       rec(x.value))
                def make_trivial_pper(x):
                        return lambda y: (indent() + x +
                                          ((" " + rec(y.value))
                                           if hasattr(y, "value") and y.value else
                                           "") +
                                          "\n")
                def pp_import(x):
                        return indent() + "import " + ", ".join(iterate(x.names))
                map = { ast.arguments:   pp_args,
                        ast.comprehension: pp_comprehension,
                        ast.GeneratorExp:  pp_generatorexp,
                        ast.Module:      pp_module,
                        ast.FunctionDef: pp_functiondef,
                        ast.Lambda:      pp_lambda,
                        ast.For:         pp_for,
                        ast.If:          pp_if,
                        ast.Expr:        pp_Expr,
                        ast.Call:        pp_call,
                        ast.Attribute:   pp_attribute,
                        ast.Name:        pp_name,
                        ast.Starred:     lambda x: "*" + rec(x.value),
                        ast.arg:         pp_arg,
                        ast.alias:       pp_alias,
                        ast.keyword:     pp_keyword,
                        ast.Assign:      pp_assign,
                        ast.Subscript:   pp_subscript,
                        ast.IfExp:       pp_ifexp,
                        ast.Index:       pp_index,
                        ast.Slice:       pp_slice,
                        ast.List:        pp_iterable,
                        ast.Tuple:       pp_iterable,
                        ast.Set:         pp_iterable,
                        ast.Dict:        pp_iterable,
                        ast.Str:         pp_string,
                        ast.Num:         pp_num,
                        ast.BinOp:       pp_binop,
                        ast.UnaryOp:     pp_unop,
                        ast.BoolOp:      pp_boolop,
                        ast.Compare:     pp_compare,
                        ast.Return:      make_trivial_pper("return"),
                        ast.Raise:       make_trivial_pper("raise"),
                        ast.Pass:        make_trivial_pper("pass"),
                        ast.Break:       make_trivial_pper("break"),
                        ast.Continue:    make_trivial_pper("continue"),
                        ast.Import:      pp_import,
                        }
                def fail(x): not_implemented("pretty-printing AST node %s" % (type(x),))
                try:
                        return map.get(type(x), fail)(x) if x else ""
                except NotImplemented:
                        raise
                # except Exception as cond:
                #         error("ERROR: %s, while pretty-printing %s.  Slots: %s",
                #               cond, x, dir(x))
        return rec(x)

## symbols
symbol_attributes = [
    'referenced',
    'assigned',
    'global',
    'free',
    'parameter',
    'local',
    'imported',
    'declared_global',
    'namespace',
    ]

def pp_symbol(o):
    mesg("   symbol '" + o.get_name() + "': %s", reduce(lambda x, y: x + ((' ' + y if getattr(o, 'is_' + y)() else '')), symbol_attributes, ''))

def pp_symtable(o):
    symtab_attributes = [
        'get_id',
        'get_lineno',
        'is_optimized',
        'is_nested',
        'has_children',
        'has_exec',
        'has_import_star',
        'get_identifiers',
        'get_symbols',
        'get_children',
        ]
    fnsymtab_attributes = ['get_parameters', 'get_locals', 'get_globals', 'get_frees']
    attributes = symtab_attributes + ((fnsymtab_attributes if typep(o, symtable.Function) else []))
    mesg('   ' + o.get_type() + " symtab '" + o.get_name() + "':\n%s", reduce(lambda x, y: x + '\n        ' + y + ': ' \
         + str(getattr(o, y)()), attributes, ''))
    mapc(pp_symbol, o.get_symbols())

def totalise_symtable(symtab):
    return ascend_tree(lambda x, *xs: reduce(multiset_appendf, xs, multiset(x.get_symbols(), symtable.Symbol.get_name)),
                       symtab,
                       key=identity,
                       children=lambda x: x.get_children() or [],
                       leafp=lambda l: not l.has_children())

def sym_bound_p(s):
    return s.is_parameter or s.is_assigned
