def _visit_NXdetector_with_image_key(name, obj):
    if "NX_class" in obj.attrs.keys():
        if str(obj.attrs["NX_class"], 'utf8') in ["NXdetector"]:
            if "image_key" in obj.keys():
                return obj


def get_NXdetector_with_image_key(nx_file, entry):
    return nx_file[entry].visititems(_visit_NXdetector_with_image_key)


class recipe:
    """
        A demo recipe for finding the information associated with this demo feature.

        This is meant to help consumers of this feature to understand how to implement
        code that understands that feature (copy and paste of the code is allowed).
        It also documents in what preference order (if any) certain things are evaluated
        when finding the information.
    """

    def __init__(self, filedesc, entrypath):
        self.file = filedesc
        self.entry = entrypath
        self.title = "NXdetector with image key"

    def process(self):
        nxDet = get_NXdetector_with_image_key(self.file, self.entry)
        if nxDet is not None:
            return {"NXdetector with image_key": nxDet}
        raise AssertionError("This file does not contain an NXdetector with the image_key field")
