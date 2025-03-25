# -*- coding: utf-8
"""Unit tests for get_suggestions_for_exception."""
from didyoumean_internal import get_suggestions_for_exception, STAND_MODULES
import didyoumean_common_tests as common
import unittest2
import didyoumean_re as re
import warnings
import sys
import math
import os
import tempfile
from shutil import rmtree


this_is_a_global_list = []  # Value does not really matter but the type does


def func_gen(name='some_func', param='', body='pass', args=None):
    """Generate code corresponding to a function definition.

    Generate code for function definition (and eventually a call to it).
    Parameters are : name (with default), body (with default),
    parameters (with default) and arguments to call the functions with (if not
    provided or provided None, function call is not included in generated
    code).
    """
    func = "def {0}({1}):\n\t{2}\n".format(name, param, body)
    call = "" if args is None else "{0}({1})\n".format(name, args)
    return func + call


def my_generator():
    """Generate values for testing purposes.

    my_generator
    This is my generator, baby.
    """
    for i in range(5):
        yield i


class FoobarClass():
    """Dummy class for testing purposes."""

    def __init__(self):
        """Constructor."""
        self.babar = 2

    @classmethod
    def this_is_cls_mthd(cls):
        """Just a class method."""
        return 5

    def nameerror_self(self):
        """Should be self.babar."""
        return babar

    def nameerror_self2(self):
        """Should be self.this_is_cls_mthd (or FoobarClass)."""
        return this_is_cls_mthd

    @classmethod
    def nameerror_cls(cls):
        """Should be cls.this_is_cls_mthd (or FoobarClass)."""
        return this_is_cls_mthd

    def some_method(self):
        """Method for testing purposes."""
        pass

    def _some_semi_private_method(self):
        """Method for testing purposes."""
        pass

    def __some_private_method(self):
        """Method for testing purposes."""
        pass


# Logic to be able to have different tests on various version of Python
FIRST_VERSION = (0, 0)
LAST_VERSION = (10, 0)
ALL_VERSIONS = (FIRST_VERSION, LAST_VERSION)
INTERPRETERS = ['cython', 'pypy']


def from_version(version):
    """Create tuple describing a range of versions from a given version."""
    return (version, LAST_VERSION)


def up_to_version(version):
    """Create tuple describing a range of versions up to a given version."""
    return (FIRST_VERSION, version)


def version_in_range(version_range):
    """Test if current version is in a range version."""
    beg, end = version_range
    return beg <= sys.version_info < end


def interpreter_in(interpreters):
    """Test if current interpreter is in a list of interpreters."""
    is_pypy = hasattr(sys, "pypy_translation_info")
    interpreter = 'pypy' if is_pypy else 'cython'
    return interpreter in interpreters


def format_str(template, *args):
    """Format multiple string by using first arg as a template."""
    return [template.format(arg) for arg in args]


def listify(value, default):
    """Return list from value, using default value if value is None."""
    if value is None:
        value = default
    if not isinstance(value, list):
        value = [value]
    return value


def no_exception(code):
    """Helper function to run code and check it works."""
    exec(code)


def get_exception(code):
    """Helper function to run code and get what it throws."""
    try:
        no_exception(code)
    except:
        return sys.exc_info()
    assert False, "No exception thrown running\n---\n{0}\n---".format(code)


# NameError for NameErrorTests
NAMEERROR = (NameError, re.NAMENOTDEFINED_RE)
NAMEERRORBEFOREREF = (NameError, re.VARREFBEFOREASSIGN_RE)
UNKNOWN_NAMEERROR = (NameError, None)
# UnboundLocalError for UnboundLocalErrorTests
UNBOUNDLOCAL = (UnboundLocalError, re.VARREFBEFOREASSIGN_RE)
UNKNOWN_UNBOUNDLOCAL = (UnboundLocalError, None)
# TypeError for TypeErrorTests
NBARGERROR = (TypeError, re.NB_ARG_RE)
MISSINGPOSERROR = (TypeError, re.MISSING_POS_ARG_RE)
UNHASHABLE = (TypeError, re.UNHASHABLE_RE)
UNSUBSCRIBTABLE = (TypeError, re.UNSUBSCRIBTABLE_RE)
UNEXPECTEDKWARG = (TypeError, re.UNEXPECTED_KEYWORDARG_RE)
UNEXPECTEDKWARG2 = (TypeError, re.UNEXPECTED_KEYWORDARG2_RE)
UNEXPECTEDKWARG3 = (TypeError, re.UNEXPECTED_KEYWORDARG3_RE)
UNSUPPORTEDOPERAND = (TypeError, re.UNSUPPORTED_OP_RE)
OBJECTDOESNOTSUPPORT = (TypeError, re.OBJ_DOES_NOT_SUPPORT_RE)
CANNOTCONCAT = (TypeError, re.CANNOT_CONCAT_RE)
CANTCONVERT = (TypeError, re.CANT_CONVERT_RE)
MUSTBETYPENOTTYPE = (TypeError, re.MUST_BE_TYPE1_NOT_TYPE2_RE)
NOTCALLABLE = (TypeError, re.NOT_CALLABLE_RE)
DESCREXPECT = (TypeError, re.DESCRIPT_REQUIRES_TYPE_RE)
ARGNOTITERABLE = (TypeError, re.ARG_NOT_ITERABLE_RE)
MUSTCALLWITHINST = (TypeError, re.MUST_BE_CALLED_WITH_INST_RE)
OBJECTHASNOFUNC = (TypeError, re.OBJECT_HAS_NO_FUNC_RE)
UNKNOWN_TYPEERROR = (TypeError, None)
# ImportError for ImportErrorTests
NOMODULE = (ImportError, re.NOMODULE_RE)
CANNOTIMPORT = (ImportError, re.CANNOTIMPORT_RE)
UNKNOWN_IMPORTERROR = (ImportError, None)
# KeyError for KeyErrorTests
KEYERROR = (KeyError, None)
# IndexError for IndexErrorTests
OUTOFRANGE = (IndexError, re.INDEXOUTOFRANGE_RE)
# ValueError for ValueErrorTests
TOOMANYVALUES = (ValueError, re.TOO_MANY_VALUES_UNPACK_RE)
NEEDMOREVALUES = (ValueError, re.NEED_MORE_VALUES_RE)
EXPECTEDLENGTH = (ValueError, re.EXPECTED_LENGTH_RE)
MATHDOMAIN = (ValueError, re.MATH_DOMAIN_ERROR_RE)
ZEROLENERROR = (ValueError, re.ZERO_LEN_FIELD_RE)
INVALIDLITERAL = (ValueError, re.INVALID_LITERAL_RE)
TIMEDATAFORMAT = (ValueError, re.TIME_DATA_DOES_NOT_MATCH_FORMAT_RE)
# AttributeError for AttributeErrorTests
ATTRIBUTEERROR = (AttributeError, re.ATTRIBUTEERROR_RE)
MODATTRIBUTEERROR = (AttributeError, re.MODULEHASNOATTRIBUTE_RE)
UNKNOWN_ATTRIBUTEERROR = (AttributeError, None)
# SyntaxError for SyntaxErrorTests
INVALIDSYNTAX = (SyntaxError, re.INVALID_SYNTAX_RE)
INVALIDTOKEN = (SyntaxError, re.INVALID_TOKEN_RE)
NOBINDING = (SyntaxError, re.NO_BINDING_NONLOCAL_RE)
OUTSIDEFUNC = (SyntaxError, re.OUTSIDE_FUNCTION_RE)
MISSINGPARENT = (SyntaxError, re.MISSING_PARENT_RE)
INVALIDCOMP = (SyntaxError, re.INVALID_COMP_RE)
FUTUREFIRST = (SyntaxError, re.FUTURE_FIRST_RE)
FUTFEATNOTDEF = (SyntaxError, re.FUTURE_FEATURE_NOT_DEF_RE)
UNQUALIFIED_EXEC = (SyntaxError, re.UNQUALIFIED_EXEC_RE)
IMPORTSTAR = (SyntaxError, re.IMPORTSTAR_RE)
# MemoryError and OverflowError for MemoryErrorTests
MEMORYERROR = (MemoryError, '')
OVERFLOWERR = (OverflowError, re.RESULT_TOO_MANY_ITEMS_RE)
# IOError
NOFILE_IO = (common.NoFileIoError, re.NO_SUCH_FILE_RE)
NOFILE_OS = (common.NoFileOsError, re.NO_SUCH_FILE_RE)
NOTADIR_IO = (common.NotDirIoError, "^Not a directory$")
NOTADIR_OS = (common.NotDirOsError, "^Not a directory$")
ISADIR_IO = (common.IsDirIoError, "^Is a directory$")
ISADIR_OS = (common.IsDirOsError, "^Is a directory$")
DIRNOTEMPTY_OS = (OSError, "^Directory not empty$")


