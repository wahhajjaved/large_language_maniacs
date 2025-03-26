#!/bin/python
import os
import sys
import cPickle as pickle
#from scipy.stats import wald
#import scipy
import numpy as np
import argparse
#import pprint
#import matplotlib.pyplot as plt
#import matplotlib.image as mpimg

'''Given relative barcode fitnesses, calculates relative codon and amino acid fitnesses, as well as sequence
entropy and information content. Also, given time constants for perturbed and unperturbed wildtype, calculates epistatic interaction
of each mutant with the perturbation. Currently propagates variance from standard error of barcode fitnesses,
but implements an empty function for estimating variance from a fitness to variance distribution.

To-do: implement estimate of variance from fitness-variance distribution.'''

NAN_REPLACEMENT = -100 #number to replace np.nan with for downstream analysis, should be absurdly large/small

def array_weighted_mean(l, variances):
    '''Calculates the inverse variance weighted average of list and returns average with variance'''
    vals = np.array(l)
    real_vals_indices = np.where(~np.isnan(vals))
    real_vals = vals[real_vals_indices]
    variances = np.array(variances)
    real_variances = variances[real_vals_indices]
    n = len(l)
    if n > 0 and n == len(real_variances):
        new_var = float(1/np.sum(1/real_variances**2))
        mean = float(new_var * np.sum(real_vals/real_variances**2))
        return mean, new_var
    return None

def rna_to_dna(x):
    '''Converts any RNA sequence to a DNA sequence'''
    return x.replace('U','T').replace('u','t')

def dna_to_rna(x):
    '''Converts any DNA sequence to a RNA sequence'''
    return x.replace('T','U').replace('t','u')

def codon_to_barcodes(pos, codon, allele_dict):
    '''Returns a list of barcodes that map to a specific codon/position combination'''
    return [x for x,y in allele_dict.items() if y[1]==codon and y[0]==pos]

def aa_to_codons(aa, translate_dict):
    '''Returns a list of codons that encode a specific amino acid (or stop)'''
    return [k for k,v in translate_dict.items() if v==aa]

def syn_codons(codon, translate_dict):
    '''Returns a list of codons synonymous to a given codon'''
    return [x for x in aa_to_codons(translate_dict[codon], translate_dict) if x != codon]

def codon_fitness_from_barcodes(barcode_fitness, allele_dict, wt_codon_dict, translate_dict, weighted_mean=True):
    '''Calculates fitness scores for all codons by averaging over fitness values for barcodes and
    returns as a dictionary of positions, then codons, where the corresponding value is a fitness score'''
    codon_fitnesses = {}
    codon_variances = {}

    for pos in wt_codon_dict.keys():
        for codon in translate_dict.keys():
            barcodes = codon_to_barcodes(pos, codon, allele_dict)
            barcode_lists = [barcode_fitness[x] for x in barcodes if not np.isnan(barcode_fitness[x][0])]
            if len(barcode_lists) > 0:
                barcode_fitnesses = np.array([x[0] for x in barcode_lists])
                barcode_stderrors = np.array([x[1] for x in barcode_lists])
                barcode_variances = barcode_stderrors**2

                if weighted_mean:
                    codon_fitness, codon_variance = array_weighted_mean(barcode_fitnesses, barcode_variances)
                else:
                    codon_fitness = np.nanmean(barcode_fitnesses)
                    codon_variance = np.sum(barcode_variances)/(len(barcode_variances)**2)

                codon_fitnesses[(pos, codon)] = float(codon_fitness)
                codon_variances[(pos, codon)] = float(codon_variance)
            else:
                codon_fitnesses[(pos, codon)] = np.nan
                codon_variances[(pos, codon)] = np.nan

    return codon_fitnesses, codon_variances

def calculate_aa_fitness(codon_fitness, codon_variance, wt_codon_dict, translate_dict, aa_index):
    '''Calculates the fitness of amino acids as the mean fitness of synonymous codons. Returns a numpy array
    of fitness values.'''
    aa_fitnesses = np.empty(shape=(len(aa_index.keys()),len(wt_codon_dict.keys())))
    aa_variances = np.empty(shape=(len(aa_index.keys()),len(wt_codon_dict.keys())))

    for j,pos in enumerate(sorted(wt_codon_dict.keys())):
        for aa,i in sorted(aa_index.items(), key=lambda x: x[1]):
            syn_codons = aa_to_codons(aa, translate_dict)
            syn_codon_fitness = np.array([codon_fitness[(pos, codon)] for codon in syn_codons if (pos, codon) in codon_fitness])
            syn_codon_variance = np.array([codon_variance[(pos, codon)] for codon in syn_codons if (pos, codon) in codon_variance])

            aa_fitness = np.nan
            aa_variance = np.nan
            if len(syn_codon_fitness) > 0:
                real_fitness_indices = np.where(~np.isnan(syn_codon_fitness))
                real_fitness = syn_codon_fitness[real_fitness_indices]
                real_variance = syn_codon_variance[real_fitness_indices]
                if len(real_fitness) > 0: 
                    aa_fitness = np.nanmean(real_fitness)
                    aa_variance = np.nansum(real_variance)/(len(real_variance)**2)

            aa_fitnesses[i,j] = float(aa_fitness)
            aa_variances[i,j] = float(aa_variance)
    return aa_fitnesses, aa_variances

