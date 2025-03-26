import ply.yacc as yacc
import threading
import web

from url_lex import make_lexer, tokens, keywords

# use ast module to build abstract syntax tree
import url_ast

################################################
# here's the grammar and ast production rules

start = 'start'

def p_start(p):
    """start : filelist
             | file
             | tagdef
             | tagdefacl
             | tags
             | query
             | transmitnumber
             | study
             | appleterror
             | loglist
             | log
             | contact
"""
    p[0] = p[1]

def p_filelist(p):
    """filelist : slash string
                | slash string slash
                | slash string slash FILE
                | slash string slash FILE slash"""
    p[0] = url_ast.FileList(appname=p[2])
    
def p_filelist_opts1(p):
    """filelist : slash string queryopts"""
    p[0] = url_ast.FileList(appname=p[2], queryopts=p[3])
    
def p_loglist(p):
    """loglist : slash string slash LOG
               | slash string slash LOG slash"""
    p[0] = url_ast.LogList(appname=p[2])

def p_contact(p):
    """contact : slash string slash CONTACT"""
    p[0] = url_ast.Contact(appname=p[2])
    
def p_filelist_opts2(p):
    """filelist : slash string slash FILE queryopts"""
    p[0] = url_ast.FileList(appname=p[2], queryopts=p[5])

def p_file(p):
    """file : slash string slash FILE slash filename"""
    p[0] = url_ast.FileId(appname=p[2], data_id=p[6])

def p_log(p):
    """log : slash string slash LOG slash string"""
    p[0] = url_ast.LogId(appname=p[2], data_id=p[6])

def p_log_opts(p):
    """file : slash string slash LOG slash string queryopts"""
    p[0] = url_ast.LogId(appname=p[2], data_id=p[6], queryopts=p[7])

def p_file_opts(p):
    """file : slash string slash FILE slash filename queryopts"""
    p[0] = url_ast.FileId(appname=p[2], data_id=p[6], queryopts=p[7])

def p_tagdef(p):
    """tagdef : slash string slash TAGDEF
              | slash string slash TAGDEF slash"""
    # GET all definitions and a creation form (HTML)
    p[0] = url_ast.Tagdef(appname=p[2])

def p_tagdef_rest_get(p):
    """tagdef : slash string slash TAGDEF slash string"""
    # GET a single definition (URL encoded)
    p[0] = url_ast.Tagdef(appname=p[2], tag_id=p[6])

def p_tagdef_rest_put(p):
    """tagdef : slash string slash TAGDEF slash string queryopts"""
    # PUT queryopts supports typestr=string&multivalue=boolean&readpolicy=pol&writepolicy=pol
    #  where pol is in [ anonymous, users, file, fowner, tag, system ]
    p[0] = url_ast.Tagdef(appname=p[2], tag_id=p[6], queryopts=p[7])

def p_tagdefacl_all(p):
    """tagdefacl : slash string slash TAGDEFACL
            | slash string slash TAGDEFACL slash"""
    # note: this class hijacks FileTags
    p[0] = url_ast.TagdefACL(appname=p[2])

def p_tagdefacl(p):
    """tagdefacl : slash string slash TAGDEFACL slash string 
            | slash string slash TAGDEFACL slash string slash"""
    # note: this class hijacks FileTags so arg naming is weird
    # data_id --> tag_id
    p[0] = url_ast.TagdefACL(appname=p[2], data_id=p[6])

def p_tagdefaclvalrest(p):
    """tagdefacl : slash string slash TAGDEFACL slash string slash tagvals"""
    # note: this class hijacks FileTags so arg naming is weird
    # data_id --> tag_id
    # tag_id --> [ readers, writers ]
    # values --> usernames
    p[0] = url_ast.TagdefACL(appname=p[2], data_id=p[6], tagvals=p[8])

def p_tags_all(p):
    """tags : slash string slash TAGS
            | slash string slash TAGS slash"""
    p[0] = url_ast.FileTags(appname=p[2])

def p_tags_all_opts(p):
    """tags : slash string slash TAGS queryopts"""
    p[0] = url_ast.FileTags(appname=p[2], queryopts=p[5])

def p_tags_all_slash_opts(p):
    """tags : slash string slash TAGS slash queryopts"""
    p[0] = url_ast.FileTags(appname=p[2], queryopts=p[6])

def p_tags(p):
    """tags : slash string slash TAGS slash filename 
            | slash string slash TAGS slash filename slash"""
    p[0] = url_ast.FileTags(appname=p[2], data_id=p[6])

