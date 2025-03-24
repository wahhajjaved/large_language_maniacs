#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import os, time
import datetime, pytz, dateutil.parser
import re

def print_todays_agenda():
    force_update = False
    _args = os.sys.argv
    for _arg in _args:
        if _arg == 'force':
            force_update = True

    tzobj = pytz.timezone("US/Eastern")
    TAG_RE = re.compile(r'<[^>]+>')

    def remove_html_tags(text):
        #''.join(xml.etree.ElementTree.fromstring(text).itertext())
        return TAG_RE.sub('',text)

    class calendar_event:
        def __init__(self, dt=datetime.datetime.now(tzobj)):
            self.event_time = dt
            self.title = None
            self.description = None
            self.eventId = None

        def read_gcal_event(self, obj):
            if 'start' in obj:
                if 'dateTime' in obj['start']:
                    tstr = obj['start']['dateTime']
                    self.event_time = dateutil.parser.parse(tstr)
            if 'summary' in obj:
                self.title = obj['summary']
            if 'description' in obj:
                self.description = remove_html_tags(obj['description'])
            self.eventId = obj['id']

        def print_event(self):
            outstr = ['']
            outstr.append(self.event_time.strftime('%Y-%m-%dT%H:%M:%S%z'))
            if self.title: outstr.append('\t summary: %s' % self.title)
            if self.description: outstr.append('\t description: %s' % self.description.replace('\n',' ').replace('  ',' '))
            outstr.append('')
            return '\n'.join(outstr)

    def process_response(response, outlist):
        for item in response['items']:
            t = calendar_event()
            t.read_gcal_event(item)
            kstr = '%s %s' % (t.event_time, t.eventId)
            outlist[kstr] = t

    def get_agenda():
        outstr = []
        from gcal_instance import gcal_instance
        gcal = gcal_instance()
        exist = gcal.get_gcal_events(calid='ddboline@gmail.com', callback_fn=process_response, do_single_events=True)
        for k in sorted(exist.keys()):
            e = exist[k]
            if e.event_time > datetime.datetime.now(tzobj) + datetime.timedelta(days=1):
                continue
            elif e.event_time > datetime.datetime.now(tzobj):
                outstr.append(e.print_event())
        return '\n'.join(outstr)

    cachefile = '/tmp/.todays_agenda.tmp'
    def convert_time_date(st):
        t0 = time.gmtime(st)
        return datetime.date(year=t0.tm_year, month=t0.tm_mon, day=t0.tm_mday)

    if not os.path.exists(cachefile) or convert_time_date(time.time()) > convert_time_date(os.stat(cachefile).st_mtime) or force_update:
        f = open(cachefile, 'w')
        f.write(get_agenda())
        f.close()
    f = open(cachefile, 'r')
    outstr = f.readlines()
    f.close()
    return ''.join(outstr)

if __name__ == '__main__':
    print(print_todays_agenda())
