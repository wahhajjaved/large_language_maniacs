import datetime
import re

import colorsys
import difflib
import logging
import tagging
from actstream import action
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.http import (HttpResponse, HttpResponseRedirect, Http404,
                         HttpResponseForbidden)
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.utils import simplejson as json
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy, ugettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, ListView
from tagging.models import TaggedItem, Tag

import models
from models import Committee, CommitteeMeeting, Topic
from auxiliary.views import GetMoreView, BaseTagMemberListView
from forms import EditTopicForm, LinksFormset
from hashnav import method_decorator as hashnav_method_decorator
from knesset.utils import clean_string
from laws.models import Bill, PrivateProposal
from links.models import Link
from mks.models import Member


logger = logging.getLogger("open-knesset.committees.views")


class CommitteeListView(ListView):
    context_object_name = 'committees'
    queryset = Committee.objects.exclude(type='plenum')
    paginate_by = 20
    INITIAL_TOPICS = 10

    def get_context_data(self, **kwargs):
        context = super(CommitteeListView, self).get_context_data(**kwargs)
        context["topics"] = Topic.objects.summary()[:self.INITIAL_TOPICS]
        context["topics_more"] = Topic.objects.summary().count() > self.INITIAL_TOPICS
        context['tags_cloud'] = Tag.objects.cloud_for_model(CommitteeMeeting)
        context["INITIAL_TOPICS"] = self.INITIAL_TOPICS

        return context


class TopicsMoreView(GetMoreView):
    """Get partially rendered member actions content for AJAX calls to 'More'"""

    paginate_by = 20
    template_name = 'committees/_topics_summary.html'

    def get_queryset(self):
        return Topic.objects.summary()


class CommitteeDetailView(DetailView):

    model = Committee

    def get_context_data(self, *args, **kwargs):
        context = super(CommitteeDetailView, self).get_context_data(*args, **kwargs)
        cm = context['object']
        cached_context = cache.get('committee_detail_%d' % cm.id, {})
        if not cached_context:
            cached_context['chairpersons'] = cm.chairpersons.all()
            cached_context['replacements'] = cm.replacements.all()
            cached_context['members'] = cm.members_by_presence()
            recent_meetings = cm.recent_meetings()
            cached_context['meetings_list'] = recent_meetings
            ref_date = recent_meetings[0].date+datetime.timedelta(1) \
                    if recent_meetings.count() > 0 \
                    else datetime.datetime.now()
            cached_context['future_meetings_list'] = cm.future_meetings()
            cur_date = datetime.datetime.now()
            cached_context['protocol_not_yet_published_list'] = \
                    cm.events.filter(when__gt = ref_date, when__lte = cur_date)
            # cache.set('committee_detail_%d' % cm.id, cached_context,
            #           settings.LONG_CACHE_TIME)
        context.update(cached_context)
        context['annotations'] = cm.annotations.order_by('-timestamp')
        context['topics'] = cm.topic_set.summary()[:5]
        return context


