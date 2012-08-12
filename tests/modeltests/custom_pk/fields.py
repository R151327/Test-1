import random
import string

from django.db import models
from django.utils import six
from django.utils.encoding import python_2_unicode_compatible


@python_2_unicode_compatible
class MyWrapper(object):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.value)

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.value == other.value
        return self.value == other

class MyAutoField(models.CharField):
    __metaclass__ = models.SubfieldBase

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 10
        super(MyAutoField, self).__init__(*args, **kwargs)

    def pre_save(self, instance, add):
        value = getattr(instance, self.attname, None)
        if not value:
            value = MyWrapper(''.join(random.sample(string.lowercase, 10)))
            setattr(instance, self.attname, value)
        return value

    def to_python(self, value):
        if not value:
            return
        if not isinstance(value, MyWrapper):
            value = MyWrapper(value)
        return value

    def get_db_prep_save(self, value, connection):
        if not value:
            return
        if isinstance(value, MyWrapper):
            return six.text_type(value)
        return value

    def get_db_prep_value(self, value, connection, prepared=False):
        if not value:
            return
        if isinstance(value, MyWrapper):
            return six.text_type(value)
        return value
