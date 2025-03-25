
import os
import sys

base = os.path.dirname(sys.argv[0])
sys.path.append(os.path.join(base, "common"))

import stream
import oprand
import read
import scope
import temp
import define
import string
import formula
import pathname

defineds = scope.scope()
oprands = scope.scope()
pathname = pathname.pathname()

# read method

def readtooprands (union, streamin):
    before = ""
    while streamin.look():
        content, oprand = read.readoprand(streamin)
        if oprand in union:
            before += content
            return before, oprand
        if oprand in oprands:
            op = oprands.get(oprand)()
            op.parse(streamin)
            before += content
            before += op.build()
            continue
        raise read.readerror('you tried undefined oprand of "%s" in readtooprands().' % oprand)

# basic oprands

class oprandIf (oprand.oprand):

    # @if ... @then ... @else ... @endif
    # @if ... newline ... @else ... @endif 
    # @if ... newline ... @endif

    def parse (self, streamin):        
        
        def parsecase ():
            
            content, oprand = readtooprands(["then", "else", "endif"], streamin)
            
            if oprand == "then":
                self.add("case", content)
                return parsethen()

            streamcontent = stream.stream(content)
            line = readline(streamcontent)
            rest = readrest(streamcontent)
                
            if oprand == "else":
                self.add("case", line)
                self.add("then", rest)
                return parseelse()
            
            if oprand == "endif":
                self.add("case", line)
                self.add("then", rest)
                return

        def parsethen ():

            content, oprand = readtooprands(["else", "endif"], streamin)

            if oprand == "else":
                self.add("then", content)
                return parseelse()
            
            if oprand == "endif":
                self.add("then", content)
                return

        def parseelse ():

            content, oprand = readtooprands(["endif"], streamin)

            if oprand == "endif":
                self.add("else", content)
                return

        parsecase()
        
        self.add("case", self.get("case").strip(string.whitespace))
        self.add("then", self.get("then").strip(string.whitespace))
        self.add("else", self.get("else").strip(string.whitespace))

    def run (self, tm):
        exp = expand(stream.stream(self.get("case")))
        if fomula.evaluate(exp) == 0:
            tm.add(load(stream.stream(self.get("else"))))
        else: tm.add(load(stream.stream(self.get("then"))))
    
    def build (self):
        return "@if %s @then %s @else %s @endif" % (
            self.get("case"),
            self.get("then"),
            self.get("else"))


class oprandIfdef (oprand.oprand):

    # @ifdef ... @then ... @else ... @endif
    # @ifdef ... newline ... @else ... @endif 
    # @ifdef ... newline ... @endif

    def parse (self, streamin):

        def parsecase ():
            
            content, oprand = readtooprands(["then", "else", "endif"], streamin)
            
            if oprand == "then":
                self.add("case", content)
                return parsethen()

            streamcontent = stream.stream(content)
            line = readline(streamcontent)
            rest = readrest(streamcontent)
                
            if oprand == "else":
                self.add("case", line)
                self.add("then", rest)
                return parseelse()
            
            if oprand == "endif":
                self.add("case", line)
                self.add("then", rest)
                return

        def parsethen ():

            content, oprand = readtooprands(["else", "endif"], streamin)

            if oprand == "else":
                self.add("then", content)
                return parseelse()
            
            if oprand == "endif":
                self.add("then", content)
                return

        def parseelse ():

            content, oprand = readtooprands(["endif"], streamin)

            if oprand == "endif":
                self.add("else", content)
                return

        parsecase()
        
        self.add("case", self.get("case").strip(string.whitespace))
        self.add("then", self.get("then").strip(string.whitespace))
        self.add("else", self.get("else").strip(string.whitespace))

    def run (self, tm):
        if not self.get("name") in defineds:
            tm.add(load(stream.stream(self.get("else"))))
        else: tm.add(load(stream.stream(self.get("then"))))

    def build (self):
        return "@ifdef %s @then %s @else %s @endif" % (
            self.get("case"),
            self.get("then"),
            self.get("else"))


