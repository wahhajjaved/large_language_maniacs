#! /usr/bin/env python

"""Sum CB values for groups of sequences."""

import argparse
from collections import Counter
import math
import sys


class LineParser(object):
    def __init__(self, indices):
        id_index, site_index, obs_index, exp_index = indices
        self.id_index = id_index
        self.site_index = site_index
        self.obs_index = obs_index
        self.exp_index = exp_index

    def __call__(self, line):
        vals = line.strip().split("\t")
        sid = vals[self.id_index]
        site = vals[self.site_index]
        obs = float(vals[self.obs_index])
        exp = float(vals[self.exp_index])
        total = int(vals[-1])
        if math.isnan(exp) or math.isinf(exp):
            exp = 0
        return sid, site, obs, exp, total


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sum CB values for groups of sequences."
    )
    parser.add_argument(
        "intsv", metavar="TSV", type=argparse.FileType("r"),
        help="input table of CB values"
    )
    parser.add_argument(
        "-g", "--groups", metavar="DICT", type=argparse.FileType("r"),
        default=sys.stdin, help="""input dict of 'group ID': 'sequence
        IDs', default is STDIN"""
    )
    parser.add_argument(
        "-o", "--out", dest="outsv", metavar="FILE",
        type=argparse.FileType("w"), default=sys.stdout,
        help="output file, default is STDOUT"
    )
    index_group_desc = (
        "All column indices are counted from 0 and could be negative\n"
        "(-1 means the last column)."
    )
    index_group = parser.add_argument_group(
        "column index arguments", description=index_group_desc
    )
    index_group.add_argument(
        "-I", "--id-index", metavar="N", type=int, default=0,
        help="sequence ID column index, default 0"
    )
    index_group.add_argument(
        "-S", "--site-index", metavar="N", type=int, default=1,
        help="site column index, default 1"
    )
    index_group.add_argument(
        "-O", "--obs-index", metavar="N", type=int, default=2,
        help="observed number column index, default 2"
    )
    index_group.add_argument(
        "-E", "--exp-index", metavar="N", type=int, default=-3,
        help="expected number column index, default -3"
    )
    args = parser.parse_args(argv)
    indices = (args.id_index, args.site_index,
               args.obs_index, args.exp_index)
    line_parser = LineParser(indices)
    sid_to_gid = dict()
    with args.groups as indct:
        for line in indct:
            if line.startswith("#"):
                continue
            group_id, sid_list = line.strip().split("\t")
            for sid in id_list.split(","):
                sid_to_gid[sid] = group_id
    cbvals = dict()
    with args.intsv as intsv:
        for line in intsv:
            if line.startswith("#"):
                continue
            sid, site, obs, exp, total = line_parser(line)
            gid = sid_to_gid[sid]
            pair = (sid, site)
            obs_, exp_, total_ = cbvals.get(pair, (0, 0, 0))
            cbvals[pair] = (obs+obs_, exp+exp_, total+total_)

    with args.outsv as outsv:
        outsv.write(
            "#:Sequence ID\tSite\tObserved\tExpected\tRatio\tTotal\n"
        )
        for (gid, site), (obs, exp, total) in sorted(cbvals):
            ratio = obs / exp
            outsv.write("%s\t%s\t%d\t%.2f\t%.3f\t%d\n" % (
                gid, site, obs, exp, total
            ))


if __name__ == "__main__":
    sys.exit(main())
