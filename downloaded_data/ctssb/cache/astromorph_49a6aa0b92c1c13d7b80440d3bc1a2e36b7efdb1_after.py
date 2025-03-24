import sys
import numpy as np
import scipy.ndimage as sci_nd
import scipy.optimize as sci_op
import astropy.io.fits as pyfits
import astropy.wcs as pywcs
import subprocess as sp
import os
import numpy.random as npr
import random as rdm
import warnings

from skimage.morphology import watershed
from skimage.feature import peak_local_max



colorred = "\033[01;31m{0}\033[00m"
colorgrn = "\033[1;32m{0}\033[00m"
colorblu = "\033[1;34m{0}\033[00m"
colorylw = "\033[1;33m{0}\033[00m"


if sys.platform =='darwin':
    SEx_COMMAND = "sex"
elif "linux" in sys.platform:
    SEx_COMMAND = "sextractor"
else:
    warnings.warn("WARNING! SExtractor only works on unix systems. Some functions will not work")

def barycenter(img,segmap):
    r"""Compute the barycenter (flux-weighted center) of the image cosidering
    the given segmentation mask.

    It returns the x,y position of the image barycenter.


    Parameters
    ----------
    img : float, array
        The image array containing the data for which to comput the barycenter
    segmap: int, array
        A image array flagging all pixels to be considered for the
        computation of the barycenter. It uses all pixels with non-zero values.

    Returns
    -------
    (x,y) : float, tuple
        The barycenter position for the given image and segmentation mask.

    References
    ----------

    Examples
    --------

    """
    assert img.shape == segmap.shape, "Input image and segmentation map must be"\
                                      +" of the same shape."

    binary_mask = segmap.copy()
    binary_mask[segmap!=0]=1

    N,M=img.shape
    YY,XX=np.meshgrid(range(M),range(N))
    gal=np.abs(img*binary_mask)
    Y = np.average(YY,weights=gal)
    X = np.average(XX,weights=gal)
    return (X,Y)

def moments(img,segmap):
    r"""Compute the second order moments of the image, using the given binary
    segmentation mask.

    It returns the x^2,y^2, and x*y moments for the input image.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute the light
        moments
    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    (x2,y2,xy) : float, tuple
        The three values of the 2nd order moments for the input image.

    References
    ----------

    Examples
    --------

    """
    assert img.shape == segmap.shape, "Input image and segmentation map must be"\
                                      +" of the same shape."

    binary_mask = segmap.copy()
    binary_mask[segmap!=0]=1

    N,M=img.shape
    YY,XX=np.meshgrid(range(M),range(N))
    gal=img*binary_mask
    xmed,ymed = barycenter(img,binary_mask)

    X2 = np.average(XX*XX,weights=gal) - xmed*xmed
    Y2 = np.average(YY*YY,weights=gal) - ymed*ymed
    XY = np.average(XX*YY,weights=gal) - xmed*ymed

    return X2,Y2,XY

def get_half_light_radius(img,segmap,axisRatio=None,positionAngle=None):
    r"""Compute the half-light radius of an object given an image and a
        segmentation mask.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute the light
        moments
    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    r : float
        The estimated half-light radius for the input image.

    References
    ----------

    Examples
    --------

    """
    totalFlux = np.sum(img*segmap)
    print(totalFlux)
    xc,yc = barycenter(img,segmap)

    if axisRatio is None:
        axisRatio = get_axis_ratio(img,segmap)
    if positionAngle is None:
        positionAngle = get_position_angle(img,segmap) - 90

    # print(positionAngle)
    dmat = compute_ellipse_distmat(img,xc,yc,axisRatio,positionAngle)

    # import matplotlib.pyplot as mpl
    # fig,ax = mpl.subplots(1,2)
    # ax[0].imshow(img)
    # ax[1].imshow(dmat)
    # mpl.show()

    dr0 = 0.1
    r0 = 0.5
    F0 = 0.0
    while F0 < 0.5*totalFlux:
        F0 = np.sum(img[dmat<r0])
        r0=r0+dr0
        if r0>max(dmat.shape):
            break

    return r0

def get_axis_ratio(img,segmap):
    r"""Computes the axis ratio of the image based on the provided segmentation
    mask.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute the axis ratio
    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    q : float
        The axis ratio associated with the image+segmentation mask

    See also
    ----------
    moments, axis_ratio_from_moments

    References
    ----------

    Examples
    --------

    """
    return axis_ratio_from_moments(*moments(img, segmap))

def get_position_angle(img,segmap):
    r"""Computes the position angle of the image based on the provided
    segmentation mask.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute the position
        angle
    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    angle : float
        The position angle associated with the image+segmentation mask

    See also
    ----------
    moments, theta_from_moments

    References
    ----------

    Examples
    --------

    """
    return theta_from_moments(*moments(img, segmap))

def theta_from_moments(x2,y2,xy):
    r""" Compute the position angle of the galaxy from the light moments.
    See the SExtractor manual for details on the equations.

    Parameters
    ----------
    x2 : float
        2nd order light moment in the horizontal axis

    y2 : float
        2nd order light moment in the vertical axis

    y2 : float
        2nd order light moment in the vertical axis

    Returns
    -------
    angle : float
        The position angle associated with the given light moments.

    See also
    ----------
    moments, axis_ratio_from_moments

    References
    ----------
    See https://www.astromatic.net/software/sextractor for more details

    Examples
    --------

    """
    if x2==y2:
        return np.sign(xy)*90.
    else:
        arg=2.0*xy/(x2-y2)
        if np.sign(x2-y2)<0:
            if np.sign(xy)<0:
                angle=abs(np.degrees(np.arctan(arg)/2.0))-90.
            else:
                angle=-1*abs(np.degrees(np.arctan(arg)/2.0))+90.
        else:
            angle=np.sign(xy)*abs(np.degrees(np.arctan(arg)/2.0))
        return angle

