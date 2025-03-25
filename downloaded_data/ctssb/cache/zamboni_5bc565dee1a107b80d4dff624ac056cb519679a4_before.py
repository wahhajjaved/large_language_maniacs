import functools
import hashlib
import json
import random
import uuid
from operator import attrgetter

from django import http
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_list_or_404, get_object_or_404, redirect
from django.utils.translation import trans_real as translation
from django.utils import http as urllib
from django.views.decorators.cache import cache_page, cache_control
from django.views.decorators.vary import vary_on_headers

import caching.base as caching
import jingo
import jinja2
import commonware.log
import session_csrf
from tower import ugettext as _, ugettext_lazy as _lazy
from mobility.decorators import mobilized, mobile_template

import amo
from amo import messages
from amo.forms import AbuseForm
from amo.utils import sorted_groupby, randslice
from amo.helpers import absolutify
from amo.models import manual_order
from amo import urlresolvers
from amo.urlresolvers import reverse
from abuse.models import send_abuse_report
from addons.utils import FeaturedManager
from bandwagon.models import Collection, CollectionFeature, CollectionPromo
import paypal
from reviews.forms import ReviewForm
from reviews.models import Review, GroupedRating
from sharing.views import share as share_redirect
from stats.models import GlobalStat, Contribution
from translations.query import order_by_translation
from translations.helpers import truncate
from versions.models import Version
from .models import Addon, MiniAddon, Persona, FrozenAddon
from .decorators import addon_view_factory

log = commonware.log.getLogger('z.addons')
paypal_log = commonware.log.getLogger('z.paypal')
addon_view = addon_view_factory(qs=Addon.objects.valid)
addon_disabled_view = addon_view_factory(qs=Addon.objects.valid_and_disabled)


def author_addon_clicked(f):
    """Decorator redirecting clicks on "Other add-ons by author"."""
    @functools.wraps(f)
    def decorated(request, *args, **kwargs):
        redirect_id = request.GET.get('addons-author-addons-select', None)
        if not redirect_id:
            return f(request, *args, **kwargs)
        try:
            target_id = int(redirect_id)
            return http.HttpResponsePermanentRedirect(reverse(
                'addons.detail', args=[target_id]))
        except ValueError:
            return http.HttpResponseBadRequest('Invalid add-on ID.')
    return decorated


@author_addon_clicked
@addon_disabled_view
def addon_detail(request, addon):
    """Add-ons details page dispatcher."""
    if addon.disabled_by_user or addon.status == amo.STATUS_DISABLED:
        return jingo.render(request, 'addons/disabled.html',
                            {'addon': addon}, status=404)

    # addon needs to have a version and be valid for this app.
    if addon.type in request.APP.types:
        if addon.type == amo.ADDON_PERSONA:
            return persona_detail(request, addon)
        else:
            if not addon.current_version:
                raise http.Http404

            return extension_detail(request, addon)
    else:
        # Redirect to an app that supports this type.
        try:
            new_app = [a for a in amo.APP_USAGE if addon.type
                       in a.types][0]
        except IndexError:
            raise http.Http404
        else:
            prefixer = urlresolvers.get_url_prefix()
            prefixer.app = new_app.short
            return http.HttpResponsePermanentRedirect(reverse(
                'addons.detail', args=[addon.slug]))


@addon_disabled_view
def impala_addon_detail(request, addon):
    """Add-ons details page dispatcher."""
    if addon.disabled_by_user or addon.status == amo.STATUS_DISABLED:
        return jingo.render(request, 'addons/impala/disabled.html',
                            {'addon': addon}, status=404)

    """Add-ons details page dispatcher."""
    # addon needs to have a version and be valid for this app.
    if addon.type in request.APP.types:
        if addon.type == amo.ADDON_PERSONA:
            return persona_detail(request, addon)
        else:
            if not addon.current_version:
                raise http.Http404

            return impala_extension_detail(request, addon)
    else:
        # Redirect to an app that supports this type.
        try:
            new_app = [a for a in amo.APP_USAGE if addon.type
                       in a.types][0]
        except IndexError:
            raise http.Http404
        else:
            prefixer = urlresolvers.get_url_prefix()
            prefixer.app = new_app.short
            return http.HttpResponsePermanentRedirect(reverse(
                'i_addons.detail', args=[addon.slug]))


