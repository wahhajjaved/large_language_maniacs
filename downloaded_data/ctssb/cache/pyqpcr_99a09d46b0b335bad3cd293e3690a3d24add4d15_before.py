# -*- coding: utf-8 -*-
#
# pyQPCR, an application to analyse qPCR raw data
# Copyright (C) 2008 Thomas Gastine
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import csv
import re
import string
from pyQPCR.wellGeneSample import Ech, Gene, Puits, WellError
from scipy.stats import t, norm
from PyQt4.QtCore import Qt, QString, QFileInfo
from numpy import mean, std, sqrt, log, log10, polyval, polyfit, sum, \
array, append
from pyQPCR.utils.odict import OrderedDict
from pyQPCR.utils.ragged import RaggedArray2D

__author__ = "$Author$"
__date__ = "$Date$"
__version__ = "$Rev$"


def returnDelimiter(fileObj):
    """
    A routine to determine the separator of a CSV file. Works with
    comma, semicolon or tabulation for now.

    :param fileObj: the file object we want to test
    :type fileObj: file
    """
    text = fileObj.read(1024) # you can change this to whatever is appropriate for your data
    fileObj.seek(0) # get back to beginning of file for csv reader
    if text.count('\t') > text.count(',') and text.count('\t') > text.count(';'):
        return '\t'
    if text.count(',') > text.count(';'):
        return ','
    else:
        return ';'

