#!/usr/bin/env python
#encoding:utf-8
from __future__ import unicode_literals

from JSAGparser import *
import Prompt
from codecs import open

class color:
   PURPLE = '\033[95m'
   WHITE = '\033[97m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

class pattern:
	DICT = '{0}' + color.BOLD + color.RED + '{1}:' + color.END
	LIST = '{0}' + color.BOLD + color.GREEN + '{1}:' + color.END
	SIMPLE = '{0}' + color.BOLD + color.WHITE + '{1}:' + color.END


def deepupdate(dict1,dict2,appendArray=False):
	if isinstance(dict1,list) and isinstance(dict2,list):
		if appendArray:
			dict1 += dict2
		else:
			dict1 = copy.deepcopy(dict2)
	elif isinstance(dict1,dict) and isinstance(dict2,dict):
		for key in dict2.keys():
			if isinstance(key,unicode) or isinstance(key,str):
				key = unicode(key)
			if key in dict1.keys():
				if isinstance(dict1[key],dict) and isinstance(dict2[key],dict):
					deepupdate(dict1[key],dict2[key])
				elif appendArray and isinstance(dict1[key],list) and isinstance(dict2[key],list):
					dict1[key] += dict2[key]
				else:
					dict1[key] = copy.deepcopy(dict2[key])
			else:
				dict1[key] = copy.deepcopy(dict2[key])
	else:
		dict1 = dict2
	return dict1

def getWidth(myList,maxLevel=-1,ident=0):
	width = 0
	for item in myList:
		if isinstance(item,list):
			width = max(width,getWidth(item,maxLevel=maxLevel-1,ident=ident+1))
		else:
			width = max(width,len(item['label'])+ident)
	return width

def printList(myList,ident="",width=0):
	for item in myList:
		if isinstance(item,list):
			printList(item,ident=" " + ident,width=width)
		else:
			try:
				label = item['pattern'].format(ident,item['label'],item['value'])
				if isinstance(item['value'],unicode):
					item['value'] = item['value'].encode('utf8')
				print ('{0:' + unicode(max(width,0)+15) + '}{1}').format(label,unicode(item['value']))
			except:
				print "ERROR"
				print myList
				sys.exit()
				
def toJSON(configValue,hidePasswords=True):
	if (isinstance(configValue,JSAGdata) and configValue.configParser.getType() == 'object') or isinstance(configValue,dict):
		result={}
		for key in configValue.keys():
			result[key] = toJSON(configValue[key],hidePasswords)
		return result
	elif (isinstance(configValue,JSAGdata) and configValue.configParser.getType() == 'array') or isinstance(configValue,list):
		result = []
		for item in configValue:
			result.append(toJSON(item,hidePasswords))
		return result
	elif isinstance(configValue,JSAGdata) and configValue.configParser.getType() in SIMPLE_TYPES:
		if configValue.configParser.getType() == 'password' and hidePasswords:
			return '****'
		return configValue.value
	else: 
		return configValue

