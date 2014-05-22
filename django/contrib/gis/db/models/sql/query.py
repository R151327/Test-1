from django.db import connections
from django.db.models.query import sql
from django.db.models.sql.constants import QUERY_TERMS

from django.contrib.gis.db.models.fields import GeometryField
from django.contrib.gis.db.models.lookups import GISLookup
from django.contrib.gis.db.models.sql import aggregates as gis_aggregates
from django.contrib.gis.db.models.sql.conversion import GeomField


class GeoQuery(sql.Query):
    """
    A single spatial SQL query.
    """
    # Overridding the valid query terms.
    query_terms = QUERY_TERMS | set(GeometryField.class_lookups.keys())
    aggregates_module = gis_aggregates

    compiler = 'GeoSQLCompiler'

    #### Methods overridden from the base Query class ####
    def __init__(self, model):
        super(GeoQuery, self).__init__(model)
        # The following attributes are customized for the GeoQuerySet.
        # The SpatialBackend classes contain backend-specific routines and functions.
        self.custom_select = {}
        self.transformed_srid = None
        self.extra_select_fields = {}

    def clone(self, *args, **kwargs):
        obj = super(GeoQuery, self).clone(*args, **kwargs)
        # Customized selection dictionary and transformed srid flag have
        # to also be added to obj.
        obj.custom_select = self.custom_select.copy()
        obj.transformed_srid = self.transformed_srid
        obj.extra_select_fields = self.extra_select_fields.copy()
        return obj

    def get_aggregation(self, using, force_subq=False):
        # Remove any aggregates marked for reduction from the subquery
        # and move them to the outer AggregateQuery.
        connection = connections[using]
        for alias, aggregate in self.aggregate_select.items():
            if isinstance(aggregate, gis_aggregates.GeoAggregate):
                if not getattr(aggregate, 'is_extent', False) or connection.ops.oracle:
                    self.extra_select_fields[alias] = GeomField()
        return super(GeoQuery, self).get_aggregation(using, force_subq)

    def resolve_aggregate(self, value, aggregate, connection):
        """
        Overridden from GeoQuery's normalize to handle the conversion of
        GeoAggregate objects.
        """
        if isinstance(aggregate, self.aggregates_module.GeoAggregate):
            if aggregate.is_extent:
                if aggregate.is_extent == '3D':
                    return connection.ops.convert_extent3d(value)
                else:
                    return connection.ops.convert_extent(value)
            else:
                return connection.ops.convert_geom(value, aggregate.source)
        else:
            return super(GeoQuery, self).resolve_aggregate(value, aggregate, connection)

    # Private API utilities, subject to change.
    def _geo_field(self, field_name=None):
        """
        Returns the first Geometry field encountered; or specified via the
        `field_name` keyword.  The `field_name` may be a string specifying
        the geometry field on this GeoQuery's model, or a lookup string
        to a geometry field via a ForeignKey relation.
        """
        if field_name is None:
            # Incrementing until the first geographic field is found.
            for fld in self.model._meta.fields:
                if isinstance(fld, GeometryField):
                    return fld
            return False
        else:
            # Otherwise, check by the given field name -- which may be
            # a lookup to a _related_ geographic field.
            return GISLookup._check_geo_field(self.model._meta, field_name)
