#! /usr/bin/env python
#
"""
This code calculates counts rates for an input spectrum in the NIRISS imaging 
filters and produces the associated magnitude values and flux density values. 
One can define a variety of spectral shapes and normalizations.  The code can 
also be used non-interactively.  The code is closely related to colcor.py.  
I am changing it to not plot the spectra by default and to make the normalization 
more flexible.  The main wish is to add WISE/Spitzer IRAC normalization because 
that is likely to be important for science programs.

The flux density to be used here is the photon mean flux density, with the 
pivot wavelength used to set the associated wavelength.

The code allows selectrion of the A0V spectral shape from a Sirius simulated 
spectrum or two versions of the Vega simulated spectrum.

"""

from __future__ import print_function
from __future__ import division
import matplotlib 
matplotlib.use('TkAgg')
import matplotlib.pyplot as pyplot
import sys
import os
import math
import bisect
import Tkinter as Tk
import ttk
from ScrolledText import ScrolledText
import tkFileDialog
import tkMessageBox
import numpy 
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2TkAgg
from matplotlib.figure import Figure
import astropy.io.fits as fits
import glob

def getWavelengths(filterwl,filter,vegawl,vegafl):
  logwl=numpy.log(filterwl)
  freq=299792458./(filterwl*1.e-06)
  vegafl1=numpy.interp(filterwl,vegawl,vegafl)
  v1=numpy.trapz(filter*filterwl,x=filterwl)
  v2=numpy.trapz(filter/filterwl,x=filterwl)
  pivot=math.sqrt(v1/v2)
  v3=numpy.trapz(filter,x=filterwl)
  meanwl=v1/v3
  v4=numpy.trapz(filter*filterwl*filterwl,x=filterwl)
  photonmeanwl=v4/v1
  frev=numpy.copy(filter[::-1])
  lrev=numpy.copy(logwl[::-1])
  frrev=numpy.copy(freq[::-1])
  v5=numpy.trapz(lrev*frev/frrev,x=frrev)
  v6=numpy.trapz(frev/frrev,x=frrev)
  sdsseffwl=math.exp(v5/v6)
  v7=numpy.trapz(filterwl*vegafl1*filter,x=filterwl)
  v8=numpy.trapz(vegafl1*filter,x=filterwl)
  fluxmeanwl=v7/v8
  v9=numpy.trapz(filterwl*filterwl*vegafl1*filter,x=filterwl)
  photonfluxmeanwl=v9/v7
  lastfraction=0.
  hunt=True
  for n in range(len(filterwl)):
    if n > 0 & hunt:
      wlfraction=numpy.copy(filterwl[0:n])
      filterfraction=numpy.copy(filter[0:n])
      partial=numpy.trapz(filterfraction,x=wlfraction)
      fraction=partial/v3
      if fraction >= 0.5:
        if lastfraction < 0.5:
          hunt=False
          wlmin=wlfraction[-2]
          wlmax=wlfraction[-1]
          central=wlmin+(wlmax-wlmin)*(0.5-lastfraction)/(fraction-lastfraction)
          lastfraction=fraction
      else:
        lastfraction=fraction
  filterpeak=numpy.max(filter)
  threshold=filterpeak*0.5
  inds=numpy.where(filter >= threshold)
  ind1=inds[0][0]-1
  ind2=inds[0][-1]
  fwhmwlmin=filterwl[ind1]+(threshold-filter[ind1])*(filterwl[ind1+1]-filterwl[ind1])/(filter[ind1+1]-filter[ind1])
  fwhmwlmax=filterwl[ind2]+(threshold-filter[ind2])*(filterwl[ind2+1]-filterwl[ind2])/(filter[ind2+1]-filter[ind2])
  fwhm=fwhmwlmax-fwhmwlmin
  values=numpy.zeros((11),dtype=numpy.float32)
  values[0]=central
  values[1]=pivot
  values[2]=meanwl
  values[3]=photonmeanwl
  values[4]=sdsseffwl
  values[5]=fluxmeanwl
  values[6]=photonfluxmeanwl
  values[7]=fwhm
  values[8]=fwhmwlmin
  values[9]=fwhmwlmax
  values[10]=filterpeak
  return values

def getFluxes(filterwl,filter,spectrumwl,spectrum,flag,refwl,fwhm):
  if flag:
    filterwl1=numpy.copy(spectrumwl)
    filter1=numpy.interp(spectrumwl,filterwl,filter)
    spectrumwl1=numpy.copy(spectrumwl)
    spectrum1=numpy.copy(spectrum)
  else:
    filterwl1=numpy.copy(filterwl)
    filter1=numpy.copy(filter)
    spectrumwl1=numpy.copy(filterwl)
    spectrum1=numpy.interp(filterwl,spectrumwl,spectrum)
  v1=numpy.trapz(filter1,x=filterwl1)
  v2=numpy.trapz(filter1*spectrum1,x=filterwl1)
  freq=299792458./(filterwl1*1.e-06)
  spectrum2=spectrum1*spectrumwl1*1.e+26/freq
  v3=numpy.trapz(filter1*spectrum2,x=filterwl1)
  spectrum3=spectrum1*spectrumwl1
  v4=numpy.trapz(filter1*spectrum3,x=filterwl1)
  values=numpy.zeros((7),dtype=numpy.float32)
  values[0]=numpy.interp(refwl,spectrumwl1,spectrum1)
  values[1]=numpy.interp(refwl,spectrumwl1,spectrum2)
  values[2]=numpy.interp(refwl,spectrumwl1,spectrum3)
  values[3]=v2/v1
  values[4]=v3/v1
  values[5]=v4/v1
  values[6]=v1/fwhm
  return values

def getPhoenixNames(phoenixpath):
  filelist=glob.glob(phoenixpath+'lte*.fits')
  list=[]
  for file in filelist:
    file=file.strip(phoenixpath)
    file=file.strip('lte')
    parts=file.split('.PHOENIX')
    values=parts[0].split('-')
    if len(values) == 3:
      label='T='+values[0]+' K log(g)='+values[1]
    else:
      v1=values[0].split('+')
      label='T='+v1[0]+' K log(g)= -'+v1[1]
    list.append(label)
  return list,filelist

def parseList(filename):
  list=[]
  infile=open(filename,'r')
  lines=infile.readlines()
  infile.close()
  for line in lines:
    line=line.strip('\n')
    values=line.split()
    label='T = '+values[7]+' log(g) = '+values[10]+' z = '+values[13]
    list.append(label)
  return list

bgcol='#F8F8FF'
otearea=25.326
h=6.62606957e-34
c=299792458.
# The following are suitable for the witserv computers
#
# phoenixpath='/ifs/jwst/wit/niriss/kevin/phoenix_grid/'
# etcpath='/home/kvolk/kevin_nis1/colcor/'
# path='/home/kvolk/kevin_nis1/colcor/'
#
#phoenixpath='/Users/kvolk/work/niriss/stellar_models/phoenix_grid/'
#etcpath='/Users/kvolk/work/niriss/standard_throughput/'
#path='/Users/kvolk/work/niriss/simulations/colcor/'
try:
  phoenixpath=os.environ['NIRISS_PHOENIX_PATH']
except:
  phoenixpath='./'
try:
  path=os.environ['NIRISS_MAGNITUDES_PATH']
except:
  path='./'
try:
  etcpath=os.environ['NIRISS_THROUGHPUT_PATH']
except:
  etcpath='./'
if not (path[-1] is '//'):
  path=path+'/'
if not (path[-1] is '//'):
  phoenixpath=phoenixpath+'/'
if not (path[-1] is '//'):
  etcpath=etcpath+'/'
oldkuruczlist=parseList(path+'oldkurucz.list')
newkuruczlist=parseList(path+'newkurucz.list')
phoenixlabels,phoenixlist=getPhoenixNames(phoenixpath)

