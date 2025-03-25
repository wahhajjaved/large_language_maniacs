# -*- coding: utf-8 -*-

from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.shortcuts import render_to_response, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from content.models import InterestGroup, IgProposal, IgProposalForm, Entry, Dict, Logo, DataList
from content.forms import SubmitForm, SubmitFormPlugin
from taggit.models import Tag
from bs4 import BeautifulSoup
from urllib import urlopen, quote_plus, urlretrieve
import tldextract
from django.template.defaultfilters import slugify
from django.contrib import messages
from datetime import datetime, timedelta
from django.conf import settings

import re
import json
import urllib2
import string
import urlparse

def get_referer_view(request, default=None):
    ''' 
    Return the referer view of the current request

    Example:

        def some_view(request):
            ...
            referer_view = get_referer_view(request)
            return HttpResponseRedirect(referer_view, '/accounts/login/')
    '''

    # if the user typed the url directly in the browser's address bar

    referer = request.META.get('HTTP_REFERER')
    if not referer:
        return default

    # remove the protocol and split the url at the slashes

    referer = re.sub('^https?:\/\/', '', referer).split('/')
    if referer[0] != request.META.get('SERVER_NAME'):
        return default

    # add the slash at the relative path's view and finished

    referer = u'/' + u'/'.join(referer[1:])
    return referer


@login_required
def myig(request):
    """
    The main page presenting subscribed IGs.
    """

    user = request.user

    subscribed = user.interestgroup_set.all().order_by('-members')

    template_data = {'subscribed': subscribed}
    return render_to_response('content/myig.html', template_data, context_instance=RequestContext(request))


    # return render_to_response('/content/ig/misc/votes.html', template_data, context_instance=RequestContext(request))

def ig(request):
    """
    The main page presenting IGs.
    """

    user = request.user

    if user.is_authenticated():

        if request.method == 'POST':
            action = request.POST.get('action', '')
            ig_slug = request.POST.get('ig_slug', '')
            if action == 'join':
                ig_change = get_object_or_404(InterestGroup, slug=ig_slug)
                ig_change.subscribers.add(user)
                ig_change.members = ig_change.members + 1
            else:
                ig_change = get_object_or_404(InterestGroup, slug=ig_slug)
                ig_change.subscribers.remove(user)
                ig_change.members = ig_change.members - 1
            ig_change.save()

        interest_groups = InterestGroup.objects.all().order_by('-members')
        subscribed = user.interestgroup_set.all().order_by('-members')
        member = []
        for ig in subscribed:
            member.append(ig.title)

        template_data = {'interest_groups': interest_groups, 'subscribed': subscribed, 'member': member}
        return render_to_response('content/ig.html', template_data, context_instance=RequestContext(request))
    else:

        interest_groups = InterestGroup.objects.all().order_by('-members')
        template_data = {'interest_groups': interest_groups}
        return render_to_response('content/ig.html', template_data, context_instance=RequestContext(request))


