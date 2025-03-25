#!/usr/bin/env python
#
# Author: David Woolford 11/10/08 (woolford@bcm.edu)
# Copyright (c) 2000-2008 Baylor College of Medicine
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
# Foundation, Inc., 59 Temple Place, Suite 330, Boston MA 02111-1307 USA
#
#

from emform import EMFormModule,ParamTable,EMTableFormModule
from emdatastorage import ParamDef
from PyQt4 import QtGui,QtCore
from PyQt4.QtCore import Qt
from EMAN2db import db_check_dict, db_open_dict,db_remove_dict,db_list_dicts,db_close_dict
from EMAN2 import *
import os
import copy
from emapplication import EMProgressDialogModule
from e2ctf import pspec_and_ctf_fit,GUIctfModule,write_e2ctf_output,get_gui_arg_img_sets
import subprocess
from pyemtbx.boxertools import set_idd_image_entry, TrimBox
import weakref
from e2history import HistoryForm

class EmptyObject:
	'''
	This just because I need an object I can assign attributes to, and object() doesn't seem to work
	'''
	def __init__(self):
		pass
	
	

class WorkFlowTask(QtCore.QObject):
	def __init__(self,application):
		QtCore.QObject.__init__(self)
		self.application = weakref.ref(application)
		self.window_title = "Set me please"
		self.preferred_size = (480,640)
	
	def run_form(self):
		self.form = EMFormModule(self.get_params(),self.application())
		self.form.qt_widget.resize(*self.preferred_size)
		self.form.setWindowTitle(self.window_title)
		self.application().show_specific(self.form)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_ok"),self.on_form_ok)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_cancel"),self.on_form_cancel)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_close"),self.on_form_close)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("display_file"),self.on_display_file)
		
	def on_display_file(self,filename):
		self.emit(QtCore.SIGNAL("display_file"),filename)	
		
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)
			
		self.form.closeEvent(None)
		self.form = None
	
		self.emit(QtCore.SIGNAL("task_idle"))
		
	def on_form_cancel(self):
		self.form.closeEvent(None)
		self.form = None

		self.emit(QtCore.SIGNAL("task_idle"))
	
	def on_form_close(self):
		self.emit(QtCore.SIGNAL("task_idle"))

	def closeEvent(self,event):
		self.form.closeEvent(None)
		#self.emit(QtCore.SIGNAL("task_idle")
		
	def write_db_entry(self,key,value):
		'''
		Call this function if you need to
		'''
		db = db_open_dict("bdb:project")
		if key == "global.apix":
			db["global.apix"] = value
		elif key == "global.microscope_voltage":
			db["global.microscope_voltage"] = value
		elif key == "global.microscope_cs":
			db["global.microscope_cs"] = value
		elif key == "global.memory_available":
			#mem = memory_stats()
			#if value > mem[0]:
				#print "error, memory usage is beyond the total amount available"
			#else:
			# we're avoiding validation because users have peculiar reasons some times
			db["global.memory_available"] = value
		elif key == "global.num_cpus":
			#n = num_cpus()
			#if value > n:
				#print "error, num_cpus more than the available cpus"
			#else:
			#  we're avoiding validation because users have peculiar reasons some times
			db["global.num_cpus"] = value
		else:
			pass
		
		db_close_dict("bdb:project")
	def get_wd(self):
		'''
		Get the working directory, originally introduced to provide a centralized mechanism for accessing the working directory,
		specificially for the purpose of spawning processes. Could be used more generally, however.
		'''
		return e2getcwd()

	def spawn_task(self,program,options,string_args,bool_args,additional_args=[],temp_file_name="e2workflow_tmp.txt"):
		'''
		splits the task over the available processors
		example-
		program="e2ctf.py"
		options is an object with the filenames, all string args and all bool_args as attributes 
		string_args=["
		bool_args=["
		additional_args=["--auto_db,--auto_fit"]
		temp_file_name = "etctf_auto_tmp.txt"
		'''
		project_db = db_open_dict("bdb:project")
		ncpu = project_db.get("global.num_cpus",dfl=num_cpus())
		cf = float(len(options.filenames))/float(ncpu) # common factor
		
		files = []
		for n in range(ncpu):
			files.append([])
			
		# distribute the names into bins
		for i,f in enumerate(options.filenames):
			idx = i % ncpu
			files[idx].append(f) 
		
		for n in range(ncpu):
			#print "n"
			filenames = files[n]
			if len(filenames) == 0: continue # maybe there are more CPUS then filenames
								
			args = [e2getinstalldir()+"/bin/"+program]
	
			for name in filenames:
				args.append(name)
			
			for string in string_args:
				args.append("--"+string+"="+str(getattr(options,string)))

			# okay the user can't currently change these, but in future the option might be there
			for string in bool_args:
				# these are all booleans so the following works:
				if getattr(options,string):
					args.append("--"+string)
					
			for arg in additional_args:
				args.append(arg)
			#print "command is ",program
			#for i in args: print i
			
			#print args
			file = open(temp_file_name,"w+")
			if(sys.platform != 'win32'):
				args_adjusted = []
			else:
				args_adjusted = ["pythonw"]
			args_adjusted.extend(args)
			#print args_adjusted
			process = subprocess.Popen(args_adjusted,stdout=file,stderr=subprocess.STDOUT)
			print "started process",process.pid
			self.emit(QtCore.SIGNAL("process_started"),process.pid)
			
		db_close_dict("bdb:project")
	
	def spawn_single_task(self,program,options,string_args,bool_args,additional_args=[],temp_file_name="e2workflow_tmp.txt"):
		'''
		runs a single job
		example-
		program="e2ctf.py"
		options is an object with the filenames, all string args and all bool_args as attributes 
		string_args=["
		bool_args=["
		additional_args=["--auto_db,--auto_fit"]
		temp_file_name = "etctf_auto_tmp.txt"
		'''
		project_db = db_open_dict("bdb:project")	
								
		#args = [program]
		args = [e2getinstalldir()+"/bin/"+program]
		for name in options.filenames:
			args.append(name)
		
		for string in string_args:
			args.append("--"+string+"="+str(getattr(options,string)))

		# okay the user can't currently change these, but in future the option might be there
		for string in bool_args:
			# these are all booleans so the following works:
			if getattr(options,string):
				args.append("--"+string)
				
		for arg in additional_args:
			args.append(arg)
		#print "command is ",program
		#for i in args: print i
		
		#print args
		file = open(temp_file_name,"w+")
		if(sys.platform != 'win32'):
			args_adjusted = []
		else:
			args_adjusted = ["pythonw"]
		args_adjusted.extend(args)
		#print args_adjusted
		process = subprocess.Popen(args_adjusted,stdout=file,stderr=subprocess.STDOUT)
		print "started process",process.pid
		self.emit(QtCore.SIGNAL("process_started"),process.pid)
		
		db_close_dict("bdb:project")
		
	def run_select_files_msg(self):
		'''
		Runs a QMessageBox asking for the user to select files for processing
		'''
		msg = QtGui.QMessageBox()
		msg.setWindowTitle("Almost")
		msg.setText("Please select files for processing")
		msg.exec_()

	def show_error_message(self,error_message):
		'''
		error_message is a list of error messages
		'''
		msg = QtGui.QMessageBox()
		msg.setWindowTitle("Almost")
		mes = ""
		for error in error_message:
			mes += error
			
			if len(error) > 0 and error[-1] != '.':
				# correct my own inconsistencies....AWESOME
				mes += '.'
			if error != error_message[-1]: mes += "\n"
		msg.setText(mes)
		msg.exec_()
		
	def get_latest_r2d_classes(self):
		dirs, files = get_files_and_directories(e2getcwd())
		
		dirs.sort()
		for i in range(len(dirs)-1,-1,-1):
			if len(dirs[i]) != 6:
				dirs.pop(i)
			elif dirs[i][:4] != "r2d_":
				dirs.pop(i)
			else:
				try: int(dirs[i][4:])
				except: dirs.pop(i)
		
		# allright everything left in dirs is "r2d_??" where the ?? is castable to an int, so we should be safe now
		class_files = []
		class_dims = []
		class_ptcls = []
		for dir in dirs:
			classes_db = None
			# check for 00 to 09 but 00 is replaced with "init"
			db_first_part = "bdb:"+dir+"#classes_"
			cont = True
			for i in range(0,10):
				for j in range(0,10):
					if i == 0 and j == 0:
						db_name = db_first_part+"init"
					else:
						db_name = db_first_part+str(i)+str(j)
						
					if db_check_dict(db_name):
						classes_db = db_name
					else:
						if i != 0 or j != 0:
							cont = False
							break
						#else just check for 01 incase the user has specified the --initial arugment
				if not cont:
					break
				
			if classes_db != None:
				class_files.append(classes_db)
				cl_db = db_open_dict(classes_db)
				if cl_db.has_key("maxrec"):
					class_ptcls.append(cl_db["maxrec"]+1)
					hdr = cl_db.get_header(0)
					class_dims.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
				else:
					class_ptcls.append("")
					class_dims.append("")
					
		return class_files,class_ptcls,class_dims
	
	def get_reference_free_class_averages_table(self):
		'''
		Looks for bdb:r2d_??#classes_?? and the bdb:r2d_??#classes_init file, finds the most recent one, then fills in the number of particles in
		in the class average file and also its dimensions.
		'''

		class_files,class_ptcls,class_dims = self.get_latest_r2d_classes()
					
		if len(class_files) > 0:
			
			p = ParamTable(name="filenames",desc_short="Most current reference free class averages",desc_long="")
			pclassnames = ParamDef(name="Files names",vartype="intlist",desc_short="Class avarerage file",desc_long="The location of the class average files",property=None,defaultunits=None,choices=class_files)
			pptcls = ParamDef(name="Class averages",vartype="intlist",desc_short="Total class averages",desc_long="The number class averages in the nominated file",property=None,defaultunits=None,choices=class_ptcls)
			pdims = ParamDef(name="Particle dimensions",vartype="stringlist",desc_short="Dimensions",desc_long="The dimensions of the images in the class averages file",property=None,defaultunits=None,choices=class_dims)
			
			p.append(pclassnames)
			p.append(pptcls)
			p.append(pdims)
			
			setattr(p,"convert_text", ptable_convert_2)
			setattr(p,"icon_type","matrix_image")
			
			return p,len(class_files)
		else:
			return None,0
		
	def check_sym(self,params,options):
		error_message = []
		if params["symname"] in ["c","d","h"]:
			n = params["symnumber"]
			fail = False
			if len(n) == 0: fail = True
			try: int(n)
			except: fail = True
			
			if not fail:
				if int(n) < 1:
					fail = True
					
			if fail:
				error_message.append("The symmetry number must be specified for c,d, and h.")
			else:
				options.sym=params["symname"]+n
		elif len(params["symnumber"]) != 0:
			error_message.append("There is something entered in the symmetry number box but you have not specified c, d or h symmetry.")
		else:
			options.sym = params["symname"]	
			
		return error_message
	
	def get_cmps_list(self):
		try: return dump_cmps_list().keys()
		except:
			return ['frc','optvariance','xyz','sqeuclidean','quadmindot','ccc','phase','dot']
			
	def get_aligners_list(self):
		try: return dump_aligners_list().keys()
		except:
			return ['rotational', 'rotate_precenter', 'xyz', 'rotate_translate', 'rtf_slow_exhaustive', 'rotate_flip', 'refine', 'translational', 'rotate_translate_flip', 'rtf_exhaustive']
	def get_projectors_list(self):
		try: return dump_projectors_list().keys()
		except:
			return ['xyz', 'gauss_fft', 'chao', 'standard', 'pawel', 'fourier_gridding']
		
	def get_orientgens_list(self):
		try: return dump_orientgens_list().keys()
		except:
			return ['even', 'opt', 'saff', 'rand', 'eman']
		
	def get_averagers_list(self):
		try: return dump_orientgens_list().keys()
		except:
			return ['ctfcw_auto', 'ctfcw', 'image', 'iteration', 'snr_weight', 'ctfc', 'minmax', 'xyz']
		
#		cmps.append("None") I think this is necessary
		
class HistoryTask(WorkFlowTask,HistoryForm):
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
		# don't need HistoryFrom init
		self.wd = os.getcwd()
		self.window_title = "History"
	
	def run_form(self):	
		self.form = EMFormModule(self.get_history_table(),self.application())
		self.form.qt_widget.resize(*self.preferred_size)
		self.form.setWindowTitle(self.window_title)
		self.form.qt_widget.setWindowIcon(QtGui.QIcon(os.getenv("EMAN2DIR")+"/images/feather.png"))
		self.application().show_specific(self.form)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_ok"),self.on_form_ok)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_cancel"),self.on_form_cancel)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_close"),self.on_form_close)
		
class ChangeDirectoryTask(WorkFlowTask):
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
		self.window_title = "Change project directory"
	
	def run_form(self):	
		
		fsp=QtGui.QFileDialog.getExistingDirectory(None, "Choose a directory")
		fsp = str(fsp)
		if os.path.exists(fsp):
			os.chdir(fsp)
			return fsp
		else: return None
		
	def closeEvent(self,event):
		pass
		#self.form.closeEvent(None)

		
class SPRInitTask(WorkFlowTask):
	'''
	A class that manages the initialization component of a Single Particle
	Reconstruction workflow
	'''
	
	# stolen from wikipedia
	Ddocumentation_string = "In physics, in the area of microscopy, single particle reconstruction is a technique in which large numbers of images (10,000 - 1,000,000) of ostensibly identical individual molecules or macromolecular assemblies are combined to produce a 3 dimensional reconstruction. This is a complementary technique to crystallography of biological molecules. As molecules/assembies become larger, it becomes more difficult to prepare high resolution crystals. For single particle reconstruction, the opposite is true. Larger objects actually improve the resolution of the final structure. In single particle reconstruction, the molecules/assemblies in solution are prepared in a thin layer of vitreous (glassy) ice, then imaged on an electron cryomicroscope (see Transmission electron microscopy). Images of individual molecules/assemblies are then selected from the micrograph and then a complex series of algorithms is applied to produce a full volumetric reconstruction of the molecule/assembly. In the 1990s this technique was limited to roughly 2 nm resolution, providing only gross features of the objects being studied. However, recent improvements in both microscope technology as well as available computational capabilities now make 0.5 nm resolution possible."
	documentation_string = "Welcome to the EMAN2 workflow. Use this tool to step through and manage the process of generating single particle reconstructions. Get started by entering what you can of the parameters in this form and then proceed to the next step task in the workflow."
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
		self.window_title = "Project information"
	def get_params(self):
		params = []
		project_db = db_open_dict("bdb:project")
		#params.append(ParamDef(name="global.micrograph_ccd_filenames",vartype="url",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=db_entry("global.micrograph_ccd_filenames","bdb:project",[]),choices=[]))
		params.append(ParamDef(name="blurb",vartype="text",desc_short="SPR",desc_long="Information regarding this task",property=None,defaultunits=SPRInitTask.documentation_string,choices=None))
		
		papix = ParamDef(name="global.apix",vartype="float",desc_short="A/pix for project",desc_long="The physical distance represented by the pixel spacing",property=None,defaultunits=project_db.get("global.apix",dfl=1.1),choices=None)
		pvolt = ParamDef(name="global.microscope_voltage",vartype="float",desc_short="Microscope voltage",desc_long="The operating voltage of the microscope in kilo volts",property=None,defaultunits=project_db.get("global.microscope_voltage",dfl=300),choices=None)
		pcs = ParamDef(name="global.microscope_cs",vartype="float",desc_short="Microscope Cs",desc_long="Microscope spherical aberration constant",property=None,defaultunits=project_db.get("global.microscope_cs",dfl=2.0),choices=None)
		pncp = ParamDef(name="global.num_cpus",vartype="int",desc_short="Number of CPUs",desc_long="Number of CPUS available for the project to use",property=None,defaultunits=project_db.get("global.num_cpus",dfl=num_cpus()),choices=None)
		mem = memory_stats()
		pmem = ParamDef(name="global.memory_available",vartype="float",desc_short="Memory usage ("+str(mem[0])+ " Gb total)",desc_long="The total amount of system memory you want to make available to the project in gigabytes",property=None,defaultunits=project_db.get("global.memory_available",dfl=mem[1]),choices=None)
		params.append(papix)
		params.append(pvolt)
		params.append(pcs)
		params.append(pncp)
		params.append(pmem)
		db_close_dict("bdb:project")
		return params

	def write_db_entry(self,key,value):
		WorkFlowTask.write_db_entry(self,key,value)		


class MicrographCCDImportTask(WorkFlowTask):	
	documentation_string = "Use this tool for importing flat files into the raw_data directory in the project database. Files that you import in this way will be automatically added the list of files in the project."
	
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
		self.window_title = "Import micrographs"
		self.thumb_shrink = -1
	def get_params(self):
		params = []
		project_db = db_open_dict("bdb:project")
		params.append(ParamDef(name="blurb",vartype="text",desc_short="Importing image data",desc_long="",property=None,defaultunits=MicrographCCDImportTask.documentation_string,choices=None))
		params.append(ParamDef(name="import_micrograph_ccd_files",vartype="url",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=[],choices=[]))
		pinvert = ParamDef(name="invert",vartype="boolean",desc_short="Invert",desc_long="Tick this if you want eman2 to invert your images while importing",property=None,defaultunits=False,choices=None)
		pxray = ParamDef(name="xraypixel",vartype="boolean",desc_short="X-ray pixel",desc_long="Tick this if you want eman2 to automatically filter out X-ray pixels while importing",property=None,defaultunits=False,choices=None)
		pnorm = ParamDef(name="norm.edgemean",vartype="boolean",desc_short="Edge norm",desc_long="Tick this if you want eman2 to automatically normalize your images using the edgmean approach",property=None,defaultunits=True,choices=None)
		pthumbnail = ParamDef(name="thumbs",vartype="boolean",desc_short="Thumbnails",desc_long="Tick this if you want eman2 to automatically generate thumbnails for your images. This will save time at later stages in the project",property=None,defaultunits=True,choices=None)
		
		params.append([pinvert,pxray,pnorm,pthumbnail])
		
		db_close_dict("bdb:project")
		return params
	
	def on_form_ok(self,params):
		
		error_message = self.check_params(params)
		if len(error_message):
			self.show_error_message(error_message)
			return
 		
		for k,v in params.items():
			if k == "import_micrograph_ccd_files":
				self.do_import(params)
			else:
				self.write_db_entry(k,v)

		self.form.closeEvent(None)
		self.form = None
	
		self.emit(QtCore.SIGNAL("task_idle"))

	def check_params(self,params):
		error_message = []
		filenames = params["import_micrograph_ccd_files"]
		
		if len(filenames) == 0:
			error_message.append("Please specify files to import.")
			return error_message
		
		for name in filenames:
			if len(name) == 0: continue
			if not file_exists(name):
				error_message.append("File %s doesn't exist." %name)
			else:
				try:
					e = EMData()
					e.read_image(name,0,1)
					n = EMUtil.get_image_count(name)
					if n > 1:
						error_message.append("File %s contains more than 1 image." %name)
				except:
					error_message.append("File %s is not a valid EM image." %name)
				
				
			
		no_dir_names = [get_file_tag(name) for name in filenames]
		
		for name in filenames:
			if name.find("bdb:rawdata#") != -1:
				error_message.append("Can't import files that are already in the project raw data directory : %s is invalid" %name)
		
		for name in no_dir_names:
			if no_dir_names.count(name) > 1:
				error_message.append("Can't import files with the same name : %s " %name)

		project_db = db_open_dict("bdb:project")
		current_project_files = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		cpft = [get_file_tag(file) for file in current_project_files]
		
		for name in filenames:
			
			tag = get_file_tag(name)
			if tag in cpft:
				error_message.append("Can't import images have identical tags to those already in the database, the problem is with %s" %name)
				
			
			db_name = "bdb:raw_data#"+tag
			if db_check_dict(db_name):
				error_message.append("There is already a raw_data database entry for %s" %db_name)

		return error_message

	def do_import(self,params):
		filenames = params["import_micrograph_ccd_files"]
		
		project_db = db_open_dict("bdb:project")
