"""
Creates permissions for all installed apps that need permissions.
"""
from __future__ import unicode_literals

import getpass
import unicodedata

from django.apps import apps
from django.contrib.auth import get_permission_codename
from django.core import exceptions
from django.core.management.base import CommandError
from django.db import DEFAULT_DB_ALIAS, router
from django.utils.encoding import DEFAULT_LOCALE_ENCODING
from django.utils import six


def _get_all_permissions(opts, ctype):
    """
    Returns (codename, name) for all permissions in the given opts.
    """
    builtin = _get_builtin_permissions(opts)
    custom = list(opts.permissions)
    _check_permission_clashing(custom, builtin, ctype)
    return builtin + custom


def _get_builtin_permissions(opts):
    """
    Returns (codename, name) for all autogenerated permissions.
    By default, this is ('add', 'change', 'delete')
    """
    perms = []
    for action in opts.default_permissions:
        perms.append((get_permission_codename(action, opts),
            'Can %s %s' % (action, opts.verbose_name_raw)))
    return perms


def _check_permission_clashing(custom, builtin, ctype):
    """
    Check that permissions for a model do not clash. Raises CommandError if
    there are duplicate permissions.
    """
    pool = set()
    builtin_codenames = set(p[0] for p in builtin)
    for codename, _name in custom:
        if codename in pool:
            raise CommandError(
                "The permission codename '%s' is duplicated for model '%s.%s'." %
                (codename, ctype.app_label, ctype.model_class().__name__))
        elif codename in builtin_codenames:
            raise CommandError(
                "The permission codename '%s' clashes with a builtin permission "
                "for model '%s.%s'." %
                (codename, ctype.app_label, ctype.model_class().__name__))
        pool.add(codename)


def create_permissions(app_config, verbosity=2, interactive=True, using=DEFAULT_DB_ALIAS, **kwargs):
    if not app_config.models_module:
        return

    try:
        Permission = apps.get_model('auth', 'Permission')
    except LookupError:
        return

    if not router.allow_migrate(using, Permission):
        return

    from django.contrib.contenttypes.models import ContentType

    # This will hold the permissions we're looking for as
    # (content_type, (codename, name))
    searched_perms = list()
    # The codenames and ctypes that should exist.
    ctypes = set()
    for klass in app_config.get_models():
        # Force looking up the content types in the current database
        # before creating foreign keys to them.
        ctype = ContentType.objects.db_manager(using).get_for_model(klass)
        ctypes.add(ctype)
        for perm in _get_all_permissions(klass._meta, ctype):
            searched_perms.append((ctype, perm))

    # Find all the Permissions that have a content_type for a model we're
    # looking for.  We don't need to check for codenames since we already have
    # a list of the ones we're going to create.
    all_perms = set(Permission.objects.using(using).filter(
        content_type__in=ctypes,
    ).values_list(
        "content_type", "codename"
    ))

    perms = [
        Permission(codename=codename, name=name, content_type=ct)
        for ct, (codename, name) in searched_perms
        if (ct.pk, codename) not in all_perms
    ]
    # Validate the permissions before bulk_creation to avoid cryptic
    # database error when the verbose_name is longer than 50 characters
    permission_name_max_length = Permission._meta.get_field('name').max_length
    verbose_name_max_length = permission_name_max_length - 11  # len('Can change ') prefix
    for perm in perms:
        if len(perm.name) > permission_name_max_length:
            raise exceptions.ValidationError(
                "The verbose_name of %s is longer than %s characters" % (
                    perm.content_type,
                    verbose_name_max_length,
                )
            )
    Permission.objects.using(using).bulk_create(perms)
    if verbosity >= 2:
        for perm in perms:
            print("Adding permission '%s'" % perm)


def get_system_username():
    """
    Try to determine the current system user's username.

    :returns: The username as a unicode string, or an empty string if the
        username could not be determined.
    """
    try:
        result = getpass.getuser()
    except (ImportError, KeyError):
        # KeyError will be raised by os.getpwuid() (called by getuser())
        # if there is no corresponding entry in the /etc/passwd file
        # (a very restricted chroot environment, for example).
        return ''
    if six.PY2:
        try:
            result = result.decode(DEFAULT_LOCALE_ENCODING)
        except UnicodeDecodeError:
            # UnicodeDecodeError - preventive treatment for non-latin Windows.
            return ''
    return result


def get_default_username(check_db=True):
    """
    Try to determine the current system user's username to use as a default.

    :param check_db: If ``True``, requires that the username does not match an
        existing ``auth.User`` (otherwise returns an empty string).
    :returns: The username, or an empty string if no username can be
        determined.
    """
    # This file is used in apps.py, it should not trigger models import.
    from django.contrib.auth import models as auth_app

    # If the User model has been swapped out, we can't make any assumptions
    # about the default user name.
    if auth_app.User._meta.swapped:
        return ''

    default_username = get_system_username()
    try:
        default_username = (unicodedata.normalize('NFKD', default_username)
                .encode('ascii', 'ignore').decode('ascii')
                .replace(' ', '').lower())
    except UnicodeDecodeError:
        return ''

    # Run the username validator
    try:
        auth_app.User._meta.get_field('username').run_validators(default_username)
    except exceptions.ValidationError:
        return ''

    # Don't return the default username if it is already taken.
    if check_db and default_username:
        try:
            auth_app.User._default_manager.get(username=default_username)
        except auth_app.User.DoesNotExist:
            pass
        else:
            return ''
    return default_username