class Plaque:
    """
    The Plaque object contains the data of a PCR experiment (basically
    96 wells). It is constructed by parsing a raw data file.

    >>> pl = Plaque('raw_data_AB7500.csv', machine='Applied 7500')
    >>> print str(pl.A1)
    >>> print pl.geneRef

    :attribute filename: the file name
    :attribute listePuits: the list of the wells of the plate
    :attribute echRef: the name of the reference sample
    :attribute geneRef: the name(s) of the reference target(s)
    :attribute contUkn: a boolean that indicates if the plate contains
                        'unknown'-type wells
    :type contUkn: logical
    """
    
    def __init__(self, filename=None, machine='Eppendorf'):
        """
        Constructor of a Plaque object.


        :param filename: the name of the raw data file
        :type filename: PyQt4.QtCore.QString
        :param machine: the PCR device used in the experiment
        :type machine: PyQt4.QtCore.QString
        """
        self.type = '96'
        self.unsaved = False
        self.filename = filename

        self.listePuits = []

        self.geneRef = []
        self.echRef = ''
        self.contUkn = True
 
        if self.filename is not None and machine is not None:
            self.determineFileType(self.filename)
            if machine == 'Eppendorf':
                self.parseEppendorf()
            elif machine in ['Applied StepOne', 'Applied 7500']:
                self.parseAppliedUniv()
            elif machine == 'Applied 7000':
                self.parseApplied7000()
            elif machine == 'Applied 7700':
                self.parseApplied7700()
            elif machine == 'Applied 7900':
                self.parseApplied7900()
            elif machine == 'Biorad MyIQ':
                self.parseBioradMyIQ()
            elif machine == 'Cepheid SmartCycler':
                self.parseCepheid()
            elif machine == 'Qiagen Corbett':
                self.parseCorbett()
            elif machine == 'Roche LightCycler 480':
                self.parseLightCycler480()
            # Raise exception if no well are detected
            if len(self.listePuits) == 0:
                raise PlateError(self.filename, machine)

    def __cmp__(self, other):
        """
        This method is used to compare two plates.
        """
        if self.echRef != other.echRef:
            return cmp(self.echRef, other.echRef)
        if self.geneRef != other.geneRef:
            return cmp(self.geneRef, other.geneRef)
        if self.type != other.type:
            return cmp(self.type, other.type)
        if self.filename != other.filename:
            return cmp(self.filename, other.filename)
        return cmp(self.listePuits, other.listePuits)

    def determineFileType(self, filename):
        """
        A method to determine the extension of the raw data file (txt or csv).

        :param filename: the name of the file
        :type filename: PyQt4.QtCore.QString
        """
        extent = filename[-3:]
        if extent in ["txt", "TXT"]:
            self.fileType = "txt"
        elif extent in ["csv", "CSV"]:
            self.fileType = "csv"
        else:
            raise IOError

    def setPlateType(self, type):
        self.type = type

    def parseLightCycler480(self):
        """
        This method allows to parse Roche Light Cycler 480 raw data.
        """
        file = open(unicode(self.filename), "r")
        iterator = file.readlines()
        file.close()
        motif = re.compile(r'^(.*) (\d*[\.,]?\d*)?$')
        ncol = 0
        indheader = 0
        for ind, line in enumerate(iterator):
            linetot = line
            line = line.split('\t')
            if linetot.__contains__('Name'):
                indheader = ind
                self.header = OrderedDict()
                for i, field in enumerate(line):
                    st = field.strip('"')
                    self.header[st] = i
                ncol = len(self.header.keys())

            if len(line) == ncol and ind != indheader:
                champs = []
                for field in line:
                    dat = field.strip('"')
                    try:
                        dat = float(field.replace(',', '.'))
                    except ValueError:
                        pass
                    champs.append(dat)
                if self.header.has_key('Position'):
                    name = champs[self.header['Position']]
                    x = Puits(name)
                    if x.xpos > 8 or x.ypos > 12:
                        self.setPlateType('384')
                elif self.header.has_key('Pos'):
                    name = champs[self.header['Pos']]
                    x = Puits(name)
                    if x.xpos > 8 or x.ypos > 12:
                        self.setPlateType('384')
                else:
                    raise KeyError
                if self.header.has_key('SampleName'):
                    geneEch = champs[self.header['SampleName']]
                    if motif.match(geneEch):
                        geneEch = motif.findall(geneEch)[0][0]
                    dat = geneEch.split('_')
                    if len(dat) > 2:
                        geneName = string.join(dat[1:], '_')
                    else:
                        geneName = dat[1]
                    x.setEch(Ech(dat[0]))
                    x.setGene(Gene(geneName))
                elif self.header.has_key('Name'):
                    geneEch = champs[self.header['Name']]
                    dat = geneEch.split('_')
                    if len(dat) > 2:
                        geneName = string.join(dat[1:], '_')
                    else:
                        geneName = None
                    x.setEch(Ech(dat[0]))
                    if geneName is not None:
                        x.setGene(Gene(geneName))
                elif self.header.has_key('Sample Name'):
                    ech = champs[self.header['Sample Name']]
                    x.setEch(Ech(ech))
                if self.header.has_key('CrossingPoint'):
                    ct = champs[self.header['CrossingPoint']]
                    if ct == '':
                        x.setEnabled(False)
                    x.setCt(ct)
                elif self.header.has_key('Cp'):
                    ct = champs[self.header['Cp']]
                    if ct == '':
                        x.setEnabled(False)
                    x.setCt(ct)
                if self.header.has_key('Standard'):
                    try:
                        am = float(champs[self.header['Standard']])
                        if am != 0:
                            x.setType('standard')
                            x.setAmount(am)
                    except ValueError:
                        pass
                if self.header.has_key('Call'):
                    type = champs[self.header['Call']]
                    if type == "pdcNegative":
                        x.setType('negative')
 
                setattr(self, x.name, x)
                self.listePuits.append(x)

    def parseEppendorf(self):
        """
        This method allows to parse Eppendorf raw data. It works with both
        TXT and CSV files (separated by a semicolon).
        """
        file = open(unicode(self.filename), "r")
        motif = re.compile(r"[\w\s]*")
        amountMotif = re.compile(r"Amount SYBR ?\[(.*)\]")
        if self.fileType == "txt":
            splitter = re.compile(r'("[\w\s.,\-\(\)\[\]\+\\/]*"|\d+[.,]?\d*)')
            iterator = file.readlines()
        if self.fileType == "csv":
            iterator = csv.reader(file, delimiter=returnDelimiter(file))
        for ind, line in enumerate(iterator):
            if self.fileType == "txt": line = splitter.findall(line)

            if ind == 0:
                self.header = OrderedDict()
                for i, field in enumerate(line):
                    st = field.strip('"')
                    if amountMotif.match(st):
                        self.stdUnit = amountMotif.match(st).group(1)
                        self.header['Amount SYBR'] = i
                    else:
                        self.header[st] = i
                ncol = len(self.header.keys())

            if len(line) == ncol and ind != 0:
                champs = []
                for field in line:
                    try:
                        dat = float(field.replace(',', '.'))
                    except ValueError:
                        dat = field.strip('"')
                    champs.append(dat)
                if self.header.has_key('Pos'):
                    name = champs[self.header['Pos']]
                    x = Puits(name)
                    if x.xpos > 8 or x.ypos > 12:
                        self.setPlateType('384')
                else:
                    raise KeyError
                if self.header.has_key('Name'):
                    echName = champs[self.header['Name']]
                    x.setEch(Ech(echName))
                if self.header.has_key('Ct SYBR'):
                    ct = champs[self.header['Ct SYBR']]
                    if ct == '':
                        x.setEnabled(False)
                    x.setCt(ct)
                if self.header.has_key('Ct Mean SYBR'):
                    ctmean = champs[self.header['Ct Mean SYBR']]
                    x.setCtmean(ctmean)
                if self.header.has_key('Ct Dev. SYBR'):
                    ctdev = champs[self.header['Ct Dev. SYBR']]
                    x.setCtdev(ctdev)
                if self.header.has_key('Amount SYBR'):
                    amount = champs[self.header['Amount SYBR']]
                    if amount != '-':
                        x.setAmount(amount)
                    else:
                        x.setAmount('')
                if self.header.has_key('Target SYBR'):
                    geneName = champs[self.header['Target SYBR']]
                    x.setGene(Gene(geneName))
                if self.header.has_key('Type'):
                    type = champs[self.header['Type']]
                    x.setType(type)
                if self.header.has_key('NRQ'):
                    nrq = champs[self.header['NRQ']]
                    x.setNRQ(nrq)
                if self.header.has_key('NRQerror'):
                    nrqerror = champs[self.header['NRQerror']]
                    x.setNRQerror(nrqerror)
 
                setattr(self, x.name, x)
                self.listePuits.append(x)

            if len(line) == 2:
                name =  motif.findall(line[0].strip('"'))[0].replace(' ', '')
                value = line[1]
                try:
                    value = float(value)
                except ValueError:
                    pass
                setattr(self, name, value)
        file.close()

    def parseApplied7000(self):
        """
        This method allows to parse Applied 7000 raw data. It supports only
        CSV files.
        """
        file = open(unicode(self.filename), 'r')
        iterator = csv.reader(file, delimiter=returnDelimiter(file))
        hasHeader = False
        for ind, line in enumerate(iterator):
            if len(line) != 0:
                if line[0] == 'Well':
                    hasHeader = True
                    initTab = ind
            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        self.header[field] = i
                    ncol = len(self.header.keys())

                if ind != initTab and len(line) == ncol:
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] not in ('Sample Name',
                                                             'Detector'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('Well'):
                        name = champs[self.header['Well']]
                        x = Puits(name)
                        if x.xpos > 8 or x.ypos > 12:
                            self.setPlateType('384')
                    else:
                        raise KeyError
                    if self.header.has_key('Sample Name'):
                        echName = champs[self.header['Sample Name']]
                        x.setEch(Ech(echName))
                    if self.header.has_key('Ct'):
                        ct = champs[self.header['Ct']]
                        x.setCt(ct)
                    if self.header.has_key('Qty'):
                        try:
                            amount = float(champs[self.header['Qty']])
                            x.setType('standard')
                            x.setAmount(amount)
                        except ValueError:
                            pass
                    if self.header.has_key('Detector'):
                        geneName = champs[self.header['Detector']]
                        x.setGene(Gene(geneName))
                    setattr(self, x.name, x)
                    self.listePuits.append(x)

    def parseApplied7700(self):
        """
        This method allows to parse Applied 7700 raw data. It supports only
        CSV files.
        """
        file = open(unicode(self.filename), 'r')
        iterator = csv.reader(file, delimiter=returnDelimiter(file))
        hasHeader = False
        numbersOnly = re.compile(r"([0-9]+)")
        for ind, line in enumerate(iterator):
            if len(line) != 0:
                if line[0] == 'Well':
                    hasHeader = True
                    initTab = ind
            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        self.header[field] = i
                    ncol = len(self.header.keys())

                if ind != initTab and len(line) == ncol:
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] in ('Ct', 'Quantity'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('Well'):
                        name = champs[self.header['Well']]
                        if numbersOnly.match(name) and len(name) <= 3:
                            x = Puits(name, plateType=96)
                            if int(name) > 96:
                                self.setPlateType('384')
                        else:
                            continue
                    else:
                        raise KeyError
                    if self.header.has_key('Ct'):
                        ct = champs[self.header['Ct']]
                        if ct == '':
                            x.setEnabled(False)
                        x.setCt(ct)
                    #if self.header.has_key('Qty'):
                        #try:
                            #amount = float(champs[self.header['Qty']])
                            #x.setType('standard')
                            #x.setAmount(amount)
                        #except ValueError:
                            #pass
                    #if self.header.has_key('Detector'):
                        #geneName = champs[self.header['Detector']]
                        #x.setGene(Gene(geneName))
                    setattr(self, x.name, x)
                    self.listePuits.append(x)

    def parseApplied7900(self):
        """
        This method allows to parse Applied 7700 raw data. It supports only
        TXT files.
        """
        file = open(unicode(self.filename), 'r')
        iterator = file.readlines()
        file.close()
        ncol = 0
        indheader = 0
        for ind, line in enumerate(iterator):
            linetot = line
            line = line.split('\t')
            if linetot.__contains__('Name'):
                indheader = ind
                self.header = OrderedDict()
                for i, field in enumerate(line):
                    st = field.strip('"')
                    self.header[st] = i
                ncol = len(self.header.keys())

            if len(line) == ncol and ind != indheader:
                champs = []
                for k, field in enumerate(line):
                    dat = field.strip('"')
                    try:
                        if self.header.keys()[k] in ('Ct', 'Quantity'):
                            dat = float(field.replace(',', '.'))
                        else:
                            dat = field
                    except ValueError:
                        pass
                    champs.append(dat)
                if self.header.has_key('Well'):
                    name = champs[self.header['Well']]
                    x = Puits(name, plateType='384')
                    if int(name) > 96:
                        self.setPlateType('384')
                else:
                    raise KeyError
                if self.header.has_key('Ct'):
                    ct = champs[self.header['Ct']]
                    if ct == 'Undetermined':
                        x.setEnabled(False)
                    x.setCt(ct)
                if self.header.has_key('Quantity'):
                    try:
                        am = float(champs[self.header['Quantity']])
                        if am != 0:
                            x.setType('standard')
                            x.setAmount(am)
                    except ValueError:
                        pass
                setattr(self, x.name, x)
                self.listePuits.append(x)

        if self.type == '96': # Recompute coordinate if it is a 96-wells
            for well in self.listePuits:
                delattr(self, well.name)
            for well in self.listePuits:
                well.setName('%i' % ((well.xpos) * 24 + (well.ypos+1)))
                well.getPosition(plateType='96')
                setattr(self, well.name, well)

    def parseAppliedUniv(self):
        """
        This method allows to parse Applied StepOne and AB7500 raw data.
        It works with TXT files and CSV files (comma separated, UTF-8
        encoding).
        """
        file = open(unicode(self.filename), 'Ur')
        fileencoding = "utf-8"
        result = re.compile(r'\[Results\]')
        motifSample = re.compile(r'Reference Sample = (.*)')
        motifTarget = re.compile(r'Endogenous Control = (.*)')
        motifWell = re.compile(r'[A-H][1-9][012]?')
        hasHeader = False
        if self.fileType == 'txt':
            iterator = file.readlines()
            splitter = re.compile(r'([\w .,\-\(\)\[\]\+\\/]*|\d+[.,]?\d*)\t',
                                  re.UNICODE)
        if self.fileType == 'csv':
            iterator = csv.reader(file, delimiter=returnDelimiter(file))

        for ind, line in enumerate(iterator):
            if self.fileType == 'txt': 
                line = line.decode(fileencoding)
                rawline = line
                line = splitter.findall(line)
            elif self.fileType == 'csv':
                rawline = string.join(line, '')
                for k in range(len(line)):
                    line[k] = line[k].decode(fileencoding)

            if len(result.findall(rawline)) != 0:
                hasHeader = True
                initTab = ind + 1
                continue

            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        self.header[field] = i
                    ncol = len(self.header.keys())
                if ind != initTab and len(line) >= ncol-1 and \
                        motifWell.match(line[self.header['Well']]):
                    # Tricky solution for CSV file with missing final colon
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] not in ('Sample Name',
                                                             'Target Name'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('Well'):
                        name = champs[self.header['Well']]
                        x = Puits(name)
                        if x.xpos > 8 or x.ypos > 12:
                            self.setPlateType('384')
                    else:
                        raise KeyError
                    if self.header.has_key('Sample Name'):
                        echName = champs[self.header['Sample Name']]
                        x.setEch(Ech(echName))
                    if self.header.has_key(u'C\u0442'):
                        ct = champs[self.header[u'C\u0442']]
                        if ct == 'Undetermined':
                            x.setEnabled(False)
                        x.setCt(ct)
                    if self.header.has_key(u'C\u0442 Mean'):
                        ctmean = champs[self.header[u'C\u0442 Mean']]
                        x.setCtmean(ctmean)
                    if self.header.has_key(u'C\u0442 SD'):
                        ctdev = champs[self.header[u'C\u0442 SD']]
                        x.setCtdev(ctdev)
                    if self.header.has_key('Quantity'):
                        try:
                            amount = float(champs[self.header['Quantity']])
                            x.setType('standard')
                            x.setAmount(amount)
                        except ValueError:
                            pass
                    if self.header.has_key('Target Name'):
                        geneName = champs[self.header['Target Name']]
                        x.setGene(Gene(geneName))
                    if self.header.has_key(u'\u0394\u0394C\u0442'):
                        nrq = champs[self.header[u'\u0394\u0394C\u0442']]
                        x.setNRQ(nrq)

                    setattr(self, x.name, x)
                    self.listePuits.append(x)
            if motifSample.match(rawline):
                self.echRef = QString(motifSample.findall(rawline)[0])
            if motifTarget.match(rawline):
                newGeneRef = QString(motifTarget.findall(rawline)[0])
                if newGeneRef not in self.geneRef:
                    self.geneRef.append(newGeneRef)
        file.close()

    def parseBioradMyIQ(self):
        """
        This method allows to parse Biorad MyIQ raw data. It supports only
        CSV files. In fact Biorad export MyIQ only in XLS format, so one has
        to export in CSV form Excel or OpenOffice.
        """
        file = open(unicode(self.filename), 'r')
        iterator = csv.reader(file, delimiter=returnDelimiter(file))
        hasHeader = False
        for ind, line in enumerate(iterator):
            if len(line) != 0:
                if string.join(line).__contains__('Well'):
                    hasHeader = True
                    initTab = ind
            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        self.header[field] = i
                    ncol = len(self.header.keys())

                if ind != initTab and len(line) == ncol:
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] in ('Threshold Cycle (Ct)', 
                                'Ct Mean', 'Ct Std. Dev', 'Starting Quantity (SQ)'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('Well'):
                        name = champs[self.header['Well']]
                        x = Puits(name)
                        if x.xpos > 8 or x.ypos > 12:
                            self.setPlateType('384')
                    else:
                        raise KeyError

                    if self.header.has_key('Identifier'):
                        name = champs[self.header['Identifier']]
                        if name.__contains__('_'):
                            dat = name.split('_')
                        elif name.__contains__('-'):
                            dat = name.split('-')
                        else:
                            dat = name
                        if len(dat) == 2:
                            x.setGene(Gene(dat[0]))
                            x.setEch(Ech(dat[1]))
                        else:
                            x.setGene(Gene(name))
                    if self.header.has_key('Threshold Cycle (Ct)'):
                        ct = champs[self.header['Threshold Cycle (Ct)']]
                        x.setCt(ct)
                    if self.header.has_key('Threshold Cycle (Ct)'):
                        ct = champs[self.header['Threshold Cycle (Ct)']]
                        if ct == 'N/A':
                            x.setEnabled(False)
                        x.setCt(ct)
                    if self.header.has_key('Ct Mean'):
                        ctmean = champs[self.header['Ct Mean']]
                        x.setCtmean(ctmean)
                    if self.header.has_key('Ct Std. Dev'):
                        ctdev = champs[self.header['Ct Std. Dev']]
                        x.setCtdev(ctdev)
                    if self.header.has_key('Starting Quantity (SQ)'):
                        try:
                            amount = float(champs[ \
                                           self.header['Starting Quantity (SQ)']])
                            if amount != 0:
                                x.setType('standard')
                                x.setAmount(amount)
                        except ValueError:
                            pass
                    if self.header.has_key('Type'):
                        type = champs[self.header['Type']]
                        if type == 'Unkn':
                            x.setType('unknown')
                        elif type == 'Std':
                            x.setType('standard')
                    setattr(self, x.name, x)
                    self.listePuits.append(x)

    def parseCorbett(self):
        """
        This method allows to parse the Qiagen Corbett files (CSV only).
        This machine uses only rotors of 72 or 100 wells, so it behaves
        a bit differantly than usual plates of 96/384 wells.
        """
        self.setPlateType('72')
        file = open(unicode(self.filename), 'r')
        iterator = csv.reader(file, delimiter=returnDelimiter(file))
        hasHeader = False
        for ind, line in enumerate(iterator):
            if len(line) != 0:
                if string.join(line).__contains__('No.'):
                    hasHeader = True
                    initTab = ind
            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        if field.startswith('Given Conc'):
                            field = 'Given Conc'
                        self.header[field] = i
                    ncol = len(self.header.keys())

                if ind != initTab and len(line) == ncol:
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] in ('Ct', 'Given Conc'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('No.'):
                        name = champs[self.header['No.']]
                        x = Puits(name, plateType='72')
                        if x.xpos > 9 or x.ypos > 8:
                            self.setPlateType('100')
                    else:
                        raise KeyError

                    if self.header.has_key('Name'):
                        name = champs[self.header['Name']]
                        if name.__contains__(' '):
                            dat = name.split(' ')
                        else:
                            dat = name
                        if len(dat) == 2:
                            x.setGene(Gene(dat[0]))
                            x.setEch(Ech(dat[1]))
                        if len(dat) > 2:
                            x.setGene(Gene(dat[0]))
                        else:
                            x.setGene(Gene(name))
                    if self.header.has_key('Ct'):
                        ct = champs[self.header['Ct']]
                        if ct == '':
                            x.setEnabled(False)
                        x.setCt(ct)
                    if self.header.has_key('Given Conc'):
                        try:
                            amount = float(champs[self.header['Given Conc']])
                            if amount != 0:
                                x.setType('standard')
                                x.setAmount(amount)
                        except ValueError:
                            pass
                    if self.header.has_key('Type'):
                        type = champs[self.header['Type']]
                        if type == 'Unknown':
                            x.setType('unknown')
                        elif type == 'Standard':
                            x.setType('standard')
                    setattr(self, x.name, x)
                    self.listePuits.append(x)

        if self.type == '100': # Recompute coordinate if there are 100-wells
            for well in self.listePuits:
                delattr(self, well.name)
            for well in self.listePuits:
                well.setName('%i' % ((well.xpos) * 8 + (well.ypos+1)))
                well.getPosition(plateType='100')
                setattr(self, well.name, well)

    def parseCepheid(self):
        """
        This method allows to parse the Cepheid SmartCycler files (CSV only).
        """
        self.setPlateType('16')
        file = open(unicode(self.filename), 'r')
        iterator = csv.reader(file, delimiter=returnDelimiter(file))
        hasHeader = False
        for ind, line in enumerate(iterator):
            if len(line) != 0:
                if string.join(line).__contains__('Site ID'):
                    hasHeader = True
                    initTab = ind
            if hasHeader:
                if ind == initTab:
                    self.header = OrderedDict()
                    for i, field in enumerate(line):
                        self.header[field] = i
                    ncol = len(self.header.keys())

                if ind != initTab and len(line) == ncol:
                    champs = []
                    for k, field in enumerate(line):
                        try:
                            if self.header.keys()[k] in ('FAM Ct', 'FAM Std/Res'):
                                dat = float(field.replace(',', '.'))
                            else:
                                dat = field
                        except ValueError:
                            dat = field
                        champs.append(dat)
                    if self.header.has_key('Site ID'):
                        name = champs[self.header['Site ID']]
                        x = Puits(name)
                    else:
                        raise KeyError

                    #if self.header.has_key('Name'):
                        #name = champs[self.header['Name']]
                        #if name.__contains__(' '):
                            #dat = name.split(' ')
                        #else:
                            #dat = name
                        #if len(dat) == 2:
                            #x.setGene(Gene(dat[0]))
                            #x.setEch(Ech(dat[1]))
                        #if len(dat) > 2:
                            #x.setGene(Gene(dat[0]))
                        #else:
                            #x.setGene(Gene(name))
                    if self.header.has_key('FAM Ct'):
                        ct = champs[self.header['FAM Ct']]
                        if ct == 0.:
                            x.setEnabled(False)
                        x.setCt(ct)
                    if self.header.has_key('FAM Std/Res'):
                        try:
                            amount = float(champs[self.header['FAM Std/Res']])
                            if amount != 0:
                                x.setType('standard')
                                x.setAmount(amount)
                        except ValueError:
                            pass
                    if self.header.has_key('Sample Type'):
                        type = champs[self.header['Sample Type']]
                        if type == 'UNKN':
                            x.setType('unknown')
                        elif type == 'STD':
                            x.setType('standard')
                    setattr(self, x.name, x)
                    self.listePuits.append(x)

    def subPlate(self, listWells):
        """
        This method allows to extract a subplate from a plate.

        :param listWells: the list of the wells we want to extract 
                          from the main plate.
        :type listWells: list
        """
        self.listePuits = listWells
        for well in self.listePuits:
            setattr(self, well.name, well)

    def writeHtml(self, ctMin=35, ectMax=0.3, typeCalc='Relative quantification'):
        """
        This method allows to represent the results of a plate in a HTML table.
        It is used for instance during the PDF export of pyQPCR.

        :param ctMin: the minimum ct value allowed
        :type ctMin: float
        :param ectMax: the maximum value of E(ct)
        :type ectMax: float
        :param typeCalc: the type of calculation
        :type typeCalc: PyQt4.QtCore.QString
        """
        html = u""
        html += "<table cellpadding=2 cellspacing=0 border=1 width=100%>\n"
        html += ("<tr>\n"
                 "<th align=center>Well</th>\n"
                 "<th align=center>Type</th>\n"
                 "<th align=center>Target</th>\n"
                 "<th align=center>Sample</th>\n"
                 "<th align=center>Ct</th>\n"
                 "<th align=center>Ctmean</th>\n"
                 "<th align=center>Ctdev</th>\n"
                 "<th align=center>Amount</th>\n"
                 "<th align=center>Efficiency</th>\n")
        if typeCalc == 'Relative quantification':
            html +=  ("<th align=center>NRQ</th>\n"
                     "<th align=center>NRQerror</th>\n"
                     "</tr>\n")
        elif typeCalc == 'Absolute quantification':
            html +=  ("<th align=center>Qabs</th>\n"
                     "<th align=center>QabsError</th>\n"
                     "</tr>\n")
        for well in self.listePuits:
            html += well.writeHtml(ctMin, ectMax)
        html += "</table>"
        return html

    def setUkn(self, cont):
        """
        A method to change the attribute contUkn. This attribute is set to
        True if the plate contains one (or more) 'unknown'-type wells.

        :param cont: a boolean with the new value of contUkn
        :type cont: logical
        """
        self.contUkn = cont

    def setDicoGene(self):
        """
        A method to construct the attribute dicoGene.
        It is an ordered dictionnary struture of type

            >>> self.dicoGene[geneName] = list of wells
        """
        self.dicoGene = OrderedDict()
        for well in self.listePuits:
            nomgene = well.gene.name
            if nomgene != '':
                if self.dicoGene.has_key(nomgene):
                    self.dicoGene[nomgene].append(well)
                else:
                    self.dicoGene[nomgene] = [well]

    def setDicoEch(self):
        """
        A method to construct the attribute dicoEch.
        It is an ordered dictionnary struture of type

            >>> self.dicoEch[echName] = list of wells
        """
        self.dicoEch = OrderedDict()
        for well in self.listePuits:
            nomech = well.ech.name
            if nomech != '':
                if self.dicoEch.has_key(nomech):
                    self.dicoEch[nomech].append(well)
                else:
                    self.dicoEch[nomech] = [well]


class StdObject:
    """
    StdObject is a small object used in standard curve calculation. 
    Basically, it is used to store the data associated with the linear 
    regression (abscissa, ordinate,
    slope, Pearsson's coefficient, ...).
    """

    def __init__(self, x, y, yest, slope, orig, R2, eff, stdeff, slopeerr, origerr):
        """
        Constructor of StdObject

        :param x: the abscissa before linear regression
        :type x: numpy.ndarray
        :param y: the ordinate before linear regression
        :type y: numpy.ndarray
        :param yest: the estimate of ordinate after linear regression
        :type yest: numpy.ndarray
        :param slope: the slope of the linear regression
        :type slope: float
        :param orig: the ordinate at the origin of the linear regression
        :type orig: float
        :param R2: the Pearsson's coefficient
        :type R2: float
        :param eff: the efficiency computed thanks to the slope
        :type eff: float
        :param stdeff: the standard error associated with the efficiency
        :type stdeff: float
        :param slopeerr: the standard error associated with the slope
        :type slopeerr: float
        :param origerr: the standard error associated with the origin
        :type origerr: float
        """
        self.x = x
        self.y = y
        self.yest = yest
        self.slope = slope
        self.orig = orig
        self.R2 = R2
        self.eff = eff
        self.stdeff = stdeff
        self.slopeerr = slopeerr
        self.origerr = origerr


class Replicate:
    """
    A Replicate object contains several wells. It is constructed from
    a list of wells and their type.

    >>> A1 = Puits('A1', ct=23.1)
    >>> A2 = Puits('A2', ct=24.0)
    >>> A3 = Puits('A2', ct=22.9)
    >>> wells = [A1, A2, A3]
    >>> re = Replicate(wells)

    :attribute confidence: the confidence level
    :attribute errtype: the type of error (Student t test or Gaussian)
    :attribute type: the type of the wells in the replicate (unknown
                     or standard)
    :attribute listePuits: the list of the wells of the replicate
    """

    def __init__(self, listePuits, type=QString('unknown'), 
                 confidence=0.9, errtype="normal"):
        """
        Constructor of Replicate

        :param listePuits: a list containing the wells of a replicate
        :type listePuits: list
        :param type: the type of the replicate (unknown, standard or negative)
        :type type: PyQt4.QtCore.QString
        :param confidence: the confidence level
        :type confidence: float
        :param errtype: the type of calculation for the errors (normal or Student)
        :type errtype: string
        """
        self.confidence = confidence
        self.errtype = errtype
        self.type = type
        self.listePuits = listePuits

        if len(self.listePuits) != 0:
            self.gene = self.listePuits[0].gene
        else:
            self.gene = Gene('')

        self.ctList =array([])
        for well in self.listePuits:
            self.ctList = append(self.ctList, well.ct)

        if self.type == QString('unknown'):
            self.ech = self.listePuits[0].ech
        elif self.type == QString('standard'):
            self.amList = array([])
            for well in self.listePuits:
                self.amList = append(self.amList, well.amount)
        self.calcMeanDev()

    def __cmp__(self, other):
        """
        This method allows to compare two replicates:

        :param other: a replicate
        :type other: pyQPCR.plate.Replicate
        """
        if self.confidence != other.confidence:
            return cmp(self.confidence, other.confidence)
        if self.type != other.type:
            return cmp(self.type, other.type)
        if self.errtype != other.errtype:
            return cmp(self.errtype, other.errtype)
        if self.ctList != other.ctList:
            return cmp(self.ctList, other.ctList)
        return cmp(self.listePuits, other.listePuits)

    def __str__(self):
        """
        A method to print Replicate object
        """
        st = '{%s:[' % self.type
        for well in self.listePuits:
            st = st + well.name + ','
        st += ']'
        if self.type == QString('unknown'):
            st += ' %s, %s}' % (self.gene, self.ech)
        else:
            st += ' %s}' % self.gene
        return st

    def __repr__(self):
        """
        A method to print Replicate object
        """
        st = '['
        for well in self.listePuits:
            st = st + well.name + ','
        st += ']'
        return st

    def setNRQ(self, NRQ):
        """
        Set the value of NRQ computed with the quantifications.

        :param NRQ: the value of NRQ for the replicate
        :type NRQ: float
        """
        self.NRQ = NRQ

    def setNRQerror(self, NRQerr):
        """
        Set the value of standard error of NRQ

        :param NRQerr: the standard error of NRQ for the replicate
        :type NRQerr: float
        """
        self.NRQerror = NRQerr

    def calcMeanDev(self):
        r"""
        Compute the mean ct of a replicate as well as the standard error.

        .. math:: {c_t}_{\text{mean}} = \dfrac{1}{n}\sum c_t

        .. math:: {c_t}_{\text{dev}} = \dfrac{t_{\alpha}^{n-2}}
                  {\sqrt{n}(n-1)}\sqrt{\sum (c_t
                  -{c_t}_{\text{mean}})^2}
        """
        try:
            self.ctmean = self.ctList.mean()
        except TypeError:
            brokenWells = []
            for well in self.listePuits:
                try:
                    f = float(well.ct)
                except ValueError:
                    brokenWells.append(well.name)
                    well.setWarning(True)
            raise WellError(brokenWells)

        if len(self.ctList) > 1:
            # Formule 8
            stdctList = self.ctList.std()*sqrt(1./(len(self.ctList)-1.))
            if self.errtype == "student":
                # coeff Student
                talpha = t.ppf(1.-(1.-self.confidence)/2., len(self.ctList)-1) 
            elif self.errtype == "normal":
                talpha = norm.ppf(1.-(1.-self.confidence)/2.) # Gaussian
            self.ctdev = stdctList*sqrt(len(self.ctList)-1.)
            self.ctdevtalpha = talpha * stdctList
        else:
            self.ctdev = 0.
            self.ctdevtalpha = 0.

        for well in self.listePuits:
            well.setCtmean(self.ctmean)
            well.setCtdev(self.ctdev)

    def calcDCt(self):
        r"""
        A method to compute the difference between ctref and the mean ct
        of the replicate and then compute the value of RQ.

        .. math:: \Delta c_t = {c_t}_{\text{ref}} - {c_t}_{\text{mean}}

        .. math:: RQ = (1+\text{eff}/100)^{\Delta c_t}
        """
        self.dct = self.gene.ctref - self.ctmean # Formule 10
        self.RQ = (1.+self.gene.eff/100.)**(self.dct) # Formule 11

    def calcRQerror(self):
        r"""
        A method to compute the standard error of RQ.

        .. math:: \text{SE}(RQ) = RQ\sqrt{\left(\dfrac{\Delta c_t
                  \text{SE}(\text{eff})/100}{1+\text{eff}/100}\right)^2+
                  \left(\ln(1+\text{eff}/100)\text{SE}(c_t)\right)^2}
        """
        # Formule 12
        err = sqrt( self.RQ**2 * ((self.dct*(self.gene.pm/100.) \
                /(1.+self.gene.eff/100.))**2 \
                + (log(1.+self.gene.eff/100.)*self.ctdevtalpha)**2 \
                ))
        self.RQerror = err


class ReplicateError(Exception):
    """
    This exception is raised if an error occur in a replicate
    """

    def __init__(self, listRep):
        """
        Constructor of ReplicateError

        :param listRep: a list of Replicates
        :type listRep: list
        """
        self.listRep = listRep

    def __str__(self):
        """
        Print method
        """
        st = "<ul>"
        for trip in self.listRep:
            st += "<li>(<b>%s, %s</b>) : E(ct)=%.2f </li>" % (trip.gene, 
                                                    trip.ech, trip.ctdev)
        st += "</ul>"

        return st

class PlateError(Exception):
    """
    Exception raised if a problem occured during file parsing.
    """

    def __init__(self, filename, machine):
        """
        Constructor of PlateError

        :param filename: the file name
        :type filename: PyQt4.QtCore.QString
        :param machine: the PCR device
        :type machine: PyQt4.QtCore.QString
        """
        self.filename = filename
        self.machine = machine

    def __str__(self):
        """
        Print method
        """
        st = "<b>Warning</b> : The file <b>%s </b> does not contain any well at the right format. " %  \
              QFileInfo(self.filename).fileName()
        st += "It probably comes from your raw data file. Your current PCR device is"
        st += " <b>%s</b>, check your file corresponds to this machine !" % self.machine
        st += " If the error continues to occur, post a message at "
        st += r' <a href="http://sourceforge.net/projects/pyqpcr/forums/forum/918935">'
        st += r'http://sourceforge.net/projects/pyqpcr/forums/forum/918935</a>'
        return st


if __name__ == '__main__':
    pl = Plaque('raw_data_corbett2.csv', machine='Qiagen Corbett')
    print pl.type
    print pl.B1
    pl = Plaque('raw_data_corbett3.csv', machine='Qiagen Corbett')
    print pl.type
    print pl.A9
