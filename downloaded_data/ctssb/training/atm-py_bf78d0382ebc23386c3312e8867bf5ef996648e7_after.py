import numpy as np
from struct import unpack, calcsize
import pandas as pd
import datetime
import os
from atmPy.tools import miscell_tools as misc
import pylab as plt
from atmPy import sizedistribution
import warnings
#from StringIO import StringIO as io
#from POPS_lib import calibration

defaultBins = np.array([0.15, 0.168, 0.188, 0.211, 0.236, 0.264, 0.296, 0.332, 0.371, 0.416, 0.466, 0.522, 0.584, 0.655, 0.864, 1.14, 1.505, 1.987, 2.623, 3.462])
defaultBins *= 1000


#######
#### Peak file
def _read_PeakFile_Binary(fname, deltaTime=0):
    """returns a peak instance
    fname: ...
    deltaTime: if you want to apply a timedelay in seconds"""
    data = _BinaryFile2Array(fname)
    directory, fname = os.path.split(fname)
    dataFrame = _PeakFileArray2dataFrame(data,fname,deltaTime)
    peakInstance = peaks(dataFrame)
    return peakInstance


def read_binary(fname):
    """Generates a single Peak instance from a file or list of files

    Arguments
    ---------
    fname: string or list of strings
    """

    m = None
    if type(fname).__name__ == 'list':
        first = True
        for file in fname:
            if 'Peak.bin' not in file:
                print('%s is not a peak file ... skipped' % file)
                continue
            print('%s ... processed' % file)
            mt = _read_PeakFile_Binary(file)
            if first:
                m = mt
                first = False
            else:
                m.data = pd.concat((m.data, mt.data))

    else:
        m = _read_PeakFile_Binary(fname)

    return m


def read_cal_process_peakFile(fname, cal, bins, averageOverTime='60S'):
    peakdf = read_binary(fname)
    peakdf.apply_calibration(cal)
    dist = peakdf.peak2numberdistribution(bins=bins)
    dist = dist.average_overTime(averageOverTime)
    return dist


def _BinaryFile2Array(fname):
    entry_format = '>fLfBB?'
    field_names = np.array(['timeSincMitnight', 'ticks', 'log10_amplitude', 'width', 'saturated', 'use'])
    entry_size = calcsize(entry_format)

    rein = open(fname, mode='rb')
    entry_count = int(os.fstat(rein.fileno()).st_size / entry_size)

    data = np.zeros((entry_count , field_names.shape[0]))

    for i in range(entry_count):
        record = rein.read(entry_size)
        entry = np.array(unpack(entry_format, record))
        data[i] = entry
    rein.close()
    return data

def _PeakFileArray2dataFrame(data,fname,deltaTime): 
    data = data.copy()
    dateString = fname.split('_')[0]
    dt = datetime.datetime.strptime(dateString, "%Y%m%d") - datetime.datetime.strptime('19700101', "%Y%m%d") 
    dts = dt.total_seconds()
    #dtsPlus = datetime.timedelta(seconds = deltaTime).total_seconds() 
    
    columns = np.array(['Ticks', 'Amplitude', 'Width', 'Saturated', 'Masked'])
    
    
    try:
        Time_s = data[:,0]
        rest = data[:,1:]
        dataTable = pd.DataFrame(rest, columns=columns)
        dataTable.index = pd.Series(pd.to_datetime(Time_s + dts + deltaTime, unit = 's'), name = 'Time_UTC')
    except OverflowError:
        
        data, report = _cleanPeaksArray(data)
        warnings.warn('Binary file %s is corrupt. Will try to fix it. if no exception accured it probably worked\nReport:\n%s'%(fname,report))
        
        
        Time_s = data[:,0]
        rest = data[:,1:]
        dataTable = pd.DataFrame(rest, columns=columns)
        dataTable.index = pd.Series(pd.to_datetime(Time_s + dts + deltaTime, unit = 's'), name = 'Time_UTC')
        

    dataTable.Amplitude = 10**dataTable.Amplitude # data is written in log10

    dataTable.Ticks = dataTable.Ticks.astype(np.int32)
    dataTable.Width = dataTable.Width.astype(np.int16)
    dataTable.Saturated = dataTable.Saturated.astype(np.int16)
    dataTable.Masked = np.abs(1. - dataTable.Masked).astype(np.int8)
    return dataTable