def extension_detail(request, addon):
    """Extensions details page."""

    # if current version is incompatible with this app, redirect
    comp_apps = addon.compatible_apps
    if comp_apps and request.APP not in comp_apps:
        prefixer = urlresolvers.get_url_prefix()
        prefixer.app = comp_apps.keys()[0].short
        return http.HttpResponsePermanentRedirect(reverse(
            'addons.detail', args=[addon.slug]))

    # source tracking
    src = request.GET.get('src', 'addondetail')

    # get satisfaction only supports en-US
    lang = translation.to_locale(translation.get_language())
    addon.has_satisfaction = (lang == 'en_US' and
                              addon.get_satisfaction_company)

    # other add-ons from the same author(s)
    author_addons = order_by_translation(addon.authors_other_addons, 'name')

    # tags
    tags = addon.tags.not_blacklisted()

    # addon recommendations
    recommended = MiniAddon.objects.valid().filter(
        recommended_for__addon=addon)[:5]

    # popular collections this addon is part of
    collections = Collection.objects.listed().filter(
        addons=addon, application__id=request.APP.id)

    data = {
        'addon': addon,
        'author_addons': author_addons,

        'src': src,
        'tags': tags,

        'recommendations': recommended,
        'review_form': ReviewForm(),
        'reviews': Review.objects.latest().filter(addon=addon),
        'get_replies': Review.get_replies,

        'collections': collections.order_by('-subscribers')[:3],
        'abuse_form': AbuseForm(request=request),
    }

    return jingo.render(request, 'addons/details.html', data)


@vary_on_headers('X-Requested-With')
def impala_extension_detail(request, addon):
    """Extensions details page."""
    # If current version is incompatible with this app, redirect.
    comp_apps = addon.compatible_apps
    if comp_apps and request.APP not in comp_apps:
        prefixer = urlresolvers.get_url_prefix()
        prefixer.app = comp_apps.keys()[0].short
        return redirect('addons.detail', addon.slug, permanent=True)

    # get satisfaction only supports en-US.
    lang = translation.to_locale(translation.get_language())
    addon.has_satisfaction = (lang == 'en_US' and
                              addon.get_satisfaction_company)

    # Other add-ons from the same author(s).
    author_addons = (Addon.objects.valid().exclude(id=addon.id)
                     .filter(addonuser__listed=True,
                             authors__in=addon.listed_authors))[:6]

    # Addon recommendations.
    recommended = Addon.objects.listed(request.APP).filter(
        recommended_for__addon=addon)[:6]

    # Popular collections this addon is part of.
    collections = Collection.objects.listed().filter(
        addons=addon, application__id=request.APP.id)

    ctx = {
        'addon': addon,
        'author_addons': author_addons,
        'src': request.GET.get('src', 'addondetail'),
        'tags': addon.tags.not_blacklisted(),
        'grouped_ratings': GroupedRating.get(addon.id),
        'recommendations': recommended,
        'review_form': ReviewForm(),
        'reviews': Review.objects.latest().filter(addon=addon),
        'get_replies': Review.get_replies,
        'collections': collections.order_by('-subscribers')[:3],
        'abuse_form': AbuseForm(request=request),
    }

    # details.html just returns the top half of the page for speed. The bottom
    # does a lot more queries we don't want on the initial page load.
    if request.is_ajax():
        return jingo.render(request, 'addons/impala/details-more.html', ctx)
    else:
        return jingo.render(request, 'addons/impala/details.html', ctx)


@mobilized(extension_detail)
def extension_detail(request, addon):
    return jingo.render(request, 'addons/mobile/details.html',
                        {'addon': addon})


def _category_personas(qs, limit):
    f = lambda: randslice(qs, limit=limit)
    key = 'cat-personas:' + qs.query_key()
    return caching.cached(f, key)


@mobile_template('addons/{mobile/}persona_detail.html')
def persona_detail(request, addon, template=None):
    """Details page for Personas."""
    persona = addon.persona

    # this persona's categories
    categories = addon.categories.filter(application=request.APP.id)
    if categories:
        qs = Addon.objects.valid().filter(categories=categories[0])
        category_personas = _category_personas(qs, limit=6)
    else:
        category_personas = None

    # other personas from the same author(s)
    author_personas = Addon.objects.valid().filter(
        persona__author=persona.author,
        type=amo.ADDON_PERSONA).exclude(
            pk=addon.pk).select_related('persona')[:3]

    data = {
        'addon': addon,
        'persona': persona,
        'categories': categories,
        'author_personas': author_personas,
        'category_personas': category_personas,
        # Remora uses persona.author despite there being a display_username.
        'author_gallery': settings.PERSONAS_USER_ROOT % persona.author,
    }
    if not request.MOBILE:
        # tags
        dev_tags, user_tags = addon.tags_partitioned_by_developer
        data.update({
            'dev_tags': dev_tags,
            'user_tags': user_tags,
            'review_form': ReviewForm(),
            'reviews': Review.objects.latest().filter(addon=addon),
            'get_replies': Review.get_replies,
            'search_cat': 'personas',
            'abuse_form': AbuseForm(request=request),
        })

    return jingo.render(request, template, data)


