from datetime import datetime, tzinfo, timedelta
import numpy as np
from itertools import compress


class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return timedelta(0)


class NXevent_dataExamples:
    def __init__(self):
        pass

    @staticmethod
    def get_pulse_index_of_event(nx_event_data, nth_event):
        """
        Find the pulse index that the nth_event occurred in

        :param: nx_event_data: An NXevent_data HDF5 group in a NeXus file
        :param nth_event: The Nth detection event in the group
        :return: pulse index of the nth_event
        """
        # Find index of the last element which has event_index lower than the nth_event
        # this is the index of the pulse (frame) which the nth_event falls in
        event_index = nx_event_data['event_index'][...]
        for i, event_index_for_pulse in enumerate(event_index):
            if event_index_for_pulse > nth_event:
                return i - 1

    def get_time_neutron_detected(self, nx_event_data, nth_event):
        """
        Use offset and time units attributes to find the absolute time
        that neutron with index of event_number to hit the detector

        :param: nx_event_data: An NXevent_data HDF5 group in a NeXus file
        :param nth_event: The Nth detection event in the group
        :return: Absolute time of neutron event detection in ISO8601 format
        """
        if "event_time_offset" in nx_event_data.keys() and nx_event_data['event_time_offset'][...].size > (
                    nth_event + 1):
            # Get absolute pulse time in seconds since epoch
            pulse_index = self.get_pulse_index_of_event(nx_event_data, nth_event)
            pulse_start_time_seconds = self._convert_to_seconds(nx_event_data['event_time_zero'][pulse_index],
                                                                nx_event_data['event_time_zero'].attrs['units'])
            pulse_start_offset = self._isotime_to_unixtime_in_seconds(nx_event_data['event_time_zero'].attrs['offset'])
            pulse_absolute_seconds = pulse_start_time_seconds + pulse_start_offset

            # Get event time in seconds relative to pulse time
            event_offset = nx_event_data['event_time_offset'][nth_event]
            event_offset_seconds = self._convert_to_seconds(event_offset,
                                                            nx_event_data['event_time_offset'].attrs['units'])

            # Calculate absolute event time in seconds since epoch
            absolute_event_time_seconds = pulse_absolute_seconds + event_offset_seconds
            # and convert to a readable string in ISO8601 format
            absolute_event_time_iso = datetime.fromtimestamp(absolute_event_time_seconds, tz=UTC()).isoformat()
            return absolute_event_time_iso

    @staticmethod
    def get_events_by_time_range(nx_event_data, range_start, range_end):
        """
        Return arrays of neutron detection timestamps and the corresponding IDs for the detectectors on which they
        were detected, for a given time range.
        Note, method uses (the optional) event_time_zero and event_index to achieve this without loading entire
        event datasets which in general can be too large to fit in memory.

        :param nx_event_data: An NXevent_data HDF5 group in a NeXus file
        :param range_start: Start time range, collect events occuring after this time
        :param range_end: End time range, collect events occuring before this time
        :return:
        """
        # event_time_zero is a small subset of timestamps from the full event_time_offsets dataset
        # Since it is small we can load the whole dataset from file with [...]
        cue_timestamps = nx_event_data['event_time_zero'][...]
        # event_index maps between indices in event_time_zero and event_time_offsets
        cue_indices = nx_event_data['event_index'][...]

        # Look up the positions in the full timestamp list where the cue timestamps are in our range of interest
        range_indices = cue_indices[np.append((range_start < cue_timestamps[1:]), [True]) &
                                    np.append([True], (range_end > cue_timestamps[:-1]))][[0, -1]]

        # Now we can extract a slice of the log which we know contains the time range we are interested in
        times = nx_event_data['event_time_offset'][range_indices[0]:range_indices[1]]
        detector_ids = nx_event_data['event_id'][range_indices[0]:range_indices[1]]

        # Truncate them to the exact time range asked for
        times_mask = (range_start <= times) & (times <= range_end)
        times = times[times_mask]
        detector_ids = detector_ids[times_mask]

        return times, detector_ids

    @staticmethod
    def _isotime_to_unixtime_in_seconds(isotime):
        utc_dt = datetime.strptime(isotime, '%Y-%m-%dT%H:%M:%S')
        # convert UTC datetime to seconds since the Epoch
        return (utc_dt - datetime(1970, 1, 1)).total_seconds()

    @staticmethod
    def _convert_to_seconds(event_offset, time_unit):
        if time_unit in ['seconds', 'second', 's']:
            return event_offset
        elif time_unit in ['milliseconds', 'millisecond', 'ms']:
            return event_offset * 1e-3
        elif time_unit in ['microseconds', 'microsecond', 'us']:
            return event_offset * 1e-6
        elif time_unit in ['nanoseconds', 'nanosecond', 'ns']:
            return event_offset * 1e-9
        else:
            raise ValueError('Unrecognised time unit in event_time_offset')


class _NXevent_dataFinder(object):
    """
    Finds NXevent_data groups in the file
    """

    def __init__(self):
        self.hits = []

    def _visit_NXevent_data(self, name, obj):
        if "NX_class" in obj.attrs.keys():
            if "NXevent_data" in obj.attrs["NX_class"]:
                self.hits.append(obj)

    def get_NXevent_data(self, nx_file, entry):
        self.hits = []
        nx_file[entry].visititems(self._visit_NXevent_data)
        return self.hits


def validate(nx_event_data):
    """
    Checks that lengths of datasets which should be the same length as each other are.

    :param nx_event_data: An NXevent_data group which was found in the file
    """
    fails = []

    _check_datasets_have_same_length(nx_event_data, ['event_time_offset', 'event_id'], fails)
    _check_datasets_have_same_length(nx_event_data, ['event_time_zero', 'event_index'], fails)
    _check_datasets_have_same_length(nx_event_data, ['cue_timestamp_zero', 'cue_index'], fails)

    if len(fails) > 0:
        raise AssertionError('\n'.join(fails))


def _check_datasets_have_same_length(group, dataset_names, fails):
    """
    If all named datasets exist in group then check they have the same length

    :param group: HDF group
    :param dataset_names: Iterable of dataset names
    :param fails: Failures are recorded in this list
    """
    dataset_lengths = [group[dataset_name].len() for dataset_name in _existant_datasets(group, dataset_names)]
    if len(set(dataset_lengths)) > 1:
        fails.append(', '.join(dataset_names) + "should have the same length in " + group.name)


def _existant_datasets(group, dataset_names):
    """
    Reduce dataset list to only those present in the group

    :param group: HDF group containing the datasets
    :param dataset_names: Iterable of dataset names
    :return: List containing only the dataset names which exist in the group
    """
    existant_dataset_mask = [True if dataset_name in group else False for dataset_name in dataset_names]
    return list(compress(dataset_names, existant_dataset_mask))


class recipe:
    """
        This is meant to help consumers of this feature to understand how to implement
        code that understands that feature (copy and paste of the code is allowed).
        It also documents in what preference order (if any) certain things are evaluated
        when finding the information.
    """

    def __init__(self, filedesc, entrypath):
        self.file = filedesc
        self.entry = entrypath
        self.title = "NXevent_data"

    def process(self):
        nx_event_data = _NXevent_dataFinder()
        nx_event_data_list = nx_event_data.get_NXevent_data(self.file, self.entry)
        if len(nx_event_data_list) == 0:
            raise AssertionError("No NXevent_data entries found")
        for nx_event_data_entry in nx_event_data_list:
            validate(nx_event_data_entry)

        return NXevent_dataExamples