class Magnitude(Tk.Frame):
  def __init__(self,parent=None,**args):
    self.filterNames=['NIRISS F090W','NIRISS F115W','NIRISS F140M','NIRISS F150W','NIRISS F158M','NIRISS F200W','NIRISS F277W','NIRISS F356W','NIRISS F380M','NIRISS F430M','NIRISS F444W','NIRISS F480M']
    self.wavelengths=[]
    self.throughputs=[]
    self.zeromagjy=[]
    self.filterwavel=[]
    self.filterValues=None
    self.vegamag=[]
    self.siriusmag=[]
    self.sprange=[0.,0.,0.,0.]
    self.plotWindow=None
    self.inputFilename1=None
    self.inputFilename2=None
    self.inputFilename3=None
    self.spectrum=False
    self.norescale=False
    self.controlWindow=None
    self.standardSpectrum=None
    self.inputSpectrum=None
    self.fl=None
    self.fnu=None
    self.lfl=None
    self.nfilters=12
    flag=self.readNIRISSValues()
    if not flag:
      print('Error: unable to read in the NIRISS throughput values.  Exiting.')
      sys.exit()
    flag=self.readFilterProfiles()
    if not flag:
      print('Error: unable to read in the non-NIRISS filter throughput values.  Exiting.')
      sys.exit()
    if parent is None:
      self.showgui=False
      status=self.parseArgv()
      if status:
        self.generateSpectrum()
        self.standardValues()
        self.getSpectrum()
        if self.nrmflag:
          self.calculateNRMMagnitudes()
        else:
          self.calculateMagnitudes()
        if self.magnitudes:
          self.otherlMagnitudes()
        if self.writeFlag:
          self.writeSpectrum()
      else:
        print("Error: could not parse the parameters.  Exiting.")
      sys.exit()
    else:
      self.showgui=True
      Tk.Frame.__init__(self,parent,args)
      self.plotButtons=[]
      self.makeWidgets()

  def putMessage(self,str1):
    self.messageText.insert(Tk.END,str1+'\n')
    self.messageText.see(Tk.END)

  def makeRangeFields(self,root,fields):
    entries=[]
    holder=Tk.Frame(root)
    holder.config(bg=bgcol)
    for i in range(len(fields)):
      j=int(i/2)
      k=i-2*j
      row=Tk.Frame(holder)
      row.config(bg=bgcol)
      lab=Tk.Label(row,text=fields[i],width="5")
      lab.config(bg=bgcol)
      ent=Tk.Entry(row,width="10")
      row.grid(column=j,row=k,sticky=Tk.W)
      lab.pack(side=Tk.LEFT)
      ent.pack(side=Tk.RIGHT)
      entries.append(ent)
    holder.pack(side=Tk.TOP)
    return entries

  def readFilterProfiles(self):
    try:
      flag1=self.readGuider(path+'guider1_throughput.fits','Guider 1')
      flag2=self.readGuider(path+'guider2_throughput.fits','Guider 2')
      if flag1 and flag2:
        self.nfilters=self.nfilters+2
      else:
        print('Error reading in the Guider response functions')
        return False
    except:
      print('Error reading in the Guider response functions')
      return False
    try:
      flag1=self.readJWST(path+'nircam_filter_throughputs.out','NIRCam ')
      flag2=self.readJWST(path+'miri_filter_throughputs.out','MIRI ')
      if flag1 and flag2:
        self.nfilters=self.nfilters+29+9
      else:
        print('Error: the NIRCam/MIRI filter profiles could not be read in.')
        return False
    except:
      print('Error: the NIRCam/MIRI filter profiles could not be read in. [2]')
      return False
    try:
      filterfile=open(path+"non_jwst_filters.data","r")
      flag=self.readFilters(filterfile)
      filterfile.close()
      if not flag:
        print('Error: the non-JWST filter profiles could not be read in.')
        return False
    except:
      print('Error: the non-JWST filter profiles could not be read in.')
      return False
    return True
    
  def parseArgv(self):
    self.xmag=15.0
    self.writeFlag=False
    self.zeromagpar=2
    self.microns=0
    self.magnitudes=False
    self.extinction=0.
    self.avflag=1
    self.normwl=0.
    self.normflux=0.
    j= -10
    self.magnumber=1
    self.renormmode=1
    self.microns=1
    self.nrmflag=False
    for i in range(len(sys.argv)):
      if 'magnitudes.py' in sys.argv[i]:
        j=i
      if '-magnitudes' in sys.argv[i]:
        self.magnitudesFlag=True
      if '-noscale' in sys.argv[i]:
        self.renormmode=0
      if '-abmag' in sys.argv[i]:
        self.renormmode=2
      if '-normfnu' in sys.argv[i]:
        try:
          normwl=float(sys.argv[i+1])
          normflux=float(sys.argv[i+2])
          if (normwl > 0.) & (normflux > 0.):
            self.renormmode=3
            self.normwl=normwl
            self.normflux=normflux
        except:
          pass
      if '-normflambda' in sys.argv[i]:
        try:
          normwl=float(sys.argv[i+1])
          normflux=float(sys.argv[i+2])
          if (normwl > 0.) & (normflux > 0.):
            self.renormmode=4
            self.normwl=normwl
            self.normflux=normflux
        except:
          pass
      if '-normlfl' in sys.argv[i]:
        try:
          normwl=float(sys.argv[i+1])
          normflux=float(sys.argv[i+2])
          if (normwl > 0.) & (normflux > 0.):
            self.renormmode=3
            self.normwl=normwl
            self.normflux=normflux
        except:
          pass
      if '-nrm' in sys.argv[i]:
        self.nrmflag=True
      if '-factor' in sys.argv[i]:
        try:
          v1=float(sys.argv[i+1])
          if v1 > 0.:
            self.factor=v1
        except:
          pass
      if '-angstroms' in sys.argv[i]:
        self.microns=0
      if '-lfl' in sys.argv[i]:
        self.lfl=1
        self.fl=0
        self.fnu=0
      if '-fnu' in sys.argv[i]:
        self.fnu=1
        self.fl=0
        self.lfl=0
      if '-oldvega' in sys.argv[i]:
        self.zeromagpar=0
      if '-newvega' in sys.argv[i]:
        self.zeromagpar=1
      if '-spectrum' in sys.argv[i]:
        self.spectrum=True
      if '-normmag' in sys.argv[i]:
        try:
          self.magnumber=int(sys.argv[i+1])
        except:
          pass
      if '-extinction' in sys.argv[i]:
        try:
          value=float(sys.argv[i+1])
          if (value > 0.) & (value < 200.):
            self.extinction=value
        except:
          pass
      if '-av' in sys.argv[i]:
        self.avflag=0
      if '-spectrum' in sys.argv[i]:
        self.writeFlag=True
    if j < 0 or (self.lfl == 1 and self.fnu == 1) or ((self.magnumber < 1 or self.magnumber > 130) and (self.renormmode == 1 or self.renormmode == 2)):
      print("Error parsing the command line arguments.  Exiting. (1)")
      return False
    else:
      options=['powerlaw','blackbody','oldkurucz','newkurucz','phoenix','phmodel','BOSZ','input']
      try:
        self.xmag=float(sys.argv[j+1])
        self.option=sys.argv[j+2]
        self.parameter=sys.argv[j+3]
      except:
        print("Error parsing the command line arguments.  Exiting. (2)")
        return False
      if not self.option in options:
        print("Error: unrecognised spectrum type entered (%s).  Exiting." % (self.option))
        return False
      else:
        for i in range(len(options)):
          if self.option == options[i]:
            self.spectrumOption=i
      if self.spectrumOption < 2:
        try:
          value=float(self.parameter)
          if value < 4. and self.spectrumOption == 1:
            print("Error: bad blackbody temperature specified.  Exiting.")
            return False
          else:
            self.parameter=value
        except:
          print("Error: bad parameter value specified.  Exiting.")
          return False
      if self.spectrumOption > 1 and self.spectrumOption < 4:
        nmodel=int(self.parameter)
        if (self.spectrumOption == 1 and (nmodel < 1 or nmodel > 412)) or (self.spectrumOption == 2 and (nmodel < 1 or nmodel > 3808)):
          print("Error: band Kurucz model number entered.  Exiting.")
          return False
        else:
          self.parameter=nmodel
      if self.spectrumOption == 5:
        found=False
        for n in range(len(phoenixlist)):
          if not found:
            if self.parameter in phoenixlist[n]:
              self.parameter=n
              found=True
        if not found:
          print("Error: phoenix grid model name not recognised.  Exiting.")
          return False
      if self.spectrumOption == 4 or self.spectrumOption > 5:
        if not os.path.isfile(self.parameter):
          print("Error: file %s was not found.  Exiting" % (self.parameter))
          return False
    return True

  def readNIRISSValues(self):
# Read in the NIRISS throughputs and assemble the filter by filter values.
# The wavelengths and throughouts are appended to self.wavelengths and
# self.throughputs.  For NIRISS the photon yield and quantum efficiency are
# included.
#
    try:
      filenames=['jwst_telescope_ote_throughput_nis.fits',
                 'jwst_niriss_internaloptics_throughput.fits',
                 'jwst_niriss_h2rg_qe.fits',
                 'jwst_niriss_internaloptics-clear_throughput.fits',
                 'jwst_niriss_internaloptics-clearp_throughput.fits',
                 'jwst_niriss_f090w_trans.fits',
                 'jwst_niriss_f115w_trans.fits',
                 'jwst_niriss_f140m_trans.fits',
                 'jwst_niriss_f150w_trans.fits',
                 'jwst_niriss_f158m_trans.fits',
                 'jwst_niriss_f200w_trans.fits',
                 'jwst_niriss_f277w_trans.fits',
                 'jwst_niriss_f356w_trans.fits',
                 'jwst_niriss_f380m_trans.fits',
                 'jwst_niriss_f430m_trans.fits',
                 'jwst_niriss_f444w_trans.fits',
                 'jwst_niriss_f480m_trans.fits',
                 'jwst_niriss_nrm_trans.fits']
      n=len(filenames)
      file1=fits.open(etcpath+filenames[0])
      tabledata=file1[1].data
      nirissWavelengths=tabledata['WAVELENGTH']
      file1.close()
      s1=nirissWavelengths.shape
      m=s1[0]
      indata=numpy.zeros((m,n+1),dtype=numpy.float32)
      loop=0
      for i in range(n):
        file1=fits.open(etcpath+filenames[i])
        tabledata=file1[1].data
        throughput=tabledata['THROUGHPUT']
        indata[:,loop]=numpy.copy(throughput)
        loop=loop+1
        if i == 2:
          throughput=tabledata['CONVERSION']
          indata[:,loop]=numpy.copy(throughput)
          loop=loop+1
# add in the CLEARP throughput value, from the header of the clearp file
        if i == 4:
          h1=file1[1].header
          clearpfactor=h1['MASKSCAL']
# add in the NRM throughput value, from the header of the nrm file
        if i == n-1:
          h1=file1[1].header
          nrmfactor=h1['MASKSCAL']
        file1.close()
# indata[:,3] is the photon yield.
      indata[:,5]=indata[:,5]*clearpfactor
      generalThroughput=indata[:,0]*indata[:,1]
      qe=numpy.copy(indata[:,2])
      py=numpy.copy(indata[:,3])
      for n in range(12):
        if n < 6:
          resp1=generalThroughput*indata[:,6+n]*indata[:,4]
        else:
          resp1=generalThroughput*indata[:,6+n]*indata[:,5]
        resp1=resp1*qe*py
        self.throughputs.append(resp1)
        self.wavelengths.append(nirissWavelengths)
        self.zeromagjy.append(0.)
        self.filterwavel.append(0.)
        self.vegamag.append(0.03)
        self.siriusmag.append(-1.415)
      indata=0.
      self.nrmCorrection=nrmfactor/clearpfactor
      return True
    except:
      return False

  def readJWST(self,filename,prefix):
    try:
      infile=open(filename,'r')
      line=infile.readline()
      line=line.replace('#',' ')
      str1=line.split()
      filternames=str1[1:]
      line=infile.readline()
      infile.close()
      line=line.replace('#',' ')
      str1=line.split()
      values=numpy.loadtxt(filename)
      s1=values.shape
      nfilters=s1[1]-1
      nvalues=s1[0]
      filwl=numpy.zeros((nfilters),dtype=numpy.float32)
      for i in range(nfilters):
        filwl[i]=float(str1[i])
        filternames[i]=prefix+filternames[i]
      wavelengths=numpy.copy(values[:,0])
      for n in range(nfilters):
        self.wavelengths.append(wavelengths)
        resp1=numpy.copy(values[:,n+1])
        self.throughputs.append(resp1)
        self.zeromagjy.append(0.)
        self.filterwavel.append(0.)
        # For NIRCam and MIRI I assumed Vega defined magnitude 0.0, not 0.03 as with NIRISS
        self.vegamag.append(0.0)
        self.siriusmag.append(-1.415)
        self.filterNames.append(filternames[n])
      return True
    except:
      return False

  def readGuider(self,filename,label):
    try:
      s1=fits.open(filename)
      tab1=s1[1].data
      s1.close
      wl1=tab1['WAVELENGTH']
      tp1=tab1['THROUGHPUT']
      self.wavelengths.append(wl1)
      self.throughputs.append(tp1)
      self.zeromagjy.append(0.)
      self.filterwavel.append(0.)
      self.vegamag.append(0.03)
      self.siriusmag.append(-1.415)
      self.filterNames.append(label)
      return True
    except:
      return False
    
  def readFilters(self,filterfile):
    try:
      lines=filterfile.readlines()
      nvals=numpy.zeros((0),dtype=numpy.int32)
      names=[]
      filwl=numpy.zeros((0),dtype=numpy.float32)
      zeromag=numpy.zeros((0),dtype=numpy.float32)
      zeromagjy=numpy.zeros((0),dtype=numpy.float32)
      vegamag=numpy.zeros((0),dtype=numpy.float32)
      i1=0
      nmax=0
      for i in range(len(lines)):
        line=lines[i].strip("\n")
        if "##" in line:
          i2=i
          nvals=numpy.append(nvals,i2-i1)
          if nvals[-1] > nmax:
            nmax=nvals[-1]
          i1=i+1
          values=line.split("|")
          names.append(values[1].lstrip(" "))
          values=line.split()
          filwl=numpy.append(filwl,float(values[1]))
          f0=float(values[2])
          zeromagjy=numpy.append(zeromagjy,f0)
          f0=1.e-26*f0*299792458./(1.e-06*filwl[-1]*filwl[-1])
          zeromag=numpy.append(zeromag,f0)
          vegamag=numpy.append(vegamag,float(values[3]))
      shape=(len(zeromag),nmax)
      wavel=numpy.zeros(shape,dtype=numpy.float)
      response=numpy.zeros(shape,dtype=numpy.float)
      npoints=numpy.zeros(len(zeromag),dtype=numpy.int16)
      j=0
      k=0
      for i in range(len(lines)):
        if "##" in lines[i]:
          j=j+1
          npoints[j-1]=k
          k=0
        else:
          try:
            line=lines[i].strip("\n")
            values=line.split()
            wavel[j,k]=float(values[0])
            response[j,k]=float(values[1])
            k=k+1
          except:
            print("Error trying to read in the non-JWST filter values.")
            return False
      for n in range(len(zeromag)):
        self.wavelengths.append(numpy.copy(wavel[n,0:npoints[n]]))
        self.throughputs.append(numpy.copy(response[n,0:npoints[n]]))
        self.zeromagjy.append(zeromagjy[n])
        self.filterwavel.append(filwl[n])
        self.vegamag.append(vegamag[n])
        self.siriusmag.append(-1.415)
        self.filterNames.append(names[n])
      return True
    except:
      return False

  def onExit(self):
    self.quit()
  
  def makeWidgets(self): 
