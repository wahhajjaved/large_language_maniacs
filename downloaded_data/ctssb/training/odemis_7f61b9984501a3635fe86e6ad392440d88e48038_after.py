# -*- coding: utf-8 -*-
'''
Created on 12 Mar 2012

@author: Éric Piel
Abstract class for testing digital camera in general.

Copyright © 2012 Éric Piel, Delmic

This file is part of Odemis.

Odemis is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License version 2 as published by the Free Software
Foundation.

Odemis is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
Odemis. If not, see http://www.gnu.org/licenses/.
'''
# This is not a real test case, but just a stub to be used for each camera driver.

from abc import ABCMeta, abstractproperty
import gc
import logging
import numpy
from odemis import model
from odemis.driver import semcomedi
import threading
import time
import unittest


#gc.set_debug(gc.DEBUG_LEAK | gc.DEBUG_STATS)
# arguments used for the creation of the SEM simulator
# Note that you need to run this line after a boot, for the simulator to work:
# sudo comedi_config /dev/comedi0 comedi_test 1000000,1000000
CONFIG_SED = {"name": "sed", "role": "sed", "channel":5, "limits": [-3, 3]}
CONFIG_SCANNER = {"name": "scanner", "role": "ebeam", "limits": [[0, 5], [0, 5]],
                  "channels": [0, 1], "settle_time": 10e-6, "hfw_nomag": 10e-3}
CONFIG_SEM = {"name": "sem", "role": "sem", "device": "/dev/comedi0",
              "children": {"detector0": CONFIG_SED, "scanner": CONFIG_SCANNER}
              }


class VirtualStaticTestCam(object):
    """
    For tests which don't need a camera ready
    """
    __metaclass__ = ABCMeta

    # needs:
    # camera_type : class of the camera
    # camera_kwargs : dict of arguments to create a camera
    @abstractproperty
    def camera_type(self):
        pass

    @abstractproperty
    def camera_kwargs(self):
        pass

    def test_scan(self):
        """
        Check that we can do a scan. It can pass only if we are
        connected to at least one camera.
        """
        if not hasattr(self.camera_type, "scan"):
            self.skipTest("Camera class doesn't support scanning")
        cameras = self.camera_type.scan()
        self.assertGreater(len(cameras), 0)


# It doesn't inherit from TestCase because it should not be run by itself
#class VirtualTestCam(unittest.TestCase):
class VirtualTestCam(object):
    """
    Abstract class for all the DigitalCameras
    """
    __metaclass__ = ABCMeta

    # needs:
    # camera_type : class of the camera
    # camera_kwargs : dict of arguments to create a camera
    @abstractproperty
    def camera_type(self):
        pass

    @abstractproperty
    def camera_kwargs(self):
        pass

    # These need to be called explicitly from the child as it's not a TestCase
    @classmethod
    def setUpClass(cls):
        cls.camera = cls.camera_type(**cls.camera_kwargs)

    @classmethod
    def tearDownClass(cls):
        cls.camera.terminate()

    def setUp(self):
        # reset size and binning
        try:
            self.camera.binning.value = (1, 1)
        except AttributeError:
            pass # no binning
        self.size = self.camera.shape[:-1]
        self.camera.resolution.value = self.size
        self.acq_dates = (set(), set())  # 2 sets of dates, one for each receiver

    def tearDown(self):
#        print gc.get_referrers(self.camera)
#        gc.collect()
        pass

#    @unittest.skip("simple")
    def test_temp(self):
        if (not hasattr(self.camera, "targetTemperature") or
            not isinstance(self.camera.targetTemperature, model.VigilantAttributeBase)):
            self.skipTest("Camera doesn't support setting temperature")

        ttemp = self.camera.targetTemperature.value
        self.assertTrue(-300 < ttemp and ttemp < 100)
        self.camera.targetTemperature.value = self.camera.targetTemperature.range[0]
        self.assertEqual(self.camera.targetTemperature.value, self.camera.targetTemperature.range[0])

