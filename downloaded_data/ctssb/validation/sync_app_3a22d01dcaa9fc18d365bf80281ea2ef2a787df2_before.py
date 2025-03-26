#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
    Unit tests for sync_app
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
#import hashlib
import unittest

CURDIR = os.path.abspath(os.curdir)
os.sys.path.append(CURDIR)

from sync_app.sync_utils import get_md5
from sync_app.file_list_s3 import FileListS3
from sync_app.s3_instance import S3Instance

TEST_FILE = 'tests/test_dir/hello_world.txt'
TEST_DIR = 'tests/test_dir'
TEST_GDR = 'Amazon-Gift-Card.pdf'

class TestSyncAppS3(unittest.TestCase):
    """ SyncApp Unit Tests """

    def setUp(self):
        self.s3 = S3Instance()
        self.flist_s3 = FileListS3(s3=self.s3)

    def test_s3_list_files(self):
        for bucket in self.s3.get_list_of_buckets():
            self.s3.get_list_of_keys(bucket_name=bucket,
                                     callback_fn=self.flist_s3.append_item)
        md_ = self.flist_s3['2015-01-01.txt'].md5sum
        self.assertEqual(md_, '866c3c2d566d44b88e1e4a4fc1e7d65d')
        
    def test_s3_upload_search_download_delete(self):
        bname = 'test_bucket_ddboline_20150521'
        self.s3.create_bucket(bname)
        self.s3.upload(bname, TEST_FILE, os.path.abspath(TEST_FILE))
        self.s3.get_list_of_keys(bucket_name=bname,
                                 callback_fn=self.flist_s3.append_item)
        md5_ = self.flist_s3[TEST_FILE].md5sum
        self.assertEqual(md5_, '8ddd8be4b179a529afa5f2ffae4b9858')
        self.s3.download(bname, TEST_FILE, 'tests/test_dir/test.txt')
        self.s3.delete_key(bname, TEST_FILE)
        self.s3.delete_bucket('test_bucket_ddbline_20150521')
        md5_ = get_md5('tests/test_dir/test.txt')
        self.assertEqual(md5_, '8ddd8be4b179a529afa5f2ffae4b9858')
        os.remove('tests/test_dir/test.txt')

if __name__ == '__main__':
    unittest.main()
