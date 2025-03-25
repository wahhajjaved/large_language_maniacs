import asyncio
import hashlib
import json
import logging
import os
import time
import traceback
from dataclasses import dataclass
from email.utils import formatdate
from io import BytesIO
from types import FunctionType
from typing import Dict, Any, TYPE_CHECKING, Sequence, Optional, Iterable
from mimetypes import guess_type

import aiofiles
from aiofiles.os import stat as aio_stat
from multipart import multipart

from slim.base import const
from slim.base.types.route_meta_info import RouteStaticsInfo
from slim.utils import async_call
from slim.utils.types import Receive, Send

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from slim import Application


class FileField:
    def __init__(self, field: multipart.File):
        self._field = field
        field.file_object.seek(0)

    @property
    def field_name(self):
        return self._field.field_name

    @property
    def file_name(self):
        return self._field.file_name

    @property
    def file(self):
        return self._field.file_object

    @property
    def size(self):
        return self._field.size


@dataclass
class CORSOptions:
    host: str
    allow_credentials: bool = False
    expose_headers: Optional[Sequence] = None
    allow_headers: Sequence = ()
    max_age: Optional[int] = None
    allow_methods: Optional[Sequence] = None

    def pack_headers(self, origin):
        def solve(val):
            if isinstance(val, str):
                return val
            elif isinstance(val, Iterable):
                return ','.join(val)

        headers = {
            const.ACCESS_CONTROL_ALLOW_ORIGIN: origin,
            const.ACCESS_CONTROL_ALLOW_CREDENTIALS: b'true' if self.allow_credentials else b'false'
        }
        if self.expose_headers:
            headers[const.ACCESS_CONTROL_EXPOSE_HEADERS] = solve(self.expose_headers)
        if self.allow_headers:
            headers[const.ACCESS_CONTROL_ALLOW_HEADERS] = solve(self.allow_headers)
        if self.max_age:
            headers[const.ACCESS_CONTROL_MAX_AGE] = self.max_age
        if self.allow_methods:
            headers[const.ACCESS_CONTROL_ALLOW_METHODS] = self.allow_methods
        return headers


@dataclass
class ASGIRequest:
    scope: Dict
    receive: FunctionType
    send: FunctionType

    origin: Optional[str] = None

    def __post_init__(self):
        for k, v in self.scope['headers']:
            if k == b'origin':
                self.origin = v
                break


@dataclass
class Response:
    status: int = 200
    body: str = None
    headers: Dict[str, Any] = None
    content_type: str = 'text/plain'
    cookies: Dict[str, Dict] = None

    async def get_body(self) -> bytes:
        if isinstance(self, JSONResponse):
            body = self.json_dumps(self.body)
        else:
            body = self.body
        if isinstance(body, str):
            return body.encode('utf-8')
        return body

    def build_headers(self):
        headers = [
            # TODO: bytes convert cache
            [const.CONTENT_TYPE.encode('utf-8'), self.content_type.encode('utf-8')]
         ]

        if self.cookies:
            set_cookie = const.SET_COOKIE.encode('utf-8')
            for k, v in self.cookies.items():
                value = f"{v['name']}={v['value']}"

                if 'expires' in v:
                    value += f"; Expires={v['expires']}"

                if 'max-age' in v:
                    value += f"; Max-Age={v['max-age']}"

                if 'domain' in v:
                    value += f"; Domain={v['domain']}"

                if 'path' in v:
                    value += f"; Path={v['path']}"

                if v.get('secure'):
                    value += f"; Secure"

                if v.get('httponly'):
                    value += f"; HttpOnly"

                headers.append([set_cookie, value.encode('utf-8')])

        if self.headers:
            for k, v in self.headers.items():
                headers.append([k, v])

        headers_new = []
        for a, b in headers:
            if not isinstance(a, bytes):
                a = str(a).encode('utf-8')
            if not isinstance(b, bytes):
                b = str(b).encode('utf-8')
            headers_new.append([a, b])

        return headers_new

    async def __call__(self, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": self.headers,
            }
        )
        await send({"type": "http.response.body", "body": self.body})


@dataclass
class JSONResponse(Response):
    body: Dict[str, Any] = None
    content_type: str = 'application/json'
    json_dumps: FunctionType = json.dumps


