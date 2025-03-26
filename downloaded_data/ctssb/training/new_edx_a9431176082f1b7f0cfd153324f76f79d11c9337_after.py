import pymongo
import sys
import logging
import copy

from bson.son import SON
from collections import namedtuple
from fs.osfs import OSFS
from itertools import repeat
from path import path
from datetime import datetime, timedelta

from importlib import import_module
from xmodule.errortracker import null_error_tracker, exc_info_to_str
from xmodule.mako_module import MakoDescriptorSystem
from xmodule.x_module import XModuleDescriptor
from xmodule.error_module import ErrorDescriptor
from xblock.runtime import DbModel, KeyValueStore, InvalidScopeError
from xblock.core import Scope

from . import ModuleStoreBase, Location
from .draft import DraftModuleStore
from .exceptions import (ItemNotFoundError,
                         DuplicateItemError)
from .inheritance import own_metadata, INHERITABLE_METADATA, inherit_metadata


log = logging.getLogger(__name__)

# TODO (cpennington): This code currently operates under the assumption that
# there is only one revision for each item. Once we start versioning inside the CMS,
# that assumption will have to change


class MongoKeyValueStore(KeyValueStore):
    """
    A KeyValueStore that maps keyed data access to one of the 3 data areas
    known to the MongoModuleStore (data, children, and metadata)
    """
    def __init__(self, data, children, metadata):
        self._data = data
        self._children = children
        self._metadata = metadata

    def get(self, key):
        if key.scope == Scope.children:
            return self._children
        elif key.scope == Scope.parent:
            return None
        elif key.scope == Scope.settings:
            return self._metadata[key.field_name]
        elif key.scope == Scope.content:
            if key.field_name == 'data' and not isinstance(self._data, dict):
                return self._data
            else:
                return self._data[key.field_name]
        else:
            raise InvalidScopeError(key.scope)

    def set(self, key, value):
        if key.scope == Scope.children:
            self._children = value
        elif key.scope == Scope.settings:
            self._metadata[key.field_name] = value
        elif key.scope == Scope.content:
            if key.field_name == 'data' and not isinstance(self._data, dict):
                self._data = value
            else:
                self._data[key.field_name] = value
        else:
            raise InvalidScopeError(key.scope)

    def delete(self, key):
        if key.scope == Scope.children:
            self._children = []
        elif key.scope == Scope.settings:
            if key.field_name in self._metadata:
                del self._metadata[key.field_name]
        elif key.scope == Scope.content:
            if key.field_name == 'data' and not isinstance(self._data, dict):
                self._data = None
            else:
                del self._data[key.field_name]
        else:
            raise InvalidScopeError(key.scope)

    def has(self, key):
        if key.scope in (Scope.children, Scope.parent):
            return True
        elif key.scope == Scope.settings:
            return key.field_name in self._metadata
        elif key.scope == Scope.content:
            if key.field_name == 'data' and not isinstance(self._data, dict):
                return True
            else:
                return key.field_name in self._data
        else:
            raise InvalidScopeError(key.scope)

MongoUsage = namedtuple('MongoUsage', 'id, def_id')


