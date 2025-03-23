import serial
import logging
import time
import x10


def test(tty):
	port = serial.Serial(tty, 9600, timeout=10)
	port.open()
	port.write(chr(0x02))
	
	result = port.read()
	if len(result) == 0:
		raise Exception, "Timeout reading from serial"
	else:
		return hex(ord(result[0]))
	

class PowerLincSerial(object):
	"""Controller for the 1132B PowerLinc Serial device"""
	
	# All raw x10 values get or'd with 0x40 for sending to PowerLinc
	HOUSE_CODES = dict(
		A=0x06, B=0x0e, C=0x02, D=0x0a,
		E=0x01, F=0x09, G=0x05, H=0x0d,
		I=0x07, J=0x0f, K=0x03, L=0x0b,
		M=0x00, N=0x08, O=0x04, P=0x0c)
	HOUSE_CODES = dict([(key, code|0x40) for key, code in HOUSE_CODES.iteritems()])
	
	# All raw x10 values get or'd with 0x40 for sending to PowerLinc
	UNIT_CODES = [
		0x00,	# a placeholder, there is no unit 0
		0x0c, 0x1c, 0x04, 0x14,
		0x02, 0x12, 0x0a, 0x1a,
		0x0e, 0x1e, 0x06, 0x16,
		0x00, 0x10, 0x08, 0x18]
	UNIT_CODES = [code|0x40 for code in UNIT_CODES]
		
	# All raw x10 values get or'd with 0x40 for sending to PowerLinc
	COMMAND_CODES = {
		x10.Cmd.ALL_UNITS_OFF: 0x01,
		x10.Cmd.ALL_LIGHTS_ON: 0x03,
		x10.Cmd.ON: 0x05,
		x10.Cmd.OFF: 0x07,
		x10.Cmd.DIM: 0x09,
		x10.Cmd.BRIGHT: 0x0b,
		x10.Cmd.ALL_LIGHTS_OFF: 0x0d,
		x10.Cmd.EXTENDED_CODE: 0x0f,
		x10.Cmd.HAIL_REQUEST: 0x11,
		x10.Cmd.PRESET_DIM_HIGH: 0x17,
		x10.Cmd.PRESET_DIM_LOW: 0x15,
		x10.Cmd.EXTENDED_DATA: 0x19,
		x10.Cmd.STATUS_ON: 0x1b,
		x10.Cmd.STATUS_OFF: 0x1d,
		x10.Cmd.STATUS_REQUEST: 0x1f,
		"unknown": 0x13
	}
	COMMAND_CODES = dict([(key, code|0x40) for key, code in COMMAND_CODES.iteritems()])
	
	# codes
	START = 0x02
	ACK = 0x06
	NAK = 0x15
	CR = 0x0d
	SEND = 0x63
	REPEAT_ONCE = 0x41
	RECEIVED = 0x58

	def __init__(self, tty):
		"""Must be initialized with a tty device like '/dev/ttyUSB0'"""
		self.serial = serial.Serial(tty, 9600, timeout=10)
		
	def send(self, command, house_unit):
		"""Shortcut for values like 'M1' and 'M2'"""
		house = house_unit[0]
		unit = int(house_unit[1:])
		self.send_house_unit(command, house, unit)
		
	def send_house_unit(self, command, house, unit):
		"""Send the command to the house and unit.  House is a letter A-P, unit is 0-16"""
		self.serial.open()
		self.make_ready()
		
		house_code = PowerLincSerial.HOUSE_CODES[house]
		
		if command:
			command_code = PowerLincSerial.COMMAND_CODES[command]
		else:
			command_code = 0x0
		
		if unit:
			unit_code = PowerLincSerial.UNIT_CODES[unit]
		else:
			# This is fucked up but that's what the docs say
			unit_code = command_code
			command_code = 0x0
		
		tosend = [PowerLincSerial.SEND, house_code, unit_code, command_code, PowerLincSerial.REPEAT_ONCE]
		tosend = ''.join([chr(b) for b in tosend])
		self.serial.write(tosend)
		
		self.read_received()
		
		self.serial.close()
		
	def read_received(self):
		"""Read the weird messages off the wire"""
		result = self.readByte()
		if result != PowerLincSerial.RECEIVED:
			raise Exception, "Instead of RECEIVED got " + hex(result)

		time.sleep(0.5)
		self.serial.flushInput()
		
	def make_ready(self):
		tries = 0
		while True:
			self.writeByte(PowerLincSerial.START)
			byte = self.readByte()
			
			if byte == PowerLincSerial.ACK:
				self.readByte() # toss the cr
				return
			elif byte == PowerLincSerial.NAK:
				if tries > 5:
					raise Exception, "Too many NAK responses"
				else:
					tries += 1
					logging.debug("Got NAK")
					time.sleep(0.5)
			else:
				raise Exception, "Read unexpected byte " + hex(byte)
		
	def writeByte(self, byte):
		"""Write one byte"""
		self.serial.write(chr(byte))
			
	def readByte(self):
		"""Read one byte"""
		result = self.serial.read()
		if len(result) == 0:
			raise Exception, "Timeout reading from serial"
		else:
			return ord(result[0])