def axis_ratio_from_moments(x2,y2,xy):
    r"""Compute the axis ratio of the galaxy from the light moments.
    See the SExtractor manual for details on the equations.

    Parameters
    ----------
    x2 : float
        2nd order light moment in the horizontal axis

    y2 : float
        2nd order light moment in the vertical axis

    y2 : float
        2nd order light moment in the vertical axis

    Returns
    -------
    angle : float
        The position angle associated with the given light moments.

    See also
    ----------
    moments, theta_sky_from_moments

    References
    ----------
    See https://www.astromatic.net/software/sextractor for more details

    """
    arg1 = (x2+y2)/2.0
    arg2 = np.sqrt(((x2-y2)/2.0)**2+xy**2)

    a2=arg1+arg2
    b2=arg1-arg2

    if (b2/a2)<0 or not np.isfinite(b2/a2):
        q = 1
    else:
        q=np.sqrt(b2/a2)
    return q


def get_center_coords_hdr(header,ra,dec,hsize=1,verify_limits=True):
    hdr=header
    wcs=pywcs.WCS(hdr)

    ctype=hdr["ctype1"]
    xmax=hdr["naxis1"]
    ymax=hdr["naxis2"]

    if 'RA' in ctype:
        sky=np.array([[ra,dec]],np.float_)
    else:
        sky=np.array([[dec,ra]],np.float_)

    pixcrd=wcs.wcs_world2pix(sky,1)

    xc=pixcrd[0,0]
    yc=pixcrd[0,1]
    if verify_limits:
       if xc>xmax-hsize or yc >ymax-hsize or xc<hsize or yc<hsize:
           raise IndexError("X=%.3f, Y=%.3f out of image bounds"%(xc,yc))

    return (xc,yc)

def get_center_coords(imgname,ra,dec,hsize=1,verify_limits=True):
    r""" Computes the x,y coordinates of a ra,dec position in a given image.

    Parameters
    ----------
    imgname : string
        The name of the FITS image to use as reference frame
    ra : float
        the right ascension coordinate
    dec: float
        the declination coordinate
    hsize : int, optional
        if given, checks if the computed coordinates are at a distance greater
        than hsize from the image border.
    verify_limits : bool, optional
        if True, verifies the distance of the coordinates to the image border.

    Returns
    -------

    (xc,yc) : tuple, float
        A tuple with the x and y pixel-coordinates corresponing to the given
        sky coordinates using the input image as reference frame.

    References
    ----------

    Examples
    --------

    """
    hdr=pyfits.getheader(imgname)

    return get_center_coords_hdr(hdr,ra,dec,hsize=1,verify_limits=verify_limits)

def compute_ellipse_distmat(img,xc,yc,q=1.00,ang=0.00):
    r"""Compute a matrix with dimensions of the image where in each pixel we
    have the distance to the center xc,yc.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute the distance
        matrix.

    xc : float
        the horizontal coordinate (in pixel) of the ellipse center

    yc : float
        the vertical coordinate (in pixel) of the ellipse center

    q : float, optional
        the axis ratio of the ellipse. If not given, computes the distance
        assuming a circular geometry.

    ang : float, optional
        the position angle (in degrees) of the ellipse. If not given, an angle
        of zero degrees is assumed.

    Returns
    -------

    dmat : float, array
        A 2D array of the same shape as the input image where each pixel encodes
        its distance to the input center coordinates and the given geometry.

    References
    ----------

    Examples
    --------

    """
    ang_rad = np.radians(ang)
    X,Y = np.meshgrid(range(img.shape[1]),range(int(img.shape[0])))
    rX=(X-xc)*np.cos(ang_rad)-(Y-yc)*np.sin(ang_rad)
    rY=(X-xc)*np.sin(ang_rad)+(Y-yc)*np.cos(ang_rad)
    dmat = np.sqrt(rX*rX+(1/(q*q))*rY*rY)
    return dmat


def distance_matrix(xc,yc,img):
    r"""Compute a matrix with circular distances and a sorted np.array with
    unique distance values from each pixel position to xc,yc.

    Parameters
    ----------
    xc : float
        the horizontal coordinate (in pixel) of the ellipse center

    yc : float
        the vertical coordinate (in pixel) of the ellipse center

    img : float, array
        The image array containing the data for which to compute the distance
        matrix.


    Returns
    -------

    Dmat : float, array
        A 2D array of the same shape as the input image where each pixel encodes
        its distance to the input center coordinates assuming circular geometry.

    dists : float, array
        a sorted array with unique distance values from the 2D distance matrix.

    References
    ----------

    See also
    ----------
    compute_ellipse_distmat

    Examples
    --------

    """
    Dmat= compute_ellipse_distmat(img,xc,yc)
    dists=np.sort(np.unique(Dmat))
    return Dmat, dists

def size_segmentation_map(segmap):
    r"""Computes the minimum square size (halved) of the segmentation map that
    contains the entire region flagged in the segmentation mask.

    Parameters
    ----------
    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    r : int
        returns the half size of the minimum square that contains all flagged
        pixels in the segmentation mask.

    See also
    -------
    find_ij

    References
    ----------

    Examples
    --------

    """
    imax,imin,jmax,jmin=find_ij(segmap,1)
    r=int(max([imax-imin,jmax-jmin])/2.0)
    return r

