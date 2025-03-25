import sys
import os
import re
import socket
import json
import time
import zipfile
import shutil
from fnmatch import fnmatch
import datetime
import tempfile
import locale

try:
    # Python 3
    from urllib.parse import urlencode, urlparse
    import compileall
    str_cls = str
except (ImportError):
    # Python 2
    from urllib import urlencode
    from urlparse import urlparse
    str_cls = unicode

import sublime

from .show_error import show_error
from .console_write import console_write
from .open_compat import open_compat, read_compat, fix_windows_path
from .unicode import unicode_from_os
from .cache import (clear_cache, set_cache, get_cache, merge_cache_under_settings,
    merge_cache_over_settings, set_cache_under_settings, set_cache_over_settings)
from .downloaders.background_downloader import BackgroundDownloader
from .downloaders.downloader_exception import DownloaderException
from .providers.provider_exception import ProviderException
from .clients.client_exception import ClientException
from .download_manager import downloader
from .business_object_io import read_business_object_file
from .providers import REPOSITORY_PROVIDERS
from . import __version__


class BusinessObjectManager():
    """
    Allows downloading, creating and deleting business objects

    Also handles displaying business object messaging, and sending usage information to
    the usage server.
    """

    def __init__(self):
        # Here we manually copy the settings since sublime doesn't like
        # code accessing settings from threads
        self.settings = {}
        settings = sublime.load_settings('CoreBuilder.sublime-settings')
        for setting in ['debug', 'repository', 'timeout', 'cache_length', 'http_proxy', 'https_proxy', 'proxy_username', 'proxy_password', 'http_cache', 'http_cache_length', 'user_agent']:
            if settings.get(setting) == None:
                continue
            self.settings[setting] = settings.get(setting)

        # https_proxy will inherit from http_proxy unless it is set to a
        # string value or false
        no_https_proxy = self.settings.get('https_proxy') in ["", None]
        if no_https_proxy and self.settings.get('http_proxy'):
            self.settings['https_proxy'] = self.settings.get('http_proxy')
        if self.settings.get('https_proxy') == False:
            self.settings['https_proxy'] = ''

        self.settings['platform'] = sublime.platform()
        self.settings['version'] = sublime.version()


    def get_repository(self):
        """
        Returns the repository

        This repository come from "repository" setting.

        :return:
            The available repository
        """

        cache_ttl = self.settings.get('cache_length')
        repository = self.settings.get('repository')
        if not repository:
            self.__init__()
            
            cache_ttl = self.settings.get('cache_length')
            repository = self.settings.get('repository')
            if not repository:
                show_error(u'A valid repository URL should be defined at "repository" setting in "CoreBuilder.sublime-settings" file.')
                return ''

        try:
            cache_key = repository + '.business-objects'
            repo_business_objects = get_cache(cache_key)

            if repo_business_objects == None:
                for provider_class in REPOSITORY_PROVIDERS:
                    if provider_class.match_url(repository):
                        provider = provider_class(repository, self.settings)
                        break
                repo_business_objects = provider.get_business_objects()
                set_cache(cache_key, repo_business_objects, cache_ttl)

        except (DownloaderException, ClientException, ProviderException) as e:
            console_write(e, True)
            return ''

        return repository


    def list_available_business_objects(self):
        """
        Returns a list of every available business object from the source

        :return:
            A dict in the format:
            {
                'Business Object Reference': {
                    # Business object details - see example-business-object.json for format
                },
                ...
            }
        """

        if self.settings.get('debug'):
            console_write(u"Fetching list of available business objects", True)
            console_write(u"  Platform: %s-%s" % (sublime.platform(),sublime.arch()))
            console_write(u"  Sublime Text Version: %s" % sublime.version())
            console_write(u"  CoreBuilder Plugin Version: %s" % __version__)

        cache_ttl = self.settings.get('cache_length')
        repository = self.get_repository()
        business_objects = {}
        bg_downloaders = {}
        active = []
        repos_to_download = []

        if repository:
            cache_key = repository + '.business-objects'
            repository_business_objects = get_cache(cache_key)
            
            if repository_business_objects != None:
                business_objects.update(repository_business_objects)
                
            else:
                domain = urlparse(repository).hostname
                if domain not in bg_downloaders:
                    bg_downloaders[domain] = BackgroundDownloader(
                        self.settings, REPOSITORY_PROVIDERS)
                bg_downloaders[domain].add_url(repository)
                repos_to_download.append(repository)

            for bg_downloader in list(bg_downloaders.values()):
                bg_downloader.start()
                active.append(bg_downloader)

            # Wait for all of the downloaders to finish
            while active:
                bg_downloader = active.pop()
                bg_downloader.run()

            # Grabs the results and stuff it all in the cache
            for repo in repos_to_download:
                domain = urlparse(repo).hostname
                bg_downloader = bg_downloaders[domain]
                provider = bg_downloader.get_provider(repo)
                repository_business_objects = provider.get_business_objects()

                # Display errors we encountered while fetching package info
                for url, exception in provider.get_failed_sources():
                    console_write(exception, True)

                if repository_business_objects != None:
                    cache_key = repo + '.business-objects'
                    set_cache(cache_key, repository_business_objects, cache_ttl)
                    business_objects.update(repository_business_objects)
            
        return business_objects


    def open_business_object(self, reference):
        """
        Downloads a business object

        Uses the self.list_available_business_objects() method to determine where to
        retrieve the business object from.

        The download process consists of:

        1. Finding the business object
        2. Downloading the file source code
        3. Write the file on business object folder
        4. Open a new tab with the file

        :param reference:
            The business object reference to download

        :return: bool if the business object was successfully downloaded
        """

        business_objects = self.list_available_business_objects()

        params = {
            'action': 'open'    
        }
        url = business_objects[reference]['url'] + '&' + urlencode(params)

        source = business_objects[reference]['source']

        # Download the business object
        try:
            with downloader(url, self.settings) as manager:
                json_string = manager.fetch(url, 'Error downloading business object.')
        except (DownloaderException) as e:
            console_write(e, True)
            show_error(u'Unable to download %s. Please view the console for more details.' % reference)
            return False

        try:
            business_object = json.loads(json_string.decode('utf-8'))
        except (ValueError) as e:
            console_write(e, True)
            show_error(u'Error parsing JSON from %s.' % url)
            return False

        if 'error' in business_object:
            error_string = "Unable to download {0}. The following error message has returned: {1}".format(reference, business_object['error'].encode('utf-8'))
            show_error(error_string)
            return False

        schema_error = u'Business object %s does not appear to be a valid file because' % reference
        if 'code' not in business_object:
            error_string = u'%s the "code" JSON key is missing.' % schema_error
            show_error(error_string)
            return False

        try:
            business_object_filename = reference.lower() + '.' + business_object['type']
            
            business_object_dir = os.path.join(sublime.packages_path(), 'User', 'CoreBuilder.business-objects', urlparse(source).hostname)
            if not os.path.exists(business_object_dir):
                os.makedirs(business_object_dir)

            business_object_file = os.path.join(business_object_dir, business_object_filename)
            with open_compat(business_object_file, 'wb') as f:
                f.write(business_object['code'].encode('utf-8'))
                f.close

            def open_file():
                sublime.active_window().run_command('open_file', {'file': fix_windows_path(business_object_file)})
                if business_object['type'] == 'php':
                    sublime.active_window().active_view().settings().set('syntax', 'Packages/PHP/PHP.tmLanguage')
                else:
                    sublime.active_window().active_view().settings().set('syntax', 'Packages/CoreBuilder/CoreBuilder.tmLanguage')
            sublime.set_timeout(open_file, 1)

        except (OSError, IOError) as e:
            show_error(u'An error occurred creating the business object file %s in %s.\n\n%s' % (
                business_object_filename, business_object_dir, unicode_from_os(e)))
            return False

        return True

    def save_business_object(self, reference, business_object_file):
        """
        Uploads a business object

        Uses the self.list_available_business_objects() method to determine where to
        send the business object to.

        The download process consists of:

        1. Finding the business object
        2. Uploading the file source code
        3. Show the server message

        :param reference:
            The business object reference to upload

        :return: bool if the business object was successfully uploaded
        """

        business_objects = self.list_available_business_objects()

        params = {
            'action': 'save'
        }
        url = business_objects[reference]['url'] + '&' + urlencode(params)

        source = business_objects[reference]['source']

        with open_compat(business_object_file, 'r') as f:
            source_code = read_compat(f)
            f.close

        # Upload the business object
        try:
            with downloader(url, self.settings) as manager:
                json_string = manager.fetch(url, 'Error uploading business object.', u'POST', source_code.encode('utf-8'))
        except (DownloaderException) as e:
            console_write(e, True)
            show_error(u'Unable to upload %s. Please view the console for more details.' % reference)
            return False

        if not json_string:
            error_string = "Unable to upload {0}. No response message was given by the server.".format(reference)
            show_error(error_string)
            return False

        def show_error_file(error_file):
            position = error_file.find('/compile/dll/log/')
            if position > 0:
                pos_string = error_file[(position + 1):]
                error_url = 'https://' + urlparse(source).hostname + '/resources/system/' + pos_string

                # Download the error file
                try:
                    with downloader(error_url, self.settings) as manager:
                        msg_string = manager.fetch(error_url, 'Error downloading business object.')
                except (DownloaderException) as e:
                    console_write(e, True)
                    show_error(u'Unable to download %s. Please view the console for more details.' % error_url)
                    return False

                error_file_name = os.path.splitext(os.path.basename(error_file))[0].lower()
                position = error_file_name.find('?pagesession')
                if position > 0:
                    error_file_name = error_file_name[:(position)]

                error_dir = os.path.join(sublime.packages_path(), 'User', 'CoreBuilder.business-objects', urlparse(source).hostname)
                if not os.path.exists(error_dir):
                    os.makedirs(error_dir)

                error_file_path = os.path.join(error_dir, error_file_name)
                with open_compat(error_file_path, 'wb') as f:
                    f.write(msg_string.encode('utf-8'))
                    f.close
                
                def open_file():
                    sublime.active_window().run_command('open_file', {'file': fix_windows_path(error_file_path)})
                sublime.set_timeout(open_file, 1)
                return True
            return False

        try:
            response = json.loads(json_string.decode('utf-8'))
        except (ValueError) as e:
            if not show_error_file(json_string.decode('utf-8')):
                console_write(e, True)
                show_error(u'Error parsing JSON from %s.' % url)
            return False
        
        if 'error' in response:
            error_string = u'Unable to upload %s. The following error message has returned: %s' % (reference, response['error'])
            show_error(error_string)
            return False

        schema_error = u'Unable to upload %s.' % reference
        if 'status' not in response:
            error_string = u'%s The "status" JSON key is missing.' % schema_error
            show_error(error_string)
            return False

        status_message = response['status_message'].encode('utf-8')
        if not show_error_file(status_message.decode('utf-8')):
            console_write(status_message, True)

        if response['status'].upper() != 'OK':
            return False
        return True
