#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest

class AboutAsserts(unittest.TestCase):

    def test_assert_truth(self):
        """
        We shall contemplate truth by testing reality, via asserts.
        """

        # Confused? This video should help:
        #
        #   http://bit.ly/about_asserts

        self.assertTrue(True)  # This should be true

if __name__ == '__main__':
    unittest.main()
