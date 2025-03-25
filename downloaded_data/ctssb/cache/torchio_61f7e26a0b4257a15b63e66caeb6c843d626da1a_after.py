#!/usr/bin/env python


import re

import nn
import torch

from .BinaryFileWriter import BinaryFileWriter
import iocommon

#----------------------------------------------------------------------

class OutputFile:

    #----------------------------------------
    
    def __init__(self, outfile, mode):

        if mode == 'binary':
            self.writer = BinaryFileWriter(outfile)
        else:
            raise Exception("mode " + str(mode) + " not supported")

        # outfile is the underlying file like object
        # to which we want to write
        self.outfile = outfile

        # maps from object id to index
        self.objectCache = {}
        
    #----------------------------------------
    # methods delegated to self.writer
    #----------------------------------------

    def writeInt(self, value):
        self.writer.writeInt(value)

    def writeInts(self, values):
        # write a list of integers
        for value in values:
            self.writer.writeInt(value)
        
    def writeChars(self, text):
        return self.writer.writeChars(text)

    def writeLong(self, value):
        return self.writer.writeLong(value)

    def writeLongs(self, values):
        return self.writer.writeLongs(values)

    def writeFloats(self, data):
        return self.writer.writeFloats(data)

    def writeDouble(self, value):
        return self.writer.writeDouble(value)

    def writeBool(self, value):
        return self.writer.writeBool(value)
    
    #----------------------------------------

    def writeString(self, text):
        self.writeInt(len(text))

        self.writeChars(text)
    
    #----------------------------------------

    def writeTorchType(self, obj):
        # writes a non-'primitive' type

        # check for custom writers
        if not hasattr(obj, 'customWriter'):
            raise Exception("don't know how to serialize an object of type " + obj.__class__.__name__)

        # type id
        self.writeInt(iocommon.MAGIC_TORCH)

        # put the object into the cache
        # note: do this before writing the members
        #       as a member may refer back to this
        #       object already

        objectIndex, isNew = self.__getCacheIndex(obj)

        self.writeInt(objectIndex)

        if not isNew:
            return

        #----------
               
        version = 1

        # write a version string with a default version
        self.writeString("V " + str(version))
        
        #----------
        # produce the class name
        className = obj.__module__ + "." + obj.__class__.__name__

        # remove the beginning 'torchio'
        className = className.split('.')
        if className[0] == 'torchio':
            className.pop(0)
        className = ".".join(className)

        self.writeString(className)

        # call type specific serialization
        obj.customWriter(self)

    #----------------------------------------    

    def __getCacheIndex(self, obj):

        # returns the index and True if
        # this was not yet in the cache

        theId = id(obj)

        if self.objectCache.has_key(theId):
            return self.objectCache[theId], False

        # we start the indexing at one
        nextIndex = len(self.objectCache) + 1
        self.objectCache[theId] = nextIndex

        return nextIndex, True

    #----------------------------------------

    def writeTable(self, obj):

        # type id
        self.writeInt(iocommon.MAGIC_TABLE)

        # get an object index and write it out
        # (avoid cyclic dependencies
        #  by writing only writing a reference number
        #  for an object instead of the
        #  object itself after the first time)

        objectIndex, isNew = self.__getCacheIndex(obj)
        self.writeInt(objectIndex)
                
        if isNew:
            # size of the table
            self.writeInt(len(obj))

            # only write out the object if it was not
            # new
            for key, value in obj.items():
                self.writeObject(key)
                self.writeObject(value)

    #----------------------------------------
    
    def writeObject(self, obj):

        if obj == None:
            self.writeInt(iocommon.MAGIC_NIL)
            return

        if isinstance(obj, bool):
            self.writeInt(iocommon.MAGIC_BOOLEAN)
            self.writeBool(obj)
            return

        # TODO: python 3 does not have a 'long' type
        if isinstance(obj, (int, long, float)):
            # write these all out as 'doubles',
            # lua does not have integer types
            self.writeInt(iocommon.MAGIC_NUMBER)
            self.writeDouble(float(obj))
            return

        if isinstance(obj, str):
            self.writeInt(iocommon.MAGIC_STRING)
            self.writeString(str)
            return

        if isinstance(obj, dict):
            # write this out as a table
            self.writeTable(obj)
            return

        # check if we have a custom serialization method
        
        if isinstance(obj, torch.GenericTorchObject):
            self.writeTorchType(obj)
            return

        raise Exception("don't know how to serialize an object of type " + str(type(obj)))

    #----------------------------------------            
