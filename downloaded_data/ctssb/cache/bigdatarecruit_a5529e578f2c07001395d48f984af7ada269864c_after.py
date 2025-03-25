# -*- coding: utf-8 -*-
import scrapy
from scrapy.http import Request,FormRequest
from scrapy import signals
from scrapy import Spider
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from tools.seleniumTest import lagouLogin
from tools.getFilterName import getHotCity,getAllCatchCity,getSickCity
from tools.seleniumTest import platformJudge
from RecruitSpider.items import LagouItem,LagouItemLoader
from urllib import parse
import json
import requests
import time
import sys

class LagouSpider(Spider):
    name = 'lagou'
    allowed_domains = ['www.lagou.com']
    start_urls = ['https://www.lagou.com/jobs/allCity.html?px=new&city=%E5%8C%97%E4%BA%AC']
    number = 0
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6',
        'Referer': 'https://www.lagou.com/jobs/list_?px=new&city=%E5%85%A8%E5%9B%BD',
        'Origin': 'https://www.lagou.com',
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.101 Safari/537.36",
        'X-Anit-Forge-Code': '0',
        'X-Anit-Forge-Token': 'None',
        'X-Requested-With': 'XMLHttpRequest'
    }

    def __init__(self, **kwargs):
        super(LagouSpider,self).__init__()
        # 谷歌浏览器
        # 如果是linux环境 则开启无界面
        if 'linux' in sys.platform:
            from pyvirtualdisplay import Display
            self.display = Display(visible=0,size=(1024,768))
            self.display.start()

        chrome_opt = Options()
        prefs = {"profile.managed_default_content_sttings.images": 2}
        chrome_opt.add_experimental_option("prefs", prefs)
        chrome_opt.add_argument("--no-sandbox")
        chrome_opt.add_argument("--disable-setuid-sandbox")

        driver_path = platformJudge()
        self.browser = webdriver.Chrome(driver_path, chrome_options=chrome_opt)

    # 爬虫信号绑定
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(LagouSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_close, signals.spider_closed)
        return spider

    def spider_close(self, spider):
        print('spider close')
        self.browser.quit()
        if 'linux' in sys.platform:
            self.display.stop()

    def start_requests(self):
        cookies = lagouLogin('dict', self.browser)
        # city_hot = getHotCity()
        # city_all_catch = getAllCatchCity()
        city_sick = getSickCity()
        yield Request('https://www.lagou.com/jobs/allCity.html?px=new&city=%E5%8C%97%E4%BA%AC',cookies=cookies,meta={'city_filter': city_sick })

    # 进入城市列表
    def parse(self, response):
        city_parent = response.xpath("//table[contains(@class,'word_list')]/tr")

        for city_node in city_parent:
            city_initial = city_node.xpath("td[1]/div/span/text()").extract_first()
            city_initial_part = city_node.xpath("td[2]/ul/li")
            city_total_num = len(city_parent.xpath("td[2]/ul/li"))
            for city_part in city_initial_part :
                city_name = city_part.xpath('a/text()').extract_first()
                url = city_part.xpath('input/@value').extract_first()
                # 组装接口链接
                city_str = {"city": city_name}
                url_city_str = parse.urlencode(city_str)
                url = 'https://www.lagou.com/jobs/positionAjax.json?px=new&' + url_city_str + '&needAddtionalResult=false&isSchoolJob=0'
                query_data = {'first': 'false', 'pn': '1', 'kd': ''}
                if city_name in response.meta.get('city_filter'):
                    yield FormRequest(url=url, headers=self.headers, callback=self.positionList, formdata=query_data, method="POST", meta={'city_name': city_name, 'city_initial': city_initial, 'city_total_num': city_total_num})

    # 进入职位列表页
    def positionList(self,response):
        self.number += 1
        # print(str(self.number) + ': ' + response.meta.get('city_name'))
        # 组装接口链接
        city_str = {"city": response.meta.get('city_name')}
        url_city_str = parse.urlencode(city_str)
        url = 'https://www.lagou.com/jobs/positionAjax.json?px=new&' + url_city_str + '&needAddtionalResult=false&isSchoolJob=0'

        res = json.loads(response.body.decode('utf-8'))

        if res['msg']:
            print( 'Yes: ' + str(res))

        if res["success"] and res['content']['pageNo'] != 0:
            hrInfoMap = res['content']['hrInfoMap']
            positionResult = res['content']['positionResult']['result']
            totalNum = res['content']['positionResult']['totalCount']

            print(response.meta.get('city_name') + " " + str(totalNum) + ' ' + str(res['content']['pageNo']))

            for item in positionResult:
                # 如果不是今天发布的，则跳过
                t = time.strptime(item['createTime'], "%Y-%m-%d %H:%M:%S")
                date_cur = t[0] * 10000 + t[1] * 100 + t[2]
                date_cur_comp = int(time.strftime('%Y%m%d', time.localtime()))
                # 2为当天 1为非当天
                status = 2 if date_cur == date_cur_comp else 1
                if status:
                    url_detail = "https://www.lagou.com/jobs/" + str(item["positionId"]) + '.html'
                    positionId = str(item["positionId"])
                    hrInfo = hrInfoMap[positionId]
                    yield Request(url=url_detail, meta={"hrInfoMap": hrInfo, 'positionInfo': item, 'city_initial': response.meta.get('city_initial'), 'total_num': totalNum}, callback=self.positionDetail)
            # 如果下一页还有职位
            if totalNum > 15 * int(res['content']['pageNo']):
                curNum = res['content']['pageNo'] + 1
                query_data = {'first': 'false', 'pn': str(curNum), 'kd': ''}
                yield FormRequest(url=url, headers=self.headers, callback=self.positionList, formdata=query_data, method="POST", meta={'city_name': response.meta.get('city_name'), 'city_initial': response.meta.get('city_initial')})


    # 职位详情页
    def positionDetail(self,response):
        item_loader = LagouItemLoader(item=LagouItem(),response=response)
        positionInfo = response.meta.get('positionInfo')
        hrInfo = response.meta.get('hrInfoMap')

        # print("抓取职位详情页面")
        # print(positionInfo['city'] + '： ' + positionInfo['positionName'])

        item_loader.add_value('cityInitial',response.meta.get('city_initial') if response.meta.get('city_initial') else 'NULL')
        item_loader.add_value('cityTotalNum',response.meta.get('total_num'))

        item_loader.add_value('url', response.url)
        item_loader.add_value('positionName',positionInfo['positionName'])
        item_loader.add_value('positionId', positionInfo['positionId'])
        item_loader.add_value('positionLabels', positionInfo['positionLables'] if positionInfo['positionLables'] else 'NULL')
        item_loader.add_value('salary', positionInfo['salary'])
        item_loader.add_value('workYear', positionInfo['workYear'])
        item_loader.add_value('education', positionInfo['education'])
        item_loader.add_value('jobNature', positionInfo['jobNature'])
        item_loader.add_value('firstType', positionInfo['firstType'])
        item_loader.add_value('secondType', positionInfo['secondType'])
        item_loader.add_value('city', positionInfo['city'])
        item_loader.add_value('district', positionInfo['district'] if positionInfo['district'] else 'NULL')

        item_loader.add_value('companyId', positionInfo['companyId'])
        item_loader.add_value('companyFullName', positionInfo['companyFullName'])
        item_loader.add_value('companyShortName', positionInfo['companyShortName'])
        item_loader.add_value('companySize', positionInfo['companySize'] if positionInfo['companySize'] else 'NULL')
        item_loader.add_value('companyLogo', 'https://www.lagou.com/' + positionInfo['companyLogo'])
        item_loader.add_value('industryField', positionInfo['industryField'] if positionInfo['industryField'] else 'NULL')
        item_loader.add_value('financeStage', positionInfo['financeStage'] if positionInfo['financeStage'] else 'NULL')

        item_loader.add_value('publisherId', positionInfo['publisherId'])
        item_loader.add_value('publishTime', positionInfo['createTime'])
        item_loader.add_value('positionAdvantage', positionInfo['positionAdvantage'] if positionInfo['positionAdvantage'] else 'NULl')
        location = response.xpath("//div[@class='work_addr']").xpath('string(.)').extract_first()
        item_loader.add_value('location', location if location else 'NULL')
        item_loader.add_xpath('department', "//div[@class='company']/text()")
        describe = response.css('.job_bt div').extract_first()
        item_loader.add_value('describe',describe if describe else 'NULL')

        item_loader.add_value('hrPortrait', hrInfo['portrait'] if hrInfo['portrait'] else 'NULL')
        item_loader.add_value('hrPositionName', hrInfo['positionName'] if hrInfo['positionName'] else 'NULL')
        item_loader.add_value('hrRealName', hrInfo['realName'])
        item_loader.add_xpath('hrActiveTime', "//div[@class='publisher_data']/div[3]/span[3]/text()")
        hr_connect_url = "https://www.lagou.com/scanCode/positionChat.html?positionId={0}&publishUserId={1}".format(positionInfo['positionId'],positionInfo['publisherId'])
        item_loader.add_value('hrConnectionLagou', hr_connect_url)
        lagou_item = item_loader.load_item()
        yield lagou_item