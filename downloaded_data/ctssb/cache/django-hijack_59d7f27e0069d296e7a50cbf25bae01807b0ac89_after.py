from django import template
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string
from django.template import RequestContext
from compat import import_string

from hijack import settings as hijack_settings

register = template.Library()


# Deprecated. Use the template tag below
@register.filter
def hijackNotification(request):
    return _render_hijack_notification(request)


@register.simple_tag(takes_context=True)
def hijack_notification(context):
    request = context['request']
    return _render_hijack_notification(request)


def _render_hijack_notification(request):
    if hijack_settings.HIJACK_USE_BOOTSTRAP:
        template_name = 'hijack/notifications_bootstrap.html'
    else:
        template_name = 'hijack/notifications.html'
    ans = ''
    if all([
        hijack_settings.HIJACK_DISPLAY_WARNING,
        request,
        request.session.get('is_hijacked_user', False),
        request.session.get('display_hijack_warning', False),
    ]):
        ans = render_to_string(template_name, {'request': request})
    return mark_safe(ans)


@register.filter
def can_hijack(hijacker, hijacked):
    check_authorization = import_string(hijack_settings.HIJACK_AUTHORIZATION_CHECK)
    return check_authorization(hijacker, hijacked)
