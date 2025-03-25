# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re

from jinja2 import Environment
from jinja2.exceptions import TemplateSyntaxError, UndefinedError
from jinja2.utils import concat as j2_concat
from jinja2.runtime import StrictUndefined

from ansible import constants as C
from ansible.errors import AnsibleError, AnsibleFilterError, AnsibleUndefinedVariable
from ansible.plugins import filter_loader, lookup_loader
from ansible.template.safe_eval import safe_eval
from ansible.template.template import AnsibleJ2Template
from ansible.template.vars import AnsibleJ2Vars
from ansible.utils.debug import debug

from numbers import Number

__all__ = ['Templar']

# A regex for checking to see if a variable we're trying to
# expand is just a single variable name.

# Primitive Types which we don't want Jinja to convert to strings.
NON_TEMPLATED_TYPES = ( bool, Number )

JINJA2_OVERRIDE = '#jinja2:'
JINJA2_ALLOWED_OVERRIDES = frozenset(['trim_blocks', 'lstrip_blocks', 'newline_sequence', 'keep_trailing_newline'])

class Templar:
    '''
    The main class for templating, with the main entry-point of template().
    '''

    def __init__(self, loader, shared_loader_obj=None, variables=dict()):
        self._loader              = loader
        self._basedir             = loader.get_basedir()
        self._filters             = None
        self._available_variables = variables

        if shared_loader_obj:
            self._filter_loader = getattr(shared_loader_obj, 'filter_loader')
            self._lookup_loader = getattr(shared_loader_obj, 'lookup_loader')
        else:
            self._filter_loader = filter_loader
            self._lookup_loader = lookup_loader

        # flags to determine whether certain failures during templating
        # should result in fatal errors being raised
        self._fail_on_lookup_errors    = True
        self._fail_on_filter_errors    = True
        self._fail_on_undefined_errors = C.DEFAULT_UNDEFINED_VAR_BEHAVIOR

        self.environment = Environment(trim_blocks=True, undefined=StrictUndefined, extensions=self._get_extensions(), finalize=self._finalize)
        self.environment.template_class = AnsibleJ2Template

        self.SINGLE_VAR = re.compile(r"^%s\s*(\w*)\s*%s$" % (self.environment.variable_start_string, self.environment.variable_end_string))

    def _count_newlines_from_end(self, in_str):
        '''
        Counts the number of newlines at the end of a string. This is used during
        the jinja2 templating to ensure the count matches the input, since some newlines
        may be thrown away during the templating.
        '''

        i = len(in_str)
        while i > 0:
            if in_str[i-1] != '\n':
                break
            i -= 1

        return len(in_str) - i

    def _get_filters(self):
        '''
        Returns filter plugins, after loading and caching them if need be
        '''

        if self._filters is not None:
            return self._filters.copy()

        plugins = [x for x in self._filter_loader.all()]

        self._filters = dict()
        for fp in plugins:
            self._filters.update(fp.filters())

        return self._filters.copy()

    def _get_extensions(self):
        ''' 
        Return jinja2 extensions to load.

        If some extensions are set via jinja_extensions in ansible.cfg, we try
        to load them with the jinja environment.
        '''

        jinja_exts = []
        if C.DEFAULT_JINJA2_EXTENSIONS:
            # make sure the configuration directive doesn't contain spaces
            # and split extensions in an array
            jinja_exts = C.DEFAULT_JINJA2_EXTENSIONS.replace(" ", "").split(',')

        return jinja_exts

    def set_available_variables(self, variables):
        '''
        Sets the list of template variables this Templar instance will use
        to template things, so we don't have to pass them around between
        internal methods.
        '''

        assert isinstance(variables, dict)
        self._available_variables = variables.copy()

    def template(self, variable, convert_bare=False, preserve_trailing_newlines=False, fail_on_undefined=None, overrides=None):
        '''
        Templates (possibly recursively) any given data as input. If convert_bare is
        set to True, the given data will be wrapped as a jinja2 variable ('{{foo}}')
        before being sent through the template engine. 
        '''

        try:
            if convert_bare:
                variable = self._convert_bare_variable(variable)

            if isinstance(variable, basestring):
                result = variable
                if self._contains_vars(variable):

                    # Check to see if the string we are trying to render is just referencing a single
                    # var.  In this case we don't want to accidentally change the type of the variable
                    # to a string by using the jinja template renderer. We just want to pass it.
                    only_one = self.SINGLE_VAR.match(variable)
                    if only_one:
                        var_name = only_one.group(1)
                        if var_name in self._available_variables:
                            resolved_val = self._available_variables[var_name]
                            if isinstance(resolved_val, NON_TEMPLATED_TYPES):
                                return resolved_val

                    result = self._do_template(variable, preserve_trailing_newlines=preserve_trailing_newlines, fail_on_undefined=fail_on_undefined, overrides=overrides)

                    # if this looks like a dictionary or list, convert it to such using the safe_eval method
                    if (result.startswith("{") and not result.startswith(self.environment.variable_start_string)) or result.startswith("["):
                        eval_results = safe_eval(result, locals=self._available_variables, include_exceptions=True)
                        if eval_results[1] is None:
                            result = eval_results[0]
                        else:
                            # FIXME: if the safe_eval raised an error, should we do something with it?
                            pass

                return result

            elif isinstance(variable, (list, tuple)):
                return [self.template(v, convert_bare=convert_bare, preserve_trailing_newlines=preserve_trailing_newlines, fail_on_undefined=fail_on_undefined, overrides=overrides) for v in variable]
            elif isinstance(variable, dict):
                d = {}
                for (k, v) in variable.iteritems():
                    d[k] = self.template(v, convert_bare=convert_bare, preserve_trailing_newlines=preserve_trailing_newlines, fail_on_undefined=fail_on_undefined, overrides=overrides)
                return d
            else:
                return variable

        except AnsibleFilterError:
            if self._fail_on_filter_errors:
                raise
            else:
                return variable

    def _contains_vars(self, data):
        '''
        returns True if the data contains a variable pattern
        '''
        return self.environment.block_start_string in data or self.environment.variable_start_string in data

    def _convert_bare_variable(self, variable):
        '''
        Wraps a bare string, which may have an attribute portion (ie. foo.bar)
        in jinja2 variable braces so that it is evaluated properly.
        '''

        if isinstance(variable, basestring):
            first_part = variable.split(".")[0].split("[")[0]
            if first_part in self._available_variables and self.environment.variable_start_string not in variable:
                return "%s%s%s" % (self.environment.variable_start_string, variable, self.environment.variable_end_string)

        # the variable didn't meet the conditions to be converted,
        # so just return it as-is
        return variable

    def _finalize(self, thing):
        '''
        A custom finalize method for jinja2, which prevents None from being returned
        '''
        return thing if thing is not None else ''

    def _lookup(self, name, *args, **kwargs):
        instance = self._lookup_loader.get(name.lower(), loader=self._loader)

        if instance is not None:
            # safely catch run failures per #5059
            try:
                ran = instance.run(*args, variables=self._available_variables, **kwargs)
            except (AnsibleUndefinedVariable, UndefinedError):
                raise
            except Exception, e:
                if self._fail_on_lookup_errors:
                    raise
                ran = None
            if ran:
                ran = ",".join(ran)
            return ran
        else:
            raise AnsibleError("lookup plugin (%s) not found" % name)

    def _do_template(self, data, preserve_trailing_newlines=False, fail_on_undefined=None, overrides=None):

        if fail_on_undefined is None:
            fail_on_undefined = self._fail_on_undefined_errors

        try:
            # allows template header overrides to change jinja2 options.
            if overrides is None:
                myenv = self.environment.overlay()
            else:
                overrides = JINJA2_ALLOWED_OVERRIDES.intersection(set(overrides))
                myenv = self.environment.overlay(overrides)

            #FIXME: add tests
            myenv.filters.update(self._get_filters())

            try:
                t = myenv.from_string(data)
            except TemplateSyntaxError, e:
                raise AnsibleError("template error while templating string: %s" % str(e))
            except Exception, e:
                if 'recursion' in str(e):
                    raise AnsibleError("recursive loop detected in template string: %s" % data)
                else:
                    return data

            t.globals['lookup']   = self._lookup
            t.globals['finalize'] = self._finalize

            jvars = AnsibleJ2Vars(self, t.globals)

            new_context = t.new_context(jvars, shared=True)
            rf = t.root_render_func(new_context)

            try:
                res = j2_concat(rf)
            except TypeError, te:
                if 'StrictUndefined' in str(te):
                    raise AnsibleUndefinedVariable(
                        "Unable to look up a name or access an attribute in template string. " + \
                        "Make sure your variable name does not contain invalid characters like '-'."
                    )
                else:
                    debug("failing because of a type error, template data is: %s" % data)
                    raise AnsibleError("an unexpected type error occurred. Error was %s" % te)

            if preserve_trailing_newlines:
                # The low level calls above do not preserve the newline
                # characters at the end of the input data, so we use the
                # calculate the difference in newlines and append them
                # to the resulting output for parity
                res_newlines  = self._count_newlines_from_end(res)
                data_newlines = self._count_newlines_from_end(data)
                if data_newlines > res_newlines:
                    res += '\n' * (data_newlines - res_newlines)

            return res
        except (UndefinedError, AnsibleUndefinedVariable), e:
            if fail_on_undefined:
                raise
            else:
                #TODO: return warning about undefined var
                return data

