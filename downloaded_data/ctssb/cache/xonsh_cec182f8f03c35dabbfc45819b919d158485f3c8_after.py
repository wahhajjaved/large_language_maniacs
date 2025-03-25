import os
import re
import ast
import builtins

from xonsh.platform import ON_WINDOWS
from xonsh.tools import (subexpr_from_unbalanced, get_sep,
                         check_for_partial_string, RE_STRING_START,
                         iglobpath, levenshtein)

from xonsh.completers.tools import get_filter_function

CHARACTERS_NEED_QUOTES = ' `\t\r\n${}*()"\',?&'
if ON_WINDOWS:
    CHARACTERS_NEED_QUOTES += '%'


def _path_from_partial_string(inp, pos=None):
    if pos is None:
        pos = len(inp)
    partial = inp[:pos]
    startix, endix, quote = check_for_partial_string(partial)
    _post = ""
    if startix is None:
        return None
    elif endix is None:
        string = partial[startix:]
    else:
        if endix != pos:
            _test = partial[endix:pos]
            if not any(i == ' ' for i in _test):
                _post = _test
            else:
                return None
        string = partial[startix:endix]
    end = re.sub(RE_STRING_START, '', quote)
    _string = string
    if not _string.endswith(end):
        _string = _string + end
    try:
        val = ast.literal_eval(_string)
    except SyntaxError:
        return None
    if isinstance(val, bytes):
        env = builtins.__xonsh_env__
        val = val.decode(encoding=env.get('XONSH_ENCODING'),
                         errors=env.get('XONSH_ENCODING_ERRORS'))
    return string + _post, val + _post, quote, end


def _normpath(p):
    """
    Wraps os.normpath() to avoid removing './' at the beginning
    and '/' at the end. On windows it does the same with backslashes
    """
    initial_dotslash = p.startswith(os.curdir + os.sep)
    initial_dotslash |= (ON_WINDOWS and p.startswith(os.curdir + os.altsep))
    p = p.rstrip()
    trailing_slash = p.endswith(os.sep)
    trailing_slash |= (ON_WINDOWS and p.endswith(os.altsep))
    p = os.path.normpath(p)
    if initial_dotslash and p != '.':
        p = os.path.join(os.curdir, p)
    if trailing_slash:
        p = os.path.join(p, '')

    if ON_WINDOWS and builtins.__xonsh_env__.get('FORCE_POSIX_PATHS'):
        p = p.replace(os.sep, os.altsep)

    return p


def _startswithlow(x, start, startlow=None):
    if startlow is None:
        startlow = start.lower()
    return x.startswith(start) or x.lower().startswith(startlow)


def _startswithnorm(x, start, startlow=None):
    return x.startswith(start)


def _add_env(paths, prefix):
    if prefix.startswith('$'):
        key = prefix[1:]
        paths.update({'$' + k
                      for k in builtins.__xonsh_env__
                      if get_filter_function()(k, key)})


def _add_dots(paths, prefix):
    if prefix in {'', '.'}:
        paths.update({'./', '../'})
    if prefix == '..':
        paths.add('../')


def _add_cdpaths(paths, prefix):
    """Completes current prefix using CDPATH"""
    env = builtins.__xonsh_env__
    csc = env.get('CASE_SENSITIVE_COMPLETIONS')
    for cdp in env.get('CDPATH'):
        test_glob = os.path.join(cdp, prefix) + '*'
        for s in iglobpath(test_glob, ignore_case=(not csc)):
            if os.path.isdir(s):
                paths.add(os.path.basename(s))


def _quote_to_use(x):
    single = "'"
    double = '"'
    if single in x and double not in x:
        return double
    else:
        return single


def _quote_paths(paths, start, end):
    expand_path = builtins.__xonsh_expand_path__
    out = set()
    space = ' '
    backslash = '\\'
    double_backslash = '\\\\'
    slash = get_sep()
    orig_start = start
    orig_end = end
    for s in paths:
        start = orig_start
        end = orig_end
        if (start == '' and
                (any(i in s for i in CHARACTERS_NEED_QUOTES) or
                 (backslash in s and slash != backslash))):
            start = end = _quote_to_use(s)
        if os.path.isdir(expand_path(s)):
            _tail = slash
        elif end == '':
            _tail = space
        else:
            _tail = ''
        if start != '' and 'r' not in start and backslash in s:
            start = 'r%s' % start
        s = s + _tail
        if end != '':
            if "r" not in start.lower():
                s = s.replace(backslash, double_backslash)
            if s.endswith(backslash) and not s.endswith(double_backslash):
                s += backslash
        if end in s:
            s = s.replace(end, ''.join('\\%s' % i for i in end))
        out.add(start + s + end)
    return out


