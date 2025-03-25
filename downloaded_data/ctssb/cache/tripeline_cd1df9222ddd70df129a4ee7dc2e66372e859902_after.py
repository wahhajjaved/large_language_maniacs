#!/usr/bin/env python
# -*- coding:utf-8 -*-

import os
import re
import subprocess
import sys
import tempfile


from automata import PatternMatcher
from collections import defaultdict
from gzopen import gzopen
from itertools import izip
from math import sqrt
from vtrack import vheader


LOGFNAME = 'tripelog.txt'

########  Mapping Pipeline ###############################################

def extract_reads_from_PE_fastq(fname_iPCR_PE1, fname_iPCR_PE2):
   """This function takes the 2 pair-end sequencing files and extracts the
   barcode making sure that the other read contains the transposon."""

   MIN_BRCD = 15
   MAX_BRCD = 25
   MIN_GENOME = 15

   # The known parts of the sequences are matched with a Levenshtein
   # automaton. On the reverse read, the end of the transposon
   # corresponds to a 34 bp sequence ending as shown below. We allow
   # up to 3 mismatches/indels. On the forward read, the only known
   # sequence is the CATG after the barcode, which is matched exactly.
   TRANSPOSON = PatternMatcher('TGTATGTAAACTTCCGACTTCAACTGTA', 3)

   # Open a file to write
   fname_fasta = re.sub(r'read[1-2].fastq(\.gz)?', 'iPCR.fasta',fname_iPCR_PE1)
   # Substitution failed, append '.fasta' to avoid name collision.
   if fname_fasta == fname_iPCR_PE1:
      fname_fasta = fname_iPCR_PE1 + '.fasta'

   # Skip if file exists.
   if os.path.exists(fname_fasta): return fname_fasta
    
   # Verbose information.
   sys.stderr.write('Extracting reads from %s\n' % fname_fasta)

   with gzopen(fname_iPCR_PE1) as f, gzopen(fname_iPCR_PE2) as g, \
      open(fname_fasta, 'w') as outf:
      # Aggregate iterator of f,g iterators -> izip(f,g).
      for lineno,(line1,line2) in enumerate(izip(f,g)):
         # Take sequence only.
         if lineno % 4 != 1: continue
         # Split on "CATG" and take the first fragment.
         # In case there is no "CATG", the barcode will be rejected
         # for being too long.
         brcd = line1.rstrip().split('CATG')[0]
         if not MIN_BRCD < len(brcd) < MAX_BRCD: continue
         # Use a Levenshtein automaton to find the transpsoson.
         gpos = TRANSPOSON.end(line2)
         if gpos < 0: continue
         # Select the region from the end of the transposon to
         # the first "CATG", if any.
         genome = line2[(gpos+1):].split('CATG')[0].rstrip()
         if len(genome) < MIN_GENOME: continue
         outf.write('>%s\n%s\n' % (brcd,genome))

   return fname_fasta


def call_gem_mapper_on_fasta_file(fname_fasta):
   """This function takes the barcodes and sequence extracted from the
   PE sequencing files and calls gem to do the mapping with up to 3
   mismatches and using 4 threads to align."""

   INDEX = '/mnt/shared/seq/gem/dm3R5/dm3R5_pT2_unmasked.gem'

   outfname = re.sub('\.fasta$', '', fname_fasta)

   # Skip if file exists.
   if os.path.exists(outfname + '.map'): return outfname + '.map'

   # Verbose information.
   sys.stderr.write('Mapping %s\n' % outfname)
    
   # TODO: specify version info for `gem-mapper`.
   # System call to `gem-mapper` passing the desired arguments.
   subprocess.call([
       'gem-mapper',
       '-I', INDEX ,
       '-i', fname_fasta,
       '-o', outfname,
       '-m3',
       '-T4',
       '--unique-mapping',
   ])
   # gem-mapper adds `.map` to the output file.
   return outfname + '.map'
    

