# -*- coding: utf-8 -*-

import re
import functools
from .openinghoursparser import OpeningHoursParser

TAG_UNSET = "unset"
TAG_INVALID = "invalid"

class Main:
	"""
	Main class of the library.
	It contains all main functions which can help managing public transport hours.
	"""

	def tagsToGtfs(self, tags):
		"""
		Convert OpenStreetMap tags into a GTFS-like format (list of dict having format { eachWeekDay: True/False, start_time: string, end_time: string, headway: int }.
		Parsed tags are : interval=\*, opening_hours=\* and interval:conditional=\*

		# param tags (dict): OpenStreetMap tags
		# return dict[]: list of dictionaries, each one representing a line of GTFS hours CSV file
		"""
		hours = self.tagsToHoursObject(tags)

		if hours['allComputedIntervals'] == TAG_INVALID:
			raise Exception("OSM tags describing route hours are probably invalid, and can't be read")
		elif hours['allComputedIntervals'] == TAG_UNSET:
			return []
		else:
			result = []

			daysId = [ "mo", "tu", "we", "th", "fr", "sa", "su", "ph" ]

			# Read each period(days, intervals)
			for period in sorted(hours['allComputedIntervals'], key=lambda x: daysId.index(x['days'][0])):
				periodGtfs = {}

				# Interpret days (we ignore ph as not used by GTFS)
				days = [ d for d in period['days'] if d != "ph" ]
				if len(days) > 0:
					periodGtfs['monday'] = "mo" in days
					periodGtfs['tuesday'] = "tu" in days
					periodGtfs['wednesday'] = "we" in days
					periodGtfs['thursday'] = "th" in days
					periodGtfs['friday'] = "fr" in days
					periodGtfs['saturday'] = "sa" in days
					periodGtfs['sunday'] = "su" in days

					# Interpret intervals
					for hourRange in sorted(period['intervals'].keys()):
						periodHourGtfs = dict(periodGtfs)
						periodHourGtfs['start_time'] = hourRange.split("-")[0] + ":00"
						periodHourGtfs['end_time'] = hourRange.split("-")[1] + ":00"
						periodHourGtfs['headway'] = period['intervals'][hourRange] * 60

						# Add to result
						result.append(periodHourGtfs)

			return result

	def tagsToHoursObject(self, tags):
		"""
		Converts OpenStreetMap tags into a ready-to-use object representing the hours of the public transport line.
		Parsed tags are : interval=\*, opening_hours=\* and interval:conditional=\*

		# param tags (dict): The list of tags from OpenStreetMap
		# return dict: The hours of the line, with structure { opens: object in format given by #OpeningHoursParser.gettable(), defaultInterval: minutes (int), otherIntervals: interval rules object, otherIntervalsByDays: list of interval by days (structure: { days: string[], intervals: { hoursRange: interval } }), allComputedIntervals: same as otherIntervalsByDays but taking also default interval and opening_hours }. Each field can also have value "unset" if no tag is defined, or "invalid" if tag can't be read.
		"""

		# Read opening_hours
		opens = TAG_UNSET
		try:
			opens = OpeningHoursParser(tags['opening_hours']).getTable() if 'opening_hours' in tags else TAG_UNSET
		except:
			opens = TAG_INVALID

		# Read interval
		interval = TAG_UNSET
		try:
			interval = self.intervalStringToMinutes(tags['interval']) if 'interval' in tags else TAG_UNSET
		except:
			interval = TAG_INVALID

		# Read interval:conditional
		intervalCond = TAG_UNSET
		intervalCondByDay = TAG_UNSET
		try:
			intervalCond = self.intervalConditionalStringToObject(tags["interval:conditional"]) if "interval:conditional" in tags else TAG_UNSET
			intervalCondByDay = self._intervalConditionObjectToIntervalByDays(intervalCond) if intervalCond != TAG_UNSET else TAG_UNSET
		except:
			intervalCond = TAG_INVALID
			intervalCondByDay = TAG_INVALID

		# Create computed calendar of intervals using previous data
		computedIntervals = TAG_UNSET
		try:
			computedIntervals = self._computeAllIntervals(opens, interval, intervalCondByDay)
		except:
			computedIntervals = TAG_INVALID

		# Send result
		return {
			"opens": opens,
			"defaultInterval": interval,
			"otherIntervals": intervalCond,
			"otherIntervalsByDays": intervalCondByDay,
			"allComputedIntervals": computedIntervals
		}

	def intervalConditionalStringToObject(self, intervalConditional):
		"""
		Reads an interval:conditional=* tag from OpenStreetMap, and converts it into a JS object.

		# param intervalConditional (string): The {@link https://wiki.openstreetmap.org/wiki/Key:interval|interval:conditional} tag
		# return (dict[]): A list of rules, each having structure { interval: minutes (int), applies: {@link #gettable|opening hours table} }
		"""
		return [ self._readSingleIntervalConditionalString(p) for p in self._splitMultipleIntervalConditionalString(intervalConditional) ]

	def _splitMultipleIntervalConditionalString(self, intervalConditional):
		"""
		Splits several conditional interval rules being separated by semicolon.

		# param intervalConditional (string)
		# return (string[]): List of single rules
		"""
		if "(" in intervalConditional:
			semicolons = [i for i, ltr in enumerate(intervalConditional) if ltr == ";"]
			cursor = 0
			stack = []

			while len(semicolons) > 0:
				scid = semicolons[0]
				part = intervalConditional[cursor:scid]

				if re.search("^[^\(\)]+$", part) or re.search("\(.*\)", part):
					stack.append(part)
					cursor = scid+1

				semicolons.pop(0)

			stack.append(intervalConditional[cursor:])
			return [ p.strip() for p in stack if len(p.strip()) > 0 ]
		else:
			return [ p.strip() for p in intervalConditional.split(";") if len(p.strip()) > 0 ]

	def _readSingleIntervalConditionalString(self, intervalConditional):
		"""
		Parses a single conditional interval value (for example : `15 @ (08:00-15:00)`).
		This should be used as many times as you have different rules (separated by semicolon).

		# param intervalConditional (string)
		# return (dict): dictionary with structure { interval: minutes (int), applies: OpeningHoursParser.gettable() structure} }
		"""
		result = {}
		parts = [ p.strip() for p in intervalConditional.split("@") ]

		if len(parts) != 2:
			raise Exception("Conditional interval can't be parsed : "+intervalConditional)

		# Read interval
		result['interval'] = self.intervalStringToMinutes(parts[0])

		# Read opening hours
		if re.search("^\(.*\)$", parts[1]):
			parts[1] = parts[1][1:len(parts[1])-1]

		result['applies'] = OpeningHoursParser(parts[1]).getTable()

		return result

	def _intervalConditionObjectToIntervalByDays(self, intervalConditionalObject):
		"""
		Transforms an object containing the conditional intervals into an object structured day by day.
		"""
		result = []
		itvByDay = {}

		# List hours -> interval day by day
		for itv in intervalConditionalObject:
			for day, hours in itv['applies'].items():
				if day not in itvByDay:
					itvByDay[day] = {}
				for h in hours:
					itvByDay[day][h] = itv['interval']

		# Merge days
		for day, intervals in itvByDay.items():
			if len(intervals) > 0:
				# Look for identical days
				ident = [ r for r in result if r['intervals'] == intervals ]

				if len(ident) == 1:
					ident[0]['days'].append(day)
				else:
					result.append({ "days": [ day ], "intervals": intervals })

		return result

	def _flatList(self, myList):
		flatList=[]
		for eachList in myList:
			for eachItem in eachList:
				flatList.append(eachItem)
		return flatList

	def _computeAllIntervals(self, openingHours, interval, intervalCondByDay):
		"""
		Reads all information, and generates a merged calendar of all intervals.
		"""

		# If opening hours or interval is invalid, returns interval conditional as is
		if openingHours == TAG_INVALID or interval == TAG_INVALID or interval == TAG_UNSET or intervalCondByDay == TAG_INVALID:
			return TAG_INVALID if (openingHours == TAG_INVALID or interval == TAG_INVALID) and intervalCondByDay == TAG_UNSET else intervalCondByDay
		else:
			myIntervalCondByDay = [] if intervalCondByDay == TAG_UNSET else intervalCondByDay

			# Check opening hours, if missing we default to 24/7
			myOH = openingHours
			if openingHours == TAG_UNSET:
				myOH = OpeningHoursParser("24/7").getTable()

			# Copy existing intervals (split day by day)
			result = []
			for di in myIntervalCondByDay:
				for d in di['days']:
					result.append({ "days": [d], "intervals": di['intervals'] })

			# Complete existing days
			result = list(result)
			for di in result:
				di['intervals'] = self._mergeIntervalsSingleDay(myOH[di['days'][0]], interval, di['intervals'])

			# List days not in myIntervalCondByDay, and add directly opening hours
			# Was: daysInCondInt = [...new Set(myIntervalCondByDay.map(d => d.days).flat())]
			daysInCondInt = list(set(self._flatList([ d['days'] for d in myIntervalCondByDay ])))
			missingDays = [ d for d in myOH if d not in daysInCondInt ]
			missingDaysOH = {}
			for day in missingDays:
				missingDaysOH[day] = myOH[day]

			result = result + self._intervalConditionObjectToIntervalByDays([{ "interval": interval, "applies": missingDaysOH }])

			# Merge similar days
			i = 1
			while i < len(result):
				j = 0
				while j < i:
					if result[i]['intervals'] == result[j]['intervals']:
						result[j]['days'] = result[j]['days'] + result[i]['days']
						del result[i]
						i -= 1
						break
					j += 1
				i += 1

			# Sort results by day
			daysId = [ "mo", "tu", "we", "th", "fr", "sa", "su", "ph" ]
			for r in result:
				r['days'].sort(key=lambda x: daysId.index(x))

			result.sort(key=lambda x: daysId.index(x['days'][0]))

			return result

	def _mergeIntervalsSingleDay(self, hours, interval, condIntervals):
		"""
		Add default interval within opening hours to conditional intervals
		"""
		hourRangeToArr = lambda hr: [ h.split("-") for h in hr ]
		ohHours = hourRangeToArr(hours)
		condHours = hourRangeToArr(condIntervals)

		# Check all conditional hours belong into opening hours
		invalidCondHours = list(condHours)
		i = 0
		while i < len(invalidCondHours):
			ch = invalidCondHours[i]
			foundOhHours = False

			for ohh in ohHours:
				if ch[0] >= ohh[0] and ch[1] <= ohh[1]:
					foundOhHours = True
					break

			if foundOhHours:
				del invalidCondHours[i]
			else:
				i += 1

		if len(invalidCondHours) > 0:
			raise Exception("Conditional intervals are not contained in opening hours")

		ohHoursWithoutConds = []

		for ohh in ohHours:
			thisHours = []

			if len(condHours) == 0 or ohh[0] != condHours[0][0]:
				thisHours.append(ohh[0])

			for ch in condHours:
				if ch[0] > ohh[0] and ch[0] < ohh[1]:
					thisHours.append(ch[0])
				if ch[1] > ohh[0] and ch[1] < ohh[1]:
					thisHours.append(ch[1])

			if len(condHours) == 0 or ohh[1] != condHours[len(condHours)-1][1]:
				thisHours.append(ohh[1])

			ohToAdd = []
			for i in range(len(thisHours)):
				if i % 2 == 1:
					ohToAdd.append(thisHours[i-1] + "-" + thisHours[i])

			ohHoursWithoutConds = ohHoursWithoutConds + ohToAdd

		result = {}
		for h in ohHoursWithoutConds:
			result[h] = interval

		result.update(condIntervals)

		return result

	def intervalStringToMinutes(self, interval):
		"""
		Converts an interval=* string into an amount of minutes

		>>> intervalStringToMinutes("00:10")
		10
		"""
		interval = interval.strip()

		# hh:mm:ss
		if re.search("^\d{1,2}:\d{2}:\d{2}$", interval):
			parts = [ int(t) for t in interval.split(":") ]
			return parts[0] * 60 + parts[1] + parts[2] / 60.0

		# hh:mm
		elif re.search("^\d{1,2}:\d{2}$", interval):
			parts = [ int(t) for t in interval.split(":") ]
			return parts[0] * 60 + parts[1]

		# mm
		elif re.search("^\d+$", interval):
			return int(interval)

		# invalid
		else:
			raise Exception("Interval value can't be parsed : "+interval)
