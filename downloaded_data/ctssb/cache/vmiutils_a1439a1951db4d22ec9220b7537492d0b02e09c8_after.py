import numpy
from numpy.linalg import lstsq
import polcart
import logging
from scipy.special import lpn as legpol
import copy

logger = logging.getLogger('vmiutils.image')

class __NullHandler(logging.Handler):
    def emit(self, record):
        pass

__null_handler = __NullHandler()
logger.addHandler(__null_handler)

def _round_int(x):
    return int(round(x))

class CartesianImage():
    """Class used to represent a VMI image stored as a cartesian
    array.

    image specifies the image data. If image is a 2D numpy ndarray,
    this will be stored in the returned instance. If image is any of
    the strings "empty" or "Empty" a 2D numpy.empty ndarray is
    created. If image is either of the strings "zeros" or "Zeros", a
    2D numpy.zeros ndarray is created. If image is not specified, or
    None, the image data is not initialized.

    if image is "empty", "Empty, "zeros" or "Zeros", xbins and ybins
    specify the size of the image to create.

    x specifies the x coordinates of the image data. If no x argument
    is specified, the bin number is used.

    y specifies the y coordinates of the image data. If no y argument
    is specified, the bin number is used.

    centre specifies the centre of the image. If not specified, the
    centre coordinate of the image array is used.

    """
    def __init__(self, image=None, x=None, y=None, 
                 xbins=None, ybins=None, centre=None):
        if image is None:
            self.image = None
            self.x = None
            self.y = None
            self.xbinw = None
            self.ybinw = None
            self.centre = None
            self.shape = None
            self.quad = None
            return

        elif image in ('empty', 'Empty', 'zeros', 'Zeros'):
            if x is not None and y is not None:
                self.x = x.copy()
                self.y = y.copy()
                xbins = x.shape[0]
                ybins = y.shape[0]
            elif xbins is not None and ybins is not None:
                self.x = numpy.arange(float(xbins))
                self.y = numpy.arange(float(ybins))
            else:
                logger.error(
                    'x and y dimensions of CartesianImage not specified')

            if image in ('empty', 'Empty'):
                self.image=numpy.empty((xbins, ybins))
            else:
                self.image=numpy.zeros((xbins, ybins))

        elif isinstance(image, numpy.ndarray):
            self.image = image.copy()

            if x is None:
                self.x = numpy.arange(float(self.image.shape[0]))
            else:
                self.x = x.copy()

            if y is None:
                self.y = numpy.arange(float(self.image.shape[1]))
            else:
                self.y = y.copy()
                    
        self.shape = self.image.shape

        # Set bin widths in each dimension assuming bins are equally
        # spaced
        self.xbinw = self.x[1] - self.x[0]
        self.ybinw = self.y[1] - self.y[0]
        
        if centre is None or centre == 'grid_centre':
            self.set_centre(self.centre_of_grid())
        elif centre == 'cofg':
            self.set_centre(self.centre_of_gravity())
        else:
            self.set_centre(centre)

    def copy(self):
        return copy.copy(self)

    def set_centre(self, centre):
        """ Specify the coordinates of the centre of the image as a tuple
        (xcentre, ycentre). These coordinates are not expected to be integers
        (though they can be).
        """
        self.centre = centre
        
        # Define the centre pixel of the image by rounding to the nearest
        # pixel 
        cx = _round_int((centre[0] - self.x[0]) / self.xbinw)
        cy = _round_int((centre[1] - self.y[0]) / self.ybinw)
        self.centre_pixel = (cx, cy)

        # Set up slices to give views of quadrants. The quadrants are numbered
        # 0-3: Quadrant 0: from centre to (xmax, ymax) [Top right] Quadrant 1:
        # from centre to (xmax, 0) [Bottom right] Quadrant 2: from centre to
        # (0, 0) [Bottom Left] Quadrant 3: from centre to (0, ymax] [Top left]
        # self.quadrant = [
        # self.image[cx::, cy::], 
        # self.image[cx::, cy - 1::-1],
        # self.image[cx - 1::-1, cy - 1::-1],
        # self.image[cx - 1::-1, cy::]
        # ]

        self.quad = [
            (slice(cx, None, None), slice (cy, None, None)),
            (slice(cx, None, None), slice (cy - 1, None, -1)),
            (slice(cx - 1, None, -1), slice (cy - 1, None, -1)),
            (slice(cx - 1, None, -1), slice (cy, None, None))
            ]

    def __quad_idx(self, quad):
        if quad in ('upper right', 'top right', 'ur', 0):
            return 0
        elif quad in ('lower right', 'bottom right', 'lr', 1):
            return 1
        elif quad in ('lower left', 'bottom left', 'll', 2):
            return 2
        elif quad in ('upper left', 'top left', 'ul', 3):
            return 3
        else:
            logger.error('quad argument not recognized: {0}'.format(quad))
            raise ValueError

    def get_quadrant(self, quad):
        """ Return a numpy array instance containing the requested image
        quadrant indexed such that [0, 0] is the image centre, and increasing
        |x| and |y| as indices increase.
        """
        return self.image[self.quad[self.__quad_idx(quad)]]
        
    def set_quadrant(self, quad, data):
        """ Return a numpy array instance containing the requested image
        quadrant indexed such that [0, 0] is the image centre, and increasing
        x and y move away from the centre.
        """
        qslice = self.quad[self.__quad_idx(quad)]

        if self.image[qslice].shape != data.shape:
            logger.error('data not correct shape for specified quadrant')
            raise ValueError
        else:
            self.image[qslice] = data

    def zoom_circle(self, rmax, pad=False):
        """ Return a new CartesianImage instance containing a square section
        centred on the image centre and containing the circular section of the
        image specified by rmax in image coordinates (not bins).
        """
        if self.centre is None:
            logger.error('image centre has not been defined prior to asking for zoom_circle')
            raise RuntimeError('image centre undefined')

        xminb = _round_int((self.centre[0] - rmax - self.x[0]) / self.xbinw) 
        if xminb < 0 and pad is False:
            logger.error('xminb less than zero in zoom_circle')
            raise RuntimeError('xminb less than zero')

        xmaxb = _round_int((self.centre[0] + rmax - self.x[0]) / self.xbinw)
        if xmaxb > self.image.shape[0] and pad is False:
            logger.error('xmaxb greater than image size in zoom_circle')
            raise RuntimeError('xmaxb greater than image size')

        yminb = _round_int((self.centre[1] - rmax - self.y[0]) / self.ybinw)
        if yminb < 0 and pad is False:
            logger.error('yminb less than zero in zoom_circle')
            raise RuntimeError('yminb less than zero')

        ymaxb = _round_int((self.centre[1] + rmax - self.y[0]) / self.ybinw)
        if ymaxb > self.image.shape[0] and pad is False:
            logger.error('ymaxb greater than image size in zoom_circle')
            raise RuntimeError('ymaxb greater than image size')
        
        return self.zoom_rect_pix([xminb, xmaxb, yminb, ymaxb], pad=pad)

    def zoom_rect_coord(self, rect):
        """ Return a new CartesianImage instance containing the zoomed image
        specified by rect. 

        rect is a list containing the rectanlge to zoom specified in
        coordinates: [xmin, xmax, ymin, ymax].
        """
        xminb = _round_int((rect[0] - self.x[0]) / self.xbinw)
        xmaxb = _round_int((rect[1] - self.x[0]) / self.xbinw)

        yminb = _round_int((rect[2] - self.y[0]) / self.ybinw)
        ymaxb = _round_int((rect[3] - self.y[0]) / self.ybinw)
    
        return self.zoom_rect_pix([xminb, xmaxb, yminb, ymaxb])
        
    def zoom_rect_pix(self, rect, pad=False):
        """Return a new CartesianImage instance containing the zoomed image
        specified by rect. 

        rect is a list containing the rectanlge to zoom specified in terms of
        bins: [xmin, xmax, ymin, ymax]. As such, all elements of rect should
        be integer.

        if pad is True, then if any of the requested area doesn't lie
        within the image data, then where no data is available, 0s are
        substituted.
        """
        xmin = rect[0]
        xmax = rect[1]
        ymin = rect[2]
        ymax = rect[3]

        if xmin >= 0:
            x1 = xmin
            xstart = 0
        else:
            if pad == True:
                x1 = 0
                xstart = -xmin
            else:
                logger.error('xmin outside of image in zoom_rect_pix')
                raise RuntimeError('xmin outside of image')

        if xmax <= self.image.shape[0]:
            x2 = xmax
        else:
            if pad == True:
                x2 = self.image.shape[0] - 1
            else:
                logger.error('xmax outside of image in zoom_rect_pix')
                raise RuntimeError('xmax outside of image')

        if ymin >= 0:
            y1 = ymin
            ystart = 0
        else:
            if pad == True:
                y1 = 0
                ystart = -ymin
            else:
                logger.error('ymin outside of image in zoom_rect_pix')
                raise RuntimeError('ymin outside of image')

        if ymax <= self.image.shape[0]:
            y2 = ymax
        else:
            if pad == True:
                y2 = self.image.shape[0] - 1
            else:
                logger.error('ymax outside of image in zoom_rect_pix')
                raise RuntimeError('ymax outside of image')

        newimg = numpy.zeros((xmax - xmin + 1, ymax - ymin + 1))

        newimg[xstart:xstart + (x2 - x1),
               ystart:ystart + (y2 - y1)] = self.image[x1:x2, y1:y2]

        newx = numpy.linspace(xmin * self.xbinw, xmax * self.xbinw, newimg.shape[0])
        newy = numpy.linspace(ymin * self.ybinw, ymax * self.ybinw, newimg.shape[1])

        return CartesianImage(image=newimg, x=newx, y=newy, centre=self.centre)

    def from_PolarImage(self, pimage, xbins=None, ybins=None, order=3):
        """Initialise from a PolarImage object by interpolation onto a
        cartesian grid.

        xbins and ybins specify the desired number of x and y bins. If
        these are None, the number of bins in each direction will
        be equal to the number of radial bins in the polar image.

        order specifies the interpolaton order used in the conversion.

        """
        self.x, self.y, self.image = pimage.cartesian_rep(xbins, ybins, order)
        self.shape = self.image.shape
        self.xbinw = self.x[1] - self.x[0]
        self.ybinw = self.y[1] - self.y[0]
        self.set_centre(self.centre_of_grid())

    def polar_rep(self, rbins=None, thetabins=None, rmax=None, order=3):
        """ Returns a tuple (r, theta, pimage) containing the coordinates and
        polar representation of the image.

        rbins and thetabins specify the number of bins in the returned image.

        rmax specifies the maximum radius to consider, and is specified in the
        coordinate system of the image (as opposed to bin number). If rmax is
        None, then the largest radius possible is used.

        order specifies the interpolaton order used in the conversion.
        """
        if self.image is None:
            logger.error('no image data')
            raise ValueError ## FIXME

        if self.centre is None:
            logger.error('image centre not defined')
            raise ValueError ## FIXME

        if rbins is None:
            rbins = min(self.image.shape[0], self.image.shape[1]) 

        if thetabins is None:
            thetabins = min(self.image.shape[0], self.image.shape[1]) 

        return polcart.cart2pol(self.image, x=self.x, y=self.y, 
                                centre=self.centre, radial_bins=rbins, 
                                angular_bins=thetabins, rmax=rmax,
                                order=order)

    def centre_of_gravity(self):
        """Returns a tuple representing the coordinates corresponding to the
        centre of gravity of the image."""
        xval = self.x * self.image 
        yval = self.y[:,numpy.newaxis] * self.image
        return xval.sum() / self.image.sum(), yval.sum() / self.image.sum()

    def centre_of_grid(self):
        """Returns a tuple containing the central coordinates of the cartesian
        grid."""
        xc = 0.5 * (self.x[-1] - self.x[0])
        yc = 0.5 * (self.y[-1] - self.y[0])
        return xc, yc

