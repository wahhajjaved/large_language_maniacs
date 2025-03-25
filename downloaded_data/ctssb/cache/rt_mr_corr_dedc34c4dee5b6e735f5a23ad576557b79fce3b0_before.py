#!usr/bin/python

#libraries:
import subprocess
import sys
import copy
import csv
import pandas as pd
import numpy as np
import scipy as scipy
from scipy.stats import pearsonr
import math
import matplotlib.pyplot as plt
#from matplotlib_venn import venn3, venn3_circles, venn2, venn2_circles
import itertools
from copy import deepcopy
from collections import defaultdict
#from datetime import datetime
from random import randint
import warnings
import pickle


pd.options.display.mpl_style = 'default'


#functions:
def bedtools_operation_cmd( query_regions_path, query_regions_file,\
                            regions_to_apply_path, regions_to_apply_file,\
                            kind_of_operation, files_are_sorted = True):
    cmd = ['bedtools']
    cmd.append(kind_of_operation)
    cmd.append('-a')
    cmd.append(query_regions_path + query_regions_file)
    cmd.append('-b')
    cmd.append(regions_to_apply_path + regions_to_apply_file)
    if files_are_sorted: cmd.append('-sorted')
    return cmd

def total_size_of_regions(query_regions_path, query_regions_file):
    size_cmd = ['awk','{SUM += $3-$2} END {print SUM}']
    size_cmd.append(query_regions_path + query_regions_file)
    #note-to-self: handle exceptions here
    total_size_op = subprocess.Popen(size_cmd, stdout=subprocess.PIPE,\
                                                stderr=subprocess.PIPE)
    total_size, err = total_size_op.communicate()
    return int(total_size)

def no_of_mutations_in_regions( query_regions_path, query_regions_file,\
                                mutations_path, mutations_file):
    find_mut_cmd = bedtools_operation_cmd(  query_regions_path,\
                                            query_regions_file,\
                                            mutations_path, mutations_file,\
                                            'intersect')
    intersecting_mutations = subprocess.Popen(find_mut_cmd,\
                                                stdout=subprocess.PIPE,\
                                                stderr=subprocess.PIPE)
    no_of_intersecting_mutations = subprocess.check_output(('wc', '-l'),\
                                        stdin=intersecting_mutations.stdout)
    return int(no_of_intersecting_mutations)

def bedtools_subtract_and_save_results(query_regions_path, query_regions_file,\
                                        regions_to_subtract_path,\
                                        regions_to_subtract_file,\
                                        resulting_regions_path,\
                                        resulting_regions_file):
    bedtools_subtract_cmd = bedtools_operation_cmd(query_regions_path,\
                                                    query_regions_file,\
                                                    regions_to_subtract_path,\
                                                    regions_to_subtract_file,\
                                                    'subtract', False)
    apply_command_and_save_output(bedtools_subtract_cmd,\
                                    resulting_regions_path,\
                                    resulting_regions_file)

def bedtools_intersect_and_save_results(query_regions_path,\
                                        query_regions_file,\
                                        regions_to_intersect_path,\
                                        regions_to_intersect_file,\
                                        resulting_regions_path,\
                                        resulting_regions_file):
    bedtools_intersect_cmd = bedtools_operation_cmd(query_regions_path,\
                                                    query_regions_file,\
                                                    regions_to_intersect_path,\
                                                    regions_to_intersect_file,\
                                                    'intersect')
    apply_command_and_save_output(bedtools_intersect_cmd,\
                                    resulting_regions_path,\
                                    resulting_regions_file)

def apply_command_and_save_output(cmd, destination_path, destination_file):
    #shell way:
    cmd.append('>')
    cmd.append(destination_path + destination_file)
    subprocess.call(' '.join(cmd),shell=True)
    #python way:
    """
    op = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, err = op.communicate()
    with open(destination_path + destination_file, 'w') as output_file:
        output_file.write(output)
    """

def regions_file_name(regions_name):
    file_prefix = 'reg_'
    file_suffix = '.bed'
    return file_prefix + regions_name + file_suffix

#note: mutations and polymorphisms are point sites in the genome
def sites_file_name(sites_name):
    file_suffix = '.bed'
    return sites_name + file_suffix

#to-do
def filter_initial_regions():
    pass

#to-do
def bin_rt_state_of_query_regions():
    pass

def no_of_sites_in_region(sites, reg_chrom, reg_chrom_start, reg_chrom_end):
    return len(sites[(sites.chrom == reg_chrom) & (sites.chrom_start>=reg_chrom_start)& (sites.chrom_end<=reg_chrom_end)].index)

#to-do: currently this is hardcoded, allow more states
#global variables:
no_of_rt_states = 4
list_of_rt_states = ['s'+str(i+1) for i in range(no_of_rt_states)]
#query_regions_prepared = True

#no_of_resampling = 10**3
#resampling_ratio = 0.9

#to-do: allow custom output folder
#analysis:
current_dir = './'
output_dir = './../../output/initial_analysis/binned_rt_sr_corr/'
input_dir = './../../data/formatted_regions_sites/'

initial_regions = sys.argv[1]
filters = sys.argv[2]
query_regions = initial_regions + '__' + filters
query_regions_file = regions_file_name(query_regions)
rt_regions = sys.argv[3]
site_dataset = sys.argv[4]
site_dataset_file = sites_file_name(site_dataset)
win_size = int(sys.argv[5])


"""
e.g.:
initial_regions: 'whole'
filters: 'acc_nc_auto'
query_regions = 'whole__acc_nc_auto'
rt_regions = 'uva_rt'
site_dataset = 'snp_pg_jw'
"""
analysis_folder_suffix =  ''
try:
    analysis_folder_suffix = sys.argv[6]
except:
    pass

analysis_folder = '__'.join([initial_regions, filters, \
                             rt_regions, site_dataset])
if analysis_folder_suffix:  analysis_folder += '__' + analysis_folder_suffix
analysis_dir = output_dir + analysis_folder + '/'
print 'creating analysis folder: ' + analysis_folder
subprocess.call('mkdir ' + analysis_dir, shell=True)


#to-do
#if query_regions_prepared is False:
#    filter_initial_regions(query_regions_file)


total_no_of_muts = total_size_of_regions(input_dir, \
                                         site_dataset_file)
total_sizes_of_all_rt_binned_regs = []
no_of_muts_in_all_rt_binned_regs = []

#binning the regions into n subsets for each rt state
#saving the resulting subsets in respective files
#measuring the total size of each subset
#counting the corresponding mutations in each subset
#note-to-self: might want to keep these regions ready for the script
for rt_state in list_of_rt_states:
    print 'intersecting with ' + rt_state
    rt_state_regs_file = regions_file_name(rt_regions.strip('rt') + rt_state)
    rt_binned_query_regions_file = regions_file_name(query_regions + '__'\
                                        + rt_regions.strip('rt') + rt_state)
    bedtools_intersect_and_save_results(input_dir, query_regions_file, \
                                        input_dir, rt_state_regs_file, \
                                        analysis_dir, \
                                        rt_binned_query_regions_file)
    print 'saving rt binned query regions file for ' + rt_state
    total_size_of_rt_binned_regs = total_size_of_regions(analysis_dir, \
                                                         rt_binned_query_regions_file)
    no_of_muts_in_rt_binned_regs = no_of_mutations_in_regions(analysis_dir, \
                                                              rt_binned_query_regions_file, \
                                                              input_dir, \
                                                              site_dataset_file)
    total_sizes_of_all_rt_binned_regs.append(total_size_of_rt_binned_regs)
    no_of_muts_in_all_rt_binned_regs.append(no_of_muts_in_rt_binned_regs)

print total_no_of_muts
print total_sizes_of_all_rt_binned_regs
print no_of_muts_in_all_rt_binned_regs


sites  = pd.read_csv(input_dir + site_dataset_file,delimiter = '\t',header=None, names = ['chrom','chrom_start','chrom_end'] )


for rt_state in list_of_rt_states:
    #for each rt
    rt_binned_query_regions_file = regions_file_name(query_regions + '__' \
                                                     + rt_regions.strip('rt') + rt_state)
    rt_binned_regs = pd.read_csv(analysis_dir+rt_binned_query_regions_file,delimiter = '\t',header=None, names = ['chrom','chrom_start','chrom_end'] )
    cur_win_len = 0
    cur_win_site_count = 0
    win_site_counts = []
    for i, reg in enumerate(rt_binned_regs.iterrows()):
        cur_reg_len = reg[1].chrom_end - reg[1].chrom_start
        #we are extending theo current window
        #if the current region length is not exceeding our window size:
        if cur_reg_len <= (win_size-cur_win_len):
            cur_win_len += cur_reg_len
            #count the number of sites that fall within current region
            cur_reg_site_count = no_of_sites_in_region(sites, reg[1].chrom, reg[1].chrom_start, reg[1].chrom_end)
            cur_win_site_count += cur_reg_site_count
        #to-do: here I am assuming the regions cannot exceed more than 1 windows. i.e. reg_size << window_size
        #else if the current region is exceeding our window size:
        else:
            #count sites in first portion of current region
            cur_reg_first_portion_site_count = no_of_sites_in_region(sites, reg[1].chrom, reg[1].chrom_start,reg[1].chrom_start+ (win_size-cur_win_len))
            cur_win_site_count += cur_reg_first_portion_site_count
            win_site_counts.append(cur_win_site_count)

            #to-do: current region might be even larger than the win_size, tackle that scenario

            #update cur_win_len for next iteration:
            cur_win_len = cur_reg_len - (win_size-cur_win_len)

            #update cur_win_site_count for next iteration:
            cur_reg_second_portion_site_count = no_of_sites_in_region(sites, reg[1].chrom, reg[1].chrom_start+ (win_size-cur_win_len),reg[1].chrom_end)
            cur_win_site_count = cur_reg_second_portion_site_count
    #pickle win_site_counts + rt_state + win_size
    print 'site counts for windows saved for rt state ' + rt_state
    win_site_counts_filename = output_dir + 'win_site_counts_'+str(win_size)+'_' +rt_state+'.pickle'
    fileObject = open(win_site_counts_filename, 'wb')
    pickle.dump(win_site_counts, fileObject)
    fileObject.close()