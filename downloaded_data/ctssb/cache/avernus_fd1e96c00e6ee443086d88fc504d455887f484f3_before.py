#!/usr/bin/env python

from urllib import urlopen
import csv, pytz
from datetime import datetime
import time


def __request(symbol, stat):
    url = 'http://finance.yahoo.com/d/quotes.csv?s=%s&f=%s' % (symbol, stat)
    return urlopen(url)


def update_stocks(stocks):
    symbols = ''
    for stock in stocks:
        symbols+= stock.yahoo_symbol+'+'
    symbols = symbols.strip('+')
    
    s = 0
    res = __request(symbols, 'l1d1d3c1')
    for row in csv.reader(res):
        stocks[s].price = float(row[0])
        try:
            date = datetime.strptime(row[1] + ' ' + row[2], '%m/%d/%Y %H:%M%p')
        except:
            date = datetime.strptime(row[1], '%m/%d/%Y')
        date = pytz.timezone('US/Eastern').localize(date)
        stocks[s].date = date.astimezone(pytz.utc)
        stocks[s].date = stocks[s].date.replace(tzinfo = None)
        stocks[s].change = float(row[3])
        s+=1
             
               
def get_info(symbol):
    #name, isin, exchange, currency
    for row in csv.reader(__request(symbol, 'nxc4')):
        if row[1] == 'N/A':
            return None
        return row[0], 'n/a', row[1], row[2]
        
def test_api(symbol):
    for row in csv.reader(__request(symbol, 'nxc4n0n1n2n3n4')):
        print row
     
def check_symbol(symbol):
    return __request(symbol, 'e1').read().strip().strip('"') == "N/A"
    

def get_historical_prices(stock, start_date, end_date):
    """
    Get historical prices for the given ticker symbol.
    Returns a nested list.
    """
    symbol = stock.yahoo_symbol
    #print "fetch data", start_date, end_date
    url = 'http://ichart.yahoo.com/table.csv?s=%s&' % symbol + \
          'd=%s&' % str(start_date.month-1) + \
          'e=%s&' % str(start_date.day) + \
          'f=%s&' % str(start_date.year) + \
          'g=d&' + \
          'a=%s&' % str(end_date.month-1) + \
          'b=%s&' % str(end_date.day) + \
          'c=%s&' % str(end_date.year) + \
          'ignore=.csv'
    #print url
    days = urlopen(url).readlines()
    data = []
    
    for row in [day[:-2].split(',') for day in days[1:]]:
        #print row[0]
        dt = datetime.strptime(row[0], '%Y-%m-%d')
        data.append((dt, float(row[1]), float(row[2]), float(row[3]), float(row[6]), int(row[5])))

    data.reverse()
    return data #(date, open, high, low, close, vol)        , Adj. Schluss


if __name__ == "__main__":
    
    test_api('cbk.de')
    #print check_symbol('ge.de')

