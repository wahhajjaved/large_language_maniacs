import numpy as np
from matplotlib.colors import LogNorm
import pylab as plt
from copy import deepcopy
from atmPy.tools import plt_tools, math_functions, array_tools
from atmPy import timeseries
import pandas as pd
import warnings
import datetime
from atmPy.mie import bhmie
import scipy.optimize as optimization
from scipy import integrate
from scipy import stats
from atmPy import vertical_profile
from atmPy.aerosols import hygroscopic_growth as hg
from atmPy.tools import pandas_tools

# Todo: rotate the plots of the layerseries (e.g. plot_particle_concentration) to have the altitude as the y-axes

# TODO: Fix distrTypes so they are consistent with our understanding.
distTypes = {'log normal': ['dNdlogDp', 'dSdlogDp', 'dVdlogDp'],
             'natural': ['dNdDp', 'dSdDp', 'dVdDp'],
             'number': ['dNdlogDp', 'dNdDp'],
             'surface': ['dSdlogDp', 'dSdDp'],
             'volume': ['dVdlogDp', 'dVdDp']}

axes_types = ('AxesSubplot', 'AxesHostAxes')

def fit_normal_dist(x, y, log=True, p0=[10, 180, 0.2]):
    """Fits a normal distribution to a """
    param = p0[:]
    x = x[~ np.isnan(y)]
    y = y[~ np.isnan(y)]

    if log:
        x = np.log10(x)
        param[1] = np.log10(param[1])
    # todo: write a bug report for the fact that I have to call the y.max() function to make the fit to work!!!!!
    y.max()
    ############

    para = optimization.curve_fit(math_functions.gauss, x, y, p0=param)

    amp = para[0][0]
    sigma = para[0][2]
    if log:
        pos = 10 ** para[0][1]
        sigma_high = 10 ** (para[0][1] + para[0][2])
        sigma_low = 10 ** (para[0][1] - para[0][2])
    else:
        pos = para[0][1]
        sigma_high = (para[0][1] + para[0][2])
        sigma_low = (para[0][1] - para[0][2])
    return [amp, pos, sigma, sigma_high, sigma_low]


