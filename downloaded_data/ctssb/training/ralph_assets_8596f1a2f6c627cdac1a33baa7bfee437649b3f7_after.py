#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Asset management models."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

import datetime
from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils.translation import ugettext_lazy as _
from lck.django.common.models import (
    EditorTrackable,
    Named,
    SoftDeletable,
    TimeTrackable,
    ViewableSoftDeletableManager
)
from lck.django.choices import Choices
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel
from uuid import uuid4

from ralph.business.models import Venture
from ralph.discovery.models_device import Device, DeviceType
from ralph.discovery.models_util import SavingUser
from lck.django.common.models import WithConcurrentGetOrCreate


SAVE_PRIORITY = 0


class LicenseType(Choices):
    _ = Choices.Choice
    not_applicable = _("not applicable")
    oem = _("oem")
    box = _("box")


class AssetType(Choices):
    _ = Choices.Choice

    DC = Choices.Group(0)
    data_center = _("data center")

    BO = Choices.Group(100)
    back_office = _("back office")
    administration = _("administration")


class AssetStatus(Choices):
    _ = Choices.Choice

    HARDWARE = Choices.Group(0)
    new = _("new")
    in_progress = _("in progress")
    waiting_for_release = _("waiting for release")
    used = _("used")
    loan = _("loan")
    damaged = _("damaged")
    liquidated = _("liquidated")
    in_service = _("in service")
    in_repair = _("in repair")
    ok = _("ok")

    SOFTWARE = Choices.Group(100)
    installed = _("installed")
    free = _("free")
    reserved = _("reserved")


class AssetSource(Choices):
    _ = Choices.Choice

    shipment = _("shipment")
    salvaged = _("salvaged")


class AssetCategoryType(Choices):
    _ = Choices.Choice

    back_office = _("back office")
    data_center = _("data center")


class AssetManufacturer(TimeTrackable, EditorTrackable, Named):
    def __unicode__(self):
        return self.name


class AssetModel(
        TimeTrackable, EditorTrackable, Named, WithConcurrentGetOrCreate):
    manufacturer = models.ForeignKey(
        AssetManufacturer, on_delete=models.PROTECT, blank=True, null=True)

    def __unicode__(self):
        return "%s %s" % (self.manufacturer, self.name)


class AssetCategory(
        MPTTModel, TimeTrackable, EditorTrackable, WithConcurrentGetOrCreate):
    name = models.CharField(max_length=50, unique=True)
    type = models.PositiveIntegerField(
        verbose_name=_("type"), choices=AssetCategoryType(),
    )
    parent = TreeForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
    )

    class MPTTMeta:
        order_insertion_by = ['name']

    def __unicode__(self):
        return self.name


class Warehouse(TimeTrackable, EditorTrackable, Named,
                WithConcurrentGetOrCreate):
    def __unicode__(self):
        return self.name


def _get_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid4(), ext)
    return os.path.join('assets', filename)


class BOAdminManager(models.Manager):
    def get_query_set(self):
        return super(BOAdminManager, self).get_query_set().filter(
            type__in=(AssetType.BO.choices)
        )


class DCAdminManager(models.Manager):
    def get_query_set(self):
        return super(DCAdminManager, self).get_query_set().filter(
            type__in=(AssetType.DC.choices)
        )


class AssetAdminManager(models.Manager):
    pass


class BOManager(BOAdminManager, ViewableSoftDeletableManager):
    pass


class DCManager(DCAdminManager, ViewableSoftDeletableManager):
    pass