#		
		current_project_files = project_db.get("global.micrograph_ccd_filenames",dfl=[])

		# get the number of process operation - the progress dialog reflects image copying and image processing operations
		num_processing_operations = 2 # there is atleast a copy and a disk write
		if params["invert"]: num_processing_operations += 1
		if params["xraypixel"]: num_processing_operations += 1
		if params["thumbs"]:num_processing_operations += 1
		if params["norm.edgemean"]:num_processing_operations += 1
		
		
		# now add the files to db (if they don't already exist
		progress = EMProgressDialogModule(self.application(),"Importing files into database...", "Abort import", 0, len(filenames)*num_processing_operations,None)
		progress.qt_widget.show()
		i = 0
		cancelled = False # if the user cancels the import then we must act
		cancelled_dbs = []
		for name in filenames:
			
			tag = get_file_tag(name)
			db_name = "bdb:raw_data#"+tag

			e = EMData()
			e.read_image(name,0)
			i += 1
			progress.qt_widget.setValue(i)	
			self.application().processEvents()
			e.set_attr("disk_file_name",name)
			
			if params["norm.edgemean"]:
				e.process_inplace("normalize.edgemean")
				i += 1
				progress.qt_widget.setValue(i)
				self.application().processEvents()
			
			if params["invert"]:
				e.mult(-1)
				i += 1
				progress.qt_widget.setValue(i)
				self.application().processEvents()
			
			if params["xraypixel"]:
				e.process_inplace("threshold.clampminmax.nsigma",{"nsigma":4,"tomean":True})
				i += 1
				progress.qt_widget.setValue(i)
				self.application().processEvents()
				
			e.write_image(db_name,0)
			db_close_dict(db_name)
			cancelled_dbs.append(db_name)
			i += 1
			progress.qt_widget.setValue(i)
			self.application().processEvents()
			current_project_files.append(db_name)
				
			if params["thumbs"]:
				shrink = self.get_thumb_shrink(e.get_xsize(),e.get_ysize())
				thumb = e.process("math.meanshrink",{"n":shrink})
				thumb.process_inplace("normalize.edgemean")
				set_idd_image_entry(db_name,"image_thumb",thumb) # boxer uses the full name
				i += 1
				progress.qt_widget.setValue(i)
				self.application().processEvents()
				
			if progress.qt_widget.wasCanceled():
				cancelled = True
				for data_db in cancelled_dbs: # policy here is to remove only the raw data dbs - the e2boxer thumbnails are tiny and I don't have time...
					db_remove_dict(data_db)
				break
			
			
			
				
		progress.qt_widget.setValue(len(filenames))
		progress.qt_widget.close()
		
		if not cancelled:
			project_db["global.micrograph_ccd_filenames"] = current_project_files
			db_close_dict("bdb:project")
		
	def get_thumb_shrink(self,nx,ny):
		if self.thumb_shrink == -1:
			shrink = 1
			inx =  nx/2
			iny =  ny/2
			while ( inx >= 128 and iny >= 128):
				inx /= 2
				iny /= 2
				shrink *= 2
		
			self.thumb_shrink=shrink
		
		return self.thumb_shrink
			
	def on_import_cancel(self):
		print "canceled"
		
	
class MicrographCCDTask(WorkFlowTask):
	
	documentation_string = "This is a list of micrographs or CCD frames that you choose to associate with this project. You can add and remove file names by editing the text entries directly and or by using the browse and clear buttons. In addition to being able to specify images that are stored on your hard drive in the usual way, you can also choose images from EMAN2 style databases."
	
	
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
		self.window_title = "Project micrographs"

	def get_params(self):
		params = []
		project_db = db_open_dict("bdb:project")
		params.append(ParamDef(name="blurb",vartype="text",desc_short="Raw image data",desc_long="",property=None,defaultunits=MicrographCCDTask.documentation_string,choices=None))
		params.append(ParamDef(name="global.micrograph_ccd_filenames",vartype="url",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=project_db.get("global.micrograph_ccd_filenames",dfl=[]),choices=[]))
		
		db_close_dict("bdb:project")
		return params

	def on_form_ok(self,params):
		
		filenames = params["global.micrograph_ccd_filenames"]
		s_names =  [get_file_tag(name) for name in filenames]
		error_message = []
		for name in s_names:
			if s_names.count(name) > 1:
				error_message.append("you can't use images with the same file tag (%s)" %name)
		
		for i,name in enumerate(filenames):
					
			if os.path.exists(name) or db_check_dict(name):
				try:
					e = EMData()
					e.read_image(name,0,True)
					if EMUtil.get_image_count(name) > 1: error_message.append("%s contains more than one image" %name)
				except:
					error_message.append("%s is not a valid EM image type" %name)
					continue
			else:
				error_message.append("%s doesn't exist please remove it from this list" %name)

		if len(error_message) > 0:
			self.show_error_message(error_message)
			return
		
		for k,v in params.items():
			self.write_db_entry(k,v)
			
			
		
		self.form.closeEvent(None)
		self.form = None
	
		self.emit(QtCore.SIGNAL("task_idle"))

	def write_db_entry(self,key,value):
		if key == "global.micrograph_ccd_filenames":
			if value != None:

				new_names = []
		
				# now just update the static list of project file names
				e = EMData()
				read_header_only = True
				for i,name in enumerate(value):
					new_names.append(name)
						
				project_db = db_open_dict("bdb:project")
				project_db["global.micrograph_ccd_filenames"] = new_names
				db_close_dict("bdb:project")
		else:  pass


class ParticleWorkFlowTask(WorkFlowTask):
	'''
	Encapsulates some functionality  common to the particle based work flow tasks
	Such tasks should inherit from this class, not the the WorkFlowTask
	'''
	def __init__(self,application):
		WorkFlowTask.__init__(self,application)
	
	
	def get_particle_db_names_versatile(self,end_string="_ptcls",strip_end=False):
		'''
		
		'''
		if os.path.exists("particles/EMAN2DB"):
			dbs = db_list_dicts("bdb:particles#")
			ptcl_dbs = []
			for db in dbs:
				db_strip = get_file_tag(db)
				if len(db_strip) > len(end_string)-1:
					if db_strip[-len(end_string):] == end_string:
						if strip_end:
							ptcl_dbs.append(db_strip[:-len(end_string)])
						else:
							ptcl_dbs.append(db_strip)
			return ptcl_dbs
		else: return []
	
	def get_particle_db_names(self,strip_ptcls=True):
		'''
		returns a list of particle databases in the project
		for instance if these dbs files exist in the particle bdb directory:
		image_001_ptcls.bdb
		image_1000_a_ptcls.bdb
		image_001_ctf.bdbs
		then this function will return [ image_001, image_1000_a]
		Note the if strip_ptcls is False then the return list would instead be [ image_001_ptcls, image_1000_a_ptcls]
		If there are no such dbs then an empty list is returned
		'''
		return self.get_particle_db_names_versatile(end_string="_ptcls",strip_end=strip_ptcls)

	def get_particle_and_project_names(self):
		'''
		
		'''
		ptcl_dbs = self.get_particle_db_names()
		
		project_db = db_open_dict("bdb:project")
		project_files = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		for name in project_files:
			stripped = get_file_tag(name)
			if stripped not in ptcl_dbs:
				ptcl_dbs.append(stripped)
		db_close_dict("bdb:project")
		return ptcl_dbs
	
	def get_num_particles(self,project_files_names):
		ptcl_dbs = self.get_particle_db_names()
		vals = []
		for name in project_files_names:
			name_strip = get_file_tag(name)
			if name_strip in ptcl_dbs:
				db_name = "bdb:particles#"+name_strip+"_ptcls"
				if db_check_dict(db_name):
					db = db_open_dict(db_name)
					if db.has_key("maxrec") and db["maxrec"] != None:
						vals.append(db["maxrec"]+1)
						db_close_dict(db_name)
					else: vals.append("")
				else:
					vals.append("")
			else:
				vals.append("")
		return vals
	
	def get_particle_dims(self,project_names):
		if not os.path.exists("particles/EMAN2DB"):
			vals = [ "" for i in range(len(project_names))]
			return vals
		else:
			vals = []
			for name in project_names:
				name_strip = get_file_tag(name)
				db_name = "bdb:particles#"+name_strip+"_ptcls"
				if db_check_dict(db_name):
					try:
						db = db_open_dict(db_name)
						hdr = db.get_header(0)
						vals.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
						db_close_dict(db_name)
					except:vals.append("")
				else: vals.append("")
			return vals
		
	def get_particle_dims_direct(self,file_names):
		'''
		Iterates through the given names opening the bdb:particles#name
		and returning the dimensions as string e.g. 128x128x1, in a list
		You can use this function if the file_names are exactly those that exist in the particles BDB
		otherwise use get_particle_dims
		'''
		vals = []
		for name in file_names:
			db_name = "bdb:particles#"+name
			if db_check_dict(db_name):
				db = db_open_dict(db_name)
				hdr = db.get_header(0)
				vals.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
				db_close_dict(db_name)
			else: vals.append("No data")
		return vals

	def get_num_particles_direct(self,file_names):
		'''
		Iterates through the given names opening the bdb:particles#name
		and returning the number of particles in each db, in a list. If for some reason the dictionary doesn't exist will
		return a -1 in the list instead
		You can use this function if the file_names are exactly those that exist in the particles BDB
		otherwise use get_num_particles
		'''
		vals = []
		for name in file_names:
			db_name = "bdb:particles#"+name
			if db_check_dict(db_name):
				db = db_open_dict(db_name)
				vals.append(db["maxrec"]+1)
				db_close_dict(db_name)
			else:
				vals.append(-1)
		return vals
	
	def get_available_initial_models(self):
			
		db = "bdb:initial_models#"
		names = []
		for d in db_list_dicts("bdb:initial_models#"):
			if len(d) != 0 and db_check_dict(db+d):
				model_db = db_open_dict(db+d)
				if model_db.has_key("maxrec"):
					hdr = model_db.get_header(0)
					if hdr["nx"] == hdr["ny"] and hdr["nx"] == hdr["nz"]:
						names.append(d)
							
		return names

	def get_project_particle_param_table(self):
		'''
		Use the names in the global.micrograph_ccd_filenames to build a table showing the corresponding and  current number of boxed particles in the particles directory, and also lists their dimensions
		Puts the information in a ParamTable.
		'''
		project_db = db_open_dict("bdb:project")	
		project_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		
		ptable,n = self.__make_particle_param_table(project_names)
		setattr(ptable,"convert_text", ptable_convert_2)
		setattr(ptable,"icon_type","single_image")
		return ptable,n
		
	def get_particle_param_table(self):
		'''
		Inspects the particle databases in the particles directory, gathering their names, number of particles and dimenions. Puts the information in a ParamTable.
		'''
		project_names = self.get_particle_db_names(strip_ptcls=True)
		
		ptable,n = self.__make_particle_param_table(project_names)
		setattr(ptable,"convert_text", ptable_convert)
		setattr(ptable,"icon_type","matrix_image")
		return ptable,n
	def __make_particle_param_table(self,project_names):
		'''
		Functionality used in two places (directly above)
		'''
		
		num_boxes = self.get_num_particles(project_names)
		dimensions = self.get_particle_dims(project_names)
		
		pnames = ParamDef(name="global.micrograph_ccd_filenames",vartype="stringlist",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=None,choices=project_names)
		pboxes = ParamDef(name="Num boxes",vartype="intlist",desc_short="Particles on disk",desc_long="The number of box images stored for this image in the database",property=None,defaultunits=None,choices=num_boxes)
		pdims = ParamDef(name="Dimensions",vartype="stringlist",desc_short="Particle dims",desc_long="The dimensions of the particle images",property=None,defaultunits=None,choices=dimensions)
		
		p = ParamTable(name="filenames",desc_short="Choose a subset of these images",desc_long="")
		p.append(pnames)
		p.append(pboxes)
		p.append(pdims)
		
		return p, len(num_boxes)
	
	def get_total_particles_project_exclusive(self,tag="_ptcls"):
		'''
		A way to get the total number of particles that have a certain 
		'''
		project_db = db_open_dict("bdb:project")	
		project_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		stripped_project_names = [get_file_tag(name) for name in project_names ]
		particle_names = self.get_particle_db_names_versatile(tag,strip_end=True)
		
		good_names = []
		for name in particle_names:
			if name in stripped_project_names:
				good_names.append(name+tag)
		
		n = 0
		for name in good_names:
			db_name = "bdb:particles#"+name
			if db_check_dict(db_name):
				pt_db = db_open_dict(db_name)
				if pt_db.has_key("maxrec"):
					val = pt_db["maxrec"]
					if val != None:
						n += val+1 # maxrec is always one less than the actual number stored
						
		return n
	
	def get_total_particles(self,tag="_ptcls"):
		'''
		A way to get the total number of particles that have a certain ending
		tag = "_ptcls"
		tag = "_ptcls_ctf_wiener"
		tag = "_ptcls_ctf_phase" ALL WORK
		'''
		particle_names = self.get_particle_db_names_versatile(tag,strip_end=False)
		
		n = 0
		for name in particle_names:
			db_name = "bdb:particles#"+name
			if db_check_dict(db_name):
				pt_db = db_open_dict(db_name)
				if pt_db.has_key("maxrec"):
					val = pt_db["maxrec"]
					if val != None:
						n += val+1 # maxrec is always one less than the actual number stored
						
		return n
	
	def get_particle_selection_table(self,tag="_ptcls"):
		'''
		tag = "_ptcls"
		tag = "_ptcls_ctf_wiener"
		tag = "_ptcls_ctf_phase" ALL WORK
		'''
		particle_names = self.get_particle_db_names_versatile(tag,strip_end=False)
		n = []
		dims = []
		snr = []
		defocus = []
		for name in particle_names:
			db_name = "bdb:particles#"+name
			act = True
			act_d = True
			if db_check_dict(db_name):
				pt_db = db_open_dict(db_name)
				if pt_db.has_key("maxrec"):
					val = pt_db["maxrec"]
					if val != None:
						n.append(val)
						hdr = pt_db.get_header(0)
						dims.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
						act = False
					if hdr.has_key("ctf"):
						ctf = hdr["ctf"]
						if ctf != None:
							s = 0.0
							try:
								s = sum(ctf.snr)/len(ctf.snr)
							except: pass
							
							snr.append("%.3f" %s )
							defocus.append("%.3f" %ctf.defocus)
							act_d = False
					
						
			if act:
				n.append("")
				dims.append("")

			if act_d:
				snr.append("")
				defocus.append("")
		
		p = ParamTable(name="filenames",desc_short="Choose a subset of these images",desc_long="")
			
		pnames = ParamDef(name="names",vartype="stringlist",desc_short="File names",desc_long="The particles that will be used",property=None,defaultunits=None,choices=particle_names)
		pboxes = ParamDef(name="Num boxes",vartype="intlist",desc_short="Particles on disk",desc_long="The number of box images stored for this image in the database",property=None,defaultunits=None,choices=n)
		pdims = ParamDef(name="Dimensions",vartype="stringlist",desc_short="Particle dims",desc_long="The dimensions of the particle images",property=None,defaultunits=None,choices=dims)
		psnr = ParamDef(name="SNR",vartype="stringlist",desc_short="SNR",desc_long="The average SNR of the particle images",property=None,defaultunits=None,choices=snr)
		pdefocus = ParamDef(name="Defocus",vartype="stringlist",desc_short="Defocus",desc_long="The defocus of the particle images",property=None,defaultunits=None,choices=defocus)
		
	
		
		p.append(pnames)
		p.append(pboxes)
		p.append(psnr)
		p.append(pdefocus)
		p.append(pdims)
		
		setattr(p,"convert_text", ptable_convert_3)
		setattr(p,"icon_type","matrix_image")
		
		return p,len(pnames)

def ptable_convert(text):
	return "bdb:particles#"+text+"_ptcls"

def ptable_convert_2(text):
	return text

def ptable_convert_3(text):
	return "bdb:particles#"+text

def ptable_convert_4(text):
	return "bdb:initial_models#"+text
		
class ParticleReportTask(ParticleWorkFlowTask):
	'''
	
	Reports the current status of the particles in the projec
	'''
	
	documentation_string = "This tool is for displaying the particles that are currently associated with this project. This list is generating by inspecting the contents of the project particles directory."
	warning_string = "\n\n\nNOTE: There are no particles currently associated with the project. You can add particles to the project using e2boxer or by importing them directly - see from the list of options associated with this task." 
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Project particles"

	def get_params(self):
		params = []
		
		p,n = self.get_particle_param_table()
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=ParticleReportTask.documentation_string+ParticleReportTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=ParticleReportTask.documentation_string,choices=None))
			params.append(p)  
		
		return params


class ParticleImportTask(ParticleWorkFlowTask):	
	'''
	
	A task for importing particles into the project particles directory
	'''
	documentation_string = "Use this tool for importing particle images into the particle directory in the project database. Files that you import in this way will be automatically added the list of particle files in the project."
	
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Import particles"

	def get_params(self):
		params = []
		project_db = db_open_dict("bdb:project")
		params.append(ParamDef(name="blurb",vartype="text",desc_short="Description",desc_long="",property=None,defaultunits=ParticleImportTask.documentation_string,choices=None))
		params.append(ParamDef(name="import_particle_files",vartype="url",desc_short="Imported particles",desc_long="A list of particle files that have been or will be imported into this project",property=None,defaultunits=[],choices=[]))
		db_close_dict("bdb:project")
		return params

	def on_form_ok(self,params):
		
		mesbox = QtGui.QMessageBox()
		mesbox.setWindowTitle("Almost but not quite")
		
		error_message = self.check_args(params)
		if len(error_message) > 0:
			self.show_error_message(error_message)
			return
		
		v = params["import_particle_files"]
		progress = EMProgressDialogModule(self.application(),"Importing files into database...", "Abort import", 0, len(v),None)
		progress.qt_widget.show()
