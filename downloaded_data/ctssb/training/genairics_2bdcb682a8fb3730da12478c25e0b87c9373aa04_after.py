#!/bin/env python
#PBS -N RNAseqPipeline
#PBS -l nodes=1:ppn=16
#PBS -l walltime=72:00:00
#PBS -m be
"""
Full pipeline starting from BaseSpace fastq project
"""
from datetime import datetime, timedelta
import luigi, os, tempfile, pathlib, glob
from luigi.contrib.external_program import ExternalProgramTask
from luigi.util import inherits
from plumbum import local

## Luigi dummy file target dir
luigitempdir = tempfile.mkdtemp(prefix=os.environ.get('TMPDIR','/tmp/')+'luigi',suffix='/')

## Tasks
class basespaceData(luigi.Task):
    datadir = luigi.Parameter(description='directory that contains data in project folders')
    NSQrun = luigi.Parameter(description='project name')
    apitoken = (
        luigi.Parameter(os.environ.get('BASESPACE_API_TOKEN'),description='$BASESPACE_API_TOKEN') if os.environ.get('BASESPACE_API_TOKEN')
        else luigi.Parameter(description='$BASESPACE_API_TOKEN')
    )

    # Set up temporary dummy output file
    # for every initiated task a new dummy is set up
    # this ensures that every new workflow run, will exectute all tasks
    def output(self):
        return luigi.LocalTarget('{}/../results/{}/plumbing/1_downloadCompleted'.format(self.datadir,self.NSQrun))

    def run(self):
        local['BaseSpaceRunDownloader.py']('-p', self.NSQrun, '-a', self.apitoken, '-d', self.datadir)
        #Renaming download dir simply to project name
        downloadedName = glob.glob('{}/{}*'.format(self.datadir,self.NSQrun))
        if len(downloadedName) != 1: raise Exception('Something went wrong downloading',self.NSQrun)
        else: os.rename(downloadedName[0],'{}/{}'.format(self.datadir,self.NSQrun))
        os.mkdir('{}/../results/{}'.format(self.datadir,self.NSQrun))
        os.mkdir('{}/../results/{}/plumbing'.format(self.datadir,self.NSQrun))
        pathlib.Path(self.output().path).touch()

@inherits(basespaceData)
class mergeFASTQs(luigi.Task):
    """
    Merge fastqs if one sample contains more than one fastq
    """
    dirstructure = luigi.Parameter(default='multidir',
                                   description='dirstructure of datatdir: onedir or multidir')
    def requires(self):
        return basespaceData()
        
    def output(self):
        return luigi.LocalTarget('{}/../results/{}/plumbing/2_mergeFASTQs'.format(self.datadir,self.NSQrun))

    def run(self):
        if self.dirstructure == 'multidir':
            outdir = '{}/../results/{}/mergedFASTQs/'.format(self.datadir,self.NSQrun)
            os.mkdir(outdir)
            dirsFASTQs = local['ls']('{}/{}'.format(self.datadir,self.NSQrun)).split()
            for d in dirsFASTQs:
                (local['ls'] >> (self.output().path + '_log'))('-lh','{}/{}/{}'.format(self.datadir,self.NSQrun,d))
                (local['cat'] > outdir+d+'.fastq.gz')(
                    *glob.glob('{}/{}/{}/*.fastq.gz'.format(self.datadir,self.NSQrun,d))
                )
            os.rename('{}/{}'.format(self.datadir,self.NSQrun),'{}/{}_original_FASTQs'.format(self.datadir,self.NSQrun))
            os.symlink(outdir,'{}/{}'.format(self.datadir,self.NSQrun), target_is_directory = True)
        pathlib.Path(self.output().path).touch()

@inherits(mergeFASTQs)
class qualityCheck(luigi.Task):

    def requires(self):
        return mergeFASTQs()
        
    def output(self):
        return luigi.LocalTarget(luigitempdir+self.task_id+'_success')

    def run(self):
        local['qualitycheck.sh'](self.NSQrun, self.dirstructure, self.datadir)
        pathlib.Path(self.output().path).touch()

@inherits(qualityCheck)
class alignTask(luigi.Task):
    suffix = luigi.Parameter(default='',description='use when preparing for xenome filtering')
    genome = luigi.Parameter(default='RSEMgenomeGRCg38/human_ensembl',
                             description='reference genome to use')

    def requires(self):
        return qualityCheck()

    def output(self):
        return luigi.LocalTarget(luigitempdir+self.task_id+'_success')

    def run(self):
        local['STARaligning.py'](self.NSQrun, self.dirstructure, self.datadir, self.suffix, self.genome)
        pathlib.Path(self.output().path).touch()
    
@inherits(alignTask)
class countTask(luigi.Task):
    forwardprob = luigi.FloatParameter(default=0.5,
                                       description='stranded seguencing [0 for illumina stranded], or non stranded [0.5]')
    PEND = luigi.BoolParameter(default=False,
                               description='paired end sequencing reads')

    def requires(self):
        return qualityCheck()

    def output(self):
        return luigi.LocalTarget(luigitempdir+self.task_id+'_success')

    def run(self):
        local['RSEMcounting.sh'](self.NSQrun, self.datadir, self.genome, self.forwardprob, self.PEND)
        pathlib.Path(self.output().path).touch()

@inherits(countTask)
class diffexpTask(luigi.Task):
    design = luigi.Parameter(description='model design for differential expression analysis')
    
    def requires(self):
        return countTask()
    
    def output(self):
        return luigi.LocalTarget(luigitempdir+self.task_id+'_success')

    def run(self):
        local['simpleDEvoom.R'](self.NSQrun, self.datadir, self.design)
        pathlib.Path(self.output().path).touch()

if __name__ == '__main__':
    import argparse

    typeMapping = {
        luigi.parameter.Parameter: str,
        luigi.parameter.BoolParameter: bool,
        luigi.parameter.FloatParameter: float
    }

    defaultMappings = {
        'genome': 'RSEMgenomeGRCg38/human_ensembl'
    }
    
    parser = argparse.ArgumentParser(description='RNAseq processing pipeline.')
    # if arguments are set in environment, they are used as the argument default values
    # this allows seemless integration with PBS jobs
    for paran,param in countTask.get_params():
        if paran in defaultMappings:
            parser.add_argument('--'+paran, default=defaultMappings[paran], type=typeMapping[type(param)], help=param.description)
        else: parser.add_argument('--'+paran, type=typeMapping[type(param)], help=param.description)
        
    if os.environ.get('PBS_JOBNAME'):
        #Retrieve arguments from qsub job environment
        #For testing:
        # os.environ.setdefault('datadir','testdir')
        # os.environ.setdefault('NSQrun','testrun')
        args = parser.parse_args('{} {} {}'.format(
            os.environ.get('datadir'),
            os.environ.get('NSQrun'),
            '--PEND ' if os.environ.get('PEND') else '',
        ).split())
    else:
        #Script started directly
        args = parser.parse_args()

    #luigi.run()
    #workflow = alignTask(datadir='/tmp',NSQrun='run1',apitoken='123abc',dirstructure='one')
    workflow = countTask(**vars(args))
    print(workflow)

    print('[re]move ',luigitempdir)
