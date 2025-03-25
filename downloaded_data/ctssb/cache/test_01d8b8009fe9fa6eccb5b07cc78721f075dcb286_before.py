#!/usr/bin/env python

#
# Author: Steven Ludtke, 02/03/2007 (sludtke@bcm.edu)
# Copyright (c) 2000-2007 Baylor College of Medicine
#
# This software is issued under a joint BSD/GNU license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  2111-1307 USA
#
#

# e2simmx.py  02/03/2007	Steven Ludtke
# This program computes a similarity matrix between two sets of images

from EMAN2 import *
from optparse import OptionParser
from math import *
import os
import sys

a = EMUtil.ImageType.IMAGE_UNKNOWN

PROJ_FILE_ATTR = "projection_file" # this attribute important to e2simmxxplor
PART_FILE_ATTR = "particle_file" # this attribute important to e2simmxxplor

def opt_rectangular_subdivision(x,y,n):
		'''
		@param x the x dimension of a matrix
		@param y the y dimensons of a matrix
		@param the number of subdivisions you wish to partition the matrix into
		@return [number of x subdivisions, number of y subdivisions]
		Note that this routine needs a little bit of work - it returns good results when
		x >> y or y >> x, but when y ~= x it's not quite optimal. Good, but not optimal.
		'''
		
		print "Matrix size %d x %d into %d regions -> "%(x,y,n),
		candidates = []	

		# x,ysub is the number of x,y subdivisions
		# we insure that xsub<x and ysub<y, and that xsub>=1 and ysub>=1
		# for a given target n, we can compute ysub for a given xsub
		# and from that the corresponding maximum transfer cost (x/xsub+y/ysub)*xsub*ysub
		# we wish to minimize that quantity (note that it doesn't simplify due to int/float issues)
		for xsub in range(1,x):
			ysub=int(ceil(float(n/xsub)))
			if ysub>y or ysub<1 : continue		# can't have more subdivisions than rows
			
			# the ceil() makes us overestimate cases uneven division, but that breaks the tie in a good way
			cost=(ceil(float(x)/xsub)+ceil(float(y)/ysub))*xsub*ysub	
			candidates.append((cost,(xsub,ysub)))
		
		if len(candidates)==0:  return (x,y)		# should only happen if we have more processors than similarity matrix pixels
		
		candidates.sort()
		#print candidates
		print " %d x %d blocks -> %d subprocesses"%(candidates[0][1][0],candidates[0][1][1],candidates[0][1][0]*candidates[0][1][1])

		return candidates[0][1]



