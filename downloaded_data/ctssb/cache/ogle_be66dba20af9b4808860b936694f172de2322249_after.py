import os
import numpy as np
import pandas as pd
from scipy.stats import linregress
from tsfresh import extract_features
from tsfresh.utilities.dataframe_functions import impute
import matplotlib.pyplot as plt
from astropy.time import Time
from copy import deepcopy
from toposort import toposort_flatten
from fats_features import Feature, get_all_subclasses
from collections import OrderedDict
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels \
    import RBF, WhiteKernel, ExpSineSquared, RationalQuadratic


dateparser = lambda x: Time(np.float32(x), format='jd')


class LC(object):
    _column_names = ['mjd', 'mag', 'err']

    def __init__(self, path):
        self.dir, self.fname = os.path.split(path)
        self.data = pd.read_table(path, sep=" ", names=self._column_names,
                                  engine='python', usecols=[0, 1, 2])
                                  # parse_dates=['mjd'],
                                  # date_parser=dateparser)
        self.features = None

    def __copy__(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))
        return result

    def __len__(self):
        return len(self.data)

    def save(self, fname, sep=" "):
        self.data.to_csv(fname, sep=sep, header=False, index=False)

    def plot(self, fig=None, fmt='.k'):
        if not fig:
            fig = plt.figure()
        mjd = self.mjd
        mag = self.mag
        err = self.err
        plt.errorbar(mjd, mag, err, fmt=fmt)
        plt.gca().invert_yaxis()
        plt.show()
        return fig

    def add_features(self, df):
        if self.features is None:
            self.features = df
        else:
            self.features = pd.concat([self.features, df], axis=1)

    @property
    def features_names(self):
        return self.features.columns

    @property
    def mag(self):
        return self.data['mag']

    @mag.setter
    def mag(self, other):
        self.data['mag'] = other

    @property
    def mjd(self):
        return self.data['mjd']

    @property
    def datetime(self):
        """
        Return times as python datetime objects. Could be used as ``dates``
        argument in ``statsmodels.tsa`` objects.

        >>> from statsmodels.tsa.ar_model import AR
        >>> ar = AR(lc.mag, dates=lc.datetime)
        >>> result = ar.fit(maxlag=1, method='mle')

        """
        t = Time(self.data['mjd'], format='jd', scale='utc')
        t = [t_.datetime for t_ in t]
        return t

    @property
    def err(self):
        return self.data['err']

    @err.setter
    def err(self, other):
        self.data['err'] = other

    def generate_features_tsfresh(self, do_impute=False):
        """
        Generate features using ``tsfresh`` package.

        :param do_impute:
            Logical. Use ``tsfresh`` impute function? (default: ``True``)

        :return:
            Pandas Dataframe with features.
        """
        df = self.data[['mjd', 'mag']]
        df.columns = ['time', 'value']
        df['id'] = np.zeros(len(self.data), dtype=int)
        extracted_features = extract_features(df, column_id="id",
                                              column_sort="time",
                                              column_value="value",
                                              n_processes=1)
        if do_impute:
            extracted_features = impute(extracted_features)
        return extracted_features

    def generate_features_fats(self):
        """
        Generate features from FATS.

        :return:
            Pandas Dataframe with calculated features.
        """
        data_available_combs = (['magnitude'],
                                ['magnitude', 'time'],
                                ['magnitude', 'time', 'error'])
        data = self.data[['mag', 'mjd', 'err']]
        data = np.atleast_2d(data).T

        features_dfs = list()
        for data_available in data_available_combs:

            features = get_all_subclasses(Feature)
            features_names = {feature: feature.get_subclass_name() for feature
                              in features}
            features_names_inv = dict((v, k) for k, v in
                                      features_names.iteritems())
            features_available = [feature for feature in features if
                                  feature.Data == data_available]
            features_available = {features_names[feature]: feature.depends for
                                  feature
                                  in features_available}

            features_sorted = list(toposort_flatten(features_available))
            features_instances = OrderedDict()
            for f in features_sorted:
                init_dict = {ff: features_instances[ff] for ff in
                             features_names_inv[f].depends}
                features_instances[f] = features_names_inv[f](**init_dict)
                features_instances[f].fit(data)
            feature_values = OrderedDict()
            for key, value in features_instances.items():
                feature_values[key] = value.value

            features_df = pd.DataFrame([feature_values],
                                       columns=feature_values.keys())
            features_dfs.append(features_df)

        return pd.concat(features_dfs, axis=1)

    def roll(self, delta):
        """
        Roll data on integer number of measurements.

        :param delta:
            Integer - number of measurements to roll the data.
        :return:
            Instance of ``LC`` with rolled data.
        """
        rolled = deepcopy(self)
        rolled.data[self._column_names] = np.roll(self.data[self._column_names],
                                                  delta, axis=0)
        return rolled

    def add_noise(self, sigma, update_err=False):
        """
        Add noise to magnitudes.

        :param sigma:
            STD of normal noise added.
        :return:
            Instance of ``LC`` with noised data.
        """
        noised = deepcopy(self)
        noised.mag += np.random.normal(0., sigma, len(noised))
        if update_err:
            noised.data['err'] = noised.data['err'].apply(lambda x:
                                                          np.sqrt(x**2 +
                                                                  sigma**2))
        return noised

    def add_trend(self, a, b):
        """
        Add trend to magnitudes.

        :param a:
            Slope of linear trend.
        :param b:
            Intercept of linear trend. Value at first measured time moment.
        :return:
            Instance of ``LC`` with trended data.
        """
        trended = deepcopy(self)
        mjd = trended.mjd
        mjd -= mjd[0]
        trended.mag += a*mjd + b
        return trended

    def estimate_trend(self):
        """
        Estimate linear trend of the light curve.

        :return:
        slope : float
            Slope of the regression line normed on median magnitude.
        intercept : float
            Intercept of the regression line centered on median magnitude.
        rvalue : float
            correlation coefficient
        pvalue : float
            two-sided p-value for a hypothesis test whose null hypothesis is
            that the slope is zero.
        stderr : float
            Standard error of the estimated gradient.
        """
        time = self.mjd
        time -= time[0]
        result = linregress(time, self.mag)
        slope, intercept, R, p, _ = result
        print(slope, intercept, R, p, _)
        return slope/self.mag.median(), intercept-self.mag.median(), R, p, _


