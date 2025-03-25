# Copyright (C) 2007 Alex Drummond <a.d.drummond@gmail.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor,
# Boston, MA  02110-1301, USA.

#
# Some random functions which don't fit anywhere in particular.
#

import time
import itertools
import StringIO
import config
import types
import urllib

def webencode(s):
    assert type(s) == types.UnicodeType
    return s.encode(config.WEB_ENCODING)

def uu_decode(s, on_fail=u''):
    """Decodes (portions of) a URI. Removes %XX sequences and interprets the
       result as a UTF-8 formatted string. By default, returns u'' on failure.
    """
    try:
        return urllib.unquote(s).decode(config.WEB_ENCODING, s)
    except UnicodeDecodeError:
        return on_fail

def truncate(n, s):
    """Truncates a string s to at most n chars,
       appending '...' if the string is truncated.
    """
    if len(s) >= n:
        x = n - 3
        if x < 1: x = 1
        return s[0:x] + "..."
    else:
        return s

class ZonedDate(object):
    def __init__(self, gmt, offset):
        self.gmt = gmt
        self.offset = offset

    def __repr__(self):
        ostring = ''
        if self.offset > 0:
            ostring = '+%i' % self.offset
        elif self.offset < 0:
            ostring = str(self.offset)
        return time.strftime("%Y-%m-%d %H:%M:%S UTC" + ostring, time.gmtime(float(self.gmt) + (self.offset * 60.0 * 60.0)))

def futz_article_title(title):
    return title.replace(' ', '-')
def unfutz_article_title(title):
    return title.replace('_', ' ').replace('-', ' ')

def get_ymdhms_tuple():
    """Get a tuple (year, month, day, hour, minute, second)."""
    f_time = time.time()
    stime = time.gmtime(f_time)
    int_time = int(f_time)
    year   = time.strftime("%Y", stime)
    month  = time.strftime("%m", stime)
    day    = time.strftime("%d", stime)
    hour   = time.strftime("%H", stime)
    minute = time.strftime("%M", stime)
    second = time.strftime("%S", stime)
    return (year, month, day, hour, minute, second)

def merge_dicts(into, from_):
    """Merge values from one dictionary into another, returning the 'into'
       argument."""
    for k, v in from_.iteritems():
        into[k] = v
    return into

def diff_lists(old, new):
    new_elts      = filter(lambda x: not (x in old), new)
    removed_elts  = filter(lambda x: not (x in new), old)
    return new_elts, removed_elts

def flatten_list(L):
    if type(L) != type([]): return [L]
    if L == []: return L
    return flatten_list(L[0]) + flatten_list(L[1:])

# From the Python cookbook.
def unique(s):
    """Return a list of the elements in s, but without duplicates.

    For example, unique([1,2,3,1,2,3]) is some permutation of [1,2,3],
    unique("abcabc") some permutation of ["a", "b", "c"], and
    unique(([1, 2], [2, 3], [1, 2])) some permutation of
    [[2, 3], [1, 2]].

    For best speed, all sequence elements should be hashable.  Then
    unique() will usually work in linear time.

    If not possible, the sequence elements should enjoy a total
    ordering, and if list(s).sort() doesn't raise TypeError it's
    assumed that they do enjoy a total ordering.  Then unique() will
    usually work in O(N*log2(N)) time.

    If that's not possible either, the sequence elements must support
    equality-testing.  Then unique() will usually work in quadratic
    time.
    """

    n = len(s)
    if n == 0:
        return []

    # Try using a dict first, as that's the fastest and will usually
    # work.  If it doesn't work, it will usually fail quickly, so it
    # usually doesn't cost much to *try* it.  It requires that all the
    # sequence elements be hashable, and support equality comparison.
    u = {}
    try:
        for x in s:
            u[x] = 1
    except TypeError:
        del u  # move on to the next method
    else:
        return u.keys()

    # We can't hash all the elements.  Second fastest is to sort,
    # which brings the equal elements together; then duplicates are
    # easy to weed out in a single pass.
    # NOTE:  Python's list.sort() was designed to be efficient in the
    # presence of many duplicate elements.  This isn't true of all
    # sort functions in all languages or libraries, so this approach
    # is more effective in Python than it may be elsewhere.
    try:
        t = list(s)
        t.sort()
    except TypeError:
        del t  # move on to the next method
    else:
        assert n > 0
        last = t[0]
        lasti = i = 1
        while i < n:
            if t[i] != last:
                t[lasti] = last = t[i]
                lasti += 1
            i += 1
        return t[:lasti]

    # Brute force is all that's left.
    u = []
    for x in s:
        if x not in u:
            u.append(x)
    return u

