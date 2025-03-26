#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import re
from subprocess import Popen, PIPE
import uuid
import vim

class LineInfo(object):
    def __init__(self, n, linebegin = -1, lineend = -1):
        self.linebegin = linebegin
        self.lineend = lineend
        self.n = n

    def __str__(self):
        return "n={} begin={} end={}".format(self.n, self.linebegin, self.lineend)


class Parser(object):
    regex = re.compile(r"\s*#\s*(if|else|endif).*")
    cmdline = ["g++", "-w", "-x", "c++", "-E", "-"]

    def __init__(self):
        self._blocks = []
        self._visblocks = []
        self.lines = []
        self._uuid = None

    def getBlocks(self):
        return self._blocks

    def getVisibleBlocks(self):
        return self._visblocks

    def getInvisibleBlocks(self):
        tmp = list(self._blocks)
        for i in self._visblocks[::-1]:
            del tmp[i.n]
        return tmp

    def parsestring(self, text):
        self.lines = text.splitlines(True)
        self._parse()

    def parsefile(self, fname):
        with open(fname, "r") as f:
            self.lines = f.readlines()
        self._parse()

    def parselines(self, lines):
        self.lines = [i for i in lines]
        self._parse()

    def compile(self):
        p = Popen(self.cmdline, stdout=PIPE, stdin=PIPE, stderr=PIPE)
        code = self._injectTags()
        printdebug("Compiler input:\n" + code)
        out = p.communicate(code)[0]
        printdebug("Compiler output:\n" + out)
        self._parseTags(out)

    def _injectTags(self):
        self._uuid = uuid.uuid1()
        for i in self._blocks[::-1]:
            if i.linebegin != i.lineend:
                self.lines.insert(i.linebegin, "{} {}".format(self._uuid, str(i)))
        return "\n".join(self.lines)

    def _parseTags(self, text):
        r = re.compile(str(self._uuid) + r" n=(\d+) begin=(\d+) end=(\d+)")
        self._visblocks = []
        for i in text.splitlines():
            m = r.match(i.strip())
            if m:
                self._visblocks.append(LineInfo(
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3))))

    def _parse(self):
        self._tags = []
        self._parseblock(enumerate(self.lines, 1))

    def _parseblock(self, enum):
        for n,l in enum:
            m = Parser.regex.match(l)
            if m:
                if m.group(1) == "if" or m.group(1) == "else":
                    self._addtag(n, enum)
                if m.group(1) == "else" or m.group(1) == "endif":
                    return n

    def _addtag(self, n, enum):
        # Keep the blocks in ascending order
        self._blocks.append(LineInfo(len(self._blocks), n))
        tmp = self._blocks[-1]
        tmp.lineend = self._parseblock(enum)

def printdebug(text):
    if debug:
        with open("grayout-log.txt", "a") as f:
            f.write(text + "\n")
        print(text)

# TODO: find a better solution for sign ids
bufnr = int(vim.eval("bufnr('%')"))
basesignid = (1 + bufnr) * 25397
debug = int(vim.eval("g:grayout_debug"))
numgrayouts = int(vim.eval("b:num_grayout_lines"))

printdebug("bufnr: " + str(bufnr))
printdebug("basesignid: " + str(basesignid))
printdebug("numgrayouts: " + str(numgrayouts))

printdebug("Clearing existing grayouts...")
for i in range(numgrayouts):
    printdebug("Removing sign " + str(basesignid + i))
    vim.command("sign unplace {} buffer={}".format(basesignid + i, bufnr))

parser = Parser()
parser.parselines(vim.current.buffer)
parser.compile()

blocks = parser.getInvisibleBlocks()
printdebug("Inactive blocks:")
for i in blocks:
    printdebug(str(i))
printdebug("Active blocks:")
for i in parser.getVisibleBlocks():
    printdebug(str(i))


printdebug("Applying new grayouts...")
numgrayouts = 0
for b in blocks:
    for i in range(b.linebegin + 1, b.lineend):
        signid = basesignid + numgrayouts
        printdebug("Creating grayout {} in line {}".format(signid, i))
        vim.command("sign place {} line={} name=PreprocessorGrayout file={}".format(
            signid, i, vim.current.buffer.name))
        numgrayouts += 1

printdebug("new numgrayouts: " + str(numgrayouts))
vim.command("let b:num_grayout_lines = " + str(numgrayouts))
