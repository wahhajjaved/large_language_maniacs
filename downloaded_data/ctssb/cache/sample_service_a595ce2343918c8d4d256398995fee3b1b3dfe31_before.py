'''
Contains metadata validation callable builder functions for the Sample service.

The builder functions are expected to take a dict of configuration parameters
from which they can configure themselves and return a validation callable.

Validation callables must accept a metadata value for their key, a dict where the keys are
strings and the values are strings, integers, floats, or booleans. A non-None return value
indicates the metadata failed validation.
For errors that are not under control of the user, any other appropriate exception should be
thrown.

If an exception is not thrown, and a falsy value is returned, the validation succeeds.
'''

import os
import ranges
from typing import Dict, Any, Callable, Optional, cast as _cast, Set as _Set
from pint import UnitRegistry as _UnitRegistry
from pint import DimensionalityError as _DimensionalityError
from pint import UndefinedUnitError as _UndefinedUnitError
from pint import DefinitionSyntaxError as _DefinitionSyntaxError
from SampleService.core.core_types import PrimitiveType
from installed_clients.OntologyAPIClient import OntologyAPI

srv_wizard_url = None
if 'KB_DEPLOYMENT_CONFIG' in os.environ:
    with open(os.environ['KB_DEPLOYMENT_CONFIG']) as f:
        for line in f:
            if line.startswith('srv-wiz-url'):
               srv_wizard_url = line.split('=')[1].strip()

def _check_unknown_keys(d, expected):
    if type(d) != dict:
        raise ValueError('d must be a dict')
    d2 = {k for k in d if k not in expected}
    if d2:
        raise ValueError(f'Unexpected configuration parameter: {sorted(d2)[0]}')