class oprandIfndef (oprand.oprand):

    # @ifndef ... @then ... @else ... @endif
    # @ifndef ... newline ... @else ... @endif 
    # @ifndef ... newline ... @endif

    def parse (self, streamin):
        
        def parsecase ():
            
            content, oprand = readtooprands(["then", "else", "endif"], streamin)
            
            if oprand == "then":
                self.add("case", content)
                return parsethen()

            streamcontent = stream.stream(content)
            line = readline(streamcontent)
            rest = readrest(streamcontent)
                
            if oprand == "else":
                self.add("case", line)
                self.add("then", rest)
                return parseelse()
            
            if oprand == "endif":
                self.add("case", line)
                self.add("then", rest)
                return

        def parsethen ():

            content, oprand = readtooprands(["else", "endif"], streamin)

            if oprand == "else":
                self.add("then", content)
                return parseelse()
            
            if oprand == "endif":
                self.add("then", content)
                return

        def parseelse ():

            content, oprand = readtooprands(["endif"], streamin)

            if oprand == "endif":
                self.add("else", content)
                return

        parsecase()
        
        self.add("case", self.get("case").strip(string.whitespace))
        self.add("then", self.get("then").strip(string.whitespace))
        self.add("else", self.get("else").strip(string.whitespace))

        def parsethen ():
            content, oprand = readtooprands(["else", "endif"], streamin)
            if oprand == "else":
                pass
            if oprand == "endif":
                pass

        def parseelse ():
            content, oprand = readtooprands(["else"], streamin)
            if oprand == "endif":
                pass

        parsecase()

    def run (self, tm):
        if self.get("name") in defineds:
            tm.add(load(stream.stream(self.get("else"))))
        else: tm.add(load(stream.stream(self.get("then"))))

    def build (self):
        return "@ifndef %s @then %s @else %s @endif" % (
            self.get("case"),
            self.get("then"),
            self.get("else"))


class defineImmediate (define.define):

    # name <- load self.source

    def init (self, source):
        self.source = source

    def run (self, streamin):
        return load(stream.stream(self.source))

    __init__ = init


class defineFunction (define.define):

    # name(...) <- load self.source with (...)

    def init (self, argument, source):
        self.source = source
        self.parse(argument)

    def parse (self, argument):
        self.argument = read.readlist(stream.stream(argument))

    def run (self, streamin):
        defineds.push()
        argument = read.readlist(streamin)
        if len(argument) < len(self.argument):
            raise Exception("macro missing arguments of (... %s)." % ",".join(self.argument[len(argument):]))
        if len(argument) > len(self.argument):
            raise Exception("macro too many arguments of (... %s)" % ",".join(argument[len(self.argument):]))
        for bind in zip(self.argument, argument):
            name, value = bind
            value = expand(stream.stream(value))
            if name != value:
                defineds.add(name, defineImmediate(value))
        content = load(stream.stream(self.source))
        defineds.pop()
        return content

    __init__ = init
    

class oprandDefine (oprand.oprand):

    # @define ... @begin ... @end
    # @define ... newline ... @end

    def parse (self, streamin):

        def parsename ():
            content, oprand = readtooprands(["begin", "end"], streamin)
            if oprand == "begin":
                self.add("name", content)
                parsebegin()
                return
            if oprand == "end":
                streamcontent = stream.stream(content)
                name = read.readline(streamcontent)
                begin = read.readrest(streamcontent)
                self.add("name", name)
                self.add("begin", begin)
                return

        def parsebegin ():
            content, oprand = readtooprands(["end"], streamin)
            if oprand == "end":
                self.add("begin", content)
                return

        parsename()

        self.add("name", self.get("name").strip(string.whitespace))
        self.add("begin", self.get("begin").strip(string.whitespace))

    def run (self, tm):
        
        nameall = self.get("name")
        nameall = nameall.strip(string.whitespace)
        index = nameall.find("(")
        
        name = nameall
        argument = None
        
        if index >= 0:
            name = nameall[:index]
            argument = nameall[index:]
            
        if index == -1:
            defineimmediate = defineImmediate(self.get("begin"))
            defineds.add(name, defineimmediate)

        else:
            definefunction = defineFunction(argument, self.get("begin"))
            defineds.add(name, definefunction)

    def build (self):
        return "@define %s @begin %s @end" % (
            self.get("name"),
            self.get("begin"))


class oprandUndefine (oprand.oprand):

    # @undefine ... @end

    def parse (self, streamin):

        def parsename ():
            content, oprand = readtooprands(["end"], streamin)
            if oprand == "end":
                pass

        parsename()

    def run (self, tm):
        oprands.remove(self.get("name"))

    def build (self):
        return "@undefine %s @end" % (self.get("name"))


class oprandImport (oprand.oprand):

    # @import locate

    imported = set()

    def parse (self, streamin):
        read.readspace(streamin)
        self.add("name", read.readstring(streamin))

    def run (self, tm):
        filename = self.get("name")[1:-1]
        findname = pathname.find(filename)
        if not filename in self.imported:
            pathname.push()
            pathname.add(os.path.dirname(filename))
            print pathname.pathnames
            with open(findname, "r") as fin:
                tm.add(load(stream.filestream(fin)))
            pathname.pop()

    def build (self):
        return "@import %s" % self.get("name")
    

