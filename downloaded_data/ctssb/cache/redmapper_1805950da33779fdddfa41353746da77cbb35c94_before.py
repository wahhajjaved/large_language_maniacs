import unittest
import numpy.testing as testing
import numpy as np
import fitsio

from esutil.cosmology import Cosmo
from redmapper.catalog import Entry
from redmapper.cluster import Cluster
from redmapper.config import Configuration
from redmapper.galaxy import GalaxyCatalog
from redmapper.background import Background
from redmapper.redsequence import RedSequenceColorPar


class BackgroundStub(Background):

    def __init__(self, filename):
        obkg = Entry.from_fits_file(filename)
        self.refmagbins = obkg.refmagbins
        self.chisqbins = obkg.chisqbins
        self.lnchisqbins = obkg.lnchisqbins
        self.zbins = obkg.zbins
        self.sigma_g = obkg.sigma_g
        self.sigma_lng = obkg.sigma_lng


class ClusterFiltersTestCase(unittest.TestCase):

    def test_nfw_filter(self):
        test_indices = np.array([46, 38,  1,  1, 11, 24, 25, 16])
        py_nfw = self.cluster._calc_radial_profile()[test_indices]
        idl_nfw = np.array([0.29360449, 0.14824243, 0.14721203, 0.14721203, 
                            0.23459411, 0.31615007, 0.29307860, 0.29737136])
        testing.assert_almost_equal(py_nfw, idl_nfw)

    def test_lum_filter(self):
        test_indices = np.array([47, 19,  0, 30, 22, 48, 34, 19])
        zred_filename, conf_filename = 'test_dr8_pars.fit', 'testconfig.yaml'
        zredstr = RedSequenceColorPar(self.file_path + '/' + zred_filename)
        confstr = Configuration(self.file_path + '/' + conf_filename)
        mstar = zredstr.mstar(self.clusters.z)
        maxmag = mstar - 2.5*np.log10(confstr.lval_reference)
        py_lum = self.cluster._calc_luminosity(zredstr, maxmag)
        idl_lum = np.array([])
        testing.assert_almost_equal(py_lum, idl_lum)

    def test_bkg_filter(self):
        test_indices = np.array([29, 16, 27,  5, 38, 35, 25, 43])
        bkg_filename = 'test_bkg.fit'
        bkg = BackgroundStub(self.file_path + '/' + bkg_filename)
        py_bkg = self.cluster._calc_bkg_density(bkg, Cosmo())
        idl_bkg = np.array([])
        testing.assert_almost_equal(py_bkg, idl_bkg)

    def setUp(self):
        self.cluster = Cluster(np.empty(1))
        self.file_path, filename = 'data', 'test_cluster_members.fit'
        self.cluster.members = GalaxyCatalog.from_fits_file(self.file_path 
                                                            + '/' + filename)
        self.cluster.z = self.cluster.members.z[0]

        
class ClusterMembersTestCase(unittest.TestCase):

    def test_member_finding(self): pass
    def test_richness(self): pass


if __name__=='__main__':
    unittest.main()

