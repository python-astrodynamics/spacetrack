import datetime as dt
from unittest.mock import Mock, call, patch

import httpx2
import pytest
from pytest_httpx2 import IteratorStream
from rush.quota import Quota

from spacetrack import (
    AuthenticationError,
    SpaceTrackClient,
    UnknownPredicateTypeWarning,
)
from spacetrack.base import (
    BASE_URL,
    Predicate,
    _iter_content_generator,
    _raise_for_status,
)


def api_url(path):
    return f"{BASE_URL}{path}"


@pytest.fixture
def client(httpx2_mock):
    with SpaceTrackClient("identity", "password") as st:
        yield st


def test_custom_httpx_client():
    httpx_client = httpx2.Client()

    with SpaceTrackClient("identity", "password", httpx_client=httpx_client) as client:
        assert client.client is httpx_client

    with pytest.raises(TypeError, match=r"httpx2\.Client"):
        SpaceTrackClient("identity", "password", httpx_client=object())


def test_iter_content_generator():
    """Test CRLF -> LF newline conversion."""

    def mock_iter_bytes():
        yield from [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]

    def mock_iter_text():
        for chunk in mock_iter_bytes():
            yield chunk.decode("utf-8")

    response = httpx2.Response(200)
    with patch.object(response, "iter_text", mock_iter_text):
        result = list(_iter_content_generator(response=response, decode_unicode=True))
        assert result == ["1\n2\n", "3", "\n4", "\n5"]

    with patch.object(response, "iter_bytes", mock_iter_bytes):
        result = list(_iter_content_generator(response=response, decode_unicode=False))
        assert result == [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]


def test_generic_request_exceptions(client, mock_auth, mock_predicates_empty):
    with pytest.raises(ValueError):
        client.generic_request(class_="gp", iter_lines=True, iter_content=True)

    with pytest.raises(ValueError):
        client.generic_request(class_="thisclassdoesnotexist")

    with pytest.raises(TypeError):
        client.generic_request("gp", madeupkeyword=None)

    with pytest.raises(ValueError):
        client.generic_request(class_="gp", controller="nonsense")

    with pytest.raises(ValueError):
        client.generic_request(class_="nonsense", controller="basicspacedata")

    with pytest.raises(AttributeError):
        client.basicspacedata.blahblah


def test_get_predicates_exceptions(client):
    with pytest.raises(ValueError):
        client.get_predicates(class_="gp", controller="nonsense")

    with pytest.raises(ValueError):
        client.get_predicates(class_="nonsense", controller="basicspacedata")


def test_get_predicates(client):
    patch_get_predicates = patch.object(SpaceTrackClient, "get_predicates")

    with patch_get_predicates as mock_get_predicates:
        client.gp.get_predicates()
        client.basicspacedata.gp.get_predicates()
        client.basicspacedata.get_predicates("gp")
        client.get_predicates("gp")
        client.get_predicates("gp", "basicspacedata")

        expected_calls = [
            call(class_="gp", controller="basicspacedata"),
            call(class_="gp", controller="basicspacedata"),
            call(class_="gp", controller="basicspacedata"),
            call("gp"),
            call("gp", "basicspacedata"),
        ]

        assert mock_get_predicates.call_args_list == expected_calls


def test_generic_request(httpx2_mock, client, mock_auth, mock_gp_predicates):
    tle = (
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n"
    )

    normalised_tle = tle.replace("\r\n", "\n")

    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/query/class/gp/format/tle"),
        text=tle,
        is_reusable=True,
    )

    assert client.gp(format="tle") == normalised_tle

    lines = list(client.gp(iter_lines=True, format="tle"))

    assert lines == [
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537",
    ]

    httpx2_mock.add_response(
        method="GET", url=api_url("basicspacedata/query/class/gp"), json={"a": 5}
    )

    result = client.gp()
    assert result["a"] == 5

    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/query/class/gp"),
        stream=IteratorStream([b"abc", b"def"]),
    )

    result = list(client.gp(iter_content=True))

    assert "".join(result) == "abcdef"


def test_predicate_error(client, mock_auth, mock_predicates_empty):
    with pytest.raises(TypeError, match=r"unexpected argument 'banana'"):
        client.gp(banana=4)


def test_bytes_response(client, httpx2_mock, mock_auth, mock_download_predicates):
    data = b"bytes response \r\n"

    url = "fileshare/query/class/download/format/stream"
    httpx2_mock.add_response(method="GET", url=api_url(url), content=data)

    assert client.download(format="stream") == data

    with pytest.raises(ValueError):
        client.download(iter_lines=True, format="stream")

    # Just use file_id to disambiguate URL from those above
    httpx2_mock.add_response(
        method="GET", url=api_url(url), stream=IteratorStream([b"abc", b"def"])
    )

    result = list(client.download(format="stream", iter_content=True))

    assert b"".join(result) == b"abcdef"


