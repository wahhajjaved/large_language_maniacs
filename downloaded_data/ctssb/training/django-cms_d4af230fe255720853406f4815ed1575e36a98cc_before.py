# -*- coding: utf-8 -*-
"""
Edit Toolbar middleware
"""
from cms.plugin_pool import plugin_pool
from cms.toolbar.toolbar import CMSToolbar
from cms.utils.i18n import force_language
from django.contrib.admin.models import LogEntry
from menus.menu_pool import menu_pool
from django.http import HttpResponse
from django.template.loader import render_to_string
from cms.utils.placeholder import get_toolbar_plugin_struct


def toolbar_plugin_processor(instance, placeholder, rendered_content, original_context):
    original_context.push()
    child_plugin_classes = []
    plugin_class = instance.get_plugin_class()
    if plugin_class.allow_children:
        inst, plugin = instance.get_plugin_instance()
        page = original_context['request'].current_page
        children = [plugin_pool.get_plugin(cls) for cls in plugin.get_child_classes(placeholder, page)]
        # Builds the list of dictionaries containing module, name and value for the plugin dropdowns
        child_plugin_classes = get_toolbar_plugin_struct(children, placeholder.slot, placeholder.page,
                                                         parent=plugin_class)
    instance.placeholder = placeholder
    request = original_context['request']
    with force_language(request.toolbar.toolbar_language):
        data = {
            'instance': instance,
            'rendered_content': rendered_content,
            'child_plugin_classes': child_plugin_classes,
            'edit_url': placeholder.get_edit_url(instance.pk),
            'add_url': placeholder.get_add_url(),
            'delete_url': placeholder.get_delete_url(instance.pk),
            'move_url': placeholder.get_move_url(),
        }
    original_context.update(data)
    output = render_to_string(instance.get_plugin_class().frontend_edit_template, original_context)
    original_context.pop()
    return output


class ToolbarMiddleware(object):
    """
    Middleware to set up CMS Toolbar.
    """

    def process_request(self, request):
        """
        If we should show the toolbar for this request, put it on
        request.toolbar. Then call the request_hook on the toolbar.
        """
        if 'edit' in request.GET and not request.session.get('cms_edit', False):
            if not request.session.get('cms_edit', False):
                menu_pool.clear()
            request.session['cms_edit'] = True
            if request.session.get('cms_build', False):
                request.session['cms_build'] = False
        if 'edit_off' in request.GET and request.session.get('cms_edit', True):
            if request.session.get('cms_edit', True):
                menu_pool.clear()
            request.session['cms_edit'] = False
            if request.session.get('cms_build', False):
                request.session['cms_build'] = False
        if 'build' in request.GET and not request.session.get('cms_build', False):
            request.session['cms_build'] = True
        if request.user.is_staff:
            request.session['cms_log_entries'] = LogEntry.objects.filter(user=request.user).count()
        request.toolbar = CMSToolbar(request)

    def process_view(self, request, view_func, view_args, view_kwarg):
        response = request.toolbar.request_hook()
        if isinstance(response, HttpResponse):
            return response

    def process_response(self, request, response):
        from django.utils.cache import add_never_cache_headers
        found = False
        if hasattr(request, 'toolbar') and request.toolbar.edit_mode:
            found = True
        for placeholder in getattr(request, 'placeholders', []):
            if not placeholder.cache_placeholder:
                found = True
                break
        if found:
            add_never_cache_headers(response)
        if request.user.is_staff:
            count = LogEntry.objects.filter(user=request.user).count()
            if request.session.get('cms_log_entries', 0) < count:
                request.session['cms_log_entries'] = count
                log = LogEntry.objects.filter(user=request.user)[0]
                if log.action_flag == 1 or log.action_flag == 2:
                    request.session['cms_log_latest'] = log.pk
        return response
