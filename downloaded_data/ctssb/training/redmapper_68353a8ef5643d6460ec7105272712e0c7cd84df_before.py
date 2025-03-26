import matplotlib
matplotlib.use('Agg')

import unittest
import os
import shutil
import numpy.testing as testing
import numpy as np
import fitsio
import tempfile
from numpy import random

from redmapper.configuration import Configuration
from redmapper.calibration.selectspecred import SelectSpecRedGalaxies

class SelectSpecRedTestCase(unittest.TestCase):
    """
    Tests for selecting red galaxies with spectra in
    redmapper.calibration.SelectSpecRedGalaxies
    """
    def test_selectspecred(self):
        """
        Run tests on redmapper.calibration.SelectSpecRedGalaxies
        """
        random.seed(seed=12345)

        file_path = 'data_for_tests'
        conf_filename = 'testconfig.yaml'
        config = Configuration(os.path.join(file_path, conf_filename))

        config.galfile = os.path.join(file_path, 'test_dr8_trainred_gals.fit')
        config.specfile_train = os.path.join(file_path, 'test_dr8_trainred_spec.fit')
        config.zrange = [0.1,0.2]

        self.test_dir = tempfile.mkdtemp(dir='./', prefix="TestRedmapper-")
        config.outpath = self.test_dir

        config.redgalfile = os.path.join(self.test_dir, 'test_redgals.fits')
        config.redgalmodelfile = os.path.join(self.test_dir, 'test_redgalmodel.fits')

        selred = SelectSpecRedGalaxies(config)
        selred.run()

        # Check that files got made
        self.assertTrue(os.path.isfile(config.redgalfile))
        self.assertTrue(os.path.isfile(config.redgalmodelfile))
        self.assertTrue(os.path.isfile(os.path.join(config.outpath, config.plotpath,
                                                    '%s_redgals_g-r.png' % (config.d.outbase))))

        redgals = fitsio.read(config.redgalfile, ext=1)
        redgalmodel = fitsio.read(config.redgalmodelfile, ext=1)

        self.assertEqual(redgals.size, 1200)

        testing.assert_almost_equal(redgalmodel['meancol'][0][:, 1],
                                    np.array([0.78079545, 1.0870565,  1.4724078]), 4)

        # These numbers have been updated for the symmetric truncation cut, which
        # looks like it works better.  An "upgrade" from the IDL code.
        # Also tweaks with new fitter.
        testing.assert_almost_equal(redgalmodel['meancol_scatter'][0][:, 1],
                                    np.array([0.0299095,  0.04490384, 0.02395549]), 4)
        testing.assert_almost_equal(redgalmodel['medcol'][0][:, 1],
                                    np.array([0.7838367, 1.0860928, 1.4521087]), 4)
        testing.assert_almost_equal(redgalmodel['medcol_width'][0][:, 1],
                                    np.array([0.0247597, 0.0453822, 0.01871387]), 4)

    def setUp(self):
        self.test_dir = None

    def tearDown(self):
        if self.test_dir is not None:
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir, True)


if __name__=='__main__':
    unittest.main()
