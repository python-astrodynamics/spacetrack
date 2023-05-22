import pytest
import respx

from spacetrack import SpaceTrackClient
from spacetrack.base import BASE_URL


@pytest.fixture(scope="session")
def respx_router():
    # Create an instance of MockRouter with our settings.
    return respx.mock(assert_all_called=False, base_url=BASE_URL)


@pytest.fixture
def respx_mock(respx_router):
    with respx_router:
        yield respx_router


@pytest.fixture
def mock_auth(respx_mock):
    respx_mock.post("ajaxauth/login").respond(json="")


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
