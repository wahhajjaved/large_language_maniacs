# -*- coding: utf-8 -*-

from zope.interface import implements

from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName

#from zope.i18nmessageid import MessageFactory
#_ = MessageFactory('notes.kbtic')
from Products.CMFPlone import PloneMessageFactory as _


class IEtiquetesCSPTPortlet(IPortletDataProvider):
    """ Defines a new portlet
    """


class Assignment(base.Assignment):
    """ Assigner for portlet. """
    implements(IEtiquetesCSPTPortlet)
    title = _(u"Etiquetes CSPT", default=u'Etiquetes CSPT')


class Renderer(base.Renderer):
    """ Overrides static.pt in the rendering of the portlet. """
    render = ViewPageTemplateFile('etiquetesCSPT.pt')

    def mostrarEtiquetesCategoryCSPT(self):
        """ Mostra etiquetes CSPT
        """
        urltool = getToolByName(self.context, 'portal_url')
        path = urltool.getPortalPath()

        results = []
        path = path + '/portal_vocabularies/categoryCSPT_keywords'
        keys = self.context.portal_catalog.searchResults(portal_type='SimpleVocabularyTerm',
                                                             path={'query': path, 'depth': 1, },
                                                             sort_on='Title')
        for value in keys:
            results.append({'id': value.id, 'title': value.Title})

        return results


class AddForm(base.NullAddForm):

    def create(self):
        return Assignment()
