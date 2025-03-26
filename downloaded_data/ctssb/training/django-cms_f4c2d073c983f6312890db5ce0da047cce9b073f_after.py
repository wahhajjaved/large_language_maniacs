# -*- coding: utf-8 -*-
from cms.api import get_page_draft
from cms.constants import TEMPLATE_INHERITANCE_MAGIC
from cms.exceptions import LanguageError
from cms.models import Title
from cms.toolbar.items import TemplateItem
from cms.toolbar_base import CMSToolbar
from cms.utils.i18n import get_language_objects, get_language_object, force_language
from django.contrib.sites.models import Site
from cms.utils import get_language_from_request, get_cms_setting
from cms.toolbar_pool import toolbar_pool
from cms.utils.permissions import get_user_sites_queryset, has_page_change_permission
from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin
from django.contrib.auth.models import User
from menus.utils import DefaultLanguageChanger


# Identifiers for search
ADMIN_MENU_IDENTIFIER = 'admin-menu'
LANGUAGE_MENU_IDENTIFIER = 'language-menu'
TEMPLATE_MENU_BREAK = 'Template Menu Break'
PAGE_MENU_FIRST_BREAK = 'Page Menu First Break'
PAGE_MENU_SECOND_BREAK = 'Page Menu Second Break'
PAGE_MENU_THIRD_BREAK = 'Page Menu Third Break'
HISTORY_MENU_BREAK = 'History Menu Break'
MANAGE_PAGES_BREAK = 'Manage Pages Break'
ADMIN_SITES_BREAK = 'Admin Sites Break'
ADMINISTRATION_BREAK = 'Administration Break'
USER_SETTINGS_BREAK = 'User Settings Break'
ADD_PAGE_LANGUAGE_BREAK = "Add page language Break"
REMOVE_PAGE_LANGUAGE_BREAK = "Remove page language Break"
COPY_PAGE_LANGUAGE_BREAK = "Copy page language Break"


@toolbar_pool.register
class PlaceholderToolbar(CMSToolbar):
    """
    Adds placeholder edit buttons if placeholders or static placeholders are detected in the template

    """

    def populate(self):
        self.page = get_page_draft(self.request.current_page)
        statics = getattr(self.request, 'static_placeholders', [])
        placeholders = getattr(self.request, 'placeholders', [])
        if self.page:
            if self.page.has_change_permission(self.request):
                self.add_structure_mode()
            elif statics:
                for static_placeholder in statics:
                    if static_placeholder.has_change_permission(self.request):
                        self.add_structure_mode()
                        break
        else:
            added = False
            if statics:
                for static_placeholder in statics:
                    if static_placeholder.has_change_permission(self.request):
                        self.add_structure_mode()
                        added = True
                        break
            if not added and placeholders:
                self.add_structure_mode()

    def add_structure_mode(self):
        switcher = self.toolbar.add_button_list('Mode Switcher', side=self.toolbar.RIGHT,
                                                extra_classes=['cms_toolbar-item-cms-mode-switcher'])
        switcher.add_button(_("Content"), '?edit', active=not self.toolbar.build_mode,
                            disabled=self.toolbar.build_mode)
        switcher.add_button(_("Structure"), '?build', active=self.toolbar.build_mode,
                            disabled=not self.toolbar.build_mode)


