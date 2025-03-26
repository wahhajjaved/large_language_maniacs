# Authors: Alexandre Gramfort <gramfort@nmr.mgh.harvard.edu>
#          Matti Hamalainen <msh@nmr.mgh.harvard.edu>
#
# License: BSD (3-clause)

import copy
import numpy as np
import fiff
from .fiff import Evoked
from .fiff.pick import pick_types, channel_indices_by_type


class Epochs(object):
    """List of Epochs

    Parameters
    ----------
    raw : Raw object
        A instance of Raw

    events : array, of shape [n_events, 3]
        Returned by the read_events function

    event_id : int
        The id of the event to consider

    tmin : float
        Start time before event

    tmax : float
        End time after event

    name : string
        Comment that describes the Evoked data created.

    keep_comp : boolean
        Apply CTF gradient compensation

    baseline: None (default) or tuple of length 2
        The time interval to apply baseline correction.
        If None do not apply it. If baseline is (a, b)
        the interval is between "a (s)" and "b (s)".
        If a is None the beginning of the data is used
        and if b is None then b is set to the end of the interval.
        If baseline is equal ot (None, None) all the time
        interval is used.

    preload : boolean
        Load all epochs from disk when creating the object
        or wait before accessing each epoch (more memory
        efficient but can be slower).

    reject : dict
        Epoch rejection parameters based on peak to peak amplitude.
        Valid keys are 'grad' | 'mag' | 'eeg' | 'eog' | 'ecg'.
        If reject is None then no rejection is done.
        Values are float. Example:
        reject = dict(grad=4000e-13, # T / m (gradiometers)
                      mag=4e-12, # T (magnetometers)
                      eeg=40e-6, # uV (EEG channels)
                      eog=250e-6 # uV (EOG channels)
                      )

    flat : dict
        Epoch rejection parameters based on flatness of signal
        Valid keys are 'grad' | 'mag' | 'eeg' | 'eog' | 'ecg'
        If flat is None then no rejection is done.

    Methods
    -------
    get_epoch(i) : self
        Return the ith epoch as a 2D array [n_channels x n_times].

    get_data() : self
        Return all epochs as a 3D array [n_epochs x n_channels x n_times].

    average() : self
        Return Evoked object containing averaged epochs as a
        2D array [n_channels x n_times].

    """

    def __init__(self, raw, events, event_id, tmin, tmax, baseline=(None, 0),
                picks=None, name='Unknown', keep_comp=False, dest_comp=0,
                preload=False, reject=None, flat=None):
        self.raw = raw
        self.event_id = event_id
        self.tmin = tmin
        self.tmax = tmax
        self.picks = picks
        self.name = name
        self.keep_comp = keep_comp
        self.dest_comp = dest_comp
        self.baseline = baseline
        self.preload = preload
        self.reject = reject
        self.flat = flat

        # Handle measurement info
        self.info = copy.copy(raw.info)
        if picks is not None:
            self.info['chs'] = [self.info['chs'][k] for k in picks]
            self.info['ch_names'] = [self.info['ch_names'][k] for k in picks]
            self.info['nchan'] = len(picks)

        if picks is None:
            picks = range(len(raw.info['ch_names']))
            self.ch_names = raw.info['ch_names']
        else:
            self.ch_names = [raw.info['ch_names'][k] for k in picks]

        if len(picks) == 0:
            raise ValueError, "Picks cannot be empty."

        #   Set up projection
        if raw.info['projs'] is None:
            print 'No projector specified for these data'
            raw['proj'] = []
        else:
            #   Activate the projection items
            for proj in raw.info['projs']:
                proj['active'] = True

            print '%d projection items activated' % len(raw.info['projs'])

            #   Create the projector
            proj, nproj = fiff.proj.make_projector_info(raw.info)
            if nproj == 0:
                print 'The projection vectors do not apply to these channels'
                raw['proj'] = None
            else:
                print ('Created an SSP operator (subspace dimension = %d)'
                                                                    % nproj)
                raw['proj'] = proj

        #   Set up the CTF compensator
        current_comp = fiff.get_current_comp(raw.info)
        if current_comp > 0:
            print 'Current compensation grade : %d' % current_comp

        if keep_comp:
            dest_comp = current_comp

        if current_comp != dest_comp:
            raw.comp = fiff.raw.make_compensator(raw.info, current_comp,
                                                 dest_comp)
            print 'Appropriate compensator added to change to grade %d.' % (
                                                                    dest_comp)

        #    Select the desired events
        selected = np.logical_and(events[:, 1] == 0, events[:, 2] == event_id)
        self.events = events[selected]
        n_events = len(self.events)

        if n_events > 0:
            print '%d matching events found' % n_events
        else:
            raise ValueError, 'No desired events found.'

        # Handle times
        sfreq = raw.info['sfreq']
        self.times = np.arange(int(round(tmin*sfreq)), int(round(tmax*sfreq)),
                          dtype=np.float) / sfreq

        # setup epoch rejection
        self._reject_setup()

        if self.preload:
            self._data = self._get_data_from_disk()

    def drop_picks(self, bad_picks):
        """Drop some picks

        Allows to discard some channels.
        """
        self.picks = list(self.picks)
        idx = [k for k, p in enumerate(self.picks) if p not in bad_picks]
        self.picks = [self.picks[k] for k in idx]

        # XXX : could maybe be factorized
        self.info['chs'] = [self.info['chs'][k] for k in idx]
        self.info['ch_names'] = [self.info['ch_names'][k] for k in idx]
        self.info['nchan'] = len(idx)
        self.ch_names = self.info['ch_names']

        if self.preload:
            self._data = self._data[:,idx,:]


    def get_epoch(self, idx):
        """Load one epoch

        Returns
        -------
        data : array of shape [n_channels, n_times]
            One epoch data
        """
        if self.preload:
            return self._data[idx]
        else:
            return self._get_epoch_from_disk(idx)

    def _get_epoch_from_disk(self, idx):
        """Load one epoch from disk"""
        sfreq = self.raw.info['sfreq']
        event_samp = self.events[idx, 0]

        # Read a data segment
        first_samp = self.raw.first_samp
        start = int(round(event_samp + self.tmin*sfreq)) - first_samp
        stop = start + len(self.times)
        epoch, _ = self.raw[self.picks, start:stop]

        # Run baseline correction
        times = self.times
        baseline = self.baseline
        if baseline is not None:
            print "Applying baseline correction ..."
            bmin = baseline[0]
            bmax = baseline[1]
            if bmin is None:
                imin = 0
            else:
                imin = int(np.where(times >= bmin)[0][0])
            if bmax is None:
                imax = len(times)
            else:
                imax = int(np.where(times <= bmax)[0][-1]) + 1
            epoch -= np.mean(epoch[:, imin:imax], axis=1)[:, None]
        else:
            print "No baseline correction applied..."

        return epoch

    def _get_data_from_disk(self):
        """Load all data from disk
        """
        n_channels = len(self.ch_names)
        n_times = len(self.times)
        n_events = len(self.events)
        data = np.empty((n_events, n_channels, n_times))
        cnt = 0
        n_reject = 0
        for k in range(n_events):
            e = self._get_epoch_from_disk(k)
            if ((self.reject is not None or self.flat is not None) and
                not _is_good(e, self.ch_names, self._channel_type_idx,
                         self.reject, self.flat)) or e.shape[1] < n_times:
                n_reject += 1
            else:
                data[cnt] = self._get_epoch_from_disk(k)
                cnt += 1
        print "Rejecting %d epochs." % n_reject
        return data[:cnt]

    def get_data(self):
        """Get all epochs as a 3D array

        Returns
        -------
        data : array of shape [n_epochs, n_channels, n_times]
            The epochs data
        """
        if self.preload:
            return self._data
        else:
            return self._get_data_from_disk()

    def _reject_setup(self):
        """Setup reject process
        """
        if self.reject is None and self.flat is None:
            return

        idx = channel_indices_by_type(self.info)

        for key in idx.keys():
            if (self.reject is not None and key in self.reject) \
                    or (self.flat is not None and key in self.flat):
                if len(idx[key]) == 0:
                    raise ValueError("No %s channel found. Cannot reject based"
                                 " on %s." % (key.upper(), key.upper()))

        self._channel_type_idx = idx

    def __iter__(self):
        """To iteration over epochs easy.
        """
        self._current = 0
        return self

    def next(self):
        """To iteration over epochs easy.
        """
        if self._current >= len(self.events):
            raise StopIteration

        epoch = self.get_epoch(self._current)

        self._current += 1
        return epoch

    def __repr__(self):
        s = "n_events : %s" % len(self.events)
        s += ", tmin : %s (s)" % self.tmin
        s += ", tmax : %s (s)" % self.tmax
        s += ", baseline : %s" % str(self.baseline)
        return "Epochs (%s)" % s

    def average(self):
        """Compute average of epochs

        Returns
        -------
        evoked : Evoked instance
            The averaged epochs
        """
        evoked = Evoked(None)
        evoked.info = copy.copy(self.info)
        n_channels = len(self.ch_names)
        n_times = len(self.times)
        n_events = len(self.events)
        if self.preload:
            data = np.mean(self._data, axis=0)
        else:
            data = np.zeros((n_channels, n_times))
            for e in self:
                data += e
            data /= n_events
        evoked.data = data
        evoked.times = self.times.copy()
        evoked.comment = self.name
        evoked.aspect_kind = np.array([100]) # for standard average file
        evoked.nave = n_events
        evoked.first = - int(np.sum(self.times < 0))
        evoked.last = int(np.sum(self.times > 0))

        # dropping EOG, ECG and STIM channels. Keeping only data
        data_picks = pick_types(evoked.info, meg=True, eeg=True,
                                stim=False, eog=False, ecg=False,
                                emg=False)
        if len(data_picks) == 0:
            raise ValueError('No data channel found when averaging.')

        evoked.info['chs'] = [evoked.info['chs'][k] for k in data_picks]
        evoked.info['ch_names'] = [evoked.info['ch_names'][k]
                                    for k in data_picks]
        evoked.info['nchan'] = len(data_picks)
        evoked.data = evoked.data[data_picks]
        return evoked


