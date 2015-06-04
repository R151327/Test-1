import sys
import time

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import router
from django.utils.six import StringIO
from django.utils.six.moves import input

# The prefix to put on the default database name when creating
# the test database.
TEST_DATABASE_PREFIX = 'test_'


class BaseDatabaseCreation(object):
    """
    This class encapsulates all backend-specific differences that pertain to
    creation and destruction of the test database.
    """
    def __init__(self, connection):
        self.connection = connection

    @property
    def _nodb_connection(self):
        """
        Used to be defined here, now moved to DatabaseWrapper.
        """
        return self.connection._nodb_connection

    def create_test_db(self, verbosity=1, autoclobber=False, serialize=True, keepdb=False):
        """
        Creates a test database, prompting the user for confirmation if the
        database already exists. Returns the name of the test database created.
        """
        # Don't import django.core.management if it isn't needed.
        from django.core.management import call_command

        test_database_name = self._get_test_db_name()

        if verbosity >= 1:
            test_db_repr = ''
            action = 'Creating'
            if verbosity >= 2:
                test_db_repr = " ('%s')" % test_database_name
            if keepdb:
                action = "Using existing"

            print("%s test database for alias '%s'%s..." % (
                action, self.connection.alias, test_db_repr))

        # We could skip this call if keepdb is True, but we instead
        # give it the keepdb param. This is to handle the case
        # where the test DB doesn't exist, in which case we need to
        # create it, then just not destroy it. If we instead skip
        # this, we will get an exception.
        self._create_test_db(verbosity, autoclobber, keepdb)

        self.connection.close()
        settings.DATABASES[self.connection.alias]["NAME"] = test_database_name
        self.connection.settings_dict["NAME"] = test_database_name

        # We report migrate messages at one level lower than that requested.
        # This ensures we don't get flooded with messages during testing
        # (unless you really ask to be flooded).
        call_command(
            'migrate',
            verbosity=max(verbosity - 1, 0),
            interactive=False,
            database=self.connection.alias,
            run_syncdb=True,
        )

        # We then serialize the current state of the database into a string
        # and store it on the connection. This slightly horrific process is so people
        # who are testing on databases without transactions or who are using
        # a TransactionTestCase still get a clean database on every test run.
        if serialize:
            self.connection._test_serialized_contents = self.serialize_db_to_string()

        call_command('createcachetable', database=self.connection.alias)

        # Ensure a connection for the side effect of initializing the test database.
        self.connection.ensure_connection()

        return test_database_name

    def set_as_test_mirror(self, primary_settings_dict):
        """
        Set this database up to be used in testing as a mirror of a primary database
        whose settings are given
        """
        self.connection.settings_dict['NAME'] = primary_settings_dict['NAME']

    def serialize_db_to_string(self):
        """
        Serializes all data in the database into a JSON string.
        Designed only for test runner usage; will not handle large
        amounts of data.
        """
        # Build list of all apps to serialize
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(self.connection)
        app_list = []
        for app_config in apps.get_app_configs():
            if (
                app_config.models_module is not None and
                app_config.label in loader.migrated_apps and
                app_config.name not in settings.TEST_NON_SERIALIZED_APPS
            ):
                app_list.append((app_config, None))

        # Make a function to iteratively return every object
        def get_objects():
            for model in serializers.sort_dependencies(app_list):
                if (model._meta.can_migrate(self.connection) and
                        router.allow_migrate_model(self.connection.alias, model)):
                    queryset = model._default_manager.using(self.connection.alias).order_by(model._meta.pk.name)
                    for obj in queryset.iterator():
                        yield obj
        # Serialize to a string
        out = StringIO()
        serializers.serialize("json", get_objects(), indent=None, stream=out)
        return out.getvalue()

    def deserialize_db_from_string(self, data):
        """
        Reloads the database with data from a string generated by
        the serialize_db_to_string method.
        """
        data = StringIO(data)
        for obj in serializers.deserialize("json", data, using=self.connection.alias):
            obj.save()

    def _get_test_db_name(self):
        """
        Internal implementation - returns the name of the test DB that will be
        created. Only useful when called from create_test_db() and
        _create_test_db() and when no external munging is done with the 'NAME'
        or 'TEST_NAME' settings.
        """
        if self.connection.settings_dict['TEST']['NAME']:
            return self.connection.settings_dict['TEST']['NAME']
        return TEST_DATABASE_PREFIX + self.connection.settings_dict['NAME']

    def _create_test_db(self, verbosity, autoclobber, keepdb=False):
        """
        Internal implementation - creates the test db tables.
        """
        suffix = self.sql_table_creation_suffix()

        test_database_name = self._get_test_db_name()

        qn = self.connection.ops.quote_name

        # Create the test database and connect to it.
        with self._nodb_connection.cursor() as cursor:
            try:
                cursor.execute(
                    "CREATE DATABASE %s %s" % (qn(test_database_name), suffix))
            except Exception as e:
                # if we want to keep the db, then no need to do any of the below,
                # just return and skip it all.
                if keepdb:
                    return test_database_name

                sys.stderr.write(
                    "Got an error creating the test database: %s\n" % e)
                if not autoclobber:
                    confirm = input(
                        "Type 'yes' if you would like to try deleting the test "
                        "database '%s', or 'no' to cancel: " % test_database_name)
                if autoclobber or confirm == 'yes':
                    try:
                        if verbosity >= 1:
                            print("Destroying old test database '%s'..."
                                  % self.connection.alias)
                        cursor.execute(
                            "DROP DATABASE %s" % qn(test_database_name))
                        cursor.execute(
                            "CREATE DATABASE %s %s" % (qn(test_database_name),
                                                       suffix))
                    except Exception as e:
                        sys.stderr.write(
                            "Got an error recreating the test database: %s\n" % e)
                        sys.exit(2)
                else:
                    print("Tests cancelled.")
                    sys.exit(1)

        return test_database_name

    def destroy_test_db(self, old_database_name, verbosity=1, keepdb=False):
        """
        Destroy a test database, prompting the user for confirmation if the
        database already exists.
        """
        self.connection.close()
        test_database_name = self.connection.settings_dict['NAME']
        if verbosity >= 1:
            test_db_repr = ''
            action = 'Destroying'
            if verbosity >= 2:
                test_db_repr = " ('%s')" % test_database_name
            if keepdb:
                action = 'Preserving'
            print("%s test database for alias '%s'%s..." % (
                action, self.connection.alias, test_db_repr))

        # if we want to preserve the database
        # skip the actual destroying piece.
        if not keepdb:
            self._destroy_test_db(test_database_name, verbosity)

        # Restore the original database name
        settings.DATABASES[self.connection.alias]["NAME"] = old_database_name
        self.connection.settings_dict["NAME"] = old_database_name

    def _destroy_test_db(self, test_database_name, verbosity):
        """
        Internal implementation - remove the test db tables.
        """
        # Remove the test database to clean up after
        # ourselves. Connect to the previous database (not the test database)
        # to do so, because it's not allowed to delete a database while being
        # connected to it.
        with self.connection._nodb_connection.cursor() as cursor:
            # Wait to avoid "database is being accessed by other users" errors.
            time.sleep(1)
            cursor.execute("DROP DATABASE %s"
                           % self.connection.ops.quote_name(test_database_name))

    def sql_table_creation_suffix(self):
        """
        SQL to append to the end of the test table creation statements.
        """
        return ''

    def test_db_signature(self):
        """
        Returns a tuple with elements of self.connection.settings_dict (a
        DATABASES setting value) that uniquely identify a database
        accordingly to the RDBMS particularities.
        """
        settings_dict = self.connection.settings_dict
        return (
            settings_dict['HOST'],
            settings_dict['PORT'],
            settings_dict['ENGINE'],
            settings_dict['NAME']
        )
