import copy
import datetime

from django.conf import settings
from django.core.exceptions import FieldError
from django.db.backends import utils as backend_utils
from django.db.models import fields
from django.db.models.constants import LOOKUP_SEP
from django.db.models.query_utils import refs_aggregate
from django.utils import timezone
from django.utils.functional import cached_property


class CombinableMixin(object):
    """
    Provides the ability to combine one or two objects with
    some connector. For example F('foo') + F('bar').
    """

    # Arithmetic connectors
    ADD = '+'
    SUB = '-'
    MUL = '*'
    DIV = '/'
    POW = '^'
    # The following is a quoted % operator - it is quoted because it can be
    # used in strings that also have parameter substitution.
    MOD = '%%'

    # Bitwise operators - note that these are generated by .bitand()
    # and .bitor(), the '&' and '|' are reserved for boolean operator
    # usage.
    BITAND = '&'
    BITOR = '|'

    def _combine(self, other, connector, reversed, node=None):
        if not hasattr(other, 'resolve_expression'):
            # everything must be resolvable to an expression
            if isinstance(other, datetime.timedelta):
                other = DurationValue(other, output_field=fields.DurationField())
            else:
                other = Value(other)

        if reversed:
            return Expression(other, connector, self)
        return Expression(self, connector, other)

    #############
    # OPERATORS #
    #############

    def __add__(self, other):
        return self._combine(other, self.ADD, False)

    def __sub__(self, other):
        return self._combine(other, self.SUB, False)

    def __mul__(self, other):
        return self._combine(other, self.MUL, False)

    def __truediv__(self, other):
        return self._combine(other, self.DIV, False)

    def __div__(self, other):  # Python 2 compatibility
        return type(self).__truediv__(self, other)

    def __mod__(self, other):
        return self._combine(other, self.MOD, False)

    def __pow__(self, other):
        return self._combine(other, self.POW, False)

    def __and__(self, other):
        raise NotImplementedError(
            "Use .bitand() and .bitor() for bitwise logical operations."
        )

    def bitand(self, other):
        return self._combine(other, self.BITAND, False)

    def __or__(self, other):
        raise NotImplementedError(
            "Use .bitand() and .bitor() for bitwise logical operations."
        )

    def bitor(self, other):
        return self._combine(other, self.BITOR, False)

    def __radd__(self, other):
        return self._combine(other, self.ADD, True)

    def __rsub__(self, other):
        return self._combine(other, self.SUB, True)

    def __rmul__(self, other):
        return self._combine(other, self.MUL, True)

    def __rtruediv__(self, other):
        return self._combine(other, self.DIV, True)

    def __rdiv__(self, other):  # Python 2 compatibility
        return type(self).__rtruediv__(self, other)

    def __rmod__(self, other):
        return self._combine(other, self.MOD, True)

    def __rpow__(self, other):
        return self._combine(other, self.POW, True)

    def __rand__(self, other):
        raise NotImplementedError(
            "Use .bitand() and .bitor() for bitwise logical operations."
        )

    def __ror__(self, other):
        raise NotImplementedError(
            "Use .bitand() and .bitor() for bitwise logical operations."
        )


