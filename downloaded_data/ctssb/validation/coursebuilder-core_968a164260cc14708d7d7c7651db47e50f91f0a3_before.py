# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Handlers that are not directly related to course content."""

__author__ = 'Saifu Angto (saifu@google.com)'

import base64
import hmac
import time
import urlparse
import jinja2
from models.config import ConfigProperty
from models.courses import Course
from models.models import MemcacheManager
from models.models import Student
from models.roles import Roles
from models.utils import get_all_scores
import webapp2
from webapp2_extras import i18n
from google.appengine.api import users


# FIXME: Set MAX_CLASS_SIZE to a positive integer if you want to restrict the
# course size to a maximum of N students. Note, though, that counting the
# students in this way uses a lot of database calls that may cost you quota
# and money.
# TODO(psimakov): we must use sharded counter and not Student.all().count()
MAX_CLASS_SIZE = None

# The name of the template dict key that stores a course's base location.
COURSE_BASE_KEY = 'gcb_course_base'

# The name of the template dict key that stores data from course.yaml.
COURSE_INFO_KEY = 'course_info'


XSRF_SECRET = ConfigProperty(
    'gcb_xsrf_secret', str, (
        'A secret text used to encrypt XSRF tokens. Can be any alphanumeric '
        'text, desirably 16-64 characters long. When this value changes, all '
        'requests issued using the old value will be rejected by the server.'),
    'course builder XSRF secret')


