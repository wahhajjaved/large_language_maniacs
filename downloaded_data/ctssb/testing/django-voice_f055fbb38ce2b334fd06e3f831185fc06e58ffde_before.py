import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.models import Site
from django.db.models import Q
from django.http import HttpResponseNotFound
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.views.generic import DeleteView, DetailView, FormView, ListView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from djangovoice.models import Feedback, Type
from djangovoice.forms import WidgetForm, EditForm


def current_site_context(method):
    """Adds the current_site in template context variable 'params'."""
    def wrapped(self, **kwargs):
        context = method(self, **kwargs)

        if Site._meta.installed:
            current_site = Site.objects.get_current()

        else:
            current_site = None

        context.setdefault('site', current_site)
        brand_view = getattr(settings, 'VOICE_BRAND_VIEW', 'djangovoice_home')
        context.setdefault('brand_view', brand_view)

        return context
    return wrapped


class FeedbackDetailView(DetailView):

    template_name = 'djangovoice/detail.html'
    model = Feedback

    @current_site_context
    def get_context_data(self, **kwargs):
        return super(FeedbackDetailView, self).get_context_data(**kwargs)

    def get(self, request, *args, **kwargs):
        feedback = self.get_object()

        if feedback.private:
            # Anonymous private feedback can be only accessed with slug
            if not request.user.is_staff and 'slug' not in kwargs and feedback.user is None:
                return HttpResponseNotFound
            if not request.user.is_staff and request.user != feedback.user and feedback.user is not None:
                return HttpResponseNotFound

        return super(FeedbackDetailView, self).get(request, *args, **kwargs)


class FeedbackListView(ListView):

    template_name = 'djangovoice/list.html'
    model = Feedback
    paginate_by = 10

    def get_queryset(self):
        f_list = self.kwargs.get('list', 'open')
        f_type = self.kwargs.get('type', 'all')
        f_status= self.kwargs.get('status', 'all')
        f_filters = {}
        # Tag to display also user's private discussions
        f_showpriv = False

        # add filter for list value, and define title.
        if f_list in ['open', 'closed']:
            f_filters.update(dict(status__status=f_list))

        elif f_list == 'mine':
            f_filters.update(user=self.request.user)

        # add filter for feedback type.
        if f_type != 'all':
            f_filters.update(dict(type__slug=f_type))

        # add filter for feedback status.
        if f_status != 'all':
            f_filters.update(dict(status__slug=f_status))

        # If user is checking his own feedback, do not filter by private
        # for everyone's discussions but add user's private feedback
        if not self.request.user.is_staff and f_list != 'mine':
            f_filters.update(dict(private=False))
            f_showpriv = True

        if f_showpriv:
            # Show everyone's public discussions and user's own private discussions
            queryset = self.model.objects.filter(Q(**f_filters) | Q(user=self.request.user, private=True)).order_by('-vote_score', '-created')
        else:
            queryset = self.model.objects.filter(**f_filters).order_by('-vote_score', '-created')
        return queryset

    @current_site_context
    def get_context_data(self, **kwargs):
        f_list = self.kwargs.get('list', 'open')
        f_type = self.kwargs.get('type', 'all')
        f_status= self.kwargs.get('status', 'all')

        title = _("Feedback")

        if f_list == 'open':
            title = _("Open Feedback")

        elif f_list == 'closed':
            title = _("Closed Feedback")

        elif f_list == 'mine':
            title = _("My Feedback")

        # update context data
        data = super(FeedbackListView, self).get_context_data(**kwargs)

        data.update({
            'list': f_list,
            'status': f_status,
            'type': f_type,
            'navigation_active': f_list,
            'title': title
        })

        return data

    def get(self, request, *args, **kwargs):
        f_list = kwargs.get('list')

        if f_list == 'mine' and not request.user.is_authenticated():
            to_url = (
                reverse('django.contrib.auth.views.login') +
                '?next=%s' % request.path)

            return redirect(to_url)

        return super(FeedbackListView, self).get(request, *args, **kwargs)


