#!/usr/bin/env python
# vim:et:sta:sts=4:sw=4:ts=8:tw=79:

from __future__ import division
import numpy as np
from sympy import diff, limit, simplify, latex, pi
from sympy.functions import Abs
from PointOfInterest import PointOfInterest as POI
from helpers import pod, fsolve, rfc
from logging import debug
import re

class Function:
    
    def update_graph_points(self, xylimits):
        x_min, x_max, y_min, y_max = xylimits
        x = np.arange(x_min, x_max, (x_max-x_min)/self.resolution)
        # if it doesn't evaluate, the expression is wrong
        try:
            y = eval(self.np_expr)
        except:
            return False
        # no need to calculate values that are off the displayed
        # scale. This fixes some trouble with asymptotes like in
        # tan(x).
        # FIXME: unfortunately there is more trouble with asymptotes
        try:
            y[y>y_max] = np.inf
            y[y<y_min] = np.inf
        # if f(x)=a, make sure that y is an array with the same size
        # as x and with a constant value.
        except TypeError:
            debug('This looks like a constant function: '+\
                    self.np_expr)
            self.constant = True
            l = len(x)
            yarr = np.ndarray([l,])
            yarr[yarr!=y]=y
            y = yarr
        self.graph_points = x, y
        return True

    def _get_expr(self, expr):
        # caps to lowercase
        expr = expr.lower()
        # remove all spaces
        expr = expr.replace(' ', '')
        # replace commas with decimals
        expr = expr.replace(',', '.')
        # braces and bracets to parens
        expr = expr.replace('{', '(')
        expr = expr.replace('}', ')')
        expr = expr.replace('[', '(')
        expr = expr.replace(']', ')')
        # turn greek (unicode) notation to english
        expr = expr.replace('\xce\xb7\xce\xbc(', 'sin(')
        expr = expr.replace('\xcf\x83\xcf\x85\xce\xbd(', 'cos(')
        expr = expr.replace('\xce\xb5\xcf\x86(', 'tan(')
        expr = expr.replace('\xcf\x83\xcf\x86(', 'cot(')
        expr = expr.replace('\xcf\x83\xcf\x84\xce\xb5\xce\xbc(',
                'csc(')
        expr = expr.replace('\xcf\x84\xce\xb5\xce\xbc(', 'sec(')
        expr = expr.replace('\xcf\x87', 'x')
        expr = expr.replace('\xcf\x80', 'pi')
        # implied multiplication
        expr = re.sub('([0-9])([a-z\(])', '\\1*\\2', expr)
        expr = re.sub('([a-z\)])([0-9])', '\\1*\\2', expr)
        expr = re.sub('(pi)([a-z\(])', '\\1*\\2', expr)
        expr = re.sub('([a-z\)])(pi)', '\\1*\\2', expr)
        expr = re.sub('(\))([a-z\(])', '\\1*\\2', expr)
        expr = re.sub('(x)([a-z\(])', '\\1*\\2', expr)
        return expr

    def _get_np_expr(self, expr):
        # add "np." prefix to trig functions
        expr = expr.replace('sin(', 'np.sin(')
        expr = expr.replace('cos(', 'np.cos(')
        expr = expr.replace('tan(', 'np.tan(')
        expr = expr.replace('cot(', '1/np.tan(') # no cot in numpy
        expr = expr.replace('sec(', '1/np.cos(') # no sec,
        expr = expr.replace('csc(', '1/np.sin(') # and no csc either
        # correct log functions
        expr = expr.replace('log(', 'np.log(')
        # square root
        expr = expr.replace('sqrt(', 'np.sqrt(')
        # absolute value. For numpy, turn the sympy Abs function
        # to np.abs
        expr = expr.replace('Abs(', 'np.abs(')
        # pi and e
        expr = expr.replace('pi', 'np.pi')
        expr = expr.replace('e', 'np.e')
        # powers
        expr = expr.replace('^', '**')
        return expr
    
    def _simplify_expr(self, expr):
        # sympy.functions.Abs is imported as Abs so we're using it
        # that way with sympy
        expr = expr.replace('abs(', 'Abs(')
        # we need to convert e to a float value. Since sec() is the
        # only function that also includes an "e", we'll remove
        # that temporarily
        expr = expr.replace('sec(', 'scc(')
        expr = expr.replace('e', '2.7183')
        expr = expr.replace('scc(', 'sec(')
        # sympy only supports natural logarithms and log(x) = ln(x).
        # For log base 10, we'll do the convertion manually:
        # log10(x) = ln(x)/ln(10) = ln(x)/2.302585093 =
        #  = 0.4342944819*ln(x)
        # This is a hack, but appears to work fine (at least
        # in most cases).
        # The number of decimal points is restricted to 4, otherwise
        # calculations could take a really long time. 4 is good
        # enough in any case. Example for f(x) = log(x)-1:
        # - 3 decimals: 152ms
        # - 4 decimals: 228ms
        # - 5 decimals: 301ms
        # - 6 decimals: 561ms
        # - 7 decimals: 3.89s
        expr = expr.replace('log(', '0.4343*ln(')

        simp_expr = simplify(expr)
        debug('"'+expr+'" has been simplified to "'+\
                str(simp_expr)+'"')
        return simp_expr


    def _get_mathtex_expr(self, expr):
        # expr is a simplified sympy expression. Creates a LaTeX
        # string from the expression using sympy latex printing.
        e = latex(expr)
        e = e.replace('0.4343 \\log{', '\\log10{')
        e = e.replace('log{', 'ln{')
        e = e.replace('log10', 'log')
        e = e.replace('\\lvert', '|')
        e = e.replace('\\rvert', '|')
        # translate e value back to e symbol
        e = e.replace('2.7183', 'e')
        e = '$'+e+'$'
        return e

    def calc_poi(self):
        expr = self.simp_expr
        
        self.poi = []
        #
        # y intercept
        #
        debug('Looking for the y intercept for: '+str(expr))
        y = expr.subs('x', 0)
        if str(y) == 'zoo' or str(y) == 'nan':
            # 'zoo' is imaginary infinity
            debug('The Y axis is actually a vertical asymptote.')
            self.poi.append(POI(0, 0, 6))
            debug('Added vertical asymptote (0,0)')
        else:
            yc = rfc(y)
            if yc is not None:
                self.poi.append(POI(0, yc, 3))
                debug('Added y intercept at (0,'+str(yc)+')')
        if not self.constant:
            #
            # x intercepts
            #
            debug('Looking for x intercepts for: '+str(expr))
            x = fsolve(expr)
            for xc in x:
                self.poi.append(POI(xc, 0, 2))
                debug('Added x intercept at ('+str(xc)+',0)')
            # try to find if the function is periodic using the
            # distance between the x intercepts
            if self.trigonometric and not self.periodic and \
                    not self.polynomial:
                debug('Checking if function is periodic using'+\
                        ' x intercepts.')
                self.check_periodic(x)
            #
            # min/max
            #
            debug('Looking for local min/max for: '+str(expr))
            f1 = diff(expr, 'x')
            x = fsolve(f1)
            for xc in x:
                y = expr.subs('x', xc)
                yc = rfc(y)
                if yc is not None:
                    self.poi.append(POI(xc, yc, 4))
                    debug('Added local min/max at ('+str(xc)+','+\
                            str(yc)+')')
            if self.trigonometric and not self.periodic and \
                    not self.polynomial:
                debug('Checking if function is periodic using'+\
                        ' min/max.')
                self.check_periodic(x)
            #
            # inflection points
            #
            debug('Looking for inflection points for: '+str(expr))
            f2 = diff(f1, 'x')
            x = fsolve(f2)
            for xc in x:
                y = expr.subs('x', xc)
                yc = rfc(y)
                if yc is not None:
                    self.poi.append(POI(xc, yc, 5))
                    debug('Added inflection point at ('+\
                            str(xc)+','+str(yc)+')')
            if self.trigonometric and not self.periodic and \
                    not self.polynomial:
                debug('Checking if function is periodic using'+\
                        ' inflection points.')
                self.check_periodic(x)
            #
            # vertical asymptotes
            #
            debug('Looking for vertical asymptotes for: '+str(expr))
            x = pod(expr, 'x')
            for i in x:
                y = expr.subs('x', i)
                xc = rfc(i)
                #yc = float(y) # this returns inf.
                # we'll just put vertical asymptotes on the x axis
                if xc is not None:
                    yc = 0
                    self.poi.append(POI(xc, yc, 6))
                    debug('Added vertical asymptote ('+str(xc)+','+\
                            str(yc)+')')
            if self.trigonometric and not self.periodic and \
                    not self.polynomial:
                debug('Checking if function is periodic using'+\
                        ' vertical asymptotes.')
                self.check_periodic(x)
            #
            # horizontal asymptotes
            #
            # if the limit(x->+oo)=a, or limit(x->-oo)=a, then
            # y=a is a horizontal asymptote.
            debug('Looking for horizontal asymptotes for: '+\
                    str(expr))
            try:
                lr = limit(expr, 'x', 'oo')
                ll = limit(expr, 'x', '-oo')
                if 'oo' not in str(lr):
                    debug('Found a horizontal asymptote at y='+\
                            str(lr)+' as x->+oo.')
                    self.poi.append(POI(0, lr, 7))
                if 'oo' not in str(ll):
                    if ll == lr:
                        debug('Same horizontal asymptote as x->-oo.')
                    else:
                        debug('Found a horizontal asymptote at y='+\
                                str(ll)+' as x->-oo')
                        self.poi.append(POI(0, ll, 7))
            except NotImplementedError:
                debug('NotImplementedError for finding limit of "'+\
                        str(expr)+'"')
            # if the function was not found to be periodic yet, try
            # some common periods
            if self.trigonometric and not self.periodic and \
                    not self.polynomial:
                self._test_common_periods()

    def check_periodic(self, x):
            l = len(x)
            if l > 1:
                for i in range(0,l-1):
                    if not self.periodic:
                        for j in range(1, l):
                            if not self.periodic:
                                for n in range(1,11):
                                    if not self.periodic:
                                        period = abs(n*(x[j] - x[i]))
                                        self._test_period(period)

    def _test_period(self, period):
        if period != 0:
            pf = self.simp_expr.subs('x', 'x+period')
            pf = pf.subs('period', period)
            pf = simplify(pf)
            g = simplify(str(self.simp_expr)+'-('+str(pf)+')')
            if g == 0:
                debug('Function is periodic and has a period of '+\
                        str(period)+'. Smaller periods may exist.')
                self.periodic = True
                self.period = period

    # checks the functions for some common periods
    # multiples of 0.25 (up to 1)
    # multiples of 1 (up to 4)
    # multiples of pi/4 (up to 2*pi)
    # multiples of pi (up to 4*pi)
    def _test_common_periods(self):
        debug('Trying some common periods to determine if '+\
                'function is periodic')
        period_list = []
        for i in np.arange(pi, 5*pi, pi):
            period_list.append(i)
        for i in np.arange(1, 5, 1):
            period_list.append(i)
        for i in np.arange(pi/4, 2*pi+pi/4, pi/4):
            period_list.append(i)
        for i in np.arange(0.25, 1.25, 0.25):
            period_list.append(i)
        for period in period_list:
            if not self.periodic:
                self._test_period(period)

    def _check_trigonometric(self):
        e = str(self.simp_expr)
        # only test for periods for trig functions
        if 'sin(' in e or 'cos(' in e or 'tan(' in e or \
                'cot(' in e or 'sec(' in e or 'csc(' in e:
            self.trigonometric = True
            debug('Function could be periodic.')
        else:
            self.trigonometric = False
            debug('Function cannot be periodic.')

    def __init__(self, expr, xylimits):
        # the number of points to calculate within the graph using
        # the function
        self.resolution = 1000
        self.visible = True
        self.constant = False
        self.valid = True
        self.polynomial = False
        self.trigonometric = False
        self.periodic = False
        self.period = None
        self.expr = self._get_expr(expr)
       
        # simplifying helps with functions like y=x^2/x which is
        # actually just y=x. Doesn't hurt in any case.
        # Also throws an error in case there are syntax problems
        try:
            self.simp_expr = self._simplify_expr(self.expr)
            # expression as used by numpy
            self.np_expr = self._get_np_expr(str(self.simp_expr))
            self.valid = self.update_graph_points(xylimits)
        except:
            self.valid = False
        self.poi = []

        if self.valid:
            self.mathtex_expr = \
                    self._get_mathtex_expr(self.simp_expr)
            self.polynomial = self.simp_expr.is_polynomial()
            if not self.polynomial:
                self._check_trigonometric()
            self.calc_poi()