class GetSuggestionsTests(unittest2.TestCase):
    """Generic class to test get_suggestions_for_exception.

    Many tests do not correspond to any handled exceptions but are
    kept because it is quite convenient to have a large panel of examples.
    Also, some correspond to example where suggestions could be added, those
    are flagged with a NICE_TO_HAVE comment.
    Finally, whenever it is easily possible, the code with the suggestions
    taken into account is usually tested too to ensure that the suggestion does
    work.
    """

    def runs(self, code, version_range=None, interpreters=None):
        """Helper function to run code.

        version_range and interpreters can be provided if the test depends on
        the used environment.
        """
        interpreters = listify(interpreters, INTERPRETERS)
        if version_range is None:
            version_range = ALL_VERSIONS
        if version_in_range(version_range) and interpreter_in(interpreters):
            no_exception(code)

    def throws(self, code, error_info,
               sugg=None, version_range=None, interpreters=None):
        """Run code and check it throws and relevant suggestions are provided.

        Helper function to run code, check that it throws, what it throws and
        that the exception leads to the expected suggestions.
        version_range and interpreters can be provided if the test depends on
        the used environment.
        """
        if version_range is None:
            version_range = ALL_VERSIONS
        interpreters = listify(interpreters, INTERPRETERS)
        sugg = listify(sugg, [])
        if version_in_range(version_range) and interpreter_in(interpreters):
            error_type, error_msg = error_info
            type_caught, value, traceback = get_exception(code)
            details = "Running following code :\n---\n{0}\n---".format(code)
            self.assertTrue(isinstance(value, type_caught))
            self.assertTrue(
                issubclass(type_caught, error_type),
                "{0} ({1}) not a subclass of {2}"
                .format(type_caught, value, error_type))
            msg = next((a for a in value.args if isinstance(a, str)), '')
            if error_msg is not None:
                self.assertRegexpMatches(msg, error_msg)
            suggestions = sorted(
                get_suggestions_for_exception(value, traceback))
            self.assertEqual(suggestions, sugg, details)


