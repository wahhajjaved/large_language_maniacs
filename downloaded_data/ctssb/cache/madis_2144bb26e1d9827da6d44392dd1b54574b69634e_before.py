#! /usr/bin/python

import os
import sys

# Workaround for MAC utf-8 encoding
if sys.platform == 'darwin':
    os.environ['LC_ALL']='en_US.UTF-8'
    reload(sys)
    sys.setdefaultencoding("utf-8")

# Workaround for windows - DISABLED
#try: import lib.winunicode
#except ImportError: pass
#else: del lib.winunicode

import re
import apsw
import functions

# Workaround for absence of a real readline module in win32
if sys.platform == 'win32':
    import pyreadline as readline
else:
    import readline

import datetime
import lib.reimport
import locale
import os

from lib.dsv import writer
import csv

pipedinput=not sys.stdin.isatty()

try:
    if pipedinput:
        raise 'go to except'
    import lib.colorama as colorama
    from colorama import Fore, Back, Style
    colnums = True
except:
    colorama=lambda x:x
    def dummyfunction():
        pass
    colorama.deinit=dummyfunction
    colorama.init=dummyfunction
    colnums = False
    pass

class mtermoutput(csv.Dialect):
    def __init__(self):
        self.delimiter='|'
        if not allquote:
            self.quotechar='|'
            self.quoting=csv.QUOTE_MINIMAL
        else:
            self.quotechar='"'
            self.quoting=csv.QUOTE_NONNUMERIC
        self.escapechar="\\"
        self.lineterminator='\n'

def createConnection(db):
    connection = functions.Connection(db)
    functions.register(connection)
    connection.enableloadextension(True)
    return connection

def reloadfunctions():
    global connection, automatic_reload, db

    if not automatic_reload:
        return

    modified=lib.reimport.modified()

    if len(modified)==0 or (modified==['__main__']):
        return

    tmp_settings=functions.settings
    tmp_vars=functions.variables
    connection.close()
    lib.reimport.reimport(functions, 'functionslocal')
    connection = createConnection(db)
    functions.settings=tmp_settings
    functions.variables=tmp_vars

def raw_input_no_history(*args):
    global pipedinput

    if pipedinput:
        try:
            input = raw_input()
        except EOFError:
            connection.close()
            exit(0)
        return input
    
    try:
        input = raw_input(*args)
    except:
        return None
    if input!='':
        try:
            readline.remove_history_item(readline.get_current_history_length()-1)
        except:
            pass
    return input

def update_tablelist():
    global alltables, alltablescompl, connection
    alltables=[]
    alltablescompl=[]
    cursor = connection.cursor()
    cexec=cursor.execute('PRAGMA database_list;')
    for row in cexec:
        cursor1 = connection.cursor()
        if row[1]=='temp':
            cexec1 = cursor1.execute("select name from sqlite_temp_master where type='table';")
        else:
            cexec1 = cursor1.execute("select name from "+row[1]+".sqlite_master where type='table';")

        for row1 in cexec1:
            tname=row1[0].lower().encode('ascii')
            if row[1] in ('main', 'temp'):
                alltables.append(tname)
                alltablescompl.append(tname)
            else:
                dbtname=(row[1]+'.'+tname).lower().encode('ascii')
                alltables.append(dbtname)
                alltablescompl.append(dbtname)
                if tname not in alltablescompl:
                    alltablescompl.append(tname)
        cursor1.close()
    cursor.close()

def get_table_cols(t):
    global connection

    if '.' in t:
        ts=t.split('.')
        dbname=ts[0]
        tname='.'.join(ts[1:])
    else:
        dbname='main'
        tname=t
    cursor = connection.cursor()
    if dbname=='main':
        cexec=cursor.execute('pragma table_info('+str(tname)+')')
        cols=[x[1] for x in cexec]
    else:
        cexec=cursor.execute('select * from '+str(tname))
        cols=[x[0] for x in cursor.getdescription()]
    return cols

def update_cols_for_table(t):
    global alltablescompl, colscompl, lastcols, connection, updated_tables
    if t!='':
        if t[-1]=='.':
            t=t[0:-1]
        if t[-2:]=='..':
            t=t[0:-2]

    if t in alltablescompl and t not in updated_tables:
        try:
            cols=get_table_cols(t)
            updated_tables.add(t)
            colscompl+= ['.'.join([ t, x ]) for x in cols]
            colscompl+= [x for x in cols]
            colscompl+=[t+'..']
        except:
            pass
        try:
            if '.' in t:
                ts=t.split('.')
                dbname=ts[0]
                tname='.'.join(ts[1:])
            else:
                dbname='main'
                tname=t
            cursor = connection.cursor()
            cexec=cursor.execute('select * from '+dbname+".sqlite_master where type='index' and tbl_name='"+str(tname)+"'")
            icompl= [x[1] for x in cexec]
            colscompl+= ['.'.join([ t, x ]) for x in icompl]
            colscompl+= icompl
        except:
            pass
        try:
            colscompl=list(set(colscompl)-set(lastcols))
        except:
            pass

