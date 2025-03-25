import logging
import os
import requests
from datetime import datetime

from django.shortcuts import redirect, render, render_to_response
from django.views.generic import DetailView, FormView
from django.views.generic.base import View, TemplateView

from articles.models import Article
from galleries.models import Gallery
from newsevents.models import Event, NewsItem
from newsevents.forms import SubscriberForm
from videos.models import Video

from .forms import FeedbackForm
from .models import Page
logger = logging.getLogger('ECHB')


class HomePageView(View):
    def get(self, request):
        context = self._get_context_data()
        return render(request, 'pages/home.html', context)

    def post(self, request):
        form = SubscriberForm(request.POST)
        context = self._get_context_data()

        captcha_is_valid = check_captcha(request)

        if form.is_valid() and captcha_is_valid:
            subscriber = form.save()
            domain = form.get_domain(request)
            form.send_mail(subscriber, domain)

            context['success_subscriber'] = True
            return render(request, 'newsevents/subscription_thankyou.html')
        else:
            context['errors'] = form.errors['email']
            return render(request, 'pages/home.html', context)

    def _get_context_data(self):
        page = Page.objects.get(slug='home')
        news = NewsItem.objects.filter(date__lt=datetime.now()).prefetch_related(
            'author').order_by('-publication_date')[:6]
        articles = Article.objects.all().order_by('-date').prefetch_related('author').select_related('category')[:6]
        events = Event.objects.filter(date__gt=datetime.now()).order_by('date')[:6]
        photos = Gallery.objects.all().prefetch_related('author').order_by('-date')[:4]
        videos = Video.objects.filter(interesting_event=True).order_by('-date')[:4]
        form = SubscriberForm()
        context = {
            'page': page,
            'news': news,
            'articles': articles,
            'events': events,
            'photos': photos,
            'videos': videos,
            'form': form
        }
        return context


class PageDetailView(DetailView):
    model = Page

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['right_menu_pages'] = Page.objects.filter(
            parent__slug='about-us').prefetch_related('children').order_by('order')
        return context


class ContactsFormView(FormView):
    template_name = 'pages/contacts.html'
    success_url = '/contacts/thankyou/'
    form_class = FeedbackForm

    def form_valid(self, form, **kwargs):
        captcha_is_valid = check_captcha(self.request)

        if captcha_is_valid:
            form.send_email()
            form.save()
            return super().form_valid(form)
        else:
            return redirect('contacts')


class ContactsThankYouView(TemplateView):
    template_name = 'pages/thankyou.html'


def handler404(request, exception, template_name='pages/404.html'):
    response = render_to_response('pages/404.html')
    response.status_code = 404
    return response


def handler500(request):
    response = render_to_response('pages/500.html')
    response.status_code = 500
    return response


def check_captcha(request):
    captcha = request.POST.get('g-recaptcha-response')
    response = requests.post("https://www.google.com/recaptcha/api/siteverify",
                             data={'secret': '6LfamGAUAAAAAEnS0-AF5p_EVmAFriMZqkkll-HM', 'response': captcha})

    debug_mode = bool(os.environ.get("DEBUG", False))
    return debug_mode if debug_mode else response.json()['success']
