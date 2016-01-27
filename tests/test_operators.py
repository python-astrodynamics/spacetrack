# coding: utf-8
from __future__ import absolute_import, division, print_function

import datetime as dt

import pytest
from spacetrack.operators import _stringify_predicate_value

stringify_data = [
    (True, 'true'),
    (False, 'false'),
    ([1, 2], '1,2'),
    (['a', 'b'], 'a,b'),
    ((dt.date(2001, 2, 3), dt.date(2004, 5, 6)), '2001-02-03,2004-05-06'),
    (dt.datetime(2001, 2, 3, 4, 5, 6), '2001-02-03 04:05:06'),
    (dt.date(2001, 2, 3), '2001-02-03'),
    (None, 'null-val'),
]


@pytest.mark.parametrize('value, expected', stringify_data)
def test_stringify_predicate_value(value, expected):
    assert _stringify_predicate_value(value) == expected
