import datetime
import pickle
import unittest
import uuid
from copy import deepcopy
from unittest import mock

from django.core.exceptions import FieldError
from django.db import DatabaseError, connection, models
from django.db.models import CharField, Q, TimeField, UUIDField
from django.db.models.aggregates import (
    Avg, Count, Max, Min, StdDev, Sum, Variance,
)
from django.db.models.expressions import (
    Case, Col, Combinable, Exists, Expression, ExpressionList,
    ExpressionWrapper, F, Func, OrderBy, OuterRef, Random, RawSQL, Ref,
    Subquery, Value, When,
)
from django.db.models.functions import (
    Coalesce, Concat, Length, Lower, Substr, Upper,
)
from django.db.models.sql import constants
from django.db.models.sql.datastructures import Join
from django.test import SimpleTestCase, TestCase, skipUnlessDBFeature
from django.test.utils import Approximate, isolate_apps

from .models import (
    UUID, UUIDPK, Company, Employee, Experiment, Number, RemoteEmployee,
    Result, SimulationRun, Time,
)


class BasicExpressionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.example_inc = Company.objects.create(
            name="Example Inc.", num_employees=2300, num_chairs=5,
            ceo=Employee.objects.create(firstname="Joe", lastname="Smith", salary=10)
        )
        cls.foobar_ltd = Company.objects.create(
            name="Foobar Ltd.", num_employees=3, num_chairs=4, based_in_eu=True,
            ceo=Employee.objects.create(firstname="Frank", lastname="Meyer", salary=20)
        )
        cls.max = Employee.objects.create(firstname='Max', lastname='Mustermann', salary=30)
        cls.gmbh = Company.objects.create(name='Test GmbH', num_employees=32, num_chairs=1, ceo=cls.max)

    def setUp(self):
        self.company_query = Company.objects.values(
            "name", "num_employees", "num_chairs"
        ).order_by(
            "name", "num_employees", "num_chairs"
        )

    def test_annotate_values_aggregate(self):
        companies = Company.objects.annotate(
            salaries=F('ceo__salary'),
        ).values('num_employees', 'salaries').aggregate(
            result=Sum(
                F('salaries') + F('num_employees'),
                output_field=models.IntegerField()
            ),
        )
        self.assertEqual(companies['result'], 2395)

    def test_annotate_values_filter(self):
        companies = Company.objects.annotate(
            foo=RawSQL('%s', ['value']),
        ).filter(foo='value').order_by('name')
        self.assertQuerysetEqual(
            companies,
            ['<Company: Example Inc.>', '<Company: Foobar Ltd.>', '<Company: Test GmbH>'],
        )

    def test_annotate_values_count(self):
        companies = Company.objects.annotate(foo=RawSQL('%s', ['value']))
        self.assertEqual(companies.count(), 3)

    @skipUnlessDBFeature('supports_boolean_expr_in_select_clause')
    def test_filtering_on_annotate_that_uses_q(self):
        self.assertEqual(
            Company.objects.annotate(
                num_employees_check=ExpressionWrapper(Q(num_employees__gt=3), output_field=models.BooleanField())
            ).filter(num_employees_check=True).count(),
            2,
        )

    def test_filtering_on_q_that_is_boolean(self):
        self.assertEqual(
            Company.objects.filter(
                ExpressionWrapper(Q(num_employees__gt=3), output_field=models.BooleanField())
            ).count(),
            2,
        )

    def test_filter_inter_attribute(self):
        # We can filter on attribute relationships on same model obj, e.g.
        # find companies where the number of employees is greater
        # than the number of chairs.
        self.assertSequenceEqual(
            self.company_query.filter(num_employees__gt=F("num_chairs")), [
                {
                    "num_chairs": 5,
                    "name": "Example Inc.",
                    "num_employees": 2300,
                },
                {
                    "num_chairs": 1,
                    "name": "Test GmbH",
                    "num_employees": 32
                },
            ],
        )

    def test_update(self):
        # We can set one field to have the value of another field
        # Make sure we have enough chairs
        self.company_query.update(num_chairs=F("num_employees"))
        self.assertSequenceEqual(
            self.company_query, [
                {
                    "num_chairs": 2300,
                    "name": "Example Inc.",
                    "num_employees": 2300
                },
                {
                    "num_chairs": 3,
                    "name": "Foobar Ltd.",
                    "num_employees": 3
                },
                {
                    "num_chairs": 32,
                    "name": "Test GmbH",
                    "num_employees": 32
                }
            ],
        )

    def test_arithmetic(self):
        # We can perform arithmetic operations in expressions
        # Make sure we have 2 spare chairs
        self.company_query.update(num_chairs=F("num_employees") + 2)
        self.assertSequenceEqual(
            self.company_query, [
                {
                    'num_chairs': 2302,
                    'name': 'Example Inc.',
                    'num_employees': 2300
                },
                {
                    'num_chairs': 5,
                    'name': 'Foobar Ltd.',
                    'num_employees': 3
                },
                {
                    'num_chairs': 34,
                    'name': 'Test GmbH',
                    'num_employees': 32
                }
            ],
        )

    def test_order_of_operations(self):
        # Law of order of operations is followed
        self.company_query.update(num_chairs=F('num_employees') + 2 * F('num_employees'))
        self.assertSequenceEqual(
            self.company_query, [
                {
                    'num_chairs': 6900,
                    'name': 'Example Inc.',
                    'num_employees': 2300
                },
                {
                    'num_chairs': 9,
                    'name': 'Foobar Ltd.',
                    'num_employees': 3
                },
                {
                    'num_chairs': 96,
                    'name': 'Test GmbH',
                    'num_employees': 32
                }
            ],
        )

    def test_parenthesis_priority(self):
        # Law of order of operations can be overridden by parentheses
        self.company_query.update(num_chairs=(F('num_employees') + 2) * F('num_employees'))
        self.assertSequenceEqual(
            self.company_query, [
                {
                    'num_chairs': 5294600,
                    'name': 'Example Inc.',
                    'num_employees': 2300
                },
                {
                    'num_chairs': 15,
                    'name': 'Foobar Ltd.',
                    'num_employees': 3
                },
                {
                    'num_chairs': 1088,
                    'name': 'Test GmbH',
                    'num_employees': 32
                }
            ],
        )

    def test_update_with_fk(self):
        # ForeignKey can become updated with the value of another ForeignKey.
        self.assertEqual(Company.objects.update(point_of_contact=F('ceo')), 3)
        self.assertQuerysetEqual(
            Company.objects.all(),
            ['Joe Smith', 'Frank Meyer', 'Max Mustermann'],
            lambda c: str(c.point_of_contact),
            ordered=False
        )

    def test_update_with_none(self):
        Number.objects.create(integer=1, float=1.0)
        Number.objects.create(integer=2)
        Number.objects.filter(float__isnull=False).update(float=Value(None))
        self.assertQuerysetEqual(
            Number.objects.all(),
            [None, None],
            lambda n: n.float,
            ordered=False
        )

    def test_filter_with_join(self):
        # F Expressions can also span joins
        Company.objects.update(point_of_contact=F('ceo'))
        c = Company.objects.first()
        c.point_of_contact = Employee.objects.create(firstname="Guido", lastname="van Rossum")
        c.save()

        self.assertQuerysetEqual(
            Company.objects.filter(ceo__firstname=F('point_of_contact__firstname')),
            ['Foobar Ltd.', 'Test GmbH'],
            lambda c: c.name,
            ordered=False
        )

        Company.objects.exclude(
            ceo__firstname=F("point_of_contact__firstname")
        ).update(name="foo")
        self.assertEqual(
            Company.objects.exclude(
                ceo__firstname=F('point_of_contact__firstname')
            ).get().name,
            "foo",
        )

        msg = "Joined field references are not permitted in this query"
        with self.assertRaisesMessage(FieldError, msg):
            Company.objects.exclude(
                ceo__firstname=F('point_of_contact__firstname')
            ).update(name=F('point_of_contact__lastname'))

    def test_object_update(self):
        # F expressions can be used to update attributes on single objects
        self.gmbh.num_employees = F('num_employees') + 4
        self.gmbh.save()
        self.gmbh.refresh_from_db()
        self.assertEqual(self.gmbh.num_employees, 36)

    def test_new_object_save(self):
        # We should be able to use Funcs when inserting new data
        test_co = Company(name=Lower(Value('UPPER')), num_employees=32, num_chairs=1, ceo=self.max)
        test_co.save()
        test_co.refresh_from_db()
        self.assertEqual(test_co.name, "upper")

    def test_new_object_create(self):
        test_co = Company.objects.create(name=Lower(Value('UPPER')), num_employees=32, num_chairs=1, ceo=self.max)
        test_co.refresh_from_db()
        self.assertEqual(test_co.name, "upper")

    def test_object_create_with_aggregate(self):
        # Aggregates are not allowed when inserting new data
        msg = 'Aggregate functions are not allowed in this query (num_employees=Max(Value(1))).'
        with self.assertRaisesMessage(FieldError, msg):
            Company.objects.create(
                name='Company', num_employees=Max(Value(1)), num_chairs=1,
                ceo=Employee.objects.create(firstname="Just", lastname="Doit", salary=30),
            )

    def test_object_update_fk(self):
        # F expressions cannot be used to update attributes which are foreign
        # keys, or attributes which involve joins.
        test_gmbh = Company.objects.get(pk=self.gmbh.pk)
        msg = 'F(ceo)": "Company.point_of_contact" must be a "Employee" instance.'
        with self.assertRaisesMessage(ValueError, msg):
            test_gmbh.point_of_contact = F('ceo')

        test_gmbh.point_of_contact = self.gmbh.ceo
        test_gmbh.save()
        test_gmbh.name = F('ceo__lastname')
        msg = 'Joined field references are not permitted in this query'
        with self.assertRaisesMessage(FieldError, msg):
            test_gmbh.save()

    def test_update_inherited_field_value(self):
        msg = 'Joined field references are not permitted in this query'
        with self.assertRaisesMessage(FieldError, msg):
            RemoteEmployee.objects.update(adjusted_salary=F('salary') * 5)

    def test_object_update_unsaved_objects(self):
        # F expressions cannot be used to update attributes on objects which do
        # not yet exist in the database
        acme = Company(name='The Acme Widget Co.', num_employees=12, num_chairs=5, ceo=self.max)
        acme.num_employees = F("num_employees") + 16
        msg = (
            'Failed to insert expression "Col(expressions_company, '
            'expressions.Company.num_employees) + Value(16)" on '
            'expressions.Company.num_employees. F() expressions can only be '
            'used to update, not to insert.'
        )
        with self.assertRaisesMessage(ValueError, msg):
            acme.save()

        acme.num_employees = 12
        acme.name = Lower(F('name'))
        msg = (
            'Failed to insert expression "Lower(Col(expressions_company, '
            'expressions.Company.name))" on expressions.Company.name. F() '
            'expressions can only be used to update, not to insert.'
        )
        with self.assertRaisesMessage(ValueError, msg):
            acme.save()

    def test_ticket_11722_iexact_lookup(self):
        Employee.objects.create(firstname="John", lastname="Doe")
        Employee.objects.create(firstname="Test", lastname="test")

        queryset = Employee.objects.filter(firstname__iexact=F('lastname'))
        self.assertQuerysetEqual(queryset, ["<Employee: Test test>"])

    def test_ticket_16731_startswith_lookup(self):
        Employee.objects.create(firstname="John", lastname="Doe")
        e2 = Employee.objects.create(firstname="Jack", lastname="Jackson")
        e3 = Employee.objects.create(firstname="Jack", lastname="jackson")
        self.assertSequenceEqual(
            Employee.objects.filter(lastname__startswith=F('firstname')),
            [e2, e3] if connection.features.has_case_insensitive_like else [e2]
        )
        qs = Employee.objects.filter(lastname__istartswith=F('firstname')).order_by('pk')
        self.assertSequenceEqual(qs, [e2, e3])

    def test_ticket_18375_join_reuse(self):
        # Reverse multijoin F() references and the lookup target the same join.
        # Pre #18375 the F() join was generated first and the lookup couldn't
        # reuse that join.
        qs = Employee.objects.filter(company_ceo_set__num_chairs=F('company_ceo_set__num_employees'))
        self.assertEqual(str(qs.query).count('JOIN'), 1)

    def test_ticket_18375_kwarg_ordering(self):
        # The next query was dict-randomization dependent - if the "gte=1"
        # was seen first, then the F() will reuse the join generated by the
        # gte lookup, if F() was seen first, then it generated a join the
        # other lookups could not reuse.
        qs = Employee.objects.filter(
            company_ceo_set__num_chairs=F('company_ceo_set__num_employees'),
            company_ceo_set__num_chairs__gte=1,
        )
        self.assertEqual(str(qs.query).count('JOIN'), 1)

    def test_ticket_18375_kwarg_ordering_2(self):
        # Another similar case for F() than above. Now we have the same join
        # in two filter kwargs, one in the lhs lookup, one in F. Here pre
        # #18375 the amount of joins generated was random if dict
        # randomization was enabled, that is the generated query dependent
        # on which clause was seen first.
        qs = Employee.objects.filter(
            company_ceo_set__num_employees=F('pk'),
            pk=F('company_ceo_set__num_employees')
        )
        self.assertEqual(str(qs.query).count('JOIN'), 1)

    def test_ticket_18375_chained_filters(self):
        # F() expressions do not reuse joins from previous filter.
        qs = Employee.objects.filter(
            company_ceo_set__num_employees=F('pk')
        ).filter(
            company_ceo_set__num_employees=F('company_ceo_set__num_employees')
        )
        self.assertEqual(str(qs.query).count('JOIN'), 2)

    def test_order_by_exists(self):
        mary = Employee.objects.create(firstname='Mary', lastname='Mustermann', salary=20)
        mustermanns_by_seniority = Employee.objects.filter(lastname='Mustermann').order_by(
            # Order by whether the employee is the CEO of a company
            Exists(Company.objects.filter(ceo=OuterRef('pk'))).desc()
        )
        self.assertSequenceEqual(mustermanns_by_seniority, [self.max, mary])

    def test_order_by_multiline_sql(self):
        raw_order_by = (
            RawSQL('''
                CASE WHEN num_employees > 1000
                     THEN num_chairs
                     ELSE 0 END
            ''', []).desc(),
            RawSQL('''
                CASE WHEN num_chairs > 1
                     THEN 1
                     ELSE 0 END
            ''', []).asc()
        )
        for qs in (
            Company.objects.all(),
            Company.objects.distinct(),
        ):
            with self.subTest(qs=qs):
                self.assertSequenceEqual(
                    qs.order_by(*raw_order_by),
                    [self.example_inc, self.gmbh, self.foobar_ltd],
                )

    def test_outerref(self):
        inner = Company.objects.filter(point_of_contact=OuterRef('pk'))
        msg = (
            'This queryset contains a reference to an outer query and may only '
            'be used in a subquery.'
        )
        with self.assertRaisesMessage(ValueError, msg):
            inner.exists()

        outer = Employee.objects.annotate(is_point_of_contact=Exists(inner))
        self.assertIs(outer.exists(), True)

    def test_exist_single_field_output_field(self):
        queryset = Company.objects.values('pk')
        self.assertIsInstance(Exists(queryset).output_field, models.BooleanField)

    def test_subquery(self):
        Company.objects.filter(name='Example Inc.').update(
            point_of_contact=Employee.objects.get(firstname='Joe', lastname='Smith'),
            ceo=self.max,
        )
        Employee.objects.create(firstname='Bob', lastname='Brown', salary=40)
        qs = Employee.objects.annotate(
            is_point_of_contact=Exists(Company.objects.filter(point_of_contact=OuterRef('pk'))),
            is_not_point_of_contact=~Exists(Company.objects.filter(point_of_contact=OuterRef('pk'))),
            is_ceo_of_small_company=Exists(Company.objects.filter(num_employees__lt=200, ceo=OuterRef('pk'))),
            is_ceo_small_2=~~Exists(Company.objects.filter(num_employees__lt=200, ceo=OuterRef('pk'))),
            largest_company=Subquery(Company.objects.order_by('-num_employees').filter(
                models.Q(ceo=OuterRef('pk')) | models.Q(point_of_contact=OuterRef('pk'))
            ).values('name')[:1], output_field=models.CharField())
        ).values(
            'firstname',
            'is_point_of_contact',
            'is_not_point_of_contact',
            'is_ceo_of_small_company',
            'is_ceo_small_2',
            'largest_company',
        ).order_by('firstname')

        results = list(qs)
        # Could use Coalesce(subq, Value('')) instead except for the bug in
        # cx_Oracle mentioned in #23843.
        bob = results[0]
        if bob['largest_company'] == '' and connection.features.interprets_empty_strings_as_nulls:
            bob['largest_company'] = None

        self.assertEqual(results, [
            {
                'firstname': 'Bob',
                'is_point_of_contact': False,
                'is_not_point_of_contact': True,
                'is_ceo_of_small_company': False,
                'is_ceo_small_2': False,
                'largest_company': None,
            },
            {
                'firstname': 'Frank',
                'is_point_of_contact': False,
                'is_not_point_of_contact': True,
                'is_ceo_of_small_company': True,
                'is_ceo_small_2': True,
                'largest_company': 'Foobar Ltd.',
            },
            {
                'firstname': 'Joe',
                'is_point_of_contact': True,
                'is_not_point_of_contact': False,
                'is_ceo_of_small_company': False,
                'is_ceo_small_2': False,
                'largest_company': 'Example Inc.',
            },
            {
                'firstname': 'Max',
                'is_point_of_contact': False,
                'is_not_point_of_contact': True,
                'is_ceo_of_small_company': True,
                'is_ceo_small_2': True,
                'largest_company': 'Example Inc.'
            }
        ])
        # A less elegant way to write the same query: this uses a LEFT OUTER
        # JOIN and an IS NULL, inside a WHERE NOT IN which is probably less
        # efficient than EXISTS.
        self.assertCountEqual(
            qs.filter(is_point_of_contact=True).values('pk'),
            Employee.objects.exclude(company_point_of_contact_set=None).values('pk')
        )

    def test_in_subquery(self):
        # This is a contrived test (and you really wouldn't write this query),
        # but it is a succinct way to test the __in=Subquery() construct.
        small_companies = Company.objects.filter(num_employees__lt=200).values('pk')
        subquery_test = Company.objects.filter(pk__in=Subquery(small_companies))
        self.assertCountEqual(subquery_test, [self.foobar_ltd, self.gmbh])
        subquery_test2 = Company.objects.filter(pk=Subquery(small_companies.filter(num_employees=3)))
        self.assertCountEqual(subquery_test2, [self.foobar_ltd])

    def test_uuid_pk_subquery(self):
        u = UUIDPK.objects.create()
        UUID.objects.create(uuid_fk=u)
        qs = UUIDPK.objects.filter(id__in=Subquery(UUID.objects.values('uuid_fk__id')))
        self.assertCountEqual(qs, [u])

    def test_nested_subquery(self):
        inner = Company.objects.filter(point_of_contact=OuterRef('pk'))
        outer = Employee.objects.annotate(is_point_of_contact=Exists(inner))
        contrived = Employee.objects.annotate(
            is_point_of_contact=Subquery(
                outer.filter(pk=OuterRef('pk')).values('is_point_of_contact'),
                output_field=models.BooleanField(),
            ),
        )
        self.assertCountEqual(contrived.values_list(), outer.values_list())

    def test_nested_subquery_outer_ref_2(self):
        first = Time.objects.create(time='09:00')
        second = Time.objects.create(time='17:00')
        third = Time.objects.create(time='21:00')
        SimulationRun.objects.bulk_create([
            SimulationRun(start=first, end=second, midpoint='12:00'),
            SimulationRun(start=first, end=third, midpoint='15:00'),
            SimulationRun(start=second, end=first, midpoint='00:00'),
        ])
        inner = Time.objects.filter(time=OuterRef(OuterRef('time')), pk=OuterRef('start')).values('time')
        middle = SimulationRun.objects.annotate(other=Subquery(inner)).values('other')[:1]
        outer = Time.objects.annotate(other=Subquery(middle, output_field=models.TimeField()))
        # This is a contrived example. It exercises the double OuterRef form.
        self.assertCountEqual(outer, [first, second, third])

    def test_nested_subquery_outer_ref_with_autofield(self):
        first = Time.objects.create(time='09:00')
        second = Time.objects.create(time='17:00')
        SimulationRun.objects.create(start=first, end=second, midpoint='12:00')
        inner = SimulationRun.objects.filter(start=OuterRef(OuterRef('pk'))).values('start')
        middle = Time.objects.annotate(other=Subquery(inner)).values('other')[:1]
        outer = Time.objects.annotate(other=Subquery(middle, output_field=models.IntegerField()))
        # This exercises the double OuterRef form with AutoField as pk.
        self.assertCountEqual(outer, [first, second])

    def test_annotations_within_subquery(self):
        Company.objects.filter(num_employees__lt=50).update(ceo=Employee.objects.get(firstname='Frank'))
        inner = Company.objects.filter(
            ceo=OuterRef('pk')
        ).values('ceo').annotate(total_employees=models.Sum('num_employees')).values('total_employees')
        outer = Employee.objects.annotate(total_employees=Subquery(inner)).filter(salary__lte=Subquery(inner))
        self.assertSequenceEqual(
            outer.order_by('-total_employees').values('salary', 'total_employees'),
            [{'salary': 10, 'total_employees': 2300}, {'salary': 20, 'total_employees': 35}],
        )

    def test_subquery_references_joined_table_twice(self):
        inner = Company.objects.filter(
            num_chairs__gte=OuterRef('ceo__salary'),
            num_employees__gte=OuterRef('point_of_contact__salary'),
        )
        # Another contrived example (there is no need to have a subquery here)
        outer = Company.objects.filter(pk__in=Subquery(inner.values('pk')))
        self.assertFalse(outer.exists())

    def test_subquery_filter_by_aggregate(self):
        Number.objects.create(integer=1000, float=1.2)
        Employee.objects.create(salary=1000)
        qs = Number.objects.annotate(
            min_valuable_count=Subquery(
                Employee.objects.filter(
                    salary=OuterRef('integer'),
                ).annotate(cnt=Count('salary')).filter(cnt__gt=0).values('cnt')[:1]
            ),
        )
        self.assertEqual(qs.get().float, 1.2)

    def test_aggregate_subquery_annotation(self):
        with self.assertNumQueries(1) as ctx:
            aggregate = Company.objects.annotate(
                ceo_salary=Subquery(
                    Employee.objects.filter(
                        id=OuterRef('ceo_id'),
                    ).values('salary')
                ),
            ).aggregate(
                ceo_salary_gt_20=Count('pk', filter=Q(ceo_salary__gt=20)),
            )
        self.assertEqual(aggregate, {'ceo_salary_gt_20': 1})
        # Aggregation over a subquery annotation doesn't annotate the subquery
        # twice in the inner query.
        sql = ctx.captured_queries[0]['sql']
        self.assertLessEqual(sql.count('SELECT'), 3)
        # GROUP BY isn't required to aggregate over a query that doesn't
        # contain nested aggregates.
        self.assertNotIn('GROUP BY', sql)

    def test_explicit_output_field(self):
        class FuncA(Func):
            output_field = models.CharField()

        class FuncB(Func):
            pass

        expr = FuncB(FuncA())
        self.assertEqual(expr.output_field, FuncA.output_field)

    def test_outerref_mixed_case_table_name(self):
        inner = Result.objects.filter(result_time__gte=OuterRef('experiment__assigned'))
        outer = Result.objects.filter(pk__in=Subquery(inner.values('pk')))
        self.assertFalse(outer.exists())

    def test_outerref_with_operator(self):
        inner = Company.objects.filter(num_employees=OuterRef('ceo__salary') + 2)
        outer = Company.objects.filter(pk__in=Subquery(inner.values('pk')))
        self.assertEqual(outer.get().name, 'Test GmbH')

    def test_annotation_with_outerref(self):
        gmbh_salary = Company.objects.annotate(
            max_ceo_salary_raise=Subquery(
                Company.objects.annotate(
                    salary_raise=OuterRef('num_employees') + F('num_employees'),
                ).order_by('-salary_raise').values('salary_raise')[:1],
                output_field=models.IntegerField(),
            ),
        ).get(pk=self.gmbh.pk)
        self.assertEqual(gmbh_salary.max_ceo_salary_raise, 2332)

    def test_pickle_expression(self):
        expr = Value(1, output_field=models.IntegerField())
        expr.convert_value  # populate cached property
        self.assertEqual(pickle.loads(pickle.dumps(expr)), expr)

    def test_incorrect_field_in_F_expression(self):
        with self.assertRaisesMessage(FieldError, "Cannot resolve keyword 'nope' into field."):
            list(Employee.objects.filter(firstname=F('nope')))

    def test_incorrect_joined_field_in_F_expression(self):
        with self.assertRaisesMessage(FieldError, "Cannot resolve keyword 'nope' into field."):
            list(Company.objects.filter(ceo__pk=F('point_of_contact__nope')))

    def test_exists_in_filter(self):
        inner = Company.objects.filter(ceo=OuterRef('pk')).values('pk')
        qs1 = Employee.objects.filter(Exists(inner))
        qs2 = Employee.objects.annotate(found=Exists(inner)).filter(found=True)
        self.assertCountEqual(qs1, qs2)
        self.assertFalse(Employee.objects.exclude(Exists(inner)).exists())
        self.assertCountEqual(qs2, Employee.objects.exclude(~Exists(inner)))

    def test_subquery_in_filter(self):
        inner = Company.objects.filter(ceo=OuterRef('pk')).values('based_in_eu')
        self.assertSequenceEqual(
            Employee.objects.filter(Subquery(inner)),
            [self.foobar_ltd.ceo],
        )

    def test_case_in_filter_if_boolean_output_field(self):
        is_ceo = Company.objects.filter(ceo=OuterRef('pk'))
        is_poc = Company.objects.filter(point_of_contact=OuterRef('pk'))
        qs = Employee.objects.filter(
            Case(
                When(Exists(is_ceo), then=True),
                When(Exists(is_poc), then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
        )
        self.assertSequenceEqual(qs, [self.example_inc.ceo, self.foobar_ltd.ceo, self.max])

    def test_boolean_expression_combined(self):
        is_ceo = Company.objects.filter(ceo=OuterRef('pk'))
        is_poc = Company.objects.filter(point_of_contact=OuterRef('pk'))
        self.gmbh.point_of_contact = self.max
        self.gmbh.save()
        self.assertSequenceEqual(
            Employee.objects.filter(Exists(is_ceo) | Exists(is_poc)),
            [self.example_inc.ceo, self.foobar_ltd.ceo, self.max],
        )
        self.assertSequenceEqual(
            Employee.objects.filter(Exists(is_ceo) & Exists(is_poc)),
            [self.max],
        )
        self.assertSequenceEqual(
            Employee.objects.filter(Exists(is_ceo) & Q(salary__gte=30)),
            [self.max],
        )
        self.assertSequenceEqual(
            Employee.objects.filter(Exists(is_poc) | Q(salary__lt=15)),
            [self.example_inc.ceo, self.max],
        )


class IterableLookupInnerExpressionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ceo = Employee.objects.create(firstname='Just', lastname='Doit', salary=30)
        # MySQL requires that the values calculated for expressions don't pass
        # outside of the field's range, so it's inconvenient to use the values
        # in the more general tests.
        Company.objects.create(name='5020 Ltd', num_employees=50, num_chairs=20, ceo=ceo)
        Company.objects.create(name='5040 Ltd', num_employees=50, num_chairs=40, ceo=ceo)
        Company.objects.create(name='5050 Ltd', num_employees=50, num_chairs=50, ceo=ceo)
        Company.objects.create(name='5060 Ltd', num_employees=50, num_chairs=60, ceo=ceo)
        Company.objects.create(name='99300 Ltd', num_employees=99, num_chairs=300, ceo=ceo)

    def test_in_lookup_allows_F_expressions_and_expressions_for_integers(self):
        # __in lookups can use F() expressions for integers.
        queryset = Company.objects.filter(num_employees__in=([F('num_chairs') - 10]))
        self.assertQuerysetEqual(queryset, ['<Company: 5060 Ltd>'], ordered=False)
        self.assertQuerysetEqual(
            Company.objects.filter(num_employees__in=([F('num_chairs') - 10, F('num_chairs') + 10])),
            ['<Company: 5040 Ltd>', '<Company: 5060 Ltd>'],
            ordered=False
        )
        self.assertQuerysetEqual(
            Company.objects.filter(
                num_employees__in=([F('num_chairs') - 10, F('num_chairs'), F('num_chairs') + 10])
            ),
            ['<Company: 5040 Ltd>', '<Company: 5050 Ltd>', '<Company: 5060 Ltd>'],
            ordered=False
        )

    def test_expressions_in_lookups_join_choice(self):
        midpoint = datetime.time(13, 0)
        t1 = Time.objects.create(time=datetime.time(12, 0))
        t2 = Time.objects.create(time=datetime.time(14, 0))
        SimulationRun.objects.create(start=t1, end=t2, midpoint=midpoint)
        SimulationRun.objects.create(start=t1, end=None, midpoint=midpoint)
        SimulationRun.objects.create(start=None, end=t2, midpoint=midpoint)
        SimulationRun.objects.create(start=None, end=None, midpoint=midpoint)

        queryset = SimulationRun.objects.filter(midpoint__range=[F('start__time'), F('end__time')])
        self.assertQuerysetEqual(
            queryset,
            ['<SimulationRun: 13:00:00 (12:00:00 to 14:00:00)>'],
            ordered=False
        )
        for alias in queryset.query.alias_map.values():
            if isinstance(alias, Join):
                self.assertEqual(alias.join_type, constants.INNER)

        queryset = SimulationRun.objects.exclude(midpoint__range=[F('start__time'), F('end__time')])
        self.assertQuerysetEqual(queryset, [], ordered=False)
        for alias in queryset.query.alias_map.values():
            if isinstance(alias, Join):
                self.assertEqual(alias.join_type, constants.LOUTER)

    def test_range_lookup_allows_F_expressions_and_expressions_for_integers(self):
        # Range lookups can use F() expressions for integers.
        Company.objects.filter(num_employees__exact=F("num_chairs"))
        self.assertQuerysetEqual(
            Company.objects.filter(num_employees__range=(F('num_chairs'), 100)),
            ['<Company: 5020 Ltd>', '<Company: 5040 Ltd>', '<Company: 5050 Ltd>'],
            ordered=False
        )
        self.assertQuerysetEqual(
            Company.objects.filter(num_employees__range=(F('num_chairs') - 10, F('num_chairs') + 10)),
            ['<Company: 5040 Ltd>', '<Company: 5050 Ltd>', '<Company: 5060 Ltd>'],
            ordered=False
        )
        self.assertQuerysetEqual(
            Company.objects.filter(num_employees__range=(F('num_chairs') - 10, 100)),
            ['<Company: 5020 Ltd>', '<Company: 5040 Ltd>', '<Company: 5050 Ltd>', '<Company: 5060 Ltd>'],
            ordered=False
        )
        self.assertQuerysetEqual(
            Company.objects.filter(num_employees__range=(1, 100)),
            [
                '<Company: 5020 Ltd>', '<Company: 5040 Ltd>', '<Company: 5050 Ltd>',
                '<Company: 5060 Ltd>', '<Company: 99300 Ltd>',
            ],
            ordered=False
        )

    @unittest.skipUnless(connection.vendor == 'sqlite',
                         "This defensive test only works on databases that don't validate parameter types")
    def test_complex_expressions_do_not_introduce_sql_injection_via_untrusted_string_inclusion(self):
        """
        This tests that SQL injection isn't possible using compilation of
        expressions in iterable filters, as their compilation happens before
        the main query compilation. It's limited to SQLite, as PostgreSQL,
        Oracle and other vendors have defense in depth against this by type
        checking. Testing against SQLite (the most permissive of the built-in
        databases) demonstrates that the problem doesn't exist while keeping
        the test simple.
        """
        queryset = Company.objects.filter(name__in=[F('num_chairs') + '1)) OR ((1==1'])
        self.assertQuerysetEqual(queryset, [], ordered=False)

    def test_in_lookup_allows_F_expressions_and_expressions_for_datetimes(self):
        start = datetime.datetime(2016, 2, 3, 15, 0, 0)
        end = datetime.datetime(2016, 2, 5, 15, 0, 0)
        experiment_1 = Experiment.objects.create(
            name='Integrity testing',
            assigned=start.date(),
            start=start,
            end=end,
            completed=end.date(),
            estimated_time=end - start,
        )
        experiment_2 = Experiment.objects.create(
            name='Taste testing',
            assigned=start.date(),
            start=start,
            end=end,
            completed=end.date(),
            estimated_time=end - start,
        )
        Result.objects.create(
            experiment=experiment_1,
            result_time=datetime.datetime(2016, 2, 4, 15, 0, 0),
        )
        Result.objects.create(
            experiment=experiment_1,
            result_time=datetime.datetime(2016, 3, 10, 2, 0, 0),
        )
        Result.objects.create(
            experiment=experiment_2,
            result_time=datetime.datetime(2016, 1, 8, 5, 0, 0),
        )

        within_experiment_time = [F('experiment__start'), F('experiment__end')]
        queryset = Result.objects.filter(result_time__range=within_experiment_time)
        self.assertQuerysetEqual(queryset, ["<Result: Result at 2016-02-04 15:00:00>"])

        within_experiment_time = [F('experiment__start'), F('experiment__end')]
        queryset = Result.objects.filter(result_time__range=within_experiment_time)
        self.assertQuerysetEqual(queryset, ["<Result: Result at 2016-02-04 15:00:00>"])


class FTests(SimpleTestCase):

    def test_deepcopy(self):
        f = F("foo")
        g = deepcopy(f)
        self.assertEqual(f.name, g.name)

    def test_deconstruct(self):
        f = F('name')
        path, args, kwargs = f.deconstruct()
        self.assertEqual(path, 'django.db.models.expressions.F')
        self.assertEqual(args, (f.name,))
        self.assertEqual(kwargs, {})

    def test_equal(self):
        f = F('name')
        same_f = F('name')
        other_f = F('username')
        self.assertEqual(f, same_f)
        self.assertNotEqual(f, other_f)

    def test_hash(self):
        d = {F('name'): 'Bob'}
        self.assertIn(F('name'), d)
        self.assertEqual(d[F('name')], 'Bob')

    def test_not_equal_Value(self):
        f = F('name')
        value = Value('name')
        self.assertNotEqual(f, value)
        self.assertNotEqual(value, f)


class ExpressionsTests(TestCase):

    def test_F_reuse(self):
        f = F('id')
        n = Number.objects.create(integer=-1)
        c = Company.objects.create(
            name="Example Inc.", num_employees=2300, num_chairs=5,
            ceo=Employee.objects.create(firstname="Joe", lastname="Smith")
        )
        c_qs = Company.objects.filter(id=f)
        self.assertEqual(c_qs.get(), c)
        # Reuse the same F-object for another queryset
        n_qs = Number.objects.filter(id=f)
        self.assertEqual(n_qs.get(), n)
        # The original query still works correctly
        self.assertEqual(c_qs.get(), c)

    def test_patterns_escape(self):
        r"""
        Special characters (e.g. %, _ and \) stored in database are
        properly escaped when using a pattern lookup with an expression
        refs #16731
        """
        Employee.objects.bulk_create([
            Employee(firstname="%Joh\\nny", lastname="%Joh\\n"),
            Employee(firstname="Johnny", lastname="%John"),
            Employee(firstname="Jean-Claude", lastname="Claud_"),
            Employee(firstname="Jean-Claude", lastname="Claude"),
            Employee(firstname="Jean-Claude", lastname="Claude%"),
            Employee(firstname="Johnny", lastname="Joh\\n"),
            Employee(firstname="Johnny", lastname="John"),
            Employee(firstname="Johnny", lastname="_ohn"),
        ])

        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__contains=F('lastname')),
            ["<Employee: %Joh\\nny %Joh\\n>", "<Employee: Jean-Claude Claude>", "<Employee: Johnny John>"],
            ordered=False,
        )
        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__startswith=F('lastname')),
            ["<Employee: %Joh\\nny %Joh\\n>", "<Employee: Johnny John>"],
            ordered=False,
        )
        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__endswith=F('lastname')),
            ["<Employee: Jean-Claude Claude>"],
            ordered=False,
        )

    def test_insensitive_patterns_escape(self):
        r"""
        Special characters (e.g. %, _ and \) stored in database are
        properly escaped when using a case insensitive pattern lookup with an
        expression -- refs #16731
        """
        Employee.objects.bulk_create([
            Employee(firstname="%Joh\\nny", lastname="%joh\\n"),
            Employee(firstname="Johnny", lastname="%john"),
            Employee(firstname="Jean-Claude", lastname="claud_"),
            Employee(firstname="Jean-Claude", lastname="claude"),
            Employee(firstname="Jean-Claude", lastname="claude%"),
            Employee(firstname="Johnny", lastname="joh\\n"),
            Employee(firstname="Johnny", lastname="john"),
            Employee(firstname="Johnny", lastname="_ohn"),
        ])

        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__icontains=F('lastname')),
            ["<Employee: %Joh\\nny %joh\\n>", "<Employee: Jean-Claude claude>", "<Employee: Johnny john>"],
            ordered=False,
        )
        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__istartswith=F('lastname')),
            ["<Employee: %Joh\\nny %joh\\n>", "<Employee: Johnny john>"],
            ordered=False,
        )
        self.assertQuerysetEqual(
            Employee.objects.filter(firstname__iendswith=F('lastname')),
            ["<Employee: Jean-Claude claude>"],
            ordered=False,
        )


