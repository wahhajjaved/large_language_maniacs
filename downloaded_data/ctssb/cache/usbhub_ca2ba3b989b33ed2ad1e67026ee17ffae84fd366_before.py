#!/usr/bin/env python
#coding:utf8
#omron plc hostlink c-mode command driver
#miaofng@2015-9-22 initial version

import sys, os, signal
import serial #http://pythonhosted.org/pyserial/
import re
import functools
import time
import io
import random

class PlcIoError(Exception):
	emsg = {
		0x00: "Normal Completion",
		0x01: "Not executable in RUN mode",
		0x02: "Not executable in MONITOR mode",
		0x03: "UM write-protected",
		0x04: "Address over",
		0x0B: "Not executable in PROGRAM mode",
		0x13: "FCS error",
		0x14: "Format error",
		0x15: "Entry number data error",
		0x16: "Command not supported",
		0x18: "Frame length error",
		0x19: "Not executable",
		0x20: "Could not create I/O table",
		0x21: "Not executable dueto CPU unit CPU error",
		0x23: "User memory protected",
		0xA3: "Aborted dueto FCS error in transmit data",
		0xA4: "Aborted dueto format error in transmit data",
		0xA5: "Aborted dueto entry number data error in transmit data",
		0xA8: "Aborted dueto frame length error in transmit data",

		#miaofng added
		"EFCS": "PLC FCS Error",
		"EACK": "PLC NO Response OR Length Error",
	}

	def __init__(self, code=0xFFFF):
		print(self.emsg[code])
		Exception.__init__(self)

class Plc:
	timeout = 1 #unit: S

	def __del__(self):
		if self.uart:
			self.uart.close()
			self.uart = None

	def __init__(self, port, baud=115200):
		self.uart = serial.Serial(port, baud,
			serial.SEVENBITS,
			serial.PARITY_EVEN,
			serial.STOPBITS_TWO,
			timeout = self.timeout,
			writeTimeout = self.timeout
		)
		self.sio = io.TextIOWrapper(
			io.BufferedRWPair(self.uart, self.uart, 1),
			newline = '\r',
			line_buffering = True
		)
		self.cio_read = functools.partial(self.__read__, header = "RR")
		self.cio_write = functools.partial(self.__write__, header = "WR")
		self.dm_read = functools.partial(self.__read__, header = "RD")
		self.dm_write = functools.partial(self.__write__, header = "WD")
		self.__mode__("MONITOR")

	def __cksum__(self, frame):
		fcs = 0
		for byte in frame:
			fcs = fcs ^ ord(byte)
		return fcs

	def __mode__(self, mode):
		list = {
			"PROGRAM": 0x00,
			"MONITOR": 0x02,
			"RUN" : 0x03,
		}
		mode = list[mode]

		cmd = []
		cmd.append("@00")
		cmd.append("SC")
		cmd.append("%02X"%mode)
		fcs = self.__cksum__(''.join(cmd))
		cmd.append("%02X*\r"%fcs)
		cmdline = ''.join(cmd)
		#self.uart.flushInput()
		#self.sio.readall()
		self.sio.write(unicode(cmdline))

		#"@00WR??FcsFcs*\r"
		echo = self.sio.readline()
		if len(echo) != 11:
			print("echo = '%s'"%echo)
			raise PlcIoError("EACK")

		fcs_echo = int(echo[7:9], 16)
		fcs = self.__cksum__(echo[:7])
		if fcs != fcs_echo:
			print("echo = '%s'"%echo)
			raise PlcIoError("EFCS")
		else:
			EndCode = int(echo[5:7], 16)
			if EndCode != 0:
				print("echo = '%s'"%echo)
				raise PlcIoError(EndCode)

	def __read__(self, addr, N=1, header=""):
		cmd = []
		cmd.append("@00")
		cmd.append(header)
		cmd.append("%04d"%addr)
		cmd.append("%04d"%N)
		fcs = self.__cksum__(''.join(cmd))
		cmd.append("%02X*\r"%fcs)
		cmdline = ''.join(cmd)
		#self.uart.flushInput()
		#self.sio.readall()
		self.sio.write(unicode(cmdline))

		#"@00WR??DAT0DAT1....FcsFcs*\r"
		echo = self.sio.readline()
		if len(echo) != 11+4*N:
			print("echo = '%s'"%echo)
			raise PlcIoError("EACK")

		data = echo[7+4*N:9+4*N]
		fcs_echo = int(data, 16)
		data = echo[:7+4*N]
		fcs = self.__cksum__(data)
		if fcs != fcs_echo:
			print("echo = '%s'"%echo)
			raise PlcIoError("EFCS")
		else:
			data = echo[5:7]
			EndCode = int(data, 16)
			if EndCode != 0:
				print("echo = '%s'"%echo)
				raise PlcIoError(EndCode)

		result = []
		for i in range(0, N):
			data = echo[7+i*4:11+i*4]
			data = int(data, 16)
			result.append(data)

		if N is 1:
			result = result[0]
		return result

	def __write__(self, addr, data, header=""):
		cmd = []
		cmd.append("@00")
		cmd.append(header)
		cmd.append("%04d"%addr)
		if type(data) is list:
			for val in data:
				cmd.append("%04X"%val)
		else:
			cmd.append("%04X"%data)
		fcs = self.__cksum__(''.join(cmd))
		cmd.append("%02X*\r"%fcs)
		cmdline = ''.join(cmd)
		#self.uart.flushInput()
		#self.sio.readall()
		self.sio.write(unicode(cmdline))

		#"@00WR??FcsFcs*\r"
		echo = self.sio.readline()
		if len(echo) != 11:
			print("echo = '%s'"%echo)
			raise PlcIoError("EACK")

		fcs_echo = int(echo[7:9], 16)
		fcs = self.__cksum__(echo[:7])
		if fcs != fcs_echo:
			print("echo = '%s'"%echo)
			raise PlcIoError("EFCS")
		else:
			EndCode = int(echo[5:7], 16)
			if EndCode != 0:
				print("echo = '%s'"%echo)
				raise PlcIoError(EndCode)

