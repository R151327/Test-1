# -*- encoding: utf-8 -*-
# This file is distributed under the same license as the Django package.
#
from __future__ import unicode_literals

# The *_FORMAT strings use the Django date format syntax,
# see http://docs.djangoproject.com/en/dev/ref/templates/builtins/#date
DATE_FORMAT = 'Y. F j.'
TIME_FORMAT = 'G.i'
DATETIME_FORMAT = 'Y. F j. G.i'
YEAR_MONTH_FORMAT = 'Y. F'
MONTH_DAY_FORMAT = 'F j.'
SHORT_DATE_FORMAT = 'Y.m.d.'
SHORT_DATETIME_FORMAT = 'Y.m.d. G.i'
FIRST_DAY_OF_WEEK = 1  # Monday

# The *_INPUT_FORMATS strings use the Python strftime format syntax,
# see http://docs.python.org/library/datetime.html#strftime-strptime-behavior
DATE_INPUT_FORMATS = (
    '%Y.%m.%d.',  # '2006.10.25.'
)
TIME_INPUT_FORMATS = (
    '%H.%M.%S',  # '14.30.59'
    '%H.%M',    # '14.30'
)
DATETIME_INPUT_FORMATS = (
    '%Y.%m.%d. %H.%M.%S',   # '2006.10.25. 14.30.59'
    '%Y.%m.%d. %H.%M.%S.%f',  # '2006.10.25. 14.30.59.000200'
    '%Y.%m.%d. %H.%M',      # '2006.10.25. 14.30'
    '%Y.%m.%d.',            # '2006.10.25.'
)
DECIMAL_SEPARATOR = ','
THOUSAND_SEPARATOR = ' '  # Non-breaking space
NUMBER_GROUPING = 3
