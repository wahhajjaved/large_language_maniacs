#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testing parameters and methods of the Detector class using mocks
"""

import pytest
from sls_detector.utils import eiger_register_to_time

def test_convert_zero():
    assert eiger_register_to_time(0) == 0

def test_convert_smallest_unit():
    assert pytest.approx(eiger_register_to_time(0b1000), 1e-9) == 1e-8

def test_convert_second_smallest_unit():
    assert pytest.approx(eiger_register_to_time(0b10000), 1e-9) == 2e-8

def test_convert_one_ms_using_exponent():
    assert pytest.approx(eiger_register_to_time(0b1101), 1e-9) == 1e-3

def test_convert_five_seconds():
    assert pytest.approx(eiger_register_to_time(0b1001110001000101), 1e-9) == 5.01
