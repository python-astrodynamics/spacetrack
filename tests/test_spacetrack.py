import datetime as dt
from unittest.mock import Mock, call, patch

import httpx
import pytest
from rush.quota import Quota

from spacetrack import (
    AuthenticationError,
    SpaceTrackClient,
    UnknownPredicateTypeWarning,
)
from spacetrack.base import Predicate, _iter_content_generator, _raise_for_status


@pytest.fixture
def client(respx_mock):
    with SpaceTrackClient("identity", "password") as st:
        yield st


def test_iter_content_generator():
    """Test CRLF -> LF newline conversion."""

    def mock_iter_bytes():
        yield from [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]

    def mock_iter_text():
        for chunk in mock_iter_bytes():
            yield chunk.decode("utf-8")

    response = httpx.Response(200)
    with patch.object(response, "iter_text", mock_iter_text):
        result = list(_iter_content_generator(response=response, decode_unicode=True))
        assert result == ["1\n2\n", "3", "\n4", "\n5"]

    with patch.object(response, "iter_bytes", mock_iter_bytes):
        result = list(_iter_content_generator(response=response, decode_unicode=False))
        assert result == [b"1\r\n2\r\n", b"3\r", b"\n4", b"\r\n5"]


def test_generic_request_exceptions(client, mock_auth, mock_predicates_empty):
    with pytest.raises(ValueError):
        client.generic_request(class_="tle", iter_lines=True, iter_content=True)

    with pytest.raises(ValueError):
        client.generic_request(class_="thisclassdoesnotexist")

    with pytest.raises(TypeError):
        client.generic_request("tle", madeupkeyword=None)

    with pytest.raises(ValueError):
        client.generic_request(class_="tle", controller="nonsense")

    with pytest.raises(ValueError):
        client.generic_request(class_="nonsense", controller="basicspacedata")

    with pytest.raises(AttributeError):
        client.basicspacedata.blahblah


def test_get_predicates_exceptions(client):
    with pytest.raises(ValueError):
        client.get_predicates(class_="tle", controller="nonsense")

    with pytest.raises(ValueError):
        client.get_predicates(class_="nonsense", controller="basicspacedata")


def test_get_predicates(client):
    patch_get_predicates = patch.object(SpaceTrackClient, "get_predicates")

    with patch_get_predicates as mock_get_predicates:
        client.tle.get_predicates()
        client.basicspacedata.tle.get_predicates()
        client.basicspacedata.get_predicates("tle")
        client.get_predicates("tle")
        client.get_predicates("tle", "basicspacedata")

        expected_calls = [
            call(class_="tle", controller="basicspacedata"),
            call(class_="tle", controller="basicspacedata"),
            call(class_="tle", controller="basicspacedata"),
            call("tle"),
            call("tle", "basicspacedata"),
        ]

        assert mock_get_predicates.call_args_list == expected_calls


def test_generic_request(respx_mock, client, mock_auth, mock_tle_publish_predicates):
    tle = (
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927\r\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537\r\n"
    )

    normalised_tle = tle.replace("\r\n", "\n")

    respx_mock.get("basicspacedata/query/class/tle_publish/format/tle").respond(
        text=tle
    )

    assert client.tle_publish(format="tle") == normalised_tle

    lines = list(client.tle_publish(iter_lines=True, format="tle"))

    assert lines == [
        "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537",
    ]

    respx_mock.get("basicspacedata/query/class/tle_publish").respond(json={"a": 5})

    result = client.tle_publish()
    assert result["a"] == 5

    respx_mock.get("basicspacedata/query/class/tle_publish").respond(
        stream=[b"abc", b"def"]
    )

    result = list(client.tle_publish(iter_content=True))

    assert "".join(result) == "abcdef"


def test_predicate_error(client, mock_auth, mock_predicates_empty):
    with pytest.raises(TypeError, match=r"unexpected argument 'banana'"):
        client.gp(banana=4)


def test_bytes_response(client, respx_mock, mock_auth, mock_download_predicates):
    data = b"bytes response \r\n"

    url = "fileshare/query/class/download/format/stream"
    respx_mock.get(url).respond(content=data)

    assert client.download(format="stream") == data

    with pytest.raises(ValueError):
        client.download(iter_lines=True, format="stream")

    # Just use file_id to disambiguate URL from those above
    respx_mock.get(url).respond(stream=[b"abc", b"def"])

    result = list(client.download(format="stream", iter_content=True))

    assert b"".join(result) == b"abcdef"


def test_ratelimit_error(client, respx_mock, mock_auth, mock_tle_publish_predicates):
    route = respx_mock.get("basicspacedata/query/class/tle_publish").mock(
        side_effect=[
            httpx.Response(500, text="violated your query rate limit"),
            httpx.Response(200, json={"a": 1}),
        ]
    )

    # Change ratelimiter period to speed up test
    client._per_minute_throttle.rate = Quota.per_second(30)

    # Do it first without our own callback, then with.

    assert client.tle_publish() == {"a": 1}
    assert route.call_count == 2
    assert route.calls[0].response.status_code == 500

    mock_callback = Mock()
    client.callback = mock_callback

    route.reset()
    route.side_effect = [
        httpx.Response(500, text="violated your query rate limit"),
        httpx.Response(200, json={"a": 1}),
    ]

    assert client.tle_publish() == {"a": 1}
    assert route.call_count == 2
    assert route.calls[0].response.status_code == 500

    assert mock_callback.call_count == 1


