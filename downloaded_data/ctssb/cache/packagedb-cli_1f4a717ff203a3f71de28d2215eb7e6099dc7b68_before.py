# -*- coding: utf-8 -*-

"""
# pkgdb2 - a python module to query the Fedora package database v2
#
# Copyright (C) 2014 Red Hat Inc
# Copyright (C) 2013 Pierre-Yves Chibon
# Author: Pierre-Yves Chibon <pingou@pingoured.fr>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
# See http://www.gnu.org/copyleft/gpl.html  for the full text of the
# license.
"""

try:
    import cPickle as pickle
except ImportError:
    import pickle
import getpass
import logging
import os
import pkg_resources

import fedora_cert
from fedora.client import AuthError
import requests


class NullHandler(logging.Handler):
    ''' Null logger to avoid spurious messages

    '''
    def emit(self, record):
        pass

LOG = logging.getLogger("pkgdb2client")

# Add the null handler to top-level logger used by the library
h = NullHandler()
LOG.addHandler(h)

__version__ = pkg_resources.get_distribution('packagedb-cli').version
PKGDB_URL = r'https://admin.fedoraproject.org/pkgdb/'


class PkgDBException(Exception):
    ''' Generic exception class raised when the Package DB returned an
    error.

    '''
    pass


class PkgDBAuthException(PkgDBException, AuthError):
    ''' Authentication exception raised when trying to call a method that
    requires authentication while not being authenticated.

    '''
    pass


def _parse_service_form(response):
    """ Retrieve the attributes from the html login form.

    Basically this extracts all the field of the form so that we can
    forward them to the OpenID API.
    """
    import bs4

    parsed = bs4.BeautifulSoup(response.text)
    inputs = {}
    for child in parsed.form.find_all(name='input'):
        if child.attrs['type'] == 'submit':
            continue
        inputs[child.attrs['name']] = child.attrs['value']
    return (parsed.form.attrs['action'], inputs)


def ask_password(username=None, bad_password=False):
    """ Example login_callback to ask username/password from user
    :kwarg username: Username
    :type username: str
    :kwarg bad_password: Whether there was a previous failed login attempt
    :type bad_password: bool
    :return: username, password
    :rtype: tuple
    """
    if bad_password:
        print "Bad password, please retry"
    if not username:
        try:
            username = fedora_cert.read_user_cert()
        except fedora_cert.fedora_cert_error:
            LOG.debug('Could not read Fedora cert, asking for username')
            username = raw_input("Username: ")
    password = getpass.getpass("FAS password for user {0}: ".format(username))
    return username, password


