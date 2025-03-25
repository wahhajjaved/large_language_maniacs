# JiJiDinBenDon
# Copyright (C) 2015 TheKK <thumbd03803@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

import requests
import json
from bs4 import BeautifulSoup
import re

BENDON_SITE = "https://dinbendon.net"

"""
Formats
=======

    self.menu_ = {
        "items": [
           { "name": XXX, "price": XXX },
           ...
           ],
        "qtyInputs": [
            { "name": XXX, "qty": XXX }, #name, is the name of input section
            ...
        ],
        "commentInputs": [
            { "name": XXX, "comment": XXX }, #name, is the name of input section
            ...
        ],
        "userInput": XXX,
        "urlToPost": XXX

"""
class Menu(object):
    def __init__(self, session, url):
        self.menu_ = {}
        self.userNameForOrdering = ""

        orderReq = session.get(url)
        soup = BeautifulSoup(orderReq.text, 'lxml')
        self.menu_['items'] = []
        self.menu_['qtyInputs'] = []
        self.menu_['commentInputs'] = []
        self.menu_['userInput'] = soup.find('table', 'lists').find('input')['name']
        self.menu_['urlToPost'] = BENDON_SITE + soup.find('form', id='addOrderItemForm')['action']
        self.priceInputUrl = ""
        self.variationPriceChosen = 0;

        for i in soup.find_all('tr', ['odd', 'even']):
            name = i.find('td', 'productName').div.string
            price = i.find('td', 'variationPrice').string
            priceInputUrl = ""
            qtyInputName = i.find('td', 'qtyColumn').find('input')['name']
            commentInputName = i.find('td', 'commentColumn').find('input')['name']

            # Multiple prices
            if price is None:
                price = []
                for label in i.find('td', 'variationPrice').find_all('label'):
                    price.append(label)

                priceInputUrl = i.find('td', 'variationPrice').find('input')["name"]

            item = {
                     "name": name,
                     "price": price,
                     "priceInput": priceInputUrl
                   }
            qtyInput = {
                         "name": qtyInputName,
                         "qty" : ''
                       }
            commentInput = {
                             "name": commentInputName,
                             "comment": ""
                           }

            self.menu_['items'].append(item)
            self.menu_['qtyInputs'].append(qtyInput)
            self.menu_['commentInputs'].append(commentInput)

    def getItemList(self):
        return self.menu_["items"]

    def setVariationPrice(self, item, priceIndex):
        if type(priceIndex) is not type(666):
            raise Exception("input priceIndex is not number")

        self.priceInputUrl = item["priceInput"]
        self.variationPriceChosen = priceIndex

    def setItemQty(self, item, qty):
        if type(qty) is not type(666):
            raise Exception("input qty is not number")

        index = self.menu_["items"].index(item)
        self.menu_['qtyInputs'][index]["qty"] = str(qty)

    def setItemComment(self, item, comment):
        index = self.menu_["items"].index(item)
        self.menu_['commentInputs'][index]["comment"] = str(comment)

    def setNameForOrdering(self, name):
        self.userNameForOrdering = name

    def sendOrder(self, session):
        urlToPost = self.menu_['urlToPost']

        payload = {}
        payload[self.menu_['userInput']] = self.userNameForOrdering
        payload['addOrderItemForm:hf:0'] = ""

        for qtyInput in self.menu_["qtyInputs"]:
            payload[qtyInput["name"]] = str(qtyInput["qty"])

        for commentInput in self.menu_["commentInputs"]:
            payload[commentInput["name"]] = str(commentInput["comment"])

        if self.priceInputUrl:
            payload[self.priceInputUrl] = self.variationPriceChosen

        session.post(urlToPost, data=payload)

class Detail(object):
    def __init__(self, session, url):
        self.detail_ = {}

        orderReq = session.get(url)
        soup = BeautifulSoup(orderReq.text, 'lxml')
        self.detail_["yourOrders"] = []

        # tr here is in the form of:
        #
        # product name / No of items / Unit price / Who order ...
        # AAA          / 1           / 30         / a / b / c ...
        # AAA          / 1           / 30         / a / b / c ...
        #
        for tr in soup.find('table', 'tiles mergeView').find_all('tr'):
            if tr.find('td', 'deletable') is None:
                continue

            productName = tr.find('td', 'mergeKey').div.string
            price = tr.find_all('td')[2].div.string
            nameUsedForOrdering = tr.find('td', 'deletable').div.span.a.span.string
            urlToPost = BENDON_SITE + tr.find('td', 'deletable').div.span.a['href']
            if tr.find('span', 'count'):
                numYouOrder = tr.find('span', 'count').string.strip('x')
            else:
                numYouOrder = 1

            yourOrder = {
                          "productName": productName,
                          "price": price,
                          "qty": numYouOrder,
                          "nameForOrdering": nameUsedForOrdering,
                          "urlToPostToCancelOrdering": urlToPost
                        }

            self.detail_["yourOrders"].append(yourOrder)

    def getOrderingDetails(self):
        return self.detail_["yourOrders"]

    def hasOrderd(self):
        return (len(self.detail_["yourOrders"]) != 0)

    def deleteOrdering(self, session, ordering):
        index = self.detail_["yourOrders"].index(ordering)
        urlToPost = self.detail_["yourOrders"][index]["urlToPostToCancelOrdering"]

        session.post(urlToPost)

class BenDonSession(object):
    def __init__(self):
        self.session = requests.Session()

    def login(self, username, password):
        r = self.session.get(BENDON_SITE + "/do/login")
        soup = BeautifulSoup(r.text, 'lxml')
        urlToPost = BENDON_SITE + soup.find('form', id='signInPanel_signInForm')['action']

        # Since cpacha here is the form of '1+49=', we can easily get result
        capcha = soup.select('td')[6].text.rstrip('=')
        exec('result = %s' % capcha)

        data = {
                "username":username,
                "password":password,
                "result":str(result),
                "submit":"login",
                "rememberMeRow:rememberMe":"on",
                "signInPanel_signInForm:hf:0":""
        }

        self.session.post(urlToPost, data=data)

        return self.session.cookies.get('INDIVIDUAL_KEY')

    def getInProgressOrderings(self):
        r = self.session.get(BENDON_SITE + "/do")
        soup = BeautifulSoup(r.text, 'lxml')
        urlsToReturn = []

        for dom in soup.find_all('tr', id=re.compile('inProgressBox_inProgressOrders_\d+')):
            AllA = dom.find_all('a')
            if not len(AllA) == 4:
                continue

            creator = AllA[2].find_all('span')[0].string
            shopName = AllA[2].find_all('span')[1].string
            count = AllA[0].find('span').string
            detailUrl = BENDON_SITE + AllA[2]['href']
            orderUrl = BENDON_SITE + AllA[3]['href']

            inProgressOrdering = {
                                   "creator": creator,
                                   "shopName": shopName,
                                   "count": count,
                                   "detailUrl": detailUrl,
                                   "orderUrl": orderUrl
                                 }

            urlsToReturn.append(inProgressOrdering)

        return urlsToReturn

    def loadCookies(self, filePath):
        cookieDict = {}
        with open(filePath, "r") as fp:
            cookieDict = json.load(fp)
        self.session.cookies = requests.utils.cookiejar_from_dict(cookieDict)

    def saveCookies(self, filePath):
        cookieDict = requests.utils.dict_from_cookiejar(self.session.cookies)
        with open(filePath, "w") as fp:
            fp.write(json.dumps(cookieDict))