#			self.application().show_specific(progress)
	
		cancelled_dbs = []
		for i,name in enumerate(v):
			progress.qt_widget.setValue(i)
			self.application().processEvents()

			tag = get_file_tag(name)
			db_name = "bdb:particles#"+tag+"_ptcls"
			imgs = EMData().read_images(name)
			cancelled_dbs.append(db_name)
			for img in imgs: img.write_image(db_name,-1)
				
			if progress.qt_widget.wasCanceled():
				cancelled = True
				for db_name in cancelled_dbs:
					db_remove_dict(db_name)
				break
		
				
		progress.qt_widget.setValue(len(v))
		#self.application().close_specific(progress)
		progress.qt_widget.close()
				
			
		for k,v in params.items():
			self.write_db_entry(k,v)
			
		self.form.closeEvent(None)
		self.form = None
	
		self.emit(QtCore.SIGNAL("task_idle"))
	
	def check_args(self,params):
		error_message = []
		if len(params["import_particle_files"]) == 0:
			error_message.append("Please specify files to import")
		else:
			project_db = db_open_dict("bdb:project")
			project_file_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
			pfnt = [ get_file_tag(name) for name in project_file_names]
			
			v = params["import_particle_files"]
			for name in v:
				if get_file_tag(name) in pfnt:
					error_message.append("error, you can't import particles that have the same file name as one of the project files - the problem is with : %s" %get_file_tag(name))
					
			# now check to see if there are duplicated filetags in the incoming list
			# Actually the url form widget may have already dealt with this?
			nt = [ get_file_tag(name) for name in v]
			for name in v:
				if nt.count(get_file_tag(name)) > 1:
					error_message.append("you can't import particles that have the same file names! The problem is with : %s" %get_file_tag(name))
			
			# now check to see if there isn't already an entry in the particle directory that corresponds to this name
			particle_dbs = self.get_particle_db_names()
			for name in v:
				if get_file_tag(name) in particle_dbs:
					error_message.append("error, you can't import particles that already have entries in the particle database! The problem is with : %s" %get_file_tag(name))

			
			for name in v:
				fine, message = is_2d_image_mx(name)
				if not fine:
					error_message.append(message)

		return error_message
	

	def write_db_entry(self,k,v):
		pass
		#if k == "import_particle_files":
			# first make sure that the file tags that will correspond to the imported file names do not conflict with names in the project files
#			project_db = db_open_dict("bdb:project")
#			project_file_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
#			pfnt = [ get_file_tag(name) for name in project_file_names]
			
#			for name in v:
#				if get_file_tag(name) in pfnt:
#					print "error, you can't import particles that have the same file name as one of the project files - the problem is with:",get_file_tag(name)
#					db_close_dict("bdb:project")
#					return
#			# now check to see if there are duplicated filetags in the incoming list
#			# Actually the url form widget may have already dealt with this?
#			nt = [ get_file_tag(name) for name in v]
#			for name in v:
#				if nt.count(get_file_tag(name)) > 1:
#					print "error, you can't import particles that have the same file names! The problem is with:",get_file_tag(name)
#					db_close_dict("bdb:project")
#					return
#			
#			# now check to see if there isn't already an entry in the particle directory that corresponds to this name
#			particle_dbs = self.get_particle_db_names()
#			for name in v:
#				if get_file_tag(name) in particle_dbs:
#					print "error, you can't import particles that already have entries in the particle database! The problem is with:",get_file_tag(name)
#					db_close_dict("bdb:project")
#					return
			# okay if we make it here we're fine, import that particles
			
				
			
		#	db_close_dict("bdb:project")

		

class E2BoxerTask(ParticleWorkFlowTask):
	'''
	Provides some common functions for the e2boxer tasks
	'''
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		
	def get_e2boxer_boxes_and_project_particles_table(self):
		'''
		
		Returns a table like this:
		
		|| Project image name || Particles currently in desktop || Dimensions of Particles || Boxes in e2boxer db || Dims of boxes in e2boxer db|
		
		Returns the table, and the the number of entries (p,n)
		if n is zero there are no entries in the table and the calling function can act appropriately
		'''
		
		p,n = self.get_project_particle_param_table() # now p is a ParamTable with rows for as many files as there in the project
		# also, p contains columns with filename | particle number | particle dimensions
		 
		project_db = db_open_dict("bdb:project")	
		project_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		
		
		nboxes,dimensions = self.__get_e2boxer_data(project_names)
		pboxes = ParamDef(name="Num boxes",vartype="intlist",desc_short="Boxes in DB",desc_long="The number of boxes stored for this image in the database",property=None,defaultunits=None,choices=nboxes)
		pdims = ParamDef(name="DB Box Dims",vartype="stringlist",desc_short="Dims in DB",desc_long="The dimensions boxes",property=None,defaultunits=None,choices=dimensions)
		
		
		p_reordered = ParamTable(name="filenames",desc_short="Choose a subset of these images",desc_long="") # because I want the boxes in db to come first
		p_reordered.append(p[0])
		p_reordered.append(pboxes)
		p_reordered.extend(p[1:])
		

		setattr(p_reordered,"convert_text", ptable_convert_2)
		setattr(p_reordered,"icon_type","single_image")
		
		
		#p.append(pdims) # don't think this is really necessary
		return p_reordered,len(nboxes)
	
	def get_project_files_that_have_db_boxes_in_table(self):
		project_db = db_open_dict("bdb:project")	
		project_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		
		flat_boxes = self.get_num_particles(project_names)
		flat_dims = self.get_particle_dims(project_names)
		
		
		db_boxes,db_dims = self.__get_e2boxer_data(project_names)
		
		
		
		for i in range(len(db_dims)-1,-1,-1):
			if db_boxes[i] == "":
				for data in [project_names,flat_boxes,flat_dims,db_boxes,db_dims]:
					data.pop(i)
		
		
		pnames = ParamDef(name="global.micrograph_ccd_filenames",vartype="stringlist",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=None,choices=project_names)
		pboxes = ParamDef(name="Particles on disk",vartype="intlist",desc_short="Particles on disk",desc_long="The number of box images stored for this image in the database",property=None,defaultunits=None,choices=flat_boxes)
		pdims = ParamDef(name="Particle dimensions",vartype="stringlist",desc_short="Particle dims",desc_long="The dimensions of the particle images",property=None,defaultunits=None,choices=flat_dims)
		pdbboxes = ParamDef(name="Boxes in DB",vartype="intlist",desc_short="Boxes in DB",desc_long="The number of boxes stored for this image in the database",property=None,defaultunits=None,choices=db_boxes)
		pdvdims = ParamDef(name="DB Box Dims",vartype="stringlist",desc_short="Dims in DB",desc_long="The dimensions boxes",property=None,defaultunits=None,choices=db_dims)
		
		p = ParamTable(name="filenames",desc_short="Choose a subset of these images",desc_long="")
		p.append(pnames)
		p.append(pdbboxes)
		p.append(pboxes)
		p.append(pdims)
		
		setattr(p,"convert_text", ptable_convert_2)
		setattr(p,"icon_type","single_image")
		#p.append(pdvdims) # decided this wasn't necessary
		
		return p,len(db_dims)
		
	def __get_e2boxer_data(self,project_names):
		
		db_name = "bdb:e2boxer.cache"		
		box_maps = {}
		if db_check_dict(db_name):
			e2boxer_db = db_open_dict(db_name)
			for name in e2boxer_db.keys():
				d = e2boxer_db[name]
				if not isinstance(d,dict): continue
				if not d.has_key("e2boxer_image_name"): # this is the test, if something else has this key then we're screwed.
					continue
				name = d["e2boxer_image_name"]
				if not name in project_names: continue
				dim = ""
				nbox = 0
				for key in ["auto_boxes","manual_boxes","reference_boxes"]:
					if d.has_key(key):
						boxes = d[key]
						if boxes != None:
							nbox += len(boxes)
							if dim == "" and len(boxes) > 0:
								box = boxes[0]
								dim = str(box.xsize) + "x"+str(box.ysize)
				
				if nbox == 0: nbox = "" # just so it appears as nothin in the interface			
				box_maps[name] = [dim,nbox]
		
		nboxes = []
		dimensions = []
		for name in project_names:
			if box_maps.has_key(name):
				dimensions.append(box_maps[name][0])
				nboxes.append(box_maps[name][1])
			else:
				dimensions.append("")
				nboxes.append("")
				
		return nboxes,dimensions


class E2BoxerGenericTask(ParticleWorkFlowTask):
	documentation_string = "Fill me in"
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "e2boxer"
		self.preferred_size = (480,200)
		
		
	def get_params(self):
		params = []		
#		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGenericTask.documentation_string,choices=None))
		
		params.append(ParamDef(name="running_mode",vartype="choice",desc_short="Choose your running mode",desc_long="There are three Boxer related task which are generally run in order",property=None,defaultunits="auto",choices=["Interactive boxing", "Autoboxing", "Write output"]))
		
		return params

	def on_form_ok(self,params):
		if params["running_mode"] == "Interactive boxing":
			self.emit(QtCore.SIGNAL("replace_task"),E2BoxerGuiTaskGeneral,"e2boxer interface launcher")
			self.form.closeEvent(None)
			self.form = None
		elif params["running_mode"] == "Autoboxing":
			self.emit(QtCore.SIGNAL("replace_task"),E2BoxerAutoTaskGeneral,"e2boxer automated boxing")
			self.form.closeEvent(None)
			self.form = None
		elif params["running_mode"] == "Write output":
			self.emit(QtCore.SIGNAL("replace_task"),E2BoxerOutputTaskGeneral,"e2boxer write output")
			self.form.closeEvent(None)
			self.form = None	
		else:
			self.form.closeEvent(None)
			self.form = None
			self.emit(QtCore.SIGNAL("task_idle"))
			
	def write_db_entry(self,key,value):
		pass


class E2BoxerAutoTask(E2BoxerTask):
	'''
	A task for running automated boxing in the project context
	'''
	documentation_string = "Select the images you wish to run autoboxing on and hit OK.\nThis will cause the workflow to spawn processes based on the available CPUs.\nData will be autoboxed using the current autoboxer in the database, which is placed there by e2boxer."
	warning_string = "\n\n\nNOTE: This feature is currently disabled as there is no autoboxing information in the EMAN2 database. You can fix this situation by using e2boxer to interactively box a few images first"
	
	def __init__(self,application):
		E2BoxerTask.__init__(self,application)
		self.window_title = "e2boxer autobox"
		self.boxer_module = None # this will actually point to an EMBoxerModule, potentially

	def get_params(self):
		params = []
		
		
		db_name = "bdb:e2boxer.cache"
		fail = False
		if db_check_dict(db_name):
			db = db_open_dict(db_name)
			if not db.has_key("current_autoboxer"): fail = True
		else:
			fail = True
			
		if fail:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerAutoTask.documentation_string+E2BoxerAutoTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerAutoTask.documentation_string,choices=None))
			p,n = self.get_e2boxer_boxes_and_project_particles_table()
			params.append(p)
	
		return params
			
	def on_form_ok(self,params): 
		for k,v in params.items():
			self.write_db_entry(k,v)
			
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return
	
		else:
			options = EmptyObject()
			for k,v in params.items():
				setattr(options,k,v)
			
			string_args = []
			bool_args = []
			additional_args = ["--method=Swarm", "--auto=db"]
			temp_file_name = "e2boxer_autobox_stdout.txt"
			self.spawn_task("e2boxer.py",options,string_args,bool_args,additional_args,temp_file_name)
			self.emit(QtCore.SIGNAL("task_idle"))
			self.form.closeEvent(None)
			self.form = None

	def write_db_entry(self,key,value):
		if key == "boxsize":
			boxer_project_db = db_open_dict("bdb:e2boxer.project")
			boxer_project_db["working_boxsize"] = value
			db_close_dict("bdb:e2boxer.project")
		else:
			pass
	
class E2BoxerAutoTaskGeneral(E2BoxerAutoTask):
	def __init__(self,application):
		E2BoxerAutoTask.__init__(self,application)
		self.window_title = "e2boxer autobox"
		self.boxer_module = None # this will actually point to an EMBoxerModule, potentially

	def get_params(self):
		params = []
		
		
		db_name = "bdb:e2boxer.cache"
		fail = False
		if db_check_dict(db_name):
			db = db_open_dict(db_name)
			if not db.has_key("current_autoboxer"): fail = True
		else:
			fail = True
			
		if fail:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerAutoTask.documentation_string+E2BoxerAutoTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerAutoTask.documentation_string,choices=None))
			params.append(ParamDef(name="filenames",vartype="url",desc_short="File names",desc_long="The names of the particle files you want to interactively box using e2boxer",property=None,defaultunits=[],choices=[]))
		
		return params

class E2BoxerGuiTask(E2BoxerTask):	
	documentation_string = "Select the images you want to box, enter your boxsize, and hit OK. This will lauch e2boxer and automatically load the selected images for boxing."
	
	warning_string = "\n\n\nNOTE: There are no images currenty associated with the project. Please import or specify which images you want as part of this project in step 1 of the workflow and try again."
	
	def __init__(self,application):
		E2BoxerTask.__init__(self,application)
		self.window_title = "e2boxer interface"
		self.boxer_module = None # this will actually point to an EMBoxerModule, potentially

	def get_params(self):
		params = []
		
		p,n = self.get_e2boxer_boxes_and_project_particles_table()
		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Interactive use of e2boxer",desc_long="",property=None,defaultunits=E2BoxerGuiTask.documentation_string+E2BoxerGuiTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Interactive use of e2boxer",desc_long="",property=None,defaultunits=E2BoxerGuiTask.documentation_string,choices=None))
			params.append(p)
			boxer_project_db = db_open_dict("bdb:e2boxer.project")
			params.append(ParamDef(name="boxsize",vartype="int",desc_short="Box size",desc_long="An integer value",property=None,defaultunits=boxer_project_db.get("working_boxsize",dfl=128),choices=[]))
		return params
			
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)
		
		if not params.has_key("filenames"): return
		
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return

		if  params.has_key("boxsize") and params["boxsize"] < 1:
			self.show_error_message(["Must specify a positive, non zero boxsize."])
			return
		else:
			options = EmptyObject()
			for key in params.keys():
				setattr(options,key,params[key])
			options.running_mode = "gui"
			options.method = "Swarm"
			
			from e2boxer import EMBoxerModule
			self.boxer_module = EMBoxerModule(self.application(),options)
			self.emit(QtCore.SIGNAL("gui_running"),"Boxer",self.boxer_module) # The controlled program should intercept this signal and keep the E2BoxerTask instance in memory, else signals emitted internally in boxer won't work
			
			QtCore.QObject.connect(self.boxer_module, QtCore.SIGNAL("module_idle"), self.on_boxer_idle)
			QtCore.QObject.connect(self.boxer_module, QtCore.SIGNAL("module_closed"), self.on_boxer_closed)
			self.form.closeEvent(None)
			self.boxer_module.show_guis()
			self.form = None
			
	def on_form_close(self):
		# this is to avoid a task_idle signal, which would be incorrect if e2boxer is running
		if self.boxer_module == None:
			self.emit(QtCore.SIGNAL("task_idle"))
		else: pass
	
	def on_boxer_closed(self): 
		if self.boxer_module != None:
			self.boxer_module = None
			self.emit(QtCore.SIGNAL("gui_exit"))
	
	def on_boxer_idle(self):
		'''
		Presently this means boxer did stuff but never opened any guis, so it's safe just to emit the signal
		'''
		self.boxer_module = None
		self.emit(QtCore.SIGNAL("gui_exit"))

	def write_db_entry(self,key,value):
		if key == "boxsize":
			boxer_project_db = db_open_dict("bdb:e2boxer.project")
			boxer_project_db["working_boxsize"] = value
			db_close_dict("bdb:e2boxer.project")
		else:
			pass

class E2BoxerGuiTaskGeneral(E2BoxerGuiTask):	
	def __init__(self,application):
		E2BoxerTask.__init__(self,application)
		self.window_title = "e2boxer interface"
		self.boxer_module = None # this will actually point to an EMBoxerModule, potentially

	def get_params(self):
		params = []
		params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerGuiTask.documentation_string,choices=None))
		params.append(ParamDef(name="filenames",vartype="url",desc_short="File names",desc_long="The names of the particle files you want to interactively box using e2boxer",property=None,defaultunits=[],choices=[]))
		boxer_project_db = db_open_dict("bdb:e2boxer.project")
		params.append(ParamDef(name="boxsize",vartype="int",desc_short="Box size",desc_long="An integer value",property=None,defaultunits=boxer_project_db.get("working_boxsize",dfl=128),choices=[]))
		
		return params
	
	
class E2BoxerOutputTask(E2BoxerTask):	
	documentation_string = "Select the images you wish to generate output for, enter the box size and normalization etc, and then hit OK.\nThis will cause the workflow to spawn output writing processes using the available CPUs. Note that the bdb option is the preferred output format, in this mode output particles are written directly to the EMAN project database."
	warning_string = "\n\n\nNOTE: There are no boxes currently stored in the database. To rectify this situation use e2boxer to interactively box your images, or alternatively used autoboxing information stored in the database to autobox your images."
	def __init__(self,application):
		E2BoxerTask.__init__(self,application)
		self.window_title = "e2boxer output"
	
	def get_params(self):
		params = []
		
		p,n = self.get_project_files_that_have_db_boxes_in_table()
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerOutputTask.documentation_string+E2BoxerOutputTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerOutputTask.documentation_string,choices=None))
			params.append(p)
			self.add_general_params(params)

		return params
	
	def add_general_params(self,params):
		'''
		Functionality used in several places
		'''
		boxer_project_db = db_open_dict("bdb:e2boxer.project")
		pbox = ParamDef(name="boxsize",vartype="int",desc_short="Box size",desc_long="An integer value",property=None,defaultunits=boxer_project_db.get("working_boxsize",dfl=128),choices=[])	
		pfo = ParamDef(name="force",vartype="boolean",desc_short="Force overwrite",desc_long="Whether or not to force overwrite files that already exist",property=None,defaultunits=False,choices=None)
		pwc = ParamDef(name="write_coord_files",vartype="boolean",desc_short="Write box db files",desc_long="Whether or not box db files should be written",property=None,defaultunits=False,choices=None)
		pwb = ParamDef(name="write_box_images",vartype="boolean",desc_short="Write box image files",desc_long="Whether or not box images should be written",property=None,defaultunits=True,choices=None)
		pn =  ParamDef(name="normproc",vartype="string",desc_short="Normalize images",desc_long="How the output box images should be normalized",property=None,defaultunits="normalize.edgemean",choices=["normalize","normalize.edgemean","none"])
		pop = ParamDef(name="outformat",vartype="string",desc_short="Output image format",desc_long="The format of the output box images",property=None,defaultunits="bdb",choices=["bdb","img","hdf"])
		params.append([pbox,pfo])
		params.append([pwc,pwb])
		params.append(pn)
		params.append(pop)
		
	
	def check_params(self,params):
		
		error_message = []
		if params["boxsize"] < 1: error_message.append("Boxsize must be greater than 0.")
		if not params["write_coord_files"] and not params["write_box_images"]: error_message.append("You must choose at least one of the write_coords/write_box_images options")
	
		return error_message
	
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)
			
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return
		
		error_message = self.check_params(params)
		if len(error_message) >0: 
			self.show_error_message(error_message)
			return
		
		else:
			options = EmptyObject()
			for k,v in params.items():
				setattr(options,k,v)
				
			options.just_output=True # this is implicit, it has to happen
			
			string_args = ["normproc","outformat","boxsize"]
			bool_args = ["force","write_coord_files","write_box_images","just_output"]
			additional_args = ["--method=Swarm", "--auto=db"]
			temp_file_name = "e2boxer_autobox_stdout.txt"
			self.spawn_task("e2boxer.py",options,string_args,bool_args,additional_args,temp_file_name)
			self.emit(QtCore.SIGNAL("task_idle"))
			self.form.closeEvent(None)
			self.form = None