def make_stamps(xc,yc,img,segmap,pixscale,radius,fact=2):
    r"""Returns two small stamps: one for the galaxy image and one from the
    segmentation map containing all the pixels from the segmentation map
    and renormalizes & selects the segmentation map to ones and zeros.
    Returns also the new center coordinates of the object in the stamp image.

    Parameters
    ----------

    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center

    img : float, array
        The image array containing the data for which to select the region.

    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask.

    fact : float
        A factor which controls the enlargement of the extracted stamps. If
        equals to one it extracts the minimum region containing the selected
        region of the segmentation mask.

    Returns
    -------

    stamp_img : float, array
        A subsection of the input image containing the selected region of the
        segmentantion mask.

    stamp_segmap : float, array
        A subsection of the input segmentation mask containing the selected
        region of the. It has the same size of stamp_img.

    (xc,yc) : tuple, float
        The new center of the object (in pixel-coordinates) in stamp_img.

    References
    ----------

    Examples
    --------

    """
    N,M=img.shape
    segmap,nr=sci_nd.label(segmap)

    temp_map = select_object_map_connected(xc,yc,img,segmap,pixscale,radius)

    r = size_segmentation_map(xc,yc,temp_map)
    xmin=int(xc-fact*r)
    xmax=int(xc+fact*r)+1
    ymin=int(yc-fact*r)
    ymax=int(yc+fact*r)+1

    if xmin < 0:
        xmin=0
    if xmax > N:
        xmax=N
    if ymin < 0:
        ymin=0
    if ymax > M:
        ymax=M

    stamp_segmap = temp_map[xmin:xmax,ymin:ymax]
    stamp_img = img[xmin:xmax,ymin:ymax]

    nxc , nyc = xc - xmin , yc-ymin

    return stamp_img, stamp_segmap, (nxc,nyc)

def sky_value(img,k=3):
    r"""
    Compute the value of sky background and respective standard
    deviation using a sigma clipping method.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to get the sky statistics.
        It should contain a large enough portion (>70% of the pixels) of sky
        region to get a good approximation.

    k : float, optional
        A multiplicative factor used in the sigma-clipping method. Default value
        is to get the sky statistics within a 3-sigma clean pixel sample.

    Returns
    -------
    media : float
        the mean value of the pixel fluxes after sigma-clipping the image.

    dev : float
        the standard deviation of the pixel fluxes after sigma-clipping the
        image.

    References
    ----------

    Examples
    --------

    """
    media=np.nanmean(img[img!=0])
    dev=np.nanstd(img[img!=0])
    back=img.copy()
    back=back[back!=0]
    thresh=media+k*dev
    npix = img[(img)>=thresh].size
    while npix>0:
        back = back[(back)<thresh]
        media=np.nanmean(back)
        dev=np.nanstd(back)
        thresh=media+k*dev
        npix = back[(back)>=thresh].size
    return media,dev

def select_object_map(xc,yc,segmap,pixscale,radius):
    r"""Filters the segmentation mask of the object by setting all regions
    outside the given radius (in arcseconds) to 0 in the output segmentation
    mask.

    Parameters
    ----------
    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center

    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask.

    Returns
    -------
    new_map : int, array
        A binary array with all regions containing at least one pixel at a
        distance smaller than the given radius.

    References
    ----------

    Examples
    --------

    """
    Dmat,d=distance_matrix(xc,yc,segmap)
    s_values = np.unique(segmap[Dmat<np.sqrt(2)*radius/pixscale])
    new_map = segmap.copy()
    for s in s_values:
        if s==0:
            continue
        new_map[new_map==s]=-1
    new_map[new_map>0]=0
    return -new_map

def select_object_map_connected(xc,yc,image,segmap,pixscale,radius=0.5):
    r"""Selects a single connected region on the segmentation mask that contains
    the brightest pixel inside the given radius (in arcseconds).

    Parameters
    ----------
    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center

    img : float, array
        The image array containing the data for which to select the region.

    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask.

    Returns
    -------
    new_map : int, array
        A binary array with the connected region containing the brightest pixel
        at a distance smaller than the given radius.

    References
    ----------

    Examples
    --------

    """
    new_map = select_object_map(xc,yc,segmap,pixscale,radius)
    Regions,Nregions = sci_nd.label(new_map)
#    A= np.array([np.size(Regions[Regions==n]) for n in range(1,Nregions+1)])
    try:
        central_region = image.copy()
        central_region[Dmat>(radius/pixscale)*(radius/pixscale)]=0.0
        central_region*=-new_map
        fmax = np.where(central_region == np.amax(central_region))
        n = Regions[fmax]
##        F= np.array([np.amax(image[Regions==n]) for n in range(1,Nregions+1)])
##        n = np.argmax(F)+1
        Regions[Regions!=n]=0
        Regions[Regions>0]=1

    except ValueError:
        ## IN CASE OF NON-DETECTIONS returns empty segmentation map
        pass

#    nFig,nAx = mpl.subplots(1,3)
#    nAx[0].imshow(segmap,cmap='rainbow')
#    nAx[0].plot([xc],[yc],'wx',markersize=20,mew=2)
#    nAx[1].imshow(new_map,cmap='jet')
#    nAx[1].plot([xc],[yc],'wx',markersize=20,mew=2)
#    nAx[2].imshow(Regions,cmap='YlGnBu_r')
#    nAx[2].plot([xc],[yc],'rx',markersize=20,mew=2)
#    mpl.show()
    return Regions


def gen_segmap_watershed(img,thresholds=[100,50,25,12,5,2],mSigma=1,Amin=5,k_sky=3):
    segmap = np.zeros_like(img)
    for t in thresholds:
        sm = gen_segmap_tresh(img,None,None,None,thresh=t,all_detection=True,Amin=Amin,k_sky=k_sky)
        sm[sm>0]=1
        segmap += sm

    segmap = sci_nd.gaussian_filter(segmap,sigma=mSigma)
    peaksImage = peak_local_max(segmap, indices=False, footprint=np.ones((3, 3)),
                        labels=sm)
    markers = sci_nd.label(peaksImage)[0]
    labels = watershed(-segmap, markers, mask=sm)
    return labels

