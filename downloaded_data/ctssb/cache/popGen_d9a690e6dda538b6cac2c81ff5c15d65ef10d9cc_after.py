#!/usr/bin/env python
# encoding: utf-8
"""
clf.make_suparparent.py

@author:     cmusselle

@license:    license

@contact:    user_email

"""

# import modules used here -- sys is a very standard one
import os, argparse, logging
import subprocess
import glob

from Bio import SeqIO


# Gather code in a main() function
def main(args, loglevel):
    # Setup Logging
    logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)

    logging.debug('Argumnets passed:\n{}'.format(str(dir(args))))

    # Get generators for filepaths
    if 'all' in args.subpops:

        all_files = glob.glob(os.path.join(args.inpath, "sample_*"))
        basenames = [(os.path.split(name)[1]).split('.')[0] for name in all_files]

        # get unique baseneamse
        basenames = list(set(basenames))

        # Generator to return all file basenames.
        file_gen = (x for x in basenames)
        file_gen_list = [file_gen]
    else:
        # Load in barcode dictionary
        f = open(args.barcodes, 'rb')
        mid2file = {}
        file2mid = {}
        for line in f:
            line = line.strip().split('\t')
            mid2file[line[0]] = line[1] # Midtag \t filename pairs per line. Need to map filename 2 MID
            file2mid[line[1]] = line[0] # Midtag \t filename pairs per line. Need to map filename 2 MID
        f.close()

        # List of raw filenames
        filenames = file2mid.keys()

        file_gen_list = []
        for i, subpop in enumerate(args.subpops):

            # Filenames and barcodes corresponding to subpopulation
            files = [fname for fname in filenames if subpop in fname]
            barcodes = [file2mid[fname] for fname in files]

            file_gen = (os.path.join(args.inpath, 'sample_' + b) for b in barcodes)
            file_gen_list.append(file_gen)

    # MAtch all files to cataloge with sstacks
    sqlidx = args.start_sqlidx
    for gen in file_gen_list:
        for sample_filepath in gen:

            sqlidx += 1
            # sstacks -b batch_id -c catalog_file -s sample_file [-r sample_file] [-o path] [-p num_threads]
            #[-g] [-x]

            #p — enable parallel execution with num_threads threads.
            #b — MySQL ID of this batch.
            #c — TSV file from which to load the catalog RAD-Tags.
            #r — Load the TSV file of a single sample instead of a catalog.
            #s — TSV file from which to load sample RAD-Tags.
            #o — output path to write results.
            #g — base matching on genomic location, not sequence identity.
            #x — don’t verify haplotype of matching locus.

            cmd = "sstacks -b {batch_id} -c {catalog_file} -s {sample_file} -o {outpath} -p {num_threads}".format(
                    batch_id=sqlidx, catalog_file=args.catalogue_filepath, sample_file=sample_filepath,
                    outpath=args.outpath, num_threads=args.processors)

            if args.use_genomic_location:
                cmd += ' -g'
            if args.skip_verify_haplotype:
                cmd += ' -x'

            logging.debug("About to run sstacks with following comandline arguments:\n{}\n".format(str(cmd.split())))
            subprocess.check_call(cmd.split())
            logging.info("Finished matching {} with sstacks".format(sample_filepath))


# Standard boilerplate to call the main() function to begin
# the program.
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Given a subpopulation and a catalogue, this script runs sstacks on each '
                    'sample_file to match it to the catalogue.')

    parser.add_argument(
        "-s", dest="subpops",
        required=True,
        nargs='+',
        help="List of string patterns denoting files that make up separate Subpopulations. 'all' will run all samples"
             "from all subpopulations.")

    parser.add_argument(
        "-P", dest="inpath",
        help="Input file path for all processed files if not specifying a subpop.")

    parser.add_argument(
        "-c", dest="catalogue_filepath",
        help="File path location of catalogue to use.")

    parser.add_argument(
        "-x", dest="start_sqlidx",
        default=1, type=int,
        help="Starting index to use for MySql index when storing data. Value is incremented for multiple input subpops")

    parser.add_argument(
        "-b", dest="barcodes",
        help="Barcode file to use for mapping mid to filenames.")

    parser.add_argument(
        "-g", dest="use_genomic_location",
        help="Base matching on genomic location, not sequence identity.")

    parser.add_argument(
        "-X", dest="skip_verify_haplotype",
        help="don’t verify haplotype of matching locus.")

    parser.add_argument(
        "-o", dest="outpath",
        required=True,
        help="Location to write sstacks output")

    parser.add_argument(
        "-p", dest="processors", default=1,
        help="Number of processors to run sstacks with.")

    parser.add_argument(
        "-v", "--verbose",
        help="increase output verbosity",
        action="store_true")

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    main(args, loglevel)