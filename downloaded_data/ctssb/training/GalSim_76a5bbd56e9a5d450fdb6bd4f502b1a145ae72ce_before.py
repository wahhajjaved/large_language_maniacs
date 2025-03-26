# Copyright 2012, 2013 The GalSim developers:
# https://github.com/GalSim-developers
#
# This file is part of GalSim: The modular galaxy image simulation toolkit.
#
# GalSim is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GalSim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GalSim.  If not, see <http://www.gnu.org/licenses/>
#
"""@file correlatednoise.py
Python layer documentation and functions for handling correlated noise in GalSim.
"""

import numpy as np
import galsim
from . import base
from . import utilities

class _BaseCorrelatedNoise(galsim.BaseNoise):
    """A Base Class describing 2D correlated Gaussian random noise fields.

    A _BaseCorrelatedNoise will not generally be instantiated directly.  This is recommended as the
    current `_BaseCorrelatedNoise.__init__` interface does not provide any guarantee that the input
    `GSObject` represents a physical correlation function, e.g. a profile that is an even function 
    (two-fold rotationally symmetric in the plane) and peaked at the origin.  The proposed pattern
    is that users instead instantiate derived classes, such as the CorrelatedNoise, which are able
    to guarantee the above.

    The _BaseCorrelatedNoise is therefore here primarily to define the way in which derived classes 
    (currently only the `CorrelatedNoise`) store the random deviate, noise correlation function
    profile and allow operations with it, generate images containing noise with these correlation
    properties, and generate covariance matrices according to the correlation function.
    """
    def __init__(self, rng, gsobject):
        
        if not isinstance(rng, galsim.BaseDeviate):
            raise TypeError(
                "Supplied rng argument not a galsim.BaseDeviate or derived class instance.")
        if not isinstance(gsobject, base.GSObject):
            raise TypeError(
                "Supplied gsobject argument not a galsim.GSObject or derived class instance.")

        # Initialize the GaussianNoise with our input random deviate/GaussianNoise
        galsim.BaseNoise.__init__(self, rng)
        # Act as a container for the GSObject used to represent the correlation funcion.
        self._profile = gsobject

        # When applying normal or whitening noise to an image, we normally do calculations. 
        # If _profile_for_stored is profile, then it means that we can use the stored values in
        # _rootps_store and/or _rootps_whitening_store and avoid having to redo the calculations.
        # So for now, we start out with _profile_for_stored = None and _rootps_store and 
        # _rootps_whitening_store empty.
        self._profile_for_stored = None
        self._rootps_store = []
        self._rootps_whitening_store = []
        # Also set up the cache for a stored value of the variance, needed for efficiency once the
        # noise field can get convolved with other GSObjects making isAnalyticX() False
        self._variance_stored = None

        # Cause any methods we don't want the user to have access to, since they don't make sense
        # for correlation functions and could cause errors in applyNoiseTo, to raise exceptions
        self._profile.applyShift = self._notImplemented

    # Make "+" work in the intuitive sense (variances being additive, correlation functions add as
    # you would expect)
    def __add__(self, other):
        ret = self.copy()
        ret += other
        return ret

    def __iadd__(self, other):
        self._profile += other._profile
        return _BaseCorrelatedNoise(self.getRNG(), self._profile)

    # Make op* and op*= work to adjust the overall variance of an object
    def __imul__(self, other):
        self._profile.scaleVariance(other)
        return self

    def __mul__(self, other):
        ret = self.copy()
        ret *= other
        return ret

    def __rmul__(self, other):
        ret = self.copy()
        ret *= other
        return ret

    # Likewise for op/ and op/=
    def __idiv__(self, other):
        self.scaleVariance(1. / other)
        return self

    def __div__(self, other):
        ret = self.copy()
        ret /= other
        return ret

    def __itruediv__(self, other):
        return __idiv__(self, other)

    def __truediv__(self, other):
        return __div__(self, other)

    def copy(self):
        """Returns a copy of the correlated noise model.

        The copy will share the galsim.BaseDeviate random number generator with the parent instance.
        Use the .setRNG() method after copying if you wish to use a different random number
        sequence.
        """
        return _BaseCorrelatedNoise(self.getRNG(), self._profile.copy())

    def applyTo(self, image):
        """Apply this correlated Gaussian random noise field to an input Image.

        Calling
        -------

            >>> correlated_noise.applyTo(image)

        On output the Image instance image will have been given additional noise according to 
        the given CorrelatedNoise instance.  image.getScale() is used to determine the input image
        pixel separation, and if image.getScale() <= 0 a pixel scale of 1 is assumed.

        To add deviates to every element of an image, the syntax 

            >>> image.addNoise(correlated_noise)

        is preferred.

        @param image The input Image object.
        """
        # Note that this uses the (fast) method of going via the power spectrum and FFTs to generate
        # noise according to the correlation function represented by this instance.  An alternative
        # would be to use the covariance matrices and eigendecomposition.  However, it is O(N^6)
        # operations for an NxN image!  FFT-based noise realization is O(2 N^2 log[N]) so we use it
        # for noise generation applications.

        # Check that the input has defined bounds
        if not hasattr(image, "bounds"):
            raise ValueError(
                "Input image argument does not have a bounds attribute, it must be a galsim.Image"+
                "or galsim.ImageView-type object with defined bounds.")

        # If the profile has changed since last time (or if we have never been here before),
        # clear out the stored values.
        if self._profile_for_stored is not self._profile:
            self._rootps_store = []
            self._rootps_whitening_store = []
            self._variance_stored = None
        # Set profile_for_stored for next time.
        self._profile_for_stored = self._profile

        # Then retrieve or redraw the sqrt(power spectrum) needed for making the noise field
        rootps = self._get_update_rootps(image.array.shape, image.getScale())

        # Finally generate a random field in Fourier space with the right PS
        noise_array = _generate_noise_from_rootps(self.getRNG(), rootps)
        # Add it to the image
        image += galsim.ImageViewD(noise_array)
        return image

    def applyWhiteningTo(self, image):
        """Apply noise designed to whiten correlated Gaussian random noise in an input Image.

        On output the Image instance image will have been given additional noise according to 
        a specified CorrelatedNoise instance, designed to whiten any correlated noise that may have
        existed in `image`.

        Calling
        -------

            >>> correlated_noise.applyWhiteningTo(image)

        If the `image` originally contained noise with a correlation function described by the 
        `correlated_noise` instance, the combined noise after using the applyWhiteningTo() method
        will be uncorrelated to a good approximation.

        Note that the code doesn't check that the "if" above s true: the user MUST make sure this is
        the case for the final noise to be uncorrelated.

        image.getScale() is used to determine the input image pixel separation, and if 
        image.getScale() <= 0 a pixel scale of 1 is assumed.

        If you are interested in a theoretical calculation of the variance in the final noise field
        after whitening, the applyWhiteningTo() method in fact returns this variance.  For example:

            >>> variance = correlated_noise.applyWhiteningTo(image)

        Example
        -------
        To see noise whitening in action, let us use a model of the correlated noise in COSMOS 
        as returned by the getCOSMOSNoise() function.  Let's initialize and add noise to an image:

            >>> cosmos_file='YOUR/REPO/PATH/GalSim/examples/data/acs_I_unrot_sci_20_cf.fits'
            >>> cn = galsim.getCOSMOSNoise(galsim.BaseDeviate(), cosmos_file)
            >>> image = galsim.ImageD(256, 256)
            >>> image.setScale(0.03) # Should match the COSMOS default since didn't specify another
            >>> image.addNoise(cn)

        The `image` will then contain a realization of a random noise field with COSMOS-like
        correlation.  Using the applyWhiteningTo() method, we can now add more noise to `image`
        with a power spectrum specifically designed to make the combined noise fields uncorrelated:

            >>> cn.applyWhiteningTo(image)

        Of course, this whitening comes at the cost of adding further noise to the image.

        @param image The input Image object.

        @return variance  A float containing the theoretically calculated variance of the combined
                          noise fields in the updated image.
        """
        # Note that this uses the (fast) method of going via the power spectrum and FFTs to generate
        # noise according to the correlation function represented by this instance.  An alternative
        # would be to use the covariance matrices and eigendecomposition.  However, it is O(N^6)
        # operations for an NxN image!  FFT-based noise realization is O(2 N^2 log[N]) so we use it
        # for noise generation applications.

        # Check that the input has defined bounds
        if not hasattr(image, "bounds"):
            raise ValueError(
                "Input image argument does not have a bounds attribute, it must be a galsim.Image"+
                "or galsim.ImageView-type object with defined bounds.")

        # If the profile has changed since last time (or if we have never been here before),
        # clear out the stored values.
        if self._profile_for_stored is not self._profile:
            self._rootps_store = []
            self._rootps_whitening_store = []
            self._variance_stored = None
        # Set profile_for_stored for next time.
        self._profile_for_stored = self._profile

        # Then retrieve or redraw the sqrt(power spectrum) needed for making the whitening noise,
        # and the total variance of the combination
        rootps_whitening, variance = self._get_update_rootps_whitening(
            image.array.shape, image.getScale())

        # Finally generate a random field in Fourier space with the right PS and add to image
        noise_array = _generate_noise_from_rootps(self.getRNG(), rootps_whitening)
        image += galsim.ImageViewD(noise_array)

        # Return the variance to the interested user
        return variance

    def applyTransformation(self, ellipse):
        """Apply a galsim.Ellipse distortion to the correlated noise model.
           
        galsim.Ellipse objects can be initialized in a variety of ways (see documentation of this
        class, galsim.ellipse.Ellipse in the doxygen documentation, for details).

        Note that the correlation function must be peaked at the origin, and is translationally
        invariant: any X0 shift in the input ellipse is therefore ignored.

        @param ellipse The galsim.Ellipse transformation to apply.
        """
        if not isinstance(ellipse, galsim.Ellipse):
            raise TypeError("Argument to applyTransformation must be a galsim.Ellipse!")
        # Create a new ellipse without a shift
        ellipse_noshift = galsim.Ellipse(shear=ellipse.getS(), mu=ellipse.getMu())
        self._profile.applyTransformation(ellipse_noshift)

    def applyMagnification(self, scale):
        """Scale the linear scale of correlations in this noise model by scale.  
        
        Scales the linear dimensions of the image by the factor scale, e.g.
        `half_light_radius` <-- `half_light_radius * scale`.

        @param scale The linear rescaling factor to apply.
        """
        self.applyTransformation(galsim.Ellipse(np.log(scale)))

    def applyRotation(self, theta):
        """Apply a rotation theta to this correlated noise model.
           
        After this call, the caller's type will still be a _BaseCorrelatedNoise, unlike in the
        GSObject implementation of this method.  This is to allow _BaseCorrelatedNoise methods to
        be available after transformation, such as .applyTo().

        @param theta Rotation angle (Angle object, +ve anticlockwise).
        """
        if not isinstance(theta, galsim.Angle):
            raise TypeError("Input theta should be an Angle")
        self._profile.applyRotation(theta)

    def applyShear(self, *args, **kwargs):
        """Apply a shear to this correlated noise model, where arguments are either a galsim.Shear,
        or arguments that will be used to initialize one.

        For more details about the allowed keyword arguments, see the documentation for galsim.Shear
        (for doxygen documentation, see galsim.shear.Shear).

        After this call, the caller's type will still be a _BaseCorrelatedNoise.  This is to allow
        _BaseCorrelatedNoise methods to be available after transformation, such as .applyTo().
        """
        self._profile.applyShear(*args, **kwargs)

    # Also add methods which create a new _BaseCorrelatedNoise with the transformations applied...
    #
    def createTransformed(self, ellipse):
        """Returns a new correlated noise model by applying a galsim.Ellipse transformation (shear,
        dilate).

        The new instance will share the galsim.BaseDeviate random number generator with the parent.
        Use the .setRNG() method after this operation if you wish to use a different random number
        sequence.

        Note that galsim.Ellipse objects can be initialized in a variety of ways (see documentation
        of this class, galsim.ellipse.Ellipse in the doxygen documentation, for details).

        Note also that the correlation function must be peaked at the origin, and is translationally
        invariant: any X0 shift in the input ellipse is therefore ignored.

        @param ellipse The galsim.Ellipse transformation to apply
        @returns The transformed object.
        """
        if not isinstance(ellipse, galsim.Ellipse):
            raise TypeError("Argument to createTransformed must be a galsim.Ellipse!")
        ret = self.copy()
        ret.applyTransformation(ellipse)
        return ret

    def createMagnified(self, scale):
        """Returns a new correlated noise model by applying a magnification by the given scale,
        scaling the linear size by scale.  

        The new instance will share the galsim.BaseDeviate random number generator with the parent.
        Use the .setRNG() method after this operation if you wish to use a different random number
        sequence.

        Scales the linear dimensions of the image by the factor scale.
        e.g. `half_light_radius` <-- `half_light_radius * scale`
 
        @param scale The linear rescaling factor to apply.
        @returns The rescaled object.
        """
        ret = self.copy()
        ret.applyTransformation(galsim.Ellipse(np.log(scale)))
        return ret

    def createRotated(self, theta):
        """Returns a new correlated noise model by applying a rotation.

        The new instance will share the galsim.BaseDeviate random number generator with the parent.
        Use the .setRNG() method after this operation if you wish to use a different random number
        sequence.

        @param theta Rotation angle (Angle object, +ve anticlockwise).
        @returns The rotated object.
        """
        if not isinstance(theta, galsim.Angle):
            raise TypeError("Input theta should be an Angle")
        ret = self.copy()
        ret.applyRotation(theta)
        return ret

    def createSheared(self, *args, **kwargs):
        """Returns a new correlated noise model by applying a shear, where arguments are either a
        galsim.Shear or keyword arguments that can be used to create one.

        The new instance will share the galsim.BaseDeviate random number generator with the parent.
        Use the .setRNG() method after this operation if you wish to use a different random number
        sequence.

        For more details about the allowed keyword arguments, see the documentation of galsim.Shear
        (for doxygen documentation, see galsim.shear.Shear).
        """
        ret = self.copy()
        ret.applyShear(*args, **kwargs)
        return ret

    def getVariance(self):
        """Return the point variance of this noise field, equal to its correlation function value at
        zero distance.

        This is the variance of values in an image filled with noise according to this model.
        """
        # Test whether we can simply return the zero-lag correlation function value, which gives the
        # variance of an image of noise generated according to this model
        if self._profile.isAnalyticX():
            variance = self._profile.xValue(galsim.PositionD(0., 0.))
        else:
            # If the profile has changed since last time (or if we have never been here before),
            # clear out the stored values.
            if self._profile_for_stored is not self._profile:
                self._rootps_store = []
                self._rootps_whitening_store = []
                self._variance_stored = None
            # Set profile_for_stored for next time.
            self._profile_for_stored = self._profile
            # Then use cached version or rebuild if necessary
            if self._variance_stored is not None:
                variance = self._variance_stored
            else:
                imtmp = galsim.ImageD(1, 1)
                self.draw(imtmp, dx=1.) # GalSim internals handle this correctly w/out folding
                variance = imtmp.at(1, 1)
                self._variance_stored = variance # Store variance for next time 
        return variance

    def scaleVariance(self, variance_ratio):
        """Multiply the variance of the noise field by variance_ratio.

        @param variance_ratio The factor by which to scale the variance of the correlation function
                              profile.
        """
        self._profile.SBProfile.scaleFlux(variance_ratio)

    def setVariance(self, variance):
        """Set the point variance of the noise field, equal to its correlation function value at
        zero distance, to an input variance.

        @param variance  The desired point variance in the noise.
        """
        variance_ratio = variance / self.getVariance()
        self.scaleVariance(variance_ratio)

    def _notImplemented(self, *args, **kwargs):
        raise NotImplementedError(
            "This method is not available for correlated noise class instances.")

    def convolveWith(self, gsobject):
        """Convolve the correlated noise model with an input GSObject.

        The resulting correlated noise model will then give a statistical description of the noise
        field that would result from convolving noise generated according to the initial correlated
        noise with a kernel represented by `gsobject` (e.g. a PSF).

        This modifies the representation of the correlation function, but leaves the random number
        generator unchanged.

        Examples
        --------
        The following command simply applies a galsim.Moffat PSF with slope parameter `beta`=3. and
        FWHM=0.7:

            >>> correlated_noise.convolveWith(galsim.Moffat(beta=3., fwhm=0.7))

        Often we will want to convolve with more than one function.  For example, if we wanted to
        simulate how a noise field would look if convolved with a ground-based PSF (such as the 
        Moffat above) and then rendered onto a new (typically larger) pixel grid, the following
        example command demonstrates the syntax: 

            >>> correlated_noise.convolveWith(
            ...    galsim.Convolve([galsim.Deconvolve(galsim.Pixel(0.03)),
            ...                     galsim.Pixel(0.2), galsim.Moffat(3., fwhm=0.7),

        Note, we also deconvolve by the original pixel, which should be the pixel size of the 
        image from which the `correlated_noise` was made.  This command above is functionally 
        equivalent to

            >>> correlated_noise.convolveWith(galsim.Deconvolve(galsim.Pixel(0.2)))
            >>> correlated_noise.convolveWith(galsim.Pixel(0.2))
            >>> correlated_noise.convolveWith(galsim.Moffat(beta=3., fwhm=0.7))

        as is demanded for a linear operation such as convolution.

        @param gsobject  A galsim.GSObject or derived class instance representing the function with
                         which the user wants to convolve the correlated noise model.
        """
        self._profile = galsim.Convolve([self._profile, galsim.AutoConvolve(gsobject)])

    def draw(self, image=None, dx=None, wmult=1., add_to_image=False):
        """The draw method for profiles storing correlation functions.

        This is a very mild reimplementation of the draw() method for GSObjects.  The normalization
        is automatically set to have the behviour appropriate for a correlation function, and the 
        `gain` kwarg is automatically set to unity.

        See the general GSObject draw() method for more information the input parameters.
        """
        return self._profile.draw(
            image=image, dx=dx, gain=1., wmult=wmult, normalization="surface brightness",
            add_to_image=add_to_image)

    def calculateCovarianceMatrix(self, bounds, dx):
        """Calculate the covariance matrix for an image with specified properties.

        A correlation function also specifies a covariance matrix for noise in an image of known
        dimensions and pixel scale.  The user specifies these bounds and pixel scale, and this
        method returns a covariance matrix as a square ImageD object, with the upper triangle
        containing the covariance values.

        @param  bounds Bounds corresponding to the dimensions of the image for which a covariance
                       matrix is required.
        @param  dx     Pixel scale of the image for which a covariance matrix is required.

        @return The covariance matrix (as an ImageD)
        """
        return galsim._galsim._calculateCovarianceMatrix(self._profile.SBProfile, bounds, dx)

    def _get_update_rootps(self, shape, dx):
        """Internal utility function for querying the rootps cache, used by applyTo and 
        applyWhiteningTo methods.
        """ 
        # First check whether we can just use a stored power spectrum (no drawing necessary if so)
        use_stored = False
        for rootps_array, scale in self._rootps_store:
            if shape == rootps_array.shape:
                if ((dx <= 0. and scale == 1.) or (dx == scale)):
                    use_stored = True
                    rootps = rootps_array
                    break

        # If not, draw the correlation function to the desired size and resolution, then DFT to
        # generate the required array of the square root of the power spectrum
        if use_stored is False:
            newcf = galsim.ImageD(shape[1], shape[0]) # set the corr func to be the correct size
            # set the scale based on dx...
            if dx <= 0.:
                newcf.setScale(1.) # sometimes new Images have getScale() = 0
            else:
                newcf.setScale(dx)
            # Then draw this correlation function into an array
            self.draw(newcf, dx=None) # setting dx=None uses the newcf image scale set above

            # Then calculate the sqrt(PS) that will be used to generate the actual noise
            rootps = np.sqrt(np.abs(np.fft.fft2(newcf.array)) * np.product(shape))

            # Then add this and the relevant scale to the _rootps_store for later use
            self._rootps_store.append((rootps, newcf.getScale()))

        return rootps

    def _get_update_rootps_whitening(self, shape, dx, headroom=1.05):
        """Internal utility function for querying the rootps_whitening cache, used by the
        applyWhiteningTo method, and calculate & update it if not present.

        @return rootps_whitening, variance
        """ 
        # First check whether we can just use a stored whitening power spectrum
        use_stored = False
        for rootps_whitening_array, scale, var in self._rootps_whitening_store:
            if shape == rootps_whitening_array.shape:
                if ((dx <= 0. and scale == 1.) or (dx == scale)):
                    use_stored = True
                    rootps_whitening = rootps_whitening_array
                    variance = var
                    break

        # If not, calculate the whitening power spectrum as (almost) the smallest power spectrum 
        # that  when added to rootps**2 gives a flat resultant power that is nowhere negative.
        # Note that rootps = sqrt(power spectrum), and this procedure therefore works since power
        # spectra add (rather like variances).  The resulting power spectrum will be all positive
        # (and thus physical).
        if use_stored is False:

            rootps = self._get_update_rootps(shape, dx)
            ps_whitening = -rootps * rootps
            ps_whitening += np.abs(np.min(ps_whitening)) * headroom # Headroom adds a little extra
            rootps_whitening = np.sqrt(ps_whitening)                # variance, for "safety"

            # Finally calculate the theoretical combined variance to output alongside the image 
            # to be generated with the rootps_whitening.  The factor of product of the image shape
            # is required due to inverse FFT conventions, and note that although we use the [0, 0] 
            # element we could use any as the PS should be flat
            variance = (rootps[0, 0]**2 + ps_whitening[0, 0]) / np.product(shape)

            # Then add all this and the relevant scale dx to the _rootps_whitening_store
            self._rootps_whitening_store.append((rootps_whitening, dx, variance))

        return rootps_whitening, variance

