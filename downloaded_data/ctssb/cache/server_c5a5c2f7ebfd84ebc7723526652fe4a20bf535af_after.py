from pyramid.view import (
    view_config,
    view_defaults,
    forbidden_view_config
)

from pyramid.response import Response
from pyramid.httpexceptions import (
    HTTPOk,
    HTTPNotFound,
    HTTPForbidden,
    HTTPFound
)

from pyramid.security import (
    remember,
    forget,
)

from argux_server.util import (
    TIMESPAN_EXPR,
)

import json

from . import BaseView


class MainViews(BaseView):

    @forbidden_view_config(
        accept='text/html'
    )
    def forbidden_view(self):
        if self.request.authenticated_userid:
            return HTTPForbidden()

        url = self.request.route_url(
            'login',
            _query=(('next', self.request.path),))
        return HTTPFound(location=url)

    @forbidden_view_config(
        accept='application/json',
        renderer='json'
    )
    def json_forbidden_view(self):
        return HTTPForbidden()

    @view_config(
        route_name='login',
        renderer='templates/login.pt',
    )
    def login_html(self):
        session = self.request.session
        if self.request.method == "POST":
            username = self.request.params['username']
            password = self.request.params['password']

            if self.dao.user_dao.validate_user(username, password):
                session['username'] = username

                headers = remember(self.request, username)

                url = self.request.params.get('next', None)
                if url is None:
                    url = self.request.route_url('home')

                response = HTTPFound(location=url)
                response.headerlist.extend(headers)

                return response
            return {}
        return {}

    @view_config(
        route_name='logout'
    )
    def logout(self):
        self.request.session.invalidate()

        headers = forget(self.request)
        url = self.request.route_url('home')

        response = HTTPFound(location=url)
        response.headerlist.extend(headers)

        return response

    @view_config(
        route_name='profile',
        renderer='templates/profile.pt',
        permission='view'
    )
    def profile(self):
        return {
            "userid": self.request.authenticated_userid,
            }
