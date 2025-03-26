#
# PC-BASIC 3.23 - tokenise.py
#
# Token parser
# converts between tokenised and ASCII formats of a GW-BASIC program file
# 
# (c) 2013 Rob Hagemans 
#
# This file is released under the GNU GPL version 3. 
# please see text file COPYING for licence terms.
#
# Acknowledgements:
#
# Norman De Forest for documentation of the file format:
#   http://www.chebucto.ns.ca/~af380/GW-BASIC-tokens.html
# danvk for the open-source detokenise implementation here:
#   http://www.danvk.org/wp/2008-02-03/reading-old-gw-basic-programs/
# Julian Bucknall and asburgoyne for descriptions of the Microsoft Binary Format posted here:
#   http://www.boyet.com/Articles/MBFSinglePrecision.html
#   http://www.experts-exchange.com/Programming/Languages/Pascal/Delphi/Q_20245266.html


#################################################################
import StringIO

import glob
import error
import fp 
import vartypes

from util import *



tokens_number = ['\x0b','\x0c','\x0f',
    '\x11','\x12','\x13','\x14','\x15','\x16','\x17','\x18','\x19','\x1a','\x1b',
    '\x1c','\x1d', '\x1f']
tokens_linenum = ['\x0d','\x0e' ]
tokens_operator = map(chr, range(0xe6, 0xed+1))
tokens_with_bracket = ['\xd2', '\xce']




# newline is considered whitespace
tokenise_whitespace = [' ', '\t', '\x0a']
tokenise_endfile = ['', '\x1a']
tokenise_endline_nonnul =  tokenise_endfile + ['\x0d']
tokenise_endline = tokenise_endline_nonnul + ['\x00'] # after NUL everything is ignored untile EOL 
tokenise_endstatement = tokenise_endline + [':']

ascii_octits = ['0','1','2','3','4','5','6','7']
ascii_digits = ascii_octits + ['8','9']
ascii_hexits = ascii_digits + ['A','B','C','D','E','F']

ascii_operators = ['+', '-', '=', '/', '\\', '^', '*', '<', '>']        
ascii_uppercase = map(chr, range(ord('A'),ord('Z')+1))        

# allowable as chars 2.. in a variable name (first char must be a letter)
name_chars = ascii_uppercase + ascii_digits + ['.']

# keywords followed by one or more line numbers
linenum_words = ['GOTO', 'THEN', 'GOSUB', 'LIST', 'RENUM', 'EDIT', 'LLIST', 'DELETE', 'RUN', 'RESUME', 'ERR', 'ERL', 'AUTO']


#################################################################

# Detokenise functions

def detokenise(ins, outs, from_line=-1, to_line=-1, pos=-1):
    textpos=0
    while True:
        # TODO - an attempt to reproduce the cursor positioning after a syntax error
        #if pos <= ins.tell():
        # tell doesn't work on stdout
        #    textpos = outs.tell()
            
        current_line = parse_line_number(ins)
        if current_line < 0:
            # stream ends or end of file sequence \x00\x00
            # in a proper ending, next character should be EOF \x1A, output warning if not 
            eof = ins.read(1)
            if eof != '\x1a':
                info =''
                if eof != '':
                    info = '&H' + hex(ord(eof))[2:]
                error.warning(2, -1, info)
            # gather everything past the end of file as a hex string to be sent to stderr
            eof_str = ins.read()    
            if eof_str != '':    
                error.warning(3, -1, eof_str.encode('hex'))
            break
        
        # 65529 is max line number for GW-BASIC 3.23. 
        # however, 65530-65535 are executed if present in tokenised form.
        # in GW-BASIC, 65530 appears in LIST, 65531 and above are hidden
        if current_line > 65530:
            error.warning(5, current_line, '')
    
        # always write one extra whitespace character after line number
        output = vartypes.int_to_str(current_line) + ' '         
        # detokenise tokens until end of line
        output += detokenise_line(ins)
            
        if (from_line==-1 or current_line>=from_line) and (to_line==-1 or current_line<=to_line):
            outs.write(output + glob.endl) 

    return textpos

    
    
    
