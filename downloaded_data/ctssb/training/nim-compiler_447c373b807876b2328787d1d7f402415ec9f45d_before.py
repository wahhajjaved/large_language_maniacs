#!/usr/bin/python
import ply.yacc as yacc
import logging
import sys, re
from collections import defaultdict
from pprint import pprint
import threeAC
import st
#get tokens
#import lexer #as ourLexer# our lexer
# tokens = lexer.tok_data
import lexer
tokens = lexer.tokens
import threeAC

TAC = threeAC.ThreeAC()
ST = st.St()
identifier = {}
identifierList = []
functionDict = {}
break_label=None
continue_label=None

def p_start(p):
#ignored extra
#module = stmt ^* (';' / IND{=})
    '''start : stmtIndentSemicolon ENDMARKER
            | stmt ENDMARKER'''
    p[0] = p[1]

def p_stmtIndentSemicolon(p):
    '''stmtIndentSemicolon : stmt NEWLINE stmtIndentSemicolon
                            | stmt SEMICOLON stmtIndentSemicolon
                            | empty'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_stmt(p):
    '''stmt : complexOrSimpleStmt '''
    p[0] = p[1]

    # print "printing stmt in stmt", p[0]

    # if p[0]['type'] != None :
    #     msg_error(p,"syntax error : stmt can not be of any type other than None")

def p_stmtStar(p):                      # changed a bit
    '''stmtStar : stmt NEWLINE stmtStar
                 | stmt SEMICOLON stmtStar
                 | stmt'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_suite(p):                         # changed it too
    '''suite : simpleStmt
                  | NEWLINE INDGR markerSuite stmtStar INDLE'''


    #print ST.curScope
    if len(p) > 2:
        p[0] = p[3]
    else:
        p[0] = p[1]

    # print "printing suite attributes", p[0]

    p[0]['value'] = ST.getCurrentScope()

    ST.endBlock()

def p_markerSuite(p):
    '''markerSuite : empty'''
    p[0]={
    'type' : None,
    'value': None,
    'place': None

    }
    ST.addBlock()

    #print ST.curScope

def p_typeDefSuite(p):                         # changed it too
    '''typeDefSuite : typeDef
              | NEWLINE INDGR typeDefStar INDLE'''
    if len(p) > 2:
        p[0] = p[3]
    else:
        p[0] = [p[1]]

def p_typeDefStar(p):                      # changed a bit
    '''typeDefStar : typeDef NEWLINE typeDefStar
                 | typeDef SEMICOLON typeDefStar
                 | typeDef'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_constantSuite(p):                         # changed it too
    '''constantSuite : constant
              | NEWLINE INDGR constantStar INDLE'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_constantStar(p):                      # changed a bit
    '''constantStar : constant NEWLINE constantStar
                 | constant SEMICOLON constantStar
                 | constant'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_variableSuite(p):                         # changed it too
    '''variableSuite : variable
              | NEWLINE INDGR variableStar INDLE'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = p[1]



def p_variableStar(p):                      # changed a bit
    '''variableStar : variable NEWLINE variableStar
                 | variable SEMICOLON variableStar
                 | variable'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_complexOrSimpleStmt(p):
    '''complexOrSimpleStmt : ifStmt
                            | whenStmt
                            | whileStmt
                            | forStmt
                            | caseStmt
                            | tryStmt
                            | simpleStmt
                            | blockStmt
                            | staticStmt
                            | deferStmt
                            | asmStmt
                            | PROC routine
                            | MACRO routine
                            | ITERATOR routine
                            | METHOD routine
                            | TYPE typeDefSuite
                            | CONST constantSuite
                            | LET variableSuite
                            | VAR variableSuite '''


    if len(p) > 2:
        p[0] = p[2]




    else:
        p[0] = p[1]
                            ## bind and mixin are also not implemented
                            ## we are not implementing 'template' routine , 'converter'





def p_simpleStmt(p):                            ## Scan manually added
    '''simpleStmt : returnStmt
                | raiseStmt
                | yieldStmt
                | discardStmt
                | breakStmt
                | continueStmt
                | pragmaStmt
                | importStmt
                | echoStmt
                | scanStmt
                | fromStmt
                | includeStmt
                | exprStmt
                | incStmt'''


    p[0] = p[1]
    # if p[0]['type']!=None:
    #     msg_error(p,"Statements should not have return type")

## we are not implementing exportStmt

def p_exprStmt(p):
    #not doing lhs expr exprStmtInter2 doBlocks
    # '''exprStmt : simpleExpr
    #             | lhs exprStmtInter
    #             | IDENTIFIER exprStmtInter'''
    # '''exprStmt : simpleExpr
    #             | lhs EQUALS expr
    #             | IDENTIFIER EQUALS expr'''
    '''exprStmt : simpleExpr exprStmtInter'''
    # print p[1],p[2],'hi'
    p[0] = {
        'type': None,
        'value': None,
        'place': None
        }

    if p[2]['type'] == None :     ## for the case when exprstmt goes to simple_expr
        p[0]=p[1]
        return

## whren a = something type thing happens

    if p[2]['type']!= None :
        if ST.getIdenScope(p[1]['value']) == None and 'array' not in p[1]:
            msg_error(p,'should be a variable')
            return
        elif 'array' in p[1] and ST.getIdenScope(p[1]['value']) != None:
            TAC.emit('=',p[1]['array'],p[2]['place'],'')
            return


    if p[1]['type'] != p[2]['type']:
        # print "##",p[1]['type'] ,"xx", p[2]
        msg_error(p,'type mismatch')
        return

    if p[2]['hasVal'] == 0:
        msg_error(p,'rhs has garbage value')
        return

    p[1]['hasVal'] = 1

    if (p[2]['type'] == 'STRLIT'):
        ST.setidenAttr(p[1]['value'], 'hasVal', 1)
        TAC.emit('string',p[1]['place'],p[2]['value'],'')
    else :
        ST.setidenAttr(p[1]['value'], 'hasVal', 1)
        TAC.emit('=',p[1]['place'],p[2]['place'],'')

                                                         ## MUST BE DEALT using Symbol table
    # print "for checking type and value in exprstmt \n"              ## Assuming it computes only identifier = expr type only
    # print "p[1] =", p[1], "p[2] = ", p[2]

    p[0] = {
        'type': None,
        'value': None,
        'place': None
        }





def p_exprStmtInter(p):
    ''' exprStmtInter : EQUALS expr
                      | expr exprStmtInter2 doBlocks
                      | empty'''


    #print "exprstmtinter debug", "p[2] =%", %(p[2])
    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None
        }
    elif(len(p) == 3):


        # print "p[2] in exprstmtinter =", p[2]

        if p[2]['type']=='ERROR_TYPE' :
            msg_error(p,'Unsupported type')

        else:
            # temp = TAC.createTemp()

            p[0] = p[2]
            # p[0] = {
            # 'type': p[2]['type'],
            # 'value': None,
            # 'place': None
            # }

    else :
        msg_error(p,'not implemented right now')


def p_exprStmtInter2(p):
    ''' exprStmtInter2 : COMMA expr exprStmtInter2
                       | empty '''

def p_makeCondLabelsLoop(p):
    ''' makeCondLabelsLoop :  '''
    if p[-2]==None:
        msg_error(p,"Error in Case Expression")
        return
    TAC.emitif('ifgoto', 'neq', p[-2]['place'], 1, p[-3]['end'])

def p_whileStmt(p):
    '''whileStmt : WHILE whileStartLabel expr COLON makeCondLabelsLoop suite whileEndLabel'''

    # print "expr type in whilestmt = ", p[3]['type']
    if p[3]['type'] != 'BOOLEAN' :
        msg_error(p,"expression should be a boolean")



    p[0] = {
    'inline': False,
    'type': p[1],
    'cond': p[3],
    'then': p[6]
    }

