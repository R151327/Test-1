from __future__ import unicode_literals

from collections import Counter

from django.conf import settings
from django.utils import six

from . import Error, Tags, Warning, register


@register(Tags.urls)
def check_url_config(app_configs, **kwargs):
    if getattr(settings, 'ROOT_URLCONF', None):
        from django.urls import get_resolver
        resolver = get_resolver()
        return check_resolver(resolver)
    return []


def check_resolver(resolver):
    """
    Recursively check the resolver.
    """
    check_method = getattr(resolver, 'check', None)
    if check_method is not None:
        return check_method()
    elif not hasattr(resolver, 'resolve'):
        return get_warning_for_invalid_pattern(resolver)
    else:
        return []


@register(Tags.urls)
def check_url_namespaces_unique(app_configs, **kwargs):
    """
    Warn if URL namespaces used in applications aren't unique.
    """
    if not getattr(settings, 'ROOT_URLCONF', None):
        return []

    from django.urls import get_resolver
    resolver = get_resolver()
    all_namespaces = _load_all_namespaces(resolver)
    counter = Counter(all_namespaces)
    non_unique_namespaces = [n for n, count in counter.items() if count > 1]
    errors = []
    for namespace in non_unique_namespaces:
        errors.append(Warning(
            "URL namespace '{}' isn't unique. You may not be able to reverse "
            "all URLs in this namespace".format(namespace),
            id="urls.W005",
        ))
    return errors


def _load_all_namespaces(resolver):
    """
    Recursively load all namespaces from URL patterns.
    """
    url_patterns = getattr(resolver, 'url_patterns', [])
    namespaces = [
        url.namespace for url in url_patterns
        if getattr(url, 'namespace', None) is not None
    ]
    for pattern in url_patterns:
        namespaces.extend(_load_all_namespaces(pattern))
    return namespaces


def get_warning_for_invalid_pattern(pattern):
    """
    Return a list containing a warning that the pattern is invalid.

    describe_pattern() cannot be used here, because we cannot rely on the
    urlpattern having regex or name attributes.
    """
    if isinstance(pattern, six.string_types):
        hint = (
            "Try removing the string '{}'. The list of urlpatterns should not "
            "have a prefix string as the first element.".format(pattern)
        )
    elif isinstance(pattern, tuple):
        hint = "Try using url() instead of a tuple."
    else:
        hint = None

    return [Error(
        "Your URL pattern {!r} is invalid. Ensure that urlpatterns is a list "
        "of url() instances.".format(pattern),
        hint=hint,
        id="urls.E004",
    )]