###
# Now a standalone utility function for generating noise according to an input (square rooted)
# Power Spectrum
#
def _generate_noise_from_rootps(rng, rootps):
    """Utility function for generating a NumPy array containing a Gaussian random noise field with
    a user-specified power spectrum also supplied as a NumPy array.

    @param rng    galsim.BaseDeviate instance to provide the random number generation
    @param rootps a NumPy array containing the square root of the discrete Power Spectrum ordered
                  in two dimensions according to the usual DFT pattern (see np.fft.fftfreq)
    @return A NumPy array (contiguous) of the same shape as rootps, filled with the noise field.
    """
    # I believe it is cheaper to make two random vectors than to make a single one (for a phase)
    # and then apply cos(), sin() to it...
    gaussvec_real = galsim.ImageD(rootps.shape[1], rootps.shape[0]) # Remember NumPy is [y, x]
    gaussvec_imag = galsim.ImageD(rootps.shape[1], rootps.shape[0])
    gn = galsim.GaussianNoise(rng, sigma=1.) # Create on the fly using an input RNG (cheap: see 
                                             # discussion on Issue #352)
    gaussvec_real.addNoise(gn)
    gaussvec_imag.addNoise(gn)
    noise_array = np.fft.ifft2((gaussvec_real.array + gaussvec_imag.array * 1j) * rootps)
    return np.ascontiguousarray(noise_array.real)