def p_whileStartLabel(p):
    '''whileStartLabel : '''
    global break_label,continue_label
    p[0] = {
    'start': TAC.newLabel(),
    'end': TAC.newLabel()
    }
    TAC.emit('label',p[0]['start'],'','')
    break_label=p[0]['end']
    continue_labe=p[0]['end']

def p_whileEndLabel(p):
    '''whileEndLabel : '''
    global break_label,continue_labe
    TAC.emit('goto',p[-5]['start'],'','')
    TAC.emit('label',p[-5]['end'],'','')
    break_label=None
    continue_labe=None

def p_identWithPragmaInter(p):
    '''identWithPragmaInter : COMMA identWithPragma identWithPragmaInter
                            | empty'''
    if len(p)==2:
        p[0]={
        'varlist': []
        }
    else:
        p[0]={
        'varlist': p[3]['varlist']
        }
        p[0]['varlist'].append(p[2]['value'])


def p_identWithPragma(p):
    '''identWithPragma : identVis pragmaInter'''

    p[0] = p[1]         # identVis -> symbol

def p_pragmaInter(p):                               ## assuming pragma -> empty
    '''pragmaInter : pragma
                    | empty'''
    if len(p) == 2 :
        p[0] ={
        'type' : None,
        'value' : None,
        }



def p_pragma(p):
    '''pragma : CURLYDOTLE pragmaInterInter optPar CURLYDOTRI
               | CURLYDOTLE pragmaInterInter optPar CURLYRI'''

def p_pragmaInterInter(p):
    '''pragmaInterInter : expr COLON expr pragmaInter
                   | empty'''

def p_pragmaStmt(p):
    '''pragmaStmt : pragma pragmaStmtInter'''

def p_pragmaStmtInter(p) :
    ''' pragmaStmtInter : COLON suite
                        | empty '''

def p_optpar(p):
    '''optPar : NEWLINE
              | NEWLINE INDGR
              | empty'''

def p_identVis(p):
    '''identVis : symbol '''  # oprInter''' should be opr = `+*` sort of
    p[0] = p[1]

def p_oprInter(p):
    #should be opr
    '''oprInter : empty'''

def p_forStmt(p):
    '''forStmt : FOR identWithPragma identWithPragmaInter IN expr COLON suite'''

def p_tryStmt(p):
    '''tryStmt : TRY COLON suite exceptInter finallyInter'''
    p[0] = {
    'type': p[1],
    'try': p[3],
    'except': p[4],
    'finally': p[5]
    }

def p_exceptInter(p):
    '''exceptInter : EXCEPT expr COLON suite exceptInter
                   | empty'''
    if len(p) > 2:
        p[0] = [{'except': p[2], 'then': p[4]}] + p[5]
    else:
        p[0] = [p[1]]

def p_finallyInter(p):
    '''finallyInter : FINALLY COLON suite
                    | empty'''
    if len(p) > 2:
        p[0] = p[2]
    else:
        p[0] = p[1]

def p_markerlabel(p):
    '''markerlabel : empty'''
    p[0] = {
    'label': TAC.newLabel()
    }
    # TAC.emit('label'  ,p[0]['label'],'','')

def p_markerif(p):
    '''markerif : empty'''
    if p[-1]['cond']['type']!='BOOLEAN':
        msg_error(p,'Condition expressions must be boolean type')

    # TAC.emit('ifgoto','==',p[-1]['cond']['place'],'0',p[-1]['truelabel'])
    # TAC.emit('goto',p[-1]['falselabel'],'','')

def p_markerjump(p):
    '''markerjump : empty'''
    # TAC.emit('goto',p[-1]['endlabel'],'','')

def p_markerend(p):
    '''markerend : empty'''
    p[0] = {
    'label': TAC.newLabel()
    }

def p_whenStmt(p):
    '''whenStmt : WHEN condStmt markerif elifStmt elseStmt'''
    p[0] = {
    'inline': False,
    'type': p[1],
    'cond': p[2]['cond'],
    'then': p[2]['then'],
    'elif': p[4],
    'else': p[5]
    }
    # if p[2]['type']!='BOOLEAN':
    #     msg_error(p,'Condition expressions must be boolean type')
    #     TAC.emit('ifgoto','==',p[2]['cond']['place'],'0',p[2]['truelabel'])
    #     TAC.emit('goto',p[2]['falselabel'])

def p_ifStmt(p):
    '''ifStmt : IF  condStmt  elifStmt elseStmt ifEndLabel'''
    p[0] = {
    'type' : None,
    'value' : None,
    'place' : None
    }



def p_condStmt(p):
    '''condStmt : expr COLON makeCondLabels1 suite endCondLabel'''

    # print "scope of suite = ", p[4]['value']
    if p[1]['type'] != 'BOOLEAN' :
        msg_error(p,"expression should be a boolean")

    # p[0] = {
    # 'inline': False,
    # 'cond': p[1],
    # 'then': p[4],
    # 'truelabel': p[3]['label'],
    # 'falselabel': p[5]['label']
    # }
    p[0] = p[3]

def p_makeCondLabels1(p):
    ''' makeCondLabels1 :  '''
    label1 = TAC.newLabel()
    label2 = TAC.newLabel()
    label3 = TAC.newLabel()
    p[0]=[label1,label2,label3]
    # print "in p_makeCondLabels1 p[-2] = ", p[-2]
    # TAC.emitif('ifgoto', 'eq', p[-2], 1, label1)
    # print p[-2]
    TAC.emitif('ifgoto', 'eq', p[-2]['place'], 1, label1)
    TAC.emit('goto', label2, '', '')
    TAC.emit('label', label1, '', '')

def p_endCondLabel(p):
    ''' endCondLabel :  '''
    TAC.emit('goto', p[-2][2], '', '')
    TAC.emit('label', p[-2][1], '', '')


def p_ifEndLabel(p):
    ''' ifEndLabel : '''
    TAC.emit('label', p[-3][2], '', '')


def p_elseStmt(p):
    '''elseStmt : ELSE COLON suite
                    | empty'''
    if len(p) > 2:
        p[0] = {
        'inline': False,
        'type': p[1],
        'then': p[3]
        }
    else:
        p[0] = p[1]

def p_elifStmt(p):
    '''elifStmt : ELIF condStmt elifStmt elifEndLabel
                    | empty'''
    p[0] = p[-1]

def p_elifEndLabel(p):
    ''' elifEndLabel : '''
    TAC.emit('label', p[-2][2], '', '')


def p_exprList(p):
    '''exprList : expr COMMA exprList
                | expr'''
    if len(p) > 2:
        p[0] = [p[1]] + p[3]
    else:
        p[0] = [p[1]]

def p_MarkerCase(p):
    '''MarkerCase : '''
    p[0] = {
    'expr': p[-4],
    'endlabel':TAC.newLabel()
    }

def p_MarkerCaseEnd(p):
    '''MarkerCaseEnd : '''
    TAC.emit('label',p[-5]['endlabel'],'','')

def p_MarkerExpr(p):
    '''MarkerExpr : '''
    p[0] ={
    'endlabel': p[-4]['endlabel'],
    'nextlabel': TAC.newLabel()
    }
    temp = TAC.createTemp()
    for expr in p[-2]:
        TAC.emitif('ifgoto','!=',expr['place'],p[-4]['expr']['place'],p[0]['nextlabel'])

def p_OfMarkerEnd(p):
    '''OfMarkerEnd : '''
    TAC.emit('goto',p[-2]['endlabel'],'','')
    TAC.emit('label',p[-2]['nextlabel'],'','')

