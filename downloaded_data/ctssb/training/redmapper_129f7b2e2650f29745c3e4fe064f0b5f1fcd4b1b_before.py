"""Classes to describe the volume limit mask.
"""

from __future__ import division, absolute_import, print_function
from past.builtins import xrange

import fitsio
import healpy as hp
import numpy as np
import esutil
import os

from .catalog import Catalog, Entry
from .depthmap import DepthMap
from .redsequence import RedSequenceColorPar
from .utilities import astro_to_sphere

class VolumeLimitMask(object):
    """
    A class to describe a volume limit mask.

    This is based on combining the red sequence model with depth maps in
    different bands, to determine the highest redshift that a typical
    red-sequence galaxy can be observed with the specified luminosity.

    """

    def __init__(self, config, vlim_lstar, vlimfile=None):
        """
        Instantiate a VolumeLimitMask

        If the mask described by maskfile already exists, it will be read in
        directly.  If it does not exist, it will be generated from the depth
        files described in the config parameters, and then stored in vlimfile.

        Parameters
        ----------
        config: `redmapper.Configuration`
           Configuration object
        vlim_lstar: `float`
           Luminosity cutoff (units of L*) for red-sequence volume limit
           computation
        vlimfile: `str`, optional
           Filename to store volume limit mask.  Default is None, which
           means generate the filename of the 'vlim_zmask' type.
        """
        self.config = config
        self.vlim_lstar = vlim_lstar

        if vlimfile is None:
            self.vlimfile = self.config.redmapper_filename('vl%02d_vlim_zmask' %
                                                            (int(self.vlim_lstar*10)))
        else:
            self.vlimfile = vlimfile

        if os.path.isfile(self.vlimfile):
            self._read_mask()
        else:
            self._build_mask()
            self._read_mask()


    def _read_mask(self):
        """
        Read an existing volume-limit mask into the VolumeLimitMask structure.
        """

        vliminfo, hdr = fitsio.read(self.vlimfile, ext=1, header=True, lower=True)
        vliminfo = Catalog(vliminfo)

        nside_mask = hdr['NSIDE']
        nest = hdr['NEST']

        self.submask_hpix = self.config.d.hpix
        self.submask_nside = self.config.d.nside
        self.submask_border = self.config.border
        self.galfile_nside = self.config.galfile_nside

        if nest != 1:
            hpix_ring = vliminfo.hpix
        else:
            hpix_ring = hp.nest2ring(nside_mask, vliminfo.hpix)

        if self.submask_hpix > 0:
            muse = get_hpmask_subpix_indices(self.submask_nside, self.submask_hpix,
                                             self.submask_border, nside_meask, hpix_ring)
        else:
            muse = np.arange(hpix_ring.size, dtype='i4')

        self.nside = nside_mask
        self.offset = np.min(hpix_ring[muse]) - 1
        self.ntot = np.max(hpix_ring[muse]) - np.min(hpix_ring[muse]) + 3

        self.npix = muse.size

        self.fracgood = np.zeros(self.npix + 1, dtype='f4')
        self.fracgood[0: self.npix] = vliminfo.fracgood[muse]
        self.zmax = np.zeros(self.npix + 1, dtype='f4')
        self.zmax[0: self.npix] = vliminfo.zmax[muse]

        # overflow bins
        self.fracgood[self.npix] = hp.UNSEEN
        self.zmax[self.npix] = 0.0

        # the look-up table
        self.hpix_to_index = np.zeros(self.ntot, dtype='i4') + self.npix
        self.hpix_to_index[hpix_ring[muse] - self.offset] = np.arange(self.npix)

    def _build_mask(self):
        """
        Build a VolumeLimitMask from the parameters in the config file, and
        store the mask in self.vlimfile
        """

        # Make some checks to make sure we can build a volume limit mask
        if not os.path.isfile(self.config.depthfile):
            raise RuntimeError("Cannot create a volume limit mask without a depth file")
        for fname in self.config.vlim_depthfiles:
            if not os.path.isfile(fname):
                raise RuntimeError("Could not find specified vlim_depthfile %s" % (fname))

        # Read in the red-sequence parameters
        zredstr = RedSequenceColorPar(self.config.parfile, fine=True)

        # create the redshift bins
        zbinsize = 0.001 # arbitrary fine bin
        nzbins = int(np.ceil((self.config.zrange[1] - self.config.zrange[0]) / zbinsize))
        # Note that we want to start one step above the low redshift range
        zbins = np.arange(nzbins) * zbinsize + self.config.zrange[0] + zbinsize

        # magnitude limits
        limmags = zredstr.mstar(zbins) - 2.5 * np.log10(self.vlim_lstar)

        # get the reference index
        ref_ind = self.config.bands.index(self.config.refmag)

        # Read in the primary depth structure
        depthinfo, hdr = fitsio.read(self.config.depthfile, ext=1, header=True, lower=True)
        dstr = Catalog(depthinfo)

        vmask = Catalog(np.zeros(dstr.size, dtype=[('hpix', 'i8'),
                                                   ('fracgood', 'f4'),
                                                   ('zmax', 'f4')]))
        vmask.hpix = dstr.hpix
        vmask.fracgood = dstr.fracgood

        nside = hdr['NSIDE']
        nest = hdr['NEST']

        lo, = np.where(dstr.m50 < limmags.min())
        vmask.zmax[lo] = zbins.min()
        hi, = np.where(dstr.m50 > limmags.max())
        vmask.zmax[hi] = zbins.max()
        mid, = np.where((dstr.m50 >= limmags.min()) & (dstr.m50 <= limmags.max()))
        if mid.size > 0:
            l = np.searchsorted(limmags, dstr.m50[mid], side='right')
            vmask.zmax[mid] = zbins[l]

        # And read in any additional depth structures
        for i, depthfile in enumerate(self.config.vlim_depthfiles):
            depthinfo2, hdr2 = fitsio.read(depthfile, ext=1, header=True, lower=True)
            dstr2 = Catalog(depthinfo2)

            nsig = hdr2['NSIG']
            zp = hdr2['ZP']

            # find mag name thing...
            # Note this is validated in the config read
            map_ind = self.config.bands.index(self.config.vlim_bands[i])

            # match pixels
            a, b = esutil.numpy_util.match(vmask.hpix, dstr2.hpix)

            # compute the limit (this should be moved to a utility function)
            n2 = self.config.vlim_nsigs[i]**2.
            flim_in = 10.**((dstr2.limmag[b] - zp) / (-2.5))
            fn = np.clip((flim_in**2. * dstr2.exptime[b]) / (nsig**2.) - flim_in, 0.001, None)
            flim_mask = (n2 + np.sqrt(n2**2. + 4.*dstr2.exptime[b] * n2 * fn)) / (2.*dstr2.exptime[b])
            lim_mask = np.zeros(vmask.size)
            lim_mask[a] = zp - 2.5*np.log10(flim_mask)

            zinds = np.searchsorted(zredstr.z, zbins, side='right')

            limmags_temp = zredstr.mstar(zbins) - 2.5*np.log10(self.vlim_lstar)
            refmag_lim = limmags_temp.copy()

            if (map_ind == ref_ind):
                self.config.logger.info('Warning: vlim_band %s is the same as the reference band!  Skipping...' % (self.config.vlim_bands[i]))
            else:
                if map_ind < ref_ind:
                    # Need to go blueward
                    for jj in xrange(ref_ind - 1, map_ind - 1, -1):
                        limmags_temp += (zredstr.c[zinds, jj] + zredstr.slope[zinds, jj]) * (refmag_lim - zredstr.pivotmag[zinds])
                else:
                    # Need to go redward
                    for jj in xrange(ref_ind, map_ind):
                        limmags_temp -= (zredstr.c[zinds, jj] + zredstr.slope[zinds, jj]) * (refmag_lim - zredstr.pivotmag[zinds])

            # adjust zmax with zmax_temp
            zmax_temp = np.zeros(vmask.size)

            lo, = np.where(lim_mask < limmags_temp.min())
            zmax_temp[lo] = zbins.min()
            hi, = np.where(lim_mask > limmags_temp.max())
            zmax_temp[hi] = zbins.max()
            mid, = np.where((lim_mask >= limmags_temp.min()) & (lim_mask <= limmags_temp.max()))
            if mid.size > 0:
                l = np.searchsorted(limmags_temp, lim_mask[mid], side='right')
                zmax_temp[mid] = zbins[l]

            limited, = np.where(zmax_temp < vmask.zmax)
            vmask.zmax[limited] = zmax_temp[limited]

        gd, = np.where(vmask.zmax > zbins[0])
        vmask = vmask[gd]

        outhdr = fitsio.FITSHDR()
        outhdr['NSIDE'] = nside
        outhdr['NEST'] = nest

        vmask.to_fits_file(self.vlimfile, header=outhdr)

    def calc_zmax(self, ra, dec, get_fracgood=False):
        """
        Calculate the maximum redshifts associated with a set of ra/decs.

        Parameters
        ----------
        ra: `np.array` or `float`
           Float array of right ascensions
        dec: `np.array` or `float`
           Float array of declinations
        get_fracgood: `bool`, optional
           Also retrieve the fracgood pixel coverage.  Default is False.

        Returns
        -------
        zmax: `np.array`
           Float array of maximum redshifts
        fracgood: `np.array`
           Float array of fracgood, if get_fracgood=True
        """

        _ra = np.atleast_1d(ra)
        _dec = np.atleast_1d(dec)

        if (_ra.size != _dec.size):
            raise ValueError("ra, dec must be same length")

        theta, phi = astro_to_sphere(_ra, _dec)
        ipring = hp.ang2pix(self.nside, theta, phi)
        ipring_offset = np.clip(ipring - self.offset, 0, self.ntot-1)

        if not get_fracgood:
            return self.zmax[self.hpix_to_index[ipring_offset]]
        else:
            return (self.zmax[self.hpix_to_index[ipring_offset]],
                    self.fracgood[self.hpix_to_index[ipring_offset]])

    def get_areas(self):
        """
        Retrieve the area structure (area as a function of redshift) associated
        with the volume-limit mask.

        Returns
        -------
        astr: `redmapper.Catalog`
           Area structure catalog, with .z and .area
        """

        zbinsize = self.config.area_finebin
        zbins = np.arange(self.config.zrange[0], self.config.zrange[1], zbinsize)

        astr = Catalog(np.zeros(zbins.size, dtype=[('z', 'f4'),
                                                   ('area', 'f4')]))
        astr.z = zbins

        pixsize = hp.nside2pixarea(self.nside, degrees=True)

        # ignore the last overflow pixel
        st = np.argsort(self.zmax[:-1])
        zmax = self.zmax[st]

        fracgoods = self.fracgood[st]

        inds = np.searchsorted(zmax, zbins, side='right')

        lo = (inds <= 0)
        astr.area[lo] = np.sum(fracgoods.astype(np.float64)) * pixsize

        if np.sum(~lo) > 0:
            carea = pixsize * np.cumsum(fracgoods.astype(np.float64))
            astr.area[~lo] = carea[carea.size - inds[~lo]]

        return astr