class ExpressionNode(CombinableMixin):
    """
    Base class for all query expressions.
    """

    # aggregate specific fields
    is_summary = False

    def get_db_converters(self, connection):
        return [self.convert_value]

    def __init__(self, output_field=None):
        self._output_field = output_field

    def get_source_expressions(self):
        return []

    def set_source_expressions(self, exprs):
        assert len(exprs) == 0

    def as_sql(self, compiler, connection):
        """
        Responsible for returning a (sql, [params]) tuple to be included
        in the current query.

        Different backends can provide their own implementation, by
        providing an `as_{vendor}` method and patching the Expression:

        ```
        def override_as_sql(self, compiler, connection):
            # custom logic
            return super(ExpressionNode, self).as_sql(compiler, connection)
        setattr(ExpressionNode, 'as_' + connection.vendor, override_as_sql)
        ```

        Arguments:
         * compiler: the query compiler responsible for generating the query.
           Must have a compile method, returning a (sql, [params]) tuple.
           Calling compiler(value) will return a quoted `value`.

         * connection: the database connection used for the current query.

        Returns: (sql, params)
          Where `sql` is a string containing ordered sql parameters to be
          replaced with the elements of the list `params`.
        """
        raise NotImplementedError("Subclasses must implement as_sql()")

    @cached_property
    def contains_aggregate(self):
        for expr in self.get_source_expressions():
            if expr and expr.contains_aggregate:
                return True
        return False

    def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False):
        """
        Provides the chance to do any preprocessing or validation before being
        added to the query.

        Arguments:
         * query: the backend query implementation
         * allow_joins: boolean allowing or denying use of joins
           in this query
         * reuse: a set of reusable joins for multijoins
         * summarize: a terminal aggregate clause

        Returns: an ExpressionNode to be added to the query.
        """
        c = self.copy()
        c.is_summary = summarize
        return c

    def _prepare(self):
        """
        Hook used by Field.get_prep_lookup() to do custom preparation.
        """
        return self

    @property
    def field(self):
        return self.output_field

    @cached_property
    def output_field(self):
        """
        Returns the output type of this expressions.
        """
        if self._output_field_or_none is None:
            raise FieldError("Cannot resolve expression type, unknown output_field")
        return self._output_field_or_none

    @cached_property
    def _output_field_or_none(self):
        """
        Returns the output field of this expression, or None if no output type
        can be resolved. Note that the 'output_field' property will raise
        FieldError if no type can be resolved, but this attribute allows for
        None values.
        """
        if self._output_field is None:
            self._resolve_output_field()
        return self._output_field

    def _resolve_output_field(self):
        """
        Attempts to infer the output type of the expression. If the output
        fields of all source fields match then we can simply infer the same
        type here.
        """
        if self._output_field is None:
            sources = self.get_source_fields()
            num_sources = len(sources)
            if num_sources == 0:
                self._output_field = None
            else:
                self._output_field = sources[0]
                for source in sources:
                    if source is not None and not isinstance(self._output_field, source.__class__):
                        raise FieldError(
                            "Expression contains mixed types. You must set output_field")

    def convert_value(self, value, connection):
        """
        Expressions provide their own converters because users have the option
        of manually specifying the output_field which may be a different type
        from the one the database returns.
        """
        field = self.output_field
        internal_type = field.get_internal_type()
        if value is None:
            return value
        elif internal_type == 'FloatField':
            return float(value)
        elif internal_type.endswith('IntegerField'):
            return int(value)
        elif internal_type == 'DecimalField':
            return backend_utils.typecast_decimal(value)
        return value

    def get_lookup(self, lookup):
        return self.output_field.get_lookup(lookup)

    def get_transform(self, name):
        return self.output_field.get_transform(name)

    def relabeled_clone(self, change_map):
        clone = self.copy()
        clone.set_source_expressions(
            [e.relabeled_clone(change_map) for e in self.get_source_expressions()])
        return clone

    def copy(self):
        c = copy.copy(self)
        c.copied = True
        return c

    def refs_aggregate(self, existing_aggregates):
        """
        Does this expression contain a reference to some of the
        existing aggregates? If so, returns the aggregate and also
        the lookup parts that *weren't* found. So, if
            exsiting_aggregates = {'max_id': Max('id')}
            self.name = 'max_id'
            queryset.filter(max_id__range=[10,100])
        then this method will return Max('id') and those parts of the
        name that weren't found. In this case `max_id` is found and the range
        portion is returned as ('range',).
        """
        for node in self.get_source_expressions():
            agg, lookup = node.refs_aggregate(existing_aggregates)
            if agg:
                return agg, lookup
        return False, ()

    def refs_field(self, aggregate_types, field_types):
        """
        Helper method for check_aggregate_support on backends
        """
        return any(
            node.refs_field(aggregate_types, field_types)
            for node in self.get_source_expressions())

    def prepare_database_save(self, field):
        return self

    def get_group_by_cols(self):
        cols = []
        for source in self.get_source_expressions():
            cols.extend(source.get_group_by_cols())
        return cols

    def get_source_fields(self):
        """
        Returns the underlying field types used by this
        aggregate.
        """
        return [e._output_field_or_none for e in self.get_source_expressions()]


