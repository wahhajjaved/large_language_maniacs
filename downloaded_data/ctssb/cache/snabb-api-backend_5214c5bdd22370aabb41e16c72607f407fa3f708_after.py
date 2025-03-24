# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Delivery
from snabb.address.models import Address
from snabb.location.models import City
from snabb.contact.models import Contact
from snabb.quote.models import Quote
from .serializers import DeliverySerializer
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404, HttpResponse
from snabb.utils.code_response import get_response
from datetime import datetime
from django.utils.dateformat import format


class DeliveryViewSet(viewsets.ModelViewSet):

    """
    API endpoint that allows to create and get a delivery
    """

    serializer_class = DeliverySerializer
    queryset = Delivery.objects.all()

    def get_queryset(self):
        queryset = Delivery.objects.filter(
            delivery_quote__quote_user=self.request.user)
        return queryset

    def list(self, request):
        entries = Delivery.objects.filter(
            delivery_quote__quote_user=self.request.user)
        serializer = DeliverySerializer(entries, many=True)
        return Response(serializer.data)

    def create(self, request):
        received = request.data

        if not request.user.is_authenticated():  # Check if is authenticated
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

        if 'quote_id' not in received:
            response = get_response(400503)
            return Response(data=response['data'], status=response['status'])
        else:
            try:
                quote = Quote.objects.get(quote_id=received['quote_id'])
            except Quote.DoesNotExist:
                response = get_response(400506)
                return Response(
                    data=response['data'], status=response['status'])

        try:
            delivery = Delivery.objects.get(
                delivery_quote=received['quote_id'])
            response = get_response(400607)
            return Response(
                data=response['data'], status=response['status'])
        except Delivery.DoesNotExist:
            pass

        if 'selected_package_size' not in received:
            response = get_response(400504)
            return Response(data=response['data'], status=response['status'])
        else:
            package_size = received['selected_package_size']

        now = int(format(datetime.now(), u'U'))

        if quote.expire_at < now:
            response = get_response(400507)
            return Response(data=response['data'], status=response['status'])

        new_delivery = Delivery()
        new_delivery.delivery_quote = quote
        new_delivery.status = 'new'
        new_delivery.size = package_size
        new_delivery.price = quote.prices[package_size]['price']
        new_delivery.save()

        serializer = DeliverySerializer(new_delivery, many=False)
        return Response(serializer.data)