class EMParallelSimMX:
	def __init__(self,options,args,logger=None):
		'''
		@param options the options produced by (options, args) = parser.parse_args()
		@param args the options produced by (options, args) = parser.parse_args()
		@param logger and EMAN2 logger, i.e. logger=E2init(sys.argv)
		assumes you have already called the check function.
		'''
		self.options = options
		self.args = args
		self.logger = logger
		
	
		from EMAN2PAR import EMTaskCustomer
		etc=EMTaskCustomer(options.parallel)
		self.num_cpus = etc.cpu_est()
		if self.num_cpus < 32: # lower limit
			self.num_cpus = 32
		
		self.__task_options = None
	
	def __get_task_options(self,options):
		'''
		Get the options required by each task as a dict
		@param options is always self.options - the initialization argument. Could be changed.
		'''
		if self.__task_options == None:
			d = {}
			d["align"] = parsemodopt(options.align)
			d["aligncmp"] = parsemodopt(options.aligncmp)
			d["cmp"] = parsemodopt(options.cmp)
			
			if hasattr(options,"ralign") and options.ralign != None: 
				d["ralign"] = parsemodopt(options.ralign)
				d["raligncmp"] = parsemodopt(options.raligncmp)  # raligncmp must be specified if using ralign
			else: 
				d["ralign"] = None
				d["raligncmp"] = None
			
			if hasattr(options,"shrink") and options.shrink != None: d["shrink"] = options.shrink
			else: d["shrink"] = None

			
			self.__task_options = d
			
		return self.__task_options
	
	def __init_memory(self,options):
		'''
		@param options is always self.options - the initialization argument. Could be changed.
		Establishes several important attributes they are:
		----
		self.clen - the number of images in the image defined by args[0], the number of columns in the similarity matrix
		self.rlen - the number of images in the image defined by args[1], the number of rows in the similarity matrix
		----
		Also, since we adopted region output writing as our preferred approach, this function makes sure the output
		image(s) exists on disk and has the correct dimensions - seeing as this is the way region writing works (the image
		has to exist on disk and have its full dimensions)
		'''
		self.clen=EMUtil.get_image_count(self.args[0])
		self.rlen=EMUtil.get_image_count(self.args[1])
		
		output = self.args[2]
		
		if file_exists(output):
			if options.force: remove_file(output)
			else: raise RuntimeError("The output file exists. Please remove it or specify the force option")
			
		e = EMData(self.clen,self.rlen)
		e.to_zero()
		n = 1
		if self.options.saveali: n = 5 # the total number of images written to disk
		for i in range(n):
			e.set_attr(PROJ_FILE_ATTR,self.args[0])
			e.set_attr(PART_FILE_ATTR,self.args[1])
			e.write_image(output,i)
	
	def __get_blocks(self):
		'''
		Gets the blocks that will be processed in parallel, these are essentially ranges
		'''
		
		steve_factor = 8 # simmx should do more 
		total_jobs = steve_factor*self.num_cpus
		
		[col_div,row_div] = opt_rectangular_subdivision(self.clen,self.rlen,total_jobs)
		
	
		block_c = self.clen/col_div
		block_r = self.rlen/row_div
		
		residual_c = self.clen-block_c*col_div # residual left over by integer division

		blocks = []
		
		current_c = 0
		for c in xrange(0,col_div):
			last_c = current_c + block_c
			if residual_c > 0:
				last_c += 1
				residual_c -= 1
					
			current_r = 0
			residual_r = self.rlen-block_r*row_div # residual left over by integer division
			for r in xrange(0,row_div) :
				last_r = current_r + block_r
				if residual_r > 0:
					last_r += 1
					residual_r -= 1
			
			
				blocks.append([current_c,last_c,current_r,last_r])
				current_r = last_r
				
			current_c = last_c
		
#		print col_div,row_div,col_div*row_div
#		print self.clen,self.rlen,residual_c,residual_r
		return blocks
	
	
	def check_blocks(self,blocks):
		'''
		@param blocks that which is returned from __get_blocks -
		This function is for testing. 
		Goes through all of the blocks and adds a '1' to the pixels in the corresponding
		location in the image for each block. If any pixel is non zero there is a problem
		The call to this function could be removed eventually - if the data sets are huge
		then it could potentially occupy a lot of memory 
		'''
		e = EMData()
		e.set_size(self.clen,self.rlen)
		e.to_zero()
		
		for block in blocks:
			tmp = EMData()
			tmp.set_size(self.clen,self.rlen)
			tmp.to_zero()
			g = EMData()
			g.set_size(block[1]-block[0],block[3]-block[2],1)
			g.to_one()
			tmp.insert_clip(g,[block[0],block[2],0])
			e.add(tmp)
			
		f = EMData()
		f.set_size(self.clen,self.rlen)
		f.to_one()
		
		if not e == f:
			e.write_image("e.mrc")
			f.write_image("f.mrc")
			(e-f).write_image("error_block.mrc")
			print "block error",e["mean"]
			print "wrote error_block.mrc to disk"
			print blocks	
			raise RuntimeError("There was a catastrophic error: please send that which was printed out to EMAN2 developers")
		
	def execute(self):
		'''
		The main function to be called
		'''
		if len(self.options.parallel) > 2 and self.options.parallel[:2] == "dc":
			self.__init_memory(self.options)
			blocks = self.__get_blocks()
#			print blocks
	
#			self.check_blocks(blocks) # testing function can be removed at some point
			
			from EMAN2PAR import EMTaskCustomer
			etc=EMTaskCustomer(self.options.parallel)

			tasks=[]
			for block in blocks:
				
				data = {}
				data["references"] = ("cache",self.args[0],block[0],block[1])
				data["particles"] = ("cache",self.args[1],block[2],block[3])
				if self.options.mask!=None : data["mask"] = ("cache",self.options.mask,0,1)
				
				task = EMSimTaskDC(data=data,options=self.__get_task_options(self.options))
				#print "Est %d CPUs"%etc.cpu_est()
				tasks.append(task)
				
			self.tids=etc.send_tasks(tasks)
			print len(self.tids)," tasks submitted"