def test_ratelimit_error(client, httpx2_mock, mock_auth, mock_gp_predicates):
    url = api_url("basicspacedata/query/class/gp")
    httpx2_mock.add_response(
        method="GET", url=url, status_code=500, text="violated your query rate limit"
    )
    httpx2_mock.add_response(method="GET", url=url, json={"a": 1})

    # Shrink the rate limit period so that the real _ratelimit_wait
    # implementation only sleeps briefly.
    client._per_minute_throttle.rate = Quota(
        period=dt.timedelta(milliseconds=50), count=30
    )

    with patch.object(
        client, "_ratelimit_wait", wraps=client._ratelimit_wait
    ) as mock_wait:
        # Do it first without our own callback, then with.

        assert client.gp() == {"a": 1}
        assert len(httpx2_mock.get_requests(method="GET", url=url)) == 2

        mock_callback = Mock()
        client.callback = mock_callback

        httpx2_mock.add_response(
            method="GET",
            url=url,
            status_code=500,
            text="violated your query rate limit",
        )
        httpx2_mock.add_response(method="GET", url=url, json={"a": 1})

        assert client.gp() == {"a": 1}
        assert len(httpx2_mock.get_requests(method="GET", url=url)) == 4

    assert mock_callback.call_count == 1
    assert mock_wait.call_args_list == [call(0.05), call(0.05)]


def test_non_ratelimit_error(client, httpx2_mock, mock_auth, mock_gp_predicates):
    # Change ratelimiter period to speed up test
    client._per_minute_throttle.rate = Quota.per_second(30)

    mock_callback = Mock()
    client.callback = mock_callback

    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/query/class/gp"),
        status_code=500,
        text="some other error",
    )

    with pytest.raises(httpx2.HTTPStatusError):
        client.gp()

    assert not mock_callback.called


def test_predicate_parse_modeldef(client):
    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "%brokentype",
        }
    ]

    with pytest.raises(ValueError):
        client._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "unknowntype",
        }
    ]

    msg = "Unknown predicate type 'unknowntype'"
    with pytest.warns(UnknownPredicateTypeWarning, match=msg):
        client._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "enum()",
        }
    ]

    with pytest.raises(ValueError):
        client._parse_predicates_data(predicates_data)

    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "enum('a','b')",
        }
    ]

    predicate = client._parse_predicates_data(predicates_data)[0]
    assert predicate.values == ("a", "b")

    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "enum('a')",
        }
    ]

    predicate = client._parse_predicates_data(predicates_data)[0]
    assert predicate.values == ("a",)

    predicates_data = [
        {
            "Default": "",
            "Extra": "",
            "Field": "TEST",
            "Key": "",
            "Null": "NO",
            "Type": "enum('a','b','c')",
        }
    ]

    predicate = client._parse_predicates_data(predicates_data)[0]
    assert predicate.values == ("a", "b", "c")


def test_bare_spacetrack_methods(client):
    """Verify that e.g. client.gp calls client.generic_request('gp')"""
    seen = set()
    with patch.object(SpaceTrackClient, "generic_request") as mock_generic_request:
        for controller, classes in client.request_controllers.items():
            for class_ in classes:
                if class_ in seen:
                    continue
                seen.add(class_)
                method = getattr(client, class_)
                method()
                expected = call(class_=class_, controller=controller)
                assert mock_generic_request.call_args == expected

    with pytest.raises(AttributeError):
        client.madeupmethod()


def test_controller_spacetrack_methods(client):
    with patch.object(SpaceTrackClient, "generic_request") as mock_generic_request:
        for controller, classes in client.request_controllers.items():
            for class_ in classes:
                controller_proxy = getattr(client, controller)
                method = getattr(controller_proxy, class_)
                method()
                expected = call(class_=class_, controller=controller)
                assert mock_generic_request.call_args == expected


def test_authenticate(httpx2_mock):
    def request_callback(request):
        if b"wrongpassword" in request.content:
            return httpx2.Response(200, json={"Login": "Failed"})
        elif b"unknownresponse" in request.content:
            # Space-Track doesn't respond like this, but make sure anything
            # other than {'Login': 'Failed'} doesn't raise AuthenticationError
            return httpx2.Response(200, json={"Login": "Successful"})
        else:
            return httpx2.Response(200, json="")

    login_url = api_url("ajaxauth/login")
    httpx2_mock.add_callback(
        request_callback, method="POST", url=login_url, is_reusable=True
    )
    httpx2_mock.add_response(
        method="GET",
        url=api_url("ajaxauth/logout"),
        json="Successfully logged out",
        is_reusable=True,
    )

    with SpaceTrackClient("identity", "wrongpassword") as client:
        with pytest.raises(AuthenticationError):
            client.authenticate()

        assert len(httpx2_mock.get_requests(method="POST", url=login_url)) == 1

        client.password = "correctpassword"
        client.authenticate()
        client.authenticate()

        # Check that only one login request was made since successful
        # authentication
        assert len(httpx2_mock.get_requests(method="POST", url=login_url)) == 2

    with SpaceTrackClient("identity", "unknownresponse") as client:
        client.authenticate()


