# -*- coding: utf-8 -*-
# This file is part of PrawoKultury, licensed under GNU Affero GPLv3 or later.
# Copyright © Fundacja Nowoczesna Polska. See NOTICE for more information.
#
from django.conf import settings
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _
from migdal.models import Entry, Attachment
from migdal import app_settings
from fnpdjango.utils.models import filtered_model
from fnpdjango.utils.models.translation import translated_fields


class AttachmentInline(admin.TabularInline):
    model = Attachment
    readonly_fields = ['url']


def filtered_entry_admin(typ):
    class EntryAdmin(admin.ModelAdmin):
        def queryset(self, request):
            return self.model.objects.filter(type=typ.db)

        def has_add_permission(self, request):
            return request.user.has_perm('migdal.add_entry')

        def has_change_permission(self, request, obj=None):
            return request.user.has_perm('migdal.change_entry')

        def has_delete_permission(self, request, obj=None):
            return request.user.has_perm('migdal.delete_entry')

        def formfield_for_dbfield(self, db_field, **kwargs):
            field = super(EntryAdmin, self).formfield_for_dbfield(db_field, **kwargs)
            if db_field.name == 'categories':
                field.widget.attrs['style'] = 'height: 10em'
            return field

        date_hierarchy = 'date'
        readonly_fields = ('date', 'changed_at', 'first_published_at') + \
            translated_fields(('published_at',))
        _promo_if_necessary = ('promo',) if typ.promotable else ()

        fieldsets = (
            (None, {
                'fields': _promo_if_necessary + (
                    'in_stream', 'author', 'author_email', 'canonical_url', 'image',
                    'date', 'first_published_at', 'changed_at')
                }),
        ) + tuple(
            (ln, {'fields': (
                ('published_%s' % lc),
                'published_at_%s' % lc,
                'title_%s' % lc,
                'slug_%s' % lc,
                'lead_%s' % lc,
                'body_%s' % lc,
                )})
            for lc, ln in app_settings.OBLIGATORY_LANGUAGES
        ) + tuple(
            (ln, {'fields': (
                ('needed_%s' % lc, 'published_%s' % lc),
                'published_at_%s' % lc,
                'title_%s' % lc,
                'slug_%s' % lc,
                'lead_%s' % lc,
                'body_%s' % lc,
                )})
            for lc, ln in app_settings.OPTIONAL_LANGUAGES
        )

        if typ.categorized:
            fieldsets += (
                (_('Categories'), {'fields': ('categories',)}),
            )
        prepopulated_fields = dict([
                ("slug_%s" % lang_code, ("title_%s" % lang_code,))
                for lang_code, lang_name in settings.LANGUAGES
            ]) 

        list_display = translated_fields(('title',), app_settings.OBLIGATORY_LANGUAGES) + \
            ('date', 'author') + \
            _promo_if_necessary + \
            ('in_stream', 'first_published_at',) + \
            translated_fields(('published_at',)) + \
            translated_fields(('needed',), app_settings.OPTIONAL_LANGUAGES)
        list_filter = _promo_if_necessary + \
            translated_fields(('published',)) + \
            translated_fields(('needed',), app_settings.OPTIONAL_LANGUAGES)
        inlines = (AttachmentInline,)
        search_fields = ('title_pl', 'title_en')
    return EntryAdmin


for typ in app_settings.TYPES:
    newmodel = filtered_model("Entry_%s" % typ.db, Entry, 'type', typ.db, typ.slug)
    admin.site.register(newmodel, filtered_entry_admin(typ))


if app_settings.TAXONOMIES:
    from migdal.models import Category

    class CategoryAdmin(admin.ModelAdmin):
        list_display = translated_fields(('title', 'slug')) + ('taxonomy',)
        prepopulated_fields = dict([
                ("slug_%s" % lang_code, ("title_%s" % lang_code,))
                for lang_code, lang_name in settings.LANGUAGES
            ]) 
    admin.site.register(Category, CategoryAdmin)