#			
			while 1:
				if len(self.tids) == 0: break
				print len(self.tids),"simmx tasks left in main loop   \r",
				sys.stdout.flush()
				st_vals = etc.check_task(self.tids)
				for i in xrange(len(self.tids)-1,-1,-1):
					st = st_vals[i]
					if st==100:
						tid = self.tids[i]
						
						try:
							rslts = etc.get_results(tid)
							self.__store_output_data(rslts[1])
						except:
							print "ERROR storing results for task %d. Rerunning."%tid
							etc.rerun_task(tid)
							contintue
						if self.logger != None:
							E2progress(self.logger,1.0-len(self.tids)/float(len(blocks)))
							if self.options.verbose: 
								print "%d/%d\r"%(len(self.tids),len(blocks))
								sys.stdout.flush()
								
						self.tids.pop(i)

				
				time.sleep(10)
			print ("All simmx tasks complete")
			
		else: raise NotImplementedError("The parallelism option you specified (%s) is not supported" %self.options.parallel )
				
	def __store_output_data(self,rslts):
		'''
		Store output data to internal images (matrices)
		@param a dictionary return by the EMSimTaskDC
		'''
	
		result_data = rslts["rslt_data"]
		output = self.args[2]
		
		insertion_c = rslts["min_ref_idx"]
		insertion_r = rslts["min_ptcl_idx"]
		result_mx = result_data[0]
		r = Region(insertion_c,insertion_r,result_mx.get_xsize(),result_mx.get_ysize())

		# Note this is region io - the init_memory function made sure the images exist and are the right dimensions (on disk)
		for i,mxout in enumerate(result_data):
			mxout.write_image(output,i,EMUtil.ImageType.IMAGE_UNKNOWN,False,r)

from EMAN2db import EMTask
class EMSimTaskDC(EMTask):
	'''
	Originally added to encapsulate a similarity matrix generation task 
	'''
	def __init__(self,command="e2simmx.py",data=None,options=None):
		EMTask.__init__(self,command,data,options)
		# options should have these keys:
		# align - the main aligner, a list of two strings
		# alligncmp - the main align cmp - a list of two strings
		# ralign - the refine aligner, a list of two string. May be None which turns it off
		# raligncmp - the refinealigncmp - a list of two strings. Needs to specified if ralign is not None
		# cmp - the final cmp - a list of two strings
		# shrink - a shrink value (int), may be None or unspecified - shrink the data by an integer amount prior to computing similarity scores

	
		# data should have
		# particles - a Task-style cached list of input images
		# references - a Task-style cached list of reference images
		
		self.sim_data = {} # this will store the eventual results
		
	def __init_memory(self,options):
		'''
		This function assigns critical attributes
		'''
		from EMAN2PAR import image_range
		shrink = None
		if options.has_key("shrink") and options["shrink"] != None and options["shrink"] > 1:
			shrink = options["shrink"]
		
		ref_data_name=self.data["references"][1]
		ref_indices = image_range(*self.data["references"][2:])
		
		if self.data.has_key("mask") :
			print "MASK ",self.data["mask"]
			mask=EMData(self.data["mask"][1],self.data["mask"][2])
			if shrink != None : mask.process_inplace("math.meanshrink",{"n":options["shrink"]})
		else : mask=None
		
