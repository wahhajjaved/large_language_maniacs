#!/USR/BIn/env python2.6
#
# [The "New BSD" license]
# Copyright (c) 2010,2011 The Board of Trustees of The University of Alabama
# All rights reserved.
#
# See LICENSE for details.

from __future__ import with_statement
from __future__ import print_function

__author__  = 'Christopher S. Corley <cscorley@crimson.ua.edu>'
__version__ = '$Id$'

import re
import os
import codecs
from difflib import SequenceMatcher
from datetime import datetime
from pprint import pprint

from PatchLineDivision import PatchLineDivision
from File import File
from antlr3 import ANTLRFileStream, ANTLRInputStream, CommonTokenStream
from JavaLexer import JavaLexer
from Java4Lexer import Java4Lexer
from Java5Lexer import Java5Lexer
from JavaParser import JavaParser
from snippets import _make_dir, _uniq, _file_len
import pysvn


class Diff:
    def __init__(self, project_repo):
        self.cvs_file_path = None
        self.revision = None
        self.project_repo = project_repo

        self.scp = []

        self.old_source = None
        self.new_source = None
        self.old_file = None
        self.new_file = None
        self.digestion = None


        self.old_file_svn = re.compile('--- ([-/._\w ]+.java)\t\(revision (\d+)\)')
        self.new_file_svn = re.compile('\+\+\+ ([-/._\w ]+.java)\t\(revision (\d+)\)')
        self.chunk_startu = re.compile('@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

    def _printToLog(self, source, revision_number, log):
        if len(log) > 0:
            revCurr = self.project_repo.getCurrentRevision()
            _make_dir('/tmp/ohm/')
            with open('/tmp/ohm/errors.log', 'a') as f:
                f.write("\n\n***********************************\n\n")
                for each in log:
                    output = str(datetime.now())
                    output += ' ' + str(revCurr.number)
                    output += ' ' + source
                    output += ' ' + str(revision_number)
                    output += '\n\t' + each[0]
                    output += ' ' + each[1]
                    output += '\n\t' + str(each[2])
                    output += '\n'
                    f.write(output)

    def _getLexerClass(self, revision):
        name = self.project_repo.getName()
        if name.upper() == 'ARGOUML':
            if revision > 13020:
                return Java5Lexer
            elif revision > 8295:
                return Java4Lexer
            else:
                return JavaLexer

        if name.upper() == 'CAROL':
            if revision > 1290:
                return Java5Lexer

        return JavaLexer

    def _getParserResults(self, source, revision_number):
        filePath = self.project_repo.checkout(source, revision_number)

        LexyLexer = self._getLexerClass(revision_number)
        # Run ANTLR on the original source and build a list of the methods
        try:
            lexer = LexyLexer(ANTLRFileStream(filePath, 'utf-8'))
        except UnicodeDecodeError:
            lexer = LexyLexer(ANTLRFileStream(filePath, 'latin-1'))
        except IOError:
            return None
        parser = JavaParser(CommonTokenStream(lexer))
        parser.file_name = source
        parser.file_len = _file_len(filePath)
        return parser.compilationUnit()

    def digest(self, diff_file):
        self.scp = []

        diff_divisions = []
        self.old_source = None
        self.new_source = None
        self.old_source_text = None
        self.new_source_text = None
        if len(diff_file) == 0:
            return None

        self.old_file = None
        self.new_file = None
        self.digestion = None
        
        log = []

        temp = []
        start = 0
        old_revision_number = 0
        new_revision_number = 0
        list_itr = None
        
        isNewFile = False
        isRemovedFile = False

        while start < len(diff_file) and not self.chunk_startu.match(diff_file[start]):
            m = self.old_file_svn.match(diff_file[start])
            if m:
                self.old_source = m.group(1)
                old_revision_number = int(m.group(2))

                nm = self.new_file_svn.match(diff_file[start + 1])
                if nm:
                    self.new_source = nm.group(1)
                    new_revision_number = int(nm.group(2))


                # allows for spaces in the filename
                if '.java' in self.old_source and not self.old_source.endswith('.java'):
                    self.old_source = self.old_source.split('.java')[0] + '.java'
                if '.java' in self.new_source and not self.new_source.endswith('.java'):
                    self.new_source = self.new_source.split('.java')[0] + '.java'

                if not self.old_source.endswith('.java'):
                    return None
                elif not self.new_source.endswith('.java'):
                    return None

                if (old_revision_number == 0):
                    isNewFile = True
                
                start += 1
                break
            start += 1

        # catch diffs that are for only property changes
        if self.old_source is None and self.new_source is None:
            return None
        
        # Divide the diff into separate chunks
        for i in range(start + 1, len(diff_file)):
            tmp = diff_file[i]
            chunk_matcher = self.chunk_startu.match(tmp)
            if chunk_matcher:
                if len(diff_divisions) == 0:
                    if int(chunk_matcher.group(1)) == 0 and int(chunk_matcher.group(2)) == 0:
                        if not isNewFile:
                            print('Uhh.... captain? New file not new?')
                        isNewFile = True
                    elif int(chunk_matcher.group(3)) == 0 and int(chunk_matcher.group(4)) == 0:
                        isRemovedFile = True
                for j in range(start, i - 1):
                    temp.append(diff_file[j])
                if len(temp) > 0:
                    diff_divisions.append(temp)
                temp = []
                start = i

        for j in range(start, len(diff_file)):
            temp.append(diff_file[j])
        diff_divisions.append(temp)

        self.PLD = PatchLineDivision(diff_divisions)
        
        if old_revision_number == 0:
            isNewFile = True
        if new_revision_number == 0:
            isRemovedFile = True

        # Begin prep to run ANTLR on the source files
        
        # Check out from SVN the original file
        if not isNewFile:
            res = self._getParserResults(self.old_source, old_revision_number)
            if res is None:
                # some error has occured.
                return None
            self.old_file = res[0]
            log = res[1]
            with open('/tmp/ohm/svn/' + self.old_source, 'r') as f:
                self.old_source_text = f.readlines()

            self.old_file.text = self.old_source_text    
            #self.old_file.recursive_print()

            self._printToLog(self.old_source, old_revision_number, log)

            self.PLD.digest_old(self.old_file)
        
        if not isRemovedFile:
            res = self._getParserResults(self.new_source, new_revision_number)
            if res is None:
                # some error has occured.
                return None
            self.new_file = res[0]
            log = res[1]

            with open('/tmp/ohm/svn/' + self.new_source, 'r') as f:
                self.new_source_text = f.readlines()

            self.new_file.text = self.new_source_text
            #self.new_file.recursive_print()

            self._printToLog(self.new_source, new_revision_number, log)

            self.PLD.digest_new(self.new_file)
            

        self.recursive_scp(self.old_file, self.new_file)
        if isNewFile:
            self.digestion = self.new_file
        else:
            self.digestion = self.old_file

        if not isRemovedFile:
            self.digestion.removed_count += self.new_file.removed_count
            self.digestion.added_count += self.new_file.added_count
            self.recursive_wtf(self.digestion, self.new_file)

    def recursive_wtf(self, old, new):
        if old is None or new is None:
            return

        if old.has_sub_blocks and new.has_sub_blocks:
            old_set = set(old.sub_blocks)
            new_set = set(new.sub_blocks)
        else:
            return 

        common_set = old_set & new_set
        added_set = new_set - common_set
        
        for block in common_set:
            o = old.sub_blocks[old.sub_blocks.index(block)]
            n = new.sub_blocks[new.sub_blocks.index(block)]
            o.removed_count += n.removed_count
            o.added_count += n.added_count

            # prune the unchanged blocks
            if o.removed_count == 0 and o.added_count == 0:
                old.sub_blocks.remove(o)
            else:
                self.recursive_wtf(o, n)

        old.sub_blocks.extend(added_set)


    def recursive_scp(self, old, new):
        """ This method is intended to recursively process all sub_blocks in
        the given block"""
        if old is None or new is None:
            return

        if old.has_sub_blocks and new.has_sub_blocks:
            old_set = set(old.sub_blocks)
            new_set = set(new.sub_blocks)
        else:
            return 

        common_set = old_set & new_set
        added_set = new_set - common_set
        removed_set = old_set - common_set
        
        for block in common_set:
            o = old.sub_blocks[old.sub_blocks.index(block)]
            n = new.sub_blocks[new.sub_blocks.index(block)]
            self.recursive_scp(o, n)

        # get scp
        scp = self.digestSCP(removed_set, added_set)
        old.scp = scp

        for pair in scp:
            if pair[0] in old and pair[1] in new:
                o = old.sub_blocks[old.sub_blocks.index(pair[0])]
                n = new.sub_blocks[new.sub_blocks.index(pair[1])]
                self.recursive_scp(o, n)

        self.scp += scp

    def digestSCP(self, removed_set, added_set):
        # renames: yes, merges: no, splits: not handled, clones: yes
        possible_pairs = []
        max_pair = None
        tiebreak_pairs = []
        for r_block in removed_set:
            if max_pair is not None:
                #added_set.remove(max_pair[1]) # do not attempt to re-pair
                max_pair = None

            tiebreak_pairs = []
            for a_block in added_set:
                # for pairing of blocks with a small number of sub_blocks (1-3), this
                # will be fairly inaccurate
                if r_block.has_sub_blocks and a_block.has_sub_blocks:
                    r_block_seq = r_block.sub_blocks
                    a_block_seq = a_block.sub_blocks
                else:
                    r_block_seq = r_block.text
                    a_block_seq = a_block.text

                s = SequenceMatcher(None, r_block_seq, a_block_seq)
                relation_value = s.ratio()
                if relation_value == 0.0:
                    continue

                if max_pair is None:
                    max_pair = (r_block, a_block, relation_value)
                    tiebreak_pairs = []
                elif relation_value > max_pair[2]:
                    max_pair = (r_block, a_block, relation_value)
                    tiebreak_pairs = []
                elif relation_value == max_pair[2]:
                    # tie breaker needed, compare the names
                    tb = self._tiebreaker(r_block.name, a_block.name,
                            max_pair[1].name)
                    if tb == 0:
                        tb = self._tiebreaker(str(r_block), str(a_block),
                            str(max_pair[1]))

                    if tb == 0:
                        tiebreak_pairs.append((r_block, a_block,
                            relation_value))
                        tiebreak_pairs.append(max_pair)
                    
                    if tb == 1:
                        max_pair = (r_block, a_block, relation_value)

            # since r_block->a_block pair has been found, should we remove
            # a_block from the list of possiblities?
            if max_pair is not None:
                if not max_pair in tiebreak_pairs:
                    possible_pairs.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                print('------------')
                for each in tiebreak_pairs:
                    print('tiebreaker needed: %s, %s, %s' % each)
                print('------------')

        return self._prunePairs(_uniq(possible_pairs))

    def _prunePairs(self, possible_pairs):
        # find pairs which have duplicates, select only best
        more_possible = []
        tiebreak_pairs = []
        
        max_pair = None
        for each in possible_pairs:
            tiebreak_pairs = []
            max_pair = each
            for pair in possible_pairs:
                if max_pair != pair and max_pair[0] == pair[0]:
                    if max_pair[2] < pair[2]:
                        max_pair = pair
                        tiebreak_pairs = []
                    elif max_pair[2] == pair[2]:
                        tiebreak_pairs.append(pair)
                        tiebreak_pairs.append(max_pair)

            if not max_pair in tiebreak_pairs:
                more_possible.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                pass

        
        tiebreak_pairs = []
        most_possible = []
        for each in more_possible:
            tiebreak_pairs = []
            max_pair = each
            for pair in more_possible:
                if max_pair != pair and max_pair[1] == pair[1]:
                    if max_pair[2] < pair[2]:
                        max_pair = pair
                        tiebreak_pairs = []
                    elif max_pair[2] == pair[2]:
                        tiebreak_pairs.append(pair)
                        tiebreak_pairs.append(max_pair)

            if not max_pair in tiebreak_pairs:
                most_possible.append(max_pair)
            if len(tiebreak_pairs) > 0:
                #possible_pairs.extend(tiebreak_pairs)
                pass

                        
        return _uniq(most_possible)

    def _tiebreaker(self, old, new_a, new_b):
        s = SequenceMatcher(None, new_a, old)
        a_ratio = s.ratio()
        s.set_seq1(new_b)
        b_ratio = s.ratio()
        if a_ratio > b_ratio:
            return 1
        elif a_ratio < b_ratio:
            return 2

        return 0
