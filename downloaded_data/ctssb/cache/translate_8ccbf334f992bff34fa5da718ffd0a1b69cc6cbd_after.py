#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright 2003-2007 Zuza Software Foundation
# 
# This file is part of translate.
#
# translate is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# translate is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with translate; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""takes a translation file and produces word counts and other statistics"""

from translate.storage import factory
from translate.lang.common import Common
from translate.misc.multistring import multistring
import re
import sys
import os

if not hasattr(__builtins__, "sum"):
  def sum(parts):
    return reduce(int.__add__, parts, 0)

def untranslatedwords(pair):
  original, translation = pair
  if translation.words != 0: return 0
  return original.words

kdepluralre = re.compile("^_n: ")
brtagre = re.compile("<br\s*?/?>")
xmltagre = re.compile("<[^>]+>")
numberre = re.compile("\\D\\.\\D")

def wordcount(postr):
  # TODO: po class should understand KDE style plurals
  postr = kdepluralre.sub("", postr)
  postr = brtagre.sub("\n", postr)
  postr = xmltagre.sub("", postr)
  postr = numberre.sub(" ", postr)
  #TODO: This should still use the correct language to count in the target 
  #language
  return len(Common.words(postr))

def wordsinpoel(poel):
  """counts the words in the source, target, taking plurals into account"""
  (sourcewords, targetwords) = (0, 0)
  if isinstance(poel.source, multistring):
    sourcestrings = poel.source.strings
  else:
    sourcestrings = [poel.source or ""]
  if isinstance(poel.target, multistring):
    targetstrings = poel.target.strings
  else:
    targetstrings = [poel.target or ""]
  for s in sourcestrings:
    sourcewords += wordcount(s)
  for s in targetstrings:
    targetwords += wordcount(s)
  return sourcewords, targetwords

def calcstats(units):
  # ignore totally blank or header units
  units = filter(lambda poel: not poel.isheader(), units)
  translated = translatedmessages(units)
  fuzzy = fuzzymessages(units)
  review = filter(lambda poel: poel.isreview(), units)
  untranslated = untranslatedmessages(units)
  wordcounts = dict(map(lambda poel: (poel, wordsinpoel(poel)), units))
  sourcewords = lambda elementlist: sum(map(lambda poel: wordcounts[poel][0], elementlist))
  targetwords = lambda elementlist: sum(map(lambda poel: wordcounts[poel][1], elementlist))
  stats = {}

  #units
  stats["translated"] = len(translated)
  stats["fuzzy"] = len(fuzzy)
  stats["untranslated"] = len(untranslated)
  stats["review"] = len(review)
  stats["total"] = stats["translated"] + stats["fuzzy"] + stats["untranslated"]

  #words
  stats["translatedsourcewords"] = sourcewords(translated)
  stats["translatedtargetwords"] = targetwords(translated)
  stats["fuzzysourcewords"] = sourcewords(fuzzy)
  stats["untranslatedsourcewords"] = sourcewords(untranslated)
  stats["reviewsourcewords"] = sourcewords(review)
  stats["totalsourcewords"] = stats["translatedsourcewords"] + stats["fuzzysourcewords"] + stats["untranslatedsourcewords"]
  return stats

def summarize(title, stats, CSVstyle=False):
  if CSVstyle:
    print "%s, " % title,
    print "%d, %d, %d," % (stats["translated"], stats["translatedsourcewords"], stats["translatedtargetwords"]),
    print "%d, %d," % (stats["fuzzy"], stats["fuzzysourcewords"]),
    print "%d, %d," % (stats["untranslated"], stats["untranslatedsourcewords"]),
    print "%d, %d" % (stats["total"], stats["totalsourcewords"]),
    if stats["review"] > 0:
      print ", %d, %d" % (stats["review"], stats["reviewsourdcewords"])
    print
  else:
    print title
    print "type              strings      words (source)    words (translation)"
    print "translated:   %5d (%3d%%) %10d (%3d%%) %15d" % (stats["translated"], stats["translated"]*100/stats["total"], stats["translatedsourcewords"], stats["translatedsourcewords"]*100/stats["totalsourcewords"], stats["translatedtargetwords"])
    print "fuzzy:        %5d (%3d%%) %10d (%3d%%)             n/a" % (stats["fuzzy"], stats["fuzzy"]*100/stats["total"], stats["fuzzysourcewords"], stats["fuzzysourcewords"]*100/stats["totalsourcewords"] )
    print "untranslated: %5d (%3d%%) %10d (%3d%%)             n/a" % (stats["untranslated"], stats["untranslated"]*100/stats["total"], stats["untranslatedsourcewords"], stats["untranslatedsourcewords"]*100/stats["totalsourcewords"])
    print "Total:        %5d %17d %22d" % (stats["total"], stats["totalsourcewords"], stats["translatedtargetwords"])
    if stats["review"] > 0:
      print "review:       %5d %17d                    n/a" % (stats["review"], stats["reviewsourcewords"])
    print

def fuzzymessages(units):
    return filter(lambda unit: unit.isfuzzy() and unit.target, units)

def translatedmessages(units):
    return filter(lambda unit: unit.istranslated(), units)

def untranslatedmessages(units):
    return filter(lambda unit: not (unit.istranslated() or unit.isfuzzy()) and unit.source, units)

class summarizer:
  def __init__(self, filenames, CSVstyle):
    self.totals = {}
    self.filecount = 0
    self.CSVstyle = CSVstyle
    if self.CSVstyle:
      print "Filename, Translated Messages, Translated Source Words, Translated \
Target Words, Fuzzy Messages, Fuzzy Source Words, Untranslated Messages, \
Untranslated Source Words, Total Message, Total Source Words, \
Review Messages, Review Source Words"
    for filename in filenames:
      if not os.path.exists(filename):
        print >>sys.stderr, "cannot process %s: does not exist" % filename
        continue
      elif os.path.isdir(filename):
        self.handledir(filename)
      else:
        self.handlefile(filename)
    if self.filecount > 1 and not self.CSVstyle:
      summarize("TOTAL:", self.totals)
      print "File count:   %5d" % (self.filecount)
      print

  def updatetotals(self, stats):
    """Update self.totals with the statistics in stats."""
    for key in stats.keys():
        if not self.totals.has_key(key):
            self.totals[key] = 0
        self.totals[key] += stats[key]

  def handlefile(self, filename):
    try:
        pof = factory.getobject(filename)
    except ValueError, e:
        print str(e)
        return
    stats = calcstats(pof.units)
    self.updatetotals(stats)
    summarize(filename, stats, self.CSVstyle)
    self.filecount += 1

  def handlefiles(self, dirname, filenames):
    for filename in filenames:
      pathname = os.path.join(dirname, filename)
      if os.path.isdir(pathname):
        self.handledir(pathname)
      else:
        self.handlefile(pathname)

  def handledir(self, dirname):
    path, name = os.path.split(dirname)
    if name in ["CSV", ".svn", "_darcs"]:
      return
    entries = os.listdir(dirname)
    self.handlefiles(dirname, entries)

def main():
  # TODO: make this handle command line options using optparse...
  CSVstyle = False
  if "--csv" in sys.argv:
    sys.argv.remove("--csv")
    CSVstyle = True
  try:
    import psyco
    psyco.full()
  except Exception:
    pass
  summarizer(sys.argv[1:], CSVstyle)

if __name__ == '__main__':
    main()
