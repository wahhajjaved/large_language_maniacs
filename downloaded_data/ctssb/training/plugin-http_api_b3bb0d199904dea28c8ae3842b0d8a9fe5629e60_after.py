"""PytSite HTTP API Functions
"""
from typing import Union as _Union, Mapping as _Mapping, Type as _Type
from pytsite import router as _router, http as _http, routing as _routing, logger as _logger, events as _events

__author__ = 'Alexander Shepetko'
__email__ = 'a@shepetko.com'
__license__ = 'MIT'

_rules_map = _routing.RulesMap()


def handle(method: str, path: str, controller: _Union[str, _Type], name: str = None, version: int = 0,
           defaults: dict = None):
    """Register API request handler
    """
    if isinstance(controller, str):
        controller = _rules_map.get(controller)

    _rules_map.add(_routing.Rule(controller, path, name, defaults, method, {'version': version}))


def match(method: str, path: str, version: int) -> _routing.Rule:
    try:
        for rule in _rules_map.match(path, method):
            if rule.attrs['version'] in (0, version):
                return rule

        raise _http.error.NotFound()

    except _routing.error.RuleNotFound as e:
        _logger.error(e)
        raise _http.error.NotFound()


def endpoint(name: str, args: _Mapping = None) -> str:
    """Get HTTP API rule's endpoint
    """
    return _rules_map.path(name, args).lstrip('/')


def url(name: str, args: _Mapping = None, version: int = 1) -> str:
    """Get an URL for an HTTP API endpoint
    """
    return _router.rule_url('pytsite.http_api@entry', {
        'http_api_version': version,
        'http_api_endpoint': _rules_map.path(name, args)
    })


def call(name: str, args: _Mapping = None):
    """Call a controller
    """
    controller = _rules_map.get(name).controller_class()  # type: _routing.Controller
    controller.args.update(args)

    return controller.exec()


def on_pre_request(handler, priority: int = 0):
    """Register handler which will be called before handling every request to HTTP API.
    """
    _events.listen('http_api@pre_request', handler, priority)


def on_request(handler, priority: int = 0):
    """Register handler which will be called on every request to HTTP API.
    """
    _events.listen('http_api@request', handler, priority)