def p_tags_opts(p):
    """tags : slash string slash TAGS slash filename queryopts"""
    p[0] = url_ast.FileTags(appname=p[2], data_id=p[6], queryopts=p[7])

def p_tagsvalrest(p):
    """tags : slash string slash TAGS slash filename slash tagvals"""
    p[0] = url_ast.FileTags(appname=p[2], data_id=p[6], tagvals=p[8])

def p_tagvals(p):
    """tagvals : tagval"""
    p[0] = dict()
    tag = p[1][0]
    vallist = p[1][1]
    p[0][tag] = list(vallist)

def p_tagvallist_grow(p):
    """tagvals : tagvals ';' tagval"""
    p[0] = p[1]
    tag = p[3][0]
    vallist = p[3][1]
    try:
        vals = p[0][tag]
        for val in vallist:
            vals.append(val)
    except:
        p[0][tag] = list(vallist)

def p_tagval(p):
    """tagval : string '=' vallist"""
    p[0] = ( p[1], p[3] )

def p_tag(p):
    """tagval : string"""
    p[0] = ( p[1], list() )

def p_query1(p):
    """query : slash string slash QUERY
             | slash string slash QUERY slash"""
    p[0] = url_ast.Query(appname=p[2], predlist=[], queryopts={})

def p_query2a(p):
    """query : slash string slash QUERY queryopts"""
    p[0] = url_ast.Query(appname=p[2], predlist=[], queryopts=p[5])

def p_query2b(p):
    """query : slash string slash QUERY slash queryopts"""
    p[0] = url_ast.Query(appname=p[2], predlist=[], queryopts=p[6])

def p_query3(p):
    """query : slash string slash QUERY slash predlist"""
    p[0] = url_ast.Query(appname=p[2], predlist=p[6], queryopts={})

def p_query4(p):
    """query : slash string slash QUERY slash predlist queryopts"""
    p[0] = url_ast.Query(appname=p[2], predlist=p[6], queryopts=p[7])

def p_predlist(p):
    """predlist : pred"""
    p[0] = list([ p[1] ])

def p_predlist_grow(p):
    """predlist : predlist ';' pred"""
    p[0] = p[1]
    p[0].append(p[3])

def p_pred_tag_val_comp(p):
    """pred : string compare vallist"""
    p[0] = dict([ ('tag', p[1]), ('op', p[2]), ('vals', p[3]) ])

def p_pred_tag(p):
    """pred : string"""
    p[0] = dict([ ('tag', p[1]), ('op', None), ('vals', []) ])

def p_pred_not_tag(p):
    """pred : string ':' NOT ':'"""
    p[0] = dict([ ('tag', p[1]), ('op', ':not:'), ('vals', []) ])

def p_pred_vallist(p):
    """vallist : string"""
    p[0] = list([ p[1] ])

def p_pred_vallist_grow(p):
    """vallist : vallist ',' string"""
    p[0] = p[1]
    p[1].append(p[3])

def p_compare_eq(p):
    """compare : '='"""
    p[0] = '='

def p_compare_neq(p):
    """compare : '!' '='"""
    p[0] = '!='

def p_compare_regex(p):
    """compare : ':' REGEXP ':'
               | ':' CIREGEXP ':'"""
    p[0] = ':' + p[2].lower() + ':'

def p_compare_nregex(p):
    """compare : ':' '!' REGEXP ':'
               | ':' '!' CIREGEXP ':'"""
    p[0] = ':!' + p[3].lower() + ':'

ineqmap = { 'lt' : ':lt:', 'leq' : ':leq:', 'gt' : ':gt:', 'geq' : ':geq:',
            'like' : ':like:', 'simto' : ':simto:'}

def p_compare_ineq(p):
    """compare : ':' LT ':'
               | ':' GT ':'
               | ':' LEQ ':'
               | ':' GEQ ':'
               | ':' LIKE ':'
               | ':' SIMTO ':'"""
    p[0] = ineqmap[ p[2].lower() ]

def p_stringset(p):
    """stringset : string ',' string"""
    p[0] = set([p[1], p[3]])

def p_stringset_grow(p):
    """stringset : stringset ',' string"""
    p[0] = p[1]
    p[1].add(p[3])

def p_queryopts(p):
    """queryopts : '?' string '=' string"""
    p[0] = { p[2] : p[4] }

def p_queryopts_set(p):
    """queryopts : '?' string '=' stringset"""
    p[0] = { p[2] : p[4] }

