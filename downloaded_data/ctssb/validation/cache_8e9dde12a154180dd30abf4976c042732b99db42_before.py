import os
import functools
import inspect
import logging

import sqlitedict
import dill
from joblib import hash


def _hash(x):
    try:
        if callable(x):
            return _hash(x.__name__)
        else:
            return hash(dill.dumps(x))
    except dill.PicklingError:
        raise RuntimeError


def deep_hash(x):
    if isinstance(x, dict):
        k = _hash([(k, deep_hash(v)) for v, k in sorted(x.items())])
        return k
    elif isinstance(x, (tuple, list, set)):
        return _hash([deep_hash(xi) for xi in x])
    else:
        return _hash(x)


def _make_key(f, args, kwargs):
    kwargs.update(dict(zip(inspect.getargspec(f).args, args)))
    key = tuple(kwargs.get(k, None) for k in inspect.getargspec(f).args) + (f.__name__, )
    return deep_hash(key)


class CacheMixin(object):
    """To use this mixin, the following methods must be implemented:

    __getitem__
    __setitem__
    """

    def key(self, f, args, kwargs):
        return _make_key(f, args, kwargs)

    def __call__(self, f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            key = self.key(f, args, kwargs.copy())
            if key not in self:
                res = f(*args, **kwargs)
                self[key] = res
            return self[key]
        return wrapped

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False


class FileCache(CacheMixin):
    def __init__(self, path):
        self.path = path
        self.fname = lambda key: os.path.join(self.path, str(hash(dill.dumps(key))) + ".dill")

    def __getitem__(self, key):
        file_ = self.fname(key)
        if not os.path.exists(file_):
            raise KeyError
        with open(file_, 'rb') as f:
            result = dill.load(f)
        return result

    def __setitem__(self, key, value):
        with open(self.name(key), 'wb') as f:
            dill.dump(value, f)


class _Memoize(CacheMixin, dict):
    pass


def memoize(f):
    m =_Memoize()(f)
    return m


class DBCache(CacheMixin):
    def __init__(self, fname, tabname, buffer_size=5, silence=True):
        self.fname = "{}.sqlite".format(fname)
        self.tabname = tabname
        self.counter = 0
        self.buffer_size = buffer_size

        if silence:
            logging.getLogger("sqlitedict").setLevel(logging.WARNING)
        with self.db as d:
            self.d = {k:v for k,v in d.items()}

    @property
    def db(self):
        return sqlitedict.SqliteDict(filename=self.fname, tablename=self.tabname)

    def __getitem__(self, key):
        return self.d[key]

    def __setitem__(self, key, value):

        self.d[key] = value
        self.counter += 1
        self.flush()

    def flush(self):
        if self.counter >= self.buffer_size:
            with self.db as d:
                for key, value in self.d.items():
                    d[key] = value
                    d.commit()
            self.counter = 0

    def __contains__(self, key):
        return key in self.d
