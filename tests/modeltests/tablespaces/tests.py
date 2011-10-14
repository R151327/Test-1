import copy

from django.db import connection
from django.db import models
from django.db.models.loading import cache
from django.core.management.color import no_style 
from django.test import TestCase, skipIfDBFeature, skipUnlessDBFeature

from models import Article, ArticleRef, Scientist, ScientistRef

# Automatically created models
Authors = Article._meta.get_field('authors').rel.through
Reviewers = Article._meta.get_field('reviewers').rel.through

# We can't test the DEFAULT_TABLESPACE and DEFAULT_INDEX_TABLESPACE settings
# because they're evaluated when the model class is defined. As a consequence,
# @override_settings doesn't work.

def sql_for_table(model):
    return '\n'.join(connection.creation.sql_create_model(model, no_style())[0])

def sql_for_index(model):
    return '\n'.join(connection.creation.sql_indexes_for_model(model, no_style()))


class TablespacesTests(TestCase):

    def setUp(self):
        # The unmanaged models need to be removed after the test in order to
        # prevent bad interactions with other tests (proxy_models_inheritance).
        self.old_app_models = copy.deepcopy(cache.app_models)
        self.old_app_store = copy.deepcopy(cache.app_store)

        for model in Article, Authors, Reviewers, Scientist:
            model._meta.managed = True

    def tearDown(self):
        for model in Article, Authors, Reviewers, Scientist:
            model._meta.managed = False

        cache.app_models = self.old_app_models
        cache.app_store = self.old_app_store
        cache._get_models_cache = {}

    def assertNumContains(self, haystack, needle, count):
        real_count = haystack.count(needle)
        self.assertEqual(real_count, count, "Found %d instances of '%s', "
                "expected %d" % (real_count, needle, count))

    @skipUnlessDBFeature('supports_tablespaces')
    def test_tablespace_for_model(self):
        # 1 for the table + 1 for the index on the primary key
        self.assertNumContains(sql_for_table(Scientist).lower(), 'tbl_tbsp', 2)

    @skipIfDBFeature('supports_tablespaces')
    def test_tablespace_ignored_for_model(self):
        # No tablespace-related SQL
        self.assertEqual(sql_for_table(Scientist),
                         sql_for_table(ScientistRef).replace('ref', ''))

    @skipUnlessDBFeature('supports_tablespaces')
    def test_tablespace_for_indexed_field(self):
        # 1 for the table + 1 for the primary key + 1 for the index on name
        self.assertNumContains(sql_for_table(Article).lower(), 'tbl_tbsp', 3)
        # 1 for the index on reference
        self.assertNumContains(sql_for_table(Article).lower(), 'idx_tbsp', 1)

    @skipIfDBFeature('supports_tablespaces')
    def test_tablespace_ignored_for_indexed_field(self):
        # No tablespace-related SQL
        self.assertEqual(sql_for_table(Article),
                         sql_for_table(ArticleRef).replace('ref', ''))

    @skipUnlessDBFeature('supports_tablespaces')
    def test_tablespace_for_many_to_many_field(self):
        # The join table of the ManyToManyField always goes to the tablespace
        # of the model.
        self.assertNumContains(sql_for_table(Authors).lower(), 'tbl_tbsp', 2)
        self.assertNumContains(sql_for_table(Authors).lower(), 'idx_tbsp', 0)
        # The ManyToManyField declares no db_tablespace, indexes for the two
        # foreign keys in the join table go to the tablespace of the model.
        self.assertNumContains(sql_for_index(Authors).lower(), 'tbl_tbsp', 2)
        self.assertNumContains(sql_for_index(Authors).lower(), 'idx_tbsp', 0)

        # The join table of the ManyToManyField always goes to the tablespace
        # of the model.
        self.assertNumContains(sql_for_table(Reviewers).lower(), 'tbl_tbsp', 2)
        self.assertNumContains(sql_for_table(Reviewers).lower(), 'idx_tbsp', 0)
        # The ManyToManyField declares db_tablespace, indexes for the two
        # foreign keys in the join table go to this tablespace.
        self.assertNumContains(sql_for_index(Reviewers).lower(), 'tbl_tbsp', 0)
        self.assertNumContains(sql_for_index(Reviewers).lower(), 'idx_tbsp', 2)
