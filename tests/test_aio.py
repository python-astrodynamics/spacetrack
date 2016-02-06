# coding: utf-8
from __future__ import absolute_import, division, print_function

import asyncio
import sys
from unittest.mock import Mock, patch

import pytest
from aiohttp import ClientResponse
from spacetrack import AsyncSpaceTrackClient, AuthenticationError


@pytest.mark.asyncio
async def test_authenticate():
    st = AsyncSpaceTrackClient('identity', 'wrongpassword')

    loop = asyncio.get_event_loop()
    response = ClientResponse(
        'post', 'https://www.space-track.org/ajaxauth/login')
    response._post_init(loop)

    response.status = 200
    response.json = Mock()

    async def mock_post(url, data):
        response.json.return_value = asyncio.Future(loop=loop)
        if data['password'] == 'wrongpassword':
            response.json.return_value.set_result({'Login': 'Failed'})
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
    response.close()
