#!/usr/bin/env python
"""
Utilities for working with sequence reads, such as converting formats and
fixing mate pairs.
"""
from __future__ import division

__author__ = "irwin@broadinstitute.org"
__version__ = "PLACEHOLDER"
__date__ = "PLACEHOLDER"
__commands__ = []

import argparse, logging, math, os, tempfile, shutil, subprocess
from Bio import SeqIO
import util.cmd, util.file
from util.file import mkstempfname
import tools.picard, tools.samtools, tools.mvicuna

log = logging.getLogger(__name__)


# =======================
# ***  purge_unmated  ***
# =======================

def purge_unmated(inFastq1, inFastq2, outFastq1, outFastq2) :
    """Use mergeShuffledFastqSeqs to purge unmated reads, and put corresponding
       reads in the same order."""
    tempOutput = mkstempfname()
    mergeShuffledFastqSeqsPath = os.path.join(util.file.get_scripts_path(),
                                              'mergeShuffledFastqSeqs.pl')
    # The regular expression that follow says that the sequence identifiers
    # of corresponding sequences must be of the form SEQID/1 and SEQID/2
    cmdline = [mergeShuffledFastqSeqsPath, '-t', '-r', '^@(\S+)/[1|2]$',
              '-f1', inFastq1, '-f2', inFastq2, '-o', tempOutput]
    log.debug(' '.join(cmdline))
    subprocess.check_call(cmdline)
    shutil.move(tempOutput + '.1.fastq', outFastq1)
    shutil.move(tempOutput + '.2.fastq', outFastq2)

def parser_purge_unmated() :
    parser = argparse.ArgumentParser(
        description='''Use mergeShuffledFastqSeqs to purge unmated reads, and
                       put corresponding reads in the same order.
                       Corresponding sequences must have sequence identifiers
                       of the form SEQID/1 and SEQID/2.
                    ''')
    parser.add_argument('inFastq1',
        help='Input fastq file; 1st end of paired-end reads.')
    parser.add_argument('inFastq2',
        help='Input fastq file; 2nd end of paired-end reads.')
    parser.add_argument('outFastq1',
        help='Output fastq file; 1st end of paired-end reads.')
    parser.add_argument('outFastq2',
        help='Output fastq file; 2nd end of paired-end reads.')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser

def main_purge_unmated(args) :
    inFastq1 = args.inFastq1
    inFastq2 = args.inFastq2
    outFastq1 = args.outFastq1
    outFastq2 = args.outFastq2
    purge_unmated(inFastq1, inFastq2, outFastq1, outFastq2)
    return 0

__commands__.append(('purge_unmated', main_purge_unmated,
                     parser_purge_unmated))

# =========================
# ***  fastq_to_fasta   ***
# =========================
def fastq_to_fasta(inFastq, outFasta) :
    'Convert from fastq format to fasta format.'
    'Warning: output reads might be split onto multiple lines.'
    
    # Do this with biopython rather than prinseq, because if the latter fails
    #    it doesn't return an error. (On the other hand, prinseq
    #    can guarantee that output lines are not split...)
    inFile  = util.file.open_or_gzopen(inFastq)
    outFile = util.file.open_or_gzopen(outFasta, 'w')
    for rec in SeqIO.parse(inFile, 'fastq') :
        SeqIO.write([rec], outFile, 'fasta')
    outFile.close()

def parser_fastq_to_fasta() :
    parser = argparse.ArgumentParser(
        description='Convert from fastq format to fasta format.')
    parser.add_argument('inFastq', help='Input fastq file.')
    parser.add_argument('outFasta', help='Output fasta file.')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser

def main_fastq_to_fasta(args) :
    inFastq = args.inFastq
    outFasta = args.outFasta
    fastq_to_fasta(inFastq, outFasta)
    return 0
__commands__.append(('fastq_to_fasta', main_fastq_to_fasta,
                     parser_fastq_to_fasta))

# ===============================
# ***  index_fasta_samtools   ***
# ===============================

def parser_index_fasta_samtools() :
    parser = argparse.ArgumentParser(
        description='''Index a reference genome for Samtools.''')
    parser.add_argument('inFasta', help='Reference genome, FASTA format.')
    parser.add_argument("--overwrite",
        help="If index exists, remove it and regenerate it (default: %(default)s)",
        default=False, action="store_true", dest="overwrite")
    util.cmd.common_args(parser, (('loglevel', None), ('version', None)))
    return parser