# First generate the controls at left
    outframe=Tk.Frame(root)
    outframe.pack(side=Tk.LEFT,fill=Tk.Y,expand=1)
    inframe=Tk.Frame(outframe)
    inframe.pack(side=Tk.TOP)
    lab=Tk.Label(inframe,text=' ',height=5,width=10)
    lab.pack()
    Tk.Button(inframe,text="Define Spectrum",command=self.defineSpectrum).pack(fill=Tk.X)
    sep1=self.sepLine(inframe,200,10,10)
    sep1.pack()
    Tk.Label(inframe,text="A0V Template Spectrum:").pack()
    self.zeroMagOption=Tk.IntVar()
    Tk.Radiobutton(inframe,text='Bohlin Vega (2012)',variable=self.zeroMagOption,value=0,command=self.recalculate).pack()
    Tk.Radiobutton(inframe,text='Bohlin Vega (2014)',variable=self.zeroMagOption,value=1,command=self.recalculate).pack()
    Tk.Radiobutton(inframe,text='Bohlin Sirius',variable=self.zeroMagOption,value=2,command=self.recalculate).pack()
    self.zeroMagOption.set(2)
    sep1=self.sepLine(inframe,200,10,10)
    sep1.pack()
    self.calculateButton=Tk.Button(inframe,text="NIRISS Magnitudes",command=self.calculateMagnitudes,state=Tk.DISABLED)
    self.calculateButton.pack(fill=Tk.X)
    self.calculateNRMButton=Tk.Button(inframe,text="NIRISS NRM Magnitudes",command=self.calculateNRMMagnitudes,state=Tk.DISABLED)
    self.calculateNRMButton.pack(fill=Tk.X)
    self.allMagnitudesButton=Tk.Button(inframe,text="All Magnitudes",command=self.otherMagnitudes,state=Tk.DISABLED)
    self.allMagnitudesButton.pack(fill=Tk.X)
    self.effectiveWavelengthsButton=Tk.Button(inframe,text="Effective Wavelengths",command=self.effectiveWavelengths,state=Tk.DISABLED)
    self.effectiveWavelengthsButton.pack(fill=Tk.X)
    self.writeSpectrumButton=Tk.Button(inframe,text="Write Spectrum",command=self.writeSpectrum,state=Tk.DISABLED)
    self.writeSpectrumButton.pack(fill=Tk.X)
    self.plotSpectrumButton=Tk.Button(inframe,text="Plot Spectrum",command=self.plotSpectrum,state=Tk.DISABLED)
    self.plotSpectrumButton.pack(fill=Tk.X)
    Tk.Button(inframe,text="List Filters",command=self.listFilters).pack(fill=Tk.X)
    Tk.Button(inframe,text="Help",command=self.listHelp).pack(fill=Tk.X)
    Tk.Button(inframe,text="Close Widget",command=self.onExit).pack(fill=Tk.X)
# Second generate the meessage area at right
    holder=Tk.Frame(root)
    holder.pack(side=Tk.LEFT,fill=Tk.Y,expand=1)
    self.messageText=ScrolledText(holder,height=50,width=80,bd=1,relief=Tk.RIDGE,wrap=Tk.NONE)
    self.messageText.config(font=('courier',16,'bold'))
    self.messageText.pack()
    shorthelp="""
The GUI allows one to define a spectral shape (a power law, a blackbody, a 
stellar model read in from a file, or a spectrum read in from an input file) 
and then calculate the NIRISS filter magnitudes, count rates, and standard flux 
densities.  Approximate filter magnitudes for other instruments/filters 
can also be calculated.  Any of these magitudes can be used for normalization 
of the spectrum in the simulation, or one can specify the flux density at a 
specific wavelength.

  The simulation depends on an standard A0V spectral shape that is assumed to 
define the same magnitude in the NIRISS filters.  The standard A0V spectral 
shape is assumed to be from on the Calspec spectra used by the Hubble Space 
Telescope.  See Bohlin (2014) for a discussion of the models of the spectra 
for these two stars.  In addition to the 2014 versions of the Sirius and Vega 
model specta, the previous 2012 Calspec model spectrum for Vega is also 
provided as an option for comparison.

  The simulated magnitudes here are expected to be accurate to 2% or so in nost
cases, but the user needs to view them with some caution.  There are 
uncertainties in the throughputs, and in any case one cannot exactly simulate 
real magnitudes on the computer.  
 
"""
    self.messageText.insert(0.0,shorthelp)
    self.generateSpectrum()
    self.standardValues()

  def listHelp(self):
    longerhelp="""

  The accuracy of the simulation of these other magnitudes depends on a number 
of factors, so the user may need to be cautious about how to do the 
normalization when magnitudes are being used.  In many instances the magnitude 
simulation is limited by uncertainties in the details of the filter profile.  
In any case it is not a given that working with the published filter profiles 
is sufficient to simulate magnitudes because in real photometry one has 
atmospheric effects as well as variations in the filter properties from one 
telescope to the next.  The process of atmospheric extinction corrections and 
standardization of photometry takes out these factors to some degree od 
accuracy, but we are not attempting to duplicate this on computer.  The "Vega 
magnitudes" depend on the mean colours of A0V stars for real photometric 
systems, not just on Vega or any other individual star.  In this simulation we 
have to assume that the selected A0V spectral template is "average".  If we 
were intending to duplicate the photometric systems we would need to simulate 
the A0V standards used and average over the results of the calculations.  For 
NIRISS or the other JWST instruments where no on-sky observations have been 
taken this is clearly not possible.  Hence we use the simpler approximation of 
a standard A0V spectral shape, but this introduces systematic errors into the 
simulated photometry.  Let the user be wary of the results.  They agree fairly 
well with tabulated standard colours for different spectral types, but the 
agreement is not perfect by any means.

  Magnitudes are defined via one of three methods:

(1) For the JWST filters, the count rates in electrons/s are calculated from 
available photon conversion efficiency functions, and the count rate from 
the source is compared to the count rate from the standard A0V spectrum to
calculate the magnitudes.  Note that the 2014 Vega model is assumed to define 
magnitude 0.0 for the NIRCam and MIRI filters but for NIRISS it is assumed to 
defined magnitude +0.03 (to have colours of zero with respect to the V 
magnitude).  This produces a 0.03 magnitude offset between NIRISS and NIRCam 
in the equivalent filters.

(2) For the non-JWST filters, all save the Sloan filters use the in-band flux 
for the standard A0V spectrum compared to that for the specfied source to 
define the spectrum.  The assumed magnitude of Vega is either 0.0 or 0.03 
depending on the filter under consideration.  

(3) For the Sloan filters the magnitude is calculated from the flux density 
following the equations given in Convey et al. (2007), and so these values 
are less accurate than the other simulated magnitudes.

  When Sirius is used to define the A0V spectral shape it is taken to have a 
magnitude of -1.415 in all fitlers.

  Note that Vega has an intrinsic V - K value of 0.066 magnitudes according to 
Rieke et al. (2008), and with V = 0.03 this means K is -0.036.  Sirius has a V 
magnitude of -1.415 according to Cousins (1967).  These magnitudes appear to be 
the best determined values, but they are inconsistent with various normally 
quoted magnitudes for these stars.  At K-band Sirius is 1.37 magnitudes 
brighter than Vega, so nominally it would have K = -1.406 from the above 
Vega K magnitude.  In that case, Sirius has V - K close to zero magnitudes.  
Vega is sometimes assumed to have magnitude 0.0 in the near-infrared filters.  
All these competing values mean that there may be global offsets between the 
magnitudes calculated here and values in the literature.  The user is warned 
to be careful about the simulated magnitudes.  The relative values should be 
good to roughly 2% in most cases, aside from any global magnitude offsets.

  For the JWST filters the flux density that is reported is a mean flux density 
that does not correpsond to the actual flux density at a given wavelength for 
all objects.  Hence when one normalizes by flux density at a particular 
wavelength this differs fundamentally from normlaizing by magnitude.

  The simulated zero magnitude count rates for the NIRISS filters when 
the Vega 2014 A0V template is used are:

  F090W      1.25089e+11
  F115W      1.06102e+11
  F140M      3.34648e+10
  F150W      6.36177e+10
  F158M      2.97536e+10
  F200W      4.42364e+10
  F277W      2.58772e+10
  F356W      1.70891e+10
  F380M      3.08114e+09
  F430M      2.00388e+09
  F444W      1.04790e+10
  F480M      1.79532e+09

The correponding values for Sirius A0V template are

  F090W      1.22526e+11
  F115W      1.02554e+11
  F140M      3.20748e+10
  F150W      6.08009e+10
  F158M      2.83481e+10  
  F200W      4.18173e+10
  F277W      2.43535e+10
  F356W      1.60248e+10
  F380M      2.88711e+09
  F430M      1.87446e+09
  F444W      9.79995e+09
  F480M      1.67781e+09

Finally the corresponding values for the Vega 2012 A0V template are

  F090W      1.25814e+11
  F115W      1.06717e+11
  F140M      3.36712e+10
  F150W      6.39956e+10
  F158M      2.99256e+10
  F200W      4.44934e+10
  F277W      2.60268e+10
  F356W      1.71881e+10
  F380M      3.09909e+09
  F430M      2.01550e+09
  F444W      1.05396e+10
  F480M      1.80572e+09


"""
    self.messageText.insert(0.0,longerhelp)

  def recalculate(self):
    self.generateSpectrum()
    self.standardValues()
    if self.spectrum:
      self.getSpectrum()
    return

  def writeSpectrum(self):
    if not self.spectrum:
      if self.showgui:
        self.putMessage('Error: no spectrum has been defined.')
      return
    outfile=open('scaled_spectrum.txt','w')
    fnu=self.otherSpectrum*self.otherWavelengths*self.otherWavelengths*1.e+20/299792458.
    str1='# Model Spectrum: %s\n# %s\n# Normalization: %s\n# ' % (self.spectrumLabel,self.extinctionLabel,self.renormLabel)
    print(str1,file=outfile)
    print('# Wavelength (microns)   F_lambda (W/m^2/micron)   F_nu (Jy)',file=outfile)
    for n in range(len(self.otherWavelengths)):
      print('%15.8f %13.6e %13.6e' % (self.otherWavelengths[n],self.otherSpectrum[n],fnu[n]),file=outfile)
    outfile.close()
    if self.showgui:
      self.putMessage('The spectrum has been written to scaled_spectrum.txt')
    outfile=open('scaled_spectrum_etc.txt','w')
    fnu=fnu*1.e+03
    for n in range(len(self.otherWavelengths)):
      print('%15.8f %13.6e' % (self.otherWavelengths[n],fnu[n]),file=outfile)
    outfile.close()
    return
  
  def plotSpectrum(self):
    if self.plotWindow is None:
      self.plotWindow=Tk.Toplevel()
      self.plotWindow.title('Assumed Spectral Shape Window')
      inframe=Tk.Frame(self.plotWindow)
      inframe.pack(side=Tk.LEFT)
      self.mplspectfig=Figure(figsize=(5,5), dpi=100)
      self.mplspectfig.subplots_adjust(left=0.16)
      self.mplspectsubplot=self.mplspectfig.add_subplot(1,1,1)
      self.SpectPosLabelText=Tk.StringVar()
      self.SpectPosLabel=Tk.Label(inframe,textvariable=self.SpectPosLabelText)
      self.SpectPosLabel.pack(side=Tk.TOP) 
      self.SpectPosLabelText.set("Position:\n")
      self.spectcanvas=FigureCanvasTkAgg(self.mplspectfig,master=inframe)
      self.spectcanvas.show()
      self.spectcanvas.mpl_connect("motion_notify_event",self.setSpectPlotPosition)
      self.spectcanvas.get_tk_widget().pack(side=Tk.TOP,fill=Tk.BOTH,expand=Tk.YES)
      frame1=Tk.Frame(self.plotWindow)
      frame1.pack(side=Tk.LEFT)
      self.spectPlotRangeLabel=Tk.Label(frame1,text="Plot Controls",font=("times",14,"bold"),foreground="blue",bg=bgcol)
      self.spectPlotRangeLabel.pack()
      fields="xmin","xmax","ymin","ymax"
      self.spectEntries=self.makeRangeFields(frame1,fields)
      self.spectLineSize=Tk.DoubleVar()
      self.spectLineScale=Tk.Scale(frame1,orient=Tk.HORIZONTAL,to=3.0,from_=0.0,tickinterval=0.5,resolution=0.01,variable=self.spectLineSize,command=self.setSpectLineSize,length=250,label="Plot Line Width")
      self.spectLineScale.pack(side=Tk.TOP)
      self.spectLineScale.set(1.0)
      buttonframe=Tk.Frame(frame1)
      buttonframe.pack(side=Tk.TOP)
      Tk.Button(buttonframe,text="Apply Range",command=self.applySpectRange,width=12).grid(column=0,row=0)
      Tk.Button(buttonframe,text="Autoscale Plot",command=self.autoScaleSpect,width=12).grid(column=1,row=0)
      Tk.Button(buttonframe,text="Save as PS",command=self.makeSpectPS,width=12).grid(column=0,row=1)
      Tk.Button(buttonframe,text="Save as PNG",command=self.makeSpectPNG,width=12).grid(column=1,row=1)
      Tk.Button(buttonframe,text="Close Window",command=self.plotWindow.withdraw,width=12).grid(column=1,row=3)