def _cleanPeaksArray(PeakArray):
    """tries to remove data points where obviously something went wrong. Returns the cleaned array."""
    BarrayClean = PeakArray.copy()
    startShape = BarrayClean.shape
    startstartShape = BarrayClean.shape

#    print BarrayClean.shape
    Tmax = 1.e6 #unless you are measuring for more than 2 weeks this should be ok
    BarrayClean = BarrayClean[BarrayClean[:,0] < Tmax]

    pointsRem = startShape[0] - BarrayClean.shape[0]
    report = '%s (%.5f%%) datapoints removed due to bad Time (quickceck)\n'%(pointsRem, pointsRem/float(startShape[0]))
    startShape = BarrayClean.shape
    ampMax = 2.*16 #the maximum you can measure with a 16 bit A2D converter
    BarrayClean = BarrayClean[BarrayClean[:,2] < ampMax]
    BarrayClean = BarrayClean[BarrayClean[:,2] > 0]

    pointsRem = startShape[0] - BarrayClean.shape[0]
    report += '%s (%.5f%%) datapoints removed due to bad Amplitude.\n'%(pointsRem, pointsRem/float(startShape[0]))
    startShape = BarrayClean.shape
    BarrayClean = BarrayClean[np.logical_or(BarrayClean[:,-1] == 1, BarrayClean[:,-1] == 0)]

    pointsRem = startShape[0] - BarrayClean.shape[0]
    report += '%s (%.5f%%) datapoints removed due to bad Used.\n'%(pointsRem, pointsRem/float(startShape[0]))
    startShape = BarrayClean.shape
    BarrayClean = BarrayClean[BarrayClean[:,3] < 1000]
    BarrayClean = BarrayClean[BarrayClean[:,3] > 1]

    pointsRem = startShape[0] - BarrayClean.shape[0]
    report +='%s (%.5f%%) datapoints removed due to bad Width.\n'%(pointsRem, pointsRem/float(startShape[0]))
    startShape = BarrayClean.shape
    BarUni = np.unique(BarrayClean[:,0])
    BarUniInt = BarUni[1:]- BarUni[:-1]
    timeMed = np.median(BarUniInt)

    lastTime = BarrayClean[0,0] #first entry in the time
    counterToHigh = 0
    counterToLow = 0
    for e,i in enumerate(BarrayClean):
        if i[0] - lastTime > timeMed * 1.1:
            i[0] = np.nan
            counterToHigh += 1
        elif i[0] - lastTime < 0:
            i[0] = np.nan
            counterToLow += 1
        else:
            lastTime = i[0]

    BarrayClean = BarrayClean[~np.isnan(BarrayClean[:,0])]


    pointsRem = startShape[0] - BarrayClean.shape[0]
    report += '%s (%.5f%%) datapoints removed due to bad Time (more elaborate check).\n'%(pointsRem, pointsRem/float(startShape[0]))
    startShape = BarrayClean.shape
    pointsRem = startstartShape[0] - BarrayClean.shape[0]
    report += 'All together %s (%.5f%%) datapoints removed.'%(pointsRem, pointsRem/float(startstartShape[0]))
    return BarrayClean, report