class PolarImage():
    """ Class used to represent a VMI image stored in polar coordinates
    i.e. in regularly spaced bins in (r, theta)."""

    def __init__(self):
        self.image = None
        self.r = None
        self.theta = None
        self.rbins = None
        self.thetabins = None

    def from_numpy_array(self, image, r=None, theta=None):
        """ Initialize from a polar image stored in a numpy array. If R or theta are
        not specified, the r and theta coordinates are stored as pixel values.
        """
        self.image = image.copy()

        if r is None:
            self.r = numpy.arange(float(self.image.shape[0]))
        else:
            self.r = r.copy()

        if theta is None:
            self.theta = numpy.linspace(-numpy.pi, numpy.pi, self.image.shape[1])
        else:
            self.theta = theta.copy()

    def from_CartesianImage(self, cimage, rbins=None, 
                            thetabins=None, rmax=None, order=3):
        """Calculate a polar represenation of a CartesianImage instance.

        cimage is a CartesianImage instance.

        rbins and thetabins specify the desired number of bins in the
        polar representation. If these are none, the number of bins in the
        cartesian image is used.
        """
        self.r, self.theta, self.image = \
            cimage.polar_rep(rbins, thetabins, rmax, order)

        self.rbins = self.r.shape[0]
        self.thetabins = self.theta.shape[0]

    def cartesian_rep(self, xbins=None, ybins=None, order=3):
        """ Returns a tuple (x, y, image) containing the coordinates and
        cartesian represenation of the image. 

        xbins and ybins optionally specify the number of bins in each
        dimension. If not specified, the number of bins in each direction will
        be equal to the number of radial bins in the polar image.

        order specifies the interpolaton order used in the conversion.
        """
        if xbins is None:
            xbins = self.image.shape[0]

        if ybins is None:
            ybins = self.image.shape[0]

        return polcart.pol2cart(self.image, self.r, self.theta, 
                                xbins, ybins, order)

    def radial_spectrum(self):
        """ Return a tuple (r, intensity) for the radial spectrum calculated
        by summing over theta for each r bin.
        """
        return self.r, self.image.sum(1)

    def beta_coefficients(self, lmax=2, oddl=False):
        """ Return a tuple (r, beta) representing the values of the beta
        parameters at for each radial bin calculated by fitting to an
        expansion in Legendre polynomials up to order lmax. oddl specifies
        whether odd l coefficients are fit or not.
        """
        
        costheta = numpy.cos(self.theta)
        A = numpy.c_[[legpol(lmax, ct)[0] for ct in costheta]]
        logger.debug(
            'matrix calculated for beta fitting with shape {0}'.format(A.shape))

        if oddl is False:
            A = A[:, ::2]
            logger.debug(
                'odd l coefs not fit: matrix reduced to shape {0}'.format(A.shape))

        try:
            # TODO set rcond
            beta, resid, rank, s = lstsq(A, self.image.transpose())
            # Note that beta is indexed as beta[l, r]
            # TODO: do something with resid, rank, s
        except numpy.linalg.LinAlgError:
            logger.error(
                'failed to converge while fitting beta coefficients')
            raise
        logger.debug('beta coefficents fit successfully')


        # Normalize to beta_0 = 1 at each r
        beta0 = beta[0, :]
        beta = beta / beta0
        logger.debug('beta coefficents normalized')

        if oddl is False:
            logger.debug('adding rows to beta matrix for odd l coeffs')
            logger.debug('beta shape before adding new rows {0}'.format(beta.shape)) 
            beta = numpy.insert(beta, numpy.arange(1, lmax), 0, axis=0)
            logger.debug('rows for odd l added to beta array; new shape {0}'.format(beta.shape)) 

        return self.r, beta
