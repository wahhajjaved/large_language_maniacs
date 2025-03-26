def check_nframes(context, nx_event_data, item, values, fails):
    dataset_length = nx_event_data[item].shape[0]
    if 'event_time_zero' in context.keys() and nx_event_data['event_time_zero'].shape[0] is not dataset_length:
        fails.append("'%s' should have the same number of entries as '%s'" % (item, context['event_time_zero']))


def check_nevents(context, nx_event_data, item, values, fails):
    dataset_length = nx_event_data[item].shape[0]
    if 'total_counts' in context.keys() and dataset_length is not nx_event_data['total_counts']:
        fails.append(
            "'%s' should have a number of entries matching the total number of events recorded in 'total_counts'"
            % item)


VALIDATE = {
    "total_counts": [],
    "event_id": [check_nevents],
    "event_index": [check_nframes],
    "event_time_offset": [check_nevents],
    "event_time_zero": []
}


class _NXevent_dataFinder(object):
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
    context = {}
    values = {}
    fails = []

    for item in VALIDATE.keys():
        if item not in nx_event_data.keys():
            fails.append("'%s' is missing from the NXevent_data entry" % item)
        else:
            for test in VALIDATE[item]:
                test(context, nx_event_data, item, values, fails)

    if len(fails) > 0:
        raise AssertionError('\n'.join(fails))
    return values


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
            raise AssertionError("No NXevent_data entries in this entry")
        entries = []
        for nx_event_data_entry in nx_event_data_list:
            entries.append(validate(nx_event_data_entry))
        return entries
