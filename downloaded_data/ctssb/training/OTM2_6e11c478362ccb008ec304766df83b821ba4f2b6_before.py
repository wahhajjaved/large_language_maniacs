# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from django.conf import settings
from django.contrib.staticfiles import finders

from treemap.util import get_last_visited_instance


def global_settings(request):
    last_instance = get_last_visited_instance(request)
    if request.user.is_authenticated():
        last_effective_instance_user =\
            request.user.get_effective_instance_user(last_instance)
    else:
        last_effective_instance_user = None
    if hasattr(request, 'instance') and request.instance.logo:
        logo_url = request.instance.logo.url
    else:
        logo_url = settings.STATIC_URL + "img/logo-beta.png"

    try:
        comment_file_path = finders.find('version.txt')
        with open(comment_file_path, 'r') as f:
            header_comment = f.read()
    except:
        header_comment = "Version information not available\n"

    ctx = {'SITE_ROOT': settings.SITE_ROOT,
           'settings': settings,
           'last_instance': last_instance,
           'last_effective_instance_user': last_effective_instance_user,
           'logo_url': logo_url,
           'header_comment': header_comment}

    return ctx