class Expression(ExpressionNode):

    def __init__(self, lhs, connector, rhs, output_field=None):
        super(Expression, self).__init__(output_field=output_field)
        self.connector = connector
        self.lhs = lhs
        self.rhs = rhs

    def get_source_expressions(self):
        return [self.lhs, self.rhs]

    def set_source_expressions(self, exprs):
        self.lhs, self.rhs = exprs

    def as_sql(self, compiler, connection):
        try:
            lhs_output = self.lhs.output_field
        except FieldError:
            lhs_output = None
        try:
            rhs_output = self.rhs.output_field
        except FieldError:
            rhs_output = None
        if (not connection.features.has_native_duration_field and
                ((lhs_output and lhs_output.get_internal_type() == 'DurationField')
                or (rhs_output and rhs_output.get_internal_type() == 'DurationField'))):
            return DurationExpression(self.lhs, self.connector, self.rhs).as_sql(compiler, connection)
        expressions = []
        expression_params = []
        sql, params = compiler.compile(self.lhs)
        expressions.append(sql)
        expression_params.extend(params)
        sql, params = compiler.compile(self.rhs)
        expressions.append(sql)
        expression_params.extend(params)
        # order of precedence
        expression_wrapper = '(%s)'
        sql = connection.ops.combine_expression(self.connector, expressions)
        return expression_wrapper % sql, expression_params

    def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False):
        c = self.copy()
        c.is_summary = summarize
        c.lhs = c.lhs.resolve_expression(query, allow_joins, reuse, summarize)
        c.rhs = c.rhs.resolve_expression(query, allow_joins, reuse, summarize)
        return c


class DurationExpression(Expression):
    def compile(self, side, compiler, connection):
        if not isinstance(side, DurationValue):
            try:
                output = side.output_field
            except FieldError:
                pass
            if output.get_internal_type() == 'DurationField':
                sql, params = compiler.compile(side)
                return connection.ops.format_for_duration_arithmetic(sql), params
        return compiler.compile(side)

    def as_sql(self, compiler, connection):
        expressions = []
        expression_params = []
        sql, params = self.compile(self.lhs, compiler, connection)
        expressions.append(sql)
        expression_params.extend(params)
        sql, params = self.compile(self.rhs, compiler, connection)
        expressions.append(sql)
        expression_params.extend(params)
        # order of precedence
        expression_wrapper = '(%s)'
        sql = connection.ops.combine_duration_expression(self.connector, expressions)
        return expression_wrapper % sql, expression_params


class F(CombinableMixin):
    """
    An object capable of resolving references to existing query objects.
    """
    def __init__(self, name):
        """
        Arguments:
         * name: the name of the field this expression references
        """
        self.name = name

    def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False):
        return query.resolve_ref(self.name, allow_joins, reuse, summarize)

    def refs_aggregate(self, existing_aggregates):
        return refs_aggregate(self.name.split(LOOKUP_SEP), existing_aggregates)


class Func(ExpressionNode):
    """
    A SQL function call.
    """
    function = None
    template = '%(function)s(%(expressions)s)'
    arg_joiner = ', '

    def __init__(self, *expressions, **extra):
        output_field = extra.pop('output_field', None)
        super(Func, self).__init__(output_field=output_field)
        self.source_expressions = self._parse_expressions(*expressions)
        self.extra = extra

    def get_source_expressions(self):
        return self.source_expressions

    def set_source_expressions(self, exprs):
        self.source_expressions = exprs

    def _parse_expressions(self, *expressions):
        return [
            arg if hasattr(arg, 'resolve_expression') else F(arg)
            for arg in expressions
        ]

    def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False):
        c = self.copy()
        c.is_summary = summarize
        for pos, arg in enumerate(c.source_expressions):
            c.source_expressions[pos] = arg.resolve_expression(query, allow_joins, reuse, summarize)
        return c

    def as_sql(self, compiler, connection, function=None, template=None):
        sql_parts = []
        params = []
        for arg in self.source_expressions:
            arg_sql, arg_params = compiler.compile(arg)
            sql_parts.append(arg_sql)
            params.extend(arg_params)
        if function is None:
            self.extra['function'] = self.extra.get('function', self.function)
        else:
            self.extra['function'] = function
        self.extra['expressions'] = self.extra['field'] = self.arg_joiner.join(sql_parts)
        template = template or self.extra.get('template', self.template)
        return template % self.extra, params

    def copy(self):
        copy = super(Func, self).copy()
        copy.source_expressions = self.source_expressions[:]
        copy.extra = self.extra.copy()
        return copy


class Value(ExpressionNode):
    """
    Represents a wrapped value as a node within an expression
    """
    def __init__(self, value, output_field=None):
        """
        Arguments:
         * value: the value this expression represents. The value will be
           added into the sql parameter list and properly quoted.

         * output_field: an instance of the model field type that this
           expression will return, such as IntegerField() or CharField().
        """
        super(Value, self).__init__(output_field=output_field)
        self.value = value

    def as_sql(self, compiler, connection):
        return '%s', [self.value]


