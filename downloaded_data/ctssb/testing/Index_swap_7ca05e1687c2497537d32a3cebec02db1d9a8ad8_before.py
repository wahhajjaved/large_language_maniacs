#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Feb  6 10:29:13 2018

@author: m006703
"""

'''
Script to parse out VCF files annotated with BioR
will pull out SNPs with gnomAD frequency less than a set value which can be altered below
'''

import gzip
import os
import argparse
import sys

def main():
    inputFile, outPath, sampleName = ParseArgs()
    outFile = ParseVcf(inputFile, outPath, sampleName)
    
    print("Script is done running")

def ParseArgs():
    parser = argparse.ArgumentParser(description="Help Message")
    parser.add_argument("-i", dest="inputFile", required=True, help="Input VCF file")
    parser.add_argument("-o", dest="outPath", required=True, help="Ouput File")
    parser.add_argument("-n", dest="sampleName", require=True, help="Name of the sample")
    args = parser.parse_args()
    
    inputFile = os.path.abspath(args.inputFile)
    outPath = os.path.abspath(args.outPath)
    sampleName = args.sampleName
    
    # Add / at the end if it is not included in the output path
    if outPath.endswith("/"):
        outPath = outPath
    else:
        outPath = outPath + "/"
        
    return(inputFile, outPath, sampleName)
    
def ParseVcf(inputFile, outPath, sampleName):

    # open files
    vcfFile = gzip.open(inputFile, 'rb')
    #vcfFile = open(inputFile, 'r')
    
    # Go to the header line
    for line in vcfFile:
        if line.startswith('#CHROM'):
            #firstline = line.split('\t')
            #sampleName = firstline[9].rstrip()
            break
        
    fileName = outPath + sampleName + '_gnomAD.vcf'
    
    # Terminate script if the file already exists
    if os.path.isfile(fileName) == True:
        print("The file " + fileName + " already exists. Please delete the file and try again")
        print("Terminating script")
        sys.exit()
    else:
            
        outFile = open(outPath + sampleName + '_gnomAD.vcf', 'w')
        #outFile = open('/Users/m006703/Index_Swap/files/gnomAD.vcf', 'w')       
        # Start collecting data after the header line           
        chrom = []
        pos = []
        snpid = []
        ref = []
        alt = []
        qual = []
        qualfilter = []
        info = []
        resultformat = []
        resultmatrix = []
        coveragelist = []
        
        # Collect data that only has value for non-population specific gnomAD frequency
        for line in vcfFile:
            result = line.split('\t')
            infoline = result[7]
            if 'gnomAD_r201_GRCh37.INFO.AF=' in infoline:
                splitinfoline = infoline.split(';')
                for item in splitinfoline:
                    if item.startswith('gnomAD_r201_GRCh37.INFO.AF='):
                        gnomADInfo = float(item.split('=')[1])
                        if 0 < gnomADInfo <= 0.05: # Cutoff for gnomAD variant frequency
                            formatlist = result[8].split(':')
                            formatresult = result[9].rstrip().split(':')
                            coverage = formatresult[formatlist.index('DP')]
                            if result[1] not in pos:
                                chrom.append(result[0])
                                pos.append(result[1])
                                snpid.append(result[2])
                                ref.append(result[3])
                                alt.append(result[4])
                                qual.append(result[5])
                                qualfilter.append(result[6])
                                info.append(gnomADInfo)
                                resultformat.append(result[8])
                                resultmatrix.append(result[9].rstrip())
                                coveragelist.append(coverage)
                           
        outFile.write('CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tgnomADINFO\tFORMAT\t\tCOVERAGE\n')
        
        for index in range(len(chrom)):
            resultList = []
            resultList = [chrom[index], pos[index], snpid[index], ref[index], alt[index], qual[index], qualfilter[index], str(info[index]), resultformat[index], resultmatrix[index], coveragelist[index]]
            outFile.write('\t'.join(resultList) + '\n')
        
        vcfFile.close()
        outFile.close()
        
        return (outFile)

if __name__ == '__main__':
    main()