class CachingDescriptorSystem(MakoDescriptorSystem):
    """
    A system that has a cache of module json that it will use to load modules
    from, with a backup of calling to the underlying modulestore for more data
    TODO (cdodge) when the 'split module store' work has been completed we can remove all
    references to metadata_inheritance_tree
    """
    def __init__(self, modulestore, module_data, default_class, resources_fs,
                 error_tracker, render_template, metadata_inheritance_tree = None):
        """
        modulestore: the module store that can be used to retrieve additional modules

        module_data: a dict mapping Location -> json that was cached from the
            underlying modulestore

        default_class: The default_class to use when loading an
            XModuleDescriptor from the module_data

        resources_fs: a filesystem, as per MakoDescriptorSystem

        error_tracker: a function that logs errors for later display to users

        render_template: a function for rendering templates, as per
            MakoDescriptorSystem
        """
        super(CachingDescriptorSystem, self).__init__(
                self.load_item, resources_fs, error_tracker, render_template)
        self.modulestore = modulestore
        self.module_data = module_data
        self.default_class = default_class
        # cdodge: other Systems have a course_id attribute defined. To keep things consistent, let's
        # define an attribute here as well, even though it's None
        self.course_id = None
        self.metadata_inheritance_tree = metadata_inheritance_tree

    def load_item(self, location):
        location = Location(location)
        json_data = self.module_data.get(location)
        if json_data is None:
            module = self.modulestore.get_item(location)
            if module is not None:
                # update our own cache after going to the DB to get cache miss
                self.module_data.update(module.system.module_data)
            return module
        else:
            # load the module and apply the inherited metadata
            try:
                class_ = XModuleDescriptor.load_class(
                    json_data['location']['category'],
                    self.default_class
                )
                definition = json_data.get('definition', {})
                kvs = MongoKeyValueStore(
                    definition.get('data', {}),
                    definition.get('children', []),
                    json_data.get('metadata', {}),
                )

                model_data = DbModel(kvs, class_, None, MongoUsage(self.course_id, location))
                module = class_(self, location, model_data)
                if self.metadata_inheritance_tree is not None:
                    metadata_to_inherit = self.metadata_inheritance_tree.get('parent_metadata', {}).get(location.url(), {})
                    inherit_metadata(module, metadata_to_inherit)
                return module
            except:
                log.warning("Failed to load descriptor", exc_info=True)
                return ErrorDescriptor.from_json(
                    json_data,
                    self,
                    error_msg=exc_info_to_str(sys.exc_info())
                )


def location_to_query(location, wildcard=True):
    """
    Takes a Location and returns a SON object that will query for that location.
    Fields in location that are None are ignored in the query

    If `wildcard` is True, then a None in a location is treated as a wildcard
    query. Otherwise, it is searched for literally
    """
    query = namedtuple_to_son(Location(location), prefix='_id.')

    if wildcard:
        for key, value in query.items():
            if value is None:
                del query[key]

    return query


def namedtuple_to_son(namedtuple, prefix=''):
    """
    Converts a namedtuple into a SON object with the same key order
    """
    son = SON()
    for idx, field_name in enumerate(namedtuple._fields):
        son[prefix + field_name] = namedtuple[idx]
    return son


