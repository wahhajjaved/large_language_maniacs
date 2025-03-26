# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'jmdelarosa@cnb.csic.es'
# *
# **************************************************************************
"""
In this module are protocol base classes related to EM imports of Micrographs, Particles, Volumes...
"""

from os.path import exists, basename

from pyworkflow.utils.properties import Message
from pyworkflow.protocol.params import FloatParam, FileParam
from pyworkflow.utils.path import copyFile
from pyworkflow.em.data import Volume, PdbFile
from pyworkflow.em.convert import ImageHandler

from base import ProtImport
from images import ProtImportImages



class ProtImportVolumes(ProtImportImages):
    """Protocol to import a set of volumes to the project"""
    _outputClassName = 'SetOfVolumes'
    _label = 'import volumes'
    
    def __init__(self, **args):
        ProtImportImages.__init__(self, **args)         
       
    def _defineAcquisitionParams(self, form):
        """ Define acquisition parameters, it can be overriden
        by subclasses to change what parameters to include.
        """
        form.addParam('samplingRate', FloatParam,
                   label=Message.LABEL_SAMP_RATE)
    
    def _insertAllSteps(self):
        self._insertFunctionStep('importVolumesStep', self.getPattern(), self.samplingRate.get())

    #--------------------------- STEPS functions ---------------------------------------------------
    
    def importVolumesStep(self, pattern, samplingRate):
        """ Copy images matching the filename pattern
        Register other parameters.
        """
        self.info("Using pattern: '%s'" % pattern)
        
        # Create a Volume template object
        vol = Volume()
        vol.setSamplingRate(self.samplingRate.get())
        copyOrLink = self.getCopyOrLink()
        imgh = ImageHandler()
        
        volSet = self._createSetOfVolumes()
        volSet.setSamplingRate(self.samplingRate.get())
        
        for fileName, fileId in self.iterFiles():
            dst = self._getExtraPath(basename(fileName))
            copyOrLink(fileName, dst)
            _, _, _, n = imgh.getDimensions(dst)
            if n > 1:
                for index in range(1, n+1):
                    vol.cleanObjId()
                    vol.setLocation(index, dst)
                    volSet.append(vol)
            else:
                vol.setObjId(fileId)
                vol.setLocation(dst)
                volSet.append(vol)
        
        if volSet.getSize() > 1:
            self._defineOutputs(outputVolumes=volSet)
        else:
            self._defineOutputs(outputVolume=vol)
        
    #--------------------------- INFO functions ----------------------------------------------------
    
    def _getVolMessage(self):
        if self.hasAttribute('outputVol'):
            return "*one* volume"
        else:
            return "*%d* volumes" % self.outputVolumes.getSize()
        
    def _summary(self):
        summary = []
        summary.append("Imported %s from:\n%s" % (self._getVolMessage(), self.getPattern()))
        summary.append("Sampling rate: *%0.2f* (A/px)" % self.samplingRate.get())
        return summary
    
    def _methods(self):
        methods = []
        methods.append("Used %s with a sampling rate *%0.2f*." % (self._getVolMessage(), self.samplingRate.get()))
        return methods
    
    
        
class ProtImportPdb(ProtImport):
    """ Protocol to import a set of pdb volumes to the project"""
    _label = 'import pdb volumes'
    
    def __init__(self, **args):
        ProtImport.__init__(self, **args)         
       
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('pdbPath', FileParam, 
                      label="PDB file",
                      help='Specify a path to desired PDB structure.')
         
    def _insertAllSteps(self):
        self._insertFunctionStep('createOutputStep', self.pdbPath.get())
        
    def createOutputStep(self, pdbPath):
        """ Copy the PDB structure and register the output object.
        """
        if not exists(pdbPath):
            raise Exception("PDB not found at *%s*" % pdbPath)
        
        baseName = basename(pdbPath)
        localPath = self._getExtraPath(baseName)
        copyFile(pdbPath, localPath)
        pdb = PdbFile()
        pdb.setFileName(localPath)
        self._defineOutputs(outputPdb=pdb)

    def _summary(self):
        summary = ['PDB file imported from *%s*' % self.pdbPath.get()]

        return summary
    
    def _validate(self):
        errors = []
        if not exists(self.pdbPath.get()):
            errors.append("PDB not found at *%s*" % self.pdbPath.get())
        #TODO: maybe also validate that if exists is a valid PDB file 
        return errors
    
    