def ig_list(request, slug, method):
    user = request.user
    ig = get_object_or_404(InterestGroup, slug=slug)
    posts = ig.entry_set.all().order_by('-decayed_score_1', '-date_added')  # decay by default.

    if user.is_authenticated():
        voted = user.voters.all()
        double_voted = user.double_voters.all()
        voter = []
        double_voter = []
        for post in voted:
            voter.append(post.slug)
        for post in double_voted:
            double_voter.append(post.slug)

        if request.method == 'POST':
            action = request.POST.get('action', '')
            post_slug = request.POST.get('post_slug', '')
            if post_slug not in voter and post_slug not in double_voter:
                if action == 'vote':
                    voter.append(post_slug)
                    post_change = get_object_or_404(Entry, slug=post_slug)
                    post_change.voted_by.add(user)
                    post_change.posts = post_change.posts + 1
                    post_change.decayed_score_1 = post_change.decayed_score_1 + 1
                    post_change.decayed_score_2 = post_change.decayed_score_2 + 1
                    post_change.decayed_score_3 = post_change.decayed_score_3 + 1
                    post_change.decayed_score_4 = post_change.decayed_score_4 + 1
                    post_change.decayed_score_5 = post_change.decayed_score_5 + 1
                    post_change.decayed_score_6 = post_change.decayed_score_6 + 1
                    post_change.decayed_score_7 = post_change.decayed_score_7 + 1
                    post_change.decayed_score_8 = post_change.decayed_score_8 + 1
                    post_change.save()

           #         if request.user.is_authenticated():
        #                messages.success(request, "Thanks for contributing! Enjoy.", fail_silently=True)

                if action == 'double_vote':
                    double_voter.append(post_slug)
                    post_change = get_object_or_404(Entry, slug=post_slug)
                    post_change.double_voted_by.add(user)
                    post_change.double_posts = post_change.double_posts + 1
                    post_change.decayed_score_1 = post_change.decayed_score_1 + 2
                    post_change.decayed_score_2 = post_change.decayed_score_2 + 2
                    post_change.decayed_score_3 = post_change.decayed_score_3 + 2
                    post_change.decayed_score_4 = post_change.decayed_score_4 + 2
                    post_change.decayed_score_5 = post_change.decayed_score_5 + 2
                    post_change.decayed_score_6 = post_change.decayed_score_6 + 2
                    post_change.decayed_score_7 = post_change.decayed_score_7 + 2
                    post_change.decayed_score_8 = post_change.decayed_score_8 + 2
                    post_change.save()

         #           if request.user.is_authenticated():
        #                messages.success(request, "Thanks for contributing! Enjoy.", fail_silently=True)

        if method == 'votes':
            posts = sorted(ig.entry_set.all(), key=lambda a: -a.ranking)
        if method == 'growth':
            posts = ig.entry_set.all().order_by('-last_growth', '-decayed_score_1')

            # posts = sorted(ig.entry_set.all().order_by('-last_growth'), key=lambda a: -a.ranking)

        if method == 'decay1':
            posts = ig.entry_set.all().order_by('-decayed_score_1', '-date_added')
        if method == 'decay2':
            posts = ig.entry_set.all().order_by('-decayed_score_2', '-date_added')
        if method == 'decay3':
            posts = ig.entry_set.all().order_by('-decayed_score_3', '-date_added')
        if method == 'decay4':
            posts = ig.entry_set.all().order_by('-decayed_score_4', '-date_added')
        if method == 'decay5':
            posts = ig.entry_set.all().order_by('-decayed_score_5', '-date_added')
        if method == 'decay6':
            posts = ig.entry_set.all().order_by('-decayed_score_6', '-date_added')
        if method == 'decay7':
            posts = ig.entry_set.all().order_by('-decayed_score_7', '-date_added')
        if method == 'decay8':
            posts = ig.entry_set.all().order_by('-decayed_score_8', '-date_added')
        if method == 'favorites':
            posts = ig.entry_set.filter(favorites__gt=0).order_by('-favorites', '-date_added')
        if method == 'green':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=1), datetime.now())), key=lambda a: -a.ranking)
        if method == 'orange':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=3), datetime.now() - timedelta(days=1))), key=lambda a: -a.ranking)
        if method == 'red':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=6), datetime.now() - timedelta(days=3))), key=lambda a: -a.ranking)
        if method == 'black':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=365), datetime.now() - timedelta(days=6))), key=lambda a: -a.ranking)

        template_data = {
            'ig': ig,
            'posts': posts,
            'voter': voter,
            'double_voter': double_voter,
            'method': method,
            }
    else:
        if method == 'votes':
            posts = ig.entry_set.all().order_by('-last_growth', '-decayed_score_1')
        if method == 'growth':

            # posts = sorted(ig.entry_set.all(), key=lambda a: -a.ranking)

            posts = ig.entry_set.all().order_by('-last_growth', '-decayed_score_1')
        if method == 'decay1':

            # posts = sorted(ig.entry_set.all().order_by('-last_growth'), key=lambda a: -a.ranking)

            posts = ig.entry_set.all().order_by('-decayed_score_1', '-date_added')
        if method == 'decay2':
            posts = ig.entry_set.all().order_by('-decayed_score_2', '-date_added')
        if method == 'decay3':
            posts = ig.entry_set.all().order_by('-decayed_score_3', '-date_added')
        if method == 'decay4':
            posts = ig.entry_set.all().order_by('-decayed_score_4', '-date_added')
        if method == 'decay5':
            posts = ig.entry_set.all().order_by('-decayed_score_5', '-date_added')
        if method == 'decay6':
            posts = ig.entry_set.all().order_by('-decayed_score_6', '-date_added')
        if method == 'decay7':
            posts = ig.entry_set.all().order_by('-decayed_score_7', '-date_added')
        if method == 'decay8':
            posts = ig.entry_set.all().order_by('-decayed_score_8', '-date_added')
        if method == 'favorites':
            posts = ig.entry_set.filter(favorites__gt=0).order_by('-favorites', '-date_added')
        if method == 'green':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=1), datetime.now())), key=lambda a: -a.ranking)
        if method == 'orange':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=3), datetime.now() - timedelta(days=1))), key=lambda a: -a.ranking)
        if method == 'red':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=6), datetime.now() - timedelta(days=3))), key=lambda a: -a.ranking)
        if method == 'black':
            posts = sorted(ig.entry_set.filter(date_added__range=(datetime.now() - timedelta(days=365), datetime.now() - timedelta(days=6))), key=lambda a: -a.ranking)

        template_data = {'ig': ig, 'posts': posts, 'method': method}

    return render_to_response('content/ig_list.html', template_data, context_instance=RequestContext(request))