def detokenise_line(bytes):
    output = ''
    litstring = False
    comment=False
    while True:
        s = bytes.read(1)
        
        if s in end_line:
            # \x00 ends lines and comments when listed, if not inside a number constant
            # stream ended or end of line
            break
            
        elif s == '"':
            # start of literal string, passed verbatim until a closing quote or EOL comes by
            # however number codes are *printed* as the corresponding numbers, even inside comments & literals
            output += s
            litstring = not litstring  

        elif s in tokens_number:
            bytes.seek(-1,1)
            output += detokenise_number(bytes)

        elif s in tokens_linenum: 
            # 0D: line pointer (unsigned int) - this token should not be here; interpret as line number and carry on
            # 0E: line number (unsigned int)
            output += vartypes.uint_to_str(bytes.read(2))
            
        elif s in ('\x10', '\x1e'):                           
            # 1E/10: UNUSED: Flags numeric constant being processed/no longer being processed
            pass
        
        elif comment or litstring or (s >= '\x20' and s <= '\x7e'):   # honest ASCII
            output += s
            
        else:
            # try for single-byte token or two-byte token
            # if no match, first char is passed unchanged
            bytes.seek(-1,1)
            output, comment = detokenise_keyword(bytes, output)
            
    return output



# token to string
def detokenise_number(bytes):
    s = bytes.read(1)
    output=''
    if s == '\x0b':                           # 0B: octal constant (unsigned int)
        output += vartypes.oct_to_str(bytes.read(2))
    elif s == '\x0c':                           # 0C: hex constant (unsigned int)
        output += vartypes.hex_to_str(bytes.read(2))
    elif s == '\x0f':                           # 0F: one byte constant
        output += vartypes.ubyte_to_str(bytes.read(1))
    elif s >= '\x11' and s < '\x1b':            # 11-1B: constants 0 to 10
        output += chr(ord('0') + ord(s) - 0x11)
    elif s == '\x1b':               
        output += '10'
    elif s == '\x1c':                           # 1C: two byte signed int
        output += vartypes.sint_to_str(bytes.read(2))
    elif s == '\x1d':                           # 1D: four-byte single-precision floating point constant
        output += fp.to_str(fp.from_bytes(bytes.read(4)), screen=False, write=False)
    elif s == '\x1f':                           # 1F: eight byte double-precision floating point constant
        output += fp.to_str(fp.from_bytes(bytes.read(8)), screen=False, write=False)
    else:
        if s!='':
            bytes.seek(-1,1)  
    return output



##########################################
# TODO: these do not belong here...

# token to value
def parse_value(ins):
    
    d = ins.read(1)
    
    # note that hex and oct strings are interpreted signed here, but unsigned the other way!
    if d == '\x0b':                         # octal constant (unsigned)
        return ('%', vartypes.sint_to_value(ins.read(2)) )
    elif d == '\x0c':                       # hex constant (unsigned)
        return ('%', vartypes.sint_to_value(ins.read(2)) )
    elif d == '\x0f':                       # one byte constant
        return ('%', ord(ins.read(1)) )
    elif d >= '\x11' and d <= '\x1b':       # constants 0 to 10  
        return ('%', ord(d) - 0x11 )
    elif d == '\x1c':          # two byte data constant (signed)
        return ('%', vartypes.sint_to_value(ins.read(2)) )
    elif d == '\x1d':          # four byte single-precision floating point constant
        return ('!', list(ins.read(4)) )
    elif d == '\x1f':          # eight byte double-precision floating point constant
        return ('#', list(ins.read(8)) )
    
    return ('','')


def str_to_value_keep(strval):
    strval = vartypes.pass_string_keep(strval)[1]
    ins = StringIO.StringIO(strval)
    outs = StringIO.StringIO()
    tokenise_number(ins, outs)    
    outs.seek(0)
    value = parse_value(outs)
    ins.close()
    outs.close()
    return value
    

##########################################