#	
	def write_db_entry(self,key,value):
		if key == "boxsize":
			boxer_project_db = db_open_dict("bdb:e2boxer.project")
			boxer_project_db["working_boxsize"] = value
			db_close_dict("bdb:e2boxer.project")
		else:
			pass

class E2BoxerOutputTaskGeneral(E2BoxerOutputTask):
	documentation_string = "Write me"
	def __init__(self,application):
		E2BoxerOutputTask.__init__(self,application)
		self.window_title = "e2boxer output"
		
	def get_params(self):
		params = []
		params.append(ParamDef(name="blurb",vartype="text",desc_short="Using e2boxer",desc_long="",property=None,defaultunits=E2BoxerOutputTaskGeneral.documentation_string,choices=None))
		
		p = self.get_e2boxer_boxes_table(project_check=False)
		params.append(p)
		
		self.add_general_params(params)
	
#		boxer_project_db = db_open_dict("bdb:e2boxer.project")
#		params.append(ParamDef(name="boxsize",vartype="int",desc_short="Box size",desc_long="An integer value",property=None,defaultunits=boxer_project_db.get("working_boxsize",dfl=128),choices=[]))
		return params
	
	def get_e2boxer_boxes_table(self,project_check=True):
		db_name = "bdb:e2boxer.cache"
		p = ParamTable(name="filenames",desc_short="Current boxes generated by e2boxer",desc_long="")
		names = []
		nboxes = []
		dimensions = []
		
		if project_check:
			project_db = db_open_dict("bdb:project")	
			project_names = project_db.get("global.micrograph_ccd_filenames",dfl=[])
		
		if db_check_dict(db_name):
			e2boxer_db = db_open_dict(db_name)
			for name in e2boxer_db.keys():
				d = e2boxer_db[name]
				if not isinstance(d,dict): continue
				if not d.has_key("e2boxer_image_name"): # this is the test, if something else has this key then we're screwed.
					continue

				name = d["e2boxer_image_name"]
				if project_check:
					if not name in project_names: continue
				names.append(name)
				
				dim = ""
				nbox = 0
				for key in ["auto_boxes","manual_boxes","reference_boxes"]:
					if d.has_key(key):
						boxes = d[key]
						nbox += len(boxes)
						if dim == "" and len(boxes) > 0:
							box = boxes[0]
							dim = str(box.xsize) + "x"+str(box.ysize)
							
							
				nboxes.append(nbox)
				dimensions.append(dim)
			
		pnames = ParamDef(name="Filenames",vartype="stringlist",desc_short="File names",desc_long="The filenames",property=None,defaultunits=None,choices=names)
		pboxes = ParamDef(name="Num boxes",vartype="intlist",desc_short="Boxes in DB",desc_long="The number of boxes stored for this image in the database",property=None,defaultunits=None,choices=nboxes)
		pdims = ParamDef(name="Dimensions",vartype="stringlist",desc_short="Dimensions",desc_long="The dimensions boxes",property=None,defaultunits=None,choices=dimensions)
		
		p = ParamTable(name="filenames",desc_short="Choose a subset of these images",desc_long="")
		p.append(pnames)
		p.append(pboxes)
		p.append(pdims)
		return p

class E2CTFWorkFlowTask(ParticleWorkFlowTask):
	'''
	Common functionality for E2CTF Work flow taskss
	'''
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)

	def get_ctf_param_table(self,project_names=None,no_particles=False):
		'''
		particle_files_names should be the return variable of self.get_particle_db_names(strip_ptcls=False), or get_ctf_project_names
		'''
		if project_names == None: # just left this here in case anyone is wandering what to do
			project_names = self.get_particle_db_names(strip_ptcls=False)
		
		defocus,dfdiff,dfang,bfactor,noise,snr = self.get_ctf_info(project_names)
		
		pnames = ParamDef(name="micrograph_ccd_filenames",vartype="stringlist",desc_short="File names",desc_long="The raw data from which particles will be extracted and ultimately refined to produce a reconstruction",property=None,defaultunits=None,choices=project_names)
		pdefocus = ParamDef(name="Defocus",vartype="stringlist",desc_short="Defocus",desc_long="Estimated defocus of the microscope",property=None,defaultunits=None,choices=defocus)
		pbfactor = ParamDef(name="Bfactor",vartype="stringlist",desc_short="B factor",desc_long="Estimated B factor of the microscope",property=None,defaultunits=None,choices=bfactor)
		pnoise = ParamDef(name="Noise",vartype="intlist",desc_short="Sampling",desc_long="The number of sample points used to generate the parameters and accompanying noise profile",property=None,defaultunits=None,choices=noise)
		psnr = ParamDef(name="SNR",vartype="intlist",desc_short="SNR",desc_long="The average SNR of the radial powever spectrum",property=None,defaultunits=None,choices=snr)
		
		num_phase,num_wiener,num_particles,phase_dims,wiener_dims,particle_dims = self.get_ctf_particle_info(project_names)
		pboxes = ParamDef(name="Num boxes",vartype="intlist",desc_short="Particles on disk",desc_long="The number of particles stored for this image in the database",property=None,defaultunits=None,choices=num_particles)
		pphase = ParamDef(name="Num phase",vartype="intlist",desc_short="Phase flipped",desc_long="The number of Wiener filter particles stored for this image in the database",property=None,defaultunits=None,choices=num_phase)
		pwiener = ParamDef(name="Num wiener",vartype="intlist",desc_short="Wien. filt",desc_long="The number of phase flipped particles stored for this image in the database",property=None,defaultunits=None,choices=num_wiener)
			
		pphasedim = ParamDef(name="phase dim",vartype="stringlist",desc_short="Phase ptcl dims",desc_long="The dimensions of the phase flipped images",property=None,defaultunits=None,choices=phase_dims)
		pwienerdim = ParamDef(name="wiener dim",vartype="stringlist",desc_short="Wiener ptcl dims",desc_long="The dimensions of the Wiener filtered images",property=None,defaultunits=None,choices=wiener_dims)
		pparticledim = ParamDef(name="particle dim",vartype="stringlist",desc_short="Particle dims",desc_long="The dimensions of the particle images",property=None,defaultunits=None,choices=particle_dims)
		
		#print len(num_phase),len(num_wiener),len(num_particles),len(phase_dims),len(wiener_dims),len(particle_dims)
		
		p = ParamTable(name="filenames",desc_short="Current CTF parameters",desc_long="")
		
		p.append(pnames)
		p.append(pdefocus)
		p.append(pbfactor)
		p.append(psnr)
		p.append(pnoise)
		if not no_particles: 
			p.append(pboxes)
			p.append(pparticledim)
			p.append(pphase)
			p.append(pphasedim)
			p.append(pwiener)
			p.append(pwienerdim)
			
		setattr(p,"convert_text", ptable_convert_3)
		setattr(p,"icon_type","matrix_image")
		
		
		return p,len(defocus)
	
	def get_ctf_info(self,project_names):
		if db_check_dict("bdb:e2ctf.parms"):
			defocus = []
			dfdiff = []
			dfang = []
			bfactor = []
			noise_profile=[]
			snrs = []
			ctf_db = db_open_dict("bdb:e2ctf.parms")
			for name in project_names:
				try:
					vals = ctf_db[name][0]
					ctf = EMAN2Ctf()
					ctf.from_string(vals)
					vals = ["%.3f" %ctf.defocus,"%.3f" %ctf.dfdiff,"%.3f" %ctf.dfang,"%.1f" %ctf.bfactor,len(ctf.background)]
					snr = 0
					try:
						snr = sum(ctf.snr)/len(ctf.snr)
					except:pass
					vals.append("%.3f" %snr)
 				except:
					vals = ["","","","",'',""]  # only need 6 at the moment

				defocus.append(vals[0])
				dfdiff.append(vals[1])
				dfang.append(vals[2])
				bfactor.append(vals[3])
				noise_profile.append(vals[4])
				snrs.append(vals[5])
				
			db_close_dict("bdb:e2ctf.parms")

			return defocus,dfdiff,dfang,bfactor,noise_profile,snrs
	
		else:
			dummy = ["" for i in range(len(project_names))]
			return dummy,dummy,dummy,dummy,dummy,dummy
	def get_ctf_particle_info(self,project_names):
		'''
		Returns three string lists containing entries correpsonding to the number of phase corrected, wiener correct, and regular particles in the database
		
		You could call this function with the names of the particle images in the bdb particles directory, i.e. all pariticle file names would
		look like
		img_001_ptcls
		img_003_ptcls
		And these would correspond to entries in the particles database, ie the following bdb entries would exist and contain particles
		bdb:particles#:img_001_ptcls
		bdb:particles#:img_003_ptcls
		
		But you might also call it with the filenames from the e2ctf.parms directory
		
		'''
		phase = []
		wiener = []
		particles = []
		
		phase_dims = []
		wiener_dims = []
		particle_dims = []
		
		for name in project_names:
			particle_db_name = "bdb:particles#"+name
			wiener_ptcl_db_name = particle_db_name + "_ctf_wiener"
			flip_ptcl_db_name = particle_db_name + "_ctf_flip"
			
			d = {}
			d[particle_db_name] = particles
			d[wiener_ptcl_db_name] = wiener
			d[flip_ptcl_db_name] = phase
			
			for db_name,data_list in d.items():
				if db_check_dict(db_name):
					particle_db = db_open_dict(db_name)
					if particle_db.has_key("maxrec"): 
						data_list.append(particle_db["maxrec"]+1)
					else: data_list.append("")
					db_close_dict(db_name)
				else: data_list.append("")
			
			d = {}
			d[particle_db_name] = particle_dims
			d[wiener_ptcl_db_name] = wiener_dims
			d[flip_ptcl_db_name] = phase_dims
			
			for db_name,data_list in d.items():
				if db_check_dict(db_name):
					particle_db = db_open_dict(db_name)
					try:
						hdr = particle_db.get_header(0)
						data_list.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
					except:
						data_list.append("")
				else: data_list.append("")
					
			
		
		return phase,wiener,particles,phase_dims,wiener_dims,particle_dims
		
	def get_ctf_project_names(self):
		'''
		Inspects the e2ctf.parms database for any images that have ctf parameters
		'''
		if db_check_dict("bdb:e2ctf.parms"):
			ctf_parms_db = db_open_dict("bdb:e2ctf.parms")
			vals = ctf_parms_db.keys()
			#print vals
			if vals == None: vals = []
			db_close_dict("bdb:e2ctf.parms")
			return vals
		else:
			return []
		
	def get_project_particle_names_with_ctf(self):
		'''
		Get the names of particles in the project db that also have an entry in the e2ctf.parms db
		This is useful for the E2CTFGui and Output task
		'''
		
		ptcl_names = self.get_particle_db_names(strip_ptcls=False) # particles in the project directory
		ctf_names = self.get_names_with_ctf_params()
		ctf_ptcl_names = [l[0] for l in ctf_names]
		
		interactable_names = []
		for name in ptcl_names:
			if name in ctf_ptcl_names:
				interactable_names.append(name)
				
		return interactable_names
		
	def get_names_with_ctf_params(self):
		'''
		opens the e2ctf.parms directory and returns all a list of lists like this:
		[[db_name_key, real_image_name],....]
		eg
		[[neg_001,neg_001.hdf],[ptcls_01,bdb:particles#ptcls_01_ptcls],...] etc
		e2ctf is responsible for making sure the last data entry for each image is the original image name (this was first enforced by d.woolford)
		'''
		parms_db = db_open_dict("bdb:e2ctf.parms")
		
		ret = []
		for key,data in parms_db.items():
			ret.append([key,data[-1]]) # parms[-1] should be the original filename
				
		return ret

class CTFReportTask(E2CTFWorkFlowTask):
	
	documentation_string = "This tool is for displaying the currently determined CTF parameters for the particles associated with the project. It also displays the number of phase flipped and/or wiener filtered images corresponding to each particle set."
	warning_string = "\n\n\nNOTE: There are no particles currently associated with the project. Please go to the \"Particles\" task and import/box particles first."
	def __init__(self,application):
		E2CTFWorkFlowTask.__init__(self,application)
		self.window_title = "Particle CTF parameters"

	def get_params(self):
		params = []
		p,n = self.get_ctf_param_table(None)
		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=CTFReportTask.documentation_string+CTFReportTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=CTFReportTask.documentation_string,choices=None))
			params.append(p)
		return params

	def write_db_entry(self,key,value):
		pass
		
class E2CTFGenericTask(ParticleWorkFlowTask):
	documentation_string = "Fill me in"
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "e2ctf"
		self.preferred_size = (480,200)
		
		
	def get_params(self):
		params = []		
#		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGenericTask.documentation_string,choices=None))
		
		params.append(ParamDef(name="running_mode",vartype="choice",desc_short="Choose your running mode",desc_long="There are three CTF related task which are generally run in order",property=None,defaultunits="auto",choices=["auto params", "interactively fine tune", "write output"]))
		
		return params

	def on_form_ok(self,params):
		if params["running_mode"] == "auto params":
			self.emit(QtCore.SIGNAL("replace_task"),E2CTFAutoFitTaskGeneral,"ctf auto fit")
			self.form.closeEvent(None)
			self.form = None
		elif params["running_mode"] == "interactively fine tune":
			self.emit(QtCore.SIGNAL("replace_task"),E2CTFGuiTaskGeneral,"fine tune ctf")
			self.form.closeEvent(None)
			self.form = None
		elif params["running_mode"] == "write output":
			self.emit(QtCore.SIGNAL("replace_task"),E2CTFOutputTaskGeneral,"ctf output")
			self.form.closeEvent(None)
			self.form = None	
		else:
			self.form.closeEvent(None)
			self.form = None
			self.emit(QtCore.SIGNAL("task_idle"))
			
	def write_db_entry(self,key,value):
		pass

class E2CTFAutoFitTask(E2CTFWorkFlowTask):	
	documentation_string = "Select the particles you wish to generate CTF parameters for, enter the appropriate parameters such as microscope voltage etc, and hit OK.\nThis will cause the workflow to spawn processes based on the available CPUs. Once finished the automatically determined CTF parameters will be stored in the EMAN2 database."
	warning_string = "\n\n\nNOTE: There are no particles currently associated with the project. Please go to the \"Particles\" task and import/box particles first."

	def __init__(self,application):
		E2CTFWorkFlowTask.__init__(self,application)
		self.window_title = "e2ctf auto fitting"

	def get_params(self):
		params = []
		p,n= self.get_ctf_param_table(self.get_particle_db_names(strip_ptcls=False),no_particles=True)
		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFAutoFitTask.documentation_string+E2CTFAutoFitTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFAutoFitTask.documentation_string,choices=None))
			params.append(p)
			self.add_general_params(params)

		return params
	
	def add_general_params(self,params):
		project_db = db_open_dict("bdb:project")
		ctf_misc_db = db_open_dict("bdb:e2ctf.misc")
		papix = ParamDef(name="global.apix",vartype="float",desc_short="A/pix for project",desc_long="The physical distance represented by the pixel spacing",property=None,defaultunits=project_db.get("global.apix",dfl=1.1),choices=None)
		pvolt = ParamDef(name="global.microscope_voltage",vartype="float",desc_short="Microscope voltage",desc_long="The operating voltage of the microscope in kilo volts",property=None,defaultunits=project_db.get("global.microscope_voltage",dfl=300),choices=None)
		pcs = ParamDef(name="global.microscope_cs",vartype="float",desc_short="Microscope Cs",desc_long="Microscope spherical aberration constant",property=None,defaultunits=project_db.get("global.microscope_cs",dfl=2.0),choices=None)
		pac = ParamDef(name="working_ac",vartype="float",desc_short="Amplitude contrast",desc_long="The amplitude contrast constant. It is recommended that this value is identical in all of your images.",property=None,defaultunits=ctf_misc_db.get("working_ac",dfl=10),choices=None)
		pos = ParamDef(name="working_oversamp",vartype="int",desc_short="Oversampling",desc_long="If greater than 1, oversampling by this amount will be used when images are being phase flipped and Wiener filtered.",property=None,defaultunits=ctf_misc_db.get("working_oversamp",dfl=1),choices=None)
		pncp = ParamDef(name="global.num_cpus",vartype="int",desc_short="Number of CPUs",desc_long="Number of CPUS available for the project to use",property=None,defaultunits=project_db.get("global.num_cpus",dfl=num_cpus()),choices=None)
		pahp = ParamDef(name="autohp",vartype="boolean",desc_short="Auto high pass",desc_long="Automatic high pass filter of the SNR only to remove initial sharp peak, phase-flipped data is not directly affected (default false)",property=None,defaultunits=False,choices=None)
		pns = ParamDef(name="nosmooth",vartype="boolean",desc_short="No smoothing",desc_long="Disable smoothing of the background (running-average of the log with adjustment at the zeroes of the CTF)",property=None,defaultunits=False,choices=None)
		
		
		mem = memory_stats()
		
		params.append([papix,pvolt])
		params.append([pcs,pac])
		params.append([pos,pncp])
		params.append([pahp,pns])

		db_close_dict("bdb:project")
	
	def get_default_ctf_options(self,params):
		'''
		These are the options required to run pspec_and_ctf_fit in e2ctf.py
		'''
		
		error_message = []
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return None
		
		filenames = params["filenames"]
		
		boxsize = None
		db_file_names = []
		for i,name in enumerate(filenames):
			db_name="bdb:particles#"+name
			db_file_names.append(db_name)
			if not db_check_dict(db_name):
				error_message.append("error, can't particle entry doesn't exist for %s." %name)
			
			if boxsize == None:
				db = db_open_dict(db_name)
				hdr = db.get_header(0)
				boxsize = hdr["nx"] # no consideration is given for non square images
				db_close_dict(db_name)
			else:
				db = db_open_dict(db_name)
				hdr = db.get_header(0)
				db_close_dict(db_name)
				if boxsize != hdr["nx"]: # no consideration is given for non square images
					error_message.append("Can't run e2ctf on images with different box sizes.")
		
		if boxsize == None or boxsize < 2:
			error_message.append("error, boxsize is less than 2.")
		
		
		options = EmptyObject()
		options.bgmask = boxsize/2
		options.filenames = db_file_names
		error_message.extend(self.append_general_options(options,params))
		
		if len(error_message) > 0:
			self.show_error_message(error_message)
			return None
	
		return options
	
	def append_general_options(self,options,params):
		'''
		This is done in more than one place hence this function
		'''
		
		options.nosmooth = params["nosmooth"]
		options.nonorm = False
		options.autohp = params["autohp"]
		options.invert = False
		options.oversamp = params["working_oversamp"]
		options.ac = params["working_ac"]
		options.apix = params["global.apix"]
		options.cs = params["global.microscope_cs"]
		options.voltage = params["global.microscope_voltage"]
		
		
		error_message = []
		if options.oversamp < 1:
			error_message.append("You must specify a value for oversamp that is atleast 1.")
		if options.apix <= 0:
			error_message.append("You must specify a positive non zero value for the apix.")
		if options.voltage <= 0:
			error_message.append("You must specify a positive non zero value for the voltage.")
		
		return error_message
		
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)
		
		options = self.get_default_ctf_options(params)
		if options != None:
			
			string_args = ["bgmask","oversamp","ac","apix","cs","voltage"]
			bool_args = ["nosmooth","nonorm","autohp","invert"]
			additional_args = ["--auto_fit"]
			temp_file_name = "e2ctf_autofit_stdout.txt"
			self.spawn_task("e2ctf.py",options,string_args,bool_args,additional_args,temp_file_name)
			
			self.form.closeEvent(None)
			self.emit(QtCore.SIGNAL("task_idle"))
			
		else:
			return
		
	def on_form_close(self):
		# this is to avoid a task_idle signal, which would be incorrect if e2boxer is running
		self.emit(QtCore.SIGNAL("task_idle"))

	def write_db_entry(self,key,value):
		if key == "working_ac":
			ctf_misc_db = db_open_dict("bdb:e2ctf.misc")
			ctf_misc_db["working_ac"] = value
			db_close_dict("bdb:e2ctf.misc")
		elif key == "working_oversamp":
			ctf_misc_db = db_open_dict("bdb:e2ctf.misc")
			ctf_misc_db["working_oversamp"] = value
			db_close_dict("bdb:e2ctf.misc")
		else:
			# there are some general parameters that need writing:
			WorkFlowTask.write_db_entry(self,key,value)
			
