"""The freesurfer module provides basic functions for interfacing with freesurfer tools.

Currently these tools are supported:

     * Dicom2Nifti: using mri_convert
     * Resample: using mri_convert
     
Examples
--------
See the docstrings for the individual classes for 'working' examples.

"""
__docformat__ = 'restructuredtext'

import os
from glob import glob

import numpy as np

from nipype.interfaces.base import Bunch, CommandLine
from nipype.interfaces.fsl import FSLCommand
from nipype.utils.docparse import get_doc
from nipype.utils.filemanip import fname_presuffix, filename_to_list
from nipype.interfaces.io import FreeSurferSource

def freesurferversion():
    """Check for freesurfer version on system

    Parameters
    ----------
    
    None

    Returns
    -------
    
    version : string
       version number as string 
       or None if freesurfer version not found

    """
    # find which freesurfer is being used....and get version from
    # /path/to/freesurfer/
    fs_home = os.getenv('FREESURFER_HOME')
    if fs_home is None:
        return fs_home
    versionfile = os.path.join(fs_home,'build-stamp.txt')
    if not os.path.exists(versionfile):
        return None
    fid = open(versionfile,'rt')
    version = fid.readline()
    fid.close()
    return version.split('-v')[1].strip('\n')

def fssubjectsdir(subjects_dir=None):
    """Check and or set the global SUBJECTS_DIR
    
    Parameters
    ----------
    
    subjects_dir :  string
        The system defined subjects directory

    Returns
    -------
    
    subject_dir : string
        Represents the current environment setting of SUBJECTS_DIR

    """
    if subjects_dir is not None:
        # set environment setting
        os.environ['SUBJECTS_DIR'] = os.path.abspath(subjects_dir)
    subjects_dir = os.getenv('SUBJECTS_DIR')
    return subjects_dir

class FSCommandLine(CommandLine):

    def __init__(self):
        super(FSCommandLine,self).__init__()
        self._cmdline = ''
        
    @property
    def cmdline(self):
        # This handles args like ['bet', '-f 0.2'] without crashing
        return self._cmdline

    def run(self, **inputs):
        """Execute the command.
        
        Returns
        -------
        results : InterfaceResult
            A `InterfaceResult` object with a copy of self in `interface`

        """
        # This is expected to populate `_cmdline` for _runner to work
        self._compile_command()
        result = self._runner(cwd=os.getcwd())
        if result.runtime.returncode == 0:
            result.outputs = self.aggregate_outputs()
        return result

class DicomDirInfo(FSLCommand):
    """uses mri_parse_sdcmdir to get information from dicom
    directories
    
    Parameters
    ----------
    To see optional arguments
    DicomDirInfo().inputs_help()


    Examples
    --------

    >>> from nipype.interfaces import freesurfer
    >>> dcminfo = freesurfer.DicomDirInfo()
    >>> dcminfo.inputs.dicomdir = 'dicomdir'
    >>> dcminfo.inputs.outfile = 'dicominfo.txt'
    >>> dcminfo.inputs.sortbyrun = True
    >>> dcminfo.inputs.summarize = True
    >>> dcminfo.cmdline
    'mri_parse_sdcmdir --d dicomdir --o dicominfo.txt --sortbyrun --summarize'
    
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_parse_sdcmdir'

    def inputs_help(self):
        """Print command line documentation for mri_parse_sdcmdir."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'dicomdir':       '--d %s',
        'outfile':        '--o %s',
        'sortbyrun':      '--sortbyrun',
        'summarize':      '--summarize',  
        'flags':           '%s'}

    def _get_outfile_name(self):
        return os.path.join(os.getcwd(),'dicominfo.txt')
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(DicomDirInfo, self)._parse_inputs()
        # Add outfile to the args if not specified
        if not self.inputs.outfile:
            allargs.extend(['--o', self._get_outfile_name()])
        return allargs
    
    def run(self, dicomdir=None, cwd=None, **inputs):
        """Execute the command.
        """
        if dicomdir:
            self.inputs.dicomdir = dicomdir
        if not self.inputs.dicomdir:
            raise AttributeError('DicomDirInfo requires a dicomdir input')
        self.inputs.update(**inputs)
        if cwd:
            os.chdir(cwd)
        return super(DicomDirInfo, self).run()

    def outputs(self):
        """
        dicominfo: filename
            file containing dicom information
        """
        return Bunch(dicominfo=None)

    def aggregate_outputs(self):
        outputs = self.outputs()
        if not self.inputs.outfile:
            outfile = self._get_outfile_name()
        if isinstance(self.inputs.outfile,str):
            outfile = self.inputs.outfile
        outputs.dicominfo = glob(outfile)[0]
        return outputs

