"""
Dump vars in Jinja2-based template files.

:copyright: (c) 2012 Masatake YAMATO <yamato @ redhat.com>
:copyright: (c) 2012 - 2015 Satoru SATOH <ssato @ redhat.com>
:license: BSD-3
"""
from __future__ import absolute_import

import jinja2.meta
import jinja2.compiler
import jinja2.visitor


from functools import reduce as foldl
from operator import concat as listplus

import jinja2_cli.render
import jinja2_cli.utils


class AttrTrackingCodeGenerator(jinja2.compiler.CodeGenerator):
    """
    Code generator with tracking node attributes.
    """

    def __init__(self, environment, target_var):
        jinja2.compiler.CodeGenerator.__init__(self, environment,
                                               '<introspection>',
                                               '<introspection>')
        self.target_var = target_var
        self.attrs = []

    def pull_dependencies(self, nodes):
        visitor = AttrVisitor(self.target_var, self.attrs)
        for node in nodes:
            visitor.visit(node)


class AttrVisitor(jinja2.visitor.NodeVisitor):
    """
    Node attribute visitor.
    """

    def __init__(self, target_var, attrs):
        self.target_var = target_var
        self.attrs = attrs
        self.astack = []
        jinja2.visitor.NodeVisitor.__init__(self)

    def visit_Name(self, node):
        store = False
        if self.astack == []:
            store = True
        if node.name == self.target_var:
            self.astack.append(node.name)
            if store:
                self.attrs.append(self.astack)
                self.astack = []

    def visit_Getattr(self, node):
        store = False
        if self.astack == []:
            store = True
        self.astack.append(node.attr)
        self.visit(node.node)
        if store:
            if self.astack[-1] == self.target_var:
                self.astack.reverse()
                self.attrs.append(self.astack)
            self.astack = []


def find_attrs(ast, target_var):
    """
    Attribute finder.

    :param ast: AST of parsed template
    :param target_var: Target variable
    """
    tracker = AttrTrackingCodeGenerator(ast.environment, target_var)
    tracker.visit(ast)

    return tracker.attrs


def get_ast(filepath, paths):
    """Parse template (`filepath`) and return an abstract syntax tree.

    see also: http://jinja.pocoo.org/docs/api/#the-meta-api

    :param filepath: (Base) filepath of template file
    :param paths: Template search paths
    """
    try:
        return jinja2_cli.render.tmpl_env(paths).parse(open(filepath).read())
    except:
        return None


def find_templates(filepath, paths, acc=[]):
    """
    Find and return template paths including ones refered in given template
    recursively.

    :param filepath: Maybe base filepath of template file
    :param paths: Template search paths
    """
    filepath = jinja2_cli.render.template_path(filepath, paths)
    ast = get_ast(filepath, paths)

    if ast:
        if filepath not in acc:
            acc.append(filepath)  # Add self.

        ref_templates = [jinja2_cli.render.template_path(f, paths) for f in
                         jinja2.meta.find_referenced_templates(ast) if f]

        for f in ref_templates:
            if f not in acc:
                acc.append(f)

            acc += [t for t in find_templates(f, paths, acc) if t not in acc]

    return acc


def find_vars_0(filepath, paths):
    """
    Find and return variables in given template.

    see also: http://jinja.pocoo.org/docs/api/#the-meta-api

    :param filepath: (Base) filepath of template file
    :param paths: Template search paths

    :return:  [(template_abs_path, [var])]
    """
    filepath = jinja2_cli.render.template_path(filepath, paths)

    def find_undecls_0(fpath, paths=paths):
        ast_ = get_ast(fpath, paths)
        if ast_:
            return [find_attrs(ast_, v) for v in
                    jinja2.meta.find_undeclared_variables(ast_)]
        else:
            return []

    return [(f, find_undecls_0(f)) for f in find_templates(filepath, paths)]


def find_vars(filepath, paths):
    return jinja2_cli.utils.uniq(foldl(listplus,
                                       (vs[1] for vs in find_vars_0(filepath,
                                                                    paths)),
                                       []))


def dumpvars(template, output=None, paths=[]):
    vs = find_vars(template, paths)
    vars = ''.join('\n'.join(v) + '\n' for v in
                   sorted(['.'.join(e) for e in elt] for elt in vs))
    jinja2_cli.utils.write_to_output(output, vars)

# vim:sw=4:ts=4:et:
