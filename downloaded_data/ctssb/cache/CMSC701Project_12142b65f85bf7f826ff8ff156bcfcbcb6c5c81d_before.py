__author__ = 'Rob Argue'
__author__ = 'Tommy Pensyl'

from project import *
import profile
import time
import numpy

#global? I just kinda guessed
alphabet = {'A':0,'C':1,'G':2,'T':3}
    
def get_q_freqs(qry, search_range):
    q_freq = []
    for q in qry:
        string = q[1]
        freq_arr = [0]*4
        for i in range(min(search_range,len(string))):
            freq_arr[alphabet[string[i]]] += 1
        q_freq.append(freq_arr)
    return q_freq

# gets letter count for all prefixes
def get_cumulative_freqs(string):
    freqs = numpy.matrix([[0]*4]*len(string))
    freq_arr = [0]*4
    for i in range(0,len(string)):
        freq_arr[alphabet[string[i]]] += 1
        freqs[i] = freq_arr
    return freqs

# gets letter counts for a string
def get_freqs(string, length = None, freqs = None):
    if length == None:
        length = len(string)

    if freqs == None:
        freqs = numpy.array([0] * len(alphabet))
    else:
        for i in range(len(alphabet)):
            freqs[i] = 0

    for i in range(length):
        freqs[alphabet[string[i]]] += 1

    return freqs

# optimimzed culling function
def cull(pat_freq, str_freq, cutoff):
    sum = 0

    for let in range(len(alphabet)):
        pat_let = pat_freq[let]
        str_let = str_freq[let]
        
        if pat_let > str_let:
            sum += pat_let - str_let
        else:
            sum += str_let - pat_let

    return sum > 2 * cutoff

def run(reference, query, cutoff = 5, search_range = 100, out_file = None, verbose = False):
    if verbose:         
        print 'Run info:'
        print '  Time : ' + time.asctime()
        if isinstance(reference, str):
            print '  Reference file : ' + reference
        if isinstance(query, str):
            print '  Query file : ' + query
		#print '  Output file : ' + out_file
        print '  Cutoff : ' + str(cutoff)
        print '  Search range : ' + str(search_range)
        print ''


    time_start = time.time()

    if out_file == None:
        out_file = time.strftime('%y_%m_%d_%H_%M_%S') + '_cutoff_' + str(cutoff) + '_range_' + str(search_range) + '.txt'

    out = open(out_file, 'w')


    ### \/ Loading data \/ ###

    time_loading_start = time.time()

    if verbose:
        print 'Loading data'

    if isinstance(reference, str):
        if verbose:
            print '  Loading ' + reference

        ref = parseFASTA(reference)
    
    else:
        ref = reference
    
    ################
    #ref = ref[0:5]#                                     # Hack here
    ################
    
    if isinstance(query, str):
        if verbose:
            print '  Loading ' + query
    
        qry = parseFASTA(query)

    else:
        qry = query

    #####################
    #qry = qry[0:100000]#                                # and here
    #####################

    if verbose:
        print '  Load time : %.3f s' % (time.time() - time_loading_start)
        print ''

    ### /\ Loading data /\ ###



    ### \/ Query preprocessing \/ ###

    time_prep_start = time.time()
    if verbose:
        print 'Preprocessing queries'
        print '  - Num queries'

    num_queries = len(qry)

    if verbose:
        print '  - Max length'

    max_len = max([len(q[1]) for q in qry])
    #search_range = min([len(x[1]) for x in qry])       # TODO : this

    if verbose:
        print '  - Query frequencies'

    q_freq = get_q_freqs(qry, search_range)

    if verbose:
        print '  Time : %.3f s' % (time.time() - time_prep_start)
        print ''

    ### /\ Query preprocessing /\ ###



    ### \/ Matching \/ ###

    time_match_start = time.time()

    if verbose:
        print 'Matching'
        print ''

    count = 0
    arr1 = numpy.array([0] * (max_len + 1))
    arr2 = numpy.array([0] * (max_len + 1))
    pat_freq = numpy.array([0] * len(alphabet))


    for pat in ref:
    
        time_single_match_start = time.time()

        line = pat[0]

        pat_freq = get_freqs(pat[1], search_range, pat_freq)

        num_culled = 0    
        num_matched = 0
        for i in range(len(qry)):
            q = qry[i]
            if not cull(pat_freq, q_freq[i], cutoff):
                edit_dist = dynamic_opt(pat[1], q[1], cutoff, arr1, arr2)
                if edit_dist <= cutoff:
                    num_matched += 1
                    line = line + ' ' + q[0]    
            else:
                num_culled+=1
            
        line = line + '\n'
        out.write(line)

        if verbose:
            count += 1
            percent_culled = 100.0 * float(num_culled) / float(num_queries)

            print 'Reference ' + str(count) + ' (' + pat[0] + '):' 
            print '  Time : %.3f s' % (time.time() - time_single_match_start)
            print '  Queries culled : ' + str(num_culled) + ' / ' + str(num_queries) + ' (%.2f%%)' % percent_culled
            print '  Queries matched : ' + str(num_matched)
    
    if verbose:
        print ''
        print 'Matching time : %.3f s' % (time.time() - time_match_start)
        print ''

    ### /\ Matching /\ ###



    out.close()

    if verbose:
        print 'Total run time : %.3f s' % (time.time() - time_start)
    

# make sure to manually edit file so that it ends on a proper line.
def get_small_query_file(file, n):
    in_file = open('query.fna','r')
    out = open('query2.fna','w')
    i = 0
    for line in in_file:
        i+=1
        if (i >= n):
            break
        out.write(line)
    in_file.close()
    out.close()

