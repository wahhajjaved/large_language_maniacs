import os
import mimetypes
import datetime

from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.utils import timezone
from pytz import timezone as pytz_timezone
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _

from irekua_database.utils import empty_JSON
from irekua_database.utils import hash_file
from irekua_database.models.base import IrekuaModelBaseUser
from sorl.thumbnail import ImageField


mimetypes.init()


def get_item_path(instance, filename):
    path_fmt = os.path.join(
        'items',
        '{collection}',
        '{sampling_event}',
        '{sampling_event_device}',
        '{hash}{ext}')

    mime_type, __ = mimetypes.guess_type(filename)
    extension = mimetypes.guess_extension(mime_type)

    sampling_event_device = instance.sampling_event_device
    sampling_event = sampling_event_device.sampling_event
    collection = sampling_event.collection

    instance.item_file.open()
    hash_string = hash_file(instance.item_file)

    path = path_fmt.format(
        collection=collection.pk,
        sampling_event=sampling_event.pk,
        sampling_event_device=sampling_event_device.pk,
        hash=hash_string,
        ext=extension)
    return path

def get_thumbnail_path(instance, filename):
    path_fmt = os.path.join(
        'thumbnails',
        '{collection}',
        '{sampling_event}',
        '{sampling_event_device}',
        '{hash}{ext}')

    mime_type, __ = mimetypes.guess_type(filename)
    extension = 'jpg'

    sampling_event_device = instance.sampling_event_device
    sampling_event = sampling_event_device.sampling_event
    collection = sampling_event.collection

    hash_string = instance.hash

    path = path_fmt.format(
        collection=collection.pk,
        sampling_event=sampling_event.pk,
        sampling_event_device=sampling_event_device.pk,
        hash=hash_string,
        ext=extension)
    return path

