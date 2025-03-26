# -*- coding: utf-8 -*-
from datetime import date
import logging

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext as _
from odnoklassniki_api.decorators import fetch_all, fetch_only_expired, fetch_by_chunks_of, atomic
from odnoklassniki_api.models import OdnoklassnikiManager, OdnoklassnikiPKModel

log = logging.getLogger('odnoklassniki_users')

USER_INFO_TIMEOUT_DAYS = getattr(settings, 'ODNOKLASSNIKI_USERS_INFO_TIMEOUT_DAYS', 0)
USER_SEX_CHOICES = ((1, u'жен.'), (2, u'муж.'))


class UserManager(models.Manager):
    pass


class UserRemoteManager(OdnoklassnikiManager):

    fetch_users_limit = 100

    @atomic
    @fetch_only_expired(USER_INFO_TIMEOUT_DAYS)
    @fetch_by_chunks_of(fetch_users_limit)
    def fetch(self, ids, empty_pictures=True, **kwargs):
        kwargs['uids'] = ','.join(map(lambda i: str(i), ids))
        kwargs['fields'] = self.get_request_fields('user')
        # Если true, не возвращает изображения Odnoklassniki по умолчанию, когда фотография пользователя недоступна
        kwargs['emptyPictures'] = empty_pictures

        return super(UserRemoteManager, self).fetch(**kwargs)


class User(OdnoklassnikiPKModel):
    """
    Model of vkontakte user
    TODO: implement relatives, schools and universities connections
    TODO: make field screen_name unique
    """
    class Meta:
        verbose_name = _('Odnoklassniki user')
        verbose_name_plural = _('Odnoklassniki users')

    resolve_screen_name_type = 'PROFILE'
    methods_namespace = 'users'
    remote_pk_field = 'uid'
    slug_prefix = 'profile'

    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    shortname = models.CharField(max_length=100, db_index=True)

    gender = models.PositiveSmallIntegerField(null=True, choices=USER_SEX_CHOICES)
    age = models.PositiveSmallIntegerField(null=True, db_index=True)
    birthday = models.CharField(max_length=100)
    city = models.CharField(max_length=200)
    country = models.CharField(max_length=200)
    country_code = models.CharField(max_length=20)
    locale = models.CharField(max_length=5)

    photo_id = models.BigIntegerField(null=True)

    current_status = models.TextField()
    current_status_date = models.DateTimeField(null=True)
    current_status_id = models.BigIntegerField(null=True)

    allows_anonym_access = models.NullBooleanField()
    has_email = models.NullBooleanField()
    has_service_invisible = models.NullBooleanField()
    private = models.NullBooleanField()

    last_online = models.DateTimeField(null=True)
    registered_date = models.DateTimeField(null=True)

    photo_fields = ['pic1024x768', 'pic128max', 'pic128x128', 'pic180min',
                    'pic190x190', 'pic240min', 'pic320min', 'pic50x50', 'pic640x480']
    pic1024x768 = models.URLField()
    pic128max = models.URLField()
    pic128x128 = models.URLField()
    pic180min = models.URLField()
    pic190x190 = models.URLField()
    pic240min = models.URLField()
    pic320min = models.URLField()
    pic50x50 = models.URLField()
    pic640x480 = models.URLField()

    url_profile = models.URLField()
    url_profile_mobile = models.URLField()

    objects = UserManager()
    remote = UserRemoteManager(methods={
        'get': 'getInfo',
    })

    def parse(self, response):
        # gender
        if 'gender' in response:
            if response['gender'] == 'female':
                response['gender'] = 1
            elif response['gender'] == 'male':
                response['gender'] = 2

        # location
        if 'location' in response:
            location = response.pop('location')
            if 'city' in location:
                response['city'] = location['city']
            if 'country' in location:
                response['country'] = location['country']
            if 'countryCode' in location:
                response['country_code'] = location['countryCode']

        super(User, self).parse(response)

    @property
    def refresh_kwargs(self):
        return {'ids': [self.pk]}

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.update()
        return super(User, self).save(*args, **kwargs)

    def get_gender(self):
        return dict(USER_SEX_CHOICES).get(self.gender)

    def update(self):
        self.update_age()

    def update_age(self):
        parts = self.birthday.split('-')
        if len(parts) == 3:
            try:
                parts = map(int, parts)
                born = date(parts[0], parts[1], parts[2])
            except ValueError:
                return
            # Using solution from here
            # http://stackoverflow.com/questions/2217488/age-from-birthdate-in-python/9754466#9754466
            today = date.today()
            self.age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
