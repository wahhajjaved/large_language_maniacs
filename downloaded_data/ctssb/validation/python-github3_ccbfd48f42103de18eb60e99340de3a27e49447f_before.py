#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from pygithub3.core.client import Client
from pygithub3.core.result import Result
from pygithub3.requests import Factory
from pygithub3.core.errors import NotFound


class Base(object):

    def __init__(self, **config):
        self._client = Client(**config)
        self.make_request = Factory()

    def get_user(self):
        return self._client.user

    def set_user(self, user):
        self._client.user = user

    def get_repo(self):
        return self._client.repo

    def set_repo(self, repo):
        self._client.repo = repo

    def set_credentials(self, login, password):
        self._client.set_credentials(login, password)

    def set_token(self, token):
        self._client.set_token(token)

    def _bool(self, request, **kwargs):
        try:
            self._client.head(request, **kwargs)
            return True
        except NotFound:
            return False

    def _patch(self, request, **kwargs):
        input_data = request.get_body()
        response = self._client.patch(request, data=input_data, **kwargs)
        return request.resource.loads(response.content)

    def _put(self, request, **kwargs):
        """ Bug in Github API? requests library?

        I must send data as empty string when the specifications' of some PUT
        request are 'Not send input data'. If I don't do that and send data as
        None, the requests library doesn't send 'Content-length' header and the
        server returns 411 - Required Content length (at least 0)

        For instance:
            - follow-user request doesn't send input data
            - merge-pull request send data

        For that reason I must do a conditional because I don't want to return
        an empty string on follow-user request because it could be confused

        Related: https://github.com/github/developer.github.com/pull/52
        """
        input_data = request.get_body() or ''
        response = self._client.put(request, data=input_data, **kwargs)
        if response.status_code != '204':  # != NO_CONTENT
            return request.resource.loads(response.content)

    def _delete(self, request, **kwargs):
        input_data = request.get_body()
        self._client.delete(request, data=input_data, **kwargs)

    def _post(self, request, **kwargs):
        input_data = request.get_body()
        response = self._client.post(request, data=input_data, **kwargs)
        return request.resource.loads(response.content)

    def _get(self, request, **kwargs):
        response = self._client.get(request, **kwargs)
        return request.resource.loads(response.content)

    def _get_result(self, request, **kwargs):
        return Result(self._client, request, **kwargs)