#		print self.data["references"][2:]
		refs = {}
		for idx in ref_indices:
			image = EMData(ref_data_name,idx)
			if shrink != None:
				image.process_inplace("math.meanshrink",{"n":options["shrink"]})
			refs[idx] = image
			
		ptcl_data_name=self.data["particles"][1]
		ptcl_indices = image_range(*self.data["particles"][2:])
			
		ptcls = {}
		for idx in ptcl_indices:
			image = EMData(ptcl_data_name,idx)
			if shrink != None:
				image.process_inplace("math.meanshrink",{"n":options["shrink"]})
				if mask!=None : image.mult(mask)
			ptcls[idx] = image
		return refs,ptcls,shrink,mask
			
	def __cmp_one_to_many(self,ptcl,refs,mask):
	
		options = self.options
		
		data = {}
		for ref_idx,ref in refs.items():
			if options.has_key("align") and options["align"] != None:
				aligned=ref.align(options["align"][0],ptcl,options["align"][1],options["aligncmp"][0],options["aligncmp"][1])
	
				if options.has_key("ralign") and options["ralign"] != None: # potentially employ refine alignment
					refine_parms=options["ralign"][1]
					refine_parms["xform.align2d"] = aligned.get_attr("xform.align2d")
					ref.del_attr("xform.align2d")
					aligned = ref.align(options["ralign"][0],ptcl,refine_parms,options["raligncmp"][0],options["raligncmp"][1])		
			
				if mask!=None : 
					aligned.mult(mask)
				t =  aligned.get_attr("xform.align2d")
				t.invert()
				data[ref_idx] = (ptcl.cmp(options["cmp"][0],aligned,options["cmp"][1]),t)
			else:
				data[ref_idx] = (ptcl.cmp(options["cmp"][0],ref,options["cmp"][1]),None)
			
		return data
	
	def execute(self,progress_callback):
		if not progress_callback(0) : return None
		refs,ptcls,shrink,mask = self.__init_memory(self.options)
		
		
		sim_data = {} # It's going to be our favorite thing, a dictionary of dictionaries
		
		min_ptcl_idx = None
		n = float(len(ptcls))
		i = 0
		for ptcl_idx,ptcl in ptcls.items():
			if min_ptcl_idx == None or ptcl_idx < min_ptcl_idx:
				min_ptcl_idx = ptcl_idx 
			sim_data[ptcl_idx] = self.__cmp_one_to_many(ptcls[ptcl_idx],refs,mask)
			i+=1
			if not progress_callback(int(100*i/n)) : return None
		
			
			
		d = {}
#		d["sim_data"] = sim_data
		result_data = []
		if self.options.has_key("align") and self.options["align"] != None:
			for i in range(0,5):
				e = EMData(len(refs),len(ptcls))
				e.to_zero()
				result_data.append(e)
		else:
			e = EMData(len(refs),len(ptcls))
			e.to_zero()
			result_data.append(e)
		
		min_ref_idx = None
		for ref_idx in refs.keys():
			if min_ref_idx == None or ref_idx < min_ref_idx:
				min_ref_idx = ref_idx
		
		for r,dd in sim_data.items():
			for c,data in dd.items():
				cmp = data[0]
				rc = c-min_ref_idx # this was a solution to a bug
				rr = r-min_ptcl_idx # this was a solution to a bug
				result_data[0].set(rc,rr,cmp)
				if self.options.has_key("align") and self.options["align"] != None:
					tran = data[1]
					params = tran.get_params("2d")
					scale_correction = 1.0
					if shrink != None: corretion = float(shrink)
					result_data[1].set(rc,rr,scale_correction*params["tx"])
					result_data[2].set(rc,rr,scale_correction*params["ty"])
					result_data[3].set(rc,rr,params["alpha"])
					result_data[4].set(rc,rr,params["mirror"])
					
		for r in result_data: r.update()
		
		# This is to catch any NaNs - yes this is a problem but this is a temporary work around
		result_data[0].process_inplace("math.finite",{"to":1e24})
		
				
		d["rslt_data"] = result_data
		d["min_ref_idx"] = min_ref_idx
		d["min_ptcl_idx"] = min_ptcl_idx
		return d 
	
#	def get_return_data(self):
#		d = {}
#		d["sim_data"] = self.sim_data
#		return d

