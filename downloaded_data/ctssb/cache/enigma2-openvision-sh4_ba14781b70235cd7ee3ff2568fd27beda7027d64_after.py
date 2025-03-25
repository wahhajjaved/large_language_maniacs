from Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.Harddisk import harddiskmanager
from Components.NimManager import nimmanager
from Components.About import about
from Components.ScrollLabel import ScrollLabel
from Components.Button import Button

from Tools.StbHardware import getFPVersion
from enigma import eTimer

class About(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)


		AboutText = _("Hardware: ") + about.getHardwareTypeString() + "\n"
		AboutText += _("CPU: ") + about.getCPUInfoString() + "\n"
		AboutText += _("Image: ") + about.getImageTypeString() + "\n"
		AboutText += _("Kernel version: ") + about.getKernelVersionString() + "\n"

		EnigmaVersion = "Enigma: " + about.getEnigmaVersionString()
		self["EnigmaVersion"] = StaticText(EnigmaVersion)
		AboutText += EnigmaVersion + "\n"

		#GStreamerVersion = "GStreamer: " + about.getGStreamerVersionString()
		#self["GStreamerVersion"] = StaticText(GStreamerVersion)
		#AboutText += GStreamerVersion + "\n"
		self["GStreamerVersion"] = StaticText("")

		ImageVersion = _("Last upgrade: ") + about.getImageVersionString()
		self["ImageVersion"] = StaticText(ImageVersion)
		AboutText += ImageVersion + "\n"

		fp_version = getFPVersion()
		if fp_version is None:
			fp_version = ""
		else:
			fp_version = _("Frontprocessor version: %d") % fp_version
			AboutText += fp_version + "\n"

		self["FPVersion"] = StaticText(fp_version)

		self["TunerHeader"] = StaticText(_("Detected NIMs:"))
		AboutText += "\n" + _("Detected NIMs:") + "\n"

		nims = nimmanager.nimList()
		for count in range(len(nims)):
			if count < 4:
				self["Tuner" + str(count)] = StaticText(nims[count])
			else:
				self["Tuner" + str(count)] = StaticText("")
			AboutText += nims[count] + "\n"

		self["HDDHeader"] = StaticText(_("Detected HDD:"))
		AboutText += "\n" + _("Detected HDD:") + "\n"

		hddlist = harddiskmanager.HDDList()
		hddinfo = ""
		if hddlist:
			for count in range(len(hddlist)):
				if hddinfo:
					hddinfo += "\n"
				hdd = hddlist[count][1]
				if int(hdd.free()) > 1024:
					hddinfo += "%s\n(%s, %d GB %s)" % (hdd.model(), hdd.capacity(), hdd.free()/1024, _("free"))
				else:
					hddinfo += "%s\n(%s, %d MB %s)" % (hdd.model(), hdd.capacity(), hdd.free(), _("free"))
		else:
			hddinfo = _("none")
		self["hddA"] = StaticText(hddinfo)
		AboutText += hddinfo
		self["AboutScrollLabel"] = ScrollLabel(AboutText)
		self["key_green"] = Button(_("Translations"))
		self["key_red"] = Button(_("Latest Commits"))

		self["actions"] = ActionMap(["ColorActions", "SetupActions", "DirectionActions"],
			{
				"cancel": self.close,
				"ok": self.close,
				"red": self.showCommits,
				"green": self.showTranslationInfo,
				"up": self["AboutScrollLabel"].pageUp,
				"down": self["AboutScrollLabel"].pageDown
			})

	def showTranslationInfo(self):
		self.session.open(TranslationInfo)

	def showCommits(self):
		self.session.open(CommitInfo)

