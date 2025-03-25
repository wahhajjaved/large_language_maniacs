#! /usr/bin/env python
import sys
from collections import defaultdict
from glob import glob
import re

from cbibio.utils.guess_encoding import guess_encoding


""" Constants """
# Extensions for fastq files
FASTQ_EXTENSIONS = set(['fastq','fq'])
# Extensions for fasta files
FASTA_EXTENSIONS = set(['fasta','fa', 'fas', 'fna'])

# Arguments for PRINSEQ
PRINSEQ_ARGS =        [ 'min_len', 'max_len', 'range_len',
                        'min_gc','max_gc','range_gc',
                        'min_qual_score', 'max_qual_score',
                        'min_qual_mean', 'max_qual_mean',
                        'ns_max_p', 'ns_max_n', 
                        'seq_num',
                        'derep', 'derep_min',
                        'lc_method', 'lc_threshold',
                        'trim_to_len',
                        'trim_left', 'trim_right', 
                        'trim_left_p','trim_right_p',
                        'trim_tail_left','trim_tail_right',
                        'trim_ns_left','trim_ns_right',
                        'trim_qual_left','trim_qual_right',
                        'trim_qual_type', 'trim_qual_rule', 'trim_qual_window', 'trim_qual_step',
                      ]
# Flags for PRINSEQ                 
PRINSEQ_FLAGS = ['noniupac']

# Preset for Illumina data
ILLUMINA_PRESET =     { 'min_len': 40,
                        'min_qual_mean': 20,
                        'derep': '23',
                        'lc_method': 'dust',
                        'lc_threshold': 7,
                        'trim_qual_left': 20,
                        'trim_qual_right': 20,
                        'trim_tail_left': 5,
                        'trim_tail_right': 5,
                        'trim_ns_left': 1,
                        'trim_ns_right': 1,
                      }
# Preset for IonTorrent data
IONTORRENT_PRESET =   { 'min_len': 40,
                        'min_qual_mean': 17,
                        'derep': '14',
                        'lc_method': 'dust',
                        'lc_threshold': 7,
                        'trim_qual_left': 17,
                        'trim_qual_right': 17,
                        'trim_tail_left': 5,
                        'trim_tail_right': 5,
                        'trim_ns_left': 1,
                        'trim_ns_right': 1,
                      }

""" Functions """

def chunks(l, n):
  ''' Yield successive n-sized chunks from list. '''
  for i in xrange(0, len(l), n):
    yield l[i:i+n]

def get_file_prefix(fn, args):
    extstr = '|'.join(FASTA_EXTENSIONS) if args.fasta else '|'.join(FASTQ_EXTENSIONS)    
    m = re.search('^(.*)%s([a-zA-Z0-9]+)\.(%s)$' % ('_', extstr),  fn)
    if m:
        return m.group(1)
    m = re.search('^(.*)\.(%s)$' % extstr, fn)
    if m:
        return m.group(1)
    return '.'.join(fn.split('.')[:-1])

def make_filecmd(fs, args):
    ''' Creates the command line for one file or pair of files '''
    # Information about the files
    fastx = 'fasta' if args.fasta else 'fastq'
    paired = len(fs) == 2
    prefix = get_file_prefix(fs[0], args)
    
    if paired:
        assert prefix == get_file_prefix(fs[1], args)

    # Guess the encoding of the files
    if guess_encoding(fs[0]) == 'Phred+64':
        encoding = '-phred64'
    else:
        encoding = ''

    # Input arguments    
    file1str = "-%s %s" % (fastx, fs[0])
    if paired:
        file2str = "-%s2 %s" % (fastx, fs[1])
    else:
        file2str = ''

    # Output arguments
    if not args.out_prinseq_names:
        goodstr = "-out_good %s_pseq" % prefix             # Output good file with wrapper naming scheme
    else:
        goodstr = ''                                       # Output good file with prinseq naming scheme
    
    if not args.out_bad:
        badstr = '-out_bad null'                           # Do not output bad file
    else:
        if not args.out_prinseq_names:
            badstr =  '-out_bad %s_pseqfail' % prefix      # Output bad file with wrapper naming scheme
        else:
            badstr =  ''                                   # Output bad file with prinseq naming scheme

    commandline = ['prinseq-lite', encoding, file1str, file2str, goodstr, badstr, "$basecmd", "&" ]
    return commandline

def make_basecmd(args):
    ''' Convert wrapper arguments to PRINSEQ command line '''
    commandline = []
    if not args.qual_header: commandline.append('-no_qual_header')
    
    d = vars(args)    
    for argkey in PRINSEQ_ARGS:
        if d[argkey] is not None:
            commandline.append('-%s %s' % (argkey, d[argkey]))
        elif args.illumina and argkey in ILLUMINA_PRESET:
            commandline.append('-%s %s' % (argkey, ILLUMINA_PRESET[argkey]))        
        elif args.iontorrent and argkey in IONTORRENT_PRESET:
            commandline.append('-%s %s' % (argkey, IONTORRENT_PRESET[argkey]))        
    for argkey in PRINSEQ_FLAGS:
        if d[argkey]:
            commandline.append('-%s' % argkey)        

    return commandline

