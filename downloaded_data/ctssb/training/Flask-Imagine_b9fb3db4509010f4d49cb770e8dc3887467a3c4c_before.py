from __future__ import division

import os
import errno
from PIL import Image
from boto.s3.connection import S3Connection
from flask import current_app, request, abort, redirect
from urllib import quote as urlquote

from . import modes
from .exception import ParameterNotFound, FilterNotFound, OriginalKeyDoesNotExist
from .size import ImageSize
from .transform import Transform


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


class Imagine(object):
    filters = {}
    s3_conn = None
    bucket = None

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        app.extensions['imagine'] = self

        app.config.setdefault('IMAGINE_URL', '/media/cache/resolve')
        app.config.setdefault('IMAGINE_NAME', 'imagine')
        app.config.setdefault('IMAGINE_TYPE', 's3') # s3 or filesystem
        app.config.setdefault('IMAGINE_THUMBS_PATH', 'cache')
        app.config.setdefault('IMAGINE_CACHE', '/tmp/flask-imagine')

        if app.config['IMAGINE_TYPE'] == 's3':
            if 'IMAGINE_S3_ACCESS_KEY' not in app.config \
                    or 'IMAGINE_S3_SECRET_KEY' not in app.config \
                    or 'IMAGINE_S3_BUCKET' not in app.config:
                raise ParameterNotFound(code=101, msg='S3 credentials has been not present')

        self.s3_conn = S3Connection(app.config['IMAGINE_S3_ACCESS_KEY'], app.config['IMAGINE_S3_SECRET_KEY'])
        self.bucket = self.s3_conn.get_bucket(app.config['IMAGINE_S3_BUCKET'])

        if 'IMAGINE_FILTERS' not in app.config:
            raise ParameterNotFound(code=102, msg='Filters configuration has been not present')

        self.filters = self._prepare_filters(app.config['IMAGINE_FILTERS'])

        app.add_url_rule(app.config['IMAGINE_URL'] + '/<regex("[^\/]+"):filter_name>/<path:path>', app.config['IMAGINE_NAME'], self.handle_request)

        if hasattr(app, 'add_template_filter'):
            app.add_template_filter(imagine_filter, 'imagine_filter')
        else:
            ctx = {
                'imagine_filter': imagine_filter
            }
            app.context_processor(lambda: ctx)

    @staticmethod
    def _prepare_filters(filters_config):
        """
        Filters validation
        :param filters_config: dict
        :return: dict
        """
        # todo: Must be realized in the future
        return filters_config

    def build_url(self, path, filter_name, **kwargs):
        if filter_name not in self.filters:
            raise FilterNotFound(code=201, msg='Filter %s has been not found in config' % filter_name)

        makedirs(current_app.config['IMAGINE_CACHE'])

        cached_key = self.bucket.get_key(current_app.config['IMAGINE_THUMBS_PATH'] + '/' + filter_name + '/' + path)

        if cached_key is not None:
            return cached_key.generate_url(expires_in=0, query_auth=False)
        else:
            original_key = self.bucket.get_key(path)
            if original_key is not None:
                external = kwargs.pop('external', None) or kwargs.pop('_external', None)
                scheme = kwargs.pop('scheme', None)
                if scheme and not external:
                    raise ValueError('cannot specify scheme without external=True')

                url = '%s/%s/%s' % (
                    current_app.config['IMAGINE_URL'],
                    urlquote(filter_name),
                    urlquote(path),
                )

                if external:
                    url = '%s://%s%s/%s' % (
                        scheme or request.scheme,
                        request.host,
                        request.script_root,
                        url.lstrip('/')
                    )

                return url
            elif 'default_image_path' in self.filters[filter_name]:
                return self.filters[filter_name]['default_image_path']
            else:
                raise OriginalKeyDoesNotExist(code=404,
                                              msg='Original key <%s> does not exist in bucket: %s' % (
                                                  path,
                                                  self.bucket.name
                                              ))

    def handle_request(self, filter_name, path):
        if filter_name not in self.filters:
            abort(404)
        original_key = self.bucket.get_key(path)

        if 'filter' in self.filters[filter_name]:
            if self.filters[filter_name]['filter'] == 'scale':
                return self._scale(original_key, filter_name)
        else:
            raise ParameterNotFound(code=202, msg='Filter type for <%s> has been not present' % filter_name)

    def find_img(self, local_path):
        local_path = os.path.normpath(local_path.lstrip('/'))
        for path_base in current_app.config['IMAGES_PATH']:
            path = os.path.join(current_app.root_path, path_base, local_path)
            if os.path.exists(path):
                return path

    def calculate_size(self, path, **kw):
        return ImageSize(path=self.find_img(path), **kw)

    @classmethod
    def scale_sizes(cls, original_width, original_height, target_width, target_height):
        if target_width > original_width and target_height > original_height:
            target_width = original_width
            target_height = original_height
        elif target_width <= original_width and target_height > original_height:
            k = original_width / original_height
            target_height = int(target_width / k)
        elif target_width > original_width and target_height <= original_height:
            k = original_width / original_height
            target_width = target_height * k

        return target_width, target_height

    def _scale(self, original_key, filter_name):
        local_directory = current_app.config['IMAGINE_CACHE'] + '/' + filter_name + \
                          '/' + os.path.dirname(original_key.name)
        makedirs(local_directory)
        local_file_path = current_app.config['IMAGINE_CACHE'] + '/' + filter_name + '/' + original_key.name
        original_key.get_contents_to_filename(local_file_path)

        image = Image.open(local_file_path)

        target_width = self.filters[filter_name]['width']
        target_height = self.filters[filter_name]['height']

        if 'scale_sizes' not in self.filters[filter_name] or self.filters[filter_name]['scale_sizes']:
            original_width, original_height = image.size
            target_width, target_height = self.scale_sizes(original_width, original_height, target_width, target_height)

        image = self.resize(image,
                            height=target_height,
                            mode='fit',
                            width=target_width)

        format = (os.path.splitext(local_file_path)[1][1:] or 'jpeg').lower()
        format = {'jpg': 'jpeg'}.get(format, format)

        cache_file_path = current_app.config['IMAGINE_CACHE'] + '/' + filter_name + '/' + \
                          os.path.dirname(original_key.name) + '/c_' + os.path.basename(original_key.name)
        cache_file = open(cache_file_path, 'wb')
        image.save(cache_file, format, quality=85)
        cache_file.close()

        cached_key = self.bucket.new_key(current_app.config['IMAGINE_THUMBS_PATH'] + '/' + filter_name + '/' +
                                         original_key.name)
        cached_key.set_contents_from_filename(cache_file_path)
        cached_key.make_public()

        os.remove(local_file_path)
        os.remove(cache_file_path)

        return redirect(cached_key.generate_url(expires_in=0, query_auth=False), code=301)

    def resize(self, image, background=None, **kw):

        size = ImageSize(image=image, **kw)

        # Get into the right colour space.
        if not image.mode.upper().startswith('RGB'):
            image = image.convert('RGBA')

        # Apply any requested transform.
        if size.transform:
            image = Transform(size.transform, image.size).apply(image)

        # Handle the easy cases.
        if size.mode in (modes.RESHAPE, None) or size.req_width is None or size.req_height is None:
            return image.resize((size.width, size.height), Image.ANTIALIAS)

        if size.mode not in (modes.FIT, modes.PAD, modes.CROP):
            raise ValueError('unknown mode %r' % size.mode)

        if image.size != (size.op_width, size.op_height):
            image = image.resize((size.op_width, size.op_height), Image.ANTIALIAS)

        if size.mode == modes.FIT:
            return image

        elif size.mode == modes.PAD:
            pad_color = str(background or 'black')
            padded = Image.new('RGBA', (size.width, size.height), pad_color)
            padded.paste(image, (
                (size.width - size.op_width) // 2,
                (size.height - size.op_height) // 2
            ))
            return padded

        elif size.mode == modes.CROP:

            dx = (size.op_width - size.width) // 2
            dy = (size.op_height - size.height) // 2
            return image.crop(
                (dx, dy, dx + size.width, dy + size.height)
            )

        else:
            raise RuntimeError('unhandled mode %r' % size.mode)


def imagine_filter(path, filter_name, **kwargs):
    self = current_app.extensions['imagine']
    return self.build_url(path, filter_name, **kwargs)