@isolate_apps('expressions')
class SimpleExpressionTests(SimpleTestCase):

    def test_equal(self):
        self.assertEqual(Expression(), Expression())
        self.assertEqual(
            Expression(models.IntegerField()),
            Expression(output_field=models.IntegerField())
        )
        self.assertEqual(Expression(models.IntegerField()), mock.ANY)
        self.assertNotEqual(
            Expression(models.IntegerField()),
            Expression(models.CharField())
        )

        class TestModel(models.Model):
            field = models.IntegerField()
            other_field = models.IntegerField()

        self.assertNotEqual(
            Expression(TestModel._meta.get_field('field')),
            Expression(TestModel._meta.get_field('other_field')),
        )

    def test_hash(self):
        self.assertEqual(hash(Expression()), hash(Expression()))
        self.assertEqual(
            hash(Expression(models.IntegerField())),
            hash(Expression(output_field=models.IntegerField()))
        )
        self.assertNotEqual(
            hash(Expression(models.IntegerField())),
            hash(Expression(models.CharField())),
        )

        class TestModel(models.Model):
            field = models.IntegerField()
            other_field = models.IntegerField()

        self.assertNotEqual(
            hash(Expression(TestModel._meta.get_field('field'))),
            hash(Expression(TestModel._meta.get_field('other_field'))),
        )


class ExpressionsNumericTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        Number(integer=-1).save()
        Number(integer=42).save()
        Number(integer=1337).save()
        Number.objects.update(float=F('integer'))

    def test_fill_with_value_from_same_object(self):
        """
        We can fill a value in all objects with an other value of the
        same object.
        """
        self.assertQuerysetEqual(
            Number.objects.all(),
            ['<Number: -1, -1.000>', '<Number: 42, 42.000>', '<Number: 1337, 1337.000>'],
            ordered=False
        )

    def test_increment_value(self):
        """
        We can increment a value of all objects in a query set.
        """
        self.assertEqual(Number.objects.filter(integer__gt=0).update(integer=F('integer') + 1), 2)
        self.assertQuerysetEqual(
            Number.objects.all(),
            ['<Number: -1, -1.000>', '<Number: 43, 42.000>', '<Number: 1338, 1337.000>'],
            ordered=False
        )

    def test_filter_not_equals_other_field(self):
        """
        We can filter for objects, where a value is not equals the value
        of an other field.
        """
        self.assertEqual(Number.objects.filter(integer__gt=0).update(integer=F('integer') + 1), 2)
        self.assertQuerysetEqual(
            Number.objects.exclude(float=F('integer')),
            ['<Number: 43, 42.000>', '<Number: 1338, 1337.000>'],
            ordered=False
        )

    def test_complex_expressions(self):
        """
        Complex expressions of different connection types are possible.
        """
        n = Number.objects.create(integer=10, float=123.45)
        self.assertEqual(Number.objects.filter(pk=n.pk).update(
            float=F('integer') + F('float') * 2), 1)

        self.assertEqual(Number.objects.get(pk=n.pk).integer, 10)
        self.assertEqual(Number.objects.get(pk=n.pk).float, Approximate(256.900, places=3))


class ExpressionOperatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.n = Number.objects.create(integer=42, float=15.5)
        cls.n1 = Number.objects.create(integer=-42, float=-15.5)

    def test_lefthand_addition(self):
        # LH Addition of floats and integers
        Number.objects.filter(pk=self.n.pk).update(
            integer=F('integer') + 15,
            float=F('float') + 42.7
        )

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 57)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(58.200, places=3))

    def test_lefthand_subtraction(self):
        # LH Subtraction of floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer') - 15, float=F('float') - 42.7)

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 27)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(-27.200, places=3))

    def test_lefthand_multiplication(self):
        # Multiplication of floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer') * 15, float=F('float') * 42.7)

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 630)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(661.850, places=3))

    def test_lefthand_division(self):
        # LH Division of floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer') / 2, float=F('float') / 42.7)

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 21)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(0.363, places=3))

    def test_lefthand_modulo(self):
        # LH Modulo arithmetic on integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer') % 20)

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 2)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(15.500, places=3))

    def test_lefthand_bitwise_and(self):
        # LH Bitwise ands on integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer').bitand(56))
        Number.objects.filter(pk=self.n1.pk).update(integer=F('integer').bitand(-56))

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 40)
        self.assertEqual(Number.objects.get(pk=self.n1.pk).integer, -64)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(15.500, places=3))

    def test_lefthand_bitwise_left_shift_operator(self):
        Number.objects.update(integer=F('integer').bitleftshift(2))
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 168)
        self.assertEqual(Number.objects.get(pk=self.n1.pk).integer, -168)

    def test_lefthand_bitwise_right_shift_operator(self):
        Number.objects.update(integer=F('integer').bitrightshift(2))
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 10)
        self.assertEqual(Number.objects.get(pk=self.n1.pk).integer, -11)

    def test_lefthand_bitwise_or(self):
        # LH Bitwise or on integers
        Number.objects.update(integer=F('integer').bitor(48))

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 58)
        self.assertEqual(Number.objects.get(pk=self.n1.pk).integer, -10)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(15.500, places=3))

    def test_lefthand_power(self):
        # LH Power arithmetic operation on floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=F('integer') ** 2, float=F('float') ** 1.5)
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 1764)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(61.02, places=2))

    def test_right_hand_addition(self):
        # Right hand operators
        Number.objects.filter(pk=self.n.pk).update(integer=15 + F('integer'), float=42.7 + F('float'))

        # RH Addition of floats and integers
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 57)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(58.200, places=3))

    def test_right_hand_subtraction(self):
        Number.objects.filter(pk=self.n.pk).update(integer=15 - F('integer'), float=42.7 - F('float'))

        # RH Subtraction of floats and integers
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, -27)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(27.200, places=3))

    def test_right_hand_multiplication(self):
        # RH Multiplication of floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=15 * F('integer'), float=42.7 * F('float'))

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 630)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(661.850, places=3))

    def test_right_hand_division(self):
        # RH Division of floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=640 / F('integer'), float=42.7 / F('float'))

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 15)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(2.755, places=3))

    def test_right_hand_modulo(self):
        # RH Modulo arithmetic on integers
        Number.objects.filter(pk=self.n.pk).update(integer=69 % F('integer'))

        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 27)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(15.500, places=3))

    def test_righthand_power(self):
        # RH Power arithmetic operation on floats and integers
        Number.objects.filter(pk=self.n.pk).update(integer=2 ** F('integer'), float=1.5 ** F('float'))
        self.assertEqual(Number.objects.get(pk=self.n.pk).integer, 4398046511104)
        self.assertEqual(Number.objects.get(pk=self.n.pk).float, Approximate(536.308, places=3))


class FTimeDeltaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sday = sday = datetime.date(2010, 6, 25)
        cls.stime = stime = datetime.datetime(2010, 6, 25, 12, 15, 30, 747000)
        midnight = datetime.time(0)

        delta0 = datetime.timedelta(0)
        delta1 = datetime.timedelta(microseconds=253000)
        delta2 = datetime.timedelta(seconds=44)
        delta3 = datetime.timedelta(hours=21, minutes=8)
        delta4 = datetime.timedelta(days=10)
        delta5 = datetime.timedelta(days=90)

        # Test data is set so that deltas and delays will be
        # strictly increasing.
        cls.deltas = []
        cls.delays = []
        cls.days_long = []

        # e0: started same day as assigned, zero duration
        end = stime + delta0
        e0 = Experiment.objects.create(
            name='e0', assigned=sday, start=stime, end=end,
            completed=end.date(), estimated_time=delta0,
        )
        cls.deltas.append(delta0)
        cls.delays.append(e0.start - datetime.datetime.combine(e0.assigned, midnight))
        cls.days_long.append(e0.completed - e0.assigned)

        # e1: started one day after assigned, tiny duration, data
        # set so that end time has no fractional seconds, which
        # tests an edge case on sqlite.
        delay = datetime.timedelta(1)
        end = stime + delay + delta1
        e1 = Experiment.objects.create(
            name='e1', assigned=sday, start=stime + delay, end=end,
            completed=end.date(), estimated_time=delta1,
        )
        cls.deltas.append(delta1)
        cls.delays.append(e1.start - datetime.datetime.combine(e1.assigned, midnight))
        cls.days_long.append(e1.completed - e1.assigned)

        # e2: started three days after assigned, small duration
        end = stime + delta2
        e2 = Experiment.objects.create(
            name='e2', assigned=sday - datetime.timedelta(3), start=stime,
            end=end, completed=end.date(), estimated_time=datetime.timedelta(hours=1),
        )
        cls.deltas.append(delta2)
        cls.delays.append(e2.start - datetime.datetime.combine(e2.assigned, midnight))
        cls.days_long.append(e2.completed - e2.assigned)

        # e3: started four days after assigned, medium duration
        delay = datetime.timedelta(4)
        end = stime + delay + delta3
        e3 = Experiment.objects.create(
            name='e3', assigned=sday, start=stime + delay, end=end,
            completed=end.date(), estimated_time=delta3,
        )
        cls.deltas.append(delta3)
        cls.delays.append(e3.start - datetime.datetime.combine(e3.assigned, midnight))
        cls.days_long.append(e3.completed - e3.assigned)

        # e4: started 10 days after assignment, long duration
        end = stime + delta4
        e4 = Experiment.objects.create(
            name='e4', assigned=sday - datetime.timedelta(10), start=stime,
            end=end, completed=end.date(), estimated_time=delta4 - datetime.timedelta(1),
        )
        cls.deltas.append(delta4)
        cls.delays.append(e4.start - datetime.datetime.combine(e4.assigned, midnight))
        cls.days_long.append(e4.completed - e4.assigned)

        # e5: started a month after assignment, very long duration
        delay = datetime.timedelta(30)
        end = stime + delay + delta5
        e5 = Experiment.objects.create(
            name='e5', assigned=sday, start=stime + delay, end=end,
            completed=end.date(), estimated_time=delta5,
        )
        cls.deltas.append(delta5)
        cls.delays.append(e5.start - datetime.datetime.combine(e5.assigned, midnight))
        cls.days_long.append(e5.completed - e5.assigned)

        cls.expnames = [e.name for e in Experiment.objects.all()]

    def test_multiple_query_compilation(self):
        # Ticket #21643
        queryset = Experiment.objects.filter(end__lt=F('start') + datetime.timedelta(hours=1))
        q1 = str(queryset.query)
        q2 = str(queryset.query)
        self.assertEqual(q1, q2)

    def test_query_clone(self):
        # Ticket #21643 - Crash when compiling query more than once
        qs = Experiment.objects.filter(end__lt=F('start') + datetime.timedelta(hours=1))
        qs2 = qs.all()
        list(qs)
        list(qs2)
        # Intentionally no assert

    def test_delta_add(self):
        for i, delta in enumerate(self.deltas):
            test_set = [e.name for e in Experiment.objects.filter(end__lt=F('start') + delta)]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [e.name for e in Experiment.objects.filter(end__lt=delta + F('start'))]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [e.name for e in Experiment.objects.filter(end__lte=F('start') + delta)]
            self.assertEqual(test_set, self.expnames[:i + 1])

    def test_delta_subtract(self):
        for i, delta in enumerate(self.deltas):
            test_set = [e.name for e in Experiment.objects.filter(start__gt=F('end') - delta)]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [e.name for e in Experiment.objects.filter(start__gte=F('end') - delta)]
            self.assertEqual(test_set, self.expnames[:i + 1])

    def test_exclude(self):
        for i, delta in enumerate(self.deltas):
            test_set = [e.name for e in Experiment.objects.exclude(end__lt=F('start') + delta)]
            self.assertEqual(test_set, self.expnames[i:])

            test_set = [e.name for e in Experiment.objects.exclude(end__lte=F('start') + delta)]
            self.assertEqual(test_set, self.expnames[i + 1:])

    def test_date_comparison(self):
        for i, days in enumerate(self.days_long):
            test_set = [e.name for e in Experiment.objects.filter(completed__lt=F('assigned') + days)]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [e.name for e in Experiment.objects.filter(completed__lte=F('assigned') + days)]
            self.assertEqual(test_set, self.expnames[:i + 1])

    @skipUnlessDBFeature("supports_mixed_date_datetime_comparisons")
    def test_mixed_comparisons1(self):
        for i, delay in enumerate(self.delays):
            test_set = [e.name for e in Experiment.objects.filter(assigned__gt=F('start') - delay)]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [e.name for e in Experiment.objects.filter(assigned__gte=F('start') - delay)]
            self.assertEqual(test_set, self.expnames[:i + 1])

    def test_mixed_comparisons2(self):
        for i, delay in enumerate(self.delays):
            delay = datetime.timedelta(delay.days)
            test_set = [e.name for e in Experiment.objects.filter(start__lt=F('assigned') + delay)]
            self.assertEqual(test_set, self.expnames[:i])

            test_set = [
                e.name for e in Experiment.objects.filter(start__lte=F('assigned') + delay + datetime.timedelta(1))
            ]
            self.assertEqual(test_set, self.expnames[:i + 1])

    def test_delta_update(self):
        for delta in self.deltas:
            exps = Experiment.objects.all()
            expected_durations = [e.duration() for e in exps]
            expected_starts = [e.start + delta for e in exps]
            expected_ends = [e.end + delta for e in exps]

            Experiment.objects.update(start=F('start') + delta, end=F('end') + delta)
            exps = Experiment.objects.all()
            new_starts = [e.start for e in exps]
            new_ends = [e.end for e in exps]
            new_durations = [e.duration() for e in exps]
            self.assertEqual(expected_starts, new_starts)
            self.assertEqual(expected_ends, new_ends)
            self.assertEqual(expected_durations, new_durations)

    def test_invalid_operator(self):
        with self.assertRaises(DatabaseError):
            list(Experiment.objects.filter(start=F('start') * datetime.timedelta(0)))

    def test_durationfield_add(self):
        zeros = [e.name for e in Experiment.objects.filter(start=F('start') + F('estimated_time'))]
        self.assertEqual(zeros, ['e0'])

        end_less = [e.name for e in Experiment.objects.filter(end__lt=F('start') + F('estimated_time'))]
        self.assertEqual(end_less, ['e2'])

        delta_math = [
            e.name for e in
            Experiment.objects.filter(end__gte=F('start') + F('estimated_time') + datetime.timedelta(hours=1))
        ]
        self.assertEqual(delta_math, ['e4'])

        queryset = Experiment.objects.annotate(shifted=ExpressionWrapper(
            F('start') + Value(None, output_field=models.DurationField()),
            output_field=models.DateTimeField(),
        ))
        self.assertIsNone(queryset.first().shifted)

    @skipUnlessDBFeature('supports_temporal_subtraction')
    def test_date_subtraction(self):
        queryset = Experiment.objects.annotate(
            completion_duration=ExpressionWrapper(
                F('completed') - F('assigned'), output_field=models.DurationField()
            )
        )

        at_least_5_days = {e.name for e in queryset.filter(completion_duration__gte=datetime.timedelta(days=5))}
        self.assertEqual(at_least_5_days, {'e3', 'e4', 'e5'})

        at_least_120_days = {e.name for e in queryset.filter(completion_duration__gte=datetime.timedelta(days=120))}
        self.assertEqual(at_least_120_days, {'e5'})

        less_than_5_days = {e.name for e in queryset.filter(completion_duration__lt=datetime.timedelta(days=5))}
        self.assertEqual(less_than_5_days, {'e0', 'e1', 'e2'})

        queryset = Experiment.objects.annotate(difference=ExpressionWrapper(
            F('completed') - Value(None, output_field=models.DateField()),
            output_field=models.DurationField(),
        ))
        self.assertIsNone(queryset.first().difference)

        queryset = Experiment.objects.annotate(shifted=ExpressionWrapper(
            F('completed') - Value(None, output_field=models.DurationField()),
            output_field=models.DateField(),
        ))
        self.assertIsNone(queryset.first().shifted)

    @skipUnlessDBFeature('supports_temporal_subtraction')
    def test_time_subtraction(self):
        Time.objects.create(time=datetime.time(12, 30, 15, 2345))
        queryset = Time.objects.annotate(
            difference=ExpressionWrapper(
                F('time') - Value(datetime.time(11, 15, 0), output_field=models.TimeField()),
                output_field=models.DurationField(),
            )
        )
        self.assertEqual(
            queryset.get().difference,
            datetime.timedelta(hours=1, minutes=15, seconds=15, microseconds=2345)
        )

        queryset = Time.objects.annotate(difference=ExpressionWrapper(
            F('time') - Value(None, output_field=models.TimeField()),
            output_field=models.DurationField(),
        ))
        self.assertIsNone(queryset.first().difference)

        queryset = Time.objects.annotate(shifted=ExpressionWrapper(
            F('time') - Value(None, output_field=models.DurationField()),
            output_field=models.TimeField(),
        ))
        self.assertIsNone(queryset.first().shifted)

    @skipUnlessDBFeature('supports_temporal_subtraction')
    def test_datetime_subtraction(self):
        under_estimate = [
            e.name for e in Experiment.objects.filter(estimated_time__gt=F('end') - F('start'))
        ]
        self.assertEqual(under_estimate, ['e2'])

        over_estimate = [
            e.name for e in Experiment.objects.filter(estimated_time__lt=F('end') - F('start'))
        ]
        self.assertEqual(over_estimate, ['e4'])

        queryset = Experiment.objects.annotate(difference=ExpressionWrapper(
            F('start') - Value(None, output_field=models.DateTimeField()),
            output_field=models.DurationField(),
        ))
        self.assertIsNone(queryset.first().difference)

        queryset = Experiment.objects.annotate(shifted=ExpressionWrapper(
            F('start') - Value(None, output_field=models.DurationField()),
            output_field=models.DateTimeField(),
        ))
        self.assertIsNone(queryset.first().shifted)

    @skipUnlessDBFeature('supports_temporal_subtraction')
    def test_datetime_subtraction_microseconds(self):
        delta = datetime.timedelta(microseconds=8999999999999999)
        Experiment.objects.update(end=F('start') + delta)
        qs = Experiment.objects.annotate(
            delta=ExpressionWrapper(F('end') - F('start'), output_field=models.DurationField())
        )
        for e in qs:
            self.assertEqual(e.delta, delta)

    def test_duration_with_datetime(self):
        # Exclude e1 which has very high precision so we can test this on all
        # backends regardless of whether or not it supports
        # microsecond_precision.
        over_estimate = Experiment.objects.exclude(name='e1').filter(
            completed__gt=self.stime + F('estimated_time'),
        ).order_by('name')
        self.assertQuerysetEqual(over_estimate, ['e3', 'e4', 'e5'], lambda e: e.name)

    def test_duration_with_datetime_microseconds(self):
        delta = datetime.timedelta(microseconds=8999999999999999)
        qs = Experiment.objects.annotate(dt=ExpressionWrapper(
            F('start') + delta,
            output_field=models.DateTimeField(),
        ))
        for e in qs:
            self.assertEqual(e.dt, e.start + delta)

    def test_date_minus_duration(self):
        more_than_4_days = Experiment.objects.filter(
            assigned__lt=F('completed') - Value(datetime.timedelta(days=4), output_field=models.DurationField())
        )
        self.assertQuerysetEqual(more_than_4_days, ['e3', 'e4', 'e5'], lambda e: e.name)

    def test_negative_timedelta_update(self):
        # subtract 30 seconds, 30 minutes, 2 hours and 2 days
        experiments = Experiment.objects.filter(name='e0').annotate(
            start_sub_seconds=F('start') + datetime.timedelta(seconds=-30),
        ).annotate(
            start_sub_minutes=F('start_sub_seconds') + datetime.timedelta(minutes=-30),
        ).annotate(
            start_sub_hours=F('start_sub_minutes') + datetime.timedelta(hours=-2),
        ).annotate(
            new_start=F('start_sub_hours') + datetime.timedelta(days=-2),
        )
        expected_start = datetime.datetime(2010, 6, 23, 9, 45, 0)
        # subtract 30 microseconds
        experiments = experiments.annotate(new_start=F('new_start') + datetime.timedelta(microseconds=-30))
        expected_start += datetime.timedelta(microseconds=+746970)
        experiments.update(start=F('new_start'))
        e0 = Experiment.objects.get(name='e0')
        self.assertEqual(e0.start, expected_start)


