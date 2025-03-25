"""
These are the basic black box tests for the doNd functions.
"""

from qdev_wrappers.dataset.doNd import do0d, do1d, do2d
from typing import Tuple, List, Optional
from qcodes.instrument.parameter import Parameter
from qcodes import config, new_experiment
from qcodes.utils import validators

import pytest

config.user.mainfolder = "output"  # set ouput folder for doNd's
new_experiment("doNd-tests", sample_name="no sample")

@pytest.fixture()
def _parameters():

    _param = Parameter('simple_parameter',
                   set_cmd=None,
                   get_cmd=lambda: 1)

    _paramComplex = Parameter('simple_complex_parameter',
                   set_cmd=None,
                   get_cmd=lambda: 1 + 1j,
                   vals=validators.ComplexNumbers())

    _param_set = Parameter('simple_setter_parameter',
                       set_cmd=None,
                       get_cmd=None)

    return _param, _paramComplex, _param_set


def _param_func(_p):
    """
    A private utility function.
    """
    _new_param = Parameter('modified_parameter',
                           set_cmd= None,
                           get_cmd= lambda: _p.get()*2)
    assert _new_param.get() == 2
    return _new_param


def test_do0d(_parameters):

    _param, _paramComplex, _ = _parameters
    do0d(_param)
    do0d(_param, write_period=1)
    do0d(_param, write_period=1, do_plot=False)

    do0d(_paramComplex)
    do0d(_paramComplex, write_period=1)
    do0d(_paramComplex, write_period=1, do_plot=False)

    do0d(_param_func(_param), write_period=1, do_plot=False)

    do0d(_param, _paramComplex, write_period=1, do_plot=False)
    do0d(_param_func(_param), _paramComplex, write_period=1, do_plot=False)

    _data = do0d(_param)
    assert type(_data[0]) == int

    _dataComplex = do0d(_paramComplex)
    assert type(_dataComplex[0]) == int

    _dataFunc = do0d(_param_func(_param))
    assert type(_dataFunc[0]) == int


def test_do1d(_parameters):

    _start = 0
    _stop = 1
    _num_points = 1
    _delay_list = [0, 0.1, 1]

    _param, _paramComplex, _param_set = _parameters

    for _delay in _delay_list:
        do1d(_param_set, _start, _stop, _num_points, _delay, _param)
        do1d(_param_set, _start, _stop, _num_points, _delay, _paramComplex)
        do1d(_param_set, _start, _stop, _num_points, _delay, _param,
                                                                 _paramComplex)

    _data = do1d(_param_set, _start, _stop, _num_points, _delay_list[0], _param)
    assert type(_data[0]) == int


def test_do2d(_parameters):

    _start_p1 = 0
    _stop_p1 = 1
    _num_points_p1 = 1
    _delay_p1 = 0

    _start_p2 = 0.1
    _stop_p2 = 1.1
    _num_points_p2 = 2
    _delay_p2 = 0.01

    _param, _paramComplex, _param_set = _parameters

    do2d(_param_set, _start_p1, _stop_p1, _num_points_p1, _delay_p1,
         _param_set, _start_p2, _stop_p2, _num_points_p2, _delay_p2,
         _param, _paramComplex)

    do2d(_param_set, _start_p1, _stop_p1, _num_points_p1, _delay_p1,
         _param_set, _start_p2, _stop_p2, _num_points_p2, _delay_p2,
         _param, _paramComplex, set_before_sweep=True)

    do2d(_param_set, _start_p1, _stop_p1, _num_points_p1, _delay_p1,
         _param_set, _start_p2, _stop_p2, _num_points_p2, _delay_p2,
         _param, _paramComplex, set_before_sweep=True, flush_columns=True)

    _data = do2d(_param_set, _start_p1, _stop_p1, _num_points_p1, _delay_p1,
                 _param_set, _start_p2, _stop_p2, _num_points_p2, _delay_p2,
                 _param, _paramComplex)

    assert type(_data[0]) == int
