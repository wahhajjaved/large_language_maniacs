#!/usr/bin/env python2
# -*- coding:utf-8 -*-
import datetime, gzip, logging, os, os.path

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import numpy as np
import pandas as pd

DATA_DIR = os.environ['OPENSHIFT_DATA_DIR']

logging.basicConfig(level=logging.DEBUG, 
        filename=os.path.join(DATA_DIR, 'crawl_yahoo.log'),
        format='[%(levelname)s]: %(asctime)s %(filename)s:%(lineno)d %(message)s')

def yestoday():
    return datetime.date.today() - datetime.timedelta(1)

def _get_stock_ps(stocks):
    is_sz = lambda x: x.startswith('0') or x.startswith('3')
    is_sh = lambda x: x.startswith('6')
    for stock in stocks:
        if is_sz(stock):
            yield stock + '.sz'
        if is_sh(stock):
            yield stock + '.ss'
 
'''改写一下，直接存储到本地文件，然后再编写一下数据库相关的函数从文件中读取后入库'''

class YahooCrawler:
    '''从yahoo上下载财经数据'''
    def __init__(self, stockfile=None, db_enabled=False):
        '''stockfile: 里面存储的是沪深两市的股票代码列表,每行一支
        db_enabled: 当为真时初始化数据库，并在数据库中读取股票列表和开始结束时间'''
       
        assert(stockfile or db_enabled)

        if db_enabled:
            self.db_enabled = True
            self._init_db()
            self._get_stocks_from_db()
        else:
            self.db_enabled = False
            self._get_stocks_from_file(stockfile)
        self.crawled_data = pd.DataFrame()

   
    def _init_db(self):
        engine =  create_engine(os.environ['OPENSHIFT_POSTGRESQL_DB_URL'])
        Session = sessionmaker()
        self.session = Session(bind=engine)
    
    def _get_stocks_from_db(self):
        from dataModels import StockNew
        #result = self.session.query(StockNew.stock_code).all()
        result = self.session.query(StockNew.stock_code).filter(StockNew.stock_code.like('60000%')).limit(5)
        temp_codes = [x.stock_code for x in result]
        self.codes = list(_get_stock_ps(temp_codes))
#        logging.debug(self.codes)

    def _get_stocks_from_file(self, filename):
        with open(filename) as f:
            lines = f.readlines()

        stocks = [line.strip() for line in lines]
        self.codes = list(_get_stock_ps(stocks))
               
    @classmethod
    def crawl_yahoo_price(cls, code, start=None, end=None):
        import pandas_datareader.data as web

        try:
            logging.debug('Starting crawling %s' % code)
            data = web.DataReader(code, 'yahoo',start=start, end=end)
        except Exception as e:
            logging.error(e)
            logging.error('Error when crawl %s' % code)
            return None
       
        stock_code = code.split('.')[0]
        code_df = pd.DataFrame(data=stock_code, 
                index=data.index, columns=['stock_code'])

        data_out = pd.concat([data,code_df],axis=1)
        data_out.columns = ['open_price','high_price','low_price','close_price','volumn','adj_close', 'stock_code']
        data_out.index.name = 'trading_date'

        return data_out


    def _get_start_from_db(self):
        from dataModels import StockDayPrice

        stocks = [code.split('.')[0] for code in self.codes]
        starts = []

        for stock in stocks:
            start = self.session.query(func.max(StockDayPrice.trading_date)).filter(StockDayPrice.stock_code==stock).scalar()
            if not (start is None):
                starts.append(start)
            else:
                starts.append(start+datetime.timedelta(1))

        return starts 

    def run(self, start=None, end=None):
        if self.db_enabled:
            starts = self._get_start_from_db()
            logging.debug('starts is')
            for c, s in zip(self.codes, starts):
                logging.debug('{0}: {1}'.format(c, s))
        elif type(start) is list:
            starts = start
        else:
            starts = np.repeat(start, len(self.codes))

        if type(end) is list:
            ends = end
        else:
            ends = np.repeat(yestoday(), len(self.codes))

        for code, s, e in zip(self.codes, starts, ends):
            data = self.crawl_yahoo_price(code, s, e)
            if data is None:
                logging.warn('%s data is not crawled' % code)
                continue

            if not self.crawled_data.empty:
                self.crawled_data = pd.concat([self.crawled_data, data])
            else:
                self.crawled_data = data


    def save2pickle(self, filename):
        if not self.crawled_data.empty:
            self.crawled_data.to_pickle(filename)

    @classmethod
    def save2database(self, data):
        from dataModels import StockDayPrice

        engine = create_engine(os.environ['OPENSHIFT_POSTGRESQL_DB_URL'])
        Session = sessionmaker()
        session = Session(bind=engine)

        ins = StockDayPrice.__table__.insert()
        dicts = data.reset_index().to_dict('records')

        total_num = len(dicts)
        batch_ins = 1000
        curr = 0
        logging.debug('Total records is %d' % total_num)
        while curr<total_num:
            try:
                temp = curr + batch_ins
                if temp>total_num:
                    temp = total_num
                session.execute(ins, dicts[curr:temp])
                logging.info('{0} stock records are inserted'.format(
                    temp-curr))
                curr = temp
            except Exception as e:
                logging.error(e)
                #logging.error('Error')
                break
       
if __name__ == '__main__':
    crawler = YahooCrawler(db_enabled=True)
    start = None
    crawler.run(start=start)
    crawler.save2database(crawler.crawled_data)