class Item(IrekuaModelBaseUser):
    hash_string = None
    item_size = None

    filesize = models.IntegerField(
        db_column='filesize',
        verbose_name=_('file size'),
        help_text=_('Size of resource in Bytes'),
        blank=True,
        null=True)
    hash = models.CharField(
        db_column='hash',
        verbose_name=_('hash'),
        help_text=_('Hash of resource file'),
        max_length=64,
        unique=True,
        blank=True,
        null=False)
    item_type = models.ForeignKey(
        'ItemType',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        verbose_name=_('item type'),
        help_text=_('Type of resource'),
        blank=False)
    item_file = models.FileField(
        upload_to=get_item_path,
        db_column='item_file',
        verbose_name=_('item file'),
        help_text=_('Upload file associated to file'),
        blank=True,
        null=True)
    item_thumbnail = ImageField(
        upload_to=get_thumbnail_path,
        db_column='item_thumbnail',
        verbose_name=_('item thumbnail'),
        help_text=_('Thumbnail associated to file'),
        blank=True,
        null=True)
    media_info = JSONField(
        db_column='media_info',
        default=empty_JSON,
        verbose_name=_('media info'),
        help_text=_('Information of resource file'),
        blank=True,
        null=False)
    sampling_event_device = models.ForeignKey(
        'SamplingEventDevice',
        db_column='sampling_event_device_id',
        verbose_name=_('sampling event device'),
        help_text=_('Sampling event device used to create item'),
        on_delete=models.PROTECT,
        blank=False,
        null=False)
    source = models.ForeignKey(
        'Source',
        db_column='source_id',
        verbose_name=_('source'),
        help_text=_('Source of item (parsing function and parent directory)'),
        on_delete=models.PROTECT,
        blank=True,
        null=True)
    source_foreign_key = models.CharField(
        db_column='source_foreign_key',
        verbose_name=_('source foreign key'),
        help_text=_('Foreign key of file in source database'),
        max_length=64,
        blank=True)
    metadata = JSONField(
        db_column='metadata',
        default=empty_JSON,
        verbose_name=_('metadata'),
        help_text=_('Metadata associated to item'),
        blank=True,
        null=True)

    captured_on = models.DateTimeField(
        db_column='captured_on',
        verbose_name=_('captured on'),
        help_text=_('Date on which item was produced'),
        blank=True,
        null=True)
    captured_on_year = models.IntegerField(
        db_column='captured_on_year',
        verbose_name=_('year'),
        help_text=_('Year in which the item was captured (YYYY)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(1800),
            MaxValueValidator(3000)])
    captured_on_month = models.IntegerField(
        db_column='captured_on_month',
        verbose_name=_('month'),
        help_text=_('Month in which the item was captured (1-12)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(12)])
    captured_on_day = models.IntegerField(
        db_column='captured_on_day',
        verbose_name=_('day'),
        help_text=_('Day in which the item was captured'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(32)])
    captured_on_hour = models.IntegerField(
        db_column='captured_on_hour',
        verbose_name=_('hour'),
        help_text=_('Hour of the day in which the item was captured (0 - 23)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(23)])
    captured_on_minute = models.IntegerField(
        db_column='captured_on_minute',
        verbose_name=_('minute'),
        help_text=_('Minute in which the item was captured (0-59)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59)])
    captured_on_second = models.IntegerField(
        db_column='captured_on_second',
        verbose_name=_('second'),
        help_text=_('Second in which the item was captured (0-59)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(59)])
    captured_on_timezone = models.CharField(
        max_length=256,
        db_column='captured_on_timezone',
        verbose_name=_('timezone'),
        help_text=_('Timezone corresponding to date fields'),
        blank=True,
        null=True)
    licence = models.ForeignKey(
        'Licence',
        db_column='licence_id',
        verbose_name=_('licence'),
        help_text=_('Licence of item'),
        on_delete=models.PROTECT,
        blank=True,
        null=True)

    tags = models.ManyToManyField(
        'Tag',
        verbose_name=_('tags'),
        help_text=_('Tags for item'),
        blank=True)
    ready_event_types = models.ManyToManyField(
        'EventType',
        verbose_name=_('ready event types'),
        help_text=_('Types of event for which item has been fully annotated'),
        blank=True)

    class Meta:
        verbose_name = _('Item')
        verbose_name_plural = _('Items')

        ordering = ['created_on']

        permissions = (
            ("download_item", _("Can download item")),
            ("annotate_item", _("Can annotate item")),
        )

    def __str__(self):
        return str(self.id)  # pylint: disable=E1101

    def validate_user(self):
        if self.created_by is None:
            self.created_by = self.sampling_event_device.created_by  # pylint: disable=E1101

        if self.created_by is None:
            msg = _(
                'Item creator was not specified and is not determined '
                'by sampling event device.')
            raise ValidationError(msg)

    @property
    def collection(self):
        return self.sampling_event_device.sampling_event.collection

    def date_in_range(self,date_info,time_info,date_down,date_up,tmezone):
        dlen = 0
        tlen = 0

        for k in date_info.keys():
            if date_info[k] is not None:
                dlen += 1

        for k in time_info.keys():
            if time_info[k] is not None:
                tlen += 1

        tz = pytz_timezone(timezone)

        date_down_ = date_down.astimezone(tz)
        date_up_ = date_up.astimezone(tz)

        hdate = None
        hdate_up = None
        hdate_down = None

        if dlen == 1:
            hdate = datetime.datetime(date_info["year"],1,1)
            hdate_down = datetime.datetime(date_down_.year,1,1)
            hdate_up = datetime.datetime(date_up_.year,1,1)
        elif dlen == 2:
            hdate = datetime.datetime(date_info["year"],date_info["month"],1)
            hdate_down = datetime.datetime(date_down_.year,date_down_.month,1)
            hdate_up = datetime.datetime(date_up_.year,date_up_.month,1)
        elif dlen == 3:
            if tlen == 0:
                hdate = datetime.datetime(date_info["year"],date_info["month"],date_info["day"])
                hdate_down = datetime.datetime(date_down_.year,date_down_.month,date_down_.day)
                hdate_up = datetime.datetime(date_up_.year,date_up_.month,date_up_.day)
            elif tlen == 1:
                hdate = datetime.datetime(date_info["year"],date_info["month"],date_info["day"])
                hdate_down = datetime.datetime(date_down_.year,date_down_.month,date_down_.day)
                hdate_up = datetime.datetime(date_up_.year,date_up_.month,date_up_.day)
            elif tlen == 2:
                hdate = datetime.datetime(date_info["year"],date_info["month"],date_info["day"],date_info["hour"],date_info["minute"])
                hdate_down = datetime.datetime(date_down_.year,date_down_.month,date_down_.day,date_down_.hour,date_down_.minute)
                hdate_up = datetime.datetime(date_up_.year,date_up_.month,date_up_.day,date_up_.hour,date_up_.minute)
            elif tlen == 3:
                hdate = datetime.datetime(date_info["year"],date_info["month"],date_info["day"],date_info["hour"],date_info["minute"],date_info["second"])
                hdate_down = datetime.datetime(date_down_.year,date_down_.month,date_down_.day,date_down_.hour,date_down_.minute,date_down_.second)
                hdate_up = datetime.datetime(date_up_.year,date_up_.month,date_up_.day,date_up_.hour,date_up_.minute,date_up_.second)
        else:
            return False

        hdate = tz.localize(hdate)
        hdate_up = tz.localize(hdate_up)
        hdate_down = tz.localize(hdate_down)

        if hdate >= hdate_down and hdate <= hdate_up:
            return True
        else:
            return False
        

    def check_captured_on(self):
        if self.captured_on is not None:
           captured_on = self.captured_on
        else:
           if self.captured_on_timezone:
               tz = pytz_timezone(self.captured_on_timezone)
               captured_on = datetime.datetime.now(tz=tz)
           else:
               captured_on = timezone.now()

        if (
                self.captured_on_year and
                self.captured_on_month and
                self.captured_on_day):

            captured_on.replace(
                year=self.captured_on_year,
                month=self.captured_on_month,
                day=self.captured_on_day)

            if (
                    self.captured_on_hour and
                    self.captured_on_minute and
                    self.captured_on_second):

                captured_on.replace(
                    hour=self.captured_on_hour,
                    minute=self.captured_on_minute,
                    second=self.captured_on_second)

            self.captured_on = captured_on

    def clean(self):
        self.check_captured_on()

        try:
            self.validate_hash_and_filesize()
        except ValidationError as error:
            raise ValidationError({'hash': error})

        try:
            self.validate_user()
        except ValidationError as error:
            raise ValidationError({'created_by': error})

        sampling_event = self.sampling_event_device.sampling_event

        deployed = self.sampling_event_device.deployed_on
        recovered = self.sampling_event_device.recovered_on
        date_info = {'year': self.captured_on_year,'month': self.captured_on_month,'day': self.captured_on_day}
        time_info = {'hour': self.captured_on_hour,'minute': self.captured_on_minute,'second': self.captured_on_second}
        timezone = self.captured_on_timezone

        if not self.date_in_range(date_info,time_info,deployed,recovered,timezone):
            raise ValidationError({'captured_on': error})

        # try:
        #     self.sampling_event.validate_date({
        #         'year': self.captured_on_year,
        #         'month': self.captured_on_month,
        #         'day': self.captured_on_day,
        #         'hour': self.captured_on_hour,
        #         'minute': self.captured_on_minute,
        #         'second': self.captured_on_second})
        # except ValidationError as error:
        #     raise ValidationError({'captured_on': error})

        collection = sampling_event.collection

        try:
            collection.validate_and_get_sampling_event_type(
                self.sampling_event_device.sampling_event.sampling_event_type)  # pylint: disable=E1101
        except ValidationError as error:
            raise ValidationError({'sampling': error})

        try:
            collection_item_type = collection.validate_and_get_item_type(
                self.item_type)
        except ValidationError as error:
            raise ValidationError({'item_type': error})

        if collection_item_type is not None:
            try:
                collection_item_type.validate_metadata(self.metadata)
            except ValidationError as error:
                raise ValidationError({'metadata': error})

        try:
            self.validate_licence()
        except ValidationError as error:
            raise ValidationError({'licence': error})

        try:
            self.item_type.validate_item_type(self)  # pylint: disable=E1101
        except ValidationError as error:
            raise ValidationError({'media_info': error})

        try:
            self.validate_mime_type()
        except ValidationError as error:
            raise ValidationError({'item_file': error})

        super(Item, self).clean()

    def validate_and_get_event_type(self, event_type):
        return self.item_type.validate_and_get_event_type(event_type)  # pylint: disable=E1101

    def validate_licence(self):
        if self.licence is not None:
            return

        if self.sampling_event_device.licence is None:  # pylint: disable=E1101
            msg = _(
                'Licence was not provided to item nor to sampling event')
            raise ValidationError({'licence': msg})

        self.licence = self.sampling_event_device.licence  # pylint: disable=E1101

        collection = self.sampling_event_device.sampling_event.collection  # pylint: disable=E1101
        collection.validate_and_get_licence(self.licence)

    def validate_hash_and_filesize(self):
        if self.item_file.name is None and self.hash is None:
            msg = _(
                'If no file is provided, a hash must be given')
            raise ValidationError(msg)

        if self.item_file.name is None:
            return

        self.item_file.open() # pylint: disable=E1101
        hash_string = hash_file(self.item_file)
        item_size = self.item_file.size  # pylint: disable=E1101

        if not self.hash:
            self.hash = hash_string
            self.filesize = item_size

        if self.hash != hash_string:
            msg = _('Hash of file and recorded hash do not coincide')
            raise ValidationError(msg)

    def validate_mime_type(self):
        physical_device = self.sampling_event_device.collection_device.physical_device
        device_type = physical_device.device.device_type
        mime_type, _ = mimetypes.guess_type(self.item_file.name)
        device_type.validate_mime_type(mime_type)

    def add_ready_event_type(self, event_type):
        self.ready_event_types.add(event_type)  # pylint: disable=E1101
        self.save()

    def remove_ready_event_type(self, event_type):
        self.ready_event_types.remove(event_type)  # pylint: disable=E1101
        self.save()

    def add_tag(self, tag):
        self.tags.add(tag)  # pylint: disable=E1101
        self.save()

    def remove_tag(self, tag):
        self.tags.remove(tag)  # pylint: disable=E1101
        self.save()

    def delete(self, *args, **kwargs):
        try:
            self.item_file.delete()
        except ValueError:
            pass
        super().delete(*args, **kwargs)
