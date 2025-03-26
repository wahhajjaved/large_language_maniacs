#STANDARD LIB
from datetime import datetime
from decimal import Decimal
from itertools import chain

import warnings

#LIBRARIES
from django.apps import apps
from django.conf import settings
from django.db.backends.utils import format_number
from django.db import IntegrityError
from django.db.models.query import QuerySet
from django.utils import timezone
from google.appengine.api import datastore
from google.appengine.api.datastore import Key, Query
try:
    from django.db.models.expressions import BaseExpression
except ImportError:
    from django.db.models.expressions import ExpressionNode as BaseExpression

#DJANGAE
from djangae.utils import memoized
from djangae.db.backends.appengine.indexing import special_indexes_for_column, REQUIRES_SPECIAL_INDEXES
from djangae.db.backends.appengine.dbapi import CouldBeSupportedError
from djangae.db.backends.appengine import POLYMODEL_CLASS_ATTRIBUTE


def make_timezone_naive(value):
    if value is None:
        return None

    if timezone.is_aware(value):
        if settings.USE_TZ:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            raise ValueError("Djangae backend does not support timezone-aware datetimes when USE_TZ is False.")
    return value


@memoized
def get_model_from_db_table(db_table):
    # We use include_swapped=True because tests might need access to gauth User models which are
    # swapped if the user has a different custom user model

    kwargs = {
        "include_auto_created": True,
        "include_swapped": True
    }

    for model in apps.get_models(**kwargs):
        if model._meta.db_table == db_table:
            return model


def decimal_to_string(value, max_digits=16, decimal_places=0):
    """
    Converts decimal to a unicode string for storage / lookup by nonrel
    databases that don't support decimals natively.

    This is an extension to `django.db.backends.utils.format_number`
    that preserves order -- if one decimal is less than another, their
    string representations should compare the same (as strings).

    TODO: Can't this be done using string.format()?
          Not in Python 2.5, str.format is backported to 2.6 only.
    """

    # Handle sign separately.
    if value.is_signed():
        sign = u'-'
        value = abs(value)
    else:
        sign = u''

    # Let Django quantize and cast to a string.
    value = format_number(value, max_digits, decimal_places)

    # Pad with zeroes to a constant width.
    n = value.find('.')
    if n < 0:
        n = len(value)
    if n < max_digits - decimal_places:
        value = u'0' * (max_digits - decimal_places - n) + value
    return sign + value


def normalise_field_value(value):
    """ Converts a field value to a common type/format to make comparable to another. """
    if isinstance(value, datetime):
        return make_timezone_naive(value)
    elif isinstance(value, Decimal):
        return decimal_to_string(value)
    return value


def get_datastore_kind(model):
    return get_top_concrete_parent(model)._meta.db_table


def get_prepared_db_value(connection, instance, field, raw=False):
    value = getattr(instance, field.attname) if raw else field.pre_save(instance, instance._state.adding)

    if isinstance(value, BaseExpression):
        from djangae.db.backends.appengine.expressions import evaluate_expression

        # We can't actually support F expressions on the datastore, but we can simulate
        # them, evaluating the expression in place.

        #TODO: For saves and updates we should raise a Warning. When evaluated in a filter
        # we should raise an Error
        value = evaluate_expression(value, instance, connection)

    if hasattr(value, "prepare_database_save"):
        value = value.prepare_database_save(field)
    else:
        value = field.get_db_prep_save(
            value,
            connection=connection
        )

    value = connection.ops.value_for_db(value, field)

    return value


def get_concrete_parents(model, ignore_leaf=False):
    ret = [x for x in model.mro() if hasattr(x, "_meta") and not x._meta.abstract and not x._meta.proxy]
    if ignore_leaf:
        ret = [ x for x in ret if x != model ]
    return ret

@memoized
def get_top_concrete_parent(model):
    return get_concrete_parents(model)[-1]

def get_concrete_fields(model, ignore_leaf=False):
    """
        Returns all the concrete fields for the model, including those
        from parent models
    """
    concrete_classes = get_concrete_parents(model, ignore_leaf)
    fields = []
    for klass in concrete_classes:
        fields.extend(klass._meta.fields)

    return fields

@memoized
def get_concrete_db_tables(model):
    return [ x._meta.db_table for x in get_concrete_parents(model) ]

@memoized
def has_concrete_parents(model):
    return get_concrete_parents(model) != [model]

@memoized
def get_field_from_column(model, column):
    for field in model._meta.fields:
        if field.column == column:
            return field
    return None