class NameErrorTests(GetSuggestionsTests):
    """Class for tests related to NameError."""

    def test_local(self):
        """Should be 'foo'."""
        code = "foo = 0\n{0}"
        typo, sugg = "foob", "foo"
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "' (local)")
        self.runs(good_code)

    def test_1_arg(self):
        """Should be 'foo'."""
        typo, sugg = "foob", "foo"
        code = func_gen(param=sugg, body='{0}', args='1')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "' (local)")
        self.runs(good_code)

    def test_n_args(self):
        """Should be 'fool' or 'foot'."""
        typo, sugg1, sugg2 = "foob", "foot", "fool"
        code = func_gen(param='fool, foot', body='{0}', args='1, 2')
        bad, good1, good2 = format_str(code, typo, sugg1, sugg2)
        self.throws(bad, NAMEERROR, ["'fool' (local)", "'foot' (local)"])
        self.runs(good1)
        self.runs(good2)

    def test_builtin(self):
        """Should be 'max'."""
        typo, sugg = 'maxi', 'max'
        self.throws(typo, NAMEERROR, "'" + sugg + "' (builtin)")
        self.runs(sugg)

    def test_keyword(self):
        """Should be 'pass'."""
        typo, sugg = 'passs', 'pass'
        self.throws(typo, NAMEERROR, "'" + sugg + "' (keyword)")
        self.runs(sugg)

    def test_global(self):
        """Should be this_is_a_global_list."""
        typo, sugg = 'this_is_a_global_lis', 'this_is_a_global_list'
        # just a way to say that this_is_a_global_list is needed in globals
        this_is_a_global_list
        self.assertFalse(sugg in locals())
        self.assertTrue(sugg in globals())
        self.throws(typo, NAMEERROR, "'" + sugg + "' (global)")
        self.runs(sugg)

    def test_name(self):
        """Should be '__name__'."""
        typo, sugg = '__name_', '__name__'
        self.throws(typo, NAMEERROR, "'" + sugg + "' (global)")
        self.runs(sugg)

    def test_decorator(self):
        """Should be classmethod."""
        typo, sugg = "class_method", "classmethod"
        code = "@{0}\n" + func_gen()
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "' (builtin)")
        self.runs(good_code)

    def test_import(self):
        """Should be math."""
        code = 'import math\n{0}'
        typo, sugg = 'maths', 'math'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "' (local)")
        self.runs(good_code)

    def test_import2(self):
        """Should be my_imported_math."""
        code = 'import math as my_imported_math\n{0}'
        typo, sugg = 'my_imported_maths', 'my_imported_math'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "' (local)")
        self.runs(good_code)

    def test_imported(self):
        """Should be math.pi."""
        code = 'import math\n{0}'
        typo, sugg = 'pi', 'math.pi'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_imported_twice(self):
        """Should be math.pi."""
        code = 'import math\nimport math\n{0}'
        typo, sugg = 'pi', 'math.pi'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_not_imported(self):
        """Should be random.choice after importing random."""
        # This test assumes that `module` is not imported
        module, attr = 'random', 'choice'
        self.assertFalse(module in locals())
        self.assertFalse(module in globals())
        self.assertTrue(module in STAND_MODULES)
        bad_code = attr
        good_code = 'from {0} import {1}\n{2}'.format(module, attr, bad_code)
        self.runs(good_code)
        self.throws(
            bad_code, NAMEERROR,
            "'{0}' from {1} (not imported)".format(attr, module))

    def test_enclosing_scope(self):
        """Test that variables from enclosing scope are suggested."""
        # NICE_TO_HAVE
        typo, sugg = 'foob', 'foo'
        code = 'def f():\n\tfoo = 0\n\tdef g():\n\t\t{0}\n\tg()\nf()'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NAMEERROR)
        self.runs(good_code)

    def test_no_sugg(self):
        """No suggestion."""
        self.throws('a = ldkjhfnvdlkjhvgfdhgf', NAMEERROR)

    def test_free_var_before_assignment(self):
        """No suggestion but different error message."""
        code = 'def f():\n\tdef g():\n\t\treturn free_var' \
               '\n\tg()\n\tfree_var = 0\nf()'
        self.throws(code, NAMEERRORBEFOREREF)

    # For added/removed names, following functions with one name
    # per functions were added in the early stages of the project.
    # In the future, I'd like to have them replaced by something
    # a bit more concise using relevant data structure. In the
    # meantime, I am keeping both versions because safer is better.
    def test_removed_cmp(self):
        """Builtin cmp is removed."""
        # NICE_TO_HAVE
        code = 'cmp(1, 2)'
        version = (3, 0, 1)
        self.runs(code, up_to_version(version))
        self.throws(code, NAMEERROR, [], from_version(version))

    def test_removed_reduce(self):
        """Builtin reduce is removed - moved to functools."""
        code = 'reduce(lambda x, y: x + y, [1, 2, 3, 4, 5])'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.runs('from functools import reduce\n' + code,
                  from_version(version))
        self.throws(
            code,
            NAMEERROR,
            "'reduce' from functools (not imported)",
            from_version(version))

    def test_removed_apply(self):
        """Builtin apply is removed."""
        # NICE_TO_HAVE
        code = 'apply(sum, [[1, 2, 3]])'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(code, NAMEERROR, [], from_version(version))

    def test_removed_reload(self):
        """Builtin reload is removed.

        Moved to importlib.reload or imp.reload depending on version.
        """
        # NICE_TO_HAVE
        code = 'reload(math)'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(code, NAMEERROR, [], from_version(version))

    def test_removed_intern(self):
        """Builtin intern is removed - moved to sys."""
        code = 'intern("toto")'
        new_code = 'sys.intern("toto")'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(
            code, NAMEERROR,
            ["'iter' (builtin)", "'sys.intern'"],
            from_version(version))
        self.runs(new_code, from_version(version))

    def test_removed_execfile(self):
        """Builtin execfile is removed - use exec() and compile()."""
        # NICE_TO_HAVE
        code = 'execfile("some_filename")'
        version = (3, 0)
        # self.runs(code, up_to_version(version))
        self.throws(code, NAMEERROR, [], from_version(version))

    def test_removed_raw_input(self):
        """Builtin raw_input is removed - use input() instead."""
        code = 'i = raw_input("Prompt:")'
        version = (3, 0)
        # self.runs(code, up_to_version(version))
        self.throws(
            code, NAMEERROR, "'input' (builtin)", from_version(version))

    def test_removed_buffer(self):
        """Builtin buffer is removed - use memoryview instead."""
        # NICE_TO_HAVE
        code = 'buffer("abc")'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(code, NAMEERROR, [], from_version(version))

    def test_added_2_7(self):
        """Test for names added in 2.7."""
        version = (2, 7)
        for name in ['memoryview']:
            self.runs(name, from_version(version))
            self.throws(name, NAMEERROR, [], up_to_version(version))

    def test_removed_3_0(self):
        """Test for names removed in 3.0."""
        version = (3, 0)
        for name, suggs in {
                'StandardError': [],  # Exception
                'apply': [],
                'basestring': [],
                'buffer': [],
                'cmp': [],
                'coerce': [],
                'execfile': [],
                'file': ["'filter' (builtin)"],
                'intern': ["'iter' (builtin)", "'sys.intern'"],
                'long': [],
                'raw_input': ["'input' (builtin)"],
                'reduce': ["'reduce' from functools (not imported)"],
                'reload': [],
                'unichr': [],
                'unicode': ["'code' (local)"],
                'xrange': ["'range' (builtin)"],
                }.items():
            self.throws(name, NAMEERROR, suggs, from_version(version))
            self.runs(name, up_to_version(version))

    def test_added_3_0(self):
        """Test for names added in 3.0."""
        version = (3, 0)
        for name, suggs in {
                'ascii': [],
                'ResourceWarning': ["'FutureWarning' (builtin)"],
                '__build_class__': [],
                }.items():
            self.runs(name, from_version(version))
            self.throws(name, NAMEERROR, suggs, up_to_version(version))

    def test_added_3_3(self):
        """Test for names added in 3.3."""
        version = (3, 3)
        for name, suggs in {
                'BrokenPipeError': [],
                'ChildProcessError': [],
                'ConnectionAbortedError': [],
                'ConnectionError': ["'IndentationError' (builtin)"],
                'ConnectionRefusedError': [],
                'ConnectionResetError': [],
                'FileExistsError': [],
                'FileNotFoundError': [],
                'InterruptedError': [],
                'IsADirectoryError': [],
                'NotADirectoryError': [],
                'PermissionError': ["'ZeroDivisionError' (builtin)"],
                'ProcessLookupError': ["'LookupError' (builtin)"],
                'TimeoutError': [],
                '__loader__': [],
                }.items():
            self.runs(name, from_version(version))
            self.throws(name, NAMEERROR, suggs, up_to_version(version))

    def test_added_3_4(self):
        """Test for names added in 3.4."""
        version = (3, 4)
        for name, suggs in {
                '__spec__': [],
                }.items():
            self.runs(name, from_version(version))
            self.throws(name, NAMEERROR, suggs, up_to_version(version))

    def test_added_3_5(self):
        """Test for names added in 3.5."""
        version = (3, 5)
        for name, suggs in {
                'StopAsyncIteration': ["'StopIteration' (builtin)"],
                }.items():
            self.runs(name, from_version(version))
            self.throws(name, NAMEERROR, suggs, up_to_version(version))

    def test_import_sugg(self):
        """Should import module first."""
        module = 'collections'
        sugg = 'import {0}'.format(module)
        typo, good_code = module, sugg + '\n' + module
        self.assertFalse(module in locals())
        self.assertFalse(module in globals())
        self.assertTrue(module in STAND_MODULES)
        suggestions = (
            # module.module is suggested on Python 3.3 :-/
            ["'{0}' from {1} (not imported)".format(module, module)]
            if version_in_range(((3, 3), (3, 4))) else []) + \
            ['to {0} first'.format(sugg)]
        self.throws(typo, NAMEERROR, suggestions)
        self.runs(good_code)

    def test_attribute_hidden(self):
        """Should be math.pi but module math is hidden."""
        math  # just a way to say that math module is needed in globals
        self.assertFalse('math' in locals())
        self.assertTrue('math' in globals())
        code = 'math = ""\npi'
        self.throws(code, NAMEERROR, "'math.pi' (global hidden by local)")

    def test_self(self):
        """"Should be self.babar."""
        self.throws(
            'FoobarClass().nameerror_self()',
            NAMEERROR, "'self.babar'")

    def test_self2(self):
        """Should be self.this_is_cls_mthd."""
        self.throws(
            'FoobarClass().nameerror_self2()', NAMEERROR,
            ["'FoobarClass.this_is_cls_mthd'", "'self.this_is_cls_mthd'"])

    def test_cls(self):
        """Should be cls.this_is_cls_mthd."""
        self.throws(
            'FoobarClass().nameerror_cls()', NAMEERROR,
            ["'FoobarClass.this_is_cls_mthd'", "'cls.this_is_cls_mthd'"])

    def test_complex_numbers(self):
        """Should be 1j."""
        code = 'assert {0} ** 2 == -1'
        sugg = '1j'
        good_code, bad_code_i, bad_code_j = format_str(code, sugg, 'i', 'j')
        suggestion = "'" + sugg + "' (imaginary unit)"
        self.throws(bad_code_i, NAMEERROR, suggestion)
        self.throws(bad_code_j, NAMEERROR, suggestion)
        self.runs(good_code)

    def test_shell_commands(self):
        """Trying shell commands."""
        cmd, sugg = 'ls', 'os.listdir(os.getcwd())'
        self.throws(cmd, NAMEERROR, "'" + sugg + "'")
        self.runs(sugg)
        cmd, sugg = 'pwd', 'os.getcwd()'
        self.throws(cmd, NAMEERROR, "'" + sugg + "'")
        self.runs(sugg)
        cmd, sugg = 'cd', 'os.chdir(path)'
        self.throws(cmd, NAMEERROR, "'" + sugg + "'")
        self.runs(sugg.replace('path', 'os.getcwd()'))
        cmd = 'rm'
        sugg = "'os.remove(filename)', 'shutil.rmtree(dir)' for recursive"
        self.throws(cmd, NAMEERROR, sugg)

    def test_unmatched_msg(self):
        """Test that arbitrary strings are supported."""
        self.throws(
            'raise NameError("unmatched NAMEERROR")',
            UNKNOWN_NAMEERROR)