class oprandLoad (oprand.oprand):

    # @load locate

    def parse (self, streamin):
        read.readspace(streamin)
        self.add("name", read.readstring(streamin))

    def run (self, tm):
        filename = self.get("name")[1:-1]
        dirname = os.path.dirname(filename)
        pathname.push()
        pathname.add(dirname)
        with open(filename, "r") as fin:
            tm.add(load(stream.filestream(fin)))
        pathname.pop()

    def build (self):
        return "@load %s" % self.get("name")

    
class oprandSource (oprand.oprand):

    # @load-string locate
 
    def parse (self, streamin):
        read.readspace(streamin)
        self.add("name", read.readstring(streamin))
        
    def run (self, tm):
        filename = self.get("name")[1:-1]
        dirname = os.path.dirname(filename)
        pathname.push()
        pathname.add(dirname)
        with open(filename, "r") as fin:
            tm.add('"%s"' % "".join(map((lambda c: '\\"' if c == '"' else c), fin.read())))
        pathname.pop()

    def build (self):
        return "@source %s" % self.get("name")
                

class oprandEnd (oprand.oprand):

    def parse (self, streamin):
        self.error()

    def error (self):
        raise Exception("@end has no meaning with alone.")

class oprandThen (oprand.oprand):

    def parse (self, streamin):
        self.error()

    def error (self):
        raise Exception("@then has no meaning with alone.")

class oprandElse (oprand.oprand):

    def parse (self, streamin):
        self.error()

    def error (self):
        raise Exception("@else has no meaning with alone.")

class oprandEndif (oprand.oprand):

    def parse (self, streamin):
        self.error()

    def error (self):
        raise Exception("@endif has no meaning with alone.")
    
    
oprands.add("if", oprandIf)
oprands.add("ifdef", oprandIfdef)
oprands.add("ifndef", oprandIfndef)
oprands.add("define", oprandDefine)
oprands.add("end", oprandEnd)
oprands.add("then", oprandThen)
oprands.add("else", oprandElse)
oprands.add("endif", oprandEndif)
oprands.add("import", oprandImport)
oprands.add("load", oprandLoad)
oprands.add("source", oprandSource)

def parseoprand (name, streamin):
    if name in oprands:
        op = oprands.get(name)()
        op.parse(streamin)
        return op
    raise Exception("undefined oprand %s in parseoprand()." % name)

def runoprand (name, tm, streamin):
    if name in oprands:
        op = parseoprand(name, streamin)
        return op.run(tm)
    raise Exception("undefined oprand %s in runoprand()." % name)

def buildoprand (name, streamin):
    if name in oprands:
        op = parseoprand(name, streamin)
        return op.build()
    raise Exception("undefined oprand %s in buildoprand()." % name)

def load (streamin):
    tm = temp.temp()
    while streamin.look():
        content, opcode = read.readoprand(streamin)
        tm.addtemp(content)
        opcode and runoprand(opcode, tm, streamin)
    source = tm.gettemp()
    source = expand(stream.stream(source))
    tm.add(source)
    return tm.get().strip(string.whitespace)

def expand (streamin):
    content = ""
    while streamin.look():
        word = read.readword(streamin)
        if word in defineds:
            content += defineds.get(word).run(streamin)
        else: content += word
        unword = read.readunword(streamin)
        content += unword
    return content

def expand2 (streamin):
    
    def expandone (streamin):
        word = read.readword(streamin)
        if word in defineds:
            word = defineds.get(word).run(streamin)
        space = read.readspace(streamin)
        connector = read.readconnector(streamin)
        if connector == "":
            return word + space + read.readunword(streamin)
        if connector == "#":
            spacen = read.readspace(streamin)
            wordn = read.readword(streamin)
            if wordn in defineds:
                wordn = defineds.get(wordn).run(streamin)
            return word + space + '"%s"' % wordn
        if connector == "##":
            read.readspace(streamin)
            return word + read.readunword(streamin)

    content = ""
    while streamin.look():
        content += expandone(streamin)
    return content

expand = expand2

# import sys

for filename in sys.argv[1:]:
    filenameout = filename.split(".")
    filenameout.insert(-1, "com")
    filenameout = ".".join(filenameout)
    pathname.push()
    pathname.add(os.path.dirname(filename))
    with open(filename, "r") as fin:
        with open(filenameout, "w") as fout:
            fout.write(load(stream.filestream(fin)))
        pathname.pop()

# import argparse

# ps = argparse.ArgumentParser()

# ps.add_argument("file", nargs = "?", help = "input source file.")

# ps.add_argument("-v", "--version", action = "version", version = "cbi version 0.6a")

# ps.add_argument("--stdin", metavar = "", help = "input from standard input.")

# ps.add_argument("--stdout", metavar = "", help = "output with standard output.")

# ps.add_argument("-o", nargs = 1, metavar = "", type = str, help = "output file name.")

# ps.add_argument("--depending", metavar = "", help = "list depending files")

# argument = ps.parse_args()

# launch application