class E2CTFAutoFitTaskGeneral(E2CTFAutoFitTask):
	'''
	This one has a generic url browser to get the input file names as opposed to the more rigid project based one
	'''
	documentation_string = "Use this tool to use e2ctf to generate ctf parameters for the particles located anywhere on disk. Use the browse buttons to locate the files on disk, enter the fitting parameters such as microscope voltage and angstrom per pixel, and hit OK. \nThis will cause the workflow to spawn processes based on the available CPUs. Once finished the automatically determined CTF parameters will be stored in the EMAN2 database."
	
	def __init__(self,application):
		E2CTFAutoFitTask.__init__(self,application)
		self.window_title = "e2ctf auto fitting"
		self.file_check = True
	def get_params(self):
		params = []		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFAutoFitTask.documentation_string,choices=None))
		
		params.append(ParamDef(name="filenames",vartype="url",desc_short="File names",desc_long="The names of the particle files you want to generate automated ctf parameters for",property=None,defaultunits=[],choices=[]))
		
		self.add_general_params(params)

		return params
	
	def get_default_ctf_options(self,params):
		'''
		These are the options required to run pspec_and_ctf_fit in e2ctf.py
		'''
		
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			return None # this is fine
		
		filenames = params["filenames"]
		fine,message = check_files_are_em_images(filenames)
		
		if not fine:
			print message
			return None
		
		boxsize = None
		db_file_names = []
		for i,name in enumerate(filenames):
			a = EMData()
			a.read_image(name,0,True)
			if boxsize == None:
				boxsize = a.get_attr("nx") # no consideration is given for non square images
			elif boxsize != a.get_attr("nx"): # no consideration is given for non square images
					print "error, can't run e2ctf on images with different box sizes." # Specifically, I can not deduce the bgmask option for the group"
					return None
		
		if boxsize == None or boxsize < 2:
			print "error, boxsize is less than 2"
			return None
		
		options = EmptyObject()
		options.bgmask = boxsize/2
		options.filenames = filenames
		self.append_general_options(options,params)
		return options

class E2CTFOutputTask(E2CTFWorkFlowTask):	
	documentation_string = "Select the particle data for which you wish to generate phase flipped and/or Wiener filtered output and hit OK.\nThis will cause the workflow to spawn processes based on the available CPUs that write the output into a predefined location in the EMAN2 database.\nNote that the Wiener filtered output images are also phase flipped."
	warning_string = "\n\n\nNOTE: There are no particles associated with the project and/or there are no previously generated CTF parameters for these particles. To establish project particles go to the \"Particles\" task. To generate CTF parameters go to the \"Automated fitting - e2ctf\" task" 
	def __init__(self,application):
		E2CTFWorkFlowTask.__init__(self,application)
		self.window_title = "e2ctf output"

	def get_params(self):
		params = []		
		
		p,n = self.get_ctf_param_table(self.get_project_particle_names_with_ctf())
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFOutputTask.documentation_string+E2CTFOutputTask.warning_string,choices=None))
		else:
			ctf_misc_db = db_open_dict("bdb:e2ctf.misc")
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFOutputTask.documentation_string,choices=None))
			params.append(p)
			pos = ParamDef(name="working_oversamp",vartype="int",desc_short="Oversampling",desc_long="If greater than 1, oversampling by this amount will be used when images are being phase flipped and Wiener filtered.",property=None,defaultunits=ctf_misc_db.get("working_oversamp",dfl=1),choices=None)
			pwiener = ParamDef(name="wiener",vartype="boolean",desc_short="Wiener",desc_long="Wiener filter your particle images using parameters in the database. Phase flipping will also occur",property=None,defaultunits=False,choices=None)
			pphase = ParamDef(name="phaseflip",vartype="boolean",desc_short="Phase flip",desc_long="Phase flip your particle images using parameters in the database",property=None,defaultunits=False,choices=None)
			params.append(pos)
			params.append([pphase,pwiener])
		return params

	def get_default_ctf_options(self,params):
		'''
		These are the options required to run pspec_and_ctf_fit in e2ctf.py, works in e2workflow
		'''
		
		error_message = []
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			error_message.append("Please select files to process")
		
		
		options = EmptyObject()
	
		filenames = params["filenames"]
#
		db_file_names = []
		for i,name in enumerate(filenames):
			db_name="bdb:particles#"+name
			db_file_names.append(db_name)
			if not db_check_dict(db_name):
				print "error, particle entry doesn't exist for",name,"aborting."
				return None
			
		options.filenames = db_file_names
		options.wiener = params["wiener"]
		options.phaseflip = params["phaseflip"]
		options.oversamp = params["working_oversamp"]
		if not options.wiener and not options.phaseflip:
			error_message.append("Please choose at atleast one of the phaseflip or Wiener options.")
			
		if options.oversamp < 1:
			error_message.append("The oversampling factor must be atleast 1")
			
		if len(error_message) > 0:
			self.show_error_message(error_message)
			return None
#		
		return options
	
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)

		options = self.get_default_ctf_options(params)
		if options != None and len(options.filenames) > 0 and (options.wiener or options.phaseflip):

			string_args = []
			bool_args = ["wiener","phaseflip"]
			additional_args = []
			temp_file_name = "e2ctf_output_stdout.txt"
			self.spawn_task("e2ctf.py",options,string_args,bool_args,additional_args,temp_file_name)
			

			self.form.closeEvent(None)
			self.emit(QtCore.SIGNAL("task_idle"))
		else:
			return
	
	def on_ctf_closed(self):
		self.emit(QtCore.SIGNAL("gui_exit")) #
		
	def on_form_close(self):
		# this is to avoid a task_idle signal, which would be incorrect if e2boxer is running
		self.emit(QtCore.SIGNAL("task_idle"))

class E2CTFOutputTaskGeneral(E2CTFOutputTask):
	''' This one uses the names in the e2ctf.parms to generate it's table of options, not the particles in the particles directory
	'''
	warning_string = "\n\n\nNOTE: There are no CTF parameters currently stored for any images in the local database. You can change this by running automated fitting with e2ctf."
	
	def __init__(self,application):
		E2CTFOutputTask.__init__(self,application)
		self.window_title = "e2ctf output"

	def get_params(self):
		params = []
		names = self.get_names_with_ctf_params()
		n = [l[0] for l in names]
		p,num = self.get_ctf_param_table(n)
		
		if num == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFOutputTask.documentation_string+E2CTFOutputTaskGeneral.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFOutputTask.documentation_string,choices=None))
			params.append(p)
			pwiener = ParamDef(name="wiener",vartype="boolean",desc_short="Wiener",desc_long="Wiener filter your particle images using parameters in the database. Phase flipping will also occur",property=None,defaultunits=False,choices=None)
			pphase = ParamDef(name="phaseflip",vartype="boolean",desc_short="Phase flip",desc_long="Phase flip your particle images using parameters in the database",property=None,defaultunits=False,choices=None)
		
			params.append([pphase,pwiener])
			
		return params
	
	def get_ctf_options(self,params):
		'''
		This is a way to get the ctf optiosn if one is using the "alternate" path, which means just in the context of general use of e2ctf (not the workflow)
		'''
		options = EmptyObject()
		
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			return None # this is fine, for example, there were no files to work

		selected_filenames = params["filenames"]
		
		filenames = []
		names = self.get_names_with_ctf_params()
		for name in names:
			if name[0] in selected_filenames:
				filenames.append(name[1])
		options.filenames = filenames

		options.wiener = params["wiener"]
		options.phaseflip = params["phaseflip"]
#		
		return options

	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)

		options = self.get_ctf_options(params)
		if options != None and len(options.filenames) > 0 and (options.wiener or options.phaseflip):
			
			string_args = []
			bool_args = ["wiener","phaseflip"]
			additional_args = []
			temp_file_name = "e2ctf_output_stdout.txt"
			self.spawn_task("e2ctf.py",options,string_args,bool_args,additional_args,temp_file_name)
			

			self.form.closeEvent(None)
			self.emit(QtCore.SIGNAL("task_idle"))
		else:
			self.form.closeEvent(None)
			self.emit(QtCore.SIGNAL("task_idle"))
	
class E2CTFGuiTask(E2CTFWorkFlowTask):	
	documentation_string = "Select the particle data you wish to evaluate/tweak in the e2ctf interactive interface and hit OK. This will launch e2ctf and the selected images will automatically be loaded for viewing. Once inside the e2ctf interface you can save your tweaked parameters to the database using the Save button."
	warning_string = "\n\n\nNOTE: There are no particles associated with the project and/or there are no previously generated CTF parameters for these particles. To establish project particles go to the \"Particles\" task. To generate CTF parameters go to the \"Automated fitting - e2ctf\" task" 
	def __init__(self,application):
		E2CTFWorkFlowTask.__init__(self,application)
		self.window_title = "e2ctf interface"
		self.gui = None # will eventually be a e2ctf gui

	def get_params(self):

		ptcl_names = self.get_particle_db_names(strip_ptcls=False) # particles in the project directory
		ctf_names = self.get_names_with_ctf_params()
		ctf_ptcl_names = [l[0] for l in ctf_names]
		
		p,n = self.get_ctf_param_table(self.get_project_particle_names_with_ctf(),no_particles=True)
		
		params = []		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGuiTask.documentation_string+E2CTFGuiTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGuiTask.documentation_string,choices=None))
		  	params.append(p)
		return params
	
	def get_default_ctf_options(self,params):
		'''
		These are the options required to run pspec_and_ctf_fit in e2ctf.py
		'''
		
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return None

		options = EmptyObject()
		filenames = params["filenames"]
#
		db_file_names = []
		for i,name in enumerate(filenames):
			db_name="bdb:particles#"+name
			db_file_names.append(db_name)
			if not db_check_dict(db_name):
				print "No project particles entry exists for",name,"aborting."
				return None
		options.filenames = db_file_names
#		
		return options

	
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)

		options = self.get_default_ctf_options(params)
		if options != None and len(options.filenames) > 0:
			
			img_sets = get_gui_arg_img_sets(options.filenames)
		
			
			self.gui=GUIctfModule(self.application(),img_sets)
			self.emit(QtCore.SIGNAL("gui_running"), "CTF", self.gui) # so the desktop can prepare some space!
			self.form.closeEvent(None)
			QtCore.QObject.connect(self.gui,QtCore.SIGNAL("module_closed"), self.on_ctf_closed)
			self.gui.show_guis()
		else:
			return
	
	def on_ctf_closed(self):
		if self.gui != None:
			self.gui = None
			self.emit(QtCore.SIGNAL("gui_exit")) #
		
	def on_form_close(self):
		# this is to avoid a task_idle signal, which would be incorrect if e2boxer is running
		if self.gui == None:
			self.emit(QtCore.SIGNAL("task_idle"))
		else: pass
		
class E2CTFGuiTaskGeneral(E2CTFGuiTask):
	''' This one uses the names in the e2ctf.parms to generate it's table of options, not the particles in the particles directory
	'''
	warning_string = "\n\n\nNOTE: There are there are no previously generated CTF parameters. Please run automated fitting using e2ctf first." 
	
	documentation_string = "Write me"
	def __init__(self,application):
		E2CTFGuiTask.__init__(self,application)

	def get_params(self):
		params = []		
		
		names = self.get_names_with_ctf_params()
		n = [l[0] for l in names]
		p,num = self.get_ctf_param_table(n)
		
		if num == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGuiTask.documentation_string+E2CTFGuiTaskGeneral.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2CTFGuiTaskGeneral.documentation_string,choices=None))
			params.append(p)
		return params
	
	def get_default_ctf_options(self,params):
		'''
		These are the options required to run pspec_and_ctf_fit in e2ctf.py
		'''
		
		
		
		if  params.has_key("filenames") and len(params["filenames"]) == 0:
			self.run_select_files_msg()
			return None # this is fine
		
		
		options = EmptyObject()

		selected_filenames = params["filenames"]
		
		filenames = []
		names = self.get_names_with_ctf_params()
		for name in names:
			if name[0] in selected_filenames:
				filenames.append(name[1])
		options.filenames = filenames
#		
		return options


class E2Refine2DReportTask(ParticleWorkFlowTask):
	documentation_string = "This form displays the current sets of reference free class averages that have been generated by 2D refinement processess."
	warning_string = "\n\n\nNote: There are no reference free class averages currently associated with the project. Try running e2refine2d in the options below."
	
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Refine 2D class averages "
		
		
	def get_params(self):
		params = []		
		
		p,n = self.get_reference_free_class_averages_table()
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2Refine2DReportTask.documentation_string+E2Refine2DReportTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2Refine2DReportTask.documentation_string,choices=None))
			params.append(p)
		return params
			
	def write_db_entry(self,key,value):
		pass
	
#	def get_reference_free_class_averages_table(self):
#		'''
#		Looks for bdb:r2d_??#classes_?? and the bdb:r2d_??#classes_init file, finds the most recent one, then fills in the number of particles in
#		in the class average file and also its dimensions.
#		'''
#
#		class_files,class_ptcls,class_dims = self.get_latest_r2d_classes()
#					
#		if len(class_files) > 0:
#			
#			p = ParamTable(name="filenames",desc_short="Most current reference free class averages",desc_long="")
#			pclassnames = ParamDef(name="Files names",vartype="intlist",desc_short="Class avarerage file",desc_long="The location of the class average files",property=None,defaultunits=None,choices=class_files)
#			pptcls = ParamDef(name="Class averages",vartype="intlist",desc_short="Total class averages",desc_long="The number class averages in the nominated file",property=None,defaultunits=None,choices=class_ptcls)
#			pdims = ParamDef(name="Particle dimensions",vartype="stringlist",desc_short="Dimensions",desc_long="The dimensions of the images in the class averages file",property=None,defaultunits=None,choices=class_dims)
#			
#			p.append(pclassnames)
#			p.append(pptcls)
#			p.append(pdims)
#			
#			setattr(p,"convert_text", ptable_convert_2)
#			setattr(p,"icon_type","matrix_image")
#			
#			return p,len(class_files)
#		else:
#			return None,0
			

	
class E2Refine2DTask(ParticleWorkFlowTask):
	'''
	Common e2refine2D functionality
	'''
	documentation_string = "This form is a way for the user to supply arguments to and execute e2refine2d.py"
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Run e2refine2d"		
		
	def get_general_params(self):
		params = []		
		piter = ParamDef(name="iter",vartype="int",desc_short="Refinement iterations",desc_long="The number of times the e2refine2d svd-based class averaging procedure is iterated",property=None,defaultunits=5,choices=[])
		piterclassav = ParamDef(name="iterclassav",vartype="int",desc_short="Class averaging iterations",desc_long="The number of iterative class average steps that occur in e2classaverage",property=None,defaultunits=2,choices=[])
		pnaliref = ParamDef(name="naliref",vartype="int",desc_short="# alignment references",desc_long="The number of alignment references to use when determining particle orientations",property=None,defaultunits=8,choices=[])
		pnbasisfp = ParamDef(name="nbasisfp",vartype="int",desc_short="# basis fp",desc_long="The number of MSA basis vectors to use when classifying",property=None,defaultunits=5,choices=[])
		pncls = ParamDef(name="ncls",vartype="int",desc_short="# classes",desc_long="The number of classes to produce",property=None,defaultunits=32,choices=[])

	   	aligners = self.get_aligners_list()
#		aligners.append("None") I think this is necessary
		cmps = self.get_cmps_list()
