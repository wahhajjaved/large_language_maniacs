#!/usr/bin/env python
"""
Usage: kMax_batch_run.py [OPTION] DIR

Option:
	DIR a directory containing the output files of db_to_mcl.py for kMax input.
	-k ..., --kMax_dir=...	the directory containing the kMax programs.
		default is '~/bin/kMax/'
	-p ..., --parameter=...	parameter passed to kMax, double quoted.
	-m ..., --max_bound=...	max_bound of kMax, 15(default)
	-h, --help              show this help
	
Examples:
	kMax_batch_run.py gph_result/mcl_input_kMax
	kMax_batch_run.py -p "0.8 0.9 2" gph_result/mcl_input_kMax
	
Description:
	It needs a directory which stores all the kMax input files(prefix is mcl_input).
	Every file is concatenated file. This program has an iterator to read through
	the file and let kMax to run over each Splat pattern. All the output files are
	in the parent directory.
	For the parameter, "min_degree(float) min_density(float) max_diameter(integer)"
	seperated by blankspace, ex. "0.7 0.8 2", which is the default.

"""

import sys, os, cStringIO, math, getopt, re

class kMax_iterator:
	'''looping over a kMax file'''
	def __init__(self, inf):
		self.inf = inf
		self.pattern = ''
	def __iter__(self):
		return self		
	def next(self):
		self.read()
		return cStringIO.StringIO(self.pattern)
	def read(self):
		kMax_begin = 0
		self.pattern = ''
		line = self.inf.readline()
		while line != '\n':
			if line == '':
				raise StopIteration
				break
			if kMax_begin:
				self.pattern += line
			if line[0] == 't':
				kMax_begin = 1
				self.pattern += line
			line = self.inf.readline()


class kMax_batch_run:
	'''
	Partition a big mcl job into 
	'''
	def __init__(self, dir, kMax_dir, parameter, max_bound):
		#no last '/' in abspath 
		self.dir = os.path.abspath(dir)
		self.kMax_dir = kMax_dir
		self.parameter = parameter
		self.max_bound = int(max_bound)
		if not os.path.isdir(self.dir):
			sys.stderr.write('%s not present\n'%self.dir)
			sys.exit(1)
		self.jobdir = os.path.join(os.path.expanduser('~'),'qjob')
		if not os.path.isdir(self.jobdir):
			os.makedirs(self.jobdir)
		self.f_list = os.listdir(self.dir)
		#parent directory of self.dir is to store the output files
		self.parent_dir = os.path.split(self.dir)[0]
		#the intermediate input file for kMax to read
		self.intermediate_ifname = os.path.join(self.dir, 'tmp1')
		#extract the number from a concatenated file to number the output files
		self.p_number = re.compile(r'\d+$')
	
	def submit(self):
		for file in self.f_list:
			if file.find('mcl_input') == 0:
				number = self.p_number.search(file).group()
				#job_outfname is the file to store the kMax results of all the splat patterns
				job_outfname = os.path.join(self.parent_dir, 'out%s'%number)
				job_outf = open(job_outfname, 'w')				
				#job_fname is the file with the commands of a job(kMax job).
				job_fname = os.path.join(self.jobdir, 'kMax_batch_run_%s.sh'%(file))
				#open the file to iterate
				inf = open(os.path.join(self.dir, file), 'r')
				iter = kMax_iterator(inf)
				for kMax_block in iter:
					splat_id_line = kMax_block.readline()
					#write the splat_id_line first
					job_outf.write(splat_id_line)
					intermediate_if = open(self.intermediate_ifname, 'w')
					intermediate_if.write(kMax_block.read())
					job_f = open(job_fname, 'w')
					out_block = '#!/bin/sh\n'		#this is '=' not '+='
					out_block += 'cd %s\n'%self.dir
					#prefix is tmp, relation_number is 1, support is 1.
					out_block += '%s tmp 1 1 %s %d\n'%(os.path.join(self.kMax_dir, 'kMax'), self.parameter, self.max_bound)
					out_block += '%s tmp patterns 1 1 %s\n'%(os.path.join(self.kMax_dir, 'kMax-distill'), self.parameter)
					job_f.write(out_block)
					#close the job_f
					job_f.close()
					#run the job with shell
					wl = ['sh', job_fname]
					os.spawnvp(os.P_WAIT, 'sh', wl)
					#after kMax-distill, the patterns are in file 'max-patterns'
					max_patterns_file = open(os.path.join(self.dir, 'max-patterns'), 'r')
					#transfer all the max-patterns into the job_outf
					job_outf.write(max_patterns_file.read())
					#add an end mark.
					job_outf.write('>\n')
					#close the max_patterns_file
					max_patterns_file.close()
				#close the output file.
				job_outf.close()
				#remove the job_f
				os.remove(job_fname)
		
if __name__ == '__main__':
	if len(sys.argv) == 1:
		print __doc__
		sys.exit(2)
		
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hk:p:m:", ["help", "kMax_dir=", "parameter=", "max_bound="])
	except:
		print __doc__
		sys.exit(2)

	kMax_dir = '~/bin/kMax'
	parameter = '0.7 0.8 2'
	max_bound = 15
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			print __doc__
			sys.exit(2)
		elif opt in ("-k", "--kMax_dir"):
			kMax_dir = int(arg)
		elif opt in ("-p", "--parameter"):
			parameter = arg
		elif opt in ("-m", "--max_bound"):
			max_bound = int(arg)
			
	if len(args)==1:
		instance = kMax_batch_run(args[0], kMax_dir, parameter, max_bound)
		instance.submit()

	else:
		print __doc__
		sys.exit(2)
