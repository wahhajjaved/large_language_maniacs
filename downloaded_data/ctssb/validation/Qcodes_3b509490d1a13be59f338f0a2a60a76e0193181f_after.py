import pytest
import warnings

from qcodes.utils.deprecate import (
    deprecate, issue_deprecation_warning, QCoDeSDeprecationWarning,
    _catch_deprecation_warnings,
    assert_not_deprecated, assert_deprecated)


def test_issue_deprecation_warning():
    with assert_deprecated(
            'The use of this function is deprecated, because '
            'of this being a test. Use \"a real function\" as an alternative.'):
        issue_deprecation_warning(
            'use of this function',
            'of this being a test',
            'a real function'
        )

@pytest.mark.filterwarnings('ignore:The function "add_one" is deprecated,')
def test_similar_output():

    def _add_one(x):
        return 1 + x

    @deprecate(reason='this function is for private use only')
    def add_one(x):
        return _add_one(x)
    with assert_deprecated(
            'The function <add_one> is deprecated, because '
            'this function is for private use only.'):
        assert add_one(1) == _add_one(1)


def test_deprecated_context_manager():
    with _catch_deprecation_warnings() as ws:
        issue_deprecation_warning('something')
        issue_deprecation_warning('something more')
        warnings.warn('Some other warning')
    assert len(ws) == 2
    with warnings.catch_warnings(record=True) as ws:
        issue_deprecation_warning('something')
        warnings.warn('Some other warning')
    assert len(ws) == 2


@deprecate(reason='this is a test')
class C:
    def __init__(self, attr: str):
        self.a = attr

    def method(self) -> None:
        self.a = 'last called by method'

    @staticmethod
    def static_method(a: int) -> int:
        return a + 1

    @property
    def prop(self) -> str:
        return self.a

    @prop.setter
    def prop(self, val: str) -> None:
        self.a = val + '_prop'


class TestClassDeprecation:
    def test_init(self):
        with assert_deprecated(
                'The class <C> is deprecated, because '
                'this is a test.'):
            c = C('pristine')
        assert c.a == 'pristine'

    def test_method(self):
        with warnings.catch_warnings():
            c = C('pristine')

        with assert_deprecated(
                'The function <method> is deprecated, because '
                'this is a test.'):
            c.method()
        assert c.a == 'last called by method'

    @pytest.mark.skip(reason="This is not implemented yet.")
    def test_property(self):
        with warnings.catch_warnings():
            c = C('pristine')

        with assert_deprecated(
                'The function <method> is deprecated, because '
                'this is a test.'):
            assert c.prop == 'pristine'

    @pytest.mark.skip(reason="This is not implemented yet.")
    def test_setter(self):
        with warnings.catch_warnings():
            c = C('pristine')

        with assert_deprecated(
                'The function <method> is deprecated, because '
                'this is a test.'):
            c.prop = 'changed'
        assert c.a == 'changed_prop'

    def test_static_method(self):
        with assert_deprecated(
                'The function <static_method> is deprecated, because '
                'this is a test.'):
            assert C.static_method(1) == 2