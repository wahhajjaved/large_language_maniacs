"""
Django settings for zosiaproject project.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
DJ_PROJECT_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(DJ_PROJECT_DIR)
WSGI_DIR = os.path.dirname(BASE_DIR)
REPO_DIR = os.path.dirname(WSGI_DIR)
DATA_DIR = os.environ.get('OPENSHIFT_DATA_DIR', BASE_DIR)
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

import sys
sys.path.append(os.path.join(REPO_DIR, 'libs'))
import secrets
SECRETS = secrets.getter(os.path.join(DATA_DIR, 'secrets.json'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = SECRETS.get('secret_key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG') == 'True'

from socket import gethostname
ALLOWED_HOSTS = [
    gethostname(), # For internal OpenShift load balancer security purposes
    os.environ.get('OPENSHIFT_APP_DNS'), # Dynamically map to the OpenShift gear name
    'zosia.org',
    'www.zosia.org',
]


# Django Debug Toolbar
#

def custom_show_toolbar(request):
    return DEBUG

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': 'zosiaproject.settings.custom_show_toolbar',
}


# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    #'django.contrib.formtools',
    'dbbackup',  # django-dbbackup
    'import_export',  # django-import-export
    'debug_toolbar',  # django-debug-toolbar

    'rooms',
    'lectures',
    'blog',
    'common',
    'blurb',
    'users',
    'sponsors',
    'polls',
    'committee',
    #'django_extensions',
)

MIDDLEWARE_CLASSES = (
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
)

ROOT_URLCONF = 'zosiaproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates')
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.request',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'zosiaproject.wsgi.application'


# Authentication backend
#

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)
AUTH_USER_MODEL = 'users.Participant'
LOGIN_REDIRECT_URL = '/change_preferences/'
LOGIN_URL = '/login/'
LOGOUT_URL = '/logout/'


# Disable caching
#

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.environ.get('PGDATABASE', 'postgres'),
        'USER': os.environ.get('OPENSHIFT_POSTGRESQL_DB_USERNAME', 'postgres'),
        'PASSWORD': os.environ.get('OPENSHIFT_POSTGRESQL_DB_PASSWORD', ''),
        'HOST': os.environ.get('OPENSHIFT_POSTGRESQL_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('OPENSHIFT_POSTGRESQL_DB_PORT', '5432')
    }
}


# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'pl'
LANGUAGES = (
    ('pl', 'Polish'),
)
LOCALE_PATHS = (os.path.join(BASE_DIR, 'locale'),)
SITE_ID = 1
TIME_ZONE = 'Europe/Warsaw'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(WSGI_DIR, 'static')


# Media directory
# (used for content uploaded by users)

MEDIA_URL = '/static/media/'
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')


# E-mail configuration

EMAIL_BACKEND = 'django_mailgun.MailgunBackend'
MAILGUN_ACCESS_KEY = SECRETS.get('mailgun_access_key')
MAILGUN_SERVER_NAME = SECRETS.get('mailgun_server_name')


# Django Database Backup

DBBACKUP_STORAGE = 'dbbackup.storage.filesystem_storage'
DBBACKUP_STORAGE_OPTIONS = {'location': os.path.join(DATA_DIR, 'backups')}
