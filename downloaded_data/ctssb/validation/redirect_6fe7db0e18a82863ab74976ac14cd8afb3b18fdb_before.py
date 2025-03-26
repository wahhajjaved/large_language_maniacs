from os.path import dirname
from subprocess import check_output

import json
import pytest
import requests
from syncloudlib.integration.hosts import add_host_alias_by_ip

import db
import smtp

DIR = dirname(__file__)


@pytest.fixture(scope="session")
def module_setup(request, log_dir, artifact_dir):
    def module_teardown():
        check_output('cp /var/log/apache2/error.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_rest-error.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_rest-access.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_ssl_rest-error.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_ssl_rest-access.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_ssl_web-access.log {0}'.format(log_dir), shell=True)
        check_output('cp /var/log/apache2/redirect_ssl_web-error.log {0}'.format(log_dir), shell=True)
        check_output('ls -la /var/log/apache2 > {0}/var.log.apache2.ls.log'.format(log_dir), shell=True)
        check_output('ls -la /var/log > {0}/var.log.ls.log'.format(log_dir), shell=True)

        check_output('chmod -R a+r {0}'.format(artifact_dir), shell=True)
        db.recreate()

    request.addfinalizer(module_teardown)


def test_start(module_setup, domain):
    add_host_alias_by_ip('app', 'www', '127.0.0.1', domain)
    add_host_alias_by_ip('app', 'api', '127.0.0.1', domain)


def test_index(domain):
    response = requests.get('https://www.{0}'.format(domain), allow_redirects=False, verify=False)
    assert response.status_code == 200, response.text


def test_user_create_special_symbols_in_password(domain):
    email = 'symbols_in_password@mail.com'
    response = requests.post('https://www.{0}/api/user/create'.format(domain),
                             data={'email': email, 'password': r'pass12& ^%"'},
                             verify=False)
    assert response.status_code == 200
    assert len(smtp.emails()) == 1
    smtp.clear()


def create_user(domain, email, password):
    response = requests.post('https://www.{0}/api/user/create'.format(domain),
                             data={'email': email, 'password': password}, verify=False)
    assert response.status_code == 200, response.text
    assert len(smtp.emails()) == 1
    activate_token = smtp.get_token(smtp.emails()[0])
    response = requests.get('https://api.{0}/user/activate?token={1}'.format(domain, activate_token),
                 verify=False)
    assert response.status_code == 200, response.text
    smtp.clear()
    response = requests.get('https://api.{0}/user/get?email={1}&password={2}'.format(domain, email, password),
                            verify=False)
    assert response.status_code == 200, response.text


def acquire_domain(domain, email, password, user_domain):
    acquire_data = {
        'user_domain': user_domain,
        'email': email,
        'password': password,
        'device_mac_address': '00:00:00:00:00:00',
        'device_name': 'some-device',
        'device_title': 'Some Device',
    }
    response = requests.post('https://api.{0}/domain/acquire'.format(domain),
                             data=acquire_data,
                             verify=False)
    domain_data = json.loads(response.text)
    update_token = domain_data['update_token']
    return update_token


def test_user_create_success(domain):
    create_user(domain, 'test@syncloud.test', 'pass123456')


def test_get_user_data(domain):
    email = 'test_get_user_data@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    user_domain = "test_get_user_data"
    update_token = acquire_domain(domain, email, password, user_domain)

    update_data = {
        'token': update_token,
        'ip': '127.0.0.1',
        'web_protocol': 'http',
        'web_local_port': 80,
        'web_port': 10000
    }
    requests.post('https://api.{0}/domain/update'.format(domain),
                  json=update_data,
                  verify=False)

    response = requests.get('https://api.{0}/user/get'.format(domain),
                            params={'email': email, 'password': password},
                            verify=False)

    response_data = json.loads(response.text)
    user_data = response_data['data']

    # This is hack. We do not know last_update value - it is set by server.
    last_update = user_data["domains"][0]["last_update"]
    update_token = user_data["update_token"]

    expected = {
        'active': True,
        'email': email,
        'unsubscribed': False,
        'update_token': update_token,
        'domains': [{
            'user_domain': user_domain,
            'web_local_port': 80,
            'web_port': 10000,
            'web_protocol': 'http',
            'ip': '127.0.0.1',
            'ipv6': None,
            'dkim_key': None,
            'local_ip': None,
            'map_local_address': False,
            'platform_version': None,
            'device_mac_address': '00:00:00:00:00:00',
            'device_name': 'some-device',
            'device_title': 'Some Device',
            'last_update': last_update
        }]
    }

    assert expected == user_data


