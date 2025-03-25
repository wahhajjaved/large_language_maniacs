#!/usr/bin/env python
# movie recommendations
import urllib
import random
import argparse
from lxml import etree

class Movie(object):
    def __init__(self, title):
        self.title = title

def movies_like(movie_title):
    url = "http://www.tastekid.com/ask/ws?" + urllib.urlencode({'q' : movie_title})
    doc = etree.parse(url)
    for rec in doc.xpath('/similar/results/resource'):
        yield Movie(rec.xpath('name')[0].text)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--number', type=int, help='number of recommendations to display (default: 3)', default=3)
    parser.add_argument('-r', '--random', action='store_true', help='randomize the results')
    parser.add_argument('movie_title', help='the title of a movie you like', nargs='+')
    args = parser.parse_args()

    recommendations = list(movies_like(' '.join(args.movie_title)))
    if args.random:
        random.shuffle(recommendations)
    for movie in recommendations[:args.number]:
        print movie.title

if __name__ == "__main__": 
    main()
