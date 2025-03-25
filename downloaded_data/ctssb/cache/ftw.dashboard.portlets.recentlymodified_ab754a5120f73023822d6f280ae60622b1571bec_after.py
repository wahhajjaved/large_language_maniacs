from zope import schema
from zope.component import getMultiAdapter
from zope.formlib import form
from zope.interface import implements
from zope.component import adapts, getUtility

from plone.app.portlets.portlets import base
from plone.memoize import ram
from plone.memoize.compress import xhtml_compress
from plone.memoize.instance import memoize
from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.cache import render_cachekey
from plone.app.vocabularies.catalog import SearchableTextSourceBinder

from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from Products.CMFCore.interfaces._content import IFolderish
from Products.statusmessages.interfaces import IStatusMessage

from plone.portlets.interfaces import IPortletManager
from plone.portlets.constants import USER_CATEGORY

from Acquisition import aq_inner
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from ftw.dashboard.portlets.recentlymodified import _

class IRecentlyModifiedPortlet(IPortletDataProvider):

    count = schema.Int(title=_(u"Number of items to display"),
                       description=_(u"How many items to list."),
                       required=True,
                       default=5)
                       
    section = schema.Choice(title=_(u"Section"),
                            description=_(u"Only changes in the selected section will be displayed."),
                            required=True,
                            source=SearchableTextSourceBinder({}, default_query='path:'))
                       

    #section = schema.Choice(title=_(u"Section"),
    #                     description=_(u"Only changes in the selected section will be displayed."),
     #                    required=True,
      #                   source=SearchableTextSourceBinder({}, default_query='path:'))

class Assignment(base.Assignment):
    implements(IRecentlyModifiedPortlet)

    def __init__(self, count=5, section=None):
        self.count = count
        self.section = section

    @property
    def title(self):
        return _(u"title_recentlyModifed_portlet", default=u"recently modified Portlet")

def _render_cachekey(fun, self):
    if self.anonymous:
        raise ram.DontCache()
    return render_cachekey(fun, self)

class Renderer(base.Renderer):
    _template = ViewPageTemplateFile('templates/recentlymodified.pt')

    def __init__(self, *args):
        base.Renderer.__init__(self, *args)

        context = aq_inner(self.context)
        portal_state = getMultiAdapter((context, self.request), name=u'plone_portal_state')
        self.anonymous = portal_state.anonymous()
        self.portal = portal_state.portal()
        self.portal_path = '/'.join(self.portal.getPhysicalPath())
        self.portal_url = portal_state.portal_url()
        self.typesToShow = portal_state.friendly_types()
        self.typesToShow = [type_ for type_ in self.typesToShow if type_ not in ['Image',]]

        plone_tools = getMultiAdapter((context, self.request), name=u'plone_tools')
        self.catalog = plone_tools.catalog()
        
    #@ram.cache(_render_cachekey)
    def render(self):
        return xhtml_compress(self._template())

    def recent_items(self):
        return self._data()

    @property
    def title(self):
        brains = self.catalog(path={'query' : self.portal_path + str(self.data.section), 'depth' : 0})
        if len(brains) == 1:
            section_title = brains[0].Title.decode('utf-8')
        else:
            section_title = self.portal.Title().decode('utf-8')
        return _(u"recent_changes_in", default=u"Recent Changes in ${section}", mapping={u"section" : section_title})

    @memoize
    def _data(self):
        limit = self.data.count

        references = self.context.portal_catalog({
            'path' : {
                    'query' : self.portal_path + str(self.data.section),
                    'depth' : 0,
                     }
            })

        if references and len(references)>0 and references[0].portal_type == "Topic":
            query = references.getObject().buildQuery()
        else:
            query = {
                'path' : self.portal_path + str(self.data.section),
            }
        
        query["sort_on"] = 'modified'
        query["sort_order"] = 'reverse'
        query["sort_limit"] = limit
        if "portal_type" in query.keys():
            if type(query["portal_type"]) not in (list,tuple):
                query["portal_type"] = list(query["portal_type"])    
            query["portal_type"] = filter(lambda a: a in self.typesToShow, query["portal_type"])
        else:
            query["portal_type"] = self.typesToShow
        
        
        return self.catalog(query)[:limit]


class AddForm(base.AddForm):
    
    form_fields = form.Fields(IRecentlyModifiedPortlet)
    label = _(u"Add recently modified Portlet")
    description = _(u"This portlet displays recently modified content in a selected section.")
    
    def create(self, data):
        
        return Assignment(count=data.get('count', 5), section=data.get('section', None))

class EditForm(base.EditForm):
    form_fields = form.Fields(IRecentlyModifiedPortlet)
    label = _(u"Edit recently modified Portlet")
    description = _(u"This portlet displays recently modified content in a selected section.")
    
    
class AddPortlet(object):
    
    def __call__(self):
        # This is only for a 'recently modified'-user-portlet in dashboard column 1 now, not at all abstracted
        column_manager = getUtility(IPortletManager, name='plone.dashboard1')
        membership_tool = getToolByName(self.context, 'portal_membership')
        userid = membership_tool.getAuthenticatedMember().getId()
        column = column_manager.get(USER_CATEGORY, {}).get(userid, {})
        id_base = 'recentlyModified'
        id = 0
        
        while id_base + str(id) in column.keys():
            id += 1
        portal_state = getMultiAdapter((self.context, self.context.REQUEST), name=u'plone_portal_state')
        context_path = '/'.join(self.context.getPhysicalPath())
        portal = portal_state.portal()
        portal_path = '/'.join(portal.getPhysicalPath())
        relative_context_path = portal_path

        if context_path != portal_path:
            relative_context_path = context_path.replace(portal_path, '')
        column[id_base + str(id)] = Assignment(count=5, section=relative_context_path)
    
        request = getattr(self.context, 'REQUEST', None)
        if request is not None:
            title = self.context.title_or_id().decode('utf-8')
            message = _(u"${title} added to dashboard.", mapping={'title' : title})
            IStatusMessage(request).addStatusMessage(message, type="info")
        return self.context.REQUEST.RESPONSE.redirect(self.context.absolute_url())

class QuickPreview(BrowserView):
    """
    """