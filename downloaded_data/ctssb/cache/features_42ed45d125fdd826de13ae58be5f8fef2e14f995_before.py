def check_len(context, entry, item, values, fails):
    frames = entry[item].shape[0]
    if ('nFrames' not in context.keys()) and frames != 1:
        context['nFrames'] = frames
        context['nFrames_item'] = item
    else:
        if frames not in [context['nFrames'], 1]:
            fails.append("'%s' does not have the same number of frames as '%s'" % (item, context['nFrames_item']))


def check_int(context, entry, item, value, fails):
    dtype = entry[item].dtype
    if dtype not in ["int64"]:
        fails.append("'%s' is of type %s, expected int32 or int64" % (item, dtype))


def check_bool(context, entry, item, value, fails):
    dtype = entry[item].dtype
    if dtype not in ["bool"]:
        fails.append("'%s' is of type %s, expected bool" % (item, dtype))


def check_uint(context, entry, item, value, fails):
    dtype = entry[item].dtype
    if dtype not in ["uint64"]:
        fails.append("'%s' is of type %s, expected uint64" % (item, dtype))


def check_float(context, entry, item, value, fails):
    dtype = entry[item].dtype
    if dtype not in ["float64"]:
        fails.append("'%s' is of type %s, expected float64" % (item, dtype))


def check_array_uint(context, entry, item, value, fails):
    dtype = entry[item].dtype
    if dtype not in ["object"]:
        fails.append("'%s' is of type %s, expected object" % (item, dtype))


VALIDATE = {
    "h": (False, [check_len, check_int]),
    "k": (False, [check_len, check_int]),
    "l": (False, [check_len, check_int]),
    "id": (False, [check_len, check_uint]),
    "reflection_id": (False, [check_len, check_uint]),
    "entering": (False, [check_len, check_bool]),
    "det_module": (False, [check_len, check_uint]),
    "flags": (False, [check_len, check_uint]),
    "d": (False, [check_len, check_float]),
    "partiality": (False, [check_len, check_float]),
    "prd_frame": (False, [check_len, check_float]),
    "prd_mm_x": (False, [check_len, check_float]),
    "prd_mm_y": (False, [check_len, check_float]),
    "prd_phi": (False, [check_len, check_float]),
    "prd_px_x": (False, [check_len, check_float]),
    "prd_px_y": (False, [check_len, check_float]),
    "obs_frame_val": (False, [check_len, check_float]),
    "obs_frame_var": (False, [check_len, check_float]),
    "obs_px_x_val": (False, [check_len, check_float]),
    "obs_px_x_var": (False, [check_len, check_float]),
    "obs_px_y_val": (False, [check_len, check_float]),
    "obs_px_y_var": (False, [check_len, check_float]),
    "obs_phi_val": (False, [check_len, check_float]),
    "obs_phi_var": (False, [check_len, check_float]),
    "obs_mm_x_val": (False, [check_len, check_float]),
    "obs_mm_x_var": (False, [check_len, check_float]),
    "obs_mm_y_val": (False, [check_len, check_float]),
    "obs_mm_y_var": (False, [check_len, check_float]),
    "bbx0": (False, [check_len, check_int]),
    "bbx1": (False, [check_len, check_int]),
    "bby0": (False, [check_len, check_int]),
    "bby1": (False, [check_len, check_int]),
    "bbz0": (False, [check_len, check_int]),
    "bbz1": (False, [check_len, check_int]),
    "bkg_mean": (False, [check_len, check_float]),
    "int_prf_val": (True, [check_len, check_float]),
    "int_prf_var": (True, [check_len, check_float]),
    "int_sum_val": (False, [check_len, check_float]),
    "int_sum_var": (False, [check_len, check_float]),
    "lp": (False, [check_len, check_float]),
    "prf_cc": (True, [check_len, check_float]),
    "overlaps": (True, [check_len, check_array_uint]),
}


def find_nx_diffraction_entries(nx_file, entry):
    hits = []

    def visitor(name, obj):
        if "NX_class" in obj.attrs.keys():
            if str(obj.attrs["NX_class"], 'utf8') in ["NXentry", "NXsubentry"]:
                if "definition" in obj.keys():
                    if str(obj["definition"].value, 'utf8') == "NXdiffraction":
                        hits.append(obj)

    nx_file[entry].visititems(visitor)
    return hits


def check_path(entry, path):
    section = entry
    for part in path.split('/'):
        if part in section.keys():
            section = section[part]
        else:
            return False
    return True


def validate(entry):
    context = {}
    values = {}
    fails = []
    for item, (optional, tests) in VALIDATE.iteritems():
        if check_path(entry, item):
            for test in tests:
                test(context, entry, item, values, fails)
        elif not optional:
            fails.append("'NXdiffraction/%s' is missing from the NXdiffraction entry" % (item))
    if len(fails) > 0:
        raise AssertionError('\n'.join(fails))
    return values


class recipe:
    """
    Recipe to validate files with the NXdiffraction feature

    """

    def __init__(self, filedesc, entrypath):
        self.file = filedesc
        self.entry = entrypath
        self.title = "NXdiffraction"

    def process(self):
        entries = find_nx_diffraction_entries(self.file, self.entry)
        if len(entries) == 0:
            raise AssertionError('No NXdiffraction entries found')
        return map(validate, entries)
