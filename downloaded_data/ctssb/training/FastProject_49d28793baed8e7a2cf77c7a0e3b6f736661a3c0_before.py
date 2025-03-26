# -*- coding: utf-8 -*-
"""
Created on Fri Jan 30 15:16:22 2015

@author: David
"""

import Global;
import argparse;


def parseFPArgs():
    parser = argparse.ArgumentParser(prog="FastProject", description='Analyze a set of expression data with FastProject.');

    parser.add_argument("data_file", help="Input expression data matrix");

    parser.add_argument("-k", "--housekeeping", metavar="FILE", default="",
                      help="Read list of housekeeping genes from FILE.  Uses default list if not specified");

    parser.add_argument("-s", "--signatures", metavar="FILE", nargs='*',
                      help="Loads signatures from FILE.");

    parser.add_argument("-p", "--precomputed", metavar="FILE", nargs='*',
                      help="Loads precomputed signature scores from FILE.");

    parser.add_argument("-o", "--output", metavar="DIRECTORY",
            help="Name of output directory.  Otherwise, output directory is auto-generated");

    parser.add_argument("--nofilter",   action="store_true",
            help="Project using all genes.");

    parser.add_argument("--nomodel",   action="store_true",
            help="No estimation of expression probability or false negative probability");

    parser.add_argument("--pca_filter", action="store_true",
            help="Filters PC principal components that correlate with a calculated QC metric for each sample");

    parser.add_argument("--qc",         action="store_true",
            help="Performs a quality check on samples, filtering samples that do not pass");

    parser.add_argument("--subsample_size", type=int, metavar="N", default=1000,
            help="Number of samples to use when sub_sampling. Default is 1000");

    parser.add_argument("--min_signature_genes", type=int, metavar="N", default=5,
            help="Signatures that match less than N genes in the data are discarded");

    parser.add_argument("--projections", metavar="FILE", nargs='*',
                        help="Loads projection coordinates from FILE");

    parser.add_argument("--weights", metavar="FILE",
                        help="Loads weights from FILE. Use these weights instead of FastProject's FNR calculation");

    parser.add_argument("--threshold", metavar="N", type=int,
                        help="Removes transcripts detected in less than N samples. " +
                               "Default is 20% of total sample count.")

    args = parser.parse_args();

    return args;


def entry():
    args = parseFPArgs();
    Global.args = args;

    from FastProject import Pipelines;
    Pipelines.FullOutput();


if(__name__ == "__main__"):
    entry();
