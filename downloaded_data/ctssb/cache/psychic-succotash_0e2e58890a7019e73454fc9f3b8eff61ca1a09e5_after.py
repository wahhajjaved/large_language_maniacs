from django.shortcuts import render
from django.utils import timezone
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse

# Create your views here.

import time, requests, re, os
from datetime import datetime
import bs4

from .models import File, Route, Stop, Prediction

cwd = os.getcwd()
routeReg = re.compile(r'routeTitle="(\d+)"')

def mode():
    #toggles mode based on time and day
    now = timezone.now()
    wday = now.strftime('%w')
    h = now.strftime('%p')
    #print(wday)
    #print(h)
    if (wday == '1' or wday == '2' or wday == '3' or wday == '4' or wday == '5') and h == 'AM':
        mode = 1
    else:
        mode = 2
    return mode

def grabber(stop):
    x = 0
    now = timezone.now()
    feed = requests.get('http://webservices.nextbus.com/service/publicXMLFeed?command=predictions&a=mbta&stopId=' + stop)
    if feed.status_code == requests.codes.ok:
        f_path = cwd+'/buslog/bus-'+str(stop)+'.xml'
        xml = open(f_path, 'w')
        xml.write(feed.text)
        xml.close()
        f = File(path=f_path)
        f.save
    return f_path

def bus_update(request):
    stops = Stop.objects.all()
    for s in stops:
        path = grabber(s.stop_tag)
        xmlf = open(path, 'r')
        xml = xmlf.read()
        soup = bs4.BeautifulSoup(xml, 'xml')
        preds = soup.find_all('predictions')
        for p in preds:
            p_dict = dict(p.attrs)
            if 'dirTitleBecauseNoPredictions' in p_dict:
                direct = p_dict['dirTitleBecauseNoPredictions']
                print('No buses to '+direct)
                r, c = Route.objects.get_or_create(agency=p_dict['agencyTitle'], route_title=p_dict['routeTitle'], route_tag=p_dict['routeTag'])
                s = Stop.objects.get(stop_tag=p_dict['stopTag'])
                s.stop_title = p_dict['stopTitle']
                b = Prediction(route=r, stop=s, direction=direct)
                r.save()
                s.save()
                b.save()
            else:
                dr = p.direction
                if dr != None:
                    dr_dict = dr.attrs
                    pred = dr.find_all('prediction')
                    for pe in pred:
                        pre_dict = dict(pe.attrs)
                        print('Bus to '+dr_dict['title']+' in '+str(pre_dict['seconds'])+' seconds.')
                        r, c = Route.objects.get_or_create(agency=p_dict['agencyTitle'], route_title=p_dict['routeTitle'], route_tag=p_dict['routeTag'])
                        s = Stop.objects.get(stop_tag=p_dict['stopTag'])
                        s.stop_title = p_dict['stopTitle']
                        b = Prediction(route=r, stop=s, direction=dr_dict['title'],
                                    dir_tag=pre_dict['dirTag'], arr_sec=int(pre_dict['seconds']),
                                    vehic=pre_dict['vehicle'], trip=pre_dict['tripTag'], block=pre_dict['block'])
                                    #add layover
                                    #add departr
                                    #add time
                        r.save()
                        s.save()
                        b.save()

    return HttpResponseRedirect(reverse('bus:bus'))


def bus(request):
    p = Prediction.objects.all()
    for item in p:
        p.arr_time = round(p.arr_sec / 60, 2)
    context = {'pred': p}
    return render(request, 'bus/bus.html', context)

def data(request):
    return render(request, 'bus/bus.html')