@login_required
def ig_proposal(request):
    if request.method == 'POST':
        form = IgProposalForm(request.POST)
        if form.is_valid():
            form.save()
            redirect_to = reverse('content_ig_proposal_done')
            return redirect(redirect_to)
    else:
        form = IgProposalForm()

    template_data = {'form': form}
    return render_to_response('content/ig_proposal.html', template_data, context_instance=RequestContext(request))


@login_required
def ig_proposal_done(request):
    template_data = {}
    return render_to_response('content/ig_proposal_done.html', template_data, context_instance=RequestContext(request))


def tag_list(request, tags, method):
    user = request.user
    tags = tags

    if user.is_authenticated():
        taglist = tags.split('|')
        voted = user.voter_set.filter(tag__in=[taglist[0]]) #only dealing with votes on the primary tag
        voter = [ i.slug for i in voted.filter(val__exact=1) ]
        double_voter = [ i.slug for i in voted.filter(val__exact=2) ]

        if request.method == 'POST':
            action = request.POST.get('action', '')
            if action == 'addfavtag':
                favtags = request.POST.get('tags','')
                if user.favoritetag_set.filter(tags=favtags):
                    pass
                else:
                    user.favoritetag_set.create(tags=favtags)
            else:
                post_slug = request.POST.get('post_slug', '')
                if post_slug not in voter and post_slug not in double_voter:
                    tagnew = Tag.objects.get(name=taglist[0])
                    post_change = get_object_or_404(Entry, slug=post_slug)
                    if action == 'vote':
                        voter.append(post_slug)
                        post_change.voted_by.voter_set.create(tag=tagnew, user=user, val=1, slug=post_slug)
                        try:
                            p=post_change.posts.tagval_set.get(tag=tagnew)
                            p.val += 1
                            p.save()
                        except:
                            post_change.posts.tagval_set.create(tag=tagnew,val=1)
                        tval1=post_change.decayed_score_1.tagval_set.get(tag=tagnew)
                        tval1.val += 1
                        tval1.save()
                        tval2=post_change.decayed_score_2.tagval_set.get(tag=tagnew)
                        tval2.val += 1
                        tval2.save()
                        tval3=post_change.decayed_score_3.tagval_set.get(tag=tagnew)
                        tval3.val += 1
                        tval3.save()
                        tval4=post_change.decayed_score_4.tagval_set.get(tag=tagnew)
                        tval4.val += 1
                        tval4.save()
                        tval5=post_change.decayed_score_5.tagval_set.get(tag=tagnew)
                        tval5.val += 1
                        tval5.save()
                        tval6=post_change.decayed_score_6.tagval_set.get(tag=tagnew)
                        tval6.val += 1
                        tval6.save()
                        tval7=post_change.decayed_score_7.tagval_set.get(tag=tagnew)
                        tval7.val += 1
                        tval7.save()
                        tval8=post_change.decayed_score_8.tagval_set.get(tag=tagnew)
                        tval8.val += 1
                        tval8.save()

                    if action == 'double_vote':
                        double_voter.append(post_slug)
                        post_change.voted_by.voter_set.create(tag=taglist[0], user=user, val=2, slug=post_slug)
                        try:
                            dbp=post_change.double_posts.tagval_set.get(tag=tagnew)
                            dbp.val += 1
                            dbp.save()
                        except:
                            post_change.double_posts.tagval_set.create(tag=tagnew,val=1)
                        tval1=post_change.decayed_score_1.tagval_set.get(tag=tagnew)
                        tval1.val += 2
                        tval1.save()
                        tval2=post_change.decayed_score_2.tagval_set.get(tag=tagnew)
                        tval2.val += 2
                        tval2.save()
                        tval3=post_change.decayed_score_3.tagval_set.get(tag=tagnew)
                        tval3.val += 2
                        tval3.save()
                        tval4=post_change.decayed_score_4.tagval_set.get(tag=tagnew)
                        tval4.val += 2
                        tval4.save()
                        tval5=post_change.decayed_score_5.tagval_set.get(tag=tagnew)
                        tval5.val += 2
                        tval5.save()
                        tval6=post_change.decayed_score_6.tagval_set.get(tag=tagnew)
                        tval6.val += 2
                        tval6.save()
                        tval7=post_change.decayed_score_7.tagval_set.get(tag=tagnew)
                        tval7.val += 2
                        tval7.save()
                        tval8=post_change.decayed_score_8.tagval_set.get(tag=tagnew)
                        tval8.val += 2
                        tval8.save()


        entries = Entry.objects.all()
        for tag in taglist:
            entries = entries.filter(tags__name__in=[tag])
			
        if method == 'votes':
            posts = sorted(entries, key=lambda a: -sum([ a._get_ranking(tag) for tag in taglist]))
            votecounts = [sum([ a._get_ranking(tag) for tag in taglist]) for a in posts]
        if method == 'growth':
            posts = entries.order_by('-last_growth', '-date_added')
            votecounts = [ a.last_growth for a in posts ]
        if method == 'decay1':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_1.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_1.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
