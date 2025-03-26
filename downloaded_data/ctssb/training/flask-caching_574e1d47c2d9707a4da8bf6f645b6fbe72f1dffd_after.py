# -*- coding: utf-8 -*-
import sys
import random
import time
import pytest
from flask_caching import Cache, function_namespace


def test_memoize(app, cache):
    with app.test_request_context():
        @cache.memoize(5)
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result = big_foo(5, 2)

        time.sleep(1)

        assert big_foo(5, 2) == result

        result2 = big_foo(5, 3)
        assert result2 != result

        time.sleep(5)

        assert big_foo(5, 2) != result

        time.sleep(1)

        assert big_foo(5, 3) != result2


def test_memoize_timeout(app):
    app.config['CACHE_DEFAULT_TIMEOUT'] = 1
    cache = Cache(app)

    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result = big_foo(5, 2)
        assert big_foo(5, 2) == result
        time.sleep(2)
        assert big_foo(5, 2) != result


def test_memoize_annotated(app, cache):
    if sys.version_info >= (3, 0):
        with app.test_request_context():
            @cache.memoize(50)
            def big_foo_annotated(a, b):
                return a + b + random.randrange(0, 100000)
            big_foo_annotated.__annotations__ = {'a': int, 'b': int, 'return': int}

            result = big_foo_annotated(5, 2)

            time.sleep(2)

            assert big_foo_annotated(5, 2) == result


def test_memoize_utf8_arguments(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b):
            return "{}-{}".format(a, b)

        big_foo("æøå", "chars")


def test_memoize_unicode_arguments(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b):
            return u"{}-{}".format(a, b)

        big_foo(u"æøå", "chars")


def test_memoize_delete(app, cache):
    with app.test_request_context():
        @cache.memoize(5)
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result = big_foo(5, 2)
        result2 = big_foo(5, 3)

        time.sleep(1)

        assert big_foo(5, 2) == result
        assert big_foo(5, 2) == result
        assert big_foo(5, 3) != result
        assert big_foo(5, 3) == result2

        cache.delete_memoized(big_foo)

        assert big_foo(5, 2) != result
        assert big_foo(5, 3) != result2


