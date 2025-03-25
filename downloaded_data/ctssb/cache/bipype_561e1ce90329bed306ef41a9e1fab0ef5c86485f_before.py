#!/usr/bin/python
import sqlite3

from glob import glob
from multiprocessing import Process
import cPickle
from os.path import exists as pexists
from os import system
from collections import Counter
#from time import time
from settings_bipype import *

def dicto_reduce(present, oversized):
    """Removes all elements from dictionaries, which keys aren't present
    in both.

    Args:
        present:                Dictionary
        oversized:              Dictionary

    Results:p
        oversized, present      Dictionaries

    ATTENTION: Order of parametres is opposite to results.

    Example:
        >>> dict_1={'a':1,'c':3,'d':4}
        >>> dict_2={'a':3,'b':4,'c':4}
        >>> dicto_reduce(dict_1, dict_2)
        ({'a': 3, 'c': 4}, {'a': 1, 'c': 3})
        >>>
    """
    surplus = set(oversized.keys()) - set(present.keys())
    for gid in surplus:
        del oversized[gid]
    unaccounted = set(present.keys()) - set(oversized.keys())
    for gid in unaccounted:
        del present[gid]
    return oversized, present


def connect_db(db):
    """Connects database

    Arg:
        db:     Path to SQL database

    Returns:
        Cursor object to database
    """
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.text_factory = str
    return conn.cursor()


def get_tables(database):
    """Prints all tables included in SQLite3 database.

    Arg:
        database: Cursor object to SQLite3 database.
    """
    database.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = database.fetchall()
    for row in tables:
        print(row[0])


def auto_tax_read(db_loc):
    """Reads pickled {KEGG GENES number : set[KO identifiers]} dict."""
    with open(db_loc, 'rb') as file_:
        dictionary = cPickle.load(file_)
        file_.close()
    return dictionary


def pickle_or_db(pickle, db): # Please, check if identifiers are correct.
    """Reads pickle or SQL database, than makes a dict.

    If appropriate pickle (a dict) is available, it is read.
    In the other case function reads 'kogenes' table from
    SQL database and makes missing pickle. Eventually returns dict.


    Args:
        pickle: Path to pickled dict in following format:
                {KEGG GENES identifier : set[KO identifiers]}

        db:     Cursor object to SQL database with 'kogenes' table
                (KO identifier          KEGG GENES identifier)
    Returns:
        Dict in {KEGG GENES identifier : set[KO identifiers]} format.


    Some information for Bipype's developers
    (delete this before final version):
    Code from this fuction was not a fuction in previous version and
    'args' was hardcoded to:
                    'kogenes.pckl' & c (variable with db's cursor)
    """
    multi_id = {}
    if pexists(pickle):
        multi_id = auto_tax_read(pickle)
        kogenes_time = time()
        print('kogenes reading time', start_time-kogenes_time)
    else: # change this to fetchall in server version
        db.execute("select * from KoGenes")
        KoPath_gid_all = c.fetchall()
        for koid, gid in KoPath_gid_all:
        if gid not in multi_id:
            multi_id[gid] = set([koid])
        else:
            multi_id[gid].add(koid)
        with open(pickle, 'w') as output:
            cPickle.dump(multi_id, output)
    return multi_id

def get_pathways(database):
    """Make dictionary from pathways table from SQLite3 database.

    Arg:
        database: Cursor object to SQLite3 database.

    Returns:
        Dictionary in following format:
                {PID:Name}
            For example:
                {   'ko04060':'Cytokine-cytokine receptor interaction',
                    'ko00910':'Nitrogen metabolism'    }
    """
    database.execute("select * from Pathways")
    paths = database.fetchall()
    pathways = {}
    for path in paths:
        pathways[path[0]] = path[1]
    return pathways


def get_kopathways(database):
    """Makes dictionaries from kopathways table from SQLite3 database.

    Arg:
        database: Cursor object to SQLite3 database.

    Returns:
        Two dictionaries:
            {KO identifier:PID}
            For example:
                {   'K01194':'ko00500',
                    'K04501':'ko04390'    }
            &
            {PID:set[KO identifiers]}
            For example:
                {ko12345:set([K12345, K12346,...]),...}
    """
    database.execute("select * from KoPathways")
    kopaths = database.fetchall()
    kopathways = {}
    kopath_path = {}
    for kopath in kopaths:
        kopathways[kopath[0]] = kopath[1]
        try:
            kopath_path[kopath[1]].add(kopath[0])
        except KeyError:
            kopath_path[kopath[1]] = set([kopath[0]])
    return kopathways, kopath_path


