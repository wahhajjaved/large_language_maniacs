# -*- coding: utf-8 -*-
import scrapy

from scrapy.spider import BaseSpider
from scrapy.selector import HtmlXPathSelector
from scrapy.http import Request,FormRequest
from scrapy.conf import settings
from scrapy.selector import Selector
from scrapy import log
from scrapy.shell import inspect_response


import leancloud
from leancloud import Object
from leancloud import LeanCloudError
from leancloud import Query

from datetime import datetime
from zhQuesFollower import settings

from zhQuesFollower.items import ZhquesfollowerItem
import bmemcached
import re

import json
import redis

class QuesfollowerSpider(scrapy.Spider):
    name = "quesFollower"
    allowed_domains = ["www.zhihu.com"]
    baseUrl = "http://www.zhihu.com/question/"
    start_urls = (
        'http://www.zhihu.com/',
    )
    questionIdList = []
    questionFollowerCountList = []
    questionInfoList = []
    quesIndex =0
    reqLimit =20
    pipelineLimit = 100000
    threhold = 100
    handle_httpstatus_list = [401,429,500]
    #handle_httpstatus_list = [401,429,500]





    def __init__(self,stats):

        self.stats = stats
        print "Initianizing ....."
        #log.start()
        # leancloud.init(settings.APP_ID_S, master_key=settings.MASTER_KEY_S)


        # client_2 = bmemcached.Client(settings.CACHE_SERVER_2,settings.CACHE_USER_2,settings.CACHE_PASSWORD_2)
        # client_4 = bmemcached.Client(settings.CACHE_SERVER_4,settings.CACHE_USER_4,settings.CACHE_PASSWORD_4)
        #

        redis0 = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_USER+':'+settings.REDIS_PASSWORD,db=0)
        redis2 = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_USER+':'+settings.REDIS_PASSWORD,db=2)
        dbPrime = 97
        self.questionIdList = redis0.hvals('questionIndex')

        # for questionId in self.questionIdList:
        #     print "askfor followerCount %s"  %str(questionId)
        #     self.questionFollowerCountList.ex(redis2.lindex(str(questionId),4))

        # dbPrime = 97
        # totalCount = int(client_2.get('totalCount'))
        # for questionIndex in range(0,totalCount):
        #     self.questionIdSet.add(int(client_2.get(str(questionIndex))[0]))

            #貌似这样占用的内存太多了
        p2 = redis2.pipeline()
        for index ,questionId in enumerate(self.questionIdList):
            p2.lindex(str(questionId),4)
            if index%self.pipelineLimit ==0:
                self.questionFollowerCountList.extend(p2.execute())
                p2 = redis2.pipeline()
                # print "length of questionFollowerCountList: %s\n" %str(len(self.questionFollowerCountList))





            # if questionInfo:
            #     if int(questionInfo[4])>self.threhold:
            #
            #         self.questionIdList.append([questionId,questionInfo[4]])
            #     else:
            #         pass
            # else:
            #     pass

        # self.questionInfoList.append([20769127,838])


    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.stats)

    def start_requests(self):
        print "start_requests ing ......"
        yield Request("http://www.zhihu.com/",callback = self.post_login)

    def post_login(self,response):
        print "post_login ing ......"
        xsrfValue = response.xpath('/html/body/input[@name= "_xsrf"]/@value').extract()[0]
        yield FormRequest.from_response(response,
                                          #headers = self.headers,
                                          formdata={
                                              '_xsrf':xsrfValue,
                                              'email':'heamon8@163.com',
                                              'password':'heamon8@()',
                                              'rememberme': 'y'
                                          },
                                          dont_filter = True,
                                          callback = self.after_login,
                                          )





    def after_login(self,response):
        print "after_login ing ....."
        print self.questionInfoList
        #inspect_response(response,self)
        #inspect_response(response,self)
        #self.urls = ['http://www.zhihu.com/question/28626263','http://www.zhihu.com/question/22921426','http://www.zhihu.com/question/20123112']
        for index ,questionId in enumerate(self.questionIdList):
            if self.questionFollowerCountList[index]:
                xsrfValue = response.xpath('/html/body/input[@name= "_xsrf"]/@value').extract()[0]

                reqUrl = self.baseUrl+str(questionId)+'/followers'

                reqTimes = (self.questionFollowerCountList[index]+self.reqLimit-1)/self.reqLimit
                for index in reversed(range(reqTimes)):
                    # print "request index: %s"  %str(index)
                    yield FormRequest(url =reqUrl,
                                              #headers = self.headers,
                                              metadata={'offset':self.reqLimit*(index +1)},
                                              formdata={
                                                  '_xsrf':xsrfValue,
                                                  'start':'0',
                                                  'offset':str(self.reqLimit*index),
                                              },
                                              dont_filter = True,
                                              callback = self.parsePage
                                              )


    def parsePage(self,response):


        if response.status != 200:
            # print "ParsePage HTTPStatusCode: %s Retrying !" %str(response.status)
            yield Request(response.url,callback=self.parsePage)
        else:

            item =  ZhquesfollowerItem()

    #         if response.status != 200:
    # #            print "ParsePage HTTPStatusCode: %s Retrying !" %str(response.status)
    #             yield  self.make_requests_from_url(response.url)
    #
    #         else:

           # inspect_response(response,self)
            data = json.loads(response.body)
            userCountRet = data['msg'][0]
            # print "userCountRet: %s" %userCountRet
            if userCountRet:
                sel = Selector(text = data['msg'][1])
                item['offset'] = response.meta['offset']
                item['questionId'] = re.split('http://www.zhihu.com/question/(\d*)/followers',response.url)[1]
                item['userDataIdList'] = sel.xpath('//button/@data-id').extract()
                item['userLinkList'] = sel.xpath('//a[@class="zm-item-link-avatar"]/@href').extract()
                item['userImgUrlList'] = sel.xpath('//a[@class="zm-item-link-avatar"]/img/@src').extract()
                item['userNameList'] = sel.xpath('//h2/a/text()').extract()
                item['userFollowersList'] = sel.xpath('//div[@class="details zg-gray"]/a[1]//text()').extract()
                item['userAskList'] = sel.xpath('//div[@class="details zg-gray"]/a[2]//text()').extract()
                item['userAnswerList'] = sel.xpath('//div[@class="details zg-gray"]/a[3]//text()').extract()
                item['userUpList'] = sel.xpath('//div[@class="details zg-gray"]/a[4]//text()').extract()

            yield item







    def closed(self,reason):
        #f = open('../../nohup.out')
        #print f.read()
        leancloud.init(settings.APP_ID, master_key=settings.MASTER_KEY)


        CrawlerLog = Object.extend('CrawlerLog')
        crawlerLog = CrawlerLog()

        crawlerLog.set('crawlerName',self.name)
        crawlerLog.set('closedReason',reason)
        crawlerLog.set('crawlerStats',self.stats.get_stats())
        try:
            crawlerLog.save()
        except:
            pass