class VolumeLimitMaskFixed(object):
    """
    A class to describe a volume limit mask with a fixed redshift maximum.

    This class is used as a placeholder when there is no depth information to
    construct a true VolumeLimitMask.
    """

    def __init__(self, config):
        """
        Instantiate a VolumeLimitMaskFixed

        The maximum redshift is set by config.zrange[1] (the max redshift in
        the config file).

        Parameters
        ----------
        config: `redmapper.Configuration`
           Configuration object
        """
        self.z_max = config.zrange[1]
        self.zrange = config.zrange
        self.zbinsize = config.area_finebin
        self.area = config.area

    def calc_zmax(self, ra, dec):
        """
        Calculate the maximum redshifts associated with a set of ra/decs.

        Parameters
        ----------
        ra: `np.array` or `float`
           Float array of right ascensions
        dec: `np.array` or `float`
           Float array of right ascensions

        Returns
        -------
        zmax: `float`
           Maximum redshift from the config file.
        """

        return self.z_max

    def get_areas(self):
        """
        Retrieve the area structure (area as a function of redshift) associated
        with the fixed-redshift mask.

        Returns
        -------
        astr: `redmapper.Catalog`
           Area structure catalog, with .z and .area
        """

        zbins = np.arange(self.zrange[0], self.zrange[1], self.zbinsize)

        astr = Catalog(np.zeros(zbins.size, dtype=[('z', 'f4'),
                                                   ('area', 'f4')]))
        astr.z = zbins

        astr.area = self.area

        return astr
