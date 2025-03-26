#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Model for fitting an absorption profile to spectral data. """

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)

__all__ = ["ProfileFittingModel"]

import logging
import numpy as np
import scipy.optimize as op
from astropy.table import Row
from astropy.constants import c as speed_of_light
from collections import OrderedDict
from scipy.special import wofz
from scipy import integrate

from .base import BaseSpectralModel

logger = logging.getLogger(__name__)


def _gaussian(x, *parameters):
    """
    Evaluate a Gaussian profile at x, given the profile parameters.

        y = amplitude * exp(-(x - position)**2 / (2.0 * sigma**2))

    :param x:
        The x-values to evaluate the Gaussian profile at.

    :param parameters:
        The position, sigma, and amplitude of the Gaussian profile.
    """
    position, sigma, amplitude = parameters
    return amplitude * np.exp(-(x - position)**2 / (2.0 * sigma**2))


def _lorentzian(x, *parameters):
    """
    Evaluate a Lorentzian profile at x, given the profile parameters:

        y = (amplitude/PI) * (width/((x - positions)**2 + width**2))

    :param x:
        The x-values to evaluate the Lorentzian profile at.

    :param parameters:
        The position, width, and amplitude of the Lorentzian profile.
    """
    position, width, amplitude = parameters
    return (amplitude/np.pi) * (width/((x - position)**2 + width**2))


def _voigt(x, *parameters):
    """
    Evaluate a Voigt profile at x, given the profile parameters.

    :param x:
        The x-values to evaluate the Voigt profile at.

    :param parameters:
        The position, fwhm, amplitude, and shape of the Voigt profile.
    """
    try:
        n = len(x)
    except TypeError:
        n = 1

    position, fwhm, amplitude, shape = parameters
    
    profile = 1 / wofz(np.zeros((n)) + 1j * np.sqrt(np.log(2.0)) * shape).real
    profile *= amplitude * wofz(2*np.sqrt(np.log(2.0)) * (x - position)/fwhm \
        + 1j * np.sqrt(np.log(2.0))*shape).real
    return profile



