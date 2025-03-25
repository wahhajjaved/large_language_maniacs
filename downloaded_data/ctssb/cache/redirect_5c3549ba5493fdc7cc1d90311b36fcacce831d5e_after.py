from datetime import datetime

from models import User, Domain, ActionType
from validation import Validator
import servicesexceptions
import util
import requests


def check_validator(validator):
    if validator.has_errors():
        raise servicesexceptions.parameters_error(validator.fields_errors)


class UsersRead:

    def __init__(self, create_storage, domain):
        self.main_domain = domain
        self.create_storage = create_storage

    def get_user(self, email):
        with self.create_storage() as storage:
            return storage.get_user_by_email(email)

    def authenticate(self, request):
        validator = Validator(request)
        email = validator.email()
        password = validator.password()
        check_validator(validator)

        user = self.get_user(email)
        if not user or not user.active or not util.hash(password) == user.password_hash:
            raise servicesexceptions.bad_request('Authentication failed')

        return user


class Users(UsersRead):

    def __init__(self, create_storage, activate_by_email, mail, dns, domain):
        UsersRead.__init__(self, create_storage, domain)
        self.activate_by_email = activate_by_email
        self.mail = mail
        self.dns = dns
        self.main_domain = domain
        self.create_storage = create_storage

    def get_user(self, email):
        with self.create_storage() as storage:
            return storage.get_user_by_email(email)

    def authenticate(self, request):
        validator = Validator(request)
        email = validator.email()
        password = validator.password()
        check_validator(validator)

        user = self.get_user(email)
        if not user or not user.active or not util.hash(password) == user.password_hash:
            raise servicesexceptions.bad_request('Authentication failed')

        return user

    def create_new_user(self, request):
        validator = Validator(request)
        email = validator.email()
        password = validator.new_password()
        check_validator(validator)

        user = None
        action = None
        with self.create_storage() as storage:
            by_email = storage.get_user_by_email(email)
            if by_email and by_email.email == email:
                raise servicesexceptions.parameter_error('email', 'Email is already registered')

            user = User(email, util.hash(password), not self.activate_by_email)

            if self.activate_by_email:
                action = user.enable_action(ActionType.ACTIVATE)

            storage.add(user)

        if self.activate_by_email:
            self.mail.send_activate(self.main_domain, user.email, action.token)

        return user

    def activate(self, request):
        validator = Validator(request)
        token = validator.token()
        check_validator(validator)

        with self.create_storage() as storage:
            user = storage.get_user_by_activate_token(token)
            if not user:
                raise servicesexceptions.bad_request('Invalid activation token')

            if user.active:
                raise servicesexceptions.bad_request('User is active already')

            user.active = True

        return True

    def drop_device(self, request):
        user = self.authenticate(request)
        validator = Validator(request)
        user_domain = validator.new_user_domain()
        check_validator(validator)

        with self.create_storage() as storage:
            domain = storage.get_domain_by_name(user_domain)

            if not domain or not domain.user.active:
                raise servicesexceptions.bad_request('Unknown domain')

            domain.update_token = None
            domain.device_mac_address = None
            domain.device_name = None
            domain.device_title = None
            domain.ip = None
            domain.local_ip = None

            self.dns.delete_domain(self.main_domain, domain)

            return domain

    def domain_acquire(self, request):
        user = self.authenticate(request)

        validator = Validator(request)
        user_domain = validator.new_user_domain()
        device_mac_address = validator.device_mac_address()
        device_name = validator.string('device_name', required=True)
        device_title = validator.string('device_title', required=True)
        check_validator(validator)

        with self.create_storage() as storage:
            domain = storage.get_domain_by_name(user_domain)
            if domain and domain.user_id != user.id:
                raise servicesexceptions.parameter_error('user_domain', 'User domain name is already in use')

            update_token = util.create_token()
            if not domain:
                domain = Domain(user_domain, device_mac_address, device_name, device_title, update_token=update_token)
                domain.user = user
                storage.add(domain)
            else:
                domain.update_token = update_token
                domain.device_mac_address = device_mac_address
                domain.device_name = device_name
                domain.device_title = device_title

            return domain

    def service_compare(self, a, b):
        return a.port == b.port and a.local_port == b.local_port and a.type == b.type and a.protocol == b.protocol and a.name == b.name

    def get_missing(self, lookfor, lookat):
        result = []
        for s in lookfor:
            existing = None
            for x in lookat:
                if self.service_compare(x, s):
                    existing = x
            if not existing:
                result.append(s)
        return result

    def validate_service(self, data):
        validator = Validator(data)
        validator.port('port', required=False)
        validator.port('local_port')
        check_validator(validator)

    def domain_update(self, request, request_ip=None):
        validator = Validator(request)
        token = validator.token()
        ip = validator.ip(request_ip)
        ipv6 = validator.string('ipv6', required=False)
        local_ip = validator.local_ip()
        map_local_address = validator.boolean('map_local_address', required=False)
        platform_version = validator.string('platform_version', required=False)
        web_protocol = validator.web_protocol(required=True)
        web_local_port = validator.port('web_local_port', required=True)
        web_port = validator.port('web_port', required=False)
        check_validator(validator)

        if map_local_address is None:
            map_local_address = False

        with self.create_storage() as storage:
            domain = storage.get_domain_by_update_token(token)

            if not domain or not domain.user.active:
                raise servicesexceptions.bad_request('Unknown domain update token')

            update_ip = (domain.map_local_address != map_local_address) or (domain.ip != ip) or (domain.local_ip != local_ip)
            domain.ip = ip
            domain.local_ip = local_ip
            domain.ipv6 = ipv6
            domain.map_local_address = map_local_address
            domain.platform_version = platform_version
            domain.web_protocol = web_protocol
            domain.web_local_port = web_local_port
            domain.web_port = web_port

            if update_ip:
                self.dns.update_domain(self.main_domain, domain)

            domain.last_update = datetime.now()
            return domain

    def domain_delete(self, request):
        user = self.authenticate(request)
        self.user_domain_delete(request, user)

    def user_domain_delete(self, request, user):
        validator = Validator(request)
        user_domain = validator.user_domain()
        check_validator(validator)

        with self.create_storage() as storage:
            domain = storage.get_domain_by_name(user_domain)

            if not domain or domain.user.email != user.email:
                raise servicesexceptions.bad_request('Unknown domain')

            self.dns.delete_domain(self.main_domain, domain)

            storage.delete_domain(domain)

    def user_set_subscribed(self, request, user_email):
        validator = Validator(request)
        subscribed = validator.boolean('subscribed', required=True)
        check_validator(validator)

        with self.create_storage() as storage:
            user = storage.get_user_by_email(user_email)
            if not user:
                raise servicesexceptions.bad_request('Unknown user')
            user.unsubscribed = not subscribed

    def get_domain(self, request):
        validator = Validator(request)
        token = validator.token()
        with self.create_storage() as storage:
            domain = storage.get_domain_by_update_token(token)
            if not domain or not domain.user.active:
                raise servicesexceptions.bad_request('Unknown domain update token')
            return domain

    def delete_user(self, request):
        validator = Validator(request)
        email = validator.email()
        password = validator.password()
        check_validator(validator)

        with self.create_storage() as storage:
            user = storage.get_user_by_email(email)

            if not user or not user.active or not util.hash(password) == user.password_hash:
                raise servicesexceptions.bad_request('Authentication failed')

            for domain in user.domains:
                self.dns.delete_domain(self.main_domain, domain)

            storage.delete_user(user)

    def do_delete_user(self, email):
        with self.create_storage() as storage:
            user = storage.get_user_by_email(email)

            if not user:
                raise servicesexceptions.bad_request('Authentication failed')

            for domain in user.domains:
                self.dns.delete_domain(self.main_domain, domain)

            storage.delete_user(user)

    def do_user_domain_delete(self, user_domain):
        with self.create_storage() as storage:
            domain = storage.get_domain_by_name(user_domain)

            if not domain:
                raise servicesexceptions.bad_request('Unknown domain')

            self.dns.delete_domain(self.main_domain, domain)

            storage.delete_domain(domain)

    def user_reset_password(self, request):
        validator = Validator(request)
        email = validator.email()
        check_validator(validator)

        with self.create_storage() as storage:
            user = storage.get_user_by_email(email)

            if user and user.active:
                action = user.enable_action(ActionType.PASSWORD)

                self.mail.send_reset_password(user.email, action.token)

    def user_log(self, request):
        validator = Validator(request)
        token = validator.token()
        data = validator.string('data')
        include_support = validator.boolean('include_support', False, True)
        with self.create_storage() as storage:
            user = storage.get_user_by_update_token(token)
            if not user:
                raise servicesexceptions.bad_request('Invalid update token')
            self.mail.send_logs(user.email, data, include_support)

    def user_set_password(self, request):
        validator = Validator(request)
        token = validator.token()
        password = validator.new_password()
        check_validator(validator)

        with self.create_storage() as storage:
            user = storage.get_user_by_token(ActionType.PASSWORD, token)

            if not user:
                raise servicesexceptions.bad_request('Invalid password token')

            user.password_hash = util.hash(password)

            self.mail.send_set_password(user.email)

            action = storage.get_action(token)
            storage.delete(action)

    def port_probe(self, request, request_ip):
        validator = Validator(request)
        token = validator.token()
        port = validator.port('port', True)
        protocol = validator.string('protocol', False)
        ip = validator.string('ip', False)
        check_validator(validator)
        domain = None
        with self.create_storage() as storage:
            domain = storage.get_domain_by_update_token(token)

        if not domain or not domain.user.active:
            raise servicesexceptions.bad_request('Unknown domain update token')

        try:
            if ip:
                request_ip = ip
            
            response = requests.get('{0}://{1}:{2}/ping'.format(protocol, request_ip, port),
                                    timeout=1, verify=False, allow_redirects=False)
            if response.status_code == 200:
                return {'message': response.text, 'device_ip': request_ip}, 200

            # TODO: Remove after release 18.07 reaches wider adoption
            elif response.status_code == 301 and protocol == 'http':
                return {'message': "OK", 'device_ip': request_ip}, 200

        except Exception, e:
            pass

        return {'message': 'Port is not reachable', 'device_ip': request_ip}, 404