# de tokenise one- or two-byte tokens
def detokenise_keyword(bytes, output):
    s = bytes.read(1)
    if not token_to_keyword.has_key(s):
        s += peek(bytes)
        if not token_to_keyword.has_key(s):
            return s[0], False
        else:
            bytes.read(1)
    
    # number followed by token is separated by a space, except D2, CE: SPC(, TAB(
    if (len(output)>0) and (output[-1] in ascii_digits) and (s not in tokens_operator+tokens_with_bracket):
        output+=' '
    
    keyword = token_to_keyword[s]
    output += keyword
    
    comment = False
    if keyword == "'":
        comment = True
    elif keyword == "REM":
        nxt = bytes.read(1)
        if nxt == '':
            pass
        elif token_to_keyword.has_key(nxt) and token_to_keyword[nxt] == "'":
            # if next char is token('), we have the special value REM' -- replaced by ' below.
            output += "'"
        else:
            # otherwise, it's part of the comment or an EOL or whatever, pass back to stream so it can be processed
            bytes.seek(-1,1)
        comment = True
    
    #   [:REM']   ->  [']
    if len(output)>4 and output[-5:] ==  ":REM'":
        output = output[:-5] + "'"  
    #   [WHILE+]  ->  [WHILE]
    elif len(output)>5 and output[-6:] == "WHILE+":
        output = output[:-1]        
    #   [:ELSE]  ->  [ELSE]
    elif len(output)>4 and output[-5:] == ":ELSE":
        output = output[:-5] + "ELSE" 
    
    
    
    # token followed by number is also separated by a space, except operator tokens and SPC(, TAB(
    nxt = peek(bytes)
    #if nxt.upper() in (ascii_uppercase+tokens_number+tokens_linenum) and s not in (tokens_operator+tokens_with_bracket):
    if nxt.upper() not in (tokens_operator+['\xD9','"',':',',']) and s not in (tokens_operator+tokens_with_bracket):
        output+=' '

    return output, comment
    
    
    
    
#################################################################
#################################################################
#################################################################

# Tokenise functions

def tokenise_stream(ins, outs, one_line=False, onfile=True):
    
    
    while True:
        
        # skip whitespace at start of line
        d = skip(ins, tokenise_whitespace)
        
        if d in tokenise_endfile:
            ins.read(1)
            return False
        
        elif d in tokenise_endline_nonnul:
            # handle \x0d\x0a
            if ins.read(1)=='\x0d':
                if peek(ins) == '\x0A':
                    ins.read(1) 

            if one_line:
                return True
            else:
                continue
        
        # read the line number
        tokenise_line_number(ins, outs, onfile)
     
     
        # non-parsing modes
        verbatim = False  # REM: pass unchnaged until e-o-line
        data = False      # DATA: pass unchanged until :
        
        # expect line number
        number_is_line = False
        # expect number
        expect_number=False
        # flag for SPC( or TAB( as numbers can follow the closing bracket
        spc_or_tab=False
        # parse through elements of line
        while True: 
            
            # non-parsing modes        
            if verbatim :
                # anything after REM is passed as is till EOL
                outs.write(ascii_read_to(ins, tokenise_endline))
                break
                
            elif data:
                # read DATA as is, till end of statement    
                outs.write(ascii_read_to(ins, tokenise_endstatement))
                data = False
                
            elif peek(ins)=='"':
                # handle string literals    
                outs.write(ins.read(1))
                outs.write(ascii_read_to(ins, tokenise_endline + ['"'] ))
                if peek(ins)=='"':
                    outs.write(ins.read(1))
            
            # read next character
            char = peek(ins)
            
            # anything after NUL is ignored till EOL
            if char=='\x00':
                ins.read(1)
                ascii_read_to(ins, tokenise_endline_nonnul)
                break
                            
            # end of line    
            if char in tokenise_endline_nonnul:
                break
                        
            # convert anything else to upper case
            c = char.upper()
            
            # handle whitespace
            if c in tokenise_whitespace:
                ins.read(1)
                outs.write(char)
    
            # handle numbers
            # numbers following var names with no operator or token in between should not be parsed, eg OPTION BASE 1
            # note we don't include leading signs, they're encoded as unary operators
            elif expect_number and c in ascii_digits + ['&', '.']:
                if number_is_line:
                    outs.write(tokenise_jump_number(ins, outs))
                else:        
                    outs.write(tokenise_number(ins, outs))
            
            # operator keywords ('+', '-', '=', '/', '\\', '^', '*', '<', '>'):    
            elif c in ascii_operators: 
                ins.read(1)
                # operators don't affect line number mode- can do line number arithmetic and RENUM will do the strangest things
                # this allows for 'LIST 100-200' etc.
                outs.write(keyword_to_token[c])    
                expect_number = True
                
            # special case ' -> :REM'
            elif c=="'":
                ins.read(1)
                verbatim = True
                outs.write(':\x8F\xD9')
            
            # special case ? -> PRINT 
            elif (c=='?'):
                ins.read(1)
                outs.write(keyword_to_token['PRINT'])
                expect_number = True
                   
            # keywords & variable names       
            elif c in ascii_uppercase:
                number_is_line = False
                
                word = tokenise_word(ins, outs)
                
                # handle non-parsing modes
                if word in ('REM', "'") or glob.debug and word=='DEBUG':  # note: DEBUG - this is not GW-BASIC behaviour
                    verbatim = True
                elif word == "DATA":    
                    data = True
                elif word in linenum_words: 
                    number_is_line = True
                
                # numbers can follow tokenised keywords and the word 'AS'    
                expect_number = (word in keyword_to_token) or word=='AS'
                
                if word in ('SPC(', 'TAB('):
                    spc_or_tab = True
                    
            elif c==',' or c=='#':
                ins.read(1)
                expect_number=True
                outs.write(c)
            elif c in ('(', '['):
                ins.read(1)
                number_is_line = False
                expect_number=True
                outs.write(c)
            elif c== ')' and spc_or_tab:
                ins.read(1)
                number_is_line = False
                expect_number=True
                outs.write(c)
            else:
                ins.read(1)
                number_is_line = False
                expect_number=False
                outs.write(c)
            
    
    

            