class MeetingDetailView(DetailView):

    model = CommitteeMeeting

    def get_queryset(self):
        return super(MeetingDetailView, self).get_queryset().select_related('committee')

    def get_context_data(self, *args, **kwargs):
        context = super(MeetingDetailView, self).get_context_data(*args, **kwargs)
        cm = context['object']
        colors = {}
        speakers = cm.parts.order_by('speaker__mk').values_list('header','speaker__mk').distinct()
        n = speakers.count()
        for (i,(p,mk)) in enumerate(speakers):
            (r,g,b) = colorsys.hsv_to_rgb(float(i)/n, 0.5 if mk else 0.3, 255)
            colors[p] = 'rgb(%i, %i, %i)' % (r, g, b)
        context['title'] = _('%(committee)s meeting on %(date)s') % {'committee':cm.committee.name, 'date':cm.date_string}
        context['description'] = _('%(committee)s meeting on %(date)s on topic %(topic)s') \
                                   % {'committee':cm.committee.name,
                                      'date':cm.date_string,
                                      'topic':cm.topics}
        context['description'] = clean_string(context['description']).replace('"', '')
        page = self.request.GET.get('page', None)
        if page:
            context['description'] += _(' page %(page)s') % {'page': page}
        context['colors'] = colors
        parts_lengths = {}
        for part in cm.parts.all():
            parts_lengths[part.id] = len(part.body)
        context['parts_lengths'] = json.dumps(parts_lengths)
        context['paginate_by'] = models.COMMITTEE_PROTOCOL_PAGINATE_BY

        if cm.committee.type == 'plenum':
            context['members'] = cm.mks_attended.order_by('name')
            context['hide_member_presence'] = True
        else:
            #get meeting members with presence calculation
            meeting_members_ids = set(m.id for m in cm.mks_attended.all())
            context['members'] = cm.committee.members_by_presence(ids=meeting_members_ids)
            context['hide_member_presence'] = False

        return context

    @hashnav_method_decorator(login_required)
    def post(self, request, **kwargs):
        cm = get_object_or_404(CommitteeMeeting, pk=kwargs['pk'])
        bill = None
        request = self.request
        user_input_type = request.POST.get('user_input_type')
        if user_input_type == 'bill':
            bill_id = request.POST.get('bill_id')
            if bill_id.isdigit():
                bill = get_object_or_404(Bill, pk=bill_id)
            else: # not a number, maybe its p/1234
                m = re.findall('\d+',bill_id)
                if len(m)!=1:
                    raise ValueError("didn't find exactly 1 number in bill_id=%s" % bill_id)
                pp = PrivateProposal.objects.get(proposal_id=m[0])
                bill = pp.bill

            if bill.stage in ['1','2','-2','3']: # this bill is in early stage, so cm must be one of the first meetings
                bill.first_committee_meetings.add(cm)
            else: # this bill is in later stages
                v = bill.first_vote # look for first vote
                if v and v.time.date() < cm.date:          # and check if the cm is after it,
                    bill.second_committee_meetings.add(cm) # if so, this is a second committee meeting
                else: # otherwise, assume its first cms.
                    bill.first_committee_meetings.add(cm)
            bill.update_stage()
            action.send(request.user, verb='added-bill-to-cm',
                description=cm,
                target=bill,
                timestamp=datetime.datetime.now())

        if user_input_type == 'mk':
            mk_names = Member.objects.values_list('name', flat=True)
            mk_name = difflib.get_close_matches(request.POST.get('mk_name'),
                                                mk_names)[0]
            mk = Member.objects.get(name=mk_name)
            cm.mks_attended.add(mk)
            cm.save()  # just to signal, so the attended Action gets created.
            action.send(request.user,
                        verb='added-mk-to-cm',
                        description=cm,
                        target=mk,
                        timestamp=datetime.datetime.now())

        if user_input_type == 'remove-mk':
            mk_names = Member.objects.values_list('name', flat=True)
            mk_name = difflib.get_close_matches(request.POST.get('mk_name'),
                                                mk_names)[0]
            mk = Member.objects.get(name=mk_name)
            cm.mks_attended.remove(mk)
            cm.save()  # just to signal, so the attended Action gets created.
            action.send(request.user,
                        verb='removed-mk-to-cm',
                        description=cm,
                        target=mk,
                        timestamp=datetime.datetime.now())

        return HttpResponseRedirect(".")

_('added-bill-to-cm')
_('added-mk-to-cm')
_('removed-mk-from-cm')


class TopicListView(ListView):
    model = Topic
    context_object_name = 'topics'

    def get_queryset(self):
        qs = Topic.objects.get_public()
        if "committee_id" in self.kwargs:
            qs = qs.filter(committees__id=self.kwargs["committee_id"])
        return qs

    def get_context_data(self, **kwargs):
        context = super(TopicListView, self).get_context_data(**kwargs)
        committee_id = self.kwargs.get("committee_id", False)
        context["committee"] = committee_id and Committee.objects.get(pk=committee_id)
        return context


class TopicDetailView(DetailView):

    model = Topic
    context_object_name = 'topic'

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, *args, **kwargs):
        return super(TopicDetailView, self).dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(TopicDetailView, self).get_context_data(**kwargs)
        topic = context['object']
        if self.request.user.is_authenticated():
            p = self.request.user.get_profile()
            watched = topic in p.topics
        else:
            watched = False
        context['watched_object'] = watched
        return context

@login_required
def edit_topic(request, committee_id, topic_id=None):
    if request.method == 'POST':
        if topic_id:
            t = Topic.objects.get(pk=topic_id)
            if not t.can_edit(request.user):
                return HttpResponseForbidden()
        else:
            t = None
        edit_form = EditTopicForm(data=request.POST, instance=t)
        links_formset = LinksFormset(request.POST)
        if edit_form.is_valid() and links_formset.is_valid():
            topic = edit_form.save(commit=False)
            if topic_id:
                topic.id = topic_id
            else: # new topic
                topic.creator = request.user
            topic.save()
            edit_form.save_m2m()
            links = links_formset.save(commit=False)
            ct = ContentType.objects.get_for_model(topic)
            for link in links:
                link.content_type = ct
                link.object_pk = topic.id
                link.save()

            messages.add_message(request, messages.INFO, 'Topic has been updated')
            return HttpResponseRedirect(
                reverse('topic-detail',args=[topic.id]))

    if request.method == 'GET':
        if topic_id: # editing existing topic
            t = Topic.objects.get(pk=topic_id)
            if not t.can_edit(request.user):
                return HttpResponseForbidden()
            edit_form = EditTopicForm(instance=t)
            ct = ContentType.objects.get_for_model(t)
            links_formset = LinksFormset(queryset=Link.objects.filter(
                content_type=ct, object_pk=t.id))
        else: # create new topic for given committee
            c = Committee.objects.get(pk=committee_id)
            edit_form = EditTopicForm(initial={'committees':[c]})
            links_formset = LinksFormset(queryset=Link.objects.none())
    return render_to_response('committees/edit_topic.html',
        context_instance=RequestContext(request,
            {'edit_form': edit_form,
             'links_formset': links_formset,
            }))