class DicomConvert(FSCommandLine):
    """use fs mri_convert to convert dicom files

    Parameters
    ----------

    To see optional arguments
    DicomConvert().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces import freesurfer
    >>> cvt = freesurfer.DicomConvert()
    >>> cvt.inputs.dicomdir = '/incoming/TrioTim-35115-2009-1900-123456/'
    >>> cvt.inputs.file_mapping = [('nifti','*.nii'),('info','dicom*.txt'),('dti','*dti.bv*')]
    >>> cvt.run()

   """
    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_convert'


    def inputs_help(self):
        """
        Parameters
        ----------
        
        (all default to None and are unset)
        
        dicomdir : /path/to/dicomfiles
            directory from which to convert dicom files
        base_output_dir : /path/to/outputdir
            base output directory in which subject specific
            directories are created to store the nifti files
        subject_dir_template : string
            template for subject directory name
            Default:'S.%04d'
        subject_id : string or int
            subject identifier to insert into template. For the
            example above template subject_identifier should be an
            integer. Default: id from Dicom file name 
        file_mapping : list of tuples
            defines the output fields of interface and the kind of
            file type they store
            Example:  [('niftifiles','*.nii'),('dtiinfo','*mghdti.bv*')]
        out_type : string
            defines the type of output file produced.
            possible options nii, nii.gz, mgz (default: nii)
        dicominfo : file
            File containing summary information from mri_parse_sdcmdir
        seq_list : list of strings
            list of pulse sequence names to be converted.
        ignore_single_slice : boolean
            ignores volumes containing a single slice. dicominfo needs to be
            available. 
        flags = unsupported flags, use at your own risk

        """
        print self.inputs_help.__doc__

    def _populate_inputs(self):
        self.inputs = Bunch(dicomdir=None,
                            base_output_dir=None,
                            subject_dir_template=None,
                            subject_id=None,
                            file_mapping=None,
                            out_type='nii',
                            dicominfo=None,
                            seq_list=None,
                            ignore_single_slice=None,
                            flags=None)

    def _parseinputs(self):
        """validate fsl bet options
        if set to None ignore
        """
        out_inputs = {'dicomfiles':None}
        inputs = {}
        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v]
        for opt in inputs:
            if opt == 'dicomdir':
                out_inputs['dicomfiles'] = glob(os.path.abspath(os.path.join(inputs[opt],'*-1.dcm')))
                continue
            if opt in ['base_output_dir', 'subject_dir_template', 'subject_id', \
                           'file_mapping', 'out_type', 'dicominfo', 'seq_list', \
                           'flags']:
                continue
            print 'option %s not supported'%(opt)
        
        return out_inputs

    def _get_outdir(self):
        """returns output directory"""
        valid_inputs = self._parseinputs()
        subjid = self.inputs.subject_id
        if not subjid:
            path,fname = os.path.split(valid_inputs['dicomfiles'][0])
            subjid = fname.split('-')[0]
        if self.inputs.subject_dir_template:
            subjid  = self.inputs.subject_dir_template % subjid
        basedir=self.inputs.base_output_dir
        if not basedir:
            basedir = os.path.abspath('.')
        outdir = os.path.abspath(os.path.join(basedir,subjid))
        return outdir

    def _get_runs(self):
        """Returns list of dicom series that should be converted.

        Requires a dicom info summary file generated by ``DicomDirInfo``

        """
        seq = np.genfromtxt(self.inputs.dicominfo,dtype=object)
        runs = []
        for s in seq:
            if self.inputs.seq_list:
                if self.inputs.ignore_single_slice:
                    if (int(s[8]) > 1) and any([s[12].startswith(sn) for sn in self.inputs.seq_list]):
                        runs.append(int(s[2]))
                else:
                    if any([s[12].startswith(sn) for sn in self.inputs.seq_list]):
                        runs.append(int(s[2]))
            else:
                runs.append(int(s[2]))
        return runs

    def _get_filelist(self, outdir):
        """Returns list of files to be converted"""
        valid_inputs = self._parseinputs()
        filemap = {}
        for f in valid_inputs['dicomfiles']:
            head,fname = os.path.split(f)
            fname,ext = os.path.splitext(fname)
            fileparts = fname.split('-')
            runno = int(fileparts[1])
            outfile = os.path.join(outdir,'.'.join(('%s-%02d'% (fileparts[0],
                                                                runno),
                                                    self.inputs.out_type)))
            filemap[runno] = (f,outfile)
        if self.inputs.dicominfo:
            files = [filemap[r] for r in self._get_runs()]
        else:
            files = [filemap[r] for r in filemap.keys()]
        return files

    def _compile_command(self):
        """validates fsl options and generates command line argument"""
        outdir = self._get_outdir()
        cmd = []
        if not os.path.exists(outdir):
            cmdstr = 'mkdir %s' % outdir
            cmd.extend([cmdstr])
        cmdstr = 'dcmdir-info-mgh %s > %s' % (self.inputs.dicomdir,
                                              os.path.join(outdir,
                                                           'shortinfo.txt'))
        cmd.extend([cmdstr])
        files = self._get_filelist(outdir)
        for infile,outfile in files:
            if not os.path.exists(outfile):
                single_cmd = '%s %s %s' % (self.cmd, infile,
                                           os.path.join(outdir, outfile))
                cmd.extend([single_cmd])
        self._cmdline =  '; '.join(cmd)
        return self._cmdline

    def outputs(self):
        return Bunch()

    def aggregate_outputs(self):
        outdir = self._get_outdir()
        outputs = self.outputs()
        if self.inputs.file_mapping:
            for field,template in self.inputs.file_mapping:
                setattr(outputs, field, sorted(glob(os.path.join(outdir,
                                                                 template))))
        return outputs

