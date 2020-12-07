"""
Caching framework.

This package defines set of cache backends that all conform to a simple API.
In a nutshell, a cache is a set of values -- which can be any object that
may be pickled -- identified by string keys.  For the complete API, see
the abstract BaseCache class in django.core.cache.backends.base.

Client code should use the `cache` variable defined here to access the default
cache backend and look up non-default cache backends in the `caches` dict-like
object.

See docs/topics/cache.txt for information on the public API.
"""
from asgiref.local import Local

from django.conf import settings
from django.core import signals
from django.core.cache.backends.base import (
    BaseCache, CacheKeyWarning, InvalidCacheBackendError, InvalidCacheKey,
)
from django.utils.module_loading import import_string

__all__ = [
    'cache', 'caches', 'DEFAULT_CACHE_ALIAS', 'InvalidCacheBackendError',
    'CacheKeyWarning', 'BaseCache', 'InvalidCacheKey',
]

DEFAULT_CACHE_ALIAS = 'default'


class CacheHandler:
    """
    A Cache Handler to manage access to Cache instances.

    Ensure only one instance of each alias exists per thread.
    """
    def __init__(self):
        self._caches = Local()

    def __getitem__(self, alias):
        try:
            return self._caches.caches[alias]
        except AttributeError:
            self._caches.caches = {}
        except KeyError:
            pass

        if alias not in settings.CACHES:
            raise InvalidCacheBackendError(
                "Could not find config for '%s' in settings.CACHES" % alias
            )
        params = settings.CACHES[alias].copy()
        backend = params.pop('BACKEND')
        location = params.pop('LOCATION', '')
        try:
            backend_cls = import_string(backend)
        except ImportError as e:
            raise InvalidCacheBackendError(
                "Could not find backend '%s': %s" % (backend, e)
            )
        cache = backend_cls(location, params)
        self._caches.caches[alias] = cache
        return cache

    def all(self):
        return getattr(self._caches, 'caches', {}).values()


caches = CacheHandler()


class DefaultCacheProxy:
    """
    Proxy access to the default Cache object's attributes.

    This allows the legacy `cache` object to be thread-safe using the new
    ``caches`` API.
    """
    def __getattr__(self, name):
        return getattr(caches[DEFAULT_CACHE_ALIAS], name)

    def __setattr__(self, name, value):
        return setattr(caches[DEFAULT_CACHE_ALIAS], name, value)

    def __delattr__(self, name):
        return delattr(caches[DEFAULT_CACHE_ALIAS], name)

    def __contains__(self, key):
        return key in caches[DEFAULT_CACHE_ALIAS]

    def __eq__(self, other):
        return caches[DEFAULT_CACHE_ALIAS] == other


cache = DefaultCacheProxy()


def close_caches(**kwargs):
    # Some caches -- python-memcached in particular -- need to do a cleanup at the
    # end of a request cycle. If not implemented in a particular backend
    # cache.close is a no-op
    for cache in caches.all():
        cache.close()


signals.request_finished.connect(close_caches)
