#!/usr/bin/env python3

import requests
import argparse
from bs4 import BeautifulSoup

base_url = 'http://www.wordreference.com'

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.87 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, sdch",
    "Accept-Language": "en-US,en;q=0.8"
}

parser = argparse.ArgumentParser()
parser.add_argument('from_to')
parser.add_argument('word')
args = parser.parse_args()

url = base_url + '/' + args.from_to + '/' + args.word

r = requests.get(url, headers=headers)
html = r.text

soup = BeautifulSoup(html, 'lxml')


def has_class(el, classes):
    if 'class' not in el.attrs:
        return False
    if isinstance(classes, str):
        classes = (classes, )
    if set(el.attrs['class']).isdisjoint(set(classes)):
        return False
    return True


def get_first_class(el, default=''):
    if 'class' not in el.attrs:
        return default
    return el.attrs['class'][0]


def get_definition_lines(el):
    lines = []
    words = [];
    for child in el.children:
        tag_name = child.name
        if not tag_name:  # it's a string node
            s = child.strip()
            if s and s != ';':
                words.append(s)
        elif tag_name != 'br':
            if has_class(child, ('i', 'ic')) and len(child.string) <= 3:
                continue
            words.append(' '.join(child.stripped_strings))
        else:  # br => start new line
            line = ' '.join(w for w in words if w)
            if line:
                lines.append(line)
            words = []
    if words:
        line = ' '.join(w for w in words if w)
        if line:
            lines.append(line)
    return lines


# try first format (table.WRD)
results = []
result = {}

for tr in soup.select('table.WRD tr'):
    if not has_class(tr, ('even', 'odd')): continue
    for td in tr.select('td'):
        c = get_first_class(td)
        if c == 'FrWrd':
            if result:
                results.append(result)
                result = {}
            result['word'] = ' '.join(td.strong.stripped_strings)
            result['trans'] = []
        elif c == 'ToWrd':
            s = list(td.strings)
            result['trans'].append(s[0])
        elif td.string:
            s = str(td.string).strip()
            if s.startswith('('):
                result['syn'] = s
if result:
    results.append(result)

# print first format
for result in results:
    header = result['word']
    if 'syn' in result:
        header = header + " " + result['syn']
    print()
    print(header)
    for trans in result['trans']:
        print("    %s" % trans)


if results:
    quit()


# second format (.trans)
results = []

# sometimes it is a table
for tr in soup.select('table.trans tr'):
    result = []
    for td in tr.select('td'):
        if get_first_class(td) == 'nums1':
            continue
        lines = get_definition_lines(td)
        if lines:
            result.extend(lines)
    if result:
        results.append(result)

# sometimes it's a div
if not results:
    for div in soup.select('#article .trans'):
        result = get_definition_lines(div)
        if result:
            results.append(result)

# print second format
for i, result in enumerate(results):
    for j, line in enumerate(result):
        if j == 0:
            print("%i. %s" % (j + 1, line))
        else:
            print("    %s" % line)
