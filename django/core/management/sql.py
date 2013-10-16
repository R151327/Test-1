from __future__ import unicode_literals

import codecs
import os
import re
import warnings

from django.conf import settings
from django.core.management.base import CommandError
from django.db import models, router


def filtered_app_models(app, db_alias, include_auto_created=False):
    """
    Return app models allowed to be synchronized on provided db.
    """
    return [model for model in models.get_models(app, include_auto_created=include_auto_created)
            if router.allow_migrate(db_alias, model)]


def sql_create(app, style, connection):
    "Returns a list of the CREATE TABLE SQL statements for the given app."

    if connection.settings_dict['ENGINE'] == 'django.db.backends.dummy':
        # This must be the "dummy" database backend, which means the user
        # hasn't set ENGINE for the database.
        raise CommandError("Django doesn't know which syntax to use for your SQL statements,\n" +
            "because you haven't properly specified the ENGINE setting for the database.\n" +
            "see: https://docs.djangoproject.com/en/dev/ref/settings/#databases")

    # Get installed models, so we generate REFERENCES right.
    # We trim models from the current app so that the sqlreset command does not
    # generate invalid SQL (leaving models out of known_models is harmless, so
    # we can be conservative).
    app_models = models.get_models(app, include_auto_created=True)
    final_output = []
    tables = connection.introspection.table_names()
    known_models = set(model for model in connection.introspection.installed_models(tables) if model not in app_models)
    pending_references = {}

    for model in filtered_app_models(app, connection.alias, include_auto_created=True):
        output, references = connection.creation.sql_create_model(model, style, known_models)
        final_output.extend(output)
        for refto, refs in references.items():
            pending_references.setdefault(refto, []).extend(refs)
            if refto in known_models:
                final_output.extend(connection.creation.sql_for_pending_references(refto, style, pending_references))
        final_output.extend(connection.creation.sql_for_pending_references(model, style, pending_references))
        # Keep track of the fact that we've created the table for this model.
        known_models.add(model)

    # Handle references to tables that are from other apps
    # but don't exist physically.
    not_installed_models = set(pending_references.keys())
    if not_installed_models:
        alter_sql = []
        for model in not_installed_models:
            alter_sql.extend(['-- ' + sql for sql in
                connection.creation.sql_for_pending_references(model, style, pending_references)])
        if alter_sql:
            final_output.append('-- The following references should be added but depend on non-existent tables:')
            final_output.extend(alter_sql)

    return final_output


def sql_delete(app, style, connection):
    "Returns a list of the DROP TABLE SQL statements for the given app."

    # This should work even if a connection isn't available
    try:
        cursor = connection.cursor()
    except Exception:
        cursor = None

    # Figure out which tables already exist
    if cursor:
        table_names = connection.introspection.table_names(cursor)
    else:
        table_names = []

    output = []

    # Output DROP TABLE statements for standard application tables.
    to_delete = set()

    references_to_delete = {}
    app_models = filtered_app_models(app, connection.alias, include_auto_created=True)
    for model in app_models:
        if cursor and connection.introspection.table_name_converter(model._meta.db_table) in table_names:
            # The table exists, so it needs to be dropped
            opts = model._meta
            for f in opts.local_fields:
                if f.rel and f.rel.to not in to_delete:
                    references_to_delete.setdefault(f.rel.to, []).append((model, f))

            to_delete.add(model)

    for model in app_models:
        if connection.introspection.table_name_converter(model._meta.db_table) in table_names:
            output.extend(connection.creation.sql_destroy_model(model, references_to_delete, style))

    # Close database connection explicitly, in case this output is being piped
    # directly into a database client, to avoid locking issues.
    if cursor:
        cursor.close()
        connection.close()

    return output[::-1]  # Reverse it, to deal with table dependencies.


def sql_flush(style, connection, only_django=False, reset_sequences=True, allow_cascade=False):
    """
    Returns a list of the SQL statements used to flush the database.

    If only_django is True, then only table names that have associated Django
    models and are in INSTALLED_APPS will be included.
    """
    if only_django:
        tables = connection.introspection.django_table_names(only_existing=True)
    else:
        tables = connection.introspection.table_names()
    seqs = connection.introspection.sequence_list() if reset_sequences else ()
    statements = connection.ops.sql_flush(style, tables, seqs, allow_cascade)
    return statements


