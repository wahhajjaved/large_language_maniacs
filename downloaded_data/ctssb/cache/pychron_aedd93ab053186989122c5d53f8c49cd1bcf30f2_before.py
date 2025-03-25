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
import os
import random
import time

from numpy import array, argmin
from traits.api import Instance, Int, Property, List, \
    Any, Enum, Str, DelegatesTo, Bool, TraitError, cached_property

from pychron.core.helpers.filetools import list_directory2
from pychron.core.progress import open_progress
from pychron.core.ramper import StepRamper
from pychron.globals import globalv
from pychron.paths import paths
from pychron.pychron_constants import QTEGRA_INTEGRATION_TIMES, \
    DEFAULT_INTEGRATION_TIME, NULL_STR
from pychron.spectrometer import get_spectrometer_config_path, \
    get_spectrometer_config_name, set_spectrometer_config_name
from pychron.spectrometer.base_detector import BaseDetector
from pychron.spectrometer.thermo.detector.base import ThermoDetector
from pychron.spectrometer.thermo.magnet.base import ThermoMagnet
from pychron.spectrometer.thermo.source.base import ThermoSource
from pychron.spectrometer.thermo.spectrometer_device import SpectrometerDevice


def normalize_integration_time(it):
    """
        find the integration time closest to "it"
    """
    x = array(QTEGRA_INTEGRATION_TIMES)
    return x[argmin(abs(x - it))]


def calculate_radius(m_e, hv, mfield):
    """
        m_e= mass/charge
        hv= accelerating voltage (V)
        mfield= magnet field (H)
    """
    r = ((2 * m_e * hv) / mfield ** 2) ** 0.5

    return r


