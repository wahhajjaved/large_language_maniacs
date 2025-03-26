#!/usr/bin/env python
# encoding: utf-8

"""
@author: amigo
@contact: 88315203@qq.com
@phone: 15618318407
@software: PyCharm
@file: sogou_spider.py
@time: 2017/11/22 下午6:26
"""
import os

import scrapy


class SogouSpider(scrapy.Spider):
    name = 'sogou'
    urls = ['https://pinyin.sogou.com/dict/cate/index/360',  # 城市信息
            'https://pinyin.sogou.com/dict/cate/index/1',  # 自然科学
            'https://pinyin.sogou.com/dict/cate/index/76',  # 社会科学
            'https://pinyin.sogou.com/dict/cate/index/96',  # 工程应用
            'https://pinyin.sogou.com/dict/cate/index/127',  # 农林渔畜
            'https://pinyin.sogou.com/dict/cate/index/132',  # 医学医药
            'https://pinyin.sogou.com/dict/cate/index/436',  # 电子游戏
            'https://pinyin.sogou.com/dict/cate/index/154',  # 艺术设计
            'https://pinyin.sogou.com/dict/cate/index/389',  # 生活百科
            'https://pinyin.sogou.com/dict/cate/index/367',  # 运动休闲
            'https://pinyin.sogou.com/dict/cate/index/31',  # 人文科学
            'https://pinyin.sogou.com/dict/cate/index/403',  # 娱乐休闲
            ]
    total_page = 300

    def start_requests(self):
        for url in self.urls:
            for i in range(self.total_page):
                yield scrapy.Request(url + '/default/' + str(i + 1),
                                     callback=self.parse_channel,
                                     dont_filter=True)

    def parse_channel(self, response):
        for sel in response.xpath("//div[@class='dict_detail_block']"):
            title = sel.xpath("div/div[@class='detail_title']/a/text()").extract()
            url = sel.xpath("div/div[@class='dict_dl_btn']/a/@href").extract()
            title = title[0]
            url = url[0]
            meta = {'title': title}
            yield scrapy.Request(url,
                                 callback=self.parse,
                                 meta=meta,
                                 dont_filter=True)

    def parse(self, response):
        _path = os.path.dirname(os.getcwd())+'/hub/'
        if not os.path.exists(_path):
            os.mkdir(_path)
        file_path = _path  + response.meta['title'] + '.scel'
        # print 'file_path:', file_path
        with open(file_path, 'w') as f:
            f.write(response.body)
