"""
Dummy database backend for Django.

Django uses this if the DATABASE_ENGINE setting is empty (None or empty string).

Each of these API functions, except connection.close(), raises
ImproperlyConfigured.
"""

from django.core.exceptions import ImproperlyConfigured

def complain(*args, **kwargs):
    raise ImproperlyConfigured, "You haven't set the DATABASE_ENGINE setting yet."

def ignore(*args, **kwargs):
    pass

class DatabaseError(Exception):
    pass

class IntegrityError(DatabaseError):
    pass

class DatabaseOperations(object):
    def __getattr__(self, *args, **kwargs):
        complain()

class DatabaseWrapper(object):
    ops = DatabaseOperations()
    cursor = complain
    _commit = complain
    _rollback = ignore

    def __init__(self, **kwargs):
        pass

    def close(self):
        pass # close()

supports_constraints = False
supports_tablespaces = False
quote_name = complain
dictfetchone = complain
dictfetchmany = complain
dictfetchall = complain
get_last_insert_id = complain
get_date_trunc_sql = complain
get_datetime_cast_sql = complain
get_limit_offset_sql = complain
get_random_function_sql = complain
get_deferrable_sql = complain
get_fulltext_search_sql = complain
get_drop_foreignkey_sql = complain
get_pk_default_value = complain
get_max_name_length = ignore
get_start_transaction_sql = complain
get_sql_flush = complain
get_sql_sequence_reset = complain

OPERATOR_MAPPING = {}