@toolbar_pool.register
class BasicToolbar(CMSToolbar):
    """
    Basic Toolbar for site and languages menu
    """

    def populate(self):
        self.current_site = Site.objects.get_current()
        self.add_admin_menu()
        self.add_language_menu()

    def add_admin_menu(self):
        admin_menu = self.toolbar.get_or_create_menu(ADMIN_MENU_IDENTIFIER, self.current_site.name)
        if self.request.user.has_perm('user.change_user') and User in admin.site._registry:
            admin_menu.add_sideframe_item(_('Users'), url=reverse("admin:auth_user_changelist"))
        # sites menu
        if get_cms_setting('PERMISSION'):
            sites_queryset = get_user_sites_queryset(self.request.user)
        else:
            sites_queryset = Site.objects.all()
        if len(sites_queryset) > 1:
            sites_menu = admin_menu.get_or_create_menu('sites', _('Sites'))
            sites_menu.add_sideframe_item(_('Admin Sites'), url=reverse('admin:sites_site_changelist'))
            sites_menu.add_break(ADMIN_SITES_BREAK)
            for site in sites_queryset:
                sites_menu.add_link_item(site.name, url='http://%s' % site.domain,
                                         active=site.pk == self.current_site.pk)
        # static placeholders
        admin_menu.add_sideframe_item(_('Static Placeholders'), url=reverse('admin:cms_staticplaceholder_changelist'))
        # admin
        admin_menu.add_sideframe_item(_('Administration'), url=reverse('admin:index'))
        admin_menu.add_break(ADMINISTRATION_BREAK)
        # cms users
        admin_menu.add_sideframe_item(_('User settings'), url=reverse('admin:cms_usersettings_change'))
        admin_menu.add_break(USER_SETTINGS_BREAK)
        # logout
        admin_menu.add_ajax_item(_('Logout'), action=reverse('admin:logout'), active=True)

    def add_language_menu(self):
        try:
            current_lang = get_language_object(get_language_from_request(self.request), self.current_site.pk)
        except LanguageError:
            current_lang = None
        language_menu = self.toolbar.get_or_create_menu(LANGUAGE_MENU_IDENTIFIER, _('Language'))
        language_changer = getattr(self.request, '_language_changer', DefaultLanguageChanger(self.request))
        for language in get_language_objects(self.current_site.pk):
            url = language_changer(language['code'])
            language_menu.add_link_item(language['name'], url=url, active=current_lang['code'] == language['code'])