_update_cols_from_tables_last_text=''
def update_cols_from_tables_in_text(t):
    global alltablescompl, _update_cols_from_tables_last_text

    if t==_update_cols_from_tables_last_text:
        return
    
    _update_cols_from_tables_last_text=t

    stablesreg='|'.join( (x.replace('$','\$').replace('.', '\.') for x in sorted(alltablescompl, key=len, reverse=True)) )
    foundtables=re.findall(r'[^a-zA-Z0-9_$]('+stablesreg+r')[,.\s)]', t+u' ')

    for i in foundtables:
        update_cols_for_table(i)


def mcomplete(textin,state):
    
    def normalizename(col):
        if re.match(ur'\.*[\w_$\d.]+\s*$', col,re.UNICODE):
            return col
        else:
            return "`"+col.lower()+"`"  

    text=textin

    #Complete \t to tabs
    if text[-2:]=='\\t':
        if state==0: return text[:-2]+'\t'
        else: return
        
    prefix=''

    localtables=[]
    completions=[]

    linebuffer=readline.get_line_buffer()

    beforecompl= linebuffer[0:readline.get_begidx()]

    # Only complete '.xxx' completions when space chars exist before completion
    if re.match(r'\s*$', beforecompl):
        completions+=dotcompletions
    # If at the start of the line, show all tables
    if beforecompl=='' and text=='':
        localtables=alltables[:]

        # Check if all tables start with the same character
        if localtables!=[]:
            prefcharset=set( (x[0] for x in localtables) )
            if len(prefcharset)==1:
                localtables+=[' ']
        completions=localtables
    # If completion starts at a string boundary, complete from local dir
    elif beforecompl!='' and beforecompl[-1] in ("'", '"'):
        completions=os.listdir(os.getcwdu())
        hits=[x for x in completions if x[:len(text)]==unicode(text)]
        if state<len(hits):
            return hits[state]
        else: return
    # Detect if in simplified 'from' or .schema
    elif re.search(r'(?i)(from\s(?:\s*[\w\d._$]+(?:\s*,\s*))*(?:\s*[\w\d._$]+)?$)|(^\s*\.schema)|(^\s*\.t)|(^\s*\.tables)', beforecompl, re.DOTALL| re.UNICODE):
        localtables=alltablescompl[:]
        completions=localtables
    else:
        localtables=alltablescompl[:]
        completions+=lastcols+colscompl
        completions+=sqlandmtermstatements+allfuncs+localtables

    hits= [x.lower() for x in completions if x.lower()[:len(text)]==unicode(text.lower())]

    update_cols_from_tables_in_text(linebuffer)

    if hits==[] and text.find('.')!=-1 and re.match(r'[\w\d._$]+', text):
        tablename=re.match(r'(.+)\.', text).groups()[0].lower()
        update_cols_for_table(tablename)
        hits= [x.lower() for x in colscompl if x.lower()[:len(text)]==unicode(text.lower())]


    # If completing something that looks like a table, complete only from cols
    if hits==[] and text[-2:]!='..':
        prepost=re.match(r'(.+\.)([^.]*)$', text)
        if prepost:
            prefix, text=prepost.groups()
            hits= [x.lower() for x in lastcols+[y for y in colscompl if y.find('.')==-1] if x.lower()[:len(text)]==unicode(text.lower())]

    try:
        # Complete from colnums
        icol=int(text)
        if len(hits)==0 and str(icol)==text:
            # Show all tables when completing 0
            if icol==0 and newcols!=[]:
                if len(newcols)==1:
                    if state>0: return
                    return prefix+normalizename(newcols[0])
                hits=[]
                maxcolchars=len(str(len(newcols)+1))
                formatstring='{:'+'>'+str(maxcolchars)+'}'
                for num in xrange(len(newcols)):
                    hits.append( formatstring.format(num+1)+'|'+newcols[num] )
                if state<len(hits):
                    return hits[state]
                else: return
            # Complete from last seen when completing for other number
            if icol<=len(lastcols) and lastcols!=[] and state<1:
                return prefix+normalizename(lastcols[icol-1])
    except:
        pass

    if state<len(hits):
        sqlstatem=set(sqlandmtermstatements)
        altset=set(localtables)
        
        if hits[state]=='..':
            if text=='..' and lastcols!=[]:
                return prefix+', '.join([normalizename(x) for x in lastcols])+' '
            else:
                return prefix+hits[state]
        if hits[state] in sqlstatem:
            return prefix+hits[state]
        if hits[state] in colscompl:
            if text[-2:]=='..':
                tname=text[:-2]
                try:
                    cols=get_table_cols(tname)
                    return prefix+', '.join(cols)+' '
                except:
                    pass
        if hits[state] in altset:
            if text in altset:
                update_cols_for_table(hits[state])
            return prefix+hits[state]
        else:
            return prefix+normalizename(hits[state])
    else:
        return