def main():
	progname = os.path.basename(sys.argv[0])
	usage = """%prog [options] <c input> <r input> <output>
	Computes a similarity matrix between c-input (col - projections) and r-input (row - particles) stacks of 2-D images. Images may
	optionally be aligned before comparison. Output is a matrix stored as an image with similarity value
	pairs. When used for classification, c input is the references and r input are the particles."""
	parser = OptionParser(usage=usage,version=EMANVERSION)

	#parser.add_option("--apix", "-A", type="float", help="A/voxel", default=1.0)
	#parser.add_option("--box", "-B", type="string", help="Box size in pixels, <xyz> or <x>,<y>,<z>")
	#parser.add_option("--het", action="store_true", help="Include HET atoms in the map", default=False)
	parser.add_option("--align",type="string",help="The name of an 'aligner' to use prior to comparing the images", default=None)
	parser.add_option("--aligncmp",type="string",help="Name of the aligner along with its construction arguments",default="dot")
	parser.add_option("--ralign",type="string",help="The name and parameters of the second stage aligner which refines the results of the first alignment", default=None)
	parser.add_option("--raligncmp",type="string",help="The name and parameters of the comparitor used by the second stage aligner. Default is dot.",default="dot")
	parser.add_option("--cmp",type="string",help="The name of a 'cmp' to be used in comparing the aligned images", default="dot:normalize=1")
	parser.add_option("--mask",type="string",help="File containing a single mask image to apply before similarity comparison",default=None)
	parser.add_option("--range",type="string",help="Range of images to process (c0,r0,c1,r1) c0,r0 inclusive c1,r1 exclusive", default=None)
	parser.add_option("--saveali",action="store_true",help="Save alignment values, output is c x r x 4 instead of c x r x 1",default=False)
	parser.add_option("--verbose","-v",type="int",help="Verbose display during run",default=0)
#	parser.add_option("--lowmem",action="store_true",help="prevent the bulk reading of the reference images - this will save memory but potentially increase CPU time",default=False)
	parser.add_option("--init",action="store_true",help="Initialize the output matrix file before performing 'range' calculations",default=False)
	parser.add_option("--force", "-f",dest="force",default=False, action="store_true",help="Force overwrite the output file if it exists")
	parser.add_option("--exclude", type="string",default=None,help="The named file should contain a set of integers, each representing an image from the input file to exclude. Matrix elements will still be created, but will be zeroed.")
	parser.add_option("--shrink", type="int",default=None,help="Optionally shrink the input particles by an integer amount prior to computing similarity scores. This will speed the process up.")
	parser.add_option("--nofilecheck",action="store_true",help="Turns file checking off in the check functionality - used by e2refine.py.",default=False)
	parser.add_option("--check","-c",action="store_true",help="Performs a command line argument check only.",default=False)
	parser.add_option("--parallel",type="string",help="Parallelism string",default=None)

	(options, args) = parser.parse_args()
	
	if len(args)<3 : parser.error("Input and output files required")
	
	if (options.check): options.verbose = True # turn verbose on if the user is only checking...
		
	if (options.nofilecheck == False):
		options.reffile=args[0]
		options.datafile = args[1]
		options.outfile = args[2]
	
	error = check(options,True)
	
	if (options.verbose):
		if (error):
			print "e2simmx.py command line arguments test.... FAILED"
		else:
			print "e2simmx.py command line arguments test.... PASSED"
		
	if error : exit(1)
	if options.check: exit(0)
	
	E2n=E2init(sys.argv)
	
	if options.parallel:
		parsimmx = EMParallelSimMX(options,args,E2n)
		parsimmx.execute()
		E2end(E2n)
		sys.exit(0)
		
	
	# just remove the file - if the user didn't specify force then the error should have been found in the check function
	if file_exists(options.outfile):
		if (options.force):
			remove_file(options.outfile)
	
	options.align=parsemodopt(options.align)
	options.aligncmp=parsemodopt(options.aligncmp)
	options.ralign=parsemodopt(options.ralign)
	options.raligncmp=parsemodopt(options.raligncmp)
	options.cmp=parsemodopt(options.cmp)

	if options.exclude: 
		try:
			excl=file(options.exclude,"r").readlines()
			excl=[int(i) for i in excl]
			excl=set(excl)
		except: print "Warning: exclude file failed"		# it's ok if this fails
		

	clen=EMUtil.get_image_count(args[0])
	rlen=EMUtil.get_image_count(args[1])
	
	if options.init:
		a=EMData()
		if options.saveali : a.set_size(clen,rlen,4)
		else : a.set_size(clen,rlen,1)
		a.to_zero()
		a.write_image(args[2])
		E2end(E2n)
		sys.exit(0)
	
	# Compute range in c and r
	if options.range :
		crange=options.range.split(",")[0:4:2]
		rrange=options.range.split(",")[1:4:2]
		crange[0]=int(crange[0])
		crange[1]=int(crange[1])
		rrange[0]=int(rrange[0])
		rrange[1]=int(rrange[1])
	else:
		crange=[0,clen]
		rrange=[0,rlen]

	# initialize output array
	mxout=[EMData()]
	mxout[0].set_attr(PROJ_FILE_ATTR,args[0])
	mxout[0].set_attr(PART_FILE_ATTR,args[1])
	mxout[0].set_size(crange[1]-crange[0],rrange[1]-rrange[0],1)
	mxout[0].to_zero()
	if options.saveali : 
		mxout.append(mxout[0].copy()) # dx
		mxout.append(mxout[0].copy()) # dy
		mxout.append(mxout[0].copy()) # alpha (angle)
		mxout.append(mxout[0].copy()) # mirror
	if options.verbose: print "Computing Similarities"

	# Read all c images, then read and compare one r image at a time
	cimgs=EMData.read_images(args[0],range(*crange))
	if options.shrink != None: # the check function guarantees that shrink is an integer greater than 1
		#d = [ image.process("math.meanshrink",{"n":options.shrink}) for image in cimgs]
		#cimgs = d
		for image in cimgs:
			image.process_inplace("math.meanshrink",{"n":options.shrink})
	