def gen_segmap_tresh(img,xc,yc,pixscale,radius =0.5,thresh=5.0,Amin=5,k_sky=3,all_detection=False,structure=None):
    r""" Creates a segmentation mask for the given image by flagging all pixels
    above a given threshold (relative to the internally computed sky rms). It
    is possible to flag all regions above that threshold that have at least
    Amin pixels. If all_detection is False, it selects only the connected region
    with the brightest pixel within 0.5 arcseconds of the given coordinates. If
    a structure array is given, it then enlarges the segmentation map using
    binary morphological dilation.

    Parameters
    ----------
    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center

    img : float, array
        The image array containing the data for which to select the region.

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    thresh : float, optional
        The flux distance, in units of sky rms, above the mean sky value for a
        pixel to be considered a positive detection.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask. Is only used if all_detections is false.

    Amin : int, optional
        The minimum number of connected pixels for a region to be considered a
        detection. Regions with less pixels are not included in the final
        segmentation mask.

    k_sky : int, optional
        K value of the sigma-clipping method used to compute the sky mean and
        rms.

    all_detection : bool, optional
        If true, it returns all regions detecteds in the image. If false, it
        selects the region with the brightest pixel within the given radius.

    structure : int, array, optional
        A binary array used as a structure element for binary morphological
        dilation of the final segmentaion mask.

    Returns
    -------

    segmap: int, array
        A binary image array flagging all pixels considered to be detections.

    References
    ----------

    Examples
    --------

    """
    N,M=img.shape
    MAP = np.zeros([N,M])
    sky_mean,sky_std=sky_value(img,k=k_sky)

    MAP[img > sky_mean+thresh*sky_std] = 1
    Regions,Nregions=sci_nd.label(MAP)
    for n in range(1,Nregions+1):
        npix = len(Regions[Regions==n])
        if npix<Amin:
            Regions[Regions==n]=0
        else:
            continue

    if structure is None:
        SIZE=6
        structure = np.zeros([SIZE,SIZE])
        dmat,d= distance_matrix(SIZE/2.-0.5,SIZE/2.-0.5,structure)
        structure[dmat<SIZE/2]=1


    if all_detection:
        return Regions
    else:
        segmap = select_object_map(xc,yc,Regions,pixscale,radius)
        return sci_nd.binary_dilation(segmap,structure=structure).astype(np.int16)

def gen_segmap_sbthresh(img,xc,yc,sblimit,pixscale,radius=0.5,thresh=5.0,Amin=5,all_detection=False,structure=None):
    r"""Generate a segmentation map by selecting pixels above
    thresh*surface_brightness limit in flux/pixel**2 and then select the regions
    within the given radius to belong to the object. Objects with a number of
    pixels less than Amin are non detections and are not present in the final
    segmentation mask. The final segmentation map is dilated to smooth
    the detections

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to select the region.

    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center

    sblimit : float
        the surface brightness limit defined as the global sky rms above which
        we compute the positive detections at a given threshold

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    thresh : float, optional
        The flux distance, in units of sky rms, above the mean sky value for a
        pixel to be considered a positive detection.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask. Is only used if all_detections is false.

    Amin : int, optional
        The minimum number of connected pixels for a region to be considered a
        detection. Regions with less pixels are not included in the final
        segmentation mask.

    k_sky : int, optional
        K value of the sigma-clipping method used to compute the sky mean and
        rms.

    all_detection : bool, optional
        If true, it returns all regions detecteds in the image. If false, it
        selects the region with the brightest pixel within the given radius.

    structure : int, array, optional
        A binary array used as a structure element for binary morphological
        dilation of the final segmentaion mask.

    Returns
    -------

    segmap: int, array
        A binary image array flagging all pixels considered to be detections.

    References
    ----------

    Examples
    --------

    """
    N,M=img.shape
    MAP = np.zeros([N,M])
    MAP[img/pixscale**2 > thresh*sblimit] = 1

    Regions,Nregions=sci_nd.label(MAP,structure= sci_nd.generate_binary_structure(2, 0))

    for n in range(1,Nregions+1):
        npix = len(Regions[Regions==n])
        if npix<Amin:
            Regions[Regions==n]=0
        else:
            continue

    if structure is None:
        SIZE=6
        structure = np.zeros([SIZE,SIZE])
        dmat,d= distance_matrix(SIZE/2.-0.5,SIZE/2.-0.5,structure)
        structure[dmat<SIZE/2]=1

    if all_detection:
        return Regions
    else:
        segmap = select_object_map(xc,yc,Regions,pixscale,radius)
        return sci_nd.binary_dilation(segmap,structure=structure)

def image_validation(image,segmap,pixscale,radius):
    r"""Function to validate the image and segmentation maps to circumvent no
     image data and/or no detected sources in the segmentation map.

    Parameters
    ----------
    image : float, array
        The image array containing the data for which to select the region.

    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    pixscale : float
        The scale to convert between pixel and arcseconds (given in arcsec/pix).
        If one wants to compute everything in pixel coordinates simply set the
        pixscale to one.

    radius : float
        The distance to consider above which all detected objects are discarded.
        Note that it is only required that a region has at least one pixel at a
        distance smaller than radius to be included in the filtered segmentation
        mask. Is only used if all_detections is false.

    Returns
    -------

    I : float, array
        Is the input image.

    S : int, array
        Is either the original segmentation mask, or a new mask with all pixels
        flagged insided the given radius (in case of no detections on the
        given segmentation mask)

    If : int
        A flag that encodes data quality. If = 0 means everything is ok.
        If = 1. means that more than half of the image pixels are zero.

    Sf : int
        A flag that encodes segmentation mask quality. Sf = 0 means everything
        is ok. Sf = 1 means a default circular segmentation mask.


    References
    ----------

    Examples
    --------

    """
    if len(segmap[segmap>0])==0:
        newseg = np.zeros(segmap.shape)
        N,M = newseg.shape
        DMAT,d = distance_matrix(N/2.,M/2.,newseg)
        newseg[DMAT<radius/pixscale] = 1
        S,Sf=newseg,1
    else:
        S,Sf=segmap,0
    N,M = image.shape
    if len(image[abs(image)>0])<(N*M)/2.0:
        I,If=image,1
    else:
        I,If=image,0
    return I,S,If,Sf