def buildrawprinter(separator):
    return writer(sys.stdout,dialect=mtermoutput(),delimiter=separator)

def schemaprint(cols):
    global pipedinput

    if pipedinput:
        return
    
    if cols!=[]:
        sys.stdout.write(Style.BRIGHT+'--- '+Style.NORMAL+ Fore.RED+'['+Style.BRIGHT+'0'+Style.NORMAL+'|'+Style.RESET_ALL+Style.BRIGHT+'Column names '+'---'+Style.RESET_ALL+'\n')
        colschars=0
        i1=1
        for i in cols:
            colschars+=len(i)+len(str(i1))+3
            i1+=1
        if colschars<=80:
            i1=1
            for i in cols:
                sys.stdout.write(Fore.RED+'['+Style.BRIGHT+str(i1)+Style.NORMAL+'|'+Style.RESET_ALL+i+' ')
                i1+=1
            sys.stdout.write('\n')
        else:
            totalchars=min(colschars/80 +1, 12) * 80
            mincolchars=12
            colschars=0
            i1=1
            for i in cols:
                charspercolname=max((totalchars-colschars)/(len(cols)+1-i1)-5, mincolchars)
                colschars+=min(len(i), charspercolname)+len(str(i1))+3
                if len(i)>charspercolname and len(cols)>1:
                    i=i[0:charspercolname-1]+'..'
                else:
                    i=i+' '
                sys.stdout.write(Fore.RED+'['+Style.BRIGHT+str(i1)+Style.NORMAL+'|'+Style.RESET_ALL+i)
                i1+=1
            sys.stdout.write('\n')

def printrow(row):
    global rawprinter, colnums

    if not colnums:
        rawprinter.writerow(row)
        return

    rowlen=len(row)
    i1=1
    for d in row:
        if rowlen>3:
            if i1==1:
                sys.stdout.write(Fore.RED+Style.BRIGHT+'['+'1'+'|'+Style.RESET_ALL)
            else:
                sys.stdout.write(Fore.RED+'['+str(i1)+Style.BRIGHT+'|'+Style.RESET_ALL)
        else:
            if i1!=1:
                sys.stdout.write(Fore.RED+Style.BRIGHT+'|'+Style.RESET_ALL)
        if type(d) in (int,float):
            d=str(d)
        elif d is None:
            d=Style.BRIGHT+'null'+Style.RESET_ALL
        try:
            sys.stdout.write(d)
        except KeyboardInterrupt:
            raise
        except:
            sys.stdout.write(repr(d))

        i1+=1
    sys.stdout.write('\n')

def printterm(*args, **kwargs):
    global pipedinput

    msg=','.join([unicode(x) for x in args])

    if not pipedinput:
        print(msg)
    elif 'exit' in kwargs:
        sys.exit(msg)



VERSION='1.0'
mtermdetails="mTerm - version "+VERSION
intromessage="""Enter ".help" for instructions
Enter SQL statements terminated with a ";" """

helpmessage=""".functions             Lists all functions
.help                  Show this message (also accepts '.h' )
.help FUNCTION         Show FUNCTION's help page
.quit                  Exit this program
.schema TABLE          Show the CREATE statements
.quote                 Toggle between normal quoting mode and quoting all mode
.beep                  Make a sound when a query finishes executing
.tables                List names of tables (you can also use ".t" or double TAB)
.t TABLE               Browse table
.explain               Explain query plan
.colnums               Toggle showing column numbers
.separator SEP         Change separator to SEP. For tabs use 'tsv' or '\\t' as SEP
                       Separator is used only when NOT using colnums
.vacuum                Vacuum DB using a temp file in current path

Use: FILE or CLIPBOARD function for importing data
     OUTPUT or CLIPOUT function for exporting data"""

