import numpy as np
import pandas as pd
import math

import pandas.io.data as pdata
from datetime import timedelta, date
from visu import plot_orders
from util.cache import DataCache

# little hack to make in working inside heroku submodule
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../'))

log_momentum = lambda previous: round(math.log(1+2*abs(previous))+1)
double_momentum = lambda previous: 2*abs(previous)
exp_momentum = lambda previous: round(math.pow(abs(previous), 2))
no_momentum = lambda previous:round(abs(previous))

import abc

class Strategy:
    __metaclass__ = abc.ABCMeta
    field = 'Close'
    datacache = DataCache()

    @abc.abstractmethod
    def apply(self, stock, data=None):
        """ return buy(1) or sell(-1) """
        return

    @classmethod
    def optimal(cls, stock, start, end=None, charts=True, verbose=False):
        ''' start is a datetime or nb days prior to now '''
        start, end = cls.get_start_end(start, end)
        # add required padding 
        data = cls.datacache.DataReader(stock, "yahoo",
                                        start=start-timedelta(days=cls.window),
                                        end=end)
        n = len(data)
        orders = cls.orders_from_trends(data[cls.field], segments=n/5, window=7, charts=charts)
        return orders, data[-n:]
        

    @classmethod
    def get_start_end(cls, start, end=None):
        end = end if end!=None else date.today()-timedelta(days=1)
        if isinstance(start, int):
            start = end-timedelta(days=start)
        return start, end

    @classmethod
    def simulate(cls, stock, start, end=None, charts=True, verbose=False):
        ''' start is a datetime or nb days prior to now '''
        start, end = cls.get_start_end(start, end)
        # add required padding 
        data = cls.datacache.DataReader(stock, "yahoo",
                                        start=start-timedelta(days=cls.window),
                                        end=end)
                                
        n = len(data)-cls.window+1
        orders=np.zeros(n)
       
        # ensure orders[0]=0 (initial point)
        for i in range(1,  n):
            start_i = start+timedelta(days=-cls.window+i)
            end_i = start+timedelta(days=i)
            data_i = data[start_i:end_i]
            order = cls.apply(stock, data_i)
            orders[i]=order
            if verbose:
                print end_i+timedelta(days=1), order
        
        if charts:
            p = data[cls.field][-n:]
            plot_orders(p, orders, stock + " (raw orders)")
            
        return orders, data[-n:]    
       
    @classmethod
    def orders_from_trends(cls, x, segments=2, window=7, charts=True):
        ''' generate orders from segtrends '''
        from filter import movingaverage
        from trendy import segtrends
        x_maxima, maxima, x_minima, minima = segtrends(x, segments, charts, window)
        n = len(x)
        y = np.array(x)
        movy = movingaverage(y, window)
        
        # generate order strategy
        orders = np.zeros(n)
        last_buy = y[0]
        last_sale = y[0]
        
        for i in range(1,n):
            # get 2 latest support point y values prior to x
            pmin = list(minima[np.where(x_minima<=i)][-2:])
            pmax = list(maxima[np.where(x_maxima<=i)][-2:])
            # sell if support slop is negative
            min_sell = True if ((len(pmin)==2) and (pmin[1]-pmin[0])<0) else False 
            max_sell = True if ((len(pmax)==2) and (pmax[1]-pmax[0])<0) else False 
            
            # if support down, sell
            buy = -1 if (min_sell and max_sell) else 0
            # buy only if lower the moving average else sale
            buy = 1 if ((buy == 0) and (y[i]<movy[i])) else -1
            # sell only if ...
            buy= -1 if ((buy == -1) and y[i]>last_buy) else 1
            
            buy_price_dec = y[i]<last_buy
            sale_price_dec = y[i]<last_sale
            orders[i] = buy
            last_buy = y[i] if (buy==1) else last_buy
            last_sale = y[i] if (buy==-1) else last_sale
        
        # OUTPUT
        return orders
    