#		cmps.append("None") I think this is necessary
		
		aligners.sort()
		cmps.sort()
		
		pshrink = ParamDef(name="shrink",vartype="int",desc_short="Shrink factor",desc_long="The the downsampling rate used to shrink the data",property=None,defaultunits=4,choices=[])
		
		
		pcmp  =  ParamDef(name="simcmp",vartype="string",desc_short="Main comparator",desc_long="The comparator to determine the final quality metric",defaultunits="frc",choices=cmps)
		pcmpargs =  ParamDef(name="simcmpargs",vartype="string",desc_short="params",desc_long="Parameters for the this comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	

		
		psimalign =  ParamDef(name="simalign",vartype="string",desc_short="Aligner",desc_long="The aligner being used",property=None,defaultunits="rotate_translate_flip",choices=aligners)
		psimalignargs =  ParamDef(name="simalignargs",vartype="string",desc_short="params",desc_long="Parameters for the aligner, see \"e2help.py aligners\"",property=None,defaultunits="",choices=[])
		
		psimaligncmp =  ParamDef(name="simaligncmp",vartype="string",desc_short="comparator",desc_long="The comparator being used",property=None,defaultunits="frc",choices=cmps)
		psimaligncmpsargs =  ParamDef(name="simaligncmpargs",vartype="string",desc_short="params",desc_long="Parameters for the comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	
		
		
		prsimalign =  ParamDef(name="simralign",vartype="string",desc_short="Refine aligner",desc_long="The refine aligner being used",property=None,defaultunits="None",choices=["None","refine"])
		prsimalignargs =  ParamDef(name="simralignargs",vartype="string",desc_short="params",desc_long="Parameters for the aligner, see \"e2help.py aligners\"",property=None,defaultunits="",choices=[])
		
		prsimaligncmp =  ParamDef(name="simraligncmp",vartype="string",desc_short="Refine comparator",desc_long="The comparator being used for refine alignment",property=None,defaultunits="frc",choices=cmps)
		prsimaligncmpsargs =  ParamDef(name="simraligncmpargs",vartype="string",desc_short="params",desc_long="Parameters for the comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	
		
		pnp = ParamDef(name="normproj",vartype="boolean",desc_short="Normalize projection vectors",desc_long="Normalizes each projected vector into the MSA subspace",property=None,defaultunits=False,choices=None)
		
		project_db = db_open_dict("bdb:project")
		pncp = ParamDef(name="parallel",vartype="int",desc_short="Number of CPUs",desc_long="Number of CPUS available for e2refine2d to use",property=None,defaultunits=project_db.get("global.num_cpus",dfl=num_cpus()),choices=None)
		pinitclasses =  ParamDef(name="initial",vartype="string",desc_short="Initial class averages",desc_long="A file (full path) containing starting class averages. If note specificed will generate starting class averages automatically.",property=None,defaultunits="",choices=[])	
		
		
		params.append(pncls)
		params.append([pshrink,pnp])
		params.append([piter,piterclassav])
		params.append([pnaliref,pnbasisfp])
		params.append([pcmp,pcmpargs])
		params.append([psimalign,psimalignargs])
		params.append([psimaligncmp,psimaligncmpsargs])
		params.append([prsimalign,prsimalignargs])
		params.append([prsimaligncmp,prsimaligncmpsargs])
		params.append([pncp,pinitclasses])
		
		return params
			
	def write_db_entry(self,key,value):
		pass
	
	def get_parms(self,params):
		mesbox = QtGui.QMessageBox()
		mesbox.setWindowTitle("Almost but not quite")
		
		options = EmptyObject()
		for k,v in params.items():
			setattr(options,k,v)
		
		if options.initial == "" or str(options.initial) == "None" or str(options.initial) == "none":
			options.initial = None
		
		vals = []
		vals.append(["simcmp","simcmpargs"])
		vals.append(["simalign","simalignargs"])
		vals.append(["simralign","simralignargs"])
		vals.append(["simaligncmp","simaligncmpargs"])
		vals.append(["simraligncmp","simraligncmpargs"])
		
		for v in vals:
			if getattr(options,v[0]) == "None": setattr(options,v[0],None)
			elif len(getattr(options,v[1])) != 0: setattr(options,v[0],getattr(options,v[0])+":"+getattr(options,v[1]))
		
		error_message = []
		if len(options.filenames) == 0: # this is the specialized part - the workflow creates starting data sets from a list of filenames
			error_message.append("Please choose the file(s) that you want to use as as input data for e2refine2d.")

		
		from e2refine2d import check_e2refin2d_args
		
		error_message.extend(check_e2refin2d_args(options))
		
 		if len(error_message) != 0:
 			self.show_error_message(error_message)
	 		return None
	 	
	 	# if we make it here we are almost definitely good to go, the only thing that can fail is the e2bdb or e2proc2d commands
	 	options.path = numbered_path("r2d",True)
	 	bdb_success, bdb_cmd = self.make_v_stack(options)
	 	if bdb_success:
	 		if options.shrink > 1:
	 			cmd = "e2proc2d.py"
	 			cmd += " bdb:"+options.path+"#all"
	 			options.input =  "bdb:"+options.path+"#all"+str(options.shrink)
	 			cmd += " "+options.input
	 			cmd += " --process=math.meanshrink:n="+str(options.shrink)
	 			
	 			self.application().setOverrideCursor(Qt.BusyCursor)
	 			success = (os.system(cmd) in (0,12))
	 			self.application().setOverrideCursor(Qt.ArrowCursor)
	 			
	 			if not success:
	 				mesbox.setText("e2proc2d.py shrinking command failed. This command was\n" + cmd +"\nTry again please. If the failure occurs a second time please contact developers.")
	 			   	mesbox.exec_()
	 				return None
	 		else: options.input =  "bdb:"+options.path+"#all"
	 		
	 		options.filenames = [] # this is so spawn_task doesn't supply args to e2refine2d.py
	 		return options # THIS IS IT, THE POINT OF SUCCESS - returning this means e2refine2d.py is good to go using the given parameters
	 	else:
	 		mesbox.setText("e2bdb.py command failed. The command was\n" + bdb_cmd +"\nTry again please. If the failure occurs a second time please contact developers")
	 		mesbox.exec_()
	 		return None 
	 		  
	def make_v_stack(self,options):
	 	
	 	cmd = "e2bdb.py"
	 	for name in options.filenames:
	 		cmd += " "+name
	 	
	 	cmd += " --makevstack=bdb:"+options.path+"#all"
	 	
	 	self.application().setOverrideCursor(Qt.BusyCursor)
	 	success = os.system(cmd)
		print "mvs ",success
		success = (success in (0,12))
	 	self.application().setOverrideCursor(Qt.ArrowCursor)
	 	return success,cmd
	 
	def run_e2refine2d(self,options):
		
		
		string_args = ["iter","iterclassav","naliref","nbasisfp","path","input","parallel"]
		bool_args = ["normproj"]
		optionals = ["simalign","simaligncmp","simralign","simraligncmp","simcmp","initial"]
		for opt in optionals:
			if getattr(options,opt) != None: string_args.append(opt)
			
		additional_args = []
		temp_file_name = "e2refine2d_stdout.txt"
		self.spawn_single_task("e2refine2d.py",options,string_args,bool_args,additional_args,temp_file_name)
		self.emit(QtCore.SIGNAL("task_idle"))
		self.form.closeEvent(None)
		self.form = None
		
 		 	
class E2Refine2DChooseDataTask(ParticleWorkFlowTask):
	documentation_string = "Choose the data you wish to use for use for running e2refine2d from the list of options below and hit OK. This will pop up a second form asking you to fill in more details.\n\nNote that usually you should have 4 options to choose from below. If you are not seeing all 4 options it means you should go back in the work flow, import particles, and generate phase flipped and Wiener filtered output." 
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "e2refine2d - getting starting"
		self.preferred_size = (480,300)
		
	def get_params(self):
		params = []		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2Refine2DChooseDataTask.documentation_string,choices=None))
		
		
		n1 = self.get_total_particles(tag="_ptcls")
		n2 = self.get_total_particles(tag="_ptcls_ctf_flip")
		n3 = self.get_total_particles(tag="_ptcls_ctf_wiener")
		
		choices = []
		if n1 > 0:
			choices.append("Particles ("+str(n1)+")")
		if n2 > 0:
			choices.append("Phase flipped ptcls ("+str(n2)+")")
		if n3 > 0:
			choices.append("Wiener ptcls ("+str(n3)+")")
			
		choices.append("Specify files")
		
		
		params.append(ParamDef(name="particle_set_choice",vartype="choice",desc_long="Choose the particle data set you wish to use to generate a starting data for e2refine2d",desc_short="Choose data",property=None,defaultunits=None,choices=choices))
			
		return params
	
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)

		choice = params["particle_set_choice"]
		
		if choice[:9] == "Particles":
			self.emit(QtCore.SIGNAL("replace_task"),E2Refine2DRunTask,"e2refine2d options")
			self.form.closeEvent(None)
			self.form = None
		elif choice[:5] == "Phase":
			self.emit(QtCore.SIGNAL("replace_task"),E2Refine2DWithPhasePtclsTask,"e2refine2d options")
			self.form.closeEvent(None)
			self.form = None
		elif choice[:6] == "Wiener":
			self.emit(QtCore.SIGNAL("replace_task"),E2Refine2DWithWienPtclsTask,"e2refine2d options")
			self.form.closeEvent(None)
			self.form = None
		elif choice == "Specify files":
			self.emit(QtCore.SIGNAL("replace_task"),E2Refine2DWithGenericTask,"e2refine2d options")
			self.form.closeEvent(None)
			self.form = None
		else:
			print "the code has changed since the original author wrote it, something is wrong!!"

	
			
	def write_db_entry(self,key,value):
		pass

class E2Refine2DRunTask(E2Refine2DTask):
	documentation_string = "Choose which files you want to be part of the input data set, enter the appropriate e2refine2d input parameters, and hit OK. This will cause the workflow to spawn e2refine2d in a separate process. Output data will automatically be stored in the EMAN2 database."
	def __init__(self,application):
		E2Refine2DTask.__init__(self,application)
		self.window_title = "run e2refine2d"
		self.end_tag = "_ptcls"
	def get_params(self):
		params = []
		
		if self.end_tag != "generic":
			p,n = self.get_particle_selection_table(tag=self.end_tag)
		else:
			p = ParamDef(name="filenames",vartype="url",desc_short="Input file name(s)",desc_long="The names of the particle files you want to use as in the input data for e2refine2d.py",property=None,defaultunits=[],choices=[])
			n = 1 # just to fool the next bit, that's all
			
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2Refine2DRunTask.documentation_string+E2Refine2DRunTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2Refine2DRunTask.documentation_string,choices=None))
			params.append(p)  
			
		other_params = self.get_general_params()
		
		params.extend(other_params)
		return params

	def on_form_ok(self,params):
		
		if self.end_tag != "generic":
			names = ["bdb:particles#"+name for name in params["filenames"]]
			params["filenames"] = names 
		options = self.get_parms(params)
		
		if options == None:
			return
		
		else:
			for k,v in params.items():
				self.write_db_entry(k,v)
			
			self.run_e2refine2d(options) # this does everything, even close the form
			
		
	def write_db_entry(self,key,value):
		pass

class E2Refine2DWithPhasePtclsTask(E2Refine2DRunTask):
	def __init__(self,application):
		E2Refine2DRunTask.__init__(self,application)
		self.end_tag = "_ptcls_ctf_flip"
		
class E2Refine2DWithWienPtclsTask(E2Refine2DRunTask):
	def __init__(self,application):
		E2Refine2DRunTask.__init__(self,application)
		self.end_tag = "_ptcls_ctf_wiener"
		
class E2Refine2DWithGenericTask(E2Refine2DRunTask):
	def __init__(self,application):
		E2Refine2DRunTask.__init__(self,application)
		self.end_tag = "generic"


class InitialModelReportTask(ParticleWorkFlowTask):
	documentation_string = "This form displays the initial models currently associated with the project. You can associate initial models with the project using e2makeinitialmodel or by importing them directly, see the options below."
	warning_string = "\n\n\nNOTE: There are no initial models currently associated with the project."
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Project initial models"
	
	def get_params(self):
		params = []
		
		p,n = self.get_initial_models_table()
		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=InitialModelReportTask.documentation_string+InitialModelReportTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=InitialModelReportTask.documentation_string,choices=None))
			params.append(p)
		return params
	
	def get_initial_models_table(self):
		
		db = "bdb:initial_models#"
		names = []
		quality = []
		dims = []
		mean = [] # just for fun
		sigma = [] # just for fun
		max = []
		min = []
		for d in db_list_dicts("bdb:initial_models#"):
			if len(d) != 0 and db_check_dict(db+d):
				model_db = db_open_dict(db+d)
				if model_db.has_key("maxrec"):
					hdr = model_db.get_header(0)
					if hdr["nx"] == hdr["ny"] and hdr["nx"] == hdr["nz"]:
						names.append(d)
						
						dims.append(str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"]))
						try: mean.append("%4.3f" %hdr["mean"])
						except: mean.append("")
						try: sigma.append("%4.3f" %hdr["sigma"])
						except: sigma.append("")
						try: max.append("%4.3f" %hdr["maximum"])
						except: max.append("")
						try: min.append("%4.3f" %hdr["minimum"])
						except: min.append("")
						try: quality.append("%4.3f" %hdr["quality"])
						except: quality.append("")
						
		p = ParamTable(name="filenames",desc_short="Current initial models",desc_long="")
		pnames = ParamDef(name="Files names",vartype="stringlist",desc_short="Initial model name",desc_long="The name of the initial model in the EMAN2 database",property=None,defaultunits=None,choices=names)
		pdims = ParamDef(name="dims",vartype="stringlist",desc_short="Dimensions",desc_long="The dimensions of the 3D image",property=None,defaultunits=None,choices=dims)
		pmax = ParamDef(name="max",vartype="stringlist",desc_short="Maximum",desc_long="The maximum voxel value in this 3D image",property=None,defaultunits=None,choices=max)
		pmin = ParamDef(name="min",vartype="stringlist",desc_short="Minimum",desc_long="The minimum voxel value in this 3D image",property=None,defaultunits=None,choices=min)
	
		pmean = ParamDef(name="mean",vartype="stringlist",desc_short="Mean",desc_long="The mean voxel value of this 3D image",property=None,defaultunits=None,choices=mean)
		psigma = ParamDef(name="sigma",vartype="stringlist",desc_short="Sigma",desc_long="The standard deviation of the voxel values in this 3D image",property=None,defaultunits=None,choices=sigma)
		
		pquality = ParamDef(name="quality",vartype="stringlist",desc_short="Quality",desc_long="A quality metric which is stored in the image header",property=None,defaultunits=None,choices=sigma)
		
		
		p.append(pnames)
		p.append(pdims)
		p.append(pquality)
		p.append(pmax)
		p.append(pmin)
		p.append(pmean)
		p.append(psigma)
		
		setattr(p,"convert_text", ptable_convert_4)
		setattr(p,"icon_type","3d_image")
		
		return p,len(names)

	

class E2MakeInitialModel(ParticleWorkFlowTask):
	documentation_string = "Make an initial model with e2initialmodel."
	warning_string = "\n\n\nNOTE: there are no reference free classes in the project. Go back a step and try running e2refine2d" 
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "run e2makeinitialmodel"
	def get_params(self):
		params = []
		
		p,n = self.get_reference_free_class_averages_table()
		if n == 0: params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2MakeInitialModel.documentation_string+E2MakeInitialModel.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2MakeInitialModel.documentation_string,choices=None))
			
			piter = ParamDef(name="iter",vartype="int",desc_short="Iterations",desc_long="The number of times each 3D is iteratively refined",property=None,defaultunits=4,choices=[])
			ptries = ParamDef(name="tries",vartype="int",desc_short="Tries",desc_long="The number of 3D models to generate",property=None,defaultunits=10,choices=[])
			syms = ["icos","oct","tet","c","d","h"]
			psym =  ParamDef(name="symname",vartype="string",desc_short="Symmetry",desc_long="Symmetry to be imposed during refinement",property=None,defaultunits=None,choices=syms)
			psymnum = ParamDef(name="symnumber",vartype="string",desc_short="Symmetry number",desc_long="In C,D and H symmetry, this is the symmetry number",property=None,defaultunits="",choices=None)
			
			p.enable_multiple_selection = False
			params.append(p)
			params.append([piter,ptries])
			params.append([psym,psymnum])
		
	
		return params
	
	def on_form_ok(self,params):
		error_message = []
		
		if not params.has_key("filenames"):
			# THERE ARE no classes to choose from and the user has hit ok
			self.emit(QtCore.SIGNAL("task_idle"))
			self.form.closeEvent(None)
			self.form = None
			return
		
		error_message = []
		if len(params["filenames"]) != 1: error_message.append("Please choose a single file to proceed")
		
		if params["iter"] < 0: error_message.append("Please specify an iter value of atleast 0")
		if params["tries"] < 1: error_message.append("Please specify a number of tries that is atleast 1")
		
		
		# copied from e2refine
		
		options = EmptyObject()
		
		error_message.extend(self.check_sym(params,options))
		
		if len(error_message) > 0:
			self.show_error_message(error_message)
			return	
		else:
			options.input = params["filenames"][0]
			options.iter = params["iter"]
			options.tries = params["tries"]
			options.filenames = []
			#options.sym - taken care of by check_sum
			string_args = ["iter","input","tries","sym"]
			bool_args = []
			additional_args = []
			temp_file_name = "e2initialmodel_stdout.txt"
			self.spawn_single_task("e2initialmodel.py",options,string_args,bool_args,additional_args,temp_file_name)
			self.emit(QtCore.SIGNAL("task_idle"))
			self.form.closeEvent(None)
			self.form = None
		
class ImportInitialModels(ParticleWorkFlowTask):
	documentation_string = "Import initial models into the EMAN2 database. Browse for the images you wish to import or type them directly into the entry form. If you tick force overwrite initial models in the EMAN2 database with the same name will automatically be over written."
	
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Import initial models"

		
	def get_params(self):
		params = []
		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=ImportInitialModels.documentation_string,choices=None))
		params.append(ParamDef(name="filenames",vartype="url",desc_short="Import models",desc_long="A list of 3D images that you wish to import into the EMAN2 database scheme.",property=None,defaultunits=[],choices=[]))
		pfo = ParamDef(name="force",vartype="boolean",desc_short="Force overwrite",desc_long="Whether or not to force overwrite files that already exist",property=None,defaultunits=False,choices=None)
		params.append(pfo)
		return params
	
	def on_form_ok(self,params):
		error_message = []
		
		
		mesbox = QtGui.QMessageBox()
		mesbox.setWindowTitle("Almost but not quite")
		if params.has_key("filenames") and len(params["filenames"])==0:
			mesbox.setText("Please provide at least one filename to proceed")
	 		mesbox.exec_()
	 		return
	 	
	 	
	 	for name in params["filenames"]:
	 		if not file_exists(name):
	 			error_message.append("The file "+name+" does not exist")
	 		else:
	 			e = EMData()
	 			e.read_image(name,0,True)
	 			if e.get_xsize() != e.get_ysize() or e.get_xsize() != e.get_zsize():
	 				error_message.append("The file "+name+" is not cubic")
	 				
	 	if params["force"] == False:	
		 	for file in params["filenames"]:
		 		output_name = "bdb:initial_models#"+get_file_tag(file)
				if file_exists(output_name):
					error_message.append("An entry exists in the initial_models database with the same name as this file "+file+", please rename your file or choose force over write")
		 	
	 			
	 	if len(error_message) > 0:
	 		self.show_error_message(error_message)
	 		return
	 	
	 	# if we make it here we're all good, 
	 	num_processing_operations = 2 # one read and one write
	 	progress = EMProgressDialogModule(self.application(),"Importing files into database...", "Abort import", 0, len(params["filenames"])*num_processing_operations,None)
		progress.qt_widget.show()
		
		i = 0
		for file in params["filenames"]:
			e = EMData()
			e.read_image(file,0)
			i +=1
			progress.qt_widget.setValue(i)
			output_name = "bdb:initial_models#"+get_file_tag(file)
			e.write_image(output_name,0)
			i +=1
			progress.qt_widget.setValue(i)
		
		progress.qt_widget.close()
		
	 	self.emit(QtCore.SIGNAL("task_idle"))
		self.form.closeEvent(None)
		self.form = None
	 			