#
# What was I smoking when I wrote this?
# Seems a shame to delete it even though it's no use.
#
#def group_by_preds(lst, *predicates):
#    """
#    Groups a list into a list of lists using a list of predicates.
#    Each element in the original list is given an index determined by the
#    predicate which it matches (or a different index if none of the predicates
#    match). Consecutive elements with identical indices are then grouped.
#    """
#    def index():
#        for elem in lst:
#            matched = False
#            for p, i in itertools.izip(predicates, itertools.count(1)):
#                if p(elem):
#                    matched = True
#                    yield (elem, i)
#            if not matched:
#                yield (elem, 0)
#    def group(it):
#        current_list = []
#        for elem in it:
#            if len(current_list) == 0:
#                current_list.append(elem)
#            else:
#                if elem[1] == current_list[len(current_list) - 1][1]:
#                    current_list.append(elem)
#                else:
#                    yield current_list
#                    current_list = [elem]
#        if len(current_list) != 0:
#            yield current_list
#    def fst(it):
#        while True:
#            yield [x[0] for x in it.next()]
#    return list(fst(group(index())))

# TODO: Is there a standard Python module for handling this format?
def csv_parse(string):
    """Parses key/value pairs in the format key1="value1", key2="value2", ...
       Quotes around values are optional.
       Returns None on failure and a dictionary on success.
    """
    d = { }
    state = 'initial'
    current_key = None
    current_value = None
    for c in string:
        if state == 'initial':
            if c.isspace():
                pass
            else:
                current_key = StringIO.StringIO()
                current_key.write(c)
                state = 'in_key'
        elif state == 'in_key':
            if c == '=':
                state = 'waiting_for_opening_quote'
            else:
                current_key.write(c)
        elif state == 'waiting_for_opening_quote':
            if c.isspace():
                pass
            elif c == '"':
                current_value = StringIO.StringIO()
                state = 'in_value'
            else:
                current_value = StringIO.StringIO()
                current_value.write(c)
                state = 'in_bare_value'
        elif state == 'in_value':
            if c == '"':
                d[current_key.getvalue()] = current_value.getvalue()
                state = 'waiting_for_comma'
            else:
                current_value.write(c)
        elif state == 'in_bare_value':
            if c.isspace() or c == ',':
                d[current_key.getvalue()] = current_value.getvalue()
                if c == ',':
                    state = 'initial'
                else:
                    state = 'waiting_for_comma'
            else:
                current_value.write(c)
        elif state == 'waiting_for_comma':
            if c.isspace():
                pass
            elif c == ',':
                state = 'initial'
            else:
                return None # Indicates error.
        else:
            assert False
    
    if state == 'in_bare_value':
        d[current_key.getvalue()] = current_value.getvalue()

    # Better to have a maximally permissive parser for our purposes.
    #
    #if state != 'initial' and state != 'waiting_for_comma' and state != 'in_bare_value':
    #    return None # Indicates error

    return d

def mark_last(seq):
    """Given a sequence, yields a (X, boolean) pair for each X in the sequence.
       The boolean is True if X is the last element in the sequence and false
       otherwise. This is a lazy as possible (only computes one element in the
       sequence ahead).
    """
    seq = iter(seq)
    previous = []
    while True:
        try:
            r1 = seq.next()
        except StopIteration:
            for p in previous: yield p, True
            break
        for p in previous: yield p, False
        previous = [r1]

