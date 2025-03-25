#!/usr/bin/env python

import sys
import os
import argparse
from Bio import SeqIO
from Bio.Alphabet import generic_dna
import subprocess


def check_if_list_or_folder(folder_or_list):
    list_files = []
    # check if given a list of genomes paths or a folder to create schema
    try:
        f = open(folder_or_list, 'r')
        f.close()
        list_files = folder_or_list
    except IOError:

        for gene in os.listdir(folder_or_list):
            try:
                genepath = os.path.join(folder_or_list, gene)
                for allele in SeqIO.parse(genepath, "fasta", generic_dna):
                    break
                list_files.append(os.path.abspath(genepath))
            except Exception as e:
                print e
                pass

    return list_files


def create_schema():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py CreateSchema [CreateSchema ...] [-h] -i [I] -o [O] --cpu [CPU] [-b [B]] [--bsr [BSR]] [-t [T]] [-v] [-l [L]]'''
	
    parser = argparse.ArgumentParser(description="This program creates a schema when provided the genomes",usage=msg())
    parser.add_argument('CreateSchema', nargs='+', help='create a schema')
    parser.add_argument('-i', nargs='?', type=str, help='List of genome files (list of fasta files)', required=True)
    parser.add_argument('-o', nargs='?', type=str, help="Name of the output files", required=True)
    parser.add_argument('--cpu', nargs='?', type=int, help="Number of cpus, if over the maximum uses maximum -2",
                        required=True)
    parser.add_argument('-b', nargs='?', type=str, help="BLAST full path", required=False, default='blastp')
    parser.add_argument('--bsr', nargs='?', type=float, help="minimum BSR similarity", required=False, default=0.6)
    parser.add_argument('-t', nargs='?', type=str, help="taxon", required=False, default=False)
    parser.add_argument("-v", "--verbose", help="increase output verbosity", dest='verbose', action="store_true",
                        default=False)
    parser.add_argument('-l', nargs='?', type=int, help="minimum bp locus lenght", required=False, default=200)

    args = parser.parse_args()

    genomeFiles = args.i
    cpuToUse = str(args.cpu)
    outputFile = args.o
    BlastpPath = args.b
    bsr = str(args.bsr)
    chosenTaxon = args.t
    verbose = args.verbose
    min_length = str(args.l)

    genomeFiles = check_if_list_or_folder(genomeFiles)
    if isinstance(genomeFiles, list):
        with open("listGenomes2Call.txt", "wb") as f:
            for genome in genomeFiles:
                f.write(genome + "\n")
        genomeFiles = "listGenomes2Call.txt"

    ppanScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'createschema/PPanGen.py')

    args = [ppanScriptPath, '-i', genomeFiles, '--cpu', cpuToUse, "-o", outputFile,
            "--bsr", bsr, "-b", BlastpPath,"-l", min_length]

    if verbose:
        args.append('-v')
    if chosenTaxon:
		args.append('-t')
		args.append(chosenTaxon)

    proc = subprocess.Popen(args)

    proc.wait()
    
    try:
        os.remove("listGenomes2Call.txt")
    except:
	    pass
		

def allele_call():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py AlleleCall [AlleleCall ...][-h] -i [I] -g [G] -o [O] --cpu [CPU] [-v] [-b [B]][--bsr [BSR]] [-t [T]] [--fc] [--fr] [--json]
			'''
	
    parser = argparse.ArgumentParser(description="This program call alleles for a set of genomes when provided a schema",usage=msg())
    parser.add_argument('AlleleCall', nargs='+', help='do allele call')
    parser.add_argument('-i', nargs='?', type=str, help='List of genome files (list of fasta files)', required=True)
    parser.add_argument('-g', nargs='?', type=str, help='List of genes (fasta)', required=True)
    parser.add_argument('-o', nargs='?', type=str, help="Name of the output files", required=True)
    parser.add_argument('--cpu', nargs='?', type=str, help="Number of cpus, if over the maximum uses maximum -2",
                        required=True)
    parser.add_argument("--contained", help=argparse.SUPPRESS, required=False, action="store_true", default=False)
    parser.add_argument("-v", "--verbose", help="increase output verbosity", dest='verbose', action="store_true",
                        default=False)
    parser.add_argument('-b', nargs='?', type=str, help="BLAST full path", required=False, default='blastp')
    parser.add_argument('--bsr', nargs='?', type=str, help="minimum BSR score", required=False, default='0.6')
    parser.add_argument('-t', nargs='?', type=str, help="taxon", required=False, default=False)
    parser.add_argument("--fc", help="force continue", required=False, action="store_true", default=False)
    parser.add_argument("--fr", help="force reset", required=False, action="store_true", default=False)
    parser.add_argument("--json", help="report in json file", required=False, action="store_true", default=False)

    args = parser.parse_args()

    genomeFiles = args.i
    genes = args.g
    cpuToUse = args.cpu
    BSRTresh = args.bsr
    verbose = args.verbose
    BlastpPath = args.b
    gOutFile = args.o
    chosenTaxon = args.t
    forceContinue = args.fc
    forceReset = args.fr
    contained = args.contained
    jsonReport = args.json
    

    genes2call = check_if_list_or_folder(genes)

    if isinstance(genes2call, list):
        with open("listGenes2Call.txt", "wb") as f:
            for genome in genes2call:
                f.write(genome + "\n")
        genes2call = "listGenes2Call.txt"

    genomes2call = check_if_list_or_folder(genomeFiles)

    if isinstance(genomes2call, list):
        with open("listGenomes2Call.txt", "wb") as f:
            for genome in genomes2call:
                f.write(genome + "\n")
        genomes2call = "listGenomes2Call.txt"

    ScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'allelecall/BBACA.py')
    args = [ScriptPath, '-i', genomes2call, '-g', genes2call, '--cpu', cpuToUse,
            "-o", gOutFile, "--bsr", BSRTresh,
            '-b', BlastpPath]
    if forceContinue:
        args.append('--fc')
    if jsonReport:
        args.append('--json')
    if verbose:
        args.append('-v')
    if forceReset:
        args.append('--fr')
    if contained:
        args.append('--contained')

    if chosenTaxon:
		args.append('-t')
		args.append(chosenTaxon)
		
    proc = subprocess.Popen(args)
    proc.wait()
	
    try:
        os.remove("listGenes2Call.txt")
    except:
	    pass
    try:
        os.remove("listGenomes2Call.txt")
    except:
	    pass

