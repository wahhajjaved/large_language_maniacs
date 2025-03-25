#Module that handles creation of the XML document
import parseutil
import customExceptions
import util
import paths
import os
import message
import devicecap
import extractor
import subprocess
import shutil
import mmap
import struct
from collections import namedtuple, OrderedDict, deque
from schemadata import Element

Address = namedtuple("Address", "start end")

class ProcessorCreator():

	@staticmethod
	def createElem():
		print "> Creating element: processor"
		cpuinfo = extractor.extractData(paths.CPUINFO)
		processor = Element("processor", "processorType")
		processor["logicalCpus"] = parseutil.count(cpuinfo,"processor")
		processor["speed"] = float(parseutil.parseData_Sep(cpuinfo, "cpu MHz", ":"))
		processor["vmxTimerRate"] = ProcessorCreator.getVmxTimerRate()
		print "Element created: processor"
		return processor

	@staticmethod
	def getVmxTimerRate():
		#check for MSR
		vmxTimerRate = 0
		MSRfound = False
		OFFSET = 0x485
		VMX_BITS_START = 0
		VMX_BITS_END = 4
		for path in paths.MSR:
			try:
				#Try to find MSR file
				byte = extractor.extractBinaryData(path, OFFSET, 1)[0]
			except IOError:
				continue
			else:
				MSRfound = True
				break

		if MSRfound is False:
			errormsg = "MSR could not be located at directories:\n"
			for path in paths.MSR:
				errormsg += ("%s\n" % path)

			errormsg += ("vmxTimerRate could not be found. Try 'modprobe msr' to "
						 "probe for MSR, then run the tool again.\n"
						 "Alternatively, run the tool again with the proper "
						 "permissions." )
			message.addError(errormsg)
		else:
			vmxbits = 0
			#Get bits from VMX_BITS_START to VMX_BITS_END
			for bitnum in range(VMX_BITS_START, VMX_BITS_END+1):
				vmxbits += util.getBit(int(byte, 16), bitnum) << bitnum
			vmxTimerRate = int(vmxbits)

		return vmxTimerRate

class MemoryCreator():

	@staticmethod
	def createElem():
		print "> Creating element: memory"

		memory = Element("memory", "physicalMemoryType")
		#Get list of memoryBlocks available
		memoryBlockList = MemoryCreator.getMemoryBlocks(paths.MEMMAP)

		for memoryBlock in memoryBlockList:
			memory.appendChild(memoryBlock)
		print "Element created: memory"
		return memory

	@staticmethod
	def getMemoryBlocks(path):
		memoryBlockList = []
		def walkError(excep):
			message.addError("Could not access memory block data: " +\
							 str(excep), False)
		for root,subdirs,files in os.walk(path, onerror=walkError):
			if not subdirs:  #at end of paths

				endfile = root + "/" + "end"
				typefile = root + "/" + "type"
				startfile = root + "/" + "start"
				try:
					memoryBlock = MemoryCreator.generateMemoryBlock(endfile,
																	typefile,
																	startfile)
				except IOError:
					message.addError("Could not retrieve complete memory data",
									 False)
				#Adds newly created memoryBlock element to memoryBlockList
				memoryBlockList.append(memoryBlock)

		return memoryBlockList

	@staticmethod
	def generateMemoryBlock(endfile,typefile,startfile):
		memoryBlock = Element("memoryBlock", "memoryBlockType")

		memoryBlock["name"] = extractor.extractData(typefile)
		if MemoryCreator.isAllocatable(memoryBlock["name"]):
			memoryBlock["allocatable"] = "true"
		else:
			memoryBlock["allocatable"] = "false"

		memoryBlock["physicalAddress"] = util.toWord64(
			extractor.extractData(startfile)
			)
		memoryBlock["size"] = util.toWord64(
			util.sizeOf(extractor.extractData(endfile),
						extractor.extractData(startfile) )
			)

		return memoryBlock



	@staticmethod
	def isAllocatable(name):
		if name == "System RAM":
			return True
		else:
			return False

