# -*- coding: utf-8 -*-

import twitter
import requests
import pymongo
#import os
import sys
from pymongo import MongoClient
from ConfigParser import SafeConfigParser

from scrapper import flipkart_scrapper, amazon_scrapper, snapdeal_scrapper
from utils import removeURLencoding , find_domain , unshorten_url


 #1. Fetch Twitter Data
####################Fetch Data for Mentions on TwitterHandle
def get_Twdata( api):
    mentions=api.GetMentions( )   
    print ""
    for mention in mentions:
        msg =  mention.text
        status_id =  mention.id
        url = msg[15:]
        #url = "https://www.flipkart.com/hp-1-tb-wired-external-hard-disk-drive/p/itmebqdzrfdyy6h4"
        #url= "http://www.amazon.in/Sanyo-inches-XT-43S7100F-Full-Black/dp/B01ICVLK4S?_encoding=UTF8&deviceType=desktop&ref_=br_isw_strs-1"
        #url = "https://www.snapdeal.com/product/micromax-spark-vdeo-q15-8gb/636218001907"
        screen_name = mention.user.screen_name

        try:
            url = unshorten_url(url)
            url = removeURLencoding(url)
            domain = find_domain(url)

            if domain== 'www.flipkart.com':
                scrapped = flipkart_scrapper(url) 
                price = scrapped[0]
                item   = scrapped[1]
                found = scrapped[2]

            elif domain== 'www.amazon.in':
                scrapped = amazon_scrapper(url)
                price = scrapped[0]
                item   = scrapped[1]
                found = scrapped[2]

            elif domain== 'www.snapdeal.com':
                scrapped = snapdeal_scrapper(url)
                price = scrapped[0]
                item   = scrapped[1]
                found = scrapped[2]
            else :
                raise NotImplementedError ("This domain is not supported yet in our system. Be back Later !")


            #proceed only if scrapped data has been found     
            if found :
                #post tweet only if it is new    
                isnew = mongo_post(status_id, screen_name, url, price, item, domain)
                if isnew:
                    Tw_post(api, screen_name, price,  status_id, item, domain)

        except requests.exceptions.MissingSchema:
            print "Tweet status doesnt have any url"
            sys.stdout.flush()    


#3.Post to MongoDb
####################
def mongo_post(status_id, screen_name, url, price, item, domain):   
    parser = SafeConfigParser( )
    parser.read('config.ini')
    is_replied = False
    connection = MongoClient(parser.get('mongo_server', 'mongo_url'))
   # connection = os.environ['mongo_url']

    db = connection.pricechanger.tweet

    #create unique Index on database
    #db.createIndex( { "status_id": 1 }, { unique: true } )
    '''db.create_index(
    [("status_id", pymongo.ASCENDING)],
    unique=True
     )'''

     #ensure_index seems to work better than create_index
    db.ensure_index('status_id', unique=True)
    print "status id :", status_id 

    pricechanger ={ }    
    pricechanger = {'status_id':status_id, 'url':url, 'screen_name':screen_name, 'price':int(price), 'item':item, 'domain':domain, 'is_replied':is_replied}
    # Item name converted to Binary  to prevent loss  of the non utf-8 characters [Mongo supports only utf-8 encoding]
    print "status id :", status_id  #Debug


    try:
        db.insert_one(pricechanger)
    except pymongo.errors.DuplicateKeyError:
        print "Duplicate Entry  for same Status Id"
        return False

    print "Data Posted to Database ..."
    sys.stdout.flush()
    return True
    #connection.close()


#4. Post Reply to Twitter Mentions
################################
def Tw_post( api, screen_name, price,  status_id, item, domain):
    try:
        status = api.PostUpdate( str("@"+screen_name) + "  Initial Price of " + item[:85] + " on " + domain +" is Rs. " +str(price),in_reply_to_status_id=str(status_id))
        print status.text
        print "Posted on Twitter"
        sys.stdout.flush()
    except twitter.error.TwitterError:
        print "Item price already twitted !!"
        sys.stdout.flush()



#Set up twitter API data from config file
#############################################################
def initial():
    sys.stdout.flush()
    parser = SafeConfigParser()
    parser.read('config.ini')
    print "Running parser"

    #Read api from env variable
    '''api = twitter.Api(consumer_key = os.environ['consumer_key'],    
                      consumer_secret = os.environ['consumer_secret'],
                      access_token_key =  os.environ['access_token_key'],
                      access_token_secret =  os.environ['access_token_secret'])'''

    #read API data from 'config.ini'  file
    api = twitter.Api(consumer_key = parser.get('twitter_API', 'consumer_key'),
                      consumer_secret = parser.get('twitter_API', 'consumer_secret'),
                      access_token_key = parser.get('twitter_API', 'access_token_key'),
                      access_token_secret = parser.get('twitter_API', 'access_token_secret'))

    get_Twdata(api) 
