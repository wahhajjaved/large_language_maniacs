# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# $Id: xmlrpc.py 428 2009-07-14 03:48:07Z tobias $
# ----------------------------------------------------------------------------
#
#    Copyright (C) 2008-2009 Caktus Consulting Group, LLC
#
#    This file is part of django-crm and was originally extracted from minibooks.
#
#    django-crm is published under a BSD-style license.
#    
#    You should have received a copy of the BSD License along with django-crm.  
#    If not, see <http://www.opensource.org/licenses/bsd-license.php>.
#

import re

from SimpleXMLRPCServer import SimpleXMLRPCDispatcher

from django.conf import settings
from django.http import HttpResponse
from django.contrib import auth
from django.forms.fields import email_re
from django.contrib.auth.models import User

from crm import models as crm
from crm.decorators import has_perm_or_basicauth

try:
    from timepiece import models as timepiece
except ImportError:
    timepiece = None

try:
    # Python 2.5
    dispatcher = SimpleXMLRPCDispatcher(allow_none=False, encoding=None)
except:
    # Python 2.4
    dispatcher = SimpleXMLRPCDispatcher()


@has_perm_or_basicauth('crm.access_xmlrpc', realm='django-crm XML-RPC Service')
def rpc_handler(request):
    response = HttpResponse()
    
    if len(request.POST):
        response.write(dispatcher._marshaled_dispatch(request.raw_post_data))
    else:
        response.write("<b>This is the django-crm XML-RPC Service.</b><br>")
        response.write("You need to invoke it using an XML-RPC Client!<br>")
        response.write("The following methods are available:<ul>")
        for method in dispatcher.system_listMethods():
            sig = dispatcher.system_methodSignature(method)
            help = dispatcher.system_methodHelp(method)
            response.write("<li><b>%s</b>: [%s] %s" % (method, sig, help))
        response.write("</ul>")
    
    response['Content-length'] = str(len(response.content))
    return response


def _get_contact(username):
    if email_re.search(username):
        try:
            contact = crm.Contact.objects.get(user__email=username)
        except crm.Contact.DoesNotExist:
            contact = None
    else:
        try:
            contact = crm.Contact.objects.get(user__username=username)
        except crm.Contact.DoesNotExist:
            contact = None
    return contact


def authenticate(username, password):
    return bool(auth.authenticate(username=username, password=password))
dispatcher.register_function(authenticate, 'authenticate')


def project_relationships(project_trac_env, username):
    groups = []
    contact = _get_contact(username)
    if contact:
        groups = crm.RelationshipType.objects.filter(
            project_relationships__contact=contact,
            project_relationships__project__trac_environment=project_trac_env,
        ).values_list('slug', flat=True)
    return list(groups)
dispatcher.register_function(project_relationships, 'project_relationships')


def callerid(number):
    number = re.sub('[^0-9]', '', number)
    if number.startswith('1'):
        number = number[1:]
    parts = (number[0:3], number[3:6], number[6:10])
    number = '-'.join(parts)
    
    try:
        user = User.objects.get(profile__locations__phones__number=number)
        return user.get_full_name()
    except User.DoesNotExist:
        try:
            business = \
              crm.Business.objects.get(locations__phones__number=number)
            return business.name
        except crm.Business.DoesNotExist:
            return number
dispatcher.register_function(callerid, 'callerid')