def tokenise_line_number(ins, outs, onfile):
    linenum = ''
    while True:
        d = ins.read(1)
        if d not in ascii_digits:
            if d!='':
                ins.seek(-1,1)
            break
        linenum += d
    
    # no line number, if we're reading a file this is a Direct Statement In File error
    if (linenum=='') and onfile:
        raise error.RunError(66, -1)    

    if linenum != '':
        if int(linenum) not in range (0, 65530):
            # note: anything >= 65530 is illegal in GW-BASIC
            # in loading an ASCII file, GWBASIC would interpret these as '6553 1' etcetera, generating a syntax error on execution.
            error.warning(5, int(linenum), '')
            
            # keep 6553 as line number and push back the last number:
            linenum = linenum[:4]
            ins.seek(-1,1)
            
        # terminates last line and fills up the first char in the buffer (that would be the magic number when written to file)
        # in direct mode, we'll know to expect a line number if the output starts with a  00
        outs.write('\x00')        
        # write line number. first two bytes are for internal use & can be anything nonzero; we use this.
        outs.write('\xC0\xDE' + vartypes.value_to_uint(int(linenum)))
    
        # ignore single whitespace after line number, if any, unless line number is zero (as does GW)
        if peek(ins)==' ' and int(linenum) !=0 :
            ins.read(1)
    else:
        # direct line; internally, we need an anchor for the program pointer, so we encode a ':'
        outs.write(':')


            
def tokenise_jump_number(ins, outs):
    word=''
    while True:
        c = ins.read(1)
        if c not in ascii_digits:
            #number_is_line=False
            if c!= '':
                ins.seek(-1,1)
            break
        else:
            word += c   

    # line number (jump)
    if word !='':
        outs.write('\x0e' + vartypes.str_to_uint(word))



   
