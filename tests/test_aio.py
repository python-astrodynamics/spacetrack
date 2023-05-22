import sys
from unittest.mock import call, patch

import httpx
import pytest
import pytest_asyncio
from rush.quota import Quota

from spacetrack import AsyncSpaceTrackClient
from spacetrack.aio import _iter_content_generator


@pytest.fixture(
    params=[
        pytest.param("asyncio", marks=pytest.mark.asyncio),
        pytest.param("trio", marks=pytest.mark.trio),
    ]
)
def async_runner(request):
    return request.param


@pytest_asyncio.fixture
async def client():
    async with AsyncSpaceTrackClient("identity", "password") as st:
        yield st


async def test_authenticate(client, async_runner, mock_auth):
    await client.authenticate()


@pytest.mark.skipif(sys.version_info < (3, 8), reason="Requires Python 3.8+")
async def test_get_predicates_calls(async_runner, client):
    patch_get_predicates = patch.object(client, "get_predicates")

    with patch_get_predicates as mock_get_predicates:
        await client.tle.get_predicates()
        await client.basicspacedata.tle.get_predicates()
        await client.basicspacedata.get_predicates("tle")
        await client.get_predicates("tle")
        await client.get_predicates("tle", "basicspacedata")

        expected_calls = [
            call(class_="tle", controller="basicspacedata"),
            call(class_="tle", controller="basicspacedata"),
            call(class_="tle", controller="basicspacedata"),
            call("tle"),
            call("tle", "basicspacedata"),
        ]

        assert mock_get_predicates.await_args_list == expected_calls


async def test_get_predicates(
    async_runner, client, mock_auth, mock_tle_publish_predicates
):
    assert len(await client.tle_publish.get_predicates()) == 3


async def test_generic_request(
    client, async_runner, respx_mock, mock_auth, mock_tle_publish_predicates
):
    tle = (
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n"
    )

    normalised_tle = tle.replace("\r\n", "\n")

    respx_mock.get("basicspacedata/query/class/tle_publish/format/tle").respond(
        text=tle
    )

    assert await client.tle_publish(format="tle") == normalised_tle

    respx_mock.get("basicspacedata/query/class/tle_publish").respond(json={"a": 5})

    result = await client.tle_publish()
    assert result["a"] == 5


async def test_iter_content_generator(async_runner):
    """Test CRLF -> LF newline conversion."""

    async def mock_aiter_bytes():
        for chunk in [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]:
            yield chunk

    async def mock_aiter_text():
        async for chunk in mock_aiter_bytes():
            yield chunk.decode("utf-8")

    response = httpx.Response(200)
    with patch.object(response, "aiter_text", mock_aiter_text):
        result = [
            c
            async for c in _iter_content_generator(
                response=response, decode_unicode=True
            )
        ]
        assert result == ["1\n2\n", "3", "\n4", "\n5"]

    with patch.object(response, "aiter_bytes", mock_aiter_bytes):
        result = [
            c
            async for c in _iter_content_generator(
                response=response, decode_unicode=False
            )
        ]
        assert result == [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]


@pytest.mark.skipif(sys.version_info < (3, 8), reason="Requires Python 3.8+")
async def test_ratelimit_error(
    async_runner, client, respx_mock, mock_auth, mock_tle_publish_predicates
):
    from unittest.mock import AsyncMock

    route = respx_mock.get("basicspacedata/query/class/tle_publish").mock(
        side_effect=[
            httpx.Response(500, text="violated your query rate limit"),
            httpx.Response(200, json={"a": 1}),
        ]
    )

    # Change ratelimiter period to speed up test
    client._per_minute_throttle.rate = Quota.per_second(30)

    # Do it first without our own callback, then with.

    assert await client.tle_publish() == {"a": 1}
    assert route.call_count == 2
    assert route.calls[0].response.status_code == 500

    mock_callback = AsyncMock()
    client.callback = mock_callback

    route.reset()
    route.side_effect = [
        httpx.Response(500, text="violated your query rate limit"),
        httpx.Response(200, json={"a": 1}),
    ]

    assert await client.tle_publish() == {"a": 1}
    assert route.call_count == 2
    assert route.calls[0].response.status_code == 500

    assert mock_callback.call_count == 1
    mock_callback.assert_awaited()
