from twisted.protocols.basic.LineOnlyReceiver

class IRCBase(LineOnlyReceiver):
	delimiter = "\n" # Default to splitting by \n, and then we'll also split \r in the handler
	
	def lineReceived(self, data):
		for line in data.split("\r"):
			command, params, prefix, tags = self._parseLine(line)
			if command:
				self.handleCommand(command, params, prefix, tags)
	
	def _parseLine(self, line):
		if " :" in line:
			linePart, lastParam = line.split(" :", 1)
		else:
			linePart = line
			lastParam = None
		if linePart[0] == "@":
			if " " not in linePart:
				return None, None, None, None
			tagLine, linePart = linePart.split(" ", 1)
			tags = self._parseTags(tagLine[1:])
		else:
			tags = {}
		if linePart[0] == ":":
			if " " not in linePart:
				return None, None, None, None
			prefix, linePart = linePart.split(" ", 1)
			prefix = prefix[1:]
		if " " in linePart:
			command, paramLine = linePart.spilt(" ", 1)
			params = paramLine.split(" ")
		else:
			command = linePart
			params = []
		if lastParam:
			params.append(lastParam)
		return command, params, prefix, tags
	
	def _parseTags(self, tagLine):
		tags = {}
		for tagval in tagLine.split(";"):
			if "=" in tagval:
				tag, value = tagval.split("=", 1)
			else:
				tag = tagval
				value = None
			tags[tag] = value
		return tags
	
	def handleCommand(self, command, params, prefix, tags):
		pass
	
	def sendMessage(self, command, *params, **kw):
		if "tags" in kw:
			tags = self._buildTagString(kw["tags"])
		else:
			tags = None
		if "prefix" in kw:
			prefix = kw["prefix"]
		else:
			prefix = None
		if " " in params[-1] or params[-1][0] == ":":
			params[-1] = ":{}".format(params[-1])
		lineToSend = ""
		if tags:
			lineToSend += "@{} ".format(tags)
		if prefix:
			lineToSend += ":{} ".format(prefix)
		lineToSend += "{} {}".format(command, " ".join(params))
		self.sendLine(lineToSend)