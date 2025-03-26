from urllib import unquote
from zope.component import queryUtility
from zope.component import getMultiAdapter

from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFPlone import PloneMessageFactory as _

from plone.registry.interfaces import IRegistry

from upcnet.cas.interface import ICASSettings


def secureURL(url):
    """ Secures an URL (given http, returns https) """
    if url[:5] == 'http:' or url[:5] == 'HTTP:':
        return '%s%s' % ('https:', url[5:])
    else:
        return url


def login_URL(context, request):
    """ Refactored to use anz.casclient """
    # We suppose that a configured plugin is in place and it's called CASUPC
    portal = getToolByName(context, "portal_url").getPortalObject()
    plugin = getattr(portal.acl_users, 'CASUPC', None)

    if plugin:
        registry = queryUtility(IRegistry)
        cas_settings = registry.forInterface(ICASSettings)

        current_url = getMultiAdapter((context, request), name=u'plone_context_state').current_page_url()

        if current_url[-6:] == '/login' or current_url[-11:] == '/login_form' or 'require_login' in current_url:
            url = loginForm_URL(context, request)
        else:
            url = '%s?idApp=%s&service=%s' % (plugin.getLoginURL(), cas_settings.cas_app_name, secureURL(unquote(plugin.getService())))

        # Now not planned to be used. If it's used, then make them go before the (unquoted) service URL
        if plugin.renew:
            url += '&renew=true'
        if plugin.gateway:
            url += '&gateway=true'

        return url

    else:
        return '%s/login_form' % portal.absolute_url()


def logout(context, request):
    portal = getToolByName(context, "portal_url").getPortalObject()
    plugin = portal.acl_users.CASUPC

    mt = getToolByName(context, 'portal_membership')
    mt.logoutUser(REQUEST=request)
    IStatusMessage(request).addStatusMessage(_('heading_signed_out'), type='info')

    logout_url = '%s%s%s' % (plugin.casServerUrlPrefix, '/logout?url=', portal.absolute_url())

    return request.RESPONSE.redirect(logout_url)


def loginForm_URL(context, request):
    """ Special treatment of the login_form CAS URL, otherwise the return URL
        will be the login form once authenticated. """
    # We suppose that a configured plugin is in place and its called CASUPC
    portal = getToolByName(context, "portal_url").getPortalObject()
    plugin = getattr(portal.acl_users, 'CASUPC', None)

    if plugin:
        registry = queryUtility(IRegistry)
        cas_settings = registry.forInterface(ICASSettings)

        camefrom = getattr(request, 'came_from', '')
        if not camefrom:
            camefrom = portal.absolute_url()

        url = '%s?came_from=%s&idApp=%s&service=%s/logged_in?' % (plugin.getLoginURL(), secureURL(camefrom), cas_settings.cas_app_name, secureURL(portal.absolute_url()))

        # Now not planned to be used. If it's used, then make them go before the (unquoted) service URL
        if plugin.renew:
            url += '&renew=true'
        if plugin.gateway:
            url += '&gateway=true'

        return url

    else:
        return '%s/login_form' % portal.absolute_url()
