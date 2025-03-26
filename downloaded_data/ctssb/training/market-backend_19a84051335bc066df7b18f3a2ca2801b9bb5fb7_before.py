import simplejson as json

from flask.ext.api import status
import flask as fk

from marketdb.common import crossdomain
from market import app, SERVICE_URL, service_response, get_user_city, get_country, get_one_number, get_cities, menu
from marketdb.common.models import Market
from time import gmtime, strftime

import mimetypes
import traceback
import datetime
import random
import string
from io import StringIO
import hashlib
import phonenumbers
from phonenumbers.phonenumberutil import region_code_for_country_code
from phonenumbers.phonenumberutil import region_code_for_number
import pycountry

from geopy import geocoders
from tzwhere import tzwhere
from pytz import timezone
import pytemperature
from translate import Translator

@app.route(SERVICE_URL + '/menu', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def service_menu():
    if fk.request.method == 'GET':
        return service_response(200, 'Service Menu', menu())
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/history/<country>/<city>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def market_by_city(country, city):
    if fk.request.method == 'GET':
        if city == 'all':
            if country == 'all':
                markets = [m.info() for m in Market.objects()]
            else:
                markets = [m.info() for m in Market.objects(country=country)]
        else:
            markets = [b.info() for c in Market.objects(city=city.lower(), country=country)]
        return service_response(200, 'City: {0} of Country: {1} market history'.format(city.lower(), country), {'size':len(markets), 'history':markets})
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/today/<country>/<city>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def market_today_city(country, city):
    if fk.request.method == 'GET':
        _country = get_country(country)
        if _country is None:
            return service_response(204, 'Unknown country', 'We could not find this country.')
        else:
            lat = _country["lat"]
            lng = _country["lng"]
            if lat == "":
                lat = 0.00
                lng = 0.00
            tz = tzwhere.tzwhere()
            timeZoneStr = tz.tzNameAt(lat, lng)
            timeZoneObj = timezone(timeZoneStr)
            now_time = datetime.datetime.now(timeZoneObj)
            day = str(now_time).split(" ")[0]
            if city == 'all':
                if country == 'all':
                    markets = [c.info() for c in Market.objects(day=day)]
                else:
                    markets = [c.info() for c in Market.objects(day=day, country=country)]
            else:
                markets = [c.info() for c in Market.objects(day=day, city=city.lower(), country=country)]
            return service_response(200, 'City: {0} of Country: {1} market today: {2}'.format(city.lower(), country, day), {'size':len(markets), 'today':markets})
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/message/delete/<market_id>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def delete_market(market_id):
    if fk.request.method == 'GET':
        _market = Market.objects.with_id(market_id)
        if _market:
            _market.delete()
            return service_response(200, 'Deletion succeeded', 'Market {0} deleted.'.format(market))
        else:
            return service_response(204, 'Unknown market', 'No corresponding market found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/message/send', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def message_send():
    if fk.request.method == 'POST':
        if fk.request.data:
            print(fk.request.data)
            data = json.loads(fk.request.data, encoding='utf-16')
            sender = data.get('sender', None)
            content = data.get('content', None)

            if sender is None and content is None:
                return service_response(405, 'Message send denied', 'A message has to contain a sender number and a content.')
            else:
                pn = phonenumbers.parse(sender, None)
                country = str(pn.country_code)
                _country = get_country(country)
                if _country is None:
                    return service_response(204, 'Unknown country', 'We could not find this country.')
                else:
                    lat = _country["lat"]
                    lng = _country["lng"]
                    if lat == "":
                        lat = 0.00
                        lng = 0.00
                    tz = tzwhere.tzwhere()
                    timeZoneStr = tz.tzNameAt(lat, lng)
                    timeZoneObj = timezone(timeZoneStr)
                    now_time = datetime.datetime.now(timeZoneObj)
                    day = str(now_time).split(" ")[0]
                    date = datetime.datetime.strptime(day, "%Y-%m-%d")
                    ignore, language = get_cities(country)
                    translator = Translator(to_lang=language)
                    city = get_user_city(country, sender)
                    if city is None:
                        return service_response(405, translator.translate('Message send denied'), translator.translate('You must register first to our servcies. Send us your city to +12408052607'))

                    markets_to_send = Market.objects(sender=sender, city=city.lower(), country=country,  day=day)
                    for mark in markets_to_send:
                        if mark.message == content:
                            return service_response(204, translator.translate('Message not saved'), translator.translate('You have already sent this message today.'))
                    if len(markets_to_send) == 10:
                        return service_response(204, translator.translate('Message not saved'), translator.translate('You have already sent 10 messages today.'))

                    market = Market(created_at=str(datetime.datetime.utcnow()), sender=sender, city=city.lower(), country=country, day=day)
                    market.message = content
                    market.save()
                    return service_response(200, translator.translate('Your message was received'), translator.translate('Message recieved. It will be on the market soon.'))
        else:
            return service_response(204, 'User registration failed', 'No data submitted.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a POST method.')

@app.route(SERVICE_URL + '/message/pushing/<country>/<city>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def market_pushing_country(country, city):
    if fk.request.method == 'GET':
        _country = get_country(country)
        if _country is None:
            return service_response(204, 'Unknown country', 'We could not find this country.')
        else:
            lat = _country["lat"]
            lng = _country["lng"]
            if lat == "":
                lat = 0.00
                lng = 0.00
            tz = tzwhere.tzwhere()
            timeZoneStr = tz.tzNameAt(lat, lng)
            timeZoneObj = timezone(timeZoneStr)
            now_time = datetime.datetime.now(timeZoneObj)
            day = str(now_time).split(" ")[0]
            date = datetime.datetime.strptime(day, "%Y-%m-%d")

            if city == "all":
                market_pulled = Market.objects(country=country, status='pulled', day=day).first()
            else:
                market_pulled = Market.objects(city=city.lower(), country=country, status='pulled', day=day).first()
            if market_pulled:
                market_pulled.status = 'pushing'
                market_pulled.save()
                ignore, language = get_cities(country)
                market_pushing =market_pulled.info()
                translator = Translator(to_lang=language)
                market_pushing["message"] = translator.translate(market_pushing["message"])
                return service_response(200, translator.translate('Market in () today {0}:'.format(day)), market_pushing)
            else:
                return service_response(204, 'No market to send', "no market at this point.")
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/message/pushed/<market_id>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def pushed_market(market_id):
    if fk.request.method == 'GET':
        _market = Market.objects.with_id(market_id)
        if _market:
            _market.status = 'pushed'
            _market.save()
            return service_response(200, 'Market pushed', 'Market {0} was confimed pushed.'.format(market_id))
        else:
            return service_response(204, 'Unknown market', 'No corresponding market found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')
