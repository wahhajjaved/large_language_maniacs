from django.db import models
from django.http import HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ddh_utils.views import FacetedSearchView

from .behaviours import PUBLISHED_STATUS
from .forms import RESULTS_PER_PAGE
from .models import Date, Person, PropertyAssertion, Source, Text
import attribution.utils


def home_display(request):
    context = {'url_path': request.path}
    return render(request, 'attribution/display/home.html', context)


def date_display(request, date):
    people = Person.objects.filter(sort_date=date)
    assertions = PropertyAssertion.objects.filter(
        models.Q(dates__sort_date=date) |
        models.Q(people__sort_date=date))
    context = {'date': date, 'people': people, 'assertions': assertions,
               'url_path': request.path}
    return render(request, 'attribution/display/date.html', context)


def date_list_display(request):
    dates = list(set(list(Date.objects.values_list('sort_date', flat=True)) +
                     list(Person.objects.values_list('sort_date', flat=True))))
    dates = [date for date in dates if date]
    dates.sort()
    context = {'dates': dates, 'url_path': request.path}
    return render(request, 'attribution/display/date_list.html', context)


def person_display(request, person_id):
    person = get_object_or_404(Person.published_objects, pk=person_id)
    context = {'person': person, 'assertions': person.get_assertions(),
               'url_path': request.path}
    return render(request, 'attribution/display/person.html', context)


def source_display(request, source_id):
    source = get_object_or_404(Source.published_objects, pk=source_id)
    context = {'source': source, 'url_path': request.path}
    return render(request, 'attribution/display/source.html', context)


def text_display(request, text_id):
    text = get_object_or_404(Text.published_objects, pk=text_id)
    assertions = text.assertions.filter(status=PUBLISHED_STATUS)
    summary = attribution.utils.get_text_summary(assertions)
    context = {'text': text, 'assertions': assertions, 'summary': summary,
               'url_path': request.path}
    return render(request, 'attribution/display/text.html', context)


def text_display_redirect(request, abbreviation, number, suffix):
    """Returns a temporary redirect to the text_display URL for the text
    identified by a Taisho/etc identifier (eg, T0001). Handles
    non-zero-filled identifiers."""
    number_zeros = 4 - len(number)
    text_id = '{}{}{}{}'.format(abbreviation, number_zeros * '0', number,
                                suffix)
    try:
        text = Text.published_objects.get(
            assertions__sources__abbreviation=abbreviation,
            assertions__identifiers__name=text_id)
    except Text.DoesNotExist:
        return HttpResponseNotFound()
    return HttpResponseRedirect(reverse('text_display', args=[text.id]))


class ModelSearchView (FacetedSearchView):

    def build_page(self):
        # Allow for the number of results per page to be set
        # dynamically.
        if self.form.is_valid():
            self.results_per_page = self.form.cleaned_data['results_per_page']
        else:
            self.results_per_page = RESULTS_PER_PAGE
        return super(ModelSearchView, self).build_page()