def m8_to_ko(file_, multi_id): #
                               # Please, check computational complexity:
                               # file -> [] -> Counter(dict) vs. file -> Counter
                               #
    """Assigns and counts KEGG GENES identifiers from BLAST Tabular
    (flag: -m 8) output format file, for every KO from multi_id.

    After mapping, writes data to output file.

    Args:
        file_:    Path to BLAST Tabular (flag: -m 8) format file
        multi_id: Dict {KEGG GENES identifier : set[KO identifiers]}

    Output file (outname) has following path:
        outname = file_.replace('txt.m8', 'out')
        outname = outname.replace('Sample_GB_RNA_stress_', '')
    & following format:
        K00161  2
        K00627  0
        K00382  11
    """
    #print('working on %s'%(file_))
    tmp_ko_dict = {}
    outname = file_.replace('txt.m8', 'out')
    outname = outname.replace('Sample_GB_RNA_stress_', '')
    content = open(file_, 'r')
    hit_gid = [] # List of KEGG GENES identifiers from file_
    for line in content:
        gid = line.split('\t')[1]
        hit_gid.append(gid)
    #file_reading_time = time()
    #print(file_, 'file_reading seconds', kogenes_time-file_reading_time, 'total time', start_time-file_reading_time)
    gid_count = Counter(hit_gid)
    multi_clean, gid_clean = dicto_reduce(gid_count, multi_id)
    #cleaning_time = time()
    #print(file_, 'cleaning time seconds', file_reading_time-cleaning_time, 'total time', start_time-cleaning_time)
    for gid in gid_clean:
        for ko in multi_clean[gid]:
            try:
                tmp_ko_dict[ko] += gid_clean[gid]
            except KeyError:
                tmp_ko_dict[ko] = gid_clean[gid]
    #comparison_time = time()
    #print(file_, 'comparing time seconds', cleaning_time-comparison_time, 'total time', start_time-comparison_time)
    with open(outname, 'w') as out_file:
        for ko in tmp_ko_dict:
            to_print = '%s\t%i\n'%(ko, tmp_ko_dict[ko])
            out_file.write(to_print)
    #writing_time = time()c
    #print(file_, 'comparing time seconds', comparison_time-writing_time, 'total time', start_time-writing_time)


def run_ko_map():
    """Runs m8_to_ko() for every .m8 file in raw directory.

    GLOBALS:
        - path to KO database:                                  PATH_KO_DB
        - pickle to dict from KO GENES table from KO database:  PATH_KO_PCKL
    """
    m8_list = glob('meta/m8/*m8')
    data = pickle_or_db(PATH_KO_PCKL, connect_db(PATH_KO_DB))
    for file_ in m8_list:
        p=Process(target=m8_to_ko,args=(file_,data))
        p.start()


def out_content(filelist, kopath_count, path_names, method='DESeq2'):
    """For every item in 'kopath_count' dictionary and for every file
    in 'filelist', writes to output file line with KOs, which are common
    for item.value and the set of KOs obtained from file.

    Args:
        filelist:      List of paths to tab-delimited .txt files, where
                       first column is a KO identifier.

        kopath_count:  Dictionary in {PID:set[KO identifiers]} format.
                       For example:
                            {ko12345:set([K12345, K12346,...]),...}

        path_names:    Dictionary in {PID:Name} format.
                       For example:
                   {'ko04060':'Cytokine-cytokine receptor interaction',c
                    'ko00910':'Nitrogen metabolism'}

        method:        Argument used only as a part of output file name
                       (default: 'DESeq2')

    Output file has following name:
            (method+'_'+filename.replace('txt', 'path_counts.csv'))
        where:
            filename = filepath.split('\\')[-1], if '\\' in filepath.
            filename = filepath.split('/')[-1],  if '/' in filepath.
            filename = filepath,                 in other cases.

    & following headline (format):
        ko_path_id;ko_path_name;percent common;common KOs

    Writes only lines with non-zero common KOs.
    """
    for filepath in filelist:
        if '\\' in filepath:
            filename = filepath.split('\\')[-1]
        elif '/' in filepath:
            filename = filepath.split('/')[-1]
        else:
            filename = filepath
        outname = method+'_'+filename.replace('txt', 'path_counts.csv')
        Kids = set()
        with open(filepath, 'r') as file_:
            filecontent = file_.readlines()[1:]
            for line in filecontent:
                Kid = line.rstrip().split('\t')[0]
                Kids.add(Kid)
        with open('meta/'+outname, 'w') as outfile:
            outfile.write('ko_path_id;ko_path_name;percent common;common KOs\n')
            for path, Kset in kopath_count.items():
                common = Kids&Kset
                if len(common) > 0:
                    percent_ko = str(int(len(common)*100.0/len(Kset)))
                    print_ko = ' '.join(common)
                    path_name_comma = path_names[path]
                    path_name = path_name_comma.replace(',', ' _')
                    outline = ';'.join([path, path_name, percent_ko, print_ko])+'\n'
                    outfile.write(outline)


def run_ko_remap():
    """Runs out_content() for files from 'edger_paths' & 'deseq_paths'.
    Uses db for making 'path_names' & 'kopath_count' out_content() args

    Arg:
        db: Path to SQLite3 database.

    HARDCODED: Paths to files:
                    edger: 'meta/tables_edgeR/*[pn].txt'
                    deseq: 'meta/tables_DESeq2/*[pn].txt'
    GLOBALS:
        - path to KO database:  PATH_KO_DB
    """
    cursor = connect_db(PATH_KO_DB)
    path_names = get_pathways(cursor)
    kopath_keys, kopath_count = get_kopathways(cursor)
    edger_files = glob('meta/tables_edgeR/*[pn].txt')
    deseq_files = glob('meta/tables_edgeR/*[pn].txt')
    out_content(deseq_files, kopath_count, path_names)
    out_content(edger_files, kopath_count, path_names, 'edgeR')


def SARTools():
    system('Rscript meta/template_script_DESeq2.r')
    system('mv meta/tables/* meta/tables_DESeq2')
    system('Rscript meta/template_script_edgeR.r')
    system('mv meta/tables/* meta/tables_edgeR')

def ko_map_remap(opts):
    """Performs analyse of metagenomic data.

    For more information please refer to
    run_ko_map(), SARTools() & run_ko_remap()
    """
    run_ko_map()
    SARTools()
    run_ko_remap()