class UnboundLocalErrorTests(GetSuggestionsTests):
    """Class for tests related to UnboundLocalError."""

    def test_unbound_typo(self):
        """Should be foo."""
        code = 'def func():\n\tfoo = 1\n\t{0} +=1\nfunc()'
        typo, sugg = "foob", "foo"
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, UNBOUNDLOCAL, "'" + sugg + "' (local)")
        self.runs(good_code)

    def test_unbound_global(self):
        """Should be global nb."""
        # NICE_TO_HAVE
        code = 'nb = 0\ndef func():\n\t{0}nb +=1\nfunc()'
        sugg = 'global nb'
        bad_code, good_code = format_str(code, "", sugg + "\n\t")
        self.throws(bad_code, UNBOUNDLOCAL)
        self.runs(good_code)  # this is to be run afterward :-/

    def test_unmatched_msg(self):
        """Test that arbitrary strings are supported."""
        self.throws(
            'raise UnboundLocalError("unmatched UNBOUNDLOCAL")',
            UNKNOWN_UNBOUNDLOCAL)


class AttributeErrorTests(GetSuggestionsTests):
    """Class for tests related to AttributeError."""

    def test_nonetype(self):
        """In-place methods like sort returns None.

        Might also happen if the functions misses a return.
        """
        # NICE_TO_HAVE
        code = '[].sort().append(4)'
        self.throws(code, ATTRIBUTEERROR)

    def test_method(self):
        """Should be 'append'."""
        code = '[0].{0}(1)'
        typo, sugg = 'appendh', 'append'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_builtin(self):
        """Should be 'max(lst)'."""
        bad_code, good_code = '[0].max()', 'max([0])'
        self.throws(bad_code, ATTRIBUTEERROR, "'max(list)'")
        self.runs(good_code)

    def test_builtin2(self):
        """Should be 'next(gen)'."""
        code = 'my_generator().next()'
        new_code = 'next(my_generator())'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(
            code, ATTRIBUTEERROR,
            "'next(generator)'",
            from_version(version))
        self.runs(new_code)

    def test_wrongmethod(self):
        """Should be 'lst.append(1)'."""
        code = '[0].{0}(1)'
        typo, sugg = 'add', 'append'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_wrongmethod2(self):
        """Should be 'lst.extend([4, 5, 6])'."""
        code = '[0].{0}([4, 5, 6])'
        typo, sugg = 'update', 'extend'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_hidden(self):
        """Accessing wrong string object."""
        # NICE_TO_HAVE
        code = 'import string\nstring = "a"\nascii = string.ascii_letters'
        self.throws(code, ATTRIBUTEERROR)

    def test_no_sugg(self):
        """No suggestion."""
        self.throws('[1, 2, 3].ldkjhfnvdlkjhvgfdhgf', ATTRIBUTEERROR)

    def test_from_module(self):
        """Should be math.pi."""
        code = 'import math\nmath.{0}'
        typo, sugg = 'pie', 'pi'
        version = (3, 5)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'",
                    up_to_version(version))
        self.throws(bad_code, MODATTRIBUTEERROR, "'" + sugg + "'",
                    from_version(version))
        self.runs(good_code)

    def test_from_module2(self):
        """Should be math.pi."""
        code = 'import math\nm = math\nm.{0}'
        typo, sugg = 'pie', 'pi'
        version = (3, 5)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'",
                    up_to_version(version))
        self.throws(bad_code, MODATTRIBUTEERROR, "'" + sugg + "'",
                    from_version(version))
        self.runs(good_code)

    def test_from_class(self):
        """Should be 'this_is_cls_mthd'."""
        code = 'FoobarClass().{0}()'
        typo, sugg = 'this_is_cls_mth', 'this_is_cls_mthd'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_from_class2(self):
        """Should be 'this_is_cls_mthd'."""
        code = 'FoobarClass.{0}()'
        typo, sugg = 'this_is_cls_mth', 'this_is_cls_mthd'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, ATTRIBUTEERROR, "'" + sugg + "'")
        self.runs(good_code)

    def test_private_attr(self):
        """Test that 'private' members are suggested with a warning message.

        Sometimes 'private' members are suggested but it's not ideal, a
        warning must be added to the suggestion.
        """
        code = 'FoobarClass().{0}'
        method = '__some_private_method'
        method2 = '_some_semi_private_method'
        typo, sugg, sugg2 = method, '_FoobarClass' + method, method2
        bad_code, bad_sugg, good_sugg = format_str(code, typo, sugg, sugg2)
        self.throws(
            bad_code,
            ATTRIBUTEERROR,
            ["'{0}' (but it is supposed to be private)".format(sugg),
             "'{0}'".format(sugg2)])
        self.runs(bad_sugg)
        self.runs(good_sugg)

    def test_removed_has_key(self):
        """Method has_key is removed from dict."""
        code = 'dict().has_key(1)'
        new_code = '1 in dict()'
        version = (3, 0)
        self.runs(code, up_to_version(version))
        self.throws(
            code,
            ATTRIBUTEERROR,
            "'key in dict'", from_version(version))
        self.runs(new_code)

    def test_removed_xreadlines(self):
        """Method xreadlines is removed."""
        # NICE_TO_HAVE
        code = "import os\nwith open(os.path.realpath(__file__)) as f:" \
            "\n\tf.{0}"
        old, sugg1, sugg2 = 'xreadlines', 'readline', 'readlines'
        old_code, new_code1, new_code2 = format_str(code, old, sugg1, sugg2)
        version = (3, 0)
        self.runs(old_code, up_to_version(version))
        self.throws(
            old_code,
            ATTRIBUTEERROR,
            ["'" + sugg1 + "'", "'" + sugg2 + "'", "'writelines'"],
            from_version(version))
        self.runs(new_code1)
        self.runs(new_code2)

    def test_removed_function_attributes(self):
        """Some functions attributes are removed."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = func_gen() + 'some_func.{0}'
        attributes = [('func_name', '__name__', []),
                      ('func_doc', '__doc__', []),
                      ('func_defaults', '__defaults__', ["'__defaults__'"]),
                      ('func_dict', '__dict__', []),
                      ('func_closure', '__closure__', []),
                      ('func_globals', '__globals__', []),
                      ('func_code', '__code__', [])]
        for (old_att, new_att, sugg) in attributes:
            old_code, new_code = format_str(code, old_att, new_att)
            self.runs(old_code, up_to_version(version))
            self.throws(old_code, ATTRIBUTEERROR, sugg, from_version(version))
            self.runs(new_code)

    def test_removed_method_attributes(self):
        """Some methods attributes are removed."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'FoobarClass().some_method.{0}'
        attributes = [('im_func', '__func__', []),
                      ('im_self', '__self__', []),
                      ('im_class', '__self__.__class__', ["'__class__'"])]
        for (old_att, new_att, sugg) in attributes:
            old_code, new_code = format_str(code, old_att, new_att)
            self.runs(old_code, up_to_version(version))
            self.throws(old_code, ATTRIBUTEERROR, sugg, from_version(version))
            self.runs(new_code)

    def test_join(self):
        """Test what happens when join is used incorrectly.

        This can be frustrating to call join on an iterable instead of a
        string, a suggestion could be nice.
        """
        # NICE_TO_HAVE
        code = "['a', 'b'].join('-')"
        self.throws(code, ATTRIBUTEERROR)

    def test_set_dict_comprehension(self):
        """{} creates a dict and not an empty set leading to errors."""
        # NICE_TO_HAVE
        version = (2, 7)
        for method in set(dir(set)) - set(dir(dict)):
            if not method.startswith('__'):  # boring suggestions
                code = "a = {0}\na." + method
                typo, dict1, dict2, sugg, set1 = format_str(
                    code, "{}", "dict()", "{0: 0}", "set()", "{0}")
                self.throws(typo, ATTRIBUTEERROR)
                self.throws(dict1, ATTRIBUTEERROR)
                self.throws(dict2, ATTRIBUTEERROR)
                self.runs(sugg)
                self.throws(set1, INVALIDSYNTAX, [], up_to_version(version))
                self.runs(set1, from_version(version))

    def test_unmatched_msg(self):
        """Test that arbitrary strings are supported."""
        self.throws(
            'raise AttributeError("unmatched ATTRIBUTEERROR")',
            UNKNOWN_ATTRIBUTEERROR)

    # TODO: Add sugg for situation where self/cls is the missing parameter


