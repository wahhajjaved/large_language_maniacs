#!/usr/bin/env python

from __future__ import print_function, division, absolute_import

import csv
from enchant import Dict
from string import ascii_letters as letters, whitespace, punctuation, digits
from os import remove
import sys
import utility

from collections import defaultdict

from tempfile import TemporaryFile


def criteria(func, uniq, threshold=9/10):
    return sum(map(func, uniq))/len(uniq) > threshold if uniq else False


def ascii_check(word):
    score = lambda x: x in letters + whitespace + punctuation + digits
    return all(map(score, word))


D = Dict('en_US')
def word_check(word):
    return  D.check(word)


def interface(inpath, outpath):
    tmpfile = utility.make_resource('bow_english.csv.tmp')
    with open(utility.make_resource(inpath), 'r') as src:
        reader = csv.reader((line.replace('\0','') for line in src))
        words_store = defaultdict(int)

        with open(tmpfile, 'w') as dst:
            writer = csv.writer(dst)
            for line in reader:

                line = list(filter(ascii_check, line))

                # date, title, artist, BOW
                uniq = {w.strip() for w, _ in map(lambda s: s.split(':'), line[3:])}

                if criteria(word_check, uniq, 6/10):
                    writer.writerow(line)
                    for word in uniq:
                        words_store[word] += 1
                else:
                    print(line)
                    print()

    minimum_count = 1
    words_store = {w:c for w, c in words_store.items() if c <= minimum_count}

    lookup = [(w,k) for k, w in enumerate(words_store, 1)]
    del words_store

    words  = [w for w, _ in lookup]
    words[0] = '%' + words[0]

    lookup = dict(lookup)

    with open(tmpfile, 'r') as src:
        reader = csv.reader(src)

        with open(utility.make_resource(outpath), 'w') as dst:
            writer = csv.writer(dst)
            writer.writerow(words)
            del words
            for line in reader:
                # date, title, artist, BOW
                date, title, artist = line[:3]
                output = []
                for w, c in map(lambda s: s.split(':'), line[3:]):
                    if lookup.get(w, False):
                        output.append('{}:{}'.format(lookup[w], c))

                if output:
                    writer.writerow([date, title, artist] + output)
    remove(tmpfile)


def cli_interface():
    """
    by convention it is helpful to have a wrapper_cli method that interfaces
    from commandline to function space.
    """
    try:
        ifname, ofpath = sys.argv[1], sys.argv[2]
    except:
        print("usage: {}  <ifname> <ofpath>".format(sys.argv[0]))
        sys.exit(1)
    interface(ifname, ofpath)


if __name__ == '__main__':
    cli_interface()