if 'HOME' not in os.environ: # Windows systems
        if 'HOMEDRIVE' in os.environ and 'HOMEPATH' in os.environ:
                os.environ['HOME'] = os.path.join(os.environ['HOMEDRIVE'], os.environ['HOMEPATH'])
        else:
                os.environ['HOME'] = "C:\\"

histfile = os.path.join(os.environ["HOME"], ".mterm")

automatic_reload=False
if not pipedinput:
    try:
        readline.read_history_file(histfile)
    except IOError:
        pass
    import atexit
    atexit.register(readline.write_history_file, histfile)
    
    automatic_reload=True
    readline.set_completer(mcomplete)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(' \t\n`!@#$^&*()=+[{]}|;:\'",<>?')

separator = "|"
allquote = False
beeping = False
db = ""
language, output_encoding = locale.getdefaultlocale()

if output_encoding==None:
    output_encoding='UTF8'

if len(sys.argv) >= 2:
    db = sys.argv[1]
    if db=="-q":
        db=':memory:'

connection = createConnection(db)

if db=='' or db==':memory':
    functions.variables.execdb=None
else:
    functions.variables.execdb=str(os.path.abspath(os.path.expandvars(os.path.expanduser(os.path.normcase(db)))))
    
functions.variables.flowname='main'

rawprinter=buildrawprinter(separator)

if len(sys.argv)>2:
        
    statement=' '.join(sys.argv[2:])
    statement = statement.decode(output_encoding)
        
    cursor = connection.cursor()
    try:
        for row in cursor.execute(statement):
            rawprinter.writerow(row)
        cursor.close()
    except KeyboardInterrupt:
        sys.exit()
    finally:
        try:
            cursor.close()
        except:
            pass
    sys.exit()

sqlandmtermstatements=['select ', 'create ', 'where ', 'table ', 'group by ', 'drop ', 'order by ', 'index ', 'from ', 'alter ', 'limit ', 'delete ', '..',
    "attach database '", 'detach database ', 'distinct', 'exists ']
dotcompletions=['.help ', '.colnums', '.schema ', '.functions ', '.tables', '.quote', '.explain ', '.vacuum', '.quit']
allfuncs=functions.functions['vtable'].keys()+functions.functions['row'].keys()+functions.functions['aggregate'].keys()
alltables=[]
alltablescompl=[]
updated_tables=set()
update_tablelist()
lastcols=[]
newcols=[]
colscompl=[]

#Intro Message
if not pipedinput:
    print mtermdetails
    print "running on Python: "+'.'.join([str(x) for x in sys.version_info[0:3]])+', APSW: '+apsw.apswversion()+', SQLite: '+apsw.sqlitelibversion(),
    try:
        sys.stdout.write(", madIS: "+functions.VERSION+'\n')
    except:
        print
    print intromessage