class ReflectiveRequestHandler(object):
    """Uses reflection to handle custom get() and post() requests.

    Use this class as a mix-in with any webapp2.RequestHandler to allow request
    dispatching to multiple get() and post() methods based on the 'action'
    parameter.

    Open your existing webapp2.RequestHandler, add this class as a mix-in.
    Define the following class variables:

        default_action = 'list'
        get_actions = ['default_action', 'edit']
        post_actions = ['save']

    Add instance methods named get_list(self), get_edit(self), post_save(self).
    These methods will now be called automatically based on the 'action'
    GET/POST parameter.
    """

    def create_xsrf_token(self, action):
        return XsrfTokenManager.create_xsrf_token(action)

    def get(self):
        """Handles GET."""
        action = self.request.get('action')
        if not action:
            action = self.__class__.default_action

        if not action in self.__class__.get_actions:
            self.error(404)
            return

        handler = getattr(self, 'get_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()

    def post(self):
        """Handles POST."""
        action = self.request.get('action')
        if not action or not action in self.__class__.post_actions:
            self.error(404)
            return

        handler = getattr(self, 'post_%s' % action)
        if not handler:
            self.error(404)
            return

        # Each POST request must have valid XSRF token.
        xsrf_token = self.request.get('xsrf_token')
        if not XsrfTokenManager.is_xsrf_token_valid(xsrf_token, action):
            self.error(403)
            return

        return handler()


class ApplicationHandler(webapp2.RequestHandler):
    """A handler that is aware of the application context."""

    @classmethod
    def is_absolute(cls, url):
        return bool(urlparse.urlparse(url).scheme)

    @classmethod
    def get_base_href(cls, handler):
        """Computes current course <base> href."""
        base = handler.app_context.get_slug()
        if not base.endswith('/'):
            base = '%s/' % base

        # For IE to work with the <base> tag, its href must be an absolute URL.
        if not cls.is_absolute(base):
            parts = urlparse.urlparse(handler.request.url)
            base = urlparse.urlunparse(
                (parts.scheme, parts.netloc, base, None, None, None))
        return base

    def __init__(self):
        super(ApplicationHandler, self).__init__()
        self.template_value = {}

    def get_template(self, template_file, additional_dir=None):
        """Computes location of template files for the current namespace."""
        self.template_value[COURSE_INFO_KEY] = self.app_context.get_environ()
        self.template_value['is_manager'] = Roles.is_course_admin(
            self.app_context)
        self.template_value[COURSE_BASE_KEY] = self.get_base_href(self)

        template_dir = self.app_context.get_template_home()
        dirs = [template_dir]
        if additional_dir:
            dirs += additional_dir

        jinja_environment = jinja2.Environment(
            extensions=['jinja2.ext.i18n'],
            loader=jinja2.FileSystemLoader(dirs))
        jinja_environment.install_gettext_translations(i18n)

        locale = self.template_value[COURSE_INFO_KEY]['course']['locale']
        i18n.get_i18n().set_locale(locale)

        return jinja_environment.get_template(template_file)

    def canonicalize_url(self, location):
        """Adds the current namespace URL prefix to the relative 'location'."""
        if not self.is_absolute(location):
            if (self.app_context.get_slug() and
                self.app_context.get_slug() != '/'):
                location = '%s%s' % (self.app_context.get_slug(), location)
        return location

    def redirect(self, location):
        super(ApplicationHandler, self).redirect(
            self.canonicalize_url(location))


class BaseHandler(ApplicationHandler):
    """Base handler."""

    def __init__(self):
        super(BaseHandler, self).__init__()
        self.course = None

    def get_course(self):
        if not self.course:
            self.course = Course(self)
        return self.course

    def get_units(self):
        """Gets all units in the course."""
        return self.get_course().get_units()

    def get_lessons(self, unit_id):
        """Gets all lessons (in order) in the specific course unit."""
        return self.get_course().get_lessons(unit_id)

    def get_user(self):
        """Validate user exists."""
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
        else:
            return user

    def personalize_page_and_get_user(self):
        """If the user exists, add personalized fields to the navbar."""
        user = self.get_user()
        if user:
            self.template_value['email'] = user.email()
            self.template_value['logoutUrl'] = users.create_logout_url('/')
        return user

    def personalize_page_and_get_enrolled(self):
        """If the user is enrolled, add personalized fields to the navbar."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return None

        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return None

        return student

    def assert_xsrf_token_or_fail(self, action):
        """Asserts the current request has proper XSRF token or fails."""
        xsrf_token = self.request.get('xsrf_token')
        if not XsrfTokenManager.is_xsrf_token_valid(xsrf_token, action):
            self.error(403)
            return False
        return True

    def render(self, template_file):
        template = self.get_template(template_file)
        self.response.out.write(template.render(self.template_value))


class PreviewHandler(BaseHandler):
    """Handler for viewing course preview."""

    def get(self):
        """Handles GET requests."""
        user = users.get_current_user()
        if not user:
            self.template_value['loginUrl'] = users.create_login_url('/')
        else:
            self.template_value['email'] = user.email()
            self.template_value['logoutUrl'] = users.create_logout_url('/')

        self.template_value['navbar'] = {'course': True}
        self.template_value['units'] = self.get_units()
        if user and Student.get_enrolled_student_by_email(user.email()):
            self.redirect('/course')
        else:
            self.render('preview.html')


class RegisterHandler(BaseHandler):
    """Handler for course registration."""

    def get(self):
        """Handles GET request."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if student:
            self.redirect('/course')
            return

        self.template_value['navbar'] = {'registration': True}
        self.template_value['register_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('register'))
        self.render('register.html')

    def post(self):
        """Handles POST requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        if not self.assert_xsrf_token_or_fail('register'):
            return

        if (MAX_CLASS_SIZE and
            Student.all(keys_only=True).count() >= MAX_CLASS_SIZE):
            self.template_value['course_status'] = 'full'
        else:
            name = self.request.get('form01')

            # create new or re-enroll old student
            student = Student.get_by_email(user.email())
            if not student:
                student = Student(key_name=user.email())
                student.user_id = user.user_id()

            student.is_enrolled = True
            student.name = name
            student.put()

        # Render registration confirmation page
        self.template_value['navbar'] = {'registration': True}
        self.render('confirmation.html')


class ForumHandler(BaseHandler):
    """Handler for forum page."""

    def get(self):
        """Handles GET requests."""
        if not self.personalize_page_and_get_enrolled():
            return

        self.template_value['navbar'] = {'forum': True}
        self.render('forum.html')


class StudentProfileHandler(BaseHandler):
    """Handles the click to 'My Profile' link in the nav bar."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['navbar'] = {}
        self.template_value['student'] = student
        self.template_value['scores'] = get_all_scores(student)
        self.template_value['student_edit_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('student_edit'))
        self.render('student_profile.html')


class StudentEditStudentHandler(BaseHandler):
    """Handles edits to student records by students."""

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail('student_edit'):
            return

        Student.rename_current(self.request.get('name'))

        self.redirect('/student/home')


class StudentUnenrollHandler(BaseHandler):
    """Handler for students to unenroll themselves."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        self.template_value['student'] = student
        self.template_value['navbar'] = {'registration': True}
        self.template_value['student_unenroll_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('student_unenroll'))
        self.render('unenroll_confirmation_check.html')

    def post(self):
        """Handles POST requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail('student_unenroll'):
            return

        Student.set_enrollment_status_for_current(False)

        self.template_value['navbar'] = {'registration': True}
        self.render('unenroll_confirmation.html')


class XsrfTokenManager(object):
    """Provides XSRF protection by managing action/user tokens in memcache."""

    # Max age of the token (4 hours).
    XSRF_TOKEN_AGE_SECS = 60 * 60 * 4

    # Token delimiters.
    DELIMITER_PRIVATE = ':'
    DELIMITER_PUBLIC = '/'

    # Default nickname to use if a user does not have a nickname,
    USER_ID_DEFAULT = 'default'

    @classmethod
    def _create_token(cls, action_id, issued_on):
        """Creates a string representation (digest) of a token."""

        # We have decided to use transient tokens to reduce datastore costs.
        # The token has 4 parts: hash of the actor user id, hash of the action,
        # hash if the time issued and the plain text of time issued.

        # Lookup user id.
        user = users.get_current_user()
        if user:
            user_id = user.user_id()
        else:
            user_id = cls.USER_ID_DEFAULT

        # Round time to seconds.
        issued_on = long(issued_on)

        digester = hmac.new(XSRF_SECRET.value)
        digester.update(str(user_id))
        digester.update(cls.DELIMITER_PRIVATE)
        digester.update(str(action_id))
        digester.update(cls.DELIMITER_PRIVATE)
        digester.update(str(issued_on))

        digest = digester.digest()
        token = '%s%s%s' % (
            issued_on, cls.DELIMITER_PUBLIC, base64.urlsafe_b64encode(digest))

        return token

    @classmethod
    def create_xsrf_token(cls, action):
        return cls._create_token(action, time.time())

    @classmethod
    def is_xsrf_token_valid(cls, token, action):
        """Validate a given XSRF token by retrieving it from memcache."""

        try:
            parts = token.split(cls.DELIMITER_PUBLIC)
            if not len(parts) == 2:
                raise Exception('Bad token format, expected: a/b.')

            issued_on = long(parts[0])
            age = time.time() - issued_on
            if age > cls.XSRF_TOKEN_AGE_SECS:
                return False

            authentic_token = cls._create_token(action, issued_on)
            if authentic_token == token:
                return True

            return False
        except Exception:  # pylint: disable-msg=broad-except
            return False

        user_str = cls._make_user_str()
        token_obj = MemcacheManager.get(token)
        if not token_obj:
            return False
        token_str, token_action = token_obj
        if user_str != token_str or action != token_action:
            return False
        return True
