from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from userservice.user import UserService
import logging
from authz_group import Group

def support(request):
    #timer = Timer()
    logger = logging.getLogger(__name__)

    user_service = UserService()
    user_service.get_user()
    # Do the group auth here.

    if not hasattr(settings, "USERSERVICE_ADMIN_GROUP"):
        print "You must have a group defined as your admin group."
        print 'Configure that using USERSERVICE_ADMIN_GROUP="foo_group"'
        raise Exception("Missing USERSERVICE_ADMIN_GROUP in settings")

    actual_user = user_service.get_original_user()
    if not actual_user:
        raise Exception("No user in session")

    g = Group()
    group_name = settings.USERSERVICE_ADMIN_GROUP
    is_admin = g.is_member_of_group(actual_user, group_name)
    if is_admin == False:
        return render_to_response('no_access.html', {})

    if "override_as" in request.POST:
        new_user = request.POST["override_as"].strip()
        logger.info("%s is impersonating %s",
                    user_service.get_original_user(),
                    new_user)
        user_service.set_override_user(new_user)

    if "clear_override" in request.POST:
        logger.info("%s is ending impersonation of %s",
                    user_service.get_original_user(),
                    user_service.get_override_user())
        user_service.clear_override()

    context = {
        'original_user': user_service.get_original_user(),
        'override_user': user_service.get_override_user(),
    }

    return render_to_response('support.html',
                              context,
                              context_instance=RequestContext(request))