def noop(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that allows any value for the metadata key.
    :params d: The configuration parameters for the callable. Unused.
    :returns: a callable that validates metadata maps.
    '''
    _check_unknown_keys(d, [])

    def f(key: str, val: Dict[str, PrimitiveType]) -> Optional[str]:
        return None
    return f  # mypy had trouble detecting the lambda type


def string(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that performs string checking based on the following rules:

    If the 'keys' parameter is specified it must contain a string or a list of strings. The
    provided string(s) are used by the returned callable to query the metadata map.
    If any of the values for the provided keys are not strings, an error is returned. If the
    `max-len` parameter is provided, the value of which must be an integer, the values' lengths
    must be less than 'max-len'. If the 'required' parameter's value is truthy, an error is
    thrown if any of the keys in the 'keys' parameter do not exist in the map, athough the
    values may be None.

    If the 'keys' parameter is not provided, 'max-len' must be provided, in which case all
    the keys and string values in the metadata value map are checked against the max-value.
    Non-string values are ignored.

    :param d: the configuration map for the callable.
    :returns: a callable that validates metadata maps.
    '''
    # no reason to require max-len, could just check all values are strings. YAGNI for now
    _check_unknown_keys(d, {'max-len', 'required', 'keys'})
    if 'max-len' not in d:
        maxlen = None
    else:
        try:
            maxlen = int(d['max-len'])
        except ValueError:
            raise ValueError('max-len must be an integer')
        if maxlen < 1:
            raise ValueError('max-len must be > 0')

    required = d.get('required')
    keys = _get_keys(d)
    if keys:

        def strlen(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k in keys:
                if required and k not in d1:
                    return f'Required key {k} is missing'
                v = d1.get(k)
                if v is not None and type(v) != str:
                    return f'Metadata value at key {k} is not a string'
                if v and maxlen and len(_cast(str, v)) > maxlen:
                    return f'Metadata value at key {k} is longer than max length of {maxlen}'
            return None
    elif maxlen:
        def strlen(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k, v in d1.items():
                if len(k) > _cast(int, maxlen):
                    return f'Metadata contains key longer than max length of {maxlen}'
                if type(v) == str:
                    if len(_cast(str, v)) > _cast(int, maxlen):
                        return f'Metadata value at key {k} is longer than max length of {maxlen}'
            return None
    else:
        raise ValueError('If the keys parameter is not specified, max-len must be specified')
    return strlen


def enum(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that checks that values are one of a set of specified values.

    The 'allowed-values' parameter is required and is a list of the allowed values for the
    metadata values. Any primitive value is allowed. By default, all the metadata values will
    be checked against the allowed values.

    If the keys parameter is provided, it must be either a string or a list of strings. In this
    case, only the specified keys are checked.

    :param d: the configuration map for the callable.
    :returns: a callable that validates metadata maps.
    '''
    _check_unknown_keys(d, {'allowed-values', 'keys'})
    tmpallowed = d.get('allowed-values')
    if not tmpallowed:
        raise ValueError('allowed-values is a required parameter')
    if type(tmpallowed) != list:
        raise ValueError('allowed-values parameter must be a list')
    for i, a in enumerate(tmpallowed):
        if _not_primitive(a):
            raise ValueError(
                f'allowed-values parameter contains a non-primitive type entry at index {i}')
    allowed: _Set[PrimitiveType] = set(tmpallowed)
    keys = _get_keys(d)
    if keys:

        def enumval(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k in keys:
                if d1.get(k) not in allowed:
                    return f'Metadata value at key {k} is not in the allowed list of values'
            return None
    else:

        def enumval(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k, v in d1.items():
                if v not in allowed:
                    return f'Metadata value at key {k} is not in the allowed list of values'
            return None
    return enumval


def _not_primitive(value):
    return (type(value) != str and type(value) != int and
            type(value) != float and type(value) != bool)


def _get_keys(d):
    keys = d.get('keys')
    if keys:
        if type(keys) == str:
            keys = [keys]
        elif type(keys) != list:
            raise ValueError('keys parameter must be a string or list')
        for i, k in enumerate(keys):
            if type(k) != str:
                raise ValueError(f'keys parameter contains a non-string entry at index {i}')
    return keys


_UNIT_REG = _UnitRegistry()
_UNIT_REG.load_definitions(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "unit_definitions.txt"
    )
)


def units(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that checks that values are equivalent to a provided example
    unit. E.g., if the example units are N, lb * ft / s^2 is also accepted.

    The 'key' parameter is a string that denotes which metadata key to check, and the 'units'
    parameter contains the example units as a string. Both are required.

    :param d: the configuration map for the callable.
    :returns: a callable that validates metadata maps.
    '''
    _check_unknown_keys(d, {'key', 'units'})
    k = d.get('key')
    if not k:
        raise ValueError('key is a required parameter')
    if type(k) != str:
        raise ValueError('the key parameter must be a string')
    u = d.get('units')
    if not u:
        raise ValueError('units is a required parameter')
    if type(u) != str:
        raise ValueError('the units parameter must be a string')
    try:
        req_units = _UNIT_REG.parse_expression(u)
        # looks like you just need to catch these two. I wish all the pint errors inherited
        # from a single pint error
        # https://pint.readthedocs.io/en/0.10.1/developers_reference.html#pint-errors
    except _UndefinedUnitError as e:
        raise ValueError(f"unable to parse units '{u}': undefined unit: {e.args[0]}")
    except _DefinitionSyntaxError as e:
        raise ValueError(f"unable to parse units '{u}': syntax error: {e.args[0]}")

    def unitval(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
        unitstr = d1.get(_cast(str, k))
        if not unitstr:
            return f'metadata value key {k} is required'
        if type(unitstr) != str:
            return f'metadata value key {k} must be a string'
        try:
            units = _UNIT_REG.parse_expression(unitstr)
        except _UndefinedUnitError as e:
            return f"unable to parse units '{u}' at key {k}: undefined unit: {e.args[0]}"
        except _DefinitionSyntaxError as e:
            return f"unable to parse units '{u}' at key {k}: syntax error: {e.args[0]}"
        try:
            (1 * units).ito(req_units)
        except _DimensionalityError as e:
            return (f"Units at key {k}, '{unitstr}', are not equivalent to " +
                    f"required units, '{u}': {e}")
        return None
    return unitval


def number(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that checks that values are numerical, and optionally within a
    given range.

    By default, all values within the metadata value map must be integers or floats.
    If the 'type' key in the configuration is set to 'int', only integers are
    allowed.

    The 'lt', 'lte', 'gt', and 'gte' configuration keys - less than, less than or equal,
    greater than, and greater than or equal, respectively - will require that the number be
    bounded by the given values of those keys. They are all optional. Specifying lt and lte or
    gt and gte at the same time is an error.

    If the 'keys' parameter is specified it must contain a string or a list of strings. The
    provided string(s) are used by the returned callable to query the metadata map.
    If any of the values for the provided keys are not a number as specified, an error is
    returned. If the 'required' parameter's value is truthy, an error is
    thrown if any of the keys in the 'keys' parameter do not exist in the map, athough the
    values may be None.

    :param d: the configuration map for the callable.
    :returns: a callable that validates metadata maps.
    '''
    # hold off on complex numbers for now
    _check_unknown_keys(d, {'required', 'keys', 'type', 'lt', 'gt', 'lte', 'gte'})
    required = d.get('required')
    keys = _get_keys(d)
    types = _get_types(d)
    # range checker
    range_ = _get_range(d)

    if keys:
        def strlen(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k in keys:
                if required and k not in d1:
                    return f'Required key {k} is missing'
                v = d1.get(k)
                if v is not None and type(v) not in types:
                    return f'Metadata value at key {k} is not an accepted number type'
                if v is not None and v not in range_:
                    return f'Metadata value at key {k} is not within the range {range_}'
            return None
    else:
        def strlen(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
            for k, v in d1.items():
                # duplicate of above, meh.
                if v is not None and type(v) not in types:
                    return f'Metadata value at key {k} is not an accepted number type'
                if v is not None and v not in range_:
                    return f'Metadata value at key {k} is not within the range {range_}'
            return None
    return strlen


def _get_types(d):
    types = [float, int]
    t = d.get('type')
    if t == 'int':
        types = [int]
    elif t is not None and t != 'float':
        raise ValueError(f"Illegal value for type parameter: {d.get('type')}")
    return types


def _get_range(d):
    gte = _is_num('gte', d.get('gte'))
    gt = _is_num('gt', d.get('gt'))
    lte = _is_num('lte', d.get('lte'))
    lt = _is_num('lt', d.get('lt'))
    # zero is ok here, so check vs. None
    if gte is not None and gt is not None:
        raise ValueError('Cannot specify both gt and gte')
    if lte is not None and lt is not None:
        raise ValueError('Cannot specify both lt and lte')
    rangevals = {}
    if gte is not None:
        rangevals['start'] = gte
        rangevals['include_start'] = True
    if gt is not None:
        rangevals['start'] = gt
        rangevals['include_start'] = False
    if lte is not None:
        rangevals['end'] = lte
        rangevals['include_end'] = True
    if lt is not None:
        rangevals['end'] = lt
        rangevals['include_end'] = False
    return ranges.Range(**rangevals)


def _is_num(name, val):
    if val is not None and type(val) != float and type(val) != int:
        raise ValueError(f'Value for {name} parameter is not a number')
    return val

def ontology_has_ancestor(d: Dict[str, Any]) -> Callable[[str, Dict[str, PrimitiveType]], Optional[str]]:
    '''
    Build a validation callable that checks that value has valid ontology ancestor term provided

    The 'ontology' parameter is required and must be a string. It is the ontology name.

    The 'ancestor_term' parameter is required and must be a string. It is the ancestor name.

    :param d: the configuration map for the callable.
    :returns: a callable that validates metadata maps.
    '''
    _check_unknown_keys(d, {'ontology', 'ancestor_term'})

    ontology = d.get('ontology')
    if not ontology:
        raise ValueError('ontology is a required paramter')
    if type(ontology) != str:
        raise ValueError('ontology must be a string')

    ancestor_term = d.get('ancestor_term')
    if not ancestor_term:
        raise ValueError('ancestor_term is a required paramter')
    if type(ancestor_term) != str:
        raise ValueError('ancestor_term must be a string')

    oac=None
    try:
        oac=OntologyAPI(srv_wizard_url)
        ret=oac.get_terms({"ids": [ancestor_term], "ns": ontology})
        if len(ret["results"]) == 0:
            raise ValueError(f"ancestor_term {ancestor_term} is not found in {ontology}")
    except Exception as err:
        if 'Parameter validation error' in str(err):
            raise ValueError(f'ontology {ontology} doesn\'t exist')
        else:
            raise
            
    def _get_ontology_ancestors(ontology, val):
        ret=oac.get_ancestors({"id": val, "ns": ontology})
        return list(map(lambda x: x["term"]["id"], ret["results"]))
    
    def ontology_has_ancestor_val(key: str, d1: Dict[str, PrimitiveType]) -> Optional[str]:
        for k, v in d1.items():
            if v is None:
                return f'Metadata value at key {k} is None'
            ancestors=_get_ontology_ancestors(ontology, v)
            if ancestor_term not in ancestors:
                return f'Metadata value at key {k} does not have {ontology} ancestor term {ancestor_term}'
        return None
    return ontology_has_ancestor_val

