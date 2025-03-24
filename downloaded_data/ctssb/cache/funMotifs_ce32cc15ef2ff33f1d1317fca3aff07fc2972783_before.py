'''
Created on 21 Oct 2017

@author: husensofteng
'''
import sys, os
import multiprocessing as mp
import psycopg2
from psycopg2.extras import DictCursor
import time

params = {'-sep': '\t', 
          '-cols_to_retrieve':'chr, motifstart, motifend, strand, name, score, pval, fscore, chromhmm, contactingdomain, dnase__seq, fantom, loopdomain, numothertfbinding, othertfbinding, replidomain, tfbinding, tfexpr', '-number_rows_select':'all',
          '-restart_conn_after_n_queries':10000, '-variants':True, '-regions':True,
          '-chr':0, '-start':1, '-end':2, '-ref':3, '-alt':4, 
          '-db_name':'regmotifsdbtest', '-db_host':'localhost', '-db_port':5432, '-db_user':'huum', '-db_password':'',
          '-all_motifs':True, '-motifs_tfbining':False, '-max_score_motif':False, '-motifs_tfbinding_otherwise_max_score_motif':False,
          '-verbose': True, '-run_parallel': True, '-num_cores':8}
    
def get_params(params_list, params_without_value):
    global params
    for i, arg in enumerate(params_list):#priority is for the command line
        if arg.startswith('-'): 
            if arg in params_without_value:
                params[arg] = True
            else:
                try:
                    v = params_list[i+1]
                    if v.lower()=='yes' or v.lower()=='true':
                        v=True
                    elif v.lower()=='no' or v.lower()=='false':
                        v=False
                    params[arg] =  v
                except IndexError:
                    print "no value is given for parameter: ", arg 
    return params

def open_connection():
    conn = psycopg2.connect("dbname={} user={} password={} host={} port={}".format(params['-db_name'], params['-db_user'], params['-db_password'], params['-db_host'], params['-db_port']))
    return conn

    
def get_col_names_from_table(table_name, conn):
    curs = conn.cursor()
    curs.execute("select * FROM {} limit 1".format(table_name))
    return [desc[0] for desc in curs.description]

def get_limit_smt():
    limit_number_rows_select_stmt = ""
    if params['-number_rows_select']!="all":
        if int(params['-number_rows_select'])>0:
            limit_number_rows_select_stmt = ' limit {}'.format(str(params['-number_rows_select']))
    return limit_number_rows_select_stmt


def run_query(cols_to_retrieve, from_tabes, cond_statement, order_by_stmt, conn, n):
    curs = conn.cursor(name = "countcurs"+n, cursor_factory=DictCursor)
    stmt = 'select {} from {}{}{} {}'.format(cols_to_retrieve, from_tabes, cond_statement, order_by_stmt, get_limit_smt())
    curs.execute(stmt)
    if curs is not None:
        return curs.fetchall()
        curs.close()
    else:
        curs.close()
        return []

def run_query_nocursorname(cols_to_retrieve, from_tabes, cond_statement, curs):
    #curs = conn.cursor()
    stmt = 'select {} from {}{} {}'.format(cols_to_retrieve, from_tabes, cond_statement, get_limit_smt())
    curs.execute(stmt)
    if curs is not None:
        return curs.fetchall()
        #curs.close()
    else:
        #curs.close()
        return []
    
