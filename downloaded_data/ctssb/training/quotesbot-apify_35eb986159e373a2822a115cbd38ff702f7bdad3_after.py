# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

from py2_apify import ApifyClient

class QuotesbotToDataset(object):
    
    def __init__(self):
        self.apify_client = ApifyClient()
        
    @classmethod
    def from_crawler(cls, crawler):
        print('initializing #############################################################################')
        return cls()

    def process_item(self, item, spider):
        print('############################################')
        self.apify_client.pushRecords( {'data': item} )
        return item