def test_memoize_no_timeout_delete(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result_a = big_foo(5, 1)
        result_b = big_foo(5, 2)

        assert big_foo(5, 1) == result_a
        assert big_foo(5, 2) == result_b
        cache.delete_memoized(big_foo, 5, 2)

        assert big_foo(5, 1) == result_a
        assert big_foo(5, 2) != result_b

        # Cleanup bigfoo 5,1 5,2 or it might conflict with
        # following run if it also uses memecache
        cache.delete_memoized(big_foo, 5, 2)
        cache.delete_memoized(big_foo, 5, 1)


def test_memoize_verhash_delete(app, cache):
    with app.test_request_context():
        @cache.memoize(5)
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result = big_foo(5, 2)
        result2 = big_foo(5, 3)

        time.sleep(1)

        assert big_foo(5, 2) == result
        assert big_foo(5, 2) == result
        assert big_foo(5, 3) != result
        assert big_foo(5, 3) == result2

        cache.delete_memoized_verhash(big_foo)

        _fname, _fname_instance = function_namespace(big_foo)
        version_key = cache._memvname(_fname)
        assert cache.get(version_key) is None

        assert big_foo(5, 2) != result
        assert big_foo(5, 3) != result2

        assert cache.get(version_key) is not None


def test_memoize_annotated_delete(app, cache):
    with app.test_request_context():
        @cache.memoize(5)
        def big_foo_annotated(a, b):
            return a + b + random.randrange(0, 100000)

        big_foo_annotated.__annotations__ = {'a': int, 'b': int, 'return': int}

        result = big_foo_annotated(5, 2)
        result2 = big_foo_annotated(5, 3)

        time.sleep(1)

        assert big_foo_annotated(5, 2) == result
        assert big_foo_annotated(5, 2) == result
        assert big_foo_annotated(5, 3) != result
        assert big_foo_annotated(5, 3) == result2

        cache.delete_memoized_verhash(big_foo_annotated)

        _fname, _fname_instance = function_namespace(big_foo_annotated)
        version_key = cache._memvname(_fname)
        assert cache.get(version_key) is None

        assert big_foo_annotated(5, 2) != result
        assert big_foo_annotated(5, 3) != result2

        assert cache.get(version_key) is not None


def test_memoize_args(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b):
            return sum(a) + sum(b) + random.randrange(0, 100000)

        result_a = big_foo([5, 3, 2], [1])
        result_b = big_foo([3, 3], [3, 1])

        assert big_foo([5, 3, 2], [1]) == result_a
        assert big_foo([3, 3], [3, 1]) == result_b

        cache.delete_memoized(big_foo, [5, 3, 2], [1])

        assert big_foo([5, 3, 2], [1]) != result_a
        assert big_foo([3, 3], [3, 1]) == result_b

        # Cleanup bigfoo 5,1 5,2 or it might conflict with
        # following run if it also uses memecache
        cache.delete_memoized(big_foo, [5, 3, 2], [1])
        cache.delete_memoized(big_foo, [3, 3], [1])


def test_memoize_kwargs(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b=None):
            return a + sum(b.values()) + random.randrange(0, 100000)

        result_a = big_foo(1, dict(one=1, two=2))
        result_b = big_foo(5, dict(three=3, four=4))

        assert big_foo(1, dict(one=1, two=2)) == result_a
        assert big_foo(5, dict(three=3, four=4)) == result_b

        cache.delete_memoized(big_foo, 1, dict(one=1, two=2))

        assert big_foo(1, dict(one=1, two=2)) != result_a
        assert big_foo(5, dict(three=3, four=4)) == result_b


def test_memoize_kwargonly(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a=None):
            if a is None:
                a = 0
            return a + random.random()

        result_a = big_foo()
        result_b = big_foo(5)

        assert big_foo() == result_a
        assert big_foo() < 1
        assert big_foo(5) == result_b
        assert big_foo(5) >= 5 and big_foo(5) < 6


def test_memoize_arg_kwarg(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def f(a, b, c=1):
            return a + b + c + random.randrange(0, 100000)

        assert f(1, 2) == f(1, 2, c=1)
        assert f(1, 2) == f(1, 2, 1)
        assert f(1, 2) == f(1, 2)
        assert f(1, 2, 3) != f(1, 2)

        with pytest.raises(TypeError):
            f(1)


def test_memoize_arg_kwarg_var_keyword(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def f(a, b, c=1, **kwargs):
            return a + b + c + random.randrange(0, 100000) + sum(list(kwargs.values()))

        assert f(1, 2) == f(1, 2, c=1)
        assert f(1, 2) == f(1, 2, 1)
        assert f(1, 2) == f(1, 2)
        assert f(1, 2, d=5, e=8) == f(1, 2, e=8, d=5)
        assert f(1, b=2, c=3, d=5, e=8) == f(1, 2, e=8, d=5, b=2, c=3)
        assert f(1, 2, 3) != f(1, 2)
        assert f(1, 2, 3) != f(1, 2)

        with pytest.raises(TypeError):
            f(1)


def test_memoize_classarg(app, cache):
    @cache.memoize()
    def bar(a):
        return a.value + random.random()

    class Adder(object):
        def __init__(self, value):
            self.value = value

    adder = Adder(15)
    adder2 = Adder(20)

    y = bar(adder)
    z = bar(adder2)

    assert y != z
    assert bar(adder) == y
    assert bar(adder) != z
    adder.value = 14
    assert bar(adder) == y
    assert bar(adder) != z

    assert bar(adder) != bar(adder2)
    assert bar(adder2) == z


def test_memoize_classfunc(app, cache):
    class Adder(object):
        def __init__(self, initial):
            self.initial = initial

        @cache.memoize()
        def add(self, b):
            return self.initial + b

    adder1 = Adder(1)
    adder2 = Adder(2)

    x = adder1.add(3)
    assert adder1.add(3) == x
    assert adder1.add(4) != x
    assert adder1.add(3) != adder2.add(3)


def test_memoize_classfunc_delete(app, cache):
    with app.test_request_context():
        class Adder(object):
            def __init__(self, initial):
                self.initial = initial

            @cache.memoize()
            def add(self, b):
                return self.initial + b + random.random()

        adder1 = Adder(1)
        adder2 = Adder(2)

        a1 = adder1.add(3)
        a2 = adder2.add(3)

        assert a1 != a2
        assert adder1.add(3) == a1
        assert adder2.add(3) == a2

        cache.delete_memoized(adder1.add)

        a3 = adder1.add(3)
        a4 = adder2.add(3)

        assert not a1 == a3
        # self.assertNotEqual(a1, a3)

        assert a1 != a3

        assert a2 == a4
        # self.assertEqual(a2, a4)

        cache.delete_memoized(Adder.add)

        a5 = adder1.add(3)
        a6 = adder2.add(3)

        assert not a5 == a6
        #self.assertNotEqual(a5, a6)
        assert not a3 == a5
        #self.assertNotEqual(a3, a5)
        assert not a4 == a6
        #self.assertNotEqual(a4, a6)


def test_memoize_classmethod_delete(app, cache):
    with app.test_request_context():
        class Mock(object):
            @classmethod
            @cache.memoize(5)
            def big_foo(cls, a, b):
                return a + b + random.randrange(0, 100000)

        result = Mock.big_foo(5, 2)
        result2 = Mock.big_foo(5, 3)

        time.sleep(1)

        assert Mock.big_foo(5, 2) == result
        assert Mock.big_foo(5, 2) == result
        assert Mock.big_foo(5, 3) != result
        assert Mock.big_foo(5, 3) == result2

        cache.delete_memoized(Mock.big_foo)

        assert Mock.big_foo(5, 2) != result
        assert Mock.big_foo(5, 3) != result2


def test_memoize_forced_update(app, cache):
    with app.test_request_context():
        forced_update = False

        @cache.memoize(5, forced_update=lambda: forced_update)
        def big_foo(a, b):
            return a + b + random.randrange(0, 100000)

        result = big_foo(5, 2)
        time.sleep(1)
        assert big_foo(5, 2) == result

        forced_update = True
        new_result = big_foo(5, 2)
        assert new_result != result

        forced_update = False
        time.sleep(1)
        assert big_foo(5, 2) == new_result


def test_memoize_multiple_arg_kwarg_calls(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b, c=[1, 1], d=[1, 1]):
            return sum(a) + sum(b) + sum(c) + sum(d) + random.randrange(0, 100000)  # noqa

        result_a = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])

        assert big_foo([5, 3, 2], [1], d=[3, 3], c=[3, 3]) == result_a
        assert big_foo(b=[1], a=[5, 3, 2], c=[3, 3], d=[3, 3]) == result_a
        assert big_foo([5, 3, 2], [1], [3, 3], [3, 3]) == result_a


def test_memoize_multiple_arg_kwarg_delete(app, cache):
    with app.test_request_context():
        @cache.memoize()
        def big_foo(a, b, c=[1, 1], d=[1, 1]):
            return sum(a) + sum(b) + sum(c) + sum(d) + random.randrange(0, 100000)  # noqa

        result_a = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        cache.delete_memoized(big_foo, [5, 3, 2], [1], [3, 3], [3, 3])
        result_b = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b

        cache.delete_memoized(big_foo, [5, 3, 2], b=[1], c=[3, 3], d=[3, 3])
        result_b = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b

        cache.delete_memoized(big_foo, [5, 3, 2], [1], c=[3, 3], d=[3, 3])
        result_a = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b

        cache.delete_memoized(big_foo, [5, 3, 2], b=[1], c=[3, 3], d=[3, 3])
        result_a = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b

        cache.delete_memoized(big_foo, [5, 3, 2], [1], c=[3, 3], d=[3, 3])
        result_b = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b

        cache.delete_memoized(big_foo, [5, 3, 2], [1], [3, 3], [3, 3])
        result_a = big_foo([5, 3, 2], [1], c=[3, 3], d=[3, 3])
        assert result_a != result_b


def test_memoize_kwargs_to_args(app, cache):
    with app.test_request_context():
        def big_foo(a, b, c=None, d=None):
            return sum(a) + sum(b) + random.randrange(0, 100000)

        expected = (1, 2, 'foo', 'bar')

        args, kwargs = cache._memoize_kwargs_to_args(big_foo, 1, 2, 'foo', 'bar')
        assert (args == expected)
        args, kwargs = cache._memoize_kwargs_to_args(big_foo, 2, 'foo', 'bar', a=1)
        assert (args == expected)
        args, kwargs = cache._memoize_kwargs_to_args(big_foo, a=1, b=2, c='foo', d='bar')
        assert (args == expected)
        args, kwargs = cache._memoize_kwargs_to_args(big_foo, d='bar', b=2, a=1, c='foo')
        assert (args == expected)
        args, kwargs = cache._memoize_kwargs_to_args(big_foo, 1, 2, d='bar', c='foo')
        assert (args == expected)
