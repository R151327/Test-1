from __future__ import unicode_literals

from django.db import DEFAULT_DB_ALIAS


class TestRouter(object):
    # A test router. The behavior is vaguely leader/follower, but the
    # databases aren't assumed to propagate changes.
    def db_for_read(self, model, instance=None, **hints):
        if instance:
            return instance._state.db or 'other'
        return 'other'

    def db_for_write(self, model, **hints):
        return DEFAULT_DB_ALIAS

    def allow_relation(self, obj1, obj2, **hints):
        return obj1._state.db in ('default', 'other') and obj2._state.db in ('default', 'other')

    def allow_migrate(self, db, model):
        return True


class AuthRouter(object):
    """A router to control all database operations on models in
    the contrib.auth application"""

    def db_for_read(self, model, **hints):
        "Point all read operations on auth models to 'default'"
        if model._meta.app_label == 'auth':
            # We use default here to ensure we can tell the difference
            # between a read request and a write request for Auth objects
            return 'default'
        return None

    def db_for_write(self, model, **hints):
        "Point all operations on auth models to 'other'"
        if model._meta.app_label == 'auth':
            return 'other'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        "Allow any relation if a model in Auth is involved"
        if obj1._meta.app_label == 'auth' or obj2._meta.app_label == 'auth':
            return True
        return None

    def allow_migrate(self, db, model):
        "Make sure the auth app only appears on the 'other' db"
        if db == 'other':
            return model._meta.app_label == 'auth'
        elif model._meta.app_label == 'auth':
            return False
        return None


class WriteRouter(object):
    # A router that only expresses an opinion on writes
    def db_for_write(self, model, **hints):
        return 'writer'