class TypeErrorTests(GetSuggestionsTests):
    """Class for tests related to TypeError."""

    def test_unhashable(self):
        """Test that other errors do not crash."""
        self.throws('dict()[list()] = 1', UNHASHABLE)

    def test_not_sub(self):
        """Should be function call, not [] operator."""
        typo, sugg = '[2]', '(2)'
        code = func_gen(param='a') + 'some_func{0}'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, UNSUBSCRIBTABLE, "'function(value)'")
        self.runs(good_code)

    def test_method_called_on_class(self):
        """Test where a method is called on a class and not an instance.

        Forgetting parenthesis makes the difference between using an
        instance and using a type.
        """
        # NICE_TO_HAVE
        wrong_type = (DESCREXPECT, MUSTCALLWITHINST, NBARGERROR)
        not_iterable = (ARGNOTITERABLE, ARGNOTITERABLE, ARGNOTITERABLE)
        version = (3, 0)
        for code, (err_cy, err_pyp, err_pyp3) in [
                ('set{0}.add(0)', wrong_type),
                ('list{0}.append(0)', wrong_type),
                ('0 in list{0}', not_iterable)]:
            bad_code, good_code = format_str(code, '', '()')
            self.runs(good_code)
            self.throws(bad_code, err_cy, [], ALL_VERSIONS, 'cython')
            self.throws(bad_code, err_pyp, [], up_to_version(version), 'pypy')
            self.throws(bad_code, err_pyp3, [], from_version(version), 'pypy')

    def test_set_operations(self):
        """+, +=, etc doesn't work on sets. A suggestion would be nice."""
        # NICE_TO_HAVE
        typo1 = 'set() + set()'
        typo2 = 's = set()\ns += set()'
        code1 = 'set() | set()'
        code2 = 'set().union(set())'
        code3 = 'set().update(set())'
        self.throws(typo1, UNSUPPORTEDOPERAND)
        self.throws(typo2, UNSUPPORTEDOPERAND)
        self.runs(code1)
        self.runs(code2)
        self.runs(code3)

    def test_dict_operations(self):
        """+, +=, etc doesn't work on dicts. A suggestion would be nice."""
        # NICE_TO_HAVE
        typo1 = 'dict() + dict()'
        typo2 = 'd = dict()\nd += dict()'
        typo3 = 'dict() & dict()'
        self.throws(typo1, UNSUPPORTEDOPERAND)
        self.throws(typo2, UNSUPPORTEDOPERAND)
        self.throws(typo3, UNSUPPORTEDOPERAND)
        code1 = 'dict().update(dict())'
        self.runs(code1)

    def test_len_on_iterable(self):
        """len() can't be called on iterable (weird but understandable)."""
        code = 'len(my_generator())'
        sugg = 'len(list(my_generator()))'
        self.throws(code, OBJECTHASNOFUNC)
        self.runs(sugg)

    def test_nb_args(self):
        """Should have 1 arg."""
        typo, sugg = '1, 2', '1'
        code = func_gen(param='a', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR)
        self.runs(good_code)

    def test_nb_args1(self):
        """Should have 0 args."""
        typo, sugg = '1', ''
        code = func_gen(param='', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR)
        self.runs(good_code)

    def test_nb_args2(self):
        """Should have 1 arg."""
        typo, sugg = '', '1'
        version = (3, 3)
        code = func_gen(param='a', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR, [], up_to_version(version))
        self.throws(bad_code, MISSINGPOSERROR, [], from_version(version))
        self.runs(good_code)

    def test_nb_args3(self):
        """Should have 3 args."""
        typo, sugg = '1', '1, 2, 3'
        version = (3, 3)
        code = func_gen(param='so, much, args', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR, [], up_to_version(version))
        self.throws(bad_code, MISSINGPOSERROR, [], from_version(version))
        self.runs(good_code)

    def test_nb_args4(self):
        """Should have 3 args."""
        typo, sugg = '', '1, 2, 3'
        version = (3, 3)
        code = func_gen(param='so, much, args', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR, [], up_to_version(version))
        self.throws(bad_code, MISSINGPOSERROR, [], from_version(version))
        self.runs(good_code)

    def test_nb_args5(self):
        """Should have 3 args."""
        typo, sugg = '1, 2', '1, 2, 3'
        version = (3, 3)
        code = func_gen(param='so, much, args', args='{0}')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NBARGERROR, [], up_to_version(version))
        self.throws(bad_code, MISSINGPOSERROR, [], from_version(version))
        self.runs(good_code)

    def test_keyword_args(self):
        """Should be param 'babar' not 'a' but it's hard to guess."""
        typo, sugg = 'a', 'babar'
        code = func_gen(param=sugg, args='{0}=1')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, UNEXPECTEDKWARG)
        self.runs(good_code)

    def test_keyword_args2(self):
        """Should be param 'abcdef' not 'abcdf'."""
        typo, sugg = 'abcdf', 'abcdef'
        code = func_gen(param=sugg, args='{0}=1')
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, UNEXPECTEDKWARG, "'" + sugg + "'")
        self.runs(good_code)

    def test_keyword_builtin(self):
        """A few builtins (like int()) have a different error message."""
        # NICE_TO_HAVE
        # 'max', 'input', 'len', 'abs', 'all', etc have a specific error
        # message and are not relevant here
        for builtin in ['int', 'float', 'bool', 'complex']:
            code = builtin + '(this_doesnt_exist=2)'
            self.throws(code, UNEXPECTEDKWARG2, [], ALL_VERSIONS, 'cython')
            self.throws(code, UNEXPECTEDKWARG, [], ALL_VERSIONS, 'pypy')

    def test_keyword_builtin_print(self):
        """Builtin "print" has a different error message."""
        # It would be NICE_TO_HAVE suggestions on keyword arguments
        v3 = (3, 0)
        code = "c = 'string'\nb = print(c, end_='toto')"
        self.throws(code, INVALIDSYNTAX, [], up_to_version(v3))
        self.throws(code, UNEXPECTEDKWARG2, [], from_version(v3), 'cython')
        self.throws(code, UNEXPECTEDKWARG3, [], from_version(v3), 'pypy')

    def test_no_implicit_str_conv(self):
        """Trying to concatenate a non-string value to a string."""
        # NICE_TO_HAVE
        code = '{0} + " things"'
        typo, sugg = '12', 'str(12)'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, UNSUPPORTEDOPERAND)
        self.runs(good_code)

    def test_no_implicit_str_conv2(self):
        """Trying to concatenate a non-string value to a string."""
        # NICE_TO_HAVE
        code = '"things " + {0}'
        typo, sugg = '12', 'str(12)'
        bad_code, good_code = format_str(code, typo, sugg)
        version = (3, 0)
        version2 = (3, 6)
        self.throws(
            bad_code, CANNOTCONCAT, [], up_to_version(version), 'cython')
        self.throws(
            bad_code, CANTCONVERT, [], (version, version2), 'cython')
        self.throws(
            bad_code, MUSTBETYPENOTTYPE, [], from_version(version2), 'cython')
        self.throws(
            bad_code, UNSUPPORTEDOPERAND, [], ALL_VERSIONS, 'pypy')
        self.runs(good_code)

    def test_assignment_to_range(self):
        """Trying to assign to range works on list, not on range."""
        # NICE_TO_HAVE
        code = '{0}[2] = 1'
        typo, sugg = 'range(4)', 'list(range(4))'
        version = (3, 0)
        bad_code, good_code = format_str(code, typo, sugg)
        self.runs(bad_code, up_to_version(version))
        self.throws(bad_code, OBJECTDOESNOTSUPPORT, [], from_version(version))
        self.runs(good_code)

    def test_not_callable(self):
        """Sometimes, one uses parenthesis instead of brackets."""
        typo, getitem = '(0)', '[0]'
        for ex, sugg in {
            '[0]': "'list[value]'",
            '{0: 0}': "'dict[value]'",
            '"a"': "'str[value]'",
        }.items():
            self.throws(ex + typo, NOTCALLABLE, sugg)
            self.runs(ex + getitem)
        for ex in ['1', 'set()']:
            self.throws(ex + typo, NOTCALLABLE)

    def test_unmatched_msg(self):
        """Test that arbitrary strings are supported."""
        self.throws(
            'raise TypeError("unmatched TYPEERROR")',
            UNKNOWN_TYPEERROR)