@dataclass
class FileResponse(Response):
    chunk_size = 4096

    def __init__(
            self,
            path: str,
            headers: dict = {},
            content_type: str = None,
            filename: str = None,
            stat_result: os.stat_result = None,
    ) -> None:
        assert aiofiles is not None, "'aiofiles' must be installed to use FileResponse"
        self.path = path
        self.status = 200
        self.filename = filename
        if content_type is None:
            content_type = guess_type(filename or path)[0] or "text/plain"
        self.content_type = content_type
        self.headers = headers
        if self.filename is not None:
            content_disposition = 'attachment; filename="{}"'.format(self.filename)
            self.headers.setdefault("content-disposition", content_disposition)
        self.stat_result = stat_result
        if stat_result is not None:
            self.set_stat_headers(stat_result)

    def set_stat_headers(self, stat_result):
        content_length = str(stat_result.st_size)
        last_modified = formatdate(stat_result.st_mtime, usegmt=True)
        etag_base = str(stat_result.st_mtime) + "-" + str(stat_result.st_size)
        etag = hashlib.md5(etag_base.encode()).hexdigest()
        self.headers.setdefault("content-length", content_length)
        self.headers.setdefault("last-modified", last_modified)
        self.headers.setdefault("etag", etag)

    async def __call__(self, receive: Receive, send: Send) -> None:
        if self.stat_result is None:
            stat_result = await aio_stat(self.path)
            self.set_stat_headers(stat_result)
        if isinstance(self.headers, dict):
            self.headers = [[k, v] for k, v in self.headers.items()]
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": self.headers,
            }
        )
        async with aiofiles.open(self.path, mode="rb") as file:
            more_body = True
            while more_body:
                chunk = await file.read(self.chunk_size)
                more_body = len(chunk) == self.chunk_size
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": more_body,
                    }
                )


async def handle_request(app: 'Application', scope, receive, send):
    """
    Handle http request
    :param app:
    :param scope:
    :param receive:
    :param send:
    :return:
    """
    from ._view.abstract_sql_view import AbstractSQLView
    from ._view.validate import view_validate_check

    if scope['type'] == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                try:
                    app.prepare()
                    for func in app.on_startup:
                        await async_call(func)
                    await send({'type': 'lifespan.startup.complete'})
                except Exception:
                    traceback.print_exc()
                    await send({'type': 'lifespan.startup.failed'})
                    return

            elif message['type'] == 'lifespan.shutdown':
                for func in app.on_shutdown:
                    await async_call(func)

                await send({'type': 'lifespan.shutdown.complete'})
                return

    try:
        if scope['type'] == 'http':
            request = ASGIRequest(scope, receive, send)
            resp = None

            if scope['method'] == 'OPTIONS':
                # Configure CORS settings.
                if app.cors_options:
                    # TODO: host match
                    for i in app.cors_options:
                        i: CORSOptions
                        resp = Response(headers=i.pack_headers(request.origin))
            else:
                _route_info, call_kwargs_raw_ = app.route.query_statics_path(scope['method'], scope['path'])
                if isinstance(_route_info, RouteStaticsInfo):
                    file_ = _route_info.handler(scope)
                    await file_(receive, send)

                route_info, call_kwargs_raw = app.route.query_path(scope['method'], scope['path'])

                if route_info:
                    t = time.perf_counter()

                    # filter call_kwargs
                    call_kwargs = call_kwargs_raw.copy()
                    if route_info.names_varkw is not None:
                        for j in route_info.names_exclude:
                            del call_kwargs[j]

                    for j in call_kwargs.keys() - route_info.names_include:
                        del call_kwargs[j]

                    # build a view instance
                    view = await route_info.view_cls._build(app, request)
                    view._route_info = call_kwargs
                    if isinstance(view, AbstractSQLView):
                        view.current_interface = route_info.builtin_interface

                    # make the method bounded
                    handler = route_info.handler.__get__(view)

                    # note: view.prepare() may case finished
                    if not view.is_finished:
                        # user's validator check
                        await view_validate_check(view, route_info.va_query, route_info.va_post, route_info.va_headers)

                        if not view.is_finished:
                            # call the request handler
                            if asyncio.iscoroutinefunction(handler):
                                await handler(**call_kwargs)
                            else:
                                handler(**call_kwargs)

                    took = round((time.perf_counter() - t) * 1000, 2)
                    # GET /api/get -> TopicView.get 200 30ms
                    name = handler.__name__
                    logger.info("{} {:4s} -> {} {}, took {}ms".format(view.method, view.path, name, 200, took))

                    # if status_code == 500:
                    #     warn_text = "The handler {!r} did not called `view.finish()`.".format(handler_name)
                    #     logger.warning(warn_text)
                    #     view_instance.finish_raw(warn_text.encode('utf-8'), status=500)
                    #     return resp
                    #
                    # await view_instance._on_finish()

                    if view.response:
                        resp = view.response
            if resp:
                body = await resp.get_body()

                # Configure CORS settings.
                if app.cors_options:
                    # TODO: host match
                    for i in app.cors_options:
                        i: CORSOptions
                        if resp.headers:
                            resp.headers.update(i.pack_headers(request.origin))
                        else:
                            resp.headers = i.pack_headers(request.origin)

                headers = resp.build_headers()
                # [[b'Content-Length', str(len(body)).encode('utf-8')]]

                await send({
                    'type': 'http.response.start',
                    'status': resp.status,
                    'headers': headers
                })

                await send({
                    'type': 'http.response.body',
                    'body': body,
                })
                return
            else:
                await send({
                    'type': 'http.response.start',
                    'status': 404,
                    'headers': [
                        [b'content-type', b'text/plain'],
                    ]
                })

                await send({
                    'type': 'http.response.body',
                    'body': b'not found',
                })
    except Exception as e:
        traceback.print_exc()
