__author__="michael XIE"

import os
import pandas as pd

class robot(object):
	def __init__(self,name):
		self.name = name
	def print_name(self):
		print("name: %s "% (self.name))
	
	def go_to_working_dir(self,path):
		"""change from cwd to path"""
		os.chdir(path)	
	def get_weekly_report_date(self,file,sheetname,number=0):
		"""open the file'sheetname and point the header to the number=0"""
		return pd.read_excel(file,sheetname=sheetname,header=number)

michael = robot("michael")
michael.print_name()