def p_ofBranch(p):
    '''ofBranch : OF exprList COLON MarkerExpr suite OfMarkerEnd'''
    p[0] = {
    'cond': p[2],
    'then': p[4],
    'expr': p[-1]['expr'],
    'endlabel' : p[-1]['endlabel']
    }

def p_ofBranches(p):
    '''ofBranches : ofBranch ofBranches
                    | ofBranch'''
    expr = p[-1]

    if len(p) > 2:
        p[0] = [p[1]] + p[2]
    else:
        p[0] = [p[1]]

def p_caseStmt(p):
    '''caseStmt : CASE expr COLON NEWLINE INDGR MarkerCase ofBranches elifStmt elseStmt INDLE MarkerCaseEnd'''
    p[0] = {
    'inline': False,
    'type': None,
    'case': p[2],
    'branches': p[7],
    'elif': p[8],
    'else': p[9]
    }

def p_echoStmt(p):
    '''echoStmt : ECHO exprList'''
    p[0] = {
    'type': None,
    'echo': p[2]
    }
    for expr in p[2]:
        if expr['type'] == 'CHARLIT' :
                TAC.emit('printchar',expr['place'],'','')
        elif expr['type'] == 'INTLIT' :
            TAC.emit('print',expr['place'],'','')
        elif expr['type'] == 'STRLIT' :
            TAC.emit('printstr',expr['place'],'','')
        elif expr['type'] == 'BOOLEAN' :
            l1 = TAC.newLabel()
            l2 = TAC.newLabel()
            l3 = TAC.newLabel()
            TAC.emitif('ifgoto','eq','1',expr['place'],l1)
            TAC.emit('goto',l2,'','')
            TAC.emit('label',l1,'','')
            strtemp = TAC.createTemp()
            # TAC.emit('string',strtemp,'"true"','')
            TAC.emit('printstr','$trueString','','')
            TAC.emit('goto',l3,'','')
            TAC.emit('label',l2,'','')
            strtemp2 = TAC.createTemp()
            # TAC.emit('string',strtemp2,'"false"','')
            TAC.emit('printstr','$falseString','','')
            TAC.emit('label',l3,'','')





def p_scanStmt(p):
    '''scanStmt : SCAN expr'''              # only one scan allowed
    p[0] = {
    'type': None,
    'scan': p[2]
    }
    expr = p[2]


    ST.setidenAttr(expr['value'], 'hasVal', 1)

    if expr['type'] == 'CHARLIT' :
            TAC.emit('scantchar',expr['place'],'','')
    elif expr['type'] == 'INTLIT' :
        TAC.emit('scan',expr['place'],'','')
    elif expr['type'] == 'STRLIT' :
        TAC.emit('scanstr',expr['place'],'','')




def p_importStmt(p):
    '''importStmt : IMPORT exprList
                | IMPORT expr EXCEPT exprList'''
    if len(p) > 3:
        p[0] = {
        'type': p[1],
        'import': p[2],
        'except': None
        }
    else:
        p[0] = {
        'type': p[1],
        'import': p[2],
        'except': p[4]
        }

def p_includeStmt(p):
    '''includeStmt : INCLUDE exprList''' # should be list of IDENTIFIER instead of exprList
    p[0] = {
    'type': p[1],
    'include': p[2]
    }

def p_fromStmt(p):
    '''fromStmt : FROM IDENTIFIER IMPORT exprList'''
    p[0] = {
    'type': p[1],
    'from': p[2],
    'import': p[4]
    }

def p_returnStmt(p):
    '''returnStmt : RETURN expr
                | RETURN'''
    if len(p) > 2:
        p[0] = {
        'type': None,
        'return': p[2]
        }
    else:
        p[0] = {
        'type': None,
        'return': None
        }
    # print p[1]
    if len(p) > 2:
        TAC.emit('ret',p[2]['place'],'','')
    else:
        TAC.emit('ret','','','')

def p_raiseStmt(p):
    '''raiseStmt : RAISE expr
                | RAISE'''
    if len(p) > 2:
        p[0] = {
        'type': p[1],
        'raise': p[2]
        }
    else:
        p[0] = {
        'type': p[1],
        'raise': None
        }

def p_yieldStmt(p):
    '''yieldStmt : YIELD expr
                | YIELD'''
    if len(p) > 2:
        p[0] = {
        'type': None,
        'yield': p[2]
        }
    else:
        p[0] = {
        'type': None,
        'yield': None
        }
    if len(p) > 2:
        TAC.emit('yield',p[2]['place'],'','')
    else:
        TAC.emit('yield','','','')

def p_discardStmt(p):
    '''discardStmt : DISCARD expr
                | DISCARD'''
    if len(p) > 2:
        p[0] = {
        'type': p[1],
        'discard': p[2]
        }
    else:
        p[0] = {
        'type': p[1],
        'discard': None
        }

def p_breakStmt(p):
    '''breakStmt : BREAK expr
                | BREAK'''
    global break_label
    if len(p) > 2:
        p[0] = {
        'type': None,
        'break': p[2]
        }
    else:
        p[0] = {
        'type': None,
        'break': None
        }
    if break_label==None:
        msg_error(p,'Break outside loop')
    else:
        TAC.emit('goto',break_label,'','')

def p_continueStmt(p):
    '''continueStmt : CONTINUE expr
                | CONTINUE'''
    global continue_label
    if len(p) > 2:
        p[0] = {
        'type': None,
        'continue': p[2]
        }
    else:
        p[0] = {
        'type': None,
        'continue': None
        }
    if continue_label==None:
        msg_error(p,'Continue outside loop')
    else:
        TAC.emit('goto',continue_label,'','')

def p_incStmt(p):
    '''incStmt : INC expr'''
    p[0] = {
    'type': None,
    'increment': p[2]
    }
    TAC.emit('incr',p[2]['place'],'','')

def p_blockStmt(p):
    '''blockStmt : BLOCK symbol COLON suite
                | BLOCK COLON suite'''
    if len(p) > 4:
        p[0] = {
        'type': p[1],
        'symbol': p[2],
        'block': p[4]
        }
    else:
        p[0] = {
        'type': p[1],
        'symbol': None,
        'block': p[3]
        }

def p_staticStmt(p):
    '''staticStmt : STATIC COLON suite'''
    p[0] = {
    'type': p[1],
    'static': p[2]
    }

def p_deferStmt(p):
    '''deferStmt : DEFER COLON suite'''
    p[0] = {
    'type': p[1],
    'defer': p[2]
    }

def p_asmStmt(p):
    '''asmStmt : ASM pragma strings
                | ASM strings'''



def p_expr(p):
    '''expr : ifExpr
            | whenExpr
            | caseExpr
            | simpleExpr'''
    p[0] = p[1]
# Ensure that expr type is INTLIT or BOOLEAN or NONE
# and expr place is temporary variable or none
def p_ifExpr(p):
    '''ifExpr : IF condExpr elifExpr elseExpr ifEndLabel'''
    p[0] = {
    'inline': True,
    'type': p[1],
    'cond': p[2]['cond'],
    'then': p[2]['then'],
    'elif': p[3],
    'else': p[4]
    }

def p_whenExpr(p):
    '''whenExpr : WHEN condExpr elifExpr elseExpr ifEndLabel'''
    p[0] = {
    'inline': True,
    'type': p[1],
    'cond': p[2]['cond'],
    'then': p[2]['then'],
    'elif': p[3],
    'else': p[4]
    }

def p_condExpr(p):
    '''condExpr : expr makeCondLabels1 COLON expr endCondLabel'''

    if p[1]['type'] != 'BOOLEAN' :
        msg_error(p,"expression should be a boolean")


    p[0] = {
    'inline': True,
    'cond': p[1],
    'then': p[3],
    }