#      Tk.Button(buttonframe,text="Recalculate",command=self.makeSpectPlot,width=12).grid(column=0,row=3)
    else:
      self.plotWindow.deiconify()
    return
  
  def makeSpectPS(self):
    outfile=tkFileDialog.asksaveasfilename(filetypes=[('PS','*.ps')])
    if isinstance(outfile,type('string')):
      s1=outfile.split('.')
      if not 'ps' in s1[-1]:
        outfile=outfile+'.ps'
      self.mplspectfig.savefig(outfile,format="PS")
    
  def makeSpectPNG(self):
    outfile=tkFileDialog.asksaveasfilename(filetypes=[('PNG','*.png')])
    if isinstance(outfile,type('string')):
      s1=outfile.split('.')
      if not 'png' in s1[-1]:
        outfile=outfile+'.png'
      self.mplspectfig.savefig(outfile,format="PNG")

  def autoScaleSpect(self):
    self.mplspectsubplot.set_xbound(self.sprange[0],self.sprange[1])
    self.mplspectsubplot.set_ybound(self.sprange[2],self.sprange[3])
    for n in range(4):
      s1=self.spectEntries[n].get()
      self.spectEntries[n].delete(0,last=len(s1))
      if n < 2:
        s1='%.2f' % self.sprange[n]
      else:
        s1='%.4e' % self.sprange[n]
      self.spectEntries[n].insert(0,s1)      
    self.spectcanvas.show()

  def applySpectRange(self):
    try:
      xmin=float(self.spectEntries[0].get())
      xmax=float(self.spectEntries[1].get())
      ymin=float(self.spectEntries[2].get())
      ymax=float(self.spectEntries[3].get())
      self.mplspectsubplot.set_xbound(xmin,xmax)
      self.mplspectsubplot.set_ybound(ymin,ymax)
      self.spectcanvas.show()
    except:
      return

  def roundFloat(self,inputvalue,flag):
    if inputvalue == 0.:
      return 0.
    value=abs(inputvalue)
    if inputvalue < 0.:
      sign=-1.
    else:
      sign=1.
    power=int(math.log10(value))
    x=value/(10.**power)
    if x < 1.:
      x=x*10.
      power=power-1.
    if (flag & (sign > 0.)) | ((not flag) & (sign < 0.)):
      newvalue=math.ceil(x)
    else:
      newvalue=math.floor(x)
    return sign*newvalue*(10.**power)
    
  def makeSpectPlot(self):
    if not self.spectrum:
      return
    lw=self.spectLineSize.get()
    self.mplspectsubplot.clear()
    self.mplspectsubplot.loglog(self.otherWavelengths,self.otherSpectrum,linewidth=lw,color='blue')
    newspectrum,label=self.scaleSpectrum(self.standardWavelengths,self.standardSpectrum)
    self.mplspectsubplot.loglog(self.standardWavelengths,newspectrum,linewidth=lw,color='red')
    self.mplspectsubplot.set_title('Red: A0V spectrum Blue: Object Spectrum')
    self.mplspectsubplot.set_xlabel('Wavelength (micron)')
    self.mplspectsubplot.set_ylabel('lambda*F_lambda(W/m^2)')
    xmin,xmax=self.mplspectsubplot.get_xlim()
    ymin,ymax=self.mplspectsubplot.get_ylim()
    xt1=self.mplspectsubplot.get_xticks()
    yt1=self.mplspectsubplot.get_yticks()
    if len(xt1) > 2:
      xratio=xt1[1]/xt1[0]
      if xratio > 11.:
        e1=math.log10(xt1[0])
        e2=math.log10(xt1[-1])
        n=int(e2-e1+0.1)+1
        xt2=numpy.logspace(e1,e2,num=n)
        self.mplspectsubplot.set_xticks(xt2)
    if len(yt1) > 2:
      yratio=yt1[1]/yt1[0]
      if yratio > 11.:
        e1=math.log10(yt1[0])
        e2=math.log10(yt1[-1])
        n=int(e2-e1+0.1)+1
        yt2=numpy.logspace(e1,e2,num=n)
        self.mplspectsubplot.set_yticks(yt2)
    xmin=self.roundFloat(xmin,False)
    xmax=self.roundFloat(xmax,True)
    ymin=self.roundFloat(ymin,False)
    ymax=self.roundFloat(ymax,True)
    self.sprange[0]=xmin
    self.sprange[1]=xmax
    self.sprange[2]=ymin
    self.sprange[3]=ymax
    self.mplspectsubplot.set_xbound(xmin,xmax)
    self.mplspectsubplot.set_ybound(ymin,ymax)
    for n in range(4):
      s1=self.spectEntries[n].get()
      self.spectEntries[n].delete(0,last=len(s1))
      if n < 2:
        s1='%.2f' % self.sprange[n]
      else:
        s1='%.4e' % self.sprange[n]
      self.spectEntries[n].insert(0,s1)
    self.spectcanvas.show()

  def setSpectPlotPosition(self,event):
    if not self.plotWindow is None:
      try:
        s1="Position: %.6g %.6g" % (event.xdata,event.ydata)
        self.SpectPosLabelText.set(s1)
      except:
        pass

  def setSpectLineSize(self,scale):
    self.makeSpectPlot()
    self.spectcanvas.show()

  def hideSpectWindow(self):
    self.plotWindow.withdraw()

  def listFilters(self):
    m=-1
    outfile=open('filter_list.out','a')
    opt=self.zeroMagOption.get()
    value=self.standardSpectrum[0]
    target=[1.23811e-16,4.0015284e-15,6.6985e-15]
    for n in range(len(target)):
      ratio=value/target[n]
      if (ratio > 0.95) & (ratio < 1.05):
        m=n
    if m != opt:
      self.putMessage('Warning: The zero magnitude option does not match the spectrum values.')
      opt=m
    labels=['Bohlin Vega (2012)','Bohlin Vega (2014)','Bohlin Sirius (2014)']
    str1=u"\n# Assumed A0V spectral template: %s\n" % (labels[opt])
    str1=str1+u"# List of Simulated Filter Magnitudes\n# N Filter Name            Wavelength (\u00B5m)  Zero Magnitude Flux Density (Jy)"
    str2="# Assumed A0V spectral template: %s\n# List of Simulated Filter Magnitudes\n# N Filter Name            Wavelength (microns)  Zero Magnitude Flux Density (Jy)" % (labels[opt])
    print(str2,file=outfile)
    self.putMessage(str1)
    for n in range(len(self.filterNames)):
      str1='%3d %-25s %8.4f %20.6f' % (n+1,self.filterNames[n],self.filterwavel[n],self.zeromagjy[n])
      self.putMessage(str1)
      print(str1,file=outfile)
    outfile.close()

  def standardValues(self):
    if self.standardSpectrum is None:
      self.generateSpectrum()
    self.pivotWavelengths=[]
    self.photonMeanFluxDensities=[]
    for n in range(len(self.filterNames)):
      pwl,pmfl=self.photomValues(self.wavelengths[n],self.throughputs[n],self.standardWavelengths,self.standardSpectrum)
      self.pivotWavelengths.append(pwl)
      offset=self.rescale(0.,n)
      self.photonMeanFluxDensities.append(pmfl)
      if ("NIRISS" in self.filterNames[n]) | ("NIRCam" in self.filterNames[n]) | ("MIRI" in self.filterNames[n]) | ("Guider" in self.filterNames[n]):
        self.filterwavel[n]=pwl
        flambda=pmfl*offset
        self.zeromagjy[n]=1.e+20*pwl*pwl*flambda/299792458.
    
  def hideSpectrumWindow(self):
    self.controlWindow.withdraw()

  def generateSpectrum(self):
    if self.showgui:
      soption=self.zeroMagOption.get()
    else:
      soption=self.zeromagpar
    filenames=['alpha_lyr_stis_005.fits','alpha_lyr_mod_002.fits','sirius_mod_002.fits']
    hdulist=fits.open(path+filenames[soption])
    tab=hdulist[1].data
    # read in the values, convert to wavelength in microns, flux density in W/m^2/micron
    self.standardWavelengths=tab['Wavelength']/10000.
    self.standardSpectrum=tab['Flux']*10.
    if soption == 2:
      self.standardMagnitudes=numpy.copy(self.siriusmag)
    else:
      self.standardMagnitudes=numpy.copy(self.vegamag)
    hdulist.close()

  def getFilterFlux(self,filterwl,filterresp,spectrumwl,spectrum,photonflag):