def test_base_url(httpx2_mock):
    login_url = "https://example.com/ajaxauth/login"
    httpx2_mock.add_response(method="POST", url=login_url, json='""')
    httpx2_mock.add_response(
        method="GET",
        url="https://example.com/ajaxauth/logout",
        json="Successfully logged out",
    )
    with SpaceTrackClient(
        "identity", "password", base_url="https://example.com"
    ) as client:
        client.authenticate()

    assert len(httpx2_mock.get_requests(method="POST", url=login_url)) == 1


def test_raise_for_status(httpx2_mock):
    httpx2_mock.add_response(
        method="GET",
        url="http://example.com/1",
        status_code=400,
        json={"error": "problem"},
    )
    httpx2_mock.add_response(
        method="GET",
        url="http://example.com/2",
        status_code=400,
        json={"wrongkey": "problem"},
    )
    httpx2_mock.add_response(
        method="GET", url="http://example.com/3", status_code=400, json="problem"
    )
    httpx2_mock.add_response(method="GET", url="http://example.com/4", status_code=400)

    response1 = httpx2.get("http://example.com/1")
    response2 = httpx2.get("http://example.com/2")
    response3 = httpx2.get("http://example.com/3")
    response4 = httpx2.get("http://example.com/4")

    with pytest.raises(httpx2.HTTPStatusError) as exc:
        _raise_for_status(response1)
    assert "Space-Track" in str(exc.value)
    assert "\nproblem" in str(exc.value)

    with pytest.raises(httpx2.HTTPStatusError) as exc:
        _raise_for_status(response2)
    assert "Space-Track" in str(exc.value)
    assert '{"wrongkey":"problem"}' in str(exc.value)

    with pytest.raises(httpx2.HTTPStatusError) as exc:
        _raise_for_status(response3)
    assert "Space-Track" in str(exc.value)
    assert '\n"problem"' in str(exc.value)

    with pytest.raises(httpx2.HTTPStatusError) as exc:
        _raise_for_status(response4)
    assert "Space-Track" not in str(exc.value)


def test_repr(httpx2_mock):
    with SpaceTrackClient("hello@example.com", "mypassword") as client:
        assert repr(client) == "SpaceTrackClient<identity='hello@example.com'>"
        assert "mypassword" not in repr(client)

        predicate = Predicate(name="a", type_="int", nullable=True, default=None)
        reprstr = "Predicate(name='a', type_='int', nullable=True, default=None)"
        assert repr(predicate) == reprstr

        predicate = Predicate(
            name="a", type_="enum", nullable=True, values=("a", "b"), default=None
        )

        reprstr = (
            "Predicate(name='a', type_='enum', nullable=True, "
            "default=None, values=('a', 'b'))"
        )
        assert repr(predicate) == reprstr

        controller_proxy = client.basicspacedata
        reprstr = "_ControllerProxy<controller='basicspacedata'>"
        assert repr(controller_proxy) == reprstr


def test_dir(client):
    assert [s for s in dir(client) if not s.startswith("_")] == [
        "announcement",
        "base_url",
        "basicspacedata",
        "boxscore",
        "callback",
        "car",
        "cdm",
        "cdm_public",
        "client",
        "decay",
        "delete",
        "dirs",
        "download",
        "expandedspacedata",
        "file",
        "file_history",
        "fileshare",
        "folder",
        "gp",
        "gp_history",
        "identity",
        "launch_site",
        "maneuver",
        "maneuver_history",
        "organization",
        "password",
        "publicfiles",
        "satcat",
        "satcat_change",
        "satcat_debut",
        "satellite",
        "spephemeris",
        "tip",
        "upload",
    ]


@pytest.mark.parametrize(
    "predicate, input, output",
    [
        (Predicate("a", "float"), "0.5", 0.5),
        (Predicate("a", "int"), "5", 5),
        (
            Predicate("a", "datetime"),
            "2017-01-01 01:02:03",
            dt.datetime(2017, 1, 1, 1, 2, 3),
        ),
        (Predicate("a", "date"), "2017-01-01", dt.date(2017, 1, 1)),
        (Predicate("a", "enum", values=("a", "b")), "a", "a"),
        (Predicate("a", "int"), None, None),
        (Predicate("a", "mediumtext"), "Hello", "Hello"),
    ],
)
def test_predicate_parse_type(predicate, input, output):
    assert predicate.parse(input) == output