def gen_segmap_sex(fname,thresh=5.0,pix_scale=0.03,seeing=0.09,minarea=5,added_options=""):
    r"""  Runs SExtractor to obtain a segmentaion mask


    Parameters
    ----------
    fname : string
        The name of the image on which to run SExtractor

    thresh : float, optional
        Threshold to pass to SExtractor

    pix_scale : float, optional
        Pixel Scale to be passed to SExtractor

    seeing : float, optional
        Seeing to be passed to SExtractor

    minarea : int, optional
        Minimum area for region detection, to be passed to SExtractor

    added_options : string
        Additional options to be passed directly to SExtractor

    Returns
    -------

    segmap: int, array
        A binary image array flagging all pixels considered to be detections.

    References
    ----------

    Examples
    --------

    """
    root=os.getcwd()
    sp.call("%s %s -CHECKIMAGE_TYPE SEGMENTATION -CHECKIMAGE_NAME %s/map.fits"+\
            " -DETECT_MINAREA %i -FILTER Y -DETECT_THRESH %f -ANALYSIS_THRESH"+\
            " %f -PIXEL_SCALE %.2f -SEEING_FWHM %.2f %s"%(SEx_COMMAND,fname,\
            root,minarea,thresh,thresh,pix_scale,seeing,added_options),shell=True)

    segmap=pyfits.getdata('%s/map.fits'%root)
    sp.call('rm %s/map.fits'%root,shell=True)
    return segmap

def get_sex_pars(xc,yc):
    r"""Returns the SExtractor parameters from the catalog associated with the
    segmentation map for the source closest to the given coordinates. Assumes
    that SExtractor was run prior to calling this function.

    Parameters
    ----------
    xc : float
        the horizontal coordinate (in pixel) of the object center

    yc : float
        the vertical coordinate (in pixel) of the object center


    Returns
    -------

    xs : float, array
        SExtractor positions of the detection centers in the horizontal axis

    ys : float, array
        SExtractor positions of the detection centers in the vertical axis

    es : float, array
        SExtractor axis ratio of the detections

    thetas : float, array
        SExtractor position angle of the detections

    obj_num : int
        Index of the closest source to the given coordinates

    References
    ----------

    Examples
    --------

    """
    assert os.path.isfile("test.cat"), "Run SExtractor first. Make sure output"+\
    "catalog name is set to test.cat"

    xs,ys,es,thetas=np.loadtxt("test.cat",unpack=True,usecols=[0,1,6,7])
    if np.size(xs)==1:
        return np.asarray([xs-1]),np.asarray([ys-1]),np.asarray([es]),\
                np.asarray([thetas]),0
    else:
        dists = np.zeros(np.size(xs))
        i=0
        while i < np.size(xs):
            dists[i]=dist(xs[i],ys[i],xc,yc)
            i+=1
        obj_num=np.where(dists == min(dists))

        return xs-1,ys-1,es,thetas,obj_num

def gen_segmap_rp(img,xc,yc,q,theta,rp=None,thresh=5):
    r""" Generate a segmentation map by selecting pixels using the petrosian
    radius as suggested by Lotz et al. 2004

    Parameters
    ----------

    Returns
    -------

    References
    ----------
    See http://adsabs.harvard.edu/abs/2004AJ....128..163L (Lotz et al. 2004)

    Examples
    --------

    """
    import CAS
    N,M=img.shape

    try:
        len(xc)
        MAP = gen_segmap_rp_multi(img,xc,yc,q,theta,rp,thresh)
        return MAP
    except TypeError:
        pass

    if rp==None:
        rp=CAS.petrosian_rad(img,xc,yc,q,theta)
    smooth = sci_nd.filters.gaussian_filter(img, rp/5, mode='nearest')
    img_cut = smooth[int(xc-2*rp):int(xc+2*rp+1),int(yc-2*rp):int(yc+2*rp+1)]

    ang=np.radians(theta)
    X,Y = np.meshgrid(range(img_cut.shape[1]),range(int(img_cut.shape[0])))
    nxc,nyc=xc-int(xc-2*rp),yc-int(yc-2*rp)
    rX=(X-nxc)*np.cos(ang)-(Y-nyc)*np.sin(ang)
    rY=(X-nxc)*np.sin(ang)+(Y-nyc)*np.cos(ang)
    dmat = np.sqrt(rX**2+(1/q**2)*rY**2)

    mu_rp=CAS.Anel(img_cut,rp,dmat)

    SMAP = np.zeros([N,M])
    SMAP[smooth > thresh*mu_rp] = 1

    Regions,Nregions=sci_nd.label(SMAP)

    MAP = np.zeros([N,M])
    if Nregions > 1:
        CenReg=Regions[xc,yc]
        MAP[Regions == CenReg] = 1
    else:
        return SMAP

    return MAP