def p_queryopts_short(p):
    """queryopts : '?' string
                 | '?' string '='"""
    p[0] = { p[2] : None }

def p_queryopts_grow(p):
    """queryopts : queryopts '&' string '=' string
                 | queryopts ';' string '=' string"""
    p[0] = p[1]
    if p[0].has_key(p[3]):
        v = p[0][p[3]]
        if type(v) != set:
            v = set([ v ])
            p[0][p[3]] = v
        v.add(p[5])
    else:
        p[0][p[3]] = p[5]

def p_queryopts_grow_set(p):
    """queryopts : queryopts '&' string '=' stringset
                 | queryopts ';' string '=' stringset"""
    p[0] = p[1]
    if p[0].has_key(p[3]):
        v = p[0][p[3]]
        if type(v) != set:
            p[0][p[3]] = v
        v.update(p[5])
    else:
        p[0][p[3]] = p[5]

def p_queryopts_grow_short(p):
    """queryopts : queryopts '&' string
                 | queryopts ';' string
                 | queryopts '&' string '='
                 | queryopts ';' string '='"""
    p[0] = p[1]
    if p[0].has_key(p[3]):
        v = p[0][p[3]]
        if type(v) != list:
            v = set([ v ])
            p[0][p[3]] = v
        v.add(None)
    else:
        p[0][p[3]] = None

def p_transmit_number(p):
    """transmitnumber : slash string slash TRANSMITNUMBER """
    p[0] = url_ast.TransmitNumber(appname=p[2])

def p_study(p):
    """study : slash string slash STUDY"""
    p[0] = url_ast.Study(appname=p[2])

def p_study_num(p):
    """study : slash string slash STUDY slash string"""
    p[0] = url_ast.Study(appname=p[2], data_id=p[6])

def p_study_num_opts(p):
    """study : slash string slash STUDY slash string queryopts"""
    p[0] = url_ast.Study(appname=p[2], data_id=p[6], queryopts=p[7])

def p_study_opts(p):
    """study : slash string slash STUDY queryopts"""
    p[0] = url_ast.Study(appname=p[2], queryopts=p[5])

def p_appleterror(p):
    """appleterror : slash string slash APPLETERROR"""
    p[0] = url_ast.AppletError(appname=p[2])

def p_appleterror_opts(p):
    """appleterror : slash string slash APPLETERROR queryopts"""
    p[0] = url_ast.AppletError(appname=p[2], queryopts=p[5])

# treat any sequence of '/'+ as a path divider
def p_slash(p):
    """slash : '/'
             | slash '/'"""
    pass

def p_filename(p):
    """filename : string"""
    p[0] = p[1]

def p_filename_version(p):
    """filename : string '@' string"""
    try:
        x = int(p[2])
    except:
        raise ParseError(p[3], 'Filename part of URL has invalid version number:')
    p[0] = p[1] + '@' + p[3]

# treat any sequence of '+'+ as a space string
def p_spacestring(p):
    """spacestring : '+'"""
    p[0] = ' '

def p_spacestringlist(p):
    """spacestring : spacestring '+'"""
    p[0] = p[1] + ' '

# grammatically, keywords can also be valid string values...
def p_stringany(p):
    """stub"""
    # weird bit:
    # this doc string is a grammar rule allowing all keywords to be used as string content
    # in contexts where strings are expected.  to avoid this list being inconsistent with
    # changes to the token set, we generate it automatically.
    # this will fail if __doc__ cannot be mutated before yacc reads it
    p[0] = p[1]

p_stringany.__doc__ =  "string : " + " \n| ".join(keywords.values()) + ' \n| STRING \n| spacestring'

def p_stringplus_concat(p):
    """string : string string"""
    p[0] = p[1] + p[2]

class ParseError:
    """Exception for parse errors"""

    def __init__(self, t, message='URL parse error at token:'):
        web.debug(message, t)
        pass

def p_error(t):
    raise ParseError(t)



################################################
# provide wrappers to get a parser instance

def make_parser():
    # use this to shut it up: errorlog=yacc.NullLogger()
    # NullLogger attribute not supported by Python 2.4
    # return yacc.yacc(debug=False, errorlog=yacc.NullLogger())
    return yacc.yacc(debug=False, optimize=0, tabmodule='urlparsetab', write_tables=0)
#    return yacc.yacc()

def make_parse():
    parser = make_parser()
    lexer = make_lexer()
    lock = threading.Lock()
    def parse(s):
        lock.acquire()
        try:
            return parser.parse(s, lexer=lexer)
        finally:
            lock.release()
    return parse