number_of_kb_exceptions=0
while True:
    statement = raw_input_no_history("mterm> ")
    if statement==None:
        number_of_kb_exceptions+=1
        print
        if number_of_kb_exceptions<2:
            continue
        else:
            break

    #Skip comments
    if statement.startswith('--'):
        continue

    number_of_kb_exceptions=0
    statement=statement.decode(output_encoding)
    #scan for commands
    iscommand=re.match("\s*\.(?P<command>\w+)\s*(?P<argument>([\w\.]*))(?P<rest>.*)$", statement)
    validcommand=False

    if iscommand:
        validcommand=True
        command=iscommand.group('command')
        argument=iscommand.group('argument')
        rest=iscommand.group('rest')
        origstatement=statement
        statement=None

        if command=='separator':
            tmpseparator=separator
            if argument=='csv':
                separator = ","
            elif argument in ('tsv','\\t','\t'):
                separator = "\t"
            else:
                separator = argument
            if separator!=tmpseparator:
                rawprinter=buildrawprinter(separator)

        elif command=='explain':
            statement=re.sub("^\s*\.explain\s+", "explain query plan ", origstatement)

        elif command=='quote':
            allquote^=True
            if allquote:
                printterm("Quoting output, uncoloured columns")
                colnums=False
            else:
                printterm("Not quoting output, coloured columns")
                colnums=True
            rawprinter=buildrawprinter(separator)

        elif command=='beep':
            beeping^=True
            if beeping:
                printterm("Beeping enabled")
            else:
                printterm("Beeping disabled")

        elif command=='colnums':
            colnums^=True
            if colnums:
                printterm("Colnums enabled")
            else:
                printterm("Colnums disabled")

        elif 'tables'.startswith(command):
            update_tablelist()
            argument=argument.rstrip('; ')
            if not argument:
                for i in sorted(alltables):
                    printterm(i)
            else:
                statement='select * from '+argument+' limit 2;'

        elif command=='vacuum':
            statement="PRAGMA temp_store_directory = '.';VACUUM;PRAGMA temp_store_directory = '';"
          
        elif command=='schema':
            if not argument:
                statement="select sql from (select * from sqlite_master union all select * from sqlite_temp_master) where sql is not null;"
            else:
                argument=argument.rstrip('; ')
                update_tablelist()
                if argument not in alltables:
                    printterm("No table found")
                else:
                    db='main'
                    if '.' in argument:
                        sa=argument.split('.')
                        db=sa[0]
                        argument=''.join(sa[1:])
                    statement="select sql from (select * from "+db+".sqlite_master union all select * from sqlite_temp_master) where tbl_name like '%s' and sql is not null;" %(argument)

        elif "quit".startswith(command):
            connection.close()
            exit(0)

        elif command=="functions":
            for ftype in functions.functions:
                for f in functions.functions[ftype]:
                    printterm(f+' :'+ftype)

        elif "help".startswith(command):
            if not argument:
                printterm(helpmessage)
            else:
                for i in functions.functions:
                    if argument in functions.functions[i]:
                        printterm("Function "+ argument + ":")
                        printterm(functions.mstr(functions.functions[i][argument].__doc__))

        elif command=="autoreload":
            automatic_reload=automatic_reload ^ True
            printterm("Automatic reload is now: " + str(automatic_reload))

        else:
            validcommand=False
            printterm("""unknown command. Enter ".help" for help""")

        if validcommand:
            histstatement='.'+command+' '+argument+rest
            try:
                readline.add_history(histstatement.encode('utf-8'))
            except:
                pass

    if statement:
        histstatement=statement
        while not apsw.complete(statement):
            more = raw_input_no_history('  ..> ')
            if more==None:
                statement=None
                break
            more=more.decode(output_encoding)
            statement = statement + '\n'.decode(output_encoding) + more
            histstatement=histstatement+' '+more

        reloadfunctions()
        number_of_kb_exceptions=0
        if not statement:
            printterm()
            continue
        try:
            if not validcommand:
                readline.add_history(histstatement.encode('utf-8'))
        except:
            pass

        before=datetime.datetime.now()
        cursor = connection.cursor()
        try:
            cexec=cursor.execute(statement)

            try:
                newcols=[x for x,y in cursor.getdescription()]
                lastcols[0:len(newcols)]=newcols
            except apsw.ExecutionCompleteError, e:
                newcols=[]

            colorama.init()
            rownum=0
            for row in cexec:
                printrow(row)
                rownum+=1
            cursor.close()

            after=datetime.datetime.now()
            tmdiff=after-before

            schemaprint(newcols)
            if not pipedinput:
                if rownum==0:
                    printterm( "Query executed in %s min. %s sec %s msec." %((int(tmdiff.days)*24*60+(int(tmdiff.seconds)/60),(int(tmdiff.seconds)%60),(int(tmdiff.microseconds)/1000))) )
                else:
                    print "Query executed and displayed %s"%(rownum),
                    if rownum==1: print "row",
                    else: print "rows",
                    print "in %s min. %s sec %s msec." %((int(tmdiff.days)*24*60+(int(tmdiff.seconds)/60),(int(tmdiff.seconds)%60),(int(tmdiff.microseconds)/1000)))
            if beeping:
                printterm('\a\a')
                
            colscompl=[]
            updated_tables=set()

            #Autoupdate in case of schema change
            if re.search(r'(?i)(create|attach|drop)', statement):
                update_tablelist()

        except KeyboardInterrupt:
            print
            schemaprint(newcols)
            printterm("KeyboardInterrupt exception: Query execution stopped", exit=True)
            continue
        except (apsw.SQLError, apsw.ConstraintError , functions.MadisError), e:
            emsg=unicode(e)
            printterm(functions.mstr(emsg), exit=True)
            try:
                if u'Error:' in emsg:
                    emsgsplit=emsg.split(u':')
                    print Fore.RED+Style.BRIGHT+ emsgsplit[0] +u':'+Style.RESET_ALL+ u':'.join(emsgsplit[1:])
                else:
                    print e
            except:
                print e
            continue
        except Exception, e:
            printterm("Unknown error:"+functions.mstr(e), exit=True)
            #raise
        finally:
            colorama.deinit()
            try:
                cursor.close()
            except:
                #print "Not proper clean-up"
                pass

