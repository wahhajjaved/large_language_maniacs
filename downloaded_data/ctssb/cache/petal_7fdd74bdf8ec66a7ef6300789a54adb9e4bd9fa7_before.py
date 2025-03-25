# -*- coding: utf-8 -*-

from flask import request, redirect

YEAR_IN_SECS = 31536000


class SSLify(object):
    """Secures your Flask App."""

    def __init__(self, app, age=YEAR_IN_SECS, subdomains=False, permanent=False,exluded=False):
        if app is not None:
            self.app = app
            self.hsts_age = age
            self.hsts_include_subdomains = subdomains
            self.permanent = permanent
            self.exluded = exluded

            self.init_app(self.app)
        else:
            self.app = None

    def init_app(self, app):
        """Configures the configured Flask app to enforce SSL."""
        app.before_request(self.redirect_to_ssl)
        app.after_request(self.set_hsts_header)

    @property
    def hsts_header(self):
        """Returns the proper HSTS policy."""
        hsts_policy = 'max-age={0}'.format(self.hsts_age)

        if self.hsts_include_subdomains:
            hsts_policy += '; includeSubDomains'

        return hsts_policy

    def redirect_to_ssl(self):
        """Redirect incoming requests to HTTPS."""
        # Should we redirect?
        criteria = [
            request.is_secure,
            not(self.app.debug), #CHANGE!
            request.headers.get('X-Forwarded-Proto', 'http') == 'https'
        ]
        #TODO this is probable not the best way to do this
        print('request.url: ',request.url)
        print('self.exluded: ', self.exluded)
        print('url and exult not in url: ', request.url.startswith('http://') and self.exluded not in request.url)
        if not self.exluded:
            if not any(criteria):
                if request.url.startswith('http://'): #my addition, prob has some security flaw
                    url = request.url.replace('http://', 'https://', 1)
                    code = 302
                    if self.permanent:
                        code = 301
                    r = redirect(url, code=code)

                    return r
        else:
            if not any(criteria):
                if request.url.startswith('http://') and self.exluded not in request.url: #my addition, prob has some security flaw
                    print('**************')
                    url = request.url.replace('http://', 'https://', 1)
                    code = 302
                    if self.permanent:
                        code = 301
                    r = redirect(url, code=code)

                    return r

    def set_hsts_header(self, response):
        """Adds HSTS header to each response."""
        response.headers.setdefault('Strict-Transport-Security', self.hsts_header)
        return response