# Calculate the mean wavelength of the filter to then see which function needs to
# be interpolated, depending on which has finer sampling at the mean filter
# wavelength.
    v1=numpy.trapz(filterwl*filterresp,x=filterwl)
    v2=numpy.trapz(filterresp,x=filterwl)
    if v1 == 0 or v2 == 0:
      wl0=(filterwl[0]+filterwl[-1])/2.
    else:
      wl0=v1/v2
    if wl0 > spectrumwl[-1] or wl0 < spectrumwl[0]:
      return 0.0
    ind=numpy.abs(filterwl-wl0).argmin()
    delwl1=filterwl[ind+1]-filterwl[ind]
    ind=numpy.abs(spectrumwl-wl0).argmin()
    delwl2=spectrumwl[ind+1]-spectrumwl[ind]
    if delwl2 < delwl1:
      newfilterresp=numpy.interp(spectrumwl,filterwl,filterresp)
      newfilterresp[spectrumwl <= filterwl[0]]=0.
      newfilterresp[spectrumwl >= filterwl[-1]]=0.
      if photonflag:
        freq=299792458./(spectrumwl*1.e-06)
        photon=6.62606957e-34*freq
        flux=numpy.trapz(spectrum*newfilterresp/photon,x=spectrumwl)
      else:
        flux=numpy.trapz(spectrum*newfilterresp,x=spectrumwl)
    else:
      newspectrum=numpy.interp(filterwl,spectrumwl,spectrum)
      if photonflag:
        freq=299792458./(filterwl*1.e-06)
        photon=6.62606957e-34*freq
        flux=numpy.trapz(newspectrum*filterresp/photon,x=filterwl)
      else:
        flux=numpy.trapz(newspectrum*filterresp,x=filterwl)
    return flux
  
  def interpolate_Kurucz(self,wavelengths,spectrum):
    newwavelengths=numpy.copy(wavelengths[0:1213])
    newspectrum=numpy.copy(spectrum[0:1213])
    ntop=1212
    power=math.log10(spectrum[ntop+1]/spectrum[ntop])/math.log10(wavelengths[ntop+1]/wavelengths[ntop])
    wl0=newwavelengths[-1]
    nmax=len(wavelengths)-2
    addwl=numpy.zeros((4750),dtype=numpy.float32)
    addsp=numpy.zeros((4750),dtype=numpy.float32)
    for n in range(4750):
      wl1=wl0+n*0.04+0.04
      if ntop < nmax and wl1 > wavelengths[ntop+1]:
        ntop=ntop+1
        power=math.log10(spectrum[ntop+1]/spectrum[ntop])/math.log10(wavelengths[ntop+1]/wavelengths[ntop])
      addwl[n]=wl1
      addsp[n]=spectrum[ntop]*math.pow(10.,power*math.log10(wl1/wavelengths[ntop]))
    newwavelengths=numpy.append(newwavelengths,addwl)
    newspectrum=numpy.append(newspectrum,addsp)
    return newwavelengths,newspectrum

  def getMagnitudeOptions(self):
    if self.showgui:
      magopt=self.normMagSelect.current()
      magvalue=float(self.magValue.get())
    else:
      magopt=self.magnumber-1
      magvalue=self.xmag
    fwl=numpy.copy(self.wavelengths[magopt])
    fresp=numpy.copy(self.throughputs[magopt])
    wlnorm=self.filterwavel[magopt]
    flnorm=self.zeromagjy[magopt]
    if magopt < 50:
      photonopt=True
    else:
      photonopt=False
    return magopt,photonopt,fwl,fresp,wlnorm,flnorm,magvalue
  
  def getSpectrum(self):
    self.spectrum=False
    self.filterValues=None
    magopt,photonopt,fwl,fresp,wlnorm,flnorm,magvalue=self.getMagnitudeOptions()
    if self.showgui:
      spectrumOption=self.buttonvar.get()
    else:
      spectrumOption=self.spectrumOption
    if spectrumOption == 0:
      otherWavelengths=numpy.copy(self.standardWavelengths)
      if self.showgui:
        power=self.plvalue.get()
      else:
        power=float(self.parameter)
      label="Power law, index = %.4f" % (power)
      otherSpectrum=numpy.power(otherWavelengths/wlnorm,power)*flnorm
    elif spectrumOption == 1:
      otherWavelengths=numpy.copy(self.standardWavelengths)
      if self.showgui:
        temperature=10.**self.tempvalue.get()
      else:
        temperature=float(self.parameter)
      label="Blackbody T = %.3f" % (temperature)
# First and second radiation constants, with wavelengths in microns not meters,
# from CODATA 2014 recommended values of the fundamental constants
      c1=3.741771790e+08
      c2=14387.7736
      c3=c2/temperature
      wlin=numpy.zeros((1),dtype=numpy.float32)
      wlin[0]=wlnorm
      factor=numpy.expm1(c2/(wlin*temperature))
      f0=(c1/numpy.power(wlin,5))/factor[0]
      scale=flnorm/f0
      exp1=c2/(self.standardWavelengths*temperature)
      otherSpectrum=scale*(c1/numpy.power(self.standardWavelengths,5))/numpy.expm1(exp1)
      overflowinds=numpy.isnan(otherSpectrum)
      otherSpectrum[overflowinds]=0.
      overflowinds=numpy.isinf(otherSpectrum)
      otherSpectrum[overflowinds]=0.
    elif spectrumOption == 2:
      values=numpy.loadtxt(path+'oldkurucz.ascii')
      otherWavelengths=numpy.copy(values[0:1221,0])
      n1=values.shape
      nmodels=int(n1[0]/1221+0.01)
      fluxes=numpy.reshape(values[:,1],(nmodels,1221))
      values=0.
      if self.showgui:
        modelnumber=self.fields[spectrumOption].current()
      else:
        modelnumber=int(self.parameter)-1
      otherSpectrum=numpy.copy(fluxes[modelnumber,:])
      label='Old Kurucz model '+oldkuruczlist[modelnumber]
      otherWavelengths,otherSpectrum=self.interpolate_Kurucz(otherWavelengths,otherSpectrum)
    elif spectrumOption == 3:
      values=numpy.loadtxt(path+'newkurucz.ascii')
      otherWavelengths=numpy.copy(values[0:1221,0])
      n1=values.shape
      nmodels=int(n1[0]/1221+0.01)
      fluxes=numpy.reshape(values[:,1],(nmodels,1221))
      values=0.
      if self.showgui:
        modelnumber=self.fields[spectrumOption].current()
      else:
        modelnumber=int(self.parameter)-1
      otherSpectrum=numpy.copy(fluxes[modelnumber,:])
      label='New Kurucz model: '+newkuruczlist[modelnumber]
      otherWavelengths,otherSpectrum=self.interpolate_Kurucz(otherWavelengths,otherSpectrum)
    elif spectrumOption == 4:
      if self.showgui:
        filename=self.fields[4].get()
        if filename in self.inputFilename1:
          filename=self.inputFilename1
      else:
        filename=self.parameter
      label='Phoenix model: '+filename
      newfilename=filename
      if '.bz2' in filename:
        os.system('bunzip2 '+filename)
        newfilename=filename.replace('.bz2','')
      if '.xz' in filename:
        os.system('unxz '+filename)
        newfilename=filename.replace('.xz','')
      infile=open(newfilename,'r')
      lines=infile.readlines()
      infile.close()
      nlines=len(lines)
      otherWavelengths=numpy.zeros((nlines),dtype=numpy.float32)
      otherSpectrum=numpy.zeros((nlines),dtype=numpy.float32)
      for n1 in range(nlines):
        values=lines[n1].split()
        otherWavelengths[n1]=float(values[0])/10000.
        otherSpectrum[n1]=10.**(float(values[1].replace('D','E')))
      if '.bz2' in filename:
        os.system('bzip2 '+newfilename)
      if '.xz' in filename:
        os.system('xz '+newfilename)
      self.highResolution=True
    elif spectrumOption == 5:
      try:
        if self.showgui:
          nmodel=self.fields[self.gridnumber].current()
        else:
          nmodel=int(self.parameter)
        filename=phoenixlist[nmodel]
        self.inputFilename=filename
        otherSpectrum=fits.getdata(self.inputFilename)
        otherWavelengths=fits.getdata(phoenixpath+'WAVE_PHOENIX-ACES-AGSS-COND-2011.fits')
# convert wavelengths to microns
        otherWavelengths=otherWavelengths/10000.
# add two long wavelength points as the coverage only goes to 5.499975 microns
        otherSpectrum=numpy.append(otherSpectrum,[0.,0.])
        otherWavelengths=numpy.append(otherWavelengths,[5.5,5.5001])
        label='Phoenix grid '+phoenixlabels[nmodel]
      except:
        if self.showgui:
          self.putMessage('Error trying to read in the Phoenix grid model.')
        return
    elif spectrumOption == 6:
      try:
        if self.showgui:
          filename=self.fields[spectrumOption].get()
          filename1=self.inputFilename2
          label=filename
          if not (filename1 is None):
            if filename in filename1:
              label=filename
              filename=filename1
        else:
          label=self.parameter
          filename=self.parameter
        if '.fits' in filename:
          s1=fits.open(filename)
          tab1=s1[1].data
          s1.close()
          otherWavelengths=numpy.copy(tab1['WAVELENGTH']/10000.)
          otherSpectrum=numpy.copy(tab1['SPECIFICINTENSITY']*10.*3.14159265359)
          tab1=0.
        if '.asc.bz2' in filename:
          os.system('bunzip2 '+filename)
          newfilename=filename.replace('.bz2','')
          otherWavelengths=numpy.loadtxt(newfilename,usecols=(0,))/10000.
          otherSpectrum=numpy.loadtxt(newfilename,usecols=(1,))*10.*3.14159265359
          os.system('bzip2 '+newfilename)
        else:
           if '.asc' in filename:
             otherWavelengths=numpy.loadtxt(filename,usecols=(0,))/10000.
             otherSpectrum=numpy.loadtxt(filename,usecols=(1,))*10.*3.14159265359
      except:
        if self.showgui:
          self.putMessage('Error trying to read in the BOSC grid model.')
        return
    elif spectrumOption == 7:
      try:
        if self.showgui:
          filename=self.fields[spectrumOption].get()
          label=filename
          if not (self.inputFilename3 is None):
            filename1=self.inputFilename3
            if filename in filename1:
              label=filename
              filename=filename1
        else:
          filename=self.parameter
          label=filename
        otherWavelengths=numpy.loadtxt(filename,usecols=(0,),comments=['#','\\','|'])
        otherSpectrum=numpy.loadtxt(filename,usecols=(1,),comments=['#','\\','|'])
        if self.showgui:
          self.microns=self.wavelengthUnits.current()
        if self.microns == 0:
          otherWavelengths=otherWavelengths/10000.
        if self.fnu == 1:
          otherSpectrum=otherSpectrum*1.e+20*otherWavelengths*otherWavelengths/299792458.
        if self.lfl == 1:
          otherSpectrum=otherSpectrum/otherWavelengths
      except:
        print('Error trying to read in the input model.')
        self.otherWavelengths=None
        self.otherSpectrum=None
        return 