##            posts = entries.order_by('-decayed_score_1', '-date_added')
        if method == 'decay2':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_2.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_2.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay3':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_3.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_3.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay4':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_4.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_4.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay5':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_5.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_5.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay6':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_6.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_6.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay7':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_7.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_7.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay8':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_8.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_8.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'favorites':
            posts = entries.filter(favorites__gt=0).order_by('-favorites', '-date_added')
        if method == 'green':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=1), datetime.now())), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'orange':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=3), datetime.now() - timedelta(days=1))), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'red':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=6), datetime.now() - timedelta(days=3))), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'black':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=365), datetime.now() - timedelta(days=6))), key=lambda a: -a._get_ranking(taglist[0]))

        tagscores = [ sorted([ [tag.name, post._get_ranking(tag)] for tag in post.tags.all()], key=lambda a: -a[1]) for post in posts]
        toprelevant = sorted([[tag.name,sum([a._get_ranking(tag) for a in posts])] for tag in Tag.objects.all()], key=lambda a: -a[1])[:10]
        toptags = sorted([[tag.name,sum([a._get_ranking(tag) for a in Entry.objects.all()])]for tag in Tag.objects.all()], key=lambda a: -a[1])[:10] #get top ten tags by number of votes over all entries
        mytags = [ favtag.tags for favtag in user.favoritetag_set.all() ]
        template_data = {
            'tags': tags,
            'postdata': zip(posts,votecounts,tagscores),
            'voter': voter,
            'double_voter': double_voter,
            'method': method,
            'taglist': taglist,
            'toptags': toptags,
            'toprelevant': toprelevant,
            'mytags': mytags,
            'breadcrumbdata': zip(taglist,['|'.join(taglist[:i]) for i in range(1,len(taglist)+1)]),
            }
    else:
        taglist = tags.split('|')
	entries = Entry.objects.all()
		
	for tag in taglist:
	    entries = entries.filter(tags__name__in=[tag])
			
        if method == 'votes':
            posts = sorted(entries, key=lambda a: -sum([ a._get_ranking(tag) for tag in taglist]))
            votecounts = [sum([ a._get_ranking(tag) for tag in taglist]) for a in posts]
        if method == 'growth':
            posts = entries.order_by('-last_growth', '-date_added')
            votecounts = [ a.last_growth for a in posts ]
        if method == 'decay1':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_5.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_1.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
