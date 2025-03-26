# ===============================================================================
# Copyright 2012 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===============================================================================


import math

from numpy import array, nan
# ============= enthought library imports =======================
from traits.api import List, Property, cached_property, Str, Bool, Int, Event, Float, Any, Enum
from uncertainties import ufloat, nominal_value, std_dev

from pychron.core.stats.core import calculate_mswd, calculate_weighted_mean, validate_mswd
from pychron.experiment.utilities.identifier import make_aliquot
from pychron.processing.analyses.analysis import IdeogramPlotable
from pychron.processing.arar_age import ArArAge
from pychron.processing.argon_calculations import calculate_plateau_age, age_equation, calculate_isochron
from pychron.pychron_constants import ALPHAS, AGE_MA_SCALARS, MSEM, SD, AGE_SUBGROUPINGS, SUBGROUPINGS, \
    SUBGROUPING_ATTRS


def AGProperty(*depends):
    d = 'dirty,analyses:[temp_status]'
    if depends:
        d = '{},{}'.format(','.join(depends), d)

    return Property(depends_on=d)


class AnalysisGroup(IdeogramPlotable):
    attribute = Str('uage')
    analyses = List
    nanalyses = AGProperty()

    weighted_age = AGProperty()
    arith_age = AGProperty()
    integrated_age = AGProperty()

    weighted_kca = AGProperty()
    arith_kca = AGProperty()
    integrated_kca = AGProperty()

    weighted_kcl = AGProperty()
    arith_kcl = AGProperty()
    integrated_kcl = AGProperty()

    weighted_rad40_percent = AGProperty()
    arith_rad40_percent = AGProperty()
    integrated_rad40_percent = AGProperty()

    weighted_moles_k39 = AGProperty()
    arith_moles_k39 = AGProperty()
    integrated_moles_k39 = AGProperty()

    weighted_age_error_kind = Str
    arith_age_error_kind = Str

    mswd = Property

    isochron_age = AGProperty()
    isochron_age_error_kind = Str
    identifier = Property

    repository_identifier = Property(depends_on='_repository_identifier')
    _repository_identifier = Str

    irradiation = Property
    irradiation_label = Property
    sample = Property
    project = Property
    aliquot = Property(depends_on='_aliquot')
    _aliquot = Any

    material = Property
    unit = Str
    location = Str

    _sample = Str
    age_scalar = Property
    age_units = Property

    j_err = AGProperty()
    j = AGProperty()
    include_j_error_in_mean = Bool(True)
    include_j_error_in_individual_analyses = Bool(False)

    # percent_39Ar = AGProperty()
    dirty = Event

    total_n = AGProperty()

    arar_constants = AGProperty()

    isochron_4036 = None
    isochron_regressor = None
    _age_units = None

    # used by XLSXAnalysisWriter/subgrouping
    subgroup_kind = None

    def __init__(self, *args, **kw):
        super(AnalysisGroup, self).__init__(make_arar_constants=False, *args, **kw)

    @property
    def nratio(self):
        return '{}/{}'.format(self.nanalyses, len(self.analyses))

    def attr_stats(self, attr):
        w, sd, sem, (vs, es) = self._calculate_weighted_mean(attr, error_kind='both')
        mswd = calculate_mswd(vs, es, wm=w)
        valid_mswd = validate_mswd(mswd, self.nanalyses)
        mi = min(vs)
        ma = max(vs)

        total_dev = (ma - mi) / ma * 100

        return {'mean': w,
                'sd': sd,
                'sem': sem,
                'mswd': mswd,
                'valid_mswd': valid_mswd,
                'min': mi, 'max': ma, 'total_dev': total_dev}

    def get_mswd_tuple(self):
        mswd = self.mswd
        valid_mswd = validate_mswd(mswd, self.nanalyses)
        return mswd, valid_mswd, self.nanalyses

    def set_temporary_age_units(self, a):
        self._age_units = a
        self.dirty = True

    def _get_age_units(self):
        if self._age_units:
            return self._age_units

        return self.analyses[0].arar_constants.age_units

    def _get_arar_constants(self):
        return self.analyses[0].arar_constants

    def _get_age_scalar(self):
        au = self.age_units
        return AGE_MA_SCALARS[au]

    # @cached_property
    def _get_mswd(self):
        attr = self.attribute
        if attr.startswith('uage'):
            attr = 'uage'
            if self.include_j_error_in_individual_analyses:
                attr = 'uage_w_j_err'

        return self._calculate_mswd(attr)

    def _calculate_mswd(self, attr, values=None):
        m = 0
        if values is None:
            values = self._get_values(attr)

        if values:
            vs, es = values
            m = calculate_mswd(vs, es)

        return m

    @cached_property
    def _get_j_err(self):
        j = self.j
        try:
            e = (std_dev(j) / nominal_value(j)) if j is not None else 0
        except ZeroDivisionError:
            e = nan
        return e

    @cached_property
    def _get_j(self):
        j = self.analyses[0].j
        return j

    @cached_property
    def _get_isochron_age(self):
        a = self.calculate_isochron_age()
        if a is None:
            a = ufloat(0, 0)

        return a

    @cached_property
    def _get_aliquot(self):
        a = self._aliquot
        if not a:
            a = self.analyses[0].aliquot
        return a

    def _set_aliquot(self, a):
        self._aliquot = a

    @cached_property
    def _get_identifier(self):
        return self.analyses[0].labnumber

    @cached_property
    def _get_repository_identifier(self):
        if self._repository_identifier:
            return self._repository_identifier
        else:
            return self.analyses[0].repository_identifier

    def _set_repository_identifier(self, v):
        self._repository_identifier = v

    @cached_property
    def _get_irradiation_label(self):
        return self.analyses[0].irradiation_label

    @cached_property
    def _get_irradiation(self):
        return self.analyses[0].irradiation

    @cached_property
    def _get_material(self):
        return self.analyses[0].material

    @cached_property
    def _get_sample(self):
        sam = self._sample
        if not sam:
            sam = self.analyses[0].sample
        return sam

    def _set_sample(self, s):
        self._sample = s

    @cached_property
    def _get_project(self):
        return self.analyses[0].project

    @cached_property
    def _get_arith_age(self):
        if self.include_j_error_in_individual_analyses:
            v, e = self._calculate_arithmetic_mean('uage')
        else:
            v, e = self._calculate_arithmetic_mean('uage_wo_j_err')
        e = self._modify_error(v, e, self.arith_age_error_kind)
        return ufloat(v, e)  # / self.age_scalar

    @cached_property
    def _get_weighted_age(self):
        attr = self.attribute
        if attr.startswith('uage'):
            attr = 'uage_w_j_err' if self.include_j_error_in_individual_analyses else 'uage'
        # if self.include_j_error_in_individual_analyses:
        #         v, e = self._calculate_weighted_mean('uage', self.weighted_age_error_kind)
        #     else:
        #         v, e = self._calculate_weighted_mean('uage_wo_j_err', self.weighted_age_error_kind)
        # else:

        v, e = self._calculate_weighted_mean(attr, self.weighted_age_error_kind)
        e = self._modify_error(v, e, self.weighted_age_error_kind)
        try:
            return ufloat(v, max(0, e))  # / self.age_scalar
        except AttributeError:
            return ufloat(0, 0)

    def _modify_error(self, v, e, kind, mswd=None, include_j_error=None):

        if mswd is None:
            mswd = self.mswd

        if kind == MSEM:
            e *= mswd ** 0.5 if mswd > 1 else 1

        return e

    @cached_property
    def _get_weighted_kca(self):
        return ufloat(*self._calculate_weighted_mean('kca'))

    @cached_property
    def _get_arith_kca(self):
        return ufloat(*self._calculate_arithmetic_mean('kca'))

    @cached_property
    def _get_integrated_kca(self):
        return ufloat(*self._calculate_integrated('kca'))

    @cached_property
    def _get_weighted_kcl(self):
        return ufloat(*self._calculate_weighted_mean('kcl'))

    @cached_property
    def _get_arith_kcl(self):
        return ufloat(*self._calculate_arithmetic_mean('kcl'))

    @cached_property
    def _get_integrated_kcl(self):
        return ufloat(*self._calculate_integrated('kcl'))

    @cached_property
    def _get_weighted_rad40_percent(self):
        return ufloat(*self._calculate_weighted_mean('rad40_percent'))

    @cached_property
    def _get_arith_rad40_percent(self):
        return ufloat(*self._calculate_arithmetic_mean('rad40_percent'))

    @cached_property
    def _get_integrated_rad40_percent(self):
        return ufloat(*self._calculate_integrated('rad40_percent'))

    @cached_property
    def _get_weighted_moles_k39(self):
        return ufloat(*self._calculate_weighted_mean('k39'))

    @cached_property
    def _get_arith_moles_k39(self):
        return ufloat(*self._calculate_arithmetic_mean('k39'))

    @cached_property
    def _get_integrated_moles_k39(self):
        return ufloat(*self._calculate_integrated('k39'))

    # @cached_property
    # def _get_percent_39Ar(self):
    #     return 0

    @cached_property
    def _get_total_n(self):
        return len(self.analyses)

    @cached_property
    def _get_nanalyses(self):
        return len(list(self.clean_analyses()))

    def clean_analyses(self):
        return (ai for ai in self.analyses if not ai.is_omitted())

    def _get_values(self, attr):
        vs = (ai.get_value(attr) for ai in self.clean_analyses())
        vs = [vi for vi in vs if vi is not None]
        if vs:
            vs, es = list(zip(*[(nominal_value(v), std_dev(v)) for v in vs]))
            vs, es = array(vs), array(es)
            return vs, es

    def _calculate_mean(self, attr, use_weights=True, error_kind=None):

        args = self._get_values(attr)
        sem = 0
        if args:
            vs, es = args
            if use_weights:
                av, werr = calculate_weighted_mean(vs, es)

                if error_kind == 'both':
                    sem = werr
                    n = len(vs)
                    werr = (sum((av - vs) ** 2) / (n - 1)) ** 0.5

                elif error_kind == SD:
                    n = len(vs)
                    werr = (sum((av - vs) ** 2) / (n - 1)) ** 0.5

            else:
                av = vs.mean()
                werr = vs.std(ddof=1)
        else:
            av, werr = 0, 0

        if error_kind == 'both':
            return av, werr, sem, args
        else:
            return av, werr

    def _calculate_integrated(self, attr):
        uv = ufloat(0, 0)
        ans = list(self.clean_analyses())

        prs = ans[0].production_ratios

        def apply_pr(n, d, k):
            pr = 1
            if prs:
                pr = prs.get(k, 1)
                if not pr:
                    pr = 1.0

                pr = 1 / pr

            try:
                v = sum(n) / sum(d) * pr
            except ZeroDivisionError:
                v = 0

            return v

        if attr == 'kca':
            ks = [ai.get_computed_value('k39') for ai in ans]
            cas = [ai.get_non_ar_isotope('ca37') for ai in ans]
            uv = apply_pr(ks, cas, 'Ca_K')
        elif attr == 'kcl':
            ks = [ai.get_computed_value('k39') for ai in ans]
            cls = [ai.get_non_ar_isotope('cl38') for ai in ans]
            uv = apply_pr(ks, cls, 'Cl_k')
        elif attr == 'rad40_percent':
            ns = [ai.rad40 for ai in ans]
            ds = [ai.total40 for ai in ans]
            uv = apply_pr(ns, ds, '')
        elif attr == 'k39':
            uv = sum([ai.get_computed_value('k39') for ai in ans])

        return uv

    def _calculate_arithmetic_mean(self, attr):
        return self._calculate_mean(attr, use_weights=False)

    def _calculate_weighted_mean(self, attr, error_kind=None):
        return self._calculate_mean(attr, use_weights=True, error_kind=error_kind)

    def get_isochron_data(self):
        ans = [a for a in self.analyses if isinstance(a, ArArAge)]
        exclude = [i for i, x in enumerate(ans) if x.is_omitted()]
        if ans:
            return calculate_isochron(ans, self.isochron_age_error_kind, exclude=exclude)

    def calculate_isochron_age(self):
        # args = calculate_isochron(list(self.clean_analyses()), self.isochron_age_error_kind,
        #                           include_j_err=self.include_j_error_in_mean)
        args = self.get_isochron_data()
        if args:
            age = args[0]
            self.isochron_4036 = args[1]
            reg = args[2]
            self.isochron_regressor = reg
            v, e = nominal_value(age), std_dev(age)
            e = self._modify_error(v, e, self.isochron_age_error_kind, mswd=reg.mswd)

            return ufloat(v, e)


