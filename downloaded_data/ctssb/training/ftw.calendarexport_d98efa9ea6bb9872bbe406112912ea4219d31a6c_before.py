from Products.ATContentTypes.interface.interfaces import ICalendarSupport
from plone.memoize import ram
from plonegov.pdflatex.browser.converter import LatexCTConverter
from Products.CMFCore.utils import getToolByName
from Products.ATContentTypes.lib import calendarsupport as cs
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.app.layout.viewlets import ViewletBase
from Acquisition import aq_inner
from Products.ATContentTypes.browser.calendar import CalendarView, cachekey

class ExportEvents(ViewletBase):
    render = ViewPageTemplateFile('export.pt')

    def active(self):
        props = getToolByName(self.context, 'portal_properties').calendarexport_properties
        return props.getProperty('active')


class ExportICS(CalendarView):

    def update(self):
        context = aq_inner(self.context)
        catalog = getToolByName(context, 'portal_catalog')
        provides = ICalendarSupport.__identifier__
        uids = self.request.form.get('uids',[])
        self.events = catalog(UID=uids, object_provides=provides)
        if not uids:
            self.events = []

    @ram.cache(cachekey)
    def feeddata(self):
        context = aq_inner(self.context)
        data = cs.ICS_HEADER % dict(prodid=cs.PRODID)
        for brain in self.events:
            tmp_data = brain.getObject().getICal()
            if brain.wholeDay:
                lines = tmp_data.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('DTSTART'):
                        lines[i] = 'DTSTART:%s' % str(brain.start).replace('/','')
                    elif line.startswith('DTEND'):
                        lines[i] = 'DTEND:%s' % str((context.end()+1).Date()).replace('/', '')
                        lines[i] += '\nTRANSP:OPAQUE'
                tmp_data = '\n'.join(lines)
            data += tmp_data
        data += cs.ICS_FOOTER
        return data


class EventsAsPDF(LatexCTConverter):

    def __call__(self, context, view):
        def date(date):
            return view.convert(context.toLocalizedTime(date, long_format=1))
        self.view = view
        catalog = getToolByName(self.context, 'portal_catalog')
        latex = []
        for brain in catalog(dict(UID=self.request.form.get('uids', []))):
            latex.append(r'\textbf{%s}\\' % view.convert(brain.Title))
            if brain.start and brain.end:
                latex.append(r'%s - %s\\' % (date(brain.start),
                                             date(brain.end)))
            latex.append(r'%s\\' % view.convert(brain.Description))
            latex.append(r'\\')
        return '\n'.join(latex)
