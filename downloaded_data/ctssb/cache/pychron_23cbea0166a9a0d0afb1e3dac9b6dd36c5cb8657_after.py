# ===============================================================================
# Copyright 2015 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===============================================================================

# ============= enthought library imports =======================
# ============= standard library imports ========================
from numpy import array
# ============= local library imports  ==========================
from uncertainties import std_dev, nominal_value
from pychron.pipeline.plot.plotter.references_series import ReferencesSeries


class ICFactor(ReferencesSeries):
    def _get_interpolated_value(self, po, analysis):
        n, d = po.name.split('/')
        #iso = next((i for i in analysis.isotopes.itervalues() if i.detector == d), None)
        v, e = 0, 0
        if d in analysis.temporary_ic_factors:
            ic = analysis.temporary_ic_factors[d]
            v, e = nominal_value(ic), std_dev(ic)

        return v, e

    def _set_interpolated_values(self, iso, fit, ans, p_uys, p_ues):
        n, d = iso.split('/')
        for ui, v, e in zip(ans, p_uys, p_ues):
            if v is not None and e is not None:
                ui.set_temporary_ic_factor(d, v, e)

    def _get_current_data(self, po):
        if '/' in po.name:
            n, d = po.name.split('/')
            nys = array([ri.get_ic_factor(n) for ri in self.sorted_analyses])
            dys = array([ri.get_ic_factor(d) for ri in self.sorted_analyses])
            return dys / nys
        else:
            return array([ri.get_value(po.name) for ri in self.sorted_analyses])

    def _get_reference_data(self, po):
        if '/' in po.name:
            n, d = po.name.split('/')

            nys = [ri.get_isotope(detector=n) for ri in self.sorted_references]
            dys = [ri.get_isotope(detector=d) for ri in self.sorted_references]

            nys = array([ni.get_non_detector_corrected_value() for ni in nys if ni is not None])
            dys = array([di.get_non_detector_corrected_value() for di in dys if di is not None])
            rys = nys/ dys
        else:
            rys = array([ri.get_value(po.name) for ri in self.sorted_references])
        rys = rys / po.standard_ratio
        return rys

# ============= EOF =============================================