def test_user_delete(domain):
    email = 'test_user_delete@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    update_token_1 = acquire_domain(domain, email, password, "user_domain_1")
    update_token_2 = acquire_domain(domain, email, password, "user_domain_2")

    response = requests.post('https://api.{0}/user/delete'.format(domain),
                             data={'email': email, 'password': password}, verify=False)
    assert response.status_code == 200

    response = requests.get('https://api.{0}/domain/get'.format(domain),
                            params={'token': update_token_1}, verify=False)
    assert response.status_code == 400

    response = requests.get('https://api.{0}/domain/get'.format(domain),
                            params={'token': update_token_2},
                            verify=False)
    assert response.status_code == 400


def test_user_reset_password_sent_mail(domain):
    email = 'test_user_reset_password_sent_mail@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    response = requests.post('https://www.{0}/api/user/reset_password'.format(domain),
                             data={'email': email}, verify=False)
    assert response.status_code == 200

    assert len(smtp.emails()) > 0, 'Server should send email with link to reset password'
    token = smtp.get_token(smtp.emails()[0])
    smtp.clear()
    assert token is not None


def test_user_reset_password_set_new(domain):
    email = 'test_user_reset_password_set_new@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    requests.post('https://www.{0}/api/user/reset_password'.format(domain), data={'email': email},
                  verify=False)
    token = smtp.get_token(smtp.emails()[0])

    smtp.clear()

    new_password = 'new_password'
    response = requests.post('https://www.{0}/api/user/set_password'.format(domain),
                             data={'token': token, 'password': new_password},
                             verify=False)
    assert response.status_code == 200, response.text

    assert len(smtp.emails()) == 0, 'Server should send email when setting new password'

    response = requests.get('https://api.{0}/user/get'.format(domain),
                            params={'email': email, 'password': new_password},
                            verify=False)
    assert response.status_code == 200, response.text


def test_user_reset_password_set_with_old_token(domain):
    email = 'test_user_reset_password_set_with_old_token@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    requests.post('https://www.{0}/api/user/reset_password'.format(domain), data={'email': email},
                  verify=False)
    token_old = smtp.get_token(smtp.emails()[0])

    smtp.clear()

    requests.post('https://www.{0}/api/user/reset_password'.format(domain), data={'email': email},
                  verify=False)
    token = smtp.get_token(smtp.emails()[0])
    smtp.clear()

    new_password = 'new_password'
    response = requests.post('https://www.{0}/api/user/set_password'.format(domain),
                             data={'token': token_old, 'password': new_password},
                             verify=False)
    assert response.status_code == 400, response.text


def test_user_reset_password_set_twice(domain):
    email = 'test_user_reset_password_set_twice@syncloud.test'
    password = 'pass123456'
    create_user(domain, email, password)

    requests.post('https://www.{0}/api/user/reset_password'.format(domain), data={'email': email},
                  verify=False)
    token = smtp.get_token(smtp.emails()[0])
    smtp.clear()

    new_password = 'new_password'
    response = requests.post('https://www.{0}/api/user/set_password'.format(domain),
                             data={'token': token, 'password': new_password},
                             verify=False)
    assert response.status_code == 200, response.text

    new_password = 'new_password2'
    response = requests.post('https://www.{0}/api/user/set_password'.format(domain),
                             data={'token': token, 'password': new_password},
                             verify=False)
    assert response.status_code == 400, response.text