class ProfileFittingModel(BaseSpectralModel):

    _profiles = {
        "gaussian": (_gaussian, ("mean", "sigma", "amplitude")),
        "lorentzian": (_lorentzian, ("mean", "width", "amplitude")),
        "voigt": (_voigt, ("mean", "fwhm", "amplitude", "shape"))
    }

    def __init__(self, transitions, session, **kwargs):
        """
        A class to fit spectral data with an absorption profile and continuum.

        :param transitions:
            Row(s) from a line list of transitions to associate with this model.

        :param session:
            The parent session that this model will be associated with.
        """

        super(ProfileFittingModel, self).__init__(
            transitions, session, **kwargs)

        # Initialize metadata with default fitting values.
        self.metadata.update({
            "profile": "gaussian",
            "central_weighting": True,
            "window": 5,
            "continuum_order": 2,
            "detection_sigma": 1.0,
            "detection_pixels": 5,
            "max_iterations": 5,
            "wavelength_tolerance": 0.1,
            "velocity_tolerance": None,
            "mask": [],
            "elements": [self._verify_elements()]
        })

        # Set the model parameter names based on the current metadata.
        self._update_parameter_names()
        self._verify_transitions()
        self._verify_metadata()

        return None


    def _verify_transitions(self):
        """
        Verify that the atomic or molecular transitions associated with this
        class are valid.
        """

        # Check format first.
        super(ProfileFittingModel, self)._verify_transitions()
        if len(self.transitions) > 1 and not isinstance(self.transitions, Row):
            raise ValueError("only a single transition can be associated with "
                             "a ProfileFittingModel")

        # Check that the transition does not have multiple element names.
        if self.transitions["elem2"][0] != "":
            raise ValueError("only an atomic transition can be associated with "
                             "a ProfileFittingModel")
        return True


    def _verify_elements(self):
        """
        Return the element that will be measured by this model.
        """
        return self.transitions["elem1"][0]
        

    def _verify_metadata(self):
        """
        Verify the metadata associated with this class.
        """
        # TODO
        return True


    def _update_parameter_names(self):
        """
        Update the model parameter names based on the current metadata.
        """

        # Profile parameter names.
        func, parameter_names = self._profiles[self.metadata["profile"]]
        parameter_names = list(parameter_names)

        # Continuum coefficients.
        parameter_names += ["c{0}".format(i) \
            for i in range(self.metadata["continuum_order"] + 1)]

        # Update the bounds.
        bounds = {}
        if self.metadata["profile"] == "gaussian":
            bounds["sigma"] = (-0.5, 0.5)
        elif self.metadata["profile"] == "voigt":
            bounds["fwhm"] = (-0.5, 0.5)

        
        if self.metadata["wavelength_tolerance"] is not None \
        or self.metadata["velocity_tolerance"] is not None:

            # Convert velocity tolerance into wavelength.
            wavelength = self.transitions["wavelength"]
            try:
                wavelength = wavelength[0]
            except IndexError:
                None
            vt = abs(self.metadata.get("velocity_tolerance", None) or np.inf)
            wt = abs(self.metadata.get("wavelength_tolerance", None) or np.inf)

            bound = np.nanmin([
                wt, wavelength * vt/speed_of_light.to("km/s").value])

            bounds["mean"] = (wavelength - bound, wavelength + bound)

        else:
            # TODO: Allow the wavelength to be fixed.
            raise NotImplementedError("wavelength cannot be fixed yet; "
                                      "set a small tolerance on wavelength")

        self._parameter_names = parameter_names
        self._parameter_bounds = bounds

        return True


    def _initial_guess(self, spectrum, **kwargs):
        """
        Generate an initial guess for the model parameters.

        :param spectrum:
            The observed spectrum.
        """

        wavelength = self.transitions["wavelength"]
        try:
            wavelength = wavelength[0]
        except IndexError:
            None

        p0 = [
            wavelength,
            kwargs.pop("p0_sigma", 0.1),
        ]

        if spectrum is None:
            p0.append(0.5)
        else:
            p0.append(1.0 - \
                spectrum.flux[spectrum.dispersion.searchsorted(wavelength)])

        if self.metadata["profile"] == "voigt":
            p0.append(kwargs.pop("p0_shape", 0))

        # Continuum?
        if self.metadata["continuum_order"] > -1:
            p0.extend(([0] * self.metadata["continuum_order"]) + [1])

        return np.array(p0)


    def fit(self, spectrum=None, **kwargs):
        """
        Fit an asborption profile to the transition in the spectrum.

        :param spectrum: [optional]
            The observed spectrum to fit the profile transition model. If None
            is given, this will default to the normalized rest-frame spectrum in
            the parent session.
        """

        spectrum = self._verify_spectrum(spectrum)
        
        failure = False

        # Update internal metadata with any input parameters.
        # Ignore additional parameters because other BaseSpectralModels will
        # have different input arguments.
        for key in set(self.metadata).intersection(kwargs):
            self.metadata[key] = kwargs[key]

        # What model parameters are in the fitting process?
        # In synth these would be abundances, etc. Here they are profile/cont
        # parameters.
        self._update_parameter_names()
        
        # Get a bad initial guess.
        p0 = self._initial_guess(spectrum, **kwargs)

        # Build a mask based on the window fitting range, and prepare the data.
        mask = self.mask(spectrum)
        x, y = spectrum.dispersion[mask], spectrum.flux[mask]
        yerr, absolute_sigma = ((1.0/spectrum.ivar[mask])**0.5, True)
        if not np.all(np.isfinite(yerr)):
            yerr, absolute_sigma = (np.ones_like(x), False)

        # Central weighting?
        if self.metadata["central_weighting"]:
            yerr /= (1 + np.exp(-(x - p0[0])**2 / (4.0 * p0[1]**2)))

        # How many iterations to do?
        nearby_lines = []
        iterative_mask = np.isfinite(y * yerr)
        for iteration in range(self.metadata["max_iterations"]):
                
            if not any(iterative_mask):
                raise Failed

            try:
                p_opt, p_cov = op.curve_fit(self.fitting_function, 
                    xdata=x[iterative_mask],
                    ydata=y[iterative_mask],
                    sigma=yerr[iterative_mask],
                    p0=p0, absolute_sigma=absolute_sigma)

            except:
                logger.exception(
                    "Exception raised in fitting atomic transition {0} "\
                    "on iteration {1}".format(
                        wavelength,
                        iteration))
                if iteration == 0:
                    return failure

            # Look for outliers peaks.
            # TODO: use continuum or model?
            O = self.metadata["continuum_order"]
            continuum = np.ones_like(x) \
                if 0 > O else np.polyval(p_opt[-(O + 1):], x)    

            model = self(x, *p_opt)
            
            sigmas = (y - model)/np.std(y[iterative_mask])
            sigmas[~iterative_mask] = 0 # Ignore points that are already masked
            outliers = np.where(sigmas < -self.metadata["detection_sigma"])[0]

            # Look for groups of neighbouring outlier points.
            separators = np.repeat(1 + np.where(np.diff(outliers) > 1)[0], 2)
            separators = np.hstack([0, separators, None]).reshape(-1, 2)

            for start, end in separators:
                indices = outliers[start:end]

                # Require a minimum group size by number of pixels.
                if indices.size < self.metadata["detection_pixels"]: continue

                # Try and fit an absorption function to the centroid of the
                # region.

                lower_group_wl = x[indices[0]]
                upper_group_wl = x[indices[-1]]

                def model_nearby_line(x_, *p):
                    # Strict requirements on these parameters, since we don't
                    # need to know them precisely.
                    if not (lower_group_wl <= p[0] <= upper_group_wl) \
                    or abs(p[1]) > p_opt[1] \
                    or not (1 >= p[2] > 0):
                        return np.nan * np.ones_like(x_)
                    
                    return model[iterative_mask] * self(x_, *p)

                # Initial parameters for this line.
                p0_outlier = [
                    np.mean(x[indices]),
                    0.5 * p_opt[1],
                    np.max(continuum[indices] - y[indices])
                ]
                if self.metadata["profile"] == "voigt":
                    p0_outlier.append(p0[3])

                try:
                    p_out, cov = op.curve_fit(model_nearby_line,
                            xdata=x[iterative_mask],
                            ydata=y[iterative_mask],
                            sigma=yerr[iterative_mask],
                            p0=p0_outlier, absolute_sigma=absolute_sigma,
                            check_finite=True)

                except:
                    # Just take a narrow range and exclude that?
                    # TODO: The old SMH just did nothing in this scenario, but
                    #       we may want to revise that behaviour.
                    None

                else:

                    # Exclude +/- 3 sigma of the fitted line
                    l, u = (p_out[0] - 3 * p_out[1], p_out[0] + 3 * p_out[1])
                    
                    # Store this line and the region masked out by it.
                    nearby_lines.append([p_out, (u, l)])

                    # Now update the iterative mask to exclude this line.                    
                    iterative_mask *= ~((u > x) * (x > l))

            # Update p0 with the best guess from this iteration.
            p0 = p_opt.copy()

        # Finished looking for neighbouring lines
        # `max_iterations` rounds of removing nearby lines. Now do final fit:
        p_opt, p_cov = op.curve_fit(self.fitting_function, 
            xdata=x[iterative_mask],
            ydata=y[iterative_mask],
            sigma=yerr[iterative_mask],
            p0=p0, absolute_sigma=absolute_sigma)

        assert p_cov is not None

        # Make many draws from the covariance matrix.
        draws = kwargs.pop("covariance_draws", 100)
        percentiles = kwargs.pop("percentiles", (2.5, 97.5))
        if np.all(np.isfinite(p_cov)):
            p_alt = np.random.multivariate_normal(p_opt, p_cov, size=draws)
        else:
            p_alt = np.nan * np.ones((draws, p_opt.size))

        # Integrate the profile.
        profile, _ = self._profiles[self.metadata["profile"]]
        if profile == _gaussian:
            ew = p_opt[1] * p_opt[2] * np.sqrt(2 * np.pi)
            ew_alt = p_alt[:, 1] * p_alt[:, 2] * np.sqrt(2 * np.pi)
            ew_uncertainty = np.percentile(ew_alt, percentiles) - ew

        else:
            N, integrate_sigma = (len(_), kwargs.pop("integrate_sigma", 10))
            l, u = (
                p_opt[0] - integrate_sigma * p_opt[1],
                p_opt[0] + integrate_sigma * p_opt[1]
            )

            ew = integrate.quad(profile, l, u, args=tuple(p_opt[:N]))[0]
            ew_alt = [integrate.quad(profile, l, u, args=tuple(_[:N]))[0] \
                for _ in p_alt]
            ew_uncertainty = np.percentile(ew_alt, percentiles) - ew
        
        # Calculate chi-square for the points that we modelled.
        ivar = spectrum.ivar[mask][iterative_mask]
        if not np.any(np.isfinite(ivar)): ivar = 1
        chi_sq = (y[iterative_mask] - self(x[iterative_mask], *p_opt))**2 * ivar

        dof = np.isfinite(chi_sq).sum() - len(p_opt) - 1
        chi_sq = np.nansum(chi_sq)
        

        model_y = self(x, *p_opt)
        model_yerr = np.percentile(
            [self(x, *_) for _ in p_alt], percentiles, axis=0) - model_y

        """
        # DEBUG PLOT
        fig, ax = plt.subplots()
        ax.plot(x, y, c='k', drawstyle='steps-mid')

        O = self.metadata["continuum_order"]
        bg = np.ones_like(x) if 0 > O else np.polyval(p_opt[-(O + 1):], x)    
        for p, (u, l) in nearby_lines:
            bg *= self(x, *p)

            m = (u >= x) * (x >= l)
            ax.scatter(x[m], y[m], facecolor="r")

        ax.plot(x, bg, c='r')
        ax.plot(x, model_y, c='b')

        model_err = np.percentile(
            [self(x, *_) for _ in p_alt], percentiles, axis=0)

        ax.fill_between(x, model_err[0] + model_y, model_err[1] + model_y,
            edgecolor="None", facecolor="b", alpha=0.5)
        """
        
        fitting_metadata = {
            "equivalent_width": (ew, ew_uncertainty[0], ew_uncertainty[1]),
            "data_indices": np.where(mask)[0][iterative_mask],
            "model_x": x,
            "model_y": model_y,
            "model_yerr": model_yerr,
            "nearby_lines": nearby_lines,
            "chi_sq": chi_sq,
            "dof": dof
        }

        # Update the equivalent width in the transition.
        self._transitions["equivalent_width"] = ew

        # Convert p_opt to ordered dictionary
        named_p_opt = OrderedDict(zip(self.parameter_names, p_opt))
        self._result = (named_p_opt, p_cov, fitting_metadata)

        return self._result


    def __call__(self, dispersion, *parameters):
        """
        Generate data at the dispersion points, given the parameters.

        :param dispersion:
            An array of dispersion points to calculate the data for.

        :param parameters:
            Keyword arguments of the model parameters and their values.
        """

        function, profile_parameters = self._profiles[self.metadata["profile"]]

        N = len(profile_parameters)
        y = 1.0 - function(dispersion, *parameters[:N])

        # Assume rest of the parameters are continuum coefficients.
        if parameters[N:]:
            y *= np.polyval(parameters[N:], dispersion)
        
        return y


    def abundances(self):
        """
        Calculate the abundance from the curve-of-growth given the fitted
        equivalent width and the current stellar parameters in the parent
        session.
        """

        # TODO: Create a hash of the stellar parameters, EW, and any relevant
        #       radiative transfer inputs.

        # Does the hash match the last calculation?
        # If so, return that value. If not, calculate the new value.

        foo = self.session.rt.abundance_cog(
            self.session.stellar_photosphere,
            self.transition)

        raise NotImplementedError


if __name__ == "__main__":


    # Load some atomic transitions
    # Measure them in a spectrum.
    # Get abundances from MOOGSILENT.


    import smh
    a = smh.Session([
        "/Users/arc/codes/smh/hd44007red_multi.fits",
        "/Users/arc/codes/smh/hd44007blue_multi.fits",
    ])

    spec = smh.specutils.Spectrum1D.read("../hd140283.fits")


    foo = ProfileFittingModel({"wavelength": [5202.336]}, a)

    raise a


    """
    with open("a", "r") as fp:
        b = fp.readlines()

    for each in b:
        

        foo = ProfileFittingModel({"wavelength": [float(each.split()[0])]}, a)

        try:
            foo.fit(spec)
        except:
            print("failed on {}".format(each))

    """