class MongoModuleStore(ModuleStoreBase):
    """
    A Mongodb backed ModuleStore
    """

    # TODO (cpennington): Enable non-filesystem filestores
    def __init__(self, host, db, collection, fs_root, render_template,
                 port=27017, default_class=None,
                 error_tracker=null_error_tracker,
                 user=None, password=None, **kwargs):

        ModuleStoreBase.__init__(self)

        self.collection = pymongo.connection.Connection(
            host=host,
            port=port,
            **kwargs
        )[db][collection]

        if user is not None and password is not None:
            self.collection.database.authenticate(user, password)


        # Force mongo to report errors, at the expense of performance
        self.collection.safe = True

        # Force mongo to maintain an index over _id.* that is in the same order
        # that is used when querying by a location
        self.collection.ensure_index(
            zip(('_id.' + field for field in Location._fields), repeat(1)))

        if default_class is not None:
            module_path, _, class_name = default_class.rpartition('.')
            class_ = getattr(import_module(module_path), class_name)
            self.default_class = class_
        else:
            self.default_class = None
        self.fs_root = path(fs_root)
        self.error_tracker = error_tracker
        self.render_template = render_template
        self.metadata_inheritance_cache = {}

    def get_metadata_inheritance_tree(self, location):
        '''
        TODO (cdodge) This method can be deleted when the 'split module store' work has been completed
        '''

        # get all collections in the course, this query should not return any leaf nodes
        query = {
                    '_id.org': location.org,
                    '_id.course': location.course,
                    '$or': [
                    {"_id.category":"course"},
                    {"_id.category":"chapter"},
                    {"_id.category":"sequential"},
                    {"_id.category":"vertical"}
                ]
                }
        # we just want the Location, children, and metadata
        record_filter = {'_id':1,'definition.children':1,'metadata':1}

        # call out to the DB
        resultset = self.collection.find(query, record_filter)

        results_by_url = {}
        root = None

        # now go through the results and order them by the location url
        for result in resultset:
            location = Location(result['_id'])
            results_by_url[location.url()] = result
            if location.category == 'course':
                root = location.url()

        # now traverse the tree and compute down the inherited metadata
        metadata_to_inherit = {}
        def _compute_inherited_metadata(url):
            my_metadata = results_by_url[url]['metadata']
            for key in my_metadata.keys():
                if key not in INHERITABLE_METADATA:
                    del my_metadata[key]
            results_by_url[url]['metadata'] = my_metadata

            # go through all the children and recurse, but only if we have
            # in the result set. Remember results will not contain leaf nodes
            for child in results_by_url[url].get('definition',{}).get('children',[]):
                if child in results_by_url:
                    new_child_metadata = copy.deepcopy(my_metadata)
                    new_child_metadata.update(results_by_url[child]['metadata'])
                    results_by_url[child]['metadata'] = new_child_metadata
                    metadata_to_inherit[child] = new_child_metadata
                    _compute_inherited_metadata(child)
                else:
                    # this is likely a leaf node, so let's record what metadata we need to inherit
                    metadata_to_inherit[child] = my_metadata

        if root is not None:
            _compute_inherited_metadata(root)

        cache = {'parent_metadata': metadata_to_inherit,
            'timestamp' : datetime.now()}

        return cache

    def get_cached_metadata_inheritance_tree(self, location, max_age_allowed):
        '''
        TODO (cdodge) This method can be deleted when the 'split module store' work has been completed
        '''
        cache_name = '{0}/{1}'.format(location.org, location.course)
        cache = self.metadata_inheritance_cache.get(cache_name,{'parent_metadata': {},
            'timestamp': datetime.now() - timedelta(hours=1)})
        age = (datetime.now() - cache['timestamp'])

        if age.seconds >= max_age_allowed:
            logging.debug('loading entire inheritance tree for {0}'.format(cache_name))
            cache = self.get_metadata_inheritance_tree(location)
            self.metadata_inheritance_cache[cache_name] = cache

        return cache



    def _clean_item_data(self, item):
        """
        Renames the '_id' field in item to 'location'
        """
        item['location'] = item['_id']
        del item['_id']

    def _cache_children(self, items, depth=0):
        """
        Returns a dictionary mapping Location -> item data, populated with json data
        for all descendents of items up to the specified depth.
        (0 = no descendents, 1 = children, 2 = grandchildren, etc)
        If depth is None, will load all the children.
        This will make a number of queries that is linear in the depth.
        """

        data = {}
        to_process = list(items)
        while to_process and depth is None or depth >= 0:
            children = []
            for item in to_process:
                self._clean_item_data(item)
                children.extend(item.get('definition', {}).get('children', []))
                data[Location(item['location'])] = item

            # Load all children by id. See
            # http://www.mongodb.org/display/DOCS/Advanced+Queries#AdvancedQueries-%24or
            # for or-query syntax
            if children:
                query = {
                    '_id': {'$in': [namedtuple_to_son(Location(child)) for child in children]}
                }
                to_process = self.collection.find(query)
            else:
                to_process = []
            # If depth is None, then we just recurse until we hit all the descendents
            if depth is not None:
                depth -= 1

        return data

    def _load_item(self, item, data_cache):
        """
        Load an XModuleDescriptor from item, using the children stored in data_cache
        """
        data_dir = getattr(item, 'data_dir', item['location']['course'])
        root = self.fs_root / data_dir

        if not root.isdir():
            root.mkdir()

        resource_fs = OSFS(root)

        metadata_inheritance_tree = None

        # if we are loading a course object, there is no parent to inherit the metadata from
        # so don't bother getting it
        if item['location']['category'] != 'course':
            metadata_inheritance_tree = self.get_cached_metadata_inheritance_tree(Location(item['location']), 300)

        # TODO (cdodge): When the 'split module store' work has been completed, we should remove
        # the 'metadata_inheritance_tree' parameter
        system = CachingDescriptorSystem(
            self,
            data_cache,
            self.default_class,
            resource_fs,
            self.error_tracker,
            self.render_template,
            metadata_inheritance_tree = metadata_inheritance_tree
        )
        return system.load_item(item['location'])

    def _load_items(self, items, depth=0):
        """
        Load a list of xmodules from the data in items, with children cached up
        to specified depth
        """
        data_cache = self._cache_children(items, depth)

        return [self._load_item(item, data_cache) for item in items]

    def get_courses(self):
        '''
        Returns a list of course descriptors.
        '''
        # TODO (vshnayder): Why do I have to specify i4x here?
        course_filter = Location("i4x", category="course")
        return self.get_items(course_filter)

    def _find_one(self, location):
        '''Look for a given location in the collection.  If revision is not
        specified, returns the latest.  If the item is not present, raise
        ItemNotFoundError.
        '''
        item = self.collection.find_one(
            location_to_query(location, wildcard=False),
            sort=[('revision', pymongo.ASCENDING)],
        )
        if item is None:
            raise ItemNotFoundError(location)
        return item

    def has_item(self, location):
        """
        Returns True if location exists in this ModuleStore.
        """
        location = Location.ensure_fully_specified(location)
        try:
            self._find_one(location)
            return True
        except ItemNotFoundError:
            return False

    def get_item(self, location, depth=0):
        """
        Returns an XModuleDescriptor instance for the item at location.

        If any segment of the location is None except revision, raises
            xmodule.modulestore.exceptions.InsufficientSpecificationError
        If no object is found at that location, raises
            xmodule.modulestore.exceptions.ItemNotFoundError

        location: a Location object
        depth (int): An argument that some module stores may use to prefetch
            descendents of the queried modules for more efficient results later
            in the request. The depth is counted in the number of
            calls to get_children() to cache. None indicates to cache all descendents.
        """
        location = Location.ensure_fully_specified(location)
        item = self._find_one(location)
        module = self._load_items([item], depth)[0]
        return module

    def get_instance(self, course_id, location, depth=0):
        """
        TODO (vshnayder): implement policy tracking in mongo.
        For now, just delegate to get_item and ignore policy.

        depth (int): An argument that some module stores may use to prefetch
            descendents of the queried modules for more efficient results later
            in the request. The depth is counted in the number of
            calls to get_children() to cache. None indicates to cache all descendents.
        """
        return self.get_item(location, depth=depth)

    def get_items(self, location, course_id=None, depth=0):
        items = self.collection.find(
            location_to_query(location),
            sort=[('revision', pymongo.ASCENDING)],
        )

        modules = self._load_items(list(items), depth)
        return modules

    def clone_item(self, source, location):
        """
        Clone a new item that is a copy of the item at the location `source`
        and writes it to `location`
        """
        try:
            source_item = self.collection.find_one(location_to_query(source))
            source_item['_id'] = Location(location).dict()
            self.collection.insert(source_item)
            item = self._load_items([source_item])[0]

            # VS[compat] cdodge: This is a hack because static_tabs also have references from the course module, so
            # if we add one then we need to also add it to the policy information (i.e. metadata)
            # we should remove this once we can break this reference from the course to static tabs
            if location.category == 'static_tab':
                course = self.get_course_for_item(item.location)
                existing_tabs = course.tabs or []
                existing_tabs.append({
                    'type': 'static_tab',
                    'name': item.display_name,
                    'url_slug': item.location.name
                })
                course.tabs = existing_tabs
                self.update_metadata(course.location, course._model_data._kvs._metadata)

            return item
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateItemError(location)

    def get_course_for_item(self, location, depth=0):
        '''
        VS[compat]
        cdodge: for a given Xmodule, return the course that it belongs to
        NOTE: This makes a lot of assumptions about the format of the course location
        Also we have to assert that this module maps to only one course item - it'll throw an
        assert if not
        This is only used to support static_tabs as we need to be course module aware
        '''

        # @hack! We need to find the course location however, we don't
        # know the 'name' parameter in this context, so we have
        # to assume there's only one item in this query even though we are not specifying a name
        course_search_location = ['i4x', location.org, location.course, 'course', None]
        courses = self.get_items(course_search_location, depth=depth)

        # make sure we found exactly one match on this above course search
        found_cnt = len(courses)
        if found_cnt == 0:
            raise Exception('Could not find course at {0}'.format(course_search_location))

        if found_cnt > 1:
            raise Exception('Found more than one course at {0}. There should only be one!!! Dump = {1}'.format(course_search_location, courses))

        return courses[0]

    def _update_single_item(self, location, update):
        """
        Set update on the specified item, and raises ItemNotFoundError
        if the location doesn't exist
        """

        # See http://www.mongodb.org/display/DOCS/Updating for
        # atomic update syntax
        result = self.collection.update(
            {'_id': Location(location).dict()},
            {'$set': update},
            multi=False,
            upsert=True,
        )
        if result['n'] == 0:
            raise ItemNotFoundError(location)

    def update_item(self, location, data):
        """
        Set the data in the item specified by the location to
        data

        location: Something that can be passed to Location
        data: A nested dictionary of problem data
        """

        self._update_single_item(location, {'definition.data': data})

    def update_children(self, location, children):
        """
        Set the children for the item specified by the location to
        children

        location: Something that can be passed to Location
        children: A list of child item identifiers
        """

        self._update_single_item(location, {'definition.children': children})

    def update_metadata(self, location, metadata):
        """
        Set the metadata for the item specified by the location to
        metadata

        location: Something that can be passed to Location
        metadata: A nested dictionary of module metadata
        """
        # VS[compat] cdodge: This is a hack because static_tabs also have references from the course module, so
        # if we add one then we need to also add it to the policy information (i.e. metadata)
        # we should remove this once we can break this reference from the course to static tabs
        loc = Location(location)
        if loc.category == 'static_tab':
            course = self.get_course_for_item(loc)
            existing_tabs = course.tabs or []
            for tab in existing_tabs:
                if tab.get('url_slug') == loc.name:
                    tab['name'] = metadata.get('display_name')
                    break
            course.tabs = existing_tabs
            self.update_metadata(course.location, own_metadata(course))

        self._update_single_item(location, {'metadata': metadata})


    def delete_item(self, location):
        """
        Delete an item from this modulestore

        location: Something that can be passed to Location
        """
        # VS[compat] cdodge: This is a hack because static_tabs also have references from the course module, so
        # if we add one then we need to also add it to the policy information (i.e. metadata)
        # we should remove this once we can break this reference from the course to static tabs
        if location.category == 'static_tab':
            item = self.get_item(location)
            course = self.get_course_for_item(item.location)
            existing_tabs = course.tabs or []
            course.tabs = [tab for tab in existing_tabs if tab.get('url_slug') != location.name]
            self.update_metadata(course.location, own_metadata(course))

        self.collection.remove({'_id': Location(location).dict()})


    def get_parent_locations(self, location, course_id):
        '''Find all locations that are the parents of this location in this
        course.  Needed for path_to_location().
        '''
        location = Location.ensure_fully_specified(location)
        items = self.collection.find({'definition.children': location.url()},
                                    {'_id': True})
        return [i['_id'] for i in items]

    def get_errored_courses(self):
        """
        This function doesn't make sense for the mongo modulestore, as courses
        are loaded on demand, rather than up front
        """
        return {}


# DraftModuleStore is first, because it needs to intercept calls to MongoModuleStore
class DraftMongoModuleStore(DraftModuleStore, MongoModuleStore):
    pass