def django_instance_to_entity(connection, model, fields, raw, instance, check_null=True):
    # uses_inheritance = False
    inheritance_root = get_top_concrete_parent(model)
    db_table = get_datastore_kind(inheritance_root)

    def value_from_instance(_instance, _field):
        value = get_prepared_db_value(connection, _instance, _field, raw)

        # If value is None, but there is a default, and the field is not nullable then we should populate it
        # Otherwise thing get hairy when you add new fields to models
        if value is None and _field.has_default() and not _field.null:
            value = connection.ops.value_for_db(_field.get_default(), _field)

        if check_null and (not _field.null and not _field.primary_key) and value is None:
            raise IntegrityError("You can't set %s (a non-nullable "
                                     "field) to None!" % _field.name)

        is_primary_key = False
        if _field.primary_key and _field.model == inheritance_root:
            is_primary_key = True

        return value, is_primary_key


    field_values = {}
    primary_key = None

    for field in fields:
        value, is_primary_key = value_from_instance(instance, field)
        if is_primary_key:
            primary_key = value
        else:
            field_values[field.column] = value

        # Add special indexed fields
        for index in special_indexes_for_column(model, field.column):
            indexer = REQUIRES_SPECIAL_INDEXES[index.split('__')[0]] # Indexes can be named regex__aaa, hence splitting by __
            values = indexer.prep_value_for_database(value, index)

            if values is None:
                continue

            if not hasattr(values, "__iter__"):
                values = [ values ]

            for v in values:
                column = indexer.indexed_column_name(field.column, v, index)
                if column in field_values:
                    if not isinstance(field_values[column], list):
                        field_values[column] = [ field_values[column], v ]
                    else:
                        field_values[column].append(v)
                else:
                    field_values[column] = v

    kwargs = {}
    if primary_key:
        if isinstance(primary_key, (int, long)):
            kwargs["id"] = primary_key
        elif isinstance(primary_key, basestring):
            if len(primary_key) > 500:
                warnings.warn("Truncating primary key that is over 500 characters. "
                              "THIS IS AN ERROR IN YOUR PROGRAM.",
                              RuntimeWarning)
                primary_key = primary_key[:500]

            kwargs["name"] = primary_key
        else:
            raise ValueError("Invalid primary key value")

    namespace = connection.settings_dict.get("NAMESPACE")
    entity = datastore.Entity(db_table, namespace=namespace, **kwargs)
    entity.update(field_values)

    classes = get_concrete_db_tables(model)
    if len(classes) > 1:
        entity[POLYMODEL_CLASS_ATTRIBUTE] = list(set(classes))

    return entity


def get_datastore_key(model, pk, namespace):
    """ Return a datastore.Key for the given model and primary key.
    """

    kind = get_top_concrete_parent(model)._meta.db_table
    return Key.from_path(kind, pk, namespace=namespace)


class MockInstance(object):
    """
        This creates a mock instance for use when passing a datastore entity
        into get_prepared_db_value. This is used when performing updates to prevent a complete
        conversion to a Django instance before writing back the entity
    """

    def __init__(self, **kwargs):
        is_adding = kwargs.pop('_is_adding', False)
        self._original = kwargs.pop('_original', None)
        self._meta = kwargs.pop('_meta', None)

        class State:
            adding = is_adding

        self.fields = {}
        for field_name, value in kwargs.items():
            self.fields[field_name] = value

        self._state = State()

    def __getattr__(self, attr):
        if attr in self.fields:
            return self.fields[attr]
        raise AttributeError(attr)


def key_exists(key):
    qry = Query(keys_only=True, namespace=key.namespace())
    qry.Ancestor(key)
    return qry.Count(limit=1) > 0


# Null-friendly comparison functions

def lt(x, y):
    if x is None and y is not None:
        return True
    elif x is not None and y is None:
        return False
    else:
        return x < y


def gt(x, y):
    if x is None and y is not None:
        return False
    elif x is not None and y is None:
        return True
    else:
        return x > y


def gte(x, y):
    return not lt(x, y)


def lte(x, y):
    return not gt(x, y)


def django_ordering_comparison(ordering, lhs, rhs):
    if not ordering:
        return -1  # Really doesn't matter

    ASCENDING = 1
    DESCENDING = 2

    for order, direction in ordering:
        if lhs is not None:
            lhs_value = lhs.key() if order == "__key__" else lhs.get(order)
        else:
            lhs_value = None

        if rhs is not None:
            rhs_value = rhs.key() if order == "__key__" else rhs.get(order)
        else:
            rhs_value = None

        if direction == ASCENDING and lhs_value != rhs_value:
            return -1 if lt(lhs_value, rhs_value) else 1
        elif direction == DESCENDING and lhs_value != rhs_value:
            return 1 if lt(lhs_value, rhs_value) else -1

    return 0


def entity_matches_query(entity, query):
    """
        Return True if the entity would potentially be returned by the datastore
        query
    """
    OPERATORS = {
        "=": lambda x, y: x == y,
        "<": lt,
        ">": gt,
        "<=": lte,
        ">=": gte
    }

    queries = [query]
    if isinstance(query, datastore.MultiQuery):
        raise CouldBeSupportedError("We just need to separate the multiquery "
                                    "into 'queries' then everything should work")

    for query in queries:
        comparisons = chain(
            [("_Query__kind", "=", "_Query__kind") ],
            [tuple(x.split(" ") + [ x ]) for x in query.keys()]
        )

        for ent_attr, op, query_attr in comparisons:
            if ent_attr == "__key__":
                continue

            op = OPERATORS[op]  # We want this to throw if there's some op we don't know about

            if ent_attr == "_Query__kind":
                ent_attr = entity.kind()
            else:
                ent_attr = entity.get(ent_attr)

            if callable(ent_attr):
                # entity.kind() is a callable, so we need this to save special casing it in a more
                # ugly way
                ent_attr = ent_attr()

            if not isinstance(query_attr, (list, tuple)):
                query_attrs = [query_attr]
            else:
                # The query value can be a list of ANDed values
                query_attrs = query_attr

            query_attrs = (
                getattr(query, x) if x == "_Query__kind" else query.get(x)
                for x in query_attrs
            )

            if not isinstance(ent_attr, (list, tuple)):
                ent_attr = [ ent_attr ]

            matches = False
            for query_attr in query_attrs:  # [22, 23]
                #If any of the values don't match then this query doesn't match
                if not any(op(attr, query_attr) for attr in ent_attr):
                    matches = False
                    break
            else:
                # One of the ent_attrs matches the query_attrs
                matches = True

            if not matches:
                # One of the AND values didn't match
                break
        else:
            # If we got through the loop without breaking, then the entity matches
            return True

    return False


def ensure_datetime(value):
    """
        Painfully, sometimes the Datastore returns dates as datetime objects, and sometimes
        it returns them as unix timestamps in microseconds!!
    """
    if isinstance(value, long):
        return datetime.fromtimestamp(value / 1e6)
    return value