def variance_from_fitness(fitness):
    '''Implements some fitness-variance distribution that allows estimation of variance from fitness value.
    Needs input.'''
    return np.nan

def calculate_sequence_entropy(matrix, aa_index):
    '''Calculates amino acid sequence entropy in bits. Sets lowest fitness value to -1, adds 1, then divides
    each fitness value at a given position by the total sum of fitness values at that position. Entropy
    is calculated by ignoring all NaN.'''
    #zeroed matrix has null growth as 0. Any fitness less than -1 is set to -1 as null.
    stop_index = aa_index['STOP']
    aa_indices = [x for x in range(len(matrix)) if x != stop_index]

    matrix_no_stop = matrix[aa_indices]

    zeroed_matrix = matrix_no_stop + 1
    real_zeroed_matrix = zeroed_matrix[np.where(np.isnan(zeroed_matrix))] = 0
    zeroed_matrix[np.where(real_zeroed_matrix < 0)] = 0

    summed_matrix = np.nansum(zeroed_matrix, axis=0)
    prob_matrix = zeroed_matrix / summed_matrix

    log_matrix = np.nan_to_num(np.log2(prob_matrix))
    entropy_components = prob_matrix * log_matrix
    entropy = -np.nansum(entropy_components, axis=0)

    return entropy

#enables us to pass an array to the function and get an array out.
array_variance_from_fitness = np.vectorize(variance_from_fitness, otypes=[np.float])

