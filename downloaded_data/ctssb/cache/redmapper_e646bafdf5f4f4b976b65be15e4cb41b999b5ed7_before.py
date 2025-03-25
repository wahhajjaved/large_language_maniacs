import fitsio
import esutil as eu
import numpy as np
import itertools
from solver_nfw import Solver
from catalog import Catalog, Entry
from utilities import chisq_pdf


class Cluster(Entry):
    """Docstring."""

    def find_members(self, radius=None, galcat=None):
        if galcat is None:
            raise ValueError("A GalaxyCatalog object must be specified.")
        if radius is None or radius < 0 or radius > 180:
            raise ValueError("A radius in degrees must be specified.")
        indices, dists = galcat.match(self, radius) # pass in a Galaxy?
        self.members = galcat[indices]
        new_fields = [('DIST', 'f8'), ('R', 'f8'), ('PMEM', 'f8'), 
                        ('CHISQ', 'f8')]
        self.members.add_fields(new_fields)
        self.members.dist = dists

    def _calc_radial_profile(self, rscale=0.15): 
        corer = 0.1
        x, corex = self.members.r/rscale, corer/rscale
        sigx = np.zeros(self.members.r.size)

        low, = np.where(x < corex)
        mid, = np.where((x >= corex) & (x < 1.0))
        high, = np.where((x >= 1.0) & (x < 10.0/rscale))
        other, = np.where((x > 0.999) & (x < 1.001))

        if low.size > 0:
            arg = np.sqrt((1. - corex)/(1. + corex))
            pre = 2./(np.sqrt(1. - corex**2))
            front = 1./(corex**2 - 1)
            sigx[low] = front * (1. - pre*0.5*np.log((1.+arg)/(1.-arg)))

        if mid.size > 0:
            arg = np.sqrt((1. - x[mid])/(1. + x[mid]))
            pre = 2./(np.sqrt(1. - x[mid]**2))
            front = 1./(x[mid]**2 - 1.)
            sigx[mid] = front * (1. - pre*0.5*np.log((1.+arg)/(1.-arg)))

        if high.size > 0:
            arg = np.sqrt((x[high] - 1.)/(x[high] + 1.))
            pre = 2./(np.sqrt(x[high]**2 - 1.))
            front = 1./(x[high]**2 - 1)
            sigx[high] = front * (1. - pre*np.atan(arg))

        if other.size > 0:
            xlo, xhi = 0.999, 1.001
            arglo, arghi = np.sqrt((1-xlo)/(1+xlo)), np.sqrt((xhi-1)/(xhi+1))
            prelo, prehi = 2./np.sqrt(1.-xlo**2), 2./np.sqrt(xhi**2 - 1)
            frontlo, fronthi = 1./(xlo**2 - 1), 1./(xhi**2 - 1)
            testlo = frontlo * (1 - prelo*0.5*np.log((1+arglo)/(1-arglo)))
            testhi = fronthi * (1 - prehi*np.atan(arghi))
            sigx[other] = (testlo + testhi)/2.

        return sigx

    def _calc_luminosity(self, zredstr, normmag):
        zind = np.clip(zredstr.zindex(self.z), 0, zredstr.size-1)
        refind = np.clip(zredstr.lumrefmagindex(normmag), 0, zredstr.lumrefmagbins.size-1)
        normalization = zredstr.lumnorm[refind, zind]
        mstar, alpha = zredstr.mstar(self.z), zredstr.alpha(self.z)
        phi_term_a = 10. ** (0.4 * (alpha +1.) * (mstar-self.members.refmag))
        phi_term_b = np.exp(-10. ** (0.4 * (mstar-self.members.refmag)))
        return phi_term_a * phi_term_b / normalization

    def _calc_bkg_density(self, bkg, cosmo):
        mpc_scale = np.radians(1.) * cosmo.Dl(0, self.z)
        sigma_g = bkg.sigma_g_lookup(self.z, self.members.chisq, 
                                                    self.members.refmag)
        return 2 * np.pi * self.members.r * (sigma_g/mpc_scale**2)

    def calc_richness(self, zredstr, bkg, cosmo, confstr, r0=1.0, beta=0.2):
        mstar, alpha = zredstr.mstar(self.z), zredstr.alpha(self.z)
        maxmag = mstar - 2.5*np.log10(confstr.lval_reference)

        self.members.r = np.radians(self.members.dist) * cosmo.Dl(0, self.z)
        self.members.chisq = zredstr.calculate_chisq(self.members, self.z)
        rho = chisq_pdf(self.members.chisq, zredstr.ncol)
        nfw = self._calc_radial_profile()
        phi = self._calc_luminosity(zredstr, maxmag)
        ucounts = (2*np.pi*self.members.r) * nfw * phi * rho
        bcounts = self._calc_bkg_density(bkg, cosmo)
        
        w = 0

        richness_obj = Solver(r0, beta, ucounts, bcounts, r, w)


class ClusterCatalog(Catalog): 
    """Dosctring."""
    entry_class = Cluster

