# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import hashlib
import time
from django.db import models


def _create_hash():
    """This function generate 10 character long hash"""
    hash_value = hashlib.sha1()
    hash_value.update(str(time.time()).encode('utf8'))
    return hash_value.hexdigest()[:-20]


class Delivery(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    quote_id = models.CharField(max_length=100, blank=True, default='')
    currency_code = models.CharField(max_length=100, blank=True, default='SEK')
    owner = models.ForeignKey('auth.User', related_name='deliveries', default='')
    tracking_url = models.TextField(default='')

    class Meta:
        ordering = ('created',)


class Quote(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    quote_id = models.CharField(max_length=20, unique=True)
    currency_code = models.CharField(max_length=100, blank=True, default='SEK')
    pickup_eta = models.IntegerField(default=0)
    delivery_eta = models.TextField(default=0)

    class Meta:
        ordering = ('created',)

    def save(self, *args, **kwargs):
        """
        Use the create_hash to generate a unique identifier for the order
        """
        self.quote_id = _create_hash()
        super(Quote, self).save(*args, **kwargs)


class Location(models.Model):
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    latitude = models.FloatField(default='0.0')
    longitude = models.FloatField(default='0.0')
