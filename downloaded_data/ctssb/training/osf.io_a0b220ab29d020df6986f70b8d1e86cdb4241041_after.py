import logging
import random
from datetime import datetime

import bson
import modularodm.exceptions
import pytz
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError as DjangoValidationError, MultipleObjectsReturned
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from osf_models.exceptions import ValidationError
from osf_models.modm_compat import to_django_query
from osf_models.utils.base import generate_object_id

ALPHABET = '23456789abcdefghjkmnpqrstuvwxyz'

logger = logging.getLogger(__name__)


def generate_guid(length=5):
    while True:
        guid_id = ''.join(random.sample(ALPHABET, length))

        try:
            # is the guid in the blacklist
            BlackListGuid.objects.get(guid=guid_id)
        except BlackListGuid.DoesNotExist:
            # it's not, check and see if it's already in the database
            try:
                Guid.objects.get(_id=guid_id)
            except Guid.DoesNotExist:
                # valid and unique guid
                return guid_id


class MODMCompatibilityQuerySet(models.QuerySet):
    def sort(self, *fields):
        # Fields are passed in as e.g. [('title', 1), ('date_created', -1)]
        if isinstance(fields[0], list):
            fields = fields[0]

        def sort_key(item):
            if isinstance(item, basestring):
                return item
            elif isinstance(item, tuple):
                field_name, direction = item
                prefix = '-' if direction == -1 else ''
                return ''.join([prefix, field_name])

        sort_keys = [sort_key(each) for each in fields]
        return self.order_by(*sort_keys)

    def limit(self, n):
        return self[:n]


class BaseModel(models.Model):
    """Base model that acts makes subclasses mostly compatible with the
    modular-odm ``StoredObject`` interface.
    """

    migration_page_size = 20000

    objects = MODMCompatibilityQuerySet.as_manager()

    class Meta:
        abstract = True

    @classmethod
    def load(cls, data):
        try:
            if issubclass(cls, GuidMixin):
                return cls.objects.get(guids___id=data)
            elif issubclass(cls, ObjectIDMixin):
                return cls.objects.get(_id=data)
            return cls.objects.getQ(pk=data)
        except cls.DoesNotExist:
            return None

    @classmethod
    def find_one(cls, query):
        try:
            return cls.objects.get(to_django_query(query, model_cls=cls))
        except cls.DoesNotExist:
            raise modularodm.exceptions.NoResultsFound()
        except cls.MultipleObjectsReturned as e:
            raise modularodm.exceptions.MultipleResultsFound(*e.args)

    @classmethod
    def find(cls, query=None):
        if not query:
            return cls.objects.all()
        else:
            return cls.objects.filter(to_django_query(query, model_cls=cls))

    @classmethod
    def remove(cls, query):
        return cls.find(query).delete()

    @classmethod
    def remove_one(cls, obj):
        if obj.pk:
            return obj.delete()

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        """
        Given a modm object, make a django object with the same local fields.

        This is a base method that may work for simple objects.
        It should be customized in the child class if it doesn't work.

        :param modm_obj:
        :return:
        """
        django_obj = cls()

        local_django_fields = set([x.name for x in django_obj._meta.get_fields() if not x.is_relation])

        intersecting_fields = set(modm_obj.to_storage().keys()).intersection(
            set(local_django_fields))

        for field in intersecting_fields:
            modm_value = getattr(modm_obj, field)
            if modm_value is None:
                continue
            if isinstance(modm_value, datetime):
                modm_value = pytz.utc.localize(modm_value)
            setattr(django_obj, field, modm_value)

        return django_obj

    @property
    def _primary_name(self):
        return '_id'

    def reload(self):
        return self.refresh_from_db()

    def _natural_key(self):
        return self.pk

    def clone(self):
        """Create a new, unsaved copy of this object."""
        copy = self.__class__.objects.get(pk=self.pk)
        copy.id = None
        try:
            copy._id = bson.ObjectId()
        except AttributeError:
            pass
        return copy

    def save(self, *args, **kwargs):
        # Make Django validate on save (like modm)
        if not kwargs.get('force_insert') and not kwargs.get('force_update'):
            try:
                self.full_clean()
            except DjangoValidationError as err:
                raise ValidationError(*err.args)
        return super(BaseModel, self).save(*args, **kwargs)