class peaks:
    def __init__(self,dataFrame):
        self.data = dataFrame
        
    def apply_calibration(self,calibrationInstance):
        self.data['Diameter'] = pd.Series(calibrationInstance.calibrationFunction(self.data.Amplitude.values), index = self.data.index)
        
        where_tooBig = np.where(self.data.Amplitude > calibrationInstance.data.amp.max())
        where_tooSmall = np.where(self.data.Amplitude < calibrationInstance.data.amp.min())
        tooSmall = len(where_tooSmall[0])
        tooBig = len(where_tooBig[0])
        self.data.Masked.values[where_tooBig] = 1
        self.data.Masked.values[where_tooSmall] = 1
        misc.msg('\t %s from %s peaks (%.1i %%) are outside the calibration range (amplitude = [%s, %s], diameter = [%s, %s])'%(tooSmall + tooBig, len(self.data.Amplitude),100 * float(tooSmall + tooBig)/float(len(self.data.Amplitude)) , calibrationInstance.data.amp.min(),  calibrationInstance.data.amp.max(), calibrationInstance.data.d.min(), calibrationInstance.data.d.max()))
        misc.msg('\t\t %s too small'%(tooSmall))
        misc.msg('\t\t %s too big'%(tooBig))
        return
        
    #########
    ### Plot some stuff
        
    def plot_timeVindex(self):
        notMasked = np.where(self.data.Masked == 0)
        f,a = plt.subplots()
        g, = a.plot(self.data.index[notMasked],'o')
        a.set_title('Time as a function of particle index')
        a.set_ylabel("Time (UTC)")
        a.set_xlabel('Particle index')
        return f,a,g
    
    def _plot_somethingVtime(self, what,title,ylabel):
        notMasked = np.where(self.data.Masked == 0)
        f,a = plt.subplots()
        g, = a.plot(self.data.index[notMasked], self.data[what].values[notMasked],'o')
        a.set_title(title)
        a.set_xlabel("Time (UTC)")
        a.set_ylabel(ylabel)
        return f,a,g
    
    def plot_widthVtime(self):
        return self._plot_somethingVtime('Width','Peak width as a function of time','Width (sampling steps)')
    
    
    def plot_diameterVtime(self):
        return self._plot_somethingVtime('Diameter', 'Peak diameter as a function of time','Diameter (nm)')
    
    
    def plot_amplitudeVtime(self):
        return self._plot_somethingVtime('Amplitude','Peak amplitude as a function of time', 'Amplitude (digitizer bins)' )
        
    ##########
    ##### Analytics
        
    def get_countRate(self,average = None):
        """average: string, e.g. "5S" for 5 seconds
        returns a pandas dataframe"""
        notMasked = np.where(self.data.Masked == 0)
        unique = np.unique(self.data.index.values[notMasked])
        numbers = np.zeros(unique.shape)
        deltaT = np.zeros(unique.shape)
        countsPerSec = np.zeros(unique.shape)
        dt = unique[1]-unique[0]
        for e,i in enumerate(unique):
            if e:
                dt = unique[e] - unique[e-1]
            numbers[e] =  float(len(np.where(self.data.index.values[notMasked] == i)[0]))
            deltaT[e] = dt / np.timedelta64(1, 's') # delta in seconds
            countsPerSec[e] = numbers[e] / deltaT[e]
    
        countRate = pd.DataFrame(np.array([numbers,deltaT,countsPerSec]).transpose(), index = unique, columns=['No_of_particles', 'DeltaT_s', 'CountRate_s'])    
        if average:
            countRate = countRate.resample(average,closed = 'right', label='center')
        return countRate
        

    
    
    def _peak2Distribution(self, bins=defaultBins, distributionType = 'number', differentialStyle = False):
        """Action required: clean up!
        Returns the particle size distribution normalized in various ways
        distributionType
        dNdDp, should be fixed to that, change to other types later once the distribution is created!
        old:
            \t calibration: this will create a intensity distribution instead of size distribution. bins should only be a number of bins which will be logaritmically spaced
            \t number:\t numbers only $\mu m^{-1}\, cm^{-3}$
            \t surface:\t surface area distribution, unit: $\mu m\, cm^{-3}$
            \t volume:\t  volume distribution, unit: $\mu m^{2}\, cm^{-3}$
        differentialStyle:\t     if False a raw histogram will be created, else:
            \t dNdDp: \t      distribution normalized to the bin width, bincenters are given by (Dn+Dn+1)/2
            \t dNdlogDp:\t    distribution normalized to the log of the bin width, bincenters are given by 10**((logDn+logDn+1)/2)
    
        """
        notMasked = np.where(self.data.Masked == 0)
        unique = np.unique(self.data.index.values[notMasked])
        N = np.zeros((unique.shape[0],bins.shape[0]-1))
    
    
        for e,i in enumerate(unique):
            condi = np.where(np.logical_and(self.data.Masked == 0, self.data.index.values == i))
            if distributionType == 'calibration':
                process = self.data.Amplitude.values[condi]
            else:
                process = self.data.Diameter.values[condi]
            n,edg = np.histogram(process, bins = bins)
            N[e] = n
    
        N = N.astype(np.float)
    
        deltaT = (unique[1:]-unique[:-1]) / np.timedelta64(1,'s')
        deltaT = np.append(deltaT[0],deltaT)
        deltaT = np.repeat(np.array([deltaT]),bins.shape[0]-1, axis=0)
        N/=deltaT.transpose()
        
        bincenter = (edg[:-1] + edg[1:])/2.
        binwidth = edg[1:] - edg[:-1]
    
        if not differentialStyle:
            pass
    
        elif differentialStyle == 'dNdDp':
            N = N/binwidth
    