class BaseFilter(object):
    """
    Filters help generate querysets for add-on listings.

    You have to define ``opts`` on the subclass as a sequence of (key, title)
    pairs.  The key is used in GET parameters and the title can be used in the
    view.

    The chosen filter field is combined with the ``base`` queryset using
    the ``key`` found in request.GET.  ``default`` should be a key in ``opts``
    that's used if nothing good is found in request.GET.
    """

    def __init__(self, request, base, key, default):
        self.opts_dict = dict(self.opts)
        self.request = request
        self.base_queryset = base
        self.key = key
        self.field, self.title = self.options(self.request, key, default)
        self.qs = self.filter(self.field)

    def options(self, request, key, default):
        """Get the (option, title) pair we want according to the request."""
        if key in request.GET and request.GET[key] in self.opts_dict:
            opt = request.GET[key]
        else:
            opt = default
        return opt, self.opts_dict[opt]

    def all(self):
        """Get a full mapping of {option: queryset}."""
        return dict((field, self.filter(field)) for field in dict(self.opts))

    def filter(self, field):
        """Get the queryset for the given field."""
        filter = self._filter(field) & self.base_queryset
        order = getattr(self, 'order_%s' % field, None)
        if order:
            return order(filter)
        return filter

    def _filter(self, field):
        return getattr(self, 'filter_%s' % field)()

    def filter_featured(self):
        ids = Addon.featured_random(self.request.APP, self.request.LANG)
        return manual_order(Addon.objects, ids, 'addons.id')

    def filter_popular(self):
        return (Addon.objects.order_by('-weekly_downloads')
                .with_index(addons='downloads_type_idx'))

    def filter_users(self):
        return (Addon.objects.order_by('-average_daily_users')
                .with_index(addons='adus_type_idx'))

    def filter_created(self):
        return (Addon.objects.order_by('-created')
                .with_index(addons='created_type_idx'))

    def filter_updated(self):
        return (Addon.objects.order_by('-last_updated')
                .with_index(addons='last_updated_type_idx'))

    def filter_rating(self):
        return (Addon.objects.order_by('-bayesian_rating')
                .with_index(addons='rating_type_idx'))

    def filter_name(self):
        return order_by_translation(Addon.objects.all(), 'name')


class ESBaseFilter(BaseFilter):
    """BaseFilter that uses elasticsearch."""

    def __init__(self, request, base, key, default):
        super(ESBaseFilter, self).__init__(request, base, key, default)

    def filter(self, field):
        sorts = {'name': 'name_sort',
                 'created': '-created',
                 'updated': '-last_updated',
                 'popular': '-weekly_downloads',
                 'users': '-average_daily_users',
                 'rating': '-bayesian_rating'}
        return self.base_queryset.order_by(sorts[field])


class HomepageFilter(BaseFilter):
    opts = (('featured', _lazy(u'Featured')),
            ('popular', _lazy(u'Popular')),
            ('new', _lazy(u'Recently Added')),
            ('updated', _lazy(u'Recently Updated')))

    filter_new = BaseFilter.filter_created


def home(request):
    # Add-ons.
    base = Addon.objects.listed(request.APP).exclude(type=amo.ADDON_PERSONA)
    filter = HomepageFilter(request, base, key='browse', default='featured')
    addon_sets = dict((key, qs[:4]) for key, qs in filter.all().items())

    # Collections.
    q = Collection.objects.filter(listed=True, application=request.APP.id)
    collections = q.order_by('-weekly_subscribers')[:3]
    promobox = CollectionPromoBox(request)

    # Global stats.
    try:
        downloads = (GlobalStat.objects.filter(name='addon_total_downloads')
                     .latest())
    except GlobalStat.DoesNotExist:
        downloads = None

    return jingo.render(request, 'addons/home.html',
                        {'downloads': downloads,
                         'filter': filter, 'addon_sets': addon_sets,
                         'collections': collections, 'promobox': promobox})