def p_elifExpr(p):
    '''elifExpr : ELIF condExpr elifExpr elifEndLabel
        | empty'''
    if len(p) > 2:
        p[0] = {
        'inline': True,
        'type': p[1],
        'cond': p[2]['cond'],
        'then': p[2]['then'],
        'next': p[3],
        }
    else:
        p[0] = p[1]

def p_elseExpr(p):
    '''elseExpr : ELSE COLON expr
        | empty'''
    if len(p) > 2:
        p[0] = {
        'inline': True,
        'type': p[1],
        'then': p[3],
        }
    else:
        p[0] = p[1]

def p_caseExpr(p):
    '''caseExpr : CASE expr COLON NEWLINE INDGR ofBranch ofBranches elifExpr elseExpr INDLE'''
    p[0] = {
    'inline': True,
    'type': p[1],
    'case': p[2],
    'branches': [p[6]] + p[7],
    'elif': p[8],
    'else': p[9]
    }

def p_simpleExpr(p):
    '''simpleExpr : arrowExpr interOne'''
    # p[0] = {
    # 'type' : 'simple'
    # }
    if p[2]['type']==None:
        p[0]=p[1]

def p_interOne(p):
    '''interOne : OP0 arrowExpr interOne
                | empty '''
    p[0] = {
    'type': ("OP0" if len(p) > 2 else None),
    'value': p[1]
    }
    if len(p) > 2:
        msg_error(p,"Arrow like Operators not supported")

def p_arrowExpr(p):
    '''arrowExpr : assignExpr
                | assignExpr OP1 assignExpr'''
    if len(p)==2:
        p[0] = p[1]
    else:
        p[0] = {
        'place': 'undef',
        'type': 'ERROR_TYPE'
        }
        if p[1]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
            msg_error(p,'Unsupported type')
        elif p[1]['type']!=p[3]['type']:
            msg_error(p,'Type mismatch')

        elif p[1]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
            msg_error(p,'rhs has garbage value')
            return

        else:
            TAC.emit(p[2][0],p[1]['place'],p[1]['place'],p[3]['place'])
            p[0] = p[1]
        # p[0] = {
        # 'type:' ("OP1" if len(p) > 2 else None),
        # 'value': p[1],
        # 'place'
        # }

# def p_interTwo(p):
#     '''interTwo : OP1 assignExpr interTwo
#                 | empty '''

def p_assignExpr(p):
    '''assignExpr : orExpr interThree'''
    if p[2]['type']==None:
        p[0]=p[1]


def p_interThree(p):
    '''interThree : OP2 orExpr interThree
                | empty '''
    p[0] = {
    'type': ("OP2" if len(p) > 2 else None),
    'value': p[1]
    }
    if len(p) > 2:
        msg_error(p,p[1]+" operators not supported")

def p_orExpr(p): # Assuming Bitwise integer operations
    '''orExpr : andExpr interFour'''
    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'hasVal':1,
        'val':None
        }

def p_interFour(p):
    '''interFour : OR andExpr interFour
                | XOR andExpr interFour
                | empty '''
    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal': 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal': 1
        }


def p_andExpr(p):
    '''andExpr : cmpExpr interFive'''
    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'value':None,
        'hasVal': 1
        }

def p_interFive(p):
    '''interFive : AND cmpExpr interFive
                | empty '''
    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal': 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')
    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal': 1
        }

def p_cmpExpr(p):
    '''cmpExpr : sliceExpr interSix'''
    if p[2]['place']==None:
        p[0]=p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    elif p[1]['type']=='BOOLEAN':
        msg_error(p,"Boolean not allowed in comparision statements")
    else:
        temp = TAC.createTemp()
        label1 = TAC.newLabel()
        label2 = TAC.newLabel()
        # print p[1],p[2],"hi"
        TAC.emitif('ifgoto',p[2]['value'],p[1]['place'],p[2]['place'],label1)
        TAC.emit('=', temp, 0,'')
        TAC.emit("goto", label2,'','')
        TAC.emit("label", label1,'','')
        TAC.emit('=', temp, 1,'')
        TAC.emit("label", label2,'','')
        p[0] = {
        'type': 'BOOLEAN',
        'place': temp,
        'value' : None,
        'hasVal': 1
        }


def p_interSix(p):
    '''interSix : OP5 sliceExpr interSix
                | empty '''

    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal': 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit('ifgoto',p[3]['value'],p[2]['place'],p[3]['place'],label1['name'])
        TAC.emit('=', temp, 0)
        TAC.emit("goto", label2['name'])
        TAC.emit("label", label1['name'])
        TAC.emit('=', temp, 1)
        TAC.emit("label", label2['name'])
        p[0] = {
        'type': 'BOOLEAN',
        'value': p[1],
        'place': temp,
        'hasVal': 1
        }

def p_sliceExpr(p):           # ignored right now just like arrow
    '''sliceExpr : ampExpr interSeven'''

    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'val' : None,
        'hasVal': 1
        }



def p_interSeven(p):
    '''interSeven : DOTDOT ampExpr interSeven
                | empty '''

    if len(p)>2:
        msg_error(p,'DOT DOT not implemented right now')
    elif len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal': 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal' : 1
        }

def p_ampExpr(p):                           # ignored right now just like arrow
    '''ampExpr : plusExpr interEight'''

    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'value' : None,
        'hasVal' : 1
        }



def p_interEight(p):
    '''interEight : OP7 plusExpr interEight
                | empty '''

    if len(p)>2:
        msg_error(p,'& not implemented right now')
    elif len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal' : 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')


    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal' : 1
        }
def p_plusExpr(p):
    '''plusExpr : mulExpr interNine'''

    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')


    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'value' : None,
        'hasVal' : 1
        }


def p_interNine(p):
    '''interNine : OP8 mulExpr interNine
                | empty '''

    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal' : 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')


    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal' : 1
        }

def p_mulExpr(p):
    '''mulExpr : dollarExpr interTen'''

    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')


    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'hasVal' : 0,
        'value' : None
        }

def p_interTen(p):
    '''interTen : OP9 dollarExpr interTen
                | empty '''

    if len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal' : 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal' : 1
        }


def p_dollarExpr(p):
    '''dollarExpr : primary interElev'''

    if p[2]['place']==None:
        p[0] = p[1]
    elif p[1]['type']=='ERROR_TYPE' or p[2]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[1]['type']!=p[2]['type']:
        msg_error(p,'Type mismatch')

    elif p[1]['hasVal'] == 0 or p[2]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')

    else:
        temp = TAC.createTemp()
        TAC.emit(p[2]['value'],temp,p[1]['place'],p[2]['place'])
        p[0] = {
        'type': p[1]['type'],
        'place': temp,
        'hasVal' : 1,
        'value' : None
        }

def p_interElev(p):
    '''interElev : OP10 primary interElev
                | empty '''

    if len(p)>2:
        msg_error(p,'$ and ^ not implemented right now')
    elif len(p)==2:
        p[0] = {
        'type': None,
        'value': None,
        'place': None,
        'hasVal' : 0
        }
    elif p[2]['type']=='ERROR_TYPE' or p[3]['type']=='ERROR_TYPE':
        msg_error(p,'Unsupported type')
    elif p[3]['place']==None:
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': p[2]['place'],
        'hasVal' : 1
        }
    elif p[2]['type']!=p[3]['type']:
        msg_error(p,'Type mismatch')

    elif p[2]['hasVal'] == 0 or p[3]['hasVal'] == 0 :
        msg_error(p,'rhs has garbage value')


    else:
        temp = TAC.createTemp()
        TAC.emit(p[3]['value'],temp,p[2]['place'],p[3]['place'])
        p[0] = {
        'type': p[2]['type'],
        'value': p[1],
        'place': temp,
        'hasVal' : 1
        }

def p_castExpr(p):
    '''castExpr : CAST BRACKETLE simpleExpr BRACKETRI PARLE expr PARRI'''