###
# Then we define the CorrelatedNoise, which generates a correlation function by estimating it
# directly from images:
#
class CorrelatedNoise(_BaseCorrelatedNoise):
    """A class that represents 2D correlated noise fields calculated from an input Image.

    This class stores an internal representation of a 2D, discrete correlation function, and allows
    a number of subsequent operations including interpolation, shearing, magnification and
    rendering of the correlation function profile into an output Image.  The class also allows
    correlated Gaussian noise fields to be generated according to the correlation function, and
    added to an Image.

    It also allows the combination of multiple correlation functions by addition, and for the
    scaling of the total variance they represent by scalar factors.

    Convolution of correlation functions with a GSObject is not yet supported, but will be in the 
    near future.

    Initialization
    --------------

    Basic example:

        >>> cn = galsim.CorrelatedNoise(rng, image)

    Instantiates a CorrelatedNoise using the pixel scale information contained in image.getScale()
    (assumes the scale is unity if image.getScale() <= 0.) by calculating the correlation function
    in the input `image`.  The input `rng` must be a galsim.BaseDeviate or derived class instance,
    setting the random number generation for the noise.

    Optional Inputs
    ---------------

        >>> cn = galsim.CorrelatedNoise(rng, image, dx=0.2)

    The example above instantiates a CorrelatedNoise, but forces the use of the pixel scale `dx` to
    set the units of the internal lookup table.

        >>> cn = galsim.CorrelatedNoise(rng, image,
        ...     interpolant=galsim.InterpolantXY(galsim.Lanczos(5, tol=1.e-4))

    The example above instantiates a CorrelatedNoise, but forces use of a non-default interpolant
    for interpolation of the internal lookup table.  Must be an InterpolantXY instance or an
    Interpolant instance (if the latter one-dimensional case is supplied an InterpolantXY will be
    automatically generated from it).

    The default interpolant if `None` is set is a galsim.InterpolantXY(galsim.Linear(tol=1.e-4)),
    which uses bilinear interpolation.  Initial tests indicate the favourable performance of this
    interpolant in applications involving correlated pixel noise.

    Methods
    -------
    The main way that a CorrelatedNoise is used is to add or assign correlated noise to an image.
    This is common to all the classes that inherit from BaseNoise, e.g.:

        >>> cn.applyTo(im)

    However, to add deviates to every element of an image, the syntax

        >>> im.addNoise(cn)

    is preferred.

    The correlation function is calculated from its pixel values using the NumPy FFT functions.
    See the .addNoise() method docstring for more information.  The image.getScale() is used to
    get the pixel scale of the input image unless this is <= 0, in which case a scale of 1 is
    assumed.

    Another method that may be of use is

        >>> cn.calculateCovarianceMatrix(im.bounds, dx)

    which can be used to generate a covariance matrix based on a user input image geometry.  See
    the .calculateCovarianceMatrix() method docstring for more information.

    A number of methods familiar from GSObject instance have also been implemented directly as 
    `cn` methods, so that the following commands are all legal:

        >>> cn.draw(im, dx, wmult=4)
        >>> cn.createSheared(s)
        >>> cn.createMagnified(m)
        >>> cn.createRotated(theta * galsim.degrees)
        >>> cn.createTransformed(ellipse)
        >>> cn.applyShear(s)
        >>> cn.applyMagnification(m)
        >>> cn.applyRotation(theta * galsim.degrees)
        >>> cn.applyTransformation(ellipse)

    See the individual method docstrings for more details.

    The BaseNoise methods

        >>> cn.setVariance(variance)
        >>> cn.getVariance()
 
    can be used to set and get the point variance of the correlated noise, equivalent to the zero
    separation distance correlation function value.  The .setVariance(variance) method scales the
    whole internal correlation function so that its point variance matches `variance`.

    A new method, which is in fact a more appropriately named reimplmentation of the
    .scaleFlux() method in GSObject instances for the internally stored correlation function, is

        >>> cn.scaleVariance(variance_ratio)

    which scales the overall correlation function, and therefore variance, by a scalar factor
    `variance_ratio`.

    Arithmetic Operators
    --------------------
    Addition, multiplication and division operators are defined to work in an intuitive way for
    correlation functions.

    Addition works simply to add the internally-stored correlated noise fields, so that

        >>> cn3 = cn2 + cn1
        >>> cn4 += cn5

    provides a representation of the correlation function of two linearly summed fields represented
    by the individual correlation function operands.

    What happens to the internally stored random number generators in the examples above?  For all
    addition operations it is the galsim.BaseDeviate belonging to the instance on the Left-Hand Side
    of the operator that is retained. 

    In the example above therefore, it is the random number generator from `cn2` that will be stored
    and used by `cn3`, and `cn4` will retain it's random number generator after inplace addition of
    `cn5`.  The random number generator of `cn5` is not affected by the operation.

    The multiplication and division operators, e.g.

        >>> cn1 /= 3.
        >>> cn2 = cn1 * 3

    scale the overall correlation function by a scalar operand using the .scaleVariance() method
    described above.  The random number generators are not affected by these scaling operations.
    """
    def __init__(self, rng, image, dx=0., interpolant=None):

        # Check that the input image is in fact a galsim.ImageSIFD class instance
        if not isinstance(image, (
            galsim.BaseImageD, galsim.BaseImageF, galsim.BaseImageS, galsim.BaseImageI)):
            raise TypeError(
                "Input image not a galsim.Image class object (e.g. ImageD, ImageViewS etc.)")
        # Build a noise correlation function (CF) from the input image, using DFTs

        # Calculate the power spectrum then a (preliminary) CF 
        ft_array = np.fft.fft2(image.array)
        ps_array = np.abs(ft_array * ft_array.conj())
        cf_array_prelim = (np.fft.ifft2(ps_array)).real / float(np.product(np.shape(ft_array)))

        # Roll CF array to put the centre in image centre.  Remember that numpy stores data [y,x]
        cf_array_prelim = utilities.roll2d(
            cf_array_prelim, (cf_array_prelim.shape[0] / 2, cf_array_prelim.shape[1] / 2))

        # The underlying C++ object is expecting the CF to be represented by an odd-dimensioned 
        # array with the central pixel denoting the zero-distance correlation (variance), even 
        # even if the input image was even-dimensioned on one or both sides.
        # We therefore copy-paste and zero pad the CF calculated above to ensure that these
        # expectations are met. 
        #
        # Determine the largest dimension of the input image, and use it to generate an empty CF 
        # array for final output, padding by one to make odd if necessary:
        cf_array = np.zeros((
            1 + 2 * (cf_array_prelim.shape[0] / 2), 
            1 + 2 * (cf_array_prelim.shape[1] / 2))) # using integer division
        # Then put the data from the prelim CF into this array
        cf_array[0:cf_array_prelim.shape[0], 0:cf_array_prelim.shape[1]] = cf_array_prelim
        # Then copy-invert-paste data from the leftmost column to the rightmost column, and lowest
        # row to the uppermost row, if the original CF had even dimensions in the x and y 
        # directions, respectively (remembering again that NumPy stores data [y,x] in arrays)
        if cf_array_prelim.shape[1] % 2 == 0: # first do x
            lhs_column = cf_array[:, 0]
            cf_array[:, cf_array_prelim.shape[1]] = lhs_column[::-1] # inverts order as required
        if cf_array_prelim.shape[0] % 2 == 0: # then do y
            bottom_row = cf_array[0, :]
            cf_array[cf_array_prelim.shape[0], :] = bottom_row[::-1] # inverts order as required

        # Store power spectrum and correlation function in an image 
        original_ps_image = galsim.ImageViewD(np.ascontiguousarray(ps_array))
        original_cf_image = galsim.ImageViewD(np.ascontiguousarray(cf_array))

        # Correctly record the original image scale if set
        if dx > 0.:
            original_cf_image.setScale(dx)
        elif image.getScale() > 0.:
            original_cf_image.setScale(image.getScale())
        else: # sometimes Images are instantiated with scale=0, in which case we will assume unit
              # pixel scale
            original_cf_image.setScale(1.)

        # If interpolant not specified on input, use bilinear
        if interpolant == None:
            linear = galsim.Linear(tol=1.e-4)
            interpolant = galsim.InterpolantXY(linear)
        else:
            if isinstance(interpolant, galsim.Interpolant):
                interpolant = galsim.InterpolantXY(interpolant)
            elif isinstance(interpolant, galsim.InterpolantXY):
                interpolant = interpolant
            else:
                raise RuntimeError(
                    'Specified interpolant is not an Interpolant or InterpolantXY instance!')

        # Then initialize...
        _BaseCorrelatedNoise.__init__(self, rng, base.InterpolatedImage(
            original_cf_image, interpolant, dx=original_cf_image.getScale(), normalization="sb",
            calculate_stepk=False, calculate_maxk=False)) # these internal calculations do not seem
                                                          # to do very well with often sharp-peaked
                                                          # correlation function images...

        # Finally store useful data as a (rootps, dx) tuple for efficient later use:
        self._profile_for_stored = self._profile
        self._rootps_store.append(
            (np.sqrt(original_ps_image.array), original_cf_image.getScale()))