def call_starcode_on_mapped_file(fname_mapped):
   """This function takes the barcodes contained in the first column of
   the mapped file and feed's them to starcode that clusters them."""

   fname_starcode = re.sub(r'\.map$', '_starcode.txt', fname_mapped)
   # Substitution failed, append '_starcode.txt' to avoid name collision.
   if fname_mapped == fname_starcode:
      fname_starcode = fname_mapped + '_starcode.txt'

   # Skip if file exists.
   if os.path.exists(fname_starcode): return fname_starcode

   # Verbose information.
   sys.stderr.write('Starcoding iPCR file: %s\n' % fname_starcode)

   # Create a pipe to make use of the `cut` command and pipe
   # it to starcode (git commit d4f63bd0cc5355d...).
   p1 = subprocess.Popen(['cut', '-f1', fname_mapped],
         stdout=subprocess.PIPE)
   p2 = subprocess.Popen([
      'starcode',
      '-t4',
      '-d2',
      '--print-clusters',
      '-o',
      fname_starcode],
      stdin=p1.stdout, stdout=subprocess.PIPE)
   # 'communicate()' returns a tuple '(stdoutdata, stderrdata)'.
   # If 'stderrdata' is not None we notify to know where the problem arose.
   stdoutdata,stderrdata = p2.communicate()
   if stderrdata is not None:
      sys.stderr.write("Pipe error (%s)\n" % str(stderrdata))
   return fname_starcode


def call_starcode_on_fastq_file(fname_fastq):
   ''' Extracts the gDNA,cDNA reads and spikes and runs stracode on them.'''
   MIN_BRCD = 15
   MAX_BRCD = 25

   brcd_outfname = re.sub(r'\.fastq.*', '_starcode.txt', fname_fastq)
   spk_outfname = re.sub(r'\.fastq.*', '_spikes_starcode.txt', fname_fastq)
   if brcd_outfname == fname_fastq:
      brcd_outfname = fname_fastq + '_starcode.txt'
   if spk_outfname == fname_fastq:
      spk_outfname = fname_fastq + '_spikes_starcode.txt'

   if os.path.exists(brcd_outfname) and os.path.exists(spk_outfname):
      return (brcd_outfname, spk_outfname)

   # Verbose information.
   sys.stderr.write('Starcoding %s and %s\n' % \
         (brcd_outfname, spk_outfname))

   GFP = PatternMatcher('CATGCTAGTTGTGGTTTGTCCAAACT', 3)
   SPIKE = PatternMatcher('CATGATTACCCTGTTATC', 2)
   barcode_tempf = tempfile.NamedTemporaryFile(delete=False)
   spike_tempf = tempfile.NamedTemporaryFile(delete=False)
   with gzopen(fname_fastq) as f:
      outf = None
      for lineno,line in enumerate(f):
         if lineno % 4 != 1: continue
         pos = GFP.start(line)
         if pos > -1:
            outf = barcode_tempf
         else:
            pos = SPIKE.start(line)
            if pos > -1:
               outf = spike_tempf
            else:
               continue
         if MIN_BRCD <= pos <= MAX_BRCD:
            outf.write(line[:pos] + '\n')
   barcode_tempf.close()
   spike_tempf.close()

   # Skip if file exists.
   if not os.path.exists(brcd_outfname):
      # Call `starcode`.
      subprocess.call([
         'starcode',
         '-t4',
         '-i', barcode_tempf.name,
         '-o', brcd_outfname,
      ])

   if not os.path.exists(spk_outfname):
      subprocess.call([
         'starcode',
         '-t4',
         '-i', spike_tempf.name,
         '-o', spk_outfname,
      ])

   # Delete temporary files.
   os.unlink(barcode_tempf.name)
   os.unlink(spike_tempf.name)

   return (brcd_outfname, spk_outfname)


