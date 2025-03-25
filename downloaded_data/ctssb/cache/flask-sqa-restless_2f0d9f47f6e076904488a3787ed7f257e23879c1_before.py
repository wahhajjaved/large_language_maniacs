# -*- coding: utf-8 -*-

"""
Heavily Influenced by and Adopted from Django Tastypie.
https://github.com/django-tastypie/django-tastypie/blob/master/tastypie/resources.py
"""

from __future__ import absolute_import, division, print_function

import copy
import sys
import traceback
from collections import OrderedDict

import six
from flask import make_response, request
from restless.constants import *
from restless.fl import FlaskResource as BaseFlaskResource
from restless.utils import format_traceback
from six import wraps
from sqlalchemy import orm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from . import util, djquery
from .authentication import Authentication
from .djquery import DjangoQuery
from .exceptions import *
from .paginator import SQLAlchemyPaginator
from .util import get_model_relationship_names


ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']


def db_http_wrapper(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IntegrityError as ex:
            db_error = get_database_error(ex)
            db_error.raise_http_error()

        except HttpErrorConvertible as ex:
            ex.raise_http_error()

    return wrapper


def with_session(func):
    @wraps(func)
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            if hasattr(func, 'im_self'):
                resource = func.im_self
            elif len(args) >= 1 and isinstance(args[0], FlaskSQAResource):
                resource = args[0]
            else:
                raise

            session = resource.session
            if session and not session.is_active:
                session.rollback()

            raise

    return _wrapper


def db_http_wrapper_with_session(func):
    return db_http_wrapper(with_session(func))


class FlaskResource(BaseFlaskResource):
    authentication = Authentication()

    list_allowed = ALLOWED_METHODS

    detail_allowed = ALLOWED_METHODS

    CUSTOM_APIS = []

    MAX_LIMIT = 100

    response_headers = {
        'default': {}
    }

    detail_uri_identifier = 'id'

    status_map = {
        'list': OK,
        'detail': OK,
        'create': CREATED,
        'update': ACCEPTED,
        'patch': ACCEPTED,
        'delete': NO_CONTENT,
        'update_list': ACCEPTED,
        'create_detail': CREATED,
        'delete_list': NO_CONTENT,
        'patch_list': ACCEPTED,
    }
    http_methods = {
        'list': {
            'GET': 'list',
            'POST': 'create',
            'PUT': 'update_list',
            'DELETE': 'delete_list',
            'PATCH': 'patch_list',
        },
        'detail': {
            'GET': 'detail',
            'POST': 'create_detail',
            'PUT': 'update',
            'DELETE': 'delete',
            'PATCH': 'patch'
        }
    }

    def __init__(self, *args, **kwargs):
        self.custom_api = kwargs.pop('custom_api', None)
        BaseFlaskResource.__init__(self, *args, **kwargs)

        self.http_methods = copy.deepcopy(self.http_methods)
        self.status_map = copy.deepcopy(self.status_map)
        self.response_headers = copy.deepcopy(self.response_headers)
        if self.custom_api:
            self.add_custom_api()

    @classmethod
    def name(cls):
        return cls.__name__.replace('Resource', '').lower()

    def add_custom_api(self):
        self.http_methods[self.custom_api['name']] = {
            method: self.custom_api['name']
            for method in self.custom_api['methods']
        }

        if self.custom_api.get('status_code'):
            self.status_map[self.custom_api['name']] = \
                self.custom_api['status_code']

    def update_http_methods(self, view, accepted_methods):
        methods = dict(self.http_methods[view])
        for method in methods:
            if method not in accepted_methods:
                del self.http_methods[view][method]

    def request_method(self):
        if 'X-HTTP-Method-Override' in self.request.headers:
            return self.request.headers['X-HTTP-Method-Override']

        return BaseFlaskResource.request_method(self)

    def request_querystring(self):
        return self.request.args.to_dict(flat=False)

    def get_view(self):
        return self.http_methods[self.endpoint][self.request_method()]

    def is_authenticated(self):
        return self.authentication. \
            is_authenticated(method=self.request_method(),
                             view=self.get_view())

    def patch(self, *args, **kwargs):
        raise MethodNotImplemented()

    def patch_list(self, *args, **kwargs):
        raise MethodNotImplemented()


    @classmethod
    def add_url_rules(cls, app, rule_prefix, endpoint_prefix=None):
        cls._add_url_rules(app, rule_prefix, endpoint_prefix)

    @classmethod
    def _add_url_rules(cls, app, rule_prefix, endpoint_prefix=None):
        if cls.list_allowed:
            app.add_url_rule(
                rule_prefix,
                endpoint=cls.build_endpoint_name('list', endpoint_prefix),
                view_func=cls.as_list(),
                methods=cls.list_allowed
            )

        if cls.detail_allowed:
            app.add_url_rule(
                rule_prefix + '<%s>/' % cls.detail_uri_identifier,
                endpoint=cls.build_endpoint_name('detail', endpoint_prefix),
                view_func=cls.as_detail(),
                methods=cls.detail_allowed
            )

        api_list = cls.get_custom_apis()

        for custom_api in api_list:
            app.add_url_rule(
                '%s%s' % (rule_prefix, custom_api['url']),
                endpoint=cls.build_endpoint_name(custom_api['name'],
                                                 endpoint_prefix),
                view_func=cls.as_view(custom_api['name'],
                                      custom_api=custom_api),
                methods=custom_api['methods']
            )

    @classmethod
    def get_custom_apis(cls):
        return list(cls.CUSTOM_APIS)

    @classmethod
    def as_view(cls, view_type, *init_args, **init_kwargs):
        def _wrapper(*args, **kwargs):
            # Make a new instance so that no state potentially leaks between
            # instances.
            inst = cls(*init_args, **init_kwargs)
            inst.request = request

            if 'custom_api' in init_kwargs:
                accepted_methods = init_kwargs['custom_api']['methods']
            else:
                accepted_methods = inst.list_allowed if view_type == 'list' \
                    else inst.detail_allowed

            inst.update_http_methods(view_type, accepted_methods)

            return inst.handle(view_type, *args, **kwargs)

        return _wrapper


class FlaskSQAResource(FlaskResource):
    QUERY_CLASS = djquery.DjangoQuery

    authentication = Authentication()

    paginator_cls = SQLAlchemyPaginator

    serializer_cls = None

    serializer = None

    allow_bulk_insert = False

    include_fields = []

    exclude_fields = []

    include_fields_deserialize = []

    exclude_fields_deserialize = []

    ordering_allowed = []

    filtering = {}

    custom_filtering = {}

    NESTED_API = []

    model = None

    session = None

    response_headers = {
        'default': {}
    }

    def __init__(self, *args, **kwargs):
        self._initialize_serializer()
        self.nested = kwargs.pop('nested', False)
        self.parent = kwargs.pop('parent', None)
        FlaskResource.__init__(self, *args, **kwargs)
        self._init_query()

    def _initialize_serializer(self):
        self.serializer = self.serializer_cls(session=self.session)
        if self.include_fields:
            self.serializer.include_fields_serialize(self.include_fields)
        elif self.exclude_fields:
            self.serializer.exclude_fields_serialize(self.exclude_fields)

        if self.include_fields_deserialize:
            self.serializer.include_fields_deserialize(self.include_fields_deserialize)
        elif self.exclude_fields_deserialize:
            self.serializer.exclude_fields_deserialize(self.exclude_fields_deserialize)

    def _init_query(self):
        mapper = orm.class_mapper(self.model)
        if mapper:
            self.query = self.QUERY_CLASS(mapper, session=self.session())
        else:
            self.query = None

    @property
    def fields(self):
        return util.get_mapper_cls_fields(self.model)

    def build_response(self, data, status=200):
        response = make_response(data, status, {
            'Content-Type': getattr(self.serializer, 'content_type',
                                    'application/json')
        })

        view_name = self.get_view()

        resp_headers = self.response_headers.get(view_name,
                                                 self.response_headers.get(
                                                     'default', {}))

        for key, value in resp_headers.items():
            response.headers[key] = value

        return response

    def wrap_list_response(self, objects):
        return {
            'meta': self.paginator.get_meta() if self.paginator_cls else {},
            'objects': self.serializer.serialize_model(objects)
        }

    def serialize_detail(self, data):
        if not data:
            return ''
        data = self.serializer.serialize_model(data)
        return FlaskResource.serialize_detail(self, data)

    def serialize(self, method, endpoint, data):
        qs = self.request_querystring()

        self.include_fields = qs.get('include_fields', self.include_fields)
        self.exclude_fields = qs.get('exclude_fields', self.exclude_fields)
        if self.include_fields:
            self.serializer.include_fields_serialize(self.include_fields)
        elif self.exclude_fields:
            self.serializer.exclude_fields_serialize(self.exclude_fields)

        if endpoint == 'list' or isinstance(data, list):
            # Create is a special-case, because you POST it to the collection,
            # not to a detail.
            if method == 'POST':
                return self.serialize_detail(data)

            return self.serialize_list(data)

        return self.serialize_detail(data)

    def bubble_exceptions(self):
        return False

    def build_error(self, error):
        debug = self.is_debug()
        tb = format_traceback(sys.exc_info()) if debug else None

        if isinstance(error, IntegrityError):
            db_error = get_database_error(error)
            err = db_error.get_http_error()
        elif isinstance(error, HttpErrorConvertible):
            err = error.get_http_error()
        else:
            err = error

        data = {
            'error': getattr(err, 'description', six.text_type(err)),
            'payload': getattr(err, 'payload', {})
        }

        if tb:
            data['traceback'] = tb

        body = self.serializer.serialize(data)

        status = getattr(err, 'code', 500)

        self.log_error(error, status, data)

        return self.build_response(body, status=status)

    def log_error(self, error, status, data):
        pass

    @classmethod
    def add_url_rules(cls, app, rule_prefix, endpoint_prefix=None):
        cls._add_url_rules(app, rule_prefix, endpoint_prefix=endpoint_prefix)
        for nested_api in cls.NESTED_API:
            cls.add_nested_url_rules(nested_api, app, rule_prefix,
                                     endpoint_prefix)

    @classmethod
    def get_custom_apis(cls):
        api_list = list(cls.CUSTOM_APIS)

        api_list.append({
            'url': 'count/',
            'name': 'count',
            'methods': ['GET']
        })

        if cls.allow_bulk_insert:
            api_list.append({
                'url': 'bulk_insert/',
                'name': 'bulk_insert',
                'methods': ['POST']
            })

        return api_list

    @classmethod
    def add_nested_url_rules(cls, nested_api, app, rule_prefix,
                             endpoint_prefix=None):

        resource = nested_api['resource']
        if isinstance(resource, six.string_types):
            resource = util.import_class(resource)

        nested_prefix = "%s<%s>/%s/" % (rule_prefix, nested_api['identifier'],
                                        nested_api['prefix'])
        if nested_api['list']:
            api_name = "%s_list" % resource.name()
            app.add_url_rule(
                nested_prefix,
                endpoint=cls.build_endpoint_name(api_name,
                                                 endpoint_prefix),
                view_func=cls.nested_view(resource, 'list',
                                          nested_api['list'],
                                          nested_api['identifier']),
                methods=nested_api['list']
            )

        if nested_api['detail']:
            api_name = "%s_detail" % resource.name()
            app.add_url_rule(
                '%s<%s>/' % (nested_prefix, resource.detail_uri_identifier),
                endpoint=cls.build_endpoint_name(api_name,
                                                 endpoint_prefix),
                view_func=cls.nested_view(resource, 'detail',
                                          nested_api['detail'],
                                          nested_api['identifier']),
                methods=nested_api['detail']
            )

        custom_apis = nested_api['custom_apis']
        custom_apis.append({
            'url': 'count/',
            'name': 'count',
            'methods': ['GET']
        })

        if nested_api['allow_bulk_insert']:
            custom_apis.append({
                'url': 'bulk_insert/',
                'name': 'bulk_insert',
                'methods': ['POST']
            })

        for custom_api in custom_apis:
            api_name = "%s_%s" % (resource.name(), custom_api['name'])
            app.add_url_rule(
                '%s%s' % (nested_prefix, custom_api['url']),
                endpoint=cls.build_endpoint_name(api_name,
                                                 endpoint_prefix),
                view_func=cls.nested_view(resource, custom_api['name'],
                                          custom_api['methods'],
                                          nested_api['identifier'],
                                          custom_api=custom_api),
                methods=custom_api['methods']
            )

    @classmethod
    def nested_view(cls, nested_resource, view, accepted_methods,
                    parent_identifier, *init_args, **init_kwargs):

        def _wrapper(*args, **kwargs):
            # Make a new instance so that no state potentially leaks between
            # instances.

            init_kwargs['parent'] = cls.model.query.get_or_404(**{
                cls.detail_uri_identifier: kwargs[parent_identifier]
            })
            init_kwargs['nested'] = True
            inst = nested_resource(*init_args, **init_kwargs)
            inst.update_http_methods(view, accepted_methods)
            inst.request = request
            return inst.handle(view, *args, **kwargs)

        return _wrapper

    def handle(self, endpoint, *args, **kwargs):
        """
        A convenient dispatching method, this centralized some of the common
        flow of the views.

        This wraps/calls the methods the user defines (``list/detail/create``
        etc.), allowing the user to ignore the
        authentication/deserialization/serialization/response & just focus on
        their data/interactions.

        :param endpoint: The style of URI call (typically either ``list`` or
            ``detail``).
        :type endpoint: string

        :param args: (Optional) Any positional URI parameter data is passed
            along here. Somewhat framework/URL-specific.

        :param kwargs: (Optional) Any keyword/named URI parameter data is
            passed along here. Somewhat framework/URL-specific.

        :returns: A response object
        """
        self.endpoint = endpoint
        method = self.request_method()

        try:
            # Use ``.get()`` so we can also dodge potentially incorrect
            # ``endpoint`` errors as well.
            if not method in self.http_methods.get(endpoint, {}):
                raise MethodNotAllowed(
                    "Unsupported method '{0}' for {1} endpoint.".format(
                        method,
                        endpoint
                    )
                )

            if not self.is_authenticated():
                raise UnAuthorized()

            self.data = self.deserialize(method, endpoint, self.request_body())
            self.check_authorization(self.http_methods[endpoint][method],
                                     self.data, *args, **kwargs)

            if self.paginator_cls:
                self.paginator = self.paginator_cls(self.request_querystring(),
                                                    resource_uri=self.request.base_url,
                                                    max_limit=self.MAX_LIMIT)

            view = self.get_view()
            view_method = getattr(self, view)
            data = view_method(*args, **kwargs)
            serialized = self.serialize(method, endpoint, data)
        except Exception as err:
            return self.handle_error(err)

        status = self.status_map.get(self.http_methods[endpoint][method], 200)
        return self.build_response(serialized, status=status)

    def check_authorization(self, view_method, data, *args, **kwargs):
        return True

    @db_http_wrapper_with_session
    def create(self, *args, **kwargs):
        return self.obj_create(self.data)

    @db_http_wrapper_with_session
    def list(self, *args, **kwargs):
        return self.obj_get_list(**kwargs)

    @db_http_wrapper_with_session
    def count(self, *args, **kwargs):
        count = self.obj_get_list(count_only=True, **kwargs)
        return {'total_count': count}

    @db_http_wrapper_with_session
    def detail(self, *args, **kwargs):
        return self.obj_get(**kwargs)

    @db_http_wrapper_with_session
    def update(self, *args, **kwargs):
        return self.obj_update(self.data, partial=False, **kwargs)

    @db_http_wrapper_with_session
    def patch(self, *args, **kwargs):
        return self.obj_update(self.data, partial=True, **kwargs)

    @db_http_wrapper_with_session
    def delete(self, *args, **kwargs):
        self.obj_delete(**kwargs)

    @db_http_wrapper_with_session
    def create_or_update(self, *args, **kwargs):
        return self.obj_create_or_update(self.data, **kwargs)

    def bulk_insert(self, *args, **kwargs):
        return self._bulk_save('Insert', self.data)

    ############################ Helper Methods ################################
    def obj_create_or_update(self, data, **filters):
        query = self.query.filter_by(**filters)
        entity = getattr(self.model, self.detail_uri_identifier)

        try:
            obj_entity = query.with_entities(entity).one()[0]
            kwargs = {self.detail_uri_identifier: obj_entity}
            return self.obj_update(data, **kwargs)
        except NoResultFound:
            return self.obj_create(data)

    def obj_create(self, data, commit=True):
        obj = self.load_model(data)
        self.session.add(obj)
        if commit:
            self.session.commit()
        return obj

    def obj_get(self, **filters):
        return self.query.get_or_404(**filters)

    def obj_get_list(self, count_only=False, **kwargs):
        query = self.query
        query = self.apply_filtering(query, **kwargs)
        query = self.apply_sorting(query)
        if count_only:
            return query.count()
        query = self.apply_pagination(query)
        return query.all()

    def obj_update(self, data, commit=True, partial=False, **filters):
        existing_obj = self.obj_get(**filters)
        self.load_model(data, partial=partial)
        for key, value in data.iteritems():
            setattr(existing_obj, key, value)

        if commit:
            self.session.commit()

        return existing_obj

    def obj_delete(self, commit=True, **filters):
        obj = self.obj_get(**filters)
        self.session.delete(obj)
        if commit:
            self.session.commit()

    def load_model(self, data, partial=False):
        return self.serializer.deserialize_model(data, partial=partial)

    def _record_exists(self, data):
        return data.get('id', None) is not None

    def _bulk_save(self, op_name, object_list):
        obj_create = db_http_wrapper_with_session(self.obj_create)
        multi_update = db_http_wrapper_with_session(self.obj_update_list)

        success = OrderedDict()
        errors = OrderedDict()
        for ind, data in enumerate(object_list):
            try:
                if self._record_exists(data):
                    object_id = data['id']
                    multi_update({'id': object_id}, data)
                else:
                    obj = obj_create(data)
                    object_id = obj.id

                success[ind] = object_id
            except ValidationError as ex:
                errors[ind] = {
                    'status': 'failure',
                    'type': 'ValidationError',
                    'error': ex.message
                }

            except HTTPConflict as ex:
                errors[ind] = {
                    'status': 'failure',
                    'type': 'Conflict',
                    'error': ex.message
                }

            except DatabaseError as ex:
                errors[ind] = {
                    'status': 'failure',
                    'type': 'DatabaseError',
                    'error': ex.message
                }

        print("Total: {}, Error Count {}, Success Count {}".format(
            len(object_list), len(errors), len(success)))

        return {
            'success': success,
            'errors': errors
        }

    def obj_update_list(self, filter_dict, data):
        self.load_model(data, partial=True)
        self.query.filter_by(**filter_dict).update(data)
        self.session.commit()

    def check_filtering(self, field, filter_type):
        """
        Given a field name, a optional filter type and an optional list of
        additional relations, determine if a field can be filtered on.
        If a filter does not meet the needed conditions, it should raise an
        ``InvalidFilterError``.
        If the filter meets the conditions, a list of attribute names (not
        field names) will be returned.
        """
        field = field.replace('__', '.')

        if self.filtering.get(field, None) == '*':
            return True

        elif not field in self.filtering:
            raise InvalidFilterError("The '%s' field does not allow filtering."
                                     % field)

        elif filter_type not in self.filtering.get(field):
            raise InvalidFilterError(
                "'%s' is not an allowed filter on the '%s' field." %
                (filter_type, field))

        return True

    def apply_pagination(self, query):
        if not self.paginator_cls:
            return query

        return self.paginator.page(query)

    def apply_sorting(self, query):
        options = self.request_querystring()

        if 'order_by' not in options:
            return query

        for order_by in options['order_by']:
            if order_by.startswith('-'):
                field = order_by[1:]
            else:
                field = order_by

            filter_parts = field.split('__')
            field_name = filter_parts[0]

            model_relationships = get_model_relationship_names(self.model)
            if field_name not in self.serializer.fields and field_name not in model_relationships:
                raise BadRequest("No matching '%s' field for ordering on."
                                 % field_name)

            if field_name not in self.ordering_allowed:
                raise BadRequest("This '%s' field does not allow ordering"
                                 % field_name)

            query = query.order_by(order_by)

        return query

    def apply_filtering(self, query, **kwargs):
        """
        Given a dictionary of filters, create the necessary ORM-level filters.
        Keys should be resource fields, **NOT** model fields.
        Valid values are either a list of Django filter types (i.e.
        ``['startswith', 'exact', 'lte']``), the ``ALL`` constant or the
        ``ALL_WITH_RELATIONS`` constant.
        """
        # At the declarative level:
        #     filtering = {
        #         'resource_field_name': ['exact', 'startswith', 'endswith', 'contains'],
        #         'resource_field_name_2': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
        #         'resource_field_name_3': ALL,
        #         'resource_field_name_4': ALL_WITH_RELATIONS,
        #         ...
        #     }
        # Accepts the filters as a dict. None by default, meaning no filters.

        qs = self.request_querystring()

        filters = dict(kwargs)

        for filter_expr, value in qs.items():
            custom_filtering_handler = self.custom_filtering.get(filter_expr)
            if isinstance(custom_filtering_handler, six.string_types):
                custom_filtering_handler = getattr(self,
                                                   custom_filtering_handler)

            if custom_filtering_handler is not None and callable(
                    custom_filtering_handler):
                query = custom_filtering_handler(query, qs, value)
                continue

            filter_bits = filter_expr.rsplit('__', 1)

            if filter_bits[-1] not in DjangoQuery.OPERATORS:
                filter_type = 'exact'
                complete_field = '__'.join(filter_bits)
            else:
                filter_type = filter_bits[-1]
                complete_field = filter_bits[0]

            field_name = complete_field.split('__')[0]
            model_relationships = get_model_relationship_names(self.model)
            if field_name not in self.fields and field_name not in model_relationships:
                continue

            self.check_filtering(complete_field, filter_type)

            if filter_type  not in ('in', 'notin') and isinstance(value, (list, tuple)):
                value = value[0]

            value = util.convert_value_to_python(value)
            filters[filter_expr] = value

        return query.filter_by(**filters) if filters else query