class VariableStarLC(LC):

    def __init__(self, fname):
        super(VariableStarLC, self).__init__(fname)
        self._gp = None

    def generate(self, lc, n_samples=1):
        """
        Generate light curve using fitted Gaussian Process on current instance
        of ``LC`` and observations of some other instance of ``LC``.
        :param lc:
            Instance of ``LC``.
        :param n_samples: (optional)
            Number of generated light curves to return. (default: ``1``)

        :return:
            Generator of ``LC`` instances.
        """
        data = lc.data[['mjd', 'mag', 'err']]
        data = np.atleast_2d(data)
        time = data[:, 0] - data[0, 0]
        time = np.atleast_2d(time).T
        samples_mag = self._gp.sample_y(time, n_samples=n_samples)
        for samples in samples_mag.T:
            lc.mag = samples
            lc.err = self.err
            yield lc

    def generate_artificial_lc_files(self, bg_fname, n=1, out_dir=None):
        """
        Using fitted instance ``self`` and some file with other light curve
        generate ``n`` files with artificial variable light curves.

        :param bg_fname:
            Path to file with some light curve that will be substituted by
            simulated light curves.
        :param n: (optional)
            Number of different artificial light curves to create and save to
            different files.
        :param out_dir: (optional)
            Directory to save created files. If ``None`` then use CWD. (default:
            ``None``)

        :return:
            Creates ``n`` files with simulated light curves using fitted
            instance of ``self``. Output files will be located in directory
            ``out_dir`` and have names ``self.fname_1``, ``self.fname_2``, etc.
        """
        if out_dir is None:
            out_dir = os.getcwd()

        bg_lc = LC(bg_fname)
        for i, lc in enumerate(self.generate(bg_lc, n_samples=n)):
            outname = "{}_{}".format(self.fname, i+1)
            print("Saving generated LC to {}".format(outname))
            lc.save(os.path.join(out_dir, outname))

    def plot_fitted(self, fig=None):
        data = self.data[['mjd', 'mag', 'err']]
        data = np.atleast_2d(data)
        time = data[:, 0] - data[0, 0]
        time = np.atleast_2d(time).T

        X_ = np.linspace(time.min() - 50,
                         time.max() + 50, 1000)[:, np.newaxis]
        y_pred, y_std = self._gp.predict(X_, return_std=True)
        if not fig:
            fig = plt.figure()
        plt.errorbar(time, data[:, 1], data[:, 2], fmt='k.')
        plt.plot(X_, y_pred)
        plt.fill_between(X_[:, 0], y_pred - y_std, y_pred + y_std,
                         alpha=0.5, color='k')
        plt.xlim(X_.min(), X_.max())
        plt.gca().invert_yaxis()
        plt.xlabel("MJD from {}".format(data[0, 0] - 50))
        plt.ylabel("Magnitude")
        plt.tight_layout()
        plt.show()