def p_primary(p):
    '''primary : typeKeyw typeDescK
                | interPrefixOperator identOrLiteral interPrimarySuffix
                | STATIC primary
                | BIND primary'''

    # if len(p)!=4:
    #     msg_error(p,'currently primary can go to only identOrLiteral')
    # else :
    #     p[0] = p[2]
    if len(p)!=4:
        p[0] = p[2]
        msg_error(p,'Operation not supported')
    elif p[3]['type']==None:
        p[0] = p[2]
    elif p[3]['type']=='CALL':
        if p[2]['type']!=None:
            p[0] = p[2]
            msg_error(p,'Improper function name')
        elif p[2]['value'] not in functionDict:
            p[0] = p[2]
            msg_error(p,'Function not declared')
        else:
            temp = TAC.createTemp()
            print "p[3] in primary =", p[3]
            for param in p[3]['params']:
                TAC.emit('push',param,'','')


            TAC.emit('call','',p[2]['value'],temp)
            p[0] = p[2]
            p[0] = {
            'type': functionDict[p[2]['value']],
            'place': temp,
            'value': functionDict[p[2]['value']],
            'hasVal': 1
            }
    elif p[3]['type']=='ARRAY':
        if p[2]['type']==None:
            p[0] = p[2]
            msg_error(p,'Improper array name')
        elif ST.getIdenScope(p[2]['value'])==None:
            p[0] = p[2]
            msg_error(p,'Array not declared')
        else:
            temp = TAC.createTemp()
            # print p[3],'hi'
            TAC.emit('=',temp,ST.getIdenAttr(p[2]['value'],'place')+'['+p[3]['place']+']','')
            p[0] = p[2]
            p[0] = {
            'type': ST.getIdenAttr(p[2]['value'],'type'),
            'place': temp,
            'value': p[2]['value'],
            'hasVal': 1,
            'array': ST.getIdenAttr(p[2]['value'],'place')+'['+p[3]['place']+']'
            }

    # print " p[1] in primary", p[1]
    if p[1]['value'] == '-' :
        # print " reached primary where p[1] = - "
        placeOfIdentOrLiteral = p[0]['place']
        TAC.emit('-',placeOfIdentOrLiteral,'0',placeOfIdentOrLiteral)

#shd be interPrefixOperator identOrLiteral interPrimarySuffix

def p_interPrefixOperator(p):
    # '''interPrefixOperator : prefixOperator interPrefixOperator               # Currently only one operator is allowed
    #                         | empty '''

    '''interPrefixOperator : prefixOperator
                            | empty '''
    if p[1]['type'] == None :
        p[0] = {
        'type': None,
        'value': None,
        'place': None
        }
    else :
        p[0] = p[1]       ## p[1]['type'] = 'operator' and p[1]['value'] = operator symbol
        # msg_error(p,'currently interPrefixOperator -> empty')  ## now our prefix operator can go to ! and - only

def p_interPrimarySuffix(p):
    '''interPrimarySuffix : primarySuffix interPrimarySuffix
                            | empty '''
    if len(p) == 2 :
        p[0] = {
        'type': None,
        'value': None,
        'place': None
        }
    elif p[2]['type']!=None:
        p[0] = p[1]
        msg_error(p,'Multidimentional arrays not allowed')
    else:
        p[0]=p[1]

def p_identOrLiteral(p):
    # '''identOrLiteral : symbol
    #                   | literal
    #                   | par
    #                   | IDENTIFIER'''
    '''identOrLiteral :  literal
                        | castExpr
                        | arrayConstr
                        | tupleConstr
                        | symbol '''
    # '''identOrLiteral :  literal
    #                     | castExpr
    #                     | symbo-l
    #                     | lhs'''

    p[0] = p[1]
    # temp = TAC.createTemp()
    # print "identorliteral", temp, p[1]['place']

    # TAC.emit('=',temp,p[1]['place'],'')
    # p[0] = {
    # 'type': (p[1]['type'] if p[1]!=None else None),
    # 'value': p[1],
    # 'place': temp
    #     }

def p_lhs(p):
    '''lhs : arrayConstr
            | tupleConstr'''
    p[0] = p[1]

def p_arrayConstr(p):
    ''' arrayConstr : BRACKETLE arrayConstrInter BRACKETRI '''

def p_arrayConstrInter(p) :
    ''' arrayConstrInter : exprColonEqExpr COMMA arrayConstrInter
                         | exprColonEqExpr  arrayConstrInter
                         | empty'''


def p_tupleConstr(p):
    ''' tupleConstr : PARLE tupleConstrInter PARRI '''

def p_tupleConstrInter(p) :
    ''' tupleConstrInter : exprColonEqExpr COMMA tupleConstrInter
                         | exprColonEqExpr  tupleConstrInter
                         | empty'''


def p_exprColonEqExpr(p) :
    ''' exprColonEqExpr : expr
                        | expr COLON expr
                        | expr EQUALS expr '''
    if len(p)==2:
        p[0] = p[1]
    elif p[2]==':':
        msg_error(p,'Ranges not supported')
    elif p[1]==None or p[3]==None:
        msg_error(p,'Empty expression')
    elif p[1]['type']!=p[3]['type']:
        p[0]=p[1]
        msg_error(p,'Type mismatch')
    else:
        temp = TAC.createTemp()
        TAC.emit('=',p[1]['place'],p[2]['place'],'')
        p[0] = {
        'type': p[1]['type'],
        'hasVal': 1,
        'place': temp,
        'value': None
        }

def p_typeKeyw(p):
    '''typeKeyw : VAR
                | OUT
                | PTR
                | REF
                | SHARED
                | TUPLE
                | ARRAY
                | PROC
                | ITERATOR
                | DISTINCT
                | OBJECT
                | ENUM
                | INT
                | INT8
                | INT16
                | INT32
                | INT64
                | FLOAT
                | FLOAT8
                | FLOAT16
                | FLOAT32
                | FLOAT64
                | CHAR
                | STRING '''
    p[0] = p[1]

def p_typeDescK(p):
    '''typeDescK : simpleExpr
                 | empty'''
    p[0] = p[1]

def p_primarySuffix(p):
    '''primarySuffix : doBlocks
                     | PARLE primarySuffixInter PARRI
                     | DOT symbol
                     | BRACKETLE exprList BRACKETRI
                     | CURLYLE exprList CURLYRI'''
    p[0] = {}
    if p[1]=='(':
        p[0]['type'] = 'CALL'
        params = []
        if p[2]!=None:
            print "p[2] in p_primarySuffix", p[2]
            for i in p[2]:
                if i!=None:
                    if i['type']!=None:
                        params.append(i['place'])
        p[0]['params'] = params
    elif p[1]=='.':
        p[0]['type'] = 'ERROR_TYPE'
        msg_error(p,'Objects not allowed')
    elif p[1]=='[':
        p[0]['type'] = 'ARRAY'
        if p[2]!=[] or p[2]!=[{}] or p[2]!= [[]]:
            if len(p[2])>1:
                msg_error(p,"Ranges not allowed")
            elif p[2][0]['type']==None or p[2][0]['type']=='ERROR_TYPE':
                msg_error(p,'Unsupported Type')
            else:
                p[0]['place'] = p[2][0]['place']
    elif p[1]=='{':
        p[0]['type'] = 'SET'
    else:
        p[0]['type'] = 'DO'

## we are not implementing generalised lit etc  ## Last rule is also not implemented

def p_primarySuffixInter(p):
    ''' primarySuffixInter : exprColonEqExpr COMMA primarySuffixInter
                           | exprColonEqExpr  primarySuffixInter
                           | empty'''

    print "len in primarySuffixInter", len(p)

    if len(p)==2:
        p[0] = [p[1]]

    elif len(p)==3 :
        # print "p[1] and p[2] and p[3] in p_primarySuffixInter =", p[1],p[2]
        p[0] = [p[1]] + p[2]

    elif len(p)==4 :
        # print "p[1] and p[2] and p[3] in p_primarySuffixInter =", p[1],p[2]
        p[0] = [p[1]] + p[3]