##            posts = entries.order_by('-decayed_score_1', '-date_added')
        if method == 'decay2':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_2.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_2.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay3':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_3.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_3.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay4':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_4.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_4.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay5':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_5.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_5.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay6':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_6.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_6.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay7':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_7.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_7.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'decay8':
            posts = sorted(entries, key=lambda a: -sum([ a.decayed_score_8.tagval_set.get(tag__iexact=tag).val for tag in taglist]))
            votecounts = [ round(sum([ a.decayed_score_8.tagval_set.get(tag__iexact=tag).val for tag in taglist]),1) for a in posts ]
        if method == 'favorites':
            posts = entries.filter(favorites__gt=0).order_by('-favorites', '-date_added')
        if method == 'green':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=1), datetime.now())), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'orange':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=3), datetime.now() - timedelta(days=1))), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'red':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=6), datetime.now() - timedelta(days=3))), key=lambda a: -a._get_ranking(taglist[0]))
        if method == 'black':
            posts = sorted(entries.filter(date_added__range=(datetime.now() - timedelta(days=365), datetime.now() - timedelta(days=6))), key=lambda a: -a._get_ranking(taglist[0]))

        
        toptags = sorted([[tag.name,sum([a._get_ranking(tag) for a in Entry.objects.all()])] for tag in Tag.objects.all()], key=lambda a: -a[1])[:10] #get top ten tags by number of votes over all entries
        toprelevant = sorted([[tag.name,sum([a._get_ranking(tag) for a in posts])] for tag in Tag.objects.all()], key=lambda a: -a[1])[:10] #get top related tags (ranked by votes only, not by how closely related they are)
        tagscores = [ sorted([ [tag.name, post._get_ranking(tag)] for tag in post.tags.all()], key=lambda a: -a[1]) for post in posts]
        template_data = {
            'tags': tags,
            'postdata': zip(posts,votecounts,tagscores),
            'method': method,
            'taglist': taglist,
            'toptags': toptags,
            'toprelevant': toprelevant,
            'breadcrumbdata': zip(taglist,['|'.join(taglist[:i]) for i in range(1,len(taglist)+1)]),
        }

    return render_to_response('content/tag_list.html', template_data, context_instance=RequestContext(request))


def submit(request):
    user = request.user

    if user.is_authenticated():

        if request.method == 'POST':
            form = SubmitForm(user, request.POST.get('url', ''), request.POST)

            if form.is_valid():
                ig = get_object_or_404(InterestGroup, slug=form.cleaned_data['ig'])
                entry = Entry.objects.filter(url__iexact=form.cleaned_data['url']).filter(ig=ig)
                if entry:
                    form.errors['url'] = ['This link has already been submitted in this Interest Group.']
                else:
                    if '_post' in request.POST:
                        request.session['action'] = 'post'
                    if '_double_post' in request.POST:
                        request.session['action'] = 'double_post'

                    request.session['url'] = form.cleaned_data['url']
                    request.session['ig'] = form.cleaned_data['ig']

                    redirect_to = reverse('content_submit_details')
                    return redirect(redirect_to)
        else:
            bkmk = request.GET.get('bkmk', '')
            form = SubmitForm(user, bkmk)
        template_data = {'form': form}
        return render_to_response('content/submit.html', template_data, context_instance=RequestContext(request))
    else:

        template_data = {}
        return render_to_response('content/submit.html', template_data, context_instance=RequestContext(request))