def read_infile(input_file):
    conn = open_connection()
    curs_for_pfms = conn.cursor()
    number_lines_processed = 0
    t = time.time()
    with open(input_file, 'r') as infile, open(input_file++'_'+params['-tissue']+'_annotated.tsv', 'w') as outfile:
        line = infile.readline()
        cols_from_file = ['cols'+str(i) for i in range(0,len(line.strip().split(params['-sep'])))]
        cols_from_file.extend((params['-cols_to_retrieve'] + ',mutposition,entropy').split(','))
        outfile.write(params['-sep'].join(cols_from_file) + '\n')
        
        while line:
            sline = line.strip().split(params['-sep'])
            if (line.startswith('#') or line.startswith('//') or len(sline)<3):
                line = infile.readline()
                continue
            if params['-variants']:#the input is variant
                try:
                    if ( #check if the number of ref/alt alleles match the variant length
                        (
                            (int(float(sline[params['-end']])) - int(float(sline[params['-start']])) + 1 != len(sline[params['-ref']]) or 
                             int(float(sline[params['-end']])) - int(float(sline[params['-start']])) + 1 != len(sline[params['-alt']])
                            ) and 
                         sline[params['-ref']]!='-' and sline[params['-alt']]!='-' and
                         sline[params['-ref']]!='deletion' and sline[params['-alt']]!='insertion' and
                         sline[params['-ref']]!='del' and sline[params['-alt']]!='ins'
                         )):#skip mis appropriate lines
                            if params['-verbose']:
                                print 'Warning -- skipped line: the variant length does not match the ref/alt length', line
                            line = infile.readline()
                            continue
                except IndexError:
                    if params['-verbose']:
                        print 'Warning -- line is not a variant (fewer than 5 columns (chr,start,end,ref,alt) detected): ', line
                    params['-variants'] = False
                    
            updated_chr = sline[params['-chr']].replace('X', '23').replace('Y', '24').replace('MT','25').replace('M','25')
            chr_table = updated_chr+'motifs'
            if not updated_chr.startswith('chr'):
                chr_table = 'chr'+updated_chr+'motifs'
            cond_statement = (" where (posrange && int4range({start},{end},'[]')) and ({tissue_table}.mid={motif_table}.mid and {tissue_table}.tfexpr>0.0)".format(
                start=int(float(sline[params['-start']])), 
                end=int(float(sline[params['-end']])), 
                tissue_table=params['-tissue'], 
                motif_table=chr_table))
            #if params['-variants'] then also retreive the affinity change directly from the query (need for if and else in postgres)
            mutation_position_stmt = ''
            order_by_stmt = ' order by fscore '
            if params['-variants']:
                mutation_position_stmt = ", (CASE WHEN (UPPER(posrange * int4range({start}, {end})) - LOWER(posrange * int4range({start}, {end}))>1) THEN 100 ELSE (CASE when STRAND='-' THEN (motifend-{start})+1 ELSE ({start}-motifstart)+1 END) END) as mutposition ".format(start=int(float(sline[params['-start']])), end=int(float(sline[params['-end']])))
            rows = run_query(params['-cols_to_retrieve']+mutation_position_stmt, params['-tissue']+',' + chr_table, cond_statement, order_by_stmt, conn, str(number_lines_processed))
            #for each row get the entropy
            motifs_with_tfbinding = []
            all_motifs = []
            for row in rows:
                entropy = 0.0
                if (row['mutposition']==100 or
                    sline[params['-ref']]=='-' or sline[params['-ref']]=='deletion' or sline[params['-ref']]=='del' or
                    sline[params['-alt']]=='-'  or sline[params['-alt']]=='insertion' or sline[params['-alt']]=='ins'
                             ):
                    entropy=1
                else:
                    rows_pfms = run_query_nocursorname(cols_to_retrieve="(select freq from motifs_pfm where position={mutposition} and name = '{motif_name}' and allele='{ref_allele}') - (select freq from motifs_pfm where position={mutposition} and name = '{motif_name}' and allele='{alt_allele}')".format(
                        mutposition=row['mutposition'], motif_name=row['name'], ref_allele=sline[params['-ref']], alt_allele=sline[params['-alt']]), 
                                           from_tabes='motifs_pfm', cond_statement=" where position={mutposition} and name='{motif_name}' and allele='{ref_allele}'".format(
                                               mutposition=row['mutposition'], motif_name=row['name'], ref_allele=sline[params['-ref']]), curs=curs_for_pfms)
                    try:
                        entropy = float(rows_pfms[0][0])
                    except TypeError:
                        entropy = 'NA'
                        if params['-verbose']:
                            print 'Warning: ref/alt allele are not correctly given in: ' +  line
                        pass
                if row['numothertfbinding']<=0.0:
                    row['othertfbinding'] = "None"
                
                lrow=list(row)
                lrow.append(entropy)
                if params['-all_motifs']:
                    outfile.write(line.strip() + params['-sep'] + params['-sep'].join(str(x) for x in lrow) + '\n')
                else:
                    if float(row['tfbinding'])>0.0:
                        motifs_with_tfbinding.append(lrow)
                all_motifs.append(lrow)
            if not params['-all_motifs']:
                if params['-motifs_tfbining']:#only report motifs that have tfbinding
                    for motif_tfbinding in motifs_with_tfbinding:
                        outfile.write(line.strip() + params['-sep'] + params['-sep'].join(str(x) for x in motif_tfbinding) + '\n')
                elif params['-max_score_motif']:#don't care about tfbinding just give the motif with the maximum score
                    try:
                        max_motif = all_motifs[0]
                        outfile.write(line.strip() + params['-sep'] + params['-sep'].join(str(x) for x in max_motif) + '\n')
                    except IndexError:
                        pass
                elif params['-motifs_tfbinding_otherwise_max_score_motif']:#if there is any motif with tfbinding return it otherwise return the motif that has the maximum score
                    if len(motifs_with_tfbinding)>0:
                        for motif_tfbinding in motifs_with_tfbinding:
                            outfile.write(line.strip() + params['-sep'] + params['-sep'].join(str(x) for x in motif_tfbinding) + '\n')
                    else:
                        try:
                            max_motif = all_motifs[0]
                            outfile.write(line.strip() + params['-sep'] + params['-sep'].join(str(x) for x in max_motif) + '\n')
                        except IndexError:
                            pass
            line = infile.readline()
            
            number_lines_processed+=1
            if number_lines_processed % int(params['-restart_conn_after_n_queries']) == 0:
                print '{} Lines are processed from {}'.format(number_lines_processed, input_file)
                print time.time()-t
                t = time.time()
                conn.close()
                curs_for_pfms.close()
                conn = open_connection()
                curs_for_pfms = conn.cursor()
    return number_lines_processed    

def run_regDriver(user_args):
    if len(user_args)<=0:
        print "Usage: python regDriver.py -f input_file -tissue tissue_name [options]"
        sys.exit(0)
    get_params(user_args, params_without_value=[])
    print params['-tissue']
    if '-f' in params.keys():
        read_infile(params['-f'])
    elif '-dir' in params.keys():
        if params['-run_parallel']:
            p = mp.Pool(int(params['-num_cores']))
        for f in os.listdir(params['-dir']):
            f_path = params['-dir'].strip()+'/'+f
            if f.endswith('_annotated.tsv') or os.path.isdir(f_path):
                continue
            print f_path
            if params['-run_parallel']:
                p.apply_async(read_infile, args= (f_path,))
            else:
                read_infile(f_path)
        if ['-run_parallel']:
            p.close()
            p.join()
        
if __name__ == '__main__':
    
    try:
        run_regDriver(sys.argv[1:])
    except KeyError:
        print "No value was found for one or more of the arguments:\n", params
        print "Usage: python regDriver.py -f file_name -tissue tissue_name"
