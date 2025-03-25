# File:         state.py
# Author:       Brian Allen Vanderburg II
# Purpose:      The state object extracts state from a document.
# License:      Refer to the file license.txt

from copy import deepcopy

from lxml import etree

class _State(object):
    def __init__(self):
        self.bookmark = None
        self.year = None
        self.month = None
        self.day = None
        self.title = None
        self.summaries = []
        self.tags = []

    @property
    def valid(self):
        return bool(self.year and self.month and self.day and self.title and self.summaries)

    def __cmp__(self, other):
        v = int(self.year) - int(other.year)
        if v != 0:
            return v
        
        v = int(self.month) - int(other.month)
        if v != 0:
            return v

        return int(self.day) - int(other.day)


class StateParser(object):
    def __init__(self, xml):
        self.entry = xml.get('entry')
        self.bookmark = xml.get('bookmark')
        self.year = xml.get('year')
        self.month = xml.get('month')
        self.day = xml.get('day')
        self.title = xml.get('title')
        self.summary = xml.get('summary')
        self.tag = xml.get('tag')

        self.ns = {}
        for i in xml.findall('namespace'):
            self.ns[i.get('prefix')] = i.get('value')

    @staticmethod
    def load(xml):
        return StateParser(xml)

    def execute(self, xml):
        if self.entry:
            entries = xml.xpath(self.entry, namespaces=self.ns)
        else:
            entries = [xml]

        states = []
        for entry in entries:
            state = _State()

            if self.bookmark:
                bookmark = entry.xpath(self.bookmark, namespaces=self.ns)
                if bookmark:
                    state.bookmark = '' + bookmark[0]

            if self.year:
                year = entry.xpath(self.year, namespaces=self.ns)
                if year:
                    state.year = '' + year[0]

            if self.month:
                month = entry.xpath(self.month, namespaces=self.ns)
                if month:
                    state.month = '' + month[0]

            if self.day:
                day = entry.xpath(self.day, namespaces=self.ns)
                if day:
                    state.day = '' + day[0]

            if self.title:
                title = entry.xpath(self.title, namespaces=self.ns)
                if title:
                    state.title = '' + title[0]

            if self.summary:
                summaries = entry.xpath(self.summary, namespaces=self.ns)
                for summary in summaries:
                    state.summaries.append(deepcopy(summary))

            if self.tag:
                tags = entry.xpath(self.tag, namespaces=self.ns)
                for tag in tags:
                    if not '' + tag in state.tags:
                        state.tags.append('' + tag)

            if state.valid:
                states.append(state)

        return states
    
