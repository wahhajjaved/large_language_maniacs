# -*- coding: utf-8 -*-
from BeautifulSoup import BeautifulSoup
from urllib import urlopen
import csv, pytz, re, os, pickle
from datetime import datetime
from stocktracker import logger, config

logger = logger.logger

TYPES = ['Fonds', 'Aktie']

class Yahoo():
    name = "yahoo"

    def __init__(self):
        self.__load_yahoo_ids()
    
    def __request(self, searchstring):
        try:
            url = 'http://de.finsearch.yahoo.com/de/index.php?nm='+searchstring+'&tp=*&r=*&sub=Suchen'
            logger.info(url)
            return urlopen(url)
        except:
            return None
                
    def __request_csv(self, symbol, stat):
        try:
            url = 'http://finance.yahoo.com/d/quotes.csv?s=%s&f=%s' % (symbol, stat)
            logger.info(url)
            return urlopen(url)
        except:
            return None
        
    def __get_yahoo_ids(self, stocks):
        ids = []
        for stock in stocks:
            try:
                #TODO always uses first yahoo id in cache, maybe could use some heuristic to choose a better exchange (e.g. highest volume)
                ids.append(self.yahoo_ids[(stock.isin, stock.currency)][0])
            except:
                print "no yahoo id cached"
                #TODO try to get it!
        return '+'.join(ids)

    def update_stocks(self, stocks):
        ids = self.__get_yahoo_ids(stocks)
        s = 0
        res = self.__request_csv(ids, 'l1d1d3c1x')
        for row in csv.reader(res):
            if len(row) > 1:
                if row[1] == 'N/A':
                    s+=1
                    continue 
                try:
                    stocks[s].price = float(row[0])
                except Exception as e:
                    logger.info(e)
                    continue
                try:
                    date = datetime.strptime(row[1] + ' ' + row[2], '%m/%d/%Y %H:%M%p')
                except Exception as e:
                    logger.info(e)
                    date = datetime.strptime(row[1], '%m/%d/%Y')
                date = pytz.timezone('US/Eastern').localize(date)
                date = date.astimezone(pytz.utc)
                stocks[s].date = date.replace(tzinfo = None)
                stocks[s].change = float(row[3])
                stocks[s].exchange = row[4]
                stocks[s].updated = True
                s+=1
                         
    def get_info(self, symbol):
        #name, isin, exchange, currency
        for row in csv.reader(self.__request_csv(symbol, 'nxc4')):
            if len(row) < 2 or row[1] == 'N/A':
                return None
        return row[0], 'n/a', row[1], row[2]
        
    def _test_api(self, symbol):
        for row in csv.reader(self.__request_csv(symbol, 'nxc4n0n1n2n3n4')):
            print row
    
    def update_historical_prices(self, stock, start_date, end_date):
        id = self.__get_yahoo_ids([stock])
        logger.debug("fetch data"+ str(start_date)+ str(end_date))
        url = 'http://ichart.yahoo.com/table.csv?s=%s&' % id + \
              'd=%s&' % str(start_date.month-1) + \
              'e=%s&' % str(start_date.day) + \
              'f=%s&' % str(start_date.year) + \
              'g=d&' + \
              'a=%s&' % str(end_date.month-1) + \
              'b=%s&' % str(end_date.day) + \
              'c=%s&' % str(end_date.year) + \
              'ignore=.csv'
        days = urlopen(url).readlines()
        data = []
        for row in [day[:-2].split(',') for day in days[1:]]:
            dt = datetime.strptime(row[0], '%Y-%m-%d').date()
            #(stock, date, open, high, low, close, vol)
            yield (stock,dt,float(row[1]),float(row[2]),\
                        float(row[3]),float(row[6]), int(row[5]))
            
    def search(self, searchstring):
        doc = self.__request(searchstring)
        if doc is None:
            return
        #1. beatifull soup does not like this part of the html file
        #2. remove newlines
        my_massage = [(re.compile('OPTION VALUE=>---------------------<'), ''), \
                      (re.compile('\n'), '')]
        soup = BeautifulSoup(doc, markupMassage=my_massage)
        for main_tab in soup.findAll('table', width="752"):
            for table in main_tab.findAll('table', cellpadding='3', cellspacing='1',width='100%'):
                for row in table('tr'):
                    item = []
                    for s in row('td', {'class':'yfnc_tabledata1'}, text=True):
                        s = s.strip()
                        if s is not None and s!=unicode(''):
                            item.append(s)
                    if len(item) == 12:
                        item = self.__to_dict(item[:-2])
                        if item is not None:
                            if (item['isin'],item['currency']) in self.yahoo_ids.keys():
                                if not item['yahoo_id'] in self.yahoo_ids[(item['isin'],item['currency'])] :
                                    self.yahoo_ids[(item['isin'],item['currency'])].append(item['yahoo_id'])
                            else:
                                self.yahoo_ids[(item['isin'],item['currency'])] = [item['yahoo_id']]
                            yield (item, self)
        self.__save_yahoo_ids()
    
    def __parse_price(self, pricestring):
        if pricestring[-1] == '$':
            price = pricestring[:-1]
            cur = '$'
        elif pricestring[-1] == 'p':
            price = pricestring[:-1]
            cur = 'GBPp'
        else:
            price, cur = pricestring.strip(';').split('&')
            if cur == 'euro':
                cur = 'EUR'
        return float(price), cur
    
    def __parse_change(self, changestring, price):
        return price - (price*100 / (100 + float(changestring.strip('%'))))
                    
    def __to_dict(self, item):
        if not item[5] in TYPES:
            return None
        res = {}
        res['name']                   = item[0]
        res['yahoo_id']               = item[1]
        res['isin']                   = item[2]
        res['wkn']                    = item[3]
        res['exchange']               = item[4]
        res['type']                   = TYPES.index(item[5])
        res['price'], res['currency'] = self.__parse_price(item[6])
        #res['time']                   = item[7]  #only time not date
        res['change']                 = self.__parse_change(item[8], res['price'])
        res['volume']                 = int(item[9].replace(",", ""))
        return res
    
    
    #FIXME since yahoo.py is now part of the main program, we should store
    #the ids in the db. or not?
    
    def __load_yahoo_ids(self):
        path = os.path.join(config.config_path, 'yahoo_ids')
        if os.path.isfile(path):
            with open(path, 'r') as file:
                data = pickle.load(file)
                if type(data) == type(dict()):
                    self.yahoo_ids = data
        else:
            self.yahoo_ids = {}

    def __save_yahoo_ids(self):
        path = os.path.join(config.config_path, 'yahoo_ids')
        with open(path, 'wb') as file:
             pickle.dump(self.yahoo_ids, file)


if __name__ == '__main__':
    y = Yahoo()
    for item in y.search('yahoo'):
        print item
        break
