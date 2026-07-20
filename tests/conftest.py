import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from spacetrack import SpaceTrackClient
from spacetrack.base import BASE_URL, CACHE_VERSION, PREDICATE_CACHE_EXPIRY_TIME


def api_url(path):
    return f"{BASE_URL}{path}"


@pytest.fixture(autouse=True)
def temporary_cache_dir(monkeypatch, tmp_path):
    def user_cache_path(appname):
        return tmp_path

    with patch("spacetrack.base.user_cache_path", user_cache_path):
        yield


@pytest.fixture
def mock_auth(httpx2_mock):
    def add_auth_responses():
        httpx2_mock.add_response(
            method="POST",
            url=api_url("ajaxauth/login"),
            json="",
        )
        httpx2_mock.add_response(
            method="GET",
            url=api_url("ajaxauth/logout"),
            json="Successfully logged out",
        )

    add_auth_responses()
    return add_auth_responses


@pytest.fixture
def mock_predicates_empty(httpx2_mock):
    for controller, classes in SpaceTrackClient.request_controllers.items():
        for class_ in classes:
            httpx2_mock.add_response(
                method="GET",
                url=api_url(f"{controller}/modeldef/class/{class_}"),
                json={"data": []},
                is_optional=True,
            )


@pytest.fixture
def mock_gp_predicates(httpx2_mock):
    httpx2_mock.add_response(
        method="GET",
        url=api_url("basicspacedata/modeldef/class/gp"),
        is_optional=True,
        json={
            "controller": "basicspacedata",
            "data": [
                {
                    "Field": "CCSDS_OMM_VERS",
                    "Type": "varchar(3)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "COMMENT",
                    "Type": "varchar(33)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "CREATION_DATE",
                    "Type": "datetime",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "ORIGINATOR",
                    "Type": "varchar(7)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "OBJECT_NAME",
                    "Type": "varchar(25)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "OBJECT_ID",
                    "Type": "varchar(12)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "CENTER_NAME",
                    "Type": "varchar(5)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "REF_FRAME",
                    "Type": "varchar(4)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "TIME_SYSTEM",
                    "Type": "varchar(3)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "MEAN_ELEMENT_THEORY",
                    "Type": "varchar(4)",
                    "Null": "NO",
                    "Key": "",
                    "Default": "",
                    "Extra": "",
                },
                {
                    "Field": "EPOCH",
                    "Type": "datetime(6)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "MEAN_MOTION",
                    "Type": "decimal(13,8)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "ECCENTRICITY",
                    "Type": "decimal(13,8)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "INCLINATION",
                    "Type": "decimal(7,4)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "RA_OF_ASC_NODE",
                    "Type": "decimal(7,4)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "ARG_OF_PERICENTER",
                    "Type": "decimal(7,4)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "MEAN_ANOMALY",
                    "Type": "decimal(7,4)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "EPHEMERIS_TYPE",
                    "Type": "tinyint(4)",
                    "Null": "YES",
                    "Key": "",
                    "Default": "0",
                    "Extra": "",
                },
                {
                    "Field": "CLASSIFICATION_TYPE",
                    "Type": "char(1)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "NORAD_CAT_ID",
                    "Type": "int(10) unsigned",
                    "Null": "NO",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "ELEMENT_SET_NO",
                    "Type": "smallint(5) unsigned",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "REV_AT_EPOCH",
                    "Type": "mediumint(8) unsigned",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "BSTAR",
                    "Type": "decimal(19,14)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "MEAN_MOTION_DOT",
                    "Type": "decimal(9,8)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "MEAN_MOTION_DDOT",
                    "Type": "decimal(22,13)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "SEMIMAJOR_AXIS",
                    "Type": "double(12,3)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "PERIOD",
                    "Type": "double(12,3)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "APOAPSIS",
                    "Type": "double(12,3)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "PERIAPSIS",
                    "Type": "double(12,3)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "OBJECT_TYPE",
                    "Type": "varchar(12)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "RCS_SIZE",
                    "Type": "char(6)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "COUNTRY_CODE",
                    "Type": "char(6)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "LAUNCH_DATE",
                    "Type": "date",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "SITE",
                    "Type": "char(5)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "DECAY_DATE",
                    "Type": "date",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "FILE",
                    "Type": "bigint(20) unsigned",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "GP_ID",
                    "Type": "int(10) unsigned",
                    "Null": "NO",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "TLE_LINE0",
                    "Type": "varchar(27)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "TLE_LINE1",
                    "Type": "varchar(71)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
                {
                    "Field": "TLE_LINE2",
                    "Type": "varchar(71)",
                    "Null": "YES",
                    "Key": "",
                    "Default": None,
                    "Extra": "",
                },
            ],
        },
    )


@pytest.fixture
def mock_download_predicates(httpx2_mock):
    httpx2_mock.add_response(
        method="GET",
        url=api_url("fileshare/modeldef/class/download"),
        is_optional=True,
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
