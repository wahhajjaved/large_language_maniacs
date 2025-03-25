#!/usr/bin/env python

""" Python 3 implementation of signal_at_orf function of hwglabr package."""

import helpers
import sys
import os
import time
import pandas as pd
import numpy as np
from scipy.interpolate import InterpolatedUnivariateSpline
from colorama import Fore, Back, Style, init as colinit
colinit(autoreset=True)


def signal_at_orf(wiggle_data, gff_file, save_file=True):
    """
    Given wiggle data generated using the lab's ChIP-seq analysis pipelines (as a
    dictionary of pandas data frames; output of function read_wiggle), this function
    pulls out the ChIP signal over all ORFs in the yeast genome. It collects the
    signal over each ORF plus both flanking regions (1/2 the length of the ORF on
    each side) and scales them all to the same value (1000).

    This means that for two example genes with lengths of 500 bp and 2 kb, flanking
    regions of 250 bp and 1 kb, respectively, will be collected up and downstream.
    Both gene lengths will then be scaled to 500 and all four flanking regions to
    250.

    After scaling, fits a spline function passing through all signal points and uses
    it to output values of the signal at each integer position between 1 and 1000.

    Keyword arguments
    =================
    :param wiggle_data: dictionary of pandas data frames (output of function read_wiggle;
    no default)
    :param gff_file: string indicating path to the gff file providing the ORF coordinates
    (no default)
    :param save_file: boolean indicating whether output should be written to a TSV
    file (in current working directory; defaults to True)
    :return: Either a pandas DataFrame or a TSV file of a table with four columns:
            - chr: chromosome number
            - position: nucleotide coordinate (in normalized total length of 1 kb)
            - signal: ChIP-seq signal at each position (1 to 1000)
            - gene: Systematic gene name
    """

    t0 = time.time()

    # GFF
    gff = helpers.read_gff(gff_file)
    # Wiggle data
    wiggle = helpers.read_wiggle(wiggle_data, use_pbar=False)
    # Check reference genome
    gff_gen = helpers.check_genome(gff.ix[0, 'seqname'])
    wiggle_gen = helpers.check_genome(next(iter(wiggle.keys())))

    if gff_gen == wiggle_gen:
        print('Identified reference genome: ', end="")
        print(Fore.RED + gff_gen)
    else:
        sys.exit('Error: reference genomes in gff file and wiggle data don\'t match.')

    # Some feedback on the provided gff
    features = ', '.join(gff.ix[:, 'feature'].unique())
    print(Fore.YELLOW + 'The following types of features are present in the gff data you provided:')
    print(Fore.YELLOW + '(they will all be included in the analysis)')
    print(Fore.RED + features)

    print()
    print('Collecting signal...')
    print('(Skip genes with missing coordinates and signal in wiggle data)')

    # Create dfs to collect final data for all chrs
    plus_final = pd.DataFrame()
    minus_final = pd.DataFrame()

    # Keep track of total and non-skipped genes
    number_genes = 0
    number_skipped_genes = 0

    # Loop through chrs
    for chrNum, chromData in wiggle.items():
        print(Style.BRIGHT + chrNum + ':')
        # -------------------------------------- Plus strand ------------------------------------- #
        # Create data frame to collect final data for all genes in chr strand
        plus_strand = pd.DataFrame()

        # Get all genes on "+" strand of current chromosome
        chrgff = gff.loc[(gff['seqname'] == chrNum) & (gff['strand'] == '+')]

        gene_count = 0

        # Loop through rows (use itertuples because it's faster than iterrows)
        for row in chrgff.itertuples():
            # Skip if gene coordinates not in ChIPseq data
            if (row.start not in chromData.loc[:, 'position'] or
                        row.end not in chromData.loc[:, 'position']):
                continue

            # Collect flanking regions scaled according to ratio gene length / 1 kb
            gene_leng = row.end - row.start
            start = row.start - (gene_leng // 2)
            end = row.end + (gene_leng // 2)
            full_leng = (end - start) + 1
            gene = row.attribute

            # Pull out signal
            gene_data = chromData.loc[(chromData['position'] >= start) & (chromData['position'] <= end)]

            # Skip if there are discontinuities in the data (missing position:value pairs)
            if gene_data.shape[0] != full_leng:
                continue

            # Normalize to segment length of 1000
            pd.options.mode.chained_assignment = None  # Disable warning about chained assignment
            gene_data['position'] = gene_data['position'] - start + 1
            gene_data['position'] = gene_data['position'] * (1000 / full_leng)

            # Genes of different sizes have different numbers of positions; small genes
            # (<1000bp) cannot produce signal values for all 1000 positions and will have gaps
            # This means that longer genes with more signal values per each position in the
            # sequence of 1000 positions will contribute more to the final output.
            # In order to avoid this, first build an interpolation model of the signal and then
            # use it to project the signal onto the first 1000 integers
            f = InterpolatedUnivariateSpline(gene_data['position'], gene_data['signal'])
            new_positions = np.int_(np.linspace(1, 1000, num=1000, endpoint=True))
            new_signals = f(new_positions)

            # Make data frame for this gene
            gene_data = pd.DataFrame({'chr': chrNum, 'position': new_positions, 'signal': new_signals, 'gene': gene})

            # To collect all genes
            plus_strand = plus_strand.append(gene_data)

            gene_count += 1


        print('... + strand: {0} genes (skipped {1})'.format(gene_count,
                                                             chrgff.shape[0] - gene_count))

        # Keep track of total and non-skipped genes, to print info at the end
        number_genes += chrgff.shape[0]
        number_skipped_genes += chrgff.shape[0] - gene_count

        # To collect all chrs
        plus_final = plus_final.append(plus_strand)

        # ------------------------------------- Minus strand ------------------------------------- #
        # Create data frame to collect final data for all genes in chr strand
        minus_strand = pd.DataFrame()

        # Get all genes on "+" strand of current chromosome
        chrgff = gff.loc[(gff['seqname'] == chrNum) & (gff['strand'] == '-')]

        gene_count = 0

        # Loop through rows (use itertuples because it's faster than iterrows)
        for row in chrgff.itertuples():
            # Skip if gene coordinates not in ChIPseq data
            if (row.start not in chromData.loc[:, 'position'] or
                        row.end not in chromData.loc[:, 'position']):
                continue

            # Collect flanking regions scaled according to ratio gene length / 1 kb
            gene_leng = row.end - row.start
            start = row.start - (gene_leng // 2)
            end = row.end + (gene_leng // 2)
            full_leng = (end - start) + 1
            gene = row.attribute

            # Pull out signal
            gene_data = chromData.loc[(chromData['position'] >= start) & (chromData['position'] <= end)]

            # Skip if there are discontinuities in the data (missing position:value pairs)
            if gene_data.shape[0] != full_leng:
                continue

            # Normalize to segment length of 1000
            pd.options.mode.chained_assignment = None  # Disable warning about chained assignment
            gene_data['position'] = gene_data['position'] - start + 1
            gene_data['position'] = gene_data['position'] * (1000 / full_leng)

            f = InterpolatedUnivariateSpline(gene_data['position'], gene_data['signal'])
            new_positions = np.int_(np.linspace(1, 1000, num=1000, endpoint=True))
            new_signals = f(new_positions)

            # Reverse the order of the position values
            new_positions = (1000 - new_positions) + 1

            # Make data frame for this gene
            gene_data = pd.DataFrame({'chr': chrNum,
                                     'position': new_positions,
                                     'signal': new_signals,
                                     'gene': gene})

            # To collect all genes
            minus_strand = minus_strand.append(gene_data)

            gene_count += 1


        print('... - strand: {0} genes (skipped {1})'.format(gene_count,
                                                             chrgff.shape[0] - gene_count))

        # Keep track of total and non-skipped genes, to print info at the end
        number_genes += chrgff.shape[0]
        number_skipped_genes += chrgff.shape[0] - gene_count

        # To collect all chrs
        minus_final = minus_final.append(minus_strand)

    # Merge '+' and '-' strand data
    merged_strands = plus_final.append(minus_final)

    # Sort by gene and position
    merged_strands = merged_strands.sort_values(['gene', 'position'])

    # Print info on total and non-skipped genes
    print()
    print('------')
    percent_skipped = np.around(number_skipped_genes * 100 / number_genes, decimals=1)
    print(Back.RED + 'Skipped {0} of a total of {1} genes ({2}%)'.format(number_skipped_genes,
                                                       number_genes, percent_skipped))
    print('------')

    if save_file:
        file_name = os.path.basename(os.path.normpath(wiggle_data)) + '_metaORF.tsv'
        print(Fore.YELLOW + 'Saving output to file:')
        print(file_name)
        merged_strands.to_csv(file_name, sep='\t', index=False)
        print()
        print(Fore.CYAN + 'Completed in ', end=" ")
        helpers.print_elapsed_time(t0)
    else:
        print()
        print(Fore.CYAN + 'Completed in ', end=" ")
        helpers.print_elapsed_time(t0)
        return merged_strands


def main():
    print()
    print(Style.BRIGHT + "----------------------------------------------------")
    print(Style.BRIGHT + "          MEAN ChIP-SEQ SIGNAL AT META ORF")
    print(Style.BRIGHT + "----------------------------------------------------")
    print()
    signal_at_orf(wiggle_data=args.wiggle_data, gff_file=args.gff_file, save_file=True)
    print(Style.BRIGHT + "----------------------------------------------------")
    print()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Calculate mean ChIP-seq signal at ORF")
    parser.add_argument('-w', '--wiggle_data', help=("path to a folder containing wiggle data"
                                                     "to get ChIP-seq signal from"), required=True)
    parser.add_argument('-g', '--gff_file', help='path to gff file', required=True)
    args = parser.parse_args()
    main()
