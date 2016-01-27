# coding: utf-8
from __future__ import absolute_import, division, print_function

import pytest
from requests import Response
from spacetrack import SpaceTrackClient
from spacetrack.base import _iter_content_generator, _iter_lines_generator

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch


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


def test_generic_request():
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



