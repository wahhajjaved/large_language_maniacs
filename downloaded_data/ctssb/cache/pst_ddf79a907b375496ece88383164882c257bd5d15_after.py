#!/usr/bin/env python

"""
Program for showing the hierarchy of processes on a Linux computer
"""

__author__ = "Mike Accardo"
__copyright__ = "Copyright 2019, Mike Accardo"
__license__ = "MIT"


# imports
import sys
import subprocess
import argparse
import processparser as pp


def less(data):
    process = subprocess.Popen(["less"], stdin=subprocess.PIPE)

    try:
        process.stdin.write(data.encode('utf-8'))
        process.communicate()
    except IOError as e:
        pass


def my_parse_args():
    parser = argparse.ArgumentParser(
        description='Show the hierarchy of processes on a Linux computer.')
    parser.add_argument(
        "-o",
        "--output",
        action='store',
        type=str,
        dest='output',
        help="Directs the output to a file name of your choice")
    parser.add_argument("-c", "--command", action='store',
                        type=str, dest='command', help="Use custom ps command")
    parser.add_argument(
        "-w",
        "--write",
        action='store_true',
        dest='stdout',
        help="Write to stdout")
    args = vars(parser.parse_args())
    return args


def main(args):

    ps_command = args['command'] or 'ps -e l'
    column_header, processes = pp.get_ps_output(ps_command)

    # Find the index of the headings that we are interested in
    # (PID,PPID,COMMAND)
    heading_indexes = pp.get_heading_indexes(column_header)

    # Next, using the indexes, extract the process data
    process_info = pp.get_process_data(heading_indexes, processes)

    # We have all the essential information that we need. Time to build the
    # process trees.
    process_trees = pp.build_process_trees(process_info)

    tree_output = pp.format_process_trees(process_info, process_trees)

    if args['output']:
        with open(args['output'], 'w') as f:
            sys.stdout = f
            sys.stdout.write(tree_output)
    elif args['stdout']:
        sys.stdout.write(tree_output)
    else:
        less(tree_output)


if __name__ == '__main__':
    args = my_parse_args()
    main(args)