def _joinpath(path):
    # convert our tuple representation back into a string representing a path
    if path is None:
        return ''
    elif len(path) == 0:
        return ''
    elif path == ('',):
        return get_sep()
    elif path[0] == '':
        return get_sep() + _normpath(os.path.join(*path))
    else:
        return _normpath(os.path.join(*path))


def _splitpath(path):
    # convert a path into an intermediate tuple representation
    # if this tuple starts with '', it means that the path was an absolute path
    path = _normpath(path)
    if path.startswith(get_sep()):
        pre = ('', )
    else:
        pre = ()
    return pre + _splitpath_helper(path, ())


def _splitpath_helper(path, sofar=()):
    folder, path = os.path.split(path)
    if path == "":
        return sofar[::-1]
    elif folder == "":
        return (sofar + (path, ))[::-1]
    else:
        return _splitpath_helper(folder, sofar + (path, ))


def subsequence_match(ref, typed, csc):
    """
    Detects whether typed is a subsequence of ref.

    Returns ``True`` if the characters in ``typed`` appear (in order) in
    ``ref``, regardless of exactly where in ``ref`` they occur.  If ``csc`` is
    ``False``, ignore the case of ``ref`` and ``typed``.

    Used in "subsequence" path completion (e.g., ``~/u/ro`` expands to
    ``~/lou/carcohl``)
    """
    if csc:
        return _subsequence_match_iter(ref, typed)
    else:
        return _subsequence_match_iter(ref.lower(), typed.lower())


def _subsequence_match_iter(ref, typed):
    if len(typed) == 0:
        return True
    elif len(ref) == 0:
        return False
    elif ref[0] == typed[0]:
        return _subsequence_match_iter(ref[1:], typed[1:])
    else:
        return _subsequence_match_iter(ref[1:], typed)


def _expand_one(sofar, nextone, csc):
    out = set()
    for i in sofar:
        _glob = os.path.join(_joinpath(i), '*') if i is not None else '*'
        for j in iglobpath(_glob):
            j = os.path.basename(j)
            if subsequence_match(j, nextone, csc):
                out.add((i or ()) + (j, ))
    return out


def complete_path(prefix, line, start, end, ctx, cdpath=True):
    """Completes based on a path name."""
    # string stuff for automatic quoting
    path_str_start = ''
    path_str_end = ''
    p = _path_from_partial_string(line, end)
    lprefix = len(prefix)
    if p is not None:
        lprefix = len(p[0])
        prefix = p[1]
        path_str_start = p[2]
        path_str_end = p[3]
    tilde = '~'
    paths = set()
    env = builtins.__xonsh_env__
    csc = env.get('CASE_SENSITIVE_COMPLETIONS')
    for s in iglobpath(prefix + '*', ignore_case=(not csc)):
        paths.add(s)
    if len(paths) == 0 and env.get('SUBSEQUENCE_PATH_COMPLETION'):
        # this block implements 'subsequence' matching, similar to fish and zsh.
        # matches are based on subsequences, not substrings.
        # e.g., ~/u/ro completes to ~/lou/carcolh
        # see above functions for details.
        p = _splitpath(os.path.expanduser(prefix))
        if len(p) != 0:
            if p[0] == '':
                basedir = ('', )
                p = p[1:]
            else:
                basedir = None
            matches_so_far = {basedir}
            for i in p:
                matches_so_far = _expand_one(matches_so_far, i, csc)
            paths |= {_joinpath(i) for i in matches_so_far}
    if len(paths) == 0 and env.get('FUZZY_PATH_COMPLETION'):
        threshold = env.get('SUGGEST_THRESHOLD')
        for s in iglobpath(os.path.dirname(prefix) + '*', ignore_case=(not csc)):
            if levenshtein(prefix, s, threshold) < threshold:
                paths.add(s)
    if tilde in prefix:
        home = os.path.expanduser(tilde)
        paths = {s.replace(home, tilde) for s in paths}
    if cdpath:
        _add_cdpaths(paths, prefix)
    paths = _quote_paths({_normpath(s) for s in paths},
                         path_str_start,
                         path_str_end)
    _add_env(paths, prefix)
    _add_dots(paths, prefix)
    return paths, lprefix


RE_UNQUOTE = re.compile("""(?:[r](?P<raw>(?P<quotes>"[^"]|'[^']|\"""|'''))|"""
                        """(?P<normal>(?P=quotes)?))"""
                        """(?P<unquoted>.+)(?:(?P=raw)|(?P=normal))$""")


def complete_dir(prefix, line, start, end, ctx, cdpath=False):
    paths, lp = complete_path(prefix, line, start, end, cdpath)
    dirs = set()
    for path in paths:
        m = RE_UNQUOTE.match(path)
        if m and os.path.isdir(m.group(3)):
            dirs.add(path)
    return dirs, lp
