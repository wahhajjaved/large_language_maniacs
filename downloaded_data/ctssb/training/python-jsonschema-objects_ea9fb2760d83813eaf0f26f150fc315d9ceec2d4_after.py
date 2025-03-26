import six
from python_jsonschema_objects import util


class ValidationError(Exception):
    pass

class ValidatorRegistry(object):

    def __init__(self):
       self.registry = {}

    def register(self, name=None):
       def f(functor):
          self.registry[name if name is not None else functor.__name__] = functor
          return functor
       return f

    def __call__(self, name):
       return self.registry.get(name)


registry = ValidatorRegistry()

@registry.register()
def multipleOf(param, value, _):
    quot, rem = divmod(value, param)
    if rem != 0:
        raise ValidationError(
            "{0} was not a multiple of {1}".format(value,
                                                   param))

@registry.register()
def enum(param, value, _):
    if value not in param:
        raise ValidationError(
            "{0} was not one of {1}".format(value, param))


@registry.register()
def minimum(param, value, type_data):
    exclusive = type_data.get('exclusiveMinimum')
    if exclusive:
        if value < param:
            raise ValidationError(
                "{0} was less than {1}".format(value, param))
    elif value <= param:
            raise ValidationError(
                "{0} was less or equal to than {1}".format(value, param))


@registry.register()
def maximum(param, value, type_data):
    exclusive = type_data.get('exclusiveMaximum')
    if exclusive:
        if value < param:
            raise ValidationError(
                "{0} was more than {1}".format(value, param))
    elif value <= param:
        raise ValidationError(
            "{0} was more than or equal to {1}".format(value, param))


@registry.register()
def maxLength(param, value, _):
    if len(value) > param:
        raise ValidationError(
            "{0} was longer than {1} characters".format(value, param))


@registry.register()
def minLength(param, value, _):
    if len(value) < param:
        raise ValidationError(
            "{0} was fewer than {1} characters".format(value, param))


@registry.register()
def pattern(param, value, _):
    import re
    match = re.search(param, value)
    if not match:
        raise ValidationError(
            "{0} did not match {1}".format(value, param)
        )


type_registry = ValidatorRegistry()

@type_registry.register(name='boolean')
def check_boolean_type(param, value, _):
    if not isinstance(value, bool):
        raise ValidationError(
            "{0} is not a boolean".format(value))

@type_registry.register(name='integer')
def check_integer_type(param, value, _):
    if not isinstance(value, int):
        raise ValidationError(
            "{0} is not an integer".format(value))

@type_registry.register(name='number')
def check_number_type(param, value, _):
    if not isinstance(value, (float, int)):
        raise ValidationError(
            "{0} is neither an integer or a float".format(value))

@type_registry.register(name='null')
def check_null_type(param, value, _):
    if value is not None:
        raise ValidationError(
            "{0} is not None".format(value))

@type_registry.register(name='string')
def check_string_type(param, value, _):
    if not isinstance(value, six.string_types):
        raise ValidationError(
            "{0} is not a string".format(value))

@type_registry.register(name='array')
def check_array_type(param, value, _):
    if not isinstance(value, list):
        raise ValidationError(
            "{0} is not an array".format(value))

@type_registry.register(name='object')
def check_object_type(param, value, _):
    from python_jsonschema_objects.classbuilder import ProtocolBase
    if not isinstance(value, (dict, ProtocolBase)):
        raise ValidationError(
            "{0} is not an object (neither dict nor ProtocolBase)".format(value))

@registry.register(name='type')
def check_type(param, value, type_data):
    type_check = type_registry(param)
    if type_check is None:
        raise ValidationError(
            "{0} is an invalid type".format(value))
    type_check(param, value, type_data)