def impala_home(request):
    # Add-ons.
    base = Addon.objects.listed(request.APP).filter(type=amo.ADDON_EXTENSION)
    featured_ext = FeaturedManager.featured_ids(request.APP, request.LANG,
                                                type=amo.ADDON_EXTENSION)
    featured_personas = FeaturedManager.featured_ids(request.APP, request.LANG,
                                                     type=amo.ADDON_PERSONA)
    # This is lame for performance. Kill it with ES.
    frozen = FrozenAddon.objects.values_list('addon', flat=True)

    # Collections.
    collections = Collection.objects.filter(listed=True,
                                            application=request.APP.id,
                                            type=amo.COLLECTION_FEATURED)
    featured = base.filter(id__in=featured_ext[:18])
    popular = base.exclude(id__in=frozen).order_by('-average_daily_users')[:10]
    hotness = base.exclude(id__in=frozen).order_by('-hotness')[:18]
    personas = (Addon.objects.listed(request.APP)
                .filter(type=amo.ADDON_PERSONA, id__in=featured_personas[:18]))

    return jingo.render(request, 'addons/impala/home.html',
                        {'popular': popular, 'featured': featured,
                         'hotness': hotness, 'personas': personas,
                         'src': 'homepage', 'collections': collections})


@mobilized(home)
@cache_page(60 * 10)
def home(request):
    # Shuffle the list and get 3 items.
    rand = lambda xs: random.shuffle(xs) or xs[:3]
    # Get some featured add-ons with randomness.
    featured = Addon.featured_random(request.APP, request.LANG)
    # Get 10 popular add-ons, then pick 3 at random.
    qs = list(Addon.objects.listed(request.APP)
                   .order_by('-average_daily_users')
                   .values_list('id', flat=True)[:10])
    popular = rand(qs)
    # Do one query and split up the add-ons.
    addons = Addon.objects.filter(id__in=featured + popular)
    featured = [a for a in addons if a.id in featured]
    popular = sorted([a for a in addons if a.id in popular],
                     key=attrgetter('average_daily_users'), reverse=True)
    return jingo.render(request, 'addons/mobile/home.html',
                        {'featured': featured, 'popular': popular})


def homepage_promos(request):
    from discovery.views import get_modules
    platform = amo.PLATFORM_DICT.get(request.GET.get('platform'),
                                     amo.PLATFORM_ALL)
    version = request.GET.get('version')
    modules = get_modules(request, platform.api_name, version)
    return jingo.render(request, 'addons/impala/homepage_promos.html',
                        {'modules': modules})


class CollectionPromoBox(object):

    def __init__(self, request):
        self.request = request

    def features(self):
        return CollectionFeature.objects.all()

    def collections(self):
        features = self.features()
        lang = translation.to_language(translation.get_language())
        locale = Q(locale='') | Q(locale=lang)
        promos = (CollectionPromo.objects.filter(locale)
                  .filter(collection_feature__in=features)
                  .transform(CollectionPromo.transformer))
        groups = sorted_groupby(promos, 'collection_feature_id')

        # We key by feature_id and locale, so we can favor locale specific
        # promos.
        promo_dict = {}
        for feature_id, v in groups:
            promo = v.next()
            key = (feature_id, translation.to_language(promo.locale))
            promo_dict[key] = promo

        rv = {}
        # If we can, we favor locale specific collections.
        for feature in features:
            key = (feature.id, lang)
            if key not in promo_dict:
                key = (feature.id, '')
                if key not in promo_dict:
                    continue

            # We only want to see public add-ons on the front page.
            c = promo_dict[key].collection
            c.public_addons = c.addons.all() & Addon.objects.public()
            rv[feature] = c

        return rv

    def __nonzero__(self):
        return self.request.APP == amo.FIREFOX


@addon_view
def eula(request, addon, file_id=None):
    if not addon.eula:
        return http.HttpResponseRedirect(addon.get_url_path())
    if file_id is not None:
        version = get_object_or_404(addon.versions, files__id=file_id)
    else:
        version = addon.current_version

    return jingo.render(request, 'addons/eula.html',
                        {'addon': addon, 'version': version})


@addon_view
def impala_eula(request, addon, file_id=None):
    if not addon.eula:
        return http.HttpResponseRedirect(addon.get_url_path(impala=True))
    if file_id:
        version = get_object_or_404(addon.versions, files__id=file_id)
    else:
        version = addon.current_version
    return jingo.render(request, 'addons/impala/eula.html',
                        {'addon': addon, 'version': version})


