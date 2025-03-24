# -*- coding: utf-8 -*-
"""
Created on Tue Oct 17 16:49:51 2017

@author: ab9621
"""
import numpy as np
import struct

class __fieldObject__:
    '''
    Class to contain the contents of the Pogo field output.
    '''
    def __init__(self,
                 nDims,
                 nNodes,
                 nFieldIncs,
                 times,
                 ux,
                 uy,
                 uz,
                 nodePos):
        self.nDims = nDims
        self.nNodes = nNodes
        self.nFieldInc = nFieldIncs
        self.times = times
        self.ux = ux
        self.uy = uy
        self.uz = uz
        self.nodePos = nodePos
        return

def loadFieldFile(fileName):
    '''
    Function to load in a Pogo field output file.
    
    Parameters
    ----------
    fileName : string
        The name of the file. Does not need to include .pogo-field.
        
    Returns
    -------
    fieldData : instance of __fieldObject__ class
        The data in the field outpt file stored in a class container.
    '''
    if fileName[-11:] != '.pogo-field':
		fileName += '.pogo-field'

    with open(fileName, 'rb') as f:
        header = struct.unpack('20s', f.read(20))
        header = header[0].replace('\x00','')
        print header
        
        if header == '%pogo-field1.0':
            fileVer = 1.0
        
        elif header == '%pogo-field1.02':
            fileVer = 1.02
            
        else:
            raise ValueError('pogo history file version not recognised.')

        precision = struct.unpack('l', f.read(4))[0]
        
        if precision not in [4,8]:
            raise ValueError('Precision {} not supported. Should be 4 or 8.'.format(precision))
            
        if precision == 4:
            precString = 'f'
            
        elif precision == 8:
            precString = 'd'
            
        else:
            raise ValueError('Unsupported precision.')
            
        nDims = struct.unpack('l', f.read(4))[0]
        nDofPerNode = 2
        if fileVer >= 1.02:
            nDofPerNode = struct.unpack('l', f.read(4))[0]
            
        if nDofPerNode not in [2,3]:
            raise ValueError('nDofPerNode must be 2 or 3, not {}'.format(nDofPerNode))
        print nDofPerNode
        nNodes = struct.unpack('l', f.read(4))[0]
        print nNodes
        
        nodePos = np.zeros((nDims, nNodes))
        for c1 in range(nNodes):
            nodePos[:, c1] = struct.unpack('{}{}'.format(nDims, precString), f.read(precision*nDims))
            
        nFieldStores = struct.unpack('l', f.read(4))[0]
        
        times = np.zeros(nFieldStores)
        ux = np.zeros((nNodes, nFieldStores))
        uy = np.zeros((nNodes, nFieldStores))
        uz = np.zeros((nNodes, nFieldStores))
        
        for c1 in range(nFieldStores):
            times[c1] = struct.unpack('{}'.format(precString), f.read(precision))[0]
            ux[:,c1] = struct.unpack('{}{}'.format(nNodes, precString), f.read(precision*nNodes))
            uy[:,c1] = struct.unpack('{}{}'.format(nNodes, precString), f.read(precision*nNodes))
            if nDims == 3:
                uz[:,c1] = struct.unpack('{}{}'.format(nNodes, precString), f.read(precision*nNodes))
                
    data = __fieldObject__(nDims, nNodes, nFieldStores,
                           times, ux, uy, uz, nodePos)
    return data