from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.paginator import Paginator
from django.conf import settings
from django.db.models import Avg, Max, Min, Count
from decimal import Decimal

from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import PaginatedContractSerializer
from contracts.models import Contract, EDUCATION_CHOICES

import numpy as np
import sys
import re

import csv

def convert_to_tsquery(query):
    """ converts multi-word phrases into AND boolean queries for postgresql """
    # remove all non-alphanumeric or whitespace chars
    pattern = re.compile('[^a-zA-Z\s]')
    query = pattern.sub('', query)
    query_parts = query.split()
    # remove empty strings and add :* to use prefix matching on each chunk
    query_parts = ["%s:*" % s for s in query_parts if s]
    tsquery = ' & '.join(query_parts)

    return tsquery

def get_contracts_queryset(request_params, wage_field):
    """ Filters and returns contracts based on query params

    Args:
        request_params (dict): the request query parameters
        wage_field (str): the name of the field currently being used for wage calculations and sorting

    Query Params:
        q (str): keywords to search by
        experience_range(str): filter by a range of years of experience
        min_experience (int): filter by minimum years of experience
        max_experience (int): filter by maximum years of experience
        min_education (str): filter by a minimum level of education (see EDUCATION_CHOICES)
        schedule (str): filter by GSA schedule
        site (str): filter by worksite
        business_size (str): filter by 's'(mall) or 'o'(ther)
        price (int): filter by exact price
        price__gte (int): price must be greater than or equal to this integer
        price__lte (int): price must be less than or equal to this integer
        sort (str): the column to sort on, defaults to wage_field
        query_type (str): defines how the user's keyword search should work. [ match_all (default) | match_phrase | match_exact ] 
        exclude: (int): comma separated list of ids to exclude from the search results

    Returns:
        QuerySet: a filtered and sorted QuerySet to retrieve Contract objects
    """

    query = request_params.get('q', None)
    experience_range = request_params.get('experience_range', None)
    min_experience = request_params.get('min_experience', None)
    max_experience = request_params.get('max_experience', None)
    min_education = request_params.get('min_education', None)
    education = request_params.get('education', None)
    schedule = request_params.get('schedule', None)
    site = request_params.get('site', None)
    business_size = request_params.get('business_size', None)
    price = request_params.get('price', None)
    price__gte = request_params.get('price__gte')
    price__lte = request_params.get('price__lte')
    sort = request_params.get('sort', wage_field)
    # query_type can be: [ match_all (default) | match_phrase | match_exact ]
    query_type = request_params.get('query_type', 'match_all')
    exclude = request_params.getlist('exclude')

    contracts = Contract.objects.all()

    if exclude:
        #getlist only works for key=val&key=val2, not for key=val1,val2
        exclude = exclude[0].split(',')
        contracts = contracts.exclude(id__in=exclude)

    if query:
        if query_type == 'match_phrase':
            contracts = contracts.filter(labor_category__icontains=query)
        elif query_type == 'match_exact':
            contracts = contracts.filter(labor_category__iexact=query)
        else:
            query = convert_to_tsquery(query)
            contracts = contracts.search(query, raw=True)

    if experience_range:
        years = experience_range.split(',')
        min_experience = int(years[0])
        if len(years) > 1:
            max_experience = int(years[1])

    if min_experience:
        contracts = contracts.filter(min_years_experience__gte=min_experience)

    if max_experience:
        contracts = contracts.filter(min_years_experience__lte=max_experience)

    if min_education:
        for index, pair in enumerate(EDUCATION_CHOICES):
            if min_education == pair[0]:
                contracts = contracts.filter(education_level__in=[ed[0] for ed in EDUCATION_CHOICES[index:] ])

    if education:
        degrees = education.split(',')
        selected_degrees = []
        for index, pair in enumerate(EDUCATION_CHOICES):
            if pair[0] in degrees:
                selected_degrees.append(pair[0])
        contracts = contracts.filter(education_level__in=selected_degrees)

    if schedule:
        contracts = contracts.filter(schedule__iexact=schedule)
    if site:
        contracts = contracts.filter(contractor_site__icontains=site)
    if business_size == 's':
        contracts = contracts.filter(business_size__istartswith='s')
    elif business_size == 'o':
        contracts = contracts.filter(business_size__istartswith='o')
    if price:
        contracts = contracts.filter(**{wage_field + '__exact': price})
    else:
        if price__gte:
            contracts = contracts.filter(**{wage_field + '__gte': price__gte})
        if price__lte:
            contracts = contracts.filter(**{wage_field + '__lte': price__lte})

    return contracts.order_by(*sort.split(','))


