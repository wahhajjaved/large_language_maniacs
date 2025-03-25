import ROOT as rt
import RootTools

def getCrossSections():
    """Return the NLO cross-sections used in the normalsation"""
    
    #the QCD cross-section is basically a junk value
    return {'SingleTop_s':4.21,'SingleTop_t':64.6,'SingleTop_tw':10.6,\
                               'TTj':157.5,'Zll':3048/3.,'Znn':2*3048,'Wln':31314/3.,\
                               'WW':43,'WZ':18.2,'ZZ':5.9,'Vgamma':173,
                               'QCD':26456
                               }

class Box(object):
    
    def __init__(self, name, variables, workspace = None):
        self.name = name
        
        if workspace is None:
            self.workspace = rt.RooWorkspace(name)
        else:
            self.workspace = workspace

        #the SM cross-sections from Chris - NB for W and Z we take the per-flavour cross-sections            
        self.cross_sections = getCrossSections()
        for name, value in self.cross_sections.iteritems():
            self.workspace.factory('%s[%f]' % (name, value) )
            
        self.fitmodel = 'fitmodel'
        self.signalmodel = self.fitmodel
        self.cut = 'MR >= 0.0'
        
    def yieldToCrossSection(self, flavour="none"):
        result = None
        if flavour != "none": 
            result = self.workspace.factory("expr::Ntot_%s('@0*@1*@2*@3',Lumi,%s,Epsilon_%s, rEps_%s)" % (flavour, flavour, flavour, flavour))
        else:
            result = self.workspace.factory("expr::Ntot('@0*@1*@2*@3',Lumi,Sigma,Epsilon, rEps)")
        return result
        
    def getVarRangeCut(self, range = ''):
        cut = ''
        def var_cut(v):
            return '( (%s >= %f) && (%s < %f) )' % (v.GetName(),v.getMin(range),v.GetName(),v.getMax(range))
        vars = [v for v in RootTools.RootIterator.RootIterator(self.workspace.set('variables'))]
        if vars:
            cut = var_cut(vars[0])
            for v in vars[1:]:
                cut = '%s && %s' % (cut, var_cut(v))
        return cut
    
    def getVarRangeCutNamed(self, ranges):
        vars = [v for v in RootTools.RootIterator.RootIterator(self.workspace.set('variables'))]
        cut = self.getVarRangeCut(ranges[0])
        for r in ranges[1:]:
            cut = '(%s) || (%s)' % (cut, self.getVarRangeCut(r) )
        return cut

    def defineSet(self, name, variables):
        self.workspace.defineSet(name,'')
        for v in variables:
            r = self.workspace.factory(v)
            self.workspace.extendSet(name,r.GetName())     
            
    def restoreWorkspace(self, inputFile, workspace, name = 'independentFRPDF'):
        input = rt.TFile.Open(inputFile)
        ws = input.Get(workspace)
        if ws:
            self.workspace = ws
        input.Close()
        pdfs = self.workspace.allPdfs()
        
        if self.workspace.obj(name):
            self.fitmodel = self.workspace.obj(name).GetName()
        else:
            #set the name of the fitmodel from the workspace
            master = 'fitmodel'
            for p in RootTools.RootIterator.RootIterator(pdfs):
                if 'fitmodel' in p.GetName():
                    if len(p.GetName().split('_')) > len(master.split('_')):
                        master = p.GetName()
                self.fitmodel = master
        if not self.workspace.pdf(self.fitmodel):
            print 'Master PDF not found... in workspace'
    
    def setFitModelName(self, name):
        if name is not None:
            self.fitmodel = '%s_%s' % (self.fitmodel,name)
        else:
            print 'WARNING:: Name decorator provided for fitmodel was None'
        return self.fitmodel
        
    def getFitPDF(self, name=None,graphViz='graphViz'):
        if name is None:
            name = self.fitmodel
        pdf = self.workspace.pdf(name)        

        if not pdf:
            print 'WARNING:: Failed to get pdf "%s"' % name
            return pdf 

        #save as a dotty file for easy inspection
        if graphViz is not None:
            pdf.graphVizTree('%s_%s.dot' % (pdf.GetName(),graphViz))
        return pdf
    
    def getMCStudy(self, fitmodel=None, genmodel=None, *options):
        if fitmodel is None:
            fitmodel = self.fitmodel
        if genmodel is None:
            genmodel = self.fitmodel
        
        fit = self.getFitPDF(fitmodel,graphViz=None)
        gen = self.getFitPDF(genmodel,graphViz=None)
        vars = self.workspace.set('variables')
        
        #make a list of arguments for FitOptions using unpacking
        opt = []
        #always save the fit result
        opt.append(rt.RooFit.Save(True))
        #automagically determine the number of cpus
        opt.append(rt.RooFit.NumCPU(RootTools.Utils.determineNumberOfCPUs()))
        for o in options:
            opt.append(o)
        opt = tuple(opt)
        
        study = rt.RooMCStudy(gen,vars,rt.RooFit.Extended(True),rt.RooFit.FitModel(fit),rt.RooFit.FitOptions(*opt))
        return study
    
    def makeRooHistPdf(self, inputFile, modelName):
        
        signal = RootTools.getDataSet(inputFile,'RMRTree', self.cut)
        vars = self.workspace.set('variables')
        
        hvars = rt.RooArgSet()
        for p in RootTools.RootIterator.RootIterator(vars):
            p.setBins(100)
            hvars.add(p)
        
        #create a binned dataset in the parameter   
        hdata = rt.RooDataHist('%sHist' % modelName,'%sHist' % modelName,hvars, signal)
        self.importToWS(hdata)
        hpdf = rt.RooHistPdf('%sPdf' % modelName,'%sPdf' % modelName,vars,hdata)
        self.importToWS(hpdf)
        return (hpdf.GetName(),signal.numEntries())

    
    def importToWS(self, *args):
        """Utility function to call the RooWorkspace::import methods"""
        return getattr(self.workspace,'import')(*args)
    
    def fit(self, inputFile, reduce = None, *options):
        """Take the dataset and fit it with the top level pdf. Return the fitresult"""
        data = self.workspace.data("RMRTree")
        return self.fitData(self.getFitPDF(), data, *options)

    def fitDataSilent(self, pdf, data, *options):
        """Take the dataset and fit it with the top level pdf. Return the fitresult"""
        
        opt = rt.RooLinkedList()
        #always save the fit result
        opt.Add(rt.RooFit.Save(True))
        #automagically determine the number of cpus
        opt.Add(rt.RooFit.NumCPU(RootTools.Utils.determineNumberOfCPUs()))
        for o in options:
            opt.Add(o)
            
        if data.isWeighted():
            opt.Add(rt.RooFit.SumW2Error(True))
        
        result = pdf.fitTo(data, opt)
        return result 

    
    def fitData(self, pdf, data, *options):
        """Take the dataset and fit it with the top level pdf. Return the fitresult"""
        
        if data.isWeighted():
            print 'The dataset is weighted: Performing a SumW2 fit'

        result = self.fitDataSilent(pdf, data, *options)
        result.Print('V')
        if result.status() != 0 or result.covQual() != 3:
            print 'WARNING:: The fit did not converge with high quality. Consider this result suspect!'
        
        return result 

    def generateToyWithYield(self, genmodel, number, *options):
        """Generate a toy dataset with the specified number of events"""
        
        vars = self.workspace.set('variables')
        pdf = self.workspace.pdf(genmodel)

        gdata = pdf.generate(vars,number,*options)
        gdata_cut = gdata.reduce(self.cut)
        return gdata_cut
    
    def generateToy(self, genmodel, *options):
        """Generate a toy dataset with the number of events the same as that in the workspace"""
        data = self.workspace.data('RMRTree')
        return self.generateToyWithYield(genmodel, rt.RooRandom.randomGenerator().Poisson(data.numEntries()), *options)


    def plotObservables(self, inputFile, name = None, range = ''):
        """Make control plots for variables defined in the 'variables' part of the config"""

        if name is None:
            name = self.fitmodel

        data = RootTools.getDataSet(inputFile,'RMRTree',self.cut)
        fitmodel = self.workspace.pdf(name)
        
        plots = []
        parameters = self.workspace.set("variables")
        #use a binned dataset to make the plots as it is faster        
        hvars = rt.RooArgSet()
        for p in RootTools.RootIterator.RootIterator(parameters):
            p.setBins(100)
            hvars.add(p)
        hdata = rt.RooDataHist('projData_%s' % self.name,'projData',hvars,data.reduce(rt.RooFit.CutRange(range)))
        hdata = hdata.reduce(self.getVarRangeCutNamed(ranges=range.split(',')))
        
        for p in RootTools.RootIterator.RootIterator(parameters):
            
            xmin = min([p.getMin(r) for r in range.split(',')])
            xmax = max([p.getMax(r) for r in range.split(',')])
            
            frame = p.frame(xmin,xmax)
            frame.SetName("autoVarPlot_%s_%s" % (p.GetName(), '_'.join(range.split(',')) ) )
            #
            hdata.plotOn(frame)
            fitmodel.plotOn(frame, rt.RooFit.NumCPU(RootTools.Utils.determineNumberOfCPUs()),rt.RooFit.Range(xmin,xmax),rt.RooFit.ProjWData(hdata))
            fitmodel.paramOn(frame)
            plots.append(frame)
            
        return plots

    def fixVariable(self, var, mean, sigma, model=None):
        """Add a Gaussian penalty term for a semi-fixed parameter"""
        
        if model is None:
            model = self.fitmodel
        
        var_m = '%s_mean[%f]' % (var,mean)
        if self.workspace.var('%s_s' % var):
            var_s = '%s_s' % var
        else:
            var_s = '%s_s[%f]' % (var,sigma)
        var_ref = self.workspace.var(var)
        
        self.workspace.factory('RooGaussian::%s_penalty(%s,%s,%s)' % (var,var,var_m,var_s))
        fitmodel = self.workspace.pdf(model)
        modelName = '%s_fix%s' % (model, var)
        self.workspace.factory('PROD::%s(%s,%s_penalty)' % (modelName,model,var))
        self.fitmodel = modelName
        print 'Added a Gaussian penalty term for %s: %f\pm %f [%f,%f]' % (var,mean,sigma,var_ref.getMin(),var_ref.getMax())

    def fixPars(self, label, doFix=rt.kTRUE, setVal=None):
        parSet = self.workspace.allVars()
        for par in RootTools.RootIterator.RootIterator(parSet):
            if label in par.GetName():
                par.setConstant(doFix)
                if setVal is not None: par.setVal(setVal)
    
    def fixAllPars(self):
        """Fix all the parameters and return a list of which ones were fixed"""
        
        fixed_pars = []
        parSet = self.workspace.allVars()
        for par in RootTools.RootIterator.RootIterator(parSet):
            if not par.isConstant():
                fixed_pars.append(par.GetName())
                par.setConstant(True)
        return fixed_pars
    
    def fixParsExact(self, label, doFix=rt.kTRUE, setVal=None, setError=None):
        parSet = self.workspace.allVars()
        for par in RootTools.RootIterator.RootIterator(parSet):
            if label == par.GetName():
                par.setConstant(doFix)
                if setVal is not None: par.setVal(setVal)
                if setError is not None: par.setError(setError)
    
    def fixParsPenalty(self, label, floatIfNoPenalty = False):
        
        allVars = self.workspace.allVars()
        pars = {}
        for p in RootTools.RootIterator.RootIterator(allVars): pars[p.GetName()] = p
        for name, par in pars.iteritems():
            if label in par.GetName():
                if pars.has_key('%s_s' % name):
                    sigma = pars['%s_s' % name].getVal() 
                    self.fixVariable(par.GetName(), par.getVal(),sigma)
                    par.setConstant(False)
                elif floatIfNoPenalty:
                    self.fixParsExact(par.GetName(),False)

    def generateToyFRWithYield(self, genmodel, fr, number, *options):
        """Generate a toy dataset with the specified number of events"""
        
        pdf = self.workspace.pdf(genmodel)
        vars = rt.RooArgSet(self.workspace.set('variables'))
        if self.workspace.cat('Boxes'):
            vars.add(self.workspace.cat('Boxes'))
        
        parSet = self.workspace.allVars()
        #set the parameter values
        pars = {}
        for p in RootTools.RootIterator.RootIterator(fr.randomizePars()): pars[p.GetName()] = p
        for name, value in pars.iteritems():
            self.fixParsExact(name,value.isConstant(),value.getVal(),value.getError())
        gdata = pdf.generate(vars,rt.RooRandom.randomGenerator().Poisson(number),*options)
        
        #now set the parameters back
        pars = {}
        for p in RootTools.RootIterator.RootIterator(fr.floatParsFinal()): pars[p.GetName()] = p
        for name, value in pars.iteritems():
            self.fixParsExact(name,value.isConstant(),value.getVal(),value.getError())

        gdata_cut = gdata.reduce(self.cut)
        return gdata_cut
    
    def generateToyFR(self, genmodel, fr, *options):
        """Generate a toy dataset with the number of events the same as that in the workspace"""
        data = self.workspace.data('RMRTree')
        return self.generateToyFRWithYield(genmodel, fr, rt.RooRandom.randomGenerator().Poisson(data.numEntries()), *options)


    def writeBackgroundDataToys(self, fr, total_yield, box, nToys):
        """Write out toys which have been sampled from a fit result"""
        
        for i in xrange(nToys):
            ds = self.generateToyFRWithYield(self.fitmodel, fr, total_yield)
            ds.write('frtoydata_%s_%i.txt' % (box,i))

    def predictBackgroundData(self, fr, data, nRepeats = 100, verbose = True):
        
        if fr.status() != 0 or fr.covQual() != 3:
            print 'Skipping background prediction for box %s as the fit did not converge properly' % self.name
            return (-1,-1)

        total_yield = data.numEntries()
        data_cut = data.reduce(self.cut)
        background_yield = data_cut.numEntries()
        
        pdf = self.workspace.pdf(self.fitmodel)
        vars = rt.RooArgSet(self.workspace.set('variables'))
        if self.workspace.cat('Boxes'):
            vars.add(self.workspace.cat('Boxes'))
        
        background_prediction = 0
        
        parSet = self.workspace.allVars()
        for i in xrange(nRepeats):
            pars = {}
            for p in RootTools.RootIterator.RootIterator(fr.randomizePars()): pars[p.GetName()] = p
            for name, value in pars.iteritems():
                self.fixParsExact(name,value.isConstant(),value.getVal(),value.getError())
            ds = pdf.generate(vars,rt.RooRandom.randomGenerator().Poisson(total_yield))
            before = ds.numEntries()
            ds = ds.reduce(self.cut)
            after = ds.numEntries()
            
            background_prediction += (before-after)
            
        background_prediction /= (1.0*nRepeats)
        if verbose:
            #print 'Background observed in the %s box: %i' % (self.name,total_yield-background_yield)
            print 'Background prediction after %i repeats: %f' % (nRepeats,background_prediction)
        
        #now set the parameters back
        pars = {}
        for p in RootTools.RootIterator.RootIterator(fr.floatParsFinal()): pars[p.GetName()] = p
        for name, value in pars.iteritems():
            self.fixParsExact(name,value.isConstant(),value.getVal(), value.getError())
            
        return (background_prediction,total_yield-background_yield)



    def predictBackground(self, fr, inputFile, nRepeats = 100):
        data = RootTools.getDataSet(inputFile,'RMRTree')
        return self.predictBackgroundData(fr, data, nRepeats)

        
    def define(self, inputFile, cuts):
        pass
    
    def addSignalModel(self, inputFile, modelName):
        """Add a signal model for model dependent limits"""
        pass

    def plot2D(self, inputFile, xvarname, yvarname, ranges=None, data = None):
        
        if ranges is None:
            ranges = ['']
        
        #before I find a better way
        if data is None:
            data = RootTools.getDataSet(inputFile,'RMRTree')
        #data = data.reduce(self.getVarRangeCutNamed(ranges=ranges))
        toyData = self.workspace.pdf(self.fitmodel).generate(rt.RooArgSet(self.workspace.argSet(xvarname+","+yvarname)), 50*data.numEntries())
        toyData = toyData.reduce(self.getVarRangeCutNamed(ranges=ranges))

        xmin = min([self.workspace.var(xvarname).getMin(r) for r in ranges])
        xmax = max([self.workspace.var(xvarname).getMax(r) for r in ranges])
        ymin = min([self.workspace.var(yvarname).getMin(r) for r in ranges])
        ymax = max([self.workspace.var(yvarname).getMax(r) for r in ranges])

        # define 2D histograms
        histoData = rt.TH2D("histoData", "histoData",
                            100, xmin, xmax, 
                            100, ymin, ymax)
        histoToy = rt.TH2D("histoToy", "histoToy",
                            100, xmin, xmax, 
                            100, ymin, ymax)
        # project the data on the histograms
        data.tree().Project("histoData",yvarname+":"+xvarname)
        toyData.tree().Project("histoToy",yvarname+":"+xvarname)
        histoToy.Scale(histoData.Integral()/histoToy.Integral())
        histoData.Add(histoToy, -1)
        histoData.SetName('Compare_Data_MC_%s' % '_'.join(ranges) )
        return histoData
    
    def plot1DHisto(self, inputFile, xvarname, ranges=None, data = None):
        
        if ranges is None:
            ranges = ['']
        
        #before I find a better way
        if data is None:
            data = RootTools.getDataSet(inputFile,'RMRTree')
        toyData = self.workspace.pdf(self.fitmodel).generate(self.workspace.set('variables'), 50*data.numEntries())
        toyData = toyData.reduce(self.getVarRangeCutNamed(ranges=ranges))

        xmin = min([self.workspace.var(xvarname).getMin(r) for r in ranges])
        xmax = max([self.workspace.var(xvarname).getMax(r) for r in ranges])
        #nbins = rt.TMath.Nint(abs(xmax-xmin)/2.5)
        nbins = 25

        def setName(h, name):
            h.SetName('%s_%s_%s' % (h.GetName(),name,'_'.join(ranges)) )
            h.GetXaxis().SetTitle(name)

        # define 1D histograms
        histoData = rt.TH1D("histoData", "histoData",nbins, xmin, xmax)
        histoToy = rt.TH1D("histoToy", "histoToy",nbins, xmin, xmax)

        # project the data on the histograms
        data.tree().Project("histoData",xvarname)
        toyData.tree().Project("histoToy",xvarname)
        histoToy.Scale(histoData.Integral()/histoToy.Integral())

        setName(histoData,xvarname)
        setName(histoToy,xvarname)

        histoData.SetOption('e1')
        histoData.SetMarkerStyle(20)
        histoToy.SetLineColor(rt.kBlue)
        histoToy.SetLineWidth(2)
        histoToy.SetOption('e3')
        
        c = rt.TCanvas()
        c.SetName('DataMC_%s_%s' % (xvarname,'_'.join(ranges)) )
        histoData.Draw()
        histoToy.Draw('same')

        return [histoData,histoToy,c]


    def plot(self, inputFile, store, box):
        [store.store(p, dir = box) for p in self.plotObservables(inputFile)]
    