# invert wavelengths, if the wavelengths are descending as in DUSTCD output files:
      if otherWavelengths[1] < otherWavelengths[0]:
        otherWavelengths=numpy.copy(otherWavelengths[::-1])
        otherSpectrum=numpy.copy(otherSpectrum[::-1])
      if not self.showgui and self.factor > 0.:
        otherSpectrum=otherSpectrum*self.factor
    else:
      self.otherSpectrum=None
      self.otherWavelengths=None
      return
    if self.showgui:
      extinction=float(self.extinctionValue.get())
    else:
      extinction=self.extinction
    if extinction > 0.:
      otherSpectrum=self.doExtinction(extinction,otherWavelengths,otherSpectrum)
    else:
      self.extinctionLabel='No ISM extinction'
    scaledOtherSpectrum,self.renormLabel=self.scaleSpectrum(otherWavelengths,otherSpectrum)
    self.spectrum=True
    self.otherWavelengths=numpy.copy(otherWavelengths)
    self.otherSpectrum=numpy.copy(scaledOtherSpectrum)
    self.spectrumLabel=label
    if showgui:
      self.calculateButton['state']=Tk.NORMAL
      self.calculateNRMButton['state']=Tk.NORMAL
      self.allMagnitudesButton['state']=Tk.NORMAL
      self.effectiveWavelengthsButton['state']=Tk.NORMAL
      self.writeSpectrumButton['state']=Tk.NORMAL
      self.plotSpectrumButton['state']=Tk.NORMAL
      self.hideSpectrumWindow()
      if not self.plotWindow is None:
        self.plotWindow.destroy()
        self.plotWindow=None
    return 

  def scaleSpectrum(self,otherWavelengths,otherSpectrum):
    outSpectrum=numpy.copy(otherSpectrum)
    magopt,photonopt,fwl,fresp,wlnorm,flnorm,magvalue=self.getMagnitudeOptions()
    flux1=self.getFilterFlux(fwl,fresp,self.standardWavelengths,self.standardSpectrum,photonopt)
    if self.showgui:
      mode=self.renormFlag.get()
    else:
      mode=self.renormmode
    if self.norescale | (mode == 0):
      renormLabel='No scaling'
      return outSpectrum,renormLabel
    else:
      if (mode == 1) | (mode == 2):
        if 'Sloan' in self.filterNames[magopt]:
          renormLabel='Sloan magnitude %f for filter %s' % ((magvalue,self.filterNames[magopt]))
          sloanfnu=self.invertSloanMagnitude(self.filterNames[magopt],magvalue)
          pivotwl,meanflambda=self.photomValues(fwl,fresp,otherWavelengths,otherSpectrum)
          meanfnu=1.e+20*pivotwl*pivotwl*meanflambda/299792458.
          rescale=sloanfnu/meanfnu
          print(sloanfnu,meanfnu,rescale)
          outSpectrum=otherSpectrum*rescale
        else:
          flux2=self.getFilterFlux(fwl,fresp,otherWavelengths,otherSpectrum,photonopt)
          if flux2 > 0.:
            rescale=flux1/flux2
            offset=self.rescale(magvalue,magopt)
            if mode == 2:
              aboffset=10.**(0.4*3631.0/self.zeromagjy[magopt])
              offset=offset*aboffset
            outSpectrum=otherSpectrum*rescale*offset
            if mode == 1:
              renormLabel='A0V magnitude %f for filter %s' % (magvalue,self.filterNames[magopt])
            else:
              renormLabel='AB Magnitude %f for filter %s' % (magvalue,self.filterNames[magopt])
          else:
            if showgui:
              self.putMessage('Error: no flux/counts in the normalization filter passband, will not scale the input spectrum.')
            renormLabel='No scaling'
        return outSpectrum,renormLabel
      if mode > 2:
        if showgui:
          normwl=float(self.normWavelengthField.get())
          normflux=float(self.normFluxField.get())
        else:
          normwl=self.normwl
          normflux=self.normflux
        if (normwl < otherWavelengths[0]) | (normwl > otherWavelengths[-1]):
          if self.showgui:
            self.putMessage('Error: the requested normalization wavelength is out of range.')
            renormLabel='No scaling'
          return outSpectrum,renormLabel
        elif normflux <= 0.:
          if self.showgui:
            self.putMessage('Error: negative or zero target flux density value.')
          renormLabel='No scaling'
          return outSpectrum,renormLabel
        else:
          flambda=numpy.interp(normwl,otherWavelengths,otherSpectrum)
          if flambda <= 0.:
            if self.showgui:
              self.putMessage('Error: negative or zero interpoalted spectrum flux density value.')
            renormLabel='No scaling'
            return outSpectrum,renormLabel
          else:
            fnu=1.e+20*normwl*normwl*flambda/299792458.
            if mode == 3:
              rescale=normflux/fnu
              renormLabel='Scaled to F_nu = %f Jy at %f microns' % (normflux,normwl)
            if mode == 4:
              rescale=normflux/flambda
              renormLabel='Scaled to F_lambda = %e W/m^2/micron at %f microns' % (normflux,normwl)
            if mode == 5:
              rescale=normflux/(normwl*flambda)
              renormLabel='Scaled to lambda*F_lambda = %e W/m^2 at %f microns' % (normflux,normwl)
            outSpectrum=otherSpectrum*rescale
        return outSpectrum,renormLabel
  
  def doExtinction(self,extinction,wavelengths,spectrum):
    try:
      extwl=numpy.loadtxt(path+'extinction.values',usecols=(0,))
      extvalues=numpy.loadtxt(path+'extinction.values',usecols=(1,))
      if self.showgui:
        extopt=self.extinctionOption.get()
      else:
        extopt=self.avflag
# Adjust if the input value is E(B - V), otherwise it is A_V matching the
# extinction file;
      if extopt == 1:
        extinction=extinction*3.52
      self.extinction=extinction
      self.extinctionLabel='ISM Extinction: A_V = %f magnitudes' % (extinction)
      extvals=numpy.interp(wavelengths,extwl,extvalues)
      e1=numpy.interp(0.55,extwl,extvalues)
      factor= 1./(numpy.power(10.,0.4*extvals*extinction))
      e1=numpy.interp(0.55,wavelengths,factor)
      spectrum1=spectrum*factor
      return spectrum1
    except:
      if self.showgui:
        self.putMessage('Error doing the extinction calculation.')
      return spectrum
      
  def rescale(self,magvalue,magopt):
    deviation=abs(1.-self.standardSpectrum[0]/6.6985e-15)
    if deviation < 0.05:
      offset=10.**(0.4*(magvalue-self.siriusmag[magopt]))
    else:
      offset=10.**(0.4*(magvalue-self.vegamag[magopt]))
    return 1./offset

  def photomValues(self,wavelengths,throughputs,spectrumwl,spectrum):
# Calculate the mean wavelength of the filter to then see which function needs to
# be interpolated, depending on which has finer sampling at the mean filter
# wavelength.
    v1=numpy.trapz(wavelengths*throughputs,x=wavelengths)
    v2=numpy.trapz(throughputs,x=wavelengths)
    if v1 == 0 or v2 == 0:
      wl0=wavelengths[numpy.argmax(throughputs)]
      str1='Unable to calculate the filter mean wavelength, using the wavelength of peak \nresponse %f microns.' % (wl0)
      self.putMessage(str1)
    else:
      wl0=v1/v2
    if wl0 > spectrumwl[-1] or wl0 < spectrumwl[0]:
      return 0.0,0.0
    ind=numpy.abs(wavelengths-wl0).argmin()
    delwl1=wavelengths[ind+1]-wavelengths[ind]
    ind=numpy.abs(spectrumwl-wl0).argmin()
    delwl2=spectrumwl[ind+1]-spectrumwl[ind]
    if delwl2 < delwl1:
      newthroughputs=numpy.interp(spectrumwl,wavelengths,throughputs)
      newthroughputs[spectrumwl <= wavelengths[0]]=0.
      newthroughputs[spectrumwl >= wavelengths[-1]]=0.
      v1=numpy.trapz(spectrumwl*spectrum*newthroughputs,x=spectrumwl)
      v2=numpy.trapz(spectrumwl*newthroughputs,x=spectrumwl)
      v3=numpy.trapz(newthroughputs/spectrumwl,x=spectrumwl)
    else:
      newspectrum=numpy.interp(wavelengths,spectrumwl,spectrum)
      v1=numpy.trapz(wavelengths*newspectrum*throughputs,x=wavelengths)
      v2=numpy.trapz(wavelengths*throughputs,x=wavelengths)
      v3=numpy.trapz(throughputs/wavelengths,x=wavelengths)
    if (v1 > 0.) & (v2 > 0.):
      meanflux=v1/v2
    else:
      meanflux=0.
    if (v2 > 0.) & (v3 > 0.):
      pivotwl=math.sqrt(v2/v3)
    else:
      pivotwl=0.
    return pivotwl,meanflux    

  def setpl(self,event):
    s1=self.fields[0].get()
    self.fields[0].delete(0,len(s1))
    self.fields[0].insert(0,(str(self.plvalue.get())))

  def sepLine(self,parent,w1,h1,pad):
    lincanvas=Tk.Canvas(parent,height=h1,width=w1)
    try:
      lincanvas.pack(side=Tk.TOP,fill=Tk.BOTH,expand=Tk.YES)
    except:
      pass
    lincanvas.create_line(pad,h1/2,w1-pad,h1/2)
    return lincanvas

  def settemp(self,event):
    s1=self.fields[1].get()
    self.fields[1].delete(0,len(s1))
    tval=10.**self.tempvalue.get()
    s1="%.1f" % tval
    self.fields[1].insert(0,s1)

  def plkey(self,event):
   s1=self.fields[0].get()
   try:
     value=float(s1)
     self.plvalue.set(value)
   except:
     pass

  def tempkey(self,event):
   s1=self.fields[1].get()
   try:
     value=float(s1)
     if value >= 1.:
       value=math.log10(value)
       self.tempvalue.set(value)
   except:
     pass

  def getFilename1(self):
    self.inputFilename1=tkFileDialog.askopenfilename()
    if '/' in self.inputFilename1:
      vals=self.inputFilename1.split('/')
      shortname=vals[-1]
    else:
      shortname=self.inputFilename1
    s1=self.fields[4].get()
    self.fields[4].delete(0,len(s1))
    self.fields[4].insert(0,shortname)

  def getFilename2(self):
    self.inputFilename2=tkFileDialog.askopenfilename()
    if '/' in self.inputFilename2:
      vals=self.inputFilename2.split('/')
      shortname=vals[-1]
    else:
      shortname=self.inputFilename2
    s1=self.fields[6].get()
    self.fields[6].delete(0,len(s1))
    self.fields[6].insert(0,shortname)

  def getFilename3(self):
    self.inputFilename3=tkFileDialog.askopenfilename()
    if '/' in self.inputFilename3:
      vals=self.inputFilename3.split('/')
      shortname=vals[-1]
    else:
      shortname=self.inputFilename3
    s1=self.fields[7].get()
    self.fields[7].delete(0,len(s1))
    self.fields[7].insert(0,shortname)

  def setDType(self):
    n=self.dataType.get()
    self.fl=0
    self.lfl=0
    self.fnu=0
    if n == 0:
      self.fl=1
    if n == 1:
      self.lfl=1
    if n == 2:
      self.fnu=1

  def calculateMagnitudes(self):
    if not self.spectrum:
      if self.showgui:
        self.putMessage('Error: no spectral shape has been defined.  The count rates cannot be calculated.')
      else:
        print('Error: no spectral shape has been defined.  The count rates cannot be calculated.')
      return
    if self.showgui:
      self.putMessage('\n')
    file1=open('niriss_zeromag_countrates.txt','w')
    outfile=open('niriss_magnitudes.out','a')
    str1=self.zeroMagLabel()
    print(str1,file=outfile)
    print(str1,file=file1)
    str1='# Filter    Simulated Zero Magnitude Count Rate (electron/second) '
    print(str1,file=file1)
    str1='# Model Spectrum: %s\n# %s\n# Normalization: %s' % (self.spectrumLabel,self.extinctionLabel,self.renormLabel)
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='# Filter        Magnitude   Count Rate    Mean F_lambda    Mean F_nu  Pivot Wavelength'
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='#                          electron/sec   W/m^2/micron       Jy         Microns       '
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    for n in range(12):
      fwl=numpy.copy(self.wavelengths[n])
      fresp=numpy.copy(self.throughputs[n])
      countrate1=otearea*self.getFilterFlux(fwl,fresp,self.standardWavelengths,self.standardSpectrum,True)
      countrate2=otearea*self.getFilterFlux(fwl,fresp,self.otherWavelengths,self.otherSpectrum,True)
      pivotwl,meanflambda=self.photomValues(fwl,fresp,self.otherWavelengths,self.otherSpectrum)
      meanfnu=1.e+20*pivotwl*pivotwl*meanflambda/299792458.
      magnitude=2.5*math.log10(countrate1/countrate2)+self.standardMagnitudes[n]
      zeromagcountrate=countrate2*(10.**(0.4*magnitude))
      zm=countrate1*(10.**(0.4*self.standardMagnitudes[n]))
      str1="%-15s %9.5f %13.6e  %13.6e  %13.6e %10.6f" % (self.filterNames[n],magnitude,countrate2,meanflambda,meanfnu,pivotwl)
      if self.showgui:
        self.putMessage(str1)
      print(str1,file=outfile)
      print('%-15s %15.8e' % (self.filterNames[n],zeromagcountrate),file=file1)
    outfile.close()
    file1.close()
      
  def calculateNRMMagnitudes(self):
    if not self.spectrum:
      if self.showgui:
        self.putMessage('Error: no spectral shape has been defined.  The count rates cannot be calculated.')
      else:
        print('Error: no spectral shape has been defined.  The count rates cannot be calculated.')
      return
    if self.showgui:
      self.putMessage('\n')
    file1=open('niriss_zeromag_countrates.txt','w')
    outfile=open('niriss_magnitudes.out','a')
    str1=self.zeroMagLabel()
    print(str1,file=outfile)
    print(str1,file=file1)
    str1='# Filter    Simulated Zero Magnitude Count Rate (electron/second) '
    print(str1,file=file1)
    str1='# Model Spectrum: %s\n# %s\n# Normalization: %s\n# Imaging with the NRM' % (self.spectrumLabel,self.extinctionLabel,self.renormLabel)
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='# Filter        Magnitude   Count Rate    Mean F_lambda    Mean F_nu  Pivot Wavelength'
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='#                          electron/sec   W/m^2/micron       Jy         Microns       '
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    nrmlist=[6,8,9,11]
    for n in nrmlist:
      fwl=numpy.copy(self.wavelengths[n])
      fresp=numpy.copy(self.throughputs[n])
      countrate1=self.nrmCorrection*otearea*self.getFilterFlux(fwl,fresp,self.standardWavelengths,self.standardSpectrum,True)
      countrate2=otearea*self.nrmCorrection*self.getFilterFlux(fwl,fresp,self.otherWavelengths,self.otherSpectrum,True)
      pivotwl,meanflambda=self.photomValues(fwl,fresp,self.otherWavelengths,self.otherSpectrum)
      meanfnu=1.e+20*pivotwl*pivotwl*meanflambda/299792458.
      magnitude=2.5*math.log10(countrate1/countrate2)+self.standardMagnitudes[n]
      zeromagcountrate=countrate2*(10.**(0.4*magnitude))
      zm=countrate1*(10.**(0.4*self.standardMagnitudes[n]))
      str1="%-15s %9.5f %13.6e  %13.6e  %13.6e %10.6f" % (self.filterNames[n],magnitude,countrate2,meanflambda,meanfnu,pivotwl)
      if self.showgui:
        self.putMessage(str1)
      print(str1,file=outfile)
      print('%-15s %15.8e' % (self.filterNames[n],zeromagcountrate),file=file1)
    outfile.close()
    file1.close()
      
  def defineSpectrum(self):
    if self.controlWindow is None:
      self.controlWindow=Tk.Toplevel()
      self.fields=[]
      options=['Power Law','Blackbody','Kurucz Model (old set)','Kurucz Model (new set)','Phoenix Model','Phoenix Grid','BOSC Model','Input Spectrum']
      self.buttons=[]
      self.buttonvar=Tk.IntVar()
      for j in range(len(options)):
        self.buttons.append(Tk.Radiobutton(self.controlWindow,text=options[j],variable=self.buttonvar,value=j))
        self.buttons[-1].grid(column=0,row=j,sticky=Tk.W)
      self.buttonvar.set(1)
      self.plvalue=Tk.DoubleVar()
      self.tempvalue=Tk.DoubleVar()
      powerlawSlider=Tk.Scale(self.controlWindow,orient=Tk.HORIZONTAL,length=300,from_=-10.00,to=+10.00,resolution=0.01,command=self.setpl,variable=self.plvalue)
      powerlawSlider.grid(column=2,row=0)
      temperatureSlider=Tk.Scale(self.controlWindow,orient=Tk.HORIZONTAL,length=300,from_=0.0,to=6.00,resolution=0.0001,command=self.settemp,variable=self.tempvalue,label="log(T)")
      temperatureSlider.grid(column=2,row=1)
      self.tempvalue.set(4.0)
      self.fields.append(Tk.Entry(self.controlWindow,width=36))
      self.fields[-1].grid(column=1,row=0)
      self.fields[-1].bind('<KeyPress>',self.plkey)
      self.fields[-1].bind('<KeyRelease>',self.plkey)
      self.fields[-1].bind('<Leave>',self.plkey)
      self.fields.append(Tk.Entry(self.controlWindow,width=36))
      self.fields[-1].grid(column=1,row=1)
      self.fields[-1].bind('<KeyPress>',self.tempkey)
      self.fields[-1].bind('<KeyRelease>',self.tempkey)
      self.fields[-1].bind('<Leave>',self.tempkey)
      self.fields.append(ttk.Combobox(self.controlWindow,width=35))
      self.fields[-1]['values']=oldkuruczlist
      self.fields[-1].grid(column=1,row=2)
      self.fields.append(ttk.Combobox(self.controlWindow,width=35))
      self.fields[-1]['values']=newkuruczlist
      self.fields[-1].grid(column=1,row=3)
      self.fields.append(Tk.Entry(self.controlWindow,width=36))
      self.fields[-1].grid(column=1,row=4)
      self.fields.append(ttk.Combobox(self.controlWindow,width=35))
      self.fields[-1]['values']=phoenixlabels
      self.fields[-1].grid(column=1,row=5)
      self.gridnumber=len(self.fields)-1
      self.fields.append(Tk.Entry(self.controlWindow,width=36))
      self.fields[-1].grid(column=1,row=6)
      self.fields.append(Tk.Entry(self.controlWindow,width=36))
      self.fields[-1].grid(column=1,row=7)
      selectButton1=Tk.Button(self.controlWindow,text="Select File",command=self.getFilename1)
      selectButton1.grid(column=2,row=4)
      selectButton3=Tk.Button(self.controlWindow,text="Select File",command=self.getFilename2)
      selectButton3.grid(column=2,row=6)
      selectButton4=Tk.Button(self.controlWindow,text="Select File",command=self.getFilename3)
      selectButton4.grid(column=2,row=7)
