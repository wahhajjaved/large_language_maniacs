# -*- mode: python; coding: utf-8; indent-tabs-mode: nil; python-indent: 2 -*-
#
# $Id$

from __future__ import division
from __future__ import print_function

from dxtbx.format.FormatPY import FormatPY


class FormatPYmultitile(FormatPY):
    @staticmethod
    def understand(image_file):
        try:
            import cPickle as pickle

            stream = FormatPYmultitile.open_file(image_file, "rb")
            data = pickle.load(stream)
        except IOError:
            return False

        wanted_header_items = ["TILES", "METROLOGY"]
        for header_item in wanted_header_items:
            if not header_item in data:
                return False

        unwanted_header_items = ["SIZE1", "SIZE2"]
        for header_item in unwanted_header_items:
            if header_item in data:
                return False

        return True

    def __init__(self, image_file):
        """Initialise the image structure from the given file."""

        assert self.understand(image_file)

        FormatPY.__init__(self, image_file)

    def _start(self):
        from xfel.cftbx.detector.cspad_detector import CSPadDetector

        self.detectorbase = CSPadDetector(self._image_file)
        self.detectorbase.readHeader()
        self._metrology_params = self.detectorbase._metrology_params
        self._tiles = self.detectorbase._tiles

        # The lines above could eventually be replaced by the lines
        # below.
        """
      from cPickle import load
      stream = FormatPYmultitile.open_file(self._image_file)
      d = load(stream)
      self._metrology_params = d['METROLOGY'].extract()
      self._tiles = d['TILES']
      stream.close()
      """

    def _goniometer(self):
        return self._goniometer_factory.single_axis()

    def _detector(self):
        """The _detector() function returns a model for a CSPAD detector as
        used at LCLS's CXI and XPP endstations.  It converts the
        metrology information in the pure Python object extracted from
        the image pickle to DXTBX-style transformation vectors.  Only
        ASIC:s are considered, since DXTBX metrology is not concerned
        with hierarchies.

        Merged from xfel.cftbx.detector.cspad_detector.readHeader() and
        xfel.cftbx.detector.metrology.metrology_as_dxtbx_vectors().
        """

        from dxtbx_model_ext import Detector, Panel, SimplePxMmStrategy
        from scitbx.matrix import col

        # XXX Introduces dependency on cctbx.xfel!  Should probably be
        # merged into the code here!
        from xfel.cftbx.detector.metrology import _transform, get_projection_matrix

        # Apply the detector distance to the translation of the root
        # detector object.
        d = self._metrology_params.detector
        Tb_d = _transform(
            col(d.orientation).normalize(),
            col(d.translation) + col((0, 0, self._metrology_params.distance * 1e-3)),
        )[1]

        panels = []
        self._raw_data = []
        for p in d.panel:
            Tb_p = (
                Tb_d * _transform(col(p.orientation).normalize(), col(p.translation))[1]
            )

            for s in p.sensor:
                Tb_s = (
                    Tb_p
                    * _transform(col(s.orientation).normalize(), col(s.translation))[1]
                )

                for a in s.asic:
                    Tb_a = (
                        Tb_s
                        * _transform(
                            col(a.orientation).normalize(), col(a.translation)
                        )[1]
                    )

                    Pb = get_projection_matrix(a.pixel_size, a.dimension)[1]

                    # The DXTBX-style metrology description consists of three
                    # vectors for each ASIC.  The origin vector locates the
                    # (0, 0)-pixel in the laboratory frame in units of mm.
                    # The second and third vectors give the directions to the
                    # pixels immediately next to (0, 0) in the fast and slow
                    # directions, respectively, in arbitrary units.
                    origin = Tb_a * Pb * col((0, 0, 1))
                    fast = Tb_a * Pb * col((0, a.dimension[0], 1)) - origin
                    slow = Tb_a * Pb * col((a.dimension[1], 0, 1)) - origin

                    # Convert vector units from meter to millimeter.  The
                    # default, SimplePxMmStrategy applies here.  XXX Due to
                    # dark subtraction, a valid pixel intensity may be
                    # negative, and this is currently not reflected by
                    # trusted_range.
                    key = (d.serial, p.serial, s.serial, a.serial)
                    panels.append(
                        Panel(
                            type="PAD",
                            name="%d:%d:%d:%d" % key,
                            fast_axis=[t * 1e3 for t in fast.elems[0:3]],
                            slow_axis=[t * 1e3 for t in slow.elems[0:3]],
                            origin=[t * 1e3 for t in origin.elems[0:3]],
                            pixel_size=[t * 1e3 for t in a.pixel_size],
                            image_size=a.dimension,
                            trusted_range=(0, a.saturation),
                        )
                    )

                    self._raw_data.append(self._tiles[key])

        detector = Detector(panels)
        detector.mask = []  # a list of dead rectangles

        return detector

    def get_raw_data(self, index=None):
        """If @p index is @c None, return the flex array for the first ASIC.
        Otherwise return the array for the ASIC at index @p index.
        """

        if index is not None:
            return self._raw_data[index]
        return self._raw_data[0]

    def _beam(self):
        """Return a simple model for the beam."""

        return self._beam_factory.simple(self._metrology_params.wavelength)

    def _scan(self):
        """Return the scan information for this image."""

        from calendar import timegm
        from time import strptime

        # Convert textual ISO 8601 timestamp in UTC to
        # millisecond-precision Unix epoch.
        str_min = self._metrology_params.timestamp[:16] + "UTC"
        str_sec = self._metrology_params.timestamp[17:]
        epoch = timegm(strptime(str_min, "%Y-%m-%dT%H:%M%Z")) + float(str_sec)

        return self._scan_factory.make_scan(
            image_range=(1, 1),
            exposure_time=1e-15 * self._metrology_params.pulse_length,
            oscillation=(0, 0),
            epochs={1: epoch},
        )


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(FormatPYmultitile.understand(arg))