def _is_good(e, ch_names, channel_type_idx, reject, flat):
    """Test if data segment e is good according to the criteria
    defined in reject and flat.
    """
    if reject is not None:
        for key, thresh in reject.iteritems():
            idx = channel_type_idx[key]
            name = key.upper()
            if len(idx) > 0:
                e_idx = e[idx]
                deltas = np.max(e_idx, axis=1) - np.min(e_idx, axis=1)
                idx_max_delta = np.argmax(deltas)
                delta = deltas[idx_max_delta]
                if delta > thresh:
                    ch_name = ch_names[idx[idx_max_delta]]
                    print '\tRejecting epoch based on %s : %s (%s > %s).' \
                                % (name, ch_name, delta, thresh)
                    return False
    if flat is not None:
        for key, thresh in flat.iteritems():
            idx = channel_type_idx[key]
            name = key.upper()
            if len(idx) > 0:
                e_idx = e[idx]
                deltas = np.max(e_idx, axis=1) - np.min(e_idx, axis=1)
                idx_min_delta = np.argmin(deltas)
                delta = deltas[idx_min_delta]
                if delta < thresh:
                    ch_name = ch_names[idx[idx_min_delta]]
                    print '\tRejecting flat epoch based on %s : %s (%s < %s).' \
                                % (name, ch_name, delta, thresh)
                    return False

    return True
