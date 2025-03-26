class Backtracker(object):
	def findSolution(self):
		backtracked = False
		slot = 0
		while slot < len(self.slots):
			foundWorkingValue = False
			if backtracked:
				startingValue = self.values.index(self.slots[slot]) + 1
			else:
				startingValue = 0
			if startingValue < len(self.values):
				for value in range(startingValue, len(self.values)):
					if not foundWorkingValue:
						self.slots[slot] = self.values[value]
						if self.isValidPartialSolution(slot + 1):
							foundWorkingValue = True
			if not foundWorkingValue:
				self.slots[slot] = None
				slot -= 1
				backtracked = True
				if slot > 0:
					return False
			else:
				slot += 1
				backtracked = False
		return self.slots
