# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk)
# *
# * MRC Laboratory of Molecular Biology (MRC-LMB)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
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
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************

import os
from io import open

import pyworkflow.protocol.params as params
from pwem.protocols import ProtAnalysis3D
from pwem.emlib.image import ImageHandler
from pwem.objects import Volume
from pyworkflow.utils import exists

from .. import Plugin


class Prot3DFSC(ProtAnalysis3D):
    """ Protocol to calculate 3D FSC.

    3D FSC is software tool for quantifying directional
    resolution using 3D Fourier shell correlation volumes.
     
    Find more information at https://github.com/nysbc/Anisotropy
    """
    _label = 'estimate resolution'

    INPUT_HELP = """ Required input volumes for 3D FSC:
        1. First half map of 3D reconstruction. Can be masked or unmasked.
        2. Second half map of 3D reconstruction. Can be masked or unmasked.
        3. Full map of 3D reconstruction. Can be masked or unmasked, sharpened or unsharpened.
    """
    
    def __init__(self, **kwargs):
        ProtAnalysis3D.__init__(self, **kwargs)

    def _initialize(self):
        """ This function is mean to be called after the
        working dir for the protocol have been set. (maybe after recovery from mapper)
        """
        self._createFilenameTemplates()

    def _createFilenameTemplates(self):
        """ Centralize how files are called for iterations and references. """
        myDict = {
                  'input_volFn': self._getExtraPath('volume_full.mrc'),
                  'input_half1Fn': self._getExtraPath('volume_half1.mrc'),
                  'input_half2Fn': self._getExtraPath('volume_half2.mrc'),
                  'input_maskFn': self._getExtraPath('mask.mrc'),
                  'out_histogram': self._getExtraPath('Results_3D-FSC/histogram.png'),
                  'out_plot3DFSC': self._getExtraPath('Results_3D-FSC/Plots3D-FSC.jpg'),
                  'out_plotFT': self._getExtraPath('Results_3D-FSC/FTPlot3D-FSC.jpg'),
                  'out_vol3DFSC': self._getExtraPath('Results_3D-FSC/3D-FSC.mrc'),
                  'out_vol3DFSC-th': self._getExtraPath('Results_3D-FSC/3D-FSC_Thresholded.mrc'),
                  'out_vol3DFSC-thbin': self._getExtraPath('Results_3D-FSC/3D-FSC_ThresholdedBinarized.mrc'),
                  'out_cmdChimera': self._getExtraPath('Results_3D-FSC/Chimera/3DFSCPlot_Chimera.cmd'),
                  'out_globalFSC': self._getExtraPath('Results_3D-FSC/ResEM3D-FSCOutglobalFSC.csv')
                  }

        self._updateFilenamesDict(myDict)

    # --------------------------- DEFINE param functions ----------------------

    def _defineParams(self, form):
        form.addHidden(params.USE_GPU, params.BooleanParam, default=False,
                       label="Use GPU?")
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       label="Choose GPU ID",
                       help="Each GPU has a unique ID. If you have only "
                            "one GPU, set ID to 0. 3DFSC can use only one GPU.")

        form.addSection(label='Input')
        form.addParam('inputVolume', params.PointerParam,
                      pointerClass='Volume',
                      label="Input volume", important=True,
                      help=self.INPUT_HELP)
        form.addParam('volumeHalf1', params.PointerParam,
                      label="Volume half 1", important=True,
                      pointerClass='Volume',
                      help=self.INPUT_HELP)
        form.addParam('volumeHalf2', params.PointerParam,
                      pointerClass='Volume',
                      label="Volume half 2", important=True,
                      help=self.INPUT_HELP)

        form.addParam('applyMask', params.BooleanParam, default=False,
                      label="Mask input volume?",
                      help='If given, it would be used to mask the half maps '
                           'during 3DFSC generation and analysis.')
        form.addParam('maskVolume', params.PointerParam, label="Mask volume",
                      pointerClass='VolumeMask', condition="applyMask",
                      help='Select a volume to apply as a mask.')

        form.addSection(label='Extra params')
        form.addParam('dTheta', params.FloatParam, default=20,
                      label='Angle of cone (deg)',
                      help='Angle of cone to be used for 3D FSC sampling in '
                           'degrees. Default is 20 degrees.')
        form.addParam('fscCutoff', params.FloatParam, default=0.143,
                      label='FSC cutoff',
                      help='FSC cutoff criterion. 0.143 is default.')
        form.addParam('thrSph', params.FloatParam, default=0.5,
                      label='Sphericity threshold',
                      help='Threshold value for 3DFSC volume for calculating '
                           'sphericity. 0.5 is default.')
        form.addParam('hpFilter', params.FloatParam, default=200,
                      label='High-pass filter (A)',
                      help='High-pass filter for thresholding in Angstrom. '
                           'Prevents small dips in directional FSCs at low '
                           'spatial frequency due to noise from messing up '
                           'the thresholding step. Decrease if you see a '
                           'huge wedge missing from your thresholded 3DFSC '
                           'volume. 200 Angstroms is default.')
        form.addParam('numThr', params.IntParam, default=1,
                      label='Number of threshold for sphericity',
                      help='Calculate sphericities at different threshold '
                           'cutoffs to determine sphericity deviation across '
                           'spatial frequencies. This can be useful to '
                           'evaluate possible effects of overfitting or '
                           'improperly assigned orientations.')

    # --------------------------- INSERT steps functions ----------------------
    
    def _insertAllSteps(self):
        # Insert processing steps
        self._initialize()
        self._insertFunctionStep('convertInputStep')
        self._insertFunctionStep('run3DFSCStep')
        self._insertFunctionStep('createOutputStep')

    # --------------------------- STEPS functions -----------------------------
    
    def convertInputStep(self):
        """ Convert input volumes to .mrc as expected by 3DFSC."""
        ih = ImageHandler()

        ih.convert(self.volumeHalf1.get().getLocation(),
                   self._getFileName('input_half1Fn'))
        ih.convert(self.volumeHalf2.get().getLocation(),
                   self._getFileName('input_half2Fn'))
        ih.convert(self.inputVolume.get().getLocation(),
                   self._getFileName('input_volFn'))
        if self.maskVolume.get() is not None:
            ih.convert(self.maskVolume.get().getLocation(),
                       self._getFileName('input_maskFn'))

    def run3DFSCStep(self):
        args = self._getArgs()
        params = ' '.join(['%s=%s' % (k, str(v)) for k, v in args.items()])

        if self.useGpu:
            params += ' --gpu --gpu_id=%s' % self.gpuList.get()

        Plugin.runProgram(self, params, cwd=self._getExtraPath())
        if not exists(self._getFileName('out_vol3DFSC')):
            raise Exception('3D FSC run failed!')

    def createOutputStep(self):
        if exists(self._getFileName('out_vol3DFSC')):
            inputVol = self.inputVolume.get()
            vol = Volume()
            vol.setObjLabel('3D FSC')
            vol.setFileName(self._getFileName('out_vol3DFSC'))
            vol.setSamplingRate(inputVol.getSamplingRate())

            self._defineOutputs(outputVolume=vol)
            self._defineSourceRelation(self.inputVolume, vol)

    # --------------------------- INFO functions ------------------------------
    
    def _summary(self):
        summary = []
        if self.getOutputsSize() > 0:
            logFn = self.getLogPaths()[0]
            sph = self.findSphericity(logFn)
            summary.append('Sphericity: %0.3f ' % sph)
        else:
            summary.append("Output is not ready yet.")

        return summary
    
    def _validate(self):
        errors = []

        half1 = self.volumeHalf1.get()
        half2 = self.volumeHalf2.get()
        mask = self.maskVolume.get() or None
        if half1.getSamplingRate() != half2.getSamplingRate():
            errors.append('The selected half volumes have not the same pixel '
                          'size.')
        if half1.getXDim() != half2.getXDim():
            errors.append('The selected half volumes have not the same '
                          'dimensions.')
        if self.applyMask and (mask.getXDim() != self.inputVolume.get().getXDim()):
            errors.append('Input volume and the mask have different '
                          'dimensions.')
                
        return errors
    
    # --------------------------- UTILS functions -----------------------------
 
    def _getArgs(self):
        """ Prepare the args dictionary."""

        args = {'--halfmap1': os.path.basename(self._getFileName('input_half1Fn')),
                '--halfmap2': os.path.basename(self._getFileName('input_half2Fn')),
                '--fullmap': os.path.basename(self._getFileName('input_volFn')),
                '--apix': self.inputVolume.get().getSamplingRate(),
                '--ThreeDFSC': '3D-FSC',
                '--dthetaInDegrees': self.dTheta.get(),
                '--FSCCutoff': self.fscCutoff.get(),
                '--ThresholdForSphericity': self.thrSph.get(),
                '--HighPassFilter': self.hpFilter.get(),
                '--numThresholdsForSphericityCalcs': self.numThr.get()
                }
        if self.applyMask and self.maskVolume:
            args.update({'--mask': os.path.basename(self._getFileName('input_maskFn'))})

        args.update({'--histogram': os.path.basename(self._getFileName('out_histogram'))})

        return args

    def findSphericity(self, fn):
        f = open(fn, 'r')
        sph = 0.
        for line in f.readlines():
            if 'Sphericity is ' in line:
                sph = float(line.split()[2])
        f.close()

        return sph