# string to token             
def tokenise_number(ins, outs):
    c = peek(ins)
    
    # handle hex or oct constants
    if c=='&':
        word = ins.read(1)
        nxt = peek(ins).upper()
        if nxt == 'H': # hex constant
            word += ins.read(1)
            while True: 
                if not peek(ins).upper() in ascii_hexits:
                    break
                else:
                    word += ins.read(1).upper()
            outs.write('\x0C' + vartypes.str_to_hex(word))
            
        elif nxt == 'O': # octal constant
            word += ins.read(1)
            while True: 
                if not peek(ins).upper() in ascii_octits:
                    break
                else:
                    word += ins.read(1).upper()
            outs.write('\x0B' + vartypes.str_to_oct(word))
       
        else:
            outs.write(c)
            
    # handle other numbers
    # note GW passes signs separately as a token and only stores positive numbers in the program        
    elif (c in ascii_digits or c=='.' or c in ('+','-')):
        
        have_exp = False
        have_point = False
        word = ''
        while True: 
            c = ins.read(1).upper()
  
            
            if c=='.' and not have_point and not have_exp:
                have_point = True
                word += c
            elif c in ('E', 'D') and not have_exp:    
                have_exp = True
                word += c
            elif c in ('-','+') and word=='':
                # must be first token
                word += c              
            elif c in ('+', '-') and word[-1] in ('E', 'D'):
                word += c
            elif c in ascii_digits: # (c >='0' and numc <='9'):
                word += c
            elif c in tokenise_whitespace:
                pass    
            elif c in ('!', '#') and not have_exp:
                word += c
                break
            else:
                if c != '':
                    ins.seek(-1,1)
                break
                
        # don't claim trailing whitespace, don't end in D or E            
        while len(word)>0 and word[-1] in tokenise_whitespace + ['D', 'E']:
            if word[-1] in ('D', 'E'):
                have_exp = False
            word = word[:-1]
            ins.seek(-1,1) # even if c==''
            
            
        # write out the numbers
                
        if len(word)==1 and word in ascii_digits:
            # digit
            outs.write(chr(0x11+int(word)))
            
        elif not (have_exp or have_point or word[-1] in ('!', '#')) and int(word) <= 0x7fff and int(word) >= -0x8000:
            if int(word) <= 0xff and int(word)>=0:
                # one-byte constant
                outs.write('\x0f'+chr(int(word)))
            else:
                # two-byte constant
                outs.write('\x1c'+vartypes.value_to_sint(int(word)))
        else:
            mbf = fp.to_bytes(fp.from_str(word))
            if len(mbf) == 4:
                # single
                outs.write('\x1d'+''.join(mbf))
            else:    
                # double
                outs.write('\x1f'+''.join(mbf))
    
    elif c!='':
            ins.seek(-1,1)



            
    
def tokenise_word(ins, outs):
    word = ''
    while True: 
        c = ins.read(1).upper()
        word += c
        
            
        # special cases 'GO     TO' -> 'GOTO', 'GO SUB' -> 'GOSUB'    
        if word=='GO':
            pos=ins.tell()
        
            # GO SUB allows 1 space
            if peek(ins, 4) == ' SUB':
                word='GOSUB'
                ins.read(4)
            else:
                # GOTO allows any number of spaces
                nxt = ins.read(1) 
                while nxt in tokenise_whitespace:
                    nxt = ins.read(1)
                
                if ins.read(2)=='TO':
                   word='GOTO'
                else:
                   ins.seek(pos)
              
            if word in ('GOTO', 'GOSUB'):
                nxt = peek(ins).upper()
                if nxt in name_chars: #ascii_uppercase or nxt in ascii_digits or nxt=='.':
                    ins.seek(pos)
                    word='GO'
                else:
                    pass
                    
        if word in keyword_to_token:
            # ignore if part of a longer name, except 'FN', 'SPC(', 'TAB('
            if word not in ('FN', 'SPC(', 'TAB('):
                nxt = peek(ins).upper()
                if nxt in name_chars:  #ascii_uppercase or nxt in ascii_digits or nxt=='.':
                    continue
            
            token = keyword_to_token[word]
            
            # handle special case ELSE -> :ELSE
            if word=='ELSE':
                outs.write('\x3a'+ token)
            # handle special case WHILE -> WHILE+
            elif word=='WHILE':
                outs.write(token +'\xe9')
            #elif token <= 0xff: # len(token)==1
            #    outs.write(token)    
            else:
                outs.write(token)
            break
            
        # allowed names: letter + (letters, numbers, .)    
        elif not(c in name_chars): 
            if c!='':
                word = word[:-1]
                ins.seek(-1,1)
            outs.write(word)            
            break

        
    return word
    
            
        