#    @unittest.skip("simple")
    def test_acquire(self):
        self.assertEqual(len(self.camera.shape), 3)
        exposure = 0.1
        self.camera.exposureTime.value = exposure

        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1])
        self.assertGreaterEqual(duration, exposure, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)

    def test_translation(self):
        """
        test the translation VA (if available)
        """
        if (not hasattr(self.camera, "translation") or
            not isinstance(self.camera.translation, model.VigilantAttributeBase) or
            self.camera.translation.readonly):
            self.skipTest("Camera doesn't support setting translation")

        # Check the translation can be changed
        self.camera.binning.value = (2, 2)
        self.camera.resolution.value = (16, 16)
        self.camera.translation.value = (-10, 3) # values are small enough they should always be fine
        im = self.camera.data.get()
        self.assertEqual(self.camera.translation.value, (-10, 3))

        # Check the translation automatically fits after putting a large ROI
        self.camera.binning.value = (1, 1)
        self.camera.resolution.value = self.camera.resolution.range[1]
        self.assertEqual(self.camera.translation.value, (0, 0))
        im = self.camera.data.get()

        # Check the MD_POS metadata is correctly updated
        orig_md = {model.MD_PIXEL_SIZE: (1e-6, 1e-6), # m
                   model.MD_PIXEL_SIZE_COR: (0.5, 0.5), # the actual pxs is /2
                   model.MD_POS: (-1.1, 0.9),
                   }
        self.camera.updateMetadata(orig_md)
        im = self.camera.data.get()
        self.assertEqual(im.metadata[model.MD_POS], orig_md[model.MD_POS])

        self.camera.binning.value = (2, 2)
        self.camera.updateMetadata({model.MD_PIXEL_SIZE: (2e-6, 2e-6)})
        self.camera.resolution.value = (16, 16)
        im = self.camera.data.get()
        self.assertEqual(im.metadata[model.MD_POS], orig_md[model.MD_POS])

        self.camera.translation.value = (-10, 3)
        im = self.camera.data.get()
        exp_pos = (-1.1 + (-10 * 2e-6 * 0.5), 0.9 - (3 * 2e-6 * 0.5))  # phys Y goes opposite direction
        self.assertEqual(im.metadata[model.MD_POS], exp_pos)

        # Note: the position of the image when the resolution is odd can be slightly
        # shift without any translation, but let's not go there...

#    @unittest.skip("simple")
    def test_two_acquire(self):
        exposure = 0.1

        # just to check it works
        self.camera.binning.value = (1, 1)

        self.camera.exposureTime.value = exposure

        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1])
        self.assertGreaterEqual(duration, exposure, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)

        # just to check it still works
        self.camera.binning.value = (1, 1)

        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1])
        self.assertGreaterEqual(duration, exposure, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)

#    @unittest.skip("simple")
    def test_acquire_flow(self):
        exposure = 0.1
        self.camera.exposureTime.value = exposure

        number = 5
        self.left = number
        self.camera.data.subscribe(self.receive_image)
        for i in range(number):
            # end early if it's already finished
            if self.left == 0:
                break
            time.sleep(2 + exposure) # 2s per image should be more than enough in any case

        self.assertEqual(self.left, 0)

#    @unittest.skip("simple")
    def test_data_flow_with_va(self):
        exposure = 1.0 # long enough to be sure we can change VAs before the end
        self.camera.exposureTime.value = exposure

        number = 3
        self.left = number
        self.camera.data.subscribe(self.receive_image)

        # change the attribute
        time.sleep(exposure)
        self.camera.exposureTime.value = exposure / 2
        # should just not raise any exception

        for i in range(number):
            # end early if it's already finished
            if self.left == 0:
                break
            time.sleep(2 + exposure) # 2s per image should be more than enough in any case

        self.assertEqual(self.left, 0)

#    @unittest.skip("not implemented")
    def test_df_subscribe_get(self):
        exposure = 1.0 # long enough to be sure we can do a get before the end
        self.camera.exposureTime.value = exposure

        number = 3
        self.left = number
        self.camera.data.subscribe(self.receive_image)

        # change the attribute
        time.sleep(exposure)
        self.camera.exposureTime.value = exposure / 2
        # should just not raise any exception

        # get one image: probably the first one from the subscribe (without new exposure)
        im = self.camera.data.get()

        # get a second image (this one must be generated with the new settings)
        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1])
        self.assertGreaterEqual(duration, exposure / 2, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)

        for i in range(number):
            # end early if it's already finished
            if self.left == 0:
                break
            time.sleep(2 + exposure) # 2s per image should be more than enough in any case

        self.assertEqual(self.left, 0)

#    @unittest.skip("simple")
    def test_df_double_subscribe(self):
        exposure = 1.0 # long enough to be sure we can do a get before the end
        number, number2 = 3, 5
        self.camera.exposureTime.value = exposure

        self.left = number
        self.camera.data.subscribe(self.receive_image)

        time.sleep(exposure)
        self.left2 = number2
        self.camera.data.subscribe(self.receive_image2)

        for i in range(number + number2):
            # end early if it's already finished
            if self.left == 0 and self.left2 == 0:
                break
            time.sleep(2 + exposure) # 2s per image should be more than enough in any case

        # check that at least some images are shared?
        common_dates = self.acq_dates[0] & self.acq_dates[1]
        self.assertGreater(len(common_dates), 0, "No common dates between %r and %r" %
                           (self.acq_dates[0], self.acq_dates[1]))

        self.assertEqual(self.left, 0)
        self.assertEqual(self.left2, 0)

