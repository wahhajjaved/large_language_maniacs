from django.shortcuts import render_to_response, render
from django.template.context import RequestContext
from django.template.loader import render_to_string
from django.db.models import ObjectDoesNotExist, Q
from django.http import HttpResponse
from django.core import serializers
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404
from django.utils.text import slugify

from bccf.models import BCCFPage, BCCFChildPage, BCCFBabyPage, BCCFTopic, UserProfile
from bccf.settings import MEDIA_URL, BCCF_RESOURCE_TYPES, BCCF_SPECIAL_PAGES
from pybb.models import Topic

import logging
import json
import datetime

log = logging.getLogger(__name__)

@staff_member_required
def bccf_admin_page_ordering(request):
    """
    Updates the ordering of pages via AJAX from within the admin.
    """

    def get_id(s):
        s = s.split("_")[-1]
        return s if s and s != "null" else None
    page = get_object_or_404(BCCFChildPage, id=get_id(request.POST['id']))
    old_parent_id = page.parent_id
    new_parent_id = get_id(request.POST['parent_id'])
    if new_parent_id != page.parent_id:
        # Parent changed - set the new parent and re-order the
        # previous siblings.
        if new_parent_id is not None:
            new_parent = BCCFChildPage.objects.get(id=new_parent_id)
        else:
            new_parent = None
        page.set_parent(new_parent)
        pages = BCCFChildPage.objects.filter(parent_id=old_parent_id)
        for i, page in enumerate(pages.order_by('_order')):
            BCCFChildPage.objects.filter(id=page.id).update(_order=i)  # @UndefinedVariable
    # Set the new order for the moved page and its current siblings.
    for i, page_id in enumerate(request.POST.getlist('siblings[]')):
        BCCFChildPage.objects.filter(id=get_id(page_id)).update(_order=i)  # @UndefinedVariable - PyDev is dumb about objects' attributes
    return HttpResponse("ok")

def page(request, parent=None, child=None, baby=None):
    if not request.is_ajax():
        page = get_object_or_404(BCCFPage, slug__exact='bccf/%s' % parent)
        log.debug(page)
        if parent in BCCF_SPECIAL_PAGES:
            template = u"pages/%s.html" % parent
        else:
            template = u"pages/bccfpage.html"
    else:
        baby_obj = None
        if baby and baby != 'baby-resources' and baby != 'child-home' and baby != 'child-info':
            baby_temp = BCCFBabyPage.objects.get(slug=('%s/%s') % (child, baby))
            baby_obj = slugify(baby_temp.title)
        elif baby:
            baby_obj = baby
        child_obj = BCCFChildPage.objects.get(slug=child)
        babies = BCCFBabyPage.objects.filter(parent=child_obj).order_by('order')
        if child_obj.content_model == 'event':
            babies = BCCFChildPage.objects.filter(~Q(content_model='formpublished'), parent=child_obj).order_by('_order')  # @UndefinedVariable
        template = 'generic/sub_page.html'
    context = RequestContext(request, locals())
    return render_to_response(template, {}, context_instance=context)

def resource_type_page(request, type):
    page = get_object_or_404(BCCFPage, slug__exact='bccf/resources')
    child = None
    context = RequestContext(request, locals())
    return render_to_response('pages/resources.html', {}, context_instance=context)

def topic_page(request, topic):
    page = get_object_or_404(BCCFTopic, slug=topic)
    context = RequestContext(request, locals())
    return render_to_response('pages/bccftopic.html', {}, context_instance=context)

def user_list(request):
    page = BCCFPage.objects.get(slug__exact='member/directory');
    p = request.GET.get('page')
    f = request.GET.get('filter')
    t = request.GET.get('type')
    
    users_list = UserProfile.objects.get_directory()
    
    if f and f != 'all':
        users_list = users_list.filter(Q(user__last_name__istartswith=f) | Q(user__first_name__istartswith=f))
    if t and t != 'all':
        users_list = users_list.filter(membership_type=t)
        
    users_list = users_list.order_by('user__last_name', 'user__first_name')
    paginator = Paginator(users_list, 10)
    try:
        recordlist = paginator.page(p)
    except PageNotAnInteger:
        recordlist = paginator.page(1)
    except EmptyPage:
        recordlist = paginator.page(paginator.num_pages)
    context = RequestContext(request, locals())
    return render_to_response('bccf/user_directory.html', {}, context_instance=context)

def next(request, parent, which, offset):
    if request.is_ajax():
        obj = BCCFPage.objects.get(id=parent)

        slides = BCCFChildPage.objects.by_gparent(obj)
        limit = int(offset)+12
        
        if obj.slug == 'bccf/resources' or obj.slug == 'bccf/tag':
            slides = slides.filter(content_type=which)
        elif which == 'parent' or which == 'professional':
            slides = slides.filter(page_for=which)     
        
        slides = slides.order_by('-created')[offset:limit]
        parts = {
            'slide': render_to_string('generic/carousel_slide_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL}),
            'grid': render_to_string('generic/carousel_grid_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL})
        }
        return HttpResponse(json.dumps(parts), content_type="application/json")
    else:
        return HttpResponse('No')

def topic_next(request, topic, which, offset):
    if request.is_ajax():
        limit = int(offset)+12
        topic = BCCFTopic.objects.get(id=topic)

        slides = BCCFChildPage.objects.by_topic(topic).filter(page_for=which).order_by('-created')[offset:limit]
        parts = {
            'slide': render_to_string('generic/carousel_slide_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL}),
            'grid': render_to_string('generic/carousel_grid_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL}),
        }
        return HttpResponse(json.dumps(parts), content_type="application/json")
    else:
        return HttpResponse('No')

def filter(request, query=None, type='slide'):
    if request.is_ajax():
        if query != '':
            topics = BCCFTopic.objects.filter(Q(title__icontains=query))
            slides = BCCFChildPage.objects.filter(Q(title__icontains=query) | Q(content__icontains=query) | Q(bccf_topic=topics), content_model='topic', status=2).distinct()
        else:
            slides = BCCFChildPage.objects.filter(content_model='topic', status=2).order_by('-created')[:12]
        parts = {
            'slide': render_to_string('generic/carousel_slide_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL}),
            'grid': render_to_string('generic/carousel_grid_part.html', {'slides':slides, 'MEDIA_URL':MEDIA_URL})
        }
        return HttpResponse(json.dumps(parts), content_type="application/json")
    else:
        return HttpResponse('No')