class ArrayValidator(object):

    def __init__(self, ary):
        self.data = ary

    def validate(self):
        converted = self.validate_items()
        self.validate_length()
        self.validate_uniqueness()
        return converted

    def validate_uniqueness(self):
        from python_jsonschema_objects import classbuilder

        if getattr(self, 'uniqueItems', None) is not None:
            testset = set(self.data)
            if len(testset) != len(self.data):
                raise ValidationError(
                    "{0} had duplicate elements, but uniqueness required"
                    .format(self.data))

    def validate_length(self):
        from python_jsonschema_objects import classbuilder

        if getattr(self, 'minItems', None) is not None:
            if len(self.data) < self.minItems:
                raise ValidationError(
                    "{1} has too few elements. Wanted {0}."
                    .format(self.minItems, self.data))

        if getattr(self, 'maxItems', None) is not None:
            if len(self.data) > self.maxItems:
                raise ValidationError(
                    "{1} has too few elements. Wanted {0}."
                    .format(self.maxItems, self.data))

    def validate_items(self):
        from python_jsonschema_objects import classbuilder

        if self.__itemtype__ is None:
            return

        type_checks = self.__itemtype__
        if not isinstance(type_checks, (tuple, list)):
            # we were given items = {'type': 'blah'} ; thus ensure the type for all data.
            type_checks = [type_checks] * len(self.data)
        elif len(type_checks) > len(self.data):
            raise ValidationError(
                "{1} does not have sufficient elements to validate against {0}"
                .format(self.__itemtype__, self.data))

        typed_elems = []
        for elem, typ in zip(self.data, type_checks):
            if isinstance(typ, dict):
                for param, paramval in six.iteritems(typ):
                    validator = registry(param)
                    if validator is not None:
                        validator(paramval, elem, typ)

            elif util.safe_issubclass(typ, classbuilder.LiteralValue):
                val = typ(elem)
                val.validate()
                typed_elems.append(val)
            elif util.safe_issubclass(typ, classbuilder.ProtocolBase):
                if not isinstance(elem, typ):
                    try:
                      val = typ(**util.coerce_for_expansion(elem))
                    except TypeError as e:
                      raise ValidationError("'{0}' was not a valid value for '{1}'".format(elem, typ))
                else:
                    val = elem
                val.validate()
                typed_elems.append(val)
            elif util.safe_issubclass(typ, ArrayValidator):
                val = typ(elem)
                val.validate()
                typed_elems.append(val)

        return typed_elems

    @staticmethod
    def create(name, item_constraint=None, **addl_constraints):
        """ Create an array validator based on the passed in constraints.

        If item_constraint is a tuple, it is assumed that tuple validation
        is being performed. If it is a class or dictionary, list validation
        will be performed. Classes are assumed to be subclasses of ProtocolBase,
        while dictionaries are expected to be basic types ('string', 'number', ...).

        addl_constraints is expected to be key-value pairs of any of the other
        constraints permitted by JSON Schema v4.
        """
        from python_jsonschema_objects import classbuilder
        props = {}

        if item_constraint is not None:
            if isinstance(item_constraint, (tuple, list)):
                for i, elem in enumerate(item_constraint):
                    isdict = isinstance(elem, (dict,))
                    isklass = isinstance( elem, type) and util.safe_issubclass(
                        elem, (classbuilder.ProtocolBase, classbuilder.LiteralValue))

                    if not any([isdict, isklass]):
                        raise TypeError(
                            "Item constraint (position {0}) was not a schema".format(i))
            else:
                isdict = isinstance(item_constraint, (dict,))
                isklass = isinstance( item_constraint, type) and util.safe_issubclass(
                    item_constraint, (classbuilder.ProtocolBase, classbuilder.LiteralValue))

                if not any([isdict, isklass]):
                    raise TypeError("Item constraint was not a schema")

                if isdict and item_constraint['type'] == 'array':
                    item_constraint = ArrayValidator.create(name + "#sub",
                                                            item_constraint=item_constraint[
                                                                'items'],
                                                            addl_constraints=item_constraint)

        props['__itemtype__'] = item_constraint

        props.update(addl_constraints)

        validator = type(str(name), (ArrayValidator,), props)

        return validator