#run
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Given either a dictionary of fitness values for barcodes or codons with and without a perturbation, calculates interactions.")
    #necessary input_files
    parser.add_argument('barcode_fitness', type=str, default=None, nargs=2, metavar=["unperturbed_barcode_fitness", "perturbed_barcode_fitness"], help='pickle files encoding a dictionary of barcodes with a list containing counts and standard error')
    parser.add_argument('--wt_time_constants', type=float, nargs=2, default=None, metavar=["unperturbed_wt_time_constant, perturbed_wt_time_constant"], help='time constants for wildtype under both conditions')
    #necessary reference pickles
    parser.add_argument('--allele_dict', type=str, default=None, help='pickle file encoding a dictionary of alleles')
    parser.add_argument('--translate_dict', type=str, default=None, help='pickle file encoding a dictionary for translating from codon to amino acid')
    parser.add_argument('--wt_codon_dict', type=str, default=None, help='pickle file encoding a dictionary with the wild-type codon for each position')
    parser.add_argument('--aa_index', type=str, default=None, help='pickle file encoding a dictionary of amino acids and corresponding indeces used for arranging while plotting')
    #running options
    parser.add_argument('--weighted_mean', action='store_true', help='use weighted mean (by inverse variance) to calculate codon fitness from barcode')
    parser.add_argument('--variance_from_distribution', type=str, default=None, help='estimate aa variance from a fitness to variance distribution instead of propagating [default: False]')
    #output options
    parser.add_argument('--codon_fitness_pickle', type=str, default=None, help='file to save pickle of codon fitnesses')
    parser.add_argument('--rel_fitness_csv', type=str, default=None, help='file to save CSV of fitness array')
    parser.add_argument('--rel_fitness_pickle', type=str, default=None, help='file to save pickle of fitness array')
    parser.add_argument('--rel_fitness_variance_csv', type=str, default=None, help='file to save CSV of variances of fitness values')
    parser.add_argument('--sequence_entropy_pickle', type=str, default=None, help='file to save pickle of one-dimensional array of positional entropy (in bits)')
    parser.add_argument('--information_content_pickle', type=str, default=None, help='file to save pickle of one-dimensional array of information content (maximum entropy minus actual entropy, in bits)')
    parser.add_argument('--interaction_pickle', type=str, default=None, help='file to save pickle of interaction terms')
    args = parser.parse_args()

    #check to make sure right options specified
    if args.allele_dict is None or args.translate_dict is None or args.wt_codon_dict is None or args.aa_index is None:
        print "--allele_dict, --translate_dict, --wt_codon_dict, and --aa_index must be specified"
        parser.print_help()
        sys.exit()

    if args.wt_time_constants is None and args.interaction_pickle is not None:
        print "time constants must be provided with --wt_time_constants in order to calculate interactions"
        parser.print_help()
        sys.exit()


    #read in necessary reference pickles
    allele_dict = pickle.load(open(args.allele_dict, 'rb')) 
    translate_dict = pickle.load(open(args.translate_dict, 'rb'))
    dna_translate_dict = {rna_to_dna(x):y for x,y in translate_dict.items()} #uracil's for suckers
    wt_codon_dict = pickle.load(open(args.wt_codon_dict, 'rb'))
    aa_index = pickle.load(open(args.aa_index, 'rb'))
    
    #get barcode fitness
    unpert_barcode_rel_fitness = pickle.load(open(args.barcode_fitness[0], 'rb')) #key is barcode. value is tuple with slope and standard error
    pert_barcode_rel_fitness = pickle.load(open(args.barcode_fitness[1], 'rb')) 
    
    #bin to codon fitness
    unpert_codon_rel_fitness, unpert_codon_rel_variance = codon_fitness_from_barcodes(unpert_barcode_rel_fitness, allele_dict, wt_codon_dict, dna_translate_dict, args.weighted_mean)
    pert_codon_rel_fitness, pert_codon_rel_variance = codon_fitness_from_barcodes(pert_barcode_rel_fitness, allele_dict, wt_codon_dict, dna_translate_dict, args.weighted_mean)

    #average codon fitness to aa fitness
    unpert_aa_rel_fitness, unpert_aa_rel_variance = calculate_aa_fitness(unpert_codon_rel_fitness, unpert_codon_rel_variance, wt_codon_dict, dna_translate_dict, aa_index)
    pert_aa_rel_fitness, pert_aa_rel_variance = calculate_aa_fitness(pert_codon_rel_fitness, pert_codon_rel_variance, wt_codon_dict, dna_translate_dict, aa_index)

    #if user provided some input file with a fitness-variance distribution, pass to function (needs to be written)
    if args.variance_from_distribution is not None:
        unpert_aa_rel_variance = array_variance_from_fitness(unpert_aa_rel_fitness)
        pert_aa_rel_variance = array_variance_from_fitness(pert_aa_rel_fitness)

    #read out relative amino acid fitness matrix as a pickle (for visualization group)
    if args.rel_fitness_pickle is not None:
        out_array = np.copy(pert_aa_rel_fitness)
        out_array[np.where(np.isnan(out_array))] = NAN_REPLACEMENT
        pickle.dump(out_array, open(args.rel_fitness_pickle, 'w'))

    #read out relative amino acid fitness matrix as a CSV file (for difference matrix calculation)
    if args.rel_fitness_csv is not None:
        np.savetxt(args.rel_fitness_csv, pert_aa_rel_fitness, delimiter=",")

    #read out relative amino acid fitness variance matrix as a CSV file (for hypothesis testing)
    if args.rel_fitness_variance_csv is not None:
        np.savetxt(args.rel_fitness_variance_csv, pert_aa_rel_variance, delimiter=",")

    #calculate sequence entropy for perturbation (and information content), and save to pickle (for downstream visualization on structure)
    if args.sequence_entropy_pickle is not None or args.information_content_pickle is not None:
        pert_aa_entropy = calculate_sequence_entropy(pert_aa_rel_fitness, aa_index)
        
        #information content is the difference of actual entropy from maximum entropy (estimated as even fitness for all fitnesses measured)
        max_fitness = np.zeros_like(pert_aa_rel_fitness)
        max_fitness[np.where(np.isnan(pert_aa_rel_fitness))] = np.nan
        maximum_entropy = calculate_sequence_entropy(max_fitness, aa_index)
        information_content = maximum_entropy - pert_aa_entropy
        
        if args.sequence_entropy_pickle is not None:
            pert_aa_entropy[np.where(np.isnan(pert_aa_entropy))] = NAN_REPLACEMENT
            pickle.dump(pert_aa_entropy, open(args.sequence_entropy_pickle, 'w'))
        
        if args.information_content_pickle is not None:
            information_content[np.where(np.isnan(information_content))] = NAN_REPLACEMENT
            pickle.dump(information_content, open(args.information_content_pickle, 'w'))

    
    if args.interaction_pickle is not None:
        #time constants (reciprocal of doubling times)
        unpert_dw, pert_dw = args.wt_time_constants

        #calculate absolute fitness (time constants) of perturbed mutants
        pert_aa_abs_fitness = (pert_aa_rel_fitness+1)*pert_dw

        #calculate fitness of mutants, normalized to unperturbed wild-type (time constant)
        pert_aa_norm_fitness = pert_aa_abs_fitness/unpert_dw
        unpert_aa_norm_fitness = unpert_aa_rel_fitness + 1

        #calculate interaction of mutant and perturbation (wild-type will always be zero)
        interactions = pert_aa_norm_fitness - pert_aa_norm_fitness*unpert_aa_norm_fitness

        #output interaction matrix as pickle for visualization group
        if args.interaction_pickle is not None:
            out_array = interactions
            out_array[np.where(np.isnan(out_array))] = NAN_REPLACEMENT
            pickle.dump(out_array, open(args.interaction_pickle, 'w'))