class RefinementReportTask(ParticleWorkFlowTask):
	documentation_string = "This form displays the models produced at the end of each refinement."
	warning_string = "\n\n\nNOTE: There are no results available."
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "Refinement results"
	
	def get_params(self):
		params = []
		
		p,n = self.get_last_refinement_models_table()
		
		if n == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=RefinementReportTask.documentation_string+RefinementReportTask.warning_string,choices=None))
		else:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=RefinementReportTask.documentation_string,choices=None))
			params.append(p)
		return params
	
	
	def get_last_refinement_models_table(self):
		'''
		Looks for bdb:r2d_??#classes_?? and the bdb:r2d_??#classes_init file, finds the most recent one, then fills in the number of particles in
		in the class average file and also its dimensions.
		'''
		dirs, files = get_files_and_directories(e2getcwd())
#		for root, dirs, files in os.walk(os.getcwd()):
#			break
		
		dirs.sort()
		for i in range(len(dirs)-1,-1,-1):
			if len(dirs[i]) != 9:
				dirs.pop(i)
			elif dirs[i][:7] != "refine_":
				dirs.pop(i)
			else:
				try: int(dirs[i][7:])
				except: dirs.pop(i)
		# allright everything left in dirs is "refine_??" where the ?? is castable to an int, so we should be safe now
		threed_files = []
		threed_dims = []
		threed_mean = []
		threed_sigma = []
		threed_max = []
		threed_min = []
		for dir in dirs:
			threed_db = None
			# check for 00 to 09 but 00 is replaced with "init"
			db_first_part = "bdb:"+dir+"#threed_"
			cont = True
			for i in range(0,10):
				for j in range(0,10):
					db_name = db_first_part+str(i)+str(j)
					if db_check_dict(db_name):
						threed_db = db_name
					else:
						if i != 0 or j != 0:
							cont = False
							break
						#else just check for 01 incase the user has specified the --initial arugment
				if not cont:
					break
				
			if threed_db != None:
				threed_files.append(threed_db)
				th_db = db_open_dict(threed_db)
				dims = ""
				mean = ""
				sigma = ""
				max = ""
				min = ""
				try:
					hdr = th_db.get_header(0)
					dims = str(hdr["nx"])+'x'+str(hdr["ny"])+'x'+str(hdr["nz"])
					mean = "%4.3f" %hdr["mean"]
					sigma = "%4.3f" %hdr["sigma"]
					min = "%4.3f" %hdr["minimum"]
					max = "%4.3f" %hdr["maximum"]
				except: pass
				
				
				threed_dims.append(dims)
				threed_mean.append(mean)
				threed_sigma.append(sigma)
				threed_max.append(max)
				threed_min.append(min)
		if len(threed_files) > 0:
			
			p = ParamTable(name="filenames",desc_short="Most current 3D reconstructions",desc_long="")
			pnames = ParamDef(name="Files names",vartype="intlist",desc_short="3D image file",desc_long="The location of 3D reconstructions",property=None,defaultunits=None,choices=threed_files)
			pmean = ParamDef(name="Mean",vartype="stringlist",desc_short="Mean",desc_long="The mean voxel value",property=None,defaultunits=None,choices=threed_mean)
			psigma = ParamDef(name="Standard deviation",vartype="stringlist",desc_short="Standard deviation",desc_long="The standard deviation of the voxel values",property=None,defaultunits=None,choices=threed_sigma)
			pdims = ParamDef(name="Dimensions",vartype="stringlist",desc_short="Dimensions",desc_long="The dimensions of the 3D images",property=None,defaultunits=None,choices=threed_dims)
			pmax = ParamDef(name="min",vartype="stringlist",desc_short="Minimum",desc_long="The maximum voxel value",property=None,defaultunits=None,choices=threed_max)
			pmin = ParamDef(name="max",vartype="stringlist",desc_short="Maximum",desc_long="The minimum voxel value",property=None,defaultunits=None,choices=threed_min)
			
			p.append(pnames)
			p.append(pdims)
			p.append(pmean)
			p.append(psigma)
			p.append(pmax)
			p.append(pmin)
			
			
			setattr(p,"convert_text", ptable_convert_2)
			setattr(p,"icon_type","3d_image")
			
			return p,len(threed_files)
		else:
			return None,0
			

