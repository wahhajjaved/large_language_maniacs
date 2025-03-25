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
This module contains the protocol base class for Relion protocols
"""

import os
import re
from glob import glob
from os.path import join, exists

import xmipp
from pyworkflow.protocol.params import (BooleanParam, PointerParam, FloatParam, 
                                        IntParam, EnumParam, StringParam)
from pyworkflow.protocol.constants import LEVEL_ADVANCED, LEVEL_EXPERT
from pyworkflow.utils.path import cleanPath
from pyworkflow.em.data import SetOfClasses3D
from pyworkflow.em.protocol import EMProtocol

from constants import ANGULAR_SAMPLING_LIST, MASK_FILL_ZERO
from convert import (createClassesFromImages
                   , addRelionLabels
                   , restoreXmippLabels
                   , convertBinaryFiles)


class ProtRelionBase(EMProtocol):
    """ This class cointains the common functionalities for all Relion protocols.
    In subclasses there should be little changes about how to create the command line
    and the files produced.
    
    Most of the Relion protocols, have two modes: NORMAL or CONTINUE. That's why
    some of the function have a template pattern approach to define the behaivour
    depending on the case.
    """
    _label = '2d classify'
    IS_CLASSIFY = True
    IS_2D = False
    OUTPUT_TYPE = SetOfClasses3D
    FILE_KEYS = ['data', 'optimiser', 'sampling'] 
    CLASS_LABEL = xmipp.MDL_REF
    CHANGE_LABELS = [xmipp.MDL_AVG_CHANGES_ORIENTATIONS, 
                 xmipp.MDL_AVG_CHANGES_OFFSETS, 
                 xmipp.MDL_AVG_CHANGES_CLASSES]
    PREFIXES = ['']
    
    def __init__(self, **args):        
        EMProtocol.__init__(self, **args)
        
    def _initialize(self):
        """ This function is mean to be called after the 
        working dir for the protocol have been set. (maybe after recovery from mapper)
        """
        self._createFilenameTemplates()
        self._createIterTemplates()
        
        self.ClassFnTemplate = '%(rootDir)s/relion_it%(iter)03d_class%(ref)03d.mrc:mrc'
        self.outputClasses = 'classes_ref3D.xmd'
        self.outputVols = 'volumes.xmd'
        self.haveDataPhaseFlipped = self._getInputParticles().isPhaseFlipped()
    
    def _createFilenameTemplates(self):
        """ Centralize how files are called for iterations and references. """
        self.extraIter = self._getExtraPath('relion_it%(iter)03d_')
        myDict = {
                  'input_star': self._getPath('input_particles.star'),
                  'input_mrcs': self._getPath('input_particles.mrcs'),
                  'data_sorted_xmipp': self.extraIter + 'data_sorted_xmipp.star',
                  'classes_scipion': self.extraIter + 'classes_scipion.sqlite',
                  'angularDist_xmipp': self.extraIter + 'angularDist_xmipp.xmd',
                  'all_avgPmax_xmipp': self._getTmpPath('iterations_avgPmax_xmipp.xmd'),
                  'all_changes_xmipp': self._getTmpPath('iterations_changes_xmipp.xmd'),
                  'selected_volumes': self._getTmpPath('selected_volumes_xmipp.xmd'),
                  'movie_particles': self._getPath('movie_particles.star')
                  }
        # add to keys, data.star, optimiser.star and sampling.star
        for key in self.FILE_KEYS:
            myDict[key] = self.extraIter + '%s.star' % key
            key_xmipp = key + '_xmipp'             
            myDict[key_xmipp] = self.extraIter + '%s.xmd' % key
        # add other keys that depends on prefixes
        for p in self.PREFIXES:            
            myDict['%smodel' % p] = self.extraIter + '%smodel.star' % p
            myDict['%svolume' % p] = self.extraIter + p + 'class%(ref3d)03d.mrc:mrc'

        self._updateFilenamesDict(myDict)
    
    def _createIterTemplates(self):
        """ Setup the regex on how to find iterations. """
        self._iterTemplate = self._getFileName('data', iter=0).replace('000','???')
        # Iterations will be identify by _itXXX_ where XXX is the iteration number
        # and is restricted to only 3 digits.
        self._iterRegex = re.compile('_it(\d{3,3})_')
        
    #--------------------------- DEFINE param functions --------------------------------------------   
    def _defineParams(self, form):
        self.IS_3D = not self.IS_2D
        form.addSection(label='Input')
        # Some hidden variables to be used for conditions
        form.addHidden('isClassify', BooleanParam, default=self.IS_CLASSIFY)
        form.addHidden('is2D', BooleanParam, default=self.IS_2D)
        
        form.addParam('doContinue', BooleanParam, default=False,
                      label='Continue from a previous run?',
                      help='If you set to *Yes*, you should select a previous'
                      'run of type *%s* class and most of the input parameters'
                      'will be taken from it.' % self.getClassName())
        form.addParam('verboseLevel', EnumParam, default=1,
                      choices=['0 low','1 high'],
                      label='Verbose Level',
                      help='the higher the more verbose output')
        form.addParam('inputParticles', PointerParam, pointerClass='SetOfParticles',
                      condition='not doContinue',
                      important=True,
                      label="Input particles",  
                      help='Select the input images from the project.')   
        form.addParam('continueRun', PointerParam, pointerClass=self.getClassName(),
                      condition='doContinue', allowsNull=True,
                      label='Select previous run',
                      help='Select a previous run to continue from.')
        form.addParam('continueIter', StringParam, default='last',
                      condition='doContinue', 
                      label='Continue from iteration',
                      help='Select from which iteration do you want to continue.'
                           'if you use *last*, then the last iteration will be used.'
                           'otherwise, a valid iteration number should be provided.')        
        
        form.addParam('numberOfClasses', IntParam, default=3, 
                      condition='not doContinue and isClassify',
                      label='Number of classes:',
                      help='The number of classes (K) for a multi-reference refinement.'
                           'These classes will be made in an unsupervised manner from a single'
                           'reference by division of the data into random subsets during the'
                           'first iteration.')
        group = form.addGroup('Reference 3D map',
                              condition='not doContinue and not is2D')
        group.addParam('referenceVolume', PointerParam, pointerClass='Volume',
                       important=True,
                       label="Input volume",
                       condition='not doContinue and not is2D',
                       help='Initial reference 3D map, it should have the same '
                           'dimensions and the same pixel size as your input particles.')
        group.addParam('isMapAbsoluteGreyScale', BooleanParam, default=False,
                      label="Is initial 3D map on absolute greyscale?", 
                      help='The probabilities are based on squared differences, '
                           'so that the absolute grey scale is important. \n'
                           'Probabilities are calculated based on a Gaussian noise model,'
                           'which contains a squared difference term between the reference and the experimental image.' 
                           'This has a consequence that the reference needs to be on the same absolute intensity '
                           'grey-scale as the experimental images. RELION and XMIPP reconstruct maps at their absolute'
                           'intensity grey-scale. Other packages may perform internal normalisations of the reference' 
                           'density, which will result in incorrect grey-scales. Therefore: if the map was reconstructed'
                           'in RELION or in XMIPP, set this option to Yes, otherwise set it to No. If set to No, RELION '
                           'will use a (grey-scale invariant) cross-correlation criterion in the first iteration, and '
                           'prior to the second iteration the map will be filtered again using the initial low-pass filter.'
                           'This procedure is relatively quick and typically does not negatively affect the outcome of the'
                           'subsequent MAP refinement. Therefore, if in doubt it is recommended to set this option to No.')        
        
        self.addSymmetry(group)

        group.addParam('initialLowPassFilterA', FloatParam, default=60,
                      condition='not is2D',
                      label='Initial low-pass filter (A)',
                      help='It is recommended to strongly low-pass filter your initial reference map. '
                           'If it has not yet been low-pass filtered, it may be done internally using this option. ' 
                           'If set to 0, no low-pass filter will be applied to the initial reference(s).')
        
        form.addParam('paddingFactor', FloatParam, default=3,
                      condition='isClassify', expertLevel=LEVEL_EXPERT,
                      label='Padding factor',
                      help='The padding factor used for oversampling of the Fourier transform. The default is 3x padding, '
                           'which is combined with nearest-neighbour interpolation. However, for large 3D maps, storing the '
                           'entire 3x oversampled Fourier transform (as doubles) plus the real-space padded map in memory may ' 
                           'be too much. Therefore, for large maps or in cases of many 3D references, in order to fit into memory ' 
                           'one may need to use a smaller padding factor: e.g. 2, or (not recommended) 1. For padding factors smaller '
                           'than 3, (slower) linear interpolation will be used.\n'
                           'The approximate amount of memory (in Gb) required to store K maps of (size x size x size) voxels and a' 
                           'padding factor (pad) may be calculated as: K*2*8*(size*pad)^3/1024/1024/1024\n' 
                           '<Note>: also consider the use of threads if memory is an issue.')
        
        extraDefault = '' if self.IS_CLASSIFY else '--low_resol_join_halves 40 '
        form.addParam('extraParams', StringParam, default=extraDefault,
                      expertLevel=LEVEL_EXPERT,
                      label='Additional parameters',
                      help='')
               
        form.addSection(label='CTF')
        form.addParam('doCTF', BooleanParam, default=True,
                      label='Do CTF-amplitud correction?',
                      help='If set to Yes, CTFs will be corrected inside the MAP refinement. '
                           'The resulting algorithm intrinsically implements the optimal linear, ' 
                           'or Wiener filter. Note that input particles should contains CTF parameters.')
        form.addParam('hasReferenceCTFCorrected', BooleanParam, default=False,
                      condition='not is2D',
                      label='Has reference been CTF-corrected?',
                      help='Set this option to Yes if the reference map represents CTF-unaffected density, '
                           'e.g. it was created using Wiener filtering inside RELION or from a PDB. If set to No, ' 
                           'then in the first iteration, the Fourier transforms of the reference projections ' 
                           'are not multiplied by the CTFs.')        
        form.addParam('doCtfManualGroups', BooleanParam, default=False,
                      label='Do manual grouping ctfs?',
                      condition='not is2D',
                      help='Set this to Yes the CTFs will grouping manually.')
        form.addParam('numberOfGroups', IntParam, default=200,
                      label='Number of ctf groups', condition='doCtfManualGroups and not is2D',
                      help='Number of ctf groups that will be create')
        form.addParam('ignoreCTFUntilFirstPeak', BooleanParam, default=False,
                      expertLevel=LEVEL_ADVANCED,
                      label='Ignore CTFs until first peak?',
                      help='If set to Yes, then CTF-amplitude correction will only be performed from the first peak ' 
                           'of each CTF onward. This can be useful if the CTF model is inadequate at the lowest resolution. ' 
                           'Still, in general using higher amplitude contrast on the CTFs (e.g. 10-20%) often yields better results. '
                           'Therefore, this option is not generally recommended.')    
        
        form.addSection(label='Optimisation')
        if self.IS_CLASSIFY:
            form.addParam('numberOfIterations', IntParam, default=25,
                          label='Number of iterations',
                          help='Number of iterations to be performed. Note that the current implementation does NOT '
                               'comprise a convergence criterium. Therefore, the calculations will need to be stopped'
                               'by the user if further iterations do not yield improvements in resolution or classes.'
                               'If continue option is True, you going to do this number of new iterations (e.g. if'
                               '*Continue from iteration* is set 3 and this param is set 25, the final iteration of the'
                               'protocol will be the 28th.')
            form.addParam('regularisationParamT', IntParam, default=1,
                          label='Regularisation parameter T',
                          help='Bayes law strictly determines the relative weight between the contribution of the '
                               'experimental data and the prior. '
                               'However, in practice one may need to adjust this weight to put slightly more weight on the experimental '
                               'data to allow optimal results. Values greater than 1 for this regularisation parameter '
                               '(T in the JMB2011 paper) put more weight on the experimental data. Values around 2-4 '
                               'have been observed to be useful for 3D refinements, values of 1-2 for 2D refinements. '
                               'Too small values yield too-low resolution structures; too high values result in ' 
                               'over-estimated resolutions and overfitting.') 
        form.addParam('maskRadiusA', IntParam, default=200,
                      label='Particle mask RADIUS (A)',
                      help='The experimental images will be masked with a soft circular mask '
                           'with this <radius> (Note that in Relion GUI the diameter is used). '
                           'Make sure this radius is not set too small because that may mask '
                           'away part of the signal! If set to a value larger than the image '
                           'size no masking will be performed.\n\n'
                           'The same radius will also be used for a spherical mask of the '
                           'reference structures if no user-provided mask is specified.') 
        if self.IS_CLASSIFY:
            form.addParam('maskZero', EnumParam, default=0,
                          choices=['Yes, fill with zeros', 'No, fill with random noise'],
                          label='Mask particles with zeros?',
                          help='If set to <Yes>, then in the individual particles, the area outside a circle with the radius '
                               'of the particle will be set to zeros prior to taking the Fourier transform. '
                               'This will remove noise and therefore increase sensitivity in the alignment and classification. ' 
                               'However, it will also introduce correlations between the Fourier components that are not modelled. ' 
                               'When set to <No>, then the solvent area is filled with random noise, which prevents introducing '
                               'correlations.High-resolution refinements (e.g. in 3D auto-refine) tend to work better when filling ' 
                               'the solvent area with random noise, some classifications go better when using zeros.') 
        form.addParam('referenceMask', PointerParam, pointerClass='Mask',
                      label='Reference mask (optional)', allowsNull=True,
                      help='A volume mask containing a (soft) mask with the same dimensions ' 
                           'as the reference(s), and values between 0 and 1, with 1 being 100% protein '
                           'and 0 being 100% solvent. The reconstructed reference map will be multiplied '
                           'by this mask. If no mask is given, a soft spherical mask based on the <radius> '
                           'of the mask for the experimental images will be applied.\n\n'  
                           'In some cases, for example for non-empty icosahedral viruses, it is also useful ' 
                           'to use a second mask. Use <More options> and check <Solvent mask> parameter. ') 
        form.addParam('solventMask', PointerParam, pointerClass='Mask',
                      expertLevel=LEVEL_EXPERT, allowsNull=True,
                      label='Solvent mask (optional)',
                      help='For all white (value 1) pixels in this second mask the '
                           'corresponding pixels in the reconstructed map are set to the average value of '
                           'these pixels. Thereby, for example, the higher density inside the virion may be '
                           'set to a constant. Note that this second mask should have one-values inside the '
                           'virion and zero-values in the capsid and the solvent areas.') 
        
        # Change the Sampling section name depending if classify or refine 3D
        if self.IS_CLASSIFY:
            form.addSection('Sampling')
        else:
            form.addSection('Auto-Sampling')
        
        if self.IS_3D:
            form.addParam('angularSamplingDeg', EnumParam, default=2,
                          choices=ANGULAR_SAMPLING_LIST,
                          label='Angular sampling interval (deg)',
                          help='There are only a few discrete angular samplings possible because '
                           'we use the HealPix library to generate the sampling of the first '
                           'two Euler angles on the sphere. The samplings are approximate numbers ' 
                           'and vary slightly over the sphere.')
        else:
            form.addParam('inplaneAngularSamplingDeg', FloatParam, default=5,
                          label='Angular sampling interval (deg)',
                          help='There are only a few discrete angular samplings possible because '
                           'we use the HealPix library to generate the sampling of the first '
                           'two Euler angles on the sphere. The samplings are approximate numbers ' 
                           'and vary slightly over the sphere.')           
        form.addParam('offsetSearchRangePix', FloatParam, default=5,
                      condition='isClassify or not doContinue',
                      label='Offset search range (pix)',
                      help='Probabilities will be calculated only for translations in a circle '
                           'with this radius (in pixels). The center of this circle changes at '
                           'every iteration and is placed at the optimal translation for each '
                           'image in the previous iteration.')
        form.addParam('offsetSearchStepPix', FloatParam, default=1.0,
                      condition='isClassify or not doContinue',
                      label='Offset search step (pix)',
                      help='Translations will be sampled with this step-size (in pixels). '
                           'Translational sampling is also done using the adaptive approach. '
                           'Therefore, if adaptive=1, the translations will first be evaluated'
                           'on a 2x coarser grid.')
        if self.IS_3D: 
            if self.IS_CLASSIFY:
                form.addParam('localAngularSearch', BooleanParam, default=False,
                              condition='not is2D',
                              label='Perform local angular search?',
                              help='If set to Yes, then rather than performing exhaustive angular searches, '
                                   'local searches within the range given below will be performed. A prior '
                                   'Gaussian distribution centered at the optimal orientation in the previous '
                                   'iteration and with a stddev of 1/3 of the range given below will be enforced.')
                form.addParam('localAngularSearchRange', FloatParam, default=5.0,
                              condition='localAngularSearch',
                              label='Local angular search range',
                              help='Local angular searches will be performed within +/- \n'
                                   'the given amount (in degrees) from the optimal orientation\n'
                                   'in the previous iteration. A Gaussian prior (also see \n'
                                   'previous option) will be applied, so that orientations \n'
                                   'closer to the optimal orientation in the previous iteration \n'
                                   'will get higher weights than those further away.')
                
                
            else:
                form.addParam('localSearchAutoSamplingDeg', EnumParam, default=4,
                              choices=ANGULAR_SAMPLING_LIST,
                              label='Local search from auto-sampling (deg)',
                              help='In the automated procedure to increase the angular samplings,\n'
                                   'local angular searches of -6/+6 times the sampling rate will\n'
                                   'be used from this angular sampling rate onwards.')
            
                form.addSection("Movies")
                form.addParam('realignMovieFrames', BooleanParam, default=False,
                              label='Realign movie frames?',
                              help='If set to Yes, then running averages of the individual frames of recorded movies will be aligned as independent particles.')
                
                group = form.addGroup('Movie frames alignment',
                                      condition='realignMovieFrames and doContinue')
                group.addParam('inputMovieParticles', PointerParam, pointerClass='SetOfMovieParticles',
                               allowsNull=True, important=True,
                               label='Input movie particles')
                group.addParam('movieAvgWindow', FloatParam, default=5,
                              label='Running average window',
                              help='The individual movie frames will be averaged using a running average window with the specified width. Use an odd number. The optimal value will depend on the SNR in the individual movie frames. For ribosomes, we used a value of 5, where each movie frame integrated approximately 1 electron per squared Angstrom.')
                group.addParam('movieStdTrans', FloatParam, default=1,
                              label='Stddev on the translations (px)',
                              help='A Gaussian prior with the specified standard deviation will be centered at the rotations determined for the corresponding particle where all movie-frames were averaged. For ribosomes, we used a value of 2 pixels. ')
                group.addParam('movieIncludeRotSearch', BooleanParam, default=False,
                              label='Also include rotational searches?',
                              help='If set to Yes, then running averages of the individual frames of recorded movies will also be aligned rotationally. \n'
                                   'If one wants to perform particle polishing, then rotational alignments of the movie frames is NOT necessary and will only take more computing time.')
                group.addParam('movieStdRot', FloatParam, default=1,
                              condition='movieIncludeRotSearch',
                              label='Stddev on the rotations (deg)',
                              help='A Gaussian prior with the specified standard deviation will be centered at the rotations determined for the corresponding particle where all movie-frames were averaged. For ribosomes, we used a value of 1 degree')

        form.addParallelSection(threads=1, mpi=3)
    
    def addSymmetry(self, container):
        container.addParam('symmetryGroup', StringParam, default='c1',
                      label="Symmetry", 
                      help='If the molecule is asymmetric, set Symmetry group to C1. Note their are multiple possibilities for icosahedral symmetry: \n'
                         '* I1: No-Crowther 222 (standard in Heymann, Chagoyen & Belnap, JSB, 151 (2005) 196-207)\n'
                         '* I2: Crowther 222                                                                     \n'
                         '* I3: 52-setting (as used in SPIDER?)                                                  \n'
                         '* I4: A different 52 setting                                                           \n'
                         'The command *relion_refine --sym D2 --print_symmetry_ops* prints a list of all symmetry operators for symmetry group D2. RELION uses XMIPP\'s libraries for symmetry operations. Therefore, look at the XMIPP Wiki for more details:  http://xmipp.cnb.csic.es/twiki/bin/view/Xmipp/WebHome?topic=Symmetry')

    #--------------------------- INSERT steps functions --------------------------------------------  
    def _insertAllSteps(self): 
        self._initialize()
        self._insertFunctionStep('convertInputStep')
        self._insertRelionStep()
        self._insertFunctionStep('createOutputStep')
    
    def _insertRelionStep(self):
        """ Prepare the command line arguments before calling Relion. """
        # Join in a single line all key, value pairs of the args dict    
        args = {}
        
        if self.doContinue:
            self._setContinueArgs(args)
        else:
            self._setNormalArgs(args)
        params = ' '.join(['%s %s' % (k, str(v)) for k, v in args.iteritems()])
        
        if self.extraParams.hasValue():
            params += ' ' + self.extraParams.get()

        self._insertFunctionStep('runRelionStep', params)
        
    def _setNormalArgs(self, args):
        args.update({'--i': self._getFileName('input_star'),
                     '--particle_diameter': self.maskRadiusA.get() * 2.0,
                     '--angpix': self._getInputParticles().getSamplingRate(),
                    })
        self._setMaskArgs(args)
        self._setCTFArgs(args)
        
        if self.IS_CLASSIFY:
            if self.maskZero == MASK_FILL_ZERO:
                args['--zero_mask'] = ''                
            args['--K'] = self.numberOfClasses.get()
        
        if self.IS_3D:
            args['--ref'] = self.referenceVolume.get().getFileName()
            if not self.isMapAbsoluteGreyScale:
                args['--firstiter_cc']=''
            args['--ini_high'] = self.initialLowPassFilterA.get()
            args['--sym'] = self.symmetryGroup.get()
            
        self._setBasicArgs(args)
        
    def _setContinueArgs(self, args):
        continueRun = self.continueRun.get()
        continueRun._initialize()
        
        if self.continueIter.get() == 'last':
            continueIter = continueRun._lastIter()
        else:
            continueIter = int(self.continueIter.get())
        
        if self.IS_CLASSIFY:
            itersToRun = continueIter + self.numberOfIterations.get()
            self.numberOfIterations.set(itersToRun)
            self.copyAttributes(continueRun, 'regularisationParamT')
        self._setBasicArgs(args)
        
        args['--continue'] = continueRun._getFileName('optimiser', iter=continueIter)
    
    def _setBasicArgs(self, args):
        """ Return a dictionary with basic arguments. """
        args.update({'--flatten_solvent': '',
                     '--norm': '',
                     '--scale': '',
                     '--o': self._getExtraPath('relion'),
                     '--oversampling': '1'
                    })

        args['--verb'] = self.verboseLevel.get()
        if self.IS_CLASSIFY:
            args['--tau2_fudge'] = self.regularisationParamT.get()
            args['--iter'] = self.numberOfIterations.get()
            
        self._setSamplingArgs(args)
        args['--offset_range'] = self.offsetSearchRangePix.get()
        args['--offset_step']  = self.offsetSearchStepPix.get() * 2
                        
    def _setCTFArgs(self, args):        
        # CTF stuff
        if self.doCTF:
            args['--ctf'] = ''
        
        # this only can be true if is 3D.
        if self.hasReferenceCTFCorrected:
            args['--ctf_corrected_ref'] = ''
            
        if self.haveDataPhaseFlipped:
            args['--ctf_phase_flipped'] = ''
            
        if self.ignoreCTFUntilFirstPeak:
            args['--ctf_intact_first_peak'] = ''
            
    def _setMaskArgs(self, args):
        if self.referenceMask.hasValue():
            args['--solvent_mask'] = self.referenceMask.get().getFileName() #FIXE: CHANGE BY LOCATION
            
        if self.solventMask.hasValue():
            args['--solvent_mask2'] = self.solventMask.get().getFileName() #FIXME: CHANGE BY LOCATION
 
   
    #--------------------------- STEPS functions --------------------------------------------       
    def convertInputStep(self):
        """ Create the input file in STAR format as expected by Relion.
        If the input particles comes from Relion, just link the file. 
        """
        imgSet = self._getInputParticles()
        imgStar = self._getFileName('input_star')
        filesMapping = convertBinaryFiles(imgSet,self._getTmpPath())

        self.info("Converting set from '%s' into '%s'" %
                           (imgSet.getFileName(), imgStar))
        from convert import writeSetOfParticles
        # Pass stack file as None to avoid write the images files
        writeSetOfParticles(imgSet, imgStar, filesMapping)
        
        if self.doCtfManualGroups:
            self._splitInCTFGroups(imgStar)
        
        if not self.IS_CLASSIFY:
            if self.realignMovieFrames:
                movieParticleSet = self.inputMovieParticles.get()
                auxMovieParticles = self._createSetOfMovieParticles(suffix='tmp')
                auxMovieParticles.copyInfo(movieParticleSet)
                # Discard the movie particles that are not present in the refinement set
                for movieParticle in movieParticleSet:
                    particle = imgSet[movieParticle._xmipp_particleId.get()]
                    if particle is not None:
                        auxMovieParticles.append(movieParticle)
                        
                writeSetOfParticles(auxMovieParticles,
                                    self._getFileName('movie_particles'), None, originalSet=imgSet)
                cleanPath(auxMovieParticles.getFileName())
        
    def runRelionStep(self, params):
        """ Execute the relion steps with the give params. """
        params += ' --j %d' % self.numberOfThreads.get()
        self.runJob(self._getProgram(), params)
    
    def createOutputStep(self):
        pass # should be implemented in subclasses
    
    #--------------------------- INFO functions -------------------------------------------- 
    def _validate(self):
        errors = []
        if self.doContinue:
            errors += self._validateContinue()
        else:
            if self._getInputParticles().isOddX():
                errors.append("Relion only works with even values for the image dimensions!")
                
            errors += self._validateNormal()
        return errors
    
    def _validateNormal(self):
        """ Should be overriden in subclasses to 
        return summary message for NORMAL EXECUTION. 
        """
        return []
    
    def _validateContinue(self):
        """ Should be overriden in subclasses to
        return summary messages for CONTINUE EXECUTION.
        """
        return []
    
    def _citations(self):
        cites = []
        return cites
    
    def _summary(self):
        if self.doContinue:
            return self._summaryContinue()
        return self._summaryNormal()

    def _summaryNormal(self):
        """ Should be overriden in subclasses to 
        return summary message for NORMAL EXECUTION. 
        """
        return []
    
    def _summaryContinue(self):
        """ Should be overriden in subclasses to
        return summary messages for CONTINUE EXECUTION.
        """
        return []
    
    #--------------------------- UTILS functions --------------------------------------------
    def _getProgram(self, program='relion_refine'):
        """ Get the program name depending on the MPI use or not. """
        if self.numberOfMpi > 1:
            program += '_mpi'
        return program
    
    def _getInputParticles(self):
        if self.doContinue:
            return self.continueRun.get().inputParticles.get()
        else:
            return self.inputParticles.get()
    
    def _getIterNumber(self, index):
        """ Return the list of iteration files, give the iterTemplate. """
        result = None
        files = sorted(glob(self._iterTemplate))
        if files:
            f = files[index]
            s = self._iterRegex.search(f)
            if s:
                result = int(s.group(1)) # group 1 is 3 digits iteration number
        return result
        
    def _lastIter(self):
        return self._getIterNumber(-1)

    def _firstIter(self):
        return self._getIterNumber(0) or 1
    
    def _getIterClasses(self, it):
        """ Return the .star file with the classes for this iteration.
        If the file doesn't exists, it will be created. 
        """
        data_star = self._getFileName('data', iter=it)
        data_classes = self._getFileName('classes_scipion', iter=it)
        
        if not exists(data_classes):
            createClassesFromImages(self._getInputParticles(), data_star, data_classes, 
                                    self.OUTPUT_TYPE, self.CLASS_LABEL, self.ClassFnTemplate, it)
        return data_classes
    
    def _getIterSortedData(self, it):
        """ Sort the it??.data.star file by the maximum likelihood. """
        data_sorted = self._getFileName('data_sorted_xmipp', iter=it)
        
        if not exists(data_sorted):
            data = self._getFileName('data', iter=it)
            # TODO: convert the sorted data directly to sqlite
            # and just displayed sorted by LL
            from convert import sortImagesByLL
            sortImagesByLL(data, data_sorted)
        
        return data_sorted
    
    def _getIterAngularDist(self, it):
        """ Return the .star file with the classes angular distribution
        for this iteration. If the file not exists, it will be written.
        """
        data_angularDist = self._getFileName('angularDist_xmipp', iter=it)
        
        if not exists(data_angularDist):
            self._writeIterAngularDist(it)
 
        return data_angularDist
    
    def _writeIterAngularDist(self, it):
        """ Write the angular distribution. Should be overriden in subclasses. """
        addRelionLabels()
        
        data_star = self._getFileName('data', iter=it)
        md = xmipp.MetaData(data_star)
        data_angularDist = self._getFileName('angularDist_xmipp', iter=it)
        
        refsList = range(1, self.numberOfClasses.get()+1) 
        print "refsList: ", refsList
        for ref3d in refsList:
            for prefix in self.PREFIXES:
                mdGroup = xmipp.MetaData()
                mdGroup.importObjects(md, xmipp.MDValueEQ(xmipp.MDL_REF, ref3d))
                mdDist = xmipp.MetaData()
                mdDist.aggregateMdGroupBy(mdGroup, xmipp.AGGR_COUNT, 
                                          [xmipp.MDL_ANGLE_ROT, xmipp.MDL_ANGLE_TILT], 
                                          xmipp.MDL_ANGLE_ROT, xmipp.MDL_WEIGHT)
                mdDist.setValueCol(xmipp.MDL_ANGLE_PSI, 0.0)
                blockName = '%sclass%06d_angularDist@' % (prefix, ref3d)
                print "Writing angular distribution to: ", blockName + data_angularDist
                mdDist.write(blockName + data_angularDist, xmipp.MD_APPEND)  
    
    def _splitInCTFGroups(self, imgStar):
        """ Add a new colunm in the image star to separate the particles into ctf groups """
        addRelionLabels(replace=True)
        
        groups = self.numberOfGroups.get()
        md = xmipp.MetaData(imgStar)
        defocus = [md.getValue(xmipp.MDL_CTF_DEFOCUSU, objId) for objId in md]
        
        minDef = min(defocus)
        maxDef = max(defocus)
        
        increment = (maxDef - minDef) / groups
        counter = 1
        part = 1
        md.sort(xmipp.MDL_CTF_DEFOCUSU)
        
        for objId in md:
            partDef = md.getValue(xmipp.MDL_CTF_DEFOCUSU, objId)
            currDef = minDef + increment
            
            if partDef <= currDef:
                part = part + 1
                md.setValue(xmipp.MDL_SERIE, "ctfgroup_%05d" % counter, objId)
            else:
                if part < 100:
                    increment = md.getValue(xmipp.MDL_CTF_DEFOCUSU, objId) - minDef
                    part = part + 1
                    md.setValue(xmipp.MDL_SERIE, "ctfgroup_%05d" % counter, objId)
                else:
                    part = 1
                    minDef = md.getValue(xmipp.MDL_CTF_DEFOCUSU, objId)
                    counter = counter + 1
                    increment = (maxDef - minDef) / (groups - counter)
                    md.setValue(xmipp.MDL_SERIE, "ctfgroup_%05d" % counter, objId)
        md.write(imgStar)
        restoreXmippLabels()
    
    