class Dicom2Nifti(FSCommandLine):
    """use fs mri_convert to convert dicom files to nifti-1 files

    Parameters
    ----------

    To see optional arguments
    Dicom2Nifti().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces import freesurfer
    >>> cvt = freesurfer.Dicom2Nifti()
    >>> cvt.inputs.dicomdir = '/software/data/STUT/RAWDATA/TrioTim-35115-20090428-081900-234000/'
    >>> cvt.inputs.file_mapping = [('nifti','*.nii'),('info','dicom*.txt'),('dti','*dti.bv*')]
    >>> #out = cvt.run() # commented out as above directories are not installed

   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_convert'


    def inputs_help(self):
        """
        Parameters
        ----------
        
        (all default to None and are unset)
        
        dicomdir : /path/to/dicomfiles
            directory from which to convert dicom files
        base_output_dir : /path/to/outputdir
            base output directory in which subject specific
            directories are created to store the nifti files
        subject_dir_template : string
            template for subject directory name
            Default:'S.%04d'
        subject_id : string or int
            subject identifier to insert into template. For the
            example above template subject_identifier should be an
            integer. Default: id from Dicom file name 
        file_mapping : list of tuples
            defines the output fields of interface and the kind of
            file type they store
            Example:  [('niftifiles','*.nii'),('dtiinfo','*mghdti.bv*')]
        out_type : string
            defines the type of output file produced.
            possible options nii, nii.gz, mgz (default: nii)
        flags = unsupported flags, use at your own risk

        """
        print self.inputs_help.__doc__

    def _populate_inputs(self):
        self.inputs = Bunch(dicomdir=None,
                            base_output_dir=None,
                            subject_dir_template=None,
                            subject_id=None,
                            file_mapping=None,
                            out_type='nii',
                            flags=None)

    def _parseinputs(self):
        """validate fsl bet options
        if set to None ignore
        """
        out_inputs = {'dicomfiles':None}
        inputs = {}
        [inputs.update({k:v}) for k, v in self.inputs.iteritems() if v is not None ]
        for opt in inputs:
            if opt == 'dicomdir':
                out_inputs['dicomfiles'] = glob(os.path.abspath(os.path.join(inputs[opt],'*-1.dcm')))
                continue
            if opt == 'base_output_dir':
                continue
            if opt == 'subject_dir_template':
                continue
            if opt == 'subject_id':
                continue
            if opt == 'file_mapping':
                continue
            if opt == 'out_type':
                continue
            if opt == 'flags':
                continue
            print 'option %s not supported'%(opt)
        
        return out_inputs

    def _get_outdir(self):
        """returns output directory"""
        valid_inputs = self._parseinputs()
        subjid = self.inputs.subject_id
        if not subjid:
            path,fname = os.path.split(valid_inputs['dicomfiles'][0])
            subjid = fname.split('-')[0]
        if self.inputs.subject_dir_template:
            subjid  = self.inputs.subject_dir_template % subjid
        basedir=self.inputs.base_output_dir
        if not basedir:
            basedir = os.path.abspath('.')
        outdir = os.path.abspath(os.path.join(basedir,subjid))
        return outdir
    
    def _compile_command(self):
        """validates fsl options and generates command line argument"""
        valid_inputs = self._parseinputs()
        outdir = self._get_outdir()
        cmd = []
        if not os.path.exists(outdir):
            cmdstr = 'mkdir %s;' % outdir
            cmd.extend([cmdstr])
        cmdstr = 'dcmdir-info-mgh %s > %s;' % (self.inputs.dicomdir,os.path.join(outdir,'dicominfo.txt'))
        cmd.extend([cmdstr])
        for f in valid_inputs['dicomfiles']:
            head,fname = os.path.split(f)
            fname,ext  = os.path.splitext(fname)
            outfile = os.path.join(outdir,'.'.join((fname,self.inputs.out_type)))
            if not os.path.exists(outfile):
                single_cmd = '%s %s %s;' % (self.cmd, f, outfile)
                cmd.extend([single_cmd])
        self._cmdline =  ' '.join(cmd)
        return self._cmdline

    def outputs(self):
        return Bunch()

    def aggregate_outputs(self):
        outdir = self._get_outdir()
        outputs = self.outputs()
        if self.inputs.file_mapping:
            for field,template in self.inputs.file_mapping:
                setattr(outputs, field, sorted(glob(os.path.join(outdir,
                                                                 template))))
        return outputs

class Resample(FSLCommand):
    """Use FreeSurfer mri_convert to up or down-sample image files

    Parameters
    ----------
    To see optional arguments
    Resample().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces import freesurfer
    >>> resampler = freesurfer.Resample()
    >>> resampler.inputs.infile = 'infile.nii'
    >>> resampler.inputs.voxel_size = [2.1, 2.1, 2.1]
    >>> resampler.cmdline
    'mri_convert -i infile.nii -vs 2.10 2.10 2.10 -o infile_resample.nii'
    
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_convert'

    def inputs_help(self):
        """Print command line documentation for bbregister."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'infile':         '-i %s',
        'outfile':        '-o %s',
        'voxel_size':     '-vs %.2f %.2f %.2f', 
        'flags':           '%s'}
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(Resample, self)._parse_inputs()

        # Add outfile to the args if not specified
        if self.inputs.outfile is None:
            allargs.extend(['-o', fname_presuffix(self.inputs.infile,
                                                   suffix='_resample')])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(Resample, self).run()

    def outputs(self):
        """
        outfile: filename
            Smoothed input volume
        """
        return Bunch(outfile=None)

    def aggregate_outputs(self):
        outputs = self.outputs()
        if self.inputs.outfile is None:
            outfile = glob(fname_presuffix(self.inputs.infile,
                                           suffix='_resample'))
            outputs.outfile = outfile[0]
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            outputs.outfile = outfile[0]
        return outputs

class ReconAll(FSLCommand):
    """Use FreeSurfer recon-all to generate surfaces and parcellations of
    structural data from an anatomical image of a subject.

    Parameters
    ----------

    To see optional arguments
    ReconAll().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces import freesurfer
    >>> reconall = freesurfer.ReconAll()
    >>> reconall.inputs.subject_id = 'foo'
    >>> reconall.inputs.all  = True
    >>> reconall.inputs.subjects_dir = '.'
    >>> reconall.inputs.T1file = 'structfile.nii'
    >>> reconall.cmdline
    'recon-all --i structfile.nii --all -subjid foo -sd .'
    
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'recon-all'

    def inputs_help(self):
        """Print command line documentation for bbregister."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'subject_id':         '-subjid %s',
        'all':                '--all',
        'T1file':             '--i %s',
        'hemi':               '-hemi %s',
        'subjects_dir':       '-sd %s',
        'flags':              '%s'}
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(ReconAll, self).run()

    def outputs(self):
        """
        See io.FreeSurferSource.outputs for the list of outputs returned
        """
        return FreeSurferSource().outputs()

    def aggregate_outputs(self):
        return FreeSurferSource(subject_id=self.inputs.subject_id,
                                subjects_dir=self.inputs.subjects_dir).aggregate_outputs()

class BBRegister(FSLCommand):
    """Use FreeSurfer bbregister to register a volume two a surface mesh

    This program performs within-subject, cross-modal registration using a
    boundary-based cost function. The registration is constrained to be 6
    DOF (rigid). It is required that you have an anatomical scan of the
    subject that has been analyzed in freesurfer.

    Parameters
    ----------

    To see optional arguments
    BBRegister().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces.freesurfer import BBRegister
    >>> bbreg = BBRegister(subject_id='me', sourcefile='foo.nii', init_header=True, t2_contrast=True)
    >>> bbreg.cmdline
    'bbregister --init-header --mov foo.nii --s me --t2 --reg foo_bbreg_me.dat'

   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'bbregister'


    def inputs_help(self):
        """Print command line documentation for bbregister."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'subject_id':         '--s %s',
        'sourcefile':         '--mov %s',
        'init_spm':           '--init-spm',
        'init_fsl':           '--init-fsl',
        'init_header':        '--init-header',
        'init_reg':           '--init-reg %s',
        't1_contrast':        '--t1',
        't2_contrast':        '--t2',
        'outregfile':         '--reg %s',
        'outfile':            '--o %s',
        'flags':              '%s'}
    
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='sourcefile',copy=False)]
        return info
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(BBRegister, self)._parse_inputs(skip=('outfile'))

        # Add infile and outfile to the args if they are specified
        if self.inputs.outregfile is None and self.inputs.sourcefile is not None:
            allargs.extend(['--reg',fname_presuffix(self.inputs.sourcefile,
                                                       suffix='_bbreg_%s.dat'%self.inputs.subject_id,
                                                       use_ext=False)])
        if self.inputs.outfile is True:
            allargs.extend(['--o',fname_presuffix(self.inputs.sourcefile,suffix='_bbreg')])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(BBRegister, self).run()

    def outputs(self):
        """
        outregfile: filename
            Output registration file
        outfile: filename
            Registered and resampled source file
        """
        outputs = Bunch(outregfile=None,
                        outfile=None)
        return outputs

    def aggregate_outputs(self):
        outputs = self.outputs()
        if self.inputs.outregfile is None:
            outregfile = fname_presuffix(self.inputs.sourcefile,
                                         suffix='_bbreg_%s.dat'%self.inputs.subject_id,
                                         use_ext=False)
        else:
            outregfile = self.inputs.outregfile
        assert len(glob(outregfile))==1, "No output registration file %s created"%outregfile
        outputs.outregfile = outregfile
        if self.inputs.outfile is True:
            outfile = glob(fname_presuffix(self.inputs.sourcefile,suffix='_bbreg'))
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        return outputs

class ApplyVolTransform(FSLCommand):
    """Use FreeSurfer mri_vol2vol to apply a transform.

    Parameters
    ----------
    To see optional arguments
    ApplyVolTransform().inputs_help()

    Examples
    --------
    >>> from nipype.interfaces.freesurfer import ApplyVolTransform
    >>> applyreg = ApplyVolTransform(tkreg='me.dat', sourcefile='foo.nii', fstarg=True)
    >>> applyreg.cmdline
    'mri_vol2vol --fstarg --mov foo.nii --reg me.dat --o foo_warped.nii'

    """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_vol2vol'

    def inputs_help(self):
        """Print command line documentation for mri_vol2vol."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'sourcefile':         '--mov %s',
        'targfile':           '--targ %s',
        'outfile':            '--o %s',
        'fstarg':             '--fstarg',
        'tkreg':              '--reg %s',
        'fslreg':             '--fsl %s',
        'xfmreg':             '--xfm %s',
        'noresample':         '--no-resample',
        'inverse':            '--inv', 
        'flags':              '%s'}
    
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='sourcefile', copy=False)]
        return info
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(ApplyVolTransform, self)._parse_inputs()

        # Add outfile to the args if not specified
        if self.inputs.outfile is None:
            allargs.extend(['--o', fname_presuffix(self.inputs.sourcefile, 
                                                   suffix='_warped')])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(ApplyVolTransform, self).run()

    def outputs(self):
        """
        outfile: filename
            Warped source file
        """
        return Bunch(outfile=None)

    def aggregate_outputs(self):
        outputs = self.outputs()
        if self.inputs.outfile is True:
            outfile = glob(fname_presuffix(self.inputs.sourcefile,
                                           suffix='_warped'))
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        return outputs

        
class Smooth(FSLCommand):
    """Use FreeSurfer mris_volsmooth to smooth a volume

    This function smoothes cortical regions on a surface and
    non-cortical regions in volume.

    Parameters
    ----------

    To see optional arguments
    Smooth().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces.freesurfer import Smooth
    >>> smoothvol = Smooth(sourcefile='foo.nii', regfile='reg.dat', surface_fwhm=10, vol_fwhm=6)
    >>> smoothvol.cmdline
    'mris_volsmooth --reg reg.dat --i foo.nii --fwhm 10 --vol-fwhm 6 --o foo_surfsmooth.nii'
    
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mris_volsmooth'

    def inputs_help(self):
        """Print command line documentation for mris_volsmooth."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'sourcefile':         '--i %s',
        'regfile':            '--reg %s',
        'outfile':            '--o %s',
        'surface_fwhm':       '--fwhm %d',
        'vol_fwhm':           '--vol-fwhm %d',
        'flags':              '%s'}
    
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='sourcefile',copy=False)]
        return info
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(Smooth, self)._parse_inputs()

        # Add outfile to the args if not specified
        if self.inputs.outfile is None:
            allargs.extend(['--o', fname_presuffix(self.inputs.sourcefile,
                                                   suffix='_surfsmooth')])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(Smooth, self).run()

    def outputs(self):
        """
        outfile: filename
            Smoothed input volume
        """
        return Bunch(outfile=None)

    def aggregate_outputs(self):
        outputs = self.outputs()
        if self.inputs.outfile is None:
            outfile = glob(fname_presuffix(self.inputs.sourcefile,
                                           suffix='_surfsmooth'))
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        return outputs

        
class SurfConcat(FSLCommand):
    """Use FreeSurfer mris_preproc to prepare a group of contrasts for
    a second level analysis
    
    Parameters
    ----------

    To see optional arguments
    SurfConcat().inputs_help()


    Examples
    --------
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mris_preproc'

    def inputs_help(self):
        """Print command line documentation for mris_preproc."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'target':             '--target %s',
        'hemi':               '--hemi %s',
        'outfile':            '--out %s',
        'outprefix':          None,
        'conimages':          '--iv %s',
        'regs':               '--iv %s',
        'flags':              '%s'}

    def _parse_inputs(self):
        """validate fs surfconcat options"""
        allargs = super(SurfConcat, self)._parse_inputs(skip=('outfile','outprefix','conimages','regs'))

        # Add outfile to the args if not specified
        if self.inputs.outfile is None:
            fname = os.path.join(os.getcwd(),'_'.join((self.inputs.outprefix,
                                                           self.inputs.target,
                                                           '.'.join((self.inputs.hemi,'mgh')))))
            allargs.extend(['--out', fname])
        for i,conimg in enumerate(self.inputs.conimages):
            allargs.extend(['--iv', conimg, self.inputs.regs[i]])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(SurfConcat, self).run()
    
    def outputs(self):
        """
        outfile: filename
            Concatenated volume
        """
        return Bunch(outfile=None)

    def aggregate_outputs(self):
        outputs = self.outputs()
        if not self.inputs.outfile:
            fname = os.path.join(os.getcwd(),'_'.join((self.inputs.outprefix,
                                                           self.inputs.target,
                                                           '.'.join((self.inputs.hemi,'mgh')))))
            outfile = glob(fname)
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            assert len(outfile)==1, "No output file %s created"%outfile
            outputs.outfile = outfile[0]
        return outputs