def main_index_fasta_samtools(args) :
    tools.samtools.SamtoolsTool().faidx(args.inFasta, overwrite=args.overwrite)
    return 0
__commands__.append(('index_fasta_samtools',
    main_index_fasta_samtools, parser_index_fasta_samtools))

# =============================
# ***  index_fasta_picard   ***
# =============================

def parser_index_fasta_picard() :
    parser = argparse.ArgumentParser(
        description='''Create an index file for a reference genome suitable
                    for Picard/GATK.''')
    parser.add_argument('inFasta', help='Input reference genome, FASTA format.')
    parser.add_argument("--overwrite",
        help="If index exists, remove it and regenerate it (default: %(default)s)",
        default=False, action="store_true", dest="overwrite")
    parser.add_argument('--JVMmemory', default = tools.picard.CreateSequenceDictionaryTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s CreateSequenceDictionary, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_index_fasta_picard(args) :
    tools.picard.CreateSequenceDictionaryTool().execute(
        args.inFasta, overwrite=args.overwrite,
        picardOptions=args.picardOptions, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('index_fasta_picard',
    main_index_fasta_picard, parser_index_fasta_picard))

# =============================
# ***  mkdup_picard   ***
# =============================

def parser_mkdup_picard() :
    parser = argparse.ArgumentParser(
        description='''Mark or remove duplicate reads from BAM file.''')
    parser.add_argument('inBams', help='Input reads, BAM format.', nargs='+')
    parser.add_argument('outBam', help='Output reads, BAM format.')
    parser.add_argument('--outMetrics',
        help='Output metrics file. Default is to dump to a temp file.',
        default=None)
    parser.add_argument("--remove",
        help="Instead of marking duplicates, remove them entirely (default: %(default)s)",
        default=False, action="store_true", dest="remove")
    parser.add_argument('--JVMmemory', default = tools.picard.MarkDuplicatesTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s MarkDuplicates, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_mkdup_picard(args) :
    opts = list(args.picardOptions)
    if args.remove:
        opts = ['REMOVE_DUPLICATES=true'] + opts
    tools.picard.MarkDuplicatesTool().execute(
        args.inBams, args.outBam, args.outMetrics,
        picardOptions=opts, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('mkdup_picard', main_mkdup_picard, parser_mkdup_picard))

# =============================
# ***  revert_bam_picard   ***
# =============================

def parser_revert_bam_picard() :
    parser = argparse.ArgumentParser(
        description='''Revert BAM to raw reads''')
    parser.add_argument('inBam', help='Input reads, BAM format.')
    parser.add_argument('outBam', help='Output reads, BAM format.')
    parser.add_argument('--JVMmemory', default = tools.picard.RevertSamTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s RevertSam, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_revert_bam_picard(args) :
    opts = list(args.picardOptions)
    tools.picard.RevertSamTool().execute(
        args.inBam, args.outBam,
        picardOptions=opts, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('revert_bam_picard',
    main_revert_bam_picard, parser_revert_bam_picard))

# =========================
# ***  generic picard   ***
# =========================

def parser_picard() :
    parser = argparse.ArgumentParser(
        description='Generic Picard runner.')
    parser.add_argument('command', help='picard command')
    parser.add_argument('--JVMmemory', default = tools.picard.PicardTools.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_picard(args) :
    tools.picard.PicardTools().execute(args.command,
        picardOptions=args.picardOptions, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('picard', main_picard, parser_picard))

# ===================
# ***  sort_bam   ***
# ===================

def parser_sort_bam() :
    parser = argparse.ArgumentParser(
        description='Sort BAM file')
    parser.add_argument('inBam',   help='Input bam file.')
    parser.add_argument('outBam',  help='Output bam file, sorted.')
    parser.add_argument('sortOrder',
        help='How to sort the reads. [default: %(default)s]',
        choices = tools.picard.SortSamTool.valid_sort_orders,
        default = tools.picard.SortSamTool.default_sort_order)
    parser.add_argument("--index",
        help="Index outBam (default: %(default)s)",
        default=False, action="store_true", dest="index")
    parser.add_argument("--md5",
        help="MD5 checksum outBam (default: %(default)s)",
        default=False, action="store_true", dest="md5")
    parser.add_argument('--JVMmemory', default = tools.picard.SortSamTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s SortSam, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_sort_bam(args) :
    opts = list(args.picardOptions)
    if args.index:
        opts = ['CREATE_INDEX=true'] + opts
    if args.md5:
        opts = ['CREATE_MD5_FILE=true'] + opts
    tools.picard.SortSamTool().execute(
        args.inBam, args.outBam, args.sortOrder,
        picardOptions=opts, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('sort_bam', main_sort_bam, parser_sort_bam))

# ====================
# ***  merge_bams  ***
# ====================

def parser_merge_bams() :
    parser = argparse.ArgumentParser(
        description='Merge multiple BAMs into one')
    parser.add_argument('inBams',  help='Input bam files.', nargs='+')
    parser.add_argument('outBam',  help='Output bam file.')
    parser.add_argument('--JVMmemory', default = tools.picard.MergeSamFilesTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s MergeSamFiles, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_merge_bams(args) :
    opts = list(args.picardOptions) + ['USE_THREADING=true']
    tools.picard.MergeSamFilesTool().execute(
        args.inBams, args.outBam,
        picardOptions=opts, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('merge_bams', main_merge_bams, parser_merge_bams))

# ====================
# ***  filter_bam  ***
# ====================

def parser_filter_bam() :
    parser = argparse.ArgumentParser(
        description='Filter BAM file by read name')
    parser.add_argument('inBam',  help='Input bam file.')
    parser.add_argument('readList',  help='Input file of read IDs.')
    parser.add_argument('outBam',  help='Output bam file.')
    parser.add_argument("--exclude",
        help="""If specified, readList is a list of reads to remove from input.
            Default behavior is to treat readList as an inclusion list (all unnamed
            reads are removed).""",
        default=False, action="store_true", dest="exclude")
    parser.add_argument('--JVMmemory', default = tools.picard.FilterSamReadsTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s FilterSamReads, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_filter_bam(args) :
    tools.picard.FilterSamReadsTool().execute(
        args.inBam, args.exclude, args.readList, args.outBam,
        picardOptions=args.picardOptions, JVMmemory=args.JVMmemory)
    return 0
__commands__.append(('filter_bam', main_filter_bam, parser_filter_bam))

# =======================
# ***  bam_to_fastq   ***
# =======================
def bam_to_fastq(inBam, outFastq1, outFastq2, outHeader = None,
                 JVMmemory = tools.picard.SamToFastqTool.jvmMemDefault, picardOptions = []) :
    ''' Convert a bam file to a pair of fastq paired-end read files and optional
        text header.
    '''
    tools.picard.SamToFastqTool().execute(inBam, outFastq1, outFastq2,
        picardOptions=picardOptions, JVMmemory=JVMmemory)
    if outHeader :
        tools.samtools.SamtoolsTool().dumpHeader(inBam, outHeader)

def parser_bam_to_fastq() :
    parser = argparse.ArgumentParser(
        description='Convert a bam file to a pair of fastq paired-end '\
                    'read files and optional text header.')
    parser.add_argument('inBam', help='Input bam file.')
    parser.add_argument('outFastq1',
        help='Output fastq file; 1st end of paired-end reads.')
    parser.add_argument('outFastq2',
        help='Output fastq file; 2nd end of paired-end reads.')
    parser.add_argument('--outHeader',
        help='Optional text file name that will receive bam header.',
        default=None)
    parser.add_argument('--JVMmemory', default = tools.picard.SamToFastqTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='Optional arguments to Picard\'s SamToFastq, OPTIONNAME=value ...')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser

def main_bam_to_fastq(args) :
    bam_to_fastq(args.inBam, args.outFastq1, args.outFastq2,
                 args.outHeader, args.JVMmemory, args.picardOptions)
    return 0

__commands__.append(('bam_to_fastq', main_bam_to_fastq,
                     parser_bam_to_fastq))

# =======================
# ***  fastq_to_bam   ***
# =======================

def fastq_to_bam(inFastq1, inFastq2, outBam, sampleName = None, header = None,
                 JVMmemory = tools.picard.FastqToSamTool.jvmMemDefault, picardOptions = []) :
    'Convert a pair of fastq paired-end read files and optional text header ' \
    'to a single bam file.'
    
    if header :
        fastqToSamOut = mkstempfname('.bam')
    else :
        fastqToSamOut = outBam
    if sampleName == None :
        sampleName = 'Dummy' # Will get overwritten by rehead command
    if header :
        # With the header option, rehead will be called after FastqToSam.
        # This will invalidate any md5 file, which would be a slow to construct
        # on our own, so just disallow and let the caller run md5sum if desired.
        if any(opt.lower() == 'CREATE_MD5_FILE=True'.lower()
                       for opt in picardOptions) :
            raise Exception('CREATE_MD5_FILE is not allowed with --header.')
    tools.picard.FastqToSamTool().execute(
        inFastq1, inFastq2, sampleName, fastqToSamOut,
        picardOptions=picardOptions, JVMmemory=JVMmemory)
    
    if header :
        tools.samtools.SamtoolsTool().reheader(fastqToSamOut, header, outBam)

def parser_fastq_to_bam() :
    parser = argparse.ArgumentParser(
        description='Convert a pair of fastq paired-end read files and '
                    'optional text header to a single bam file.')
    parser.add_argument('inFastq1',
        help='Input fastq file; 1st end of paired-end reads.')
    parser.add_argument('inFastq2',
        help='Input fastq file; 2nd end of paired-end reads.')
    parser.add_argument('outBam', help='Output bam file.')
    headerGroup = parser.add_mutually_exclusive_group(required = True)
    headerGroup.add_argument('--sampleName',
        help='Sample name to insert into the read group header.')
    headerGroup.add_argument('--header',
        help='Optional text file containing header.')
    parser.add_argument('--JVMmemory', default = tools.picard.FastqToSamTool.jvmMemDefault,
        help='JVM virtual memory size (default: %(default)s)')
    parser.add_argument('--picardOptions', default = [], nargs='*',
        help='''Optional arguments to Picard\'s FastqToSam,
                OPTIONNAME=value ...  Note that header-related options will be 
                overwritten by HEADER if present.''')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser

def main_fastq_to_bam(args) :
    fastq_to_bam(args.inFastq1, args.inFastq2, args.outBam, args.sampleName,
                 args.header, args.JVMmemory, args.picardOptions)
    return 0

__commands__.append(('fastq_to_bam', main_fastq_to_bam,
                     parser_fastq_to_bam))


# ======================
# ***  split_reads   ***
# ======================
defaultIndexLen = 2
defaultMaxReads = 1000
defaultFormat = 'fastq'

def split_reads(inFileName, outPrefix, outSuffix = "",
                maxReads = None, numChunks = None,
                indexLen = defaultIndexLen, format = defaultFormat) :
    '''Split fasta or fastq file into chunks of maxReads reads or into 
           numChunks chunks named outPrefix01, outPrefix02, etc.
       If both maxReads and numChunks are None, use defaultMaxReads.
       The number of characters in file names after outPrefix is indexLen;
            if not specified, use defaultIndexLen.
       Format can be 'fastq' or 'fasta'.
    '''
    if maxReads == None :
        if numChunks == None :
            maxReads = defaultMaxReads
        else :
            with util.file.open_or_gzopen(inFileName, 'rt') as inFile :
                totalReadCount = 0
                for rec in SeqIO.parse(inFile, format) :
                    totalReadCount += 1
                maxReads = int(totalReadCount / numChunks + 0.5)

    with util.file.open_or_gzopen(inFileName, 'rt') as inFile :
        readsWritten = 0
        curIndex = 0
        outFile = None
        for rec in SeqIO.parse(inFile, format) :
            if outFile == None :
                indexstring = "%0" + str(indexLen) + "d"
                outFileName = outPrefix + (indexstring % (curIndex+1)) + outSuffix
                outFile = util.file.open_or_gzopen(outFileName, 'wt')
            SeqIO.write([rec], outFile, format)
            readsWritten += 1
            if readsWritten == maxReads :
                outFile.close()
                outFile = None
                readsWritten = 0
                curIndex += 1
        if outFile != None :
            outFile.close()

def parser_split_reads() :
    parser = argparse.ArgumentParser(
        description='Split a fastq or fasta file into chunks.')
    parser.add_argument('inFile', help='Input fastq or fasta file.')
    parser.add_argument('outPrefix',
        help='Output files will be named ${outPrefix}01${outSuffix}, ${outPrefix}02${outSuffix}...')
    group = parser.add_mutually_exclusive_group(required = False)
    group.add_argument('--maxReads', type = int,
        help = 'Maximum number of reads per chunk (default {:d} if neither '\
               'maxReads nor numChunks is specified).'.format(defaultMaxReads))
    group.add_argument('--numChunks', type = int,
        help = 'Number of output files, if maxReads is not specified.')
    parser.add_argument('--indexLen', type = int, default = defaultIndexLen,
        help = '''Number of characters to append to outputPrefix for each
               output file (default %(default)s).
               Number of files must not exceed 10^INDEXLEN.''')
    parser.add_argument('--format', choices = ['fastq', 'fasta'],
        default = defaultFormat,
        help='Input fastq or fasta file (default: %(default)s).')
    parser.add_argument('--outSuffix',
        default = '',
        help = '''Output filename suffix (e.g. .fastq or .fastq.gz).
                  A suffix ending in .gz will cause the output file
                  to be gzip compressed. Default is no suffix.''')
    return parser

def main_split_reads(args) :
    split_reads(args.inFile, args.outPrefix, args.outSuffix,
        args.maxReads, args.numChunks, args.indexLen, args.format)
    return 0
__commands__.append(('split_reads', main_split_reads, parser_split_reads))


def split_bam(inBam, outBams) :
    '''Split BAM file equally into several output BAM files. '''
    samtools = tools.samtools.SamtoolsTool()
    picard = tools.picard.PicardTools()
    
    # get totalReadCount and maxReads
    # maxReads = totalReadCount / num files, but round up to the nearest
    # even number in order to keep read pairs together (assuming the input
    # is sorted in query order and has no unmated reads, which can be
    # accomplished by Picard RevertSam with SANITIZE=true)
    totalReadCount = samtools.count(inBam)
    maxReads = int(math.ceil(float(totalReadCount) / len(outBams) / 2) * 2)
    log.info("splitting %d reads into %d files of %d reads each" % (
        totalReadCount, len(outBams), maxReads))
    
    # load BAM header into memory
    header = samtools.getHeader(inBam)
    if 'SO:queryname' not in header[0]:
        raise Exception('Input BAM file must be sorted in queryame order')
    
    # dump to bigsam
    bigsam = mkstempfname('.sam')
    samtools.execute('view', [inBam], stdout=bigsam)
    
    # split bigsam into little ones
    with util.file.open_or_gzopen(bigsam, 'rt') as inf:
        for outBam in outBams:
            log.info("preparing file "+outBam)
            tmp_sam_reads = mkstempfname('.sam')
            with open(tmp_sam_reads, 'wt') as outf:
                for row in header:
                    outf.write('\t'.join(row)+'\n')
                for i in range(maxReads):
                    line = inf.readline()
                    if not line:
                        break
                    outf.write(line)
                if outBam == outBams[-1]:
                    for line in inf:
                        outf.write(line)
            picard.execute("SamFormatConverter", [
                'INPUT='+tmp_sam_reads, 'OUTPUT='+outBam,
                'VERBOSITY=WARNING'], JVMmemory='512m')
            os.unlink(tmp_sam_reads)
    os.unlink(bigsam)
def parser_split_bam() :
    parser = argparse.ArgumentParser(
        description='Split a fastq or fasta file into chunks.')
    parser.add_argument('inFile',
        help='Input BAM file.')
    parser.add_argument('outFiles', nargs='+',
        help='Output BAM files')
    return parser
def main_split_bam(args) :
    split_bam(args.inFile, args.outFiles)
    return 0
__commands__.append(('split_bam', main_split_bam, parser_split_bam))


# ============================
# ***  dup_remove_mvicuna  ***
# ============================

def mvicuna_fastqs_to_readlist(inFastq1, inFastq2, readList):
    # Run M-Vicuna on FASTQ files
    outFastq1 = mkstempfname('.1.fastq')
    outFastq2 = mkstempfname('.2.fastq')
    tools.mvicuna.MvicunaTool().rmdup((inFastq1, inFastq2), (outFastq1, outFastq2), None)
    
    # Make a list of reads to keep
    with open(readList, 'at') as outf:
        for fq in (outFastq1, outFastq2):
            with util.file.open_or_gzopen(fq, 'rt') as inf:
                line_num = 0
                for line in inf:
                    if (line_num % 4) == 0:
                        outf.write(line[1:])
                    line_num += 1
    os.unlink(outFastq1)
    os.unlink(outFastq2)

def parser_rmdup_mvicuna_bam() :
    parser = argparse.ArgumentParser(
        description='''Remove duplicate reads from BAM file using M-Vicuna. The
            primary advantage to this approach over Picard's MarkDuplicates tool
            is that Picard requires that input reads are aligned to a reference,
            and M-Vicuna can operate on unaligned reads.''')
    parser.add_argument('inBam', help='Input reads, BAM format.')
    parser.add_argument('outBam', help='Output reads, BAM format.')
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_rmdup_mvicuna_bam(args) :
    ''' TODO: this needs to be made smarter to operate independently
        on a per-library basis.'''
    
    # Convert BAM -> FASTQ pairs per read group and load all read groups
    tempDir = tempfile.mkdtemp()
    tools.picard.SamToFastqTool().per_read_group(args.inBam, tempDir,
        picardOptions=['VALIDATION_STRINGENCY=LENIENT'])
    read_groups = [x[1:] for x in
        tools.samtools.SamtoolsTool().getHeader(args.inBam)
        if x[0]=='@RG']
    read_groups = [dict(pair.split(':',1) for pair in rg) for rg in read_groups]
    
    # Collect FASTQ pairs for each library
    lb_to_files = {}
    for rg in read_groups:
        lb_to_files.setdefault(rg['LB'], set())
        fname = rg['ID']
        if 'PU' in rg:
            fname = rg['PU']
        lb_to_files[rg['LB']].add(os.path.join(tempDir, fname))
    log.info("found %d distinct libraries and %d read groups" % (len(lb_to_files), len(read_groups)))
    
    # For each library, merge FASTQs and run rmdup for entire library
    readList = mkstempfname('.keep_reads.txt')
    for lb, files in lb_to_files.items():
        log.info("executing M-Vicuna DupRm on library " + lb)
        
        # create merged FASTQs per library
        infastqs = (mksetmpfname('.1.fastq'), mksetmpfname('.2.fastq'))
        for d in range(2):
            with open(infastqs[d], 'wt') as outf:
                for fprefix in files:
                    fn = '%s_%d.fastq' % (fprefix, d+1)
                    with open(fn, 'rt') as inf:
                        for line in inf:
                            outf.write(line)
                    os.unlink(fn)
        
        # M-Vicuna DupRm to see what we should keep (append IDs to running file)
        mvicuna_fastqs_to_readlist(infastqs[0], infastqs[1], readList)
        map(os.unlink, infastqs)
    
    # Filter original input BAM against keep-list
    tools.picard.FilterSamReadsTool().execute(args.inBam, False, readList, args.outBam)
    return 0
__commands__.append(('rmdup_mvicuna_bam', main_rmdup_mvicuna_bam, parser_rmdup_mvicuna_bam))


def parser_dup_remove_mvicuna() :
    parser = argparse.ArgumentParser(
        description='''Run mvicuna's duplicate removal operation on paired-end 
                       reads.''')
    parser.add_argument('inFastq1',
        help='Input fastq file; 1st end of paired-end reads.')
    parser.add_argument('inFastq2',
        help='Input fastq file; 2nd end of paired-end reads.')
    parser.add_argument('pairedOutFastq1',
        help='Output fastq file; 1st end of paired-end reads.')
    parser.add_argument('pairedOutFastq2',
        help='Output fastq file; 2nd end of paired-end reads.')
    parser.add_argument('--unpairedOutFastq',
        default=None,
        help='File name of output unpaired reads')        
    util.cmd.common_args(parser, (('loglevel', None), ('version', None), ('tmpDir', None)))
    return parser
def main_dup_remove_mvicuna(args) :
    tools.mvicuna.MvicunaTool().rmdup(
        (args.inFastq1, args.inFastq2),
        (args.pairedOutFastq1, args.pairedOutFastq2),
        args.unpairedOutFastq)
    return 0
__commands__.append(('dup_remove_mvicuna', main_dup_remove_mvicuna,
                     parser_dup_remove_mvicuna))


# =======================

if __name__ == '__main__':
    util.cmd.main_argparse(__commands__, __doc__)
