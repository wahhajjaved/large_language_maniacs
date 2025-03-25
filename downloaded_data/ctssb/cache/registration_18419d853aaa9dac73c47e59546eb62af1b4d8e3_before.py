# Create your views here.
from __future__ import print_function

from datetime import timedelta

from django import http
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from app.utils import reverse
from register import models, forms, emails


def add_vote(application, user, tech_rat, pers_rat):
    v = models.Vote()
    v.user = user
    v.application = application
    v.tech = tech_rat
    v.personal = pers_rat
    v.save()
    return v


class RankingView(PermissionRequiredMixin, TemplateView):
    permission_required = 'register.vote'
    template_name = 'ranking.html'

    def get_context_data(self, **kwargs):
        context = super(RankingView, self).get_context_data(**kwargs)
        context['ranking'] = User.objects.annotate(vote_count=Count('vote__calculated_vote')).order_by(
            '-vote_count').values('vote_count', 'username')
        return context


class VoteApplicationView(PermissionRequiredMixin, TemplateView):
    permission_required = 'register.vote'
    template_name = 'vote.html'

    def get_next_application(self):
        """
        Django model to the rescue. This is transformed to an SQL sentence that does exactly what we need
        :return: pending aplication that has not been voted by the current user and that has less votes and its older
        """
        return models.Application.objects \
            .exclude(vote__user_id=self.request.user.id) \
            .filter(status=models.APP_PENDING) \
            .annotate(count=Count('vote__calculated_vote')) \
            .order_by('count', 'submission_date') \
            .first()

    def post(self, request, *args, **kwargs):
        tech_vote = request.POST.get('tech_rat', None)
        pers_vote = request.POST.get('pers_rat', None)
        application = models.Application.objects.get(id=request.POST.get('app_id'))
        try:
            if request.POST.get('skip'):
                add_vote(application, request.user, None, None)
            else:
                add_vote(application, request.user, tech_vote, pers_vote)
        # If application has already been voted -> Skip and bring next application
        except IntegrityError:
            pass
        return HttpResponseRedirect(reverse('vote'))

    def get_context_data(self, **kwargs):
        context = super(VoteApplicationView, self).get_context_data(**kwargs)
        application = self.get_next_application()
        context['app'] = application
        try:
            context['hacker'] = application.hacker
        except:
            pass
        return context


class ConfirmApplication(TemplateView, View):
    template_name = 'confirm.html'

    def get_context_data(self, **kwargs):
        context = super(ConfirmApplication, self).get_context_data(**kwargs)
        request = self.request
        try:
            application = request.user.hacker.application_set.first()
        except:
            raise Http404
        msg = None
        if application.status == models.APP_INVITED:
            msg = emails.create_confirmation_email(application, self.request)
        already_confirmed = application.is_confirmed()
        cancellation_url = str(reverse('cancel_app', request=request))
        try:
            application.confirm()

            context.update({
                'application': application,
                'hacker': application.hacker,
                'cancel': cancellation_url,
                'reconfirming': already_confirmed
            })

        except ValidationError as e:
            context.update({
                'application': application,
                'hacker': application.hacker,
                'error': e.message,
            })
        if msg: msg.send()
        return context


class CancelApplication(TemplateView):
    template_name = 'cancel.html'

    def get_context_data(self, **kwargs):
        context = super(CancelApplication, self).get_context_data(**kwargs)
        try:
            application = self.request.user.hacker.application_set.first()
        except:
            raise http.Http404

        context.update({
            'application': application,
        })

        if application.status == models.APP_CANCELLED:
            context.update({
                'error':
                    """
                    Thank you for responding.
                     We're sorry you won't be able to make it to HackUPC. Hope to see you next edition!
                    """
            })
        elif application.status == models.APP_EXPIRED:
            context.update({
                'error':
                    """
                    Unfortunately your invite has expired.
                    """
            })
        elif not application.can_be_cancelled():
            context.update({
                'error':
                    """
                    You found a glitch! You are trying to cancel a non invited application.
                    Is this the question to 42?
                    """,
                'application': None
            })

        return context

    def post(self, request, *args, **kwargs):
        application = self.request.user.hacker.application_set.first()
        try:
            application.cancel()
        except ValidationError:
            pass

        return http.HttpResponseRedirect(reverse('cancel_app'))


def create_phase(template_name, title, finished_func, user):
    is_finished = False
    try:
        is_finished = bool(finished_func(user))
    except:
        pass

    return {'template': 'phases/' + template_name + '.html', 'finished': is_finished, 'title': title}


class ProfileHacker(LoginRequiredMixin, TemplateView):
    template_name = 'profile.html'

    def get_context_data(self, **kwargs):
        context = super(ProfileHacker, self).get_context_data(**kwargs)

        phases = self.get_phases()
        try:
            current = [p for p in phases if not p['finished']][0]
        except IndexError:
            current = [p for p in phases if p['finished']][-1]
        try:
            hacker_form = forms.HackerForm(instance=self.request.user.hacker)
        except:
            hacker_form = forms.HackerForm()

        context.update({'phases': phases, 'current': current, 'hacker_form': hacker_form})
        try:
            application = self.request.user.hacker.application_set.first()
            last_updated = application.status_update_date
            if application.status == models.APP_INVITED:
                deadline = last_updated + timedelta(days=5)
            else:
                deadline = last_updated + timedelta(days=1)
            context.update({'invite_deadline': deadline})
        except:
            pass
        return context

    def get_phases(self):
        user = self.request.user
        phases = [
            create_phase('hacker_info', "Basic information", lambda x: x.hacker, user),
            create_phase('fill_application', "Apply", lambda x: x.hacker.application_set.exists(), user),
        ]
        # Try/Except caused by Hacker not existing any hacker
        try:
            current_app = user.hacker.application_set.first()

            phases.append(
                create_phase('pending', "Wait for review", lambda x: not current_app.is_pending(),
                             self.request.user)
            )
            if not current_app.is_pending() and current_app.status in [models.APP_CONFIRMED, models.APP_CANCELLED,
                                                                       models.APP_ATTENDED,
                                                                       models.APP_LAST_REMIDER, models.APP_INVITED]:
                phases.append(
                    create_phase('invited', "Answer invite", lambda x: current_app.answered_invite(),
                                 self.request.user)
                )
                if current_app.status in [models.APP_CONFIRMED, models.APP_ATTENDED]:
                    phases.append(
                        create_phase('attend', "Attend", lambda x: current_app.is_confirmed(),
                                     self.request.user)
                    )
        except:
            pass

        return phases

    def post(self, request, *args, **kwargs):
        form = forms.HackerForm(request.POST)
        if form.is_valid():
            hacker = form.save(commit=False)
            hacker.user = request.user
            hacker.save()
            messages.success(request, 'Profile details saved!')

            return HttpResponseRedirect(reverse('profile'))
        else:
            c = self.get_context_data()
            c.update({'hacker_form': form})
            return render(request, self.template_name, c)


class ApplyHacker(TemplateView):
    template_name = 'apply.html'