def p_prefixOperator(p):
    '''prefixOperator : operator'''

    p[0]= p[1]

def p_symbol(p):
    '''symbol : IDENTIFIER'''
#                | ADDR'''
#                | BOOLEAN'''
    #           | TYPE

    # print "$$$$$$ \n"
    # print p[1]
    # print "$$$$$$ \n"

    if(ST.getIdenScope(p[1]) == None):
        # temp = TAC.createTemp()
        #print "symbol fdfdfd", temp, p[1]
        #TAC.emit('=',temp,p[1],'')
        p[0] = {
        'type': None,
        'place': None ,
        'value' : p[1],
        'hasVal' : 0
        }
        # ST.addIden(p[0]['value'],p[0]['place'],p[0]['type'])
    else :
        iplace = ST.getIdenAttr(p[1], 'place')
        itype = ST.getIdenAttr(p[1], 'type')
        ihasVal = ST.getIdenAttr(p[1], 'hasVal')
        p[0] = {
        'type': itype,
        'place': iplace,
        'value' : p[1],
        'hasVal' : ihasVal
        }

def p_literal(p):# was INTLIT in place of INT
    '''literal : int
                | char
                | strings '''
                # | INT8LIT
                # | INT32LIT
                # | INT16LIT
                # | INT64LIT
                # | FLOATLIT
                # | FLOAT32LIT
                # | FLOAT64LIT
                # | CHARLIT
                # | strings

                # | NIL'''
 #boolean also added
    p[0]=p[1]

def p_int(p):
    '''int : INTLIT
            | BOOLEAN'''

    temp = TAC.createTemp()
    # print "literal ---",temp,p[1], p.slice[1].type
    TAC.emit('=',temp,p[1],'')

    p[0] = {
    'type': p.slice[1].type,
    'value': p[1],
    'place': temp,
    'hasVal': 1
    }

def p_char(p):
    '''char : CHARLIT '''

    temp = TAC.createTemp()
    # print "literal ---",temp,p[1], p.slice[1].type
    # print "type of p[1]= ", type(p[1])
    # print " using list to get char ", list(p[1]),list(p[1])[0]
    # print "ASCII of p[1] = ", ord(list(p[1])[0])

    strAscii = str(ord(p[1]))

    TAC.emit('=',temp,strAscii,'')

    p[0] = {
    'type': p.slice[1].type,
    'value': ord(p[1]),                 ## ord() gives ASCII
    'place': temp,
    'hasVal': 1
    }

    # print "p[0] in char", p[0]


def p_strings(p):
    # '''strings : STRLIT
    #             | RSTRLIT
    #             | TRIPLESTRLIT'''

    '''strings : STRLIT
                | RSTRLIT
                | TRIPLESTRLIT'''
    temp = TAC.createTemp()
    # print "p[1] in strings = ", p[1]
    TAC.emit('string',temp,p[1],'')
    p[0]={
    'type': 'STRLIT',
    'place': temp,
    'value': p[1],
    'hasVal': 1
    }

# def p_par(p):

# def p_int(p):
#     ''' int : INTLIT '''
#     temp = TAC.createTemp()
#     TAC.emit('=',temp,p[1],'','')
#     p[0] = {
#     'type': 'int',
#     'value': p[1],
#     'place': temp
#     }

def p_doBlocks(p):
    '''doBlocks : doBlock NEWLINE doBlocks
                | empty '''
    if len(p) > 2:
        p[0] = {
        'type': 'do',
        'blocks': [p[1]] + p[3]
        }
    else:
        p[0] = {
        'type': 'do',
        'blocks': [p[1]]
        }

def p_doBlock(p):
    '''doBlock : DO COLON suite'''
    p[0] = p[3]

def p_operator(p):
    '''operator : OP0
                | OP1
                | OP2
                | OP5
                | OP6
                | OP7
                | OP8
                | OP9
                | OR
                | AND
                | XOR
                | IS
                | ISNOT
                | NOTIN
                | IN
                | OF
                | DIV
                | MOD
                | SHL
                | SHR
                | NOT
                | STATIC
                | DOTDOT'''
    p[0] = {
    'value' : p[1],
    'type' : 'operator'
    }


def p_routine(p):
    ''' routine :  identVis markerFuncLabel paramListColon markerRoutine EQUALS suite  '''
    #  Uncomment it after pulling from rajni
    functionDict[p[1]['value']] = p[3]['returnType']
    # print "printing dict =", functionDict

    ST.endBlock()
    p[0] = {
    'varlist' : p[3]['varlist'], #p[2]['varlist'] has 2 attributes name and type
    'type' : None,
    'value': p[1]['value'],
    'returnType' : p[3]['returnType']
    }

    TAC.emit('ret','','','')
    TAC.emit('label', "end"+p[0]['value'],'','')
    # print "p[1] in routine" , p[1]

def p_markerFuncLabel(p) :
    ''' markerFuncLabel : empty '''
    p[0] = p[-1]
    if p[0]['value'] in functionDict:
        msg_error(p,'Two functions with same name')
    functionDict[p[0]['value']] = "INTLIT"
    TAC.emit('goto', "end"+p[0]['value'],'','')
    TAC.emit('label', p[0]['value'],'','')



## need to update hasValue


def p_markerRoutine(p) :
    ''' markerRoutine : empty '''

    p[0]={
    'type' : None,
    'value': None,
    'place': None,
    'varlist': p[-1]['varlist']

    }
    ST.addBlock()


    if p[0]['varlist'] != None :

        newScope = ST.getCurrentScope()
        # print "now new scope = ", newScope


        # print "p[0]['varlist']", p[0]['varlist']
        for i in p[0]['varlist'] :
            temp = TAC.createTemp()
            # print "var name and var type = ",p[0]['varlist'][i]['varName'],p[0]['varlist'][i]['varType']
            ST.addIdenInScope(newScope,p[0]['varlist'][i]['varName'],temp,p[0]['varlist'][i]['varType'],1)
            if p[0]['varlist'][i]['varValue'] != None :
                TAC.emit('=',temp,p[0]['varlist'][i]['varValue'],'')


def p_markerFuncLabelRet(p) :
    ''' markerFuncLabelRet : empty '''

    TAC.emit('ret', '','','')


def p_typeKeyww(p):
    ''' typeKeyww : INT
                    | FLOAT
                    | CHAR
                    | BOOL
                    | STRING '''
    p[0] = {
        'type': None,
        'size':None
    }
    if p[1]=='int':
        p[0]['type']='INTLIT'
    elif p[1]=='bool':
        p[0]['type']='BOOLEAN'
    elif p[1]=='char':
        p[0]['type']='CHARLIT'
    elif p[1]=='string':
        p[0]['type']='STRLIT'


    # print 'hi'
    # print p[0]['type']

def p_paramListColon(p):
    ''' paramListColon : paramListInter
                        | paramListInter COLON typeKeyww'''  # changed from paramListInter COLON typeDescK
    p[0] = {
    'varlist': (p[1]['varlist'] if p[1]['type'] != None else None ),
    'returnType': (p[3]['type'] if len(p)>2 else None),
    'type' : 'paramListColon'
    }



def p_paramListInter(p):
    ''' paramListInter : PARLE declColonEqualsInter2 PARRI'''

    if p[2]['type'] == None :
        p[0]={
        'type' : None
        }

    else :
        p[0] = {
        'varlist' : p[2]['varlist'],
        'type' : p[2]['type']
        }
    # print "p[0] after paramListInter = ", p[0]

