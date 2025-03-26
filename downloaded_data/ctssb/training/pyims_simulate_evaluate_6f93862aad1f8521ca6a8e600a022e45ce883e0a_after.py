__author__ = 'palmer'
import numpy as np
ms_types = ['orbitrap',]
class sim_data():
    def __init__(self,output_filename,layers,ms_info):
        assert ms_info["ms_type"] in ms_types, "ms_type not in {}".format(ms_types)
        self.output_filename=output_filename
        self.ms_info=ms_info
        self.layers = layers
        layer_names = layers['layers_list'].keys()
        self.n_y,self.n_x = np.shape(layers['layers_list'][layer_names[0]]['image'])
        self.base_mz = self.generate_base_mz()
        s_fac = self.ms_info["sample_scale_factor"]
        self.resample_mz = self.resample_mz(self.base_mz,s_fac)

    def resample_mz(self,base_mz,s_fac):
        baseLen = len(base_mz)
        x  = np.linspace(0,baseLen,int(baseLen*s_fac))
        xi = range(0,baseLen)
        yi = base_mz
        mzs = np.interp(x,xi,yi)
        return mzs

    def generate_base_mz(self):
        if self.ms_info["ms_type"] == 'orbitrap':
            n_samples = self.ms_info["n_samples"]
            min_mz = self.ms_info["min_mz"]
            max_mz = self.ms_info["max_mz"]
            s_fac = self.ms_info["sample_scale_factor"]
            mzs = np.square(np.linspace(np.sqrt(min_mz),np.sqrt(max_mz),n_samples))
        return mzs

    def get_pixel_mzs_abundances(self,x,y):
        layers = self.layers
        mzList = []
        intensityList = []
        layer_names = layers['layers_list'].keys()
        for layer_name in layer_names:
            px_mult = layers['layers_list'][layer_name]['image'][y,x]
            for sf_a in layers['layers_list'][layer_name]['sf_list']:
                iso_pattern = sf_a["iso_pattern"]
                _mzs = iso_pattern[0]
                _intensities = [sf_a["mult"][0]*ii*px_mult for ii in iso_pattern[1]]
                mzList.extend(_mzs)
                intensityList.extend(_intensities)
        mzList=np.asarray(mzList)
        intensityList=np.asarray(intensityList)
        return mzList, intensityList

    def get_peaks(self,x,y):
        mzList,intensityList = self.get_pixel_mzs_abundances(x,y)
        mzList = self.apply_mass_accuracy(mzList)
        min_mz = self.ms_info["min_mz"]
        max_mz = self.ms_info["max_mz"]
        _keepIdx = [all((m>min_mz,m<max_mz)) for m in mzList]
        mzList=[mm for mm, ii in zip(mzList,_keepIdx) if ii == True]
        intensityList=[mm for mm, ii in zip(intensityList,_keepIdx) if ii == True]
        return mzList,intensityList

    def apply_mass_accuracy(self,mzList):
        delta_m = self.ms_info['ppm_accuracy']*1e-6
        mzList +=  np.random.randn(len(mzList))*delta_m*mzList
        return mzList

    def simulate_orbitrap(self,intensities):
        noise_factor = self.ms_info["noise_factor"]
        s_fac = self.ms_info["sample_scale_factor"]
        tran = np.fft.fft(intensities)
        tran += noise_factor*np.random.randn(len(tran))
        intensities = np.fft.ifft(tran[0:int(s_fac*len(tran))])
        intensities = np.abs(intensities)
        intensities -= np.median(intensities)
        return intensities

    def simulate_spectrum(self,peakList):
        mzs = peakList[0]
        intensities = peakList[1]
        mz_idx = np.digitize(mzs,self.base_mz)
        intensityVect = np.bincount(mz_idx,weights=intensities,minlength=len(self.base_mz))
        if self.ms_info["ms_type"] == 'orbitrap':
            intensityVect = self.simulate_orbitrap(intensityVect)
        return self.resample_mz, intensityVect

    def generate_spectrum(self,x,y,mode='centroid', cent_kwargs={}):
        peakList = self.get_peaks(x,y)
        mzs,intensities = self.simulate_spectrum(peakList)
        if mode=='centroid':
            from pyMSpec.centroid_detection import gradient
            from pyMSpec import smoothing
            mzs, intensities = smoothing.fast_change(mzs,intensities)
            #intensities[intensities<0.015] = 0
            mzs,intensities,_ = gradient(np.asarray(mzs),np.asarray(intensities), **cent_kwargs)
        return mzs,intensities

    def simulate_dataset(self,mode='centroid'):
        from pyimzml.ImzMLWriter import ImzMLWriter
        #imzml = self.open_imzml(self.output_filename)
        with ImzMLWriter(self.output_filename, mz_dtype=np.float32, intensity_dtype=np.float32) as imzml:
            for x in range(self.n_x):
                print x
                for y in range(self.n_y):
                    thisSpectrum = self.generate_spectrum(x,y, mode=mode, cent_kwargs = self.ms_info['cent_kwargs'])
                    pos = (x, y, 0)
                    mzs = thisSpectrum[0]
                    intensities = thisSpectrum[1]
                    # don't store zeros
                    zer_idx = mzs>0
                    mzs = mzs[zer_idx]
                    intensities=intensities[zer_idx]
                    imzml.addSpectrum(mzs, intensities, pos)