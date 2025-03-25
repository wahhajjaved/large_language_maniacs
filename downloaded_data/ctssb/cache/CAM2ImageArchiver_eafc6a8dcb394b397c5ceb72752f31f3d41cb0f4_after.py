'''
Copyright 2017 Purdue University

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''
from __future__ import absolute_import

import unittest
import sys
import os
import shutil
from CAM2ImageArchiver.camera import Camera, IPCamera, StreamFormat
from CAM2ImageArchiver.CAM2ImageArchiver import CAM2ImageArchiver
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCamera(unittest.TestCase):

    def setUp(self):

        # Instantiate camera test fixtures
        cam = {
            'cameraID': '101',
            'camera_type': 'non_ip',
            'snapshot_url': 'http://images.webcams.travel/preview/1169307993.jpg'
        }
        cam2 = {
            'cameraID': '201',
            'camera_type': 'ip',
            'ip': '207.251.86.238',
            'port': '',
            'image_path': '/cctv254.jpg',
            'video_path': '/axis-cgi/mjpg/video.cgi'
        }
        cam3 = {
            'cameraID': '301',
            'camera_type': 'stream',
            'm3u8_url': 'http://images.webcams.travel/preview/1169307993.jpg'
        }
        self.cameras = [cam, cam2, cam3]
        self.archiver = CAM2ImageArchiver(num_processes=1, result_path='testing/')

        # Test functions that only belong to IP Camera
        self.ip_cam = IPCamera(221, "127.1.1.1", "/test_image_path", "/test_mjpeg_path", "3000")


    @classmethod
    def tearDownClass(cls):
        if os.path.isdir('testing'):
            shutil.rmtree('testing')

    def test_get_frame_with_custom_result_path_success(self):
        self.assertIsNone(self.archiver.archive(self.cameras))
        directories = set(os.listdir('testing'))
        expected_dirs = set(('301', '101', '201'))
        self.assertEqual(directories, expected_dirs, 'Image Parsing Failed.')

    def test_get_frame_with_longer_duration_interval_success(self):
        self.assertIsNone(self.archiver.archive(self.cameras, duration=6, interval=3))
        directories = set(os.listdir('testing'))
        expected_dirs = set(('301', '101', '201'))
        self.assertEqual(directories, expected_dirs, 'Image Parsing Failed.')

    def test_folder_not_generated_when_parsing_failed(self):
        if os.path.isdir('testing'):
            shutil.rmtree('testing')
        cam2 = {
            'cameraID': '202',
            'camera_type': 'ip',
            'ip': '207.251.86.238',
            'port': '',
            'image_path': '/axis-cgi/mjpg/video.cgi',
            'video_path': '/axis-cgi/mjpg/video.cgi'
        }
        self.cameras = [cam2]
        self.assertIsNone(self.archiver.archive(self.cameras))
        self.assertEqual(os.listdir('testing'), [], 'Folder 202 should not exist because it is empty')

    def test_duplicate_image(self):
        """
        Test downloading a image for 5 seconds from Google IMAGE
        """
        dupcam = {
            'cameraID': '203',
            'camera_type': 'non_ip',
            'snapshot_url': 'https://cdn.britannica.com/s:700x450/45/5645-004-7461C1BD.jpg'
        }
        self.cameras = [dupcam]
        self.assertIsNone(self.archiver.archive(self.cameras, duration=5, interval=1))

    # Test IP Camera
    def test_get_frame_no_parser(self):
        # Assert camera raises error when no parser is present
        # Todo: Change Exception to the Actual error 'ClosedStreamError' will trigger error
        with self.assertRaises(Exception):
            Camera(220).get_frame()

    def test_open_stream_invalid_enum(self):
        # Assert exception raised with invalid enum
        self.assertRaises(ValueError, self.ip_cam.open_stream, "INVALID_ENUM_VAL")

    def test_get_url_invalid_enum(self):
        # Assert exception raised with invalid enum
        self.assertRaises(ValueError, self.ip_cam.get_url, "INVALID_ENUM_VAL")

    def test_get_url_mjpeg(self):
        # Assert url correctly created for mjpeg case
        result = self.ip_cam.get_url(StreamFormat.MJPEG)
        self.assertEqual(result, "http://127.1.1.1:3000/test_mjpeg_path")

    def test_get_url_image(self):
        # Assert url correctly created for image case
        result = self.ip_cam.get_url(StreamFormat.IMAGE)
        self.assertEqual(result, "http://127.1.1.1:3000/test_image_path")


if __name__ == '__main__':
    unittest.main()
