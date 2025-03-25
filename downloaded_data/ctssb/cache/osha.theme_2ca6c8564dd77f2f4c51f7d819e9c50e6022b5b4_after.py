import Acquisition, re
from zope.interface import implements
from zope.component import getMultiAdapter

from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base

from zope import schema
from zope.formlib import form

from plone.memoize.instance import memoize
from plone.memoize import ram
from plone.memoize.compress import xhtml_compress

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone.app.vocabularies.catalog import SearchableTextSourceBinder
from plone.app.form.widgets.uberselectionwidget import UberMultiSelectionWidget

from Products.ATContentTypes.interface import IATDocument
from Products.CMFCore.utils import getToolByName

from osha.theme import OSHAMessageFactory as _
from plone.portlet.collection import PloneMessageFactory as _plone
from plone.app.vocabularies.catalog import SearchableTextSourceBinder, SearchableTextSource
from Products.Archetypes.interfaces import IBaseObject
from zope.app.component.hooks import getSite


from zope import component
from Acquisition import aq_inner

def get_language(context, request):
    portal_state = component.getMultiAdapter(
        (context, request), name=u'plone_portal_state')
    return portal_state.locale().getLocaleID()

def render_cachekey(fun, self):
    """
    Generates a key based on:

    * Portal URL
    * Negotiated language
    * Anonymous user flag
    * Portlet manager
    * Assignment
    * Fingerprint of the data used by the portlet
    
    """
    context = aq_inner(self.context)
    
    fingerprint = "".join(self.data.urls)

    anonymous = getToolByName(context, 'portal_membership').isAnonymousUser()

    return "".join((
        getToolByName(aq_inner(self.context), 'portal_url')(),
        get_language(aq_inner(self.context), self.request),
        str(anonymous),
        self.manager.__name__,
        self.data.__name__,
        fingerprint))
        
        

class LocalSearchableTextSourceBinder(SearchableTextSourceBinder):
    """ make the binder search in the local folder first """

    def __call__(self, context):
        site = getSite()
        portal_url = getToolByName(site, 'portal_url')
        portal = Acquisition.aq_inner(portal_url).aq_parent
        current_path = '/'+'/'.join(portal_url.getRelativeContentPath(portal.REQUEST.PARENTS[2]))
        self.default_query = 'path:%s' % current_path
        return SearchableTextSource(context, base_query=self.query.copy(),
                                    default_query=self.default_query)
                                    
class ITop5Portlet(IPortletDataProvider):
    """A portlet which shows a list of links in an order
    """

    header = schema.TextLine(title=_(u"Portlet header"),
                             description=_(u"Title of the rendered portlet"),
                             required=True)
    
    urls = schema.List(title=u"Referenced Objects",
                       description=u"Search and select the documents you want to add to your linklist. The first box contains your current selection. Below it you can do a fulltext search for documents. Below the search are the search results you can pic from. Initially they show the contents of the current folder.",
                       required=True,
                       value_type=schema.Choice(title=u"Referenced Objects",
                                                description=u"",                                                             
                                                source=LocalSearchableTextSourceBinder({'object_provides' : IBaseObject.__identifier__})
                                                             )
                                                 )
                      
class Assignment(base.Assignment):
    """
    Portlet assignment.    
    This is what is actually managed through the portlets UI and associated
    with columns.
    """

    implements(ITop5Portlet)

    header = u""
    urls=[]

    def __init__(self, header=u"", urls=[]):
        self.header = header
        self.urls = urls

    @property
    def title(self):
        """This property is used to give the title of the portlet in the
        "manage portlets" screen. Here, we use the title that the user gave.
        """
        return self.header


        
class Renderer(base.Renderer):
    """Portlet renderer.
    
    This is registered in configure.zcml. The referenced page template is
    rendered, and the implicit variable 'view' will refer to an instance
    of this class. Other methods can be added and referenced in the template.
    """

    _template = ViewPageTemplateFile('top5.pt')

    def __init__(self, *args):
        base.Renderer.__init__(self, *args)
        context = Acquisition.aq_base(self.context)
        portal_languages = getToolByName(self.context, 'portal_languages')
        self.preflang = portal_languages.getPreferredLanguage()

    @ram.cache(render_cachekey)
    def render(self):
        return xhtml_compress(self._template())


    def title(self):
        return _(self.data.header)
        
    @memoize
    def get_urls_and_titles(self):
        """ get the urls to the objects
            fall back to the canonical if language version cannot be found
        """
        results = []
        urls = self.data.urls
        if not urls:
            return results
        
        preflang = getToolByName(self.context, 'portal_languages').getPreferredLanguage()
        portal_state = getMultiAdapter((self.context, self.request), name=u'plone_portal_state')
        portal = portal_state.portal()
        portal_path = '/'.join(portal.getPhysicalPath())

        for url in urls:
            ob = portal.restrictedTraverse("%s%s" %(portal_path, url), default=None)
            if ob is None:
                continue
            tob = ob.getTranslation(preflang)
            if not tob or not tob.Title():
                tob = ob.getCanonical()
            results.append((tob.absolute_url(), tob.Title()))
        
        return results
        
        
class AddForm(base.AddForm):
    """Portlet add form.
    
    This is registered in configure.zcml. The form_fields variable tells
    zope.formlib which fields to display. The create() method actually
    constructs the assignment that is being added.
    """
    form_fields = form.Fields(ITop5Portlet)
    form_fields['urls'].custom_widget = UberMultiSelectionWidget
    
    label = _(u"Add Top5 Portlet")
    description = _(u"This portlet displays links to objects.")

    def create(self, data):
        return Assignment(**data)

class EditForm(base.EditForm):
    """Portlet edit form.
    
    This is registered with configure.zcml. The form_fields variable tells
    zope.formlib which fields to display.
    """

    form_fields = form.Fields(ITop5Portlet)
    form_fields['urls'].custom_widget = UberMultiSelectionWidget

    label = _(u"Edit Top5 Portlet")
    description = _(u"This portlet displays links to objects.")