# class IntermediateAnalysis(HasTraits):
#     analysis_group = Instance(AnalysisGroup)
#
#     def is_omitted(self):
#         return False
#
#     def get_value(self, attr):
#         try:
#             return getattr(self, attr)
#         except AttributeError:
#             print('sdfa', attr)
#             return 0
#
#     def __getattr__(self, item):
#         return getattr(self.analysis_group, item)


class StepHeatAnalysisGroup(AnalysisGroup):
    plateau_age = AGProperty()
    integrated_age = AGProperty()

    include_j_error_in_plateau = Bool(True)
    plateau_steps_str = Str
    plateau_steps = None

    plateau_age_error_kind = Str
    nsteps = Int
    fixed_step_low = Str
    fixed_step_high = Str

    plateau_nsteps = Int(3)
    plateau_gas_fraction = Float(50)
    plateau_mswd = Float
    plateau_mswd_valid = Bool

    # def _get_nanalyses(self):
    #     if self.plateau_steps:
    #         n = self.nsteps
    #     else:
    #         n = super(StepHeatAnalysisGroup, self)._get_nanalyses()
    #     return n
    total_ar39 = AGProperty()

    @property
    def labnumber(self):
        return self.identifier

    @cached_property
    def _get_total_ar39(self):
        total = sum([a.get_computed_value('k39') for a in self.analyses])
        return nominal_value(total)

    def plateau_total_ar39(self):
        cleantotal = sum([a.get_computed_value('k39') for a in self.analyses if self.get_is_plateau_step(a)])
        return nominal_value(cleantotal / self.total_ar39 * 100)

    def valid_total_ar39(self):
        cleantotal = sum([a.get_computed_value('k39') for a in self.clean_analyses()])
        return nominal_value(cleantotal / self.total_ar39 * 100)

    def cumulative_ar39(self, idx):
        # ai = self.analyses[idx]
        # # if ai.is_omitted():
        #     return ''

        cum = 0
        for i, a in enumerate(self.analyses):
            # if a.is_omitted():
            #     continue
            if i > idx:
                break
            cum += a.get_computed_value('k39')

        return nominal_value(cum / self.total_ar39 * 100)

    def get_plateau_mswd_tuple(self):
        return self.plateau_mswd, self.plateau_mswd_valid, self.nsteps

    def calculate_plateau(self):
        return self.plateau_age

    def get_is_plateau_step(self, an):
        if isinstance(an, int):
            idx = an
            an = self.analyses[idx]
        else:
            idx = self.analyses.index(an)

        plateau_step = False
        if self.plateau_age:
            if not an.is_omitted():
                ps, pe = self.plateau_steps
                plateau_step = ps <= idx <= pe

        return plateau_step

    @cached_property
    def _get_integrated_age(self):
        ret = ufloat(0, 0)
        ans = list(self.clean_analyses())
        if ans and all((not isinstance(a, InterpretedAgeGroup) for a in ans)):

            rad40 = sum([a.get_computed_value('rad40') for a in ans])
            k39 = sum([a.get_computed_value('k39') for a in ans])

            a = ans[0]
            j = a.j
            try:
                ret = age_equation(rad40 / k39, j, a.arar_constants)  # / self.age_scalar
            except ZeroDivisionError:
                pass

        return ret

    # def _get_steps(self):
    #     d = [(ai.age,
    #           ai.age_err,
    #           nominal_value(ai.get_computed_value('k39')))
    #          for ai in self.clean_analyses()]
    #
    #     return zip(*d)

    @property
    def fixed_steps(self):
        l, h = '', ''
        if self.fixed_step_low:
            l = self.fixed_step_low

        if self.fixed_step_high:
            h = self.fixed_step_high

        if not (l is None and h is None):
            return l, h

    @cached_property
    def _get_plateau_age(self):
        # ages, errors, k39 = self._get_steps()
        ans = self.analyses
        v, e = 0, 0
        if all((not isinstance(ai, InterpretedAgeGroup) for ai in ans)):
            if ans:
                ages = [ai.age for ai in ans]
                errors = [ai.age_err for ai in ans]

                k39 = [nominal_value(ai.get_computed_value('k39')) for ai in ans]

                options = {'nsteps': self.plateau_nsteps,
                           'gas_fraction': self.plateau_gas_fraction,
                           'fixed_steps': self.fixed_steps}

                excludes = [i for i, ai in enumerate(ans) if ai.is_omitted()]
                args = calculate_plateau_age(ages, errors, k39, options=options, excludes=excludes)

                if args:
                    v, e, pidx = args
                    if pidx[0] == pidx[1]:
                        return
                    self.plateau_steps = pidx
                    self.plateau_steps_str = '{}-{}'.format(ALPHAS[pidx[0]],
                                                            ALPHAS[pidx[1]])

                    step_idxs = [i for i in range(pidx[0], pidx[1] + 1) if not ans[i].is_omitted()]
                    self.nsteps = len(step_idxs)

                    pages = [ages[i] for i in step_idxs]
                    perrs = [errors[i] for i in step_idxs]

                    mswd = calculate_mswd(pages, perrs)
                    self.plateau_mswd_valid = validate_mswd(mswd, self.nsteps)
                    self.plateau_mswd = mswd

                    e = self._modify_error(v, e,
                                           self.plateau_age_error_kind,
                                           mswd=mswd,
                                           include_j_error=self.include_j_error_in_plateau)
                    if math.isnan(e):
                        e = 0

        return ufloat(v, max(0, e))  # / self.age_scalar


