# -*- coding: utf-8 -*-
import datetime
from math import radians, cos, sin, asin, sqrt

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

from social_auth.models import UserSocialAuth

from backend.models import *
from api.serializers import *

class JSONResponse(HttpResponse):
    """
    An HttpResponse that renders its content into JSON.
    """
    def __init__(self, data, **kwargs):
        content = JSONRenderer().render(data)
        kwargs['content_type'] = 'application/json'
        super(JSONResponse, self).__init__(content, **kwargs)


from social.apps.django_app.utils import strategy
@strategy()
def auth_by_token(request, backend):
    backend = request.strategy.backend

    try:
        user = backend.do_auth(
            access_token=request.POST.get('access_token', '').strip()
            )
    except Exception as err:
        print err
        user = None

    if user and user.is_active:
        return user# Return anything that makes sense here
    else:
        return None


@csrf_exempt
def check_binding(request):
    """
    Test if a social user has authendicated
    """
    if request.method == 'POST':
        uid = request.POST.get('uid', '').strip()
        provider = request.POST.get('provider', '').strip()
        access_token = request.POST.get('access_token', '').strip()
        print "access_token is :"
        print access_token

        auths = UserSocialAuth.objects.filter(uid=uid, provider=provider)

        if auths.count() != 0:
            user_social_auth = auths[0]
            bindings = Binding.objects.filter(user=user_social_auth.user)
        else:
            user = auth_by_token(request, provider)
            # if user:
                # strategy = load_strategy(request=request, backend=backend)
                # _do_login(strategy, user)
            bindings = Binding.objects.filter(user=user)

        serializer = BindingSerializer(bindings, many=True)
        return JSONResponse(serializer.data)

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    # 6367 km is the radius of the Earth
    km = 6367 * c
    return km

def pretty_date(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime
    from django.utils import timezone
    # now = datetime.now()
    now = timezone.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " sec ago"
        if second_diff < 120:
            return  "a minute ago"
        if second_diff < 3600:
            return str( second_diff / 60 ) + " min ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str( second_diff / 3600 ) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff/7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff/30) + " months ago"
    return str(day_diff/365) + " years ago"

def computeDistance(from_binding, to_binding):

    from_locations = Location.objects.filter(binding=from_binding).order_by('-create_time')
    to_locations = Location.objects.filter(binding=to_binding).order_by('-create_time')

    if from_binding == to_binding:
        return('0.00km', 'now', to_locations[0].longitude, to_locations[0].latitude)

    if len(to_locations) > 0:

        from_loc = from_locations[0]
        to_loc = to_locations[0]

        distance = haversine(float(from_loc.longitude), float(from_loc.latitude), float(to_loc.longitude),
                float(to_loc.latitude))
        distance = "%.2fkm" % distance
        appear_time = pretty_date(to_loc.create_time)

        return (distance, appear_time, to_loc.longitude, to_loc.latitude)

    else:
        return ('no data', 'no data', '0', '0')

def bind_school(school):
    import urllib2
    import json
    import re

    if school.sid:
        r = urllib2.urlopen('http://graph.facebook.com/'+school.sid)
        o = json.loads(r.read())
        school_link = o.get('link', None)
        if school_link:
            r = urllib2.urlopen(school_link)
            school_search = re.search('window\.location\.replace\("(.*)\?rf=[0-9]*"\)', r.read(), re.IGNORECASE)

            if school_search:
                school_link = school_search.group(1).replace("\/", "/")
                # school.fblink = school_search.group(1).replace("\/", "/")
                # school.save()
            else:
                ### this school is the final link
                # school.ref = school
                # school.fblink = school_link
                # school.save()
                print 'redirect link not found'

            ref_school = School.objects.filter(fblink=school_link)
            if len(ref_school) > 0:
                school.ref = ref_school[0]
            else:
                school.fblink = school_link
                school.ref = school

            school.save()

        else:
            return
    else:
        return


@csrf_exempt
def nearby_users(request):
    '''
    get nearby users by client locations
    '''

    if request.method == 'POST':
        bindingId = request.POST.get('bindingId', '').strip()
        longitude = request.POST.get('longitude', '').strip()
        latitude = request.POST.get('latitude', '').strip()

        try:
            me = Binding.objects.get(id=bindingId)
        except Binding.DoesNotExist:
            return HttpResponse(status=status.HTTP_404_NOT_FOUND)
        except Exception,e:
            return HttpResponse(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        location = Location(
                    binding=me,
                    longitude=longitude,
                    latitude=latitude
                )
        location.save()

        ### get related users and return to clients
        my_attendances = Attendance.objects.filter(binding=me)
        nearby_bindings = {}
        for ma in my_attendances:
            ref_schools = School.objects.filter(ref=ma.school.ref)
            for s in ref_schools:
                ads = Attendance.objects.filter(school=s)
                for a in ads:
                    nearby_bindings[a.binding.id] = a.binding

        print nearby_bindings

        users = []
        for bid, binding in nearby_bindings.iteritems():
            nearby_user = binding.user
            social_auth = UserSocialAuth.objects.get(user=nearby_user)
            attendances = Attendance.objects.filter(binding=binding)
            distance, appear_time, longitude, latitude= computeDistance(me, binding)
            data = {
                    'bindingId': str(binding.id),
                    'uid': str(social_auth.uid),
                    'first_name': nearby_user.first_name,
                    'last_name': nearby_user.last_name,
                    'provider': social_auth.provider,
                    'attendances': attendances,
                    'associated_attendances': attendances,
                    'distance': distance,
                    'appear_time': appear_time,
                    'latitude': latitude,
                    'longitude': longitude
                    }
            users.append(data)

        ### sort users by distance
        users.sort(key=lambda x: x['distance'])

        # atts = Attendance.objects.filter(binding=me)
        # schools = [a.school for a in atts]
        # for s in schools:
            # bind_school(s)

        nearby_serializer = UserNearbySerializer(users, many=True)
        return JSONResponse(nearby_serializer.data)

