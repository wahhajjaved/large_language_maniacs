#!/usr/bin/env python
# coding: utf-8

import unittest
from CubicCNN.src.util.calcutil import *


class TestCalcUtil(unittest.TestCase):
    def setup(self):
        print "TestCalcUtil : setup"

    def test_identity(self):
        print "TestCalcUtil : test_identity"
        self.assertEqual(identity(0), 0)
        self.assertEqual(identity(1), 1)
        self.assertEqual(identity(-1), -1)
        self.assertEqual(identity(1.), -1.)
        self.assertEqual(identity(-1.), -1.)

    def test_relu(self):
        print "TestCalcUtil : test_relu"
        self.assertTrue(relu(1) == 1)
        self.assertTrue(relu(0) == 0)
        self.assertTrue(relu(-5) == 0)
        self.assertTrue(relu(0.) == 0)