class PeriodicLC(VariableStarLC):

    def fit(self, long_term_length_scale=None,
            pre_periodic_term_length_scale=None,
            periodic_term_length_scale=None, periodicity=None,
            noise_level=None, do_plot=False, fig=None):

        data = self.data[['mjd', 'mag', 'err']]
        data = np.atleast_2d(data)
        time = data[:, 0] - data[0, 0]
        time = np.atleast_2d(time).T

        if self._gp is None:
            time_scale = data[-1, 0] - data[0, 0]
            data_scale = np.max(data[:, 1]) - np.min(data[:, 1])
            noise_std = np.median(data[:, 2])

            if long_term_length_scale is None:
                long_term_length_scale = 0.5 * time_scale

            if pre_periodic_term_length_scale is None:
                pre_periodic_term_length_scale = 0.5 * time_scale

            if periodic_term_length_scale is None:
                periodic_term_length_scale = 0.1 * time_scale

            if periodicity is None:
                periodicity = 0.1 * time_scale

            if noise_level is None:
                noise_level = noise_std

            k1 = data_scale ** 2 * RBF(length_scale=long_term_length_scale)
            k2 = 0.1 * data_scale *\
                 RBF(length_scale=pre_periodic_term_length_scale) *\
                 ExpSineSquared(length_scale=periodic_term_length_scale,
                                periodicity=periodicity)
            k3 = WhiteKernel(noise_level=noise_level ** 2,
                             noise_level_bounds=(1e-3, 1.))
            kernel = k1 + k2 + k3
            gp = GaussianProcessRegressor(kernel=kernel,
                                          alpha=(data[:, 2] / data[:, 1]) ** 2,
                                          normalize_y=True,
                                          n_restarts_optimizer=10)
            gp.fit(time, data[:, 1])
            self._gp = gp

        if do_plot:
            self.plot_fitted(fig=fig)


class APeriodicLC(VariableStarLC):

    def fit(self, long_term_length_scale=None, short_term_length_scale=None,
            noise_level=None, do_plot=False, fig=None):

        data = self.data[['mjd', 'mag', 'err']]
        data = np.atleast_2d(data)
        time = data[:, 0] - data[0, 0]
        time = np.atleast_2d(time).T

        if self._gp is None:
            time_scale = data[-1, 0] - data[0, 0]
            data_scale = np.max(data[:, 1]) - np.min(data[:, 1])
            noise_std = np.median(data[:, 2])

            if long_term_length_scale is None:
                long_term_length_scale = 0.5 * time_scale

            if short_term_length_scale is None:
                short_term_length_scale = 0.05 * time_scale

            if noise_level is None:
                noise_level = noise_std

            k1 = data_scale ** 2 *\
                 RationalQuadratic(length_scale=long_term_length_scale)
            k2 = 0.1 * data_scale * RBF(length_scale=short_term_length_scale)
            k3 = WhiteKernel(noise_level=noise_level ** 2,
                             noise_level_bounds=(1e-3, np.inf))
            kernel = k1 + k2 + k3
            gp = GaussianProcessRegressor(kernel=kernel,
                                          alpha=(data[:, 2] / data[:, 1]) ** 2,
                                          normalize_y=True)
            gp.fit(time, data[:, 1])
            self._gp = gp

        if do_plot:
            self.plot_fitted(fig=fig)


if __name__ == '__main__':
    # # Test features calculation
    # lc = PeriodicLC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_28995.dat')
    # features_fats = lc.generate_features_fats()
    # features_tsfresh = lc.generate_features_tsfresh()
    # lc.add_features(features_fats)
    # lc.add_features(features_tsfresh)
    # print(lc.features)

    # # Test periodic variable
    # lc = PeriodicLC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_28995.dat')
    # lc.fit(do_plot=True)
    # # This LC gives us data points where to generate new LCs
    # lc_ = LC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_180039.dat')
    # for lc__ in lc.generate(lc_, n_samples=4):
    #     lc__.plot()

    # # Test a-periodic variable
    # lc = APeriodicLC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_38470.dat')
    # lc.fit(do_plot=True)
    # lc_ = LC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_180039.dat')
    # for lc__ in lc.generate(lc_, n_samples=4):
    #     lc__.plot()

    # # Test trend
    # lc = LC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_25801.dat')
    # lc.plot()
    # slope, intercept, R, p, _ = lc.estimate_trend()

    # Test creation of files with artificial light curves.
    lc = PeriodicLC('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_28995.dat')
    lc.fit(do_plot=True)
    out_dir = '/home/ilya/github/ogle'
    lc.generate_artificial_lc_files('/home/ilya/Dropbox/papers/ogle2/data/sc19/lmc_sc19_i_180039.dat',
                                    n=5, out_dir=out_dir)