class TranslationInfo(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		# don't remove the string out of the _(), or it can't be "translated" anymore.

		# TRANSLATORS: Add here whatever should be shown in the "translator" about screen, up to 6 lines (use \n for newline)
		info = _("TRANSLATOR_INFO")

		if info == "TRANSLATOR_INFO":
			info = "(N/A)"

		infolines = _("").split("\n")
		infomap = {}
		for x in infolines:
			l = x.split(': ')
			if len(l) != 2:
				continue
			(type, value) = l
			infomap[type] = value
		print infomap

		self["TranslationInfo"] = StaticText(info)

		translator_name = infomap.get("Language-Team", "none")
		if translator_name == "none":
			translator_name = infomap.get("Last-Translator", "")

		self["TranslatorName"] = StaticText(translator_name)

		self["actions"] = ActionMap(["SetupActions"],
			{
				"cancel": self.close,
				"ok": self.close,
			})

class CommitInfo(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["CommitInfo", "About"]
		self["AboutScrollLabel"] = ScrollLabel(_("Please wait"))

		self["actions"] = ActionMap(["SetupActions", "DirectionActions"],
			{
				"cancel": self.close,
				"ok": self.close,
				"up": self["AboutScrollLabel"].pageUp,
				"down": self["AboutScrollLabel"].pageDown,
				"left": self.left,
				"right": self.right
			})

		self.project = 0
		self.projects = [
			("taapat-enigma2", "Taapat Enigma2"),
			("taapat-amikoar-p", "Taapat amikoAR-P"),
			("ar-p-enigma2-plugins-sh4", "AR-P Enigma2 Plugins sh4"),
			("taapat-skin-dTV-HD-Reloaded", "Taapat skin-dTV-HD-Reloaded"),
			("enigma2", "Enigma2"),
			("openpli-oe-core", "Openpli Oe Core"),
			("enigma2-plugins", "Enigma2 Plugins"),
			("aio-grab", "Aio Grab"),
			("gst-plugin-dvbmediasink", "Gst Plugin Dvbmediasink"),
			("openembedded", "Openembedded"),
			("plugin-xmltvimport", "Plugin Xmltvimport"),
			("plugins-enigma2", "Plugins Enigma2"),
			("skin-magic", "Skin Magic"),
			("tuxtxt", "Tuxtxt")
		]
		self.cachedProjects = {}
		self.Timer = eTimer()
		self.Timer.callback.append(self.readCommitLogs)
		self.Timer.start(50, True)

	def readCommitLogs(self):
		from urllib2 import urlopen
		feed = self.projects[self.project][0]
		commitlog = 80 * '-' + '\n'
		commitlog += feed + '\n'
		commitlog += 80 * '-' + '\n'
		if "ar-p-" in feed or "-skin-" in feed:
			if "ar-p-" in feed:
				url = 'https://github.com/OpenAR-P/%s/commits/master' % feed[5:]
			else:
				url = 'https://github.com/Taapat/%s/commits/master' % feed[7:]
			try:
				for x in  urlopen(url, timeout=5).read().split('commit-title')[1:]:
					for y in x.split('" ', 7):
						if y[:7] == 'title="':
							title = y.split('>', 1)[1].split('<', 1)[0]
						if y[:4] == 'rel=':
							author = y.split('>', 1)[1].split('<', 1)[0]
							date = y.split('datetime="')[1][:10]
					commitlog += date + ' ' + author + '\n' + title + 2 * '\n'
			except:
				commitlog = _("Currently the commit log cannot be retrieved - please try later again")
		elif "taapat" in feed:
			try:
				url = open('/etc/opkg/official-feed.conf', 'r').read().split()[2]
				url += '/' + feed + '.log'
				commitlog += urlopen(url, timeout=5).read()
			except:
				commitlog = _("Currently the commit log cannot be retrieved - please try later again")
		else:
			url = 'http://sourceforge.net/p/openpli/%s/feed' % feed
			try:
				for x in  urlopen(url, timeout=5).read().split('<title>')[2:]:
					for y in x.split("><"):
						if '</title' in y:
							title = y[:-7]
						if '</dc:creator' in y:
							creator = y.split('>')[1].split('<')[0]
						if '</pubDate' in y:
							date = y.split('>')[1].split('<')[0][:-6]
					commitlog += date + ' ' + creator + '\n' + title + 2 * '\n'
				self.cachedProjects[self.projects[self.project][1]] = commitlog
			except:
				commitlog = _("Currently the commit log cannot be retrieved - please try later again")
		self["AboutScrollLabel"].setText(commitlog)

	def updateCommitLogs(self):
		if self.cachedProjects.has_key(self.projects[self.project][1]):
			self["AboutScrollLabel"].setText(self.cachedProjects[self.projects[self.project][1]])
		else:
			self["AboutScrollLabel"].setText(_("Please wait"))
			self.Timer.start(50, True)

	def left(self):
		self.project = self.project == 0 and len(self.projects) - 1 or self.project - 1
		self.updateCommitLogs()

	def right(self):
		self.project = self.project != len(self.projects) - 1 and self.project + 1 or 0
		self.updateCommitLogs()