class Fixture(Plc):
	def GetID(self, station):
		id = self.cio_read(3)
		if station is 0:
			#left fixture
			id = (id >> 4) & 0x0f
		else:
			#right fixture
			id = (id >> 0) & 0x0f
		return id

	def IsEstop(self):
		#tester handle this signal as test stop
		status = self.cio_read(0)
		estop = status & (1 << 2)
		return estop

	def Start(self, station):
		#cleared by pc until 'READY' received
		self.dm_write(12, 1+station)

	def IsReady(self, station):
		#cleared by plc until 'PASS' or 'FAIL' received
		ready = 0
		if station is 0:
			ready = self.dm_read(26)
		else:
			ready = self.dm_read(28)

		if ready:
			#clear fixture start signal
			self.dm_write(12, 0)
		return ready

	def Signal(self, station, signal):
		#signal could be "PASS" "FAIL" "BUSY" "OFF"
		addr = 14 + station
		vals = {"PASS":3, "FAIL":2, "BUSY":1, "OFF":0}
		value = vals[signal]
		self.dm_write(addr, value)

	def IsUutPresent(self, station):
		#sensor not exist yet
		return True

	def ClearWasteCount(self):
		self.dm_write(30, 0)

	def ReadWasteCount(self):
		return self.dm_read(30)

######################module self test######################
if __name__ == '__main__':
	def cmd_cio_read(plc, argc, argv):
		addr = 0
		len = 1
		if argc > 1:
			addr = int(argv[1])
		if argc > 2:
			len = int(argv[2])

		result = plc.cio_read(addr, len)
		return str(result)+"\r\n"

	def cmd_cio_write(plc, argc, argv):
		if argc > 2:
			addr = int(argv[1])
			value = int(argv[2])
			plc.cio_write(addr, value)

	def cmd_dm_read(plc, argc, argv):
		addr = 0
		len = 1
		if argc > 1:
			addr = int(argv[1])
		if argc > 2:
			len = int(argv[2])

		result = plc.dm_read(addr, len)
		return str(result)+"\r\n"

	def cmd_dm_write(plc, argc, argv):
		if argc > 2:
			addr = int(argv[1])
			value = int(argv[2])
			plc.dm_write(addr, value)

	def cmd_debug(fixture, argc, argv):
		station = 1
		id = fixture.GetID(station)
		print "FixtureID = %d\r\n"%id
		if not id:
			return "Fixture Not Exist, Exit\r\n"

		while True:
			#1, barcode could be scanned several times until uut present
			#2, pass/fail led = fast flash once the barcode is gotten
			#3, gui display a gif picture to point out workstation
			#4, fixture start
			#5, tester locked until fixture ready
			print "Please Scan the Barcode...\r\n"
			for i in range(0, 3):
				sec = 3 - i
				#print "%ds\r\n"% sec
				time.sleep(1)
			print "barcode = %d\r\n" % random.randint(1000, 9999)
			fixture.Start(station)
			print "fixture started\r\n"
			print "Please Put the UUT into fixture ..\r\n"
			while not fixture.IsReady(station):
				time.sleep(0.001)
				if True:
					#not self.IsUutPresent(station):
					fixture.Signal(station, "OFF")
					time.sleep(0.025)
					fixture.Signal(station, "BUSY")
					time.sleep(0.025)
			print "fixture is ready, testing...\r\n"
			time.sleep(10)
			passed = random.randint(0, 1)
			if passed:
				fixture.Signal(station, "PASS")
				print("Test Passed\r\n")
			else:
				fixture.Signal(station, "FAIL")
				print("Test Failed\r\n")
				wastes = fixture.ReadWasteCount()

			if False:
				print "Please Remove the UUT from Fixture"
				while fixture.IsUutPresent(station):
					time.sleep(0.001)

			if not passed:
				print "waste count = %d\r\n"%wastes
				print "Put the UUT to the Waste Box...\r\n"
				while True:
					time.sleep(0.001)
					n = fixture.ReadWasteCount()
					if n != wastes:
						print "waste count = %d\r\n"%n
						break

			#fixture.Signal(station, "OFF")
			print "Test Finished\r\n"

	def signal_handler(signal, frame):
		sys.exit(0)

	from shell import Shell
	signal.signal(signal.SIGINT, signal_handler)
	fixture = Fixture("COM1")
	saddr = ('localhost', 10003)
	shell = Shell(saddr)
	shell.register("rr", functools.partial(cmd_cio_read, fixture), "rr 10")
	shell.register("wr", functools.partial(cmd_cio_write, fixture), "wr 10 5")
	shell.register("rd", functools.partial(cmd_dm_read, fixture), "rd 10")
	shell.register("wd", functools.partial(cmd_dm_write, fixture), "wd 10 5")
	shell.register("debug", functools.partial(cmd_debug, fixture), "test [left|right|dual]")

	while True:
		shell.update()