class DurationValue(Value):
    def as_sql(self, compiler, connection):
        if (connection.features.has_native_duration_field and
                connection.features.driver_supports_timedelta_args):
            return super(DurationValue, self).as_sql(compiler, connection)
        return connection.ops.date_interval_sql(self.value)


class Col(ExpressionNode):
    def __init__(self, alias, target, source=None):
        if source is None:
            source = target
        super(Col, self).__init__(output_field=source)
        self.alias, self.target = alias, target

    def as_sql(self, compiler, connection):
        qn = compiler.quote_name_unless_alias
        return "%s.%s" % (qn(self.alias), qn(self.target.column)), []

    def relabeled_clone(self, relabels):
        return self.__class__(relabels.get(self.alias, self.alias), self.target, self.output_field)

    def get_group_by_cols(self):
        return [self]


class Ref(ExpressionNode):
    """
    Reference to column alias of the query. For example, Ref('sum_cost') in
    qs.annotate(sum_cost=Sum('cost')) query.
    """
    def __init__(self, refs, source):
        super(Ref, self).__init__()
        self.source = source
        self.refs = refs

    def get_source_expressions(self):
        return [self.source]

    def set_source_expressions(self, exprs):
        self.source, = exprs

    def relabeled_clone(self, relabels):
        return self

    def as_sql(self, compiler, connection):
        return "%s" % compiler.quote_name_unless_alias(self.refs), []

    def get_group_by_cols(self):
        return [self]


class Date(ExpressionNode):
    """
    Add a date selection column.
    """
    def __init__(self, lookup, lookup_type):
        super(Date, self).__init__(output_field=fields.DateField())
        self.lookup = lookup
        self.col = None
        self.lookup_type = lookup_type

    def get_source_expressions(self):
        return [self.col]

    def set_source_expressions(self, exprs):
        self.col, = exprs

    def resolve_expression(self, query, allow_joins, reuse, summarize):
        copy = self.copy()
        copy.col = query.resolve_ref(self.lookup, allow_joins, reuse, summarize)
        field = copy.col.output_field
        assert isinstance(field, fields.DateField), "%r isn't a DateField." % field.name
        if settings.USE_TZ:
            assert not isinstance(field, fields.DateTimeField), (
                "%r is a DateTimeField, not a DateField." % field.name
            )
        return copy

    def as_sql(self, compiler, connection):
        sql, params = self.col.as_sql(compiler, connection)
        assert not(params)
        return connection.ops.date_trunc_sql(self.lookup_type, sql), []

    def copy(self):
        copy = super(Date, self).copy()
        copy.lookup = self.lookup
        copy.lookup_type = self.lookup_type
        return copy

    def convert_value(self, value, connection):
        if isinstance(value, datetime.datetime):
            value = value.date()
        return value


class DateTime(ExpressionNode):
    """
    Add a datetime selection column.
    """
    def __init__(self, lookup, lookup_type, tzinfo):
        super(DateTime, self).__init__(output_field=fields.DateTimeField())
        self.lookup = lookup
        self.col = None
        self.lookup_type = lookup_type
        if tzinfo is None:
            self.tzname = None
        else:
            self.tzname = timezone._get_timezone_name(tzinfo)
        self.tzinfo = tzinfo

    def get_source_expressions(self):
        return [self.col]

    def set_source_expressions(self, exprs):
        self.col, = exprs

    def resolve_expression(self, query, allow_joins, reuse, summarize):
        copy = self.copy()
        copy.col = query.resolve_ref(self.lookup, allow_joins, reuse, summarize)
        field = copy.col.output_field
        assert isinstance(field, fields.DateTimeField), (
            "%r isn't a DateTimeField." % field.name
        )
        return copy

    def as_sql(self, compiler, connection):
        sql, params = self.col.as_sql(compiler, connection)
        assert not(params)
        return connection.ops.datetime_trunc_sql(self.lookup_type, sql, self.tzname)

    def copy(self):
        copy = super(DateTime, self).copy()
        copy.lookup = self.lookup
        copy.lookup_type = self.lookup_type
        copy.tzname = self.tzname
        return copy

    def convert_value(self, value, connection):
        if settings.USE_TZ:
            if value is None:
                raise ValueError(
                    "Database returned an invalid value in QuerySet.datetimes(). "
                    "Are time zone definitions for your database and pytz installed?"
                )
            value = value.replace(tzinfo=None)
            value = timezone.make_aware(value, self.tzinfo)
        return value
