#! /usr/bin/python3.7


'''
    Tests should cover:
        * Proper application logic
        * Information is being properly processed and validated
        * Minimal side effects and seperation of concerns are preserved
'''

from saltbot.saltbot import SaltBot
import pytest
import time


def test_get_home(silent_requests, site_cookies):
    bot = SaltBot(dbname='testing')
    bot.get('https://www.saltybet.com')
    assert bot.session.cookies == site_cookies


def test_get_state(silent_requests):
    bot = SaltBot(dbname='testing')
    resp = bot.get(
        'https://www.saltybet.com/state.json',
        params={'t': int(time.time())})
    assert isinstance(resp.json(), dict)


def test_get_zdata(silent_requests):
    bot = SaltBot(dbname='testing')
    resp = bot.get(
        'https://www.saltybet.com/zdata.json',
        params={'t': int(time.time())})
    assert isinstance(resp.json(), dict)


def test_get_bad_state(silent_requests):
    with pytest.raises(Exception):
        bot = SaltBot(dbname='testing')
        bot.get('https://www.saltybet.com/state.json')


def test_get_bad_zdata(silent_requests):
    with pytest.raises(Exception):
        bot = SaltBot(dbname='testing')
        bot.get('https://www.saltybet.com/zdata.json')