#	if (options.lowmem):
	rimg=EMData()
#	else:
#		rimages = EMData.read_images(args[1],range(*rrange))
#		if options.shrink != None: # the check function guarantees that shrink is an integer greater than 1
#			#d = [ image.process("math.meanshrink",{"n":options.shrink}) for image in rimages]
#			#rimages = d
#			# I chose this way in the end for memory efficiency. There's probably a better way to do it
#			for image in rimages:
#				image.process_inplace("math.meanshrink",{"n":options.shrink})
		
	#dimages =  EMData.read_images(args[1],range(*rrange))
	#d = [ image.process_inplace("math.meanshrink",{"n":options.shrink}) for image in dimages]
	
	if options.mask==None : mask=None
	else : mask=EMData(options.mask,0)
	
	for r in range(*rrange):
		if options.exclude and r in excl : continue
		
		if options.verbose: 
			print "%d/%d\r"%(r,rrange[1]),
			sys.stdout.flush()
			
#		if ( options.lowmem ):
		rimg.read_image(args[1],r)
		if options.shrink != None: # the check function guarantees that shrink is an integer greater than 
			rimg.process_inplace("math.meanshrink",{"n":options.shrink})
			if mask!=None : mask.process_inplace("math.meanshring",{"n":options.shrink})

		if mask!=None : rimg.mult(mask) 		# cimgs are masked in cmponetomany
#		else:
#			rimg = rimages[r]
		
		E2progress(E2n,float(r-rrange[0])/(rrange[1]-rrange[0]))
		shrink = options.shrink
		row=cmponetomany(cimgs,rimg,options.align,options.aligncmp,options.cmp, options.ralign, options.raligncmp,options.shrink,mask)
		for c,v in enumerate(row):
			mxout[0].set_value_at(c,r,0,v[0])
		
		# This is to catch any NaNs - yes this is a problem but this is a temporary work around
		mxout[0].process_inplace("math.finite",{"to":1e24})
		if options.saveali :
			for c,v in enumerate(row):
#				print row
				#print "%f %f %f " %(v[1],v[2],v[3])
				mxout[1].set_value_at(c,r,0,v[1])
				mxout[2].set_value_at(c,r,0,v[2])
				mxout[3].set_value_at(c,r,0,v[3])
				mxout[4].set_value_at(c,r,0,v[4])
	
	if options.verbose : print"\nSimilarity computation complete"
	
	# write the results into the full-sized matrix
	if crange==[0,clen] and rrange==[0,rlen] :
		for i,j in enumerate(mxout) : j.write_image(args[2],i)
	else :
		for i,j in enumerate(mxout) : j.write_image(args[2],i,IMAGE_UNKNOWN,0,Region(crange[0],rrange[0],0,crange[1]-crange[0],rrange[1]-rrange[0],1))
	
	E2end(E2n)
	
