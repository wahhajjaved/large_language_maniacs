#add third party libs 
import sys
sys.path.insert(0, 'libs')

import webapp2
import jinja2
import os

from GChartWrapper import *
from utils import render_str
from db import dmv
from google.appengine.ext import ndb
from google.appengine.ext.ndb import Query

class MainPage(webapp2.RequestHandler):
    
    def get(self):
        self.response.headers['Content-Type'] = 'text/html'

        template_values = {
                        "chart_src": "../static/images/icon1.jpg"
                        }
        self.response.write(render_str("home.html", template_values))
class WaitTimeQuery(webapp2.RequestHandler):
    
    def post(self):
        self.response.headers['Content-Type'] = 'text/html'
        office = self.request.get("office")
        weekday = self.request.get("weekday")
        
        q = dmv.DMV.query().filter(ndb.GenericProperty('dmv_id') == office).filter(ndb.GenericProperty('weekday') == int(weekday)).order( -ndb.GenericProperty('sample_tm'))
        rst = q.fetch()

        node_appt = []
        node_nonappt = []
        node_sample_tm = []

        for r in rst:
            node_appt.append(int(r.appt_wait_mins))
            node_nonappt.append(int(r.non_appt_wait_mins))
            node_sample_tm.append( int(r.sample_tm.minute) + int(r.sample_tm.hour)*60)

        G = LineXY( [ 
                   node_sample_tm, # x values
                   node_appt, # y values, etc.
                   node_sample_tm,
                   node_nonappt,
                   
                  ])
        G.color('green', red)
        G.line(4, 4)
        G.size(600, 300)
        G.axes('xy')
        G.scale(*[480, 1020, 0, 120] * 2)
        G.axes.label(0, '8AM', '9', '10', '11', '12PM', '1', '2', '3', '4', '5PM')
        G.axes.label(1, 0,30,60,90,120)
        G.marker('fMax','red',0,19,10)
        G.line(2,4,1)

        self.response.write(str(G))


        