@login_required
def submit_plugin(request):
    user = request.user
    form = None
    extra = 'Entered.'
    if request.method == 'POST':
        form = SubmitFormPlugin(user, request.POST.get('url', ''), request.POST.get('tags',''), request.POST)
        extra += ' Getting form...'
        
        if form.is_valid():
            extra += ' Form is valid.'
            url = form.cleaned_data['url']
            tags = form.cleaned_data['tags']
            withurl=Entry.objects.filter(url__iexact=url) #collect all posts with the submitted url (should be only 1)
            entry = None
            if withurl:
                for tag in form.cleaned_data['tags'].split(', '): #consider each of the specified tags individually
                    #load or create the tag
                    tagcheck = Tag.objects.filter(name__iexact=tag)
                    if tagcheck:
                        newtag = tagcheck[0]
                    else:
                        newtag = Tag(name=tag)
                        newtag.save()
                    #make tag active so that ranktags knows to look at it
                    activetags = eval(DataList.objects.get(id=1).data)
                    if newtag.id not in activetags:
                        activetags.append(newtag.id)
                        d = DataList.objects.get(id=1)
                        d.data = activetags
                        d.save()
                        del d
                    entry = withurl.filter(tags__name__in=[tag]) #find out if it already has the given tag
                    if entry: #update the posts/double_posts
                        form.errors['url'] = ['This link has already been submitted in this Interest Group, and you have voted for it.']
                        extra += ' Entry exists.'
                        voters = [ i.user for i in entry[0].voted_by.voter_set.filter(tag__iexact=tag) ] #check to see if the user has already voted under this tag. change to __exact if we want case sensitive
                        if user not in voters:
                            if request.user.is_authenticated():
                                messages.success(request, 'This link was already submitted in this Interest Group, but we kept your votes for it.', fail_silently=True)
                            action = request.session.get('action', '')
                            if '_post' in request.POST:
                                tagval=entry[0].posts.tagval_set.get(tag__name_iexact=tag)
                                tagval.val += 1
                                tagval.save()
                                entry[0].voted_by.voter_set.create(tag=tag, user=user, val=1, slug=entry[0].slug)
                            else:
                                tagval=entry[0].double_posts.tagval_set.get(tag__name_iexact=tag)
                                tagval.val += 1
                                tagval.save()
                                entry[0].voted_by.voter_set.create(tag=tag, user=user, val=2, slug=entry[0].slug)

                            entry[0].save()

                            extra += ' Entry has been updated.'
                    else: #add tag
                        action = request.session.get('action', '')
                        withurl[0].tags.add(newtag)
                        if '_post' in request.POST:
                            withurl[0].posts.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_1.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_2.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_3.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_4.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_5.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_6.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_7.tagval_set.create(tag=newtag, val=1)
                            withurl[0].decayed_score_8.tagval_set.create(tag=newtag, val=1)
                            withurl[0].voted_by.voter_set.create(tag=tag, user=user, val=1, slug=withurl[0].slug)
                        else:
                            withurl[0].double_posts.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_1.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_2.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_3.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_4.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_5.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_6.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_7.tagval_set.create(tag=newtag, val=2)
                            withurl[0].decayed_score_8.tagval_set.create(tag=newtag, val=2)
                            withurl[0].voted_by.voter_set.create(tag=tag, user=user, val=2, slug=withurl[0].slug)

                        withurl[0].save()

                        extra += ' Added tag'+tag

            else: #add entry and tags
                results = linter(url)
                ext = tldextract.extract(url)

                #create entry
                entry = Entry()
                entry.url = url
                entry.title = results.get('title', 'Untitled')
                if results.get('description'):
                    entry.summary = results.get('description')
                if results.get('image'):
                    entry.photo = results.get('image')
                entry.domain = '%s.%s' % (ext.domain, ext.tld)
                entry.submitted_by = user

                #initialize dictionaries for entry
                postsdict = Dict(name=entry.url)
                postsdict.save()
                entry.posts=postsdict
                
                dblpostsdict = Dict(name=entry.url)
                dblpostsdict.save()
                entry.double_posts = dblpostsdict
                
                favdict = Dict(name=entry.url)
                favdict.save()
                entry.favorites = favdict
                
                voterdict = Dict(name=entry.url)
                voterdict.save()
                entry.voted_by = voterdict

                dcy1dict = Dict(name=entry.url)
                dcy1dict.save()
                entry.decayed_score_1 = dcy1dict

                dcy2dict = Dict(name=entry.url)
                dcy2dict.save()
                entry.decayed_score_2 = dcy2dict

                dcy3dict = Dict(name=entry.url)
                dcy3dict.save()
                entry.decayed_score_3 = dcy3dict

                dcy4dict = Dict(name=entry.url)
                dcy4dict.save()
                entry.decayed_score_4 = dcy4dict

                dcy5dict = Dict(name=entry.url)
                dcy5dict.save()
                entry.decayed_score_5 = dcy5dict

                dcy6dict = Dict(name=entry.url)
                dcy6dict.save()
                entry.decayed_score_6 = dcy6dict

                dcy7dict = Dict(name=entry.url)
                dcy7dict.save()
                entry.decayed_score_7 = dcy7dict

                dcy8dict = Dict(name=entry.url)
                dcy8dict.save()
                entry.decayed_score_8 = dcy8dict

                #slugify
                entry.slug = '%s-%s' % (slugify(entry.title), str(entry.id))
                entry.save()