class Asset(TimeTrackable, EditorTrackable, SavingUser, SoftDeletable):
    device_info = models.OneToOneField(
        'DeviceInfo', null=True, blank=True, on_delete=models.CASCADE
    )
    part_info = models.OneToOneField(
        'PartInfo', null=True, blank=True, on_delete=models.CASCADE
    )
    office_info = models.OneToOneField(
        'OfficeInfo', null=True, blank=True, on_delete=models.CASCADE
    )
    type = models.PositiveSmallIntegerField(choices=AssetType())
    model = models.ForeignKey('AssetModel', on_delete=models.PROTECT)
    source = models.PositiveIntegerField(
        verbose_name=_("source"), choices=AssetSource(), db_index=True
    )
    invoice_no = models.CharField(
        max_length=128, db_index=True, null=True, blank=True
    )
    order_no = models.CharField(max_length=50, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    sn = models.CharField(max_length=200, null=True, blank=True, unique=True)
    barcode = models.CharField(
        max_length=200, null=True, blank=True, unique=True, default=None
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    support_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    support_period = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="support period in months"
    )
    support_type = models.CharField(max_length=150)
    support_void_reporting = models.BooleanField(default=True, db_index=True)
    provider = models.CharField(max_length=100, null=True, blank=True)
    status = models.PositiveSmallIntegerField(
        default=AssetStatus.new.id,
        verbose_name=_("status"),
        choices=AssetStatus(),
    )
    remarks = models.CharField(
        verbose_name='Additional remarks',
        max_length=1024,
        blank=True,
    )
    niw = models.CharField(max_length=50, null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    request_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    production_use_date = models.DateField(null=True, blank=True)
    provider_order_date = models.DateField(null=True, blank=True)
    deprecation_rate = models.DecimalField(
        decimal_places=2, max_digits=5, null=True, blank=True)
    category = models.ForeignKey('AssetCategory', null=True, blank=True)
    slots = models.FloatField(
        verbose_name='Slots (for blade centers)',
        max_length=64,
        default=0,
    )
    admin_objects = AssetAdminManager()
    admin_objects_dc = DCAdminManager()
    admin_objects_bo = BOAdminManager()
    objects_dc = DCManager()
    objects_bo = BOManager()

    def __unicode__(self):
        return "{} - {} - {}".format(self.model, self.sn, self.barcode)

    @property
    def venture(self):
        if not self.device_info or not self.device_info.ralph_device_id:
            return None
        else:
            return Device.objects.get(
                pk=self.device_info.ralph_device_id,
            ).venture

    @classmethod
    def create(cls, base_args, device_info_args=None, part_info_args=None):
        asset = Asset(**base_args)
        if device_info_args:
            d = DeviceInfo(**device_info_args)
            d.save()
            asset.device_info = d
        elif part_info_args:
            d = PartInfo(**part_info_args)
            d.save()
            asset.part_info = d
        asset.save()
        return asset

    def get_data_type(self):
        if self.device_info:
            return 'device'
        elif self.part_info:
            return 'part'
        else:
            # should not return this value ;-)
            return 'Unknown'

    def get_data_icon(self):
        if self.get_data_type() == 'device':
            return 'fugue-computer'
        elif self.get_data_type() == 'part':
            return 'fugue-box'
        else:
            raise UserWarning('Unknown asset data type!')

    def create_stock_device(self):
        if self.type and self.type.name is not 'data_center':
            return
        try:
            if self.sn:
                device = Device.objects.get(sn=self.sn)
            elif self.barcode:
                device = Device.objects.get(barcode=self.barcode)
            else:
                raise UserWarning("No barcode and no sn")
        except Device.DoesNotExist:
            try:
                venture = Venture.objects.get(name='Stock')
            except Venture.DoesNotExist:
                venture = Venture(name='Stock', symbol='stock')
                venture.save()
            device = Device.create(
                sn=self.sn or 'bc-' + self.barcode,
                barcode=self.barcode,
                model_name='Unknown',
                model_type=DeviceType.unknown,
                priority=SAVE_PRIORITY,
                venture=venture,
                name='Unknown',
            )
        self.device_info.ralph_device_id = device
        self.device_info.save()

    def get_parts_info(self):
        return PartInfo.objects.filter(device=self)

    def get_parts(self):
        return Asset.objects.filter(part_info__device=self)

    def has_parts(self):
        return PartInfo.objects.filter(device=self).exists()

    def __init__(self, *args, **kwargs):
        self.save_comment = None
        self.saving_user = None
        super(Asset, self).__init__(*args, **kwargs)

    def is_deprecated(self):
        if not self.support_period or not self.invoice_date:
            return False
        if isinstance(self.invoice_date, basestring):
            self.invoice_date = datetime.datetime.strptime(
                self.invoice_date, '%Y-%m-%d'
            )
        deprecation_date = self.invoice_date + relativedelta(
            months=self.support_period
        )
        if isinstance(deprecation_date, datetime.datetime):
            deprecation_date = deprecation_date.date()
        return deprecation_date < datetime.date.today()

    def delete_with_info(self, *args, **kwargs):
        """
        Remove Asset with linked info-tables alltogether, because cascade
        works bottom-up only.
        """
        if self.part_info:
            self.part_info.delete()
        elif self.office_info:
            self.office_info.delete()
        elif self.device_info:
            self.device_info.delete()
        return super(Asset, self).delete(*args, **kwargs)


class DeviceInfo(TimeTrackable, SavingUser, SoftDeletable):
    ralph_device_id = models.IntegerField(
        verbose_name=_("Ralph device id"),
        null=True,
        blank=True,
        unique=True,
        default=None,
    )
    size = models.PositiveSmallIntegerField(
        verbose_name='Size in units', default=1
    )
    u_level = models.CharField(max_length=10, null=True, blank=True)
    u_height = models.CharField(max_length=10, null=True, blank=True)
    rack = models.CharField(max_length=10, null=True, blank=True)

    def __unicode__(self):
        return "{} - {}".format(
            self.ralph_device_id,
            self.size,
        )

    def __init__(self, *args, **kwargs):
        self.save_comment = None
        self.saving_user = None
        super(DeviceInfo, self).__init__(*args, **kwargs)


class OfficeInfo(TimeTrackable, SavingUser, SoftDeletable):
    license_key = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=50, blank=True)
    attachment = models.FileField(
        upload_to=_get_file_path, blank=True)
    license_type = models.IntegerField(
        choices=LicenseType(), verbose_name=_("license type"),
        null=True, blank=True
    )
    date_of_last_inventory = models.DateField(
        null=True, blank=True)
    last_logged_user = models.CharField(max_length=100, null=True, blank=True)

    def __unicode__(self):
        return "{} - {} - {}".format(
            self.license_key,
            self.version,
            self.license_type
        )

    def __init__(self, *args, **kwargs):
        self.save_comment = None
        self.saving_user = None
        super(OfficeInfo, self).__init__(*args, **kwargs)


class PartInfo(TimeTrackable, SavingUser, SoftDeletable):
    barcode_salvaged = models.CharField(max_length=200, null=True, blank=True)
    source_device = models.ForeignKey(
        Asset, null=True, blank=True, related_name='source_device'
    )
    device = models.ForeignKey(
        Asset, null=True, blank=True, related_name='device'
    )

    def __unicode__(self):
        return "{} - {}".format(self.device, self.barcode_salvaged)

    def __init__(self, *args, **kwargs):
        self.save_comment = None
        self.saving_user = None
        super(PartInfo, self).__init__(*args, **kwargs)