@login_required
def delete_topic(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    if topic.can_edit(request.user):
        # Delete on POST
        if request.method == 'POST':
            topic.status = models.TOPIC_DELETED
            topic.save()
            return HttpResponseRedirect(reverse('committee-detail',
                                                args=[topic.committees.all()[0].id]))

        # Render a form on GET
        else:
            return render_to_response('committees/delete_topic.html',
                {'topic': topic},
                RequestContext(request)
            )
    else:
        raise Http404


class MeetingsListView(ListView):

    allow_empty = False
    paginate_by = 20

    def get_context_data(self, *args, **kwargs):
        context = super(MeetingsListView, self).get_context_data(*args,
                                                                 **kwargs)
        committee_id = self.kwargs.get('committee_id')
        if committee_id:
            items = context['object_list']
            committee = items[0].committee

            if committee.type == 'plenum':
                committee_name = _('Knesset Plenum')
            else:
                committee_name = committee.name
            context['title'] = _('All meetings by %(committee)s') % {
                'committee': committee_name}
            context['committee'] = committee
        else:
            context['title'] = _('Parliamentary committees meetings')
        context['committee_id'] = committee_id

        context['none'] = _('No %(object_type)s found') % {
            'object_type': CommitteeMeeting._meta.verbose_name_plural}

        return context

    def get_queryset(self):
        c_id = self.kwargs.get('committee_id', None)
        qs = CommitteeMeeting.objects.filter_and_order(**dict(self.request.GET))
        if c_id:
            qs = qs.filter(committee__id=c_id)
        return qs

def meeting_list_by_date(request, *args, **kwargs):
    committee_id = kwargs.get('committee_id')
    date_string = kwargs.get('date')
    try:
        date = datetime.datetime.strptime(date_string, '%Y-%m-%d').date()
    except:
        raise Http404()

    context = {}
    if committee_id:
        qs = CommitteeMeeting.objects.filter(committee_id=committee_id)
        committee = qs[0].committee.name
        context['committee'] = committee
        context['title'] = _('Meetings by %(committee)s on date %(date)s') % {'committee': committee, 'date': date}
        context['committee_id'] = committee_id
    else:
        context['title'] = _('Parliamentary committees meetings on date %(date)s') % {'date': date}
        qs = CommitteeMeeting.objects.all()
    qs = qs.filter(date=date)

    context['object_list'] = qs
    context['none'] = _('No %(object_type)s found') % {'object_type': CommitteeMeeting._meta.verbose_name_plural}

    return render_to_response("committees/committeemeeting_list.html",
                              context, context_instance=RequestContext(request))


class MeetingTagListView(BaseTagMemberListView):

    template_name = 'committees/committeemeeting_list_by_tag.html'
    url_to_reverse = 'committeemeeting-tag'

    def get_queryset(self):
        return TaggedItem.objects.get_by_model(CommitteeMeeting,
                                               self.tag_instance)

    def get_mks_cloud(self):
        mks = [cm.mks_attended.all() for cm in
               TaggedItem.objects.get_by_model(
                   CommitteeMeeting, self.tag_instance)]
        d = {}
        for mk in mks:
            for p in mk:
                d[p] = d.get(p, 0) + 1
        # now d is a dict: MK -> number of meetings in this tag
        mks = d.keys()
        for mk in mks:
            mk.count = d[mk]
        return tagging.utils.calculate_cloud(mks)

    def get_context_data(self, *args, **kwargs):
        context = super(MeetingTagListView, self).get_context_data(*args,
                                                                   **kwargs)

        context['title'] = ugettext_lazy(
            'Committee Meetings tagged %(tag)s') % {
                'tag': self.tag_instance.name}

        context['members'] = self.get_mks_cloud()
        return context

# TODO: This has be replaced by the class based view above for Django 1.5.
# Remove once working
#
#def meeting_tag(request, tag):
#    tag_instance = get_tag(tag)
#    if tag_instance is None:
#        raise Http404(_('No Tag found matching "%s".') % tag)
#
#    extra_context = {'tag':tag_instance}
#    extra_context['tag_url'] = reverse('committeemeeting-tag',args=[tag_instance])
#    extra_context['title'] = ugettext_lazy('Committee Meetings tagged %(tag)s') % {'tag': tag}
#    qs = CommitteeMeeting
#    queryset = TaggedItem.objects.get_by_model(qs, tag_instance)
#    mks = [cm.mks_attended.all() for cm in
#           TaggedItem.objects.get_by_model(CommitteeMeeting, tag_instance)]
#    d = {}
#    for mk in mks:
#        for p in mk:
#            d[p] = d.get(p,0)+1
#    # now d is a dict: MK -> number of meetings in this tag
#    mks = d.keys()
#    for mk in mks:
#        mk.count = d[mk]
#    mks = tagging.utils.calculate_cloud(mks)
#    extra_context['members'] = mks
#    return generic.list_detail.object_list(request, queryset,
#        template_name='committees/committeemeeting_list_by_tag.html', extra_context=extra_context)

def delete_topic_rating(request, object_id):
    if request.method=='POST':
        topic= get_object_or_404(Topic, pk=object_id)
        topic.rating.delete(request.user, request.META['REMOTE_ADDR'])
        return HttpResponse('Vote deleted.')

