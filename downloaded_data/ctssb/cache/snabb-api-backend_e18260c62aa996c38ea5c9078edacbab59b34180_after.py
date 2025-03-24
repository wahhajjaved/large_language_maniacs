import json
from django.conf import settings
from snabb.users.models import Profile
from snabb.location.models import Zipcode, City, Country, Region
from snabb.deliveries.models import Delivery
from snabb.currency.models import Currency
import stripe
from rest_framework.test import (
    APIRequestFactory,
    force_authenticate
)
from snabb.quote.tests.json import test1
from snabb.quote.views import QuoteViewSet
"""
We use this library to setup all object creation, to use them accross our tests
"""


def create_profile():
    profile = Profile.objects.get_or_create(
        company_name='My Company S.L.', email='email@example.com',
        password='123456', phone='+34123456789', user_lang='es', enterprise=True
    )
    return profile[0]


def create_country(name, iso_code, active, currency):
    country = Country.objects.get_or_create(
        name=name, iso_code=iso_code, active=active, country_currency=currency
    )
    return country[0]


def create_region(name, google_short_name, region_country, active):
    region = Region.objects.get_or_create(
        name=name, active=active,
        google_short_name=google_short_name
    )
    return region[0]


def create_zipcode(code, city, active):
    zipcode = Zipcode.objects.get_or_create(
        code=code, zipcode_city=city, active=active
    )
    return zipcode[0]


def create_city(name, google_short_name, region, active):
    city = City.objects.get_or_create(
        name=name, active=active, google_short_name=google_short_name
    )
    return city[0]


def create_currency(currency, symbol, iso_code, active):
    currency = Currency.objects.get_or_create(
        currency='Euro', symbol='€', iso_code='EUR', active=active
    )
    return currency[0]


def init_data_geo():
    currency = create_currency('Euro', '€', 'EUR', True)
    country = create_country('Spain', 'ES', True, currency)
    region_valencia = create_region(
        'Valencia', 'Comunidad Valenciana', country, True)
    city = create_city(
        'Albaida', 'Albaida', region_valencia, True)
    zipcode = create_zipcode(46860, city, True)


def update_delivery_status(pk, status):
    "Change delivery status for testing purposes"
    delivery = Delivery.objects.get(pk=pk)
    delivery.status = status
    delivery.save()
    return delivery


def post_api(user, data, url, view):
    factory = APIRequestFactory()
    request = factory.post(
        url,
        json.dumps(data), content_type='application/json'
    )
    force_authenticate(request, user=user.profile_apiuser)
    view = view.as_view({'post': 'create'})
    response = view(request)
    return response


def create_quote(user):
    """ Create a quote for testing purposes."""

    # Init Data
    init_data_geo()

    # Test Cases
    response = post_api(
        user, test1.data, '/api/v1/deliveries/quote', QuoteViewSet)
    return response


def patch_api(user, data, url, view):
    factory = APIRequestFactory()
    request = factory.patch(
        url,
        json.dumps(data), content_type='application/json'
    )
    force_authenticate(request, user=user.profile_apiuser)
    view = view.as_view({'patch': 'partial_update'})
    response = view(request)
    return response


def create_token_card(data_card):
    "Generate a token to create a card"
    stripe.api_key = settings.PINAX_STRIPE_SECRET_KEY
    card = stripe.Token.create(card=data_card,)
    return card['id']