class ImportErrorTests(GetSuggestionsTests):
    """Class for tests related to ImportError."""

    def test_no_module_no_sugg(self):
        """No suggestion."""
        self.throws('import fqslkdfjslkqdjfqsd', NOMODULE)

    def test_no_module(self):
        """Should be 'math'."""
        code = 'import {0}'
        typo, sugg = 'maths', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_no_module2(self):
        """Should be 'math'."""
        code = 'from {0} import pi'
        typo, sugg = 'maths', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_no_module3(self):
        """Should be 'math'."""
        code = 'import {0} as my_imported_math'
        typo, sugg = 'maths', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_no_module4(self):
        """Should be 'math'."""
        code = 'from {0} import pi as three_something'
        typo, sugg = 'maths', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_no_module5(self):
        """Should be 'math'."""
        code = '__import__("{0}")'
        typo, sugg = 'maths', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_import_future_nomodule(self):
        """Should be '__future__'."""
        code = 'import {0}'
        typo, sugg = '__future_', '__future__'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, NOMODULE, "'" + sugg + "'")
        self.runs(good_code)

    def test_no_name_no_sugg(self):
        """No suggestion."""
        self.throws('from math import fsfsdfdjlkf', CANNOTIMPORT)

    def test_wrong_import(self):
        """Should be 'math'."""
        code = 'from {0} import pi'
        typo, sugg = 'itertools', 'math'
        self.assertTrue(sugg in STAND_MODULES)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, CANNOTIMPORT, "'" + good_code + "'")
        self.runs(good_code)

    def test_typo_in_method(self):
        """Should be 'pi'."""
        code = 'from math import {0}'
        typo, sugg = 'pie', 'pi'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, CANNOTIMPORT, "'" + sugg + "'")
        self.runs(good_code)

    def test_typo_in_method2(self):
        """Should be 'pi'."""
        code = 'from math import e, {0}, log'
        typo, sugg = 'pie', 'pi'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, CANNOTIMPORT, "'" + sugg + "'")
        self.runs(good_code)

    def test_typo_in_method3(self):
        """Should be 'pi'."""
        code = 'from math import {0} as three_something'
        typo, sugg = 'pie', 'pi'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, CANNOTIMPORT, "'" + sugg + "'")
        self.runs(good_code)

    def test_unmatched_msg(self):
        """Test that arbitrary strings are supported."""
        self.throws(
            'raise ImportError("unmatched IMPORTERROR")',
            UNKNOWN_IMPORTERROR)

    def test_module_removed(self):
        """Sometimes, modules are deleted/moved/renamed."""
        # NICE_TO_HAVE
        version1 = (2, 7)  # result for 2.6 seems to vary
        version2 = (3, 0)
        code = 'import {0}'
        lower, upper = format_str(code, 'tkinter', 'Tkinter')
        self.throws(lower, NOMODULE, [], (version1, version2))
        self.throws(upper, NOMODULE, [], from_version(version2))


class LookupErrorTests(GetSuggestionsTests):
    """Class for tests related to LookupError."""


class KeyErrorTests(LookupErrorTests):
    """Class for tests related to KeyError."""

    def test_no_sugg(self):
        """No suggestion."""
        self.throws('dict()["ffdsqmjklfqsd"]', KEYERROR)


class IndexErrorTests(LookupErrorTests):
    """Class for tests related to IndexError."""

    def test_no_sugg(self):
        """No suggestion."""
        self.throws('list()[2]', OUTOFRANGE)