def test_parse_types(client, httpx2_mock, mock_auth):
    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/modeldef/class/gp"),
        json={
            "controller": "basicspacedata",
            "data": [
                {
                    "Default": "0000-00-00 00:00:00",
                    "Extra": "",
                    "Field": "PUBLISH_EPOCH",
                    "Key": "",
                    "Null": "NO",
                    "Type": "datetime",
                },
                {
                    "Default": None,
                    "Extra": "",
                    "Field": "CREATION_DATE",
                    "Key": "",
                    "Null": "YES",
                    "Type": "datetime",
                },
                {
                    "Default": "",
                    "Extra": "",
                    "Field": "TLE_LINE1",
                    "Key": "",
                    "Null": "NO",
                    "Type": "char(71)",
                },
                {
                    "Default": "",
                    "Extra": "",
                    "Field": "TLE_LINE2",
                    "Key": "",
                    "Null": "NO",
                    "Type": "char(71)",
                },
            ],
        },
    )

    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/query/class/gp"),
        json=[
            {
                # Test a type that is parsed.
                "PUBLISH_EPOCH": "2017-01-02 03:04:05",
                # Newer classes (e.g. gp) return a different date format
                "CREATION_DATE": "2017-01-02T03:04:05",
                # Test a type that is passed through.
                "TLE_LINE1": "The quick brown fox jumps over the lazy dog.",
                # Test a field there was no predicate for.
                "OTHER_FIELD": "Spam and eggs.",
            }
        ],
    )

    (result,) = client.gp(parse_types=True)
    assert result["PUBLISH_EPOCH"] == dt.datetime(2017, 1, 2, 3, 4, 5)
    assert result["TLE_LINE1"] == "The quick brown fox jumps over the lazy dog."
    assert result["OTHER_FIELD"] == "Spam and eggs."

    with pytest.raises(ValueError) as exc_info:
        client.gp(format="tle", parse_types=True)

    assert "parse_types" in exc_info.value.args[0]


def test_params(httpx2_mock, mock_auth):
    data = b"hello\n"
    httpx2_mock.add_response(
        method="GET",
        url=api_url("publicfiles/query/class/download"),
        match_params={"name": "filename.txt"},
        content=data,
    )

    with SpaceTrackClient("identity", "password") as client:
        result = client.publicfiles.download(name="filename.txt", iter_content=True)

    assert b"".join(result) == data


def test_modeldef_cache(httpx2_mock, mock_auth, cache_file_mangler):
    # This test creates three independently authenticated clients.
    mock_auth()
    mock_auth()

    query_url = api_url("basicspacedata/query/class/gp/norad_cat_id/25541")
    httpx2_mock.add_response(
        method="GET", url=query_url, json="dummy", is_reusable=True
    )

    modeldef_url = api_url("basicspacedata/modeldef/class/gp")
    httpx2_mock.add_response(
        method="GET",
        url=modeldef_url,
        is_reusable=True,
        json={
            "controller": "fileshare",
            "data": [
                {
                    "Field": "NORAD_CAT_ID",
                    "Type": "int(10) unsigned",
                    "Null": "NO",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
            ],
        },
    )

    with SpaceTrackClient("identity", "password") as client:
        assert client.gp(norad_cat_id=25541) == "dummy"
        assert len(httpx2_mock.get_requests(method="GET", url=modeldef_url)) == 1

        assert client.gp(norad_cat_id=25541) == "dummy"
        assert len(httpx2_mock.get_requests(method="GET", url=modeldef_url)) == 1

    with SpaceTrackClient("identity", "password") as client:
        assert client.gp(norad_cat_id=25541) == "dummy"
        assert len(httpx2_mock.get_requests(method="GET", url=modeldef_url)) == 1

        cache_files = list(client._cache_path.glob("*.json"))
        assert len(cache_files) == 1
        assert cache_files[0].name.startswith("predicates-")
        assert cache_files[0].name.endswith(".json")

        for file in cache_files:
            cache_file_mangler(file)

        # Even though cache file is gone, client still has it in memory so there
        # should be no new modeldef request
        assert client.gp(norad_cat_id=25541) == "dummy"
        assert len(httpx2_mock.get_requests(method="GET", url=modeldef_url)) == 1

    with SpaceTrackClient("identity", "password") as client:
        # There should be a new modeldef request because we deleted the cache file
        assert client.gp(norad_cat_id=25541) == "dummy"
        assert len(httpx2_mock.get_requests(method="GET", url=modeldef_url)) == 2


def test_implicit_cleanup_warning():
    with pytest.warns(ResourceWarning, match="without being closed explicitly"):
        SpaceTrackClient("identity", "password")


def test_custom_cache_path(httpx2_mock, tmp_path):
    with SpaceTrackClient("identity", "password", cache_path=tmp_path) as client:
        assert client._cache_path == tmp_path