# put in the Angstroms/Micron selection for input models
      holder=Tk.Frame(self.controlWindow)
      holder.grid(column=1,row=8,sticky=Tk.W)
      lab=Tk.Label(holder,text="Input Wavelengths ")
      lab.pack(side=Tk.LEFT)
      self.wavelengthUnits=ttk.Combobox(holder,width=15)
      self.wavelengthUnits.pack(side=Tk.RIGHT)
      self.wavelengthUnits['values']=['Angstroms','Microns']
      self.wavelengthUnits.current(0)
# put in buttons for F_lamda, F_nu or lambda*F_lambda
      dataFrame=Tk.Frame(self.controlWindow)
      dataFrame.grid(column=2,row=8,sticky=Tk.W)
      self.dataType=Tk.IntVar()
      dfl=Tk.Radiobutton(dataFrame,text=u"F_\u03BB",variable=self.dataType,command=self.setDType,value=0)
      dlfl=Tk.Radiobutton(dataFrame,text=u"\u03BB F_\u03BB",variable=self.dataType,command=self.setDType,value=1)
      dfnu=Tk.Radiobutton(dataFrame,text=u"F_\u03BD",variable=self.dataType,command=self.setDType,value=2)
      dfnu.pack(side=Tk.LEFT)
      dlfl.pack(side=Tk.LEFT)
      dfl.pack(side=Tk.LEFT)
      self.sep3=self.sepLine(self.controlWindow,800,16,10)
      self.sep3.grid(column=0,row=9,columnspan=3)
      self.renormFlag=Tk.IntVar()
      renormFrame=Tk.Frame(self.controlWindow)
      renormFrame.grid(column=0,row=10,columnspan=3)
      lab=Tk.Label(renormFrame,text='Normalziation Option:')
      lab.pack(side=Tk.LEFT)
      self.renormOption1=Tk.Radiobutton(renormFrame,text='None',variable=self.renormFlag,value=0)
      self.renormOption1.pack(side=Tk.LEFT)
      self.renormOption2=Tk.Radiobutton(renormFrame,text='A0V Magnitude',variable=self.renormFlag,value=1)
      self.renormOption2.pack(side=Tk.LEFT)
      self.renormOption3=Tk.Radiobutton(renormFrame,text='AB Magnitude',variable=self.renormFlag,value=2)
      self.renormOption3.pack(side=Tk.LEFT)
      self.renormOption4=Tk.Radiobutton(renormFrame,text=u"F_\u03BD (Jy)",variable=self.renormFlag,value=3)
      self.renormOption4.pack(side=Tk.LEFT)
      self.renormOption5=Tk.Radiobutton(renormFrame,text=u"F_\u03BB (W/m\u00B2/\u00B5m)",variable=self.renormFlag,value=4)
      self.renormOption5.pack(side=Tk.LEFT)
      self.renormOption6=Tk.Radiobutton(renormFrame,text=u"\u03BB F_\u03BB (W/m\u00B2)",variable=self.renormFlag,value=5)
      self.renormOption6.pack(side=Tk.LEFT)
      self.renormFlag.set(1)
      lab=Tk.Label(self.controlWindow,text="Normalization Magnitude")
      lab.grid(column=0,row=11)
      self.magValue=Tk.Entry(self.controlWindow,width=15)
      self.magValue.insert(0,'15.0')
      self.magValue.grid(column=1,row=11,sticky=Tk.W)
      holder=Tk.Frame(self.controlWindow)
      holder.grid(column=2,row=11,sticky=Tk.W)
      lab=Tk.Label(holder,text="for filter ")
      lab.pack(side=Tk.LEFT)
      self.normMagSelect=ttk.Combobox(holder,width=15)
      self.normMagSelect.pack(side=Tk.RIGHT)
      self.normMagSelect['values']=self.filterNames
      self.normMagSelect.current(77)
      lab=Tk.Label(self.controlWindow,text="Extinction at V (mag)")
      lab.grid(column=0,row=12)
      self.extinctionValue=Tk.Entry(self.controlWindow,width=15)
      self.extinctionValue.insert(0,'0.0')
      self.extinctionValue.grid(column=1,row=12,sticky=Tk.W)
      self.extinctionOption=Tk.IntVar()
      avselect=Tk.Frame(self.controlWindow)
      avselect.grid(column=2,row=12,sticky=Tk.W)
      t1=Tk.Radiobutton(avselect,text="E(B-V)",variable=self.extinctionOption,value=1)
      t1.pack(side=Tk.LEFT)
      t1=Tk.Radiobutton(avselect,text=u"A\u1D20",variable=self.extinctionOption,value=2)
      t1.pack(side=Tk.LEFT)
      self.extinctionOption.set(1)
      holder=Tk.Frame(self.controlWindow)
      holder.grid(column=0,row=13,sticky=Tk.W,columnspan=3)
      lab=Tk.Label(holder,text=u"        Normalization \u03BB (\u00B5m)")
      lab.pack(side=Tk.LEFT)
      self.normWavelengthField=Tk.Entry(holder,width=15)
      self.normWavelengthField.pack(side=Tk.LEFT)
      self.normWavelengthField.insert(0,'1.0')
      lab=Tk.Label(holder,text="                     Normalization Flux Density")
      lab.pack(side=Tk.LEFT)
      self.normFluxField=Tk.Entry(holder,width=15)
      self.normFluxField.pack(side=Tk.LEFT)
      self.normFluxField.insert(0,'1.0e-06')
      holder=Tk.Frame(self.controlWindow)
      holder.grid(column=0,row=14,columnspan=3)
      applyButton=Tk.Button(holder,text="Select",command=self.getSpectrum)
      applyButton.pack(side=Tk.LEFT)
      closeButton=Tk.Button(holder,text="Close Window",command=self.hideSpectrumWindow)
      closeButton.pack(side=Tk.LEFT)
    else:
      self.controlWindow.deiconify()  

  def zeroMagLabel(self):
    if showgui:
      opt=self.zeroMagOption.get()
    else:
      opt=self.zeromagpar
    value=self.standardSpectrum[0]
    target=[1.23811e-16,4.0015284e-15,6.6985e-15]
    for n in range(len(target)):
      ratio=value/target[n]
      if (ratio > 0.95) & (ratio < 1.05):
        m=n
    if m != opt:
      if showgui:
        self.putMessage('Warning: The zero magnitude option does not match the spectrum values.')
      opt=m
    labels=['Bohlin Vega (2012)','Bohlin Vega (2014)','Bohlin Sirius (2014)']
    str1="# Assumed A0V spectral template: %s" % (labels[opt])
    return str1
      
  def otherMagnitudes(self):
    if not self.spectrum:
      if self.showgui:
        self.putMessage('Error: no spectral shape has been defined.  The magnitudes cannot be calculated.')
      return
    if self.showgui:
      self.putMessage('\n')
    sloanoffset=[0.9879,-0.1830,0.09214,0.3291,0.4162]
    outfile=open('all_magnitudes.out','a')
    str1=self.zeroMagLabel()
    print(str1,file=outfile)
    str1='# Model Spectrum: %s\n# %s\n# Normalization: %s' % (self.spectrumLabel,self.extinctionLabel,self.renormLabel)
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='# Filter                  Magnitude   Count Rate    Mean F_lambda    Mean F_nu    Pivot     AB Magnitude'
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='#                                   or in-band flux                             Wavelength              '
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='#                                    electrons/sec   W/m^2/micron       Jy        Microns       '
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    str1='#                                       or W/m^2                                                '
    if self.showgui:
      self.putMessage(str1)
    print(str1,file=outfile)
    for n in range(len(self.filterNames)):
      fwl=numpy.copy(self.wavelengths[n])
      fresp=numpy.copy(self.throughputs[n])
      if n < 52:
        photonflag=True
        marker='C'
      else:
        photonflag=False
        marker='F'
      pivotwl,meanflambda=self.photomValues(fwl,fresp,self.otherWavelengths,self.otherSpectrum)
      meanfnu=1.e+20*pivotwl*pivotwl*meanflambda/299792458.
      if 'Sloan' in self.filterNames[n]:
        magnitude=self.sloanMagnitude(self.filterNames[n],meanfnu)
        countrate2=self.getFilterFlux(fwl,fresp,self.otherWavelengths,self.otherSpectrum,photonflag)
      else:
        if photonflag:
          countrate1=otearea*self.getFilterFlux(fwl,fresp,self.standardWavelengths,self.standardSpectrum,photonflag)
          countrate2=otearea*self.getFilterFlux(fwl,fresp,self.otherWavelengths,self.otherSpectrum,photonflag)
        else:
          countrate1=self.getFilterFlux(fwl,fresp,self.standardWavelengths,self.standardSpectrum,photonflag)
          countrate2=self.getFilterFlux(fwl,fresp,self.otherWavelengths,self.otherSpectrum,photonflag)
        magnitude=2.5*math.log10(countrate1/countrate2)+self.standardMagnitudes[n]
      aboffset=2.5*math.log10(3631.0/self.zeromagjy[n])
      abmag=magnitude+aboffset
      str1="%-25s %9.5f %13.6e  %13.6e  %13.6e %10.6f %9.5f %1s" % (self.filterNames[n],magnitude,countrate2,meanflambda,meanfnu,pivotwl,abmag,marker)
      if self.showgui:
        self.putMessage(str1)
      print(str1,file=outfile)
    outfile.close()

  def invertSloanMagnitude(self,filtername,magnitude):
    f0=3631.
    snames=["Sloan u","Sloan g","Sloan r","Sloan i","Sloan z"]
    b=[1.4e-10,0.9e-10,1.2e-10,1.8e-10,7.4e-10]
