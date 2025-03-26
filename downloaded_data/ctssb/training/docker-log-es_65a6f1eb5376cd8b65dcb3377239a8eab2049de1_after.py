#!/usr/bin/env python
# encoding: utf-8
import socket
from os import environ as env
from tornado.netutil import Resolver
from tornado import gen
from tornado.httpclient import AsyncHTTPClient


class UnixResolver(Resolver):

    def initialize(self, resolver):
        self.resolver = resolver

    def close(self):
        self.resolver.close()

    @gen.coroutine
    def resolve(self, host, port, *args, **kwargs):

        scheme, path = Storage.DOCKER.split('://')
        if host == 'docker':

            if scheme == 'unix':
                raise gen.Return([(socket.AF_UNIX, path)])

            elif scheme == 'tcp' or scheme == 'http':
                t = path.split(":")
                if len(t) > 1:
                    host, port = t
                    port = int(port)
                else:
                    host, port = t[0], 80

        result = yield self.resolver.resolve(host, port, *args, **kwargs)
        raise gen.Return(result)


AsyncHTTPClient.configure(
    None,
    resolver=UnixResolver(resolver=Resolver()),
    max_clients=20000
)


class Storage(object):
    CONTAINERS = set([])
    DOCKER = env.get('DOCKER_HOST', 'unix:///var/run/docker.sock')
    ELASTICSEARCH = env.get('ELASTICSEARCH', 'http://127.0.0.1:9200')
    http = AsyncHTTPClient()