def sql_custom(app, style, connection):
    "Returns a list of the custom table modifying SQL statements for the given app."
    output = []

    app_models = filtered_app_models(app, connection.alias)

    for model in app_models:
        output.extend(custom_sql_for_model(model, style, connection))

    return output


def sql_indexes(app, style, connection):
    "Returns a list of the CREATE INDEX SQL statements for all models in the given app."
    output = []
    for model in filtered_app_models(app, connection.alias, include_auto_created=True):
        output.extend(connection.creation.sql_indexes_for_model(model, style))
    return output


def sql_destroy_indexes(app, style, connection):
    "Returns a list of the DROP INDEX SQL statements for all models in the given app."
    output = []
    for model in filtered_app_models(app, connection.alias, include_auto_created=True):
        output.extend(connection.creation.sql_destroy_indexes_for_model(model, style))
    return output


def sql_all(app, style, connection):
    "Returns a list of CREATE TABLE SQL, initial-data inserts, and CREATE INDEX SQL for the given module."
    return sql_create(app, style, connection) + sql_custom(app, style, connection) + sql_indexes(app, style, connection)


def _split_statements(content):
    comment_re = re.compile(r"^((?:'[^']*'|[^'])*?)--.*$")
    statements = []
    statement = []
    for line in content.split("\n"):
        cleaned_line = comment_re.sub(r"\1", line).strip()
        if not cleaned_line:
            continue
        statement.append(cleaned_line)
        if cleaned_line.endswith(";"):
            statements.append(" ".join(statement))
            statement = []
    return statements


def custom_sql_for_model(model, style, connection):
    opts = model._meta
    app_dirs = []
    app_dir = models.get_app_path(model._meta.app_label)
    app_dirs.append(os.path.normpath(os.path.join(app_dir, 'sql')))

    # Deprecated location -- remove in Django 1.9
    old_app_dir = os.path.normpath(os.path.join(app_dir, 'models/sql'))
    if os.path.exists(old_app_dir):
        warnings.warn("Custom SQL location '<app_label>/models/sql' is "
                      "deprecated, use '<app_label>/sql' instead.",
                      PendingDeprecationWarning)
        app_dirs.append(old_app_dir)

    output = []

    # Post-creation SQL should come before any initial SQL data is loaded.
    # However, this should not be done for models that are unmanaged or
    # for fields that are part of a parent model (via model inheritance).
    if opts.managed:
        post_sql_fields = [f for f in opts.local_fields if hasattr(f, 'post_create_sql')]
        for f in post_sql_fields:
            output.extend(f.post_create_sql(style, model._meta.db_table))

    # Find custom SQL, if it's available.
    backend_name = connection.settings_dict['ENGINE'].split('.')[-1]
    sql_files = []
    for app_dir in app_dirs:
        sql_files.append(os.path.join(app_dir, "%s.%s.sql" % (opts.model_name, backend_name)))
        sql_files.append(os.path.join(app_dir, "%s.sql" % opts.model_name))
    for sql_file in sql_files:
        if os.path.exists(sql_file):
            with codecs.open(sql_file, 'U', encoding=settings.FILE_CHARSET) as fp:
                # Some backends can't execute more than one SQL statement at a time,
                # so split into separate statements.
                output.extend(_split_statements(fp.read()))
    return output


def emit_pre_migrate_signal(create_models, verbosity, interactive, db):
    # Emit the pre_migrate signal for every application.
    for app in models.get_apps():
        app_name = app.__name__.split('.')[-2]
        if verbosity >= 2:
            print("Running pre-migrate handlers for application %s" % app_name)
        models.signals.pre_migrate.send(sender=app, app=app,
                                       create_models=create_models,
                                       verbosity=verbosity,
                                       interactive=interactive,
                                       db=db)


def emit_post_migrate_signal(created_models, verbosity, interactive, db):
    # Emit the post_migrate signal for every application.
    for app in models.get_apps():
        app_name = app.__name__.split('.')[-2]
        if verbosity >= 2:
            print("Running post-migrate handlers for application %s" % app_name)
        models.signals.post_migrate.send(sender=app, app=app,
            created_models=created_models, verbosity=verbosity,
            interactive=interactive, db=db)