##                action = request.session.get('action','')
                for tagname in tags.split(', '):
                    #if the tag already exists grab it, otherwise create a new one
                    tagcheck = Tag.objects.filter(name__iexact=tagname)
                    if tagcheck:
                        newtag = tagcheck[0]
                    else:
                        newtag = Tag(name=tag)
                        newtag.save()
                        
                    #make tag active so that ranktags knows to look at it
                    activetags = eval(DataList.objects.get(id=1).data)
                    if newtag.id not in activetags:
                        activetags.append(newtag.id)
                        d = DataList.objects.get(id=1)
                        d.data = activetags
                        d.save()
                        del d
                        
                    if '_post' in request.POST: #'good'
                        postsdict.tagval_set.create(tag=newtag, val=1)
                        dcy1dict.tagval_set.create(tag=newtag, val=1)
                        dcy2dict.tagval_set.create(tag=newtag, val=1)
                        dcy3dict.tagval_set.create(tag=newtag, val=1)
                        dcy4dict.tagval_set.create(tag=newtag, val=1)
                        dcy5dict.tagval_set.create(tag=newtag, val=1)
                        dcy6dict.tagval_set.create(tag=newtag, val=1)
                        dcy7dict.tagval_set.create(tag=newtag, val=1)
                        dcy8dict.tagval_set.create(tag=newtag, val=1)
                        voterdict.voter_set.create(tag=tag, user=user, val=1, slug=entry.slug)
                    else: #'great'
                        dblpostsdict.tagval_set.create(tag=newtag, val=1)
                        dcy1dict.tagval_set.create(tag=newtag, val=2)
                        dcy2dict.tagval_set.create(tag=newtag, val=2)
                        dcy3dict.tagval_set.create(tag=newtag, val=2)
                        dcy4dict.tagval_set.create(tag=newtag, val=2)
                        dcy5dict.tagval_set.create(tag=newtag, val=2)
                        dcy6dict.tagval_set.create(tag=newtag, val=2)
                        dcy7dict.tagval_set.create(tag=newtag, val=2)
                        dcy8dict.tagval_set.create(tag=newtag, val=2)
                        voterdict.voter_set.create(tag=tag, user=user, val=2, slug=entry.slug)
                    entry.tags.add(newtag)
                    entry.save()
            
                #try to pull in image from twitter, if it exists.
                domains = Logo.objects.filter(site__iexact=entry.domain)
                r = list(domains[:1])
                if not r:
                    logo = Logo()
                    logo.site = entry.domain
                    try:
                        googleResult = urllib2.urlopen('http://ajax.googleapis.com/ajax/services/search/web?v=1.0&q=twitter+' + logo.site).read()
                        results = json.loads(googleResult)
                        data = results['responseData']['results']
                        urls = [e['url'] for e in data]
                        
                        for url in urls:
                            if re.search(r"https?://(www\.)?twitter.com/\w+", url):
                                contents = urllib2.urlopen(url).read()
                                start = string.find(contents,"profile-picture")
                                start = string.find(contents,"src=",start)
                                m = re.search(r"src=\"([A-Za-z\.:/_0-9\-]+)\"",contents[start:])
                                if m:
                                    image_url = m.group(1)
                                    split = urlparse.urlsplit(image_url)
                                    localPath = settings.MEDIA_ROOT + "site_logos/" + split.path.split("/")[-1]
                                    urlretrieve(image_url, localPath)
                                    logo.logo = "site_logos/" + split.path.split("/")[-1]
                                    logo.save()
                                break #only first matching
                    except:
                        logo = None
            
        if 'url' in request.session:
            del request.session['url']
        if 'action' in request.session:
            del request.session['action']
        if 'tags' in request.session:
            del request.session['tags']
        return render_to_response('autoclose.html')
    else:
        extra += ' First open.'
        bkmk = request.GET.get('bkmk', '')
        tags = request.GET.get('tags', '')
        form = SubmitFormPlugin(user, bkmk, tags)
        mytags = [ favtag.tags for favtag in user.favoritetag_set.all() ]
    template_data = {'form': form, 'extra': extra, 'tags':tags, 'mytags':mytags,}
    return render_to_response('content/submit_plugin.html', template_data, context_instance=RequestContext(request))


