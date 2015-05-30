import datetime
import unittest

from django.core import exceptions, serializers
from django.db import connection
from django.test import TestCase

from . import PostgreSQLTestCase
from .models import JSONModel

try:
    from django.contrib.postgres import forms
    from django.contrib.postgres.fields import JSONField
except ImportError:
    pass


def skipUnlessPG94(test):
    try:
        PG_VERSION = connection.pg_version
    except AttributeError:
        PG_VERSION = 0
    if PG_VERSION < 90400:
        return unittest.skip('PostgreSQL >= 9.4 required')(test)
    return test


@skipUnlessPG94
class TestSaveLoad(TestCase):
    def test_null(self):
        instance = JSONModel()
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, None)

    def test_empty_object(self):
        instance = JSONModel(field={})
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, {})

    def test_empty_list(self):
        instance = JSONModel(field=[])
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, [])

    def test_boolean(self):
        instance = JSONModel(field=True)
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, True)

    def test_string(self):
        instance = JSONModel(field='why?')
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, 'why?')

    def test_number(self):
        instance = JSONModel(field=1)
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, 1)

    def test_realistic_object(self):
        obj = {
            'a': 'b',
            'c': 1,
            'd': ['e', {'f': 'g'}],
            'h': True,
            'i': False,
            'j': None,
        }
        instance = JSONModel(field=obj)
        instance.save()
        loaded = JSONModel.objects.get()
        self.assertEqual(loaded.field, obj)


@skipUnlessPG94
class TestQuerying(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.objs = [
            JSONModel.objects.create(field=None),
            JSONModel.objects.create(field=True),
            JSONModel.objects.create(field=False),
            JSONModel.objects.create(field='yes'),
            JSONModel.objects.create(field=7),
            JSONModel.objects.create(field=[]),
            JSONModel.objects.create(field={}),
            JSONModel.objects.create(field={
                'a': 'b',
                'c': 1,
            }),
            JSONModel.objects.create(field={
                'a': 'b',
                'c': 1,
                'd': ['e', {'f': 'g'}],
                'h': True,
                'i': False,
                'j': None,
                'k': {'l': 'm'},
            }),
            JSONModel.objects.create(field=[1, [2]]),
            JSONModel.objects.create(field={
                'k': True,
                'l': False,
            }),
        ]

    def test_exact(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__exact={}),
            [self.objs[6]]
        )

    def test_exact_complex(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__exact={'a': 'b', 'c': 1}),
            [self.objs[7]]
        )

    def test_isnull(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__isnull=True),
            [self.objs[0]]
        )

    def test_contains(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__contains={'a': 'b'}),
            [self.objs[7], self.objs[8]]
        )

    def test_contained_by(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__contained_by={'a': 'b', 'c': 1, 'h': True}),
            [self.objs[6], self.objs[7]]
        )

    def test_has_key(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__has_key='a'),
            [self.objs[7], self.objs[8]]
        )

    def test_has_keys(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__has_keys=['a', 'c', 'h']),
            [self.objs[8]]
        )

    def test_has_any_keys(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__has_any_keys=['c', 'l']),
            [self.objs[7], self.objs[8], self.objs[10]]
        )

    def test_shallow_list_lookup(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__0=1),
            [self.objs[9]]
        )

    def test_shallow_obj_lookup(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__a='b'),
            [self.objs[7], self.objs[8]]
        )

    def test_deep_lookup_objs(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__k__l='m'),
            [self.objs[8]]
        )

    def test_shallow_lookup_obj_target(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__k={'l': 'm'}),
            [self.objs[8]]
        )

    def test_deep_lookup_array(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__1__0=2),
            [self.objs[9]]
        )

    def test_deep_lookup_mixed(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__d__1__f='g'),
            [self.objs[8]]
        )

    def test_deep_lookup_transform(self):
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__c__gt=1),
            []
        )
        self.assertSequenceEqual(
            JSONModel.objects.filter(field__c__lt=5),
            [self.objs[7], self.objs[8]]
        )


@skipUnlessPG94
class TestSerialization(TestCase):
    test_data = '[{"fields": {"field": {"a": "b"}}, "model": "postgres_tests.jsonmodel", "pk": null}]'

    def test_dumping(self):
        instance = JSONModel(field={'a': 'b'})
        data = serializers.serialize('json', [instance])
        self.assertJSONEqual(data, self.test_data)

    def test_loading(self):
        instance = list(serializers.deserialize('json', self.test_data))[0].object
        self.assertEqual(instance.field, {'a': 'b'})


class TestValidation(PostgreSQLTestCase):

    def test_not_serializable(self):
        field = JSONField()
        with self.assertRaises(exceptions.ValidationError) as cm:
            field.clean(datetime.timedelta(days=1), None)
        self.assertEqual(cm.exception.code, 'invalid')
        self.assertEqual(cm.exception.message % cm.exception.params, "Value must be valid JSON.")


class TestFormField(PostgreSQLTestCase):

    def test_valid(self):
        field = forms.JSONField()
        value = field.clean('{"a": "b"}')
        self.assertEqual(value, {'a': 'b'})

    def test_valid_empty(self):
        field = forms.JSONField(required=False)
        value = field.clean('')
        self.assertEqual(value, None)

    def test_invalid(self):
        field = forms.JSONField()
        with self.assertRaises(exceptions.ValidationError) as cm:
            field.clean('{some badly formed: json}')
        self.assertEqual(cm.exception.messages[0], "'{some badly formed: json}' value must be valid JSON.")

    def test_formfield(self):
        model_field = JSONField()
        form_field = model_field.formfield()
        self.assertIsInstance(form_field, forms.JSONField)

    def test_prepare_value(self):
        field = forms.JSONField()
        self.assertEqual(field.prepare_value({'a': 'b'}), '{"a": "b"}')
        self.assertEqual(field.prepare_value(None), 'null')
