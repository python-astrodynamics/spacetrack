# coding: utf-8
from __future__ import absolute_import, division, print_function

from collections.abc import AsyncIterator
from unittest.mock import Mock, patch

import asyncio
import pytest
from aiohttp import ClientResponse
from spacetrack import AuthenticationError
from spacetrack.aio import (
    AsyncSpaceTrackClient, _AsyncChunkIterator, _AsyncLineIterator)
from yarl import URL


@pytest.mark.asyncio
async def test_authenticate():
    st = AsyncSpaceTrackClient('identity', 'wrongpassword')

    loop = asyncio.get_event_loop()
    response = ClientResponse(
        'post', URL('https://www.space-track.org/ajaxauth/login'))
    response._post_init(loop)

    response.status = 200
    response.json = Mock()

    async def mock_post(url, data):
        response.json.return_value = asyncio.Future()
        if data['password'] == 'wrongpassword':
            response.json.return_value.set_result({'Login': 'Failed'})
        elif data['password'] == 'unknownresponse':
            # Space-Track doesn't respond like this, but make sure anything
            # other than {'Login': 'Failed'} doesn't raise AuthenticationError
            response.json.return_value.set_result({'Login': 'Successful'})
        else:
            response.json.return_value.set_result('')
        return response

    with st, patch.object(st.session, 'post', mock_post):
        with pytest.raises(AuthenticationError):
            await st.authenticate()

        assert response.json.call_count == 1

        st.password = 'password'
        await st.authenticate()

        # This shouldn't make a HTTP request since we're already authenticated.
        await st.authenticate()

    assert response.json.call_count == 2

    st = AsyncSpaceTrackClient('identity', 'unknownresponse')

    with st, patch.object(st.session, 'post', mock_post):
        await st.authenticate()

    response.close()


@pytest.mark.asyncio
async def test_generic_request_exceptions():
    st = AsyncSpaceTrackClient('identity', 'password')

    with pytest.raises(ValueError):
        await st.generic_request(class_='tle', iter_lines=True, iter_content=True)

    with pytest.raises(ValueError):
        await st.generic_request(class_='thisclassdoesnotexist')

    def mock_authenticate(self):
        result = asyncio.Future()
        result.set_result(None)
        return result

    def mock_get_predicates(self, class_):
        result = asyncio.Future()
        result.set_result([])
        return result

    patch_authenticate = patch.object(
        AsyncSpaceTrackClient, 'authenticate', mock_authenticate)

    patch_get_predicates = patch.object(
        AsyncSpaceTrackClient, 'get_predicates', mock_get_predicates)

    with patch_authenticate, patch_get_predicates:
        with pytest.raises(TypeError):
            await st.generic_request('tle', madeupkeyword=None)

    st.close()


@pytest.mark.asyncio
async def test_generic_request():
    def mock_authenticate(self):
        result = asyncio.Future()
        result.set_result(None)
        return result

    def mock_download_predicate_data(self, class_, controller=None):
        result = asyncio.Future()
        data = [
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
        ]

        result.set_result(data)
        return result

    st = AsyncSpaceTrackClient('identity', 'password')

    loop = asyncio.get_event_loop()
    response = ClientResponse(
        'get', URL('https://www.space-track.org/basicspacedata/query/class'
                   '/tle_publish/format/tle'))
    response._post_init(loop)

    tle = (
        '1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n'
        '2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n')

    normalised_tle = tle.replace('\r\n', '\n')

    response.status = 200
    response.text = Mock()

    response.text.return_value = asyncio.Future()
    response.text.return_value.set_result(tle)

    mock_get = asyncio.Future()
    mock_get.set_result(response)

    patch_authenticate = patch.object(
        AsyncSpaceTrackClient, 'authenticate', mock_authenticate)

    patch_download_predicate_data = patch.object(
        AsyncSpaceTrackClient, '_download_predicate_data',
        mock_download_predicate_data)

    patch_get = patch.object(st.session, 'get', return_value=mock_get)

    with patch_authenticate, patch_download_predicate_data, patch_get:
        assert await st.tle_publish(format='tle') == normalised_tle

    response.close()

    response = ClientResponse(
        'get', URL('https://www.space-track.org/basicspacedata/query/class'
                   '/tle_publish'))
    response._post_init(loop)

    response.status = 200
    response.json = Mock()
    response.json.return_value = asyncio.Future()
    response.json.return_value.set_result({'a': 5})

    mock_get = asyncio.Future()
    mock_get.set_result(response)

    patch_get = patch.object(st.session, 'get', return_value=mock_get)

    with patch_authenticate, patch_download_predicate_data, patch_get:
        result = await st.tle_publish()
        assert result['a'] == 5

    response.close()

    st.close()


@pytest.mark.asyncio
async def test_async_iterator():
    response = Mock()

    class TestAsyncIterator(AsyncIterator):
        def __init__(self):
            self.i = 0

        async def __anext__(self):
            self.i += 1

            if self.i > 5:
                raise StopAsyncIteration
            else:
                return '{}\r\n'.format(self.i).encode('utf-8')

    response.content = TestAsyncIterator()
    ait = _AsyncLineIterator(response, True)
    ait.get_encoding = lambda: 'utf-8'

    lines = list()
    async for line in ait:
        lines.append(line)

    assert lines == ['1', '2', '3', '4', '5']

    response = Mock()
    response.content.iter_chunked.return_value = TestAsyncIterator()
    ait = _AsyncChunkIterator(response, True)
    ait.get_encoding = lambda: 'utf-8'

    chunks = list()
    async for chunk in ait:
        chunks.append(chunk)

    assert chunks == ['1\n', '2\n', '3\n', '4\n', '5\n']