def get_filesets(flist, args):
    ''' Attempt to pair files 
        Assumes that paired files have the same prefix ahead of some delimiter.
    '''
    if args.single:
        return [(f,) for f in flist]
    pairs = defaultdict(list)
    for f in flist:
        prefix = get_file_prefix(f, args)
        pairs[prefix].append(f)
    
    ret = []
    for prefix, fl in pairs.iteritems():
        if len(fl) == 1:
            ret.append((fl[0],))
        elif len(fl) == 2:
            ret.append(tuple(sorted(fl)))
        else:
            sys.exit("ERROR: identifying pairs failed! %s" % ', '.join(fl))
    return sorted(ret, key=lambda x:x[0])

def make_header(args):
  ''' Returns header for batch scripts '''
  return [     '#! /bin/bash',
               '#SBATCH -t %d' % args.walltime,
               '#SBATCH -p %s' % args.partition,
               '#SBATCH -N %d' % args.nodes,
               '',
               'SN="prinseq_wrapper"',
               'echo "[---$SN---] ($(date)) Starting $SN"',
               't1=$(date +"%s")',
               '',
               'module load %s' % args.prinseq_module,
               'export basecmd="%s"' % ' '.join(make_basecmd(args)),'',
               'echo "[---$SN---] ($(date))  Prinseq executable: $(which prinseq-lite)"',
               'echo "[---$SN---] ($(date))  Prinseq arguments:  $basecmd"',
               '',          
         ]

def make_footer():
  ''' Returns footer for batch scripts '''
  return [     '',
               '# Wait for all subprocesses to finish',
               'wait',
               '',
               '#---Complete job',
               't2=$(date +"%s")',
               'diff=$(($t2-$t1))',
               'echo "[---$SN---] Total time: ($(date)) $(($diff / 60)) minutes and $(($diff % 60)) seconds."',
               'echo "[---$SN---] ($(date)) $SN COMPLETE."',
         ]

def main(args):
    if not args.nosubmit:
        from subprocess import Popen,PIPE

    # Get list of files
    if args.fofn is not None:
        allfiles  = sorted([l.strip() for l in args.fofn])
    else:
        if args.fasta:
            allfiles  = sorted([f for f in glob('*') if f.split('.')[-1] in FASTA_EXTENSIONS])
        else:
            allfiles  = sorted([f for f in glob('*') if f.split('.')[-1] in FASTQ_EXTENSIONS])
    
    # Identify pairs of files
    filesets = get_filesets(allfiles, args)
    print >>sys.stderr, "INPUT FILES FOUND:"
    for fs in filesets:
        if len(fs)==1:
            print >>sys.stderr, 'unpaired: %s' % fs[0]
        elif len(fs)==2:
            print >>sys.stderr, 'reads1: %s\treads2: %s' % (fs)
    print >>sys.stderr, ''

    # Construct job script
    header = make_header(args)
    footer = make_footer()
    for i,chunk in enumerate(chunks(filesets, args.chunksize)):
        filecmds = []
        for fs in chunk:
            cmd = ' '.join(make_filecmd(fs, args))
            filecmds.extend(['echo "[---$SN---] ($(date)) COMMAND: %s"' % cmd, cmd, ''])
        script = header + filecmds + footer
        
        # Submit jobs or write files
        if args.nosubmit:
            print >>sys.stderr, '[--- job: prinseq%02d ---] Slurm script written to "job.%02d.sh".' % ((i+1), (i+1))
            with open('job.%02d.sh' % (i+1), 'w') as outh: 
                print >>outh, '\n'.join(script)
        else:
            # Submit these
            from subprocess import Popen,PIPE
            p = Popen(['sbatch','-J','prinseq%02d' % (i+1)],  stdin=PIPE, stdout=PIPE)
            out,err = p.communicate(input='\n'.join(script))
            print >>sys.stderr, '[--- job: prinseq%02d ---] %s. Running %d prinseq processes.' % ((i+1), out.strip('\n'), len(chunk))
            if args.detail:
                print >>sys.stderr, '\n'.join(script)
                print >>sys.stderr, ''
            
            