class SyntaxErrorTests(GetSuggestionsTests):
    """Class for tests related to SyntaxError."""

    def test_no_error(self):
        """No error."""
        self.runs("1 + 2 == 2")

    def test_yield_return_out_of_func(self):
        """yield/return needs to be in functions."""
        sugg = "to indent it"
        self.throws("yield 1", OUTSIDEFUNC, sugg)
        self.throws("return 1", OUTSIDEFUNC, ["'sys.exit([arg])'", sugg])

    def test_print(self):
        """print is a functions now and needs parenthesis."""
        # NICE_TO_HAVE
        code, new_code = 'print ""', 'print("")'
        version = (3, 0)
        version2 = (3, 4)
        self.runs(code, up_to_version(version))
        self.throws(code, INVALIDSYNTAX, [], (version, version2))
        self.throws(code, INVALIDSYNTAX, [], from_version(version2))
        self.runs(new_code)

    def test_exec(self):
        """exec is a functions now and needs parenthesis."""
        # NICE_TO_HAVE
        code, new_code = 'exec "1"', 'exec("1")'
        version = (3, 0)
        version2 = (3, 4)
        self.runs(code, up_to_version(version))
        self.throws(code, INVALIDSYNTAX, [], (version, version2))
        self.throws(code, INVALIDSYNTAX, [], from_version(version2))
        self.runs(new_code)

    def test_old_comparison(self):
        """<> comparison is removed, != always works."""
        code = '1 {0} 2'
        old, new = '<>', '!='
        version = (3, 0)
        old_code, new_code = format_str(code, old, new)
        self.runs(old_code, up_to_version(version))
        self.throws(
            old_code,
            INVALIDCOMP,
            "'!='",
            from_version(version),
            'pypy')
        self.throws(
            old_code,
            INVALIDSYNTAX,
            "'!='",
            from_version(version),
            'cython')
        self.runs(new_code)

    def test_missing_colon(self):
        """Missing colon is a classic mistake."""
        # NICE_TO_HAVE
        code = "if True{0}\n\tpass"
        bad_code, good_code = format_str(code, "", ":")
        self.throws(bad_code, INVALIDSYNTAX)
        self.runs(good_code)

    def test_simple_equal(self):
        """'=' for comparison is a classic mistake."""
        # NICE_TO_HAVE
        code = "if 2 {0} 3:\n\tpass"
        bad_code, good_code = format_str(code, "=", "==")
        self.throws(bad_code, INVALIDSYNTAX)
        self.runs(good_code)

    def test_keyword_as_identifier(self):
        """Using a keyword as a variable name."""
        # NICE_TO_HAVE
        code = '{0} = 1'
        bad_code, good_code = format_str(code, "from", "from_")
        self.throws(bad_code, INVALIDSYNTAX)
        self.runs(good_code)

    def test_increment(self):
        """Trying to use '++' or '--'."""
        # NICE_TO_HAVE
        code = 'a = 0\na{0}'
        for op in ('-', '+'):
            typo, sugg = 2 * op, op + '=1'
            bad_code, good_code = format_str(code, typo, sugg)
            self.throws(bad_code, INVALIDSYNTAX)
            self.runs(good_code)

    def test_wrong_bool_operator(self):
        """Trying to use '&&' or '||'."""
        # NICE_TO_HAVE
        code = 'True {0} False'
        for typo, sugg in (('&&', 'and'), ('||', 'or')):
            bad_code, good_code = format_str(code, typo, sugg)
            self.throws(bad_code, INVALIDSYNTAX)
            self.runs(good_code)

    def test_import_future_not_first(self):
        """Test what happens when import from __future__ is not first."""
        code = 'a = 8/7\nfrom __future__ import division'
        self.throws(code, FUTUREFIRST)

    def test_import_future_not_def(self):
        """Should be 'division'."""
        code = 'from __future__ import {0}'
        typo, sugg = 'divisio', 'division'
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(bad_code, FUTFEATNOTDEF, "'" + sugg + "'")
        self.runs(good_code)

    def test_unqualified_exec(self):
        """Exec in nested functions."""
        # NICE_TO_HAVE
        version = (3, 0)
        codes = [
            "def func1():\n\tbar='1'\n\tdef func2():"
            "\n\t\texec(bar)\n\tfunc2()\nfunc1()",
            "def func1():\n\texec('1')\n\tdef func2():"
            "\n\t\tTrue",
        ]
        for code in codes:
            self.throws(code, UNQUALIFIED_EXEC, [], up_to_version(version))
            self.runs(code, from_version(version))

    def test_import_star(self):
        """'import *' in nested functions."""
        # NICE_TO_HAVE
        codes = [
            "def func1():\n\tbar='1'\n\tdef func2():"
            "\n\t\tfrom math import *\n\t\tTrue\n\tfunc2()\nfunc1()",
            "def func1():\n\tfrom math import *"
            "\n\tdef func2():\n\t\tTrue",
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=SyntaxWarning)
            for code in codes:
                self.throws(code, IMPORTSTAR, [])

    def test_unpack(self):
        """Extended tuple unpacking does not work prior to Python 3."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'a, *b = (1, 2, 3)'
        self.throws(code, INVALIDSYNTAX, [], up_to_version(version))
        self.runs(code, from_version(version))

    def test_unpack2(self):
        """Unpacking in function arguments was supported up to Python 3."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'def addpoints((x1, y1), (x2, y2)):\n\tpass'
        self.runs(code, up_to_version(version))
        self.throws(code, INVALIDSYNTAX, [], from_version(version))

    def test_nonlocal(self):
        """nonlocal keyword is added in Python 3."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'def func():\n\tfoo = 1\n\tdef nested():\n\t\tnonlocal foo'
        self.runs(code, from_version(version))
        self.throws(code, INVALIDSYNTAX, [], up_to_version(version))

    def test_nonlocal2(self):
        """nonlocal must be used only when binding exists."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'def func():\n\tdef nested():\n\t\tnonlocal foo'
        self.throws(code, NOBINDING, [], from_version(version))
        self.throws(code, INVALIDSYNTAX, [], up_to_version(version))

    def test_nonlocal3(self):
        """nonlocal must be used only when binding to non-global exists."""
        # NICE_TO_HAVE
        version = (3, 0)
        code = 'foo = 1\ndef func():\n\tdef nested():\n\t\tnonlocal foo'
        self.throws(code, NOBINDING, [], from_version(version))
        self.throws(code, INVALIDSYNTAX, [], up_to_version(version))

    def test_octal_literal(self):
        """Syntax for octal liberals has changed."""
        # NICE_TO_HAVE
        version = (3, 0)
        bad, good = '0720', '0o720'
        self.runs(good)
        self.runs(bad, up_to_version(version))
        self.throws(bad, INVALIDTOKEN, [], from_version(version))

    def test_extended_unpacking(self):
        """Extended iterable unpacking is added with Python 3."""
        version = (3, 0)
        code = '(a, *rest, b) = range(5)'
        self.throws(bad, INVALIDSYNTAX, [], up_to_version(version))
        self.runs(code, from_version(version))

    def test_ellipsis(self):
        """Triple dot (...) aka Ellipsis can be used anywhere in Python 3."""
        version = (3, 0)
        code = '...'
        self.throws(bad, INVALIDSYNTAX, [], up_to_version(version))
        self.runs(code, from_version(version))


class MemoryErrorTests(GetSuggestionsTests):
    """Class for tests related to MemoryError."""

    def test_out_of_memory(self):
        """Test what happens in case of MemoryError."""
        code = '[0] * 999999999999999'
        self.throws(code, MEMORYERROR)

    def test_out_of_memory_range(self):
        """Test what happens in case of MemoryError."""
        code = '{0}(999999999999999)'
        typo, sugg = 'range', 'xrange'
        bad_code, good_code = format_str(code, typo, sugg)
        self.runs(bad_code, ALL_VERSIONS, 'pypy')
        version = (2, 7)
        version2 = (3, 0)
        self.throws(
            bad_code,
            OVERFLOWERR, "'" + sugg + "'",
            up_to_version(version),
            'cython')
        self.throws(
            bad_code,
            MEMORYERROR, "'" + sugg + "'",
            (version, version2),
            'cython')
        self.runs(good_code, up_to_version(version2), 'cython')
        self.runs(bad_code, from_version(version2), 'cython')