#################################################################
#################################################################
#################################################################

token_to_keyword = {  
    '\x81': 'END',    '\x82': 'FOR',       '\x83': 'NEXT',   '\x84': 'DATA',  '\x85': 'INPUT',   '\x86': 'DIM',    '\x87': 'READ',  
    '\x88': 'LET',    '\x89': 'GOTO',      '\x8A': 'RUN',    '\x8B': 'IF',    '\x8C': 'RESTORE', '\x8D': 'GOSUB',  '\x8E': 'RETURN',  
    '\x8F': 'REM',    '\x90': 'STOP',      '\x91': 'PRINT',  '\x92': 'CLEAR', '\x93': 'LIST',    '\x94': 'NEW',    '\x95': 'ON',  
    '\x96': 'WAIT',   '\x97': 'DEF',       '\x98': 'POKE',   '\x99': 'CONT',  '\x9C': 'OUT',     '\x9D': 'LPRINT', '\x9E': 'LLIST',  
    '\xA0': 'WIDTH',  '\xA1': 'ELSE',      '\xA2': 'TRON',   '\xA3': 'TROFF', '\xA4': 'SWAP',    '\xA5': 'ERASE',  '\xA6': 'EDIT',  
    '\xA7': 'ERROR',  '\xA8': 'RESUME',    '\xA9': 'DELETE', '\xAA': 'AUTO',  '\xAB': 'RENUM',   '\xAC': 'DEFSTR', '\xAD': 'DEFINT',  
    '\xAE': 'DEFSNG', '\xAF': 'DEFDBL',    '\xB0': 'LINE',   '\xB1': 'WHILE', '\xB2': 'WEND',    '\xB3': 'CALL',   '\xB7': 'WRITE',  
    '\xB8': 'OPTION', '\xB9': 'RANDOMIZE', '\xBA': 'OPEN',   '\xBB': 'CLOSE', '\xBC': 'LOAD',    '\xBD': 'MERGE',  '\xBE': 'SAVE',      
    '\xBF': 'COLOR',  '\xC0': 'CLS',       '\xC1': 'MOTOR',  '\xC2': 'BSAVE', '\xC3': 'BLOAD',   '\xC4': 'SOUND',  '\xC5': 'BEEP',
    '\xC6': 'PSET',   '\xC7': 'PRESET',    '\xC8': 'SCREEN', '\xC9': 'KEY',   '\xCA': 'LOCATE',  '\xCC': 'TO',     '\xCD': 'THEN',  
    '\xCE': 'TAB(',   '\xCF': 'STEP',      '\xD0': 'USR',    '\xD1': 'FN',    '\xD2': 'SPC(',    '\xD3': 'NOT',    '\xD4': 'ERL',
    '\xD5': 'ERR',    '\xD6': 'STRING$',   '\xD7': 'USING',  '\xD8': 'INSTR', '\xD9': "'",       '\xDA': 'VARPTR', '\xDB': 'CSRLIN',  
    '\xDC': 'POINT',  '\xDD': 'OFF',       '\xDE': 'INKEY$', '\xE6': '>',     '\xE7': '=',       '\xE8': '<',      '\xE9': '+', 
    '\xEA': '-',      '\xEB': '*',         '\xEC': '/',      '\xED': '^',     '\xEE': 'AND',     '\xEF': 'OR',     '\xF0': 'XOR',  
    '\xF1': 'EQV',    '\xF2': 'IMP',       '\xF3': 'MOD',    '\xF4': '\\',
    
    '\xFD\x81': 'CVI',    '\xFD\x82': 'CVS',     '\xFD\x83': 'CVD',   '\xFD\x84': 'MKI$',    '\xFD\x85': 'MKS$',  '\xFD\x86': 'MKD$',
    '\xFD\x8B': 'EXTERR', '\xFE\x81': 'FILES',   '\xFE\x82': 'FIELD', '\xFE\x83': 'SYSTEM',  '\xFE\x84': 'NAME',  '\xFE\x85': 'LSET',  
    '\xFE\x86': 'RSET',   '\xFE\x87': 'KILL',    '\xFE\x88': 'PUT',   '\xFE\x89': 'GET',     '\xFE\x8A': 'RESET', '\xFE\x8B': 'COMMON',
    '\xFE\x8C': 'CHAIN',  '\xFE\x8D': 'DATE$',   '\xFE\x8E': 'TIME$', '\xFE\x8F': 'PAINT',   '\xFE\x90': 'COM',   '\xFE\x91': 'CIRCLE', 
    '\xFE\x92': 'DRAW',   '\xFE\x93': 'PLAY',    '\xFE\x94': 'TIMER', '\xFE\x95': 'ERDEV',   '\xFE\x96': 'IOCTL', '\xFE\x97': 'CHDIR', 
    '\xFE\x98': 'MKDIR',  '\xFE\x99': 'RMDIR',   '\xFE\x9A': 'SHELL', '\xFE\x9B': 'ENVIRON', '\xFE\x9C': 'VIEW',  '\xFE\x9D': 'WINDOW',
    '\xFE\x9E': 'PMAP',   '\xFE\x9F': 'PALETTE', '\xFE\xA0': 'LCOPY', '\xFE\xA1': 'CALLS',   '\xFE\xA5': 'PCOPY', 
    '\xFE\xA7': 'LOCK',   '\xFE\xA8': 'UNLOCK',  '\xFF\x81': 'LEFT$', '\xFF\x82': 'RIGHT$',  '\xFF\x83': 'MID$',  '\xFF\x84': 'SGN',    
    '\xFF\x85': 'INT',    '\xFF\x86': 'ABS',     '\xFF\x87': 'SQR',   '\xFF\x88': 'RND',     '\xFF\x89': 'SIN',   '\xFF\x8A': 'LOG',   
    '\xFF\x8B': 'EXP',    '\xFF\x8C': 'COS',     '\xFF\x8D': 'TAN',   '\xFF\x8E': 'ATN',     '\xFF\x8F': 'FRE',   '\xFF\x90': 'INP',   
    '\xFF\x91': 'POS',    '\xFF\x92': 'LEN',     '\xFF\x93': 'STR$',  '\xFF\x94': 'VAL',     '\xFF\x95': 'ASC',   '\xFF\x96': 'CHR$',   
    '\xFF\x97': 'PEEK',   '\xFF\x98': 'SPACE$',  '\xFF\x99': 'OCT$',  '\xFF\x9A': 'HEX$',    '\xFF\x9B': 'LPOS',  '\xFF\x9C': 'CINT',  
    '\xFF\x9D': 'CSNG',   '\xFF\x9E': 'CDBL',    '\xFF\x9F': 'FIX',   '\xFF\xA0': 'PEN',     '\xFF\xA1': 'STICK', '\xFF\xA2': 'STRIG',  
    '\xFF\xA3': 'EOF',    '\xFF\xA4': 'LOC',     '\xFF\xA5': 'LOF'          
}

# Note - I have implemented this as my own debugging command, executes python string.
if glob.debug:
    token_to_keyword['\xFE\xA4']='DEBUG'
    
keyword_to_token = dict((reversed(item) for item in token_to_keyword.items()))


# other keywords documented on http://www.chebucto.ns.ca/~af380/GW-BASIC-tokens.html :

# PCjr only:
#   0xFEA4: 'NOISE' 
#   0xFEA6: 'TERM'
# The site also remarks - 0xFEA5: PCOPY (PCjr or EGA system only) 
# Apparently I have an 'EGA system', as this keyword is in the GW-BASIC 3.23 documentation.

# Sperry PC only:
#   0xFEA4: 'DEBUG'

# Undefined tokens:
#   0x9A,  0x9B,  0x9F,  0xB4,  0xB5,  0xB6,  0xCB,  0xDF,  0xE0,  0xE1,  0xE2
#   0xE3,  0xE4,  0xE5,  0xF5,  0xF6,  0xF7,  0xF8,  0xF9,  0xFA,  0xFB,  0xFC