class DevicesCreator():

	@staticmethod
	def createElem():
		print "> Creating element: devices"
		devices = Element("devices", "devicesType")
		devices["pciConfigAddress"] = util.toWord64(
			DevicesCreator.getPciConfigAddress(paths.IOMEM)
			)

		#Add IOMMUs
		print "Extracting IOMMU device information..."
		devices.appendChild(IommuDevicesCreator().createElems())

		#Add Serial Devices
		print "Extracting Serial device information..."
		devices.appendChild(SerialDevicesCreator().createElems())

		#Add Pci Devices
		print "Extracting PCI device information..."
		devices.appendChild(PciDevicesCreator().createElems())

		print "Element created: devices"

		return devices

	@staticmethod
	def getPciConfigAddress(path):
		pciconfigaddr = ""
		key = "PCI MMCONFIG"
		try:
			iomemdata = extractor.extractData(path)
			keyline = parseutil.findLines(iomemdata, key)[0]
			pciconfigaddr = keyline.split("-")[0]

		except (customExceptions.KeyNotFound, IOError):
			message.addWarning("Could not obtain pciConfigAddress from %s." % path)

		return pciconfigaddr


class PciDevicesCreator():
	"Helper class of DevicesCreator"
	def __init__(self):
		self.devicepaths = []
		self.capabilities = {} #devicepath = capabilitylist
		self.devicenames = {} #devicepath = name
		self.deviceShortNames = {} #devicepath = shortname

	def createElems(self):
		pcidevicelist = []
		print "Finding PCI devices..."
		self.devicepaths = self.findDevicePaths(paths.DEVICES)
		print "Checking Dependencies..."
		self.getDependencies()
		print "Examining PCI devices..."
		filteredpaths = self.filterDevicePaths(self.devicepaths)
		print ("Extracting device information from %d PCI devices " % len(filteredpaths) +
			   "(excluding PCI bridges and non PCI-Express devices behind bridges)...")
		for devicepath in filteredpaths:
			device = self.createDeviceFromPath(devicepath)
			pcidevicelist.append(device)

		return pcidevicelist

	def getDependencies(self):
		"Checks whether dependencies are fulfilled and fills up the class attributes"
		self.capabilities = self.getCapabilities(self.devicepaths)
		#self.devicenames = self.getDeviceNames(self.devicepaths)
		self.deviceShortNames = self.getDeviceShortNames(self.devicepaths)

	def findDevicePaths(self, path):
		"Gets paths to all PCI devices in system"
		devicePaths = []
		devicePaths = util.getLinks(path, self.isDeviceName)
		return devicePaths

	def filterDevicePaths(self, devicePaths):
		"Returns filtered list of paths of devices"
		bridgePaths = []
		pciExpressPaths = []
		bridgedDevicePaths = []
		nonPciExpressPaths = []
		resultPaths = []
		for devicepath in devicePaths:
			if self.isPciExpress(devicepath):
				pciExpressPaths.append(devicepath)

			if self.isBridge(devicepath):
				bridgePaths.append(devicepath)
				for root, subdirs, files in os.walk(devicepath):
					for subdir in subdirs:
						if self.isDeviceName(subdir):
							bridgedDevicePaths.append(os.path.join(root,subdir))

		for bridgedDevice in bridgedDevicePaths:
			if self.isPciExpress(bridgedDevice) is False:
				nonPciExpressPaths.append(bridgedDevice)

		print "PCI Devices found: %d\n------------------" % len(self.devicepaths)
		print "> PCI Bridges: ", len(bridgePaths)
		for item in bridgePaths:
			print "  ", os.path.basename(item)

		print "> Bridged Devices: ", len(bridgedDevicePaths)
		for item in bridgedDevicePaths:
			print "  ", os.path.basename(item)

		print "> PCI Express Devices: ", len(pciExpressPaths)
		for item in pciExpressPaths:
			print "  ", os.path.basename(item)

		resultPaths = util.removeListsFromList(devicePaths,
											   bridgePaths,
											   nonPciExpressPaths)
		return resultPaths

	def isBridge(self, devicepath):
		isBridge = False
		PCI_BRIDGE = "0x0604"
		if extractor.extractData(os.path.join(devicepath, "class"))[0:6] == PCI_BRIDGE:
			isBridge = True

		return isBridge

	def isPciExpress(self, devicepath):
		isPciExpress = False
		PCI_EXPRESS = "0x10"

		if PCI_EXPRESS in self.capabilities.get(devicepath):
			isPciExpress = True

		return isPciExpress

	def isDeviceName(self, value):
		"Checks for format: ####:##:##.#"
		splitcolon = value.split(':')
		if len(splitcolon) != 3:
			return False

		if '.' not in splitcolon[2]:
			return False

		if len(splitcolon[0]) != 4: #Host bus no. length
			return False
		
		if len(splitcolon[1]) != 2: #Bus no. length
			return False
		
		if len(splitcolon[2].split('.')[0]) != 2: #Device no. length
			return False
		
		if len(splitcolon[2].split('.')[1]) != 1: #Function no. length
			return False

		return True

	def getDeviceBus(self, devicestr):
		return devicestr.split(':')[1]

	def getDeviceNo(self, devicestr):
		return (devicestr.split(':')[2] ).split('.')[0]

	def getDeviceFunction(self, devicestr):
		return (devicestr.split(':')[2] ).split('.')[1]

	def getCapabilities(self, devicepaths):
		"Checks if device capabilities can be found"
		capabilities = {}

		#Initialise empty dictionary
		for devicepath in devicepaths:
			capabilities[devicepath] = []

		#Attempt to fill dictionary
		try:
			for devicepath in devicepaths:
				capabilities[devicepath] = devicecap.getCapability(devicepath)
		except customExceptions.NoAccessToFile:
			message.addError("Not enough permissions to access capabilities of "
							 "devices. It is advised to run the tool again with "
							 "the proper permissions.", False)

		return capabilities

	#TODO Unused for now, while device names are relying on class codes and not Vendor and Device pairs
	"""
	@staticmethod
	def getDeviceNames(devicepaths):
		"Gets device names from pci.ids"
		names = {}
		#Initialise names
		for devicepath in devicepaths:
			names[devicepath] = "NO_NAME"

		#Attempt to access pci.ids to retrieve device name
		try:
			pciIdsParser = parseutil.PciIdsParser(paths.PCIIDS)

		except customExceptions.PciIdsFileNotFound:
			message.addError("pci.ids file could not be located in tool directory: "
							 "%s. " % paths.CURRENTDIR + "Device names could not "
							 "be obtained.\nPlease ensure that the file is in "
							 "the directory.", False)

		else:
			for devicepath in devicepaths:
				try:
					venhex = extractor.extractData(os.path.join(devicepath,"vendor") )
					devhex = extractor.extractData(os.path.join(devicepath,"device") )
					names[devicepath] = pciIdsParser.getVendorName(venhex) #TODO Name constraint
				except customExceptions.PciIdsFailedSearch as e:
					message.addWarning(("Names for Device %s of Vendor %s could " +
									   "not be found. ") % (devhex,venhex) +\
									   "It would be a good idea to update pci.ids")

				except customExceptions.PciIdsMultipleEntries as e:
					message.addWarning("Multiple names for Device %s of Vendor %s " %
									   (devhex, venhex) + "were found. Please "
									   "insert the correct names manually in the "
									   "XML file.")

		return names
	"""

	def getDeviceShortNames(self, devicepaths):
		shortnames = OrderedDict()
		namecount = {}
		#Initialise PciIdsParser
		try:
			pciIdsParser = parseutil.PciIdsParser(paths.PCIIDS)

		except customExceptions.PciIdsFileNotFound:
			message.addError("pci.ids file could not be located in tool "
							 "directory: %s. " % paths.CURRENTDIR + "Device "
							 "names could not be obtained.\n"
							 "Please ensure that the file is in the directory.",
							 False)

		else:
			for devicepath in devicepaths:
				#Get class code from "class" file"
				classcode = extractor.extractData(
					os.path.join(devicepath, "class") )[0:6]
				classname = classcode
				try:
					classname = pciIdsParser.getClassName(classcode)

				except (customExceptions.PciIdsFailedSearch,
					customExceptions.PciIdsSubclassNotFound):
					message.addWarning(("Name for Device at: %s " % devicepath +
										"could not be found. It would " +
										"be a good idea to update pci.ids "+
										"(try '-update' or '-u')" ))

				classname = util.spacesToUnderscores(classname.lower())
				#Add entry to dictionary shortnames
				shortnames[devicepath] = classname

		namelist = []
		for value in shortnames.itervalues():
			namelist.append(value)

		listnumberer = util.ListNumberer(namelist)
		for devicepath in shortnames.iterkeys():
			shortnames[devicepath] = listnumberer.getName(shortnames[devicepath])

		return shortnames

	def createDeviceFromPath(self, devicepath):
		pcistr = os.path.basename(devicepath)
		device = Element("device", "deviceType")
		#Old code that gets device name as Vendor DeviceName
		#device["name"] = self.devicenames[devicepath]
		device["name"] = self.deviceShortNames[devicepath]
		device["shared"] = "false" #TODO Check for shared status sometime in the future

		#pci
		pci = Element("pci", "pciType")
		pci["bus", "device", "function"] = (util.wrap16(self.getDeviceBus(pcistr)),
											util.wrap16(self.getDeviceNo(pcistr)),
											self.getDeviceFunction(pcistr))
		device.appendChild(pci)

		#irq
		try:
			irqNo = extractor.extractData(os.path.join(devicepath,"irq"))
			if irqNo is not "0":
				irq = Element("irq", "irqType")
				irq["name", "number"] = "irq", irqNo
				device.appendChild(irq)

		except IOError:
			message.addError("Could not obtain irq number for device: %s" % pcistr,
							 False)

		#memory, includes expansion roms
		try:
			resourceData = extractor.extractData(os.path.join(devicepath,
															  "resource") )
			memcount = 0
			for line in resourceData.splitlines():
				tokens = line.split(' ')
				if tokens[2][-3] == '2': #if line represents a memory block

					memory = Element("memory", "deviceMemoryType")
					memory["name"] = "mem%d" % memcount
					memory["physicalAddress"] = util.toWord64(tokens[0])
					memory["size"] = util.toWord64(util.sizeOf(tokens[1],
															   tokens[0]) )
					memory["caching"] = "UC" #TODO
					device.appendChild(memory)
					memcount += 1

		except IOError:
			message.addError("Could not obtain memory information for device: "
							 "%s" % pcistr,
							 False)

		#ioports
		try:
			resourceData = extractor.extractData(os.path.join(devicepath,
															  "resource") )
			ioportcount = 0
			for line in resourceData.splitlines():
				tokens = line.split(' ')
				if tokens[2][-3] == '1': #if line represents ioport information

					ioPort = Element("ioPort", "ioPortType")
					ioPort["name"] = "ioport%d" % ioportcount
					ioPort["start"] = util.toWord64(tokens[0])
					ioPort["end"] = util.toWord64(tokens[1])
					ioportcount += 1
					device.appendChild(ioPort)

		except IOError:
			message.addError("Could not obtain ioport information for device: "
							 "%s" % pcistr,
							 False)

		#capabilities
		caplist = self.capabilities[devicepath]
		if caplist:
			capabilities = Element("capabilities", "capabilitiesType")
			for cap in caplist:
				capability = Element("capability", "capabilityType")
				capability["name"] = cap

				try:
					capability.setContent(devicecap.translate(cap))
				except customExceptions.CapabilityUnknown:
					message.addWarning("Capability code: %s is unknown. " % cap +
									   "It might be a good idea to update "
									   "'devicecap.py'.")
					capability.setContent(cap)

				capabilities.appendChild(capability)

			device.appendChild(capabilities)

		return device