class PkgDB(object):
    ''' PkgDB class used to interact with the Package DB instance via its
    API.

    '''

    def __init__(self, url=PKGDB_URL, insecure=False, cookies=None,
                 login_callback=None, login_attempts=3,
                 sessionfile="~/.cache/pkgdb-session.pickle"):
        ''' Constructor for the PkgDB object used to query the package
        database.

        :kwarg url: the basic url to the package DB instance to query
        :type url: str
        :kwarg insecure: If :data:`True` then the connection to the server
            is not checked to be sure that any SSL certificate information
            is valid.  That means that a remote host can lie about who it
            is.  Useful for development but should not be used in
            production code.
        :type insecure: bool
        :kwarg login_callback: Function to be called to provide username and/or
            password, it must accept two keyword arguments, `username` and
            `bad_password`. Username is the currently known username (can be
            None) and bad_password is a bool to specifies whether a bad
            password was supplied earlier. It needs to return a (username,
            password) tuple. See pkgdb2client.ask_password() for an example.
        :type login_callback: function
        :kwarg login_attempts: How often a login might fail after
            login_callback() was called before a API call fails permanently.
        :type login_attempts: int

        '''
        self.url = url
        self.session = requests.session()
        self.insecure = insecure
        self.username = None
        self.password = None
        self.login_callback = login_callback
        self.login_attempts = login_attempts
        self.sessionfile = os.path.expanduser(sessionfile)

        try:
            with open(self.sessionfile, "rb") as sessionfo:
                self.session.cookies = pickle.load(sessionfo)["cookies"]
        except (IOError, KeyError, TypeError):
            pass

    def __send_request(self, url, method, params=None, data=None):
        ''' Send a http request to the provided URL with the provided
        method.

        :arg url: the url to query
        :arg method: the http method to use when querying the url
        :kwarg params: the arguments to use in the query
        :kwarg data: the data

        '''
        LOG.debug(
            'Calling: %s with arg: %s and data: %s', url, params, data)
        req = self.session.request(
            method=method,
            url=url,
            params=params,
            data=data,
            verify=not self.insecure,
        )
        self._save_cookies()
        return req

    def _save_cookies(self):
        try:
            with open(self.sessionfile, 'rb') as sessionfo:
                data = pickle.load(sessionfo)
        except:
            data = {}
        try:
            with open(self.sessionfile, 'wb', 0600) as sessionfo:
                sessionfo.seek(0)
                data["cookies"] = self.session.cookies
                pickle.dump(data, sessionfo)
        except:
            pass

    @property
    def is_logged_in(self):
        ''' Return whether the user if logged in or not. '''

        response = self.session.get(self.url + '/login/')
        return "logged in as" in response.text

    def login(self, username=None, password=None, openid_insecure=False,
              response=None):
        ''' Login the user on pkgdb2.

        :arg username: the FAS username of the user.
        :type username: str
        :arg password: the FAS password of the user.
        :type password: str
        :kwarg openid_insecure: If True, do not check the openid server
            certificates against their CA's.  This means that man-in-the
            middle attacks are possible against the `BaseClient`. You might
            turn this option on for testing against a local version of a
            server with a self-signed certificate but it should be off in
            production.
        :type openid_insecure: bool
        '''
        if not username:
            username = self.username
        if not password:
            password = self.password
        if self.login_callback and not password:
            username, password = self.login_callback(username=username,
                                                     bad_password=False)

        if not username or not password:
            raise PkgDBAuthException('Username or password missing')

        import re
        from urlparse import urlparse, parse_qs

        fedora_openid_api = r'https://id.fedoraproject.org/api/v1/'
        fedora_openid = r'^http(s)?:\/\/id\.(|stg.|dev.)?fedoraproject'\
            '\.org(/)?'
        motif = re.compile(fedora_openid)

        # Log into the service
        if not response:
            response = self.session.get(self.url + '/login/')

        if '<title>OpenID transaction in progress</title>' \
                in response.text:
            # requests.session should hold onto this for us....
            openid_url, data = _parse_service_form(response)
            if not motif.match(openid_url):
                raise PkgDBException(
                    'Un-expected openid provider asked: %s' % openid_url)
        elif 'logged in as' in response.text:
            # User already logged in via its cookie file by default:
            # ~/.cache/pkgdb-session.pickle
            return
        else:
            data = {}
            for resp in response.history:
                if motif.match(resp.url):
                    parsed = parse_qs(urlparse(resp.url).query)
                    for key, value in parsed.items():
                        data[key] = value[0]
                    break
            else:
                raise PkgDBException(
                    'Unable to determine openid parameters from login: %r' %
                    openid_url)

        # Contact openid provider
        data['username'] = username
        data['password'] = password
        # Let's precise to FedOAuth that we want to authenticate with FAS
        data['auth_module'] = 'fedoauth.auth.fas.Auth_FAS'

        response = self.__send_request(
            url=fedora_openid_api,
            method='POST',
            data=data)
        output = response.json()

        if not output['success']:
            raise PkgDBException(output['message'])

        response = self.__send_request(
            url=output['response']['openid.return_to'],
            method='POST',
            data=output['response'])

        return output

    def call_api(self, path, params=None, data=None):
        ''' call the API.

        :arg path: The path to call
        :type path: str
        :arg params: URL params for the API call
        :type params: dict
        :arg data: POST data for the API call
        :type data: dict
        :return: requests response object
        :rtype: requests.models.Response
        :raise PkgDBAuthException: If login is required and fails
        '''
        if data:
            method = "POST"
        else:
            method = "GET"

        url = self.url + "/api" + path
        response = self.__send_request(url=url, method=method, data=data,
                                       params=params)
        if '<title>OpenID transaction in progress</title>' \
                in response.text:
            bad_password = False
            password = self.password
            username = self.username
            success = False
            for count in xrange(self.login_attempts):
                if not username or not password or bad_password:
                    if self.login_callback:
                        username, password = self.login_callback(
                            username=username,
                            bad_password=bad_password
                        )
                    else:
                        raise PkgDBAuthException('Authentication required')
                try:
                    self.login(username=username, password=password,
                               response=response)
                    success = True
                    break
                except PkgDBException as err:
                    log.debug('Exception: {0}'.format(err))
                    response = None
                    bad_password = True
            if not success:
                raise PkgDBAuthException("Too many failed login attempts")
            response = self.__send_request(url=url, method=method, data=data,
                                           params=params)
        return response

    def handle_api_call(self, path, params=None, data=None):
        ''' call the API.

        :arg path: The path to call
        :type path: str
        :arg params: URL params for the API call
        :type params: dict
        :arg data: POST data for the API call
        :type data: dict
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''

        response = self.call_api(path, params, data)
        output = None
        try:
            output = response.json()
        except Exception, err:
            LOG.debug('Error while decoding the JSON: {0}'.format(err))
            LOG.debug(response.text)

        if response.status_code != 200:
            LOG.debug('full output: {0}'.format(output))
            raise PkgDBException(output['error'])

        return output

    ## Actual API calls

    def create_collection(self, clt_name, version, clt_status, branchname,
                          dist_tag, git_branch_name, kojiname):
        ''' Create a new collection.

        :arg clt_name: The name of the collection, for example ``Fedora``
            or ``Fedora EPEL``
        :type clt_name: str
        :arg version: The version of the collection, for example ``21`` or
            ``devel``
        :type version: int or str
        :arg clt_status: The status of the collection, options are: ``EOL``,
            ``Active``, ``Under Development``
        :type clt_status: str
        :arg branchname: The branch name of the collection, for example
            ``f21`` or ``epel8``
        :type branchname: str
        :arg dist_tag: The dist tag of the collection, for example
            ``fc21`` or ``.el8``
        :type dist_tag: str
        :arg git_branch_name: The branch name in git for this collection
            for example ``f21`` or ``epel7``
        :type git_branch_name: str
        :arg kojiname: The koji name for this collection, for example
            ``f21`` or ``epel7``
        :type kojiname: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'clt_name': clt_name,
            'version': version,
            'clt_status': clt_status,
            'branchname': branchname,
            'dist_tag': dist_tag,
            'git_branch_name': git_branch_name,
            'kojiname': kojiname,
        }

        return self.handle_api_call('/collection/new/', data=args)

    def create_package(
            self, pkgname, summary, description, review_url, status,
            shouldopen, branches, poc, upstream_url, critpath=False):
        ''' Create a new package.

        :arg pkgname: The name of the package
        :type pkgname: str
        :arg summary: The summary of the package as provided in the
            spec file
        :type summary: str
        :arg description: The description of the package as provided in
            the spec file
        :type description: str
        :arg review_url: The URL to the package review where the
            package was approved
        :type review_url: str
        :arg status: The status of the package, options are:
            ``Approved``, ``Orphaned``, ``Removed``, ``Retired``
        :type status: str
        :arg shouldopen:
        :type shouldopen: bool
        :arg branches: The collection in which to add this package
        :type branches: str or list
        :arg poc: The point of contact of the package in the provided
            collection
        :type poc: str
        :arg upstream_url: The URL to the project upstream
        :type upstream_url: str
        :kwarg critpath: A boolean specifying whether to add this
            package to the critpath
        :type critpath: bool
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgname': pkgname,
            'summary': summary,
            'description': description,
            'review_url': review_url,
            'status': status,
            'shouldopen': shouldopen,
            'branches': branches,
            'poc': poc,
            'upstream_url': upstream_url,
        }
        if critpath:
            args['critpath'] = critpath

        return self.handle_api_call('/package/new/', data=args)

    def get_critpath_packages(self, branches=None, **kwargs):
        ''' Return the list of package names in the critical path.

        To get information about the ACL on the package, you
        also need to call ``get_package``.

        :kwarg branches: One or more branches to restrict the packages
            returned
        :type branches: str or list or None
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        Example of json returned

        ::

            {
              "pkgs": {
                "master": [
                  "rsyslog",
                  "pth",
                  "xorg-x11-server-utils",
                  "giflib"
                ]
              }
            }

        '''
        args = {
            'branches': branches,
            'format': 'json',
        }

        return self.handle_api_call('/critpath/', params=args)

    def get_collections(self, pattern='*', clt_status=None):
        ''' Return the list of collections matching the provided criterias.

        :kwarg pattern: The pattern to match against the branch name of the
            collections. Defaults to ``*``
        :type pattern: str
        :kwarg clt_status: One or more status of the collections to retrieve,
            options are: ``EOL``, ``Active``, ``Under Development``
        :type status: str or list
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pattern': pattern,
            'clt_status': clt_status,
        }

        return self.handle_api_call('/collections/', params=args)

    def get_package(self, pkgname, branches=None, eol=False):
        ''' Return the information of a package matching the provided
        criterias.

        :arg pkgname: The package name to retrieve information for
        :type pkgname: str
        :kwarg branches: The branches to retrieve information for
        :type branch: str or list
        :kwarg eol: a boolean to specify whether to include results for
            EOL collections or not. Defaults to ``False``.
            If True, it will return results for all collections (including
            EOL).
            If False, it will return results only for non-EOL collections.
        :type eol: boolean
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgname': pkgname,
            'branches': branches,
        }
        if eol is True:
            args['eol'] = eol

        return self.handle_api_call('/package/', params=args)

    def get_packager_acls(
            self, packagername, acls=None, eol=False, poc=None,
            page=1, count=False):
        ''' Return the list of ACL for the packager matching the provided
        criterias.

        To get information about what packages a user is poc on, you also
        want to call ``get_packages``.

        :arg packagername: The FAS username of the packager to retrieve the
            ACLs for
        :type packagername: str
        :kwarg acls: One or more ACL to filter/restrict the ACLs retrieved.
            Options are: ``approveacls``, ``commit``, ``watchbugzilla``,
            ``watchcommits``.
        :type acls: str or list or None
        :kwarg eol: a boolean to specify whether to include results for
            EOL collections or not. Defaults to ``False``.
            If True, it will return results for all collections (including
            EOL).
            If False, it will return results only for non-EOL collections.
        :type eol: boolean
        :kwarg poc: a boolean specifying whether the results should be
            restricted to ACL for which the provided packager is the point
            of contact or not. Defaults to None.
            If ``None`` it will not filter the ACLs returned based on the
            point of contact of the package (thus every packages is returned).
            If ``True`` it will only return ACLs for packages on which the
            provided packager is point of contact.
            If ``False`` it will only return ACLs for packages on which the
            provided packager is not the point of contact.
        :type poc: boolean or None
        :kwarg page: The page number to retrieve. If page is 0 or lower or
            equal to ``all`` then all pages are returned. Defaults to 0.
        :type page: int or ``all``
        :kwarg count: A boolean to retrieve the count of ACLs the user has
            instead of the details. If count is True the page argument will
            be ignored
        :type count: bool
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        def _get_pages(page):
            ''' Retrieve a specified page of a packager's ACLs list.

            :arg page: the page number to retrieve

            '''
            args = {
                'packagername': packagername,
                'acls': acls,
                'page': page,
            }
            if count is True:
                args['count'] = count
            if eol is True:
                args['eol'] = eol
            if poc is not None:
                args['poc'] = poc

            return self.handle_api_call('/packager/acl/', params=args)

        if page == 'all':
            page = 0

        if count:
            page = 1

        if page < 1:
            output = _get_pages(1)
            total = output['page_total']
            for i in range(2, total + 1):
                data = _get_pages(i)
                output['acls'].extend(data['acls'])
        else:
            output = _get_pages(page)

        return output

    def get_packager_stats(self, packagername):
        ''' Return for the specified user, the number of packages on each
        active branch for which he/she is the point of contact.

        :arg packagername: The FAS username of the user for which to
            retrieve the statistics
        :type packagername: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'packagername': packagername,
        }

        return self.handle_api_call('/packager/stats/', params=args)

    def get_packagers(self, pattern='*'):
        ''' Return the list of packagers matching the provided criterias.

        Only packagers having at least commit right on one package are
        returned (on the contrary to querying
        `FAS <https://admin.fedorapoject.org/accounts>`_ for the members of
        the packager group).

        :kwarg pattern: The pattern to query the usernames of the packager
        :type pattern: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pattern': pattern,
        }

        return self.handle_api_call('/packagers/', params=args)


    def get_packager_package(self, packager, branches=None):
        ''' Return the list of packages related to the specified packager.

        The list of packages is split into three categories:
            point of contact, co-maintained, watch
        These are the same three categories used in the packager's page in
        the pkgdb2 UI.

        :arg packager: The name the packager to query the packages of
        :type pattern: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'packagername': packager,
        }

        if branches:
            args['branches'] = branches

        return self.handle_api_call('/packager/package/', params=args)

    def get_packages(
            self, pattern='*', branches=None, poc=None, status=None,
            orphaned=False, critpath=None, acls=False, eol=False,
            page=1, count=False):
        ''' Return the list of packages matching the provided criterias.

        To get information about what packages a person has acls on, you
        also need to call ``get_packager_acls``.

        :kwarg pattern: The pattern to match against the name of the
            packages
        :type pattern: str
        :kwarg branches: One or more branches to restrict the packages
            returned
        :type branches: str or list or None
        :kwarg poc: The point of contact of the packages to filter the
            packages returned
        :type poc: str or None
        :kwarg status: The status of the package to filter the packages
            returned, options are: ``Approved``, ``Orphaned``, ``Removed``,
            ``Retired``
        :type status: str or list or None
        :kwarg orphaned: A boolean to returned only orphaned packages
        :type orphaned: bool
        :kwarg critpath: A boolean to returned only packages in the critical
            path. Can be ``True``, ``False`` or ``None``.
            Defaults to ``None``.
        :type critpath: bool
        :kwarg acls: A boolean to return the package ACLs in the output.
            Beware, this may slow down you call considerably, maybe even
            leading to a timeout
        :type acls: bool
        :kwarg eol: a boolean to specify whether to include results for
            EOL collections or not. Defaults to ``False``.
            If True, it will return results for all collections (including
            EOL).
            If False, it will return results only for non-EOL collections.
        :type eol: boolean
        :kwarg page: The page number to retrieve. If page is 0 or lower or
            equal to ``all`` then all pages are returned. Defaults to 1.
        :type page: int or ``all``
        :kwarg count: A boolean to retrieve the count of ACLs the user has
            instead of the details. If count is True the page argument will
            be ignored
        :type count: bool
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        def _get_pages(page):
            ''' Retrieve a specified page of the packages list.

            :arg page: the page number to retrieve

            '''
            args = {
                'pattern': pattern,
                'branches': branches,
                'poc': poc,
                'status': status,
                'page': page,
            }
            if count is True:
                args['count'] = count
            if acls is True:
                args['acls'] = acls
            if orphaned is True:
                args['orphaned'] = orphaned
            if critpath is True:
                args['critpath'] = 1
            elif critpath is False:
                args['critpath'] = 0
            if eol is True:
                args['eol'] = eol

            return self.handle_api_call('/packages/', params=args)

        if page == 'all':
            page = 0

        if count:
            page = 1

        if page < 1:
            output = _get_pages(1)
            total = output['page_total']
            for i in range(2, total + 1):
                data = _get_pages(i)
                output['packages'].extend(data['packages'])
        else:
            output = _get_pages(page)

        return output

    def orphan_packages(self, pkgnames, branches):
        ''' Orphans the provided list of packages on the provided list of
        branches.

        :arg pkgnames: One or more package name of the packages to orphan
        :type pkgnames: str or list
        :arg branches: One or more branch names for the collections in
            which to orphan the packages
        :type branches: str or list
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgnames': pkgnames,
            'branches': branches,
        }

        return self.handle_api_call('/package/orphan/', data=args)

    def retire_packages(self, pkgnames, branches):
        ''' Retires the provided list of packages on the provided list of
        branches.

        :arg pkgnames: One or more package name of the packages to retire
        :type pkgnames: str or list
        :arg branches: One or more branch names for the collections in
            which to retire the packages
        :type branches: str or list
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgnames': pkgnames,
            'branches': branches,
        }

        return self.handle_api_call('/package/retire/', data=args)

    def unorphan_packages(self, pkgnames, branches, poc):
        ''' Un orphan the provided list of packages on the provided list of
        branches.

        :arg pkgname: One or more package name of the packages to unorphan
        :type pkgname: str or list
        :arg branches: One or more branch names for the collections in
            which to unorphan the packages
        :type branches: str or list
        :arg poc:
        :type poc: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgnames': pkgnames,
            'branches': branches,
            'poc': poc,
        }

        return self.handle_api_call('/package/unorphan/', data=args)

    def unretire_packages(self, pkgnames, branches):
        ''' Un retires the provided list of packages on the provided list of
        branches.

        :arg pkgnames: One or more package name of the packages to unretire
        :type pkgnames: str or list
        :arg branches: One or more branch names for the collections in
            which to unretire the packages
        :type branches: str or list
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgnames': pkgnames,
            'branches': branches,
        }

        return self.handle_api_call('/package/unretire/', data=args)

    def update_acl(self, pkgname, branches, acls, status, user):
        ''' Update the specified ACLs, on the specified Branches of the
        specified package.

        This method can also be used to request or set new ACLs on a
        package. For example if you want to requrest ACLs on a package or
        if you want to grant ACLs to someone.

        :arg pkgname: The package name of the package whom ACLs to update
        :type pkgname: str
        :arg branches: One or more branch for which to update their ACLs
        :type branches: str or list
        :arg acls: The ACL to update, options are: ``watchcommits``,
            ``watchbugzilla``, ``approveacls``, ``commit``
        :type acls: str or list
        :arg status: The status of the ACL to update, options are:
            ``Approved``, ``Awaiting Review``, ``Denied``, ``Obsolete``,
            ``Removed``
        :type status: str
        :arg user: The user for which to update the ACL (the person
            requesting new ACLs or for which to approve/deny the ACLs)
        :type user: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgname': pkgname,
            'branches': branches,
            'acl': acls,
            'acl_status': status,
            'user': user,
        }

        return self.handle_api_call('/package/acl/', data=args)

    def update_collection_status(self, branch, clt_status):
        ''' Update the status of the specified collection.

        :arg branch: The branch name of the collection for which to
            update the status
        :type branch: str
        :arg clt_status: The new status of the collection, options are:
            ``EOL``, ``Active``, ``Under Development``
        :type clt_status: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'branch': branch,
            'clt_status': clt_status,
        }

        return self.handle_api_call('/collection/{0}/status/'.format(branch),
                                    data=args)

    def update_package_poc(self, pkgnames, branches, poc):
        ''' Update the point of contact of the specified packages on the
        specified branches.

        :arg pkgnames: One or more package names of package for which to
            change the point of contact
        :type pkgnames: str or list
        :arg branches: One or more branch names for the collections for
            which to update the point of contact
        :type branches: str or list
        :arg poc:
        :type poc: str
        :return: the json object returned by the API
        :rtype: dict
        :raise PkgDBAuthException: if this method is called while the
            client is not authenticated.
        :raise PkgDBException: if the API call does not return a http code
            200.

        '''
        args = {
            'pkgnames': pkgnames,
            'branches': branches,
            'poc': poc,
        }
        return self.handle_api_call('/package/acl/reassign/', data=args)

    def get_version(self):
        ''' Return a tuple of the pkgdb API version.

        :return: the pkgdb API version
        :rtype: tuple
        :raise PkgDBException: if the API call does not return a http code
            200.

        Example of data returned

        ::

            (1, 6)

        '''
        version = self.handle_api_call('/version')
        if not 'version' in version:
            raise PkgDBException(
                'No version information could be retrieved')
        version = version['version']
        output = []
        for el in version.split('.'):
            try:
                el = int(el)
            except ValueError:
                pass
            output.append(el)

        return tuple(output)
