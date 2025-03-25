#!/usr/bin/env python

from glob import glob
from DataObject import SignalRegion
from ValueWithError import valueWithError
import ROOT
ROOT.gROOT.SetBatch(True)

class DMSTAReader:
    """Similar to the dummy reader, but reads truth yields from an ntuple and CL values from text files."""

    # Dictionary that serves two purposes
    # 1) the keys control what analyses will be included
    # 2) the values are associated strings used in the ntuple branch names
    analysisdict = {
        '3L': 'EwkThreeLepton_3L',
        '4L': 'EwkFourLepton',
        '2L': 'EwkTwoLepton',
        '2T': 'EwkTwoTau',
        }
    
    # Gah, way too many arguments - could fix with slots if I have time
    def __init__(self, yieldfile='Data_Yields/SummaryNtuple_STA_sim.root',
                 dirprefix='Data_', fileprefix='pMSSM_STA_table_EWK_', filesuffix='.dat',
                 DSlist='Data_Yields/D3PDs.txt'):
        """
        Set up to read input files from several directories.
        The yield ntuple path is stated explicitly, as is the DS list (for mapping the model ID to the DS ID).
        The CL values are assumed to be in dirprefix+analysis/fileprefix+analysis+'_'+SR+filesuffix
        The analysis names are taken from self.analysisdict.keys(), and the SR names are deduced from the file names.
        The ntuple is in the format described in https://twiki.cern.ch/twiki/bin/view/AtlasProtected/SUSYRun1pMSSMSummaryNtuple
        The file format column-based with whitespace separation and should look like
        Dataset   CL_b    CL_b_up   CL_b_down   CL_s+b   CL_s+b_up   CL_s+b_down
        Lines beginning with a # are regarded as comments and ignored.
        The dataset will be used to label the model.
        Lines with non-numeric data will be ignored.

        If no files of the above pattern are found for a particular directory, but files ending .yaml are found,
        Then the reader assumes a format like
        SR: [yield,CLs_obs,CLs_exp]
        At the time of writing, this is used by the 2L search
        """
        
        self.__yieldfile = yieldfile
        self.__dirprefix = dirprefix
        self.__fileprefix = fileprefix
        self.__filesuffix = filesuffix
        self.__dslist = DSlist
        self.__DSIDdict = {} # Formed from the DSlist in a bit
        
    def ReadFiles(self):
        """Returns a list of SignalRegion objects, as required by the CorrelationPlotter.
        """

        # This is what we want to return
        result = []

        # First map model IDs to DSIDs
        self.__ReadDSIDs()

        # Because the input is split between different formats,
        # I need to break the reading down into two steps.

        # The CL values are more refined and can give me the SR names for free,
        # so start with those
        for analysis in self.analysisdict.keys():
            result = self.ReadCLValues(result, analysis)

        # Then add the yields
        result = self.ReadYields(result)

        # Keep warning/info messages from different sources separate
        print

        return result

    def __ReadDSIDs(self):
        """Map the model number to the ATLAS dataset ID.
        The information from self.__dslist is stored in self.__DSIDdict
        """
        
        if not self.__dslist:
            return
            
        # First open the DSlist to find which models we need
        f = open(self.__dslist)
        
        for line in f:

            line = line.rstrip()
            if not line:
                continue
            
            # The line should be empty or a dataset name
            splitline = line.split('.')

            try:
                # In both cases I need a string, but want to check that it's a valid int
                DSID = int(splitline[1])
                modelID = int(splitline[2].split('_')[5])
            except IndexError:
                print 'WARNING in Reader_DMSTA: failed to read line'
                print repr(line)
                print splitline
                raise # Because I want to see what this is and fix it

            self.__DSIDdict[modelID] = DSID

        f.close()

        return

    def ReadYields(self, data):
        """Reads the model yields from the given ntuple file.
        The data argument should be an already-populated list of SignalRegion instances.
        """

        if not self.__yieldfile:
            return data
            
        # Keep warning/info messages from different sources separate
        print
            
        # Open up the ROOT ntuple with the yields and iterate over the entries
        # looking for relevant models
        yieldfile = ROOT.TFile.Open(self.__yieldfile)

        if not yieldfile:
            print 'ERROR: ROOT file %s not found'%(self.__yieldfile)
            # If I were doing this properly, I'd probably raise an exception
            return result
        
        tree = yieldfile.Get('susy')

        # Quick & dirty optimisation of what to read, as the tree is big
        tree.SetBranchStatus('*', 0)
        tree.SetBranchStatus('modelName', 1)
        for analysis in self.analysisdict.values():
            tree.SetBranchStatus('*%s*'%(analysis), 1)

        print 'INFO: Reader_DMSTA looping over %s entries'%(tree.GetEntries())
        filledYields = 0
        
        for entry in tree:

            modelID = int(entry.modelName)

            try:
                DSID = self.__DSIDdict[modelID]
            except KeyError:
                continue # Not interested (yet)

            # Loop over known analyses/SRs and look for the truth yield
            for datum in data:

                analysisSR = datum.name

                truthyield = getattr(entry, '_'.join(['EW_ExpectedEvents',datum.branchname]))
                trutherror = getattr(entry, '_'.join(['EW_ExpectedError',datum.branchname]))

                try:
                    datum.data[DSID]['yield'] = valueWithError(truthyield,trutherror)
                    filledYields += 1

                except KeyError:
                    # FIXME: Should check if the model is in DSIDdict and the yield is high and print a warning if it's not in data
                    pass

        print 'Filled %i entries with yields'%(filledYields)
        return data
    
    def ReadCLValues(self, data, analysis):
        """For the given analysis, add the CL values to the data.
        """

        # Find the input files
        # Try the traditional pMSSM paper format first
        firstbit = self.__dirprefix+analysis+'/'+self.__fileprefix+analysis+'_'
        searchstring = firstbit+'*'+self.__filesuffix
        infiles = glob(searchstring)

        if infiles:
            
            print 'INFO: Reader_DMSTA found %i matches to %s'%(len(infiles),searchstring)
            for fname in infiles:
                SRname = fname.replace(firstbit,'').replace(self.__filesuffix,'')
                data = self.__ReadPmssmFiles(data, analysis, fname, SRname)

        else:

            # Oh dear, maybe these are YAML files
            firstbit = self.__dirprefix+analysis
            searchstring = '/'.join([firstbit,'*.yaml'])
            infiles = glob(searchstring)

            print 'INFO: Reader_DMSTA found %i matches to %s'%(len(infiles),searchstring)
            for fname in infiles:
                modelname = int(fname.split('/')[-1].split('.')[0])
                DSID = self.__DSIDdict[modelname]
                data = self.__ReadYamlFiles(data, analysis, fname, DSID)

        return data

    def __ReadYamlFiles(self, data, analysis, fname, modelname):

        f = open(fname)

        for line in f:

            splitline = line.split()

            # Skip empty lines
            if not splitline: continue

            # Apply some basic formatting to the SR name
            SRname = splitline[0].rstrip(':').replace('-','_')

            analysisSR = '_'.join([analysis,SRname])

            # Try to find the existing data item
            obj = next((x for x in data if x.name == analysisSR), None)
            if obj is None:
                # First time we've looked at this analysisSR
                obj = SignalRegion(analysisSR, ['CLs'])
                data.append(obj)

                # Store the equivalent ntuple branch name for convenience later
                obj.branchname = '_'.join([self.analysisdict[analysis],self.NtupleSRname(SRname,analysis)])
                
                obj.fitfunctions['CLs'] = ROOT.TF1('fitfunc','(x-1)++TMath::Log(x)')
                obj.fitfunctions['CLs'].SetParameter(0,-10)
                obj.fitfunctions['CLs'].SetParLimits(0,-500,0)
                obj.fitfunctions['CLs'].SetParameter(1,-5.)
                obj.fitfunctions['CLs'].SetParLimits(1,-500,0)
                obj.fitfunctions['CLs'].SetRange(0,0.8)

            # The data is stored as a list, use ast to read it
            import ast
            numericdata = ast.literal_eval(''.join(splitline[1:]))

            try:
                CLs = float(numericdata[1])
            except IndexError:
                print 'WARNING: Incomplete data in %s, %s'%(fname,SRname)
                print line
                continue
            except:
                print 'WARNING: Invalid CLs value %s in %s, %s'%(numericdata[1],fname,SRname)
                continue

            try:
                datum = obj.data[modelname]
                print 'WARNING: Entry for model %i already exists for %s'%(modelname,analysisSR)
            except KeyError:
                datum = obj.AddData(modelname)

            if CLs and CLs > 0:
                datum['CLs'] = CLs
                
        f.close() # Let's be tidy

        return data

    def __ReadPmssmFiles(self, data, analysis, fname, SRname):

        analysisSR = '_'.join([analysis,SRname])

        # Try to find the existing data item
        obj = next((x for x in data if x.name == analysisSR), None)
        if obj is None:
            # First time we've looked at this analysisSR
            obj = SignalRegion(analysisSR, ['CLs'])
            data.append(obj)

            # Store the equivalent ntuple branch name for convenience later
            obj.branchname = '_'.join([self.analysisdict[analysis],self.NtupleSRname(SRname,analysis)])
        else:
            print 'WARNING in Reader_DMSTA: already read-in file for %s'%(analysisSR)
            return data

        obj.fitfunctions['CLs'] = ROOT.TF1('fitfunc','(x-1)++TMath::Log(x)')
        obj.fitfunctions['CLs'].SetParameter(0,-0.1)
        obj.fitfunctions['CLs'].SetParLimits(0,-500,0)
        obj.fitfunctions['CLs'].SetParameter(1,-1.)
        obj.fitfunctions['CLs'].SetParLimits(1,-500,0)
        obj.fitfunctions['CLs'].SetRange(0,0.8)

        # Special case(s)
        if SRname in ['SR0aBIN01','SR0aBIN02','SR0aBIN03','SR0aBIN04']:
            obj.fitfunctions['CLs'].SetRange(0,0.7)

        f = open(fname)
        for line in f:

            splitline = line.split()

            # Skip comments and empty lines
            if not splitline: continue
            if splitline[0].startswith('#'): continue
            try:
                modelpoint = int(splitline[0])
            except ValueError:
                continue # Line of text
            
            try:
                # Find all the input data first
                CLb = float(splitline[1])
                CLsb = float(splitline[4])
            except:
                print 'WARNING: Malformed line in %s: %s'%(fname,line)
                # Carry on, hopefully we can just analyse the other results
                continue

            # Check that either CLsb or CLb were read OK
            if CLb is None and CLsb is None: continue

            if not CLb and CLb is not None:
                print 'WARNING: CLb is zero in %s, model %s'%(fname,modelpoint)
            if not CLsb and CLsb is not None:
                print 'WARNING: CLsb is zero in %s, model %s'%(fname,modelpoint)

            try:
                datum = obj.data[modelpoint]
                print 'WARNING: Entry for model %i already exists for %s'%(modelpoint,analysisSR)
            except KeyError:
                datum = obj.AddData(modelpoint)

            if CLb and CLsb:
                datum['CLs'] = CLsb/CLb

        f.close() # Let's be tidy
        
        return data
    
    def NtupleSRname(self, SRname, analysis):
        """Convert the SR name used in the CL files to that used in the yield ntuple.
        """

        if analysis == '3L':
            # Fix for 3L SR0a
            SRname = SRname.replace('BIN0','_')
            SRname = SRname.replace('BIN','_')
    
            # Fix for a couple of other 3L SRs
            SRname = SRname.replace('SR0tb','SR0b')
            SRname = SRname.replace('SR1t','SR1SS')

        return SRname
    