# The following offsets are given in Covey et al. (2007) AJ 134 2398, and
# differ from slightly from the Eisenstein et al. (2006) values.
    m0=[0.036,-0.012,-0.01,-0.028,-0.04]
    t1=math.log(10.)/2.5
    for n in range(len(snames)):
      if snames[n] in filtername:
        value=(m0[n]-magnitude)*t1-math.log(b[n])
        term=math.sinh(value)
        meanfnu=term*f0*2.*b[n]
        return meanfnu
    
  def sloanMagnitude(self,filtername,meanfnu):
    f0=3631.
    swl=[0.359,0.481,0.623,0.764,0.906]
    snames=["Sloan u","Sloan g","Sloan r","Sloan i","Sloan z"]
    b=[1.4e-10,0.9e-10,1.2e-10,1.8e-10,7.4e-10]
# The following offsets are given in Covey et al. (2007) AJ 134 2398, and
# differ from slightly from the Eisenstein et al. (2006) values.
    m0=[0.036,-0.012,-0.01,-0.028,-0.04]
    for n in range(len(snames)):
      if snames[n] in filtername:
        term=meanfnu/(2.*b[n]*f0)
        mag=m0[n]-(math.log(b[n])+math.asinh(term))*2.5/math.log(10.)
        return mag
    
  def filterProperties(self):
    values=numpy.zeros((12,27),dtype=numpy.float32)
    for n in range(12):
      filterresponse=numpy.copy(self.throughputs[n])
      filterwavelengths=numpy.copy(self.wavelengths[n])
      v1=getWavelengths(filterwavelengths,filterresponse,self.standardWavelengths,self.standardSpectrum)
      s1=numpy.trapz(filterresponse,x=filterwavelengths)
      rmax1=numpy.max(filterresponse)
      bw1=s1/rmax1
      f1=getFluxes(filterwavelengths,filterresponse,self.standardWavelengths,self.standardSpectrum,False,v1[0],v1[7])
      zeromagnitudescale=10.**(0.4*(self.standardMagnitudes[n]))
      values[n,0:7]=numpy.copy(f1)
      values[n,0:6]=values[n,0:6]*zeromagnitudescale
      values[n,7:18]=numpy.copy(v1)
      values[n,18:25]=numpy.interp(values[n,7:14],self.standardWavelengths,self.standardSpectrum)
# add the bandwidth and the effective response
      values[n,25]=bw1
      wlmin=values[n,8]-bw1/2.
      wlmax=values[n,8]+bw1/2.
      filterresponse=numpy.copy(self.throughputs[n])
      filterwavelengths=numpy.copy(self.wavelengths[n])
      resp1=filterresponse*0.+1.
      resp1[filterwavelengths < wlmin]=0.
      resp1[filterwavelengths > wlmax]=0.
      filterresponse=filterresponse*resp1
      eresp1=numpy.trapz(filterresponse,x=filterwavelengths)/numpy.trapz(resp1,x=filterwavelengths)
      values[n,26]=eresp1
    return values
# Values returned:
#
# values[:,0] zero magnitude F_lambda at central wavelength (W/m^2/micron)
# values[:,1] zero magnitude F_nu at central wavelength (Jy)
# values[:,2] zero magnitude lambda*F_lambda at central wavelength (Jy)
# values[:,3] zero_magnitude mean F_lambda
# values[:,4] zero_magnitude mean F_nu
# values[:,5] zero_magnitude mean lambda*F_lambda
# values[:,6] mean filter response (total filter response/FWHM)
# values[:,7] central wavelengths
# values[:,8] pivot wavelengths
# values[:,9] mean wavelengths
# values[:,10] photon mean wavelengths
# values[:,11] SDSS effective wavelengths
# values[:,12] flux mean wavelengths
# values[:,13] photon flux mean wavelengths
# values[:,14] FWHM values
# values[:,15] lower half maximum wavelengths
# values[:,16] upper half maximum wavelengths
# values[:,17] peak filter response
# values[:,18] wavelength flux densities at the central wavelengths
# values[:,19] wavelength flux densities at the pivot wavelengths
# values[:,20] wavelength flux densities at the mean wavelengths
# values[:,21] wavelength flux densities at the photon mean wavelengths
# values[:,22] wavelength flux densities at the SDSS effective  wavelengths
# values[:,23] wavelength flux densities at the flux mean wavelengths
# values[:,24] wavelength flux densities at the photon flux mean wavelengths
# values[:,25] effective wavelength values
# values[:,26] effective response values

  def effectiveWavelengths(self):
    if self.filterValues is None:
      self.filterValues=self.filterProperties()
    opt=self.zeroMagOption.get()
    value=self.standardSpectrum[0]
    target=[1.23811e-16,4.0015284e-15,6.6985e-15]
    for n in range(len(target)):
      ratio=value/target[n]
      if (ratio > 0.95) & (ratio < 1.05):
        m=n
    if m != opt:
      self.putMessage('Warning: The zero magnitude option does not match the spectrum values.')
      opt=m
    labels=['Bohlin Vega (2012)','Bohlin Vega (2014)','Bohlin Sirius (2014)']
    outfile=open('niriss_filter_values.txt','w')
    print('# Filter                                Zero Magnitude Flux Density                           Mean Response                                     Filter Wavelengths                                                                                                                             Scaled A0V Spectrum Flux Density at Filter Wavelengths',file=outfile)
    print('#       F_lambda          F_nu    lambda*F_lambda  <F_lambda>      <F_nu>   <lambda*F_lambda>                Central         Pivot         Mean      Photon Mean   SDSS Effective  Flux Mean  Photon Flux Mean   FWHM        FWHM Min       FWHM Max  Peak Response  Central         Pivot         Mean      Photon Mean   SDSS Effective  Flux Mean  Photon Flux Mean ',file=outfile)
    for loop in range(12):
      str1='%5s ' % (self.filterNames[loop])
      for l1 in range(25):
        str1=str1+'%13.6g ' % (self.filterValues[loop,l1])
      print(str1,file=outfile)
    outfile.close()
    f1=open('effective_wavelengths.out','w')
    label1=['Central','Pivot','Mean','Photon Mean','SDSS Effective','Flux Mean','Photon Flux Mean']
    str1='# Effective Wavelengths for the standard A0V spectrum\n# %s \n# Filter   Central     Pivot      Mean      Photon Mean     SDSS Effective   Flux Mean   Photon Flux Mean\n# \n' % (labels[opt])
    for n in range(12):
      str1=str1+'%s %10.6f %10.6f %10.6f %10.6f %10.6f %10.6f %10.6f\n' % (self.filterNames[n],self.filterValues[n,7],self.filterValues[n,8],self.filterValues[n,9],self.filterValues[n,10],self.filterValues[n,11],self.filterValues[n,12],self.filterValues[n,13])
    self.putMessage(str1)
    print(str1,file=f1)
    f1.close()
    f1=open('effective_wavelengths_long.out','w')
    print('# Values for standard spectrum: %s' % (labels[opt]),file=f1)
    print('# Wavelength  F_nu(Jy)  F_lambda(W/m^2/micron)  lambda*Flambda(W/m^2)',file=f1)
    for n in range(12):
      print('# Filter: %s' % (self.filterNames[n]),file=f1)
      for m in range(7):
        flout=numpy.interp(self.filterValues[n,7+m],self.standardWavelengths,self.standardSpectrum)
        freq=299792458./(self.filterValues[n,7+m]*1.e-06)
        lflout=flout*self.filterValues[n,7+m]
        fnuout=lflout*1.e+26/freq
        print('%-17s %10.6f %13.6e %13.6e %13.6e' % (label1[m],self.filterValues[n,7+m],fnuout,flout,lflout),file=f1)
      fl1=self.filterValues[n,3]
      fn1=self.filterValues[n,4]
      lfl1=self.filterValues[n,5]
      print('%-17s            %13.6e %13.6e %13.6e' % ('Filter Mean',fn1,fl1,lfl1),file=f1)
    f1.close()
    
if __name__ == "__main__":
  showgui=True
  root=None
  for par in sys.argv:
    if '-nogui' in par:
      showgui=False
  if showgui:
    root=Tk.Tk()
    root.title("NIRISS Count Rate/Magnitude/Flux Density Tool")
    x=Magnitude(root)
    root.mainloop()
  else:
    Magnitude(root)