if __name__ == '__main__':
  import argparse
  import sys
  parser = argparse.ArgumentParser(description='',formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  preset_group = parser.add_argument_group("Presets")
  preset_group.add_argument('--illumina', action='store_true',
                           help='''Illumina filtering presets. 
                                   Equivalent to "%s"''' % ' '.join('-%s %s' % (k,v) for k,v in ILLUMINA_PRESET.iteritems()) )
  preset_group.add_argument('--iontorrent', action='store_true',
                           help='''IonTorrent filtering presets. 
                                   Equivalent to "%s"''' % ' '.join('-%s %s' % (k,v) for k,v in IONTORRENT_PRESET.iteritems()) )
  
  input_group = parser.add_argument_group("Input options")
  input_group.add_argument('--fofn', type=argparse.FileType('r'),
                           help="File of file names")
  input_group.add_argument('--single', action='store_true',
                           help="All files are single-end. Do not attempt to find paired files.")
  input_group.add_argument('--delim', default='_',
                           help="Delimiter used when looking for paired files.")
  input_group.add_argument('--fasta', action='store_true',
                           help="Input files are fasta format.")

  slurm_group = parser.add_argument_group("Slurm options")
  slurm_group.add_argument('--nosubmit', action='store_true',
                           help="Do not submit jobs directly. Output is written to batch scripts")
  slurm_group.add_argument('--chunksize', type=int, default=16, 
                           help="Number of prinseq instances per job. This should be less than or equal to the number of CPUs per node")
  slurm_group.add_argument('--walltime', type=int, default=480, 
                           help="Slurm walltime request (in minutes)")
  slurm_group.add_argument('--partition', default="short", 
                           help="Slurm partition request for resource allocation")
  slurm_group.add_argument('--nodes', type=int, default=1, 
                           help="Slurm node request")
  slurm_group.add_argument('--prinseq_module', default="prinseq/0.20.4", 
                           help='Name of prinseq module. Calling "module load [prinseq_module]" must load prinseq-lite into environment')
  slurm_group.add_argument('--detail', action='store_true',
                           help='Show detailed information about jobs being submitted.')


  output_group = parser.add_argument_group("Output options")
  output_group.add_argument('--out_format', type=int, default=3,
                           help='''To change the output format, use one of the following options. 
                                   If not defined, the output format will be the same as the input format. 
                                   1 (FASTA only), 2 (FASTA and QUAL), 3 (FASTQ), 4 (FASTQ and FASTA), or 5 (FASTQ, FASTA and QUAL)''')
  output_group.add_argument('--out_prinseq_names', action='store_true',
                           help='''By default, this wrapper names the good output files by removing the file
                                   extension and adding "_pseq" to the file name. The prinseq default
                                   is to add random characters to prevent overwriting; however, the
                                   filenames can be cumbersome for downstream analysis. Use this flag to
                                   use the default prinseq behavior.''')
  output_group.add_argument('--out_bad', action='store_true',
                            help='''By default, this wrapper does not output "bad" data that
                                    does not pass filters. Use this flag to output the failed
                                    data; the file names will have "_pseqfail" appended to the file name,
                                    unlessed used in conjunction with "--out_prinseq_names"''')
                                    
  output_group.add_argument('--qual_header', action='store_true',
                            help='''By default, this wrapper outputs an empty header line for the
                                    quality data to reduce file size. Use this flag to enable the
                                    quality header.''')

  filter_group = parser.add_argument_group("Filter options")
  filter_group.add_argument('--min_len', type=int,
                            help=" Filter sequence shorter than min_len.")
  filter_group.add_argument('--max_len', type=int,
                            help=" Filter sequence longer than max_len.")
  filter_group.add_argument('--range_len', 
                            help='''Filter sequence by length range. Multiple range values
                                    should be separated by comma without spaces. Example:
                                    --range_len 50-100,250-300''')
  filter_group.add_argument('--min_gc',
                            help='''Filter sequence with GC content below min_gc.''')
  filter_group.add_argument('--max_gc',
                            help='''Filter sequence with GC content above max_gc.''')
  filter_group.add_argument('--range_gc', 
                            help='''Filter sequence by GC content range. Multiple range values
                                    should be separated by comma without spaces. Example:
                                    --range_gc 50-100,250-300''')

  filter_group.add_argument('--min_qual_score', 
                            help='''Filter sequence with at least one quality score below min_qual_score.''')                                  
  filter_group.add_argument('--max_qual_score', 
                            help='''Filter sequence with at least one quality score above max_qual_score.''')
  filter_group.add_argument('--min_qual_mean', 
                            help='''Filter sequence with quality score mean below min_qual_mean.''')
  filter_group.add_argument('--max_qual_mean', 
                            help='''Filter sequence with quality score mean above max_qual_mean.''')                            

  filter_group.add_argument('--ns_max_p', 
                            help='''Filter sequence with more than ns_max_p percentage of Ns.''')                                       
  filter_group.add_argument('--ns_max_n', 
                            help='''Filter sequence with more than ns_max_n Ns.''')

  filter_group.add_argument('--noniupac', 
                            help='''Filter sequence with characters other than A, C, G, T or N.''')
  filter_group.add_argument('--seq_num', 
                            help='''Only keep the first seq_num number of sequences (that pass all other filters).''')

  filter_group.add_argument('--derep',
                            help='''Type of duplicates to filter. Allowed values are 1, 2,
                                    3, 4 and 5. Use integers for multiple selections (e.g.
                                    124 to use type 1, 2 and 4). The order does not
                                    matter. Option 2 and 3 will set 1 and option 5 will
                                    set 4 as these are subsets of the other option. 1
                                    (exact duplicate), 2 (5' duplicate), 3 (3' duplicate),
                                    4 (reverse complement exact duplicate), 5 (reverse
                                    complement 5'/3' duplicate)''')
  filter_group.add_argument('--derep_min',
                            help='''This option specifies the number of allowed
                                    duplicates. If you want to remove sequence duplicates
                                    that occur more than x times, then you would specify
                                    x+1 as the -derep_min values. For examples, to remove
                                    sequences that occur more than 5 times, you would
                                    specify -derep_min 6. This option can only be used in
                                    combination with -derep 1 and/or 4 (forward and/or
                                    reverse exact duplicates).''')
  filter_group.add_argument('--lc_method',
                            help='''Method to filter low complexity sequences. The current
                                    options are "dust" and "entropy". Use "-lc_method
                                    dust" to calculate the complexity using the dust
                                    method''')
  filter_group.add_argument('--lc_threshold',
                            help='''The threshold value (between 0 and 100) used to filter
                                    sequences by sequence complexity. The dust method uses
                                    this as maximum allowed score and the entropy method
                                    as minimum allowed value.''')

  trim_group = parser.add_argument_group("Trim options")
  trim_group.add_argument('--trim_to_len', type=int,
                          help='''Trim all sequence from the 3'-end to result in
                                  sequence with this length.''')
  trim_group.add_argument('--trim_left', type=int,
                          help='''Trim sequence at the 5'-end by trim_left positions.''')
  trim_group.add_argument('--trim_right', type=int,
                          help='''Trim sequence at the 3'-end by trim_right positions.''')
  trim_group.add_argument('--trim_left_p', type=int,
                          help='''Trim sequence at the 5'-end by trim_left_p percentage
                                  of read length. The trim length is rounded towards the
                                  lower integer (e.g. 143.6 is rounded to 143
                                  positions). Use an integer between 1 and 100 for the
                                  percentage value.''')
  trim_group.add_argument('--trim_right_p', type=int,
                          help='''Trim sequence at the 3'-end by trim_right_p percentage
                                  of read length. The trim length is rounded towards the
                                  lower integer (e.g. 143.6 is rounded to 143
                                  positions). Use an integer between 1 and 100 for the
                                  percentage value.''')
  trim_group.add_argument('--trim_tail_left', type=int,
                          help='''Trim poly-A/T tail with a minimum length of
                                  trim_tail_left at the 5'-end.''')
  trim_group.add_argument('--trim_tail_right', type=int,
                          help='''Trim poly-A/T tail with a minimum length of
                                  trim_tail_right at the 3'-end.''')
  trim_group.add_argument('--trim_ns_left', type=int,
                          help='''Trim poly-N tail with a minimum length of trim_ns_left
                                  at the 5'-end.''')
  trim_group.add_argument('--trim_ns_right', type=int,
                          help='''Trim poly-N tail with a minimum length of
                                  trim_ns_right at the 3'-end.''')
  trim_group.add_argument('--trim_qual_left', type=int,
                          help='''Trim sequence by quality score from the 5'-end with
                                  this threshold score.''')
  trim_group.add_argument('--trim_qual_right', type=int,
                          help='''Trim sequence by quality score from the 3'-end with
                                  this threshold score.''')
  trim_group.add_argument('--trim_qual_type', choices=['min', 'mean', 'max', 'sum'],
                          help='''Type of quality score calculation to use. Allowed
                                  options are min, mean, max and sum.''')
  trim_group.add_argument('--trim_qual_rule', choices=['lt','gt','et'],
                          help='''Rule to use to compare quality score to calculated
                                  value. Allowed options are lt (less than), gt (greater
                                  than) and et (equal to).''')
  trim_group.add_argument('--trim_qual_window', type=int,
                          help='''The sliding window size used to calculate quality
                                  score by type. To stop at the first base that fails
                                  the rule defined, use a window size of 1.''')
  trim_group.add_argument('--trim_qual_step', type=int,
                          help='''Step size used to move the sliding window. To move the
                                  window over all quality scores without missing any,
                                  the step size should be less or equal to the window
                                  size.''')

  args = parser.parse_args()
  main(args)
