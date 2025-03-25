#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2011-2012 Luca Wehrstedt <luca.wehrstedt@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import simplejson as json
import os

from cmsranking.Config import config
from cmsranking.Logger import logger

from cmsranking.Entity import Entity, InvalidKey, InvalidData


class Store(object):
    """A store for entities.

    Provide methods to perform the CRUD operations (create, retrieve, update,
    delete) on a set of entities, accessed by their unique key.
    It's very similar to a dict, except that keys are strings, values are of
    a single type (defined at init-time) and it's possible to get notified
    when something changes by providing appropriate callbacks.

    """
    def __init__(self, entity, dir_name):
        """Initialize an empty EntityStore.

        The entity definition given as argument will define what kind of
        entities will be stored. It cannot be changed.

        entity (class): the class definition of the entities that will
            be stored

        """
        if not issubclass(entity, Entity):
            raise ValueError("The 'entity' parameter "
                             "isn't a subclass of Entity")
        self._entity = entity
        self._path = os.path.join(config.lib_dir, dir_name)
        self._store = dict()
        self._create_callbacks = list()
        self._update_callbacks = list()
        self._delete_callbacks = list()

        try:
            os.mkdir(self._path)
        except OSError:
            # it's ok: it means the directory already exists
            pass

        try:
            for name in os.listdir(self._path):
                if name[-5:] == '.json' and name[:-5] != '':
                    with open(os.path.join(self._path, name), 'r') as rec:
                        data = rec.read()
                        item = self._entity()
                        item.load(json.loads(data))
                        item.key = name[:-5]
                        self._store[name[:-5]] = item
        except OSError:
            # the path isn't a directory or is inaccessible
            logger.error("OSError occured", exc_info=True)
        except IOError:
            logger.error("IOError occured", exc_info=True)
        except ValueError:
            logger.error("Invalid JSON", exc_info=False,
                         extra={'location': os.path.join(self._path, name),
                                'details': data})
        except InvalidData, exc:
            logger.error(str(exc), exc_info=False,
                         extra={'location': os.path.join(self._path, name),
                                'details': data})

    def add_create_callback(self, callback):
        """Add a callback to be called when entities are created.

        Callbacks can be any kind of callable objects. They must accept
        a single argument: the key of the entity.

        """
        self._create_callbacks.append(callback)

    def add_update_callback(self, callback):
        """Add a callback to be called when entities are updated.

        Callbacks can be any kind of callable objects. They must accept
        a single argument: the key of the entity.

        """
        self._update_callbacks.append(callback)

    def add_delete_callback(self, callback):
        """Add a callback to be called when entities are deleted.

        Callbacks can be any kind of callable objects. They must accept
        a single argument: the key of the entity.

        """
        self._delete_callbacks.append(callback)

    def _verify_key(self, key, must_be_present=False):
        """Verify that the key has the correct type.

        key (string): the key of the entity we want to interact with.
        must_be_present (bool): True if we need the key in the store,
                                False if the key must not be in the
                                store.

        raise: InvalidKey if key is not valid.
        """
        if not (isinstance(key, unicode) or isinstance(key, str)):
            raise InvalidKey
        if (key in self._store and not must_be_present) or \
               (key not in self._store and must_be_present):
            raise InvalidKey

    def create(self, key, data):
        """Create a new entity.

        Create a new entity with the given key and the given data.

        key (str): the key with which the entity will be later accessed
        data (str): the properties of the entity (a dict encoded in JSON)

        Raise InvalidKey if key isn't a str or if an entity with the same
        key is already present in the store.
        Raise InvalidData if data cannot be parsed, if it's missing some
        properties or if properties are of the wrong type.

        """
        self._verify_key(key)

        # create entity
        try:
            item = self._entity()
            item.set(json.loads(data))
            item.key = key
            self._store[key] = item
        except ValueError:
            raise InvalidData('Invalid JSON')
        # notify callbacks
        for callback in self._create_callbacks:
            callback(key)
        # reflect changes on the persistent storage
        try:
            with open(os.path.join(self._path, key + '.json'), 'w') as rec:
                rec.write(json.dumps(self._store[key].dump()))
        except IOError:
            logger.error("IOError occured", exc_info=True)

    def update(self, key, data):
        """Update an entity.

        Update an existing entity with the given key and the given data.

        key (str): the key of the entity that has to be updated
        data (str): the new properties of the entity (a dict encoded in JSON)

        Raise InvalidKey if key isn't a str or if no entity with that key
        is present in the store.
        Raise InvalidData if data cannot be parsed, if it's missing some
        properties or if properties are of the wrong type.

        """
        self._verify_key(key, must_be_present=True)

        # update entity
        try:
            item = self._entity()
            item.set(json.loads(data))
            item.key = key
            self._store[key] = item
        except ValueError:
            raise InvalidData('Invalid JSON')
        # notify callbacks
        for callback in self._update_callbacks:
            callback(key)
        # reflect changes on the persistent storage
        try:
            with open(os.path.join(self._path, key + '.json'), 'w') as rec:
                rec.write(json.dumps(self._store[key].dump()))
        except IOError:
            logger.error("IOError occured", exc_info=True)

    def merge_list(self, data):
        """Merge a list of entities.

        Take a dictionary of entites and, for each of them:
         - if it's not present in the store, create it
         - if it's present, update it

        data (str): the dictionary of entities (a dict encoded in JSON)

        Raise InvalidData if data cannot be parsed, if an entity is missing
        some properties or if properties are of the wrong type.

        """
        try:
            data_dict = json.loads(data)
            assert type(data_dict) is dict, "Not a dictionary"
            item_dict = dict()
            for key, value in data_dict.iteritems():
                try:
                    item = self._entity()
                    item.set(value)
                    item.key = key
                    item_dict[key] = item
                except InvalidData as exc:
                    exc.message = '[entity %s] %s' % (key, exc)
                    exc.args = exc.message,
                    raise exc
        except ValueError:
            raise InvalidData('Invalid JSON')
        except AssertionError as message:
            raise InvalidData(str(message))

        for key, value in item_dict.iteritems():
            # insert entity
            self._store[key] = value
            # notify callbacks
            for callback in self._update_callbacks:
                callback(key)
            # reflect changes on the persistent storage
            try:
                with open(os.path.join(self._path, key + '.json'), 'w') as rec:
                    rec.write(json.dumps(value.dump()))
            except IOError:
                logger.error("IOError occured", exc_info=True)

    def delete(self, key):
        """Delete an entity.

        Delete an existing entity from the store.

        key (str): the key of the entity that has to be deleted

        Raise InvalidKey if key isn't a str or if no entity with that key
        is present in the store.

        """
        self._verify_key(key, must_be_present=True)

        # delete entity
        del self._store[key]
        # notify callbacks
        for callback in self._delete_callbacks:
            callback(key)
        # reflect changes on the persistent storage
        try:
            os.remove(os.path.join(self._path, key + '.json'))
        except OSError:
            logger.error("OSError occured", exc_info=True)

    def delete_list(self):
        """Delete all entities.

        Delete all existing entities from the store.

        """
        for key in list(self._store.iterkeys()):
            # delete entity
            del self._store[key]
            # notify callbacks
            for callback in self._delete_callbacks:
                callback(key)
            # reflect changes on the persistent storage
            try:
                os.remove(os.path.join(self._path, key + '.json'))
            except OSError:
                logger.error("OSError occured", exc_info=True)

    def retrieve(self, key):
        """Retrieve an entity.

        Retrieve an existing entity from the store.

        key (str): the key of the entity that has to be retrieved

        Raise InvalidKey if key isn't a str or if no entity with that key
        is present in the store.

        """
        self._verify_key(key, must_be_present=True)

        # retrieve entity
        # TODO remove "key" field from returned entity
        return json.dumps(self._store[key].get())

    def retrieve_list(self):
        """List all entities."""
        result = dict()
        for key, value in self._store.iteritems():
            result[key] = value.get()
        # TODO remove "key" field from returned entities
        return json.dumps(result)

    def __contains__(self, key):
        return key in self._store
