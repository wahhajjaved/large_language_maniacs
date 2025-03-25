#!/usr/bin/python
# -*- coding: utf-8; mode: python; tab-width: 3; indent-tabs-mode: nil -*-
#
# Copyright 2015 Raffaello D. Di Napoli
#
# This file is part of Abamake.
#
# Abamake is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Abamake is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
# the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with Abamake. If not, see
# <http://www.gnu.org/licenses/>.
#---------------------------------------------------------------------------------------------------

"""YAML parser."""

import collections
import io
import os
import re


####################################################################################################

def parse_file(sFilePath):
   """Loads and parses a YAML file.

   str sFilePath
      Path to the YAML file.
   object return
      Python object corresponding to the contents of the file.
   """

   return YamlParser().parse_file(sFilePath)

def parse_string(s):
   """Loads and parses a string containing YAML.

   str s
      YAML source.
   object return
      Python object corresponding to the contents of the string.
   """

   return YamlParser().parse_string(s)

####################################################################################################

class SyntaxError(Exception):
   """Indicates a syntactical or semantical error in a YAML source."""

   pass

####################################################################################################

class YamlParser(object):
   """YAML parser. Only accepts a small subset of YAML 1.2 (sequences, maps, strings, comments)."""

   # Matches a comment.
   _smc_reComment = re.compile(r'[\t ]*#.*$')
   # Matchers and convertors for stock scalar types (see YAML 1.2 § 10.3.2. “Tag Resolution”).
   _smc_reDefaultTypes = (
      (re.compile(r'^(?:~|NULL|[Nn]ull)?$'),                                  None),
      (re.compile(r'^(?:TRUE|[Tt]rue)$'),                                     True),
      (re.compile(r'^(?:FALSE|[Ff]alse)$'),                                   False),
      (re.compile(r'^(?P<s>[-+]?\d+)$'),                                      lambda s: int(s, 10)),
      (re.compile(r'^0o(?P<s>[0-7]+)$'),                                      lambda s: int(s,  8)),
      (re.compile(r'^0x(?P<s>[0-9A-Fa-f]+)$'),                                lambda s: int(s, 16)),
      (re.compile(r'^\+?\.(?:INF|[Ii]nf)$'),                                  float('inf')),
      (re.compile(r'^-\.(?:INF|[Ii]nf)$'),                                    float('-inf')),
      (re.compile(r'^\.(?:N[Aa]N|nan)$'),                                     float('nan')),
      (re.compile(r'^(?P<x>[-+]?(?:\.\d+|\d+(?:\.\d*)?)(?:[Ee][-+]?\d+)?)$'), float), # float(x)
   )
   # Matches a document start mark.
   _smc_reDocStart = re.compile(r'^---(?: +|$)')
   # Matches trailing horizontal whitespace.
   _smc_reHorizontalWs = re.compile(r'[\t ]*$')
   # Matches leading horizontal whitespace.
   _smc_reIndent = re.compile(r'^[\t ]*')
   # Matches a mapping key and the whitespace around it.
   _smc_reMappingKey = re.compile(r'^(?P<key>[^:]+?) *:(?: +|$)')
   # Matches a sequence element start.
   _smc_reSequenceDash = re.compile(r'-(?: +|$)')
   _sm_dictStaticLocalTags = {}
   # Matches a tag. This is intentionally an oversimplification of the relatively complex BNF
   # specified by the standard.
   _smc_reTag = re.compile(r'^!(?:(?P<auto>)|(?P<local>\w+)|!(?P<builtin>\w+))(?: +|$)')

   def __init__(self):
      """Constructor."""

      self._m_dictInstanceLocalTags = {}
      self._reset()

   def constructor_from_local_tag(self, sTag):
      """Returns the constructor associated to the specified local tag, if any.

      str sTag
         Local tag to look up.
      callable return
         Constructor associated to sTag, or None if no such local tag was registered.
      """

      return self._m_dictInstanceLocalTags.get(sTag) or self._sm_dictStaticLocalTags.get(sTag)

   def consume_map_implicit(self):
      """Consumes a map.

      dict(str: object) return
         Parsed map.
      """

      iOldMappingMinIndent    = self._m_iMappingMinIndent
      iOldScalarWrapMinIndent = self._m_iScalarWrapMinIndent
      iOldSequenceMinIndent   = self._m_iSequenceMinIndent

      iIndent = self._m_iLineIndent
      self._m_iMappingMinIndent    = iIndent + 1
      self._m_iScalarWrapMinIndent = iIndent + 1
      self._m_iSequenceMinIndent   = iIndent

      dictRet = {}
      while True:
         # Grab the key and strip off the whole matched string.
         sKey = self._m_matchLine.group('key')
         self._m_sLine = self._m_sLine[self._m_matchLine.end():]

         # Parse whatever is left; this may span multiple lines.
         # TODO: reject non-explicit sequences or maps.
         dictRet[sKey] = self.consume_object(False)

         # consume_*() functions always quit after reading one last line, so check if we’re still in
         # the map.
         if self._m_sLine is None or self._m_iLineIndent < iIndent:
            # No next line, or the next line is not part of the map.
            break
         if not self.match_and_store(self._smc_reMappingKey):
            self.raise_parsing_error('mapping key expected')

      self._m_iMappingMinIndent    = iOldMappingMinIndent
      self._m_iScalarWrapMinIndent = iOldScalarWrapMinIndent
      self._m_iSequenceMinIndent   = iOldSequenceMinIndent
      return dictRet

   def consume_object(self, bAllowImplicitMappingOrSequence):
      """Dispatches a call to any of the other consume_*() functions, after inspecting the current
      line.

      bool bAllowImplicitMappingOrSequence
         True if a mapping key or sequence element will be allowed on the initial line, or False
         otherwise.
      object return
         Parsed object.
      """

      if len(self._m_sLine) == 0:
         # The current container left no characters on the current line, so read another one.
         self.next_line()
         bWrapped = True
         bAllowImplicitMappingOrSequence = True
      else:
         bWrapped = False

      # If None, no constructor needs to be called, and the parsed value can be returned as-is.
      fnConstructor = None
      if self.match_and_store(self._smc_reTag):
         # TODO: support more ways of specifying a tag.
         sType = self._m_matchLine.lastgroup
         if sType == 'auto':
            # Nothing to do; this is the same as an omitted tag.
            # TODO: the YAML specification seems to say something different: “All nodes with the “!”
            # non-specific tag are resolved, by the standard convention, to “tag:yaml.org,2002:seq”,
            # “tag:yaml.org,2002:map”, or “tag:yaml.org,2002:str”, according to their kind.”.
            pass
         elif sType == 'local':
            fnConstructor = self.constructor_from_local_tag(self._m_matchLine.group('local'))
            if not fnConstructor:
               self.raise_parsing_error('unrecognized local tag')
         elif sType == 'builtin':
            fnConstructor = {
               'map': dict,
               'seq': list,
               'str': str,
            }.get(self._m_matchLine.group('builtin'))
            if not fnConstructor:
               self.raise_parsing_error('unrecognized built-in tag')

         # Consume the tag.
         iMatchEnd = self._m_matchLine.end()
         if iMatchEnd < len(self._m_sLine):
            # Remove the matched text from the current line.
            self._m_sLine = self._m_sLine[iMatchEnd:]
            bAllowImplicitMappingOrSequence = False
         else:
            # The whole line was consumed; read a new one.
            self.next_line()
            bWrapped = True
            bAllowImplicitMappingOrSequence = True

      if not bWrapped and (self._m_sLine.startswith('"') or self._m_sLine.startswith('\'')):
         oParsed = self.consume_string_explicit()
      elif (
         not bWrapped or self._m_iLineIndent >= self._m_iSequenceMinIndent
      ) and self.match_and_store(self._smc_reSequenceDash):
         if not bAllowImplicitMappingOrSequence:
            self.raise_parsing_error('sequence element not expected in this context')
         # Continue parsing this line as a sequence.
         oParsed = self.consume_sequence_implicit()
      elif (
         not bWrapped or self._m_iLineIndent >= self._m_iMappingMinIndent
      ) and self.match_and_store(self._smc_reMappingKey):
         if not bAllowImplicitMappingOrSequence:
            self.raise_parsing_error('mapping key not expected in this context')
         # Continue parsing this line as a map.
         oParsed = self.consume_map_implicit()
      elif not bWrapped or self._m_iLineIndent >= self._m_iScalarWrapMinIndent:
         oParsed = self.consume_scalar()
      else:
         # The input was an empty line and the indentation of the next line was incompatible with
         # any of the options above.
         oParsed = None

      if fnConstructor and (
         isinstance(fnConstructor, collections.Callable) or isinstance(oParsed, fnConstructor)
      ):
         oParsed = fnConstructor(oParsed)
      return oParsed

   def consume_scalar(self):
      """Consumes a scalar.

      object return
         Parsed scalar, converted to the appropriate type.
      """

      sRet = self._m_sLine
      bMultiline = False
      while self.next_line() and self._m_iLineIndent >= self._m_iScalarWrapMinIndent:
         if ':' in self._m_sLine:
            self.raise_parsing_error('mapping key not expected in scalar context')
         sRet += ' ' + self._m_sLine
         bMultiline = True
      if not bMultiline:
         # Compare the consumed string against one of the matchers for stock scalar types.
         for reMatcher, oConvertor in self._smc_reDefaultTypes:
            match = reMatcher.match(sRet)
            if match:
               if isinstance(oConvertor, collections.Callable):
                  return oConvertor(**match.groupdict())
               else:
                  return oConvertor
      # It’s a string.
      return sRet

   def consume_sequence_implicit(self):
      """Consumes a sequence.

      list(object) return
         Parsed sequence.
      """

      iOldMappingMinIndent    = self._m_iMappingMinIndent
      iOldScalarWrapMinIndent = self._m_iScalarWrapMinIndent
      iOldSequenceMinIndent   = self._m_iSequenceMinIndent

      iIndent = self._m_iLineIndent
      self._m_iScalarWrapMinIndent = iIndent + 1

      listRet = []
      while True:
         # Strip the “- ” prefix and any following whitespace.
         cchMatched = self._m_matchLine.end()
         self._m_sLine = self._m_sLine[cchMatched:]
         # The indentation of the sequence element includes the dash match.
         self._m_iLineIndent       += cchMatched
         self._m_iMappingMinIndent  = iIndent + cchMatched
         self._m_iSequenceMinIndent = iIndent + cchMatched

         # Parse whatever is left; this may span multiple lines.
         listRet.append(self.consume_object(True))

         # consume_*() functions always quit after reading one last line, so check if we’re still in
         # the sequence.
         if self._m_sLine is None or self._m_iLineIndent < iIndent:
            break
            # No next line, or the next line is not part of the sequence.
         elif not self.match_and_store(self._smc_reSequenceDash):
            # The next line is not a sequence element.
            break
         elif self._m_iLineIndent > iIndent:
            self.raise_parsing_error('excessive indentation for sequence element')

      self._m_iMappingMinIndent    = iOldMappingMinIndent
      self._m_iScalarWrapMinIndent = iOldScalarWrapMinIndent
      self._m_iSequenceMinIndent   = iOldSequenceMinIndent
      return listRet

   def consume_string_explicit(self):
      """Consumes an explicit (quoted) string.

      str return
         Parsed string.
      """

      sQuote = self._m_sLine[0]
      ichEndQuote = self._m_sLine.find(sQuote, len(sQuote))
      if ichEndQuote > 0:
         sRet = ''
      else:
         # The string spans multiple lines; go find its end.
         sRet = self._m_sLine[len(sQuote):]
         while self.next_line():
            sRet += ' '
            ichEndQuote = self._m_sLine.find(sQuote)
            if ichEndQuote >= 0:
               break
            sRet += self._m_sLine
         else:
            self.raise_parsing_error('unexpected end of input while looking for string end quote')
      # Verify that nothing follows the closing quote.
      if not self.match_and_store(self._smc_reHorizontalWs, ichEndQuote + len(sQuote)):
         self.raise_parsing_error('unexpected characters after string end quote')
      # Consume what we’re returning.
      sRet += self._m_sLine[0 if sRet else len(sQuote):ichEndQuote]
      self.next_line()
      return sRet

   def find_and_consume_doc_start(self):
      """Consumes and validates the start of the YAML document.

      bool return
         True if the current line was wholly consumed, or False if it still contains characters to be
         parsed.
      """

      self.next_line()
      if self._m_sLine != '%YAML 1.2':
         self.raise_parsing_error('expected %YAML directive')
      if not self.next_line():
         self.raise_parsing_error('missing document start')
      if not self.match_and_store(self._smc_reDocStart):
         self.raise_parsing_error('expected document start')
      iMatchEnd = self._m_matchLine.end()
      if iMatchEnd < len(self._m_sLine):
         # Remove the matched text from the current line.
         self._m_sLine = self._m_sLine[iMatchEnd:]
         return False
      else:
         # The whole line was consumed.
         return True

   class local_tag(object):
      """Decorator to associate in YamlParser a tag with a constructor. The constructor can be a
      class or a function, as long as it’s something that can be called.

      str sTag
         Tag to associate to the constructor.
      """

      def __init__(self, sTag):
         self._m_sTag = sTag

      def __call__(self, fnConstructor):
         # TODO: check for duplicates.
         YamlParser._sm_dictStaticLocalTags[self._m_sTag] = fnConstructor
         return fnConstructor

   def match_and_store(self, re, iStart = 0):
      """Performs a match on the current line with the specified regexp, returning True if a match
      was produced and storing the match object for later access via self._m_matchLine.

      re.RegExp
         Expression to match.
      int iStart
         Character index from which to start the matching; defaults to 0.
      bool return
         True if re was matched, or False otherwise.
      """

      match = re.match(self._m_sLine, iStart)
      self._m_matchLine = match
      return match != None

   def next_line(self):
      """Attempts to read a new line from the YAML document, making it available as self._m_sLine
      after stripping from it any indentation, the length of which is stored in self._m_iLineIndent.

      bool return
         True if a new line was read, of False otherwise.
      """

      while True:
         self._m_iLine += 1
         sLine = next(self._m_iterLines, None)
         if sLine is None:
            # EOF has no indentation.
            self._m_iLineIndent = 0
         else:
            # Strip the trailing line terminator.
            sLine = sLine.rstrip('\n\r')
            # Strip trailing comments.
            # TODO: make this not peek inside quoted strings.
            sLine = self._smc_reComment.sub('', sLine)
            # If nothing’s left, move on to the next line; otherwise return True to consume it.
            if not sLine:
               continue
            # Determine the indentation of the line.
            self._m_iLineIndent = len(self._smc_reIndent.match(sLine).group())
            sLine = sLine[self._m_iLineIndent:]
         self._m_sLine = sLine
         return sLine is not None

   def parse(self, sSourceName, iterLines):
      """Parses the specified source.

      str sSourceName
         Name of the source for use in diagnostic messages.
      iterator(str) iterLines
         Object that yields YAML lines.
      object return
         Top-level parsed object.
      """

      self._m_iterLines = iterLines
      self._m_sSourceName = sSourceName
      try:
         if self.find_and_consume_doc_start():
            # The whole line was consumed; read the next one.
            if not self.next_line():
               # Nothing follows the document start.
               return None
            o = self.consume_object(True)
         else:
            # Finish reading the line with the document start.
            o = self.consume_object(False)
         # Verify that there’s nothing left to parse.
         if self._m_sLine is not None:
            self.raise_parsing_error('invalid token')
      finally:
         self._reset()
      return o

   def parse_file(self, sFilePath):
      """Loads and parses a YAML file.

      str sFilePath
         Path to the YAML file.
      object return
         Python object corresponding to the contents of the file.
      """

      with io.open(sFilePath, 'rt') as fileYaml:
         return self.parse(sFilePath, fileYaml)

   def parse_string(self, s):
      """Parses a string containing YAML.

      str s
         YAML source.
      object return
         Python object corresponding to the contents of the string.
      """

      return self.parse('<string>', iter(s.splitlines(True)))

   def raise_parsing_error(self, sMessage):
      """Raises a yaml.SyntaxError the available context information and the provided message.

      str sMessage
         Error message.
      """

      raise SyntaxError('{}:{}: {}, found: “{}”'.format(
         self._m_sSourceName, self._m_iLine, sMessage, self._m_sLine
      ))

   def register_local_tag(self, sTag, fnConstructor):
      """Registers a new local tag, associating it with the specified constructor.

      str sTag
         Tag to associate to fnConstructor.
      callable fnConstructor
         Constuctor. Must be callable with exactly one argument, which will be a parsed object that
         had its type explicitly set to sTag.
      """

      # TODO: check for duplicates.
      self._m_dictInstanceLocalTags[sTag] = fnConstructor

   def _reset(self):
      """Reinitializes the internal parser status."""

      self._m_iLine = 0
      self._m_matchLine = None
      self._m_sLine = None
      self._m_iLineIndent = 0
      self._m_iterLines = None
      self._m_iMappingMinIndent = 0
      self._m_iScalarWrapMinIndent = 0
      self._m_iSequenceMinIndent = 0
      self._m_sSourceName = '<no input>'