#    @unittest.skip("simple")
    def test_df_alternate_sub_unsub(self):
        """
        Test the dataflow on a quick cycle subscribing/unsubscribing
        Andorcam3 had a real bug causing deadlock in this scenario
        """
        exposure = 0.1 # s
        number = 5
        self.camera.exposureTime.value = exposure

        self.left = 10000 + number # don't unsubscribe automatically

        for i in range(number):
            self.camera.data.subscribe(self.receive_image)

            time.sleep(1 + exposure) # make sure we received at least one image
            self.camera.data.unsubscribe(self.receive_image)

        # if it has acquired a least 5 pictures we are already happy
        self.assertLessEqual(self.left, 10000)

    def receive_image(self, dataflow, image):
        """
        callback for df of test_acquire_flow()
        """
        self.assertEqual(image.shape, self.size[::-1])
        self.assertIn(model.MD_EXP_TIME, image.metadata)
        self.acq_dates[0].add(image.metadata[model.MD_ACQ_DATE])
#        print "Received an image"
        self.left -= 1
        if self.left <= 0:
            dataflow.unsubscribe(self.receive_image)

    def receive_image2(self, dataflow, image):
        """
        callback for df of test_acquire_flow()
        """
        self.assertEqual(image.shape, self.size[::-1])
        self.assertIn(model.MD_EXP_TIME, image.metadata)
        self.acq_dates[1].add(image.metadata[model.MD_ACQ_DATE])
#        print "Received an image in 2"
        self.left2 -= 1
        if self.left2 <= 0:
            dataflow.unsubscribe(self.receive_image2)

#    @unittest.skip("simple")
    def test_binning(self):
        self.camera.binning.value = (1, 1)
        max_binning = self.camera.binning.range[1]
        new_binning = (2, 2)
        if new_binning >= max_binning:
            # if there is no binning 2, let's not try
            self.skipTest("Camera doesn't support binning")

        # binning should automatically resize the image
        prev_size = self.camera.resolution.value
        self.camera.binning.value = new_binning
        self.assertNotEqual(self.camera.resolution.value, prev_size)

        # ask for the whole image
        self.size = (self.camera.shape[0] / 2, self.camera.shape[1] / 2)
        self.camera.resolution.value = self.size
        exposure = 0.1
        self.camera.exposureTime.value = exposure

        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1]) # TODO a small size diff is fine if bigger than requested
        self.assertGreaterEqual(duration, exposure, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)
        self.assertEqual(im.metadata[model.MD_BINNING], new_binning)

#    @unittest.skip("simple")
    def test_aoi(self):
        """
        Check sub-area acquisition works
        """
        self.size = (self.camera.shape[0] / 2, self.camera.shape[1] / 2)
        exposure = 0.1

        if (self.camera.resolution.range[0][0] > self.size[0] or
            self.camera.resolution.range[0][1] > self.size[1]):
            # cannot divide the size by 2? Then it probably doesn't support AOI
            self.skipTest("Camera doesn't support area of interest")

        self.camera.resolution.value = self.size
        if self.camera.resolution.value == self.camera.shape[:2]:
            # cannot divide the size by 2? Then it probably doesn't support AOI
            self.skipTest("Camera doesn't support area of interest")

        self.camera.exposureTime.value = exposure
        start = time.time()
        im = self.camera.data.get()
        duration = time.time() - start

        self.assertEqual(im.shape, self.size[::-1])
        self.assertGreaterEqual(duration, exposure, "Error execution took %f s, less than exposure time %f." % (duration, exposure))
        self.assertIn(model.MD_EXP_TIME, im.metadata)

#    @unittest.skip("simple")
    def test_error(self):
        """
        Errors should raise an exception but still allow to access the camera afterwards
        """
        # empty resolution
        try:
            self.camera.resolution.value = (self.camera.shape[0], 0) # 0 px should be too small
            self.fail("Empty resolution should fail")
        except:
            pass # good!

        # null and negative exposure time
        try:
            self.camera.exposureTime.value = 0.0 # 0 is too short
            self.fail("Null exposure time should fail")
        except:
            pass # good!

        try:
            self.camera.exposureTime.value = -1.0 # negative
            self.fail("Negative exposure time should fail")
        except:
            pass # good!