# TODO: Rename to Identifier?
class Guid(BaseModel):
    """Stores either a short guid or long object_id for any model that inherits from BaseIDMixin.
    Each ID field (e.g. 'guid', 'object_id') MUST have an accompanying method, named with
    'initialize_<ID type>' (e.g. 'initialize_guid') that generates and sets the field.
    """
    primary_identifier_name = '_id'
    # TODO DELETE ME POST MIGRATION
    modm_query = None
    migration_page_size = 500000
    # /TODO DELETE ME POST MIGRATION

    id = models.AutoField(primary_key=True)
    _id = models.CharField(max_length=255, null=False, blank=False, default=generate_guid, db_index=True,
                           unique=True)
    referent = GenericForeignKey()
    content_type = models.ForeignKey(ContentType, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    created = models.DateTimeField(db_index=True, auto_now_add=True)

    # Override load in order to load by GUID
    @classmethod
    def load(cls, data):
        try:
            return cls.objects.get(_id=data)
        except cls.DoesNotExist:
            return None

    @classmethod
    def migrate_from_modm(cls, modm_obj, object_id=None, content_type=None):
        """
        Given a modm Guid make a django Guid

        :param object_id:
        :param content_type:
        :param modm_obj:
        :return:
        """
        django_obj = cls()

        if modm_obj._id != modm_obj.referent._id:
            # if the object has a BSON id, get the created date from that
            django_obj.created = bson.ObjectId(modm_obj.referent._id).generation_time
        else:
            # just make it now
            django_obj.created = timezone.now()

        django_obj._id = modm_obj._id

        if object_id and content_type:
            # if the referent was passed set the GFK to point to it
            django_obj.content_type = content_type
            django_obj.object_id = object_id

        return django_obj

    class Meta:
        ordering = ['-created']
        get_latest_by = 'created'


class BlackListGuid(BaseModel):
    # TODO DELETE ME POST MIGRATION
    modm_model_path = 'framework.guid.model.BlacklistGuid'
    modm_query = None
    migration_page_size = 500000
    # /TODO DELETE ME POST MIGRATION
    id = models.AutoField(primary_key=True)
    guid = models.fields.CharField(max_length=255, unique=True, db_index=True)

    @property
    def _id(self):
        return self.guid

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        """
        Given a modm BlacklistGuid make a django BlackListGuid

        :param modm_obj:
        :return:
        """
        django_obj = cls()

        django_obj.guid = modm_obj._id

        return django_obj


def generate_guid_instance():
    return Guid.objects.create().id


class PKIDStr(str):
    def __new__(self, _id, pk):
        return str.__new__(self, _id)

    def __init__(self, _id, pk):
        self.__pk = pk

    def __int__(self):
        return self.__pk


class BaseIDMixin(models.Model):
    @classmethod
    def migrate_from_modm(cls, modm_obj):
        """
        Given a modm object, make a django object with the same local fields.

        This is a base method that may work for simple objects.
        It should be customized in the child class if it doesn't work.

        :param modm_obj:
        :return:
        """
        django_obj = cls()

        local_django_fields = set([x.name for x in django_obj._meta.get_fields() if not x.is_relation])

        intersecting_fields = set(modm_obj.to_storage().keys()).intersection(
            set(local_django_fields))

        for field in intersecting_fields:
            modm_value = getattr(modm_obj, field)
            if modm_value is None:
                continue
            if isinstance(modm_value, datetime):
                modm_value = pytz.utc.localize(modm_value)
            setattr(django_obj, field, modm_value)

        return django_obj

    def clone(self):
        ret = super(BaseIDMixin, self).clone()
        ret.guid = None
        return ret

    class Meta:
        abstract = True


class ObjectIDMixin(BaseIDMixin):
    primary_identifier_name = '_id'

    _id = models.CharField(max_length=24, default=generate_object_id, unique=True, db_index=True)

    @classmethod
    def load(cls, q):
        try:
            return cls.objects.get(_id=q)
        except cls.DoesNotExist:
            # modm doesn't throw exceptions when loading things that don't exist
            return None

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        django_obj = super(ObjectIDMixin, cls).migrate_from_modm(modm_obj)
        django_obj._id = str(modm_obj._id)
        return django_obj

    class Meta:
        abstract = True

    def _natural_key(self):
        return self._id


class InvalidGuid(Exception):
    pass


class OptionalGuidMixin(BaseIDMixin):
    """
    This makes it so that things can **optionally** have guids. Think files.
    Things that inherit from this must also inherit from ObjectIDMixin ... probably
    """
    __guid_min_length__ = 5

    guids = GenericRelation(Guid, related_name='referent', related_query_name='referents')
    guid_string = ArrayField(models.CharField(max_length=255, null=True, blank=True), null=True, blank=True)
    content_type_pk = models.PositiveIntegerField(null=True, blank=True)

    def get_guid(self, create=False):
        if create:
            try:
                guid, created = Guid.objects.get_or_create(
                    object_id=self.pk,
                    content_type_pk=ContentType.objects.get_for_model(self).pk
                )
            except MultipleObjectsReturned:
                # lol, hacks
                pass
            else:
                return guid
        return self.guids.order_by('-created').first()

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        instance = super(OptionalGuidMixin, cls).migrate_from_modm(modm_obj)
        from website.models import Guid as MODMGuid
        from modularodm import Q as MODMQ
        if modm_obj.get_guid():
            guids = MODMGuid.find(MODMQ('referent', 'eq', modm_obj._id))
            setattr(instance, 'guid_string', [x.lower() for x in guids.get_keys()])
            setattr(instance, 'content_type_pk', ContentType.objects.get_for_model(cls).pk)
        return instance

    class Meta:
        abstract = True


class GuidMixin(BaseIDMixin):
    __guid_min_length__ = 5

    primary_identifier_name = 'guid_string'

    guids = GenericRelation(Guid, related_name='referent', related_query_name='referents')
    guid_string = ArrayField(models.CharField(max_length=255, null=True, blank=True), null=True, blank=True)
    content_type_pk = models.PositiveIntegerField(null=True, blank=True)

    # TODO: use pre-delete signal to disable delete cascade

    def _natural_key(self):
        return self.guid_string

    @property
    def _id(self):
        guid = self.guids.order_by('-created').first()
        if guid:
            return guid._id
        return None

    @_id.setter
    def _id(self, value):
        # TODO do we really want to allow this?
        guid, created = Guid.objects.get_or_create(_id=value)
        if created:
            guid.object_id = self.pk
            guid.content_type = ContentType.objects.get_for_model(self)
            guid.save()
        elif guid.content_type == ContentType.objects.get_for_model(self) and guid.object_id == self.pk:
            # TODO should this up the created for the guid until now so that it appears as the first guid
            # for this object?
            return
        else:
            raise InvalidGuid('Cannot indirectly repoint an existing guid, please use the Guid model')

    _primary_key = _id

    @classmethod
    def load(cls, q):
        try:
            # if referent doesn't exist it will return None
            return Guid.objects.get(_id=q).referent
        except Guid.DoesNotExist:
            # modm doesn't throw exceptions when loading things that don't exist
            return None

    @property
    def deep_url(self):
        return None

    @classmethod
    def migrate_from_modm(cls, modm_obj):
        """
        Given a modm object, make a django object with the same local fields.

        This is a base method that may work for simple objects.
        It should be customized in the child class if it doesn't work.

        :param modm_obj:
        :return:
        """
        django_obj = cls()

        local_django_fields = set(
            [x.name for x in django_obj._meta.get_fields() if not x.is_relation and x.name != '_id'])

        intersecting_fields = set(modm_obj.to_storage().keys()).intersection(
            set(local_django_fields))

        for field in intersecting_fields:
            modm_value = getattr(modm_obj, field)
            if modm_value is None:
                continue
            if isinstance(modm_value, datetime):
                modm_value = pytz.utc.localize(modm_value)
            setattr(django_obj, field, modm_value)

        from website.models import Guid as MODMGuid
        from modularodm import Q as MODMQ

        guids = MODMGuid.find(MODMQ('referent', 'eq', modm_obj._id))

        setattr(django_obj, 'guid_string', [x.lower() for x in guids.get_keys()])
        setattr(django_obj, 'content_type_pk', ContentType.objects.get_for_model(cls).pk)

        return django_obj

    class Meta:
        abstract = True


@receiver(post_save)
def ensure_guid(sender, instance, created, **kwargs):
    if not issubclass(sender, GuidMixin):
        return False
    if not instance.guids.exists() and instance.guid_string is None:
        print('Creating a guid for {} with a generated guid'.format(instance.__repr__()))
        Guid.objects.create(object_id=instance.pk, content_type=ContentType.objects.get_for_model(instance),
                            _id=generate_guid(instance.__guid_min_length__))
    elif not instance.guids.exists() and instance.guid_string is not None:
        print('Creating a guid for {} with an existing guid'.format(instance.__repr__()))
        Guid.objects.create(object_id=instance.pk, content_type_id=instance.content_type_pk,
                            _id=instance.guid_string)