@login_required
def submit_details(request): #no longer used
    referer = get_referer_view(request)

    from_site = referer.find('/content/submit/')
    from_plugin = referer.find('/content/submit_plugin/')

    if from_site == -1 and from_plugin == -1:
        return redirect('/')

    user = request.user
    url = request.session.get('url', '')
    ig_slug = request.session.get('ig', '')
    newtags = request.session.get('tags', '')
    action = request.session.get('action', '')

    if request.method == 'POST':
        pass
    else:
        results = linter(url)
        ext = tldextract.extract(url)

        entry = Entry()
        entry.url = url
        entry.title = results.get('title', 'Untitled')
        if results.get('description'):
            entry.summary = results.get('description')
        if results.get('image'):
            entry.photo = results.get('image')
        entry.domain = '%s.%s' % (ext.domain, ext.tld)
        entry.submitted_by = user

        ig = get_object_or_404(InterestGroup, slug=ig_slug)
        entry.ig = ig

        if action == 'post':
            entry.posts = 1
            entry.last_score = 1
            entry.decayed_score_1 = 1
            entry.double_posts = 0
            entry.save()
            entry.voted_by.add(user)
        else:
            entry.posts = 0
            entry.double_posts = 1
            entry.last_score = 2
            entry.decayed_score_1 = 2
            entry.save()
            entry.double_voted_by.add(user)

        entry.save()
        for tag in newtags.split(', '):
        	entry.tags.add(tag)
    	entry.save()
        
        
        ig.posts = ig.posts + 1
        ig.save()

        if 'url' in request.session:
            del request.session['url']
        if 'ig' in request.session:
            del request.session['ig']
        if 'action' in request.session:
            del request.session['action']

#   Getting rid of the green part
#     if request.user.is_authenticated():
#            messages.success(request, "Keep it up! You are making the lists stronger.", fail_silently=True)

        if from_site != -1:
            redirect_to = reverse('content_myig')
        else:
            redirect_to = '/autoclose/'
        return redirect(redirect_to)

#         html5 = urlopen(url).read()
#         soup = BeautifulSoup(html5)
#         title = soup.title.string
#         h1 = soup.find_all('h1')
#         headings = [h.string for h in h1]
#         p1 = soup.find_all('p')
#         paragraphs = [p.string for p in p1 if p.string and len(p.string) > 40]
#         text = get_text(soup)
#         headings2 = soup.find_all('h2')
#         headings3 = soup.find_all('h3')
        # intros = find_intro(soup)

    template_data = {
        'url': url,
        'ig': ig,
        'results': results,
        'tags': tags,
        }

        # 'title': title,
        # 'intros': intros,
        # 'headings': headings,
        # 'paragraphs': paragraphs,
        # 'text': text

    return render_to_response('content/submit_details.html', template_data, context_instance=RequestContext(request))


def find_intro(soup):
    headings = soup.find_all('h1')
    intros = []
    for h1 in headings:
        s = []
        s.append(h1.next_simbling)
        s.append(s[0].next_simbling)
        s.append(s[1].next_simbling)
        intro = ''
        for tag in s:
            intro = intro + '%s: %s\n' % (tag.tag, tag.stripped_strings)

        intros.append(intro)

    return intros


def get_text(soup):
    paragraphs = soup.find_all('p')
    text = []
    for p in paragraphs:
        for s in p.stripped_strings:
            if len(s) > 70:
                text.append(s)

    return text


def linter(url):
    encurl = quote_plus(url)
    html5 = urlopen('http://developers.facebook.com/tools/debug/og/object?q=' + encurl).read()

    # html5 = urlopen("https://developers.facebook.com/tools/lint/?url=" + encurl + "&format=json").read()

    soup = BeautifulSoup(html5)
    data = soup.find_all('td')
    prev = [x.previous_element for x in data]
    results = {}
    for cell in data:
        if cell.previous_element == u'og:title:':
            results['title'] = cell.string
        if cell.previous_element == u'og:description:':
            results['description'] = cell.string
        if cell.previous_element == u'og:image:':
            href = cell.span.img['src']
            results['image'] = href
    return results
