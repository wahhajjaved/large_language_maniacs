import os
import posixpath

from flask import current_app, Response
from flask import _app_ctx_stack as stack

import sass


class Sass(object):
    _output_styles = {
        'nested': sass.SASS_STYLE_NESTED,
        'expanded': sass.SASS_STYLE_EXPANDED,
        'compact': sass.SASS_STYLE_COMPACT,
        'compressed': sass.SASS_STYLE_COMPRESSED,
    }

    def __init__(self, files, app=None,
                 url_path='/css', endpoint='sass',
                 include_paths=None, output_style=None):
        self._files = files
        self._url_path = url_path
        self._endpoint = endpoint
        self._include_paths = ','.join(include_paths).encode()
        self._output_style = self._output_styles.get(
            output_style, sass.SASS_STYLE_NESTED
        )

        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.add_url_rule(
            posixpath.join(self._url_path, '<path:filename>.css'),
            endpoint=self._endpoint,
            view_func=self.send_css
        )

    def compile(self, filename):
        input_file = os.path.join(
            current_app.root_path,
            self._files[filename]
        ).encode()

        return sass.compile_file(
            input_file,
            include_paths=self._include_paths,
            output_style=self._output_style
        )

    def send_css(self, filename):
        if filename not in self._files:
            raise NotFound()

        rebuild = current_app.config.get('SASS_REBUILD', False)

        if rebuild:
            if not hasattr(stack.top, 'sass_cache'):
                stack.top.sass_cache = {}
            cache = stack.top.sass_cache

            if filename not in cache:
                cache[filename] = self.compile(filename)
            css = cache[filename]
        else:
            css = self.compile(filename)

        return Response(css, content_type='text/css')