def p_declColonEqualsInter2(p):
    ''' declColonEqualsInter2 : empty
                              | declColonEqualsInter '''
    if p[1]['type'] == None :
        p[0]={
        'type' : None
        }
    else :
        p[0] ={
        'varlist' : p[1]['varlist'],
        'type' : 'notNone'
        }
    # print "p[0] after declColonEqualsInter2 = ", p[0]

def merge_two_dicts(x, y):
    '''Given two dicts, merge them into a new dict as a shallow copy.'''
    z = x.copy()
    z.update(y)
    return z

def p_declColonEqualsInter(p):
    ''' declColonEqualsInter : declColonEquals COMMA declColonEqualsInter
                            |  declColonEquals SEMICOLON declColonEqualsInter
                            |  declColonEquals  '''



    if len(p) == 2:
        p[0]={
        'varlist' : p[1]['varlist'],
        'type' : 'notnone'
        }
    else:
        # print "p[3] in declColonEqualsInter = ", p[3]
        # print "p[1] in declColonEqualsInter = ", p[1]

        p[0] ={
        'varlist' : merge_two_dicts(p[3]['varlist'], p[1]['varlist']),
        'type' : 'notnone'
        }

    # print "p[0] after declColonEqualsInter = \n *****", p[0]

    ## original rule : routine = optInd identVis pattern? genericParamList? paramListColon pragma? ('=' COMMENT? stmt)? indAndComment
    ## pattern is used in template hence not implemented

def p_declColonEquals(p) :
    ''' declColonEquals : commaIdentWithPragmaInter commaInter colonTypeDescKInter equalExprInter'''

    # print "p[1] in descolonequals =", p[1]

    varNameList = p[1]['varlist']
    varType = p[3]['type']
    eqExpr = p[4]['place']

    # print "varType = p[3]['type'] in declColonEquals ",varType, "and p[3] =", p[3]


    # print "p[4]= in deccolonequals", p[4]


    l={}
    for i in varNameList :
        l[i]={
        'varName' : i,
        'varType' : varType,
        'varValue' : eqExpr              ## will be none if p[4] = none
        }
    # print " printing list in declColonEquals", l
    p[0]={
    'varlist':l,
    'type' : varType
    }
    # print "p[0]= after deccolonequals", p[0]




    # p[0] = { # Not sure what identColonEqualsInter2 does
    # 'vars': p[1],
    # 'type': p[3],
    # 'value': p[4]
    # }
    # for i in p[0]['vars']:
    #     if i in identifierList:
    #     msg_error(p,"Redeclaring Variable \"" + str(i) + "\"")
    #     else:
    #         identifier[i] = {'type': p[3], 'value': p[4]}
    #         identifierList.append(i)

def p_commaIdentWithPragmaInter(p) :                            #currently identWithPragma = symbol
    '''commaIdentWithPragmaInter : identWithPragma
                                  | COMMA identWithPragma commaIdentWithPragmaInter '''

    if len(p) == 2 :
        p[0]={
        'varlist': []
        }
        p[0]['varlist'].append(p[1]['value'])
    else :
        p[0]={
        'varlist': p[3]['varlist']
        }
        p[0]['varlist'].append(p[2]['value'])

    # if len(p) > 2:
    #     p[0] = [p[2]] + p[3]
    # else:
    #     p[0] = [p[1]]

def p_commaInter(p): # Not sure what this does
    ''' commaInter : COMMA
                   | empty'''

def p_colonTypeDescKInter(p):
    ''' colonTypeDescKInter : COLON typeKeyww
                            | empty '''       # changed from COLON typeDescK
    if len(p) > 2:
        p[0] = {
        'type' : p[2]['type']
        }
    else:
        p[0]={
        'type' : None
        }

def p_equalExprInter(p):
    ''' equalExprInter : EQUALS expr
                            | empty '''
    if len(p) > 2:
        p[0] = p[2]
    else:
        p[0]={
        'type' : None,
        'place' :None
        }

def p_typeDef(p) :
    ''' typeDef : identWithPragma genericParamListInter EQUALS typeDefAux '''

def p_typeDefAux(p) :
    '''  typeDefAux : simpleExpr   '''
    p[0] = p[1]
##  concept not implemented

def p_genericParam(p) :
    '''  genericParam : symbol genericParamInter1 genericParamInter2 genericParamInter3   '''

def p_genericParamInter1(p) :
    ''' genericParamInter1 : COMMA symbol genericParamInter1
                           | empty '''

def p_genericParamInter2(p) :
    ''' genericParamInter2 : COLON expr
                           | empty '''


def p_genericParamInter3(p) :
    ''' genericParamInter3 : EQUALS expr
                           | empty '''

def p_genericParamListInter(p):
    ''' genericParamListInter : genericParamList
                              | empty '''

def p_genericParamList(p):
    '''genericParamList  : BRACKETLE genericParamInter4 optPar BRACKETRI   '''


def p_genericParamInter4(p):
    ''' genericParamInter4 : empty
                              | genericParamInter5 '''

def p_genericParamInter5(p):
    ''' genericParamInter5 : genericParam COMMA genericParamInter5
                            |  genericParam SEMICOLON genericParamInter5
                            |  genericParam  '''


def p_constant(p) :
    ''' constant : identWithPragma constantInter1 EQUALS expr'''

def p_constantInter1(p) :
    ''' constantInter1 : empty
                       | COLON typeKeyww '''

def p_variable(p):
    ''' variable : varTuple
                 | identColonEquals '''
    p[0] = p[1]

def p_varTuple(p) :
    ''' varTuple : PARLE identWithPragma varTupleInter PARRI EQUALS expr '''

def p_varTupleInter(p) :
    ''' varTupleInter : COMMA identWithPragma varTupleInter
                      | empty '''

def p_identColonEquals(p) :
    ''' identColonEquals : identColonEqualsInter1 identColonEqualsInter2 identColonEqualsInter3 identColonEqualsInter4  '''
    p[0] = { # Not sure what identColonEqualsInter2 does
    'varlist': p[2]['varlist'],
     'type': None,
     'value': None
    }

    # print " p[4] in identcolonequal = ", p[4]

    p[0]['varlist'].append(p[1]['value'])
    for i in p[0]['varlist']:
        temp = TAC.createTemp()
        ST.addIden(i,temp,None,0,None)
    if p[3]['type']!=None and p[4]['type']!=None:
        if p[3]['type'] != p[4]['type']:
            msg_error(p,'Type mismatch')
            return
        elif p[4]['hasVal'] == 0 :
            msg_error(p,'rhs has garbage value')
            return
        for i in p[0]['varlist']:
            # ST.setidenAttr(i,'place',p[4]['place'])
            if p[4]['type'] == 'STRLIT' :
                place = ST.getIdenAttr(i,'place')
                TAC.emit('string', place, p[4]['value'], '' )
                ST.setidenAttr(i,'type',p[4]['type'])
                ST.setidenAttr(i,'hasVal',1)
            else :
                place = ST.getIdenAttr(i,'place')
                TAC.emit('=', place, p[4]['place'], '' )
                ST.setidenAttr(i,'type',p[4]['type'])
                ST.setidenAttr(i,'hasVal',1)

    elif p[3]['type']!=None:
        if p[3]['size']!=None:
            for i in p[0]['varlist']:
                TAC.emit('array',ST.getIdenAttr(i,'place'),p[3]['size'],p[3]['type'])
                ST.setidenAttr(i,'type',p[3]['type'])
                ST.setidenAttr(i,'size',p[3]['size'])
        else:
            for i in p[0]['varlist']:
                ST.setidenAttr(i,'type',p[3]['type'])
    elif p[4]['type']!=None:

        for i in p[0]['varlist']:

            if p[4]['type'] == 'STRLIT' :
                place = ST.getIdenAttr(i,'place')
                TAC.emit('string', place, p[4]['value'], '' )
                ST.setidenAttr(i,'type',p[4]['type'])
                ST.setidenAttr(i,'hasVal',1)
            else :
                place = ST.getIdenAttr(i,'place')
                TAC.emit('=', place, p[4]['place'], '' )
                ST.setidenAttr(i,'type',p[4]['type'])
                ST.setidenAttr(i,'hasVal',1)


    # print "debug in identColonEquals"
    # print ST.St[ST.curScope]['identifiers']
    # print " ^^\n"
    # print p[2]['varlist']
    # print p[0]['varlist']
    # for i in p[2]['varlist']:
    #     if i in identifierList:
    #         msg_error(p,"Redeclaring Variable \"" + str(i) + "\"")
    #     else:
    #         # identifier[i] = {'type': p[3], 'value': p[4]}
    #         identifierList.append(i)