class InterpretedAgeGroup(StepHeatAnalysisGroup):
    uuid = Str
    all_analyses = List
    preferred_age = Property(depends_on='preferred_age_kind, preferred_age_error_kind')
    preferred_mswd = Property(depends_on='preferred_age_kind')
    preferred_kca = Property(depends_on='preferred_kca_kind')
    preferred_kcl = Property(depends_on='preferred_kcl_kind')
    preferred_rad40_percent = Property(depends_on='preferred_rad40_percent_kind')
    preferred_moles_k39 = Property(depends_on='preferred_moles_k39_kind')

    preferred_age_kind = Enum(*AGE_SUBGROUPINGS)
    preferred_kca_kind = Enum(*SUBGROUPINGS)
    preferred_kcl_kind = Enum(*SUBGROUPINGS)
    preferred_rad40_percent_kind = Enum(*SUBGROUPINGS)
    preferred_moles_k39_kind = Enum(*SUBGROUPINGS)

    preferred_age_error_kind = Str(MSEM)
    preferred_kca_error_kind = Str(MSEM)
    preferred_kcl_error_kind = Str(MSEM)
    preferred_rad40_percent_error_kind = Str(MSEM)
    preferred_moles_k39_error_kind = Str(MSEM)

    preferred_age_value = Property(depends_on='preferred_age_kind')
    preferred_kca_value = Property(depends_on='preferred_kca_kind')
    preferred_kcl_value = Property(depends_on='preferred_kcl_kind')
    preferred_rad40_percent_value = Property(depends_on='preferred_rad40_percent_kind')
    preferred_moles_k39_value = Property(depends_on='preferred_moles_k39_kind')

    preferred_age_error = Property(depends_on='preferred_age_kind, preferred_age_error_kind')
    preferred_kca_error = Property(depends_on='preferred_kca_kind, preferred_kca_error_kind')
    preferred_kcl_error = Property(depends_on='preferred_kcl_kind, preferred_kcl_error_kind')
    preferred_rad40_percent_error = Property(depends_on='preferred_rad40_percent_kind, '
                                                        'preferred_rad40_percent_error_kind')
    preferred_moles_k39_error = Property(depends_on='preferred_moles_k39_kind, preferred_moles_k39_error_kind')

    preferred_ages = ('Weighted Mean', 'Arithmetic Mean', 'Isochron', 'Integrated', 'Plateau')

    name = Str
    use = Bool

    lithology_class = Str
    lithology_classes = List

    lithology_group = Str
    lithology_groups = List

    lithology_type = Str
    lithology_types = List

    lithology = Str
    lithologies = List

    reference = Str
    lat_long = Str
    rlocation = Str

    comments = Str

    def set_preferred_defaults(self, default_kind='Weighted Mean', default_error_kind=MSEM):
        for attr in SUBGROUPING_ATTRS:
            setattr(self, 'preferred_{}_kind'.format(attr), default_kind)
            setattr(self, 'preferred_{}_error_kind'.format(attr), default_error_kind)

    def is_omitted(self, tags=None):
        return False

    def get_age(self, okind, set_preferred=False):

        kind = okind.lower().replace(' ', '_')
        if kind == 'weighted_mean':
            a = self.weighted_age
            label = 'wt. mean'
        elif kind == 'plateau':
            a = self.plateau_age
            label = 'plateau'
        elif kind == 'isochron':
            a = self.isochron_age
            label = 'isochron'
        elif kind == 'integrated':
            a = self.integrated_age
            label = 'integrated'
        elif kind == 'plateau_else_weighted_mean':
            label = 'plateau'
            a = self.plateau_age
            if not self.plateau_steps:
                label = 'wt. mean'
                a = self.weighted_age
        else:
            label = 'wt. mean'

        if set_preferred:
            self.preferred_age_kind = okind

        return a, label

    def ages(self, asfloat=True):
        vs = {k: getattr(self, k) for k in ('weighted_age', 'plateau_age', 'isochron_age', 'integrated_age')}
        if asfloat:
            es = {}
            for k, v in vs.items():
                vs[k] = nominal_value(v)
                es['{}_err'.format(k)] = std_dev(v)

            vs.update(es)
        return vs

    @property
    def age(self):
        return self.preferred_age

    @property
    def uage(self):
        return self.preferred_age

    @property
    def kca(self):
        return self.preferred_kca

    @property
    def kcl(self):
        return self.preferred_kcl

    @property
    def rad40_percent(self):
        return self.preferred_rad40_percent

    @property
    def k39(self):
        return self.preferred_moles_k39

    def _value_string(self, t):
        try:
            v = getattr(self, t)
            a, e = nominal_value(v), std_dev(v)
        except AttributeError:
            a, e = '---', '---'

        return a, e

    def get_value(self, attr):
        if hasattr(self, attr):
            ret = getattr(self, attr)
        else:
            ret = ufloat(0, 0)
        return ret

    def _name_default(self):
        name = ''
        if self.analyses:
            name = make_aliquot(self.analyses[0].aliquot)
        return name

    def _get_nanalyses(self):
        if self.preferred_age_kind.lower() == 'plateau':
            return self.nsteps
        else:
            return super(InterpretedAgeGroup, self)._get_nanalyses()

    def _preferred_age_error_kind_changed(self, new):
        self.weighted_age_error_kind = new
        self.arith_age_error_kind = new
        self.plateau_age_error_kind = new
        self.isochron_age_error_kind = new
        self.dirty = True

    def get_ma_scaled_age(self):
        a = self.preferred_age
        return a / self.age_scalar

    def _get_preferred_mswd(self):
        if self.preferred_age_kind.lower() == 'plateau':
            return self.plateau_mswd
        else:
            return self.mswd

    def _get_preferred_age_value(self):
        return self._get_preferred_value('age')

    def _get_preferred_age_error(self):
        return self._get_preferred_error('age')

    def _get_preferred_kca_value(self):
        return self._get_preferred_value('kca')

    def _get_preferred_kca_error(self):
        return self._get_preferred_error('kca')

    def _get_preferred_kcl_value(self):
        return self._get_preferred_value('kcl')

    def _get_preferred_kcl_error(self):
        return self._get_preferred_error('kcl')

    def _get_preferred_rad40_percent_value(self):
        return self._get_preferred_value('rad40_percent')

    def _get_preferred_rad40_percent_error(self):
        return self._get_preferred_error('rad40_percent')

    def _get_preferred_moles_k39_value(self):
        return self._get_preferred_value('moles_k39')

    def _get_preferred_moles_k39_error(self):
        return self._get_preferred_error('moles_k39')

    def _get_preferred_value(self, tag):
        pa = getattr(self, 'preferred_{}'.format(tag))
        v = 0
        if pa is not None:
            v = float(nominal_value(pa))
        return v

    def _get_preferred_error(self, tag):
        pa = getattr(self, 'preferred_{}'.format(tag))
        if pa is not None:
            e = float(std_dev(pa))

        return e

    # get preferred objects
    def _get_preferred_age(self):
        pa = ufloat(0, 0)
        pak = self._convert_preferred_kind('age')
        if pak in ('weighted_mean', 'wt._mean'):
            pa = self.weighted_age
        elif pak == 'arithmetic_mean':
            pa = self.arith_age
        elif pak == 'isochron':
            pa = self.isochron_age
        elif pak == 'integrated':
            pa = self.integrated_age
        elif pak == 'plateau':
            pa = self.plateau_age
        elif pak == 'plateau_else_weighted_mean':
            pa = self.plateau_age
            if not self.plateau_steps:
                pa = self.weighted_age

        return pa

    def _get_preferred_kca(self):
        return self._get_preferred_('kca')

    def _get_preferred_kcl(self):
        return self._get_preferred_('kcl')

    def _get_preferred_rad40_percent(self):
        return self._get_preferred_('rad40_percent')

    def _get_preferred_moles_k39(self):
        return self._get_preferred_('moles_k39')

    def _get_preferred_(self, attr):
        pk = self._convert_preferred_kind(attr)
        if pk == 'weighted_mean':
            pa = getattr(self, 'weighted_{}'.format(attr))
        elif pk == 'integrated':
            pa = getattr(self, 'integrated_{}'.format(attr))
        else:
            pa = getattr(self, 'arith_{}'.format(attr))

        return pa

    def _convert_preferred_kind(self, attr):
        return getattr(self, 'preferred_{}_kind'.format(attr)).lower().replace(' ', '_')

    # @cached_property
    # def _get_preferred_ages(self):
    #     ps = ['Weighted Mean', 'Arithmetic Mean', 'Isochron',
    #           'Integrated', 'Plateau']
    #     # if self.analyses:
    #     #     ref = self.analyses[0]
    #     #     print 'asfasfasdfasfas', ref, ref.step
    #     #     if ref.step:
    #     #         ps.append('Integrated')
    #     #         if self.plateau_age:
    #     #             ps.append('Plateau')
    #
    #     return ps

