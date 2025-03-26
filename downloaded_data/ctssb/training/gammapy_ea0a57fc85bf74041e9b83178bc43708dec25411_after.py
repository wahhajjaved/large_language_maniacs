# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from astropy.tests.helper import pytest, assert_quantity_allclose
import astropy.units as u
from numpy.testing import assert_allclose 
from ...datasets import gammapy_extra
from ...spectrum.spectrum_extraction import SpectrumObservationList, SpectrumObservation
from ...spectrum.spectrum_fit import SpectrumFit
from ...utils.testing import requires_dependency, requires_data, SHERPA_LT_4_8
from astropy.utils.compat import NUMPY_LT_1_9


@pytest.mark.skipif('NUMPY_LT_1_9')
@pytest.mark.skipif('SHERPA_LT_4_8')
@requires_dependency('sherpa')
@requires_data('gammapy-extra')
def test_spectral_fit():
    pha1 = gammapy_extra.filename("datasets/hess-crab4_pha/pha_obs23592.fits")
    pha2 = gammapy_extra.filename("datasets/hess-crab4_pha/pha_obs23523.fits")
    obs1 = SpectrumObservation.read(pha1)
    obs2 = SpectrumObservation.read(pha2)
    obs_list = SpectrumObservationList([obs1, obs2])

    fit = SpectrumFit(obs_list)
    
    fit.run()
    assert fit.result.fit.spectral_model == 'PowerLaw'
    assert_allclose(fit.result.fit.statval, 100.433, rtol=1e-3)
    assert_quantity_allclose(fit.result.fit.parameters.index,
                             2.405 * u.Unit(''), rtol=1e-3)
    
    # Compare Npred vectors
    # TODO: Read model from FitResult
    from gammapy.spectrum.models import PowerLaw
    model = PowerLaw(index=fit.result.fit.parameters.index,
                     reference=fit.result.fit.parameters.reference,
                     amplitude=fit.result.fit.parameters.norm
                    )
    npred = obs1.predicted_counts(model)
    assert_allclose(fit.result.fit.n_pred, npred.data, rtol=1e-3)