@addon_view
def privacy(request, addon):
    if not addon.privacy_policy:
        return http.HttpResponseRedirect(addon.get_url_path())

    return jingo.render(request, 'addons/privacy.html', {'addon': addon})


@addon_view
def impala_privacy(request, addon):
    if not addon.privacy_policy:
        return http.HttpResponseRedirect(addon.get_url_path(impala=True))
    return jingo.render(request, 'addons/impala/privacy.html',
                        {'addon': addon})


def _developers(request, addon, page, template=None):
    if 'version' in request.GET:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=request.GET['version'])[0]
    else:
        version = addon.current_version

    if 'src' in request.GET:
        contribution_src = src = request.GET['src']
    else:
        # Download src and contribution_src are be different.
        src = {'developers': 'developers',
               'installed': 'meet-the-developer-post-install',
               'roadblock': 'meetthedeveloper_roadblock'}.get(page, None)
        contribution_src = {'developers': 'meet-developers',
                            'installed': 'post-download',
                            'roadblock': 'roadblock'}.get(page, None)

    if addon.is_persona():
        raise http.Http404()
    author_addons = order_by_translation(addon.authors_other_addons, 'name')
    return jingo.render(request, template,
                        {'addon': addon, 'author_addons': author_addons,
                         'page': page, 'src': src,
                         'contribution_src': contribution_src,
                         'version': version})


@addon_view
def developers(request, addon, page):
    if 'version' in request.GET:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=request.GET['version'])[0]
    else:
        version = addon.current_version

    if 'src' in request.GET:
        contribution_src = src = request.GET['src']
    else:
        # Download src and contribution_src are be different.
        src = {'developers': 'developers',
               'installed': 'meet-the-developer-post-install',
               'roadblock': 'meetthedeveloper_roadblock'}.get(page, None)
        contribution_src = {'developers': 'meet-developers',
                            'installed': 'post-download',
                            'roadblock': 'roadblock'}.get(page, None)

    if addon.is_persona():
        raise http.Http404()
    author_addons = order_by_translation(addon.authors_other_addons, 'name')
    return jingo.render(request, 'addons/developers.html',
                        {'addon': addon, 'author_addons': author_addons,
                         'page': page, 'src': src,
                         'contribution_src': contribution_src,
                         'version': version})


@addon_view
def impala_developers(request, addon, page):
    if addon.is_persona():
        raise http.Http404()
    if 'version' in request.GET:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=request.GET['version'])[0]
    else:
        version = addon.current_version

    if 'src' in request.GET:
        contribution_src = src = request.GET['src']
    else:
        page_srcs = {
            'developers': ('developers', 'meet-developers'),
            'installed': ('meet-the-developer-post-install', 'post-download'),
            'roadblock': ('meetthedeveloper_roadblock', 'roadblock'),
        }
        # Download src and contribution_src are different.
        src, contribution_src = page_srcs.get(page)
    return jingo.render(request, 'addons/impala/developers.html',
                        {'addon': addon, 'page': page, 'src': src,
                         'contribution_src': contribution_src,
                         'version': version})


@addon_view
def contribute(request, addon):
    contrib_type = request.GET.get('type', 'suggested')
    is_suggested = contrib_type == 'suggested'
    source = request.GET.get('source', '')
    comment = request.GET.get('comment', '')

    amount = {
        'suggested': addon.suggested_amount,
        'onetime': request.GET.get('onetime-amount', '')}.get(contrib_type, '')
    if not amount:
        amount = settings.DEFAULT_SUGGESTED_CONTRIBUTION

    contribution_uuid = hashlib.md5(str(uuid.uuid4())).hexdigest()
    uuid_qs = urllib.urlencode({'uuid': contribution_uuid})

    if addon.charity:
        name, paypal_id = addon.charity.name, addon.charity.paypal
    else:
        name, paypal_id = addon.name, addon.paypal_id
    contrib_for = _(u'Contribution for {0}').format(jinja2.escape(name))

    paykey, nice_error = None, None
    try:
        paykey = paypal.get_paykey({
            'return_url': absolutify('%s?%s' % (reverse('addons.paypal',
                                                args=[addon.slug, 'complete']),
                                                uuid_qs)),
            'cancel_url': absolutify('%s?%s' % (reverse('addons.paypal',
                                                args=[addon.slug, 'cancel']),
                                                uuid_qs)),
            'uuid': contribution_uuid,
            'amount': str(amount),
            'email': paypal_id,
            'ip': request.META.get('REMOTE_ADDR'),
            'memo': contrib_for})
    except paypal.AuthError, error:
        paypal_log.error('Authentication error: %s' % error)
        nice_error = _('There was a problem communicating with Paypal.')
    except Exception, error:
        paypal_log.error('Error: %s' % error)
        nice_error = _('There was a problem with that contribution.')

    if paykey:
        contrib = Contribution(addon_id=addon.id,
                           charity_id=addon.charity_id,
                           amount=amount,
                           source=source,
                           source_locale=request.LANG,
                           annoying=addon.annoying,
                           uuid=str(contribution_uuid),
                           is_suggested=is_suggested,
                           suggested_amount=addon.suggested_amount,
                           comment=comment,
                           paykey=paykey)
        contrib.save()

    assert settings.PAYPAL_FLOW_URL, 'settings.PAYPAL_FLOW_URL is not defined'

    url = '%s?paykey=%s' % (settings.PAYPAL_FLOW_URL, paykey)
    if request.GET.get('result_type') == 'json' or request.is_ajax():
        # If there was an error getting the paykey, then JSON will
        # not have a paykey and the JS can cope appropriately.
        return http.HttpResponse(json.dumps({'url': url,
                                             'paykey': paykey,
                                             'error': nice_error}),
                                 content_type='application/json')
    return http.HttpResponseRedirect(url)


