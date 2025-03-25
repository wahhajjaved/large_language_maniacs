from config import config, ConfigSubsection, ConfigSelection, ConfigSlider, ConfigYesNo, ConfigNothing
from enigma import eDBoxLCD, eTimer
from Components.SystemInfo import SystemInfo
from os import path
import usb

def IconCheck(session=None, **kwargs):
	if path.exists("/proc/stb/lcd/symbol_network") or path.exists("/proc/stb/lcd/symbol_usb"):
		global networklinkpoller
		networklinkpoller = IconCheckPoller()
		networklinkpoller.start()

class IconCheckPoller:
	def __init__(self):
		self.timer = eTimer()

	def start(self):
		if self.iconcheck not in self.timer.callback:
			self.timer.callback.append(self.iconcheck)
		self.timer.startLongTimer(0)

	def stop(self):
		if self.iconcheck in self.timer.callback:
			self.timer.callback.remove(self.iconcheck)
		self.timer.stop()

	def iconcheck(self):
		if path.exists("/proc/stb/lcd/symbol_network"):
			LinkState = 0
			if path.exists('/sys/class/net/wlan0/operstate'):
				LinkState = open('/sys/class/net/wlan0/operstate').read()
				if LinkState != 'down':
					LinkState = open('/sys/class/net/wlan0/operstate').read()
			elif path.exists('/sys/class/net/eth0/operstate'):
				LinkState = open('/sys/class/net/eth0/operstate').read()
				if LinkState != 'down':
					LinkState = open('/sys/class/net/eth0/carrier').read()
			LinkState = LinkState[:1]
			file = open("/proc/stb/lcd/symbol_network", "w")
			file.write('%d' % int(LinkState))
			file.close()
		if path.exists("/proc/stb/lcd/symbol_usb"):
			USBState = 0
			busses = usb.busses()
			for bus in busses:
				devices = bus.devices
				for dev in devices:
					if dev.deviceClass != 9 and dev.deviceClass != 2 and dev.idVendor > 0:
						print ' '
						print "Device:", dev.filename
						print "  Number:", dev.deviceClass
						print "  idVendor: %d (0x%04x)" % (dev.idVendor, dev.idVendor)
						print "  idProduct: %d (0x%04x)" % (dev.idProduct, dev.idProduct)
						USBState = 1
			file = open("/proc/stb/lcd/symbol_usb", "w")
			file.write('%d' % int(USBState))
			file.close()
		self.timer.startLongTimer(30)

class LCD:
	def __init__(self):
		pass

	def setBright(self, value):
		value *= 255
		value /= 10
		if value > 255:
			value = 255
		eDBoxLCD.getInstance().setLCDBrightness(value)

	def setContrast(self, value):
		value *= 63
		value /= 20
		if value > 63:
			value = 63
		eDBoxLCD.getInstance().setLCDContrast(value)

	def setInverted(self, value):
		if value:
			value = 255
		eDBoxLCD.getInstance().setInverted(value)

	def isOled(self):
		return eDBoxLCD.getInstance().isOled()

	def setMode(self, value):
		file = open("/proc/stb/lcd/show_symbols", "w")
		file.write('%d' % int(value))
		file.close()
		print "[LCD] set mode to %d" % int(value)

	def setRepeat(self, value):
		file = open("/proc/stb/lcd/scroll_repeats", "w")
		file.write('%d' % int(value))
		file.close()
		print "[LCD] set repeat to %d" % int(value)

	def setScrollspeed(self, value):
		file = open("/proc/stb/lcd/scroll_delay", "w")
		file.write('%d' % int(value))
		file.close()
		print "[LCD] set scrollspeed to %d" % int(value)

def leaveStandby():
	config.lcd.bright.apply()

def standbyCounterChanged(configElement):
	from Screens.Standby import inStandby
	inStandby.onClose.append(leaveStandby)
	config.lcd.standby.apply()

def InitLcd():
	detected = eDBoxLCD.getInstance().detected()
	SystemInfo["Display"] = detected
	config.lcd = ConfigSubsection();
	if detected:
		def setLCDbright(configElement):
			ilcd.setBright(configElement.value);

		def setLCDcontrast(configElement):
			ilcd.setContrast(configElement.value);

		def setLCDinverted(configElement):
			ilcd.setInverted(configElement.value);

		def setLCDmode(configElement):
			ilcd.setMode(configElement.value);

		def setLCDrepeat(configElement):
			ilcd.setRepeat(configElement.value);

		def setLCDscrollspeed(configElement):
			ilcd.setScrollspeed(configElement.value);

		standby_default = 0

		ilcd = LCD()

		if not ilcd.isOled():
			config.lcd.contrast = ConfigSlider(default=5, limits=(0, 20))
			config.lcd.contrast.addNotifier(setLCDcontrast);
		else:
			config.lcd.contrast = ConfigNothing()
			standby_default = 1

		config.lcd.standby = ConfigSlider(default=standby_default, limits=(0, 10))
		config.lcd.standby.addNotifier(setLCDbright);
		config.lcd.standby.apply = lambda : setLCDbright(config.lcd.standby)

		config.lcd.bright = ConfigSlider(default=5, limits=(0, 10))
		config.lcd.bright.addNotifier(setLCDbright);
		config.lcd.bright.apply = lambda : setLCDbright(config.lcd.bright)
		config.lcd.bright.callNotifiersOnSaveAndCancel = True

		config.lcd.invert = ConfigYesNo(default=False)
		config.lcd.invert.addNotifier(setLCDinverted);

		if path.exists("/proc/stb/lcd/scroll_delay"):
			config.lcd.mode = ConfigSelection([("0", _("No")), ("1", _("Yes"))], "1")
			config.lcd.mode.addNotifier(setLCDmode);
			config.lcd.repeat = ConfigSelection([("0", _("None")), ("1", _("1X")), ("2", _("2X")), ("3", _("3X")), ("4", _("4X")), ("500", _("Continues"))], "3")
			config.lcd.repeat.addNotifier(setLCDrepeat);
			config.lcd.scrollspeed = ConfigSlider(default = 150, increment = 10, limits = (0, 500))
			config.lcd.scrollspeed.addNotifier(setLCDscrollspeed);
		else:
			config.lcd.mode = ConfigNothing()
			config.lcd.repeat = ConfigNothing()
			config.lcd.scrollspeed = ConfigNothing()

	else:
		def doNothing():
			pass
		config.lcd.contrast = ConfigNothing()
		config.lcd.bright = ConfigNothing()
		config.lcd.standby = ConfigNothing()
		config.lcd.bright.apply = lambda : doNothing()
		config.lcd.standby.apply = lambda : doNothing()
		config.lcd.mode = ConfigNothing()
		config.lcd.repeat = ConfigNothing()
		config.lcd.scrollspeed = ConfigNothing()

	config.misc.standbyCounter.addNotifier(standbyCounterChanged, initial_call = False)