def gen_segmap_rp_multi(img,xc,yc,q,theta,rp,thresh):
    r"""

    Parameters
    ----------

    Returns
    -------

    References
    ----------

    Examples
    --------

    """
    """ Same as segmap_rp but for an entire field of galaxies.
    """
    N=np.size(img,0)
    M=np.size(img,1)
    MAP = np.zeros([N,M])

    for i in range(len(xc)):
        MAP+=(i+1)*gen_segmap_rp(img,xc[i],yc[i],q[i],theta[i],rp=rp,thresh=thresh)

    return MAP


def find_ij(segmap,seg_value=1):
    r""" Finds the corners of the smallest rectangle enclosing the segmentation
    mask.

    Parameters
    ----------

    segmap: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    seg_value : int, optional
        The value of the region to consider for corner identification. In the
        case the segmentation mask hs more than one detection with different ids
        this is useful to isolate a single connected region.

    Returns
    -------

    (imax, imin,jmax,jmin) : tuple, int
        The corner coordinates of the smallest rectangle including the
        considered region.

    References
    ----------

    Examples
    --------

    """
    xs,ys=np.where(segmap==seg_value)
    return (max(xs)+1,min(xs),max(ys)+1,min(ys))

def background_estimate(img,source_map):
    r"""Estimate the background mean and standard deviation values by masking
    out all pixels detected on the segmentation mask.

    Parameters
    ----------
    img : float, array
        The image array containing the data for which to compute background
        flux statistics.

    source_map: int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------
    sky : float
        the mean value of background pixel fluxes

    sigma : float
        the standard deviation of background pixel fluxes

    References
    ----------

    Examples
    --------

    """
    background = img[source_map==0]

    sky = np.mean(background)
    sigma = np.std(background)

    return sky,sigma


def sky_patch(img,segmap,stamp_shape,**kwargs):
    r"""Generate a sky image based on a random sample of the pixels with zero flag on
    the segmentation mask.

    Parameters
    ----------

    img : float, array
        The image array containing the data from which to extract the sky patch

    segmap : int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    stamp_shape : tuple, int
        The shape of the region to extract.

    **kwargs :
        additional keyword arguments are passed to outlier_detection
    Returns
    -------
    sky_img : float, array
        As image patch containing an empty sky region.

    outlier_map : int, array
        A binary mask flaggin all pixels which are outliers with respect to
        their neighbours.

    See also
    ----------
    outlier_detection

    References
    ----------

    Examples
    --------

    """

    sky_img = np.zeros(stamp_shape)

    outlier_map=outlier_detection_alt(img,**kwargs)
    sky_fluxes = img[(segmap+outlier_map)==0]

    sky_sample = npr.choice(sky_fluxes,np.size(sky_img),replace=True)
    sky_img = np.array(sky_sample).reshape(stamp_shape)

    return sky_img,outlier_map


def outlier_detection(img,k=15,s=3,mask=None):
    r""" Flags the pixels that are recognized as outliers from a median_filter
    passage.

    Parameters
    ----------

    img : float, array
        The image array containing the data

    k : int, optional
        The amount above sigma to be considered an outlier

    s : int, optional
        Controls the size of the median filter kernel

    mask : int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------

    out_map : int, array
        An array of the shape of the input image where all pixel outliers are
        flagged with ones.

    References
    ----------

    Examples
    --------

    """

    out_map=np.zeros(img.shape)
    blurred = sci_nd.median_filter(img,size=s)
    diff=img-blurred

    out_map=np.zeros(img.shape)
    ks=np.where(diff>np.mean(diff)+k*np.std(diff))
    if mask==None:
        out_map[ks]=1
    else:
        out_map[ks]=1-mask[ks]

#    fig,ax=subplots(1,2)
#    ax[0].imshow(np.sqrt(abs(img)))
#    ax[1].imshow(out_map)
#    show()
    return out_map



def dist(x1,y1,x2,y2):
    r""" Computes the distance between two points with coordinates
    (x1,y1) and (x2,y2)

    Parameters
    ----------
    x1 : float
        x coordinate of first point

    y1 : float
        y corrdinate of first point

    x2 : float
        x coordinate of second point

    y2 : float
        y corrdinate of second point

    Returns
    -------
    dist : float
        The euclidean distance between the two points

    References
    ----------

    Examples
    --------

    """
    return np.sqrt((x1-x2)*(x1-x2)+(y1-y2)*(y1-y2))

def find_clean_sky(img,nx,ny,nmax,map_sky):
    r""" Attemps to find a contiguous empty sky region of size [nx,ny], by
    randomly searching regions a total of nmax times. If no such region is found
    returns the last attempt. You can check the success of this function by
    comparing the outpu n to the input nmax.

    Parameters
    ----------
    img : float, array
        The image array containing the data

    nx : int
        Number of pixels in horizontal direction

    ny : int
        Number of pixels in vertical direction

    nmax : int
        Maximum number of tries for contiguous sky region search

    map_sky : int, array
        A binary image array flagging all pixels belonging to a detected object.
        All values above 0 are considered as positive detections.

    Returns
    -------
    n : int
        the number of tries it took to find an empty sky region.

    xr: int
        the center coordinate (horizontal axis) of the found sky region.

    yr : int
        the center coordinate (vertical axis) of the found sky region.


    References
    ----------

    Examples
    --------

    """
    all_sky=False
    N,M=img.shape
    n=0
    while (not all_sky) and (n<nmax):
        if (nx==N) or(ny==M):
            n=nmax
            xr=-99
            yr=-99
            break
        xr = rdm.randint(nx/2,N-nx/2-1)
        yr = rdm.randint(ny/2,M-ny/2-1)

        if True in np.array(map_sky[xr-nx/2:xr+nx/2+1,yr-ny/2:yr+ny/2+1]>0):
            n+=1
            continue
        else:
            all_sky=True
    return n,xr,yr

