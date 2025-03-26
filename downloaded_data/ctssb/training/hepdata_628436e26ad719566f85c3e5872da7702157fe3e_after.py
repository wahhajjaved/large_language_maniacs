#
# This file is part of HEPData.
# Copyright (C) 2015 CERN.
#
# HEPData is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# HEPData is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HEPData; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""HEPData end to end testing of accounts."""
from urllib2 import urlopen

import flask
from invenio_accounts import testutils
from conftest import e2e_assert, e2e_assert_url


def test_user_registration_and_login(live_server, env_browser):
    """E2E user registration and login test."""
    browser = env_browser
    # 1. Go to user registration page
    browser.get(flask.url_for('security.register', _external=True))
    e2e_assert_url(browser, 'security.register')

    # 2. Input user data
    signup_form = browser.find_element_by_name('register_user_form')
    input_email = signup_form.find_element_by_name('email')
    input_password = signup_form.find_element_by_name('password')
    # input w/ name "email"
    # input w/ name "password"
    user_email = 'eamonnmag@gmail.com'
    user_password = '12345_SIx'
    input_email.send_keys(user_email)
    input_password.send_keys(user_password)

    # 3. submit form
    signup_form.submit()
    # ...and get redirected to the "home page" ('/')
    e2e_assert_url(browser, 'hepdata_theme.index')

    # 3.5: After registering we should be logged in.
    e2e_assert(browser, testutils.webdriver_authenticated(browser),
               'Should be authenticated')
    browser.get(flask.url_for('security.change_password', _external=True))
    e2e_assert_url(browser, 'security.change_password')

    # 3.5: logout.
    browser.get(flask.url_for('security.logout', _external=True))
    e2e_assert(browser, not testutils.webdriver_authenticated(browser),
               'Should not be authenticated')

    # 4. go to login-form
    browser.get(flask.url_for('security.login', _external=True))
    e2e_assert_url(browser, 'security.login')

    login_form = browser.find_element_by_name('login_user_form')
    # 5. input registered info
    login_form.find_element_by_name('email').send_keys(user_email)
    login_form.find_element_by_name('password').send_keys(user_password)
    # 6. Submit!
    # check if authenticated at `flask.url_for('security.change_password')`
    login_form.submit()

    e2e_assert(browser, testutils.webdriver_authenticated(browser))
