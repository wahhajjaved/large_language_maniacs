#!/usr/bin/env python

from __future__ import division
from graph2 import Graph
import json
import os
import pdb
import logging
import operator
from datetime import datetime
from collections import OrderedDict
import sys

def average_degree_graph(graph):
    """get average degree of a graph object"""
    edges = float(len(graph.edges()))
    no_vertices = float(len(graph.vertices()))
    if no_vertices != 0:
        average_degree = round(2*edges/no_vertices, 2)
        # print '%.2f' % average_degree
    # print 'res:', edges, no_vertices, average_degree
    return '%.2f' % average_degree

def main():
    try:
        with open(sys.argv[1], 'r') as tweets, open (sys.argv[2], 'w') as output:
            # make a pretty global dictionary to store time and hashtag info
            hashtag_dict = OrderedDict()
            result = 0.00
            # iterate over the input file, one line at a time
            for line in tweets:
                tweet = line.decode('utf-8')
                tweet_json = json.loads(tweet) # dict object
                if 'created_at' in tweet_json: # needed to address keyError
                    # get the time of the tweet
                    created_at = datetime.strptime(tweet_json['created_at'].encode('utf-8'), "%a %b %d %H:%M:%S +0000 %Y")
                    # get the time of the last tweet
                    if len(hashtag_dict.keys()) == 0:
                        time_last_tweet = created_at
                    else:
                        time_last_tweet = hashtag_dict.keys()[-1]
                    # ensure to only address tweets not over 60 seconds older than the last
                    time_delta = created_at - time_last_tweet
                    if time_delta.total_seconds() > - 60:
                        if 'entities' in tweet_json:
                            if 'hashtags' in tweet_json['entities']:
                                hashtags = tweet_json['entities']['hashtags']
                                hashtag_list = [i['text'].encode('utf-8').strip() for i in hashtags]
                                # update hashtag_dict with tweet of at least 2 tags
                                hashtag_list = list(set(hashtag_list)) # keep only unique tags
                                if len(hashtag_list) > 1:
                                    hashtag_dict[created_at] = hashtag_list
                    else:
                        continue

                    # remove the tweets more than 60 second older than the current tweet
                    sorted_key_list = sorted(hashtag_dict.keys())
                    for k in sorted_key_list:
                        time_elapsed = created_at - k
                        if time_elapsed.total_seconds() > 60:
                            del hashtag_dict[k]
                        else:
                            break

                    # finally, initialize the graph, and derive average degree
                    graph = Graph()
                    for k in hashtag_dict:
                        for tag in hashtag_dict[k]:
                            graph.add_vertex(tag)
                        length = len(hashtag_dict[k])
                        for start in range(length - 1):
                            for end in range(start+1, length):
                                graph.add_edge((hashtag_dict[k][start], hashtag_dict[k][end]))
                        result = average_degree_graph(graph)

                # ignore those lines without 'created_at'
                else:
                    continue
                # for each valid line, report the result
                print result
                output.write(str(result) + '\n')

    except IOError as err:
        print 'File error:', str(err)

if __name__ == '__main__':
    main()
