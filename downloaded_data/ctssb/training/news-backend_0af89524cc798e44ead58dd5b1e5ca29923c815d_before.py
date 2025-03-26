import simplejson as json

from flask.ext.api import status
import flask as fk

from newsdb.common import crossdomain
from news import app, SERVICE_URL, service_response, news_importance, get_one_number
from newsdb.common.models import Radio, Coverage, News
from news.crawlers.coreCrawler import CoreCawler
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

@app.route(SERVICE_URL + '/cover/add', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def add_cover():
    if fk.request.method == 'POST':
        if fk.request.data:
            data = json.loads(fk.request.data)
            name = data.get('name', None)
            country = data.get('country', None)
            radios = data.get('radios', None)
            schedule = data.get('schedule', ["6:00"])
            if name is None or country is None or radios is None:
                return service_response(405, 'Coverage addition denied', 'A coverage has to contain a name, country, radios and zone.')
            else:
                _cover = Coverage.objects(name=name, country=country).first()
                if _cover is None:
                    _cover = Coverage(updated_at=str(datetime.datetime.utcnow()))
                    _cover.name = name
                    _cover.country = country
                    _cover.radios = [Radio.objects.with_id(radio_id) for radio_id in radios]
                    _cover.schedule = schedule
                    _cover.synchronization = ["" for s in schedule]
                    _cover.delivery = ["" for s in schedule]

                    pn = phonenumbers.parse(get_one_number(country), None)
                    _country_object = pycountry.countries.get(alpha_2=region_code_for_number(pn))
                    g = geocoders.GoogleV3()
                    tz = tzwhere.tzwhere()
                    place, (lat, lng) = g.geocode(_country_object.name)
                    timeZoneStr = tz.tzNameAt(lat, lng)
                    timeZoneObj = timezone(timeZoneStr)
                    now_time = datetime.datetime.now(timeZoneObj)
                    time_block = str(now_time).split(" ")
                    if "-" in time_block[1]:
                        _cover.zone = "GMT-{0}".format(time_block[1].split("-")[1].split(":")[0])
                    if "+" in time_block[1]:
                        _cover.zone = "GMT+{0}".format(time_block[1].split("+")[1].split(":")[0])
                    _cover.save()
                    return service_response(200, 'Coverage created', 'Coverage added with success')
                else:
                    return service_response(204, 'Coverage addition denied', 'A coverage with this name, country, radios and zone already exists.')
        else:
            return service_response(204, 'Coverage addition failed', 'No data submitted.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a POST method.')

@app.route(SERVICE_URL + '/cover/edit/<cover_id>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def edit_cover(cover_id):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            if fk.request.data:
                data = json.loads(fk.request.data)
                name = data.get('name', _cover.name)
                country = data.get('country', _cover.country)
                radios = data.get('radios', _cover.radios)
                schedule = data.get('schedule', _cover.schedule)
                synchronization = data.get('sync', _cover.synchronization)
                delivery = data.get('delivery', _cover.delivery)

                _cover_check = Coverage.objects(name=name, country=country, radios=radios).first()
                if _cover_check is None:
                    _cover.name = name
                    _cover.country = country
                    pn = phonenumbers.parse(get_one_number(country), None)
                    _country_object = pycountry.countries.get(alpha_2=region_code_for_number(pn))
                    g = geocoders.GoogleV3()
                    tz = tzwhere.tzwhere()
                    place, (lat, lng) = g.geocode(_country_object.name)
                    timeZoneStr = tz.tzNameAt(lat, lng)
                    timeZoneObj = timezone(timeZoneStr)
                    now_time = datetime.datetime.now(timeZoneObj)
                    time_block = str(now_time).split(" ")
                    if "-" in time_block[1]:
                        _cover.zone = "GMT-{0}".format(time_block[1].split("-")[1].split(":")[0])
                    if "+" in time_block[1]:
                        _cover.zone = "GMT+{0}".format(time_block[1].split("+")[1].split(":")[0])
                    _cover.radios = [Radio.objects.with_id(radio_id) for radio_id in radios]
                    _cover.schedule = schedule
                    _cover.synchronization = synchronization
                    _cover.delivery = delivery
                    _cover.save()
                    return service_response(200, 'Edition succeeded', 'Coverage {0} edited.'.format(cover_id))
                else:
                    return service_response(204, 'Coverage edition denied', 'A coverage with this name, country, zone and radios already exists.')
            else:
                return service_response(204, 'Coverage edition failed', 'No data submitted.')
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/covers/country/<country>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def covers_by_country(country):
    if fk.request.method == 'GET':
        if country == 'all':
            covers = [c.info() for c in Coverage.objects()]
        else:
            covers = [c.info() for c in Coverage.objects(country=country)]
        return service_response(200, 'Country {0} coverages'.format(country), {'size':len(covers), 'covers':covers})
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/delete/<cover_id>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def delete_cover(cover_id):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            _cover.delete()
            return service_response(200, 'Deletion succeeded', 'Coverage {0} deleted.'.format(cover_id))
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/sync/<country>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def sync_cover(country):
    if fk.request.method == 'GET':
        _covers = Coverage.objects(country=country)
        pn = phonenumbers.parse(get_one_number(country), None)
        _country_object = pycountry.countries.get(alpha_2=region_code_for_number(pn))
        g = geocoders.GoogleV3()
        tz = tzwhere.tzwhere()
        place, (lat, lng) = g.geocode(_country_object.name)
        timeZoneStr = tz.tzNameAt(lat, lng)
        timeZoneObj = timezone(timeZoneStr)
        now_time = datetime.datetime.now(timeZoneObj)
        day = str(now_time).split(" ")[0]
        if "-" in str(now_time).split(" ")[1]:
            country_time = str(now_time).split(" ")[1].split("-")[0]
        if "+" in str(now_time).split(" ")[1]:
            country_time = str(now_time).split(" ")[1].split("+")[0]
        # day = str(datetime.date.today().isoformat())
        # hour = strftime("%H:%M", gmtime())
        # hour_now = int(hour.split(':')[0])
        country_hour = int(country_time.split(":")[0])
        count = 0
        _coverages = []
        for index, _cover in enumerate(_covers):
            if _cover:
                # h_align = _cover.zone.split("GMT")[1]
                data = {}
                data['coverage'] = str(_cover.id)
                data['schedule'] = _cover.schedule
                # if h_align == "":
                #     h_align = "0"
                # hour_sch = int(float(hour_now) + float(h_align))
                # if hour_sch < 0:
                #     hour_sch = 24 + hour_sch
                # elif hour_sch > 24:
                #     hour_sch = hour_sch - 24
                # print("%d:00".format(hour_sch))
                data['country-time'] = country_time
                data['radios'] = {}
                try:
                    sync_index = _cover.schedule.index("%d:00"%country_hour)
                    sync_status = _cover.synchronization[sync_index]
                    if sync_status == day: # Mean already synchronized today. skip it.
                        sync_index = -1
                except:
                    # When the time is not scheduled look for inconsistencies to fix specially
                    # in the closest lower bound scheduled time.
                    sync_index = -1
                    for index in reversed(range(len(_cover.synchronization))):
                        if country_hour > int(_cover.schedule[index].split(":")[0]):
                            if _cover.synchronization[index] != day:
                                sync_index = index
                                country_hour = int(_cover.schedule[index].split(":")[0])
                            break
                    if sync_index != -1:
                        data['comment'] = "coverage schedule %s updated"%_cover.schedule[sync_index]

                for r in _cover.radios:
                    data['radios'][r.name] = 0
                sub_count = 0
                if sync_index != -1:
                    radios = _cover.radios
                    for radio in _cover.radios:
                        crawler = CoreCawler()
                        news = crawler.fetch(radio.url)
                        for new in news:
                            _new, created = News.objects.get_or_create(coverage=_cover, radio=radio, day=day, content=new, country=_cover.country)
                            if created:
                                _new.created_at = str(datetime.datetime.utcnow())
                                _new.content = new
                                _new.schedule = "%d:00"%country_hour
                                _new.importance = news_importance(new)
                                _new.save()
                                data['radios'][radio.name] = data['radios'][radio.name] + 1
                                sub_count = sub_count + 1
                    count = count + sub_count
                    _cover.synchronization[int(sync_index)] = day
                    _cover.delivery[int(sync_index)] = 0
                    _cover.save()
                    data['status'] = 'processed'
                else:
                    data['status'] = 'skiped'
                data['news'] = sub_count
                _coverages.append(data)

        return service_response(200, 'Coverage sync succeeded', {'now-gmt': strftime("%H:%M", gmtime()), 'news':count, 'coverages':_coverages})
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/schedule/add/<cover_id>/<schedule>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def add_schedule_cover(cover_id, schedule):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            if schedule in _cover.schedule:
                return service_response(201, 'Schedule addition denied', 'There is already an existing schedule at this time.')
            else:
                try:
                    insert_idx = 0
                    sch_hour = int(schedule.split(":")[0])
                    for index, val in enumerate(_cover.schedule):
                        val_hour = int(val.split(":")[0])
                        if val_hour > sch_hour:
                            insert_idx = index
                            break
                    _cover.schedule = _cover.schedule.insert(insert_idx, schedule)
                    _cover.synchronization = _cover.synchronization.insert(insert_idx, "")
                    _cover.delivery = _cover.delivery.insert(insert_idx, "")
                    _cover.save()
                    return service_response(200, 'Schedule add succeeded', 'Coverage schedule {0} added.'.format(schedule))
                except:
                    return service_response(500, 'Schedule addition failed', 'You can only provide: %s'%str(["24:00", "1:00", "2:00", "3:00", "4:00", "5:00", "6:00", "7:00", "8:00", "9:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]))
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/schedule/delete/<cover_id>/<schedule>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def delete_schedule_cover(cover_id, schedule):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            if schedule not in _cover.schedule:
                return service_response(201, 'Schedule delete denied', 'There is no existing schedule at this time.')
            else:
                index = _cover.schedule.index(schedule)
                del _cover.schedule[index]
                del _cover.synchronization[index]
                del _cover.delivery[index]
                _cover.save()
                return service_response(200, 'Schedule delete succeeded', 'Coverage schedule {0} deleted.'.format(schedule))
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/schedule/reset/<cover_id>/<schedule>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def reset_schedule_cover(cover_id, schedule):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            if schedule not in _cover.schedule:
                return service_response(201, 'Schedule delete denied', 'There is no existing schedule at this time.')
            else:
                index = _cover.schedule.index(schedule)
                _cover.synchronization[index] = ""
                _cover.delivery[index] = ""
                _cover.save()
                return service_response(200, 'Schedule delete succeeded', 'Coverage schedule {0} deleted.'.format(schedule))
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')

@app.route(SERVICE_URL + '/cover/schedule/show/<cover_id>', methods=['GET','POST','PUT','UPDATE','DELETE'])
@crossdomain(fk=fk, app=app, origin='*')
def show_schedule_cover(cover_id):
    if fk.request.method == 'GET':
        _cover = Coverage.objects.with_id(cover_id)
        if _cover:
            data = {}
            data['schedule'] = _cover.schedule
            data['sync'] = _cover.synchronization
            data['delivery'] = _cover.delivery
            return service_response(200, 'Coverage schedule', data)
        else:
            return service_response(204, 'Unknown coverage', 'No corresponding coverage found.')
    else:
        return service_response(405, 'Method not allowed', 'This endpoint supports only a GET method.')