class ThermoSpectrometer(SpectrometerDevice):
    magnet = Instance(ThermoMagnet)
    source = Instance(ThermoSource)
    magnet_klass = Any
    source_klass = Any
    detector_klass = Any

    detectors = List(ThermoDetector)

    microcontroller = Any
    integration_time = Enum(QTEGRA_INTEGRATION_TIMES)

    reference_detector = Str('H1')

    magnet_dac = DelegatesTo('magnet', prefix='dac')

    magnet_dacmin = DelegatesTo('magnet', prefix='dacmin')
    magnet_dacmax = DelegatesTo('magnet', prefix='dacmin')

    current_hv = DelegatesTo('source')

    molecular_weight = Str('Ar40')
    molecular_weights = None
    isotopes = Property

    spectrometer_configuration = Str
    spectrometer_configurations = List

    sub_cup_configurations = List
    sub_cup_configuration = Property(depends_on='_sub_cup_configuration')
    _sub_cup_configuration = Str

    dc_start = Int(0)
    dc_stop = Int(500)
    dc_step = Int(50)
    dc_stepmin = Int(1)
    dc_stepmax = Int(1000)
    dc_threshold = Int(3)
    dc_npeak_centers = Int(3)

    send_config_on_startup = Bool
    use_deflection_correction = Bool(True)
    max_deflection = Int(500)

    _connection_status = False
    _config = None
    _debug_values = None
    _saved_integration = None

    def reload_mftable(self):
        self.magnet.reload_mftable()

    def get_detector_active(self, dname):
        """
        return True if dname in the list of intensity keys
        e.g.

        keys, signals = get_intensities
        return dname in keys

        :param dname:
        :return:
        """
        keys, prev = self.get_intensities()
        return dname in keys

    def test_intensity(self):
        """
        test if intensity is changing. make 2 measurements if exactlly the same for all
        detectors make third measurement if same as 1,2 make fourth measurement if same
        all four measurements same then test fails
        :return:
        """
        ret, err = True, ''
        keys, one = self.get_intensities()
        it = 0.1 if self.simulation else self.integration_time

        time.sleep(it)
        keys, two = self.get_intensities()

        if all(one == two):
            time.sleep(it)
            keys, three = self.get_intensities()
            if all(two == three):
                time.sleep(it)
                keys, four = self.get_intensities()
                if all(three == four):
                    ret = False
        return ret, err

    def test_connection(self, force=True):
        """
            if not in simulation mode send a GetIntegrationTime to the spectrometer
            if in simulation mode and the globalv.communication_simulation is disabled
            then return False

        :return: bool
        """
        self.info('testing connnection')
        ret, err = False, ''
        if not self.simulation:
            if force:
                ret = self.ask('GetIntegrationTime', verbose=True) is not None
            else:
                ret = self._connection_status
        elif globalv.communication_simulation:
            ret = True

        self._connection_status = ret
        self.microcontroller.set_simulation(not ret)
        return ret, err

    def set_gains(self, history=None):
        """

        :param history:
        :return: list
        """
        if history:
            self.debug(
                'setting gains to {}, user={}'.format(history.create_date,
                                                      history.username))
        for di in self.detectors:
            di.set_gain()

        return {di.name: di.gain for di in self.detectors}

    def load_current_detector_gains(self):
        """
        load the detector gains from the spectrometer
        """
        for di in self.detectors:
            di.get_gain()

    def get_integration_time(self, current=True):
        """
        return current or cached integration time, i.e time between intensity measurements

        :param current: bool, if True retrieve value from qtegra
        :return: float
        """
        if current:
            resp = self.ask('GetIntegrationTime')
            if resp:
                try:
                    self.integration_time = float(resp)
                    self.info(
                        'Integration Time {}'.format(self.integration_time))

                except (TypeError, ValueError, TraitError):
                    self.warning(
                        'Invalid integration time. resp={}'.format(resp))
                    self.integration_time = DEFAULT_INTEGRATION_TIME

        return self.integration_time

    def save_integration(self):
        self._saved_integration = self.integration_time

    def restore_integration(self):
        if self._saved_integration:
            self.set_integration_time(self._saved_integration)
            self._saved_integration = None

    def set_integration_time(self, it, force=False):
        """

        :param it: float, integration time
        :param force: set integration even if "it" is not different than self.integration_time
        :return: float, integration time
        """
        it = normalize_integration_time(it)
        if self.integration_time != it or force:
            self.debug('setting integration time = {}'.format(it))
            name = 'SetIntegrationTime'
            self.set_parameter(name, it)
            self.trait_setq(integration_time=it)

        return it

    def send_configuration(self, **kw):
        """
            send the configuration values to the device
        """
        self._send_configuration(**kw)

    def set_parameter(self, name, v):
        cmd = '{} {}'.format(name, v)
        self.ask(cmd)

    def get_parameter(self, cmd):
        return self.ask(cmd)

    def set_microcontroller(self, m):
        self.debug('set microcontroller {}'.format(m))
        self.magnet.microcontroller = m
        self.source.microcontroller = m
        self.microcontroller = m
        for d in self.detectors:
            d.microcontroller = m
            d.load()

    def set_deflection(self, name, value):
        det = self.get_detector(name)
        if det:
            det.deflection = value
        else:
            self.warning('Could not find detector "{}". Deflection Not Possible'.format(name))

    def get_deflection(self, name, current=False):
        """
        get deflection by detector name

        :param name: str, detector name
        :param current: bool, if True query qtegra
        :return: float
        """
        deflection = 0
        det = self.get_detector(name)
        if det:
            if current:
                det.read_deflection()
            deflection = det.deflection
        else:
            self.warning('Failed getting deflection for detector ="{}"'.format(name))

        return deflection

    def get_detector(self, name):
        """
        get Detector object by name

        :param name: str
        :return: Detector
        """

        if isinstance(name, BaseDetector):
            return name
        else:
            if name.endswith('_'):
                name = '{})'.format(name[:-1])
                name = name.replace('_', '(')

            return next((det for det in self.detectors if det.name == name), None)

    def map_isotope(self, mass):
        """
        map a mass to an isotope
        @param mass:
        @return:
        """
        molweights = self.molecular_weights
        # for k, v in molweights.iteritems():
        #     print '\t',k,v,mass, v-mass
        #     if abs(v-mass) < 0.05:
        #         print 'found'
        #         break
        print molweights, mass

        return next((k for k, v in molweights.iteritems() if abs(v - mass) < 0.15), 'Iso{:0.4f}'.format(mass))

    def map_mass(self, isotope):
        """
        map an isotope to a mass
        @param isotope:
        @return:
        """
        try:
            return self.molecular_weights[isotope]
        except KeyError:
            self.warning('Invalid isotope. Cannot map to a mass. {} not in molecular_weights'.format(isotope))

    def update_isotopes(self, isotope, detector):
        """
        update the isotope name for each detector

        called by AutomatedRun._define_detectors

        :param isotope: str
        :param detector: str or Detector
        :return:
        """
        if isotope != NULL_STR:
            det = self.get_detector(detector)
            if not det:
                self.debug('cannot update detector "{}"'.format(detector))
            else:
                det.isotope = isotope

                index = det.index
                try:
                    # nmass = int(isotope[2:])
                    nmass = self.map_mass(isotope)
                    for di in self.detectors:

                        mass = nmass + (di.index - index)

                        isotope = self.map_isotope(mass)
                        self.debug('setting detector {} to {} ({})'.format(di.name, isotope, mass))
                        di.isotope = isotope

                except BaseException, e:
                    self.warning('Cannot update isotopes. isotope={}, detector={}. error:{}'.format(isotope, detector, e))

    def get_deflection_word(self, keys):
        if self.simulation:
            x = [random.random() for i in keys]
        else:
            x = self.ask('GetDeflections {}'.format(','.join(keys)),
                         verbose=False)
            x = self._parse_word(x)
        return x

    def get_parameter_word(self, keys):
        if self.simulation:
            if self._debug_values:
                x = self._debug_values
            else:
                x = [random.random() for i in keys]
        else:
            x = self.ask('GetParameters {}'.format(','.join(keys)),
                         verbose=False)
            x = self._parse_word(x)

        return x

    def get_configuration_value(self, key):

        for d in self._get_cached_config():
            try:
                return d[key]
            except KeyError:
                try:
                    return d[key.lower()]
                except KeyError:
                    pass
        else:
            return 0

    def set_debug_configuration_values(self):
        if self.simulation:
            d, _, _ = self._get_cached_config()
            keys = ('ElectronEnergy', 'YSymmetry', 'ZSymmetry', 'ZFocus', 'IonRepeller', 'ExtractionLens')
            ds = [0] + [d[k.lower()] for k in keys]
            self._debug_values = ds

    # ===============================================================================
    # load
    # ===============================================================================
    def load_configurations(self):
        """
        load configurations from Qtegra
        :return:
        """
        # self.sub_cup_configurations = ['A', 'B', 'C']
        # self._sub_cup_configuration = 'B'
        #
        # scc = self.ask('GetSubCupConfigurationList Argon', verbose=False)
        # if scc:
        #     if 'ERROR' not in scc:
        #         self.sub_cup_configurations = scc.split('\r')
        #
        # n = self.ask('GetActiveSubCupConfiguration')
        # if n:
        #     if 'ERROR' not in n:
        #         self._sub_cup_configuration = n

        self.molecular_weight = 'Ar40'

    def load(self):
        """
        load detectors
        load setupfiles/spectrometer/config.cfg file
        load magnet
        load deflections coefficients

        :return:
        """
        self.load_detectors()

        # load local configurations
        self.spectrometer_configurations = list_directory2(paths.spectrometer_config_dir, remove_extension=True,
                                                           extension='.cfg')

        name = get_spectrometer_config_name()
        sc, _ = os.path.splitext(name)
        self.spectrometer_configuration = sc

        p = get_spectrometer_config_path(name)
        config = self.get_configuration_writer(p)
        pd = 'Protection'

        if config.has_section(pd):

            self.magnet.use_beam_blank = self.config_get(config, pd, 'use_beam_blank',
                                                         cast='boolean',
                                                         default=False)
            self.magnet.use_detector_protection = self.config_get(config, pd, 'use_detector_protection',
                                                                  cast='boolean',
                                                                  default=False)
            self.magnet.beam_blank_threshold = self.config_get(config, pd, 'beam_blank_threshold',
                                                               cast='float',
                                                               default=0.1)

            # self.magnet.detector_protection_threshold = self.config_get(config, pd,
            # 'detector_protection_threshold',
            # cast='float', default=0.1)
            ds = self.config_get(config, pd, 'detectors')
            if ds:
                ds = ds.split(',')
                self.magnet.protected_detectors = ds
                for di in ds:
                    self.info('Making protection available for detector "{}"'.format(di))

        if config.has_section('Deflections'):
            if config.has_option('Deflections', 'max'):
                v = config.getint('Deflections', 'max')
                if v:
                    self.max_deflection = v

        self.magnet.load()

        self.debug('Detectors {}'.format(self.detectors))
        for d in self.detectors:
            d.load_deflection_coefficients()

    def finish_loading(self):
        """
        finish loading magnet
        send configuration if self.send_config_on_startup set in Preferences
        :return:
        """
        if self.microcontroller:
            self.name = self.microcontroller.name

        self.magnet.finish_loading()

        self.test_connection()
        # if self.send_config_on_startup:
        # write configuration to spectrometer
        # self._send_configuration()

    def start(self):
        self.debug('********** Spectrometer start. send configuration: {}'.format(self.send_config_on_startup))
        if self.send_config_on_startup:
            self.send_configuration(use_ramp=True)

    def load_detectors(self):
        """
        load setupfiles/spectrometer/detectors.cfg
        populates self.detectors
        :return:
        """
        config = self.get_configuration(path=os.path.join(paths.spectrometer_dir, 'detectors.cfg'))

        for i, name in enumerate(config.sections()):
            # relative_position = self.config_get(config, name, 'relative_position', cast='float')

            color = self.config_get(config, name, 'color', default='black')
            default_state = self.config_get(config, name, 'default_state',
                                            default=True, cast='boolean')
            isotope = self.config_get(config, name, 'isotope')
            kind = self.config_get(config, name, 'kind', default='Faraday',
                                   optional=True)
            pt = self.config_get(config, name, 'protection_threshold',
                                 default=None, optional=True, cast='float')

            index = self.config_get(config, name, 'index', cast='float')
            if index is None:
                index = i

            use_deflection = self.config_get(config, name, 'use_deflection', cast='boolean', optional=True)
            if use_deflection is None:
                use_deflection = True

            deflection_correction_sign = 1
            if use_deflection:
                deflection_correction_sign = self.config_get(config, name, 'deflection_correction_sign', cast='int')

            deflection_name = self.config_get(config, name, 'deflection_name', optional=True, default=name)

            self._add_detector(name=name,
                               index=index,
                               use_deflection=use_deflection,
                               protection_threshold=pt,
                               deflection_correction_sign=deflection_correction_sign,
                               deflection_name=deflection_name,
                               color=color,
                               active=default_state,
                               isotope=isotope,
                               kind=kind)

    # ===============================================================================
    # signals
    # ===============================================================================
    def get_intensities(self, tagged=True):
        """
        issue a GetData command to Qtegra.

        keys, list of strings
        signals, list of floats::

            keys = ['H2', 'H1', 'AX', 'L1', 'L2', 'CDD']
            signals = [10,100,1,0.1,1,0.001]

        :param tagged:
        :return: keys, signals
        """
        keys = []
        signals = []
        if self.microcontroller and not self.microcontroller.simulation:
            # if self.microcontroller.simulation and globalv.communication_simulation:
            # keys, signals = self._get_simulation_data()
            # else:
            datastr = self.ask('GetData', verbose=False, quiet=True)
            if datastr:
                if 'ERROR' not in datastr:
                    data = datastr.split(',')
                    if tagged:
                        keys = data[::2]
                        signals = data[1::2]
                    else:
                        keys = ['H2', 'H1', 'AX', 'L1', 'L2', 'CDD']
                        signals = data

                signals = map(float, signals)

        if not keys and globalv.communication_simulation:
            keys, signals = self._get_simulation_data()

        for k, v in zip(keys, signals):
            det = self.get_detector(k)
            det.set_intensity(v)

        return keys, array(signals)

    def get_intensity(self, dkeys):
        """
            dkeys: str or tuple of strs

        """
        data = self.get_intensities()
        if data is not None:

            keys, signals = data

            def func(k):
                return signals[keys.index(k)] if k in keys else 0

            if isinstance(dkeys, (tuple, list)):
                return [func(key) for key in dkeys]
            else:
                return func(dkeys)
                # return signals[keys.index(dkeys)] if dkeys in keys else 0

    def get_hv_correction(self, dac, uncorrect=False, current=False):
        """
        ion optics correction::

            r=M*v_o/(q*B_o)
            r=M*v_c/(q*B_c)

            E=m*v^2/2
            v=(2*E/m)^0.5

            v_o/B_o = v_c/B_c
            B_c = B_o*v_c/v_o

            B_c = B_o*(E_c/E_o)^0.5

            B_o = B_c*(E_o/E_c)^0.5

            E_o = nominal hv
            E_c = current hv
            B_o = nominal dac
            B_c = corrected dac

        """
        source = self.source
        cur = source.current_hv
        if current:
            cur = source.read_hv()

        if cur is None:
            cor = 1
        else:
            try:
                # cor = source.nominal_hv / cur
                if uncorrect:
                    cor = source.nominal_hv / cur
                else:
                    cor = cur / source.nominal_hv

                cor **= 0.5

            except ZeroDivisionError:
                cor = 1

        dac *= cor
        return dac

    def correct_dac(self, det, dac, current=True):
        """
            correct for deflection
            correct for hv
        """
        # correct for deflection
        if self.use_deflection_correction:
            dev = det.get_deflection_correction(current=current)
            dac += dev

        # correct for hv
        # dac *= self.get_hv_correction(current=current)
        dac = self.get_hv_correction(dac, current=current)
        return dac

    def uncorrect_dac(self, det, dac, current=True):
        """
                inverse of correct_dac
        """

        ndac = self.get_hv_correction(dac, uncorrect=True, current=current)
        if self.use_deflection_correction:
            ndac -= det.get_deflection_correction(current=current)
        return ndac

    def clear_cached_config(self):
        self._config = None

    def update_config(self, **kw):
        # p = os.path.join(paths.spectrometer_dir, 'config.cfg')
        p = get_spectrometer_config_path()
        config = self.get_configuration_writer(p)
        for k, v in kw.items():
            if not config.has_section(k):
                config.add_section(k)

            for option, value in v:
                config.set(k, option, value)

        with open(p, 'w') as wfile:
            config.write(wfile)

        self.clear_cached_config()

    # ===============================================================================
    # private
    # ===============================================================================
    def _spectrometer_configuration_changed(self, new):
        if new:
            set_spectrometer_config_name(new)

    def _parse_word(self, word):
        try:
            x = [float(v) for v in word.split(',')]
        except (AttributeError, ValueError):
            x = []
        return x

    def _get_cached_config(self):
        if self._config is None:
            p = get_spectrometer_config_path()
            if not os.path.isfile(p):
                self.warning('Spectrometer configuration file {} not found'.format(p))
                return

            self.debug('caching configuration from {}'.format(p))
            config = self.get_configuration_writer(p)
            d = {}
            defl = {}
            trap = {}
            for section in config.sections():
                if section in ('Default', 'Protection', 'General', 'Trap', 'Magnet'):
                    continue

                for attr in config.options(section):
                    v = config.getfloat(section, attr)
                    if v is not None:
                        if section == 'Deflections':
                            defl[attr.upper()] = v
                        else:
                            d[attr] = v

            section = 'Trap'
            if config.has_section(section):
                for attr in ('current', 'ramp_step', 'ramp_period', 'ramp_tolerance'):
                    if config.has_option(section, attr):
                        trap[attr] = config.getfloat(section, attr)

            section = 'Magnet'
            magnet = {}
            if config.has_section(section):
                for attr in ('mftable',):
                    if config.has_option(section, attr):
                        magnet[attr] = config.get(section, attr)

            if 'hv' in d:
                self.source.nominal_hv = d['hv']

            self._config = (d, defl, trap, magnet)

        return self._config

    def _add_detector(self, **kw):
        d = self.detector_klass(spectrometer=self, **kw)
        self.detectors.append(d)

    def _get_simulation_data(self):
        signals = [1, 100, 3, 0.01, 0.01, 0.01]  # + random(6)
        keys = ['H2', 'H1', 'AX', 'L1', 'L2', 'CDD']
        return keys, signals

    def _send_configuration(self, use_ramp=True):
        self.debug('======== Sending configuration ========')
        command_map = dict(ionrepeller='IonRepeller',
                           electronenergy='ElectronEnergy',
                           ysymmetry='YSymmetry',
                           zsymmetry='ZSymmetry',
                           zfocus='ZFocus',
                           extractionlens='ExtractionLens',
                           ioncountervoltage='IonCounterVoltage',
                           hv='HV')

        if self.microcontroller:
            specparams, defl, trap, magnet = self._get_cached_config()
            for k, v in defl.items():
                cmd = 'SetDeflection'
                v = '{},{}'.format(k, v)
                self.set_parameter(cmd, v)

            for k, v in specparams.items():
                try:
                    cmd = 'Set{}'.format(command_map[k])
                    self.set_parameter(cmd, v)
                except KeyError:
                    self.debug(
                        '$$$$$$$$$$ Not setting {}. Not in command_map'.format(
                            k))

            # set the trap current
            v = trap.get('current')
            self.debug('send trap current {}'.format(v))
            if v is not None:
                step = trap.get('ramp_step', 1)
                period = trap.get('ramp_period', 1)
                tol = trap.get('ramp_tolerance', 10)
                if not self._ramp_trap_current(v, step, period, use_ramp, tol):
                    self.set_parameter('SetParameter',
                                       'Trap Current Set,{}'.format(v))
            # set the mftable
            mftable_name = magnet.get('mftable')
            if mftable_name:
                self.debug('updating mftable name {}'.format(mftable_name))
                self.magnet.mftable.path = mftable_name
                self.magnet.mftable.load_mftable(load_items=True)

            self.debug('======== Configuration Finished ========')
            self.source.sync_parameters()

    def _ramp_trap_current(self, v, step, period, use_ramp=False, tol=10):
        if use_ramp:
            current = self.source.read_trap_current()
            if current is None:
                self.debug('could not read current trap. skipping ramp')
                return

            if v - current >= tol:
                if self.confirmation_dialog('Would you like to ramp up the '
                                            'Trap current from {} to {}'.format(current, v)):
                    prog = open_progress(1)

                    def func(x):
                        cmd = 'SetParameter Trap Current Set,{:0.5f}'.format(x)
                        prog.change_message(cmd)
                        self.ask(cmd)
                        if not prog.accepted and not prog.canceled:
                            return True

                    r = StepRamper()

                    steps = (v - current) / step
                    prog.max = int(steps)
                    r.ramp(func, current, v, step, period)
                    prog.close()
                    return True

    # ===============================================================================
    # defaults
    # ===============================================================================
    def _magnet_default(self):
        return self.magnet_klass(spectrometer=self)

    def _source_default(self):
        return self.source_klass(spectrometer=self)

    def _integration_time_default(self):
        return DEFAULT_INTEGRATION_TIME

    # ===============================================================================
    # property get/set
    # ===============================================================================
    def _get_sub_cup_configuration(self):
        return self._sub_cup_configuration

    def _set_sub_cup_configuration(self, v):
        self._sub_cup_configuration = v
        self.ask('SetSubCupConfiguration {}'.format(v))

    @cached_property
    def _get_isotopes(self):
        return sorted(self.molecular_weights.keys())

    @property
    def detector_names(self):
        return [di.name for di in self.detectors]

# if __name__ == '__main__':
# s = Spectrometer()
# ss = ArgusSource()
# ss.current_hv = 4505
# s.source = ss
# corrected = s.get_hv_correction(100,current=False)
# uncorrected = s.get_hv_correction(corrected, uncorrect=True, current=False)
#
# print corrected, uncorrected

# ============= EOF =============================================