class OneSampleTTest(FSLCommand):
    """Use FreeSurfer mri_glmfit to prepare a group of contrasts for
    a second level analysis
    
    Parameters
    ----------

    To see optional arguments
    SurfConcat().inputs_help()


    Examples
    --------
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_glmfit'

    def inputs_help(self):
        """Print command line documentation for mris_preproc."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {
        'surf':             '--surf %s',
        'hemi':               '%s',
        'outdir':             '--glmdir %s',
        'outdirprefix':          None,
        'funcimage':          '--y %s',
        'onesample':          '--osgm',
        'design':             '--X %s',
        'flags':              '%s'}

    def _parse_inputs(self):
        """validate fs onesamplettest options"""
        allargs = super(OneSampleTTest, self)._parse_inputs(skip=('surf','hemi','outdir','outdirprefix',))

        # Add outfile to the args if not specified
        allargs.extend(['--surf',self.inputs.surf,self.inputs.hemi])
        if self.inputs.outdir is None:
            outdir = os.getcwd()
            allargs.extend(['--glmdir', outdir])
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(OneSampleTTest, self).run()

    def outputs(self):
        """
        """
        return Bunch()

    def aggregate_outputs(self):
        return self.outputs()
        

class Threshold(FSLCommand):
    """Use FreeSurfer mri_binarize to threshold an input volume

    Parameters
    ----------

    To see optional arguments
    Threshold().inputs_help()


    Examples
    --------
    >>> from nipype.interfaces.freesurfer import Threshold
    >>> binvol = Threshold(infile='foo.nii', min=10, outfile='foo_out.nii')
    >>> binvol.cmdline
    'mri_binarize --i foo.nii --min 10.000000 --o foo_out.nii'
    
   """

    @property
    def cmd(self):
        """sets base command, not editable"""
        return 'mri_binarize'


    def inputs_help(self):
        """Print command line documentation for mri_binarize."""
        print get_doc(self.cmd, self.opt_map, trap_error=False)

    opt_map = {'abs': '--abs',
               'bincol': '--bincol',
               'binval': '--binval %f',
               'binvalnot': '--binvalnot %f',
               'count': '--count %s',
               'dilate': '--dilate %d',
               'erode': '--erode %d',
               'erode2d': '--erode2d %d',
               'frame': '--frame %d',
               'infile': '--i %s',
               'inv': '--inv',
               'mask': '--mask %s',
               'mask-thresh': '--mask-thresh %f',
               'match': '--match %d',
               'max': '--max %f',
               'merge': '--merge %s',
               'min': '--min %f',
               'outfile': '--o %s',
               'rmax': '--rmax %f',
               'rmin': '--rmin %f',
               'ventricles': '--ventricles',
               'wm': '--wm',
               'wm+vcsf': '--wm+vcsf',
               'zero-edges': '--zero-edges',
               'zero-slice-edges': '--zero-slice-edges',
               'flags' : '%s'}
    
    def get_input_info(self):
        """ Provides information about inputs as a dict
            info = [Bunch(key=string,copy=bool,ext='.nii'),...]
        """
        info = [Bunch(key='infile',copy=False)]
        return info
    
    def _parse_inputs(self):
        """validate fs bbregister options"""
        allargs = super(Threshold, self)._parse_inputs()

        # Add infile and outfile to the args if they are specified
        if not self.inputs.outfile and self.inputs.infile:
            allargs.extend(['--o',fname_presuffix(self.inputs.infile,
                                                  suffix='_out',
                                                  newpath=os.getcwd())])
        
        return allargs
    
    def run(self, **inputs):
        """Execute the command.
        """
        return super(Threshold, self).run()

    def outputs(self):
        """
        outfile: filename
            thresholded output file
        """
        outputs = Bunch(outfile=None)
        return outputs

    def aggregate_outputs(self):
        outputs = self.outputs()
        if isinstance(self.inputs.outfile,str):
            outfile = glob(self.inputs.outfile)
            outputs.outfile = outfile[0]
        elif not self.inputs.outfile and self.inputs.infile:
            outfile = glob(fname_presuffix(self.inputs.infile,
                                           suffix='_out', newpath=os.getcwd())) 
            outputs.outfile = outfile[0]
        return outputs