# ============= EOF =============================================

# class AnalysisRatioMean(AnalysisGroup):
#    Ar40_39 = Property
#    Ar37_39 = Property
#    Ar36_39 = Property
#    kca = Property
#    kcl = Property
#
#    def _get_Ar40_39(self):
#        return self._calculate_weighted_mean('Ar40_39')
#
#    #        return self._calculate_weighted_mean('rad40') / self._calculate_weighted_mean('k39')
#
#    def _get_Ar37_39(self):
#        return self._calculate_weighted_mean('Ar37_39')
#
#    #        return self._calculate_weighted_mean('Ar37') / self._calculate_weighted_mean('Ar39')
#
#    def _get_Ar36_39(self):
#        return self._calculate_weighted_mean('Ar36_39')
#
#    #        return self._calculate_weighted_mean('Ar36') / self._calculate_weighted_mean('Ar39')
#
#    def _get_kca(self):
#        return self._calculate_weighted_mean('kca')
#
#    def _get_kcl(self):
#        return self._calculate_weighted_mean('kcl')
#
# class AnalysisIntensityMean(AnalysisGroup):
#    Ar40 = Property
#    Ar39 = Property
#    Ar38 = Property
#    Ar37 = Property
#    Ar36 = Property
#
#    def _get_Ar40(self):
#        return self._calculate_weighted_mean('Ar40')
#
#    def _get_Ar39(self):
#        return self._calculate_weighted_mean('Ar39')
#
#    def _get_Ar38(self):
#        return self._calculate_weighted_mean('Ar38')
#
#    def _get_Ar37(self):
#        return self._calculate_weighted_mean('Ar37')
#
#    def _get_Ar36(self):
#        return self._calculate_weighted_mean('Ar36')