# Make a function for returning Noise correlations
def _Image_getCorrelatedNoise(image):
    """Returns a CorrelatedNoise instance by calculating the correlation function of image pixels.
    """
    return CorrelatedNoise(image)

# Then add this Image method to the Image classes
for Class in galsim.Image.itervalues():
    Class.getCorrelatedNoise = _Image_getCorrelatedNoise

for Class in galsim.ImageView.itervalues():
    Class.getCorrelatedNoise = _Image_getCorrelatedNoise

for Class in galsim.ConstImageView.itervalues():
    Class.getCorrelatedNoise = _Image_getCorrelatedNoise

# Free function for returning a COSMOS noise field correlation function
def getCOSMOSNoise(rng, file_name, dx_cosmos=0.03, variance=0.):
    """Returns a representation of correlated noise in the HST COSMOS F814W unrotated science coadd
    images.

    See http://cosmos.astro.caltech.edu/astronomer/hst.html for information about the COSMOS survey,
    and Leauthaud et al (2007) for detailed information about the unrotated F814W coadds used for
    weak lensing science.

    This function uses a stacked estimate of the correlation function in COSMOS noise fields, the
    location of which should be input to this function via the `file_name` argument.  This image is
    stored in FITS format, and is generated as described in
    `YOUR/REPO/PATH/GalSim/devel/external/hst/make_cosmos_cfimage.py`.  The image itself can also be
    found within the GalSim repo, located at:

        /YOUR/REPO/PATH/GalSim/examples/data/acs_I_unrot_sci_20_cf.fits

    @param rng        Must be a galsim.BaseDeviate or derived class instance, provides the random
                      number generator for the noise field.
    @param file_name  String containing the path and filename above but modified to match the
                      location of the GalSim repoistory on your system.
    @param dx_cosmos  COSMOS ACS F814W coadd image pixel scale in the units you are using to
                      describe GSObjects and image scales in GalSim: defaults to 0.03 arcsec, see
                      below for more information.
    @param variance   Scales the correlation function so that its point variance, equivalent to its
                      value at zero separation distance, matches this value.  The default
                      `variance = 0.` uses the variance in the original COSMOS noise fields.

    Important note regarding units
    ------------------------------
    The ACS coadd images in COSMOS have a pixel scale of 0.03 arcsec, and so the pixel scale
    `dx_cosmos` adopted in the representation of of the correlation function takes a default value

        dx_cosmos = 0.03

    If you wish to use other units, ensure that the input keyword `dx_cosmos` takes the value
    corresponding to 0.03 arcsec in your chosen system.

    Example usage
    -------------
    The following commands use this function to generate a 300 pixel x 300 pixel image of noise with
    HST COSMOS correlation properties (substitute in your own file and path for the `filestring`).

        >>> filestring='/YOUR/REPO/PATH/GalSim/devel/external/hst/acs_I_unrot_sci_20_cf.fits'
        >>> import galsim
        >>> rng = galsim.UniformDeviate(123456)
        >>> cf = galsim.correlatednoise.getCOSMOSNoise(rng, filestring)
        >>> im = galsim.ImageD(300, 300)
        >>> im.setScale(0.03)
        >>> cf.applyTo(im)
        >>> im.write('out.fits')

    The FITS file `out.fits` should then contain an image of randomly-generated, COSMOS-like noise.
    """
    # First try to read in the image of the COSMOS correlation function stored in the repository
    import os
    if not os.path.isfile(file_name):
        raise IOError("The input file_name '"+str(file_name)+"' does not exist.")
    try:
        cfimage = galsim.fits.read(file_name)
    except Exception as original_exception:
        # Give a vaguely helpful warning, then raise the original exception for extra diagnostics
        import warnings
        warnings.warn(
            "Function getCOSMOSNoise() unable to read FITS image from "+str(file_name)+", "+
            "more information on the error in the following Exception...")
        raise original_exception

    # Then check for negative variance before doing anything time consuming
    if variance < 0:
        raise ValueError("Input keyword variance must be zero or positive.")
    
    # Use this info to then generate a correlated noise model DIRECTLY: note this is non-standard
    # usage, but tolerated since we can be sure that the input cfimage is appropriately symmetric
    # and peaked at the origin
    ret = _BaseCorrelatedNoise(rng, base.InterpolatedImage(
        cfimage, dx=dx_cosmos, normalization="sb", calculate_stepk=False, calculate_maxk=False))
    # If the input keyword variance is non-zero, scale the correlation function to have this
    # variance
    if variance > 0.:
        ret.setVariance(variance)
    return ret
