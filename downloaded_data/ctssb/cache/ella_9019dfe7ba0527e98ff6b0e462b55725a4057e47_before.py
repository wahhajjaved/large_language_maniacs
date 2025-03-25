"""
This module is intended as TEMPORARY. Contains registrations for testing purposes only, without affecting EllaAdmin.
Useful for NewmanModelAdmin registrations and other stuff.
"""

import datetime
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from ella.tagging.admin import TaggingInlineOptions

#from ella.core.admin import PlacementInlineOptions
from ella.core.models import Category, Author, Source
from ella.articles.models import ArticleContents, Article, InfoBox

from ella.newman import NewmanModelAdmin, NewmanTabularInline, site
from ella.newman import options
from ella.newman import generic as ng
from django.utils.safestring import mark_safe

# ------------------------------------
# Categories, Authors, Sources
# ------------------------------------
class CategoryOptions(NewmanModelAdmin):
    list_filter = ('site',)
    list_display = ('draw_title', 'tree_path', '__unicode__')
    search_fields = ('title', 'slug',)
    #ordering = ('site', 'tree_path',)
    prepopulated_fields = {'slug': ('title',)}

class AuthorOptions(NewmanModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

class SourceOptions(NewmanModelAdmin):
    list_display = ('name', 'url',)
    search_fields = ('name',)

# ------------------------------------
# DbTemplates
# ------------------------------------
from ella.db_templates.models import DbTemplate, TemplateBlock
#from ella.db_templates.admin import TemplateBlockFormset

class TemplateBlockFormset(options.NewmanInlineFormSet):
    "Custom formset enabling us to supply custom validation."

    @staticmethod
    def cmp_by_till(f, t):
        if f[1] is None:
            return 1
        elif t[1] is None:
            return -1
        else:
            return cmp(f[1], t[1])

    def clean(self):
        " Validate that the template's activity don't overlap. "
        if not self.is_valid():
            return

        # check that active_till datetime is greather then active_from
        validation_error = None
        for i,d in ( (i,d) for i,d in enumerate(self.cleaned_data) if d ):
            # don't bother with empty edit-inlines
            if not d:
                continue
            # both datetimes entered
            if d['active_from'] and d['active_till']:
                if d['active_from'] > d['active_till']:
                    validation_error = ValidationError( _('Block active till must be greater than Block active from') )
                    self.forms[i]._errors['active_till'] = validation_error.messages
        if validation_error:
            raise ValidationError( _('Invalid datetime interval. Block active till must be greater than Block active from' ) )

        # dictionary of blocks with tuples (active from, active till)
        items = {}
        for i,d in ( (i,d) for i,d in enumerate(self.cleaned_data) if d ):
            if not items.has_key(d['name']):
                items[d['name']] = [(d['active_from'], d['active_till'])]
            else:
                items[d['name']].append((d['active_from'], d['active_till']))

        # check that intervals are not in colision
        errors = []
        error_message = 'Block active intervals are in colision on %s. Specified interval stops at %s and next interval started at %s.'
        for name, intervals in items.items():
            if len(intervals) > 1:
                intervals.sort(self.cmp_by_till)
                for i in xrange(len(intervals)-1):
                    try:
                        # exact covering allwoved (00:00:00 to 00:00:00)
                        if intervals[i][1] > intervals[i+1][0]:
                            errors.append(error_message % (name, intervals[i][1], intervals[i+1][0]))
                    except TypeError:
                        errors.append(error_message % (name, 'Infinite', intervals[i+1][0]))
        if errors:
            raise ValidationError, errors

        return self.cleaned_data

class TemplateBlockInlineOptions( NewmanTabularInline ):
    model = TemplateBlock
    extra = 3
    fieldsets = ( ( None, { 'fields' : ( 'name', 'box_type', 'target_ct', 'target_id', 'active_from', 'active_till', 'text', ) } ), )
    formset = TemplateBlockFormset

class DbTemplateOptions( NewmanModelAdmin ):
    ordering = ( 'description', )
    inlines = ( TemplateBlockInlineOptions, )
    list_display = ( 'name', 'site', 'extends', 'description', )
    list_filter = ( 'site', )

    def queryset(self, request):
        return self.model._default_manager.all() # FIXME remove this line, newman testing purposes only.
        if request.user.is_superuser:
            return self.model._default_manager.all()
        else:
            return self.model._default_manager.filter(pk__in=[401,399,397,395,393,391,389,387,373])

site.register( DbTemplate, DbTemplateOptions )



# ------------------------------------
# Placements
# ------------------------------------
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.forms import models as modelforms

from ella.core.models import Author, Source, Category, Listing, HitCount, Placement
from ella.ellaadmin import widgets

class PlacementForm( modelforms.ModelForm ):
    # create the field here to pass validation
    listings =  modelforms.ModelMultipleChoiceField( Category.objects.all(), label=_('Category'), cache_choices=True, required=False )

    class Meta:
        model = Placement

    def __init__( self, *args, **kwargs ):
        initial = []
        if 'initial' in kwargs:
            initial = [ c.pk for c in Category.objects.distinct().filter( listing__placement=kwargs['initial']['id'] ) ]

        self.base_fields['listings'] = modelforms.ModelMultipleChoiceField(
                Category.objects.all(), label=_('Category'), cache_choices=True, required=False, initial=initial )
        super( PlacementForm, self ).__init__( *args, **kwargs )


class PlacementInlineFormset( ng.BaseGenericInlineFormSet ):
    def __init__(self, data=None, files=None, instance=None, save_as_new=None, prefix=None):
        self.can_delete = True
        super(PlacementInlineFormset, self).__init__(instance=instance, data=data, files=files, prefix=prefix)

    def save_existing(self, form, instance, commit=True):
        instance = super( PlacementInlineFormset, self ).save_existing( form, instance, commit )
        return self.save_listings( form, instance, commit )

    def save_new(self, form, commit=True):
        instance = super( PlacementInlineFormset, self ).save_new( form, commit )
        return self.save_listings( form, instance, commit )

    def save_listings(self, form, instance, commit=True):
        list_cats = form.cleaned_data.pop( 'listings' )

        def save_listings():
            listings = dict( [ ( l.category, l ) for l in Listing.objects.filter( placement=instance.pk ) ] )

            for c in list_cats:
                if not c in listings:
                    # create listing
                    l = Listing( placement=instance, category=c, publish_from=instance.publish_from )
                    l.save()
                else:
                    del listings[c]
            for l in listings.values():
                l.delete()

        if commit:
            save_listings()
        else:
            save_m2m = form.save_m2m
            def save_all():
                save_m2m()
                save_listings()
            form.save_m2m = save_all
        return instance

    def clean ( self ):
        # no data - nothing to validate
        if not self.is_valid() or not self.cleaned_data or not self.instance or not self.cleaned_data[0]:
            return

        obj = self.instance
        cat = getattr( obj, 'category', None )
        obj_slug = getattr( obj, 'slug', obj.pk )
        target_ct=ContentType.objects.get_for_model( obj )

        main = None
        for d in self.cleaned_data:
            # empty form
            if not d: break

            if cat and cat == cat and cat:
                main = d

            if d['slug'] and d['slug'] != '':
                slug = d['slug']
            else:
                slug = obj_slug

            # try and find conflicting placement
            qset = Placement.objects.filter(
                category=d['category'],
                slug=slug,
                target_ct=target_ct.pk,
                static=d['static']
            )

            if d['static']: # allow placements that do not overlap
                q = Q(publish_to__lt=d['publish_from'])
                if d['publish_to']:
                    q |= Q( publish_from__gt=d['publish_to'] )
                qset = qset.exclude(q)

            # check for same date in URL
            if not d['static']:
                qset = qset.filter(
                    publish_from__year=d['publish_from'].year,
                    publish_from__month=d['publish_from'].month,
                    publish_from__day=d['publish_from'].day,
                )

            # exclude current object from search
            if d['id']:
                qset = qset.exclude( pk=d['id'] )

            if qset:
                plac = qset[0]
                # raise forms.ValidationError(
                raise ValidationError(
                        _('''There is already a Placement object published in
                        category %(category)s with the same URL referring to %(target)s.
                        Please change the slug or publish date.''') % {
                            'category' : plac.category,
                            'target' : plac.target,
                        } )

            '''
            qset = Placement.objects.filter(
                        target_id=obj.pk,
                        target_ct=target_ct,
                    )

            if 'id' in d:
                qset = qset.exclude( id=d['id']  )

            if qset:
                # raise forms.ValidationError('Chyba')
                raise ValidationError('Chyba')
            '''

        if cat and not main:
            # raise forms.ValidationError( _( 'If object has a category, it must have a main placement.' ) )
            raise ( _( 'If object has a category, it must have a main placement.' ) )

        return

class PlacementInlineOptions( ng.GenericTabularInline ):
    model = Placement
    max_num = 1
    ct_field = 'target_ct'
    ct_fk_field = 'target_id'
    formset = PlacementInlineFormset
    form = PlacementForm
    fieldsets = ( ( None, { 'fields' : ('category', 'publish_from', 'publish_to', 'slug', 'static', 'listings', ) } ), )

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'category':
            kwargs['widget'] = widgets.ListingCategoryWidget
        return super( PlacementInlineOptions, self ).formfield_for_dbfield( db_field, **kwargs )

class ListingInlineOptions( NewmanTabularInline ):
    model = Listing
    extra = 2
    fieldsets = ( ( None, { 'fields' : ('category','publish_from', 'priority_from', 'priority_to', 'priority_value', 'remove', 'commercial', ) } ), )

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'category':
            kwargs['widget'] = widgets.ListingCategoryWidget
        return super( ListingInlineOptions, self ).formfield_for_dbfield( db_field, **kwargs )

class PlacementOptions(NewmanModelAdmin):
    list_display = ('target_admin', 'category', 'publish_from', 'full_url',)
    list_filter = ('publish_from', 'category', 'target_ct',)
    inlines = (ListingInlineOptions,)
    fieldsets = (
        (_('target'), {'fields': ('target_ct', 'target_id', 'slug', 'category',), 'classes': ('wide',)},),
        (_('time'), {'fields': ('publish_from','publish_to', 'static',), 'classes': ('wide',)},),
)

# ------------------------------------
# Articles
# ------------------------------------

class ArticleContentInlineOptions(NewmanTabularInline):
    model = ArticleContents
    max_num = 1
    rich_text_fields = { None: ('content',) }

class InfoBoxOptions(NewmanModelAdmin):
    list_display = ( 'title', 'created', )
    date_hierarchy = 'created'
    list_filter = ( 'created', 'updated', )
    search_fields = ( 'title', 'content', )
    rich_text_fields = { None: ('content',) }

class ArticleOptions(NewmanModelAdmin):
    list_display = ('title', 'category', 'photo_thumbnail', 'publish_from', 'hitcounts', 'obj_url')
    list_display_ext = ('article_age', 'get_hits', 'pk', 'full_url',)
    ordering = ( '-created', )
    fieldsets = (
        ( _( "Article heading" ), { 'fields': ( 'title', 'upper_title', 'updated', 'slug' ) } ),
        ( _( "Article contents" ), { 'fields': ( 'perex', ) } ),
        ( _( "Metadata" ), { 'fields': ( 'category', 'authors', 'source', 'photo' ) } ),
    )
    raw_id_fields = ('photo',)
    list_filter = ( 'category__site', 'created', 'category', )
    search_fields = ( 'title', 'upper_title', 'perex', 'slug', 'authors__name', 'authors__slug', ) # FIXME: 'tags__tag__name', )
    inlines = [ ArticleContentInlineOptions, PlacementInlineOptions ]
    suggest_fields = { 'authors': ('name', 'slug',), 'source': ('name', 'url',), 'category': ('title', 'tree_path'), }
    prepopulated_fields = { 'slug' : ( 'title', ) }
    rich_text_fields = { None: ('perex',) }
    list_per_page = 20

    def obj_url(self, obj):
        if obj.get_absolute_url():
            return mark_safe('<a href="%s">url</a>' % obj.get_absolute_url())
        return _('No URL')
    obj_url.allow_tags = True
    obj_url.short_description = _('Full URL')

    def hitcounts(self, obj):
        return mark_safe('<a class="icn na" href="">?</a>')
    hitcounts.allow_tags = True
    hitcounts.short_description = _('Hits')

    def publish_from(self, obj):
        if not obj.main_placement:
            return '--'
        pf = obj.main_placement.publish_from
        if datetime.datetime.now() < pf:
            return mark_safe('<div style="background-color: darkorange;">%s</div>' % pf)
        return pf
    publish_from.allow_tags = True
    publish_from.short_description = _('Publish from')
#    publish_from.admin_order_field = 'created'

#    def queryset(self, request):
#        q = super(ArticleOptions, self).queryset(request)
#        q = q.extra(
#            select={
#                'publish_from': 'SELECT publish_from FROM core_placement WHERE target_ct_id=16 AND target_id=articles_article.id AND core_placement.category_id=articles_article.category_id',
#            }
#        )
#        q = q.extra(
#            tables = ['core_placement'],
#            where = [
#                'target_ct_id=%s',
#                'target_id=articles_article.id',
#                'core_placement.category_id=articles_article.category_id'
#            ],
#            params = [16],
#        )
#        raise KeyError, connection.queries
#        return q

from ella.db.models import Publishable


site.register(InfoBox, InfoBoxOptions)
site.register(Article, ArticleOptions)
site.register(Category, CategoryOptions)
site.register(Author, AuthorOptions)
site.register(Source, SourceOptions)
site.register(Placement, PlacementOptions)


# ------------------------------------
# Django auth model admins
# ------------------------------------

from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

site.register(Group, GroupAdmin)
site.register(User, UserAdmin)
