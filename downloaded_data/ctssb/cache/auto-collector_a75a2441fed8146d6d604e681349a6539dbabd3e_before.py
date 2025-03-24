import logging

from datetime import datetime
from functools import reduce
from psycopg2 import IntegrityError
from random import random
from sqlalchemy.sql import select

import settings

from auto.utils import db_insert, make_db_query, shorten_url


logger = logging.getLogger('auto.updater')


class Updater:
    pk_field = 'id'
    condition_fields = []
    comparable_fields = []
    shorten_url_fields = []
    cache_fieldsets = ['condition_fields', 'comparable_fields']
    table = None

    @classmethod
    async def new(cls, *args, **kwargs):
        self = cls(*args, **kwargs)
        self.cache_fields = self.get_cache_fields()

        async def get_cache_data(rows):
            cache = {}
            async for row in rows:
                cache[getattr(row, self.pk_field)] = [
                    getattr(row, field) for field in self.cache_fields
                ]
            return cache

        fields = list(set([self.pk_field] + self.cache_fields))
        query = select(getattr(self.table.c, field) for field in fields)
        query = self.complete_query(query)
        self.cache = await make_db_query(query, get_cache_data)
        self.not_updated = set(self.cache.keys())
        return self

    def __init__(self, table=None, shorten_url_fields=None):
        if table is not None:
            self.table = table

        if shorten_url_fields is not None:
            self.shorten_url_fields = shorten_url_fields

    def __iter__(self):
        for pk in self.cache:
            yield pk

    def complete_query(self, query):
        return query

    def get_update_probability(self, data, **kwargs):
        return 0

    def get_cache_fields(self):
        return list(set(reduce(
            lambda x, y: x + getattr(self, y),
            self.cache_fieldsets,
            [],
        )))

    def get_cache_data(self, pk):
        return dict(zip(self.cache_fields, self.cache[pk]))

    def get_condition_data(self, pk):
        cache = self.get_cache_data(pk)
        return {x: cache[x] for x in self.condition_fields}

    def get_pk_for_data(self, data):
        for pk in self.cache:
            cache = self.get_cache_data(pk)
            if all(cache[field] == data[field] for field in self.comparable_fields):
                return pk

    async def preprocess_data(self, data):
        if not data:
            return

        processed = {}

        if self.comparable_fields and self.pk_field not in data:
            pk = self.get_pk_for_data(data)
            processed[self.pk_field] = pk

        for field, value in data.items():
            if field in self.shorten_url_fields:
                value = await shorten_url(value)

            processed[field] = value

        return processed

    def get_updater_name(self):
        return self.__class__.__name__

    def get_log_message(self, msg, *args, **kwargs):
        msg = msg.format(*args, **kwargs)
        return '({}) {}'.format(self.get_updater_name(), msg)

    async def update(self, data):
        data = await self.preprocess_data(data)

        if not data:
            return

        pk = data.get(self.pk_field)
        self.not_updated.discard(pk)

        if pk not in self.cache:
            return await self.create(data)

        conditions = self.get_condition_data(pk)
        update_probability = self.get_update_probability(data, **conditions)

        if update_probability >= random():
            query = self.table.update().values(**data).where(self.table.c.id == pk)
            try:
                await make_db_query(self.complete_query(query))
                logger.debug(self.get_log_message('{}: Update #{}', self.table.name, pk))
            except IntegrityError as e:
                logger.warning(self.get_log_message(e))

        return data

    async def create(self, data):
        if not data.get(self.pk_field, True):
            del data[self.pk_field]

        query = self.table.insert().values(**data)

        try:
            pk = await db_insert(query)

            data[self.pk_field] = pk
            self.cache[pk] = [data.get(x) for x in self.cache_fields]
            logger.debug(self.get_log_message('{}: Create #{}', self.table.name, pk))
            return data
        except IntegrityError as e:
            logger.warning(e)

    async def delete_not_updated(self):
        if self.not_updated:
            pk_field = getattr(self.table.c, self.pk_field)
            query = self.table.delete().where(pk_field.in_(self.not_updated))
            result = await make_db_query(self.complete(query))

            for pk in self.not_updated:
                self.cache.pop(pk, None)

            msg = self.get_log_message(
                '{}: {} objects were removed!',
                self.table.name,
                len(self.not_updated),
            )
            logger.debug(msg)

        self.not_updated = set(self.cache.keys())