def read_csv(fname, fixGaps=True):
    headerNo = 50
    rein = open(fname, 'r')
    nol = ['distributionType', 'objectType']
    outDict = {}
    for i in range(headerNo):
        split = rein.readline().split('=')
        variable = split[0].strip()
        if split[0][0] == '#':
            break
        value = split[1].strip()
        if variable in nol:
            outDict[variable] = value
        else:
            outDict[variable] = np.array(eval(value))
        if i == headerNo - 1:
            raise TypeError('Sure this is a size distribution?')

    rein.close()
    data = pd.read_csv(fname, header=i + 1, index_col=0)
    data.index = pd.to_datetime(data.index)
    if outDict['objectType'] == 'SizeDist_TS':
        distRein = SizeDist_TS(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    elif outDict['objectType'] == 'SizeDist':
        distRein = SizeDist(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    elif outDict['objectType'] == 'SizeDist_LS':
        distRein = SizeDist_LS(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    else:
        raise TypeError('not a valid object type')
    return distRein


def get_label(distType):
    """ Return the appropriate label for a particular distribution type
    """
    if distType == 'dNdDp':
        label = '$\mathrm{d}N\,/\,\mathrm{d}D_{P}$ (nm$^{-1}\,$cm$^{-3}$)'
    elif distType == 'dNdlogDp':
        label = '$\mathrm{d}N\,/\,\mathrm{d}log(D_{P})$ (cm$^{-3}$)'
    elif distType == 'dSdDp':
        label = '$\mathrm{d}S\,/\,\mathrm{d}D_{P}$ (nm$\,$cm$^{-3}$)'
    elif distType == 'dSdlogDp':
        label = '$\mathrm{d}S\,/\,\mathrm{d}log(D_{P})$ (nm$^2\,$cm$^{-3}$)'
    elif distType == 'dVdDp':
        label = '$\mathrm{d}V\,/\,\mathrm{d}D_{P}$ (nm$^2\,$cm$^{-3}$)'
    elif distType == 'dVdlogDp':
        label = '$\mathrm{d}V\,/\,\mathrm{d}log(D_{P})$ (nm$^3\,$cm$^{-3}$)'
    elif distType == 'calibration':
        label = '$\mathrm{d}N\,/\,\mathrm{d}Amp$ (bin$^{-1}\,$cm$^{-3}$)'
    elif distType == 'numberConcentration':
        label = 'Particle number in bin'
    else:
        raise ValueError('%s is not really an option!?!' % distType)
    return label


# Todo: Docstring is wrong
# Todo: implement into the Layer Series
def _calculate_optical_properties(sd, wavelength, n, aod=False, noOfAngles=100):
    """
    !!!Tis Docstring need fixn
    Calculates the extinction crossection, AOD, phase function, and asymmetry Parameter for each layer.
    plotting the layer and diameter dependent extinction coefficient gives you an idea what dominates the overall AOD.

    Parameters
    ----------
    wavelength: float.
        wavelength of the scattered light, unit: nm
    n: float.
        Index of refraction of the scattering particles

    noOfAngles: int, optional.
        Number of scattering angles to be calculated. This mostly effects calculations which depend on the phase
        function.

    Returns
    -------
    OpticalProperty instance

    """
    out = {}
    out['n'] = n
    out['wavelength'] = wavelength
    sdls = sd.convert2numberconcentration()
    index = sdls.data.index

    if isinstance(n, pd.DataFrame):
        n_multi = True
    else:
        n_multi = False

    if not n_multi:
        mie, angular_scatt_func = _perform_Miecalculations(np.array(sdls.bincenters / 1000.), wavelength / 1000., n,
                                                       noOfAngles=noOfAngles)

    if aod:
        AOD_layer = np.zeros((len(sdls.layercenters)))

    extCoeffPerLayer = np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))
    angular_scatt_func_effective = pd.DataFrame()
    asymmetry_parameter_LS = np.zeros((len(sdls.data.index.values)))

    # print('\n oben mie.extinction_crossection: %s \n'%(mie.extinction_crossection))

    for i, lc in enumerate(sdls.data.index.values):
        laydata = sdls.data.iloc[i].values
        # print('laydata: ',laydata.shape)
        # print(laydata)
        if n_multi:
            mie, angular_scatt_func = _perform_Miecalculations(np.array(sdls.bincenters / 1000.), wavelength / 1000., n.iloc[i].values[0],
                                                       noOfAngles=noOfAngles)
        extinction_coefficient = _get_coefficients(mie.extinction_crossection, laydata)

        # print('\n oben ext_coef %s \n'%extinction_coefficient)


        # print('mie.extinction_crossection ', mie.extinction_crossection.shape)
        # print('extinction_coefficient: ', extinction_coefficient.shape)
        # scattering_coefficient = _get_coefficients(mie.scattering_crossection, laydata)

        if aod:
            layerThickness = sdls.layerbounderies[i][1] - sdls.layerbounderies[i][0]
            AOD_perBin = extinction_coefficient * layerThickness
            AOD_layer[i] = AOD_perBin.values.sum()

        extCoeffPerLayer[i] = extinction_coefficient


        # return laydata, mie.scattering_crossection

        scattering_cross_eff = laydata * mie.scattering_crossection

        pfe = (laydata * angular_scatt_func).sum(axis=1)  # sum of all angular_scattering_intensities
        # pfe2 = pfe.copy()
        # angular_scatt_func_effective[lc] =  pfe
        # asymmetry_parameter_LS[i] = (pfe.values*np.cos(pfe.index.values)).sum()/pfe.values.sum()
        x_2p = pfe.index.values
        y_2p = pfe.values
        # limit to [0,pi]
        y_1p = y_2p[x_2p < np.pi]
        x_1p = x_2p[x_2p < np.pi]
        # integ = integrate.simps(y_1p*np.sin(x_1p),x_1p)
        # y_phase_func = y_1p/integ
        y_phase_func = y_1p * 4 * np.pi / scattering_cross_eff.sum()
        asymmetry_parameter_LS[i] = .5 * integrate.simps(np.cos(x_1p) * y_phase_func * np.sin(x_1p), x_1p)
        # return mie,phase_fct, laydata, scattering_cross_eff, phase_fct_effective[lc], y_phase_func, asymmetry_parameter_LS[i]
        angular_scatt_func_effective[
            lc] = pfe * 1e-12 * 1e6  # equivalent to extCoeffPerLayer # similar to  _get_coefficients (converts everthing to meter)
        # return mie.extinction_crossection, angular_scatt_func, laydata, layerThickness # correct integrales match
        # return extinction_coefficient, angular_scatt_func_effective
        # return AOD_layer, pfe, angular_scatt_func_effective[lc]


        #     print(mie.extinction_crossection)

    if aod:
        out['AOD'] = AOD_layer[~ np.isnan(AOD_layer)].sum()
        out['AOD_layer'] = pd.DataFrame(AOD_layer, index=sdls.layercenters, columns=['AOD per Layer'])
        out['AOD_cum'] = out['AOD_layer'].iloc[::-1].cumsum().iloc[::-1]

    extCoeff_perrow_perbin = pd.DataFrame(extCoeffPerLayer, index=index, columns=sdls.data.columns)

    out['extCoeff_perrow_perbin'] = extCoeff_perrow_perbin
    extCoeff_perrow = pd.DataFrame(extCoeff_perrow_perbin.sum(axis=1), columns=['ext_coeff'])
    if index.dtype == '<M8[ns]':
        out['extCoeff_perrow'] = timeseries.TimeSeries(extCoeff_perrow)
    else:
        out['extCoeff_perrow'] = extCoeff_perrow

    out['asymmetry_param'] = pd.DataFrame(asymmetry_parameter_LS, index=index,
                                          columns=['asymmetry_param'])
    # out['asymmetry_param_alt'] = pd.DataFrame(asymmetry_parameter_LS_alt, index=sdls.layercenters, columns = ['asymmetry_param_alt'])
    # out['OptPropInstance']= OpticalProperties(out, self.bins)
    out['wavelength'] = wavelength
    out['index_of_refraction'] = n
    out['bin_centers'] = sdls.bincenters
    out['angular_scatt_func'] = angular_scatt_func_effective
    # opt_properties = OpticalProperties(out, self.bins)
    # opt_properties.wavelength = wavelength
    # opt_properties.index_of_refractio = n
    # opt_properties.angular_scatt_func = angular_scatt_func_effective  # This is the formaer phase_fct, but since it is the angular scattering intensity, i changed the name
    # opt_properties.parent_dist_LS = self
    return out

class SizeDist(object):
    """
    Object defining a log normal aerosol size distribution


    Arguments
    ----------
    bincenters:         NumPy array, optional
                        this is if you actually want to pass the bincenters, if False they will be calculated
    distributionType:
                        log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
                        natural: 'dNdDp','dSdDp','dVdDp'
                        number: 'dNdlogDp', 'dNdDp', 'numberConcentration'
                        surface: 'dSdlogDp','dSdDp'
                        volume: 'dVdlogDp','dVdDp'
    data:   pandas dataFrame, optional
            None, will generate an empty pandas data frame with columns defined by bins
             - pandas dataFrame with
                 - column names (each name is something like this: '150-200')
                 - index is time (at some point this should be arbitrary, convertable to altitude for example?)
    unit conventions:
             - diameters: nanometers
             - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD)



    Notes
    ------
    * Diameters are specified in nanometers

    """
    # todo: write setters and getters for bins and bincenter, so when one is changed the otherone is automatically
    #  changed too
    def __init__(self, data, bins, distrType,
                 # bincenters=False,
                 fixGaps=True):

        if type(data).__name__ == 'NoneType':
            self.data = pd.DataFrame()
        else:
            self.data = data



        self.bins = bins
        self.__index_of_refraction = None
        self.__growth_factor = None
        # if type(bincenters) == np.ndarray:
        #     self.bincenters = bincenters
        # else:
        #     self.bincenters = (bins[1:] + bins[:-1]) / 2.
        # self.binwidth = (bins[1:] - bins[:-1])
        self.distributionType = distrType
        if fixGaps:
            self.fillGaps()


    @property
    def bins(self):
        return self.__bins

    @bins.setter
    def bins(self,array):
        bins_st = array.astype(int).astype(str)
        col_names = []
        for e,i in enumerate(bins_st):
            if e == len(bins_st) - 1:
                break
            col_names.append(bins_st[e] + '-' + bins_st[e+1])
        self.data.columns = col_names


        self.__bins = array
        self.__bincenters = (array[1:] + array[:-1]) / 2.
        self.__binwidth = (array[1:] - array[:-1])



    @property
    def bincenters(self):
        return self.__bincenters

    @property
    def binwidth(self):
        return self.__binwidth

    @property
    def index_of_refraction(self):
        return self.__index_of_refraction

    @index_of_refraction.setter
    def index_of_refraction(self,n):
        # if not self.__index_of_refraction:
        self.__index_of_refraction = n
        # elif self.__index_of_refraction:
        #     txt = """Security stop. This is to prevent you from unintentionally changing this value.
        #     The index of refraction is already set to %.2f, either by you or by another function, e.g. apply_hygro_growth.
        #     If you really want to change the value do it by setting the __index_of_refraction attribute."""%self.index_of_refraction
        #     raise ValueError(txt)

    @property
    def growth_factor(self):
        return self.__growth_factor

    def apply_hygro_growth(self, kappa, RH, how = 'shift_bins'):
        """
        how: string ['shift_bins', 'shift_data']
        """

        if not self.index_of_refraction:
            txt = '''The index_of_refraction attribute of this sizedistribution has not been set yet, please do so first!'''
            raise ValueError(txt)
        # out_I = {}
        dist_g = self.copy()
        dist_g.convert2numberconcentration()

        gf,n_mix = hg.kappa_simple(kappa, RH, n = dist_g.index_of_refraction)
        # out_I['growth_factor'] = gf
        if how == 'shift_bins':
            if not isinstance(gf, (float,int)):
                txt = '''If how is equal to 'shift_bins' RH has to be of type int or float.
                It is %s'''%(type(RH).__name__)
                raise TypeError(txt)

            dist_g.bins = dist_g.bins * gf
            dist_g.__index_of_refraction = n_mix
        elif how == 'shift_data':
            test = dist_g._hygro_growht_shift_data(dist_g.data.values[0],dist_g.bins,gf.max())
            bin_num = test['data'].shape[0]
            data_new = np.zeros((dist_g.data.shape[0],bin_num))
            for e,i in enumerate(dist_g.data.values):
                out = dist_g._hygro_growht_shift_data(i,dist_g.bins,gf[e])
                dt = out['data']
                diff = bin_num - dt.shape[0]
                dt = np.append(dt, np.zeros(diff))
                data_new[e] = dt
            df = pd.DataFrame(data_new)
            df.index = dist_g.data.index
            # return df
            dist_g = SizeDist(df, test['bins'], dist_g.distributionType)
            df = pd.DataFrame(n_mix, columns = ['index_of_refraction'])
            df.index = dist_g.data.index
            dist_g.index_of_refraction = df
        else:
            txt = '''How has to be either 'shift_bins' or 'shift_data'.'''
            raise ValueError(txt)

        dist_g.__growth_factor = pd.DataFrame(gf, index = dist_g.data.index, columns = ['Growth_factor'])
        # out_I['size_distribution'] = dist_g
        return dist_g


    def _hygro_growht_shift_data(self, data, bins, gf):
        """data: 1D array
        bins: 1D array
        gf: float"""
        bins = bins.copy()
        if np.any(gf < 1):
            txt = 'Growth factor must be equal or larger than 1. No shrinking!!'
            raise ValueError(txt)

        shifted = bins*gf
        ml = array_tools.find_closest(bins, shifted, how='closest_low')
        mh = array_tools.find_closest(bins, shifted, how='closest_high')

        if np.any((mh - ml) > 1):
            raise ValueError('shifted bins spans over more than two of the original bins, programming required ;-)')

        no_extra_bins = bins[ml].shape[0] - np.unique(bins[ml]).shape[0] + 1

        ######### Ad bins to shift data into

        last_two = np.log10(bins[- (no_extra_bins + 1):])
        step_width = last_two[-1] - last_two[-2]
        new_bins = np.zeros(no_extra_bins)
        for i in range(no_extra_bins):
            new_bins[i] = np.log10(bins[-1]) + ((i + 1) * step_width)
        newbins = 10**new_bins
        bins = np.append(bins,newbins)
        shifted = (bins * gf)[:-no_extra_bins]

        ######## and again ########################

        ml = array_tools.find_closest(bins, shifted, how='closest_low')
        mh = array_tools.find_closest(bins, shifted, how='closest_high')

        if np.any((mh - ml) > 1):
            raise ValueError('shifted bins spans over more than two of the original bins, programming required ;-)')


        ##### percentage of particles moved to next bin ...')

        shifted_w = shifted[1:] - shifted[:-1]

        fract_first = (bins[mh] - shifted)[:-1]/shifted_w
        fract_last = (shifted - bins[ml])[1:]/shifted_w

        data_new = np.zeros(data.shape[0]+ no_extra_bins)
        data_new[no_extra_bins - 1:-1] += fract_first * data
        data_new[no_extra_bins:] += fract_last * data

    #     data = np.append(data, np.zeros(no_extra_bins))
        out = {}
        out['bins'] = bins
        out['data'] = data_new
        out['num_extr_bins'] = no_extra_bins
        return out


    # def grow_particles(self, shift=1):
    #     """This function shifts the data by "shift" columns to the right
    #     Argurments
    #     ----------
    #     shift: int.
    #         number of columns to shift.
    #
    #     Returns
    #     -------
    #     New dist_LS instance
    #     Growth ratio (mean,std) """
    #
    #     dist_grow = self.copy()
    #     gf = dist_grow.bincenters[shift:] / dist_grow.bincenters[:-shift]
    #     gf_mean = gf.mean()
    #     gf_std = gf.std()
    #
    #     shape = dist_grow.data.shape[1]
    #     dist_grow.data[:] = 0
    #     dist_grow.data.iloc[:, shift:] = self.data.values[:, :shape - shift]
    #
    #     return dist_grow, (gf_mean, gf_std)

    def calculate_optical_properties(self, wavelength, n):
        out = _calculate_optical_properties(self, wavelength, n)
        return out


    def fillGaps(self, scale=1.1):
        """
        Finds gaps in dataset (e.g. when instrument was shut of) and fills them with zeros.

        It adds one line of zeros to the beginning and one to the end of the gap. 
        Therefore the gap is visible as zeros instead of the interpolated values

        Parameters
        ----------
        scale:  float, optional
                This is a scale.
        """
        diff = self.data.index[1:].values - self.data.index[0:-1].values
        threshold = np.median(diff) * scale
        where = np.where(diff > threshold)[0]
        if len(where) != 0:
            warnings.warn('The dataset provided had %s gaps' % len(where))
            gap_start = self.data.index[where]
            gap_end = self.data.index[where + 1]
            for gap_s in gap_start:
                self.data.loc[gap_s + threshold] = np.zeros(self.bincenters.shape)
            for gap_e in gap_end:
                self.data.loc[gap_e - threshold] = np.zeros(self.bincenters.shape)
            self.data = self.data.sort_index()
        return

    def fit_normal(self, log=True, p0=[10, 180, 0.2]):
        """ Fits a single normal distribution to each line in the data frame.

        Returns
        -------
        pandas DataFrame instance (also added to namespace as data_fit_normal)

        """
        sd = self.copy()

        if sd.distributionType != 'dNdlogDp':
            if sd.distributionType == 'calibration':
                pass
            else:
                warnings.warn(
                    "Size distribution is not in 'dNdlogDp'. I temporarily converted the distribution to conduct the fitting. If that is not what you want, change the code!")
                sd = sd.convert2dNdlogDp()

        n_lines = sd.data.shape[0]
        amp = np.zeros(n_lines)
        pos = np.zeros(n_lines)
        sigma = np.zeros(n_lines)
        sigma_high = np.zeros(n_lines)
        sigma_low = np.zeros(n_lines)
        for e, lay in enumerate(sd.data.values):
            try:
                fit_res = fit_normal_dist(sd.bincenters, lay, log=log, p0=p0)
            except (ValueError, RuntimeError):
                fit_res = [np.nan, np.nan, np.nan, np.nan, np.nan]
            amp[e] = fit_res[0]
            pos[e] = fit_res[1]
            sigma[e] = fit_res[2]
            sigma_high[e] = fit_res[3]
            sigma_low[e] = fit_res[4]

        df = pd.DataFrame()
        df['Amp'] = pd.Series(amp)
        df['Pos'] = pd.Series(pos)
        df['Sigma'] = pd.Series(sigma)
        df['Sigma_high'] = pd.Series(sigma_high)
        df['Sigma_low'] = pd.Series(sigma_low)
        # df.index = self.layercenters
        self.data_fit_normal = df
        return self.data_fit_normal


    def get_particle_concentration(self):
        """ Returns the sum of particles per line in data

        Returns
        -------
        int: if data has only one line
        pandas.DataFrame: else """
        sd = self.convert2numberconcentration()
        particles = np.zeros(sd.data.shape[0])
        for e, line in enumerate(sd.data.values):
            particles[e] = line.sum()
        if sd.data.shape[0] == 1:
            return particles[0]
        else:
            df = pd.DataFrame(particles, index=sd.data.index, columns=['Count_rate'])
            return df

    def plot(self,
             showMinorTickLabels=True,
             removeTickLabels=["700", "900"],
             fit_res=True,
             fit_res_scale = 'log',
             ax=None,
             ):
        """
        Plots and returns f,a (figure, axis).

        Arguments
        ---------
        showMinorTickLabels: bool [True], optional
            if minor tick labels are labled
        removeTickLabels: list of string ["700", "900"], optional
            list of tick labels aught to be removed (in case there are overlapping)
        fit_res: bool [True], optional
            allows plotting of fitresults if fit_normal was previously executed
        fit_res: string
            If fit_normal was done using log = False, you want to set this to linear!
        ax: axis object [None], optional
            option to provide axis to plot on

        Returns
        -------
        Handles to the figure and axes of the figure.


        """
        if type(ax).__name__ in axes_types:
            a = ax
            f = a.get_figure()
        else:
            f, a = plt.subplots()

        g, = a.plot(self.bincenters, self.data.loc[0], color=plt_tools.color_cycle[0], linewidth=2, label='exp.')
        g.set_drawstyle('steps-mid')

        a.set_xlabel('Particle diameter (nm)')

        label = get_label(self.distributionType)
        a.set_ylabel(label)
        a.set_xscale('log')

        if fit_res:
            if 'data_fit_normal' in dir(self):
                amp, pos, sigma = self.data_fit_normal.values[0, :3]
                if fit_res_scale == 'log':
                    normal_dist = math_functions.gauss(np.log10(self.bincenters), amp, np.log10(pos), sigma)
                elif fit_res_scale =='linear':
                    normal_dist = math_functions.gauss(self.bincenters, amp, pos, sigma)
                else:
                    txt = '"fit_res_scale has to be either log or linear'
                    raise ValueError(txt)
                a.plot(self.bincenters, normal_dist, color=plt_tools.color_cycle[1], linewidth=2,
                       label='fit with norm. dist.')
                a.legend()

        return f, a


    def convert2dNdDp(self):
        return self._convert2otherDistribution('dNdDp')

    def convert2dNdlogDp(self):
        return self._convert2otherDistribution('dNdlogDp')

    def convert2dSdDp(self):
        return self._convert2otherDistribution('dSdDp')

    def convert2dSdlogDp(self):
        return self._convert2otherDistribution('dSdlogDp')

    def convert2dVdDp(self):
        return self._convert2otherDistribution('dVdDp')

    def convert2dVdlogDp(self):
        return self._convert2otherDistribution('dVdlogDp')

    def convert2numberconcentration(self):
        return self._convert2otherDistribution('numberConcentration')

    def copy(self):
        return deepcopy(self)

    def save_csv(self, fname, header=True):
        if header:
            raus = open(fname, 'w')
            raus.write('bins = %s\n' % self.bins.tolist())
            raus.write('distributionType = %s\n' % self.distributionType)
            raus.write('objectType = %s\n' % (type(self).__name__))
            raus.write('#\n')
            raus.close()
        self.data.to_csv(fname, mode='a')
        return

    def zoom_diameter(self, start=None, end=None):
        sd = self.copy()
        if start:
            startIdx = array_tools.find_closest(sd.bins, start)
        else:
            startIdx = 0
        if end:
            endIdx = array_tools.find_closest(sd.bins, end)
        else:
            endIdx = len(self.bincenters)
        # sd.binwidth = self.binwidth[startIdx:endIdx]
        sd.data = self.data.iloc[:, startIdx:endIdx]
        sd.bins = self.bins[startIdx:endIdx + 1]
        # sd.bincenters = self.bincenters[startIdx:endIdx]

        return sd

    def _normal2log(self):
        trans = (self.bincenters * np.log(10.))
        return trans

    def _2Surface(self):
        trans = 4. * np.pi * (self.bincenters / 2.) ** 2
        return trans

    def _2Volume(self):
        trans = 4. / 3. * np.pi * (self.bincenters / 2.) ** 3
        return trans

    def _convert2otherDistribution(self, distType, verbose=False):

        dist = self.copy()
        if dist.distributionType == distType:
            if verbose:
                warnings.warn(
                    'Distribution type is already %s. Output is an unchanged copy of the distribution' % distType)
            return dist

        if dist.distributionType == 'numberConcentration':
            pass
        elif distType == 'numberConcentration':
            pass
        elif dist.distributionType in distTypes['log normal']:
            if distType in distTypes['log normal']:
                if verbose:
                    print('both log normal')
            else:
                dist.data = dist.data / self._normal2log()

        elif dist.distributionType in distTypes['natural']:
            if distType in distTypes['natural']:
                if verbose:
                    print('both natural')
            else:
                dist.data = dist.data * self._normal2log()
        else:
            raise ValueError('%s is not an option' % distType)

        if dist.distributionType == 'numberConcentration':
            pass

        elif distType == 'numberConcentration':
            pass
        elif dist.distributionType in distTypes['number']:
            if distType in distTypes['number']:
                if verbose:
                    print('both number')
            else:
                if distType in distTypes['surface']:
                    dist.data *= self._2Surface()
                elif distType in distTypes['volume']:
                    dist.data *= self._2Volume()
                else:
                    raise ValueError('%s is not an option' % distType)

        elif dist.distributionType in distTypes['surface']:
            if distType in distTypes['surface']:
                if verbose:
                    print('both surface')
            else:
                if distType in distTypes['number']:
                    dist.data /= self._2Surface()
                elif distType in distTypes['volume']:
                    dist.data *= self._2Volume() / self._2Surface()
                else:
                    raise ValueError('%s is not an option' % distType)

        elif dist.distributionType in distTypes['volume']:
            if distType in distTypes['volume']:
                if verbose:
                    print('both volume')
            else:
                if distType in distTypes['number']:
                    dist.data /= self._2Volume()
                elif distType in distTypes['surface']:
                    dist.data *= self._2Surface() / self._2Volume()
                else:
                    raise ValueError('%s is not an option' % distType)
        else:
            raise ValueError('%s is not an option' % distType)

        if distType == 'numberConcentration':
            dist = dist.convert2dNdDp()
            dist.data *= self.binwidth

        elif dist.distributionType == 'numberConcentration':
            dist.data = dist.data / self.binwidth
            dist.distributionType = 'dNdDp'
            dist = dist._convert2otherDistribution(distType)

        dist.distributionType = distType
        if verbose:
            print('converted from %s to %s' % (self.distributionType, dist.distributionType))
        return dist


class SizeDist_TS(SizeDist):
    """Returns a SizeDistribution_TS instance.

    Parameters:
    -----------
    data: pandas dataFrame with
         - column names (each name is something like this: '150-200')
         - index is time (at some point this should be arbitrary, convertable to altitude for example?)
    unit conventions:
         - diameters: nanometers
         - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD)
    distributionType:
         log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
         natural: 'dNdDp','dSdDp','dVdDp'
         number: 'dNdlogDp', 'dNdDp', 'numberConcentration'
         surface: 'dSdlogDp','dSdDp'
         volume: 'dVdlogDp','dVdDp'
       """

    def fit_normal(self, log=True, p0=[10, 180, 0.2]):
        """ Fits a single normal distribution to each line in the data frame.

        Returns
        -------
        pandas DataFrame instance (also added to namespace as data_fit_normal)

        """

        super(SizeDist_TS, self).fit_normal(log=log, p0=p0)
        self.data_fit_normal.index = self.data.index
        return self.data_fit_normal


    def _getXYZ(self):
        """
        This will create three arrays, so when plotted with pcolor each pixel will represent the exact bin width
        """
        binArray = np.repeat(np.array([self.bins]), self.data.index.shape[0], axis=0)
        timeArray = np.repeat(np.array([self.data.index.values]), self.bins.shape[0], axis=0).transpose()
        ext = np.array([np.zeros(self.data.index.values.shape)]).transpose()
        Z = np.append(self.data.values, ext, axis=1)
        return timeArray, binArray, Z

    def get_timespan(self):
        return self.data.index.min(), self.data.index.max()

    # TODO: Fix plot options such as showMinorTickLabels
    def plot(self,
             vmax=None,
             vmin=None,
             norm='linear',
             showMinorTickLabels=True,
             removeTickLabels=["700", "900"],
             ax=None,
             fit_pos=True,
             cmap=plt_tools.get_colorMap_intensity(),
             colorbar=True):

        """ plots an intensity plot of all data

        Arguments
        ---------
        scale (optional): ('log',['linear']) - defines how the z-direction is scaled
        vmax
        vmin
        show_minor_tickLabels:
        cma:
        fit_pos: bool[True]. Optional
            plots the position of a fitted normal distribution onto the plot.
            in order for this to work execute fit_normal
        ax (optional):  axes instance [None] - option to plot on existing axes

        Returns
        -------
        f,a,pc,cb (figure, axis, pcolormeshInstance, colorbar)

        """
        X, Y, Z = self._getXYZ()
        Z = np.ma.masked_invalid(Z)

        if type(ax).__name__ in axes_types:
            a = ax
            f = a.get_figure()
        else:
            f, a = plt.subplots()
            f.autofmt_xdate()

        if norm == 'log':
            norm = LogNorm()
        elif norm == 'linear':
            norm = None

        # ToDo: The following screws up log-plotting, Is that stuff neaded anywhere else?
        # if not vmax:
        # vmax = Z.max()
        # if not vmin:
        #     vmin = Z.min()

        pc = a.pcolormesh(X, Y, Z, vmin=vmin, vmax=vmax, norm=norm, cmap=cmap)
        a.set_yscale('log')
        a.set_ylim((self.bins[0], self.bins[-1]))
        a.set_xlabel('Time (UTC)')

        if self.distributionType == 'calibration':
            a.set_ylabel('Amplitude (digitizer bins)')
        else:
            a.set_ylabel('Diameter (nm)')
        if colorbar:
            cb = f.colorbar(pc)
            label = get_label(self.distributionType)
            cb.set_label(label)
        else:
            cb = get_label(self.distributionType)

        if self.distributionType != 'calibration':
            a.yaxis.set_major_formatter(plt.FormatStrFormatter("%i"))

            f.canvas.draw()  # this is important, otherwise the ticks (at least in case of minor ticks) are not created yet
            if showMinorTickLabels:
                a.yaxis.set_minor_formatter(plt.FormatStrFormatter("%i"))
                ticks = a.yaxis.get_minor_ticks()
                for i in ticks:
                    if i.label.get_text() in removeTickLabels:
                        i.label.set_visible(False)

        if fit_pos:
            if 'data_fit_normal' in dir(self):
                a.plot(self.data.index, self.data_fit_normal.Pos, color='m', linewidth=2, label='normal dist. center')
                leg = a.legend(fancybox=True, framealpha=0.5)
                leg.draw_frame(True)

        return f, a, pc, cb

    def plot_fitres(self):
        """ Plots the results from fit_normal"""

        f, a = plt.subplots()
        data = self.data_fit_normal.dropna()
        a.fill_between(data.index, data.Sigma_high, data.Sigma_low,
                       color=plt_tools.color_cycle[0],
                       alpha=0.5,
                       )
        a.plot(data.index.values, data.Pos.values, color=plt_tools.color_cycle[0], linewidth=2, label='center')
        # data.Pos.plot(ax=a, color=plt_tools.color_cycle[0], linewidth=2, label='center')
        a.legend(loc=2)
        a.set_ylabel('Particle diameter (nm)')
        a.set_xlabel('Altitude (m)')

        a2 = a.twinx()
        # data.Amp.plot(ax=a2, color=plt_tools.color_cycle[1], linewidth=2, label='amplitude')
        a2.plot(data.index.values, data.Amp.values, color=plt_tools.color_cycle[1], linewidth=2, label='amplitude')
        a2.legend()
        a2.set_ylabel('Amplitude - %s' % (get_label(self.distributionType)))
        f.autofmt_xdate()
        return f, a, a2

    def plot_particle_concentration(self, ax=None, label=None):
        """Plots the particle rate as a function of time.

        Parameters
        ----------
        ax: matplotlib.axes instance, optional
            perform plot on these axes.

        Returns
        -------
        matplotlib.axes instance

        """

        if type(ax).__name__ in axes_types:
            color = plt_tools.color_cycle[len(ax.get_lines())]
            f = ax.get_figure()
        else:
            f, ax = plt.subplots()
            color = plt_tools.color_cycle[0]

        # layers = self.convert2numberconcentration()

        particles = self.get_particle_concentration().dropna()

        ax.plot(particles.index.values, particles.Count_rate.values, color=color, linewidth=2)

        if label:
            ax.get_lines()[-1].set_label(label)
            ax.legend()

        ax.set_xlabel('Time (UTC)')
        ax.set_ylabel('Particle number concentration (cm$^{-3})$')
        if particles.index.dtype.type.__name__ == 'datetime64':
            f.autofmt_xdate()
        return ax

    def zoom_time(self, start=None, end=None):
        """
        2014-11-24 16:02:30
        """
        dist = self.copy()
        dist.data = dist.data.truncate(before=start, after=end)
        return dist


    def average_overTime(self, window='1S'):
        """returns a copy of the sizedistribution_TS with reduced size by averaging over a given window

        Arguments
        ---------
        window: str ['1S']. Optional
            window over which to average. For aliases see
            http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases

        Returns
        -------
        SizeDistribution_TS instance
            copy of current instance with resampled data frame
        """

        dist = self.copy()
        window = window
        dist.data = dist.data.resample(window, closed='right', label='right')
        if dist.distributionType == 'calibration':
            dist.data.values[np.where(np.isnan(self.data.values))] = 0
        return dist

    def average_overAllTime(self):
        """
        averages over the entire dataFrame and returns a single sizedistribution (numpy.ndarray)
        """
        singleHist = np.zeros(self.data.shape[1])

        for i in range(self.data.shape[1]):
            line = self.data.values[:, i]
            singleHist[i] = np.average(line[~np.isnan(line)])

        data = pd.DataFrame(np.array([singleHist]), columns=self.data.columns)
        avgDist = SizeDist(data, self.bins, self.distributionType)

        return avgDist

    def convert2layerseries(self, hk, layer_thickness=10, force=False):
        """convertes the time series to a layer series.

        Note
        ----
        nan values are excluded when an average is taken over a the time that corresponds to the particular layer
        (altitude). If there are only nan values nan is returned and there is a gap in the Layerseries.

        The the housekeeping instance has to have a column called "Altitude" and which is monotonicly in- or decreasing

        Arguments
        ---------
        hk: housekeeping instance
        layer_thickness (optional): [10] thickness of each generated layer in meter"""
        if any(np.isnan(hk.data.Altitude)):
            txt = """The Altitude contains nan values. Either fix this first, eg. with pandas interpolate function"""
            raise ValueError(txt)

        if ((hk.data.Altitude.values[1:] - hk.data.Altitude.values[:-1]).min() < 0) and (
                    (hk.data.Altitude.values[1:] - hk.data.Altitude.values[:-1]).max() > 0):
            if force:
                hk.data = hk.data.sort(columns='Altitude')
            else:
                txt = '''Given altitude data is not monotonic. This is not possible (yet). Use force if you
know what you are doing'''
                raise ValueError(txt)

        start_h = round(hk.data.Altitude.values.min() / layer_thickness) * layer_thickness
        end_h = round(hk.data.Altitude.values.max() / layer_thickness) * layer_thickness

        layer_edges = np.arange(start_h, end_h, layer_thickness)
        empty_frame = pd.DataFrame(columns=self.data.columns)
        lays = SizeDist_LS(empty_frame, self.bins, self.distributionType, None)

        for e, end_h_l in enumerate(layer_edges[1:]):
            start_h_l = layer_edges[e]
            layer = hk.data.Altitude.iloc[
                np.where(np.logical_and(start_h_l < hk.data.Altitude.values, hk.data.Altitude.values < end_h_l))]
            start_t = layer.index.min()
            end_t = layer.index.max()
            dist_tmp = self.zoom_time(start=start_t, end=end_t)
            avrg = dist_tmp.average_overAllTime()
            # return avrg,lays
            lays.add_layer(avrg, (start_h_l, end_h_l))
        lays.parent_dist_TS = self
        lays.parent_timeseries = hk

        data = hk.data.copy()
        data['Time_UTC'] = data.index
        data.index = data.Altitude
        data = data.sort_index()
        if not data.index.is_unique: #this is needed in case there are duplicate indeces
            grouped = data.groupby(level = 0)
            data = grouped.last()

        lays.housekeeping = data
        data = data.reindex(lays.layercenters,method = 'nearest')
        lays.housekeeping = vertical_profile.VerticalProfile(data)
        return lays


class SizeDist_LS(SizeDist):
    """
    Parameters
    ----------
    data:    pandas DataFrame ...
    bins:    array
    distributionType:   str
    layerbounderies:    array shape(n_layers,2)

    OLD
    ---
    data: pandas dataFrame with
                 - column names (each name is something like this: '150-200')
                 - altitude (at some point this should be arbitrary, convertable to altitude for example?)
       unit conventions:
             - diameters: nanometers
             - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD) 
       distributionType:  
             log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
             natural: 'dNdDp','dSdDp','dVdDp'
             number: 'dNdlogDp', 'dNdDp', 'numberConcentration'
             surface: 'dSdlogDp','dSdDp'
             volume: 'dVdlogDp','dVdDp'

    """

    def __init__(self, data, bins, distributionType, layerbounderies, fixGaps=True):
        super(SizeDist_LS, self).__init__(data, bins, distributionType, fixGaps=True)
        if type(layerbounderies).__name__ == 'NoneType':
            self.layerbounderies = np.empty((0, 2))
            # self.layercenters = np.array([])
        else:
            self.layerbounderies = layerbounderies

    @property
    def layercenters(self):
        return self.__layercenters

    @property
    def layerbounderies(self):
        return self.__layerbouderies

    @layerbounderies.setter
    def layerbounderies(self,lb):
        self.__layerbouderies = lb
        # newlb = np.unique(self.layerbounderies.flatten()) # the unique is sorting the data, which is not reallyt what we want!
        # self.__layercenters = (newlb[1:] + newlb[:-1]) / 2.
        self.__layercenters = (self.layerbounderies[:,0] + self.layerbounderies[:,1]) / 2.
        self.data.index = self.layercenters

    def apply_hygro_growth(self, kappa, RH = None, how='shift_data'):
        """ see docstring of atmPy.sizedistribution.SizeDist for more information
        Parameters
        ----------
        kappa: float
        RH: bool, float, or array.
            If None, RH from self.housekeeping will be taken"""

        if not np.any(RH):
            pandas_tools.ensure_column_exists(self.housekeeping.data, 'Relative_humidity')
            RH = self.housekeeping.data.Relative_humidity.values
        # return kappa,RH,how
        sd = super(SizeDist_LS,self).apply_hygro_growth(kappa,RH,how = how)
        # sd = out['size_distribution']
        # gf = out['growth_factor']
        sd_LS = SizeDist_LS(sd.data, sd.bins, sd.distributionType, self.layerbounderies, fixGaps=False)
        sd_LS.index_of_refraction = sd.index_of_refraction
        sd_LS._SizeDist__growth_factor = sd.growth_factor
        # out['size_distribution'] = sd_LS
        return sd_LS

    def calculate_angstromex(self, wavelengths=[460.3, 550.4, 671.2, 860.7], n=1.455):
        """Calculates the Anstrome coefficience (overall, layerdependent)

        Parameters
        ----------
        wavelengths:    array-like, optional.
            the angstrom coefficient will be calculated based on the AOD of these wavelength values (in nm)
        n:              float, optional.
            index of refraction used in the underlying mie calculation.

        Returns
        -------
        Angstrom exponent, float
        List containing the OpticalProperties instances for the different wavelengths

        New Attributes
        --------------
        angstromexp:        float
            the resulting angstrom exponent
        angstromexp_fit:    pandas instance.
            AOD and fit result as a function of wavelength
        angstromexp_LS:     pandas instance.
            angstrom exponent as a function of altitude
        """

        AOD_list = []
        AOD_dict = {}
        for w in wavelengths:
            AOD = self.calculate_optical_properties(w, n)  # calculate_AOD(wavelength=w, n=n)
            #     opt= sizedistribution.OpticalProperties(AOD, dist_LS.bins)
            AOD_list.append({'wavelength': w, 'opt_inst': AOD})
            AOD_dict['%.1f' % w] = AOD

        eg = AOD_dict[list(AOD_dict.keys())[0]]

        wls = AOD_dict.keys()
        wls_a = np.array(list(AOD_dict.keys())).astype(float)
        ang_exp = []
        ang_exp_std = []
        ang_exp_r_value = []
        for e, el in enumerate(eg.layercenters):
            AODs = np.array([AOD_dict[wl].data_orig['AOD_layer'].values[e][0] for wl in wls])
            slope, intercept, r_value, p_value, std_err = stats.linregress(np.log10(wls_a), np.log10(AODs))
            ang_exp.append(-slope)
            ang_exp_std.append(std_err)
            ang_exp_r_value.append(r_value)
        # break
        ang_exp = np.array(ang_exp)
        ang_exp_std = np.array(ang_exp_std)
        ang_exp_r_value = np.array(ang_exp_r_value)

        tmp = np.array([[float(i), AOD_dict[i].AOD] for i in AOD_dict.keys()])
        wavelength, AOD = tmp[np.argsort(tmp[:, 0])].transpose()
        slope, intercept, r_value, p_value, std_err = stats.linregress(np.log10(wavelength), np.log10(AOD))

        self.angstromexp = -slope
        aod_fit = np.log10(wavelengths) * slope + intercept
        self.angstromexp_fit = pd.DataFrame(np.array([AOD, 10 ** aod_fit]).transpose(), index=wavelength,
                                            columns=['data', 'fit'])

        self.angstromexp_LS = pd.DataFrame(np.array([ang_exp, ang_exp_std, ang_exp_r_value]).transpose(),
                                           index=self.layercenters,
                                           columns=['ang_exp', 'standard_dif', 'correlation_coef'])
        self.angstromexp_LS.index.name = 'layercenter'

        return -slope, AOD_dict

    def calculate_optical_properties(self, wavelength, n = None, noOfAngles=100):
        if not n:
            n = self.index_of_refraction
        out = _calculate_optical_properties(self, wavelength, n, aod = True, noOfAngles=noOfAngles)
        opt_properties = OpticalProperties(out, self.bins)
        opt_properties.wavelength = wavelength
        opt_properties.index_of_refractio = n
        opt_properties.angular_scatt_func = out['angular_scatt_func']  # This is the formaer phase_fct, but since it is the angular scattering intensity, i changed the name
        opt_properties.parent_dist_LS = self
        return opt_properties



    def add_layer(self, sd, layerboundery):
        """
        Adds a sizedistribution instance to the layerseries.
        layerboundery

        Parameters
        ----------
        sd:
        layerboundary:
        """
        if len(layerboundery) != 2:
            raise ValueError('layerboundery has to be of length 2')

        sd = sd._convert2otherDistribution(self.distributionType)

        layerbounderies = np.append(self.layerbounderies, np.array([layerboundery]), axis=0)

        layerbounderiesU = np.unique(layerbounderies)

        if (np.where(layerbounderiesU == layerboundery[1])[0] - np.where(layerbounderiesU == layerboundery[0])[0])[
            0] != 1:
            raise ValueError('The new layer is overlapping with an existing layer!')
        self.data = self.data.append(sd.data)
        self.layerbounderies = layerbounderies
        # self.layerbounderies.sort(axis=0)
        #
        # layercenter = np.array(layerboundery).sum() / 2.
        # self.layercenters = np.append(self.layercenters, layercenter)
        # self.layercenters.sort()
        # sd.data.index = np.array([layercenter])

        # self.data = self.data.append(sd.data)
        return

    def _getXYZ(self):
        """
        This will create three arrays, so when plotted with pcolor each pixel will represent the exact bin width
        """
        binArray = np.repeat(np.array([self.bins]), self.data.index.shape[0], axis=0)
        layerArray = np.repeat(np.array([self.data.index.values]), self.bins.shape[0], axis=0).transpose()
        ext = np.array([np.zeros(self.data.index.values.shape)]).transpose()
        Z = np.append(self.data.values, ext, axis=1)
        return layerArray, binArray, Z

    def plot_eachLayer(self, a=None, normalize=False):
        """
        Plots the distribution of each layer in one plot.

        Returns
        -------
        Handles to the figure and axes of the plot
        """
        if not a:
            f, a = plt.subplots()
        else:
            f = None
            pass
        for iv in self.data.index.values:
            if normalize:
                a.plot(self.bincenters, self.data.loc[iv, :] / self.data.loc[iv, :].max(), label='%i' % iv)
            else:
                a.plot(self.bincenters, self.data.loc[iv, :], label='%i' % iv)
        a.set_xlabel('Particle diameter (nm)')
        a.set_ylabel(get_label(self.distributionType))
        a.legend()
        a.semilogx()
        return f, a


    def plot(self, vmax=None, vmin=None, scale='linear', show_minor_tickLabels=True,
             removeTickLabels=["500", "700", "800", "900"],
             plotOnTheseAxes=False,
             cmap=plt_tools.get_colorMap_intensity(),
             fit_pos=True,
             ax=None,
             colorbar = True):
        """ plots and returns f,a,pc,cb (figure, axis, pcolormeshInstance, colorbar)

        Arguments
        ---------
        scale (optional): ('log',['linear']) - defines how the z-direction is scaled
        vmax
        vmin
        show_minor_tickLabels:
        cma:
        fit_pos (optional): bool [True] - plots the position of a fitted normal distribution onto the plot.
                                          in order for this to work execute fit_normal
        ax (optional):  axes instance [None] - option to plot on existing axes

        """
        X, Y, Z = self._getXYZ()
        Z = np.ma.masked_invalid(Z)
        if type(ax).__name__ in axes_types:
            a = ax
            f = a.get_figure()
        else:
            f, a = plt.subplots()
            # f.autofmt_xdate()

        if scale == 'log':
            scale = LogNorm()
        elif scale == 'linear':
            scale = None

        pc = a.pcolormesh(Y, X, Z, vmin=vmin, vmax=vmax, norm=scale, cmap=cmap)
        a.set_yscale('linear')
        a.set_xscale('log')
        a.set_xlim((self.bins[0], self.bins[-1]))
        a.set_ylabel('Altitude (m)')
        a.set_ylim((self.layercenters[0], self.layercenters[-1]))

        a.set_xlabel('Diameter (nm)')

        a.get_yaxis().set_tick_params(direction='out', which='both')
        a.get_xaxis().set_tick_params(direction='out', which='both')

        if colorbar:
            cb = f.colorbar(pc)
            label = get_label(self.distributionType)
            cb.set_label(label)
        else:
            cb = None

        if self.distributionType != 'calibration':
            a.xaxis.set_minor_formatter(plt.FormatStrFormatter("%i"))
            a.xaxis.set_major_formatter(plt.FormatStrFormatter("%i"))

            f.canvas.draw()  # this is important, otherwise the ticks (at least in case of minor ticks) are not created yet
            ticks = a.xaxis.get_minor_ticks()
            for i in ticks:
                if i.label.get_text() in removeTickLabels:
                    i.label.set_visible(False)

        if fit_pos:
            if 'data_fit_normal' in dir(self):
                a.plot(self.data_fit_normal.Pos, self.layercenters, color='m', linewidth=2, label='normal dist. center')
                leg = a.legend(fancybox=True, framealpha=0.5)
                leg.draw_frame(True)

        return f, a, pc, cb

    #todo: when you want to plot one plot on existing one it will rotated it twice!
    def plot_particle_concentration(self, ax=None, label=None):
        """Plots the particle concentration as a function of altitude.

        Parameters
        ----------
        ax: matplotlib.axes instance, optional
            perform plot on these axes.
        rotate: bool.
            When True the y-axes is the Altitude.
        Returns
        -------
        matplotlib.axes instance

        """

        # ax = SizeDist_TS.plot_particle_concetration(self, ax=ax, label=label)
        # ax.set_xlabel('Altitude (m)')
        #
        # if rotate:
        #     g = ax.get_lines()[-1]
        #     x, y = g.get_xydata().transpose()
        #     xlim = ax.get_xlim()
        #     ylim = ax.get_ylim()
        #     ax.set_xlim(ylim)
        #     ax.set_ylim(xlim)
        #     g.set_xdata(y)
        #     g.set_ydata(x)
        #     xlabel = ax.get_xlabel()
        #     ylabel = ax.get_ylabel()
        #     ax.set_xlabel(ylabel)
        #     ax.set_ylabel(xlabel)


        if type(ax).__name__ in axes_types:
            color = plt_tools.color_cycle[len(ax.get_lines())]
            f = ax.get_figure()
        else:
            f, ax = plt.subplots()
            color = plt_tools.color_cycle[0]

        # layers = self.convert2numberconcentration()

        particles = self.get_particle_concentration().dropna()

        ax.plot(particles.Count_rate.values, particles.index.values, color=color, linewidth=2)

        if label:
            ax.get_lines()[-1].set_label(label)
            ax.legend()

        ax.set_ylabel('Altitude (m)')
        ax.set_xlabel('Particle number concentration (cm$^{-3})$')
        return ax

    def plot_fitres(self, amp=True, rotate=True):
        """ Plots the results from fit_normal

        Arguments
        ---------
        amp: bool.
            if the amplitude is to be plotted
        """

        f, a = plt.subplots()
        a.fill_between(self.layercenters, self.data_fit_normal.Sigma_high, self.data_fit_normal.Sigma_low,
                       color=plt_tools.color_cycle[0],
                       alpha=0.5,
                       )

        self.data_fit_normal.Pos.plot(ax=a, color=plt_tools.color_cycle[0], linewidth=2)
        g = a.get_lines()[-1]
        g.set_label('Center of norm. dist.')
        a.legend(loc=2)

        a.set_ylabel('Particle diameter (nm)')
        a.set_xlabel('Altitude (m)')

        if amp:
            a2 = a.twinx()
            self.data_fit_normal.Amp.plot(ax=a2, color=plt_tools.color_cycle[1], linewidth=2)
            g = a2.get_lines()[-1]
            g.set_label('Amplitude of norm. dist.')
            a2.legend()
            a2.set_ylabel('Amplitude - %s' % (get_label(self.distributionType)))
        else:
            a2 = False
        return f, a, a2

    def plot_angstromex_fit(self):
        if 'angstromexp_fit' not in dir(self):
            raise ValueError('Execute function calculate_angstromex first!')

        f, a = plt.subplots()
        a.plot(self.angstromexp_fit.index, self.angstromexp_fit.data, 'o', color=plt_tools.color_cycle[0],
               label='exp. data')
        a.plot(self.angstromexp_fit.index, self.angstromexp_fit.fit, color=plt_tools.color_cycle[1], label='fit',
               linewidth=2)
        a.set_xlim((self.angstromexp_fit.index.min() * 0.95, self.angstromexp_fit.index.max() * 1.05))
        a.set_ylim((self.angstromexp_fit.data.min() * 0.95, self.angstromexp_fit.data.max() * 1.05))
        a.set_xlabel('Wavelength (nm)')
        a.set_ylabel('AOD')
        a.loglog()
        a.xaxis.set_minor_formatter(plt.FormatStrFormatter("%i"))
        a.yaxis.set_minor_formatter(plt.FormatStrFormatter("%.2f"))
        return a

    def plot_angstromex_LS(self, corr_coeff=False, std=False):
        if 'angstromexp_fit' not in dir(self):
            raise ValueError('Execute function calculate_angstromex first!')

        f, a = plt.subplots()
        a.plot(self.angstromexp_LS.index, self.angstromexp_LS.ang_exp, color=plt_tools.color_cycle[0], linewidth=2,
               label='Angstrom exponent')
        a.set_xlabel('Altitude (m)')
        a.set_ylabel('Angstrom exponent')

        if corr_coeff:
            a.legend(loc=2)
            a2 = a.twinx()
            a2.plot(self.angstromexp_LS.index, self.angstromexp_LS.correlation_coef, color=plt_tools.color_cycle[1],
                    linewidth=2, label='corr_coeff')
            a2.set_ylabel('Correlation coefficiant')
            a2.legend(loc=1)

        if std:
            a.legend(loc=2)
            a2 = a.twinx()
            a2.plot(self.angstromexp_LS.index, self.angstromexp_LS.standard_dif, color=plt_tools.color_cycle[1],
                    linewidth=2, label='corr_coeff')
            a2.set_ylabel('Standard deviation')
            a2.legend(loc=1)

        tmp = (self.angstromexp_LS.index.max() - self.angstromexp_LS.index.min()) * 0.05
        a.set_xlim((self.angstromexp_LS.index.min() - tmp, self.angstromexp_LS.index.max() + tmp))
        return a

    def zoom_altitude(self, bottom, top):
        """'2014-11-24 16:02:30'"""
        dist = self.copy()
        dist.data = dist.data.truncate(before=bottom, after=top)
        where = np.where(np.logical_and(dist.layercenters < top, dist.layercenters > bottom))
        # dist.layercenters = dist.layercenters[where]
        dist.layerbounderies = dist.layerbounderies[where]
        if 'data_fit_normal' in dir(dist):
            dist.data_fit_normal = dist.data_fit_normal.iloc[where]
        return dist

    # dist = self.copy()
    #        dist.data = dist.data.truncate(before=start, after = end)
    #        return dist
    #


    def average_overAltitude(self, window='1S'):
        print('need fixn')
        return False

    #        window = window
    # self.data = self.data.resample(window, closed='right',label='right')
    #        if self.distributionType == 'calibration':
    #            self.data.values[np.where(np.isnan(self.data.values))] = 0
    #        return




    def average_overAllAltitudes(self):
        dataII = self.data.mean(axis=0)
        out = pd.DataFrame(dataII).T
        return SizeDist(out, self.bins, self.distributionType)


    def fit_normal(self):
        """ Fits a single normal distribution to each line in the data frame.

        Returns
        -------
        pandas DataFrame instance (also added to namespace as data_fit_normal)

        """

        super(SizeDist_LS, self).fit_normal()
        self.data_fit_normal.index = self.layercenters
        return self.data_fit_normal

#        singleHist = np.zeros(self.data.shape[1])
#        for i in xrange(self.data.shape[1]):
#            line = self.data.values[:,i]
#            singleHist[i] = np.average(line[~np.isnan(line)])
#        return singleHist


#Todo: bins are redundand
# Todo: some functions should be switched of
class OpticalProperties(object):
    def __init__(self, data, bins):
        # self.data = data['extCoeffPerLayer']
        self.data = data['extCoeff_perrow_perbin']
        self.data_orig = data
        self.AOD = data['AOD']
        self.bins = bins
        self.layercenters = self.data.index.values
        self.asymmetry_parameter_LS = data['asymmetry_param']
        # self.asymmetry_parameter_LS_alt = data['asymmetry_param_alt']

        # ToDo: to define a distribution type does not really make sence ... just to make the stolen plot function happy
        self.distributionType = 'dNdlogDp'

    def get_extinction_coeff_verticle_profile(self):
        """
        Creates a verticle profile of the extinction coefficient.
        """
        ext = self.data.sum(axis=1)
        ext = pd.DataFrame(ext, columns=['ext. coeff.'])
        ext.index.name = 'Altitude'
        out = ExtinctionCoeffVerticlProfile(ext, self, self.wavelength, self.index_of_refractio)
        # out.wavelength = self.wavelength
        # out.n = self.index_of_refractio
        # out.parent = self
        return out

    def plot_AOD_cum(self, color=plt_tools.color_cycle[0], linewidth=2, ax=None, label='cumulative AOD',
                     extra_info=True):
        if not ax:
            f,a = plt.subplots()
        else:
            a = ax
        # a = self.data_orig['AOD_cum'].plot(color=color, linewidth=linewidth, ax=ax, label=label)
        g, = a.plot(self.data_orig['AOD_cum']['AOD per Layer'], self.data_orig['AOD_cum'].index, color=color, linewidth=linewidth, label=label)

        # g = a.get_lines()[-1]
        g.set_label(label)
        a.legend()
        # a.set_xlim(0, 3000)
        a.set_ylabel('Altitude (m)')
        a.set_xlabel('AOD')
        txt = '''$\lambda = %s$ nm
n = %s
AOD = %.4f''' % (self.data_orig['wavelength'], self.data_orig['n'], self.data_orig['AOD'])
        if extra_info:
            a.text(0.7, 0.7, txt, transform=a.transAxes)
        return a

    def _getXYZ(self):
        out = SizeDist_LS._getXYZ(self)
        return out

    def plot_extCoeffPerLayer(self,
                              vmax=None,
                              vmin=None,
                              scale='linear',
                              show_minor_tickLabels=True,
                              removeTickLabels=['500', '700', '800', '900'],
                              plotOnTheseAxes=False, cmap=plt_tools.get_colorMap_intensity(),
                              fit_pos=True,
                              ax=None):
        f, a, pc, cb = SizeDist_LS.plot(self,
                                        vmax=vmax,
                                        vmin=vmin,
                                        scale=scale,
                                        show_minor_tickLabels=show_minor_tickLabels,
                                        removeTickLabels=removeTickLabels,
                                        plotOnTheseAxes=plotOnTheseAxes,
                                        cmap=cmap,
                                        fit_pos=fit_pos,
                                        ax=ax)
        cb.set_label('Extinction coefficient ($m^{-1}$)')

        return f, a, pc, cb


class ExtinctionCoeffVerticlProfile(vertical_profile.VerticalProfile):
    def __init__(self, ext, parent, wavelength, index_of_refraction):
        super(ExtinctionCoeffVerticlProfile, self).__init__(ext)
        self.parent = parent
        self.wavelength = wavelength
        self.index_of_refraction = index_of_refraction

    def plot(self, *args, **kwargs):
        a = super(ExtinctionCoeffVerticlProfile, self).plot(*args, **kwargs)
        a.set_xlabel('Extinction coefficient (m$^{-1}$)')
        return a



def simulate_sizedistribution(diameter=[10, 2500], numberOfDiameters=100, centerOfAerosolMode=200,
                              widthOfAerosolMode=0.2, numberOfParticsInMode=1000):
    """generates a numberconcentration of an aerosol layer which has a gaussian shape when plottet in dN/log(Dp). 
    However, returned is a numberconcentrations (simply the number of particles in each bin, no normalization)
    Returns
        Number concentration (#)
        bin edges (nm)"""

    start = diameter[0]
    end = diameter[1]
    noOfD = numberOfDiameters
    centerDiameter = centerOfAerosolMode
    width = widthOfAerosolMode
    bins = np.linspace(np.log10(start), np.log10(end), noOfD)
    binwidth = bins[1:] - bins[:-1]
    bincenters = (bins[1:] + bins[:-1]) / 2.
    dNDlogDp = plt.mlab.normpdf(bincenters, np.log10(centerDiameter), width)
    extraScale = 1
    scale = 1
    while 1:
        NumberConcent = dNDlogDp * binwidth * scale * extraScale
        if scale != 1:
            break
        else:
            scale = float(numberOfParticsInMode) / NumberConcent.sum()

    binEdges = 10 ** bins
    diameterBinwidth = binEdges[1:] - binEdges[:-1]

    cols = []
    for e, i in enumerate(binEdges[:-1]):
        cols.append(str(i) + '-' + str(binEdges[e + 1]))

    data = pd.DataFrame(np.array([NumberConcent / diameterBinwidth]), columns=cols)
    return SizeDist(data, binEdges, 'dNdDp')


def simulate_sizedistribution_timeseries(diameter=[10, 2500], numberOfDiameters=100, centerOfAerosolMode=200,
                                         widthOfAerosolMode=0.2, numberOfParticsInMode=1000,
                                         startDate='2014-11-24 17:00:00',
                                         endDate='2014-11-24 18:00:00', frequency=10):
    delta = datetime.datetime.strptime(endDate, '%Y-%m-%d %H:%M:%S') - datetime.datetime.strptime(startDate,
                                                                                                  '%Y-%m-%d %H:%M:%S')
    periods = delta.total_seconds() / float(frequency)
    rng = pd.date_range(startDate, periods=periods, freq='%ss' % frequency)

    noOfOsz = 5
    ampOfOsz = 100

    oszi = np.linspace(0, noOfOsz * 2 * np.pi, periods)
    sdArray = np.zeros((periods, numberOfDiameters - 1))
    for e, i in enumerate(rng):
        sdtmp = simulate_sizedistribution(diameter=diameter,
                                          numberOfDiameters=numberOfDiameters,
                                          centerOfAerosolMode=centerOfAerosolMode + (ampOfOsz * np.sin(oszi[e])))
        sdArray[e] = sdtmp.data
    sdts = pd.DataFrame(sdArray, index=rng, columns=sdtmp.data.columns)
    return SizeDist_TS(sdts, sdtmp.bins, sdtmp.distributionType)


def simulate_sizedistribution_layerseries(diameter=[10, 2500], numberOfDiameters=100, heightlimits=[0, 6000],
                                          noOflayers=100, layerHeight=[500., 4000.], layerThickness=[100., 300.],
                                          layerDensity=[1000., 5000.], layerModecenter=[200., 800.], widthOfAerosolMode = 0.2 ):
    gaussian = lambda x, mu, sig: np.exp(-(x - mu) ** 2 / (2 * sig ** 2))

    lbt = np.linspace(heightlimits[0], heightlimits[1], noOflayers + 1)
    layerbounderies = np.array([lbt[:-1], lbt[1:]]).transpose()
    layercenter = (lbt[1:] + lbt[:-1]) / 2.

    # strata = np.linspace(heightlimits[0],heightlimits[1],noOflayers+1)

    layerArray = np.zeros((noOflayers, numberOfDiameters - 1))

    for e, stra in enumerate(layercenter):
        for i, lay in enumerate(layerHeight):
            sdtmp = simulate_sizedistribution(diameter=diameter, numberOfDiameters=numberOfDiameters,
                                              widthOfAerosolMode=widthOfAerosolMode, centerOfAerosolMode=layerModecenter[i],
                                              numberOfParticsInMode=layerDensity[i])
            layerArray[e] += sdtmp.data.values[0] * gaussian(stra, layerHeight[i], layerThickness[i])

    sdls = pd.DataFrame(layerArray, index=layercenter, columns=sdtmp.data.columns)
    return SizeDist_LS(sdls, sdtmp.bins, sdtmp.distributionType, layerbounderies)


def generate_aerosolLayer(diameter=[.01, 2.5], numberOfDiameters=30, centerOfAerosolMode=0.6,
                          widthOfAerosolMode=0.2, numberOfParticsInMode=10000, layerBoundery=[0., 10000], ):
    """Probably deprecated!?! generates a numberconcentration of an aerosol layer which has a gaussian shape when plottet in dN/log(Dp). 
    However, returned is a numberconcentrations (simply the number of particles in each bin, no normalization)
    Returns
        Number concentration (#)
        bin edges (nm)"""

    layerBoundery = np.array(layerBoundery)
    start = diameter[0]
    end = diameter[1]
    noOfD = numberOfDiameters
    centerDiameter = centerOfAerosolMode
    width = widthOfAerosolMode
    bins = np.linspace(np.log10(start), np.log10(end), noOfD)
    binwidth = bins[1:] - bins[:-1]
    bincenters = (bins[1:] + bins[:-1]) / 2.
    dNDlogDp = plt.mlab.normpdf(bincenters, np.log10(centerDiameter), width)
    extraScale = 1
    scale = 1
    while 1:
        NumberConcent = dNDlogDp * binwidth * scale * extraScale
        if scale != 1:
            break
        else:
            scale = float(numberOfParticsInMode) / NumberConcent.sum()

    binEdges = 10 ** bins
    # diameterBinCenters = (binEdges[1:] + binEdges[:-1])/2.
    diameterBinwidth = binEdges[1:] - binEdges[:-1]

    cols = []
    for e, i in enumerate(binEdges[:-1]):
        cols.append(str(i) + '-' + str(binEdges[e + 1]))

    layerBoundery = np.array([0., 10000.])
    # layerThickness = layerBoundery[1:] - layerBoundery[:-1]
    layerCenter = [5000.]
    data = pd.DataFrame(np.array([NumberConcent / diameterBinwidth]), index=layerCenter, columns=cols)
    # return data

    #     atmosAerosolNumberConcentration = pd.DataFrame()
    # atmosAerosolNumberConcentration['bin_center'] = pd.Series(diameterBinCenters)
    #     atmosAerosolNumberConcentration['bin_start'] = pd.Series(binEdges[:-1])
    #     atmosAerosolNumberConcentration['bin_end'] = pd.Series(binEdges[1:])
    #     atmosAerosolNumberConcentration['numberConcentration'] = pd.Series(NumberConcent)
    #     return atmosAerosolNumberConcentration

    return SizeDist_LS(data, binEdges, 'dNdDp', layerBoundery)


def test_generate_numberConcentration():
    """result should look identical to Atmospheric Chemistry and Physis page 422"""
    nc = generate_aerosolLayer(diameter=[0.01, 10], centerOfAerosolMode=0.8, widthOfAerosolMode=0.3,
                               numberOfDiameters=100, numberOfParticsInMode=1000, layerBoundery=[0.0, 10000])

    plt.plot(nc.bincenters, nc.data.values[0].transpose() * nc.binwidth, label='numberConc')
    plt.plot(nc.bincenters, nc.data.values[0].transpose(), label='numberDist')
    ncLN = nc.convert2dNdlogDp()
    plt.plot(ncLN.bincenters, ncLN.data.values[0].transpose(), label='LogNormal')
    plt.legend()
    plt.semilogx()


def _perform_Miecalculations(diam, wavelength, n, noOfAngles=100.):
    """
    Performs Mie calculations

    Parameters
    ----------
    diam:       NumPy array of floats
                Array of diameters over which to perform Mie calculations; units are um
    wavelength: float
                Wavelength of light in um for which to perform calculations
    n:          complex
                Ensemble complex index of refraction

    Returns
        panda DataTable with the diameters as the index and the mie results in the different collumns
        total_extinction_coefficient: this takes the sum of all particles crossections of the particular diameter in a qubic
                                      meter. This is in principle the AOD of an L

    """


    diam = np.asarray(diam)

    extinction_efficiency = np.zeros(diam.shape)
    scattering_efficiency = np.zeros(diam.shape)
    absorption_efficiency = np.zeros(diam.shape)

    extinction_crossection = np.zeros(diam.shape)
    scattering_crossection = np.zeros(diam.shape)
    absorption_crossection = np.zeros(diam.shape)

    # phase_function_natural = pd.DataFrame()
    angular_scattering_natural = pd.DataFrame()
    # extinction_coefficient = np.zeros(diam.shape)
    # scattering_coefficient = np.zeros(diam.shape)
    # absorption_coefficient = np.zeros(diam.shape)



    # Function for calculating the size parameter for wavelength l and radius r
    sp = lambda r, l: 2. * np.pi * r / l
    for e, d in enumerate(diam):
        radius = d / 2.

        # print('sp(radius, wavelength)', sp(radius, wavelength))
        # print('n', n)
        # print('d', d)

        mie = bhmie.bhmie_hagen(sp(radius, wavelength), n, noOfAngles, diameter=d)
        values = mie.return_Values_as_dict()
        extinction_efficiency[e] = values['extinction_efficiency']

        # print("values['extinction_crosssection']",values['extinction_crosssection'])


        scattering_efficiency[e] = values['scattering_efficiency']
        absorption_efficiency[e] = values['extinction_efficiency'] - values['scattering_efficiency']

        extinction_crossection[e] = values['extinction_crosssection']
        scattering_crossection[e] = values['scattering_crosssection']
        absorption_crossection[e] = values['extinction_crosssection'] - values['scattering_crosssection']

        # phase_function_natural[d] = values['phaseFct_natural']['Phase_function_natural'].values
        angular_scattering_natural[d] = mie.get_angular_scatt_func().natural.values

        # print('\n')

    # phase_function_natural.index = values['phaseFct_natural'].index
    angular_scattering_natural.index = mie.get_angular_scatt_func().index

    out = pd.DataFrame(index=diam)
    out['extinction_efficiency'] = pd.Series(extinction_efficiency, index=diam)
    out['scattering_efficiency'] = pd.Series(scattering_efficiency, index=diam)
    out['absorption_efficiency'] = pd.Series(absorption_efficiency, index=diam)

    out['extinction_crossection'] = pd.Series(extinction_crossection, index=diam)
    out['scattering_crossection'] = pd.Series(scattering_crossection, index=diam)
    out['absorption_crossection'] = pd.Series(absorption_crossection, index=diam)
    return out, angular_scattering_natural


def _get_coefficients(crossection, cn):
    """
    Calculates the extinction, scattering or absorbtion coefficient

    Parameters
    ----------
    crosssection:   float
                    Units are um^2
    cn:             float
                    Particle concentration in cc^-1

    Returns
    --------
    coefficient in m^-1.  This is the differential AOD.
    """
    crossection = crossection.copy()
    cn = cn.copy()
    crossection *= 1e-12  # conversion from um^2 to m^2
    cn *= 1e6  # conversion from cm^-3 to m^-3
    coefficient = cn * crossection

    # print('cn',cn)
    # print('crossection', crossection)
    # print('coeff',coefficient)
    # print('\n')

    return coefficient


def test_ext_coeff_vertical_profile():
    #todo: make this a real test
    dist = simulate_sizedistribution_layerseries(layerHeight=[3000.0, 3000.0],
                                               layerDensity=[1000.0, 100.0],
                                               layerModecenter=[100.0, 100.0],
                                               layerThickness=[6000, 6000],
                                               widthOfAerosolMode = 0.01,
                                               noOflayers=3,
                                               numberOfDiameters=1000)
    dist.plot()


    dist = dist.zoom_diameter(99,101)
    avg = dist.average_overAllAltitudes()
    f,a = avg.plot()
    a.set_xscale('linear')

    opt = dist.calculate_optical_properties(550, n = 1.455)
    opt_II = dist.calculate_optical_properties(550, n = 1.1)
    opt_III = dist.calculate_optical_properties(550, n = 4.)

    ext = opt.get_extinction_coeff_verticle_profile()
    ext_II = opt_II.get_extinction_coeff_verticle_profile()
    ext_III = opt_III.get_extinction_coeff_verticle_profile()

    tvI_is = (ext_III.data/ext.data).values[0][0]
    tvI_want = 14.3980239083
    tvII_is = (ext_II.data/ext.data).values[0][0]
    tvII_want = 0.05272993413

    print('small deviations could come from averaging over multiple bins with slightly different diameter')
    print('test values 1 is/should_be: %s/%s'%(tvI_is,tvI_want))
    print('test values 2 is/should_be: %s/%s'%(tvII_is,tvII_want))

    return False