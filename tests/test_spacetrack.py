# coding: utf-8
from __future__ import absolute_import, division, print_function

import json

import pytest
import responses
from requests import Response
from spacetrack import AuthenticationError, SpaceTrackClient
from spacetrack.base import (
    Predicate, _iter_content_generator, _iter_lines_generator)

try:
    from unittest.mock import call, patch
except ImportError:
    from mock import call, patch


def test_iter_lines_generator():
    """Test that lines are split correctly."""
    def mock_iter_content(self, chunk_size, decode_unicode):
        for chunk in ['1\r\n2\r\n', '3\r', '\n4', '\r\n5']:
            yield chunk

    with patch.object(Response, 'iter_content', mock_iter_content):
        result = list(
            _iter_lines_generator(response=Response(), decode_unicode=True))
        assert result == ['1', '2', '3', '4', '5']


def test_iter_content_generator():
    """Test CRLF -> LF newline conversion."""
    def mock_iter_content(self, chunk_size, decode_unicode):
        for chunk in ['1\r\n2\r\n', '3\r', '\n4', '\r\n5']:
            yield chunk

    with patch.object(Response, 'iter_content', mock_iter_content):
        result = list(
            _iter_content_generator(response=Response(), decode_unicode=True))
        assert result == ['1\n2\n', '3', '\n4', '\n5']

        result = list(
            _iter_content_generator(response=Response(), decode_unicode=False))
        assert result == ['1\r\n2\r\n', '3\r', '\n4', '\r\n5']


def test_generic_request_exceptions():
    st = SpaceTrackClient('identity', 'password')

    with pytest.raises(ValueError):
        st.generic_request(class_='tle', iter_lines=True, iter_content=True)

    with pytest.raises(ValueError):
        st.generic_request(class_='thisclassdoesnotexist')

    def mock_get_predicate_fields(self, class_):
        return set()

    patch_authenticate = patch.object(SpaceTrackClient, 'authenticate')

    patch_get_predicate_fields = patch.object(
        SpaceTrackClient, '_get_predicate_fields', mock_get_predicate_fields)

    with patch_authenticate, patch_get_predicate_fields:
        with pytest.raises(TypeError):
            st.generic_request('tle', madeupkeyword=None)


@responses.activate
def test_generic_request():
    responses.add(
        responses.POST, 'https://www.space-track.org/ajaxauth/login', json='""')

    responses.add(
        responses.GET,
        'https://www.space-track.org/basicspacedata/modeldef/class/tle_publish',
        json={
            'controller': 'basicspacedata',
            'data': [
                {
                    'Default': '0000-00-00 00:00:00',
                    'Extra': '',
                    'Field': 'PUBLISH_EPOCH',
                    'Key': '',
                    'Null': 'NO',
                    'Type': 'datetime'
                },
                {
                    'Default': '',
                    'Extra': '',
                    'Field': 'TLE_LINE1',
                    'Key': '',
                    'Null': 'NO',
                    'Type': 'char(71)'
                },
                {
                    'Default': '',
                    'Extra': '',
                    'Field': 'TLE_LINE2',
                    'Key': '',
                    'Null': 'NO',
                    'Type': 'char(71)'
                }
            ]})

    tle = (
        '1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n'
        '2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n')

    normalised_tle = tle.replace('\r\n', '\n')

    responses.add(
        responses.GET,
        'https://www.space-track.org/basicspacedata/query/class/tle_publish'
        '/format/tle',
        body=tle)

    st = SpaceTrackClient('identity', 'password')
    assert st.generic_request('tle_publish', format='tle') == normalised_tle

    lines = list(
        st.generic_request('tle_publish', iter_lines=True, format='tle'))

    assert lines == [
        '1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927',
        '2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537'
    ]


@responses.activate
def test_predicate_parse():
    st = SpaceTrackClient('identity', 'password')

    predicates_data = [
        {
            'Default': '',
            'Extra': '',
            'Field': 'TEST',
            'Key': '',
            'Null': 'NO',
            'Type': '%brokentype'
        }
    ]

    with pytest.raises(ValueError):
        st._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            'Default': '',
            'Extra': '',
            'Field': 'TEST',
            'Key': '',
            'Null': 'NO',
            'Type': 'unknowntype'
        }
    ]

    with pytest.raises(ValueError):
        st._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            'Default': '',
            'Extra': '',
            'Field': 'TEST',
            'Key': '',
            'Null': 'NO',
            'Type': 'enum()'
        }
    ]

    with pytest.raises(ValueError):
        st._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            'Default': '',
            'Extra': '',
            'Field': 'TEST',
            'Key': '',
            'Null': 'NO',
            'Type': "enum('a','b')"
        }
    ]

    predicate = st._parse_predicates_data(predicates_data)[0]
    assert predicate.values == ('a', 'b')


def test_spacetrack_methods():
    """Verify that e.g. st.tle_publish calls st.generic_request('tle_publish')"""
    st = SpaceTrackClient('identity', 'password')
    with patch.object(SpaceTrackClient, 'generic_request') as mock_generic_request:
        for class_ in st.request_classes:
            method = getattr(st, class_)
            method()
            assert mock_generic_request.call_args == call(class_)

    with pytest.raises(AttributeError):
        st.madeupmethod()


@responses.activate
def test_authenticate():
    def request_callback(request):
        if 'wrongpassword' in request.body:
            return (200, dict(), json.dumps({'Login': 'Failed'}))
        else:
            return (200, dict(), json.dumps(''))

    responses.add_callback(
        responses.POST, 'https://www.space-track.org/ajaxauth/login',
        callback=request_callback, content_type='application/json')

    st = SpaceTrackClient('identity', 'wrongpassword')

    with pytest.raises(AuthenticationError):
        st.authenticate()

    assert len(responses.calls) == 1

    st.password = 'correctpassword'
    st.authenticate()
    st.authenticate()

    # Check that only one login request was made since successful
    # authentication
    assert len(responses.calls) == 2


def test_repr():
    st = SpaceTrackClient('hello@example.com', 'mypassword')
    assert repr(st) == "SpaceTrackClient<identity='hello@example.com'>"
    assert 'mypassword' not in repr(st)

    predicate = Predicate(name='a', type_='int', nullable=True)
    assert repr(predicate) == "Predicate(name='a', type_='int', nullable=True)"

    predicate = Predicate(
        name='a', type_='enum', nullable=True, values=('a', 'b'))

    reprstr = "Predicate(name='a', type_='enum', nullable=True, values=('a', 'b'))"
    assert repr(predicate) == reprstr