def p_identColonEqualsInter1(p) :
    ''' identColonEqualsInter1 : identOrLiteral'''
                              # | COMMA identOrLiteral identColonEqualsInter1'''
    # if len(p) > 2:
    #     p[0] = [p[2]] + p[3]
    # else:
    p[0] = p[1]

def p_identColonEqualsInter2(p) :
    ''' identColonEqualsInter2 : empty
                               | COMMA identOrLiteral identColonEqualsInter2'''
    if len(p)==2:
        p[0]={
        'varlist': []
        }
    else:
        p[0]={
        'varlist': p[3]['varlist']
        }
        p[0]['varlist'].append(p[2]['value'])

def p_identColonEqualsInter3(p) :
    ''' identColonEqualsInter3 : empty
                               | COLON typeKeyww
                               | COLON ARRAY BRACKETLE int COMMA typeKeyww BRACKETRI'''
    if len(p) == 3:
        p[0] = p[2]
    elif len(p) ==2:
        p[0]={
            'type':None,
            'size':None
        }
    else:
        p[0] = {
        'type': p[6]['type'],
        'size': p[4]['value']
        }

def p_identColonEqualsInter4(p) :
    ''' identColonEqualsInter4 : empty
                               | EQUALS expr '''
    if len(p) > 2:
        p[0] = p[2]
    else:
        p[0]={
            'type': None
        }
msg = ''

def msg_error(p,_msg=''):
    global msg
    msg = ": " + _msg
    p_error(p)
    msg = ''

def p_error(p):
    global msg
	# global haltExecution
	# haltExecution = True
    try:
		print "Syntax Error near '"+str(p.stack[-1].value)+ "' in line "+str(p.stack[-1].lineno) + str(msg)
    except:
		try:
			print "Syntax Error in line "+str(p.stack[-1].lineno) + str(msg)
		except:
			print "Syntax Error" + str(msg)

	# sys.exit()

# def p_
# def p_
# def p_
# def p_
# def p_
# def p_
# def p_
# def p_
# def p_

#for epsilon
def p_empty(p):
    'empty :'

    p[0] = {
    'type' : None
    }

# Error rule for syntax errors
# def p_error(p):
#     print("Syntax error!")

# Build the parser
logging.basicConfig(
    level = logging.DEBUG,
    filename = "parselog.txt",
    filemode = "w")
log = logging.getLogger()
parser = yacc.yacc()

def parseProgram(program):
    parser.parse(program, lexer=lexer)
    pprint(result)

# a function to test the parser
def testYacc(inputFile):
    program = open(inputFile)
    data = program.read()
    customLexer = lexer.customLexer()
    result=parser.parse(data, lexer=customLexer, debug=log)
    # pprint(result)               # removed as we don't know what it does : Preetansh
    # print "now printing TAC code"
    TAC.printCode()
    # parser.parse(program, lexer=lexer, debug=1)

if __name__ == "__main__":
    from sys import argv
    filename, inputFile = argv
    testYacc(inputFile)

    # # to print TAC code
    # TAC.printCode()


    #code to get reduced rules as an output file
    actionfile = open("actionfile.txt", 'w')
    with open("parselog.txt") as f:
        for line in f:
            if line.startswith("INFO:root:Action"):
                actionfile.write(line)
    invert = []
    actionfile = open("actionfile.txt", 'r')
    reverselist = open("reverselist.txt", 'w')
    for line in actionfile:
        rule = re.findall('rule \[(.*)\] with', line)
        if (rule[0]!="empty -> <empty>"):
            reverselist.write(rule[0]+'\n')
            invert.append(rule[0]+'\n')
    #reverselist.txt contains the final production rules
    actionfile.close()
    reverselist.close()
    rulelist = open("rulelist.txt","w")
    while invert:
        rulelist.write(invert.pop())
    rulelist.close()
    #code to create the graphviz flowchart
    nodeno = 1;
    nodes = defaultdict(list)
    data = open(inputFile)
    inputFile = inputFile[0:len(inputFile)-4]
    reverselist = open("reverselist.txt",'r')
    dotfile = open(inputFile+".dot",'w')
    dotfile.write("digraph G {"+"\n graph [ordering=\"out\"];\n")
    for line in reverselist:
        # if "empty -> <empty>" in line: continue
        colsplit = line.split(" ")
        k = len(colsplit)-1
        colsplit[k] = colsplit[k][0:len(colsplit[k])-1]
        pid = nodeno
        innode="node"+str(nodeno)
        dotfile.write(innode+" [ label = \""+colsplit[0]+"\" ];\n")
        nodeno+=1
        for i in range(2,len(colsplit)):
            if colsplit[i] in nodes:
                temp = nodes[colsplit[i]].pop(len(nodes[colsplit[i]])-1)
                outnode="node"+str(temp)
                dotfile.write(innode+" -> "+outnode+";\n")
                if len(colsplit[i])==0:
                    del nodes[colsplit[i]]
            else:
                outnode="node"+str(nodeno)
                dotfile.write(outnode+" [ label = \""+colsplit[i]+"\" ];\n")
                dotfile.write(innode+" -> "+outnode+";\n")
                nodeno+=1
        nodes[colsplit[0]].append(pid)
    dotfile.write("}")

    #code to generate html file
    rulelist = open("rulelist.txt","r")
    final = ["init"]
    lhs = []
    lines = 0
    flag = 0
    for line in rulelist:
        split = line.split(" ")
        lhs.append(split[0])
        lines+=1
    i=1
    html = open("output.html","w")
    rulelist = open("rulelist.txt","r")
    for line in rulelist:
        colsplit = line.split(" ")
        k = len(colsplit)-1
        colsplit[k] = colsplit[k][0:len(colsplit[k])-1]
        html.write('''
<table>
   <tr>
      <td>
        <table>
          <tr>%d. </tr>
        </table>
      </td>
      <td>
        <table>
          <tr>start</tr>
        </table>
      </td>
      <td>
        <table>
           <tr> ==> </tr>
        </table>
      </td>''' %(i))
        final.pop(flag)
        for j in xrange(len(colsplit)-1,1,-1):
            if (colsplit[j]!="empty"):
                final.insert(flag,colsplit[j])

        for j in xrange(len(final)-1,-1,-1):
            if i!=lines:
                if lhs[i]==final[j]:
                    flag=j
                    break
        for j in range(0,len(final)):
            if j!=flag:
                html.write('''
        <td>
            <table>
               <tr> %s </tr>
            </table>
        </td>''' %(final[j]))
            else:
                if i!=lines:
                    html.write('''
        <td>
        <table>
           <tr> <font color="red"><u>%s</u></font></tr>
        </table>
        </td>''' %(final[j]))
                else:
                    html.write('''
        <td>
            <table>
               <tr> %s </tr>
            </table>
        </td>''' %(final[j]))
        html.write('''
    </tr>
</table>''')
        i+=1
