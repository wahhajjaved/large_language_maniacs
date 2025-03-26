# -*- coding: utf-8 -*-
"""
flask_cacheobj.api
~~~~~~~~~~~~~~~

Support cache for Flask.

:copyright: (c) 2016 Liwushuo Inc.
:license: MIT, see LICENSE for more details.
"""

from flask import current_app

try:
    from flask import _app_ctx_stack as stack
except ImportError:
    from flask import _request_ctx_stack as stack

from .cache import cache_obj, cache_hash, cache_list, cache_counter, delete_obj
from .consts import __flask_extension_name__

class FlaskCacheOBJ(object):
    """Use redis as cache layer for Flask applications.

    Register it with::

        app = Flask(__name__)
        cache = FlaskCacheOBJ(app)

    Or::

        app = Flask(__name__)
        cache = FlaskCacheOBJ()
        cache.init_app(app)
    """

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.config.setdefault('CACHE_HOST', 'localhost')
        app.config.setdefault('CACHE_PORT', 6379)
        app.config.setdefault('CACHE_DB', 0)
        app.config.setdefault('CACHE_PREFIX', '')

        if not hasattr(app, 'extensions'):
            app.extensions = {}

        app.extensions.setdefault(__flask_extension_name__, self)

    def init_redis(self):
        host = current_app.config.get('CACHE_HOST')
        port = current_app.config.get('CACHE_PORT')
        db = current_app.config.get('CACHE_DB')
        prefix = current_app.config.get('CACHE_PREFIX')
        from .redis_client import RedisClient
        return RedisClient(
            host=host,
            port=port,
            db=db,
            key_prefix=prefix
        )

    @property
    def mc(self):
        """Redis instance used to cache value. Replace redis instance if you want.

        Usage::

            cache.mc = redis.StrictRedis()
        """
        ctx = stack.top
        if ctx is not None:
            if not hasattr(ctx, 'cache_redis'):
                ctx.cache_redis = self.init_redis()
            return ctx.cache_redis

    @mc.setter
    def mc(self, value):
        ctx = stack.top
        if ctx is not None:
            ctx.cache_redis = value

    def obj(self, *args, **kwargs):
        """A decorator that can cache object. Alias for `flask_cacheobj.cache.cache_obj`.

        Define cache strategy and decorate your function::

            ITEM = {
                'key': 'item:{item_id}',
                'expire': 86400,
            }

            @cache.obj(ITEM)
            def get_item(item_id):
                return Item.query.get(item_id)
        """
        return cache_obj(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """A decorator that can delete object after function executed. Alias for `flask_cacheobj.cache.delete_obj`.

        Define cache strategy and decorate your function::

            ITEM = {
                'key': 'item:{item_id}',
                'expire': 86400,
            }

            @cache.delete(ITEM)
            def update_item(item_id, attributes):
                return Item.query.get(item_id).update(**attributes)
        """
        return delete_obj(*args, **kwargs)

    def counter(self, *args, **kwargs):
        """A decorator that can cache counter. Alias for `flask_cacheobj.cache.cache_counter`.

        Define counter cache strategy and decorator your function::

            STAT = {
                'key': 'item:stat:{item_id}',
                'expire': 60,
            }

            @cache.counter(STAT)
            def get_item_stat(item_id):
                return ItemStat.query.filter_by(item_id).first()
        """
        return cache_counter(*args, **kwargs)

    def list(self, *args, **kwargs):
        """A decorator that can cache list. Alias for `flask_cacheobj.cache.cache_list`.

        Define list cache strategy and decorator your function::

            MEMBERS = {
                'key': 'item:members:{item_id}',
                'expire': 60,
            }

            @cache.counter(STAT)
            def get_item_members(item_id):
                members = ItemMember.query.filter_by(item_id).all()
                return [member.user_id for member in members]
        """
        return cache_list(*args, **kwargs)

    def hash(self, *args, **kwargs):
        """A decorator that can cache hash. Alias for `flask_cacheobj.cache.cache_hash`.

        Define hash cache strategy and decorator your function::

            ITEM_HASH = {
                'hash_key': 'item',
                'key': '{item_id}',
                'expire': 86400,
            }

            @cache.obj(ITEM)
            def get_item(item_id):
                return Item.query.get(item_id)
        """
        return cache_hash(*args, **kwargs)