class FeedbackWidgetView(FormView):

    template_name = 'djangovoice/widget.html'
    form_class = WidgetForm
    initial = {'type': Type.objects.get(pk=1)}

    def get(self, request, *args, **kwargs):
        return super(FeedbackWidgetView, self).get(request, *args, **kwargs)

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        return super(FeedbackWidgetView, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        feedback = form.save(commit=False)
        if form.cleaned_data.get('anonymous') != 'on':
            feedback.user = self.request.user
        feedback.save()

        messages.add_message(
            self.request, messages.SUCCESS, _("Thanks for feedback."))

        return redirect('djangovoice_widget')

    def form_invalid(self, form):
        messages.add_message(self.request, messages.ERROR,
                             _("Form is invalid."))

        return super(FeedbackWidgetView, self).form_invalid(form)


class FeedbackSubmitView(FormView):

    template_name = 'djangovoice/submit.html'
    form_class = WidgetForm

    @current_site_context
    def get_context_data(self, **kwargs):
        return super(FeedbackSubmitView, self).get_context_data(**kwargs)

    def get(self, request, *args, **kwargs):
        if self.request.user.is_anonymous() and not getattr(settings, 'VOICE_ALLOW_ANONYMOUS_USER_SUBMIT', False):
            return redirect(reverse('django.contrib.auth.views.login') + '?next=%s' % request.path)
        return super(FeedbackSubmitView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.request.user.is_anonymous() and not getattr(settings, 'VOICE_ALLOW_ANONYMOUS_USER_SUBMIT', False):
            return HttpResponseNotFound
        return super(FeedbackSubmitView, self).post(request, *args, **kwargs)

    def get_form(self, form_class):
        form = super(FeedbackSubmitView, self).get_form(form_class)
        if self.request.user.is_anonymous():
          del form.fields['anonymous']
          del form.fields['private']
        else:
          del form.fields['email']
        return form

    def form_valid(self, form):
        feedback = form.save(commit=False)
        if self.request.user.is_anonymous() and getattr(settings, 'VOICE_ALLOW_ANONYMOUS_USER_SUBMIT', False):
            feedback.private = True
        elif form.data.get('anonymous') != 'on':
            feedback.user = self.request.user

        if not feedback.user:
            feedback.slug = uuid.uuid1().hex[:10]

        feedback.save()

        # If there is no user, show the feedback with slug
        if not feedback.user:
            return redirect('djangovoice_slug_item', slug=feedback.slug)
        return redirect(feedback)


class FeedbackEditView(FormView):

    template_name = 'djangovoice/edit.html'

    def get_form_class(self):
        feedback = self.get_object()
        if self.request.user.is_staff:
            return EditForm
        elif self.request.user == feedback.user:
            return WidgetForm
        return None

    def get_object(self):
        return Feedback.objects.get(pk=self.kwargs.get('pk'))

    def get_form_kwargs(self):
        kwargs = super(FeedbackEditView, self).get_form_kwargs()
        kwargs.update({'instance': self.get_object()})

        return kwargs

    @current_site_context
    def get_context_data(self, **kwargs):
        return super(FeedbackEditView, self).get_context_data(**kwargs)

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        if not form_class:
            raise HttpResponseNotFound

        return super(FeedbackEditView, self).get(request, *args, **kwargs)

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        return super(FeedbackEditView, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        feedback = form.save()
        return redirect(feedback)


class FeedbackDeleteView(DeleteView):

    template_name = 'djangovoice/delete.html'

    def get_object(self):
        return Feedback.objects.get(pk=self.kwargs.get('pk'))

    @current_site_context
    def get_context_data(self, **kwargs):
        return super(FeedbackDeleteView, self).get_context_data(**kwargs)

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        # FIXME: should feedback user have delete permissions?
        feedback = self.get_object()
        if not request.user.is_staff and request.user != feedback.user:
            raise HttpResponseNotFound

        return super(FeedbackDeleteView, self).get(request, *args, **kwargs)

    @method_decorator(login_required)
    def post(self, request, *args, **kwargs):
        feedback = self.get_object()
        feedback.delete()

        return redirect('djangovoice_home')
