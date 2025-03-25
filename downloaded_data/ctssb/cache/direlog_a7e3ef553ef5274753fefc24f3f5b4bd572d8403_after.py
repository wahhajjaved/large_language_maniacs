#!/usr/bin/env python
# encoding: utf-8

import sys
import re
import argparse
import fileinput
import copy
import itertools

from argparse import RawDescriptionHelpFormatter

from patterns import main_patterns

def show_snippets(input_stream, patterns=main_patterns):
    """show snippets for patterns

    :input_stream: input stream
    :patterns: patterns that need to look
    :returns: None

    """

    LINES_ABOVE = 3
    LINES_BELOW = 3
    SNIPPETS_TO_SHOW = 5

    class Snippet(object):
        def __init__(self, lines_above, pattern, line_number):
            self.text = copy.copy(lines_above)
            self.pattern = pattern
            self.line_number = line_number

        def full(self):
            return len(self.text) >= LINES_ABOVE + LINES_BELOW + 1

        def add(self, line):
            self.text.append(line)

        def show(self):
            i = 0
            for line in self.text:
                if i == LINES_ABOVE:
                    sys.stdout.write('| {} ==>'.format(self.line_number))
                else:
                    if re.search(self.pattern, line):
                        sys.stdout.write('|-->')
                    else:
                        sys.stdout.write('|>')
                sys.stdout.write(line)
                i += 1

            sys.stdout.write('-' * 80 + '\n')

    class SnippetsQueue(object):
        def __init__(self):
            self.new_snippets = []
            self.ready_snippets = {}
            self.pattern_used = {}

        def push(self, snippet):
            if not self.pattern_used.get(pattern, False):
                self.new_snippets.append(snippet)
            self.pattern_used[pattern] = True

        def add(self, line):
            for snippet in self.new_snippets:
                if snippet.full():
                    self.make_ready(snippet)
                else:
                    snippet.add(line)

        def make_ready(self, snippet):
            self.new_snippets.remove(snippet)
            pattern = snippet.pattern
            try:
                self.ready_snippets[pattern].append(snippet)
            except KeyError:
                self.ready_snippets[pattern] = [snippet]
            self.pattern_used[pattern] = False

        def make_all_ready(self):
            for snippet in self.new_snippets:
                make_ready(snippet)

        def show(self):
            for pattern, snippets in self.ready_snippets.iteritems():
                print """\
*********************************************************************************
pattern: "{}"
*********************************************************************************\
""".format(pattern)
                for snippet in snippets[:SNIPPETS_TO_SHOW]:
                    snippet.show()

            pass

    snippets_queue = SnippetsQueue()

    lines_above = [''] * LINES_ABOVE

    line_number = 1
    for line in input_stream:
        lines_above.append(line)
        lines_above = lines_above[1:LINES_ABOVE+1]
        for pattern in patterns:
            if re.search(pattern, line):
                snippet = Snippet(lines_above, pattern, line_number)
                snippets_queue.push(snippet)
        snippets_queue.add(line)
        line_number += 1

    snippets_queue.make_all_ready()
    snippets_queue.show()


def main():
    parser = argparse.ArgumentParser(description=\
    """
        Parse file[s]\n\n
        examlpe: ./direlog.py file[s]
    """, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument('file', nargs='+', default=[],
                        help='file[s] to do some work')
    parser.add_argument('--snippets', action='store_const', const=True)
    args = parser.parse_args()

    def input_stream_generator(): return fileinput.input(args.file)

    # for line in input_stream_generator():
        # sys.stdout.write(line)
    if args.snippets:
        show_snippets(input_stream_generator())

    pass

if __name__ == '__main__':
    main()
