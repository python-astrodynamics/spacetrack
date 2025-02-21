import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import respx

from spacetrack import SpaceTrackClient
from spacetrack.base import BASE_URL, CACHE_VERSION, PREDICATE_CACHE_EXPIRY_TIME


@pytest.fixture(scope="session")
def respx_router():
    # Create an instance of MockRouter with our settings.
    return respx.mock(assert_all_called=False, base_url=BASE_URL)


@pytest.fixture
def respx_mock(respx_router):
    with respx_router:
        yield respx_router


@pytest.fixture(autouse=True)
def temporary_cache_dir(monkeypatch, tmp_path):
    class MockPlatformDirs:
        def __init__(self, appname):
            pass

        @property
        def user_cache_path(self):
            return tmp_path

    with patch("spacetrack.base.PlatformDirs", MockPlatformDirs):
        yield


@pytest.fixture
def mock_auth(respx_mock):
    respx_mock.post("ajaxauth/login").respond(json="")
    respx_mock.get("ajaxauth/logout").respond(json="Successfully logged out")


@pytest.fixture
def mock_predicates_empty(respx_mock):
    for controller, classes in SpaceTrackClient.request_controllers.items():
        for class_ in classes:
            respx_mock.get(f"{controller}/modeldef/class/{class_}").respond(
                json={"data": []}
            )


@pytest.fixture
def mock_tle_publish_predicates(respx_mock):
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


@pytest.fixture
def mock_download_predicates(respx_mock):
    respx_mock.get("fileshare/modeldef/class/download").respond(
        json={
            "controller": "fileshare",
            "data": [
                {
                    "Default": "0",
                    "Extra": "",
                    "Field": "FILE_ID",
                    "Key": "",
                    "Null": "NO",
                    "Type": "int(10) unsigned",
                },
                {
                    "Default": None,
                    "Extra": "",
                    "Field": "FILE_CONTENET",
                    "Key": "",
                    "Null": "YES",
                    "Type": "longblob",
                },
            ],
        },
    )


def cache_mangler_missing(path: Path) -> None:
    path.unlink(missing_ok=True)


def cache_mangler_invalid_json(path: Path) -> None:
    path.write_text("{")


def cache_mangler_not_an_object(path: Path) -> None:
    path.write_text("[]")


def cache_mangler_version_missing(path: Path) -> None:
    with open(path, "w") as f:
        json.dump({"timestamp": 1740152892.518211, "data": {}}, f)


def cache_mangler_wrong_version(path: Path) -> None:
    with open(path, "w") as f:
        json.dump({"version": 42, "timestamp": 1740152892.518211, "data": {}}, f)


def cache_mangler_timestamp_missing(path: Path) -> None:
    with open(path, "w") as f:
        json.dump({"version": CACHE_VERSION, "data": {}}, f)


def cache_mangler_timestamp_invalid(path: Path) -> None:
    with open(path, "w") as f:
        json.dump({"version": CACHE_VERSION, "timestamp": "today", "data": {}}, f)


def cache_mangler_timestamp_overflow(path: Path) -> None:
    with open(path, "w") as f:
        json.dump({"version": CACHE_VERSION, "timestamp": 253402300800, "data": {}}, f)


def cache_mangler_timestamp_expired(path: Path) -> None:
    t = datetime.now(timezone.utc) - PREDICATE_CACHE_EXPIRY_TIME
    with open(path, "w") as f:
        json.dump({"version": CACHE_VERSION, "timestamp": t.timestamp(), "data": {}}, f)


@pytest.fixture(
    params=[
        cache_mangler_missing,
        cache_mangler_invalid_json,
        cache_mangler_not_an_object,
        cache_mangler_version_missing,
        cache_mangler_wrong_version,
        cache_mangler_timestamp_missing,
        cache_mangler_timestamp_invalid,
        cache_mangler_timestamp_overflow,
        cache_mangler_timestamp_expired,
    ],
    ids=lambda p: p.__name__.removeprefix("cache_mangler_"),
)
def cache_file_mangler(request):
    return request.param