class JSAGdata(object):
	def __init__(self,configParser=None,value=None,filename=None,path=[]):
		if isinstance(configParser,JSAGparser):
			self.configParser = configParser
		elif isinstance(configParser,dict):
			self.configParser = JSAGparser(configParser)
		else:
			raise TypeError("configParser argument is mandatory and must be a JSAGparser instance")

		self.setFilename(filename,path)

		if value is None or unicode(value) == '':
			if 'default' in self.configParser.keys():
				self.value = self.configParser['default']
			else:
				self.value = None
		else:
			self.setValue(value)
			
	def cliCreate(self):
		newConf = self.configParser.cliCreate()
		self.setValue(newConf)
		
	def cliChange(self):
		newConf = self.configParser.cliChange(self.getValue(path=[],hidePasswords=True)) #self.value
		self.setValue(newConf)
		
	def proposeSave(self,display=True,filename=None,path=[]):
		if filename is not None:
			self.setFilename(filename,path)
		if display:
			self.display()
		if self.filename is not None:
			if Prompt.promptYN("Save in file {0}?".format(self.filename),default='N',cleanScreen=False):
				self.save(path=path)
				print "Saved!"
				return True
			else:
				print "Not saved!"
				return False
		else:
			raise Exception("No filename specified")
			
	def save(self,filename=None,path=[]):
		if filename is not None:
			self.setFilename(filename,path)
		if self.filename is None:
			raise Exception("No file specified")
		path = list(self.path)
		try:
			with open(self.filename,encoding='utf8') as data_file:
				existingData = json.load(data_file)
		except:
			# File not exists yet
			if len(path)>0:
				raise Exception("File does not exist, path must be empty")
			existingData = {}
			
		data = existingData
		if len(path)==0:
			existingData = self.getValue(path=[],hidePasswords=False)
		else:
			while len(path)>1:
				level = path.pop(0)
				try:
					data = data[level]
				except:
					raise Exception("path cannot be reached: " + unicode(path))
			level = path.pop(0)
			data[level] = self.getValue(path=[],hidePasswords=False)
		try:
			with open(self.filename, 'w') as outfile:
				json.dump(existingData, outfile,encoding='utf8') #self.value
		except:
			raise Exception("Unable to write file {0}".format(unicode(self.filename)))

	def load(self,filename=None,path=[]):
		if filename is not None:
			self.setFilename(filename,path)
		if self.filename is None:
			raise Exception("No file specified")
		try:
			with open(self.filename,encoding='utf8') as data_file:
				data = json.load(data_file)
		except:
			raise Exception("Unable to read file {0}".format(unicode(self.filename)))
		try:
			path = list(self.path)
			while len(path)>0:
				data = data[path.pop(0)]
		except:
			raise Exception("path cannot be reached: " + unicode(path))
		self.setValue(data)
			
	def setFilename(self,filename=None,path=[]):
		if filename is None:
			self.filename = None
			return
		if not isinstance(filename,str) and not isinstance(filename,unicode):
			raise TypeError("Filename must be a string. {0} entered".format(unicode(filename)))
		if not isinstance(path,list):
			raise TypeError("path parameter must be a list")
		self.filename = filename
		self.path = path

	def keys(self):
		return self.value.keys()

	def __getitem__(self,key):
		if self.value is None:
			raise IndexError
		if self.configParser.getType() in ['object','array']:
			return self.value[key]
		else:
			raise TypeError("value is not object nor list")
	
	def __str__(self):
		if self.configParser.getType() == 'object':
			return u"Object"
		elif self.configParser.getType() == 'array':
			return u"Array ({0})".format(unicode(len(self.value)))
		elif self.configParser.getType() == "integer":
			return unicode(self.value).encode('utf8')
		elif self.configParser.getType() == "boolean":
			return unicode(self.value).encode('utf8')
		else:
			return self.value.encode('utf8')
		
	def setValue(self,src_value,path=[]):
		value = copy.deepcopy(src_value)
		configParser = self.getConfigParser(path)
		if configParser.getType() == 'object':
			if not isinstance(value,dict):
				raise Exception(unicode(path)+": "+unicode(value) +" received, dict excepted (path="+unicode(path)+")")
			result = {}
			for prop in value.keys():
				if prop not in configParser['properties']:
					raise Exception(unicode(prop)+": unknown property")
				propProperties = configParser['properties'][prop]
				result[prop] = JSAGdata(propProperties,propProperties._convert(value[prop]))
			configParser.validate(toJSON(result,hidePasswords=False)) # ICI !!!
		elif configParser.getType() == 'array':
			if not isinstance(value,list):
				raise Exception(unicode(path)+": "+unicode(value) +" received, list excepted")
			propProperties = configParser['items']
			result = []
			result = [JSAGdata(propProperties,propProperties._convert(val)) for val in value if val is not None]
			json = toJSON(result,hidePasswords=False)
			configParser.validate(json)
		elif configParser.getType() in SIMPLE_TYPES:
			result = copy.copy(value)
			configParser.validate(result)
		self.value = result

	def getValue(self,path=[],hidePasswords=True):
		value = self #.value
		if len(path) > 0:
			for level in path:
				if value.getType() == 'object' and level in value.value.keys():
					value = value[level]
				elif value.getType() == 'array' and len(value.value	) > level:
					value = value[level]
				else:
					return None
		return toJSON(value,hidePasswords)

	def getConfigParser(self,path=[]):
		configParser = self.configParser
		if len(path) > 0:
			for level in path:
				if isinstance(level,int):
					configParser = configParser['items']
				else:
					configParser = configParser['properties'][level]
		return configParser
		
	def getType(self,path=[]):
		configParser = self.getConfigParser(path)
		return configParser.getType()

	def update(self,value,appendArray=False):
		self.value = deepupdate(toJSON(self.value,hidePasswords=False),value,appendArray)
		self.configParser.validate(self.getValue())

	def choose(self,path=[]):
		value = self.getValue(path)
		configParser = self.getConfigParser(path)
		if (configParser.getType() in SIMPLE_TYPES) or (configParser.getType() == 'array' and configParser['items'].getType() in SIMPLE_TYPES) or value is None:
			parent = self.getValue(path[:-1])
			parent[path[-1]] = configParser.cliCreate()
		else:
			lines = self.displayConf(path=path,maxLevel=1)
			question = lines[0]['pattern'].format('',lines[0]['label'],lines[0]['value'])
			choices = []
			width = getWidth(lines,maxLevel=1)
			target_path = []
			for key,line in enumerate(lines[1]):
				label = pattern.SIMPLE.format('',line['label'])
				line['value'] = line['value']
				choices.append(('{0:' + unicode(max(width,0)+15) + '}{1}').format(label,line['value']))
				target_path.append(line['path'])
			reponse = Prompt.promptChoice(question,choices,warning='',selected=[],default = None,mandatory=True,multi=False)
			self.choose(target_path[reponse])

	def display(self,path=[],maxLevel=-1,cleanScreen=True):
		lines = self.displayConf(path=path,maxLevel=maxLevel)
		width = getWidth(lines)
		if cleanScreen:
			print(chr(27) + "[2J")
		printList(lines,ident='',width=width)
		
	def displayConf(self,path=[],maxLevel=-1,key=''):
		lines = []
		value = self.getValue(path)
		configParser = self.getConfigParser(path)
		if configParser.getType() == 'object':
			if value is None:
				val = "Not managed"
			else:
				if maxLevel != 0:
					val = ''
				else:
					val = "Managed"
			lines.append({'pattern':pattern.DICT,"label":configParser['title']+key,"value":val,"path":path})
			if maxLevel !=0 and value is not None:
				lines.append([])
				for item in sorted(configParser['properties'].iteritems(),key=lambda k:k[1]['order'] if 'order' in k[1].keys() else 0):
					lines[1] +=self.displayConf(path=path+[item[0]],maxLevel=maxLevel-1)
		# array
		elif configParser.getType() == 'array':
			if value is None or len(value)<1:
				val = "0 managed"
			else:
				if maxLevel != 0:
					val = ''
				else:
					val = unicode(len(value)) + " managed"
			label = "List of " + configParser['title']
			lines.append({'pattern':pattern.LIST,"label":label,"value":val,"path":path})
			if value is not None and maxLevel != 0:
				lines.append(self.displayList(path=path,maxLevel=maxLevel-1))
				

		# Simple
		else:
			val = value if value is not None else "None"
			lines.append({'pattern':pattern.SIMPLE,"label":configParser['title'],"value":val,"path":path})
		return lines
			
	def displayList(self,path=[],maxLevel=-1):
		lines = []
		value = self.getValue(path)
		configParser = self.getConfigParser(path)
		for key,item in enumerate(value):
			if configParser['items'].getType() == 'object':
				lines+=self.displayConf(path=path+[key],maxLevel=maxLevel,key=' '+unicode(key+1))
			elif configParser['items'].getType() == 'array':
				lines.append({'pattern':pattern.LIST,"label":configParser['title']+' '+unicode(key+1),"value":'',"path":path})
			else:
				value = unicode(item)
				lines.append({'pattern':pattern.SIMPLE,"label":configParser['title']+' '+unicode(key+1),"value":value,"path":path})
		return lines
