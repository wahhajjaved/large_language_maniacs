#
#  Copyright (c) 2009 Helmut Merz helmutm@cy55.de
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

"""
Utilities for the loops.organize package.

$Id$
"""

from zope import interface, component, schema
from zope.app.authentication.interfaces import IPluggableAuthentication
from zope.app.authentication.interfaces import IAuthenticatorPlugin
from zope.app.authentication.groupfolder import GroupFolder
from zope.app.security.interfaces import IAuthentication, PrincipalLookupError
from zope.app.security.settings import Allow, Deny, Unset
from zope.app.securitypolicy.interfaces import IPrincipalRoleManager
from zope.traversing.api import getParents
from loops.common import adapted
from loops.type import getOptionsDict

defaultAuthPluginId = 'loops'


def getPrincipalFolder(context=None, authPluginId=None, ignoreErrors=False):
    pau = component.getUtility(IAuthentication, context=context)
    if not IPluggableAuthentication.providedBy(pau):
        if ignoreErrors:
            return None
        raise ValueError(u'There is no pluggable authentication '
                          'utility available.')
    if authPluginId is None and context is not None:
        person = context.getLoopsRoot().getConceptManager()['person']
        od = getOptionsDict(adapted(person).options)
        authPluginId = od.get('principalfolder', defaultAuthPluginId)
    if authPluginId is None:
        authPluginId = defaultAuthPluginId
    if authPluginId not in pau.authenticatorPlugins:
        if ignoreErrors:
            return None
        raise ValueError(u"There is no loops authenticator "
                          "plugin '%s' available." % authPluginId)
    for name, plugin in pau.getAuthenticatorPlugins():
        if name == authPluginId:
            return plugin


def getGroupsFolder(context=None, name='gloops', create=False):
    gf = getPrincipalFolder(authPluginId=name, ignoreErrors=True)
    if gf is None and create:
        pau = component.getUtility(IAuthentication, context=context)
        gf = pau[name] = GroupFolder(name + '.')
        pau.authenticatorPlugins = tuple(
                        list(pau.authenticatorPlugins) + ['name'])
    return gf


def getGroupId(group):
    gf = group.__parent__
    return ''.join((gf.__parent__.prefix, gf._groupid(group)))


def getInternalPrincipal(id, context=None, pau=None):
    if pau is None:
        pau = component.getUtility(IAuthentication, context=context)
    if not IPluggableAuthentication.providedBy(pau):
        raise ValueError(u'There is no pluggable authentication '
                         u'utility available.')
    if not id.startswith(pau.prefix):
        next = queryNextUtility(pau, IAuthentication)
        if next is None:
            raise PrincipalLookupError(id)
        #return next.getPrincipal(id)
        return getInternalPrincipal(id, context, pau=next)
    id = id[len(pau.prefix):]
    for name, authplugin in pau.getAuthenticatorPlugins():
        if not id.startswith(authplugin.prefix):
            continue
        principal = authplugin.get(id[len(authplugin.prefix):])
        if principal is None:
            continue
        return principal
    next = queryNextUtility(pau, IAuthentication)
    if next is not None:
        #return next.getPrincipal(pau.prefix + id)
        return getInternalPrincipal(id, context, pau=next)
    raise PrincipalLookupError(id)


def getPrincipalForUserId(id, context=None):
    auth = component.getUtility(IAuthentication, context=context)
    try:
        return auth.getPrincipal(id)
    except PrincipalLookupError:
        return None


def getRolesForPrincipal(id, context):
    prinrole = IPrincipalRoleManager(context, None)
    if prinrole is None:
        return []
    result = []
    denied = []
    for role, setting in prinrole.getRolesForPrincipal(id):
        if setting == Allow:
            result.append(role)
        elif setting == Deny:
            denied.append(role)
    for obj in getParents(context):
        prinrole = IPrincipalRoleManager(obj, None)
        if prinrole is not None:
            for role, setting in prinrole.getRolesForPrincipal(id):
                if setting == Allow and role not in denied and role not in result:
                    result.append(role)
                elif setting == Deny and role not in denied:
                    denied.append(role)
    return result


def getTrackingStorage(obj, name):
    records = obj.getLoopsRoot().getRecordManager()
    if records is not None:
        return records.get(name)
    return None