def evaluate_schema():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py SchemaEvaluator [SchemaEvaluator ...] [-h] -i [I] [-p] [--log] -l [L] -ta [TA] [-t [T]] [--title [TITLE]] --cpu [CPU] [-s [S]] [--light]
			'''
	
    parser = argparse.ArgumentParser(
        description="This program analyses a set of gene files, analyzing the alleles CDS and the length of the alleles per gene",usage=msg())
    parser.add_argument('SchemaEvaluator', nargs='+', help='evaluation of a schema')
    parser.add_argument('-i', nargs='?', type=str, help='list genes, directory or .txt file with the full path',
                        required=True)
    parser.add_argument('-p', dest='conserved', action='store_true', help='One bad allele still makes gene conserved',
                        required=False,
                        default=False)
    parser.add_argument('--log', dest='logScale', action='store_true', default=False)
    parser.add_argument('-l', nargs='?', type=str, help='name/location main html file', required=True)
    parser.add_argument('-ta', nargs='?', type=int, help='ncbi translation table', required=True)
    parser.add_argument('-t', nargs='?', type=float, help='Threshold', required=False, default=0.05)
    parser.add_argument('--title', nargs='?', type=str, help='title on the html', required=False,
                        default="My Analyzed wg/cg MLST Schema - Rate My Schema")
    parser.add_argument('--cpu', nargs='?', type=int, help='number of cpu to use', required=True)
    parser.add_argument('-s', nargs='?', type=int,
                        help='number of boxplots per page (more than 500 can make the page very slow)', required=False,
                        default=500)
    parser.add_argument('--light', help="skip clustal and mafft run", required=False, action="store_true", default=False)
    
    args = parser.parse_args()
    genes = args.i
    transTable = str(args.ta)
    logScale = args.logScale
    htmlFile = args.l
    outputpath = htmlFile
    cpuToUse = args.cpu
    threshold = str(args.t)
    OneBadGeneNotConserved = args.conserved
    splited = str(args.s)
    light = args.light
    title = str(args.title)

    ScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SchemaEvaluator/ValidateSchema.py')
    args = [ScriptPath, '-i', genes, '--cpu', str(cpuToUse), "-l", outputpath,
            '-ta', transTable, '-t', threshold,
            '-s', splited, '--title', title]
    if logScale:
        args.append('--log')
    if OneBadGeneNotConserved:
        args.append('-p')
    if light:
        args.append('--light')

    proc = subprocess.Popen(args)
    proc.wait()


def test_schema():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py TestGenomeQuality [TestGenomeQuality ...] [-h] -i [I] -n [N] -t [T] -s [S] [-o [O]] [-v]
                    '''
	
    parser = argparse.ArgumentParser(
        description="This program analyze an allele call raw output matrix, returning info on which genomes are responsible for cgMLST loci loss",usage=msg())
    parser.add_argument('TestGenomeQuality', nargs='+', help='test the quality of the genomes on the allele call')
    parser.add_argument('-i', nargs='?', type=str, help='raw allele call matrix file', required=True)
    parser.add_argument('-n', nargs='?', type=int, help='maximum number of iterations', required=True)
    parser.add_argument('-t', nargs='?', type=int, help='maximum threshold of bad calls above 95 percent',
                        required=True)
    parser.add_argument('-s', nargs='?', type=int, help='step between each threshold analysis', required=True)
    parser.add_argument('-o', nargs='?', type=str, help="Folder for the analysis files", required=False, default=".")
    parser.add_argument("-v", "--verbose", help="increase output verbosity", dest='verbose', action="store_true",
                        default=False)

    args = parser.parse_args()

    pathOutputfile = args.i
    iterationNumber = str(args.n)
    thresholdBadCalls = str(args.t)
    step = str(args.s)
    out_folder = args.o
    verbose = args.verbose

    ScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils/TestGenomeQuality.py')
    args = [ScriptPath, '-i', pathOutputfile, '-n', iterationNumber, '-t',
            thresholdBadCalls, '-s', step, '-o', out_folder]
    if verbose:
        args.append('-v')

    proc = subprocess.Popen(args)
    proc.wait()


