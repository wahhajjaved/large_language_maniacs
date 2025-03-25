# coding: utf-8
# /*##########################################################################
# Copyright (C) 2016-2017 European Synchrotron Radiation Facility
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ############################################################################*/
"""Tests for fabioh5 wrapper"""

__authors__ = ["V. Valls"]
__license__ = "MIT"
__date__ = "04/10/2017"

import os
import sys
import logging
import numpy
import unittest
import tempfile
import shutil

_logger = logging.getLogger(__name__)


try:
    import fabio
except ImportError:
    fabio = None

try:
    import h5py
except ImportError:
    h5py = None

if fabio is not None and h5py is not None:
    from .. import fabioh5
    from .. import commonh5


class TestFabioH5(unittest.TestCase):

    def setUp(self):
        if fabio is None:
            self.skipTest("fabio is needed")
        if h5py is None:
            self.skipTest("h5py is needed")

        header = {
            "integer": "-100",
            "float": "1.0",
            "string": "hi!",
            "list_integer": "100 50 0",
            "list_float": "1.0 2.0 3.5",
            "string_looks_like_list": "2000 hi!",
        }
        data = numpy.array([[10, 11], [12, 13], [14, 15]], dtype=numpy.int64)
        self.fabio_image = fabio.numpyimage.NumpyImage(data, header)
        self.h5_image = fabioh5.File(fabio_image=self.fabio_image)

    def test_main_groups(self):
        self.assertEquals(self.h5_image.h5py_class, h5py.File)
        self.assertEquals(self.h5_image["/"].h5py_class, h5py.File)
        self.assertEquals(self.h5_image["/scan_0"].h5py_class, h5py.Group)
        self.assertEquals(self.h5_image["/scan_0/instrument"].h5py_class, h5py.Group)
        self.assertEquals(self.h5_image["/scan_0/measurement"].h5py_class, h5py.Group)

    def test_wrong_path_syntax(self):
        # result tested with a default h5py file
        self.assertRaises(ValueError, lambda: self.h5_image[""])

    def test_wrong_root_name(self):
        # result tested with a default h5py file
        self.assertRaises(KeyError, lambda: self.h5_image["/foo"])

    def test_wrong_root_path(self):
        # result tested with a default h5py file
        self.assertRaises(KeyError, lambda: self.h5_image["/foo/foo"])

    def test_wrong_name(self):
        # result tested with a default h5py file
        self.assertRaises(KeyError, lambda: self.h5_image["foo"])

    def test_wrong_path(self):
        # result tested with a default h5py file
        self.assertRaises(KeyError, lambda: self.h5_image["foo/foo"])

    def test_single_frame(self):
        data = numpy.arange(2 * 3)
        data.shape = 2, 3
        fabio_image = fabio.edfimage.edfimage(data=data)
        h5_image = fabioh5.File(fabio_image=fabio_image)

        dataset = h5_image["/scan_0/instrument/detector_0/data"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertTrue(isinstance(dataset[()], numpy.ndarray))
        self.assertEquals(dataset.dtype.kind, "i")
        self.assertEquals(dataset.shape, (2, 3))
        self.assertEquals(dataset[...][0, 0], 0)
        self.assertEquals(dataset.attrs["interpretation"], "image")

    def test_multi_frames(self):
        data = numpy.arange(2 * 3)
        data.shape = 2, 3
        fabio_image = fabio.edfimage.edfimage(data=data)
        fabio_image.appendFrame(data=data)
        h5_image = fabioh5.File(fabio_image=fabio_image)

        dataset = h5_image["/scan_0/instrument/detector_0/data"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertTrue(isinstance(dataset[()], numpy.ndarray))
        self.assertEquals(dataset.dtype.kind, "i")
        self.assertEquals(dataset.shape, (2, 2, 3))
        self.assertEquals(dataset[...][0, 0, 0], 0)
        self.assertEquals(dataset.attrs["interpretation"], "image")

    def test_heterogeneous_frames(self):
        """Frames containing 2 images with different sizes and a cube"""
        data1 = numpy.arange(2 * 3)
        data1.shape = 2, 3
        data2 = numpy.arange(2 * 5)
        data2.shape = 2, 5
        data3 = numpy.arange(2 * 5 * 1)
        data3.shape = 2, 5, 1
        fabio_image = fabio.edfimage.edfimage(data=data1)
        fabio_image.appendFrame(data=data2)
        fabio_image.appendFrame(data=data3)
        h5_image = fabioh5.File(fabio_image=fabio_image)

        dataset = h5_image["/scan_0/instrument/detector_0/data"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertTrue(isinstance(dataset[()], numpy.ndarray))
        self.assertEquals(dataset.dtype.kind, "i")
        self.assertEquals(dataset.shape, (3, 2, 5, 1))
        self.assertEquals(dataset[...][0, 0, 0], 0)
        self.assertEquals(dataset.attrs["interpretation"], "image")

    def test_single_3d_frame(self):
        """Image source contains a cube"""
        data = numpy.arange(2 * 3 * 4)
        data.shape = 2, 3, 4
        # Do not provide the data to the constructor to avoid slicing of the
        # data. In this way the result stay a cube, and not a multi-frame
        fabio_image = fabio.edfimage.edfimage()
        fabio_image.data = data
        h5_image = fabioh5.File(fabio_image=fabio_image)

        dataset = h5_image["/scan_0/instrument/detector_0/data"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertTrue(isinstance(dataset[()], numpy.ndarray))
        self.assertEquals(dataset.dtype.kind, "i")
        self.assertEquals(dataset.shape, (2, 3, 4))
        self.assertEquals(dataset[...][0, 0, 0], 0)
        self.assertEquals(dataset.attrs["interpretation"], "image")

    def test_metadata_int(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/integer"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset[()], -100)
        self.assertEquals(dataset.dtype.kind, "i")
        self.assertEquals(dataset.shape, (1,))

    def test_metadata_float(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/float"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset[()], 1.0)
        self.assertEquals(dataset.dtype.kind, "f")
        self.assertEquals(dataset.shape, (1,))

    def test_metadata_string(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/string"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset[()], numpy.string_("hi!"))
        self.assertEquals(dataset.dtype.type, numpy.string_)
        self.assertEquals(dataset.shape, (1,))

    def test_metadata_list_integer(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/list_integer"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset.dtype.kind, "u")
        self.assertEquals(dataset.shape, (1, 3))
        self.assertEquals(dataset[0, 0], 100)
        self.assertEquals(dataset[0, 1], 50)

    def test_metadata_list_float(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/list_float"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset.dtype.kind, "f")
        self.assertEquals(dataset.shape, (1, 3))
        self.assertEquals(dataset[0, 0], 1.0)
        self.assertEquals(dataset[0, 1], 2.0)

    def test_metadata_list_looks_like_list(self):
        dataset = self.h5_image["/scan_0/instrument/detector_0/others/string_looks_like_list"]
        self.assertEquals(dataset.h5py_class, h5py.Dataset)
        self.assertEquals(dataset[()], numpy.string_("2000 hi!"))
        self.assertEquals(dataset.dtype.type, numpy.string_)
        self.assertEquals(dataset.shape, (1,))

    def test_float_32(self):
        float_list = [u'1.2', u'1.3', u'1.4']
        data = numpy.array([[0, 0], [0, 0]], dtype=numpy.int8)
        fabio_image = None
        for float_item in float_list:
            header = {"float_item": float_item}
            if fabio_image is None:
                fabio_image = fabio.edfimage.EdfImage(data=data, header=header)
            else:
                fabio_image.appendFrame(data=data, header=header)
        h5_image = fabioh5.File(fabio_image=fabio_image)
        data = h5_image["/scan_0/instrument/detector_0/others/float_item"]
        # There is no equality between items
        self.assertEqual(len(data), len(set(data)))
        # At worst a float32
        self.assertIn(data.dtype.char, ['d', 'f'])
        self.assertLessEqual(data.dtype.itemsize, 32 / 8)

    def test_float_64(self):
        float_list = [
            u'1469117129.082226',
            u'1469117136.684986', u'1469117144.312749', u'1469117151.892507',
            u'1469117159.474265', u'1469117167.100027', u'1469117174.815799',
            u'1469117182.437561', u'1469117190.094326', u'1469117197.721089']
        data = numpy.array([[0, 0], [0, 0]], dtype=numpy.int8)
        fabio_image = None
        for float_item in float_list:
            header = {"time_of_day": float_item}
            if fabio_image is None:
                fabio_image = fabio.edfimage.EdfImage(data=data, header=header)
            else:
                fabio_image.appendFrame(data=data, header=header)
        h5_image = fabioh5.File(fabio_image=fabio_image)
        data = h5_image["/scan_0/instrument/detector_0/others/time_of_day"]
        # There is no equality between items
        self.assertEqual(len(data), len(set(data)))
        # At least a float64
        self.assertIn(data.dtype.char, ['d', 'f'])
        self.assertGreaterEqual(data.dtype.itemsize, 64 / 8)

    def test_ub_matrix(self):
        """Data from mediapix.edf"""
        header = {}
        header["UB_mne"] = 'UB0 UB1 UB2 UB3 UB4 UB5 UB6 UB7 UB8'
        header["UB_pos"] = '1.99593e-16 2.73682e-16 -1.54 -1.08894 1.08894 1.6083e-16 1.08894 1.08894 9.28619e-17'
        header["sample_mne"] = 'U0 U1 U2 U3 U4 U5'
        header["sample_pos"] = '4.08 4.08 4.08 90 90 90'
        data = numpy.array([[0, 0], [0, 0]], dtype=numpy.int8)
        fabio_image = fabio.edfimage.EdfImage(data=data, header=header)
        h5_image = fabioh5.File(fabio_image=fabio_image)
        sample = h5_image["/scan_0/sample"]
        self.assertIsNotNone(sample)
        self.assertEquals(sample.attrs["NXclass"], "NXsample")

        d = sample['unit_cell_abc']
        expected = numpy.array([4.08, 4.08, 4.08])
        self.assertIsNotNone(d)
        self.assertEquals(d.shape, (3, ))
        self.assertIn(d.dtype.char, ['d', 'f'])
        numpy.testing.assert_array_almost_equal(d[...], expected)

        d = sample['unit_cell_alphabetagamma']
        expected = numpy.array([90.0, 90.0, 90.0])
        self.assertIsNotNone(d)
        self.assertEquals(d.shape, (3, ))
        self.assertIn(d.dtype.char, ['d', 'f'])
        numpy.testing.assert_array_almost_equal(d[...], expected)

        d = sample['ub_matrix']
        expected = numpy.array([[[1.99593e-16, 2.73682e-16, -1.54],
                                 [-1.08894, 1.08894, 1.6083e-16],
                                 [1.08894, 1.08894, 9.28619e-17]]])
        self.assertIsNotNone(d)
        self.assertEquals(d.shape, (1, 3, 3))
        self.assertIn(d.dtype.char, ['d', 'f'])
        numpy.testing.assert_array_almost_equal(d[...], expected)

    def test_get_api(self):
        result = self.h5_image.get("scan_0", getclass=True, getlink=True)
        self.assertIs(result, h5py.HardLink)
        result = self.h5_image.get("scan_0", getclass=False, getlink=True)
        self.assertIsInstance(result, h5py.HardLink)
        result = self.h5_image.get("scan_0", getclass=True, getlink=False)
        self.assertIs(result, h5py.Group)
        result = self.h5_image.get("scan_0", getclass=False, getlink=False)
        self.assertIsInstance(result, commonh5.Group)

    def test_detector_link(self):
        detector1 = self.h5_image["/scan_0/instrument/detector_0"]
        detector2 = self.h5_image["/scan_0/measurement/image_0/info"]
        self.assertIsNot(detector1, detector2)
        self.assertEqual(list(detector1.items()), list(detector2.items()))
        self.assertEqual(self.h5_image.get(detector2.name, getlink=True).path, detector1.name)

    def test_detector_data_link(self):
        data1 = self.h5_image["/scan_0/instrument/detector_0/data"]
        data2 = self.h5_image["/scan_0/measurement/image_0/data"]
        self.assertIsNot(data1, data2)
        self.assertIs(data1._get_data(), data2._get_data())
        self.assertEqual(self.h5_image.get(data2.name, getlink=True).path, data1.name)

    def test_dirty_header(self):
        """Test that it does not fail"""
        try:
            header = {}
            header["foo"] = b'abc'
            data = numpy.array([[0, 0], [0, 0]], dtype=numpy.int8)
            fabio_image = fabio.edfimage.edfimage(data=data, header=header)
            header = {}
            header["foo"] = b'a\x90bc\xFE'
            fabio_image.appendFrame(data=data, header=header)
        except Exception as e:
            _logger.error(e.args[0])
            _logger.debug("Backtrace", exc_info=True)
            self.skipTest("fabio do not allow to create the resource")

        h5_image = fabioh5.File(fabio_image=fabio_image)
        scan_header_path = "/scan_0/instrument/file/scan_header"
        self.assertIn(scan_header_path, h5_image)
        data = h5_image[scan_header_path]
        self.assertIsInstance(data[...], numpy.ndarray)

    def test_unicode_header(self):
        """Test that it does not fail"""
        try:
            header = {}
            header["foo"] = b'abc'
            data = numpy.array([[0, 0], [0, 0]], dtype=numpy.int8)
            fabio_image = fabio.edfimage.edfimage(data=data, header=header)
            header = {}
            header["foo"] = u'abc\u2764'
            fabio_image.appendFrame(data=data, header=header)
        except Exception as e:
            _logger.error(e.args[0])
            _logger.debug("Backtrace", exc_info=True)
            self.skipTest("fabio do not allow to create the resource")

        h5_image = fabioh5.File(fabio_image=fabio_image)
        scan_header_path = "/scan_0/instrument/file/scan_header"
        self.assertIn(scan_header_path, h5_image)
        data = h5_image[scan_header_path]
        self.assertIsInstance(data[...], numpy.ndarray)


class TestFabioH5WithEdf(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if fabio is None:
            raise unittest.SkipTest("fabio is needed")
        if h5py is None:
            raise unittest.SkipTest("h5py is needed")

        cls.tmp_directory = tempfile.mkdtemp()

        cls.edf_filename = os.path.join(cls.tmp_directory, "test.edf")

        header = {
            "integer": "-100",
            "float": "1.0",
            "string": "hi!",
            "list_integer": "100 50 0",
            "list_float": "1.0 2.0 3.5",
            "string_looks_like_list": "2000 hi!",
        }
        data = numpy.array([[10, 11], [12, 13], [14, 15]], dtype=numpy.int64)
        fabio_image = fabio.edfimage.edfimage(data, header)
        fabio_image.write(cls.edf_filename)

        cls.fabio_image = fabio.open(cls.edf_filename)
        cls.h5_image = fabioh5.File(fabio_image=cls.fabio_image)

    @classmethod
    def tearDownClass(cls):
        cls.fabio_image = None
        cls.h5_image = None
        if sys.platform == "win32" and fabio is not None:
            # gc collect is needed to close a file descriptor
            # opened by fabio and not released.
            # https://github.com/silx-kit/fabio/issues/167
            import gc
            gc.collect()
        shutil.rmtree(cls.tmp_directory)

    def test_reserved_format_metadata(self):
        if fabio.hexversion < 327920:  # 0.5.0 final
            self.skipTest("fabio >= 0.5.0 final is needed")

        # The EDF contains reserved keys in the header
        self.assertIn("HeaderID", self.fabio_image.header)
        # We do not expose them in FabioH5
        self.assertNotIn("/scan_0/instrument/detector_0/others/HeaderID", self.h5_image)


def suite():
    loadTests = unittest.defaultTestLoader.loadTestsFromTestCase
    test_suite = unittest.TestSuite()
    test_suite.addTest(loadTests(TestFabioH5))
    test_suite.addTest(loadTests(TestFabioH5WithEdf))
    return test_suite


if __name__ == '__main__':
    unittest.main(defaultTest="suite")