def get_histogram(values, bins=10):
    """
    Get a histogram of a list of numeric values.

    >>> hist = get_histogram([1, 2, 3], 3)
    >>> len(hist)
    3
    >>> hist[0]
    {'count': 1, 'max': 1.6666666666666665, 'min': 1.0}
    >>> hist[1]
    {'count': 1, 'max': 2.333333333333333, 'min': 1.6666666666666665}
    >>> hist[2]
    {'count': 1, 'max': 3.0, 'min': 2.333333333333333}
    """
    hist, edges = np.histogram(list(map(float, values)), bins, density=False)
    result = []
    for i, edge in enumerate(edges[1:]):
        result.append({
            'count': hist[i],
            'min': edges[i],
            'max': edges[i + 1]
        })
    return result

def quantize(num, precision=2):
  if num is None:
    return None
  return Decimal(num).quantize(Decimal(10) ** -precision)

class GetRates(APIView):

    def get(self, request):

        page = request.QUERY_PARAMS.get('page', 1)
        bins = request.QUERY_PARAMS.get('histogram', None)

        wage_field = 'current_price'
        contracts_all = self.get_queryset(request.QUERY_PARAMS, wage_field)
        
        paginator = Paginator(contracts_all, settings.PAGINATION)
        contracts = paginator.page(page)
        
        page_stats = {}
        current_rates = []

        page_stats['minimum'] = contracts_all.aggregate(Min(wage_field))[wage_field + '__min']
        page_stats['maximum'] = contracts_all.aggregate(Max(wage_field))[wage_field + '__max']
        page_stats['average'] = quantize(contracts_all.aggregate(Avg(wage_field))[wage_field + '__avg'])

        for rate in contracts_all.values(wage_field):
            current_rates.append(rate[wage_field])
        page_stats['first_standard_deviation'] = np.std(current_rates)

        #use paginator count method
        if paginator.count > 0:
            if bins and bins.isnumeric():
                # numpy wants these to be floats, not Decimals
                values = contracts_all.values_list(wage_field, flat=True)
                # see api.serializers.PaginatedContractSerializer#get_wage_histogram()
                page_stats['wage_histogram'] = get_histogram(values, int(bins))

            serializer = PaginatedContractSerializer(contracts, context=page_stats)

            return Response(serializer.data)

        else:
            return Response({'count': 0, 'results': []})

    def get_queryset(self, request, wage_field):
        return get_contracts_queryset(request, wage_field)

class GetRatesCSV(APIView):

    def get(self, request, format=None):
        """ Returns a CSV of matched records and selected search and filter options

        Query Params:
            q (str): keywords to search by
            min_experience (int): filter by minimum years of experience
            min_education (str): filter by a minimum level of education
            site (str): filter by worksite
            business_size (str): filter by 's'(mall) or 'o'(ther)
        """

        wage_field = 'current_price'
        contracts_all = get_contracts_queryset(request.GET, wage_field)

        q = request.QUERY_PARAMS.get('q', 'None')
        min_education = request.QUERY_PARAMS.get('min_education', 'None Specified')
        min_experience = request.QUERY_PARAMS.get('min_experience', 'None Specified')
        site = request.QUERY_PARAMS.get('site', 'None Specified')
        business_size = request.QUERY_PARAMS.get('business_size', 'None Specified')
        business_size_map = {
            'o': 'other than small',
            's': 'small business'
        }
        business_size_set = business_size_map.get(business_size)
        if business_size_set:
            business_size = business_size_set
        
        response = HttpResponse(content_type="text/csv")
        response['Content-Disposition'] = 'attachment; filename="pricing_results.csv"'
        writer = csv.writer(response)
        writer.writerow(("Search Query", "Minimum Education Level", "Minimum Years Experience", "Worksite", "Business Size", "", "", "", "", "", "", ""))
        writer.writerow((q, min_education, min_experience, site, business_size, "", "", "", "", "", "", "")) 
        writer.writerow(("Contract #", "Business Size", "Schedule", "Site", "Begin Date", "End Date", "SIN", "Vendor Name", "Labor Category", "education Level", "Minimum Years Experience", "Current Year Labor Price"))

        for c in contracts_all:
            writer.writerow((c.idv_piid, c.get_readable_business_size(), c.schedule, c.contractor_site, c.contract_start, c.contract_end, c.sin, c.vendor_name, c.labor_category, c.get_education_level_display(), c.min_years_experience, c.current_price ))
        
        return response

class GetAutocomplete(APIView):

    def get(self, request, format=None):
        """
        Query Params:
            q (str): the search query
            query_type (str): defines how the search query should work. [ match_all (default) | match_phrase ]
        """
        q = request.QUERY_PARAMS.get('q', False)
        query_type = request.QUERY_PARAMS.get('query_type', 'match_all')

        if q:
            if query_type == 'match_phrase':
                data = Contract.objects.filter(labor_category__icontains=q)
            else:
                data = Contract.objects.search(convert_to_tsquery(q), raw=True)
            data = data.values('labor_category').annotate(count=Count('labor_category')).order_by('-count')
            return Response(data)
        else:
            return Response([])