class VirtualTestSynchronized(object):
    """
    Test the synchronizedOn(Event) interface, using the fake SEM
    """
    __metaclass__ = ABCMeta

    # needs:
    # camera_type : class of the camera
    # camera_kwargs : dict of arguments to create a camera
    @abstractproperty
    def camera_type(self):
        pass

    @abstractproperty
    def camera_kwargs(self):
        pass

    @classmethod
    def setUpClass(cls):
        cls.ccd = cls.camera_type(**cls.camera_kwargs)
        cls.sem = semcomedi.SEMComedi(**CONFIG_SEM)

        for child in cls.sem.children.value:
            if child.name == CONFIG_SED["name"]:
                cls.sed = child
            elif child.name == CONFIG_SCANNER["name"]:
                cls.scanner = child

    @classmethod
    def tearDownClass(cls):
        cls.ccd.terminate()
        cls.sem.terminate()

    def setUp(self):
        self.got_image = threading.Event()

    def tearDown(self):
        # just in case it failed
        self.ccd.data.unsubscribe(self.receive_ccd_image)
        self.sed.data.unsubscribe(self.receive_sem_data)

    def test_basic(self):
        """
        check the synchronization of the SEM with the CCD:
        The SEM scans a region and for each point, the CCD acquires one image.
        """
        start = time.time()
        # use large binning, to reduce the resolution
        self.ccd.binning.value = (min(self.ccd.binning.range[1][0], 4),
                                  self.ccd.binning.range[1][1])

        exp = 50e-3  # s
        # in practice, it takes up to 500ms to take an image of 50 ms exposure
        self.sem_size = (10, 10)
        self.ccd_size = self.ccd.resolution.value
        numbert = numpy.prod(self.sem_size)

        self.ccd.exposureTime.value = exp
        # magical formula to get a long enough dwell time.
        # works with PVCam and Andorcam, but is probably different with other drivers :-(
        readout = numpy.prod(self.ccd_size) / self.ccd.readoutRate.value
        # it seems with the iVac, 20ms is enough to account for the overhead and extra image acquisition
        self.scanner.dwellTime.value = (exp + readout) * 1.1 + 0.1
        self.scanner.resolution.value = self.sem_size
        # pixel write/read setup is pretty expensive ~10ms
        expected_duration = numbert * (self.scanner.dwellTime.value + 0.01)

        self.sem_left = 1 # unsubscribe just after one
        self.ccd_left = numbert # unsubscribe after receiving

        try:
            self.ccd.data.synchronizedOn(self.scanner.newPosition)
        except IOError:
            self.skipTest("Camera doesn't support synchronisation")
        self.ccd.data.subscribe(self.receive_ccd_image)

        self.sed.data.subscribe(self.receive_sem_data)
        for i in range(10):
            # * 3 because it can be quite long to setup each pixel.
            time.sleep(expected_duration * 2 / 10)
            if self.sem_left == 0:
                break # just to make it quicker if it's quicker

        logging.info("Took %g s", self.end_time - start)
        time.sleep(exp + readout)
        self.assertEqual(self.sem_left, 0)
        self.assertEqual(self.ccd_left, 0)
        self.ccd.data.synchronizedOn(None)

        # check we can still get data normally
        d = self.ccd.data.get()

        time.sleep(0.1)

    def test_software_trigger(self):
        """
        Check that the synchronisation with softwareTrigger works.
        Make it typical, by waiting for the data received, and then notifying
        the software trigger again after a little while.
        """
        if not hasattr(self.ccd, "softwareTrigger"):
            self.skipTest("Camera doesn't support software trigger")
        exp = 50e-3 # s
        self.ccd.exposureTime.value = exp
        self.ccd.binning.value = (1, 1)
        self.ccd_size = self.ccd.resolution.value
        readout = numpy.prod(self.ccd_size) / self.ccd.readoutRate.value
        duration = exp + readout # approximate time for one frame

        numbert = 10
        self.ccd_left = numbert # unsubscribe after receiving

        try:
            self.ccd.data.synchronizedOn(self.ccd.softwareTrigger)
        except IOError:
            self.skipTest("Camera doesn't support synchronisation")
        self.ccd.data.subscribe(self.receive_ccd_image)

        # Wait for the image
        for i in range(numbert):
            self.got_image.clear()
            self.ccd.softwareTrigger.notify()
            # wait for the image to be received
            gi = self.got_image.wait(duration + 10)
            self.assertTrue(gi, "image not received after %g s" % (duration + 10))
            time.sleep(i * 0.1) # wait a bit to simulate some processing

        self.assertEqual(self.ccd_left, 0)
        self.ccd.data.synchronizedOn(None)

        # check we can still get data normally
        d = self.ccd.data.get()

        time.sleep(0.1)

    def receive_sem_data(self, dataflow, image):
        """
        callback for SEM df
        """
        self.assertEqual(image.shape, self.sem_size[::-1])
        self.assertIn(model.MD_DWELL_TIME, image.metadata)
        self.sem_left -= 1
        if self.sem_left <= 0:
            dataflow.unsubscribe(self.receive_sem_data)

    def receive_ccd_image(self, dataflow, image):
        """
        callback for CCD
        """
        self.assertEqual(image.shape, self.ccd_size[::-1])
        self.ccd_left -= 1
        if self.ccd_left <= 0:
            dataflow.unsubscribe(self.receive_ccd_image)
            self.end_time = time.time()
        self.got_image.set()