class ValueTests(TestCase):
    def test_update_TimeField_using_Value(self):
        Time.objects.create()
        Time.objects.update(time=Value(datetime.time(1), output_field=TimeField()))
        self.assertEqual(Time.objects.get().time, datetime.time(1))

    def test_update_UUIDField_using_Value(self):
        UUID.objects.create()
        UUID.objects.update(uuid=Value(uuid.UUID('12345678901234567890123456789012'), output_field=UUIDField()))
        self.assertEqual(UUID.objects.get().uuid, uuid.UUID('12345678901234567890123456789012'))

    def test_deconstruct(self):
        value = Value('name')
        path, args, kwargs = value.deconstruct()
        self.assertEqual(path, 'django.db.models.expressions.Value')
        self.assertEqual(args, (value.value,))
        self.assertEqual(kwargs, {})

    def test_deconstruct_output_field(self):
        value = Value('name', output_field=CharField())
        path, args, kwargs = value.deconstruct()
        self.assertEqual(path, 'django.db.models.expressions.Value')
        self.assertEqual(args, (value.value,))
        self.assertEqual(len(kwargs), 1)
        self.assertEqual(kwargs['output_field'].deconstruct(), CharField().deconstruct())

    def test_equal(self):
        value = Value('name')
        self.assertEqual(value, Value('name'))
        self.assertNotEqual(value, Value('username'))

    def test_hash(self):
        d = {Value('name'): 'Bob'}
        self.assertIn(Value('name'), d)
        self.assertEqual(d[Value('name')], 'Bob')

    def test_equal_output_field(self):
        value = Value('name', output_field=CharField())
        same_value = Value('name', output_field=CharField())
        other_value = Value('name', output_field=TimeField())
        no_output_field = Value('name')
        self.assertEqual(value, same_value)
        self.assertNotEqual(value, other_value)
        self.assertNotEqual(value, no_output_field)

    def test_raise_empty_expressionlist(self):
        msg = 'ExpressionList requires at least one expression'
        with self.assertRaisesMessage(ValueError, msg):
            ExpressionList()


class FieldTransformTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sday = sday = datetime.date(2010, 6, 25)
        cls.stime = stime = datetime.datetime(2010, 6, 25, 12, 15, 30, 747000)
        cls.ex1 = Experiment.objects.create(
            name='Experiment 1',
            assigned=sday,
            completed=sday + datetime.timedelta(2),
            estimated_time=datetime.timedelta(2),
            start=stime,
            end=stime + datetime.timedelta(2),
        )

    def test_month_aggregation(self):
        self.assertEqual(
            Experiment.objects.aggregate(month_count=Count('assigned__month')),
            {'month_count': 1}
        )

    def test_transform_in_values(self):
        self.assertQuerysetEqual(
            Experiment.objects.values('assigned__month'),
            ["{'assigned__month': 6}"]
        )

    def test_multiple_transforms_in_values(self):
        self.assertQuerysetEqual(
            Experiment.objects.values('end__date__month'),
            ["{'end__date__month': 6}"]
        )


class ReprTests(SimpleTestCase):

    def test_expressions(self):
        self.assertEqual(
            repr(Case(When(a=1))),
            "<Case: CASE WHEN <Q: (AND: ('a', 1))> THEN Value(None), ELSE Value(None)>"
        )
        self.assertEqual(
            repr(When(Q(age__gte=18), then=Value('legal'))),
            "<When: WHEN <Q: (AND: ('age__gte', 18))> THEN Value(legal)>"
        )
        self.assertEqual(repr(Col('alias', 'field')), "Col(alias, field)")
        self.assertEqual(repr(F('published')), "F(published)")
        self.assertEqual(repr(F('cost') + F('tax')), "<CombinedExpression: F(cost) + F(tax)>")
        self.assertEqual(
            repr(ExpressionWrapper(F('cost') + F('tax'), models.IntegerField())),
            "ExpressionWrapper(F(cost) + F(tax))"
        )
        self.assertEqual(repr(Func('published', function='TO_CHAR')), "Func(F(published), function=TO_CHAR)")
        self.assertEqual(repr(OrderBy(Value(1))), 'OrderBy(Value(1), descending=False)')
        self.assertEqual(repr(Random()), "Random()")
        self.assertEqual(repr(RawSQL('table.col', [])), "RawSQL(table.col, [])")
        self.assertEqual(repr(Ref('sum_cost', Sum('cost'))), "Ref(sum_cost, Sum(F(cost)))")
        self.assertEqual(repr(Value(1)), "Value(1)")
        self.assertEqual(
            repr(ExpressionList(F('col'), F('anothercol'))),
            'ExpressionList(F(col), F(anothercol))'
        )
        self.assertEqual(
            repr(ExpressionList(OrderBy(F('col'), descending=False))),
            'ExpressionList(OrderBy(F(col), descending=False))'
        )

    def test_functions(self):
        self.assertEqual(repr(Coalesce('a', 'b')), "Coalesce(F(a), F(b))")
        self.assertEqual(repr(Concat('a', 'b')), "Concat(ConcatPair(F(a), F(b)))")
        self.assertEqual(repr(Length('a')), "Length(F(a))")
        self.assertEqual(repr(Lower('a')), "Lower(F(a))")
        self.assertEqual(repr(Substr('a', 1, 3)), "Substr(F(a), Value(1), Value(3))")
        self.assertEqual(repr(Upper('a')), "Upper(F(a))")

    def test_aggregates(self):
        self.assertEqual(repr(Avg('a')), "Avg(F(a))")
        self.assertEqual(repr(Count('a')), "Count(F(a))")
        self.assertEqual(repr(Count('*')), "Count('*')")
        self.assertEqual(repr(Max('a')), "Max(F(a))")
        self.assertEqual(repr(Min('a')), "Min(F(a))")
        self.assertEqual(repr(StdDev('a')), "StdDev(F(a), sample=False)")
        self.assertEqual(repr(Sum('a')), "Sum(F(a))")
        self.assertEqual(repr(Variance('a', sample=True)), "Variance(F(a), sample=True)")

    def test_distinct_aggregates(self):
        self.assertEqual(repr(Count('a', distinct=True)), "Count(F(a), distinct=True)")
        self.assertEqual(repr(Count('*', distinct=True)), "Count('*', distinct=True)")

    def test_filtered_aggregates(self):
        filter = Q(a=1)
        self.assertEqual(repr(Avg('a', filter=filter)), "Avg(F(a), filter=(AND: ('a', 1)))")
        self.assertEqual(repr(Count('a', filter=filter)), "Count(F(a), filter=(AND: ('a', 1)))")
        self.assertEqual(repr(Max('a', filter=filter)), "Max(F(a), filter=(AND: ('a', 1)))")
        self.assertEqual(repr(Min('a', filter=filter)), "Min(F(a), filter=(AND: ('a', 1)))")
        self.assertEqual(repr(StdDev('a', filter=filter)), "StdDev(F(a), filter=(AND: ('a', 1)), sample=False)")
        self.assertEqual(repr(Sum('a', filter=filter)), "Sum(F(a), filter=(AND: ('a', 1)))")
        self.assertEqual(
            repr(Variance('a', sample=True, filter=filter)),
            "Variance(F(a), filter=(AND: ('a', 1)), sample=True)"
        )
        self.assertEqual(
            repr(Count('a', filter=filter, distinct=True)), "Count(F(a), distinct=True, filter=(AND: ('a', 1)))"
        )


class CombinableTests(SimpleTestCase):
    bitwise_msg = 'Use .bitand() and .bitor() for bitwise logical operations.'

    def test_negation(self):
        c = Combinable()
        self.assertEqual(-c, c * -1)

    def test_and(self):
        with self.assertRaisesMessage(NotImplementedError, self.bitwise_msg):
            Combinable() & Combinable()

    def test_or(self):
        with self.assertRaisesMessage(NotImplementedError, self.bitwise_msg):
            Combinable() | Combinable()

    def test_reversed_and(self):
        with self.assertRaisesMessage(NotImplementedError, self.bitwise_msg):
            object() & Combinable()

    def test_reversed_or(self):
        with self.assertRaisesMessage(NotImplementedError, self.bitwise_msg):
            object() | Combinable()