class SerialDevicesCreator():
	"Helper class of DevicesCreator"

	def __init__(self):
		self.addresses = []
		self.COMADDRESSES = {
					Address("03f8", "03ff") : "com_1",
					Address("02f8", "02ff") : "com_2",
					Address("03e8", "03ef") : "com_3",
					Address("02e8", "02ef") : "com_4"
							} #TODO Check

	def createElems(self):
		serialdevicelist = []
		self.addresses = self.getSerialAddresses()
		#Get COM Device addresses
		for comdevice in self.createComDevices(self.COMADDRESSES):
			serialdevicelist.append(comdevice)
		#Filter COM devices from list
		filteredlist = util.removeListsFromList(self.addresses,
												self.COMADDRESSES.iterkeys() )
		for serialdevice in self.createSerialDevices(filteredlist):
			serialdevicelist.append(serialdevice)
		return serialdevicelist

	def getSerialAddresses(self):
		"Gets serial addresses in form (startaddr, endaddr)"
		serialAddresses = []
		KEYWORD = "serial"
		TTY_PATH = paths.TTY

		#Get all lines which include KEYWORD
		try:
			ioportdata = extractor.extractData(TTY_PATH)
		except IOError:
			message.addError("Could not access location: %s\n" % TTY_PATH +\
							 "Serial device addresses not found.", False)
		else:
			try:
				lines = parseutil.findLines(ioportdata, KEYWORD)
			except customExceptions.KeyNotFound:
				message.addMessage(
					"No serial devices found in file: %s" % TTY_PATH)
			else:
				#Retrieve (start,end) data for serial devices
				for line in lines:
					serialAddresses.append(self.getAddressFromLine(line))

		return serialAddresses

	def getAddressFromLine(self, line):
		"Parses line to obtain (start,end)"
		addrInfo = line.partition(":")[0].strip()
		start = addrInfo.partition("-")[0]
		end = addrInfo.partition("-")[2]
		addr = Address(start, end)
		return addr

	def createComDevices(self,comAddresses):
		comdevices = []
		comaddr = []
		for addr in self.addresses:
			if addr in self.COMADDRESSES:
				comaddr.append(addr)

		for addr in comaddr:
			device = Element("device", "deviceType")
			device["name"] = self.COMADDRESSES[addr]
			device["shared"] = "true"
			ioport = Element("ioPort", "ioPortType")
			ioport["name"] = "port"
			ioport["start"] = util.toWord64(addr.start)
			ioport["end"] = util.toWord64(addr.end)
			device.appendChild(ioport)
			comdevices.append(device)

		return comdevices

	def createSerialDevices(self,addresses):
		devices = []
		serialcount = 0
		for addr in addresses:
			device = Element("device", "deviceType")
			device["name"] = "serial_%d" % serialcount
			device["shared"] = "true"
			ioport = Element("ioPort", "ioPortType")
			ioport["name"] = "port"
			ioport["start"] = util.toWord64(addr.start)
			ioport["end"] = util.toWord64(addr.end)
			device.appendChild(ioport)
			devices.append(device)
			serialcount += 1

		return devices

