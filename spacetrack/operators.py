# coding: utf-8
from __future__ import absolute_import, division, print_function

import datetime
from collections import Sequence

import six


def greater_than(value):
    """``'>value'``."""
    return '>' + _stringify_predicate_value(value)


def less_than(value):
    """``'<value'``."""
    return '<' + _stringify_predicate_value(value)


def not_equal(value):
    """``'<>value'``."""
    return '<>' + _stringify_predicate_value(value)


def inclusive_range(left, right):
    """``'left--right'``."""
    return (_stringify_predicate_value(left) + '--' +
            _stringify_predicate_value(right))


def like(value):
    """``'~~value'``."""
    return '~~' + _stringify_predicate_value(value)


def startswith(value):
    """``'^value'``."""
    return '^' + _stringify_predicate_value(value)


def _stringify_predicate_value(value):
    """Convert Python objects to Space-Track compatible strings

    - Booleans (``True`` -> ``'true'``)
    - Sequences (``[25544, 34602]`` -> ``'25544,34602'``)
    - dates/datetimes (``date(2015, 12, 23)`` -> ``'2015-12-23'``)
    - ``None`` -> ``'null-val'``
    """
    if isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, Sequence) and not isinstance(value, six.string_types):
        return ','.join(_stringify_predicate_value(x) for x in value)
    elif isinstance(value, datetime.datetime):
        return value.isoformat(sep=' ')
    elif isinstance(value, datetime.date):
        return value.isoformat()
    elif value is None:
        return 'null-val'
    else:
        return str(value)