#        elif differentialStyle == 'dNdlogDp':
#            bincenter = 10**((np.log10(edg[:-1]) + np.log10(edg[1:]))/2.)
#            binwidth = np.log10(edg[1:]) - np.log10(edg[:-1])
#            N = N/binwidth
        else:
            raise ValueError('wrong type for argument "differentialStyle"')      
    
#        if distributionType == 'surface':
#            N *= (bincenter**2 * np.pi)
#        elif distributionType == 'volume':
#            N *= (bincenter**3 * np.pi/6.)
#        elif (distributionType == 'number') or (distributionType == 'calibration'):
#            pass
#        else:
#            raise ValueError('wrong type for argument "distributionType"')    
    
        binstr = bins.astype(int).astype(str)
        cols=[]
        for e,i in enumerate(binstr[:-1]):
            cols.append(i+'-'+binstr[e+1])
        dataFrame = pd.DataFrame(N, columns=cols, index = unique)
        if distributionType == 'calibration':
            return sizedistribution.SizeDist_TS(dataFrame, bins, 'calibration')
        else:
            return sizedistribution.SizeDist_TS(dataFrame, bins, 'dNdDp')
        
#    def peak2numberdistribution_dNdlogDp(self, bins = defaultBins):
#        return self._peak2Distribution(bins = bins, differentialStyle='dNdlogDp')
#        
#    def peak2numberconcentration(self, bins = defaultBins):
#        return self._peak2Distribution(bins = bins)
    def peak2peakHeightDistribution(self, bins = np.logspace(np.log10(35),np.log10(65000), 200)):
        """see doc-string of _peak2Distribution"""
        return self._peak2Distribution(bins = bins,distributionType = 'calibration',differentialStyle = 'dNdDp')
        
    def peak2numberdistribution(self, bins = defaultBins):
        """see doc-string of _peak2Distribution"""
        return self._peak2Distribution(bins = bins, differentialStyle='dNdDp')
        
#    def peak2calibration(self, bins = 200, ampMin = 20):
#        bins = np.logspace(np.log10(20), np.log10(self.data.Amplitude.values.max()),bins)
#        dist = self._peak2Distribution(bins = bins, distributionType='calibration')
#        return dist
#    peak2calibration.__doc__ = blabla