def cmponetomany(reflist,target,align=None,alicmp=("dot",{}),cmp=("dot",{}), ralign=None, alircmp=("dot",{}),shrink=None,mask=None):
	"""Compares one image (target) to a list of many images (reflist). Returns """
	
	ret=[None for i in reflist]
	for i,r in enumerate(reflist):
		if align[0] :
			r.del_attr("xform.align2d")
			ta=r.align(align[0],target,align[1],alicmp[0],alicmp[1])
			#ta.debug_print_params()
			
			if ralign and ralign[0]:
				ralign[1]["xform.align2d"] = ta.get_attr("xform.align2d")
				r.del_attr("xform.align2d")
				ta = r.align(ralign[0],target,ralign[1],alircmp[0],alircmp[1])
			
			t = ta.get_attr("xform.align2d")
			t.invert()
			p = t.get_params("2d")
			
			if mask!=None : ta.mult(mask)
			
			scale_correction = 1.0
			if shrink != None: scale_correction = float(shrink)
			ret[i]=(target.cmp(cmp[0],ta,cmp[1]),scale_correction*p["tx"],scale_correction*p["ty"],p["alpha"],p["mirror"])
		else :
			ret[i]=(target.cmp(cmp[0],r,cmp[1]),0,0,0,False)
		
	return ret

def check(options,verbose):
	print "in check"
	error = False
	if ( options.nofilecheck == False ):
		if not file_exists(options.datafile) and not db_check_dict(options.datafile):
			if verbose:
				print "Error: the file expected to contain the particle images (%s) does not exist." %(options.reffile)
			error = True
		if not file_exists(options.reffile) and not db_check_dict(options.reffile):
			if verbose:
				print "Error: the file expected to contain the projection images (%s) does not exist." %(options.reffile)
			error = True
		
		if ( file_exists(options.datafile) and file_exists(options.reffile) ):
			(xsize, ysize ) = gimme_image_dimensions2D(options.datafile);
			(pxsize, pysize ) = gimme_image_dimensions2D(options.reffile);
			if ( xsize != pxsize ):
				if verbose:
					print "Error - the (x) dimension of the reference images %d does not match that of the particle data %d" %(xsize,pxsize)
				error = True
			elif ( ysize != pysize ):
				if verbose:
					print "Error - the (y) dimension of the reference images %d does not match that of the particle data %d" %(ysize,pysize)
				error = True
				
		if  file_exists(options.outfile):
			if ( not options.force):
				if verbose:
					print "Error: File %s exists, will not write over - specify the force option" %options.outfile
				error = True
	
	if (options.cmp == None or options.cmp == ""):
		if verbose:
			print "Error: the --cmp argument must be specified"
		error = True
	else:
		if ( check_eman2_type(options.cmp,Cmps,"Comparitor") == False ):
			error = True
	
	if (options.shrink != None):
		if options.shrink == 1:
			options.shrink = None # just leave it as None please
			print "Warning, setting shrink to 1 does nothing. If you don't want shrinking to occur just forget the shrink argument"
			
		if options.shrink <= 1:
			print "Error: shrink must be greater than 1"
			error = True

	
	if (options.saveali):
		if   (options.align == None or options.align == ""):
			if verbose:
				print "Error: the --align argument must be specified if --saveali is specificed"
			error = True
		else:
			if ( check_eman2_type(options.align, Aligners,"Aligner") == False ):
				error = True
		
		if ( (options.aligncmp == None or options.aligncmp == "") and options.saveali):
			if verbose:
				print "Error: the --aligncmp argument must be specified if --saveali is specificed"
			error = True
		else:
			if ( check_eman2_type(options.aligncmp,Cmps,"Comparitor") == False ):
				error = True
		
	
		if ( options.ralign != None and options.ralign != ""):
			
			if ( check_eman2_type(options.ralign,Aligners,"Aligner") == False ):
				error = True
			
			if ( options.raligncmp == None or options.raligncmp == ""):
				if verbose:
					print "Error: the --raligncmp argument must be specified if --ralign is specificed"
			else:
				if ( check_eman2_type(options.raligncmp,Cmps,"Comparitor") == False ):
					error = True
	
	if hasattr(options,"parallel") and options.parallel != None:
  		if len(options.parallel) < 2:
  			print "The parallel option %s does not make sense" %options.parallel
  			error = True
  		elif options.parallel[:2] != "dc":
  			print "Only dc parallelism is currently supported"
  			error = True
  		elif len(options.parallel.split(":")) != 3:
  			print "dc parallel options must be formatted like 'dc:localhost:9990'"
  			error = True
	
	return error
	
	
	
if __name__ == "__main__":
    main()
