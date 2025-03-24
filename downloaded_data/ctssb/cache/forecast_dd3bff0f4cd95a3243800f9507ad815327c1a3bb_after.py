# -*- coding: utf-8 -*-
############################################################################
#    Module Writen For Odoo, Open Source Management Solution
#
#    Copyright (c) 2011 Vauxoo - http://www.vauxoo.com
#    All Rights Reserved.
#    info Vauxoo (info@vauxoo.com)
#    coded by: Katherine Zaoral <kathy@vauxoo.com>
#    planned by: Nhomar Hernandez <nhomar@vauxoo.com>
#                Gabriela Quilarque <gabriela@vauxoo.com>
############################################################################

from openerp import _
from openerp.tests import common


class TestForecasting(common.TransactionCase):

    """
    Test that the forecasting smothing model is working propertly.
    """

    maxDiff = None

    def setUp(self):
        super(TestForecasting, self).setUp()
        self.forecast_obj = self.env['forecasting.smoothing.techniques']

    def compare(self, expected, real):
        """
        Compare the correct result with the real result. Print logger with
        error tag.
        """
        elist = list()
        keys = expected.keys()
        keys.sort()
        error_msg = "{key:15} {real:15} != {expected:15} {ca} {diff:15}"
        for key in keys:
            vreal = real.get(key)
            vexpected  = expected.get(key)
            vdiff = abs(vreal - vexpected)
            allowed_error = 0.1
            if vdiff > allowed_error:
                elist += [error_msg.format(
                    key=key,
                    real=vreal,
                    expected=vexpected,
                    ca=vexpected < vreal and '>' or '<',
                    diff=vdiff)]

        error_msg = '\n'.join(['\n', _('Fall forecast calculation ')] + elist)
        self.assertTrue(elist == [], error_msg)
        # self.assertDictEqual(correct, real)

    def test_01(self):
        """
        Run 80 values, count for 1 to 30 and repeat.
        """
        values = self.get_test_01_in()
        forecast = self.forecast_obj.create(values)
        out = self.get_test_01_out()
        self.compare(out, forecast.read(out.keys())[0])

    def get_test_01_in(self):
        """
        config the values for the forecasting model to test.
        """
        data = {}
        val = 1
        for item in range(1, 81):
            fvfield = 'fv_{num:02d}'.format(num=item)
            data.update({fvfield: val})
            if val == 30:
                val = 1
            else:
                val += 1
        return data

    def get_test_01_out(self):
        """
        Return a dictionary with the expected result of the test.
        """
        return dict(
            ma_forecast=14.0,
            ma_ma_error=3.157895,
            wma_forecast=4.666667,
            wma_ma_error=10.684211,
            single_forecast=17.690605,
            single_ma_error=2.881943,
            double_forecast=19.755723,
            double_ma_error=5.155758,
            triple_forecast=19.580177,
            triple_ma_error=6.901317,
            holt_forecast=18.221501,
            holt_ma_error=3.003755
        )

    def test_02(self):
        """
        Run 10 values
        - Only 10 forecast values of the 80 spaces.
        """
        values = self.get_test_02_in()
        forecast = self.forecast_obj.create(values)
        out = self.get_test_02_out()
        self.compare(out, forecast.read(out.keys())[0])

    def get_test_02_in(self):
        """
        This method will return the forecast input values in a list.
        """
        data = {}
        val = 1
        for item in range(1, 11):
            fvfield = 'fv_{num:02d}'.format(num=item)
            data.update({fvfield: val})
            val += 1
        return data

    def get_test_02_out(self):
        """
        Return a dictionary with the expected result of the test.
        """
        return dict(
            ma_forecast=4.0,
            ma_ma_error=2,
            wma_forecast=1.333333,
            wma_ma_error=5.666667,
            single_forecast=7.760825,
            single_ma_error=1.577526,
            double_forecast=9.481168,
            double_ma_error=2.691897,
            triple_forecast=9.451321,
            triple_ma_error=3.432094,
            holt_forecast=11,
            holt_ma_error=0
        )

    # def _test_all(self):
    #     """
    #     Run all the test cases know.
    #     """
    #     for test_num in range(1, 5):
    #         test_name = 'test_{num:02d}'.format(num=test_num)
    #         values, out = self.get_test_data(test_name)
    #         forecast = self.forecast_obj.create(values)
    #         self.compare(out, forecast.read([])[0])

    def get_test_data(self, test_name):
        """
        return tupla in, out with the values to use in the test.
        """
        data = {
            'test_01': self.get_test_01_data(),
            'test_02': self.get_test_02_data(),
            'test_03': {'in': self.get_test_03_in(),
                        'out': self.get_test_03_out(),
                        },
            'test_04': {'in': self.get_test_04_in(),
                        'out': self.get_test_04_out(),
                        },
        }
        test_data = data.get(test_name)
        return test_data.get('in'), test_data.get('out')

    def get_test_01_data(self):
        """
        return dictionary with the keys (in, out).
        - in: values to create the forecast record. Used to config the test.
        - out: the expected results of the test.
        """
        values = {}
        val = 1
        for item in range(1, 81):
            fvfield = 'fv_{num:02d}'.format(num=item)
            values.update({fvfield: val})
            if val == 30:
                val = 1
            else:
                val += 1

        out = dict(
            ma_forecast=14.0,
            ma_ma_error=3.157895,
            wma_forecast=4.666667,
            wma_ma_error=10.684211,
            single_forecast=17.690605,
            single_ma_error=2.881943,
            double_forecast=19.755723,
            double_ma_error=5.155758,
            triple_forecast=19.580177,
            triple_ma_error=6.901317,
            holt_forecast=18.221501,
            holt_ma_error=3.003755
        )
        return {'in': values, 'out': out}


    def get_test_02_data(self):
        """
        return dictionary with the keys (in, out).
        - in: values to create the forecast record. Used to config the test.
        - out: the expected results of the test.
        """
        values = {}
        val = 1
        for item in range(1, 11):
            fvfield = 'fv_{num:02d}'.format(num=item)
            values.update({fvfield: val})
            val += 1
        out = dict(
            ma_forecast=4.0,
            ma_ma_error=2,
            wma_forecast=1.333333,
            wma_ma_error=5.666667,
            single_forecast=7.760825,
            single_ma_error=1.577526,
            double_forecast=9.481168,
            double_ma_error=2.691897,
            triple_forecast=9.451321,
            triple_ma_error=3.432094,
            holt_forecast=11,
            holt_ma_error=0
        )
        return {'in': values, 'out': out}

    def test_03(self):
        """
        Run 10 values
        - Only 10 forecast values of the 80 spaces.
        """
        values = self.get_test_03_in()
        forecast = self.forecast_obj.create(values)
        out = self.get_test_03_out()
        self.compare(out, forecast.read(out.keys())[0])

    def get_test_03_in(self):
        """
        This method will return the forecast input values in a list.
        """
        data = {
            'fv_01': 133,
            'fv_02': 155,
            'fv_03': 165,
            'fv_04': 171,
            'fv_05': 194,
            'fv_06': 231,
            'fv_07': 274,
            'fv_08': 312,
            'fv_09': 313,
            'fv_10': 333,
            'fv_11': 343,
            'holt_alpha': 0.7,
            'beta': 0.6,
            'period': 2,
        }
        return data

    def get_test_03_out(self):
        """
        Return a dictionary with the expected result of the test.
        """
        # period forecast
        # 1	359.7
        # 2	372.6
        # 3	385.4
        # 4	398.3
        return dict(
            holt_forecast=372.6,
        )

    def get_test_04_in(self):
        """
        This are data to run the forecast test_04
        """
        data = {
            'fv_01': 105,
            'fv_02': 100,
            'fv_03': 105,
            'fv_04': 95,
            'fv_05': 100,
            'fv_06': 95,
            'fv_07': 105,
            'fv_08': 120,
            'fv_09': 115,
            'fv_10': 125,
            'fv_11': 120,
            'fv_12': 120,
        }
        return data

    def get_test_04_out(self):
        """
        Return a dictionary with the expected result of the test.

        Week	Sales ($1000)	MA(5)	WMA(5)
        1	105	-	-
        2	100	-	-
        3	105	-	-
        4	95	-	-
        5	100	101	100
        6	95	99	98
        7	105	100	100
        8	120	103	107
        9	115	107	111
        10	125	117	116
        11	120	120	119
        12	120	120	119
        """
        return dict(
            ma=120,
            wma=119,
        )