def extract_sky(img,sides,map_sky,nmax=100,**kwargs):
    r"""  Extracts a region of the sky from image np.where all the pixels have
    zero value in the segmentation mask.

    Parameters
    ----------
    img : float, array
        The image array containing the data

    sides : int, tuple
        The dimensions of the sky region to be extracted

    nmax : int,optional
        Maximum number of tries for contiguous sky region search

    map_sky : int, array
        A binary image array flagging all pixels belonging to a detected object.
        All values above 0 are considered as positive detections.

    Additional **kwargs are passed to sky_patch.

    Returns
    -------

    sky_r : float, array
        An array of the requested size with only sky pixels. If it cannot
        find one, it will produced a random (non-contiguous) sky region.

    References
    ----------

    Examples
    --------

    """
    nx,ny=sides

    dx,dy=0,0
    if nx%2==1:
        dx=1
    if ny%2==1:
        dy=1

    n,xr,yr = find_clean_sky(img,nx,ny,nmax,map_sky)

    if n>=nmax:
#        print "No cohesive region with np.size %s found! Sorting values for sky pixels!"%(str(sides))
#        sky_r=ones(sides)
        sky_r=sky_patch(img,map_sky,sides,**kwargs)[0]
    else:
        sky_r=img[xr-nx/2:xr+nx/2+dx,yr-ny/2:yr+ny/2+dy]

    return sky_r


def sky_region(fname,sides,sky_thresh=3.0,nmax=100):
    r""" Extracts a rectangular region from an image with sides where all values
    have zero value on the SExtractor segmention mask with threshold=sky_thresh.

    Parameters
    ----------

    fname : string
        The name of the image on which to run SExtractor

    sides : int, tuple
        The dimensions of the sky region to be extracted

    sky_thresh : float, optional
        Threshold to be passed to SExtractor.

    nmax : int,optional
        Maximum number of tries for contiguous sky region search. If it cannot
        find one, it will produced a random (non-contiguous) sky region.

    Returns
    -------

    sky_r : float, array
        An array of the requested size with only sky pixels.

    References
    ----------

    Examples
    --------

    """
    img=pyfits.getdata(fname)
    map_sky=gen_segmap_sex(fname,thresh=sky_thresh)
    sp.call('rm %s/test.cat'%os.getcwd(),shell=True)
    all_sky=False
    nx,ny=sides

    dx,dy=0,0
    if nx%2==1:
        dx=1
    if ny%2==1:
        dy=1

    N,M=img.shape
    n=0
    while (not all_sky) and (n<nmax):
        if (nx==N) or(ny==M):
            n=nmax
            break
        xr = rdm.randint(nx/2,N-nx/2-1)
        yr = rdm.randint(ny/2,M-ny/2-1)

        if True in np.array(map_sky[xr-nx/2:xr+nx/2+1,yr-ny/2:yr+ny/2+1]>0):
            n+=1
            continue
        else:
            all_sky=True

    if n>=nmax:
        print("No cohesive region with size %s found! Sorting values for sky pixels!"%(str(sides)))
        sky_r=sky_patch(img,map_sky,sides)[0]
    else:
        sky_r=img[xr-nx/2:xr+nx/2+dx,yr-ny/2:yr+ny/2+dy]

##    mpl.figure()
##    mpl.imshow(img,cmap='bone',vmax=0.05)
##    rect=np.array([[yr-ny/2,xr-nx/2],[yr+ny/2+1,xr-nx/2],[yr+ny/2+1,xr+nx/2+1],[yr-ny/2,xr+nx/2+1],[yr-ny/2,xr-nx/2]])-0.5
##    P=Polygon(rect,fill=False,linewidth=2,color='white')
##    ax=gca()
##    ax.add_artist(P)
##    mpl.figure()
##    mpl.imshow(map_sky,cmap='spectral')
##    ax=mpl.gca()
##    ax.add_artist(P)
##    show()


    return sky_r



def average_SNR(img,segmap):
    r""" Computes the np.average S/N ratio per galaxy pixel as from eq. 5
    of Lotz et al. 2004.

    Parameters
    ----------

    img : float, array
        The image array containing the data

    segmap : int, array
        A binary image array flagging all pixels to be considered for the
        computation. It uses all pixels with non-zero values.

    Returns
    -------

    SNR : float
        The average S/N per pixel of the input image


    References
    ----------

    Examples
    --------

    """
    exptime = 1 ### check the need for exposure time, check values
    ## Image should be in counts for it to be correctly interpreted

    sigma=sky_value(img,k=3)[-1]
    gal = img * segmap

    npix = np.size(gal[gal>0])

    noise_map = gal/np.sqrt(sigma*sigma+gal)*np.sqrt(exptime)

    SNR = np.sum(noise_map)/npix

    return SNR


def define_structure(size):
    r"""
    Returns a square array with a cross-shaped element of the given size. This
    array is useful when used for binary morphological operations such as
    erosion or dilation. Size must be an odd number greater or equal to three.

    Parameters
    ----------
    size : int
        The size of the desired struture element.

    Returns
    -------
    circular : int, array
        An array of shape [size,size] with an approximation of circular
        geometry.

    References
    ----------

    Examples
    --------

    """
    basic_structure = np.array([[0,1,0],\
                       [1,1,1],\
                       [0,1,0]],dtype=np.int)
    if size==3:
        return basic_structure
    assert size>=3, 'Minimum size 3 is required!'
    assert size%2==1, 'Structure element needs to by odd!'
    structure = np.zeros([size,size])
    structure[size/2-1:size/2+2,size/2-1:size/2+2]=basic_structure
    for i in range(size/3):
        structure = sci_nd.binary_dilation(structure,basic_structure).astype(np.int)
    return structure


