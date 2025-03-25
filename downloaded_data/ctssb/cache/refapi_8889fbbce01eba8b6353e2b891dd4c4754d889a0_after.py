import json

import pytest

import basil_refapi.storage as db
import support
from tests import *


@pytest.fixture(scope="module")
def session():
    return support.session_maker()()


def test_get_by_id(session):
    r = db.Type.get(session, 34)
    assert_that(r, has_property('name', equal_to('Tritanium')))


def test_get_by_invalid_id(session):
    r = db.Type.get(session, -4)
    assert_that(r, none())


def test_find_unique(session):
    matches = db.Type.find(session, 'Tritani')
    assert_that(matches, instance_of(list))
    assert_that(matches, has_length(1))
    assert_that(matches[0], has_property('name', equal_to('Tritanium')))


def test_find_none(session):
    matches = db.Type.find(session, 'Gandalf')
    assert_that(matches, instance_of(list))
    assert_that(matches, empty())


def test_find_many(session):
    matches = db.Type.find(session, 'Prototype')
    assert_that(matches, instance_of(list))
    assert_that(matches, has_length(27))


def test_dict():
    name = unicode('a\xac\u1234\u20ac\U00008000', 'utf-8', 'ignore')
    instance = db.Type(id=12345, group_id=4545, name=name, volume=1.2,
                       capacity=0, base_price=12500000, market_group_id=3232,
                       portion_size=1, published=False)
    returned = instance.dict()
    assert_that(returned, has_entries({'id': 12345, 'name': name,
                                       'volume': 1.2, 'capacity': 0,
                                       'portion_size': 1}))


def test_json():
    name = unicode('a\xac\u1234\u20ac\U00008000', 'utf-8', 'ignore')
    type = db.Type(id=12345, group_id=4545, name=name, volume=1.2, capacity=0,
                   base_price=12500000, market_group_id=3232, portion_size=1,
                   published=False)
    returned = type.json()

    # no error by reloading from json string
    json.loads(returned)