def collect_integrations(fname_starcode_out, fname_mapped, *args):
   """This function reads the stacode output and changes all the barcodes
   mapped by their canonicals while it calculates the mapped distance
   rejecting multiple mapping integrations or unmmaped ones. It also
   counts the frequency that each barcode is found in the mapped data
   even for the non-mapping barcodes."""

   KEEP = frozenset([
      '2L', '2LHet', '2R', '2RHet', '3L', '3LHet',
      '3R', '3RHet', '4', 'X', 'XHet', 'U', 'Uextra',
      'dmel_mitochondrion_genome', 'pT2',
   ])

   fname_insertions_table = re.sub(r'\.map', '_insertions.txt',
          fname_mapped)
   # Substitution failed, append '_insertions.txt' to avoid name conflict.
   if fname_insertions_table == fname_mapped:
       fname_insertions_table = fname_mapped + '_insertions.txt'

   # Skip if file exists.
   if os.path.exists(fname_insertions_table): return

   # Verbose information.
   sys.stderr.write('processing %s\n' % fname_insertions_table)

   def dist(intlist):
      intlist.sort()
      try:
         if intlist[0][0] != intlist[-1][0]: return float('inf')
         return intlist[-1][1] - intlist[0][1]
      except IndexError:
         return float('inf')

   canonical = dict()
   with open(fname_starcode_out) as f:
      for line in f:
         items = line.split()
         for brcd in items[2].split(','):
            canonical[brcd] = items[0]

   counts = defaultdict(lambda: defaultdict(int))
   with open(fname_mapped) as f:
      for line in f:
         items = line.split()
         try:
            barcode = canonical[items[0]]
         except KeyError:
            continue
         if items[3] == '-':
            position = ('', 0)
         else:
            pos = items[3].split(':')
            loc = int(pos[2]) if pos[1] == '+' else \
                  int(pos[2]) + len(items[1])
            position = (pos[0], loc, pos[1])
         counts[barcode][position] += 1
      
   integrations = dict()
   for brcd,hist in counts.items():
       total = sum(hist.values())
       top = [pos for pos,count in hist.items() \
             if count > max(1, 0.1*total)]
       # Skip barcode in case of disagreement between top votes.
       if dist(top) > 10: continue
       ins = max(hist, key=hist.get)
       integrations[brcd] = (ins, total)

   # Count reads from other files.
   reads = dict()
   for (fname,ignore) in args:
      reads[fname] = defaultdict(int)
      with open(fname) as f:
         for line in f:
            items = line.split('\t')
            reads[fname][items[0]] = int(items[1])

   with open(fname_insertions_table, 'w') as outf:
      outf.write(vheader(*sys.argv))
      unmapped = 0
      mapped = 0
      for brcd in sorted(integrations, key=integrations.get):
         try:
            (chrom,pos,strand),total = integrations[brcd]
            if chrom not in KEEP: raise ValueError
         except ValueError:
            unmapped += 1
            continue
         mapped += 1
         outf.write('%s\t%s\t%s\t%d\t%d' % (brcd,chrom,strand,pos,total))
         for fname,ignore in args:
            outf.write('\t' + str(reads[fname][brcd]))
         outf.write('\n')

      # Now add the spikes.
      N = len(args)
      for i in range(N):
         (ignore,fname) = args[i]
         with open(fname) as f:
            for line in f:
               items = line.rstrip().split('\t')
               array = ['0'] * N
               array[i] = items[1]
               outf.write('%s\tspike\t*\t0\t0\t' % items[0])
               outf.write('\t'.join(array) + '\n')

   with open(LOGFNAME, 'a') as f:
      f.write('%s: mapped:%d, unmapped:%d\n' \
            % (fname_mapped, mapped, unmapped))
   return
   # Done.
   

def main(fname_fastq1, fname_fastq2, *args):
   fname_fasta = extract_reads_from_PE_fastq(fname_fastq1, fname_fastq2)
   fname_mapped = call_gem_mapper_on_fasta_file(fname_fasta)
   fname_starcode = call_starcode_on_mapped_file(fname_mapped)
   fnames_extra = [call_starcode_on_fastq_file(fname) for fname in args]
   collect_integrations(fname_starcode, fname_mapped, *fnames_extra)


if __name__ == '__main__':
   main(sys.argv[1], sys.argv[2], *sys.argv[3:])