def extract_cgmlst():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py ExtractCgMLST [ExtractCgMLST ...] [-h] -i [I] -o [O] [-r [R]] [-g [G]]
                    '''
	
    parser = argparse.ArgumentParser(description="This program cleans an output file for phyloviz",usage=msg())
    parser.add_argument('ExtractCgMLST', nargs='+', help='clean chewBBACA output')
    parser.add_argument('-i', nargs='?', type=str, help='input file to clean', required=True)
    parser.add_argument('-o', nargs='?', type=str, help='output folder', required=True)
    parser.add_argument('-r', nargs='?', type=str, help='listgenes to remove', required=False, default=False)
    parser.add_argument('-g', nargs='?', type=str, help='listgenomes to remove', required=False, default=False)
    parser.add_argument('-p', nargs='?', type=float, help='maximum presence (e.g 0.95)', required=False, default=1)

    args = parser.parse_args()

    pathOutputfile = args.i
    newfile = args.o
    genes2remove = args.r
    genomes2remove = args.g
    cgMLSTpercent=str(args.p)

    ScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils/Extract_cgAlleles.py')
    args = [ScriptPath, '-i', pathOutputfile, '-o', newfile,'-p', cgMLSTpercent]

    if genes2remove:
        args.append('-r')
        args.append(genes2remove)
    if genomes2remove:
        args.append('-g')
        args.append(genomes2remove)

    proc = subprocess.Popen(args)
    proc.wait()

def remove_genes():
	
    def msg(name=None):                                                            
        return ''' chewBBACA.py RemoveGenes [RemoveGenes ...][-h] -i [I] -g [G] -o [O] [--inverse]
                    '''
	
    parser = argparse.ArgumentParser(description="This program removes gens from a tab separated allele profile file",usage=msg())
    parser.add_argument('RemoveGenes', nargs='+', help='remove loci from a chewBBACA profile')
    parser.add_argument('-i', nargs='?', type=str, help='main matrix file from which to remove', required=True)
    parser.add_argument('-g', nargs='?', type=str, help='list of genes to remove', required=True)
    parser.add_argument('-o', nargs='?', type=str, help='output file name', required=True)
    parser.add_argument("--inverse", help="list to remove is actually the one to keep", dest='inverse',
                        action="store_true", default=False)

    args = parser.parse_args()

    args = parser.parse_args()
    mainListFile = args.i
    toRemoveListFile = args.g
    outputfileName = args.o
    inverse = args.inverse
    

    ScriptPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'utils/RemoveGenes.py')
    args = [ScriptPath, '-i', mainListFile, '-g', toRemoveListFile, '-o', outputfileName]

    if inverse:
        args.append('--inverse')

    proc = subprocess.Popen(args)
    proc.wait()


if __name__ == "__main__":

	functions_list = ['CreateSchema', 'AlleleCall', 'SchemaEvaluator', 'TestGenomeQuality', 'ExtractCgMLST','RemoveGenes']
	desc_list = ['Create a gene by gene schema based on genomes', 'Perform allele call for target genomes', 'Tool that builds an html output to better navigate/visualize your schema', 'Analyze your allele call output to refine schemas', 'Select a subset of loci without missing data (to be used as PHYLOViZ input)','Remove a provided list of loci from your allele call output']

	try:
		print ("\n")
		if sys.argv[1] == functions_list[0]:
			create_schema()
		elif sys.argv[1] == functions_list[1]:
			allele_call()
		elif sys.argv[1] == functions_list[2]:
			evaluate_schema()
		elif sys.argv[1] == functions_list[3]:
			test_schema()
		elif sys.argv[1] == functions_list[4]:
			extract_cgmlst()
		elif sys.argv[1] == functions_list[5]:
			remove_genes()
		else:
			print('\n\tUSAGE : chewBBACA.py [module] -h \n')
			print('Select one of the following functions :\n')
			i=0
			while i<len(functions_list):
				print functions_list[i] +" : "+desc_list[i]
				i+=1
	except Exception as e:
		#print e
		print('\n\tUSAGE : chewBBACA.py [module] -h \n')
		print('Select one of the following functions :\n')
		i=0
		while i<len(functions_list):
			print functions_list[i] +" : "+desc_list[i]
			i+=1
