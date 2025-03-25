# -*- coding: utf-8 -*-

""" Provides the entry point for the application """

#Application version. Modify this accordingly
__version__ = "0.0.1" 

#Imported utility modules
import sys
import argparse
import logging
import os
from lxml import etree

#Imported application modules
from .generator import yamglGenerator
from .parser import yamglParser
from .image import yamglImage
from .font import yamglFont

#########################################################################################
class yamglApplication:
	"""
	Main application class
	"""

#---------------------------------------------------------------------------------------#
	def __init__(self, xml, src, inc, log = False, debug = True):
		"""
		Constructor
		"""
		#Logging setup
		logging.basicConfig(format = "yamgl_gen: %(levelname)s: %(message)s", 
				level = logging.DEBUG if debug else logging.INFO if log else logging.WARNING)
		
		log_subst = {logging.DEBUG : "debug", logging.INFO : "info", logging.WARNING : "warning", logging.ERROR : "error", logging.CRITICAL : "critical",}
		for key in log_subst:
			logging.addLevelName(key, log_subst[key])

		logging.debug("xml file = %s" % xml.name)
		logging.debug("src file = %s" % src.name)
		logging.debug("inc file = %s" % inc.name)

		#Get schema file
		try:
			with open(os.path.join(os.path.dirname(__file__), "schema.xsd")) as f:
				#Recode
				schema_root = etree.XML(bytes(bytearray(f.read(), encoding='utf-8')))	
		except:
			logging.error("could not open schema file")
			exit(1)

		schema = etree.XMLSchema(schema_root)
		xmlparser = etree.XMLParser(schema = schema)

		#Validate here
		try:
			xml_tree = etree.fromstring(bytes(bytearray(xml.read(), encoding='utf-8')), xmlparser)
		except:
			for error in xmlparser.error_log:
				logging.error("line %s: %s" % (error.line, error.message.encode("utf-8")))	
			exit(1)

		logging.info("ui file validation ... OK")

		#Change path relative to xml file
		os.chdir(os.path.dirname(os.path.realpath(xml.name)))

		#Create the parser
		self.parser = yamglParser(xml_tree)

		#List of objects
		self.object_list = []

		#Code generator
		self.code_generator = yamglGenerator(src, inc)

#---------------------------------------------------------------------------------------#
	def run(self):
		"""
		Run the application
		"""

		#Generate images
		image_list = self.parser.get_images()
	
		for img in image_list:
			self.object_list.append(yamglImage(img["name"], img["path"]))

		#Generate fonts
		font_list = self.parser.get_fonts()

		for fnt in font_list:
			self.object_list.append(yamglFont(fnt["name"], fnt["path"], fnt["size"], [(i["from"], i["to"]) for i in fnt["maps"]]))

		#Add objects to generator
		for data_object in self.object_list:
			data_object.add_to_generator(self.code_generator)

		#Run the generator
		self.code_generator.run()	

#########################################################################################
def main():
	"""
	Main entry point
	"""

    #Set up the command line interpreter
	parser = argparse.ArgumentParser(prog = 'yamgl_gen')

	#Version
	parser.add_argument("-v", "--version", action = "version", 
						version = '%(prog)s ' + __version__)
    
	#Log messages
	parser.add_argument("-l" , "--log", help = "display log messages", 
						action = "store_true")

	#Output directory
	parser.add_argument("-d", "--dir", action = 'store', default = "./",
						help = "output folder path")

	#Input xml file
	parser.add_argument("file", type = argparse.FileType("r"), 
						help="configuration file")

	#Parse arguments
	args = parser.parse_args()

	#Check and create output files
	try:
		src = open(os.path.join(args.dir, "yamgl_data.cpp"), "w")
		inc = open(os.path.join(args.dir, "yamgl_data.h"), "w")
	except BaseException as e:
		print("yamgl_gen: error: could not open output files")	
		exit(1)

	#Create and run
	app = yamglApplication(args.file, src, inc, log = args.log, debug = False)
	app.run()