def test_non_ratelimit_error(
    client, respx_mock, mock_auth, mock_tle_publish_predicates
):
    # Change ratelimiter period to speed up test
    client._per_minute_throttle.rate = Quota.per_second(30)

    mock_callback = Mock()
    client.callback = mock_callback

    respx_mock.get("basicspacedata/query/class/tle_publish").respond(
        500, text="some other error"
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.tle_publish()

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
    """Verify that e.g. client.tle_publish calls client.generic_request('tle_publish')"""
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


def test_authenticate(respx_mock):
    def request_callback(request):
        if b"wrongpassword" in request.content:
            return httpx.Response(200, json={"Login": "Failed"})
        elif b"unknownresponse" in request.content:
            # Space-Track doesn't respond like this, but make sure anything
            # other than {'Login': 'Failed'} doesn't raise AuthenticationError
            return httpx.Response(200, json={"Login": "Successful"})
        else:
            return httpx.Response(200, json="")

    route = respx_mock.post("ajaxauth/login").mock(side_effect=request_callback)
    respx_mock.get("ajaxauth/logout").respond(json="Successfully logged out")

    with SpaceTrackClient("identity", "wrongpassword") as client:
        with pytest.raises(AuthenticationError):
            client.authenticate()

        assert route.call_count == 1

        client.password = "correctpassword"
        client.authenticate()
        client.authenticate()

        # Check that only one login request was made since successful
        # authentication
        assert route.call_count == 2

    with SpaceTrackClient("identity", "unknownresponse") as client:
        client.authenticate()


def test_base_url(respx_mock):
    route = respx_mock.post("https://example.com/ajaxauth/login").respond(json='""')
    respx_mock.get("https://example.com/ajaxauth/logout").respond(
        json="Successfully logged out"
    )
    with SpaceTrackClient(
        "identity", "password", base_url="https://example.com"
    ) as client:
        client.authenticate()

    assert route.call_count == 1


def test_raise_for_status(respx_mock):
    respx_mock.get("http://example.com/1").respond(400, json={"error": "problem"})
    respx_mock.get("http://example.com/2").respond(400, json={"wrongkey": "problem"})
    respx_mock.get("http://example.com/3").respond(400, json="problem")
    respx_mock.get("http://example.com/4").respond(400)

    response1 = httpx.get("http://example.com/1")
    response2 = httpx.get("http://example.com/2")
    response3 = httpx.get("http://example.com/3")
    response4 = httpx.get("http://example.com/4")

    with pytest.raises(httpx.HTTPStatusError) as exc:
        _raise_for_status(response1)
    assert "Space-Track" in str(exc.value)
    assert "\nproblem" in str(exc.value)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        _raise_for_status(response2)
    assert "Space-Track" in str(exc.value)
    assert '{"wrongkey":"problem"}' in str(exc.value)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        _raise_for_status(response3)
    assert "Space-Track" in str(exc.value)
    assert '\n"problem"' in str(exc.value)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        _raise_for_status(response4)
    assert "Space-Track" not in str(exc.value)


def test_repr(respx_mock):
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
        "omm",
        "organization",
        "password",
        "publicfiles",
        "satcat",
        "satcat_change",
        "satcat_debut",
        "satellite",
        "spephemeris",
        "tip",
        "tle",
        "tle_latest",
        "tle_publish",
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


def test_parse_types(client, respx_mock, mock_auth):
    respx_mock.get("basicspacedata/modeldef/class/tle_publish").respond(
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

    respx_mock.get("basicspacedata/query/class/tle_publish").respond(
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

    (result,) = client.tle_publish(parse_types=True)
    assert result["PUBLISH_EPOCH"] == dt.datetime(2017, 1, 2, 3, 4, 5)
    assert result["TLE_LINE1"] == "The quick brown fox jumps over the lazy dog."
    assert result["OTHER_FIELD"] == "Spam and eggs."

    with pytest.raises(ValueError) as exc_info:
        client.tle_publish(format="tle", parse_types=True)

    assert "parse_types" in exc_info.value.args[0]


def test_params(respx_mock, mock_auth):
    data = b"hello\n"
    respx_mock.get(
        "publicfiles/query/class/download", params={"name": "filename.txt"}
    ).respond(
        content=data,
    )

    with SpaceTrackClient("identity", "password") as client:
        result = client.publicfiles.download(name="filename.txt", iter_content=True)

    assert b"".join(result) == data


def test_implicit_cleanup_warning():
    with pytest.warns(ResourceWarning, match="without being closed explicitly"):
        SpaceTrackClient("identity", "password")
