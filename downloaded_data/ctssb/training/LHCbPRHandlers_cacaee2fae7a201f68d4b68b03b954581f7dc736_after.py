import os, sys, re
from BaseHandler import BaseHandler
from xml.etree.ElementTree import ElementTree
from xml.parsers.expat import ExpatError

class StrippingTimingHandler(BaseHandler):
        
    def __init__(self):
        super(self.__class__, self).__init__()
        self.finished = False
        self.results = []

    def collectResults(self,directory):

        # Parsing the log
        from timing.TimingParser import TimingParser
        tp = TimingParser(os.path.join(directory,'run.log'))

        # COlelcting the interesting nodes
        nodelist = []
        eventLoop = tp.getRoot()
        nodelist.append(eventLoop)
        
        dvUserSeq = eventLoop.findByName("DaVinciUserSequence")
        nodelist.append(dvUserSeq)
        for c in dvUserSeq.children:
            nodelist.append(c)
            
        stripGlobal = dvUserSeq.findByName("StrippingGlobal")
        nodelist.append(stripGlobal)
        for c in stripGlobal.children:
            nodelist.append(c)

        StrippingProtectedSequenceALL = stripGlobal.findByName("StrippingProtectedSequenceALL")
        nodelist.append(StrippingProtectedSequenceALL)
        for c in StrippingProtectedSequenceALL.children:
            nodelist.append(c)

        for node in nodelist:
            print node.name

        # Now saving the results
        for node in tp.nodelist:
            self.saveFloat(node.name, node.value, group="Timing")
            self.saveInt(node.name + "_count", node.entries, group="TimingCount")
            self.saveInt(node.name + "_rank", node.rank, group="TimingRank")
            if node.parent != None:
                self.saveString(node.name + "_parent", node.parent.name, group="TimingTree")
            else:
                self.saveString(node.name + "_parent", "None", group="TimingTree")
            self.saveInt(node.name + "_id", node.id, group="TimingID")