class OriginUpdater(Updater):
    origin_field = 'origin'
    origin = None

    def __init__(self, origin=None, *args, **kwargs):
        self.origin = origin or self.origin
        super().__init__(*args, **kwargs)

    def complete_query(self, query):
        query = super().complete_query(query)
        query = query.where(self.table.c.origin == self.origin)
        return query

    def get_updater_name(self):
        return '{}: {}'.format(super().get_updater_name(), self.origin)

    async def preprocess_data(self, data):
        data = await super().preprocess_data(data)

        if data:
            data[self.origin_field] = self.origin

        return data


class SynchronizerUpdater(Updater):
    comparable_fields = ['name']
    sync_fields = []
    origin_table = None
    real_instance_table = None  # use origin_table if not provided

    def get_update_probability(self, data, **kwargs):
        return 0

    async def get_real_instance(self, model, origin, pk):
        if not pk:
            return

        table = model.__table__
        query = table.select().where(table.c.id == pk).where(table.c.origin == origin)
        results = await make_db_query(query)
        instance = await results.first()
        return instance and instance.real_instance

    async def preprocess_data(self, data):
        if data and 'origin' in data:
            del data['origin']

        return await super().preprocess_data(data)

    async def sync(self):
        logger.debug('Synchronize {}'.format(self.table.name))

        real_instance_table = self.origin_table if self.real_instance_table is None else self.real_instance_table
        fields = set(self.sync_fields + self.comparable_fields)
        fields.add(self.pk_field)
        fields.add('origin')

        query_fields = [getattr(self.origin_table.c, field) for field in fields]
        query_fields.append(real_instance_table.c.real_instance)

        query = select(query_fields).where(real_instance_table.c.id == self.origin_table.c.id)
        rows = await make_db_query(query)

        async for row in rows:
            data = dict(row)
            origin = data['origin']
            prev_real_instance = data['real_instance']
            del data['real_instance']
            del data[self.pk_field]

            if not prev_real_instance and self.real_instance_table:
                continue

            if prev_real_instance:
                data[self.pk_field] = prev_real_instance

            object_data = await self.update(data)

            if not object_data:
                continue

            pk = object_data[self.pk_field]

            if prev_real_instance != pk:
                real_instance_pk_field = getattr(real_instance_table.c, self.pk_field)
                row_pk = getattr(row, self.pk_field)
                await make_db_query(
                    self.origin_table.update()
                    .values(real_instance=pk)
                    .where(getattr(self.origin_table.c, self.pk_field) == row_pk)
                    .where(self.origin_table.c.origin == origin)
                )


class UpdaterWithDatesMixin:
    created_at_field = 'created_at'
    updated_at_field = 'updated_at'

    def get_cache_fields(self):
        fields = super().get_cache_fields()
        fields = set(fields + [self.created_at_field, self.updated_at_field])
        return list(fields)

    async def create(self, data):
        data[self.created_at_field] = datetime.now()
        return await super().create(data)

    async def preprocess_data(self, data):
        data = await super().preprocess_data(data)
        if data:
            data[self.updated_at_field] = datetime.now()
        return data


class UpdateNotSimilarMixin:
    def get_update_probability(self, data, **conditions):
        for condition, value in conditions.items():
            if data[condition] != value:
                return 1

        return 0


class UpdateByCreatedAtMixin:
    threshold = 60 * 60 * 24

    def __init__(self, *args, **kwargs):
        if self.created_at_field not in self.condition_fields:
            self.condition_fields = list(self.condition_fields) + [self.created_at_field]

        return super().__init__(*args, **kwargs)

    def get_update_probability(self, data, created_at=None, **kwargs):
        if not created_at:
            return 1.0

        delta_seconds = (datetime.now() - created_at).total_seconds()

        if delta_seconds < self.threshold:
            return delta_seconds / self.threshold
        else:
            return self.threshold / delta_seconds
