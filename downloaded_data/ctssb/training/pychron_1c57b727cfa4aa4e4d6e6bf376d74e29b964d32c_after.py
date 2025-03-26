#===============================================================================
# Copyright 2013 Jake Ross
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
#===============================================================================

#============= enthought library imports =======================
from traits.api import Any, List, CInt, Int, Bool, Enum
# from traitsui.api import View, Item
# from pyface.timer.do_later import do_after
#============= standard library imports ========================
import time
from threading import Event, Timer
from numpy import Inf
#============= local library imports  ==========================
from pychron.loggable import Loggable
# from pychron.ui.gui import invoke_in_main_thread
from pychron.globals import globalv
from pychron.consumer_mixin import consumable
# from pychron.codetools.memory_usage import mem_log
from pychron.ui.gui import invoke_in_main_thread


class DataCollector(Loggable):
    measurement_script = Any
    plot_panel = Any
    arar_age = Any

    detectors = List
    check_conditions = Bool(True)
    truncation_conditions = List
    terminations_conditions = List
    action_conditions = List
    ncounts = CInt
    #grpname = Str

    is_baseline = Bool(False)
    for_peak_hop = Bool(False)
    fits = List
    series_idx = Int
    #total_counts = CInt

    canceled = False

    _truncate_signal = False
    starttime = None
    _alive = False
    _evt = None
    _warned_no_fit = None

    collection_kind = Enum(('sniff', 'signal', 'baseline'))

    def _detectors_changed(self):
        self._idx_func = self._get_idx_func()

    def wait(self):
        st = time.time()
        self.debug('wait started')
        while 1:
            if self._evt and self._evt.set():
                break
        self.debug('wait complete {:0.1f}s'.format(time.time() - st))

    def set_truncated(self):
        self._truncate_signal = True

    def stop(self):
        self._alive = False
        if self._evt:
            self._evt.set()

    def measure(self):
        if self.canceled:
            return

        self._truncate_signal = False
        self._warned_no_fit = []

        st = time.time()
        if self.starttime is None:
            self.starttime = st

        et = self.ncounts * self.period_ms * 0.001
        evt = self._evt
        if evt:
            evt.set()
            evt.wait(0.05)
        else:
            evt = Event()

        self._evt = evt
        evt.clear()

        #wait for graphs to be fully constructed in the MainThread
        evt.wait(0.05)

        self._alive = True

        self._measure(evt)

        tt = time.time() - st
        self.debug('estimated time: {:0.3f} actual time: :{:0.3f}'.format(et, tt))

    def _measure(self, evt):
        self.debug('starting measurment')
        with consumable(func=self._iter_step) as con:
            self._iter(con, evt, 1)
            while not evt.is_set():
                time.sleep(0.25)

        self.debug('measurement finished')

    def _iter(self, con, evt, i, prev=0):
        if not self._check_iteration(evt, i):
            if not self._iter_hook(con, i):
                evt.set()
                return

            ot = time.time()

            p = self.period_ms * 0.001
            p -= prev
            p = max(0, p)

            #self.debug('period {} {} {}'.format(p,prev, self.period_ms))
            t = Timer(p, self._iter, args=(con, evt, i + 1,
                                           time.time() - ot))

            t.name = 'iter_{}'.format(i + 1)
            t.start()

        else:
            #self.debug('no more iter')
            evt.set()

    def _iter_hook(self, con, i):
        return True

    def _iter_step(self, data):
        pass

    def _get_data(self, dets=None):
        data = self.data_generator.next()
        if dets:
            data = zip(*[(k, s) for k, s in zip(*data)
                         if k in dets])

        return data

    def _save_data(self, x, keys, signals):
        self.data_writer(self.detectors, x, keys, signals)

        #update arar_age
        if self.is_baseline and self.for_peak_hop:
            self._update_baseline_peak_hop(x, keys, signals)
        else:
            self._update_isotopes(x, keys, signals)

    def _update_baseline_peak_hop(self, x, keys, signals):
        a = self.arar_age
        for iso in self.arar_age.isotopes.itervalues():
            signal = signals[keys.index(iso.detector)]
            a.append_data(iso.name, x, signal, 'baseline')

    def _update_isotopes(self, x, keys, signals):
        a = self.arar_age

        kind = self.collection_kind
        for dn in keys:
            dn = self._get_detector(dn)
            if dn:
                iso = dn.isotope
                signal = signals[keys.index(dn.name)]
                a.append_data(iso, x, signal, kind)

    def _get_detector(self, d):
        if isinstance(d, str):
            d = next((di for di in self.detectors
                      if di.name == d), None)
        return d

    def plot_data(self, *args, **kw):
        invoke_in_main_thread(self._plot_data, *args, **kw)

    def _plot_baseline_for_peak_hop(self, i, x, keys, signals):
        idx_func = self._idx_func
        nfs = self.get_fit_block(i)
        for iso in self.arar_age.isotopes.itervalues():
            pi = idx_func(iso.name, iso.detector)
            signal = signals[keys.index(iso.detector)]
            self._set_plot_data(pi, iso.name, nfs, x, signal)

    def _plot_data_(self, i, x, keys, signals):
        nfs = self.get_fit_block(i)
        idx_func = self._idx_func
        for dn in keys:
            dn = self._get_detector(dn)
            if dn:
                iso = dn.isotope
                pi = idx_func(iso, dn.name)
                signal = signals[keys.index(dn.name)]
                self._set_plot_data(pi, iso, nfs, x, signal)

    def _set_plot_data(self, pi, iso, nfs, x, signal):
        graph = self.plot_panel.isotope_graph
        np = len(graph.plots)
        # print iso, dn.name, pi
        try:
            fi = nfs[pi]
        except IndexError:
            if not iso in self._warned_no_fit:
                self.warning('No fit defined for {}, idx={}'.format(iso, pi))
                self._warned_no_fit.append(iso)
            return

        if pi >= np:
            graph.new_plot()
            graph.new_series(type='scatter',
                             marker='circle',
                             plotid=pi)

        #print i, x, pi, dn
        graph.add_datum((x, signal),
                        series=self.series_idx,
                        plotid=pi,
                        update_y_limits=True,
                        ypadding='0.1')

        miso = self.arar_age.isotopes[iso]
        if self.is_baseline:
            miso.baseline.fit = fi
        else:
            miso.fit = fi

        if fi:
            graph.set_fit(fi, plotid=pi, series=0)

    def _plot_data(self, i, x, keys, signals):
        if globalv.experiment_debug:
            x *= (self.period_ms * 0.001) ** -1

        if self.is_baseline and self.for_peak_hop:
            self._plot_baseline_for_peak_hop(i, x, keys, signals)
        else:
            self._plot_data_(i, x, keys, signals)

        graph = self.plot_panel.isotope_graph
        graph.refresh()

    #===============================================================================
    #
    #===============================================================================
    def get_fit_block(self, iter_cnt, fits=None):
        if fits is None:
            fits = self.fits
        return self._get_fit_block(iter_cnt, fits)

    def _get_fit_block(self, iter_cnt, fits):
        midx = None
        me = -Inf
        for i, (sli, fs) in enumerate(fits):
            if sli:
                s, e = sli
                if s is None:
                    s = 0
                if e is None:
                    e = Inf

                if iter_cnt < 0:
                    if me < e:
                        me = e
                        midx = i
                else:
                    if iter_cnt > s and iter_cnt < e:
                        break

        if midx is not None:
            fs = fits[midx]

        #        self.debug('fs {}'.format(fs))
        return fs

    #===============================================================================
    # checks
    #===============================================================================
    def _check_conditions(self, conditions, cnt):
        for ti in conditions:
            if ti.check(self.arar_age, cnt):
                return ti

    def _check_iteration(self, evt, i):
        if evt and evt.isSet():
            return True

        j = i - 1
        user_counts = 0 if self.plot_panel is None else self.plot_panel.ncounts
        script_counts = 0 if self.measurement_script is None else self.measurement_script.ncounts
        original_counts = self.ncounts
        count_args = (j, original_counts)

        if not self._alive:
            self.info('measurement iteration executed {}/{} counts'.format(*count_args))
            return 'cancel'

        if user_counts != original_counts:
            if i > user_counts:
                self.info('user termination. measurement iteration executed {}/{} counts'.format(*count_args))
                self.plot_panel.total_counts -= (original_counts - i)
                return 'break'
        elif script_counts != original_counts:
            if i > script_counts:
                self.info('script termination. measurement iteration executed {}/{} counts'.format(*count_args))
                return 'break'
        elif i > original_counts:
            return 'break'

        if self._truncate_signal:
            self.info('measurement iteration executed {}/{} counts'.format(*count_args))
            self._truncate_signal = False

            return 'break'

        if self.check_conditions:
            termination_condition = self._check_conditions(self.termination_conditions, i)
            if termination_condition:
                self.info('termination condition {}. measurement iteration executed {}/{} counts'.format(
                    termination_condition.message, j, original_counts),
                          color='red')
                return 'cancel'

            truncation_condition = self._check_conditions(self.truncation_conditions, i)
            if truncation_condition:
                self.info('truncation condition {}. measurement iteration executed {}/{} counts'.format(
                    truncation_condition.message, j, original_counts),
                          color='red')
                self.state = 'truncated'
                self.measurement_script.abbreviated_count_ratio = truncation_condition.abbreviated_count_ratio

                #                self.condition_truncated = True
                return 'break'

            action_condition = self._check_conditions(self.action_conditions, i)
            if action_condition:
                self.info(
                    'action condition {}. measurement iteration executed {}/{} counts'.format(action_condition.message,
                                                                                              j, original_counts),
                    color='red')
                action_condition.perform(self.measurement_script)
                if not action_condition.resume:
                    return 'break'

    def _get_idx_func(self):
        original_idx = [(di.name, di.isotope) for di in self.detectors]
        # print original_idx
        def idx_func(isot, detname):
            idx = next((i for i, (n, ii) in enumerate(original_idx)
                        if ii == isot), None)

            if idx is None:
                idx = next((i for i, (n, ii) in enumerate(original_idx)
                            if n == detname), None)
            return idx

        return idx_func

        #============= EOF =============================================