class E2RefineParticlesTask(ParticleWorkFlowTask):
	'''
	The mother of all tasks
	'''
	 
	general_documentation = "These are the general parameters for 3D refinement in EMAN2. Please select which particles you wish to use as part of this process, specify your starting model, and fill in other parameters such as symmetry and whether or not the usefilt option should be used."
	project3d_documentation = "These  parameters are used by e2project3d. Several orientation generation techniques provide alternative methods for distributing orientations in the asymmetric unit. Orientations can be generated based on your desired angular spacing, or alternatively on the desired total number of projections. In the latter case EMAN2 will generate a number as close as possible to the specified number, but note that there is no guarantee of a perfect match. You can also vary the method by which projections are generated. If you check the \'include mirror\' option you should be sure to use aligners to that do not perform mirror alignment."
	simmx_documentation = "These  parameters are used by e2simmx, a program that compares each particle to each projection and records quality scores. To do this the particles must first be aligned to the projections using the aligners you specify. Once aligned the \'Main comparator\' is used to record the quality score. These quality values are recorded to an image matrix on handed on to the next stage in the refinement process.\n\nThe shrink parameter causes all projections and particles to be shrunken by the given amount prior to comparison. This can provide a significant time boost, though at the expense of resolution. Note however that the class averaging stage, which  can involve iterative alignment, does not use shrunken data."
	class_documentation = "Most of these parameters are for e2classaverage with the exception of the \"Class separation\" parameter which is the solely used by e2classify. Classification is first performed using this latter program and the output from e2simmx. This is followed by the class averaging stage. The critical argument for the class averaging procedure is the number of iterations. In early stages of refinement this should be relatively large and it should gradually be reduced as your model converges to the answer."
	make3d_documentation = "Iterative Fourier inversion is the preferred method of 3D reconstruction in EMAN2."

	def __init__(self,application):
	 	ParticleWorkFlowTask.__init__(self,application)
	 	self.end_tag = "_ptcls"
	 	self.window_title = "e2refine parameters"
	 	self.usefilt_tags = ["_ptcls_ctf_wiener"] # these tags could eventually generalized, such that if the user does their filtering option then their "tag" is included as an option
		self.usefilt_display_names = ["Wiener"]
	 	
	def run_form(self):
		self.form = EMTableFormModule(self.get_params(),self.application())
		self.form.qt_widget.resize(*self.preferred_size)
		self.form.setWindowTitle(self.window_title)
		self.application().show_specific(self.form)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_ok"),self.on_form_ok)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_cancel"),self.on_form_cancel)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("emform_close"),self.on_form_close)
		QtCore.QObject.connect(self.form,QtCore.SIGNAL("display_file"),self.on_display_file)
		
	def get_params(self):
	 	params = []
		
	#	params.append(self.get_intro_params())
		params.append(self.get_main_params())
		params.append(self.get_project3d_page())
		params.append(self.get_simmx_page())
		params.append(self.get_classaverage_page())
		params.append(self.get_make3d_page())
		
		return params
	
	def on_form_ok(self,params):
		
		options = EmptyObject()
		error_message = self.check_main_page(params,options)
		
		
		for checker in [self.check_main_page,self.check_project3d_page,self.check_simmx_page,self.check_classaverage_page,self.check_make3d_page]:
			error_message = checker(params,options)
			if len(error_message) > 0 :
				self.display_errors(error_message)
				return
			
		# w'oh if we make it here a lot of checking has occured. Now get the args in order to spawn_single_task
		string_args = []
		bool_args = []
		
		additional_args = []
		
		for get_args in [self.add_general_args,self.add_project3d_args,self.add_simmx_args,self.add_classaverage_args,self.add_make3d_args]:
		  	error = get_args(options,string_args,bool_args,additional_args)
		
			if error != None: # not too fast, something still could have gone wrong
				self.display_errors([error])
				return
		
		temp_file_name = "e2refine_stdout.txt"
		
		self.write_db_parms(options,string_args,bool_args)
		
		self.spawn_single_task("e2refine.py",options,string_args,bool_args,additional_args,temp_file_name)
		self.emit(QtCore.SIGNAL("task_idle"))
		self.form.closeEvent(None)
		self.form = None
		
	def write_db_parms(self,options,string_args,bool_args):
		db = db_open_dict("bdb:e2refine.args")
		
		for string in string_args:
			db[string] = getattr(options,string)
			
		for string in bool_args:
			db[string] = getattr(options,string)
		
	
	def display_errors(self,error_message):
		'''
		error_message is a list of strings
		'''
		
		if len(error_message) > 0:
			self.show_error_message(error_message)
	 		
	
	def get_main_params(self):
		'''
		General/broad refine params
		'''
		params = []
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineParticlesTask.general_documentation,choices=None))

		
		if self.end_tag != "generic":
			p,n = self.get_particle_selection_table(tag=self.end_tag)
		else:
			p = ParamDef(name="filenames",vartype="url",desc_short="Input file name(s)",desc_long="The names of the particle files you want to use as in the input data for e2refine2d.py",property=None,defaultunits=[],choices=[])
			n = 1 # just to fool the next bit, that's all
			
		# If we make it here n should be greater than 0, so just continue
		if n == 0:
			print "woops didn't think this could happen" # and it shouldn't
			
		
		params.append(p)
		
		init_models = self.get_available_initial_models()
		init_models.sort()
		
		pinitialmodel =  ParamDef(name="model",vartype="string",desc_short="Starting model",desc_long="The starting 3D model that will be used to seed refinement",property=None,defaultunits=None,choices=init_models)
		params.append(pinitialmodel)
		
		syms = ["icos","oct","tet","d","c","h"]
		
		piter = ParamDef(name="iter",vartype="int",desc_short="Refinement iterations",desc_long="The number of times 3D refinement should be iterated",property=None,defaultunits=3,choices=[])
		plowmem = ParamDef(name="lowmem",vartype="boolean",desc_short="Low mem",desc_long="Causes various programs to restrict memory usage but results in increased CPU time.",property=None,defaultunits=False,choices=None)
		
		psym =  ParamDef(name="symname",vartype="string",desc_short="Symmetry",desc_long="Symmetry to be imposed during refinement",property=None,defaultunits=None,choices=syms)
		psymnum = ParamDef(name="symnumber",vartype="string",desc_short="Symmetry number",desc_long="In C,D and H symmetry, this is the symmetry number",property=None,defaultunits="",choices=None)
		
		filt_options = self.get_usefilt_options()
		
		if len(filt_options) > 0:
			filled_out_options = ["None"]
			filled_out_options.extend(filt_options)
			filled_out_options.append("Specify")
			pusefilt = ParamDef(name="usefilt_choice",vartype="choice",desc_short="Usefilt",desc_long="If specified will cause filtered images to be used for alignment of images",property=None,defaultunits="None",choices=filled_out_options)
			pusefiltentry  =  ParamDef(name="usefilt_string",vartype="string",desc_short="file",desc_long="Specify the file containing the filtered images directly",property=None,defaultunits="",choices=[])
			params.append([pusefilt,pusefiltentry])
		else:
			pusefiltentry  =  ParamDef(name="usefilt_string",vartype="string",desc_short="Usefilt",desc_long="Specify the file containing the filtered images directly",property=None,defaultunits="",choices=[])
			params.append(pusefiltentry)

		params.append([piter,plowmem])
		params.append([psym,psymnum])
		
		return ["General",params]
	
	def add_general_args(self,options,string_args,bool_args,additional_args):
		
		options.path = numbered_path("refine",True)
		
		if self.end_tag != "generic":
			success,cmd = self.make_v_stack(options.filenames,"all",options,"input")
			if not success:
				return cmd + " failed"
		else:
			success, cmd = self.make_stack(options.filenames, "all",options,"input")
			if not success:
				return cmd + " failed"
			
		string_args.append("input")
		
		if hasattr(options,"usefilt"):
			if hasattr(options,"usefilt_names"):
				success,cmd = self.make_v_stack(options.usefilt_names,"usefilt",options,"usefilt")# sets the attribute for us
			else:
				pass
				# pass it should be fine, the usefilt attr is already set
			
			string_args.append("usefilt")
		
		error = self.check_model(options)
		if error != None:
			return error
		
		options.filenames = [] # important for this to happen so the argument doesn't have all the filenames as args
		string_args.extend(["iter","sym","model","path"])
		bool_args.append("lowmem")
		
		return None # returning None is good
	
	def check_model(self,options):
		
		model = "bdb:initial_models#"+options.model
		if not db_check_dict(model):
			return "db checked failed for %s, check initial models" %model
		
		nx,ny = gimme_image_dimensions2D(options.input)
		if nx != ny:
			return "input images aren't square"
		
		
		x,y,z = gimme_image_dimensions3D(model)
		
		
		if x != y or z != y:
			return "initial model isn't square"
		
		if nx != x:
			scale = float(nx)/x
			new_model = "bdb:"+options.path + "#initial_model"
			
			db = db_open_dict(model)
			image = db[0]

			start = (x-nx)/2
			if scale > 1:
				image.clip_inplace(Region(start,start,start,nx,nx,nx))
				t = Transform()
				t.set_scale(scale)
				image.transform(t)	
			else:
				t = Transform()
				t.set_scale(scale)
				image.transform(t)
				image.clip_inplace(Region(start,start,start,nx,nx,nx))
				
			image.write_image(new_model,0) # db got opened here

		 	options.model = new_model
		 	db_close_dict(new_model) # force synchronization so e2refine.py will definetely run -
		else:
			options.model = model # all good
			
		return None
		
		
	def make_stack(self,filenames,out_name,options,attr):
		'''
		This one's a bit more specialized to handle flat files and avoid massive copying
		'''
		if len(filenames) == 1:
			setattr(options,attr,filenames[0])
		else:
			fail = False
			# check if they're all bdb files, in which case we can make a v stack
			for name in filenames:
				if name[0:4] != "bdb:":
					fail = True
					break
				
			if fail: # we can't make a vstack
				# potentially lots of e2proc2d
				progress = EMProgressDialogModule(self.application(),"Importing files into database...", "Abort import", 0, len(filenames),None)
				progress.qt_widget.show()
		  	   	i = 0
		  	   	setattr(options,attr, "bdb:"+options.path+"#"+out_name)
				for i,name in enumerate(filenames):
					cmd = "e2proc2d.py"
		 			cmd += " "+name
		 			cmd += " "+getattr(options,attr)
		 			success = (os.system(cmd) in (0,12))
		 			if not success:
		 				return False,cmd
		 			else:
		 				progress.setValue(i+1)
				
				progress.qt_widget.close()	
			else:
				return self.make_input_v_stack(filenames,out_names,options,attr)

	
	def make_v_stack(self,filenames,out_name,options,attr):
	 	
	 	cmd = "e2bdb.py"
	 	for name in filenames:
	 		cmd += " "+name
	 	
	 	cmd += " --makevstack=bdb:"+options.path+"#"+out_name
	 	
	 	print "executing cmd", cmd
	 	
	 	self.application().setOverrideCursor(Qt.BusyCursor)
	 	success = os.system(cmd)
	 	success = (success in (0,11,12))
	 	self.application().setOverrideCursor(Qt.ArrowCursor)
	 	
	 	setattr(options,attr,"bdb:"+options.path+"#"+out_name) # Note important 
	 	
	 	return success,cmd
	 
	
	def check_main_page(self,params,options):
		'''
		Called internally to check that the user has entered correct parameters in the main page
		returns a potentially empty list of error messages, if it is empty it means there are no errors
		Also sets argument attributes of the options object, killing two birds with one stone
		'''
		error_message = []
		#filenames
		if len(params["filenames"]) == 0:
			error_message.append("Please choose files to form the input data set.")
			
		if self.end_tag != "generic":
			names = ["bdb:particles#"+name for name in params["filenames"]]
			options.filenames = names
			print options.filenames
		#usefilt
		check_usefilt_file = False
		if params.has_key("usefilt_choice"):
			if params["usefilt_choice"] == "Specify":
				check_usefilt_file = True
			elif len(params["usefilt_string"]) != 0:
				error_message.append("You entered a file name for the usefilt option but did not choose the \'Specify\' option. Please choose what you want to do.")
		elif len(params["usefilt_string"]) != 0:
			check_usefilt_file = True
			
		
		if check_usefilt_file:
			# d'oh this is tiring
			if params["usefilt_string"] == "None":
				pass # this is fine do nothing
			elif len(params["usefilt_string"]) == 0:
				error_message.append("You chose to specify a usefilt file but did not provide the name")
			else:
				fine, message = is_2d_image_mx(params["usefilt_string"])
				if not fine:
					error_message.append("The usefilt file you specified is not a 2D matrix." %params["usefilt_string"])
				else:
					n = 0
					for name in options.filenames:
						n += EMUtil.get_image_count(name)
						
					n2 = EMUtil.get_image_count(params["usefilt_string"])
					
					if n != n2:
						error_message.append("The total number of images in the input data ("+str(n)+") does not match the number of images in the usefilt file ("+str(n2)+").")
						
					else:
						options.usefilt=params["usefilt_string"]
		else:
			if params.has_key("usefilt_choice") and params["usefilt_choice"] != "None":
				# If we make it here we're guaranteed to be using images in the database, and they should have a one to one correspondance
				options.usefilt = params["usefilt_choice"] # the choice should only be there if it is valid
				
				i = self.usefilt_display_names.index(params["usefilt_choice"])
				if i == -1:
					error_message.append("There is an internal error, please close the workflow and try again. If this message persists contact developers")
				new_tag = self.usefilt_tags[i]
				
				usefilt_names = []
				l = len(self.end_tag)
				for name in options.filenames:
					usefilt_names.append(name[:-l]+new_tag)
					
				options.usefilt_names = usefilt_names
				print options.usefilt_names
				
				
		#symmetry
		error_message.extend(self.check_sym(params,options))
		
		
		# iterations
		if params["iter"] < 1:
			error_message.append("The number of refinement iterations must be atleast 1.")
		else:
			options.iter = params["iter"]
			
		options.lowmem = params["lowmem"]
		options.model = params["model"] # can't get this one wrong
		
		return error_message
	
	def get_usefilt_options(self):
		if self.end_tag != "generic":
			
			n = self.get_total_particles(self.end_tag)
			
			available_filt_files = []
			number = []
			for i,tag in enumerate(self.usefilt_tags):
				if tag != self.end_tag:
					n_ = self.get_total_particles(tag=tag)
					if n_ > 0 and n_ == n:
						available_filt_files.append(self.usefilt_display_names[i])
					
			return available_filt_files
		else:
			return []
		
	def add_project3d_args(self,options,string_args,bool_args,additional_args):
		
		string_args.extend(["orientgen","projector"])
		# sym is already taken care of in the main args
		return None # no error to report
	def get_project3d_page(self):
		params = []
		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineParticlesTask.project3d_documentation,choices=None))

		
		
		projectors = self.get_projectors_list()
		orientgens = self.get_orientgens_list()
			
		pprojector =  ParamDef(name="projector",vartype="string",desc_short="Projector",desc_long="The method used to generate projections",property=None,defaultunits="standard",choices=projectors)
		
		porientgens =  ParamDef(name="orientgen",vartype="string",desc_short="Orientation generator",desc_long="The method of orientation generation",property=None,defaultunits="eman",choices=orientgens)
		
		pmirror = ParamDef(name="incmirror",vartype="boolean",desc_short="Include mirror",desc_long="Include the mirror portion of the asymmetric uni",property=None,defaultunits=False,choices=[])
		
		
		orient_options = ["angle based", "number based"]
		porientoptions = ParamDef(name="orientopt",vartype="choice",desc_short="Method of generating orientation distribution",desc_long="Choose whether you want the orientations generating based on an angle or based on a total number of orientations desired",property=None,defaultunits="angle based",choices=orient_options)
		porientoptionsentry  =  ParamDef(name="orientopt_entry",vartype="float",desc_short="value",desc_long="Specify the value corresponding to your choice",property=None,defaultunits=5,choices=[])
		
		params.append([pprojector,porientgens])
		params.append([porientoptions,porientoptionsentry])
		params.append(pmirror)
		
		return ["Project 3D",params]
	
	def check_project3d_page(self,params,options):
		
		error_message = []
		if params["orientopt_entry"] < 0:
			error_message.append("Please enter a positive non zero value for the angle/number of projections in the Project3D settings")
		
		if params["orientgen"] == "rand" and params["orientopt"] == "angle based":
			error_message.append("The random orientation generator doesn't work with the \'angle based\' argument, please choose \'number based\' instead") 
		
		if int(params["orientopt_entry"]) !=  params["orientopt_entry"] and  params["orientopt"] == "number based":
			error_message.append("In project3d - for the number based orientation method the number must be an integer")
		
		options.orientgen = params["orientgen"]
		if params["orientopt"] == "angle based":
			options.orientgen += ":delta="
		else:
			options.orientgen += ":n="
		
		options.orientgen += str(params["orientopt_entry"])	
		
		if params["incmirror"]:
			options.orientgen += ":inc_mirror=1"
		else:
			options.orientgen += ":inc_mirror=0"
			
		
		options.projector = params["projector"]
		
		return error_message
		
	def add_simmx_args(self,options,string_args,bool_args,additional_args):
		
		optionals = ["simcmp","simalign","simaligncmp","simralign","simraligncmp"]
		for opt in optionals:
			if getattr(options,opt) != None: string_args.append(opt)
		
		if options.shrink > 1: string_args.append("shrink") # e2simmx doesn't like it if shrink is 1
	
	
	def check_simmx_page(self,params,options):
		error_message = []
		if params["shrink"] <= 0:
			error_message.append("The shrink argument in the simmx page must be atleast 1")
			
		options.shrink=params["shrink"]
		
		error_message.extend(self.check_aligners_and_cmps(params,options,"sim","Simmx"))
		
		return error_message
	
	def check_aligners_and_cmps(self,params,options,parameter_prefix="class",page="Class averaging"):
		
		error_message = []
		vals = []
		
		vals.append(["align","alignargs"])
		vals.append(["ralign","ralignargs"])
		vals.append(["aligncmp","aligncmpargs"])
		vals.append(["raligncmp","raligncmpargs"])
		vals.append(["cmp","cmpargs"])
		
		
		for v in vals:
			v[0] = parameter_prefix + v[0]
			v[1] = parameter_prefix + v[1]
		
		for v in vals:
			setattr(options,v[0],params[v[0]])
			setattr(options,v[1],params[v[1]])
		
		for v in vals:
			if getattr(options,v[0]) == "None": setattr(options,v[0],None)
			elif len(getattr(options,v[1])) != 0: setattr(options,v[0],getattr(options,v[0])+":"+getattr(options,v[1]))
		
		
		for i,v in enumerate(vals):
			arg = getattr(options,v[0])
			if arg != None:
				if i > 1: # its a cmp, yes a hack but I have no time
					if not check_eman2_type(arg,Cmps,"Cmp",False): error_message.append("There is problem with the " +v[0]+ " comparator argument in the "+page+" page.")
				else:
					if not check_eman2_type(arg,Aligners,"Aligner",False): error_message.append("There is problem with the " +v[0]+ " aligner argument in the "+page+" page.")
  	
  		return error_message
	
	def get_simmx_page(self):
		
		params = []
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineParticlesTask.simmx_documentation,choices=None))

		pshrink = ParamDef(name="shrink",vartype="int",desc_short="Shrink",desc_long="The the downsampling rate used to shrink the data at various stages in refinement, for speed purposes",property=None,defaultunits=4,choices=[])
		
		
		params.append(pshrink)
		params.extend(self.get_cls_simmx_params(parameter_prefix="sim"))
		
		
		return ["Simmx",params]
	
	def add_classaverage_args(self,options,string_args,bool_args,additional_args):
		
		optionals = ["classcmp","classalign","classaligncmp","classralign","classraligncmp"]
		for opt in optionals:
			if getattr(options,opt) != None: string_args.append(opt)
			
		string_args.extend(["sep","classiter","classkeep","classnormproc"])
		bool_args.append("classkeepsig")
	
	def check_classaverage_page(self,params,options):
		error_message = []
		
		if params["sep"] <= 0:
			error_message.append("The separation argument in the Class average page must be atleast 1")
		
		if params["classiter"] < 0:
			error_message.append("The number of class averaging iterations must be atleast 0")
		
		if params["classkeepsig"] == False:
			if params["classkeep"] < 0 or params["classkeep"] > 1:
				error_message.append("The keep parameter in the Class average page must be between 0 and 1. This does not hold if the \'Sigma based\' option is selected.")
		
		error_message.extend(self.check_aligners_and_cmps(params,options,"class", "Class average"))
		
		if len(error_message) > 0: return error_message # calling program should act and discontinue
		
		options.sep = params["sep"]
		options.classkeep = params["classkeep"]
		options.classkeepsig = params["classkeepsig"]
		options.classnormproc = params["classnormproc"]
		options.classiter = params["classiter"]
		
		return error_message
	
	
	def get_classaverage_page(self):
		params = []
		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineParticlesTask.class_documentation,choices=None))

		
		psep = ParamDef(name="sep",vartype="int",desc_short="Class separation",desc_long="The number of classes a particle can contribute towards",property=None,defaultunits=1,choices=[])
		piter = ParamDef(name="classiter",vartype="int",desc_short="Averaging iterations",desc_long="The number of class averaging iterations",property=None,defaultunits=2,choices=[])
		
		averagers = self.get_averagers_list()
		averagers.sort()
		paverager =  ParamDef("classaverager",vartype="string",desc_short="Averager",desc_long="The method used for generating class averages",property=None,defaultunits="image",choices=averagers)
		
		pkeep = ParamDef(name="classkeep",vartype="float",desc_short="keep",desc_long="The fraction of particles to keep in each class average. If sigma based is checked this value is interpreted in standard deviations from the mean instead",property=None,defaultunits=0.8,choices=[])
		pkeepsig = ParamDef(name="classkeepsig",vartype="boolean",desc_short="Sigma based",desc_long="If checked the keep value is interpreted in standard deviations from the mean instead of basic ratio",property=None,defaultunits=True,choices=[])
		
		pnormproc =  ParamDef("classnormproc",vartype="string",desc_short="Normalization processor",desc_long="The normalization method applied to the class averages",property=None,defaultunits="normalize.edgemean",choices=["normalize","normalize.edgemean","None"])
		
		
	
		params.append([piter,psep])
		params.append([pkeep,pkeepsig])
		params.append([paverager,pnormproc])
		params.extend(self.get_cls_simmx_params(parameter_prefix="class"))

		return ["Class averaging",params]
		
		
	def get_cls_simmx_params(self,parameter_prefix=""):
		params = []
		aligners = self.get_aligners_list()
		cmps = self.get_cmps_list()
		
		aligners.sort()
		cmps.sort()
		
		psimalign =  ParamDef(name=parameter_prefix+"align",vartype="string",desc_short="Aligner",desc_long="The aligner being used",property=None,defaultunits="rotate_translate_flip",choices=aligners)
		psimalignargs =  ParamDef(name=parameter_prefix+"alignargs",vartype="string",desc_short="params",desc_long="Parameters for the aligner, see \"e2help.py aligners\"",property=None,defaultunits="",choices=[])
		
		psimaligncmp =  ParamDef(name=parameter_prefix+"aligncmp",vartype="string",desc_short="Align comparator",desc_long="The comparator being used",property=None,defaultunits="frc",choices=cmps)
		psimaligncmpargs =  ParamDef(name=parameter_prefix+"aligncmpargs",vartype="string",desc_short="params",desc_long="Parameters for this comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	
		
		
		prsimalign =  ParamDef(name=parameter_prefix+"ralign",vartype="string",desc_short="Refine aligner",desc_long="The refine aligner being used",property=None,defaultunits="None",choices=["None","refine"])
		prsimalignargs =  ParamDef(name=parameter_prefix+"ralignargs",vartype="string",desc_short="params",desc_long="Parameters for this aligner, see \"e2help.py aligners\"",property=None,defaultunits="",choices=[])
		
		prsimaligncmp =  ParamDef(name=parameter_prefix+"raligncmp",vartype="string",desc_short="Refine align comparator",desc_long="The comparator being used for refine alignment",property=None,defaultunits="frc",choices=cmps)
		prsimaligncmpargs =  ParamDef(name=parameter_prefix+"raligncmpargs",vartype="string",desc_short="params",desc_long="Parameters for thos comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	
		
		pcmp  =  ParamDef(name=parameter_prefix+"cmp",vartype="string",desc_short="Main comparator",desc_long="The comparator to determine the final quality metric",defaultunits="frc",choices=cmps)
		pcmpargs =  ParamDef(name=parameter_prefix+"cmpargs",vartype="string",desc_short="params",desc_long="Parameters for the this comparator, see \"e2help.py cmps\"",property=None,defaultunits="",choices=[])	
	

		params.append([pcmp,pcmpargs])
		params.append([psimalign,psimalignargs])
		params.append([psimaligncmp,psimaligncmpargs])
		params.append([prsimalign,prsimalignargs])
		params.append([prsimaligncmp,prsimaligncmpargs])
		
		return params

	def add_make3d_args(self,options,string_args,bool_args,additional_args):
		
		string_args.extend(["m3diter","m3dkeep","recon"])
		bool_args.append("m3dkeepsig")
		if hasattr(options,"m3dpreprocess"): string_args.append("m3dpreprocess")
		if hasattr(options,"pad"): string_args.append("pad")

	def check_make3d_page(self,params,options):
		error_message = []
		
		if params["m3diter"] < 0:
			error_message.append("The number of make3d iterations must be atleast 0")
		
		if params["m3dkeepsig"] == False:
			if params["m3dkeep"] < 0 or params["m3dkeep"] > 1:
				error_message.append("The keep parameter in the Make3D page must be between 0 and 1. This does not hold if the \'Sigma based\' option is selected.")
		
		if len(error_message) > 0 : return error_message # calling program should discontinue
		
		
		
		if len(params["pad"]) > 0:
			try: int(params["pad"])
			except: error_message.append("The value you entered for padding is nonsensical")
			pad = int(params["pad"])
			if params["filenames"] > 0:
#				try:
					if self.end_tag != "generic":
						nx,ny = gimme_image_dimensions2D("bdb:particles#"+params["filenames"][0])
					else:
						nx,ny = gimme_image_dimensions2D(params["filenames"][0])
					if nx >= pad or ny >= pad:
						error_message.append("You must specify a value for padding that is larger than the image dimensions - the image dimensions are %i x %i and your pad value is %i" %(nx,ny,pad))				
					else:
						options.pad = int(params["pad"])
#				except:
#					error_message.append("Can't get the dimensions of the first image???")
			else:
				pass # the user not entering filenames is an error, so after they've correct that we'll with the issues here
		
		options.m3diter = params["m3diter"]
		options.m3dkeep = params["m3dkeep"]
		options.m3dkeepsig = params["m3dkeepsig"]
		
		options.recon = params["recon"]
		
		if params["m3dpreprocess"] != "None":
			options.m3dpreprocess = params["m3dpreprocess"]

			
		return error_message

	def get_make3d_page(self):
		
		
		pkeep = ParamDef(name="m3dkeep",vartype="float",desc_short="keep",desc_long="The fraction of particles to keep in each class average. If sigma based is checked this value is interpreted in standard deviations from the mean instead",property=None,defaultunits=0.8,choices=[])
		pkeepsig = ParamDef(name="m3dkeepsig",vartype="boolean",desc_short="Sigma based",desc_long="If checked the keep value is interpreted in standard deviations from the mean instead of basic ratio",property=None,defaultunits=True,choices=[])
		
		piter = ParamDef(name="m3diter",vartype="int",desc_short="Reconstruction iterations",desc_long="The number of times the reconstruction algorithm is iterated",property=None,defaultunits=3,choices=[])
	
		
		pnormproc =  ParamDef("m3dpreprocess",vartype="string",desc_short="Normalization processor",desc_long="The normalization method applied to the class averages",property=None,defaultunits="normalize.edgemean",choices=["normalize","normalize.edgemean","None"])
		
		precon = ParamDef("recon",vartype="string",desc_short="Reconstruction technique",desc_long="The method used to perform 3D reconstruction",property=None,defaultunits="fourier",choices=["fourier","back_projection"])
		ppad = ParamDef("pad",vartype="string",desc_short="Pad to",desc_long="The amount to which you want to pad the 3D volume when Fourier inversion is being used. At least 25% is recommended", defaultunits="",choices=[])
		params = []
		
		params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineParticlesTask.make3d_documentation,choices=None))

		
		params.append([precon,piter])
		params.append([pnormproc,ppad])
		params.append([pkeep,pkeepsig])
		
		return ["Make3d", params]

class E2RefineGeneralTask(E2RefineParticlesTask):
	def __init__(self,application):
		E2RefineParticlesTask.__init__(self,application)
		self.end_tag = "generic"		 

class E2RefinePhaseTask(E2RefineParticlesTask):
	def __init__(self,application):
		E2RefineParticlesTask.__init__(self,application)
		self.end_tag = "_ptcls_ctf_flip"

class E2RefineWienerTask(E2RefineParticlesTask):
	def __init__(self,application):
		E2RefineParticlesTask.__init__(self,application)
		self.end_tag = "_ptcls_ctf_wiener"
		 
		  

class E2RefineChooseDataTask(ParticleWorkFlowTask):
	documentation_string = "This form assists you in providing all of the necessary parameters for 3D refinement in EMAN2. First choose the data you wish to use for use for running e2refine from the list of options below and hit OK. This will pop up a second form asking you to fill in more details." 
	warning_string = "\n\n\nNOTE: There are no initial models currently associated with the project. Please go back to the \'Initial model\' task and create/import initial models."
	def __init__(self,application):
		ParticleWorkFlowTask.__init__(self,application)
		self.window_title = "e2refine- getting starting"
		self.preferred_size = (480,300)
		
	def get_params(self):
		params = []		
		
		
		error_message = []
		
		init_models = self.get_available_initial_models()
		if len(init_models) == 0:
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineChooseDataTask.documentation_string+E2RefineChooseDataTask.warning_string,choices=None))
		else:
			n1 = self.get_total_particles(tag="_ptcls")
			n2 = self.get_total_particles(tag="_ptcls_ctf_flip")
			n3 = self.get_total_particles(tag="_ptcls_ctf_wiener")
			choices = []
			if n1 > 0:
				choices.append("Particles ("+str(n1)+")")
			if n2 > 0:
				choices.append("Phase flipped ptcls ("+str(n2)+")")
			if n3 > 0:
				choices.append("Wiener ptcls ("+str(n3)+")")
				
			choices.append("Specify files")
		
			params.append(ParamDef(name="blurb",vartype="text",desc_short="",desc_long="",property=None,defaultunits=E2RefineChooseDataTask.documentation_string,choices=None))
			params.append(ParamDef(name="particle_set_choice",vartype="choice",desc_long="Choose the particle data set you wish to use to generate a starting data for e2refine2d",desc_short="Choose data",property=None,defaultunits=None,choices=choices))
			
		return params
	
	def on_form_ok(self,params):
		for k,v in params.items():
			self.write_db_entry(k,v)


		if not params.has_key("particle_set_choice"):
			self.form.closeEvent(None)
			self.form = None
			self.emit(QtCore.SIGNAL("task_idle"))
			return
			
		choice = params["particle_set_choice"]
		
		if choice[:9] == "Particles":
			self.emit(QtCore.SIGNAL("replace_task"),E2RefineParticlesTask,"e2refine params")
			self.form.closeEvent(None)
			self.form = None
		elif choice[:5] == "Phase":
			self.emit(QtCore.SIGNAL("replace_task"),E2RefinePhaseTask,"e2refine params")
			self.form.closeEvent(None)
			self.form = None
		elif choice[:6] == "Wiener":
			self.emit(QtCore.SIGNAL("replace_task"),E2RefineWienerTask,"e2refine params")
			self.form.closeEvent(None)
			self.form = None
		elif choice == "Specify files":
			self.emit(QtCore.SIGNAL("replace_task"),E2RefineGeneralTask,"e2refine params")
			self.form.closeEvent(None)
			self.form = None
		else:
			print "the code has changed since the original author wrote it, something is wrong!!"
			self.form.closeEvent(None)
			self.form = None
			self.emit(QtCore.SIGNAL("task_idle"))
	
			
	def write_db_entry(self,key,value):
		pass

	
if __name__ == '__main__':
	
	from emapplication import EMStandAloneApplication
	em_app = EMStandAloneApplication()
	sprinit = SPRInitTask(em_app)
	window = sprinit.run_form() 
	
	
	
	
	#em_app.show()
	em_app.execute()	
