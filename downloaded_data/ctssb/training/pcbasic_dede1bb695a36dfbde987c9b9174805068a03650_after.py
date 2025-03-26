#
# PC-BASIC 3.23 - util.py
#
# Token stream utilities
# 
# (c) 2013, 2014 Rob Hagemans 
#
# This file is released under the GNU GPL version 3. 
# please see text file COPYING for licence terms.
#

# basic stream utility functions

# peek next char in stream
def peek(ins, n=1):
    d = ins.read(n)
    ins.seek(-len(d), 1)
    return d

# skip chars in skip_range, then read next
def skip_read(ins, skip_range, n=1):
    while True: 
        d = ins.read(1)
        # skip_range must not include ''
        if d == '' or d not in skip_range:
            return d + ins.read(n-1)

# skip chars in skip_range, then peek next
def skip(ins, skip_range, n=1):
    d = skip_read(ins, skip_range, n) 
    ins.seek(-len(d), 1)
    return d
    
##################################################
##################################################

from functools import partial

# tokens

# LF is just whitespace if not preceded by CR
# (what about TAB? are there other whitespace chars in a tokenised file?)
whitespace = (' ', '\t', '\x0a')
# line ending tokens
end_line = ('\x00', '')
# statement ending tokens
end_statement = end_line + (':',) 
# expression ending tokens
# '\xCC is 'TO', \x89 is GOTO, \x8D is GOSUB, \xCF is STEP, \xCD is THEN 
end_expression = end_statement + (')', ']', ',', ';', '\xCC', '\x89', '\x8D', '\xCF', '\xCD') 
## tokens followed by one or more bytes to be skipped
plus_bytes = {'\x0f':1, '\xff':1 , '\xfe':1, '\x0b':2, '\x0c':2, '\x0d':2, '\x0e':2, '\x1c':2, '\x1d':4, '\x1f':8, '\x00':4}


# these are for tokenised streams only

skip_white_read = partial(skip_read, skip_range=whitespace)
skip_white = partial(skip, skip_range=whitespace)

def skip_white_read_if(ins, in_range):
    d = skip_white(ins, n=len(in_range[0]))
    if d != '' and d in in_range:
        ins.read(len(d))
        return True
    return False

def skip_to(ins, findrange, break_on_first_char=True):        
    literal = False
    while True: 
        c = ins.read(1)
        if c == '':
            break
        elif c == '"':
            literal = not literal
        elif c == '\x00':   
            literal = False
        if literal:
            continue    
        if c in findrange:
            if break_on_first_char:
                ins.seek(-1, 1)
                break
            else: 
                break_on_first_char = True    
        # not elif! if not break_on_first_char, c needs to be properly processed.
        if c == '\x00':  # offset and line number follow
            literal = False
            off = ins.read(2)
            if len(off) < 2 or off == '\x00\x00':
                break
            ins.read(2)
        elif c in ('\xff', '\xfe', '\xfd', '\x0f'):
            ins.read(1)
        elif c in ('\x0b', '\x0c', '\x0d', '\x0e', '\x1c'):
            ins.read(2)
        elif c == '\x1d':
            ins.read(4)
        elif c == '\x1f':
            ins.read(8)

def skip_to_read(ins, findrange):
    skip_to(ins, findrange)
    return ins.read(1)

##################################################
##################################################

# parsing

import error
import vartypes

def require_read(ins, in_range, err=2):
    if skip_white_read(ins, n=len(in_range[0])) not in in_range:
        raise error.RunError(err)
    
def require(ins, rnge, err=2):
    a = skip_white(ins, n=len(rnge[0]))
    if a not in rnge:
        # position correctly for EDIT gadget and throw the (syntax) error
        if a != '':
            ins.read(1)
        raise error.RunError(err)
    
# parse line number and leve pointer at first char of line
# if end of program or truncated, leave pointer at start of line number C0 DE or 00 00    
def parse_line_number(ins):
    off = ins.read(2)
    if off=='\x00\x00' or len(off) < 2:
        ins.seek(-len(off),1)
        return -1
    off = ins.read(2)
    if len(off) < 2:
        ins.seek(-len(off)-2,1)
        return -1
    else:
        return vartypes.uint_to_value(bytearray(off))
  
# parses a line number when referred toindirectly as in GOTO, GOSUB, LIST, RENUM, EDIT, etc.
def parse_jumpnum(ins, allow_empty=False, err=2):
    if skip_white_read_if(ins, ('\x0e',)):
        return vartypes.uint_to_value(bytearray(ins.read(2)))    
    else:
        if allow_empty:
            return -1
        # Syntax error
        raise error.RunError(err)

# token to value
def parse_value(ins):
    d = ins.read(1)
    # note that hex and oct strings are interpreted signed here, but unsigned the other way!
    try:
        length = plus_bytes[d]
    except KeyError:
        length = 0
    val = bytearray(ins.read(length))
    if len(val) < length:
        # truncated stream
        raise error.RunError(2)
    if d in ('\x0b', '\x0C', '\x1C'):       # octal, hex, signed int
        return ('%', val)
    elif d == '\x0f':                       # one byte constant
        return ('%', val + '\x00') 
    elif d >= '\x11' and d <= '\x1b':       # constants 0 to 10  
        return ('%', bytearray(chr(ord(d)-0x11) + '\x00'))
    elif d == '\x1d':                       # four byte single-precision floating point constant
        return ('!', val)
    elif d == '\x1f':                       # eight byte double-precision floating point constant
        return ('#', val)
    return None


def get_var_name(ins, allow_empty=False):
    name = ''
    d = skip_white_read(ins).upper()
    if not (d >= 'A' and d <= 'Z'):
        # variable name must start with a letter
        ins.seek(-len(d), 1)
    else:
        while (d>='A' and d<='Z') or (d>='0' and d<='9') or d=='.':
            name += d
            d = ins.read(1).upper()
        if d in ('$', '%', '!', '#'):
            name += d
        else:
            ins.seek(-len(d), 1)
    if not name and not allow_empty:
        raise error.RunError(2)    
    # append type specifier
    name = vartypes.complete_name(name)
    # only the first 40 chars are relevant in GW-BASIC, rest is discarded
    if len(name) > 41:
        name = name[:40]+name[-1]
    return name

def range_check(lower, upper, *allvars):
    for v in allvars:
        if v != None and v < lower or v > upper:
            raise error.RunError(5)
            
def range_check_err(lower, upper, v, err=5):
    if v != None and v < lower or v > upper:
        raise error.RunError(err)
            
            