class IommuDevicesCreator():
	def __init__(self):
		self.DMAR_TEMPNAME = "dmar.dat"
		self.DMAR_NAME = "dmar.dsl"
		self.OUTPUTPATH = paths.TEMP
		self.DEVMEM = paths.DEVMEM
		self.iommuaddrs = []
		self.iommunames = deque([])

	def createElems(self):
		elemlist = []
		print "Parsing DMAR table..."
		try:
			self.genDMAR(paths.DMAR, self.OUTPUTPATH)
		except customExceptions.DmarFileNotFound:
			message.addMessage("No DMAR file found at: '%s'; " % paths.DMAR +\
							   "IOMMU devices not detected.")
		except (customExceptions.DmarFileNotCopied,
				customExceptions.IaslToolNotFound):
			message.addError("Could not obtain DMAR information; IOMMU device "
							   "information not found.", False)
		else:
			self.iommuaddrs = self.getIommuAddrs(os.path.join(self.OUTPUTPATH,
															  self.DMAR_NAME) )
			for addr in self.iommuaddrs:
				elemlist.append(self.createDeviceFromAddr(addr))

		return elemlist

	def genDMAR(self, dmar, outputloc):
		"Creates Parsed DMAR file in temp folder"

		#Make temp folder if does not exist
		try:
			os.makedirs(outputloc)
		except OSError:
			if not os.path.isdir(outputloc):
				raise
			
		#Check if DMAR exists
		try:
			open(dmar,"r")
		except IOError:
			raise customExceptions.DmarFileNotFound("DMAR file not found at: "
													"%s" % dmar)
			return

		#Copy DMAR to temp folder
		try:
			tempfile = os.path.join(outputloc, self.DMAR_TEMPNAME)
			shutil.copyfile(dmar, tempfile)

		except IOError:
			message.addMessage("DMAR table at: '%s' " % dmar +\
							 "could not be copied to location: '%s'" % tempfile)
			raise customExceptions.DmarFileNotCopied("DMAR file could not be copied")

		else:
			#Parse temp file
			try:
				subprocess.call(["iasl","-d",tempfile], stdout=subprocess.PIPE)

			except OSError as e:
				if e.errno == os.errno.ENOENT: #iasl does not exist
					message.addMessage("iasl tool not found in the system. "+
							"Try 'apt-get install iasl' to install.")
				raise customExceptions.IaslToolNotFound()

	def getIommuAddrs(self, dmarfile):
		"Retrieves Register Base Addresses of IOMMUs from parsed DMAR"
		iommuaddrs = []
		KEY = "Register Base Address"
		try:
			dmardata = extractor.extractData(dmarfile)
		except IOError:
			message.addError("Could not find '%s' in location: %s." %
							 (self.DMAR_NAME, self.OUTPUTPATH), False)
		else:
			for line in dmardata.splitlines():
				try:
					addr = parseutil.parseLine_Sep(line, KEY, ":")
					addr = addr.lstrip("0")
					addr = "0x" + addr
					addr = addr.lower()
					iommuaddrs.append(addr)

				except customExceptions.KeyNotFound:
					pass

		return iommuaddrs

	def createDeviceFromAddr(self, iommuaddr):
		"Generates a device element from a given iommu address"
		MAP_MAX = "0x30"
		CAPABILITY_OFFSET = "0x08"
		AGAW_39_BITNO = 1
		AGAW_48_BITNO = 2
		IOMMU_SIZE = "1000"

		device = Element("device", "deviceType")
		device["shared"] = "false"

		#name attr
		for addr in self.iommuaddrs:
			self.iommunames.append("iommu")
		self.iommunames = deque(util.numberMultiples(self.iommunames))
		device["name"] = self.iommunames.popleft()

		#memory
		memory = Element("memory", "deviceMemoryType")
		memory["caching"] = "UC" #TODO
		memory["name"] = "mmio"
		memory["physicalAddress"] = util.toWord64(iommuaddr)
		memory["size"] = util.toWord64(IOMMU_SIZE)
		device.appendChild(memory)

		#capabilities
		capabilities = Element("capabilities", "capabilitiesType")
		## iommu
		iommucap = Element("capability", "capabilityType")
		iommucap["name"] = "iommu"
		capabilities.appendChild(iommucap)
		## agaw
		agawcap = Element("capability", "capabilityType")
		agawcap["name"] = "agaw"

		try:
			bytes = extractor.extractBinaryData(self.DEVMEM,
												int(CAPABILITY_OFFSET,0)+1, 1)
		except IOError:
			message.addError("Could not access file: %s" % self.DEVMEM, False)
		else:
			if util.getBit(int(bytes[0], 16),AGAW_39_BITNO):
				agawcap["name"] = "agaw39"
			elif util.getBit(int(bytes[0], 16), AGAW_48_BITNO):
				agawcap["name"] = "agaw48"
			else:
				message.addError("AGAW Capability could not be found for IOMMU "
								 "device.", False)

		capabilities.appendChild(agawcap)
		device.appendChild(capabilities)

		return device


def createElements():
	"Creates the element tree and returns top element"
	platform = Element("platform", "platformType")
	platform.appendChild(ProcessorCreator.createElem())
	platform.appendChild(MemoryCreator.createElem())
	platform.appendChild(DevicesCreator.createElem())

	return platform

