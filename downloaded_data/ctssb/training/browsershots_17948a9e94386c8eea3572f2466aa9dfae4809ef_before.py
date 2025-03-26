# browsershots.org - Test your web design in different browsers
# Copyright (C) 2007 Johann C. Rocholl <johann@browsershots.org>
#
# Browsershots is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Browsershots is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
URL input form.
"""

__revision__ = "$Rev$"
__date__ = "$Date$"
__author__ = "$Author$"

import re
import urlparse
import socket
from datetime import datetime
from psycopg import IntegrityError
from django import newforms as forms
from django.utils.text import capfirst
from django.db import transaction
from django.newforms.util import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from shotserver04.websites.utils import \
     split_netloc, unsplit_netloc, http_get, count_profanities, \
     HTTP_TIMEOUT, HTTPError, ConnectError, RequestError, \
     dotted_ip, long_ip, bit_mask, slash_mask
from shotserver04.websites.models import Domain, Website
from shotserver04.websites import normalize_url

SUPPORTED_SCHEMES = ['http', 'https']

scheme_match = re.compile(r'[A-Za-z0-9\.+-]+:').match


class UrlForm(forms.Form):
    """
    URL input form.
    """
    url = forms.CharField(
        max_length=Website._meta.get_field('url').max_length,
        label=_("Enter your web address here:"))

    def clean_url(self):
        """
        Clean URL and attempt HTTP GET request.
        """
        self.cleaned_data['url'] = normalize_url(self.cleaned_data['url'])
        self.add_scheme()
        self.split_url()
        self.punycode_url()
        self.check_server_ip()
        self.add_slash()
        self.cleaned_data['content'] = self.http_get()
        self.cleaned_data['profanities'] = count_profanities(
            settings.PROFANITIES_LIST,
            self.cleaned_data['url'] + ' ' + self.cleaned_data['content'])
        self.cleaned_data['domain'] = self.get_or_create_domain()
        self.cleaned_data['website'] = self.get_or_create_website()
        return self.cleaned_data['url']

    def add_scheme(self):
        """
        Add http:// if it's missing.
        """
        url = self.cleaned_data['url']
        if not scheme_match(url):
            self.cleaned_data['url'] = 'http://' + url.lstrip('/')

    def split_url(self):
        """
        Parse URL into components.
        """
        url = self.cleaned_data['url']
        self.url_parts = list(urlparse.urlsplit(url, 'http'))
        # print self.url_parts
        if self.url_parts[0] not in SUPPORTED_SCHEMES:
            raise ValidationError(
                unicode(_("URL scheme %(scheme)s is not supported.") %
                        {'scheme': self.url_parts[0]}))
        self.netloc_parts = split_netloc(self.url_parts[1])
        if not self.url_parts[1] or not self.netloc_parts[2]:
            raise ValidationError(
                unicode(_("Malformed URL (server name not specified).")))
        # print self.netloc_parts

    def punycode_url(self):
        """
        Convert url to punycode if necessary.
        """
        hostname = original = self.netloc_parts[2]
        while '..' in hostname:
            hostname = hostname.replace('..', '.')
        punycode = hostname.encode('idna').decode('ascii')
        if punycode == original:
            return
        self.netloc_parts[2] = punycode
        self.url_parts[1] = unsplit_netloc(self.netloc_parts)
        self.cleaned_data['url'] = urlparse.urlunsplit(self.url_parts)
        # print self.cleaned_data['url']

    def check_server_ip(self):
        """
        Check if server IP is disallowed in settings.py.
        """
        try:
            hostname = self.netloc_parts[2]
            ip = socket.gethostbyname(hostname)
        except socket.error:
            raise ValidationError(unicode(
                _("Could not resolve IP address for %(hostname)s.") %
                locals()))
        if (not hasattr(settings, DISALLOWED_SERVER_IP_LIST) or
            not settings.DISALLOWED_SERVER_IP_LIST):
            return
        server = long_ip(ip)
        # print 'server', server, dotted_ip(server), ip
        for disallowed in settings.DISALLOWED_SERVER_IP_LIST:
            mask = bit_mask(32)
            if '/' in disallowed:
                disallowed, bits = disallowed.split('/', 1)
                mask = slash_mask(int(bits))
            identifier = long_ip(disallowed) & mask
            masked = server & mask
            if masked == identifier:
                raise ValidationError(unicode(
                    _("Server IP address %(ip)s is disallowed.") % locals()))

    def add_slash(self):
        """
        Add slash after hostname if it's missing.
        """
        if not self.url_parts[2]: # path
            self.url_parts[2] = '/'
            self.cleaned_data['url'] = urlparse.urlunsplit(self.url_parts)

    def http_get(self):
        """
        Load page content from remote HTTP server.
        """
        try:
            return http_get(self.cleaned_data['url'])
        except HTTPError, error:
            if isinstance(error, ConnectError):
                text = _("Could not connect to %(hostname)s.")
            elif isinstance(error, RequestError):
                text = _("Could not send HTTP request to %(hostname)s.")
            else:
                text = _("Could not get page content from %(hostname)s.")
            text %= {'hostname': error.hostname}
            if error.message == 'timed out':
                error.message = (
                    _("Server failed to respond within %d seconds.") %
                    HTTP_TIMEOUT)
            elif error.message:
                error.message = capfirst(error.message).rstrip('.') + '.'
            raise ValidationError(' '.join((text, error.message)).strip())

    def get_or_create_domain(self):
        """
        Get or create domain entry in database.
        """
        domain_name = self.netloc_parts[2] # hostname
        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]
        transaction.commit() # Because we may need to call rollback below.
        try:
            domain, created = Domain.objects.get_or_create(name=domain_name)
        except IntegrityError, error:
            if 'duplicate key' in str(error):
                transaction.rollback()
                domain = Domain.objects.get(name=domain_name)
            else:
                raise
        return domain

    def get_or_create_website(self):
        """
        Get or create website entry in database.
        """
        defaults = {}
        defaults['domain'] = self.cleaned_data['domain']
        # defaults['content'] = self.cleaned_data['content']
        defaults['profanities'] = self.cleaned_data['profanities']
        transaction.commit() # Because we may need to call rollback below.
        try:
            website, created = Website.objects.get_or_create(
                url=self.cleaned_data['url'], defaults=defaults)
        except IntegrityError, error:
            if 'duplicate key' in str(error):
                transaction.rollback()
                website = Website.objects.get(url=self.cleaned_data['url'])
                created = False
            elif 'websites_website_url_check' in str(error):
                transaction.rollback()
                raise ValidationError(
                    unicode(_("Malformed URL (database integrity error).")))
            else:
                raise
        # Update content cache
        if not created:
            website.update_fields(
                profanities=self.cleaned_data['profanities'],
                fetched=datetime.now())
        return website
