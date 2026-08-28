import requests_mock
import pytest

from app.services.geocoder import resolve_location


@pytest.mark.parametrize(
    "location",
    ["181,38", "121,91", "nan,30", "121,inf"],
)
def test_resolve_location_rejects_invalid_coordinates(location):
    with requests_mock.Mocker() as mocker:
        with pytest.raises(ValueError, match="invalid coordinates"):
            resolve_location(location)

        assert mocker.request_history == []


def test_resolve_location_normalizes_valid_coordinates():
    assert resolve_location(" 121.6, 38.9 ") == "121.6000,38.9000"