def contribute_url_params(business, addon_id, item_name, return_url,
                          amount='', item_number='',
                          monthly=False, comment=''):

    lang = translation.get_language()
    try:
        paypal_lang = settings.PAYPAL_COUNTRYMAP[lang]
    except KeyError:
        lang = lang.split('-')[0]
        paypal_lang = settings.PAYPAL_COUNTRYMAP.get(lang, 'US')

    # Get all the data elements that will be URL params
    # on the Paypal redirect URL.
    data = {'business': business,
            'item_name': item_name,
            'item_number': item_number,
            'bn': settings.PAYPAL_BN + '-AddonID' + str(addon_id),
            'no_shipping': '1',
            'return': return_url,
            'charset': 'utf-8',
            'lc': paypal_lang,
            'notify_url': "%s%s" % (settings.SERVICES_URL,
                                    reverse('amo.paypal'))}

    if not monthly:
        data['cmd'] = '_donations'
        if amount:
            data['amount'] = amount
    else:
        data.update({
            'cmd': '_xclick-subscriptions',
            'p3': '12',  # duration: for 12 months
            't3': 'M',  # time unit, 'M' for month
            'a3': amount,  # recurring contribution amount
            'no_note': '1'})  # required: no "note" text field for user

    if comment:
        data['custom'] = comment

    return data


@addon_view
def paypal_result(request, addon, status):
    uuid = request.GET.get('uuid')
    if not uuid:
        raise http.Http404()
    if status == 'cancel':
        log.info('User cancelled contribution: %s' % uuid)
    else:
        log.info('User completed contribution: %s' % uuid)
    response = jingo.render(request, 'addons/paypal_result.html',
                            {'addon': addon, 'status': status})
    response['x-frame-options'] = 'allow'
    return response


@addon_view
def share(request, addon):
    """Add-on sharing"""
    return share_redirect(request, addon, name=addon.name,
                          description=truncate(addon.summary, length=250))


def _license(request, addon, version=None, template=None):
    if version is not None:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=version)[0]
    else:
        version = addon.current_version
    if not (version and version.license):
        raise http.Http404()
    return jingo.render(request, template, dict(addon=addon, version=version))


@addon_view
def license(request, addon, version=None):
    return _license(request, addon, version, 'addons/license.html')


@addon_view
def impala_license(request, addon, version=None):
    return _license(request, addon, version, 'addons/impala/license.html')


def license_redirect(request, version):
    version = get_object_or_404(Version, pk=version)
    return redirect(version.license_url(), permanent=True)


@session_csrf.anonymous_csrf_exempt
@addon_view
def report_abuse(request, addon):
    form = AbuseForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        send_abuse_report(request, addon, form.cleaned_data['text'])
        messages.success(request, _('Abuse reported.'))
        return redirect('addons.detail', addon.slug)
    else:
        return jingo.render(request, 'addons/report_abuse_full.html',
                            {'addon': addon, 'abuse_form': form, })


@cache_control(max_age=60 * 60 * 24)
def persona_redirect(request, persona_id):
    persona = get_object_or_404(Persona, persona_id=persona_id)
    return redirect('addons.detail', persona.addon.slug, permanent=True)