@toolbar_pool.register
class PageToolbar(CMSToolbar):
    def populate(self):
        self.current_site = Site.objects.get_current()
        # always use draft if we have a page
        self.page = get_page_draft(self.request.current_page)
        # check global permissions if CMS_PERMISSIONS is active
        if get_cms_setting('PERMISSION'):
            has_global_current_page_change_permission = has_page_change_permission(self.request)
        else:
            has_global_current_page_change_permission = False
            # check if user has page edit permission
        can_change = self.request.current_page and self.request.current_page.has_change_permission(self.request)
        if has_global_current_page_change_permission or can_change:
            self.change_admin_menu()
            if self.page:
                self.add_page_menu()
        statics = getattr(self.request, 'static_placeholders', [])
        dirty_statics = [stpl for stpl in statics if stpl.dirty]
        placeholders = getattr(self.request, 'placeholders', [])
        if self.page or statics:
            if self.toolbar.edit_mode:
                # history menu
                if self.page:
                    self.add_history_menu()
                    self.change_language_menu()
                # publish button
                publish_permission = True
                if self.page and not self.page.has_publish_permission(self.request):
                    publish_permission = False

                for static_placeholder in dirty_statics:
                    if not static_placeholder.has_publish_permission(self.request):
                        publish_permission = False

                classes = ["cms_btn-action", "cms_btn-publish"]

                dirty = bool(self.page and self.page.is_dirty()) or len(dirty_statics) > 0
                if dirty:
                    classes.append("cms_btn-publish-active")
                if dirty_statics or (self.page and self.page.published):
                    title = _("Publish changes")
                else:
                    title = _("Publish page now")
                pk = 0
                if self.page:
                    pk = self.page.pk
                publish_url = reverse('admin:cms_page_publish_page', args=(pk,))
                if dirty_statics:
                    publish_url += "?statics=%s" % ','.join(str(static.pk) for static in dirty_statics)
                if publish_permission:
                    self.toolbar.add_button(title, url=publish_url, extra_classes=classes, side=self.toolbar.RIGHT,
                                        disabled=not dirty)
        if self.page:
            if self.page.has_change_permission(self.request) and self.page.published:
                self.add_draft_live()
            elif statics:
                for static_placeholder in statics:
                    if static_placeholder.has_change_permission(self.request):
                        self.add_draft_live()
                        break
        else:
            added = False
            if statics:
                for static_placeholder in statics:
                    if static_placeholder.has_change_permission(self.request):
                        self.add_draft_live()
                        added = True
                        break
            if not added and placeholders:
                self.add_draft_live()

    def add_draft_live(self):
        self.toolbar.add_item(TemplateItem("cms/toolbar/items/live_draft.html", extra_context={'request': self.request},
                                           side=self.toolbar.RIGHT), len(self.toolbar.right_items))

    def change_language_menu(self):
        language_menu = self.toolbar.get_or_create_menu(LANGUAGE_MENU_IDENTIFIER)
        add = []
        remove = Title.objects.filter(page=self.page).values_list('language', flat=True)
        languages = get_language_objects(self.current_site.pk)
        for language in languages:
            code = language['code']
            if not code in remove:
                add.append(code)
        if add:
            language_menu.add_break(ADD_PAGE_LANGUAGE_BREAK)
            for code in add:
                language = get_language_object(code, self.current_site.pk)
                url = "%s?language=%s" % (reverse("admin:cms_page_change", args=[self.page.pk]), language['code'])
                language_menu.add_modal_item(_("Add %(language)s Translation") % {'language': language['name']},
                                             url=url)
        if remove:
            language_menu.add_break(REMOVE_PAGE_LANGUAGE_BREAK)
            for code in remove:
                try:
                    language = get_language_object(code, self.current_site.pk)
                    language_code = language['code']
                    language_name = language['name']
                except LanguageError:
                    language_code = code
                    language_name = code
                url = "%s?language=%s" % (
                    reverse("admin:cms_page_delete_translation", args=[self.page.pk]), language_code)
                language_menu.add_modal_item(_("Delete %(language)s Translation") % {'language': language_name},
                                             url=url, disabled=len(remove) == 1)
        try:
            current_lang = get_language_object(get_language_from_request(self.request), self.current_site.pk)
        except LanguageError:
            current_lang = None
        if len(languages) > 1 and current_lang and len(remove) > 1:
            language_menu.add_break(COPY_PAGE_LANGUAGE_BREAK)
            for language in languages:
                if current_lang['code'] == language['code'] or language['code'] in add:
                    continue
                url = reverse('admin:cms_page_copy_language', args=[self.page.pk])
                question = _('Are you sure you want copy all plugins from %s?') % language['name']
                language_menu.add_ajax_item(_("Copy all plugins from %s") % language['name'], action=url,
                                            data={'source_language': language['code'],
                                            'target_language': current_lang['code']}, question=question)

    def change_admin_menu(self):
        admin_menu = self.toolbar.get_or_create_menu(ADMIN_MENU_IDENTIFIER)
        # cms page admin
        admin_menu.add_sideframe_item(_('Pages'), url=reverse("admin:cms_page_changelist"), position=0)

    def add_page_menu(self):
        # menu for current page
        not_edit_mode = not self.toolbar.edit_mode
        current_page_menu = self.toolbar.get_or_create_menu('page', _('Page'), position=1)
        current_page_menu.add_link_item(_('Edit this Page'), disabled=self.toolbar.edit_mode, url='?edit')
        page_info_url = reverse('admin:cms_page_change', args=(self.page.pk,))
        current_page_menu.add_modal_item(_('Page settings'), url=page_info_url, disabled=not_edit_mode,
                                         close_on_url=self.toolbar.URL_CHANGE, on_close=self.toolbar.REFRESH_PAGE)
        # Why are we doing this everywhere ?
        try:
            current_lang = get_language_object(get_language_from_request(self.request), self.current_site.pk)
        except LanguageError:
            current_lang = None
        if self.toolbar.build_mode or self.toolbar.edit_mode:
            # add templates
            templates_menu = current_page_menu.get_or_create_menu('templates', _('Templates'))
            action = reverse('admin:cms_page_change_template', args=(self.page.pk,))
            for path, name in get_cms_setting('TEMPLATES'):
                active = self.page.template == path
                if path == TEMPLATE_INHERITANCE_MAGIC:
                    templates_menu.add_break(TEMPLATE_MENU_BREAK)
                templates_menu.add_ajax_item(name, action=action, data={'template': path}, active=active)
        current_page_menu.add_break(PAGE_MENU_FIRST_BREAK)
        # advanced settings
        advanced_url = reverse('admin:cms_page_advanced', args=(self.page.pk,))
        advanced_disabled = not self.page.has_advanced_settings_permission(self.request) or not self.toolbar.edit_mode
        current_page_menu.add_modal_item(_('Advanced settings'), url=advanced_url, close_on_url=self.toolbar.URL_CHANGE,
                                         disabled=advanced_disabled)
        # permissions
        if get_cms_setting('PERMISSION'):
            permissions_url = reverse('admin:cms_page_permissions', args=(self.page.pk,))
            permission_disabled = not self.toolbar.edit_mode or not self.page.has_change_permissions_permission(
                self.request)
            current_page_menu.add_modal_item(_('Permissions'), url=permissions_url,
                                             close_on_url=self.toolbar.URL_CHANGE,
                                             disabled=permission_disabled)
        current_page_menu.add_break(PAGE_MENU_SECOND_BREAK)
        # navigation toggle
        if self.page.in_navigation:
            nav_title = _("Hide in navigation")
        else:
            nav_title = _("Display in navigation")
        nav_action = reverse('admin:cms_page_change_innavigation', args=(self.page.pk,))
        current_page_menu.add_ajax_item(nav_title, action=nav_action, disabled=not_edit_mode)
        # publisher
        if self.page.published:
            publish_title = _('Unpublish page')
        else:
            publish_title = _('Publish page')
        publish_url = reverse('admin:cms_page_change_status', args=(self.page.pk,))
        current_page_menu.add_ajax_item(publish_title, action=publish_url, disabled=not_edit_mode)
        current_page_menu.add_break(PAGE_MENU_THIRD_BREAK)
        # delete
        delete_url = reverse('admin:cms_page_delete', args=(self.page.pk,))
        with force_language(current_lang['code']):
            # We use force_language because it makes no sense to redirect a user
            # who just deleted a german page to an english page (user's default language)
            # simply because the url /en/some-german-page-slug will show nothing
            if self.page.parent:
                # If this page has a parent, then redirect to it
                on_delete_redirect_url = self.page.parent.get_absolute_url(language=current_lang['code'])
            else:
                # If there's no parent, we redirect to the root.
                # Can't call Page.objects.get_home() because the user could very well delete the homepage
                # causing get_home to throw an error.
                # Let's keep in mind that if the user has deleted the last page, and django is running on DEBUG == False
                # this redirect will cause a 404...
                on_delete_redirect_url = reverse('pages-root')
        current_page_menu.add_modal_item(_('Delete page'), url=delete_url, close_on_url=self.toolbar.URL_CHANGE,
                                         on_close=on_delete_redirect_url, disabled=not_edit_mode)

    def add_history_menu(self):
        # history menu
        history_menu = self.toolbar.get_or_create_menu('history', _('History'), position=2)
        if 'reversion' in settings.INSTALLED_APPS:
            import reversion
            from reversion.models import Revision

            versions = reversion.get_for_object(self.page)
            if self.page.revision_id:
                current_revision = Revision.objects.get(pk=self.page.revision_id)
                has_undo = versions.filter(revision__pk__lt=current_revision.pk).count() > 0
                has_redo = versions.filter(revision__pk__gt=current_revision.pk).count() > 0
            else:
                has_redo = False
                has_undo = versions.count() > 1
            undo_action = reverse('admin:cms_page_undo', args=(self.page.pk,))
            redo_action = reverse('admin:cms_page_redo', args=(self.page.pk,))
            history_menu.add_ajax_item(_('Undo'), action=undo_action, disabled=not has_undo)
            history_menu.add_ajax_item(_('Redo'), action=redo_action, disabled=not has_redo)
            history_menu.add_break(HISTORY_MENU_BREAK)
        revert_action = reverse('admin:cms_page_revert_page', args=(self.page.pk,))
        revert_question = _('Are you sure you want to revert to live?')
        history_menu.add_ajax_item(_('Revert to live'), action=revert_action, question=revert_question,
                                   disabled=not self.page.is_dirty())
        history_menu.add_modal_item(_('View history'), url=reverse('admin:cms_page_history', args=(self.page.pk,)))