class ValueErrorTests(GetSuggestionsTests):
    """Class for tests related to ValueError."""

    def test_too_many_values(self):
        """Unpack 4 values in 3 variables."""
        code = 'a, b, c = [1, 2, 3, 4]'
        version = (3, 0)
        self.throws(code, EXPECTEDLENGTH, [], up_to_version(version), 'pypy')
        self.throws(code, TOOMANYVALUES, [], from_version(version), 'pypy')
        self.throws(code, TOOMANYVALUES, [], ALL_VERSIONS, 'cython')

    def test_not_enough_values(self):
        """Unpack 2 values in 3 variables."""
        code = 'a, b, c = [1, 2]'
        version = (3, 0)
        self.throws(code, EXPECTEDLENGTH, [], up_to_version(version), 'pypy')
        self.throws(code, NEEDMOREVALUES, [], from_version(version), 'pypy')
        self.throws(code, NEEDMOREVALUES, [], ALL_VERSIONS, 'cython')

    def test_conversion_fails(self):
        """Conversion fails."""
        self.throws('int("toto")', INVALIDLITERAL)

    def test_math_domain(self):
        """Math function used out of its domain."""
        code = 'import math\nlg = math.log(-1)'
        self.throws(code, MATHDOMAIN)

    def test_zero_len_field_in_format(self):
        """Format {} is not valid before Python 2.7."""
        code = '"{0}".format(0)'
        old, new = '{0}', '{}'
        old_code, new_code = format_str(code, old, new)
        version = (2, 7)
        self.runs(old_code)
        self.throws(new_code, ZEROLENERROR, '{0}', up_to_version(version))
        self.runs(new_code, from_version(version))

    def test_timedata_does_not_match(self):
        """Strptime arguments are in wrong order."""
        code = 'import datetime\ndatetime.datetime.strptime({0}, {1})'
        timedata, timeformat = '"30 Nov 00"', '"%d %b %y"'
        good_code = code.format(*(timedata, timeformat))
        bad_code = code.format(*(timeformat, timedata))
        self.runs(good_code)
        self.throws(bad_code, TIMEDATAFORMAT,
                    ['to swap value and format parameters'])


class IOErrorTests(GetSuggestionsTests):
    """Class for tests related to IOError."""

    def test_no_such_file(self):
        """File does not exist."""
        code = 'with open("doesnotexist") as f:\n\tpass'
        self.throws(code, NOFILE_IO)

    def test_no_such_file2(self):
        """File does not exist."""
        code = 'os.listdir("doesnotexist")'
        self.throws(code, NOFILE_OS)

    def test_no_such_file_user(self):
        """Suggestion when one needs to expanduser."""
        code = 'os.listdir("{0}")'
        typo, sugg = "~", os.path.expanduser("~")
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(
            bad_code, NOFILE_OS,
            "'" + sugg + "' (calling os.path.expanduser)")
        self.runs(good_code)

    def test_no_such_file_vars(self):
        """Suggestion when one needs to expandvars."""
        code = 'os.listdir("{0}")'
        key = 'HOME'
        typo, sugg = "$" + key, os.path.expanduser("~")
        original_home = os.environ.get('HOME')
        os.environ[key] = sugg
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(
            bad_code, NOFILE_OS,
            "'" + sugg + "' (calling os.path.expandvars)")
        self.runs(good_code)
        if original_home is None:
            del os.environ[key]
        else:
            os.environ[key] = original_home

    def create_tmp_dir_with_files(self, filelist):
        """Create a temporary directory with files in it."""
        tmpdir = tempfile.mkdtemp()
        absfiles = [os.path.join(tmpdir, f) for f in filelist]
        for name in absfiles:
            open(name, 'a').close()
        return (tmpdir, absfiles)

    def test_is_dir_empty(self):
        """Suggestion when file is an empty directory."""
        # Create empty temp dir
        tmpdir, _ = self.create_tmp_dir_with_files([])
        code = 'with open("{0}") as f:\n\tpass'
        bad_code, _ = format_str(code, tmpdir, "TODO")
        self.throws(
            bad_code, ISADIR_IO, "to add content to {0} first".format(tmpdir))
        rmtree(tmpdir)

    def test_is_dir_small(self):
        """Suggestion when file is directory with a few files."""
        # Create temp dir with a few files
        nb_files = 3
        files = sorted([str(i) + ".txt" for i in range(nb_files)])
        tmpdir, absfiles = self.create_tmp_dir_with_files(files)
        code = 'with open("{0}") as f:\n\tpass'
        bad_code, good_code = format_str(code, tmpdir, absfiles[0])
        self.throws(
            bad_code, ISADIR_IO,
            "any of the 3 files in directory ('0.txt', '1.txt', '2.txt')")
        self.runs(good_code)
        rmtree(tmpdir)

    def test_is_dir_big(self):
        """Suggestion when file is directory with many files."""
        # Create temp dir with many files
        tmpdir = tempfile.mkdtemp()
        nb_files = 30
        files = sorted([str(i) + ".txt" for i in range(nb_files)])
        tmpdir, absfiles = self.create_tmp_dir_with_files(files)
        code = 'with open("{0}") as f:\n\tpass'
        bad_code, good_code = format_str(code, tmpdir, absfiles[0])
        self.throws(
            bad_code, ISADIR_IO,
            "any of the 30 files in directory "
            "('0.txt', '1.txt', '10.txt', '11.txt', etc)")
        self.runs(good_code)
        rmtree(tmpdir)

    def test_is_not_dir(self):
        """Suggestion when file is not a directory."""
        code = 'with open("{0}") as f:\n\tpass'
        code = 'os.listdir("{0}")'
        typo, sugg = __file__, os.path.dirname(__file__)
        bad_code, good_code = format_str(code, typo, sugg)
        self.throws(
            bad_code, NOTADIR_OS,
            "'" + sugg + "' (calling os.path.dirname)")
        self.runs(good_code)

    def test_dir_is_not_empty(self):
        """Suggestion when directory is not empty."""
        # NICE_TO_HAVE
        nb_files = 3
        files = sorted([str(i) + ".txt" for i in range(nb_files)])
        tmpdir, _ = self.create_tmp_dir_with_files(files)
        self.throws('os.rmdir("{0}")'.format(tmpdir), DIRNOTEMPTY_OS)
        rmtree(tmpdir)  # this should be the suggestion


class AnyErrorTests(GetSuggestionsTests):
    """Class for tests not related to an error type in particular."""

    def test_wrong_except(self):
        """Test where except is badly used and thus does not catch.

        Common mistake : "except Exc1, Exc2" doesn't catch Exc2.
        Adding parenthesis solves the issue.
        """
        # NICE_TO_HAVE
        version = (3, 0)
        raised_exc, other_exc = KeyError, TypeError
        raised, other = raised_exc.__name__, other_exc.__name__
        code = "try:\n\traise {0}()\nexcept {{0}}:\n\tpass".format(raised)
        typo = "{0}, {1}".format(other, raised)
        sugg = "({0})".format(typo)
        bad1, bad2, good1, good2 = format_str(code, typo, other, sugg, raised)
        self.throws(bad1, (raised_exc, None), [], up_to_version(version))
        self.throws(bad1, INVALIDSYNTAX, [], from_version(version))
        self.throws(bad2, (raised_exc, None))
        self.runs(good1)
        self.runs(good2)


if __name__ == '__main__':
    print(sys.version_info)
    unittest2.main()