def rebin2d(img,size_out,flux_scale=False):
    r""" Special case of non-integer magnification for 2D arrays
    from FREBIN of IDL Astrolib.

    Parameters
    ----------
    img : float, array
        The image array containing the data

    size_out : int, tuple
        A tuple containing the 2D dimensions of the desired output array.

    flux_scale : bool, optional
        If true, the flux of the output image is scaled by the area of its array.
        Else, all flux is preserved.

    Returns
    -------

    img_bin : float, array
        the input image resized to match the diemnsions of size_out.

    References
    ----------
    http://www.harrisgeospatial.com/docs/frebin.html

    Examples
    --------

    """
    assert len(size_out)==2, "size_out must have two elements"
    N,M = img.shape

    Nout,Mout = size_out
    xbox = N/float(Nout)
    ybox = M/float(Mout)

    temp_y = np.zeros([N,Mout])

    for i in range(Mout):
        rstart = i*ybox
        istart = int(rstart)

        rstop = rstart + ybox
        if int(rstop) > M-1:
            istop = M-1
        else:
            istop = int(rstop)

        frac1 = rstart-istart
        frac2 = 1.0 - (rstop-istop)
        if istart == istop:
            temp_y[:,i] = (1.0-frac1-frac2)*img[:,istart]
        else:
            temp_y[:,i] = np.sum(img[:,istart:istop+1],1) - frac1 * img[:,istart] - frac2 * img[:,istop]

    temp_y = temp_y.transpose()
    img_bin = np.zeros([Mout,Nout])

    for i in range(Nout):
        rstart = i*xbox
        istart = int(rstart)

        rstop = rstart + xbox
        if int(rstop) > N-1:
            istop = N-1
        else:
            istop = int(rstop)

        frac1 = rstart-istart
        frac2 = 1.0 - (rstop-istop)

        if istart == istop:
            img_bin[:,i] = (1.0-frac1-frac2)*temp_y[:,istart]
        else:
            img_bin[:,i] = np.sum(temp_y[:,istart:istop+1],1) - frac1 * temp_y[:,istart]- frac2 * temp_y[:,istop]

    if flux_scale:
        return img_bin.transpose()
    else:
        return img_bin.transpose()/(xbox*ybox)


def get_bounding_box(header,coords,size,pixelscale):
    r""" Returns a square bounding box coordinates (in pixels) centered in
    coords (astropy SkyCoord with ra,dec) and 'size' width in arcseconds.
    It requires the pixel scale (in arcseconds per pixel).

    Parameters
    ----------

    header : io.fits header object
        The header of the fits file to get the bounding box for.

    coords : astropy.coordinates.SkyCoord
        A set of coordinates (with ra,dec values) representing the center of
        the bounding box.

    size : float
        The size of the bounding box in arcseconds.

    pixelscale : float
        The pixel scale (in arcseconds per pixel) of the given image.

    Returns
    -------

    xl,xu,yl,yu : float, tuple
        The corner coordinates of the bounding box.

    References
    ----------

    Examples
    --------

    """
    centerCoords = get_center_coords_hdr(header,coords.ra.value[0],coords.dec.value[0])
    hsize = int(size/pixelscale)//2

    xl = int(centerCoords[0]-hsize)
    xu = int(centerCoords[0]+hsize)
    yl = int(centerCoords[1]-hsize)
    yu = int(centerCoords[1]+hsize)
    return (xl,xu,yl,yu)

def get_cutout(imgname,coords,size,pixelscale):
    r""" Returns a cutout from the given image, centered on coords and with the
    requested size (in arcseconds). A pixel scale of the image is also required.

    Parameters
    ----------

    imgname : str
        The name of the fits image to get the bounding box for.

    coords : astropy.coordinates.SkyCoord
        A set of coordinates (with ra,dec values) representing the center of
        the bounding box.

    size : float
        The size of the bounding box in arcseconds.

    pixelscale : float
        The pixel scale (in arcseconds per pixel) of the given image.

    Returns
    -------

    img : float, 2D array
        A cutout of the given image centered on coords, and with the given size.

    References
    ----------

    Examples
    --------

    """
    header = pyfits.getheader(imgname)
    boxCoords = get_bounding_box(header,coords,size,pixelscale)
    if boxCoords is None:
        return None
    else:
        xl,xu,yl,yu = boxCoords
    data = pyfits.getdata(imgname)
    return data[yl:yu,xl:xu]


if __name__=='__main__':
#    img = pyfits.getdata('CFHTLS_1.fits')
#    hdr=pyfits.getheader('CFHTLS_1.fits')
#    etime=hdr['exptime']
#    gain=hdr['gain']
###    img*=etime/gain
#    smap = gen_segmap_tresh(img,25,25,3)
#    print np.average_SNR(img,smap)

    pass


##
##def test_makestamps():
##    imgdir='/Users/bribeiro/Documents/PhD/VUDS/sample_zgt2_flags0203040922232429'
##    field='cosmos'
##    path="%s/%s/%i"%(imgdir,'cosmos',510202821)
##    tim=get_name_fits(path,'acs','I')
##    img=pyfits.getdata(tim)
##    maps=gen_segmap_sex(tim,thresh=3.)
##    ys,xs,e,theta,obj_num = get_sex_pars(167,167)
##    XC=xs[obj_num]
##    YC=ys[obj_num]
##    i,s,nc=make_stamps(XC,YC,img,maps,4,0.03)
##    ax=make_subplot(2,2,width=10,height=10)
##    ax[0].imshow(img)
##    ax[1].imshow(maps)
##    ax[2].imshow(i)
##    ax[3].imshow(s)
##    draw_segmap_border(ax[2],s)
##    show()
##    return
##test_makestamps()
##
