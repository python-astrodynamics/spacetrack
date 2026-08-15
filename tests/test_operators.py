import datetime as dt

import pytest

import spacetrack.operators as op
from spacetrack.operators import _stringify_predicate_value

stringify_data = [
    (True, "true"),
    (False, "false"),
    ([1, 2], "1,2"),
    (["a", "b"], "a,b"),
    ({1}, "1"),
    (frozenset(["a"]), "a"),
    ((dt.date(2001, 2, 3), dt.date(2004, 5, 6)), "2001-02-03,2004-05-06"),
    (dt.datetime(2001, 2, 3, 4, 5, 6), "2001-02-03 04:05:06"),
    (dt.datetime(2001, 2, 3, tzinfo=dt.timezone.utc), "2001-02-03 00:00:00"),
    (dt.date(2001, 2, 3), "2001-02-03"),
    (None, "null-val"),
]


@pytest.mark.parametrize("value, expected", stringify_data)
def test_stringify_predicate_value(value, expected):
    assert _stringify_predicate_value(value) == expected


@pytest.mark.parametrize("value", [b"abc", bytearray(b"abc"), memoryview(b"abc")])
def test_stringify_predicate_value_rejects_bytes(value):
    # bytes would otherwise be serialised as comma-joined integer ordinals.
    with pytest.raises(TypeError):
        _stringify_predicate_value(value)


operator_data = [
    (op.greater_than, "test", ">test"),
    (op.less_than, "test", "<test"),
    (op.not_equal, "test", "<>test"),
    (op.like, "test", "~~test"),
    (op.startswith, "test", "^test"),
]


@pytest.mark.parametrize("function, value, expected", operator_data)
def test_operators(function, value, expected):
    assert function(value) == expected


def test_inclusive_range():
    assert op.inclusive_range("a", "b") == "a--b"
