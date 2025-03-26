#
# Copyright 2008, Blue Dynamics Alliance, Austria - http://bluedynamics.com
#
# GNU General Public Licence Version 2 or later

__author__ = """Robert Niederreiter <rnix@squarewave.at>"""
__docformat__ = 'plaintext'

from zope.interface import implements
from zope.component import adapter
from zope.component import getUtilitiesFor
from zope.event import notify

from interfaces import ConflictingHotspot
from interfaces import IHotspot
from interfaces import IHotspotCheck
from interfaces import IHotspotHitEvent

from base import XBrowserView

class HotspotHitEvent(object):
    """IHotspotHitEvent implementation.
    """
    
    implements(IHotspotHitEvent)
    
    def __init__(self, context, request, hotspoturl):
        self.context = context
        self.request = request
        self.hotspoturl = hotspoturl


class Hotspot(object):
    """IHotspot implementation.
    """
    
    implements(IHotspot)
    
    def __init__(self, obj, interface, resource, considerparams):
        self.obj = obj
        self.interface = interface
        self.resource = resource
        self.considerparams = considerparams
    
    def weight(self, obj, request):
        weight = 0
        if self.obj:
            if isinstance(obj, self.obj):
                weight += 1
        if self.interface:
            if self.interface.providedBy(obj):
                weight += 1
        if self.resource:
            url = request['ACTUAL_URL']
            if url.find('/%s' % self.resource) != -1:
                weight += 1
        return weight


class HotspotCheck(XBrowserView):
    """IHotspotCheck implementation.
    """
    
    implements(IHotspotCheck)
    
    def __call__(self):
        hotspots = getUtilitiesFor(IHotspot, self.context)
        
        possible = list()
        for hotspot in hotspots:
            if hotspot[1].weight(self.context, self.request) > 0:
                possible.append(hotspot[1])
        if not possible:
            return True
        possible.sort(cmp=lambda x, y: x.weight < y.weight and -1 or 1)
        
        lastweight = 0
        for hotspot in possible:
            currentweight = hotspot.weight
            if currentweight == lastweight:
                raise ConflictingHotspot(u"More than one hotspot definition "
                                         "matching requested resource.")
            lastweight = currentweight
        
        hotspot = possible[0]
        resource = None
        if hotspot.resource:
            resource = hotspot.resource
        
        consider = list()
        if hotspot.considerparams:
            consider += hotspot.considerparams
        if len(possible) > 1:
            for hotspot in possible[1:]:
                if hotspot.considerparams:
                        consider += hotspot.considerparams
        
        query = self.makeQuery(considerexisting=False,
                               considerspecific=consider)
        hotspoturl = self.makeUrl(resource=resource, query=query)
        notify(HotspotHitEvent(self.context,
                               self.request,
                               hotspoturl))
        return True


@adapter(IHotspotHitEvent)
def writeHotspotUrlToCookie(event):
    """Default IHotspotHitEvent subscriber.
    
    Write hotspot url to cookie.
    """
    request = event.request
    url = event.hotspoturl
    request.response.setCookie('hotspoturl', url)
